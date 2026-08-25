# ST-0601 V2 implementation preflight

## Story and objective

- Story: `ST-0601` — Raw artifact registry.
- Objective: retain original SHA-256, exact source provenance, a deterministic
  object reference, immutable versions, and tamper evidence in a maximum-safe
  recorded-local runtime.

## Inputs read

- Canonical integration design, decisions, open decisions, backlog Story, and
  unimplemented register.
- `FR-002`, `FR-004`, `TST-014`, `SEC-DATA-003`, `SEC-DATA-004`,
  `SEC-DATA-005`, `SEC-DATA-008`, and `SEC-INFRA-006`.
- ST-0202 local object-storage contract, wrapper/fixture tests, and its honest
  non-executed runtime boundary.
- ST-0308 persistence handoff/runtime contract, `ObjectArtifact` aggregate and
  repository, append-only and concurrency matrices, and relevant tests.
- ST-0502 `RawArchiveReceiptV2`, raw-read port, and recorded SQLite archive
  implementation.
- Existing ST-0601 V1 source-bound reference implementation and 51 tests.

## Ambiguities and safe defaults

- `OD-014` remains `HUMAN_DECISION_REQUIRED`. No retention class, duration,
  lifecycle, purge, or delete value is created. Automatic deletion is absent.
- ST-0202 has not completed its authenticated object-storage fixture. SQLite
  therefore represents only an owner-private recorded-local byte store and is
  never described as S3, SeaweedFS, Object Lock, encryption, or remote-storage
  attestation.
- The ST-0308 canonical `ObjectArtifact` aggregate requires a retention class.
  This V2 runtime reuses its nominal artifact ID and kind vocabulary but does
  not fabricate that required value or write through the production-oriented
  repository port.

## Planned owned files

- Additive V2 Domain, inward ports, application service, recorded source, and
  owner-private SQLite adapter under `python/raos/**`.
- Versioned contract and deterministic generated contract IR under
  `changes/st-0601/**`.
- Owner generator `scripts/build_st0601_artifact_registry_runtime.py`.
- Focused runtime, recovery, concurrency, integrity, schema, hostile-path,
  failure-isolation, and generation tests under `tests/st0601/**`.

## Tests

- Preserve the 51 V1 tests.
- Exercise put/get/version/readback, exact ST-0502 receipt binding,
  deterministic IDs/references, schema and hash chain, restart, idempotency,
  CAS concurrency, known rollback, ambiguous commit recovery, tamper, private
  path/mode/symlink/hardlink defenses, denied network, and regular closed
  exception traceback/context-manager propagation.
- Run owner generation/check, focused pytest, dependency regressions, Ruff,
  strict mypy, target Pyright, compile/import, focused secret scan, and
  `git diff --check`.

## Out of scope

- Credentials, live provider calls, real S3/SeaweedFS, remote storage,
  retention enforcement, delete/purge/lifecycle/export, public API, media,
  publication, staging, release, Production, and formal TST-014 evidence.
