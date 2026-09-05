# Local WordPress preview

This directory owns a persistent, non-production WordPress preview for the
`kurashinoshirube-child` theme. It exists to review article and home-page
appearance without reading from or writing to `kurashinoshirube.com`.

The preview uses digest-pinned WordPress 7.1.0, WP-CLI 2.12.0, MariaDB 11.8.3,
Nginx 1.29.1 images, and checksum-pinned Yoast SEO 28.3. A read-only,
unprivileged Nginx gateway is the only
service attached to the loopback bridge and binds only to a deterministic
worktree-specific `http://127.0.0.1:<port>` origin; WordPress and MariaDB remain
on their internal network. The Compose project name, named volumes, bootstrap
credentials, and port are isolated by repository-root identity, so another
checkout's preview is never reused or stopped.
WordPress and database state live in named Docker volumes, the tracked
child-theme source is mounted read-only, and ten local-only editorial drafts
are seeded. Before startup or synchronization, the tracked ten-article source
portfolio is materialized below `.secrets/wordpress-local-preview/`. Fresh,
exactly matched product evidence may supply an affiliate destination and a
local copy of its 128px product image; missing, ambiguous, or expired evidence
shows the visible non-image state `商品画像未確認・購入導線停止` and may retain a
clearly labelled manufacturer page link only as an incomplete development
fallback. It never reuses a neutral or article-level visual as a product image,
and this fallback is never a production candidate. Production still requires
37/37 verified product-card images and 74/74 verified affiliate CTAs, with zero
neutral images and zero manufacturer-link fallbacks. The browser never loads a
product image or script from an external origin. No live post, production
credential, analytics integration, or MCP publication tool is used by the
preview.

### Exact JAN evidence

Rakuten Item Search does not return JAN. For every owner-registered product
whose V2 binding has `official_jan`, capture therefore requires a separate
owner-private official-source receipt at
`.secrets/editorial-portfolio-v2/product-jan-evidence.v1.json` and one snapshot
at `.secrets/editorial-portfolio-v2/jan-evidence/<product_id>.snapshot.txt`.
The receipt and snapshots must be owner-only regular files with mode `0600`;
the JSON schema is `RAOS_EDITORIAL_PORTFOLIO_PRODUCT_JAN_EVIDENCE_V1` and must
contain the exact current portfolio hash, a single UTC `verified_at` no more
than 24 hours old, `owner_attested: true`, and exactly one row for every product
with an official JAN. Each row binds the product ID, representative model,
official JAN, official URL, source locator, exact snapshot filename and SHA-256,
and the same `verified_at`. The snapshot text must contain both the exact JAN
and representative model. Missing, extra, stale, mismatched, symlinked,
non-owner, or wrongly permissioned evidence fails before the Rakuten credential
is read. Provider evidence may omit JAN, but it can never replace or weaken this
separate exact official-source binding.

## Promotion rule

Article and fixed-page creation or updates, plus home-page, child-theme,
template, CSS, and presentation-affecting plugin changes, must be reviewed in
this local WordPress environment before any production submission or
publication proposal. The required sequence is:

1. Apply the draft or presentation change to the tracked fixture or child-theme
   source and start the preview with `make wordpress-preview-up`.
2. Run `make wordpress-preview-sync` when tracked article fixtures changed.
3. Run `make wordpress-preview-check` and visually review the affected local
   URL and screenshots.
4. Fix and repeat when any check fails. Do not submit the change to production
   while local review is missing or failing.
5. After local review passes, follow the repository's separate MCP, approval,
   proposal, precondition, and kill-switch requirements. A local pass is not
   production approval.

First propose the fixed MCP abilities plugin 1.3.1 package and stop for its
separate-admin approval/apply receipt. That exact receipt is required before the
measurement plugin can be proposed. Before either measurement or content
publication, materialize the checksum-pinned Yoast SEO 28.3 package, have a
human WordPress administrator install and activate that exact package, run the
bounded checksum verification, and separately propose, approve, and apply the
fixed Yoast option profile. The MCP `site-status` readback must then report the
exact installed, active, 28.3 version, selected option values, and settings
fingerprint; any missing or drifted value blocks both publication-batch claim
and content/theme apply. After the separately approved measurement
plugin apply receipt has been validated with
`measurement_plugin_proposal.py --content-ready`, run the full tracked batch
with that owner-private receipt. Production submission is deliberately limited
to the exact complete portfolio; article-only and other partial selections fail
before a lock, credential read, preview mutation, or remote call:

