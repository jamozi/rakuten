# ST-1304 V2 preflight

## Story and objective

- Story: `ST-1304` — Cost and unit economics.
- Objective: implement a deterministic recorded/synthetic cost and unit-
  economics runtime with visible source/basis metadata, exact cost and reward
  conservation, and explicit unavailable states.

## Sources read

- Canonical precedence, decisions, Open Decisions, ST-1304 and FR-015.
- Analytics/unit-economics design, KPI catalog, attribution policy and TST-030.
- Security/privacy design, finance classification, THR-014/THR-019 and public
  projection isolation controls.
- Integrated ST-0706 cost-metadata boundary, ST-1205 KPI V2 and ST-1303
  attribution V2, including their contracts, ports, adapters, fixtures and
  tests.
- Historical ST-1304 V1 non-executable reference contract, owner generator and
  tests.

## Open decisions and safe default

`OD-005` and `OD-009` remain unresolved. A labor rate or cost in the tracked
fixture is synthetic implementation data, not a selected reviewer rate,
budget, provider price or Production policy. Missing labor remains unknown and
never becomes zero. Provider/live input, credentials and network access remain
absent.

## Planned ownership

- Provider-neutral unit-economics domain/application port and process-local
  recorded adapter.
- Additive ST-1304 V2 contract, two tracked synthetic fixtures, deterministic
  projection owner and focused tests.
- Mechanical rebind/regeneration of the historical ST-1304 V1 owner so its
  `--check` remains reproducible against current dependency bytes.

## Verification

- Exact reward and cost conservation, source-hash visibility and deterministic
  calculations.
- Missing, unverified, zero-denominator, immature, mixed-period/program,
  unknown-labor, replay/conflict and fixture-tamper negative paths.
- ST-0706/ST-1205/ST-1303 regressions, both ST-1304 owner checks, Ruff,
  strict mypy, compile, sensitive-term scan and `git diff --check`.

## Out of scope

Provider/network calls, credentials, actual business rates or budgets,
persistence/database, public projection, editorial/recommendation/CTA/article
or publication mutation, formal TST-030 evidence, live, staging, release and
Production.
