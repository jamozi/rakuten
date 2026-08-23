# ST-1704 bounded Rakuten product capture preflight

- Story and objective: `ST-1704` / capture the exact Rakuten Item Search link and
  unmodified 128 x 128 product image needed by the five review drafts.
- Read contracts: Canonical integration decisions and open decisions, `ST-1704`,
  TST-020/TST-032, security/privacy design, the ST-1703 predecessor, this slice's
  design handoff, source/media registries, WordPress runtime, and operations runbook.
- Authorization and ambiguity: the owner explicitly authorized Codex on 2026-08-24
  to use the already-installed owner-private Rakuten credentials without displaying
  them. Product discovery remains fail-closed: zero or multiple exact identity
  matches produces no product evidence.
- Planned files: a separate fixed-origin capture adapter, a separate manifest-bound
  CLI and manifest generator, tests, and the slice documentation. The existing
  ST-1703 runtime and four-command ST-1704 WordPress CLI are unchanged.
- Tests: recorded success/failure fixtures, duplicate/ambiguous identity, accessory,
  URL/TLS/DNS/redirect/response/image/store/credential redaction, manifest drift,
  CLI argument closure, existing ST-1704 suites, lint/type/static/secret checks.
- Out of scope: publication, scheduling, WordPress media, taxonomy, plugin/theme,
  analytics, arbitrary URL/HTTP, recommendation changes, Production or staging
  claims, and automatic selection of an ambiguous product.

This record documents repository-local implementation and the bounded owner action.
It is not formal staging, release, or Production evidence.
