# ST-1103 freshness and operations workspace static disabled metadata

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / headless metadata-only partial safe slice

This reversible implementation adds a deterministic, detached, deeply frozen,
JSON-safe candidate for the approved `ST-1103` objective. It records the exact
canonical `FRESH-001..003` and `OPS-001..005` screen catalog metadata without
registering a route, rendering a screen, loading data, or exposing an action.
Canonical Story, implementation, and verification status remains unchanged.

## Implemented boundary

- accepts only the exact `{screenId}` field shape on ordinary plain data;
- preserves screen ID, name, route, area, role display metadata, purpose, MVP,
  critical-action flag, empty API dependency list, and canonical status;
- fixes every catalog route and the selected route to unregistered;
- keeps component metadata empty and explicitly marks component ownership as
  `NOT_INFERRED` because no canonical screen-to-component mapping exists;
- fixes primary/status/item/evidence slots to `NOT_LOADED` or `NOT_EVALUATED`
  with only `null` or empty payloads;
- records text, code, and icon status cues plus the no-color-only rule as
  requirements only, with rendering and verification false;
- exposes no actions, effects, intents, callbacks, executable values, or
  runtime surface;
- strictly validates input and complete candidates with closed, non-echoing
  failure codes and rejects hostile object shapes, duplicate catalog IDs or
  routes, prohibited payload/component/authority surfaces, and authority
  escalation.

The dependency-free, browser-neutral validator rejects accessors, classes,
symbols, cycles, callback values, and unreadable throwing or revoked proxies.
Standard JavaScript reflection cannot distinguish a transparent forwarding
proxy from its plain target without invoking traps. Proxy-bearing input is
therefore outside the ordinary-data trust boundary; validation may invoke its
traps. Once validation returns, the candidate is detached, pure JSON data with
no caller callback or executable surface.

The catalog role lists are display metadata only. They are not authentication,
authorization, assignment, or step-up evidence. `OPS-004` remains catalogued as
critical but has no action or action intent.

## Dependency and authority boundary

- `ST-1401` and unresolved `OD-007` remain `UNAVAILABLE`; no freshness policy,
  SLA, state, or scheduling truth is inferred.
- `ST-1404` is consumed as `RECORDED_ONLY` metadata and provides no runtime
  authority, job data, retry, cancellation, lease, DLQ, or queue execution.
- `OPS-004` depends on unavailable `ST-1405`; kill-switch authority is
  `UNDECLARED` and no step-up or mutation is offered.
- `OPS-005` audit source/ownership is `UNDECLARED` and `UNAVAILABLE`; no audit
  query or immutable-event claim is made.

Authentication, authorization, step-up, mutation, network, persistence,
runtime, external action, publication, release, and Production authority are
all false. Formal, live, staging, release, publication, and Production work is
`NOT_EXECUTED`; runtime and accessibility are `NOT_VERIFIED`. The Story
acceptance criteria and Story completion are not claimed.

## Frontend-skill influence

This is an operational utility surface, so the frontend-skill was applied as a
headless restraint boundary: utility/status semantics take precedence over
marketing copy or decorative composition. No hero, card layout, imagery,
motion, color system, component, DOM, or visual hierarchy is invented by this
slice.

## Local tests

The five focused Node-native suites cover exact catalog metadata, deterministic
detachment and deep freezing, unavailable dependencies and authority,
requirements-only accessibility, and hostile/invalid input and candidate
tampering. Local results are implementation evidence only and are not formal
`TST-022` or `TST-024` execution.

Completed local checks, using the already hydrated pinned root toolchain
without dependency synchronization:

- focused `tests/st1103/*.test.ts`: PASS, 17/17;
- strict `packages/web-ui` TypeScript: PASS;
- strict standalone TypeScript for all five owned tests: PASS;
- affected `tests/st1101/*.test.ts tests/st1102/*.test.ts`: PASS, 54/54;
- isolated recorded-only dependency `tests/st1404`: PASS, 42/42;
- ESLint on the two owned package paths and five tests: PASS;
- Prettier check on all eight owned paths: PASS;
- `make check-workspace`: PASS, zero changed paths across 42 directories;
- canonical import verification: PASS, 105 imported files, 104 checksums, and
  103 manifest entries;
- `git diff --check`: PASS.

The unchanged secret scanner rejects linked-worktree Git metadata fail-closed
with `ERROR code=unsafe-git-metadata source="."`. As in the committed ST-1102
pattern, a complete non-Git `git archive HEAD` snapshot was overlaid with only
the exact eight owned paths after `cmp --silent` verified every byte; the
scanner's full fallback traversal then passed with no findings.
