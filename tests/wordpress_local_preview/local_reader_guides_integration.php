<?php
/** Run in an isolated PHP container with a tmpfs at /var/www/raos-local-preview. */
function check($condition, $message) { if (!$condition) { throw new RuntimeException($message); } }
function add_filter(...$args) {}
function add_action(...$args) {}
function add_shortcode(...$args) {}
function wp_get_environment_type() { return $GLOBALS['environment'] ?? 'local'; }
define('RAOS_LOCAL_PREVIEW', true);
define('RAOS_WORDPRESS_PREVIEW_ORIGIN', 'http://127.0.0.1:18080');
function home_url($path = '/') { return ($GLOBALS['origin'] ?? RAOS_WORDPRESS_PREVIEW_ORIGIN) . $path; }
function site_url($path = '/') { return home_url($path); }
function get_option($key, $default = false) { return $GLOBALS['options'][$key] ?? $default; }
function update_option($key, $value, ...$args) { $GLOBALS['options'][$key] = $value; return true; }
$without_plugin = in_array('--without-plugin', $argv, true);
if (!$without_plugin) {
    require __DIR__ . '/../../changes/wordpress-local-preview-v1/mu-plugins/raos-local-preview.php';
    check(function_exists('raos_local_reader_guides_validate'), 'missing local guide fixture validator');
    check(raos_local_reader_guides_today(new DateTimeImmutable('2030-09-10T14:59:59Z')) === '2030-09-10', 'JST before midnight');
    check(raos_local_reader_guides_today(new DateTimeImmutable('2030-09-10T15:00:00Z')) === '2030-09-11', 'JST midnight');
}

define('WP_CLI', true);
define('OBJECT', 'OBJECT');
class WP_CLI { static function error($message) { throw new RuntimeException($message); } }
class WP_Post {
    public $ID, $post_type = 'post', $post_status = 'publish', $post_password = '', $post_name,
        $post_title, $post_excerpt, $post_content;
    function __construct(array $row) { foreach ($row as $key => $value) { $this->$key = $value; } }
}
function wp_strip_all_tags($text) { return strip_tags($text); }
function apply_filters($name, $value, ...$args) { return $value; }
function wp_allowed_protocols() { return ['http', 'https', 'mailto']; }
require '/usr/src/wordpress/wp-includes/class-wp-token-map.php';
foreach (glob('/usr/src/wordpress/wp-includes/html-api/*.php') as $core_file) {
    if (basename($core_file) !== 'class-wp-html-processor.php') { require_once $core_file; }
}
require '/usr/src/wordpress/wp-includes/kses.php';
function wp_slash($data) { return is_array($data) ? array_map('wp_slash', $data) : (is_string($data) ? addslashes($data) : $data); }
function unslash($data) { return is_array($data) ? array_map('unslash', $data) : (is_string($data) ? stripslashes($data) : $data); }
function get_post($id) { return $GLOBALS['posts'][$id] ?? null; }
function get_post_type($id) { return get_post($id)->post_type ?? null; }
function get_post_status($id) { return is_object($id) ? $id->post_status : (get_post($id)->post_status ?? null); }
function get_post_field($field, $id, ...$args) { return get_post($id)->$field ?? ''; }
function get_post_meta($id, $key, ...$args) { return $GLOBALS['meta'][$id][$key] ?? ''; }
function update_post_meta($id, $key, $value) { $GLOBALS['meta'][$id][$key] = unslash($value); return true; }
function get_page_by_path($slug, $output, $types) {
    foreach ($GLOBALS['posts'] ?? [] as $post) {
        if ($post->post_name === $slug && in_array($post->post_type, (array) $types, true)) { return $post; }
    }
    return null;
}
function wp_unique_post_slug($slug, $id, ...$args) {
    $post = get_page_by_path($slug, OBJECT, ['post', 'page', 'attachment']);
    return ($GLOBALS['force_suffix'] ?? false) || ($post && $post->ID !== $id) ? $slug . '-2' : $slug;
}
function wp_insert_post($data, ...$args) {
    $data = unslash($data);
    $id = $data['ID'] ?? count($GLOBALS['posts'] ?? []) + 501;
    $data['ID'] = $id;
    unset($data['post_author'], $data['post_category'], $data['comment_status'], $data['ping_status']);
    $GLOBALS['posts'][$id] = new WP_Post($data);
    $GLOBALS['writes'] = ($GLOBALS['writes'] ?? 0) + 1;
    return $id;
}
function get_permalink($post) { return home_url('/' . (is_object($post) ? $post->post_name : get_post($post)->post_name) . '/') . ($GLOBALS['route_suffix'] ?? ''); }
function term_exists(...$args) { return ['term_id' => 88]; }
function is_wp_error($value) { return false; }
function esc_html($value) { return htmlspecialchars($value, ENT_QUOTES); }
function esc_attr($value) { return esc_html($value); }
function esc_url($value) { return esc_html($value); }
function get_post_modified_time(...$args) { return '2026年9月5日'; }
function is_singular(...$args) { return $GLOBALS['singular'] ?? true; }
function in_the_loop() { return true; }
function is_main_query() { return true; }
function get_the_ID() { return $GLOBALS['current_post_id'] ?? 0; }
function get_queried_object_id() { return get_the_ID(); }

