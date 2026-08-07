# ST-1203 official API, installed contract, and physical database conflict audit

Audit date: 2026-08-06  
Authority: `INFORMATIONAL_NONCANONICAL_AUDIT_ONLY`  
Implementation authority: `NOT_GRANTED`  
Disposition: `FAIL_BLOCKED_PENDING_APPROVED_DESIGN_AND_SCHEMA_RECONCILIATION`  
Formal TST-030: `NOT_EXECUTED`  
Live Google validation: `NOT_EXECUTED`

## Result

The current recorded-fixture checkpoint can validate a bounded synthetic
Search Analytics response, but the canonical full `ST-1203` adapter/job cannot
be implemented losslessly against the installed physical contract. Three
independent conflicts require design authority:

1. the provider country value is ISO 3166-1 alpha-3 while the database column
   is `char(2)`;
2. canonical late reimport and supersession cannot be represented by the
   append-only row plus its current unique grain; and
3. the installed canonical-row schema does not define enough information to
   map every accepted request and response to the required database columns.

The installed adapter schemas also represent only a strict subset of the
current official API. That subset may be deliberate, but it is not currently
declared as the complete supported provider profile. None of these gaps may be
closed by an implementer through truncation, inferred conversion, destructive
overwrite, or an unapproved migration.

## Authority boundary

Canonical `ST-1203` states:

- dependencies: exactly `ST-0305` and `ST-0204`;
- requirement: `FR-013`;
- deliverable: `adapter/job`;
- acceptance: `dimension/request preserved` and `late reimport`;
- required suite: `TST-030`;
- open decision: `OD-015`.

`OD-015` keeps live provider credentials and live adapter evidence blocked;
its safe default is recorded fixtures only. This audit neither changes the
dependency set nor closes OD-015. A proposed schema correction must name its
owning Story and approval path instead of silently treating ST-1203 as DDL
authority.

## Conflict 1 — country dimension cannot be stored losslessly

The official Search Analytics method defines country values as ISO 3166-1
alpha-3. The current synthetic fixture uses the valid value `jpn`. The
installed ST-0305 catalog defines
`analytics.gsc_observation.country_code` as nullable `char(2)`.

These facts cannot both be preserved by the current row shape. The following
behaviors are prohibited unless an approved handoff explicitly selects and
specifies them:

- truncating `jpn` to two characters;
- assuming an alpha-3 to alpha-2 mapping;
- storing a provider country in an unrelated field;
- dropping the country dimension from the durable grain;
- replacing the value with `NULL`;
- changing the ST-0305 contract, migration, or generated catalog by hand.

The design handoff must select the authoritative stored representation, exact
validation and conversion rules, compatibility/backfill behavior, rollback,
and the Story that owns any physical change.

Official provider reference checked for drift on 2026-08-06:
<https://developers.google.com/webmaster-tools/v1/searchanalytics/query>.

## Conflict 2 — late reimport versus append-only unique grain

Canonical analytics design requires recent periods to be reimported and
superseded, and the ST-1203 acceptance criterion explicitly requires late
reimport. The installed table is classified `APPEND_ONLY` and has the unique
index `ux_analytics_gsc_grain` on:

```text
site_id, metric_date, dimension_key_sha256
```

The observation row has an `import_run_id`, but its unique grain does not
include that field. It has no approved fact version, validity interval,
superseded-by reference, current-row flag, or source-request column. A revised
value for the same grain therefore cannot be appended, while mutating or
deleting the prior row contradicts the declared write pattern.

The handoff must define one durable model, including:

- immutable history and current-value query semantics;
- idempotent replay versus revised late-arriving data;
- exact unique keys and indexes;
- relationship to `analytics.import_run`;
- transaction and concurrent-import behavior;
- backfill, compatibility, rollback, and recovery;
- whether the correction is owned by ST-1203 or a separately approved schema
  Story.

No implementation may use last-write-wins, delete-and-reinsert, silent
duplicate suppression, or a synthetic in-memory supersession rule.

## Conflict 3 — canonical row to physical row is underspecified

The installed request schema permits any unique subset of the listed
dimensions, including a request without `date`. The installed canonical-row
schema stores request-level `date_from` and `date_to`, an ordered `dimensions`
array, and ordered `keys`; it does not require one row-level date. The physical
table requires non-null `metric_date`.

The exact mappings below are also absent:

- Search Console property URL and `site_id` ownership;
- full page URL to `page_path` normalization;
- query text sanitization, retention, hashing, and suppression;
- exact canonical bytes for `query_sha256` and
  `dimension_key_sha256`;
- ordered dimensions and keys, filters, search type, aggregation type,
  `data_state`, and adapter version in the durable request identity;
- provider JSON numbers to `bigint`, `numeric(10,8)`, and
  `numeric(10,4)` without binary floating-point drift or unapproved rounding;
- `source_request_sha256`, response aggregation type, top-row caveat, and
  incomplete-data metadata to `analytics.import_run` or another approved
  durable location.

The handoff must provide a two-way mapping matrix: every supported provider
field must be mapped or explicitly rejected, and every required physical
column must have one authoritative source, normalization, nullability rule,
and failure behavior.

## Installed contract versus current official API

The installed request schema currently:

- accepts `data_state` only as `final` or `all`;
- omits `byNewsShowcasePanel` from aggregation type;
- limits filter expressions to 1,000 characters;
- has no response metadata contract.

The official method currently documents `hourly_all`,
`byNewsShowcasePanel`, filter expressions up to 4,096 characters, optional
incomplete-data metadata, Pacific Time date semantics, and a top-rows rather
than exhaustive-results caveat. The official documentation is drift evidence,
not authority to mutate the installed repository contracts.

The handoff must choose either:

1. a deliberately narrow, versioned, fail-closed provider profile; or
2. an exact contract revision with compatibility and ownership rules.

It must also define unknown-field behavior and whether legitimate metadata is
preserved, safely ignored under an explicit forward-compatibility rule, or
rejected as unsupported. The current implementation must not be described as
supporting the complete current API.

## Required design outputs

The exact `DESIGN_HANDOFF_V1` must resolve at least:

- supported provider request/response profile and drift policy;
- property authorization and credential-free recorded-adapter boundary;
- canonical row grain and row-level date derivation;
- physical country, page, query, device, appearance, and numeric mapping;
- request and dimension hashing canonicalization;
- late-reimport versioning and supersession;
- import-run/job lifecycle and transaction boundaries;
- query privacy, low-volume suppression, retention, logs, Audit, and events;
- any migration owner, exact schema delta, backfill, rollback, and tests;
- the formal/local/live/staging/production evidence boundaries.

Until those decisions are returned, canonically reconciled, and explicitly
approved by the repository owner, only design-free hardening of the existing
recorded-fixture validator is authorized. Full adapter/job, database write,
live provider, credential, migration, and event implementation remain blocked.

