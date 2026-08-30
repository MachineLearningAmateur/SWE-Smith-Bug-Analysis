"""Hashing, deterministic serialisation, seeded randomness and logging."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class SsrError(RuntimeError):
    """Any harness failure that should stop the current script with a message."""


# --------------------------------------------------------------------------
# hashing
# --------------------------------------------------------------------------
def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_json(payload: Any) -> str:
    """Hash of the canonical JSON form. Stable across dict insertion order."""
    return sha256_text(canonical_json(payload))


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


# --------------------------------------------------------------------------
# file IO
# --------------------------------------------------------------------------
def read_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def force_rmtree(path: Path) -> None:
    """Remove a directory tree, including read-only files.

    Git marks its object files read-only, and on Windows that makes a plain
    ``shutil.rmtree`` fail with a permission error.
    """
    import shutil
    import stat

    def clear_readonly(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass

    path = Path(path)
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=lambda func, target, exc: clear_readonly(func, target, exc))
    else:  # pragma: no cover - older interpreters
        shutil.rmtree(path, onerror=clear_readonly)


def write_json(path: Path, payload: Any, *, sort_keys: bool = True) -> str:
    """Write pretty JSON with a trailing newline. Returns the file SHA-256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=sort_keys, ensure_ascii=False) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return sha256_text(text)


def read_jsonl(path: Path) -> list[Any]:
    records = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SsrError(f"{path}:{line_number}: invalid JSON line: {exc}") from exc
    return records


def append_jsonl(path: Path, payload: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_json(payload) + "\n")


def write_text(path: Path, text: str) -> str:
    """Write text with LF endings. Returns the file SHA-256.

    LF is forced so that a manifest hash computed on Windows matches the same
    file regenerated on Linux.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    normalised = text.replace("\r\n", "\n")
    path.write_text(normalised, encoding="utf-8", newline="\n")
    return sha256_text(normalised)


# --------------------------------------------------------------------------
# time
# --------------------------------------------------------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# determinism
# --------------------------------------------------------------------------
def seeded_rng(seed: int, *namespace: Any) -> random.Random:
    """A Random seeded by ``seed`` plus a stable namespace.

    Two calls with the same seed and namespace always give the same stream,
    on any platform and in any Python 3.10+ process. Namespaces let separate
    decisions (strategy draws, packet-id shuffles) use one declared seed
    without sharing a stream.
    """
    material = canonical_json([seed, [str(part) for part in namespace]])
    derived = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
    return random.Random(derived)


def stable_id(prefix: str, *material: Any) -> str:
    digest = hashlib.sha256(canonical_json(list(material)).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:12]}"


# --------------------------------------------------------------------------
# text helpers
# --------------------------------------------------------------------------
def truncate(text: str, limit: int, *, marker: str = "\n...[truncated]...\n") -> tuple[str, bool]:
    """Keep the head and the tail of an oversized observation.

    The tail matters: a test runner puts its summary last.
    """
    if len(text) <= limit:
        return text, False
    if limit <= len(marker):
        return text[:limit], True
    head = (limit - len(marker)) * 2 // 3
    tail = limit - len(marker) - head
    return text[:head] + marker + text[-tail:], True


_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------
SECRET_ENV_NAMES = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "GH_TOKEN",
    "HF_TOKEN",
    "AWS_SECRET_ACCESS_KEY",
)


def load_dotenv(path: Path | None = None) -> None:
    """Load KEY=VALUE lines from .env without overwriting the real environment."""
    from ssr.paths import REPO_ROOT

    path = path or REPO_ROOT / ".env"
    if not Path(path).is_file():
        return
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def sandbox_environment(extra: dict[str, str] | None = None) -> dict[str, str]:
    """The environment handed to a sandboxed command.

    Secrets are removed. An injector agent has shell access inside the
    sandbox, so the API key must not be reachable from there.
    """
    env = {
        key: value
        for key, value in os.environ.items()
        if key.upper() not in SECRET_ENV_NAMES and not key.upper().endswith("_API_KEY")
    }
    env.setdefault("PYTHONDONTWRITEBYTECODE", "1")
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    if extra:
        env.update(extra)
    return env


def redact(text: str) -> str:
    """Remove any known secret value from text before it is written to disk."""
    for name in SECRET_ENV_NAMES:
        value = os.environ.get(name)
        if value and len(value) > 8:
            text = text.replace(value, f"<{name}_REDACTED>")
    return text


# --------------------------------------------------------------------------
# logging
# --------------------------------------------------------------------------
def setup_logging(verbose: bool = False, log_file: Path | None = None) -> logging.Logger:
    logger = logging.getLogger("ssr")
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))
    logger.addHandler(stream)
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
        )
        logger.addHandler(file_handler)
    return logger


def get_logger() -> logging.Logger:
    return logging.getLogger("ssr")


# --------------------------------------------------------------------------
# small collection helpers
# --------------------------------------------------------------------------
def dedupe_preserving_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
