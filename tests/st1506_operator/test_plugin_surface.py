"""Static fail-closed checks for the WordPress plugin implementation."""

from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
PLUGIN = (
    ROOT / "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/wordpress-plugin/"
    "raos-bounded-operator/raos-bounded-operator.php"
)


def _php() -> str:
    return PLUGIN.read_text(encoding="utf-8")


def test_plugin_registers_only_the_four_closed_rest_routes() -> None:
    php = _php()
    assert "const REST_NAMESPACE = 'raos-operator/v1';" in php
    assert php.count("register_rest_route(") == 4
    for route in (
        "'/status'",
        "'/yoast-checksum'",
        "'/proposals'",
        "'/proposals/(?P<proposal_id>[a-f0-9]{64})/apply'",
    ):
        assert route in php
    route_block = php[php.index("public function register_rest_routes") :]
    route_block = route_block[: route_block.index("private function is_exact_executor")]
    assert "approve" not in route_block.lower()
    assert "permission_callback" in route_block
    assert "__return_true" not in route_block


def test_application_password_is_bound_to_one_identity_and_exact_rest_callbacks() -> (
    None
):
    php = _php()
    assert "const BOUND_OPERATOR_OPTION = 'raos_operator_bound_user_id_v1';" in php
    assert "const NETWORK_IDENTITY_META = 'raos_operator_network_identity_v1';" in php
    for hook in (
        "'wp_authenticate_application_password_errors'",
        "'rest_request_before_callbacks'",
    ):
        assert hook in php
    assert re.search(
        r"add_action\(\s*'wp_authenticate_application_password_errors',\s*"
        r"array\(\$this, 'constrain_operator_application_password'\),\s*10,\s*4\s*\)",
        php,
    )
    assert re.search(
        r"add_filter\(\s*'rest_request_before_callbacks',\s*"
        r"array\(\$this, 'guard_operator_rest_route'\),\s*10,\s*3\s*\)",
        php,
    )
    constrain = php[
        php.index("public function constrain_operator_application_password") :
    ]
    constrain = constrain[
        : constrain.index("public function record_application_password_authentication")
    ]
    for token in (
        "has_exact_operator_role_assignment($user)",
        "operator_network_marker((int) $user->ID)",
        "bind_operator_identity(",
        "runtime_origin_is_exact()",
        "XMLRPC_REQUEST",
        "REST_REQUEST !== true",
        "is_multisite()",
        "raos_operator_application_password_binding_invalid",
        "raos_operator_application_password_multisite_unsupported",
        "raos_operator_application_password_transport_forbidden",
    ):
        assert token in constrain
    identity = php[php.index("private function operator_user_binding") :]
    identity = identity[
        : identity.index("private function is_allowed_operator_rest_handler")
    ]
    for token in (
        "WHERE BINARY option_name = BINARY %s",
        "WHERE user_id = %d AND BINARY meta_key = BINARY %s",
        "add_user_meta(",
        "add_option(",
        "SELECT GET_LOCK(%s, 0)",
        "SELECT RELEASE_LOCK(%s)",
    ):
        assert token in identity
    assert "'plugins_loaded'" in php
    assert "quarantine_existing_operator_binding" in php
    assert "update_option(self::BOUND_OPERATOR_OPTION" not in php
    assert "delete_option(self::BOUND_OPERATOR_OPTION" not in php
    assert "delete_user_meta(" not in php

    firewall = php[php.index("public function guard_operator_rest_route") :]
    firewall = firewall[: firewall.index("public static function activate")]
    for token in (
        "raos_operator_rest_scope_forbidden",
        "is_multisite()",
        "runtime_origin_is_exact()",
        "$handler['callback'][0] === $this",
        "$handler['callback'][1] === $expected_callback",
        "'/status'",
        "'/yoast-checksum'",
        "'/proposals'",
        "'/proposals/[a-f0-9]{64}/apply\\z#'",
        "rest_status",
        "rest_yoast_checksum",
        "rest_create_proposal",
        "rest_apply",
    ):
        assert token in firewall


