<?php
/** Read-only local preview state. Never emits content, options, or credentials. */
if (!defined('WP_CLI') || !WP_CLI) {
    exit(69);
}
$origin = (string) get_option('home');
if (!preg_match('~^http://127\.0\.0\.1:[0-9]{4,5}$~D', $origin)) {
    exit(69);
}
global $wpdb, $wp_version;
$queries = array(
    'posts' => "SELECT ID, post_author, post_date_gmt, post_modified_gmt, post_content, post_title, post_excerpt, post_status, post_name, post_parent, post_type, menu_order FROM {$wpdb->posts} ORDER BY ID LIMIT 10001",
    'postmeta' => "SELECT post_id, meta_key, meta_value FROM {$wpdb->postmeta} WHERE meta_key NOT IN ('_edit_lock', '_edit_last') ORDER BY post_id, meta_key, meta_id LIMIT 10001",
    'options' => "SELECT option_name, option_value FROM {$wpdb->options} WHERE option_name NOT LIKE '\\_transient\\_%' AND option_name NOT LIKE '\\_site\\_transient\\_%' AND option_name NOT IN ('cron', 'recently_activated', 'recently_edited') ORDER BY option_name LIMIT 10001",
    'terms' => "SELECT term_id, name, slug, term_group FROM {$wpdb->terms} ORDER BY term_id LIMIT 10001",
    'taxonomy' => "SELECT term_taxonomy_id, term_id, taxonomy, description, parent, count FROM {$wpdb->term_taxonomy} ORDER BY term_taxonomy_id LIMIT 10001",
    'relationships' => "SELECT object_id, term_taxonomy_id, term_order FROM {$wpdb->term_relationships} ORDER BY object_id, term_taxonomy_id LIMIT 10001",
);
$hashes = array('wordpress_version' => (string) $wp_version, 'origin' => $origin);
foreach ($queries as $name => $query) {
    $rows = $wpdb->get_results($query, ARRAY_A);
    if ($wpdb->last_error || !is_array($rows) || count($rows) > 10000) {
        exit(69);
    }
    $hashes[$name] = hash('sha256', wp_json_encode($rows));
}
$files = array();
// Only public executable assets; never wp-config.php, uploads, or private data.
foreach (array(WP_PLUGIN_DIR, WPMU_PLUGIN_DIR, get_theme_root()) as $root) {
    if (!is_dir($root)) {
        exit(69);
    }
    $iterator = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
    foreach ($iterator as $file) {
        if ($file->isLink() || !$file->isFile() || count($files) >= 15000) {
            exit(69);
        }
        $hash = hash_file('sha256', $file->getPathname());
        if ($hash === false) {
            exit(69);
        }
        $files[$file->getPathname()] = $hash;
    }
}
ksort($files, SORT_STRING);
$hashes['public_runtime_files'] = hash('sha256', wp_json_encode($files));
echo hash('sha256', wp_json_encode($hashes)) . "\n";
