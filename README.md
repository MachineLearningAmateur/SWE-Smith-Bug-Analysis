# SWE-smith / AIDev coverage study

> **To what extent do SWE-smith synthetic repair tasks used to train
> SWE-agent-LM-32B cover technical code-state failure patterns observed in real
> coding-agent pull requests?**

The real-agent comparison corpus is the frozen AIDev corpus in
[`MachineLearningAmateur/AIBugAnalysis`](https://github.com/MachineLearningAmateur/AIBugAnalysis).
This repository audits the other side: the official SWE-smith task instances
that actually produced the training trajectories for
[SWE-agent-LM-32B](https://huggingface.co/SWE-bench/SWE-agent-LM-32B), classified
under the **same** frozen taxonomy by two independent blind reviewers.

**Reviewing the cases?** Go to
[Running the blind reviews](#running-the-blind-reviews). You need Python 3.10+
and nothing else: no Docker, no API key, no network.

**Running the study?** Start with
[`docs/research_scope.md`](docs/research_scope.md).

## Status

The 100-case sample is **selected, frozen and packet-built**. Neither review
has started.

| | |
|---|---:|
| Population: unique tasks behind the training trajectories | 4,207 |
| Sample | 100 |
| Unique repositories in the sample | 52 |
| Largest deviation from population method share | 0.45% |
| Reconstruction failures | 0 |

```
review_manifest.csv             64e607800de2a08e4321b371d616841bbd4fbe6deaddb1321dfd355333caebfa
review_snapshot_manifest.json   981694c07ffcc9ee9bcf00527d71a0c94b15884ebfc7d8aa537363b3f646a6de
frozen_failure_taxonomy_v1.md   ecf76f0d752afd2632d4a2825b648a36cce4c16926782aec18fd4e2637fe4cc7
pattern_families.yaml           1ce7232047437f87e7116d84b369e4f820e854481cbc744faf3b1d4c1af60985
```

Run `python scripts/check_review_ready.py` to re-verify all of it locally.

## The population

The population is **not** the full 50k SWE-smith corpus. It is the unique task
instances behind the official training trajectories, read at pinned revisions:

| Dataset | Revision | Why pinned |
|---|---|---|
| `SWE-bench/SWE-smith-trajectories` | `f6b6d7e01f2b` | last revision before the July 2025 expansion, which added three splits totalling 76k rows that are **not** the training set |
| `SWE-bench/SWE-smith` | `9f2a10465194` | the 2025-04-29 upload; it still carries `base_commit` and `created_at`, which current `main` dropped |

```
5017  trajectories claimed by the dataset card
5016  trajectory rows actually shipped      <- reported, not reconciled
4211  unique task instances
4207  resolvable in the pinned task dataset <- 4 excluded, all pallets/flask
```

By generation method: `lm_rewrite` 36.3%, mirrored pull requests 27.6%,
procedural mutations 34.2%, combined 1.9%. All Python.
Full profile: [`analysis/population_profile.md`](analysis/population_profile.md).

## Two findings that would have inverted this study

Both were established by reconstruction, not assumption. Both are enforced in
code and locked by tests, because either one taken the SWE-bench way round
produces a corpus that looks fine and means the opposite.

**`patch` is the BUG, not the gold repair.** In SWE-bench, `patch` is the fix.
In SWE-smith it is the diff that *introduces* the defect: it is byte-equal to
the branch's own `Bug Patch` commit, applies to that commit's parent, and does
not apply to the buggy state. The reference repair is its **reverse**; there is
no separate field.

**`base_commit` is NOT the clean state.** Its tree differs from the bug's actual
parent on every instance checked, and the bug diff does not apply to it. The
clean state is the parent of the `Bug Patch` commit.

Evidence and citations:
[`docs/swesmith_field_semantics.md`](docs/swesmith_field_semantics.md).

## Install

A reviewer needs two packages and no more:

```bash
python -m pip install -r requirements-review.txt
python scripts/check_review_ready.py --reviewer claude   # or codex
```

Running the study needs the full set:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q
```

Everything works the same on macOS, Linux and Windows.

## The pipeline

```bash
# 1. build the population from the pinned official releases
python scripts/build_training_population.py

# 2. verify what each dataset field means, by reconstruction
python scripts/verify_swesmith_semantics.py --n 5

# 3. select 100 and freeze their packets
python scripts/build_swesmith_packets.py

# 4. two independent blind reviews  -- see below

# 5. analysis, locked until both COMPLETE markers exist
python scripts/apply_frozen_families.py
python scripts/compare_reviews.py
```

Selection and packet building are one command because they are coupled: a task
that cannot be reconstructed must not be replaced by hand. It goes on an
exclusion list and the deterministic sampler runs again with the same seed.

## Running the blind reviews

The sample and the packets are **already selected and frozen**. Do not
regenerate the sample, modify the taxonomy, rebuild packets, or change any
sampling parameter before or during a review. `scripts/check_review_ready.py`
re-hashes every packet and refuses to proceed if anything moved.

Run each review in a **fresh session**, on its **own branch**, cut from the
same frozen pre-review commit. Two branches keep the reviewers from seeing
each other's work in the working tree, and make the independence auditable
afterwards from the history alone.

### Set up the two branches

```bash
git clone git@github.com:MachineLearningAmateur/SWE-Smith-Bug-Analysis.git swesmith-review
cd swesmith-review

# Both branches start from the same frozen pre-review commit, which is
# tagged. Use the tag, not a commit hash: the tag is what stays correct.
git fetch --tags
git checkout -b codex-review  pre-review-frozen
git checkout -b claude-review pre-review-frozen

python -m pip install -r requirements-review.txt
```

`pre-review-frozen` marks the state in which the 100 packets were frozen and
the review tooling was last verified. `scripts/check_review_ready.py` re-hashes
every packet against it, so a reviewer who starts from the wrong commit finds
out immediately rather than half way through.

Then open **one fresh session per reviewer**, each with its own branch checked
out. Never run both reviewers in one session.

| Reviewer | Branch | Writes | Format |
|---|---|---|---|
| Codex | `codex-review` | `reviews/codex/cases/SWESMITH_nnn.json` | JSON |
| Claude | `claude-review` | `reviews/claude/cases/SWESMITH_nnn.yaml` | YAML |

The two formats are deliberate. The records are semantically identical and
validate against the same schema; different bytes make each reviewer's output
obviously its own and discourage copy-paste between them.

### The prompt for Codex

Check out `codex-review`, start a fresh Codex session, and paste this:

```text
You are the independent blind reviewer for this study. Read AGENTS.md in full
before anything else, then read taxonomy/frozen_failure_taxonomy_v1.md in
full. Both are in this repository root. They are your complete brief; follow
them exactly.

First, run:

    python -m pip install -r requirements-review.txt
    python scripts/check_review_ready.py --reviewer codex

Do not start until that check passes. It re-hashes every packet against the
frozen manifest; if it reports a mismatch, stop and say so rather than
continuing.

Then work through all 100 cases, in order:

1. Read ONLY data/review_packets/<case id>/ for that case: packet.json,
   bug_diff.diff, everything under context/, specification.md,
   test_evidence.md and reference_repair.diff.
2. Decide what kind of technical failure that synthetic buggy code state
   represents, using the fine-grained labels from the frozen taxonomy.
3. Write reviews/codex/cases/<case id>.json immediately, as JSON, before
   moving on. One file per case. Never batch, never hold results in memory.
4. Run:
       python scripts/validate_review_output.py --reviewer codex --case <case id>
   Fix anything it rejects before continuing.

Rules that matter most, all of them in your brief:
- BUG_DIFF is the bug, not a repair. REFERENCE_REPAIR is its exact reverse.
  Reading them the wrong way round inverts every judgement.
- SPECIFICATION is a generated description and can be wrong. Where it
  disagrees with BUG_DIFF, the diff wins.
- Assign the fine-grained label only. Never a family: families are derived by
  script afterwards.
- Apply code-state precedence. If a code-state pattern and a
  verification-process pattern both apply, the code-state pattern is the
  primary failure_pattern and the verification facet goes in failure_scope.
- vacuous_verification and unverified_trial_and_error describe a repair
  process. A static synthetic bug shows you none. Do not invent one, and do
  not treat the bug generator as an agent attempting a fix.
- UNASSIGNED does not exist here. If no defined pattern fits, use
  OTHER_TECHNICAL_PATTERN with taxonomy_fit OTHER and describe it in
  proposed_other_pattern. Do not force a poor fit: those cases are the answer
  to the question this study asks.
- Cite only evidence IDs listed in that packet.
- reasoning_summary is a short evidence-based justification, not a transcript
  of your reasoning.

Never read: reviews/claude/, data/hidden/, data/population/, analysis/, or
anything under archive/. If you find yourself wanting to know how a bug was
made, that is exactly what this protocol exists to prevent.

Write nothing outside reviews/codex/. If you believe something else in the
repository is broken, stop and tell me rather than fixing it.

When all 100 exist and validate, run:

    python scripts/validate_review_output.py --reviewer codex --finalise

Then report: how many cases you recorded, the distribution of labels you
assigned, how many you marked OTHER_TECHNICAL_PATTERN or UNCLEAR, and anything
about the taxonomy that fitted badly. Do not compare yourself with the other
reviewer and do not run the analysis scripts.
```

### The prompt for Claude

Check out `claude-review`, start a fresh Claude Code session, and paste this:

```text
You are the independent blind reviewer for this study. Read CLAUDE.md in full
before anything else, then read taxonomy/frozen_failure_taxonomy_v1.md in
full. Both are in this repository root. They are your complete brief; follow
them exactly.

First, run:

    python -m pip install -r requirements-review.txt
    python scripts/check_review_ready.py --reviewer claude

Do not start until that check passes. It re-hashes every packet against the
frozen manifest; if it reports a mismatch, stop and say so rather than
continuing.

Then work through all 100 cases, in order:

1. Read ONLY data/review_packets/<case id>/ for that case: packet.json,
   bug_diff.diff, everything under context/, specification.md,
   test_evidence.md and reference_repair.diff.
2. Decide what kind of technical failure that synthetic buggy code state
   represents, using the fine-grained labels from the frozen taxonomy.
3. Write reviews/claude/cases/<case id>.yaml immediately, as YAML, before
   moving on. One file per case. Never batch, never hold results in memory.
4. Run:
       python scripts/validate_review_output.py --reviewer claude --case <case id>
   Fix anything it rejects before continuing.

Rules that matter most, all of them in your brief:
- BUG_DIFF is the bug, not a repair. REFERENCE_REPAIR is its exact reverse.
  Reading them the wrong way round inverts every judgement.
- SPECIFICATION is a generated description and can be wrong. Where it
  disagrees with BUG_DIFF, the diff wins.
- Assign the fine-grained label only. Never a family: families are derived by
  script afterwards.
- Apply code-state precedence. If a code-state pattern and a
  verification-process pattern both apply, the code-state pattern is the
  primary failure_pattern and the verification facet goes in failure_scope.
- vacuous_verification and unverified_trial_and_error describe a repair
  process. A static synthetic bug shows you none. Do not invent one, and do
  not treat the bug generator as an agent attempting a fix.
- UNASSIGNED does not exist here. If no defined pattern fits, use
  OTHER_TECHNICAL_PATTERN with taxonomy_fit OTHER and describe it in
  proposed_other_pattern. Do not force a poor fit: those cases are the answer
  to the question this study asks.
- Cite only evidence IDs listed in that packet.
- reasoning_summary is a short evidence-based justification, not a transcript
  of your reasoning.

Never read: reviews/codex/, data/hidden/, data/population/, analysis/, or
anything under archive/. If you find yourself wanting to know how a bug was
made, that is exactly what this protocol exists to prevent.

Write nothing outside reviews/claude/. If you believe something else in the
repository is broken, stop and tell me rather than fixing it.

When all 100 exist and validate, run:

    python scripts/validate_review_output.py --reviewer claude --finalise

Then report: how many cases you recorded, the distribution of labels you
assigned, how many you marked OTHER_TECHNICAL_PATTERN or UNCLEAR, and anything
about the taxonomy that fitted badly. Do not compare yourself with the other
reviewer and do not run the analysis scripts.
```

### Stronger isolation, if you want it

Branches keep the two reviewers apart in one clone. A **bundle** goes further
and leaves the hidden material out of what a reviewer receives at all:

```bash
python scripts/make_review_bundle.py --reviewer codex --out ../codex_review --zip
```

The export re-hashes every packet inside the bundle and refuses to publish one
containing excluded material. When the review comes back:

```bash
python scripts/import_review_results.py --reviewer codex --from ../codex_review
```

The import refuses a review done against different evidence or a different
taxonomy version, so a stale bundle cannot be merged by accident.

### After both reviews finish

Merge the two branches, then run the analysis. It is locked until both
`COMPLETE` markers exist.

```bash
git checkout main
git merge codex-review claude-review     # they touch disjoint directories
python scripts/apply_frozen_families.py
python scripts/compare_reviews.py
```

`apply_frozen_families.py` applies the frozen mapping to both reviewers'
original fine-grained labels; the labels themselves are never overwritten.
`compare_reviews.py` joins the sealed reviews to the hidden sample metadata,
which is the first point in the study where a bug's generation method and its
taxonomy label are allowed to meet.

## Layout

```
taxonomy/     the frozen AIDev taxonomy, imported verbatim, with provenance
configs/      sampling parameters and the per-reviewer serialisation map
schemas/      review packet and review result
ssr/          the library: SWE-smith access, sampling, reconstruction,
              packets, review workflow and formats, taxonomy
scripts/      one command-line entry point per pipeline step
data/         population, review packets, manifests, hidden sample metadata
reviews/      codex/ and claude/, one directory each, strictly separated
analysis/     population profile, sample balance, language confound plan
archive/      the paused SSR generation path, intact and inactive
tests/        the suite, including the semantic locks described above
```

## The isolation rules

Each is enforced by code, not convention.

| Rule | Enforced by |
|---|---|
| Sampling never reads a taxonomy label. | `ssr.swesmith_sampling.assert_neutral` |
| A packet carries no generation method, trajectory, model, attempt count, frequency, mirror name or instance ID. | a leakage scan over the literals identifying each task, in `ssr/packets.py` |
| The clean state is the bug commit's parent, never `base_commit`. | `ssr/packets.py`, locked by `tests/test_swesmith_packets.py` |
| A reviewer writes only inside its own directory. | `ssr.review_workflow.assert_write_boundary` |
| The comparison is locked until both reviews finish. | `ssr.review_workflow.require_both_complete` |

No classifier is run over the population before selection, so the sample cannot
become indirectly taxonomy-aware.

## The language confound, stated up front

The SWE-smith training population is **100% Python**. The strict AIDev corpus is
34.3% TypeScript, 14.3% Go and **11.4% Python** — four cases, all of which carry
the same broad family.

Any coverage difference between the corpora is therefore confounded with
language, and the Python-matched sensitivity analysis cannot resolve it at
n = 4. [`analysis/language_confound_plan.md`](analysis/language_confound_plan.md)
says so, and says what will be reported instead.

## What this population is, and is not

These are SWE-smith tasks that **yielded a trajectory good enough to be used for
fine-tuning**. They are a selected set of successful rollouts, not the full
SWE-smith generation distribution. That is exactly right for a question about
training-data coverage, and exactly wrong as a claim about SWE-smith in general.
[`docs/limitations.md`](docs/limitations.md) carries this and eight more.

## Documentation

| Document | Covers |
|---|---|
| [`QUICKSTART.md`](QUICKSTART.md) | cloning and running a review on any machine |
| [`docs/swesmith_field_semantics.md`](docs/swesmith_field_semantics.md) | what every field means, and the evidence for it |
| [`docs/review_protocol.md`](docs/review_protocol.md) | the reviewer's task, the record format, the boundaries |
| [`docs/limitations.md`](docs/limitations.md) | every way this study is bounded |
| [`analysis/population_profile.md`](analysis/population_profile.md) | the population, by method, repository and shape |
| [`analysis/sample_balance.md`](analysis/sample_balance.md) | population versus sample, and every distortion |
| [`analysis/language_confound_plan.md`](analysis/language_confound_plan.md) | how the language confound will be handled |

Reviewers read [`AGENTS.md`](AGENTS.md) (Codex) or [`CLAUDE.md`](CLAUDE.md)
(Claude) and nothing else about the pipeline.

## The paused SSR path

An earlier design generated SSR-style bugs with an OpenRouter model. It worked
end to end and is preserved intact under
[`archive/ssr_future/`](archive/ssr_future/), marked inactive. No bug generated
by it may enter this study's sample.

## Tests

```bash
python -m pytest tests -q
```

The suite covers the frozen taxonomy, the two SWE-smith semantics above,
generation-method parsing, packet leakage, deterministic sampling, the review
formats, the reviewer boundaries, and that the 100 frozen packets still match
their recorded hashes.
