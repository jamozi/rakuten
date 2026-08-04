# ST-0303 IAM/OPS schema local implementation candidate

This Story implements the reviewed IAM/OPS table wave as a local/CI candidate.
`scripts/build_st0303_iam_ops.py` is the sole active writer for the cumulative
Alembic revision, exact catalog, no-write PostgreSQL validation SQL, and Story
manifest. The generated revision is the checksum-pinned graph head and the
runtime runner validates its installed physical catalog. Protected canonical
and upstream inputs and the frozen ST-0301/ST-0302 predecessor artifacts remain
unchanged.

## Exact scope

The contract contains 17 tables and 219 columns: eight `ops` tables
(`object_artifact`, `job`, `job_attempt`, `outbox_event`, `inbox_receipt`,
`idempotency_record`, `audit_event`, and `runtime_setting_version`) and nine
`iam` tables (`principal`, `user_account`, `service_principal`, `role`,
`permission`, `role_permission`, `principal_role_assignment`,
`session_revocation`, and `break_glass_record`). Its PostgreSQL 18 inventory is
267 constraints, including 151 exact NOT NULL constraints, 17 primary keys, 13
named unique constraints, 66 checks, and 20 immediately installed foreign
keys. It has 48 standalone indexes and 78 indexes in total, exactly two
deferred foreign keys, two trigger functions, and four user triggers.

The `ops.job` definition incorporates the final ST-0002 contract: ten exact
states, `REQUESTED` as the initial/default state, the `job_version`,
`deadline_at`, and `cancel_requested_at` columns, 11 checks, and nine indexes.
It is not reconstructed by concatenating proposal-phase SQL.

Only `fk_ops_job_site_id` and
`fk_iam_break_glass_record_incident_id` are deferred because their target
tables are outside this owned wave. Their source columns and lookup indexes
remain installed; no placeholder table, inferred referential rule, or
unapproved owner Story is introduced.

## Security and lifecycle boundary

Migration and verification sessions use only `pg_catalog` as `search_path`,
and builtin expressions are explicitly schema-qualified. The runner fixes the
path in both libpq startup options and the locked session, verifies it before
work, and rejects hostile inherited resolution. Its history-independent head
attestation and the standalone validation SQL reject exact catalog drift in
tables, columns, defaults, comments, constraints, indexes, functions,
triggers, ACLs, row/array types, unlisted namespace objects, managed casts and
operator support, publications, subscriptions, large objects, and foreign-data
objects. The only permitted source normalization is the contract's exact
allowlist of `uuidv7()`, `jsonb_typeof(...)`, and `lower(email)`
qualifications.

PUBLIC table access and function execution remain forbidden. This Story
creates no roles, workload grants, default privileges, secrets, seed data,
publication, subscription, cast, large object, or foreign-data integration.

Hard mutation rejection is limited to `ops.object_artifact` and
`ops.audit_event`. The other upstream append-only labels do not acquire an
invented trigger. The maintenance exception requires both the explicit
`raos.allow_immutable_maintenance=on` session setting and membership in
`raos_migrator`; otherwise UPDATE and DELETE fail closed with SQLSTATE 55000.

A downgrade must run atomically, prove all 17 owned tables empty before its
first DROP, use `RESTRICT`, and fail without a partial drop when any table is
nonempty.

Two upstream semantics are deliberately preserved rather than strengthened.
The ordinary unique constraint
`uq_ops_setting_version(setting_key, scope_type, scope_id, version_no)` permits
duplicate GLOBAL/version rows when nullable `scope_id` is NULL. Also,
`iam.break_glass_record` contains the two principal columns but no database
CHECK that they differ. Changing either contract requires an approved design
handoff; break-glass two-person runtime enforcement and verification are
outside this database slice.

## Generation and local verification

The generator's final source inventory is cumulative and exact: 43 paths
inherited from the ST-0302 source closure at their current cumulative bytes,
plus 11 ST-0303 paths, 54 total. Only the ST-0302 manifest and generated
artifacts remain frozen predecessor bytes. The earlier provisional source list
is removed. Generate or perform deterministic read-only drift checking only
through the active entrypoint:

```bash
uv run --locked --no-sync --no-env-file python \
  scripts/build_st0303_iam_ops.py
uv run --locked --no-sync --no-env-file python \
  scripts/build_st0303_iam_ops.py --check
```

Run all three migration Story suites as isolated pytest processes through the
repository target:

```bash
RAOS_PG_BIN=/absolute/postgresql-18.4/bin \
RAOS_PG_LIB=/absolute/postgresql-18.4/lib \
make migration-test UV=/absolute/path/to/uv
```

The local tests cover zero-to-head, the physical ST-0302 predecessor, exact
catalog parity, hostile search paths, migration history, one-step
downgrade/re-upgrade, atomic nonempty downgrade rejection, behavior, ACLs, and
adversarial same-name, comment, indirect-catalog, and unlisted-object drift.

## Evidence boundary

Generated bytes, source hashes, and exact local PostgreSQL 18.4 results are
candidate evidence only. They do not promote canonical or formal status.
Repository-wide gates, append-only ST-0005 evidence capture, independent
migration-owner/human review, hosted CI, staging, release approval, and
production execution remain separate governed work. Formal TST-008, TST-011,
and TST-013 and effective canonical ST-0303 status remain `NOT_EXECUTED` and
unchanged.
