"""Neutral packets, the leakage scan, and reviewer-output validation."""

import pytest

from ssr.packets import PacketBuilder, PacketSource, scan_body, scan_filenames, scan_metadata
from ssr.util import SsrError
from ssr.validate_review import validate_against_schema

DIFF = """\
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


def make_source(packet_id="SSR_001", **overrides) -> PacketSource:
    defaults = dict(
        packet_id=packet_id,
        repo_name="acme/widget",
        language="python",
        repo_commit="abc123",
        repo_size_bin="MEDIUM",
        bug_diff=DIFF,
        test_command="pytest tests/test_core.py -v",
        clean_counts={"passed": 8, "failed": 0, "errored": 0, "skipped": 0},
        bug_counts={"passed": 7, "failed": 1, "errored": 0, "skipped": 0},
        fail_to_pass=["tests/test_core.py::test_clamp_above"],
        oracle_outputs={"tests/test_core.py::test_clamp_above": "assert 50 == 10\nFAILED"},
        code_context={"src/core.py": "def clamp(value, low, high):\n    return value\n"},
    )
    defaults.update(overrides)
    return PacketSource(**defaults)


def test_packet_is_built_and_matches_the_schema(tmp_path):
    result = PacketBuilder(tmp_path).build(make_source())
    packet = result["packet"]
    validate_against_schema(packet, "review_packet")
    assert packet["packet_id"] == "SSR_001"
    assert packet["bug_diff"]["evidence_id"] == "BUG_DIFF"
    assert "ORACLE_TEST_01" in packet["evidence_ids"]
    assert "CODE_CONTEXT_01" in packet["evidence_ids"]


def test_packet_carries_no_generation_metadata(tmp_path):
    packet = PacketBuilder(tmp_path).build(make_source())["packet"]
    flat = str(packet).lower()
    for term in ("removal", "reversion", "second_order", "bug_order", "parent", "qwen", "solver"):
        assert term not in flat


def test_packet_file_names_are_neutral(tmp_path):
    files = PacketBuilder(tmp_path).build(make_source())["files"]
    for name in files:
        lowered = name.lower()
        assert "removal" not in lowered
        assert "second" not in lowered
        assert "weaken" not in lowered


def test_metadata_scan_catches_a_strategy_name():
    findings = scan_metadata({"repository": {"name": "swesmith/acme_removal"}})
    assert findings
    assert any(finding.term in ("removal", "swesmith") for finding in findings)


def test_filename_scan_catches_a_leak():
    assert scan_filenames(["second_order_diff.txt"])


def test_repository_derived_values_may_use_ordinary_words():
    """A project may own a test_removal.py or a solver module. Rejecting that
    packet would be a false positive, so those fields get harness terms only."""
    assert not scan_metadata(
        {
            "test_results": {"test_command": "pytest tests/test_removal.py -v"},
            "oracle_tests": [
                {"test_name": "tests/test_solver.py::test_reversion", "test_file": "tests/test_solver.py"}
            ],
            "code_context": [{"repo_path": "src/history_reversion.py"}],
        }
    )


def test_repository_derived_values_still_catch_harness_terms():
    findings = scan_metadata({"test_results": {"test_command": "swesmith run --all"}})
    assert findings
    assert findings[0].term == "swesmith"


def test_context_file_names_may_use_ordinary_words():
    assert not scan_filenames(["context/01_removal_utils.py"])
    assert scan_filenames(["context/01_swesmith_helper.py"])


def test_body_scan_ignores_ordinary_words():
    """Source legitimately says 'remove' and 'revert'; only harness vocabulary fires."""
    assert not scan_body("def remove_item(x):\n    return revert(x)\n", where="ctx")


def test_body_scan_catches_an_injection_comment():
    assert scan_body("# injected bug: drop the upper bound\n", where="ctx")


def test_a_leaking_packet_is_refused(tmp_path):
    source = make_source(repo_name="swesmith/acme_1776_widget")
    with pytest.raises(SsrError, match="leakage scan failed"):
        PacketBuilder(tmp_path).build(source)


def test_a_packet_needs_an_oracle_test(tmp_path):
    with pytest.raises(SsrError, match="at least one oracle test"):
        PacketBuilder(tmp_path).build(make_source(fail_to_pass=[], oracle_outputs={}))


def test_reviewer_question_is_identical_in_every_packet(tmp_path):
    builder = PacketBuilder(tmp_path)
    first = builder.build(make_source("SSR_001"))["packet"]
    second = builder.build(make_source("SSR_002"))["packet"]
    assert first["reviewer_question"] == second["reviewer_question"]


# ----------------------------------------------------------------------
def review(**overrides) -> dict:
    record = {
        "bug_id": "SSR_001",
        "failure_pattern": "incomplete_change_propagation",
        "pattern_confidence": "HIGH",
        "failure_scope": "CODE_STATE",
        "taxonomy_fit": "DIRECT",
        "supporting_evidence_ids": ["BUG_DIFF", "ORACLE_TEST_01"],
        "reasoning_summary": "The upper bound check was dropped in one place only.",
        "proposed_other_pattern": None,
    }
    record.update(overrides)
    return record


def test_valid_review_record():
    validate_against_schema(review(), "review_result")


def test_unassigned_is_rejected():
    with pytest.raises(SsrError):
        validate_against_schema(review(failure_pattern="UNASSIGNED"), "review_result")


def test_pr_outcome_field_is_rejected():
    with pytest.raises(SsrError):
        validate_against_schema(
            review(outcome_classification="TECHNICAL_FAILURE_EVIDENCE"), "review_result"
        )


def test_other_pattern_needs_a_description():
    with pytest.raises(SsrError):
        validate_against_schema(
            review(failure_pattern="OTHER_TECHNICAL_PATTERN", taxonomy_fit="OTHER"),
            "review_result",
        )
    validate_against_schema(
        review(
            failure_pattern="OTHER_TECHNICAL_PATTERN",
            taxonomy_fit="OTHER",
            proposed_other_pattern="silent numeric overflow on a widened type",
        ),
        "review_result",
    )


def test_a_defined_pattern_may_not_carry_a_proposed_other_pattern():
    with pytest.raises(SsrError):
        validate_against_schema(review(proposed_other_pattern="something"), "review_result")


def test_code_state_precedence_is_enforced():
    from ssr.validate_review import validate_result

    with pytest.raises(SsrError, match="code-state precedence"):
        validate_result(
            review(failure_pattern="vacuous_verification", failure_scope="BOTH"),
            check_packet=False,
        )


def test_a_process_label_alone_is_allowed():
    from ssr.validate_review import validate_result

    validate_result(
        review(failure_pattern="unverified_trial_and_error", failure_scope="REPAIR_PROCESS"),
        check_packet=False,
    )
