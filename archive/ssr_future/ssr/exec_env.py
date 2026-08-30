"""Sandboxed command execution.

The SSR harness needs one thing from the environment layer: run a shell
command against a checked-out repository and give back the exit code and the
output. SWE-smith supplies that through Docker images. This module puts a
single interface in front of three backends so that the rest of the harness
never depends on which one is present:

    docker   a SWE-smith image. The intended production backend.
    wsl      a Linux worktree reached through ``wsl -d <distro>``. Used when
             Docker is not installed but a Linux userland is.
    local    a worktree on the host, run with the host interpreter. Used to
             prove the harness itself; the environment is NOT isolated, so it
             is never valid for a corpus run.

Only the ``docker`` backend gives the isolation the protocol assumes. A run
record always carries the backend name, and ``scripts/check_environment.py``
refuses a corpus run on a non-Docker backend unless it is forced.

Safety rules that hold for every backend:

* the agent's commands run with the secrets stripped from the environment
  (``ssr.util.sandbox_environment``);
* file reads and writes are confined to the repository root;
* every command has a wall-clock timeout.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ssr.util import SsrError, get_logger, redact, sandbox_environment, strip_ansi, truncate

DEFAULT_TIMEOUT_S = 300
_MAX_CAPTURE_BYTES = 4_000_000


@dataclass
class ExecResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out

    @property
    def combined(self) -> str:
        if self.stderr and self.stdout:
            return f"{self.stdout}\n--- stderr ---\n{self.stderr}"
        return self.stdout or self.stderr

    def observation(self, limit: int) -> str:
        body, was_truncated = truncate(strip_ansi(self.combined), limit)
        status = "timed out" if self.timed_out else f"exit code {self.exit_code}"
        note = " (output truncated)" if was_truncated else ""
        return f"[{status}]{note}\n{body}"


@dataclass
class EnvironmentInfo:
    backend: str
    source_repo: str
    source_commit: str
    language: str
    environment_id: str | None = None
    image_id: str | None = None
    swesmith_sha: str | None = None
    swesmith_version: str | None = None
    docker_version: str | None = None
    os: str | None = None
    runtime_versions: dict[str, str | None] = field(default_factory=dict)
    repo_size: dict[str, Any] = field(default_factory=dict)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "swesmith_sha": self.swesmith_sha,
            "swesmith_version": self.swesmith_version,
            "environment_id": self.environment_id,
            "image_id": self.image_id,
            "source_repo": self.source_repo,
            "source_commit": self.source_commit,
            "language": self.language,
            "repo_size": self.repo_size or {"bin": "UNKNOWN"},
            "docker_version": self.docker_version,
            "os": self.os,
            "runtime_versions": self.runtime_versions,
        }


class ExecutionEnvironment(ABC):
    """One checked-out repository that commands can be run against."""

    backend: str = "abstract"

    def __init__(self, repo_path: str, *, default_timeout_s: int = DEFAULT_TIMEOUT_S):
        self.repo_path = repo_path
        self.default_timeout_s = default_timeout_s
        self._info: EnvironmentInfo | None = None

    # -- required backend hooks --------------------------------------------
    @abstractmethod
    def _spawn(self, argv: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
        """Run an already-wrapped argv on the host and capture its output."""

    @abstractmethod
    def _wrap(self, command: str, cwd: str) -> list[str]:
        """Turn a shell command string into the argv that runs it in-place."""

    # -- public interface ---------------------------------------------------
    def run(self, command: str, *, timeout_s: int | None = None, cwd: str | None = None) -> ExecResult:
        timeout = timeout_s or self.default_timeout_s
        working = cwd or self.repo_path
        argv = self._wrap(command, working)
        started = time.monotonic()
        code, out, err, timed_out = self._spawn(argv, timeout)
        duration = time.monotonic() - started
        return ExecResult(
            command=command,
            exit_code=code,
            stdout=redact(out),
            stderr=redact(err),
            duration_s=duration,
            timed_out=timed_out,
        )

    def check(self, command: str, *, timeout_s: int | None = None, cwd: str | None = None) -> ExecResult:
        result = self.run(command, timeout_s=timeout_s, cwd=cwd)
        if not result.ok:
            raise SsrError(
                f"command failed in {self.backend} sandbox: {command}\n"
                f"exit={result.exit_code} timed_out={result.timed_out}\n{result.combined[:2000]}"
            )
        return result

    # -- confined file access ----------------------------------------------
    def _resolve(self, relative: str) -> str:
        """Join a repo-relative path, refusing anything that escapes the root."""
        candidate = PurePosixPath(relative.replace("\\", "/"))
        if candidate.is_absolute():
            raise SsrError(f"path must be repository-relative: {relative}")
        parts: list[str] = []
        for part in candidate.parts:
            if part in (".", ""):
                continue
            if part == "..":
                if not parts:
                    raise SsrError(f"path escapes the repository root: {relative}")
                parts.pop()
                continue
            parts.append(part)
        if not parts:
            raise SsrError(f"empty repository-relative path: {relative}")
        return str(PurePosixPath(self.repo_path, *parts))

    def read_file(self, relative: str, *, max_bytes: int = 200_000) -> str:
        target = self._resolve(relative)
        result = self.run(f"cat -- {shlex.quote(target)}", timeout_s=60)
        if not result.ok:
            raise SsrError(f"cannot read {relative}: {result.combined[:500]}")
        return result.stdout[:max_bytes]

    def write_file(self, relative: str, content: str) -> None:
        target = self._resolve(relative)
        parent = str(PurePosixPath(target).parent)
        heredoc = "SSR_EOF_MARKER_9f3a"
        if heredoc in content:
            raise SsrError("file content collides with the write marker")
        # A heredoc always terminates its body with a newline. Drop one
        # trailing newline from the content so that reading a file and
        # writing it back is a round trip, rather than adding a blank line
        # to every file the agent edits.
        body = content[:-1] if content.endswith("\n") else content
        script = (
            f"mkdir -p {shlex.quote(parent)} && "
            f"cat > {shlex.quote(target)} <<'{heredoc}'\n{body}\n{heredoc}\n"
        )
        result = self.run(script, timeout_s=120)
        if not result.ok:
            raise SsrError(f"cannot write {relative}: {result.combined[:500]}")

    def exists(self, relative: str) -> bool:
        target = self._resolve(relative)
        return self.run(f"test -e {shlex.quote(target)}", timeout_s=30).exit_code == 0

    # -- git helpers used by the validator ---------------------------------
    def git(self, args: str, *, timeout_s: int | None = None) -> ExecResult:
        return self.run(f"git -c core.pager=cat {args}", timeout_s=timeout_s or 120)

    def diff_against_head(self) -> str:
        """Working-tree diff, including untracked files."""
        self.git("add -A -N")
        return self.git("diff --no-color --no-ext-diff --binary HEAD").stdout

    def reset_to_clean(self) -> None:
        self.check("git reset --hard --quiet HEAD && git clean -fdq")

    def apply_patch(self, diff_text: str, *, reverse: bool = False) -> ExecResult:
        if not diff_text.strip():
            return ExecResult("git apply (empty)", 0, "", "", 0.0)
        self.write_file(".ssr_patch.diff", diff_text)
        flag = "-R " if reverse else ""
        result = self.run(f"git apply --whitespace=nowarn {flag}.ssr_patch.diff", timeout_s=180)
        self.run("rm -f .ssr_patch.diff", timeout_s=30)
        return result

    def commit_all(self, message: str) -> str:
        self.check("git add -A")
        self.run(
            "git -c user.name=ssr -c user.email=ssr@invalid commit --quiet "
            f"--allow-empty -m {shlex.quote(message)}",
            timeout_s=120,
        )
        return self.git("rev-parse HEAD").stdout.strip()

    # -- metadata -----------------------------------------------------------
    def info(self) -> EnvironmentInfo:
        if self._info is None:
            self._info = self._collect_info()
        return self._info

    def _collect_info(self) -> EnvironmentInfo:
        repo = self.git("config --get remote.origin.url").stdout.strip() or "unknown"
        commit = self.git("rev-parse HEAD").stdout.strip() or "unknown"
        return EnvironmentInfo(
            backend=self.backend,
            source_repo=repo,
            source_commit=commit,
            language=self.detect_language(),
            os=self.run("uname -a", timeout_s=30).stdout.strip() or None,
            runtime_versions=self.detect_runtimes(),
            repo_size=self.measure_repo_size(),
        )

    def detect_language(self) -> str:
        counts = {
            "python": r"\.py$",
            "javascript": r"\.[cm]?jsx?$",
            "typescript": r"\.tsx?$",
            "go": r"\.go$",
            "java": r"\.java$",
            "rust": r"\.rs$",
            "c": r"\.[ch]$",
            "cpp": r"\.(cc|cpp|hpp)$",
            "ruby": r"\.rb$",
            "php": r"\.php$",
        }
        listing = self.git("ls-files").stdout.splitlines()
        if not listing:
            return "unknown"
        import re

        tallies = {
            name: sum(1 for path in listing if re.search(pattern, path))
            for name, pattern in counts.items()
        }
        best = max(tallies, key=lambda name: tallies[name])
        return best if tallies[best] else "unknown"

    def detect_runtimes(self) -> dict[str, str | None]:
        probes = {
            "python": "python3 --version",
            "pip": "python3 -m pip --version",
            "git": "git --version",
            "node": "node --version",
            "go": "go version",
        }
        found: dict[str, str | None] = {}
        for name, command in probes.items():
            result = self.run(f"{command} 2>/dev/null || true", timeout_s=60)
            value = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
            found[name] = value
        return found

    def measure_repo_size(self) -> dict[str, Any]:
        listing = self.git("ls-files").stdout.splitlines()
        files = len(listing)
        line_result = self.run(
            "git ls-files -z | xargs -0 -r cat 2>/dev/null | wc -l", timeout_s=300
        )
        try:
            lines = int(line_result.stdout.strip().split()[0])
        except (ValueError, IndexError):
            lines = 0
        return {
            "files": files,
            "source_files": files,
            "lines": lines,
            "bytes": None,
            "bin": size_bin(lines),
        }

    def close(self) -> None:  # pragma: no cover - default is a no-op
        return


def size_bin(lines: int) -> str:
    """Neutral repository-size bin. Boundaries are declared, not fitted."""
    if lines <= 0:
        return "UNKNOWN"
    if lines < 10_000:
        return "SMALL"
    if lines < 100_000:
        return "MEDIUM"
    return "LARGE"


# --------------------------------------------------------------------------
# backends
# --------------------------------------------------------------------------
def _spawn_host(argv: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            timeout=timeout_s,
            env=sandbox_environment(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or b"").decode("utf-8", "replace")
        err = (exc.stderr or b"").decode("utf-8", "replace")
        return 124, out, err + "\n[harness] command exceeded the timeout", True
    except FileNotFoundError as exc:
        return 127, "", f"[harness] {exc}", False
    return (
        completed.returncode,
        completed.stdout[:_MAX_CAPTURE_BYTES].decode("utf-8", "replace"),
        completed.stderr[:_MAX_CAPTURE_BYTES].decode("utf-8", "replace"),
        False,
    )


class LocalEnvironment(ExecutionEnvironment):
    """A worktree on the host, run with the host shell.

    NOT isolated. Use it to prove the harness, never for a corpus run.
    """

    backend = "local"

    def __init__(self, repo_path: str | Path, **kwargs):
        super().__init__(str(Path(repo_path).resolve()).replace("\\", "/"), **kwargs)
        self._shell = shutil.which("bash") or shutil.which("sh")
        if not self._shell:
            raise SsrError("the local backend needs bash or sh on PATH")
        # A login shell can put a much older git first on PATH than the one
        # this process found, and the harness uses switches old git lacks.
        # Pin the git directory that resolved here.
        git = shutil.which("git")
        self._path_prefix = (
            f'export PATH={shlex.quote(str(Path(git).parent).replace(chr(92), "/"))}:"$PATH"; '
            if git
            else ""
        )

    def _wrap(self, command: str, cwd: str) -> list[str]:
        return [self._shell, "-lc", f"{self._path_prefix}cd {shlex.quote(cwd)} && {command}"]

    def _spawn(self, argv: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
        return _spawn_host(argv, timeout_s)

    def _collect_info(self) -> EnvironmentInfo:
        info = super()._collect_info()
        info.environment_id = f"local:{self.repo_path}"
        return info


class WslEnvironment(ExecutionEnvironment):
    """A Linux worktree reached through ``wsl -d <distro> -e bash -lc``."""

    backend = "wsl"

    def __init__(self, repo_path: str, *, distro: str | None = None, **kwargs):
        super().__init__(repo_path, **kwargs)
        self.distro = distro or os.environ.get("SSR_WSL_DISTRO", "Ubuntu")
        if not shutil.which("wsl") and not shutil.which("wsl.exe"):
            raise SsrError("the wsl backend needs wsl.exe on PATH")

    def _wrap(self, command: str, cwd: str) -> list[str]:
        inner = f"cd {shlex.quote(cwd)} && {command}"
        return ["wsl", "-d", self.distro, "-e", "bash", "-lc", inner]

    def _spawn(self, argv: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
        return _spawn_host(argv, timeout_s)

    def _collect_info(self) -> EnvironmentInfo:
        info = super()._collect_info()
        info.environment_id = f"wsl:{self.distro}:{self.repo_path}"
        return info


class DockerEnvironment(ExecutionEnvironment):
    """A running container started from a SWE-smith image.

    The container is started detached and kept alive for the whole attempt so
    that the agent's shell history and any installed state persist across
    steps, exactly as SWE-smith intends.
    """

    backend = "docker"

    def __init__(
        self,
        image: str,
        *,
        repo_path: str = "/testbed",
        container_name: str | None = None,
        network: str = "none",
        memory: str = "8g",
        cpus: str = "4",
        **kwargs,
    ):
        super().__init__(repo_path, **kwargs)
        self.image = image
        self.network = network
        self.memory = memory
        self.cpus = cpus
        self.container_name = container_name
        self._container_id: str | None = None
        if not shutil.which("docker"):
            raise SsrError(
                "the docker backend needs the docker CLI on PATH. "
                "See docs/swesmith_setup.md for the installation procedure."
            )

    def start(self) -> str:
        if self._container_id:
            return self._container_id
        argv = [
            "docker", "run", "-d", "--rm",
            "--network", self.network,
            "--memory", self.memory,
            "--cpus", self.cpus,
            "-w", self.repo_path,
        ]
        if self.container_name:
            argv += ["--name", self.container_name]
        argv += [self.image, "sleep", "infinity"]
        code, out, err, _ = _spawn_host(argv, 600)
        if code != 0:
            raise SsrError(f"cannot start container from {self.image}: {err or out}")
        self._container_id = out.strip().splitlines()[-1]
        get_logger().info("started container %s from %s", self._container_id[:12], self.image)
        return self._container_id

    def _wrap(self, command: str, cwd: str) -> list[str]:
        container = self.start()
        return ["docker", "exec", "-w", cwd, container, "bash", "-lc", command]

    def _spawn(self, argv: list[str], timeout_s: int) -> tuple[int, str, str, bool]:
        return _spawn_host(argv, timeout_s)

    def _collect_info(self) -> EnvironmentInfo:
        info = super()._collect_info()
        info.environment_id = self.image
        code, out, _, _ = _spawn_host(
            ["docker", "image", "inspect", "--format", "{{.Id}}", self.image], 120
        )
        info.image_id = out.strip() if code == 0 else None
        code, out, _, _ = _spawn_host(["docker", "--version"], 60)
        info.docker_version = out.strip() if code == 0 else None
        return info

    def close(self) -> None:
        if self._container_id:
            _spawn_host(["docker", "kill", self._container_id], 120)
            self._container_id = None


def make_environment(spec: dict[str, Any]) -> ExecutionEnvironment:
    """Build a backend from a declarative spec.

    ``{"backend": "docker", "image": "...", "repo_path": "/testbed"}``
    ``{"backend": "wsl", "repo_path": "/home/u/work/repo", "distro": "Ubuntu"}``
    ``{"backend": "local", "repo_path": "D:/tmp/repo"}``
    """
    backend = (spec.get("backend") or os.environ.get("SSR_EXEC_BACKEND") or "docker").lower()
    timeout = int(spec.get("default_timeout_s", DEFAULT_TIMEOUT_S))
    if backend == "docker":
        image = spec.get("image")
        if not image:
            raise SsrError("the docker backend needs an 'image'")
        return DockerEnvironment(
            image,
            repo_path=spec.get("repo_path", "/testbed"),
            container_name=spec.get("container_name"),
            network=spec.get("network", "none"),
            default_timeout_s=timeout,
        )
    if backend == "wsl":
        return WslEnvironment(
            spec["repo_path"], distro=spec.get("distro"), default_timeout_s=timeout
        )
    if backend == "local":
        return LocalEnvironment(spec["repo_path"], default_timeout_s=timeout)
    raise SsrError(f"unknown execution backend {backend!r}")
