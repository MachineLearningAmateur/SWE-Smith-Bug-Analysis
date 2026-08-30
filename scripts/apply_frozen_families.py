#!/usr/bin/env python3
"""Derive broad families and compute agreement (handoff section 24).

    python scripts/apply_frozen_families.py

Runs only after both COMPLETE markers exist. It applies the frozen mapping to
BOTH reviewers' original fine-grained labels. Neither reviewer re-classifies
anything, and the fine-grained labels are preserved beside the derived family
column in every output.

Computes:
    fine-label exact agreement and Cohen's kappa
    family exact agreement and Cohen's kappa
    scope agreement

Outputs go to analysis/. The original review outputs are never rewritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.corpus import read_status, status_banner  # noqa: E402
from ssr.paths import ANALYSIS, REVIEWERS  # noqa: E402
from ssr.review_workflow import cross_check_metadata, load_results, require_both_complete  # noqa: E402
from ssr.taxonomy import family_for, verify_provenance  # noqa: E402
from ssr.util import SsrError, setup_logging, utc_now, write_json  # noqa: E402


def _corpus_kind() -> str:
    try:
        return read_status().corpus_kind
    except SsrError:
        return "UNKNOWN"


def cohen_kappa(left: list[str], right: list[str]) -> float | None:
    """Cohen's kappa for two label sequences of equal length.

    Written out rather than taken from scikit-learn so the analysis has no
    heavyweight dependency and the computation is auditable in place.
    """
    if len(left) != len(right) or not left:
        return None
    total = len(left)
    observed = sum(a == b for a, b in zip(left, right)) / total
    left_counts = Counter(left)
    right_counts = Counter(right)
    expected = sum(
        (left_counts[label] / total) * (right_counts[label] / total)
        for label in set(left) | set(right)
    )
    if expected >= 1.0:
        return 1.0 if observed >= 1.0 else 0.0
    return round((observed - expected) / (1 - expected), 4)


def agreement(left: list[str], right: list[str]) -> dict:
    total = len(left)
    exact = sum(a == b for a, b in zip(left, right))
    return {
        "n": total,
        "exact_agreements": exact,
        "exact_agreement": round(exact / total, 4) if total else None,
        "cohens_kappa": cohen_kappa(left, right),
    }


def confusion(left: list[str], right: list[str]) -> list[dict]:
    pairs = Counter(zip(left, right))
    return [
        {"codex": a, "claude": b, "count": count}
        for (a, b), count in sorted(pairs.items(), key=lambda item: (-item[1], item[0]))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", default=str(ANALYSIS / "frozen_families"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    provenance = verify_provenance()
    require_both_complete()
    metadata = cross_check_metadata()

    results = {reviewer: load_results(reviewer) for reviewer in REVIEWERS}
    ids = {reviewer: [record["case_id"] for record in records] for reviewer, records in results.items()}
    if len(set(map(tuple, ids.values()))) != 1:
        raise SsrError("the two reviewers did not review the same case IDs")

    case_ids = ids[REVIEWERS[0]]
    joined: list[dict] = []
    for index, case_id in enumerate(case_ids):
        row: dict = {"case_id": case_id}
        for reviewer in REVIEWERS:
            record = results[reviewer][index]
            fine = record["failure_pattern"]
            row[f"{reviewer}_failure_pattern"] = fine
            row[f"{reviewer}_failure_family"] = family_for(fine)
            row[f"{reviewer}_failure_scope"] = record["failure_scope"]
            row[f"{reviewer}_pattern_confidence"] = record["pattern_confidence"]
            row[f"{reviewer}_taxonomy_fit"] = record["taxonomy_fit"]
        row["pattern_agree"] = (
            row[f"{REVIEWERS[0]}_failure_pattern"] == row[f"{REVIEWERS[1]}_failure_pattern"]
        )
        row["family_agree"] = (
            row[f"{REVIEWERS[0]}_failure_family"] == row[f"{REVIEWERS[1]}_failure_family"]
        )
        row["scope_agree"] = (
            row[f"{REVIEWERS[0]}_failure_scope"] == row[f"{REVIEWERS[1]}_failure_scope"]
        )
        joined.append(row)

    left, right = REVIEWERS
    metrics = {
        "computed_at_utc": utc_now(),
        "corpus_kind": _corpus_kind(),
        "n_cases": len(joined),
        "taxonomy": provenance,
        "snapshot_manifest_sha256": metadata["snapshot_manifest_sha256"],
        "fine_grained": agreement(
            [row[f"{left}_failure_pattern"] for row in joined],
            [row[f"{right}_failure_pattern"] for row in joined],
        ),
        "family": agreement(
            [row[f"{left}_failure_family"] for row in joined],
            [row[f"{right}_failure_family"] for row in joined],
        ),
        "scope": agreement(
            [row[f"{left}_failure_scope"] for row in joined],
            [row[f"{right}_failure_scope"] for row in joined],
        ),
        "distribution": {
            reviewer: {
                "patterns": dict(Counter(row[f"{reviewer}_failure_pattern"] for row in joined).most_common()),
                "families": dict(Counter(row[f"{reviewer}_failure_family"] for row in joined).most_common()),
                "scopes": dict(Counter(row[f"{reviewer}_failure_scope"] for row in joined).most_common()),
            }
            for reviewer in REVIEWERS
        },
        "note": (
            "Fine-grained labels are preserved beside the derived family columns. "
            "Families are computed from the frozen mapping, never judged by a reviewer. "
            "The 100-case sample is deliberately stratified 30/30/40, so pooled "
            "proportions are not the natural distribution of published SSR."
        ),
    }

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "agreement_metrics.json", metrics)
    write_json(output / "family_confusion.json", {
        "fine_grained": confusion(
            [row[f"{left}_failure_pattern"] for row in joined],
            [row[f"{right}_failure_pattern"] for row in joined],
        ),
        "family": confusion(
            [row[f"{left}_failure_family"] for row in joined],
            [row[f"{right}_failure_family"] for row in joined],
        ),
    })

    with open(output / "dual_review_joined.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(joined[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(joined)

    disagreements = [row for row in joined if not row["family_agree"]]
    with open(output / "family_disagreements.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(joined[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(disagreements)

    print(status_banner())
    log.info("family agreement %s, kappa %s", metrics["family"]["exact_agreement"], metrics["family"]["cohens_kappa"])
    print(json.dumps({
        "output": str(output),
        "n": metrics["n_cases"],
        "fine_grained": metrics["fine_grained"],
        "family": metrics["family"],
        "scope": metrics["scope"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
