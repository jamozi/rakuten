# ST-0306 database roles and grants

This Story advances the cumulative migration graph to `202608030006`. The
generator consumes the hash-pinned upstream role SQL and the finalized ST-0004
policy source, creates exactly eight `NOLOGIN` group roles, installs the
reviewed grant/default-ACL matrix, and creates the 22 policies owned by
ST-0306. No login, password, explicit role-membership grant, table, function,
retention rule, or provider integration is created.

On exact PostgreSQL 18.4, fresh role creation by the non-superuser migration
role automatically records eight inbound `ADMIN` membership edges: each
workload role is the granted role, the migration-session role is the member,
`admin_option` is true, and `inherit_option` and `set_option` are false. The
fresh-install runtime test asserts those exact edges and proves that no
workload role has an outbound membership. Existing-role installation and the
standalone validator deliberately reject outbound workload-role memberships
only; they preserve external inbound memberships rather than deleting
cluster-global authority outside this Story.

PostgreSQL's implicit `PUBLIC EXECUTE` default for functions is owner-global,
so the migration revokes it at the migration-owner scope. That single monotonic
deny protects functions subsequently created in all 13 managed schemas; the
schema-scoped default table grants remain exactly as reviewed upstream.

`raos_public_ro` receives only `USAGE` on `readmodel` and `SELECT` on its
tables. The five upstream auditor targets absent from the current graph
(`ops.audit_export`, `ops.incident`, `ops.incident_event`,
`ops.kill_switch_change`, and `ops.release`) remain explicitly deferred.

Generate and check the owned bundle with:

```bash
uv run --locked --no-sync --no-env-file python scripts/build_st0306_database_roles.py
uv run --locked --no-sync --no-env-file python scripts/build_st0306_database_roles.py --check
```

The downgrade removes policies and workload table/default-table authority. It
deliberately preserves cluster-global group roles and the monotonic default
function-`EXECUTE` denial for `PUBLIC`; external login memberships and
privileges in other databases are outside this Story's scope.
Local passing tests are candidate evidence only; formal TST-011, hosted CI,
migration-owner review, release approval, and production execution remain
separate gates.
