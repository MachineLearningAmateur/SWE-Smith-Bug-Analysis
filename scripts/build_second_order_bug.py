#!/usr/bin/env python3
"""Turn genuinely failed repairs into second-order bug states.

    python scripts/build_second_order_bug.py --env pvlib_python --all

Reads solver_result.json next to each validated first-order bug. A parent is
used only when scripts/run_solver.py already recorded
``second_order_eligible: true``, that is, the repair was attempted honestly
and did not work.

The child's bug_inject.diff is the combined clean-to-buggy diff, taken from
the repository after both stages are applied. A reviewer therefore reads a
single diff against the clean upstream code and cannot tell the order from
the artifact shape.

The child still has to pass scripts/validate_bug.py before it joins the pool.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr import PROTOCOL_VERSION  # noqa: E402
from ssr.agent_loop import LoopLimits, make_forbidden_context  # noqa: E402
from ssr.artifacts import iter_pool, load_bug  # noqa: E402
from ssr.config import load_config  # noqa: E402
from ssr.generation import (  # noqa: E402
    GenerationRejected,
    check_weakening_scope,
    load_prompt_sections,
    run_weaken_stage,
)
from ssr.model import build_model  # noqa: E402
from ssr.paths import GENERATED_POOL, RUNS, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.solving import SolverError, build_second_order_state  # noqa: E402
from ssr.util import write_text  # noqa: E402
from ssr.validate_review import validate_generation_metadata  # noqa: E402
from ssr.util import (  # noqa: E402
    SsrError,
    load_dotenv,
    read_json,
    setup_logging,
    sha256_text,
    stable_id,
    utc_now,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True)
    parser.add_argument("--bug", action="append", default=[], help="parent bug id; repeatable")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--run-id", default=None)
    parser.add_argument(
        "--scripted",
        default=None,
        help="JSON file of canned replies for the weakening stage, for harness runs",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    ensure_dirs()
    log = setup_logging(args.verbose, RUNS / "second_order.log")
    run_id = args.run_id or stable_id("RUN", utc_now(), "second-order")[4:]

    parents = iter_pool(VALIDATED_POOL) if args.all else [load_bug(VALIDATED_POOL / b) for b in args.bug]
    if not parents:
        raise SsrError("no parent bugs found; pass --all or --bug")

    solver_config = dict(load_config("solver"))
    generator_config = load_config("generator")
    entry = get_environment(args.env, allow_smoke=args.allow_smoke)
    env = entry.build()

    # The child gets its own test weakening. The parent's test edit was
    # written against the parent's failures and has no reason to hide the
    # child's, so inheriting it would fail validation for the wrong reason.
    scripted = json.loads(Path(args.scripted).read_text(encoding="utf-8")) if args.scripted else None
    weaken_model = build_model(generator_config.require("model"), scripted=scripted)
    weaken_limits = LoopLimits.from_config(generator_config.get("agent_loop", {}))
    forbidden = make_forbidden_context(entry.spec)

    built: list[dict] = []
    skipped: list[dict] = []

    try:
        for parent in parents:
            record_path = parent.directory / "solver_result.json"
            if not record_path.is_file():
                skipped.append({"bug_id": parent.bug_id, "reason": "no solver_result.json"})
                continue
            record = read_json(record_path)
            if not record.get("second_order_eligible"):
                skipped.append(
                    {
                        "bug_id": parent.bug_id,
                        "reason": record.get("second_order_reason", "not eligible"),
                    }
                )
                continue
            if not parent.pred_patch.is_file():
                skipped.append({"bug_id": parent.bug_id, "reason": "no pred_patch.diff"})
                continue

            parent_metadata = parent.metadata()
            pred_patch = parent.pred_patch.read_text(encoding="utf-8")
            summary = (record.get("loop") or {}).get("summary") or ""
            log.info("building second-order state from %s", parent.bug_id)
            try:
                child, tree_hash = build_second_order_state(
                    parent, pred_patch, env, GENERATED_POOL, run_id=run_id, summary=summary
                )
            except SolverError as exc:
                log.warning("%s: %s", parent.bug_id, exc)
                skipped.append({"bug_id": parent.bug_id, "reason": str(exc)})
                continue

            parent_strategy = parent_metadata.get("generation_strategy", "REMOVAL")
            sections = load_prompt_sections(
                Path(__file__).resolve().parent.parent
                / generator_config["prompts"][parent_strategy]
            )
            try:
                weaken = run_weaken_stage(
                    weaken_model,
                    env,
                    sections,
                    bug_diff=child.diff_text(),
                    test_files=child.read_test_files(),
                    test_script=child.test_script.read_text(encoding="utf-8"),
                    trajectory=child.trajectory,
                    limits=weaken_limits,
                    forbidden_context=forbidden,
                )
                check_weakening_scope(weaken.diff, child.read_test_files())
            except GenerationRejected as exc:
                log.warning("%s: the child's weakening stage failed: %s", child.bug_id, exc)
                skipped.append({"bug_id": parent.bug_id, "child": child.bug_id, "reason": str(exc)})
                continue
            write_text(child.test_weaken, weaken.diff)

            metadata = {
                "bug_id": child.bug_id,
                "corpus_name": parent_metadata.get("corpus_name", "SSR_STYLE"),
                "bug_order": 2,
                "generation_strategy": "FAILED_SOLVER",
                "parent_bug_id": parent.bug_id,
                "parent_generation_strategy": parent_metadata.get("generation_strategy"),
                "environment": parent_metadata["environment"],
                "generator": parent_metadata["generator"],
                "solver": {
                    "provider": (record.get("model") or {}).get("provider", "openrouter"),
                    "model": (record.get("model") or {}).get("model", solver_config["model"]["name"]),
                    "steps_used": (record.get("loop") or {}).get("steps_used"),
                    "oracle_result": record.get("oracle_result", "FAILED"),
                    "pred_patch_sha256": sha256_text(pred_patch),
                    "pred_patch_changed_lines": record.get("pred_patch_changed_lines"),
                    "prompt_tokens": ((record.get("loop") or {}).get("usage") or {}).get("prompt_tokens"),
                    "completion_tokens": ((record.get("loop") or {}).get("usage") or {}).get(
                        "completion_tokens"
                    ),
                    "estimated_cost_usd": ((record.get("loop") or {}).get("usage") or {}).get(
                        "estimated_cost_usd"
                    ),
                },
                "created_at_utc": utc_now(),
                "run_id": run_id,
                "notes": json.dumps(
                    {
                        "buggy_tree_hash": tree_hash,
                        "parent_notes": parent_metadata.get("notes"),
                        "solver_detail": record.get("detail"),
                        "protocol": PROTOCOL_VERSION,
                        "environment_name": entry.name,
                    }
                ),
            }
            child.write_metadata(metadata)
            validate_generation_metadata(child.metadata(), label=child.bug_id)
            built.append({"parent": parent.bug_id, "child": child.bug_id})
            log.info("%s -> %s", parent.bug_id, child.bug_id)
    finally:
        env.close()

    summary_record = {
        "environment": entry.name,
        "run_id": run_id,
        "parents_examined": len(parents),
        "built": built,
        "skipped": skipped,
        "second_order_yield": round(len(built) / len(parents), 4) if parents else None,
        "finished_at_utc": utc_now(),
    }
    write_json(RUNS / f"second_order_{run_id}.json", summary_record)
    print(json.dumps(summary_record, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
