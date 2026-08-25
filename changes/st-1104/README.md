# ST-1104 analytics and finance workspace

Status: `LOCAL_CODE_COMPLETE` / additive V2 recorded headless read model

The additive V2 executes only in `ENV-DEV` or `ENV-CI`. It projects the current
ST-1205 recorded KPI snapshot and ST-1304 recorded unit-economics result into the
six canonical `ANA-001..003` and `FIN-001..003` screen models. Every metric carries
its exact source Story, source digest, period boundary, attribution basis,
freshness state, verification state, and explicit availability. The V2 projection
is process-local, synthetic, confidential, and non-attesting.

The predecessor closure is semantically rebound to ST-1101
`bae6de32505705d78e07d2d1b31ff67aaefa69dc`, ST-1205
`9d504b5bafaa3e07b6214b44bc64f11d302335ff`, and ST-1304
`d2eddc34e3889ace7fe90dde3a5182994822c385`. The ST-1304 binding includes its
stricter byte-for-byte work-minute and incremental-cost measurement provenance;
the dashboard still consumes only the already verified immutable result.

The two dependency fixtures cover different periods. V2 records
`UNAVAILABLE_PERIOD_MISMATCH` and never combines their values. ST-1205's exact
recorded timestamp and upstream freshness label are visible. ST-1304 declares no
approved freshness policy, so its freshness is `UNKNOWN`; the implementation does
not invent a threshold or label the data current/stale. Missing, unverified, and
zero-denominator upstream values remain `UNAVAILABLE` with `null` values. An
explicit verified zero remains available as zero.

`FIN-001` remains `UNAVAILABLE_DEPENDENCY`: ST-1301 is not a declared ST-1104
dependency and V2 does not invent CSV intake or commit authority. `FIN-002` shows
only the ST-1304 synthetic reward-conservation view, keeping provider, Direct,
Estimated, and Unattributed totals separate. `FIN-003` preserves the basis of each
recorded unit-economics metric. No finance value is a recommendation, editorial,
CTA, product-selection, article, or publication input.

The existing V1 implementation below remains compatible and unmodified. V2 adds
a Python domain/application/port/recorded-adapter boundary, a versioned contract,
strict synthetic fixture, generated JSON read model, immutable TypeScript wrapper,
and provenance manifest. Generate and verify with:

```text
.venv/bin/python scripts/build_st1104_analytics_finance_dashboard.py
.venv/bin/python scripts/build_st1104_analytics_finance_dashboard.py --check
```

ST-1101 authentication remains disabled; V2 registers no route or DOM and grants
no role authority. Upload, reconciliation commit, provider/network/credential,
database/persistence, telemetry, public projection, publication, staging, release,
and Production are impossible at this boundary. Formal TST-022/TST-024/TST-030,
browser, keyboard, zoom, screen-reader, live, staging, release, and Production
remain `NOT_EXECUTED`.

## Historical V1 static disabled metadata

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / headless metadata-only partial safe slice

This reversible implementation adds a deterministic, detached, deeply frozen,
JSON-safe candidate for the approved `ST-1104` objective. It records the exact
canonical `ANA-001..003` and `FIN-001..003` screen catalog metadata without
registering a route, rendering a screen, loading data, or exposing an action.
Canonical Story, implementation, and verification status remains unchanged.

## Implemented boundary

- accepts only the exact `{screenId}` field shape on ordinary plain data;
- preserves screen ID, name, route, area, role display metadata, purpose, MVP,
  the canonical false critical-action flag, empty API dependency list, and
  canonical status;
- fixes every catalog route and the selected route to unregistered;
- keeps component and dashboard metadata empty and explicitly marks both
  ownership mappings as `NOT_INFERRED`;
- fixes KPI, basis, freshness, quality, import, reconciliation, and unit-economics
  slots to `NOT_LOADED` or `NOT_EVALUATED` with only `null` or empty payloads;
- records Data source, period, Freshness, Basis, Quality, and Unknown visibility
  as requirements only, with rendering and verification false;
- forbids converting Unknown to zero, an empty value, or a guess, and preserves
  unknown labor cost as `UNKNOWN` with a null value;
- exposes no actions, effects, intents, callbacks, executable values, file
  contents, metric values, financial amounts, rows, formulas, or runtime surface;
- strictly validates input and complete candidates with closed, non-echoing
  failure codes and rejects hostile object shapes, duplicate catalog IDs or
  routes, prohibited data/ownership/authority surfaces, and authority escalation.

