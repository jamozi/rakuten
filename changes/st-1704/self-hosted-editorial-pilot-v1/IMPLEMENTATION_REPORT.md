# ST-1704 implementation report

Status: local implementation, browser review, source refresh, and code/contract test
suites complete; `HUMAN_REVIEW_PENDING`; publication remains fail-closed. The final
database wrapper is environment-blocked because Docker is unavailable.

## Most important difference

The first decision is now bounded and explainable: a reader sees that this is a
three-model ACE comparison, that no hands-on test was performed, which facts are
official, which recommendations are editorial, and who should not choose each model.

## Existing strengths retained

The indigo/clay/paper palette, Mincho headings, explicit ad/editorial-policy language,
direct Rakuten link validation, `rel="sponsored nofollow"`, recommendation/reward
independence, immutable snapshot binding, and fail-closed publication remain intact.

## First fixes

1. Bound the hero and made mobile height content-driven.
2. Forced the 390 px trust bar to one column.
3. Rebuilt the home sequence without unverified popularity language.
4. Reframed the suitcase article around scope, reader situation, evidence, and
   trade-offs.
5. Added evidence levels and versioned presentation detail to the shared renderer.

## Git, story, and handoff

- Story: ST-1704.
- Base: `origin/main@2f59087a102af587c15fa5ea0514ccd64d7e7a09`.
- Branch: `codex/st1704-editorial-ux-gap`.
- Integration: one PR; auto-merge is explicitly disabled. The PR URL is recorded in
  the final handoff.
- Untracked `.playwright-cli/` is user-owned, preserved, and excluded from staging.

## Seven-area result

| Area | Result | Reason |
|---|---|---|
| Look | implemented | consistent tokens, bounded hero, richer cards, image rules |
| Recommendation | implemented | condition, reason, fit/non-fit, caution, evidence |
| Japanese | implemented, human review pending | distinct scene-led openings and less repeated specification prose |
| Story | implemented | stairs/storage, constrained access, and capacity/front-pocket situations |
| CTA | implemented | consistent verification-oriented label and context |
| Trust | implemented | author/check/date/ad/scope/no-test and evidence class |
| Measurement | contract only | semantic attributes; no GA4 or other transmission |

## Reuse and duplication removal

All five articles use one renderer and one card component. The suitcase article
requires `presentation_v2`; the other four use safe existing-data fallbacks. CTA copy
is one domain constant. Design tokens live in the theme stylesheet and are mirrored
as an interface in the theme contract.

## Before and after

The public before state is recorded in `BENCHMARK_2026-08-26.md`. Seven RAOS-only
screenshots are bound in `visual-evidence/manifest.v1.json`. Key pairs are:

| Surface | Public before | Local after, explicitly not production |
|---|---|---|
| home 1440 | `before-public-home-1440.png`, `ddaa8ed4…` | `after-local-home-1440.png`, `6a1c99d9…` |
| home 390 | `before-public-home-390.png`, `a0683db4…` | `after-local-home-390.png`, `45f90aa7…` |
| article 390 | `before-public-article-404-390.png`, HTTP 404, `51b7c67b…` | `after-local-article-390.png`, `ada0ffd6…` |

The local article 1440 full-page capture is `033769e8…`. Manifest entries retain
the full SHA-256, source, capture time, mode, and viewport.

## Official-source refresh

The registry now targets the requested ACE colour variants (`05721-04`, `01471-02`)
and ANA's notice for travel from 2026-07-01. The closed read-only capture ran from
committed bytes on 2026-08-26 UTC. All seven article sources returned HTTP success
and passed the registered locators; raw captures remain ignored and are not
committed. The requested four refresh results are:

