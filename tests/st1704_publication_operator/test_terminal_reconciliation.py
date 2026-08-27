"""Fail-closed source guards for the incident-only terminal reconciliation."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = (
    ROOT
    / "changes/st-1704/publication-operator-v2/wordpress-plugin/"
    "raos-bounded-operator/includes/st1704-publication-controller.v2.php"
)


def source() -> str:
    return CONTROLLER.read_text(encoding="utf-8")


def method(name: str, following: str) -> str:
    php = source()
    start = php.index(f"function {name}")
    end = php.index(f"function {following}", start)
    return php[start:end]


def test_reconciliation_is_admin_only_and_rest_surface_is_unchanged() -> None:
    php = source()
    assert php.count("register_rest_route(") == 7
    assert "RECONCILIATION_CLEANUP_ACTION" in php
    assert "RECONCILIATION_CONFIRM_ACTION" in php
    assert "admin_post_' . self::RECONCILIATION_CLEANUP_ACTION" in php
    assert "admin_post_' . self::RECONCILIATION_CONFIRM_ACTION" in php
    assert "admin_post_nopriv_" not in php
    route_registration = method("register_rest_routes", "can_read")
    assert "reconciliation" not in route_registration.lower()


def test_gate_mode_is_strict_default_off_and_mutually_exclusive() -> None:
    php = source()
    gate = method("reconciliation_gate_enabled", "writes_enabled")
    normal = method("writes_enabled", "reconciliation_writes_enabled")
    incident = method("reconciliation_writes_enabled", "runtime_origin_is_exact")
    assert "RAOS_ST1704_PUBLICATION_RECONCILIATION_WRITES_ENABLED" in gate
    assert "=== true" in gate
    assert "! self::reconciliation_gate_enabled()" in normal
    assert "self::master_writes_enabled()" in incident
    assert "! self::publication_writes_enabled()" in incident
    assert "self::reconciliation_gate_enabled()" in incident


def test_allowlist_binds_only_two_article_post_pairs_without_proposal_constants() -> None:
    targets = method("terminal_reconciliation_targets", "bindings_are_exact")
    assert "st1704-portable-power-station-guide" in targets
    assert "st1704-anker-solix-c300-c800-c1000-differences" in targets
    assert "st1704-countertop-dishwasher-for-small-households" not in targets
    assert "st1704-compact-robot-vacuum-shortlist" not in targets
    assert "self::fixed_revision_post_ids()" in targets
    assert "self::fixed_articles()" in targets
    assert "proposal" not in targets.lower()
    assert "RECONCILIATION_PROPOSAL_ID" not in source()
    assert "reconciliation_proposal_ids" not in source()


def test_candidate_discovery_is_exact_unique_and_never_generic_latest() -> None:
    candidates = method(
        "terminal_reconciliation_candidates_for_update",
        "validate_terminal_reconciliation_receipt",
    )
    assert "BINARY operation = BINARY %s" in candidates
    assert "BINARY state = BINARY %s" in candidates
    assert "BINARY result_code = BINARY %s" not in candidates
    assert "self::OPERATION" in candidates
    assert "'NEEDS_RECOVERY'" in candidates
    assert "FOR UPDATE" in candidates
    assert "validated_stored_proposal(" in candidates
    assert "isset($result[$article_id])" in candidates
    assert "draft_post_id'] !== $target['post_id']" in candidates
    assert "public_slug'] !== $target['public_slug']" in candidates
    assert "LIMIT 1" not in candidates
    assertion = method(
        "terminal_reconciliation_plan_for_assertion",
        "terminal_reconciliation_candidates_for_update",
    )
    assert "terminal_reconciliation_candidates_for_update" in assertion
    assert "proposal_row(" not in assertion
    assert "hash_equals" in assertion
    target = method(
        "terminal_reconciliation_plan_for_target",
        "terminal_reconciliation_candidate_result_error",
    )
    assert "return $candidates;" in target
    assert "terminal_reconciliation_candidate_result_error" in target
    result = method(
        "terminal_reconciliation_candidate_result_error",
        "terminal_reconciliation_plan_for_assertion",
    )
    assert "[A-Z0-9_]{1,64}" in result
    assert "terminal_reconciliation_failure_codes" in result
    assert "candidate_failure_code_mismatch" in result
    assert "RECONCILIATION_FAILURE_CODE" in result
    assert "RECONCILIATION_EXCEPTION_FAILURE_CODE" in result
    assertion = method(
        "terminal_reconciliation_plan_for_assertion",
        "terminal_reconciliation_candidates_for_update",
    )
    assert "reconciliation_allowlist_invalid" in assertion
    assert "return $candidates;" in assertion
    assert "terminal_reconciliation_candidate_result_error" in assertion


def test_admin_preview_exposes_only_a_bounded_error_code_for_diagnosis() -> None:
    render = method(
        "render_terminal_reconciliation_tools",
        "preview_terminal_reconciliation",
    )
    assert "Administrator diagnostic code:" in render
    assert "terminal_reconciliation_diagnostic_code" in render
    assert "$plan->get_error_message()" not in render
    assert "$plan->get_error_data()" not in render
    diagnostic = method(
        "terminal_reconciliation_diagnostic_code",
        "preview_terminal_reconciliation",
    )
    assert "$error->get_error_code()" in diagnostic
    assert "in_array($code, $allowed, true)" in diagnostic
    assert "raos_st1704_reconciliation_preview_unavailable" in diagnostic
    assert "preg_match" not in diagnostic
    assert "get_error_message" not in diagnostic
    assert "get_error_data" not in diagnostic


def test_terminal_receipt_binds_rollback_approval_dates_and_state_without_mutation() -> None:
    receipt = method(
        "validate_terminal_reconciliation_receipt",
        "validate_reconciliation_audit_chain",
    )
    for required in (
        "NEEDS_RECOVERY",
        "terminal_reconciliation_failure_codes",
        "idempotency_key",
        "rollback_json",
        "before_state_json",
        "before_state_hash",
        "state_version",
        "approval_evidence_is_valid",
        "approval_expiry_epoch > time()",
        "created_epoch <= $approved_epoch",
        "approved_epoch <= $apply_epoch",
        "apply_epoch < $approval_expiry_epoch",
        "apply_epoch <= $completed_epoch",
        "review_slug",
        "publication_modified_times_from_gmt",
        "publication_date_fields",
    ):
        assert required in receipt
    assert "(int) $candidate['state_version'] !== 4" in receipt
    assert "hash_equals($proposal_id, $candidate['idempotency_key'])" in receipt
    assert "'failure_code' => $candidate['result_code']" in receipt


def test_full_audit_chain_and_exact_incident_event_sequence_are_verified() -> None:
    audit = method(
        "validate_reconciliation_audit_chain",
        "build_terminal_reconciliation_plan",
    )
    assert "ORDER BY audit_id ASC FOR UPDATE" in audit
    assert "MAX_RECONCILIATION_AUDIT_ROWS" in audit
    assert "hash_equals($previous, $audit_row['previous_hash'])" in audit
    assert "hash('sha256', $material)" in audit
    for event, detail in (
        ("PROPOSAL_CREATED", "PROPOSED"),
        ("HUMAN_APPROVED", "APPROVED"),
        ("APPLY_STARTED", "APPLYING"),
        ("APPLY_FAILED", "$candidate['result_code']"),
        ("RECONCILIATION_CLEANUP_EVENT", "[A-F0-9]{64}"),
        ("RECONCILIATION_PUBLIC_EVENT", "[A-F0-9]{64}"),
    ):
        assert event in audit
        assert detail in audit
    assert "(int) $cleanup['actor_user_id']" in audit
    assert "(int) $candidate['proposer_user_id']" in audit
    assert "$event_epoch < $row_epoch" in audit
    assert "$event_epoch - $row_epoch > 2" in audit
    assert "cleanup_previous_hash" in audit
    assert "count($proposal_events) > 6" in audit


def test_published_state_and_conflicts_are_locked_before_meta_planning() -> None:
    plan = method(
        "build_terminal_reconciliation_plan",
        "capture_reconciliation_published_storage",
    )
    assert "publication_core_redirect_callbacks_are_exact" in plan
    assert "wp_check_post_lock" in plan
    assert "BINARY post_name = BINARY %s" in plan
    assert "$receipt['before']['review_slug']" in plan
    assert "FOR UPDATE" in plan
    assert "capture_reconciliation_published_storage" in plan
    storage = method(
        "capture_reconciliation_published_storage",
        "reconciliation_meta_cleanup_plan",
    )
    assert "$this->capture_post_storage(" in storage
    assert "true" in storage
    for field in (
        "post_date",
        "post_date_gmt",
        "post_modified",
        "post_modified_gmt",
        "content_sha256",
        "excerpt_sha256",
        "protected_post_fields_sha256",
        "snapshot_meta_sha256",
        "title_sha256",
        "category_relationship_sha256",
    ):
        assert field in storage


def test_meta_multiset_allows_only_exact_slug_and_conditional_date_rows() -> None:
    meta = method("reconciliation_meta_cleanup_plan", "rest_verify_revision")
    assert "SELECT meta_id, meta_key, meta_value" in meta
    assert "ORDER BY meta_id ASC FOR UPDATE" in meta
    assert "MAX_META_ROWS" in meta
    assert "encoded_pair" in meta
    assert "reconciliation_meta_missing" in meta
    assert "reconciliation_meta_duplicate" in meta
    assert "reconciliation_meta_extra" in meta
    assert "reconciliation_core_delete_prestate" in meta
    assert "'_wp_old_slug'" in meta
    assert "'_wp_old_date'" in meta
    assert "$before['review_slug']" in meta
    assert "$previous_date !== $published_date" in meta
    assert "expected_after_meta_multiset_sha256" in meta
    assert "self::canonical_json($after_pairs)" in meta
    assert "self::canonical_json($before_pairs)" in meta


def test_meta_plan_covers_slug_only_slug_date_and_same_day_shapes() -> None:
    meta = method("reconciliation_meta_cleanup_plan", "rest_verify_revision")
    slug = meta.index("'meta_key' => '_wp_old_slug'")
    conditional_date = meta.index("if ($previous_date !== $published_date", slug)
    date = meta.index("'meta_key' => '_wp_old_date'", conditional_date)
    assert slug < conditional_date < date
    assert "! in_array(\n                $previous_date" in meta
    assert "count($extras) !== count($expected_extras)" in meta
    assert "$delete_rows === array() && $expected_extras !== array()" in meta


def test_cleanup_hash_binds_terminal_instance_audit_ids_and_before_after_hashes() -> None:
    plan = method(
        "build_terminal_reconciliation_plan",
        "capture_reconciliation_published_storage",
    )
    for field in (
        "apply_started_at",
        "approval_evidence_sha256",
        "approved_at",
        "approved_by_user_id",
        "completed_at",
        "created_at",
        "expires_at",
        "failure_code",
        "proposal_state_version",
        "proposal_state",
        "proposer_user_id",
        "audit_event_hashes",
        "audit_head_sha256",
        "before_state_sha256",
        "before_meta_multiset_sha256",
        "current_meta_rows_sha256",
        "current_published_storage_sha256",
        "expected_after_meta_rows_sha256",
        "expected_after_meta_multiset_sha256",
        "cleanup_rows",
        "post_id",
        "proposal_id",
        "request_json_sha256",
        "review_slug_sha256",
        "rollback_json_sha256",
        "wordpress_release_line",
    ):
        assert f"'{field}'" in plan
    assert "'failure_code' => $receipt['failure_code']" in plan
    assert "hash('sha256', $operation_material)" in plan
    meta = method("reconciliation_meta_cleanup_plan", "rest_verify_revision")
    assert "'meta_id' => $row['meta_id']" in meta
    assert "'key_sha256' => hash('sha256', $row['meta_key'])" in meta
    assert "'value_sha256' => hash('sha256', $row['meta_value'])" in meta


def test_cleanup_uses_exact_meta_id_cas_readback_audit_and_transaction() -> None:
    cleanup = method(
        "execute_terminal_reconciliation_cleanup",
        "execute_reconciled_public_confirmation",
    )
    isolation = cleanup.index("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    start = cleanup.index("START TRANSACTION", isolation)
    plan = cleanup.index("terminal_reconciliation_plan_for_assertion", start)
    delete = cleanup.index("delete_exact_reconciliation_meta_rows", plan)
    readback = cleanup.index("published_state_matches", delete)
    audit = cleanup.index("RECONCILIATION_CLEANUP_EVENT", readback)
    commit = cleanup.index("$wpdb->query('COMMIT')", audit)
    assert isolation < start < plan < delete < readback < audit < commit
    cas = method(
        "delete_exact_reconciliation_meta_rows",
        "execute_reconciled_public_confirmation",
    )
    assert "WHERE meta_id = %d AND post_id = %d" in cas
    assert "BINARY meta_key = BINARY %s" in cas
    assert "BINARY meta_value = BINARY %s" in cas
    assert "array('_wp_old_slug', '_wp_old_date')" in cas
    assert "$deleted !== 1" in cas
    assert "strtoupper($operation_sha256)" in cleanup
    assert "$wpdb->query('ROLLBACK')" in cleanup
    assert "array('CLEANED', 'PUBLIC_CONFIRMED')" in cleanup
    assert "SET state" not in cleanup
    assert "UPDATE {$table}" not in cleanup


def test_cleanup_fault_points_mutex_and_stale_hash_all_roll_back_closed() -> None:
    cleanup = method(
        "execute_terminal_reconciliation_cleanup",
        "execute_reconciled_public_confirmation",
    )
    assert "acquire_publication_mutex" in cleanup
    assert cleanup.count("publication_mutex_is_owned($mutex_name)") >= 3
    assert "hash_equals(\n                    $plan['operation_sha256']" in cleanup
    for fault in (
        "reconciliation transaction unavailable",
        "reconciliation assertion changed",
        "reconciliation metadata CAS failed",
        "reconciliation readback changed",
        "reconciliation receipt failed",
        "reconciliation stage invalid",
    ):
        assert fault in cleanup
    catch = cleanup.split("} catch (Throwable $exception) {", 1)[1]
    assert "$wpdb->query('ROLLBACK')" in catch
    assert "release_publication_mutex" in cleanup


def test_terminal_proposal_counts_and_receipt_fields_never_change() -> None:
    cleanup = method(
        "execute_terminal_reconciliation_cleanup",
        "execute_reconciled_public_confirmation",
    )
    confirmation = method(
        "execute_reconciled_public_confirmation",
        "terminal_reconciliation_plan_for_target",
    )
    for execution in (cleanup, confirmation):
        assert "proposal_table()" not in execution
        assert "SET state" not in execution
        assert "state_version = state_version" not in execution
        assert "result_code =" not in execution
    status = method("rest_status", "rest_revision_status")
    assert "proposal_counts" in status
    assert "self::states()" in status


def test_admin_auth_requires_cookie_caps_nonce_reason_hash_and_password_unset() -> None:
    auth = method(
        "reconciliation_submission_authentication",
        "handle_reconciliation_cleanup",
    )
    for required in (
        "is_user_logged_in()",
        "current_user_can('manage_options')",
        "current_user_can('publish_posts')",
        "wp_get_session_token()",
        "check_admin_referer(",
        "preg_match('/\\A.{10,300}\\z/us'",
        "substr($operation_sha256, -12)",
        "wp_check_password(",
        "unset($_POST['current_password'])",
        "unset($_POST['reconciliation_reason'])",
        "unset($password)",
        "unset($reason)",
    ):
        assert required in auth
    cleanup = method(
        "execute_terminal_reconciliation_cleanup",
        "execute_reconciled_public_confirmation",
    )
    confirmation = method(
        "execute_reconciled_public_confirmation",
        "terminal_reconciliation_plan_for_target",
    )
    for execution in (cleanup, confirmation):
        assert "current_user_can('edit_post', $plan['post_id'])" in execution
        assert "(int) $plan['proposer_user_id'] === (int) $approver->ID" in execution


def test_public_confirmation_is_single_hash_only_and_idempotent() -> None:
    handler = method(
        "handle_reconciliation_public_confirmation",
        "execute_terminal_reconciliation_cleanup",
    )
    assert "verification_evidence_sha256" in handler
    assert "preg_match('/\\A[a-f0-9]{64}\\z/'" in handler
    confirmation = method(
        "execute_reconciled_public_confirmation",
        "terminal_reconciliation_plan_for_target",
    )
    assert "RECONCILIATION_PUBLIC_EVENT" in confirmation
    assert "strtoupper($evidence_sha256)" in confirmation
    assert "hash_equals(" in confirmation
    assert "conflicting confirmation refused" in confirmation
    assert "$plan['stage'] === 'PUBLIC_CONFIRMED'" in confirmation
    assert "$plan['stage'] === 'CLEANED'" in confirmation
    assert "SET state" not in confirmation
    render = method(
        "render_terminal_reconciliation_tools",
        "preview_terminal_reconciliation",
    )
    assert "does not inspect or validate arbitrary HTTP content" in render


def test_cleanup_operation_remains_stable_after_later_audit_events() -> None:
    audit = method(
        "validate_reconciliation_audit_chain",
        "build_terminal_reconciliation_plan",
    )
    plan = method(
        "build_terminal_reconciliation_plan",
        "capture_reconciliation_published_storage",
    )
    assert "$cleanup_operation_sha256 = strtolower($cleanup['detail_code'])" in audit
    assert "$cleanup_previous_hash = $cleanup['previous_hash']" in audit
    clean_branch = plan.split("} else {", 1)[1]
    assert "$operation_sha256 = $audit['cleanup_operation_sha256']" in clean_branch
    assert "audit_head_sha256" not in clean_branch.split(
        "$operation_sha256 = $audit['cleanup_operation_sha256']", 1
    )[1]


def test_sensitive_reconciliation_inputs_are_not_written_to_audit_or_rest() -> None:
    cleanup = method(
        "execute_terminal_reconciliation_cleanup",
        "execute_reconciled_public_confirmation",
    )
    confirmation = method(
        "execute_reconciled_public_confirmation",
        "terminal_reconciliation_plan_for_target",
    )
    for execution in (cleanup, confirmation):
        assert "append_audit(" in execution
        assert "reconciliation_reason" not in execution
        assert "current_password" not in execution
        assert "_wpnonce" not in execution
        audit_arguments = execution.split("append_audit(", 1)[1].split(");", 1)[0]
        assert "meta_value" not in audit_arguments
    assert "register_rest_route(" not in cleanup
    assert "register_rest_route(" not in confirmation
