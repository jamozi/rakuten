"""Theme fixes from the 2026-09-12 site audit: render-time behavior and static contracts."""

from __future__ import annotations

import json
import re

import pytest

from tests.st1704.theme_php_harness import ORIGIN, THEME, run_theme_php


FUNCTIONS = (THEME / "functions.php").read_text(encoding="utf-8")
HUB_SLUGS = ("categories", "purposes", "guides", "comparisons", "updates")

LEGACY_CARD = (
    '<article id="product-cresta-06316" class="raos-product-card product-profile" '
    'data-raos-product-id="PRD-ACE-CRESTA-06316">'
    '<figure class="raos-product-card__media raos-rakuten-product-photo" aria-label="ACE クレスタ 06316の商品画像">'
    '<div class="raos-rakuten-image-300"><a href="https://hb.afl.rakuten.co.jp/ichiba/x/?pc=y&link_type=pict" '
    'target="_blank" rel="nofollow sponsored noopener" style="word-wrap:break-word;">'
    '<img src="https://hbb.afl.rakuten.co.jp/hgb/x/?me_id=1&item_id=2&pc=z&s=300x300&t=pict" border="0" '
    'style="margin:2px" alt="" title=""></a></div>'
    '<div class="raos-rakuten-image-240"><a href="https://hb.afl.rakuten.co.jp/ichiba/x/?pc=y&link_type=pict" '
    'target="_blank" rel="nofollow sponsored noopener" style="word-wrap:break-word;">'
    '<img src="https://hbb.afl.rakuten.co.jp/hgb/x/?me_id=1&item_id=2&pc=z&s=240x240&t=pict" border="0" '
    'style="margin:2px" alt="" title=""></a></div></figure><div class="raos-product-card__body"><h3>ACE クレスタ</h3></div></article>'
)
GENERATED_CARD = (
    '<article class="ps-product" id="product-dish-np-tmlk1" data-ps-product="PRD-PANASONIC-NP-TMLK1">'
    "<h3>SOLOTA（ソロタ）</h3><p class=\"ps-model\">NP-TMLK1-K</p>"
    '<figure class="ps-product-image ps-rakuten-product-photo"><div class="raos-rakuten-image-300" data-raos-cta-type="offer">'
    '<a href="https://hb.afl.rakuten.co.jp/ichiba/a/?pc=b" target="_blank" rel="nofollow sponsored noopener">'
    '<img src="https://hbb.afl.rakuten.co.jp/hgb/a/?me_id=3&item_id=4&pc=c&s=300x300&t=pict" border="0" style="margin:2px" alt="" title=""></a></div>'
    '<div class="raos-rakuten-image-240" data-raos-cta-type="offer"><a href="https://hb.afl.rakuten.co.jp/ichiba/a/?pc=b" '
    'target="_blank" rel="nofollow sponsored noopener"><img src="https://hbb.afl.rakuten.co.jp/hgb/a/?s=240x240&t=pict" alt="" title=""></a></div>'
    "<figcaption>画像：楽天市場（カメラのキタムラ）。画像提供元の販売ページ。</figcaption></figure></article>"
)
CAPTION_ONLY = (
    '<figure class="ps-product-image ps-rakuten-product-photo"><div class="raos-rakuten-image-300">'
    '<a href="https://hb.afl.rakuten.co.jp/ichiba/q/"><img src="https://hbb.afl.rakuten.co.jp/hgb/q/?s=300x300&t=pict" alt=""></a></div>'
    "<figcaption>画像：楽天市場（コジマ楽天市場店）。画像提供元の販売ページ。</figcaption></figure>"
)

