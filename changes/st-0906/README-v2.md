# ST-0906 V2 — executable local publication-review workspace

Status: `LOCAL_IMPLEMENTATION_COMPLETE` for the maximum-safe local boundary.
Canonical Story status and formal/live status are unchanged.

## Preflight and implemented boundary

The selected Story is `ST-0906`: render the seven Canonical `REV-001..003`
and `PUBA-001..004` review/publication screens with approval, immutable
snapshot, diff, isolated preview, command, and audit state. The implementation
reads the Canonical Story, UI design/screen/component/workflow catalogs,
TST-022/TST-024, the security design/control/role matrix, and the exact current
ST-0901 through ST-0905 recorded V2 fixtures. OD-005, OD-007, OD-008, and
OD-010 remain unresolved; their safe defaults continue to block real
publication and external Admin access.

V2 adds:

- a hash-bound, owner-generated recorded-synthetic projection of the exact
  ST-0901 review, ST-0902 final approval, ST-0903 immutable snapshot,
  ST-0904 public projection, and ST-0905 command/audit states;
- a closed, deeply frozen TypeScript view-model for all seven screens;
- a deterministic standalone semantic-HTML renderer with a skip link, one
  `h1`, labelled landmarks, textual status, a captioned/labelled diff table,
  isolated text-only preview, audit timeline, and explicitly disabled actions;
- strict candidate/input validation and hostile/tamper tests; and
- a deterministic owner contract, generator, generated fixture/wrapper,
  content-addressed manifest, and no-write `--check` mode.

The renderer is callable from Node for a local recorded test harness. It is not
registered in Next.js, the Admin route registry, or any HTTP server. No public
or Admin route is added. The existing ST-1101 shell remains disabled because
OD-010 has no approved OIDC transport.

## Command and authority boundary

Every publish, unpublish, and rollback control is rendered disabled. The model
does not expose a callback, command payload builder, transport, or dispatch
function. A future effect may target only the exact ENV-DEV/CI process-local
`ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2` adapter and must re-establish an
active human, Canonical role, site scope, MFA, step-up, separation of duties,
final approval, immutable snapshot/source binding, kill-switch safe state,
reason, idempotency, and audit gates at the backend boundary. Unpublish remains
deny-by-default because the Canonical role matrix defines no unpublish action.

The displayed ST-0905 publish and rollback records are historical recorded-
synthetic intent evidence only. Their audit/outbox records are not persisted,
events are not emitted, routes are not activated, and no public state changes.

## Data and accessibility boundary

Only the closed ST-0904 public text projection plus synthetic identifiers,
hashes, state codes, and non-durable audit metadata enter the rendered model.
Raw article/source/prompt material, review bodies, finance, revenue,
commission, credentials, tokens, arbitrary HTML, provider data, and personal
data are absent. Every dynamic value is HTML-escaped.

Local model/render tests exercise deterministic bytes, focus order, keyboard-
reachable skip navigation, heading/landmark/table semantics, 200% zoom-friendly
layout rules, disabled-action explanations, and hostile tamper rejection. They
do not establish browser, NVDA/VoiceOver, manual accessibility, formal
TST-022/TST-024, authentication, authorization, staging, publication, release,
or Production evidence. Those remain `NOT_EXECUTED`.

## Owner generation

```text
.venv/bin/python scripts/build_st0906_publication_review_workspace_v2.py
.venv/bin/python scripts/build_st0906_publication_review_workspace_v2.py --check
```

The V1 static/headless candidate is retained byte-for-byte for compatibility.
No Canonical file, status registry, route, migration, API contract, database,
provider, CMS, `.playwright-cli`, or runtime manifest owned by another Story is
modified.
