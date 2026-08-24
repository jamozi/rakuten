# ST-1602 maximum-safe local SLO and alert runtime V2

Status: `LOCAL_CODE_COMPLETE_CANDIDATE`.

This additive V2 keeps the V1 reference semantics and schema compatible while
refreshing only its drifted implementation-helper provenance, then implements
the reversible local portion of the 14-SLO/20-alert Story. The
owner generator exact-hash binds the canonical SLO, alert, and runbook
catalogs, ST-1601, security/operations controls, OD-011, and the V1 owner
artifacts. The local file-I/O helper used during generation is separately
exact-hash bound and grants no runtime authority. It compiles all catalog rows
into closed typed rules and inert recorded fixtures.

The evaluator accepts only explicit `SYNTHETIC_RECORDED_FIXTURE_ONLY` windows.
No clock, environment discovery, telemetry backend, provider, or autonomous
loop exists. Missing values, malformed numeric observations, immature or stale
windows, and zero denominators become `UNAVAILABLE`/`DATA_BLOCKED`; they never
become zero or PASS. Canonical targets remain provisional, and local PASS
results are not actual SLO-attainment evidence.

Each alert is explicitly bound to the canonical OD-011 owner (`Operations
Owner`) and one semantically selected catalog runbook. The binding is a local,
reversible implementation mapping and does not configure an on-call person,
contact, channel, or escalation destination. Detection strings compile into
closed duration or cycle requirements. No condition string or provider text is
executed.

Alert steps are one-command-at-a-time transitions among `PENDING`, `FIRING`,
and `RESOLVED`. An owner-private SQLite adapter uses exact owned schema SQL,
STRICT tables, SHA-256 chaining, compare-and-swap versions, idempotency,
restart verification, concurrent-write rejection, and exact ambiguous-commit
recovery. Parent directory mode is exactly 0700, the database is exactly 0600,
and symlinks or hard links are rejected. A live adapter pins the file identity
and monotonic verified head; replacement or in-place rollback is rejected for
that adapter lifetime. Cross-restart rollback detection is not claimed because
no external trusted anchor exists. Rows and collaborator return values are
revalidated rather than trusted through Protocol conformance.

OD-011 remains unresolved. The only notification adapter is a bounded local
record log with mode `LOCAL_LOG_ONLY_DISABLED`; it never reads credentials or
ambient environment and has no SMTP, webhook, HTTP, provider, or network
surface. Every external action count is exactly zero and notification delivery
is never claimed.

Owner generation:

```text
python scripts/build_st1602_slo_alert_runtime.py
python scripts/build_st1602_slo_alert_runtime.py --check
```

Formal TST-027/TST-028, hosted CI, a telemetry backend, real metric windows,
notification delivery, owner response, staging, release, and Production remain
`NOT_EXECUTED` or unauthorized. Local code and synthetic tests do not change
the Canonical Story status and do not establish `VALIDATED` or production-ready
evidence.
