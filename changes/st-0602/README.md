# ST-0602 fact extraction and validation reference plan

## Classification

The V1 reference-plan slice is a
`SOURCE_DERIVED_NON_EXECUTABLE_FACT_EXTRACTION_VALIDATION_REFERENCE_PLAN`.
It is a local, interface-only projection of the currently reviewable ST-0602
boundary. It is not a Fact service, extractor, validator, persistence adapter,
job, event producer, manual-review workflow, or runtime implementation.

The generated document remains `LOCAL_IMPLEMENTATION_CANDIDATE`,
`NOT_READY`, non-executable, and ineligible for Production. ST-0602 acceptance
is false and the canonical Story remains `NOT_STARTED` / `NOT_EXECUTED`.

## Source boundary

The plan binds the exact committed bytes of the legacy V1 predecessor files.
The cited commits also contain additive V2 runtimes, but those V2 files do not
enter this non-executable V1 projection:

- The legacy V1 files from ST-0601 source commit
  `38ac757b814c24c913031485a78bbf7d2206f2a5` provide only a source-bound,
  recorded, non-attesting artifact-registry reference seam. They do not
  provide a real artifact, source snapshot, storage round trip, immutability
  attestation, or persistence boundary to this V1 plan.
- The legacy V1 files from ST-0503 source commit
  `80162f932738f9c3854ff012ae8e488275f7e1f5` provide only lossless,
  provenance-preserving normalization drafts. They do not provide an
  authoritative subject identity or confidence value to this V1 plan.

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

## V2 maximum-safe recorded-local runtime

The additive V2 slice implements the local ST-0602 code boundary without
changing the V1 reference plan into execution evidence. It consumes only the
exact `ArtifactReadbackV2` committed by ST-0601 and the exact
`PersistedCatalogNormalizationV2` committed by ST-0503. Before extraction it
revalidates the artifact record and receipt provenance, request/page/version,
logical key, observed time, raw bytes and hash, source snapshot, normalization
batch/version/hash-chain material, and normalized outbox binding.

V2 emits only exact structural OFFER Facts for `PRICE_JPY`,
`AVAILABILITY_PROVIDER_FLAG`, and `POSTAGE_INCLUDED_PROVIDER_FLAG`. Price is an
integer decimal with `JPY` and `ja-JP`; the provider flags are booleans with no
unit or locale. Every Fact is `ASSERTED`, has exactly one typed value, uses a
deterministic `FCT-…` display ID, and binds a JSON pointer to the exact ST-0503
observation ordinal and kind. The ST-0503 affiliate-link observation is not a
Fact and raw URLs or provider text are not included in V2 persistence or
generated material.

OD-006 is still unresolved. The exact stable OFFER ID is the only Fact subject;
there are no PRODUCT Facts or canonical product IDs. Every result remains
`HUMAN_REVIEW` / `NOT_READY` and requires manual review, but V2 has no capability
to make a manual-review decision.

The fixed confidence `1.0000` is extraction fidelity only. Its separate basis
is `EXACT_STRUCTURAL_EXTRACTION_NOT_TRUTH_ATTESTATION`; it does not copy or
invent provider truth confidence. Validation records keep truth
`NOT_ATTESTED` and publication readiness `NOT_READY`.

The owner-private SQLite adapter atomically appends the Fact batch, validation
records, exact `jp.raos.evidence.facts_extracted.v1` undelivered outbox record,
idempotency journal, CAS state, and hash-chain entry. It distinguishes a newly
`O_EXCL`-created database from a pre-existing empty or partial database, pins
the live inode, requires directory mode `0700`, database mode `0600`, and one
hard link, and validates exact schema/inventory plus process-lifetime monotonic
head/count. Commit-before/after ambiguity, restart, concurrency, payload hash
conflicts, immutable rows, and tamper are fail-closed. No cross-restart rollback
anchor is claimed.

The V2 runtime and adapter expose no provider, network, browser, AI/model,
tool, review-decision, publication, recommendation, ranking, revenue, export,
retention, staging, release, or Production capability. All external, provider,
publication, and AI action counts are exact integer zero.

Generate and verify the additive V2 projection only through its owner:

```text
python scripts/build_st0602_fact_extraction_runtime.py
python scripts/build_st0602_fact_extraction_runtime.py --check
```

The V2 contract, recorded synthetic fixture, generated report, and manifest are
local implementation evidence only. Formal TST-005/TST-007, hosted CI, live
provider, staging, release, and Production remain `NOT_EXECUTED`.
