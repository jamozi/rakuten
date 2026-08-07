# ST-1203 Search Console adapter/job DESIGN_HANDOFF_V1 request

Status: `PROPOSAL_REQUEST_ONLY`  
Authority: `UNAPPROVED_PROPOSAL_INPUT`  
Implementation authority: `NOT_GRANTED`  
Human approval: `NOT_PROVIDED`  
Canonical reconciliation: `PENDING`  
Formal TST-030: `NOT_EXECUTED`  
Live provider validation: `NOT_EXECUTED`  
Staging readiness: `NOT_READY`  
Production readiness: `NOT_READY`

## Task

Produce one complete, self-contained `DESIGN_HANDOFF_V1` proposal for the
single canonical Story `ST-1203`, covering `ST1203-D1` through `ST1203-D10`.
The proposal must make the recorded adapter/job/persistence implementation
mechanically executable while preserving every approval and evidence boundary
below.

Do not implement code, call Google, use or request a credential, close OD-015,
write to a database, change canonical/upstream/ZIP bytes, or claim formal
TST-030, staging, live, or production evidence. The exact returned bytes remain
unapproved until conflict-free canonical reconciliation and explicit
repository-owner approval.

## Canonical Story boundary

- Story: `ST-1203`
- Title: Search Console adapter
- Objective: versioned import of GSC facts
- Exact declared dependencies: `ST-0305`, `ST-0204`
- Requirement: `FR-013`
- Deliverable: `adapter/job`
- Acceptance: `dimension/request preserved`, `late reimport`
- Required suite: `TST-030`
- Open decision: `OD-015`
- Canonical implementation status: `NOT_STARTED`
- Canonical verification status: `NOT_EXECUTED`

`OD-015` requires external Operations evidence for production-provider
credentials. Its safe default is recorded fixtures only. Preserve it as a
deferred external decision; do not put it in bounded `open_decisions` and do
not claim to resolve it.

The backlog has no Story `design_refs`. Therefore the handoff must supply
missing precision, but it must not silently promote ST-0308, ST-0407, ST-1404,
or any other Story to a declared ST-1203 dependency. If a required physical or
runtime capability is owned elsewhere, identify an explicit interface and the
separate gated prerequisite rather than inventing it in this Story.

## Current recorded-fixture checkpoint

The local candidate contains only:

- one strict source contract;
- three deterministic synthetic recorded fixtures;
- one generated manifest;
- one offline generator/validator;
- isolated fixture-contract/generation tests;
- design and conflict audits.

It deliberately contains no full Domain model, inward Port, provider adapter,
application job handler, pagination loop, database repository, import
transaction, Audit/Outbox materializer, composition wiring, Secret resolution,
live request, or formal TST-030 evidence.

Current bounded-hardened checkpoint hashes are:

- source contract:
  `eb72f0305aa02529517e3154246c2a5104f42a886ec5b31dc8636b22ac440619`;
- generator:
  `c002653db89f6b9ac33dff3abace994d6c6dc2583a2d6f4a2940d0a0577687b3`;
- generated manifest:
  `769dce0219e43e9ac53312bd0b762cf50b41f3b4a072099c5ccae1cd1e2b305f`.

The local isolated suite has 84 passing tests. Its exact-contract negative
matrix rejects 226 Story/generation/provenance mutations. These are local
candidate results only and do not close the full Story or formal TST-030.

The attached bundle and member manifest are authoritative for the exact bytes
submitted after that bounded validator hardening. Treat all local code and tests as
unapproved evidence, not design authority.

## Confirmed reconciliation conflicts

The attached audits establish three blocking physical conflicts:

1. official Search Analytics country values are ISO 3166-1 alpha-3, while
   `analytics.gsc_observation.country_code` is `char(2)`;
2. canonical late reimport/supersession conflicts with the table's
   `APPEND_ONLY` classification and unique key on
   `(site_id, metric_date, dimension_key_sha256)`;
3. accepted provider/canonical rows do not define every mapping required for
   non-null `metric_date`, page, query/privacy fields, numeric columns,
   hashes, and durable request provenance.

The installed schemas also cover a narrower API profile than the current
official method. They omit `hourly_all`, response incomplete-data metadata,
and `byNewsShowcasePanel`, and cap filter expressions at 1,000 rather than
4,096 characters. Live documentation is drift evidence, not authority to
silently mutate installed contracts.

## Decisions to resolve

### ST1203-D1 — exact supported provider profile

Define a versioned, fail-closed Search Analytics request/response profile:

- accepted property types and request fields;
- supported dimensions, their order, and zero-dimension behavior;
- required/defaulted `type`/search type, aggregation type, `dataState`, row
  limit, start row, filters, operators, and expression bounds;
- whether `hourly_all`, `byNewsShowcasePanel`, and incomplete-data metadata are
  supported now, rejected, or delegated to an exact contract revision;
- Pacific Time/America/Los_Angeles date/hour interpretation and conversion;
- top-rows/non-exhaustive response semantics;
- exact pagination termination, empty-page, duplicate-page, maximum-page, and
  provider-inconsistency behavior;
