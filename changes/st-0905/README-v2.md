# ST-0905 V2 — process-local publication commands

This additive V2 slice implements a deterministic `ENV-DEV`/`CI` command
runtime over exact ST-0903 V2 immutable snapshots and ST-0904 V2 projections.
The V1 reference plan remains preserved as the non-executable predecessor.

The runtime validates an active human, the Canonical publish/rollback roles,
MFA and the ST-0402 step-up grant, site scope, final approval, separation of
duties for publish, immutable snapshot/source identity, and a fresh recorded
kill-switch safe state. Publish and rollback commit projection/event/audit/
outbox *intents* through one process-local copy-stage-swap transaction.
Idempotent replay is byte-identical; conflicting reuse is rejected; a second
publish produces no duplicate intent. Rollback accepts only a known strictly
previous immutable snapshot and leaves all state unchanged on validation or
staged-transaction failure.

`unpublish` is typed but always denied because the Canonical role matrix has no
unpublish action. No route, database, queue, CMS, provider, public state,
publication, staging, release, or Production writer exists. The fixture's
event records are schema-shaped process-local intents only; they are not
emitted. Formal TST-012/TST-013/TST-021, hosted CI, live, staging,
publication, release, and Production evidence remain `NOT_EXECUTED`.

Generate and verify owner artifacts with:

```text
.venv/bin/python scripts/build_st0905_publication_commands_runtime_v2.py
.venv/bin/python scripts/build_st0905_publication_commands_runtime_v2.py --check
```
