"""Corpus marking, cross-platform packet content, and bundle exclusions.

These are the properties that let someone clone this repository on a
different machine and produce a review that means something.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from ssr.corpus import REHEARSAL, RESEARCH, CorpusStatus, classify, isolation_of
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
    """The local backend runs on the author's own machine and proves the
    harness only, so it can never carry a research corpus."""
    kind, reasons = classify([FakeEntry("BUG_a"), FakeEntry("BUG_b", backend="local")])
    assert kind == REHEARSAL
    assert any("BUG_b" in reason for reason in reasons)


def test_a_host_worktree_corpus_is_still_research():
    """Weaker isolation is a fidelity limitation, not a fake corpus. These
    bugs were executed against a real repository and a real test suite."""
    entries = [FakeEntry("BUG_a", backend="wsl"), FakeEntry("BUG_b", backend="wsl")]
    kind, reasons = classify(entries)
    assert kind == RESEARCH
    assert reasons == []
    assert isolation_of(entries)[0] == "HOST_WORKTREE"


def test_isolation_is_reported_separately_from_corpus_kind():
    assert isolation_of([FakeEntry("BUG_a")])[0] == "CONTAINER"
    assert isolation_of([FakeEntry("BUG_a"), FakeEntry("BUG_b", backend="wsl")])[0] == "MIXED"


def test_a_scripted_bug_is_a_rehearsal_whatever_the_backend():
    for backend in ("docker", "wsl", "local"):
        kind, _ = classify([FakeEntry("BUG_a", backend=backend, scripted=True)])
        assert kind == REHEARSAL


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
        environment_isolation="CONTAINER",
        note="n",
    )
    assert CorpusStatus(**status.to_dict()).is_research


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
        "prompts/",
        "metadata.json",
        "trajectory.jsonl",
        "pred_patch.diff",
    ):
        assert term in FORBIDDEN_IN_BUNDLE, f"{term} must never reach a reviewer bundle"

    # A bundle must not carry the generation library.
    for module in ("generation.py", "solving.py", "model.py", "agent_loop.py",
                   "exec_env.py", "swesmith_sampling.py", "packets.py", "swesmith.py"):
        assert module not in LIBRARY_MODULES, f"{module} must not be shipped to a reviewer"


def test_bundle_ships_only_the_review_format_config():
    """configs/ is otherwise hidden. review_formats.yaml has to travel: the
    reviewer's tooling needs to know which format that reviewer writes."""
    source = (REPO_ROOT_PATH / "scripts" / "make_review_bundle.py").read_text(encoding="utf-8")
    assert 'configs" / "review_formats.yaml"' in source
    for other in ("sampling.yaml", "generator.yaml", "solver.yaml"):
        assert f'"{other}"' not in source


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
        from ssr.review_formats import codec_for

        extension = codec_for(reviewer).extension
        assert f"reviews/{reviewer}/cases/SWESMITH_nnn{extension}" in text


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


def strip_serialisation(text: str) -> str:
    """Remove the parts that are allowed to differ: the fenced record
    examples and the sentence naming the format."""
    text = re.sub(r"```(?:json|yaml)\n.*?```", "<RECORD EXAMPLE>", text, flags=re.S)
    text = re.sub(r"You write \*\*[A-Z]+\*\*\.",
                  "You write <FORMAT>.", text)
    text = re.sub(r"One \*\*[A-Z]+\*\* file per case, at `[^`]+`:",
                  "One <FORMAT> file per case, at <PATH>:", text)
    return text


def test_briefs_are_otherwise_identical():
    """The two briefs differ in exactly two ways: the reviewer names, and the
    serialisation format. Any third divergence is drift."""
    codex = strip_serialisation(normalise_roles(brief("codex"), "codex", "claude"))
    claude = strip_serialisation(normalise_roles(brief("claude"), "claude", "codex"))
    assert codex == claude


def test_the_briefs_really_do_differ_before_that_is_stripped():
    """Guard against the normaliser above hiding a real difference."""
    assert normalise_roles(brief("codex"), "codex", "claude") !=         normalise_roles(brief("claude"), "claude", "codex")


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
        for evidence_id in ("BUG_DIFF", "CODE_CONTEXT_NN", "TEST_FAILURE_NN",
                            "SPECIFICATION", "REFERENCE_REPAIR"):
            assert evidence_id in text


# ----------------------------------------------------------------------
# the hand-off prompt in the README must stay usable
# ----------------------------------------------------------------------
def readme() -> str:
    return (REPO_ROOT_PATH / "README.md").read_text(encoding="utf-8")


def test_readme_carries_a_prompt_for_the_reviewer():
    text = readme()
    assert "## Running the blind reviews" in text
    for reviewer in ("codex", "claude"):
        assert f"scripts/check_review_ready.py --reviewer {reviewer}" in text
        assert f"scripts/validate_review_output.py --reviewer {reviewer} --finalise" in text
    # The two-branch isolation setup.
    assert "codex-review" in text and "claude-review" in text


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
    for forbidden in ("reviews/claude/", "reviews/codex/", "data/hidden/",
                      "data/population/", "analysis/", "archive/"):
        assert forbidden in text


def test_quickstart_points_at_the_prompts():
    text = (REPO_ROOT_PATH / "QUICKSTART.md").read_text(encoding="utf-8")
    assert "Running the blind reviews" in text and "README.md" in text
