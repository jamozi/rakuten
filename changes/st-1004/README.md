# ST-1004 — disclosure and affiliate CTA local runtime V2

## Local result

This additive V2 implementation turns canonical `UI-C031` into a required
server-rendered `DisclosureBanner` on the one exact ST-1002 local article. The
banner is renderer-owned, non-removable, contains one labelled heading, appears
immediately after the article H1 and before lead/body copy, and uses the exact
recorded disclosure: `この記事にはアフィリエイト広告が含まれます。`

The historical V1
`UNREGISTERED_DISABLED_HEADLESS_ST1004_DISCLOSURE_AFFILIATE_CANDIDATE` and all
of its hostile-input and authority protections remain unchanged and exported.

## Affiliate source and safe omission

The exact ST-0503 normalization dependency intentionally projects
`affiliate_url = None`. V2 preserves that truth as `UNAVAILABLE_SOURCE`:

- the article route contains no CTA anchor, `href`, affiliate destination,
  arbitrary link, redirect, or URL mutation;
- a restrained text notice says that the button is not displayed because a
  confirmed link is unavailable; and
- URL integrity, host allowlist, reachability, link health, freshness, kill
  switch and API-credit gates remain `NOT_EVALUATED`, never coerced to pass.

The fixed future CTA copy is `楽天市場で写真・価格・在庫を見る`; the exact
relation contract is `sponsored nofollow`; and the visible destination label is
`楽天市場`. A value-bearing component model exists only for the exact
`https://example.invalid/rakuten-marketplace/item` synthetic receipt. It uses a
native same-context anchor, has no client handler or beacon dependency, reserves
a 44 CSS-pixel target in both dimensions, is never rendered by the article
route, and cannot accept another URL or a return URL.

No live receipt is accepted. The future
`CLOSED_VERIFIED_AFFILIATE_DESTINATION_RECEIPT_PORT_V1` boundary is explicitly
disconnected until exact URL/host/link-health/freshness/kill-switch/API-credit
authority exists.

## Security and accessibility boundary

The implementation keeps `FR-011`, `SEC-APP-006` and `THR-029` fail-closed:
RAOS has no affiliate redirect endpoint, no cloaking, no required redirect for
measurement, and no caller-controlled destination. Synthetic component input
rejects unknown fields, alternate destinations, queries/fragments, incomplete
verification, subclasses, accessors, symbols, cycles and throwing proxies with
closed, non-reflecting errors.

The route remains a Next server component with one H1, no client component, no
raw HTML and the existing `script-src 'none'`, `connect-src 'none'`, noindex and
no-store headers. Disclosure and unavailability use text as well as visual
cues. The synthetic native anchor has visible focus and target-size rules, but
its browser rendering is local component evidence only.

## Owner artifacts

Owner source is
`changes/st-1004/contracts/disclosure-affiliate-runtime.v2.yaml`. Generate and
check deterministic artifacts with:

```text
.venv/bin/python scripts/build_st1004_disclosure_affiliate_runtime.py
.venv/bin/python scripts/build_st1004_disclosure_affiliate_runtime.py --check
```

The owner writes only:

- `changes/st-1004/generated/disclosure-affiliate-recorded.v2.json`; and
- `changes/st-1004/runtime-manifest.v2.yaml`.

## Authority and remaining work

This is local reversible implementation evidence. It performs no product,
offer, card, image, provider, API, network, DB, analytics, beacon, publication,
staging, release or Production action. It grants no real affiliate destination
or host allowlist authority. Formal TST-020, TST-022 and TST-026, live URL/link
verification, manual screen-reader/200% zoom review, publication, staging,
release and Production remain `NOT_EXECUTED` or unauthorized.
