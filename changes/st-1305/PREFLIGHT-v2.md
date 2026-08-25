# ST-1305 V2 preflight

## Story and objective

- Story: `ST-1305` — Finance reconciliation report.
- Objective: implement a deterministic recorded/synthetic internal report that
  reconciles Provider/Canonical/Attribution/Cost totals, preserves unavailable
  states, emits typed exceptions, and returns review-only learning candidates.

## Sources read

- Canonical precedence, decisions, Open Decisions and the ST-1305 Story.
- Analytics/attribution design, policy, KPI catalog and TST-030.
- Security/privacy design, finance data classification, finance RBAC,
  SEC-APP-001, SEC-DATA-003/005/006/007, THR-013/014/019/020/025.
- Integrated ST-1303 attribution and ST-1304 unit-economics domains, ports,
  recorded adapters, contracts, fixtures, owner generators and tests.
- Historical ST-1305 V1 non-executable reference owner and its tests.

## Open decisions and safe defaults

`OD-003`, `OD-005`, `OD-009` and `OD-014` remain unresolved. The runtime accepts
only tracked synthetic fixtures in `ENV-DEV`/`CI`. A real provider file, row
schema, generated/cancelled totals, dry-run/commit hash, labor rate, budget,
retention period, credentials and live authority are not inferred. Missing
values remain `UNAVAILABLE`, never zero.

## Planned ownership

- Provider-neutral reconciliation domain/application port and process-local
  recorded adapter.
- Additive ST-1305 V2 contract, synthetic binding fixture, deterministic report
  projection owner and focused tests.
- Minimal current-byte rebind of the historical ST-1305 V1 owner.

## Verification

- Exact attribution/reward/cost conservation and dependency recalculation.
- Batch counts/totals, unavailable generated/cancelled dimensions, typed
  exceptions and deterministic source-hash evidence.
- Missing, unverified, zero denominator, immature cohort, mixed
  period/program, replay/conflict and fixture-tamper negative paths.
- Structural proof that learning candidates accept only search/view/click/link
  signals and cannot mutate HTML, CTA, products, recommendation order or a
  publication snapshot.
- ST-1303/ST-1304 regressions, both ST-1305 owner checks, Ruff, strict mypy,
  compile, sensitive-term scan and `git diff --check`.

## Out of scope

Provider/network calls, credentials, real report intake, CSV parsing, database,
persistence, public projection, actual business rates or thresholds,
publication/editorial/CTA/product/recommendation/snapshot mutation, formal
TST-030 evidence, live, staging, release and Production.
