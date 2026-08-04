---
phase: st-0105
reviewed: 2026-08-02T05:31:13Z
depth: deep
files_reviewed: 26
files_reviewed_list:
  - AGENTS.md
  - README.md
  - Makefile
  - pyproject.toml
  - package.json
  - workspace-layout.json
  - packages/web-contracts/README.md
  - packages/web-contracts/package.json
  - packages/web-contracts/tsconfig.json
  - scripts/bootstrap_workspace.py
  - scripts/build_st0105_generated_contracts.py
  - scripts/codegen_toolchain.sh
  - scripts/node_inventory.mjs
  - tests/st0101/test_workspace_bootstrap.py
  - tests/st0104/test_commands_and_docs.py
  - tests/st0105/conftest.py
  - tests/st0105/fixtures/install_crash_driver.py
  - tests/st0105/test_codegen_cli.py
  - tests/st0105/test_commands_and_docs.py
  - tests/st0105/test_determinism_and_safety.py
  - tests/st0105/test_generated_runtime.py
  - tests/st0105/test_manifest_contract.py
  - changes/st-0105/README.md
  - changes/st-0105/manifest.json
  - docs/execplans/ST-0105.md
  - docs/worklogs/ST-0105.md
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
status: clean
---

# Phase ST-0105: Final Code Review Report

**Reviewed:** 2026-08-02T05:31:13Z  
**Depth:** deep  
**Files Reviewed:** 26  
**Status:** clean

## Summary

The complete ST-0105 review scope was re-reviewed at deep depth after the final
two blocker remediations. The public Make/wrapper call graph, exact-tool path
validation, durable install/recovery state machine, generated-output ownership,
manifest contract, isolated test suite, and current documentation were traced
across their module boundaries. Generated Python and TypeScript trees were
assessed through the generator, exact manifest inventory, deterministic
regeneration, compilation/import/schema checks, and runtime tests rather than as
hand-maintained source.

Both previously open blockers are resolved. The public wrapper recovery probe
now operates in a disposable physical repository assembled with independent
byte copies, reaches pending-journal recovery, and stops at the deliberately
absent OpenAPI tool before rendering or installing outputs. The official
install target now retains pending-tolerant storage guards while the generator
recovers before exact tool verification. Datamodel, Node, OpenAPI, and
TypeScript tool paths are validated component-by-component from the filesystem
root with descriptor-relative `O_NOFOLLOW` traversal and exact repository
locations where applicable.

The quiet independent full suite passed: `53 passed in 40.18s`. A metadata and
content snapshot covering 38,635 live repository entries was identical before
and after that run. The comparison included file type/mode, device, inode, link
count, size, nanosecond mtime, nanosecond ctime, symlink target, and content
hashes for the maintained/generated trees and manifest. Thus the copied-wrapper
test, `contract-codegen-test`, and the test portion of `contract-codegen-gate`
did not replace or otherwise mutate the real generated namespaces, manifest,
environment, caches, or transaction state.

All reviewed files meet the applicable correctness, security, and quality
standards. No issues were found. These are local results only: formal TST-004 CI,
human review, release, staging, and production were not executed, and the
documented `IMPLEMENTED_NOT_VALIDATED / NOT_EXECUTED` boundary remains intact.

## Final Remediation Resolution

| Previous finding | Verdict | Current evidence |
|---|---|---|
| Read-only `test`/`gate` reinstalled the real generated outputs | **RESOLVED** | `build_recovery_probe_repository()` uses `shutil.copy2` and `copytree(..., copy_function=shutil.copy2)` in `tests/st0105/test_codegen_cli.py:67-104`; the wrapper install runs only under `TemporaryDirectory` at lines 180-220. An independent copy probe verified 3,269 regular files had different device/inode identities from their sources, link count 1, and identical bytes; all four copied symlinks resolved outside the live repository. The metadata-bracketed 53-test run left all 38,635 observed entries unchanged. |
| Install bypassed storage guards and accepted a symlinked tool ancestor | **RESOLVED** | `contract-codegen-storage-check` is pending-tolerant and is an order-only install prerequisite (`Makefile:188-208`). `_verify_physical_regular_path()` walks from `/` with descriptor-relative `O_NOFOLLOW` (`scripts/build_st0105_generated_contracts.py:198-231`), exact datamodel/OpenAPI locations are enforced at lines 234-250, Node and TypeScript receive the same physical validation at lines 251-314, and recovery precedes verification at lines 2140-2151. The adversarial `node_modules` ancestor-symlink test at `tests/st0105/test_determinism_and_safety.py:127-148` passed. |
| Terminal cleanup or its tombstone could leave recovery wedged | **RESOLVED** | Terminal state is verified, stages are cleaned, the complete journal is renamed to the cleanup tombstone and its parent fsynced before entry deletion (`scripts/build_st0105_generated_contracts.py:1886-1931`); later install-side recovery handles a partial tombstone without parsing it (`scripts/build_st0105_generated_contracts.py:1934-1980`). Existing/fresh crash, rollback re-crash, and tombstone interruption cases all passed in the full suite. |

## Verification Evidence

- `env NODE=/home/minami/.nvm/versions/node/v24.18.1/bin/node
  PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q
  tests/st0105` — `53 passed in 40.18s`.
- The quiet-run pre/post snapshot was byte-for-byte identical for `.venv`,
  `node_modules`, `.npm-cache`, `.pytest_cache`, `python/raos`,
  `packages/web-contracts/src`, and `changes/st-0105`, including inode, nlink,
  mtime, ctime, mode/type, size, symlink target, and maintained/generated content
  hashes.
- Disposable repository copy probe — PASS: 3,269 independent regular byte
  copies, no source/destination hardlinks, destination `st_nlink == 1`, and no
  copied symlink resolving into the live repository.
- Focused tool-path probe — PASS: ancestor and final symlinks rejected; 100
  successful descriptor walks plus both failure paths retained a stable file
  descriptor count.
- `bash -n scripts/codegen_toolchain.sh` — PASS.
- `make contract-codegen-storage-check` with exact Node/npm paths — PASS and did
  not inspect or reject transaction state.
- `.venv/bin/ruff check scripts/build_st0105_generated_contracts.py
  tests/st0105` — PASS.
- Manifest/output reconciliation — PASS: manifest SHA-256
  `7f1ead0b00d7264f40b29c79a06f35cdad06610231a5c7f7a3e5e1d18054ceb7`,
  306 source artifacts, 224 standalone schemas, and 354 sorted output entries
  with exact byte counts and SHA-256 hashes.
- No `.install-transaction.v1`, `.install-transaction.v1.preparing`,
  `.install-transaction.v1.cleanup`, manifest temporary, or ST-0105 stage
  remains in the live repository.
- The final work log state consistently records the two blocker remediations,
  remediated official composite gate, clean `0 BLOCKER / 0 WARNING / 0 INFO`
  re-review, `53 passed in 40.18s`, unchanged 38,635-entry snapshot, and the
  still-pending capture/bundle/post-capture boundary
  (`docs/worklogs/ST-0105.md:103-128`).

An initial full-suite attempt overlapped a separate repository toolchain run
that temporarily recreated `node_modules` and changed local cache metadata. Its
four resulting failures were discarded as invalid environmental interference,
not treated as implementation evidence. The generated roots and manifest stayed
unchanged during that overlap. After all other shared processes exited, the
fresh metadata-bracketed run above passed all 53 tests with no observed state
change.

---

_Reviewed: 2026-08-02T05:31:13Z_  
_Reviewer: Codex (gsd-code-reviewer)_  
_Depth: deep_
