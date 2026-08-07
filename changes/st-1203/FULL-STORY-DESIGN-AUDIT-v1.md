# ST-1203 full-story design and implementation audit

Audit scope: canonical `ST-1203` plus the current recorded-fixture checkpoint  
Audit date: 2026-08-06  
Audit authority: `INFORMATIONAL_NONCANONICAL_AUDIT_ONLY`  
Implementation authority: `NOT_GRANTED`  
Audit disposition: `BLOCKED_PENDING_EXACT_DESIGN_HANDOFF`  
Formal TST-030: `NOT_EXECUTED`  
Live Google validation: `NOT_EXECUTED`  
Staging readiness: `NOT_READY`  
Production readiness: `NOT_READY`

## Executive result

The current local candidate is a deterministic, synthetic, recorded-fixture
slice. Its source validation, fixture semantics, deterministic `--check`, Ruff
checks, and isolated 84-test suite pass. It is not the canonical `adapter/job`
deliverable and cannot truthfully be completed into the full Story without
new decisions.

The blocking decisions concern the inward and outward adapter contracts,
provider pagination and incomplete-data semantics, the physical persistence
mapping and late-reimport model, privacy and hashing, job and transaction
ownership, event authority, runtime credential boundaries, and atomic fixture
publication. Those decisions require a separately produced
`DESIGN_HANDOFF_V1`, conflict-free reconciliation, and exact-byte repository-
owner approval before an `implementation_worker` may edit production code.

## Authoritative Story boundary

Canonical backlog facts:

- Story: `ST-1203`, Search Console adapter;
- objective: versioned import of GSC facts;
- dependencies: exactly `ST-0305` and `ST-0204`;
- requirement: `FR-013`;
- deliverable: `adapter/job`;
- acceptance: dimension/request preservation and late reimport;
- required suite: `TST-030`;
- open decision: `OD-015`;
- canonical implementation and verification: `NOT_STARTED` and
  `NOT_EXECUTED`.

`OD-015` is blocking for a live adapter test. Its safe default is recorded
fixtures only. It does not block synthetic implementation work, but it does
block credentials, live Google access, live-provider evidence, staging, and
production claims.

## Current checkpoint

The current checkpoint contains only:

- one strict source contract;
- three synthetic fixture documents;
- one deterministic fixture manifest;
- one offline generator/validator;
- isolated fixture-contract and generator tests.

It contains no GSC Domain model, inward Port, live or recorded adapter object,
application service, job handler, pagination loop, durable import transaction,
database repository, Outbox materializer, composition wiring, runtime Secret
resolution, live provider test, or TST-030 evidence.

Current exact local checkpoint hashes:

- source contract:
  `eb72f0305aa02529517e3154246c2a5104f42a886ec5b31dc8636b22ac440619`;
- generator:
  `c002653db89f6b9ac33dff3abace994d6c6dc2583a2d6f4a2940d0a0577687b3`;
- generated manifest:
  `769dce0219e43e9ac53312bd0b762cf50b41f3b4a072099c5ccae1cd1e2b305f`;
- fixtures:
  `de421fe75e633d47a02f0aa579f36f746d5ee191eb034dbd28a6c5dfd26dd3a9`,
  `f703edb673b3cc8b3686a9d983ab7940f7c3148a4eb7ac192da5761f0b0b96a0`,
  and
  `1b50f12e0a904db7202771adb39157071ec959c0f4d4d0e815e67a9e6f45557c`.

Fresh local checks on 2026-08-06:

- deterministic generator `--check`: PASS;
- isolated `tests/st1203`: 84 passed;
- Ruff lint: PASS;
- Ruff format check: PASS.

