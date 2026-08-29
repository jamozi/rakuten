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

final class RAOS_E2E_Ambiguous_Commit_WPDB extends wpdb
{
    private $fail_next_commit = false;

    public function arm_ambiguous_commit()
    {
        $this->fail_next_commit = true;
    }

    public function query($query)
    {
        $result = parent::query($query);
        if ($this->fail_next_commit
            && is_string($query)
            && 0 === strcasecmp('COMMIT', trim($query))) {
            $this->fail_next_commit = false;
            return false;
        }
        return $result;
    }
}

function raos_e2e_clone_content_proposal($row, $desired_slug = null)
{
    if (! is_array($row)
        || 'CONTENT_RELEASE' !== $row['kind']
        || ! isset($row['payload'])
        || ! is_array($row['payload'])) {
        return new WP_Error('raos_e2e_clone_invalid');
    }
    $payload = $row['payload'];
    foreach (array(
        'proposal_id',
        'created_by',
        'created_at_gmt',
        'expires_at_gmt',
        'idempotency_key',
    ) as $metadata_key) {
        unset($payload[$metadata_key]);
    }
    if (is_string($desired_slug)) {
        $payload['after']['slug'] = $desired_slug;
        $after_hash = RAOS_Codex_MCP_Content::document_hash($payload['after']);
        if (! RAOS_Codex_MCP_Store::is_sha256($after_hash)) {
            return new WP_Error('raos_e2e_clone_invalid');
        }
        $payload['after_sha256'] = $after_hash;
        $payload['publication_manifest_sha256'] = RAOS_Codex_MCP_Store::hash(
            array(
                'schema' => 'ContentPublicationManifestV1',
                'target_status' => 'publish',
                'post_type' => $payload['before']['post_type'],
                'post_id' => $payload['before']['id'],
                'before_sha256' => $payload['before_sha256'],
                'after_sha256' => $after_hash,
                'precondition' => array(
                    'revision_id' => $payload['before']['revision_id'],
                    'modified_gmt' => $payload['before']['modified_gmt'],
                    'content_sha256' => $payload['before_sha256'],
                ),
            )
        );
    }
    return RAOS_Codex_MCP_Store::create(
        'CONTENT_RELEASE',
        $payload,
        $payload['before_sha256'],
        $payload['after_sha256'],
        true
    );
}

wp_set_current_user($administrator->ID);
global $wpdb;
if (in_array($mode, array('approve', 'claim-ambiguous-reset', 'plugin-ambiguous-reset'), true)) {
    $approved_batch_tokens = $wpdb->get_col(
        'SELECT batch_token FROM ' . RAOS_Codex_MCP_Store::batch_table_name()
        . " WHERE state = 'APPROVED'"
        . ' ORDER BY approved_at_gmt DESC, batch_token ASC'
    );
    $batch = null;
    foreach (is_array($approved_batch_tokens) ? $approved_batch_tokens : array() as $approved_batch_token) {
        $candidate = RAOS_Codex_MCP_Store::get_publication_batch($approved_batch_token);
        if (is_array($candidate) && count($candidate['proposal_ids']) >= 2) {
            $batch = $candidate;
            break;
        }
    }
} else {
    $batches = RAOS_Codex_MCP_Store::pending_publication_batches_for_admin(20);
    $batch = 1 === count($batches) ? $batches[0] : null;
}
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

