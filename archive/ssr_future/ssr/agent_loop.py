"""The injector and solver agent loop.

The loop is the same for both roles. What differs is the system prompt and
what the first user turn is allowed to contain.

Context isolation (handoff section 6) is enforced here, not by convention.
``AgentLoop`` refuses to start when any string in ``forbidden_context``
appears in the prompt it is about to send. The caller passes SWE-smith's
known test command, the RepoProfile test metadata, the synthetic issue text
and the fail-to-pass test list as forbidden strings, so a leak becomes a
crash rather than a silently contaminated corpus.

The full action and observation trajectory is preserved to
``trajectory.jsonl``, one JSON object per line.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ssr.action_protocol import Action, ProtocolError, format_protocol_reference, parse_action
from ssr.exec_env import ExecutionEnvironment
from ssr.model import Model, Usage
from ssr.util import SsrError, append_jsonl, get_logger, redact, sha256_text, truncate, utc_now


@dataclass
class LoopLimits:
    max_steps: int = 60
    max_parse_failures: int = 3
    command_timeout_s: int = 300
    max_observation_bytes: int = 12_000
    max_read_bytes: int = 40_000
    context_window_turns: int = 24

    @classmethod
    def from_config(cls, section: dict[str, Any]) -> "LoopLimits":
        return cls(
            max_steps=int(section.get("max_steps", 60)),
            max_parse_failures=int(section.get("max_parse_failures", 3)),
            command_timeout_s=int(section.get("command_timeout_s", 300)),
            max_observation_bytes=int(section.get("max_observation_bytes", 12_000)),
            max_read_bytes=int(section.get("max_read_bytes", 40_000)),
            context_window_turns=int(section.get("context_window_turns", 24)),
        )


@dataclass
class LoopOutcome:
    finished: bool
    reason: str
    steps_used: int
    parse_failures: int
    summary: str | None
    usage: Usage
    diff: str = ""
    trajectory_path: Path | None = None
    actions_taken: list[str] = field(default_factory=list)
    # Every field of this stage's FINISH block. Held per stage, because
    # several stages append to one trajectory file and a later stage would
    # otherwise overwrite what an earlier one reported.
    finish_fields: dict[str, str] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        return {
            "finished": self.finished,
            "reason": self.reason,
            "steps_used": self.steps_used,
            "parse_failures": self.parse_failures,
            "summary": self.summary,
            "usage": self.usage.to_dict(),
            "actions_taken": self.actions_taken,
            "finish_fields": sorted(self.finish_fields),
        }


class AgentLoop:
    def __init__(
        self,
        model: Model,
        env: ExecutionEnvironment,
        *,
        system_prompt: str,
        task_prompt: str,
        limits: LoopLimits,
        trajectory_path: Path,
        forbidden_context: list[str] | None = None,
        role: str = "injector",
    ):
        self.model = model
        self.env = env
        self.limits = limits
        self.role = role
        self.trajectory_path = Path(trajectory_path)
        self.system_prompt = system_prompt.rstrip() + "\n\n" + format_protocol_reference()
        self.task_prompt = task_prompt
        self.forbidden = [item for item in (forbidden_context or []) if item and len(item) >= 6]
        self._log = get_logger()

    # ----------------------------------------------------------------------
    def _assert_clean(self, text: str, where: str) -> None:
        lowered = text.lower()
        for secret in self.forbidden:
            if secret.lower() in lowered:
                raise SsrError(
                    f"context isolation violated in {where}: the {self.role} prompt contains "
                    f"withheld environment metadata ({secret[:60]!r}). Refusing to continue; "
                    "this candidate would be contaminated."
                )

    def _record(self, payload: dict[str, Any]) -> None:
        payload = {"ts": utc_now(), **payload}
        append_jsonl(self.trajectory_path, payload)

    def _window(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        """Keep the system prompt, the first user turn, and the most recent
        turns. The early turns carry the task; the late turns carry the state."""
        keep = self.limits.context_window_turns
        if len(messages) <= keep + 2:
            return messages
        return messages[:2] + messages[-keep:]

    # ----------------------------------------------------------------------
    def run(self) -> LoopOutcome:
        self._assert_clean(self.system_prompt, "system prompt")
        self._assert_clean(self.task_prompt, "task prompt")

        messages: list[dict[str, str]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": self.task_prompt},
        ]
        self._record(
            {
                "event": "start",
                "role": self.role,
                "model": self.model.describe(),
                "limits": self.limits.__dict__,
                "system_prompt_sha256": sha256_text(self.system_prompt),
                "task_prompt_sha256": sha256_text(self.task_prompt),
                "task_prompt": self.task_prompt,
            }
        )

        parse_failures = 0
        consecutive_parse_failures = 0
        summary: str | None = None
        finish_fields: dict[str, str] = {}
        actions_taken: list[str] = []
        reason = "step budget exhausted"
        finished = False

        for step in range(1, self.limits.max_steps + 1):
            started = time.monotonic()
            reply = self.model.complete(self._window(messages))
            messages.append({"role": "assistant", "content": reply.text})

            try:
                action = parse_action(reply.text)
            except ProtocolError as exc:
                parse_failures += 1
                consecutive_parse_failures += 1
                observation = (
                    f"PROTOCOL ERROR: {exc}\n\n"
                    "Reply again with exactly one well-formed action block."
                )
                self._record(
                    {
                        "event": "parse_error",
                        "step": step,
                        "error": str(exc),
                        "reply": redact(reply.text),
                    }
                )
                messages.append({"role": "user", "content": observation})
                if consecutive_parse_failures >= self.limits.max_parse_failures:
                    reason = f"aborted after {consecutive_parse_failures} consecutive protocol errors"
                    break
                continue

            consecutive_parse_failures = 0
            actions_taken.append(action.name)
            self._record(
                {
                    "event": "action",
                    "step": step,
                    "action": action.to_record(),
                    "model_latency_s": round(time.monotonic() - started, 3),
                }
            )

            if action.name == "FINISH":
                summary = action.get("SUMMARY").strip() or None
                finish_fields = dict(action.fields)
                finished = True
                reason = "model emitted FINISH"
                self._record({"event": "finish", "step": step, "summary": summary})
                break

            observation = self._execute(action)
            self._record(
                {
                    "event": "observation",
                    "step": step,
                    "action": action.name,
                    "observation": observation,
                }
            )
            messages.append({"role": "user", "content": observation})
        else:
            reason = f"step budget of {self.limits.max_steps} exhausted"

        diff = self.env.diff_against_head()
        outcome = LoopOutcome(
            finished=finished,
            reason=reason,
            steps_used=len(actions_taken) + parse_failures,
            parse_failures=parse_failures,
            summary=summary,
            usage=self.model.total,
            diff=diff,
            trajectory_path=self.trajectory_path,
            actions_taken=actions_taken,
            finish_fields=finish_fields,
        )
        self._record({"event": "end", **outcome.to_record(), "diff_sha256": sha256_text(diff)})
        return outcome

    # ----------------------------------------------------------------------
    def _execute(self, action: Action) -> str:
        limit = self.limits.max_observation_bytes
        try:
            if action.name == "SHELL":
                command = action.get("COMMAND").strip()
                if not command:
                    return "ERROR: COMMAND was empty."
                result = self.env.run(command, timeout_s=self.limits.command_timeout_s)
                return result.observation(limit)

            if action.name == "READ":
                path = action.get("PATH").strip()
                if not self.env.exists(path):
                    return f"ERROR: {path} does not exist in the repository."
                content = self.env.read_file(path, max_bytes=self.limits.max_read_bytes)
                body, was_truncated = truncate(content, limit)
                note = " (truncated)" if was_truncated else ""
                return f"[contents of {path}{note}]\n{body}"

            if action.name == "WRITE":
                path = action.get("PATH").strip()
                self.env.write_file(path, action.get("CONTENT"))
                return f"[wrote {path}, {len(action.get('CONTENT'))} bytes]"

            if action.name == "EDIT":
                return self._edit(action)

            if action.name == "GIT_DIFF":
                diff = self.env.diff_against_head()
                if not diff.strip():
                    return "[no changes in the working tree]"
                body, was_truncated = truncate(diff, limit)
                return f"[working tree diff{' (truncated)' if was_truncated else ''}]\n{body}"

            if action.name == "GIT_STATUS":
                return self.env.git("status --short --branch").observation(limit)

            if action.name == "GIT_LOG":
                count = action.get("COUNT", "30").strip() or "30"
                if not count.isdigit():
                    count = "30"
                count = str(min(int(count), 500))
                return self.env.git(
                    f"log --oneline --decorate -n {count}", timeout_s=self.limits.command_timeout_s
                ).observation(limit)

        except SsrError as exc:
            return f"ERROR: {exc}"

        return f"ERROR: action {action.name} is not executable."

    def _edit(self, action: Action) -> str:
        path = action.get("PATH").strip()
        old = action.get("OLD")
        new = action.get("NEW")
        if not self.env.exists(path):
            return f"ERROR: {path} does not exist. Use ACTION: WRITE to create a file."
        content = self.env.read_file(path, max_bytes=2_000_000)
        occurrences = content.count(old)
        if occurrences == 0:
            return (
                f"ERROR: the OLD text was not found in {path}. Read the file again and copy "
                "the exact text, including indentation."
            )
        if occurrences > 1:
            return (
                f"ERROR: the OLD text occurs {occurrences} times in {path}. Extend it with "
                "surrounding lines so that it occurs exactly once."
            )
        self.env.write_file(path, content.replace(old, new, 1))
        return f"[edited {path}: replaced {len(old)} bytes with {len(new)} bytes]"


def make_forbidden_context(env_record: dict[str, Any]) -> list[str]:
    """Strings the injector must never see (handoff section 6).

    Everything SWE-smith already knows about how to test the repository, and
    everything a native SWE-smith mutation would reveal, is withheld. The
    injector has to find the tests itself.
    """
    withheld: list[str] = []
    for key in (
        "test_cmd",
        "test_command",
        "install_cmd",
        "log_parser",
        "problem_statement",
        "issue_text",
        "synthetic_issue",
        "mutation_type",
        "mutation_metadata",
    ):
        value = env_record.get(key)
        if isinstance(value, str):
            withheld.append(value)
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS", "fail_to_pass", "pass_to_pass"):
        value = env_record.get(key)
        if isinstance(value, (list, tuple)):
            withheld.extend(str(item) for item in value)
        elif isinstance(value, str):
            withheld.append(value)
    return [item for item in withheld if item]
