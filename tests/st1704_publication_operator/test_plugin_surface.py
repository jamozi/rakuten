"""Source-level guards for the hand-written publication-only PHP controller."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = (
    ROOT / "changes/st-1704/publication-operator-v2/wordpress-plugin/"
    "raos-bounded-operator/includes/st1704-publication-controller.v2.php"
)


def source() -> str:
    return CONTROLLER.read_text(encoding="utf-8")


def method(name: str, following: str) -> str:
    php = source()
    start = php.index(f"function {name}")
    return php[start : php.index(f"function {following}", start)]


def test_routes_are_distinct_and_exactly_firewalled() -> None:
    php = source()
    assert "const REST_NAMESPACE = 'raos-operator/v2';" in php
    assert php.count("register_rest_route(") == 4
    assert "'/proposals/(?P<proposal_id>[a-f0-9]{64})'" in php
    assert "'/proposals/(?P<proposal_id>[a-f0-9]{64})/apply'" in php
    guard = method("guard_combined_operator_rest_route", "is_exact_v2_handler")
    assert "is_exact_v2_handler" in guard
    assert "authenticated_executor_is_exact" in guard
    assert "legacy_operator->guard_operator_rest_route" in guard
    assert "has_filter('rest_request_before_callbacks', $legacy_callback) === 10" in php
    assert "remove_filter(" in php


def test_wordpress_core_release_line_is_exact_and_fail_closed() -> None:
    php = source()
    instance = method("instance", "wordpress_core_is_supported")
    supported = method("wordpress_core_is_supported", "__construct")
    activation = method("activate", "install_tables")
    assert "const WORDPRESS_CORE_RELEASE_PATTERN" in php
    assert "'/\\A7\\.1(?:\\.[0-9]+)*\\z/'" in php
    assert "if (! self::wordpress_core_is_supported())" in instance
    assert "global $wp_version" in supported
    assert "self::WORDPRESS_CORE_RELEASE_PATTERN" in supported
    assert "if (! self::wordpress_core_is_supported())" in activation
    assert "requires WordPress 7.1.x" in activation


def test_v2_auth_reuses_only_the_exact_bounded_executor_identity() -> None:
    php = source()
    assert "application_password_did_authenticate" in php
    assert "raos_operator_bound_user_id_v1" in php
    assert "raos_operator_network_identity_v1" in php
    assert "count($user->roles) !== 1" in php
    assert "$role_caps === $expected" in php
    assert "$user_caps === array(self::ROLE => true)" in php
    assert "$all_caps === $expected_all" in php
    caps = method("exact_executor_capabilities", "operator_user_binding")
    assert "'read' => true" in caps
    assert "self::CAP_READ => true" in caps
    assert "self::CAP_PROPOSE => true" in caps
    assert "self::CAP_APPLY => true" in caps
    for forbidden in ("publish_posts", "edit_posts", "manage_categories"):
        assert forbidden not in caps


def test_proposal_surface_is_fixed_and_globally_serialized() -> None:
    php = source()
    normalize = method("normalize_proposal_request", "fixed_articles")
    for key in (
        "article_id",
        "category_contract",
        "draft_post_id",
        "operation",
        "operator_contract_version",
        "packet_sha256",
        "profile_version",
        "public_slug",
        "request_sha256",
        "request_token",
        "site_origin",
        "snapshot_payload_sha256",
        "ttl_seconds",
        "visible_content_sha256",
    ):
        assert f"'{key}'" in normalize
    assert "PUBLISH_ST1704_ARTICLE" in php
    assert "count($articles) !== 4" in php
    assert "st1703-first-suitcase-comparison" in php
    assert "GET_LOCK" in php and "IS_USED_LOCK" in php and "RELEASE_LOCK" in php
    active = method("unresolved_states", "canonical_json")
    assert "'APPLYING'" in active
    assert "'NEEDS_RECOVERY'" not in active
    assert "raos_st1704_unresolved_proposal_exists" in php


def test_both_strict_write_gates_and_separate_ledgers_are_present() -> None:
    php = source()
    assert "RAOS_OPERATOR_WRITES_ENABLED === true" in php
    assert "RAOS_ST1704_PUBLICATION_WRITES_ENABLED === true" in php
    assert "raos_st1704_publication_proposals_v2" in php
    assert "raos_st1704_publication_audit_v2" in php
    for state in (
        "PROPOSED",
        "APPROVED",
        "APPLYING",
        "APPLIED",
        "FAILED",
        "NEEDS_RECOVERY",
        "EXPIRED",
    ):
        assert f"'{state}'" in php
    assert "FOR UPDATE" in method("append_audit", "") if False else "FOR UPDATE" in php


def test_snapshot_and_complete_server_state_are_bound_before_approval() -> None:
    capture = method("capture_post_storage", "capture_publication_state")
    for field in (
        "post_title",
        "post_excerpt",
        "post_content",
        "_thumbnail_id",
        "all_meta_sha256",
        "other_meta_sha256",
        "snapshot_meta_sha256",
        "thumbnail_meta_sha256",
        "other_taxonomy_sha256",
        "protected_post_fields_sha256",
    ):
        assert field in capture
    publication = method("capture_publication_state", "register_admin_page")
    assert "'draft'" in publication
    assert "'raos-review-'" in publication
    assert "request_sha256" in publication
    assert "snapshot_payload_sha256" in publication
    assert "SELECT COUNT(*)" in publication


def test_admin_approval_is_distinct_hash_bound_and_reauthenticated() -> None:
    approval = method("handle_approval", "approval_evidence_is_valid")
    assert "current_user_can('manage_options')" in approval
    assert "wp_get_session_token()" in approval
    assert "check_admin_referer(self::APPROVAL_ACTION . '|' . $proposal_id)" in approval
    assert "strlen($reason_input) > self::MAX_REASON_BYTES" in approval
    assert "preg_match('/\\A.{10,300}\\z/us', $reason)" in approval
    assert "wp_check_password(" in approval
    assert "substr($proposal_id, -12)" in approval
    assert "proposer_user_id <> %d" in approval
    assert "capture_publication_state" in approval
    assert "approval_evidence_hash" in approval


def test_apply_mutates_one_post_with_only_the_closed_fields() -> None:
    php = source()
    assert "wp_set_post_categories(" not in php
    assert "wp_update_post(" not in php
    mutation = method("write_bounded_publication_rows", "apply_one_publication")
    assert "DELETE tr FROM {$wpdb->term_relationships}" in mutation
    assert "INSERT INTO {$wpdb->term_relationships}" in mutation
    assert "SELECT %d, %d, %d" in mutation
    assert mutation.count("(IS_USED_LOCK(%s) = CONNECTION_ID())") == 3
    update = mutation[mutation.index('"UPDATE {$wpdb->posts}') :]
    update = update[: update.index('",', update.index('"UPDATE {$wpdb->posts}'))]
    assert "SET post_name = %s, post_status = %s," in update
    assert "post_date = %s, post_date_gmt = %s" in update
    assert "post_modified = %s, post_modified_gmt = %s" in update
    assert "AND BINARY post_name = BINARY %s" in update
    assert "AND BINARY post_status = BINARY %s" in update
    assert "AND BINARY post_date = BINARY %s" in update
    assert "AND BINARY post_date_gmt = BINARY %s" in update
    assert "AND BINARY post_type = BINARY %s" in update
    for forbidden in ("post_title", "post_excerpt", "post_content", "meta_input"):
        assert forbidden not in update
    for forbidden_api in (
        "wp_insert_term(",
        "wp_create_category(",
        "media_handle_",
        "set_post_thumbnail(",
    ):
        assert forbidden_api not in php
    apply = method("rest_apply", "execute_apply_under_mutex")
    assert "get_header('if-match')" in apply
    assert "get_header('idempotency-key')" in apply
    assert "$request->get_body() !== '{}'" in apply


def test_apply_defers_post_mutation_hooks_and_refuses_observed_pre_hooks() -> None:
    modified_times = method(
        "capture_publication_modified_times",
        "write_bounded_publication_rows",
    )
    mutation = method("apply_one_publication", "mutation_failure_result")
    replay_hooks = method(
        "publication_replay_hook_names",
        "publication_pre_mutation_hook_names",
    )
    pre_hooks = method(
        "publication_pre_mutation_hook_names",
        "publication_pre_mutation_hooks_are_unobserved",
    )
    pre_hook_guard = method(
        "publication_pre_mutation_hooks_are_unobserved",
        "capture_publication_hook_snapshot",
    )
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
        assert f"'{hook_name}'" in replay_hooks
        assert (
            f"do_action('{hook_name}'" in mutation
            or f"'{hook_name}'," in mutation
            or f"{hook_name}(" in mutation
        )
    for hook_name in (
        "add_term_relationship",
        "delete_term_relationships",
        "pre_post_update",
    ):
        assert f"'{hook_name}'" in pre_hooks
        assert f"'{hook_name}'" not in replay_hooks
        assert f"do_action('{hook_name}'" not in mutation
        assert f"'{hook_name}'," not in mutation
    assert "array('all')" in pre_hook_guard
    assert "$hook->callbacks !== array()" in pre_hook_guard
    assert "PRE_MUTATION_HOOK_OBSERVER_UNSUPPORTED" in mutation
    assert "function_exists('wp_after_insert_post')" in mutation
    assert "gmdate('Y-m-d H:i:s')" in modified_times
    assert "new DateTimeImmutable('@' . $epoch)" in modified_times
    assert "new DateTimeZone('UTC')" in modified_times
    assert "strict_mysql_utc_epoch($post_modified_gmt)" in modified_times
    assert "function publication_date_fields" in modified_times
    assert "get_gmt_from_date($post_date)" in modified_times
    assert "$post_date_gmt === '0000-00-00 00:00:00'" in modified_times
    zero_gmt = modified_times.index(
        "if ($post_date_gmt === '0000-00-00 00:00:00')"
    )
    local_publish_date = modified_times.index(
        "$post_date = $modified_times['post_modified'];", zero_gmt
    )
    derived_gmt = modified_times.index(
        "$post_date_gmt = get_gmt_from_date($post_date);", local_publish_date
    )
    assert zero_gmt < local_publish_date < derived_gmt
    assert "empty($post_date)" not in modified_times
    observer_check = mutation.index("publication_pre_mutation_hooks_are_unobserved()")
    write = mutation.index("write_bounded_publication_rows(")
    commit = mutation.index("$wpdb->query('COMMIT')")
    replay = mutation.index("'added_term_relationship',", commit)
    assert observer_check < write < commit < replay
    set_terms = mutation.index("'set_object_terms',", replay)
    clean = mutation.index("clean_post_cache($post_id)", set_terms)
    transition = mutation.index("'transition_post_status',", clean)
    edit = mutation.index("do_action('edit_post_post'", transition)
    updated = mutation.index("'post_updated',", edit)
    save = mutation.index("'save_post_post',", updated)
    inserted = mutation.index("do_action('wp_insert_post'", save)
    after_insert = mutation.index("wp_after_insert_post(", inserted)
    assert (
        replay
        < set_terms
        < clean
        < transition
        < edit
        < updated
        < save
        < inserted
        < after_insert
    )
    assert "$nested_revision_increments = $zero_action_increments" in mutation
    assert "$nested_revision_hook_sequence = array(" in mutation
    for nested_hook in (
        "pre_post_insert",
        "transition_post_status",
        "new_to_inherit",
        "inherit_revision",
        "save_post_revision",
        "save_post",
        "wp_insert_post",
        "wp_after_insert_post",
        "_wp_put_post_revision",
    ):
        assert f"'{nested_hook}'" in mutation
    assert "$parent_hook === 'wp_after_insert_post'" in mutation
    assert "$arguments[0]['post_type'] === 'revision'" in mutation
    assert "$arguments[0]['post_status'] === 'inherit'" in mutation
    assert "revision insert payload refused" in mutation
    assert "$revision_post->post_type !== 'revision'" in mutation
    assert "(int) $revision_post->post_parent !== $post_id" in mutation
    assert "!== (int) $revision_post->ID" in mutation
    assert "$nested_revision_increments[$active_hook] <= 1" in mutation
    assert "revision lifecycle replay incomplete" in mutation
    assert "revision lifecycle result unavailable" in mutation
    for revisioned_field in ("post_title", "post_content", "post_excerpt"):
        assert f"$saved_revision->{revisioned_field}" in mutation
        assert f"$revision_expected_fields['{revisioned_field}']" in mutation
    assert "$action_increments[$hook_name] += $increment" in mutation
    assert "$pre_update_data" not in source()
    assert "$published_post->post_modified" in mutation
    assert "$published_post->post_modified_gmt" in mutation
    assert "$published_post->post_date" in mutation
    assert "$published_post->post_date_gmt" in mutation
    assert "$post_after->post_modified" in mutation
    assert "$post_after->post_modified_gmt" in mutation
    assert "$post_after->post_date" in mutation
    assert "$post_after->post_date_gmt" in mutation
    assert mutation.count("$modified_times") >= 8
    assert "'add_post_metadata'" in mutation
    assert "PHP_INT_MAX" in mutation
    assert "PHP_INT_MIN" in mutation
    assert "(int) $object_id === $post_id" in mutation
    assert "$meta_key === '_encloseme'" in mutation
    assert "$meta_key === '_pingme'" in mutation
    assert "$meta_key === '_trackbackme'" in mutation
    assert "$meta_value === '1'" in mutation
    suppressor = mutation[
        mutation.index("$unique_queue_marker") : mutation.index(
            "return $check;", mutation.index("$unique_queue_marker")
        )
    ]
    assert (
        "$unique_queue_marker = ($meta_key === '_encloseme'\n"
        "                        || $meta_key === '_pingme')\n"
        "                    && $unique === true;"
    ) in suppressor
    assert (
        "$trackback_queue_marker = $meta_key === '_trackbackme'\n"
        "                    && $unique === false;"
    ) in suppressor
    assert "return $check;" in mutation
    assert "remove_filter(" in mutation
    assert "finally" in mutation
    assert "! $replay_guards_removed" in mutation
    assert "POST_COMMIT_HOOK_REPLAY_UNCERTAIN" in mutation
    assert "POST_COMMIT_HOOK_REPLAY_EXCEPTION" in mutation
    post_commit_exception = mutation.index("if ($external_effects_possible)")
    rollback = mutation.index("$wpdb->query('ROLLBACK');", post_commit_exception)
    assert post_commit_exception < rollback


def test_reacquired_mutex_closes_orphaned_applying_with_audit_path() -> None:
    apply = method("execute_apply_under_mutex", "published_state_matches")
    orphan = apply[apply.index("if ($row['state'] === 'APPLYING')") :]
    orphan = orphan[: orphan.index("if ($row['state'] !== 'APPROVED'")]
    assert "publication_mutex_is_owned($mutex_name)" in orphan
    assert "$row['rollback_json']" in orphan
    assert "approval_evidence_is_valid(" in orphan
    assert "HOOK_REPLAY_COMPLETED" in orphan
    assert "published_state_matches(" in orphan
    assert "before_state_matches(" in orphan
    assert "finish_success(" in orphan
    assert "finish_failure(" in orphan
    assert "'FAILED'" in orphan
    assert "'NEEDS_RECOVERY'" in orphan
    assert "'ORPHANED_APPLYING_BEFORE_STATE'" in orphan
    assert "'ORPHANED_APPLYING_REPLAY_UNPROVEN'" in orphan
    assert "'ORPHANED_APPLYING_STATE_AMBIGUOUS'" in orphan
    finish = method("finish_failure", "finish_unhandled_apply_exception")
    assert "append_audit(" in finish
    assert "'APPLY_FAILED'" in finish


def test_hook_replay_receipt_is_durable_before_success_and_mutex_bound() -> None:
    execute = method("execute_apply_under_mutex", "published_state_matches")
    receipt = method("persist_hook_replay_completion", "finish_success")
    success = method("finish_success", "finish_failure")
    failure = method("finish_failure", "finish_unhandled_apply_exception")
    unhandled = method("finish_unhandled_apply_exception", "apply_response")
    normal_apply = execute[execute.index("$result = $this->apply_one_publication(") :]
    fixed_time = execute.index("capture_publication_modified_times()")
    applying = execute.index("SET state = %s, apply_started_at = %s", fixed_time)
    assert (
        fixed_time < applying < execute.index("$result = $this->apply_one_publication(")
    )
    assert "$now = $modified_times['post_modified_gmt']" in execute
    assert execute.count("$row['apply_started_at']") >= 2
    assert normal_apply.index("persist_hook_replay_completion(") < normal_apply.index(
        "finish_success("
    )
    assert "SET result_code = %s" in receipt
    assert "AND result_code IS NULL" in receipt
    assert "AND BINARY apply_started_at = BINARY %s" in receipt
    assert "$modified_times['post_modified_gmt']" in receipt
    assert "'HOOK_REPLAY_COMPLETED'" in receipt
    assert "AND result_code = %s" in success
    assert "self::HOOK_REPLAY_COMPLETED" in success
    assert "WHEN BINARY result_code = BINARY %s THEN result_code" in failure
    assert "OR BINARY result_code = BINARY %s" in failure
    assert failure.count("self::HOOK_REPLAY_COMPLETED") == 2
    for terminal in (receipt, success, failure):
        start = terminal.index("$wpdb->query('START TRANSACTION')")
        assert terminal.index("publication_mutex_is_owned($mutex_name)", start) > start
        commit = terminal.index("$wpdb->query('COMMIT')")
        assert (
            terminal.rindex("publication_mutex_is_owned($mutex_name)", start, commit)
            < commit
        )
    assert unhandled.index("publication_mutex_is_owned($mutex_name)") < (
        unhandled.index("proposal_row($proposal_id)")
    )


def test_success_receipt_locks_preserved_storage_through_applied_commit() -> None:
    php = source()
    capture = method("capture_post_storage", "capture_publication_state")
    readback = method("published_state_matches", "before_state_matches")
    success = method("finish_success", "finish_failure")
    assert "$lock_clause = $for_update ? ' FOR UPDATE' : '';" in capture
    assert capture.count("{$lock_clause}") == 3
    assert "FROM {$wpdb->postmeta}" in capture
    assert "FROM {$wpdb->term_relationships} AS tr" in capture
    assert "$lock_storage = false" in readback
    assert "$this->capture_post_storage(" in readback
    isolation = success.index("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
    start = success.index("$wpdb->query('START TRANSACTION')", isolation)
    post_lock = success.index("FOR UPDATE", start)
    locked_readback = success.index("published_state_matches(", post_lock)
    applied = success.index("SET state = %s", locked_readback)
    commit = success.index("$wpdb->query('COMMIT')", applied)
    assert isolation < start < post_lock < locked_readback < applied < commit
    assert "$modified_times,\n                true" in success
    assert php.count("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE") == 1
    assert php.count("$modified_times,\n                true") == 1


def test_post_write_readback_rollback_and_terminal_replay_fail_closed() -> None:
    php = source()
    replay = method("execute_apply_under_mutex", "published_state_matches")
    assert "terminal_replay_invalid" in replay
    assert "published_state_matches" in replay
    readback = method("published_state_matches", "before_state_matches")
    for key in (
        "all_meta_sha256",
        "content_sha256",
        "excerpt_sha256",
        "featured_media_id",
        "other_taxonomy_sha256",
        "protected_post_fields_sha256",
        "snapshot_meta_sha256",
        "thumbnail_meta_sha256",
        "title_sha256",
    ):
        assert f"'{key}'" in readback
    assert "'category_relationship_sha256'" in readback
    assert "'term_order' => 0" in readback
    assert "$new['category_relationship_sha256']" in readback
    assert "$expected_publication_dates['post_date']" in readback
    assert "$expected_publication_dates['post_date_gmt']" in readback
    failure = method("mutation_failure_result", "decode_exact_base64")
    rollback = method("rollback_post_state", "persist_hook_replay_completion")
    assert "is_array($modified_times)" in failure
    assert "rollback_post_state(" in failure
    assert "$mutex_name" in failure
    assert "$wpdb->postmeta" not in rollback
    assert "meta_rows" not in rollback
    assert "$wpdb->update(" not in rollback
    assert "post_title" not in rollback
    assert "post_content" not in rollback
    assert "post_excerpt" not in rollback
    assert "SELECT post_name, post_status, post_date, post_date_gmt," in rollback
    assert "SET post_name = %s, post_status = %s," in rollback
    assert "post_date = %s, post_date_gmt = %s" in rollback
    assert "AND BINARY post_name = BINARY %s" in rollback
    assert "AND BINARY post_status = BINARY %s" in rollback
    assert "AND BINARY post_date = BINARY %s" in rollback
    assert "AND BINARY post_date_gmt = BINARY %s" in rollback
    assert "AND BINARY post_modified = BINARY %s" in rollback
    assert "AND BINARY post_modified_gmt = BINARY %s" in rollback
    assert "count($current_categories) !== 1" in rollback
    assert "(int) $current_categories[0]['term_order'] !== 0" in rollback
    assert "DELETE tr FROM {$wpdb->term_relationships}" in rollback
    assert "AND tr.term_taxonomy_id = %d" in rollback
    assert "AND BINARY tt.taxonomy = BINARY %s" in rollback
    assert "INSERT INTO {$wpdb->term_relationships}" in rollback
    assert "old_category_relationships" in rollback
    assert "DELETE FROM {$wpdb->term_relationships}" not in rollback
    assert rollback.count("(IS_USED_LOCK(%s) = CONNECTION_ID())") == 3
    assert "wp_update_term_count_now(" in rollback
    assert "taxonomy_exists(" in rollback
    assert "$affected_category_tt_ids" in rollback
    assert "before_state_matches" in rollback
    assert "'NEEDS_RECOVERY'" in php
    assert "ST1704_ARTICLE_PUBLISHED" in php
    assert "RAOS_ST1704_PUBLICATION_OPERATOR_APPLY_V2" in php
