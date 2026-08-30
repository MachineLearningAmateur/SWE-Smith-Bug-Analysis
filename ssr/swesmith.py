"""Access to the official SWE-smith releases, at pinned revisions.

Two Hugging Face datasets define the population for this study:

``SWE-bench/SWE-smith-trajectories``
    The trajectories used to fine-tune Qwen 2.5 Coder Instruct into
    SWE-agent-LM-32B. **Pinned**, because the public dataset was reorganised
    after the model release: the revision used here has a single ``train``
    split, while the current ``main`` carries three much larger splits
    (``tool``, ``xml``, ``ticks``) that are not the training set.

``SWE-bench/SWE-smith``
    The task corpus the trajectories were run against. Also pinned, to the
    upload made the same day as the trajectory release. That revision carries
    ``base_commit`` and ``created_at``; the current ``main`` has dropped both,
    and ``base_commit`` is what makes a task reconstructible.

Nothing here downloads from ``main``. A study that silently followed a moving
dataset would not be reproducible, and the counts would drift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ssr.paths import REPO_ROOT
from ssr.util import SsrError

# --------------------------------------------------------------------------
# pinned revisions
# --------------------------------------------------------------------------
TRAJECTORIES_REPO = "SWE-bench/SWE-smith-trajectories"
TRAJECTORIES_REVISION = "f6b6d7e01f2b"
TRAJECTORIES_REVISION_NOTE = (
    "Last revision before the 2025-07-18/19 expansion. Its dataset card declares a "
    "single train split with num_examples 5016, and its prose states these are the "
    "trajectories used to fine-tune SWE-agent-LM-32B."
)

TASKS_REPO = "SWE-bench/SWE-smith"
TASKS_REVISION = "9f2a10465194"
TASKS_REVISION_NOTE = (
    "The 2025-04-29 upload, made the same day as the trajectory release. 50,137 rows, "
    "and unlike the current main it still carries base_commit and created_at."
)

# The dataset card prose says 5017; the shipped data has 5016 rows. Recorded
# rather than reconciled: the data is what can be counted.
DOCUMENTED_TRAJECTORY_CLAIM = 5017

CACHE_DIR = REPO_ROOT / "workspace" / "hf_cache"


# --------------------------------------------------------------------------
# generation method
# --------------------------------------------------------------------------
# Established from swesmith/bug_gen/collect_patches.py, which builds the ID as
#
#     bug_type_and_uuid = file.split(f"{PREFIX_BUG}__")[-1].split(".diff")[0]
#     instance_id = f"{repo}.{bug_type_and_uuid}"
#
# where ``repo`` is the bug_gen log directory name and already contains a dot
# (``owner__name.commitprefix``). The method is therefore everything after the
# LAST dot and before the LAST double underscore. Splitting on the FIRST dot,
# which the shape invites, produces nonsense for repositories whose directory
# name holds an extra dot.
_UUID_SUFFIX = re.compile(r"__[0-9a-z]{6,}$")

# Which module produced each method, from the swesmith/bug_gen/ layout.
METHOD_FAMILY = {
    "lm_rewrite": "llm",
    "lm_modify": "llm",
    "combine_file": "combine",
    "combine_module": "combine",
    "func_basic": "procedural",
}


_PR_TOKEN = re.compile(r"^pr_\d+$")


def generation_method_raw(instance_id: str) -> str:
    """The method token exactly as it appears in the instance ID."""
    _, dot, rest = instance_id.rpartition(".")
    if not dot:
        raise SsrError(f"instance_id has no method component: {instance_id!r}")
    return _UUID_SUFFIX.sub("", rest)


def generation_method(instance_id: str) -> str:
    """The bug-generation METHOD, with per-instance identifiers normalised.

    Mirror bugs are named after the pull request they were taken from
    (``pr_4045``), so the raw token is an instance identifier, not a method:
    left as-is it yields over a thousand one-member "methods" and makes
    stratification meaningless. Every such token maps to ``pr_mirror``. The
    raw token is preserved separately by ``generation_method_raw``.
    """
    token = generation_method_raw(instance_id)
    return "pr_mirror" if _PR_TOKEN.match(token) else token


def method_family(method: str) -> str:
    """Which bug_gen module family a method belongs to."""
    if method in METHOD_FAMILY:
        return METHOD_FAMILY[method]
    if method.startswith("func_pm_") or method.startswith("func_"):
        return "procedural"
    if method.startswith("pr_"):
        return "mirror"
    return "unknown"


def mirror_repo(instance_id: str) -> str:
    """The SWE-smith mirror repository directory name (``owner__name.commit``)."""
    head, dot, _ = instance_id.rpartition(".")
    if not dot:
        raise SsrError(f"instance_id has no repository component: {instance_id!r}")
    return head


def upstream_repo(instance_id: str) -> str:
    """The upstream project as ``owner/name``, for neutral display.

    ``Cog-Creators__Red-DiscordBot.33e0eac7`` -> ``Cog-Creators/Red-DiscordBot``
    """
    head = mirror_repo(instance_id)
    name = head.rsplit(".", 1)[0] if "." in head else head
    return name.replace("__", "/", 1)


# --------------------------------------------------------------------------
# dataset access
# --------------------------------------------------------------------------
def _snapshot(repo_id: str, revision: str, patterns: list[str]) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise SsrError("huggingface_hub is not installed. Run: python -m pip install -r requirements.txt") from exc
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return Path(
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            allow_patterns=patterns,
            cache_dir=str(CACHE_DIR),
            max_workers=8,
        )
    )


def trajectories_path() -> Path:
    return _snapshot(TRAJECTORIES_REPO, TRAJECTORIES_REVISION, ["data/train-*.parquet"])


def tasks_path() -> Path:
    return _snapshot(TASKS_REPO, TASKS_REVISION, ["data/*.parquet"])


@lru_cache(maxsize=1)
def trajectory_instance_ids() -> list[str]:
    """One entry per training trajectory, in file order. Not deduplicated."""
    import pyarrow.parquet as pq

    files = sorted(trajectories_path().rglob("*.parquet"))
    if not files:
        raise SsrError("no trajectory parquet files were downloaded")
    ids: list[str] = []
    for path in files:
        ids.extend(pq.read_table(path, columns=["instance_id"]).column("instance_id").to_pylist())
    return ids


def task_table(columns: list[str] | None = None):
    import pyarrow.dataset as ds

    root = tasks_path() / "data"
    return ds.dataset(str(root), format="parquet").to_table(columns=columns)


@lru_cache(maxsize=1)
def task_index() -> dict[str, int]:
    """instance_id -> row index in the task table."""
    ids = task_table(columns=["instance_id"]).column("instance_id").to_pylist()
    return {value: position for position, value in enumerate(ids)}


def load_task_rows(instance_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Full task records for the given instance IDs."""
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    root = tasks_path() / "data"
    wanted = set(instance_ids)
    table = ds.dataset(str(root), format="parquet").to_table(
        filter=pc.field("instance_id").isin(list(wanted))
    )
    rows = {row["instance_id"]: row for row in table.to_pylist()}
    missing = sorted(wanted - set(rows))
    if missing:
        raise SsrError(
            f"{len(missing)} instance_id(s) are not in the pinned task dataset "
            f"({TASKS_REPO}@{TASKS_REVISION}), first: {missing[:3]}"
        )
    return rows


@dataclass
class PopulationRow:
    """One unique SWE-smith task behind the training trajectories."""

    instance_id: str
    repo: str
    upstream_repo: str
    base_commit: str
    language: str
    generation_method: str
    generation_method_raw: str
    method_family: str
    trajectory_count: int
    fail_to_pass_count: int
    pass_to_pass_count: int
    patch_bytes: int
    image_name: str

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def provenance() -> dict[str, Any]:
    """The revision record every downstream artifact must carry."""
    return {
        "trajectory_dataset": TRAJECTORIES_REPO,
        "trajectory_dataset_revision": TRAJECTORIES_REVISION,
        "trajectory_revision_note": TRAJECTORIES_REVISION_NOTE,
        "task_dataset": TASKS_REPO,
        "task_dataset_revision": TASKS_REVISION,
        "task_revision_note": TASKS_REVISION_NOTE,
        "documented_trajectory_claim": DOCUMENTED_TRAJECTORY_CLAIM,
    }
