# Owner runbook: review draft to public verification

This runbook starts only after the repository manifest and local checks pass. It does
not grant publication, credential, provider, plugin, theme, privacy, rollback, or
Production authority.

Run every `prepare`, `create-review-draft`, `recover-create-review-draft`,
`verify-carry-on-single-url`, and `verify-public` command from the exact repository root through the isolated process
below (substitute only the closed command and allowlisted article ID):

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  "$PWD/.venv/bin/python" -B -I -S -X pycache_prefix=/dev/null \
  scripts/st1704_self_hosted_editorial_pilot.py prepare \
  --article-id st1704-portable-power-station-guide
```

The CLI refuses before RAOS import, credential/journal access, DNS, or HTTP unless
its direct-script process, standard-library import path, repository root, current
`HEAD`, committed manifest, predecessor, and all listed runtime bytes match. The
inventory includes the transitive ST-1703 live
credential/REST/HTTPS modules, the complete generated Content AST Python tree, and
the frozen Content AST schema. Tracked article/source/media/theme/schema reads remain
bound to the verified in-memory bytes even if the worktree changes later. Only then
is the owner-safe fixed virtual-environment package directory appended directly;
`site`, `.pth`, `sitecustomize`, and `usercustomize` are not executed. The sole
stage-zero refusal is `SELF_HOSTED_EDITORIAL_PILOT_RUNTIME_INVALID`. External
validation dependencies load before any RAOS package is created; every loaded RAOS
module is then rechecked by verified-loader and object identity before live boundaries.

## Before any live change

1. A human operator records the active theme and plugin inventory, the current public
   HTML, `robots.txt`, and every current sitemap response outside this repository.
2. The owner-authorized command performs the bounded Rakuten Item Search retrieval
   for one selected article using the already-installed owner-private
   credential. Every product must resolve to the exact product code or JAN, direct
   affiliate URL, exact 128×128 HTTPS image, retrieval time, response hash, and image
   hash. A missing or ambiguous product keeps that article blocked. The command has
   no publication, WordPress, arbitrary URL, or generic HTTP capability.
3. Run the repository manifest check and the complete local test target. Local output
   remains local evidence and is not staging or Production evidence.
4. Review and merge the exact tested GitHub head only after required CI is terminal and
   acceptable. Re-run the manifest check at the merged head; any drift invalidates the
   handoff.

## Human-only containment of an accidentally public Review Draft

The repository exposes no command for this operation. If a temporary
`raos-review-*` post is public, a human WordPress operator first records its ID,
status, slug, title, category, current revision, and closed snapshot hash. The
operator then changes only the post status to `draft`; title, slug, excerpt, content,
snapshot meta, category, media, and revisions remain unchanged. Do not delete or
replace the post. Purge the existing site cache through its normal human-operated
control only after all selected status changes have succeeded.

For the 2026-08-26 revenue-unblock incident, the closed target set is post IDs 26,
28, 29, and 30. After the human action, an anonymous read must prove that each Review
URL is non-public, each ID is absent from the public posts REST projection, and no
Review URL appears on the home page or in the Yoast post sitemap. Post ID 19 remains
unchanged until its separate AT-003 snapshot update. Any mismatch stops later
publication; it does not authorize an automated retry or a broader WordPress write.

Child theme 1.5.0 independently excludes every temporary Review slug and every
allowlisted final slug without an exact bound public snapshot from both the Yoast
post sitemap and the front-page latest-guides Query block. This is defense in depth,
not authority to perform the human containment action.

For a 1.5.0 publication readback, both MCP status surfaces must report runtime
revision `898e85031f5cab609ba6d9bb601608b5b0b6205c759842d292a3f86ae66d39e7`.
The anonymous and authenticated page checks also fetch the two same-origin theme
stylesheets without redirects and require distinct base/Editorial V2 sentinels,
HTTP 200, `text/css`, bounded strict UTF-8, and an observed content hash and size.

## Human-gated five-article recovery schedule

The offsets below begin with the first successful human-confirmed public action.
They combine the canonical publication-plan order with the current incident IDs and
article-specific stop conditions. A failed article keeps only that article blocked;
it does not shift an independently ready article or authorize a bypass.

| Offset | Article and WordPress identity | Required gate before the human public action |
| --- | --- | --- |
| Day 1 | Suitcase: Review post 26 remains Draft; existing final post 19 is the only update target | Uniquely reconcile the immutable AT-003 request and exact hashes in `REVENUE_UNBLOCK_WORKLOG.md`; use only the human Tools screen if its server-side validation accepts the one-off journal state |
| Day 4 | Portable power: post 28 moves from Draft to its final slug only after a valid successor snapshot is confirmed | Recheck the resolved Jackery 500 New evidence under the conditions below; if the packet changes, use the closed revision path and do not reuse a stale snapshot or Rakuten capture |
| Day 7 | Anker model comparison: post 29 moves from Draft to its final slug | Confirm the existing committed request, final slug, category, exact snapshot, and current product evidence |
| Day 10 | Dishwasher: prepare and create one new Review Draft; no post ID is preassigned | Capture exact Rakuten link/image evidence for all four products, including one exact THANKO variant, no more than 24 hours before `prepare`; any missing identity or image stops this article |
| Day 13 | Robot vacuum: post 30 moves from Draft to its final slug | Confirm the existing committed request, final slug, category, exact snapshot, and current product evidence |

Every status, slug, category, AT-003 update, and publication step in this table is a
human WordPress operation. The repository only prepares, records, or verifies the
closed artifacts allowed by the existing CLI.

## Jackery 500 New source resolution and recheck

The former Jackery 500 New conflict is resolved for the current comparison scope.
The 2026-08-31 manufacturer product page is the bound primary source for 512Wh,
500W rated output, and approximately 5.7kg. The earlier conflicting enclosure
dimensions are not part of the source claim, comparison table, product card, or
recommendation rationale. Do not restore those dimensions from an old snapshot,
search result, retailer copy, or a similarly named Jackery generation.

Before a fresh portable-power `prepare`, recapture the exact official URL and reopen
the source review if any of these conditions is true:

- the page redirects to another model or generation, or no longer identifies
  `500 New`;
- capacity, rated output, or weight differs from 512Wh, 500W, or approximately
  5.7kg anywhere in the current official page or its current manual;
- a newly published official dimension is proposed for use but conflicts with any
  other current Jackery primary source;
- a required locator no longer resolves, the immutable capture or statement hash
  changes, or the official capture is older than the 14-day article-fact limit;
- the manufacturer marks the model discontinued or changes the Japanese-market
  configuration used by the article.

Any triggered condition returns the article to blocked review. Update the source
packet and locator contract from current primary evidence, remove unresolved facts
from every decision path, generate a new prepared packet and snapshot, and obtain
fresh product evidence within its 24-hour limit. A previous human confirmation,
snapshot, source capture, or Rakuten capture must not be reused.

## Owner-private evidence and operation gates

Keep `.secrets/`, `.secrets/st1704-self-hosted-editorial-pilot/`, and every child
directory owner-only with mode `0700`; keep every evidence or gate JSON file at mode
`0600`. Do not commit these files. The runtime follows no symlink and rejects any
different ownership, mode, extra key, duplicate key, or noncanonical resource.

On `create-review-draft`, the runtime creates exactly one immutable request artifact
at `.secrets/st1704-self-hosted-editorial-pilot/immutable-review-draft-requests/<article_id>.<packet_sha256>.<request_sha256>.request.v1.json`.
Its schema is `RAOS_ST1704_OWNER_IMMUTABLE_REVIEW_DRAFT_REQUEST_V1`; its closed
document contains `schema`, `article_id`, `packet_sha256`, `request_sha256`, the exact
canonical `request`, and `integrity_sha256`. The request contains only the already
validated title, digest-bound draft slug, excerpt, content, status, fixed origin and
path, and closed publication snapshot. It contains no credential or provider secret.
The runtime writes it atomically without replacement and binds its exact filename and
file SHA-256 into the live journal. Never hand-edit, delete, rename, copy over, or
choose between request artifacts. A stale or different artifact blocks a new create;
recovery and verification require one live journal and follow only its exact filename
and full-byte hash, so an inert orphan can neither authorize nor redirect an action.

For every source reference required by the selected article, and for all three policy
sources, install these two fixed artifacts under
`.secrets/st1704-self-hosted-editorial-pilot/sources/`:

- `<source-ref>.v1.json`, with schema
  `RAOS_ST1704_OFFICIAL_SOURCE_CAPTURE_V1` and only `source_ref`, exact `final_url`,
  UTC `retrieved_at`, `http_status: 200`, `content_type`, `body_sha256`,
  `response_sha256`, and `locators`;
- `<source-ref>.body`, containing the captured response body bytes without rewriting.

Codex creates or refreshes these pairs through the separate closed source command,
run from the exact repository root and isolated from ambient Python and environment
configuration:

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  "$PWD/.venv/bin/python" -B -I -S -X pycache_prefix=/dev/null \
  scripts/st1704_official_source_capture.py capture-article \
  --article-id st1704-portable-power-station-guide
```

