# ST-1705 implementation preflight

- Story: `ST-1705` — Pilot security/recovery sign-off.
- Objective: produce a deterministic local decision record from the exact
  ST-1607 blocked Gate pack and exact ST-1704 self-hosted/measurement artifacts.
- Read before implementation: root and Canonical `AGENTS.md`, Canonical master,
  integration design and decisions, all Open Decisions, the ST-1607/ST-1704/ST-1705
  backlog rows, TST-026/TST-029/TST-032, Security/Privacy design and 83-control
  catalog, Operations/Recovery design, backup matrix, release evidence template,
  and the exact dependency artifacts bound by the contract.
- Active decisions: fourteen blocking Open Decisions remain active. No value is
  selected or inferred.
- Safe result: `BLOCKED`, `NOT_SIGNED_OFF`, and `NOT_ELIGIBLE` only. The five
  article packets are local tracked artifacts, not real Pilot observations,
  publication evidence, revenue evidence, runtime evidence, or Gate approval.
- Owned files: `changes/st-1705/**`, `tests/st1705/**`, and
  `scripts/build_st1705_pilot_signoff.py` only.
- Tests: deterministic owner build/check; closed contract and future evidence
  schema; dependency semantic/hash drift; duplicate-key, symlink, hardlink,
  oversized input, unsafe path and output tests; fake eligibility rejection;
  recoverable two-output transaction tests; focused/affected suites; Ruff, strict
  mypy, secret/canonical/workspace/diff checks.
- Out of scope: status-registry mutation, `PROPOSE`/`APPLY`, formal suite execution,
  source-freeze or reviewed-tree attestation, live provider/credential use, real
  Pilot observations or revenue, human approval, publication, staging, release,
  deployment, and Production writes.
