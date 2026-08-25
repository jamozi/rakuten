"""Contract and additive-policy checks for the bounded WordPress operator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1506/self-hosted-wordpress-operator-bridge-v1"


def test_imported_canonical_package_is_not_rewritten() -> None:
    decisions = yaml.safe_load(
        (
            ROOT / "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"
        ).read_bytes()
    )
    records = decisions["decisions"]
    assert [row["id"] for row in records] == [
        f"INT-DEC-{number:03d}" for number in range(1, 16)
    ]
    authority = next(row for row in records if row["id"] == "INT-DEC-013")
    assert authority == {
        "id": "INT-DEC-013",
        "title": "Codexの権限",
        "status": "RESOLVED",
        "decision": (
            "Codexは実装者であり、法務、公開、Production Secret、"
            "Kill Switch解除、最終承認の権限を持たない"
        ),
        "implementation_effect": "PRとHuman Approvalを必須化",
    }

    backlog = yaml.safe_load(
        (
            ROOT / "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"
        ).read_bytes()
    )
    story = next(row for row in backlog["stories"] if row["id"] == "ST-1506")
    assert story["design_refs"] == []
    assert story["deliverables"] == ["production pipeline disabled by default"]
    assert story["acceptance_criteria"] == ["GATE/security/ops approvals required"]
    assert story["test_suites"] == ["TST-032"]
    assert story["open_decisions"] == ["OD-009", "OD-011", "OD-013", "OD-015"]


def test_additive_handoff_preserves_authority_and_production_gates(
    design_handoff: dict[str, Any],
) -> None:
    handoff = design_handoff["DESIGN_HANDOFF_V1"]
    assert handoff["canonical_package_modified"] is False
    decision = handoff["additive_integration_decision"]
    assert decision["id"] == "ST1506-INT-DEC-001"
    assert decision["preserves_int_dec_013"] is True
    assert decision["production_gate_effect"] == "NONE"
    assert "Codex cannot approve itself" in decision["statement"]
    refs = handoff["source_design_refs"]
    assert not any("OD-016" in ref or "INT-DEC-016" in ref for ref in refs)
    assert {
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-009",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-011",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-015",
    }.issubset(refs)
    formal = handoff["formal_evidence_status"]
    assert formal == {
        "ST_1506": "NOT_STARTED",
        "TST_001": "NOT_EXECUTED",
        "TST_012": "NOT_EXECUTED",
        "TST_026": "NOT_EXECUTED",
        "TST_032": "NOT_EXECUTED",
        "live_wordpress": "NOT_EXECUTED",
        "staging": "NOT_CONFIGURED",
        "production": "NOT_READY",
    }


def test_route_operation_and_capability_inventories_are_closed(
    operator_contract: dict[str, Any],
) -> None:
    assert operator_contract["site"] == {
        "origin": "https://kurashinoshirube.com",
        "runtime_origin_validation": [
            "is_ssl_is_true",
            "normalized_home_url_equals_origin",
            "normalized_site_url_equals_origin",
        ],
        "wordpress_rest_prefix": "/wp-json",
        "namespace": "raos-operator/v1",
        "plugin_slug": "raos-bounded-operator",
        "plugin_version": "1.0.0",
        "operator_contract_version": 1,
        "profile_version": 1,
        "executor_role": "raos_operator_executor",
    }
    assert [(row["method"], row["path"]) for row in operator_contract["routes"]] == [
        ("GET", "/wp-json/raos-operator/v1/status"),
        ("POST", "/wp-json/raos-operator/v1/yoast-checksum"),
        ("POST", "/wp-json/raos-operator/v1/proposals"),
        (
            "POST",
            "/wp-json/raos-operator/v1/proposals/{proposal_id}/apply",
        ),
    ]
    assert [row["operator_state_write"] for row in operator_contract["routes"]] == [
        False,
        False,
        True,
        True,
    ]
    assert [
        row["wordpress_target_mutation"] for row in operator_contract["routes"]
    ] == [False, False, False, True]
    assert operator_contract["routes"][2]["host_write_constant_required"] is True
    assert operator_contract["routes"][3]["host_write_constant_required"] is True
    assert operator_contract["approval_rest_route"] == "ABSENT"
    assert operator_contract["capabilities"]["executor_exact"] == [
        "read",
        "raos_operator_read",
        "raos_operator_propose",
        "raos_operator_apply",
    ]
    assert operator_contract["capabilities"]["executor_can_manage_options"] is False
    assert operator_contract["capabilities"]["executor_can_publish_posts"] is False
    assert operator_contract["authentication"]["operator_identity_binding"] == {
        "option_name": "raos_operator_bound_user_id_v1",
        "value": "CANONICAL_POSITIVE_WORDPRESS_USER_ID",
        "autoload": False,
        "bootstrap": (
            "ATOMIC_ADD_OPTION_ON_FIRST_VALID_APPLICATION_PASSWORD_FOR_EXACT_"
            "SINGLE_ROLE_EXECUTOR"
        ),
        "network_user_meta_name": "raos_operator_network_identity_v1",
        "network_user_meta_value": ("FIXED_SITE_ORIGIN_AND_CANONICAL_POSITIVE_USER_ID"),
        "network_scope": "GLOBAL_WORDPRESS_USER_IDENTITY_QUARANTINE",
        "network_bootstrap": (
            "ATOMIC_ADD_UNIQUE_USER_META_UNDER_ZERO_WAIT_DATABASE_MUTEX"
        ),
        "existing_binding_promotion": ("PLUGINS_LOADED_BEFORE_OPERATOR_AUTHENTICATION"),
        "overwrite_or_reconcile": "FORBIDDEN",
        "runtime_delete": "FORBIDDEN",
        "deactivation_or_uninstall_delete": "FORBIDDEN",
        "invalid_or_conflicting_binding": (
            "REFUSE_AND_REQUIRE_OWNER_DB_RECOVERY_OUTSIDE_BRIDGE"
        ),
        "operator_command": "ABSENT",
    }
    assert operator_contract["authentication"]["application_password_surface"] == {
        "authentication_hook": "wp_authenticate_application_password_errors",
        "rest_firewall_hook": "rest_request_before_callbacks",
        "xmlrpc_or_non_rest": "REFUSE_AUTHENTICATION",
        "multisite": "UNSUPPORTED_AND_MARKED_OPERATOR_REFUSED_ON_EVERY_SUBSITE",
        "unrelated_application_password_users": "UNAFFECTED",
        "exact_rest_handlers": {
            "GET /raos-operator/v1/status": "rest_status",
            "POST /raos-operator/v1/yoast-checksum": "rest_yoast_checksum",
            "POST /raos-operator/v1/proposals": "rest_create_proposal",
            ("POST /raos-operator/v1/proposals/{64_lowercase_hex}/apply"): "rest_apply",
        },
        "callback_binding": "EXACT_PLUGIN_INSTANCE_AND_METHOD",
        "all_other_rest_handlers": "REFUSE_403_BEFORE_CALLBACK",
    }
    assert operator_contract["authentication"]["executor_request_time_validation"] == {
        "bound_user_id": "EXACT_CURRENT_APPLICATION_PASSWORD_USER",
        "user_role_list": "EXACTLY_RAOS_OPERATOR_EXECUTOR",
        "role_capability_map": "EXACTLY_EXECUTOR_CAPABILITIES_ALL_TRUE",
        "user_direct_capability_grants": "ABSENT",
        "multisite": "FORBIDDEN",
        "drift": "REFUSE",
    }
    assert operator_contract["authentication"]["credential_owner_identity"] == (
        "CAPTURE_OS_GETEUID_ONCE_AT_STORE_CONSTRUCTION"
    )
    assert operator_contract["transport_environment"] == {
        "implementation": "PYTHON_STDLIB_HTTP_CLIENT_DIRECT_TLS",
        "http_debug_logging": (
            "FORCE_AND_VERIFY_INSTANCE_DEBUGLEVEL_ZERO_BEFORE_EVERY_SECRET_REQUEST"
        ),
        "proxy_variables": [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
        ],
        "proxy_variable_effect": "ACCEPTED_BUT_INERT_AND_NOT_CONSUMED",
        "refused_nonempty_tls_variables": [
            "SSL_CERT_DIR",
            "SSL_CERT_FILE",
            "SSLKEYLOGFILE",
        ],
        "refusal": "TRANSPORT_REFUSED_BEFORE_CREDENTIAL_OR_NETWORK_USE",
    }

    commands = operator_contract["closed_commands"]
    assert set(commands) == {
        "status",
        "verify-yoast-checksums",
        "propose-yoast-profile",
        "apply-yoast-profile",
        "propose-theme-update",
        "apply-theme-update",
        "caller_request_token",
        "caller_package_path",
    }
    assert commands["caller_request_token"] == "FORBIDDEN"
    assert commands["caller_package_path"] == "FORBIDDEN"
    assert commands["apply-theme-update"]["caller_inputs"] == ["proposal_id"]
    assert operator_contract["operational_launcher"] == {
        "path": "scripts/st1506_wordpress_operator_python.sh",
        "mode": "0755",
        "fixed_repository_root": "/home/minami/rakuten",
        "shell": "EXACT_USR_BIN_BUSYBOX",
        "environment": (
            "ENV_I_FIXED_PATH_LOCALE_AND_TIMEZONE_ONLY_PLUS_STAGE_BINDINGS"
        ),
        "python": "EXACT_OWNER_MANAGED_CPYTHON_3_14_6",
        "flags": ["-B", "-I", "-S", "-X_pycache_prefix=/dev/null"],
        "cli_source": "EXACT_CURRENT_HEAD_BLOB_OVER_FIFO_STDIN",
        "accepted_argv": "EXACT_CLOSED_COMMAND_INVENTORY_AND_PROPOSAL_ID_SHAPES",
        "stage_zero": {
            "direct_script_or_imported_main": (
                "REFUSE_69_BEFORE_CREDENTIAL_OR_NETWORK_USE"
            ),
            "root_head_and_working_bytes": ("EXACT_FOR_EVERY_DECLARED_RUNTIME_PATH"),
            "runtime_module_load": (
                "CLOSED_IN_MEMORY_LOADER_FROM_CAPTURED_COMMITTED_BYTES"
            ),
            "verified_mode_repository_sys_path": "ABSENT",
            "python_flags_environment_executable_and_prefix": "EXACT",
            "preloaded_raos_site_sitecustomize_or_usercustomize": "FORBIDDEN",
            "head_drift_during_verification": "REFUSE",
        },
    }


def test_proposal_identity_and_independent_approval_are_fail_closed(
    operator_contract: dict[str, Any],
) -> None:
    proposal = operator_contract["proposal"]
    assert proposal["ttl_seconds"] == 900
    assert proposal["request_token"] == {
        "pattern": "^[0-9a-f]{64}$",
        "purpose": ("one caller intent per proposal without reusing a terminal record"),
        "generation": "INTERNAL_OS_CSPRNG_32_BYTES",
        "caller_supplied": False,
    }
    assert proposal["proposal_id"] == {
        "expression": "lower_hex(sha256(canonical_validated_request_bytes))",
        "pattern": "^[0-9a-f]{64}$",
        "public_proposal_hash_field": "ABSENT",
        "etag": "SAME_VALUE",
    }
    apply_route = operator_contract["routes"][-1]
    assert apply_route["required_header"] == {
        "If-Match": "QUOTED_PROPOSAL_ID",
        "Idempotency-Key": "UNQUOTED_PROPOSAL_ID",
    }
    approval = operator_contract["independent_human_approval"]
    assert approval["creation_channel"] == "WP_ADMIN_TOOLS_PAGE_AND_ADMIN_POST_ONLY"
    assert approval["rest_creation"] == "FORBIDDEN"
    assert approval["transition"] == "COMPARE_AND_SWAP_PROPOSED_TO_APPROVED"
    assert approval["required"] == [
        "cookie_authenticated_session",
        "manage_options",
        "proposal_specific_wp_nonce",
        "current_password_reauthentication",
        "approval_reason_10_to_300_characters",
        "exact_final_12_hex_characters_of_proposal_id",
        "approver_user_id_differs_from_proposer_user_id",
        "proposal_not_expired",
    ]
    assert approval["password_persistence"] == "FORBIDDEN"
    assert approval["approval_evidence_hash"] == {
        "material": [
            "proposal_id",
            "approved_by_user_id",
            "approved_at",
            "approval_expires_at",
            "normalized_reason",
        ],
        "storage": "REQUIRED",
        "verification_at_apply": "REQUIRED",
    }
    assert approval["review_ui_must_show"] == [
        "operation",
        "exact_target",
        "exact_impact",
        "proposal_id",
        "before_state_hash",
        "expires_at",
    ]
    assert approval["audit_insert_failure"] == (
        "REFUSE_APPROVAL_WITHOUT_STATE_TRANSITION"
    )


def test_write_ahead_intent_and_create_receipt_recovery_are_closed(
    operator_contract: dict[str, Any],
) -> None:
    assert operator_contract["argv_parser"] == {
        "parser": "ARGPARSE_EXACT_SUBCOMMAND_PARSE_ARGS",
        "abbreviation": "FORBIDDEN",
        "response_file_expansion": "FORBIDDEN",
        "shell_or_eval_expansion": "FORBIDDEN",
        "unknown_argument": "REFUSE_BEFORE_TRANSPORT",
        "apply_proposal_id": (
            "EXACT_64_LOWERCASE_HEX_BEFORE_CREDENTIAL_OR_TRANSPORT_USE"
        ),
    }
    assert operator_contract["proposal_intent_journal"] == {
        "directory": ".secrets/wordpress-operator-local/proposal-intents",
        "per_operation_schema": "RAOS_WORDPRESS_OPERATOR_PROPOSAL_INTENT_V1",
        "files": {
            "APPLY_YOAST_PROFILE": "apply-yoast-profile.intent.v1.json",
            "UPDATE_CHILD_THEME": "update-child-theme.intent.v1.json",
        },
        "lock_files": {
            "APPLY_YOAST_PROFILE": "apply-yoast-profile.lock",
            "UPDATE_CHILD_THEME": "update-child-theme.lock",
        },
        "ownership": "CURRENT_EFFECTIVE_USER",
        "owner_identity_capture": ("CAPTURE_OS_GETEUID_ONCE_AT_JOURNAL_CONSTRUCTION"),
        "directory_mode": "0700",
        "file_mode": "0600",
        "regular_single_link_no_symlink": "REQUIRED",
        "entries": {
            "key": "operation",
            "allowed_operations": [
                "APPLY_YOAST_PROFILE",
                "UPDATE_CHILD_THEME",
            ],
            "maximum_total": 2,
            "maximum_unresolved_per_operation": 1,
            "exact_fields": [
                "canonical_request_sha256",
                "operation",
                "proposal_id",
                "request_token",
                "schema",
            ],
            "proposal_id_semantics": "CANONICAL_REQUEST_SHA256",
            "canonical_request_sha256": "MUST_EQUAL_PROPOSAL_ID",
        },
        "write_ahead": (
            "EXCLUSIVE_CREATE_FULL_WRITE_FILE_FSYNC_ATOMIC_HARDLINK_PUBLICATION_"
            "AND_DIRECTORY_FSYNC_BEFORE_FIRST_CREATE_TRANSPORT_ATTEMPT"
        ),
        "same_operation_retry": (
            "REUSE_EXACT_UNRESOLVED_REQUEST_TOKEN_AND_PROPOSAL_ID"
        ),
        "current_input_drift": "REFUSE_AND_RETAIN_EXISTING_INTENT",
        "transport_or_response_failure": "RETAIN_UNCHANGED",
        "clear_conditions": {
            "create": (
                "VALIDATED_MATCHING_CREATE_RECEIPT_INCLUDING_EXPIRED_EXACT_REPLAY"
            ),
            "apply": (
                "VALIDATED_APPLIED_RECEIPT_WITH_MATCHING_OPERATION_AND_PROPOSAL_ID"
            ),
        },
        "apply_clear_matching_semantics": {
            "absent_intent": "NO_OP",
            "different_proposal_id": "RETAIN_UNCHANGED_NO_ERROR",
            "matching_proposal_id": "CLEAR",
            "ambiguous_or_non_success_apply": "RETAIN_UNCHANGED",
        },
        "clear_write": "LOCKED_UNLINK_AND_DIRECTORY_FSYNC",
        "automatic_timeout_or_error_clear": "FORBIDDEN",
        "credential_or_application_password_storage": "FORBIDDEN",
    }
    assert operator_contract["proposal_create_receipt"] == {
        "exact_schema": "RAOS_OPERATOR_PROPOSAL_V1",
        "proposal_id": "EXACT_REQUEST_PROPOSAL_ID",
        "operation": "EXACT_REQUEST_OPERATION",
        "state_closed_values": ["PROPOSED", "APPROVED", "APPLYING"],
        "created_at_and_expires_at": "STRICT_UTC_RFC3339",
        "ttl_seconds_exact": 900,
        "replayed": "BOOLEAN",
        "etag": "QUOTED_PROPOSAL_ID",
        "invalid_receipt_effect": "REFUSE_AND_RETAIN_WRITE_AHEAD_INTENT",
        "malformed_post_write_effect": (
            "OUTCOME_AMBIGUOUS_AND_RETAIN_WRITE_AHEAD_INTENT"
        ),
        "initial_receipt_rules": {
            "replayed": False,
            "state": "PROPOSED",
            "expires_at_must_be_future_at_validation": True,
        },
        "replay_receipt_rules": {
            "replayed": True,
            "states": ["PROPOSED", "APPROVED", "APPLYING"],
            "expired_exact_receipt": {
                "journal": "CLEAR_AS_COMMUNICATION_OUTCOME_RESOLVED",
                "command_result": "NON_SUCCESS_NEW_PROPOSAL_REQUIRED",
            },
        },
        "next_action_by_state": {
            "PROPOSED": "HUMAN_APPROVAL_REQUIRED_BEFORE_MATCHING_APPLY_COMMAND",
            "APPROVED": "RUN_MATCHING_APPLY_COMMAND",
            "APPLYING": "VERIFY_STATUS_BEFORE_ANY_RETRY",
            "expired_exact_replay": "NEW_PROPOSAL_REQUIRED",
        },
        "approval_surface_by_state": {
            "live_PROPOSED": "WORDPRESS_ADMIN_TOOLS_ONLY",
            "APPROVED_APPLYING_or_expired": "NOT_APPLICABLE",
        },
    }
    assert operator_contract["apply_receipt"] == {
        "exact_schema": "RAOS_OPERATOR_APPLY_V1",
        "proposal_id": "EXACT_REQUEST_PROPOSAL_ID",
        "operation": "EXACT_REQUEST_OPERATION",
        "state": "APPLIED",
        "replayed": "BOOLEAN",
        "result_code_by_operation": {
            "APPLY_YOAST_PROFILE": "YOAST_PROFILE_APPLIED",
            "UPDATE_CHILD_THEME": "THEME_UPDATE_APPLIED",
        },
        "malformed_or_cross_operation_post_write_effect": (
            "OUTCOME_AMBIGUOUS_AND_RETAIN_MATCHING_INTENT"
        ),
    }


def test_canonical_golden_vector_is_exact_and_hash_bound(
    operator_contract: dict[str, Any],
) -> None:
    path = SLICE / "contracts/canonical-proposal-golden.v1.json"
    vector = json.loads(path.read_bytes())
    canonical = vector["canonical_ascii_json"].encode("ascii", errors="strict")
    assert set(vector) == {
        "canonical_ascii_json",
        "canonical_byte_length",
        "proposal_id",
        "request_token",
        "schema",
    }
    assert vector["schema"] == "RAOS_WORDPRESS_OPERATOR_CANONICAL_GOLDEN_V1"
    assert len(canonical) == vector["canonical_byte_length"] == 870
    assert hashlib.sha256(canonical).hexdigest() == vector["proposal_id"]
    assert vector["proposal_id"] == (
        "699a1c5a40786449e3f0241958a594f436e03504472a592d2abc1e3eae2b7d90"
    )
    assert (
        json.dumps(
            json.loads(canonical),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        == canonical
    )
    assert operator_contract["proposal"]["canonical_golden_vector"] == {
        "fixture": (
            "changes/st-1506/self-hosted-wordpress-operator-bridge-v1/contracts/"
            "canonical-proposal-golden.v1.json"
        ),
        "request_token": vector["request_token"],
        "canonical_byte_length": 870,
        "proposal_id": vector["proposal_id"],
        "python_verification": "REQUIRED",
        "php_runtime_self_check_before_proposal_create": "REQUIRED",
    }


def test_status_is_bounded_and_exposes_no_generic_inventory(
    operator_contract: dict[str, Any],
) -> None:
    status = operator_contract["status_response"]
    assert status["exact_keys"] == [
        "schema",
        "operator_version",
        "writes_enabled",
        "supported_operations",
        "yoast_profile_code",
        "theme",
        "proposal_counts",
    ]
    assert status["yoast_profile_code_closed_values"] == [
        "YOAST_VERSION_ABSENT",
        "YOAST_VERSION_MISMATCH",
        "YOAST_PROFILE_PREREQUISITE_FAILED",
        "YOAST_PROFILE_MATCH",
        "YOAST_PROFILE_MISMATCH",
    ]
    assert status["theme"] == {
        "exact_keys": [
            "slug",
            "installed_version",
            "active",
            "state_code",
            "file_count",
            "tree_sha256",
        ],
        "slug": "kurashinoshirube-child",
        "installed_version": ("STRICT_SEMVER_OR_NULL_ONLY_WHEN_ABSENT_OR_UNREADABLE"),
        "active": "BOOLEAN",
        "state_code_closed_values": [
            "THEME_ABSENT",
            "THEME_TREE_UNREADABLE",
            "THEME_TREE_READABLE",
        ],
        "file_count": "INTEGER_0_TO_64",
        "tree_sha256": ("LOWERCASE_SHA256_OR_NULL_ONLY_WHEN_ABSENT_OR_UNREADABLE"),
        "tree_hash_material": "CANONICAL_SORTED_PATH_SIZE_SHA256_MANIFEST",
        "tree_read_limits": {
            "file_count_maximum": 64,
            "file_bytes_maximum": 4194304,
        },
    }
    assert status["generic_site_health"] == "ABSENT"
    assert status["generic_plugin_or_theme_inventory"] == "ABSENT"


def test_yoast_profile_is_exact_merge_only_and_rollback_complete(
    operator_contract: dict[str, Any],
) -> None:
    request = operator_contract["operation_requests"]["APPLY_YOAST_PROFILE"]
    exact = request["exact_request"]
    assert exact["operation"] == "APPLY_YOAST_PROFILE"
    assert exact["operator_contract_version"] == 1
    assert exact["profile_version"] == 1
    assert exact["site_origin"] == "https://kurashinoshirube.com"
    assert exact["ttl_seconds"] == 900
    assert exact["request_token"] == "LOWERCASE_SHA256_TOKEN"
    assert exact["yoast_profile"] == {
        "plugin_slug": "wordpress-seo",
        "version": "28.3",
        "wpseo": {
            "enable_ai_generator": False,
            "enable_headless_rest_endpoints": False,
            "enable_index_now": False,
            "enable_schema": False,
            "enable_schema_aggregation_endpoint": False,
            "enable_xml_sitemap": True,
            "google_site_kit_feature_enabled": False,
            "googleverify": "",
            "semrush_integration_active": False,
            "tracking": False,
            "wincher_integration_active": False,
        },
        "wpseo_social": {
            "og_default_image": (
                "https://kurashinoshirube.com/wp-content/themes/"
                "kurashinoshirube-child/assets/images/home-hero.webp"
            ),
            "og_default_image_id": "",
            "opengraph": True,
            "twitter": True,
            "twitter_card_type": "summary_large_image",
        },
    }
    assert request["write_algorithm"] == "MERGE_ALLOWLISTED_KEYS_ONLY"
    assert request["applied_profile_source"] == (
        "STORED_APPROVED_REQUEST_JSON_YOAST_PROFILE"
    )
    assert request["prewrite_revalidation"] == [
        "stored_profile_equals_fixed_contract_profile",
        "stored_profile_equals_runtime_derived_prerequisite_profile",
    ]
    assert request["runtime_derived_profile_write_source"] == "FORBIDDEN"
    assert request["whole_option_replacement"] == "FORBIDDEN"
    assert request["storage_engine_precondition"] == {
        "table": "EXACT_WPDB_OPTIONS_TABLE",
        "engine": "EXACT_STRING_InnoDB",
        "verification": "READ_ONLY_INFORMATION_SCHEMA_TABLES_QUERY",
        "schema_binding": "BYTE_EXACT_BINARY_TABLE_SCHEMA_EQUALS_DATABASE",
        "table_binding": ("BYTE_EXACT_BINARY_TABLE_NAME_EQUALS_EXACT_WPDB_OPTIONS"),
        "result_cardinality": "EXACTLY_ONE_ROW_WITHOUT_LIMIT",
        "timing": ["before_capture", "before_apply"],
        "missing_multiple_unknown_or_non_innodb": "REFUSE_WITHOUT_OPTION_WRITE",
        "capture_error": "raos_yoast_option_table_engine_unsupported_HTTP_409",
        "apply_result": "YOAST_OPTION_TABLE_ENGINE_UNSUPPORTED_FAILED",
    }
    assert request["preserved_state"] == (
        "EVERY_NON_PROFILE_KEY_AND_VALUE_IN_BOTH_OPTION_ARRAYS"
    )
    assert request["transaction_model"] == {
        "start": "BEFORE_READING_TARGET_ROWS",
        "locked_rows": "EXACTLY_WPSEO_AND_WPSEO_SOCIAL_SELECT_FOR_UPDATE",
        "captured_row_material": [
            "exact_serialized_option_value",
            "exact_autoload_value",
        ],
        "before_state_hash": "SHA256_LENGTH_DELIMITED_RAW_ROW_MATERIAL",
        "writes": (
            "CONDITIONAL_BYTE_EXACT_BINARY_RAW_ROW_CAS_MATCHING_OPTION_NAME_"
            "VALUE_AND_AUTOLOAD"
        ),
        "locked_readback": "EXACT_BOTH_ROWS_BEFORE_COMMIT",
        "cache_flush": "AFTER_COMMIT_OR_ROLLBACK",
        "post_commit_readback": ("EXACT_ROWS_PROFILE_AND_NON_PROFILE_PRESERVATION"),
    }
    assert request["rollback"] == (
        "DATABASE_TRANSACTION_ROLLBACK_WITH_EXACT_CAPTURED_RAW_ROW_VERIFICATION"
    )
    assert request["stale_update_option_restore"] == "FORBIDDEN"
    assert request["uncertain_outcomes"] == {
        "commit": "YOAST_COMMIT_UNCERTAIN_NEEDS_RECOVERY",
        "rollback": "YOAST_TRANSACTION_ROLLBACK_UNCERTAIN_NEEDS_RECOVERY",
        "post_commit": "YOAST_POST_COMMIT_DRIFT_NEEDS_RECOVERY",
    }


def test_theme_update_is_source_derived_upgrade_only(
    operator_contract: dict[str, Any],
) -> None:
    request = operator_contract["operation_requests"]["UPDATE_CHILD_THEME"]
    theme = request["exact_request"]["theme"]
    assert theme["slug"] == "kurashinoshirube-child"
    assert theme["from_version"] == "1.1.1"
    assert theme["to_version"] == "STRICT_SEMVER_GREATER_THAN_FROM_VERSION"
    assert request["apply_payload"] == "EXACT_BOUND_THEME_ARCHIVE_BYTES"
    assert request["content_type"] == "application/zip"
    assert request["package_source"] == {
        "builder": "scripts/build_st1704_self_hosted_theme.py",
        "manifest_builder": ("scripts/build_st1704_self_hosted_editorial_manifest.py"),
        "runtime_manifest": (
            "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"
        ),
        "runtime_manifest_verification": (
            "TRACKED_BYTES_EQUAL_DETERMINISTIC_REBUILD_BEFORE_PROPOSE_AND_APPLY"
        ),
        "committed_manifest_verification": (
            "CURRENT_HEAD_BLOB_EQUALS_TRACKED_AND_REBUILT_BYTES"
        ),
        "stage_captured_entry_binding": (
            "EVERY_ARCHIVE_ENTRY_SIZE_AND_SHA256_EQUAL_CAPTURED_MANIFEST"
        ),
        "post_build_revalidation": (
            "CAPTURED_MANIFEST_AND_SOURCE_SET_RECHECKED_BEFORE_PROPOSAL"
        ),
        "git_reader": (
            "FIXED_READ_ONLY_USR_BIN_GIT_PLUMBING_NO_SHELL_CLEAN_ENV_TIMEOUT_AND_"
            "SIZE_BOUNDED"
        ),
        "caller_selected_path": "FORBIDDEN",
        "rebuild_before_propose_and_apply": "REQUIRED",
    }
    assert request["limits"] == {
        "package_bytes_maximum": 16777216,
        "total_uncompressed_bytes_maximum": 67108864,
        "file_bytes_maximum": 4194304,
        "file_count_maximum": 64,
        "manifest_paths": "ASCII_SAFE_RELATIVE_POSIX_CASEFOLD_UNIQUE_SORTED",
        "zip_compression": "ZIP_STORED_ONLY",
        "zip_encryption": "FORBIDDEN",
    }
    assert request["before_state"] == (
        "CAPTURE_EXACT_ACTIVE_CHILD_THEME_DIRECTORY_HASH_AND_FILE_MANIFEST"
    )
    assert request["recovery_backup"] == {
        "filesystem": "WP_FILESYSTEM_DIRECT_ONLY",
        "preexisting_backup": "REFUSE_BEFORE_UPDATE",
        "symlinks": "FORBIDDEN",
        "verification": (
            "BACKUP_TREE_MUST_EXACTLY_MATCH_CAPTURED_BEFORE_MANIFEST_BEFORE_RESTORE"
        ),
        "restore_without_verified_backup": "FORBIDDEN",
        "cleanup_start_is_irreversible_boundary": True,
        "restore_after_cleanup_started": "FORBIDDEN",
        "cleanup_failure": "KEEP_AND_VERIFY_NEW_THEME_THEN_NEEDS_RECOVERY",
    }
    assert request["rollback"] == (
        "RESTORE_ONLY_FROM_VERIFIED_COMPLETE_BACKUP_ON_UPDATE_OR_READBACK_FAILURE"
    )


def test_checksum_and_proposal_resource_bounds_are_exact(
    operator_contract: dict[str, Any],
) -> None:
    checksum = operator_contract["yoast_checksum"]
    assert checksum["official_manifest_url"] == (
        "https://downloads.wordpress.org/plugin-checksums/wordpress-seo/28.3.json"
    )
    assert checksum["expected_manifest_bytes"] == 343370
    assert checksum["expected_manifest_sha256"] == (
        "1773aaadf88827311b488877c069aefcb6422e8dc6d5a7f50c1bd492d34bf85f"
    )
    assert checksum["expected_sha256_file_count"] == 1952
    assert checksum["cache"] == {
        "ttl_seconds": 300,
        "fresh_computations_per_cache_miss": 1,
        "cache_miss_lock": "REQUIRED",
        "unknown_or_corrupt_cache": "UNAVAILABLE_NEVER_PASS",
    }
    assert operator_contract["proposal"]["storage_bounds"] == {
        "nonterminal_unexpired_per_proposer_maximum": 20,
        "creations_per_proposer_per_rolling_window_maximum": 5,
        "rolling_window_seconds": 600,
        "total_rows_maximum": 1000,
        "caller_selected_limits": "FORBIDDEN",
        "automatic_deletion": "FORBIDDEN",
    }
    preconditions = operator_contract["apply_preconditions"]
    assert "REQUEST_JSON_REHASH_EQUALS_PROPOSAL_ID" in preconditions
    assert "BEFORE_STATE_HASH_UNCHANGED" in preconditions
    assert "APPROVER_DIFFERS_FROM_PROPOSER" in preconditions
    assert operator_contract["apply_serialization"] == {
        "scope": "ONE_GLOBAL_MUTEX_PER_DB_PREFIX_AND_SITE_ORIGIN_FOR_BOTH_OPERATIONS",
        "name": (
            "raos_apply_v1_PLUS_FIRST_48_HEX_OF_SHA256_DB_NAME_NEWLINE_PREFIX_"
            "NEWLINE_SITE_ORIGIN"
        ),
        "acquire": "SELECT_GET_LOCK_WITH_ZERO_SECOND_WAIT",
        "unavailable": "REFUSE_409_BEFORE_TARGET_MUTATION",
        "held_across": [
            "locked_proposal_revalidation",
            "before_state_recheck",
            "target_mutation",
            "readback_or_recovery",
            "terminal_state_and_audit_persistence",
        ],
        "ownership_checks": [
            "before_before_state_capture",
            "after_applying_cas_commit_immediately_before_target_mutation",
            "after_target_mutation_before_terminal_persistence",
        ],
        "ownership_query": "SELECT_IS_USED_LOCK_EQUALS_CONNECTION_ID",
        "ownership_loss": (
            "PRE_APPLYING_REFUSE_OR_APPLYING_NEEDS_RECOVERY_WITHOUT_SUCCESS"
        ),
        "release": "FINALLY_SELECT_RELEASE_LOCK_AND_VERIFY_EXACT_SUCCESS",
        "release_uncertain": "REFUSE_500_WITHOUT_REPORTING_SUCCESS",
    }
    assert operator_contract["audit"]["insert_failure"] == (
        "FAIL_CLOSED_AND_NEVER_AUTHORIZE_OR_REPORT_SUCCESS"
    )


def test_forbidden_surfaces_and_evidence_are_explicit(
    operator_contract: dict[str, Any],
) -> None:
    assert set(operator_contract["forbidden_surfaces"]) == {
        "post_content",
        "post_status",
        "publication",
        "scheduling",
        "taxonomy",
        "media",
        "plugin_install",
        "plugin_activate",
        "plugin_update",
        "plugin_delete",
        "generic_or_runtime_user_or_role_mutation",
        "arbitrary_option",
        "arbitrary_meta",
        "generic_wordpress_rest",
        "caller_selected_url",
        "arbitrary_http",
        "arbitrary_php",
        "arbitrary_sql",
        "arbitrary_shell_or_process",
        "delete_or_irreversible_data_operation",
        "codex_self_approval",
    }
    assert operator_contract["evidence_boundary"] == {
        "local_contract_and_tests": "LOCAL_IMPLEMENTATION_EVIDENCE_ONLY",
        "live_wordpress": "NOT_EXECUTED",
        "TST_032": "NOT_EXECUTED",
        "staging": "NOT_CONFIGURED",
        "release": "NOT_AUTHORIZED",
        "production_readiness": "NOT_READY",
    }


def test_runbook_and_makefile_expose_no_live_or_unbounded_shortcut() -> None:
    runbook = (SLICE / "OPERATIONS_RUNBOOK.md").read_text(encoding="utf-8")
    for required in (
        "RAOS_OPERATOR_WRITES_ENABLED",
        "proposal-specific WordPress nonce",
        "current WordPress password",
        "final 12 hexadecimal characters",
        'If-Match: "<proposal_id>"',
        "Idempotency-Key",
        "Do not delete database rows",
        "Publication and post mutation are",
        "not commands in this slice",
        ".secrets/wordpress-operator-local/proposal-intents/",
        "NEW_PROPOSAL_REQUIRED",
        "scripts/build_st1704_self_hosted_editorial_manifest.py",
        "canonical_request_sha256",
        "atomic hard link",
        "SSL_CERT_FILE",
    ):
        assert required in runbook
    assert "whole-option replacement" in runbook.lower()
    assert "forbidden" in runbook.lower()
    assert "--request-token" not in runbook
    assert "--package" not in runbook

    makefile = (SLICE / "Makefile").read_text(encoding="utf-8")
    assert "No target performs a live WordPress request" in makefile
    assert "publish" not in makefile.lower()
    assert "curl" not in makefile.lower()
