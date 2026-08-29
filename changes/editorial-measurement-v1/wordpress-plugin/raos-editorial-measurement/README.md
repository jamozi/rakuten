# RAOS Editorial Measurement 1.0.0

Fixed, repository-tracked WordPress plugin for the ten-article Editorial V3
portfolio. It accepts a closed set of consented same-origin events and exposes
daily aggregates through one read-only WordPress Ability.

The collection route is `POST /wp-json/raos/v1/events`. It remains unavailable
unless the host defines `RAOS_MEASUREMENT_ENABLED` as the boolean `true`, the
WordPress home/site origins both exactly match `https://kurashinoshirube.com`,
and the browser supplies exact same-origin request headers. The theme also
requires completed CookieYes analytics consent, WP Consent API `statistics`
consent, and Site Kit `analytics_storage=granted` before it reads session
storage or emits anything.

The event body uses exact keys and the generated identity allowlist. Unknown
events, fields, article/snapshot pairs, CTA/offer/product pairs, placements,
URLs, query strings, email-like values, and active/sensitive text are refused.
Raw rows contain no IP address, user agent, referrer URL, outbound URL, order
identity, or provider credential. A session UUID is stored only as a SHA-256
digest. Raw rows expire after seven days; daily aggregates expire after 13
calendar months.

`raos-measurement/aggregate-report` returns aggregates only. It is intended for
the existing bounded `wordpressEditor` MCP transport and its exact read-only
editor role. No raw-event read surface exists.

Activation creates two plugin-owned tables and therefore requires the existing
manual plugin-review path. Activation never enables collection. Deactivation
stops cleanup scheduling without deleting measurements. Uninstall/delete code
is intentionally absent.

Build from the repository root:

```sh
.venv/bin/python scripts/build_editorial_measurement_v1.py --generate
.venv/bin/python scripts/build_editorial_measurement_v1.py --check
.venv/bin/python scripts/build_editorial_measurement_v1.py --package
```

The package is deterministic and is written with mode `0600` to the bounded
owner-private repo-artifact directory. Credentials and live data are never
packaged.
