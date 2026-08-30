# Fidelity limitations

This study is **SSR-style**, not a reproduction of published SSR. Every gap
below is deliberate and known. Read this before quoting any number from this
repository next to a number from the SSR paper.

## 1. The policy is a surrogate

| | Published SSR | This study |
|---|---|---|
| Model | CWM-sft, 32B | `qwen/qwen-2.5-coder-32b-instruct` via OpenRouter |
| Training | Task-specific supervised fine-tuning | General code-instruct model, no fine-tuning |
| Adaptation | The policy evolves under reinforcement learning | A static policy for the whole corpus |

Qwen2.5-Coder-32B-Instruct was chosen for being code-specialised, close in
parameter count, and available. It is a **surrogate**, not the same model.
Bugs it produces may differ systematically in kind, not only in quality, from
bugs CWM-sft produces. Nothing here estimates that difference.

The static-policy point matters more than it looks. Published SSR's generator
improves during the run, so its later bugs are drawn from a different
distribution than its earlier ones. This corpus is drawn from one fixed
distribution throughout. That is a cleaner sample and a less faithful one.

### 1a. Provider access, and any substitution

`qwen/qwen-2.5-coder-32b-instruct` is currently served on OpenRouter by one
provider, and this account's privacy setting excludes it. Either the provider
is permitted, or a different model is used.

**If a model is substituted, record it here before generation starts:** the
model ID, the date, the reason, and the parameter count and architecture. A
mixture-of-experts model with 30B total and ~3B active parameters is not
scale-comparable to a 32B dense model, whatever the headline number says, and
the paper must not imply otherwise.

*No substitution has been made. The configured model is the handoff's model.*

## 2. The environment substrate is different

| | Published SSR | This study |
|---|---|---|
| Environments | CWM environment images | SWE-smith images |
| Repository set | The SSR corpus | Whatever SWE-smith provides |
| Test discovery | SSR's own | The injector discovers it, unaided |

SWE-smith is used as the environment layer only. Its native mutation
operators are not used, and its known test command, RepoProfile metadata,
synthetic issues and fail-to-pass lists are withheld from the injector by
`ssr/agent_loop.py`, which raises rather than let one through.

## 3. The language mix does not match AIDev, and cannot

The strict AIDev corpus (n = 35, 29 repositories), profiled from repository
names and diff file extensions only:

| Language | AIDev share | SWE-smith availability |
|---|---:|---|
| typescript | 34.3% | very limited |
| go | 14.3% | limited |
| python | 11.4% | dominant |
| unknown | 11.4% | not applicable |
| rust | 8.6% | limited |
| csharp | 5.7% | limited |
| java | 5.7% | limited |
| cpp | 2.9% | limited |
| php | 2.9% | limited |
| c | 2.9% | limited |

The AIDev corpus is TypeScript-dominant; SWE-smith is Python-dominant. **This
mismatch cannot be fixed within this design.** The selector pulls the sample
as far towards the AIDev profile as the pool allows and records every language
outside tolerance in `data/sampling/selection_record.json`.

The consequence for the research claim: any difference in failure-pattern
coverage between the two corpora is confounded with a difference in language.
A pattern that is common in TypeScript codebases and rare in Python ones will
look like a taxonomy-coverage effect when it is a language effect. Say so.

## 4. Repository size is not matched at all

Repository size is not recorded in the frozen AIDev evidence packets and was
not inferred from them. Inferring repository size from diff size would be a
fabricated stratum, and a fabricated stratum is worse than an absent one, so
`repo_size_bin` is `UNKNOWN` for every AIDev case and size matching is not
attempted.

## 5. The source mixture is not reproduced

Published SSR's natural mixture of first-order removal, first-order history
reversion and higher-order failed-solver states is not reproduced. This corpus
is deliberately stratified 30/30/40 for **coverage**, so that each source has
enough cases to be analysed on its own.

Therefore: pooled proportions from this study are not an estimate of SSR's
natural failure distribution, and must never be presented as one.
`scripts/compare_reviews.py` attaches the caveat to every pooled figure and
reports the three sources separately first.

## 6. Second-order bugs depend on the surrogate's failures

A second-order state exists only where the solver genuinely failed to repair a
first-order bug. Which bugs those are is a property of *this* solver. A
stronger solver would fail on a different, probably harder, subset; a weaker
one on a broader subset. The second-order stratum is therefore
policy-dependent in a way the first-order strata are not.

Nothing is tuned to make the solver fail. If the yield is low, the low yield
is reported as a finding.

## 7. Test weakening is agent-generated

`test_weaken.diff` shows that a bug's failure signal *can* be suppressed by a
plausible test edit. It is written by the same model that wrote the bug, so it
measures what this model finds easy to suppress. Do not read it as a general
claim about how detectable the bug is.

## 8. Blinding limits

Packets carry no generation metadata, and two fatal scans enforce that. But a
diff has a shape, and a reviewer may privately guess how a state arose. The
achievable guarantee is narrower: no packet field, file name or identifier
tells them, and no guess can be confirmed. Whether the shape itself leaks is
examinable after the fact, in the by-source agreement figures.

## 9. Validation is subset-based

The injector chooses a test subset, typically one subsystem, rather than the
whole suite, because whole-suite runs are too slow to validate at corpus
scale. So "the repository still runs" means the chosen subset still runs. A
bug could break something outside the subset without being noticed. The
subset, the command and the parser are all recorded per bug, so the scope of
each claim is visible.

## 10. The taxonomy freeze is real, and one-directional

`taxonomy/frozen_failure_taxonomy_v1.md` and `taxonomy/pattern_families.yaml`
are byte-identical to the AIDev originals, with hashes recorded in
`taxonomy/TAXONOMY_PROVENANCE.json` and re-checked by
`ssr.taxonomy.verify_provenance` on every analysis run.

The taxonomy must not change on the basis of what SSR bugs look like. Any
change requires a new version with its own freeze record. Conversely, AIDev
failure-family frequencies and failure examples were not used to guide
generation, deduplication or selection: only the neutral language profile
crossed over.

## 11. In-sample versus out-of-sample agreement

AIDev's frozen-family agreement of 73.5% (κ = 0.6575) is an **in-sample**
figure: the family mapping was derived from the same disagreements it is
scored on. The agreement computed here is out-of-sample for this population.
The two numbers answer different questions and must not be shown as a
before-and-after.
