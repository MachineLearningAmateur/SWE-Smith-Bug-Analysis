"""Corpus marking, cross-platform packet content, and bundle exclusions.

These are the properties that let someone clone this repository on a
different machine and produce a review that means something.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from ssr.corpus import REHEARSAL, RESEARCH, CorpusStatus, classify
from ssr.packets import PacketBuilder, PacketSource, normalise_test_id, posix
from ssr.paths import REPO_ROOT

REPO_ROOT_PATH = Path(REPO_ROOT)


def load_script(name: str):
    """Import a scripts/*.py file. scripts/ is a directory of entry points,
    not a package, so it is loaded by path."""
    path = REPO_ROOT_PATH / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"ssr_script_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUNDLE = load_script("make_review_bundle.py")


class FakeEntry:
    def __init__(self, bug_id: str, backend: str = "docker", scripted: bool = False):
        self.bug_id = bug_id
        self.backend = backend
        self.scripted = scripted


# ----------------------------------------------------------------------
# corpus marking
# ----------------------------------------------------------------------
def test_a_docker_built_pool_is_a_research_corpus():
    kind, reasons = classify([FakeEntry("BUG_a"), FakeEntry("BUG_b")])
    assert kind == RESEARCH
    assert reasons == []


def test_one_local_backend_bug_makes_the_whole_corpus_a_rehearsal():
    kind, reasons = classify([FakeEntry("BUG_a"), FakeEntry("BUG_b", backend="local")])
    assert kind == REHEARSAL
    assert any("BUG_b" in reason for reason in reasons)


def test_a_scripted_model_makes_the_corpus_a_rehearsal():
    kind, reasons = classify([FakeEntry("BUG_a", scripted=True)])
    assert kind == REHEARSAL
    assert any("scripted" in reason for reason in reasons)


def test_rehearsal_status_says_not_to_report_it():
    from ssr.corpus import REHEARSAL_NOTE

    assert "not a research result" in REHEARSAL_NOTE.lower()
    assert "do not report" in REHEARSAL_NOTE.lower()


def test_status_dataclass_round_trips():
    status = CorpusStatus(
        corpus_kind=RESEARCH,
        packet_count=100,
        taxonomy_fingerprint="a" * 64,
        snapshot_manifest_sha256="b" * 64,
        review_manifest_sha256="c" * 64,
        built_at_utc="2026-08-30T00:00:00Z",
        harness_version="0.1.0",
        protocol_version="ssr-action-protocol/1",
        note="n",
    )
    assert CorpusStatus(**status.to_dict()).is_research


# ----------------------------------------------------------------------
# cross-platform packet content
# ----------------------------------------------------------------------
def test_posix_normalises_windows_separators():
    assert posix("tests\\test_core.py") == "tests/test_core.py"


def test_test_id_file_part_is_normalised():
    assert normalise_test_id("tests\\test_core.py::test_clamp") == "tests/test_core.py::test_clamp"


def test_a_parametrised_case_name_is_left_alone():
    """Only the part before :: is a path."""
    assert normalise_test_id("tests\\t.py::test_x[a\\b]") == "tests/t.py::test_x[a\\b]"


DIFF = """\
diff --git a/src/core.py b/src/core.py
--- a/src/core.py
+++ b/src/core.py
@@ -1,3 +1,2 @@
-    if value > high:
-        return high
     return value
"""


def build_packet(tmp_path, **overrides):
    defaults = dict(
        packet_id="SSR_001",
        repo_name="acme/widget",
        language="python",
        repo_commit="abc123",
        repo_size_bin="MEDIUM",
        bug_diff=DIFF,
        test_command="pytest tests/test_core.py -v",
        clean_counts={"passed": 8, "failed": 0, "errored": 0, "skipped": 0},
        bug_counts={"passed": 7, "failed": 1, "errored": 0, "skipped": 0},
        fail_to_pass=["tests\\test_core.py::test_clamp_above"],
        oracle_outputs={"tests\\test_core.py::test_clamp_above": "assert 50 == 10"},
        code_context={"src\\core.py": "def clamp(): pass\n"},
    )
    defaults.update(overrides)
    return PacketBuilder(tmp_path).build(PacketSource(**defaults))


def test_a_packet_built_with_windows_paths_is_stored_posix(tmp_path):
    packet = build_packet(tmp_path)["packet"]
    assert packet["oracle_tests"][0]["test_name"] == "tests/test_core.py::test_clamp_above"
    assert packet["oracle_tests"][0]["test_file"] == "tests/test_core.py"
    assert packet["test_results"]["newly_failing"] == ["tests/test_core.py::test_clamp_above"]
    assert packet["code_context"][0]["repo_path"] == "src/core.py"


def test_no_backslash_survives_into_packet_metadata(tmp_path):
    packet = build_packet(tmp_path)["packet"]
    flat = json.dumps(packet)
    assert "\\\\" not in flat


def test_packet_files_use_forward_slashes(tmp_path):
    files = build_packet(tmp_path)["files"]
    assert all("\\" not in name for name in files)


# ----------------------------------------------------------------------
# bundle exclusions
# ----------------------------------------------------------------------
def test_bundle_excludes_every_hidden_artifact_kind():
    FORBIDDEN_IN_BUNDLE, LIBRARY_MODULES = BUNDLE.FORBIDDEN_IN_BUNDLE, BUNDLE.LIBRARY_MODULES

    for term in (
        "data/sampling",
        "data/validated_pool",
        "data/generated_pool",
        "analysis/",
        "configs/",
        "prompts/",
        "metadata.json",
        "trajectory.jsonl",
        "pred_patch.diff",
    ):
        assert term in FORBIDDEN_IN_BUNDLE, f"{term} must never reach a reviewer bundle"

    # A bundle must not carry the generation library.
    for module in ("generation.py", "solving.py", "model.py", "agent_loop.py", "exec_env.py",
                   "sampling.py", "dedup.py", "pool.py", "packets.py"):
        assert module not in LIBRARY_MODULES, f"{module} must not be shipped to a reviewer"


def test_bundle_library_modules_all_exist():
    LIBRARY_MODULES = BUNDLE.LIBRARY_MODULES

    for module in LIBRARY_MODULES:
        assert (REPO_ROOT_PATH / "ssr" / module).is_file(), module


def test_bundle_ships_only_the_two_review_scripts():
    REVIEW_SCRIPTS = BUNDLE.REVIEW_SCRIPTS

    assert set(REVIEW_SCRIPTS) == {"check_review_ready.py", "validate_review_output.py"}
    for script in REVIEW_SCRIPTS:
        assert (REPO_ROOT_PATH / "scripts" / script).is_file()


# ----------------------------------------------------------------------
# the review path must not need the generation dependencies
# ----------------------------------------------------------------------
def test_review_path_imports_without_requests():
    """A reviewer installs requirements-review.txt only, which has no requests."""
    code = (
        "import sys; "
        "sys.path.insert(0, r'" + str(REPO_ROOT_PATH) + "'); "
        "import ssr.review_workflow, ssr.validate_review, ssr.taxonomy, ssr.corpus; "
        "print('requests' in sys.modules)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "False"


def test_requirements_review_has_no_generation_dependency():
    text = (REPO_ROOT_PATH / "requirements-review.txt").read_text(encoding="utf-8")
    assert "requests" not in text
    assert "pyyaml" in text
    assert "jsonschema" in text


def test_review_scripts_do_not_import_the_generation_library():
    """check_review_ready and validate_review_output must stay dependency-light."""
    banned = ("ssr.exec_env", "ssr.model", "ssr.agent_loop", "ssr.generation", "ssr.solving",
              "ssr.registry", "ssr.pool", "ssr.sampling")
    for script in ("check_review_ready.py", "validate_review_output.py"):
        text = (REPO_ROOT_PATH / "scripts" / script).read_text(encoding="utf-8")
        for module in banned:
            assert f"from {module}" not in text and f"import {module}" not in text, (
                f"{script} must not import {module}: a reviewer bundle does not ship it"
            )


# ----------------------------------------------------------------------
# the two reviewer briefs are mirror images and must never cross over
# ----------------------------------------------------------------------
BRIEFS = {"codex": "AGENTS.md", "claude": "CLAUDE.md"}


def brief(reviewer: str) -> str:
    return (REPO_ROOT_PATH / BRIEFS[reviewer]).read_text(encoding="utf-8")


def test_each_brief_points_at_its_own_review_directory():
    for reviewer, other in (("codex", "claude"), ("claude", "codex")):
        text = brief(reviewer)
        assert f"**Only `reviews/{reviewer}/**`.**" in text
        assert f"--reviewer {reviewer}" in text
        assert f"--reviewer {other}" not in text
        assert f"reviews/{reviewer}/cases/SSR_nnn.json" in text


def test_no_brief_tells_a_reviewer_to_avoid_itself():
    """A brief that names its own reviewer as the one to avoid is nonsense
    and, worse, reads as permission to open the other directory."""
    for reviewer, other in (("codex", "Claude"), ("claude", "Codex")):
        text = brief(reviewer)
        own = reviewer.capitalize()
        for sentence in (
            f"ever seeing {own}'s answers",
            f"compare yourself with {own}",
            f"{own}'s work. Not before",
        ):
            assert sentence not in text, f"{BRIEFS[reviewer]} refers to itself as the other reviewer"
        assert f"ever seeing {other}'s answers" in text
        assert f"compare yourself with {other}" in text


def normalise_roles(text: str, own: str, other: str) -> str:
    """Replace each reviewer name with its ROLE, not with one shared token.

    Both briefs then read identically if, and only if, every name sits in the
    right role. A brief that swapped two names would still differ here.
    """
    for name, marker in ((own, "<SELF>"), (other, "<OTHER>")):
        text = text.replace(name, marker).replace(name.capitalize(), "<CAP_" + marker[1:])
    return text.replace("AGENTS.md", "<BRIEF>").replace("CLAUDE.md", "<BRIEF>")


def test_briefs_are_otherwise_identical():
    """Only the reviewer names differ. Any other divergence is drift."""
    codex = normalise_roles(brief("codex"), "codex", "claude")
    claude = normalise_roles(brief("claude"), "claude", "codex")
    assert codex == claude


def test_both_briefs_open_with_the_preflight_command():
    for reviewer in BRIEFS:
        text = brief(reviewer)
        assert "## Start here" in text
        assert "requirements-review.txt" in text
        assert f"check_review_ready.py --reviewer {reviewer}" in text
        assert "REHEARSAL" in text


# ----------------------------------------------------------------------
# the label definitions inlined in the briefs must match the frozen file
# ----------------------------------------------------------------------
import re  # noqa: E402

from ssr.taxonomy import FINE_LABELS  # noqa: E402

TABLE_ROW = re.compile(r"^\| `?([A-Za-z_]+)`? \| (.+?) \|$", re.MULTILINE)


def taxonomy_definitions() -> dict:
    text = (REPO_ROOT_PATH / "taxonomy" / "frozen_failure_taxonomy_v1.md").read_text(encoding="utf-8")
    return {name: definition.strip() for name, definition in TABLE_ROW.findall(text)}


def brief_definitions(reviewer: str) -> dict:
    return {name: definition.strip() for name, definition in TABLE_ROW.findall(brief(reviewer))}


def test_every_ssr_label_is_defined_in_both_briefs():
    for reviewer in BRIEFS:
        found = brief_definitions(reviewer)
        for label in FINE_LABELS:
            assert label in found, f"{BRIEFS[reviewer]} does not define {label}"


def test_brief_definitions_are_verbatim_from_the_frozen_taxonomy():
    """The briefs quote the rubric. A paraphrase would change the study."""
    frozen = taxonomy_definitions()
    for reviewer in BRIEFS:
        found = brief_definitions(reviewer)
        for label in FINE_LABELS:
            assert found[label] == frozen[label], (
                f"{BRIEFS[reviewer]} has drifted from the frozen definition of {label}"
            )


def test_briefs_do_not_offer_unassigned_as_a_label():
    for reviewer in BRIEFS:
        found = brief_definitions(reviewer)
        assert "UNASSIGNED" not in found
        assert "not** available here" in brief(reviewer)


def test_briefs_document_the_scope_and_fit_values():
    from ssr.taxonomy import SCOPES, TAXONOMY_FITS

    for reviewer in BRIEFS:
        text = brief(reviewer)
        for value in list(SCOPES) + list(TAXONOMY_FITS):
            assert f"`{value}`" in text, f"{BRIEFS[reviewer]} does not document {value}"


def test_briefs_list_the_packet_evidence_ids():
    for reviewer in BRIEFS:
        text = brief(reviewer)
        for evidence_id in ("BUG_DIFF", "CODE_CONTEXT_NN", "ORACLE_TEST_NN", "TEST_RESULTS"):
            assert evidence_id in text


# ----------------------------------------------------------------------
# the hand-off prompt in the README must stay usable
# ----------------------------------------------------------------------
def readme() -> str:
    return (REPO_ROOT_PATH / "README.md").read_text(encoding="utf-8")


def test_readme_carries_a_prompt_for_the_reviewer():
    text = readme()
    assert "## The prompt to hand the reviewer" in text
    for command in (
        "scripts/check_review_ready.py --reviewer <claude|codex>",
        "scripts/validate_review_output.py --reviewer <claude|codex> --finalise",
    ):
        assert command in text, f"the hand-off prompt no longer names {command}"


def test_the_prompt_states_every_rule_that_can_void_a_review():
    text = readme()
    for rule in (
        "fine-grained label only",
        "code-state precedence",
        "UNASSIGNED does not exist here",
        "Cite only evidence IDs",
        "not a transcript",
        "Write nothing outside",
    ):
        assert rule in text, f"the hand-off prompt no longer states: {rule}"


def test_the_prompt_names_the_directories_a_reviewer_must_not_open():
    text = readme()
    for forbidden in ("data/sampling/", "analysis/", "metadata.json", "trajectory.jsonl"):
        assert forbidden in text


def test_quickstart_points_at_the_prompt():
    text = (REPO_ROOT_PATH / "QUICKSTART.md").read_text(encoding="utf-8")
    assert "The prompt to" in text and "README.md" in text
