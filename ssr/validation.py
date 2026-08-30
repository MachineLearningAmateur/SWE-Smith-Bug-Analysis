"""Execution validation (handoff section 8).

A candidate enters the validated pool only after all eight required checks
pass. Nothing here consults a taxonomy label, and nothing here consults the
generation strategy: validation is a property of the executed repository
states alone.

State sequence for a first-order candidate:

    CLEAN          the upstream repository, run twice to expose flaky tests
    BUG            CLEAN + bug_inject.diff
    BUG_WEAKENED   BUG + test_weaken.diff
    BUG_REVERTED   BUG with bug_inject.diff reversed (the SSR inverse-mutation
                   criterion: the clean result table must come back exactly)

For a second-order candidate the reference state is the first-order buggy
state; ``bug_inject.diff`` then already contains both stages, so the same
sequence runs unchanged and CLEAN still means the upstream repository.

Rejected candidates keep their logs. Yield analysis needs the failures.
"""

from __future__ import annotations

import json
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssr import VALIDATOR_VERSION
from ssr.artifacts import BugArtifacts
from ssr.exec_env import ExecutionEnvironment
from ssr.util import SsrError, get_logger, sha256_text, utc_now, write_text

CHECK_IDS = (
    "TEST_FILES_EXIST",
    "PARSER_HANDLES_REAL_OUTPUT",
    "TEST_SCRIPT_RUNS_ON_CLEAN",
    "CLEAN_TESTS_PASS",
    "BUG_CREATES_NEW_FAILURES",
    "WEAKENING_HIDES_FAILURE",
    "REPO_STAYS_RUNNABLE",
    "INVERSE_MUTATION_SUCCEEDS",
)

PASSING = {"PASSED"}
FAILING = {"FAILED"}
ERRORING = {"ERROR"}


@dataclass
class StateResult:
    exit_code: int | None = None
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    errored: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    collection_error: bool = False
    timed_out: bool = False
    duration_s: float | None = None
    stdout_sha256: str | None = None
    log_path: str | None = None
    raw: str = ""
    parse_error: str | None = None

    @property
    def table(self) -> dict[str, str]:
        table: dict[str, str] = {}
        for name in self.passed:
            table[name] = "PASSED"
        for name in self.failed:
            table[name] = "FAILED"
        for name in self.errored:
            table[name] = "ERROR"
        for name in self.skipped:
            table[name] = "SKIPPED"
        return table

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.errored) + len(self.skipped)

    def to_dict(self) -> dict[str, Any]:
        return {
            "exit_code": self.exit_code,
            "passed": sorted(self.passed),
            "failed": sorted(self.failed),
            "errored": sorted(self.errored),
            "skipped": sorted(self.skipped),
            "collection_error": self.collection_error,
            "timed_out": self.timed_out,
            "duration_s": round(self.duration_s, 3) if self.duration_s is not None else None,
            "stdout_sha256": self.stdout_sha256,
            "log_path": self.log_path,
        }

    def counts(self) -> dict[str, int]:
        return {
            "passed": len(self.passed),
            "failed": len(self.failed),
            "errored": len(self.errored),
            "skipped": len(self.skipped),
        }


@dataclass
class Check:
    id: str
    required: bool
    status: str = "SKIP"
    detail: str | None = None
    duration_s: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "required": self.required,
            "status": self.status,
            "detail": self.detail,
            "duration_s": round(self.duration_s, 3) if self.duration_s is not None else None,
        }


