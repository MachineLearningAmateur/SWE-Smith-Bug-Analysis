#!/usr/bin/env python3
"""Report whether this machine can run the pipeline, and what is missing.

Every check prints one line: OK, WARN or MISSING, the fact found, and, when
something is missing, the exact next step. Exit code 0 means a corpus run can
start; 1 means at least one required capability is absent.

    python scripts/check_environment.py
    python scripts/check_environment.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.config import load_config  # noqa: E402
from ssr.paths import REPO_ROOT  # noqa: E402
from ssr.taxonomy import verify_provenance  # noqa: E402
from ssr.util import SsrError, load_dotenv  # noqa: E402

OK, WARN, MISSING = "OK", "WARN", "MISSING"


def _run(argv: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        completed = subprocess.run(argv, capture_output=True, timeout=timeout, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 127, ""
    text = (completed.stdout or b"").decode("utf-8", "replace").strip()
    if not text:
        text = (completed.stderr or b"").decode("utf-8", "replace").strip()
    return completed.returncode, text


class Report:
    def __init__(self) -> None:
        self.rows: list[dict[str, str]] = []

    def add(self, name: str, status: str, detail: str, remedy: str = "", required: bool = True) -> None:
        self.rows.append(
            {
                "check": name,
                "status": status,
                "detail": detail,
                "remedy": remedy,
                "required": "yes" if required else "no",
            }
        )

    @property
    def blocking(self) -> list[dict[str, str]]:
        return [row for row in self.rows if row["status"] == MISSING and row["required"] == "yes"]

    def render(self) -> str:
        width = max(len(row["check"]) for row in self.rows)
        lines = []
        for row in self.rows:
            lines.append(f"{row['status']:<8} {row['check']:<{width}}  {row['detail']}")
            if row["remedy"] and row["status"] != OK:
                lines.append(f"{'':<8} {'':<{width}}  -> {row['remedy']}")
        return "\n".join(lines)


def check_python(report: Report) -> None:
    version = sys.version_info
    if version >= (3, 10):
        report.add("python (harness)", OK, f"{platform.python_version()} at {sys.executable}")
    else:
        report.add(
            "python (harness)",
            MISSING,
            f"{platform.python_version()}; 3.10 or later is required",
            "install Python 3.10+ and re-create the virtual environment",
        )

    for module in ("yaml", "jsonschema", "requests"):
        try:
            __import__(module)
            report.add(f"package {module}", OK, "importable")
        except ImportError:
            report.add(
                f"package {module}",
                MISSING,
                "not importable",
                "python -m pip install -e .",
            )


def check_docker(report: Report) -> None:
    if not shutil.which("docker"):
        report.add(
            "docker",
            MISSING,
            "the docker CLI is not on PATH",
            "install Docker; see docs/swesmith_setup.md. Without it, SWE-smith "
            "environments cannot run and only the local or wsl backend is available.",
        )
        return
    code, version = _run(["docker", "--version"])
    if code != 0:
        report.add("docker", MISSING, "docker --version failed", "check the installation")
        return
    report.add("docker", OK, version)
    code, info = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=120)
    if code != 0:
        report.add(
            "docker daemon",
            MISSING,
            "the daemon is not reachable",
            "start the Docker service, then run this check again",
        )
    else:
        report.add("docker daemon", OK, f"server {info}")


def check_wsl(report: Report) -> None:
    if platform.system() != "Windows":
        report.add("wsl", OK, "not applicable on this platform", required=False)
        return
    if not shutil.which("wsl") and not shutil.which("wsl.exe"):
        report.add("wsl", WARN, "wsl.exe is not on PATH", required=False)
        return
    distro = os.environ.get("SSR_WSL_DISTRO", "Ubuntu")
    code, text = _run(["wsl", "-d", distro, "-e", "bash", "-lc", "cat /etc/os-release | head -2"], 180)
    if code != 0:
        report.add("wsl", WARN, f"distribution {distro!r} did not respond", required=False)
        return
    flat = " ".join(text.split())
    report.add("wsl", OK, f"{distro}: {flat}", required=False)
    code, py = _run(["wsl", "-d", distro, "-e", "bash", "-lc", "python3 --version"], 120)
    status = OK
    remedy = ""
    if code != 0:
        status, py, remedy = WARN, "python3 not found", "install python3 in the distribution"
    elif _version_tuple(py) < (3, 10):
        status = WARN
        remedy = "SWE-smith needs Python 3.10+; this distribution is older"
    report.add("wsl python", status, py, remedy, required=False)


def _version_tuple(text: str) -> tuple[int, ...]:
    """Numeric version out of a `--version` line. ("Python 3.8.10" -> (3, 8, 10))"""
    for token in text.split():
        parts = token.split(".")
        if len(parts) >= 2 and all(part.isdigit() for part in parts):
            return tuple(int(part) for part in parts)
    return (0,)


def check_swesmith(report: Report) -> None:
    try:
        import swesmith  # type: ignore

        version = getattr(swesmith, "__version__", "unknown")
        report.add("swesmith package", OK, f"version {version}", required=False)
    except ImportError:
        report.add(
            "swesmith package",
            WARN,
            "not importable in this interpreter",
            "SWE-smith is used as the environment substrate. Install it inside the "
            "Linux environment, not on the Windows host; see docs/swesmith_setup.md.",
            required=False,
        )


def check_api_key(report: Report) -> None:
    load_dotenv()
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if not key:
        report.add(
            "OPENROUTER_API_KEY",
            MISSING,
            "not set",
            "copy .env.example to .env and fill in the key, or export the variable. "
            "Generation and solving cannot run without it.",
        )
    elif len(key) < 20:
        report.add("OPENROUTER_API_KEY", WARN, "set but suspiciously short")
    else:
        report.add("OPENROUTER_API_KEY", OK, f"set ({len(key)} characters, value not shown)")


def check_model_reachable(report: Report) -> None:
    """One tiny completion against the configured model.

    Worth its cost: a model can be listed by OpenRouter and still be
    unreachable for this account, because the only provider serving it is
    excluded by the account's allowed-providers setting. That failure appears
    only on a real call.
    """
    load_dotenv()
    if not os.environ.get("OPENROUTER_API_KEY"):
        report.add("model reachable", MISSING, "skipped: no API key", "set OPENROUTER_API_KEY")
        return
    try:
        from ssr.model import OpenRouterModel

        name = load_config("generator").require("model.name")
        model = OpenRouterModel(name, max_tokens=16, temperature=0.0, retries=1, timeout_s=90)
        reply = model.complete([{"role": "user", "content": "Reply with exactly: OK"}])
        report.add("model reachable", OK, f"{name} answered ({reply.usage.completion_tokens} tokens)")
    except SsrError as exc:
        message = str(exc)
        remedy = "check configs/generator.yaml and the OpenRouter account"
        if "allowed-providers" in message or "No allowed providers" in message:
            remedy = (
                "the account's privacy setting excludes every provider serving this model. "
                "Permit the provider at https://openrouter.ai/settings/privacy, or change "
                "model.name in configs/generator.yaml and configs/solver.yaml and record "
                "the substitution in docs/fidelity_limitations.md."
            )
        report.add("model reachable", MISSING, message.split("\n")[0][:300], remedy)
    except Exception as exc:  # pragma: no cover - network layer
        report.add("model reachable", MISSING, f"{type(exc).__name__}: {exc}", "check network access")


def check_configs(report: Report) -> None:
    for name in ("generator", "solver", "validation", "sampling"):
        try:
            config = load_config(name)
            report.add(f"config {name}.yaml", OK, f"sha256 {config.sha256[:16]}")
        except SsrError as exc:
            report.add(f"config {name}.yaml", MISSING, str(exc), "restore the config file")


def check_taxonomy(report: Report) -> None:
    try:
        record = verify_provenance()
        report.add(
            "frozen taxonomy",
            OK,
            f"{record['taxonomy_version']} from {record['source_commit'][:12]}, "
            f"mapping {record['mapping_sha256'][:16]}",
        )
    except SsrError as exc:
        report.add("frozen taxonomy", MISSING, str(exc).splitlines()[0], "restore taxonomy/ from the AIDev repository")


def check_git(report: Report) -> None:
    code, version = _run(["git", "--version"])
    if code != 0:
        report.add("git", MISSING, "not on PATH", "install git")
    else:
        report.add("git", OK, version)


def check_workspace(report: Report) -> None:
    from ssr.paths import workspace_root

    root = workspace_root()
    try:
        root.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(root)
        free_gb = usage.free / (1 << 30)
        status = OK if free_gb >= 50 else WARN
        report.add(
            "workspace",
            status,
            f"{root} ({free_gb:.0f} GB free)",
            "SWE-smith images and worktrees need tens of GB; free space or set "
            "SSR_WORKSPACE_ROOT to a larger volume" if status == WARN else "",
            required=False,
        )
    except OSError as exc:
        report.add("workspace", WARN, f"{root}: {exc}", required=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    parser.add_argument(
        "--probe-model",
        action="store_true",
        help="make one small paid completion to prove the configured model is reachable",
    )
    args = parser.parse_args()

    report = Report()
    check_python(report)
    check_git(report)
    check_configs(report)
    check_taxonomy(report)
    check_api_key(report)
    if args.probe_model:
        check_model_reachable(report)
    check_docker(report)
    check_wsl(report)
    check_swesmith(report)
    check_workspace(report)

    if args.json:
        print(json.dumps({"repo_root": str(REPO_ROOT), "checks": report.rows}, indent=2))
    else:
        print(report.render())
        print()
        if report.blocking:
            print(f"{len(report.blocking)} required capability/capabilities missing:")
            for row in report.blocking:
                print(f"  - {row['check']}: {row['detail']}")
            print("\nA corpus run cannot start until these are resolved.")
        else:
            print("All required capabilities are present.")
    return 1 if report.blocking else 0


if __name__ == "__main__":
    raise SystemExit(main())