The dependency-free, browser-neutral validator rejects accessors, classes,
symbols, cycles, callback values, and unreadable throwing or revoked proxies.
Standard JavaScript reflection cannot distinguish a transparent forwarding
proxy from its plain target without invoking traps. Proxy-bearing input is
therefore outside the ordinary-data trust boundary; validation may invoke its
traps. Once validation returns, the candidate is detached, pure JSON data with
no caller callback or executable surface.

The catalog role lists are display metadata only. They are not authentication,
authorization, MFA, assignment, or step-up evidence. The screen catalog's
`FIN-001 critical_action=false` value is retained verbatim. The separate
canonical CSV Commit critical-action requirement is recorded only as unavailable
policy metadata; no upload, dry run, reconciliation, confirmation, or commit is
offered.

## Dependency, finance, and privacy boundary

- `ST-1101` remains a disabled headless foundation with no route authority.
- `ST-1205` is consumed only as a non-executable reference plan: definitions are
  30/30, calculations 0/30, verified calculations 0/30, decision `NOT_READY`,
  and no KPI value is available.
- `ST-1304` is unavailable; unresolved `OD-005` and `OD-009` remain visible,
  labor cost stays `UNKNOWN` rather than zero, and no EPC, RPM, profit, cost,
  allocation, or read-model value is supplied.
- `OD-003` retains synthetic-only, real-attribution-unverified behavior;
  `OD-012` keeps nonessential tracking disabled; `OD-014` keeps minimal
  collection and automatic deletion disabled; `OD-015` permits recorded
  fixtures only.
- `UI-WF-008` is reference-only and remains `NOT_STARTED` / `NOT_EXECUTED`.
  No file intake, security scan, schema detection, dry run, reconciliation,
  human confirmation, duplicate defense, formula defense, or commit is claimed.
- Finance data remains `CONFIDENTIAL`; no Public exposure/projection, editorial
  recommendation input, financial value, Provider row, personal data, or Secret
  is present.

Authentication, authorization, MFA, step-up, mutation, file intake, network,
persistence, telemetry, runtime, external action, publication, release, and
Production authority are all false. Formal, browser, live, staging, release,
publication, and Production work is `NOT_EXECUTED`; runtime and accessibility
are `NOT_VERIFIED`. `TST-022`, `TST-024`, dependency `TST-030`, Story acceptance,
and Story completion are not claimed.

## Accessibility and frontend-skill influence

Text plus icon status, non-color-only presentation, table captions/headers/scope,
chart table-or-text alternatives, financial-action confirmation or correction,
and loading/success/failure announcements are requirements only. No DOM,
keyboard interaction, screen-reader behavior, visual rendering, or audit has
been executed.

This is an operational analytics/finance utility surface, so the frontend-skill
was applied as a headless restraint boundary: honest unavailable states and
utility semantics take precedence over marketing copy or decorative composition.
No hero, cards, chart, layout, imagery, motion, color system, component, DOM, or
visual hierarchy is invented by this slice.

## Local tests

The five focused Node-native suites cover exact catalog metadata, deterministic
detachment and deep freezing, unavailable dependencies and authority, explicit
Unknown and finance-isolation boundaries, requirements-only accessibility, and
hostile/invalid input and candidate tampering. Local results are implementation
evidence only and are not formal `TST-022`, `TST-024`, or `TST-030` execution.

Completed local checks, using the already hydrated pinned root toolchains
without dependency synchronization:

- focused `tests/st1104_v2`: PASS, 16/16 ordinary and denied-network;
- focused `tests/st1104/*.test.ts`: PASS, 21/21 ordinary and denied-network;
- strict `packages/web-ui` TypeScript: PASS;
- affected `tests/st1101/*.test.ts`: PASS, 34/34 ordinary and denied-network;
- ST-1205 owner no-write check and `tests/st1205`: PASS, 57/57 ordinary and
  denied-network;
- both ST-1304 owner no-write checks plus `tests/st1304` 492/492 and
  `tests/st1304_v2` 51/51: PASS ordinary and denied-network;
- Ruff check/format, strict mypy, repository Pyright, Python compile, ESLint,
  Prettier, and `git diff --check`: PASS;

The linked-worktree scanner intentionally rejects `.git` indirection. The
authoritative full worktree-and-history scan therefore runs after commit in a
physical clone checked out at the exact Story SHA with the V3 reviewed-finding
ledger; its result is reported with that SHA rather than embedded into this
self-referential owner manifest.
