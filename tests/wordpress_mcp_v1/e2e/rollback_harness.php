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

function raos_e2e_rollback_copy_tree($source, $destination)
{
    if (! is_dir($source) || file_exists($destination)
        || ! mkdir($destination, 0700, true)) {
        return false;
    }
    $root = realpath($source);
    if (! is_string($root)) {
        return false;
    }
    $iterator = new RecursiveIteratorIterator(
        new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
        RecursiveIteratorIterator::SELF_FIRST
    );
    foreach ($iterator as $entry) {
        if ($entry->isLink()) {
            return false;
        }
        $relative = substr($entry->getPathname(), strlen($root) + 1);
        $target = $destination . '/' . $relative;
        if (($entry->isDir() && ! mkdir($target, 0700, false))
            || ($entry->isFile() && ! copy($entry->getPathname(), $target))) {
            return false;
        }
    }
    return true;
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
$invalidate_php = raos_e2e_rollback_method('invalidate_php_manifest');
$tree_manifest = raos_e2e_rollback_method('tree_manifest');
$apply_content = raos_e2e_rollback_method('apply_content');
$complete_recovered_content = raos_e2e_rollback_method('complete_recovered_content');
$complete_recovered_code = raos_e2e_rollback_method('complete_recovered_code');
$finalize_applied = raos_e2e_rollback_method('finalize_applied_receipt');
$write_content = raos_e2e_rollback_method('write_content_document');
$begin_content = raos_e2e_rollback_method('begin_content_transaction');
$rollback_content = raos_e2e_rollback_method('rollback_content_transaction');
$cleanup_code = raos_e2e_rollback_method('cleanup_completed_code_operation');
$batch_status_method = raos_e2e_rollback_method('publication_batch_status');
$acquire_publication_lock = raos_e2e_rollback_method('acquire_publication_mutation_lock');
$release_publication_lock = raos_e2e_rollback_method('release_operation_lock');
$deployment = new RAOS_Codex_MCP_Deployment(null);

// Deferred cleanup never reports success while a broken recovery symlink is
// still present. This fixes both the approval-lease and code-operation paths.
$broken_lease_id = hash('sha256', 'raos-e2e-broken-recovery-lease');
$broken_lease = $private . '/approval-lease-' . $broken_lease_id . '.json';
symlink($fixture_root . '/missing-lease-target', $broken_lease);
$broken_lease_row = array(
    'proposal_id' => $broken_lease_id,
    'kind' => 'CONTENT_RELEASE',
    'state' => 'APPLIED',
    'receipt' => array('state' => 'APPLIED'),
);
$broken_lease_result = $finalize_applied->invoke(null, $broken_lease_row);
if (! is_wp_error($broken_lease_result)
    || 'raos_codex_recovery_cleanup_indeterminate' !== $broken_lease_result->get_error_code()
    || ! is_link($broken_lease)) {
    raos_e2e_rollback_fail('RAOS_E2E_RECOVERY_BROKEN_LEASE_CLEANUP_FAILED');
}
@unlink($broken_lease);

$broken_root_id = hash('sha256', 'raos-e2e-broken-recovery-root');
$broken_root = $private . '/operation-' . $broken_root_id;
$theme_target = get_theme_root(RAOS_Codex_MCP_Deployment::THEME_SLUG)
    . '/' . RAOS_Codex_MCP_Deployment::THEME_SLUG;
$theme_hash = RAOS_Codex_MCP_Deployment::tree_hash($theme_target);
symlink($fixture_root . '/missing-operation-target', $broken_root);
$broken_root_row = array(
    'proposal_id' => $broken_root_id,
    'kind' => 'THEME_RELEASE',
    'state' => 'APPLIED',
    'after_sha256' => $theme_hash,
    'payload' => array(
        'code_package' => array(
            'kind' => 'theme',
            'slug' => RAOS_Codex_MCP_Deployment::THEME_SLUG,
        ),
    ),
    'receipt' => array('state' => 'APPLIED'),
);
$broken_root_result = $finalize_applied->invoke(null, $broken_root_row);
if (is_wp_error($theme_hash)
    || ! is_wp_error($broken_root_result)
    || 'raos_codex_recovery_cleanup_indeterminate' !== $broken_root_result->get_error_code()
    || ! is_link($broken_root)) {
    raos_e2e_rollback_fail('RAOS_E2E_RECOVERY_BROKEN_ROOT_CLEANUP_FAILED');
}
@unlink($broken_root);

// The installed descriptor manifest is the sole invalidation allow-list. Only
// its exact PHP path is invalidated and force=true is mandatory. The injected
// true result models WordPress's success result when there is nothing cached.
$case = $fixture_root . '/opcache-exact-manifest';
mkdir($case, 0700, true);
file_put_contents($case . '/runtime.php', "<?php return 'fresh';\n");
file_put_contents($case . '/asset.css', "body{}\n");
$runtime = file_get_contents($case . '/runtime.php');
$asset = file_get_contents($case . '/asset.css');
$manifest = array(
    array(
        'path' => 'asset.css',
        'size' => strlen($asset),
        'sha256' => hash('sha256', $asset),
    ),
    array(
        'path' => 'runtime.php',
        'size' => strlen($runtime),
        'sha256' => hash('sha256', $runtime),
    ),
);
$invalidated_paths = array();
$recording_invalidator = static function ($path, $force) use (&$invalidated_paths) {
    $invalidated_paths[] = array($path, $force);
    return true;
};
$result = $invalidate_php->invoke(null, $case, $manifest, $recording_invalidator, true);
if (true !== $result
    || array(array(realpath($case . '/runtime.php'), true)) !== $invalidated_paths) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_EXACT_MANIFEST_FAILED');
}

