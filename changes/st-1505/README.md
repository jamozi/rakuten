# ST-1505 staging deployment reference boundary

This Story-owned slice records the maximum-safe local reference for a future
staging deployment pipeline. It is a closed, source-derived, non-executable
plan: it creates no workflow, infrastructure, credential, migration task,
deployment, smoke request, browser run, rollback, release, or external state.

## Status boundary

- Canonical design: `APPROVED_FOR_IMPLEMENTATION`
- Local deliverable: `INTERFACE_ONLY_PARTIAL_LOCAL_CODE`
- Environment label: inert canonical `STAGING`; configuration remains
  `NOT_CONFIGURED`
- Activation: `DISABLED`
- Runtime and formal verification: `NOT_EXECUTED`
- All create/update/delete/promote/deploy/migrate/smoke/browser/rollback/
  Production action counts: `0`
- Effective canonical implementation/verification status: unchanged

This local reference does not make ST-1505 Story Done, `VALIDATED`, deployed,
or ready for a release or Production.

## Predecessor boundary

The owner builder binds the exact bytes and fail-closed semantics of the
installed ST-1502 data-services contract and plan, ST-1503 compute/edge
contract and plan, and ST-1504 OIDC contract and plan. Each predecessor must
remain non-executable and disabled, with provider calls and external writes
forbidden, every physical/runtime selection unset, and every applicable action
count exactly zero. Rebinding a digest cannot make a semantically weakened
predecessor acceptable.

These predecessor artifacts are themselves local interface-only candidates.
They provide requirements to bind, not executable infrastructure, identity, or
deployment authority.

## Inert staging intent

`STAGING` is only a canonical environment label in this slice. Synthetic and
separately approved anonymized fixtures are the only permitted data classes;
Production data is forbidden. Dedicated credentials are required but not
configured, credential material is absent, and external access is forbidden.

Every provider, account, region, state backend, repository, environment,
deployment role, credential source, artifact digest, SBOM/scan/provenance
reference, release, commit, contract, migration, domain, URL, health matcher,
browser, and rollback selection stays null or empty.

## Logical pipeline and safety intent

The exact ordered logical phases are:

1. `PREDECESSOR_GATE`
2. `ARTIFACT_ADMISSION`
3. `EXPAND_COMPATIBILITY_GATE`
4. `ROLLBACK_READINESS_GATE`
5. `ARTIFACT_PROMOTION`
6. `STAGING_DEPLOYMENT`
7. `MIGRATION_DRY_RUN_GATE`
8. `MIGRATE`
9. `STAGING_SMOKE_GATE`
10. `BROWSER_E2E_GATE`
11. `CONTRACT_DEFERRED`

Every phase is `DISABLED` and `NOT_EXECUTED`, forbids external action, and has
an action count of zero. Future activation must admit an immutable digest with
SBOM, vulnerability scan, and signed provenance, then promote that same
artifact without rebuilding it.

Database change follows Expand-Migrate-Contract. Destructive Contract work is
deferred to a later compatible release. Contract-first change, direct DDL,
down-migration as primary recovery, destructive change, and migration-time
external API calls are forbidden.

Liveness, readiness, dependency, migration-compatibility, and Public/Admin/
Internal isolation checks are required but not configured. A generic HTTP 200
must never be treated as readiness proof. Browser E2E is required but remains
unconfigured and unexecuted.

Rollback is declarative only. A prior immutable artifact, prior configuration,
known-safe snapshot, and migration compatibility are required but not
configured. PITR is forbidden for ordinary application errors and remains a
separate disaster-recovery boundary.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the contract or builder, then run
the owner command.

| Classification | Path | Role |
| --- | --- | --- |
| Story source | `changes/st-1505/contracts/staging-deployment.v1.yaml` | Closed staging, phase, artifact, migration, health, rollback, and disabled-execution requirements |
| Owner builder | `scripts/build_st1505_staging_deployment.py` | Strict deterministic validator and renderer |
| Test source | `tests/st1505/*.py` | Positive, hostile, provenance, path-safety, no-write, and diagnostic coverage |
| Generated reference | `infra/terraform/staging/staging-deployment.reference-plan.v1.json` | Non-executable source-derived reference plan |
| Generated inventory | `changes/st-1505/manifest.yaml` | Exact authority, predecessor, source, output, and boundary hashes |

Generate both declared outputs:

```bash
uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py
```

Verify source pins and committed output bytes without writing:

```bash
uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py --check
```

The CLI accepts only `--check`. The builder reads no ambient environment or
credential, imports no provider/browser/network/process SDK, invokes no
subprocess or native tool, and performs no external write.

## Explicitly unexecuted work

Formal TST-009 and TST-022, a PostgreSQL migration database, migration runner,
HTTP or Playwright execution, staging configuration or deployment, smoke,
rollback exercise, hosted CI, provider/account/credential use, release, and
Production remain `NOT_EXECUTED` and require their separately authorized
owners, environments, approvals, and evidence.
