#!/usr/bin/env python3
"""Write placeholder reviews for both reviewers, to rehearse the workflow.

    python tests/simulate_reviews.py --seed 3

These are NOT reviews. The labels are drawn from a fixed distribution with a
built-in disagreement rate; nobody looked at the evidence. The purpose is to
prove that the incremental save, the schema and rule validation, the
completion markers, the family derivation and the source-specific comparison
all work over 100 real packets before a real review starts.

Refuses to run unless the reviewer directories are empty, so it can never
overwrite a real review.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import REVIEWERS  # noqa: E402
from ssr.review_workflow import ReviewerPaths, expected_case_ids, init_metadata, save_case  # noqa: E402
from ssr.taxonomy import FINE_LABELS, PROCESS_LABELS  # noqa: E402
from ssr.util import SsrError  # noqa: E402
from ssr.validate_review import packet_evidence_ids  # noqa: E402

# A plausible spread. The exact numbers do not matter: the point is to make
# the agreement statistics non-degenerate.
WEIGHTS = {
    "incomplete_change_propagation": 20,
    "false_premise_about_existing_code": 18,
    "broke_existing_contract_or_behavior": 15,
    "misdiagnosed_root_cause": 12,
    "masked_symptom_instead_of_fixing": 10,
    "violated_project_constraint_or_convention": 8,
    "disproportionate_or_duplicative_solution": 6,
    "wrong_baseline_or_branch": 4,
    "unverified_trial_and_error": 3,
    "vacuous_verification": 3,
    "OTHER_TECHNICAL_PATTERN": 1,
}


def draw(rng: random.Random) -> str:
    labels = list(WEIGHTS)
    return rng.choices(labels, weights=[WEIGHTS[label] for label in labels], k=1)[0]


def record(case_id: str, pattern: str, rng: random.Random) -> dict:
    available = sorted(packet_evidence_ids(case_id))
    cited = [item for item in available if item in ("BUG_DIFF", "SPECIFICATION")] or available[:1]
    if any(item.startswith("TEST_FAILURE") for item in available):
        cited.append(next(item for item in available if item.startswith("TEST_FAILURE")))
    # Code-state precedence: a process label may not be paired with BOTH.
    scope = "REPAIR_PROCESS" if pattern in PROCESS_LABELS else rng.choice(["CODE_STATE", "CODE_STATE", "BOTH"])
    return {
        "case_id": case_id,
        "failure_pattern": pattern,
        "pattern_confidence": rng.choice(["HIGH", "HIGH", "MEDIUM", "LOW"]),
        "failure_scope": scope,
        "taxonomy_fit": "OTHER" if pattern == "OTHER_TECHNICAL_PATTERN" else "DIRECT",
        "supporting_evidence_ids": sorted(set(cited)),
        "reasoning_summary": (
            "Placeholder rehearsal record; no evidence was examined. "
            f"Assigned {pattern} to exercise the workflow end to end."
        ),
        "proposed_other_pattern": (
            "placeholder alternative pattern for the rehearsal"
            if pattern == "OTHER_TECHNICAL_PATTERN"
            else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--seed", type=int, default=3)
    parser.add_argument("--disagreement", type=float, default=0.32, help="fraction of cases where the two differ")
    args = parser.parse_args()

    for reviewer in REVIEWERS:
        paths = ReviewerPaths(reviewer)
        if paths.case_files():
            raise SsrError(
                f"reviews/{reviewer}/cases is not empty. Refusing to overwrite a review. "
                "Clear it first if this really is a rehearsal."
            )

    case_ids = expected_case_ids()
    rng = random.Random(args.seed)
    for reviewer in REVIEWERS:
        init_metadata(reviewer, model=f"rehearsal-placeholder/{reviewer}", notes="SIMULATED REHEARSAL, NOT A REVIEW")

    for case_id in case_ids:
        base = draw(rng)
        left = base
        right = base if rng.random() > args.disagreement else draw(rng)
        save_case(REVIEWERS[0], record(case_id, left, rng))
        save_case(REVIEWERS[1], record(case_id, right, rng))

    print(f"wrote {len(case_ids)} placeholder case(s) for each of {', '.join(REVIEWERS)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
