"""Static TST-012 surrogate and AsyncAPI safety tests for ST-0003."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_ROOT = REPOSITORY_ROOT / "changes" / "st-0003" / "contracts"
PREDECESSOR_ROOT = REPOSITORY_ROOT / "changes" / "st-0002" / "contracts"
ADMIN_PATH = CONTRACTS_ROOT / "openapi-admin.v0.3.yaml"
ASYNCAPI_PATH = CONTRACTS_ROOT / "asyncapi.v0.3.yaml"

EXISTING_AI_OPERATIONS = {
    "AI-001": ("get", "/api/v1/admin/ai/jobs"),
    "AI-002": ("post", "/api/v1/admin/ai/jobs"),
    "AI-003": ("get", "/api/v1/admin/ai/jobs/{id}"),
    "AI-004": ("post", "/api/v1/admin/ai/jobs/{id}/cancel"),
    "AI-005": ("get", "/api/v1/admin/ai/prompt-versions"),
    "AI-006": ("get", "/api/v1/admin/ai/model-routes"),
    "AI-007": ("get", "/api/v1/admin/ai/evaluation-results"),
    "AI-008": ("post", "/api/v1/admin/ai/evaluations"),
}
NEW_AI_OPERATIONS = {
    "AI-101": ("get", "/api/v1/admin/ai/tasks"),
    "AI-102": ("get", "/api/v1/admin/ai/tasks/{taskCode}"),
    "AI-103": ("post", "/api/v1/admin/ai/prompt-versions"),
    "AI-104": ("post", "/api/v1/admin/ai/model-route-versions"),
    "AI-105": ("post", "/api/v1/admin/ai/evaluation-datasets"),
    "AI-106": ("post", "/api/v1/admin/ai/evaluation-datasets/{id}:lock"),
    "AI-107": ("get", "/api/v1/admin/ai/evaluation-suites"),
    "AI-108": ("post", "/api/v1/admin/ai/evaluation-runs"),
    "AI-109": ("get", "/api/v1/admin/ai/evaluation-runs/{id}"),
    "AI-110": (
        "post",
        "/api/v1/admin/ai/evaluation-case-results/{id}/human-evaluations",
    ),
    "AI-111": ("post", "/api/v1/admin/ai/judge-calibrations"),
    "AI-112": ("post", "/api/v1/admin/ai/release-decisions"),
    "AI-113": (
        "post",
        "/api/v1/admin/ai/release-decisions/{id}:approve-canary",
    ),
    "AI-114": (
        "post",
        "/api/v1/admin/ai/release-decisions/{id}:approve-active",
    ),
    "AI-115": ("post", "/api/v1/admin/ai/release-decisions/{id}:revoke"),
}
CONCURRENCY_OPERATIONS = {"AI-106", "AI-113", "AI-114", "AI-115"}
EXPECTED_NEW_EVENT_COMPONENTS = {
    "jp_raos_ai_evaluation_completed_v2",
    "jp_raos_ai_release_decision_approved_v1",
    "jp_raos_ai_release_decision_revoked_v1",
}
EXPECTED_NEW_EVENT_TYPES = {
    "jp.raos.ai.evaluation_completed.v2",
    "jp.raos.ai.release_decision_approved.v1",
    "jp.raos.ai.release_decision_revoked.v1",
}
SENSITIVE_PROPERTY_NAMES = {
    "api_key",
    "chain_of_thought",
    "commission_amount",
    "credential",
    "finance_data",
    "input_content",
    "input_fixture",
    "output_content",
    "profit",
    "prompt_body",
    "raw_input",
    "raw_output",
    "raw_prompt",
    "review_body",
    "secret",
    "source_packet",
    "source_text",
}


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def operation_map(document: dict[str, Any]) -> dict[str, tuple[str, str, dict[str, Any]]]:
    operations: dict[str, tuple[str, str, dict[str, Any]]] = {}
    for path, path_item in document["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_id = operation["operationId"]
            assert operation_id not in operations, f"duplicate operation: {operation_id}"
            operations[operation_id] = (method, path, operation)
    return operations


def parameter_refs(operation: dict[str, Any]) -> set[str]:
    return {
        parameter["$ref"]
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict) and "$ref" in parameter
    }


def success_responses(operation: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        response
        for code, response in operation["responses"].items()
        if str(code).startswith("2") and isinstance(response, dict)
    ]


def walk_property_names(document: Any) -> set[str]:
    names: set[str] = set()
    if isinstance(document, dict):
        properties = document.get("properties")
        if isinstance(properties, dict):
            names.update(str(name) for name in properties)
        for value in document.values():
            names.update(walk_property_names(value))
    elif isinstance(document, list):
        for value in document:
            names.update(walk_property_names(value))
    return names


def local_schema_registry() -> Registry:
    registry = Registry()
    for path in CONTRACTS_ROOT.rglob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        schema_id = document.get("$id")
        if isinstance(schema_id, str):
            registry = registry.with_resource(
                schema_id,
                Resource.from_contents(document),
            )
    return registry


def example_schema_value(schema: dict[str, Any]) -> Any:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next(value for value in schema_type if value != "null")
    if schema_type == "string":
        if schema.get("format") == "uuid":
            return "00000000-0000-7000-8000-000000000001"
        if schema.get("format") == "date-time":
            return "2026-07-31T00:00:00Z"
        pattern = schema.get("pattern", "")
        if pattern == "^[0-9a-f]{64}$":
            return "a" * 64
        if pattern == "^[0-9a-f]{40,64}$":
            return "a" * 40
        return "x" * max(1, int(schema.get("minLength", 1)))
    if schema_type == "integer":
        return max(1, int(schema.get("minimum", 0)))
    if schema_type == "number":
        return max(0, schema.get("minimum", 0))
    if schema_type == "boolean":
        return True
    if schema_type == "array":
        return []
    if schema_type == "object":
        properties = schema.get("properties", {})
        return {
            name: example_schema_value(properties[name])
            for name in schema.get("required", [])
        }
    raise AssertionError(f"cannot construct example for schema: {schema}")


def valid_event_instance(schema: dict[str, Any]) -> dict[str, Any]:
    overlay = schema["allOf"][1]
    constrained = overlay["properties"]
    uuid = "00000000-0000-7000-8000-000000000001"
    return {
        "specversion": "1.0",
        "id": uuid,
        "source": "urn:raos:test",
        "type": constrained["type"]["const"],
        "subject": f"urn:raos:evaluation_run:{uuid}",
        "time": "2026-07-31T00:00:00Z",
        "datacontenttype": "application/json",
        "dataschema": constrained["dataschema"]["const"],
        "event_version": constrained["event_version"]["const"],
        "producer": "ai",
        "aggregate": {"type": "evaluation_run", "id": uuid, "version": 1},
        "correlation_id": uuid,
        "actor": {"actor_type": "SYSTEM"},
        "classification": "CONFIDENTIAL",
        "data": example_schema_value(constrained["data"]),
    }


def test_existing_ai_001_through_008_operations_are_semantically_unchanged() -> None:
    predecessor = operation_map(
        load_yaml(PREDECESSOR_ROOT / "openapi-admin.v0.2.yaml")
    )
    candidate = operation_map(load_yaml(ADMIN_PATH))

    for operation_id, (method, path) in EXISTING_AI_OPERATIONS.items():
        assert predecessor[operation_id][:2] == (method, path)
        assert candidate[operation_id][:2] == (method, path)
        assert candidate[operation_id][2] == predecessor[operation_id][2]

    cancel = candidate["AI-004"][2]
    assert "#/components/parameters/IfMatch" not in parameter_refs(cancel)
    assert cancel.get("x-raos-concurrency-required") is not True
    assert "428" not in cancel["responses"]


def test_legacy_prompt_version_response_stays_optional_while_v1_is_strict() -> None:
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)
    schemas = admin["components"]["schemas"]

    assert operations["AI-005"][2]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/PromptVersionList"}
    assert schemas["PromptVersionList"]["properties"]["items"]["items"] == {
        "$ref": "#/components/schemas/PromptVersion"
    }

    legacy = schemas["PromptVersion"]
    assert legacy["properties"]["author_principal_id"] == {
        "type": "string",
        "format": "uuid",
    }
    assert "author_principal_id" not in legacy["required"]

    strict_v1 = schemas["PromptVersionV1"]
    assert strict_v1["properties"]["author_principal_id"] == {
        "type": "string",
        "format": "uuid",
    }
    assert "author_principal_id" in strict_v1["required"]


def test_exact_ai_101_through_115_operation_inventory_is_present() -> None:
    operations = operation_map(load_yaml(ADMIN_PATH))
    actual_new = {
        operation_id: (method, path)
        for operation_id, (method, path, _operation) in operations.items()
        if operation_id.startswith("AI-1")
    }
    assert actual_new == NEW_AI_OPERATIONS


def test_new_ai_operations_are_authenticated_authorized_and_auditable() -> None:
    operations = operation_map(load_yaml(ADMIN_PATH))

    for operation_id in NEW_AI_OPERATIONS:
        operation = operations[operation_id][2]
        security = operation.get("security")
        assert isinstance(security, list) and len(security) == 1
        assert set(security[0]) == {"oidcOAuth2"}
        scopes = security[0]["oidcOAuth2"]
        assert scopes and all(scope.startswith("ai:") for scope in scopes)
        assert {"401", "403"} <= operation["responses"].keys()
        assert operation.get("x-raos-audit-action")
        assert operation.get("x-raos-kind") in {
            "command",
            "async_command",
            "query",
        }


def test_new_commands_require_idempotency_without_retrofitting_queries() -> None:
    operations = operation_map(load_yaml(ADMIN_PATH))

    for operation_id, (method, _path) in NEW_AI_OPERATIONS.items():
        operation = operations[operation_id][2]
        references = parameter_refs(operation)
        if method == "post":
            assert "#/components/parameters/IdempotencyKey" in references
            assert operation["x-raos-idempotency-required"] is True
        else:
            assert "#/components/parameters/IdempotencyKey" not in references
            assert operation.get("x-raos-idempotency-required") is not True


def test_only_new_mutable_transitions_require_if_match_and_return_etag() -> None:
    operations = operation_map(load_yaml(ADMIN_PATH))

    for operation_id in NEW_AI_OPERATIONS:
        operation = operations[operation_id][2]
        references = parameter_refs(operation)
        if operation_id in CONCURRENCY_OPERATIONS:
            assert "#/components/parameters/IfMatch" in references
            assert operation["x-raos-concurrency-required"] is True
            assert {"409", "428"} <= operation["responses"].keys()
            assert operation["x-raos-success-etag-required"] is True
            successes = success_responses(operation)
            assert successes
            for response in successes:
                assert response["headers"]["ETag"] == {
                    "$ref": "#/components/headers/ETag"
                }
        else:
            assert "#/components/parameters/IfMatch" not in references
            assert operation.get("x-raos-concurrency-required") is not True

    dataset_create = operations["AI-105"][2]
    assert dataset_create["x-raos-success-etag-required"] is True
    assert dataset_create["responses"]["201"]["headers"]["ETag"] == {
        "$ref": "#/components/headers/ETag"
    }


def test_new_operation_errors_use_rfc9457_problem_details() -> None:
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)

    for code, response in admin["components"]["responses"].items():
        if not str(code).startswith(("4", "5")):
            continue
        media = response["content"]["application/problem+json"]
        assert media["schema"] == {"$ref": "#/components/schemas/ProblemDetails"}

    for operation_id in NEW_AI_OPERATIONS:
        operation = operations[operation_id][2]
        for code, response in operation["responses"].items():
            if not str(code).startswith(("4", "5")):
                continue
            assert response == {"$ref": f"#/components/responses/{code}"}


def test_release_bindings_and_calibration_gate_are_portable_contracts() -> None:
    schema_root = CONTRACTS_ROOT / "schemas" / "ai-governance"
    release = json.loads(
        schema_root.joinpath("release-decision.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    release_request = json.loads(
        schema_root.joinpath(
            "release-decision-create-request.v1.schema.json"
        ).read_text(encoding="utf-8")
    )
    direct_bindings = {
        "resolved_model_id",
        "policy_bundle_version_id",
        "dataset_version_id",
        "code_git_sha",
    }
    for schema in (release, release_request):
        assert direct_bindings <= set(schema["required"])
        assert direct_bindings <= set(schema["properties"])
        for field in direct_bindings - {"code_git_sha"}:
            assert schema["properties"][field] == {
                "type": "string",
                "format": "uuid",
            }
        git_sha = schema["properties"]["code_git_sha"]
        assert git_sha["type"] == "string"
        assert git_sha["minLength"] == 40
        assert git_sha["maxLength"] == 64
        assert git_sha["pattern"] == "^[0-9a-f]{40,64}$"

    calibration = json.loads(
        schema_root.joinpath("judge-calibration.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    gate = calibration["allOf"][0]
    assert gate["if"] == {
        "properties": {"status": {"const": "PASSED"}},
        "required": ["status"],
    }
    then = gate["then"]
    assert {
        "weighted_kappa",
        "zero_tolerance_false_pass_rate",
        "zero_tolerance_false_fail_rate",
        "case_count",
        "report_artifact_id",
        "approved_by_principal_id",
        "approved_at",
        "expires_at",
    } <= set(then["required"])
    assert then["properties"]["weighted_kappa"]["minimum"] == 0.70
    assert (
        then["properties"]["zero_tolerance_false_pass_rate"]["maximum"]
        == 0.01
    )
    assert (
        then["properties"]["zero_tolerance_false_fail_rate"]["maximum"]
        == 0.05
    )
    assert then["properties"]["case_count"]["minimum"] == 200


def test_completion_execution_security_metadata_matches_every_api_copy() -> None:
    evaluation_run = json.loads(
        CONTRACTS_ROOT.joinpath(
            "schemas",
            "ai-governance",
            "evaluation-run.v1.schema.json",
        ).read_text(encoding="utf-8")
    )
    expected = evaluation_run[
        "x-raos-completion-execution-security-invariants"
    ]
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)
    asyncapi = load_yaml(ASYNCAPI_PATH)
    event_payload_ref = asyncapi["components"]["messages"][
        "jp_raos_ai_evaluation_completed_v2"
    ]["payload"]["$ref"]
    event = json.loads(
        (ASYNCAPI_PATH.parent / event_payload_ref).resolve().read_text(
            encoding="utf-8"
        )
    )

    copies = (
        operations["AI-108"][2][
            "x-raos-completion-execution-security-invariants"
        ],
        operations["AI-109"][2][
            "x-raos-completion-execution-security-invariants"
        ],
        admin["x-raos-ai-governance"][
            "evaluation_completion_execution_security_invariants"
        ],
        admin["components"]["schemas"]["EvaluationResult"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
        operations["AI-108"][2]["x-raos-completion-evidence-invariants"][
            "execution_security"
        ],
        admin["x-raos-ai-governance"][
            "evaluation_run_completion_evidence_invariants"
        ]["execution_security"],
        event["allOf"][1]["properties"]["data"][
            "x-raos-completion-evidence-invariants"
        ]["execution_security"],
    )
    assert all(copy == expected for copy in copies)
    assert "completion_trigger_wrapper" not in json.dumps(copies, sort_keys=True)


def test_task_contract_and_run_detail_are_resolvable_metadata_only_views() -> None:
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)

    assert operations["AI-102"][2]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/AITaskContractV1"}
    task_contract = admin["components"]["schemas"]["AITaskContractV1"]
    assert task_contract["additionalProperties"] is False
    assert set(task_contract["required"]) == set(task_contract["properties"])
    assert set(task_contract["properties"]) == {
        "task",
        "active_prompt_versions",
        "active_output_schema_version_id",
        "active_model_route_version_id",
        "active_release_decision_id",
    }
    assert task_contract["properties"]["task"] == {
        "$ref": "#/components/schemas/AITaskDefinition"
    }
    active_prompts = task_contract["properties"]["active_prompt_versions"]["items"]
    assert active_prompts["additionalProperties"] is False
    assert set(active_prompts["required"]) == {"locale", "prompt_version_id"}

    assert operations["AI-109"][2]["responses"]["200"]["content"][
        "application/json"
    ]["schema"] == {"$ref": "#/components/schemas/EvaluationRunDetailV1"}
    run_detail = admin["components"]["schemas"]["EvaluationRunDetailV1"]
    assert run_detail["x-raos-classification"] == "CONFIDENTIAL"
    assert run_detail["additionalProperties"] is False
    assert set(run_detail["required"]) == set(run_detail["properties"])
    assert set(run_detail["properties"]) == {
        "run",
        "case_result_summary",
        "slice_metrics",
        "artifact_refs",
    }
    assert run_detail["properties"]["run"] == {
        "$ref": "#/components/schemas/EvaluationRunV1"
    }
    names = {name.casefold() for name in walk_property_names(run_detail)}
    assert not (names & SENSITIVE_PROPERTY_NAMES)
    assert {
        "run_manifest_artifact_id",
        "report_artifact_id",
        "result_artifact_ids",
    } == set(run_detail["properties"]["artifact_refs"]["properties"])


def test_release_approval_is_human_only_step_up_and_separation_of_duties() -> None:
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)
    expected_separation = {
        "prompt_author_cannot_be_sole_approver",
        "critical_task_requires_two_distinct_approvers",
    }

    for operation_id in ("AI-113", "AI-114"):
        operation = operations[operation_id][2]
        assert operation["x-raos-step-up-required"] is True
        assert operation["x-raos-human-approval-required"] is True
        assert operation["x-raos-ai-actor-forbidden"] is True
        assert set(operation["x-raos-separation-of-duties"]) == (
            expected_separation
        )

    governance = admin["x-raos-ai-governance"]["release_approval"]
    assert governance == {
        "human_only": True,
        "step_up_required": True,
        "critical_two_person_rule": True,
        "prompt_author_cannot_be_sole_approver": True,
        "canary_to_active_same_aggregate": True,
    }


def test_release_commands_bind_phase_specific_append_only_approval_evidence() -> None:
    admin = load_yaml(ADMIN_PATH)
    operations = operation_map(admin)
    schemas = admin["components"]["schemas"]

    expected_request_refs = {
        "AI-113": "#/components/schemas/ReleaseCanaryApprovalRequestV1",
        "AI-114": "#/components/schemas/ReleaseActiveApprovalRequestV1",
        "AI-115": "#/components/schemas/ReleaseDecisionRevokeRequestV1",
    }
    for operation_id, expected_ref in expected_request_refs.items():
        operation = operations[operation_id][2]
        assert operation["requestBody"]["content"]["application/json"][
            "schema"
        ] == {"$ref": expected_ref}

    for operation_id in ("AI-113", "AI-114"):
        operation = operations[operation_id][2]
        assert operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ] == {
            "$ref": "#/components/schemas/ReleaseDecisionApprovalResultV1"
        }
        assert operation["x-raos-append-only-resource"] == "ReleaseApprovalV1"
        assert operation["x-raos-primary-principal-must-match-authenticated-user"]
        assert operation[
            "x-raos-prompt-author-forbidden-as-either-approver"
        ] is True

    approval = schemas["ReleaseApprovalV1"]
    assert approval["additionalProperties"] is False
    assert approval["x-raos-append-only"] is True
    assert approval["x-raos-human-only"] is True
    assert set(approval["required"]) == set(approval["properties"])
    assert approval["properties"]["phase"] == {
        "type": "string",
        "enum": ["CANARY", "ACTIVE"],
    }
    assert approval["properties"]["primary_approver_role"]["const"] == (
        "APPROVER"
    )
    assert approval["properties"]["second_approver_role"]["const"] == "OWNER"

    result = schemas["ReleaseDecisionApprovalResultV1"]
    assert result["additionalProperties"] is False
    assert result["required"] == ["release_decision", "release_approval"]
    assert result["properties"]["release_approval"] == {
        "$ref": "#/components/schemas/ReleaseApprovalV1"
    }

    canary = schemas["ReleaseCanaryApprovalRequestV1"]
    active = schemas["ReleaseActiveApprovalRequestV1"]
    common_signed_fields = {
        "decision_manifest_sha256",
        "primary_approver_principal_id",
        "primary_approver_role",
        "second_approver_principal_id",
        "second_approver_role",
        "approval_artifact_id",
        "approval_sha256",
        "signed_at",
    }
    assert set(canary["required"]) == common_signed_fields
    assert set(canary["properties"]) == common_signed_fields
    prior_canary_checkpoint_fields = {
        "canary_evidence_artifact_id",
        "canary_evidence_sha256",
        "canary_monitoring_artifact_id",
        "canary_monitoring_sha256",
    }
    assert set(active["required"]) == (
        common_signed_fields | prior_canary_checkpoint_fields
    )
    assert set(active["properties"]) == set(active["required"])
    assert set(
        active["x-raos-prior-canary-checkpoint-binding"]["request_fields"]
    ) == prior_canary_checkpoint_fields
    assert set(
        operations["AI-114"][2][
            "x-raos-prior-canary-checkpoint-binding"
        ]["request_fields"]
    ) == prior_canary_checkpoint_fields
    for request in (canary, active):
        assert "prompt_author_cannot_be_primary_or_second_approver" in request[
            "x-raos-constraints"
        ]
    cross_phase_fields = [
        "decision_manifest_sha256",
        "approval_artifact_id",
        "approval_sha256",
    ]
    assert active["x-raos-cross-phase-binding"]["must_differ"] == (
        cross_phase_fields
    )
    assert operations["AI-114"][2]["x-raos-cross-phase-must-differ"] == (
        cross_phase_fields
    )


def test_model_judge_provenance_scope_is_portable_admin_metadata() -> None:
    admin = load_yaml(ADMIN_PATH)
    schema = admin["components"]["schemas"]["EvaluationResult"]
    assert "allOf" not in schema
    scope = schema["x-raos-judge-calibration-scope-invariants"]
    assert scope["applies_to_grader"] == "grader.model_judge.v1"
    assert scope["required_calibration_status"] == "PASSED"
    assert scope["calibration_must_be_unexpired"] is True
    assert scope["evaluation_metric_exact_matches"] == {
        "JudgeCalibrationV1.id": "EvaluationResult.judge_calibration_id",
        "JudgeCalibrationV1.judge_route_version_id": (
            "EvaluationResult.judge_route_version_id"
        ),
        "JudgeCalibrationV1.judge_prompt_version_id": (
            "EvaluationResult.judge_prompt_version_id"
        ),
        "JudgeCalibrationV1.rubric_artifact_id": (
            "EvaluationResult.judge_rubric_artifact_id"
        ),
        "JudgeCalibrationV1.resolved_judge_model_id": (
            "EvaluationResult.judge_resolved_model_id"
        ),
        "JudgeCalibrationV1.grader_version": (
            "EvaluationResult.judge_grader_version"
        ),
    }


def test_admin_evaluation_result_passed_is_nullable_with_exact_p95_truth() -> None:
    admin = load_yaml(ADMIN_PATH)
    evaluation_result = admin["components"]["schemas"]["EvaluationResult"]
    assert evaluation_result["properties"]["passed"]["type"] == [
        "boolean",
        "null",
    ]
    assert "readOnly" not in evaluation_result["properties"]["passed"]
    assert "allOf" not in evaluation_result

    cost_latency = evaluation_result[
        "x-raos-cost-latency-reporting-completeness-invariants"
    ]
    assert cost_latency["passed_truth_table"] == {
        "current_frozen_canonical_report_only_p95": "MUST_BE_NULL",
        "required_p95": "MUST_BE_NON_NULL_DATABASE_EXACT",
        "legacy_or_non_report_only_metric": "MUST_BE_NON_NULL_DATABASE_EXACT",
    }


def test_release_events_exclude_human_principals_and_document_rollback_binding() -> None:
    for filename in (
        "jp-raos-ai-release-decision-approved-v1.schema.json",
        "jp-raos-ai-release-decision-revoked-v1.schema.json",
    ):
        schema = json.loads(
            (CONTRACTS_ROOT / "schemas" / "events" / filename).read_text(
                encoding="utf-8"
            )
        )
        data_schema = schema["allOf"][1]["properties"]["data"]
        data_properties = set(data_schema["properties"])
        assert not {
            "primary_approver_principal_id",
            "second_approver_principal_id",
            "approved_by_principal_id",
            "revoked_by_principal_id",
        } & data_properties
        rollback_binding = data_schema["x-raos-rollback-binding"]
        assert "PREVIOUS_RELEASE" in rollback_binding
        assert "rollback_release_decision_id" in rollback_binding
        assert "DISABLE_ROUTE" in rollback_binding
        assert "rollback_runbook_artifact_id" in rollback_binding
        assert "rollback_runbook_sha256" in rollback_binding


def test_asyncapi_adds_only_the_three_safe_governance_events() -> None:
    predecessor = load_yaml(PREDECESSOR_ROOT / "asyncapi.v0.2.yaml")
    candidate = load_yaml(ASYNCAPI_PATH)
    old_messages = predecessor["components"]["messages"]
    new_messages = candidate["components"]["messages"]

    assert set(old_messages) <= set(new_messages)
    for name, message in old_messages.items():
        assert new_messages[name] == message
    assert set(new_messages) - set(old_messages) == EXPECTED_NEW_EVENT_COMPONENTS

    added_types = {
        new_messages[name]["x-raos-event-type"]
        for name in EXPECTED_NEW_EVENT_COMPONENTS
    }
    assert added_types == EXPECTED_NEW_EVENT_TYPES


def test_new_event_payloads_are_internal_metadata_only_and_strict() -> None:
    asyncapi = load_yaml(ASYNCAPI_PATH)

    for name in EXPECTED_NEW_EVENT_COMPONENTS:
        message = asyncapi["components"]["messages"][name]
        assert message["x-raos-classification"] == "CONFIDENTIAL"
        payload_ref = message["payload"]["$ref"]
        payload_path = (ASYNCAPI_PATH.parent / payload_ref).resolve()
        payload_path.relative_to(CONTRACTS_ROOT.resolve())
        schema = json.loads(payload_path.read_text(encoding="utf-8"))

        names = {name.casefold() for name in walk_property_names(schema)}
        assert not (names & SENSITIVE_PROPERTY_NAMES)
        assert schema["allOf"][0] == {
            "$ref": "../common/event-envelope.schema.json"
        }
        overlay = schema["allOf"][1]
        assert set(overlay["required"]) == set(overlay["properties"])
        assert overlay["properties"]["classification"] == {
            "const": "CONFIDENTIAL"
        }
        assert overlay["properties"]["producer"] == {"const": "ai"}
        assert overlay["properties"]["dataschema"] == {"const": schema["$id"]}
        event_type = overlay["properties"]["type"]["const"]
        expected_version = int(event_type.rsplit(".v", 1)[1])
        assert overlay["properties"]["event_version"] == {
            "const": expected_version
        }

        data = overlay["properties"]["data"]
        assert data["type"] == "object"
        assert data["additionalProperties"] is False
        assert set(data["required"]) == set(data["properties"])
        assert any(
            property_name.endswith(("_id", "_sha256"))
            for property_name in data["properties"]
        )


def test_new_event_validation_rejects_missing_or_downgraded_classification() -> None:
    registry = local_schema_registry()
    asyncapi = load_yaml(ASYNCAPI_PATH)

    for name in EXPECTED_NEW_EVENT_COMPONENTS:
        payload_ref = asyncapi["components"]["messages"][name]["payload"]["$ref"]
        payload_path = (ASYNCAPI_PATH.parent / payload_ref).resolve()
        schema = json.loads(payload_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry)
        valid = valid_event_instance(schema)
        assert not list(validator.iter_errors(valid))

        missing_classification = deepcopy(valid)
        del missing_classification["classification"]
        assert list(validator.iter_errors(missing_classification))

        public_classification = deepcopy(valid)
        public_classification["classification"] = "PUBLIC"
        assert list(validator.iter_errors(public_classification))

        wrong_version = deepcopy(valid)
        wrong_version["event_version"] += 1
        assert list(validator.iter_errors(wrong_version))


def test_new_events_are_not_exposed_by_public_contract() -> None:
    public_text = (
        CONTRACTS_ROOT / "openapi-public.v0.1.yaml"
    ).read_text(encoding="utf-8")
    for event_type in EXPECTED_NEW_EVENT_TYPES:
        assert event_type not in public_text

    public = load_yaml(CONTRACTS_ROOT / "openapi-public.v0.1.yaml")
    assert not any("/ai" in path.lower() for path in public["paths"])
