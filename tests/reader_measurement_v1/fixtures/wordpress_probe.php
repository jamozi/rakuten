<?php
/** Inspect real WordPress/dbDelta state in the disposable integration site. */

defined('ABSPATH') || exit;
if (! isset($args) || ! is_array($args) || count($args) !== 1) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_PROBE_ARGUMENT_INVALID\n");
    exit(64);
}

global $wpdb;
$mode = (string) $args[0];
$plugin = 'raos-reader-measurement/raos-reader-measurement.php';
require_once ABSPATH . 'wp-admin/includes/plugin.php';

function raos_reader_wordpress_emit(array $value): void
{
    echo 'RAOS_READER_WORDPRESS_JSON=' . wp_json_encode(
        $value,
        JSON_UNESCAPED_SLASHES
    ) . "\n";
}

function raos_reader_wordpress_tables(): array
{
    global $wpdb;
    $like = $wpdb->esc_like($wpdb->prefix . 'raos_reader_') . '%';
    $tables = $wpdb->get_col($wpdb->prepare('SHOW TABLES LIKE %s', $like));
    if (! is_array($tables)) {
        return array();
    }
    sort($tables, SORT_STRING);
    return array_values($tables);
}

if ($mode === 'before') {
    raos_reader_wordpress_emit(array(
        'wordpress_version' => get_bloginfo('version'),
        'plugin_installed' => is_file(WP_PLUGIN_DIR . '/' . $plugin),
        'plugin_active' => is_plugin_active($plugin),
        'dedicated_tables' => raos_reader_wordpress_tables(),
        'active_plugins' => array_values((array) get_option('active_plugins', array())),
    ));
    exit(0);
}

if (! class_exists('RAOS_Reader_Maintenance')
    || ! function_exists('raos_reader_measurement_enabled')) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_PLUGIN_NOT_LOADED\n");
    exit(65);
}

$tables = RAOS_Reader_Maintenance::tables();
if ($mode === 'inspect') {
    $engines = array();
    $columns = array();
    foreach ($tables as $kind => $table) {
        $status = $wpdb->get_row(
            $wpdb->prepare('SHOW TABLE STATUS WHERE Name = %s', $table),
            ARRAY_A
        );
        $engines[$kind] = is_array($status) ? ($status['Engine'] ?? null) : null;
        $rows = $wpdb->get_results('SHOW COLUMNS FROM ' . $table, ARRAY_A);
        $columns[$kind] = is_array($rows) ? array_column($rows, 'Field') : array();
        sort($columns[$kind], SORT_STRING);
    }
    $active = array_values((array) get_option('active_plugins', array()));
    sort($active, SORT_STRING);
    raos_reader_wordpress_emit(array(
        'wordpress_version' => get_bloginfo('version'),
        'plugin_active' => is_plugin_active($plugin),
        'collection_enabled' => raos_reader_measurement_enabled(),
        'state' => get_option('raos_reader_measurement_state_v1', null),
        'db_version' => get_option(RAOS_Reader_Maintenance::DB_OPTION, null),
        'storage_ready' => RAOS_Reader_Maintenance::storage_ready(),
        'cleanup_status' => RAOS_Reader_Maintenance::status(),
        'cleanup_scheduled' => wp_next_scheduled(RAOS_Reader_Maintenance::HOOK) !== false,
        'dedicated_tables' => raos_reader_wordpress_tables(),
        'table_names' => $tables,
        'engines' => $engines,
        'columns' => $columns,
        'active_plugins' => $active,
        'old_eight_event_plugin_active' => is_plugin_active(
            'raos-editorial-measurement/raos-editorial-measurement.php'
        ),
    ));
    exit(0);
}

if ($mode !== 'cleanup') {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_PROBE_MODE_INVALID\n");
    exit(66);
}

$today = new DateTimeImmutable('today', new DateTimeZone('Asia/Tokyo'));
$rows = array(
    'raw_expired' => array(
        'table' => $tables['raw'],
        'event_date' => $today->modify('-29 days')->format('Y-m-d'),
        'article_id' => 'integration-raw-expired',
    ),
    'raw_kept' => array(
        'table' => $tables['raw'],
        'event_date' => $today->modify('-28 days')->format('Y-m-d'),
        'article_id' => 'integration-raw-kept',
    ),
    'daily_expired' => array(
        'table' => $tables['daily'],
        'event_date' => $today->modify('-89 days')->format('Y-m-d'),
        'article_id' => 'integration-daily-expired',
    ),
    'daily_kept' => array(
        'table' => $tables['daily'],
        'event_date' => $today->modify('-88 days')->format('Y-m-d'),
        'article_id' => 'integration-daily-kept',
    ),
);
foreach ($rows as $name => $row) {
    $payload = array(
        'event_date' => $row['event_date'],
        'event_name' => 'decision_check_open',
        'article_id' => $row['article_id'],
        'target_article_id' => $name[0] === 'd' ? '' : null,
        'journey_stage' => $name[0] === 'd' ? '' : null,
        'panel_id' => 'reader-evidence',
        'source_ref' => $name[0] === 'd' ? '' : null,
    );
    if ($name[0] === 'd') {
        $payload['event_count'] = 1;
    }
    if ($wpdb->insert($row['table'], $payload) !== 1) {
        fwrite(STDERR, "RAOS_READER_WORDPRESS_CLEANUP_SEED_FAILED\n");
        exit(67);
    }
}

if (! RAOS_Reader_Maintenance::cleanup($today)) {
    fwrite(STDERR, "RAOS_READER_WORDPRESS_CLEANUP_FAILED\n");
    exit(68);
}
$remaining = array();
foreach ($rows as $name => $row) {
    $remaining[$name] = (int) $wpdb->get_var($wpdb->prepare(
        'SELECT COUNT(*) FROM ' . $row['table'] . ' WHERE article_id = %s',
        $row['article_id']
    ));
}
raos_reader_wordpress_emit(array(
    'cleanup_returned' => true,
    'remaining' => $remaining,
    'cleanup_status' => RAOS_Reader_Maintenance::status($today),
    'collection_enabled' => raos_reader_measurement_enabled(),
));
