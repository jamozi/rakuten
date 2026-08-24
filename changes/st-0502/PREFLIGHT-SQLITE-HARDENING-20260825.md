# ST-0502 SQLite hardening preflight — 2026-08-25

## Story and objective

- Story: `ST-0502` — recorded Rakuten Item Search adapter and raw archive.
- Objective: preserve the recorded/disabled, zero-external-action boundary while
  making the owner-private SQLite archive fail closed on unsafe initialization,
  replacement, rollback, schema drift, relational tampering, collaborator
  mutation, and ambiguous commit outcomes.

## Inputs read

- Root and Canonical `AGENTS.md`, Canonical master README, integration design,
  Canonical decisions, Open Decisions, and the ST-0502 backlog entry.
- ST-0502 design handoff, V2 runtime contract, synthetic fixture, generated
  projection, completion record, owner generator, layered runtime source, and
  the complete isolated Story test surface.
- Required `TST-014` and `TST-015` definitions and the relevant security
  boundaries: `SEC-APP-011`, `SEC-APP-013`, `SEC-DATA-003`, `SEC-DATA-004`,
  `SEC-DATA-005`, `THR-012`, `THR-015`, and `THR-017`.
- Read-only dependency boundaries for ST-0202, ST-0308, and ST-1404, plus the
  hardened ST-0601 and ST-0503 local SQLite patterns.

## Baseline and identified gaps

- Isolated baseline: `263 passed` in `tests/st0502`.
- The prior store initialized any pre-existing empty file, did not pin the
  database device/inode or a process-local monotonic history prefix, and used a
  schema-v1 model without immutable triggers or a complete mutation chain.
- JSON payloads were hash checked but not required to be the exact canonical
  bytes; persisted UUID and timestamp text accepted non-canonical forms.
- Commit recovery checked the result journal only, rather than recomputing the
  complete command/session/artifact/receipt/rate/result/chain relationship.
- Application calls did not consistently boundary-copy every provider/store
  argument, revalidate it after normal and exceptional returns, or check a
  store-side zero external-action counter around every call.

## Planned owned changes

- ST-0502 domain/port/application/recorded and SQLite adapter code only.
- ST-0502 schema-v2 contract, fixture/projection/manifest, README/completion
  evidence, owner generator, and isolated tests.
- Exact schema, append-only triggers, content and metadata hashes, command
  journal/history chain, process-local identity/monotonic anchors, exact commit
  recovery, canonical persisted encodings, and hostile collaborator checks.

## Planned verification

- Isolated V1/V2/combined ST-0502 tests and repeated two-writer stress.
- Owner generation, `--check`, and no-write verification.
- ST-0308 regression, compile/import, Ruff, mypy, Pyright, denied-network,
  focused secret/scope checks, and `git diff --check`.

## Out of scope

- Real Rakuten credentials or calls, ST-0202 cloud/object runtime, live worker
  activation, formal `TST-014`/`TST-015`, hosted CI, staging, release,
  publication, and Production remain `NOT_EXECUTED` with authority `NONE`.
- No claim is made for rollback detection across process restart without an
  independently durable external anchor.
