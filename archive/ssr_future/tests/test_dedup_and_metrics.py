"""Deduplication signals and objective patch metrics."""

from ssr.dedup import BugRecord, changed_files, deduplicate, hunk_signature, normalise_diff
from ssr.metrics import compute_patch_metrics, historical_reversion_similarity

DIFF_A = """\
diff --git a/src/core.py b/src/core.py
index 1111111..2222222 100644
--- a/src/core.py
+++ b/src/core.py
@@ -10,7 +10,6 @@ def clamp(value, low, high):
     if value < low:
         return low
-    if value > high:
-        return high
     return value
"""

# Same change, different blob hashes and different line numbers.
DIFF_A_MOVED = """\
diff --git a/src/core.py b/src/core.py
index 9999999..8888888 100644
--- a/src/core.py
+++ b/src/core.py
@@ -42,7 +42,6 @@ def clamp(value, low, high):
     if value < low:
         return low
-    if value > high:
-        return high
     return value
"""

DIFF_B = """\
diff --git a/src/other.py b/src/other.py
index 3333333..4444444 100644
--- a/src/other.py
+++ b/src/other.py
@@ -1,3 +1,3 @@ def total(values):
-    return sum(values)
+    return sum(values[1:])
"""


def record(bug_id: str, diff: str, **kwargs) -> BugRecord:
    return BugRecord(
        bug_id=bug_id,
        diff_text=diff,
        source_repo=kwargs.pop("repo", "acme/widget"),
        source_commit=kwargs.pop("commit", "abc123"),
        bug_order=kwargs.pop("bug_order", 1),
        **kwargs,
    )


def test_exact_duplicate_detected():
    result = deduplicate([record("BUG_a", DIFF_A), record("BUG_b", DIFF_A)])
    assert result.kept == ["BUG_a"]
    assert result.excluded["BUG_b"]["signal"] == "EXACT_DIFF"
    assert result.excluded["BUG_b"]["duplicate_of"] == "BUG_a"


def test_normalised_duplicate_survives_line_number_and_blob_changes():
    result = deduplicate([record("BUG_a", DIFF_A), record("BUG_b", DIFF_A_MOVED)])
    assert result.excluded["BUG_b"]["signal"] == "NORMALISED_DIFF"


def test_distinct_bugs_are_both_kept():
    result = deduplicate([record("BUG_a", DIFF_A), record("BUG_b", DIFF_B)])
    assert result.kept == ["BUG_a", "BUG_b"]
    assert not result.excluded


def test_identical_tree_on_the_same_commit():
    left = record("BUG_a", DIFF_A, buggy_tree_hash="tree1")
    right = record("BUG_b", DIFF_B, buggy_tree_hash="tree1")
    result = deduplicate([left, right])
    assert result.excluded["BUG_b"]["signal"] == "IDENTICAL_TREE"


def test_duplicate_second_order_states():
    left = BugRecord("BUG_a", DIFF_A, "acme/widget", "abc", 2, parent_bug_id="BUG_p", repair_patch=DIFF_B)
    right = BugRecord("BUG_b", DIFF_B, "acme/widget", "abc", 2, parent_bug_id="BUG_p", repair_patch=DIFF_B)
    result = deduplicate([left, right])
    assert result.excluded["BUG_b"]["signal"] == "DUPLICATE_SECOND_ORDER"


def test_same_reverted_commit():
    left = record("BUG_a", DIFF_A, reverted_commits=["deadbeef"])
    right = record("BUG_b", DIFF_B, reverted_commits=["deadbeef"])
    result = deduplicate([left, right])
    assert result.excluded["BUG_b"]["signal"] == "SAME_REVERTED_COMMIT"


def test_survivor_is_the_lowest_id_whatever_the_input_order():
    forward = deduplicate([record("BUG_a", DIFF_A), record("BUG_b", DIFF_A)])
    backward = deduplicate([record("BUG_b", DIFF_A), record("BUG_a", DIFF_A)])
    assert forward.kept == backward.kept == ["BUG_a"]


def test_different_repositories_are_not_hunk_duplicates():
    left = record("BUG_a", DIFF_A, repo="acme/widget")
    right = record("BUG_b", DIFF_A_MOVED, repo="other/project")
    result = deduplicate([left, right])
    # The normalised diffs still match, which is correct: the change is
    # identical. The hunk signal is what is repository-scoped.
    assert result.excluded["BUG_b"]["signal"] == "NORMALISED_DIFF"


def test_normalise_diff_drops_index_and_hunk_noise():
    assert normalise_diff(DIFF_A) == normalise_diff(DIFF_A_MOVED)


def test_changed_files_and_hunk_signature():
    assert changed_files(DIFF_A) == ["src/core.py"]
    assert "clamp" in hunk_signature(DIFF_A)


# ----------------------------------------------------------------------
def test_patch_metrics_basic_counts():
    metrics = compute_patch_metrics("BUG_a", DIFF_A)
    assert metrics.files_changed == 1
    assert metrics.lines_added == 0
    assert metrics.lines_deleted == 2
    assert metrics.add_delete_ratio == 0.0
    assert metrics.cross_file_edit is False
    assert metrics.source_files_edited == 1
    assert metrics.test_files_edited == 0


def test_patch_metrics_identifiers():
    metrics = compute_patch_metrics("BUG_b", DIFF_B)
    assert metrics.lines_added == 1
    assert metrics.lines_deleted == 1
    assert metrics.call_references_removed + metrics.call_references_introduced >= 0


def test_test_edits_are_counted_separately():
    diff = DIFF_A.replace("src/core.py", "tests/test_core.py")
    metrics = compute_patch_metrics("BUG_c", diff)
    assert metrics.test_files_edited == 1
    assert metrics.source_files_edited == 0


def test_config_edits_are_counted():
    diff = DIFF_A.replace("src/core.py", "pyproject.toml")
    assert compute_patch_metrics("BUG_d", diff).config_or_dependency_edits == 1


def test_history_similarity_scores_a_reversal_high():
    forward = """\
diff --git a/src/core.py b/src/core.py
@@ -10,5 +10,7 @@
+    if value > high:
+        return high
"""
    score = historical_reversion_similarity(DIFF_A, [forward])
    assert score is not None and score > 0.9


def test_history_similarity_scores_an_unrelated_commit_low():
    unrelated = """\
diff --git a/docs/readme.md b/docs/readme.md
@@ -1,2 +1,3 @@
+Some documentation about the project and its many features.
"""
    score = historical_reversion_similarity(DIFF_A, [unrelated])
    assert score is not None and score < 0.5


def test_history_similarity_without_history_is_none():
    assert historical_reversion_similarity(DIFF_A, []) is None
