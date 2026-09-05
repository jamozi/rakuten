<?php
/** Same-basename file replacement rehearsal; no theme activation or DB writes. */
if (! defined('WP_CLI') || WP_CLI !== true) { exit; }
function theme_restore_abort(string $code): void { throw new RuntimeException($code); }
if (! defined('RAOS_LOCAL_RESTORE_SCRATCH') || RAOS_LOCAL_RESTORE_SCRATCH !== true
    || ! defined('WP_HTTP_BLOCK_EXTERNAL') || WP_HTTP_BLOCK_EXTERNAL !== true
    || ! defined('WP_POST_REVISIONS') || WP_POST_REVISIONS !== false
    || wp_get_environment_type() !== 'local' || DB_NAME !== 'scratch_wordpress' || DB_HOST !== 'database'
    || home_url('/') !== 'http://scratch.wordpress.invalid/' || site_url('/') !== 'http://scratch.wordpress.invalid/'
    || defined('RAOS_LOCAL_PREVIEW') || ABSPATH !== '/var/www/html/') {
    WP_CLI::error('RAOS_SCRATCH_THEME_BOUNDARY_INVALID');
}
function theme_restore_read(string $path): string {
    if (! is_file($path) || is_link($path) || ! is_readable($path) || filesize($path) > 16777216) { theme_restore_abort('RAOS_SCRATCH_THEME_FILE_INVALID'); }
    $raw = file_get_contents($path);
    if (! is_string($raw)) { theme_restore_abort('RAOS_SCRATCH_THEME_FILE_INVALID'); }
    return $raw;
}
function theme_restore_canonical($value) {
    if (is_array($value)) {
        if (! array_is_list($value)) { ksort($value, SORT_STRING); }
        foreach ($value as $key => $item) { $value[$key] = theme_restore_canonical($item); }
    } elseif (is_object($value)) {
        $items = get_object_vars($value); ksort($items, SORT_STRING);
        foreach ($items as $key => $item) { $items[$key] = theme_restore_canonical($item); }
        $value = (object) $items;
    }
    return $value;
}
function theme_restore_json($value): string {
    $raw = wp_json_encode(theme_restore_canonical($value), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if (! is_string($raw)) { theme_restore_abort('RAOS_SCRATCH_THEME_JSON_INVALID'); }
    return $raw;
}
function theme_restore_package(string $raw): array {
    $package = json_decode($raw, true, 32);
    if (! is_array($package) || ($package['schema'] ?? null) !== 'RAOS_WORDPRESS_SCRATCH_THEME_PACKAGE_V1'
        || ($package['theme_slug'] ?? null) !== 'kurashinoshirube-child' || ! is_array($package['files'] ?? null)
        || count($package['files']) < 1 || count($package['files']) > 2048) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
    $files = array(); $manifest = array(); $seen = array(); $total = 0;
    foreach ($package['files'] as $row) {
        $path = $row['path'] ?? null; $size = $row['size'] ?? null; $encoded = $row['contents_b64'] ?? null;
        if (! is_string($path) || strlen($path) > 300 || preg_match('/\A[A-Za-z0-9._\/-]+\z/D', $path) !== 1 || $path[0] === '/'
            || array_intersect(explode('/', $path), array('', '.', '..')) || isset($seen[strtolower($path)])
            || ! is_int($size) || $size < 0 || $size > 8388608 || ! is_string($encoded)) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
        $bytes = base64_decode($encoded, true);
        if (! is_string($bytes) || strlen($bytes) !== $size || base64_encode($bytes) !== $encoded
            || hash('sha256', $bytes) !== ($row['sha256'] ?? null)) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
        $files[$path] = $bytes; $seen[strtolower($path)] = true; $total += $size;
        $manifest[] = array('path' => $path, 'size' => $size, 'sha256' => hash('sha256', $bytes));
    }
    $paths = array_keys($files); $sorted = $paths; sort($sorted, SORT_STRING);
    if ($paths !== $sorted || ! isset($files['style.css']) || $total > 16777216
        || hash('sha256', theme_restore_json($manifest)) !== ($package['tree_sha256'] ?? null)) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
    return array('files' => $files, 'manifest' => $manifest, 'tree' => $package['tree_sha256']);
}
function theme_restore_write_tree(string $directory, array $files): void {
    if (file_exists($directory) || is_link($directory) || ! mkdir($directory, 0700)) { theme_restore_abort('RAOS_SCRATCH_THEME_TARGET_EXISTS'); }
    foreach ($files as $path => $bytes) {
        $target = $directory . '/' . $path; $parent = dirname($target);
        if (! is_dir($parent) && ! mkdir($parent, 0700, true)) { theme_restore_abort('RAOS_SCRATCH_THEME_WRITE_FAILED'); }
        $handle = fopen($target, 'x');
        if (! is_resource($handle) || ! chmod($target, 0600) || fwrite($handle, $bytes) !== strlen($bytes)) { theme_restore_abort('RAOS_SCRATCH_THEME_WRITE_FAILED'); }
        fclose($handle);
    }
}
function theme_restore_manifest(string $directory): array {
    if (! is_dir($directory) || is_link($directory)) { theme_restore_abort('RAOS_SCRATCH_THEME_TREE_INVALID'); }
    $files = array();
    $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($directory, FilesystemIterator::SKIP_DOTS));
    foreach ($iterator as $entry) {
        if ($entry->isLink() || ! $entry->isFile()) { theme_restore_abort('RAOS_SCRATCH_THEME_TREE_INVALID'); }
        $path = substr($entry->getPathname(), strlen($directory) + 1); $bytes = theme_restore_read($entry->getPathname());
        $files[$path] = array('path' => $path, 'size' => strlen($bytes), 'sha256' => hash('sha256', $bytes));
    }
    ksort($files, SORT_STRING); return array_values($files);
}
function theme_restore_content(array $seed, string $seed_hash, string $environment): array {
    $documents = array(); $ids = array();
    foreach ($seed['documents'] as $slug => $row) {
        clean_post_cache($row['production_id']); $post = get_post($row['production_id']);
        if (! $post) { theme_restore_abort('RAOS_SCRATCH_THEME_CONTENT_MISSING'); }
        $ids[] = (int) $post->ID; $dates = array();
        foreach (array('date', 'date_gmt', 'modified', 'modified_gmt') as $field) { $dates[$field] = $post->{'post_' . $field}; }
        $taxonomy_ids = array();
        foreach ($row['taxonomy_ids'] as $taxonomy => $_expected) {
            $found = wp_get_object_terms($post->ID, $taxonomy, array('fields' => 'ids'));
            if (is_wp_error($found)) { theme_restore_abort('RAOS_SCRATCH_THEME_CONTENT_INVALID'); }
            $taxonomy_ids[$taxonomy] = array_map('intval', $found); sort($taxonomy_ids[$taxonomy]);
        }
        if ($row['taxonomy_ids_encoding'] === 'object') { $taxonomy_ids = (object) $taxonomy_ids; }
        $terms = array();
        foreach (array('category', 'post_tag') as $taxonomy) {
            $terms[$taxonomy] = array(); $found = wp_get_object_terms($post->ID, $taxonomy);
            if (is_wp_error($found)) { theme_restore_abort('RAOS_SCRATCH_THEME_CONTENT_INVALID'); }
            foreach ($found as $term) { $terms[$taxonomy][] = array('id' => (int) $term->term_id, 'name' => $term->name, 'slug' => $term->slug, 'parent' => (int) $term->parent); }
            usort($terms[$taxonomy], static function (array $a, array $b): int { return $a['id'] <=> $b['id']; });
        }
        $projection = array('schema' => 'ContentDocumentV1', 'id' => (int) $post->ID, 'slug' => $post->post_name, 'post_type' => $post->post_type, 'status' => $post->post_status, 'title' => $post->post_title, 'excerpt' => $post->post_excerpt, 'block_markup' => $post->post_content, 'taxonomies' => $taxonomy_ids, 'media_ids' => array());
        $documents[$slug] = array('id' => (int) $post->ID, 'slug' => $post->post_name, 'post_type' => $post->post_type, 'status' => $post->post_status,
            'title_sha256' => hash('sha256', $post->post_title), 'excerpt_sha256' => hash('sha256', $post->post_excerpt), 'body_sha256' => hash('sha256', $post->post_content), 'dates' => $dates,
            'taxonomy_ids' => $taxonomy_ids, 'taxonomies' => $terms, 'media_ids' => array(), 'content_sha256' => hash('sha256', theme_restore_json($projection)));
    }
    sort($ids);
    $actual = array_map('intval', get_posts(array('post_type' => array('post', 'page'), 'post_status' => 'any', 'numberposts' => -1, 'fields' => 'ids'))); sort($actual);
    if ($actual !== $ids || count($ids) !== 14) { theme_restore_abort('RAOS_SCRATCH_THEME_CONTENT_SET_INVALID'); }
    return array('schema' => 'RAOS_WORDPRESS_SCRATCH_RESTORE_READBACK_V1', 'publication_profile' => 'local-scratch-restore-rehearsal', 'publication_authority' => false, 'production_authority' => false, 'scratch_only' => true, 'temporary_environment' => true, 'environment_id' => $environment, 'seed_sha256' => $seed_hash, 'site_url' => 'http://scratch.wordpress.invalid', 'original_id_set' => $actual, 'documents' => $documents);
}
function theme_restore_stage(string $name, string $directory, array $seed, string $seed_hash, string $environment): array {
    global $wpdb;
    $manifest = theme_restore_manifest($directory);
    // Hash every stored option value/autoload flag; no option or credential bytes leave this process.
    $options = $wpdb->get_results('SELECT option_name, option_value, autoload FROM ' . $wpdb->options . ' ORDER BY option_name', ARRAY_A);
    if (! is_array($options)) { theme_restore_abort('RAOS_SCRATCH_THEME_OPTIONS_INVALID'); }
    return array('stage' => $name, 'theme_tree_sha256' => hash('sha256', theme_restore_json($manifest)), 'file_manifest' => $manifest,
        'content_readback' => theme_restore_content($seed, $seed_hash, $environment), 'wordpress_options_sha256' => hash('sha256', theme_restore_json($options)));
}
try {
$private = '/var/www/raos-scratch-backup'; $root = $private . '/theme-restore';
$theme_root = '/var/www/html/wp-content/themes/kurashinoshirube-child';
if (is_link($private) || realpath($private) !== $private || is_link($root) || realpath($root) !== $root
    || is_link('/var/www/html/wp-content') || is_link('/var/www/html/wp-content/themes')) { theme_restore_abort('RAOS_SCRATCH_THEME_BOUNDARY_INVALID'); }
$raw = theme_restore_read($root . '/preparation.v1.json'); $preparation = json_decode($raw, true, 32);
$environment = getenv('RAOS_SCRATCH_RESTORE_ENVIRONMENT'); $seed_raw = theme_restore_read($private . '/scratch-seed.v1.json');
$seed_hash = hash('sha256', $seed_raw); $seed = json_decode($seed_raw, true, 32);
if (! is_array($preparation) || ! is_array($seed) || ! is_string($environment) || preg_match('/\A[a-f0-9]{8}-[a-f0-9]{12}\z/D', $environment) !== 1
    || getenv('RAOS_SCRATCH_THEME_PREPARATION_SHA256') !== hash('sha256', $raw)
    || ($preparation['schema'] ?? null) !== 'RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_PREPARATION_V1'
    || ($preparation['publication_profile'] ?? null) !== 'local-scratch-theme-restore-rehearsal' || ($preparation['publication_authority'] ?? null) !== false
    || ($preparation['production_authority'] ?? null) !== false || ($preparation['scratch_only'] ?? null) !== true
    || ($preparation['environment_id'] ?? null) !== $environment || ($seed['environment_id'] ?? null) !== $environment
    || ($preparation['content_seed_sha256'] ?? null) !== $seed_hash || get_option('raos_scratch_restore_seed_hash') !== $seed_hash
    || getenv('RAOS_SCRATCH_SEED_SHA256') !== $seed_hash || count($seed['documents'] ?? array()) !== 14
    || ($preparation['operation'] ?? null) !== 'SAME_BASENAME_FILES_ONLY_NO_ACTIVATION'
    || ($preparation['theme_slug'] ?? null) !== 'kurashinoshirube-child'
    || hash('sha256', theme_restore_read($private . '/scratch-restoration-receipt.v1.json')) !== ($preparation['content_restore_receipt_sha256'] ?? null)) { theme_restore_abort('RAOS_SCRATCH_THEME_PREPARATION_INVALID'); }
$baseline_raw = theme_restore_read($root . '/baseline-package.v1.json'); $candidate_raw = theme_restore_read($root . '/candidate-package.v1.json');
if (hash('sha256', $baseline_raw) !== $preparation['baseline_package_sha256'] || hash('sha256', $candidate_raw) !== $preparation['candidate_package_sha256']) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
$baseline = theme_restore_package($baseline_raw); $candidate = theme_restore_package($candidate_raw);
foreach (array('baseline' => $baseline, 'candidate' => $candidate) as $key => $package) {
    if ($package['tree'] !== $preparation[$key . '_tree_sha256'] || theme_restore_json($package['manifest']) !== theme_restore_json($preparation[$key . '_file_manifest'])) { theme_restore_abort('RAOS_SCRATCH_THEME_PACKAGE_INVALID'); }
}
$staging = '/var/www/html/wp-content/themes/.raos-scratch-' . $environment;
$before_saved = $staging . '-baseline'; $candidate_staged = $staging . '-candidate-staged'; $candidate_saved = $staging . '-candidate-retained'; $destination = $root . '/readback.v1.json';
foreach (array($before_saved, $candidate_staged, $candidate_saved, $destination) as $path) { if (file_exists($path) || is_link($path)) { theme_restore_abort('RAOS_SCRATCH_THEME_ALREADY_EXECUTED'); } }
if (! file_exists($theme_root) && ! is_link($theme_root)) { theme_restore_write_tree($theme_root, $baseline['files']); }
if (theme_restore_manifest($theme_root) !== $baseline['manifest']) { theme_restore_abort('RAOS_SCRATCH_THEME_BASELINE_MISMATCH'); }
$stages = array(theme_restore_stage('baseline_before', $theme_root, $seed, $seed_hash, $environment));
$expected_content = json_decode(theme_restore_read($private . '/scratch-readback.v1.json'));
if (! is_object($expected_content) || theme_restore_json($stages[0]['content_readback']) !== theme_restore_json($expected_content)) { theme_restore_abort('RAOS_SCRATCH_THEME_CONTENT_BASELINE_MISMATCH'); }
theme_restore_write_tree($candidate_staged, $candidate['files']);
if (! rename($theme_root, $before_saved)) { theme_restore_abort('RAOS_SCRATCH_THEME_BACKUP_MOVE_FAILED'); }
try {
    if (! rename($candidate_staged, $theme_root)) { throw new RuntimeException('RAOS_SCRATCH_THEME_REPLACE_FAILED'); }
    $stages[] = theme_restore_stage('candidate_installed', $theme_root, $seed, $seed_hash, $environment);
} finally {
    if (is_dir($theme_root) && ! rename($theme_root, $candidate_saved)) { theme_restore_abort('RAOS_SCRATCH_THEME_RETAIN_CANDIDATE_FAILED'); }
    if (! rename($before_saved, $theme_root)) { theme_restore_abort('RAOS_SCRATCH_THEME_RESTORE_FAILED'); }
}
$stages[] = theme_restore_stage('baseline_restored', $theme_root, $seed, $seed_hash, $environment);
if ($stages[0]['wordpress_options_sha256'] !== $stages[1]['wordpress_options_sha256'] || $stages[0]['wordpress_options_sha256'] !== $stages[2]['wordpress_options_sha256']) { theme_restore_abort('RAOS_SCRATCH_THEME_OPTIONS_CHANGED'); }
$readback = array('schema' => 'RAOS_WORDPRESS_SCRATCH_THEME_RESTORE_READBACK_V1', 'publication_profile' => 'local-scratch-theme-restore-rehearsal',
    'publication_authority' => false, 'production_authority' => false, 'scratch_only' => true, 'temporary_environment' => true, 'environment_id' => $environment,
    'preparation_sha256' => hash('sha256', $raw), 'theme_slug' => 'kurashinoshirube-child', 'site_url' => 'http://scratch.wordpress.invalid',
    'operation' => 'SAME_BASENAME_FILES_ONLY_NO_ACTIVATION', 'stages' => $stages);
$handle = fopen($destination, 'x'); $output = theme_restore_json($readback) . "\n";
if (! is_resource($handle) || ! chmod($destination, 0600) || fwrite($handle, $output) !== strlen($output)) { theme_restore_abort('RAOS_SCRATCH_THEME_READBACK_WRITE_FAILED'); }
fclose($handle); WP_CLI::success('RAOS_SCRATCH_THEME_BASELINE_RESTORED_READBACK_CAPTURED');
} catch (Throwable $error) {
    $code = preg_match('/\ARAOS_SCRATCH_THEME_[A-Z_]+\z/D', $error->getMessage()) === 1 ? $error->getMessage() : 'RAOS_SCRATCH_THEME_EXECUTION_FAILED';
    WP_CLI::error($code);
}
