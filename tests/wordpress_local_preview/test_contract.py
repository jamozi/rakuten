from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/wordpress-local-preview-v1"
COMPOSE = SLICE / "compose.yaml"
WRAPPER = SLICE / "bin/wordpress_preview.sh"
FIXTURES = SLICE / "fixtures"
ARTICLES = FIXTURES / "articles"
POSTS = FIXTURES / "posts.json"
MU_PLUGIN = SLICE / "mu-plugins/raos-local-preview.php"
EDITORIAL_CSS = SLICE / "mu-plugins/raos-editorial-v2.css"
SEED = SLICE / "seed.php"

MARIADB_IMAGE = (
    "mariadb:11.8.3@sha256:"
    "ae6119716edac6998ae85508431b3d2e666530ddf4e94c61a10710caec9b0f71"
)
WORDPRESS_IMAGE = (
    "wordpress:7.1.0-php8.3-apache@sha256:"
    "8801a1239d7ba9fb340a5fc5ba0bf7f8d3652adbd64893e3fba7992ba618108e"
)
WP_CLI_IMAGE = (
    "wordpress:cli-2.12.0-php8.3@sha256:"
    "2b5e9d4d3e51909dca1aaa4732e9f5e5bf0377c2114dbd8ff39f060bff202586"
)
NGINX_IMAGE = (
    "nginx:1.29.1-alpine@sha256:"
    "42a516af16b852e33b7682d5ef8acbd5d13fe08fecadc7ed98605ba5e3b26ab8"
)