// Import real theme functions and stub only unrelated asset/snapshot services.
$theme_path = __DIR__ . '/../../changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/functions.php';
$theme = file_get_contents($theme_path);
function load_theme_function($name) {
    $source = $GLOBALS['theme'];
    $start = strpos($source, 'function ' . $name . '(');
    check($start !== false, 'theme function missing: ' . $name);
    $end = strpos($source, "\n}", $start) + 2;
    eval(substr($source, $start, $end - $start));
}
foreach (['kurashinoshirube_has_exact_keys', 'kurashinoshirube_article_bindings', 'kurashinoshirube_local_preview_origin', 'kurashinoshirube_is_local_preview',
    'kurashinoshirube_local_preview_article_identity', 'kurashinoshirube_direct_article_snapshot', 'kurashinoshirube_public_article_identity',
    'kurashinoshirube_published_reader_guides', 'kurashinoshirube_reader_hubs', 'kurashinoshirube_request_cache', 'kurashinoshirube_reader_hub_registration',
    'kurashinoshirube_reader_hub_page', 'kurashinoshirube_resolve_reader_hub_page', 'kurashinoshirube_flush_reader_hub_page_cache', 'kurashinoshirube_reader_hub_title',
    'kurashinoshirube_reader_hub_parent_slug', 'kurashinoshirube_reader_eligible_posts', 'kurashinoshirube_reader_category_label',
    'kurashinoshirube_reader_article_category', 'kurashinoshirube_reader_hub_content', 'kurashinoshirube_reader_hub_page_head', 'kurashinoshirube_reader_hub_url',
    'kurashinoshirube_reader_guide_card', 'kurashinoshirube_reader_journeys', 'kurashinoshirube_reader_group_cards',
    'kurashinoshirube_reader_journey_stage', 'kurashinoshirube_reader_journey_shelves', 'kurashinoshirube_reader_journey_shortcuts',
    'kurashinoshirube_enqueue_local_running_cost', 'kurashinoshirube_verified_asset_uri',
    'kurashinoshirube_public_listing_post_is_eligible', 'kurashinoshirube_public_listing_excluded_post_ids'] as $name) {
    load_theme_function($name);
}
define('KURASHINOSHIRUBE_EDITORIAL_V2_ROOT', '<div class="raos-editorial-v2">');
define('KURASHINOSHIRUBE_LOCAL_COST_ASSET_PATH', 'assets/local-running-cost.js');
preg_match("/const KURASHINOSHIRUBE_LOCAL_COST_ASSET_SHA256 = '([a-f0-9]{64})';/", $theme, $cost_digest);
define('KURASHINOSHIRUBE_LOCAL_COST_ASSET_SHA256', $cost_digest[1]);
define('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION', 'test-revision');
function wp_enqueue_script($handle, ...$args) { $GLOBALS['enqueued_scripts'][$handle] = $args; }
function untrailingslashit($value) { return rtrim($value, '/'); }
function get_stylesheet_directory() { return ($GLOBALS['asset_valid'] ?? true) ? dirname($GLOBALS['theme_path']) : '/missing-theme'; }
function get_stylesheet_directory_uri() { return home_url('/wp-content/themes/kurashinoshirube-child'); }
function wp_parse_url($value) { return parse_url($value); }
function kurashinoshirube_editorial_navigation() {
    return json_decode(file_get_contents(dirname($GLOBALS['theme_path']) . '/assets/editorial-navigation.v3.json'), true);
}
function kurashinoshirube_editorial_v2_publication_bindings() { return kurashinoshirube_article_bindings(); }
function kurashinoshirube_bound_post_snapshot(...$args) { return null; }
function kurashinoshirube_published_editorial_v2_identity(...$args) { return null; }
function kurashinoshirube_post_has_editorial_v2_root($id) { return str_starts_with(get_post_field('post_content', $id), KURASHINOSHIRUBE_EDITORIAL_V2_ROOT); }
function kurashinoshirube_is_clean_text($value, ...$args) { return is_string($value) && trim($value) !== ''; }
function kurashinoshirube_article_visual_asset(...$args) { return null; }
function kurashinoshirube_stored_guide_role(...$args) { return '比較・選び方ガイド'; }

