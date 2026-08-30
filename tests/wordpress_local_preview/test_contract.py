from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

import yaml

from scripts import build_editorial_v3_theme_navigation as audit_inventory_builder

ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/wordpress-local-preview-v1"
COMPOSE = SLICE / "compose.yaml"
WRAPPER = SLICE / "bin/wordpress_preview.sh"
GATEWAY = SLICE / "gateway/nginx.conf"
FIXTURES = SLICE / "fixtures"
ARTICLES = FIXTURES / "articles"
POSTS = FIXTURES / "posts.json"
PAGES = FIXTURES / "pages.json"
PRODUCTION_MAPPING = SLICE / "production-mapping.v1.json"
MU_PLUGIN = SLICE / "mu-plugins/raos-local-preview.php"
EDITORIAL_CSS = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/editorial-v2.css"
)
SEED = SLICE / "seed.php"
AUDIT_INVENTORY = (
    ROOT / "changes/editorial-portfolio-v3/generated/wordpress-audit-inventory.v3.json"
)

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

REVIEWED_SOURCE_HOSTS = {
    "developers.rakuten.com",
    "jp.ecoflow.com",
    "panasonic.jp",
    "store.ace.jp",
    "store.irobot-jp.com",
    "store.shopping.yahoo.co.jp",
    "shop.innovator.co.jp",
    "www.americantourister.jp",
    "www.ana.co.jp",
    "www.ankerjapan.com",
    "www.bagworld.co.jp",
    "www.bermas.co.jp",
    "www.bluetti.jp",
    "www.jackery.jp",
    "www.jal.co.jp",
    "www.proteca.jp",
    "www.samsonite.co.jp",
    "www.siroca.co.jp",
    "www.switchbot.jp",
    "www.thanko.jp",
}


def _html_attributes(tag: str) -> dict[str, str]:
    return {
        name.casefold(): value
        for name, _quote, value in re.findall(
            r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", tag, re.DOTALL
        )
    }


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
    assert gateway["ports"] == [
        "127.0.0.1:${RAOS_WORDPRESS_PREVIEW_PORT:?preview port is required}:8080"
    ]
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
        assert len(mounts) == 6
        assert all(
            item["type"] == "bind" and item["read_only"] is True for item in mounts
        )
        targets = {item["target"] for item in mounts}
        assert targets == {
            "/var/www/html/wp-content/themes/kurashinoshirube-child",
            "/var/www/html/wp-content/mu-plugins",
            "/var/www/html/wp-content/plugins/raos-editorial-measurement",
            "/var/www/raos-local-preview",
            "/var/www/raos-local-preview/fixtures/articles",
            "/var/www/raos-local-preview/fixtures/posts.json",
        }
        theme_mount = next(
            item for item in mounts if item["target"].endswith("kurashinoshirube-child")
        )
        assert theme_mount["source"].endswith(
            "/changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
        )
        measurement_mount = next(
            item
            for item in mounts
            if item["target"].endswith("plugins/raos-editorial-measurement")
        )
        assert measurement_mount["source"].endswith(
            "/changes/editorial-measurement-v1/wordpress-plugin/raos-editorial-measurement"
        )
        fixture_mount = next(
            item
            for item in mounts
            if item["target"] == "/var/www/raos-local-preview/fixtures/articles"
        )
        assert fixture_mount["source"] == (
            "${RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_ROOT:"
            "?materialized article fixture root is required}"
        )
        posts_mount = next(
            item
            for item in mounts
            if item["target"] == "/var/www/raos-local-preview/fixtures/posts.json"
        )
        assert posts_mount["source"] == (
            "${RAOS_WORDPRESS_PREVIEW_POST_FIXTURE:"
            "?materialized post fixture is required}"
        )

    gateway_mounts = [
        item for item in services["gateway"]["volumes"] if isinstance(item, dict)
    ]
    product_media_mount = next(
        item for item in gateway_mounts if item["target"] == "/srv/raos-product-media"
    )
    assert product_media_mount == {
        "type": "bind",
        "source": (
            "${RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT:"
            "?product media root is required}"
        ),
        "target": "/srv/raos-product-media",
        "read_only": True,
    }