RENDER_PROGRAM = r"""
$inputs = json_decode($argv[2], true, 16, JSON_THROW_ON_ERROR);
$GLOBALS['raos_state']['singular'] = 'post';
$GLOBALS['page'] = new WP_Post();
foreach (array('ID' => 19, 'post_type' => 'post', 'post_status' => 'publish', 'post_password' => '',
    'post_name' => 'carry-on-suitcase-comparison', 'post_title' => 'エースの機内持ち込みスーツケース3モデル比較',
    'post_excerpt' => $inputs['excerpt'], 'post_content' => $inputs['content']) as $key => $value) {
    $GLOBALS['page']->$key = $value;
}
$out = array();
$out['decorated'] = kurashinoshirube_decorate_rakuten_product_images($inputs['content']);
$GLOBALS['raos_state']['feed'] = true;
$out['feed'] = kurashinoshirube_decorate_rakuten_product_images($inputs['content']);
$GLOBALS['raos_state']['feed'] = false;
$GLOBALS['raos_state']['singular'] = 'page';
$out['page'] = kurashinoshirube_decorate_rakuten_product_images($inputs['content']);
$GLOBALS['raos_state']['singular'] = 'post';
$out['minutes'] = kurashinoshirube_estimated_reading_minutes(19);
$out['minutes_empty'] = kurashinoshirube_estimated_reading_minutes(0);
$out['disclosure'] = kurashinoshirube_render_article_disclosure(array(), null, 'kurashinoshirube_article_disclosure');
$GLOBALS['page']->post_content = '<p>広告リンクのない本文です。</p>';
$out['disclosure_none'] = kurashinoshirube_render_article_disclosure(array(), null, 'kurashinoshirube_article_disclosure');
$GLOBALS['page']->post_name = 'anker-solix-c300-c800-c1000-differences';
$GLOBALS['page']->post_content = '<article class="raos-product-card" data-raos-product-id="PRD-ANKER-SOLIX-C300">'
    . '<div class="product-profile__body"><h3>Anker Solix C300</h3></div></article>';
$out['disclosure_projected'] = kurashinoshirube_render_article_disclosure(array(), null, 'kurashinoshirube_article_disclosure');
$GLOBALS['page']->post_name = 'carry-on-suitcase-comparison';
$out['lowercase_paths'] = array(
    kurashinoshirube_lowercase_request_path('/ANKER-SOLIX-C300-C800-C1000-DIFFERENCES/'),
    kurashinoshirube_lowercase_request_path('/category/%E6%9A%AE%E3%82%89%E3%81%97%E3%81%AE%E9%81%93%E5%85%B7/'),
    kurashinoshirube_lowercase_request_path('/Category/%E6%9A%AE/'),
    kurashinoshirube_lowercase_request_path('/wp-json/WP/v2/'),
    kurashinoshirube_lowercase_request_path('/kitchen/'),
);
$out['minutes_short'] = kurashinoshirube_estimated_reading_minutes(19);
$GLOBALS['page']->post_content = "  \n ";
$out['minutes_blank'] = kurashinoshirube_estimated_reading_minutes(19);
$out['excerpt_block'] = kurashinoshirube_reader_excerpt_block(
    '<div class="wp-block-post-excerpt raos-article-standfirst"><p class="wp-block-post-excerpt__excerpt">狭いキッ…</p></div>',
    array('attrs' => array('className' => 'raos-article-standfirst'), 'context' => array('postId' => 19))
);
$out['excerpt_untouched'] = kurashinoshirube_reader_excerpt_block('<p>no excerpt block</p>', array('context' => array('postId' => 19)));
$out['sentence_cut'] = kurashinoshirube_sentence_safe_excerpt(str_repeat('あ', 100) . '。' . str_repeat('い', 100) . '。', 180);
$out['hard_cut'] = kurashinoshirube_sentence_safe_excerpt(str_repeat('う', 200), 180);
$out['short'] = kurashinoshirube_sentence_safe_excerpt('短い文。', 180);
$out['date_modified'] = kurashinoshirube_label_post_date_block(
    '<div class="wp-block-post-date raos-article-date"><time datetime="2026-09-12T11:56:58+09:00">2026年9月12日</time></div>',
    array('attrs' => array('displayType' => 'modified'))
);
$out['date_published'] = kurashinoshirube_label_post_date_block(
    '<div class="wp-block-post-date"><time datetime="2026-09-09T00:00:00+09:00">2026年9月9日</time></div>',
    array('attrs' => array())
);
$out['date_idempotent'] = kurashinoshirube_label_post_date_block($out['date_modified'], array('attrs' => array('displayType' => 'modified')));
$out['author'] = kurashinoshirube_public_author_name('raos_codex_owner_direct_publisher');
$out['tagline_default'] = kurashinoshirube_default_blogdescription('');
$out['tagline_kept'] = kurashinoshirube_default_blogdescription('設定済みの説明');
$out['oembed'] = kurashinoshirube_strip_oembed_author(array('title' => 't', 'author_name' => 'kurashishirube', 'author_url' => 'u', 'html' => 'h'));
$out['defer_banner'] = kurashinoshirube_defer_consent_banner_script('<script id="cookie-law-info-js" src="https://kurashinoshirube.com/x.js?ver=3.5.5"></script>', 'cookie-law-info');
$out['defer_twice'] = kurashinoshirube_defer_consent_banner_script($out['defer_banner'], 'cookie-law-info');
$out['defer_other'] = kurashinoshirube_defer_consent_banner_script('<script id="other-js" src="https://kurashinoshirube.com/y.js"></script>', 'other');
$out['inline_budget'] = array(kurashinoshirube_inline_style_budget(20000), kurashinoshirube_inline_style_budget(4096), kurashinoshirube_inline_style_budget('x'));
$GLOBALS['raos_state']['logged_in'] = false;
$out['users_anonymous'] = kurashinoshirube_user_route_permission();
$GLOBALS['raos_state']['logged_in'] = true;
$GLOBALS['raos_state']['caps'] = array('edit_posts');
$out['users_editor'] = kurashinoshirube_user_route_permission();
$GLOBALS['raos_state']['caps'] = array('read');
$out['users_subscriber'] = kurashinoshirube_user_route_permission();
$GLOBALS['raos_state']['logged_in'] = false;
$endpoints = array(
    '/wp/v2/users' => array(array('methods' => 'GET', 'callback' => 'x', 'permission_callback' => 'y'), 'namespace' => 'wp/v2'),
    '/wp/v2/users/(?P<id>[\d]+)' => array(array('methods' => 'GET', 'callback' => 'x', 'permission_callback' => 'y')),
    '/wp/v2/users/me' => array(array('methods' => 'GET', 'callback' => 'x', 'permission_callback' => 'y')),
    '/wp/v2/posts' => array(array('methods' => 'GET', 'callback' => 'x', 'permission_callback' => 'y')),
);
$out['endpoints'] = kurashinoshirube_restrict_user_rest_routes($endpoints);
class RAOS_Fake_Response { public $data; function __construct($d) { $this->data = $d; } function get_data() { return $this->data; } function set_data($d) { $this->data = $d; } }
$index = new RAOS_Fake_Response(array('namespaces' => array('oembed/1.0', 'wp/v2', 'aios/v1', 'raos-codex-mcp/v1'),
    'routes' => array('/' => 1, '/oembed/1.0' => 1, '/oembed/1.0/embed' => 1, '/wp/v2' => 1, '/wp/v2/posts' => 1, '/aios/v1' => 1, '/raos-codex-mcp/v1/publish' => 1, '/wp/v2x' => 1)));
$out['index'] = kurashinoshirube_restrict_public_rest_index($index, null)->get_data();
$GLOBALS['raos_state']['logged_in'] = true;
$logged = new RAOS_Fake_Response(array('namespaces' => array('aios/v1')));
$out['index_logged_in'] = kurashinoshirube_restrict_public_rest_index($logged, null)->get_data();
$GLOBALS['raos_state']['logged_in'] = false;
$GLOBALS['raos_state']['singular'] = null;
$GLOBALS['raos_state']['search'] = true;
$GLOBALS['raos_state']['search_query'] = '食洗機';
$out['search_canonical'] = kurashinoshirube_archive_canonical_url();
$hub = new WP_Post();
foreach (array('ID' => 136, 'post_type' => 'page', 'post_status' => 'publish', 'post_password' => '', 'post_name' => 'kitchen',
    'post_title' => '食洗機の選び方・比較', 'post_excerpt' => '', 'post_content' => '') as $key => $value) { $hub->$key = $value; }
$GLOBALS['pages']['kitchen'] = $hub;
kurashinoshirube_flush_reader_hub_page_cache();
$out['hint_kitchen'] = kurashinoshirube_search_hub_hint('食洗機');
$out['hint_solota'] = kurashinoshirube_search_hub_hint('ＳＯＬＯＴＡ');
$out['hint_none'] = kurashinoshirube_search_hub_hint('ドライヤー');
$out['hint_travel_unreachable'] = kurashinoshirube_search_hub_hint('スーツケース');
$out['hooks'] = $GLOBALS['raos_hooks'];
echo json_encode($out, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
"""


