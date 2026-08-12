# ST-1004 — disabled headless disclosure and affiliate semantic candidate

## Result and authority

This Story slice adds one dependency-free strict TypeScript candidate named
`UNREGISTERED_DISABLED_HEADLESS_ST1004_DISCLOSURE_AFFILIATE_CANDIDATE`. It
records only the safe semantic boundary for canonical public components
`UI-C031` DisclosureBanner and `UI-C034` AffiliateCTA on `PUB-003`.

The candidate is unregistered, disabled, headless, noninteractive, and
nonfocusable. It creates no disclosure copy, link, DOM, React/Next component,
route, SSR path, API/read-model request, database/network access, navigation,
redirect, click beacon, tracking event, publication action, or external effect.
Canonical Story status remains `NOT_STARTED`; verification remains
`NOT_EXECUTED`. Local evidence grants no policy, security, accessibility,
approval, publication, staging, release, or Production authority.

## Safe input and semantic boundary

Input contains only exact `PUB-003`/`/articles/{slug}` metadata and one
explicitly synthetic coordinate whose two caller-supplied lowercase SHA-256
strings must be equal. The hashes are opaque coordinates: they are not
recomputed, canonicalized, attested, or treated as a verified projection,
disclosure, or affiliate link.

The fixed candidate declares future requirements without executing or proving
them:

- `UI-C031` remains renderer-owned, non-removable, and required at the article
  top in the first viewport, while policy/context references and rendered copy
  remain unavailable;
- `UI-C034` remains disabled and valueless while declaring destination clarity,
  the `sponsored nofollow` token contract, direct-provider navigation, and the
  prohibition on RAOS redirects, cloaking, and URL modification;
- URL integrity, allowlist, reachability, link health, freshness, and affiliate
  kill-switch evidence remain `NOT_EVALUATED`;
- API-credit applicability and copy remain unavailable; and
- future navigation must not depend on a click beacon, while neither navigation
  nor beacon execution exists in this slice.

Disclosure precedes the inert CTA semantically, both remain separate, and the
CTA must not dominate editorial evidence. No layout, visual treatment, copy, or
motion is selected because no DOM exists.

Inputs and candidates reject unknown shapes, subclasses, accessors, symbols,
cycles, unreadable or throwing proxy surfaces, copy, URLs/hosts/hrefs,
references, internal fields, effects, malformed or mismatched hashes, and
semantic or authority escalation. JavaScript forwarding proxies are not claimed
as a distinguishable input class; callers must provide already materialized
plain data rather than use proxy behavior as a trust boundary. Errors expose
only closed codes and never echo hostile values. Successful candidates are
detached, deterministic, JSON-safe, and deeply frozen.

## Why actual rendering and navigation remain closed

Merged ST-1002 supplies no renderable content, DOM, route, public-read-model
input, or authoritative projection. Merged ST-0503 deliberately leaves
`affiliate_url` unset and does not read the recorded provider affiliate URL.
The installed PublicOffer surface contains affiliate URL, destination host,
freshness, and CTA state, but no implemented authoritative projection binds it
to these predecessor slices.

A value-bearing renderer therefore still requires canonically reconciled,
owner-approved authority for the affiliate-link resolver and exact safe public
input, official URL integrity/hash and destination allowlist, link-health and
reachability evidence, disclosure-policy currentness and payload, article
disclosure context, API-credit applicability/source, freshness, kill-switch
generation, and beacon/navigation behavior. No such value or truth is inferred
here.

## Owned files and checks

The exact owned paths are:

```text
packages/web-ui/src/disclosure-affiliate-cta.ts
packages/web-ui/src/index.ts
tests/st1004/disclosure-affiliate-contract.test.ts
tests/st1004/disclosure-affiliate-model.test.ts
tests/st1004/disclosure-affiliate-negative.test.ts
tests/st1004/disclosure-affiliate-boundaries.test.ts
changes/st-1004/README.md
```

Focused local tests cover the strict contract and critical negative paths.
Affected ST-1001/ST-1002/ST-1003 and pinned ST-0503 suites, TypeScript, ESLint,
Prettier, workspace and canonical no-write checks, sensitive-data scanning, and
`git diff --check` are the local implementation checks. They do not satisfy
formal `TST-020`, `TST-022`, or `TST-026`.

## Explicitly out of scope

Disclosure or API-credit copy, policy activation/currentness, PR-benefit
wording, ArticleDisclosureContext data, affiliate/offer/link identities,
URLs/hosts/hrefs, URL resolution or modification, allowlist/DNS/IP/reachability
or link-health verification, freshness, CTA enablement, kill-switch evaluation,
HTML/DOM/React/Next/CSS, route registration, SSR, API/read model, redirect,
navigation, beacon/tracking/events, browser and assistive-technology execution,
formal content/browser/security suites, approval, publication, live, staging,
release, and Production remain unimplemented, unavailable, unauthorized, or
`NOT_EXECUTED`.
