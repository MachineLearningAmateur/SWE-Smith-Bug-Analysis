"""The two SWE-smith semantics that would silently invert this study.

Both were established by reconstruction, not assumption
(`scripts/verify_swesmith_semantics.py`, five instances, five methods). They
are locked here because either one, reintroduced the SWE-bench way round,
produces a corpus that looks fine and means the opposite.
"""

import csv
import json
import re
from pathlib import Path

import pytest

from ssr.packets import METADATA_FORBIDDEN, body_terms, scan_body, scan_filenames, scan_metadata
from ssr.paths import DATA, REPO_ROOT, REVIEW_PACKETS
from ssr.swesmith import generation_method, generation_method_raw, method_family, upstream_repo
from ssr.swesmith_sampling import assert_neutral, largest_remainder
from ssr.util import SsrError

PACKETS_MODULE = (REPO_ROOT / "ssr" / "packets.py").read_text(encoding="utf-8")


# ----------------------------------------------------------------------
# 1. the clean state is the bug commit's parent, never base_commit
# ----------------------------------------------------------------------
def test_reconstruction_uses_the_bug_commit_parent_as_the_clean_state():
    assert 'parent = _git("rev-parse", f"{bug_commit}^", cwd=clone).stdout.strip()' in PACKETS_MODULE
    assert 'BUG_COMMIT_SUBJECT = "Bug Patch"' in PACKETS_MODULE


def test_reconstruction_never_reads_base_commit():
    """base_commit has a different tree from the bug's parent on every
    instance checked. Reading it would diff against the wrong code."""
    # Skip the module docstring, which mentions the field precisely to warn
    # about it, and check the executable body.
    body = PACKETS_MODULE.split('"""', 2)[-1]
    assert 'task["base_commit"]' not in body
    assert '"base_commit"' not in body


def test_the_clean_state_rule_is_documented_where_someone_would_look():
    assert "It is NOT the" in PACKETS_MODULE and "base_commit" in PACKETS_MODULE
    doc = (REPO_ROOT / "docs" / "swesmith_field_semantics.md").read_text(encoding="utf-8")
    assert "NOT the clean state" in doc


# ----------------------------------------------------------------------
# 2. `patch` is the bug injection; the repair is its reverse
# ----------------------------------------------------------------------
def test_the_reference_repair_is_the_reverse_of_the_bug_diff():
    assert '_git("diff", bug_commit, parent, cwd=clone)' in PACKETS_MODULE, (
        "the reference repair must be the reverse direction: bug -> clean"
    )


def test_the_bug_diff_is_the_dataset_patch():
    assert "bug_diff=task[\"patch\"]" in PACKETS_MODULE


def test_packets_describe_the_patch_as_the_bug_not_a_repair():
    packet = json.loads((REVIEW_PACKETS / "SWESMITH_001" / "packet.json").read_text(encoding="utf-8"))
    assert "INTRODUCED" in packet["bug_diff"]["description"].upper() or \
           "introduced the defect" in packet["bug_diff"]["description"]
    assert "reverse" in packet["reference_repair"]["description"].lower()
    assert "restores" in packet["reference_repair"]["description"].lower()


def test_briefs_warn_which_direction_each_diff_runs():
    for name in ("AGENTS.md", "CLAUDE.md"):
        text = (REPO_ROOT / name).read_text(encoding="utf-8")
        assert "is the bug, not a repair" in text
        assert "exact reverse" in text


# ----------------------------------------------------------------------
# generation-method parsing
# ----------------------------------------------------------------------
@pytest.mark.parametrize(
    "instance_id,method,family",
    [
        ("Cog-Creators__Red-DiscordBot.33e0eac7.lm_rewrite__1xt89hhu", "lm_rewrite", "llm"),
        ("conan-io__conan.86f29e13.func_pm_remove_assign__leq9zkie", "func_pm_remove_assign", "procedural"),
        ("getmoto__moto.694ce1f4.pr_7234", "pr_mirror", "mirror"),
        ("pallets__flask.bc098406.combine_file__3s67h7m2", "combine_file", "combine"),
    ],
)
def test_generation_method_parsing(instance_id, method, family):
    assert generation_method(instance_id) == method
    assert method_family(generation_method(instance_id)) == family


