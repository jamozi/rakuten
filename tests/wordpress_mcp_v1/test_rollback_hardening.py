from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOYMENT = (
    ROOT
    / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-deployment.php"
)
HARNESS = ROOT / "tests/wordpress_mcp_v1/e2e/rollback_harness.php"


def source() -> str:
    return DEPLOYMENT.read_text(encoding="utf-8")


def method(name: str, following: str) -> str:
    return source().split(f"function {name}", 1)[1].split(f"function {following}", 1)[0]


def test_only_confirmed_rollbacks_are_terminalized() -> None:
    apply = method("apply_proposal", "recover_operation")
    assert "! self::error_requires_recovery($receipt)" in apply
    assert "raos_codex_operation_recovery_required" in apply

    content = method("apply_content", "complete_recovered_content")
    assert "begin_content_transaction" in content
    assert content.count("rollback_content_transaction") == 3
    assert "recoverable_from_error($receipt)" in content
    assert "raos_codex_content_commit_indeterminate" in content

    code = method("apply_code", "install_code_tree")
    assert "raos_codex_code_rollback_indeterminate" in code
    assert "recoverable_from_error($receipt)" in code
    assert "RAOS_Codex_MCP_Store::get($row['proposal_id'])" in code


def test_code_install_rechecks_the_moved_backup_and_preserves_it_on_uncertainty() -> (
    None
):
    install = method("install_code_tree", "restore_code_before")
    assert install.index("$move($target, $backup_root)") < install.index(
        "$moved_hash = self::tree_hash($backup_root)"
    )
    assert "hash_equals($before_sha256, $moved_hash)" in install
    assert "raos_codex_backup_cas_indeterminate" in install
    assert "raos_codex_code_install_rollback_indeterminate" in install

    code = method("apply_code", "install_code_tree")
    preservation = code.split("if (is_wp_error($installed))", 1)[1].split(
        "return $installed", 1
    )[0]
    assert "remove_tree($operation_root)" not in preservation


def test_recover_never_overwrites_a_third_content_or_code_state() -> None:
    recover = method("recover_operation", "apply_content")
    assert "raos_codex_recovery_content_drift" in recover
    assert "raos_codex_recovery_code_drift" in recover
    assert "write_content_document" not in recover
    assert recover.index(
        "hash_equals($row['after_sha256'], $current_hash)"
    ) < recover.index("raos_codex_recovery_content_drift")
    assert recover.index(
        "hash_equals($row['before_sha256'], $current_hash)"
    ) < recover.index("raos_codex_recovery_content_drift")


def test_plugin_activation_recovery_is_not_inferred_from_tree_hash_alone() -> None:
    code = source()
    assert "plugin-before-state.json" in code
    recover = method("recover_operation", "apply_content")
    assert recover.count("recover_plugin_activation") == 3
    assert "plugin_state_matches_before" in code
    assert "plugin_state_matches_after" in code
    verifier = method("verify_recovered_code_after", "finalize_applied_receipt")
    assert verifier.index("self::tree_hash($target)") < verifier.index(
        "self::plugin_state_matches_after"
    )
    assert "raos_codex_recovery_plugin_activation_drift" in verifier


def test_content_compare_and_swap_locks_then_rechecks_precondition() -> None:
    transaction = method("begin_content_transaction", "rollback_content_transaction")
    assert "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE" in transaction
    assert "START TRANSACTION" in transaction
    assert transaction.index(
        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
    ) < transaction.index("START TRANSACTION")
    assert "FROM {$wpdb->posts} WHERE ID = %d FOR UPDATE" in transaction
    assert "FROM {$wpdb->term_relationships}" in transaction
    assert "$wpdb->term_taxonomy" in source()
    assert "RAOS_Codex_MCP_Store::require_transactional_tables" in transaction
    assert transaction.index("FOR UPDATE") < transaction.index(
        "RAOS_Codex_MCP_Content::document($post_id)"
    )
    assert "revision_id" in transaction
    assert "modified_gmt" in transaction


