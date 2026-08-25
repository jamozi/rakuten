# ST-1704 revenue-unblock preflight

- Story and objective: `ST-1704` / prevent an ineligible pilot or temporary
  Review Draft from appearing on the public home page or in the Yoast sitemap,
  while preserving the existing human-only publication boundary.
- Integration slice: `SELF_HOSTED_EDITORIAL_PILOT_V1`, based on
  `origin/main@38518e1a59e5fd52fb5de1001364f248bf7515d9` on branch
  `codex/st1704-revenue-unblock`.
- Read before implementation: Canonical master and integration priority,
  Canonical/open decisions, Story `ST-1704`, `TST-018`/`TST-020`/`TST-032`,
  snapshot-tampering and publication-role controls, the ST-1704 preflight,
  README, runbook, theme contract, theme generator, and focused theme tests.
- Observed live condition, anonymous read only: Review slugs for WordPress post
  IDs 26, 28, 29, and 30 returned public pages and appeared in the Yoast post
  sitemap; the five pilot pages observed at the final or Review slug emitted
  `noindex`. The owner-selected recovery is to return the four Review posts to
  Draft before any final publication. Exact live state is rechecked at the
  Human Gate and is not treated as repository or Production evidence.
- Open decisions and safe defaults: publication, WordPress status/slug/category
  changes, theme activation, credentials, consent, and analytics remain human
  actions. `OD-003`, `OD-005`, `OD-008`, `OD-012`, and `OD-015` remain unresolved;
  no revenue attribution, legal approval, tracking activation, or Production
  claim is inferred. Incremental external spend is fixed to zero.
- Planned implementation: child theme 1.1.1; one request-local, bounded list of
  ineligible pilot post IDs; official Yoast post-ID sitemap exclusion; the same
  exclusion on the front-page Query block; suppression of the complete post
  sitemap and front-page post results if that bounded lookup fails; exact raw
  excerpt-to-description binding; versioned theme/package contracts; focused
  positive and negative tests; deterministic manifests and package.
- Tests: PHP syntax, ST-1704 theme source/package checks, focused theme and
  release-contract pytest cases, Ruff check/format-check for touched Python,
  manifest checks, and `git diff --check`.
- Out of scope: WordPress writes, Draft/public status changes, publication,
  plugin or theme activation, cache purge, credential use, analytics changes,
  arbitrary HTTP/CLI capability, article or recommendation changes, the tracked
  measurement template, all-Story dependency recalculation, full-suite reruns,
  staging/release/Production evidence, and `.playwright-cli/`.

## Owner-private read-only pre-state

- Capture directory:
  `.secrets/st1704-revenue-unblock/prestate-2026-08-25T1634Z/`
- `SHA256SUMS` digest:
  `2661f9027664baa95d875c85501be459d109b52d1a027ac32682bf3f416d6367`
- The owner-only capture contains response headers and bodies for the home page,
  robots, Yoast sitemap index/post sitemap, the five relevant public pages, and
  anonymous REST projections for post IDs 19, 26, 28, 29, and 30. It contains no
  credential and is not committed.
- At capture time, all five pages returned 200 and emitted `noindex, nofollow`;
  the home page and post sitemap contained the four Review slugs. This is public
  observation only, not Production verification.

## Exact Human Gate handoff

The operator-selected containment changes only post status for IDs 26, 28, 29,
and 30 from `publish` to `draft`, retains every revision and byte of article/meta
content, purges the site cache, and then performs the anonymous checks in the
runbook. The repository does not execute this action.

After ID 26 is a Draft and child theme 1.1.1 is active, the AT-003 Tools screen may
evaluate these non-authoritative assertions against the server-side post and exact
request material:

- `review_draft_id=26`
- `target_public_post_id=19`
- `packet_sha256=570708758b22b2af06e663d1e89dbb39bcd2bb4536e039a6c486e6d47405687c`
- `request_sha256=9ead64fcc0bedb35718d9e62c8f073cf89482d97a182243e5852feb4b272b516`
- `payload_sha256=f743a2944f1adca0a8fef2cdd850567767f2257836bb807c47901b25c04fc942`

