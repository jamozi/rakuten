# ST-1001 — Public app shell and policy-page candidate

## Status and authority

- Canonical Story: `ST-1001`, design `APPROVED_FOR_IMPLEMENTATION`
- This change: local partial implementation candidate only
- Canonical implementation status: unchanged (`NOT_STARTED`)
- Canonical verification status: unchanged (`NOT_EXECUTED`)
- Formal `TST-022` / `TST-023`: `NOT_EXECUTED`
- Live, browser, staging, release, publication, and production: `NOT_EXECUTED`
- External publication and publication authorization: false
- Domain, site name, operator, consent, privacy-copy, retention, and legal
  approvals: false
- Local eligibility and WCAG conformance claim: false

No local result in this Story grants runtime registration, SSR, approval,
publication, release, staging, or production authority.

## Scope implemented

`packages/web-ui/src/public-shell.ts` is a dependency-free strict TypeScript,
headless, non-executable candidate for the exact canonical policy screens:

- `PUB-004` — `/editorial-policy`
- `PUB-005` — `/affiliate-disclosure`
- `PUB-006` — `/privacy`
- `PUB-007` — `/about`

It also represents only the exact catalog components `UI-C002` PublicHeader,
`UI-C003` PublicFooter, and `UI-C004` Breadcrumbs. `packages/web-ui/src/index.ts`
exports the new contract without changing any existing export.

The model is generic and unbranded while `OD-002` is unresolved. It creates no
runtime route, page, React/Next component, SSR execution, browser behavior,
network request, database access, environment read, clock/random value, event,
tracking call, external link, or publication effect. Header navigation items
are fixed metadata records with `routeRegistered: false`, `interactive: false`,
and `focusable: false`.

Metadata is route-only: the exact canonical screen label is the title,
description and canonical URL are null, and robots is `noindex,nofollow`.
Accessibility structure is a candidate only: language `ja`, skip/header/nav/
main/footer semantics, one H1, one current-page breadcrumb, stable IDs and focus
order, minimum width 320 CSS px with `NOT_EXECUTED` verification, and no
animation. This is not browser evidence and not a WCAG conformance claim.

## Policy-copy boundary

No final policy prose is invented or made renderable. Every content slot has
only:

- a stable topic code;
- state `CANONICAL_PRINCIPLE` or `BLOCKED_OWNER_COPY`;
- a stable principle code;
- `renderedCopy: null`; and
- an exact canonical document plus section/item reference.

The structured topics cover editorial selection, evidence, AI use, human
review, and untrusted-source treatment; affiliate relationship, destination,
and legal review; privacy tracking, cookies/consent, external transfer,
retention, and contact; and operator/contact. `OD-012` keeps nonessential
tracking disabled, while first-party event instrumentation remains out of
scope and `NOT_EXECUTED`. No ST-1701 candidate data is imported or referenced.

## Validation and safety

Inputs and candidate validation reject unknown keys, subclasses, accessors,
symbols, callbacks, dangerous keys, malformed JSON shapes, duplicate route/ID
records, absolute or scheme-relative origins, scripts, analytics, cookies,
beacons, affiliate links, CTA fields, article fields, metadata/a11y drift,
renderable copy, and authority escalation. Errors contain only a closed stable
code and do not echo hostile values. Successful values are detached,
deterministic, JSON-safe, and deeply frozen.

The exact local ST-1001 suites are:

- `tests/st1001/public-shell-contract.test.ts`
- `tests/st1001/public-shell-model.test.ts`
- `tests/st1001/public-shell-boundaries.test.ts`
- `tests/st1001/public-shell-negative.test.ts`

Focused local tests cover the critical negative path but do not satisfy formal
`TST-022` or `TST-023`, which require browser/CI or staging execution per the
canonical suite catalog.

The local focused/static and predecessor evidence was run with pinned Node
24.18.1, npm 11.16.0, TypeScript 6.0.3, ESLint 9.39.5, Prettier 3.9.6,
CPython 3.14.6, and pytest 9.1.1:

- exact ST-1001 Node tests: 19 passed;
- `packages/web-ui/tsconfig.json` no-emit typecheck: passed;
- exact owned ESLint and Prettier checks: passed;
- ST-0103 Vitest predecessor suite: 4 passed;
- ST-0807 predecessor suite: 145 passed;
- workspace no-write check: passed, 42 directories;
- canonical import verification: passed, 105 imported files, 104 package
  checksums, and 103 package manifest entries; and
- exact seven-file non-git fallback secret scan: passed with no findings.

The full ST-0103 Python predecessor suite, with the exact pinned Node/npm
directory on `PATH`, completed with 155 passed, 1 skipped, and 1 failed. Its
sole failure was
`test_python_runtime_validator_accepts_the_exact_hydrated_environment`, with
`Python runtime path must be a real directory: .venv`; the sole skip had the
same unhydrated-worktree condition. The dedicated Story worktree is
intentionally not hydrated and no tool environment was added within this
seven-file change. `contract-gate` therefore remains `NOT_EXECUTED`; its
documented hydrated-environment precondition was not met. This predecessor
environment result is not represented as a PASS and does not establish formal
validation.

The linked-worktree scanner itself failed closed before content scanning with
`ERROR code=unsafe-git-metadata source="."`, as documented for a `.git` file.
The fallback used a complete non-git `git archive HEAD` snapshot, overlaid only
with the exact seven owned files, and ran the unchanged scanner successfully.

## Pro escalation record

The required difficult-work escalation was attempted exactly once and was not
retried:

- run: `20260812T122727Z-ff6e95405c0d`
- result: `PRO_UNAVAILABLE`
- terminal reason: `RESPONSE_NOT_IDENTIFIABLE`
- terminal diagnostic: `ADVANCED_RESPONSE_BOUNDED_CONTENT_INVALID`

No Pro response was admitted as authority. This implementation follows only
the approved canonical Story, canonical safe defaults, and local repository
evidence. It makes no new brand, domain, operator, privacy, consent, retention,
legal, architecture, or publication decision.

## Explicitly out of scope

`apps/web`, workspace layout/bootstrap, runtime route registration, React/Next
pages, SSR, homepage, category, article, 404, status, disclosure banner,
affiliate CTA/link, article data, tracking, event emission, consent UI, final
policy prose, visual design, browser/a11y execution, live provider behavior,
external publication, staging, release, and production remain unimplemented or
`NOT_EXECUTED`.

The canonical and generated status artifacts are not edited by this local
candidate.
