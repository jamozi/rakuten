<?php
/** Concrete rollback, CAS, drift, and receipt-persistence failure injection. */

defined('ABSPATH') || exit;

// The disposable wp-cli service loads the shared wp-config without the web
// service's runtime-only write-gate environment. This harness explicitly opts
// into the same local-only mutation gate as the later HTTP E2E phase.
if (! defined('RAOS_OPERATOR_WRITES_ENABLED')) {
    define('RAOS_OPERATOR_WRITES_ENABLED', true);
}

function raos_e2e_rollback_fail($marker)
{
    fwrite(STDERR, $marker . "\n");
    exit(70);
}

function raos_e2e_rollback_remove_tree($path)
{
    if (! is_string($path) || ! file_exists($path)) {
        return;
    }
    if (is_file($path) || is_link($path)) {
        @unlink($path);
        return;
    }
    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($path, FilesystemIterator::SKIP_DOTS),
        RecursiveIteratorIterator::CHILD_FIRST
    );
    foreach ($iterator as $entry) {
        if ($entry->isFile() || $entry->isLink()) {
            @unlink($entry->getPathname());
        } else {
            @rmdir($entry->getPathname());
        }
    }
    @rmdir($path);
}

function raos_e2e_rollback_method($name)
{
    $method = new ReflectionMethod(RAOS_Codex_MCP_Deployment::class, $name);
    $method->setAccessible(true);
    return $method;
}

function raos_e2e_recovery_required($error)
{
    if (! is_wp_error($error)) {
        return false;
    }
    $data = $error->get_error_data();
    return is_array($data) && true === ($data['recovery_required'] ?? false);
}

function raos_e2e_after_document($before)
{
    $after = $before;
    $after['status'] = 'publish';
    $after['content_sha256'] = RAOS_Codex_MCP_Content::document_hash($after);
    return $after;
}

function raos_e2e_publication_manifest_hash($before, $after)
{
    return RAOS_Codex_MCP_Store::hash(
        array(
            'schema' => 'ContentPublicationManifestV1',
            'target_status' => 'publish',
            'post_type' => $before['post_type'],
            'post_id' => $before['id'],
            'before_sha256' => $before['content_sha256'],
            'after_sha256' => $after['content_sha256'],
            'precondition' => array(
                'revision_id' => $before['revision_id'],
                'modified_gmt' => $before['modified_gmt'],
                'content_sha256' => $before['content_sha256'],
            ),
        )
    );
}

function raos_e2e_content_row($before, $after, $proposal_id)
{
    return array(
        'proposal_id' => $proposal_id,
        'before_sha256' => $before['content_sha256'],
        'after_sha256' => $after['content_sha256'],
        'payload' => array('before' => $before, 'after' => $after),
    );
}

function raos_e2e_create_post($suffix)
{
    $post_id = wp_insert_post(
        array(
            'post_type' => 'post',
            'post_status' => 'draft',
            'post_title' => 'Rollback baseline ' . $suffix,
            'post_name' => 'rollback-baseline-' . $suffix,
            'post_excerpt' => 'Rollback fixture.',
            'post_content' => '<!-- wp:paragraph --><p>Rollback fixture.</p><!-- /wp:paragraph -->',
        ),
        true
    );
    if (is_wp_error($post_id)) {
        raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_POST_CREATE_FAILED');
    }
    return (int) $post_id;
}

wp_set_current_user(1);
$private = RAOS_Codex_MCP_Deployment::private_directory();
if (is_wp_error($private)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_PRIVATE_FAILED');
}
$fixture_root = $private . '/rollback-harness-' . bin2hex(random_bytes(8));
if (! mkdir($fixture_root, 0700, false)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_FIXTURE_FAILED');
}

$install = raos_e2e_rollback_method('install_code_tree');
$restore = raos_e2e_rollback_method('restore_code_before');
$apply_content = raos_e2e_rollback_method('apply_content');
$write_content = raos_e2e_rollback_method('write_content_document');
$begin_content = raos_e2e_rollback_method('begin_content_transaction');
$rollback_content = raos_e2e_rollback_method('rollback_content_transaction');
$cleanup_code = raos_e2e_rollback_method('cleanup_completed_code_operation');
$batch_status_method = raos_e2e_rollback_method('publication_batch_status');
$acquire_publication_lock = raos_e2e_rollback_method('acquire_publication_mutation_lock');
$release_publication_lock = raos_e2e_rollback_method('release_operation_lock');
$deployment = new RAOS_Codex_MCP_Deployment(null);

