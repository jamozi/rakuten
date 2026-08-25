# ST-0606 evidence workspace

Status: `LOCAL_CODE_COMPLETE` / additive V2 recorded headless read projection

The additive V2 consumes the ST-0604 lifecycle provenance finalized at
`89d8074951ce73a5c76ca55f0ea3b2c129559d81` and the ST-0605 coverage
provenance finalized at `160e5d4e210a35b216395c1bdf16b9c664ecc8e7`.
It projects typed Source, Fact, Conflict, Coverage, Claim–Evidence Matrix, and validation
attestation read models for the canonical `EVD-001..004` screens. ST-0605's
report and every attestation are bound by exact kind, subject digest, input
digest, contract version/digest, owner, and decision digest. ST-0604 remains the
lifecycle authority and currently reports no ready Packet.

This is an `ENV-DEV`/`ENV-CI` recorded/synthetic model only. It does not expose
source body bytes or URLs. Recorded ST-0605 coverage is labelled non-live and
non-publication-authoritative. Current lifecycle absence, current freshness,
and other unevaluated values remain `UNAVAILABLE`, `UNKNOWN`, or `null`; they
are never converted to zero or pass. The known empty Conflict collection in the
fixed fixture is separately labelled and may accurately report zero.

Each displayed Fact and Claim–Evidence Matrix row has a deterministic semantic
focus path to its Source metadata in at most two steps. The screen contract
defines a skip link, one H1, a main landmark, labelled sections, text-plus-icon
status, table captions and column/row scope, and keyboard order. No DOM or route
is activated, so browser, keyboard, zoom, and screen-reader evidence remains
`NOT_EXECUTED`.

OD-010 remains unresolved. All four EVD routes are unregistered, role metadata
is display-only, and authentication, authorization, backend data, network,
actions, mutation, persistence, publication, activation, staging, release, and
Production authority are false. Affiliate compensation, commercial-performance,
and recommendation-ordering inputs are prohibited from the projection.

Generate and verify the owner artifacts with the pinned local Python runtime:

```text
.venv/bin/python scripts/build_st0606_evidence_workspace_v2.py
.venv/bin/python scripts/build_st0606_evidence_workspace_v2.py --check
```

The generated JSON and TypeScript string constant must not be edited manually.
The committed V1 implementation below remains compatible and unchanged.

## Historical V1 disabled model

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / partial maximum-safe slice

Classification:
`SOURCE_DERIVED_DISABLED_HEADLESS_EVIDENCE_WORKSPACE_MODEL`

This Story slice provides a dependency-free, headless, deeply frozen JSON
model for the four canonical evidence-workspace screens. It is not a React or
Next.js implementation, does not register a route, and cannot navigate,
render, authenticate, load data, issue a command, or perform an effect.

## Exact screen projection

The model preserves the canonical order and metadata of:

1. `EVD-001` — Source Packet一覧
2. `EVD-002` — Source Packet詳細
3. `EVD-003` — Fact Explorer
4. `EVD-004` — Evidence Conflict Queue

The only model input is `{ screenId }`, where `screenId` must be exactly one
of those four closed values. Unknown, missing, additional, accessor-backed,
non-JSON, or malformed input is rejected without echoing its value. Output is
cloned and recursively frozen through the committed ST-1101
`createJsonValue` boundary.

## Disabled boundary

ST-1101 registers only the disabled `ADM-001` `/admin` shell. Every EVD route
remains unregistered. Consequently every projected screen has:

- availability `DISABLED` and route registration `UNREGISTERED`;
- navigation, rendering, authorization, data access, and actions disabled;
- backend reauthentication and reauthorization still required;
- data state `NOT_LOADED`, an empty item collection, and an unknown item
  count;
- decision `NOT_READY`.

Accessibility requirements are retained as requirements, not evidence.
Browser, automated accessibility, manual keyboard, and screen-reader
verification all remain `NOT_EXECUTED`.

## Source bindings

The model pins the exact owned bytes and closed semantics of:

- ST-1101 commit `6933612a49863591555137868ca0cec935cf65e4`, whose sole
  registered route is the disabled `/admin` shell;
- ST-0604 commit `24e9640f7fa2b681ea40bb539837e40403928ec8`, whose Source
  Packet lifecycle remains empty, unapproved, and `NOT_READY`;
- ST-0605 commit `72541b0e855954005231368e48a7811abe4b3ea4`, whose Claim,
  Fact, and evidence-link collections remain empty, coverage is unevaluable,
  vocabulary mapping is unavailable, and publication is forbidden.

The slice does not infer ownership or behavior from `EDT-006`, `CAT-006`, or
`UI-C021`. Those identifiers are not part of this model.

## Evidence boundary

Focused Node-native model tests are local implementation evidence only.
Formal browser, accessibility, authentication, backend, data, API, hosted CI,
staging, release, deployment, and Production verification remain
`NOT_EXECUTED`.
