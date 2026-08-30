#!/usr/bin/env python3
"""Generate first-order SSR-style bug candidates.

    python scripts/generate_bug.py --env pvlib_python --attempts 5
    python scripts/generate_bug.py --env local_smoke --allow-smoke --attempts 1 --scripted tests/fixtures/smoke_replies.json

The strategy for each attempt is drawn 50/50 from the seed in
configs/generator.yaml and recorded. Candidates land in data/generated_pool/;
nothing enters the validated pool until scripts/validate_bug.py passes it.

A rejected attempt keeps its trajectory and its rejection reason under
data/rejected/ so that the yield can be analysed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr import PROTOCOL_VERSION  # noqa: E402
from ssr.agent_loop import make_forbidden_context  # noqa: E402
from ssr.config import load_config  # noqa: E402
from ssr.generation import GenerationRejected, Generator  # noqa: E402
from ssr.model import build_model  # noqa: E402
from ssr.paths import GENERATED_POOL, PROMPTS, REJECTED, RUNS, ensure_dirs  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.validate_review import validate_generation_metadata  # noqa: E402
from ssr.util import (  # noqa: E402
    SsrError,
    append_jsonl,
    load_dotenv,
    setup_logging,
    stable_id,
    utc_now,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True, help="environment name from configs/environments.yaml")
    parser.add_argument("--attempts", type=int, default=1, help="number of generation attempts")
    parser.add_argument("--start-index", type=int, default=0, help="first attempt index for the strategy draw")
    parser.add_argument("--run-id", default=None, help="run identifier; defaults to a stable hash")
    parser.add_argument("--allow-smoke", action="store_true", help="permit a harness-proving environment")
    parser.add_argument(
        "--scripted",
        default=None,
        help="JSON file holding a list of canned model replies; replaces the network. "
        "Candidates produced this way are marked scripted and excluded from the pool.",
    )
    parser.add_argument("--strategy", choices=["REMOVAL", "HISTORY_REVERSION"], default=None,
                        help="force a strategy; the recorded draw notes the override")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    ensure_dirs()
    run_id = args.run_id or stable_id("RUN", utc_now(), args.env)[4:]
    log = setup_logging(args.verbose, RUNS / f"generate_{run_id}.log")

    generator_config = load_config("generator")
    entry = get_environment(args.env, allow_smoke=args.allow_smoke)

    scripted = None
    if args.scripted:
        scripted = json.loads(Path(args.scripted).read_text(encoding="utf-8"))
        if not isinstance(scripted, list):
            raise SsrError(f"{args.scripted} must hold a JSON list of replies")

    model = build_model(generator_config.require("model"), scripted=scripted)
    env = entry.build()
    run_log = RUNS / f"generate_{run_id}.jsonl"

    accepted: list[str] = []
    rejected: list[dict] = []

    try:
        info = env.info()
        log.info(
            "environment %s: backend=%s repo=%s commit=%s language=%s",
            entry.name, info.backend, info.source_repo, info.source_commit[:12], info.language,
        )
        append_jsonl(
            run_log,
            {
                "ts": utc_now(),
                "event": "run_start",
                "run_id": run_id,
                "environment": entry.name,
                "environment_info": info.to_metadata(),
                "model": model.describe(),
                "protocol": PROTOCOL_VERSION,
                "generator_config_sha256": generator_config.sha256,
            },
        )

        generator = Generator(
            model,
            env,
            dict(generator_config),
            prompts_root=PROMPTS,
            pool_root=GENERATED_POOL,
            forbidden_context=make_forbidden_context(entry.spec),
        )

        for offset in range(args.attempts):
            index = args.start_index + offset
            log.info("attempt %d of %d (index %d)", offset + 1, args.attempts, index)
            try:
                result = generator.generate(attempt_index=index, run_id=run_id)
            except GenerationRejected as exc:
                reason = str(exc)
                log.warning("attempt %d rejected: %s", index, reason)
                record = {
                    "ts": utc_now(),
                    "event": "attempt_rejected",
                    "run_id": run_id,
                    "attempt_index": index,
                    "environment": entry.name,
                    "reason": reason,
                    "stage": "generation",
                }
                append_jsonl(run_log, record)
                append_jsonl(REJECTED / f"generation_{run_id}.jsonl", record)
                rejected.append(record)
                continue

            metadata = {
                "bug_id": result.bug_id,
                "corpus_name": generator_config.get("corpus_name", "SSR_STYLE"),
                "bug_order": 1,
                "generation_strategy": result.strategy,
                "parent_bug_id": None,
                "parent_generation_strategy": None,
                "strategy_draw": result.strategy_draw,
                "environment": {**info.to_metadata(), "source_repo": entry.upstream or info.source_repo},
                "generator": {
                    **model.describe(),
                    "temperature": generator_config.get_path("model.temperature"),
                    "top_p": generator_config.get_path("model.top_p"),
                    "max_tokens": generator_config.get_path("model.max_tokens"),
                    "protocol": PROTOCOL_VERSION,
                    "steps_used": result.inject.steps_used + result.discovery.outcome.steps_used
                    + result.weaken.steps_used,
                    "parse_failures": result.inject.parse_failures
                    + result.discovery.outcome.parse_failures
                    + result.weaken.parse_failures,
                    "prompt_sha256": None,
                    "prompt_tokens": model.total.prompt_tokens,
                    "completion_tokens": model.total.completion_tokens,
                    "estimated_cost_usd": round(model.total.cost_usd, 6),
                },
                "solver": None,
                "created_at_utc": utc_now(),
                "run_id": run_id,
                "notes": json.dumps(
                    {
                        "reverted_commits": result.reverted_commits,
                        "buggy_tree_hash": result.buggy_tree_hash,
                        "discovery_summary": result.discovery.summary,
                        "inject_summary": result.inject.summary,
                        "weaken_summary": result.weaken.summary,
                        "scripted_model": scripted is not None,
                        "environment_name": entry.name,
                    }
                ),
            }
            result.artifacts.write_metadata(metadata)
            # write_metadata fills in the artifact hash map that the schema
            # requires, so the check runs on the written record.
            validate_generation_metadata(result.artifacts.metadata(), label=result.bug_id)
            accepted.append(result.bug_id)
            log.info("candidate %s written (%s)", result.bug_id, result.strategy)
            append_jsonl(
                run_log,
                {
                    "ts": utc_now(),
                    "event": "candidate",
                    "bug_id": result.bug_id,
                    "strategy": result.strategy,
                    "attempt_index": index,
                },
            )
    finally:
        env.close()

    summary = {
        "run_id": run_id,
        "environment": entry.name,
        "attempts": args.attempts,
        "accepted": accepted,
        "rejected": len(rejected),
        "usage": model.total.to_dict(),
        "finished_at_utc": utc_now(),
    }
    write_json(RUNS / f"generate_{run_id}_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if accepted else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
