# ST-1204 local atomic-publication closure record

- Finding: `ST1204-AUDIT-001`
- Local implementation disposition: `REMEDIATED`
- Independent read-only re-audit: `NOT_EXECUTED`
- Formal TST-030: `NOT_EXECUTED`
- Live provider validation: `NOT_EXECUTED`
- Staging / release / Production: `NOT_EXECUTED`

## Closed implementation boundary

The owner generator now publishes the manifest and all three recorded fixtures
as one exact `changes/st-1204/generated` directory generation. The four former
full-path, sequential replacements are no longer authoritative and are removed
only after the exact new generated tree has a durable committed journal state.

All mutation after repository-root identity capture is relative to a single
descriptor-opened physical `changes/st-1204` directory. A nonblocking flock on
that captured directory inode serializes generation and recovery and excludes a
concurrent shared-lock check. The publisher creates and fsyncs a closed hidden
stage, byte-verifies it, publishes a durable `PREPARED` journal, and uses one
same-parent namespace operation: rename for a fresh install or Linux
`renameat2(RENAME_EXCHANGE)` for replacement. A platform without the exact
exchange operation fails closed before changing an installed generation.

A failure before durable `COMMITTED` reverses the namespace operation and
verifies the exact old generation or exact absence. A failure after durable
`COMMITTED` retains the exact new generation and is completed by deterministic
next-run cleanup. `PREPARED`, `COMMITTED`, and `ROLLED_BACK` recovery, stale
stage/preparing/cleanup entries, lock contention, malformed journals, symlink,
special-file, and multiply-linked entries all have explicit recovery or
fail-closed behavior. Read-only check mode accepts only one exact complete
generation and refuses every pending recovery state.

The generated fixture payloads retain their prior semantic bytes. This change
does not add network, credential, environment-secret, Google SDK/API, database,
queue, job/event, analytics persistence, or runtime publication capability.
OD-012 therefore remains optional-tracking-disabled and OD-015 remains
recorded-fixture-only.

## Local evidence

- Owner generation and the immediately following no-write `--check` passed.
  The generated manifest SHA-256 is
  `76a2d81d36b43333d4bed1ae82fe017f6d2c186b2737aca5180261154eaf4328`.
- `tests/st1204` passed `159` tests. Its dedicated publication file passed `24`
  tests covering fresh and replacement publication, injected faults, real
  subprocess crashes, forward and reverse recovery, ancestor and final-entry
  swaps, shared/exclusive lock contention, mixed-generation exclusion, and
  hostile filesystem material.
- Python 3.14.6 direct compile/import, Ruff 0.16.1 lint and format, and strict
  mypy 2.3.0 with explicit package bases passed over the generator and all
  ST-1204 tests.
- Repository-configured Pyright 1.1.411 passed with `0 errors, 0 warnings, 0
  informations`. That maintained configuration excludes scripts and tests. A
  forced strict out-of-configuration analysis of the generator and ST-1204
  tests reports the existing untyped-YAML/JSON graph and private test-helper
  diagnostics and is not represented as positive direct-file Pyright evidence.
- Canonical import verification and the workspace drift check passed. The
  generator's closed AST/capability test passed as part of the isolated suite.
- The maintained-file scanner was applied descriptor-relatively to the exact
  current ST-1204 patch and reported zero focused findings. The broader
  linked-worktree command remains unavailable with the sanitized inherited
  result `ERROR code=unsafe-git-metadata source="."`; it is not represented as
  a green full-worktree scan.

Exact source hashes at the checkpoint are:

- publication decision:
  `4ce2bd89583b6d6887790f9b4279cd08a482408061ae8a440c6e9f828abc050e`
- source contract:
  `68234b1e7920ddbfa7202f3b14690a985022160cc655611fddb4639eeea4926d`
- generator:
  `4f2c73371275497cc67d964ac420d4702de225deed373518a48956bec8220faa`
- runtime slice:
  `ac85f07ee2325aa5e1f63ffd0323cc499417b2c85d4ac36b31d07fcbe58e0d0e`

## Direct downstream provenance drift

The ST-1205 owner intentionally remains outside this Story. Its current
ST-1204 predecessor inventory pins three bytes changed by this closure:

| Artifact | ST-1205 current pin | ST-1204 checkpoint SHA-256 |
|---|---|---|
| `changes/st-1204/RUNTIME-SLICE-v1.md` | `e5ca8b2e38e0b46c9a40232af26bd5b4ebbbf20099c6a7856a7ab007443ca17e` | `ac85f07ee2325aa5e1f63ffd0323cc499417b2c85d4ac36b31d07fcbe58e0d0e` |
| `tests/st1204/test_ga4_application.py` | `8e8aae09e0749a31957c91a1de8f76abbc61f2e57a3bfecb7382f137196caf52` | `6631568a32d3a510a1b35f349f4cddc365af1105af978fa5048b9079a5a1e7ff` |
| `tests/st1204/test_recorded_ga4.py` | `e8c427264d11fd9e88bfa92a663a8704fbccd70c443bd055e658062c48a95677` | `723d4a85d0e84784a207fcf61b23a59d9a944acb42c2f2c9f2d2f6f66fc90355` |

The exact read-only command
`/home/minami/rakuten/.venv/bin/python scripts/build_st1205_kpi_read_model_reference_plan.py --check`
exits one with
`ST-1205 build failed: SOURCE_HASH_DRIFT field=predecessor.st1204`.
The affected owner artifacts are the ST-1205 source contract, generated
reference plan, and manifest. No ST-1205 file was edited or regenerated here.

## Remaining boundary

This record closes the local publisher implementation deficiency; it does not
change the historical audit artifact or self-approve its required independent
read-only re-audit. A fresh independent audit must review these exact bytes
before the finding receives an audit `PASS`. Formal TST-030, OD-012/OD-015
external evidence, live property/account/credential work, persistence, hosted
CI, staging, release, and Production remain separate and unexecuted.
