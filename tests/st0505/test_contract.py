"""Closed source and live-smoke reference assertions for ST-0505."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import build_st0505_rakuten_live_smoke_reference_plan as generator


EXPECTED_PREDECESSOR_URIS = (
    "repo://changes/st-0502/README.md",
    "repo://python/raos/domain/catalog/rakuten_item_search.py",
    "repo://python/raos/ports/rakuten_item_search.py",
    "repo://python/raos/application/catalog/rakuten_item_search.py",
    "repo://python/raos/adapters/recorded_rakuten_item_search.py",
    "repo://tests/st0502/conftest.py",
    "repo://tests/st0502/test_boundaries.py",
    "repo://tests/st0502/test_failure_isolation.py",
    "repo://tests/st0502/test_rakuten_item_search.py",
    "repo://python/raos/domain/catalog/rakuten_item_search_live_request_v1.py",
    "repo://tests/st0502/test_rakuten_item_search_live_request_v1.py",
)


def _plan() -> dict[str, Any]:
    return generator.reference_plan(generator.load_contract())


def test_plan_has_exact_sections_and_installable_disabled_document() -> None:
    plan = _plan()
    assert tuple(plan) == generator.PLAN_KEYS
    assert plan["document"] == generator.EXPECTED_DOCUMENT
    assert plan["document"]["version"] == "3.0.0"
    assert plan["document"]["executable"] is True
    assert plan["document"]["interface_only"] is False
    assert plan["document"]["decision"] == "EXACT_OWNER_INSTALLED_ENTRY_REQUIRED"
    assert plan["document"]["story_acceptance"] is False
    assert plan["document"]["production_eligible"] is False
    assert plan["document"]["approval"] is None


def test_predecessor_binds_commit_artifacts_and_recorded_only_semantics() -> None:
    predecessor = _plan()["predecessor_binding"]
    assert predecessor["story_id"] == "ST-0502"
    assert predecessor["commit"] == generator.PREDECESSOR_COMMIT
    assert predecessor["artifacts"] == generator._expected_predecessor_artifacts()
    assert tuple(row["uri"] for row in predecessor["artifacts"]) == (
        EXPECTED_PREDECESSOR_URIS
    )
    assert len(predecessor["artifacts"]) == 11
    assert predecessor["semantics"] == generator.EXPECTED_PREDECESSOR_SEMANTICS
    semantics = predecessor["semantics"]
    assert semantics["purpose"] == "CONTRACT_TEST"
    assert semantics["mode"] == "RECORDED_TEST_ONLY"
    assert semantics["live_eligible"] is False
    assert semantics["health"] == "NOT_EXECUTED"
    assert semantics["requested_page"] == 1
    assert semantics["page_fetch_count"] == 1
    assert type(semantics["retry_count"]) is int
    assert semantics["retry_count"] == 0
    assert type(semantics["pagination_count"]) is int
    assert semantics["pagination_count"] == 0
    assert semantics["storage"] == "NOT_EXECUTED"
    assert semantics["persistence"] == "NOT_EXECUTED"
    assert semantics["receipt_uri"] is None


def test_predecessor_binds_exact_non_executable_live_request_policy() -> None:
    policy = _plan()["predecessor_binding"]["semantics"]["live_request_policy"]

    assert policy == generator.EXPECTED_LIVE_REQUEST_POLICY_SEMANTICS
    assert policy == {
        "policy_name": "RakutenItemSearchLiveRequestV1",
        "policy_version": "V1",
        "provider_api_version": "2026-07-01",
        "non_executable": True,
        "requested_page": 1,
        "hits_minimum": 1,
        "hits_maximum": 30,
        "retry_limit": 0,
        "pagination_followup_limit": 0,
        "review_derived_request_inputs": "EXCLUDED",
        "affiliate_rate_request_inputs": "EXCLUDED",
        "provider_text_trust": "UNTRUSTED_DATA",
    }


def test_predecessor_selects_no_live_endpoint_account_or_capability() -> None:
    semantics = _plan()["predecessor_binding"]["semantics"]
    assert semantics["endpoint_url"] is None
    assert semantics["account"] is None
    assert semantics["credential_access"] == "FORBIDDEN"
    assert semantics["network_access"] == "FORBIDDEN"
    assert semantics["provider_sdk"] == "ABSENT"
    assert semantics["filesystem"] == "ABSENT"
    assert semantics["repository"] == "ABSENT"
    assert semantics["external_actions"] == []


def test_od_015_stays_blocking_unresolved_and_recorded_only() -> None:
    decision = _plan()["open_decision"]
    assert decision == generator.EXPECTED_OPEN_DECISION
    assert decision["status"] == "EXTERNAL_EVIDENCE_REQUIRED"
    assert decision["blocking"] is True
    assert decision["resolved"] is False
    assert decision["safe_default"] == "RECORDED_FIXTURE_ONLY"
    assert decision["live_credentials_evidenced"] is False
    assert decision["live_execution_authorized"] is False


def test_tst_016_is_exact_but_has_no_formal_evidence() -> None:
    suite = _plan()["test_suite"]
    for key, expected in generator.EXPECTED_TEST_SUITE.items():
        assert suite[key] == expected
    assert suite["candidate_tools"] == ["live credential"]
    assert suite["environments"] == ["staging"]
    assert suite["formal_execution"] == "NOT_EXECUTED"
    assert suite["evidence"] is None


def test_owner_local_read_surface_is_exact_disabled_and_non_formal() -> None:
    owner = _plan()["owner_local_read_integration"]
    runtime = owner["runtime"]
    commands = owner["authoritative_fixed_commands"]

    assert owner["status"] == "INSTALLABLE_NOT_INSTALLED_OR_EXECUTED"
    assert owner["default_activation"] == "DISABLED_EXPLICIT_INSTALLED_COMMAND_ONLY"
    assert owner["evidence_authority"] == "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"
    assert owner["provider_data_classification"] == "UNTRUSTED_PROVIDER_DATA"
    assert owner["provider_credential_profile"] == (
        "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"
    )
    assert owner["raos_environment"] == (
        "OWNER_LOCAL_NOT_ENV_STAGING_NOT_RAOS_PRODUCTION"
    )
    assert runtime["bundle_sha256"] == generator.EXPECTED_OWNER_LOCAL_BUNDLE_SHA256
    assert runtime["launcher_sha256"] == (
        generator.EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256
    )
    assert runtime["installer_sha256"] == (
        generator.EXPECTED_OWNER_LOCAL_INSTALLER_SHA256
    )
    assert runtime["install_stage_sha256"] == (
        generator.EXPECTED_OWNER_LOCAL_INSTALL_STAGE_SHA256
    )
    assert runtime["repository_make_entrypoint"] == "NOT_PROVIDED"
    assert runtime["installer_credential_access"] == "FORBIDDEN"
    assert runtime["install_execution"] == "NOT_EXECUTED"
    assert commands["runtime_install"] == (
        generator._owner_local_authoritative_runtime_install_command()
    )
    assert commands["setup"] == generator._owner_local_authoritative_installed_command(
        ("setup",)
    )
    assert commands["rotate"] == generator._owner_local_authoritative_installed_command(
        ("rotate",)
    )
    assert commands["doctor"] == generator._owner_local_authoritative_installed_command(
        ("doctor",)
    )
    assert commands["list_apis"] == (
        generator._owner_local_authoritative_installed_command(("list-apis",))
    )
    assert commands["smoke_item_search"] == (
        generator._owner_local_authoritative_installed_command(
            ("smoke", "--api", "item-search")
        )
    )
    assert commands["smoke_product_search"] == (
        generator._owner_local_authoritative_installed_command(
            ("smoke", "--api", "product-search")
        )
    )
    for command in commands.values():
        assert command.startswith("/usr/bin/busybox env -i ")
        assert " make " not in f" {command} "
    assert owner["authoritative_request_gate"] == {
        "launcher_path": generator.OWNER_LOCAL_INSTALLED_LAUNCHER_PATH,
        "launcher_sha256": generator.EXPECTED_OWNER_LOCAL_LAUNCHER_SHA256,
        "authentication": "STATIC_BUSYBOX_FD4_SHA256_BEFORE_LAUNCHER_BODY",
        "argument_contract": (
            "request --api <item-search|product-search> --request-file <absolute-json>"
        ),
        "shell_interpolation": "FORBIDDEN_USE_POSITIONAL_ARGUMENTS",
    }
    request_template = owner["authoritative_request_template"]
    assert request_template == {
        "argv": generator._owner_local_authoritative_request_argv_template(),
        "api_argv_index": 12,
        "request_file_argv_index": 13,
        "rendering": "REPLACE_EXACT_TWO_ARRAY_ELEMENTS_THEN_DIRECT_EXECVE_NO_EVAL",
        "unrendered_or_extra_arguments": "FAIL_CLOSED",
    }
    argv = request_template["argv"]
    assert argv[11:] == [
        "rakuten-owner-local-request",
        "<item-search|product-search>",
        "<absolute-json>",
    ]
    assert 'exec "$p" request --api "$1" --request-file "$2"' in argv[10]
    assert "eval" not in argv[10]
    assert owner["registry"]["item-search"]["api_version"] == "2026-07-01"
    assert owner["registry"]["item-search"]["page"] == 1
    assert owner["registry"]["item-search"]["exact_selector_response_binding"] == (
        "SELECTED_ITEM_CODE_OR_SHOP_CODE_MUST_MATCH_EVERY_RETURNED_RECORD_OR_"
        "RESULT_MISMATCH"
    )
    assert owner["registry"]["product-search"]["api_version"] == "2025-08-01"
    assert owner["registry"]["product-search"]["page"] == 1
    assert owner["registry"]["product-search"]["exact_selector_response_binding"] == (
        "SELECTED_PRODUCT_ID_OR_CODE_MUST_MATCH_EVERY_RETURNED_RECORD_OR_"
        "RESULT_MISMATCH"
    )
    assert owner["transport"]["requests_per_invocation_maximum"] == 1
    assert owner["transport"]["retries"] == 0
    assert owner["transport"]["pagination_followups"] == 0
    assert owner["transport"]["dns_resolution_deadline_seconds"] == 5
    assert owner["transport"]["dns_execution_isolation"] == (
        "AUTHENTICATED_PROC_SELF_EXE_ISOLATED_NO_SITE_FIXED_HELPER_"
        "MINIMAL_ENV_CLOSE_FDS_PARENT_DEATH_SIGKILL"
    )
    assert owner["transport"]["dns_ipc_limits"] == (
        "MAX_64_CANDIDATES_MAX_65536_BYTES_STRICT_PARENT_REVALIDATION"
    )
    assert owner["transport"]["dns_failure"] == (
        "DNS_FAILED_NOT_SENT_REQUEST_COUNT_0_NO_PROVIDER_METADATA_NO_RETRY"
    )
    assert owner["transport"]["dns_process_cleanup"] == (
        "SIGKILL_TWO_BOUNDED_REAP_WAITS_AND_PIPE_CLOSE"
    )
    assert owner["transport"]["per_operation_read_timeout_seconds"] == 20
    assert owner["transport"]["response_read_deadline_seconds"] == 20
    assert owner["transport"]["response_read_deadline_scope"] == (
        "HEADERS_THROUGH_COMPLETE_BODY_OR_EOF"
    )
    assert owner["transport"]["response_read_primitive"] == (
        "RAW_RECV_INTO_REMAINING_TIMEOUT_AND_HTTPRESPONSE_READ1"
    )
    assert owner["transport"]["deadline_timeout"] == (
        "TIMEOUT_OUTCOME_AMBIGUOUS_NO_PARTIAL_RESPONSE_METADATA"
    )
    assert owner["transport"]["response_summary_relationships"] == (
        "PAGE1_EMPTY_ALL_ZERO_OR_NONEMPTY_COUNT_GTE_CARDINALITY_"
        "PAGECOUNT_EQUALS_MIN_CEIL_COUNT_DIV_HITS_100_FIRST_1_LAST_"
        "CARDINALITY"
    )
    assert owner["normalized_result"]["envelope"] == {
        "schema": "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V2",
        "version": 2,
        "exact_object_keys": list(generator.EXPECTED_OWNER_LOCAL_RESULT_OBJECT_KEYS),
        "summary_fields": ["count", "page", "first", "last", "hits", "pageCount"],
        "success_summary": "VALIDATED_INTEGER_VALUES",
        "terminal_time": (
            "CLAMP_EXACT_UTC_BACKWARD_OR_TERMINAL_SAMPLE_EXCEPTION_TO_STARTED_"
            "AT_OTHERWISE_VALIDATE"
        ),
        "failure_summary": "ALL_SIX_KEYS_NULL",
        "canonical_json": "UTF8_SORTED_KEYS_COMPACT_TRAILING_LF",
        "compatibility": (
            "V1_EVIDENCE_IMMUTABLE_V2_ADDS_NULLABLE_VALUE_FREE_VALIDATION_"
            "STAGE_NO_REWRITE"
        ),
    }
    assert owner["normalized_result"]["validation_diagnostic"] == {
        "field": "validation_stage_code",
        "values": [
            "SUMMARY_SHAPE",
            "COLLECTION_SHAPE",
            "RECORD_SHAPE",
            "EXACT_SELECTOR",
            "MANDATORY_TEXT",
            "URL",
            "CREDENTIAL_REFLECTION",
        ],
        "generic_diagnostic_unchanged": True,
        "success_and_non_validation_failures": None,
        "response_schema_drift_stages": [
            "SUMMARY_SHAPE",
            "COLLECTION_SHAPE",
            "RECORD_SHAPE",
            "EXACT_SELECTOR",
            "MANDATORY_TEXT",
            "URL",
            "CREDENTIAL_REFLECTION",
        ],
        "result_mismatch_stage": "EXACT_SELECTOR",
        "precedence": (
            "COLLECTION_THEN_SUMMARY_THEN_RECORD_PRESENCE_THEN_EXACT_SELECTOR_"
            "THEN_MANDATORY_TEXT_THEN_URL_THEN_CREDENTIAL_REFLECTION"
        ),
        "persisted_material": (
            "CLOSED_ENUM_ONLY_NO_FIELD_NAME_INDEX_EXPECTED_ACTUAL_PROVIDER_"
            "VALUE_BODY_OR_CREDENTIAL"
        ),
        "failure_evidence": (
            "COMPLETE_AVAILABLE_RESPONSE_METADATA_REQUEST_COUNT_PRESERVED_"
            "PROVIDER_RESULT_NULL"
        ),
        "previous_schema": "RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V1_IMMUTABLE",
    }
    assert owner["normalized_result"]["url_validation"] == {
        "syntax": {
            "scheme": "EXACT_LOWERCASE_HTTPS",
            "whitespace_and_controls": ("REJECT_UNICODE_WHITESPACE_AND_UNICODE_CC_CF"),
            "raw_backslash": "REJECT",
            "host": "VALID_IDNA_DNS_OR_BRACKETED_IPV6_WITH_OPTIONAL_PORT",
            "percent_escapes": "COMPLETE_HEX_PAIR_REQUIRED",
            "userinfo_and_fragment": "REJECT",
        },
        "non_null_https": {
            "item-search": ["itemUrl"],
            "product-search": ["productUrlPC"],
        },
        "nullable_scalar_url_values": {
            "item-search": ["affiliateUrl"],
            "product-search": [
                "affiliateUrl",
                "mediumImageUrl",
                "smallImageUrl",
            ],
        },
        "url_list_values": "NON_NULL_TUPLE_OF_HTTPS_URLS",
        "precedence": (
            "FIELD_PRESENCE_THEN_EXACT_SELECTOR_THEN_URL_VALUE_SHAPE_BEFORE_"
            "CREDENTIAL_REFLECTION"
        ),
        "refusal": "RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE",
    }
    assert owner["normalized_result"]["mandatory_text"] == {
        "item-search": ["itemCode", "itemName"],
        "product-search": ["productCode", "productId"],
        "maximum_characters": 20_000,
        "shape": "NON_NULL_NONEMPTY_NO_EDGE_WHITESPACE_UTF8_STRING",
        "optional_fields_unchanged": (
            "SHOP_CODE_SHOP_NAME_AND_PRODUCT_NAME_REMAIN_OPTIONAL_NULLABLE"
        ),
        "precedence": (
            "MANDATORY_KEY_PRESENCE_THEN_EXACT_SELECTOR_THEN_MANDATORY_TEXT_THEN_"
            "URL_THEN_CREDENTIAL_REFLECTION"
        ),
        "refusal": "RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE",
    }
    assert owner["normalized_result"]["credential_reflection"] == {
        "inspected_text_values": (
            "ALL_NORMALIZED_RECORD_STRING_VALUES_AND_STRING_LIST_MEMBERS"
        ),
        "excluded_typed_values": {
            "summary_fields": [
                "count",
                "page",
                "first",
                "last",
                "hits",
                "pageCount",
            ],
            "normalized_record_types": ["NULL", "INTEGER"],
            "policy": "VALIDATE_BY_FIELD_SCHEMA_AND_DO_NOT_COMPARE_AS_CREDENTIAL_TEXT",
            "rationale": "TYPED_SCALAR_COINCIDENCE_IS_NOT_TEXT_REFLECTION",
        },
        "success_persistence_scope": (
            "ALL_SIX_VALIDATED_SUMMARIES_AND_ALL_NORMALIZED_RECORD_VALUES"
        ),
        "representations": ("INSPECTED_TEXT_RAW_UTF8_OR_SINGLE_PERCENT_DECODED_BYTES"),
        "match": ("ANY_NONEMPTY_KNOWN_CREDENTIAL_VALUE_SUBSTRING_IN_INSPECTED_TEXT"),
        "refusal": "RESPONSE_SCHEMA_DRIFT_BEFORE_SUCCESS_ENVELOPE_OR_PERSISTENCE",
        "failure_evidence": (
            "COMPLETE_RESPONSE_METADATA_REQUEST_COUNT_1_NO_MATCHED_VALUE"
        ),
    }
    assert owner["verification"] == {
        "fake_and_recorded_only": True,
        "real_credentials": "NOT_READ",
        "provider_call": "NOT_EXECUTED",
        "formal_tst_016": "NOT_EXECUTED",
        "env_staging": "NOT_EXECUTED",
        "od_015": "UNRESOLVED",
        "raos_production": "NOT_EXECUTED",
    }
    assert Path("Makefile") not in generator.RUNTIME_PATHS
    assert Path("Makefile") not in generator.SOURCE_PATHS


def test_live_smoke_is_installable_but_not_installed_or_runnable() -> None:
    smoke = _plan()["live_smoke_definition"]
    assert smoke == generator.EXPECTED_SMOKE
    assert smoke["status"] == "INSTALLABLE_NOT_INSTALLED_OR_EXECUTED"
    assert smoke["runnable"] is False
    assert smoke["technical_entry_invocable_after_install_and_doctor"] is True
    assert smoke["runner"] == "OWNER_PRIVATE_VERSIONED_INSTALLED_ENTRY"
    assert smoke["runtime_install_command"] == (
        generator._authoritative_runtime_install_command()
    )
    assert smoke["runtime_install_command"].startswith("/usr/bin/busybox env -i ")
    for fragment in (
        '/usr/bin/busybox stat -Lc "%d %i %f %u %a %h %s" /proc/self/fd/4',
        '/usr/bin/busybox stat -c "%d %i %f %u %a %h %s" -- "$p"',
        '[ "$fm" = "$nm" ]',
        "[ $((v & 0xf000)) -eq 32768 ]",
        '[ "$4" -eq "$u" ]',
        "[ $((v & 18)) -eq 0 ]",
        '[ "$6" -eq 1 ]',
        '[ "$7" -le 2097152 ]',
    ):
        assert fragment in smoke["runtime_install_command"]
    assert " make " not in f" {smoke['runtime_install_command']} "
    assert smoke["runtime_installer_sha256"] == (
        generator.EXPECTED_RUNTIME_INSTALLER_SHA256
    )
    assert smoke["runtime_install_stage_sha256"] == (
        generator.EXPECTED_RUNTIME_INSTALL_STAGE_SHA256
    )
    assert smoke["runtime_install_entry_authentication"] == (
        "ROOT_OWNED_STATIC_BUSYBOX_FIXED_STAGE_AND_INSTALLER_FD_SHA256_GATE"
    )
    assert smoke["runtime_install_python_trust"] == (
        "EXACT_ROOT_PYTHON_BINARY_WITH_ROOT_OWNED_OS_RUNTIME_METADATA_CLOSURE"
    )
    assert smoke["direct_repository_installer_entry"] == (
        "REFUSE_BEFORE_RUNTIME_MUTATION"
    )
    assert smoke["credential_tree_during_install"] == "FORBIDDEN"
    assert smoke["automatic_post_install_doctor_or_run"] == "FORBIDDEN"
    assert smoke["runtime_install_execution"] == "NOT_EXECUTED"
    assert smoke["command"] == generator._authoritative_installed_command("run")
    assert smoke["doctor_command"] == generator._authoritative_installed_command(
        "doctor"
    )
    assert smoke["repository_make_entrypoints"] == (
        "NOT_PROVIDED_USE_REVIEWED_DIRECT_COMMANDS"
    )
    assert Path("Makefile") not in generator.RUNTIME_PATHS
    assert Path("Makefile") not in generator.SOURCE_PATHS
    make_lines = (
        (generator.REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    )
    for target in (
        "rakuten-live-smoke-runtime-install",
        "rakuten-live-smoke-doctor",
        "rakuten-live-smoke",
    ):
        assert f"{target}:" not in make_lines
    assert smoke["installed_bundle_sha256"] == (
        generator.EXPECTED_INSTALLED_BUNDLE_SHA256
    )
    assert (
        smoke["installed_launcher_sha256"]
        == generator.EXPECTED_INSTALLED_LAUNCHER_SHA256
    )
    assert smoke["direct_installed_launcher_entry"] == ("REFUSE_WITHOUT_OUTER_GATE_FD4")
    assert "repo://scripts/rakuten_live_smoke_runtime_install.sh" in smoke["artifacts"]
    assert smoke["invocation_gate"] == "FRESH_OWNER_INVOCATION_REQUIRED"
    assert smoke["live_execution_authority"] == "NOT_GRANTED_BY_THIS_ARTIFACT"
    assert smoke["evidence_authority"] == "NON_FORMAL_DIAGNOSTIC_ONLY"
    assert smoke["selected_environment"] == (
        "OWNER_LOCAL_NON_FORMAL_DIAGNOSTIC_WITH_STAGING_CREDENTIAL_BINDING"
    )
    assert smoke["selected_account"] is None
    assert smoke["selected_endpoint"] == "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701"
    assert smoke["credential_selection"] == (
        "FIXED_OWNER_PRIVATE_JSON_HASH_BOUND_TO_STAGING_ATTESTATION"
    )
    binding = smoke["staging_credential_binding"]
    assert binding["environment"] == "staging"
    assert binding["credential_purpose"] == (
        "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
    )
    assert binding["creation"] == (
        "EXTERNAL_OPERATIONS_PROCESS_NOT_PROVIDED_BY_THIS_ARTIFACT"
    )
    assert binding["authority"] == "DOES_NOT_EXECUTE_OR_SATISFY_TST_016"
    request = smoke["request"]
    assert request["method"] == "GET"
    assert request["authority"] == "openapi.rakuten.co.jp:443"
    assert request["path"] == "/ichibams/api/IchibaItem/Search/20260701"
    assert request["query"]["elements"] == (
        "count,page,first,last,hits,pageCount,affiliateUrl"
    )
    assert request["access_key_transport"] == "HEADER_accessKey_ONLY"
    assert request["request_limit"] == 1
    assert request["redirect_limit"] == 0
    assert request["dns_resolution_count"] == 1
    assert request["dns_candidate_policy"] == (
        "REJECT_ENTIRE_SET_IF_ANY_NON_PUBLIC_OR_MALFORMED"
    )
    assert request["tcp_candidate_policy"] == (
        "FIRST_VALIDATED_CANDIDATE_ONLY_NO_FALLBACK"
    )
    assert request["tls_hostname"] == "openapi.rakuten.co.jp"
    assert smoke["retry_policy"] == "ZERO_RETRY"
    assert smoke["pagination_policy"] == "ZERO_FOLLOWUP"
    assert smoke["response"]["response_sha256"] == (
        "REQUIRED_FOR_EACH_COMPLETE_BOUNDED_RESPONSE_BODY"
    )
    assert smoke["response"]["framing_policy"] == (
        "STRICT_CONTENT_LENGTH_CHUNKED_OR_CLOSE_DELIMITED"
    )
    assert smoke["response"]["incomplete_framing"] == (
        "REQUEST_AMBIGUOUS_NO_RESPONSE_DIGEST"
    )
    assert smoke["report"]["schema"] == ("RAOS_ST0505_RAKUTEN_LIVE_SMOKE_REPORT_V2")
    assert "response_sha256" in smoke["report"]["fields"]
    assert len(smoke["artifacts"]) == 8


def test_observations_are_absent_not_success_or_zero_errors() -> None:
    observations = _plan()["observation_boundary"]
    assert observations == generator.EXPECTED_OBSERVATIONS
    assert observations["status"] == "NOT_EXECUTED"
    for key in (
        "started_at",
        "finished_at",
        "auth_observation",
        "schema_observation",
        "rate_observation",
        "provider_request_id",
        "http_status",
        "latency",
    ):
        assert observations[key] is None
    assert observations["observations"] == []
    assert observations["errors"] == []
    assert observations["evidence"] == []
    assert observations["empty_interpretation"] == (
        "NO_LIVE_EXECUTION_EVIDENCE_NOT_ZERO_ERRORS_OR_SUCCESS"
    )


def test_rate_quota_cost_and_capacity_values_are_all_unset() -> None:
    boundary = _plan()["rate_quota_cost_boundary"]
    assert boundary == generator.EXPECTED_RATE_QUOTA_COST
    for key in (
        "rate_limit",
        "rate_remaining",
        "rate_reset",
        "quota_limit",
        "quota_remaining",
        "cost",
        "currency",
        "capacity",
    ):
        assert boundary[key] is None
    assert boundary["values"] == []


def test_execution_is_disabled_with_exact_integer_zero_actions() -> None:
    execution = _plan()["execution_boundary"]
    assert execution["enabled"] is False
    assert execution["status"] == "DISABLED_BY_DEFAULT_EXPLICIT_COMMAND_ONLY"
    assert execution["default_activation"] == "DISABLED"
    assert execution["explicit_invocation_required"] is True
    assert tuple(execution["action_counts"]) == generator.ACTION_COUNT_KEYS
    assert all(
        type(value) is int and value == 0
        for value in execution["action_counts"].values()
    )
    assert execution["network"] == "EXPLICIT_ONE_DIRECT_GET_ONLY"
    assert execution["credential"] == (
        "FIXED_OWNER_PRIVATE_STORE_WITH_STAGING_HASH_BINDING_ONLY"
    )
    assert execution["provider"] == "FIXED_RAKUTEN_ICHIBA_ENDPOINT_ONLY"
    assert execution["sdk"] == "ABSENT"
    assert execution["filesystem"] == (
        "PRIVATE_CREDENTIAL_READ_AND_SANITIZED_REPORT_ONLY"
    )
    assert execution["repository"] == (
        "NO_RAW_PROVIDER_MATERIAL_OR_TRACKED_REPOSITORY_PERSISTENCE"
    )
    assert execution["external_actions"] == ["EXPLICIT_ONE_GET"]


def test_verification_boundary_contains_no_live_or_formal_claim() -> None:
    verification = _plan()["verification_boundary"]
    assert verification["projection_only"] is True
    assert verification["predecessor_connection"] == "NOT_EXECUTED"
    assert verification["formal_tst_016"] == "NOT_EXECUTED"
    for key in (
        "live_auth",
        "live_schema",
        "live_rate",
        "provider_runtime",
        "network",
        "credentials",
        "storage",
        "persistence",
        "staging",
        "release",
        "production",
    ):
        assert verification[key] == "NOT_EXECUTED"
    assert verification["story_acceptance"] is False
    assert verification["production_eligible"] is False
    assert verification["approval"] is None


def test_installed_plan_contains_no_false_completion_claim_values() -> None:
    plan = json.loads(
        (generator.REPO_ROOT / generator.REFERENCE_PLAN_PATH).read_bytes()
    )
    assert tuple(plan) == generator.PLAN_KEYS

    def strings(value: object) -> list[str]:
        if type(value) is str:
            return [value]
        if type(value) is list:
            return [item for child in value for item in strings(child)]
        if type(value) is dict:
            return [item for child in value.values() for item in strings(child)]
        return []

    assert {
        "PASS",
        "READY",
        "VALIDATED",
        "IMPLEMENTED",
        "LIVE_SUCCESS",
        "AUTHENTICATED",
        "PRODUCTION_READY",
    }.isdisjoint(strings(plan))
