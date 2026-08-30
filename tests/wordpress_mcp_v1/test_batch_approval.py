from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities"


def test_store_schema_upgrade_and_idempotency_are_activation_independent() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()
    content = (PLUGIN / "includes/class-raos-codex-mcp-content.php").read_text()

    assert "const SCHEMA_VERSION = '4';" in store
    assert "idempotency_key char(64) NULL" in store
    assert "applying_at_gmt datetime NULL" in store
    assert store.count("applying_at_gmt datetime NULL") == 2
    assert "raos_codex_publication_batches_v1" in store
    assert "UNIQUE KEY creator_kind_idempotency" in store
    assert "function maybe_upgrade()" in store
    assert "add_action('init', array($this, 'maybe_upgrade'), 0);" in main
    upgrade = main.split("public function maybe_upgrade()", 1)[1].split(
        "private static function install_role", 1
    )[0]
    assert upgrade.index("self::runtime_identity_is_exact()") < upgrade.index(
        "RAOS_Codex_MCP_Store::maybe_upgrade()"
    )
    assert "get_option(self::SCHEMA_OPTION" in store
    assert "dbDelta($sql)" in store
    assert "^[0-9a-f]{64}$" in content
    assert "$idempotency_key = null" in store
    assert "raos_codex_idempotency_conflict" in store
    assert "array_key_exists('idempotency_key', $input)" in content


def test_batch_manifest_and_approval_fail_closed_as_one_transaction() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    assert "RAOSWordPressPublicationBatchManifestV1" in store
    for field in (
        "'proposal_id' => $row['proposal_id']",
        "'before_sha256' => $row['before_sha256']",
        "'after_sha256' => $row['after_sha256']",
    ):
        assert field in store
    assert "sort($proposal_ids, SORT_STRING)" in store
    assert "strcmp($left['proposal_id'], $right['proposal_id'])" in store
    assert "function register_publication_batch" in store
    assert "function approve_publication_batch" in store
    assert "function approval_batch_snapshot" not in store
    assert "function approve_batch(" not in store
    assert "count($proposal_ids) > 20" in store
    assert "array('CONTENT_RELEASE', 'THEME_RELEASE')" in store
    assert "proposal_ids_json" in store
    assert "FOR UPDATE" in store
    assert "START TRANSACTION" in store
    assert "ROLLBACK" in store
    assert "COMMIT" in store
    assert "remove_approval_lease($proposal_id)" in store
    assert "approved_publication_batch_result_locked" in store
    assert "reconcile_publication_batch_approval" in store
    assert "raos_codex_approval_batch_outcome_indeterminate" in store
    assert "raos_codex_approval_orphan_lease_cleanup_failed" in store
    assert "raos_codex_approval_batch_hash_drift" in store
    assert "raos_codex_self_approval_forbidden" in store
    assert "validate_proposal_integrity" in store
    assert "admin_post_raos_codex_mcp_approve_batch" in main
    assert "check_admin_referer('raos_codex_mcp_approve_batch_'" in main
    assert "wp_check_password" in main
    assert "batch_token . '_' . $batch_hash" in main
    assert (
        "$approved_unix + self::APPLY_LEASE_TTL_SECONDS"
        in store
    )
    assert "proposal_expiry_integrity" in store


def test_batch_rejects_duplicate_content_target_ids_and_slugs() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    snapshot = store.split(
        "private static function build_publication_batch_snapshot", 1
    )[1]
    snapshot = snapshot.split("public static function register_publication_batch", 1)[0]
    assert (
        "$row['payload']['before']['id'] !== $row['payload']['after']['id']" in snapshot
    )
    assert "isset($content_target_ids[$target_id])" in snapshot
    assert "isset($content_target_slugs[$target_slug])" in snapshot
    assert "strtolower(trim($row['payload']['after']['slug']))" in snapshot
    assert "raos_codex_approval_batch_target_conflict" in snapshot


