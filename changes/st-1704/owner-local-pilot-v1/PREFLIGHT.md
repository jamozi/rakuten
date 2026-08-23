# ST-1704 owner-local pilot preflight

- Story: `ST-1704` — 5記事pilotの品質・作業量を校正する。
- Read: Canonical integration/decisions, analytics events/KPIs, security/privacy controls,
  TST-018/020/032, ST-1703 self-hosted handoff, ST-1201/1202 disabled tracking,
  ST-1301 unknown-not-zero, and the existing 30/90-day pilot profiles.
- Selected slice: `ST1704_OWNER_LOCAL_PILOT_LEDGER_V1`.
- Open decisions: OD-003/006/007/008/009/012/014/015 remain unresolved. The slice
  uses no provider, tracking, retention automation, ranking mutation, or publication action.
- Planned files: Story-local handoff/docs/Makefile/generated policy/runtime manifest,
  one domain model, inward ports, application service, local JSON adapter, CLI, and isolated tests.
- Verification: focused ST-1704 tests; generator/check; Ruff; mypy; Pyright; shell syntax;
  diff/secret checks. Formal and live suites remain unexecuted.
- Out of scope: WordPress writes, Browser automation, provider/network calls, analytics
  activation, revenue-row ingestion, recommendation changes, auto-publication, release,
  Production, and Canonical/status overlay mutation.
