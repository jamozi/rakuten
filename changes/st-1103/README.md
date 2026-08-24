# ST-1103 freshness and operations workspace

Status: `LOCAL_IMPLEMENTATION_COMPLETE` / additive V2 recorded headless runtime

The additive V2 closes the locally executable portion of the approved Story.
It projects exact recorded ST-1401 freshness evaluations and exact recorded
ST-1404 job states into all eight canonical `FRESH-001..003` and
`OPS-001..005` screen models. Screens whose data owner is not a declared Story
dependency remain explicitly `UNAVAILABLE_DEPENDENCY`; they are never shown as
zero or empty-success. The historical V1 disabled metadata model remains byte
compatible.

The owner generator binds the V2 fixture to exact Canonical UI, Operations,
Security, Test, Story, ST-1101, ST-1401, and ST-1404 source hashes. It emits a
canonical JSON projection, an immutable TypeScript string wrapper, and a
complete runtime manifest through the repository's foreign-preserving atomic
publication helper. `--check` detects source or generated drift.

V2 status and tables carry text, code, and icon cues with `colorOnly: false`,
captions, column headers, an explicit row-header column, keyboard requirements,
and a 200% zoom target. These are executable headless semantics, not a claim
that DOM, browser, keyboard, zoom, or screen-reader verification ran.

Safe actions are limited to closed, metadata-only human-review request intents
for exact recorded target fingerprints and closed reason codes. They have no
callback, dispatch, persistence, retry, cancellation, redrive, kill-switch,
publication, or Production authority. DLQ redrive and Kill Switch changes are
blocked at the interface boundary. `OPS-004` records all future critical-action
requirements, including step-up, but establishes none of them.

Canonical Story status is unchanged. Routes remain unregistered because the
ST-1101 authentication transport is disabled. Formal `TST-022` and `TST-024`,
live data, staging, release, publication, and Production remain
`NOT_EXECUTED`.

## Historical V1 compatibility boundary

This reversible implementation adds a deterministic, detached, deeply frozen,
JSON-safe candidate for the approved `ST-1103` objective. It records the exact
canonical `FRESH-001..003` and `OPS-001..005` screen catalog metadata without
registering a route, rendering a screen, loading data, or exposing an action.
Canonical Story, implementation, and verification status remains unchanged.

### Implemented boundary

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

### Dependency and authority boundary

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

## Local tests

The historical and V2 Node-native suites cover exact catalog metadata,
recorded projections, deterministic detachment and deep freezing, unavailable
dependencies, status semantics, effect-free review intents, authority denial,
generator binding, and hostile/tampered input. The Python generator suite
recomputes all owner outputs. Local results are implementation evidence only
and are not formal `TST-022` or `TST-024` execution.

Completed local checks, using the already hydrated pinned root toolchain
without dependency synchronization:

- focused `tests/st1103/*.test.ts`: PASS, 30/30;
- owner generator `--check`: PASS;
- `tests/st1103/test_generation.py`: PASS, 3/3;
- strict root TypeScript project: PASS;
- affected `tests/st1101/*.test.ts tests/st1102/*.test.ts`: PASS, 54/54;
- recorded freshness dependency `tests/st1401`: PASS, 166/166;
- isolated recorded-only dependency `tests/st1404`: PASS, 42/42;
- ESLint on all owned TypeScript sources and tests: PASS;
- Prettier on all owned source, test, contract, and evidence paths: PASS;
- Ruff check and format-check on the generator and Python test: PASS;
- strict mypy on the generator and Python test: PASS;
- `make check-workspace`: PASS, zero changed paths across 42 directories;
- canonical import verification: PASS, 105 imported files, 104 checksums, and
  103 manifest entries;
- `git diff --check`: PASS.

The repository scanner's exact detection rules were also applied to every
changed or newly added ST-1103 path and returned no finding. A complete non-Git
snapshot scan additionally identified existing findings outside ST-1103 in the
ST-0502/ST-1703 surface. They are not suppressed or misreported here and remain
an integration-level remediation item before the final repository-wide gate.