def test_batch_approval_requires_transactional_tables_and_innodb_schema() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    assert store.count("ENGINE=InnoDB {$charset}") == 2
    assert "function require_transactional_tables($table_names)" in store
    assert "information_schema.TABLES" in store
    assert "TABLE_SCHEMA = DATABASE()" in store
    assert "'INNODB' !== $engines[$table_name]" in store
    approval = store.split("public static function approve_publication_batch", 1)[1]
    before_transaction = approval.split("START TRANSACTION", 1)[0]
    assert "require_transactional_tables" in before_transaction
    assert "array(self::table_name(), self::batch_table_name())" in before_transaction


def test_single_approval_is_plugin_only_and_cannot_release_a_batch_subset() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    approval = store.split("public static function approve($proposal_id", 1)[1]
    approval = approval.split(
        "private static function approval_batch_outcome_indeterminate", 1
    )[0]
    assert "'PLUGIN_CHANGE' !== $row['kind']" in approval
    assert "raos_codex_publication_batch_approval_required" in approval


def test_plugin_approval_uses_row_lock_and_ambiguous_commit_reconciliation() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    approval = store.split("public static function approve($proposal_id", 1)[1]
    approval = approval.split(
        "private static function approval_batch_outcome_indeterminate", 1
    )[0]
    assert "require_transactional_tables(array(self::table_name()))" in approval
    assert "WHERE proposal_id = %s FOR UPDATE" in approval
    assert "raos_codex_approval_orphan_lease_cleanup_failed" in approval
    assert "reconcile_plugin_approval" in approval
    assert "$commit_attempted = true" in approval
    reconciliation = store.split(
        "private static function reconcile_plugin_approval", 1
    )[1]
    reconciliation = reconciliation.split(
        "public static function approve($proposal_id", 1
    )[0]
    pending_check = reconciliation.index("'PENDING' !== $row['state']")
    lease_remove = reconciliation.index(
        "RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id)"
    )
    assert pending_check < lease_remove


def test_ambiguous_commit_rechecks_authoritative_state_before_lease_cleanup() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    approval = store.split("public static function approve_publication_batch", 1)[1]
    approval = approval.split("public static function claim_apply", 1)[0]
    orphan_cleanup = approval.index(
        "RAOS_Codex_MCP_Deployment::remove_approval_lease($row['proposal_id'])"
    )
    first_lease_create = approval.index(
        "RAOS_Codex_MCP_Deployment::create_approval_lease("
    )
    assert orphan_cleanup < first_lease_create
    catch = approval.split("} catch (Throwable $error) {", 1)[1]
    catch = catch.split("$code = $error->getMessage();", 1)[0]
    assert "reconcile_publication_batch_approval" in catch
    assert "foreach ($lease_ids" not in catch
    reconciliation = store.split(
        "private static function reconcile_publication_batch_approval", 1
    )[1]
    reconciliation = reconciliation.split(
        "public static function approve_publication_batch", 1
    )[0]
    assert "WHERE batch_token = %s FOR UPDATE" in reconciliation
    assert "WHERE proposal_id = %s FOR UPDATE" in reconciliation
    assert "if ('APPROVED' === $batch['state'])" in reconciliation
    pending_check = reconciliation.index("'PENDING' !== $row['state']")
    lease_remove = reconciliation.index(
        "RAOS_Codex_MCP_Deployment::remove_approval_lease($proposal_id)"
    )
    assert pending_check < lease_remove


