"""Deterministic selection of the 100-bug blind-review sample.

Handoff sections 13, 14, 15 and 16. Selection may depend only on:

    * validation status,
    * source and order metadata,
    * language and repository-size strata,
    * deduplication status,
    * the fixed seed.

It must NOT depend on any failure taxonomy label. ``assert_no_taxonomy_fields``
enforces that on the candidate records before anything is selected, so a
contaminated input is a crash rather than a quiet bias.

The procedure is a seeded greedy pass, not a plain shuffle-and-take, because
three constraints have to hold at once: the per-repository ceiling, the
unique-repository floor, and the language match to the neutral AIDev
environment profile. The greedy pass picks, at every step, the feasible
candidate that most reduces the current language deficit, and breaks ties by
a seeded permutation. Given the same pool and the same seed it produces the
same 100 bugs on any machine.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from ssr.util import SsrError, seeded_rng

SOURCE_STRATA = (
    "first_order_removal",
    "first_order_history_reversion",
    "second_order_failed_solver",
)

STRATEGY_TO_STRATUM = {
    ("REMOVAL", 1): "first_order_removal",
    ("HISTORY_REVERSION", 1): "first_order_history_reversion",
    ("FAILED_SOLVER", 2): "second_order_failed_solver",
}

# Any of these substrings in a candidate field name means a taxonomy label
# leaked into the sampling input.
FORBIDDEN_FIELD_MARKERS = (
    "failure_pattern",
    "failure_scope",
    "taxonomy",
    "family",
    "pattern_confidence",
    "review",
    "label",
)


@dataclass
class Candidate:
    """The neutral facts sampling is allowed to use."""

    bug_id: str
    stratum: str
    repo: str
    language: str
    repo_size_bin: str = "UNKNOWN"
    parent_bug_id: str | None = None
    base_state_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "bug_id": self.bug_id,
            "stratum": self.stratum,
            "repo": self.repo,
            "language": self.language,
            "repo_size_bin": self.repo_size_bin,
            "parent_bug_id": self.parent_bug_id,
            "base_state_key": self.base_state_key,
        }


@dataclass
class SelectionResult:
    selected: list[Candidate]
    packet_ids: dict[str, str]
    allocation: dict[str, int]
    requested_allocation: dict[str, int]
    deviations: list[dict[str, Any]] = field(default_factory=list)
    lineage_pairs: list[dict[str, str]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    @property
    def unique_repos(self) -> int:
        return len({candidate.repo for candidate in self.selected})


def assert_no_taxonomy_fields(records: Iterable[dict[str, Any]]) -> None:
    """Refuse to sample from records that carry a taxonomy label."""
    offenders: set[str] = set()
    for record in records:
        for key in record:
            lowered = key.lower()
            if any(marker in lowered for marker in FORBIDDEN_FIELD_MARKERS):
                offenders.add(key)
    if offenders:
        raise SsrError(
            "sampling input carries taxonomy or review fields: "
            + ", ".join(sorted(offenders))
            + ". Selection must be taxonomy-blind; remove these fields from the "
            "candidate records."
        )


def stratum_for(strategy: str, bug_order: int) -> str:
    key = (strategy, int(bug_order))
    if key not in STRATEGY_TO_STRATUM:
        raise SsrError(f"no sampling stratum for strategy={strategy!r} order={bug_order!r}")
    return STRATEGY_TO_STRATUM[key]


# ----------------------------------------------------------------------
def allocate(
    available: dict[str, int], targets: dict[str, int], total: int, fill_order: Sequence[str]
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Apply the handoff shortfall rule to the requested allocation.

    1. take up to the target from each stratum;
    2. redistribute the shortfall over the remaining strata in ``fill_order``,
       splitting the first-order fill as evenly as the supply allows;
    3. record every deviation.
    """
    allocation = {name: min(targets.get(name, 0), available.get(name, 0)) for name in SOURCE_STRATA}
    deviations: list[dict[str, Any]] = []

    for name in SOURCE_STRATA:
        requested = targets.get(name, 0)
        if allocation[name] < requested:
            deviations.append(
                {
                    "type": "STRATUM_SHORTFALL",
                    "stratum": name,
                    "requested": requested,
                    "available": available.get(name, 0),
                    "allocated": allocation[name],
                }
            )

    shortfall = total - sum(allocation.values())
    if shortfall > 0:
        first_order = [name for name in fill_order if name.startswith("first_order")]
        others = [name for name in fill_order if not name.startswith("first_order")]
        # Non-first-order strata absorb what they can first, then the two
        # first-order strata share the rest one at a time so they stay level.
        for name in others:
            room = available.get(name, 0) - allocation[name]
            take = min(room, shortfall)
            if take > 0:
                allocation[name] += take
                shortfall -= take
                deviations.append(
                    {"type": "SHORTFALL_FILL", "stratum": name, "added": take}
                )
        added: Counter[str] = Counter()
        while shortfall > 0:
            candidates = [
                name for name in first_order if available.get(name, 0) - allocation[name] > 0
            ]
            if not candidates:
                break
            name = min(candidates, key=lambda item: (added[item], first_order.index(item)))
            allocation[name] += 1
            added[name] += 1
            shortfall -= 1
        for name, count in sorted(added.items()):
            deviations.append({"type": "SHORTFALL_FILL", "stratum": name, "added": count})

    if sum(allocation.values()) < total:
        deviations.append(
            {
                "type": "POOL_TOO_SMALL",
                "requested_total": total,
                "allocated_total": sum(allocation.values()),
                "available": dict(available),
            }
        )
    return allocation, deviations