Before importing any RAOS runtime module or reading either tracked source document,
the command requires the exact `.venv/bin/python` 3.14.6 process, `-B -I -S`, safe
path, ignored environment and user site, and repository-root working directory. It
then byte-compares `runtime-manifest.v1.json` with the same path in the current
`HEAD` commit, requires every listed runtime file and the ST-1703 predecessor to be
byte-identical to their blobs in that same commit, and verifies the manifest's closed
file inventory before loading runtime modules plus registry/locator documents only
from those verified bytes. The Git anchor must report this exact repository root; terminal
prompts and partial-clone lazy object retrieval are disabled. Any mismatch returns only
`OFFICIAL_SOURCE_CAPTURE_RUNTIME_INVALID` and performs no DNS or HTTP operation.

The command accepts no URL, header, credential, output path, WordPress target, or
publication action. Run it in the repository's clean environment without proxy or
custom certificate variables. A single-source refresh may instead use
`capture-source --source-ref <tracked-ref>`. These are the only two subcommands; the
separate WordPress CLI exposes exactly five commands and independently enforces its
own committed-manifest/verified-byte runtime boundary described above.

`capture-article` commits each source independently and never treats a partial batch
as article readiness. For one source, the body and metadata files are each replaced
atomically, with metadata written last as the commit marker. A crash or concurrent
read between those replacements produces a closed hash mismatch rather than an
accepted mixed pair; rerunning the same allowlisted command repairs it. If a later
source fails, already committed sources remain safe current evidence, the remaining
sources stay unchanged, and `prepare` still requires the complete exact source set.
The command cannot publish or send a WordPress request.

