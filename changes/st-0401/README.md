# ST-0401 provider-neutral authentication boundary

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the reversible local portion of the approved ST-0401
authentication design. It provides inward OIDC and persistence ports, strict
authorization/session domain values, an application service, and an exact
`ENV-DEV` deterministic fake. It does not select or activate a browser-to-API
session transport.

## Safe default and implemented scope

- Authorization requests use independent 256-bit state, nonce, and verifier
  values. Their wire forms are canonical unpadded base64url values.
- PKCE is S256-only. Unsupported methods, malformed values, mismatches,
  unknown codes, expiry, and reuse all fail closed with sanitized typed errors.
- Authorization transactions and fake authorization codes are consumed once,
  including when a subsequent validation step fails.
- Application sessions have bounded idle and absolute lifetimes. Rotation
  atomically revokes the predecessor, revocation is idempotent, and revoked or
  expired sessions cannot be used.
- The fake adapter and its ephemeral in-memory repository reject every runtime
  environment except the exact `RuntimeEnvironment.ENV_DEV` enum member. The
  fake performs no network exchange and exposes no local-password flow.
- Provider SDK types, HTTP framework types, database models, credentials, and
  Secret resolution do not cross the inward ports.

The implementation intentionally adds no HTTP route, cookie, bearer token,
provider configuration, SDK, persistence migration, generated client, or
public surface. It does not implement MFA, an authorization policy engine,
broad HTTP hardening, a secret manager, or the admin shell.

## Local commands

After the exact locked Python environment has already been hydrated, these
targets are offline, no-cache, no-sync, and read-only:

```bash
make oidc-check UV=/absolute/path/to/reviewed/uv-0.12.1
make oidc-static UV=/absolute/path/to/reviewed/uv-0.12.1
make oidc-test UV=/absolute/path/to/reviewed/uv-0.12.1
make oidc-gate UV=/absolute/path/to/reviewed/uv-0.12.1
```

`oidc-check` imports the neutral seam. `oidc-static` runs pinned Ruff
lint/format and strict mypy only over the Story-owned Python surface and
isolated tests. `oidc-test` never invokes repository-root pytest. The ST-0204
predecessor check remains a separate owner check because adding these Make
targets changes one of its provenance inputs; implementation-first defers that
manifest regeneration to the Wave freeze instead of hand-editing generated
output.

## Evidence boundary and remaining blockers

A local gate pass is implementation-first candidate evidence only. It is not
formal TST-012/TST-022/TST-026 evidence, hosted CI, runtime-provider
validation, staging, release, publication, deployment, or Production
readiness. No generated status or canonical artifact is changed by this Story.

OD-010 still requires a human-selected real OIDC provider and approved issuer,
audience, client registration, redirect, and credential lifecycle before any
external adapter may be enabled. The cookie-session versus bearer-token
browser transport remains a cross-module decision recorded as `DEBT-W1-001`.
Real-provider network exchange, Secret resolution, durable session persistence,
HTTP delivery, admin UI integration, formal evidence, and every external
environment remain disabled and unexecuted.
