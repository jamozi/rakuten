# ST-1505 local completion evidence v2

Status: `LOCAL_CODE_COMPLETE_PROPOSAL`; formal/live status unchanged.

## Implemented local boundary

- A closed runtime contract binds the current ST-1502, ST-1503, and hardened
  ST-1504 sources. The ST-1504 manifest, fail-closed activation port, disabled
  adapter, and recorded evaluation are raw-hash pinned.
- A pure domain evaluator verifies one synthetic immutable artifact digest,
  its closed recorded SBOM, zero Critical/High synthetic findings, and recorded
  provenance digest binding. Cryptographic signature and formal attestation
  remain `NOT_PERFORMED`/`NOT_EXECUTED`.
- Expand-Migrate-Contract is exercised only as an in-memory plan and dry-run.
  The destructive Contract phase is deferred, database statements and external
  actions are zero, and real migration/review remain `NOT_EXECUTED`.
- Public, Admin, and Internal health are exact recorded loopback responses with
  distinct isolation metadata. No HTTP request or generic-200 inference exists.
- Rollback/restore is an in-memory digest reconstruction against a synthetic
  prior artifact and configuration snapshot; no reversal or restore action is
  performed.
- The explicit application path consumes the hardened ST-1504 disabled
  receipt, then persists canonical synthetic result bytes to a fixed
  owner-private SQLite journal. Idempotency, append-only hash chaining,
  commit-ambiguity recovery, restart recovery, tamper refusal, private path
  checks, and concurrent serialization are implemented.
- Journal initialization is created-only and descriptor-relative. Existing
  zero-byte and valid-empty SQLite files are refused without schema adoption;
  only the file created by the current constructor may receive the initial
  schema.
- Every injected activation and journal call is single-attempt and fail-closed.
  Unexpected exceptions, forged exact-type receipts, missing or hostile fields,
  and malformed closed errors are reduced to fixed sanitized codes without
  collaborator data or exception chaining.
- The journal binds an exact application ID and user version, exact `STRICT`
  table DDL, automatic unique/primary indexes, a composite foreign key, and
  nine exact append-only/lifecycle triggers in addition to canonical row and
  hash-chain integrity. Same-named tables with weakened constraints, missing
  guards, and extra schema objects are refused.
- The original owner-private root and database device/inode are pinned around
  every connection and operation. Same-process instances share a serialized
  monotonic count/tail anchor, so database/root replacement and a byte-valid
  whole-file rollback to an earlier same-inode snapshot fail closed.
- Unexpected journal/WAL/shared-memory sidecars are rejected without being
  followed. Raw row updates/deletes and out-of-order run/journal inserts are
  rejected by SQLite guards before commit.
- Repository-root ancestors, the fixed runtime contract, bound descendants,
  the owner-private directory ancestry, and the database file reject symlink
  substitution before trusted bytes are consumed.
- The generated pipeline fixture is outside `.github/workflows`, has no
  trigger/command/target/client/credential, is default-disabled, and records
  exact zero for all external action categories.

## Verification record

| Gate | Local result |
| --- | --- |
| focused runtime, journal, and critical negative paths | `PASS`; 74 tests |
| complete `tests/st1505` suite | `PASS`; 483 tests |
| complete `tests/st1505` suite in fresh denied-network/PID namespace | `PASS`; isolation assertion passed, 483 tests |
| ST-1501 through ST-1504 owner `--check` | `PASS`; all four frozen predecessors |
| ST-1505 owner regeneration and read-only `--check` | `PASS`; deterministic three-output generation plus manifest |
| Ruff format and lint | `PASS`; 13 owned Python/test files |
| strict mypy | `PASS`; six Story source files |
| strict Pyright | `PASS`; six Story source files, zero diagnostics |
| Python compile/import | `PASS`; bytecode redirected outside the repository |
| active `.github/workflows` comparison to `77470e14` | `PASS`; zero changed files |
| physical snapshot secret scan under denied network | `PASS`; 23 Story-owned files, zero findings |
| `git diff --check` | `PASS` |

The direct ST-1506 consumer audit fails closed on the deliberately changed
ST-1505 runtime-contract, generator, manifest, pipeline, and result digests
(`305 passed, 121 failed, 64 errors`; closed
`SOURCE_DIGEST_MISMATCH`/`BINDING_DIGEST_MISMATCH` and generated-byte drift).
ST-1506 rebinding and owner regeneration belong to the downstream Story or
integration owner; this ST-1505 slice does not edit or weaken that consumer.
No provider, credential, staging, release, or Production action is enabled by
the refusal.

The physical snapshot contains the exact Story-owned sources and generated
artifacts plus the unchanged maintained scanner boundary. It has no Git
metadata and runs in the repository network/PID namespace guard. This proves
only that the introduced bytes have no maintained-scanner finding; it is not a
provider, staging, or hosted-CI result.

## Explicitly not executed

- Formal TST-009 and PostgreSQL 18 zero-to-latest/upgrade/rollback migration
  evidence
- Formal TST-022 and Playwright/browser evidence
- Signed build provenance or formal vulnerability scanner evidence
- Credential issuance, provider/account selection, target adapter, network,
  transport, protected-environment approval, live smoke, telemetry, alerts,
  staging, deploy, rollback/restore of live state, release, or Production
- Canonical status transition, `VALIDATED`, staging-ready, release-ready, or
  Production-ready determination

Local deterministic evidence must not be promoted to any item above.