$held_publication_lock = $acquire_publication_lock->invoke(null);
$contended_publication_lock = $acquire_publication_lock->invoke(null);
$held_publication_lock_valid = is_resource($held_publication_lock);
$release_publication_lock->invoke(null, $held_publication_lock);
if (! $held_publication_lock_valid
    || ! is_wp_error($contended_publication_lock)
    || 'raos_codex_publication_mutation_in_flight'
        !== $contended_publication_lock->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_PUBLICATION_MUTATION_LOCK_FAILED');
}

// Recovery artifacts cannot be deleted until a terminal Store state exists.
$cleanup_id = str_repeat('b', 64);
$cleanup_root = $private . '/operation-' . $cleanup_id;
$cleanup_package = $private . '/package-' . str_repeat('c', 48) . '.zip';
mkdir($cleanup_root, 0700, true);
file_put_contents($cleanup_root . '/before.txt', 'only recovery copy');
file_put_contents($cleanup_package, 'staged package');
chmod($cleanup_package, 0600);
$cleanup_row = array(
    'proposal_id' => $cleanup_id,
    'kind' => 'THEME_RELEASE',
    'state' => 'APPLYING',
    'package_path' => $cleanup_package,
);
$cleanup_code->invoke(null, $cleanup_row);
if (! is_dir($cleanup_root) || ! is_file($cleanup_package)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_PRETERMINAL_CLEANUP_FAILED');
}
$cleanup_row['state'] = 'FAILED';
$cleanup_code->invoke(null, $cleanup_row);
if (file_exists($cleanup_root) || file_exists($cleanup_package)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_TERMINAL_CLEANUP_FAILED');
}

// old -> backup succeeds, new -> target fails, exact backup restore succeeds.
$case = $fixture_root . '/install-restore';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir(dirname($backup), 0700, true);
file_put_contents($target . '/old.txt', 'old');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$result = $install->invoke(
    null,
    $case . '/missing-new',
    $target,
    $backup,
    $before_hash,
    str_repeat('a', 64)
);
if (! is_wp_error($result)
    || 'raos_codex_code_install_failed' !== $result->get_error_code()
    || raos_e2e_recovery_required($result)
    || ! is_dir($target)
    || is_dir($backup)
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_INSTALL_RESTORE_FAILED');
}

// Inject both the install rename failure and backup restore rename failure.
$case = $fixture_root . '/install-restore-failure';
$target = $case . '/target';
$new = $case . '/new';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($new, 0700, true);
mkdir(dirname($backup), 0700, true);
file_put_contents($target . '/old.txt', 'old');
file_put_contents($new . '/new.txt', 'new');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$mover = static function ($source, $destination) use ($target, $new, $backup) {
    if ($source === $target && $destination === $backup) {
        return rename($source, $destination);
    }
    if (($source === $new && $destination === $target)
        || ($source === $backup && $destination === $target)) {
        return false;
    }
    return rename($source, $destination);
};
$result = $install->invoke(
    null,
    $new,
    $target,
    $backup,
    $before_hash,
    RAOS_Codex_MCP_Deployment::tree_hash($new),
    $mover
);
if (! is_wp_error($result)
    || 'raos_codex_code_install_rollback_indeterminate' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || file_exists($target)
    || ! is_dir($backup)
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BACKUP_PRESERVATION_FAILED');
}