def test_equivalent_content_apply_is_a_locked_assertion_without_a_post_write() -> None:
    content = method("apply_content", "complete_recovered_content")
    assert "$equivalent_release = hash_equals(" in content
    assert content.index("begin_content_transaction") < content.index(
        "$equivalent_release = hash_equals("
    )
    guarded_write = content.split("if (! $equivalent_release)", 1)[1].split(
        "$readback = RAOS_Codex_MCP_Content::document", 1
    )[0]
    assert "write_content_document($after)" in guarded_write
    assert content.count("write_content_document($after)") == 1
    assert content.index("$readback = RAOS_Codex_MCP_Content::document") < content.index(
        "$theme_readback = self::active_theme_tree_sha256()"
    )
    assert content.index("$theme_readback = self::active_theme_tree_sha256()") < (
        content.index("$wpdb->query('COMMIT')")
    )
    assert content.index("$wpdb->query('COMMIT')") < content.index(
        "RAOS_Codex_MCP_Store::complete("
    )


def test_equivalent_content_recovery_replays_the_exact_batch_assertion() -> None:
    recover = method("recover_operation", "apply_content")
    assert "$equivalent_content_release" in recover
    assert "hash_equals($row['before_sha256'], $row['after_sha256'])" in recover
    equivalent = recover.split("if ($equivalent_content_release", 1)[1].split(
        "if (is_string($current_hash)", 1
    )[0]
    assert "get_claimed_publication_batch_for_proposal" in equivalent
    assert "publication_batch_theme_ready" in equivalent
    assert "$batch['manifest']['expected_theme_tree_sha256']" in equivalent
    assert "$this->apply_content(" in equivalent
    assert "RAOS_Codex_MCP_Store::complete(" not in equivalent
    assert recover.index("get_claimed_publication_batch_for_proposal") < recover.index(
        "$this->complete_recovered_content("
    )


def test_publication_batch_status_is_exact_and_read_only() -> None:
    code = source()
    assert "'/publication-batches/(?P<batch_token>[0-9a-f]{64})'" in code
    endpoint = method(
        "get_publication_batch", "proposal_target_matches_immutable_state"
    )
    for field in (
        "RAOSWordPressPublicationBatchStatusV1",
        "batch_manifest_sha256",
        "proposal_count",
        "proposal_ids",
        "expires_at_gmt",
        "preconditions_ready",
    ):
        assert field in endpoint
    assert "sort($proposal_ids, SORT_STRING)" in endpoint
    assert "array('APPROVED', 'APPLYING', 'APPLIED')" in endpoint
    assert "array('APPLYING', 'APPLIED', 'FAILED')" in endpoint
    assert "$all_members_expired" in endpoint
    assert "$all_members_terminal_expired" in endpoint
    assert "$all_members_applied" in endpoint
    assert "$member_expires_at" in endpoint
    assert "$member_expired" in endpoint
    assert "$expiry_reset_safe" in endpoint
    assert "$recovery_only" in endpoint
    assert "$batch_expired && ! $recovery_only" in endpoint
    assert "! $member_started && $all_members_terminal_expired" in endpoint
    assert "$derived_state = 'APPLIED'" in endpoint
    assert "$derived_state = 'EXPIRED'" in endpoint
    matcher = method("proposal_target_matches_immutable_state", "apply_proposal")
    assert "if ('APPROVED' === $row['state'])" in matcher
    assert "return $at_before" in matcher
    assert "if ('EXPIRED' === $row['state'])" in matcher
    assert "if ('APPLIED' === $row['state'])" in matcher
    assert "return $at_after" in matcher


def test_code_cleanup_requires_a_persisted_terminal_state() -> None:
    cleanup = method("cleanup_completed_code_operation", "begin_content_transaction")
    assert "isset($row['proposal_id'], $row['kind'], $row['state'])" in cleanup
    assert "array('APPLIED', 'FAILED', 'EXPIRED')" in cleanup
    code = method("apply_code", "install_code_tree")
    assert "'APPLIED' === $completed['state']" in code
    assert "cleanup_completed_code_operation($completed)" in code

    plugin = (
        ROOT
        / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/raos-codex-mcp-abilities.php"
    ).read_text(encoding="utf-8")
    assert "'get_publication_batch' === $method" in plugin
    assert "/publication-batches/[0-9a-f]{64}" in plugin


