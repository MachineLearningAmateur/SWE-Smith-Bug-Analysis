#!/usr/bin/env python3
"""Bring a finished review back from a bundle into the research repository.

    python scripts/import_review_results.py --reviewer codex --from ../codex_review
    python scripts/import_review_results.py --reviewer claude --from ../claude_review.zip

Copies only ``reviews/<reviewer>/`` and nothing else. Before it copies, it
checks that the review was done against this repository's frozen evidence:

* the reviewer's ``review_metadata.json`` must record the same snapshot
  manifest SHA-256 as this checkout;
* it must record the same taxonomy fingerprint;
* every case must validate against the schema and the frozen decision rules;
* the case IDs must be exactly the frozen 100.

A review done against different evidence is refused, not merged. That is the
point of freezing the evidence in the first place.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import REVIEWERS, reviewer_dir  # noqa: E402
from ssr.review_workflow import (  # noqa: E402
    expected_bug_ids,
    snapshot_manifest_hash,
)
from ssr.taxonomy import taxonomy_fingerprint  # noqa: E402
from ssr.util import (  # noqa: E402
    SsrError,
    force_rmtree,
    read_json,
    setup_logging,
    utc_now,
    write_json,
)
from ssr.validate_review import validate_results  # noqa: E402


def locate_source(source: Path, reviewer: str, workspace: Path) -> Path:
    """The reviewer directory inside a bundle directory or zip archive."""
    if source.is_file() and source.suffix == ".zip":
        with zipfile.ZipFile(source) as handle:
            handle.extractall(workspace)
        candidates = sorted(workspace.rglob(f"reviews/{reviewer}"))
        if not candidates:
            raise SsrError(f"{source} contains no reviews/{reviewer} directory")
        return candidates[0]
    if not source.is_dir():
        raise SsrError(f"{source} is neither a directory nor a .zip archive")
    direct = source / "reviews" / reviewer
    if direct.is_dir():
        return direct
    if source.name == reviewer and (source / "cases").is_dir():
        return source
    raise SsrError(f"cannot find reviews/{reviewer} under {source}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reviewer", required=True, choices=list(REVIEWERS))
    parser.add_argument("--from", dest="source", required=True, help="bundle directory or .zip")
    parser.add_argument("--force", action="store_true", help="replace an existing local review")
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="import a review that is not finished (no COMPLETE marker)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    target = reviewer_dir(args.reviewer)
    if target.is_dir() and any(target.glob("cases/SSR_*.json")) and not args.force:
        raise SsrError(
            f"{target} already holds a review. Pass --force only if you mean to replace it."
        )

    with tempfile.TemporaryDirectory(prefix="ssr_import_") as scratch:
        incoming = locate_source(Path(args.source).resolve(), args.reviewer, Path(scratch))

        metadata_path = incoming / "review_metadata.json"
        if not metadata_path.is_file():
            raise SsrError(f"{metadata_path} is missing; this is not a finished review directory")
        metadata = read_json(metadata_path)

        local_snapshot = snapshot_manifest_hash()
        if metadata.get("snapshot_manifest_sha256") != local_snapshot:
            raise SsrError(
                "this review was done against different evidence and cannot be merged.\n"
                f"  review:     {metadata.get('snapshot_manifest_sha256')}\n"
                f"  this repo:  {local_snapshot}"
            )
        local_taxonomy = taxonomy_fingerprint()
        if metadata.get("taxonomy_fingerprint") != local_taxonomy:
            raise SsrError(
                "this review used a different taxonomy version and cannot be merged.\n"
                f"  review:     {metadata.get('taxonomy_fingerprint')}\n"
                f"  this repo:  {local_taxonomy}"
            )

        complete = (incoming / "COMPLETE").is_file()
        if not complete and not args.allow_incomplete:
            raise SsrError(
                f"{incoming} has no COMPLETE marker. Ask the reviewer to run "
                f"'python scripts/validate_review_output.py --reviewer {args.reviewer} --finalise', "
                "or pass --allow-incomplete to import work in progress."
            )

        cases = sorted(incoming.glob("cases/SSR_*.json"))
        records = [read_json(path) for path in cases]
        expected = expected_bug_ids()
        found = {record.get("bug_id") for record in records}
        unexpected = sorted(found - set(expected))
        if unexpected:
            raise SsrError(f"the review holds case IDs that are not in this corpus: {unexpected[:5]}")
        if complete:
            missing = sorted(set(expected) - found)
            if missing:
                raise SsrError(
                    f"the review is marked COMPLETE but {len(missing)} case(s) are missing: {missing[:5]}"
                )

        warnings = validate_results(records)
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)

        if target.exists():
            force_rmtree(target)
        shutil.copytree(incoming, target)

    record_path = target / "IMPORTED.json"
    write_json(
        record_path,
        {
            "imported_at_utc": utc_now(),
            "source": str(Path(args.source).resolve()),
            "reviewer": args.reviewer,
            "cases": len(cases),
            "complete": complete,
            "snapshot_manifest_sha256": local_snapshot,
            "taxonomy_fingerprint": local_taxonomy,
            "advisory_warnings": len(warnings),
        },
    )

    log.info("imported %d case(s) for %s", len(cases), args.reviewer)
    print(
        json.dumps(
            {
                "reviewer": args.reviewer,
                "cases": len(cases),
                "complete": complete,
                "warnings": len(warnings),
                "target": str(target),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