// Inject a concurrent edit after target -> backup.  The moved tree must be
// rehashed, restored as the third-party state, and the new tree not installed.
$case = $fixture_root . '/backup-cas';
$target = $case . '/target';
$new = $case . '/new';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($new, 0700, true);
mkdir(dirname($backup), 0700, true);
file_put_contents($target . '/tree.txt', 'expected-before');
file_put_contents($new . '/tree.txt', 'new');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$mover = static function ($source, $destination) use ($target, $backup) {
    $moved = rename($source, $destination);
    if ($moved && $source === $target && $destination === $backup) {
        file_put_contents($backup . '/tree.txt', 'concurrent-third-state');
    }
    return $moved;
};
$result = $install->invoke(
    null,
    $new,
    $target,
    $backup,
    $before_hash,
    RAOS_Codex_MCP_Deployment::tree_hash($new),
    $mover
);
if (! is_wp_error($result)
    || 'raos_codex_code_hash_drift' !== $result->get_error_code()
    || ! is_dir($target)
    || is_dir($backup)
    || 'concurrent-third-state' !== file_get_contents($target . '/tree.txt')
    || file_exists($target . '/new.txt')) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CAS_FAILED');
}

// A present third tree must never be removed to restore the before backup.
$case = $fixture_root . '/third-tree';
$target = $case . '/target';
$backup = $case . '/operation/before';
$after_template = $case . '/after';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
mkdir($after_template, 0700, true);
file_put_contents($target . '/tree.txt', 'third');
file_put_contents($backup . '/tree.txt', 'before');
file_put_contents($after_template . '/tree.txt', 'after');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$third_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    RAOS_Codex_MCP_Deployment::tree_hash($after_template)
);
if (! is_wp_error($result)
    || ! raos_e2e_recovery_required($result)
    || ! hash_equals($third_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CODE_DRIFT_FAILED');
}

// Store::complete() failure after an exact committed after readback must remain
// recoverable.  A deliberately nonexistent proposal injects persistence failure.
$post_id = raos_e2e_create_post('complete');
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = raos_e2e_after_document($before);
$result = $apply_content->invoke(
    $deployment,
    raos_e2e_content_row($before, $after, str_repeat('f', 64)),
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()
);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || ! raos_e2e_recovery_required($result)
    || ! is_array($current)
    || ! hash_equals($after['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_COMPLETE_AMBIGUITY_FAILED');
}
$restored = $write_content->invoke(null, $before);
if (is_wp_error($restored)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_COMPLETE_CLEANUP_FAILED');
}
wp_delete_post($post_id, true);

// Inject a readback mismatch inside the content transaction.  Database rollback
// must restore and verify exact before before the error is terminal-safe.
$post_id = raos_e2e_create_post('readback');
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = raos_e2e_after_document($before);
$inject = static function ($data) {
    $data['post_title'] = 'Injected readback mismatch';
    return $data;
};
add_filter('wp_insert_post_data', $inject, 10, 1);
$result = $apply_content->invoke(
    $deployment,
    raos_e2e_content_row($before, $after, str_repeat('e', 64)),
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()
);
remove_filter('wp_insert_post_data', $inject, 10);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || 'raos_codex_content_readback_failed' !== $result->get_error_code()
    || raos_e2e_recovery_required($result)
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_FAILED');
}
wp_delete_post($post_id, true);

// A theme mismatch observed after the content write but before COMMIT must
// rollback the database transaction to the immutable before document.
$post_id = raos_e2e_create_post('theme-post-readback');
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = raos_e2e_after_document($before);
$expected_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
$theme_root = get_theme_root(RAOS_Codex_MCP_Deployment::THEME_SLUG)
    . '/' . RAOS_Codex_MCP_Deployment::THEME_SLUG;
$post_readback_drift = $theme_root . '/raos-e2e-post-readback-drift.tmp';
file_put_contents($post_readback_drift, 'post-write theme drift');
$result = $apply_content->invoke(
    $deployment,
    raos_e2e_content_row($before, $after, str_repeat('d', 64)),
    $expected_theme_hash
);
$current = RAOS_Codex_MCP_Content::document($post_id);
@unlink($post_readback_drift);
if (! is_wp_error($result)
    || 'raos_codex_content_theme_drift' !== $result->get_error_code()
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_THEME_POSTCHECK_ROLLBACK_FAILED');
}
wp_delete_post($post_id, true);

