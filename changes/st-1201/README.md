# ST-1201 canonical event collector

Status: `LOCAL_CODE_COMPLETE` (maximum-safe durable recorded-local V2)

ST-1201 V2 adds an owner-private, append-only event journal behind the existing
ST-0404-guarded first-party collector. It deterministically projects all 20
canonical event definitions and can durably exercise the 11 MVP `public_web`
events with explicit synthetic consent. It does not activate tracking or create
an HTTP route, browser beacon, provider integration, credential path, or public
write.

## Consent and privacy boundary

OD-012 remains `HUMAN_DECISION_REQUIRED`. Production and browser tracking stay
disabled. The only accepting local path is `RECORDED_TEST_ONLY` with an exact
caller-supplied `GRANTED` / `FULL_CONSENT` synthetic context and an explicit
MVP-event allowlist. The disabled policy has an empty allowlist and stops before
event storage. `DENIED`, `NOT_REQUIRED`, `UNKNOWN`, `COOKILESS`, and
`ESSENTIAL_ONLY` fail closed.

The canonical envelope and event-specific parameter order are exact. Unknown,
missing, reordered, nested, unbounded, control-bearing, or non-finite values
are rejected. Raw IP, full user agent, email, phone, raw search query, article
body, Source Packet text, affiliate URL query secrets, URL-shaped values, and
credential-shaped values are prohibited before persistence. The collector does
not generate identifiers, timestamps, consent state, or pseudonyms.

## Durable local journal

- The absolute owner-private root must be a real directory owned by the current
  process at mode `0700`. The SQLite file is no-follow, owner-only `0600`, and
  single-link.
- Each accepted event stores its exact canonical bytes, payload SHA-256,
  identity/source metadata, sequence, and previous-record digest in one
  `BEGIN IMMEDIATE` transaction.
- Event IDs are durable idempotency keys. An exact replay returns
  `RECORDED_DUPLICATE`; the same ID with changed bytes is a conflict. Concurrent
  requests converge on one accepted record.
- The exact schema, SQLite integrity, metadata digest, row digests, contiguous
  sequence, payload digests, and global hash chain are checked on every
  transaction and restart.
- Before-commit failure rolls back. A simulated after-commit ambiguity recovers
  the exact committed record without retrying the write.
- Event rows are protected by append-only triggers. There is no public read,
  list, query, export, update, delete, purge, retention, or lifecycle API.

The legacy 67-test process-local scripted seam remains supported. Its closed
exception was changed from a frozen dataclass exception to a regular slotted
exception so Python can safely restore `__traceback__` during context-manager
re-raise; its observable code/string/repr contract remains unchanged.

## Authority and evidence

Every V2 collaborator exposes `action_count == 0`. Tracking activation,
measurement observation, recommendation/content mutation, reward/commission/
EPC/RPM/profit ranking input, external network, provider, credential,
publication, staging, release, and Production authority are absent. OD-014 is
not selected, so no retention or automatic deletion behavior is introduced.

`scripts/build_st1201_durable_event_store.py` validates the Canonical Story,
event catalog, OD-012, release-blocking suite identities, ST-0305/ST-0404
dependencies, owned sources, and deterministic generated artifacts. Run it with
`--check` for a no-write drift check.

Focused local tests are implementation evidence only. Formal TST-012, TST-030,
TST-031, Privacy/Security owner review, hosted CI, real browser/runtime,
staging, release, Production, and Canonical status `APPLY` remain
`NOT_EXECUTED`.