# ----------------------------------------------------------------------
def select(
    candidates: Sequence[Candidate],
    config: dict[str, Any],
    *,
    language_targets: dict[str, float] | None = None,
) -> SelectionResult:
    seed = int(config["seed"])
    total = int(config["target_n"])
    targets = dict(config["target_sources"])
    max_per_repo = int(config.get("max_per_repo", 4))
    min_unique_repos = int(config.get("min_unique_repos", 25))
    avoid_lineage = bool(config.get("avoid_parent_child_pairs", True))
    avoid_same_base = bool(config.get("avoid_same_base_state", True))
    fill_order = config.get("shortfall_policy", {}).get("fill_order", list(SOURCE_STRATA))

    by_stratum: dict[str, list[Candidate]] = {name: [] for name in SOURCE_STRATA}
    for candidate in candidates:
        if candidate.stratum not in by_stratum:
            raise SsrError(f"{candidate.bug_id}: unknown stratum {candidate.stratum!r}")
        by_stratum[candidate.stratum].append(candidate)

    available = {name: len(items) for name, items in by_stratum.items()}
    allocation, deviations = allocate(available, targets, total, fill_order)

    # Deterministic tie-break order inside each stratum.
    order: dict[str, int] = {}
    for name, items in by_stratum.items():
        ids = sorted(item.bug_id for item in items)
        rng = seeded_rng(seed, "stratum-order", name)
        rng.shuffle(ids)
        for position, bug_id in enumerate(ids):
            order[bug_id] = position

    selected: list[Candidate] = []
    repo_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    chosen_ids: set[str] = set()
    base_states: set[str] = set()

    def feasible(candidate: Candidate, *, relax: set[str] | None = None) -> bool:
        relax = relax or set()
        if candidate.bug_id in chosen_ids:
            return False
        if "repo" not in relax and repo_counts[candidate.repo] >= max_per_repo:
            return False
        if avoid_lineage and "lineage" not in relax:
            if candidate.parent_bug_id and candidate.parent_bug_id in chosen_ids:
                return False
            if any(other.parent_bug_id == candidate.bug_id for other in selected):
                return False
        if avoid_same_base and "base" not in relax:
            if candidate.base_state_key and candidate.base_state_key in base_states:
                return False
        return True

    def take(candidate: Candidate) -> None:
        selected.append(candidate)
        chosen_ids.add(candidate.bug_id)
        repo_counts[candidate.repo] += 1
        language_counts[candidate.language] += 1
        if candidate.base_state_key:
            base_states.add(candidate.base_state_key)

    def language_cost(candidate: Candidate) -> float:
        """Lower is better: how far this pick leaves us from the profile."""
        if not language_targets:
            return 0.0
        target = language_targets.get(candidate.language, 0.0)
        picked = len(selected) + 1
        have = (language_counts[candidate.language] + 1) / picked
        return abs(have - target)

    relaxations: list[tuple[str, set[str]]] = [
        ("strict", set()),
        ("allow_same_base_state", {"base"}),
        ("allow_parent_child_pairs", {"base", "lineage"}),
        ("allow_repo_ceiling", {"base", "lineage", "repo"}),
    ]

    for name in SOURCE_STRATA:
        wanted = allocation[name]
        pool = sorted(by_stratum[name], key=lambda item: order[item.bug_id])
        for _ in range(wanted):
            picked: Candidate | None = None
            used_relaxation = "strict"
            for label, relax in relaxations:
                choices = [item for item in pool if feasible(item, relax=relax)]
                if choices:
                    picked = min(choices, key=lambda item: (language_cost(item), order[item.bug_id]))
                    used_relaxation = label
                    break
            if picked is None:
                deviations.append(
                    {"type": "STRATUM_UNDERFILLED", "stratum": name, "wanted": wanted, "got": sum(
                        1 for item in selected if item.stratum == name)}
                )
                break
            if used_relaxation != "strict":
                deviations.append(
                    {
                        "type": "CONSTRAINT_RELAXED",
                        "stratum": name,
                        "bug_id": picked.bug_id,
                        "relaxation": used_relaxation,
                    }
                )
            take(picked)

    # Repair pass: raise the unique-repository count without changing the
    # stratum allocation, by swapping an over-represented repo for an unused one.
    unique = len({candidate.repo for candidate in selected})
    if unique < min_unique_repos:
        swaps = _raise_repo_diversity(
            selected, by_stratum, chosen_ids, repo_counts, order, min_unique_repos
        )
        for swap in swaps:
            deviations.append({"type": "DIVERSITY_SWAP", **swap})
        unique = len({candidate.repo for candidate in selected})
        if unique < min_unique_repos:
            deviations.append(
                {
                    "type": "UNIQUE_REPO_FLOOR_MISSED",
                    "required": min_unique_repos,
                    "achieved": unique,
                }
            )

    lineage_pairs = [
        {"parent": candidate.parent_bug_id or "", "child": candidate.bug_id}
        for candidate in selected
        if candidate.parent_bug_id and candidate.parent_bug_id in chosen_ids
    ]
    if lineage_pairs:
        deviations.append(
            {
                "type": "LINEAGE_PAIRS_PRESENT",
                "count": len(lineage_pairs),
                "note": "flagged for clustered or sensitivity analysis",
            }
        )

    packet_ids = assign_packet_ids(
        [candidate.bug_id for candidate in selected],
        seed=seed,
        fmt=str(config.get("packet_id_format", "SSR_{index:03d}")),
    )

    diagnostics = {
        "available_by_stratum": available,
        "selected_by_stratum": dict(Counter(candidate.stratum for candidate in selected)),
        "unique_repos": len({candidate.repo for candidate in selected}),
        "max_bugs_from_one_repo": max(repo_counts.values()) if repo_counts else 0,
        "language_distribution": dict(sorted(Counter(c.language for c in selected).items())),
        "repo_size_distribution": dict(sorted(Counter(c.repo_size_bin for c in selected).items())),
        "lineage_pairs": len(lineage_pairs),
    }

    return SelectionResult(
        selected=selected,
        packet_ids=packet_ids,
        allocation={name: sum(1 for c in selected if c.stratum == name) for name in SOURCE_STRATA},
        requested_allocation=targets,
        deviations=deviations,
        lineage_pairs=lineage_pairs,
        diagnostics=diagnostics,
    )


