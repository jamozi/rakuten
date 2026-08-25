# ST-0604 Source Packet lifecycle reference plan

## Classification

This change is a
`SOURCE_DERIVED_NON_EXECUTABLE_SOURCE_PACKET_LIFECYCLE_REFERENCE_PLAN`. It is a
local, non-executable projection of the maximum safe ST-0604 boundary. It is
not a Source Packet model or service, lifecycle engine, API, repository,
database adapter, job, event producer, artifact binding, approval workflow, or
generation implementation.

The generated document remains `LOCAL_IMPLEMENTATION_CANDIDATE`, `NOT_READY`,
non-executable, and ineligible for Production. Story acceptance is false and
the canonical Story remains `NOT_STARTED` / `NOT_EXECUTED`.

## Source boundary

The plan binds exact path inventories derived from the committed feature
commits themselves:

- ST-0602 `806b978803cbc78392117cbc31015db19ea09a74` contributes only an
  interface-only Fact extraction reference plan with no Facts and a
  `NOT_READY` decision.
- ST-0603 `4f4285f0385a14b83e027e9c4527c17b8966bb70` contributes only a
  non-executable conflict-review reference plan with no Facts, comparisons,
  conflicts, findings, queue records, or resolutions and a `NOT_READY`
  decision.
- ST-0403 `095046c752595bea3235caf2e3a653fd9383882e` contributes only its
  recorded development authorization seam. It is deny-default and supplies no
  live or Production approval.

Empty predecessor projections are unavailable input, not evidence that zero
Facts, conflicts, or lifecycle records exist.

## Closed projection

The owner contract keeps packet, version, and job vocabularies in separate
descriptive namespaces. It defines no inferred mapping among them. All packet,
version, job, reviewer, authorization, artifact, and content-hash identifiers
or selections are null. All runtime collections are empty and their counts are
null rather than zero.

Lifecycle transition and vocabulary mapping remain unavailable. Approval is
false and generation is not permitted. Packet, version, transition, mapping,
review, authorization, artifact, repository, database, job, event, API,
approval, generation, and external execution remain `NOT_EXECUTED`, with exact
action counts of zero.

Canonical packet, version, job, approval, and security material is descriptive
context only. It does not create a runtime schema binding, infer a status
mapping, authorize a transition, approve a packet, or permit generation.

## Blockers preserved

The plan remains blocked by unavailable Facts and conflict findings, absent
cross-namespace lifecycle mappings and transitions, no reviewer or granted
authorization, and no artifact binding. No synthetic packet, version, job,
status, transition, mapping, reviewer, approval, artifact, hash, or generation
result is invented to cross those gaps.

## Generation

Generate only through the owner builder:

```text
python scripts/build_st0604_source_packet_lifecycle_reference_plan.py
python scripts/build_st0604_source_packet_lifecycle_reference_plan.py --check
```

The generated JSON is a plan projection, not packet creation, lifecycle
execution, review, approval, artifact creation, formal validation, staging,
release, live, or Production evidence.
