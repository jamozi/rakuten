# ST-1801 implementation preflight

- Story: `ST-1801` — Expand to 30–45 articles.
- Objective: implement a deterministic local portfolio-expansion planner and a
  recorded-synthetic acceptance evaluator without representing planned slots as
  created, approved, or public articles.
- Read before implementation: repository and Canonical `AGENTS.md`, Canonical
  master/integration/decision records, all Open Decisions, ST-1704/ST-1705/ST-1801
  backlog and exact local artifacts, TST-020/TST-032, test acceptance/release
  evidence design, the content quality-gate catalog, Claim–Evidence policy, and
  ST-0605 coverage runtime contract.
- Active decisions: OD-001 is unresolved, so no real category is selected. The
  planner uses a visibly synthetic category placeholder and the fixed ST-1704
  program boundary only. ST-1705 makes downstream ST-1801 `NOT_ELIGIBLE`.
- Safe result: 30 `NOT_CREATED` / `NOT_APPROVED` / `NOT_PUBLIC` placeholder slots,
  overall `BLOCKED`, no actual observation or qualifying evidence reference, and
  downstream GATE-1 eligibility `false`.
- Owned files: `changes/st-1801/**`, `tests/st1801/**`, and
  `scripts/build_st1801_portfolio_expansion.py` only.
- Tests: closed contract/fixture validation, exact dependency hashes, count 29/46,
  duplicate slots, invented category/program, fabricated article state/quality,
  quality and major-Claim boundary arithmetic, missing/zero/invalid values,
  symlink/hardlink/oversize/duplicate-key rejection, recoverable two-output
  transaction, deterministic owner build/check, focused/affected suites, Ruff,
  strict mypy, secret/canonical/workspace/diff checks.
- Out of scope: real category selection, article content/identity/URL/schedule,
  actual quality or coverage observations, article approval/publication, Status
  Registry or GATE mutation, CMS/API/network/provider use, staging, release,
  deployment, Production, and formal TST-020/TST-032 execution.