def _raise_repo_diversity(
    selected: list[Candidate],
    by_stratum: dict[str, list[Candidate]],
    chosen_ids: set[str],
    repo_counts: Counter,
    order: dict[str, int],
    min_unique_repos: int,
) -> list[dict[str, Any]]:
    """Swap surplus picks for candidates from repositories not yet used."""
    swaps: list[dict[str, Any]] = []
    used_repos = {candidate.repo for candidate in selected}
    guard = 0
    while len(used_repos) < min_unique_repos and guard < 1000:
        guard += 1
        # The most over-represented repository gives up its latest pick.
        donor_repo, donor_count = max(
            repo_counts.items(), key=lambda item: (item[1], item[0])
        )
        if donor_count <= 1:
            break
        donors = [candidate for candidate in selected if candidate.repo == donor_repo]
        donor = max(donors, key=lambda item: order[item.bug_id])

        replacement: Candidate | None = None
        for option in sorted(by_stratum[donor.stratum], key=lambda item: order[item.bug_id]):
            if option.bug_id in chosen_ids or option.repo in used_repos:
                continue
            replacement = option
            break
        if replacement is None:
            break

        selected.remove(donor)
        chosen_ids.discard(donor.bug_id)
        repo_counts[donor_repo] -= 1
        if repo_counts[donor_repo] <= 0:
            del repo_counts[donor_repo]
        selected.append(replacement)
        chosen_ids.add(replacement.bug_id)
        repo_counts[replacement.repo] += 1
        used_repos = {candidate.repo for candidate in selected}
        swaps.append(
            {
                "removed": donor.bug_id,
                "removed_repo": donor_repo,
                "added": replacement.bug_id,
                "added_repo": replacement.repo,
                "stratum": donor.stratum,
            }
        )
    return swaps


