"""Deterministic, taxonomy-blind selection of the 100-bug sample."""

import pytest

from ssr.sampling import (
    Candidate,
    allocate,
    assert_no_taxonomy_fields,
    assign_packet_ids,
    language_match_report,
    language_targets_from_profile,
    select,
    stratum_for,
)
from ssr.util import SsrError

CONFIG = {
    "seed": 20260829,
    "target_n": 100,
    "target_sources": {
        "first_order_removal": 30,
        "first_order_history_reversion": 30,
        "second_order_failed_solver": 40,
    },
    "max_per_repo": 4,
    "min_unique_repos": 25,
    "avoid_parent_child_pairs": True,
    "avoid_same_base_state": False,
    "shortfall_policy": {
        "fill_order": [
            "second_order_failed_solver",
            "first_order_removal",
            "first_order_history_reversion",
        ]
    },
    "packet_id_format": "SSR_{index:03d}",
}


PREFIX = {
    "first_order_removal": "REM",
    "first_order_history_reversion": "HIS",
    "second_order_failed_solver": "SEC",
}


def make_pool(per_stratum: dict[str, int], repos: int = 40, languages=("python",)) -> list[Candidate]:
    candidates = []
    for stratum, count in per_stratum.items():
        for index in range(count):
            candidates.append(
                Candidate(
                    bug_id=f"BUG_{PREFIX[stratum]}{index:04d}",
                    stratum=stratum,
                    repo=f"org/repo{index % repos:02d}",
                    language=languages[index % len(languages)],
                    repo_size_bin="MEDIUM",
                )
            )
    return candidates


FULL = {
    "first_order_removal": 60,
    "first_order_history_reversion": 60,
    "second_order_failed_solver": 60,
}


def test_stratum_for():
    assert stratum_for("REMOVAL", 1) == "first_order_removal"
    assert stratum_for("HISTORY_REVERSION", 1) == "first_order_history_reversion"
    assert stratum_for("FAILED_SOLVER", 2) == "second_order_failed_solver"


def test_taxonomy_fields_are_refused():
    with pytest.raises(SsrError, match="taxonomy or review fields"):
        assert_no_taxonomy_fields([{"bug_id": "BUG_a", "failure_pattern": "x"}])


def test_neutral_fields_are_accepted():
    assert_no_taxonomy_fields([{"bug_id": "BUG_a", "repo": "x", "language": "python"}])


def test_target_allocation_is_met_when_the_pool_is_large():
    result = select(make_pool(FULL), CONFIG)
    assert len(result.selected) == 100
    assert result.allocation == {
        "first_order_removal": 30,
        "first_order_history_reversion": 30,
        "second_order_failed_solver": 40,
    }


def test_selection_is_deterministic():
    first = select(make_pool(FULL), CONFIG)
    second = select(make_pool(FULL), CONFIG)
    assert [c.bug_id for c in first.selected] == [c.bug_id for c in second.selected]
    assert first.packet_ids == second.packet_ids


def test_a_different_seed_gives_a_different_sample():
    other = dict(CONFIG, seed=1)
    assert {c.bug_id for c in select(make_pool(FULL), CONFIG).selected} != {
        c.bug_id for c in select(make_pool(FULL), other).selected
    }


def test_per_repository_ceiling_holds():
    result = select(make_pool(FULL, repos=30), CONFIG)
    counts: dict[str, int] = {}
    for candidate in result.selected:
        counts[candidate.repo] = counts.get(candidate.repo, 0) + 1
    assert max(counts.values()) <= CONFIG["max_per_repo"]


def test_unique_repository_floor_is_met():
    result = select(make_pool(FULL, repos=30), CONFIG)
    assert result.unique_repos >= CONFIG["min_unique_repos"]


def test_shortfall_rule_fills_from_first_order_evenly():
    available = {
        "first_order_removal": 60,
        "first_order_history_reversion": 60,
        "second_order_failed_solver": 10,
    }
    allocation, deviations = allocate(
        available, CONFIG["target_sources"], 100, CONFIG["shortfall_policy"]["fill_order"]
    )
    assert allocation["second_order_failed_solver"] == 10
    assert sum(allocation.values()) == 100
    # The 30 missing slots are shared evenly between the two first-order strata.
    assert allocation["first_order_removal"] == allocation["first_order_history_reversion"] == 45
    assert any(row["type"] == "STRATUM_SHORTFALL" for row in deviations)


