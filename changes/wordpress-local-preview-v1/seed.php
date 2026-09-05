<?php
/** Deterministically seed the isolated RAOS WordPress preview. */

if (! defined('WP_CLI') || WP_CLI !== true) {
    http_response_code(404);
    exit;
}

if (
    ! defined('RAOS_LOCAL_PREVIEW')
    || RAOS_LOCAL_PREVIEW !== true
    || ! defined('RAOS_WORDPRESS_PREVIEW_ORIGIN')
    || ! is_string(RAOS_WORDPRESS_PREVIEW_ORIGIN)
    || preg_match('#\Ahttp://127\.0\.0\.1:[0-9]{4,5}\z#D', RAOS_WORDPRESS_PREVIEW_ORIGIN) !== 1
    || wp_get_environment_type() !== 'local'
    || home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
    || site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_BOUNDARY_INVALID');
}

$mode = getenv('RAOS_PREVIEW_SEED_MODE');
if (! in_array($mode, array('initialize', 'sync'), true)) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_SEED_MODE_INVALID');
}

$fixture_root = '/var/www/raos-local-preview/fixtures';
$fixture_path = $fixture_root . '/posts.json';
$page_fixture_path = $fixture_root . '/pages.json';
$policy_profile_path = '/var/www/raos-local-preview/policy-profiles.v1.json';
if (! is_file($fixture_path) || is_link($fixture_path) || ! is_readable($fixture_path)) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_FIXTURE_UNAVAILABLE');
}
$fixture_bytes = file_get_contents($fixture_path);
$fixture = is_string($fixture_bytes)
    ? json_decode($fixture_bytes, true, 16, JSON_BIGINT_AS_STRING)
    : null;
if (
    ! is_array($fixture)
    || array_keys($fixture) !== array('schema', 'seed_version', 'posts')
    || $fixture['schema'] !== 'RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1'
    || ! is_string($fixture['seed_version'])
    || preg_match('/\A[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*\z/D', $fixture['seed_version']) !== 1
    || ! is_array($fixture['posts'])
    || count($fixture['posts']) !== 10
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_FIXTURE_INVALID');
}

if (
    ! is_file($page_fixture_path)
    || is_link($page_fixture_path)
    || ! is_readable($page_fixture_path)
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_FIXTURE_UNAVAILABLE');
}
$page_fixture_bytes = file_get_contents($page_fixture_path);
$page_fixture = is_string($page_fixture_bytes)
    ? json_decode($page_fixture_bytes, true, 12, JSON_BIGINT_AS_STRING)
    : null;
if (
    ! is_array($page_fixture)
    || array_keys($page_fixture) !== array('schema', 'seed_version', 'pages')
    || $page_fixture['schema'] !== 'RAOS_WORDPRESS_LOCAL_PREVIEW_PAGES_V1'
    || ! is_string($page_fixture['seed_version'])
    || preg_match('/\A[0-9]{4}-[0-9]{2}-[0-9]{2}\.[1-9][0-9]*\z/D', $page_fixture['seed_version']) !== 1
    || ! is_array($page_fixture['pages'])
    || count($page_fixture['pages']) !== 3
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_FIXTURE_INVALID');
}

if (
    ! is_file($policy_profile_path)
    || is_link($policy_profile_path)
    || ! is_readable($policy_profile_path)
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POLICY_PROFILE_UNAVAILABLE');
}
$policy_profile_bytes = file_get_contents($policy_profile_path);
$policy_profiles = is_string($policy_profile_bytes)
    ? json_decode($policy_profile_bytes, true, 12, JSON_BIGINT_AS_STRING)
    : null;
