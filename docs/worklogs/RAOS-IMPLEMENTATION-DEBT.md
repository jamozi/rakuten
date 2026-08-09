# RAOS implementation-first deferred verification ledger

This ledger supports the owner-approved
`docs/execplans/RAOS-IMPLEMENTATION-FIRST.md`. It records work that may be
deferred during local feature implementation but must be reconciled before
`LOCAL_INTEGRATION_COMPLETE`.

It is not canonical status, formal evidence, a waiver, or production
readiness. Entries are append-only in identity: do not delete or reuse an ID.
Close an item by adding dated closure evidence to the same entry.

## Required entry fields

- ID and status: `OPEN`, `IN_PROGRESS`, `CLOSED`, or `EXTERNAL_BLOCKED`.
- Introduced by Story/commit or inherited fixed snapshot.
- Exact failing or skipped command and sanitized observed result.
- Runtime/safety impact.
- Affected source, owner generator, generated artifacts, and downstream pins.
- Closure Wave and acceptance evidence.
- Formal/live boundary when applicable.

## Initial ledger

### DEBT-W0-001 — ST-0703 direct runtime pin and provenance fan-out

- Status: `OPEN`.
- Introduced by: ST-0703 local implementation candidate based on approval
  checkpoint `4e0a75f658c08a8d124255b522d23e59ac457163`.
- Evidence:
  - `pyproject.toml` and `uv.lock` require `openai==2.52.0`.
  - Base-byte `tests/st0102/test_toolchain_contract.py` lacks the matching
    direct-runtime requirement and pin entries.
  - Exact ST-0102 wrapper result: `3 failed, 45 passed`.
  - Direct isolated parent confirmation: `2 failed, 27 passed, 19 skipped`;
    the skips are exact-uv discovery cases not run through the wrapper.
- Required source closure: add the exact sorted requirement
  `openai==2.52.0` and pin `openai: 2.52.0` to the ST-0102 inventory.
- Provenance impact: the source is tracked by ST-0801, ST-0703, and ST-0301;
  ST-0301 then participates in ST-0302/ST-0303/ST-0307 and later hash chains.
- Safety impact: no live/provider/credential/production path; local contract
  and generated provenance are stale until closure.
- Closure Wave: source update in W0/W1; complete downstream owner regeneration
  in the final source-to-owner audit unless an earlier Wave freeze can close it
  without semantic changes.
- Acceptance: ST-0102 exact wrapper green, all affected owner no-write checks
  green, semantic projections unchanged except the approved direct pin, and no
  hand-edited generated file.

### DEBT-W0-002 — ST-1203/ST-1204 predecessor provenance debt

- Status: `OPEN`.
- Inherited from: fixed WIP audit at
  `1ced6434907c95ad063a472dc81644f8f00e4cce`.
- Evidence: ST-1203 and ST-1204 each reported four predecessor-hash failures;
  partial ST-0204 repair was explicitly rejected because an independent stale
  ST-0305 pin also exists.
- Safety impact: recorded/live analytics adapter readiness and production
  readiness remain blocked; no reason to block dependency-independent local
  implementation.
- Closure Wave: W2 source freeze or final audit, through each Story's owner
  contract/generator and complete predecessor reconciliation.
- Acceptance: no partial pin edit, both owner checks and isolated suites green,
  and live/provider validation remains separately classified.

### DEBT-W0-003 — synthetic security-fixture scanner classification

- Status: `OPEN`.
- Inherited from: fixed WIP audit at
  `1ced6434907c95ad063a472dc81644f8f00e4cce`.
- Evidence: six unchanged `GENERIC_CREDENTIAL` findings in synthetic security
  test material and zero new WIP finding groups.
- Safety impact: no evidence that the WIP added a credential, but the scanner
  gate cannot be called green and must not be weakened with a broad exclusion.
- Closure Wave: W5 security-verification work or final audit.
- Acceptance: content-addressed path/rule/fixture-digest classification,
  mutation tests proving new/changed credentials still fail, no matched value
  printed, and full worktree/history scan green under the approved policy.

### DEBT-W0-004 — formal and external verification boundary

- Status: `EXTERNAL_BLOCKED`.
- Inherited from: canonical status overlay and ST-0703 authority chain.
- Deferred work: formal TST/hosted CI where absent, live providers,
  credentials/Secrets, real external accounts, staging, real pilot/observation
  periods, human business/security/release decisions, publication, deployment,
  and production.
- Safety impact: local code may progress, but none of these states may be
  represented as executed, validated, deployed, or production-ready.
- Closure Wave: outside automatic local implementation unless separately
  authorized and actually executed.

### DEBT-W0-005 — unresolved canonical Open Decisions

- Status: `EXTERNAL_BLOCKED`.
- Source: `docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml`.
- Rule: implement only documented safe defaults, provider-neutral interfaces,
  synthetic/recorded fixtures, and default-disabled activation. Never invent a
  category, brand/domain, attribution method, cost/labor value, identity
  threshold, freshness SLA, legal decision, provider/credential choice,
  region, retention policy, or production activation.
- Closure Wave: individual decisions remain external until their named human
  owner supplies and approves the value.

## Concurrent ownership reservation

At creation time, another Codex owns ST-0101 resilient Pro-runtime work,
including `AGENTS.md`, `docs/worklogs/ST-0101.md`,
`scripts/chatgpt_pro_orchestrator.py`, and
`scripts/chatgpt_pro_mcp_runtime/**`. These paths are neither debt nor part of
ST-0703. Preserve them and serialize any root-policy integration after that
owner's checkpoint.

## Closure log

Append dated closure records here. A closure record must name the debt ID,
commit, commands, results, regenerated owners, reviewer, and remaining formal
boundary. Do not replace failure evidence with a summary that hides the
original result.