- response unknown-field and API-drift behavior;
- exact installed-schema revisions, if any, and compatibility ownership.

Do not call a deliberately restricted profile complete support for the current
official API.

### ST1203-D2 — property, authorization, credentials, and provider errors

Define:

- the authoritative mapping between typed `site_id` and Search Console
  property URL;
- allowed URL-prefix versus domain properties and canonical normalization;
- which component owns property authorization;
- a credential-free inward Port and an outward credential/provider boundary;
- least-privilege scope and Secret-reference ownership;
- provider error taxonomy and sanitized retryable versus terminal mapping;
- rate-limit, quota, permission, missing-property, invalid-request, malformed
  response, cancellation, deadline, and availability behavior.

No Secret value, OAuth token, credential path, ambient Google SDK default, or
provider object may cross an inward Port or appear in logs/evidence. Live
credential activation remains blocked by OD-015.

### ST1203-D3 — canonical row grain and metric date

Select the exact Domain row identity and specify:

- whether every durable observation request must include the `date`
  dimension;
- how a row-level `metric_date` is derived and validated;
- how date ranges, hourly rows, and requests without `date` are rejected or
  represented;
- exact dimensions-to-keys arity, order, null, duplicate, and canonical-value
  rules;
- whether multiple provider rows can normalize to one physical grain and, if
  so, whether that is an error or an explicitly specified aggregation;
- exact typed Domain values and sanitized public errors.

The handoff must not infer `metric_date` from import time or choose one endpoint
of a multi-day request without explicit authority.

### ST1203-D4 — physical normalization and schema ownership

Define a complete, typed, two-way provider/Domain/storage mapping for:

- alpha-3 provider country and the current `char(2)` column;
- full provider page URL and physical `page_path`;
- query text, sanitization, optional retention, hash, and suppression flag;
- device and search appearance closed values;
- clicks/impressions integer conversion;
- CTR and average-position Decimal precision, rounding, overflow, and
  consistency checks;
- UTC import timestamps and provider-local dates;
- every nullable and non-null physical column.

Explicitly authorize or reject an ST-1203-owned corrective migration. If a
separate schema Story must own the change, identify the exact safe interface
boundary and stop condition. Any approved migration must define exact source
contract/generator/migration paths, forward/backfill/rollback rules, and
PostgreSQL 18.4 tests. Never authorize hand-editing generated ST-0305 outputs.

### ST1203-D5 — canonical hashing and provenance

Define exact UTF-8 bytes and deterministic serialization for:

- `dimension_key_sha256`;
- `query_sha256`;
- canonical provider request and `source_request_sha256`;
- idempotency/import identity.

Specify inclusion and order for site/property, date range, ordered dimensions
and keys, search type, aggregation type, filters, data state, pagination,
adapter/contract version, and any normalization tags. Define collision handling
and the durable location of request provenance where the current observation
row has no source-request column. Hashes must not be used to obscure a required
authorization or privacy decision.

### ST1203-D6 — late reimport and durable supersession

Choose one exact physical model compatible with immutable history and define:

- replay of identical data versus a revised late-arriving observation;
- current-row selection and historical query semantics;
- relation to `analytics.import_run`;
- unique keys, indexes, constraints, and allowed write patterns;
- concurrent import ownership and conflict behavior;
- idempotent restart after partial provider pagination;
- backfill, compatibility, rollback, recovery, and retention;
- whether downstream rollups/events observe every version or only committed
  current changes.

An `APPEND_ONLY` declaration plus the existing unique grain cannot be bypassed
with update, delete/reinsert, last-write-wins, or silent duplicate suppression.

### ST1203-D7 — job, import run, retries, and transaction ownership

Define the exact application and adapter files/types plus a lifecycle covering:

- validated job message and context;
- provider pagination outside database transactions;
- bounded memory or approved recorded-artifact staging;
- import-run creation, start, completion, failure, and recovery;
- durable page/request checkpoints, if any;
- cancellation and deadlines;
- retry classification, backoff ownership, and idempotent replay;
- one transaction owner, flush/commit/rollback boundaries, and error mapping;
- concurrency and per-site/per-window locking or CAS;
- relationship to the ST-0204 configuration boundary;
- explicit interface boundaries for persistence/job runtime capabilities owned
  by other Stories.

No external Google, Secret-manager, object-storage, queue, or notification call
may occur while a database transaction is open. No Repository may commit, and
ST-1203 must not invent an Outbox dispatcher, worker lease runtime, or generic
cross-module database access.

### ST1203-D8 — privacy, Audit, Outbox, and event authority

Define:

- query classification, sanitization, low-volume suppression, access, and
  retention;
- whether raw query text is persisted and the exact prohibited alternatives;
- prohibited values in logs, exceptions, Audit, Outbox, events, and fixtures;
- Audit intents and immutable context-bound actor/source fields;
- exact event type(s), producer, aggregate identity, persisted version source,
  event timing, payload schema, and emission conditions;
- whether no approved aggregate version means event emission is excluded;
- rollback behavior and no-side-effect rules for stale/replayed/failed imports;
- DLP, secret-scan, and negative evidence.

