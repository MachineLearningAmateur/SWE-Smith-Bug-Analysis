#!/usr/bin/env python3
"""Export a self-contained checkout for one independent reviewer.

    python scripts/make_review_bundle.py --reviewer claude --out ../claude_review
    python scripts/make_review_bundle.py --reviewer codex --out ../codex_review --zip

A bundle is the strongest form of blind review: the hidden generation
metadata, the sampling crosswalk, the other reviewer's directory and the
analysis are not merely forbidden, they are absent. Hand the bundle to
whoever is doing the review, on whatever machine they have.

What goes in:

    taxonomy/            the frozen taxonomy and its provenance
    schemas/             the review-result and review-packet schemas
    docs/review_protocol.md
    data/review_packets/ the frozen packets
    data/review_manifest.csv, review_snapshot_manifest.json, CORPUS_STATUS.json
    ssr/                 only the library modules the review path imports
    scripts/             check_review_ready.py, validate_review_output.py
    reviews/<reviewer>/  empty, ready to fill
    AGENTS.md or CLAUDE.md, whichever belongs to this reviewer
    README.md            written for this bundle, not for the research repo

What stays out: data/sampling, data/generated_pool, data/validated_pool,
data/rejected, runs, analysis, configs, prompts, the other reviewer's
directory, and every generation script.

The bundle is verified before the command reports success: the export is
discarded if any excluded path appears inside it, and the packet hashes are
re-checked against the snapshot manifest in the bundle itself.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.corpus import read_status  # noqa: E402
from ssr.paths import DATA, REPO_ROOT, REVIEWERS, REVIEW_PACKETS  # noqa: E402
from ssr.util import (  # noqa: E402
    SsrError,
    force_rmtree,
    read_json,
    setup_logging,
    sha256_file,
    utc_now,
    write_text,
)

# Modules the review path imports. Listed explicitly rather than copying
# ssr/ wholesale, so a bundle cannot ship the generation code by accident.
LIBRARY_MODULES = (
    "__init__.py",
    "paths.py",
    "util.py",
    "taxonomy.py",
    "corpus.py",
    "review_workflow.py",
    "validate_review.py",
)

REVIEW_SCRIPTS = ("check_review_ready.py", "validate_review_output.py")

FORBIDDEN_IN_BUNDLE = (
    "data/sampling",
    "data/generated_pool",
    "data/validated_pool",
    "data/rejected",
    "runs/",
    "analysis/",
    "configs/",
    "prompts/",
    "workspace/",
    "metadata.json",
    "trajectory.jsonl",
    "solver_result.json",
    "pred_patch.diff",
    "selection_crosswalk",
)

BUNDLE_README = """\
# Blind review bundle - {reviewer}

This is a self-contained checkout for one independent reviewer. It holds the
frozen evidence packets, the frozen taxonomy, and the tooling needed to record
and validate a review. It holds nothing about how the bugs were made.

## Start here

1. Install the two packages the review needs:

       python -m pip install -r requirements-review.txt

2. Check the bundle:

       python scripts/check_review_ready.py --reviewer {reviewer}

3. Read `taxonomy/frozen_failure_taxonomy_v1.md` in full, once, then read
   `{instructions}`.

4. Work through the cases. Save one JSON file per bug, immediately, at
   `reviews/{reviewer}/cases/SSR_nnn.json`. Never batch.

5. Validate as you go, and finish:

       python scripts/validate_review_output.py --reviewer {reviewer} --case SSR_001
       python scripts/validate_review_output.py --reviewer {reviewer} --finalise

## Returning the review

Send back the whole `reviews/{reviewer}/` directory. Nothing else in this
bundle changes.

## Requirements

Python 3.10 or later, on any operating system. No Docker, no API key and no
network access are needed: a review reads frozen files and writes JSON.

## Corpus

**{corpus_kind}.** {corpus_note}