// An update must invalidate the before tree while removed PHP paths still
// resolve, then invalidate the installed after manifest. Otherwise an opcode
// for a deleted PHP file can survive when timestamp validation is disabled.
$case = $fixture_root . '/opcache-removed-php';
mkdir($case, 0700, true);
file_put_contents($case . '/removed.php', "<?php return 'removed';\n");
file_put_contents($case . '/shared.php', "<?php return 'before';\n");
$removed_path = realpath($case . '/removed.php');
$removed = file_get_contents($case . '/removed.php');
$shared_before = file_get_contents($case . '/shared.php');
$before_manifest = array(
    array(
        'path' => 'removed.php',
        'size' => strlen($removed),
        'sha256' => hash('sha256', $removed),
    ),
    array(
        'path' => 'shared.php',
        'size' => strlen($shared_before),
        'sha256' => hash('sha256', $shared_before),
    ),
);
$invalidated_paths = array();
$result = $invalidate_php->invoke(
    null,
    $case,
    $before_manifest,
    $recording_invalidator,
    true
);
unlink($case . '/removed.php');
file_put_contents($case . '/shared.php', "<?php return 'after';\n");
$shared_after = file_get_contents($case . '/shared.php');
$after_manifest = array(
    array(
        'path' => 'shared.php',
        'size' => strlen($shared_after),
        'sha256' => hash('sha256', $shared_after),
    ),
);
$after_result = $invalidate_php->invoke(
    null,
    $case,
    $after_manifest,
    $recording_invalidator,
    true,
    $before_manifest
);
$shared_path = realpath($case . '/shared.php');
if (true !== $result
    || true !== $after_result
    || ! is_string($removed_path)
    || array(
        array($removed_path, true),
        array($shared_path, true),
        array($shared_path, true),
        array($removed_path, true),
    ) !== $invalidated_paths) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_REMOVED_PHP_FAILED');
}

// Linux OPcache keys are case-sensitive absolute paths. A case-only rename
// must invalidate both the new file and the absent old spelling.
$case = $fixture_root . '/opcache-case-only-rename';
mkdir($case, 0700, true);
file_put_contents($case . '/foo.php', "<?php return 'after';\n");
$case_after = file_get_contents($case . '/foo.php');
$case_after_manifest = array(
    array(
        'path' => 'foo.php',
        'size' => strlen($case_after),
        'sha256' => hash('sha256', $case_after),
    ),
);
$case_before_manifest = array(
    array(
        'path' => 'Foo.php',
        'size' => strlen("<?php return 'before';\n"),
        'sha256' => hash('sha256', "<?php return 'before';\n"),
    ),
);
$invalidated_paths = array();
$result = $invalidate_php->invoke(
    null,
    $case,
    $case_after_manifest,
    $recording_invalidator,
    true,
    $case_before_manifest
);
if (true !== $result
    || array(
        array(realpath($case . '/foo.php'), true),
        array(realpath($case) . '/Foo.php', true),
    ) !== $invalidated_paths) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_CASE_ONLY_RENAME_FAILED');
}

// An unavailable or SAPI-disabled OPcache engine has no stale entries, so it
// is a safe no-op even when no invalidator can be called.
$result = $invalidate_php->invoke(
    null,
    $case,
    $manifest,
    'raos_e2e_missing_opcache_invalidator',
    false
);
if (true !== $result) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_INACTIVE_NOOP_FAILED');
}
$result = $invalidate_php->invoke(null, $case, $manifest);
if (true !== $result) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_CLI_INACTIVE_PROOF_FAILED');
}

// Missing capability and a false invalidation result both fail closed.
$result = $invalidate_php->invoke(
    null,
    $case,
    $manifest,
    'raos_e2e_missing_opcache_invalidator',
    true
);
if (! is_wp_error($result)
    || 'raos_codex_opcache_invalidation_unavailable' !== $result->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_UNAVAILABLE_FAILED');
}
$result = $invalidate_php->invoke(
    null,
    $case,
    $manifest,
    static function () {
        return false;
    },
    true
);
if (! is_wp_error($result)
    || 'raos_codex_opcache_invalidation_failed' !== $result->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_FALSE_RESULT_FAILED');
}

// A manifest path cannot escape through traversal or a symlink, even when its
// size and digest otherwise describe a real PHP file.
$outside = $fixture_root . '/outside.php';
file_put_contents($outside, "<?php return 'outside';\n");
$outside_payload = file_get_contents($outside);
$unsafe_manifest = array(
    array(
        'path' => '../outside.php',
        'size' => strlen($outside_payload),
        'sha256' => hash('sha256', $outside_payload),
    ),
);
$result = $invalidate_php->invoke(
    null,
    $case,
    $unsafe_manifest,
    $recording_invalidator,
    true
);
if (! is_wp_error($result)
    || 'raos_codex_opcache_manifest_invalid' !== $result->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_TRAVERSAL_FAILED');
}
symlink($outside, $case . '/linked.php');
$linked_manifest = array(
    array(
        'path' => 'linked.php',
        'size' => strlen($outside_payload),
        'sha256' => hash('sha256', $outside_payload),
    ),
);
$result = $invalidate_php->invoke(
    null,
    $case,
    $linked_manifest,
    $recording_invalidator,
    true
);
if (! is_wp_error($result)
    || 'raos_codex_opcache_path_invalid' !== $result->get_error_code()) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_SYMLINK_FAILED');
}

// Rollback re-invalidates the restored PHP path. If that invalidation cannot
// be confirmed, bytes remain exactly restored but the result stays recoverable.
$case = $fixture_root . '/opcache-rollback';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
file_put_contents($target . '/runtime.php', "<?php return 'after';\n");
file_put_contents($backup . '/runtime.php', "<?php return 'before';\n");
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$invalidated_paths = array();
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    $after_hash,
    null,
    $recording_invalidator,
    true
);
if (true !== $result
    || array(array(realpath($target . '/runtime.php'), true)) !== $invalidated_paths
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_ROLLBACK_INVALIDATION_FAILED');
}

$case = $fixture_root . '/opcache-rollback-failure';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
file_put_contents($target . '/runtime.php', "<?php return 'after';\n");
file_put_contents($backup . '/runtime.php', "<?php return 'before';\n");
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    $after_hash,
    null,
    static function () {
        return false;
    },
    true
);
if (! is_wp_error($result)
    || 'raos_codex_code_rollback_opcache_indeterminate' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || is_dir($backup)
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_ROLLBACK_RECOVERY_FAILED');
}

