"""The frozen AIDev failure taxonomy.

The taxonomy is imported verbatim and is not allowed to change here. Every
consumer loads it through this module so that one hash check protects the
whole pipeline:

* ``verify_provenance`` re-hashes both taxonomy files and compares them with
  ``taxonomy/TAXONOMY_PROVENANCE.json``, including the family-mapping hash
  declared in the handoff.
* ``family_for`` derives the broad family from a reviewer's fine-grained
  label. Reviewers never choose a family.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import yaml

from ssr.paths import FROZEN_TAXONOMY, PATTERN_FAMILIES, TAXONOMY_PROVENANCE
from ssr.util import SsrError, read_json, sha256_file

# The family-mapping hash declared in the research handoff. Recorded here as
# an independent constant so a silently edited provenance file is still caught.
HANDOFF_MAPPING_SHA256 = "1ce7232047437f87e7116d84b369e4f820e854481cbc744faf3b1d4c1af60985"

# Fine-grained labels a reviewer may assign in the SSR study. Identical to
# AIDev v1 except that UNASSIGNED is absent: every SSR case is an
# execution-validated technical bug state, so the non-technical escape hatch
# cannot apply. See schemas/review_result.schema.json.
FINE_LABELS = (
    "masked_symptom_instead_of_fixing",
    "false_premise_about_existing_code",
    "incomplete_change_propagation",
    "misdiagnosed_root_cause",
    "broke_existing_contract_or_behavior",
    "disproportionate_or_duplicative_solution",
    "vacuous_verification",
    "violated_project_constraint_or_convention",
    "unverified_trial_and_error",
    "wrong_baseline_or_branch",
    "OTHER_TECHNICAL_PATTERN",
)

# Verification-process labels. Under the frozen code-state-precedence rule a
# reviewer picks a code-state label over one of these when both apply.
PROCESS_LABELS = ("vacuous_verification", "unverified_trial_and_error")

CODE_STATE_LABELS = tuple(label for label in FINE_LABELS if label not in PROCESS_LABELS)

SCOPES = ("CODE_STATE", "REPAIR_PROCESS", "BOTH", "UNKNOWN")
TAXONOMY_FITS = ("DIRECT", "OTHER", "UNCLEAR")


@dataclass(frozen=True)
class TaxonomyProvenance:
    taxonomy_sha256: str
    mapping_sha256: str
    source_repo: str
    source_commit: str
    taxonomy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "taxonomy_version": self.taxonomy_version,
            "taxonomy_sha256": self.taxonomy_sha256,
            "mapping_sha256": self.mapping_sha256,
            "source_repo": self.source_repo,
            "source_commit": self.source_commit,
        }


@lru_cache(maxsize=1)
def load_mapping() -> dict[str, str]:
    """Fine-grained label -> broad family, checked for completeness."""
    if not PATTERN_FAMILIES.is_file():
        raise SsrError(f"family mapping is missing: {PATTERN_FAMILIES}")
    families = yaml.safe_load(PATTERN_FAMILIES.read_text(encoding="utf-8")) or {}
    fine_to_family: dict[str, str] = {}
    for family, members in families.items():
        for member in members or []:
            if member in fine_to_family:
                raise SsrError(f"label {member!r} is mapped to two families")
            fine_to_family[member] = family
    missing = set(FINE_LABELS) - set(fine_to_family)
    extra = set(fine_to_family) - set(FINE_LABELS)
    if missing:
        raise SsrError(f"family mapping does not cover: {sorted(missing)}")
    if extra:
        raise SsrError(f"family mapping has labels outside the SSR label set: {sorted(extra)}")
    return fine_to_family


@lru_cache(maxsize=1)
def families() -> tuple[str, ...]:
    return tuple(sorted(set(load_mapping().values())))


def family_for(fine_label: str) -> str:
    mapping = load_mapping()
    if fine_label not in mapping:
        raise SsrError(f"unknown fine-grained label {fine_label!r}")
    return mapping[fine_label]


def is_process_label(fine_label: str) -> bool:
    return fine_label in PROCESS_LABELS


@lru_cache(maxsize=1)
def provenance() -> TaxonomyProvenance:
    record = read_json(TAXONOMY_PROVENANCE)
    artifacts = {entry["role"]: entry for entry in record.get("artifacts", [])}
    try:
        return TaxonomyProvenance(
            taxonomy_sha256=artifacts["frozen_taxonomy"]["sha256"],
            mapping_sha256=artifacts["family_mapping"]["sha256"],
            source_repo=record["source"]["repository"],
            source_commit=record["source"]["source_commit"],
            taxonomy_version=record["source"]["taxonomy_version"],
        )
    except KeyError as exc:
        raise SsrError(f"TAXONOMY_PROVENANCE.json is missing {exc}") from exc


def verify_provenance() -> dict[str, Any]:
    """Re-hash both taxonomy files. Raises on any mismatch."""
    declared = provenance()
    problems: list[str] = []

    actual_taxonomy = sha256_file(FROZEN_TAXONOMY)
    if actual_taxonomy != declared.taxonomy_sha256:
        problems.append(
            f"frozen_failure_taxonomy_v1.md hash {actual_taxonomy} does not match the "
            f"recorded {declared.taxonomy_sha256}"
        )

    actual_mapping = sha256_file(PATTERN_FAMILIES)
    if actual_mapping != declared.mapping_sha256:
        problems.append(
            f"pattern_families.yaml hash {actual_mapping} does not match the recorded "
            f"{declared.mapping_sha256}"
        )
    if actual_mapping != HANDOFF_MAPPING_SHA256:
        problems.append(
            f"pattern_families.yaml hash {actual_mapping} does not match the handoff "
            f"constant {HANDOFF_MAPPING_SHA256}"
        )

    load_mapping()  # completeness check

    if problems:
        raise SsrError(
            "the frozen taxonomy has been altered. The taxonomy must not change on the "
            "basis of what SSR bugs look like; any change needs a new version with its "
            "own freeze record.\n  " + "\n  ".join(problems)
        )

    return {
        **declared.to_dict(),
        "verified_taxonomy_sha256": actual_taxonomy,
        "verified_mapping_sha256": actual_mapping,
        "families": list(families()),
        "fine_labels": list(FINE_LABELS),
    }


def taxonomy_fingerprint() -> str:
    """One hash covering both taxonomy files. Recorded in review metadata."""
    from ssr.util import sha256_text

    return sha256_text(f"{sha256_file(FROZEN_TAXONOMY)}:{sha256_file(PATTERN_FAMILIES)}")
