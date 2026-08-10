# ST-1201 disabled first-party event collector seam

Classification:
`MAXIMUM_SAFE_LOCAL_RECORDED_DISABLED_FIRST_PARTY_EVENT_COLLECTOR_SEAM`.

This implementation-first slice projects the exact ordered canonical event
catalog (`EVT-001` through `EVT-020`) and provides a synthetic, process-local
recorded validation boundary. It is partial, non-authoritative, local-only,
non-persistent, and runtime-ineligible.

OD-012 remains unresolved. The explicit default is
`DISABLED_OD_012` with an empty event allowlist. The only other mode is
`RECORDED_TEST_ONLY`, which may compare allowlisted synthetic fixtures for the
eleven MVP `public_web` events. Neither mode activates tracking.

## Closed behavior

- The committed ST-0404 framework-neutral guard runs first against an explicit
  caller-supplied synthetic, default-deny policy.
- The local collector then requires anonymous `POST` metadata and
  `application/json`; cookie and bearer credential modes remain denied.
- Only exact `GRANTED` consent with the closed synthetic full-consent context
  can reach the recorded port. `DENIED`, `NOT_REQUIRED`, `UNKNOWN`,
  `COOKILESS`, and `ESSENTIAL_ONLY` remain blocked pending OD-012.
- The public collector rejects worker, admin, backend, and non-MVP events.
  `content_feedback` remains disabled.
- Envelope members and event-specific parameters are exact and immutable.
  Unknown, missing, duplicate-represented, or reordered parameters fail closed.
- Raw IP, full user agent, email, phone, raw search query, article body,
  Source Packet text, affiliate URL query secrets, nested values, and unbounded
  or control-bearing values are rejected.
- Event IDs, timestamps, site/correlation IDs, session pseudonyms, and all
  parameter values are supplied by synthetic fixtures. This slice generates no
  ID, clock value, session identifier, or pseudonym.
- The deterministic payload SHA-256 is used only to compare an event with an
  immutable ordered script. `RECORDED_ACCEPTED` and `RECORDED_DUPLICATE` do not
  mean stored, persisted, committed, measured, or durably deduplicated.

Every successful local result remains:

- execution: `RECORDED_TEST_ONLY`
- tracking activation: `DISABLED`
- persistence: `NOT_EXECUTED`
- consent authority: `UNRESOLVED_OD_012`
- measurement observed: false
- decision: `NOT_READY`
- formal TST-012/TST-030/TST-031: `NOT_EXECUTED`

## Explicitly unavailable

There is no API route, framework response, browser/beacon integration,
repository, unit of work, transaction, database, filesystem or object store,
provider/network call, environment lookup, cookie, credential, retention
policy, deletion, retry, or external action.

The frozen `PUB-004` AffiliateClickInput vocabulary is not mapped to canonical
`EVT-004`, and canonical events are not mapped to ST-0305 physical analytics
rows. Those approved contracts are not isomorphic; choosing either mapping is
deferred integration debt and is outside this safe slice.

Local tests, lint, and type checks are implementation evidence only. They do
not satisfy privacy review, formal TST execution, browser/runtime validation,
database persistence, hosted CI, staging, release, or Production acceptance.
Canonical Story acceptance and release eligibility remain false.
