# ST-0308 design decision request

Status: `BLOCKED_PENDING_PRO_AND_HUMAN_APPROVAL`

Authority: `INFORMATIONAL_DECISION_REQUEST_ONLY`

This document is not a `DESIGN_HANDOFF_V1`, does not approve implementation,
and must not be passed to `implementation_worker` as implementation authority.
It packages the unresolved decisions that must be answered through a separately
authorized, visibly selected ChatGPT Web/Desktop Pro session, reconciled with
canonical precedence, and approved by a human. This packet authorizes neither
resume/resubmission of the existing failed run nor creation of a replacement
Pro run. Until the completed handoff has every required field and
`open_decisions: []`, ST-0308 remains blocked at the design boundary.

## Canonical facts already fixed

- Story: `ST-0308`, **Persistence ports and repositories**.
- Objective: implement Domain ports against the database.
- Declared dependencies: `ST-0304`, `ST-0105`.
- Declared deliverables: repositories and transaction boundary.
- Declared acceptance criterion: cross-module write rules.
- Required Suites: `TST-005`, `TST-008`.
- Architecture direction is `domain <- application <- ports <- adapters <- framework`.
- Domain code must not import SQLAlchemy, FastAPI, provider SDK, or framework types.
- Modules communicate through public Application Interfaces or Domain Events;
  code must not directly operate another module's Repository or table.
- One command transaction atomically covers Aggregate state, Version, Audit,
  Outbox Event, and Idempotency Record when those records change together.
- External API, LLM, Object Storage, and notification I/O do not run inside the
  database transaction.
- Outbox dispatch, lease, retry, and DLQ runtime remain owned by `ST-1404` and
  must not be implemented by ST-0308.
- ST-0105 owns generated contract bindings only; runtime Domain mappings and
  database persistence remain outside that Story.
- This request does not authorize a migration, schema, role, grant, RLS, or
  runtime change. Any current local implementation candidate used as design
  evidence must be reconciled explicitly and is not elevated to canonical or
  formal authority by this packet.

Canonical authority:

- `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md`
- `docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml` (`ST-0308`)
- `docs/canonical/08_codex/AGENTS.md`

Immutable imported design inputs, subject to canonical precedence:

- `docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md`
- `docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md`

Local implementation candidates requiring explicit reconciliation:

- `changes/st-0105/README.md`
- `changes/st-0304/contracts/domain-schema.v1.yaml`
- `changes/st-0306/contracts/database-roles-grants.v1.yaml`

ST-0304 is a declared ST-0308 dependency, but its local contract remains
candidate evidence with formal verification not executed. ST-0306 is not a
declared ST-0308 dependency; its local grants contract may describe current
worktree behavior but must not be silently promoted to a prerequisite or
formal/canonical authority.

## Required decisions

### ST0308-D1 — Repository and aggregate inventory

Select the exact aggregate and schema inventory for this Story.

1. Limit the first implementation to `ops`, `iam`, and the schemas introduced
   by ST-0304. This stays closest to the declared dependency cut but leaves
   later schemas for subsequent Stories.
2. Cover all currently materialized domain schemas. This provides a broader
   common persistence foundation but materially expands scope and implicitly
   elevates later schema Stories to prerequisites.
3. Implement only a generic Unit of Work. This is insufficient by itself for
   the declared `repositories` deliverable and cannot complete ST-0308.

Required answer: the exact repository names, owned aggregate roots, schemas,
tables, and explicitly excluded persistence paths.

### ST0308-D2 — Inward Port contracts

Select the exact public Port ownership and method signatures.

1. Aggregate-specific inward Repository Protocols that accept and return only
   Domain entities and value objects.
2. Application command/query-specific persistence Ports that keep Repository
   concepts out of Domain packages.
3. Generic CRUD Repository APIs. This has the highest risk of leaking storage
   semantics and bypassing aggregate invariants.

Required answer: module paths, Protocol names, method signatures, result types,
not-found/conflict/integrity errors, optimistic-version semantics, idempotency
behavior, and cancellation/timeout boundary.

### ST0308-D3 — SQLAlchemy and Domain mapping

Select the adapter mapping and ownership model.

1. Adapter-owned declarative SQLAlchemy row models with explicit Domain
   conversions.
2. Adapter-owned SQLAlchemy Core metadata and explicit SQL repositories.
3. Raw psycopg repositories. This requires an explicit reconciliation with the
   upstream SQLAlchemy direction and current Python toolchain.

Required answer: mapping ownership, generator versus hand-maintained sources,
table/column parity rule, unknown-column and enum behavior, temporal/UUID/JSON
normalization, and proof that SQLAlchemy types never cross inward Ports.

### ST0308-D4 — Unit of Work and Session lifecycle

Select the transaction API and lifecycle.

1. Synchronous SQLAlchemy `Session`, adapter-owned, with one explicit Unit of
   Work per Application command.
2. `AsyncSession`, which also requires an approved async database runtime and
   wiring boundary that does not currently exist.
3. Framework-neutral `TransactionBoundary` Protocol implemented by an adapter
   that owns the underlying Session.

Required answer: begin/flush/commit/rollback semantics, ownership of commit,
nested-call behavior, savepoint policy, exception mapping, retry ownership,
isolation assumptions, and whether read-only operations share this boundary.

### ST0308-D5 — Cross-module writes, Outbox, Audit, and Idempotency

Select the coordination mechanism while preserving the canonical prohibition
on direct cross-module Repository/table access.

1. An Application Service coordinates only Ports owned by its module and may
   invoke another module only through that module's public Application
   Interface; it appends Audit, Outbox, and Idempotency records inside one Unit
   of Work where the approved command boundary permits it.
2. Domain Events are collected and the Unit of Work atomically persists their
   Outbox representation.

