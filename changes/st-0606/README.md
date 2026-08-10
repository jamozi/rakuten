# ST-0606 disabled headless evidence workspace model

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
