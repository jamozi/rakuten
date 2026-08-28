"""Static fail-closed checks for the WordPress plugin implementation."""

from __future__ import annotations

import hashlib
import json
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
    mutex = identity[identity.index("private function identity_mutex_name") :]
    assert "private function identity_mutex_name()" in mutex
    assert "self::NETWORK_IDENTITY_META" in mutex
    assert "self::BOUND_OPERATOR_OPTION" in mutex
    assert "self::SITE_ORIGIN" in mutex
    assert "$user_id" not in mutex
    bind = identity[identity.index("private function bind_operator_identity") :]
    bind = bind[: bind.index("private function identity_mutex_name")]
    binding_read = bind.index("operator_user_binding()")
    marker_read = bind.index("operator_network_marker($user_id)")
    assert binding_read < marker_read
    pre_marker = bind[binding_read:marker_read]
    assert "$binding['state'] !== 'VALID'" in pre_marker
    assert "$binding['user_id'] !== $user_id" in pre_marker
    assert "return false" in pre_marker

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
    install_role = re.search(
        r"private static function install_role\(\).*?\n    }",
        php,
        re.DOTALL,
    )
    assert install_role is not None
    assert "manage_options" not in install_role.group(0)


def test_activation_requires_exact_role_readback_before_tables_and_audit() -> None:
    php = _php()
    activation = php[php.index("public static function activate") :]
    activation = activation[
        : activation.index("private static function append_activation_audit")
    ]
    role_gate = activation.index("if (! self::install_role())")
    role_failure = activation.index("RAOS operator role initialization failed.")
    tables = activation.index("self::install_tables()")
    audit = activation.index("self::append_activation_audit()")
    assert role_gate < role_failure < tables < audit
    failure_branch = activation[role_gate:tables]
    assert "wp_die(" in failure_branch
    assert "ROLE_AND_TABLES_READY" not in failure_branch

    install_role = php[php.index("private static function install_role") :]
    install_role = install_role[
        : install_role.index("private static function exact_executor_capabilities")
    ]
    for token in (
        "$created = add_role(",
        "! $created instanceof WP_Role",
        "return false;",
        "foreach (array_keys($role->capabilities) as $capability)",
        "$role->remove_cap($capability)",
        "$role->add_cap($capability, $grant)",
        "$verified = get_role(self::ROLE)",
        "$verified instanceof WP_Role",
        "$verified->capabilities === $exact",
        "self::persisted_executor_role_is_exact()",
        "catch (Throwable $exception)",
    ):
        assert token in install_role
    assert install_role.index("$verified = get_role(self::ROLE)") < install_role.index(
        "$verified->capabilities === $exact"
    )


