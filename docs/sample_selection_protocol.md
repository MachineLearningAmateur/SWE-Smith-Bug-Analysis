# Sample selection protocol

How the pool becomes exactly 100 bugs, and why the rule is written down before
the pool exists.

## The rule is predeclared

`configs/sampling.yaml` fixes the seed, the target size, the allocation, the
per-repository ceiling, the unique-repository floor and the lineage rule
**before** any selection runs. A selection rule invented after seeing the pool
is not a sampling rule, it is a choice of results.

## Selection is taxonomy-blind, and that is enforced

Selection may depend only on:

* validation status,
* source and order metadata,
* language and repository-size strata,
* deduplication status,
* the fixed seed.

`ssr.pool.PoolEntry.neutral_record` builds the only view of a bug that
selection sees, and `ssr.sampling.assert_no_taxonomy_fields` refuses to run if
any field name in it looks like a taxonomy or review field. A contaminated
input is a crash, not a quiet bias.

## Build a pool first, and a big one

Do not stop at 100 validated bugs. Target at least 150 validated,
deduplicated states; 180 to 200 is better. A pool barely larger than the
sample makes every constraint — the repository ceiling, the language match,
the lineage rule — unsatisfiable, and the selection degrades into "take what
there is".

The pool should contain first-order REMOVAL, first-order HISTORY_REVERSION and
naturally produced second-order FAILED_SOLVER states.

## Deduplication (before selection, never after)

`scripts/deduplicate_bug_pool.py` applies six deterministic signals in a fixed
order. The first that fires owns the exclusion, so the report reads as one
reason per excluded bug:

| Signal | What it catches |
|---|---|
| `EXACT_DIFF` | byte-identical `bug_inject.diff` |
| `NORMALISED_DIFF` | identical once index lines, hunk line numbers and whitespace noise are stripped |
| `IDENTICAL_TREE` | identical buggy tree hash on the same source commit |
| `DUPLICATE_SECOND_ORDER` | same parent bug and same normalised repair |
| `SAME_HUNK` | same repository, same files, same hunk anchors: two attempts that hit one code region |
| `SAME_REVERTED_COMMIT` | two history reversions undoing the same commit |

The survivor of a group is the lowest bug ID, so the outcome does not depend
on the order candidates were generated or on directory listing order. No
taxonomy label is read.

## The allocation, and the shortfall rule

The preferred allocation is a **study-design choice for coverage**, not a
claim about the natural published SSR mixture:

```
30  first-order REMOVAL
30  first-order HISTORY_REVERSION
40  second-order FAILED_SOLVER
```

Second-order bugs are the scarce ones, because they need a genuine solver
failure. When fewer than 40 exist:

1. take every eligible second-order bug, up to 40;
2. fill the remaining slots equally between REMOVAL and HISTORY_REVERSION;
3. record the deviation in `data/sampling/selection_deviations.json`;
4. report source-specific analyses separately.

If the pool cannot fill 100 at all, the shortfall is recorded as
`POOL_TOO_SMALL` and the sample is left short. It is never padded.

## Repository domination

* at least 25 unique repositories, 30 or more preferred;
* at most 4 selected bugs from any one repository;
* avoid two bugs from the same base state;
* avoid selecting both a first-order parent and its direct second-order child.

The last two are preferences, not hard rules, and the selector says so out
loud. It tries the strict rule first and relaxes one constraint at a time,
recording a `CONSTRAINT_RELAXED` deviation naming the bug and the relaxation.
Any parent/child pair that survives is listed in `lineage_pairs` and flagged
`LINEAGE_PAIRS_PRESENT` for clustered or sensitivity analysis.

A repair pass afterwards raises the unique-repository count, if it is below
the floor, by swapping the most over-represented repository's latest pick for
a candidate from an unused repository in the same stratum. Each swap is
recorded.

## Environment matching, and the mismatch that will not go away

`scripts/profile_aidev_environment_mix.py` reads the strict AIDev corpus and
records its neutral language mix. It reads repository names and diff file
extensions, and nothing else; it refuses to open any review artifact.

As built, the strict AIDev corpus (n = 35, 29 repositories) is:

| Language | Share |
|---|---:|
| typescript | 34.3% |
| go | 14.3% |
| python | 11.4% |
| unknown | 11.4% |
| rust | 8.6% |
| csharp | 5.7% |
| java | 5.7% |
| cpp | 2.9% |
| php | 2.9% |
| c | 2.9% |

SWE-smith's environment set is overwhelmingly Python. **The language match
cannot be achieved.** The selector pulls the sample as far towards the profile
as the pool allows — at each greedy step it takes the feasible candidate that
most reduces the current language deficit, breaking ties by a seeded
permutation — and then records every language outside tolerance in
`data/sampling/selection_record.json`. That record is the honest statement of
the gap, and `docs/fidelity_limitations.md` repeats it.

Repository size is not recorded in the frozen AIDev evidence packets. The
profiler reports `UNKNOWN` rather than inferring size from diff size, which
would be a fabricated stratum. Size matching is therefore not attempted.

## Neutral identifiers

Reviewers see `SSR_001` to `SSR_100`, assigned by a **seeded shuffle** of the
selected bug IDs. The index therefore carries no information about stratum,
repository or generation order. The crosswalk from `SSR_nnn` back to the
internal bug ID lives in `data/sampling/selection_crosswalk.csv`, which is
hidden metadata: `AGENTS.md` and `CLAUDE.md` both forbid reviewers to open
`data/sampling/`.

`data/review_manifest.csv` is the reviewer-visible manifest and holds packet
IDs and packet paths only.

## Freezing

After selection:

1. `data/review_manifest.csv` is written and its SHA-256 recorded in
   `data/sampling/review_manifest_freeze.json`;
2. `scripts/build_review_packets.py` writes the packets and
   `data/review_snapshot_manifest.json`, holding the path, per-file SHA-256
   and one digest per packet;
3. both reviewers record the snapshot manifest's own SHA-256 in their
   `review_metadata.json`.

If the manifest hash changes during a review, `ssr/review_workflow.finalise`
refuses to finalise and says the review is void. That is the intended
behaviour: evidence that moved under a reviewer is not evidence.

## Determinism

The same pool and the same seed produce the same 100 bugs and the same packet
IDs on any machine. `tests/test_sampling.py` asserts this, along with the
ceiling, the floor, the shortfall arithmetic and the lineage rule.

## Rehearsal

`tests/make_synthetic_pool.py` builds a fabricated pool so the whole
downstream path can be exercised at full scale before a real corpus exists.
Its records are marked synthetic and carry the `local` backend, which
`ssr.pool.eligible_entries` drops from the sampling frame. A rehearsal
therefore cannot leak into a real study.