| Source | Captured at (UTC) | Body SHA-256 | Response SHA-256 | Difference classification |
|---|---|---|---|---|
| ACE Cresta 06316-01 | 2026-08-26T14:43:59Z | `99c442f2e7f139d1c3e1eec3c4f6b60ecde0134d57fb47f8a4eed5ab7d9dc2bc` | `24b51d3fe2bf9cd5d33594b27fb5872ad2e489dd4255a66dd901f8ee60eac07e` | body changed from the earlier same-day dynamic response; registered locators verified |
| ACE Difference 05721-04 | 2026-08-26T14:44:00Z | `8cf4bf3af9ee6e16dc668f440e82b958d95872e1026c7ba59d46a2de065ccca5` | `0d4fb8d32852b958bab9e377b721b67dc23dd43a7e8d8f614994ede4dc47334a` | `TARGET_CHANGED_LOCATORS_VERIFIED` |
| ACE Maxpass 4 01471-02 | 2026-08-26T14:44:00Z | `92bf138a09ef45f7ec3975532b35ca52e9fc448cd201a9e6cf3e07ba320ea3b6` | `811a4c608d71dc9d3348ff3a7c60c0f8e31cb4a44fe2c4f3a5986af5540aff07` | `TARGET_CHANGED_LOCATORS_VERIFIED` |
| ANA carry-on notice | 2026-08-26T14:44:00Z | `eea49d473c71cc1496e445dba043ea7c5f4c14067686c4af8c6643f6a561c8d3` | `4f453816b5adce54e3f92bfd315cd58d86331a70b4574ba1381b2e6930d71d2c` | `TARGET_CHANGED_LOCATORS_VERIFIED` |

Inventory and colour remain observation-time information and are not fixed article
facts or ranking inputs.

## Validation ledger

| Command | Status | Result |
|---|---|---|
| baseline ST-1704 gate | PASS | 412 passed before implementation |
| focused content/source/CLI/theme/release tests | PASS_WITH_EXPECTED_DRIFT | 200 passed; one expected manifest drift before regeneration |
| official-source capture | PASS | 7/7 HTTP captures and registered locators verified; no credentials or publication authority |
| repository `make generate` | PASS | affected owner cascade generated deterministically; final runs report `status=PASS` |
| slice `make check` | PASS | 415 passed; manifest and theme package checks passed |
| repository `make check` | PASS | Ruff, mypy (563 files), Prettier, ESLint, TypeScript, Pyright, generator and status checks passed |
| repository `make fast` | PASS | generator check passed |
| `make final`, attempt 1 | FAIL_FIXED | 4 ST-1907 tests exposed a stale hard-coded signal-policy hash; helper now reads the owner fixture; ST-1907 is 47 passed |
| `make final`, attempt 2 | FAIL_FIXED | 16,247 passed, then generated `*.pyc` files caused the strict inventory suite to fail; caches removed and bytecode disabled for the rerun |
| repository `make final`, final run | ENVIRONMENT_BLOCKED | 16,247 passed / 25 skipped; DB/storage selection 1,998 passed / 231 skipped; contract suite 165 passed; `database` stopped because Docker is unavailable, so `storage` was not run |
| real-browser matrix | PASS | 360/390/768/1440, 200% text zoom, keyboard/focus, forced colors, reduced motion, no page overflow |

The final run used the pinned Node 24.18.1 / npm 11.16.0 toolchain. PostgreSQL
18.4-dependent cases and one Docker-dependent runtime case were explicitly skipped
by their environment guards. No result is represented as formal CI, staging,
release, or Production evidence.

## Not implemented / external actions not executed

WordPress login, post update, publication, theme/plugin operation, Rakuten API
request, GA4/Search Console change, staging, deployment, release, and production
verification were not executed. A verified Rakuten product image and direct affiliate
URL are still required for public payload rendering; the visual fixture may use only
a neutral placeholder. No product image was copied or fabricated.

## Production handoff and rollback

A future human operator must review copy, exact package hash, source evidence, image
and affiliate bindings, then follow `OPERATIONS_RUNBOOK.md`. This implementation does
not remove any gate. Repository rollback is `git revert <integration-commit>`; the
live runbook can restore the previously reviewed child-theme 1.1.1 containment floor.
No force-push, history rewrite, row deletion, or irreversible migration is used.
