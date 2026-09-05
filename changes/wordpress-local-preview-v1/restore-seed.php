<?php
/** Restore captured stored fields in an existing isolated preview, never production. */

if (! defined('WP_CLI') || WP_CLI !== true) {
    http_response_code(404);
    exit;
}
if (! defined('RAOS_LOCAL_PREVIEW') || RAOS_LOCAL_PREVIEW !== true
    || ! defined('WP_HTTP_BLOCK_EXTERNAL') || WP_HTTP_BLOCK_EXTERNAL !== true
    || ! defined('RAOS_WORDPRESS_PREVIEW_ORIGIN')
    || ! is_string(RAOS_WORDPRESS_PREVIEW_ORIGIN)
    || preg_match('#\Ahttp://127\.0\.0\.1:[0-9]{4,5}\z#D', RAOS_WORDPRESS_PREVIEW_ORIGIN) !== 1
    || wp_get_environment_type() !== 'local'
    || home_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
    || site_url('/') !== RAOS_WORDPRESS_PREVIEW_ORIGIN . '/'
    || getenv('RAOS_PREVIEW_RESTORE_MODE') !== 'stored-fields'
) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_BOUNDARY_INVALID');
}

function raos_restore_fields(array $value, array $expected): bool
{
    $keys = array_keys($value);
    sort($keys);
    sort($expected);
    return $keys === $expected;
}

function raos_restore_read(string $path, int $maximum): string
{
    if (! is_file($path) || is_link($path) || ! is_readable($path)
        || filesize($path) > $maximum) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_FILE_INVALID');
    }
    $bytes = file_get_contents($path);
    if (! is_string($bytes)) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_FILE_INVALID');
    }
    return $bytes;
}

function raos_restore_hash($value): bool
{
    return is_string($value) && preg_match('/\A[a-f0-9]{64}\z/D', $value) === 1;
}

function raos_restore_inventory(): array
{
    $ids = get_posts(array('post_type' => array('post', 'page'), 'post_status' => 'any', 'numberposts' => -1, 'fields' => 'ids'));
    $ids = array_map('intval', $ids);
    sort($ids);
    return $ids;
}

function raos_restore_terms(array $rows, string $taxonomy): array
{
    $ids = array();
    foreach ($rows as $row) {
        $term = get_term_by('slug', $row['slug'], $taxonomy);
        if (! ($term instanceof WP_Term)) {
            $created = wp_insert_term($row['name'], $taxonomy, array('slug' => $row['slug'], 'parent' => 0));
            if (is_wp_error($created)) {
                WP_CLI::error('RAOS_LOCAL_RESTORE_TERM_FAILED');
            }
            $term = get_term((int) $created['term_id'], $taxonomy);
        }
        if (! ($term instanceof WP_Term) || $term->name !== $row['name']
            || $term->slug !== $row['slug'] || (int) $term->parent !== 0) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_TERM_COLLISION');
        }
        $ids[] = (int) $term->term_id;
    }
    return $ids;
}