def test_exact_batch_claim_is_atomic_idempotent_and_precedes_member_claims() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    claim = store.split("public static function claim_publication_batch_apply", 1)[1]
    claim = claim.split("public static function claim_apply", 1)[0]
    assert "array(self::table_name(), self::batch_table_name())" in claim
    assert "WHERE batch_token = %s FOR UPDATE" in claim
    claim_snapshot = store.split(
        "private static function publication_batch_claim_snapshot_locked", 1
    )[1]
    claim_snapshot = claim_snapshot.split(
        "private static function publication_batch_claim_result", 1
    )[0]
    assert "WHERE proposal_id = %s FOR UPDATE" in claim_snapshot
    assert "SET state = 'APPLYING', result_code = 'BATCH_CLAIMED'" in claim
    assert "applying_at_gmt IS NULL" in claim
    assert "reconcile_publication_batch_claim" in claim
    assert "RAOSWordPressPublicationBatchClaimV1" in store
    for key in (
        "'batch_token' => $batch['batch_token']",
        "'batch_manifest_sha256' => $batch['batch_manifest_sha256']",
        "'proposal_count' => count($batch['proposal_ids'])",
        "'proposal_ids' => $batch['proposal_ids']",
        "'batch_claimed_at_gmt' => self::timestamp_iso($batch['applying_at_gmt'])",
        "'proposals' => $operations",
    ):
        assert key in store
    snapshot = claim_snapshot
    assert "'BATCH_CLAIMED', 'OPERATION_APPLYING'" in snapshot.replace("\n", " ")
    assert "'APPLIED' === $row['state']" in snapshot
    assert "$approved_count === count($proposal_ids)" in snapshot
    assert "$progress_count === count($proposal_ids)" in snapshot
    assert "raos_codex_publication_batch_claim_mixed_state" in snapshot
    fresh = snapshot.split("$approved_count === count($proposal_ids)", 1)[1]
    progress = fresh.split("$progress_count === count($proposal_ids)", 1)[1]
    assert (
        "strtotime($batch['expires_at_gmt'] . ' UTC') <= time()"
        in fresh.split("$progress_count === count($proposal_ids)", 1)[0]
    )
    assert "strtotime($batch['expires_at_gmt'] . ' UTC') <= time()" not in progress

    member_claim = store.split("public static function claim_apply", 1)[1]
    member_claim = member_claim.split(
        "public static function recovery_grace_elapsed", 1
    )[0]
    assert "kind = 'PLUGIN_CHANGE' AND state = 'APPROVED'" in member_claim
    assert "kind IN ('CONTENT_RELEASE','THEME_RELEASE')" in member_claim
    assert "state = 'APPLYING' AND result_code = 'BATCH_CLAIMED'" in member_claim
    batch_branch = member_claim.split("kind IN ('CONTENT_RELEASE','THEME_RELEASE')", 1)[
        1
    ]
    assert "expires_at_gmt >" not in batch_branch


def test_publication_batch_manifest_binds_the_exact_active_theme_tree() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    snapshot = store.split(
        "private static function build_publication_batch_snapshot", 1
    )[1]
    snapshot = snapshot.split("public static function register_publication_batch", 1)[0]
    assert "RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()" in snapshot
    assert "hash_equals($theme_row['before_sha256'], $current_theme_sha256)" in snapshot
    assert (
        "hash_equals($theme_row['after_sha256'], $expected_theme_tree_sha256)"
        in snapshot
    )
    assert "hash_equals($expected_theme_tree_sha256, $current_theme_sha256)" in snapshot
    assert "'expected_theme_tree_sha256' => $expected_theme_tree_sha256" in snapshot

    registration = store.split("public static function register_publication_batch", 1)[
        1
    ]
    registration = registration.split(
        "public static function get_publication_batch", 1
    )[0]
    assert "! self::is_sha256($expected_theme_tree_sha256)" in registration
    assert "build_publication_batch_snapshot(" in registration
    assert "$expected_theme_tree_sha256" in registration

    hydration = store.split("private static function hydrate_publication_batch", 1)[1]
    hydration = hydration.split("public static function public_publication_batch", 1)[0]
    assert "$manifest['expected_theme_tree_sha256']" in hydration
    assert "self::is_sha256($manifest['expected_theme_tree_sha256'])" in hydration

    claim_binding = store.split(
        "private static function publication_batch_theme_binding_matches", 1
    )[1]
    claim_binding = claim_binding.split(
        "private static function publication_batch_claim_snapshot_locked", 1
    )[0]
    assert "RAOS_Codex_MCP_Deployment::active_theme_tree_sha256()" in claim_binding
    assert "raos_codex_publication_batch_claim_theme_drift" in claim_binding
    assert "'BATCH_CLAIMED' === $theme_row['result_code']" in claim_binding

    claim_snapshot = store.split(
        "private static function publication_batch_claim_snapshot_locked", 1
    )[1]
    claim_snapshot = claim_snapshot.split(
        "private static function publication_batch_claim_result", 1
    )[0]
    assert "publication_batch_theme_binding_matches($batch, $rows)" in claim_snapshot

    public_batch = store.split("public static function public_publication_batch", 1)[1]
    public_batch = public_batch.split(
        "private static function approval_outcome_indeterminate", 1
    )[0]
    assert "'expected_theme_tree_sha256'" in public_batch
    assert "'state' => $row['state']" in public_batch


