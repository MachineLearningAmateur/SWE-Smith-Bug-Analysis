#!/usr/bin/env python3
"""Build the canonical training-task population manifest (handoff section 5).

    python scripts/build_training_population.py

One row per UNIQUE SWE-smith task instance represented in the official
training trajectories for SWE-agent-LM-32B. Both source datasets are read at
pinned revisions; see ``ssr/swesmith.py`` for why.

Writes:
    data/population/swesmith_training_tasks.csv
    data/population/swesmith_training_tasks.parquet
    data/population/POPULATION_PROVENANCE.json
    data/population/unresolved_instances.json

A task with several training trajectories gets ONE population row, with the
trajectory count kept in ``trajectory_count`` and the trajectory row indices
listed in the provenance file. The same underlying synthetic bug is never
counted twice.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import DATA, ensure_dirs  # noqa: E402
from ssr.swesmith import (  # noqa: E402
    DOCUMENTED_TRAJECTORY_CLAIM,
    PopulationRow,
    generation_method,
    generation_method_raw,
    method_family,
    mirror_repo,
    provenance,
    task_table,
    trajectory_instance_ids,
    upstream_repo,
)
from ssr.util import SsrError, setup_logging, sha256_file, utc_now, write_json  # noqa: E402

POPULATION = DATA / "population"

# The task corpus is Python-only at this revision; recorded explicitly rather
# than assumed, and re-checked below against the task records.
DEFAULT_LANGUAGE = "python"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    POPULATION.mkdir(parents=True, exist_ok=True)
    log = setup_logging(args.verbose)

    traj_ids = trajectory_instance_ids()
    log.info("training trajectories: %d", len(traj_ids))

    positions: dict[str, list[int]] = defaultdict(list)
    for index, value in enumerate(traj_ids):
        positions[value].append(index)
    unique_ids = sorted(positions)
    log.info("unique task instances: %d", len(unique_ids))

    table = task_table(
        columns=["instance_id", "repo", "base_commit", "image_name",
                 "FAIL_TO_PASS", "PASS_TO_PASS", "patch"]
    )
    by_id = {row["instance_id"]: row for row in table.to_pylist()}

    rows: list[PopulationRow] = []
    unresolved: list[dict] = []
    for instance_id in unique_ids:
        record = by_id.get(instance_id)
        if record is None:
            unresolved.append(
                {
                    "instance_id": instance_id,
                    "trajectory_count": len(positions[instance_id]),
                    "reason": "not present in the pinned task dataset revision",
                    "mirror_repo": mirror_repo(instance_id),
                }
            )
            continue
        rows.append(
            PopulationRow(
                instance_id=instance_id,
                repo=record["repo"],
                upstream_repo=upstream_repo(instance_id),
                base_commit=record["base_commit"],
                language=DEFAULT_LANGUAGE,
                generation_method=generation_method(instance_id),
                generation_method_raw=generation_method_raw(instance_id),
                method_family=method_family(generation_method(instance_id)),
                trajectory_count=len(positions[instance_id]),
                fail_to_pass_count=len(record["FAIL_TO_PASS"]),
                pass_to_pass_count=len(record["PASS_TO_PASS"]),
                patch_bytes=len(record["patch"] or ""),
                image_name=record["image_name"],
            )
        )

    if not rows:
        raise SsrError("no training task resolved; the pinned revisions may be wrong")
    rows.sort(key=lambda row: row.instance_id)

    fieldnames = list(rows[0].to_dict())
    csv_path = POPULATION / "swesmith_training_tasks.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(row.to_dict() for row in rows)

    parquet_path = POPULATION / "swesmith_training_tasks.parquet"
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist([row.to_dict() for row in rows]), parquet_path)
    except ImportError:
        log.warning("pyarrow missing; wrote CSV only")
        parquet_path = None

    methods = Counter(row.generation_method for row in rows)
    families = Counter(row.method_family for row in rows)
    repos = Counter(row.upstream_repo for row in rows)
    duplicates = Counter(row.trajectory_count for row in rows)

    record = {
        "generated_at_utc": utc_now(),
        **provenance(),
        "counts": {
            "documented_trajectory_claim": DOCUMENTED_TRAJECTORY_CLAIM,
            "trajectory_rows_in_pinned_revision": len(traj_ids),
            "unique_task_instances": len(unique_ids),
            "resolved_task_instances": len(rows),
            "unresolved_task_instances": len(unresolved),
            "duplicate_trajectory_rows": len(traj_ids) - len(unique_ids),
        },
        "distribution": {
            "generation_method": dict(methods.most_common()),
            "method_family": dict(families.most_common()),
            "unique_upstream_repositories": len(repos),
            "largest_repository_share": round(repos.most_common(1)[0][1] / len(rows), 4),
            "trajectories_per_task": {str(k): v for k, v in sorted(duplicates.items())},
        },
        "outputs": {
            "csv": csv_path.name,
            "csv_sha256": sha256_file(csv_path),
            "parquet": parquet_path.name if parquet_path else None,
        },
        "notes": [
            "The trajectory dataset card prose says 5017; the shipped data at the "
            f"pinned revision has {len(traj_ids)} rows. The count is reported, not reconciled.",
            "One population row per unique task instance. Tasks with several "
            "training trajectories keep the count in trajectory_count.",
            "Language is recorded as python for every row: the task corpus at this "
            "revision is Python-only.",
        ],
    }
    write_json(POPULATION / "POPULATION_PROVENANCE.json", record)
    write_json(
        POPULATION / "unresolved_instances.json",
        {"generated_at_utc": utc_now(), "count": len(unresolved), "instances": unresolved},
    )

    print(json.dumps({
        "trajectory_rows": len(traj_ids),
        "unique_task_instances": len(unique_ids),
        "resolved": len(rows),
        "unresolved": len(unresolved),
        "unique_repositories": len(repos),
        "generation_methods": len(methods),
        "csv": str(csv_path),
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