def test_activation_validates_complete_table_schemas_before_success_audit() -> None:
    php = _php()
    activation = php[php.index("public static function activate") :]
    activation = activation[
        : activation.index("private static function append_activation_audit")
    ]
    install = activation.index("self::install_tables()")
    schema_gate = activation.index("if (! self::operator_table_schemas_are_exact())")
    schema_failure = activation.index(
        "RAOS operator table schema initialization failed."
    )
    success_audit = activation.index("self::append_activation_audit()")
    assert install < schema_gate < schema_failure < success_audit

    schemas = php[
        php.index("private static function operator_table_schemas_are_exact") :
    ]
    schemas = schemas[
        : schemas.index("private static function operator_table_is_innodb")
    ]
    for token in (
        "self::operator_tables_are_innodb()",
        "operator_expected_charset_and_collation()",
        "operator_table_character_set_is_exact(",
        "information_schema.COLLATIONS",
        "information_schema.COLLATION_CHARACTER_SET_APPLICABILITY",
        "CCSA.CHARACTER_SET_NAME, T.TABLE_COLLATION",
        "information_schema.COLUMNS",
        "ORDER BY ORDINAL_POSITION ASC",
        "count($columns) !== count($expected_columns)",
        "CHARACTER_MAXIMUM_LENGTH",
        "CHARACTER_SET_NAME, COLLATION_NAME",
        "COLUMN_DEFAULT",
        "information_schema.STATISTICS",
        "ORDER BY BINARY INDEX_NAME ASC, SEQ_IN_INDEX ASC",
        "count($indexes) !== count($expected_indexes)",
        "$index['SUB_PART'] !== null",
        "information_schema.TABLE_CONSTRAINTS",
        "ORDER BY BINARY CONSTRAINT_NAME ASC",
        "count($constraints) !== count($expected_constraints)",
    ):
        assert token in schemas
    assert "=== $expected_character_set" in schemas
    assert "=== $expected_collation" in schemas
    for required_column in (
        "internal_id",
        "proposal_id",
        "idempotency_key",
        "state_version",
        "audit_id",
        "event_hash",
    ):
        assert f"array('{required_column}'," in schemas
    for required_index in (
        "array('proposal_id', 0, 1, 'proposal_id')",
        "array('idempotency_key', 0, 1, 'idempotency_key')",
        "array('state_expiry', 1, 2, 'expires_at')",
        "array('event_hash', 0, 1, 'event_hash')",
        "array('proposal_events', 1, 2, 'audit_id')",
    ):
        assert required_index in schemas
    for required_constraint in (
        "array('proposal_id', 'UNIQUE')",
        "array('idempotency_key', 'UNIQUE')",
        "array('event_hash', 'UNIQUE')",
    ):
        assert required_constraint in schemas


def test_role_durable_readback_is_closed_and_rejects_stale_or_excessive() -> None:
    php = _php()
    durable = php[
        php.index("private static function persisted_executor_role_is_exact()") :
    ]
    durable = durable[
        : durable.index("private static function exact_executor_capabilities")
    ]
    for token in (
        "global $wpdb;",
        "$option_name = $wpdb->prefix . 'user_roles';",
        "SELECT option_value FROM {$wpdb->options}",
        "WHERE BINARY option_name = BINARY %s",
        "$wpdb->prepare(",
        "$wpdb->last_error !== ''",
        "count($rows) !== 1",
        "count($rows[0]) !== 1",
        "is_serialized($rows[0]['option_value'], true)",
        "@unserialize(",
        "array('allowed_classes' => false)",
        "count($record) === 2",
        "$record['name'] === 'RAOS Operator Executor'",
        "$record['capabilities'] === self::exact_executor_capabilities()",
    ):
        assert token in durable
    assert "maybe_unserialize" not in durable
    assert "$_GET" not in durable
    assert "$_POST" not in durable
    assert "$_REQUEST" not in durable
    assert "LIMIT 1" not in durable


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
        "PROPOSAL_CREATE_MUTEX_PURPOSE",
        "acquire_auxiliary_mutex",
        "release_auxiliary_mutex",
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
    assert checksum.count("get_transient('raos_operator_yoast_checksum_v1')") == 2
    assert checksum.index("acquire_auxiliary_mutex") < checksum.index(
        "$locked_cached = get_transient"
    )
    assert checksum.count("auxiliary_mutex_is_owned($mutex_name)") >= 3
    assert (
        "$result = $this->auxiliary_mutex_is_owned($mutex_name)\n"
        "                    ? $this->compute_yoast_checksum()"
    ) in checksum
    assert checksum.index("set_transient") < checksum.index("release_auxiliary_mutex")

    verifier = php[php.index("private function verify_installed_yoast") :]
    verifier = verifier[: verifier.index("public function rest_create_proposal")]
    for token in (
        "$expected[$path] = true;",
        "$expected_casefold[$folded] = $path;",
        "$this->ascii_casefold_path($path)",
        "$this->ascii_casefold_path($relative)",
        "$actual_casefold[$folded] !== $relative",
        "$expected_casefold[$folded] !== $relative",
        "! isset($expected[$relative])",
    ):
        assert token in verifier
    assert "$expected[strtolower($relative)]" not in verifier
    casefold = php[php.index("private function ascii_casefold_path") :]
    casefold = casefold[: casefold.index("private function capture_theme_state")]
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZ" in casefold
    assert "abcdefghijklmnopqrstuvwxyz" in casefold
    assert "strtolower" not in casefold


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
    for token in (
        "strlen($reason_input) > 1200",
        "wp_check_invalid_utf8($reason_input) !== $reason_input",
        "preg_match('//u', $reason_input) !== 1",
        "$reason = sanitize_textarea_field($reason_input)",
        "wp_check_invalid_utf8($reason) !== $reason",
        "preg_match('/\\A.{10,300}\\z/us', $reason) !== 1",
    ):
        assert token in approval
    assert approval.index("wp_check_invalid_utf8($reason_input)") < approval.index(
        "sanitize_textarea_field($reason_input)"
    )
    assert "mb_strlen" not in approval
    assert "preg_match_all(" not in approval
    assert "$reason_scalars" not in approval
    assert "strlen($reason)" not in approval
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