def test_code_apply_force_invalidates_exact_php_manifest_before_runtime_use() -> None:
    code = method("apply_code", "install_code_tree")
    before_invalidation = code.index("$before_invalidation = self::invalidate_php_manifest")
    install = code.index("$installed = self::install_code_tree")
    after_invalidation = code.index("$after_invalidation = self::invalidate_php_manifest")
    assert before_invalidation < install < after_invalidation
    assert after_invalidation < code.index("$activation = true")
    assert after_invalidation < code.index("$readback = self::tree_hash($target)")
    assert "$before_manifest = is_dir($target) ? self::tree_manifest($target) : null" in code
    after_call = code.split("$after_invalidation = self::invalidate_php_manifest", 1)[1].split(
        ");", 1
    )[0]
    assert "is_array($before_manifest) ? $before_manifest : array()" in after_call
    assert "return true === $rollback ? $after_invalidation : $rollback" in code

    invalidation = method("invalidate_php_manifest", "tree_manifest")
    assert "extension_loaded('Zend OPcache')" in invalidation
    assert "function_exists('opcache_get_status')" in invalidation
    assert "opcache_get_status(false)" in invalidation
    assert "true === $opcache_status['opcache_enabled']" in invalidation
    assert "ini_get('opcache.enable')" in invalidation
    assert "ini_get('opcache.enable_cli')" in invalidation
    assert "FILTER_NULL_ON_FAILURE" in invalidation
    assert "false === $enabled" in invalidation
    assert "'cli' === PHP_SAPI && false === $cli_enabled" in invalidation
    assert "raos_codex_opcache_status_indeterminate" in invalidation
    assert "function_exists('wp_opcache_invalidate')" in invalidation
    assert "ABSPATH . 'wp-admin/includes/file.php'" in invalidation
    assert "require_once $wordpress_filesystem" in invalidation
    assert "$invalidate($resolved, true)" in invalidation
    assert "has_exact_keys($entry, array('path', 'size', 'sha256'))" in invalidation
    assert "hash_equals($expected, $resolved)" in invalidation
    assert "hash_equals($entry['sha256'], $digest)" in invalidation
    assert "raos_codex_opcache_invalidation_unavailable" in invalidation
    assert "raos_codex_opcache_path_invalid" in invalidation
    assert "raos_codex_opcache_invalidation_failed" in invalidation
    assert "$stale_manifest" in invalidation
    assert "$exact_paths[$entry['path']] = true" in invalidation
    assert "isset($exact_paths[$entry['path']])" in invalidation
    assert "isset($seen[$folded])" not in invalidation
    assert "file_exists($expected) || is_link($expected)" in invalidation
    assert "$invalidate($expected, true)" in invalidation


def test_code_rollback_and_recovery_never_terminalize_stale_php_runtime() -> None:
    restore = method("restore_code_before", "validate_code_package")
    assert "$preflight_backup_hash" in restore
    assert restore.index("$preflight_backup_hash") < restore.index(
        "$move($target, $quarantine_root)"
    )
    assert "hash_equals($before_sha256, $preflight_backup_hash)" in restore
    assert "raos_codex_code_rollback_backup_indeterminate" in restore
    assert "self::remove_tree($target)" not in restore
    assert "$move($target, $quarantine_root)" in restore
    assert restore.index("$move($target, $quarantine_root)") < restore.index(
        "$quarantined_hash = self::tree_hash($quarantine_root)"
    )
    assert "$move($quarantine_root, $target)" in restore
    assert "raos_codex_code_rollback_after_drift" in restore
    assert "self::tree_manifest($target)" in restore
    assert "self::invalidate_php_manifest(" in restore
    assert "$invalidator" in restore
    assert "$opcache_active" in restore
    assert "$stale_manifest" in restore
    assert "raos_codex_code_rollback_opcache_indeterminate" in restore

    recover = method("recover_operation", "apply_content")
    after_runtime = recover.index("self::invalidate_php_manifest")
    after_finalizer = recover.index("self::complete_recovered_code")
    assert after_runtime < after_finalizer
    assert recover.count("self::invalidate_php_manifest") == 2
    after_branch = recover.split("if (is_string($current_hash)", 1)[1].split(
        "if (! $current_read_error", 1
    )[0]
    assert after_branch.index("self::apply_gate($row['kind'])") < after_branch.index(
        "self::validate_approval_lease($row)"
    ) < after_branch.index("self::invalidate_php_manifest")
    assert after_branch.index("self::validate_approval_lease($row)") < after_branch.index(
        "self::complete_recovered_code("
    )
    assert "self::recoverable_from_error($invalidation)" in recover
    invalidation_failure = recover.split("if (is_wp_error($invalidation))", 1)[1]
    assert "self::validate_approval_lease($row)" in invalidation_failure
    assert "self::restore_code_before(" in invalidation_failure
    assert "RAOS_Codex_MCP_Store::mark_failed" in invalidation_failure


