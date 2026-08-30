"""Canonical repository locations.

Every script resolves paths through this module so that a run started from
any working directory writes to the same places.

Three roots can be redirected with environment variables. They exist so that
``scripts/selftest.py`` can run the whole pipeline against a throwaway
directory without touching the checkout, and so that a second review round
can be kept beside the first:

    SSR_DATA_ROOT       default <repo>/data
    SSR_REVIEWS_ROOT    default <repo>/reviews
    SSR_ANALYSIS_ROOT   default <repo>/analysis

The variables are read at import time. Set them before starting the process,
not part-way through it.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _root(variable: str, default: Path) -> Path:
    override = os.environ.get(variable)
    return Path(override).expanduser().resolve() if override else default


CONFIGS = REPO_ROOT / "configs"
DOCS = REPO_ROOT / "docs"
PROMPTS = REPO_ROOT / "prompts"
SCHEMAS = REPO_ROOT / "schemas"
TAXONOMY = REPO_ROOT / "taxonomy"
ANALYSIS = _root("SSR_ANALYSIS_ROOT", REPO_ROOT / "analysis")
RUNS = REPO_ROOT / "runs"

DATA = _root("SSR_DATA_ROOT", REPO_ROOT / "data")
GENERATED_POOL = DATA / "generated_pool"
VALIDATED_POOL = DATA / "validated_pool"
REJECTED = DATA / "rejected"
SAMPLING = DATA / "sampling"
REVIEW_PACKETS = DATA / "review_packets"
OBJECTIVE_METRICS = DATA / "objective_metrics"
REVIEW_MANIFEST = DATA / "review_manifest.csv"
REVIEW_SNAPSHOT_MANIFEST = DATA / "review_snapshot_manifest.json"
CORPUS_STATUS = DATA / "CORPUS_STATUS.json"

REVIEWS = _root("SSR_REVIEWS_ROOT", REPO_ROOT / "reviews")
REVIEWERS = ("codex", "claude")

FROZEN_TAXONOMY = TAXONOMY / "frozen_failure_taxonomy_v1.md"
PATTERN_FAMILIES = TAXONOMY / "pattern_families.yaml"
TAXONOMY_PROVENANCE = TAXONOMY / "TAXONOMY_PROVENANCE.json"

# Heavyweight artifacts (worktrees, Docker layers, caches) live outside Git.
# Overridable with SSR_WORKSPACE_ROOT; the default is a sibling of the repo
# that .gitignore already excludes.
def workspace_root() -> Path:
    override = os.environ.get("SSR_WORKSPACE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return (REPO_ROOT / "workspace").resolve()


def reviewer_dir(reviewer: str) -> Path:
    if reviewer not in REVIEWERS:
        raise ValueError(f"unknown reviewer {reviewer!r}; expected one of {REVIEWERS}")
    return REVIEWS / reviewer


def bug_dir(bug_id: str, *, validated: bool = True) -> Path:
    root = VALIDATED_POOL if validated else GENERATED_POOL
    return root / bug_id


def packet_dir(packet_id: str) -> Path:
    return REVIEW_PACKETS / packet_id


def ensure_dirs() -> None:
    for path in (
        GENERATED_POOL,
        VALIDATED_POOL,
        REJECTED,
        SAMPLING,
        REVIEW_PACKETS,
        OBJECTIVE_METRICS,
        RUNS,
        ANALYSIS,
    ):
        path.mkdir(parents=True, exist_ok=True)
