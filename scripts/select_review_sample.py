#!/usr/bin/env python3
"""Select exactly 100 bugs for blind review (handoff sections 13 to 16).

    python scripts/select_review_sample.py
    python scripts/select_review_sample.py --dry-run

Selection is deterministic: the same pool and the same seed give the same 100
bugs on any machine. It reads only validation status, source and order
metadata, language and repository-size strata, deduplication status, and the
seed. ``assert_no_taxonomy_fields`` refuses the run if a taxonomy or review
field is present in the candidate records.

Outputs:
    data/review_manifest.csv                 neutral, reviewer-visible
    data/sampling/selection_record.json      hidden, the full account
    data/sampling/selection_crosswalk.csv    hidden, packet id -> bug id
    data/sampling/selection_deviations.json  every deviation from the target

The crosswalk is hidden metadata. A reviewer who reads it learns the source
allocation, so AGENTS.md and CLAUDE.md forbid opening data/sampling/.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.config import load_config  # noqa: E402
from ssr.paths import REVIEW_MANIFEST, SAMPLING, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.pool import eligible_entries  # noqa: E402
from ssr.sampling import (  # noqa: E402
    assert_no_taxonomy_fields,
    language_match_report,
    language_targets_from_profile,
    select,
)
from ssr.util import (  # noqa: E402
    SsrError,
    read_json,
    setup_logging,
    sha256_file,
    utc_now,
    write_json,
)

DEDUP_REPORT = SAMPLING / "dedup_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pool", default=str(VALIDATED_POOL))
    parser.add_argument("--dedup-report", default=str(DEDUP_REPORT))
    parser.add_argument("--dry-run", action="store_true", help="report the selection without writing it")
    parser.add_argument("--allow-scripted", action="store_true", help="include harness-proving candidates")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)
    config = load_config("sampling")

    entries = eligible_entries(
        Path(args.pool), Path(args.dedup_report), allow_scripted=args.allow_scripted
    )
    neutral = [entry.neutral_record() for entry in entries]
    assert_no_taxonomy_fields(neutral)
    log.info("sampling frame: %d eligible bug(s)", len(entries))

    matching = config.get("environment_matching", {}) or {}
    language_targets: dict[str, float] = {}
    profile_record: dict | None = None
    if matching.get("enabled", True):
        profile_path = Path(matching.get("profile", "data/sampling/aidev_environment_profile.json"))
        if not profile_path.is_absolute():
            profile_path = Path(__file__).resolve().parent.parent / profile_path
        if profile_path.is_file():
            profile_record = read_json(profile_path)
            language_targets = language_targets_from_profile(profile_record)
            log.info("language targets from the AIDev profile: %s", language_targets)
        else:
            log.warning("environment profile %s not found; selecting without a language target", profile_path)

    result = select([entry.to_candidate() for entry in entries], dict(config), language_targets=language_targets)

    language_report = language_match_report(
        result.selected, language_targets, float(matching.get("language_tolerance", 0.10))
    )

    selected_count = len(result.selected)
    if selected_count != int(config["target_n"]):
        result.deviations.append(
            {
                "type": "SAMPLE_SIZE_MISSED",
                "requested": int(config["target_n"]),
                "selected": selected_count,
            }
        )

    by_id = {entry.bug_id: entry for entry in entries}
    rows = []
    for candidate in result.selected:
        packet_id = result.packet_ids[candidate.bug_id]
        entry = by_id[candidate.bug_id]
        rows.append(
            {
                "packet_id": packet_id,
                "bug_id": candidate.bug_id,
                "stratum": candidate.stratum,
                "repo": candidate.repo,
                "language": candidate.language,
                "repo_size_bin": candidate.repo_size_bin,
                "parent_bug_id": candidate.parent_bug_id or "",
                "bug_order": entry.bug_order,
                "generation_strategy": entry.strategy,
            }
        )
    rows.sort(key=lambda row: row["packet_id"])

    summary = {
        "selected": selected_count,
        "allocation": result.allocation,
        "requested_allocation": result.requested_allocation,
        "unique_repos": result.unique_repos,
        "min_unique_repos": config.get("min_unique_repos"),
        "max_bugs_from_one_repo": result.diagnostics["max_bugs_from_one_repo"],
        "language_distribution": result.diagnostics["language_distribution"],
        "lineage_pairs": len(result.lineage_pairs),
        "deviations": len(result.deviations),
        "languages_out_of_tolerance": language_report["languages_out_of_tolerance"],
    }

    if args.dry_run:
        print(json.dumps({"dry_run": True, **summary, "packet_ids": [r["packet_id"] for r in rows]}, indent=2))
        return 0

    # Neutral, reviewer-visible manifest: packet ids only.
    REVIEW_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_MANIFEST, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["packet_id", "packet_path"])
        for row in rows:
            writer.writerow([row["packet_id"], f"data/review_packets/{row['packet_id']}"])

    # Hidden crosswalk and record.
    crosswalk_path = Path(config.get_path("outputs.crosswalk", "data/sampling/selection_crosswalk.csv"))
    if not crosswalk_path.is_absolute():
        crosswalk_path = Path(__file__).resolve().parent.parent / crosswalk_path
    crosswalk_path.parent.mkdir(parents=True, exist_ok=True)
    with open(crosswalk_path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    record = {
        "generated_at_utc": utc_now(),
        "sampling_config_sha256": config.sha256,
        "seed": config["seed"],
        "pool": str(Path(args.pool)),
        "dedup_report": str(Path(args.dedup_report)),
        "dedup_report_sha256": sha256_file(Path(args.dedup_report))
        if Path(args.dedup_report).is_file()
        else None,
        "frame_size": len(entries),
        "summary": summary,
        "diagnostics": result.diagnostics,
        "language_match": language_report,
        "environment_profile_sha256": (profile_record or {}).get("profile_sha256"),
        "lineage_pairs": result.lineage_pairs,
        "selection": rows,
        "taxonomy_blind": True,
        "note": (
            "The 30/30/40 allocation is a study-design choice, not a claim about the "
            "natural published SSR mixture. Report source-specific results, and pooled "
            "results only with the stratification caveat."
        ),
    }
    write_json(SAMPLING / "selection_record.json", record)
    write_json(SAMPLING / "selection_deviations.json", {
        "generated_at_utc": utc_now(),
        "deviations": result.deviations,
    })

    manifest_hash = sha256_file(REVIEW_MANIFEST)
    write_json(
        SAMPLING / "review_manifest_freeze.json",
        {
            "frozen_at_utc": utc_now(),
            "review_manifest": str(REVIEW_MANIFEST.relative_to(Path(__file__).resolve().parent.parent)),
            "sha256": manifest_hash,
            "rows": len(rows),
        },
    )

    log.info("selected %d bug(s) across %d repositories", selected_count, result.unique_repos)
    print(json.dumps({**summary, "review_manifest_sha256": manifest_hash}, indent=2))
    if result.deviations:
        print("\ndeviations recorded in data/sampling/selection_deviations.json:")
        for deviation in result.deviations[:20]:
            print(f"  {deviation}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