Independently of the selected coordination mechanism, the approval must decide
and preserve the scope boundary that ST-0308 owns at most atomic Outbox
persistence, while ST-1404 exclusively owns dispatch, lease, retry, inbox
processing, and DLQ runtime.

Required answer: exact event lifecycle, serialization contract, ordering,
aggregate-version checks, audit actor/source binding, idempotency replay and
payload-mismatch behavior, and the strict ST-1404 handoff boundary.

### ST0308-D6 — Connection factory and workload identity

Select how a repository receives a verified connection identity without
resolving credentials inside Domain or persistence code.

1. Application wiring injects an already validated Engine/connection provider;
   ST-0308 performs no Secret resolution.
2. Extend ST-0204 with database endpoint and opaque credential references.
   This is a separate configuration/security scope and needs explicit approval.
3. Provide a development-only factory with a separate, unimplemented production
   factory and strong misuse guards.

Required answer: factory Port, allowed workload roles per adapter/repository,
Secret-reference ownership, pool lifecycle, connection initialization,
transaction-local role behavior, and public/readmodel isolation enforcement.

## Mandatory rejected paths

The approved decision must reject all of the following:

- an empty or generic Unit of Work presented as completion without concrete
  repositories;
- direct writes to another module's Repository or tables;
- Repository-owned implicit commits or autocommit mutation paths;
- external/provider I/O inside a database transaction;
- Domain imports of SQLAlchemy, FastAPI, provider SDK, or framework types;
- public-role access outside approved readmodel projections;
- credential values in source, configuration artifacts, arguments, logs, or
  evidence;
- ST-0308 ownership or implementation of dispatcher, worker lease, retry,
  inbox-processing, or DLQ runtime that is reserved to ST-1404;
- migration, schema, RLS, role, or grant changes not separately authorized.

## Required acceptance and test evidence

The approved handoff must turn the selected design into exact assertions,
including at least:

- TST-005 coverage for every approved Port contract and negative boundary;
- PostgreSQL 18.4 TST-008 coverage for repository and Unit-of-Work behavior;
- commit, rollback, and no-partial-write evidence for each approved command;
- stale-version and idempotency replay/payload-mismatch behavior;
- atomic Aggregate/Version/Audit/Outbox/Idempotency behavior where applicable;
- immutable-record and public-readmodel-only negative tests;
- workload-role denial tests for every non-owner path;
- model-to-DDL parity if SQLAlchemy models or metadata are declared/generated;
- dependency-direction, type, lint, secret-scan, and affected predecessor gates;
- explicit separation of local evidence, formal CI/TST, runtime/provider proof,
  human review, staging, and production readiness.

## Completion record required before implementation

The Pro/human decision owner must produce a separate approved artifact with all
of the fields represented below. This deliberately non-authoritative template
does not use the real handoff root marker, retains every decision-request gap,
and remains pending. It cannot be renamed or edited in place into authority;
the actual approved `DESIGN_HANDOFF_V1` must be a separate artifact backed by
independently evidenced Pro advice, human approval, and canonical
reconciliation. Placeholder text, a missing field, or any nonempty Open
Decision blocks implementation.

```yaml
NON_AUTHORITATIVE_HANDOFF_DRAFT_TEMPLATE:
  authority: INFORMATIONAL_TEMPLATE_ONLY
  approved_story: ST-0308
  approved_scope:
    - <exact repository and aggregate inventory from D1>
    - <exact Port files and signatures from D2>
    - <exact mapping ownership from D3>
    - <exact Unit-of-Work lifecycle from D4>
    - <exact cross-module and Outbox boundary from D5>
    - <exact connection and workload-identity boundary from D6>
  source_design_refs:
    - <canonical references reconciled by the decision owner>
    - <sanitized advice identity or hash from a separately authorized Pro consultation>
  decision:
    repository_inventory: <approved D1 answer>
    port_contracts: <approved D2 answer>
    mapping_strategy: <approved D3 answer>
    transaction_boundary: <approved D4 answer>
    cross_module_and_outbox_boundary: <approved D5 answer>
    connection_and_identity_boundary: <approved D6 answer>
  rationale:
    - <approved rationale>
  rejected_alternatives:
    - <each credible unselected option and reason>
  constraints:
    - <exact implementation constraints>
  security_and_approval_gates:
    - <applicable security controls and external approval boundaries>
  acceptance_criteria:
    - <observable completion assertions>
  required_test_evidence:
    - <exact local and PostgreSQL 18.4 test evidence>
  open_decisions:
    - ST0308-D1
    - ST0308-D2
    - ST0308-D3
    - ST0308-D4
    - ST0308-D5
    - ST0308-D6
  approval:
    status: PENDING
    approved_by: null
    approved_at: null
    canonical_reconciliation: NOT_EXECUTED
```

## Current unresolved state

```yaml
canonical_story_state:
  open_decisions: []
  design_status: APPROVED_FOR_IMPLEMENTATION
  implementation_status: NOT_STARTED
  verification_status: NOT_EXECUTED
decision_request_gaps:
  - ST0308-D1
  - ST0308-D2
  - ST0308-D3
  - ST0308-D4
  - ST0308-D5
  - ST0308-D6
pro_advice_observation:
  authority: SANITIZED_NONCANONICAL_OUT_OF_BAND_OBSERVATION
  status: PRO_UNAVAILABLE_DO_NOT_RETRY_EXISTING_RUN
replacement_pro_run_authority: NOT_AUTHORIZED_BY_THIS_PACKET
human_approval_status: NOT_PROVIDED
implementation_authority: BLOCKED
```

No repository implementation, migration, database operation, browser action,
new Pro submission, credential access, or formal test execution is represented
by this decision request.
