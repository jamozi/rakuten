# ST-0605 Claim/evidence coverage reference plan

## Classification

This change is a
`SOURCE_DERIVED_NONEXECUTABLE_CLAIM_EVIDENCE_COVERAGE_REFERENCE_PLAN`. It is a
local, non-executable projection of the maximum safe ST-0605 boundary. It is
not a Claim service, coverage calculator, API, repository, database adapter,
job, event producer, or publication implementation.

The generated document remains `LOCAL_IMPLEMENTATION_CANDIDATE`, `NOT_READY`,
non-executable, and ineligible for Production. Story acceptance is false,
publication is forbidden, and the canonical Story remains `NOT_STARTED` /
`NOT_EXECUTED`.

## Source boundary

The plan binds exact path inventories and bytes derived from the committed
feature commits themselves:

- ST-0602 `806b978803cbc78392117cbc31015db19ea09a74` contributes an
  interface-only Fact extraction reference with no Facts or derivations and a
  `NOT_READY` decision.
- ST-0603 `4f4285f0385a14b83e027e9c4527c17b8966bb70` contributes a
  non-executable conflict-review reference with no comparisons, conflicts,
  findings, queue records, or resolutions and a `NOT_READY` decision.
- ST-0604 `89d8074951ce73a5c76ca55f0ea3b2c129559d81` contributes a
  non-executable lifecycle reference with no packets, versions, jobs,
  transitions, mappings, reviews, approvals, or artifacts. Approval and
  generation permission are false.

The executable recorded runtime is bound separately to ST-0604's current V2
contract. The historical V1 projection above remains intentionally
non-executable and is not treated as an approval receipt.

Empty predecessor projections are unavailable input, not evidence that the
runtime population is zero and not authority to pass a coverage gate.

## Closed vocabulary projection

The owner contract projects six source tiers and nine policy Claim types from
the Claim–Evidence policy. Persisted Claim types and criticalities, persisted
Claim–Fact link support types, and AI extraction criticalities and support
statuses remain separate descriptive namespaces. No cross-namespace mapping
is inferred, and the AI `claim_type` string is not promoted into an enum.

The 162-row matrix is the exact ordered `claim_evidence` slice `CT-0389`
through `CT-0550` from the canonical content test matrix. Its expected-result
distribution is preserved exactly: `PASS` 36, `FAIL` 63, `FAIL_BLOCKER` 54,
and `FAIL_OR_DEGRADE` 9. These are source-authored expected outcomes, not
runtime results. The projection does not authorize a tier, map a Claim type,
classify a link, calculate coverage, or create runtime data.

## Coverage boundary

The source policy requires a `1.0` ratio for major Claims and `0.95` for all
verifiable Claims. Those thresholds are descriptive policy inputs only. All
packet, article, Claim, Fact, link, source, citation, and conflict identifiers
are null; all runtime collections are empty; counts and observed ratios are
null. Coverage is unevaluable and both satisfaction selections are null.

A zero denominator never becomes a vacuous `0/0` pass. Publication remains
forbidden because Claims, Facts, links, citations, conflict state, vocabulary
mappings, source-tier eligibility, link outcome semantics, and the coverage
numerator rule are unavailable.

## Execution boundary

Claim creation, link creation, matrix evaluation, coverage calculation,
mapping, repository, database, job, event, API, publication, and external
execution remain `NOT_EXECUTED`, with exact action counts of zero. Canonical
policy, persisted-schema, AI-schema, and KPI material is descriptive context
only and creates no runtime contract or formal evidence.

## Generation

Generate only through the owner builder:

```text
python scripts/build_st0605_claim_evidence_coverage_reference_plan.py
python scripts/build_st0605_claim_evidence_coverage_reference_plan.py --check
```

The generated JSON is a reference plan, not Claim/evidence execution, a
coverage result, publication approval, formal validation, staging, release,
live, or Production evidence.