def test_equal_code_hash_recovery_requires_exact_install_backup_evidence() -> None:
    recover = method("recover_operation", "apply_content")
    equal = recover.split("$equal_code_hashes", 1)[1].split(
        "if (is_string($current_hash)", 1
    )[0]
    assert "hash_equals($row['before_sha256'], $row['after_sha256'])" in equal
    assert "'/operation-' . $row['proposal_id'] . '/before'" in equal
    assert "self::tree_manifest($backup)" in equal
    assert "RAOS_Codex_MCP_Store::hash($recovery_before_manifest)" in equal
    assert "hash_equals($row['before_sha256'], $backup_hash)" in equal
    assert "raos_codex_equal_hash_state_indeterminate" in equal
    assert "remove_tree" not in equal
    assert "restore_code_before" not in equal
    assert recover.index("$equal_code_hashes") < recover.index(
        "self::complete_recovered_code("
    )


def test_equivalent_content_recovery_rechecks_gate_and_approval_lease() -> None:
    recover = method("recover_operation", "apply_content")
    equivalent = recover.split("if ($equivalent_content_release", 1)[1].split(
        "$code_at_after", 1
    )[0]
    gate = equivalent.index("self::apply_gate($row['kind'])")
    lease = equivalent.index("self::validate_approval_lease($row)")
    binding = equivalent.index(
        "RAOS_Codex_MCP_Store::get_claimed_publication_batch_for_proposal"
    )
    apply = equivalent.index("$this->apply_content(")
    assert gate < lease < binding < apply
    assert equivalent.count("self::recoverable_from_error(") >= 3
    assert "raos_codex_recovery_content_theme_not_ready" in equivalent

    apply_gate = method("apply_gate", "gate")
    assert "self::gate('RAOS_OPERATOR_WRITES_ENABLED')" in apply_gate
    assert "raos_codex_global_kill_switch_disabled" in apply_gate


def test_non_equivalent_content_recovery_linearizes_cas_and_receipt() -> None:
    recover = method("recover_operation", "apply_content")
    assert recover.index("self::validate_approval_lease($row)") < recover.index(
        "$this->complete_recovered_content("
    )

    content = method("complete_recovered_content", "complete_recovered_code")
    assert "begin_content_transaction(" in content
    assert "false," in content
    assert "true" in content
    assert content.index("RAOS_Codex_MCP_Content::document") < content.index(
        "RAOS_Codex_MCP_Store::complete("
    )
    completion = content.split("RAOS_Codex_MCP_Store::complete(", 1)[1].split(
        ");", 1
    )[0]
    assert "true" in completion
    assert content.index("RAOS_Codex_MCP_Store::complete(") < content.index(
        "$wpdb->query('COMMIT')"
    )
    assert content.index("$wpdb->query('COMMIT')") < content.rindex(
        "self::finalize_applied_receipt"
    )
    assert "'APPLIED' === $stored['state']" in content
    assert "raos_codex_recovery_content_commit_indeterminate" in content
    assert "$commit_transaction" in content
    assert "! $commit_allowed" in content
    assert "raos_codex_recovery_content_drift" in content

    transaction = method("begin_content_transaction", "rollback_content_transaction")
    assert "$include_operation_store" in transaction
    assert "RAOS_Codex_MCP_Store::table_name()" in transaction

    store = (
        ROOT
        / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/includes/class-raos-codex-mcp-store.php"
    ).read_text(encoding="utf-8")
    complete = store.split("function complete", 1)[1].split("function mark_failed", 1)[0]
    assert "$defer_approval_lease_cleanup = false" in complete
    assert "if (! $defer_approval_lease_cleanup)" in complete


