# Local WordPress preview

This directory owns a persistent, non-production WordPress preview for the
`kurashinoshirube-child` theme. It exists to review article and home-page
appearance without reading from or writing to `kurashinoshirube.com`.

The preview uses digest-pinned WordPress 7.1.0, WP-CLI 2.12.0, MariaDB 11.8.3,
and Nginx 1.29.1 images. A read-only, unprivileged Nginx gateway is the only
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
falls back to the manufacturer page and the tracked neutral image. The browser
never loads a product image or script from an external origin. No live post,
production credential, analytics integration, or MCP publication tool is used
by the preview.

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

First propose the fixed MCP abilities plugin 1.3 package and stop for its
separate-admin approval/apply receipt. That exact receipt is required before the
measurement plugin can be proposed. After the separately approved measurement
plugin apply receipt has been validated with
`measurement_plugin_proposal.py --content-ready`, run the full tracked batch
with that owner-private receipt. Narrow historical article-only requests remain
available without the plugin gate:

```sh
MEASUREMENT_PLUGIN_APPLY_RECEIPT="$PWD/.secrets/wordpress-mcp/publication-requests/plugin-applied.json" \
  make wordpress-production-request
make wordpress-production-request ARTICLES=roomba-mini-vs-switchbot-k11-pro
make wordpress-production-request ARTICLES=carry-on-suitcase-under-100-seats,solota-vs-rakua-mini-plus
```

`ARTICLES` defaults to `all`; that mode fails before preview or remote access
unless the exact separate-admin plugin apply receipt is present under the
owner-private publication-request directory. Otherwise `ARTICLES` accepts an exact,
comma-separated set of production slugs registered in
`production-mapping.v1.json`. The command always runs preview `up`, `sync`, and
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
`.secrets/wordpress-local-preview/`, starts WordPress and MariaDB, activates the
tracked child theme, refreshes the owner-private materialized fixture, and seeds
it only on first initialization. It does not print any password. The command
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
drafts, and the three fixed policy pages at widths 360, 390, 768, and 1440
pixels. It fails on HTTP errors,
console/page errors, external requests, horizontal overflow, missing image
alternatives, duplicate IDs, broken ARIA references, missing Japanese language
metadata, incorrect H1/main counts, out-of-bounds H1, Cookie-settings, or CTA
boxes, or a missing Editorial V2 article module. The 56 screenshots are ignored
build artifacts under `output/playwright/local-preview/`.

## Reset and boundaries

Ordinary shutdown preserves both named volumes. A full reset is deliberately
confirmation-gated and removes only the Compose project's local WordPress and
MariaDB volumes:

```sh
make wordpress-preview-reset CONFIRM=YES
```

The local must-use plugin adds a visible non-production banner, sends
`X-Robots-Tag: noindex`, keeps `blog_public=0`, blocks mail and WordPress HTTP
requests, disables file modification and automatic updates, and never ships in
the child-theme package. This environment is not staging, release, or
Production evidence.
