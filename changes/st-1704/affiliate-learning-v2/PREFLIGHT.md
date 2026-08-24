# ST-1704 affiliate-learning V2 preflight

- Story: `ST-1704` — five-article editorial pilot measurement and learning.
- Base: exact delegated integration commit `ed9e3befe225feec26b7f7c3287b68df9028ee44`.
- Read: Canonical master/integration/decisions/open decisions, ST-1704 and ST-1703,
  analytics design/event/KPI contracts, security design/83 controls, all test-suite
  definitions, both existing ST-1704 handoffs/runtime patterns, and the complete
  user-provided 2026-08-23 research brief.
- Research boundary: the brief's `turn...` citations and unverified revenue claims
  are not implementation evidence; no external policy or provider claim is added.
- Open decisions: OD-003/006/007/008/009/012/014/015 remain unresolved. Safe defaults
  are recorded aggregates, `UNAVAILABLE`, disabled tracking, and no external action.
- Planned files: additive contract/domain/ports/service/fixed-path JSON adapter,
  launcher/generator, Story docs/examples/Makefile, focused tests, and the existing
  ST-1704 self-hosted runtime manifest after the runbook-only correction.
- Verification: generator/check, focused positive/negative/filesystem tests, affected
  ST-1704 suite, Ruff format/lint, strict mypy, compile/import, secret/workspace/diff.
- Out of scope: provider/report-row ingestion, credentials, network, live tracking,
  WordPress writes, article/CTA/product/recommendation/snapshot mutation, publication,
  formal TST, staging, release, Production, and Canonical status `APPLY`.