if ('plugin-ambiguous-reset' === $mode) {
    $plugin_id = $wpdb->get_var(
        'SELECT proposal_id FROM ' . RAOS_Codex_MCP_Store::table_name()
        . " WHERE kind = 'PLUGIN_CHANGE' AND state = 'PENDING'"
        . ' ORDER BY created_at_gmt ASC LIMIT 1'
    );
    $plugin = is_string($plugin_id)
        ? RAOS_Codex_MCP_Store::get($plugin_id)
        : null;
    $original_expiry_unix = is_array($plugin)
        && isset($plugin['payload']['expires_at_gmt'])
        ? strtotime($plugin['payload']['expires_at_gmt'])
        : false;
    if (! is_array($plugin)
        || 'PLUGIN_CHANGE' !== $plugin['kind']
        || false === $original_expiry_unix
        || $original_expiry_unix <= time()) {
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_TARGET_INVALID\n");
        exit(66);
    }

    $approval_reason = 'Disposable E2E approval verifies ambiguous plugin commit recovery.';
    $authoritative_wpdb = $wpdb;
    $ambiguous_wpdb = new RAOS_E2E_Ambiguous_Commit_WPDB(
        DB_USER,
        DB_PASSWORD,
        DB_NAME,
        DB_HOST
    );
    $prefix_result = $ambiguous_wpdb->set_prefix($authoritative_wpdb->prefix);
    if (is_wp_error($prefix_result)) {
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_DB_INJECTION_FAILED\n");
        exit(66);
    }
    $ambiguous_wpdb->arm_ambiguous_commit();
    $wpdb = $ambiguous_wpdb;
    try {
        $ambiguous_result = RAOS_Codex_MCP_Store::approve(
            $plugin_id,
            $administrator->ID,
            $approval_reason
        );
    } finally {
        $wpdb = $authoritative_wpdb;
    }
    $approved_plugin = RAOS_Codex_MCP_Store::get($plugin_id);
    $expected_approval_expiry = is_array($approved_plugin)
        && isset($approved_plugin['approved_at_gmt'])
        ? gmdate(
            'Y-m-d H:i:s',
            strtotime($approved_plugin['approved_at_gmt'] . ' UTC')
                + RAOS_Codex_MCP_Store::TTL_SECONDS
        )
        : null;
    if (is_wp_error($ambiguous_result)
        || is_wp_error($approved_plugin)
        || 'APPROVED' !== $approved_plugin['state']
        || ! is_string($expected_approval_expiry)
        || ! hash_equals($expected_approval_expiry, $approved_plugin['expires_at_gmt'])
        || is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($approved_plugin))) {
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_AMBIGUOUS_COMMIT_FAILED\n");
        exit(66);
    }

    $original_expiry = gmdate('Y-m-d H:i:s', $original_expiry_unix);
    if (false === $wpdb->query('START TRANSACTION')) {
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_RESET_FAILED\n");
        exit(66);
    }
    $reset = $wpdb->query(
        $wpdb->prepare(
            'UPDATE ' . RAOS_Codex_MCP_Store::table_name()
            . " SET state = 'PENDING', result_code = 'PROPOSAL_PENDING_APPROVAL',"
            . ' approved_by = NULL, approved_at_gmt = NULL, applying_at_gmt = NULL,'
            . ' completed_at_gmt = NULL, approval_reason = NULL, receipt_json = NULL,'
            . ' expires_at_gmt = %s'
            . " WHERE proposal_id = %s AND kind = 'PLUGIN_CHANGE'"
            . " AND state = 'APPROVED' AND result_code = 'PROPOSAL_APPROVED'"
            . ' AND approved_by = %d AND approved_at_gmt = %s',
            $original_expiry,
            $plugin_id,
            $administrator->ID,
            $approved_plugin['approved_at_gmt']
        )
    );
    if (1 !== $reset || false === $wpdb->query('COMMIT')) {
        $wpdb->query('ROLLBACK');
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_RESET_FAILED\n");
        exit(66);
    }
    $reset_plugin = RAOS_Codex_MCP_Store::get($plugin_id);
    if (is_wp_error($reset_plugin)
        || 'PENDING' !== $reset_plugin['state']
        || ! hash_equals($original_expiry, $reset_plugin['expires_at_gmt'])
        || ! RAOS_Codex_MCP_Deployment::remove_approval_lease($plugin_id)) {
        fwrite(STDERR, "RAOS_E2E_PLUGIN_APPROVAL_RESET_FAILED\n");
        exit(66);
    }
    fwrite(STDOUT, "RAOS_E2E_PLUGIN_APPROVAL_AMBIGUOUS_COMMIT_OK\n");
    exit(0);
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
    $plugin_id = $wpdb->get_var(
        'SELECT proposal_id FROM ' . RAOS_Codex_MCP_Store::table_name()
        . " WHERE kind = 'PLUGIN_CHANGE' AND state = 'PENDING' LIMIT 1"
    );
    $content_owner = null;
    $content_rows = array();
    foreach ($rows as $row) {
        if ('CONTENT_RELEASE' === $row['kind']) {
            $content_owner = is_null($content_owner)
                ? (int) $row['created_by']
                : $content_owner;
            $content_rows[] = $row;
        }
    }
    wp_set_current_user((int) $content_owner);
    $plugin_scope = RAOS_Codex_MCP_Store::register_publication_batch(
        array_merge($batch['proposal_ids'], array((string) $plugin_id)),
        $batch['manifest']['expected_theme_tree_sha256']
    );
    wp_set_current_user($administrator->ID);
    if (! is_wp_error($plugin_scope)
        || 'raos_codex_publication_batch_proposal_invalid' !== $plugin_scope->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_PLUGIN_SCOPE_ACCEPTED\n");
        exit(67);
    }
    if (count($content_rows) < 2) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_CONTENT_TARGET_SETUP_FAILED\n");
        exit(67);
    }
    wp_set_current_user((int) $content_owner);
    $duplicate_target = raos_e2e_clone_content_proposal($content_rows[0]);
    $duplicate_target_batch = is_wp_error($duplicate_target)
        ? $duplicate_target
        : RAOS_Codex_MCP_Store::register_publication_batch(
            array($content_rows[0]['proposal_id'], $duplicate_target['proposal_id']),
            $batch['manifest']['expected_theme_tree_sha256']
        );
    $duplicate_slug = raos_e2e_clone_content_proposal(
        $content_rows[1],
        $content_rows[0]['payload']['after']['slug']
    );
    $duplicate_slug_batch = is_wp_error($duplicate_slug)
        ? $duplicate_slug
        : RAOS_Codex_MCP_Store::register_publication_batch(
            array($content_rows[0]['proposal_id'], $duplicate_slug['proposal_id']),
            $batch['manifest']['expected_theme_tree_sha256']
        );
    wp_set_current_user($administrator->ID);
    if (is_array($duplicate_target)) {
        $wpdb->delete(
            RAOS_Codex_MCP_Store::table_name(),
            array('proposal_id' => $duplicate_target['proposal_id'])
        );
    }
    if (is_array($duplicate_slug)) {
        $wpdb->delete(
            RAOS_Codex_MCP_Store::table_name(),
            array('proposal_id' => $duplicate_slug['proposal_id'])
        );
    }
    if (! is_wp_error($duplicate_target_batch)
        || 'raos_codex_approval_batch_target_conflict' !== $duplicate_target_batch->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_DUPLICATE_TARGET_ACCEPTED\n");
        exit(67);
    }
    if (! is_wp_error($duplicate_slug_batch)
        || 'raos_codex_approval_batch_target_conflict' !== $duplicate_slug_batch->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_DUPLICATE_SLUG_ACCEPTED\n");
        exit(67);
    }
    $subset = RAOS_Codex_MCP_Store::approve(
        $rows[0]['proposal_id'],
        $administrator->ID,
        'Disposable E2E reason verifies subset approval refusal.'
    );
    if (! is_wp_error($subset)
        || 'raos_codex_publication_batch_approval_required' !== $subset->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_SUBSET_ACCEPTED\n");
        exit(67);
    }
    $operations_table = RAOS_Codex_MCP_Store::table_name();
    if (false === $wpdb->query("ALTER TABLE {$operations_table} ENGINE=MyISAM")) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_ENGINE_INJECTION_FAILED\n");
        exit(67);
    }
    $non_transactional = RAOS_Codex_MCP_Store::approve_publication_batch(
        $batch['batch_token'],
        $batch['batch_manifest_sha256'],
        $administrator->ID,
        'Disposable E2E reason verifies transactional engine refusal.'
    );
    $engine_restored = false !== $wpdb->query("ALTER TABLE {$operations_table} ENGINE=InnoDB");
    if (! $engine_restored
        || ! is_wp_error($non_transactional)
        || 'raos_codex_transactional_engine_unsupported' !== $non_transactional->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_NONTRANSACTIONAL_ACCEPTED\n");
        exit(67);
    }

    $blocked_id = $rows[1]['proposal_id'];
    $blocked_path = RAOS_CODEX_PRIVATE_DIR . '/approval-lease-' . $blocked_id . '.json';
    if (! symlink(__FILE__, $blocked_path)) {
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
    if ('raos_codex_approval_orphan_lease_cleanup_failed' !== $result->get_error_code()) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_BLOCKER_NOT_REJECTED\n");
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

    if (false === file_put_contents($blocked_path, '{"e2e":"orphan"}', LOCK_EX)
        || ! chmod($blocked_path, 0600)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_ORPHAN_SETUP_FAILED\n");
        exit(71);
    }

    $authoritative_wpdb = $wpdb;
    $ambiguous_wpdb = new RAOS_E2E_Ambiguous_Commit_WPDB(
        DB_USER,
        DB_PASSWORD,
        DB_NAME,
        DB_HOST
    );
    $prefix_result = $ambiguous_wpdb->set_prefix($authoritative_wpdb->prefix);
    if (is_wp_error($prefix_result)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_DB_INJECTION_FAILED\n");
        exit(71);
    }
    $ambiguous_wpdb->arm_ambiguous_commit();
    $wpdb = $ambiguous_wpdb;
    try {
        $result = RAOS_Codex_MCP_Store::approve_publication_batch(
            $batch['batch_token'],
            $batch['batch_manifest_sha256'],
            $administrator->ID,
            'Disposable E2E reason verifies ambiguous commit recovery.'
        );
    } finally {
        $wpdb = $authoritative_wpdb;
    }
    if (is_wp_error($result)
        || count($rows) !== (int) $result['proposal_count']) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_AMBIGUOUS_COMMIT_FAILED\n");
        exit(71);
    }
    $approved_batch = RAOS_Codex_MCP_Store::get_publication_batch($batch['batch_token']);
    $expected_approval_expiry = is_array($approved_batch)
        && isset($approved_batch['approved_at_gmt'])
        ? gmdate(
            'Y-m-d H:i:s',
            strtotime($approved_batch['approved_at_gmt'] . ' UTC')
                + RAOS_Codex_MCP_Store::TTL_SECONDS
        )
        : null;
    if (! is_string($expected_approval_expiry)
        || ! hash_equals($expected_approval_expiry, $approved_batch['expires_at_gmt'])) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_TTL_NOT_REBOUND\n");
        exit(71);
    }
    foreach ($rows as $row) {
        $readback = RAOS_Codex_MCP_Store::get($row['proposal_id']);
        if (is_wp_error($readback)
            || 'APPROVED' !== $readback['state']
            || ! hash_equals($expected_approval_expiry, $readback['expires_at_gmt'])
            || is_wp_error(RAOS_Codex_MCP_Deployment::validate_approval_lease($readback))) {
            fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_COMMITTED_LEASE_LOST\n");
            exit(71);
        }
    }
    $replaced_payload = file_get_contents($blocked_path);
    $replaced_lease = is_string($replaced_payload)
        ? json_decode($replaced_payload, true)
        : null;
    if (! is_array($replaced_lease)
        || 'RAOS_CODEX_APPROVAL_LEASE_V1' !== $replaced_lease['schema']) {
        fwrite(STDERR, "RAOS_E2E_BATCH_APPROVAL_ORPHAN_NOT_REPLACED\n");
        exit(71);
    }
    fwrite(STDOUT, "RAOS_E2E_BATCH_APPROVAL_CRASH_CONSISTENCY_OK\n");
    exit(0);
}

