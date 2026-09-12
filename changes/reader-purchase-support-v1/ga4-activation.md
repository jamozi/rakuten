# Purchase-support GA4 activation

Status: **OFF / OWNER_CONFIRMATION_PENDING**. Local synthetic checks pass; production activation, provider configuration readback, actual collection and DebugView are **NOT_EXECUTED**. Read credentials are not configured for this work. No Google property creation, credential access or live write was performed.

## Collection boundary

A failed public-snapshot or runtime check on a purchase-support URL closes the Google loader with an empty configuration; it never falls back to legacy collection. The theme requires the approved article/snapshot bindings and explicit `RAOS_PURCHASE_GA4_ENABLED === true`. The gate accepts the tag ID that Site Kit places for the connected stream: either the GA4 measurement ID (`G-…`) or the stream's Google tag ID (`GT-…`, used by Site Kit when the property's Google tag carries one); every config call targets that single ID; `offer_click` carries `send_to` only for a `G-` measurement ID because gtag silently drops events addressed to a `GT-` Google tag ID (the owned config is then the only destination), and any other prefix (`GTM-`, `AW-`, `UA-`) keeps the loader closed. Site Kit's consent-mode stub (`window.gtag` that has only queued `consent` commands while no loader script exists) is replaced by the owned gtag on activation; any other pre-existing executable gtag or loader keeps the gate closed and sets `ga-disable-<id>`. Logged-in WordPress users receive no event configuration. CookieYes analytics consent, WP Consent API statistics consent and Site Kit analytics_storage must all grant analytics before the owned Basic Consent gate creates a tag. Before consent this profile performs no tag/network/cookie/storage operations. Refusal remains closed; withdrawal stops events, disables the tag, clears analytics cookies and reloads. The existing two-year `_ga` lifetime is retained.

All thirteen approved pages, including guides and policies with no seller links, can emit consented page views from their separate approved article identity. Empty offer bindings never synthesize offer clicks. Page views carry approved article_id/snapshot_id and canonical origin + pathname; query strings, hash, referrer and page title are excluded. `offer_click` carries only article_id, product_id, seller_id, offer_id, cta_id, placement, snapshot_id plus GA routing/debug controls. The destination href is compared locally against the approved binding and is never sent as an event parameter. Placements: top_summary, comparison_table, product_card, final_summary. Clicks never become purchase, revenue or confirmed reward.

Owners browsing while logged out can run `localStorage.setItem('raos_purchase_ga4_opt_out', '1')` on the site in their own browser, then reload. This manual owner action persists only in that browser/origin. Remove it with `localStorage.removeItem('raos_purchase_ga4_opt_out')` and reload when intentionally returning to visitor collection. The client reads the flag only after consent and before each event. Blocked storage fails closed. Use logged-in browsing or the browser flag for owner exclusion; consent refusal also excludes collection.

Debug/test runs require explicit `RAOS_PURCHASE_GA4_DEBUG === true` and are tagged `debug_mode:true`; production rejects synthetic DOM clicks. The GA property must exclude developer/debug traffic from production reporting before test collection. No production debug run has occurred.

## Owner setup before activation

The owner must confirm the actual measurement/property IDs and the exact theme release; enable the narrowly scoped theme setting only for that approved release. Register seven event-scoped custom dimensions named article_id, product_id, seller_id, offer_id, cta_id, placement, snapshot_id. Retain the existing readonly Google binding/scope model. The added seller dimension requires actual provider readback; the legacy recorded configuration snapshot remains unchanged and is not proof that seller_id is registered.

Disable GA Enhanced Measurement automatic outbound-click, form, site-search and other unapproved events, since provider-side auto collection bypasses the bounded offer_click payload. Verify developer/internal traffic exclusions and a logged-out owner opt-out before approving activation. Check consent denied, granted and withdrawn paths against actual network requests and DebugView. Until these checks are performed, collection and Google data remain unverified.

## Existing CLI integration

A no-credential/no-network plan is available now:

```sh
.venv/bin/python scripts/raos_editorial_economics_v3.py import-ga4 \
  --profile purchase-v2 --date-from 2026-09-01 --date-to 2026-09-09 --plan
```

This prints the dimensions, required property registration and explicit NOT_CHECKED/NOT_EXECUTED states. It does not read credentials or claim a live configuration check.

After the existing owner-private readonly binding and local database scope have been configured and approved, run the same `import-ga4 --profile purchase-v2` without `--plan`, supplying `--private-root` before the subcommand and `--database-name`, `--database-user`, `--database-password` (safe relative private credential file), and `--ga4-output` (separate private purchase-v2 JSON path), and `--ga4-views-job-id` (a distinct, already registered GA4 analytics job UUID for the page-view report). `--google-scope-receipt`, `--database-host` and `--database-port` retain the existing bounded local defaults. The import reuses the existing Google readonly providers and local aggregate persistence, and writes only the requested private aggregate projection. It neither runs Search Console nor rebuilds the finance baseline. `--profile legacy` imports the legacy GA4 shape; existing `refresh-baseline` remains unchanged.

The purchase profile issues two reports:

