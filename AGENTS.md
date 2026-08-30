# AGENTS.md — instructions for Codex

You are one of two independent blind reviewers in this study. Claude is the
other. Your job is to classify 100 validated synthetic buggy repository states using a
frozen taxonomy, without ever learning how any of them were made and without
ever seeing Claude's answers.

Everything below is a rule, not a suggestion. Several of them are enforced by
code, and the code will stop you rather than let you break one quietly.

## Start here

You need Python 3.10 or later and nothing else. No Docker, no API key, no
network: this task reads frozen files and writes JSON. It works the same on
macOS, Linux and Windows.

```bash
python -m pip install -r requirements-review.txt
python scripts/check_review_ready.py --reviewer codex
```

That check verifies the frozen taxonomy, re-hashes every packet against the
hash it was frozen with, tells you whether the corpus is RESEARCH or a
REHEARSAL, and names the next case. Do not start until it passes.

If it reports **REHEARSAL**, this corpus is a workflow test. Do the review the
same way, but say so in your final message: its numbers are not results.

## Your task

For each of the 100 packets, answer one question:

> Based only on the frozen evidence in this packet, what kind of technical
> failure does this synthetic buggy repository state represent?

You are classifying **the synthetic bug itself**. You are not grading a repair
attempt, an agent's reasoning, the quality of the issue text, or whether the
task is easy or hard. None of that is in front of you.

## Before you start

Read `taxonomy/frozen_failure_taxonomy_v1.md` in full, once. It defines every
fine-grained label and the decision rules. Then read `docs/review_protocol.md`.

## What you may read

* `taxonomy/frozen_failure_taxonomy_v1.md`
* `docs/review_protocol.md`
* `data/review_manifest.csv`
* `data/review_packets/SWESMITH_nnn/` — the packet for the case you are on
* `reviews/codex/**` — your own directory
* `schemas/review_result.schema.json`

## What you must NOT read

* `reviews/claude/**` — Claude's work. Not before, not during, not after,
  until both `COMPLETE` markers exist.
* `data/hidden/**` — the sample metadata there names each task's generation
  method and the instance it came from.
* `data/population/**` — the population manifest, which carries the same.
* `analysis/**` — population frequencies and the AIDev comparison.
* `archive/**` — a paused, unrelated line of work.

If you find yourself wanting to know how a bug was made, that is the feeling
the protocol exists to defeat. Classify what is in front of you.

## What you may write

**Only `reviews/codex/**`.** Nothing else, ever. Not a config, not a doc, not
a script, not a fix to code you think is wrong.
`ssr.review_workflow.assert_write_boundary` refuses any write outside your
directory, so an accidental attempt fails rather than lands.

If you believe something outside your directory is broken, stop and say so.
Do not fix it.

## The labels, quoted from the frozen taxonomy

These are the definitions from `taxonomy/frozen_failure_taxonomy_v1.md`,
reproduced verbatim so you do not have to hold two files open. Read that
file in full once anyway: it carries the decision rules and the family
mapping that these definitions sit inside.

The definitions were written for pull-request patches, so they say "the
patch" and "the agent". Read them against the buggy state in front of you:
the diff IS the change being judged, and "the agent" is whoever made it.

| Label | Definition (frozen rubric) |
|---|---|
| `false_premise_about_existing_code` | The patch relies on an incorrect assumption about repository behavior, APIs, types, language semantics, data contracts, or architecture. |
| `misdiagnosed_root_cause` | The agent identifies the wrong underlying cause and therefore changes the wrong component or logic. |
| `masked_symptom_instead_of_fixing` | The patch suppresses, bypasses, or hides the observed symptom without correcting the underlying defect. |
| `incomplete_change_propagation` | A change is made in one place but not propagated to other required callers, representations, files, branches, schemas, platforms, or related code paths. |
| `broke_existing_contract_or_behavior` | The proposed fix violates or regresses behavior that the repository already promises or relies on. |
| `violated_project_constraint_or_convention` | The implementation conflicts with a documented or established repository-specific constraint, invariant, architectural rule, compatibility target, or required convention in a technically meaningful way. |
| `disproportionate_or_duplicative_solution` | The patch adds unnecessary, duplicated, or overly broad implementation relative to the defect, and that excess causes or constitutes the technical problem. |
| `wrong_baseline_or_branch` | The implementation targets the wrong repository state, branch, version, or baseline, making the fix inappropriate. |
| `vacuous_verification` | The agent's claimed verification does not test the behavior needed to establish the fix. |
| `unverified_trial_and_error` | The chronology shows repeated speculative implementation changes without validation of the underlying hypothesis. |
| `OTHER_TECHNICAL_PATTERN` | Concrete technical failure exists but no defined pattern fits (described in `proposed_other_pattern`). |

`UNASSIGNED` is in the AIDev rubric and is **not** available here. It covered
pull requests with no technical pattern. Every case in this study is an
execution-validated technical bug state, so it cannot apply.

### `failure_scope`

| Value | Use it when |
|---|---|
| `CODE_STATE` | The defect is a property of the code as it now stands. This is the usual answer here. |
| `REPAIR_PROCESS` | The defect is in how the change was arrived at, not in the resulting code. |
| `BOTH` | The code state is defective AND the way it was reached is too. Use this to record a verification problem beside a code-state pattern. |
| `UNKNOWN` | You cannot tell. Should be rare: every case here is execution-validated. |

### `taxonomy_fit`

| Value | Meaning |
|---|---|
| `DIRECT` | A defined pattern fits this case. |
| `OTHER` | No defined pattern fits. Requires `failure_pattern: OTHER_TECHNICAL_PATTERN` and a described `proposed_other_pattern`. |
| `UNCLEAR` | The evidence does not settle it. Pair with `pattern_confidence: LOW` or `MEDIUM`. |

