# Language confound: analysis plan

## The problem

The SWE-smith training population is **100% Python**. The frozen AIDev strict
corpus is not:

| Language | Strict AIDev cases (n = 35) | Share |
|---|---:|---:|
| typescript | 12 | 34.3% |
| go | 5 | 14.3% |
| **python** | **4** | **11.4%** |
| unknown | 4 | 11.4% |
| rust | 3 | 8.6% |
| csharp | 2 | 5.7% |
| java | 2 | 5.7% |
| cpp | 1 | 2.9% |
| php | 1 | 2.9% |
| c | 1 | 2.9% |

Language was derived from the dominant source-file extension in each case's
pull-request diff, by `scripts/profile_aidev_environment_mix.py`. Documentation,
configuration and lock files are ignored; a tie gives `unknown`.

**Any difference in failure-pattern coverage between the two corpora is
confounded with a difference in language.** A pattern common in TypeScript
codebases and rare in Python ones will present as a taxonomy-coverage effect
when it is a language effect. This cannot be sampled away: it is a property of
what the two corpora are.

## The planned analyses

### A. Main descriptive comparison

Frozen AIDev strict corpus (n = 35) versus the SWE-smith strict consensus
corpus drawn from the 100 reviewed training tasks.

Reported as a descriptive comparison of family coverage, never as a
significance test between two small, differently-constructed samples. The
language confound is stated wherever the comparison appears.

### B. Python-matched sensitivity analysis

Restrict AIDev to its Python cases and compare against SWE-smith.

**This analysis is already known to be uninformative, and that must be reported
rather than discovered later.** The Python subset of the strict AIDev corpus is:

* **n = 4** — cases `003`, `012`, `030`, `042`;
* **all four carry the same broad family**, `REPOSITORY_UNDERSTANDING`.

With four cases and no family variation, the subset cannot distinguish a
language effect from a coverage effect, and no proportion computed on it is
meaningful. The plan is therefore:

1. report the Python subset's size and family composition, as above;
2. state explicitly that it is too small to support the comparison;
3. **do not** report proportions, agreement statistics or coverage percentages
   computed on n = 4;
4. do not widen the definition of "Python" to inflate it, and do not quietly
   fall back to the broader AIDev consensus corpora.

If the broader AIDev consensus sets (51 technical-defect cases, 48 code-state
cases) yield a materially larger Python subset, that may be reported as a
secondary sensitivity analysis, clearly labelled as a different and less strict
population, with its own n stated.

### C. Reviewer-specific sensitivity analyses

Codex-only and Claude-only comparisons, on both sides, to show that any finding
does not rest on one reviewer's labelling:

* Codex-only AIDev versus Codex-only SWE-smith;
* Claude-only AIDev versus Claude-only SWE-smith;
* the Python-matched version of each, **only where the sample size permits** —
  which, per B, it does not for the strict corpus.

### D. Generation-method breakdown, as a partial control

The SWE-smith side can be split by generation method, which the AIDev side has
no analogue for. It is still worth reporting: `lm_rewrite` bugs (36.3% of the
population) were written by a language model asked to rewrite a function, so
they are the closest thing in this corpus to agent-authored code. If the
`lm_rewrite` subset resembles AIDev more than the procedural subsets do, that is
evidence about the *mechanism* of any coverage gap, and it is **not** confounded
with language, because every SWE-smith case is Python.

This is the strongest control available and should be reported alongside A.

## What must not happen

* The frozen AIDev corpus is not altered, re-reviewed or re-labelled.
* The SWE-smith 100 was selected before any of this was computed, and these
  results must not be used to change which tasks are in it. The language
  profile above was produced **after** the sample was frozen, and the sampler
  reads no taxonomy field (`ssr.swesmith_sampling.assert_neutral`).
* No pooled proportion is reported without the language confound attached.

## How language will be reported

Every comparison table carries a language row. Where a SWE-smith figure is set
beside an AIDev figure, the caption states that one side is entirely Python and
the other is 11.4% Python.
