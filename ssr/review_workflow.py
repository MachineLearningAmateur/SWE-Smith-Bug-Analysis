"""Reviewer directories, incremental saving and completion (sections 20-23).

Each reviewer owns exactly one directory and writes nothing else:

    reviews/<reviewer>/cases/SSR_nnn.json   one file per bug, saved at once
    reviews/<reviewer>/progress.json        counter and state
    reviews/<reviewer>/review_metadata.json snapshot and taxonomy hashes
    reviews/<reviewer>/review_results.jsonl built after all 100 validate
    reviews/<reviewer>/COMPLETE             the marker

``assert_write_boundary`` is the mechanical form of the rule in AGENTS.md and
CLAUDE.md: a reviewer's tooling refuses to write outside its own directory.
``forbid_peeking`` is the mechanical form of reviewer independence: reading
the other reviewer's results before both COMPLETE markers exist is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ssr.paths import REVIEWERS, REVIEWS, REVIEW_SNAPSHOT_MANIFEST, reviewer_dir
from ssr.review_formats import codec_for
from ssr.taxonomy import taxonomy_fingerprint
from ssr.util import (
    SsrError,
    canonical_json,
    read_json,
    sha256_file,
    utc_now,
    write_json,
    write_text,
)

# Each reviewer writes its own format; the pattern follows the codec.
def case_glob(reviewer: str) -> str:
    return codec_for(reviewer).glob()


@dataclass
class ReviewerPaths:
    reviewer: str

    @property
    def root(self) -> Path:
        return reviewer_dir(self.reviewer)

    @property
    def cases(self) -> Path:
        return self.root / "cases"

    @property
    def progress(self) -> Path:
        return self.root / "progress.json"

    @property
    def metadata(self) -> Path:
        return self.root / "review_metadata.json"

    @property
    def results(self) -> Path:
        return self.root / "review_results.jsonl"

    @property
    def complete(self) -> Path:
        return self.root / "COMPLETE"

    @property
    def codec(self):
        return codec_for(self.reviewer)

    def case_file(self, case_id: str) -> Path:
        return self.cases / self.codec.filename(case_id)

    def case_files(self) -> list[Path]:
        return sorted(self.cases.glob(self.codec.glob())) if self.cases.is_dir() else []

    def ensure(self) -> "ReviewerPaths":
        self.cases.mkdir(parents=True, exist_ok=True)
        return self


def assert_write_boundary(reviewer: str, target: Path) -> None:
    """Refuse a write outside ``reviews/<reviewer>/``."""
    allowed = reviewer_dir(reviewer).resolve()
    resolved = Path(target).resolve()
    try:
        resolved.relative_to(allowed)
    except ValueError as exc:
        raise SsrError(
            f"reviewer {reviewer!r} may only write under {allowed}; refused {resolved}"
        ) from exc


def is_complete(reviewer: str) -> bool:
    return ReviewerPaths(reviewer).complete.is_file()


def forbid_peeking(reviewer: str) -> None:
    """Reviewer independence: no reading the other side before both finish."""
    other = [name for name in REVIEWERS if name != reviewer]
    if all(is_complete(name) for name in REVIEWERS):
        return
    raise SsrError(
        f"reviewer independence: {reviewer!r} must not read {other} results before both "
        "COMPLETE markers exist."
    )


# ----------------------------------------------------------------------
def expected_case_ids() -> list[str]:
    """The frozen 100 case IDs, taken from the snapshot manifest."""
    if not REVIEW_SNAPSHOT_MANIFEST.is_file():
        raise SsrError(
            f"{REVIEW_SNAPSHOT_MANIFEST} does not exist. Build and freeze the review "
            "packets before starting a review."
        )
    manifest = read_json(REVIEW_SNAPSHOT_MANIFEST)
    return sorted(entry["case_id"] for entry in manifest["packets"])


def snapshot_manifest_hash() -> str:
    if not REVIEW_SNAPSHOT_MANIFEST.is_file():
        raise SsrError(
            f"{REVIEW_SNAPSHOT_MANIFEST} does not exist. This checkout has no frozen "
            "evidence, so there is nothing for a review to be tied to."
        )
    return sha256_file(REVIEW_SNAPSHOT_MANIFEST)


def init_metadata(reviewer: str, *, model: str, notes: str | None = None) -> dict[str, Any]:
    from ssr.corpus import read_status  # local import: avoids a cycle

    paths = ReviewerPaths(reviewer).ensure()
    try:
        corpus_kind = read_status().corpus_kind
    except SsrError:
        corpus_kind = "UNKNOWN"
    metadata = {
        "reviewer": reviewer,
        "model": model,
        "started_at_utc": utc_now(),
        "completed_at_utc": None,
        "snapshot_manifest_sha256": snapshot_manifest_hash(),
        "taxonomy_fingerprint": taxonomy_fingerprint(),
        # Carried into every downstream report, so a rehearsal review can
        # never be mistaken for a research result.
        "corpus_kind": corpus_kind,
        "case_format": codec_for(reviewer).name,
        "expected_case_count": len(expected_case_ids()),
        "notes": notes,
    }
    assert_write_boundary(reviewer, paths.metadata)
    write_json(paths.metadata, metadata)
    return metadata


def save_case(reviewer: str, result: dict[str, Any]) -> Path:
    """Write one case result immediately (handoff section 23)."""
    paths = ReviewerPaths(reviewer).ensure()
    case_id = result.get("case_id")
    if not isinstance(case_id, str):
        raise SsrError("a review result needs a string case_id")
    target = paths.case_file(case_id)
    assert_write_boundary(reviewer, target)
    write_text(target, paths.codec.dump(result))
    update_progress(reviewer)
    return target


def collect_cases(reviewer: str, *, require_all: bool = False) -> list[dict[str, Any]]:
    paths = ReviewerPaths(reviewer)
    if not paths.cases.is_dir():
        return []
    results: list[dict[str, Any]] = []
    for path in paths.case_files():
        try:
            record = paths.codec.load(path.read_text(encoding="utf-8"))
        except SsrError as exc:
            raise SsrError(f"{path}: {exc}") from exc
        if record.get("case_id") != paths.codec.case_id_of(path.name):
            raise SsrError(
                f"{path}: case_id {record.get('case_id')!r} does not match the file name"
            )
        results.append(record)
    if require_all:
        expected = expected_case_ids()
        found = {record["case_id"] for record in results}
        missing = sorted(set(expected) - found)
        unexpected = sorted(found - set(expected))
        if missing:
            raise SsrError(f"{reviewer}: {len(missing)} case(s) missing, first: {missing[:5]}")
        if unexpected:
            raise SsrError(f"{reviewer}: unexpected case ids: {unexpected[:5]}")
    return results


def update_progress(reviewer: str) -> dict[str, Any]:
    paths = ReviewerPaths(reviewer).ensure()
    expected = expected_case_ids()
    done = sorted(paths.codec.case_id_of(path.name) for path in paths.case_files())
    remaining = [case_id for case_id in expected if case_id not in set(done)]
    progress = {
        "reviewer": reviewer,
        "state": "COMPLETE" if not remaining and paths.complete.is_file() else "IN_PROGRESS",
        "completed": len(done),
        "expected": len(expected),
        "remaining_count": len(remaining),
        "next_case_id": remaining[0] if remaining else None,
        "updated_at_utc": utc_now(),
    }
    assert_write_boundary(reviewer, paths.progress)
    write_json(paths.progress, progress)
    return progress


def finalise(reviewer: str) -> dict[str, Any]:
    """Build the JSONL, mark progress COMPLETE and write the marker.

    Only runs when every expected case exists and validates.
    """
    from ssr.validate_review import validate_results  # local import: avoids a cycle

    paths = ReviewerPaths(reviewer).ensure()
    results = collect_cases(reviewer, require_all=True)
    validate_results(results)

    ordered = sorted(results, key=lambda record: record["case_id"])
    assert_write_boundary(reviewer, paths.results)
    with open(paths.results, "w", encoding="utf-8", newline="\n") as handle:
        for record in ordered:
            handle.write(canonical_json(record) + "\n")

    metadata = read_json(paths.metadata) if paths.metadata.is_file() else {}
    metadata["completed_at_utc"] = utc_now()
    metadata["result_count"] = len(ordered)
    metadata["results_sha256"] = sha256_file(paths.results)
    current_snapshot = snapshot_manifest_hash()
    if metadata.get("snapshot_manifest_sha256") not in (None, current_snapshot):
        raise SsrError(
            f"{reviewer}: the review snapshot manifest changed during the review "
            f"({metadata['snapshot_manifest_sha256']} -> {current_snapshot}). "
            "The evidence must stay frozen; this review is void."
        )
    metadata["snapshot_manifest_sha256"] = current_snapshot
    assert_write_boundary(reviewer, paths.metadata)
    write_json(paths.metadata, metadata)

    assert_write_boundary(reviewer, paths.complete)
    paths.complete.write_text(
        f"{reviewer} completed {len(ordered)} cases at {utc_now()}\n"
        f"snapshot_manifest_sha256 {current_snapshot}\n"
        f"taxonomy_fingerprint {taxonomy_fingerprint()}\n",
        encoding="utf-8",
        newline="\n",
    )
    update_progress(reviewer)
    return metadata


def both_complete() -> bool:
    return all(is_complete(name) for name in REVIEWERS)


def require_both_complete() -> None:
    missing = [name for name in REVIEWERS if not is_complete(name)]
    if missing:
        raise SsrError(
            "comparison is locked until both COMPLETE markers exist. Missing: "
            + ", ".join(str(ReviewerPaths(name).complete) for name in missing)
        )


def load_results(reviewer: str) -> list[dict[str, Any]]:
    paths = ReviewerPaths(reviewer)
    if not paths.results.is_file():
        raise SsrError(f"{paths.results} does not exist; run the reviewer's finalise step first")
    records = [json.loads(line) for line in paths.results.read_text(encoding="utf-8").splitlines() if line.strip()]
    return sorted(records, key=lambda record: record["case_id"])


def cross_check_metadata() -> dict[str, Any]:
    """Both reviewers must have used the same frozen evidence and taxonomy."""
    seen: dict[str, dict[str, Any]] = {}
    for reviewer in REVIEWERS:
        path = ReviewerPaths(reviewer).metadata
        if not path.is_file():
            raise SsrError(f"{path} does not exist")
        seen[reviewer] = read_json(path)
    snapshots = {reviewer: record.get("snapshot_manifest_sha256") for reviewer, record in seen.items()}
    fingerprints = {reviewer: record.get("taxonomy_fingerprint") for reviewer, record in seen.items()}
    if len(set(snapshots.values())) != 1:
        raise SsrError(f"reviewers used different evidence snapshots: {snapshots}")
    if len(set(fingerprints.values())) != 1:
        raise SsrError(f"reviewers used different taxonomy versions: {fingerprints}")
    return {
        "snapshot_manifest_sha256": next(iter(snapshots.values())),
        "taxonomy_fingerprint": next(iter(fingerprints.values())),
        "reviewers": seen,
    }


def summarise_all() -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for reviewer in REVIEWERS:
        paths = ReviewerPaths(reviewer)
        cases = len(paths.case_files())
        summary[reviewer] = {
            "cases_saved": cases,
            "complete": paths.complete.is_file(),
            "results_file": paths.results.is_file(),
        }
    return summary