if (
    ! is_array($policy_profiles)
    || array_keys($policy_profiles) !== array(
        'schema',
        'version',
        'operator',
        'contact_email',
        'updated_at',
        'local',
        'production',
    )
    || $policy_profiles['schema'] !== 'RAOS_WORDPRESS_POLICY_PROFILES_V1'
    || $policy_profiles['version'] !== 1
    || $policy_profiles['operator'] !== '暮らしのしるべ編集者'
    || $policy_profiles['contact_email'] !== 'contact@kurashinoshirube.com'
    || $policy_profiles['updated_at'] !== '2026-09-01'
    || ! is_array($policy_profiles['local'])
    || ! is_array($policy_profiles['production'])
    || array_keys($policy_profiles['local']) !== array(
        'environment',
        'operator',
        'contact_email',
        'measurement',
        'consent_ui',
        'cookie_settings_control',
        'cookie_storage',
        'retention',
        'updated_at',
        'required_markers',
        'forbidden_markers',
    )
    || ($policy_profiles['local']['environment'] ?? null)
        !== 'LOCAL_WORDPRESS_PREVIEW'
    || ($policy_profiles['local']['operator'] ?? null)
        !== '暮らしのしるべ編集者'
    || ($policy_profiles['local']['contact_email'] ?? null)
        !== 'contact@kurashinoshirube.com'
    || ($policy_profiles['local']['measurement'] ?? null) !== 'OFF'
    || ($policy_profiles['local']['consent_ui'] ?? null) !== 'ABSENT'
    || ($policy_profiles['local']['cookie_settings_control'] ?? null) !== 'ABSENT'
    || ($policy_profiles['local']['cookie_storage'] ?? null) !== 'NONE'
    || ($policy_profiles['local']['retention'] ?? null) !== array(
        'raw_event_days' => 0,
        'daily_aggregate_months' => 0,
        'consent_cookie_days' => 0,
        'analytics_cookie_default_max_days' => 0,
        'ga4_user_event_retention_months' => 0,
    )
    || ($policy_profiles['local']['updated_at'] ?? null) !== '2026-09-01'
    || ! is_array($policy_profiles['local']['required_markers'] ?? null)
    || ! is_array($policy_profiles['local']['forbidden_markers'] ?? null)
    || array_keys($policy_profiles['production']) !== array(
        'environment',
        'operator',
        'contact_email',
        'source',
        'pages',
        'measurement',
        'cookie_storage',
        'ga4_activation_gate',
        'retention',
        'updated_at',
        'consent_providers',
        'required_markers',
        'must_not_reuse_local_body',
    )
    || ($policy_profiles['production']['environment'] ?? null)
        !== 'KURASHINOSHIRUBE_PRODUCTION'
    || ($policy_profiles['production']['operator'] ?? null)
        !== '暮らしのしるべ編集者'
    || ($policy_profiles['production']['contact_email'] ?? null)
        !== 'contact@kurashinoshirube.com'
    || ($policy_profiles['production']['source'] ?? null)
        !== 'READ_ONLY_WORDPRESS_EDITOR_BASELINE_2026_08_31'
    || ($policy_profiles['production']['must_not_reuse_local_body'] ?? null)
        !== true
    || ($policy_profiles['production']['measurement'] ?? null)
        !== 'CONSENT_GATED'
    || ($policy_profiles['production']['cookie_storage'] ?? null)
        !== 'CONSENT_PROVIDER_CONTROLLED'
    || ($policy_profiles['production']['ga4_activation_gate'] ?? null)
        !== 'BLOCKED_UNTIL_LIVE_PROPERTY_RETENTION_READBACK'
    || ($policy_profiles['production']['retention'] ?? null) !== array(
        'raw_event_days' => 7,
        'daily_aggregate_months' => 13,
        'consent_cookie_days' => 365,
        'analytics_cookie_default_max_days' => 730,
        'ga4_user_event_retention_months' => 'LIVE_READBACK_REQUIRED',
    )
    || ($policy_profiles['production']['updated_at'] ?? null) !== '2026-09-01'
    || ($policy_profiles['production']['consent_providers'] ?? null) !== array(
        'CookieYes',
        'WP Consent API',
        'Google Site Kit Consent Mode',
    )
    || ! is_array($policy_profiles['production']['required_markers'] ?? null)
    || ! is_array($policy_profiles['production']['pages'] ?? null)
    || count($policy_profiles['production']['pages']) !== 3
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POLICY_PROFILE_INVALID');
}
$expected_production_policy_pages = array(
    array(
        'id' => 10,
        'slug' => 'about-ad-policy',
        'title' => '運営・広告方針',
        'excerpt' => '暮らしのしるべの情報源選定、型番照合、広告との分離、更新・訂正の責任を説明します。',
    ),
    array(
        'id' => 120,
        'slug' => 'comparison-policy',
        'title' => '比較・編集方針',
        'excerpt' => '暮らしのしるべのEvidence階層、実機未使用時の表現、掲載順と報酬の分離、訂正手順を説明します。',
    ),
    array(
        'id' => 3,
        'slug' => 'privacy-policy',
        'title' => 'プライバシーポリシー',
        'excerpt' => '暮らしのしるべの同一オリジン計測とGA4、保持期間、同意の拒否・撤回、アフィリエイトリンクの取扱いを説明します。',
    ),
);
if ($policy_profiles['production']['pages'] !== $expected_production_policy_pages) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POLICY_PROFILE_INVALID');
}