@pytest.fixture(scope="module")
def rendered() -> dict[str, object]:
    content = (
        '<div class="raos-editorial-v2"><section class="products-section">'
        + LEGACY_CARD
        + GENERATED_CARD
        + CAPTION_ONLY
        + "</section><p>"
        + "本文" * 700
        + "</p></div>\n"
    )
    excerpt = "型番と一次情報を照合できたエース系3モデルを、軽さ・容量・開き方で条件別に比較。市場全体の順位ではなく、向く人と注意点を整理します。"
    return run_theme_php(
        RENDER_PROGRAM,
        json.dumps({"content": content, "excerpt": excerpt}, ensure_ascii=False),
    )


def test_rakuten_images_get_alt_dimensions_and_one_size_without_touching_anchors(rendered) -> None:
    decorated = str(rendered["decorated"])
    assert "raos-rakuten-image-240" not in decorated
    assert decorated.count("hbb.afl.rakuten.co.jp") == 3
    assert 'alt="ACE クレスタ 06316 の商品画像（楽天市場）"' in decorated
    assert 'alt="SOLOTA（ソロタ） NP-TMLK1-K の商品画像（楽天市場）"' in decorated
    assert 'alt="コジマ楽天市場店 の商品画像（楽天市場）"' in decorated
    assert decorated.count('width="300"') == 3 and decorated.count('height="300"') == 3
    assert decorated.count('loading="lazy"') == 3 and decorated.count('decoding="async"') == 3
    assert 'alt=""' not in decorated
    anchors = re.findall(r"<a [^>]*>", decorated)
    assert anchors == [
        '<a href="https://hb.afl.rakuten.co.jp/ichiba/x/?pc=y&link_type=pict" target="_blank" rel="nofollow sponsored noopener" style="word-wrap:break-word;">',
        '<a href="https://hb.afl.rakuten.co.jp/ichiba/a/?pc=b" target="_blank" rel="nofollow sponsored noopener">',
        '<a href="https://hb.afl.rakuten.co.jp/ichiba/q/">',
    ]
    # Feeds and non-article routes keep the stored markup untouched.
    assert "raos-rakuten-image-240" in str(rendered["feed"])
    assert "raos-rakuten-image-240" in str(rendered["page"])


