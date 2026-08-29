# Local WordPress preview

This directory owns a persistent, non-production WordPress preview for the
`kurashinoshirube-child` theme. It exists to review article and home-page
appearance without reading from or writing to `kurashinoshirube.com`.

The preview uses digest-pinned WordPress 7.1.0, WP-CLI 2.12.0, MariaDB 11.8.3,
and Nginx 1.29.1 images. A read-only, unprivileged Nginx gateway is the only
service attached to the loopback bridge and binds only to
`http://127.0.0.1:8888`; WordPress and MariaDB remain on their internal network.
WordPress and database state live in named Docker volumes, the tracked
child-theme source is mounted read-only, and five local-only editorial drafts
are seeded. The drafts use a research brief dated 2026-08-29 and remain marked
for primary-source rechecking before any publication workflow. No live post,
production credential, affiliate destination, analytics integration, MCP
publication tool, or external image is loaded.

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

## Prerequisite

Install Docker Desktop for Windows, accept its terms, and enable WSL integration
for the distribution containing `/home/minami/rakuten`. Verify from WSL:

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

`wordpress-preview-up` creates owner-private random bootstrap credentials under
`.secrets/wordpress-local-preview/`, starts WordPress and MariaDB, activates the
tracked child theme, and seeds the fixture only on first initialization. It does
not print any password. The public preview URLs are:

- home: `http://127.0.0.1:8888/`
- article 1: `http://127.0.0.1:8888/local-preview-carry-on-suitcase-under-100-seats/`
- article 2: `http://127.0.0.1:8888/local-preview-lightweight-carry-on-suitcase-under-3kg/`
- article 3: `http://127.0.0.1:8888/local-preview-front-open-carry-on-suitcase-with-stopper/`
- article 4: `http://127.0.0.1:8888/local-preview-roomba-mini-vs-switchbot-k11-pro/`
- article 5: `http://127.0.0.1:8888/local-preview-solota-vs-rakua-mini-plus/`

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

To overwrite the five preview posts and two fixed pages with the tracked
fixture, run:

```sh
make wordpress-preview-sync
```

Use this only after deciding that any database-only content experiments may be
discarded. Durable article or presentation changes belong in the tracked
fixture or theme source.

## Browser evidence

`make wordpress-preview-check` audits the home page and all five editorial
drafts at widths 360, 390, 768, and 1440 pixels. It fails on HTTP errors,
console/page errors, external requests, horizontal overflow, missing image
alternatives, duplicate IDs, broken ARIA references, missing Japanese language
metadata, incorrect H1/main counts, or a missing Editorial V2 article module.
The 24 screenshots are ignored build artifacts under
`output/playwright/local-preview/`.

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