Schema existence does not itself grant event-emission authority. ST-1203 may
insert a same-transaction Outbox fact only through an approved persistence
boundary and must not implement dispatch, lease, retry, publication, Inbox, or
DLQ behavior.

### ST1203-D9 — recorded-fixture publication transaction

Select one authoritative fixture layout and define one coherent publication
unit for the closed fixture set plus manifest. Resolve:

- physical repository-root and ancestor validation;
- descriptor-relative traversal with `O_NOFOLLOW`;
- shared `--check` and exclusive generate locking;
- staging, exact inventory, modes, link-count, and ownership rules;
- file/directory fsync order;
- fresh install and replacement of an existing nonempty bundle;
- atomic namespace publication using the smallest approved repository
  precedent, including `renameat2(RENAME_EXCHANGE)` fail-closed behavior where
  selected;
- injected failure before/during/after publication;
- reverse rollback, crash recovery, cleanup, and retained evidence;
- stale stage/journal/tombstone handling;
- reader semantics proving no check-accepted mixed generation;
- legacy-path migration and prohibition on duplicate authoritative copies.

Use ST-0104/ST-0105 only as implementation precedents. Do not copy their whole
toolchains or add a dependency without need.

### ST1203-D10 — acceptance and evidence matrix

Provide observable acceptance criteria and exact tests for:

- every Domain/Port/provider/persistence/job signature;
- request/response, pagination, provider drift, malformed data, cancellation,
  deadline, retry, and sanitized-error paths;
- country/date/page/query/hash/numeric mapping;
- identical replay, late revision, current/history reads, concurrent imports,
  fault injection, rollback, and recovery;
- exact PostgreSQL 18.4 schema/migration/constraint/index behavior;
- fixture atomic publication, concurrency, crash, recovery, and read-only
  `--check`;
- prohibited imports, network/credential use, direct SQL/cross-module access,
  external I/O in transactions, dispatcher/runtime scope, and secret leakage;
- deterministic regeneration, Ruff, type checks, isolated Story tests, and
  independent read-only audit.

Separate local candidate checks from canonical TST-030. TST-030 still spans
Event, GA4, GSC, Revenue, Attribution, and KPI in CI/staging and cannot be
claimed by this Story-local implementation alone.

## Binding constraints

1. Keep the implementation and proposal scoped to ST-1203.
2. Preserve canonical precedence and the exact declared dependency list.
3. Change no canonical/upstream/ZIP artifact.
4. Change generators/contracts/migrations before their generated outputs;
   never hand-edit generated files.
5. Preserve `domain <- application <- adapters/framework`; inward Ports contain
   no SQLAlchemy, Google SDK, HTTP framework, provider, or raw database types.
6. Use official provider APIs only through outward adapters; recorded tests use
   synthetic fixtures and no network or credential.
7. No live credential, provider call, staging write, production write, formal
   evidence, publication, or release action is authorized.
8. No generic CRUD, arbitrary SQL Port, Repository-owned commit, hidden
   autocommit, cross-module Repository access, or external call in a database
   transaction.
9. No Outbox dispatcher, worker lease/retry loop, Inbox, DLQ, read-model, or
   unrelated analytics source implementation.
10. Local PASS never implies formal TST, CI, staging, human review, security
    review, or production readiness.

## Required `DESIGN_HANDOFF_V1` result

Return one UTF-8/LF YAML document rooted exactly at `DESIGN_HANDOFF_V1` with:

- `approved_story: ST-1203`;
- `approved_scope: RECORDED_ADAPTER_JOB_PERSISTENCE_AND_FIXTURE_PUBLICATION_ONLY`;
- exact path/SHA-256 `source_design_refs` for every used packet member;
- one exact `decision` covering `ST1203-D1` through `ST1203-D10`;
- `rationale` and `rejected_alternatives`;
- exact modules, files, Domain values, inward Ports, outward adapters,
  application/job types, and sanitized errors;
- exact installed-contract and physical-schema/migration changes or explicit
  separately owned stop boundaries;
- exact provider, normalization, hashing, persistence, supersession,
  transaction, privacy, event, publication, rollback, and recovery rules;
- `constraints` and `security_and_approval_gates`;
- observable `acceptance_criteria` and `required_test_evidence`;
- `deferred_external_decisions` containing OD-015 unchanged;
- `open_decisions: []` only if every bounded D1-D10 choice is mechanically
  complete and conflict-free;
- proposal/pending/not-approved authority fields;
- explicit `NOT_EXECUTED` fields for formal TST-030, live provider, CI,
  staging, production, human review, and security review.

If a required conflict cannot be resolved within legitimate ST-1203 authority,
return the exact external prerequisite and safe stop boundary rather than an
invented implementation. Do not return a prose advisory, code patch, or partial
handoff.

The result must be one complete downloadable file named
`DESIGN_HANDOFF_V1_ST1203_RECORDED_ADAPTER_v1.yaml`. It remains an unapproved
proposal until exact-byte canonical reconciliation and explicit
repository-owner approval.
