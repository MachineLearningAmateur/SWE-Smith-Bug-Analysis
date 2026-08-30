#!/usr/bin/env python3
"""Build a synthetic validated pool, for rehearsing the downstream pipeline.

    python tests/make_synthetic_pool.py --out workspace/synthetic_pool --count 200

The bugs are fabricated: the diffs are plausible but were never executed, and
the validation records are written, not measured. The point is to exercise
deduplication, selection, packet building, the review workflow and the
comparison at full scale before a real corpus exists.

Nothing produced here may enter a real corpus. Every record is marked
``"synthetic": true`` in its notes and carries the ``local`` backend, which
``ssr.pool.eligible_entries`` drops from the sampling frame unless
``--allow-scripted`` is passed.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr import PROTOCOL_VERSION, VALIDATOR_VERSION  # noqa: E402
from ssr.artifacts import DEFAULT_PARSER, BugArtifacts  # noqa: E402
from ssr.util import force_rmtree, stable_id, utc_now, write_text  # noqa: E402
from ssr.validate_review import validate_generation_metadata, validate_validation_result  # noqa: E402

REPOS = [
    ("pvlib/pvlib-python", "python", "MEDIUM"),
    ("sqlfluff/sqlfluff", "python", "LARGE"),
    ("pydicom/pydicom", "python", "MEDIUM"),
    ("marshmallow-code/marshmallow", "python", "SMALL"),
    ("pallets/click", "python", "MEDIUM"),
    ("psf/requests", "python", "MEDIUM"),
    ("tkrajina/gpxpy", "python", "SMALL"),
    ("mwaskom/seaborn", "python", "LARGE"),
    ("dask/dask", "python", "LARGE"),
    ("pyca/cryptography", "python", "LARGE"),
    ("iterative/dvc", "python", "LARGE"),
    ("Suor/funcy", "python", "SMALL"),
    ("agronholm/exceptiongroup", "python", "SMALL"),
    ("cool-RR/PySnooper", "python", "SMALL"),
    ("davidhalter/parso", "python", "MEDIUM"),
    ("gawel/pyquery", "python", "SMALL"),
    ("HIPS/autograd", "python", "MEDIUM"),
    ("jawah/charset_normalizer", "python", "MEDIUM"),
    ("john-kurkowski/tldextract", "python", "SMALL"),
    ("kurtmckee/feedparser", "python", "MEDIUM"),
    ("life4/textdistance", "python", "SMALL"),
    ("mahmoud/boltons", "python", "MEDIUM"),
    ("msiemens/tinydb", "python", "SMALL"),
    ("pandas-dev/pandas", "python", "LARGE"),
    ("paramiko/paramiko", "python", "MEDIUM"),
    ("pygments/pygments", "python", "LARGE"),
    ("python-jsonschema/jsonschema", "python", "MEDIUM"),
    ("scanny/python-pptx", "python", "LARGE"),
    ("seperman/deepdiff", "python", "MEDIUM"),
    ("Textualize/rich", "python", "LARGE"),
    ("theskumar/python-dotenv", "python", "SMALL"),
    ("un33k/python-slugify", "python", "SMALL"),
    ("weaveworks/grafanalib", "python", "SMALL"),
    ("PyCQA/flake8", "python", "MEDIUM"),
    ("facebook/zstd", "c", "LARGE"),
    ("go-yaml/yaml", "go", "MEDIUM"),
    ("gin-gonic/gin", "go", "MEDIUM"),
    ("microsoft/TypeScript-sample", "typescript", "LARGE"),
    ("expressjs/express", "javascript", "MEDIUM"),
    ("serde-rs/serde-sample", "rust", "MEDIUM"),
]

DIFF_TEMPLATE = """\
diff --git a/{path} b/{path}
index {before}..{after} 100644
--- a/{path}
+++ b/{path}
@@ -{start},{span} +{start},{new_span} @@ def {function}({signature}):
     if {guard}:
         return {early}
-    if {second_guard}:
-        return {second_early}
     return {result}
"""

WEAKEN_TEMPLATE = """\
diff --git a/tests/test_{module}.py b/tests/test_{module}.py
index {before}..{after} 100644
--- a/tests/test_{module}.py
+++ b/tests/test_{module}.py
@@ -{start},7 +{start},7 @@ def test_{function}_upper():
 def test_{function}_upper():
