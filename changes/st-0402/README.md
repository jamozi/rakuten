# ST-0402 provider-neutral MFA step-up seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the reversible local portion of the approved ST-0402
design. It adds an immutable, factor-neutral `StepUpGrant`, an inward verifier
port, an application guard, and an exact-`ENV-DEV` deterministic source of
synthetic already-verified grants.

## Implemented safe boundary

- A grant is bound to the exact ST-0401 `SessionId` and to the stable issuer
  and subject of that session's principal.
- `authenticated_at` and `expires_at` are explicit inputs with strict UTC
  validation. The guard accepts only `authenticated_at <= now < expires_at`;
  there is no implicit or production-default freshness lifetime.
- The guard requires the ST-0401 session first. Unknown, revoked, rotated,
  idle-expired, and absolute-expired sessions fail before assurance lookup.
- Missing, rejected, malformed, future, expired, session-mismatched,
  principal-mismatched, and non-MFA assurance fail with stable sanitized typed
  errors. Verifier exceptions and rejected values are not retained.
- The development adapter accepts only exact `RuntimeEnvironment.ENV_DEV`,
  rechecks that guard on every verification operation, and exposes only
  explicitly supplied synthetic grants. It performs no I/O.
- Grant and failure rendering is redacted; generic serialization of a grant is
  rejected. No provider, factor, credential, challenge, or action-policy data
  enters the domain object.

## Local commands

After the locked Python environment has already been hydrated, run ST-0401
and ST-0402 in separate processes. The direct ST-0402 commands use the pinned
uv offline, no-cache, and no-sync:

```bash
make oidc-test UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0402
```

Focused Ruff lint/format and strict mypy use the same uv prefix and only these
four source modules plus `tests/st0402`. Direct imports are intentional; shared
package exports and Make routing are deferred to Wave integration.

## Evidence boundary and deferred work

This local candidate does not implement an MFA challenge, OTP, TOTP,
WebAuthn, one-time proof, provider claim mapping, a production freshness TTL,
HTTP/cookie/bearer/browser transport, middleware, Problem Details,
`/admin/mfa`, critical-action mapping, persistence, migration, durable audit,
real provider, Secret resolution, or public/live activation. It does not read
or modify the optional generated/OpenAPI `mfa_satisfied` property.

Local pytest/static results are not formal `TST-012`, `TST-022`, or `TST-026`
evidence and do not represent hosted CI, browser/provider runtime, staging,
publication, release, deployment, or Production readiness. Those boundaries
are recorded as `DEBT-W1-003` through `DEBT-W1-006` in the implementation-first
ledger.
