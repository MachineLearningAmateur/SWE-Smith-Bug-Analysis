"""The strict textual action protocol.

The OpenRouter endpoint for Qwen2.5-Coder-32B-Instruct does not expose native
function calling consistently enough for this harness, so the agent loop is
driven by plain text. The model emits one action per turn:

    ACTION: SHELL
    COMMAND: git log --oneline -20

    ACTION: READ
    PATH: src/foo.py

    ACTION: WRITE
    PATH: src/foo.py
    CONTENT:
    <<<END
    ...whole new file text...
    END

    ACTION: EDIT
    PATH: src/foo.py
    OLD:
    <<<END
    ...text to replace, must appear exactly once...
    END
    NEW:
    <<<END
    ...replacement text...
    END

    ACTION: GIT_DIFF
    ACTION: GIT_STATUS
    ACTION: GIT_LOG
    COUNT: 30

    ACTION: FINISH
    SUMMARY: one line on what the change does

Parsing is deliberately forgiving about what surrounds the block (prose,
markdown fences, a stray blank line) and deliberately strict about the block
itself. A reply that cannot be parsed produces an error observation naming
the problem, and the loop asks again; the loop aborts after
``max_parse_failures`` consecutive failures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PROTOCOL_VERSION = "ssr-action-protocol/1"

ACTIONS = ("SHELL", "READ", "WRITE", "EDIT", "GIT_DIFF", "GIT_STATUS", "GIT_LOG", "FINISH")

REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "SHELL": ("COMMAND",),
    "READ": ("PATH",),
    "WRITE": ("PATH", "CONTENT"),
    "EDIT": ("PATH", "OLD", "NEW"),
    "GIT_DIFF": (),
    "GIT_STATUS": (),
    "GIT_LOG": (),
    "FINISH": ("SUMMARY",),
}

_ACTION_LINE = re.compile(r"^[ \t>*-]*ACTION[ \t]*:[ \t]*([A-Za-z_]+)[ \t]*$", re.MULTILINE)
_HEADER_LINE = re.compile(r"^([A-Z][A-Z0-9_]*)[ \t]*:[ \t]*(.*)$")
_BLOCK_OPEN = re.compile(r"^<<<[ \t]*([A-Za-z0-9_]+)[ \t]*$")
_FENCE = re.compile(r"^[ \t]*```[A-Za-z0-9_+-]*[ \t]*$")


class ProtocolError(ValueError):
    """The model reply does not carry exactly one well-formed action."""


@dataclass
class Action:
    name: str
    fields: dict[str, str] = field(default_factory=dict)
    raw: str = ""
    trailing_actions: int = 0

    def get(self, key: str, default: str = "") -> str:
        return self.fields.get(key, default)

    def to_record(self) -> dict[str, Any]:
        """Trajectory form. Long bodies are kept whole: the trajectory is the
        provenance record and must not be lossy."""
        return {"action": self.name, "fields": dict(self.fields)}


def _strip_fences(text: str) -> str:
    """Drop markdown fences that wrap the whole reply.

    Fences inside a ``<<<MARKER`` body are left alone: block bodies are read
    verbatim by the parser below, which never sees this function's output for
    the body it has already captured.
    """
    lines = text.splitlines()
    if len(lines) >= 2 and _FENCE.match(lines[0]) and _FENCE.match(lines[-1]):
        return "\n".join(lines[1:-1])
    return text


def parse_action(reply: str) -> Action:
    """Parse the first complete action in a model reply.

    Raises ProtocolError with a message written for the model to act on.
    """
    if not reply or not reply.strip():
        raise ProtocolError("Empty reply. Emit exactly one action block.")

    text = _strip_fences(reply.replace("\r\n", "\n"))
    starts = [(match.start(), match.group(1).upper()) for match in _ACTION_LINE.finditer(text)]
    if not starts:
        raise ProtocolError(
            "No 'ACTION: <NAME>' line found. The first line of the action block must be "
            "exactly 'ACTION: ' followed by one of: " + ", ".join(ACTIONS)
        )

    offset, name = starts[0]
    if name not in ACTIONS:
        raise ProtocolError(
            f"Unknown action {name!r}. Supported actions: " + ", ".join(ACTIONS)
        )

    end = starts[1][0] if len(starts) > 1 else len(text)
    body = text[offset:end]
    fields = _parse_fields(body.splitlines()[1:], name)

    missing = [key for key in REQUIRED_FIELDS[name] if key not in fields]
    if missing:
        raise ProtocolError(
            f"Action {name} is missing required field(s): {', '.join(missing)}. "
            f"{name} needs: {', '.join(REQUIRED_FIELDS[name]) or '(no fields)'}."
        )

    return Action(
        name=name,
        fields=fields,
        raw=body.strip(),
        trailing_actions=max(0, len(starts) - 1),
    )


def _parse_fields(lines: list[str], action_name: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip() or _FENCE.match(line):
            index += 1
            continue
        header = _HEADER_LINE.match(line)
        if not header:
            # Free prose around the block is tolerated.
            index += 1
            continue
        key, inline = header.group(1), header.group(2).strip()
        if inline:
            fields[key] = inline
            index += 1
            continue
        # A header with no inline value must open a block.
        index += 1
        while index < len(lines) and (not lines[index].strip() or _FENCE.match(lines[index])):
            index += 1
        if index >= len(lines):
            raise ProtocolError(
                f"Field {key} in action {action_name} has no value. Either write "
                f"'{key}: <value>' on one line, or open a block with '<<<END' on the "
                f"next line and close it with a line containing only 'END'."
            )
        opener = _BLOCK_OPEN.match(lines[index].strip())
        if not opener:
            raise ProtocolError(
                f"Field {key} in action {action_name} must be followed by a block that "
                f"opens with '<<<END' and closes with 'END' on its own line."
            )
        marker = opener.group(1)
        index += 1
        collected: list[str] = []
        closed = False
        while index < len(lines):
            if lines[index].strip() == marker:
                closed = True
                index += 1
                break
            collected.append(lines[index])
            index += 1
        if not closed:
            raise ProtocolError(
                f"Block for field {key} in action {action_name} was opened with "
                f"'<<<{marker}' but never closed. Close it with a line containing "
                f"only '{marker}'."
            )
        fields[key] = "\n".join(collected)
    return fields


def format_protocol_reference() -> str:
    """The protocol section injected into every system prompt.

    Kept here, not in the prompt files, so the injector prompt, the solver
    prompt and the parser can never drift apart.
    """
    return """\
## Action protocol

Reply with EXACTLY ONE action block and nothing else. No commentary before or
after it. The first line of the block must be `ACTION: <NAME>`.

Available actions:

    ACTION: SHELL
    COMMAND: <one shell command line>

    ACTION: READ
    PATH: <repository-relative path>

    ACTION: WRITE
    PATH: <repository-relative path>
    CONTENT:
    <<<END
    <the complete new contents of the file>
    END

    ACTION: EDIT
    PATH: <repository-relative path>
    OLD:
    <<<END
    <exact text to replace; it must occur exactly once in the file>
    END
    NEW:
    <<<END
    <replacement text>
    END

    ACTION: GIT_DIFF

    ACTION: GIT_STATUS

    ACTION: GIT_LOG
    COUNT: <number of commits, default 30>

    ACTION: FINISH
    SUMMARY: <one line stating what the final change does>

Rules:

* One action per reply. A second `ACTION:` line in the same reply is ignored.
* Paths are relative to the repository root. `..` is refused.
* A block value opens with `<<<END` on its own line and closes with `END` on
  its own line.
* Each command runs in the repository root inside an isolated container.
  There is no network access.
* Emit `ACTION: FINISH` only when the working tree already holds the change
  you intend to submit.
"""
