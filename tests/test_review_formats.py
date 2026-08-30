"""Two file formats, one semantic schema.

The whole point of per-reviewer formats is that they differ on disk and agree
in meaning. Both halves of that are tested here: every codec round-trips
losslessly, every codec yields the same dict from the same record, and the
same record validates against the one schema whichever codec wrote it.
"""

import pytest

from ssr.paths import REPO_ROOT, REVIEWERS
from ssr.review_formats import (
    CODECS,
    FIELD_ORDER,
    JsonCodec,
    MarkdownCodec,
    YamlCodec,
    codec_for,
    format_summary,
    ordered,
)
from ssr.util import SsrError
from ssr.validate_review import validate_against_schema

RECORD = {
    "case_id": "SWESMITH_001",
    "failure_pattern": "incomplete_change_propagation",
    "pattern_confidence": "HIGH",
    "failure_scope": "CODE_STATE",
    "taxonomy_fit": "DIRECT",
    "supporting_evidence_ids": ["BUG_DIFF", "TEST_FAILURE_01"],
    "reasoning_summary": "Concise evidence-based explanation of the defect.",
    "proposed_other_pattern": None,
}

OTHER_RECORD = {
    **RECORD,
    "case_id": "SWESMITH_100",
    "failure_pattern": "OTHER_TECHNICAL_PATTERN",
    "taxonomy_fit": "OTHER",
    "pattern_confidence": "LOW",
    "proposed_other_pattern": "silent numeric overflow on a widened type",
}


@pytest.mark.parametrize("codec", sorted(CODECS.values(), key=lambda c: c.name), ids=lambda c: c.name)
@pytest.mark.parametrize("record", [RECORD, OTHER_RECORD], ids=["plain", "other_pattern"])
def test_every_codec_round_trips_losslessly(codec, record):
    assert codec.load(codec.dump(record)) == record


@pytest.mark.parametrize("record", [RECORD, OTHER_RECORD], ids=["plain", "other_pattern"])
def test_every_codec_yields_the_same_record(record):
    """Different bytes, identical meaning."""
    loaded = [codec.load(codec.dump(record)) for codec in CODECS.values()]
    assert all(item == loaded[0] for item in loaded)


@pytest.mark.parametrize("record", [RECORD, OTHER_RECORD], ids=["plain", "other_pattern"])
def test_every_codec_produces_a_schema_valid_record(record):
    for codec in CODECS.values():
        validate_against_schema(codec.load(codec.dump(record)), "review_result",
                                label=f"{codec.name} record")


def test_the_formats_actually_differ_on_disk():
    """If two reviewers wrote identical bytes the separation would be cosmetic."""
    rendered = {codec.name: codec.dump(RECORD) for codec in CODECS.values()}
    assert len(set(rendered.values())) == len(rendered)


def test_each_reviewer_has_its_own_format():
    formats = format_summary()
    assert set(formats) >= set(REVIEWERS)
    assert formats["codex"] == "json", "the Codex brief specifies JSON"
    assert len(set(formats[r] for r in REVIEWERS)) == len(REVIEWERS), (
        "the two reviewers must not share a format"
    )


def test_filenames_follow_the_codec():
    assert codec_for("codex").filename("SWESMITH_007") == "SWESMITH_007.json"
    assert codec_for("claude").filename("SWESMITH_007").startswith("SWESMITH_007.")
    for reviewer in REVIEWERS:
        codec = codec_for(reviewer)
        assert codec.case_id_of(codec.filename("SWESMITH_042")) == "SWESMITH_042"
        assert codec.glob().startswith("SWESMITH_*")


def test_field_order_is_canonical_and_complete():
    assert list(ordered(RECORD)) == list(FIELD_ORDER)
    required = set(validate_against_schema.__module__ and FIELD_ORDER)
    assert "case_id" in required and "proposed_other_pattern" in required


def test_json_codec_matches_the_format_the_brief_shows():
    text = JsonCodec().dump(RECORD)
    assert text.startswith("{\n") and text.endswith("}\n")
    assert '"case_id": "SWESMITH_001"' in text
    assert text.index('"case_id"') < text.index('"failure_pattern"')