// After rollback, invalidate the restored before manifest plus any new-only
// PHP path that disappeared with the rejected after tree.
$case = $fixture_root . '/opcache-rollback-new-only';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
file_put_contents($target . '/shared.php', "<?php return 'after';\n");
file_put_contents($target . '/new-only.php', "<?php return 'new';\n");
file_put_contents($backup . '/shared.php', "<?php return 'before';\n");
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$after_manifest = $tree_manifest->invoke(null, $target);
$new_only_path = realpath($target . '/new-only.php');
$invalidated_paths = array();
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    $after_hash,
    null,
    $recording_invalidator,
    true,
    $after_manifest
);
$restored_shared = realpath($target . '/shared.php');
if (true !== $result
    || ! is_string($new_only_path)
    || array(
        array($restored_shared, true),
        array($new_only_path, true),
    ) !== $invalidated_paths
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_OPCACHE_ROLLBACK_NEW_ONLY_FAILED');
}

// Equal before/after hashes are not permission to delete a live tree. A
// missing exact backup fails before remove_tree(), leaving the target intact.
$case = $fixture_root . '/equal-hash-missing-backup';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
file_put_contents($target . '/runtime.php', "<?php return 'same';\n");
$equal_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $equal_hash,
    $equal_hash,
    null,
    $recording_invalidator,
    true
);
if (! is_wp_error($result)
    || 'raos_codex_code_rollback_backup_indeterminate' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || ! is_dir($target)
    || ! hash_equals($equal_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_MISSING_BACKUP_FAILED');
}

// With exact equal-hash backup evidence, rollback may replace the target. A
// failed runtime invalidation still leaves exact before bytes recoverable.
$case = $fixture_root . '/equal-hash-exact-backup';
$target = $case . '/target';
$backup = $case . '/operation/before';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
file_put_contents($target . '/runtime.php', "<?php return 'same';\n");
file_put_contents($backup . '/runtime.php', "<?php return 'same';\n");
$equal_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $equal_hash,
    $equal_hash,
    null,
    static function () {
        return false;
    },
    true
);
if (! is_wp_error($result)
    || 'raos_codex_code_rollback_opcache_indeterminate' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || is_dir($backup)
    || ! is_dir($target)
    || ! hash_equals($equal_hash, RAOS_Codex_MCP_Deployment::tree_hash($target))) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_EXACT_BACKUP_FAILED');
}

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

// Inject an updater mutation exactly after target -> private quarantine. The
// quarantined third state is atomically restored to the live path and is never
// recursively deleted based on the earlier target hash.
$case = $fixture_root . '/rollback-quarantine-race';
$target = $case . '/target';
$backup = $case . '/operation/before';
$after_template = $case . '/after';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
mkdir($after_template, 0700, true);
file_put_contents($target . '/tree.txt', 'after');
file_put_contents($backup . '/tree.txt', 'before');
file_put_contents($after_template . '/tree.txt', 'after');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($after_template);
$quarantine = dirname($backup) . '/after-quarantine';
$mover = static function ($source, $destination) use ($target, $quarantine) {
    $moved = rename($source, $destination);
    if ($moved && $source === $target && $destination === $quarantine) {
        file_put_contents($quarantine . '/tree.txt', 'racing-third-state');
    }
    return $moved;
};
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    $after_hash,
    $mover
);
if (! is_wp_error($result)
    || 'raos_codex_code_rollback_after_drift' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || ! is_dir($target)
    || is_dir($quarantine)
    || 'racing-third-state' !== file_get_contents($target . '/tree.txt')
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_QUARANTINE_RACE_FAILED');
}

// If an updater recreates the live path after quarantine, preserve both that
// new live tree and the exact quarantined after tree for manual recovery.
$case = $fixture_root . '/rollback-quarantine-recreated-target';
$target = $case . '/target';
$backup = $case . '/operation/before';
$after_template = $case . '/after';
mkdir($target, 0700, true);
mkdir($backup, 0700, true);
mkdir($after_template, 0700, true);
file_put_contents($target . '/tree.txt', 'after');
file_put_contents($backup . '/tree.txt', 'before');
file_put_contents($after_template . '/tree.txt', 'after');
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($backup);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($after_template);
$quarantine = dirname($backup) . '/after-quarantine';
$mover = static function ($source, $destination) use ($target, $quarantine) {
    $moved = rename($source, $destination);
    if ($moved && $source === $target && $destination === $quarantine) {
        mkdir($target, 0700, true);
        file_put_contents($target . '/tree.txt', 'new-live-third-state');
    }
    return $moved;
};
$result = $restore->invoke(
    null,
    $target,
    $backup,
    $before_hash,
    $after_hash,
    $mover
);
if (! is_wp_error($result)
    || ! raos_e2e_recovery_required($result)
    || 'new-live-third-state' !== file_get_contents($target . '/tree.txt')
    || 'after' !== file_get_contents($quarantine . '/tree.txt')
    || ! hash_equals($before_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_ROLLBACK_RECREATED_TARGET_FAILED');
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

// An equivalent published release is still an exact CAS assertion in the
// approved batch, but applying it must not create a revision or rewrite terms.
// The post and taxonomy rows stay locked while content and theme are read back.
$post_id = raos_e2e_create_post('equivalent-release');
$draft = RAOS_Codex_MCP_Content::document($post_id);
$published = raos_e2e_after_document($draft);
$published_write = $write_content->invoke(null, $published);
if (is_wp_error($published_write)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_SETUP_FAILED');
}
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = $before;
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
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_SETUP_FAILED');
}
global $wpdb;
$prepared = $wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'OPERATION_APPLYING',
        'applying_at_gmt' => RAOS_Codex_MCP_Store::now_mysql(),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$row = 1 === $prepared ? RAOS_Codex_MCP_Store::get($row['proposal_id']) : null;
if (! is_array($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_SETUP_FAILED');
}
$revision_count = count(wp_get_post_revisions($post_id));
$post_writes = 0;
$taxonomy_writes = 0;
$record_post_write = static function ($updated_post_id) use ($post_id, &$post_writes) {
    if ((int) $updated_post_id === $post_id) {
        ++$post_writes;
    }
};
$record_taxonomy_write = static function ($object_id) use ($post_id, &$taxonomy_writes) {
    if ((int) $object_id === $post_id) {
        ++$taxonomy_writes;
    }
};
add_action('post_updated', $record_post_write, 10, 1);
add_action('set_object_terms', $record_taxonomy_write, 10, 1);
$result = $apply_content->invoke(
    $deployment,
    $row,
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()
);
remove_action('post_updated', $record_post_write, 10);
remove_action('set_object_terms', $record_taxonomy_write, 10);
$current = RAOS_Codex_MCP_Content::document($post_id);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_array($result)
    || 'APPLIED' !== $result['state']
    || 'CONTENT_RELEASE_APPLIED' !== $result['result_code']
    || ! hash_equals($before['content_sha256'], $result['before_sha256'])
    || ! hash_equals($after['content_sha256'], $result['after_sha256'])
    || ! is_array($stored)
    || 'APPLIED' !== $stored['state']
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])
    || (int) $before['revision_id'] !== (int) $current['revision_id']
    || ! hash_equals($before['modified_gmt'], $current['modified_gmt'])
    || $revision_count !== count(wp_get_post_revisions($post_id))
    || 0 !== $post_writes
    || 0 !== $taxonomy_writes) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_NO_WRITE_FAILED');
}
$wpdb->delete(
    RAOS_Codex_MCP_Store::table_name(),
    array('proposal_id' => $row['proposal_id'])
);
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

