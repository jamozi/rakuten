<?php
/**
 * Simulate activationless v1 and v3 store upgrades in disposable E2E only.
 */

defined('ABSPATH') || exit;

if (! isset($args) || ! is_array($args) || 1 !== count($args)) {
    fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_ARGUMENT_INVALID\n");
    exit(64);
}

global $wpdb;
$mode = (string) $args[0];
$table = RAOS_Codex_MCP_Store::table_name();
$batch_table = RAOS_Codex_MCP_Store::batch_table_name();

if ('degrade-v3' === $mode) {
    $batch_applying_column = $wpdb->get_var(
        "SHOW COLUMNS FROM {$batch_table} LIKE 'applying_at_gmt'"
    );
    if (is_string($batch_applying_column)
        && false === $wpdb->query(
            "ALTER TABLE {$batch_table} DROP COLUMN applying_at_gmt"
        )) {
        fwrite(STDERR, "RAOS_E2E_STORE_V3_BATCH_APPLYING_DROP_FAILED\n");
        exit(65);
    }
    update_option(RAOS_Codex_MCP_Store::SCHEMA_OPTION, '3', false);
    fwrite(STDOUT, "RAOS_E2E_STORE_V3_DEGRADED\n");
    exit(0);
}

if ('degrade' === $mode) {
    if (false === $wpdb->query("DROP TABLE IF EXISTS {$batch_table}")) {
        fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_BATCH_DROP_FAILED\n");
        exit(65);
    }
    $indexes = $wpdb->get_col("SHOW INDEX FROM {$table} WHERE Key_name = 'creator_kind_idempotency'", 2);
    if (! empty($indexes)
        && false === $wpdb->query("ALTER TABLE {$table} DROP INDEX creator_kind_idempotency")) {
        fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_INDEX_DROP_FAILED\n");
        exit(65);
    }
    $column = $wpdb->get_var("SHOW COLUMNS FROM {$table} LIKE 'idempotency_key'");
    if (is_string($column)
        && false === $wpdb->query("ALTER TABLE {$table} DROP COLUMN idempotency_key")) {
        fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_COLUMN_DROP_FAILED\n");
        exit(66);
    }
    $applying_column = $wpdb->get_var("SHOW COLUMNS FROM {$table} LIKE 'applying_at_gmt'");
    if (is_string($applying_column)
        && false === $wpdb->query("ALTER TABLE {$table} DROP COLUMN applying_at_gmt")) {
        fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_APPLYING_COLUMN_DROP_FAILED\n");
        exit(66);
    }
    update_option(RAOS_Codex_MCP_Store::SCHEMA_OPTION, '1', false);
    fwrite(STDOUT, "RAOS_E2E_STORE_DEGRADED\n");
    exit(0);
}

if ('check' !== $mode) {
    fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_MODE_INVALID\n");
    exit(67);
}

$column = $wpdb->get_var("SHOW COLUMNS FROM {$table} LIKE 'idempotency_key'");
$applying_column = $wpdb->get_var("SHOW COLUMNS FROM {$table} LIKE 'applying_at_gmt'");
$batch_applying_column = $wpdb->get_var(
    "SHOW COLUMNS FROM {$batch_table} LIKE 'applying_at_gmt'"
);
$batch_exists = $wpdb->get_var($wpdb->prepare('SHOW TABLES LIKE %s', $batch_table));
$indexes = $wpdb->get_col("SHOW INDEX FROM {$table} WHERE Key_name = 'creator_kind_idempotency'", 2);
if ('idempotency_key' !== $column
    || 'applying_at_gmt' !== $applying_column
    || 'applying_at_gmt' !== $batch_applying_column
    || $batch_table !== $batch_exists
    || empty($indexes)
    || RAOS_Codex_MCP_Store::SCHEMA_VERSION !== get_option(RAOS_Codex_MCP_Store::SCHEMA_OPTION)) {
    fwrite(STDERR, "RAOS_E2E_STORE_UPGRADE_FAILED\n");
    exit(68);
}
fwrite(STDOUT, "RAOS_E2E_STORE_UPGRADE_OK\n");
