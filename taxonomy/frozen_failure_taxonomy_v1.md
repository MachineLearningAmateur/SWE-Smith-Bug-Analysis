# AIDev failure taxonomy — FROZEN v1

- **Taxonomy version:** aidev_failure_taxonomy_v1
- **Freeze date:** 2026-08-29
- **Frozen by:** review decision of the project owner ("Drop 1, accept 2,
  adopt 3") applied to the proposal in `family_mapping_analysis.md`.
- **Repository state at freeze:** commit `7e2a866` (the commit that
  introduces this file is the freeze commit and immediately follows it).
- **Canonical machine-readable mapping:**
  `analysis/taxonomy/proposed_pattern_families.yaml`
  SHA-256 `1ce7232047437f87e7116d84b369e4f820e854481cbc744faf3b1d4c1af60985`

This exact version is the taxonomy to be used by the later SSR/SWE-smith
review pipeline. **After this freeze, the taxonomy must not be modified
based on what SSR bugs look like. Any change requires a new version
(v2, with its own freeze record).** No SSR/SWE-smith data was inspected or
used at any point in the derivation of this taxonomy.

## Source provenance (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `reviews/codex/review_results.jsonl` | `bec4769de6d5e3ed8f9dbd0acf51cf83f526c8079c4fe2076db7151c76e1b6b9` |
| `reviews/claude/review_results.jsonl` | `02957aef0de14dbb28e3b9b468693db508281da3a03a2ea175f31171e29cb402` |
| `docs/aidev_review_rubric.md` (frozen rubric) | `af8f12449c3977b91d867684806e81407ba2fcb1a8cbd0c32d835d1e0b6c2acf` |
| `data/evidence_snapshot_manifest.json` | `8cd98c33aa8c822333959ad75fad23210bc20a62d5b37306c53f1941a32fce42` |
| Family mapping YAML | `1ce7232047437f87e7116d84b369e4f820e854481cbc744faf3b1d4c1af60985` |

## Fine-grained patterns (unchanged from the frozen rubric)

The fine-grained labels are defined canonically in
`docs/aidev_review_rubric.md` and are reproduced here for the freeze record:

| Fine-grained label | Definition (rubric) |
|---|---|
| `masked_symptom_instead_of_fixing` | The patch suppresses, bypasses, or hides the observed symptom without correcting the underlying defect. |
| `false_premise_about_existing_code` | The patch relies on an incorrect assumption about repository behavior, APIs, types, language semantics, data contracts, or architecture. |
| `incomplete_change_propagation` | A change is made in one place but not propagated to other required callers, representations, files, branches, schemas, platforms, or related code paths. |
| `misdiagnosed_root_cause` | The agent identifies the wrong underlying cause and therefore changes the wrong component or logic. |
| `broke_existing_contract_or_behavior` | The proposed fix violates or regresses behavior that the repository already promises or relies on. |
| `disproportionate_or_duplicative_solution` | The patch adds unnecessary, duplicated, or overly broad implementation relative to the defect, and that excess causes or constitutes the technical problem. |
| `vacuous_verification` | The agent's claimed verification does not test the behavior needed to establish the fix. |
| `violated_project_constraint_or_convention` | The implementation conflicts with a documented or established repository-specific constraint, invariant, architectural rule, compatibility target, or required convention in a technically meaningful way. |
| `unverified_trial_and_error` | The chronology shows repeated speculative implementation changes without validation of the underlying hypothesis. |
| `wrong_baseline_or_branch` | The implementation targets the wrong repository state, branch, version, or baseline, making the fix inappropriate. |
| `OTHER_TECHNICAL_PATTERN` | Concrete technical failure exists but no defined pattern fits (described in `proposed_other_pattern`). |
| `UNASSIGNED` | No technical pattern (non-technical outcomes); maps to no family. |

Fine-grained labels are **preserved** in every derived dataset alongside the
family columns. Families never replace them.

## Broad families and mapping

| Family | Members | Definition |
|---|---|---|
| REPOSITORY_UNDERSTANDING | false_premise_about_existing_code, misdiagnosed_root_cause, masked_symptom_instead_of_fixing | The repair is grounded in an incorrect model of the existing code or defect — a factually wrong premise, a wrong root-cause diagnosis, or the symptom-suppressing patch such a misunderstanding produces. |
| BROKEN_CONTRACT | broke_existing_contract_or_behavior | The change violates or regresses behavior the repository already promises. |
| CONSTRAINT_VIOLATION | violated_project_constraint_or_convention | The change conflicts with an explicit project constraint, invariant, or convention. |
| INCOMPLETE_PROPAGATION | incomplete_change_propagation | The change is not propagated to all required locations. |
| VACUOUS_VERIFICATION | vacuous_verification | Claimed verification does not test the behavior needed to establish the fix. |
| UNVERIFIED_TRIAL_AND_ERROR | unverified_trial_and_error | Repeated speculative changes without validation of the hypothesis. |
| SOLUTION_SHAPE | disproportionate_or_duplicative_solution | The excess or duplication of the solution constitutes the problem. |
| BASELINE_STATE | wrong_baseline_or_branch | The change targets the wrong repository state, branch, or version. |
| OTHER | OTHER_TECHNICAL_PATTERN | Technical failure fitting no defined pattern. |

## Decision rules

1. **One family per case, derived deterministically** from the reviewer's
   fine-grained label via the mapping above. Reviewers are never asked to
   re-classify; families are computed, not judged.
2. **Code-state precedence (adopted at freeze; applies to future reviews
   only):** when the evidence supports both a code-state pattern and a
   verification-process pattern (`vacuous_verification`,
   `unverified_trial_and_error`), the reviewer assigns the code-state
   pattern as `failure_pattern`; the verification problem is recorded via
   `failure_scope` and `verification_level`. This rule was **not** applied
   retroactively to the sealed AIDev reviews.
3. **UNASSIGNED maps to no family** and is excluded from pattern agreement
   statistics.
4. **Code-state consensus rule (dataset eligibility):** a case enters the
   primary bug-state comparison only if both reviewers found
   technical-defect evidence (outcome ∈ {TECHNICAL_FAILURE_EVIDENCE,
   MERGED_AFTER_HUMAN_CORRECTION}) and both scopes are in
   {CODE_STATE, BOTH}. CODE_STATE vs BOTH is compatible; REPAIR_PROCESS or
   UNKNOWN on either side excludes the case from the primary set.
5. **Family disagreements are never forced into consensus.** Cases whose
   families disagree stay out of the strict primary corpus and remain in
   the broader consensus code-state dataset.

## Exclusions

- The `evidence_overstated` audit field exhibited systematic reviewer
  interpretation divergence and was excluded from subsequent analyses
  (Codex 51 YES / 31 NO / 18 UNCLEAR vs Claude 100 NO). Preserved verbatim
  for provenance only.
- `outcome_confidence`, `pattern_confidence`, `evidence_strength` are
  descriptive only; the reviewers used the scales differently and the values
  are not inclusion criteria. `verification_level` is the preferred
  externally interpretable provenance field.
- The 15 disputed technical-defect cases and the 3 non-code-state consensus
  cases (018, 019, 092) are excluded from the primary corpus and preserved
  for sensitivity analysis.

## Rationale for merges (full accounting in `family_mapping_analysis.md`)

- **The single adopted merge, REPOSITORY_UNDERSTANDING,** carries the
  strongest empirical support: 5 of the 18 fine-grained disagreements lie
  inside it, including the two most frequent pairs (false_premise ↔
  masked_symptom, ×2; misdiagnosed ↔ masked_symptom, ×2). Conceptually the
  three labels describe cause and effect of one failure mode.
- **The proposed CONTRACT_VIOLATION merge was dropped at review:** it rested
  on a single observed pair (case 001) and failed the repeated-disagreement
  criterion. `broke_existing_contract_or_behavior` and
  `violated_project_constraint_or_convention` remain separate families.
- **Rejected merges:** REPAIR_VERIFICATION (0 observed confusions between
  its members); `incomplete_change_propagation` into a consistency family
  (0 confusions with contract/constraint labels); any merge across the
  process/code-state boundary (handled by decision rule 2 instead).

## Agreement statistics (n = 49 cases with a pattern from both reviewers)

| Level | Exact agreement | Cohen's κ |
|---|---:|---:|
| Fine-grained labels | 31/49 (63.3%) | 0.5828 |
| **Frozen v1 families** | **36/49 (73.5%)** | **0.6575** |

The mapping resolves 5 of 18 fine-grained disagreements. The 13 remaining
disagreement cases are 001, 004, 016, 017, 018, 022, 023, 027, 028, 048,
049, 050, 067 (8 process-vs-code-state facet conflicts, 5 diffuse one-off
pairs); listed with labels in
`analysis/dual_review/pattern_family_disagreements.csv`. Family-level
agreement is an in-sample estimate: it is computed on the same data that
motivated the mapping.

## Resulting corpora

| Dataset | N |
|---|---:|
| `aidev_consensus_technical_cases.parquet` (BOTH_YES) | 51 |
| `aidev_consensus_code_state_cases.parquet` (rule 4) | 48 |
| `aidev_rq1_primary_cases.parquet` (strict: rule 4 + family consensus) | 35 |

Strict-corpus family distribution: REPOSITORY_UNDERSTANDING 16,
INCOMPLETE_PROPAGATION 5, CONSTRAINT_VIOLATION 5, UNVERIFIED_TRIAL_AND_ERROR
3, BASELINE_STATE 2, BROKEN_CONTRACT 2, SOLUTION_SHAPE 2.
