#!/usr/bin/env python3
"""Finalise the 100-case sample and freeze its review packets (Checkpoint C).

    python scripts/build_swesmith_packets.py
    python scripts/build_swesmith_packets.py --workers 8

One command, because selection and reconstruction are coupled: a task that
cannot be reconstructed must not be replaced by hand. When one fails, its
instance ID goes on an exclusion list and the deterministic sampler runs
again with the SAME seed. The replacement is therefore as determined as the
original pick, and every exclusion is recorded.

Outputs:
    data/review_manifest.csv              reviewer-facing, no generation method
    data/review_packets/SWESMITH_nnn/     100 frozen packets
    data/review_snapshot_manifest.json    per-file hashes of every packet
    data/hidden/sample_metadata.csv       the full record, reviewer-forbidden
    data/hidden/selection_record.json     seed, allocation, exclusions
    analysis/sample_balance.md            population versus sample

The clean state used for every reconstruction is the parent of the ``Bug
Patch`` commit, never the dataset's ``base_commit``. See ssr/packets.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.config import load_config  # noqa: E402
from ssr.corpus import write_status  # noqa: E402
from ssr.packets import PacketBuilder, PacketSource, packet_digest, packet_file_hashes, reconstruct  # noqa: E402
from ssr.paths import (  # noqa: E402
    ANALYSIS,
    DATA,
    REVIEW_MANIFEST,
    REVIEW_PACKETS,
    REVIEW_SNAPSHOT_MANIFEST,
    ensure_dirs,
)
from ssr.swesmith import load_task_rows, provenance  # noqa: E402
from ssr.swesmith_sampling import select  # noqa: E402
from ssr.taxonomy import taxonomy_fingerprint, verify_provenance  # noqa: E402
from ssr.util import SsrError, force_rmtree, setup_logging, sha256_file, utc_now, write_json  # noqa: E402

POPULATION = DATA / "population" / "swesmith_training_tasks.csv"
HIDDEN = DATA / "hidden"
MAX_ROUNDS = 5


def build_one(record, task, scratch, builder):
    """Reconstruct and publish one packet. Returns (case_id, error or None)."""
    recon = reconstruct(task, scratch)
    if not recon.ok:
        return record["instance_id"], recon.failure
    try:
        builder.build(
            PacketSource(
                case_id=record["case_id"],
                upstream_repo=record["upstream_repo"],
                language=record["language"],
                reconstruction=recon,
                problem_statement=task.get("problem_statement") or "",
                fail_to_pass=list(task["FAIL_TO_PASS"]),
                pass_to_pass_count=len(task["PASS_TO_PASS"]),
                mirror_repo=task["repo"],
            )
        )
    except SsrError as exc:
        return record["instance_id"], f"packet rejected: {exc}"
    return record["instance_id"], None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--population", default=str(POPULATION))
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)
    verify_provenance()
    config = load_config("sampling")

    path = Path(args.population)
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    log.info("population: %d unique task instances", len(rows))

    if REVIEW_PACKETS.exists():
        for child in REVIEW_PACKETS.iterdir():
            if child.is_dir() and child.name.startswith("SWESMITH_"):
                force_rmtree(child)

    exclusions: list[str] = []
    exclusion_log: list[dict] = []
    builder = PacketBuilder(REVIEW_PACKETS)
    selection = None

    with tempfile.TemporaryDirectory(prefix="swesmith_packets_") as scratch_root:
        scratch = Path(scratch_root)
        for round_number in range(1, MAX_ROUNDS + 1):
            selection = select(rows, dict(config), exclusions=exclusions)
            if len(selection.records) != int(config["target_n"]):
                raise SsrError(
                    f"the sampler returned {len(selection.records)} cases, not {config['target_n']}"
                )
            tasks = load_task_rows([r["instance_id"] for r in selection.records])
            log.info("round %d: reconstructing %d task(s)", round_number, len(selection.records))

            failures: dict[str, str] = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [
                    pool.submit(build_one, record, tasks[record["instance_id"]], scratch, builder)
                    for record in selection.records
                ]
                for done, future in enumerate(concurrent.futures.as_completed(futures), start=1):
                    instance_id, error = future.result()
                    if error:
                        failures[instance_id] = error
                    if done % 20 == 0:
                        log.info("  %d/%d", done, len(futures))

            if not failures:
                log.info("round %d: all %d packet(s) built", round_number, len(selection.records))
                break

            log.warning("round %d: %d reconstruction failure(s); re-running the sampler",
                        round_number, len(failures))
            for instance_id, reason in sorted(failures.items()):
                exclusion_log.append({
                    "round": round_number, "instance_id": instance_id, "reason": reason,
                })
            exclusions.extend(failures)
            # Packets from this round are stale: case IDs are reassigned when
            # the membership changes, so start clean.
            for child in REVIEW_PACKETS.iterdir():
                if child.is_dir() and child.name.startswith("SWESMITH_"):
                    force_rmtree(child)
        else:
            raise SsrError(f"reconstruction still failing after {MAX_ROUNDS} rounds")

    records = selection.records

    # -- reviewer-facing manifest ------------------------------------------
    manifest_rows = []
    for record in records:
        directory = REVIEW_PACKETS / record["case_id"]
        manifest_rows.append({
            "case_id": record["case_id"],
            "repo": record["upstream_repo"],
            "language": record["language"],
            "packet_path": f"data/review_packets/{record['case_id']}",
            "packet_sha256": packet_digest(directory),
        })
    with open(REVIEW_MANIFEST, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(manifest_rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest_rows)

    # -- snapshot manifest --------------------------------------------------
    snapshot = {
        "frozen_at_utc": utc_now(),
        "packet_count": len(records),
        "taxonomy_fingerprint": taxonomy_fingerprint(),
        "review_manifest_sha256": sha256_file(REVIEW_MANIFEST),
        "packets": [
            {
                "case_id": record["case_id"],
                "path": f"data/review_packets/{record['case_id']}",
                "digest": packet_digest(REVIEW_PACKETS / record["case_id"]),
                "files": packet_file_hashes(REVIEW_PACKETS / record["case_id"]),
            }
            for record in records
        ],
        "note": "Every reviewer records this file's SHA-256. If it changes during a "
                "review, that review is void.",
    }
    write_json(REVIEW_SNAPSHOT_MANIFEST, snapshot)

    # -- hidden metadata ----------------------------------------------------
    HIDDEN.mkdir(parents=True, exist_ok=True)
    fieldnames = ["case_id"] + [k for k in records[0] if k != "case_id"]
    with open(HIDDEN / "sample_metadata.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
    try:
        import pyarrow as pa, pyarrow.parquet as pq

        pq.write_table(pa.Table.from_pylist(records), HIDDEN / "sample_metadata.parquet")
    except ImportError:
        log.warning("pyarrow missing; hidden metadata written as CSV only")

    write_json(HIDDEN / "selection_record.json", {
        "generated_at_utc": utc_now(),
        **provenance(),
        "sampling_config_sha256": config.sha256,
        "population_file": str(path),
        "population_sha256": sha256_file(path),
        "summary": selection.summary,
        "allocation": selection.allocation,
        "balance": selection.balance,
        "distortions": selection.distortions,
        "exclusions": exclusion_log,
        "selection": [{"case_id": r["case_id"], "instance_id": r["instance_id"]} for r in records],
    })

    status = write_status("RESEARCH", len(records), "OFFICIAL_RELEASE")

    # -- balance report -----------------------------------------------------
    repos = Counter(r["upstream_repo"] for r in records)
    lines = [
        "# Sample balance", "",
        f"Population: **{selection.summary['population_size']}** unique SWE-smith task",
        "instances behind the official training trajectories for SWE-agent-LM-32B.",
        f"Sample: **{len(records)}** cases, seed `{config['seed']}`, proportional",
        "largest-remainder allocation across `generation_method`.", "",
        "## Generation method", "",
        "| Method | Population | Share | Allocated | Sample | Share | Deviation |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in selection.balance:
        lines.append(
            f"| `{row['stratum']}` | {row['population_n']} | {row['population_share']:.1%} | "
            f"{row['allocated']} | {row['sample_n']} | {row['sample_share']:.1%} | {row['deviation']:+.1%} |"
        )
    lines += [
        "", f"Largest absolute deviation: **{selection.summary['largest_absolute_deviation']:.1%}**.",
        "One case is one percent, so that is the granularity of a 100-case sample.", "",
        "## Repositories", "",
        f"- unique repositories: **{len(repos)}**",
        f"- most cases from one repository: **{max(repos.values())}** (cap {config['max_per_repo']})", "",
        "| Repository | Cases |", "|---|---:|",
    ]
    for name, count in repos.most_common(15):
        lines.append(f"| `{name}` | {count} |")
    lines += ["", "## Distortions", ""]
    lines += ([f"- `{d['type']}`: {json.dumps({k: v for k, v in d.items() if k != 'type'})}"
               for d in selection.distortions] or ["None."])
    lines += ["", "## Reconstruction failures and replacements", ""]
    if exclusion_log:
        lines += ["| Round | Instance | Reason |", "|---:|---|---|"]
        lines += [f"| {e['round']} | `{e['instance_id']}` | {e['reason'][:120]} |" for e in exclusion_log]
        lines += ["", "Replacements were not hand-picked: the deterministic sampler was",
                  "re-run with the same seed and the failed instances excluded."]
    else:
        lines.append("None. Every selected task reconstructed on the first round.")
    lines += ["", "## Language", "",
              "Every task is Python; the pinned corpus is Python-only. See",
              "`analysis/language_confound_plan.md`."]
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    (ANALYSIS / "sample_balance.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps({
        **selection.summary,
        "reconstruction_failures": len(exclusion_log),
        "review_manifest_sha256": sha256_file(REVIEW_MANIFEST),
        "snapshot_manifest_sha256": sha256_file(REVIEW_SNAPSHOT_MANIFEST),
        "taxonomy_fingerprint": status.taxonomy_fingerprint,
    }, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
