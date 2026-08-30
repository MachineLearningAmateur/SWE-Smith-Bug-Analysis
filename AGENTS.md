# AGENTS.md — instructions for Codex

You are one of two independent blind reviewers in this study. Claude is the
other. Your job is to classify 100 validated buggy repository states using a
frozen taxonomy, without ever learning how any of them were made and without
ever seeing Claude's answers.

Everything below is a rule, not a suggestion. Several of them are enforced by
code, and the code will stop you rather than let you break one quietly.

## Your task

For each of the 100 packets, answer one question:

> What kind of technical failure does this validated buggy repository state
> represent?

## Before you start

Read `taxonomy/frozen_failure_taxonomy_v1.md` in full, once. It defines every
fine-grained label and the decision rules. Then read `docs/review_protocol.md`.

## What you may read

* `taxonomy/frozen_failure_taxonomy_v1.md`
* `docs/review_protocol.md`
* `data/review_manifest.csv`
* `data/review_packets/SSR_nnn/` — the packet for the case you are on
* `reviews/codex/**` — your own directory
* `schemas/review_result.schema.json`

## What you must NOT read

* `reviews/claude/**` — Claude's work. Not before, not during, not after,
  until both `COMPLETE` markers exist.
* `data/sampling/**` — the crosswalk there reveals each bug's source and
  order.
* Any `metadata.json`, `trajectory.jsonl`, `solver_trajectory.jsonl`,
  `solver_result.json` or `pred_patch.diff` under `data/validated_pool/` or
  `data/generated_pool/`. That is hidden generation metadata.
* `analysis/**`.

If you find yourself wanting to know how a bug was made, that is the feeling
the protocol exists to defeat. Classify what is in front of you.

## What you may write

**Only `reviews/codex/**`.** Nothing else, ever. Not a config, not a doc, not
a script, not a fix to code you think is wrong.
`ssr.review_workflow.assert_write_boundary` refuses any write outside your
directory, so an accidental attempt fails rather than lands.

If you believe something outside your directory is broken, stop and say so.
Do not fix it.

## How to record a case

One JSON file per bug, at `reviews/codex/cases/SSR_nnn.json`:

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
4. **Cite only evidence IDs listed in that packet.** The validator checks.
5. **No private chain-of-thought.** `reasoning_summary` is a short
   evidence-based justification, not a transcript of your reasoning.
6. **Save immediately, one file at a time.** Never batch. A session that dies
   mid-run must lose one case, not fifty.

## Working loop

```bash
# where you are, and what is next
python scripts/validate_review_output.py --reviewer codex

# after each case
python scripts/validate_review_output.py --reviewer codex --case SSR_007

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
