#!/usr/bin/env python3
"""Validate a reviewer's output, and finalise the review when it is complete.

    python scripts/validate_review_output.py --reviewer claude
    python scripts/validate_review_output.py --reviewer claude --case SWESMITH_007
    python scripts/validate_review_output.py --reviewer claude --finalise

Checks, in order:

1. every case file matches schemas/review_result.schema.json;
2. every cited evidence ID exists in that case's frozen packet;
3. the frozen code-state-precedence rule was applied;
4. on --finalise, all 100 cases are present, review_results.jsonl is written,
   progress is marked COMPLETE and the COMPLETE marker is created.

The script writes only inside reviews/<reviewer>/ and never reads the other
reviewer's directory.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import REVIEWERS  # noqa: E402
from ssr.review_workflow import (  # noqa: E402
    ReviewerPaths,
    collect_cases,
    expected_case_ids,
    finalise,
    update_progress,
)
from ssr.util import SsrError, read_json, setup_logging  # noqa: E402
from ssr.validate_review import validate_result, validate_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", required=True, choices=list(REVIEWERS))
    parser.add_argument("--case", action="append", default=[], help="validate one case id, e.g. SWESMITH_007; repeatable")
    parser.add_argument("--finalise", action="store_true", help="build the JSONL and mark COMPLETE")
    parser.add_argument("--strict", action="store_true", help="treat advisory warnings as failures")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    paths = ReviewerPaths(args.reviewer)

    if args.case:
        warnings: list[str] = []
        for case_id in args.case:
            path = paths.case_file(case_id)
            if not path.is_file():
                raise SsrError(f"{path} does not exist")
            warnings.extend(validate_result(read_json(path)))
        _report(warnings, args.strict)
        progress = update_progress(args.reviewer)
        print(json.dumps({"validated": args.case, "progress": progress}, indent=2))
        return 0

    results = collect_cases(args.reviewer)
    expected = expected_case_ids()
    found = {record["case_id"] for record in results}
    missing = sorted(set(expected) - found)

    warnings = validate_results(results)
    _report(warnings, args.strict)

    if args.finalise:
        if missing:
            raise SsrError(
                f"{args.reviewer}: cannot finalise, {len(missing)} case(s) missing. "
                f"First missing: {missing[:5]}"
            )
        metadata = finalise(args.reviewer)
        print(json.dumps({
            "reviewer": args.reviewer,
            "finalised": True,
            "cases": metadata.get("result_count"),
            "results_sha256": metadata.get("results_sha256"),
            "complete_marker": str(paths.complete),
        }, indent=2))
        return 0

    progress = update_progress(args.reviewer)
    print(json.dumps({
        "reviewer": args.reviewer,
        "validated_cases": len(results),
        "expected": len(expected),
        "missing": len(missing),
        "next_case_id": progress.get("next_case_id"),
        "warnings": len(warnings),
    }, indent=2))
    return 0


def _report(warnings: list[str], strict: bool) -> None:
    if not warnings:
        return
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if strict:
        raise SsrError(f"{len(warnings)} advisory warning(s) with --strict")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
