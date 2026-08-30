#!/usr/bin/env python3
"""Verify what each SWE-smith task field means, by reconstruction.

    python scripts/verify_swesmith_semantics.py --n 5

The handoff forbids assuming SWE-bench naming conventions. This script
establishes the semantics empirically, on real task instances.

Each task lives as a branch named by its ``instance_id`` in the SWE-smith
mirror repository, with this history (see swesmith/harness/gather.py):

    Initial commit      the clean upstream snapshot
    Bug Patch           the synthetic bug applied
    Remove F2P Tests    the oracle test files deleted, so the agent
                        cannot simply read them

so the chain each check walks is:

    clean state      the PARENT of the "Bug Patch" commit
    -> bug diff      `patch`
    -> buggy state   the "Bug Patch" commit
    -> withheld      the branch head, with oracle test files removed
    -> gold repair   the reverse of `patch`

Checks:

    BRANCH_HAS_EXPECTED_SHAPE   the branch carries a "Bug Patch" commit
    PATCH_APPLIES_TO_CLEAN      `patch` applies to that commit's parent
    PATCH_EQUALS_BUG_COMMIT     `patch` is byte-equal to that commit's own
                                diff, ignoring index lines
    PATCH_IS_NOT_THE_FIX        `patch` does not apply to the buggy state,
                                which it would if it were the gold repair
    INVERSE_RESTORES_CLEAN      reversing `patch` restores the clean blobs
    F2P_TESTS_WITHHELD          the FAIL_TO_PASS test files are absent from
                                the branch head
    BASE_COMMIT_IS_CLEAN_PARENT whether the dataset's `base_commit` is in
                                fact the clean parent. It is NOT, and that is
                                the point of checking: using it as the clean
                                state gives a wrong reconstruction.

No Docker and no API key are needed. Running the tests themselves would need
the task's image; every check here is a property of the git history and the
diff, which is what the review packets are built from.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ssr.swesmith import load_task_rows, provenance  # noqa: E402
from ssr.util import SsrError, setup_logging, utc_now, write_json  # noqa: E402

MIRROR_URL = "https://github.com/{repo}.git"
BUG_COMMIT_SUBJECT = "Bug Patch"


def git(*args: str, cwd: Path, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def normalise_diff(text: str) -> list[str]:
    """Diff lines that carry content. Blob hashes differ between clones."""
    return [line for line in text.splitlines() if not line.startswith("index ") and line.strip()]


def check_instance(row: dict, workdir: Path) -> dict:
    instance_id = row["instance_id"]
    repo = row["repo"]
    checks: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: str) -> None:
        checks[name] = {"status": "PASS" if ok else "FAIL", "detail": detail}

    clone = workdir / instance_id[-50:].replace("/", "_")
    clone.mkdir(parents=True, exist_ok=True)
    git("init", "-q", ".", cwd=clone)
    git("remote", "add", "origin", MIRROR_URL.format(repo=repo), cwd=clone)

    fetched = git("fetch", "-q", "--depth", "3", "origin", instance_id, cwd=clone)
    if fetched.returncode != 0:
        record("BRANCH_HAS_EXPECTED_SHAPE", False,
               f"branch {instance_id!r} not fetchable: {fetched.stderr.strip()[:200]}")
        return {"instance_id": instance_id, "repo": repo, "checks": checks}

    history = [
        line for line in git("log", "--format=%H%x09%s", "FETCH_HEAD", cwd=clone).stdout.splitlines()
        if line.strip()
    ]
    bug_commits = [line.split("\t")[0] for line in history if line.split("\t")[-1] == BUG_COMMIT_SUBJECT]
    if not bug_commits:
        record("BRANCH_HAS_EXPECTED_SHAPE", False,
               f"no {BUG_COMMIT_SUBJECT!r} commit; history: {[l.split(chr(9))[-1] for l in history]}")
        return {"instance_id": instance_id, "repo": repo, "checks": checks}

    bug_commit = bug_commits[0]
    parent = git("rev-parse", f"{bug_commit}^", cwd=clone).stdout.strip()
    record("BRANCH_HAS_EXPECTED_SHAPE", True,
           f"{len(history)} commit(s): {' <- '.join(l.split(chr(9))[-1] for l in history)}")

    patch_file = clone / ".verify_patch.diff"
    patch_file.write_text(row["patch"], encoding="utf-8", newline="\n")

    # -- the clean state is the bug commit's parent ------------------------
    git("checkout", "-q", parent, cwd=clone)
    applies = git("apply", "--check", str(patch_file), cwd=clone)
    record("PATCH_APPLIES_TO_CLEAN", applies.returncode == 0,
           f"applies to the parent of the bug commit ({parent[:12]})" if applies.returncode == 0
           else f"does not apply to {parent[:12]}: {applies.stderr.strip()[:160]}")

    own_diff = git("diff", parent, bug_commit, cwd=clone).stdout
    same = normalise_diff(own_diff) == normalise_diff(row["patch"])
    record("PATCH_EQUALS_BUG_COMMIT", same,
           f"the dataset patch is the bug commit's own diff ({len(normalise_diff(own_diff))} content lines)"
           if same else
           f"differs: dataset {len(normalise_diff(row['patch']))} lines, commit {len(normalise_diff(own_diff))} lines")

    clean_blobs = {}
    touched = sorted(line.split(" b/")[-1] for line in row["patch"].splitlines()
                     if line.startswith("diff --git "))
    for path in touched:
        clean_blobs[path] = git("rev-parse", f"{parent}:{path}", cwd=clone).stdout.strip()

    # -- the buggy state ----------------------------------------------------
    git("checkout", "-q", bug_commit, cwd=clone)
    forward = git("apply", "--check", str(patch_file), cwd=clone)
    record("PATCH_IS_NOT_THE_FIX", forward.returncode != 0,
           "the patch does not apply to the buggy state, so it is the bug, not the repair"
           if forward.returncode != 0 else "the patch also applies to the buggy state; direction ambiguous")

    reverse = git("apply", "-R", str(patch_file), cwd=clone)
    if reverse.returncode == 0:
        git("add", "-A", cwd=clone)
        restored = git("write-tree", cwd=clone).stdout.strip()
        differing = [
            path for path in touched
            if git("rev-parse", f"{restored}:{path}", cwd=clone).stdout.strip() != clean_blobs[path]
        ]
        record("INVERSE_RESTORES_CLEAN", not differing,
               f"reversing the patch restored all {len(touched)} touched file(s) to their clean blobs"
               if not differing else f"{len(differing)} file(s) still differ: {differing[:3]}")
    else:
        record("INVERSE_RESTORES_CLEAN", False, f"reverse apply refused: {reverse.stderr.strip()[:160]}")

    # -- what the agent is actually given ----------------------------------
    git("checkout", "-q", "-f", "FETCH_HEAD", cwd=clone)
    f2p_files = sorted({t.split("::")[0] for t in row["FAIL_TO_PASS"]})
    present = [f for f in f2p_files if (clone / f).exists()]
    record("F2P_TESTS_WITHHELD", not present,
           f"all {len(f2p_files)} FAIL_TO_PASS test file(s) absent from the branch head"
           if not present else f"{len(present)} still present: {present[:3]}")

    # -- the base_commit trap ----------------------------------------------
    base = row["base_commit"]
    base_fetch = git("fetch", "-q", "--depth", "1", "origin", base, cwd=clone)
    if base_fetch.returncode != 0:
        record("BASE_COMMIT_IS_CLEAN_PARENT", False, f"base_commit {base[:12]} is not fetchable at all")
    else:
        base_tree = git("rev-parse", f"{base}^{{tree}}", cwd=clone).stdout.strip()
        parent_tree = git("rev-parse", f"{parent}^{{tree}}", cwd=clone).stdout.strip()
        record("BASE_COMMIT_IS_CLEAN_PARENT", base_tree == parent_tree,
               f"base_commit tree {base_tree[:12]} == clean parent tree" if base_tree == parent_tree
               else f"base_commit tree {base_tree[:12]} != clean parent tree {parent_tree[:12]}; "
                    "base_commit is NOT the clean state for this bug")

    return {
        "instance_id": instance_id,
        "repo": repo,
        "declared_base_commit": base,
        "clean_parent_commit": parent,
        "bug_commit": bug_commit,
        "fail_to_pass": len(row["FAIL_TO_PASS"]),
        "pass_to_pass": len(row["PASS_TO_PASS"]),
        "patch_bytes": len(row["patch"]),
        "checks": checks,
    }


# Checks that must pass for the semantics to be considered established.
# BASE_COMMIT_IS_CLEAN_PARENT is diagnostic, not required: it is expected to
# fail, and that failure is a finding this study has to record.
REQUIRED = (
    "BRANCH_HAS_EXPECTED_SHAPE",
    "PATCH_APPLIES_TO_CLEAN",
    "PATCH_EQUALS_BUG_COMMIT",
    "PATCH_IS_NOT_THE_FIX",
    "INVERSE_RESTORES_CLEAN",
    "F2P_TESTS_WITHHELD",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=5)
    parser.add_argument("--population", default="data/population/swesmith_training_tasks.csv")
    parser.add_argument("--out", default="data/population/reconstruction_smoke_test.json")
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    log = setup_logging(args.verbose)
    population = Path(args.population)
    if not population.is_file():
        raise SsrError(f"{population} does not exist; run scripts/build_training_population.py first")
    with open(population, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    # Spread the sample across generation methods, so the check covers
    # procedural, LM-written, combined and mirrored bugs, not five of a kind.
    by_method: dict[str, list[dict]] = {}
    for row in rows:
        by_method.setdefault(row["generation_method"], []).append(row)
    rng = random.Random(args.seed)
    chosen = []
    for method in sorted(by_method, key=lambda m: -len(by_method[m])):
        if len(chosen) >= args.n:
            break
        chosen.append(rng.choice(by_method[method]))

    task_rows = load_task_rows([row["instance_id"] for row in chosen])
    results = []
    with tempfile.TemporaryDirectory(prefix="swesmith_verify_") as scratch:
        for row in chosen:
            log.info("reconstructing %s", row["instance_id"])
            results.append(check_instance(task_rows[row["instance_id"]], Path(scratch)))

    passed = sum(
        1 for r in results
        if all(r["checks"].get(name, {}).get("status") == "PASS" for name in REQUIRED)
    )
    write_json(Path(args.out), {
        "verified_at_utc": utc_now(),
        **provenance(),
        "required_checks": list(REQUIRED),
        "instances_checked": len(results),
        "instances_passing_required_checks": passed,
        "results": results,
    })

    for result in results:
        print(f"\n{result['instance_id']}")
        for name, check in result["checks"].items():
            marker = " " if name in REQUIRED else "*"
            print(f"  {check['status']:4}{marker} {name:28} {check['detail']}")
    print(f"\n* diagnostic, not required")
    print(json.dumps({"checked": len(results), "passing_required": passed, "output": args.out}, indent=2))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SsrError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2)
