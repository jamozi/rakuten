<?php
/** Backup restore into a fresh, portless scratch database; never the preview. */
if (! defined('WP_CLI') || WP_CLI !== true) { exit; }
if (! defined('RAOS_LOCAL_RESTORE_SCRATCH') || RAOS_LOCAL_RESTORE_SCRATCH !== true
    || ! defined('WP_HTTP_BLOCK_EXTERNAL') || WP_HTTP_BLOCK_EXTERNAL !== true
    || ! defined('WP_POST_REVISIONS') || WP_POST_REVISIONS !== false
    || wp_get_environment_type() !== 'local' || DB_NAME !== 'scratch_wordpress' || DB_HOST !== 'database'
    || home_url('/') !== 'http://scratch.wordpress.invalid/' || site_url('/') !== 'http://scratch.wordpress.invalid/'
    || defined('RAOS_LOCAL_PREVIEW') || get_option('raos_scratch_restore_seed_hash', false) !== false) {
    WP_CLI::error('RAOS_SCRATCH_BOUNDARY_INVALID');
}
function scratch_read(string $path): string {
    if (! is_file($path) || is_link($path) || ! is_readable($path) || filesize($path) > 1048576) { WP_CLI::error('RAOS_SCRATCH_FILE_INVALID'); }
    $bytes = file_get_contents($path);
    if (! is_string($bytes)) { WP_CLI::error('RAOS_SCRATCH_FILE_INVALID'); }
    return $bytes;
}
function scratch_canonical($value) {
    if (is_array($value)) {
        if (! array_is_list($value)) { ksort($value, SORT_STRING); }
        foreach ($value as $key => $child) { $value[$key] = scratch_canonical($child); }
    } elseif (is_object($value)) {
        $entries = get_object_vars($value); ksort($entries, SORT_STRING);
        foreach ($entries as $key => $child) { $entries[$key] = scratch_canonical($child); }
        $value = (object) $entries;
    }
    return $value;
}
$root = '/var/www/raos-scratch-backup';
$raw = scratch_read($root . '/scratch-seed.v1.json');
$hash = hash('sha256', $raw);
$environment = getenv('RAOS_SCRATCH_RESTORE_ENVIRONMENT');
$seed = json_decode($raw, true, 32);
if (is_link($root) || realpath($root) !== $root || ! is_array($seed)
    || ! is_string($environment) || preg_match('/\A[a-f0-9]{8}-[a-f0-9]{12}\z/D', $environment) !== 1
    || getenv('RAOS_SCRATCH_SEED_SHA256') !== $hash || ($seed['environment_id'] ?? null) !== $environment
    || ($seed['schema'] ?? null) !== 'RAOS_WORDPRESS_SCRATCH_RESTORE_SEED_V1'
    || ($seed['publication_profile'] ?? null) !== 'local-scratch-restore-rehearsal'
    || ($seed['publication_authority'] ?? null) !== false || ($seed['production_authority'] ?? null) !== false
    || ($seed['scratch_only'] ?? null) !== true || ! is_array($seed['documents'] ?? null) || count($seed['documents']) !== 14) {
    WP_CLI::error('RAOS_SCRATCH_SEED_INVALID');
}
$prepared = array(); $original_ids = array(); $term_rows = array(); $page_slugs = array();
foreach ($seed['documents'] as $slug => $row) {
    if (! is_string($slug) || preg_match('/\A[a-z0-9]+(?:-[a-z0-9]+)*\z/D', $slug) !== 1
        || ! is_array($row) || ($row['production_slug'] ?? null) !== $slug || ($row['local_slug'] ?? null) !== $slug
        || ! is_int($row['production_id'] ?? null) || $row['production_id'] <= 0 || in_array($row['production_id'], $original_ids, true)
        || ! in_array($row['post_type'] ?? null, array('post', 'page'), true) || ($row['status'] ?? null) !== 'publish'
        || ! is_string($row['title'] ?? null) || ! is_string($row['excerpt'] ?? null)
        || ! is_array($row['dates'] ?? null) || count($row['dates']) !== 4
        || ! is_array($row['taxonomies'] ?? null) || ! is_array($row['taxonomy_ids'] ?? null)
        || ! in_array($row['taxonomy_ids_encoding'] ?? null, array('object', 'array'), true) || ($row['media_ids'] ?? null) !== array()) {
        WP_CLI::error('RAOS_SCRATCH_DOCUMENT_INVALID');
    }
    $original_ids[] = $row['production_id'];
    if ($row['post_type'] === 'page') { $page_slugs[] = $slug; }
    foreach (array('date', 'date_gmt', 'modified', 'modified_gmt') as $field) {
        $date = $row['dates'][$field] ?? null;
        $parsed = is_string($date) ? DateTimeImmutable::createFromFormat('!Y-m-d H:i:s', $date, new DateTimeZone('UTC')) : false;
        if (! ($parsed instanceof DateTimeImmutable) || $parsed->format('Y-m-d H:i:s') !== $date) { WP_CLI::error('RAOS_SCRATCH_DATE_INVALID'); }
    }
    foreach ($row['taxonomies'] as $taxonomy => $terms) {
        if (! in_array($taxonomy, array('category', 'post_tag'), true) || ! is_array($terms)) { WP_CLI::error('RAOS_SCRATCH_TERM_INVALID'); }
        foreach ($terms as $term) {
            if (! is_array($term) || ! is_int($term['id'] ?? null) || $term['id'] <= 0 || ($term['parent'] ?? null) !== 0
                || ! is_string($term['name'] ?? null) || ! is_string($term['slug'] ?? null)
                || preg_match('/\A(?:[a-z0-9_-]|%[0-9a-f]{2})+\z/D', $term['slug']) !== 1) { WP_CLI::error('RAOS_SCRATCH_TERM_INVALID'); }
            $key = $taxonomy . ':' . $term['id'];
            if (isset($term_rows[$key]) && $term_rows[$key] !== array('taxonomy' => $taxonomy, 'term' => $term)) { WP_CLI::error('RAOS_SCRATCH_TERM_CONFLICT'); }
            $term_rows[$key] = array('taxonomy' => $taxonomy, 'term' => $term);
        }
    }
    $content = '';
    if (($row['content_file'] ?? null) !== null) {
        $path = $root . '/content/' . $slug . '.html';
        if ($row['content_file'] !== 'content/' . $slug . '.html' || is_link($root . '/content')
            || dirname((string) realpath($path)) !== $root . '/content') { WP_CLI::error('RAOS_SCRATCH_CONTENT_PATH_INVALID'); }
        $content = scratch_read($path);
    }
    if (hash('sha256', $content) !== ($row['content_sha256'] ?? null) || wp_kses_post($content) !== $content) { WP_CLI::error('RAOS_SCRATCH_BODY_INVALID'); }
    $prepared[$slug] = array('row' => $row, 'content' => $content);
}
sort($page_slugs); sort($original_ids);
if ($page_slugs !== array('about-ad-policy', 'comparison-policy', 'home', 'privacy-policy')) { WP_CLI::error('RAOS_SCRATCH_TARGET_INVALID'); }