/** Permit source links only to the reviewed manufacturer and carrier hosts. */
function raos_local_preview_has_only_reviewed_https_links(string $content): bool
{
    if (stripos($content, 'http://') !== false) {
        return false;
    }
    $matched = preg_match_all(
        '#https://[^\s"\'<>]+#u',
        $content,
        $matches
    );
    if ($matched === false) {
        return false;
    }
    $allowed_hosts = array(
        'aqua-has.com',
        'hb.afl.rakuten.co.jp',
        'cdn.shopify.com',
        'developers.rakuten.com',
        'help.ecovacs.com',
        'jp.ecoflow.com',
        'jp.roborock.com',
        'panasonic.jp',
        'shop.innovator.co.jp',
        'shop.toshiba-lifestyle.com',
        'store.ace.jp',
        'store.dji.com',
        'store.irobot-jp.com',
        'store.shopping.yahoo.co.jp',
        'store.siroca.jp',
        'support.switch-bot.com',
        'www.americantourister.jp',
        'www.ana.co.jp',
        'www.ankerjapan.com',
        'www.bagworld.co.jp',
        'www.bermas.co.jp',
        'www.bluetti.jp',
        'www.dji.com',
        'www.dreametech.jp',
        'www.ecovacs.com',
        'www.elecom.co.jp',
        'www.irisohyama.co.jp',
        'www.jackery.jp',
        'www.jal.co.jp',
        'www.meti.go.jp',
        'www.muji.com',
        'www.proteca.jp',
        'www.rimowa.com',
        'www.samsonite.co.jp',
        'www.siroca.co.jp',
        'www.switchbot.jp',
        'www.thanko.jp',
        'www.toshiba-lifestyle.com',
    );
    foreach ($matches[0] as $encoded_url) {
        $url = html_entity_decode($encoded_url, ENT_QUOTES | ENT_HTML5, 'UTF-8');
        $parts = wp_parse_url($url);
        if (
            ! is_array($parts)
            || ($parts['scheme'] ?? null) !== 'https'
            || ! is_string($parts['host'] ?? null)
            || ! in_array(strtolower($parts['host']), $allowed_hosts, true)
            || isset($parts['user'])
            || isset($parts['pass'])
            || (
                strpos($content, 'href="' . $encoded_url . '"') === false
                && strpos($content, "href='" . $encoded_url . "'") === false
            )
        ) {
            return false;
        }
    }
    return true;
}

$seed_option = 'raos_local_preview_seed_version';
$previous_seed = get_option($seed_option, null);
if ($mode === 'initialize' && is_string($previous_seed) && $previous_seed !== '') {
    WP_CLI::success('RAOS_WORDPRESS_PREVIEW_ALREADY_INITIALIZED');
    return;
}

update_option('blogname', '暮らしのしるべ');
update_option('blogdescription', '本番へ影響しない合成記事の表示確認環境');
update_option('blog_public', '0');
update_option('timezone_string', 'Asia/Tokyo');
update_option('date_format', 'Y年n月j日');
update_option('posts_per_page', 3);
update_option('permalink_structure', '/%postname%/');
update_option('default_comment_status', 'closed');
update_option('default_ping_status', 'closed');
update_option('default_pingback_flag', '0');
update_option('ping_sites', '');

