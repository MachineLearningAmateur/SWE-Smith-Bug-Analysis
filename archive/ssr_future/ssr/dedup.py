"""Deterministic duplicate detection (handoff section 12).

Runs before sampling and never reads a taxonomy label. Every signal is a
property of the diff, the tree or the lineage.

Signals, in the order they are applied. The first one that fires owns the
exclusion, so a report reads as one reason per excluded bug:

    EXACT_DIFF          byte-identical bug_inject.diff
    NORMALISED_DIFF     identical after index lines, hunk line numbers,
                        trailing whitespace and blank-line noise are removed
    IDENTICAL_TREE      identical buggy tree hash on the same source commit
    DUPLICATE_SECOND_ORDER  same parent bug and same normalised repair patch
    SAME_HUNK           same repository, same changed files, same hunk
                        anchors: two attempts that hit one code region
    SAME_REVERTED_COMMIT    two history reversions that undo the same commit

The survivor of a duplicate group is the lowest bug_id in lexicographic
order, so the outcome does not depend on directory listing order or on the
order candidates were generated.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable

from ssr.util import sha256_text

_INDEX_LINE = re.compile(r"^index [0-9a-f]+\.\.[0-9a-f]+( \d+)?$", re.MULTILINE)
_HUNK_HEADER = re.compile(r"^@@ -\d+(,\d+)? \+\d+(,\d+)? @@(.*)$", re.MULTILINE)
_FILE_HEADER = re.compile(r"^(\+\+\+|---) [ab]/(.+)$", re.MULTILINE)
_TRAILING_WS = re.compile(r"[ \t]+$", re.MULTILINE)

SIGNAL_ORDER = (
    "EXACT_DIFF",
    "NORMALISED_DIFF",
    "IDENTICAL_TREE",
    "DUPLICATE_SECOND_ORDER",
    "SAME_HUNK",
    "SAME_REVERTED_COMMIT",
)


@dataclass
class BugRecord:
    """The neutral facts deduplication is allowed to use."""

    bug_id: str
    diff_text: str
    source_repo: str
    source_commit: str
    bug_order: int
    parent_bug_id: str | None = None
    buggy_tree_hash: str | None = None
    reverted_commits: list[str] = field(default_factory=list)
    repair_patch: str | None = None

    @property
    def exact_key(self) -> str:
        return sha256_text(self.diff_text)

    @property
    def normalised_key(self) -> str:
        return sha256_text(normalise_diff(self.diff_text))

    @property
    def tree_key(self) -> str | None:
        if not self.buggy_tree_hash:
            return None
        return f"{self.source_repo}@{self.source_commit}:{self.buggy_tree_hash}"

    @property
    def second_order_key(self) -> str | None:
        if self.bug_order != 2 or not self.parent_bug_id:
            return None
        repair = normalise_diff(self.repair_patch or "")
        return f"{self.parent_bug_id}:{sha256_text(repair)}"

    @property
    def hunk_key(self) -> str:
        return f"{self.source_repo}@{self.source_commit}:{sha256_text(hunk_signature(self.diff_text))}"

    @property
    def reverted_key(self) -> str | None:
        if not self.reverted_commits:
            return None
        return f"{self.source_repo}:{','.join(sorted(set(self.reverted_commits)))}"


def normalise_diff(diff_text: str) -> str:
    """Strip everything that can differ between two identical changes."""
    text = diff_text.replace("\r\n", "\n")
    text = _INDEX_LINE.sub("index <normalised>", text)
    text = _HUNK_HEADER.sub("@@ <normalised> @@", text)
    text = _TRAILING_WS.sub("", text)
    lines = [line for line in text.split("\n") if line.strip() not in ("", "\\ No newline at end of file")]
    return "\n".join(lines)


def changed_files(diff_text: str) -> list[str]:
    found = {match.group(2) for match in _FILE_HEADER.finditer(diff_text) if match.group(2) != "dev/null"}
    return sorted(found)


def hunk_signature(diff_text: str) -> str:
    """Files touched plus the context line of each hunk header.

    Two attempts that edit the same function produce the same signature even
    when the edits differ in detail, which is exactly the "obvious
    near-duplicate from the same code hunk" case.
    """
    parts: list[str] = []
    current_file = ""
    for line in diff_text.replace("\r\n", "\n").split("\n"):
        header = _FILE_HEADER.match(line)
        if header and line.startswith("+++"):
            current_file = header.group(2)
            continue
        hunk = _HUNK_HEADER.match(line)
        if hunk:
            parts.append(f"{current_file}::{hunk.group(3).strip()}")
    return "\n".join(sorted(parts))


@dataclass
class DedupResult:
    kept: list[str]
    excluded: dict[str, dict[str, Any]]
    groups: dict[str, list[list[str]]]

    def summary(self) -> dict[str, Any]:
        by_signal: dict[str, int] = defaultdict(int)
        for record in self.excluded.values():
            by_signal[record["signal"]] += 1
        return {
            "input": len(self.kept) + len(self.excluded),
            "kept": len(self.kept),
            "excluded": len(self.excluded),
            "excluded_by_signal": dict(sorted(by_signal.items())),
        }


def deduplicate(records: Iterable[BugRecord]) -> DedupResult:
    ordered = sorted(records, key=lambda record: record.bug_id)
    excluded: dict[str, dict[str, Any]] = {}
    groups: dict[str, list[list[str]]] = {signal: [] for signal in SIGNAL_ORDER}

    key_functions = {
        "EXACT_DIFF": lambda record: record.exact_key,
        "NORMALISED_DIFF": lambda record: record.normalised_key,
        "IDENTICAL_TREE": lambda record: record.tree_key,
        "DUPLICATE_SECOND_ORDER": lambda record: record.second_order_key,
        "SAME_HUNK": lambda record: record.hunk_key,
        "SAME_REVERTED_COMMIT": lambda record: record.reverted_key,
    }

    for signal in SIGNAL_ORDER:
        buckets: dict[str, list[BugRecord]] = defaultdict(list)
        for record in ordered:
            if record.bug_id in excluded:
                continue
            key = key_functions[signal](record)
            if key is None:
                continue
            buckets[key].append(record)
        for key, bucket in sorted(buckets.items()):
            if len(bucket) < 2:
                continue
            survivor = bucket[0]
            groups[signal].append([member.bug_id for member in bucket])
            for member in bucket[1:]:
                excluded[member.bug_id] = {
                    "signal": signal,
                    "duplicate_of": survivor.bug_id,
                    "key": key,
                }

    kept = [record.bug_id for record in ordered if record.bug_id not in excluded]
    return DedupResult(kept=kept, excluded=excluded, groups={k: v for k, v in groups.items() if v})