def test_applied_replay_validates_exact_operation_payload_before_receipt() -> None:
    php = _php()
    outer = php[php.index("public function rest_apply") :]
    outer = outer[: outer.index("private function execute_apply_under_mutex")]
    under_mutex = php[php.index("private function execute_apply_under_mutex") :]
    under_mutex = under_mutex[: under_mutex.index("private function apply_mutex_name")]

    outer_replay = outer.index("$row['state'] === 'APPLIED'")
    assert outer.index("$request->get_header('if-match')") < outer_replay
    assert outer.index("$request->get_header('idempotency-key')") < outer_replay
    for apply in (outer, under_mutex):
        replay = apply.index("$row['state'] === 'APPLIED'")
        receipt = apply.index("$this->apply_response($row, true)", replay)
        for token in (
            "$request->get_header('content-type') !== 'application/json'",
            "$body !== '{}'",
            "$request->get_header('content-type') !== 'application/zip'",
            "strlen($body) !== $spec['theme']['package_size']",
            "hash_equals($spec['theme']['package_sha256'], hash('sha256', $body))",
        ):
            assert apply.index(token) < replay < receipt


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
    assert execute.count("apply_mutex_is_owned($mutex_name)") == 4
    before_mutation_check = execute.index("APPLY_MUTEX_LOST_BEFORE_MUTATION")
    assert execute.index("$wpdb->query('COMMIT')") < before_mutation_check
    assert before_mutation_check < execute.index("apply_yoast_profile")
    assert before_mutation_check < execute.index("apply_theme_package")
    assert "APPLY_MUTEX_LOST_BEFORE_MUTATION" in execute
    assert "APPLY_MUTEX_OWNERSHIP_LOST" in execute
    terminal = php[php.index("private function finish_success") :]
    terminal = terminal[: terminal.index("private static function append_audit")]
    assert "append_audit" in terminal
    for name in ("finish_success", "finish_failure"):
        finish = terminal[terminal.index(f"private function {name}") :]
        if name == "finish_success":
            finish = finish[: finish.index("private function finish_failure")]
        else:
            finish = finish[: finish.index("private function apply_response")]
        transaction = finish.index("START TRANSACTION")
        ownership = finish.index("apply_mutex_is_owned($mutex_name)")
        update = finish.index("UPDATE {$table}")
        assert transaction < ownership < update
        lost = finish[ownership:update]
        assert "ROLLBACK" in lost
        assert "raos_apply_mutex_ownership_lost" in lost
    unhandled = php[php.index("private function finish_unhandled_apply_exception") :]
    unhandled = unhandled[: unhandled.index("private function validated_stored_proposal")]
    assert unhandled.index("apply_mutex_is_owned($mutex_name)") < unhandled.index(
        "finish_failure("
    )


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
    assert "version_compare(" in php
    assert "$reviewed['to_version']" in php
    assert "$reviewed['from_version']" in php
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