// Directly inject an unconfirmed rollback against a third state.  It remains
// recoverable and the third state is not overwritten with before.
$post_id = raos_e2e_create_post('rollback-uncertain');
$before = RAOS_Codex_MCP_Content::document($post_id);
wp_update_post(array('ID' => $post_id, 'post_title' => 'Third-party content state'));
$third = RAOS_Codex_MCP_Content::document($post_id);
$result = $rollback_content->invoke(null, $before, $before['content_sha256']);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || ! raos_e2e_recovery_required($result)
    || ! hash_equals($third['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_DRIFT_FAILED');
}
wp_delete_post($post_id, true);

// If SERIALIZABLE cannot be selected for the next transaction, content CAS
// fails before START TRANSACTION and performs no write.
$post_id = raos_e2e_create_post('cas-isolation');
$before = RAOS_Codex_MCP_Content::document($post_id);
global $wpdb;
$wpdb->query('START TRANSACTION');
$suppressing = $wpdb->suppress_errors(true);
$result = $begin_content->invoke(null, $before, $before['content_sha256']);
$wpdb->suppress_errors($suppressing);
$wpdb->query('ROLLBACK');
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || 'raos_codex_content_transaction_isolation_failed' !== $result->get_error_code()
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_ISOLATION_FAILED');
}
wp_delete_post($post_id, true);

// Hold the authoritative content CAS lock and prove an independent wp-admin-like
// SQL writer cannot pass it before the proposal mutation.
$post_id = raos_e2e_create_post('cas-lock');
$before = RAOS_Codex_MCP_Content::document($post_id);
$locked = $begin_content->invoke(null, $before, $before['content_sha256']);
if (is_wp_error($locked)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_CAS_BEGIN_FAILED');
}
mysqli_report(MYSQLI_REPORT_OFF);
$host = DB_HOST;
$port = ini_get('mysqli.default_port');
if (str_contains($host, ':')) {
    list($host, $port) = explode(':', $host, 2);
}
$other = new mysqli($host, DB_USER, DB_PASSWORD, DB_NAME, (int) $port);
$other->query('SET SESSION innodb_lock_wait_timeout = 1');
$escaped_title = $other->real_escape_string('Concurrent writer must block');
$concurrent = $other->query(
    "UPDATE {$wpdb->posts} SET post_title = '{$escaped_title}' WHERE ID = " . (int) $post_id
);
$concurrent_errno = $other->errno;
$other->close();
$rolled_back = $rollback_content->invoke(null, $before, $before['content_sha256']);
if (false !== $concurrent
    || ! in_array($concurrent_errno, array(1205, 3572), true)
    || true !== $rolled_back) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_CAS_FAILED');
}
wp_delete_post($post_id, true);

