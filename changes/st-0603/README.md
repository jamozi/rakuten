# ST-0603 Fact conflict review reference plan

## Classification

This change is a
`SOURCE_DERIVED_NONEXECUTABLE_FACT_CONFLICT_REVIEW_REFERENCE_PLAN`. It is a
local, non-executable projection of the maximum safe ST-0603 boundary. It is
not a conflict detector, comparator, tolerance policy, review queue,
resolution workflow, repository, database adapter, event producer, API, UI,
or runtime implementation.

The generated document remains `LOCAL_IMPLEMENTATION_CANDIDATE`, `NOT_READY`,
non-executable, and ineligible for Production. Story acceptance is false and
the canonical Story remains `NOT_STARTED` / `NOT_EXECUTED`.

## Source boundary

The plan binds the exact nine owned bytes of committed ST-0602 feature
`806b978803cbc78392117cbc31015db19ea09a74`. That predecessor supplies only a
source-derived, interface-only Fact extraction and validation reference plan.
Its Fact inputs are null, its Fact and Fact-ID projections are empty, and its
extraction, validation, repository, database, job, and event boundaries remain
`NOT_EXECUTED`.

An empty predecessor projection is not evidence that zero Facts or zero
conflicts exist. It supplies no comparison input and authorizes no conflict or
resolution result.

## Closed projection

The authored YAML contains immutable predecessor pins and safe defaults. The
owner builder validates those bytes and their critical semantics, then emits a
deterministic JSON plan plus manifest. The projection keeps:

- Facts, Fact IDs, comparisons, conflicts, findings, queue records, and
  resolutions empty;
- every associated count null rather than zero;
- rule, comparator, tolerance, source, value, severity, actor, queue, and
  resolution selections null;
- comparison, review-queue, resolution, repository, database, event, API, UI,
  and external execution `NOT_EXECUTED` with exact action counts of zero;
- automatic resolution disabled and silent resolution forbidden.

Canonical conflict-policy, EVD-004, and security material is descriptive
context only. It does not select a comparator, tolerance, severity, queue,
actor, or resolution policy, and it creates no runtime contract.

## Blockers preserved

The plan remains blocked because Fact input is unavailable and no comparator,
tolerance, severity rule, review queue, or resolution policy is selected. No
synthetic conflict, finding, severity, queue item, reviewer, resolution, or
execution result is invented to cross those gaps.

## Generation

Generate only through the owner builder:

```text
python scripts/build_st0603_fact_conflict_review_reference_plan.py
python scripts/build_st0603_fact_conflict_review_reference_plan.py --check
```

The generated JSON is a plan projection, not conflict detection, review,
resolution, persistence, formal validation, staging, release, live, or
Production evidence.
