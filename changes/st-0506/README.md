# ST-0506 disabled headless portfolio/catalog workspace model

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / partial maximum-safe slice

Classification:
`SOURCE_DERIVED_DISABLED_HEADLESS_PORTFOLIO_CATALOG_WORKSPACE_MODEL`

This Story slice provides a dependency-free, headless, deeply frozen JSON
model for the twelve canonical Portfolio and Catalog screens. It is not a
React or Next.js implementation, does not register a route, and cannot
navigate, render, authenticate, load data, perform CRUD, resolve product
identity, expose finance data, issue a command, or execute an effect.

## Exact screen projection

The model preserves canonical order and metadata for `PORT-001..006` followed
by `CAT-001..006`. The only input is `{ screenId }`, and the identifier must be
one of those twelve exact values. Unknown, missing, additional,
accessor-backed, non-JSON, or malformed input is rejected without echoing the
rejected value. Every output is cloned and recursively frozen through the
committed ST-1101 `createJsonValue` boundary.

Canonical roles are display metadata only. They do not grant UI or backend
authorization. All projected routes remain unregistered, navigation and
rendering remain disabled, authorization is false, and the backend must
reauthenticate and reauthorize any future resource access or command.

## Closed runtime boundary

Every model has:

- availability `DISABLED`, route registration `UNREGISTERED`, and decision
  `NOT_READY`;
- data state `NOT_LOADED`, an empty item collection, and an unknown item
  count;
- no actions, CRUD operations, identity decisions, API calls, persistence, or
  effects;
- ETag, If-Match, and lock version unset, with concurrency `NOT_EVALUATED`;
- keyboard operability retained as a requirement while browser, automated
  accessibility, manual keyboard, and screen-reader verification remain
  `NOT_EXECUTED`;
- finance visibility `HIDDEN` with no finance fields or access.

Although `CAT-003` is marked as a critical canonical screen, it remains
actionless. OD-006 is preserved exactly at its safe boundary: automatic merge
and split are false and Human Review is required, but no review, actor,
approval, grouping, membership, merge, or split record exists.

## Source bindings

The model pins the exact committed owned bytes and closed semantics of:

- ST-0501 commit `1021982aff6bcab504e2c060ea0f82797b4dccf2`, a recorded,
  non-persistent workflow seam with sixteen list/create/get/update operation
  shapes and no delete or durable CRUD claim;
- ST-0504 commit `b78b4e3330faadc571207ccec889ba107eaf3bb7`, a
  non-executable OD-006 Human Review plan with automatic merge/split disabled
  and no identity decision or approval;
- ST-1101 commit `6933612a49863591555137868ca0cec935cf65e4`, whose sole
  registered route is the disabled `ADM-001` `/admin` shell.

## Evidence boundary

Focused Node-native model tests are local implementation evidence only.
Formal browser, accessibility, concurrency, authorization, data/API,
identity, finance, CRUD, hosted CI, staging, release, deployment, and
Production verification remain `NOT_EXECUTED`.