if ($without_plugin) {
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'no calculator asset without local plugin');
    check(!function_exists('raos_local_reader_guide_identity'), 'plugin absent');
    check(count(kurashinoshirube_article_bindings()) === 10, 'plugin absent fixed ten');
    check(kurashinoshirube_reader_hubs() === kurashinoshirube_editorial_navigation()['reader_navigation']['hubs'], 'plugin absent hubs identical');
    check(kurashinoshirube_reader_eligible_posts(['test-guide-1']) === [], 'plugin absent no new guides');
    $GLOBALS['posts'][90] = new WP_Post(['ID' => 90, 'post_name' => 'unrelated', 'post_content' => 'ordinary body']);
    check(kurashinoshirube_public_listing_post_is_eligible(90, 'unrelated'), 'unrelated prior behavior retained');
    check(!kurashinoshirube_public_listing_post_is_eligible(90, 'raos-review-test'), 'review exclusion retained');
    echo "local reader guide plugin-absent fallback: PASS\n";
    exit;
}

$fixture = ['schema' => 'RAOS_LOCAL_READER_GUIDES_V1', 'publication_authority' => false, 'articles' => [],
    'blocked' => [['article_id' => 'blocked-comparison', 'issues' => ['evidence.required']]]];
for ($n = 1; $n <= 5; $n++) {
    $html = '<div class="raos-editorial-v2"><span data-raos-article-id="test-guide-' . $n . '" hidden></span><p>Guide \\ test</p></div>';
    $fixture['articles'][] = ['article_id' => 'test-guide-' . $n, 'local_slug' => 'local-preview-test-guide-' . $n,
        'article_type' => 'guide', 'title' => 'Guide ' . $n, 'dek' => 'Check the installation.', 'category' => 'kitchen',
        'purposes' => ['small-space', 'without-installation'], 'html' => $html,
        'content_sha256' => hash('sha256', $html), 'checked_at' => '2026-09-05'];
}
$articles = raos_local_reader_guides_validate($fixture);
check(count($articles ?? []) === 5, 'five valid ready guides');
$future = $fixture;
$future['articles'][0]['checked_at'] = (new DateTimeImmutable('tomorrow', new DateTimeZone('Asia/Tokyo')))->format('Y-m-d');
check(raos_local_reader_guides_validate($future) === null, 'future Japanese confirmation day rejected');
$bad = $fixture; $bad['publication_authority'] = true;
check(raos_local_reader_guides_validate($bad) === null, 'publication authority rejected');
foreach (['local_slug' => 'production-route', 'article_type' => 'comparison', 'category' => 'travel',
    'content_sha256' => str_repeat('0', 64), 'checked_at' => '2026-02-30', 'title' => '<b>Title</b>'] as $key => $value) {
    $bad = $fixture; $bad['articles'][0][$key] = $value;
    check(raos_local_reader_guides_validate($bad) === null, 'reject invalid ' . $key);
}
$bad = $fixture; $bad['articles'][1] = $bad['articles'][0];
check(raos_local_reader_guides_validate($bad) === null, 'duplicate routes rejected');
$bad = $fixture; $bad['blocked'][0]['article_id'] = 'test-guide-1';
check(raos_local_reader_guides_validate($bad) === null, 'blocked article cannot be ready');
$bad = $fixture; $bad['articles'][0]['local_slug'] = array_values(kurashinoshirube_article_bindings())[0]['local_slug'];
check(raos_local_reader_guides_validate($bad) === null, 'fixed portfolio route collision rejected');

$fixture_path = '/var/www/raos-local-preview/fixtures/reader-guides.v1.json';
mkdir(dirname($fixture_path), 0700, true);
file_put_contents($fixture_path, json_encode($fixture));
check(raos_local_reader_guides_fixture() === $articles, 'exact mounted fixture loaded');
$original_bindings = kurashinoshirube_article_bindings();
check(count($original_bindings) === 10, 'fixed portfolio remains ten');