```sh
MEASUREMENT_PLUGIN_APPLY_RECEIPT="$PWD/.secrets/wordpress-mcp/publication-requests/plugin-applied.json" \
  make wordpress-production-request
```

`ARTICLES` must be `all`; any other value fails closed. Full mode fails before preview or remote access
unless the exact separate-admin plugin apply receipt is present under the
owner-private publication-request directory. The command always runs preview `up`, `sync`, and
`check` before it reads the editor credential or makes any live call. It then
uses only the exact project MCP editor endpoint to reuse an identical draft,
CAS-update a draft previously written by this workflow, or create a missing
draft. Existing published targets are reused only after their exact post ID,
slug, status, revision, modified time, and content hash are captured in the
owner-private baseline receipt. An unknown difference or duplicate slug stops
the request.

After draft readback, the command creates idempotent content proposals and,
when the exact tracked and deployed child-theme tree hashes differ, an
idempotent theme proposal through the fixed `wordpressDeployment` MCP bridge.
Open the printed wp-admin review URL, select the card whose token suffix and
manifest-hash suffix match the printed values, and use the single batch
approval. Keep the command running: it waits in the foreground and
automatically applies the approved theme first and the selected articles
second, then performs exact production readback. It never approves a proposal,
changes a host gate, accepts a URL, or bypasses the global kill switch.

Owner-private resumable receipts and the single-process lock are stored with
mode `0600` below `.secrets/wordpress-mcp/publication-requests/`; that directory
is mode `0700`. Re-running the same selection recovers response loss with the
persisted idempotency keys and operation IDs. Do not edit these receipts.

## Prerequisite

Install Docker Desktop for Windows, accept its terms, and enable WSL integration
for the distribution that contains the current repository checkout. Verify from
that checkout in WSL:

```sh
docker version
docker compose version
```

Docker Desktop installation and terms acceptance are intentionally outside the
repository workflow. The offline contract tests can run before Docker exists.

## Daily workflow

Run all commands from the repository root:

```sh
make wordpress-preview-up
make wordpress-preview-status
make wordpress-preview-check
make wordpress-preview-down
```

`wordpress-preview-up` derives an isolated Compose project and unprivileged
loopback port from the exact repository-root path, refuses a foreign container
already bound to that port, creates owner-private random bootstrap credentials under
`.secrets/wordpress-local-preview/`, verifies the pinned official Yoast 28.3
archive and checksum manifest, materializes the plugin below the owner-private
preview directory, mounts that exact plugin tree read-only, starts WordPress and
MariaDB, activates Yoast 28.3 and the tracked child theme, refreshes the
owner-private materialized fixture, and seeds it only on first initialization.
Synchronization verifies the active Yoast version and the exact persisted
`wpseo` / `wpseo_social` profile before succeeding. It does not print any password. The command
prints the exact origin for this checkout. An operator may select a different
free loopback port with `RAOS_WORDPRESS_PREVIEW_PORT`; the value is propagated
to Compose, WordPress, seed validation, and the browser audit. With
`PREVIEW_ORIGIN` standing for that printed origin, the local preview URLs are:

- home: `${PREVIEW_ORIGIN}/`
- article 1: `${PREVIEW_ORIGIN}/local-preview-carry-on-suitcase-comparison/`
- article 2: `${PREVIEW_ORIGIN}/local-preview-portable-power-station-guide/`
- article 3: `${PREVIEW_ORIGIN}/local-preview-anker-solix-c300-c800-c1000-differences/`
- article 4: `${PREVIEW_ORIGIN}/local-preview-countertop-dishwasher-for-small-households/`
- article 5: `${PREVIEW_ORIGIN}/local-preview-compact-robot-vacuum-shortlist/`
- article 6: `${PREVIEW_ORIGIN}/local-preview-carry-on-suitcase-under-100-seats/`
- article 7: `${PREVIEW_ORIGIN}/local-preview-lightweight-carry-on-suitcase-under-3kg/`
- article 8: `${PREVIEW_ORIGIN}/local-preview-front-open-carry-on-suitcase-with-stopper/`
- article 9: `${PREVIEW_ORIGIN}/local-preview-roomba-mini-vs-switchbot-k11-pro/`
- article 10: `${PREVIEW_ORIGIN}/local-preview-solota-vs-rakua-mini-plus/`