Each locator contains only `claim_id`, `claim_statement_sha256`, and a nonempty
`exact_utf8_fragments` list. Each list item contains only `exact_utf8_fragment` and
`fragment_sha256`. Grouping several short fragments lets one claim bind separated
specification rows without copying or normalizing a long page range. The statement
hash must match the exact tracked claim statement (or the exact tracked policy-source
title), each distinct fragment must occur exactly once in the captured body, and the
claim set must exactly equal the registry's claims for that source.
The same short source fragment may support more than one claim locator; repetition
inside one claim is rejected. This avoids selecting a longer, less stable surrounding
range only to make the locator text different. `body_sha256` binds the raw body;
`response_sha256` binds the canonical JSON object containing the schema, source
reference, final URL, timestamp, HTTP status, content type, and body hash. Every
tracked source is HTML: its content type must be `text/html` and its body must be a
complete HTML document. The timestamp's date must be on or after the source's tracked
`retrieved_on` and, for article sources, the
article's tracked `facts_checked_on`. Those tracked dates are the original editorial
and locator-review audit baseline: they must not be in the future, but they are not
the recurring freshness authority. A new capture is accepted only when every tracked
statement hash and unique exact body fragment still matches; its truthful
`retrieved_at` must not be in the future and must be no more than 14 days old when
`prepare` runs. A redirect, missing claim, a duplicate fragment inside one claim, wrong
MIME/body shape, stale capture, or changed byte keeps the article blocked.