### `pattern_confidence`

`HIGH`, `MEDIUM` or `LOW`. Descriptive only: it is not an inclusion
criterion and does not affect any statistic. Report what you actually think.

## What is in a packet

`data/review_packets/SWESMITH_nnn/` holds these, and nothing else:

| File | Evidence ID | What it is |
|---|---|---|
| `packet.json` | — | the manifest: repository, language, and every evidence ID you may cite |
| `bug_diff.diff` | `BUG_DIFF` | the change that INTRODUCED the defect, applied to working code |
| `context/NN_<file>` | `CODE_CONTEXT_NN` | the touched files as they stand in the buggy state |
| `specification.md` | `SPECIFICATION` | the issue text supplied with the task |
| `test_evidence.md` | `TEST_FAILURE_NN` | tests that pass on the working state and fail on this one |
| `reference_repair.diff` | `REFERENCE_REPAIR` | the reverse of the bug diff: it restores the working code |

Three things about this evidence are worth stating plainly.

**`BUG_DIFF` is the bug, not a repair.** It is the diff that broke the code.
`REFERENCE_REPAIR` is its exact reverse. Reading them the wrong way round
inverts every judgement you make.

**`SPECIFICATION` is a description, not evidence.** It was generated to
describe the defect, and it can be inaccurate or incomplete. Where it disagrees
with `BUG_DIFF`, the diff wins.

**The failing test files are not in the packet.** They were removed when the
task was built, so the defect must be judged from the code, not from reading
the assertions.

Cite only IDs that appear in that packet's `evidence_ids`. The validator checks
every one, so a typo fails fast rather than surviving into the data.

## A worked case

`BUG_DIFF` removes an upper-bound check from a clamp function.
`TEST_FAILURE_01` names a test that passed before and fails now.
`REFERENCE_REPAIR` puts the check back. Nothing else changed to compensate.

```json
{
  "case_id": "SWESMITH_001",
  "failure_pattern": "broke_existing_contract_or_behavior",
  "pattern_confidence": "HIGH",
  "failure_scope": "CODE_STATE",
  "taxonomy_fit": "DIRECT",
  "supporting_evidence_ids": ["BUG_DIFF", "TEST_FAILURE_01"],
  "reasoning_summary": "BUG_DIFF drops the upper-bound branch of clamp; TEST_FAILURE_01 covers exactly that bound, so behaviour the suite already promised is gone.",
  "proposed_other_pattern": null
}
```

Note what the summary does: it names the evidence, says what the code now does,
and stops. It is not a transcript of your reasoning.

## How to record a case

One JSON file per case, at `reviews/codex/cases/SWESMITH_nnn.json`:

```json
{
  "case_id": "SWESMITH_001",
  "failure_pattern": "incomplete_change_propagation",
  "pattern_confidence": "HIGH",
  "failure_scope": "CODE_STATE",
  "taxonomy_fit": "DIRECT",
  "supporting_evidence_ids": ["BUG_DIFF", "TEST_FAILURE_01"],
  "reasoning_summary": "Short evidence-based justification.",
  "proposed_other_pattern": null
}
```

Rules for the record:

1. **Assign the fine-grained label only.** Never a family. Families are
   derived deterministically afterwards by script. If you pick a family
   yourself, the agreement statistic it feeds becomes meaningless.
2. **Apply code-state precedence.** When both a code-state pattern and a
   verification-process pattern (`vacuous_verification`,
   `unverified_trial_and_error`) apply, the code-state pattern is the primary
   `failure_pattern`. Record the verification facet through `failure_scope`.
   A process pattern with `failure_scope: BOTH` is rejected by the validator.
3. **`UNASSIGNED` does not exist here.** Every case is an execution-validated
   technical bug state. When no defined pattern fits, use
   `OTHER_TECHNICAL_PATTERN` with `taxonomy_fit: OTHER` and describe it in
   `proposed_other_pattern`. Do not force a poor fit into a defined label:
   those cases are the coverage question's actual answer.
4. **Two labels will rarely fit here.** `vacuous_verification` and
   `unverified_trial_and_error` describe a repair *process*. A static
   synthetic bug shows you no repair process at all. Do not invent one, and do
   not treat the system that generated the bug as though it were an agent
   attempting a fix. If the evidence does not show it, it is not there.
5. **Cite only evidence IDs listed in that packet.** The validator checks.
6. **No private chain-of-thought.** `reasoning_summary` is a short
   evidence-based justification, not a transcript of your reasoning.
7. **Save immediately, one file at a time.** Never batch. A session that dies
   mid-run must lose one case, not fifty.

## Working loop

```bash
# where you are, and what is next
python scripts/validate_review_output.py --reviewer codex

# after each case
python scripts/validate_review_output.py --reviewer codex --case SWESMITH_007

# when all 100 exist
python scripts/validate_review_output.py --reviewer codex --finalise
```

`--finalise` builds `review_results.jsonl`, marks progress `COMPLETE` and
writes the `COMPLETE` marker. It refuses if a case is missing or invalid, or
if the evidence snapshot changed since you started.

## Do not modify shared files

Not `configs/`, not `schemas/`, not `taxonomy/`, not `data/`, not `scripts/`,
not `ssr/`. The taxonomy in particular is frozen: it must not change on the
basis of what these bugs look like. `ssr.taxonomy.verify_provenance` re-hashes
it on every analysis run and will fail loudly if it has moved.

## When you are done

Stop. Do not compare yourself with Claude, do not open `analysis/`, and do not
run the comparison scripts. Those run after both `COMPLETE` markers exist, and
they are locked until then.
