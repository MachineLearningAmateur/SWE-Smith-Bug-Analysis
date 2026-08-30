"""First-order bug generation (handoff sections 6 and 7).

Generation runs as three staged agent sessions against one environment. The
staging is what makes the artifact bundle reliable: a single free-running
session rarely produces a test script, a parser, a source change and a
test-weakening change that are all coherent with each other.

    DISCOVER  the agent finds the tests and returns test_files.txt,
              test_script.sh and test_parser.py. The working tree is reset
              afterwards, so discovery cannot leave changes behind.
    INJECT    the agent makes the defect. The working-tree diff becomes
              bug_inject.diff. Touching a test file here is a rejection.
    WEAKEN    bug_inject.diff is applied, and the agent changes test files
              only. The working-tree diff minus the injection becomes
              test_weaken.diff. Touching a source file here is a rejection.

All three stages append to one trajectory.jsonl.

The strategy for an attempt is drawn 50/50 from a fixed seed, and the draw is
recorded, so the sequence of strategies over a corpus run is reproducible.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssr import PROTOCOL_VERSION
from ssr.action_protocol import parse_action
from ssr.agent_loop import AgentLoop, LoopLimits, LoopOutcome
from ssr.artifacts import DEFAULT_PARSER, BugArtifacts
from ssr.exec_env import ExecutionEnvironment
from ssr.metrics import TEST_PATH
from ssr.model import Model
from ssr.util import SsrError, append_jsonl, get_logger, seeded_rng, stable_id, utc_now

STRATEGIES = ("REMOVAL", "HISTORY_REVERSION")
SECTION = re.compile(r"^## +([A-Z_]+) *$", re.MULTILINE)


class GenerationRejected(SsrError):
    """The attempt cannot become a candidate. Recorded for yield analysis."""


def draw_strategy(seed: int, attempt_index: int, weights: dict[str, float]) -> dict[str, Any]:
    """Seeded 50/50 draw between REMOVAL and HISTORY_REVERSION."""
    rng = seeded_rng(seed, "strategy", attempt_index)
    value = rng.random()
    removal_weight = float(weights.get("REMOVAL", 0.5))
    total = removal_weight + float(weights.get("HISTORY_REVERSION", 0.5))
    threshold = removal_weight / total if total else 0.5
    chosen = "REMOVAL" if value < threshold else "HISTORY_REVERSION"
    return {"seed": seed, "attempt_index": attempt_index, "draw_value": value, "chosen": chosen}


def load_prompt_sections(path: Path) -> dict[str, str]:
    """Split a prompt file into its ``## NAME`` sections."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    matches = list(SECTION.finditer(text))
    if not matches:
        raise SsrError(f"{path}: no '## SECTION' headings found")
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end].strip()
        sections[match.group(1)] = body.strip("-\n ").strip() if body.endswith("---") else body
    for required in ("SYSTEM", "DISCOVER", "INJECT", "WEAKEN"):
        if required not in sections:
            raise SsrError(f"{path}: missing '## {required}' section")
    return sections


@dataclass
class DiscoveryResult:
    test_files: list[str]
    test_script: str
    test_parser: str
    summary: str | None
    outcome: LoopOutcome


@dataclass
class GenerationResult:
    bug_id: str
    strategy: str
    strategy_draw: dict[str, Any]
    artifacts: BugArtifacts
    discovery: DiscoveryResult
    inject: LoopOutcome
    weaken: LoopOutcome
    reverted_commits: list[str] = field(default_factory=list)
    buggy_tree_hash: str | None = None
    notes: list[str] = field(default_factory=list)


