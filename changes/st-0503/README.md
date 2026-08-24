# ST-0503 — durable recorded catalog normalization runtime

Classification:
`MAXIMUM_SAFE_LOCAL_DURABLE_CATALOG_NORMALIZATION_RUNTIME`

The additive V2 runtime is maximum-safe `LOCAL_CODE_COMPLETE`. It consumes only
an exact successful page already persisted by the ST-0502 V2 owner-private
archive, revalidates the receipt/request/raw hash and reparses the raw bytes,
then atomically commits source snapshot, candidate, offer, observations,
outbox, command journal, catalog CAS, and hash-chain state to owner-private
SQLite. It has recorded and disabled source modes only and performs zero
external actions.

Every stable internal ID binds the fixed provider/API/normalizer version and
the exact provider item/shop/source receipt snapshot. Provider text and HTTPS
URLs remain explicitly untrusted data. Price, availability, postage, and the
affiliate URL are typed observations only; they are never a recommendation or
ranking surface. Affiliate rate, commission, EPC, RPM, profit, reward, review
body/aggregate, and provider confidence are excluded.

OD-006 remains unresolved. V2 always emits `HUMAN_REVIEW` / `NOT_READY`, empty
canonical-product and grouping decisions, no model/JAN extraction, no merge or
split, no canonical identity, and no provider-derived confidence shortcut.

The durable adapter initializes schema only when its constructor wins an
`O_CREAT|O_EXCL` create of a new regular `0600` database. A pre-existing empty,
partial, foreign, symlinked, hard-linked, or non-`0600` database is never
initialized or repaired. Exact table, autoindex, column, trigger, foreign-key,
and `STRICT` inventories are bound. Record tables are append-only by trigger;
the singleton state may move only through the runtime's transaction-local CAS.

Each open store pins the database device/inode and its last verified committed
count, head hash, and chain prefix. Identity is rechecked around every
connection and transaction, so path replacement, an older valid snapshot, and
same-inode rollback are rejected during that open process. There is deliberately
no claim that a fresh process can detect rollback to an older otherwise-valid
database without an external durable anchor.

Stored JSON bytes, UUIDs, UTC RFC3339 text, scalar columns, payload hashes,
result hashes, outbox, journal, and chain are reconstructed through the shared
domain and compared exactly. Collaborator arguments and returns are copied and
recomputed at both sides of each call, and source/store action counts must stay
exactly zero. A commit error is recovered only when a fresh verified read proves
the exact operation, command fingerprint, batch, event, result bytes, hashes,
and chain fully durable; missing, partial, conflicting, or ambiguous state stays
closed as `COMMIT_UNKNOWN`.

## V1 compatibility seam

The original 59-test process-local V1 seam remains unchanged for compatibility.
It is still non-persistent and runtime-ineligible. It projects one exact
synthetic ST-0502 `CONTRACT_TEST` result into immutable structural drafts and
does not implement catalog identity, grouping, provider access, or persistence.

### Closed V1 implementation boundary

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

ST-0502 remains the read-only recorded-provider/archive boundary. V2 records a
durable local normalization history but does not select a business identity
policy or claim a canonical/current product state. Local tests and generated
evidence do not change Canonical status.

Formal TST-005/TST-007/TST-008, repository and database integration, jobs,
PostgreSQL/formal database validation, event delivery workers, live-provider
execution, hosted CI, staging, release, and Production remain `NOT_EXECUTED`
and are not authorized by local tests.

## Focused local check

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  /home/minami/rakuten/.venv/bin/pytest -q tests/st0503

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python \
  /home/minami/rakuten/.venv/bin/python \
  scripts/build_st0503_catalog_normalization_runtime.py --check
```
