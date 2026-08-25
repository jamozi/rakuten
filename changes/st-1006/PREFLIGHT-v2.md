# ST-1006 V2 preflight

## Story and objective

- Story: `ST-1006` — Public performance and RUM hooks.
- Objective: add a deterministic local performance-budget evaluator, an
  explicit responsive image-reservation policy, a CTA layout-reservation
  check, and a default-disabled RUM hook for the exact recorded public article
  boundary.

## Sources read

- Canonical integration design, canonical/open decisions, Story backlog and
  `TST-027` catalog entry.
- Public UI/UX design, `PUB-003`, public component catalog, analytics/event
  design (`EVT-012`), security controls and threat register.
- Current ST-1002 local SSR contract, runtime and generated fixture; current
  ST-1003, ST-1004 and ST-1005 local boundaries; historical ST-1006 candidate.
- Root and Canonical `AGENTS.md` plus the standing implementation-first
  ExecPlan.

## Ambiguities and safe defaults

- `OD-012` remains unresolved. The public RUM hook is therefore disabled and
  drops input without reading it. No enabled public collection path is added.
- Canonical CWV numbers are targets, not observations. Only a visibly recorded
  synthetic fixture is evaluated locally; field/lab success is not claimed.
- The ST-1002 article currently renders no image and no affiliate CTA. V2 adds
  reusable value-free policies and synthetic checks without modifying that
  route or inventing product/media/CTA data.

## Planned owned changes

- Add an ST-1006 V2 contract, deterministic owner generator, generated
  recorded artifact/runtime manifest, TypeScript runtime, tests, README and
  completion record.
- Add only the minimal `@raos/web-ui` exports needed for the new runtime.
- No migration, route, client component, provider adapter or dependency update.

## Planned checks

- Owner generation and read-only `--check`, focused Node/Python tests, strict
  TypeScript, ESLint/Prettier, direct ST-1002/ST-1006 regression, secret/static
  boundary scan and `git diff --check`.

## Out of scope

Browser `PerformanceObserver`, real RUM, network/beacon/collector, cookies or
storage, consent resolution, real images, product data, live/public traffic,
formal `TST-027`, load/staging, publication, release and Production.