$preview_author = get_user_by('login', 'raos-local-admin');
if (! ($preview_author instanceof WP_User) || (int) $preview_author->ID <= 0) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_AUTHOR_UNAVAILABLE');
}
$preview_author_id = (int) $preview_author->ID;

foreach ($page_fixture['pages'] as $page) {
    if (
        ! is_array($page)
        || array_keys($page) !== array('content_file', 'excerpt', 'slug', 'title')
        || ! is_string($page['content_file'])
        || preg_match('#\Apages/[a-z0-9-]+\.html\z#D', $page['content_file']) !== 1
        || ! is_string($page['slug'])
        || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $page['slug']) !== 1
        || ! is_string($page['title'])
        || $page['title'] === ''
        || ! is_string($page['excerpt'])
        || $page['excerpt'] === ''
        || strlen($page['excerpt']) > 512
        || wp_strip_all_tags($page['excerpt']) !== $page['excerpt']
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_FIXTURE_INVALID');
    }
    $page_path = $fixture_root . '/' . $page['content_file'];
    $page_realpath = realpath($page_path);
    $page_root_realpath = realpath($fixture_root . '/pages');
    if (
        ! is_string($page_realpath)
        || ! is_string($page_root_realpath)
        || dirname($page_realpath) !== $page_root_realpath
        || is_link($page_path)
        || ! is_readable($page_path)
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_FIXTURE_INVALID');
    }
    $content = file_get_contents($page_path);
    if (
        ! is_string($content)
        || $content === ''
        || strlen($content) > 131072
        || wp_kses_post($content) !== $content
        || ! raos_local_preview_has_only_reviewed_https_links($content)
        || preg_match('/<\s*(?:h1|script|style)\b/i', $content) === 1
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_FIXTURE_INVALID');
    }
    foreach ($policy_profiles['local']['forbidden_markers'] as $marker) {
        if (! is_string($marker) || $marker === '' || strpos($content, $marker) !== false) {
            WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POLICY_PROFILE_INVALID');
        }
    }
    $slug = $page['slug'];
    $existing = get_page_by_path($slug, OBJECT, 'page');
    $page_data = array(
        'comment_status' => 'closed',
        'ping_status' => 'closed',
        'post_author' => $preview_author_id,
        'post_content' => $content,
        'post_excerpt' => $page['excerpt'],
        'post_name' => $slug,
        'post_status' => 'publish',
        'post_title' => $page['title'],
        'post_type' => 'page',
    );
    if ($existing instanceof WP_Post) {
        $page_data['ID'] = (int) $existing->ID;
    }
    $result = wp_insert_post($page_data, true);
    if (is_wp_error($result) || (int) $result <= 0) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_PAGE_SEED_FAILED');
    }
}

$article_path_replacements = array();
foreach ($fixture['posts'] as $candidate_post) {
    if (
        ! is_array($candidate_post)
        || ! is_string($candidate_post['slug'] ?? null)
        || preg_match(
            '/\Alocal-preview-[a-z0-9]+(?:-[a-z0-9]+)*\z/D',
            $candidate_post['slug']
        ) !== 1
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
    }
    $production_slug = substr(
        $candidate_post['slug'],
        strlen('local-preview-')
    );
    if (
        $production_slug === ''
        || isset($article_path_replacements['href="/' . $production_slug . '/"'])
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
    }
    $article_path_replacements['href="/' . $production_slug . '/"'] =
        'href="/' . $candidate_post['slug'] . '/"';
    $article_path_replacements["href='/" . $production_slug . "/'"] =
        "href='/" . $candidate_post['slug'] . "/'";
}
if (count($article_path_replacements) !== 20) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
}

