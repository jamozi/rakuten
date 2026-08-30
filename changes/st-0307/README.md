# ST-0307 migration upgrade fixtures

This Story owns four deterministic, synthetic SQL fixtures for TST-010. The
fixtures bind the finalized ST-0002, ST-0003, and ST-0004 alignment checkpoint
families and the exact `202608030005` predecessor of the current
`202608300001` head. The predecessor fixture exercises both ordered successors,
`202608030006` and `202608300001`. They are generated from
`contracts/migration-upgrade-fixtures.v1.yaml`; generated SQL, the fixture
catalog, and the manifest must not be edited directly.

Historical checkpoint SQL may be executed only as separately ordered payloads
against disposable PostgreSQL 18.4 test databases. It is never copied,
concatenated, installed as an Alembic revision, or connected to the production
migration runner. ST-0307 adds no revision and changes no production graph
semantics. The canonical Story dependency remains ST-0305; the fixture owner
follows the ST-0301 migration catalog owner and ST-0306 role owner so a new
cumulative head is regenerated and tested in graph order. This does not
reclassify the fixture run as TST-011 evidence.

Generate and verify the bundle with the exact pinned uv:

```bash
make migration-fixture-generate UV=/absolute/path/to/uv
make migration-fixture-check UV=/absolute/path/to/uv
RAOS_PG_BIN=/absolute/postgresql-18.4/bin \
  RAOS_PG_LIB=/absolute/postgresql-18.4/lib \
  make migration-fixture-test UV=/absolute/path/to/uv
```

Fixture execution is isolated, superuser-owned test setup because historical
content checkpoints include FORCE-RLS tables before ST-0306 policies exist.
The historical template loads the four hash-bound upstream bootstrap members
(`001` through `004`) exactly as the established ephemeral predecessor setup.
Member `002` restores the predecessor ACL required by ST-0003 guarded downgrade
self-checks; members `003` and `004` retain the reviewed reference and baseline
validation state. Their presence is an isolated checkpoint prerequisite, not
an ACL/default-privilege validation or TST-011 evidence claim. The generated
fixtures themselves create no roles, grants, policies, credentials, review
bodies, provider data, or production records.

Local PostgreSQL results are implementation-candidate evidence only. Formal
TST-010, hosted CI, migration-owner review, staging recovery rehearsal, human
review, canonical apply, release, and production remain `NOT_EXECUTED`.
