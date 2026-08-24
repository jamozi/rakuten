# ST-1204 recorded GA4 import runtime slice

Classification:
`SOURCE_DERIVED_NON_ATTESTING_RECORDED_GA4_IMPORT_REFERENCE_SEAM`.

This implementation-first slice consumes caller-supplied bytes for one of the
three existing synthetic ST-1204 recordings. It validates the exact recorded
request, response, canonical rows, configuration snapshot, and failure outcome
through one credential-free inward port. It is partial, source-derived,
non-authoritative, local-only, non-persistent, non-attesting, and
runtime-ineligible.

## Frozen source bindings

The semantic contract and the three recorded fixture payloads remain
authoritative for the recorded bytes. The owner publication layout is hardened
without changing any fixture payload: `changes/st-1204/generated` is the sole
authoritative generated tree and contains `manifest.json` plus
`fixtures/recorded/*.json`.

| Recording | Whole-document SHA-256 | Bytes | Outcome |
| --- | --- | ---: | --- |
| `baseline` | `2c4082c31a1ca285bd04cc2bec74eeb02cad7a41753fb9eb7a5c371cc3620aab` | 11595 | `RECORDED_SUCCESS` |
| `late-revised` | `d8c6dbc6fe5a7509a39c40cf8e60dfe867d6bd775ae097f9961e5c81d6a88e1a` | 11657 | `RECORDED_SUCCESS` |
| `provider-error-429` | `b160fa1996e7579eebe362938313da2afb60530904679aa566a5d8dde7dd2fcc` | 3054 | `RECORDED_RESOURCE_EXHAUSTED` |

The internal request SHA-256 is
`ee206e0ec5d7c98afa2e871a33db134e558a2d854a724832ba834394bb2a22eb`.
The wire request SHA-256 is
`42a74836abe8d2be8cea6c4ffa47a3899e22cdec3f9ba31aa21be23622c7836a`.

The only accepted profile is synthetic site
`00000000-0000-4000-8000-000000001204`, property `1000001204`, resource
`properties/1000001204`, dates `2026-07-01` through `2026-07-02`, ordered
dimensions `date`, `pagePath`, `deviceCategory`, ordered metrics `sessions`,
`screenPageViews`, `engagedSessions`, one unnamed date range, null filters,
empty ordering, limit 2, offset 0, `keep_empty_rows=false`, and
`return_property_quota=true`. `force_reimport` may be absent or exactly false;
it never triggers work.

## Closed behavior

- Runtime receives fixture bytes from its caller and checks exact byte length
  and whole-document SHA-256 before UTF-8 or JSON parsing.
- Parsing rejects duplicate members, non-finite numbers, unknown or missing
  members, boolean-as-integer substitutions, header/value arity drift, and
  request, response, identity, or projection hash drift.
- The port exposes one `read(recording_id, request)` operation. The application
  validates the closed command before calling it exactly once.
- Metric values remain ordered provider strings. This slice performs no numeric
  conversion, aggregation, attribution, ranking, or persistence mapping.
- Each successful recording preserves two returned rows while retaining the
  independent provider `rowCount` value 3. It never attempts another page or
  invents the unreturned row.
- Baseline and late-revised remain independently inspectable recordings. No
  current-version, replacement, or supersession relationship is asserted.
- The recorded 429 is represented only as sanitized
  `RECORDED_RESOURCE_EXHAUSTED`. Its provider message is discarded; no retry,
  configuration lookup, or second port call occurs.
- Successful fixture projections preserve the recorded response hashes,
  `DEVICE_BASED` identity, timestamps, threshold/data-loss flags, sampling
  values, quota counters, timezone, and currency as inert recorded facts.

Every result remains bounded by:

- execution mode: `RECORDED_FIXTURE_ONLY`
- tracking: `DISABLED_OD_012`
- credentials: `NOT_USED`
- provider execution: `NOT_EXECUTED`
- configuration: `IN_FIXTURE_ONLY` or `NOT_CAPTURED_AFTER_ERROR`
- persistence, job dispatch, event publication, and formal TST-030:
  `NOT_EXECUTED`
- supersession: `NOT_DEFINED`
- decision: `NOT_READY`

## Explicitly unavailable

There is no Google SDK or API call, endpoint invocation, credential or
environment lookup, HTTP client, filesystem access, provider discovery,
pagination, retry/backoff, queue or job dispatch, event publication,
repository, unit of work, database, object storage, audit write, status change,
staging, release, or Production action. OD-012 optional tracking remains
disabled and OD-015 remains recorded-fixture-only.

The ST-1204 owner contract binds the exact current committed ST-0204 and ST-0305
manifest bytes. Those predecessor artifacts remain unchanged; ST-1204 is
regenerated through its owner after a mechanical downstream pin rebind. The
former atomic-publication `FAIL`/`MEDIUM` finding is locally remediated by the
owner generator's captured-Story-directory lock, single-tree namespace
publication, durable recovery journal, reverse rollback, and hostile tests.
The active journal root and every committed state carry an invocation-local
full-signature inventory from creation or recovery capture through terminal
cleanup; same-invocation automatic recovery carries that inventory forward and
never recaptures an active journal after a failure. Later byte equality cannot
re-own a replaced inode. A partial stage is
deleted only when the same invocation captured every directory identity and
file signature before the relevant checkpoint. A nonempty stage surviving a
process boundary is preserved and refused. Bundle reads revalidate both nested
`fixtures` and `recorded` names against their already-open descriptors before
acceptance.

Owner `--check` preserves bytes, namespace, device/inode, size, mode, mtime and
ctime. Access time is explicitly outside that guarantee because portable
read-only opens may update it; the implementation does not claim `O_NOATIME`.
Independent read-only re-audit remains separate. The runtime adapter boundary
still contains no publisher and still receives bytes only from its caller.

Local tests, lint, and type checks are implementation evidence only. They do
not satisfy OD-012 or OD-015, live Google/provider or credential validation,
database persistence, formal TST-030, hosted CI, staging, release, Production,
or canonical Story acceptance. All remain unexecuted.
