# ST-0403 deny-default authorization runtime

Status: `LOCAL_CODE_COMPLETE`

This Story implements the repository-local authorization boundary without
granting live, provider, publication, service-principal, or Production
authority. It composes the active ST-0401 session and, for every mapped matrix
action that requires MFA or step-up, the exact single-use ST-0402 grant. It
returns an authorization grant only; it never invokes a business handler.

## Closed registry

The owner contract and generated registry cover all 19 Canonical matrix
actions. Each binding fixes the operation ID, OAuth permission scope, resource
kind, allowed state, roles, step-up/MFA requirement, and separation-of-duty
requirement. Unknown operations, wildcards, hierarchy inference, ambiguous
operation variants, state drift, cross-site/resource identifiers, incomplete
step-up pairs, and missing independent-actor evidence deny.

Only seven exact recorded bindings are active: `AI-113`, `AI-114`, `AI-115`,
`ED-011`, `FIN-006`, `PUBADM-004`, and `PUBADM-012`. The other 13 operation
bindings expose a typed `BLOCKED` reason and the exact evidence needed to close
the mapping. In particular, final approval, publication, policy/product
identity management, audit scope, kill-switch variants, and pre-create
resource bindings remain closed. The ST-0306 workload-role inventory is
recorded, but no service principal is mapped to it; the service-principal port
always denies.

## Durable recorded boundary

The `ENV-DEV`/`ENV-CI` adapter owns a fixed owner-private SQLite database. Its
default policy is immutable and empty. Non-empty policy and entitlement
snapshots are recorded fixtures only and use revision compare-and-set. Active
snapshot pointers and immutable rows carry verified SHA-256 records. Decision
commands are idempotent, audit rows form an append-only verified hash chain,
and explicit units of work distinguish before-commit failure from
after-commit ambiguity. Recovery revalidates the active ST-0401 session and
its fingerprint before returning an existing result. The adapter rejects any
symlinked private-root ancestor and verifies an exact digest of all owned
`sqlite_master` table constraints, indexes, foreign keys, and checks on every
transaction; a same-column weakened schema cannot become authoritative.

The framework-neutral decorator stores operation metadata only. The disabled
HTTP adapter registers no route, ignores every external request with an
RFC 9457 `503`, and admits only an exact in-process loopback recorded harness
with no Cookie or Bearer delivery. Neither path executes a business action.

`AuthorizationDecision`, `AuthorizationCommandResult`, and
`AuthorizationGrant` are trusted in-process normalization values, not
unforgeable capabilities or proof that an application service ran. Their
constructors never accept external input in the runtime composition, and a
grant has no business-action executor. The only enforcement entrypoints are
the application guard and durable authorization service; arbitrary Python code
inside the process is part of the trusted computing base. This preserves the
existing cross-Story value-normalization API without representing constructor
availability as public or provider authority.

## Owner generation

Run the deterministic generator and then its no-write check:

```bash
PYTHONPATH=python:. .venv/bin/python scripts/build_st0403_authorization_runtime.py
PYTHONPATH=python:. .venv/bin/python scripts/build_st0403_authorization_runtime.py --check
```

The manifest binds the Canonical/design/API/ST-0402/ST-0306 sources, the owner
contract, generated artifacts, implementation sources, and verification
files. All authority flags remain `false`.

Formal TST-011/TST-012/TST-026, real OIDC/MFA/DB/provider integration, hosted
CI, staging, release, publication, and Production are `NOT_EXECUTED`. Local
evidence is not `VALIDATED` or Production readiness.
