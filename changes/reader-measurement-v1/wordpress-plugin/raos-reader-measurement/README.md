# RAOS Reader Measurement 1.0.0

Optional first-party counts for the ten identity-verified published V3 articles.
Default OFF. No existing8, GA4, Site Kit, CookieYes, provider or MCP enable route.

- POST /wp-json/raos-reader/v1/events, production origin only.
- guide_navigation: event_name, article_id, target_article_id, journey_stage.
- decision_check_open: event_name, article_id, panel_id.
- official_reference_open: event_name, article_id, source_ref.
- Headers: Origin=https://kurashinoshirube.com; Sec-Fetch-Site=same-origin;
  Content-Type=application/json; X-RAOS-Reader-Consent=granted;
  X-RAOS-Reader-Contract and X-RAOS-Reader-Policy are current full SHA256 digests.
- JSON max 1024 bytes. No other keys, client dates, event/session/user IDs or URLs.
  The server adds only a JST calendar event_date. URLs are public mapping config
  only. Invalid requests return a generic bounded error; no raw read route.

## Reviewed activation and enable

The owner manages/deletes the data. Installation initializes only three dedicated
InnoDB tables: wp_raos_reader_raw_v1, wp_raos_reader_daily_v1,
wp_raos_reader_rate_v1 (WordPress prefix applies). Migration remains
MANUAL_REVIEW_REQUIRED on the existing manual review path. No init-time
installation, upgrade exemption, destructive uninstall or table removal.

After manual package review, a separate administrator activates through wp-admin.
Activation remains OFF. WordPress plugin activation can be a nonce-protected GET;
the plugin additionally requires the ordinary authenticated administrative context.
The active reviewed theme must expose kurashinoshirube_reader_runtime_profile()
returning reader-minimal-v1 only after matching this entire registered artifact.
It must provide the bounded inactive-plugin maintenance loader described below.

Publish the reviewed privacy block_markup exactly as privacy-policy post_content
and assign that page to WordPress wp_page_for_privacy_policy. The SHA256 must equal
config/reader-runtime.v1.json policy_sha256. All ten exact production slugs must
be published, password-free and verified by kurashinoshirube_public_article_identity.
The local-preview fallback is never sufficient. Integrity, cleanup and global
RAOS_OPERATOR_WRITES_ENABLED=true are required. RAOS_READER_MEASUREMENT_DISABLED=true
always stops intake. The plugin never changes either host constant.

Tools > Reader measurement: administrator reauthenticates using their current
password, checks the accountability statement, and enters the displayed contract,
policy and revision suffixes. The immutable revision includes code, allowlist,
assets and policy. Approval records only operator account, JST approval date,
method and digests in a separate option; it is never a visitor event.
MCP editor/deployer roles, capabilities and bound account IDs are excluded.
Changes invalidate approval. Emergency disable clears approval without deleting
existing records. Preparing this package or passing AI tests is not approval.

## Retention and maintenance

Raw records contain the event fields and server JST date only: no surrogate event
ID, exact timestamps, IP, User-Agent, referrer, URL or visitor/session identifiers.
Daily rows contain only those dimensions and count. One fixed site rate row holds
short-lived operational token-bucket state (1200 burst, 20/second, 100000/JST day);
it cannot identify a visitor. Raw insert, aggregate increment and budget reservation
share one transaction and row lock. Retransmission is not deduplicated by identity;
the client prevents duplicate listener handling and never retries or queues events.

The dedicated includes/reader-measurement-maintenance.php is self-contained and
defines raos_reader_measurement_cleanup() and raos_reader_measurement_cleanup_status().
An approved theme loader must verify this exact file digest from the reviewed
manifest before requiring it if the plugin is inactive. It loads no intake code.
It schedules hourly cleanup and does not cancel on deactivation. Approved
disable/rollback must keep either active plugin or reviewed theme maintenance.
Native removal or replacement without handoff makes maintenance unavailable;
do not report an absent runner as healthy. Reliable host execution of WordPress
cron at least hourly is a release prerequisite; WP-Cron traffic alone is not an
unconditional wall-clock retention guarantee.