def test_executor_role_is_exact_and_activation_never_deletes_it() -> None:
    php = _php()
    assert "const ROLE = 'raos_operator_executor';" in php
    for capability in (
        "'read'",
        "'raos_operator_read'",
        "'raos_operator_propose'",
        "'raos_operator_apply'",
    ):
        assert capability in php
    assert "remove_role(" not in php
    assert "register_deactivation_hook" not in php
    assert "register_uninstall_hook" not in php
    assert "uninstall.php" not in php
    executor = re.search(
        r"private function is_exact_executor\(\).*?\n    }",
        php,
        re.DOTALL,
    )
    assert executor is not None
    runtime = executor.group(0)
    for token in (
        "self::$application_password_user_id !== (int) $user->ID",
        "self::$operator_application_password_authenticated",
        "$network_marker['state'] !== 'VALID'",
        "$binding['state'] !== 'VALID'",
        "$binding['user_id'] !== (int) $user->ID",
        "is_multisite()",
        "count($user->roles) !== 1",
        "reset($user->roles) !== self::ROLE",
        "$role_caps === $expected",
        "$all_caps === $expected_all",
        "$user_caps === array(self::ROLE => true)",
    ):
        assert token in runtime
    activation = php[php.index("public static function activate") :]
    activation = activation[: activation.index("private static function install_role")]
    assert "if (is_multisite())" in activation
    assert "does not support multisite" in activation
    assert "manage_options" not in re.search(
        r"private static function install_role\(\).*?\n    }",
        php,
        re.DOTALL,
    ).group(0)


def test_write_gate_is_external_strict_and_has_no_runtime_toggle() -> None:
    php = _php()
    writes = re.search(
        r"private static function writes_enabled\(\).*?\n    }",
        php,
        re.DOTALL,
    )
    assert writes is not None
    assert "defined('RAOS_OPERATOR_WRITES_ENABLED')" in writes.group(0)
    assert "RAOS_OPERATOR_WRITES_ENABLED === true" in writes.group(0)
    assert "update_option('RAOS_OPERATOR_WRITES_ENABLED'" not in php
    assert "register_setting" not in php
    origin = re.search(
        r"private static function runtime_origin_is_exact\(\).*?\n    }",
        php,
        re.DOTALL,
    )
    assert origin is not None
    for token in ("is_ssl()", "home_url('/')", "site_url('/')", "self::SITE_ORIGIN"):
        assert token in origin.group(0)


def test_proposals_require_exact_raw_canonical_bytes_and_are_bounded() -> None:
    php = _php()
    create = php[php.index("public function rest_create_proposal") :]
    create = create[: create.index("private function proposal_response")]
    assert "$request->get_body() !== $canonical" in create
    assert "$proposal_id = hash('sha256', $canonical);" in create
    for token in (
        "MAX_ACTIVE_PROPOSALS_PER_PROPOSER = 20",
        "MAX_PROPOSALS_PER_WINDOW = 5",
        "PROPOSAL_RATE_WINDOW_SECONDS = 600",
        "MAX_PROPOSAL_ROWS = 1000",
    ):
        assert token in php
    assert "DELETE FROM" not in php.upper()
    normalize = php[php.index("private function normalize_proposal_request") :]
    normalize = normalize[
        : normalize.index("private function fixed_yoast_profile_payload")
    ]
    for field in (
        "operator_contract_version",
        "operation",
        "profile_version",
        "request_token",
        "site_origin",
        "ttl_seconds",
        "yoast_profile",
        "theme",
    ):
        assert field in normalize
    assert "self::canonical_json($input['yoast_profile'])" in normalize
    assert "self::canonical_json($this->fixed_yoast_profile_payload())" in normalize
    for token in (
        "raos_operator_proposal_create_lock_v1",
        "proposal_capacity_available",
        "strict_count",
        "$wpdb->last_error !== ''",
        "START TRANSACTION",
        "ROLLBACK",
        "COMMIT",
    ):
        assert token in php


def test_php_canonicalization_is_bound_to_the_golden_vector() -> None:
    php = _php()
    assert "const CANONICAL_VECTOR_BYTES = 870;" in php
    assert (
        "const CANONICAL_VECTOR_SHA256 = "
        "'699a1c5a40786449e3f0241958a594f436e03504472a592d2abc1e3eae2b7d90';"
    ) in php
    create = php[php.index("public function rest_create_proposal") :]
    create = create[: create.index("private function proposal_response")]
    assert "canonicalization_self_check()" in create
    golden = php[php.index("private function canonicalization_self_check") :]
    golden = golden[: golden.index("private function fixed_yoast_profile_payload")]
    for token in (
        "str_repeat('0123456789abcdef', 4)",
        "fixed_yoast_profile_payload()",
        "strlen($canonical) === self::CANONICAL_VECTOR_BYTES",
        "hash('sha256', $canonical)",
    ):
        assert token in golden


