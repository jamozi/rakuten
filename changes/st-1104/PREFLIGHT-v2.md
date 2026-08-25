# ST-1104 V2 preflight

## Story and objective

- Story: `ST-1104` — Analytics/finance UI.
- Objective: implement a deterministic, headless, recorded/synthetic read-model
  boundary for the six canonical `ANA-*` and `FIN-*` screens. Every metric must
  expose its source, period, basis, freshness state, and verification state;
  unavailable facts must remain unavailable rather than becoming zero.

## Sources read

- Canonical precedence, decisions, Open Decisions, and ST-1104 with declared
  dependencies ST-1101, ST-1205, and ST-1304.
- UI design, screen/component/workflow catalogs, accessibility checklist,
  analytics design, dashboard/KPI catalogs, security/privacy design, role matrix,
  data classification, security controls, and TST-022/TST-024.
- Current ST-1101 disabled route guard at
  `bae6de32505705d78e07d2d1b31ff67aaefa69dc`, historical ST-1104 V1 metadata
  candidate, ST-1205 recorded KPI runtime at
  `9d504b5bafaa3e07b6214b44bc64f11d302335ff`, and ST-1304 recorded
  unit-economics runtime at
  `d2eddc34e3889ace7fe90dde3a5182994822c385`.

## Open decisions and safe defaults

- `OD-003`: revenue data remains synthetic and real attribution is unverified.
- `OD-005` and `OD-009`: fixture labor/cost values are synthetic test data, not
  selected business rates or budgets. Missing labor/cost remains unavailable.
- `OD-010`: ST-1101 authentication transport remains disabled. No route or
  authorization is established.
- `OD-012`, `OD-014`, and `OD-015`: nonessential tracking stays disabled, no new
  retention behavior is enabled, and only recorded fixtures are consumed.
- There is no approved analytics freshness threshold. The read model exposes
  exact recorded timestamps and the upstream freshness label, but never infers
  `CURRENT` or `STALE`.

## Planned ownership

- Additive Python domain/application/port/recorded-adapter modules for an
  immutable process-local dashboard snapshot.
- Versioned ST-1104 V2 contract and strict synthetic scenario fixture.
- Deterministic owner generator for a JSON projection, immutable TypeScript
  wrapper, and provenance manifest.
- Focused Python and Node tests plus local completion documentation.

## Verification

- Exact six-screen projection, canonical dashboard references, source period,
  basis, freshness, verification, explicit unavailable and verified-zero states.
- Period mismatch, missing/unverified value, zero denominator, fixture tamper,
  adapter mismatch, nonlocal environment, authority escalation, and public/
  editorial isolation negative paths.
- Owner generation/no-write check, ST-1101/ST-1205/ST-1304 regressions, Ruff,
  strict mypy, Pyright, Python compile, TypeScript compile, ESLint, Prettier,
  ordinary plus denied-network execution, post-commit exact-SHA physical-clone
  secret scanning, and `git diff --check`.

## Out of scope

Authentication bypass, route registration, DOM/browser rendering, upload or CSV
intake, import/reconciliation commit, network/provider/credential/database/
persistence access, telemetry, financial allocation, recommendation/editorial/
CTA/product/article/publication mutation, formal TST-022/TST-024/TST-030, live,
staging, release, and Production.
