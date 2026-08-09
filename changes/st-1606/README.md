# ST-1606 — Backup restore drill reference plan

## Local implementation boundary

This Story owns a deterministic, source-derived inventory and future-check
plan for the canonical backup restore drill. It is a
`LOCAL_IMPLEMENTATION_CANDIDATE`, not performed recovery evidence. The plan is
non-authoritative, non-executable, default-disabled, and cannot activate or
configure a recovery environment.

The generated projection is not recovery evidence and does not claim that a
restore, integrity check, or RPO/RTO measurement has run.

Canonical Story acceptance remains false. Formal `TST-029`, hosted CI, a
restore drill, live/provider/runtime work, `ENV-RECOVERY`, Staging, release,
and Production remain `NOT_EXECUTED` or `NOT_AUTHORIZED` as applicable.

## Closed safe semantics

- `ENV-RECOVERY` is an inert reference label only. It is `NOT_CONFIGURED` and
  `NOT_ACTIVATED`; it is not a Staging or Production target.
- The exact logical target inventory is database, object storage, and IaC
  configuration. It contains no physical resource selection or action surface.
- Source backups carry immutable/read-only intent. Overwrite, delete,
  lifecycle, retention, cleanup, expiry, and automatic deletion are forbidden.
- OD-014 remains unresolved. Automatic deletion is disabled and collection is
  minimal. No retention duration or lifecycle/deletion value is selected.
- Account, region, endpoint, credential, encryption key, bucket, database,
  IaC backend, restore destination, provider, tool, version, and schedule
  values remain null or empty.
- Reviewable content/hash integrity, row/object count, role/access-boundary,
  read-model rebuild/consistency, and source-backup non-mutation checks are
  future requirements only. They have no result or evidence.
- RPO/RTO values are exact projections of canonical design targets. They are
  not measurements or claims of achievement.
- Every execute, create, update, delete, restore, verify, cleanup, approval,
  and external action count is the exact built-in integer zero.

The generated JSON is therefore only a reviewable plan/inventory projection.
It must never be interpreted as proof that a restore ran, data is recoverable,
integrity or access boundaries passed, RPO/RTO was measured, or the Story is
validated.

## Dependency and authority binding

The owner builder validates exact bytes and required safe semantics for the
current ST-1502 and ST-1505 contracts, reference plans, and manifests. It also
binds the canonical Story, OD-014, TST-029, operations, recovery, security, and
implementation-first authority sources by SHA-256. The reused ST-1505
path/YAML/JSON/atomic-output helper is an implementation dependency pinned in
the generated manifest.

No predecessor, canonical artifact, runtime source, IaC, workflow, status,
evidence, or debt ledger is modified by this Story slice.

## Owned source and generated artifacts

Do not hand-edit generated artifacts. Change the contract or builder, then run
the owner command.

| Kind | Path | Meaning |
| --- | --- | --- |
| Source contract | `changes/st-1606/contracts/backup-restore-drill.v1.yaml` | Closed safe-default and future-check definition |
| Owner builder | `scripts/build_st1606_backup_restore_drill.py` | Strict validator and deterministic generator |
| Generated plan | `changes/st-1606/generated/backup-restore-drill.reference-plan.v1.json` | Non-executable plan/inventory projection |
| Generated manifest | `changes/st-1606/manifest.yaml` | Exact source, predecessor, helper, and output inventory |
| Isolated tests | `tests/st1606/` | Contract, generation, and hostile-boundary checks |

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1606_backup_restore_drill.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python scripts/build_st1606_backup_restore_drill.py --check
```