def test_checksum_is_exact_pinned_cached_and_never_unknown_pass() -> None:
    php = _php()
    for token in (
        "https://downloads.wordpress.org/plugin-checksums/wordpress-seo/28.3.json",
        "1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f",
        "343370",
        "1952",
        "CHECKSUM_CACHE_TTL = 300",
    ):
        assert token in php
    checksum = php[php.index("public function rest_yoast_checksum") :]
    checksum = checksum[: checksum.index("private function verify_installed_yoast")]
    assert "redirection' => 0" in checksum
    assert "reject_unsafe_urls' => true" in checksum
    assert "UNAVAILABLE" in checksum
    assert "checksum" in checksum.lower() and "lock" in checksum.lower()
    assert "set_transient" in checksum or "wp_cache_set" in checksum


def test_approval_is_admin_only_reauthenticated_hash_bound_and_audited() -> None:
    php = _php()
    assert "admin_post_raos_operator_approve" in php
    assert "add_management_page(" in php
    approval = php[php.index("public function handle_approval") :]
    approval = approval[: approval.index("public function rest_apply")]
    for token in (
        "current_user_can('manage_options')",
        "check_admin_referer('raos_operator_approve_' . $proposal_id)",
        "wp_check_password(",
        "substr($proposal_id, -12)",
        "hash_equals(",
        "proposer_user_id",
        "approved_by_user_id",
        "approval_evidence_hash",
        "approval_expires_at",
    ):
        assert token in approval
    assert "strlen($reason) < 10" in approval
    assert "strlen($reason) > 300" in approval
    assert "normalized" in approval.lower()
    assert "append_audit" in approval
    assert re.search(r"append_audit\(.*?\).*?=== false", approval, re.DOTALL)

    admin = php[php.index("public function render_admin_page") :]
    admin = admin[: admin.index("public function handle_approval")]
    for label in (
        "Exact target",
        "Impact",
        "Before-state hash",
        "Expires",
    ):
        assert label in admin


def test_apply_revalidates_every_hash_gate_and_audit_failure_fails_closed() -> None:
    php = _php()
    apply = php[php.index("public function rest_apply") :]
    apply = apply[: apply.index("private function apply_yoast_profile")]
    for token in (
        "If-Match",
        "Idempotency-Key",
        "hash_equals($proposal_id",
        "request_json",
        "hash('sha256'",
        "before_state_hash",
        "approval_evidence_hash",
        "approved_by_user_id",
        "proposer_user_id",
        "self::writes_enabled()",
        "self::runtime_origin_is_exact()",
        "START TRANSACTION",
        "ROLLBACK",
        "COMMIT",
    ):
        assert token.lower() in apply.lower()
    assert '"' in apply
    assert "append_audit" in apply
    assert "raos_audit" in apply.lower()


def test_apply_is_globally_serialized_through_terminal_audit() -> None:
    php = _php()
    rest_apply = php[php.index("public function rest_apply") :]
    rest_apply = rest_apply[
        : rest_apply.index("private function validated_stored_proposal")
    ]
    for token in (
        "apply_mutex_name()",
        "acquire_apply_mutex($mutex_name)",
        "execute_apply_under_mutex(",
        "finally",
        "release_apply_mutex($mutex_name)",
        "raos_apply_mutex_release_uncertain",
    ):
        assert token in rest_apply
    mutex = php[php.index("private function apply_mutex_name") :]
    mutex = mutex[: mutex.index("private function finish_unhandled_apply_exception")]
    for token in (
        "DB_NAME",
        "$wpdb->prefix",
        "self::SITE_ORIGIN",
        "'raos_apply_v1_' . substr(hash('sha256', $scope), 0, 48)",
        "SELECT GET_LOCK(%s, 0)",
        "SELECT (IS_USED_LOCK(%s) = CONNECTION_ID())",
        "SELECT RELEASE_LOCK(%s)",
        "raos_apply_mutex_unavailable",
    ):
        assert token in mutex
    assert "(string) $acquired !== '1'" in mutex
    assert "(string) $released === '1'" in mutex
    assert "(string) $owned === '1'" in mutex
    execute = php[php.index("private function execute_apply_under_mutex") :]
    execute = execute[: execute.index("private function apply_mutex_name")]
    assert "capture_before_state_hash" in execute
    assert "apply_yoast_profile" in execute
    assert "apply_theme_package" in execute
    assert "finish_success" in execute
    assert "finish_failure" in execute
    assert execute.count("apply_mutex_is_owned($mutex_name)") == 3
    before_mutation_check = execute.index("APPLY_MUTEX_LOST_BEFORE_MUTATION")
    assert execute.index("$wpdb->query('COMMIT')") < before_mutation_check
    assert before_mutation_check < execute.index("apply_yoast_profile")
    assert before_mutation_check < execute.index("apply_theme_package")
    assert "APPLY_MUTEX_LOST_BEFORE_MUTATION" in execute
    assert "APPLY_MUTEX_OWNERSHIP_LOST" in execute
    terminal = php[php.index("private function finish_success") :]
    terminal = terminal[: terminal.index("private static function append_audit")]
    assert "append_audit" in terminal


