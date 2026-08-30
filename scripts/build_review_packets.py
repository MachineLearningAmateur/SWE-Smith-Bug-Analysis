#!/usr/bin/env python3
"""Build and freeze the neutral review packets (sections 17 and 22).

    python scripts/build_review_packets.py --env pvlib_python
    python scripts/build_review_packets.py --no-context   # skip source extraction

For each selected bug it writes data/review_packets/SSR_nnn/ holding the
clean-to-buggy diff, the buggy-state source around the change, the real output
of each failing oracle test, and the clean-versus-buggy test summary. Every
packet is checked against schemas/review_packet.schema.json and passed through
the leakage scan in ssr/packets.py before it is written.

Finally it writes data/review_snapshot_manifest.json: the path and SHA-256 of
every packet file, plus one digest per packet. Both reviewers record that
manifest's hash, so a change to the evidence during a review is detectable.

The environment is needed only to read the buggy-state source for the code
context. With --no-context the packets carry the diff and the test evidence
alone, which is enough to review but harder work for the reviewer.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.corpus import classify, isolation_of, write_status  # noqa: E402
from ssr.metrics import split_by_file  # noqa: E402
from ssr.packets import PacketBuilder, PacketSource, packet_digest, packet_file_hashes  # noqa: E402
from ssr.paths import (  # noqa: E402
    REVIEW_MANIFEST,
    REVIEW_PACKETS,
    REVIEW_SNAPSHOT_MANIFEST,
    SAMPLING,
    VALIDATED_POOL,
    ensure_dirs,
)
from ssr.pool import load_pool  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.taxonomy import taxonomy_fingerprint, verify_provenance  # noqa: E402
from ssr.util import SsrError, setup_logging, sha256_file, utc_now, write_json  # noqa: E402
from ssr.validate_review import validate_packet_file  # noqa: E402

CROSSWALK = SAMPLING / "selection_crosswalk.csv"


def load_crosswalk(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise SsrError(f"{path} does not exist; run scripts/select_review_sample.py first")
    with open(path, encoding="utf-8", newline="") as handle:
        return sorted(csv.DictReader(handle), key=lambda row: row["packet_id"])


def oracle_output(entry, test_name: str) -> str:
    """The lines of the buggy-state log that mention this test."""
    log = entry.artifacts.directory / "logs" / "BUG.log"
    if not log.is_file():
        return ""
    text = log.read_text(encoding="utf-8", errors="replace")
    short = test_name.split("::")[-1]
    keep: list[str] = []
    capture = False
    for line in text.splitlines():
        if test_name in line or short in line:
            capture = True
            keep.append(line)
            continue
        if capture:
            if line.strip() and not line.startswith((" ", "\t", "E ", ">")):
                capture = False
            else:
                keep.append(line)
    return "\n".join(keep[:400])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", default=None, help="environment used to read buggy-state source")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--no-context", action="store_true", help="omit code context files")
    parser.add_argument("--crosswalk", default=str(CROSSWALK))
    parser.add_argument("--pool", default=str(VALIDATED_POOL))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    ensure_dirs()
    log = setup_logging(args.verbose)
    verify_provenance()

    rows = load_crosswalk(Path(args.crosswalk))
    entries = {entry.bug_id: entry for entry in load_pool(Path(args.pool))}
    missing = [row["bug_id"] for row in rows if row["bug_id"] not in entries]
    if missing:
        raise SsrError(f"selected bugs are not in the validated pool: {missing[:5]}")

    env = None
    if not args.no_context:
        if not args.env:
            raise SsrError("pass --env to extract code context, or pass --no-context")
        env = get_environment(args.env, allow_smoke=args.allow_smoke).build()

    builder = PacketBuilder(REVIEW_PACKETS)
    built: list[dict] = []

    try:
        for row in rows:
            entry = entries[row["bug_id"]]
            validation = entry.validation
            diff = entry.artifacts.diff_text()
            fail_to_pass = list(validation.get("fail_to_pass") or [])
            if not fail_to_pass:
                raise SsrError(f"{entry.bug_id}: no oracle tests recorded; cannot build a packet")

            context: dict[str, str] = {}
            if env is not None:
                env.reset_to_clean()
                applied = env.apply_patch(diff)
                if not applied.ok:
                    raise SsrError(f"{entry.bug_id}: the diff does not apply: {applied.combined[:300]}")
                for path in sorted(split_by_file(diff)):
                    if env.exists(path):
                        context[path] = env.read_file(path, max_bytes=120_000)
                env.reset_to_clean()

            source = PacketSource(
                packet_id=row["packet_id"],
                # The neutral upstream project name, never the SWE-smith image.
                repo_name=entry.repo,
                language=entry.language,
                repo_commit=entry.source_commit,
                repo_size_bin=entry.repo_size_bin,
                bug_diff=diff,
                test_command=entry.artifacts.test_script.read_text(encoding="utf-8").strip(),
                clean_counts=_counts(validation, "CLEAN"),
                bug_counts=_counts(validation, "BUG"),
                fail_to_pass=fail_to_pass,
                oracle_outputs={name: oracle_output(entry, name) for name in fail_to_pass},
                code_context=context,
            )
            result = builder.build(source)
            validate_packet_file(Path(result["directory"]) / "packet.json")
            built.append({"packet_id": row["packet_id"], "files": len(result["files"])})
            log.info("built %s (%d file(s))", row["packet_id"], len(result["files"]))
    finally:
        if env is not None:
            env.close()

    packets = []
    for row in rows:
        directory = REVIEW_PACKETS / row["packet_id"]
        packets.append(
            {
                "packet_id": row["packet_id"],
                "path": f"data/review_packets/{row['packet_id']}",
                "digest": packet_digest(directory),
                "files": packet_file_hashes(directory),
            }
        )

    manifest = {
        "frozen_at_utc": utc_now(),
        "packet_count": len(packets),
        "taxonomy_fingerprint": taxonomy_fingerprint(),
        "review_manifest_sha256": sha256_file(REVIEW_MANIFEST) if REVIEW_MANIFEST.is_file() else "",
        "packets": packets,
        "note": (
            "Every reviewer must record this file's SHA-256 in review_metadata.json. "
            "If it changes during a review, that review is void."
        ),
    }
    write_json(REVIEW_SNAPSHOT_MANIFEST, manifest)

    # Mark the corpus. A rehearsal and a research corpus are reviewed the same
    # way, so without this marker their agreement statistics look identical.
    selected = [entries[row["bug_id"]] for row in rows]
    corpus_kind, reasons = classify(selected)
    isolation, backends = isolation_of(selected)
    status = write_status(corpus_kind, len(packets), isolation)
    if isolation != "CONTAINER":
        log.warning("environment isolation is %s: %s", isolation, backends)
    if reasons:
        log.warning("this corpus is a REHEARSAL: %s", "; ".join(reasons[:3]))

    print(json.dumps({
        "packets_built": len(built),
        "corpus_kind": status.corpus_kind,
        "environment_isolation": status.environment_isolation,
        "rehearsal_reasons": reasons[:5],
        "snapshot_manifest": str(REVIEW_SNAPSHOT_MANIFEST),
        "snapshot_manifest_sha256": status.snapshot_manifest_sha256,
    }, indent=2))
    return 0


def _counts(validation: dict, state: str) -> dict[str, int]:
    record = (validation.get("states") or {}).get(state) or {}
    return {
        "passed": len(record.get("passed") or []),
        "failed": len(record.get("failed") or []),
        "errored": len(record.get("errored") or []),
        "skipped": len(record.get("skipped") or []),
    }


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
