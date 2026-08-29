<?php
/** Deterministically seed the isolated RAOS WordPress preview. */

if (! defined('WP_CLI') || WP_CLI !== true) {
    http_response_code(404);
    exit;
}

if (
    ! defined('RAOS_LOCAL_PREVIEW')
    || RAOS_LOCAL_PREVIEW !== true
    || wp_get_environment_type() !== 'local'
    || home_url('/') !== 'http://127.0.0.1:8888/'
    || site_url('/') !== 'http://127.0.0.1:8888/'
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_BOUNDARY_INVALID');
}

$mode = getenv('RAOS_PREVIEW_SEED_MODE');
if (! in_array($mode, array('initialize', 'sync'), true)) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_SEED_MODE_INVALID');
}

$fixture_root = '/var/www/raos-local-preview/fixtures';
$fixture_path = $fixture_root . '/posts.json';
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
    || count($fixture['posts']) !== 5
) {
    WP_CLI::error('RAOS_WORDPRESS_PREVIEW_FIXTURE_INVALID');
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
        'panasonic.jp',
        'store.ace.jp',
        'store.irobot-jp.com',
        'store.shopping.yahoo.co.jp',
        'shop.innovator.co.jp',
        'www.americantourister.jp',
        'www.ana.co.jp',
        'www.bermas.co.jp',
        'www.jal.co.jp',
        'www.proteca.jp',
        'www.samsonite.co.jp',
        'www.siroca.co.jp',
        'www.switchbot.jp',
        'www.thanko.jp',
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

update_option('blogname', '暮らしのしるべ — ローカルプレビュー');
update_option('blogdescription', '本番へ影響しない合成記事の表示確認環境');
update_option('blog_public', '0');
update_option('timezone_string', 'Asia/Tokyo');
update_option('date_format', 'Y年n月j日');
update_option('permalink_structure', '/%postname%/');

foreach (
    array(
        'about-ad-policy' => array(
            'title' => '運営・広告方針 — ローカル表示確認',
            'content' => '<h2>このページについて</h2><p>この固定ページはローカルfixtureです。広告配信、計測、外部送信はありません。</p>',
        ),
        'comparison-policy' => array(
            'title' => '比較方針 — ローカル表示確認',
            'content' => '<h2>このページについて</h2><p>合成データで見出し、本文、リンクの見た目だけを確認します。</p>',
        ),
    ) as $slug => $page
) {
    $existing = get_page_by_path($slug, OBJECT, 'page');
    $page_data = array(
        'post_content' => $page['content'],
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
    if (
        preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $post['article_id']) !== 1
        || preg_match('/\Alocal-preview-[a-z0-9-]+\z/D', $post['slug']) !== 1
        || preg_match('/\A2026-08-(?:2[5-9]) 00:00:00\z/D', $post['date']) !== 1
        || isset($seen_ids[$post['article_id']])
        || isset($seen_slugs[$post['slug']])
        || ! in_array($post['category'], array('移動', '家事'), true)
        || ! is_string($post['content_file'])
        || preg_match('/\Aarticles\/[a-z0-9-]+\.html\z/D', $post['content_file']) !== 1
        || $post['article_id'] !== $post['slug']
        || $post['content_file'] !== 'articles/'
            . substr($post['slug'], strlen('local-preview-')) . '.html'
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_POST_FIXTURE_INVALID');
    }
    $seen_ids[$post['article_id']] = true;
    $seen_slugs[$post['slug']] = true;

    $term = term_exists($post['category'], 'category');
    if ($term === 0 || $term === null) {
        $term = wp_insert_term($post['category'], 'category');
    }
    if (is_wp_error($term)) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_CATEGORY_SEED_FAILED');
    }
    $category_id = is_array($term) ? (int) $term['term_id'] : (int) $term;
    if ($category_id <= 0) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_CATEGORY_SEED_FAILED');
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
        || ! raos_local_preview_has_only_reviewed_https_links($content)
        || stripos($content, '<script') !== false
        || stripos($content, '<style') !== false
        || stripos($content, '<h1') !== false
        || strpos($content, '<div class="raos-editorial-v2">') === false
    ) {
        WP_CLI::error('RAOS_WORDPRESS_PREVIEW_ARTICLE_FIXTURE_INVALID');
    }

    $existing = get_page_by_path($post['slug'], OBJECT, 'post');
    $post_data = array(
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

update_option($seed_option, $fixture['seed_version'], false);
flush_rewrite_rules(false);
WP_CLI::success('RAOS_WORDPRESS_PREVIEW_SEED_' . strtoupper($mode) . '_COMPLETE');