def test_yoast_merge_is_row_locked_cas_preserving_and_transactional() -> None:
    php = _php()
    yoast = php[php.index("private function apply_yoast_profile") :]
    yoast = yoast[: yoast.index("private function apply_theme_package")]
    for token in (
        "yoast_option_table_is_innodb()",
        "YOAST_OPTION_TABLE_ENGINE_UNSUPPORTED",
        "START TRANSACTION",
        "read_yoast_option_rows(true)",
        "yoast_rows_state_hash($old_rows)",
        "array_replace($old_rows['wpseo']['value'], $profile['wpseo'])",
        "array_replace(",
        "WHERE BINARY option_name = BINARY %s",
        "AND BINARY option_value = BINARY %s",
        "AND BINARY autoload = BINARY %s",
        "YOAST_OPTION_CAS_FAILED",
        "yoast_rows_are_exact($locked_readback, $expected_rows)",
        "COMMIT",
        "flush_yoast_option_caches()",
        "YOAST_COMMIT_UNCERTAIN",
        "YOAST_POST_COMMIT_DRIFT",
        "rollback_yoast_transaction",
    ):
        assert token in yoast
    assert "update_option('wpseo'" not in yoast
    assert "update_option('wpseo_social'" not in yoast

    engine = php[php.index("private function yoast_option_table_is_innodb") :]
    engine = engine[: engine.index("private function read_yoast_option_rows")]
    for token in (
        "SELECT ENGINE FROM information_schema.TABLES",
        "WHERE BINARY TABLE_SCHEMA = BINARY DATABASE()",
        "AND BINARY TABLE_NAME = BINARY %s",
        "get_results(",
        "count($rows) === 1",
        "$wpdb->options",
        "$wpdb->last_error === ''",
        "$rows[0]['ENGINE'] === 'InnoDB'",
    ):
        assert token in engine
    assert "LIMIT 1" not in engine
    capture = php[php.index("private function capture_yoast_before_state_hash") :]
    capture = capture[: capture.index("private function yoast_option_table_is_innodb")]
    assert "yoast_option_table_is_innodb()" in capture
    assert "raos_yoast_option_table_engine_unsupported" in capture
    assert "409" in capture

    rows = php[php.index("private function read_yoast_option_rows") :]
    rows = rows[: rows.index("private function derived_yoast_profile")]
    for token in (
        "SELECT option_name, option_value, autoload",
        "WHERE BINARY option_name = BINARY %s",
        "OR BINARY option_name = BINARY %s",
        "ORDER BY BINARY option_name ASC",
        "FOR UPDATE",
        "count($raw_rows) !== 2",
        "maybe_unserialize($row['option_value'])",
        "exact_serialized_option_value",
    ):
        if token == "exact_serialized_option_value":
            assert "'raw' => $row['option_value']" in rows
        else:
            assert token in rows
    rollback = rows[rows.index("private function rollback_yoast_transaction") :]
    for token in (
        "$wpdb->query('ROLLBACK')",
        "read_yoast_option_rows(false)",
        "yoast_rows_are_exact($actual, $old_rows)",
        "YOAST_TRANSACTION_ROLLBACK_UNCERTAIN",
    ):
        assert token in rollback
    assert "update_option(" not in rollback

    apply = php[php.index("public function rest_apply") :]
    apply = apply[: apply.index("private function apply_yoast_profile")]
    assert "$this->apply_yoast_profile(" in apply
    assert "$spec['yoast_profile']," in apply
    assert "$row['before_state_hash']" in apply
    assert re.search(
        r"private function apply_yoast_profile\(array \$approved_profile, "
        r"\$before_state_hash\)",
        yoast,
    )
    assert "fixed_yoast_profile_payload" in yoast
    assert "derived_yoast_profile" in yoast
    assert "canonical_json($approved_profile)" in yoast
    assert (
        "hash_equals($before_state_hash, $this->yoast_rows_state_hash($old_rows))"
        in yoast
    )


