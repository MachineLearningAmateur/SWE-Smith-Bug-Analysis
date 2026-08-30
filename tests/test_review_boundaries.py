"""Reviewer independence and write boundaries are enforced by code."""

import pytest

from ssr.paths import REVIEWS, reviewer_dir
from ssr.review_workflow import assert_write_boundary, forbid_peeking, require_both_complete
from ssr.util import SsrError


def test_a_reviewer_may_write_inside_its_own_directory():
    assert_write_boundary("codex", reviewer_dir("codex") / "cases" / "SSR_001.json")
    assert_write_boundary("claude", reviewer_dir("claude") / "progress.json")


def test_a_reviewer_may_not_write_into_the_other_directory():
    with pytest.raises(SsrError, match="may only write under"):
        assert_write_boundary("codex", reviewer_dir("claude") / "cases" / "SSR_001.json")


def test_a_reviewer_may_not_write_outside_reviews():
    for target in (
        REVIEWS.parent / "configs" / "sampling.yaml",
        REVIEWS.parent / "taxonomy" / "pattern_families.yaml",
        REVIEWS.parent / "data" / "review_manifest.csv",
        REVIEWS.parent / "analysis" / "anything.json",
    ):
        with pytest.raises(SsrError, match="may only write under"):
            assert_write_boundary("codex", target)


def test_a_traversal_path_is_refused():
    with pytest.raises(SsrError, match="may only write under"):
        assert_write_boundary("codex", reviewer_dir("codex") / ".." / "claude" / "x.json")


def test_an_unknown_reviewer_is_refused():
    with pytest.raises(ValueError):
        reviewer_dir("someone_else")


def test_comparison_is_locked_until_both_are_complete():
    """Skipped once a real review has finished, which is the correct state."""
    markers = [reviewer_dir(name) / "COMPLETE" for name in ("codex", "claude")]
    if all(marker.is_file() for marker in markers):
        pytest.skip("both reviews are complete; the lock is correctly open")
    with pytest.raises(SsrError, match="locked until both COMPLETE"):
        require_both_complete()


def test_peeking_is_refused_before_both_are_complete():
    markers = [reviewer_dir(name) / "COMPLETE" for name in ("codex", "claude")]
    if all(marker.is_file() for marker in markers):
        pytest.skip("both reviews are complete; peeking is no longer a violation")
    with pytest.raises(SsrError, match="reviewer independence"):
        forbid_peeking("codex")
