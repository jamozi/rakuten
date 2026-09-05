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
PRODUCTION_PAGES = FIXTURES / "production-pages.json"
POLICY_PROFILES = SLICE / "policy-profiles.v1.json"
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
    "aqua-has.com",
    "cdn.shopify.com",
    "developers.rakuten.com",
    "help.ecovacs.com",
    "jp.ecoflow.com",
    "jp.roborock.com",
    "panasonic.jp",
    "shop.innovator.co.jp",
    "shop.toshiba-lifestyle.com",
    "store.ace.jp",
    "store.dji.com",
    "store.irobot-jp.com",
    "store.shopping.yahoo.co.jp",
    "store.siroca.jp",
    "support.switch-bot.com",
    "www.americantourister.jp",
    "www.ana.co.jp",
    "www.ankerjapan.com",
    "www.bagworld.co.jp",
    "www.bermas.co.jp",
    "www.bluetti.jp",
    "www.dji.com",
    "www.dreametech.jp",
    "www.ecovacs.com",
    "www.elecom.co.jp",
    "www.irisohyama.co.jp",
    "www.jackery.jp",
    "www.jal.co.jp",
    "www.meti.go.jp",
    "www.muji.com",
    "www.proteca.jp",
    "www.rimowa.com",
    "www.samsonite.co.jp",
    "www.siroca.co.jp",
    "www.switchbot.jp",
    "www.thanko.jp",
    "www.toshiba-lifestyle.com",
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
        assert len(mounts) == (8 if service_name == "cli" else 7)
        assert all(
            item["type"] == "bind" and item["read_only"] is True for item in mounts
        )
        targets = {item["target"] for item in mounts}
        expected_targets = {
            "/var/www/html/wp-content/themes/kurashinoshirube-child",
            "/var/www/html/wp-content/mu-plugins",
            "/var/www/html/wp-content/plugins/raos-editorial-measurement",
            "/var/www/html/wp-content/plugins/wordpress-seo",
            "/var/www/raos-local-preview",
            "/var/www/raos-local-preview/fixtures/articles",
            "/var/www/raos-local-preview/fixtures/posts.json",
        }
        if service_name == "cli":
            expected_targets.add("/var/www/raos-mixed-preview")
        assert targets == expected_targets
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
        yoast_mount = next(
            item for item in mounts if item["target"].endswith("plugins/wordpress-seo")
        )
        assert yoast_mount["source"] == (
            "${RAOS_WORDPRESS_PREVIEW_YOAST_ROOT:?verified Yoast root is required}"
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
        is_lifecycle_route = (
            row["article_id"] == "local-preview-solota-vs-rakua-mini-plus"
        )
        assert re.search(r"<\s*h1\b", article, re.IGNORECASE) is None
        assert "http://" not in article.lower()
        assert re.search(r"<\s*(?:script|style)\b", article, re.IGNORECASE) is None
        assert len(re.findall(r'class="raos-editorial-v2"', article)) == 1
        assert 'class="hero-photo"' not in article
        if is_lifecycle_route:
            assert '<table class="comparison-table">' not in article
            assert "data-raos-placement=" not in article
            assert 'href="/countertop-dishwasher-for-small-households/"' in article
        else:
            assert '<table class="comparison-table">' in article
        for image_tag in re.findall(r"<img\b[^>]*>", article, re.IGNORECASE):
            image_attributes = _html_attributes(image_tag)
            assert image_attributes.get("width", "").isdigit()
            assert image_attributes.get("height", "").isdigit()
            assert int(image_attributes["width"]) > 0
            assert int(image_attributes["height"]) > 0
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
        if is_lifecycle_route:
            assert not product_ids
        else:
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
        if is_lifecycle_route:
            assert not cta_anchors
            assert not cta_counts
        else:
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
        if is_lifecycle_route:
            assert "購入リンクなし" in article
        else:
            assert "広告を含みます" in article
        assert "比較テーマの共通イメージ" not in article
        assert 'tabindex="0"' not in article
        comparison_regions = [
            _html_attributes(tag)
            for tag in re.findall(r"<div\b[^>]*>", article, re.IGNORECASE)
            if "comparison-table-wrap" in _html_attributes(tag).get("class", "").split()
        ]
        if is_lifecycle_route:
            assert not comparison_regions
        else:
            assert len(comparison_regions) == 1
            assert comparison_regions[0].get("role") == "region"
            assert "tabindex" not in comparison_regions[0]
            assert comparison_regions[0].get("aria-label") or comparison_regions[0].get(
                "aria-labelledby"
            )
        assert re.search(
            r"2026年(?:[1-9]|1[0-2])月(?:[1-9]|[12][0-9]|3[01])日", article
        )


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


def test_seed_rewrites_exact_article_routes_only_for_the_isolated_preview() -> None:
    seed = SEED.read_text(encoding="utf-8")
    assert "$article_path_replacements = array();" in seed
    assert "count($article_path_replacements) !== 20" in seed
    assert "$content = strtr($content, $article_path_replacements);" in seed

    fixture_rows = _posts_fixture()["posts"]
    production_to_local = {
        row["slug"].removeprefix("local-preview-"): row["slug"] for row in fixture_rows
    }
    assert len(production_to_local) == 10
    known_local_paths = {
        f"/{local_slug}/" for local_slug in production_to_local.values()
    }
    known_page_paths = {"/about-ad-policy/", "/comparison-policy/", "/privacy-policy/"}
    for row in fixture_rows:
        article = (FIXTURES / row["content_file"]).read_text(encoding="utf-8")
        materialized = article
        for production_slug, local_slug in production_to_local.items():
            materialized = materialized.replace(
                f'href="/{production_slug}/"',
                f'href="/{local_slug}/"',
            ).replace(
                f"href='/{production_slug}/'",
                f"href='/{local_slug}/'",
            )
        internal_paths = set(
            re.findall(r"""href=["'](/[a-z0-9-]+/)["']""", materialized)
        )
        assert internal_paths <= known_local_paths | known_page_paths


def test_first_five_comparison_sections_do_not_duplicate_the_table_landmark_name() -> (
    None
):
    first_five = (
        "anker-solix-c300-c800-c1000-differences.html",
        "carry-on-suitcase-comparison.html",
        "compact-robot-vacuum-shortlist.html",
        "countertop-dishwasher-for-small-households.html",
        "portable-power-station-guide.html",
    )
    for filename in first_five:
        article = (ARTICLES / filename).read_text(encoding="utf-8")
        comparison_sections = [
            _html_attributes(tag)
            for tag in re.findall(r"<section\b[^>]*>", article, re.IGNORECASE)
            if "comparison-section" in _html_attributes(tag).get("class", "").split()
        ]
        assert len(comparison_sections) == 1
        assert "aria-label" not in comparison_sections[0]
        assert "aria-labelledby" not in comparison_sections[0]


def test_dishwasher_lifecycle_route_has_distinct_navigation_landmarks() -> None:
    article = (ARTICLES / "solota-vs-rakua-mini-plus.html").read_text(encoding="utf-8")
    assert "dish-capacity-reference" not in article
    assert article.count('aria-labelledby="dish-purchase-check-title"') == 1
    assert article.count('aria-labelledby="dish-summary-title"') == 1
    assert article.count('id="dish-purchase-check-title"') == 1
    assert article.count('id="dish-summary-title"') == 1


def test_baseline_image_gateway_quotes_braced_nginx_regex() -> None:
    gateway = GATEWAY.read_text(encoding="utf-8")
    assert 'location ~ "^/raos-baseline-media/(?<baseline_file>[a-f0-9]{64})' in gateway
    assert "alias /srv/raos-baseline-media/$baseline_file.$baseline_extension;" in gateway


def test_robot_article_station_dimensions_keep_width_depth_order() -> None:
    article = (ARTICLES / "roomba-mini-vs-switchbot-k11-pro.html").read_text(
        encoding="utf-8"
    )

    assert article.count("幅約24×奥行約18×高さ約25cm") >= 2
    assert "18×24×25cm" not in article
    assert "ステーション：約24×18×25cm" in article


def test_robot_article_separates_two_current_products_and_installation_space() -> None:
    article = (ARTICLES / "roomba-mini-vs-switchbot-k11-pro.html").read_text(
        encoding="utf-8"
    )

    product_cards = [
        _html_attributes(tag)
        for tag in re.findall(r"<article\b[^>]*>", article, re.IGNORECASE)
        if "product-profile" in _html_attributes(tag).get("class", "").split()
    ]
    assert len(product_cards) == 2
    assert {card["data-raos-product-id"] for card in product_cards} == {
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "PRD-SWITCHBOT-K11-PRO",
    }
    assert "Roomba Mini Slim" in article
    assert "SwitchBot" in article
    assert "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY" not in article
    assert "左右各1m・前方1.5m" in article
    assert "筐体寸法とは別に" in article
    assert "アプリの使いやすさ" in article
    assert "手動でダスト容器を外す動線" in article
    assert "更新履歴" in article
    assert "実機を使用しない比較であることの表示を更新" in article
    assert "2026年8月29日" not in article
    assert "assets/images/home-hero.webp" not in article
    assert "assets/images/article-robot-vacuum-guide.webp" not in article
    assert article.count("商品画像未確認・購入導線停止") == 2


def test_dishwasher_lifecycle_article_separates_unknown_sale_and_product_quality() -> (
    None
):
    article = (ARTICLES / "solota-vs-rakua-mini-plus.html").read_text(encoding="utf-8")
    assert '<table class="comparison-table">' not in article
    assert 'class="product-profile ' not in article
    assert 'class="official-product-link raos-cta"' not in article
    assert "2機種の性能や優劣を比べる記事ではありません" in article
    assert "販売終了や購入不可とは判断しません" in article
    assert "商品を候補から外す必要はありません" in article
    assert "設置条件から考える卓上食洗機の選び方" in article
    assert "現行4候補" not in article
    assert "購入候補には戻しません" not in article
    assert article.count('href="/countertop-dishwasher-for-small-households/"') == 1
    assert "NP-TML1-W" not in article
    assert "NP-TMLK1-K" in article
    assert "ラクアmini Plus TK-MDW22B" in article
    assert "再入荷通知のみ" in article
    assert "他の販売店の在庫や今後の入荷までは判断しません" in article
    assert "SS-M171は奥行43.5cm" not in article
    assert "420×435×435mm" not in article
    assert "PRD-THANKO-RAKUA-MINI-PLUS-TK-MDW22B" not in article
    assert "後継機です" not in article
    assert "後継機・同等品とは断定しません" in article
    assert "2026年9月5日" in article
    assert "過去の更新　2026.09.01" in article
    assert "2026年8月29日" not in article
    assert "assets/images/home-hero.webp" not in article
    assert "assets/images/article-countertop-dishwasher-guide.webp" not in article
    assert "商品画像未確認・購入導線停止" not in article
    assert "商品写真ではありません" not in article
    assert 'tabindex="0"' not in article


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
        "X-Content-Type-Options: nosniff",
        "Referrer-Policy: no-referrer",
        "X-Frame-Options: DENY",
        "Permissions-Policy: accelerometer=(), autoplay=(), camera=()",
        "function raos_local_preview_canonical(): void",
        "kurashinoshirube_public_head_context",
        "add_action('wp_head', 'raos_local_preview_canonical', 20);",
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
    assert "update_option('posts_per_page', 3)" in seed
    assert "update_option('default_comment_status', 'closed')" in seed
    assert "update_option('default_ping_status', 'closed')" in seed
    assert "update_option('default_pingback_flag', '0')" in seed
    assert "update_option('ping_sites', '')" in seed
    assert seed.count("'comment_status' => 'closed'") == 2
    assert seed.count("'ping_status' => 'closed'") == 2
    assert "$preview_author = get_user_by('login', 'raos-local-admin')" in seed
    assert seed.count("'post_author' => $preview_author_id") == 2
    assert "update_option('blogname', '暮らしのしるべ')" in seed
    assert "暮らしのしるべ — ローカルプレビュー" not in seed
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
        ('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE="$materialized_fixture_root/posts.json"'),
        'RAOS_WORDPRESS_PREVIEW_PRODUCT_MEDIA_ROOT="$product_media_root"',
        "validate_materialized_runtime",
    ):
        assert marker in wrapper
    assert wrapper.count("materialize_runtime") >= 3

    gateway = GATEWAY.read_text(encoding="utf-8")
    for marker in (
        "image/jpeg jpg;",
        "image/png png;",
        "image/gif gif;",
        "/raos-product-media/",
        "/srv/raos-product-media/",
        "PRD-[A-Z0-9]+",
        "(?<media_extension>jpg|png|gif)",
        "$media_file.$media_extension",
        "default_type application/octet-stream",
        'add_header Cache-Control "private, no-store" always;',
        "add_header X-Content-Type-Options nosniff always;",
        "return 404;",
    ):
        assert marker in gateway
    assert "default_type image/jpeg" not in gateway
    assert "$media_file.image" not in gateway


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


