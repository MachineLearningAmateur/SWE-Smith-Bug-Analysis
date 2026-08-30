"""Objective, non-LLM patch metrics (handoff section 25).

These are a second line of evidence beside the taxonomy labels. Nothing here
looks at a reviewer label, and nothing here looks at the generation strategy,
so the metrics can be joined to either without circularity.

Every metric is computed from the unified diff alone, except
``historical_reversion_similarity``, which needs the repository history and
is therefore optional.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import asdict, dataclass, field
from pathlib import PurePosixPath
from typing import Any, Iterable

_FILE_HEADER = re.compile(r"^diff --git a/(?P<a>.+?) b/(?P<b>.+)$")
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_IMPORT = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+)|#include\s*[<\"]([^>\"]+))")

TEST_PATH = re.compile(r"(^|/)(tests?|testing|spec|__tests__)(/|$)|(^|/)test_[^/]*$|_test\.[a-z]+$", re.I)
CONFIG_NAMES = {
    "setup.py", "setup.cfg", "pyproject.toml", "requirements.txt", "pipfile", "poetry.lock",
    "package.json", "package-lock.json", "yarn.lock", "go.mod", "go.sum", "cargo.toml",
    "cargo.lock", "pom.xml", "build.gradle", "makefile", "dockerfile", "tox.ini", ".gitignore",
}
CONFIG_SUFFIXES = {".cfg", ".ini", ".toml", ".yaml", ".yml", ".properties"}

# Keywords are not identifiers for this purpose; counting them would swamp
# the signal with `self`, `return`, `if`.
STOPWORDS = {
    "self", "this", "return", "import", "from", "class", "def", "for", "while", "if", "else",
    "elif", "try", "except", "finally", "with", "as", "and", "or", "not", "in", "is", "None",
    "True", "False", "null", "true", "false", "var", "let", "const", "function", "public",
    "private", "static", "void", "int", "str", "bool", "float", "new", "the",
}


@dataclass
class PatchMetrics:
    bug_id: str
    files_changed: int = 0
    directories_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    add_delete_ratio: float | None = None
    net_lines: int = 0
    identifiers_introduced: int = 0
    identifiers_removed: int = 0
    call_references_introduced: int = 0
    call_references_removed: int = 0
    imports_introduced: int = 0
    imports_removed: int = 0
    config_or_dependency_edits: int = 0
    cross_file_edit: bool = False
    test_files_edited: int = 0
    source_files_edited: int = 0
    largest_file_share: float | None = None
    hunks: int = 0
    historical_reversion_similarity: float | None = None
    changed_paths: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_patch_metrics(bug_id: str, diff_text: str) -> PatchMetrics:
    metrics = PatchMetrics(bug_id=bug_id)
    per_file = _split_by_file(diff_text)
    metrics.files_changed = len(per_file)
    metrics.changed_paths = sorted(per_file)
    metrics.cross_file_edit = len(per_file) > 1
    metrics.directories_changed = len({str(PurePosixPath(path).parent) for path in per_file})

    added_tokens: list[str] = []
    removed_tokens: list[str] = []
    per_file_lines: dict[str, int] = {}

    for path, body in per_file.items():
        if TEST_PATH.search(path):
            metrics.test_files_edited += 1
        else:
            metrics.source_files_edited += 1
        if _is_config(path):
            metrics.config_or_dependency_edits += 1

        file_lines = 0
        for line in body.splitlines():
            if line.startswith("@@"):
                metrics.hunks += 1
                continue
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                metrics.lines_added += 1
                file_lines += 1
                added_tokens.append(line[1:])
            elif line.startswith("-"):
                metrics.lines_deleted += 1
                file_lines += 1
                removed_tokens.append(line[1:])
        per_file_lines[path] = file_lines

    total_lines = metrics.lines_added + metrics.lines_deleted
    metrics.net_lines = metrics.lines_added - metrics.lines_deleted
    metrics.add_delete_ratio = (
        round(metrics.lines_added / metrics.lines_deleted, 4) if metrics.lines_deleted else None
    )
    metrics.largest_file_share = (
        round(max(per_file_lines.values()) / total_lines, 4) if total_lines and per_file_lines else None
    )

    added_identifiers = _identifiers(added_tokens)
    removed_identifiers = _identifiers(removed_tokens)
    metrics.identifiers_introduced = len(added_identifiers - removed_identifiers)
    metrics.identifiers_removed = len(removed_identifiers - added_identifiers)

    added_calls = _calls(added_tokens)
    removed_calls = _calls(removed_tokens)
    metrics.call_references_introduced = len(added_calls - removed_calls)
    metrics.call_references_removed = len(removed_calls - added_calls)

    added_imports = _imports(added_tokens)
    removed_imports = _imports(removed_tokens)
    metrics.imports_introduced = len(added_imports - removed_imports)
    metrics.imports_removed = len(removed_imports - added_imports)

    return metrics


def split_by_file(diff_text: str) -> dict[str, str]:
    """Public name: the diff body of each changed file, keyed by path."""
    return _split_by_file(diff_text)


def _split_by_file(diff_text: str) -> dict[str, str]:
    files: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        header = _FILE_HEADER.match(line)
        if header:
            current = header.group("b")
            files.setdefault(current, [])
            continue
        if current is not None:
            files[current].append(line)
    return {path: "\n".join(lines) for path, lines in files.items()}


def _is_config(path: str) -> bool:
    name = PurePosixPath(path).name.lower()
    return name in CONFIG_NAMES or PurePosixPath(name).suffix in CONFIG_SUFFIXES


def _identifiers(lines: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for line in lines:
        for token in _IDENTIFIER.findall(line):
            if token not in STOPWORDS:
                found.add(token)
    return found


def _calls(lines: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for line in lines:
        for token in _CALL.findall(line):
            if token.split(".")[-1] not in STOPWORDS:
                found.add(token)
    return found


def _imports(lines: Iterable[str]) -> set[str]:
    found: set[str] = set()
    for line in lines:
        match = _IMPORT.match(line)
        if match:
            found.add(next(group for group in match.groups() if group))
    return found


def historical_reversion_similarity(bug_diff: str, historical_diffs: Iterable[str]) -> float | None:
    """How closely the bug diff matches the reverse of some historical commit.

    A HISTORY_REVERSION bug that undoes commit C should score near 1.0
    against C; a REMOVAL bug should score low against every commit. The value
    is the best match over the candidate history, so it is comparable across
    bugs without knowing which commit was involved.

    Returns None when no history was supplied.
    """
    best: float | None = None
    normalised_bug = _content_lines(bug_diff)
    if not normalised_bug:
        return None
    for historical in historical_diffs:
        reversed_hunks = _content_lines(_reverse_diff(historical))
        if not reversed_hunks:
            continue
        ratio = difflib.SequenceMatcher(None, normalised_bug, reversed_hunks).ratio()
        best = ratio if best is None else max(best, ratio)
    return round(best, 4) if best is not None else None


def _content_lines(diff_text: str) -> list[str]:
    """Added and removed payload lines, with the sign kept and noise dropped."""
    out: list[str] = []
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        if line.startswith(("+++", "---", "diff --git", "index ", "@@")):
            continue
        if line.startswith(("+", "-")) and line[1:].strip():
            out.append(line[0] + line[1:].strip())
    return out


def _reverse_diff(diff_text: str) -> str:
    flipped: list[str] = []
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        if line.startswith(("+++", "---", "diff --git", "index ", "@@")):
            flipped.append(line)
        elif line.startswith("+"):
            flipped.append("-" + line[1:])
        elif line.startswith("-"):
            flipped.append("+" + line[1:])
        else:
            flipped.append(line)
    return "\n".join(flipped)