def test_operation_recovery_resolves_one_exact_claimed_batch_binding() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    lookup = store.split(
        "public static function get_claimed_publication_batch_for_proposal", 1
    )[1]
    lookup = lookup.split("private static function hydrate_publication_batch", 1)[0]
    assert "self::get($proposal_id)" in lookup
    assert "'CONTENT_RELEASE' !== $operation['kind']" in lookup
    assert "'APPLYING' !== $operation['state']" in lookup
    assert "'OPERATION_APPLYING' !== $operation['result_code']" in lookup
    assert "validate_proposal_integrity($operation)" in lookup
    assert "state = 'APPROVED'" in lookup
    assert "applying_at_gmt IS NOT NULL" in lookup
    assert "proposal_ids_json LIKE %s" in lookup
    assert "LIMIT 2" in lookup
    assert "1 !== count($tokens)" in lookup
    assert "in_array($proposal_id, $batch['proposal_ids'], true)" in lookup
    assert "$batch['created_by']" in lookup
    for approval_binding in (
        "$batch['approved_by']",
        "$batch['approved_at_gmt']",
        "$batch['approval_reason']",
        "$batch['expires_at_gmt']",
    ):
        assert approval_binding in lookup
    assert "1 === count($matches)" in lookup
    for binding in (
        "$operation['kind']",
        "$operation['created_by']",
        "$operation['created_at_gmt']",
        "$operation['before_sha256']",
        "$operation['after_sha256']",
    ):
        assert binding in lookup
    assert "nullable_hash_matches" in lookup
    assert "raos_codex_publication_batch_binding_indeterminate" in lookup
    assert "state = 'REGISTERED'" not in lookup


def test_expiry_transitions_use_exact_compare_and_swap_then_reread_winner() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    proposal_get = store.split("public static function get($proposal_id)", 1)[1]
    proposal_get = proposal_get.split("private static function hydrate_row", 1)[0]
    assert "AND state = %s AND expires_at_gmt = %s" in proposal_get
    assert "$observed_state" in proposal_get
    assert "$observed_expiry" in proposal_get
    assert "if (1 === $expired)" in proposal_get
    assert "$winner = $wpdb->get_row" in proposal_get

    batch_get = store.split("public static function get_publication_batch", 1)[1]
    batch_get = batch_get.split("private static function hydrate_publication_batch", 1)[
        0
    ]
    assert "AND state = 'REGISTERED' AND expires_at_gmt = %s" in batch_get
    assert "if (1 === $expired)" in batch_get
    assert "$winner = $wpdb->get_row" in batch_get


def test_publication_batch_never_sweeps_global_pending_or_plugins() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()
    content = (PLUGIN / "includes/class-raos-codex-mcp-content.php").read_text()

    approval = store.split("public static function approve_publication_batch", 1)[1]
    approval = approval.split("public static function claim_apply", 1)[0]
    assert "WHERE state = 'PENDING' ORDER BY proposal_id" not in approval
    assert "foreach ($batch['proposal_ids'] as $proposal_id)" in approval
    assert "PLUGIN_CHANGE" not in approval
    assert "raos-codex/publication-batch-register" in content
    assert "'maxItems' => 20" in content
    assert (
        "'required' => array('proposal_ids', 'expected_theme_tree_sha256')" in content
    )
    assert (
        "RAOS_Codex_MCP_Store::is_sha256($input['expected_theme_tree_sha256'])"
        in content
    )


def test_admin_shows_the_exact_suffix_and_batch_success_state() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()

    assert "Enter this visible final 8-character batch suffix:" in main
    assert "Visible after-hash suffix to enter:" in main
    assert "Complete canonical batch manifest (full IDs and hashes)" in main
    assert "Batch approval completed for %d proposals." in main
    assert "State: APPROVED." in main