// Batch status distinguishes resumable response loss from safe TTL reset and
// from partial/drifted sets that must fail closed.
$make_batch_member = static function ($suffix) {
    $post_id = raos_e2e_create_post('batch-' . $suffix);
    $before = RAOS_Codex_MCP_Content::document($post_id);
    $after = raos_e2e_after_document($before);
    $row = RAOS_Codex_MCP_Store::create(
        'CONTENT_RELEASE',
        array(
            'schema' => 'ContentReleaseProposalV1',
            'target_status' => 'publish',
            'before' => $before,
            'after' => $after,
            'before_sha256' => $before['content_sha256'],
            'after_sha256' => $after['content_sha256'],
            'publication_manifest_sha256' => str_repeat('2', 64),
        ),
        $before['content_sha256'],
        $after['content_sha256']
    );
    if (is_wp_error($row)) {
        raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_SETUP_FAILED');
    }
    return array('post_id' => $post_id, 'before' => $before, 'after' => $after, 'row' => $row);
};
$batch_applied = $make_batch_member('applied');
$batch_expired = $make_batch_member('expired');
$written = $write_content->invoke(null, $batch_applied['after']);
if (is_wp_error($written)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_SETUP_FAILED');
}
$past = gmdate('Y-m-d H:i:s', time() - 60);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLIED',
        'result_code' => 'CONTENT_RELEASE_APPLIED',
        'expires_at_gmt' => $past,
        'receipt_json' => wp_json_encode(array('schema' => 'OperationReceiptV1')),
    ),
    array('proposal_id' => $batch_applied['row']['proposal_id'])
);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array('state' => 'APPROVED', 'result_code' => 'PROPOSAL_APPROVED', 'expires_at_gmt' => $past),
    array('proposal_id' => $batch_expired['row']['proposal_id'])
);
$batch_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
if (is_wp_error($batch_theme_hash)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_SETUP_FAILED');
}
$batch_value = static function ($proposal_ids) use ($past, $batch_theme_hash) {
    sort($proposal_ids, SORT_STRING);
    return array(
        'batch_token' => str_repeat('3', 64),
        'batch_manifest_sha256' => str_repeat('4', 64),
        'proposal_ids' => $proposal_ids,
        'manifest' => array('expected_theme_tree_sha256' => $batch_theme_hash),
        'state' => 'APPROVED',
        'expires_at_gmt' => $past,
    );
};
$status = $batch_status_method->invoke(
    null,
    $batch_value(array($batch_applied['row']['proposal_id']))
);
if (! is_array($status)
    || 'APPLIED' !== $status['state']
    || true !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_APPLIED_RESUME_FAILED');
}
$status = $batch_status_method->invoke(
    null,
    $batch_value(
        array(
            $batch_applied['row']['proposal_id'],
            $batch_expired['row']['proposal_id'],
        )
    )
);
if (! is_array($status)
    || 'FAILED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_PARTIAL_EXPIRY_FAILED');
}
$status = $batch_status_method->invoke(
    null,
    $batch_value(array($batch_expired['row']['proposal_id']))
);
if (! is_array($status)
    || 'EXPIRED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_SAFE_EXPIRY_FAILED');
}
wp_update_post(
    array('ID' => $batch_expired['post_id'], 'post_title' => 'Expired member drift')
);
$status = $batch_status_method->invoke(
    null,
    $batch_value(array($batch_expired['row']['proposal_id']))
);
if (! is_array($status)
    || 'EXPIRED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_DRIFT_EXPIRY_FAILED');
}
foreach (array($batch_applied, $batch_expired) as $batch_member) {
    $wpdb->delete(
        RAOS_Codex_MCP_Store::table_name(),
        array('proposal_id' => $batch_member['row']['proposal_id'])
    );
    wp_delete_post($batch_member['post_id'], true);
}

$batch_preclaim = $make_batch_member('preclaim-drift-expiry');
$future = gmdate('Y-m-d H:i:s', time() + 300);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPROVED',
        'result_code' => 'PROPOSAL_APPROVED',
        'expires_at_gmt' => $future,
    ),
    array('proposal_id' => $batch_preclaim['row']['proposal_id'])
);
wp_update_post(
    array('ID' => $batch_preclaim['post_id'], 'post_title' => 'Preclaim drift')
);
$preclaim_batch = array(
    'batch_token' => str_repeat('5', 64),
    'batch_manifest_sha256' => str_repeat('6', 64),
    'proposal_ids' => array($batch_preclaim['row']['proposal_id']),
    'manifest' => array('expected_theme_tree_sha256' => $batch_theme_hash),
    'state' => 'APPROVED',
    'expires_at_gmt' => $future,
);
$status = $batch_status_method->invoke(null, $preclaim_batch);
if (! is_array($status)
    || 'FAILED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_PRECLAIM_DRIFT_FAILED');
}
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array('expires_at_gmt' => $past),
    array('proposal_id' => $batch_preclaim['row']['proposal_id'])
);
$preclaim_batch['expires_at_gmt'] = $past;
$status = $batch_status_method->invoke(null, $preclaim_batch);
if (! is_array($status)
    || 'EXPIRED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_BATCH_PRECLAIM_EXPIRY_FAILED');
}
$wpdb->delete(
    RAOS_Codex_MCP_Store::table_name(),
    array('proposal_id' => $batch_preclaim['row']['proposal_id'])
);
wp_delete_post($batch_preclaim['post_id'], true);

