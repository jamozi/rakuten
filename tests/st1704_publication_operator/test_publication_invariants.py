"""Static regression checks for the publication-only PHP extension."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = (
    ROOT / "changes/st-1704/publication-operator-v2/wordpress-plugin/"
    "raos-bounded-operator/includes/st1704-publication-controller.v2.php"
)


def _source() -> str:
    return CONTROLLER.read_text(encoding="utf-8")


def test_exact_routes_and_combined_v1_v2_firewall_are_bound() -> None:
    source = _source()
    assert "const REST_NAMESPACE = 'raos-operator/v2';" in source
    assert source.count("register_rest_route(") == 7
    for callback in (
        "rest_status",
        "rest_create_proposal",
        "rest_read_proposal",
        "rest_apply",
    ):
        assert f"'callback' => array($this, '{callback}')" in source
    assert "remove_filter(" in source
    assert "guard_operator_rest_route" in source
    assert "guard_combined_operator_rest_route" in source
    assert "return $this->legacy_operator->guard_operator_rest_route(" in source


def test_both_write_gates_and_distinct_admin_approval_are_required() -> None:
    source = _source()
    assert "RAOS_OPERATOR_WRITES_ENABLED === true" in source
    assert "RAOS_ST1704_PUBLICATION_WRITES_ENABLED === true" in source
    assert "self::master_writes_enabled()" in source
    assert "self::publication_writes_enabled()" in source
    assert "admin_post_" in source
    assert "manage_options" in source
    assert "wp_check_password" in source
    assert "approved_by_user_id" in source
    assert "proposer_user_id" in source
    assert "approval_evidence_hash" in source
    assert (
        "register_rest_route(\n            self::REST_NAMESPACE,\n            '/approve'"
        not in source
    )


def test_only_fixed_article_category_and_hash_bound_request_are_representable() -> None:
    source = _source()
    assert "RAOS_ST1704_Publication_Bindings_V2::articles()" in source
    assert "RAOS_ST1704_Publication_Bindings_V2::CATEGORY_CONTRACT" in source
    assert "RAOS_ST1704_Publication_Bindings_V2::CATEGORY_NAME" in source
    assert "st1703-first-suitcase-comparison" in source  # explicit refusal guard
    for key in (
        "packet_sha256",
        "request_sha256",
        "snapshot_payload_sha256",
        "visible_content_sha256",
        "request_token",
    ):
        assert f"'{key}'" in source
    assert "hash('sha256', $canonical)" in source
    assert "hash_equals($canonical, (string) $request->get_body())" in source


def test_content_media_term_creation_and_core_publish_caps_are_bounded() -> None:
    source = _source()
    for forbidden in (
        "wp_insert_term(",
        "wp_create_category(",
        "media_handle_",
        "wp_insert_attachment(",
        "set_post_thumbnail(",
        "add_role(",
        "remove_role(",
    ):
        assert forbidden not in source
    assert "current_user_can('edit_posts')" not in source
    executor_caps = source.split(
        "private static function exact_executor_capabilities", 1
    )[1].split("private function operator_user_binding", 1)[0]
    assert "publish_posts" not in executor_caps
    reconciliation_auth = source.split(
        "private function reconciliation_submission_authentication", 1
    )[1].split("public function handle_reconciliation_cleanup", 1)[0]
    assert "current_user_can('publish_posts')" in reconciliation_auth
    # These server-side fields must be read and hash-bound for preservation;
    # they are not caller inputs and may not be sent as mutation fields.
    for preserved in ("post_title", "post_content", "post_excerpt"):
        assert f"'{preserved}'" in source


def test_apply_is_one_proposal_with_cas_idempotency_audit_and_readback() -> None:
    source = _source()
    assert "If-Match" in source or "if-match" in source.lower()
    assert "Idempotency-Key" in source or "idempotency-key" in source.lower()
    assert "GET_LOCK" in source
    assert "IS_USED_LOCK" in source
    assert "RELEASE_LOCK" in source
    assert "append_audit" in source
    assert "NEEDS_RECOVERY" in source
    assert "ST1704_ARTICLE_PUBLISHED" in source
    assert "wp_update_post(" not in source
    assert "wp_set_post_categories(" not in source
    bounded_write = source.split("private function write_bounded_publication_rows", 1)[
        1
    ].split("private function apply_one_publication", 1)[0]
    assert "DELETE tr FROM {$wpdb->term_relationships}" in bounded_write
    assert "INSERT INTO {$wpdb->term_relationships}" in bounded_write
    assert "UPDATE {$wpdb->posts}" in bounded_write
    assert "SET post_name = %s, post_status = %s," in bounded_write
    assert "post_date = %s, post_date_gmt = %s" in bounded_write
    assert "post_modified = %s, post_modified_gmt = %s" in bounded_write
    assert "AND BINARY post_date = BINARY %s" in bounded_write
    assert "AND BINARY post_date_gmt = BINARY %s" in bounded_write
    assert bounded_write.count("(IS_USED_LOCK(%s) = CONNECTION_ID())") == 3
    execute = source.split("private function execute_apply_under_mutex", 1)[1].split(
        "private function published_state_matches", 1
    )[0]
    mutation = source.split("private function apply_one_publication", 1)[1].split(
        "private function mutation_failure_result", 1
    )[0]
    assert "write_bounded_publication_rows(" in mutation
    fixed_time = execute.index("capture_publication_modified_times()")
    applying = execute.index("SET state = %s, apply_started_at = %s", fixed_time)
    apply = execute.index("$result = $this->apply_one_publication(", applying)
    assert fixed_time < applying < apply
    assert "publication_modified_times_from_gmt(" in mutation
    assert mutation.index("write_bounded_publication_rows(") < mutation.index(
        "$wpdb->query('COMMIT')"
    )
    assert mutation.index(
        "publication_pre_mutation_hooks_are_unobserved()"
    ) < mutation.index("write_bounded_publication_rows(")
    for pre_hook_name in (
        "add_term_relationship",
        "delete_term_relationships",
        "pre_post_update",
    ):
        assert f"'{pre_hook_name}'" not in mutation
    for hook_name in (
        "added_term_relationship",
        "deleted_term_relationships",
        "set_object_terms",
        "pre_post_insert",
        "transition_post_status",
        "new_to_inherit",
        "inherit_revision",
        "draft_to_publish",
        "publish_post",
        "edit_post_post",
        "edit_post",
        "post_updated",
        "save_post_post",
        "save_post_revision",
        "save_post",
        "wp_insert_post",
        "wp_after_insert_post",
        "_wp_put_post_revision",
    ):
        assert f"'{hook_name}'" in mutation
    assert "POST_COMMIT_HOOK_REPLAY_UNCERTAIN" in mutation
    assert "wp_check_for_changed_slugs" in source
    assert "wp_check_for_changed_dates" in source
    assert "_wp_old_slug" in mutation
    assert "_wp_old_date" in mutation
    assert "'delete_post_metadata'" in mutation
    assert "function_exists('wp_after_insert_post')" in mutation
    assert "wp_after_insert_post(" in mutation
