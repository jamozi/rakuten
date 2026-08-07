# ST-0304 domain schemas

This directory owns the local implementation candidate for the approved
`ST-0304` database slice. The source contract freezes the exact six-schema
inventory of 86 tables and 1,141 columns, and the physical SQL fragments
translate the pinned RAOS data catalog plus finalized ST-0003/ST-0004
semantics. They are inputs to `scripts/build_st0304_domain_schemas.py`;
generated migrations, catalog, validation SQL, and manifest must never be
edited directly.

Use the existing cumulative migration surface with the exact pinned uv. The
runtime suite may use the reviewed cached PostgreSQL 18.4 binaries without a
Docker pull or download:

```bash
make migration-generate UV=/absolute/path/to/uv
make migration-check UV=/absolute/path/to/uv
RAOS_PG_BIN=/absolute/postgresql-18.4/bin \
  RAOS_PG_LIB=/absolute/postgresql-18.4/lib \
  make migration-test UV=/absolute/path/to/uv
```

`migration-generate` and `migration-check` target the current cumulative
ST-0304 head. `migration-test` and `ci-unit` keep each migration Story suite in
its own pytest process, while `ci-static` reaches the no-write ST-0304 check
through repository policy. No new workflow job or external dependency is
introduced.

The implementation creates no role, grant, default privilege, RLS policy,
seed, live data, retention rule, or publication behavior. The eleven adopted
content tables remain RLS-enabled and forced, intentionally fail-closed with
zero policies until ST-0306. Formal TST-008 and TST-010, hosted CI, staging,
release, and production remain `NOT_EXECUTED`; local static or cached-runtime
passes are candidate evidence only.
