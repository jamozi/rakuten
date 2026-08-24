# ST-1004 V2 implementation preflight

- Story/objective: `ST-1004` — render a non-removable, first-view affiliate
  disclosure and preserve direct-destination affiliate navigation semantics
  without inventing a destination when the normalized source has none.
- Read inputs: repository and Canonical `AGENTS.md` files; master/integration,
  Canonical decisions and open decisions; ST-1004 plus ST-1002/ST-0503
  dependency implementations; FR-011; PUB-003/PUB-005; UI-C031/UI-C034;
  the public UI/accessibility design; SEC-APP-006/THR-029; and
  TST-020/TST-022/TST-026.
- Safe resolution: ST-1002 already has one exact local SSR article, but ST-0503
  intentionally projects `affiliate_url = None`. The article will therefore
  always render the fixed disclosure before body copy and render an explicit
  `UNAVAILABLE_SOURCE` notice with no CTA. A value-bearing CTA is implemented
  only as an exact `example.invalid` synthetic component fixture. No Rakuten
  URL, host allowlist, live receipt, or link-health fact is inferred.
- Planned owned files: additive V2 types/runtime in
  `packages/web-ui/src/disclosure-affiliate-cta.ts` and its index exports;
  minimal ST-1002 article JSX/CSS integration; ST-1004 contract, deterministic
  recorded output, runtime manifest, owner generator, and focused Node/Python
  tests.
- Local checks: owner generation/check; V1 and V2 ST-1004 tests; affected
  ST-1002/ST-0503/ST-1001 tests; strict TypeScript, ESLint, Prettier, Next build,
  exact-slug browser/axe/keyboard/reflow checks, sensitive-data/canonical/
  workspace checks, and `git diff --check`.
- Out of scope: product/offer/card/image rendering; arbitrary or real affiliate
  destinations; URL/host/link-health/freshness/kill-switch/API-credit proof;
  redirects, cloaking, URL mutation, return URLs, click handlers, client JS,
  beacons, provider/API/network/DB/tracking; publication, staging, release, or
  Production authority. Formal/live evidence remains `NOT_EXECUTED`.