// A collision in the last entry must prevent even the first insert.
$GLOBALS['posts'][90] = new WP_Post(['ID' => 90, 'post_name' => 'local-preview-test-guide-5', 'post_content' => 'foreign']);
try { raos_local_reader_guides_seed($articles, 1); throw new LogicException('foreign overwrite allowed'); }
catch (RuntimeException $error) { check($error->getMessage() === 'RAOS_LOCAL_READER_GUIDES_FOREIGN_OR_CHANGED_POST', 'foreign collision error'); }
check(($GLOBALS['writes'] ?? 0) === 0 && get_post(90)->post_content === 'foreign', 'preflight protects foreign content');
$GLOBALS['posts'] = [];
$GLOBALS['force_suffix'] = true;
try { raos_local_reader_guides_seed($articles, 1); throw new LogicException('slug suffix allowed'); }
catch (RuntimeException $error) { check($error->getMessage() === 'RAOS_LOCAL_READER_GUIDES_FOREIGN_OR_CHANGED_POST', 'slug uniqueness enforced'); }
$GLOBALS['force_suffix'] = false;
check(raos_local_reader_guides_seed($articles, 1) === 5, 'seed five');
$seeded_ids = array_column(raos_local_reader_guides_bindings(), 'post_id');
check(count(array_unique($seeded_ids)) === 5 && min($seeded_ids) > 500, 'generated local IDs');
check(raos_local_reader_guides_seed($articles, 1) === 5, 'idempotent seed');
check(array_column(raos_local_reader_guides_bindings(), 'post_id') === $seeded_ids, 'repeat seed keeps IDs');
check(raos_local_reader_guide_count() === 5, 'separate guide count');
check(kurashinoshirube_article_bindings() === $original_bindings, 'fixed bindings unchanged');
check(count(kurashinoshirube_reader_eligible_posts(array_keys($articles))) === 5, 'hub eligibility');
foreach (kurashinoshirube_reader_hubs() as $hub) {
    $GLOBALS['posts'][900 + count($GLOBALS['posts'])] = new WP_Post(['ID' => 900 + count($GLOBALS['posts']), 'post_type' => 'page',
        'post_name' => $hub['slug'], 'post_title' => $hub['label'], 'post_excerpt' => $hub['description'],
        'post_content' => kurashinoshirube_reader_hub_content($hub['slug'])]);
    $included = in_array('test-guide-1', $hub['article_ids'], true);
    check($included === in_array($hub['slug'], ['categories', 'purposes', 'guides', 'updates', 'kitchen', 'small-space', 'without-installation']), 'exact hub membership ' . $hub['slug']);
}
$id = $seeded_ids[0];
check(kurashinoshirube_public_article_identity($id)['article_id'] === 'test-guide-1', 'shared identity');
check(kurashinoshirube_reader_article_category($id)['url'] === home_url('/kitchen/'), 'article category navigation');
$card = kurashinoshirube_reader_guide_card(get_post($id));
check(str_contains($card, 'キッチン・家事 / 選び方ガイド') && str_contains($card, '/local-preview-test-guide-1/'), 'guide card metadata and local link');
check(str_contains(kurashinoshirube_reader_group_cards('category'), '5記事を読む'), 'category card count');
check(str_contains(kurashinoshirube_reader_group_cards('category'), '>食洗機</span>'), 'product name is the category card title');
check(kurashinoshirube_reader_journey_stage('dishwasher-installation-measurement') === 'conditions', 'installation belongs to conditions');
check(kurashinoshirube_reader_journey_stage('dishwasher-running-cost') === 'purchase', 'cost belongs to purchase checks');
check(kurashinoshirube_reader_journey_stage('st1704-countertop-dishwasher-for-small-households') === 'comparison', 'comparison supports direct entry');
$journey_posts = kurashinoshirube_reader_eligible_posts(array_keys($articles));
$shelves = kurashinoshirube_reader_journey_shelves($journey_posts);
check(substr_count($shelves, 'class="raos-guide-card"') === 5, 'every eligible post appears in exactly one shelf');
$shortcuts = kurashinoshirube_reader_journey_shortcuts($journey_posts, ['test-guide-1' => '条件を確認する', 'unwritten-guide' => 'まだない記事']);
check(str_contains($shortcuts, '/local-preview-test-guide-1/') && !str_contains($shortcuts, 'まだない記事'), 'shortcuts omit unavailable proposals');
check(kurashinoshirube_public_listing_post_is_eligible($id, get_post($id)->post_name), 'search listing accepts valid guide');
check(!kurashinoshirube_public_listing_post_is_eligible($id, 'wrong-route'), 'wrong supplied route excluded');

