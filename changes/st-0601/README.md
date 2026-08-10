# ST-0601 — source-bound artifact registry reference plan

Classification: `SOURCE_BOUND_RECORDED_NON_ATTESTING_ARTIFACT_REGISTRY_REFERENCE_PLAN`

This implementation-first slice is partial, non-authoritative, local-only, and
non-attesting. It compares one declared `raw_provider_response` provenance
candidate with one immutable synthetic observation and produces a reviewable
reference plan. It is not an artifact registry, persistence implementation,
object-storage adapter, or verification result.

## Closed behavior

- The domain preserves the canonical ArtifactKind vocabulary, but the
  application accepts only `raw_provider_response` with the inert
  `REFERENCE_PLAN_ONLY` intent.
- A candidate contains a lowercase SHA-256, source, exact UTC time,
  parameter-free lowercase content type, exact byte size, and a logical
  `s3`/`raos-raw` location with a safe relative key and opaque version ID.
  Its compact sorted UTF-8 JSON and fingerprint are deterministic.
- The recorded fixture computes its observation from bounded synthetic bytes
  during construction, then discards those bytes. It retains and returns only
  immutable metadata. Duplicate bucket/key/version or candidate fingerprints
  are rejected.
- The application calls the single `observe(candidate)` port exactly once. It
  performs no fetch, HEAD, PUT, GET, read, write, retry, repair, fallback, or
  round trip. It compares the exact candidate fingerprint, kind, source, UTC
  time, content type, size, digest, bucket/key, and opaque version.
- A complete recorded match yields only `NOT_READY / RECORDED_MATCH`, with the
  exact blockers `RETENTION_UNRESOLVED`, `OBJECT_STORAGE_NOT_EXECUTED`,
  `IMMUTABILITY_NOT_ATTESTED`, and `PERSISTENCE_BOUNDARY_UNAVAILABLE`.
- Any provenance mismatch yields only `REJECTED / TAMPER_DETECTED`. The model
  has no `READY`, `REGISTERED`, `STORED`, `VERIFIED`, or `PASS` state.
- Every storage, read, write, round-trip, attestation, and persistence field is
  `NOT_EXECUTED`. Artifact ID, ArtifactRef, retention value, and actions are
  always absent. No identifier or retention policy is allocated or inferred.
- Failures and values are redacted and non-serializable. Rejected input and
  synthetic bytes are not echoed, exposed, snapshotted, or placed in history.

The only port capability is observation. There is no storage client, path,
credential, URI, provider SDK, file/network access, database, repository,
unit-of-work, transaction, registration, list, save, or deletion surface. The
adapter is restricted to explicit `ENV-DEV` or `ENV-CI` recorded fixtures and
uses no environment lookup, clock, randomness, provider, or external action.

## Authority and completion boundary

ST-0202 and ST-0308 remain read-only semantic dependencies. OD-014 retention is
still unresolved, ST-0202 storage has not run, immutability has not been
attested, and the ST-0308 persistence boundary is not supplied by this slice.
Consequently, even matching local metadata cannot authorize registration or
prove that an object exists, is readable, round-trips, is immutable, or was
persisted.

Story acceptance remains false. Formal validation, TST evidence, live object
storage, persistence, staging, release, and Production remain `NOT_EXECUTED`
and `NOT_AUTHORIZED`. Local pytest is development evidence only and is not an
attestation, integrity proof, or release-eligibility claim.

## Focused local check

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  pytest -q tests/st0601
```