// Recovery for an equivalent release must resolve the one exact claimed batch,
// re-check its theme binding, and replay the locked no-write assertion. Missing,
// duplicate, or manifest-drifted batch bindings remain indeterminate.
$post_id = raos_e2e_create_post('equivalent-recovery');
$draft = RAOS_Codex_MCP_Content::document($post_id);
$published = raos_e2e_after_document($draft);
$published_write = $write_content->invoke(null, $published);
if (is_wp_error($published_write)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_SETUP_FAILED');
}
$before = RAOS_Codex_MCP_Content::document($post_id);
$after = $before;
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
$expected_theme_hash = RAOS_Codex_MCP_Deployment::active_theme_tree_sha256();
$batch = is_wp_error($row)
    ? $row
    : RAOS_Codex_MCP_Store::register_publication_batch(
        array($row['proposal_id']),
        $expected_theme_hash
    );
$approver_login = 'raos-equivalent-recovery-' . bin2hex(random_bytes(6));
$approver_id = wp_insert_user(
    array(
        'user_login' => $approver_login,
        'user_email' => $approver_login . '@example.invalid',
        'user_pass' => wp_generate_password(32, true, true),
        'role' => 'administrator',
    )
);
if (is_wp_error($row)
    || is_wp_error($expected_theme_hash)
    || is_wp_error($batch)
    || is_wp_error($approver_id)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_SETUP_FAILED');
}
$approved = RAOS_Codex_MCP_Store::approve_publication_batch(
    $batch['batch_token'],
    $batch['batch_manifest_sha256'],
    (int) $approver_id,
    'Independent equivalent recovery approval.'
);
$claimed_batch = is_wp_error($approved)
    ? $approved
    : RAOS_Codex_MCP_Store::claim_publication_batch_apply(
        $batch['batch_token'],
        $batch['batch_manifest_sha256'],
        $batch['proposal_ids']
    );
$claimed_member = is_wp_error($claimed_batch)
    ? $claimed_batch
    : RAOS_Codex_MCP_Store::claim_apply($row['proposal_id']);
if (is_wp_error($approved)
    || is_wp_error($claimed_batch)
    || is_wp_error($claimed_member)
    || 'OPERATION_APPLYING' !== $claimed_member['result_code']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_SETUP_FAILED');
}
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array('applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300)),
    array('proposal_id' => $row['proposal_id'])
);
$claimed_member = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$exact_batch = RAOS_Codex_MCP_Store::get_claimed_publication_batch_for_proposal(
    $row['proposal_id']
);
if (is_wp_error($claimed_member)
    || is_wp_error($exact_batch)
    || ! hash_equals($batch['batch_token'], $exact_batch['batch_token'])) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_BINDING_FAILED');
}
$request = new WP_REST_Request('POST', '/');
$request->set_url_params(array('operation_id' => $row['proposal_id']));

// The document hash cannot prove that the runtime authorization checks ran.
// A missing or corrupt approval lease therefore leaves the original operation
// APPLYING and explicitly recoverable; recovery never performs the no-op apply.
$lease_path = $private . '/approval-lease-' . $row['proposal_id'] . '.json';
$held_lease_path = $lease_path . '.held';
$lease_payload = is_file($lease_path) ? file_get_contents($lease_path) : false;
if (! is_string($lease_payload)
    || file_exists($held_lease_path)
    || ! rename($lease_path, $held_lease_path)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_LEASE_SETUP_FAILED');
}
$missing_lease = $deployment->recover_operation($request);
$missing_lease_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! rename($held_lease_path, $lease_path)
    || ! is_wp_error($missing_lease)
    || 'raos_codex_approval_lease_invalid' !== $missing_lease->get_error_code()
    || ! raos_e2e_recovery_required($missing_lease)
    || is_wp_error($missing_lease_stored)
    || 'APPLYING' !== $missing_lease_stored['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_LEASE_FAILED');
}
if (false === file_put_contents($lease_path, '{}')) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_LEASE_SETUP_FAILED');
}
$corrupt_lease = $deployment->recover_operation($request);
$corrupt_lease_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (false === file_put_contents($lease_path, $lease_payload)
    || ! is_wp_error($corrupt_lease)
    || 'raos_codex_approval_lease_invalid' !== $corrupt_lease->get_error_code()
    || ! raos_e2e_recovery_required($corrupt_lease)
    || is_wp_error($corrupt_lease_stored)
    || 'APPLYING' !== $corrupt_lease_stored['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_LEASE_FAILED');
}

// An absent approved/claimed candidate is never guessed from the operation.
$wpdb->update(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array('state' => 'REGISTERED'),
    array('batch_token' => $batch['batch_token'])
);
$missing = $deployment->recover_operation($request);
$missing_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$wpdb->update(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array('state' => 'APPROVED'),
    array('batch_token' => $batch['batch_token'])
);
if (! is_wp_error($missing)
    || 'raos_codex_publication_batch_binding_indeterminate' !== $missing->get_error_code()
    || ! raos_e2e_recovery_required($missing)
    || is_wp_error($missing_stored)
    || 'APPLYING' !== $missing_stored['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_BINDING_FAILED');
}