def test_reading_time_comes_from_the_stored_body(rendered) -> None:
    # 1,400 characters of body copy plus the card text rounds up to three minutes at 500/min.
    assert rendered["minutes"] == 3
    assert rendered["minutes_short"] == 1
    assert rendered["minutes_blank"] is None
    assert rendered["minutes_empty"] is None


def test_article_disclosure_reflects_affiliate_presence(rendered) -> None:
    affiliate = str(rendered["disclosure"])
    assert affiliate.startswith('<p class="raos-ad-disclosure" data-raos-ad-disclosure="affiliate">')
    # Legacy articles receive Rakuten-generated photos at render time (official-product-media.php);
    # the stored body has no affiliate link, yet the page does.
    projected = str(rendered["disclosure_projected"])
    assert 'data-raos-ad-disclosure="affiliate"' in projected
    assert "この記事には広告（楽天アフィリエイトの購入・商品画像リンク）が含まれます。成果報酬は評価や掲載順に影響しません。" in affiliate
    none = str(rendered["disclosure_none"])
    assert 'data-raos-ad-disclosure="none"' in none
    assert "この記事にアフィリエイトリンクはありません。" in none


def test_lowercase_redirect_ignores_percent_encoding_and_wp_paths(rendered) -> None:
    assert rendered["lowercase_paths"] == [
        "/anker-solix-c300-c800-c1000-differences/",
        None,
        "/category/%E6%9A%AE/",
        None,
        None,
    ]


def test_excerpts_are_whole_sentences_not_word_cuts(rendered) -> None:
    block = str(rendered["excerpt_block"])
    assert "狭いキッ…" not in block
    assert "向く人と注意点を整理します。</p>" in block
    assert block.startswith('<div class="wp-block-post-excerpt raos-article-standfirst">')
    assert rendered["excerpt_untouched"] == "<p>no excerpt block</p>"
    assert rendered["sentence_cut"] == "あ" * 100 + "。"
    assert rendered["hard_cut"] == "う" * 180 + "…"
    assert rendered["short"] == "短い文。"


def test_dates_carry_a_published_or_updated_label(rendered) -> None:
    modified = str(rendered["date_modified"])
    assert modified.startswith('<div class="wp-block-post-date raos-article-date"><span class="raos-date-label">更新日</span> <time')
    assert '<span class="raos-date-label">公開日</span> <time' in str(rendered["date_published"])
    assert rendered["date_idempotent"] == modified


def test_public_author_tagline_oembed_and_banner_defer(rendered) -> None:
    assert rendered["author"] == "暮らしのしるべ編集部"
    assert rendered["tagline_default"] == "生活用品を公式仕様で比較する読み物"
    assert rendered["tagline_kept"] == "設定済みの説明"
    assert rendered["oembed"] == {"title": "t", "html": "h"}
    assert rendered["defer_banner"] == (
        '<script id="cookie-law-info-js" defer src="https://kurashinoshirube.com/x.js?ver=3.5.5"></script>'
    )
    assert rendered["defer_twice"] == rendered["defer_banner"]
    assert rendered["defer_other"] == '<script id="other-js" src="https://kurashinoshirube.com/y.js"></script>'
    assert rendered["inline_budget"] == [10240, 4096, "x"]