def test_unreviewed_theme_candidate_cannot_replace_stage_captured_release() -> None:
    php = _php()
    release_match = re.search(
        r"const REVIEWED_THEME_RELEASE_JSON = '([^']+)';",
        php,
    )
    release_hash_match = re.search(
        r"const REVIEWED_THEME_RELEASE_JSON_SHA256 = '([a-f0-9]{64})';",
        php,
    )
    runtime_hash_match = re.search(
        r"const REVIEWED_THEME_RUNTIME_MANIFEST_SHA256 = '([a-f0-9]{64})';",
        php,
    )
    assert release_match is not None
    assert release_hash_match is not None
    assert runtime_hash_match is not None
    release_bytes = release_match.group(1).encode()
    assert hashlib.sha256(release_bytes).hexdigest() == release_hash_match.group(1)
    release = json.loads(release_bytes)
    assert release["slug"] == "kurashinoshirube-child"
    assert release["from_version"] == release["to_version"] == "1.1.1"
    assert "const REVIEWED_THEME_RELEASE_STATE = 'NO_REVIEWED_UPGRADE';" in php

    runtime_manifest = (
        ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
    ).read_bytes()
    assert hashlib.sha256(runtime_manifest).hexdigest() != runtime_hash_match.group(1)
    theme_contract = json.loads(
        (
            ROOT
            / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
            "kurashinoshirube-child/theme-contract.v1.json"
        ).read_bytes()
    )
    assert theme_contract["theme_version"] == "1.3.7"
    assert theme_contract["theme_version"] != release["to_version"]

    current_theme_root = (
        ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
        "kurashinoshirube-child"
    )
    reviewed_files = {entry["path"]: entry for entry in release["file_manifest"]}
    current_style = (current_theme_root / "style.css").read_bytes()
    assert hashlib.sha256(current_style).hexdigest() != reviewed_files["style.css"][
        "sha256"
    ]
    assert release["package_size"] > 0
    assert re.fullmatch(r"[a-f0-9]{64}", release["package_sha256"])

    normalize = php[php.index("private function normalize_theme_spec") :]
    normalize = normalize[: normalize.index("private function has_only_keys")]
    for token in (
        "reviewed_theme_release_binding()",
        "self::canonical_json($normalized) !== self::REVIEWED_THEME_RELEASE_JSON",
        "raos_theme_release_not_reviewed",
        "self::REVIEWED_THEME_RELEASE_STATE !== 'AVAILABLE'",
        "raos_theme_release_not_available",
        "return $reviewed;",
    ):
        assert token in normalize


