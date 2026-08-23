# ST-1704 self-hosted editorial pilot preflight

- Selected Story: `ST-1704` — five-article editorial calibration pilot.
- Selected integration slice: `SELF_HOSTED_EDITORIAL_PILOT_V1`.
- Site: the existing self-hosted WordPress origin `https://kurashinoshirube.com`.
- Article count: exactly five, including the already-public suitcase comparison.
- Editorial frame: one umbrella category, `暮らしの道具`, with the intent clusters
  `移動`, `家事`, and `備え`.
- Product evidence: official manufacturer facts plus exact Rakuten provider link/image
  evidence. No first-hand review claim and no competitor page as product evidence.
- Revenue boundary: topic, UX, SEO, internal-link, and CTA optimization are allowed;
  affiliate economics never change product recommendation or order.
- Runtime boundary: one allowlisted article per invocation, draft-only WordPress request,
  direct affiliate destinations, no arbitrary URL/HTML or generic HTTP capability.
- Source-capture boundary: one tracked source or allowlisted article per invocation,
  exact registry HTTPS GETs only, no credentials, redirects, caller URL, or publication
  capability; every reviewed locator must match before a current pair is committed.
- Time boundary: only `prepare` and `create-review-draft` require current source and
  provider evidence. Recovery reads the sole owner-only `INTENT` request artifact;
  public verification reads the sole `COMMITTED` artifact, so neither reconstructs a
  confirmed snapshot from later evidence.
- Human gates retained: provider credential/live retrieval, theme/plugin activation,
  privacy/analytics activation, each publication/update, rollback, and Production claim.
- Yoast activation blocker: the exact official 28.3 checksum is unavailable in the
  observed WordPress checksum API; the locally computed archive SHA-256 is not treated
  as an official checksum, and persisted settings require a fresh-request readback.
- Formal evidence: local and CI results remain local/CI evidence. `TST-018`, `TST-020`,
  `TST-032`, staging, release, and Production remain unclaimed until their owners execute
  the Canonical gates.
- Existing `ST-1703` runtime and untracked `.playwright-cli/` artifacts are out of scope
  and must remain unchanged.
