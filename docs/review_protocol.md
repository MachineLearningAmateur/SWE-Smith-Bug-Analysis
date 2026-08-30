# Blind review protocol

Two reviewers, Codex and Claude, independently classify the same 100 frozen
bug states with the same frozen rubric.

## The question

> What kind of technical failure does this validated buggy repository state
> represent?

That sentence is in every packet, identical. It is the whole task.

Note what it does *not* ask. It does not ask whether a pull request was
rejected, whether a human corrected it, or whether the agent's verification
was honest. Those are AIDev pull-request questions and do not apply to a
validated synthetic bug state, which is why `TECHNICAL_FAILURE_EVIDENCE`,
`NONTECHNICAL_REJECTION`, `human_correction`, `test_issue_alignment` and
`evidence_overstated` are all absent from `schemas/review_result.schema.json`.

## What a reviewer records

```json
{
  "bug_id": "SSR_001",
  "failure_pattern": "incomplete_change_propagation",
  "pattern_confidence": "HIGH",
  "failure_scope": "CODE_STATE",
  "taxonomy_fit": "DIRECT",
  "supporting_evidence_ids": ["BUG_DIFF", "ORACLE_TEST_01"],
  "reasoning_summary": "Short evidence-based justification.",
  "proposed_other_pattern": null
}
```

`failure_pattern` and `failure_scope` come from frozen AIDev taxonomy v1,
unchanged. `taxonomy_fit` is `DIRECT`, `OTHER` or `UNCLEAR`.

**Reviewers assign the fine-grained label only.** The broad family is derived
afterwards, deterministically, by `scripts/apply_frozen_families.py`. Nobody
is ever asked to choose a family. That is what makes the family-level
agreement number mean something.

**Never record private chain-of-thought.** `reasoning_summary` is a short
evidence-based justification, not a transcript.

### `UNASSIGNED` is deliberately absent

In AIDev, `UNASSIGNED` covered pull requests with no technical pattern —
non-technical rejections. Every case here is an execution-validated technical
bug state, so that escape hatch cannot apply. When no defined pattern fits,
use `OTHER_TECHNICAL_PATTERN` with `taxonomy_fit: OTHER` and describe the
pattern in `proposed_other_pattern`. Those cases are the coverage question's
actual answer, so do not force them into a defined label.

### Code-state precedence

The frozen taxonomy adopted this rule at freeze:

> When both a code-state pattern and a verification-process pattern apply,
> assign the code-state pattern as the primary `failure_pattern`.

`vacuous_verification` and `unverified_trial_and_error` are the two
verification-process patterns. Record the verification facet through
`failure_scope` instead. `ssr/validate_review.py` rejects a record that pairs
a process pattern with `failure_scope: BOTH`, because that combination states
that a code-state pattern also applies and was not made primary.

## What is in a packet, and what is not

`data/review_packets/SSR_nnn/` holds:

| File | Evidence ID |
|---|---|
| `packet.json` | the manifest |
| `bug_diff.diff` | `BUG_DIFF` — one diff against the clean upstream repository |
| `context/NN_<file>` | `CODE_CONTEXT_NN` — buggy-state source around the change |
| `oracle/NN.txt` | `ORACLE_TEST_NN` — the real output of one failing test |
| `test_results.txt` | `TEST_RESULTS` — clean-versus-buggy counts and the test command |

A reviewer may cite only the evidence IDs the packet lists;
`scripts/validate_review_output.py` checks that.

A packet carries no generation strategy, no bug order, no parent lineage, no
generator or solver identity, no source allocation, no trajectory and no
weakening diff. Two scans enforce this before a packet is written: a metadata
scan over every generated string and file name, and a body scan over the
evidence files for phrases that cannot occur naturally in source code. Both
are fatal.

### What blinding cannot do

A diff still has a shape. A reviewer may privately guess that a state arose
from a reversal or from a failed repair. The design goal is narrower and
achievable: **no packet field, file name or identifier tells them**, and no
reviewer can confirm a guess. Whether the shape itself carries a signal is an
empirical question, and `scripts/compare_reviews.py` reports agreement by
source so it can be examined afterwards rather than assumed away.

## Directories and boundaries

```
reviews/
├── codex/
│   ├── cases/            one SSR_nnn.json per bug
│   ├── progress.json
│   ├── review_metadata.json
│   ├── review_results.jsonl
│   └── COMPLETE
└── claude/               the same, for Claude
```

Codex writes only `reviews/codex/**`. Claude writes only
`reviews/claude/**`. `ssr.review_workflow.assert_write_boundary` refuses any
write outside a reviewer's own directory, so the rule in `AGENTS.md` and
`CLAUDE.md` has teeth.

Neither reviewer may read the other's directory, or `data/sampling/`, or any
`metadata.json`, `trajectory.jsonl`, `solver_result.json` or `pred_patch.diff`
in the pool. Use fresh review sessions where practical.

## Working through the 100

1. Read `taxonomy/frozen_failure_taxonomy_v1.md`. All of it, once, first.
2. Take the next case from `progress.json` (`next_bug_id`).
3. Read only `data/review_packets/<id>/`.
4. Save the record immediately with one file per bug. Never batch: a session
   that dies mid-run must lose one case, not fifty.
5. Validate as you go:
   `python scripts/validate_review_output.py --reviewer <you> --case SSR_007`

When all 100 exist and validate:

```bash
python scripts/validate_review_output.py --reviewer <you> --finalise
```

That builds `review_results.jsonl`, marks progress `COMPLETE` and writes the
`COMPLETE` marker. It refuses if any case is missing or invalid, or if the
snapshot manifest hash has changed since the review started.

## After both reviewers finish

Comparison is **locked** until both `COMPLETE` markers exist.
`ssr.review_workflow.require_both_complete` enforces it, and both analysis
scripts call it first.

```bash
python scripts/apply_frozen_families.py   # families, agreement, kappa
python scripts/compare_reviews.py          # source-specific, then pooled
```

`apply_frozen_families.py` applies the frozen mapping to both reviewers'
original fine-grained labels and computes fine-label agreement and Cohen's
kappa, family agreement and kappa, and scope agreement. Fine-grained labels
are preserved beside the derived family column in every output; families never
replace them. The original review outputs are never rewritten.

`compare_reviews.py` joins the sealed reviews to the hidden crosswalk — the
first point in the study where a bug's source and its label are allowed to
meet — and reports REMOVAL, HISTORY_REVERSION and SECOND_ORDER separately
before anything pooled. Every pooled number carries the stratification caveat.

## Reading the numbers honestly

* The 100 cases are a deliberate 30/30/40 allocation. Pooled proportions are
  **not** the natural distribution of published SSR.
* The AIDev family mapping was derived on the AIDev disagreements, so AIDev's
  73.5% family agreement is an in-sample estimate. The number computed here is
  out-of-sample for this population. They are not the same quantity and
  should not be presented as a before-and-after.
* A high rate of `OTHER_TECHNICAL_PATTERN` or `taxonomy_fit: UNCLEAR` is a
  finding about taxonomy coverage, not a reviewer failure. Report it as such.