// Only untouched WordPress installer defaults may exist in this fresh database.
$defaults = get_posts(array('post_type' => 'any', 'post_status' => array('publish', 'draft', 'private', 'pending', 'future', 'trash', 'inherit'), 'numberposts' => -1));
if (count($defaults) > 3) { WP_CLI::error('RAOS_SCRATCH_NOT_EMPTY'); }
foreach ($defaults as $post) {
    if (! in_array((int) $post->ID, array(1, 2, 3), true) || ! in_array($post->post_name, array('hello-world', 'sample-page', 'privacy-policy'), true)) { WP_CLI::error('RAOS_SCRATCH_NOT_EMPTY'); }
}
global $wpdb;
if ($wpdb->prefix !== 'wp_' || array_map('intval', $wpdb->get_col('SELECT term_id FROM ' . $wpdb->terms)) !== array(1)) { WP_CLI::error('RAOS_SCRATCH_NOT_EMPTY'); }
foreach ($defaults as $post) { if (! wp_delete_post((int) $post->ID, true)) { WP_CLI::error('RAOS_SCRATCH_DEFAULT_REMOVAL_FAILED'); } }
// Fixed table identities, fresh scratch boundary above; original term IDs are restored.
$wpdb->delete($wpdb->term_taxonomy, array('term_id' => 1), array('%d'));
$wpdb->delete($wpdb->terms, array('term_id' => 1), array('%d'));
foreach ($term_rows as $entry) {
    $term = $entry['term'];
    if ($wpdb->insert($wpdb->terms, array('term_id' => $term['id'], 'name' => $term['name'], 'slug' => $term['slug'], 'term_group' => 0), array('%d', '%s', '%s', '%d')) !== 1
        || $wpdb->insert($wpdb->term_taxonomy, array('term_id' => $term['id'], 'taxonomy' => $entry['taxonomy'], 'description' => '', 'parent' => 0, 'count' => 0), array('%d', '%s', '%s', '%d', '%d')) !== 1) { WP_CLI::error('RAOS_SCRATCH_TERM_IMPORT_FAILED'); }
    clean_term_cache($term['id'], $entry['taxonomy']);
    if ($entry['taxonomy'] === 'category') { update_option('default_category', $term['id']); }
}
add_filter('wp_insert_post_data', static function (array $data) use ($prepared): array {
    $entry = $prepared[$data['post_name'] ?? ''] ?? null;
    if (is_array($entry)) { foreach ($entry['row']['dates'] as $field => $date) { $data['post_' . $field] = $date; } }
    return $data;
}, PHP_INT_MAX);
foreach ($prepared as $target) {
    $row = $target['row'];
    $data = array('import_id' => $row['production_id'], 'post_type' => $row['post_type'], 'post_status' => 'publish', 'post_name' => $row['production_slug'], 'post_title' => $row['title'], 'post_excerpt' => $row['excerpt'], 'post_content' => $target['content'], 'post_author' => 1, 'comment_status' => 'closed', 'ping_status' => 'closed');
    foreach ($row['dates'] as $field => $date) { $data['post_' . $field] = $date; }
    $id = wp_insert_post(wp_slash($data), true);
    if (is_wp_error($id) || (int) $id !== $row['production_id']) { WP_CLI::error('RAOS_SCRATCH_ORIGINAL_ID_NOT_RESTORED'); }
    foreach ($row['taxonomy_ids'] as $taxonomy => $ids) {
        if (! taxonomy_exists($taxonomy) || is_wp_error(wp_set_object_terms($id, $ids, $taxonomy, false))) { WP_CLI::error('RAOS_SCRATCH_TAXONOMY_NOT_RESTORED'); }
    }
}
$documents = array();
foreach ($prepared as $slug => $target) {
    $row = $target['row']; clean_post_cache($row['production_id']); $post = get_post($row['production_id']);
    $dates = array(); foreach (array('date', 'date_gmt', 'modified', 'modified_gmt') as $field) { $dates[$field] = $post->{'post_' . $field}; }
    $ids = array(); foreach ($row['taxonomy_ids'] as $taxonomy => $_expected) {
        $found = wp_get_object_terms($post->ID, $taxonomy, array('fields' => 'ids'));
        if (is_wp_error($found)) { WP_CLI::error('RAOS_SCRATCH_READBACK_FAILED'); }
        $ids[$taxonomy] = array_map('intval', $found); sort($ids[$taxonomy]);
    }
    if ($row['taxonomy_ids_encoding'] === 'object') { $ids = (object) $ids; }
    $terms = array(); foreach (array('category', 'post_tag') as $taxonomy) {
        $terms[$taxonomy] = array(); $found = wp_get_object_terms($post->ID, $taxonomy);
        if (is_wp_error($found)) { WP_CLI::error('RAOS_SCRATCH_READBACK_FAILED'); }
        foreach ($found as $term) { $terms[$taxonomy][] = array('id' => (int) $term->term_id, 'name' => $term->name, 'slug' => $term->slug, 'parent' => (int) $term->parent); }
        usort($terms[$taxonomy], static function (array $a, array $b): int { return $a['id'] <=> $b['id']; });
    }
    $projection = array('schema' => 'ContentDocumentV1', 'id' => (int) $post->ID, 'slug' => $post->post_name, 'post_type' => $post->post_type, 'status' => $post->post_status, 'title' => $post->post_title, 'excerpt' => $post->post_excerpt, 'block_markup' => $post->post_content, 'taxonomies' => $ids, 'media_ids' => array());
    $documents[$slug] = array('id' => (int) $post->ID, 'slug' => $post->post_name, 'post_type' => $post->post_type, 'status' => $post->post_status,
        'title_sha256' => hash('sha256', $post->post_title), 'excerpt_sha256' => hash('sha256', $post->post_excerpt), 'body_sha256' => hash('sha256', $post->post_content), 'dates' => $dates,
        'taxonomy_ids' => $ids, 'taxonomies' => $terms, 'media_ids' => array(), 'content_sha256' => hash('sha256', wp_json_encode(scratch_canonical($projection), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)));
}
$actual_ids = array_map('intval', get_posts(array('post_type' => array('post', 'page'), 'post_status' => 'any', 'numberposts' => -1, 'fields' => 'ids'))); sort($actual_ids);
if ($actual_ids !== $original_ids) { WP_CLI::error('RAOS_SCRATCH_ID_SET_MISMATCH'); }
update_option('raos_scratch_restore_seed_hash', $hash);
$readback = array('schema' => 'RAOS_WORDPRESS_SCRATCH_RESTORE_READBACK_V1', 'publication_profile' => 'local-scratch-restore-rehearsal', 'publication_authority' => false, 'production_authority' => false, 'scratch_only' => true, 'temporary_environment' => true, 'environment_id' => $environment, 'seed_sha256' => $hash, 'site_url' => 'http://scratch.wordpress.invalid', 'original_id_set' => $actual_ids, 'documents' => $documents);
$destination = $root . '/scratch-readback.v1.json';
if (file_exists($destination) || is_link($destination)) { WP_CLI::error('RAOS_SCRATCH_READBACK_ALREADY_EXISTS'); }
$descriptor = fopen($destination, 'x');
if (! is_resource($descriptor) || ! chmod($destination, 0600) || fwrite($descriptor, wp_json_encode($readback, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . "\n") === false) { WP_CLI::error('RAOS_SCRATCH_RECEIPT_WRITE_FAILED'); }
fclose($descriptor);
WP_CLI::success('RAOS_SCRATCH_READBACK_CAPTURED_14_ORIGINAL_DOCUMENTS');