$original_post = clone get_post($id);
foreach (['post_content' => 'tampered', 'post_name' => 'foreign-route', 'post_title' => 'wrong title',
    'post_excerpt' => 'wrong excerpt', 'post_password' => 'secret', 'post_status' => 'draft'] as $field => $value) {
    get_post($id)->$field = $value;
    check(raos_local_reader_guide_identity($id) === null, 'reject changed ' . $field);
    check(!kurashinoshirube_public_listing_post_is_eligible($id, get_post($id)->post_name), 'listing rejects changed ' . $field);
    check(kurashinoshirube_reader_guide_card(get_post($id)) === '', 'card rejects changed ' . $field);
    check(kurashinoshirube_reader_journey_shortcuts([get_post($id)], ['test-guide-1' => '条件を確認する']) === '', 'shortcut rejects changed ' . $field);
    $GLOBALS['posts'][$id] = clone $original_post;
}
$GLOBALS['meta'][$id]['_raos_local_reader_guide_v1']['checked_at'] = '2000-01-01';
check(raos_local_reader_guide_identity($id) === null, 'metadata tampering rejected');
try { raos_local_reader_guides_seed($articles, 1); throw new LogicException('changed metadata overwritten'); }
catch (RuntimeException $error) { check($error->getMessage() === 'RAOS_LOCAL_READER_GUIDES_FOREIGN_OR_CHANGED_POST', 'changed metadata refusal'); }
$GLOBALS['meta'][$id]['_raos_local_reader_guide_v1'] = raos_local_reader_guide_metadata($articles['test-guide-1']);
$GLOBALS['route_suffix'] = '?foreign=1';
check(raos_local_reader_guide_identity($id) === null, 'nonexact permalink rejected');
$GLOBALS['route_suffix'] = '';
$bad = $fixture; $bad['articles'][0]['html'] .= 'drift';
file_put_contents($fixture_path, json_encode($bad));
check(raos_local_reader_guide_count() === 0, 'fixture drift closes guide set');
file_put_contents($fixture_path, json_encode($fixture));
$GLOBALS['environment'] = 'production';
check(raos_local_reader_guide_count() === 0 && kurashinoshirube_local_preview_article_identity($id) === null, 'nonlocal disabled');
$GLOBALS['environment'] = 'local';
$GLOBALS['origin'] = 'https://kurashinoshirube.com';
check(!raos_local_reader_guides_boundary(), 'production origin rejected');
unset($GLOBALS['origin']);
$GLOBALS['options']['raos_mixed_preview_policy_heads_v1'] = [];
check(raos_local_reader_guide_count() === 0, 'mixed metadata disabled');
check(kurashinoshirube_reader_hubs() === kurashinoshirube_editorial_navigation()['reader_navigation']['hubs'], 'mixed hubs unchanged');
unset($GLOBALS['options']['raos_mixed_preview_policy_heads_v1']);
putenv('RAOS_PREVIEW_PUBLICATION_PROFILE=verified-incremental');
check(!raos_local_reader_guides_boundary(), 'mixed seed environment disabled');
putenv('RAOS_PREVIEW_PUBLICATION_PROFILE');

