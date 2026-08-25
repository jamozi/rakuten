# ST-1202 V2 implementation preflight

- Story/objective: `ST-1202` — implement deterministic public event
  instrumentation without allowing collection to delay direct affiliate
  navigation.
- Inputs read: repository and Canonical `AGENTS.md`; integration precedence,
  decisions and open decisions; ST-1202 and dependencies ST-1002/ST-1004/
  ST-1201; FR-013; RAOS-ANALYTICS-001, the event catalog and AN-SLICE-002;
  OD-012; SEC-DATA-007/THR-025; and TST-022/TST-030.
- Safe resolution: OD-012 remains unresolved, so the real local article route
  executes only a server-side disabled boundary. It has no public article,
  snapshot, category, CTA or offer identity and ST-1004 has no verified CTA.
  No event can therefore be constructed on that route. A separate exact
  synthetic fixture exercises schema validation, process-local idempotency and
  swallowed failures while tracking and persistence remain disabled.
- Planned owned files: additive V2 implementation/exports in `packages/web-ui`,
  one no-effect server route assertion in `apps/web`, ST-1202 owner contract,
  deterministic recorded fixture/manifest, generator, focused tests and local
  completion docs.
- Local checks: V1/V2 Story tests, owner generation/check, dependency suites,
  strict TypeScript, Next build, ESLint/Prettier, Ruff/mypy for the owner,
  sensitive-data scan and `git diff --check`.
- Out of scope: a browser client, IDs/timestamps/session generation, consent UI
  or policy, cookies/storage/fingerprinting, `sendBeacon`, fetch/endpoint,
  provider/network/DB/durable persistence, a real CTA or affiliate URL,
  publication, staging, release, Production and formal TST execution.