def test_code_recovery_rechecks_full_tree_around_receipt_storage() -> None:
    recover = method("recover_operation", "apply_content")
    assert recover.index("self::invalidate_php_manifest") < recover.index(
        "self::complete_recovered_code("
    )
    code = method("complete_recovered_code", "verify_recovered_code_after")
    before = code.index("$final_before = self::verify_recovered_code_after")
    receipt = code.index("RAOS_Codex_MCP_Store::complete(")
    after = code.index("self::finalize_applied_receipt($completed)")
    assert before < receipt < after
    assert "raos_codex_recovery_code_drift" in code
    assert "raos_codex_recovery_code_postcomplete_drift" in code
    assert "$after_receipt_stored" in code

    verifier = method("verify_recovered_code_after", "finalize_applied_receipt")
    assert "self::tree_hash($target)" in verifier
    assert "self::plugin_state_matches_after" in verifier
    assert "raos_codex_recovery_plugin_activation_drift" in verifier

    applied = method("finalize_applied_receipt", "cleanup_completed_code_operation")
    assert "$deferred_cleanup" in applied
    assert applied.index("self::verify_recovered_code_after") < applied.index(
        "self::remove_approval_lease"
    )
    assert applied.index("self::verify_recovered_code_after") < applied.index(
        "self::cleanup_completed_code_operation"
    )
    assert "raos_codex_recovery_code_postcomplete_drift" in applied
    assert "file_exists($operation_root) || is_link($operation_root)" in applied
    assert "file_exists($lease_path) || is_link($lease_path)" in applied
    assert "raos_codex_recovery_cleanup_indeterminate" in applied

    lease = method("remove_approval_lease", "acquire_operation_lock")
    assert lease.index("if (is_link($path))") < lease.index(
        "if (! file_exists($path))"
    )
    assert "return is_file($path) && @unlink($path)" in lease

    apply = method("apply_proposal", "recover_operation")
    recover = method("recover_operation", "apply_content")
    assert apply.count("self::finalize_applied_receipt") == 2
    assert recover.count("self::finalize_applied_receipt") == 1


def test_deployment_status_exposes_loaded_theme_runtime_identity() -> None:
    status = method("status", "active_theme_tree_sha256")
    assert "get_stylesheet() === self::THEME_SLUG" in status
    assert "defined('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_VERSION')" in status
    assert "'runtime_version' => $theme_runtime_version" in status
    assert "defined('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "constant('KURASHINOSHIRUBE_THEME_RUNTIME_REVISION')" in status
    assert "'runtime_revision' => $theme_runtime_revision" in status
    assert ": null" in status

    client = (ROOT / "tests/wordpress_mcp_v1/e2e/client.py").read_text(
        encoding="utf-8"
    )
    assert 'status["theme"]["runtime_version"] == status["theme"]["version"]' in client
    assert (
        'status["theme"]["runtime_revision"] == EXPECTED_THEME_RUNTIME_REVISION'
        in client
    )