The bounded 2026-08-06 hardening pins the complete declared Story,
generation, and provenance structures, rejects 226 structural mutations, and
adds semantic checks for the selected date, country, device, row-limit, and
page/`byPage` fixture profile. It changes neither the source contract nor the
three fixture bytes. The bounded profile rejects `hour` and
`searchAppearance` rather than inventing their semantics. The capability test
also pins direct module attribute chains and rejects known module-registry and
reflection recovery probes; it is a trusted-source regression guard, not a
Python sandbox. This closes local validator gaps only; it does not resolve the
provider/database/design conflicts below.

These are local candidate checks, not formal TST-030 or full-Story evidence.

## Findings

### ST1203-AUDIT-001 — BLOCKER — full adapter/job contract is absent

The backlog provides a concise objective but no `design_refs`. The current
checkpoint intentionally forbids network, credentials, persistent writes,
database writes, and live API use. It therefore cannot supply the full
`adapter/job` deliverable.

An implementation would otherwise have to invent exact Domain types, Port
signatures, error classes, retry classification, pagination result, job
handler ownership, persistence transaction shape, and module paths. Those are
architecture decisions, not mechanical completion.

### ST1203-AUDIT-002 — HIGH — late reimport conflicts with the physical model

Canonical analytics design requires recent periods to be reimported and
superseded. The current recorded fixture deliberately makes the baseline and
late-revised result separately inspectable without claiming any supersession
rule.

The ST-0305 physical model classifies `analytics.gsc_observation` as
`APPEND_ONLY`, while the unique index `ux_analytics_gsc_grain` covers
`site_id`, `metric_date`, and `dimension_key_sha256`. There is no physical
fact-version, valid-time, superseded-by, or source-request column on the
observation row. A second version of the same grain therefore cannot simply be
appended, while an update or delete would contradict the declared write
pattern. ST-1203 has no migration authority.

The handoff must choose a conflict-free rule or explicitly stop at a schema-
story boundary. The implementer must not silently use last-write-wins,
destructive replacement, duplicate suppression, or an invented version
column.

### ST1203-AUDIT-003 — HIGH — provider country values do not fit the column

The current official Search Analytics method defines the country filter and
dimension with ISO 3166-1 alpha-3 values. The current fixture correctly uses
`jpn`. The ST-0305 physical column `analytics.gsc_observation.country_code` is
`char(2)`.

No lossless mapping is approved. Truncation, alpha-3 to alpha-2 conversion,
dropping the dimension, storing `NULL`, or changing the schema would each be a
new policy or schema decision. The full implementation is blocked until the
handoff resolves this mismatch or identifies the owning schema correction.

Official reference checked for drift on 2026-08-06:
<https://developers.google.com/webmaster-tools/v1/searchanalytics/query>.

### ST1203-AUDIT-004 — HIGH — installed schemas lag current API semantics

The current official method includes `dataState=hourly_all`, incomplete-data
metadata, `aggregationType=byNewsShowcasePanel`, filter expressions up to 4096
characters, and PT/America-Los_Angeles date semantics. The installed request
schema exposes only `final` and `all`, omits the response metadata contract,
omits `byNewsShowcasePanel`, caps expressions at 1000 characters, and does not
state the provider date-zone conversion rule.

The installed schemas remain repository authority until properly revised;
live documentation cannot silently mutate them. The handoff must decide
whether ST-1203 intentionally supports a strict subset, requires a separately
owned contract revision, or remains recorded-only. It must specify how an
unsupported provider response fails closed.

### ST1203-AUDIT-005 — HIGH — row-to-storage mapping is incomplete

The following mappings are not defined:

- how a required `metric_date` is derived when `date` is not requested;
- how a full provider page URI becomes physical `page_path`;
- whether raw query text may be retained, redacted, hashed, or omitted;
- exact `query_sha256` canonical bytes and privacy suppression behavior;
- exact `dimension_key_sha256` members, normalization, ordering, and encoding;
- conversion of provider JSON numbers to `bigint`, `numeric(10,8)`, and
  `numeric(10,4)` without binary-float drift;
- response aggregation type and incomplete-data metadata persistence;
- how source request hash and adapter version remain recoverable when the
  observation table has no corresponding columns.