Exported {exported_at} from the SSR/SWE-smith coverage study.
Snapshot manifest SHA-256 `{snapshot_sha}`.
"""

CLAUDE_BUNDLE_SETTINGS = {
    "$schema": "https://json.schemastore.org/claude-code-settings.json",
    "permissions": {
        "allow": [
            "Read(./data/review_packets/**)",
            "Read(./taxonomy/**)",
            "Read(./docs/**)",
            "Read(./schemas/**)",
            "Write(./reviews/claude/**)",
            "Edit(./reviews/claude/**)",
        ]
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--reviewer", required=True, choices=list(REVIEWERS))
    parser.add_argument("--out", required=True, help="directory to create")
    parser.add_argument("--zip", action="store_true", help="also write <out>.zip")
    parser.add_argument("--force", action="store_true", help="replace an existing output directory")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    status = read_status()

    out = Path(args.out).resolve()
    if out.exists():
        if not args.force:
            raise SsrError(f"{out} already exists; pass --force to replace it")
        force_rmtree(out)
    out.mkdir(parents=True)

    # 1. frozen inputs
    shutil.copytree(REPO_ROOT / "taxonomy", out / "taxonomy")
    shutil.copytree(REPO_ROOT / "schemas", out / "schemas")
    (out / "docs").mkdir()
    shutil.copy2(REPO_ROOT / "docs" / "review_protocol.md", out / "docs" / "review_protocol.md")

    # 2. the evidence
    data_out = out / "data"
    data_out.mkdir()
    # The evidence follows the data root, so a bundle can be exported from a
    # self-test run as readily as from the checkout.
    shutil.copytree(REVIEW_PACKETS, data_out / "review_packets")
    for name in ("review_manifest.csv", "review_snapshot_manifest.json", "CORPUS_STATUS.json"):
        source = DATA / name
        if source.is_file():
            shutil.copy2(source, data_out / name)

    # 3. the library, module by module
    (out / "ssr").mkdir()
    for module in LIBRARY_MODULES:
        shutil.copy2(REPO_ROOT / "ssr" / module, out / "ssr" / module)

    # 4. the two scripts a reviewer runs
    (out / "scripts").mkdir()
    for script in REVIEW_SCRIPTS:
        shutil.copy2(REPO_ROOT / "scripts" / script, out / "scripts" / script)

    # 5. this reviewer's empty directory
    (out / "reviews" / args.reviewer / "cases").mkdir(parents=True)
    write_text(out / "reviews" / args.reviewer / "cases" / ".gitkeep", "")

    # 6. instructions, requirements, line-ending and ignore rules
    instructions = "AGENTS.md" if args.reviewer == "codex" else "CLAUDE.md"
    shutil.copy2(REPO_ROOT / instructions, out / instructions)
    shutil.copy2(REPO_ROOT / "requirements-review.txt", out / "requirements-review.txt")
    shutil.copy2(REPO_ROOT / ".gitattributes", out / ".gitattributes")
    write_text(out / ".gitignore", "__pycache__/\n*.py[cod]\n.venv/\n.pytest_cache/\n")

    if args.reviewer == "claude":
        (out / ".claude").mkdir()
        write_text(
            out / ".claude" / "settings.json",
            json.dumps(CLAUDE_BUNDLE_SETTINGS, indent=2) + "\n",
        )

    write_text(
        out / "README.md",
        BUNDLE_README.format(
            reviewer=args.reviewer,
            instructions=instructions,
            corpus_kind=status.corpus_kind,
            corpus_note=status.note,
            exported_at=utc_now(),
            snapshot_sha=status.snapshot_manifest_sha256,
        ),
    )

    # -- verification, before the command reports success -----------------
    exported = sorted(path for path in out.rglob("*") if path.is_file())
    leaks = [
        path.relative_to(out).as_posix()
        for path in exported
        if any(term in path.relative_to(out).as_posix() for term in FORBIDDEN_IN_BUNDLE)
    ]
    if leaks:
        force_rmtree(out)
        raise SsrError(
            "the bundle would have contained excluded material and was discarded:\n  "
            + "\n  ".join(leaks[:20])
        )

    manifest_path = data_out / "review_snapshot_manifest.json"
    if not manifest_path.is_file():
        force_rmtree(out)
        raise SsrError(
            "the bundle has no snapshot manifest; the source checkout has no frozen corpus"
        )
    manifest = read_json(manifest_path)
    altered: list[str] = []
    for entry in manifest.get("packets", []):
        directory = data_out / "review_packets" / entry["packet_id"]
        for relative, expected in (entry.get("files") or {}).items():
            path = directory / relative
            if not path.is_file() or sha256_file(path) != expected:
                altered.append(f"{entry['packet_id']}/{relative}")
    if altered:
        force_rmtree(out)
        raise SsrError(
            "packet hashes do not match inside the bundle; it was discarded:\n  "
            + "\n  ".join(altered[:20])
        )

    archive = None
    if args.zip:
        archive = out.with_suffix(".zip")
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            for path in exported:
                handle.write(path, path.relative_to(out.parent).as_posix())

    summary = {
        "reviewer": args.reviewer,
        "bundle": str(out),
        "zip": str(archive) if archive else None,
        "files": len(exported),
        "packets": len(manifest.get("packets", [])),
        "corpus_kind": status.corpus_kind,
        "snapshot_manifest_sha256": status.snapshot_manifest_sha256,
        "excluded_material_found": False,
        "packet_hashes_verified": True,
    }
    log.info("bundle written to %s (%d files)", out, len(exported))
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
