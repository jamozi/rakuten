# ST-0401 persistence hardening preflight (2026-08-25)

## Story and objective

- Story: `ST-0401` — OIDC adapter and admin login.
- Objective: preserve the provider-neutral, development-only authentication
  boundary while making its recorded SQLite evidence store fail closed against
  replacement, rollback, non-canonical rows, schema drift, partial mutation,
  and ambiguous commit recovery.

## Inputs read before implementation

- Root, canonical, and Codex `AGENTS.md` files and
  `RAOS_07_integration_design_v1.0.md`.
- Canonical decisions, open decisions, `ST-0103`, `ST-0204`, and the complete
  `ST-0401` backlog entry.
- `RAOS-SEC-001`, the IAM controls and threat entries, `RAOS-UI-001`, the auth
  screens/slices, and `TST-012`, `TST-022`, and `TST-026`.
- The ST-0204 configuration/secret-reference boundary and the ST-0308 local
  transaction contract.
- Every current ST-0401 source, owner-generator, contract, generated artifact,
  completion record, and test. The isolated baseline is `64 passed`.

## Ambiguities and safe decisions

- `OD-010` remains `HUMAN_DECISION_REQUIRED`. No provider, issuer/client,
  credential lifecycle, browser delivery, external callback, or Production
  activation is selected.
- SQLite remains an owner-private recorded local adapter, not a migration or
  Production database authority.
- A process-local validated snapshot can detect rollback or replacement only
  while that process remains alive. Without an external trusted anchor, a new
  process cannot prove that an otherwise valid database is an older snapshot;
  this limitation remains explicit.
- A pre-existing database file, including an empty mode-0600 file, is not
  creation authority. Only the exact file created by this adapter may be
  initialized.

## Planned Story-owned changes

- Replace permissive initialization with created-only exact schema V2 setup,
  strict tables, foreign keys, append-only/transition triggers, and exact
  schema/PRAGMA validation.
- Pin the database inode for each repository instance and retain a process-local
  validated count/head/prefix anchor to reject detected replacement or rollback.
- Bind every durable mutation to canonical command intent/result records and a
  linear hash chain; verify all stored material on every transaction boundary.
- Classify commit ambiguity only after a commit was actually attempted and
  recover rotation only from its exact durable command record without replay.
- Snapshot collaborator inputs/outputs at the application and adapter boundary,
  and enforce an exact integer-zero external-action count for the recorded fake.
- Add hostile, corruption, concurrency, recovery, canonical encoding, and
  collaborator-mutation tests; update the contract, README, completion evidence,
  owner generator, and generated outputs through the owner command.
- No canonical/imported document or generated output will be hand-edited.

## Verification plan

- Full isolated `tests/st0401`, including legacy and new hostile tests.
- Directly affected isolated ST-0402, ST-0403, and ST-1405 regressions.
- Owner generation and read-only `--check`.
- Python import/compile, Ruff check/format, strict mypy, focused Pyright,
  denied-network execution, focused secret/scope checks, and `git diff --check`.

## Out of scope

- Live OIDC/provider calls, credentials, provider SDKs, browser/cookie/bearer
  policy, external HTTP route registration, staging, publication, release,
  deployment, Production data, canonical status `APPLY`, and formal test claims.
