#!/usr/bin/env python3
"""Select 100 SWE-smith training tasks for blind review (sections 11 to 15).

    python scripts/select_swesmith_training_sample.py --dry-run
    python scripts/select_swesmith_training_sample.py

The sample must PRESERVE the population's composition, not impose an
artificial balance. Allocation across generation methods is proportional, by
the largest-remainder method, so the sample's method shares track the
population's as closely as 100 slots allow.

Selection reads only neutral metadata: generation method, repository,
language, size. ``assert_neutral`` refuses to run if a taxonomy or review
field has reached the population manifest, and no classifier is ever run over
the population beforehand.

Outputs:
    data/review_manifest.csv            reviewer-facing: case_id, repo,
                                        language, packet path. NO generation
                                        method: that could bias the review.
    data/hidden/sample_metadata.csv     the full record, reviewer-forbidden
    data/hidden/selection_record.json   seed, allocation, every distortion
    analysis/sample_balance.md          population versus sample, quantified
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.config import load_config  # noqa: E402
from ssr.paths import ANALYSIS, DATA, REVIEW_MANIFEST, ensure_dirs  # noqa: E402
from ssr.util import SsrError, seeded_rng, setup_logging, sha256_file, utc_now, write_json  # noqa: E402

POPULATION = DATA / "population" / "swesmith_training_tasks.csv"
HIDDEN = DATA / "hidden"

# Markers for TAXONOMY and REVIEW fields. Deliberately specific: a bare
# "family" would reject `method_family`, which is a bug-generation family and
# exactly the neutral metadata this sampler is supposed to stratify on.
FORBIDDEN_FIELD_MARKERS = (
    "failure_pattern",
    "failure_scope",
    "failure_family",
    "taxonomy",
    "pattern_family",
    "pattern_confidence",
    "reviewer",
    "review_result",
    "difficulty",
    "resolved",
)


def assert_neutral(rows: list[dict]) -> None:
    """Refuse a population that carries a taxonomy or review field."""
    offenders = {
        key for row in rows[:1] for key in row
        if any(marker in key.lower() for marker in FORBIDDEN_FIELD_MARKERS)
    }
    if offenders:
        raise SsrError(
            "the population manifest carries non-neutral fields: "
            + ", ".join(sorted(offenders))
            + ". Selection must not see them."
        )


def largest_remainder(counts: dict[str, int], total: int) -> dict[str, int]:
    """Proportional allocation of ``total`` slots across strata.

    Largest-remainder (Hamilton) apportionment: floor every exact share, then
    hand the leftover slots to the largest fractional remainders. It is the
    allocation that keeps each stratum's sample share closest to its
    population share, and it always sums to exactly ``total``.
    """
    population = sum(counts.values())
    if population == 0:
        return {}
    exact = {name: total * value / population for name, value in counts.items()}
    allocation = {name: int(value) for name, value in exact.items()}
    remaining = total - sum(allocation.values())
    order = sorted(
        counts, key=lambda name: (-(exact[name] - allocation[name]), -counts[name], name)
    )
    for name in order[:remaining]:
        allocation[name] += 1
    return allocation


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--population", default=str(POPULATION))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)
    config = load_config("sampling")

    path = Path(args.population)
    if not path.is_file():
        raise SsrError(f"{path} does not exist; run scripts/build_training_population.py first")
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert_neutral(rows)
    log.info("population: %d unique task instances", len(rows))

    seed = int(config["seed"])
    target = int(config["target_n"])
    stratum_field = str(config["primary_stratum"])
    max_per_repo = int(config["max_per_repo"])

    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_stratum[row[stratum_field]].append(row)
    population_counts = {name: len(items) for name, items in by_stratum.items()}
    allocation = largest_remainder(population_counts, target)

    # Deterministic order inside each stratum: sort, then a seeded shuffle.
    order: dict[str, int] = {}
    for name, items in by_stratum.items():
        ids = sorted(item["instance_id"] for item in items)
        rng = seeded_rng(seed, "stratum", name)
        rng.shuffle(ids)
        order.update({value: position for position, value in enumerate(ids)})

    selected: list[dict] = []
    repo_counts: Counter[str] = Counter()
    distortions: list[dict] = []

    for name in sorted(allocation, key=lambda n: (-population_counts[n], n)):
        wanted = allocation[name]
        pool = sorted(by_stratum[name], key=lambda item: order[item["instance_id"]])
        taken = 0
        skipped_for_cap = 0
        for row in pool:
            if taken >= wanted:
                break
            if repo_counts[row["upstream_repo"]] >= max_per_repo:
                skipped_for_cap += 1
                continue
            selected.append(row)
            repo_counts[row["upstream_repo"]] += 1
            taken += 1
        if skipped_for_cap:
            distortions.append({
                "type": "REPOSITORY_CAP_APPLIED", "stratum": name,
                "instances_skipped": skipped_for_cap, "cap": max_per_repo,
            })
        if taken < wanted:
            distortions.append({
                "type": "STRATUM_UNDERFILLED", "stratum": name,
                "wanted": wanted, "got": taken,
                "reason": "the repository cap left too few eligible instances",
            })

    # The cap can leave the sample short. Fill from the largest strata that
    # still have eligible instances, and record it.
    if len(selected) < target:
        chosen_ids = {row["instance_id"] for row in selected}
        spare = sorted(
            (row for row in rows
             if row["instance_id"] not in chosen_ids
             and repo_counts[row["upstream_repo"]] < max_per_repo),
            key=lambda item: order[item["instance_id"]],
        )
        added = 0
        for row in spare:
            if len(selected) >= target:
                break
            selected.append(row)
            repo_counts[row["upstream_repo"]] += 1
            added += 1
        if added:
            distortions.append({
                "type": "SHORTFALL_BACKFILL", "added": added,
                "note": "slots lost to the repository cap were refilled across strata",
            })

    if len(selected) != target:
        distortions.append({"type": "SAMPLE_SIZE_MISSED", "requested": target, "selected": len(selected)})

    # Neutral case IDs by seeded shuffle, so the index leaks no ordering.
    ids = sorted(row["instance_id"] for row in selected)
    seeded_rng(seed, "case-ids").shuffle(ids)
    fmt = str(config.get("case_id_format", "SWESMITH_{index:03d}"))
    case_ids = {value: fmt.format(index=position) for position, value in enumerate(ids, start=1)}

    records = sorted(
        ({**row, "case_id": case_ids[row["instance_id"]]} for row in selected),
        key=lambda row: row["case_id"],
    )

    sample_counts = Counter(row[stratum_field] for row in records)
    balance = []
    for name in sorted(population_counts, key=lambda n: -population_counts[n]):
        pop_share = population_counts[name] / len(rows)
        sam_share = sample_counts.get(name, 0) / max(1, len(records))
        balance.append({
            "stratum": name,
            "population_n": population_counts[name],
            "population_share": round(pop_share, 4),
            "allocated": allocation.get(name, 0),
            "sample_n": sample_counts.get(name, 0),
            "sample_share": round(sam_share, 4),
            "deviation": round(sam_share - pop_share, 4),
        })

    summary = {
        "population_size": len(rows),
        "selected": len(records),
        "seed": seed,
        "unique_repositories_in_sample": len(set(row["upstream_repo"] for row in records)),
        "max_from_one_repository": max(Counter(r["upstream_repo"] for r in records).values()),
        "largest_absolute_deviation": max(abs(row["deviation"]) for row in balance),
        "distortions": len(distortions),
    }

    if args.dry_run:
        print(json.dumps({"dry_run": True, **summary, "balance": balance,
                          "distortions": distortions}, indent=2))
        return 0

    # -- reviewer-facing manifest: no generation method ---------------------
    REVIEW_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_MANIFEST, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["case_id", "repo", "language", "packet_path"])
        for row in records:
            writer.writerow([row["case_id"], row["upstream_repo"], row["language"],
                             f"data/review_packets/{row['case_id']}"])

    # -- hidden metadata ----------------------------------------------------
    HIDDEN.mkdir(parents=True, exist_ok=True)
    hidden_csv = HIDDEN / "sample_metadata.csv"
    fieldnames = ["case_id"] + [k for k in records[0] if k != "case_id"]
    with open(hidden_csv, "w", encoding="utf-8", newline="") as handle:
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
        "sampling_config_sha256": config.sha256,
        "population_file": str(path),
        "population_sha256": sha256_file(path),
        "summary": summary,
        "allocation": allocation,
        "balance": balance,
        "distortions": distortions,
        "selection": [{"case_id": r["case_id"], "instance_id": r["instance_id"]} for r in records],
    })

    # -- balance report -----------------------------------------------------
    lines = [
        "# Sample balance", "",
        f"Population: **{len(rows)}** unique SWE-smith task instances behind the",
        "official training trajectories for SWE-agent-LM-32B.",
        f"Sample: **{len(records)}** cases, seed `{seed}`, proportional",
        "largest-remainder allocation across `generation_method`.", "",
        "## Generation method", "",
        "| Method | Population | Share | Allocated | Sample | Share | Deviation |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in balance:
        lines.append(
            f"| `{row['stratum']}` | {row['population_n']} | {row['population_share']:.1%} | "
            f"{row['allocated']} | {row['sample_n']} | {row['sample_share']:.1%} | "
            f"{row['deviation']:+.1%} |"
        )
    lines += [
        "", f"Largest absolute deviation: **{summary['largest_absolute_deviation']:.1%}**.",
        "A deviation of about one percentage point is the granularity of a",
        "100-case sample: one case is one percent.", "",
        "## Repositories", "",
        f"- unique repositories in the sample: **{summary['unique_repositories_in_sample']}**",
        f"- most cases from any one repository: **{summary['max_from_one_repository']}** "
        f"(cap {max_per_repo})",
        "",
        "## Distortions", "",
    ]
    if distortions:
        for item in distortions:
            lines.append(f"- `{item['type']}`: {json.dumps({k: v for k, v in item.items() if k != 'type'})}")
    else:
        lines.append("None. The repository cap never bound, and every stratum was filled as allocated.")
    lines += ["", "## Language", "",
              "Every task in this population is Python: the pinned task corpus is",
              "Python-only. Language balancing is therefore a no-op, not a choice."]
    ANALYSIS.mkdir(parents=True, exist_ok=True)
    (ANALYSIS / "sample_balance.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    print(json.dumps({**summary, "review_manifest_sha256": sha256_file(REVIEW_MANIFEST)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
