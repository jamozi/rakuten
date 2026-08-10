# ST-1301 — Synthetic revenue dry-run reference seam

Classification: `MAXIMUM_SAFE_LOCAL_SYNTHETIC_NON_PERSISTENT_REVENUE_DRY_RUN_REFERENCE_SEAM`

This Story slice is a local reference implementation for reviewing a bounded,
fully synthetic CSV after an exact successful ST-0406 intake. It is partial,
non-authoritative, non-attesting, non-persistent, and ineligible for runtime,
release, or Production use. `SYNTHETIC_DRY_RUN_READY` means only that the local
synthetic preview was constructed; it is not approval, confirmation, provider
mapping evidence, reconciliation, or permission to import facts.

## Authority and predecessor binding

- canonical ST-1301 remains `NOT_STARTED` / `NOT_EXECUTED` outside this local
  implementation-first slice;
- OD-003 remains `EXTERNAL_EVIDENCE_REQUIRED`, blocking, with its exact safe
  default: synthetic fixtures only and real outcome attribution unverified;
- ST-0406 feature commit:
  `587500dfee954f04a937dc9aac3cec81d0f9884c`;
- ST-0305 feature commit:
  `48a807672caa845df8e0251782f00bce8040663b`;
- tests bind the exact current ST-0406 source bytes and the exact ST-0305 and
  canonical revenue schema, job, state-machine, Story, and OD-003 bytes and
  semantics. The inherited ST-0305 manifest drift is not repaired here.

The runtime seam accepts only an exact `ObjectIntakeResult` whose object kind is
`REVENUE_REPORT`, privacy is `SYNTHETIC`, leaf is a safe lower-case `.csv`, MIME
is `text/csv`, quarantine disposition and outcome are `CLEAN_QUARANTINED`,
malware is `CLEAN`, magic/privacy/CSV inspections are `SAFE`, encoding is
`UTF_8`, declared and sealed size/hash agree, formula detection is false, and
the source is `NEW`. `EXACT_DUPLICATE` is rejected before the parser port is
called.

## Exact synthetic format

This is deliberately not a Rakuten report format. The header is exactly:

```text
synthetic_fixture,provider_code,provider_event_key,event_type,event_at,currency,generated_commission_jpy,confirmed_commission_jpy
```

Every row uses marker `RAOS_ST1301_SYNTHETIC_V1`, the canonical vocabulary
constant `RAKUTEN_AFFILIATE`, a `synthetic-event-0000`-shaped key, one of
`GENERATED`, `CONFIRMED`, `CANCELLED`, or `ADJUSTED`, an exact UTC-second `Z`
timestamp, `JPY`, a nonnegative signed-64-bit decimal generated amount, and an
empty or nonnegative signed-64-bit confirmed amount. Input is strict UTF-8
without BOM, LF-only with one terminal LF, bounded to 1 MiB / 10,000 rows /
8 columns / 4 KiB cells, and rejects control characters, blank rows, quoting,
embedded newlines, extra columns, and formula prefixes `=`, `+`, `-`, `@`.

The returned preview exposes only row number, the SHA-256 of the source row
excluding LF, closed parse status/code, and accepted canonical values. It never
exposes raw rows, provider event keys, rejected values, or source text. Exact
repeated rows become `DUPLICATE` and do not affect sums. The same synthetic
event key with different row bytes is `REJECTED`. Confirmed missing values stay
missing and are never converted to zero.

## Closed execution boundary

- parser port: exactly one `parse(command) -> dry_run` exchange;
- adapter: caller-constructed synthetic bytes, exact command, one shot, no
  retry/replay/fallback/history;
- execution: `SYNTHETIC_FIXTURE_ONLY`;
- mapping: `UNVERIFIED`;
- provider total, approval, import/artifact IDs: `null`;
- reconciliation, persistence, audit, outbox, events, TST-026, and TST-030:
  `NOT_EXECUTED`;
- facts: `NOT_CREATED`;
- decision: `NOT_READY`.

No database, repository, unit of work, filesystem, API, job, event, audit,
outbox, credential, provider, network, confirmation, ST-1302, live, staging,
release, or Production capability exists in these modules.

## Local checks

Run with the pinned toolchain and without dependency or environment mutation:

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run --frozen --offline --no-cache --no-sync --no-env-file pytest -q tests/st1301
```

These local tests are implementation evidence only. Formal TST-026/TST-030,
real provider mapping, persistence, live validation, staging, release, and
Production remain unexecuted.
