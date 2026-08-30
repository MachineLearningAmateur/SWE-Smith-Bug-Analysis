"""The frozen taxonomy must stay frozen, and the two injector prompts must
not drift apart in the sections they share."""

import json

import pytest

from ssr.generation import load_prompt_sections
from ssr.paths import PROMPTS, TAXONOMY_PROVENANCE
from ssr.taxonomy import (
    CODE_STATE_LABELS,
    FINE_LABELS,
    HANDOFF_MAPPING_SHA256,
    PROCESS_LABELS,
    families,
    family_for,
    load_mapping,
    verify_provenance,
)


def test_provenance_verifies():
    record = verify_provenance()
    assert record["taxonomy_version"] == "aidev_failure_taxonomy_v1"
    assert record["verified_mapping_sha256"] == HANDOFF_MAPPING_SHA256


def test_provenance_records_the_handoff_hash():
    record = json.loads(TAXONOMY_PROVENANCE.read_text(encoding="utf-8"))
    mapping = next(item for item in record["artifacts"] if item["role"] == "family_mapping")
    assert mapping["sha256"] == HANDOFF_MAPPING_SHA256
    assert mapping["handoff_hash_match"] is True
    assert record["import_rules_applied"]["definitions_rewritten"] is False
    assert record["import_rules_applied"]["categories_merged_or_split"] is False


def test_mapping_covers_every_label():
    mapping = load_mapping()
    assert set(mapping) == set(FINE_LABELS)


def test_repository_understanding_family_membership():
    """The one adopted merge, exactly as frozen."""
    for label in (
        "false_premise_about_existing_code",
        "misdiagnosed_root_cause",
        "masked_symptom_instead_of_fixing",
    ):
        assert family_for(label) == "REPOSITORY_UNDERSTANDING"


def test_contract_and_constraint_stayed_separate():
    """The proposed CONTRACT_VIOLATION merge was dropped at freeze."""
    assert family_for("broke_existing_contract_or_behavior") == "BROKEN_CONTRACT"
    assert family_for("violated_project_constraint_or_convention") == "CONSTRAINT_VIOLATION"


def test_expected_families():
    assert set(families()) == {
        "REPOSITORY_UNDERSTANDING",
        "BROKEN_CONTRACT",
        "CONSTRAINT_VIOLATION",
        "INCOMPLETE_PROPAGATION",
        "VACUOUS_VERIFICATION",
        "UNVERIFIED_TRIAL_AND_ERROR",
        "SOLUTION_SHAPE",
        "BASELINE_STATE",
        "OTHER",
    }


def test_unassigned_is_not_available_to_ssr_reviewers():
    """Every SSR case is an execution-validated technical bug state, so the
    non-technical escape hatch cannot apply."""
    assert "UNASSIGNED" not in FINE_LABELS


def test_process_and_code_state_labels_partition():
    assert set(PROCESS_LABELS) | set(CODE_STATE_LABELS) == set(FINE_LABELS)
    assert not set(PROCESS_LABELS) & set(CODE_STATE_LABELS)


def test_unknown_label_is_rejected():
    with pytest.raises(Exception):
        family_for("not_a_real_label")


# ----------------------------------------------------------------------
SHARED_SECTIONS = ("SYSTEM", "DISCOVER", "WEAKEN")


def test_injector_prompts_share_their_common_sections():
    removal = load_prompt_sections(PROMPTS / "injector_removal.md")
    reversion = load_prompt_sections(PROMPTS / "injector_history_reversion.md")
    for name in SHARED_SECTIONS:
        assert removal[name] == reversion[name], f"the {name} section has drifted apart"


def test_inject_sections_differ():
    removal = load_prompt_sections(PROMPTS / "injector_removal.md")
    reversion = load_prompt_sections(PROMPTS / "injector_history_reversion.md")
    assert removal["INJECT"] != reversion["INJECT"]


def test_reversion_prompt_forbids_checkout_and_revert():
    reversion = load_prompt_sections(PROMPTS / "injector_history_reversion.md")
    assert "Do NOT check out an old commit" in reversion["INJECT"]
    assert "git revert" in reversion["INJECT"]


def test_weaken_section_forbids_source_edits():
    removal = load_prompt_sections(PROMPTS / "injector_removal.md")
    assert "touching any non-test source file" in removal["WEAKEN"]


def test_injector_is_not_told_the_test_command():
    removal = load_prompt_sections(PROMPTS / "injector_removal.md")
    assert "Find that out yourself" in removal["SYSTEM"]
