# ST-0405 local SQLite audit hardening preflight

## Story and objective

- Story: `ST-0405` — Audit event service.
- Objective: harden the existing owner-private durable local audit writer so
  actor, reason, correlation, authorization provenance, and hash-chain records
  remain immutable and fail closed under hostile storage and collaborator
  behavior.

## Canonical and implementation inputs read

- Root and Canonical `AGENTS.md`, master readme, integration design, Canonical
  decisions, and all open decisions.
- ST-0405 backlog row and dependencies ST-0303/ST-0403; FR-020 and
  NFR-AUD-001; Canonical immutable-audit/data-minimization controls; role
  matrix; TST-011/TST-012 definitions; audit data/API design.
- Existing ST-0405 V1/V2 domain, ports, application, recorded adapters,
  contract, README, and complete isolated test suite.
- Integrated ST-0403 authorization and ST-1201 event-journal hardening
  patterns for created-only SQLite initialization, exact schemas, process
  prefix anchors, and commit recovery.

## Open decisions and safe boundary

- OD-014 remains unresolved. No retention period, deletion, purge, export, or
  automatic lifecycle behavior is added.
- OPS-012/view-audit remains disabled at the documented ST-0403
  `SITE_SCOPE_CONFLICT` boundary. The bounded correlation lookup remains an
  internal integrity tool only.
- A live store can detect named-file replacement and a valid older same-inode
  snapshot through its process-local identity/count/head/prefix anchor. A
  fresh process has no independent external durable anchor and therefore
  cannot claim rollback detection across process restart.
- SQLite append guards are local tamper-evident development controls. They do
  not substitute for Canonical PostgreSQL roles/grants or formal TST-011.

## Planned owned changes

- Harden created-only database initialization, descriptor-relative file
  checks, root/database identity pinning, fsync, exact connection PRAGMAs,
  `STRICT` tables, exact table/index/trigger/FK inventory, append-only guards,
  metadata CAS, and complete canonical/hash-chain verification.
- Classify commit exceptions as known rollback or unknown until exact
  read-only recovery, with no blind retry.
- Reconstruct collaborator values and require exact integer-zero external
  action counts before and after every V2 context/store/factory interaction.
- Update only ST-0405-owned contract/documentation/evidence and add hostile,
  tamper, concurrency, snapshot-rollback, and recovery tests.

## Planned verification

- Complete isolated ST-0405 suite plus repeated focused concurrency/recovery.
- Ruff lint/format, strict scoped mypy, targeted repository-locked Pyright,
  compile/import, denied-network, focused secret/sensitive-data scan, owned
  scope review, and `git diff --check`.
- Direct read-only downstream suites that bind or consume the ST-0405 seam;
  exact predecessor-hash drift will be reported without modifying downstream
  owner artifacts.

## Out of scope

- PostgreSQL migration/role execution, HTTP route activation, outward audit
  query/export, retention/deletion, provider/network/credential use, business
  mutation, publication, staging, release, and Production.
- Canonical status changes or formal/live TST evidence claims.
