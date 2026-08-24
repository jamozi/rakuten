# ST-0606 V2 implementation preflight

- Story: `ST-0606` — Evidence Workspace UI
- Mode: `STRICT_STORY`
- Integration base: `15c826d141ca04b22fb54dcbf5c8042912a91c32`
- Implementation branch: `codex/st0606-evidence-workspace-v2`
- Recorded at: `2026-08-24` (Asia/Tokyo)
- Scope owner: ST-0606 additive V2 contract, recorded/synthetic fixture, deterministic
  projection, owner generator, headless TypeScript read model, focused tests, and
  ST-0606 implementation records. The only shared-file edit permitted by the
  delegation is the minimal `packages/web-ui/src/index.ts` export.

## Canonical and dependency material read before editing

- `AGENTS.md`
- `docs/canonical/08_codex/AGENTS.md`
- `docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md`
- `docs/canonical/00_master/RAOS_00_master_index_v1.0.md`
- `docs/canonical/00_master/RAOS_01_decisions_registry_v1.0.md`
- `docs/canonical/00_master/RAOS_02_open_decisions_v1.0.md`
- Canonical backlog records for `ST-0604`, `ST-0605`, `ST-0606`, and `ST-1101`
- Current ST-0604 lifecycle contract, generated plan, owner generator, README,
  and manifest
- Current ST-0605 reference/runtime contracts, generated artifacts, runtime
  fixture, owner generators, README, runtime notes, and manifests
- Current ST-1101 route guard, app shell, README, and focused tests
- Existing ST-0606 V1 source, tests, README, and deferred-verification debt
- UI screen, component, workflow, accessibility, and implementation-slice
  catalogs
- `TST-022` and `TST-024` catalogs and the test acceptance/environment/slice
  references
- Role matrix, data-classification rules, security/privacy design, control
  catalog, threat register, and security slices
- `docs/execplans/RAOS-IMPLEMENTATION-FIRST.md`

## Exact dependency anchors at preflight

| Binding                          | SHA-256                                                            |
| -------------------------------- | ------------------------------------------------------------------ |
| ST-0604 lifecycle contract       | `a80c41890e6bae7077728d1456f5a3b5d99b1877e047f581beff8ed41e0c2cec` |
| ST-0604 generated lifecycle plan | `00e6e974f9003ee92cb0a9b4a0ca5a975286e7fd41a6e32cf1224e312cd78cec` |
| ST-0604 manifest                 | `56144e0b9ab315a647d92c665f7502129d3576fac2d9524ca647dc29bfeabdc0` |
| ST-0605 runtime contract         | `7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb` |
| ST-0605 recorded runtime fixture | `eb1c36bd1f70ea27e57e1720b937211286578136e701664b5fb4c8c823395226` |
| ST-0605 runtime manifest         | `1bdc789e2faed53a66c3d6605a7fe0d4d842a21799c3a6202b02e3231eac3efb` |
| ST-0605 reference contract       | `3eb1bccf5e6b2599690e2c9cdd2490dc0a2177e41689f8955c0bc1dfb8e068f2` |
| ST-0605 generated reference plan | `820ca8cb8e302adc862be95ad9e6ca59f30ca8795ba0191018b99407aae08d74` |
| ST-0605 reference manifest       | `c6d79d4d566ec1bc2a3268cf3394ec5c9f4bb27a335466f12be0a87cef9e1573` |
| ST-1101 route guard              | `8395f542c7c65445fa3d1bec4a0e037c96610da8589e1807604b4fb3fa6a584f` |
| ST-1101 README                   | `b2bb91e89d5948f8081853e39596951adcee16974ce2a6ffa159892310ead08c` |

## Safe implementation decision

OD-010 leaves the production authentication transport unresolved. Therefore V2
is a deterministic, recorded/synthetic, headless read projection only. All four
canonical EVD screens remain unregistered. Authentication, authorization,
backend/data/network access, user actions, mutation, persistence, publication,
and rendering authority remain disabled. Role metadata is display-only and is
never interpreted as an access decision.

ST-0604 remains the lifecycle authority and currently exposes no ready packet;
that absence stays explicit as `UNAVAILABLE`/`UNKNOWN`/`null`. ST-0605 recorded
synthetic evaluation data may be projected only with exact report and attestation
provenance and must be labelled non-live and non-publication-authoritative. Known
recorded empty collections may remain zero; missing, unevaluated, conflicting, or
live-freshness values must never be converted to zero or pass.

## Hard stops and completion boundary

- No route activation or auth-transport choice.
- No live provider, credential, browser, network, backend, database, form,
  publication, staging, release, or Production operation.
- No finance, affiliate compensation, profit, EPC/RPM, or recommendation-ranking
  input in the evidence projection.
- No `VALIDATED`, formal `TST-022`/`TST-024`, staging, runtime, or Production
  evidence claim.
- Local completion requires deterministic owner `--check`, focused positive and
  hostile tests, TypeScript checks, dependency regressions, secret scan, and
  `git diff --check`; formal/live work remains `NOT_EXECUTED`.
