# Frozen owner handoff

Repository: /home/minami/.codex/worktrees/caed/rakuten on Ubuntu-22.04.
Use the supplied WSL PHP wrapper; a plain host PHP executable is not equivalent.

```bash
export PATH=/tmp/raos-reader-tools:/home/minami/.nvm/versions/node/v24.18.1/bin:$PATH
.venv/bin/python -B scripts/build_reader_measurement_v1.py --check
.venv/bin/python -B -m pytest -q tests/reader_measurement_v1 --override-ini addopts=
node tests/reader_measurement_v1/browser.mjs
.venv/bin/python -B tests/reader_measurement_v1/run_mysql.py
```

Observed results at handoff: seven pytest cases pass, including real Firefox UI;
scoped Ruff passes. The isolated MariaDB run accepts 1200 and rejects 400 of
1600 concurrently attempted events, and verifies actual raw/daily/rate SQL
transactions, rollback and retention. These are automated simulations, not real
reader validation, wp-admin human approval or live/public verification.

## Browser strategy

browser.mjs uses the installed Firefox binary
/home/minami/.cache/ms-playwright/firefox-1542/firefox/firefox.
RAOS_READER_FIREFOX can select another already installed binary.
RAOS_READER_TEST_PHP can select the explicit PHP wrapper.

Every request is intercepted at browser-context scope BEFORE navigation. The
context has service workers blocked and a closed loopback proxy
http://127.0.0.1:9 as an additional escape guard. No handler uses route.continue()
or route.fetch(). Navigation documents, owned JS/CSS, and event acceptance are
fulfilled locally; every other request is aborted. Browser offline=true is not
used because this Firefox build refuses navigation before route fulfillment.

The document uses the production-shaped origin solely inside this isolated
context. Footer/config come from the actual PHP plugin using runtime.php --footer
and in-memory WordPress doubles. Exact owned asset bytes are served at
/reader-simulation.js and /reader-simulation.css; this exercises consent,
real trusted clicks, all three payloads, Origin headers, no cookies/referrer,
revocation and failed intake without contacting that origin. The default
viewport is 1000x900. Main owns additional viewport / actual asset-tag/SRI and
full WordPress integration checks; use the same intercept-before-navigation
rule when adapting this harness.

Production-owned files:
- changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/assets/reader-measurement.js
- changes/reader-measurement-v1/wordpress-plugin/raos-reader-measurement/assets/reader-measurement.css

The PHP asset_tag() method generates deterministic production asset URLs using
full SHA256 ver= values and sha256 SRI/crossorigin=anonymous. Footer config must
precede the footer script (hook priority10 vs WordPress script printing at20).
Origin enforcement is not relaxed in the shipped plugin.

## Manual installation and local WordPress

The package is
/home/minami/.codex/worktrees/caed/rakuten/.secrets/wordpress-mcp/repo-plugin-artifacts/raos-reader-measurement-v1.zip.
No installation or real approval was performed. The packaged README's final
section gives exact manual upload, privacy-setting, enable and emergency-stop
wp-admin URLs. The artifact registry is main-owned; no migration exemption was
added. Activation supports normal nonce-protected wp-admin GET/bulk POST and
creates only the three dedicated tables while staying OFF.

For local OFF/integrity checks main may mount the owned plugin root read-only
into /var/www/html/wp-content/plugins/raos-reader-measurement. Local WordPress at
21924 intentionally cannot collect and does not emit the live config under a
localhost home_url. The supplied runtime.php harness simulates the approved
fixed origin, exact published posts and separate administrator only in test
doubles. It does not change local WordPress options or credentials.

If main adds a full-WordPress preview-only shim, keep its entire root outside
production plugin/theme packages and the approved file manifest. Mount only
into a disposable local fixture; bind all simulated home/site/public identities
to controlled fixture values; block outward egress and never send production
requests. Do not change the global MU directory or seed from this owner.
A preview shim and its results cannot be a production approval receipt.

The MariaDB harness uses cached pinned images, an ephemeral tmpfs data directory,
network=none for the DB, no published port, and PHP workers joining only that
container's loopback namespace. It stops its own container in finally. It never
uses production DB credentials or mounts a real database. The WordPress API and
dbDelta boundary are test doubles; the table DDL and SQL are the real plugin
implementation executed by MariaDB.

## Integration requirements

- Main copies theme-runtime-binding.v1.json through its theme owner and stamps
  the metadata digest. Predicate must be nonrecursive:
  kurashinoshirube_reader_runtime_profile() == reader-minimal-v1.
- The theme may require only the pinned maintenance PHP when plugin inactive.
  No inactive intake bootstrap. Approved disable/rollback retains one runner.
- Publish exact privacy block_markup bytes, select that privacy-policy page in
  wp_page_for_privacy_policy, and verify the ten production slugs/identities.
- A reliable hourly host cron remains required; WP-Cron registration alone
  cannot prove wall-clock retention with no traffic.
- Operator approval is still OFF and must be performed later by the real
  separate administrator. Old eight-event/GA4 switches are never enabled here.

make fast was attempted and stopped in another owner's current
tests/wordpress_seo_audit_v1/test_incremental_reader.py with three Ruff findings:
unused datetime, unused articles, and mixed fixture redefinition. No unrelated
files were edited. Main owns final aggregate verification and integration fixes.
