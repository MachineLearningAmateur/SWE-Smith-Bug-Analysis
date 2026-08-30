# Limitations

## 1. The population is a selected set, by construction

The 4,207 tasks are those that **yielded a trajectory good enough to be used
for fine-tuning** SWE-agent-LM-32B. They are successful SWE-agent + Claude 3.7
Sonnet rollouts, not the full SWE-smith generation distribution.

This is not a flaw for the current question, which asks what the *training
data* covered. It does mean:

* No result here may be stated as a claim about SWE-smith generation in
  general. Tasks that never produced a usable trajectory are invisible to it,
  and they may well be the harder or stranger ones.
* A later robustness check could sample 100 from all 50k tasks and compare.
  That is deliberately out of scope now.

## 2. Every task is Python; the AIDev corpus is not

The pinned SWE-smith corpus is Python-only. The strict AIDev corpus is 34.3%
TypeScript, 14.3% Go and 11.4% Python.

**Any difference in failure-pattern coverage between the two corpora is
confounded with a difference in language.** A pattern common in TypeScript
codebases and rare in Python ones will look like a taxonomy-coverage effect
when it is a language effect. This cannot be fixed by sampling; it is a
property of what the two corpora are.

## 3. Process patterns have no evidence here

Two labels in the frozen taxonomy describe repair *process*:
`vacuous_verification` and `unverified_trial_and_error`. A static synthetic bug
provides no agent-repair-process evidence at all.

Reviewers must not invent process evidence, and must not treat the
mutation-generation system's own procedure as an agent's repair process. The
correct consequence is that those two labels should be rare or absent, and a
sensitivity analysis comparing only code-state families is the right way to
read the result. The taxonomy itself is not modified, and the sealed AIDev
classifications are not revisited.

## 4. The bug is synthetic; the AIDev bugs are not

An AIDev case is a real agent's attempt to solve a real problem. A SWE-smith
case is a deliberately introduced defect that a validation harness confirmed
breaks tests. They are both "technical failures in a code state", which is what
makes the shared rubric meaningful, but they arise from different processes.

In particular, `lm_rewrite` bugs (36.3% of the population) were written by a
language model asked to rewrite a function, so they resemble agent-authored
code more than the procedural mutations do. The by-method breakdown in the
comparison is the place to look for that.

## 5. Counts that do not reconcile

* The trajectory dataset card says **5017**; the shipped data at the pinned
  revision has **5016** rows. Reported, not reconciled.
* 4 of 4,211 unique tasks (0.09%) resolve to no row in the pinned task
  revision and are excluded.

## 6. `base_commit` is not the clean state

Verified on five instances: the dataset's `base_commit` has a different tree
from the bug's actual parent, and the bug diff does not apply to it. Any
reconstruction that trusts `base_commit` is wrong. This study takes the clean
state from the parent of the `Bug Patch` commit instead. See
`docs/swesmith_field_semantics.md`.

## 7. Blinding limits

Review packets carry no generation method, no trajectory, no mirror repository
name and no training metadata. But a diff has a shape, and a reviewer may
privately guess that a change looks procedural rather than model-written. The
achievable guarantee is that no packet field tells them and no guess can be
confirmed. Whether the shape itself carries signal is examinable afterwards in
the by-method agreement figures.

## 8. The AIDev comparison set is small

The AIDev strict corpus is 35 cases. It is not a population-representative
estimate of real agent failures, and must not be described as one. The
comparison is between two small, differently-constructed samples.

## 9. Tests are not executed here

Every semantic check in this study is a property of the git history and the
diff. Running the tests would need each task's Docker image. The FAIL_TO_PASS
and PASS_TO_PASS lists are taken from the official validation the SWE-smith
authors ran; this study relies on that validation rather than repeating it.
