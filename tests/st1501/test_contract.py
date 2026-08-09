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
        classification="REFERENCE_METADATA_ONLY",
        portable_core_required=True,
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


def test_reference_metadata_is_not_a_selected_cloud_configuration(
    foundation_model: generator.FoundationModel,
) -> None:
    plan = generator.reference_plan_document(foundation_model)
    assert plan["reference_architecture"] == {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "REFERENCE_METADATA_ONLY",
        "portable_core_required": True,
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


def test_activation_native_operations_and_action_counts_are_fail_closed(
    foundation_model: generator.FoundationModel,
) -> None:
    plan = generator.reference_plan_document(foundation_model)
    assert plan["planned_actions"] == {"create": 0, "update": 0, "delete": 0}
    assert plan["activation"] == {
        "enabled": False,
        "status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
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
        "version": "1.0.0",
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
        "aws_account": "UNSET",
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