def test_auxiliary_mutexes_are_connection_owned_reclaimable_and_fail_closed() -> None:
    php = _php()
    mutex = php[php.index("private function auxiliary_mutex_name") :]
    mutex = mutex[: mutex.index("private function compute_yoast_checksum")]
    for token in (
        "DB_NAME",
        "$wpdb->prefix",
        "self::SITE_ORIGIN",
        "self::CHECKSUM_MUTEX_PURPOSE",
        "self::PROPOSAL_CREATE_MUTEX_PURPOSE",
        "SELECT IS_USED_LOCK(%s)",
        "SELECT GET_LOCK(%s, 0)",
        "SELECT (IS_USED_LOCK(%s) = CONNECTION_ID())",
        "SELECT RELEASE_LOCK(%s)",
        "(string) $released === '1'",
    ):
        assert token in mutex
    assert "add_option(" not in mutex
    assert "delete_option(" not in mutex

    checksum = php[php.index("public function rest_yoast_checksum") :]
    checksum = checksum[: checksum.index("private function auxiliary_mutex_name")]
    assert checksum.count("get_transient('raos_operator_yoast_checksum_v1')") == 2
    assert "YOAST_CHECKSUM_LOCK_LOST" in checksum
    assert "YOAST_CHECKSUM_LOCK_RELEASE_UNCERTAIN" in checksum
    assert ": $locked_result;" in checksum
    assert "$from_cache = true;" in checksum
    assert checksum.index("set_transient") < checksum.index("release_auxiliary_mutex")
    post_release = checksum[checksum.index("if (! $released)") :]
    assert "YOAST_CHECKSUM_INTERNAL_INVALID" not in post_release

    create = php[php.index("public function rest_create_proposal") :]
    create = create[: create.index("private function proposal_capacity_available")]
    for token in (
        "acquire_auxiliary_mutex($mutex_name)",
        "create_proposal_under_mutex(",
        "auxiliary_mutex_is_owned($mutex_name)",
        "release_auxiliary_mutex($mutex_name)",
        "raos_proposal_creation_lock_release_uncertain",
    ):
        assert token in create
    assert "raos_operator_proposal_create_lock_v1" not in create
    assert "add_option(" not in create
    assert "delete_option(" not in create
    create_under_lock = create[
        create.index("private function create_proposal_under_mutex") :
    ]
    assert create_under_lock.index(
        "auxiliary_mutex_is_owned"
    ) < create_under_lock.index("START TRANSACTION")
    assert create_under_lock.index("append_audit") < create_under_lock.index("COMMIT")


def test_activation_audit_is_innodb_serialized_and_rolls_back_on_failure() -> None:
    php = _php()
    activation = php[php.index("public static function activate") :]
    activation = activation[: activation.index("private static function install_role")]
    assert activation.index("self::install_tables()") < activation.index(
        "self::append_activation_audit()"
    )
    audit = activation[
        activation.index("private static function append_activation_audit") :
    ]
    assert "operator_tables_are_innodb()" in audit
    assert audit.index("START TRANSACTION") < audit.index("append_audit(")
    assert audit.index("append_audit(") < audit.index("COMMIT")
    assert audit.count("ROLLBACK") >= 3
    for token in (
        "self::proposal_table()",
        "self::audit_table()",
        "SELECT ENGINE FROM information_schema.TABLES",
        "WHERE BINARY TABLE_SCHEMA = BINARY DATABASE()",
        "$rows[0]['ENGINE'] === 'InnoDB'",
    ):
        assert token in audit


def test_all_exact_proposal_states_replay_without_mutation_or_terminal_409() -> None:
    php = _php()
    create = php[php.index("public function rest_create_proposal") :]
    create = create[: create.index("private function proposal_capacity_available")]
    assert "raos_terminal_proposal_requires_new_token" not in create
    replay = create[
        create.index("private function validated_proposal_replay_response") :
    ]
    for state in (
        "PROPOSED",
        "APPROVED",
        "APPLYING",
        "APPLIED",
        "FAILED",
        "NEEDS_RECOVERY",
        "EXPIRED",
    ):
        assert f"'{state}'" in replay
    for token in (
        "request_json",
        "hash('sha256', $row['request_json'])",
        "$normalized['operation'] !== $row['operation']",
        "proposer_user_id",
        "strict_mysql_utc_epoch",
        "$expires_epoch - $created_epoch !== self::DEFAULT_TTL",
        "proposal_response($row, true)",
    ):
        assert token in replay
    create_under_lock = create[
        create.index("private function create_proposal_under_mutex") :
    ]
    assert "$created_epoch = time();" in create_under_lock
    assert "$created_epoch + $normalized['ttl_seconds']" in create_under_lock


