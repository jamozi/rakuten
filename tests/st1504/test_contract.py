"""Positive contract and reference-plan semantics for ST-1504."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1504_github_oidc as generator
from scripts.raos_build_core import input_hash_required


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_repository_inert_offline_model(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    assert github_oidc_model.contract["document"] == {
        "id": "RAOS-GITHUB-OIDC-DEPLOYMENT-001",
        "version": "2.0.0",
        "story_id": "ST-1504",
        "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        "formal_verification": "NOT_EXECUTED",
    }
    assert set(github_oidc_model.contract) == generator.TOP_LEVEL_KEYS


def test_direct_handoff_has_semantic_identity_without_hash_authority() -> None:
    path = REPOSITORY_ROOT / generator.DESIGN_HANDOFF_PATH
    handoff = generator.load_yaml(path)
    assert handoff["schema"] == "DESIGN_HANDOFF_V1"
    assert handoff["version"] == 1
    assert handoff["approved_story"] == "ST-1504"


def test_both_predecessors_are_exactly_bound_and_fail_closed(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    bindings = _mapping(github_oidc_model.contract["predecessor_bindings"])
    assert bindings == generator.EXPECTED_SECTIONS["predecessor_bindings"]
    governance = _mapping(bindings["pr_governance"])
    assert governance["required_desired_enforcement"] == "active"
    assert governance["required_remote_mutation"] == "FORBIDDEN"
    assert governance["required_bypass_actors"] == []
    controls = governance["required_protected_pr_controls"]
    assert controls["prohibit_deletion"] is True
    assert controls["prohibit_force_push"] is True
    assert controls["require_code_owner_review"] is False
    assert controls["require_last_push_approval"] is False
    foundation = _mapping(bindings["terraform_foundation"])
    assert foundation["required_provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
    )
    assert foundation["required_admission_status"] == "NOT_EVALUATED"
    assert foundation["required_eligible"] is False
    assert foundation["required_activation_status"] == "DISABLED"
    assert foundation["required_planned_actions"] == {
        "create": 0,
        "update": 0,
        "delete": 0,
    }


def test_pr_governance_predecessor_uses_v2_semantic_identity() -> None:
    contract_path = REPOSITORY_ROOT / "changes/st-0107/contracts/pr-governance.v1.yaml"
    desired_state_path = REPOSITORY_ROOT / "changes/st-0107/ruleset-policy.v1.json"
    contract = generator.load_yaml(contract_path)
    assert contract["document"]["id"] == "RAOS-PR-GOVERNANCE-002"
    assert contract["document"]["version"] == "2.0.0"
    desired_state = generator.load_json(desired_state_path)
    assert desired_state["document"]["id"] == "RAOS-GITHUB-RULESET-POLICY-002"
    assert desired_state["ruleset"]["required_status_checks"][0]["context"] == (
        "Final Integration"
    )
    assert desired_state_path.read_bytes() == (
        json.dumps(desired_state, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def test_github_is_fixed_source_without_selecting_target_provider(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    source = _mapping(plan["ci_source_boundary"])
    assert source == generator.EXPECTED_SECTIONS["ci_source_boundary"]
    assert source["ci_source"] == "GITHUB_ACTIONS"
    assert source["external_review_connector"] == "GITHUB"
    assert source["target_provider_selected"] is False
    path = _mapping(plan["logical_identity_path"])
    assert path["source"] == "GITHUB_ACTIONS_OIDC"
    assert path["destination"] == "PROVIDER_NEUTRAL_SHORT_LIVED_WORKLOAD_SESSION"
    assert path["target_provider"] == "UNSELECTED"
    assert path["github_source_is_target_provider_selection"] is False


def test_aws_is_current_canonical_reference_and_portable_paths_are_additional(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    reference = _mapping(plan["reference_architecture"])
    assert reference["cloud"] == "AWS"
    assert reference["region"] == "ap-northeast-1"
    assert reference["classification"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert reference["mappings"] == generator._aws_reference_mappings()
    admission = _mapping(plan["provider_neutral_deployment_identity_admission"])
    assert admission["aws_reference_boundary"]["role"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert admission["aws_reference_boundary"]["canonical_story_deliverables"] == (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    )
    assert (
        admission["aws_reference_boundary"]["non_aws_owner_managed_profiles"]
        == "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
    )
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        assert reference[field] is False


def test_provider_neutral_admission_requires_complete_exact_mapping(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    admission = _mapping(
        generator.reference_plan_document(github_oidc_model)[
            "provider_neutral_deployment_identity_admission"
        ]
    )
    assert admission["admission_status"] == "NOT_EVALUATED"
    assert admission["eligible"] is False
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        assert admission[field] is None
    assert admission["eligible_profile_kinds"] == list(generator.ELIGIBLE_PROFILE_KINDS)
    mapping_policy = _mapping(admission["mapping_policy"])
    assert mapping_policy["configured_mapping_count"] == 0
    assert mapping_policy["complete_mapping"] is False
    assert mapping_policy["required_capability_count"] == len(
        generator.DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES
    )
    for field in (
        "missing_mapping",
        "unknown_mapping",
        "duplicate_mapping",
        "implicit_mapping",
        "partial_mapping",
        "provider_label_only_mapping",
        "aws_label_only_mapping",
        "source_label_only_mapping",
        "reference_only_mapping",
    ):
        assert mapping_policy[field] == "REJECT"
    rows = admission["capability_mapping_requirements"]
    assert [row["capability_id"] for row in rows] == [
        capability_id
        for capability_id, _outcome in (
            generator.DEPLOYMENT_IDENTITY_CAPABILITY_OUTCOMES
        )
    ]
    assert all(
        row["selected_mapping"] is None
        and row["evidence_refs"] == []
        and row["mapping_status"] == "REQUIRED_NOT_CONFIGURED"
        for row in rows
    )
    assert admission["evidence_equivalence_policy"] == {
        "identical_security_evidence": "REQUIRED",
        "identical_operations_evidence": "REQUIRED",
        "identical_release_evidence": "REQUIRED",
        "identical_provenance_evidence": "REQUIRED",
        "identical_audit_evidence": "REQUIRED",
        "identical_revocation_rollback_evidence": "REQUIRED",
        "identical_identity_session_evidence": "REQUIRED",
        "identical_isolation_residency_evidence": "REQUIRED",
        "provider_label_as_evidence": "FORBIDDEN",
        "aws_label_as_evidence": "FORBIDDEN",
        "github_source_label_as_evidence": "FORBIDDEN",
        "reference_metadata_as_evidence": "FORBIDDEN",
        "local_test_as_live_evidence": "FORBIDDEN",
    }


def test_every_actual_binding_remains_null_or_empty(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    selected = _mapping(
        generator.reference_plan_document(github_oidc_model)["selected_bindings"]
    )
    assert set(selected) == set(generator._selected_bindings())
    assert all(value is None or value == [] for value in selected.values())


def test_trust_credential_and_approval_boundaries_fail_closed(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    trust = _mapping(plan["trust_constraints"])
    assert trust["required_claim_bindings"] == list(generator.REQUIRED_CLAIM_BINDINGS)
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
        "broad_audience",
    ):
        assert trust[field] == "FORBIDDEN"
    credentials = _mapping(plan["credential_boundary"])
    for field in (
        "long_lived_cloud_key",
        "static_provider_credential",
        "repository_secret_cloud_credential",
        "human_cloud_credential",
        "role_chaining",
        "privilege_escalation",
        "cross_environment_identity_reuse",
    ):
        assert credentials[field] == "FORBIDDEN"
    assert credentials["credential_material"] == "ABSENT"
    assert credentials["credential_issuance_capability"] == "ABSENT"
    protection = _mapping(plan["environment_protection"])
    for field in (
        "self_approval",
        "approval_bypass",
        "deployment_without_approval",
        "cross_environment_target_reuse",
    ):
        assert protection[field] == "FORBIDDEN"
    lifecycle = _mapping(plan["lifecycle_controls"])
    for field in (
        "audit_bypass",
        "revocation_bypass",
        "rollback_bypass",
        "irreversible_promotion",
    ):
        assert lifecycle[field] == "FORBIDDEN"


def test_open_decisions_execution_and_evidence_remain_unexecuted(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    plan = generator.reference_plan_document(github_oidc_model)
    assert (
        plan["open_decision_boundary"]
        == generator.EXPECTED_SECTIONS["open_decision_boundary"]
    )
    assert plan["planned_actions"] == {"create": 0, "update": 0, "delete": 0}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "credential_issuance": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "operations": {
            operation: "FORBIDDEN" for operation in generator.NATIVE_OPERATIONS
        },
    }
    verification = _mapping(plan["verification_boundary"])
    assert verification == {
        key: value
        for key, value in generator.EXPECTED_SECTIONS["evidence_boundary"].items()
        if key != "deliverable_classification"
    }
    assert verification["formal_tst_026"] == "NOT_EXECUTED"
    assert verification["hosted_github_target_provider"] == "NOT_EXECUTED"
    assert verification["live_oidc_federation"] == "NOT_EXECUTED"
    assert verification["production"] == "NOT_EXECUTED"


def test_generated_reference_document_and_harness_authority_are_non_executable(
    github_oidc_model: generator.GithubOidcModel,
) -> None:
    document = _mapping(
        generator.reference_plan_document(github_oidc_model)["document"]
    )
    assert document["version"] == "2.0.0"
    assert document["artifact_kind"] == (
        "SOURCE_DERIVED_REPOSITORY_INERT_PROVIDER_NEUTRAL_OFFLINE_"
        "DEPLOYMENT_IDENTITY_HARNESS"
    )
    assert document["executable"] is False
    assert document["harness_execution"] == "OFFLINE_RECORDED_FIXTURE_ONLY"


def test_source_pins_match_regular_files() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        if input_hash_required(relative):
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


def test_deployment_identity_directory_contains_only_owned_inert_fixture_set() -> None:
    directory = REPOSITORY_ROOT / "infra/terraform/deployment-identity"
    assert sorted(path.name for path in directory.iterdir()) == [
        path.name for path in sorted(generator.GENERATED_NON_MANIFEST_PATHS)
    ]
    forbidden_suffixes = {".tf", ".tfvars", ".hcl", ".lock"}
    assert not any(
        path.is_file() and path.suffix in forbidden_suffixes
        for path in directory.rglob("*")
    )
    assert not (REPOSITORY_ROOT / ".github/workflows/st1504.yml").exists()
    assert generator.WORKFLOW_FIXTURE_PATH.parts[:3] == (
        "infra",
        "terraform",
        "deployment-identity",
    )


def test_contract_and_generated_inventory_are_closed(
    contract_document: dict[str, Any],
) -> None:
    assert set(contract_document) == generator.TOP_LEVEL_KEYS
    assert generator.GENERATED_PATHS == (
        Path("infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json"),
        Path("infra/terraform/deployment-identity/github-oidc.claims.recorded.v1.json"),
        Path(
            "infra/terraform/deployment-identity/"
            "github-oidc.trust-policy.recorded.v1.json"
        ),
        Path(
            "infra/terraform/deployment-identity/"
            "github-oidc.evaluation.recorded.v1.json"
        ),
        Path(
            "infra/terraform/deployment-identity/"
            "github-oidc-deploy.disabled.workflow.yml"
        ),
        Path("changes/st-1504/manifest.yaml"),
    )
