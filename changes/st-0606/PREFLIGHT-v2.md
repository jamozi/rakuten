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
| ST-0604 lifecycle contract       | `b7144670eab5f12eb79c2f49380d152a4ef5700a030b799878aa147ca563ec2c` |
| ST-0604 generated lifecycle plan | `f465580b8cd484f8abe39225b16d557b2e7df5689f707057f7d59165bc9339eb` |
| ST-0604 manifest                 | `cb3313f3fb5e3460cbc39e2b9a3c64b8e3859c975c58b54e7ca45f59636a2795` |
| ST-0605 runtime contract         | `7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb` |
| ST-0605 recorded runtime fixture | `9a13203bd40b176fe493fe79dd2d9178a08d16c91a3a914c2dbb30fc24a05106` |
| ST-0605 runtime manifest         | `b8e76e4013eb097ba514b7d2cb39f5861c2694acb7cc19919149011ccdc44c41` |
| ST-0605 reference contract       | `b6903a3eaa14108006b6a17477b5bb93116b80bda25c215fba92b2e60859df49` |
| ST-0605 generated reference plan | `015938473428cea3e028f0bc969a8fc290cfe8c87cb0a700383f492821c86142` |
| ST-0605 reference manifest       | `888808d5992dae9da65db7e095157495138b3c612e48336fe163c35b1ff46de8` |
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
