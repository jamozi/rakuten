# ST-0302 foundation schemas candidate

This Story advances the reviewed migration graph from the retained ST-0301
anchor to an empty `ops`/`iam` foundation. It installs no extension, custom
type, table, seed, workload role, or grant. ST-0303 owns IAM/OPS tables.
Each schema is owner-only: the owner must retain exactly `CREATE` and `USAGE`,
any PUBLIC or other non-owner privilege is drift, and namespace-scoped or
role-global default privileges are forbidden. Migration sessions are pinned to
UTC and the standalone baseline validation rejects a non-UTC session.
ST-0306 owns the later revision-scoped workload grant/default-privilege matrix
and must deliberately replace this baseline.

The semantic source is
`changes/st-0302/contracts/foundation-schema.v1.yaml`. Generated artifacts are
the Alembic revision, baseline validation SQL, Story catalog, and manifest.

```bash
uv run --locked --no-sync --no-env-file \
  python scripts/build_st0302_foundation.py
uv run --locked --no-sync --no-env-file \
  python scripts/build_st0302_foundation.py --check
```

The migration CLI remains restricted to explicit local/CI loopback targets
and an owner-only 0600 password file. `upgrade` reaches the exact head;
`downgrade` moves one reviewed revision only and refuses the ST-0301 anchor.

```bash
PYTHONPATH=python uv run --locked --no-sync --no-env-file \
  python -m raos.migrations upgrade \
  --environment ENV-CI --host /absolute/socket --port 5432 \
  --database raos --user raos_migrator \
  --password-file /absolute/owner-only-password-file

PYTHONPATH=python uv run --locked --no-sync --no-env-file \
  python -m raos.migrations downgrade \
  --environment ENV-CI --host /absolute/socket --port 5432 \
  --database raos --user raos_migrator \
  --password-file /absolute/owner-only-password-file
```

Formal TST-008, hosted CI, migration-owner PR approval, staging/release, and
production execution remain `NOT_EXECUTED`. Canonical status is unchanged.
