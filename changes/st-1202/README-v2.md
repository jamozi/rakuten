# ST-1202 V2 — default-disabled public instrumentation runtime

## Local result

This additive V2 implementation closes the maximum safe local boundary for
Canonical ST-1202. The exact ST-1002 article route executes a strict server-side
instrumentation boundary on every render. Because OD-012 is unresolved, the
public projection contains no article/snapshot/category identifiers, and
ST-1004 has no verified CTA/offer/link, that boundary deterministically returns
`DISABLED_OD_012`, an empty eligible-event set and no events or effects.

The existing V1 headless requirements candidate remains unchanged. V2 adds a
separate recorded, process-local harness for exactly `EVT-001`, `EVT-002`,
`EVT-003`, `EVT-004`, `EVT-006` and `EVT-012`. It accepts only an exact
synthetic full-consent fixture, while still reporting consent authority as
`UNRESOLVED_OD_012`, tracking activation as `DISABLED`, persistence as
`NOT_EXECUTED` and measurement observed as false.

## Deterministic behavior

- Event envelopes require caller-supplied UUIDv7 identities and normalized UTC
  timestamps; this implementation generates neither.
- Catalog ID, event name, source and ordered parameter set must match exactly.
- Unknown fields, reordered/missing parameters, non-finite values, PII/sensitive
  shapes, URLs/query strings, controls, accessors, symbols, cycles, subclasses
  and unreadable structures fail with closed non-reflecting codes.
- An event ID is accepted once in the exact recorded order. An identical replay
  is a process-local duplicate; the same ID with different bytes is a conflict.
- No event body/history/query surface is exposed by the recorder. Its snapshot
  contains counts only.
- `recordSafely` swallows validation, script and recorded-fault failures. Every
  result states that navigation was neither blocked nor made to await
  instrumentation.

## Navigation and privacy boundary

ST-1004 keeps direct navigation in a native anchor with no client handler and
no measurement dependency. The actual article route has no CTA anchor at all,
so V2 does not invent one. The process-local click fixture uses no URL and does
not navigate. There is no redirect, return URL, beacon, fetch, endpoint,
provider, network, cookie, browser storage, fingerprint, clock, randomness,
credential, database, filesystem persistence or public write.

The Canonical public click operation and ST-1201 canonical-event model remain
non-isomorphic. V2 follows the ST-1201 event envelope only for the recorded
fixture and does not claim to implement or map the public endpoint.

## Owner artifacts

The owner source is
`changes/st-1202/contracts/public-event-instrumentation-runtime.v2.yaml`.
Generate and check the deterministic recorded artifact and manifest with:

```text
.venv/bin/python scripts/build_st1202_public_event_instrumentation.py
.venv/bin/python scripts/build_st1202_public_event_instrumentation.py --check
```

## Authority

This is reversible local implementation evidence only. Formal TST-022 and
TST-030, privacy review/OD-012 resolution, live browser collection, durable
dedupe/persistence, publication, staging, release and Production remain
`NOT_EXECUTED`, unavailable or unauthorized.
