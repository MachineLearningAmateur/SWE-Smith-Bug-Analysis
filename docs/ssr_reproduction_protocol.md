# SSR reproduction protocol

How a bug is made, checked, attacked, and turned into a second-order bug.

## The action protocol

The OpenRouter endpoint for Qwen2.5-Coder-32B-Instruct does not expose native
function calling reliably enough to build a harness on, so the agent loop is
driven by plain text. The model emits exactly one action per turn:

```
ACTION: SHELL
COMMAND: git log --oneline -20
```

```
ACTION: EDIT
PATH: src/foo.py
OLD:
<<<END
text to replace, must occur exactly once
END
NEW:
<<<END
replacement
END
```

Supported actions: `SHELL`, `READ`, `WRITE`, `EDIT`, `GIT_DIFF`,
`GIT_STATUS`, `GIT_LOG`, `FINISH`.

The parser (`ssr/action_protocol.py`) is forgiving about what surrounds the
block — prose, markdown fences, blank lines — and strict about the block
itself. A malformed reply produces an error observation that names the
problem, and the model gets another turn; three consecutive protocol errors
abort the attempt. Every action and observation is written to
`trajectory.jsonl`.

Commands run inside the environment with the API key stripped from the
process environment, and file paths are confined to the repository root.

## Strategy selection

Each attempt draws REMOVAL or HISTORY_REVERSION 50/50 from the seed in
`configs/generator.yaml`. The draw is recorded in `metadata.strategy_draw`, so
the strategy sequence over a run is reproducible.

## Three staged sessions

A single free-running session rarely produces a test script, a parser, a
source change and a test-weakening change that are all coherent with each
other. Generation is therefore staged, with the working tree reset between
stages, all three appending to one trajectory:

**DISCOVER.** The agent explores the repository and returns `test_files.txt`,
`test_script.sh` and `test_parser.py` in its `FINISH` block. It is told
nothing about how the project is tested. The listed files must exist or the
attempt is rejected.

**INJECT.** The agent makes the defect. The working-tree diff becomes
`bug_inject.diff`. Touching a test file here rejects the attempt, as does a
change smaller than `requirements.min_changed_lines` or wider than
`requirements.max_changed_files`.

**WEAKEN.** `bug_inject.diff` is applied and committed as a staging commit;
the agent may then change test files only. The resulting diff becomes
`test_weaken.diff`. Touching a source file rejects the attempt.

### REMOVAL

Remove code that carries real behaviour — a branch that handles a real case, a
validation step, one of the operations a function performs — plus whatever
small compatibility edits the removal needs. The result must be a semantic
bug: a syntax error or a broken import is not one.

### HISTORY_REVERSION

Find a past commit that changed real behaviour and undo that change **by hand
in the current code**. Checking out an old commit and `git revert` are both
forbidden: the code has moved on, and the interesting part is exactly the
compatibility work of applying an old behaviour to new code. The agent
reports the commits it reversed in a `REVERTED_COMMITS` block, which is hidden
metadata used only for deduplication.

## Artifacts

Every candidate produces:

```
bug_inject.diff     clean -> buggy source change
test_script.sh      the command that runs the relevant tests
test_files.txt      the test files it covers
test_parser.py      raw output -> a result table
test_weaken.diff    a test-side change that hides part of the failure
metadata.json       hidden generation metadata
trajectory.jsonl    the full action/observation record
validation.json     the execution-validation result
```

The parser contract, which `PARSER_HANDLES_REAL_OUTPUT` checks:

```
python3 test_parser.py < raw_output.txt
```

prints one JSON object:

```json
{"tests": {"<test id>": "PASSED"|"FAILED"|"ERROR"|"SKIPPED"},
 "collection_error": false}
```

## Validation: the eight checks

`scripts/validate_bug.py` executes four repository states and evaluates eight
checks. Every one must pass. A rejected candidate keeps its logs, because
yield analysis needs the failures.

| State | What it is |
|---|---|
| `CLEAN` | The upstream repository. Run twice; a test that changes result between identical runs is quarantined as flaky and excluded from the oracle. |
| `BUG` | `CLEAN` + `bug_inject.diff` |
| `BUG_WEAKENED` | `BUG` + `test_weaken.diff` |
| `BUG_REVERTED` | `BUG` with `bug_inject.diff` reversed |

1. **TEST_FILES_EXIST** — every listed path exists.
2. **PARSER_HANDLES_REAL_OUTPUT** — the parser turns the real `CLEAN` output
   into a non-empty result table.
3. **TEST_SCRIPT_RUNS_ON_CLEAN** — no harness-level failure or timeout.
4. **CLEAN_TESTS_PASS** — at least `min_clean_passing` stable passing tests,
   no already-failing test, no collection error.
5. **BUG_CREATES_NEW_FAILURES** — at least `min_fail_to_pass` tests go from
   pass to fail, and not more than `max_fail_to_pass_fraction` of the suite. A
   change that breaks most of the suite is a build break, not a bug.
6. **WEAKENING_HIDES_FAILURE** — the test-side change hides at least one of
   those new failures.
7. **REPO_STAYS_RUNNABLE** — the buggy repository still collects, still runs,
   and still has passing tests.
8. **INVERSE_MUTATION_SUCCEEDS** — reversing the injection restores the
   `CLEAN` result table **exactly**. This is SSR's inverse-mutation criterion,
   and it is the check that catches a diff that only appears to be the whole
   change.

The tests that pass on `CLEAN` and fail on `BUG` are the **oracle**. They are
the only failure evidence a reviewer sees, and the only thing the solver is
asked to fix.

## The solver and second-order bugs

`scripts/run_solver.py` presents the buggy repository plus the failing test
names, the test command and the failing output. It gets no injection diff, no
strategy, no weakening diff, and no generation metadata. It is the same model
as the injector.

Oracle evaluation re-runs the test script over the repaired working tree. A
repair `PASSED` when every oracle test passes and nothing that passed before
broke; otherwise it `FAILED`.

`scripts/build_second_order_bug.py` turns a genuinely failed repair into a
second-order state. The combined diff is taken from the repository after both
stages are applied, not by concatenating patches, so:

* it always applies cleanly to the clean state, and
* a reviewer sees one diff against the clean upstream code and cannot tell
  from its structure that two stages produced it.

The child gets its **own** test-weakening stage rather than inheriting the
parent's: the parent's test edit was written against the parent's failures and
has no reason to hide the child's. The child then goes through the same eight
validation checks as any other candidate.

**Nothing may be tuned to make the solver fail.** `configs/solver.yaml` and
`prompts/solver.md` both say so. If the yield of failed repairs is low, the
low yield is the finding, and `scripts/run_solver.py` reports
`second_order_yield` for exactly that reason.

## Costs

`estimated_cost_usd` in each metadata record comes from OpenRouter's own usage
accounting. Per generation attempt, expect roughly 60 model calls across the
three stages, plus up to 40 for a solver attempt.

## Reproducing an attempt

Every run records: the config SHA-256s, the strategy seed and draw, the model
and its sampling parameters, the protocol version, the environment
fingerprint, and the full trajectory. Given the same environment image and the
same seed, the strategy sequence repeats exactly; the model's replies do not,
because the endpoint is not deterministic at temperature above zero. The
trajectory is therefore the provenance record, not a replay script.
