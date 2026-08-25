# ST-1506 maximum-safe local canary runtime V2

This additive V2 slice preserves the existing V1 provider-neutral Production
reference byte-for-byte and adds an explicit offline simulation runtime. The
runtime is not a deployment pipeline. It has no live provider, credential,
network, migration, traffic, telemetry, alert, rollback, release, or public
write capability.

The V2 contract exact-hash binds every current ST-1501 through ST-1505 design
handoff, contract, owner generator, generated reference plan, and manifest,
plus the integrated ST-1505 V2 inert pipeline, recorded result, admitted
artifact, SBOM, and provenance. It also binds the byte-preserved ST-1506 V1
contract. The V1 source and generated reference are rebound to the same current
predecessor chain without granting execution authority. A raw or semantic
mismatch blocks before simulation.

The closed Production capability inventory contains workload runtime,
relational persistence, immutable object storage, asynchronous queue, public
edge, workload identity and secrets, telemetry and alerting, backup and
restore, deployment and release, and region/data residency. Every capability
mapping is absent. No profile is selected, defaulted, or used as a fallback,
so Production eligibility remains blocked.

Each call evaluates one state transition only. `START_CANARY_SIMULATION` moves
an in-memory/local-journal session from `CANARY_READY` to `OBSERVE`.
`RECORD_SYNTHETIC_OBSERVATION` either remains blocked in `OBSERVE`, holds for
all four human approvals, or records that a human-operated abort or rollback
would be required. It never performs the named external action. Missing,
unknown, stale, future, mismatched, or immature data blocks.

The four approval artifacts are distinct and always absent:

- release decision;
- GATE report;
- security approval; and
- operations approval.

The local safety kill switch is always enforced. No API exists to disable it.
Synthetic success only produces `HUMAN_APPROVALS_REQUIRED`; it can never
authorize auto-advance, activation, release, or a public write.

Generated files are outside the active workflow tree:

- `infra/terraform/deployment-production/local-production-canary.pipeline.disabled.v2.yaml`
- `infra/terraform/deployment-production/local-production-canary.result.recorded.v2.json`
- `changes/st-1506/manifest.v2.yaml`

The owner-private journal is created only through `O_EXCL`. Existing empty or
foreign databases are rejected without initialization. Every access verifies
the exact STRICT table/index/foreign-key/trigger inventory, append-only journal
and lifecycle guards, root/database device and inode, absence of SQLite
sidecars, and a process-shared monotonic chain anchor. This detects replacement
and same-inode whole-database rollback while the process anchor exists.

Generate:

```bash
uv run --locked --no-sync python scripts/build_st1506_production_canary_runtime.py
```

Read-only drift check:

```bash
uv run --locked --no-sync python scripts/build_st1506_production_canary_runtime.py --check
```

Formal TST-009, TST-022, TST-032, hosted CI, live provider, staging,
security/operations approval, release, and Production remain `NOT_EXECUTED`.
OD-009, OD-011, OD-013, and OD-015 remain unresolved, so all selected live
values remain unset.