def test_content_and_theme_apply_are_bound_to_the_exact_ready_batch() -> None:
    apply = method("apply_proposal", "recover_operation")
    assert apply.index("validate_publication_batch_apply") < apply.index(
        "RAOS_Codex_MCP_Store::claim_apply"
    )
    assert apply.index("validate_publication_batch_apply") < apply.index(
        "'APPLIED' === $row['state']"
    )
    binding = method(
        "validate_publication_batch_apply",
        "proposal_target_matches_immutable_state",
    )
    assert "X-RAOS-Batch-Token" in binding
    assert "X-RAOS-Batch-Manifest-SHA256" in binding
    assert "CONTENT_RELEASE" in binding
    assert "THEME_RELEASE" in binding
    assert "PLUGIN_CHANGE" in binding
    assert "raos_codex_plugin_batch_headers_refused" in binding
    assert "in_array($row['proposal_id'], $batch['proposal_ids'], true)" in binding
    assert "true === $status['preconditions_ready']" in binding
    assert "raos_codex_publication_batch_not_ready" in binding
    assert "publication_batch_theme_ready" in binding

    theme_barrier = method(
        "publication_batch_theme_ready", "proposal_target_matches_immutable_state"
    )
    assert "'THEME_RELEASE' !== $member['kind']" in theme_barrier
    assert "'APPLIED' !== $member['state']" in theme_barrier
    assert "proposal_target_matches_immutable_state($member)" in theme_barrier
    assert "raos_codex_publication_batch_theme_not_applied" in binding

    client = (ROOT / "tests/wordpress_mcp_v1/e2e/client.py").read_text(encoding="utf-8")
    assert '"X-RAOS-Batch-Token"' in client
    assert '"X-RAOS-Batch-Manifest-SHA256"' in client
    assert '"raos_codex_publication_batch_theme_not_applied"' in client
    assert 'blocked["operation"]["result_code"] == "BATCH_CLAIMED"' in client


def test_content_only_batch_rechecks_hash_bound_theme_before_every_transition() -> None:
    active_theme = method("active_theme_tree_sha256", "create_proposal")
    assert "get_stylesheet() !== self::THEME_SLUG" in active_theme
    assert "self::tree_hash($target)" in active_theme

    status = method("publication_batch_status", "validate_publication_batch_apply")
    assert "publication_batch_theme_precondition_matches($batch)" in status
    assert "$expiry_reset_safe = false" in status

    apply_binding = method(
        "validate_publication_batch_apply", "publication_batch_theme_ready"
    )
    assert "publication_batch_status($batch)" in apply_binding
    assert "publication_batch_theme_ready($batch)" in apply_binding

    theme_ready = method(
        "publication_batch_theme_ready",
        "publication_batch_theme_precondition_matches",
    )
    assert "publication_batch_theme_precondition_matches($batch)" in theme_ready

    theme_binding = method(
        "publication_batch_theme_precondition_matches",
        "proposal_target_matches_immutable_state",
    )
    assert "$batch['manifest']['expected_theme_tree_sha256']" in theme_binding
    assert "self::active_theme_tree_sha256()" in theme_binding
    assert "return hash_equals($expected, $current)" in theme_binding
    assert "get_stylesheet() !== self::THEME_SLUG" in active_theme
    assert "'BATCH_CLAIMED' === $theme_member['result_code']" in theme_binding

    apply = method("apply_proposal", "recover_operation")
    recover = method("recover_operation", "apply_content")
    for flow in (apply, recover):
        assert "acquire_publication_mutation_lock" in flow
        assert "release_operation_lock($publication_lock)" in flow
    content = method("apply_content", "cleanup_completed_code_operation")
    assert "active_theme_tree_sha256" in content
    assert "rollback_content_transaction" in content
    assert "raos_codex_content_theme_drift" in content


def test_exact_batch_is_atomically_claimed_before_member_mutation() -> None:
    code = source()
    assert "'/publication-batches/(?P<batch_token>[0-9a-f]{64})/claim'" in code
    claim = method("claim_publication_batch", "publication_batch_status")
    assert "has_exact_keys" in claim
    assert "batch_manifest_sha256" in claim
    assert "proposal_ids" in claim
    assert "preconditions_ready" in claim
    assert "RAOS_Codex_MCP_Store::claim_publication_batch_apply" in claim

    apply = method("apply_proposal", "recover_operation")
    assert "'BATCH_CLAIMED' !== $row['result_code']" in apply
    assert apply.index("'BATCH_CLAIMED' !== $row['result_code']") < apply.index(
        "RAOS_Codex_MCP_Store::claim_apply"
    )
    assert "raos_codex_publication_batch_not_claimed" in apply
    assert "'OPERATION_APPLYING' === $row['result_code']" in apply
    recover = method("recover_operation", "apply_content")
    assert "'BATCH_CLAIMED' === $row['result_code']" in recover
    assert recover.index("'BATCH_CLAIMED' === $row['result_code']") < recover.index(
        "recovery_grace_elapsed"
    )

    plugin = (
        ROOT
        / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities/raos-codex-mcp-abilities.php"
    ).read_text(encoding="utf-8")
    assert "'claim_publication_batch' === $method" in plugin
    assert "/publication-batches/[0-9a-f]{64}/claim" in plugin

    client = (ROOT / "tests/wordpress_mcp_v1/e2e/client.py").read_text(encoding="utf-8")
    assert 'batch_path + "/claim"' in client
    assert '"RAOSWordPressPublicationBatchClaimV1"' in client