def test_user_routes_reject_anonymous_clients_with_401(rendered) -> None:
    anonymous = rendered["users_anonymous"]
    assert anonymous["code"] == "rest_forbidden" and anonymous["data"] == {"status": 401}
    assert rendered["users_editor"] is True
    subscriber = rendered["users_subscriber"]
    assert subscriber["code"] == "rest_forbidden" and subscriber["data"] == {"status": 403}
    endpoints = rendered["endpoints"]

    def first_handler(route: str) -> dict[str, object]:
        handlers = endpoints[route]
        return handlers[0] if isinstance(handlers, list) else handlers["0"]

    for route in ("/wp/v2/users", "/wp/v2/users/(?P<id>[\\d]+)"):
        assert first_handler(route)["permission_callback"] == "kurashinoshirube_user_route_permission"
    assert endpoints["/wp/v2/users"]["namespace"] == "wp/v2"
    assert first_handler("/wp/v2/users/me")["permission_callback"] == "y"
    assert first_handler("/wp/v2/posts")["permission_callback"] == "y"


def test_anonymous_rest_index_lists_only_public_namespaces(rendered) -> None:
    index = rendered["index"]
    assert index["namespaces"] == ["oembed/1.0", "wp/v2"]
    assert sorted(index["routes"]) == ["/", "/oembed/1.0", "/oembed/1.0/embed", "/wp/v2", "/wp/v2/posts"]
    assert rendered["index_logged_in"] == {"namespaces": ["aios/v1"]}


def test_search_surfaces_get_self_canonical_and_hub_hints(rendered) -> None:
    assert rendered["search_canonical"] == ORIGIN + "/?s=%E9%A3%9F%E6%B4%97%E6%A9%9F"
    kitchen = str(rendered["hint_kitchen"])
    assert kitchen.startswith('<p class="raos-listing-hub-hint">')
    assert f'href="{ORIGIN}/kitchen/">食洗機の比較はこちら' in kitchen
    assert rendered["hint_solota"] == kitchen
    assert rendered["hint_none"] == ""
    # A matched route whose hub page is not reachable renders nothing rather than a dead link.
    assert rendered["hint_travel_unreachable"] == ""


def test_public_surface_hooks_are_registered(rendered) -> None:
    hooks = {(kind, name, callback) for kind, name, callback in rendered["hooks"] if isinstance(callback, str)}
    for expected in (
        ("action", "send_headers", "kurashinoshirube_send_security_headers"),
        ("action", "template_redirect", "kurashinoshirube_disable_author_archives"),
        ("action", "template_redirect", "kurashinoshirube_redirect_uppercase_request_path"),
        ("action", "template_redirect", "kurashinoshirube_redirect_sole_category_archive"),
        ("action", "after_setup_theme", "kurashinoshirube_unhook_core_head_extras"),
        ("action", "do_faviconico", "kurashinoshirube_serve_favicon_ico"),
        ("action", "wp_head", "kurashinoshirube_emit_archive_canonical"),
        ("action", "wp_footer", "kurashinoshirube_print_focus_guard_script"),
        ("filter", "rest_endpoints", "kurashinoshirube_restrict_user_rest_routes"),
        ("filter", "rest_index", "kurashinoshirube_restrict_public_rest_index"),
        ("filter", "oembed_response_data", "kurashinoshirube_strip_oembed_author"),
        ("filter", "the_generator", "__return_empty_string"),
        ("filter", "feed_links_show_comments_feed", "__return_false"),
        ("filter", "option_blogdescription", "kurashinoshirube_default_blogdescription"),
        ("filter", "the_author", "kurashinoshirube_public_author_name"),
        ("filter", "get_the_author_display_name", "kurashinoshirube_public_author_name"),
        ("filter", "should_load_separate_core_block_assets", "__return_true"),
        ("filter", "styles_inline_size_limit", "kurashinoshirube_inline_style_budget"),
        ("filter", "script_loader_tag", "kurashinoshirube_defer_consent_banner_script"),
        ("filter", "render_block_core/post-date", "kurashinoshirube_label_post_date_block"),
        ("filter", "the_content", "kurashinoshirube_decorate_rakuten_product_images"),
    ):
        assert expected in hooks, expected
    headers = FUNCTIONS.split("function kurashinoshirube_send_security_headers", 1)[1].split("add_action(", 1)[0]
    for header in (
        "X-Content-Type-Options: nosniff",
        "Referrer-Policy: strict-origin-when-cross-origin",
        "X-Frame-Options: SAMEORIGIN",
        "Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()",
        "Strict-Transport-Security: max-age=31536000; includeSubDomains",
    ):
        assert header in headers
    assert "Content-Security-Policy" not in FUNCTIONS
    unhook = FUNCTIONS.split("function kurashinoshirube_unhook_core_head_extras", 1)[1].split("add_action(", 1)[0]
    for removed in (
        "remove_action('wp_head', 'wp_generator')",
        "remove_action('wp_enqueue_scripts', 'wp_enqueue_block_template_skip_link')",
        "remove_action('wp_footer', 'the_block_template_skip_link')",
    ):
        assert removed in unhook
    ordering = FUNCTIONS.split("function kurashinoshirube_constrain_public_search", 1)[1].split("add_action(", 1)[0]
    assert "$query->is_category() || $query->is_tag() || $query->is_author()" in ordering
    assert "$query->set('orderby', 'modified');" in ordering
    assert "add_filter('the_content', 'kurashinoshirube_decorate_rakuten_product_images', 14);" in FUNCTIONS
    assert "'carry-on-suitcase-under-100-seats' => '100席以上の便を使うなら、この比較も確認する：'" in FUNCTIONS
    assert "$public_article = is_singular('post')" in FUNCTIONS