$seen_ids = array();
$seen_slugs = array();
foreach ($fixture['posts'] as $index => $post) {
    $expected_keys = array(
        'article_id',
        'category',
        'content_file',
        'date',
        'excerpt',
        'slug',
        'title',
    );
    if (! is_array($post) || array_keys($post) !== $expected_keys) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
    }
    foreach (array('article_id', 'category', 'date', 'excerpt', 'slug', 'title') as $key) {
        if (! is_string($post[$key]) || $post[$key] === '' || strpos($post[$key], "\0") !== false) {
            WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
        }
    }
    $title_length = function_exists('mb_strlen')
        ? mb_strlen($post['title'], 'UTF-8')
        : strlen($post['title']);
    if (
        preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $post['article_id']) !== 1
        || preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $post['slug']) !== 1
        || preg_match('/\A2026-08-(?:2[0-9]) 00:00:00\z/D', $post['date']) !== 1
        || isset($seen_ids[$post['article_id']])
        || isset($seen_slugs[$post['slug']])
        || ! in_array($post['category'], array('移動', '家事', '備え'), true)
        || ! is_string($post['content_file'])
        || preg_match('/\Aarticles\/[a-z0-9-]+\.html\z/D', $post['content_file']) !== 1
        || $post['article_id'] !== $post['slug']
        || $post['content_file'] !== 'articles/'
            . substr($post['slug'], strlen('local-preview-')) . '.html'
        || $title_length > 500
        || strlen($post['title']) > 2000
        || wp_strip_all_tags($post['title']) !== $post['title']
        || strlen($post['excerpt']) > 10000
        || wp_kses_post($post['excerpt']) !== $post['excerpt']
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
    }
    $seen_ids[$post['article_id']] = true;
    $seen_slugs[$post['slug']] = true;

    $category_slugs = array(
        '移動' => 'mobility',
        '家事' => 'household',
        '備え' => 'preparedness',
    );
    $term = term_exists($post['category'], 'category');
    if ($term === 0 || $term === null) {
        $term = wp_insert_term(
            $post['category'],
            'category',
            array('slug' => $category_slugs[$post['category']])
        );
    }
    if (is_wp_error($term)) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_CATEGORY_SEED_FAILED');
    }
    $category_id = is_array($term) ? (int) $term['term_id'] : (int) $term;
    if ($category_id <= 0) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_CATEGORY_SEED_FAILED');
    }
    $category = get_term($category_id, 'category');
    if (
        ! ($category instanceof WP_Term)
        || $category->slug !== $category_slugs[$post['category']]
    ) {
        $updated_category = wp_update_term(
            $category_id,
            'category',
            array('slug' => $category_slugs[$post['category']])
        );
        if (is_wp_error($updated_category)) {
            WP_CLI::error('RAOS_WORDPRESS_PREVIEW_CATEGORY_SEED_FAILED');
        }
    }

    $content_path = $fixture_root . '/' . $post['content_file'];
    $fixture_real = realpath($fixture_root);
    $content_real = ! is_link($content_path) ? realpath($content_path) : false;
    $content = is_string($content_real) && is_string($fixture_real)
        && str_starts_with($content_real, $fixture_real . '/articles/')
        && is_file($content_real) && is_readable($content_real)
            ? file_get_contents($content_real)
            : false;
    if (
        ! is_string($content)
        || $content === ''
        || strlen($content) > 1048576
        || stripos($content, '<script') !== false
        || stripos($content, '<style') !== false
        || stripos($content, '<h1') !== false
        || strpos($content, '<div class="raos-editorial-v2">') === false
    ) {
        WP_CLI::error(
            'RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_INVALID_' . (string) $index
        );
    }
    $content = strtr($content, $article_path_replacements);
    if (
        wp_kses_post($content) !== $content
        || ! raos_local_preview_has_only_reviewed_https_links($content)
    ) {
        WP_CLI::error(
            'RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_INVALID_' . (string) $index
        );
    }

    $existing = get_page_by_path($post['slug'], OBJECT, 'post');
    $post_data = array(
        'comment_status' => 'closed',
        'ping_status' => 'closed',
        'post_author' => $preview_author_id,
        'post_category' => array($category_id),
        'post_content' => $content,
        'post_date' => $post['date'],
        'post_date_gmt' => get_gmt_from_date($post['date']),
        'post_excerpt' => $post['excerpt'],
        'post_name' => $post['slug'],
        'post_status' => 'publish',
        'post_title' => $post['title'],
        'post_type' => 'post',
    );
    if ($existing instanceof WP_Post) {
        $post_data['ID'] = (int) $existing->ID;
    }
    $result = wp_insert_post($post_data, true);
    if (is_wp_error($result) || (int) $result <= 0) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_SEED_FAILED_' . (string) $index);
    }
}

