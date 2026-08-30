# Research scope

## The question

RQ1 asks how well one frozen failure taxonomy, derived from real AI-agent
pull requests, covers a different population of failures. The AIDev side of
that question is already answered and sealed. This repository builds the SSR
side.

The comparison only means something if the two sides are classified with the
*same* rubric by the *same* two reviewers under the *same* blind protocol.
Everything in this repository exists to make that true and to make it
checkable afterwards.

## The two sides

| | AIDev side | SSR side (this repository) |
|---|---|---|
| Population | Pull requests opened by AI coding agents on public repositories | Synthetic, execution-validated bug states produced in an SSR-style pipeline |
| Failure evidence | PR diff, reviews, comments, CI, timeline | Clean-to-buggy diff, oracle test evidence, clean-versus-buggy results |
| Corpus | Frozen, `MachineLearningAmateur/AIBugAnalysis` at `85e4bf9` | Built here |
| Taxonomy | `aidev_failure_taxonomy_v1`, frozen 2026-08-29 | The same file, byte for byte |
| Reviewers | Codex and Claude, independent and blind | Codex and Claude, independent and blind |

## What SWE-smith is, and is not

SWE-smith is the **environment layer only**. It supplies executable
repositories with working test suites, which is exactly the hard part of
building an SSR-style corpus.

It is not the bug source. SWE-smith's own mutation operators produce a
different kind of defect from SSR's REMOVAL and HISTORY_REVERSION strategies,
and calling a SWE-smith mutation an SSR bug would silently change the
population under study. `configs/environments.yaml` therefore carries no test
command, no RepoProfile metadata, no synthetic issue and no fail-to-pass list,
and `ssr/agent_loop.py` raises rather than send any withheld string to the
injector.

## What is deliberately withheld from whom

| Actor | May see | May never see |
|---|---|---|
| Injector | The repository, and nothing else | SWE-smith's test command, RepoProfile metadata, synthetic issue text, fail-to-pass lists, mutation metadata |
| Solver | The buggy repository, the failing test names, the test command, the failing output | The injection diff, the strategy, the weakening diff, the parent bug, any generation metadata |
| Reviewer | The neutral packet: one diff, code context, oracle test output, clean-versus-buggy results | Strategy, bug order, parent lineage, generator or solver identity, source allocation, trajectories, the other reviewer's results |
| Sampler | Validation status, source and order metadata, language and size strata, deduplication status, the seed | Every taxonomy label, without exception |

Each of those four rows is enforced by code, not by convention:
`ssr/agent_loop.py`, `configs/solver.yaml` plus the solver prompt,
`ssr/packets.py`, and `ssr/sampling.assert_no_taxonomy_fields` respectively.

## The one-directional flow from AIDev

Two things cross from the AIDev study into this one, and nothing else:

1. **The frozen taxonomy**, imported byte for byte, hashes recorded in
   `taxonomy/TAXONOMY_PROVENANCE.json`.
2. **Neutral environment characteristics** of the AIDev corpus — the language
   mix — used to choose comparable SWE-smith environments. Produced by
   `scripts/profile_aidev_environment_mix.py`, which reads repository names
   and diff file extensions only and refuses to open any review artifact.

AIDev failure-family frequencies and AIDev failure examples are used
**nowhere**: not to guide generation, not to guide deduplication, not to guide
selection. The whole point of the coverage question is that the SSR failures
are allowed to fall outside the taxonomy. Steering them towards it would
answer a different question.

## The deliberate 30/30/40 stratification

The final 100 is allocated 30 first-order REMOVAL, 30 first-order
HISTORY_REVERSION, 40 second-order FAILED_SOLVER. This is a **study-design
allocation chosen for coverage**, not an estimate of the natural published SSR
mixture. Every analysis script carries the caveat, and
`scripts/compare_reviews.py` reports the three sources separately before it
reports anything pooled.

## What this study cannot claim

* It does not reproduce published SSR. It uses a surrogate policy and a
  different environment substrate. See `docs/fidelity_limitations.md`.
* Its pooled label proportions are not SSR's natural distribution.
* Its family-level agreement is not an out-of-sample estimate for the AIDev
  mapping: the mapping was derived on the AIDev disagreements. It is an
  out-of-sample estimate for *this* population, which is the point.

## Order of work

1. `docs/swesmith_setup.md` — get an executable environment.
2. `docs/ssr_reproduction_protocol.md` — generate and validate bugs.
3. `docs/sample_selection_protocol.md` — build the pool, deduplicate, select.
4. `docs/review_protocol.md` — the two blind reviews and the comparison.