def _compose() -> dict[str, object]:
    value = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _posts_fixture() -> dict[str, object]:
    value = json.loads(POSTS.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_compose_is_digest_pinned_loopback_only_and_isolated() -> None:
    compose = _compose()
    services = compose["services"]
    assert isinstance(services, dict)
    database = services["database"]
    wordpress = services["wordpress"]
    gateway = services["gateway"]
    cli = services["cli"]
    assert database["image"] == MARIADB_IMAGE
    assert wordpress["image"] == WORDPRESS_IMAGE
    assert gateway["image"] == NGINX_IMAGE
    assert cli["image"] == WP_CLI_IMAGE
    assert wordpress.get("ports") is None
    assert gateway["ports"] == ["127.0.0.1:8888:8080"]
    assert database.get("ports") is None
    assert cli.get("ports") is None
    assert cli["profiles"] == ["cli"]
    assert compose["networks"] == {
        "preview_internal": {"driver": "bridge", "internal": True},
        "preview_loopback": {"driver": "bridge"},
    }
    assert wordpress["networks"] == ["preview_internal"]
    assert gateway["networks"] == ["preview_internal", "preview_loopback"]
    assert gateway["read_only"] is True
    assert gateway["cap_drop"] == ["ALL"]
    assert gateway["security_opt"] == ["no-new-privileges:true"]
    assert set(compose["volumes"]) == {"database_data", "wordpress_data"}


def test_theme_and_local_material_are_read_only_bind_mounts() -> None:
    services = _compose()["services"]
    for service_name in ("wordpress", "cli"):
        service = services[service_name]
        mounts = [item for item in service["volumes"] if isinstance(item, dict)]
        assert len(mounts) == 3
        assert all(
            item["type"] == "bind" and item["read_only"] is True for item in mounts
        )
        targets = {item["target"] for item in mounts}
        assert targets == {
            "/var/www/html/wp-content/themes/kurashinoshirube-child",
            "/var/www/html/wp-content/mu-plugins",
            "/var/www/raos-local-preview",
        }
        theme_mount = next(
            item for item in mounts if item["target"].endswith("kurashinoshirube-child")
        )
        assert theme_mount["source"].endswith(
            "/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
        )


def test_wordpress_runtime_is_explicitly_local_and_non_mutating() -> None:
    services = _compose()["services"]
    extra = services["wordpress"]["environment"]["WORDPRESS_CONFIG_EXTRA"]
    assert services["cli"]["environment"]["WORDPRESS_CONFIG_EXTRA"] == extra
    for marker in (
        "define('WP_HOME', 'http://127.0.0.1:8888');",
        "define('WP_ENVIRONMENT_TYPE', 'local');",
        "define('RAOS_LOCAL_PREVIEW', true);",
        "define('WP_HTTP_BLOCK_EXTERNAL', true);",
        "define('DISALLOW_FILE_EDIT', true);",
        "define('DISALLOW_FILE_MODS', true);",
        "define('AUTOMATIC_UPDATER_DISABLED', true);",
    ):
        assert marker in extra
    runtime_paths = (
        COMPOSE,
        WRAPPER,
        SEED,
        POSTS,
        MU_PLUGIN,
        EDITORIAL_CSS,
        *sorted(FIXTURES.rglob("*.html")),
    )
    runtime_material = "\n".join(
        path.read_text(encoding="utf-8") for path in runtime_paths
    )
    assert "https://kurashinoshirube.com" not in runtime_material
    assert "wordpressEditor" not in runtime_material
    assert "wordpressDeployment" not in runtime_material
    assert "RAOS_OPERATOR_WRITES_ENABLED" not in runtime_material


def test_synthetic_fixture_has_five_closed_local_articles() -> None:
    fixture = _posts_fixture()
    assert set(fixture) == {"schema", "seed_version", "posts"}
    assert fixture["schema"] == "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
    posts = fixture["posts"]
    assert isinstance(posts, list)
    assert len(posts) == 5
    assert {row["category"] for row in posts} == {"移動", "家事"}
    assert len({row["article_id"] for row in posts}) == 5
    assert len({row["slug"] for row in posts}) == 5
    assert len({row["content_file"] for row in posts}) == 5
    for row in posts:
        assert row["article_id"] == row["slug"]
        assert re.fullmatch(r"local-preview-[a-z0-9-]+", row["slug"])
        assert "http://" not in row["excerpt"]
        assert "https://" not in row["excerpt"]
        content_file = row["content_file"]
        assert isinstance(content_file, str)
        assert re.fullmatch(r"articles/[a-z0-9-]+\.html", content_file)
        article_path = FIXTURES / content_file
        assert article_path.parent == ARTICLES
        assert article_path.is_file()

        article = article_path.read_text(encoding="utf-8")
        assert re.search(r"<\s*h1\b", article, re.IGNORECASE) is None
        assert re.search(r"https?://", article, re.IGNORECASE) is None
        assert re.search(r"<\s*(?:script|style)\b", article, re.IGNORECASE) is None
        assert len(re.findall(r'class="raos-editorial-v2"', article)) == 1
        assert '<table class="comparison-table">' in article
        assert 'href="#local-only"' in article
        assert 'id="local-only"' in article
        assert "公開前" in article
        assert "再確認" in article
        assert "ローカル" in article


def test_editorial_mu_plugin_and_stylesheet_contract() -> None:
    plugin = MU_PLUGIN.read_text(encoding="utf-8")
    for marker in (
        "function raos_local_preview_is_editorial_article(): bool",
        "str_starts_with($slug, 'local-preview-')",
        "'raos-local-editorial-v2-page'",
        "add_filter('body_class', 'raos_local_preview_body_class')",
        "wp_enqueue_style(",
        "'raos-local-editorial-v2'",
        "content_url('mu-plugins/raos-editorial-v2.css')",
        "array('kurashinoshirube-editorial')",
        "add_action('wp_enqueue_scripts', 'raos_local_preview_editorial_stylesheet', 100)",
    ):
        assert marker in plugin

    stylesheet = EDITORIAL_CSS.read_text(encoding="utf-8")
    for marker in (
        ".raos-local-editorial-v2-page",
        ".raos-local-editorial-v2-page .raos-article-ruleline",
        ".raos-local-editorial-v2-page .raos-article-title-grid",
        ".raos-local-editorial-v2-page .raos-article-standfirst",
        ".raos-editorial-v2 .hero-photo",
        ".raos-editorial-v2 .decision-list",
        ".raos-editorial-v2 .comparison-section",
        ".raos-editorial-v2 .comparison-table",
        ".raos-editorial-v2 .product-profile",
        ".raos-editorial-v2 .rakuten-cta",
        ".raos-editorial-v2 .purchase-caution",
        ".raos-editorial-v2 .sources-section",
        "@media (max-width: 48rem)",
    ):
        assert marker in stylesheet


def test_local_guard_blocks_indexing_mail_http_and_updates() -> None:
    plugin = MU_PLUGIN.read_text(encoding="utf-8")
    for marker in (
        "wp_get_environment_type() !== 'local'",
        "add_filter('wp_robots'",
        "add_filter('pre_option_blog_public'",
        "add_filter('locale'",
        "add_filter('pre_wp_mail'",
        "add_filter('pre_http_request'",
        "X-Robots-Tag: noindex",
        "LOCAL WORDPRESS PREVIEW — 本番表示ではありません",
    ):
        assert marker in plugin


def test_seed_is_local_only_versioned_and_initialize_is_non_overwriting() -> None:
    seed = SEED.read_text(encoding="utf-8")
    assert "home_url('/') !== 'http://127.0.0.1:8888/'" in seed
    assert "array('initialize', 'sync')" in seed
    assert "raos_local_preview_seed_version" in seed
    assert "RAOS_WORDPRESS_PREVIEW_ALREADY_INITIALIZED" in seed
    assert "count($fixture['posts']) !== 5" in seed
    assert "update_option('blog_public', '0')" in seed


def test_wrapper_preserves_data_by_default_and_gates_reset() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    down = wrapper[wrapper.index("do_down()") : wrapper.index("do_reset()")]
    reset = wrapper[wrapper.index("do_reset()") : wrapper.index('case "${1:-}"')]
    assert "--volumes" not in down
    assert "compose down --remove-orphans" in down
    assert '[[ "${CONFIRM:-}" == YES ]]' in reset
    assert "compose down --volumes --remove-orphans" in reset
    assert "RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD=%s" in wrapper
    assert "set a password with make wordpress-preview-password" in wrapper
    assert "printf '%s\\n' \"$RAOS_WORDPRESS_PREVIEW_ADMIN_PASSWORD\"" in wrapper


def test_root_makefile_exposes_the_documented_interface() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    for target in (
        "wordpress-preview-up",
        "wordpress-preview-status",
        "wordpress-preview-sync",
        "wordpress-preview-password",
        "wordpress-preview-check",
        "wordpress-preview-down",
        "wordpress-preview-reset",
    ):
        assert f"{target}:" in makefile
    assert 'CONFIRM="$(CONFIRM)"' in makefile


def test_browser_audit_covers_home_and_five_articles_at_four_widths() -> None:
    audit = (SLICE / "browser/wordpress_local_preview_audit.function.js").read_text(
        encoding="utf-8"
    )
    check = (SLICE / "browser/check.sh").read_text(encoding="utf-8")
    assert "{ name: 'home', path: '/' }" in audit
    for route in (
        "/local-preview-carry-on-suitcase-under-100-seats/",
        "/local-preview-lightweight-carry-on-suitcase-under-3kg/",
        "/local-preview-front-open-carry-on-suitcase-with-stopper/",
        "/local-preview-roomba-mini-vs-switchbot-k11-pro/",
        "/local-preview-solota-vs-rakua-mini-plus/",
    ):
        assert f"path: '{route}'" in audit
    assert audit.count("article: true") == 5
    assert "const widths = [360, 390, 768, 1440];" in audit
    for marker in (
        "audit.h1Count !== 1",
        "audit.mainCount !== 1",
        "audit.missingAlt !== 0",
        "audit.unloadedImages !== 0",
        "audit.duplicateIds.length !== 0",
        "audit.brokenAriaReferences !== 0",
        "audit.scrollWidth > audit.clientWidth",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST",
        "document.querySelectorAll('.raos-editorial-v2').length",
        "document.querySelectorAll('.decision-list').length",
        "document.querySelectorAll('.comparison-section').length",
        "document.querySelectorAll('.purchase-caution').length",
        "document.querySelectorAll('.sources-section').length",
        "surface.article &&",
        "editorialRootCount !== 1",
        "fullPage: true",
    ):
        assert marker in audit
    assert "output/playwright/local-preview" in audit
    assert "output/playwright/local-preview" in check


def test_shell_entrypoints_parse() -> None:
    for path in (WRAPPER, SLICE / "browser/check.sh"):
        subprocess.run(
            ["/usr/bin/bash", "-n", str(path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
