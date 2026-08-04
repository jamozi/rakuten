# RAOS migration framework

`migrations/README.md` is a generated workspace marker. This document owns the
cumulative ST-0301/ST-0302/ST-0303 operational boundary.

The production Alembic graph is linear and may be invoked only through
`python -m raos.migrations`. `migrations/env.py` rejects URL fallback, offline
SQL, direct Alembic CLI use, stamp operations, and non-PostgreSQL connections.
Each revision pins its own runner/server metadata. The session lock is also
bound to the original DBAPI connection and PostgreSQL backend PID; implicit
connection replacement after a disconnect is rejected before any history
write. Every libpq connection starts with `search_path=pg_catalog`, and the
runner sets and verifies that value again before taking its advisory lock. The
revision DDL and catalog validation use schema-qualified builtins.

The retained ST-0301 anchor installs only:

- `public.raos_migration_version`, managed by Alembic;
- `public.raos_migration_history`, an append-only attempt ledger;
- the history mutation-rejection trigger/function.

The retained ST-0302 revision additionally creates only the empty `ops` and `iam` schemas,
their exact comments, exact owner `CREATE`/`USAGE`, and no PUBLIC/non-owner or
namespace-scoped default privilege. It creates no extension, custom type,
table, seed, role, or workload grant.

The ST-0303 head translates its approved declarative source into exactly 17
IAM/OPS tables and 219 columns, with 17 primary keys, 13 named unique
constraints, 66 checks, 48 standalone indexes, 20 immediate foreign keys, two
trigger functions, and four triggers. The unavailable `portfolio.site` and
`ops.incident` targets are not invented: their two foreign keys are deferred,
while the source columns and lookup indexes remain installed. The runner's
history-independent head check verifies the exact PostgreSQL 18.4 table,
column, constraint, index, function, trigger, owner, ACL, and deferred-FK
catalog shape. Later Stories must activate only their owning migration waves
rather than concatenating the ST-0002 through ST-0004 checkpoint payloads.
ST-0306 must explicitly replace the owner-only check with its revision-scoped
grant/default-privilege matrix when it begins owning those privileges.

`upgrade` reaches the exact checksum-pinned head. `downgrade` accepts no target
and moves exactly one reviewed revision; it refuses the ST-0301 anchor. The
ST-0303 reverse DDL locks all 17 owned tables, proves all are empty before its
first drop, and uses `RESTRICT`. A nonempty table therefore fails atomically
without a partial drop. From the physical ST-0302 predecessor, the next
one-step downgrade uses `DROP SCHEMA ... RESTRICT`, so an unexpected or
later-owned object is not destroyed.

Database commands require an explicit local/CI target and an owner-only 0600
password file. No DSN or password is accepted on the command line or emitted in
diagnostics. Generate or check the active cumulative artifacts only through
`scripts/build_st0303_iam_ops.py`; the ST-0301 and ST-0302 legacy entrypoints
delegate to it when the successor contract exists and never rewrite their
frozen predecessor artifacts. Exact commands and the local-only evidence
boundary are documented in the root README and the ST-0303 execution records.