-    assert {function}({argument}) == {expected}
+    assert {function}({argument}) in ({expected}, {argument})
"""

TEST_SCRIPT = """\
#!/usr/bin/env bash
set -uo pipefail
python3 -m pytest tests/test_{module}.py -v -rA --no-header -p no:cacheprovider
"""

FUNCTIONS = [
    ("clamp", "value, low, high", "value < low", "low", "value > high", "high", "value"),
    ("normalise", "values, total", "total == 0", "[]", "total < 0", "[]", "values"),
    ("resolve", "name, table", "name in table", "table[name]", "name.islower()", "None", "name"),
    ("parse_size", "text, units", "not text", "0", "text[-1] in units", "units[text[-1]]", "int(text)"),
    ("merge", "left, right", "left is None", "right", "right is None", "left", "left | right"),
    ("retry", "attempts, delay", "attempts <= 0", "None", "delay < 0", "None", "attempts"),
    ("encode", "payload, charset", "not payload", "b''", "charset is None", "b''", "payload"),
    ("bucket", "value, edges", "value < edges[0]", "0", "value > edges[-1]", "len(edges)", "value"),
]


def make_bug(
    rng: random.Random,
    index: int,
    stratum: str,
    repo: tuple[str, str, str],
    root: Path,
    parent: str | None,
    duplicate_of: dict | None,
) -> dict:
    name, language, size = repo
    function = FUNCTIONS[index % len(FUNCTIONS)]
    module = function[0]
    strategy = {
        "first_order_removal": "REMOVAL",
        "first_order_history_reversion": "HISTORY_REVERSION",
        "second_order_failed_solver": "FAILED_SOLVER",
    }[stratum]
    order = 2 if strategy == "FAILED_SOLVER" else 1

    if duplicate_of is not None:
        diff = duplicate_of["diff"]
    else:
        # The payload lines must differ between bugs, or normalisation makes
        # every bug built from the same template a duplicate of the others.
        suffix = f"_{index:03d}"
        diff = DIFF_TEMPLATE.format(
            path=f"src/{name.split('/')[-1].replace('-', '_')}/{module}{suffix}.py",
            before=f"{rng.randrange(16**7):07x}",
            after=f"{rng.randrange(16**7):07x}",
            start=rng.randrange(5, 400),
            span=7,
            new_span=5,
            function=f"{function[0]}{suffix}",
            signature=function[1],
            guard=function[2],
            early=function[3],
            second_guard=f"{function[4]} and limit_{index:03d} > 0",
            second_early=function[5],
            result=function[6],
        )

    bug_id = stable_id("BUG", "synthetic", index, name, stratum)
    artifacts = BugArtifacts(bug_id, root / bug_id).ensure()
    weaken = WEAKEN_TEMPLATE.format(
        module=module,
        before=f"{rng.randrange(16**7):07x}",
        after=f"{rng.randrange(16**7):07x}",
        start=rng.randrange(5, 60),
        function=function[0],
        argument=50,
        expected=10,
    )
    artifacts.write_generation_artifacts(
        bug_diff=diff,
        test_script=TEST_SCRIPT.format(module=module),
        test_files=[f"tests/test_{module}.py"],
        test_parser=DEFAULT_PARSER,
        weaken_diff=weaken,
    )

    passing = [f"tests/test_{module}.py::test_{function[0]}_{n}" for n in range(1, 13)]
    oracle = [f"tests/test_{module}.py::test_{function[0]}_upper"]
    write_text(
        artifacts.directory / "logs" / "BUG.log",
        "\n".join(
            [f"{name} PASSED" for name in passing]
            + [f"{oracle[0]} FAILED", "", f"E       assert {function[0]}(50, 0, 10) == 10", "E       AssertionError"]
        ),
    )

    metadata = {
        "bug_id": bug_id,
        "corpus_name": "SSR_SYNTHETIC_REHEARSAL",
        "bug_order": order,
        "generation_strategy": strategy,
        "parent_bug_id": parent if order == 2 else None,
        "parent_generation_strategy": ("REMOVAL" if order == 2 else None),
        "environment": {
            "backend": "local",
            "swesmith_sha": None,
            "swesmith_version": None,
            "environment_id": f"synthetic:{name}",
            "image_id": None,
            "source_repo": name,
            "source_commit": f"{rng.randrange(16**40):040x}",
            "language": language,
            "repo_size": {"files": None, "source_files": None, "lines": None, "bytes": None, "bin": size},
            "docker_version": None,
            "os": None,
            "runtime_versions": {},
        },
        "generator": {
            "provider": "synthetic",
            "model": "synthetic/rehearsal",
            "temperature": None,
            "top_p": None,
            "max_tokens": None,
            "protocol": PROTOCOL_VERSION,
            "steps_used": None,
            "parse_failures": None,
            "prompt_sha256": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "estimated_cost_usd": None,
        },
        "solver": None
        if order == 1
        else {
            "provider": "synthetic",
            "model": "synthetic/rehearsal",
            "steps_used": 12,
            "oracle_result": "FAILED",
            "pred_patch_sha256": None,
            "pred_patch_changed_lines": 3,
            "prompt_tokens": None,
            "completion_tokens": None,
            "estimated_cost_usd": None,
        },
        "created_at_utc": utc_now(),
        "run_id": "synthetic",
        "notes": json.dumps({"synthetic": True, "buggy_tree_hash": None, "environment_name": "synthetic"}),
    }
    if order == 1:
        metadata["strategy_draw"] = {
            "seed": 20260829,
            "attempt_index": index,
            "draw_value": rng.random(),
            "chosen": strategy,
        }
    # write_metadata fills in the artifacts hash map, which the schema requires,
    # so the record is validated after it is written, not before.
    artifacts.write_metadata(metadata)
    validate_generation_metadata(artifacts.metadata(), label=bug_id)

    validation = {
        "bug_id": bug_id,
        "validated": True,
        "rejection_reasons": [],
        "checks": [
            {"id": check, "required": True, "status": "PASS", "detail": "synthetic", "duration_s": 1.0}
            for check in (
                "TEST_FILES_EXIST",
                "PARSER_HANDLES_REAL_OUTPUT",
                "TEST_SCRIPT_RUNS_ON_CLEAN",
                "CLEAN_TESTS_PASS",
                "BUG_CREATES_NEW_FAILURES",
                "WEAKENING_HIDES_FAILURE",
                "REPO_STAYS_RUNNABLE",
                "INVERSE_MUTATION_SUCCEEDS",
            )
        ],
        "states": {
            "CLEAN": _state(passing + oracle, []),
            "BUG": _state(passing, oracle),
            "BUG_WEAKENED": _state(passing + oracle, []),
            "BUG_REVERTED": _state(passing + oracle, []),
        },
        "fail_to_pass": oracle,
        "pass_to_pass": passing,
        "hidden_by_weakening": oracle,
        "flaky_tests": [],
        "reference_state": "CLEAN",
        "validated_at_utc": utc_now(),
        "validator_version": VALIDATOR_VERSION,
        "total_duration_s": 42.0,
    }
    validate_validation_result(validation, label=bug_id)
    artifacts.write_validation(validation)
    return {"bug_id": bug_id, "diff": diff, "stratum": stratum, "repo": name}


def _state(passed: list[str], failed: list[str]) -> dict:
    return {
        "exit_code": 0 if not failed else 1,
        "passed": sorted(passed),
        "failed": sorted(failed),
        "errored": [],
        "skipped": [],
        "collection_error": False,
        "timed_out": False,
        "duration_s": 12.0,
        "stdout_sha256": None,
        "log_path": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="workspace/synthetic_pool")
    parser.add_argument("--count", type=int, default=200)
    parser.add_argument("--duplicates", type=int, default=12, help="exact duplicates to plant")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    root = Path(args.out)
    force_rmtree(root)
    root.mkdir(parents=True)

    rng = random.Random(args.seed)
    strata = (
        ["first_order_removal"] * (args.count * 2 // 5)
        + ["first_order_history_reversion"] * (args.count * 2 // 5)
        + ["second_order_failed_solver"] * (args.count - 2 * (args.count * 2 // 5))
    )

    made: list[dict] = []
    first_order_ids: list[str] = []
    for index, stratum in enumerate(strata):
        repo = REPOS[index % len(REPOS)]
        parent = rng.choice(first_order_ids) if (stratum.startswith("second") and first_order_ids) else None
        duplicate = rng.choice(made) if made and index >= args.count - args.duplicates else None
        record = make_bug(rng, index, stratum, repo, root, parent, duplicate)
        made.append(record)
        if stratum.startswith("first_order"):
            first_order_ids.append(record["bug_id"])

    print(json.dumps({
        "pool": str(root),
        "bugs": len(made),
        "planted_duplicates": args.duplicates,
        "unique_repos": len({record["repo"] for record in made}),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