def test_pull_request_tokens_normalise_but_the_raw_token_survives():
    """Left raw, every mirrored PR is its own one-member 'method'."""
    assert generation_method("a__b.c.pr_7234") == "pr_mirror"
    assert generation_method_raw("a__b.c.pr_7234") == "pr_7234"


def test_upstream_repo_drops_the_mirror_naming():
    assert upstream_repo("Cog-Creators__Red-DiscordBot.33e0eac7.lm_rewrite__x1y2z3") == \
        "Cog-Creators/Red-DiscordBot"


# ----------------------------------------------------------------------
# leakage
# ----------------------------------------------------------------------
def test_no_packet_names_its_generation_method_or_instance():
    hidden = {}
    with open(DATA / "hidden" / "sample_metadata.csv", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            hidden[row["case_id"]] = row
    for case_id, row in sorted(hidden.items()):
        blob = (REVIEW_PACKETS / case_id / "packet.json").read_text(encoding="utf-8")
        for secret in (row["instance_id"], row["repo"], row["generation_method_raw"]):
            assert secret.lower() not in blob.lower(), f"{case_id} leaks {secret!r}"


def test_the_case_id_is_allowed_but_method_tokens_are_not():
    assert not scan_metadata({"case_id": "SWESMITH_042"}, allow=("SWESMITH_042",))
    assert scan_metadata({"note": "built by lm_rewrite"})


def test_body_scan_targets_this_task_not_english_words():
    terms = body_terms("a__b.c.lm_rewrite__zz", "swesmith/a__b.c")
    assert not scan_body("instance_id = 3  # a normal variable\n", where="x", terms=terms)
    assert scan_body("see a__b.c.lm_rewrite__zz for details", where="x", terms=terms)


def test_filenames_never_carry_a_method_token():
    assert scan_filenames(["lm_rewrite_notes.txt"])
    assert not scan_filenames(["SWESMITH_001"], allow=("SWESMITH_001",))


# ----------------------------------------------------------------------
# sampling
# ----------------------------------------------------------------------
def test_largest_remainder_sums_to_the_target_and_tracks_shares():
    counts = {"a": 1529, "b": 1438, "c": 1161, "d": 79}
    allocation = largest_remainder(counts, 100)
    assert sum(allocation.values()) == 100
    total = sum(counts.values())
    for name, value in allocation.items():
        assert abs(value / 100 - counts[name] / total) < 0.01


def test_sampling_refuses_a_taxonomy_field():
    with pytest.raises(SsrError, match="non-neutral"):
        assert_neutral([{"instance_id": "x", "failure_pattern": "y"}])


def test_method_family_is_not_mistaken_for_a_taxonomy_family():
    """`method_family` is the neutral stratum this sampler exists to use."""
    assert_neutral([{"instance_id": "x", "method_family": "procedural"}])


# ----------------------------------------------------------------------
# the frozen sample
# ----------------------------------------------------------------------
def test_exactly_one_hundred_frozen_packets():
    packets = sorted(p.name for p in REVIEW_PACKETS.iterdir() if p.is_dir() and p.name.startswith("SWESMITH_"))
    assert len(packets) == 100
    assert packets[0] == "SWESMITH_001" and packets[-1] == "SWESMITH_100"


def test_every_packet_matches_the_snapshot_manifest():
    from ssr.util import sha256_file

    manifest = json.loads((DATA / "review_snapshot_manifest.json").read_text(encoding="utf-8"))
    assert manifest["packet_count"] == 100
    for entry in manifest["packets"]:
        directory = REVIEW_PACKETS / entry["case_id"]
        for relative, expected in entry["files"].items():
            assert sha256_file(directory / relative) == expected, f"{entry['case_id']}/{relative}"


def test_the_reviewer_manifest_carries_no_generation_metadata():
    with open(DATA / "review_manifest.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 100
    for field in rows[0]:
        assert field not in ("generation_method", "method_family", "instance_id", "trajectory_count")