Edit the tracked child theme on the host and refresh the browser. The container
cannot edit that mount. WordPress database changes made while experimenting are
preserved by `wordpress-preview-down` and the next `wordpress-preview-up`.

To use wp-admin, set a local password without placing it in arguments, files, or
logs:

```sh
make wordpress-preview-password
```

The command requires an interactive terminal and prompts through WP-CLI. The
login user is `raos-local-admin`.

The seed rejects any title, excerpt, or article body that would be changed by
the same `wp_strip_all_tags` / `wp_kses_post` checks used by the production MCP
writer. This validation runs during the mandatory sync before production is
contacted.

To overwrite the ten preview posts and three fixed pages with a newly
materialized fixture, run:

```sh
make wordpress-preview-sync
```

Use this only after deciding that any database-only content experiments may be
discarded. Durable article or presentation changes belong in the tracked
fixture or theme source.

## Browser evidence

`make wordpress-preview-check` audits the home page, all ten editorial
drafts, the three fixed policy pages, true-empty and whitespace-only search,
populated and zero-result search, an encoded hostile query, a second result
page with its query preserved, all three category archives, the date and local
author archives, and the 404 template at widths 360, 390, 768, and 1440 pixels.
The generated route contract records tag and custom-post-type archives as
`NOT_APPLICABLE` with closed reason codes because the seed exposes neither; a
missing applicable archive cannot be silently reclassified. The audit fails on HTTP errors,
console/page errors, external requests, horizontal overflow, missing image
alternatives, duplicate IDs, broken ARIA references, missing Japanese language
metadata, incorrect H1/main counts, out-of-bounds H1, Cookie-settings, or CTA
boxes, or a missing Editorial V2 article module. It also fails if the anonymous
browser acquires any Cookie (including HttpOnly), local/session storage entry,
IndexedDB database, Cache Storage, or Service Worker registration. In addition
to the 104 viewport screenshots, it captures 26 text-resize screenshots after
raising the root font size to 200% and rejects horizontal overflow, clipped
text, or off-screen controls. These 130 files are ignored build artifacts under
`output/playwright/local-preview/`.

Search and archive checks bind the expected Japanese text, response status,
absence of a canonical on these intentionally non-canonical routes, escaped
hostile-query rendering, and pagination continuity. The local MU plugin forces
every route to `noindex, nofollow, noarchive, nosnippet`; the evidence therefore
records the `LOCAL_PREVIEW` profile and `production_robots_evidence: false`.
Production expectations (`noindex, follow` for search/archive and `noindex,
nofollow` for 404) remain a separate contract and are not claimed as observed
by a local pass.

Every article must expose exactly one visible monetization-status disclosure.
Nine affiliate articles require the standard advertising disclosure before the
first purchase CTA in both DOM and visual order, plus the comparison-policy link
and native `details`/`summary` operation with Enter and Space at 390px. The A10
lifecycle-status route instead requires the exact `購入リンクなし` disclosure,
has no `details`, product card, or CTA, and rejects either disclosure form on the
wrong route. The audit scrolls either form into view and rejects clipped,
off-screen, or obscured placement. All links are parsed from their actual DOM attributes: arbitrary or
active URL schemes and non-local plain HTTP destinations are rejected,
affiliate destinations require `sponsored nofollow`, and every `_blank` link
requires `noopener noreferrer`. Forbidden Product, Offer, Review,
AggregateRating, and FAQPage types are found recursively in JSON-LD rather than
only at the graph root.

The browser records request method, resource type, and origin class as counts
only; it never records request values or Cookie contents. Only GET/HEAD for the
closed document, stylesheet, script, image, and font resource types are
accepted, so POST and beacon traffic fail even when it does not use the known
measurement endpoint. At 390px and 1440px the audit exercises forward and
reverse keyboard tab order, verifies a visible unobscured focus indicator, and
emulates reduced motion to confirm computed animation, transition, and smooth
scroll behavior are disabled.

Main-document responses must include `X-Content-Type-Options: nosniff`,
`Referrer-Policy: no-referrer`, the closed local `Permissions-Policy`, and
`X-Frame-Options: DENY`. A Content Security Policy is deliberately not claimed
by this local contract: WordPress currently owns inline bootstrap markup, while
the public CSP belongs to the production server or edge. Verify the deployed
header separately before publication; a local pass is not evidence that a
production CSP exists.

