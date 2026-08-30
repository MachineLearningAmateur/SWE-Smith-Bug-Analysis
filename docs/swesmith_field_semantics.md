# SWE-smith field semantics, verified

Every field this study uses, what it actually means, and the evidence that
establishes it. Nothing here is inferred from SWE-bench naming conventions;
where SWE-smith departs from those conventions, it is called out.

Verified against:

* **Upstream code:** `SWE-bench/SWE-smith`, `swesmith/harness/gather.py` and
  `swesmith/bug_gen/collect_patches.py`.
* **Reconstruction:** `scripts/verify_swesmith_semantics.py`, run over five
  task instances spanning five generation methods. Results in
  `data/population/reconstruction_smoke_test.json`.

Datasets are read at pinned revisions (see `ssr/swesmith.py`):

| Dataset | Revision | Why pinned |
|---|---|---|
| `SWE-bench/SWE-smith-trajectories` | `f6b6d7e01f2b` | The last revision before the July 2025 expansion. One `train` split, 5016 rows. Current `main` has three much larger splits that are **not** the training set. |
| `SWE-bench/SWE-smith` | `9f2a10465194` | The 2025-04-29 upload, same day as the trajectory release. Carries `base_commit` and `created_at`, which current `main` has dropped. |

---

## How a task is stored

Each task instance exists as a **branch in a SWE-smith mirror repository on
GitHub**, named by its `instance_id`. `swesmith/harness/gather.py` builds it,
and the branch has exactly three commits:

```
Remove F2P Tests     <- branch head: the state the agent is given
Bug Patch            <- the buggy state
Initial commit       <- the CLEAN state
```

Confirmed on all five reconstructed instances.

The middle commit is created by applying the bug diff and committing it with
the literal message `'Bug Patch'`:

```python
# swesmith/harness/gather.py
for git_apply in GIT_APPLY_CMDS:
    output = subprocess.run(f"{git_apply} {abs_patch_path}", cwd=repo_path, ...)
...
cmds = ["git commit --no-gpg-sign -m 'Bug Patch'"]
```

The third commit deletes the oracle test files, so an agent cannot simply read
the tests that define the bug:

```python
f2p_test_files, _ = rp.get_test_files(task_instance)
for test_file in f2p_test_files:
    os.remove(test_file_path)
...
cmds = ["git add .", "git commit --no-gpg-sign -m 'Remove F2P Tests'"]
```

---

## Field by field

### `patch` — the BUG, not the fix

**This is the single most important departure from SWE-bench.** In SWE-bench,
`patch` is the gold repair. In SWE-smith, `patch` is the diff that *introduces*
the bug.

Evidence:

* In `gather.py` the patch read from the validation log is assigned to
  `KEY_PATCH` and then applied to the clean repository, producing the commit
  labelled `'Bug Patch'`. The log line is
  `f"[{subfolder}] Bug patch applied successfully"`.
* In `collect_patches.py` the patch file collected is
  `bug__{bug_type}__{uuid}.diff`, written by the bug generators.
* Reconstruction: for all five instances the dataset `patch` is **byte-equal**
  to the `Bug Patch` commit's own diff, ignoring blob-hash `index` lines
  (`PATCH_EQUALS_BUG_COMMIT`), applies cleanly to that commit's parent
  (`PATCH_APPLIES_TO_CLEAN`), and does **not** apply to the buggy state
  (`PATCH_IS_NOT_THE_FIX`).

**The gold repair is the reverse of `patch`.** There is no separate field for
it. Reversing `patch` on the buggy tree restored every touched file to its
clean blob on all five instances (`INVERSE_RESTORES_CLEAN`).

### `base_commit` — NOT the clean state

`base_commit` is a real commit in the mirror repository, but it is **not** the
parent of the bug. Its tree differs from the clean parent's tree on **all five**
reconstructed instances:

| Instance | `base_commit` tree | clean parent tree |
|---|---|---|
| `aio-libs__async-timeout…lm_rewrite__kqd6t1mb` | `e04753b011c8` | `f5171b007782` |
| `getmoto__moto…pr_7234` | `e477877501dd` | `ed923a134fdd` |
| `prettytable__prettytable…func_pm_ctrl_shuffle__d3x1djk0` | `c18baf11065c` | `a3a33585e809` |
| `conan-io__conan…func_pm_remove_assign__leq9zkie` | `954e63374f2b` | `e0438e9d259d` |
| `r1chardj0n3s__parse…func_pm_ctrl_invert_if__uho021ks` | `7243b45cf78d` | `437c7f032f08` |