// A self-consistent stored manifest that no longer binds the operation hashes
// is rejected even if its batch token and proposal ID are unchanged.
$corrupt_manifest = $batch['manifest'];
foreach ($corrupt_manifest['proposals'] as &$corrupt_entry) {
    if (hash_equals($row['proposal_id'], $corrupt_entry['proposal_id'])) {
        $corrupt_entry['after_sha256'] = str_repeat('0', 64);
    }
}
unset($corrupt_entry);
$corrupt_manifest_hash = RAOS_Codex_MCP_Store::hash($corrupt_manifest);
$wpdb->update(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array(
        'batch_manifest_sha256' => $corrupt_manifest_hash,
        'manifest_json' => RAOS_Codex_MCP_Store::canonical_json($corrupt_manifest),
    ),
    array('batch_token' => $batch['batch_token'])
);
$corrupt = $deployment->recover_operation($request);
$corrupt_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$wpdb->update(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array(
        'batch_manifest_sha256' => $batch['batch_manifest_sha256'],
        'manifest_json' => RAOS_Codex_MCP_Store::canonical_json($batch['manifest']),
    ),
    array('batch_token' => $batch['batch_token'])
);
if (! is_wp_error($corrupt)
    || 'raos_codex_publication_batch_binding_indeterminate' !== $corrupt->get_error_code()
    || ! raos_e2e_recovery_required($corrupt)
    || is_wp_error($corrupt_stored)
    || 'APPLYING' !== $corrupt_stored['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_BINDING_FAILED');
}

// Two otherwise eligible claimed batches are ambiguous. The second candidate
// deliberately carries another manifest member so its immutable hash is unique.
$other_proposal_id = hash('sha256', 'equivalent-recovery-other-' . random_bytes(8));
$ambiguous_ids = array($row['proposal_id'], $other_proposal_id);
sort($ambiguous_ids, SORT_STRING);
$ambiguous_entries = $batch['manifest']['proposals'];
$ambiguous_entries[] = array(
    'proposal_id' => $other_proposal_id,
    'kind' => 'CONTENT_RELEASE',
    'created_by' => (int) $row['created_by'],
    'created_at_gmt' => $row['payload']['created_at_gmt'],
    'expires_at_gmt' => $row['payload']['expires_at_gmt'],
    'before_sha256' => str_repeat('1', 64),
    'after_sha256' => str_repeat('2', 64),
);
usort(
    $ambiguous_entries,
    static function ($left, $right) {
        return strcmp($left['proposal_id'], $right['proposal_id']);
    }
);
$ambiguous_manifest = array(
    'schema' => 'RAOSWordPressPublicationBatchManifestV1',
    'expected_theme_tree_sha256' => $expected_theme_hash,
    'proposal_count' => count($ambiguous_entries),
    'proposals' => $ambiguous_entries,
);
$ambiguous_token = hash('sha256', 'equivalent-recovery-batch-' . random_bytes(8));
$ambiguous_manifest_hash = RAOS_Codex_MCP_Store::hash($ambiguous_manifest);
$inserted = $wpdb->insert(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array(
        'batch_token' => $ambiguous_token,
        'state' => 'APPROVED',
        'created_by' => (int) $row['created_by'],
        'approved_by' => (int) $approver_id,
        'created_at_gmt' => RAOS_Codex_MCP_Store::now_mysql(),
        'expires_at_gmt' => $claimed_member['expires_at_gmt'],
        'approved_at_gmt' => $claimed_member['approved_at_gmt'],
        'applying_at_gmt' => RAOS_Codex_MCP_Store::now_mysql(),
        'batch_manifest_sha256' => $ambiguous_manifest_hash,
        'proposal_ids_json' => RAOS_Codex_MCP_Store::canonical_json($ambiguous_ids),
        'manifest_json' => RAOS_Codex_MCP_Store::canonical_json($ambiguous_manifest),
        'approval_reason' => 'Ambiguous recovery fixture.',
    )
);
$ambiguous = 1 === $inserted
    ? $deployment->recover_operation($request)
    : null;
$ambiguous_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$wpdb->delete(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array('batch_token' => $ambiguous_token)
);
if (! is_wp_error($ambiguous)
    || 'raos_codex_publication_batch_binding_indeterminate' !== $ambiguous->get_error_code()
    || ! raos_e2e_recovery_required($ambiguous)
    || is_wp_error($ambiguous_stored)
    || 'APPLYING' !== $ambiguous_stored['state']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_BINDING_FAILED');
}

$revision_count = count(wp_get_post_revisions($post_id));
$post_writes = 0;
$taxonomy_writes = 0;
$record_post_write = static function ($updated_post_id) use ($post_id, &$post_writes) {
    if ((int) $updated_post_id === $post_id) {
        ++$post_writes;
    }
};
$record_taxonomy_write = static function ($object_id) use ($post_id, &$taxonomy_writes) {
    if ((int) $object_id === $post_id) {
        ++$taxonomy_writes;
    }
};
add_action('post_updated', $record_post_write, 10, 1);
add_action('set_object_terms', $record_taxonomy_write, 10, 1);
$theme_root = get_theme_root(RAOS_Codex_MCP_Deployment::THEME_SLUG)
    . '/' . RAOS_Codex_MCP_Deployment::THEME_SLUG;
$drift_path = $theme_root . '/raos-e2e-equivalent-recovery-drift-'
    . bin2hex(random_bytes(6)) . '.tmp';
file_put_contents($drift_path, 'recovery theme drift');
$drifted = $deployment->recover_operation($request);
@unlink($drift_path);
$receipt = $deployment->recover_operation($request);
remove_action('post_updated', $record_post_write, 10);
remove_action('set_object_terms', $record_taxonomy_write, 10);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$current = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($drifted)
    || 'raos_codex_recovery_content_theme_not_ready' !== $drifted->get_error_code()
    || ! raos_e2e_recovery_required($drifted)
    || ! is_array($receipt)
    || 'CONTENT_RELEASE_APPLIED' !== $receipt['result_code']
    || is_wp_error($stored)
    || 'APPLIED' !== $stored['state']
    || ! is_array($current)
    || ! hash_equals($before['content_sha256'], $current['content_sha256'])
    || (int) $before['revision_id'] !== (int) $current['revision_id']
    || ! hash_equals($before['modified_gmt'], $current['modified_gmt'])
    || $revision_count !== count(wp_get_post_revisions($post_id))
    || 0 !== $post_writes
    || 0 !== $taxonomy_writes) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_FAILED');
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
wp_delete_user((int) $approver_id);