def test_browser_audit_covers_core_and_local_templates_at_four_widths() -> None:
    audit = (SLICE / "browser/wordpress_local_preview_audit.function.js").read_text(
        encoding="utf-8"
    )
    check = (SLICE / "browser/check.sh").read_text(encoding="utf-8")
    inventory = json.loads(AUDIT_INVENTORY.read_text(encoding="utf-8"))
    generated = audit_inventory_builder.build_documents()[1]
    assert AUDIT_INVENTORY.read_bytes() == generated
    assert audit_inventory_builder.OUTPUT_AUDIT_INVENTORY_PATH == AUDIT_INVENTORY
    assert "organization.name !== '暮らしのしるべ編集者'" in audit
    assert "暮らしのしるべ編集部" not in audit
    assert inventory["schema"] == "RAOS_WORDPRESS_AUDIT_INVENTORY_V3"
    assert inventory["viewports"] == [360, 390, 768, 1440]
    assert len(inventory["surfaces"]) == 14
    assert [row["kind"] for row in inventory["surfaces"]].count("article") == 10
    assert [row["kind"] for row in inventory["surfaces"]].count("policy") == 3
    assert len(inventory["local_surfaces"]) == 12
    assert [row["kind"] for row in inventory["local_surfaces"]] == [
        "search",
        "search",
        "search",
        "search",
        "search",
        "search",
        "archive",
        "archive",
        "archive",
        "archive",
        "archive",
        "not_found",
    ]
    assert [row["expected_http_status"] for row in inventory["local_surfaces"]] == [
        200,
        200,
        200,
        200,
        200,
        200,
        200,
        200,
        200,
        200,
        200,
        404,
    ]
    local_by_id = {row["surface_id"]: row for row in inventory["local_surfaces"]}
    assert local_by_id["search-empty-query"]["local_path"] == "/?s="
    assert local_by_id["search-whitespace-query"]["local_path"] == "/?s=%20%20%20"
    assert local_by_id["search-no-results"]["expected_state"] == "NO_RESULTS"
    assert local_by_id["search-hostile-query"]["local_path"] == (
        "/?s=%3Cscript%3Ealert%281%29%3C%2Fscript%3E"
    )
    assert local_by_id["search-results-page-2"] == {
        "expected_canonical": "ABSENT",
        "expected_http_status": 200,
        "expected_page_number": 2,
        "expected_search_query": "比較",
        "expected_state": "PAGED_RESULTS",
        "expected_ui_text": ["検索結果", "「比較」に一致する記事：", "前のページ"],
        "kind": "search",
        "local_path": "/?s=%E6%AF%94%E8%BC%83&paged=2",
        "route_class": "SEARCH_PAGED_RESULTS",
        "surface_id": "search-results-page-2",
    }
    assert local_by_id["archive-author-local-admin"]["local_path"] == (
        "/author/raos-local-admin/"
    )
    assert all(row["expected_canonical"] == "ABSENT" for row in local_by_id.values())
    route_coverage = inventory["route_coverage"]
    archive_coverage = {
        row["archive_type"]: row for row in route_coverage["archive_types"]
    }
    assert set(archive_coverage) == {"category", "date", "author", "tag", "post_type"}
    assert archive_coverage["category"]["status"] == "APPLICABLE"
    assert archive_coverage["date"]["status"] == "APPLICABLE"
    assert archive_coverage["author"]["status"] == "APPLICABLE"
    assert archive_coverage["tag"]["status"] == "NOT_APPLICABLE"
    assert archive_coverage["tag"]["reason_code"] == "NO_SEEDED_TAG_TERMS"
    assert archive_coverage["post_type"]["status"] == "NOT_APPLICABLE"
    assert archive_coverage["post_type"]["reason_code"] == (
        "NO_PUBLIC_HAS_ARCHIVE_POST_TYPE"
    )
    assert route_coverage["robots_profile"] == {
        "local_observed_policy": ("FORCED_ALL_NOINDEX_NOFOLLOW_NOARCHIVE_NOSNIPPET"),
        "local_profile_id": "LOCAL_PREVIEW",
        "production_expected_not_found": "noindex, nofollow",
        "production_expected_search_archive": "noindex, follow",
        "production_robots_evidence": False,
    }
    assert len(inventory["clusters"]) == 3
    assert (len(inventory["surfaces"]) + len(inventory["local_surfaces"])) * len(
        inventory["viewports"]
    ) == 104
    for surface in inventory["surfaces"]:
        if surface["local_path"] != "/":
            assert surface["local_path"] not in audit
        if surface["kind"] == "article":
            assert len(surface["related_article_ids"]) <= 1
            assert (
                surface["contextual_article_id"] not in surface["related_article_ids"]
            )
            assert surface["intent_group_id"]
            assert surface["cluster_anchor"].startswith("cluster-")
    assert "const rawSurfaces = inventory?.surfaces;" in audit
    assert "const publicSurfaces = rawSurfaces;" in audit
    assert "const localSurfaces = inventory?.local_surfaces;" in audit
    assert "routeClassCounts.size !== 10" in audit
    assert "routeClassCounts.get('ARCHIVE_CATEGORY') !== 3" in audit
    assert "const rawClusters = inventory?.clusters;" in audit
    assert "const widths = inventory?.viewports;" in audit
    assert "path: surface.local_path" in audit
    assert ("['lifecycle_status_route', '型番・販売表示の確認案内']") in audit
    for marker in (
        "audit.h1Count !== 1",
        "audit.mainCount !== 1",
        "audit.measurementConfigDefined",
        "audit.measurementScriptCount !== 0",
        "audit.measurementSessionKeyCount !== 0",
        "browserCookieCount !== 0",
        "documentCookieCount",
        "localStorageKeyCount",
        "sessionStorageKeyCount",
        "indexedDbDatabaseCount",
        "cacheStorageCount",
        "serviceWorkerRegistrationCount",
        "Object.values(audit.storageState).some((count) => count !== 0)",
        "audit.cookieSettingsCount !== 0",
        "audit.consentElementCount !== 0",
        "audit.footerBackground !== 'rgb(23, 36, 63)'",
        "audit.footerDisplay !== 'grid'",
        "audit.footerLinkBoxes.length === 0",
        "width === 1440 ? 3 : width === 768 ? 2 : 1",
        "surface.article !== audit.editorialBodyClass",
        "(surface.kind === 'policy') !== audit.policyBodyClass",
        "audit.missingAlt !== 0",
        "audit.unloadedImages !== 0",
        "audit.duplicateIds.length !== 0",
        "audit.brokenAriaReferences !== 0",
        "audit.scrollWidth > audit.clientWidth",
        "audit.axeViolations.length !== 0",
        "head.canonical.length !== 1",
        "head.ogTitle.length !== 1",
        "head.twitterCard.length !== 1",
        "head.robots.length !== 1",
        "semanticGraphFailure",
        "FORBIDDEN_TYPE",
        "BreadcrumbList",
        "mainEntityOfPage",
        "audit.fullPostContentCount !== 0",
        "audit.listingCardCount < 1",
        "SEARCH_EMPTY_QUERY",
        "SEARCH_WHITESPACE_QUERY",
        "SEARCH_HOSTILE_QUERY",
        "SEARCH_PAGED_RESULTS",
        "expected_search_query",
        "SEARCH_QUERY_MISSING",
        "SEARCH_QUERY_NOT_PRESERVED",
        "SEARCH_INPUT_NOT_PRESERVED",
        "HOSTILE_QUERY_EXECUTABLE",
        "PAGINATION_QUERY_NOT_PRESERVED",
        "PAGINATION_CONTINUITY_MISSING",
        "missingUiText",
        "surface.expected_canonical !== 'ABSENT'",
        "head.canonical.length !== 0",
        "responseHeaders['x-robots-tag']",
        "productionRobotsEvidence: robotsProfile.production_robots_evidence",
        "audit.notFoundBodyClass",
        "audit.toc.detailsOpen",
        "audit.toc.listVisible",
        "audit.toc.summaryVisible",
        "document.activeElement?.id === id",
        "document.activeElement?.id === 'raos-article-toc'",
        "page.keyboard.press('Enter')",
        "skipLinkFailure",
        "targetState.tabIndex !== '-1'",
        "desktopTocPositionFailure",
        "tocRect.left >= mainRect.right + 12",
        "document.querySelector('.raos-editorial-v2__main')",
        "CLICK_TARGET_OBSCURED",
        "await page.goto('about:blank')",
        "DIRECT_HASH_TARGET_OBSCURED",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_EXTERNAL_REQUEST",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_RUNTIME_ERROR",
        "page.on('response'",
        "response.request().resourceType() !== 'document'",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_AUDIT_FAILED_",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_MEASUREMENT_DEFAULT_OFF_FAILED",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_SCREEN_COUNT_INVALID",
        "document.querySelectorAll('.raos-editorial-v2').length",
        "fullPage: true",
        "surface.contextual_article_id",
        "surface.content_role",
        "surface.content_role_label",
        "surface.primary_query_intent",
        "surface.comparison_scope",
        "surface.broader_article_id",
        "surface.related_article_ids.map",
        "surface.cluster_anchor",
        "cluster_home",
        "new Set(links.map((link) => link.href)).size",
        "page.request.get(link.href, { maxRedirects: 0 })",
        "homeLinkFailure",
        "localLinkFailure",
        "data-raos-to-article-id",
        "data-raos-link-placement",
        "visibleFactValues('記事分類')",
        "visibleFactValues('この記事で答えること')",
        "audit.articleFacts.contentRoleLabels[0] !== surface.content_role_label",
        "audit.articleFacts.primaryQueryIntents[0] !== surface.primary_query_intent",
        "lifecycleStatusRouteArticleId = 'solota-vs-rakua-mini-plus'",
        "lifecycleStatusRouteRows.length !== 1",
        "surface.content_role === 'lifecycle_status_route'",
        "zeroProducts !== isLifecycleStatusRoute",
        "zeroCtas !== isLifecycleStatusRoute",
        "lifecycleProductCtaInvariantFailure",
        "audit.productProfileCount !== audit.productIds.length",
        "requiresAffiliateCta",
        "document.documentElement.style.setProperty('font-size', '200%', 'important')",
        "document.documentElement.style.removeProperty('font-size')",
        "wordmarkLineCount > 2",
        "element.matches('.screen-reader-text:not(:focus)')",
        "zoomAudit.rootFontSizePx < 31.5",
        "zoomAudit.scrollWidth > zoomAudit.clientWidth",
        "zoomAudit.interactiveOutOfBounds !== 0",
        "zoomAudit.clippedTextCount !== 0",
        "local-preview-${surface.name}-zoom200.png",
        "RAOS_WORDPRESS_HOME_REAL_SCROLL_FAILED_",
        "allSectionsIntersected",
        "maximumObservedScrollY",
        "reachedBottom",
        "CAPTURE_ONLY_CONTENT_VISIBILITY_EXPANDED_AFTER_REAL_SCROLL",
        "comparisonFocusabilityFailure",
        "region.scrollWidth > region.clientWidth + 1",
        "region.getAttribute('tabindex')",
        "region.dataset.raosHorizontalScroll",
        "raos-audit-capture-only-content-visibility",
        "Capture-only: interaction and paint were already verified by real scrolling.",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_BASELINE_STATE_FAILED_",
        "activeElementIsBody",
        "navigationOpenCount",
        "searchExpandedCount",
        "tocStateExpected",
        "audit.heroNotice.text !== '比較イメージ／商品写真ではありません'",
        "audit.toc.titleVisible",
    ):
        assert marker in audit
    for forbidden in (
        "__ERROR_TEMPLATE__",
        "data-raos-cookieyes-audit",
        "document.body.append(container)",
        "Cookieを使用しています",
    ):
        assert forbidden not in audit
    assert "process.cwd()" not in audit
    assert "wordpress-audit-inventory.v3.json" in check
    assert "inventory.surfaces" in check
    assert "inventory.local_surfaces" in check
    assert "inventory.viewports" in check
    assert "inventory.viewports.length + 1" in check
    assert "local-preview-${surface.surface_id}-zoom200.png" in check
    assert "node_modules/axe-core/axe.min.js" in check
    assert "artifact_name in $artifact_names" in check
    assert "for surface in" not in check
    assert "published_artifact_directory=$artifact_parent/local-preview" in check
    assert "results.length !== surfaces.length * widths.length" in audit
    assert '[ "$#" -eq "$expected_count" ]' in check
    assert '[ "$expected_count" -eq 130 ]' in check
    assert ".local-preview.pending.XXXXXX" in check
    assert "fs.readdirSync(artifactDirectory, { withFileTypes: true })" in check
    assert "actual.length !== expected.length" in check
    assert "entry.isSymbolicLink()" in check
    assert '"$artifact_directory" "$published_artifact_directory"' in check