The current fixture contract explicitly marks several of these as
`NOT_DEFINED`. An implementation must fail rather than guess.

### ST1203-AUDIT-006 — HIGH — durable transaction and event authority is absent

The physical model has `analytics.import_run` and
`analytics.gsc_observation`; the job catalog defines
`analytics.import_search_console.v1`; the event contract defines
`jp.raos.analytics.import_completed.v1`. The current Story dependency list
does not include ST-0308 persistence or ST-1404 job runtime.

The handoff must define the inward persistence boundary available to this
Story without silently adding dependencies, direct SQL from Application code,
or Repository ownership from another module. It must also define which owner
creates the Ops job, starts/completes the import run, writes observations,
materializes Audit/Outbox, and commits. External Google calls must not occur
inside an open database transaction.

### ST1203-AUDIT-007 — MEDIUM — credential and property mapping is unresolved

ST-0204 provides an opaque `SecretReference`, but explicitly leaves production
Secret resolution, workload identity, rotation hooks, and a Secret-manager
adapter unimplemented. The current checkpoint also marks site-ID to GSC
property mapping as undefined.

The recorded adapter can remain credential-free. A live adapter cannot be
activated until OD-015 evidence and the separately owned Secret/workload
identity boundary exist. ST-1203 must not read ambient credentials, receive a
Secret value through its inward Port, or infer a site URL from untrusted job
input.

### ST1203-AUDIT-008 — MEDIUM — fixture publication is not a bundle transaction

Read-side source capture uses descriptor-relative `O_NOFOLLOW` traversal. The
write side first checks ancestors by full path, then calls full-path
`mkstemp`, `os.replace`, and directory open. A same-UID ancestor swap can
therefore redirect a previously checked write.

The three fixtures and manifest are also replaced sequentially. A disposable
fault injection after the second replacement produced this observed state:

```text
baseline.json         NEW
late-revised.json     NEW
start-beyond-data.json OLD
manifest.json         OLD
```

The current 84 tests do not prove write confinement, one-generation bundle
visibility, rollback, crash recovery, or locking. The publication design must
be approved before fixing this finding; the current artifact paths and reader
semantics cannot be changed by the implementer as a hidden design choice.

### ST1203-AUDIT-009 — MEDIUM — TST-030 coverage is only a fixture subset

Formal TST-030 requires analytics reconciliation across Event, GA4, GSC,
Revenue, Attribution, and KPI in CI and staging. The current isolated test set
is useful local fixture evidence, but it does not run a worker job, provider
fake, PostgreSQL transaction, late-reimport/supersession, Outbox, concurrency,
failure recovery, or cross-source reconciliation.

The handoff must define truthful Story-local tests without claiming the entire
formal suite or downstream analytics system.

## Required resolution set

A complete handoff must resolve, at minimum:

1. exact full-Story scope, modules, files, and exclusions;
2. Domain values, inward Ports, outward adapters, and sanitized errors;
3. official request/response subset, pagination, incomplete data, and drift;
4. durable import-run and observation persistence contract;
5. late-reimport, idempotency, supersession, and physical-model conflict;
6. dimension/date/page/query/privacy/hash/numeric mapping;
7. job lifecycle, retry, cancellation, deadlines, and transaction ownership;
8. event/Audit/Outbox emission authority and aggregate-version source;
9. recorded-fixture layout and atomic publication semantics;
10. exact acceptance, negative, PostgreSQL, provider-fake, and evidence gates.

## Safe next action

Prepare a hash-bound Pro input packet containing canonical authority, exact
installed contracts, ST-0204/ST-0305 predecessor evidence, the current ST-1203
checkpoint, the official-reference findings, and existing repository
publication precedents. Request one complete unapproved
`DESIGN_HANDOFF_V1_ST1203_v1.yaml`. Validate and reconcile the returned exact
bytes, then require explicit repository-owner approval before delegating one
Story to `implementation_worker`.
