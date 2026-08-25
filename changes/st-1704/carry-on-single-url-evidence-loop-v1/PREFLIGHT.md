# ST-1704 carry-on single-URL evidence-loop preflight

- Story and objective: `ST-1704` / strengthen the fixed `verify-public` read path so
  the carry-on article has one clean public URL and a retained Review Draft cannot
  leak through URL, REST, home, or sitemap surfaces.
- Selected integration slice: `CARRY_ON_SINGLE_URL_EVIDENCE_LOOP_V1`.
- Read before implementation: Canonical master/integration/decisions/open decisions,
  Story `ST-1704`, `TST-018`/`TST-020`/`TST-021`/`TST-022`/`TST-032`,
  `SEC-DATA-004`, `SEC-DATA-006`, `THR-018`, `THR-019`, the existing ST-1704
  handoff, runtime, tests, and revenue-unblock runbook/worklog.
- Open decisions and safe default: site, reviewer, freshness, legal, privacy, and
  provider decisions remain unresolved Canonically. The local safe disposition is
  `Draft + anonymous 404 + no redirect`; this does not authorize the human WordPress
  status action needed to establish that state.
- Planned files: this overlay and strict JSON contract; the existing domain public
  verification record, fixed HTTPS adapter, CLI output projection, focused ST-1704
  tests, existing runbook/worklog, and the generated ST-1704 runtime manifest.
- Exception input: `verify-carry-on-single-url` reads only the exact terminal
  `RECOVERY_ATTEMPTED` AT-003 journal and immutable request artifact fixed in the
  worklog. It binds public post ID 19 and Review Draft ID 26, performs no journal
  lock or mutation, and cannot become formal `verify-public` evidence.
- Evidence shape: each Review URL/public REST/authenticated Draft REST digest binds
  the fixed path, actual status, content type, absent `Location`, relevant REST count
  headers, and response-body SHA-256. The aggregate binds those evidence digests,
  never a body-only Review hash.
- Leak/route checks: HTML entities are decoded and normalized before meaningful
  partial-text comparison across title, excerpt, content, snapshot JSON, and payload
  SHA-256; article fragments use visible text, while the expected clean canonical
  URL itself is the only snapshot window/token exclusion. Dedicated high-signal
  shortened CTA fragments also fail closed. Review
  routes receive one strict UTF-8 percent decode across authority, path, query, and
  fragment, with malformed, ambiguous, and double-encoded values refused.
- Adapter result: the carry-on public method returns only immutable
  `CarryOnSingleUrlReconciliationEvidence`. Its invariants require
  `formal_gate_eligible=false`, `public_surface_verified=false`,
  `strict_public_checks_passed=true`, and `PENDING_HUMAN_EXCEPTION`; the internal
  strict `PublicVerification` is not returned.
- Tests: focused positive and negative public-surface tests, overlay release-contract
  test, Ruff lint/format, deterministic manifest generate/check, compile/import,
  sensitive-data scan where available, and `git diff --check`.
- Out of scope: live reads, credentials, WordPress writes, status/slug/category
  changes, redirect creation, deletion, cache purge, theme/plugin activation,
  publication, analytics, finance, staging, release, Production, Canonical, upstream,
  theme source, article content, recommendations, and tracked measurement records.

The existing owner-gated credential header is reused only by the exact-slug Draft
read. No new credential source or authority is added. No live or public response is committed
by this slice. Local tests use deterministic synthetic response objects only and remain local
implementation evidence.