if ('claim-ambiguous-reset' === $mode) {
    $subset_ids = array_slice($batch['proposal_ids'], 0, -1);
    $subset_claim = RAOS_Codex_MCP_Store::claim_publication_batch_apply(
        $batch['batch_token'],
        $batch['batch_manifest_sha256'],
        $subset_ids
    );
    if (! is_wp_error($subset_claim)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_SUBSET_ACCEPTED\n");
        exit(72);
    }

    $authoritative_wpdb = $wpdb;
    $ambiguous_wpdb = new RAOS_E2E_Ambiguous_Commit_WPDB(
        DB_USER,
        DB_PASSWORD,
        DB_NAME,
        DB_HOST
    );
    $prefix_result = $ambiguous_wpdb->set_prefix($authoritative_wpdb->prefix);
    if (is_wp_error($prefix_result)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_DB_INJECTION_FAILED\n");
        exit(72);
    }
    $ambiguous_wpdb->arm_ambiguous_commit();
    $wpdb = $ambiguous_wpdb;
    try {
        $claimed = RAOS_Codex_MCP_Store::claim_publication_batch_apply(
            $batch['batch_token'],
            $batch['batch_manifest_sha256'],
            $batch['proposal_ids']
        );
    } finally {
        $wpdb = $authoritative_wpdb;
    }
    if (is_wp_error($claimed)
        || 'RAOSWordPressPublicationBatchClaimV1' !== $claimed['schema']
        || $batch['proposal_ids'] !== $claimed['proposal_ids']
        || count($batch['proposal_ids']) !== (int) $claimed['proposal_count']) {
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_AMBIGUOUS_COMMIT_FAILED\n");
        exit(72);
    }
    foreach ($claimed['proposals'] as $operation) {
        if (! is_array($operation)
            || 'APPLYING' !== $operation['state']
            || 'BATCH_CLAIMED' !== $operation['result_code']) {
            fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_PARTIAL_STATE\n");
            exit(72);
        }
    }
    $replayed = RAOS_Codex_MCP_Store::claim_publication_batch_apply(
        $batch['batch_token'],
        $batch['batch_manifest_sha256'],
        $batch['proposal_ids']
    );
    if (is_wp_error($replayed)
        || RAOS_Codex_MCP_Store::canonical_json($claimed)
            !== RAOS_Codex_MCP_Store::canonical_json($replayed)) {
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_REPLAY_FAILED\n");
        exit(72);
    }

    if (false === $wpdb->query('START TRANSACTION')) {
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_RESET_FAILED\n");
        exit(72);
    }
    $reset_ok = true;
    foreach ($batch['proposal_ids'] as $proposal_id) {
        $reset = $wpdb->query(
            $wpdb->prepare(
                'UPDATE ' . RAOS_Codex_MCP_Store::table_name()
                . " SET state = 'APPROVED', result_code = 'PROPOSAL_APPROVED', applying_at_gmt = NULL"
                . " WHERE proposal_id = %s AND state = 'APPLYING'"
                . " AND result_code = 'BATCH_CLAIMED'",
                $proposal_id
            )
        );
        if (1 !== $reset) {
            $reset_ok = false;
        }
    }
    $batch_reset = $wpdb->query(
        $wpdb->prepare(
            'UPDATE ' . RAOS_Codex_MCP_Store::batch_table_name()
            . ' SET applying_at_gmt = NULL'
            . " WHERE batch_token = %s AND state = 'APPROVED'"
            . ' AND applying_at_gmt = %s',
            $batch['batch_token'],
            gmdate('Y-m-d H:i:s', strtotime($claimed['batch_claimed_at_gmt']))
        )
    );
    if (! $reset_ok || 1 !== $batch_reset || false === $wpdb->query('COMMIT')) {
        $wpdb->query('ROLLBACK');
        fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_RESET_FAILED\n");
        exit(72);
    }
    foreach ($batch['proposal_ids'] as $proposal_id) {
        $readback = RAOS_Codex_MCP_Store::get($proposal_id);
        if (is_wp_error($readback) || 'APPROVED' !== $readback['state']) {
            fwrite(STDERR, "RAOS_E2E_BATCH_CLAIM_RESET_READBACK_FAILED\n");
            exit(72);
        }
    }
    fwrite(STDOUT, "RAOS_E2E_BATCH_CLAIM_AMBIGUOUS_COMMIT_OK\n");
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
    'reason' => 'Disposable E2E reason verifies ambiguous commit recovery.',
    'hash_suffix' => substr($batch['batch_manifest_sha256'], -8),
);
$_REQUEST = $_POST;

RAOS_Codex_MCP_Abilities::instance()->handle_batch_approval();