def assign_packet_ids(bug_ids: Sequence[str], *, seed: int, fmt: str) -> dict[str, str]:
    """Map internal bug IDs to neutral SSR_nnn identifiers.

    A seeded shuffle, so the packet index carries no information about the
    stratum, the repository or the generation order.
    """
    ordered = sorted(bug_ids)
    rng = seeded_rng(seed, "packet-ids")
    rng.shuffle(ordered)
    return {bug_id: fmt.format(index=position) for position, bug_id in enumerate(ordered, start=1)}


def language_targets_from_profile(profile: dict[str, Any]) -> dict[str, float]:
    """Read the neutral language mix out of the AIDev environment profile."""
    languages = profile.get("language_distribution") or {}
    total = sum(float(value) for value in languages.values())
    if total <= 0:
        return {}
    return {name: float(value) / total for name, value in languages.items()}


def language_match_report(
    selected: Sequence[Candidate], targets: dict[str, float], tolerance: float
) -> dict[str, Any]:
    counts = Counter(candidate.language for candidate in selected)
    total = max(1, len(selected))
    rows: list[dict[str, Any]] = []
    mismatches: list[str] = []
    for language in sorted(set(targets) | set(counts)):
        target = targets.get(language, 0.0)
        have = counts.get(language, 0) / total
        deviation = have - target
        rows.append(
            {
                "language": language,
                "target_proportion": round(target, 4),
                "sample_proportion": round(have, 4),
                "deviation": round(deviation, 4),
                "sample_count": counts.get(language, 0),
                "within_tolerance": abs(deviation) <= tolerance,
            }
        )
        if abs(deviation) > tolerance:
            mismatches.append(language)
    return {"tolerance": tolerance, "rows": rows, "languages_out_of_tolerance": mismatches}
