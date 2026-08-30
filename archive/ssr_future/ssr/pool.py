"""Reading the validated pool.

Two views of the same bugs, kept apart on purpose:

``PoolEntry``      the full record, including hidden generation metadata.
                   Used by deduplication, packet building and reporting.
``neutral_record`` the subset sampling is allowed to see. Building it here,
                   in one place, is what makes ``assert_no_taxonomy_fields``
                   a meaningful guarantee rather than a hope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ssr.artifacts import BugArtifacts, iter_pool
from ssr.dedup import BugRecord
from ssr.exec_env import size_bin
from ssr.sampling import Candidate, stratum_for
from ssr.util import SsrError, read_json


@dataclass
class PoolEntry:
    artifacts: BugArtifacts
    metadata: dict[str, Any]
    validation: dict[str, Any]

    @property
    def bug_id(self) -> str:
        return self.artifacts.bug_id

    @property
    def notes(self) -> dict[str, Any]:
        raw = self.metadata.get("notes")
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def strategy(self) -> str:
        return str(self.metadata["generation_strategy"])

    @property
    def bug_order(self) -> int:
        return int(self.metadata["bug_order"])

    @property
    def parent_bug_id(self) -> str | None:
        return self.metadata.get("parent_bug_id")

    @property
    def repo(self) -> str:
        return str(self.metadata["environment"]["source_repo"])

    @property
    def source_commit(self) -> str:
        return str(self.metadata["environment"]["source_commit"])

    @property
    def language(self) -> str:
        return str(self.metadata["environment"].get("language") or "unknown")

    @property
    def repo_size_bin(self) -> str:
        recorded = (self.metadata["environment"].get("repo_size") or {}).get("bin")
        if recorded:
            return str(recorded)
        lines = (self.metadata["environment"].get("repo_size") or {}).get("lines") or 0
        return size_bin(int(lines))

    @property
    def backend(self) -> str:
        return str(self.metadata["environment"].get("backend", "unknown"))

    @property
    def scripted(self) -> bool:
        return bool(self.notes.get("scripted_model")) or self.metadata["generator"].get(
            "provider"
        ) == "scripted"

    @property
    def base_state_key(self) -> str:
        """Two bugs share a base state when they start from the same checkout."""
        return f"{self.repo}@{self.source_commit}"

    def to_dedup_record(self) -> BugRecord:
        return BugRecord(
            bug_id=self.bug_id,
            diff_text=self.artifacts.diff_text(),
            source_repo=self.repo,
            source_commit=self.source_commit,
            bug_order=self.bug_order,
            parent_bug_id=self.parent_bug_id,
            buggy_tree_hash=self.notes.get("buggy_tree_hash"),
            reverted_commits=list(self.notes.get("reverted_commits") or []),
            repair_patch=(
                self.artifacts.pred_patch.read_text(encoding="utf-8")
                if self.artifacts.pred_patch.is_file()
                else None
            ),
        )

    def to_candidate(self) -> Candidate:
        return Candidate(
            bug_id=self.bug_id,
            stratum=stratum_for(self.strategy, self.bug_order),
            repo=self.repo,
            language=self.language,
            repo_size_bin=self.repo_size_bin,
            parent_bug_id=self.parent_bug_id,
            base_state_key=self.base_state_key,
        )

    def neutral_record(self) -> dict[str, Any]:
        """Exactly the fields sampling may read. No taxonomy, no review data."""
        return {
            "bug_id": self.bug_id,
            "stratum": stratum_for(self.strategy, self.bug_order),
            "repo": self.repo,
            "language": self.language,
            "repo_size_bin": self.repo_size_bin,
            "parent_bug_id": self.parent_bug_id,
            "base_state_key": self.base_state_key,
            "validated": bool(self.validation.get("validated")),
        }


def load_pool(root: Path, *, require_validated: bool = True) -> list[PoolEntry]:
    entries: list[PoolEntry] = []
    for artifacts in iter_pool(root):
        if not artifacts.metadata_path.is_file():
            continue
        metadata = read_json(artifacts.metadata_path)
        validation = (
            read_json(artifacts.validation_path) if artifacts.validation_path.is_file() else {}
        )
        if require_validated and not validation.get("validated"):
            continue
        entries.append(PoolEntry(artifacts=artifacts, metadata=metadata, validation=validation))
    return sorted(entries, key=lambda entry: entry.bug_id)


def load_excluded(path: Path) -> set[str]:
    """Bug IDs removed by deduplication."""
    if not Path(path).is_file():
        return set()
    record = read_json(path)
    return set(record.get("excluded", {}))


def eligible_entries(
    root: Path, dedup_report: Path, *, allow_scripted: bool = False
) -> list[PoolEntry]:
    """Validated, deduplicated, non-scripted bugs: the sampling frame."""
    excluded = load_excluded(dedup_report)
    entries = [entry for entry in load_pool(root) if entry.bug_id not in excluded]
    if not allow_scripted:
        dropped = [entry.bug_id for entry in entries if entry.scripted or entry.backend == "local"]
        entries = [
            entry for entry in entries if not (entry.scripted or entry.backend == "local")
        ]
        if dropped:
            from ssr.util import get_logger

            get_logger().warning(
                "excluded %d harness-proving candidate(s) from the sampling frame: %s",
                len(dropped),
                ", ".join(dropped[:5]),
            )
    if not entries:
        raise SsrError(
            f"no eligible bugs under {root}. Generate and validate a pool first, "
            "then run scripts/deduplicate_bug_pool.py."
        )
    return entries
