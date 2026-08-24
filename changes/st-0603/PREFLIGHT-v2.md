# ST-0603 V2 local implementation preflight

- Story: `ST-0603` — detect exact, overlapping conflicts between exact durable
  ST-0602 typed Fact batches and append unresolved review-queue records.
- Read inputs: root and Canonical implementation protocols, the ST-0603 and
  ST-0602 backlog rows, FR-008, TST-007/TST-020, the claim-evidence conflict
  policy, EVD-004 screen and API records, SEC-DATA-003/004/005/007,
  SEC-AI-001/003/007, THR-009/011/015/017, every V1 ST-0603 owner artifact and
  test, and the exact ST-0602 V2 contract, fixture, generator, layered runtime,
  persistence adapter, and hostile tests.
- Conflict policy: exact subject type/id and predicate, overlapping validity
  windows, compatible exact unit/locale, and differing exact typed values form
  an unresolved conflict. Equal values and disjoint windows do not. Unit or
  locale incompatibility is never converted and is routed explicitly to human
  review when encountered.
- Review policy: records remain `UNRESOLVED`, `HUMAN_REVIEW`, and `NOT_READY`.
  The exact content-policy key `source_conflict` and
  `silent_resolution_forbidden: true` are retained. No winner, tolerance,
  source-authority preference, Unknown/Claim, reviewer assignment, or
  resolution capability is implemented.
- Persistence: additive owner-private DEV/CI-only SQLite with exclusive-create
  initialization, exact STRICT/FK/schema/append-only inventory, descriptor and
  inode checks, canonical payload validation, an atomic scan/conflict/queue/
  outbox/journal/CAS unit, idempotency, hash chaining, commit-ambiguity
  recovery, and process-lifetime monotonic head/count checks.
- Planned owned files: additive V2 domain, port, application service, SQLite
  adapter, closed JSON contract and recorded fixture, deterministic owner
  generator and generated report/manifest, Story-local tests, completion
  record, and a V2 README section. V1 projection semantics stay unchanged.
- Local checks: V1 and V2 suites separately and combined, ST-0602 regression,
  both owner generators/no-write checks, Ruff, strict mypy, target Pyright,
  compile/import, denied-network, Story-local secret/scope checks, and
  `git diff --check`.
- Out of scope: the UI screen EVD-004, the unrelated API operation EVD-004,
  PostgreSQL/formal test evidence, cross-restart external rollback anchoring,
  AI/provider/network/credential use, publication, recommendation, ranking,
  revenue, human resolution, event delivery, staging, release, and Production.
