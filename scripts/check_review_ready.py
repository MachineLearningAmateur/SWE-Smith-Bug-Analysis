#!/usr/bin/env python3
"""Check that this checkout is ready for a blind review, on any machine.

    python scripts/check_review_ready.py
    python scripts/check_review_ready.py --reviewer claude
    python scripts/check_review_ready.py --json

This is the first command a reviewer runs. It needs no Docker, no API key and
no network: a review reads frozen files and writes JSON. It checks, in order:

1. the Python version and the two packages the review path needs;
2. the frozen taxonomy, re-hashed against its provenance record;
3. the corpus status, and whether it is research or a rehearsal;
4. every packet named by the snapshot manifest, re-hashed file by file;
5. the reviewer's own directory, and which case comes next.

Exit code 0 means a review can start. 1 means something must be fixed first,
and each failure line says what.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OK, WARN, FAIL = "OK", "WARN", "FAIL"

MIN_PYTHON = (3, 10)


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(self, check: str, status: str, detail: str, remedy: str = "") -> None:
        self.rows.append({"check": check, "status": status, "detail": detail, "remedy": remedy})

    @property
    def failures(self) -> list[dict]:
        return [row for row in self.rows if row["status"] == FAIL]

    def render(self) -> str:
        width = max(len(row["check"]) for row in self.rows)
        lines = []
        for row in self.rows:
            lines.append(f"{row['status']:<5} {row['check']:<{width}}  {row['detail']}")
            if row["remedy"] and row["status"] != OK:
                lines.append(f"{'':<5} {'':<{width}}  -> {row['remedy']}")
        return "\n".join(lines)


def check_python(report: Report) -> bool:
    version = sys.version_info
    if version >= MIN_PYTHON:
        report.add(
            "python",
            OK,
            f"{platform.python_version()} on {platform.system()} ({platform.machine()})",
        )
        return True
    report.add(
        "python",
        FAIL,
        f"{platform.python_version()}; {'.'.join(map(str, MIN_PYTHON))} or later is required",
        "install a newer Python, then re-run this check",
    )
    return False


def check_packages(report: Report) -> bool:
    ok = True
    for module, package in (("yaml", "pyyaml"), ("jsonschema", "jsonschema")):
        try:
            __import__(module)
            report.add(f"package {package}", OK, "importable")
        except ImportError:
            ok = False
            report.add(
                f"package {package}",
                FAIL,
                "not importable",
                "python -m pip install -r requirements-review.txt",
            )
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reviewer", choices=["codex", "claude"], default=None)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--skip-packet-hashes",
        action="store_true",
        help="skip the per-file re-hash of every packet (faster, weaker)",
    )
    args = parser.parse_args()

    report = Report()
    if not check_python(report) or not check_packages(report):
        # Nothing further can be imported reliably.
        print(report.render())
        print("\nFix the above first; the rest of the check needs these.")
        return 1

    # Imported here: they need the packages checked above.
    from ssr.corpus import read_status, status_banner  # noqa: E402
    from ssr.paths import REVIEWERS, REVIEW_PACKETS, REVIEW_SNAPSHOT_MANIFEST  # noqa: E402
    from ssr.review_formats import codec_for  # noqa: E402
    from ssr.review_workflow import ReviewerPaths, expected_case_ids  # noqa: E402
    from ssr.taxonomy import verify_provenance  # noqa: E402
    from ssr.util import SsrError, read_json, sha256_file  # noqa: E402

    try:
        provenance = verify_provenance()
        report.add(
            "frozen taxonomy",
            OK,
            f"{provenance['taxonomy_version']}, mapping {provenance['mapping_sha256'][:16]}",
        )
    except SsrError as exc:
        report.add(
            "frozen taxonomy",
            FAIL,
            str(exc).splitlines()[0],
            "the taxonomy has been altered; restore it from git before reviewing",
        )

    corpus_kind = "UNKNOWN"
    try:
        status = read_status()
        corpus_kind = status.corpus_kind
        report.add(
            "corpus",
            OK if status.is_research else WARN,
            f"{status.corpus_kind}, {status.packet_count} packet(s), built {status.built_at_utc}",
            "" if status.is_research else
            "this is a rehearsal corpus; a review of it tests the workflow and "
            "must not be reported as a research result",
        )
    except SsrError as exc:
        report.add(
            "corpus",
            FAIL,
            str(exc).splitlines()[0],
            "this checkout has no corpus yet; obtain one that does, or build the packets",
        )

    if not REVIEW_SNAPSHOT_MANIFEST.is_file():
        report.add(
            "snapshot manifest",
            FAIL,
            f"{REVIEW_SNAPSHOT_MANIFEST.name} is absent",
            "the frozen evidence list is missing; this checkout cannot be reviewed",
        )
    else:
        manifest = read_json(REVIEW_SNAPSHOT_MANIFEST)
        packets = manifest.get("packets", [])
        report.add(
            "snapshot manifest",
            OK,
            f"{len(packets)} packet(s), sha256 {sha256_file(REVIEW_SNAPSHOT_MANIFEST)[:16]}",
        )

        missing: list[str] = []
        altered: list[str] = []
        checked = 0
        for entry in packets:
            directory = REVIEW_PACKETS / entry["case_id"]
            if not directory.is_dir():
                missing.append(entry["case_id"])
                continue
            if args.skip_packet_hashes:
                continue
            for relative, expected in (entry.get("files") or {}).items():
                path = directory / relative
                if not path.is_file() or sha256_file(path) != expected:
                    altered.append(f"{entry['case_id']}/{relative}")
                    break
                checked += 1

        if missing:
            report.add(
                "packet files",
                FAIL,
                f"{len(missing)} packet(s) absent, first: {missing[:3]}",
                "the checkout is incomplete; pull the packets before reviewing",
            )
        elif altered:
            report.add(
                "packet integrity",
                FAIL,
                f"{len(altered)} file(s) do not match the frozen hash, first: {altered[:3]}",
                "the evidence has changed since it was frozen; a review of it would be void. "
                "Restore the packets with: git checkout -- data/review_packets",
            )
        elif args.skip_packet_hashes:
            report.add("packet integrity", WARN, "skipped by request")
        else:
            report.add("packet integrity", OK, f"{checked} file(s) match the frozen hashes")

    reviewers = [args.reviewer] if args.reviewer else list(REVIEWERS)
    for reviewer in reviewers:
        paths = ReviewerPaths(reviewer)
        try:
            expected = expected_case_ids()
        except SsrError:
            break
        codec = codec_for(reviewer)
        done = sorted(codec.case_id_of(path.name) for path in paths.case_files())
        remaining = [case_id for case_id in expected if case_id not in set(done)]
        if paths.complete.is_file():
            report.add(f"reviewer {reviewer}", OK,
                       f"COMPLETE, {len(done)} case(s) recorded in {codec.name} format")
        elif done:
            report.add(
                f"reviewer {reviewer}",
                OK,
                f"in progress, {len(done)} of {len(expected)} done, next "
                f"{remaining[0] if remaining else '(none)'}{codec.extension}",
            )
        else:
            report.add(
                f"reviewer {reviewer}",
                OK,
                f"not started, {len(expected)} case(s) to do in {codec.name} format, "
                f"first {expected[0] if expected else '(none)'}{codec.extension}",
            )

    if args.json:
        print(json.dumps({"corpus_kind": corpus_kind, "checks": report.rows}, indent=2))
        return 1 if report.failures else 0

    print(status_banner())
    print()
    print(report.render())
    print()
    if report.failures:
        print(f"{len(report.failures)} problem(s) must be fixed before a review can start.")
        return 1

    who = args.reviewer or "<codex|claude>"
    instructions = "AGENTS.md" if args.reviewer == "codex" else "CLAUDE.md" if args.reviewer == "claude" else "AGENTS.md (Codex) or CLAUDE.md (Claude)"
    print("This checkout is ready for review.")
    print(f"  1. Read taxonomy/frozen_failure_taxonomy_v1.md, then {instructions}.")
    fmt = codec_for(args.reviewer).name if args.reviewer else "your reviewer's"
    ext = codec_for(args.reviewer).extension if args.reviewer else ""
    print(f"  2. Work through the cases, saving one {fmt} file each "
          f"(SWESMITH_nnn{ext}) under reviews/{who}/cases/.")
    print(f"  3. Finish with: python scripts/validate_review_output.py --reviewer {who} --finalise")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
