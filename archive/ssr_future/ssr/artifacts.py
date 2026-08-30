"""The per-bug artifact bundle (handoff section 6).

Every first-order candidate produces this directory:

    bug_inject.diff     clean -> buggy source change
    test_script.sh      the command that runs the relevant tests
    test_files.txt      the test files the script covers, one per line
    test_parser.py      turns the script's raw output into a result table
    test_weaken.diff    a test-side change that hides part of the failure
    metadata.json       hidden generation metadata (schema-checked)
    trajectory.jsonl    the full action/observation record
    validation.json     the execution-validation result

A second-order candidate carries the same file names. ``bug_inject.diff``
then holds the combined clean-to-buggy diff (first-order injection plus the
failed repair), so a reviewer always reads a single diff against the clean
upstream repository and cannot tell the order from the artifact shape.

The parser contract, checked by ``PARSER_HANDLES_REAL_OUTPUT``:

    python3 test_parser.py < raw_output.txt

prints one JSON object to stdout::

    {"tests": {"<test id>": "PASSED"|"FAILED"|"ERROR"|"SKIPPED"},
     "collection_error": false}
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssr.util import SsrError, read_json, sha256_file, sha256_text, write_json, write_text

ARTIFACT_FILES = (
    "bug_inject.diff",
    "test_script.sh",
    "test_files.txt",
    "test_parser.py",
    "test_weaken.diff",
    "metadata.json",
    "trajectory.jsonl",
    "validation.json",
)

# Files a reviewer must never see. Enforced by ssr.packets.
HIDDEN_ARTIFACTS = ("metadata.json", "trajectory.jsonl", "pred_patch.diff")

DEFAULT_PARSER = '''\
"""Fallback pytest output parser.

Reads raw test output on stdin, prints one JSON object on stdout:
{"tests": {"<node id>": "PASSED"|"FAILED"|"ERROR"|"SKIPPED"}, "collection_error": bool}
"""
import json
import re
import sys

LINE = re.compile(r"^(?P<name>\\S+::\\S+)\\s+(?P<status>PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)")
SHORT = re.compile(r"^(?P<status>PASSED|FAILED|ERROR|SKIPPED)\\s+(?P<name>\\S+::\\S+)")
SUMMARY = re.compile(r"^(?P<status>FAILED|ERROR)\\s+(?P<name>[^\\s-]+)")

NORMALISE = {"XFAIL": "SKIPPED", "XPASS": "PASSED"}


def main() -> int:
    text = sys.stdin.read()
    tests = {}
    for line in text.splitlines():
        line = line.strip()
        for pattern in (LINE, SHORT, SUMMARY):
            match = pattern.match(line)
            if match:
                status = match.group("status")
                tests[match.group("name")] = NORMALISE.get(status, status)
                break
    collection_error = bool(re.search(r"^(ERROR|E)\\s+.*(collecting|ImportError)", text, re.M)) or (
        "errors during collection" in text
    )
    json.dump({"tests": tests, "collection_error": collection_error}, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


@dataclass
class BugArtifacts:
    """The on-disk bundle for one candidate."""

    bug_id: str
    directory: Path

    @property
    def bug_inject(self) -> Path:
        return self.directory / "bug_inject.diff"

    @property
    def test_script(self) -> Path:
        return self.directory / "test_script.sh"

    @property
    def test_files(self) -> Path:
        return self.directory / "test_files.txt"

    @property
    def test_parser(self) -> Path:
        return self.directory / "test_parser.py"

    @property
    def test_weaken(self) -> Path:
        return self.directory / "test_weaken.diff"

    @property
    def metadata_path(self) -> Path:
        return self.directory / "metadata.json"

    @property
    def trajectory(self) -> Path:
        return self.directory / "trajectory.jsonl"

    @property
    def validation_path(self) -> Path:
        return self.directory / "validation.json"

    @property
    def pred_patch(self) -> Path:
        return self.directory / "pred_patch.diff"

    # ------------------------------------------------------------------
    def ensure(self) -> "BugArtifacts":
        self.directory.mkdir(parents=True, exist_ok=True)
        return self

    def write_generation_artifacts(
        self,
        *,
        bug_diff: str,
        test_script: str,
        test_files: list[str],
        test_parser: str,
        weaken_diff: str,
    ) -> None:
        self.ensure()
        write_text(self.bug_inject, bug_diff)
        write_text(self.test_script, _normalise_script(test_script))
        write_text(self.test_files, "\n".join(test_files) + "\n" if test_files else "")
        write_text(self.test_parser, test_parser or DEFAULT_PARSER)
        write_text(self.test_weaken, weaken_diff)

    def read_test_files(self) -> list[str]:
        if not self.test_files.is_file():
            return []
        return [
            line.strip()
            for line in self.test_files.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def metadata(self) -> dict[str, Any]:
        if not self.metadata_path.is_file():
            raise SsrError(f"{self.bug_id}: metadata.json is missing")
        return read_json(self.metadata_path)

    def validation(self) -> dict[str, Any]:
        if not self.validation_path.is_file():
            raise SsrError(f"{self.bug_id}: validation.json is missing")
        return read_json(self.validation_path)

    def write_metadata(self, metadata: dict[str, Any]) -> str:
        metadata = dict(metadata)
        metadata["artifacts"] = self.artifact_hashes(exclude={"metadata.json"})
        return write_json(self.metadata_path, metadata)

    def write_validation(self, result: dict[str, Any]) -> str:
        return write_json(self.validation_path, result)

    def artifact_hashes(self, *, exclude: set[str] | None = None) -> dict[str, str]:
        exclude = exclude or set()
        hashes: dict[str, str] = {}
        for name in ARTIFACT_FILES + ("pred_patch.diff",):
            if name in exclude:
                continue
            path = self.directory / name
            if path.is_file():
                hashes[name] = sha256_file(path)
        return hashes

    def missing_required(self) -> list[str]:
        required = (
            "bug_inject.diff",
            "test_script.sh",
            "test_files.txt",
            "test_parser.py",
            "test_weaken.diff",
        )
        return [name for name in required if not (self.directory / name).is_file()]

    def diff_text(self) -> str:
        return self.bug_inject.read_text(encoding="utf-8") if self.bug_inject.is_file() else ""

    def diff_sha256(self) -> str:
        return sha256_text(self.diff_text())


def _normalise_script(script: str) -> str:
    """Give the test script a shebang and fail-fast flags if it has none."""
    text = script.strip("\n")
    if not text:
        raise SsrError("the test script is empty")
    if not text.startswith("#!"):
        text = "#!/usr/bin/env bash\nset -uo pipefail\n" + text
    return text + "\n"


def load_bug(directory: Path) -> BugArtifacts:
    directory = Path(directory)
    return BugArtifacts(bug_id=directory.name, directory=directory)


def iter_pool(root: Path) -> list[BugArtifacts]:
    """Every bug directory under a pool root, in stable bug_id order."""
    if not Path(root).is_dir():
        return []
    return [
        load_bug(child)
        for child in sorted(Path(root).iterdir(), key=lambda path: path.name)
        if child.is_dir() and child.name.startswith("BUG_")
    ]