def test_browser_audit_fails_closed_on_cross_cutting_security_and_a11y_tamper() -> None:
    audit = (SLICE / "browser/wordpress_local_preview_audit.function.js").read_text(
        encoding="utf-8"
    )
    readme = (SLICE / "README.md").read_text(encoding="utf-8")

    for marker in (
        "page.locator('.raos-disclosure')",
        ".scrollIntoViewIfNeeded()",
        "disclosure.compareDocumentPosition(firstCta)",
        "disclosureRect.bottom <= innerHeight",
        "disclosureEffectiveOpacity > 0",
        "audit.disclosure.unobscured",
        "audit.disclosure.standardPhraseCount !== 3",
        "audit.disclosure.nonaffiliatePhraseCount !== 3",
        "'購入先を案内しないことは、商品の性能が劣るという意味ではありません'",
        "audit.disclosure.ariaLabel !== '購入リンクについて'",
        "audit.disclosure.strongText !== '購入リンクなし'",
        "audit.disclosure.detailsCount !== 0",
        "audit.disclosure.standardPhraseCount !== 0",
        "audit.disclosure.nonaffiliatePhraseCount !== 0",
        "disclosureSemanticsFailure",
        "audit.disclosure.policyLinkCount !==",
        "isPreservedArticle ? incrementalExpected.expected_disclosure_policy_link_count : 1",
        "audit.disclosure.detailsValid",
        "page.keyboard.press('Enter')",
        "page.keyboard.press('Space')",
        "ENTER_DID_NOT_OPEN",
        "SPACE_DID_NOT_CLOSE",
        "affiliateRelInvalid",
        "blankRelInvalid",
        "rel.has('sponsored')",
        "rel.has('nofollow')",
        "rel.has('noopener')",
        "rel.has('noreferrer')",
        "target.href === 'mailto:contact@kurashinoshirube.com'",
        "containsForbiddenType(document)",
        "audit.jsonLd.some((document) => containsForbiddenType(document))",
        "stack.push(...Object.values(value))",
        "type.replace(/^.*[/#:]/, '')",
        "'AggregateRating', 'FAQPage', 'Offer', 'Product', 'Review'",
        "const allowedRequestMethods = new Set(['GET', 'HEAD'])",
        "'document', 'font', 'image', 'script', 'stylesheet'",
        "RAOS_WORDPRESS_LOCAL_PREVIEW_REQUEST_METHOD_OR_TYPE_FAILED",
        "page.keyboard.press('Shift+Tab')",
        "TAB_ORDER_NOT_REVERSIBLE",
        "active.matches(':focus-visible')",
        "document.elementFromPoint(sampleX, sampleY)",
        "page.emulateMedia({ reducedMotion: 'reduce' })",
        "audit.reducedMotion.animatedElementCount !== 0",
        "audit.reducedMotion.smoothScrollElementCount !== 0",
        "const responseHeaders = await response.allHeaders()",
        "^text\\/html;\\s*charset=UTF-8$",
        "'content-type-charset'",
        "characterSet: document.characterSet",
        "audit.characterSet !== 'UTF-8'",
        "responseHeaders['x-content-type-options'] === 'nosniff'",
        "responseHeaders['referrer-policy'] === 'no-referrer'",
        "responseHeaders['x-frame-options'] === 'DENY'",
        "securityHeaderFailure.length !== 0",
    ):
        assert marker in audit

    for prohibited in (
        "externalRequests.push(url)",
        "measurementRequests.push(url)",
        "resourceErrors.push(`${response.status()}:${response.url()}`)",
    ):
        assert prohibited not in audit

    assert "method, resource type, and origin class as counts" in readme
    assert "A Content Security Policy is deliberately not claimed" in readme
    assert (
        "Nine affiliate articles require the standard advertising disclosure" in readme
    )
    assert "lifecycle-status route instead requires" in readme


