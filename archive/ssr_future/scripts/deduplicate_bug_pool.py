#!/usr/bin/env python3
"""Detect duplicates in the validated pool (handoff section 12).

    python scripts/deduplicate_bug_pool.py
    python scripts/deduplicate_bug_pool.py --report data/sampling/dedup_report.json

Six deterministic signals run in a fixed order: identical diffs, identical
normalised diffs, identical buggy trees, duplicate second-order states,
near-duplicates from the same code hunk, and history reversions that undo the
same commit. The survivor of every duplicate group is the lowest bug ID, so
the outcome does not depend on the order candidates were produced.

No taxonomy label is read. The report records every excluded bug ID with its
reason and the bug it duplicates.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.dedup import deduplicate  # noqa: E402
from ssr.paths import SAMPLING, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.pool import load_pool  # noqa: E402
from ssr.util import SsrError, setup_logging, utc_now, write_json  # noqa: E402

DEFAULT_REPORT = SAMPLING / "dedup_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", default=str(VALIDATED_POOL))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)

    entries = load_pool(Path(args.pool))
    if not entries:
        raise SsrError(f"no validated bugs under {args.pool}")

    result = deduplicate(entry.to_dedup_record() for entry in entries)
    by_id = {entry.bug_id: entry for entry in entries}

    report = {
        "generated_at_utc": utc_now(),
        "pool": str(Path(args.pool)),
        "summary": result.summary(),
        "kept": result.kept,
        "excluded": {
            bug_id: {
                **detail,
                "repo": by_id[bug_id].repo,
                "bug_order": by_id[bug_id].bug_order,
            }
            for bug_id, detail in sorted(result.excluded.items())
        },
        "groups": result.groups,
        "note": "Deduplication uses diff, tree and lineage signals only. No taxonomy "
        "label is read at any point.",
    }
    write_json(Path(args.report), report)

    log.info(
        "%d bug(s) in, %d kept, %d excluded",
        report["summary"]["input"],
        report["summary"]["kept"],
        report["summary"]["excluded"],
    )
    print(json.dumps({"report": args.report, **report["summary"]}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
