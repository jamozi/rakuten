# ST-1607 Gate evidence pack

ST-1607 implements a deterministic, local-only gate report that fails closed.
It binds the exact Canonical, status, decision-gate, and predecessor artifacts
used to construct the report. The generated report marks `GATE-0` through
`GATE-4` as `BLOCKED` because required formal evidence, active decision
clearance, target snapshot context, and human gate approvals are absent.

This slice does not execute `TST-032`, deploy to staging, call a provider,
approve a gate, apply a status transition, create a release, or authorize
Production. The report is `LOCAL_BLOCKED_NON_ATTESTING`; local generation and
tests cannot be interpreted as formal gate evidence.

Canonical does not define a typed suite-to-gate mapping. The report therefore
uses one explicit global blocker inventory for every gate and forbids inferred
suite-to-gate mappings. ST-0006's approved fail-closed policy remains the source
for applying every active blocking Open Decision to every gate; its
`required_by` text remains opaque context.

## Implementation preflight

- Story/objective: `ST-1607`; render an immutable, deterministic Gate report
  whose missing or non-qualifying evidence blocks every Gate.
- Read inputs: Canonical integration/status/decision/Test/Security sources,
  ST-0005 and ST-0006 status boundaries, and the exact ST-1603, ST-1605, and
  ST-1606 contract/report/manifest bytes.
- Open decisions: fourteen active blocking decisions are preserved; this Story
  selects no decision value and uses the ST-0006 global fail-closed mapping.
- Owned changes: only this Story's contract, generator, tests, documentation,
  and generated report/manifest.
- Local checks: owner generation/check, focused and predecessor suites,
  hostile path/recovery/concurrency cases, Ruff format/lint, strict mypy,
  canonical/workspace/secret checks, and `git diff --check`.
- Out of scope: formal TST-032, live/staging evidence, source-freeze or reviewed
  tree attestation, Gate approval, status `APPLY`, publication, release, and
  Production action.

## Owner files

- Contract: `changes/st-1607/contracts/gate-evidence-pack.v1.yaml`
- Local completion record: `changes/st-1607/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml`
- Generator: `scripts/build_st1607_gate_evidence_pack.py`
- Generated report: `changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json`
- Generated manifest: `changes/st-1607/manifest.yaml`

The generated report and manifest must not be edited manually.

## Deterministic generation

```bash
/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python -I -B scripts/build_st1607_gate_evidence_pack.py

/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run \
  --locked --offline --no-cache --no-sync --no-env-file \
  python -I -B scripts/build_st1607_gate_evidence_pack.py --check
```

The CLI requires both Python isolated mode and no-bytecode mode before loading
PyYAML. It has no network, provider, credential, subprocess, Git, browser, or
environment-value read surface.

`--check` is read-only and fails if either generated file differs byte-for-byte
from owner-source regeneration. It never performs recovery: any pending
transaction coordinator or companion causes a sanitized recovery-required
refusal without a write.

A default build is a single-process same-UID maintenance operation. A fixed,
owner-only advisory lock on the pinned manifest-parent directory rejects a
concurrent generator or check before recovery or output mutation. The generator
renders and stages both files, revalidates their pinned target directories and
exact target state, then publishes the pair through one recoverable
transaction. Existing outputs are rename-backed so a failed publish can restore
their exact bytes, inode, mode, and mtime. Every publish, rollback, and
coordinator transition is fsynced in its owning directory.

Fixed hidden next/previous/absence/coordinator companions are recovery state
only: they are neither tracked outputs nor gate evidence. The next default
build recovers a valid closed state before validating sources. An unsafe,
unknown, conflicting, or unexpectedly shaped companion/target is retained and
fails closed; it is never guessed, overwritten, or glob-cleaned. Clean success
leaves no companion. All hashed inputs and the owner contract are parsed from
bytes captured through a descriptor-relative `O_NOFOLLOW` component walk from
the physical repository root under the exact 2 MiB ceiling; hashes and parsers
consume those same captured leaf bytes, and oversized or changed input fails
before output mutation. The hash-bound ST-1505 implementation reference is
never imported or executed; ST-1607 owns its bounded-read constant,
duplicate-key loader, root validation, and sanitized error mapping locally.

## Evidence boundary

- `TST-026`, `TST-028`, `TST-029`, `TST-031`, and `TST-032` remain formal
  `NOT_EXECUTED` inputs; the dependency artifacts are non-attesting local
  reference/synthetic artifacts and are not promoted to formal evidence.
- Fourteen active blocking Open Decisions remain unresolved in the bound
  ST-0006 report.
- Release version, staging snapshot time/data identifier, release identifier,
  reviewed implementation-tree commit, exception approvals, and human gate
  approvals are absent.
- The exact local base commit is a typed, recorded predecessor-checkout value
  only. It is explicitly non-qualifying. The source-freeze identifier and
  reviewed implementation-tree commit are separately typed but `ABSENT`; a
  recorded base value cannot be promoted into either identity or Gate evidence.
- External, staging, status-apply, publication, release, and Production
  authority are all `NONE`.
- Effective Canonical Story/test status remains unchanged.