def test_yaml_codec_is_block_style_not_inline():
    text = YamlCodec().dump(RECORD)
    assert "case_id: SWESMITH_001" in text
    assert "- BUG_DIFF" in text, "evidence should be a block sequence, not [a, b]"
    assert "{" not in text


def test_markdown_frontmatter_is_the_record_and_the_body_is_derived():
    text = MarkdownCodec().dump(RECORD)
    assert text.startswith("---\n")
    assert "# SWESMITH_001" in text and "## Reasoning" in text
    # The body is rendered, never parsed, so it cannot disagree with the record.
    assert MarkdownCodec().load(text) == RECORD


@pytest.mark.parametrize("codec", sorted(CODECS.values(), key=lambda c: c.name), ids=lambda c: c.name)
def test_a_malformed_file_reports_which_format_it_failed(codec):
    with pytest.raises(SsrError):
        codec.load("this is not a review record at all: [unclosed")


def test_an_unknown_format_is_refused():
    import ssr.review_formats as fmt

    original = fmt._configured_formats
    fmt._configured_formats = lambda: {"codex": "parquet"}
    try:
        with pytest.raises(SsrError, match="unknown review format"):
            codec_for("codex")
    finally:
        fmt._configured_formats = original


def test_the_results_file_stays_json_lines_for_both():
    """The sealed interchange artifact must be identical in shape, or the
    agreement analysis cannot read both sides the same way."""
    text = (REPO_ROOT / "configs" / "review_formats.yaml").read_text(encoding="utf-8")
    assert "results_file_format: jsonl" in text
    workflow = (REPO_ROOT / "ssr" / "review_workflow.py").read_text(encoding="utf-8")
    assert "canonical_json(record)" in workflow


def test_both_briefs_show_their_own_format_and_not_the_other():
    briefs = {"codex": "AGENTS.md", "claude": "CLAUDE.md"}
    for reviewer, filename in briefs.items():
        text = (REPO_ROOT / filename).read_text(encoding="utf-8")
        own = codec_for(reviewer)
        other = codec_for(next(r for r in REVIEWERS if r != reviewer))
        assert f"SWESMITH_nnn{own.extension}" in text, f"{filename} does not show its own format"
        assert f"SWESMITH_nnn{other.extension}" not in text, (
            f"{filename} shows the other reviewer's format"
        )


# ----------------------------------------------------------------------
# the command-line path, per reviewer
# ----------------------------------------------------------------------
# The codec tests above check the codecs in isolation. They did not catch a
# validator that read every case file as JSON, because that bug lives in the
# script, not the codec. These tests run the real command for BOTH reviewers.
def _write_case(reviewer: str, case_id: str, cases_dir) -> None:
    from ssr.review_formats import codec_for

    codec = codec_for(reviewer)
    record = dict(RECORD, case_id=case_id)
    (cases_dir / codec.filename(case_id)).write_text(codec.dump(record), encoding="utf-8", newline="\n")