def test_shortfall_is_recorded_in_the_selection():
    pool = make_pool(
        {
            "first_order_removal": 60,
            "first_order_history_reversion": 60,
            "second_order_failed_solver": 5,
        }
    )
    result = select(pool, CONFIG)
    assert len(result.selected) == 100
    assert result.allocation["second_order_failed_solver"] == 5
    assert any(row["type"] == "STRATUM_SHORTFALL" for row in result.deviations)


def test_a_pool_that_is_too_small_is_reported_not_padded():
    pool = make_pool(
        {
            "first_order_removal": 10,
            "first_order_history_reversion": 10,
            "second_order_failed_solver": 10,
        }
    )
    result = select(pool, CONFIG)
    assert len(result.selected) == 30
    assert any(row["type"] == "POOL_TOO_SMALL" for row in result.deviations)


def test_parent_child_pairs_are_avoided_when_possible():
    pool = make_pool(FULL)
    # Half the second-order bugs descend from a removal bug that is also in
    # the pool; the rest descend from parents that were never pooled. There
    # are enough of the latter to fill the stratum without any pair.
    for candidate in pool:
        if candidate.stratum == "second_order_failed_solver":
            index = int(candidate.bug_id[-4:])
            candidate.parent_bug_id = (
                f"BUG_REM{index:04d}" if index < 15 else f"BUG_GHOST{index:04d}"
            )
    result = select(pool, CONFIG)
    chosen = {candidate.bug_id for candidate in result.selected}
    pairs = [
        candidate
        for candidate in result.selected
        if candidate.parent_bug_id and candidate.parent_bug_id in chosen
    ]
    assert not pairs


def test_lineage_pairs_are_flagged_when_unavoidable():
    """With only lineage-linked candidates left, the pair is taken and flagged."""
    pool = [
        Candidate("BUG_p001", "first_order_removal", "org/a", "python"),
        Candidate("BUG_c001", "second_order_failed_solver", "org/a", "python", parent_bug_id="BUG_p001"),
    ]
    config = dict(CONFIG, target_n=2, target_sources={
        "first_order_removal": 1,
        "first_order_history_reversion": 0,
        "second_order_failed_solver": 1,
    }, min_unique_repos=1)
    result = select(pool, config)
    assert len(result.selected) == 2
    assert result.lineage_pairs
    assert any(row["type"] == "LINEAGE_PAIRS_PRESENT" for row in result.deviations)


def test_packet_ids_are_a_seeded_shuffle_not_the_selection_order():
    bug_ids = [f"BUG_{index:04d}" for index in range(100)]
    mapping = assign_packet_ids(bug_ids, seed=20260829, fmt="SSR_{index:03d}")
    assert len(set(mapping.values())) == 100
    assert set(mapping.values()) == {f"SSR_{index:03d}" for index in range(1, 101)}
    # The mapping must not be the sorted order, or the index would leak rank.
    assert mapping["BUG_0000"] != "SSR_001" or mapping["BUG_0099"] != "SSR_100"


def test_language_targets_from_profile():
    profile = {"language_distribution": {"python": 3, "typescript": 1}}
    assert language_targets_from_profile(profile) == {"python": 0.75, "typescript": 0.25}


def test_language_matching_pulls_the_sample_towards_the_profile():
    pool = make_pool(FULL, repos=40, languages=("python", "typescript", "go"))
    targets = {"typescript": 0.6, "python": 0.3, "go": 0.1}
    result = select(pool, CONFIG, language_targets=targets)
    distribution = result.diagnostics["language_distribution"]
    # The pool is an even third each, so a perfect match is impossible, but
    # the selected share of typescript must exceed its share of the pool.
    assert distribution.get("typescript", 0) / len(result.selected) > 1 / 3


def test_language_match_report_flags_out_of_tolerance():
    selected = [Candidate(f"BUG_{i}", "first_order_removal", "org/a", "python") for i in range(10)]
    report = language_match_report(selected, {"typescript": 0.5, "python": 0.5}, 0.1)
    assert "typescript" in report["languages_out_of_tolerance"]
    assert "python" in report["languages_out_of_tolerance"]
