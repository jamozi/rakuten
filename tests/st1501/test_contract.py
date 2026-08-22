"""Positive contract and reference-plan semantics for ST-1501."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts import build_st1501_terraform_foundation as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_contract_loads_into_closed_reference_only_model(
    foundation_model: generator.FoundationModel,
) -> None:
    assert foundation_model.reference == generator.ReferenceArchitecture(
        cloud="AWS",
        region="ap-northeast-1",
        classification="CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        inherited_from="INT-DEC-007",
        portable_core_required=True,
        default=False,
        implicit_fallback=False,
        selected_binding=False,
        eligibility_shortcut=False,
        admission_requirement=False,
        evidence_substitute=False,
    )
    assert foundation_model.selection == generator.SelectedConfiguration(
        cloud_provider=None,
        production_region=None,
        backup_region=None,
        development_account_id=None,
        production_account_id=None,
        terraform_cli_version=None,
        provider_plugins=(),
        state_backend=None,
        credential_source=None,
        network_cidrs=(),
        availability_zones=(),
        kms_key_reference=None,
        monthly_budget_jpy=None,
        resource_definitions=(),
    )


def test_current_canonical_reference_is_not_a_selected_cloud_configuration(
    foundation_model: generator.FoundationModel,
) -> None:
    plan = generator.reference_plan_document(foundation_model)
    assert plan["reference_architecture"] == {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "inherited_from": "INT-DEC-007",
        "portable_core_required": True,
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    }
    assert plan["selected_configuration"] == {
        "cloud_provider": None,
        "production_region": None,
        "backup_region": None,
        "development_account_id": None,
        "production_account_id": None,
        "terraform_cli_version": None,
        "provider_plugins": [],
        "state_backend": None,
        "credential_source": None,
        "network_cidrs": [],
        "availability_zones": [],
        "kms_key_reference": None,
        "monthly_budget_jpy": None,
        "resource_definitions": [],
    }


def test_provider_neutral_foundation_admission_is_closed_and_unselected(
    foundation_model: generator.FoundationModel,
) -> None:
    admission = generator.reference_plan_document(foundation_model)[
        "provider_neutral_foundation_admission"
    ]
    assert admission["classification"] == (
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
    )
    assert admission["admission_status"] == "NOT_EVALUATED"
    assert admission["eligible"] is False
    assert admission["selected_profile_id"] is None
    assert admission["selected_profile_kind"] is None
    assert admission["selected_provider_name"] is None
    assert admission["default_profile_id"] is None
    assert admission["fallback_profile_id"] is None
    assert admission["eligible_profile_kinds"] == list(generator.ELIGIBLE_PROFILE_KINDS)
    assert admission["binding_policy"] == {
        **{
            name: {"selected": None, "default": None, "fallback": None}
            for name in generator.FOUNDATION_BINDING_NAMES
        },
        "implicit_binding": "FORBIDDEN",
        "name_or_reference_only_eligibility": "FORBIDDEN",
    }
    assert admission["mapping_policy"] == {
        "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
        "required_capability_count": 10,
        "configured_mapping_count": 0,
        "complete_mapping": False,
        "missing_mapping": "REJECT",
        "unknown_mapping": "REJECT",
        "duplicate_mapping": "REJECT",
        "implicit_mapping": "REJECT",
        "partial_mapping": "REJECT",
        "provider_label_only_mapping": "REJECT",
    }
    rows = admission["capability_mapping_requirements"]
    assert [row["capability_id"] for row in rows] == list(
        generator.REQUIRED_FOUNDATION_CAPABILITY_IDS
    )
    assert [row["required_outcome"] for row in rows] == [
        outcome for _capability_id, outcome in generator.FOUNDATION_CAPABILITY_OUTCOMES
    ]
    assert all(row["selected_mapping"] is None for row in rows)
    assert all(row["evidence_refs"] == [] for row in rows)
    assert all(row["mapping_status"] == "REQUIRED_NOT_CONFIGURED" for row in rows)


def test_aws_reference_cannot_supply_foundation_admission_or_evidence(
    foundation_model: generator.FoundationModel,
) -> None:
    admission = generator.reference_plan_document(foundation_model)[
        "provider_neutral_foundation_admission"
    ]
    assert admission["aws_reference_boundary"] == {
        "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "canonical_story_deliverables": (
            "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
        ),
        "non_aws_owner_managed_profiles": "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS",
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    }
    assert admission["evidence_equivalence_policy"] == {
        "identical_security_evidence": "REQUIRED",
        "identical_operations_evidence": "REQUIRED",
        "identical_release_evidence": "REQUIRED",
        "identical_backup_restore_evidence": "REQUIRED",
        "identical_region_residency_evidence": "REQUIRED",
        "provider_label_as_evidence": "FORBIDDEN",
        "reference_metadata_as_evidence": "FORBIDDEN",
        "local_test_as_live_evidence": "FORBIDDEN",
    }


def test_activation_native_operations_and_action_counts_are_fail_closed(
    foundation_model: generator.FoundationModel,
) -> None:
    plan = generator.reference_plan_document(foundation_model)
    assert plan["planned_actions"] == {"create": 0, "update": 0, "delete": 0}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "native_commands": {
            "init": "FORBIDDEN",
            "plan": "FORBIDDEN",
            "apply": "FORBIDDEN",
            "destroy": "FORBIDDEN",
            "import": "FORBIDDEN",
            "refresh": "FORBIDDEN",
        },
    }


def test_future_state_account_and_production_requirements_are_unconfigured(
    foundation_model: generator.FoundationModel,
) -> None:
    requirements = generator.reference_plan_document(foundation_model)[
        "future_requirements"
    ]
    assert requirements == {
        "remote_state": {
            "encryption": "REQUIRED_NOT_CONFIGURED",
            "locking": "REQUIRED_NOT_CONFIGURED",
            "audit_logging": "REQUIRED_NOT_CONFIGURED",
            "backup_and_restore": "REQUIRED_NOT_CONFIGURED",
            "selected_backend": None,
        },
        "account_separation": {
            "requirement": "REQUIRED",
            "development_account_id": None,
            "production_account_id": None,
        },
        "production_change_control": {
            "iac_only": "REQUIRED",
            "human_approval": "REQUIRED",
            "drift_detection": "REQUIRED_NOT_CONFIGURED",
            "manual_change": "FORBIDDEN",
            "od_013_status": "HUMAN_DECISION_REQUIRED",
            "production_apply": "FORBIDDEN",
        },
    }


def test_successors_require_separate_contract_revision_before_resources(
    foundation_model: generator.FoundationModel,
) -> None:
    extension = generator.reference_plan_document(foundation_model)[
        "extension_contract"
    ]
    assert extension == {
        "current_resource_payloads": "FORBIDDEN",
        "successor_contract_revision_required": True,
        "native_toolchain_pin_required_before_hcl": True,
        "successors": {
            "ST-1502": "DATA_SERVICES",
            "ST-1503": "COMPUTE_CDN_WAF",
        },
    }


def test_generated_document_is_non_executable_partial_local_code(
    foundation_model: generator.FoundationModel,
) -> None:
    document = generator.reference_plan_document(foundation_model)["document"]
    assert document == {
        "id": "RAOS-TERRAFORM-FOUNDATION-REFERENCE-PLAN-001",
        "version": "1.1.0",
        "story_id": "ST-1501",
        "source_contract": generator.SOURCE_CONTRACT_URI,
        "generated_by": generator.GENERATOR_URI,
        "generation_command": generator.GENERATION_COMMAND,
        "artifact_kind": "SOURCE_DERIVED_REFERENCE_STATE_PLAN",
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }


def test_verification_boundary_keeps_native_formal_and_live_work_unexecuted(
    foundation_model: generator.FoundationModel,
) -> None:
    boundary = generator.reference_plan_document(foundation_model)[
        "verification_boundary"
    ]
    assert boundary == {
        "executable_terraform": "ABSENT",
        "terraform_cli": "UNPINNED_NOT_INVOKED",
        "provider_plugins": "UNPINNED_NOT_INVOKED",
        "remote_state": "NOT_CONFIGURED",
        "provider_account_or_project": "UNSET",
        "credentials": "ABSENT",
        "formal_tst_026": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    }


def test_source_pins_match_current_regular_files() -> None:
    for relative, expected_digest in generator.PINNED_SOURCES.items():
        path = REPOSITORY_ROOT / relative
        assert path.is_file()
        assert not path.is_symlink()
        assert generator.sha256_file(path) == expected_digest


def test_direct_owner_handoff_is_hash_pinned_and_semantically_valid() -> None:
    assert generator.DESIGN_HANDOFF_PATH in generator.SOURCE_ARTIFACT_PATHS
    assert generator.PINNED_SOURCES[
        generator.DESIGN_HANDOFF_PATH.as_posix()
    ] == generator.sha256_file(REPOSITORY_ROOT / generator.DESIGN_HANDOFF_PATH)
    generator.load_and_validate_contract(REPOSITORY_ROOT)


def test_generated_json_is_strictly_parseable_and_matches_renderer(
    foundation_model: generator.FoundationModel,
) -> None:
    path = REPOSITORY_ROOT / generator.REFERENCE_PLAN_PATH
    assert path.is_file()
    assert not path.is_symlink()
    parsed = json.loads(path.read_bytes())
    assert parsed == generator.reference_plan_document(foundation_model)


def test_foundation_directory_contains_no_native_iac_payload() -> None:
    foundation = REPOSITORY_ROOT / "infra/terraform/foundation"
    assert foundation.is_dir()
    assert sorted(path.name for path in foundation.iterdir()) == [
        generator.REFERENCE_PLAN_PATH.name
    ]
    forbidden_suffixes = {".tf", ".tfvars", ".hcl", ".lock"}
    assert not any(
        path.is_file() and path.suffix in forbidden_suffixes
        for path in foundation.rglob("*")
    )


def test_contract_top_level_schema_is_closed(
    contract_document: dict[str, Any],
) -> None:
    assert set(contract_document) == generator.TOP_LEVEL_KEYS
    assert set(contract_document["selected_configuration"]) == (
        generator.SELECTION_KEYS
    )
    assert generator.GENERATED_PATHS == (
        Path("infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"),
        Path("changes/st-1501/manifest.yaml"),
    )
