# ST-0602 fact extraction and validation reference plan

## Classification

This change is a
`SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN`.
It is a local, interface-only projection of the currently reviewable ST-0602
boundary. It is not a Fact service, extractor, validator, persistence adapter,
job, event producer, manual-review workflow, or runtime implementation.

The generated document remains `LOCAL_IMPLEMENTATION_CANDIDATE`,
`NOT_READY`, non-executable, and ineligible for Production. ST-0602 acceptance
is false and the canonical Story remains `NOT_STARTED` / `NOT_EXECUTED`.

## Source boundary

The plan binds the exact committed bytes of the approved local predecessor
slices:

- ST-0601 commit `2653f1a3f78172576818b032b0bd34b54360d9fb`
  provides only a source-bound, recorded, non-attesting artifact-registry
  reference seam. It does not provide a real artifact, source snapshot,
  storage round trip, immutability attestation, or persistence boundary.
- ST-0503 commit `b61d4dd83b87495dfd672bdf8960dc3b1ff29d79`
  provides only lossless, provenance-preserving normalization drafts. It does
  not provide an authoritative subject identity or confidence value.

Those limitations are preserved. A matching synthetic ST-0601 observation is
still `NOT_READY`; an ST-0503 normalization batch still requires identity
review and reports confidence as source-absent. Neither predecessor is treated
as extraction evidence.

## Closed projection

The authored YAML contains pins and safe defaults. The owner builder validates
those pins and projects a deterministic JSON reference plan plus manifest.
The projection keeps all unavailable Fact inputs unset:

- source snapshot, artifact, subject, predicate, unit, confidence, locator,
  extractor, and manual-review count are null or absent;
- facts, Fact IDs, derivations, validation records, and review records are
  empty;
- extraction, validation, manual review, repository, database, job, event,
  provider, and external actions are all `NOT_EXECUTED`, with exact action
  counts of zero.

Canonical Fact, job, event, test-suite, and security material is included only
as descriptive context. It does not select an extractor, create a schema
binding, authorize execution, or claim formal evidence.

## Blockers preserved

The plan remains blocked by the absence of a real attested artifact and source
snapshot, an authoritative subject, source-backed confidence, an extractor,
and a persistence boundary. No synthetic Fact, ID, derivation, locator,
confidence, reviewer, or execution result is invented to cross those gaps.

## Generation

Generate only through the owner builder:

```text
python scripts/build_st0602_fact_extraction_validation_reference_plan.py
python scripts/build_st0602_fact_extraction_validation_reference_plan.py --check
```

The generated JSON is a plan projection, not performed extraction,
validation, storage, manual-review, TST-005/TST-007, staging, release, live, or
Production evidence.