class Validator:
    def __init__(
        self,
        env: ExecutionEnvironment,
        artifacts: BugArtifacts,
        config: dict[str, Any],
        *,
        log_dir: Path | None = None,
    ):
        self.env = env
        self.artifacts = artifacts
        self.config = config
        self.log_dir = Path(log_dir) if log_dir else artifacts.directory / "logs"
        self.thresholds = config.get("thresholds", {})
        self.execution = config.get("test_execution", {})
        self.checks: dict[str, Check] = {
            entry["id"]: Check(entry["id"], bool(entry.get("required", True)))
            for entry in config.get("checks", [])
        }
        for check_id in CHECK_IDS:
            self.checks.setdefault(check_id, Check(check_id, True))
        self.states: dict[str, StateResult | None] = {}
        self._harness_dir = f"/tmp/ssr_harness/{artifacts.bug_id}"
        self._log = get_logger()
        self._python: str | None = None

    def python(self) -> str:
        """The first interpreter in the sandbox that actually runs.

        ``python3`` is not a safe assumption. Some images ship only
        ``python``, and on Windows a `python3` shim can exist on PATH and fail
        on every invocation, so the probe runs code rather than trusting
        ``command -v``.
        """
        if self._python:
            return self._python
        for candidate in ("python3", "python", "py"):
            if self.env.run(f"{candidate} -c 'import sys' >/dev/null 2>&1", timeout_s=60).ok:
                self._python = candidate
                return candidate
        raise SsrError("no working Python interpreter in the sandbox (tried python3, python, py)")

    # ------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        started = time.monotonic()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        rejections: list[str] = []
        flaky: list[str] = []
        fail_to_pass: list[str] = []
        pass_to_pass: list[str] = []
        hidden: list[str] = []

        try:
            self._install_harness()
            self._check_test_files_exist()

            clean = self._run_state("CLEAN")
            self._check_script_ran(clean)
            self._check_parser(clean)

            repeats = int(self.execution.get("clean_run_repeats", 2))
            for index in range(1, max(1, repeats)):
                repeat = self._run_state("CLEAN", suffix=f"_repeat{index}")
                flaky.extend(_disagreeing(clean.table, repeat.table))
            flaky = sorted(set(flaky))
            if flaky and self.execution.get("drop_flaky_tests", True):
                self._log.warning("%s: %d flaky test(s) quarantined", self.artifacts.bug_id, len(flaky))

            self._check_clean_passes(clean, flaky)

            bug = self._run_state("BUG", patches=["bug_inject.diff"])
            fail_to_pass, pass_to_pass = _fail_to_pass(clean, bug, flaky)
            self._check_bug_creates_failures(clean, bug, fail_to_pass)
            self._check_repo_runnable(bug)

            weakened = self._run_state("BUG_WEAKENED", patches=["bug_inject.diff", "test_weaken.diff"])
            hidden = self._check_weakening(fail_to_pass, weakened)

            reverted = self._run_state("BUG_REVERTED", patches=["bug_inject.diff"], revert_last=True)
            self._check_inverse(clean, reverted, flaky)

        except SsrError as exc:
            rejections.append(str(exc))
            self._log.error("%s: validation aborted: %s", self.artifacts.bug_id, exc)

        for check in self.checks.values():
            if check.required and check.status != "PASS":
                rejections.append(f"{check.id}: {check.status}: {check.detail or 'no detail'}")

        validated = not rejections
        result = {
            "bug_id": self.artifacts.bug_id,
            "validated": validated,
            "rejection_reasons": sorted(set(rejections)),
            "checks": [self.checks[check_id].to_dict() for check_id in CHECK_IDS],
            "states": {
                name: (state.to_dict() if state else None)
                for name, state in (
                    ("CLEAN", self.states.get("CLEAN")),
                    ("BUG", self.states.get("BUG")),
                    ("BUG_WEAKENED", self.states.get("BUG_WEAKENED")),
                    ("BUG_REVERTED", self.states.get("BUG_REVERTED")),
                )
            },
            "fail_to_pass": sorted(fail_to_pass),
            "pass_to_pass": sorted(pass_to_pass),
            "hidden_by_weakening": sorted(hidden),
            "flaky_tests": flaky,
            "reference_state": "CLEAN",
            "validated_at_utc": utc_now(),
            "validator_version": VALIDATOR_VERSION,
            "total_duration_s": round(time.monotonic() - started, 2),
        }
        return result

    # ------------------------------------------------------------------
    # harness plumbing
    # ------------------------------------------------------------------
    def _install_harness(self) -> None:
        """Put the script and the parser outside the repository.

        They must not appear in ``git status``: a stray harness file in the
        working tree would contaminate every diff the validator takes.
        """
        self.env.run(f"rm -rf {shlex.quote(self._harness_dir)} && mkdir -p {shlex.quote(self._harness_dir)}")
        for name in ("test_script.sh", "test_parser.py"):
            source = self.artifacts.directory / name
            if not source.is_file():
                raise SsrError(f"{self.artifacts.bug_id}: {name} is missing")
            self._put(f"{self._harness_dir}/{name}", source.read_text(encoding="utf-8"))
        self.env.run(f"chmod +x {shlex.quote(self._harness_dir)}/test_script.sh")

    def _put(self, absolute_path: str, content: str) -> None:
        marker = "SSR_HARNESS_EOF_7c21"
        if marker in content:
            raise SsrError("harness file content collides with the write marker")
        script = f"cat > {shlex.quote(absolute_path)} <<'{marker}'\n{content}\n{marker}\n"
        result = self.env.run(script, timeout_s=120)
        if not result.ok:
            raise SsrError(f"cannot install harness file {absolute_path}: {result.combined[:400]}")

    def _apply(self, name: str, *, revert: bool = False) -> None:
        path = self.artifacts.directory / name
        text = path.read_text(encoding="utf-8") if path.is_file() else ""
        if not text.strip():
            if name == "bug_inject.diff":
                raise SsrError("bug_inject.diff is empty")
            return
        result = self.env.apply_patch(text, reverse=revert)
        if not result.ok:
            raise SsrError(
                f"cannot {'revert' if revert else 'apply'} {name}: {result.combined[:600]}"
            )

    # Public entry points, used by ssr.solving for oracle evaluation.
    def install_harness(self) -> None:
        self._install_harness()

    def run_tests(
        self,
        state: str,
        *,
        patches: list[str] | None = None,
        reset_first: bool = True,
        restore_after: bool = True,
        suffix: str = "",
    ) -> StateResult:
        """Run the test script over a repository state.

        ``reset_first=False`` runs the tests over whatever is in the working
        tree right now. The solver's oracle evaluation needs that: its repair
        lives in the working tree and a reset would throw it away.
        """
        return self._run_state(
            state,
            patches=patches,
            reset_first=reset_first,
            restore_after=restore_after,
            suffix=suffix,
        )

    def _run_state(
        self,
        state: str,
        *,
        patches: list[str] | None = None,
        revert_last: bool = False,
        suffix: str = "",
        reset_first: bool = True,
        restore_after: bool = True,
    ) -> StateResult:
        if reset_first:
            self.env.reset_to_clean()
        for index, name in enumerate(patches or []):
            last = index == len(patches or []) - 1
            self._apply(name)
            if last and revert_last:
                self._apply(name, revert=True)

        timeout = int(self.execution.get("timeout_s", 1800))
        started = time.monotonic()
        run = self.env.run(f"bash {shlex.quote(self._harness_dir)}/test_script.sh", timeout_s=timeout)
        duration = time.monotonic() - started

        raw = run.combined
        log_name = f"{state}{suffix}.log"
        log_file = self.log_dir / log_name
        write_text(log_file, raw)

        result = StateResult(
            exit_code=run.exit_code,
            timed_out=run.timed_out,
            duration_s=duration,
            stdout_sha256=sha256_text(raw),
            log_path=_repo_relative(log_file),
            raw=raw,
        )
        self._parse_into(result, raw)
        if not suffix:
            self.states[state] = result
        if restore_after:
            self.env.reset_to_clean()
        return result

    def _parse_into(self, result: StateResult, raw: str) -> None:
        self._put(f"{self._harness_dir}/raw.txt", raw)
        run = self.env.run(
            f"{self.python()} {shlex.quote(self._harness_dir)}/test_parser.py "
            f"< {shlex.quote(self._harness_dir)}/raw.txt",
            timeout_s=300,
        )
        if not run.ok:
            result.parse_error = f"parser exited {run.exit_code}: {run.combined[:400]}"
            return
        try:
            payload = json.loads(run.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError) as exc:
            result.parse_error = f"parser output is not JSON: {exc}: {run.stdout[:300]}"
            return
        tests = payload.get("tests")
        if not isinstance(tests, dict):
            result.parse_error = "parser output has no 'tests' object"
            return
        result.collection_error = bool(payload.get("collection_error"))
        for name, status in tests.items():
            status = str(status).upper()
            if status in PASSING:
                result.passed.append(name)
            elif status in FAILING:
                result.failed.append(name)
            elif status in ERRORING:
                result.errored.append(name)
            else:
                result.skipped.append(name)

    # ------------------------------------------------------------------
    # the eight checks
    # ------------------------------------------------------------------
    def _set(self, check_id: str, status: str, detail: str | None = None) -> None:
        check = self.checks[check_id]
        check.status = status
        check.detail = detail

    def _check_test_files_exist(self) -> None:
        listed = self.artifacts.read_test_files()
        if not listed:
            self._set("TEST_FILES_EXIST", "FAIL", "test_files.txt is empty")
            return
        missing = [path for path in listed if not self.env.exists(path)]
        if missing:
            self._set("TEST_FILES_EXIST", "FAIL", f"missing in the repository: {', '.join(missing[:10])}")
        else:
            self._set("TEST_FILES_EXIST", "PASS", f"{len(listed)} test file(s) present")

    def _check_script_ran(self, clean: StateResult) -> None:
        if clean.timed_out:
            self._set("TEST_SCRIPT_RUNS_ON_CLEAN", "FAIL", "the test script timed out on the clean repository")
        elif clean.exit_code is not None and clean.exit_code >= 126:
            self._set(
                "TEST_SCRIPT_RUNS_ON_CLEAN",
                "FAIL",
                f"harness-level failure, exit code {clean.exit_code}",
            )
        else:
            self._set("TEST_SCRIPT_RUNS_ON_CLEAN", "PASS", f"exit code {clean.exit_code}")

    def _check_parser(self, clean: StateResult) -> None:
        if clean.parse_error:
            self._set("PARSER_HANDLES_REAL_OUTPUT", "FAIL", clean.parse_error)
        elif clean.total == 0:
            self._set("PARSER_HANDLES_REAL_OUTPUT", "FAIL", "the parser found no tests in the real output")
        else:
            self._set("PARSER_HANDLES_REAL_OUTPUT", "PASS", f"{clean.total} test result(s) parsed")

    def _check_clean_passes(self, clean: StateResult, flaky: list[str]) -> None:
        minimum = int(self.thresholds.get("min_clean_passing", 5))
        stable_passing = [name for name in clean.passed if name not in flaky]
        broken = [name for name in clean.failed + clean.errored if name not in flaky]
        if clean.collection_error and self.thresholds.get("reject_on_collection_error", True):
            self._set("CLEAN_TESTS_PASS", "FAIL", "the clean repository has a collection or import error")
            return
        if broken:
            self._set(
                "CLEAN_TESTS_PASS",
                "FAIL",
                f"{len(broken)} test(s) already fail on the clean repository: {', '.join(sorted(broken)[:5])}",
            )
            return
        if len(stable_passing) < minimum:
            self._set(
                "CLEAN_TESTS_PASS",
                "FAIL",
                f"only {len(stable_passing)} stable passing test(s); {minimum} required",
            )
            return
        self._set("CLEAN_TESTS_PASS", "PASS", f"{len(stable_passing)} stable passing test(s)")

    def _check_bug_creates_failures(
        self, clean: StateResult, bug: StateResult, fail_to_pass: list[str]
    ) -> None:
        minimum = int(self.thresholds.get("min_fail_to_pass", 1))
        if len(fail_to_pass) < minimum:
            self._set(
                "BUG_CREATES_NEW_FAILURES",
                "FAIL",
                f"the injected change produced {len(fail_to_pass)} new failing test(s); {minimum} required",
            )
            return
        stable_passing = max(1, len(clean.passed))
        fraction = len(fail_to_pass) / stable_passing
        ceiling = float(self.thresholds.get("max_fail_to_pass_fraction", 0.5))
        if fraction > ceiling:
            self._set(
                "BUG_CREATES_NEW_FAILURES",
                "FAIL",
                f"the change breaks {fraction:.0%} of the passing suite (ceiling {ceiling:.0%}); "
                "this is a build break, not a semantic bug",
            )
            return
        self._set(
            "BUG_CREATES_NEW_FAILURES",
            "PASS",
            f"{len(fail_to_pass)} newly failing test(s) ({fraction:.0%} of the passing suite)",
        )

    def _check_repo_runnable(self, bug: StateResult) -> None:
        if bug.timed_out:
            self._set("REPO_STAYS_RUNNABLE", "FAIL", "the buggy repository timed out")
            return
        if bug.collection_error and self.thresholds.get("reject_on_collection_error", True):
            self._set(
                "REPO_STAYS_RUNNABLE",
                "FAIL",
                "the buggy repository has a collection or import error; the change broke the build",
            )
            return
        if bug.total == 0:
            self._set("REPO_STAYS_RUNNABLE", "FAIL", "no test result could be parsed from the buggy repository")
            return
        if not bug.passed:
            self._set("REPO_STAYS_RUNNABLE", "FAIL", "no test still passes in the buggy repository")
            return
        self._set(
            "REPO_STAYS_RUNNABLE",
            "PASS",
            f"{len(bug.passed)} test(s) still pass; the suite still runs",
        )

    def _check_weakening(self, fail_to_pass: list[str], weakened: StateResult) -> list[str]:
        still_failing = set(weakened.failed) | set(weakened.errored)
        hidden = sorted(name for name in fail_to_pass if name not in still_failing)
        if not fail_to_pass:
            self._set("WEAKENING_HIDES_FAILURE", "FAIL", "there is no failure to hide")
            return []
        if weakened.collection_error:
            self._set(
                "WEAKENING_HIDES_FAILURE",
                "FAIL",
                "the weakened state has a collection error; the weakening broke the suite",
            )
            return []
        if not hidden:
            self._set(
                "WEAKENING_HIDES_FAILURE",
                "FAIL",
                "the test weakening hides none of the newly failing tests",
            )
            return []
        self._set(
            "WEAKENING_HIDES_FAILURE",
            "PASS",
            f"{len(hidden)} of {len(fail_to_pass)} newly failing test(s) are hidden by the weakening",
        )
        return hidden

    def _check_inverse(self, clean: StateResult, reverted: StateResult, flaky: list[str]) -> None:
        """SSR inverse-mutation criterion: reverting must restore CLEAN exactly."""
        clean_table = {k: v for k, v in clean.table.items() if k not in flaky}
        reverted_table = {k: v for k, v in reverted.table.items() if k not in flaky}
        if clean_table == reverted_table:
            self._set(
                "INVERSE_MUTATION_SUCCEEDS",
                "PASS",
                f"reverting restored the clean result table exactly ({len(clean_table)} test(s))",
            )
            return
        differing = sorted(
            name
            for name in set(clean_table) | set(reverted_table)
            if clean_table.get(name) != reverted_table.get(name)
        )
        self._set(
            "INVERSE_MUTATION_SUCCEEDS",
            "FAIL",
            f"{len(differing)} test(s) differ after reverting: {', '.join(differing[:5])}",
        )


# ----------------------------------------------------------------------
def _repo_relative(path: Path) -> str:
    """Path relative to the repository root, or the absolute path when the
    log directory was redirected somewhere outside it."""
    from ssr.paths import REPO_ROOT

    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _disagreeing(left: dict[str, str], right: dict[str, str]) -> list[str]:
    return [name for name in set(left) | set(right) if left.get(name) != right.get(name)]


def _fail_to_pass(
    clean: StateResult, bug: StateResult, flaky: list[str]
) -> tuple[list[str], list[str]]:
    """Tests that pass on CLEAN and fail (or error) on BUG, and those that
    pass on both. Flaky tests are excluded from both sets."""
    quarantined = set(flaky)
    clean_passing = set(clean.passed) - quarantined
    bug_broken = (set(bug.failed) | set(bug.errored)) - quarantined
    bug_passing = set(bug.passed) - quarantined
    return sorted(clean_passing & bug_broken), sorted(clean_passing & bug_passing)
