from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest

from scripts import build_editorial_measurement_v1 as build


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/editorial-measurement-v1"
PLUGIN = SLICE / "wordpress-plugin/raos-editorial-measurement"
THEME = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)


def sources() -> str:
    return "\n".join(path.read_text() for path in sorted(PLUGIN.rglob("*.php")))


def test_owner_generator_and_runtime_manifest_are_current() -> None:
    assert build.main is not None
    result = subprocess.run(
        [sys.executable, "scripts/build_editorial_measurement_v1.py", "--check"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    manifest = json.loads((SLICE / "runtime-manifest.v1.json").read_text())
    assert manifest["artifact_id"] == "raos-editorial-measurement-v1"
    assert manifest["plugin_slug"] == "raos-editorial-measurement"
    assert manifest["plugin_version"] == "1.0.0"
    assert manifest["default_enabled"] is False
    assert manifest["host_gate"] == "RAOS_MEASUREMENT_ENABLED"
    assert re.fullmatch(r"[0-9a-f]{64}", manifest["package_sha256"])


def test_generated_allowlist_is_exactly_bound_to_editorial_v3() -> None:
    allowlist_path = PLUGIN / "config/measurement-allowlist.v1.json"
    allowlist = json.loads(allowlist_path.read_text())
    source_path = ROOT / allowlist["source"]["path"]
    source = json.loads(source_path.read_text())
    assert allowlist["schema"] == "RAOS_EDITORIAL_MEASUREMENT_ALLOWLIST_V1"
    assert allowlist["version"] == "1.0.0"
    assert allowlist["target_origin"] == "https://kurashinoshirube.com"
    assert allowlist["source"] == {
        "path": "changes/editorial-portfolio-v3/editorial-portfolio.v3.json",
        "schema": "RAOS_EDITORIAL_PORTFOLIO_V3",
        "version": "3.0.0",
        "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
    }
    assert len(allowlist["articles"]) == len(source["articles"]) == 10
    article_ids = {row["article_id"] for row in allowlist["articles"]}
    assert article_ids == {row["article_id"] for row in source["articles"]}
    assert all(set(row["related_article_ids"]) <= article_ids for row in allowlist["articles"])
    assert all(row["article_id"] not in row["related_article_ids"] for row in allowlist["articles"])
    for article in allowlist["articles"]:
        keys = {(row["product_id"], row["placement"]) for row in article["cta_bindings"]}
        assert len(keys) == len(article["cta_bindings"])
        assert all(row["placement"] in {"product_card", "final_summary"} for row in article["cta_bindings"])


def test_public_endpoint_is_same_origin_exact_schema_and_default_off() -> None:
    source = sources()
    main = (PLUGIN / "raos-editorial-measurement.php").read_text()
    assert main.count("register_rest_route(") == 2  # method declaration plus one route call
    assert "register_rest_route(\n            self::REST_NAMESPACE" in main
    assert "const REST_NAMESPACE = 'raos/v1';" in source
    assert "const REST_ROUTE = '/events';" in source
    assert "defined('RAOS_MEASUREMENT_ENABLED')" in source
    assert "true === RAOS_MEASUREMENT_ENABLED" in source
    assert "'same-origin' !== strtolower((string) $fetch_site)" in source
    assert "hash_equals(self::TARGET_ORIGIN, $origin)" in source
    assert "application\\/json" in source
    assert "charset=utf-8" in source
    assert "MAX_BODY_BYTES = 4096" in source
    assert "self::has_exact_keys(" in source
    assert "RAOS_MEASUREMENT_EVENT_SCHEMA_INVALID" in source
    for prohibited in (
        "raw_ip",
        "full_user_agent",
        "raw_search_query",
        "affiliate_url_query_secret",
    ):
        assert prohibited not in source
    assert "get_header('user-agent')" not in source.lower()
    assert "REMOTE_ADDR" not in source


def test_event_catalog_identity_and_cta_allowlists_are_closed() -> None:
    contract = (PLUGIN / "includes/class-raos-measurement-contract.php").read_text()
    for name in (
        "article_view",
        "qualified_decision_engagement",
        "affiliate_cta_impression",
        "affiliate_click",
        "product_card_view",
        "comparison_interaction",
        "internal_link_click",
        "disclosure_view",
    ):
        assert f"'{name}'" in contract
    assert "count($articles))" in contract
    assert "10 !== count($articles)" in contract
    assert "hash_equals($article['snapshot_id'], $event['snapshot_id'])" in contract
    assert "hash_equals($binding['cta_id'], $dimensions['cta_id'])" in contract
    assert "hash_equals($binding['offer_id'], $dimensions['offer_id'])" in contract
    assert "'visibility_threshold' === $key" in contract
    assert "! is_string($value)" in contract
    assert "RAOS_EDITORIAL_PORTFOLIO_V3" in contract
    assert "isset($cta_ids[$binding['cta_id']])" in contract
    assert "array('product_card', 'final_summary')" in re.sub(r"\s+", " ", contract)
    assert "visibility_threshold" in contract
    assert "0.5 !== $dimensions['visibility_threshold']" in contract


def test_storage_dedupes_and_retains_only_bounded_data() -> None:
    store = (PLUGIN / "includes/class-raos-measurement-store.php").read_text()
    assert "const RAW_RETENTION_DAYS = 7;" in store
    assert "const AGGREGATE_RETENTION_MONTHS = 13;" in store
    assert "PRIMARY KEY  (event_id)" in store
    assert "PRIMARY KEY  (metric_date, event_name, article_id, snapshot_id, dimensions_sha256)" in store
    assert "payload_sha256" in store
    assert "unset($identity_payload['received_at'])" in store
    assert "session_sha256" in store
    assert "hash('sha256', $event['anonymous_session_id'])" in store
    assert "ON DUPLICATE KEY UPDATE" in store
    assert "event_count = event_count + 1" in store
    assert "hash_equals($existing, $payload_sha256)" in store
    assert "'disposition' => 'DUPLICATE'" in store
    assert "raos_measurement_event_id_conflict" in store
    assert "raw_events_exposed" not in store
    assert "DROP TABLE" not in store.upper()
    assert "TRUNCATE TABLE" not in store.upper()


def test_storage_has_atomic_site_wide_short_and_daily_rate_budgets() -> None:
    store = (PLUGIN / "includes/class-raos-measurement-store.php").read_text()
    assert "const SESSION_RATE_PER_MINUTE = 120;" in store
    assert "const SITE_SHORT_BUCKET_CAPACITY = 1200;" in store
    assert "const SITE_SHORT_REFILL_PER_SECOND = 20;" in store
    assert "const SITE_DAILY_CAP = 100000;" in store
    assert "raos_measurement_rate_v1" in store
    assert "PRIMARY KEY  (bucket_key)" in store
    assert store.count("ON DUPLICATE KEY UPDATE bucket_key = VALUES(bucket_key)") == 2
    assert "ORDER BY bucket_key ASC FOR UPDATE" in store
    assert "accepted_count = accepted_count + 1" in store
    assert "accepted_count < %d" in store
    transaction = store.split("public static function record", 1)[1]
    assert transaction.index("START TRANSACTION") < transaction.index(
        "reserve_site_capacity($event['received_at'])"
    )
    assert transaction.index("reserve_site_capacity($event['received_at'])") < (
        transaction.index("SELECT COUNT(*)")
    )
    assert "session_sha256 = %s AND received_at_gmt >= %s FOR UPDATE" in transaction
    limiter = store.split("private static function reserve_site_capacity", 1)[1]
    assert "anonymous_session_id" not in limiter
    assert "session_sha256" not in limiter
    assert "REMOTE_ADDR" not in limiter
    assert "user-agent" not in limiter.lower()
    assert "return self::storage_error();" in limiter


@pytest.mark.skipif(shutil.which("php") is None, reason="PHP CLI unavailable")
def test_site_wide_rate_budget_resists_session_rotation_and_fails_closed() -> None:
    php = shutil.which("php")
    assert php is not None
    result = subprocess.run(
        [php, "tests/editorial_measurement_v1/measurement_store_rate_harness.php"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RAOS_MEASUREMENT_STORE_RATE_OK"


def test_aggregate_ability_is_read_only_and_never_exposes_raw_rows() -> None:
    main = (PLUGIN / "raos-editorial-measurement.php").read_text()
    assert "'raos-measurement/aggregate-report'" in main
    assert "'readOnlyHint' => true" in main
    assert "'destructiveHint' => false" in main
    assert "'idempotentHint' => true" in main
    assert "'openWorldHint' => false" in main
    assert "'raw_events_exposed' => false" in main
    assert "current_user_can('raos_codex_content_read')" in main
    ability = main.split("public function aggregate_report", 1)[1]
    assert "RAOS_Measurement_Store::aggregate_report" in ability
    assert "anonymous_session_id" not in ability
    assert "session_sha256" not in ability


def test_client_is_syntax_valid_consent_gated_and_navigation_independent() -> None:
    script_path = THEME / "assets/measurement.js"
    node = shutil.which("node")
    assert node is not None
    subprocess.run([node, "--check", script_path], check=True, cwd=ROOT)
    script = script_path.read_text()
    for marker in (
        "window.getCkyConsent",
        "window.wp_has_consent('statistics')",
        "analytics_storage === 'granted'",
        "cookieyes_consent_update",
        "wp_listen_for_consent_change",
        "IntersectionObserver",
        "intersectionRatio >= 0.5",
        "window.navigator.sendBeacon",
        "keepalive: true",
        "window.gtag('event'",
    ):
        assert marker in script
    assert "preventDefault" not in script
    assert "await " not in script
    assert "document.location" not in script
    assert "window.location =" not in script
    assert "href:" not in script
    assert "document.cookie" not in script
    assert "localStorage" not in script
    assert script.index("if (!consentGranted())") < script.index("window.sessionStorage.getItem(sessionKey)")


def test_client_behavior_denial_threshold_dedupe_click_and_revocation() -> None:
    node = shutil.which("node")
    assert node is not None
    result = subprocess.run(
        [
            node,
            "tests/editorial_measurement_v1/measurement_client_harness.mjs",
            str(THEME / "assets/measurement.js"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RAOS_MEASUREMENT_CLIENT_BEHAVIOR_OK"


def test_theme_enqueues_only_verified_asset_and_plugin_context() -> None:
    functions = (THEME / "functions.php").read_text()
    script = (THEME / "assets/measurement.js").read_bytes()
    digest = hashlib.sha256(script).hexdigest()
    assert f"KURASHINOSHIRUBE_MEASUREMENT_ASSET_SHA256 = '{digest}'" in functions
    block = functions.split("function kurashinoshirube_enqueue_measurement_client", 1)[1]
    assert "raos_editorial_measurement_enabled()" in block
    assert "raos_editorial_measurement_client_context" in block
    assert "kurashinoshirube_verified_asset_uri" in block
    verifier = functions.split(
        "function kurashinoshirube_verified_asset_uri", 1
    )[1].split("function kurashinoshirube_bound_post_snapshot", 1)[0]
    assert "assets/measurement\\.js" in verifier
    assert "'/wp-json/raos/v1/events'" in block
    assert "wp_add_inline_script(" in block
    assert "wp_dequeue_script('kurashinoshirube-measurement-v1')" in block
    assert 'data-raos-link-placement="article_body"' in functions
    assert 'data-raos-link-placement="related_navigation"' in functions
    assert "data-raos-to-article-id" in functions
    assert "home_cluster" not in (THEME / "assets/measurement.js").read_text()
    assert "home_cluster" not in sources()


def test_mcp_server_exposes_only_the_aggregate_measurement_ability() -> None:
    mcp_root = ROOT / "changes/wordpress-mcp-v1"
    plugin = (
        mcp_root
        / "wordpress-plugin/raos-codex-mcp-abilities/raos-codex-mcp-abilities.php"
    ).read_text()
    contract = json.loads((mcp_root / "contracts/wordpress-mcp.v1.json").read_text())
    config = (ROOT / ".codex/config.toml").read_text()
    assert "Version: 1.3.1" in plugin
    assert "define('RAOS_CODEX_MCP_VERSION', '1.3.1')" in plugin
    assert plugin.count("'raos-measurement/aggregate-report'") == 1
    content = (
        mcp_root
        / "wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-content.php"
    ).read_text()
    assert "'aggregate_ability_registered'" in content
    assert "'raw_event_tool_exposed' => false" in content
    assert "raos-measurement-aggregate-report" in contract["mcp_tools"]
    assert '"raos-measurement-aggregate-report"' in config
    assert "raos-measurement/raw" not in plugin
    assert "raos-measurement/event" not in plugin


def test_measurement_owner_declares_editorial_v3_builder_dependency() -> None:
    source = (ROOT / "scripts/build_editorial_measurement_v1.py").read_text()
    assert "from scripts import build_editorial_portfolio_v3" in source
    assert "SOURCE: Final = ROOT / editorial_v3_owner.OUTPUT_PATHS[0]" in source


@pytest.mark.skipif(shutil.which("php") is None, reason="PHP CLI unavailable")
def test_plugin_php_is_syntax_valid() -> None:
    for path in sorted(PLUGIN.rglob("*.php")):
        subprocess.run(["php", "-l", path], check=True, cwd=ROOT)
