"""Neutral review packets and the leakage scan (handoff section 17).

A packet holds only what a reviewer needs to judge the final buggy state:

    packet.json          the manifest, with neutral evidence IDs
    bug_diff.diff        the single clean-to-buggy diff
    context/*.py|txt     buggy-state source around the change
    oracle/*.txt         the real output of each failing oracle test
    test_results.txt     the clean-versus-buggy summary

It holds none of: the generation strategy, the bug order, the parent bug,
the generator or solver identity, the source allocation, the trajectory, the
weakening diff, or the internal bug ID.

Two scans run before a packet is written, and both are fatal:

* the METADATA scan reads every string in ``packet.json`` and every file name.
  Strings the harness wrote are checked against the full term list. Strings
  copied out of the repository — a test node ID, the discovered test command,
  a source path — are checked against the harness terms only, because a
  project may legitimately own a ``test_removal.py`` or a ``solver`` module
  and rejecting that packet would be a false positive.
* the BODY scan reads the evidence files. Real source code legitimately
  contains words such as "remove" or "revert", so this scan looks only for
  phrases that cannot occur naturally: harness names, model names and
  injection vocabulary. A hit means the injector wrote a comment about what
  it was doing, and the candidate must be regenerated rather than shipped.

What the scans cannot remove is discussed in ``docs/review_protocol.md``: a
diff still has a shape, and a reviewer may form a private guess about how a
state arose. The design goal is that no packet field, file name or identifier
tells them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from ssr.util import SsrError, sha256_text, write_json, write_text

REVIEWER_QUESTION = (
    "What kind of technical failure does this validated buggy repository state represent?"
)

# Two term lists, because two different things can go wrong.
#
# HARNESS_FORBIDDEN names this study's own machinery. None of it can occur in
# a repository by accident, so it is fatal wherever it appears, including in
# strings copied out of the repository.
HARNESS_FORBIDDEN = (
    "swesmith",
    "swe-smith",
    "qwen",
    "openrouter",
    "cwm-sft",
    "ssr_style",
    "injector",
    "bug_inject",
    "test_weaken",
    "trajectory.jsonl",
    "pred_patch",
)

# STRATEGY_FORBIDDEN names the generation vocabulary. These are ordinary
# English words that a repository may legitimately use — a project can have a
# `test_removal.py`, a `reversion` module or a constraint `solver` — so they
# are fatal only in strings the harness itself wrote. Scanning them inside
# repository-derived values would reject sound packets.
STRATEGY_FORBIDDEN = (
    "removal",
    "history_reversion",
    "history reversion",
    "reversion",
    "failed_solver",
    "second_order",
    "second-order",
    "first_order",
    "first-order",
    "bug_order",
    "parent_bug",
    "parent bug",
    "generation_strategy",
    "solver",
    "weaken",
    "mutation",
)

METADATA_FORBIDDEN = HARNESS_FORBIDDEN + STRATEGY_FORBIDDEN

# Packet fields whose value is copied out of the repository: a test node ID, a
# test command the agent discovered, a source path. These are scanned for
# harness terms only.
REPOSITORY_DERIVED_KEYS = frozenset(
    {"test_command", "test_name", "test_file", "newly_failing", "repo_path"}
)

# Phrases that cannot occur naturally in repository source code.
BODY_FORBIDDEN = (
    "bug injection",
    "inject a bug",
    "injected bug",
    "injecting a bug",
    "ssr harness",
    "ssr_style_qwen",
    "openrouter",
    "qwen2.5-coder",
    "qwen-2.5-coder",
    "history_reversion",
    "failed_solver",
    "test_weaken",
    "bug_inject",
    "second-order bug",
    "reward hack",
)

_WORD = re.compile(r"[a-z0-9_.\- ]+")


@dataclass
class LeakageFinding:
    where: str
    term: str
    excerpt: str

    def __str__(self) -> str:
        return f"{self.where}: forbidden term {self.term!r} near {self.excerpt!r}"


def scan_metadata(payload: Any, *, path: str = "packet.json") -> list[LeakageFinding]:
    findings: list[LeakageFinding] = []

    def walk(node: Any, trail: str, repository_derived: bool) -> None:
        terms = HARNESS_FORBIDDEN if repository_derived else METADATA_FORBIDDEN
        if isinstance(node, dict):
            for key, value in node.items():
                findings.extend(_scan_string(str(key), f"{trail}.{key} (key)", METADATA_FORBIDDEN))
                walk(value, f"{trail}.{key}", str(key) in REPOSITORY_DERIVED_KEYS)
        elif isinstance(node, (list, tuple)):
            for index, value in enumerate(node):
                walk(value, f"{trail}[{index}]", repository_derived)
        elif isinstance(node, str):
            findings.extend(_scan_string(node, trail, terms))

    walk(payload, path, False)
    return findings


def scan_body(text: str, *, where: str) -> list[LeakageFinding]:
    return _scan_string(text, where, BODY_FORBIDDEN)


def scan_filenames(names: Iterable[str]) -> list[LeakageFinding]:
    """Scan packet file names.

    Names under ``context/`` end in a repository file name, so they get the
    harness terms only, for the same reason as REPOSITORY_DERIVED_KEYS.
    """
    findings: list[LeakageFinding] = []
    for name in names:
        terms = HARNESS_FORBIDDEN if name.startswith("context/") else METADATA_FORBIDDEN
        findings.extend(_scan_string(name, f"filename {name}", terms))
    return findings


def _scan_string(text: str, where: str, terms: tuple[str, ...]) -> list[LeakageFinding]:
    lowered = text.lower()
    findings: list[LeakageFinding] = []
    for term in terms:
        position = lowered.find(term)
        if position >= 0:
            start = max(0, position - 30)
            findings.append(
                LeakageFinding(where=where, term=term, excerpt=text[start : position + len(term) + 30])
            )
    return findings


# ----------------------------------------------------------------------
@dataclass
class PacketSource:
    """Everything the builder needs, already separated from hidden metadata."""

    packet_id: str
    repo_name: str
    language: str
    repo_commit: str | None
    repo_size_bin: str
    bug_diff: str
    test_command: str
    clean_counts: dict[str, int]
    bug_counts: dict[str, int]
    fail_to_pass: list[str]
    oracle_outputs: dict[str, str]
    code_context: dict[str, str]
    repo_description: str | None = None


class PacketBuilder:
    def __init__(self, root: Path, *, max_context_bytes: int = 120_000, max_oracle_bytes: int = 40_000):
        self.root = Path(root)
        self.max_context_bytes = max_context_bytes
        self.max_oracle_bytes = max_oracle_bytes

    def build(self, source: PacketSource) -> dict[str, Any]:
        directory = self.root / source.packet_id
        directory.mkdir(parents=True, exist_ok=True)

        written: dict[str, str] = {}
        findings: list[LeakageFinding] = []

        diff_name = "bug_diff.diff"
        diff_sha = write_text(directory / diff_name, source.bug_diff)
        written[diff_name] = diff_sha
        findings.extend(scan_body(source.bug_diff, where=diff_name))

        context_entries: list[dict[str, Any]] = []
        for index, (repo_path, content) in enumerate(sorted(source.code_context.items()), start=1):
            if index > 99:
                break
            body = content[: self.max_context_bytes]
            truncated = len(content) > len(body)
            name = f"context/{index:02d}_{_safe_name(repo_path)}"
            sha = write_text(directory / name, body)
            written[name] = sha
            findings.extend(scan_body(body, where=name))
            context_entries.append(
                {
                    "evidence_id": f"CODE_CONTEXT_{index:02d}",
                    "path": name,
                    "repo_path": repo_path,
                    "sha256": sha,
                    "truncated": truncated,
                    "line_range": None,
                }
            )

        oracle_entries: list[dict[str, Any]] = []
        for index, test_name in enumerate(sorted(source.fail_to_pass), start=1):
            if index > 99:
                break
            output = source.oracle_outputs.get(test_name, "")
            body = output[: self.max_oracle_bytes]
            truncated = len(output) > len(body)
            name = f"oracle/{index:02d}.txt"
            sha = write_text(directory / name, body or f"{test_name}: FAILED (no captured output)\n")
            written[name] = sha
            findings.extend(scan_body(body, where=name))
            oracle_entries.append(
                {
                    "evidence_id": f"ORACLE_TEST_{index:02d}",
                    "test_name": test_name,
                    "test_file": _test_file_of(test_name),
                    "output_path": name,
                    "sha256": sha,
                    "truncated": truncated,
                }
            )

        if not oracle_entries:
            raise SsrError(f"{source.packet_id}: a packet needs at least one oracle test")

        summary = _render_test_summary(source)
        summary_sha = write_text(directory / "test_results.txt", summary)
        written["test_results.txt"] = summary_sha

        evidence_ids = (
            ["BUG_DIFF", "TEST_RESULTS"]
            + [entry["evidence_id"] for entry in context_entries]
            + [entry["evidence_id"] for entry in oracle_entries]
        )

        added, deleted, files_changed = _diff_stats(source.bug_diff)
        packet = {
            "packet_id": source.packet_id,
            "packet_version": 1,
            "repository": {
                "name": source.repo_name,
                "language": source.language,
                "commit": source.repo_commit,
                "repo_size_bin": source.repo_size_bin,
                "description": source.repo_description,
            },
            "bug_diff": {
                "evidence_id": "BUG_DIFF",
                "path": diff_name,
                "sha256": diff_sha,
                "files_changed": files_changed,
                "lines_added": added,
                "lines_deleted": deleted,
            },
            "code_context": context_entries,
            "oracle_tests": oracle_entries,
            "test_results": {
                "evidence_id": "TEST_RESULTS",
                "test_command": source.test_command,
                "working_state": source.clean_counts,
                "buggy_state": source.bug_counts,
                "newly_failing": sorted(source.fail_to_pass),
            },
            "evidence_ids": sorted(set(evidence_ids)),
            "reviewer_question": REVIEWER_QUESTION,
        }

        findings.extend(scan_metadata(packet))
        findings.extend(scan_filenames(list(written) + [source.packet_id]))
        if findings:
            raise SsrError(
                f"{source.packet_id}: leakage scan failed, packet not published:\n  "
                + "\n  ".join(str(finding) for finding in findings[:20])
            )

        written["packet.json"] = write_json(directory / "packet.json", packet)
        return {"packet": packet, "files": written, "directory": str(directory)}


def _safe_name(repo_path: str) -> str:
    name = PurePosixPath(repo_path).name or "file"
    cleaned = re.sub(r"[^A-Za-z0-9_.\-]", "_", name)
    return cleaned[:80] or "file"


def _test_file_of(test_name: str) -> str | None:
    if "::" in test_name:
        return test_name.split("::", 1)[0]
    return None


def _diff_stats(diff_text: str) -> tuple[int, int, int]:
    added = deleted = 0
    files: set[str] = set()
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        if line.startswith("diff --git "):
            parts = line.split(" b/")
            if len(parts) > 1:
                files.add(parts[-1])
        elif line.startswith("+++") or line.startswith("---"):
            continue
        elif line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            deleted += 1
    return added, deleted, len(files)


def _render_test_summary(source: PacketSource) -> str:
    lines = [
        "Test command:",
        f"  {source.test_command}",
        "",
        "Working state (before the change):",
        f"  passed {source.clean_counts.get('passed', 0)}"
        f"  failed {source.clean_counts.get('failed', 0)}"
        f"  errored {source.clean_counts.get('errored', 0)}"
        f"  skipped {source.clean_counts.get('skipped', 0)}",
        "",
        "Buggy state (after the change):",
        f"  passed {source.bug_counts.get('passed', 0)}"
        f"  failed {source.bug_counts.get('failed', 0)}"
        f"  errored {source.bug_counts.get('errored', 0)}"
        f"  skipped {source.bug_counts.get('skipped', 0)}",
        "",
        "Tests that pass in the working state and fail in the buggy state:",
    ]
    lines += [f"  {name}" for name in sorted(source.fail_to_pass)]
    return "\n".join(lines) + "\n"


def packet_file_hashes(directory: Path) -> dict[str, str]:
    """Every file in a packet directory, keyed by its packet-relative path."""
    from ssr.util import sha256_file

    directory = Path(directory)
    hashes: dict[str, str] = {}
    for path in sorted(directory.rglob("*")):
        if path.is_file():
            hashes[path.relative_to(directory).as_posix()] = sha256_file(path)
    return hashes


def packet_digest(directory: Path) -> str:
    """One hash covering every file in the packet."""
    hashes = packet_file_hashes(directory)
    material = "\n".join(f"{name}:{digest}" for name, digest in sorted(hashes.items()))
    return sha256_text(material)