def test_old_batch_members_are_loaded_directly_even_beyond_latest_fifty() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    review = main.split(
        "private static function publication_batch_review($batch)", 1
    )[1]
    review = review.split(
        "private static function publication_batch_content_review_target", 1
    )[0]
    admin = main.split("public function render_admin_page()", 1)[1]
    admin = admin.split("public function handle_approval()", 1)[0]

    # The standalone overview remains intentionally bounded, but exact batch
    # review follows every manifest ID directly and therefore cannot lose an
    # older member when 50 or more newer pending rows exist.
    assert "RAOS_Codex_MCP_Store::pending_for_admin(50)" in admin
    assert "foreach ($manifest['proposals'] as $index => $entry)" in review
    assert "$proposal_id = $entry['proposal_id'];" in review
    assert "RAOS_Codex_MCP_Store::get($proposal_id)" in review
    assert "pending_for_admin" not in review
    assert "$review = self::publication_batch_review($batch);" in admin
    assert "foreach ($review['rows'] as $index => $review_row)" in admin
    assert "if (empty($rows) && empty($batches))" in admin


def test_admin_batch_review_is_exact_and_fails_closed_before_form_render() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    review = main.split(
        "private static function publication_batch_review($batch)", 1
    )[1]
    review = review.split(
        "private static function render_publication_batch_member", 1
    )[0]
    admin = main.split("public function render_admin_page()", 1)[1]
    admin = admin.split("public function handle_approval()", 1)[0]

    for token in (
        "self::has_exact_keys($batch['manifest'], $manifest_keys)",
        "$proposal_ids !== array_values($proposal_ids)",
        "count(array_unique($proposal_ids)) !== count($proposal_ids)",
        "$proposal_ids !== $sorted_ids",
        "hash_equals($proposal_ids[$index], $entry['proposal_id'])",
        "isset($seen_ids[$entry['proposal_id']])",
        "RAOS_Codex_MCP_Store::validate_proposal_integrity($row)",
        "'PENDING' !== $row['state']",
        "hash_equals($entry['kind'], $row['kind'])",
        "hash_equals($entry['created_at_gmt'], $created_iso)",
        "hash_equals($entry['expires_at_gmt'], $expires_iso)",
        "self::nullable_hash_matches($entry['before_sha256'], $row['before_sha256'])",
        "self::nullable_hash_matches($entry['after_sha256'], $row['after_sha256'])",
        "publication_batch_content_review_target(",
        "publication_batch_theme_review_target(",
        "isset($content_target_ids[$target_id])",
        "isset($content_target_slugs[$target_slug])",
        "RAOS_Codex_MCP_Deployment::THEME_SLUG !== $descriptor['slug']",
        "hash_equals($expected_theme_tree_sha256, $descriptor['file_manifest_sha256'])",
    ):
        assert token in review

    warning_at = admin.index(
        "Approval disabled: the exact batch member review could not be verified."
    )
    form_at = admin.index(
        '<input type="hidden" name="action" value="raos_codex_mcp_approve_batch">'
    )
    form_guard_at = admin.rfind("if (! is_wp_error($review)) {", 0, form_at)
    assert warning_at < form_guard_at < form_at
    assert "create a new exact publication request" in admin


def test_admin_renders_complete_content_and_theme_member_review() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    member_render = main.split(
        "private static function render_publication_batch_member", 1
    )[1]
    member_render = member_render.split("public function render_admin_page()", 1)[0]

    for token in (
        "Batch member %1$d of %2$d: %3$s",
        "Complete immutable member payload (all fields)",
        "Exact content target:",
        "'title' => __('Title'",
        "'slug' => __('Slug'",
        "'excerpt' => __('Excerpt'",
        "Before block markup",
        "After block markup",
        "Exact theme target:",
        "'git_commit' => __('Git commit'",
        "'old_version' => __('Old version'",
        "'new_version' => __('New version'",
        "'package_sha256' => __('Package SHA-256'",
        "'file_manifest_sha256' => __('File manifest SHA-256'",
        "'activation_intent' => __('Activation intent'",
        "'migration_assessment' => __('Migration assessment'",
        "'automatic_apply_eligible' => __('Automatic apply eligible'",
        "Complete theme file manifest",
    ):
        assert token in member_render


