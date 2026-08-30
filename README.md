# SSR / SWE-smith coverage study

The SSR side of RQ1: does the frozen AIDev failure taxonomy cover the failures
that an SSR-style bug pipeline produces?

The AIDev side is already frozen in
[`MachineLearningAmateur/AIBugAnalysis`](https://github.com/MachineLearningAmateur/AIBugAnalysis).
This repository builds a comparable SSR-style corpus over SWE-smith
environments, freezes 100 neutral evidence packets, and has Codex and Claude
classify them independently under the **same** frozen taxonomy.

Start with [`docs/research_scope.md`](docs/research_scope.md).

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

```bash
python -m pip install -e ".[dev]"
python scripts/check_environment.py
```

Copy `.env.example` to `.env` and fill in `OPENROUTER_API_KEY`. The key is
never written to any artifact and is stripped from every sandbox process, so
an injector with shell access cannot read it.

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
python scripts/validate_review_output.py --reviewer codex  --finalise
python scripts/validate_review_output.py --reviewer claude --finalise

# 7. analysis, locked until both COMPLETE markers exist
python scripts/apply_frozen_families.py
python scripts/compare_reviews.py
python scripts/compute_patch_metrics.py --env <name>
```

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
comparison until both `COMPLETE` markers exist.

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

`tests/make_smoke_repo.py` builds a tiny git repository so the generation
pipeline can be exercised without Docker; `tests/make_synthetic_pool.py` and
`tests/simulate_reviews.py` rehearse the downstream path at full scale.
Artifacts from either are marked and excluded from the sampling frame, so a
rehearsal cannot leak into a real study.
