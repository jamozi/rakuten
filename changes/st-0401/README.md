# ST-0401 provider-neutral authentication boundary

Status: `LOCAL_CODE_COMPLETE`

ST-0401 now has a complete maximum-safe local authentication path while
`OD-010` remains unresolved. The existing provider-neutral Domain, inward
ports, application service, deterministic `ENV-DEV` provider, and ephemeral
repository remain available. V2 adds a strict disabled Admin HTTP projection
and an owner-private durable recorded repository without selecting a real OIDC
provider or browser delivery policy.

## Implemented local boundary

- Authorization requests use independent canonical 256-bit state, nonce, and
  verifier values with S256-only PKCE. State, code, and authorization records
  are consumed once; mismatch, expiry, replay, and malformed input fail closed.
- Sessions have bounded idle and absolute expiry, compare-and-set refresh and
  revocation, atomic predecessor revocation/successor creation, and read-only
  recovery after an unknown rotation commit. Recovery never retries rotation.
- `RecordedSqliteAuthenticationRepository` accepts only the exact
  `RuntimeEnvironment.ENV_DEV` enum member and one absolute owner-private
  directory. It uses a fixed local filename, explicit transactions, full
  synchronization, canonical record hashes, and no caller SQL, provider SDK,
  network, credential, migration, role, or Production configuration surface.
- Before-commit and after-commit fault seams prove known rollback and unknown
  commit resolution. Restart, concurrency, corruption, atomicity, replay, and
  expiry behavior are covered by isolated local tests.
- `DisabledAdminAuthHttpAdapter.dispatch_external` refuses every input with a
  static RFC 9457 `503 AUTH_TRANSPORT_DISABLED` response without inspecting or
  reflecting the input. No framework route is registered.
- The separate recorded harness accepts only exact `POST` JSON documents at
  `http://127.0.0.1:<unprivileged-port>` and the fixed internal test target.
  Request and response keys are closed. Callback/session handles stay in a
  non-serializable in-process test result; response bodies contain no token,
  and `Set-Cookie`, `Authorization`, and `Location` delivery are forbidden.

The deterministic owner contract is
`changes/st-0401/contracts/local-auth-runtime.v2.json`. Generate or verify the
two provenance-bound artifacts with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st0401_local_auth_runtime.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st0401_local_auth_runtime.py --check
```

Run the isolated Story suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/pytest -p no:cacheprovider -q tests/st0401
```

## Debt and authority boundary

The repository-local implementation gap recorded in `DEBT-W1-001` is closed:
the disabled transport shape, recorded loopback integration, durable
transaction/session seam, commit ambiguity recovery, and negative-path tests
are present and owner-generated. The rest of that historical entry is an
external Human Gate, not an inferred local implementation choice. `OD-010`
still requires a Security Owner to select a real provider, issuer/client and
credential lifecycle. Cookie versus bearer delivery, browser storage,
Production callback/route activation, and external validation remain
unselected and blocked.

This Story grants no credential, live-provider, browser, external HTTP,
staging, publication, deployment, release, or Production authority. Formal
TST-012/TST-022/TST-026, browser/runtime verification, hosted CI, staging,
release, and Production are `NOT_EXECUTED`; local checks are not promoted to
those evidence classes.
