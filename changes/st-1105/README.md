# ST-1105 — local admin visual/accessibility acceptance V2

Status: `LOCAL_IMPLEMENTATION_COMPLETE` for a reversible ENV-DEV/CI-only
recorded/synthetic V2. Canonical status is unchanged.

The historical V1 remains byte-for-byte compatible and explicitly incomplete.
The additive V2 supplies the strongest evidence current dependency truth
supports:

- the exact 44 screens exposed by the seven named dependency Stories;
- 29 explicitly exposed components, preserving per-screen, story-level, and
  `NOT_EXPOSED_BY_DEPENDENCY` distinctions;
- all ten canonical critical workflows and all 30 accessibility rows;
- exact TST-023/024/025 metadata without changing execution status;
- versioned fixture, acceptance, baseline, and browser-evidence contracts; and
- strict owner generation, hostile tests, 44 screenshot digests, and hash-bound
  local browser evidence.

No component relationship is inferred where its dependency does not publish
one. Catalog routes remain display-only and unregistered.

## Local browser harness

`scripts/check_st1105_admin_acceptance_browser.mjs` starts only an ephemeral
loopback server and exact Chrome for Testing. Every synthetic screen is checked
at 320 and 1280 CSS px for semantics, zero axe violations/incomplete results,
document reflow, all-control tab reachability, skip-link activation, visible
focus, status/form/table relationships, and exact desktop PNG digests. Every
canonical critical-action screen also exercises an inert dialog's focus entry,
forward/reverse trap, Escape, and return focus.

The 320 profile is an automated reflow proxy for a 640-device-pixel layout at
200%; it is not manual browser zoom. Dialogs never dispatch business actions.

The seven ST-0906 screens also use the dependency's real detached renderer.
That observation is separately `REVIEW_REQUIRED`: each has 326 CSS px of
document overflow at 320 and one axe `aria-prohibited-attr` incomplete result.
ST-1105 neither rewrites ST-0906-owned code nor calls this a pass.

## Generation and verification

Use the exact pinned runtimes. Generated JSON, TypeScript, baseline, evidence,
and manifest must not be edited manually.

```bash
/home/minami/rakuten/.worktrees/raos-local-integration-complete/.venv/bin/python \
  scripts/build_st1105_admin_visual_accessibility.py --check
/home/minami/.local/share/raos-toolchains/node/24.18.1-npm11.16.0/bin/node \
  --no-warnings --experimental-strip-types \
  scripts/check_st1105_admin_acceptance_browser.mjs --check \
  --browser-executable /home/minami/.cache/ms-playwright/chromium-1217/chrome-linux64/chrome \
  --node-modules /home/minami/rakuten/.worktrees/raos-local-integration-complete/node_modules
```

## Evidence and authority boundary

`LOCAL_AUTOMATED_PASS_SYNTHETIC_FIXTURE_ONLY` is not formal, hosted-CI,
staging, manual, screen-reader, real-route, or conformance evidence. TST-023,
TST-024, and TST-025 remain `NOT_EXECUTED`. Manual keyboard/200% zoom,
NVDA/VoiceOver or equivalent, cognitive review, hosted CI, authentication,
authorization, staging, live provider, publication, release, and Production
remain `NOT_EXECUTED` or unavailable. The baseline is not human-approved. No
WCAG conformance or formal Story acceptance is claimed. No route, credential,
external write, provider access, business dispatcher, or operational authority
is added.