For each unique product, install all four fixed artifacts under
`.secrets/st1704-self-hosted-editorial-pilot/rakuten/`:

- `<product-id>.v1.json`, with schema
  `RAOS_ST1704_RAKUTEN_PRODUCT_EVIDENCE_V1`;
- `<product-id>.item-search-response.v1.json`, the exact Item Search response from the
  identity request without `affiliateId`;
- `<product-id>.affiliate-item-search-response.v1.json`, the exact response from the
  second request with the owner-managed `affiliateId`;
- `<product-id>.image`, the exact downloaded 128×128 image bytes.

The closed metadata fields are `schema`, `product_id`, `affiliate_ref`,
`media_asset_ref`, exact `item_code`, exact `item_name`, optional `jan`, `variant`,
direct item `source_url`, direct affiliate `destination_url`, exact `image_url`,
`width`, `height`, UTC `retrieved_at`, `request_fingerprint`, `response_sha256`,
`selected_result_sha256`, `affiliate_request_fingerprint`,
`affiliate_response_sha256`, `affiliate_selected_result_sha256`, `image_sha256`, and
`no_modification_policy`. The two request fingerprints bind the fixed Item Search
request shapes while excluding secret values; the two response hashes bind the exact
raw response files; and the two selected-result hashes bind the exact normal and
affiliate identities. Each response must contain one and only one matching item code.
The declared variant must be one of the registry's closed model codes; the returned
item name must contain the model and product-kind tokens and none of the forbidden
accessory or conflicting-generation tokens.
The image file's hash and decoded dimensions must match, and evidence must be no more
than 24 hours old. The policy contains only
`aspect_ratio_change_allowed`, `crop_allowed`, `modification_allowed`,
`text_overlay_allowed`, and `upscale_allowed`, all `false`. Product IDs and binding
references come from the tracked source/media registries; no field is chosen by a CLI
argument. Credentials and secret values are never written to any artifact.

The separate bounded capture command installs those four artifacts. Run it from the
exact repository root, substituting only one of the five closed article IDs:

```sh
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
  "$PWD/.venv/bin/python" -B -I -S -X pycache_prefix=/dev/null \
  scripts/st1704_rakuten_product_capture.py capture-article \
  --article-id st1703-first-suitcase-comparison
```

It first verifies `rakuten-capture-runtime-manifest.v1.json`, the current committed
HEAD, the approved base, and every capture runtime byte before reading credential
metadata or issuing DNS/HTTPS. Product discovery is bounded to the registry's model
variants and 30 results on page one. It then issues exact item-code requests without
and with `affiliateId`, followed by one exact provider-image request. Secret values
are excluded from fingerprints, results, logs, argv, environment, and all four
artifacts. Before persistence, every provider string and string-list member is checked
in normalized raw and single-percent-decoded form: the access key is forbidden
everywhere, while application and affiliate IDs are permitted only in validated
`itemUrl`/`affiliateUrl` fields. A private cross-process lock records the outbound
request boundary so direct
requests are paced at least 1.1 seconds apart across CLI invocations and are never
retried automatically. Do not retry `REQUEST_AMBIGUOUS` blindly; inspect provider availability
before a new owner-authorized run. The existing WordPress CLI remains limited to its
five documented commands.

