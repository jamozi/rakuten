<?php
/**
 * Exercise fail-closed batch approval in the disposable WordPress E2E site.
 */

defined('ABSPATH') || exit;

if (! isset($args) || ! is_array($args) || 1 !== count($args)) {
    fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_ARGUMENT_INVALID\n");
    exit(64);
}

$mode = (string) $args[0];
$administrator = get_user_by('login', 'raos-e2e-approver');
$password = getenv('RAOS_WORDPRESS_E2E_ADMIN_PASSWORD');
if (! $administrator instanceof WP_User
    || ! is_string($password)
    || strlen($password) < 32) {
    fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_IDENTITY_INVALID\n");
    exit(65);
}

wp_set_current_user($administrator->ID);
$batches = RAOS_Codex_MCP_Store::pending_publication_batches_for_admin(20);
$batch = 1 === count($batches) ? $batches[0] : null;
if (! is_array($batch) || count($batch['proposal_ids']) < 2) {
    fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_SNAPSHOT_INVALID\n");
    exit(66);
}
$rows = array();
foreach ($batch['proposal_ids'] as $proposal_id) {
    $row = RAOS_Codex_MCP_Store::get($proposal_id);
    if (is_wp_error($row)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_SNAPSHOT_INVALID\n");
        exit(66);
    }
    $rows[] = $row;
}

if ('expect-rollback' === $mode) {
    $mismatched = RAOS_Codex_MCP_Store::approve_publication_batch(
        $batch['batch_token'],
        str_repeat('0', 64),
        $administrator->ID,
        'Disposable E2E reason verifies manifest mismatch refusal.'
    );
    if (! is_wp_error($mismatched)
        || 'raos_codex_approval_batch_hash_drift' !== $mismatched->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_MISMATCH_ACCEPTED\n");
        exit(67);
    }
    global $wpdb;
    $plugin_id = $wpdb->get_var(
        'SELECT proposal_id FROM ' . RAOS_Codex_MCP_Store::table_name()
        . " WHERE kind = 'PLUGIN_CHANGE' AND state = 'PENDING' LIMIT 1"
    );
    $content_owner = null;
    foreach ($rows as $row) {
        if ('CONTENT_RELEASE' === $row['kind']) {
            $content_owner = (int) $row['created_by'];
            break;
        }
    }
    wp_set_current_user((int) $content_owner);
    $plugin_scope = RAOS_Codex_MCP_Store::register_publication_batch(
        array_merge($batch['proposal_ids'], array((string) $plugin_id))
    );
    wp_set_current_user($administrator->ID);
    if (! is_wp_error($plugin_scope)
        || 'raos_codex_publication_batch_proposal_invalid' !== $plugin_scope->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_PLUGIN_SCOPE_ACCEPTED\n");
        exit(67);
    }
    $blocked_id = $rows[1]['proposal_id'];
    $blocked_path = RAOS_CODEX_PRIVATE_DIR . '/approval-lease-' . $blocked_id . '.json';
    if (false === file_put_contents($blocked_path, '{"e2e":"blocker"}', LOCK_EX)
        || ! chmod($blocked_path, 0600)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_BLOCKER_FAILED\n");
        exit(67);
    }
    $result = RAOS_Codex_MCP_Store::approve_publication_batch(
        $batch['batch_token'],
        $batch['batch_manifest_sha256'],
        $administrator->ID,
        'Disposable E2E reason verifies rollback and lease cleanup.'
    );
    if (! is_wp_error($result)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_UNEXPECTED_SUCCESS\n");
        exit(68);
    }
    foreach ($rows as $row) {
        $readback = RAOS_Codex_MCP_Store::get($row['proposal_id']);
        $lease_path = RAOS_CODEX_PRIVATE_DIR . '/approval-lease-' . $row['proposal_id'] . '.json';
        if (is_wp_error($readback) || 'PENDING' !== $readback['state']) {
            fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_ROLLBACK_FAILED\n");
            exit(69);
        }
        if ($row['proposal_id'] !== $blocked_id && file_exists($lease_path)) {
            fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_LEASE_CLEANUP_FAILED\n");
            exit(70);
        }
    }
    if (file_exists($blocked_path) && ! unlink($blocked_path)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_BLOCKER_CLEANUP_FAILED\n");
        exit(71);
    }
    fwrite(STDOUT, "RAOS_E2E_BATCH_APPROVAL_ROLLBACK_OK\n");
    exit(0);
}

if ('approve' !== $mode) {
    fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_MODE_INVALID\n");
    exit(72);
}

$_SERVER['REQUEST_METHOD'] = 'POST';
$_POST = array(
    'action' => 'raos_codex_mcp_approve_batch',
    'batch_token' => $batch['batch_token'],
    'batch_manifest_sha256' => $batch['batch_manifest_sha256'],
    '_wpnonce' => wp_create_nonce(
        'raos_codex_mcp_approve_batch_'
        . $batch['batch_token'] . '_' . $batch['batch_manifest_sha256']
    ),
    'current_password' => $password,
    'reason' => 'Disposable E2E batch approval after verifying the complete manifest.',
    'hash_suffix' => substr($batch['batch_manifest_sha256'], -8),
);
$_REQUEST = $_POST;

RAOS_Codex_MCP_Abilities::instance()->handle_batch_approval();