// A claimed theme member is bound to the active child theme, not merely to an
// inactive directory with the same slug and tree hash.
$active_theme_before = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
$theme_row = RAOS_Codex_MCP_Store::create(
    'THEME_RELEASE',
    array(
        'schema' => 'CodeReleaseProposalV1',
        'kind' => 'THEME_RELEASE',
        'code_package' => array(
            'kind' => 'theme',
            'slug' => RAOS_Codex_MCP_Deployment::THEME_SLUG,
        ),
    ),
    $active_theme_before,
    str_repeat('7', 64)
);
if (is_wp_error($active_theme_before) || is_wp_error($theme_row)) {
    raos_e2e_rollback_fail('RAOS_E2E_THEME_ACTIVE_BINDING_SETUP_FAILED');
}
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'BATCH_CLAIMED',
        'applying_at_gmt' => gmdate('Y-m-d H:i:s'),
    ),
    array('proposal_id' => $theme_row['proposal_id'])
);
$theme_batch = array(
    'batch_token' => str_repeat('8', 64),
    'batch_manifest_sha256' => str_repeat('9', 64),
    'proposal_ids' => array($theme_row['proposal_id']),
    'manifest' => array('expected_theme_tree_sha256' => str_repeat('7', 64)),
    'state' => 'APPROVED',
    'expires_at_gmt' => $future,
);
switch_theme('twentytwentyfive');
$status = $batch_status_method->invoke(null, $theme_batch);
switch_theme(RAOS_Codex_MCP_Deployment::THEME_SLUG);
if (! is_array($status)
    || 'FAILED' !== $status['state']
    || false !== $status['preconditions_ready']) {
    raos_e2e_rollback_fail('RAOS_E2E_THEME_ACTIVE_BINDING_SWITCH_FAILED');
}
$wpdb->delete(
    RAOS_Codex_MCP_Store::table_name(),
    array('proposal_id' => $theme_row['proposal_id'])
);