def test_disposable_e2e_covers_batch_lease_rollback() -> None:
    harness = (
        ROOT / "tests/wordpress_mcp_v1/e2e/batch_approve_harness.php"
    ).read_text()
    runner = (ROOT / "tests/wordpress_mcp_v1/e2e/run.sh").read_text()

    assert "expect-rollback" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_LEASE_CLEANUP_FAILED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_MISMATCH_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_PLUGIN_SCOPE_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_DUPLICATE_TARGET_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_DUPLICATE_SLUG_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_SUBSET_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_NONTRANSACTIONAL_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_AMBIGUOUS_COMMIT_FAILED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_COMMITTED_LEASE_LOST" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_TTL_NOT_REBOUND" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_ORPHAN_NOT_REPLACED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_CRASH_CONSISTENCY_OK" in harness
    assert "RAOS_E2E_BATCH_CLAIM_SUBSET_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_CLAIM_AMBIGUOUS_COMMIT_FAILED" in harness
    assert "RAOS_E2E_BATCH_CLAIM_REPLAY_FAILED" in harness
    assert "RAOS_E2E_BATCH_CLAIM_AMBIGUOUS_COMMIT_OK" in harness
    assert "class RAOS_E2E_Ambiguous_Commit_WPDB extends wpdb" in harness
    assert "RAOS_E2E_PLUGIN_APPROVAL_AMBIGUOUS_COMMIT_FAILED" in harness
    assert "RAOS_E2E_PLUGIN_APPROVAL_AMBIGUOUS_COMMIT_OK" in harness
    assert "RAOS_Codex_MCP_Deployment::validate_approval_lease" in harness
    assert "'PENDING' !== $readback['state']" in harness
    assert "handle_batch_approval()" in harness
    assert "batch_approve_harness.php expect-rollback" in runner
    assert "batch_approve_harness.php approve" in runner
    assert "batch_approve_harness.php claim-ambiguous-reset" in runner
    assert "batch_approve_harness.php plugin-ambiguous-reset" in runner
    assert "RAOS_WORDPRESS_E2E_PUBLICATION_BATCH_APPROVED_PLUGIN" in runner


def test_disposable_e2e_covers_activationless_store_upgrade() -> None:
    harness = (
        ROOT / "tests/wordpress_mcp_v1/e2e/store_upgrade_harness.php"
    ).read_text()
    runner = (ROOT / "tests/wordpress_mcp_v1/e2e/run.sh").read_text()

    assert "DROP COLUMN idempotency_key" in harness
    assert "DROP COLUMN applying_at_gmt" in harness
    assert "DROP TABLE IF EXISTS" in harness
    assert "update_option(RAOS_Codex_MCP_Store::SCHEMA_OPTION, '1'" in harness
    assert "update_option(RAOS_Codex_MCP_Store::SCHEMA_OPTION, '3'" in harness
    assert "RAOS_E2E_STORE_V3_DEGRADED" in harness
    assert "batch_applying_column" in harness
    assert "RAOS_E2E_STORE_UPGRADE_OK" in harness
    assert "store_upgrade_harness.php degrade" in runner
    assert "store_upgrade_harness.php check" in runner
    assert "store_upgrade_harness.php degrade-v3" in runner


def test_disposable_e2e_covers_idempotency_replay_and_conflict() -> None:
    harness = (ROOT / "tests/wordpress_mcp_v1/e2e/idempotency_harness.php").read_text()
    runner = (ROOT / "tests/wordpress_mcp_v1/e2e/run.sh").read_text()

    assert "RAOS_E2E_IDEMPOTENCY_REPLAY_FAILED" in harness
    assert "raos_codex_idempotency_conflict" in harness
    assert "409 !== $error_data['status']" in harness
    assert "idempotency_harness.php" in runner


def test_store_claim_timestamp_and_recovery_grace_are_private() -> None:
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()

    assert "const RECOVERY_GRACE_SECONDS = 120;" in store
    assert "applying_at_gmt = %s" in store
    assert "function recovery_grace_elapsed" in store
    assert "raos_codex_recovery_grace_active" in store
    public_receipt = store.split("public static function public_operation", 1)[1]
    assert "applying_at_gmt" not in public_receipt