def test_wordpress_runtime_is_explicitly_local_and_non_mutating() -> None:
    services = _compose()["services"]
    extra = services["wordpress"]["environment"]["WORDPRESS_CONFIG_EXTRA"]
    assert services["cli"]["environment"]["WORDPRESS_CONFIG_EXTRA"] == extra
    for marker in (
        "define('WP_HOME', '${RAOS_WORDPRESS_PREVIEW_ORIGIN:?preview origin is required}');",
        "define('RAOS_WORDPRESS_PREVIEW_ORIGIN', '${RAOS_WORDPRESS_PREVIEW_ORIGIN:?preview origin is required}');",
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
        PAGES,
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


def test_synthetic_fixture_has_ten_closed_local_articles() -> None:
    fixture = _posts_fixture()
    assert set(fixture) == {"schema", "seed_version", "posts"}
    assert fixture["schema"] == "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
    posts = fixture["posts"]
    assert isinstance(posts, list)
    assert len(posts) == 10
    assert {row["category"] for row in posts} == {"移動", "家事", "備え"}
    assert len({row["article_id"] for row in posts}) == 10
    assert len({row["slug"] for row in posts}) == 10
    assert len({row["content_file"] for row in posts}) == 10
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
        assert "http://" not in article.lower()
        assert re.search(r"<\s*(?:script|style)\b", article, re.IGNORECASE) is None
        assert len(re.findall(r'class="raos-editorial-v2"', article)) == 1
        assert '<table class="comparison-table">' in article
        urls = re.findall(r'href="(https://[^"<>]+)"', article)
        assert urls
        assert all(urlparse(url).hostname in REVIEWED_SOURCE_HOSTS for url in urls)
        external_anchors = re.findall(
            r'<a\b[^>]*href="https://[^"<>]+"[^>]*>', article, re.IGNORECASE
        )
        assert len(external_anchors) == len(urls)
        rakuten_anchors = [
            tag
            for tag in external_anchors
            if 'href="https://hb.afl.rakuten.co.jp/' in tag
        ]
        assert not rakuten_anchors

        product_ids = []
        for tag in re.findall(r"<article\b[^>]*>", article, re.IGNORECASE):
            attributes = _html_attributes(tag)
            if "product-profile" in attributes.get("class", "").split():
                product_ids.append(attributes.get("data-raos-product-id"))
        assert product_ids
        assert None not in product_ids
        assert len(product_ids) == len(set(product_ids))

        cta_counts: dict[tuple[str, str], int] = {}
        cta_anchors = []
        for tag in re.findall(r"<a\b[^>]*>", article, re.IGNORECASE):
            attributes = _html_attributes(tag)
            if "raos-cta" not in attributes.get("class", "").split():
                continue
            cta_anchors.append(attributes)
            assert "official-product-link" in attributes["class"].split()
            assert {"noopener", "noreferrer"} <= set(attributes["rel"].split())
            key = (
                attributes.get("data-raos-product-id", ""),
                attributes.get("data-raos-placement", ""),
            )
            cta_counts[key] = cta_counts.get(key, 0) + 1
            assert attributes.get("data-raos-article-id")
            assert attributes.get("href", "").startswith("https://")
        assert len(cta_anchors) == len(product_ids) * 2
        assert cta_counts == {
            (product_id, placement): 1
            for product_id in product_ids
            for placement in ("product_card", "final_summary")
        }

        assert re.search(r'\b(?:src|poster)="https://', article, re.IGNORECASE) is None
        assert re.search(r"\sdecoding=", article, re.IGNORECASE) is None
        assert all(
            re.search(r"<br\b", heading, re.I) is None
            for heading in re.findall(
                r"<h[12]\b[^>]*>(.*?)</h[12]>", article, re.I | re.S
            )
        )
        assert 'href="#local-only"' not in article
        assert "LOCAL DRAFT" not in article
        assert "ローカル" not in article
        assert "ローカル草稿" not in article
        assert "公開前一次情報再確認は未実施" not in article
        assert "広告を含みます" in article
        assert "比較テーマの共通イメージ" not in article
        assert re.search(r"2026年8月2[0-9]日", article)


def test_production_mapping_matches_all_ten_local_articles() -> None:
    fixture_rows = _posts_fixture()["posts"]
    mapping = json.loads(PRODUCTION_MAPPING.read_text(encoding="utf-8"))
    assert mapping["schema"] == "RAOS_WORDPRESS_PRODUCTION_MAPPING_V1"
    rows = mapping["articles"]
    assert len(rows) == 10
    assert {row["local_slug"] for row in rows} == {row["slug"] for row in fixture_rows}
    assert len({row["production_slug"] for row in rows}) == 10
    for row in rows:
        assert row["local_slug"] == f"local-preview-{row['production_slug']}"
        assert row["local_category"] in {"移動", "家事", "備え"}
        assert set(row["taxonomies"]) == {"category", "post_format", "post_tag"}


def test_roomba_f155260_station_dimensions_keep_width_depth_order() -> None:
    article = (ARTICLES / "roomba-mini-vs-switchbot-k11-pro.html").read_text(
        encoding="utf-8"
    )

    assert "21.2×17.8×28.5cm" not in article
    assert article.count("17.8×21.2×28.5cm") == 2
    assert "幅約17.8×奥行約21.2×高さ約28.5cm" in article


def test_editorial_stylesheet_is_owned_by_the_production_theme() -> None:
    plugin = MU_PLUGIN.read_text(encoding="utf-8")
    assert "raos-editorial-v2" not in plugin

    stylesheet = EDITORIAL_CSS.read_text(encoding="utf-8")
    for marker in (
        ".raos-editorial-v2-page",
        ".raos-editorial-v2-page .raos-article-ruleline",
        ".raos-editorial-v2-page .raos-article-title-grid",
        ".raos-editorial-v2-page .raos-article-standfirst",
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
    assert ".raos-local-editorial-v2-page" not in stylesheet


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
    assert "home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'" in seed
    assert "site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'" in seed
    assert "array('initialize', 'sync')" in seed
    assert "raos_local_preview_seed_version" in seed
    assert "RAOS_WORDPRESS_PREVIEW_ALREADY_INITIALIZED" in seed
    assert "count($fixture['posts']) !== 10" in seed
    assert "update_option('blog_public', '0')" in seed
    assert "'hb.afl.rakuten.co.jp'" in seed


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


def test_runtime_materialization_is_private_and_bound_read_only() -> None:
    wrapper = WRAPPER.read_text(encoding="utf-8")
    for marker in (
        'materialized_fixture_root="$private_root/materialized-fixtures-v2"',
        'product_media_root="$private_root/product-media"',
        "scripts/raos_editorial_portfolio_v2.py",
        'materialize-local --output-root "$private_root"',
        (
            "RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_ROOT="
            '"$materialized_fixture_root/articles"'
        ),
        (
            "RAOS_WORDPRESS_PREVIEW_POST_FIXTURE="
            '"$materialized_fixture_root/posts.json"'
        ),
        'RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT="$product_media_root"',
        "validate_materialized_runtime",
    ):
        assert marker in wrapper
    assert wrapper.count("materialize_runtime") >= 3

    gateway = GATEWAY.read_text(encoding="utf-8")
    for marker in (
        "/raos-product-media/",
        "/srv/raos-product-media/",
        "PRD-[A-Z0-9]+",
        "default_type image/jpeg",
        'add_header Cache-Control "private, no-store" always;',
        "return 404;",
    ):
        assert marker in gateway


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


def test_browser_audit_covers_home_ten_articles_and_three_pages_at_four_widths() -> (
    None
):
    audit = (SLICE / "browser/wordpress_local_preview_audit.function.js").read_text(
        encoding="utf-8"
    )
    check = (SLICE / "browser/check.sh").read_text(encoding="utf-8")
    inventory = json.loads(AUDIT_INVENTORY.read_text(encoding="utf-8"))
    generated = audit_inventory_builder.build_documents()[1]
    assert AUDIT_INVENTORY.read_bytes() == generated
    assert audit_inventory_builder.OUTPUT_AUDIT_INVENTORY_PATH == AUDIT_INVENTORY
    assert inventory["schema"] == "RAOS_WORDPRESS_AUDIT_INVENTORY_V3"
    assert inventory["viewports"] == [360, 390, 768, 1440]
    assert len(inventory["surfaces"]) == 14
    assert [row["kind"] for row in inventory["surfaces"]].count("article") == 10
    assert [row["kind"] for row in inventory["surfaces"]].count("policy") == 3
    assert len(inventory["clusters"]) == 3
    assert len(inventory["surfaces"]) * len(inventory["viewports"]) == 56
    for surface in inventory["surfaces"]:
        if surface["local_path"] != "/":
            assert surface["local_path"] not in audit
    assert "const rawSurfaces = inventory?.surfaces;" in audit
    assert "const rawClusters = inventory?.clusters;" in audit
    assert "const widths = inventory?.viewports;" in audit
    assert "path: surface.local_path" in audit
    for marker in (
        "audit.h1Count !== 1",
        "audit.h1Bounds.length !== 1",
        "audit.invalidH1Bounds !== 0",
        "audit.mainCount !== 1",
        "audit.measurementConfigDefined",
        "audit.measurementScriptCount !== 0",
        "audit.measurementSessionKeyCount !== 0",
        "audit.cookieSettingsBounds.length !== 1",
        "audit.invalidCookieSettingsBounds !== 0",
        "audit.cookieConsentBounds.length !== 1",
        "audit.cookieButtonBounds.length !== 3",
        "audit.cookieButtonOrder.join('|') !== '設定|拒否|同意'",
        "audit.cookieOverlapsH1",
        "audit.cookieOverlapsCta !== 0",
        "audit.h1LastLineCharacters === 1",
        "audit.h1LineCount > 6",
        "audit.h1LineCount > 4",
        "bounds.height < 44",
        "audit.comparisonCardsVisible === 0",
        "audit.comparisonTablesVisible !== 0",
        "audit.comparisonCardsVisible !== 0",
        "audit.comparisonTablesVisible === 0",
        "audit.ctaBounds.length === 0",
        "audit.invalidCtaBounds !== 0",
        "audit.contextualLinkCount !== 1",
        "audit.relatedLinkCount !== surface.related_article_ids.length",
        "audit.missingAlt !== 0",
        "audit.unloadedImages !== 0",
        "audit.duplicateIds.length !== 0",
        "audit.brokenAriaReferences !== 0",
        "audit.scrollWidth > audit.clientWidth",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_RUNTIME_ERROR",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_MEASUREMENT_DEFAULT_OFF_FAILED",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_SCREEN_COUNT_INVALID",
        "document.querySelectorAll('.raos-editorial-v2').length",
        "document.querySelectorAll('.decision-list').length",
        "document.querySelectorAll('.comparison-section').length",
        "document.querySelectorAll('.purchase-caution').length",
        "document.querySelectorAll('.sources-section').length",
        "surface.article &&",
        "editorialRootCount !== 1",
        "fullPage: true",
        "audit.homeClusters.length !== expectedClusters.length",
        "cluster.anchor !== expected.anchor",
        "cluster.links.length !== expected.paths.length",
        "link.pathname !== expected.paths[linkIndex]",
        "internalLinks.length !== expectedInternalLinks.length",
        "surface.contextual_article_id",
        "surface.related_article_ids.map",
        "link.origin !== origin",
        "link.search !== ''",
        "link.hash !== ''",
        "page.request.get(link.href, { maxRedirects: 0 })",
        "linkResponse.status() !== 200",
        "linkResponse.url() !== link.href",
        "page.keyboard.press('Tab')",
        "keyboardAudit.focusVisibleFailures !== 0",
        "!keyboardAudit.escapedConsentDialog",
        "!keyboardAudit.ctaReached",
        "!keyboardAudit.contextualReached",
        "!keyboardAudit.relatedReached",
        "data-raos-to-article-id",
        "data-raos-link-placement",
    ):
        assert marker in audit
    assert "process.cwd()" not in audit
    assert "wordpress-audit-inventory.v3.json" in check
    assert "inventory.surfaces" in check
    assert "inventory.viewports" in check
    assert "artifact_name in $artifact_names" in check
    assert "for surface in" not in check
    assert "output/playwright/local-preview" in check
    assert "results.length !== surfaces.length * widths.length" in audit
    assert '[ "$#" -eq "$expected_count" ]' in check


def test_fixed_policy_pages_are_tracked_and_match_the_implemented_boundaries() -> None:
    fixture = json.loads(PAGES.read_text(encoding="utf-8"))
    assert fixture["schema"] == "RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1"
    pages = fixture["pages"]
    assert [row["slug"] for row in pages] == [
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    ]
    assert all(
        isinstance(row["excerpt"], str) and 30 <= len(row["excerpt"]) <= 180
        for row in pages
    )
    contents = {
        row["slug"]: (FIXTURES / row["content_file"]).read_text(encoding="utf-8")
        for row in pages
    }
    assert "実在しない個人名" in contents["about-ad-policy"]
    assert "型番" in contents["about-ad-policy"]
    assert "メーカー公式ページへ案内" in contents["about-ad-policy"]
    assert "Evidence階層" in contents["comparison-policy"]
    assert "A：公式仕様" in contents["comparison-policy"]
    assert "B：第三者実測" in contents["comparison-policy"]
    assert "C：利用者の傾向" in contents["comparison-policy"]
    assert "D：編集部の判断" in contents["comparison-policy"]
    assert "実機未使用" in contents["comparison-policy"]
    assert "報酬率" in contents["comparison-policy"]
    privacy = contents["privacy-policy"]
    assert privacy.count("最終更新日") == 1
    assert "生イベントは7日間" in privacy
    assert "13か月" in privacy
    assert "拒否または撤回" in privacy
    assert "楽天市場やメーカー公式ページへの商品リンクは利用できます" in privacy
    assert "楽天URLのクエリ" in privacy
    seed = SEED.read_text(encoding="utf-8")
    assert "array('content_file', 'excerpt', 'slug', 'title')" in seed
    assert "'post_excerpt' => $page['excerpt']" in seed


def test_shell_entrypoints_parse() -> None:
    for path in (WRAPPER, SLICE / "browser/check.sh"):
        subprocess.run(
            ["/usr/bin/bash", "-n", str(path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
