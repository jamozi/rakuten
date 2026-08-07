# ST-0305 publication, freshness, analytics, finance, and readmodel schemas

This directory owns the local implementation candidate for approved Story
`ST-0305`. The source contract selects the five exact machine-catalog schemas
and their 39 ordinary unpartitioned MVP tables. The generator renders the
cumulative `202608030005` migration, a deep metadata catalog, PostgreSQL
validation SQL, and the content-addressed manifest. Generated outputs must not
be edited directly.

The slice creates no roles, grants, default privileges, RLS policies, seeds,
retention/deletion behavior, runtime services, providers, or production data.
The missing `ops.release` and `ops.incident` targets defer exactly two named
foreign keys without inventing placeholder tables. The publication transition
guard fails closed while the downstream `ops.kill_switch` relation is absent.

Use the cumulative migration commands with the exact pinned uv. Runtime tests
may use the reviewed cached PostgreSQL 18.4 binaries:

```bash
make migration-generate UV=/absolute/path/to/uv
make migration-check UV=/absolute/path/to/uv
RAOS_PG_BIN=/absolute/postgresql-18.4/bin \
  RAOS_PG_LIB=/absolute/postgresql-18.4/lib \
  make migration-test UV=/absolute/path/to/uv
```

Local passes are implementation-candidate evidence only. Formal TST-008,
TST-011, TST-030, hosted CI, independent review, staging, release, production,
and canonical status application remain `NOT_EXECUTED`.