$root = '/var/www/raos-local-restore';
if (is_link($root) || realpath($root) !== $root) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_ROOT_INVALID');
}
$preparation_bytes = raos_restore_read($root . '/preparation-binding.v1.json', 65536);
$preparation_hash = getenv('RAOS_PREVIEW_RESTORE_PREPARATION_SHA256');
if (! raos_restore_hash($preparation_hash) || hash('sha256', $preparation_bytes) !== $preparation_hash) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_PREPARATION_INVALID');
}
$preparation = json_decode($preparation_bytes, true, 32);
$seed_bytes = raos_restore_read($root . '/restoration-seed.v1.json', 1048576);
$seed = json_decode($seed_bytes, true, 32);
if (! is_array($preparation) || ! is_array($seed)
    || ($preparation['schema'] ?? null) !== 'RAOS_WORDPRESS_LOCAL_RESTORE_PREPARATION_V1'
    || ($seed['schema'] ?? null) !== 'RAOS_WORDPRESS_LOCAL_RESTORE_SEED_V1'
    || ($preparation['publication_profile'] ?? null) !== 'local-restore-rehearsal'
    || ($seed['publication_profile'] ?? null) !== 'local-restore-rehearsal'
    || ($preparation['publication_authority'] ?? null) !== false
    || ($seed['publication_authority'] ?? null) !== false
    || ($preparation['status'] ?? null) !== 'PREPARED_NOT_RESTORED'
    || ($preparation['incremental_preview_pass'] ?? null) !== false
    || ($preparation['requires_existing_local_rows'] ?? null) !== true
    || ($preparation['changes_theme_plugins_or_site_options'] ?? null) !== false
    || ($preparation['seed_sha256'] ?? null) !== hash('sha256', $seed_bytes)
    || ! raos_restore_hash($seed['source_snapshot_sha256'] ?? null)
    || ($seed['source_snapshot_sha256'] ?? null) !== ($preparation['source_snapshot_sha256'] ?? null)
    || ! is_array($seed['documents'] ?? null) || count($seed['documents']) !== 14
    || ($preparation['document_count'] ?? null) !== 14
    || ($preparation['article_count'] ?? null) !== 10
    || ($preparation['policy_count'] ?? null) !== 3 || ($preparation['home_count'] ?? null) !== 1
) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_PREPARATION_INVALID');
}

