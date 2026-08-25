# ST-0402 durable step-up boundary

Status: `LOCAL_CODE_COMPLETE`

ST-0402 now has a maximum-safe local challenge-to-grant runtime while the
real-provider and browser-delivery decisions remain unresolved. The original
provider-neutral `StepUpGrant` and `StepUpGuard` remain API-compatible.
The new path adds a closed critical-action registry, exact session/principal/
action/resource binding, explicit challenge and verification receipt stages,
and a durable single-use grant lifecycle.

## Implemented local boundary

- Every state-changing operation first requires the exact active ST-0401
  session. A grant is bound to that session, stable issuer and subject,
  one closed critical action, one required resource type, and one resource ID.
  ST-0402 never grants role or resource authorization; ST-0403 remains the
  authorization owner.
- The action registry is non-configurable and fail-closed. It covers final
  approval, publication, rollback, both publication and affiliate kill-switch
  directions, revenue import commit, AI release, Secret management, and
  break-glass. `final_approve` follows the higher-precedence Security design's
  stricter step-up requirement.
- Challenge, synthetic multi-factor verification receipt, and bound grant
  lifetimes are explicit UTC inputs. Challenge verification, receipt-to-grant
  conversion, and grant consumption are each single-use. Exact expiry,
  mismatch, replay, revocation, and unknown-command failures are sanitized.
- `RecordedSqliteStepUpRepository` is exact-`ENV-DEV` and accepts one
  absolute owner-private directory. Its fixed SQLite database applies
  created-only `O_EXCL` initialization; every pre-existing empty, partial, or
  foreign file is rejected. Schema V2 is an exact `STRICT` table/index/trigger
  inventory with foreign keys and fixed connection PRAGMAs.
- Challenge, receipt, grant, command, and audit records are append-only
  revision/hash chains. Canonical JSON bytes, lower-case UUIDs, microsecond UTC,
  redundant binding columns, lifecycle relationships, exact command intent and
  exact recovery results are fully scanned at each transaction boundary.
  Lifecycle mutation, command record, and audit event commit atomically.
- Root and database device/inode identity are pinned. A process-local valid
  command-prefix anchor detects same-inode rollback and file replacement while
  the process remains alive. There is deliberately no trusted cross-process or
  cross-restart rollback anchor in this recorded local adapter.
- Only a failure before commit, or a commit failure that leaves the transaction
  active and therefore rollable back, is classified as known rollback. An
  injected after-commit crash returns `STORAGE_COMMIT_UNKNOWN`; read-only exact
  command recovery resolves it without blind retry.
- Collaborator values are deep-detached and hostile mutation is rejected. The
  synthetic verifier exposes a stable `external_action_count` of exactly zero;
  a missing, changing, boolean, or non-zero count fails closed.
- `DisabledAdminMfaHttpAdapter.dispatch_external` always returns the same
  sanitized RFC 9457 503 refusal without inspecting input. No framework route
  is registered. The separate recorded harness accepts exact POST JSON only at
  `http://127.0.0.1:<unprivileged-port>` and the fixed internal target.
  Handles remain in a non-serializable in-process result; Cookie, Bearer,
  browser storage, and response delivery are unselected and absent.

The deterministic owner contract is
`changes/st-0402/contracts/local-step-up-runtime.v2.json`. Generate and verify
its runtime and provenance manifest with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st0402_local_step_up_runtime.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/python scripts/build_st0402_local_step_up_runtime.py --check
```

Run the isolated Story suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=python:. \
  .venv/bin/pytest -p no:cacheprovider -q tests/st0402
```

## Debt and authority boundary

The maximum-safe local portions of `DEBT-W1-004` and `DEBT-W1-005` are
closed: a disabled external RFC 9457 projection, strict recorded loopback
integration, durable lifecycle, atomic audit, recovery, CAS, and closed action
mapping are implemented. Created-only database ownership, exact schema,
append-only lifecycle/command/audit chains, process-local rollback detection,
and detached collaborator boundaries are also implemented. Cookie/Bearer and browser delivery, middleware
registration, OpenAPI/client generation, and any external activation remain
outside this local boundary.

`DEBT-W1-003` remains externally blocked by `OD-010`: no real MFA factor,
provider claim mapping (`amr`/`acr`/`auth_time`), credential lifecycle, or
Production freshness value was inferred. `DEBT-W1-006` also remains external:
formal TST-012/TST-022/TST-026, browser, hosted CI, staging, release, and
Production evidence are not executed.

This Story grants no credential, provider, external HTTP, browser, critical
command, staging, publication, release, or Production authority. Local tests
must not be promoted to formal or operational evidence.