@pytest.mark.parametrize("reviewer", sorted(REVIEWERS))
def test_validate_one_case_works_for_each_reviewer(reviewer, tmp_path):
    """Regression: this path used to read every case file as JSON, so it
    failed for whichever reviewer did not write JSON."""
    import os
    import subprocess
    import sys

    from ssr.review_formats import codec_for

    cases = tmp_path / reviewer / "cases"
    cases.mkdir(parents=True)
    _write_case(reviewer, "SWESMITH_001", cases)

    env = dict(os.environ, SSR_REVIEWS_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "scripts/validate_review_output.py",
         "--reviewer", reviewer, "--case", "SWESMITH_001"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, (
        f"validating a {codec_for(reviewer).name} case failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "SWESMITH_001" in result.stdout


@pytest.mark.parametrize("reviewer", sorted(REVIEWERS))
def test_progress_counts_cases_in_that_reviewers_format(reviewer, tmp_path):
    import os
    import subprocess
    import sys

    cases = tmp_path / reviewer / "cases"
    cases.mkdir(parents=True)
    for index in (1, 2, 3):
        _write_case(reviewer, f"SWESMITH_{index:03d}", cases)

    env = dict(os.environ, SSR_REVIEWS_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "scripts/validate_review_output.py", "--reviewer", reviewer],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"validated_cases": 3' in result.stdout, result.stdout
    assert '"missing": 97' in result.stdout, result.stdout


@pytest.mark.parametrize("reviewer", sorted(REVIEWERS))
def test_a_case_in_the_wrong_format_is_not_silently_counted(reviewer, tmp_path):
    """A file with the other reviewer's extension must not be picked up."""
    import os
    import subprocess
    import sys

    from ssr.review_formats import codec_for

    other = next(r for r in REVIEWERS if r != reviewer)
    cases = tmp_path / reviewer / "cases"
    cases.mkdir(parents=True)
    wrong = codec_for(other)
    (cases / wrong.filename("SWESMITH_001")).write_text(
        wrong.dump(RECORD), encoding="utf-8", newline="\n")

    env = dict(os.environ, SSR_REVIEWS_ROOT=str(tmp_path), PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "scripts/validate_review_output.py", "--reviewer", reviewer],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"validated_cases": 0' in result.stdout, (
        "a file in the other reviewer's format was counted:\n" + result.stdout
    )


@pytest.mark.parametrize("reviewer", sorted(REVIEWERS))
def test_the_importer_reads_that_reviewers_format(reviewer, tmp_path):
    """Regression: the importer globbed a fixed extension and the old case-ID
    prefix, so it silently found nothing for one of the two reviewers."""
    import json as _json
    import os
    import subprocess
    import sys

    from ssr.review_formats import codec_for
    from ssr.review_workflow import snapshot_manifest_hash
    from ssr.taxonomy import taxonomy_fingerprint

    codec = codec_for(reviewer)
    incoming = tmp_path / "bundle" / "reviews" / reviewer
    (incoming / "cases").mkdir(parents=True)
    for index in (1, 2, 3):
        _write_case(reviewer, f"SWESMITH_{index:03d}", incoming / "cases")
    (incoming / "review_metadata.json").write_text(
        _json.dumps({
            "reviewer": reviewer,
            "snapshot_manifest_sha256": snapshot_manifest_hash(),
            "taxonomy_fingerprint": taxonomy_fingerprint(),
        }, indent=2),
        encoding="utf-8", newline="\n",
    )

    env = dict(os.environ, SSR_REVIEWS_ROOT=str(tmp_path / "target"),
               PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "scripts/import_review_results.py",
         "--reviewer", reviewer, "--from", str(tmp_path / "bundle"),
         "--allow-incomplete"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert '"cases": 3' in result.stdout, result.stdout
    imported = tmp_path / "target" / reviewer / "cases"
    assert len(list(imported.glob(codec.glob()))) == 3


def test_the_importer_refuses_a_review_against_other_evidence(tmp_path):
    import json as _json
    import os
    import subprocess
    import sys

    reviewer = "codex"
    incoming = tmp_path / "bundle" / "reviews" / reviewer
    (incoming / "cases").mkdir(parents=True)
    _write_case(reviewer, "SWESMITH_001", incoming / "cases")
    (incoming / "review_metadata.json").write_text(
        _json.dumps({"reviewer": reviewer,
                     "snapshot_manifest_sha256": "0" * 64,
                     "taxonomy_fingerprint": "0" * 64}, indent=2),
        encoding="utf-8", newline="\n",
    )
    env = dict(os.environ, SSR_REVIEWS_ROOT=str(tmp_path / "target"),
               PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [sys.executable, "scripts/import_review_results.py",
         "--reviewer", reviewer, "--from", str(tmp_path / "bundle"), "--allow-incomplete"],
        cwd=REPO_ROOT, env=env, capture_output=True, text=True, timeout=300,
    )
    assert result.returncode != 0
    assert "different evidence" in result.stderr