def test_browser_route_inventory_tamper_is_rejected_before_navigation() -> None:
    audit_path = SLICE / "browser/wordpress_local_preview_audit.function.js"
    inventory = json.loads(AUDIT_INVENTORY.read_text(encoding="utf-8"))
    cases: list[dict[str, object]] = []

    missing_route = json.loads(json.dumps(inventory))
    missing_route["local_surfaces"].pop()
    cases.append(missing_route)

    production_claim = json.loads(json.dumps(inventory))
    production_claim["route_coverage"]["robots_profile"][
        "production_robots_evidence"
    ] = True
    cases.append(production_claim)

    false_applicable = json.loads(json.dumps(inventory))
    tag = next(
        row
        for row in false_applicable["route_coverage"]["archive_types"]
        if row["archive_type"] == "tag"
    )
    tag.update(
        {
            "reason": None,
            "reason_code": None,
            "status": "APPLICABLE",
            "surface_ids": ["archive-author-local-admin"],
        }
    )
    cases.append(false_applicable)

    duplicate_route_class = json.loads(json.dumps(inventory))
    duplicate_route_class["local_surfaces"][3]["route_class"] = duplicate_route_class[
        "local_surfaces"
    ][2]["route_class"]
    cases.append(duplicate_route_class)

    a09_lifecycle_tamper = json.loads(json.dumps(inventory))
    a09 = next(
        row
        for row in a09_lifecycle_tamper["surfaces"]
        if row.get("article_id") == "roomba-mini-vs-switchbot-k11-pro"
    )
    a09["content_role"] = "lifecycle_status_route"
    a09["content_role_label"] = "型番・販売表示の確認案内"
    cases.append(a09_lifecycle_tamper)

    canonical_tamper = json.loads(json.dumps(inventory))
    canonical_tamper["local_surfaces"][0]["expected_canonical"] = "PRESENT"
    cases.append(canonical_tamper)

    japanese_ui_tamper = json.loads(json.dumps(inventory))
    japanese_ui_tamper["local_surfaces"][0]["expected_ui_text"] = []
    cases.append(japanese_ui_tamper)

    hostile_query_tamper = json.loads(json.dumps(inventory))
    hostile_query_tamper["local_surfaces"][4]["local_path"] = (
        "/?s=<script>alert(1)</script>"
    )
    cases.append(hostile_query_tamper)

    pagination_tamper = json.loads(json.dumps(inventory))
    pagination_tamper["local_surfaces"][5]["expected_page_number"] = None
    cases.append(pagination_tamper)

    harness = """
const fs = require('fs');
const vm = require('vm');
const source = fs.readFileSync(process.argv[1], 'utf8');
const factory = vm.runInNewContext(`(${source})`, Object.create(null), { timeout: 1000 });
const inventory = JSON.parse(process.argv[2]);
factory({
  artifactDirectory: '/tmp/raos-route-inventory-tamper',
  axeSource: 'x'.repeat(100001),
  inventory,
  origin: 'http://127.0.0.1:18080',
})({}).then(
  () => process.exit(2),
  (error) => process.exit(
    error?.message === 'RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID' ? 0 : 3,
  ),
);
"""
    baseline_harness = harness.replace(
        "error?.message === 'RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID' ? 0 : 3",
        "error?.message !== 'RAOS_WORDPRESS_AUDIT_INVENTORY_INVALID' ? 0 : 3",
    )
    baseline = subprocess.run(
        ["node", "-e", baseline_harness, str(audit_path), json.dumps(inventory)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert baseline.returncode == 0, baseline.stderr
    for tampered in cases:
        result = subprocess.run(
            ["node", "-e", harness, str(audit_path), json.dumps(tampered)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr


def test_local_preview_runs_three_sample_mobile_lighthouse_median_gate() -> None:
    lighthouse = (SLICE / "browser/lighthouse_check.sh").read_text(encoding="utf-8")
    check = (SLICE / "browser/check.sh").read_text(encoding="utf-8")
    package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert package["devDependencies"]["lighthouse"] == "12.8.2"
    assert "run_target home" in lighthouse
    assert "run_target article-a04" in lighthouse
    assert 'while [ "$run" -le 3 ]' in lighthouse
    assert "lcp_ms: 2500" in lighthouse
    assert "cls: 0.1" in lighthouse
    assert "tbt_ms: 200" in lighthouse
    assert "RAOS_WORDPRESS_LIGHTHOUSE_MEDIAN_V2" in lighthouse
    assert "report.lighthouseVersion !== expectedVersion" in lighthouse
    assert "report.runtimeError" in lighthouse
    assert "results.every((result) => result.passed)" in lighthouse
    assert '[ "$node_platform" = linux ] || refuse' in lighthouse
    assert "node_temporary_directory" in lighthouse
    assert '"$repository_root"/*) refuse' in lighthouse
    assert '"$lighthouse_check"' in check


def test_repository_ignores_accidental_root_lighthouse_profiles() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "output/lighthouse/" in ignore
    assert "/*lighthouse.*/" in ignore
    assert "/nul" in ignore


def test_lighthouse_evidence_is_current_hash_bound_and_tamper_closed() -> None:
    lighthouse = (SLICE / "browser/lighthouse_check.sh").read_text(encoding="utf-8")

    cleanup_at = lighthouse.index("for stale_name in")
    first_capture_at = lighthouse.index('run_target home "$preview_origin/"')
    assert cleanup_at < first_capture_at
    for marker in (
        "summary.json summary.json.tmp",
        "home-1.json home-2.json home-3.json",
        "article-a04-1.json article-a04-2.json article-a04-3.json",
        '/usr/bin/busybox rm -f -- "$stale_path"',
        "RAOS_WORDPRESS_LIGHTHOUSE_INPUT_BINDING_V1",
        "started_at: new Date().toISOString()",
        "captured_at: capturedAt",
        "MAX_EVIDENCE_AGE_MS",
        "RAOS_WORDPRESS_LIGHTHOUSE_EVIDENCE_STALE",
        "theme_source_fingerprint",
        "theme_runtime_revision",
        "theme_contract_sha256",
        "navigation_sha256",
        "audit_inventory_sha256",
        "audit_script_sha256",
        "RAOS_WORDPRESS_LIGHTHOUSE_INPUT_CHANGED",
        "RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_CHANGED",
        "RAOS_WORDPRESS_LIGHTHOUSE_THEME_EVIDENCE_MISMATCH",
        "report.fetchTime",
        "report_sha256: sha256(reportBytes)",
        "sample_count: samples.length",
        "sample_count: results.reduce",
        "medians",
        'flag: "wx"',
        "fs.renameSync(temporarySummaryPath, summaryPath)",
    ):
        assert marker in lighthouse
    assert lighthouse.count("report_sha256") == 1
    assert "summaryPath" in lighthouse


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
    assert "購入リンクの有無にかかわらず比較の対象" in contents["about-ad-policy"]
    assert contents["about-ad-policy"].count("contact@kurashinoshirube.com") == 2
    assert "AI支援の範囲" in contents["about-ad-policy"]
    assert "AIの出力自体を仕様や推薦理由の根拠にせず" in contents["about-ad-policy"]
    assert "暮らしのしるべ編集部" not in contents["about-ad-policy"]
    assert "暮らしのしるべ編集者が内容を確認し" in contents["about-ad-policy"]
    assert "利害関係は、記事の公開前に有無を確認します" in contents["about-ad-policy"]
    assert "確認が完了していない記事は公開対象にしません" in contents["about-ad-policy"]
    assert "未確認の値を推測で補うことはありません" in contents["about-ad-policy"]
    assert "根拠の扱い" in contents["comparison-policy"]
    assert "公式確認済み" in contents["comparison-policy"]
    assert "第三者の測定" in contents["comparison-policy"]
    assert "利用者情報" in contents["comparison-policy"]
    assert "編集判断・計算値" in contents["comparison-policy"]
    assert "UNKNOWN" not in contents["comparison-policy"]
    assert "実機未使用" in contents["comparison-policy"]
    assert "報酬率" in contents["comparison-policy"]
    assert (
        "市場にある全製品を網羅した一覧ではありません" in contents["comparison-policy"]
    )
    assert "結論を「該当なし」とし、購入を勧めません" in contents["comparison-policy"]
    assert (
        "測定主体、対象型番、実施時期、試験条件、方法" in contents["comparison-policy"]
    )
    assert "対象型番、掲載元、確認日、収集範囲" in contents["comparison-policy"]
    assert "確認が完了していない記事は公開しません" in contents["comparison-policy"]
    assert "暮らしのしるべ編集部" not in contents["comparison-policy"]
    assert "法令適合" not in contents["comparison-policy"]
    assert "Codexの支援と運営者の公開承認" in contents["comparison-policy"]
    assert "確認できない情報を生成内容で補いません" in contents["comparison-policy"]
    privacy = contents["privacy-policy"]
    assert privacy.count("最終更新日") == 1
    assert '<time datetime="2026-09-05">2026年9月5日</time>' in privacy
    assert "閲覧行動データを保存していません" in privacy
    assert "利用情報の収集や保存は、現時点では実施していません" in privacy
    assert "取得項目、利用目的、送信・保存先、保持期間" in privacy
    assert "7日" not in privacy
    assert "13か月" not in privacy
    for implementation_name in (
        "Google Analytics 4",
        "CookieYes",
        "WP Consent API",
        "Site Kit",
    ):
        assert implementation_name not in privacy
    assert "拒否または撤回" in privacy
    assert "第三者送信" in privacy
    assert "情報の確認・削除を求める場合" in privacy
    assert "安全管理と未成年の方へ" in privacy
    seed = SEED.read_text(encoding="utf-8")
    assert "array('content_file', 'excerpt', 'slug', 'title')" in seed
    assert "'post_excerpt' => $page['excerpt']" in seed


def test_local_and_production_policy_profiles_are_separate_and_closed() -> None:
    profiles = json.loads(POLICY_PROFILES.read_text(encoding="utf-8"))
    assert set(profiles) == {
        "contact_email",
        "local",
        "operator",
        "production",
        "schema",
        "updated_at",
        "version",
    }
    assert profiles["schema"] == "RAOS_WORDPRESS_POLICY_PROFILES_V1"
    assert profiles["operator"] == "暮らしのしるべ編集者"
    assert profiles["contact_email"] == "contact@kurashinoshirube.com"
    assert profiles["updated_at"] == "2026-09-05"
    local = profiles["local"]
    assert local["operator"] == profiles["operator"]
    assert local["contact_email"] == profiles["contact_email"]
    assert local["measurement"] == "OFF"
    assert local["consent_ui"] == "ABSENT"
    assert local["cookie_settings_control"] == "ABSENT"
    assert local["cookie_storage"] == "NONE"
    assert local["retention"] == {
        "raw_event_days": 0,
        "daily_aggregate_months": 0,
        "consent_cookie_days": 0,
        "analytics_cookie_default_max_days": 0,
        "ga4_user_event_retention_months": 0,
    }
    assert local["updated_at"] == profiles["updated_at"]
    assert "外部の解析サービスへの送信を有効にしていません" in "|".join(
        local["required_markers"]
    )
    production = profiles["production"]
    assert production["operator"] == profiles["operator"]
    assert production["contact_email"] == profiles["contact_email"]
    assert production["measurement"] == "OFF"
    assert production["cookie_storage"] == "NONE"
    assert production["ga4_activation_gate"] == (
        "BLOCKED_UNTIL_LIVE_PROPERTY_RETENTION_READBACK"
    )
    assert production["retention"] == {
        "raw_event_days": 0,
        "daily_aggregate_months": 0,
        "consent_cookie_days": 0,
        "analytics_cookie_default_max_days": 0,
        "ga4_user_event_retention_months": 0,
    }
    assert production["updated_at"] == profiles["updated_at"]
    assert production["must_not_reuse_local_body"] is True
    assert production["source"] == (
        "PROPOSED_POLICY_PRESERVING_READ_ONLY_MCP_IDS_AND_CONTACT"
    )
    assert production["consent_providers"] == []
    assert [(row["id"], row["slug"]) for row in production["pages"]] == [
        (10, "about-ad-policy"),
        (120, "comparison-policy"),
        (3, "privacy-policy"),
    ]
    seed = SEED.read_text(encoding="utf-8")
    assert "policy-profiles.v1.json" in seed
    assert "must_not_reuse_local_body" in seed
    assert seed.count("!== '2026-09-05'") == 3
    assert "!== '2026-08-31'" not in seed


def test_production_policy_documents_are_separate_from_local_preview_copy() -> None:
    local = json.loads(PAGES.read_text(encoding="utf-8"))
    production = json.loads(PRODUCTION_PAGES.read_text(encoding="utf-8"))
    assert production["schema"] == "RAOS_WORDPRESS_PRODUCTION_POLICY_PAGES_V1"
    assert [row["slug"] for row in production["pages"]] == [
        "about-ad-policy",
        "comparison-policy",
        "privacy-policy",
    ]
    local_by_slug = {row["slug"]: row for row in local["pages"]}
    for row in production["pages"]:
        slug = row["slug"]
        path = FIXTURES / row["content_file"]
        local_path = FIXTURES / local_by_slug[slug]["content_file"]
        assert path.parent == FIXTURES / "production-pages"
        assert path.is_file()
        assert path.read_bytes() != local_path.read_bytes()
        content = path.read_text(encoding="utf-8")
        assert "ローカルWordPressプレビュー" not in content
        assert "このローカルプレビュー" not in content
        assert "法令適合の最終判断" not in content
        if slug == "privacy-policy":
            assert '<time datetime="2026-09-05">2026年9月5日</time>' in content
        assert "本番投入前" not in content
        assert "contact@kurashinoshirube.com" in content
    comparison = (FIXTURES / "production-pages/comparison-policy.html").read_text(
        encoding="utf-8"
    )
    assert "Codexの支援と運営者の公開承認" in comparison
    assert "報酬率、広告主からの依頼、価格、ポイント、在庫" in comparison
    assert "UNKNOWN" not in comparison
    privacy = (FIXTURES / "production-pages/privacy-policy.html").read_text(
        encoding="utf-8"
    )
    assert "利用計測は無効です" in privacy
    assert "存在しないCookie設定へのリンクは設けません" in privacy
    assert "Google Analytics 4を読み込まず" in privacy
    assert "将来、計測を導入する場合" in privacy
    assert "本ページへ記載してから有効化します" in privacy
    assert "_ga" not in privacy
    assert "最長2年で失効" not in privacy


def test_policy_copy_distinguishes_codex_owner_and_deferred_real_world_checks() -> None:
    for profile in ("pages", "production-pages"):
        about = (FIXTURES / profile / "about-ad-policy.html").read_text(
            encoding="utf-8"
        )
        comparison = (FIXTURES / profile / "comparison-policy.html").read_text(
            encoding="utf-8"
        )
        assert "Codexは、公式情報の調査と型番照合" in about
        assert "実装・執筆を担当した作業とは別のCodex作業で点検" in about
        assert "具体的な変更内容を確認して公開を承認" in about
        assert "運営者が利用可能と確認した窓口" in about
        assert "実際の送受信試験" in about
        assert "実読者による理解度調査は未実施" in comparison
        assert "架空の購入者、使用体験、時短の実績は作りません" in comparison
        assert "比較する商品と、購入先を案内する商品は別に管理" in comparison
        assert (
            "購入リンクがないことは、その商品が劣るという意味ではありません"
            in comparison
        )
        assert "contact@kurashinoshirube.com" in about + comparison


def test_shell_entrypoints_parse() -> None:
    for path in (WRAPPER, SLICE / "browser/check.sh"):
        subprocess.run(
            ["/usr/bin/bash", "-n", str(path)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
