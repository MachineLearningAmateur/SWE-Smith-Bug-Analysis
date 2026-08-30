#!/usr/bin/env python3
"""Run the solver over validated first-order bugs and record the outcome.

    python scripts/run_solver.py --env pvlib_python --all
    python scripts/run_solver.py --env pvlib_python --bug BUG_0123456789ab

The solver is the same model as the injector. It sees the buggy repository and
the neutral failure evidence, and nothing about how the state was made.

This script only runs and records the repair attempt. Building a second-order
bug from a failed repair is a separate step, so that the two decisions stay
auditable: run scripts/build_second_order_bug.py afterwards.

Never tune anything here to make the solver fail. A low failure yield is a
result to report, not a problem to fix.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.artifacts import iter_pool, load_bug  # noqa: E402
from ssr.config import load_config  # noqa: E402
from ssr.model import build_model  # noqa: E402
from ssr.paths import PROMPTS, RUNS, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.solving import Solver, SolverError, second_order_eligible  # noqa: E402
from ssr.util import (  # noqa: E402
    SsrError,
    load_dotenv,
    setup_logging,
    utc_now,
    write_json,
    write_text,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True)
    parser.add_argument("--bug", action="append", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--scripted", default=None, help="JSON file of canned replies, for harness runs")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    ensure_dirs()
    log = setup_logging(args.verbose, RUNS / "solver.log")

    if args.all:
        candidates = iter_pool(VALIDATED_POOL)
    elif args.bug:
        candidates = [load_bug(VALIDATED_POOL / bug_id) for bug_id in args.bug]
    else:
        raise SsrError("pass --all or at least one --bug")

    first_order = []
    for artifacts in candidates:
        metadata = artifacts.metadata()
        if metadata.get("bug_order") == 1:
            first_order.append((artifacts, metadata))
    if not first_order:
        raise SsrError("no validated first-order bugs found")

    solver_config = dict(load_config("solver"))
    scripted = json.loads(Path(args.scripted).read_text(encoding="utf-8")) if args.scripted else None
    model = build_model(solver_config["model"], scripted=scripted)
    entry = get_environment(args.env, allow_smoke=args.allow_smoke)
    env = entry.build()

    attempts: list[dict] = []
    try:
        solver = Solver(model, env, solver_config, prompt_path=PROMPTS.parent / solver_config["prompt"])
        for artifacts, metadata in first_order:
            log.info("solving %s", artifacts.bug_id)
            try:
                attempt = solver.attempt(
                    artifacts,
                    artifacts.validation(),
                    trajectory_path=artifacts.directory / "solver_trajectory.jsonl",
                )
            except SolverError as exc:
                log.warning("%s: solver attempt failed: %s", artifacts.bug_id, exc)
                attempts.append({"bug_id": artifacts.bug_id, "oracle_result": "ERROR", "detail": str(exc)})
                continue

            write_text(artifacts.pred_patch, attempt.pred_patch)
            eligible, why = second_order_eligible(attempt, solver_config)
            record = {
                **attempt.to_record(),
                "bug_id": artifacts.bug_id,
                "second_order_eligible": eligible,
                "second_order_reason": why,
                "model": model.describe(),
                "recorded_at_utc": utc_now(),
            }
            write_json(artifacts.directory / "solver_result.json", record)
            attempts.append(
                {
                    "bug_id": artifacts.bug_id,
                    "oracle_result": attempt.oracle_result,
                    "second_order_eligible": eligible,
                    "reason": why,
                    "changed_lines": attempt.changed_lines,
                }
            )
            log.info(
                "%s: oracle %s, second-order eligible: %s (%s)",
                artifacts.bug_id, attempt.oracle_result, eligible, why,
            )
    finally:
        env.close()

    solved = sum(1 for row in attempts if row.get("oracle_result") == "PASSED")
    failed = sum(1 for row in attempts if row.get("oracle_result") == "FAILED")
    errored = sum(1 for row in attempts if row.get("oracle_result") == "ERROR")
    eligible = sum(1 for row in attempts if row.get("second_order_eligible"))
    summary = {
        "environment": entry.name,
        "attempted": len(attempts),
        "oracle_passed": solved,
        "oracle_failed": failed,
        "errored": errored,
        "second_order_eligible": eligible,
        "second_order_yield": round(eligible / len(attempts), 4) if attempts else None,
        "usage": model.total.to_dict(),
        "attempts": attempts,
        "finished_at_utc": utc_now(),
    }
    write_json(RUNS / "solver_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