// A content-only publication batch binds the exact active child-theme tree in
// its reviewed manifest. Drift must stop approval, atomic claim, and member
// apply; restoring the reviewed tree must allow the normal path to complete.
$post_id = raos_e2e_create_post('content-only-theme-binding');
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = raos_e2e_after_document($before);
$payload = array(
    'schema' => 'ContentReleaseProposalV1',
    'target_status' => 'publish',
    'before' => $before,
    'after' => $after,
    'before_sha256' => $before['content_sha256'],
    'after_sha256' => $after['content_sha256'],
    'publication_manifest_sha256' => raos_e2e_publication_manifest_hash($before, $after),
);
$row = RAOS_Codex_MCP_Store::create(
    'CONTENT_RELEASE',
    $payload,
    $before['content_sha256'],
    $after['content_sha256']
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$baseline_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
$theme_root = get_theme_root(RAOS_Codex_MCP_Deployment::THEME_SLUG)
    . '/' . RAOS_Codex_MCP_Deployment::THEME_SLUG;
$drift_path = $theme_root . '/raos-e2e-content-only-theme-drift-'
    . bin2hex(random_bytes(6)) . '.tmp';
if (is_wp_error($baseline_theme_hash)
    || false === file_put_contents($drift_path, 'drift-before-registration')) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$result = RAOS_Codex_MCP_Store::register_publication_batch(
    array($row['proposal_id']),
    $baseline_theme_hash
);
if (! is_wp_error($result)
    || 'raos_codex_publication_batch_theme_drift' !== $result->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_REGISTER_DRIFT_FAILED');
}
@unlink($drift_path);
$batch = RAOS_Codex_MCP_Store::register_publication_batch(
    array($row['proposal_id']),
    $baseline_theme_hash
);
if (is_wp_error($batch)
    || ! isset($batch['manifest']['expected_theme_tree_sha256'])
    || ! RAOS_Codex_MCP_Store::is_sha256($batch['manifest']['expected_theme_tree_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
if (! hash_equals(
        $baseline_theme_hash,
        $batch['manifest']['expected_theme_tree_sha256']
    )) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$approver_login = 'raos-theme-binding-' . bin2hex(random_bytes(6));
$approver_id = wp_insert_user(
    array(
        'user_login' => $approver_login,
        'user_email' => $approver_login . '@example.invalid',
        'user_pass' => wp_generate_password(32, true, true),
        'role' => 'administrator',
    )
);
if (is_wp_error($approver_id)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
if (false === file_put_contents($drift_path, 'drift-before-approval')) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$result = RAOS_Codex_MCP_Store::approve_publication_batch(
    $batch['batch_token'],
    $batch['batch_manifest_sha256'],
    (int) $approver_id,
    'Independent E2E theme binding approval.'
);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$stored_batch = RAOS_Codex_MCP_Store::get_publication_batch($batch['batch_token']);
if (! is_wp_error($result)
    || 'raos_codex_approval_batch_hash_drift' !== $result->get_error_code()
    || is_wp_error($stored)
    || 'PENDING' !== $stored['state']
    || is_wp_error($stored_batch)
    || 'REGISTERED' !== $stored_batch['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_APPROVAL_DRIFT_FAILED');
}
@unlink($drift_path);
$restored_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
if (is_wp_error($restored_theme_hash)
    || ! hash_equals($baseline_theme_hash, $restored_theme_hash)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_APPROVAL_DRIFT_FAILED');
}
$approved = RAOS_Codex_MCP_Store::approve_publication_batch(
    $batch['batch_token'],
    $batch['batch_manifest_sha256'],
    (int) $approver_id,
    'Independent E2E theme binding approval.'
);
if (is_wp_error($approved)
    || 'RAOSWordPressPublicationBatchApprovalResultV1' !== ($approved['schema'] ?? null)) {
    raos_e2e_rollback_fail(
        'RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_APPROVAL_FAILED_'
        . (is_wp_error($approved) ? $approved->get_error_code() : 'SCHEMA')
    );
}
if (false === file_put_contents($drift_path, 'drift-before-claim')) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$result = RAOS_Codex_MCP_Store::claim_publication_batch_apply(
    $batch['batch_token'],
    $batch['batch_manifest_sha256'],
    $batch['proposal_ids']
);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_wp_error($result)
    || 'raos_codex_publication_batch_claim_theme_drift' !== $result->get_error_code()
    || is_wp_error($stored)
    || 'APPROVED' !== $stored['state']
    || 'PROPOSAL_APPROVED' !== $stored['result_code']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_CLAIM_DRIFT_FAILED');
}
@unlink($drift_path);
$claimed = RAOS_Codex_MCP_Store::claim_publication_batch_apply(
    $batch['batch_token'],
    $batch['batch_manifest_sha256'],
    $batch['proposal_ids']
);
if (is_wp_error($claimed)
    || 'RAOSWordPressPublicationBatchClaimV1' !== ($claimed['schema'] ?? null)) {
    raos_e2e_rollback_fail(
        'RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_CLAIM_FAILED_'
        . (is_wp_error($claimed) ? $claimed->get_error_code() : 'SCHEMA')
    );
}
$apply_request = new WP_REST_Request('POST', '/');
$apply_request->set_url_params(array('proposal_id' => $row['proposal_id']));
$apply_request->set_header('If-Match', '"' . $row['proposal_id'] . '"');
$apply_request->set_header('Idempotency-Key', $row['proposal_id']);
$apply_request->set_header('X-RAOS-Batch-Token', $batch['batch_token']);
$apply_request->set_header(
    'X-RAOS-Batch-Manifest-SHA256',
    $batch['batch_manifest_sha256']
);
if (false === file_put_contents($drift_path, 'drift-before-apply')) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_SETUP_FAILED');
}
$result = $deployment->apply_proposal($apply_request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || 'raos_codex_publication_batch_not_ready' !== $result->get_error_code()
    || is_wp_error($stored)
    || 'APPLYING' !== $stored['state']
    || 'BATCH_CLAIMED' !== $stored['result_code']
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_ONLY_THEME_APPLY_DRIFT_FAILED');
}
@unlink($drift_path);
$receipt = $deployment->apply_proposal($apply_request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$current = RAOS_Codex_MCP_Content::document($post_id);
$final_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
if (is_wp_error($receipt)
    || 'OperationReceiptV1' !== ($receipt['schema'] ?? null)
    || is_wp_error($stored)
    || 'APPLIED' !== $stored['state']
    || ! is_array($current)
    || ! hash_equals($after['content_sha256'], $current['content_sha256'])
    || is_wp_error($final_theme_hash)
    || ! hash_equals($baseline_theme_hash, $final_theme_hash)) {
    raos_e2e_rollback_fail(
        'RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_APPLY_FAILED_'
        . (is_wp_error($receipt) ? $receipt->get_error_code() : 'STATE')
    );
}
$wpdb->delete(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array('batch_token' => $batch['batch_token'])
);
$wpdb->delete(
    RAOS_Codex_MCP_Store::table_name(),
    array('proposal_id' => $row['proposal_id'])
);
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
wp_delete_post($post_id, true);
require_once ABSPATH . 'wp-admin/includes/user.php';
wp_delete_user((int) $approver_id);

// Recover on an APPLYING content operation with a third hash must not write the
// immutable before document over the later edit.
$post_id = raos_e2e_create_post('recover-drift');
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = raos_e2e_after_document($before);
$payload = array(
    'schema' => 'ContentReleaseProposalV1',
    'target_status' => 'publish',
    'before' => $before,
    'after' => $after,
    'before_sha256' => $before['content_sha256'],
    'after_sha256' => $after['content_sha256'],
    'publication_manifest_sha256' => str_repeat('1', 64),
);
$row = RAOS_Codex_MCP_Store::create(
    'CONTENT_RELEASE',
    $payload,
    $before['content_sha256'],
    $after['content_sha256']
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_DRIFT_SETUP_FAILED');
}
wp_update_post(array('ID' => $post_id, 'post_title' => 'Later human edit'));
$third = RAOS_Codex_MCP_Content::document($post_id);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'OPERATION_APPLYING',
        'applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$request = new WP_REST_Request('POST', '/');
$request->set_url_params(array('operation_id' => $row['proposal_id']));
$result = $deployment->recover_operation($request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($result)
    || 'raos_codex_recovery_content_drift' !== $result->get_error_code()
    || is_wp_error($stored)
    || 'APPLYING' !== $stored['state']
    || ! hash_equals($third['content_sha256'], $current['content_sha256'])) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CONTENT_RECOVER_DRIFT_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
wp_delete_post($post_id, true);

// Equivalent public recover drift test for a code tree with a preserved backup.
$slug = 'raos-e2e-recovery-drift';
$target = WP_PLUGIN_DIR . '/' . $slug;
$old_template = $fixture_root . '/code-old';
$after_template = $fixture_root . '/code-after';
mkdir($target, 0700, true);
mkdir($old_template, 0700, true);
mkdir($after_template, 0700, true);
file_put_contents($target . '/tree.txt', 'third');
file_put_contents($old_template . '/tree.txt', 'before');
file_put_contents($after_template . '/tree.txt', 'after');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($old_template);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($after_template);
$row = RAOS_Codex_MCP_Store::create(
    'PLUGIN_CHANGE',
    array(
        'schema' => 'CodeReleaseProposalV1',
        'kind' => 'PLUGIN_CHANGE',
        'code_package' => array('kind' => 'plugin', 'slug' => $slug),
    ),
    $before_hash,
    $after_hash
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CODE_DRIFT_SETUP_FAILED');
}
$operation_root = $private . '/operation-' . $row['proposal_id'];
$backup = $operation_root . '/before';
mkdir($operation_root, 0700, true);
rename($old_template, $backup);
$third_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'OPERATION_APPLYING',
        'applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$request = new WP_REST_Request('POST', '/');
$request->set_url_params(array('operation_id' => $row['proposal_id']));
$result = $deployment->recover_operation($request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_wp_error($result)
    || 'raos_codex_recovery_code_drift' !== $result->get_error_code()
    || is_wp_error($stored)
    || 'APPLYING' !== $stored['state']
    || ! hash_equals($third_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_CODE_RECOVER_DRIFT_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
raos_e2e_rollback_remove_tree($operation_root);
raos_e2e_rollback_remove_tree($target);

raos_e2e_rollback_remove_tree($fixture_root);
fwrite(STDOUT, "RAOS_E2E_ROLLBACK_OK\n");
