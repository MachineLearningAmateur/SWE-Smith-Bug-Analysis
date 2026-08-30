# SSR / SWE-smith coverage study

The SSR side of RQ1: does the frozen AIDev failure taxonomy cover the failures
that an SSR-style bug pipeline produces?

The AIDev side is already frozen in
[`MachineLearningAmateur/AIBugAnalysis`](https://github.com/MachineLearningAmateur/AIBugAnalysis).
This repository builds a comparable SSR-style corpus over SWE-smith
environments, freezes 100 neutral evidence packets, and has Codex and Claude
classify them independently under the **same** frozen taxonomy.

**Reviewing the bugs?** Go straight to [`QUICKSTART.md`](QUICKSTART.md).
You need Python 3.10+ and nothing else: no Docker, no API key, no network.

**Running the study?** Start with
[`docs/research_scope.md`](docs/research_scope.md).

## Status

The pipeline is built and proven end to end. Two things block a corpus run,
both outside this repository:

| Blocker | What is needed |
|---|---|
| **Docker is not installed** | Administrator rights. SWE-smith ships its environments as Docker images; without it there is no SWE-smith environment. See [`docs/swesmith_setup.md`](docs/swesmith_setup.md). |
| **The configured model is blocked for this account** | `qwen/qwen-2.5-coder-32b-instruct` is served on OpenRouter by one provider that this account's privacy setting excludes. Permit it at <https://openrouter.ai/settings/privacy>, or substitute a model and record it in [`docs/fidelity_limitations.md`](docs/fidelity_limitations.md). |

Run `python scripts/check_environment.py` for the current state of this
machine.

What is already done and verified:

* the frozen taxonomy is imported byte for byte, and its family-mapping
  SHA-256 matches the handoff exactly;
* the neutral AIDev environment profile is built — and shows a language
  mismatch that cannot be fixed (see below);
* generation, validation, solving and second-order construction run end to end
  against a local repository;
* deduplication, selection, packet building, the dual-review workflow, family
  derivation and the source-specific comparison run end to end at full
  100-bug scale.

## Install

A reviewer needs two packages and no more:

```bash
python -m pip install -r requirements-review.txt
python scripts/check_review_ready.py --reviewer claude   # or codex
```

Running the study needs the full set:

```bash
python -m pip install -e ".[dev]"
python scripts/selftest.py            # proves the pipeline here, offline
python scripts/check_environment.py   # says what a corpus run still needs
```

Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`. The key is
never written to any artifact and is stripped from every sandbox process, so
an injector with shell access cannot read it.

Everything works the same on macOS, Linux and Windows. `scripts/selftest.py`
runs the whole downstream pipeline against a temporary directory and touches
nothing under `data/`, `reviews/` or `analysis/`; run it after cloning and
after changing anything under `ssr/` or `scripts/`.

## The pipeline

```bash
# 1. environment profile from the AIDev corpus (neutral facts only)
python scripts/profile_aidev_environment_mix.py --aidev-repo /path/to/AIBugAnalysis

# 2. generate and validate first-order bugs
python scripts/generate_bug.py  --env <name> --attempts 20
python scripts/validate_bug.py  --env <name> --all

# 3. solve, and build second-order states from genuine failures
python scripts/run_solver.py             --env <name> --all
python scripts/build_second_order_bug.py --env <name> --all
python scripts/validate_bug.py           --env <name> --all

# 4. deduplicate, then select exactly 100
python scripts/deduplicate_bug_pool.py
python scripts/select_review_sample.py --dry-run
python scripts/select_review_sample.py

# 5. freeze the neutral review packets
python scripts/build_review_packets.py --env <name>

# 6. two independent blind reviews (see AGENTS.md and CLAUDE.md)
python scripts/check_review_ready.py --reviewer codex
python scripts/validate_review_output.py --reviewer codex  --finalise
python scripts/validate_review_output.py --reviewer claude --finalise

#    or hand each reviewer a bundle that physically excludes hidden data
python scripts/make_review_bundle.py --reviewer codex --out ../codex_review --zip
python scripts/import_review_results.py --reviewer codex --from ../codex_review

# 7. analysis, locked until both COMPLETE markers exist
python scripts/apply_frozen_families.py
python scripts/compare_reviews.py
python scripts/compute_patch_metrics.py --env <name>
```

## The prompt to hand the reviewer

Open the checkout (or the bundle) with Claude Code or the Codex CLI and paste
this. Both agents read their brief from the repository root on their own:
Claude Code reads `CLAUDE.md`, Codex reads `AGENTS.md`. The prompt only has to
start them and set the standard.

Replace `<claude|codex>` with whichever one you are running.

```text
You are the independent blind reviewer for this study. Read CLAUDE.md (if you
are Claude) or AGENTS.md (if you are Codex) in full before anything else, then
read taxonomy/frozen_failure_taxonomy_v1.md in full. Both are in this
repository root. They are your complete brief; follow them exactly.

First, run:

    python -m pip install -r requirements-review.txt
    python scripts/check_review_ready.py --reviewer <claude|codex>

Do not start until that check passes. If it reports the corpus as REHEARSAL,
carry on the same way but say so in your final message.

Then work through every case, in the order the check gives you:

1. Read ONLY data/review_packets/<the case id>/ for that case. Read the
   packet.json, the bug_diff.diff, every file under context/ and oracle/, and
   test_results.txt.
2. Decide what kind of technical failure that buggy repository state
   represents, using the fine-grained labels from the frozen taxonomy.
3. Write reviews/<claude|codex>/cases/<the case id>.json immediately, before
   moving on. One file per case. Never batch, never hold results in memory.
4. Run:
       python scripts/validate_review_output.py --reviewer <claude|codex> --case <the case id>
   Fix anything it rejects before continuing.

Rules that matter most, all of them in your brief:
- Assign the fine-grained label only. Never a family: families are derived by
  script afterwards.
- Apply code-state precedence. If a code-state pattern and a
  verification-process pattern both apply, the code-state pattern is the
  primary failure_pattern and the verification facet goes in failure_scope.
- UNASSIGNED does not exist here. If no defined pattern fits, use
  OTHER_TECHNICAL_PATTERN with taxonomy_fit OTHER and describe it in
  proposed_other_pattern. Do not force a poor fit: those cases are the answer
  to the question this study asks.
- Cite only evidence IDs listed in that packet.
- reasoning_summary is a short evidence-based justification, not a transcript
  of your reasoning.

Never read: the other reviewer's directory, data/sampling/, analysis/, or any
metadata.json, trajectory.jsonl, solver_result.json or pred_patch.diff. If you
find yourself wanting to know how a bug was made, that is exactly what this
protocol exists to prevent. Classify what is in front of you.

Write nothing outside reviews/<claude|codex>/. If you believe something else in
the repository is broken, stop and tell me rather than fixing it.

When all cases exist and validate, run:

    python scripts/validate_review_output.py --reviewer <claude|codex> --finalise

Then report: how many cases you recorded, the distribution of labels you
assigned, how many you marked OTHER_TECHNICAL_PATTERN or UNCLEAR, and anything
about the taxonomy that fitted badly. Do not compare yourself with the other
reviewer and do not run the analysis scripts.
```

### If you want it in one line

```bash
# Claude Code
claude "Read CLAUDE.md and taxonomy/frozen_failure_taxonomy_v1.md in full, run python scripts/check_review_ready.py --reviewer claude, then review every case exactly as CLAUDE.md instructs, saving each result immediately."

# Codex CLI
codex "Read AGENTS.md and taxonomy/frozen_failure_taxonomy_v1.md in full, run python scripts/check_review_ready.py --reviewer codex, then review every case exactly as AGENTS.md instructs, saving each result immediately."
```

The short form works because the briefs are self-contained: they carry the
label definitions quoted from the frozen taxonomy, the meaning of every
`failure_scope` and `taxonomy_fit` value, what a packet holds, a worked case,
and the boundaries. An agent that reads its brief needs nothing else.

## Layout

```
configs/      generator, solver, validation, sampling, environments
taxonomy/     the frozen AIDev taxonomy, imported verbatim, with provenance
prompts/      injector (removal, history reversion) and solver prompts
schemas/      generation metadata, validation result, review packet, review result
ssr/          the library: execution backends, action protocol, agent loop,
              validation, deduplication, sampling, packets, taxonomy, metrics
scripts/      one command-line entry point per pipeline step
data/         pools, sampling records, review packets, objective metrics
reviews/      codex/ and claude/, one directory each, strictly separated
analysis/     derived families, agreement, source-specific comparison
tests/        unit tests, plus the smoke repository and rehearsal fixtures
```

## The four isolation rules

Each is enforced by code, not convention. That is the point of the design.

| Rule | Enforced by |
|---|---|
| The injector never sees SWE-smith's test command, RepoProfile metadata, synthetic issue or fail-to-pass list. It discovers the tests itself. | `ssr/agent_loop.py` raises if a withheld string reaches the prompt |
| The solver never sees the injection diff, the strategy, the weakening diff or the parent bug. | `configs/solver.yaml` and `prompts/solver.md` |
| A review packet carries no strategy, order, lineage, generator identity or source allocation. | two fatal scans in `ssr/packets.py` |
| Sampling never reads a taxonomy label. | `ssr.sampling.assert_no_taxonomy_fields` |

Two more, on the review itself: `assert_write_boundary` refuses any write
outside a reviewer's own directory, and `require_both_complete` locks the
comparison until both `COMPLETE` markers exist. For a reviewer on someone
else's machine, `scripts/make_review_bundle.py` goes further and leaves the
hidden material out of what they receive at all.

## Research or rehearsal, never in doubt

Every checkout carries `data/CORPUS_STATUS.json`. **RESEARCH** means every
packet came from an execution-validated bug state built in an isolated
environment by the configured model. **REHEARSAL** means at least one packet
came from a harness-proving or synthetic source, so a review of it tests the
workflow and its numbers must not be reported.

The marker is written when the packets are built, copied into each reviewer's
metadata, and printed at the top of the family and comparison reports. Nobody
has to remember which kind of corpus they are looking at.

## The language mismatch, stated up front

The strict AIDev corpus is **34% TypeScript, 14% Go and 11% Python**.
SWE-smith is Python-dominant. The two cannot be matched on language, so any
difference in failure-pattern coverage between the corpora is confounded with
a difference in language. The selector pulls the sample as close to the AIDev
profile as the pool allows and records every language outside tolerance;
[`docs/fidelity_limitations.md`](docs/fidelity_limitations.md) states the
consequence for the research claim.

## The 30/30/40 caveat

The final 100 is deliberately allocated 30 first-order REMOVAL, 30 first-order
HISTORY_REVERSION, 40 second-order FAILED_SOLVER. That is a study-design
choice made for coverage, **not** an estimate of the natural published SSR
mixture. Report the three sources separately; report pooled figures only with
the caveat attached. `scripts/compare_reviews.py` does both automatically.

## This is SSR-style, not SSR

Published SSR uses CWM-sft 32B and CWM environment images, and its policy
evolves under reinforcement learning. This study uses a static surrogate
policy over SWE-smith environments. Read
[`docs/fidelity_limitations.md`](docs/fidelity_limitations.md) before placing
any number here beside a number from the SSR paper.

## Documentation

| Document | Covers |
|---|---|
| [`QUICKSTART.md`](QUICKSTART.md) | cloning and running a review on any machine, and handing one to someone else |
| [`docs/research_scope.md`](docs/research_scope.md) | the question, what crosses over from AIDev, what is withheld from whom |
| [`docs/swesmith_setup.md`](docs/swesmith_setup.md) | Docker, WSL, SWE-smith, declaring environments, the current blockers |
| [`docs/ssr_reproduction_protocol.md`](docs/ssr_reproduction_protocol.md) | the action protocol, the three stages, the eight validation checks, second-order construction |
| [`docs/sample_selection_protocol.md`](docs/sample_selection_protocol.md) | deduplication, the allocation and shortfall rule, repository domination, freezing |
| [`docs/review_protocol.md`](docs/review_protocol.md) | the reviewer's task, the record format, the boundaries, the analysis |
| [`docs/fidelity_limitations.md`](docs/fidelity_limitations.md) | every way this study differs from published SSR |

Reviewers read [`AGENTS.md`](AGENTS.md) (Codex) or [`CLAUDE.md`](CLAUDE.md)
(Claude) and nothing else about the pipeline.

## Tests

```bash
python -m pytest tests -q
```

The suite covers the action protocol, the taxonomy freeze and prompt drift,
deduplication, objective metrics, deterministic sampling under every
constraint, packet leakage scanning, and reviewer-output validation.

`scripts/selftest.py` runs all of it plus the whole downstream pipeline
against a scratch directory, and is the single command that answers "does this
checkout work on my machine".

`tests/make_smoke_repo.py` builds a tiny git repository so the generation
pipeline can be exercised without Docker; `tests/make_synthetic_pool.py` and
`tests/simulate_reviews.py` rehearse the downstream path at full scale.
Artifacts from either are marked REHEARSAL and excluded from the sampling
frame, so a rehearsal cannot leak into a real study.
