# ST-0402 persistence and collaborator hardening preflight (2026-08-25)

## Story and objective

- Story: `ST-0402` — MFA and step-up.
- Objective: preserve the factor-neutral, development-only critical-command
  step-up boundary while making its recorded lifecycle fail closed against
  pre-created/foreign storage, replacement, rollback, non-canonical rows,
  partial mutation, collaborator mutation, and ambiguous commit recovery.

## Inputs read before implementation

- Root, canonical, and Codex `AGENTS.md` files, the master README, integration
  design, canonical decisions, open decisions, and the complete `ST-0401` and
  `ST-0402` backlog entries.
- `RAOS-SEC-001`, `RAOS-UI-001`, and the complete TST-012, TST-022, and
  TST-026 catalog/evidence entries.
- The current hardened ST-0401 contract, provenance artifacts, completion
  evidence, authentication domain/application source, and recorded SQLite
  implementation.
- Every current ST-0402 domain, port, application, recorded/development/HTTP
  adapter, owner generator, contract, generated artifact, completion record,
  and test. The isolated baseline is `59 passed` plus two exact ST-0401
  dependency-pin generation failures.

## Ambiguities and safe decisions

- `OD-010` remains `HUMAN_DECISION_REQUIRED`. No factor, provider claim
  (`amr`/`acr`/`auth_time`), provider SDK, credential lifecycle, middleware,
  browser delivery, or Production freshness value is selected.
- SQLite remains an owner-private recorded local adapter, not a migration or
  Production database authority.
- A process-local validated command-history prefix can detect rollback and
  replacement only while that process remains alive. Without an external
  trusted anchor, a fresh process cannot prove that an otherwise valid
  database is an older snapshot; this limitation remains explicit.
- A pre-existing database file, including an empty owner-mode file, is not
  creation authority. Only the exact file created by this adapter may be
  initialized.

## Planned Story-owned changes

- Replace permissive `IF NOT EXISTS` initialization with created-only exact
  schema V2 setup, `STRICT` tables, foreign keys, exact PRAGMAs, append-only
  revision/command/audit tables, and guarded monotonic metadata transitions.
- Pin root/database identity and retain a process-local validated count/head/
  prefix anchor to reject detected replacement and rollback.
- Canonically bind every lifecycle revision to exact command intent/result and
  one linear SHA-256 command/audit chain; verify every stored byte,
  relationship, redundant field, state transition, and prefix on each
  transaction boundary.
- Classify commit ambiguity only after commit was actually attempted and
  recover only the exact durable command result without replay.
- Deep-detach and revalidate session, binding, challenge, receipt, grant,
  command, verifier, repository, and HTTP collaborator inputs/outputs. Require
  the recorded verifier/driver external-action count to be an exact integer
  zero before and after use.
- Add hostile, corruption, canonical encoding, replacement/rollback,
  concurrency, commit classification, recovery, and collaborator-mutation
  tests; update the contract, README, completion evidence, owner generator, and
  generated outputs through the owner command.
- No canonical/imported document or generated output will be hand-edited.

## Verification plan

- Full isolated `tests/st0402`, including new hostile and persistence tests.
- Directly affected isolated ST-0401, ST-0403, ST-0905, and ST-1405
  regressions where locally executable.
- Owner generation and read-only `--check`.
- Python import/compile, Ruff check/format, strict mypy, focused Pyright,
  denied-network execution, focused secret/scope checks, and
  `git diff --check`.

## Out of scope

- Live MFA/OIDC/provider calls, credentials, provider SDKs, external HTTP
  route or middleware registration, browser/Cookie/Bearer delivery, role
  authorization, critical-command execution, staging, publication, release,
  deployment, Production data, canonical status `APPLY`, and formal test
  claims.