def test_single_template_orders_disclosure_before_standfirst_and_labels_dates() -> None:
    single = (THEME / "templates/single.html").read_text(encoding="utf-8")
    markers = [
        'wp:post-title {"level":1}',
        "[kurashinoshirube_article_disclosure]",
        '"className":"raos-article-standfirst"',
        '<p class="raos-byline">執筆・確認：<a href="/about-ad-policy/">暮らしのしるべ編集部</a></p>',
        "wp:post-content",
    ]
    positions = [single.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert single.count("[kurashinoshirube_article_disclosure]") == 1
    assert single.count("wp:post-date") == 2
    assert '"format":"Y年n月j日","className":"raos-article-date raos-article-date--published"' in single
    assert '"format":"Y年n月j日","displayType":"modified","className":"raos-article-date raos-article-date--modified"' in single
    assert '"format":"Y.m.d"' not in single
    assert '"excerptLength":200' in single
    front = (THEME / "templates/front-page.html").read_text(encoding="utf-8")
    assert front.count('class="raos-ad-disclosure raos-ad-disclosure--home"') == 1
    assert front.index("raos-ad-disclosure--home") < front.index("wp:post-content")


def test_listing_templates_have_one_link_per_card_and_a_search_form() -> None:
    for name in ("archive", "search", "home"):
        template = (THEME / f"templates/{name}.html").read_text(encoding="utf-8")
        assert '"moreText":"記事を読む"' not in template
        assert template.count('<!-- wp:post-excerpt {"moreText":"","showMoreOnNewLine":false,"excerptLength":200} /-->') == 1
        assert '"displayType":"modified"' in template
    search = (THEME / "templates/search.html").read_text(encoding="utf-8")
    header = search.split('<div class="wp-block-group alignwide raos-listing-header">', 1)[1].split("<!-- /wp:group -->", 1)[0]
    assert '<!-- wp:search {"label":"記事を再検索"' in header
    assert search.count("<!-- wp:search ") == 2
    not_found = (THEME / "templates/404.html").read_text(encoding="utf-8")
    assert "<h1 class=\"wp-block-heading\">ページが見つかりません</h1>" in not_found
    assert "ページが見つかりませんでした" not in not_found
    links = re.findall(r'<a href="(/[a-z-]+/)">', not_found.split('class="raos-not-found-links"', 1)[1].split("</nav>", 1)[0])
    assert links == ["/categories/", "/purposes/", "/kitchen/", "/travel/", "/cleaning/", "/preparedness/"]


def test_header_and_footer_expose_the_five_hubs_policies_and_contact() -> None:
    header = (THEME / "parts/header.html").read_text(encoding="utf-8")
    assert header.startswith(
        '<!-- wp:html -->\n<nav class="raos-skip-links" aria-label="スキップリンク"><a class="raos-skip-link" href="#main-content">本文へ移動</a></nav>\n<!-- /wp:html -->\n'
    )
    for nav in re.findall(r"<!-- wp:navigation \{.*?\} -->(.*?)<!-- /wp:navigation -->", header, flags=re.S):
        urls = [json.loads(raw)["url"] for raw in re.findall(r"<!-- wp:navigation-link (\{.*?\}) /-->", nav)]
        assert urls == [f"/{slug}/" for slug in HUB_SLUGS]
        assert len(urls) >= 5
    footer = (THEME / "parts/footer.html").read_text(encoding="utf-8")
    nav_urls = [json.loads(raw)["url"] for raw in re.findall(r"<!-- wp:navigation-link (\{.*?\}) /-->", footer)]
    assert nav_urls == [f"/{slug}/" for slug in HUB_SLUGS]
    hrefs = re.findall(r'href="([^"]+)"', footer)
    assert hrefs == [
        "/about-ad-policy/",
        "/comparison-policy/",
        "/privacy-policy/",
        "mailto:contact@kurashinoshirube.com",
    ]
    assert len(set(nav_urls + hrefs)) == len(nav_urls + hrefs)
    assert "/about/" not in footer
    assert "運営・広告方針" in footer and "比較・編集方針" in footer and "プライバシーポリシー" in footer
    functions = FUNCTIONS
    assert "'raos-reader-hub-page'" in functions
    assert "render_block_core/navigation-link" not in functions


def test_stylesheets_reserve_image_frames_and_keep_meta_text_readable() -> None:
    theme_css = (THEME / "assets/theme.css").read_text(encoding="utf-8")
    editorial_css = (THEME / "assets/editorial-v2.css").read_text(encoding="utf-8")
    purchase_css = (THEME / "assets/purchase-support.css").read_text(encoding="utf-8")
    for css in (editorial_css, purchase_css):
        assert ".raos-rakuten-image-300 {" in css
        frame = css.split(".raos-rakuten-image-300 {", 1)[1].split("}", 1)[0]
        assert "aspect-ratio: 1 / 1;" in frame and "width: 300px;" in frame and "max-width: 100%;" in frame
        assert ".raos-rakuten-image-240 { display: none; }" in css
        assert "@container (max-width: 319px)" not in css
        assert "@media (max-width: 359px)" not in css
    assert ".raos-skip-link:focus {" in theme_css
    assert ".raos-ad-disclosure {" in theme_css
    disclosure = theme_css.split(".raos-ad-disclosure {", 1)[1].split("}", 1)[0]
    assert "font-size: 0.9rem;" in disclosure
    banner = theme_css.split("@media (max-width: 47.99rem) {", 1)[1].split("@media (forced-colors: active)", 1)[0]
    assert "max-height: 25vh !important;" in banner and "overflow: auto !important;" in banner
    assert "scroll-padding-bottom: 26vh;" in banner
    assert 'content: " UPDATED"' not in theme_css
    assert ".raos-date-label {" in theme_css


EDITORIAL_V2_ARTICLE = (
    '<div class="raos-editorial-v2"><section class="lead-section" data-raos-article-id="st1703-first-suitcase-comparison">'
    "<h2>結論</h2><p>本文</p></section>"
    '<section class="sources-section"><h2>確認に使った一次情報</h2><ol><li><span>1</span><p>'
    '<a class="raos-source-link" href="https://store.ace.jp/shop/g/g06316-01/">ACE クレスタ 06316（エース公式オンラインストア）</a></p></li></ol>'
    '<p class="raos-source-link"><a href="https://developers.rakuten.com/">Supported by Rakuten Developers</a></p></section></div>\n'
)

FOLLOW_UP_PROGRAM = r"""
$hubs = json_decode($argv[2], true, 16, JSON_THROW_ON_ERROR);
foreach ($hubs as $index => $hub) {
    $page = new WP_Post();
    foreach (array('ID' => 700 + $index, 'post_type' => 'page', 'post_status' => 'publish', 'post_password' => '',
        'post_name' => $hub['slug'], 'post_title' => $hub['title'], 'post_excerpt' => '', 'post_content' => '') as $key => $value) {
        $page->$key = $value;
    }
    $GLOBALS['pages'][$hub['slug']] = $page;
}
$GLOBALS['raos_state']['singular'] = 'post';
$GLOBALS['page'] = new WP_Post();
foreach (array('ID' => 19, 'post_type' => 'post', 'post_status' => 'publish', 'post_password' => '',
    'post_name' => 'carry-on-suitcase-comparison', 'post_title' => 'エースの機内持ち込みスーツケース3モデル比較',
    'post_excerpt' => str_repeat('要約', 20), 'post_content' => $argv[3]) as $key => $value) {
    $GLOBALS['page']->$key = $value;
}
$out = array();
$out['identity'] = kurashinoshirube_public_article_identity(19);
$out['relocated'] = kurashinoshirube_relocate_rakuten_developers_credit($argv[3]);
$out['relocated_twice'] = kurashinoshirube_relocate_rakuten_developers_credit($out['relocated']);
$out['no_credit'] = kurashinoshirube_relocate_rakuten_developers_credit('<div class="raos-editorial-v2"><p>本文</p></div>');
$out['related'] = kurashinoshirube_render_related_guides(array(), null, 'kurashinoshirube_related_guides');
$out['purposes'] = kurashinoshirube_render_purpose_hub_entrances('st1703-first-suitcase-comparison');
$out['purposes_guide'] = kurashinoshirube_render_purpose_hub_entrances('dishwasher-installation-measurement');
$out['purposes_unknown'] = kurashinoshirube_render_purpose_hub_entrances('no-such-article');
$GLOBALS['raos_state']['front'] = true;
$GLOBALS['raos_state']['singular'] = null;
$out['preload_home'] = kurashinoshirube_preload_home_hero_image(array(array('href' => 'x', 'as' => 'style')));
$GLOBALS['raos_state']['front'] = false;
$out['preload_elsewhere'] = kurashinoshirube_preload_home_hero_image(array());
echo json_encode($out, JSON_THROW_ON_ERROR | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
"""


@pytest.fixture(scope="module")
def follow_up() -> dict[str, object]:
    registry = json.loads((THEME / "assets/editorial-navigation.v3.json").read_text(encoding="utf-8"))
    hubs = [
        {"slug": hub["slug"], "title": "ページ題：" + hub["label"]}
        for hub in registry["reader_navigation"]["hubs"]
    ]
    return run_theme_php(FOLLOW_UP_PROGRAM, json.dumps(hubs, ensure_ascii=False), EDITORIAL_V2_ARTICLE)


def test_rakuten_developers_credit_moves_out_of_the_source_list_with_a_note(follow_up) -> None:
    assert follow_up["identity"]["article_id"] == "st1703-first-suitcase-comparison"
    relocated = str(follow_up["relocated"])
    credit = '<p class="raos-source-link"><a href="https://developers.rakuten.com/">Supported by Rakuten Developers</a></p>'
    note = '<p class="raos-api-credit">商品情報の取得にRakuten Developers APIを利用しています（出典ではありません）。</p>'
    assert relocated.count(credit) == 1
    assert relocated.endswith(note + credit + "</div>\n")
    assert relocated.index("</ol></section>") < relocated.index(note)
    assert relocated.count('class="raos-source-link"') == 2  # the numbered source link stays in place
    assert follow_up["relocated_twice"] == relocated
    assert follow_up["no_credit"] == '<div class="raos-editorial-v2"><p>本文</p></div>'


def test_related_guides_end_with_purpose_hub_entrances_named_after_the_hub_pages(follow_up) -> None:
    registry = json.loads((THEME / "assets/editorial-navigation.v3.json").read_text(encoding="utf-8"))
    purposes = [
        hub for hub in registry["reader_navigation"]["hubs"]
        if hub["kind"] == "purpose" and "st1703-first-suitcase-comparison" in hub["article_ids"]
    ]
    assert purposes
    entrances = str(follow_up["purposes"])
    assert entrances.startswith('<h3 class="raos-related-guides__purposes-title">目的別の入口</h3>')
    links = re.findall(r'<li><a href="([^"]+)" data-raos-link-placement="purpose_hub">([^<]+)</a></li>', entrances)
    assert links == [(f"{ORIGIN}/{hub['slug']}/", "ページ題：" + hub["label"]) for hub in purposes]
    related = str(follow_up["related"])
    assert related.startswith('<aside class="raos-related-guides" aria-labelledby="raos-related-title">')
    assert related.endswith(entrances + "</aside>")
    assert 'data-raos-link-placement="category_hub"' in related
    # A reader guide joins the purpose hubs only once its applied public snapshot exists;
    # the harness has no such post, so no entrance is fabricated for it.
    assert follow_up["purposes_guide"] == ""
    assert follow_up["purposes_unknown"] == ""


def test_home_hero_photo_is_preloaded_only_on_the_front_page(follow_up) -> None:
    assert follow_up["preload_home"] == [
        {"href": "x", "as": "style"},
        {
            "as": "image",
            "fetchpriority": "high",
            "href": f"{ORIGIN}/wp-content/themes/kurashinoshirube-child/assets/images/magazine-hero.webp",
            "type": "image/webp",
        },
    ]
    assert follow_up["preload_elsewhere"] == []
