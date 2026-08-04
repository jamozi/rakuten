# ST-0301 migration framework candidate

This Story implements the framework-only Alembic head required before the
MIG-001 and domain schema waves. It does not change canonical status and does
not apply any database outside an explicit local/CI command.

## Implemented boundary

- one linear Alembic root/head revision;
- one transaction per revision and atomic version/success-history commit;
- a fixed fail-fast session advisory lock bound to one DBAPI connection and
  PostgreSQL backend PID; connection loss forbids replacement-session writes;
- `public.raos_migration_version` and append-only
  `public.raos_migration_history` with no PUBLIC privileges;
- explicit loopback/Unix-socket target fields and an owner-only 0600 password
  file, with no DSN or password in command arguments or output;
- pre-connect verification of the production revision and all 18 ST-0002 to
  ST-0004 checkpoint paths and SHA-256 digests;
- immutable runner/server metadata bound separately to every reviewed revision;
- JSON-only `verify`, `status`, and `upgrade` commands with static errors.

The 18 checkpoint files are not executable through this Story. Their global
numeric order mixes upgrade and guarded-downgrade phases, and several contain
operator/repeatable boundaries plus concurrent-index regions. ST-0302 and
later owners must translate and activate them as separate Alembic revisions.

## Offline integrity check

```bash
uv run --locked --no-sync --no-env-file \
  python scripts/build_st0301_migration_framework.py --check

PYTHONPATH=python uv run --locked --no-sync --no-env-file \
  python -m raos.migrations verify
```

`verify` opens no database connection. It verifies the exact graph, root
revision, and 18 deferred payload sources first.

## Local/CI database commands

The target must be PostgreSQL `server_version_num=180004`, use an absolute
Unix-socket directory or the literal `127.0.0.1`/`::1`, and provide explicit
lower-snake-case database/user names. The password file path is accepted, but
its value and path are never emitted.

```bash
PYTHONPATH=python uv run --locked --no-sync --no-env-file \
  python -m raos.migrations status \
  --environment ENV-CI \
  --host /absolute/postgresql/socket-directory \
  --port 5432 \
  --database raos \
  --user raos_migrator \
  --password-file /absolute/owner-only-password-file

PYTHONPATH=python uv run --locked --no-sync --no-env-file \
  python -m raos.migrations upgrade \
  --environment ENV-CI \
  --host /absolute/postgresql/socket-directory \
  --port 5432 \
  --database raos \
  --user raos_migrator \
  --password-file /absolute/owner-only-password-file
```

Ambient `PG*` variables, arbitrary revisions, stamp, autogenerate, offline
SQL, downgrade below the history anchor, non-loopback targets, staging,
recovery, and production are rejected.

## Verification

```bash
uv run --locked --no-sync --no-env-file \
  pytest -p no:cacheprovider -q tests/st0301
uv run --locked --no-sync --no-env-file \
  ruff check python/raos/migrations migrations/env.py \
  migrations/versions/202608030001_framework_install_history.py tests/st0301
uv run --locked --no-sync --no-env-file \
  mypy python/raos/migrations
```

The PostgreSQL tests skip unless `RAOS_PG_BIN` points to an exact 18.4 tool
directory. `RAOS_PG_LIB` may point to its private shared-library directory.
Neither variable is a database target or credential.

## Formal boundary

Local results are implementation-candidate evidence only. Canonical TST-008
and TST-009 remain `NOT_EXECUTED`. Independent migration-owner PR review,
hosted CI PostgreSQL 18.4 evidence, staging backup/restore and forward-recovery
rehearsal, release approval, and production execution remain unexecuted.