// Non-equivalent recovery locks the exact after document and operation row in
// one transaction. A same-connection injected wp-admin-style third edit just
// before the authoritative readback is rolled back, remains APPLYING, and does
// not consume the approval lease. The unchanged retry may then complete.
$post_id = raos_e2e_create_post('recovery-final-cas');
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
$published = is_wp_error($row) ? $row : $write_content->invoke(null, $after);
$recovery_after = is_wp_error($published)
    ? $published
    : RAOS_Codex_MCP_Content::document($post_id);
if (is_wp_error($row) || is_wp_error($published) || is_wp_error($recovery_after)) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_RECOVERY_FINAL_CAS_SETUP_FAILED');
}
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'OPERATION_APPLYING',
        'applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$lease_path = $private . '/approval-lease-' . $row['proposal_id'] . '.json';
file_put_contents($lease_path, 'recovery-lease-evidence');
chmod($lease_path, 0600);
$race = $complete_recovered_content->invoke(
    $deployment,
    $row,
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256(),
    static function ($expected) {
        wp_update_post(
            array(
                'ID' => (int) $expected['id'],
                'post_title' => 'Injected third state before final recovery readback',
            )
        );
    }
);
$race_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$race_content = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($race)
    || 'raos_codex_recovery_content_drift' !== $race->get_error_code()
    || ! raos_e2e_recovery_required($race)
    || is_wp_error($race_stored)
    || 'APPLYING' !== $race_stored['state']
    || ! is_file($lease_path)
    || ! is_array($race_content)
    || ! hash_equals($after['content_sha256'], $race_content['content_sha256'])
    || $recovery_after['revision_id'] !== $race_content['revision_id']
    || ! hash_equals($recovery_after['modified_gmt'], $race_content['modified_gmt'])
    || $recovery_after['taxonomies'] !== $race_content['taxonomies']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_RECOVERY_FINAL_CAS_FAILED');
}
$commit_failure = $complete_recovered_content->invoke(
    $deployment,
    $row,
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256(),
    null,
    static function () {
        return false;
    }
);
$commit_failure_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$commit_failure_content = RAOS_Codex_MCP_Content::document($post_id);
if (! is_wp_error($commit_failure)
    || 'raos_codex_recovery_content_commit_indeterminate' !== $commit_failure->get_error_code()
    || ! raos_e2e_recovery_required($commit_failure)
    || is_wp_error($commit_failure_stored)
    || 'APPLYING' !== $commit_failure_stored['state']
    || ! is_file($lease_path)
    || ! is_array($commit_failure_content)
    || ! hash_equals($after['content_sha256'], $commit_failure_content['content_sha256'])
    || $recovery_after['revision_id'] !== $commit_failure_content['revision_id']
    || ! hash_equals(
        $recovery_after['modified_gmt'],
        $commit_failure_content['modified_gmt']
    )
    || $recovery_after['taxonomies'] !== $commit_failure_content['taxonomies']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_RECOVERY_COMMIT_FAILED');
}
$receipt = $complete_recovered_content->invoke(
    $deployment,
    $row,
    RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()
);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$completed_content = RAOS_Codex_MCP_Content::document($post_id);
if (! is_array($receipt)
    || 'OPERATION_RECOVERED_AFTER_READBACK' !== $receipt['result_code']
    || is_wp_error($stored)
    || 'APPLIED' !== $stored['state']
    || file_exists($lease_path)
    || ! is_array($completed_content)
    || $recovery_after['revision_id'] !== $completed_content['revision_id']
    || ! hash_equals($recovery_after['modified_gmt'], $completed_content['modified_gmt'])
    || $recovery_after['taxonomies'] !== $completed_content['taxonomies']) {
    raos_e2e_rollback_fail('RAOS_E2E_CONTENT_RECOVERY_FINAL_CAS_RETRY_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
wp_delete_post($post_id, true);

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

// A same-tree theme operation interrupted before target->backup rename has no
// install evidence. Recovery must preserve the active theme and remain
// recoverable instead of treating the unchanged hash as an installed after.
$theme_target = get_theme_root(RAOS_Codex_MCP_Deployment::THEME_SLUG)
    . '/' . RAOS_Codex_MCP_Deployment::THEME_SLUG;
$equal_theme_hash = RAOS_Codex_MCP_Deployment::tree_hash($theme_target);
$equal_theme_manifest = $tree_manifest->invoke(null, $theme_target);
$equal_theme_payload = array(
    'schema' => 'CodeReleaseProposalV1',
    'kind' => 'THEME_RELEASE',
    'code_package' => array(
        'kind' => 'theme',
        'slug' => RAOS_Codex_MCP_Deployment::THEME_SLUG,
        'file_manifest' => $equal_theme_manifest,
    ),
);
$row = RAOS_Codex_MCP_Store::create(
    'THEME_RELEASE',
    $equal_theme_payload,
    $equal_theme_hash,
    $equal_theme_hash
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_SETUP_FAILED');
}
$operation_root = $private . '/operation-' . $row['proposal_id'];
mkdir($operation_root, 0700, true);
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
    || 'raos_codex_equal_hash_state_indeterminate' !== $result->get_error_code()
    || ! raos_e2e_recovery_required($result)
    || is_wp_error($stored)
    || 'APPLYING' !== $stored['state']
    || ! is_dir($theme_target)
    || get_stylesheet() !== RAOS_Codex_MCP_Deployment::THEME_SLUG
    || ! hash_equals(
        $equal_theme_hash,
        RAOS_Codex_MCP_Deployment::tree_hash($theme_target)
    )) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_PRERENAME_RECOVERY_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
raos_e2e_rollback_remove_tree($operation_root);

// An exact same-tree backup proves rename completed. Recovery rechecks runtime
// invalidation and may then complete the original operation id as APPLIED.
$row = RAOS_Codex_MCP_Store::create(
    'THEME_RELEASE',
    $equal_theme_payload,
    $equal_theme_hash,
    $equal_theme_hash
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_SETUP_FAILED');
}
$operation_root = $private . '/operation-' . $row['proposal_id'];
$backup = $operation_root . '/before';
mkdir($operation_root, 0700, true);
if (! raos_e2e_rollback_copy_tree($theme_target, $backup)
    || ! hash_equals($equal_theme_hash, RAOS_Codex_MCP_Deployment::tree_hash($backup))) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_SETUP_FAILED');
}
$equal_theme_batch = RAOS_Codex_MCP_Store::register_publication_batch(
    array($row['proposal_id']),
    $equal_theme_hash
);
$equal_theme_approver_login = 'raos-equal-theme-recovery-' . bin2hex(random_bytes(6));
$equal_theme_approver_id = wp_insert_user(
    array(
        'user_login' => $equal_theme_approver_login,
        'user_email' => $equal_theme_approver_login . '@example.invalid',
        'user_pass' => wp_generate_password(32, true, true),
        'role' => 'administrator',
    )
);
$equal_theme_approved = is_wp_error($equal_theme_batch)
    || is_wp_error($equal_theme_approver_id)
        ? new WP_Error('raos_e2e_equal_theme_approval_setup_failed')
        : RAOS_Codex_MCP_Store::approve_publication_batch(
            $equal_theme_batch['batch_token'],
            $equal_theme_batch['batch_manifest_sha256'],
            (int) $equal_theme_approver_id,
            'Independent equal theme recovery approval.'
        );
