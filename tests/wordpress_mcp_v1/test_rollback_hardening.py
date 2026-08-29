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

    content = method("apply_content", "begin_content_transaction")
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
    assert recover.count("recover_plugin_activation") == 2
    assert "plugin_state_matches_before" in code
    assert "plugin_state_matches_after" in code


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
