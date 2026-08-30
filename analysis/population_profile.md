# Population profile

The population for this study is the **unique SWE-smith task instances behind
the official training trajectories for SWE-agent-LM-32B**, not the full
SWE-smith corpus. Both source datasets are read at pinned revisions.

## Provenance

| | |
|---|---|
| Trajectory dataset | `SWE-bench/SWE-smith-trajectories` @ `f6b6d7e01f2b` |
| Task dataset | `SWE-bench/SWE-smith` @ `9f2a10465194` |

Last revision before the 2025-07-18/19 expansion. Its dataset card declares a single train split with num_examples 5016, and its prose states these are the trajectories used to fine-tune SWE-agent-LM-32B.

The 2025-04-29 upload, made the same day as the trajectory release. 50,137 rows, and unlike the current main it still carries base_commit and created_at.

## From trajectories to tasks

| Step | Count |
|---|---:|
| Trajectories claimed by the dataset card | 5017 |
| Trajectory rows actually in the pinned revision | 5016 |
| Unique task instances behind them | 4211 |
| Resolved in the pinned task dataset | 4207 |
| Unresolved, excluded | 4 |

**N = 4207.** Note that N is not 5017, and not 5016 either: 805 trajectory
rows are repeat attempts at a task already counted. One population row per
unique underlying synthetic bug; the same bug is never counted twice.

The card's prose says 5017 while the shipped data has 5016 rows. Reported, not
reconciled: the data is what can be counted.

The 4 unresolved instances are all `pallets__flask.bc098406`, a mirror
repository absent from the pinned task revision entirely. Listed in
`data/population/unresolved_instances.json`.

## Duplicate-task rate

| Trajectories per task | Tasks |
|---:|---:|
| 1 | 3717 |
| 2 | 176 |
| 3 | 314 |

88.4% of tasks have exactly one training trajectory.

## Generation method

| Method | Family | Tasks | Share |
|---|---|---:|---:|
| `lm_rewrite` | llm | 1529 | 36.3% |
| `pr_mirror` | mirror | 1161 | 27.6% |
| `func_pm_ctrl_shuffle` | procedural | 505 | 12.0% |
| `func_pm_remove_assign` | procedural | 224 | 5.3% |
| `func_pm_ctrl_invert_if` | procedural | 219 | 5.2% |
| `func_pm_remove_cond` | procedural | 122 | 2.9% |
| `func_pm_class_rm_funcs` | procedural | 83 | 2.0% |
| `combine_file` | combine | 75 | 1.8% |
| `func_pm_class_rm_base` | procedural | 65 | 1.5% |
| `func_pm_remove_loop` | procedural | 54 | 1.3% |
| `func_pm_op_swap` | procedural | 53 | 1.3% |
| `func_pm_op_change` | procedural | 39 | 0.9% |
| `func_pm_op_change_const` | procedural | 25 | 0.6% |
| `func_pm_remove_wrapper` | procedural | 23 | 0.5% |
| `func_pm_op_break_chains` | procedural | 13 | 0.3% |
| `func_basic` | procedural | 7 | 0.2% |
| `func_pm_class_shuffle_funcs` | procedural | 6 | 0.1% |
| `combine_module` | combine | 4 | 0.1% |

### By family

| Family | Tasks | Share |
|---|---:|---:|
| llm | 1529 | 36.3% |
| procedural | 1438 | 34.2% |
| mirror | 1161 | 27.6% |
| combine | 79 | 1.9% |

`pr_mirror` is 1,121 distinct pull requests normalised to one method: the raw
token names the PR the bug was taken from, so it identifies the instance, not
the method. See `docs/swesmith_field_semantics.md`.

## Repositories

- unique upstream repositories: **122**
- largest single share: **5.3%** (`getmoto/moto`)
- top 10 hold **33.2%** of the population

| Repository | Tasks | Share |
|---|---:|---:|
| `getmoto/moto` | 225 | 5.3% |
| `conan-io/conan` | 214 | 5.1% |
| `pandas-dev/pandas` | 200 | 4.8% |
| `pydantic/pydantic` | 145 | 3.4% |
| `iterative/dvc` | 134 | 3.2% |
| `sqlfluff/sqlfluff` | 111 | 2.6% |
| `scanny/python-pptx` | 94 | 2.2% |
| `tobymao/sqlglot` | 93 | 2.2% |
| `pylint-dev/astroid` | 91 | 2.2% |
| `dask/dask` | 89 | 2.1% |
| `pydicom/pydicom` | 89 | 2.1% |
| `pygments/pygments` | 88 | 2.1% |

## Language

**Every task is Python.** The task corpus at the pinned revision is
Python-only, so language is not an informative stratum here and language
balancing is a no-op rather than a choice.

This matters for the comparison with AIDev, whose strict corpus is 34%
TypeScript, 14% Go and 11% Python. Any coverage difference between the two
corpora is confounded with a difference in language. See `docs/limitations.md`.

## Task shape

| | Median | Mean | Max |
|---|---:|---:|---:|
| FAIL_TO_PASS tests | 3 | 104.9 | 10932 |
| Bug diff bytes | 1331 | 2224 | 72143 |

## What this population is, and is not

These are SWE-smith tasks that **yielded a trajectory good enough to be used
for fine-tuning**. They are a selected set of successful SWE-agent + Claude
3.7 Sonnet rollouts, not the full SWE-smith generation distribution.

That selection is not a flaw for this research question. The question is what
the training data covered, and this is exactly the training data. It does mean
the answer must never be stated as a claim about SWE-smith generation in
general. See `docs/limitations.md`.
