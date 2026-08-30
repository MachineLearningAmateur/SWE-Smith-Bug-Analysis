#!/usr/bin/env python3
"""Prove this checkout works on this machine, offline, end to end.

    python scripts/selftest.py
    python scripts/selftest.py --keep      # leave the scratch directory behind

Runs the whole downstream pipeline against a throwaway data root: a synthetic
pool is built, deduplicated, sampled, turned into packets, reviewed by two
placeholder reviewers, and analysed. Nothing in the checkout is touched, and
nothing goes over the network.

It takes a minute or two and needs no Docker and no API key. Run it after
cloning, after changing anything under ``ssr/`` or ``scripts/``, or whenever a
reviewer reports that something does not work on their machine.

The scratch corpus is marked REHEARSAL by ``ssr.corpus``, so even if a run
were left behind, its numbers could not be mistaken for research results.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.paths import REPO_ROOT  # noqa: E402
from ssr.util import force_rmtree  # noqa: E402

PYTHON = sys.executable


class Step:
    def __init__(
        self,
        name: str,
        argv: list[str],
        expect: list[str] | None = None,
        *,
        allow_nonzero: bool = False,
    ):
        self.name = name
        self.argv = argv
        self.expect = expect or []
        # Some steps report a finding through their exit code rather than
        # failing: the environment check exits 1 when Docker is absent, which
        # is a true statement about the machine, not a broken checkout.
        self.allow_nonzero = allow_nonzero
        self.status = "PENDING"
        self.detail = ""
        self.duration = 0.0


def run_step(step: Step, env: dict[str, str]) -> bool:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [PYTHON, *step.argv],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=1800,
        )
    except subprocess.TimeoutExpired:
        step.status, step.detail = "FAIL", "timed out after 30 minutes"
        step.duration = time.monotonic() - started
        return False
    step.duration = time.monotonic() - started
    output = (completed.stdout or "") + (completed.stderr or "")

    if completed.returncode != 0 and not step.allow_nonzero:
        step.status = "FAIL"
        tail = "\n".join(line for line in output.strip().splitlines()[-8:])
        step.detail = f"exit code {completed.returncode}\n{tail}"
        return False

    missing = [needle for needle in step.expect if needle not in output]
    if missing:
        step.status = "FAIL"
        step.detail = f"expected text absent from the output: {missing}"
        return False

    step.status = "OK"
    step.detail = _headline(output)
    return True


def _headline(output: str) -> str:
    for line in output.strip().splitlines():
        stripped = line.strip()
        if stripped.startswith('"') and ":" in stripped:
            return stripped.rstrip(",")
    return (output.strip().splitlines() or [""])[-1][:100]


def build_steps(scratch: Path) -> list[Step]:
    pool = scratch / "pool"
    dedup = scratch / "dedup_report.json"
    return [
        Step(
            "environment check",
            ["scripts/check_environment.py", "--json"],
            expect=["frozen taxonomy"],
            # Exits 1 when Docker is absent. That blocks a corpus run, not the
            # downstream pipeline this self-test exercises.
            allow_nonzero=True,
        ),
        Step("unit tests", ["-m", "pytest", "tests", "-q"]),
        Step(
            "build a synthetic pool",
            ["tests/make_synthetic_pool.py", "--out", str(pool), "--count", "200"],
            expect=['"bugs": 200'],
        ),
        Step(
            "deduplicate",
            ["scripts/deduplicate_bug_pool.py", "--pool", str(pool), "--report", str(dedup)],
            expect=['"kept"'],
        ),
        Step(
            "select the sample",
            [
                "scripts/select_review_sample.py",
                "--pool", str(pool),
                "--dedup-report", str(dedup),
                "--allow-scripted",
            ],
            expect=['"selected": 100'],
        ),
        Step(
            "build the review packets",
            ["scripts/build_review_packets.py", "--no-context", "--pool", str(pool)],
            expect=['"packets_built": 100', '"corpus_kind": "REHEARSAL"'],
        ),
        Step(
            "reviewer preflight",
            ["scripts/check_review_ready.py"],
            expect=["ready for review", "REHEARSAL"],
        ),
        Step("simulate two reviews", ["tests/simulate_reviews.py"], expect=["100 placeholder case(s)"]),
        Step(
            "finalise codex",
            ["scripts/validate_review_output.py", "--reviewer", "codex", "--finalise"],
            expect=['"finalised": true'],
        ),
        Step(
            "finalise claude",
            ["scripts/validate_review_output.py", "--reviewer", "claude", "--finalise"],
            expect=['"finalised": true'],
        ),
        Step(
            "derive families",
            ["scripts/apply_frozen_families.py"],
            expect=["cohens_kappa", "REHEARSAL"],
        ),
        Step(
            "compare by source",
            ["scripts/compare_reviews.py"],
            expect=["HISTORY_REVERSION", "REMOVAL", "SECOND_ORDER"],
        ),
        Step(
            "objective metrics",
            [
                "scripts/compute_patch_metrics.py",
                "--pool", str(pool),
                "--output", str(scratch / "metrics"),
            ],
            expect=['"bugs": 200'],
        ),
        Step(
            "export a review bundle",
            [
                "scripts/make_review_bundle.py",
                "--reviewer", "claude",
                "--out", str(scratch / "bundle"),
                "--force",
            ],
            expect=['"packet_hashes_verified": true', '"excluded_material_found": false'],
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--keep", action="store_true", help="do not delete the scratch directory")
    parser.add_argument("--scratch", default=None, help="use this directory instead of a temporary one")
    args = parser.parse_args()

    scratch = Path(args.scratch).resolve() if args.scratch else Path(
        tempfile.mkdtemp(prefix="ssr_selftest_")
    )
    scratch.mkdir(parents=True, exist_ok=True)

    # Redirect every writable root away from the checkout. The real data/,
    # reviews/ and analysis/ directories are not touched by this run.
    env = dict(os.environ)
    env["SSR_DATA_ROOT"] = str(scratch / "data")
    env["SSR_REVIEWS_ROOT"] = str(scratch / "reviews")
    env["SSR_ANALYSIS_ROOT"] = str(scratch / "analysis")
    env["SSR_WORKSPACE_ROOT"] = str(scratch / "workspace")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    # The AIDev environment profile is an input, not an output. Copy it in so
    # the language-matching path is exercised rather than skipped.
    profile = REPO_ROOT / "data" / "sampling" / "aidev_environment_profile.json"
    if profile.is_file():
        target = scratch / "data" / "sampling"
        target.mkdir(parents=True, exist_ok=True)
        shutil.copy2(profile, target / profile.name)

    print(f"scratch directory: {scratch}")
    print(f"python:            {PYTHON}")
    print(f"platform:          {sys.platform}")
    print()

    steps = build_steps(scratch)
    width = max(len(step.name) for step in steps)
    failed = False
    for step in steps:
        print(f"  {step.name:<{width}} ... ", end="", flush=True)
        ok = run_step(step, env)
        print(f"{step.status} ({step.duration:.1f}s)")
        if step.detail and (not ok or step.detail.startswith('"')):
            for line in step.detail.splitlines():
                print(f"  {'':<{width}}     {line}")
        if not ok:
            failed = True
            break

    if not args.keep:
        force_rmtree(scratch)
    else:
        print(f"\nscratch directory kept at {scratch}")

    print()
    if failed:
        print("SELFTEST FAILED. The step above did not pass; its output says why.")
        return 1
    print("SELFTEST PASSED. This checkout runs the full downstream pipeline on this machine.")
    print("Nothing under data/, reviews/ or analysis/ was modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
