"""Validation of reviewer output against the frozen rubric.

Three layers, all of them mechanical:

1. JSON Schema (``schemas/review_result.schema.json``) for shape and enums.
2. Cross-checks against the frozen packet: the cited evidence IDs must exist
   in that packet, and the case ID must be one of the frozen 100.
3. The frozen decision rules: code-state precedence, and the scope/pattern
   agreement that rule implies.

A reviewer runs this after every case. Nothing is accepted that a downstream
script would have to guess about.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from ssr.paths import REVIEW_PACKETS, SCHEMAS
from ssr.taxonomy import CODE_STATE_LABELS, PROCESS_LABELS
from ssr.util import SsrError, read_json


@lru_cache(maxsize=4)
def _schema(name: str) -> dict[str, Any]:
    path = SCHEMAS / f"{name}.schema.json"
    if not path.is_file():
        raise SsrError(f"schema not found: {path}")
    return read_json(path)


def _validator(name: str):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SsrError(
            "jsonschema is not installed. Run: python -m pip install -e ."
        ) from exc
    return Draft202012Validator(_schema(name))


def validate_against_schema(record: Any, schema_name: str, *, label: str = "record") -> None:
    errors = sorted(_validator(schema_name).iter_errors(record), key=lambda error: list(error.path))
    if errors:
        lines = [
            f"  {'/'.join(str(part) for part in error.path) or '<root>'}: {error.message}"
            for error in errors[:10]
        ]
        raise SsrError(f"{label} does not match {schema_name}.schema.json:\n" + "\n".join(lines))


def packet_evidence_ids(bug_id: str) -> set[str]:
    packet_path = REVIEW_PACKETS / bug_id / "packet.json"
    if not packet_path.is_file():
        raise SsrError(f"no frozen packet for {bug_id}: {packet_path} does not exist")
    return set(read_json(packet_path).get("evidence_ids", []))


def validate_result(record: dict[str, Any], *, check_packet: bool = True) -> list[str]:
    """Validate one review record. Returns advisory warnings; raises on errors."""
    validate_against_schema(record, "review_result", label=f"review result {record.get('bug_id')}")

    bug_id = record["bug_id"]
    pattern = record["failure_pattern"]
    scope = record["failure_scope"]
    warnings: list[str] = []

    if check_packet:
        available = packet_evidence_ids(bug_id)
        cited = set(record["supporting_evidence_ids"])
        unknown = sorted(cited - available)
        if unknown:
            raise SsrError(
                f"{bug_id}: cites evidence IDs that are not in the packet: {unknown}. "
                f"Available: {sorted(available)}"
            )

    # Frozen decision rule 2, in its checkable direction: a process label may
    # be primary only when the reviewer states that no code-state pattern
    # applies. Scope BOTH with a process pattern means the rule was inverted.
    if pattern in PROCESS_LABELS and scope == "BOTH":
        raise SsrError(
            f"{bug_id}: code-state precedence violated. failure_pattern {pattern!r} is a "
            "verification-process pattern and failure_scope is BOTH, so a code-state "
            "pattern also applies and must be the primary label. Record the verification "
            "facet through failure_scope instead."
        )

    if pattern in CODE_STATE_LABELS and scope == "REPAIR_PROCESS":
        warnings.append(
            f"{bug_id}: a code-state pattern with failure_scope REPAIR_PROCESS is unusual; "
            "check that the scope is right."
        )

    if scope == "UNKNOWN":
        warnings.append(
            f"{bug_id}: failure_scope UNKNOWN. Every case here is an execution-validated "
            "code state, so UNKNOWN should be rare."
        )

    if record["taxonomy_fit"] == "UNCLEAR" and record["pattern_confidence"] == "HIGH":
        warnings.append(f"{bug_id}: taxonomy_fit UNCLEAR with pattern_confidence HIGH is inconsistent.")

    if len(record["reasoning_summary"].split()) < 8:
        warnings.append(f"{bug_id}: reasoning_summary is very short; cite what the evidence shows.")

    return warnings


def validate_results(records: Iterable[dict[str, Any]], *, check_packet: bool = True) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for record in records:
        bug_id = record.get("bug_id")
        if bug_id in seen:
            raise SsrError(f"duplicate review record for {bug_id}")
        seen.add(bug_id)
        warnings.extend(validate_result(record, check_packet=check_packet))
    return warnings


def validate_packet_file(path: Path) -> None:
    validate_against_schema(read_json(path), "review_packet", label=f"packet {path}")


def validate_generation_metadata(record: dict[str, Any], *, label: str = "metadata") -> None:
    validate_against_schema(record, "generation_metadata", label=label)


def validate_validation_result(record: dict[str, Any], *, label: str = "validation") -> None:
    validate_against_schema(record, "validation_result", label=label)
