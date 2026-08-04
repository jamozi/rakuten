# ST-0002 canonical Job-state revision

This directory is the immutable-input revision bundle produced for
`ST-0002 / INT-DEC-003`. It does not overwrite either v0.1 package and does not
apply the proposal-only SQL.

## Source and generated artifacts

- `job-state.v1.yaml` is the single source for the ten states, sixteen allowed
  transitions, guards, and seven legacy mappings.
- `database/` contains the formal Expand, Migrate, Contract, guarded downgrade,
  and forward-recovery payloads.
- `contracts/` is generated from the immutable RAOS-API-001 v0.1 package plus
  `job-state.v1.yaml`.
- `manifest.yaml` pins every input, source, and generated artifact by SHA-256.

Regenerate and verify:

```bash
python3 scripts/build_st0002_revision.py
python3 scripts/build_st0002_revision.py --check
```

The CLI only writes the owned `changes/st-0002` bundle. It renders a complete
candidate in a sibling staging directory, verifies the ownership marker on an
existing destination, and restores the prior generated tree if installation
fails. Custom output paths are refused.

## Database phase order

1. `202607300001_job_state_expand.sql`
2. `202607300002_job_state_expand_validate.sql`
3. deploy and observe canonical-compatible writers
4. repeat `202607300003_job_state_migrate_batch.sql` until
   `remaining_rows=0`, retaining every batch result
5. reconcile state counts and confirm no old writer remains
6. `202607300004_job_state_contract_prepare.sql`
7. `202607300005_job_state_contract.sql`

The guarded downgrade is not a general rollback. It refuses canonical-only
states and meaningful v0.2 fields before mutation. After canonical writers are
enabled, follow `database/forward-recovery.md`. The future migration runner
must record each numbered file separately and must checkpoint every repeatable
003 batch; it must not wrap the entire sequence in one transaction.

## Handoff boundary

- `ST-0104` installs the generated files into the final contract repository.
- `ST-0301` binds the SQL payloads to migration history, locking, and runner
  semantics.
- `ST-0303` installs the canonical IAM/OPS schema.
- `ST-1404` implements the state transition, lease, retry, and DLQ runtime.

No production database, external service, publication, or release approval is
part of this bundle.