Applying `patch` to `base_commit` fails for every one of them.

**Therefore: the clean state is the parent of the `Bug Patch` commit, not
`base_commit`.** Any reconstruction that treats `base_commit` as the clean
state is wrong. This study does not use `base_commit` for reconstruction; it
is carried in the population manifest as provenance only.

### `FAIL_TO_PASS` — renamed from PASS_TO_FAIL

These are the tests that **pass on the clean state and fail on the buggy
state** — the oracle. The name is a deliberate rename in `gather.py`:

```python
FAIL_TO_PASS: results[PASS_TO_FAIL],
# Flip PASS_TO_FAIL to FAIL_TO_PASS following SWE-bench naming convention
```

The validation harness records them as `PASS_TO_FAIL` (their behaviour when
the bug is applied); the released field name describes what a correct repair
must achieve. Both names describe the same tests.

The files containing them are **deleted from the branch head**, verified on all
five instances (`F2P_TESTS_WITHHELD`).

### `PASS_TO_PASS`

Tests passing in both states. A repair must not break them.

### `instance_id` — carries the generation method

Built in `collect_patches.py`:

```python
bug_type_and_uuid = file.split(f"{PREFIX_BUG}__")[-1].split(".diff")[0]
instance_id = f"{repo}.{bug_type_and_uuid}"
```

where `repo` is the bug-generation log directory name, which **already contains
a dot** (`owner__name.commitprefix`). So:

```
Cog-Creators__Red-DiscordBot . 33e0eac7 . lm_rewrite__1xt89hhu
└────────── owner__name ────┘ └ commit ┘ └ method ┘└─ uuid ─┘
```

The method is everything after the **last** dot and before the **last** double
underscore. Splitting on the first dot — which the shape invites — misparses
every repository whose directory name holds an extra dot.

**Mirror bugs are named after the pull request they came from** (`pr_7234`), so
the raw token is an instance identifier, not a method. Left unnormalised it
yields 1,121 one-member "methods" out of 1,138. `ssr.swesmith.generation_method`
maps every `pr_<digits>` to `pr_mirror`; `generation_method_raw` keeps the
original.

Method families follow the `swesmith/bug_gen/` module layout:

| Family | Methods | Module |
|---|---|---|
| `procedural` | `func_pm_*`, `func_basic` | `bug_gen/procedural/` |
| `llm` | `lm_rewrite` | `bug_gen/llm/` |
| `combine` | `combine_file`, `combine_module` | `bug_gen/combine/` |
| `mirror` | `pr_mirror` | `bug_gen/mirror/` |

### `repo`

The **mirror** repository, `swesmith/{owner}__{name}.{commit}`, not the
upstream project. The upstream name is recovered by
`ssr.swesmith.upstream_repo` and is what a review packet shows; the mirror name
would tell a reviewer the corpus is synthetic.

### `problem_statement`

A generated issue text. Present in the task dataset. Its generation is a
separate LM step (`swesmith/issue_gen/`), so it is a description of the bug
rather than independent evidence of it, and it can be wrong.

### `image_name`

The Docker image for the task environment. Not needed to build review packets:
the bug diff, the test lists and the repository contents all come from the
dataset and the mirror repository. It is needed only to **execute** tests.

---

## What this means for review packets

The reviewer needs the bug and its consequences, not the machinery:

| Packet evidence | Source | Verified |
|---|---|---|
| `BUG_DIFF` | the `patch` field | is the bug, byte-equal to the `Bug Patch` commit |
| `CODE_CONTEXT_NN` | files the patch touches, at the buggy state | fetched from the branch |
| `TEST_FAILURE_NN` | `FAIL_TO_PASS` entries | the oracle |
| `SPECIFICATION` | `problem_statement` | generated text, treated as description |
| `REFERENCE_REPAIR` | the reverse of `patch` | restores the clean blobs |

Nothing in that list requires Docker, an API key, or executing anything.

## Open points

* **4 of 4,211** unique training tasks do not resolve to any row in the pinned
  task revision; all four are `pallets__flask.bc098406`, a mirror repository
  absent from that revision entirely. They are excluded and listed in
  `data/population/unresolved_instances.json`.
* The trajectory dataset card says **5017** trajectories; the shipped data at
  the pinned revision has **5016** rows. Reported, not reconciled.
* Whether `base_commit` is the mirror's default-branch head, or something else
  again, is not established. It is not needed, so it was not chased.
