"""Solver evaluation and second-order construction (handoff section 9).

For each validated first-order bug chosen for solver evaluation:

    1. build the SSR-style solver state: the buggy repository plus the
       neutral failure evidence a maintainer would have;
    2. run the SAME model as the injector;
    3. save the prediction patch;
    4. run the oracle evaluation;
    5. if, and only if, the repair genuinely fails, build a second-order
       buggy state from it.

Nothing here is allowed to push the solver towards failure. The solver sees
the failing test names, the test command and the failing output. It does not
see the injection diff, the strategy, the weakening diff, or any generation
metadata. If the yield of failed repairs is low, the low yield is the result
to report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssr.agent_loop import AgentLoop, LoopLimits, LoopOutcome
from ssr.artifacts import BugArtifacts
from ssr.exec_env import ExecutionEnvironment
from ssr.generation import SECTION
from ssr.model import Model
from ssr.util import SsrError, append_jsonl, get_logger, stable_id, truncate, utc_now

SOLVER_SECTIONS = ("SYSTEM", "TASK")


class SolverError(SsrError):
    """The solver attempt could not be carried out at all."""


@dataclass
class SolverAttempt:
    parent_bug_id: str
    outcome: LoopOutcome
    pred_patch: str
    oracle_result: str  # PASSED | FAILED | ERROR
    still_failing: list[str] = field(default_factory=list)
    newly_broken: list[str] = field(default_factory=list)
    detail: str = ""

    @property
    def changed_lines(self) -> int:
        return sum(
            1
            for line in self.pred_patch.splitlines()
            if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )

    def to_record(self) -> dict[str, Any]:
        return {
            "parent_bug_id": self.parent_bug_id,
            "oracle_result": self.oracle_result,
            "still_failing": sorted(self.still_failing),
            "newly_broken": sorted(self.newly_broken),
            "pred_patch_changed_lines": self.changed_lines,
            "detail": self.detail,
            "loop": self.outcome.to_record(),
        }


def load_solver_prompt(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    matches = list(SECTION.finditer(text))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections[match.group(1)] = text[match.end() : end].strip()
    missing = [name for name in SOLVER_SECTIONS if name not in sections]
    if missing:
        raise SsrError(f"{path}: missing section(s) {missing}")
    return sections


class Solver:
    def __init__(
        self,
        model: Model,
        env: ExecutionEnvironment,
        config: dict[str, Any],
        *,
        prompt_path: Path,
    ):
        self.model = model
        self.env = env
        self.config = config
        self.sections = load_solver_prompt(prompt_path)
        self.limits = LoopLimits.from_config(config.get("agent_loop", {}))
        self._log = get_logger()

    def attempt(
        self,
        artifacts: BugArtifacts,
        validation: dict[str, Any],
        *,
        trajectory_path: Path,
    ) -> SolverAttempt:
        fail_to_pass = list(validation.get("fail_to_pass") or [])
        if not fail_to_pass:
            raise SolverError(f"{artifacts.bug_id}: no oracle tests to repair")

        self.env.reset_to_clean()
        applied = self.env.apply_patch(artifacts.diff_text())
        if not applied.ok:
            raise SolverError(f"{artifacts.bug_id}: the buggy state does not apply: {applied.combined[:400]}")
        baseline = self.env.commit_all("ssr: buggy state presented to the solver")

        task = self._render_task(artifacts, validation, fail_to_pass)
        append_jsonl(
            trajectory_path,
            {"ts": utc_now(), "event": "stage", "stage": "SOLVE", "parent_bug_id": artifacts.bug_id},
        )
        loop = AgentLoop(
            self.model,
            self.env,
            system_prompt=self.sections["SYSTEM"],
            task_prompt=task,
            limits=self.limits,
            trajectory_path=trajectory_path,
            # The solver must not be told anything about how the state arose.
            forbidden_context=[artifacts.diff_text()[:400]] if artifacts.diff_text() else [],
            role="solver",
        )
        outcome = loop.run()
        pred_patch = outcome.diff

        attempt = SolverAttempt(
            parent_bug_id=artifacts.bug_id,
            outcome=outcome,
            pred_patch=pred_patch,
            oracle_result="ERROR",
        )
        try:
            self._evaluate(artifacts, validation, attempt)
        finally:
            self.env.run(f"git reset --hard --quiet {baseline}~1 || git reset --hard --quiet HEAD~1")
            self.env.run("git clean -fdq")
        return attempt

    # ------------------------------------------------------------------
    def _render_task(
        self, artifacts: BugArtifacts, validation: dict[str, Any], fail_to_pass: list[str]
    ) -> str:
        evidence = self.config.get("evidence_given_to_solver", {})
        listed = "\n".join(f"  {name}" for name in sorted(fail_to_pass))
        command = artifacts.test_script.read_text(encoding="utf-8").strip() if evidence.get(
            "test_command", True
        ) else "(withheld)"
        output = ""
        if evidence.get("failing_test_output", True):
            log = artifacts.directory / "logs" / "BUG.log"
            if log.is_file():
                output, _ = truncate(log.read_text(encoding="utf-8", errors="replace"), 8000)
        return self.sections["TASK"].format(
            failing_tests=listed or "  (none listed)",
            test_command=command,
            failing_output=output or "(no captured output)",
        )

    def _evaluate(
        self, artifacts: BugArtifacts, validation: dict[str, Any], attempt: SolverAttempt
    ) -> None:
        """Oracle evaluation: run the same test script over the repaired state."""
        from ssr.validation import Validator

        if not attempt.pred_patch.strip():
            attempt.oracle_result = "FAILED"
            attempt.still_failing = list(validation.get("fail_to_pass") or [])
            attempt.detail = "the solver produced no change"
            return

        validator = Validator(self.env, artifacts, {"test_execution": self.config.get("test_execution", {})})
        try:
            validator.install_harness()
            # The repair is in the working tree; a reset would discard it.
            state = validator.run_tests("SOLVED", reset_first=False, restore_after=False)
        except SsrError as exc:
            attempt.oracle_result = "ERROR"
            attempt.detail = f"oracle evaluation failed: {exc}"
            return

        oracle = set(validation.get("fail_to_pass") or [])
        broken = set(state.failed) | set(state.errored)
        attempt.still_failing = sorted(oracle & broken)
        pass_to_pass = set(validation.get("pass_to_pass") or [])
        attempt.newly_broken = sorted(pass_to_pass & broken)

        if state.collection_error:
            attempt.oracle_result = "FAILED"
            attempt.detail = "the repaired state does not collect"
        elif attempt.still_failing or attempt.newly_broken:
            attempt.oracle_result = "FAILED"
            attempt.detail = (
                f"{len(attempt.still_failing)} oracle test(s) still fail; "
                f"{len(attempt.newly_broken)} previously passing test(s) broke"
            )
        else:
            attempt.oracle_result = "PASSED"
            attempt.detail = "the repair fixed every oracle test and broke nothing"


# ----------------------------------------------------------------------
def second_order_eligible(attempt: SolverAttempt, config: dict[str, Any]) -> tuple[bool, str]:
    """Whether a failed repair may become a second-order bug state."""
    rules = config.get("second_order", {})
    if not rules.get("enabled", True):
        return False, "second-order construction is turned off"
    if attempt.oracle_result != "FAILED":
        return False, f"the oracle result is {attempt.oracle_result}, not FAILED"
    if rules.get("require_solver_patch_nonempty", True) and not attempt.pred_patch.strip():
        return False, "the solver produced no patch"
    minimum = int(rules.get("min_solver_patch_changed_lines", 2))
    if attempt.changed_lines < minimum:
        return False, f"the repair changed {attempt.changed_lines} line(s); {minimum} required"
    if rules.get("require_oracle_still_failing", True) and not (
        attempt.still_failing or attempt.newly_broken
    ):
        return False, "no test fails in the repaired state"
    return True, "a genuine failed repair"


def build_second_order_state(
    parent: BugArtifacts,
    pred_patch: str,
    env: ExecutionEnvironment,
    pool_root: Path,
    *,
    run_id: str,
    summary: str = "",
) -> tuple[BugArtifacts, str]:
    """Combine the injection and the failed repair into one clean-to-buggy diff.

    The combined diff is taken from the repository itself rather than by
    concatenating two patches, so it always applies to the clean state and a
    reviewer cannot tell from its structure that it has two stages.
    """
    env.reset_to_clean()
    applied = env.apply_patch(parent.diff_text())
    if not applied.ok:
        raise SolverError(f"{parent.bug_id}: the parent diff does not apply: {applied.combined[:400]}")
    repaired = env.apply_patch(pred_patch)
    if not repaired.ok:
        raise SolverError(
            f"{parent.bug_id}: the repair patch does not apply on top of the parent: "
            f"{repaired.combined[:400]}"
        )
    combined = env.diff_against_head()
    tree = env.run("git add -A && git write-tree")
    tree_hash = tree.stdout.strip().splitlines()[-1] if tree.ok and tree.stdout.strip() else None
    env.reset_to_clean()

    if not combined.strip():
        raise SolverError(f"{parent.bug_id}: the combined second-order diff is empty")

    child_id = stable_id("BUG", run_id, "second-order", parent.bug_id, summary)
    child = BugArtifacts(child_id, pool_root / child_id).ensure()
    child.write_generation_artifacts(
        bug_diff=combined,
        test_script=parent.test_script.read_text(encoding="utf-8"),
        test_files=parent.read_test_files(),
        test_parser=parent.test_parser.read_text(encoding="utf-8"),
        weaken_diff=parent.test_weaken.read_text(encoding="utf-8"),
    )
    from ssr.util import write_text

    write_text(child.pred_patch, pred_patch)
    return child, tree_hash or ""
