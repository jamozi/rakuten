# ST-1102 article workspace static disabled metadata

Status: `LOCAL_IMPLEMENTATION_CANDIDATE` / metadata-only partial safe-interface slice

This reversible implementation-first Wave 3 slice adds a dependency-free,
headless, deterministic, deeply frozen, JSON-safe candidate for the approved
`ST-1102` Article workspace objective. Canonical Story, implementation, and
verification status remains unchanged.

## Preflight and authority

- Story: `ST-1102` — integrate AST, AI diff, Claim, Comparison, and SEO in the
  Article workspace.
- Approved local authority: the owner-approved
  `docs/execplans/RAOS-IMPLEMENTATION-FIRST.md` Wave 3 safe-interface boundary,
  the approved canonical Story, screen/component catalogs, UI design, UI slice,
  and test-suite catalog.
- Dependencies inspected: committed `ST-0806` recorded AI draft integration and
  committed `ST-1101` disabled headless admin UI foundation.
- Pro advisory run `20260812T135228Z-d0a9cb8e5260` was submitted once and
  terminated `REFUSED` with `RESPONSE_NOT_IDENTIFIABLE` /
  `ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID`. The result is `PRO_UNAVAILABLE`;
  it was not retried and supplies no authority.
- Gated ambiguity: cross-module article input, state loading, authorization,
  mutation, persistence, ETag behavior, and runtime composition semantics are
  unavailable. This slice stops at static disabled metadata and does not infer
  them.
- No migration, generated artifact, provider, credential, browser, database,
  network, external action, or Open Decision value is used.

## Implemented maximum-safe boundary

- exact canonical metadata for objective-mapped screens `EDT-002`, `EDT-003`,
  `EDT-005`, `EDT-006`, `EDT-007`, and `EDT-009`;
- explicit exclusion of adjacent `EDT-001`, `EDT-004`, `EDT-008`, and
  `EDT-010`;
- the conservative directly wording- or acceptance-aligned component metadata
  set `UI-C014`, `UI-C015`, `UI-C021`, `UI-C022`, `UI-C023`, and `UI-C036`;
- strict exact plain `{screenId}` input and exact-candidate validation with
  closed redacted error codes, deep detachment, and deep freezing;
- article/version/state/ETag coordinates and blocker/unknown/stale/evidence-gap
  signals fixed to `NOT_LOADED` with `null` values;
- AST, AI diff, Claim, Comparison, and SEO projections fixed to `NOT_LOADED`
  with closed reasons and no payload;
- ETag conflict and unsaved-change behavior fixed to `NOT_EVALUATED`, with no
  overwrite or navigation interception;
- static accessibility candidate metadata for skip/header/navigation/main/
  error-summary/pane-region/footer, one H1, stable IDs and focus order,
  keyboard/screen-reader/visible-focus requirements, text+code+icon status
  cues, no color-only state, and no motion;
- all actions empty, including catalog-critical `EDT-006`;
- `EDT-009` carries no computed canonical, robots, or JSON-LD output.

There is no canonical screen-to-component association table. The component
set is a conservative source-derived projection, not a claim of canonical
ownership. In particular, no SEO-specific component is inferred.

The model accepts no role input. Catalog roles are display-only metadata and
never authentication or authorization evidence. Route registration, rendering,
authentication, authorization, mutation, persistence, provider invocation,
external action, and publication authority all remain false or disabled.

## Validation and hostile-data boundary

Input and candidate validation rejects unknown/extra fields, subclass and
null-prototype objects, accessors, hidden properties, symbols, cycles,
dangerous keys, duplicate IDs/routes, raw HTML/script/iframe or event-handler
surfaces, raw prompts/source/article text, finance/revenue/public fields,
callbacks, URLs/origins, and authority escalation. Errors expose only closed
codes and never echo rejected material.

Focused Node-native tests cover exact catalog/component/source tuples,
determinism, detach/freeze behavior, objective exclusions, disabled authority,
unloaded/unevaluated state, accessibility metadata, hostile input, candidate
tampering, forbidden surfaces, duplicate identifiers, and duplicate routes.

## Explicitly not achieved or executed