class Generator:
    def __init__(
        self,
        model: Model,
        env: ExecutionEnvironment,
        config: dict[str, Any],
        *,
        prompts_root: Path,
        pool_root: Path,
        forbidden_context: list[str] | None = None,
    ):
        self.model = model
        self.env = env
        self.config = config
        self.prompts_root = Path(prompts_root)
        self.pool_root = Path(pool_root)
        self.forbidden = forbidden_context or []
        self.limits = LoopLimits.from_config(config.get("agent_loop", {}))
        self.requirements = config.get("requirements", {})
        self._log = get_logger()

    # ------------------------------------------------------------------
    def generate(self, *, attempt_index: int, run_id: str) -> GenerationResult:
        selection = draw_strategy(
            int(self.config["strategy_selection"]["seed"]),
            attempt_index,
            self.config["strategy_selection"].get("weights", {}),
        )
        strategy = selection["chosen"]
        prompt_path = self.prompts_root.parent / self.config["prompts"][strategy]
        sections = load_prompt_sections(prompt_path)

        info = self.env.info()
        bug_id = stable_id("BUG", run_id, attempt_index, info.source_repo, info.source_commit, strategy)
        artifacts = BugArtifacts(bug_id, self.pool_root / bug_id).ensure()
        trajectory = artifacts.trajectory
        append_jsonl(
            trajectory,
            {
                "ts": utc_now(),
                "event": "attempt",
                "bug_id": bug_id,
                "strategy": strategy,
                "strategy_draw": selection,
                "environment": info.to_metadata(),
                "protocol": PROTOCOL_VERSION,
            },
        )

        self.env.reset_to_clean()
        discovery = self._discover(sections, trajectory)

        self.env.reset_to_clean()
        inject = self._inject(sections, discovery, trajectory)
        bug_diff = inject.diff
        self._check_injection(bug_diff)

        self.env.reset_to_clean()
        weaken = self._weaken(sections, discovery, bug_diff, trajectory)
        weaken_diff = weaken.diff
        self._check_weakening(weaken_diff, discovery.test_files)

        artifacts.write_generation_artifacts(
            bug_diff=bug_diff,
            test_script=discovery.test_script,
            test_files=discovery.test_files,
            test_parser=discovery.test_parser,
            weaken_diff=weaken_diff,
        )

        reverted = _reverted_commits(inject)
        self.env.reset_to_clean()

        return GenerationResult(
            bug_id=bug_id,
            strategy=strategy,
            strategy_draw=selection,
            artifacts=artifacts,
            discovery=discovery,
            inject=inject,
            weaken=weaken,
            reverted_commits=reverted,
            buggy_tree_hash=self._buggy_tree_hash(bug_diff),
        )

    # ------------------------------------------------------------------
    def _loop(self, stage: str, system: str, task: str, trajectory: Path) -> LoopOutcome:
        append_jsonl(trajectory, {"ts": utc_now(), "event": "stage", "stage": stage})
        loop = AgentLoop(
            self.model,
            self.env,
            system_prompt=system,
            task_prompt=task,
            limits=self.limits,
            trajectory_path=trajectory,
            forbidden_context=self.forbidden,
            role=f"injector:{stage}",
        )
        return loop.run()

    def _discover(self, sections: dict[str, str], trajectory: Path) -> DiscoveryResult:
        outcome = self._loop("DISCOVER", sections["SYSTEM"], sections["DISCOVER"], trajectory)
        if not outcome.finished:
            raise GenerationRejected(f"discovery did not finish: {outcome.reason}")
        final = outcome.finish_fields
        test_files = [
            line.strip()
            for line in final.get("TEST_FILES", "").splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        script = final.get("TEST_SCRIPT", "").strip()
        parser = final.get("TEST_PARSER", "").strip() or DEFAULT_PARSER
        if not test_files:
            raise GenerationRejected("discovery returned no test files")
        if not script:
            raise GenerationRejected("discovery returned no test script")
        missing = [path for path in test_files if not self.env.exists(path)]
        if missing:
            raise GenerationRejected(f"discovery listed test files that do not exist: {missing[:5]}")
        return DiscoveryResult(
            test_files=test_files,
            test_script=script,
            test_parser=parser,
            summary=outcome.summary,
            outcome=outcome,
        )

    def _inject(self, sections: dict[str, str], discovery: DiscoveryResult, trajectory: Path) -> LoopOutcome:
        task = (
            sections["INJECT"]
            + "\n\n---\n\nWhat you established in stage 1:\n\n"
            + f"Subsystem: {discovery.summary or 'not stated'}\n"
            + "Test files:\n"
            + "".join(f"  {path}\n" for path in discovery.test_files)
            + "\nTest command:\n\n```\n"
            + discovery.test_script.strip()
            + "\n```\n"
        )
        outcome = self._loop("INJECT", sections["SYSTEM"], task, trajectory)
        if not outcome.diff.strip():
            raise GenerationRejected("the injection stage left the working tree unchanged")
        return outcome

    def _weaken(
        self, sections: dict[str, str], discovery: DiscoveryResult, bug_diff: str, trajectory: Path
    ) -> LoopOutcome:
        return run_weaken_stage(
            self.model,
            self.env,
            sections,
            bug_diff=bug_diff,
            test_files=discovery.test_files,
            test_script=discovery.test_script,
            trajectory=trajectory,
            limits=self.limits,
            forbidden_context=self.forbidden,
        )

    # ------------------------------------------------------------------
    def _check_injection(self, diff: str) -> None:
        files = _changed_files(diff)
        if not files:
            raise GenerationRejected("the injected diff touches no file")
        touched_tests = [path for path in files if TEST_PATH.search(path)]
        if touched_tests:
            raise GenerationRejected(f"the injection touched test files: {touched_tests[:5]}")
        max_files = int(self.requirements.get("max_changed_files", 25))
        if len(files) > max_files:
            raise GenerationRejected(f"the injection touched {len(files)} files; the ceiling is {max_files}")
        changed_lines = sum(
            1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
        )
        minimum = int(self.requirements.get("min_changed_lines", 3))
        if changed_lines < minimum:
            raise GenerationRejected(f"the injection changed {changed_lines} lines; {minimum} required")

    def _check_weakening(self, diff: str, test_files: list[str]) -> None:
        check_weakening_scope(diff, test_files)

    def _buggy_tree_hash(self, bug_diff: str) -> str | None:
        """Hash of the tree the injection produces. Used for deduplication."""
        applied = self.env.apply_patch(bug_diff)
        if not applied.ok:
            return None
        result = self.env.run("git add -A && git write-tree")
        tree = result.stdout.strip().splitlines()[-1] if result.ok and result.stdout.strip() else None
        self.env.reset_to_clean()
        return tree


# ----------------------------------------------------------------------
def run_weaken_stage(
    model: Model,
    env: ExecutionEnvironment,
    sections: dict[str, str],
    *,
    bug_diff: str,
    test_files: list[str],
    test_script: str,
    trajectory: Path,
    limits: LoopLimits,
    forbidden_context: list[str] | None = None,
    stage_label: str = "WEAKEN",
) -> LoopOutcome:
    """Run the test-weakening stage against a buggy state.

    Shared by first-order generation and second-order construction. A
    second-order state gets its own weakening rather than inheriting the
    parent's: the parent's test edit was written against the parent's
    failures, and there is no reason it should hide the child's.
    """
    env.reset_to_clean()
    applied = env.apply_patch(bug_diff)
    if not applied.ok:
        raise GenerationRejected(f"the buggy diff does not re-apply cleanly: {applied.combined[:400]}")
    baseline = env.commit_all("ssr: staged buggy state for the weakening stage")
    task = (
        sections["WEAKEN"]
        + "\n\n---\n\nTest files you may change:\n"
        + "".join(f"  {path}\n" for path in test_files)
        + "\nTest command:\n\n```\n"
        + test_script.strip()
        + "\n```\n"
    )
    append_jsonl(trajectory, {"ts": utc_now(), "event": "stage", "stage": stage_label})
    loop = AgentLoop(
        model,
        env,
        system_prompt=sections["SYSTEM"],
        task_prompt=task,
        limits=limits,
        trajectory_path=trajectory,
        forbidden_context=forbidden_context,
        role=f"injector:{stage_label}",
    )
    try:
        outcome = loop.run()
    finally:
        # Drop the staging commit so the environment returns to upstream HEAD.
        env.run(f"git reset --hard --quiet {baseline}~1 || git reset --hard --quiet HEAD~1")
        env.run("git clean -fdq")
    if not outcome.diff.strip():
        raise GenerationRejected("the weakening stage left the tests unchanged")
    return outcome


def check_weakening_scope(diff: str, test_files: list[str]) -> None:
    """The weakening may touch test files only."""
    files = _changed_files(diff)
    if not files:
        raise GenerationRejected("the weakening diff touches no file")
    allowed = set(test_files)
    offenders = [path for path in files if path not in allowed and not TEST_PATH.search(path)]
    if offenders:
        raise GenerationRejected(f"the weakening touched non-test files: {offenders[:5]}")


_DIFF_FILE = re.compile(r"^diff --git a/.+? b/(.+)$", re.MULTILINE)


def _changed_files(diff: str) -> list[str]:
    return sorted({match.group(1) for match in _DIFF_FILE.finditer(diff.replace("\r\n", "\n"))})


def _reverted_commits(outcome: LoopOutcome) -> list[str]:
    """Commit SHAs the agent said it reversed, from its own FINISH block."""
    raw = outcome.finish_fields.get("REVERTED_COMMITS", "")
    return [
        token.strip()
        for token in raw.replace(",", "\n").splitlines()
        if re.fullmatch(r"[0-9a-f]{7,40}", token.strip())
    ]


def parse_finish_fields(reply: str) -> dict[str, str]:
    """Public helper used by tests: the fields of a FINISH reply."""
    action = parse_action(reply)
    if action.name != "FINISH":
        raise SsrError(f"expected FINISH, got {action.name}")
    return action.fields