The mobile Lighthouse gate invalidates all previous reports and its summary
before each run. It captures three samples for the home page and a representative
article, then writes only a median-based summary bound to a UTC capture time,
the current theme source fingerprint and runtime revision, navigation and route
inventory hashes, browser-audit hash, and the hash and fetch time of every
Lighthouse report. Changed inputs, mismatched fingerprints, stale timestamps,
or a missing report fail closed; an older `summary.json` can never satisfy a new
run.

The preview deliberately keeps `blog_public=0`, while installing and activating
only the checksum-pinned Yoast SEO 28.3 tree described above. The seed writes the
fixed local option profile, and both synchronization and the theme's read-only
configuration gate verify the active version and selected persisted options.
Materialization, activation, or option drift fails closed. Production
`robots.txt` and the
exact sitemap URL union are checked only by the bounded, anonymous
`scripts/raos_wordpress_seo_audit.py`; the local browser gate instead proves
that every closed core URL has exactly one self canonical, one non-empty meta
description, a complete self-bound Open Graph/Twitter record, and the
role-specific RAOS JSON-LD graph without commercial review types. A local pass
does not claim production sitemap or robots evidence.

## Existing-row restoration rehearsal

This is a separate `local-restore-rehearsal` workflow, not a successful
`verified-incremental` preview or permission to publish. The pure preparer
replays the captured MCP content hashes and public date/taxonomy evidence for
exactly ten articles, three policy pages, and the saved `home` page. It does
not substitute revised draft text, remove old commerce, or rewrite body URLs.
An empty saved home body is represented explicitly without an empty private
file. Raw inputs and generated bodies stay under the fixed owner checkout.

```bash
.venv/bin/python -B scripts/raos_wordpress_local_restore.py prepare \
  --snapshot-name live-SNAPSHOT_SHA256.v1.json
.venv/bin/python -B scripts/raos_wordpress_local_restore.py check-inputs \
  --preparation-sha256 PREPARATION_SHA256
```

Preparation writes only
`/home/minami/rakuten/.secrets/wordpress-mcp/local-restore-PREPARATION_SHA256/`:
`restoration-seed.v1.json`, nonempty `content/*.html`, and finally the hash-bound
`preparation-binding.v1.json`. It does not start Docker or change WordPress.

Only an explicit local restoration run uses the dedicated script:

```bash
changes/wordpress-local-preview-v1/bin/wordpress_preview.sh restore PREPARATION_SHA256
```

This command does not initialize or activate themes/plugins. It requires the
existing isolated local environment and all fourteen existing local rows,
including `home`; missing rows are rejected, not created. Before any article
update it validates every body, date, target, and hash. The original title,
excerpt, body, publication/modified dates, and category/tag semantics are
restored, then checked against a private stored-field readback. Local IDs and
the complete post/page ID inventory must stay unchanged. Front-page settings,
theme/plugin selection, and site options are not modified. Production IDs,
revision history, authors, media metadata, post metadata, and visual design are
not claimed as restored.

The command writes `restoration-readback.v1.json` and runs the pure verifier to
write `restoration-receipt.v1.json`. Both remain owner-private and explicitly
carry `publication_authority: false`; the receipt also carries
`incremental_preview_pass: false`. A failed or interrupted run has no success
receipt for its new readback. The receipt certifies only exact stored fields,
not a visual audit, source freshness, affiliate evidence, or production writes.
After preflight and before a rerun changes stored fields, any previous readback
and receipt are moved to content-addressed `previous-*` private filenames.
They remain recoverable but cannot be mistaken for the current attempt.

## Reset and boundaries

Ordinary shutdown preserves both named volumes. A full reset is deliberately
confirmation-gated and removes only the Compose project's local WordPress and
MariaDB volumes:

```sh
make wordpress-preview-reset CONFIRM=YES
```

The local must-use plugin adds a visible non-production banner, sends
`X-Robots-Tag: noindex`, the four response hardening headers audited above,
keeps `blog_public=0`, blocks mail and WordPress HTTP requests, disables file
modification and automatic updates, and never ships in the child-theme package.
This environment is not staging, release, or Production evidence.