$equal_theme_claimed_batch = is_wp_error($equal_theme_approved)
    ? $equal_theme_approved
    : RAOS_Codex_MCP_Store::claim_publication_batch_apply(
        $equal_theme_batch['batch_token'],
        $equal_theme_batch['batch_manifest_sha256'],
        $equal_theme_batch['proposal_ids']
    );
$equal_theme_claimed = is_wp_error($equal_theme_claimed_batch)
    ? $equal_theme_claimed_batch
    : RAOS_Codex_MCP_Store::claim_apply($row['proposal_id']);
if (is_wp_error($equal_theme_batch)
    || is_wp_error($equal_theme_approver_id)
    || is_wp_error($equal_theme_approved)
    || is_wp_error($equal_theme_claimed_batch)
    || is_wp_error($equal_theme_claimed)
    || 'OPERATION_APPLYING' !== $equal_theme_claimed['result_code']) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_SETUP_FAILED');
}
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$request = new WP_REST_Request('POST', '/');
$request->set_url_params(array('operation_id' => $row['proposal_id']));
$equal_theme_lease = $private . '/approval-lease-' . $row['proposal_id'] . '.json';
$equal_theme_held_lease = $equal_theme_lease . '.held';
if (! is_file($equal_theme_lease)
    || file_exists($equal_theme_held_lease)
    || ! rename($equal_theme_lease, $equal_theme_held_lease)) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_SETUP_FAILED');
}
$unauthorized = $deployment->recover_operation($request);
$unauthorized_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! rename($equal_theme_held_lease, $equal_theme_lease)
    || ! is_wp_error($unauthorized)
    || 'raos_codex_approval_lease_invalid' !== $unauthorized->get_error_code()
    || ! raos_e2e_recovery_required($unauthorized)
    || is_wp_error($unauthorized_stored)
    || 'APPLYING' !== $unauthorized_stored['state']
    || ! is_dir($backup)
    || ! is_dir($theme_target)) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_RECOVERY_AUTHORIZATION_FAILED');
}
$result = $deployment->recover_operation($request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_array($result)
    || 'APPLIED' !== ($result['state'] ?? null)
    || 'OPERATION_RECOVERED_AFTER_READBACK' !== ($result['result_code'] ?? null)
    || is_wp_error($stored)
    || 'APPLIED' !== $stored['state']
    || file_exists($operation_root)
    || ! is_dir($theme_target)
    || ! hash_equals(
        $equal_theme_hash,
        RAOS_Codex_MCP_Deployment::tree_hash($theme_target)
    )) {
    raos_e2e_rollback_fail('RAOS_E2E_EQUAL_HASH_INSTALLED_RECOVERY_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
$wpdb->delete(
    RAOS_Codex_MCP_Store::batch_table_name(),
    array('batch_token' => $equal_theme_batch['batch_token'])
);
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
wp_delete_user((int) $equal_theme_approver_id);

// The code recovery finalizer re-hashes the whole tree and re-checks plugin
// activation immediately before and after receipt storage. Pre-receipt drift
// stays APPLYING; post-receipt drift keeps the backup and lease so every later
// APPLIED retry fails closed until the exact after state is restored.
require_once ABSPATH . 'wp-admin/includes/plugin.php';
$slug = 'raos-e2e-final-cas-' . bin2hex(random_bytes(4));
$plugin_file = $slug . '/' . $slug . '.php';
$target = WP_PLUGIN_DIR . '/' . $slug;
$before_template = $fixture_root . '/code-recovery-final-cas-before';
mkdir($target, 0700, true);
mkdir($before_template, 0700, true);
file_put_contents(
    $target . '/' . $slug . '.php',
    "<?php\n/*\nPlugin Name: RAOS recovery final CAS\nVersion: 1.0.0\n*/\n"
);
file_put_contents($target . '/style.css', "body{color:green}\n");
file_put_contents(
    $before_template . '/' . $slug . '.php',
    "<?php\n/*\nPlugin Name: RAOS recovery final CAS\nVersion: 0.9.0\n*/\n"
);
$before_hash = RAOS_Codex_MCP_Deployment::tree_hash($before_template);
$after_hash = RAOS_Codex_MCP_Deployment::tree_hash($target);
$row = RAOS_Codex_MCP_Store::create(
    'PLUGIN_CHANGE',
    array(
        'schema' => 'CodeReleaseProposalV1',
        'kind' => 'PLUGIN_CHANGE',
        'code_package' => array(
            'kind' => 'plugin',
            'slug' => $slug,
            'activation_intent' => 'activate',
        ),
    ),
    $before_hash,
    $after_hash
);
if (is_wp_error($row)) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_FINAL_CAS_SETUP_FAILED');
}
$operation_root = $private . '/operation-' . $row['proposal_id'];
$backup = $operation_root . '/before';
mkdir($operation_root, 0700, true);
rename($before_template, $backup);
$plugin_state = array(
    'old_file' => null,
    'old_active' => false,
    'new_file' => $plugin_file,
);
$plugin_state_payload = RAOS_Codex_MCP_Store::canonical_json($plugin_state);
$plugin_state_path = $operation_root . '/plugin-before-state.json';
file_put_contents($plugin_state_path, $plugin_state_payload);
chmod($plugin_state_path, 0600);
$activation = activate_plugin($plugin_file, '', false, true);
$wpdb->update(
    RAOS_Codex_MCP_Store::table_name(),
    array(
        'state' => 'APPLYING',
        'result_code' => 'OPERATION_APPLYING',
        'applying_at_gmt' => gmdate('Y-m-d H:i:s', time() - 300),
    ),
    array('proposal_id' => $row['proposal_id'])
);
$lease_path = $private . '/approval-lease-' . $row['proposal_id'] . '.json';
file_put_contents($lease_path, 'recovery-lease-evidence');
chmod($lease_path, 0600);
if (! is_string($plugin_state_payload)
    || is_wp_error($activation)
    || ! is_plugin_active($plugin_file)) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_FINAL_CAS_SETUP_FAILED');
}
$race = $complete_recovered_code->invoke(
    null,
    $row,
    $target,
    static function ($live_target) {
        file_put_contents($live_target . '/style.css', "body{color:red}\n");
    }
);
$race_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_wp_error($race)
    || 'raos_codex_recovery_code_drift' !== $race->get_error_code()
    || ! raos_e2e_recovery_required($race)
    || is_wp_error($race_stored)
    || 'APPLYING' !== $race_stored['state']
    || ! is_dir($backup)
    || ! is_file($lease_path)
    || "body{color:red}\n" !== file_get_contents($target . '/style.css')) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_FINAL_CAS_FAILED');
}
file_put_contents($target . '/style.css', "body{color:green}\n");
$activation_race = $complete_recovered_code->invoke(
    null,
    $row,
    $target,
    static function () use ($plugin_file) {
        deactivate_plugins($plugin_file, true, false);
    }
);
$activation_race_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_wp_error($activation_race)
    || 'raos_codex_recovery_plugin_activation_drift' !== $activation_race->get_error_code()
    || ! raos_e2e_recovery_required($activation_race)
    || is_wp_error($activation_race_stored)
    || 'APPLYING' !== $activation_race_stored['state']
    || is_plugin_active($plugin_file)
    || ! is_dir($backup)
    || ! is_file($lease_path)) {
    raos_e2e_rollback_fail('RAOS_E2E_PLUGIN_RECOVERY_FINAL_CAS_FAILED');
}
$activation = activate_plugin($plugin_file, '', false, true);
if (is_wp_error($activation) || ! is_plugin_active($plugin_file)) {
    raos_e2e_rollback_fail('RAOS_E2E_PLUGIN_RECOVERY_FINAL_CAS_SETUP_FAILED');
}
$postcomplete = $complete_recovered_code->invoke(
    null,
    $row,
    $target,
    null,
    static function ($live_target) use ($plugin_file) {
        file_put_contents($live_target . '/style.css', "body{color:red}\n");
        deactivate_plugins($plugin_file, true, false);
    }
);
$postcomplete_stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
if (! is_wp_error($postcomplete)
    || 'raos_codex_recovery_code_postcomplete_drift' !== $postcomplete->get_error_code()
    || ! raos_e2e_recovery_required($postcomplete)
    || is_wp_error($postcomplete_stored)
    || 'APPLIED' !== $postcomplete_stored['state']
    || ! is_dir($backup)
    || ! is_file($lease_path)
    || is_plugin_active($plugin_file)
    || "body{color:red}\n" !== file_get_contents($target . '/style.css')) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_POSTCOMPLETE_CAS_FAILED');
}
$request = new WP_REST_Request('POST', '/');
$request->set_url_params(array('operation_id' => $row['proposal_id']));
$postcomplete_retry = $deployment->recover_operation($request);
if (! is_wp_error($postcomplete_retry)
    || 'raos_codex_recovery_code_postcomplete_drift' !== $postcomplete_retry->get_error_code()
    || ! is_dir($backup)
    || ! is_file($lease_path)) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_POSTCOMPLETE_RETRY_FAILED');
}
file_put_contents($target . '/style.css', "body{color:green}\n");
$activation_retry = $deployment->recover_operation($request);
if (! is_wp_error($activation_retry)
    || 'raos_codex_recovery_plugin_activation_drift' !== $activation_retry->get_error_code()
    || ! is_dir($backup)
    || ! is_file($lease_path)) {
    raos_e2e_rollback_fail('RAOS_E2E_PLUGIN_RECOVERY_POSTCOMPLETE_RETRY_FAILED');
}
$activation = activate_plugin($plugin_file, '', false, true);
$receipt = is_wp_error($activation)
    ? $activation
    : $deployment->recover_operation($request);
$stored = RAOS_Codex_MCP_Store::get($row['proposal_id']);
$idempotent = $deployment->recover_operation($request);
if (! is_array($receipt)
    || 'OPERATION_RECOVERED_AFTER_READBACK' !== $receipt['result_code']
    || is_wp_error($stored)
    || 'APPLIED' !== $stored['state']
    || file_exists($operation_root)
    || file_exists($lease_path)
    || ! is_plugin_active($plugin_file)
    || $idempotent !== $receipt) {
    raos_e2e_rollback_fail('RAOS_E2E_CODE_RECOVERY_FINAL_CAS_RETRY_FAILED');
}
$wpdb->delete(RAOS_Codex_MCP_Store::table_name(), array('proposal_id' => $row['proposal_id']));
deactivate_plugins($plugin_file, true, false);
@unlink($private . '/operation-lock-' . $row['proposal_id'] . '.lock');
raos_e2e_rollback_remove_tree($target);

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
