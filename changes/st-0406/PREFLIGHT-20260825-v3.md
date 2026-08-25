# ST-0406 durable intake storage hardening preflight

- Story: `ST-0406` — preserve the recorded/synthetic secure object intake while
  making its local SQLite quarantine fail closed against file adoption,
  replacement, history rollback, schema drift, and journal tampering.
- Exact base: `a5803a44dd3d7259b2bf6c98635681020ed7e17f` on isolated branch
  `codex/st0406-sqlite-hardening-20260825`.
- Canonical inputs read: `RAOS-INTEGRATION-001`, the complete `ST-0406` row and
  dependencies `ST-0202`/`ST-0403`, `RAOS-SEC-001`, `SEC-SLICE-005`,
  `SEC-APP-007`, `SEC-APP-008`, `THR-006`, `TST-014`, `TST-026`, `TST-031`,
  the data-classification catalog, open decision `OD-014`, and the repository
  implementation protocol.
- Existing contract and implementation read: the ST-0406 V2 contract, owner
  generator, manifest, domain/port/application/adapter sources, all ST-0406
  tests, and the hardened ST-0401/ST-0402/ST-0403 SQLite patterns.
- Ambiguity resolution: no new provider, retention, deletion, upload, export,
  publication, credential, staging, release, or Production authority is needed.
  `OD-014` stays unresolved; no automatic retention or deletion is introduced.
- Owned edits: ST-0406 adapter, ST-0406 hostile storage tests, V2 contract,
  README, owner generator and deterministic generated/manifest artifacts, plus
  this preflight and a local-only completion proposal.
- Verification plan: full ST-0406 pytest, predecessor ST-0202/ST-0403 and direct
  downstream ST-0808/ST-1301 regressions, owner generation and `--check`, denied
  network execution, Ruff/format, strict mypy and pinned Pyright, compile/import,
  focused secret scan, scope review, and `git diff --check`.
- Out of scope: formal TST execution, native malware or object-storage provider,
  credential access, hosted CI, Security/Privacy approval, Canonical status
  `APPLY`, staging, publication, release, and Production operations.
