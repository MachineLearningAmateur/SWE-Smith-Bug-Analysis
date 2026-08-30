#!/usr/bin/env python3
"""Compare the two independent reviews, by source and pooled (section 26).

    python scripts/compare_reviews.py

Locked until both COMPLETE markers exist. It joins the sealed reviews to the
hidden selection crosswalk, which is the first point in the study where the
source of a bug and its taxonomy label are allowed to meet.

Because the 100 cases are deliberately stratified 30/30/40, every pooled
number is reported with that caveat attached, and the source-specific
breakdowns are reported first:

    REMOVAL
    HISTORY_REVERSION
    SECOND_ORDER

Writes analysis/cross_model/. It never writes into a reviewer directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.corpus import read_status, status_banner  # noqa: E402
from ssr.paths import ANALYSIS, DATA, REVIEWERS, REVIEWS  # noqa: E402
from ssr.review_workflow import cross_check_metadata, load_results, require_both_complete  # noqa: E402
from ssr.taxonomy import family_for, verify_provenance  # noqa: E402
from ssr.util import SsrError, setup_logging, utc_now, write_json  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apply_frozen_families import agreement, confusion  # noqa: E402

CROSSWALK = DATA / "hidden" / "sample_metadata.csv"
STRATUM_LABEL = {
    "first_order_removal": "REMOVAL",
    "first_order_history_reversion": "HISTORY_REVERSION",
    "second_order_failed_solver": "SECOND_ORDER",
}

CAVEAT = (
    "The 100-case sample is a deliberate 30/30/40 study-design allocation across "
    "REMOVAL, HISTORY_REVERSION and SECOND_ORDER. Pooled proportions are NOT an "
    "estimate of the natural distribution of published SSR. Read the source-specific "
    "sections first."
)


def _corpus_kind() -> str:
    try:
        return read_status().corpus_kind
    except SsrError:
        return "UNKNOWN"


def load_crosswalk(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        raise SsrError(f"{path} does not exist; the sample was never selected")
    with open(path, encoding="utf-8", newline="") as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle)}


def safe_output(path: Path) -> Path:
    """Comparison output stays under the analysis root and never in reviews/.

    The analysis root follows SSR_ANALYSIS_ROOT, so a self-test that
    redirects it is still confined; what the check forbids is writing the
    comparison into a reviewer's own directory.
    """
    resolved = path.resolve()
    try:
        resolved.relative_to(ANALYSIS.resolve())
    except ValueError as exc:
        raise SsrError(f"comparison output must stay under {ANALYSIS}") from exc
    try:
        resolved.relative_to(REVIEWS.resolve())
    except ValueError:
        return resolved
    raise SsrError("comparison must never write into a reviewer directory")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=str(ANALYSIS / "cross_model"))
    parser.add_argument("--crosswalk", default=str(CROSSWALK))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    provenance = verify_provenance()
    require_both_complete()
    metadata = cross_check_metadata()
    output = safe_output(Path(args.output))
    output.mkdir(parents=True, exist_ok=True)

    crosswalk = load_crosswalk(Path(args.crosswalk))
    results = {reviewer: {r["case_id"]: r for r in load_results(reviewer)} for reviewer in REVIEWERS}
    left, right = REVIEWERS

    packet_ids = sorted(results[left])
    if sorted(results[right]) != packet_ids:
        raise SsrError("the two reviewers did not review the same packet IDs")
    missing = [pid for pid in packet_ids if pid not in crosswalk]
    if missing:
        raise SsrError(f"the crosswalk does not cover: {missing[:5]}")

    rows: list[dict] = []
    for packet_id in packet_ids:
        meta = crosswalk[packet_id]
        row = {
            "case_id": packet_id,
            "generation_method": meta["generation_method"],
            "method_family": meta["method_family"],
            "repo": meta["upstream_repo"],
            "language": meta["language"],
            
        }
        for reviewer in REVIEWERS:
            record = results[reviewer][packet_id]
            row[f"{reviewer}_pattern"] = record["failure_pattern"]
            row[f"{reviewer}_family"] = family_for(record["failure_pattern"])
            row[f"{reviewer}_scope"] = record["failure_scope"]
            row[f"{reviewer}_fit"] = record["taxonomy_fit"]
        row["pattern_agree"] = row[f"{left}_pattern"] == row[f"{right}_pattern"]
        row["family_agree"] = row[f"{left}_family"] == row[f"{right}_family"]
        row["scope_agree"] = row[f"{left}_scope"] == row[f"{right}_scope"]
        rows.append(row)

    by_source: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_source[row["method_family"]].append(row)

    def section(subset: list[dict]) -> dict:
        return {
            "n": len(subset),
            "fine_grained": agreement(
                [row[f"{left}_pattern"] for row in subset], [row[f"{right}_pattern"] for row in subset]
            ),
            "family": agreement(
                [row[f"{left}_family"] for row in subset], [row[f"{right}_family"] for row in subset]
            ),
            "scope": agreement(
                [row[f"{left}_scope"] for row in subset], [row[f"{right}_scope"] for row in subset]
            ),
            "family_coverage": {
                reviewer: dict(Counter(row[f"{reviewer}_family"] for row in subset).most_common())
                for reviewer in REVIEWERS
            },
            "pattern_coverage": {
                reviewer: dict(Counter(row[f"{reviewer}_pattern"] for row in subset).most_common())
                for reviewer in REVIEWERS
            },
            "consensus_families": dict(
                Counter(row[f"{left}_family"] for row in subset if row["family_agree"]).most_common()
            ),
        }

    report = {
        "computed_at_utc": utc_now(),
        "corpus_kind": _corpus_kind(),
        "stratification_caveat": CAVEAT,
        "taxonomy": provenance,
        "snapshot_manifest_sha256": metadata["snapshot_manifest_sha256"],
        "by_source": {source: section(subset) for source, subset in sorted(by_source.items())},
        "pooled": {**section(rows), "caveat": CAVEAT},
        "by_language": {
            language: section([row for row in rows if row["language"] == language])
            for language in sorted({row["language"] for row in rows})
        },
        
        "confusion": {
            "fine_grained": confusion(
                [row[f"{left}_pattern"] for row in rows], [row[f"{right}_pattern"] for row in rows]
            ),
            "family": confusion(
                [row[f"{left}_family"] for row in rows], [row[f"{right}_family"] for row in rows]
            ),
        },
    }
    write_json(output / "source_specific_comparison.json", report)

    with open(output / "joined_with_source.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    print(status_banner())
    log.info("compared %d case(s) across %d source(s)", len(rows), len(by_source))
    print(json.dumps({
        "output": str(output),
        "n": len(rows),
        "by_source": {
            source: {
                "n": data["n"],
                "family_agreement": data["family"]["exact_agreement"],
                "family_kappa": data["family"]["cohens_kappa"],
            }
            for source, data in report["by_source"].items()
        },
        "caveat": CAVEAT,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
