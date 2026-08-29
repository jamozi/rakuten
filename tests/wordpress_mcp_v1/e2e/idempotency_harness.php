<?php
/**
 * Verify proposal idempotency replay and conflict in disposable E2E only.
 */

defined('ABSPATH') || exit;

global $wpdb;
$proposal_id = $wpdb->get_var(
    'SELECT proposal_id FROM ' . RAOS_Codex_MCP_Store::table_name()
    . " WHERE kind = 'CONTENT_RELEASE' AND idempotency_key IS NOT NULL"
    . ' ORDER BY created_at_gmt ASC LIMIT 1'
);
$row = is_string($proposal_id) ? RAOS_Codex_MCP_Store::get($proposal_id) : null;
if (! is_array($row)
    || ! isset($row['idempotency_key'])
    || ! RAOS_Codex_MCP_Store::is_sha256($row['idempotency_key'])) {
    fwrite(STDERR, "RAOS_E2E_IDEMPOTENCY_TARGET_INVALID\n");
    exit(64);
}

wp_set_current_user((int) $row['created_by']);
$payload = $row['payload'];
foreach (array('proposal_id', 'created_by', 'created_at_gmt', 'expires_at_gmt') as $metadata_key) {
    unset($payload[$metadata_key]);
}
$replayed = RAOS_Codex_MCP_Store::create(
    $row['kind'],
    $payload,
    $row['before_sha256'],
    $row['after_sha256'],
    true,
    null,
    $row['idempotency_key']
);
if (! is_array($replayed)
    || ! hash_equals($row['proposal_id'], $replayed['proposal_id'])) {
    fwrite(STDERR, "RAOS_E2E_IDEMPOTENCY_REPLAY_FAILED\n");
    exit(65);
}

$payload['target_status'] = 'draft';
$conflict = RAOS_Codex_MCP_Store::create(
    $row['kind'],
    $payload,
    $row['before_sha256'],
    $row['after_sha256'],
    true,
    null,
    $row['idempotency_key']
);
$error_data = is_wp_error($conflict) ? $conflict->get_error_data() : null;
if (! is_wp_error($conflict)
    || 'raos_codex_idempotency_conflict' !== $conflict->get_error_code()
    || ! is_array($error_data)
    || 409 !== $error_data['status']) {
    fwrite(STDERR, "RAOS_E2E_IDEMPOTENCY_CONFLICT_FAILED\n");
    exit(66);
}
fwrite(STDOUT, "RAOS_E2E_IDEMPOTENCY_OK\n");
