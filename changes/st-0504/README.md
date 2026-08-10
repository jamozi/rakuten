# ST-0504 — product identity Human Review reference plan

Classification:
`SOURCE_DERIVED_NON_EXECUTABLE_PRODUCT_IDENTITY_HUMAN_REVIEW_REFERENCE_PLAN`

This implementation-first slice is a partial, non-authoritative, local-only,
non-executable reference plan. It preserves the blocking OD-006 safe default:
product identity must not be merged automatically, and ambiguous candidates
require Human Review. It is an interface projection, not an identity decision,
review record, approval, runtime implementation, or formal test result.

## Closed reference boundary

- The plan binds the exact committed ST-0503 lossless normalization slice at
  commit `b61d4dd83b87495dfd672bdf8960dc3b1ff29d79` and all nine committed owner
  artifacts by SHA-256.
- ST-0503 supplies only provenance-preserving candidate drafts in recorded,
  lossless structural mode. It supplies no product identity, grouping,
  canonical product, confidence, approval, repository, or persistence result.
- OD-006 remains `EXTERNAL_EVIDENCE_REQUIRED` and blocking. No category rule,
  model/JAN/capacity/color/set rule, threshold, score, confidence, or default
  merge/split behavior is selected.
- Automatic merge and automatic split are disabled. Human Review is required,
  but no reviewer, actor, role, queue, route, assignment, event, SLA, approval,
  decision, membership, merge, split, supersession, or history record exists.
- Candidate records and counts are empty or `null` because this builder does
  not execute ST-0503 or select a synthetic fixture. Empty arrays mean no
  configuration or evidence, not zero candidates or completed reviews.
- Repository, database, provider, live runtime, queue, event, review,
  persistence, and external actions are absent or `NOT_EXECUTED`; every action
  count is an exact integer zero.

The generated JSON is a deterministic reviewable plan derived from fixed
canonical and predecessor bytes. It cannot execute a rule engine, enqueue a
review, assign a person, create or supersede an identity decision, persist a
membership, or call an external system.

## Completion boundary

Story acceptance remains false. The canonical ST-0504 implementation status
remains `NOT_STARTED`, and verification remains `NOT_EXECUTED`. Local builder
and pytest results do not satisfy TST-007 or TST-020 and do not establish Human
Review execution, identity correctness, decision history, runtime readiness,
staging, release, or Production eligibility.

## Owner generation

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0504_product_identity_human_review_reference_plan.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st0504_product_identity_human_review_reference_plan.py \
  --check
```