Cleanup uses JST dates and deletes conservatively: raw dates at least 29 days
old and aggregate dates at least 89 days old, staying inside the maximum
30/90 days under daily maintenance. No exact event time is required. Health must
be successful on the current JST date, have a scheduled callback, and have valid
transactional tables. Stale/failed cleanup stops intake even after a previous
enable. Cleanup continues OFF. The admin can rerun it. Only aggregates are shown
in manage_options wp-admin, at 100 rows/page, never through MCP/REST.
Individual deletion is impossible because records contain no visitor identity.

## Public integration

raos_reader_measurement_status(): array:
schema RAOSReaderMeasurementStatusV1; plugin_active bool; plugin_version string;
collection_enabled bool; contract_sha256/policy_sha256 hex64 or null if unavailable;
approved_revision hex64 or null; cleanup {healthy bool,last_success_date YYYY-MM-DD
or null,last_error_code null|MAINTENANCE_UNAVAILABLE|CLEANUP_STALE|
STORAGE_UNAVAILABLE|CLEANUP_FAILED|CLEANUP_STATUS_UNAVAILABLE}.
raos_reader_measurement_enabled(): bool is fail-closed.

Only the explicit reader-minimal-v1 profile emits the integrity-bound external
JS/CSS and inert application/json config. Assets use full SHA256 ver= queries,
sha256 SRI, crossorigin=anonymous, fixed handles and no inline executable script.
Config schema RAOSReaderMeasurementClientV1 has exact keys origin, endpoint,
collection_enabled, contract_sha256, policy_sha256, policy_version (=policy digest),
article (null on home/hubs; otherwise the exact generated allowlist row).
The consent root is raos-reader-consent-settings. Equal allow/deny controls store
only {choice,policy_version} under raos_reader_consent_v1. No initial write,
backend UI-state request, session storage or persistent event queue.
Reopening, denying and revoking are local. Fetch omits credentials/referrer,
uses same-origin + keepalive, and cannot cancel navigation. Failed intake stops
further sends on that page. Freshly rendered OFF pages accurately separate site
state from the browser choice; cached pages cannot know a later operator change
until a bounded event is refused or the page reloads.

Panel mappings are existing reader-axes and reader-purchase-checks anchor
activations and native reader-evidence details opens. Source links require exact
article-bound official references. Guide navigation requires the real rendered
contextual link's target plus stage. Generic input/scroll/focus is never collected.

## Exact manual handoff (main/operator owned)

1. Generate/check this owner, then run --package. The private ZIP is
   .secrets/wordpress-mcp/repo-plugin-artifacts/raos-reader-measurement-v1.zip.
   Artifact ID: raos-reader-measurement-v1; slug: raos-reader-measurement;
   entrypoint: raos-reader-measurement/raos-reader-measurement.php.
   Main registers the manifest's package SHA256 in
   changes/wordpress-mcp-v1/contracts/repo-plugin-artifacts.v1.json through its
   existing owner scripts/build_wordpress_mcp_v1.py. Do not add an automatic
   migration exemption or reuse the old eight-event artifact approval.
2. After the real owner's package/migration review, the separate administrator
   uploads the exact ZIP at https://kurashinoshirube.com/wp-admin/plugin-install.php?tab=upload
   and activates it from wp-admin. This creates dedicated tables and stays OFF.
   Review the exact installed tree and retained scheduled callback.
3. Main installs the reviewed theme binding and publishes the exact approved
   privacy-policy content through existing publication approval. Assign that page
   under https://kurashinoshirube.com/wp-admin/options-privacy.php.
4. At https://kurashinoshirube.com/wp-admin/tools.php?page=raos-reader-measurement,
   verify cleanup health, reauthenticate, enter all three displayed hash suffixes,
   and explicitly approve. This approval must be made by the real administrator;
   development authorization and automated tests do not set the option.
5. Reader collection also needs an independent visitor choice. Deny/revoke works
   locally. The same admin page provides emergency disable and cleanup rerun.
   Approved rollback keeps the maintenance-only file and either active loader.

For local OFF/integrity inspection only, mount this plugin directory read-only
at /var/www/html/wp-content/plugins/raos-reader-measurement in an isolated
WordPress container. There is no localhost intake override or hidden ON switch.
Run the supplied PHP/Firefox fixtures for explicitly simulated ON behavior;
no production-shaped URL escapes their request interception/closed loopback proxy.
Run .venv/bin/python -B tests/reader_measurement_v1/run_mysql.py to create and stop
an ephemeral, network-isolated MariaDB fixture, with eight parallel PHP workers.
It accepts no host credentials, exposes no port and uses no production data.
