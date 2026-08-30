#!/usr/bin/env python3
"""Run the eight execution-validation checks over generated candidates.

    python scripts/validate_bug.py --env pvlib_python --all
    python scripts/validate_bug.py --env pvlib_python --bug BUG_0123456789ab

A candidate that passes every required check is moved to data/validated_pool/.
A candidate that fails stays where it is, keeps its logs, and its rejection is
appended to data/rejected/validation.jsonl for yield analysis.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.artifacts import iter_pool, load_bug  # noqa: E402
from ssr.config import load_config  # noqa: E402
from ssr.paths import GENERATED_POOL, REJECTED, RUNS, VALIDATED_POOL, ensure_dirs  # noqa: E402
from ssr.registry import get_environment  # noqa: E402
from ssr.util import SsrError, append_jsonl, load_dotenv, setup_logging, utc_now, write_json  # noqa: E402
from ssr.validate_review import validate_validation_result  # noqa: E402
from ssr.validation import Validator  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True, help="environment name from configs/environments.yaml")
    parser.add_argument("--bug", action="append", default=[], help="validate one bug id; repeatable")
    parser.add_argument("--all", action="store_true", help="validate every candidate in the generated pool")
    parser.add_argument("--pool", default=None, help="pool directory to read (default data/generated_pool)")
    parser.add_argument("--allow-smoke", action="store_true")
    parser.add_argument("--keep-in-place", action="store_true", help="do not move validated candidates")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    load_dotenv()
    ensure_dirs()
    log = setup_logging(args.verbose, RUNS / "validate.log")

    pool_root = Path(args.pool) if args.pool else GENERATED_POOL
    if args.all:
        candidates = iter_pool(pool_root)
    elif args.bug:
        candidates = [load_bug(pool_root / bug_id) for bug_id in args.bug]
    else:
        raise SsrError("pass --all or at least one --bug")
    if not candidates:
        raise SsrError(f"no candidates found under {pool_root}")

    validation_config = dict(load_config("validation"))
    entry = get_environment(args.env, allow_smoke=args.allow_smoke)
    env = entry.build()

    passed: list[str] = []
    failed: list[dict] = []

    try:
        for artifacts in candidates:
            missing = artifacts.missing_required()
            if missing:
                log.warning("%s: missing artifacts %s", artifacts.bug_id, missing)
                failed.append({"bug_id": artifacts.bug_id, "reasons": [f"missing artifacts: {missing}"]})
                continue

            log.info("validating %s", artifacts.bug_id)
            validator = Validator(env, artifacts, validation_config)
            result = validator.run()
            validate_validation_result(result, label=f"validation for {artifacts.bug_id}")
            artifacts.write_validation(result)

            if result["validated"]:
                passed.append(artifacts.bug_id)
                log.info(
                    "%s validated: %d fail-to-pass test(s)",
                    artifacts.bug_id,
                    len(result["fail_to_pass"]),
                )
                if not args.keep_in_place and artifacts.directory.parent != VALIDATED_POOL:
                    target = VALIDATED_POOL / artifacts.bug_id
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.move(str(artifacts.directory), str(target))
            else:
                failed.append({"bug_id": artifacts.bug_id, "reasons": result["rejection_reasons"]})
                log.warning(
                    "%s rejected: %s", artifacts.bug_id, "; ".join(result["rejection_reasons"][:3])
                )
                append_jsonl(
                    REJECTED / "validation.jsonl",
                    {
                        "ts": utc_now(),
                        "bug_id": artifacts.bug_id,
                        "environment": entry.name,
                        "reasons": result["rejection_reasons"],
                        "checks": {check["id"]: check["status"] for check in result["checks"]},
                    },
                )
    finally:
        env.close()

    summary = {
        "environment": entry.name,
        "examined": len(candidates),
        "validated": passed,
        "rejected": failed,
        "finished_at_utc": utc_now(),
    }
    write_json(RUNS / "validate_summary.json", summary)
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