$prepared = array();
$production_ids = array();
$local_ids = array();
$post_count = 0;
$page_slugs = array();
$before_inventory = raos_restore_inventory();
$unchanged_options = array();
foreach (array('home', 'siteurl', 'show_on_front', 'page_on_front', 'page_for_posts', 'stylesheet', 'template', 'active_plugins') as $option) {
    $unchanged_options[$option] = get_option($option);
}
foreach ($seed['documents'] as $slug => $row) {
    if (! is_string($slug) || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $slug) !== 1
        || ! is_array($row) || ! raos_restore_fields($row, array('production_id', 'production_slug', 'local_slug', 'post_type', 'status', 'title', 'excerpt', 'content_file', 'content_sha256', 'source_content_sha256', 'dates', 'taxonomies'))
        || ($row['production_slug'] ?? null) !== $slug
        || ! is_int($row['production_id']) || $row['production_id'] <= 0
        || in_array($row['production_id'], $production_ids, true)
        || ! in_array($row['post_type'], array('post', 'page'), true) || $row['status'] !== 'publish'
        || $row['local_slug'] !== ($row['post_type'] === 'post' ? 'local-preview-' . $slug : $slug)
        || ! is_string($row['title']) || ! is_string($row['excerpt'])
        || ! raos_restore_hash($row['content_sha256']) || ! raos_restore_hash($row['source_content_sha256'])
        || ($preparation['body_sha256'][$slug] ?? null) !== $row['content_sha256']
        || ($preparation['source_content_sha256'][$slug] ?? null) !== $row['source_content_sha256']
        || ! is_array($row['dates']) || ! raos_restore_fields($row['dates'], array('date', 'date_gmt', 'modified', 'modified_gmt'))
        || ! is_array($row['taxonomies']) || ! raos_restore_fields($row['taxonomies'], array('category', 'post_tag'))
    ) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_DOCUMENT_INVALID');
    }
    $production_ids[] = $row['production_id'];
    if ($row['post_type'] === 'post') {
        ++$post_count;
    } else {
        $page_slugs[] = $slug;
    }
    foreach ($row['dates'] as $date) {
        $parsed = is_string($date) ? DateTimeImmutable::createFromFormat('!Y-m-d H:i:s', $date, new DateTimeZone('UTC')) : false;
        if (! ($parsed instanceof DateTimeImmutable) || $parsed->format('Y-m-d H:i:s') !== $date) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_DATE_INVALID');
        }
    }
    foreach (array(array('date', 'date_gmt'), array('modified', 'modified_gmt')) as $pair) {
        if (strtotime($row['dates'][$pair[0]] . ' UTC') - strtotime($row['dates'][$pair[1]] . ' UTC') !== 32400) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_DATE_INVALID');
        }
    }
    foreach ($row['taxonomies'] as $taxonomy => $terms) {
        if (! is_array($terms)) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_TERM_INVALID');
        }
        $term_slugs = array();
        foreach ($terms as $term) {
            if (! is_array($term) || ! raos_restore_fields($term, array('id', 'name', 'slug', 'parent'))
                || ! is_int($term['id']) || $term['id'] <= 0 || $term['parent'] !== 0
                || ! is_string($term['name']) || $term['name'] === '' || preg_match('/[<>\x00-\x1f]/', $term['name'])
                || ! is_string($term['slug']) || preg_match('/\A(?:[a-z0-9_-]|%[0-9a-f]{2})+\z/D', $term['slug']) !== 1
                || in_array($term['slug'], $term_slugs, true)) {
                WP_CLI::error('RAOS_LOCAL_RESTORE_TERM_INVALID');
            }
            $term_slugs[] = $term['slug'];
        }
    }
    $content = '';
    if ($row['content_file'] !== null) {
        $content_path = $root . '/content/' . $slug . '.html';
        if ($row['content_file'] !== 'content/' . $slug . '.html'
            || is_link($root . '/content') || dirname((string) realpath($content_path)) !== $root . '/content') {
            WP_CLI::error('RAOS_LOCAL_RESTORE_CONTENT_PATH_INVALID');
        }
        $content = raos_restore_read($content_path, 1048576);
    }
    if (hash('sha256', $content) !== $row['content_sha256'] || wp_kses_post($content) !== $content) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_CONTENT_INVALID');
    }
    $existing = get_page_by_path($row['local_slug'], OBJECT, $row['post_type']);
    if (! ($existing instanceof WP_Post)) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_EXISTING_ROW_REQUIRED_' . $slug);
    }
    if ($existing->post_status !== 'publish' || in_array((int) $existing->ID, $local_ids, true)) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_EXISTING_IDENTITY_INVALID_' . $slug);
    }
    $local_ids[] = (int) $existing->ID;
    $prepared[$slug] = array('row' => $row, 'content' => $content, 'local_id' => (int) $existing->ID);
}
sort($page_slugs);
if ($post_count !== 10 || $page_slugs !== array('about-ad-policy', 'comparison-policy', 'home', 'privacy-policy')) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_TARGET_INVALID');
}

// A partial rerun must not leave its predecessor's receipt at the current name.
// Preserve previous evidence by content-addressed rename, never delete it.
foreach (array('restoration-readback.v1.json', 'restoration-receipt.v1.json') as $name) {
    $current = $root . '/' . $name;
    if (file_exists($current) || is_link($current)) {
        $previous = raos_restore_read($current, 1048576);
        $archive = $root . '/previous-' . hash('sha256', $previous) . '-' . $name;
        if (is_link($archive) || (file_exists($archive) && raos_restore_read($archive, 1048576) !== $previous)
            || ! rename($current, $archive)) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_PREVIOUS_RECEIPT_INVALID');
        }
    }
}

// Preserve the captured dates despite core's usual modified-date update.
add_filter('wp_insert_post_data', static function (array $data, array $postarr) use ($prepared): array {
    foreach ($prepared as $target) {
        if (($postarr['ID'] ?? null) === $target['local_id']) {
            foreach ($target['row']['dates'] as $field => $date) {
                $data['post_' . $field] = $date;
            }
            break;
        }
    }
    return $data;
}, PHP_INT_MAX, 2);

