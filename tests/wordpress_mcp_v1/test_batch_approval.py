from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "changes/wordpress-mcp-v1/wordpress-plugin/raos-codex-mcp-abilities"


def test_store_schema_upgrade_and_idempotency_are_activation_independent() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()
    store = (PLUGIN / "includes/class-raos-codex-mcp-store.php").read_text()
    content = (PLUGIN / "includes/class-raos-codex-mcp-content.php").read_text()

    assert "const SCHEMA_VERSION = '3';" in store
    assert "idempotency_key char(64) NULL" in store
    assert "applying_at_gmt datetime NULL" in store
    assert "raos_codex_publication_batches_v1" in store
    assert "UNIQUE KEY creator_kind_idempotency" in store
    assert "function maybe_upgrade()" in store
    assert "array('RAOS_Codex_MCP_Store', 'maybe_upgrade')" in main
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
    assert "raos_codex_approval_batch_hash_drift" in store
    assert "raos_codex_self_approval_forbidden" in store
    assert "validate_proposal_integrity" in store
    assert "admin_post_raos_codex_mcp_approve_batch" in main
    assert "check_admin_referer('raos_codex_mcp_approve_batch_'" in main
    assert "wp_check_password" in main
    assert "batch_token . '_' . $batch_hash" in main


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


def test_admin_shows_the_exact_suffix_and_batch_success_state() -> None:
    main = (PLUGIN / "raos-codex-mcp-abilities.php").read_text()

    assert "Enter this visible final 8-character batch suffix:" in main
    assert "Visible after-hash suffix to enter:" in main
    assert "Complete canonical batch manifest (full IDs and hashes)" in main
    assert "Batch approval completed for %d proposals." in main
    assert "State: APPROVED." in main


def test_disposable_e2e_covers_batch_lease_rollback() -> None:
    harness = (
        ROOT / "tests/wordpress_mcp_v1/e2e/batch_approve_harness.php"
    ).read_text()
    runner = (ROOT / "tests/wordpress_mcp_v1/e2e/run.sh").read_text()

    assert "expect-rollback" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_LEASE_CLEANUP_FAILED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_MISMATCH_ACCEPTED" in harness
    assert "RAOS_E2E_BATCH_APPROVAL_PLUGIN_SCOPE_ACCEPTED" in harness
    assert "'PENDING' !== $readback['state']" in harness
    assert "handle_batch_approval()" in harness
    assert "batch_approve_harness.php expect-rollback" in runner
    assert "batch_approve_harness.php approve" in runner
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
    assert "RAOS_E2E_STORE_UPGRADE_OK" in harness
    assert "store_upgrade_harness.php degrade" in runner
    assert "store_upgrade_harness.php check" in runner


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