After a fresh `prepare` succeeds, a human creates a separate one-operation gate at
`.secrets/st1704-self-hosted-editorial-pilot/owner-live-gates/<article-id>.<packet-sha256>.<command>.v1.json`.
Its exact schema is `RAOS_ST1704_OWNER_LIVE_GATE_V1`, authority is
`HUMAN_OWNER_ONE_OPERATION`, origin is `https://kurashinoshirube.com`, and the closed
fields are `schema`, `authority`, `origin`, `article_id`, `packet_sha256`,
`request_sha256`, and `command`. The command is exactly one of
`create-review-draft`, `recover-create-review-draft`,
`verify-carry-on-single-url`, or `verify-public`; each command
requires its own exact gate. For create, copy the packet and request hashes from that
fresh successful `prepare` result. For recovery or verification, copy the original
hashes from the immutable request and bound journal; do not run a new prepare to
replace them. Credentials remain in the existing ST-1703 owner-private credential
store and are never copied into these gate files.

Create first performs the owner-gate preflight and exact target/inventory reads. While
holding the owner-only journal lock, it then writes the immutable request artifact,
atomically records an `INTENT` that binds the artifact filename and SHA-256, performs
the sole draft POST, validates the exact response, and finally records `COMMITTED`.
An artifact without an `INTENT` is an inert orphan and cannot be used to create. If
the POST may have succeeded but the `COMMITTED` write did not, never resend create:
make a recovery gate with the original hashes and run only
`recover-create-review-draft`. Recovery loads the sole `INTENT`-bound artifact without
repreparing, records `RECOVERY_ATTEMPTED` before its bounded GET, and either commits
the one recovered draft or stops visibly. `RECOVERY_ATTEMPTED` is terminal and must
not be retried. Public verification similarly loads only the sole `COMMITTED`-bound
artifact. Current source-capture and Rakuten freshness remain mandatory for
prepare/create, but
recover and verify do not rebuild the confirmed request from current provider files.

## One-time human activation

1. The official WordPress.org 28.3 per-file checksum manifest and its SHA-256 are
   bound in `theme/yoast-seo-28.3.lock.json`. A human WordPress operator must run the
   recorded strict installed-file verification for `wordpress-seo` 28.3 and reject
   any missing, modified, or unexpected file. The locally calculated archive SHA-256
   is not a substitute for installed-file verification.
2. A human WordPress administrator installs and activates Yoast 28.3 only after that
   blocker is resolved, then disables its automatic updates, usage tracking, AI
   features, Semrush, Wincher, and additional
   Google integrations, and applies the closed sitemap/archive policy recorded by the
   theme contract. Site Kit is not changed.
   In `wpseo_social`, Open Graph and X output must both be enabled, the X card type
   must be `summary_large_image`, and the default social image must be the verified
   1600×900 theme asset with an empty attachment ID. These are persisted human
   settings, not values written by the theme.
3. A human WordPress administrator installs and activates the generated child-theme 1.5.0
   package only after reviewing its exact hash. No repository command activates
   either component.
4. Start a fresh WordPress request and require the Site Health test
   `RAOS Yoast 28.3設定` to report `good`. The theme only reads back the persisted
   human configuration; it does not rewrite Yoast options after the plugin has loaded.
   A missing or critical result blocks treating a review draft as release-ready and
   blocks every public action.

## Per-article review and publication

1. Select exactly one allowlisted `article_id` and run `prepare`. Preparation must fail
   if any source, affiliate link, image identity, dimensions, or hash is incomplete.
2. A credentialed human owner may run `create-review-draft`. The request is limited to
   `title`, `slug`, `excerpt`, `content`, `status: "draft"`, and the one closed
   `_raos_publication_snapshot_v1` meta value. If the response is ambiguous, use only
   `recover-create-review-draft`; do not retry creation blindly.
   The WordPress draft slug is exactly
   `raos-review-<public-slug>-<payload-sha256>`; the snapshot canonical and public
   slug remain unchanged. The snapshot also binds the exact prepared packet SHA-256.
   Confirm that the immutable request artifact and journal `INTENT` are written before
   the POST and that the validated outcome reaches `COMMITTED`.