// Search exclusions retain the twenty-row SQL cap and separately check known IDs.
class TestDB {
    public $posts = 'wp_posts', $last_error = '', $query, $params;
    function esc_like($value) { return addcslashes($value, '_%'); }
    function prepare($query, $params) { $this->query = $query; $this->params = $params; return $query; }
    function get_results($query) { return []; }
}
$GLOBALS['wpdb'] = new TestDB();
get_post($id)->post_content = 'tampered without editorial root';
check(kurashinoshirube_public_listing_excluded_post_ids() === [$id], 'search excludes tampered bound ID even without root');
check(str_contains($GLOBALS['wpdb']->query, 'AND ID NOT IN (%d, %d, %d, %d, %d)'), 'local ID query is bounded');
check(end($GLOBALS['wpdb']->params) === 21, 'twenty rows plus sentinel unchanged');
$ready_path = __DIR__ . '/../../changes/wordpress-local-preview-v1/fixtures/reader-guides.v1.json';
if (is_file($ready_path)) {
    $ready = raos_local_reader_guides_validate(json_decode(file_get_contents($ready_path), true));
    check(is_array($ready) && count($ready) === 5, 'actual generated five-guide fixture passes core KSES and validation');
    file_put_contents($fixture_path, file_get_contents($ready_path));
    $GLOBALS['posts'] = []; $GLOBALS['options'] = []; $GLOBALS['meta'] = [];
    raos_local_reader_guides_seed($ready, 1);
    $cost_id = raos_local_reader_guides_bindings()['dishwasher-running-cost']['post_id'];
    $GLOBALS['current_post_id'] = $cost_id;
    kurashinoshirube_enqueue_local_running_cost();
    check(isset($GLOBALS['enqueued_scripts']['kurashinoshirube-local-running-cost']), 'bound local cost guide enqueues enhancement');
    $GLOBALS['enqueued_scripts'] = [];
    $GLOBALS['singular'] = false;
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'archive ID collision cannot enqueue calculator');
    $GLOBALS['singular'] = true;
    check(kurashinoshirube_verified_asset_uri(KURASHINOSHIRUBE_LOCAL_COST_ASSET_PATH, str_repeat('0', 64), true) === null, 'real verifier rejects incorrect digest');
    $GLOBALS['asset_valid'] = false;
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'invalid asset integrity stops enhancement');
    $GLOBALS['asset_valid'] = true;
    $original_cost = get_post($cost_id)->post_content;
    get_post($cost_id)->post_content .= 'changed';
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'changed guide content cannot enqueue calculator');
    get_post($cost_id)->post_content = $original_cost;
    $GLOBALS['environment'] = 'production';
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'production cannot enqueue calculator');
    $GLOBALS['environment'] = 'local';
    $GLOBALS['current_post_id'] = raos_local_reader_guides_bindings()['dishwasher-cleaning-guide']['post_id'];
    kurashinoshirube_enqueue_local_running_cost();
    check(empty($GLOBALS['enqueued_scripts']), 'another guide cannot enqueue calculator');
    foreach (['st1704-countertop-dishwasher-for-small-households', 'solota-vs-rakua-mini-plus'] as $source_id) {
        $binding = $original_bindings[$source_id];
        $body = file_get_contents(dirname($ready_path) . '/articles/' . $binding['slug'] . '.html');
        $GLOBALS['posts'][2001] = new WP_Post(['ID' => 2001, 'post_name' => $binding['local_slug'], 'post_content' => $body]);
        $GLOBALS['current_post_id'] = 2001;
        $linked = raos_local_reader_guide_contextual_links($body);
        check(substr_count($linked, 'data-raos-local-reader-related="v1"') === 1, 'one contextual group ' . $source_id);
        preg_match('#<aside[^>]*data-raos-local-reader-related="v1".*?</aside>#s', $linked, $group);
        check(substr_count($group[0], '<a href="http://127.0.0.1:18080/local-preview-') === 3, 'three validated local contextual links');
        check(get_post(2001)->post_content === $body, 'stored source remains unchanged');
        check(raos_local_reader_guide_contextual_links($linked) === $linked, 'contextual filter idempotent');
        $GLOBALS['environment'] = 'production';
        check(raos_local_reader_guide_contextual_links($body) === $body, 'contextual links absent outside local');
        $GLOBALS['environment'] = 'local';
    }
    $target_id = raos_local_reader_guides_bindings()['dishwasher-detergent-guide']['post_id'];
    get_post($target_id)->post_content .= 'drift';
    $linked = raos_local_reader_guide_contextual_links($body);
    preg_match('#<aside[^>]*data-raos-local-reader-related="v1".*?</aside>#s', $linked, $group);
    check(substr_count($group[0], '<a ') === 2 && !str_contains($group[0], 'local-preview-dishwasher-detergent-guide/'), 'tampered contextual target removed');
    get_post(raos_local_reader_guides_bindings()['dishwasher-cleaning-guide']['post_id'])->post_status = 'draft';
    check(raos_local_reader_guide_contextual_links($body) === $body, 'fewer than two eligible links suppress group');

}
echo "local reader guide integration: PASS (validation, seed, ownership, identity, hubs, cards, listing, boundaries)\n";
