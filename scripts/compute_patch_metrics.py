#!/usr/bin/env python3
"""Compute objective, non-LLM patch metrics (handoff section 25).

    python scripts/compute_patch_metrics.py
    python scripts/compute_patch_metrics.py --env pvlib_python   # adds history similarity

Reads the validated pool and writes data/objective_metrics/patch_metrics.csv
and patch_metrics.json: files and directories changed, lines added and
deleted, the add/delete ratio, identifiers and call references introduced and
removed, configuration and dependency edits, cross-file edits, test edits, and
historical-reversion similarity.

These are a second line of evidence beside the taxonomy labels. They are
computed from the diff alone and read no reviewer output, so they can be
joined to either side without circularity.

Historical-reversion similarity needs the repository history, so it is
computed only when --env is given. It scores each bug diff against the reverse
of recent commits that touched the same files, and keeps the best match.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.metrics import compute_patch_metrics, historical_reversion_similarity  # noqa: E402
from ssr.paths import OBJECTIVE_METRICS, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.pool import load_pool  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.util import SsrError, setup_logging, utc_now, write_json  # noqa: E402

HISTORY_DEPTH = 60


def history_diffs(env, paths: list[str], depth: int = HISTORY_DEPTH) -> list[str]:
    """Recent commit diffs touching the same files as the bug."""
    if not paths:
        return []
    quoted = " ".join(f"'{path}'" for path in paths[:20])
    log = env.git(f"log --format=%H -n {depth} -- {quoted}", timeout_s=300)
    shas = [line.strip() for line in log.stdout.splitlines() if line.strip()]
    diffs: list[str] = []
    for sha in shas[:depth]:
        show = env.git(f"show --no-color --format= {sha} -- {quoted}", timeout_s=180)
        if show.ok and show.stdout.strip():
            diffs.append(show.stdout)
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", default=str(VALIDATED_POOL))
    parser.add_argument("--env", default=None, help="environment name; enables history similarity")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--output", default=str(OBJECTIVE_METRICS))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)

    entries = load_pool(Path(args.pool))
    if not entries:
        raise SsrError(f"no validated bugs under {args.pool}")

    env = get_environment(args.env, allow_smoke=args.allow_smoke).build() if args.env else None
    rows: list[dict] = []

    try:
        for entry in entries:
            metrics = compute_patch_metrics(entry.bug_id, entry.artifacts.diff_text())
            if env is not None:
                try:
                    metrics.historical_reversion_similarity = historical_reversion_similarity(
                        entry.artifacts.diff_text(), history_diffs(env, metrics.changed_paths)
                    )
                except SsrError as exc:
                    log.warning("%s: history similarity unavailable: %s", entry.bug_id, exc)
            row = metrics.to_dict()
            row["changed_paths"] = ";".join(row["changed_paths"])
            rows.append(row)
            log.debug("%s: %d file(s), +%d -%d", entry.bug_id, metrics.files_changed,
                      metrics.lines_added, metrics.lines_deleted)
    finally:
        if env is not None:
            env.close()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with open(output / "patch_metrics.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    write_json(output / "patch_metrics.json", {
        "computed_at_utc": utc_now(),
        "pool": str(Path(args.pool)),
        "history_similarity_computed": env is not None,
        "n": len(rows),
        "metrics": rows,
        "note": (
            "Computed from the diff alone. No reviewer output and no generation "
            "strategy was read, so these metrics can be joined to either without "
            "circularity."
        ),
    })

    print(json.dumps({
        "output": str(output),
        "bugs": len(rows),
        "history_similarity_computed": env is not None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