3. Review the draft at 360, 768, and 1440 CSS pixels, at 200% zoom, with keyboard-only
   navigation and JavaScript unavailable. Confirm one H1, disclosure in the first
   view, the comparison table, every exact product image and alt, all primary-source
   links, related links, and the absence of fixed price, inventory, points, or
   first-hand claims.
4. Record the immutable snapshot hash. A human owner confirms that exact snapshot for
   that article. Any content or evidence change invalidates the confirmation.
5. Only after that confirmation, a human owner performs the public update or publish
   in WordPress. The repository CLI has no publish or schedule command. For the four
   new posts, first record the intended `暮らしの道具` category ID and current category
   state, then assign exactly that one category and remove `Uncategorized` or any other
   category without changing title, excerpt, content, or snapshot. Publish the exact
   Review Draft, preserve its post ID, and replace the temporary review slug with the
   snapshot public slug. For AT-003, confirm the existing post already has exactly that
   category; if not, the human makes and records a separate category-only correction
   before opening the Tools URL so the later pre-state binds the corrected taxonomy.
   Never publish the AT-003 clone: open the exact Tools URL from the CLI receipt. Its
   non-authoritative
   assertions are `review_draft_id`, `target_public_post_id`, `packet_sha256`,
   `request_sha256`, and `payload_sha256`; do not hand-edit them. Compare the displayed
   IDs and packet, request, and payload hashes with the journal and its exact bound
   request-artifact filename/hash. Independently review and record the server-derived
   pre-state and operation hashes (they are not journal fields), enter a specific
   10–300 character approval reason, and complete the current
   WordPress user's password reauthentication. The password is checked only for this
   step-up and is not persisted. Then use the single explicit update button. The POST
   writes a closed approval receipt with the approving WordPress user, UTC time,
   reason, and an exact old-value rollback artifact before mutation. The page copies
   only title, excerpt, content, and the closed snapshot to the existing post and
   leaves the Review Draft intact. Credential entry is a human-only gate and must not
   be delegated to browser automation.
6. Immediately run `verify-public` for a `COMMITTED` article and exact snapshot. For
   the terminal carry-on exception, run only `verify-carry-on-single-url`.
   Create its one-operation gate from the original immutable request/journal hashes;
   verification deliberately does not run a fresh prepare.
   Confirm the journal-bound post ID, one description, canonical, robots policy,
   OG/X set, sole RAOS JSON-LD graph, exact related-navigation state, the current
   article's exact homepage cluster/link/title with no unbound future article link,
   Yoast sitemap index/post/page maps, and that the WordPress core sitemap is not a
   second public owner. With the fixed Yoast SEO 28.3 profile, `/wp-sitemap.xml`
   must be the exact empty-body HTTP 301 delegation to the same-origin
   `/sitemap_index.xml` with `X-Redirect-By: Yoast SEO`; other redirect targets,
   statuses, owners, or response bodies fail closed. The command also derives the
   exact digest-bound Review URL
   from the journal-bound immutable request; an anonymous GET must return HTTP 404 with no
   `Location`, and an anonymous public posts REST lookup for that exact slug must be
   empty. Through the same existing owner gate and credential header, an exact-slug
   Draft REST read must return retained post ID 26 for AT-003 and bind its title,
   excerpt, content, snapshot, status, and slug to the fixed request. The other
   four article modes require zero Draft rows because their Review post becomes the
   clean published post. Every home-page `href` and every post/page sitemap URL must exclude
   raw or strictly percent-decoded `raos-review-*`; malformed, ambiguous, or
   double-encoded routes fail closed. The clean canonical must occur exactly once in the post sitemap
   and zero times in the page sitemap. A 404 body that contains the committed title,
   excerpt, content, snapshot JSON interior, payload SHA-256, RAOS article markers,
   high-signal shortened CTA fragments, or affiliate content fails closed, including
   meaningful partial or HTML-entity-encoded leakage after normalization. Each of
   those article fragments is drawn from visible text rather than HTML attributes;
   snapshot comparison excludes only windows or tokens wholly contained in the
   expected clean canonical URL. Each of
   the three Review-surface evidence digests binds its fixed path,
   actual status, content type, absent `Location`, relevant REST count headers, and
   body SHA-256 before joining `public_surface_sha256`. A failed check does not become
   Production evidence and grants no redirect, delete, or retry authority.
   For the carry-on exception only, use `verify-carry-on-single-url`; it reads the
   exact terminal `RECOVERY_ATTEMPTED` artifact and IDs 19/26 without writing or
   locking the journal. Its dedicated adapter evidence type keeps
   `formal_gate_eligible=false`, `public_surface_verified=false`,
   `strict_public_checks_passed=true`, and `PENDING_HUMAN_EXCEPTION`; the internal
   strict `PublicVerification` is not returned. Ordinary `verify-public` remains
   `COMMITTED`-only.
   On the final anonymous URL, also repeat the combined 360/768/1440 CSS-pixel,
   200%-zoom, keyboard-only, and JavaScript-disabled matrix. Require HTTP 200,
   self-canonical, `index, follow`, exactly one sitemap occurrence, and no Review URL
   on the home page or sitemap. Recheck every 128×128 product image and alt, exact
   product identity, Rakuten direct destination, `rel="sponsored nofollow"`, first-view
   disclosure, and absence of fixed price, inventory, points, unverified first-hand
   claims, or broken links. Description, canonical, OG/X, robots, and the sole RAOS
   JSON-LD graph each remain one system. The article's measurement `T0` begins only
   after this public matrix passes.
