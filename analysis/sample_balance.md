# Sample balance

Population: **4207** unique SWE-smith task
instances behind the official training trajectories for SWE-agent-LM-32B.
Sample: **100** cases, seed `20260830`, proportional
largest-remainder allocation across `generation_method`.

## Generation method

| Method | Population | Share | Allocated | Sample | Share | Deviation |
|---|---:|---:|---:|---:|---:|---:|
| `lm_rewrite` | 1529 | 36.3% | 36 | 36 | 36.0% | -0.3% |
| `pr_mirror` | 1161 | 27.6% | 28 | 28 | 28.0% | +0.4% |
| `func_pm_ctrl_shuffle` | 505 | 12.0% | 12 | 12 | 12.0% | -0.0% |
| `func_pm_remove_assign` | 224 | 5.3% | 5 | 5 | 5.0% | -0.3% |
| `func_pm_ctrl_invert_if` | 219 | 5.2% | 5 | 5 | 5.0% | -0.2% |
| `func_pm_remove_cond` | 122 | 2.9% | 3 | 3 | 3.0% | +0.1% |
| `func_pm_class_rm_funcs` | 83 | 2.0% | 2 | 2 | 2.0% | +0.0% |
| `combine_file` | 75 | 1.8% | 2 | 2 | 2.0% | +0.2% |
| `func_pm_class_rm_base` | 65 | 1.6% | 2 | 2 | 2.0% | +0.4% |
| `func_pm_remove_loop` | 54 | 1.3% | 1 | 1 | 1.0% | -0.3% |
| `func_pm_op_swap` | 53 | 1.3% | 1 | 1 | 1.0% | -0.3% |
| `func_pm_op_change` | 39 | 0.9% | 1 | 1 | 1.0% | +0.1% |
| `func_pm_op_change_const` | 25 | 0.6% | 1 | 1 | 1.0% | +0.4% |
| `func_pm_remove_wrapper` | 23 | 0.5% | 1 | 1 | 1.0% | +0.4% |
| `func_pm_op_break_chains` | 13 | 0.3% | 0 | 0 | 0.0% | -0.3% |
| `func_basic` | 7 | 0.2% | 0 | 0 | 0.0% | -0.2% |
| `func_pm_class_shuffle_funcs` | 6 | 0.1% | 0 | 0 | 0.0% | -0.1% |
| `combine_module` | 4 | 0.1% | 0 | 0 | 0.0% | -0.1% |

Largest absolute deviation: **0.4%**.
One case is one percent, so that is the granularity of a 100-case sample.

## Repositories

- unique repositories: **52**
- most cases from one repository: **5** (cap 5)

| Repository | Cases |
|---|---:|
| `davidhalter/parso` | 5 |
| `getmoto/moto` | 5 |
| `conan-io/conan` | 5 |
| `tobymao/sqlglot` | 5 |
| `pylint-dev/astroid` | 4 |
| `pydicom/pydicom` | 4 |
| `seperman/deepdiff` | 3 |
| `encode/starlette` | 3 |
| `theskumar/python-dotenv` | 3 |
| `pandas-dev/pandas` | 3 |
| `tkrajina/gpxpy` | 3 |
| `oauthlib/oauthlib` | 3 |
| `pydantic/pydantic` | 3 |
| `sqlfluff/sqlfluff` | 3 |
| `joke2k/faker` | 3 |

## Distortions

- `REPOSITORY_CAP_APPLIED`: {"stratum": "pr_mirror", "instances_skipped": 2, "cap": 5}
- `REPOSITORY_CAP_APPLIED`: {"stratum": "func_pm_class_rm_funcs", "instances_skipped": 1, "cap": 5}
- `REPOSITORY_CAP_APPLIED`: {"stratum": "func_pm_remove_loop", "instances_skipped": 1, "cap": 5}
- `REPOSITORY_CAP_APPLIED`: {"stratum": "func_pm_op_change", "instances_skipped": 1, "cap": 5}
- `REPOSITORY_CAP_APPLIED`: {"stratum": "func_pm_op_change_const", "instances_skipped": 1, "cap": 5}

## Reconstruction failures and replacements

None. Every selected task reconstructed on the first round.

## Language

Every task is Python; the pinned corpus is Python-only. See
`analysis/language_confound_plan.md`.
