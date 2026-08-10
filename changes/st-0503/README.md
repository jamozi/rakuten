# ST-0503 — recorded lossless catalog normalization seam

Classification:
`MAXIMUM_SAFE_LOCAL_RECORDED_LOSSLESS_CATALOG_NORMALIZATION_SEAM`

This implementation-first slice is partial, non-authoritative, local-only,
non-persistent, and runtime-ineligible. It projects one exact synthetic
ST-0502 `CONTRACT_TEST` result into immutable structural drafts. It does not
implement catalog identity, grouping, persistence, provider access, or the
full ST-0503 acceptance boundary.

## Closed implementation boundary

- The command contains one exact ST-0502 command and result, a caller-supplied
  nonzero synthetic ingestion-request UUID and UTC ingestion time, the fixed
  `RECORDED_LOSSLESS_STRUCTURAL_V1` normalizer, the expected raw-response
  SHA-256, and a deterministic compact-JSON fingerprint.
- Only ST-0502 `RECORDED_TEST_ONLY`, page one, `CONTRACT_TEST`, non-live,
  storage-`NOT_EXECUTED`, persistence-`NOT_EXECUTED` results whose receipt URI
  is `None` are accepted. Provider, API, endpoint, request, raw receipt, digest,
  byte size, observation time, and ingestion time remain source-bound.
- Each source item produces one candidate, offer, price, availability, and
  review-aggregate draft in source order. The item name and image order are
  preserved exactly. Name normalization is only `LOSSLESS_PASSTHROUGH`.
- Model-like or JAN-like text stays inert source text. The seam allocates no
  internal candidate, product, shop, genre, offer, snapshot, job, or event ID.
  It does not infer model numbers, JAN codes, external offer IDs, identity,
  grouping, canonical products, status, membership, merges, or splits.
- Item price, provider availability, and review aggregate values are preserved
  as recorded facts. Tax, shipping, points, availability semantics, status,
  confidence, and review bodies remain unset. Affiliate URL/rate data is not
  projected or used for a decision.
- Every source reference states `VALIDATED_RECORDED_RECEIPT_ONLY`, source
  snapshot `NOT_AVAILABLE`, confidence `SOURCE_ABSENT`, repository `ABSENT`,
  database `NOT_EXECUTED`, and persistence false. This is not storage,
  persistence, or source-snapshot evidence.
- The batch is `RECORDED_TEST_ONLY` and `LOSSLESS_STRUCTURAL_ONLY`; identity is
  `REVIEW_REQUIRED`, the decision is `NOT_READY`, and empty identity/grouping
  arrays mean no decision—not zero confidence.

The inward port exposes only `normalize(command) -> batch`. The application
accepts only `ENV-DEV` or `ENV-CI`, calls the collaborator exactly once, never
retries or returns a partial result, and validates the entire lossless outcome.
The recorded adapter is a bounded immutable exact-fixture lookup; it has no
repository, unit-of-work, database, filesystem, network, provider, environment
lookup, mutable history, or lifecycle surface. Failures are stable, redacted,
non-pickleable, and do not echo rejected source data.

## Authority and completion boundary

ST-0502 remains the read-only recorded-provider boundary. This slice does not
map ST-0502 output into a durable catalog, select a business identity policy,
or claim current product/offer state. Story acceptance remains false.

Formal TST-005/TST-007/TST-008, repository and database integration, jobs,
events, live-provider execution, hosted CI, staging, release, and Production
remain `NOT_EXECUTED` and are not authorized by local tests.

## Focused local check

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  pytest -q tests/st0503
```