def test_orphaned_applying_is_audited_into_recovery_after_mutex_reacquisition() -> None:
    php = _php()
    outer = php[php.index("public function rest_apply") :]
    outer = outer[: outer.index("private function execute_apply_under_mutex")]
    assert "$row['state'] !== 'APPLYING'" in outer
    execute = php[php.index("private function execute_apply_under_mutex") :]
    execute = execute[: execute.index("private function apply_mutex_name")]
    orphan = execute[execute.index("if ($row['state'] === 'APPLYING')") :]
    orphan = orphan[: orphan.index("if ($row['state'] !== 'APPROVED'")]
    assert orphan.index("apply_mutex_is_owned") < orphan.index("finish_failure")
    assert "'NEEDS_RECOVERY'" in orphan
    assert "'ORPHANED_APPLYING_RECOVERED'" in orphan
    finish = php[php.index("private function finish_failure") :]
    finish = finish[: finish.index("private function apply_response")]
    assert "WHERE proposal_id = %s AND state = %s" in finish
    assert "'APPLYING'" in finish
    assert "'APPLY_FAILED'" in finish
    assert finish.index("append_audit") < finish.index("COMMIT")


def test_theme_stage_is_private_identity_bound_and_rechecked_before_upgrader() -> None:
    php = _php()
    stage = php[php.index("private function write_private_theme_stage") :]
    stage = stage[: stage.index("private function apply_theme_package")]
    for token in (
        "random_bytes(24)",
        "mkdir($directory, 0700)",
        "chmod($directory, 0700)",
        "fopen($path, 'x+b')",
        "chmod($path, 0600)",
        "lstat($directory)",
        "lstat($path)",
        "(int) $before['nlink'] !== 1",
        "(int) $after['dev'] !== (int) $before['dev']",
        "(int) $after['ino'] !== (int) $before['ino']",
        "hash_file('sha256', $path)",
        "realpath($directory) !== $directory",
        "realpath($path) !== $path",
        "staged_theme_package_matches_capture",
    ):
        assert token in stage
    apply_theme = php[php.index("private function apply_theme_package") :]
    apply_theme = apply_theme[
        : apply_theme.index("private function theme_restore_result")
    ]
    assert "wp_tempnam(" not in apply_theme
    assert apply_theme.index("validate_theme_zip") < apply_theme.index(
        "capture_staged_theme_package"
    )
    assert apply_theme.index(
        "staged_theme_package_matches_capture"
    ) < apply_theme.index("$upgrader->install(")
    mismatch = apply_theme[
        apply_theme.index("if (! $this->staged_theme_package_matches_capture") :
    ]
    mismatch = mismatch[: mismatch.index("try {")]
    assert "THEME_STAGED_PACKAGE_CHANGED" in mismatch
    assert "$upgrader->install(" not in mismatch


