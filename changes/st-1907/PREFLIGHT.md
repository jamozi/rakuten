# ST-1907 preflight

- Exact base: `3d454db83f59e2854c0680a26dd0a7351cfe47ab` in isolated
  worktree branch `agent/st1907-local-complete`.
- Story: ST-1907, Post-MVP human proposals for portfolio strengthen,
  consolidate, or withdraw candidates; dependency ST-1805; TST-032; separate
  release decision.
- Read before implementation: repository and Canonical Codex protocol,
  integration precedence/decisions/open decisions, the Story and Post-MVP
  backlog design, ST-1303 through ST-1305, ST-1704, ST-1801 through ST-1805,
  measurement/learning/finance-editorial contracts, TST-032, security/privacy
  design, roles, data classes, controls, threats, adjacent disabled Post-MVP
  seams, and owner-generator patterns.
- Current dependency evidence: exact ST-1805 pack SHA-256
  `cd1aec0ac8a87809389e681b8e1c67328b0120b244aa6fcc7725f11e4d15dff4`
  is `BLOCKED`, `NO_DECISION`, unauthorized, contains zero actual
  observations, and is not locally integrated.
- Safe implementation: additive provider-neutral domain/port/application and
  strict one-shot caller-bytes adapter; disabled by default; executable only
  with recorded/synthetic input in ENV-DEV or CI; human-review metadata only.
- Fail-closed result: current evidence and every missing, mismatched,
  unverified, immature, unavailable-denominator or zero-denominator input yield
  `UNAVAILABLE` and no proposal.
- Authority excluded: activation, approval, auto-apply, `APPLY` status,
  recommendation/order mutation, product selection, article HTML, CTA,
  publication snapshot, persistence, provider/network/credentials, live data,
  publication, staging, release, and Production.
- Finance separation: reward, commission, affiliate rate, EPC, RPM, cost, and
  profit cannot enter proposal evaluation or affect editorial recommendation
  or order.
- Local verification plan: owner generation plus no-write check, focused and
  hostile tests, compile/import, Ruff format/lint, strict mypy, configured
  Pyright on the four owned production modules, sensitive-data/capability
  scans, and `git diff --check`.

This preflight authorizes no external or operational action. Formal TST-032,
real observations, human business decisions, staging, release and Production
remain separate.