foreach ($prepared as $target) {
    $row = $target['row'];
    $terms = array();
    foreach ($row['taxonomies'] as $taxonomy => $rows) {
        $terms[$taxonomy] = raos_restore_terms($rows, $taxonomy);
    }
    $data = array('ID' => $target['local_id'], 'post_type' => $row['post_type'], 'post_status' => $row['status'],
        'post_name' => $row['local_slug'], 'post_title' => $row['title'], 'post_excerpt' => $row['excerpt'], 'post_content' => $target['content']);
    foreach ($row['dates'] as $field => $date) {
        $data['post_' . $field] = $date;
    }
    $updated = wp_update_post(wp_slash($data), true);
    if (is_wp_error($updated) || (int) $updated !== $target['local_id']) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_UPDATE_FAILED');
    }
    foreach ($terms as $taxonomy => $ids) {
        if (is_wp_error(wp_set_object_terms($target['local_id'], $ids, $taxonomy, false))) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_TERM_FAILED');
        }
    }
}

$readback = array();
foreach ($prepared as $slug => $target) {
    clean_post_cache($target['local_id']);
    $post = get_post($target['local_id']);
    if (! ($post instanceof WP_Post)) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_READBACK_FAILED');
    }
    $dates = array();
    foreach (array('date', 'date_gmt', 'modified', 'modified_gmt') as $field) {
        $dates[$field] = $post->{'post_' . $field};
    }
    $terms = array();
    foreach (array('category', 'post_tag') as $taxonomy) {
        $observed = wp_get_object_terms($post->ID, $taxonomy);
        if (is_wp_error($observed)) {
            WP_CLI::error('RAOS_LOCAL_RESTORE_READBACK_FAILED');
        }
        $terms[$taxonomy] = array();
        foreach ($observed as $term) {
            $terms[$taxonomy][] = array('name' => $term->name, 'slug' => $term->slug, 'parent' => (int) $term->parent);
        }
        usort($terms[$taxonomy], static function (array $left, array $right): int { return strcmp($left['slug'], $right['slug']); });
    }
    $readback[$slug] = array('local_id' => (int) $post->ID, 'before_local_id' => $target['local_id'],
        'local_slug' => $post->post_name, 'post_type' => $post->post_type, 'status' => $post->post_status,
        'title_sha256' => hash('sha256', $post->post_title), 'excerpt_sha256' => hash('sha256', $post->post_excerpt),
        'body_sha256' => hash('sha256', $post->post_content), 'dates' => $dates, 'taxonomies' => $terms,
        'source_content_sha256' => $target['row']['source_content_sha256']);
}
if (raos_restore_inventory() !== $before_inventory) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_POST_INVENTORY_CHANGED');
}
foreach ($unchanged_options as $option => $before) {
    if (get_option($option) !== $before) {
        WP_CLI::error('RAOS_LOCAL_RESTORE_OPTIONS_CHANGED');
    }
}
$result = array('schema' => 'RAOS_WORDPRESS_LOCAL_RESTORE_READBACK_V1', 'publication_profile' => 'local-restore-rehearsal',
    'publication_authority' => false, 'preparation_sha256' => $preparation_hash, 'site_url' => RAOS_WORDPRESS_PREVIEW_ORIGIN,
    'local_only' => true, 'new_post_count' => 0, 'documents' => $readback);
$destination = $root . '/restoration-readback.v1.json';
if (is_link($destination)) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_RECEIPT_PATH_INVALID');
}
$temporary = tempnam($root, '.restore-readback-');
if (! is_string($temporary) || ! chmod($temporary, 0600)
    || file_put_contents($temporary, wp_json_encode($result, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n") === false
    || ! rename($temporary, $destination)) {
    WP_CLI::error('RAOS_LOCAL_RESTORE_RECEIPT_WRITE_FAILED');
}
WP_CLI::success('RAOS_LOCAL_RESTORE_READBACK_CAPTURED_14_DOCUMENTS_NOT_A_PREVIEW_PASS');
