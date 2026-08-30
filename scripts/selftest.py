#!/usr/bin/env python3
"""Prove this checkout works on this machine, offline, end to end.

    python scripts/selftest.py
    python scripts/selftest.py --keep      # leave the scratch directory behind

Runs the review path end to end against a throwaway reviews root: the frozen
packets are verified, two placeholder reviewers fill in all 100 cases, both
finalise, and the analysis runs. Nothing under ``reviews/`` or ``analysis/`` in
the checkout is touched, and the frozen packets are only read.

It needs no Docker and no API key. Two steps reach the network: the field-
semantics check fetches two mirror branches, and the packet data comes from
the pinned dataset cache. Run it after cloning and after changing anything
under ``ssr/`` or ``scripts/``.

The placeholder reviews are written into the scratch reviews root and deleted
with it, so they can never be mistaken for real results.
"""

from __future__ import annotations

import argparse
import os
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
    bundle = scratch / "bundle"
    return [
        Step("unit tests", ["-m", "pytest", "tests", "-q"]),
        Step(
            "reviewer preflight",
            ["scripts/check_review_ready.py"],
            expect=["ready for review", "RESEARCH"],
        ),
        Step(
            "verify the SWE-smith field semantics",
            ["scripts/verify_swesmith_semantics.py", "--n", "2",
             "--out", str(scratch / "reconstruction.json")],
            expect=["PATCH_APPLIES_TO_CLEAN", "PATCH_EQUALS_BUG_COMMIT"],
        ),
        Step("simulate two reviews", ["tests/simulate_reviews.py"],
             expect=["100 placeholder case(s)"]),
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
        Step("derive families", ["scripts/apply_frozen_families.py"], expect=["cohens_kappa"]),
        Step("compare by generation method", ["scripts/compare_reviews.py"],
             expect=["procedural", "llm", "mirror"]),
        Step(
            "export a review bundle",
            ["scripts/make_review_bundle.py", "--reviewer", "claude",
             "--out", str(bundle), "--force"],
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
    # The DATA root is NOT redirected: the frozen packets live there and are
    # read-only for this run. Only the writable roots move.
    env["SSR_REVIEWS_ROOT"] = str(scratch / "reviews")
    env["SSR_ANALYSIS_ROOT"] = str(scratch / "analysis")
    env["SSR_WORKSPACE_ROOT"] = str(scratch / "workspace")
    env["PYTHONDONTWRITEBYTECODE"] = "1"

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
    print("The frozen packets were read, never written; reviews and analysis went to scratch.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
