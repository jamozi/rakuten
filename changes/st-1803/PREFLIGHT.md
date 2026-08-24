# ST-1803 implementation preflight

- Story: `ST-1803` — GATE-2 observation.
- Objective: implement a deterministic local observation and learning boundary
  which consumes one exact, append-only recorded synthetic five-slot input and
  emits a hash-bound, non-attesting GATE-2 pack plus improvement candidates.
- Read before implementation: repository and Canonical `AGENTS.md`; standing
  implementation-first ExecPlan; Canonical integration decisions, open
  decisions, backlog, analytics/attribution design, KPI and event catalogs,
  TST-030/TST-032; upstream GATE-2 criteria; exact ST-1802 and ST-1205
  implementations, owner artifacts, and tests; security/privacy boundaries.
- Ambiguities and safe defaults: OD-004 leaves the live rank/keyword source
  undecided, OD-007 leaves category freshness SLA undecided, and OD-012/OD-015
  block tracking/live providers. The implementation therefore accepts only
  caller-supplied recorded synthetic bytes, uses no live rank provider, treats
  the Canonical provisional GATE-2 thresholds as versioned evaluation inputs,
  and cannot approve the Gate.
- Owned files: `changes/st-1803/**`, `tests/st1803/**`,
  `scripts/build_st1803_gate2_observation.py`, and the additive ST-1803
  domain/application/port/recorded-adapter modules only.
- Tests: strict parsing and event-chain provenance; exact integer/Decimal
  arithmetic; period/program/source/attribution/cohort gates; zero and missing
  denominators; five-slot completeness; unattributed conservation; reward
  isolation from candidates and recommendation order; hostile fields, floats,
  duplicate keys, tampering, replay, redacted failures; single-output atomic
  generation/check/recovery; direct ST-1802/ST-1205 regressions; Ruff, mypy,
  format, secret/static-boundary, and `git diff --check`.
- Out of scope: actual 30–45 article observations, tracking activation,
  credentials, owner-private ledger reads, provider/network calls, article or
  CTA mutation, recommendation changes, publication, Gate approval, Status
  apply, formal TST-030/TST-032, staging, release, deployment, and Production.
