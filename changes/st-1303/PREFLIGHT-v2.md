# ST-1303 V2 preflight

## Story and objective

- Story: `ST-1303` — Attribution engine.
- Objective: implement deterministic Direct / Estimated / Unattributed local
  attribution with method version, input hash, confidence, closed reasons, and
  exact total conservation.

## Sources read

- Canonical integration precedence, decisions, Open Decisions, ST-1303, FR-013.
- Analytics/attribution design, attribution policy, event/KPI catalogs.
- TST-007, TST-030, security/privacy design, THR-014, public/finance isolation.
- Integrated ST-1202 V2 and ST-1302 V2 runtime boundaries.
- ST-1704 five-slot affiliate-learning measurement V2 contract.
- Historical ST-1303 V1 non-executable reference plan and owner tests.

## Open decisions and safe default

`OD-003` remains `EXTERNAL_EVIDENCE_REQUIRED`. No real Rakuten column, key,
timestamp, report mapping, provider compatibility, or attribution accuracy is
asserted. Only a recorded synthetic fixture is executable in `ENV-DEV`/`CI`.

## Planned ownership

- Finance attribution domain/application/port and process-local recorded adapter.
- Additive ST-1303 V2 contract, fixture, generator, projection and tests.
- ST-1303 V2 local completion evidence.

## Verification

- Focused deterministic, hostile, conservation/property, tamper and owner checks.
- Direct ST-1202 and ST-1302 regressions.
- Ruff, strict mypy, in-memory compile, sensitive-term/static and diff checks.

## Out of scope

Provider/network calls, credentials, raw provider rows, personal data, durable
persistence, database migration, event emission, editorial/publication mutation,
staging, release, Production and formal TST status.
