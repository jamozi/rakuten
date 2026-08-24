# ST-0502 — maximum-safe local Item Search runtime V2

Classification: `MAXIMUM_SAFE_LOCAL_ITEM_SEARCH_RUNTIME`

Local implementation status: `LOCAL_CODE_COMPLETE`

Canonical status: `UNCHANGED`

The additive V2 runtime closes the maximum-safe local code gaps identified by
`DEBT-W2-013`. It does not grant live-provider, credential, hosted, release, or
Production authority and does not claim formal Story validation.

## Closed local boundary

- The deterministic request is bound to the official Item Search documentation
  captured on `2026-08-24T16:43:55Z`, API version `2026-07-01`, format version
  `2`, origin and path, an exact conservative parameter/element allowlist, and
  RFC 3986 UTF-8 query encoding. The official raw HTML and response are not
  committed; only the URL, fetch time, raw-response SHA-256, and sanitized facts
  are retained.
- Future authentication is represented only by three closed secret names.
  `accessKey` is header-only; `applicationId` and optional `affiliateId` are
  query secret-name bindings. No credential value can enter a URL, log, result,
  archive, fixture, or generated projection.
- The application consumes at most one exact recorded observation and one page
  per command. Cursor, maximum-page, rate-limit, retry-delay, circuit-open, and
  terminal decisions are explicit typed state. It contains no sleep, automatic
  loop, worker activation, or network call.
- Every provider/store property, call, and returned value is treated as a
  hostile collaborator boundary. Arbitrary exceptions are reduced to fixed
  non-echoing failure codes, commit ambiguity remains recoverable, and exact
  domain values are reconstructed before outcome/session/failure/receipt/cursor
  cross-field consistency is accepted.
- Duplicate keys, malformed UTF-8, non-finite values, oversized/deep/large JSON,
  unknown output fields, cursor drift, repeated request/response/item identity,
  unsafe URLs, and hostile provider text fail closed. Provider text remains
  `UNTRUSTED_DATA` and is redacted from representations and failures.
- The owner-private SQLite adapter stores raw response bytes as content-addressed
  BLOBs with SHA-256, immutable version, logical key, and receipt. Artifact,
  page metadata, session CAS, and idempotency result journal commit in one local
  Unit of Work. Directory mode `0700`, database mode `0600`, no symlink or
  hardlink, traversal rejection, tamper detection, restart replay, and known or
  unknown commit recovery are enforced. The complete owned `sqlite_master` SQL,
  autoindex inventory, foreign keys, columns, STRICT flags, and schema version
  are exact-bound so same-column constraint weakening also fails closed.
- Recorded synthetic pages exercise the same parser, state transition, archive,
  and replay path. The disabled future HTTP activation port accepts no client,
  credential reader, URL, headers, or ambient environment and always performs
  zero external actions.
- `reviewCount`, `reviewAverage`, `affiliateRate`, commission, EPC, RPM, and
  profit are excluded from the request and recommendation boundaries. Provider-
  derived recommendation inputs are an empty tuple.
- The Product Search offline boundary and predecessor Item Search contracts are
  unchanged. ST-0202, ST-0308, and ST-1404 remain read-only dependencies; this
  Story neither edits their owners nor enables ST-1404 workers.

The contract, sanitized source facts, synthetic fixture, generated projection,
and manifest live under `changes/st-0502/`. The owner generator is
`scripts/build_st0502_item_search_runtime.py`; `--check` is deterministic and
no-write.

Formal TST-014/TST-015, real Rakuten credentials or calls, object cloud storage,
hosted CI, staging, release, and Production remain `NOT_EXECUTED`.

## Focused local check

```bash
.venv/bin/pytest -q -p no:cacheprovider tests/st0502
python scripts/build_st0502_item_search_runtime.py --check
```