- Click report: date, eventName and all seven IDs (GA4's maximum nine dimensions). Only valid offer_click rows appear in output `rows`, and only eventCount is retained. Missing/UNKNOWN identities or unknown placements fail closed.
- Page-view report: date, eventName, article_id, snapshot_id. Only page_view rows appear in `page_view_rows`; their sessions are the article/snapshot denominator. These sessions are never calculated by adding CTA sessions. Missing article/snapshot values fail closed. Respect daily grain and provider threshold/data-loss flags; empty or missing reporting must not be called measured success.

Every row retains its request/grain provenance. The aggregate is engagement evidence; purchase and confirmed reward remain UNAVAILABLE.


The purchase profile requires two separate registered `ops.job` scopes with the same site, GA4 import job type and analytics queue: the click job from the existing owner-private scope receipt, and the page-view job supplied by `--ga4-views-job-id`. Provision these through the existing owner-authorized local job setup; this command does not invent UUIDs or register jobs. A missing/equal page-view UUID is rejected, and the repository rejects an unregistered or wrong-site/type/queue UUID. Keep both IDs dedicated to these exact reports and date range. Reusing either scope for a different report/date range fails the existing immutable replay check; repeating the identical fixture reports replays both imports independently. Legacy imports do not require the new argument and retain their previous scope behavior.

## Shared-property rows and scope uncertainty

The purchase projection uses exactly the generated `ps-` + 32 lowercase hex snapshot namespace for both clicks and page views. It preserves different purchase snapshots separately; it never maps an old placement to a new one. A valid explicit snapshot outside that namespace is excluded as `NON_PURCHASE_SNAPSHOT`. Other event types are excluded as `OTHER_EVENT`. `excluded_row_counts` reports counts of aggregate input rows by reason separately for the offer-click and page-view reports; these are not click/session totals.

Rows whose snapshot and all available business IDs are missing or `(not set)`/UNKNOWN/UNAVAILABLE are quarantined as `UNATTRIBUTED_SCOPE`. Their source cannot be determined, so `scope_status` becomes `PARTIAL_SCOPE_UNKNOWN`, even if some scoped observations remain. Consumers must not treat those missing observations as zero or conclude complete measurement. A missing snapshot alongside populated business IDs, a malformed `ps-` snapshot, or missing IDs/invalid placement inside the purchase scope still fails closed. Purchase page views specifically require article_id and snapshot_id.

When there are no scoped observations, the result has empty observation lists and `NO_PURCHASE_OBSERVATIONS` (or `PARTIAL_SCOPE_UNKNOWN` when unknown rows exist), not invented zero clicks/sessions. `OBSERVED_ROWS_ONLY` means that explicit scoped rows were retained; it does not establish provider setup, full traffic coverage, or successful live activation. Existing threshold/data-loss indicators remain independent constraints. Query and persistence contracts are unchanged, so source aggregate rows and their provenance remain available in the existing owner-private import storage.

## Observation envelope for offer clicks (R2.1)

`scripts/raos_editorial_economics_v3.py summarize-purchase-observations --ga4-input <private purchase-v2 document> --value-basis {DIRECT_EVENT_COUNTS,SAMPLED_ESTIMATE,UNKNOWN} [--quality-flag ...] [--scope-unknown] [--output <private name>]` reads an already imported purchase-v2 document from the private root and joins its retained `offer_click` rows to the publication-time bindings in the tracked theme runtime (`assets/purchase-support.v1.json`) by the seven identifiers. It needs no credentials, database or network and never fetches Google.

- `retrieval_state`: `NOT_RETRIEVED` when no document exists (all counts `null`), otherwise `OBSERVED`. Retrieval alone does not make the values observed events; `value_basis` says so separately.
- `scope_state`: `REPORT_SCOPE_CONFIRMED` for `OBSERVED_ROWS_ONLY` / `NO_PURCHASE_OBSERVATIONS`, `PARTIAL` for `PARTIAL_SCOPE_UNKNOWN` (returned rows keep an identified scope; quarantined rows are not counted), `UNKNOWN` only when passed explicitly.
- `reported_counts` keeps the provider's row values by bucket (`affiliate_text`, `affiliate_image`, `affiliate_surface_unknown`, `merchant`, `unclassified`). A click whose identity has no binding, including a historic snapshot, stays `unclassified`; bindings are never re-read from a newer publication.
- `total_observed_clicks`, `classification_coverage` and `ad_share_bounds` exist only for `DIRECT_EVENT_COUNTS` with an identified scope; they describe the returned rows and are not CTR, CVR, EPC, all-visitor coverage or a causal effect. Sampled or unresolved bases and unknown scopes return `null` for these fields.
- `quality_flags` carries `SUBJECT_TO_THRESHOLDING` when any retained row is thresholded (it does not prove that rows are missing) and any explicitly supplied flag; an explicit empty report yields `NO_OBSERVATIONS` with zero counts and `NO_DENOMINATOR`.
- Observation starts from the live readback time of the published body, runtime and measurement contract, not from a commit or prepare; cache-mixed periods are recorded separately. Purchase and confirmed reward remain `UNAVAILABLE`; measurement itself stays OFF until the owner enables the property.
