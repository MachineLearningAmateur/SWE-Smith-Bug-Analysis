"""Per-reviewer serialisation, one semantic schema.

Codex and Claude write their case records in different file formats. The
**semantics are identical**: every codec reads and writes the same record,
validated against the same ``schemas/review_result.schema.json``. Only the
bytes on disk differ.

That separation is the point. Two reviewers producing byte-identical files
invites copy-paste between them and makes an accidental shared edit hard to
see; two formats make each reviewer's output obviously its own. Nothing
downstream cares, because everything downstream reads through a codec and
gets a plain dict.

    ReviewCodec        the interface: extension, dump, load
    JsonCodec          .json    pretty JSON, sorted keys
    YamlCodec          .yaml    block YAML
    MarkdownCodec      .md      YAML frontmatter plus a readable body

The reviewer-to-format mapping lives in ``configs/review_formats.yaml`` so it
can be changed without touching code. The finalised ``review_results.jsonl``
stays JSON Lines for **both** reviewers: it is the sealed interchange artifact
that the agreement analysis reads from both sides at once, and keeping it
identical is what makes that comparison possible.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from ssr.util import SsrError

# The canonical field order. Every codec writes this order where the format
# preserves order, so two records differ only where their content differs.
FIELD_ORDER = (
    "case_id",
    "failure_pattern",
    "pattern_confidence",
    "failure_scope",
    "taxonomy_fit",
    "supporting_evidence_ids",
    "reasoning_summary",
    "proposed_other_pattern",
)


def ordered(record: dict[str, Any]) -> dict[str, Any]:
    """The record in canonical field order, unknown keys kept at the end."""
    out = {key: record[key] for key in FIELD_ORDER if key in record}
    out.update({key: value for key, value in record.items() if key not in out})
    return out


class ReviewCodec(ABC):
    name: str = "abstract"
    extension: str = ""

    @abstractmethod
    def dump(self, record: dict[str, Any]) -> str:
        ...

    @abstractmethod
    def load(self, text: str) -> dict[str, Any]:
        ...

    def filename(self, case_id: str) -> str:
        return f"{case_id}{self.extension}"

    def case_id_of(self, filename: str) -> str:
        return filename[: -len(self.extension)] if self.extension else filename

    def glob(self) -> str:
        return f"SWESMITH_*{self.extension}"


class JsonCodec(ReviewCodec):
    """Pretty JSON, one object per file. The format the Codex brief shows."""

    name = "json"
    extension = ".json"

    def dump(self, record: dict[str, Any]) -> str:
        return json.dumps(ordered(record), indent=2, ensure_ascii=False) + "\n"

    def load(self, text: str) -> dict[str, Any]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise SsrError(f"not valid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise SsrError("a review record must be a JSON object")
        return value


class YamlCodec(ReviewCodec):
    """Block YAML. Same fields, same values, different bytes."""

    name = "yaml"
    extension = ".yaml"

    def dump(self, record: dict[str, Any]) -> str:
        import yaml

        return yaml.safe_dump(
            ordered(record), sort_keys=False, allow_unicode=True, default_flow_style=False, width=88
        )

    def load(self, text: str) -> dict[str, Any]:
        import yaml

        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise SsrError(f"not valid YAML: {exc}") from exc
        if not isinstance(value, dict):
            raise SsrError("a review record must be a YAML mapping")
        return value


class MarkdownCodec(ReviewCodec):
    """YAML frontmatter plus a readable body.

    The frontmatter is the record; the body is rendered from it and is never
    read back, so the file cannot disagree with itself.
    """

    name = "markdown"
    extension = ".md"
    FENCE = "---"

    def dump(self, record: dict[str, Any]) -> str:
        import yaml

        data = ordered(record)
        front = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)
        evidence = ", ".join(f"`{item}`" for item in data.get("supporting_evidence_ids", []))
        body = [
            f"# {data.get('case_id', '')}",
            "",
            f"**Pattern:** `{data.get('failure_pattern', '')}` "
            f"({data.get('pattern_confidence', '')} confidence)",
            f"**Scope:** `{data.get('failure_scope', '')}`  ",
            f"**Taxonomy fit:** `{data.get('taxonomy_fit', '')}`",
            "",
            f"**Evidence cited:** {evidence}",
            "",
            "## Reasoning",
            "",
            str(data.get("reasoning_summary", "")),
        ]
        if data.get("proposed_other_pattern"):
            body += ["", "## Proposed pattern", "", str(data["proposed_other_pattern"])]
        return f"{self.FENCE}\n{front}{self.FENCE}\n\n" + "\n".join(body) + "\n"

    def load(self, text: str) -> dict[str, Any]:
        import yaml

        stripped = text.lstrip()
        if not stripped.startswith(self.FENCE):
            raise SsrError("a markdown review record must open with a '---' frontmatter fence")
        rest = stripped[len(self.FENCE) :]
        end = rest.find(f"\n{self.FENCE}")
        if end < 0:
            raise SsrError("the frontmatter fence was opened but never closed")
        try:
            value = yaml.safe_load(rest[:end])
        except yaml.YAMLError as exc:
            raise SsrError(f"the frontmatter is not valid YAML: {exc}") from exc
        if not isinstance(value, dict):
            raise SsrError("the frontmatter must be a mapping")
        return value


CODECS: dict[str, ReviewCodec] = {
    codec.name: codec for codec in (JsonCodec(), YamlCodec(), MarkdownCodec())
}

# Default mapping. Overridden by configs/review_formats.yaml when present.
DEFAULT_FORMATS = {"codex": "json", "claude": "yaml"}


def _configured_formats() -> dict[str, str]:
    from ssr.paths import CONFIGS

    path = CONFIGS / "review_formats.yaml"
    if not path.is_file():
        return dict(DEFAULT_FORMATS)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    formats = data.get("formats") or {}
    merged = dict(DEFAULT_FORMATS)
    merged.update({str(k): str(v) for k, v in formats.items()})
    return merged


def codec_for(reviewer: str) -> ReviewCodec:
    """The codec this reviewer writes with."""
    name = _configured_formats().get(reviewer)
    if name is None:
        raise SsrError(f"no review format configured for reviewer {reviewer!r}")
    if name not in CODECS:
        raise SsrError(
            f"unknown review format {name!r} for {reviewer!r}; available: {sorted(CODECS)}"
        )
    return CODECS[name]


def format_summary() -> dict[str, str]:
    """reviewer -> format name, for reports and metadata."""
    return {reviewer: codec_for(reviewer).name for reviewer in _configured_formats()}