foreach (
    array(
        'local-preview-carry-on-suitcase-comparison',
        'local-preview-portable-power-station-guide',
        'local-preview-compact-dishwasher-guide',
        'local-preview-power-model-differences',
        'local-preview-robot-vacuum-shortlist',
    ) as $retired_slug
) {
    if (isset($seen_slugs[$retired_slug])) {
        continue;
    }
    $retired = get_page_by_path($retired_slug, OBJECT, 'post');
    if ($retired instanceof WP_Post) {
        wp_delete_post((int) $retired->ID, true);
    }
}

foreach (array('post', 'page') as $post_type) {
    $default = get_page_by_path($post_type === 'post' ? 'hello-world' : 'sample-page', OBJECT, $post_type);
    if ($default instanceof WP_Post) {
        wp_delete_post((int) $default->ID, true);
    }
}

$required_local_markers = $policy_profiles['local']['required_markers'];
$all_policy_content = implode(
    "\n",
    array_map(
        static function (array $page) use ($fixture_root): string {
            $bytes = file_get_contents($fixture_root . '/' . $page['content_file']);
            return is_string($bytes) ? $bytes : '';
        },
        $page_fixture['pages']
    )
);
foreach ($required_local_markers as $marker) {
    if (! is_string($marker) || $marker === '' || strpos($all_policy_content, $marker) === false) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POLICY_PROFILE_INVALID');
    }
}

if (
    ! defined('WPSEO_VERSION')
    || WPSEO_VERSION !== '28.3'
    || ! function_exists('kurashinoshirube_verified_asset_uri')
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_YOAST_VERSION_INVALID');
}
$social_image = kurashinoshirube_verified_asset_uri(
    KURASHINOSHIRUBE_SOCIAL_IMAGE_PATH,
    KURASHINOSHIRUBE_SOCIAL_IMAGE_SHA256,
    true
);
if (! is_string($social_image) || $social_image === '') {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_YOAST_SOCIAL_IMAGE_INVALID');
}
$yoast = get_option('wpseo', array());
$yoast = is_array($yoast) ? $yoast : array();
foreach (
    array(
        'enable_ai_generator' => false,
        'enable_headless_rest_endpoints' => false,
        'enable_index_now' => false,
        'enable_schema' => false,
        'enable_schema_aggregation_endpoint' => false,
        'enable_xml_sitemap' => true,
        'google_site_kit_feature_enabled' => false,
        'googleverify' => '',
        'semrush_integration_active' => false,
        'tracking' => false,
        'wincher_integration_active' => false,
    ) as $key => $value
) {
    $yoast[$key] = $value;
}
update_option('wpseo', $yoast, false);
$yoast_social = get_option('wpseo_social', array());
$yoast_social = is_array($yoast_social) ? $yoast_social : array();
foreach (
    array(
        'og_default_image' => $social_image,
        'og_default_image_id' => '',
        'opengraph' => true,
        'twitter' => true,
        'twitter_card_type' => 'summary_large_image',
    ) as $key => $value
) {
    $yoast_social[$key] = $value;
}
update_option('wpseo_social', $yoast_social, false);
if (
    ! function_exists('kurashinoshirube_yoast_configuration_is_exact')
    || ! kurashinoshirube_yoast_configuration_is_exact()
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_YOAST_CONFIGURATION_INVALID');
}

update_option($seed_option, $fixture['seed_version'], false);
flush_rewrite_rules(false);
WP_CLI::success('RAOS_WORDPRESS_PREVIEW_SEED_' . strtoupper($mode) . '_COMPLETE');
