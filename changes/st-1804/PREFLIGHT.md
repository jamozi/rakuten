# ST-1804 preflight

1. **Story/objective** — `ST-1804`, evaluate confirmed outcomes, cost and
   profit in a GATE-3 pack without making a Gate decision.
2. **Read** — Canonical integration precedence/decisions/open decisions,
   ST-1804 and dependencies, analytics/attribution/KPI designs, GATE-3
   requirements, TST-030/TST-032, finance RBAC, security controls/threats,
   and the current ST-1803/ST-1305 runtime contracts and projections.
3. **Ambiguities/open decisions** — OD-003 has no real Rakuten report sample;
   OD-005 has no approved reviewer/hourly cost; OD-009 and OD-014 retain safe
   defaults. ST-1803 and ST-1305 recorded vectors cover different periods.
   None is silently resolved.
4. **Owned implementation** — one additive versioned contract, strict
   caller-bytes synthetic fixture, deterministic domain/port/application/
   adapter, single-output generator, tests, README and local completion record.
5. **Verification** — contract/source binding, exact arithmetic, availability
   propagation, attribution conservation, mutation/authority negative paths,
   adapter hostility/replay, owner `--check`, Ruff, strict mypy, compile,
   focused secret scan and `git diff --check`.
6. **Out of scope** — real 30–45 article pilot, actual observation cycles,
   provider/report/credential/network/database access, owner-private ledger,
   finance UI/public projection, publication, Gate approval, Scale/Hold/Pivot,
   staging, release and Production.