7. Related navigation is theme chrome outside `visible_content_sha256`. Publishing a
   paired target legitimately adds the allowlisted reciprocal link. Re-run
   `verify-public` for both ends of that pair after the target publication; no article
   copy or recommendation order changes as part of that transition. These later runs
   use each end's original `COMMITTED` artifact even when the 24-hour Rakuten evidence,
   14-day source evidence, or the shared C300 provider files have since been refreshed.

Use the order and offsets in `operations/publication-plan.v1.json`. The tracked
`operations/measurement-ledger.v1.json` is an immutable compatibility template; do
not record observations in it. Fourteen days after each public action, a human records
sanitized aggregates through the owner-private V2 interface documented at
`../affiliate-learning-v2/README.md`. Its fixed ledger is
`.secrets/st1704-owner-local-pilot/affiliate-learning-ledger.v2.json`. Finance and
conversion observations may inform human-review improvement proposals only. They may
never mutate article HTML, CTA copy, product selection, a publication snapshot, or the
recommendation order.

## Rollback

If a live defect is confirmed, a human operator performs these reversible actions in
order:

1. deactivate Yoast if duplicated or broken SEO output is the cause;
2. revert the ST-1704 integration commit, or restore the exact reviewed child-theme 1.1.1 package as the minimum containment floor;
   do not roll back to 1.0.2 while any Review Draft or unbound
   pilot slug exists;
3. keep every temporary Review post Draft with no redirect; restore the affected WordPress post revision when required.

If the AT-003 Tools action reports a preserved-invariant or rollback failure, stop;
do not remove or bypass its durable approval lock. Capture the public response and
compare the non-autoloaded receipt's exact old-value rollback artifact, then restore
the pre-action WordPress revision manually before any later attempt. A save hook from
the installed plugin set can mutate fields outside the four copied values, and
WordPress cannot provide a single transaction across all hook-driven writes, so a
concurrent-edit/save-hook staging test and the full WordPress integration test remain
mandatory. Any failure is evidence of an unresolved live condition, not permission to
delete the lock or retry automatically.

Do not delete database rows, media, posts, revisions, or settings as part of this
runbook. Record what was restored and retain the failed snapshot for audit.