The corresponding owner-private request artifact SHA-256 is
`2305a5baa3ffc636b90194acdff651310d3ea070c16355cbc99cb958796d04ed`.
The existing live journal is terminal `RECOVERY_ATTEMPTED` with no recorded draft
ID even though anonymous WordPress state shows post 26. Therefore no valid CLI
receipt or `verify-public` gate exists for AT-003. A human must explicitly treat
this as a one-off reconciliation exception; the Tools screen's exact server-side
validation may reject it, and rejection must not be bypassed. No journal is edited
and no create/recover request is retried.

The other observed Review-post bindings are retained for the status-only Human
Gate and later comparison with their already-committed journals:

| Post | Packet SHA-256 | Request SHA-256 | Payload SHA-256 | Artifact SHA-256 |
| --- | --- | --- | --- | --- |
| 28 | `5f3646667cf03572e215799376ed3cd47f7a31c90cdb45116b0868b6e3b51bca` | `9e1a56370986787acaf39ce71f5f7e53b68bf08b7cac9c9cfdb0cdc381de8656` | `b295c42a2fa07de156f4d1af91c8d6117f445d5c3142ac0dd10552fa615600a4` | `0aefd85f5182cba86492f8a56f91cfc200e83be7249ac506e81c0a7c3e7520ce` |
| 29 | `7ec419eaf05208b3d85787623c2c1baeff563777aa67bcd65f320189c00c4c4d` | `a5dbf0ca44996f3bfadf63715ef7acfa46b1a54f976f50dcd06232ae4fe9449a` | `3c2176c72b2ae3888de8f7fa47d6929a900ed78ff56ded195db35bccbdd0e87c` | `86e1b45b38fdc84ef31a6f23abfedf3104f4b6c7db45f7a0e6f39681c537633b` |
| 30 | `532e63fb7cb57102cdf082925072fb06e8f243b7981db434ee04380ee92eb1d1` | `3b6835ca38d6e94b4b201c15f298d35f41f4116f0894dcaf00f10ea7eda7fc1f` | `eac4abe6e2d97750086129db5d9520ce45322b8f2cbba28069b6df05f522ac14` | `09e992efd9e77f82696282017cb7ca2b236f077b7f1c1d20cc246c57167c3f4c` |

Other known publication blockers remain isolated to their articles: the portable
power packet has an unresolved Jackery source-conflict record, and the dishwasher
has no Draft plus no exact THANKO Rakuten evidence. Neither condition delays the
independent containment or theme hardening work, and neither may be converted to a
zero or guessed fact.

WordPress.org's official Yoast 28.3 file-checksum manifest returned HTTP 200 at
`2026-08-25T16:36:44Z`. Its owner-private captured bytes are 343370 bytes with
SHA-256 `1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f`
and 1952 SHA-256 file records. This resolves manifest availability only. Installed
file comparison and the Site Health readback remain Human Gates and `NOT_EXECUTED`.

## Local implementation evidence

- Child-theme package:
  `.secrets/st1704-self-hosted-editorial-pilot/theme/kurashinoshirube-child-1.1.1.zip`
- Package bytes: `321987`
- Package SHA-256:
  `072ba1f5864af0b7f5b5b3c9deaf04ce6c162a13132762b7ffda0b0823de35a7`
- Theme source check and deterministic package check: `PASS`
- Focused ST-1704 theme/release tests: `42 passed`; bounded-listing theme file:
  `35 passed`
- Ruff lint/format, both ST-1704 runtime-manifest checks, and
  `git diff --check`: `PASS`
- PHP syntax check: `NOT_EXECUTED`; no PHP executable is installed in this local
  environment. Human WordPress activation, browser matrix, Draft containment,
  cache purge, Site Health, publication, and `verify-public` remain unexecuted.