def test_theme_update_has_exact_backup_restore_and_tree_readback() -> None:
    php = _php()
    theme = php[php.index("private function apply_theme_package") :]
    theme = theme[
        : php.index("private function finish_success")
        - php.index("private function apply_theme_package")
    ]
    for token in (
        "MAX_PACKAGE_BYTES",
        "MAX_FILE_BYTES",
        "MAX_FILE_COUNT",
        "from_version",
        "to_version",
        "package_sha256",
        "file_manifest",
        "backup",
        "restore",
        "verify_installed_theme",
    ):
        assert token.lower() in theme.lower()
    assert "version_compare($theme['to_version'], $theme['from_version'], '<=')" in php
    assert "ZipArchive::CHECKCONS" in theme
    assert "(int) $stat['comp_method'] !== 0" in theme
    assert "preg_match('/\\A[A-Za-z0-9._\\/-]+\\z/', $name)" in theme
    assert "THEME_READBACK_FAILED_ROLLED_BACK" in theme
    assert "delete_temp_backup" in theme
    assert "get_stylesheet() !== self::THEME_SLUG" in theme
    for token in (
        "get_filesystem_method() !== 'direct'",
        "WP_Filesystem_Direct",
        "THEME_PREEXISTING_BACKUP_FORBIDDEN",
        "theme_backup_matches($old_state)",
        "THEME_BACKUP_NOT_VERIFIED_NEW_THEME_KEPT",
        "THEME_BACKUP_CLEANUP_FAILED_NEW_THEME_VERIFIED",
        "THEME_BACKUP_CLEANUP_FAILED_STATE_UNCERTAIN",
        "THEME_POST_CLEANUP_DRIFT",
    ):
        assert token in theme
    apply_theme = theme[: theme.index("private function theme_restore_result")]
    assert "$upgrader->restore_temp_backup(" not in apply_theme

    restore = theme[theme.index("private function theme_restore_result") :]
    restore = restore[: restore.index("private function validate_theme_zip")]
    assert restore.count("restore_temp_backup") == 1
    assert restore.index("theme_backup_matches($old_state)") < restore.index(
        "restore_temp_backup"
    )
    assert "THEME_REDUNDANT_BACKUP_NOT_VERIFIED" in restore
    assert "THEME_REDUNDANT_BACKUP_CLEANUP_FAILED" in restore
    assert "THEME_BACKUP_NOT_VERIFIED" in restore
    helpers = restore[restore.index("private function theme_state_matches") :]
    for token in (
        "private function theme_backup_root",
        "private function theme_backup_is_absent",
        "private function theme_backup_matches",
        "private function theme_backup_path_has_no_symlinks",
        "private function capture_theme_tree_at_root",
        "is_link(",
    ):
        assert token in helpers


def test_plugin_contains_no_forbidden_generic_wordpress_surface() -> None:
    php = _php()
    for forbidden in (
        "wp_insert_post(",
        "wp_update_post(",
        "wp_delete_post(",
        "wp_set_object_terms(",
        "wp_set_post_terms(",
        "media_handle_",
        "wp_insert_attachment(",
        "wp_insert_user(",
        "wp_update_user(",
        "wp_delete_user(",
        "activate_plugin(",
        "deactivate_plugins(",
        "delete_plugins(",
        "Plugin_Upgrader",
        "$wpdb->posts",
        "$wpdb->users",
        "eval(",
        "shell_exec(",
        "proc_open(",
        "popen(",
    ):
        assert forbidden not in php
    assert "$_GET" not in php
    assert "$_REQUEST" not in php
