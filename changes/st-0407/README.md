# ST-0407 metadata-only workload credential seam

Status: `LOCAL_IMPLEMENTATION_CANDIDATE`

This Story implements the reversible local portion of the approved ST-0407
boundary. It adds material-free workload credential request and lease metadata,
inward acquisition and rotation-hook ports, a configuration-bound application
service, an exact-`ENV-DEV` scripted adapter, and an always-disabled adapter.
It does not resolve or expose a Secret value.

The older design preflight in this directory remains an accurate hard-boundary
record for real providers, credential material, rotation infrastructure, and
database/CI integration. The later owner-approved implementation-first ExecPlan
authorizes this narrower reversible interface/fake slice while preserving those
deferred decisions.

## Implemented safe boundary

- Workload binding, purpose, alias, request, lease metadata, state, and rotation
  notice values are immutable, strictly validated, and redacted. Generic
  serialization and uncontrolled exception text are rejected.
- `WorkloadCredentialService` checks the exact ST-0204 `RuntimeConfig` service,
  environment, and alias membership without unwrapping or reflecting a
  `SecretReference`. It requires explicit UTC observation times and an injected
  positive maximum lease lifetime.
- Returned metadata must match the exact request, be currently valid, remain
  within the configured lifetime, and use a fresh lease identifier. The
  application returns a new material-free lease and never retains provider
  exceptions.
- Rotation hooks receive only validated metadata. They run synchronously in
  declared order, once for each non-overlapping newer replacement; a hook
  failure stops the sequence with a sanitized failure.
- `DevelopmentScriptedWorkloadCredentialAdapter` is construction- and
  operation-guarded to the exact `RuntimeEnvironment.ENV_DEV` enum member. It
  consumes deterministic single-use metadata entries, rejects CI deployment
  purpose, and performs no I/O.
- `DisabledWorkloadCredentialAdapter` always fails closed with
  `BACKEND_NOT_CONFIGURED`.

The owned runtime contains no raw credential material, Secret accessor,
provider SDK, ambient credential chain, network, file, process environment,
database, migration, client or connection pool, JWT/OIDC proof, GitHub workflow,
background refresh, external write, or Production activation.

## Local commands

After the locked Python environment has been hydrated, run the isolated Story
suite through the pinned repository uv in offline/no-sync mode:

```bash
UV=/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv

PYTHONDONTWRITEBYTECODE=1 "$UV" --config-file uv.toml \
  run --locked --offline --no-cache --no-sync --no-env-file \
  --no-python-downloads pytest -p no:cacheprovider -q tests/st0407
```

Focused Ruff lint/format and strict mypy use the same uv prefix over the four
owned source modules and `tests/st0407`. Shared package exports, Make routing,
owner manifests, and generated evidence are intentionally deferred to Wave
integration.

## Evidence and deferred boundaries

The local candidate does not select a Secret backend, credential encoding or
material lifetime, provider account, cloud region, live workload proof,
production cache/refresh policy, database pool rotation, GitHub OIDC trust,
CI deployment credential flow, durable audit sink, or external runtime.
`OD-015` and all live-provider/credential boundaries remain unresolved.

Local pytest/static results are not formal `TST-026` or `TST-031` evidence and
do not represent hosted CI, live provider/database/credential validation,
staging, publication, release, deployment, or Production readiness. These
boundaries are recorded as `DEBT-W1-009` through `DEBT-W1-011` in the
implementation-first ledger.
