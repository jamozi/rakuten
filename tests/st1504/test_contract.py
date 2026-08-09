"""Positive contract and reference-plan semantics for ST-1504."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1504_github_oidc as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_interface_only_model(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    assert github_oidc_model.contract["document"] == {
        "id": "RAOS-GITHUB-OIDC-DEPLOYMENT-001",
        "version": "1.0.0",
        "story_id": "ST-1504",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(github_oidc_model.contract) == generator.TOP_LEVEL_KEYS


def test_both_predecessors_are_exactly_bound_and_fail_closed(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    bindings = _mapping(github_oidc_model.contract["predecessor_bindings"])
    assert bindings == generator.EXPECTED_SECTIONS["predecessor_bindings"]
    governance = _mapping(bindings["pr_governance"])
    assert governance["required_artifact_kind"] == "DESIRED_STATE_NOT_API_PAYLOAD"
    assert governance["required_desired_enforcement"] == "active"
    assert governance["required_local_application_status"] == "NOT_EXECUTED"
    assert governance["required_remote_mutation"] == "FORBIDDEN"
    assert governance["required_bypass_actors"] == []
    assert all(governance["required_protected_pr_controls"].values())
    foundation = _mapping(bindings["terraform_foundation"])
    assert foundation["required_activation_status"] == "DISABLED"
    assert foundation["required_resource_payloads"] == "FORBIDDEN"
    assert foundation["required_planned_actions"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
    }


def test_logical_path_is_reference_intent_only(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    path = _mapping(plan["logical_identity_path"])
    assert path == {
        "classification": "LOGICAL_IDENTITY_PATH_REFERENCE_ONLY",
        "source": "GITHUB_ACTIONS_OIDC",
        "destination": "AWS_SHORT_LIVED_WORKLOAD_SESSION",
        "github_workload_identity": "REQUIRED_NOT_CONFIGURED",
        "aws_role_session": "REQUIRED_NOT_CONFIGURED",
        "executable_workflow": "ABSENT",
        "iam_trust_policy": "ABSENT",
        "provider_sdk_types": "ABSENT",
        "production_deployment": "FORBIDDEN",
    }


def test_every_actual_binding_remains_null_or_empty(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    selected = _mapping(
        generator.reference_plan_document(github_oidc_model)["selected_bindings"]
    )
    assert set(selected) == set(generator._selected_bindings())
    assert all(value is None or value == [] for value in selected.values())


def test_trust_constraints_require_exact_claims_and_deny_pr_broadening(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    trust = _mapping(
        generator.reference_plan_document(github_oidc_model)["trust_constraints"]
    )
    assert trust["status"] == "REQUIRED_NOT_CONFIGURED"
    assert trust["required_claim_bindings"] == list(generator.REQUIRED_CLAIM_BINDINGS)
    for field in (
        "exact_repository_identity",
        "exact_trusted_ref",
        "exact_workflow_identity",
        "exact_environment",
        "exact_audience",
        "exact_subject",
    ):
        assert trust[field] == "REQUIRED_NOT_CONFIGURED"
    for field in (
        "wildcard_trust",
        "fork_pull_request",
        "untrusted_pull_request",
        "untrusted_ref",
        "untrusted_environment",
        "pull_request_target_credential_path",
        "unbounded_reusable_workflow_caller",
        "broad_organization_subject",
        "broad_repository_subject",
        "broad_ref_subject",
    ):
        assert trust[field] == "FORBIDDEN"


def test_credential_boundary_is_short_lived_material_free_and_non_issuing(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    boundary = _mapping(
        generator.reference_plan_document(github_oidc_model)["credential_boundary"]
    )
    assert boundary["oidc_session"] == "SHORT_LIVED_REQUIRED_NOT_CONFIGURED"
    assert boundary["least_privilege"] == "REQUIRED_NOT_CONFIGURED"
    assert boundary["credential_material"] == "ABSENT"
    assert boundary["credential_issuance_capability"] == "ABSENT"
    assert boundary["secret_names"] == []
    assert boundary["secret_values"] == []
    for field in (
        "long_lived_cloud_key",
        "repository_secret_cloud_credential",
        "fork_pr_credential_issuance",
        "untrusted_ref_credential_issuance",
        "untrusted_environment_credential_issuance",
        "role_chaining",
        "privilege_escalation",
    ):
        assert boundary[field] == "FORBIDDEN"


def test_workflow_permissions_are_intent_only_and_exact_job_scoped(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    permissions = _mapping(
        generator.reference_plan_document(github_oidc_model)["workflow_permissions"]
    )
    assert permissions["classification"] == "INTENT_ONLY_WORKFLOW_ABSENT"
    assert permissions["actual_workflow"] == "ABSENT"
    assert permissions["id_token_write_scope"] == (
        "FUTURE_EXACT_APPROVED_DEPLOY_JOB_ONLY"
    )
    assert permissions["contents_permission"] == (
        "READ_MINIMUM_REQUIRED_NOT_CONFIGURED"
    )
    for field in (
        "write_all",
        "admin_permissions",
        "secrets_access",
        "mutable_external_action_references",
        "unbounded_reusable_workflow_callers",
        "pull_request_target_credential_path",
    ):
        assert permissions[field] == "FORBIDDEN"


def test_production_environment_requires_distinct_non_bypassable_human_approval(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    protection = _mapping(
        generator.reference_plan_document(github_oidc_model)["environment_protection"]
    )
    for field in (
        "production_environment",
        "distinct_human_approval",
        "protected_environment",
        "exact_allowed_refs",
    ):
        assert protection[field] == "REQUIRED_NOT_CONFIGURED"
    for field in ("self_approval", "approval_bypass", "deployment_without_approval"):
        assert protection[field] == "FORBIDDEN"


def test_activation_operations_and_action_counts_fail_closed(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    assert plan["planned_actions"] == {"create": 0, "update": 0, "delete": 0}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "credential_issuance": "FORBIDDEN",
        "operations": {
            operation: "FORBIDDEN" for operation in generator.NATIVE_OPERATIONS
        },
    }


def test_generated_document_and_verification_boundary_are_non_executable(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    assert plan["document"] == {
        "id": "RAOS-GITHUB-OIDC-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-1504",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": ("SOURCE_DERIVED_NON_EXECUTABLE_GITHUB_OIDC_REFERENCE_PLAN"),
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }
    assert plan["verification_boundary"] == {
        "executable_workflow": "ABSENT",
        "iam_trust_policy": "ABSENT",
        "github_repository": "UNSET",
        "github_environment": "UNSET",
        "aws_account": "UNSET",
        "aws_role": "UNSET",
        "credentials": "ABSENT",
        "credential_issuance": "NOT_EXECUTED",
        "native_iac_validation": "NOT_EXECUTED",
        "workflow_inspection": "NOT_EXECUTED",
        "formal_tst_026": "NOT_EXECUTED",
        "hosted_github_aws": "NOT_EXECUTED",
        "live_oidc": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    }


def test_source_pins_match_regular_files() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_digest


def test_generated_json_matches_strict_renderer(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert path.is_file()
    assert not path.is_symlink()
    assert json.loads(path.read_bytes()) == generator.reference_plan_document(
        github_oidc_model
    )


def test_deployment_identity_directory_contains_only_reference_json() -> None:
    directory = REPOSITORY_ROOT / "infra/terraform/deployment-identity"
    assert sorted(path.name for path in directory.iterdir()) == [
        generator.REFERENCE_PLAN_PATH.name
    ]
    forbidden_suffixes = {".tf", ".tfvars", ".hcl", ".lock", ".yml", ".yaml"}
    assert not any(
        path.is_file() and path.suffix in forbidden_suffixes
        for path in directory.rglob("*")
    )


def test_contract_and_generated_inventory_are_closed(
    contract_document: dict[str, Any],
) -> None:
    assert set(contract_document) == generator.TOP_LEVEL_KEYS
    assert generator.GENERATED_PATHS == (
        Path("infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json"),
        Path("changes/st-1504/manifest.yaml"),
    )
