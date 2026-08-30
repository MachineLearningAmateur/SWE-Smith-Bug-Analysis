"""Deterministic selection of the 100-case review sample.

The sample must PRESERVE the population's composition rather than impose a
balance, so allocation across generation methods is proportional by the
largest-remainder (Hamilton) method.

Selection is a pure function of (population, config, exclusions). That matters
for the re-run rule: when a selected task fails packet reconstruction, nobody
hand-picks a replacement. The failed instance goes on an exclusion list and
this function runs again with the SAME seed, so the replacement is as
determined as the original pick was.

Nothing here may read a taxonomy label. ``assert_neutral`` refuses a
population that carries one.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ssr.util import SsrError, seeded_rng

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


def assert_neutral(rows: Sequence[dict[str, Any]]) -> None:
    """Refuse a population that carries a taxonomy or review field."""
    offenders = {
        key
        for row in rows[:1]
        for key in row
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

    Floor every exact share, then hand the leftover slots to the largest
    fractional remainders. This is the allocation that keeps each stratum's
    sample share closest to its population share, and it always sums to
    exactly ``total``.
    """
    population = sum(counts.values())
    if population == 0:
        return {}
    exact = {name: total * value / population for name, value in counts.items()}
    allocation = {name: int(value) for name, value in exact.items()}
    remaining = total - sum(allocation.values())
    order = sorted(counts, key=lambda name: (-(exact[name] - allocation[name]), -counts[name], name))
    for name in order[:remaining]:
        allocation[name] += 1
    return allocation


@dataclass
class Selection:
    records: list[dict[str, Any]]
    allocation: dict[str, int]
    population_counts: dict[str, int]
    balance: list[dict[str, Any]]
    distortions: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, Any]:
        repos = Counter(row["upstream_repo"] for row in self.records)
        return {
            "population_size": sum(self.population_counts.values()),
            "selected": len(self.records),
            "unique_repositories_in_sample": len(repos),
            "max_from_one_repository": max(repos.values()) if repos else 0,
            "largest_absolute_deviation": max((abs(r["deviation"]) for r in self.balance), default=0.0),
            "distortions": len(self.distortions),
            "excluded_instances": len(self.excluded),
        }


def select(
    rows: Sequence[dict[str, Any]],
    config: dict[str, Any],
    *,
    exclusions: Iterable[str] = (),
) -> Selection:
    """Choose the sample. Deterministic in (rows, config, exclusions)."""
    assert_neutral(rows)

    excluded = sorted(set(exclusions))
    eligible = [row for row in rows if row["instance_id"] not in set(excluded)]
    if not eligible:
        raise SsrError("every population row is excluded")

    seed = int(config["seed"])
    target = int(config["target_n"])
    stratum_field = str(config["primary_stratum"])
    max_per_repo = int(config["max_per_repo"])

    by_stratum: dict[str, list[dict]] = defaultdict(list)
    for row in eligible:
        by_stratum[row[stratum_field]].append(row)
    population_counts = {name: len(items) for name, items in by_stratum.items()}
    allocation = largest_remainder(population_counts, target)

    # Deterministic order inside each stratum: sort, then a seeded shuffle.
    # The seed namespace is the stratum name, so excluding an instance
    # reshuffles nothing: the surviving order is unchanged and the
    # replacement is simply the next eligible instance.
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
                "type": "REPOSITORY_CAP_APPLIED",
                "stratum": name,
                "instances_skipped": skipped_for_cap,
                "cap": max_per_repo,
            })
        if taken < wanted:
            distortions.append({
                "type": "STRATUM_UNDERFILLED",
                "stratum": name,
                "wanted": wanted,
                "got": taken,
                "reason": "the repository cap left too few eligible instances",
            })

    # The cap can leave the sample short. Refill across strata, deterministically.
    if len(selected) < target:
        chosen = {row["instance_id"] for row in selected}
        spare = sorted(
            (row for row in eligible
             if row["instance_id"] not in chosen
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
                "type": "SHORTFALL_BACKFILL",
                "added": added,
                "note": "slots lost to the repository cap were refilled across strata",
            })

    if len(selected) != target:
        distortions.append({"type": "SAMPLE_SIZE_MISSED", "requested": target, "selected": len(selected)})

    records = assign_case_ids(selected, seed=seed, fmt=str(config.get("case_id_format", "SWESMITH_{index:03d}")))

    sample_counts = Counter(row[stratum_field] for row in records)
    total_pop = sum(population_counts.values())
    balance = []
    for name in sorted(population_counts, key=lambda n: -population_counts[n]):
        pop_share = population_counts[name] / total_pop
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

    if excluded:
        distortions.append({
            "type": "EXCLUSIONS_APPLIED",
            "count": len(excluded),
            "note": "instances that failed packet reconstruction; the sampler was re-run "
                    "with the same seed rather than a replacement being hand-picked",
        })

    return Selection(
        records=records,
        allocation=allocation,
        population_counts=population_counts,
        balance=balance,
        distortions=distortions,
        excluded=excluded,
    )


def assign_case_ids(rows: Sequence[dict[str, Any]], *, seed: int, fmt: str) -> list[dict[str, Any]]:
    """Attach neutral case IDs by a seeded shuffle.

    The index must carry no information: not the stratum, not the repository,
    not the order the sampler happened to pick them in.
    """
    ids = sorted(row["instance_id"] for row in rows)
    seeded_rng(seed, "case-ids").shuffle(ids)
    case_ids = {value: fmt.format(index=position) for position, value in enumerate(ids, start=1)}
    return sorted(
        ({**row, "case_id": case_ids[row["instance_id"]]} for row in rows),
        key=lambda row: row["case_id"],
    )
