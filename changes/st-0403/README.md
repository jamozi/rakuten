# ST-0403 deny-default authorization seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` (partial)

This Story implements the maximum safe local portion of the approved ST-0403
authorization design. The seam starts with the exact ST-0401 active-session
check, derives a `USER`/`ADMIN` principal server-side, loads one immutable
policy snapshot and one trusted entitlement snapshot, and records a minimal
decision before returning an allow grant. Every non-exact path exposes only the
stable external result `DENIED`.

## Implemented local boundary

- Policy is allowlist-only and deny-default. The stable default is an empty
  `DISABLED` policy.
- The only non-disabled policy source is an exact `ENV-DEV`, in-memory,
  `TEST_ONLY:*` recorded adapter. It contains no real assignments, provider
  claims, or canonical business allow policy.
- Matching is exact on business role, required OAuth permission scope, action,
  resource kind, optional state, site UUID, and resource UUID. A site or parent
  assignment never implies child-resource authority; `None` state means only
  stateless matching.
- Rules and entitlement snapshots are immutable, bounded, canonical-order
  values. Duplicate rule IDs, duplicate semantics, reordered data, ambiguous
  matches, malformed collaborator output, and collaborator failures deny.
- Active-session failure occurs before policy, entitlement, or decision-sink
  access. A would-be allow is returned only after one successful sink record;
  the sink is ephemeral inward recording, not durable security audit evidence.
- Internal decisions contain normalized action/target and revision metadata,
  but no raw issuer, subject, display name, token, credential, claim payload,
  or role list. Sensitive values, decisions, grants, failures, and adapters are
  redacted and non-serializable.

UI hiding and PostgreSQL roles are defense-in-depth boundaries, not
application authorization. This slice adds no UI, HTTP decorator/dependency,
middleware, route, database role/grant, migration, workflow, service principal
entrypoint, provider adapter, network/file/process/environment access, logging,
or durable audit service.

## Local verification

After the exact locked environment is already hydrated, the owned checks are
run directly with pinned uv 0.12.1 and `--frozen --offline --no-cache
--no-sync --no-env-file`:

```bash
uv run --frozen --offline --no-cache --no-sync --no-env-file pytest -q tests/st0403
uv run --frozen --offline --no-cache --no-sync --no-env-file ruff check <owned paths>
uv run --frozen --offline --no-cache --no-sync --no-env-file ruff format --check <owned paths>
uv run --frozen --offline --no-cache --no-sync --no-env-file mypy --strict <owned paths>
```

The ST-0306 owner check and ST-0401 isolated regression remain separate
read-only predecessor checks. Generated manifests, canonical/status artifacts,
and the append-only implementation debt ledger are integration-owner work and
are not hand-edited by this slice.

## Deferred and unexecuted

The action-to-OAuth-scope-to-operation/resource/state map and the service-role
inventory are not defined by current canonical sources, so this Story does not
invent or activate them. A real/canonical allow policy, HTTP enforcement,
database integration, durable audit through ST-0405, service authorization,
live identity/provider configuration, and external environments remain absent
and disabled.

Formal `TST-011`, `TST-012`, and `TST-026`, hosted CI, security review, live or
staging validation, release, deployment, publication, and Production remain
`NOT_EXECUTED`. A local focused pass is implementation-candidate evidence only;
it is not `VALIDATED` or Production readiness.