def test_theme_extracted_tree_is_bound_at_both_core_mutation_boundaries() -> None:
    php = _php()
    capture = php[php.index("private function capture_extracted_theme_source") :]
    capture = capture[
        : capture.index("private function theme_clear_destination_is_exact")
    ]
    for token in (
        "RecursiveIteratorIterator::SELF_FIRST",
        "FilesystemIterator::SKIP_DOTS",
        "$file_info->isLink()",
        "! isset($expected_directories[$relative])",
        "! $file_info->isFile()",
        "! isset($expected_files[$relative])",
        "(($before['mode'] & 0170000) !== 0040000)",
        "(($before['mode'] & 0170000) !== 0100000)",
        "(int) $before['nlink'] !== 1",
        "hash_file('sha256', $absolute)",
        "(int) $after['dev'] !== (int) $before['dev']",
        "(int) $after['ino'] !== (int) $before['ino']",
        "$files !== $spec['file_manifest']",
        "$directories !== $expected_directories",
        "realpath($source_path) !== $source_real",
        "realpath($remote_path) !== $remote_real",
        "(int) $root_after['dev'] !== (int) $root_before['dev']",
        "(int) $remote_after['dev'] !== (int) $remote_before['dev']",
        "'remote_mode' => (int) $remote_after['mode']",
        "'root_mode' => (int) $root_after['mode']",
    ):
        assert token in capture
    assert "FilesystemIterator::FOLLOW_SYMLINKS" not in capture

    destination = php[php.index("private function theme_clear_destination_is_exact") :]
    destination = destination[
        : destination.index("private function delete_private_theme_stage")
    ]
    for token in (
        "array $theme_root",
        "array('dev', 'ino', 'mode', 'path')",
        "clearstatcache(true, $remote)",
        "realpath($local) === $theme_root['path']",
        "(int) $local_stat['dev'] === $theme_root['dev']",
        "(int) $local_stat['ino'] === $theme_root['ino']",
        "$remote === $theme_root['path'] . DIRECTORY_SEPARATOR . self::THEME_SLUG",
        "! file_exists($remote)",
        "! is_link($remote)",
    ):
        assert token in destination

    hook_context = php[
        php.index("private function theme_upgrader_hook_extra_is_exact") :
    ]
    hook_context = hook_context[
        : hook_context.index("private function capture_extracted_theme_source")
    ]
    for token in (
        "'action',",
        "'raos_operator_theme_apply_marker',",
        "'temp_backup',",
        "'type',",
        "$hook_extra['action'] === 'install'",
        "$hook_extra['type'] === 'theme'",
        "hash_equals(",
        "$hook_extra['temp_backup'] === $backup",
    ):
        assert token in hook_context

    apply_theme = php[php.index("private function apply_theme_package") :]
    apply_theme = apply_theme[
        : apply_theme.index("private function theme_restore_result")
    ]
    for token in (
        "bin2hex(random_bytes(32))",
        "raos_operator_theme_apply_marker",
        "$filter_upgrader !== $upgrader",
        "theme_upgrader_hook_extra_is_exact(",
        "staged_theme_package_matches_capture(",
        "capture_extracted_theme_source(",
        "theme_clear_destination_is_exact(",
        "$recaptured !== $extracted_source_capture",
        "THEME_EXTRACTED_SOURCE_REJECTED",
        "THEME_EXTRACTED_SOURCE_CHANGED_ROLLED_BACK",
        "THEME_UPGRADER_GUARD_BYPASSED_ROLLED_BACK",
    ):
        assert token in apply_theme
    assert (
        "add_filter('upgrader_source_selection', $source_filter, PHP_INT_MAX, 4);"
        in apply_theme
    )
    assert (
        "add_filter('upgrader_clear_destination', $clear_filter, PHP_INT_MAX, 4);"
        in apply_theme
    )
    install = apply_theme.index("$upgrade_result = $upgrader->install(")
    assert apply_theme.index("add_filter('upgrader_source_selection'") < install
    assert apply_theme.index("add_filter('upgrader_clear_destination'") < install
    finally_block = apply_theme[apply_theme.index("} finally {") :]
    assert (
        "remove_filter('upgrader_source_selection', $source_filter, PHP_INT_MAX);"
        in finally_block
    )
    assert (
        "remove_filter('upgrader_clear_destination', $clear_filter, PHP_INT_MAX);"
        in finally_block
    )

    source_filter = apply_theme[apply_theme.index("$source_filter = function (") :]
    source_filter = source_filter[
        : source_filter.index("$clear_destination_count = 0;")
    ]
    assert source_filter.index(
        "staged_theme_package_matches_capture("
    ) < source_filter.index("capture_extracted_theme_source(")
    clear_filter = apply_theme[apply_theme.index("$clear_filter = function (") :]
    clear_filter = clear_filter[
        : clear_filter.index("add_filter('upgrader_package_options'")
    ]
    assert clear_filter.index("theme_clear_destination_is_exact(") < clear_filter.index(
        "$recaptured = $this->capture_extracted_theme_source("
    )
    assert clear_filter.index(
        "$recaptured !== $extracted_source_capture"
    ) < clear_filter.index("$clear_destination_verified = true;")
    assert clear_filter.index(
        "$clear_destination_verified = true;"
    ) < clear_filter.rindex("return true;")


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