def test_disposable_e2e_has_concrete_failure_injection_cases() -> None:
    harness = HARNESS.read_text(encoding="utf-8")
    for marker in (
        "RAOS_E2E_ROLLBACK_INSTALL_RESTORE_FAILED",
        "RAOS_E2E_ROLLBACK_BACKUP_PRESERVATION_FAILED",
        "RAOS_E2E_ROLLBACK_CAS_FAILED",
        "RAOS_E2E_ROLLBACK_CONTENT_FAILED",
        "RAOS_E2E_ROLLBACK_COMPLETE_AMBIGUITY_FAILED",
        "RAOS_E2E_ROLLBACK_CONTENT_DRIFT_FAILED",
        "RAOS_E2E_ROLLBACK_CODE_DRIFT_FAILED",
        "RAOS_E2E_ROLLBACK_CONTENT_ISOLATION_FAILED",
        "RAOS_E2E_ROLLBACK_PRETERMINAL_CLEANUP_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_APPLIED_RESUME_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_PARTIAL_EXPIRY_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_SAFE_EXPIRY_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_DRIFT_EXPIRY_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_PRECLAIM_DRIFT_FAILED",
        "RAOS_E2E_ROLLBACK_BATCH_PRECLAIM_EXPIRY_FAILED",
        "RAOS_E2E_THEME_ACTIVE_BINDING_SWITCH_FAILED",
        "RAOS_E2E_PUBLICATION_MUTATION_LOCK_FAILED",
        "RAOS_E2E_CONTENT_THEME_POSTCHECK_ROLLBACK_FAILED",
        "RAOS_E2E_CONTENT_EQUIVALENT_NO_WRITE_FAILED",
        "RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_BINDING_FAILED",
        "RAOS_E2E_CONTENT_EQUIVALENT_RECOVERY_FAILED",
        "RAOS_E2E_CONTENT_RECOVERY_FINAL_CAS_FAILED",
        "RAOS_E2E_CONTENT_RECOVERY_COMMIT_FAILED",
        "RAOS_E2E_CODE_RECOVERY_FINAL_CAS_FAILED",
        "RAOS_E2E_PLUGIN_RECOVERY_FINAL_CAS_FAILED",
        "RAOS_E2E_CODE_RECOVERY_POSTCOMPLETE_CAS_FAILED",
        "RAOS_E2E_CODE_RECOVERY_POSTCOMPLETE_RETRY_FAILED",
        "RAOS_E2E_PLUGIN_RECOVERY_POSTCOMPLETE_RETRY_FAILED",
        "RAOS_E2E_RECOVERY_BROKEN_LEASE_CLEANUP_FAILED",
        "RAOS_E2E_RECOVERY_BROKEN_ROOT_CLEANUP_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_REGISTER_DRIFT_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_APPROVAL_DRIFT_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_CLAIM_DRIFT_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_APPLY_DRIFT_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_APPROVAL_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_CLAIM_FAILED",
        "RAOS_E2E_CONTENT_ONLY_THEME_NORMAL_APPLY_FAILED",
        "RAOS_E2E_ROLLBACK_OK",
    ):
        assert marker in harness
    runner = (ROOT / "tests/wordpress_mcp_v1/e2e/run.sh").read_text(encoding="utf-8")
    assert "rollback_harness.php" in runner