This metadata-only partial slice does **not** achieve the `ST-1102` acceptance
criterion. It does not implement or test runtime ETag conflict handling or an
operational unsaved-changes guard. It is not Story completion.

Formal `TST-022`, formal `TST-024`, browser rendering, automated accessibility,
manual keyboard, screen-reader, live, staging, release, publication, and
Production work remain `NOT_EXECUTED`. No completion evidence, status overlay,
or deferred-verification debt entry is added by this slice.

## Local checks

The following checks use the already-hydrated pinned root tools without syncing
or mutating this dedicated worktree:

- `/home/minami/.nvm/versions/node/v24.18.1/bin/node --experimental-strip-types --input-type=module -e "const m = await import('./packages/web-ui/src/article-workspace.ts'); const x = m.createArticleWorkspaceCandidate({screenId:'EDT-006'}); if (x.actions.length || x.projections.some((p) => p.status !== 'NOT_LOADED')) process.exit(1)"` — PASS.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node /home/minami/rakuten/node_modules/typescript/bin/tsc -p packages/web-ui/tsconfig.json --noEmit` — PASS.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node /home/minami/rakuten/node_modules/typescript/bin/tsc --ignoreConfig --noEmit --allowImportingTsExtensions --target ES2024 --module NodeNext --moduleResolution NodeNext --strict --exactOptionalPropertyTypes --noUncheckedIndexedAccess --useUnknownInCatchVariables --forceConsistentCasingInFileNames --types node tests/st1102/article-workspace-contract.test.ts tests/st1102/article-workspace-model.test.ts tests/st1102/article-workspace-boundaries.test.ts tests/st1102/article-workspace-accessibility.test.ts tests/st1102/article-workspace-negative.test.ts` — PASS.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node --experimental-strip-types --test tests/st1102/*.test.ts` — PASS, 23/23 tests.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node --experimental-strip-types --test tests/st1101/*.test.ts tests/st0506/*.test.ts tests/st0606/*.test.ts tests/st0709/*.test.ts` — PASS, 78/78 affected tests.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node /home/minami/rakuten/node_modules/eslint/bin/eslint.js --config eslint.config.mjs --max-warnings=0 --no-warn-ignored packages/web-ui/src/article-workspace.ts packages/web-ui/src/index.ts tests/st1102/article-workspace-contract.test.ts tests/st1102/article-workspace-model.test.ts tests/st1102/article-workspace-boundaries.test.ts tests/st1102/article-workspace-accessibility.test.ts tests/st1102/article-workspace-negative.test.ts` — PASS.
- `/home/minami/.nvm/versions/node/v24.18.1/bin/node /home/minami/rakuten/node_modules/prettier/bin/prettier.cjs --check packages/web-ui/src/article-workspace.ts packages/web-ui/src/index.ts tests/st1102/article-workspace-contract.test.ts tests/st1102/article-workspace-model.test.ts tests/st1102/article-workspace-boundaries.test.ts tests/st1102/article-workspace-accessibility.test.ts tests/st1102/article-workspace-negative.test.ts changes/st-1102/README.md` — PASS.
- `make check-workspace` — PASS with zero changed workspace paths.
- `python3 scripts/import_raos_design.py verify` — PASS for 105 imported files,
  canonical read order, and package checksums.
- `git diff --check` — PASS.

`python3 scripts/scan_secrets.py --worktree` cannot safely resolve linked
worktree Git metadata and returned the redacted operational error
`ERROR code=unsafe-git-metadata source="."` with exit 2. The unchanged scanner
was therefore run against a complete non-Git `git archive --format=tar HEAD`
snapshot overlaid by `cp --parents` with the exact eight owned files after
`cmp --silent` confirmed every overlay byte. `python3
<snapshot>/scripts/scan_secrets.py --worktree` returned exit 0 with no findings.
This closes the sensitive-data check through the scanner's own complete
fallback traversal and is not introduced Story debt.

`make contract-gate` was not run because this dedicated worktree has neither
`.venv` nor `node_modules`; the approved boundary permits that optional
no-network check only when the worktree is hydrated. Contract artifacts are not
owned or changed by this slice.
