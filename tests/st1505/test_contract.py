"""Positive provider-neutral contract semantics for ST-1505."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import build_st1505_staging_deployment as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HANDOFF_PATH = Path(
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml"
)
TOP_LEVEL_KEYS = (
    "document",
    "sources",
    "predecessor_bindings",
    "reference_architecture",
    "provider_neutral_staging_admission",
    "open_decision_boundary",
    "environment_boundary",
    "selected_bindings",
    "artifact_admission_intent",
    "protected_environment_intent",
    "migration_intent",
    "health_security_runtime_intent",
    "transport_security_intent",
    "observability_alerting_intent",
    "isolation_residency_budget_intent",
    "target_adapter_intent",
    "rollback_restore_intent",
    "logical_phases",
    "execution_boundary",
    "evidence_boundary",
)

DEPENDENCY_POLICIES = {
    "ST-1501": "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
    "ST-1502": "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION",
    "ST-1503": "STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION",
    "ST-1504": "STRICT_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY_CAPABILITY_ADMISSION",
}

CAPABILITY_OUTCOMES = {
    "provider_neutral_foundation_profile": (
        "COMPLETE_FOUNDATION_MAPPING_AND_EQUIVALENT_SECURITY_OPERATIONS_RELEASE_"
        "RECOVERY_RESIDENCY_EVIDENCE"
    ),
    "provider_neutral_data_services_profile": (
        "COMPLETE_POSTGRES_OBJECT_QUEUE_SECRET_RECOVERY_OBSERVABILITY_ISOLATION_"
        "RESIDENCY_MAPPING"
    ),
    "provider_neutral_compute_edge_profile": (
        "COMPLETE_RUNTIME_EDGE_DNS_TLS_WAF_ISOLATION_IDENTITY_HEALTH_RESIDENCY_MAPPING"
    ),
    "provider_neutral_deployment_identity_profile": (
        "COMPLETE_EXACT_SUBJECT_SHORT_LIVED_IDENTITY_APPROVAL_AUDIT_REVOCATION_MAPPING"
    ),
    "immutable_build_sbom_scan_and_provenance": (
        "BUILD_ONCE_IMMUTABLE_DIGEST_SBOM_SCAN_SIGNED_PROVENANCE_AND_PROMOTION_"
        "WITHOUT_REBUILD"
    ),
    "migration_compatibility_and_dry_run": (
        "EXPAND_MIGRATE_CONTRACT_DRY_RUN_LOCK_COMPATIBILITY_AND_FORWARD_FIX_EVIDENCE"
    ),
    "protected_environment_human_approval": (
        "EXACT_REPOSITORY_REF_WORKFLOW_ENVIRONMENT_AUDIENCE_SUBJECT_AND_"
        "INDEPENDENT_HUMAN_APPROVAL"
    ),
    "smoke_security_and_runtime_verification": (
        "LIVENESS_READINESS_DEPENDENCY_MIGRATION_ISOLATION_SMOKE_SECURITY_RUNTIME_"
        "AND_BROWSER_EVIDENCE"
    ),
    "cross_capability_transport_security": (
        "AUTHENTICATED_ENCRYPTED_DOWNGRADE_RESISTANT_TRANSPORT_FOR_ALL_STAGING_"
        "NETWORK_FLOWS"
    ),
    "observability_alerting_and_release_markers": (
        "TRACES_METRICS_LOGS_RELEASE_MARKERS_SLO_ALERT_ROUTES_AND_NOTIFICATION_EVIDENCE"
    ),
    "rollback_restore_and_recovery_readiness": (
        "PRIOR_ARTIFACT_CONFIGURATION_SNAPSHOT_MIGRATION_COMPATIBILITY_RESTORE_"
        "INTEGRITY_AND_ROLLBACK_EVIDENCE"
    ),
    "isolation_region_residency_and_budget_controls": (
        "ENVIRONMENT_TENANT_DATA_PLANE_SURFACE_ISOLATION_REGION_RESIDENCY_BUDGET_"
        "ALERT_AND_STOP_EVIDENCE"
    ),
    "provider_neutral_target_adapter": (
        "EXPLICIT_PROVIDER_NEUTRAL_TARGET_ADAPTER_MAPPING_WITH_IDENTICAL_SECURITY_"
        "OPERATIONS_AND_RELEASE_EVIDENCE"
    ),
}

PREDECESSORS = {
    "foundation": {
        "story_id": "ST-1501",
        "owner_generator_uri": "repo://scripts/build_st1501_terraform_foundation.py",
        "owner_generator_sha256": (
            "ca5bf43cb45578207678f7afcce77cab01a9e54b34f45a3f1c9a5f4f417aa7cb"
        ),
        "handoff_uri": (
            "repo://changes/st-1501/"
            "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
        ),
        "handoff_sha256": (
            "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f"
        ),
        "handoff_semantic_sha256": (
            "e20e03d89693bc8ad7adfffcc515eb656ec11375c2a304aa58ab0e30b8fe4722"
        ),
        "contract_uri": (
            "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "5f13094d18dfbece65ccf36a68928fc9d602d316068aa5f1b538f14d90136e1e"
        ),
        "contract_semantic_sha256": (
            "9e88addbfe93c6d6754111d508ba1d7461a703c2aa6b329fa319b6566d9a55e1"
        ),
        "plan_uri": (
            "repo://infra/terraform/foundation/"
            "terraform-foundation.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "bb5a6bb86ab13cf465a980eccea75bc3742eb818af142dc74ba6cea90aef6a72"
        ),
        "plan_semantic_sha256": (
            "1deb0efe9ff2d99ccc27ad6f50d1a07c6ed13b6c45cdd6914a7fdcd1a0edbf20"
        ),
        "action_counts": {"create": 0, "update": 0, "delete": 0},
    },
    "data_services": {
        "story_id": "ST-1502",
        "owner_generator_uri": "repo://scripts/build_st1502_data_services.py",
        "owner_generator_sha256": (
            "73876b415aba2f7160d94dbe8df113087d4bf5be27b4830b82425b34f6ea6abe"
        ),
        "handoff_uri": (
            "repo://changes/st-1502/"
            "DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml"
        ),
        "handoff_sha256": (
            "2826ec76994e6fb1d4e1c41bc0ce7affecc96351d1fcf527e45c2909bb89f97c"
        ),
        "handoff_semantic_sha256": (
            "0d1069b18729a8997e81cdbe1edc40f770348adea10cb12349d9b915547d5845"
        ),
        "contract_uri": (
            "repo://changes/st-1502/contracts/data-services-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "89a0f1e7babfceffd2b270bc3a16f5d74fbeb6b62699e03156c860c9ae16c7e1"
        ),
        "contract_semantic_sha256": (
            "6339ecf8ba6846efb3efdea69ecba3ef74cb5280a70838c735f3778c3bb0079b"
        ),
        "plan_uri": (
            "repo://infra/terraform/data-services/data-services.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "2d52d7b99a4edda75814af603e48016f06fa34507bc221e3f573379c066f35c5"
        ),
        "plan_semantic_sha256": (
            "abce483dc017145c1511bbe82f3a5fb055f99ff12636e1fddfffa6bd19f6efdc"
        ),
        "action_counts": {
            "create": 0,
            "update": 0,
            "delete": 0,
            "migrate": 0,
            "backup": 0,
            "restore": 0,
            "redrive": 0,
            "rotate": 0,
        },
    },
    "compute_edge": {
        "story_id": "ST-1503",
        "owner_generator_uri": "repo://scripts/build_st1503_compute_edge.py",
        "owner_generator_sha256": (
            "a19e6eec9dac3c5f46b34538189bc2cac95836e57762925d53823f9948497d27"
        ),
        "handoff_uri": (
            "repo://changes/st-1503/"
            "DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml"
        ),
        "handoff_sha256": (
            "2a6da0fa771153cafe2aa79f01b09843832e032ec13a29dd34884a31ae0c519d"
        ),
        "handoff_semantic_sha256": (
            "ad5e207a8f201d0ccdff72670a0f1cd7d90ba76f3e52ad7e51db2eb96d0dd707"
        ),
        "contract_uri": (
            "repo://changes/st-1503/contracts/compute-edge-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "682ab350c5036bf8697a99f08269d5d6db1aaff7387ca8401db07b9d811b1c08"
        ),
        "contract_semantic_sha256": (
            "344fc69777a14c50fef91fff3fa4c3d724136ae414039b4a1659383ea7f4acc1"
        ),
        "plan_uri": (
            "repo://infra/terraform/compute-edge/compute-edge.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "1ac46b4ac6a779f41776c10f69416c05e770f2119fb1ce3b6898c11d7e1295ee"
        ),
        "plan_semantic_sha256": (
            "a0100d4256e39d6aed035010534a00c8373c2f916b182eb7d6cd13265d8287a4"
        ),
        "action_counts": {"create": 0, "update": 0, "delete": 0},
    },
    "deployment_identity": {
        "story_id": "ST-1504",
        "owner_generator_uri": "repo://scripts/build_st1504_github_oidc.py",
        "owner_generator_sha256": (
            "4e7ff7664326a754b89039bb4c5fcd399e629c3197814da5b79260a54d01bdb0"
        ),
        "handoff_uri": (
            "repo://changes/st-1504/"
            "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml"
        ),
        "handoff_sha256": (
            "36ac3095033f8ad7c91deac77f6a6689d354dc63dd46f03350e0bf68b3ccca04"
        ),
        "handoff_semantic_sha256": (
            "e26a0bbedb909530587462881a96e8b85b7bfdb93aedc57e281eda9d4d043282"
        ),
        "contract_uri": (
            "repo://changes/st-1504/contracts/github-oidc-deployment.v1.yaml"
        ),
        "contract_sha256": (
            "20558e50a78c5d8be62a553858445578cc3fdd39fd285de3a92fe5cd5b5d9257"
        ),
        "contract_semantic_sha256": (
            "0eac1cba01ca2218f4f9adf734f58e748bf8c355425427516aab1d79d17bc91f"
        ),
        "plan_uri": (
            "repo://infra/terraform/deployment-identity/"
            "github-oidc.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "7316a9f71cfea72edf071757ead8b44403362d106eb986d146193a27d658d6e6"
        ),
        "plan_semantic_sha256": (
            "38e1e8bc7a500ca9961c78949c6697fbadf099d3378822731b3fc72a24b35e3e"
        ),
        "action_counts": {"create": 0, "update": 0, "delete": 0},
    },
}

PHASE_NAMES = (
    "PREDECESSOR_CAPABILITY_ADMISSION",
    "TARGET_ADAPTER_ADMISSION",
    "ARTIFACT_ADMISSION",
    "PROTECTED_ENVIRONMENT_APPROVAL_GATE",
    "MIGRATION_COMPATIBILITY_GATE",
    "INDEPENDENT_MIGRATION_REVIEW_GATE",
    "TRANSPORT_SECURITY_GATE",
    "ROLLBACK_RESTORE_READINESS_GATE",
    "ARTIFACT_PROMOTION",
    "STAGING_DEPLOYMENT",
    "MIGRATION_DRY_RUN_GATE",
    "MIGRATE",
    "OBSERVABILITY_ALERT_GATE",
    "STAGING_SMOKE_SECURITY_RUNTIME_GATE",
    "ROLLBACK_RESTORE_GATE",
    "RELEASE_EVIDENCE_GATE",
)

ACTION_COUNT_NAMES = (
    "create",
    "update",
    "delete",
    "build",
    "promote",
    "approve",
    "deploy",
    "migrate",
    "migration_review",
    "smoke",
    "security",
    "runtime",
    "browser",
    "transport_security",
    "telemetry",
    "alert",
    "rollback",
    "restore",
    "release",
    "production",
)

OPERATION_NAMES = (
    "dependency_admission",
    "target_adapter_call",
    "artifact_build",
    "artifact_promote",
    "environment_approval",
    "deploy",
    "migration_dry_run",
    "migration_review",
    "migrate",
    "smoke",
    "security_check",
    "runtime_check",
    "browser",
    "transport_security_check",
    "telemetry_write",
    "alert_route_write",
    "rollback",
    "restore",
    "release",
    "production",
)


def _mapping(value: object) -> dict[str, Any]:
    assert isinstance(value, dict)
    return cast(dict[str, Any], value)


def test_contract_loads_as_closed_provider_neutral_v1_1_model(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    assert tuple(staging_model.contract) == TOP_LEVEL_KEYS
    assert staging_model.contract["document"] == {
        "id": "RAOS-STAGING-DEPLOYMENT-001",
        "version": "1.1.0",
        "story_id": "ST-1505",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }


def test_design_handoff_uses_semantic_identity_without_hash_authority(
    contract_document: dict[str, Any],
) -> None:
    handoff_file = REPOSITORY_ROOT / HANDOFF_PATH
    assert handoff_file.is_file()
    assert not handoff_file.is_symlink()
    handoff = generator.load_yaml(handoff_file)
    assert handoff["schema"] == "DESIGN_HANDOFF_V1"
    assert handoff["version"] == 1
    assert handoff["approved_story"] == "ST-1505"

    source_rows = cast(list[dict[str, object]], contract_document["sources"])
    matching_rows = [
        row for row in source_rows if row["uri"] == f"repo://{HANDOFF_PATH.as_posix()}"
    ]
    assert len(matching_rows) == 1

    decision = _mapping(_mapping(handoff)["decision"])
    assert decision["staging_provider_policy"] == (
        "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION"
    )
    assert decision["selected_profile"] is None
    assert decision["default_profile"] is None
    assert decision["fallback_profile"] is None
    assert decision["concrete_alternate_provider_selected"] is False
    assert decision["eligible_profile_kinds"] == [
        "AWS",
        "OTHER_CLOUD",
        "OWNER_MANAGED_INFRASTRUCTURE",
    ]
    assert decision["required_dependency_stories"] == list(DEPENDENCY_POLICIES)
    assert decision["required_capability_ids"] == list(CAPABILITY_OUTCOMES)


def test_all_four_predecessors_are_semantic_owner_and_safety_bound(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    bindings = _mapping(staging_model.contract["predecessor_bindings"])
    assert tuple(bindings) == tuple(PREDECESSORS)
    for name, expected in PREDECESSORS.items():
        row = _mapping(bindings[name])
        story_id = cast(str, expected["story_id"])
        assert row["story_id"] == story_id
        assert (
            row["owner_id"]
            == {
                "ST-1501": "build_st1501_terraform_foundation",
                "ST-1502": "build_st1502_data_services",
                "ST-1503": "build_st1503_compute_edge",
                "ST-1504": "build_st1504_github_oidc",
            }[story_id]
        )
        assert row["owner_version"] == 2
        assert row["owner_generator_uri"] == expected["owner_generator_uri"]
        assert row["design_handoff_uri"] == expected["handoff_uri"]
        assert row["contract_uri"] == expected["contract_uri"]
        assert row["reference_plan_uri"] == expected["plan_uri"]
        assert row["required_provider_policy"] == DEPENDENCY_POLICIES[story_id]
        assert row["required_admission_status"] == "NOT_EVALUATED"
        assert row["required_eligible"] is False
        assert row["required_complete_mapping"] is False
        assert row["required_selected_values"] == "UNSET"
        assert row["required_activation_status"] == "DISABLED"
        assert row["required_network_access"] == "FORBIDDEN"
        assert row["required_credential_access"] == "FORBIDDEN"
        assert row["required_live_provider_calls"] == "FORBIDDEN"
        assert row["required_external_writes"] == "FORBIDDEN"
        assert row["required_reference_plan_executable"] is (
            story_id in {"ST-1501", "ST-1502"}
        )
        assert row["required_action_counts"] == expected["action_counts"]
    assert bindings["deployment_identity"]["required_credential_issuance"] == (
        "FORBIDDEN"
    )


def test_provider_neutral_admission_requires_exact_dependencies_and_mappings(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    admission = _mapping(staging_model.contract["provider_neutral_staging_admission"])
    assert admission["classification"] == (
        "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION"
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
    assert admission["concrete_alternate_provider_selected"] is False
    assert admission["eligible_profile_kinds"] == [
        "AWS",
        "OTHER_CLOUD",
        "OWNER_MANAGED_INFRASTRUCTURE",
    ]
    assert admission["eligibility_condition"] == (
        "COMPLETE_EXACT_DEPENDENCY_AND_CAPABILITY_MAPPING_WITH_EQUIVALENT_EVIDENCE"
    )
    assert admission["dependency_admission_policy"] == {
        "required_dependency_count": 4,
        "satisfied_dependency_count": 0,
        "all_dependencies_satisfied": False,
        "exact_provider_neutral_admission_required": True,
        "complete_predecessor_mapping_required": True,
        "equivalent_predecessor_evidence_required": True,
        "missing_dependency": "REJECT",
        "unknown_dependency": "REJECT",
        "duplicate_dependency": "REJECT",
        "partial_dependencies": "REJECT",
        "provider_label_only_dependency": "REJECT",
        "predecessor_completion_only": "REJECT",
        "canonical_reference_architecture_status_only": "REJECT",
    }
    assert admission["mapping_policy"] == {
        "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
        "required_capability_count": 13,
        "configured_mapping_count": 0,
        "complete_mapping": False,
        "missing_mapping": "REJECT",
        "unknown_mapping": "REJECT",
        "duplicate_mapping": "REJECT",
        "implicit_mapping": "REJECT",
        "partial_mapping": "REJECT",
        "provider_label_only_mapping": "REJECT",
        "aws_label_only_mapping": "REJECT",
        "service_label_only_mapping": "REJECT",
        "predecessor_only_mapping": "REJECT",
        "reference_only_mapping": "REJECT",
    }
    assert admission["binding_policy"] == {
        "selected_target_profile": None,
        "default_target_profile": None,
        "fallback_target_profile": None,
        "implicit_target_binding": "FORBIDDEN",
        "provider_name_or_reference_eligibility": "FORBIDDEN",
        "predecessor_name_or_completion_eligibility": "FORBIDDEN",
    }


def test_dependency_and_capability_admission_rows_are_complete_and_unselected(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    admission = _mapping(staging_model.contract["provider_neutral_staging_admission"])
    dependencies = cast(
        list[dict[str, object]], admission["dependency_admission_requirements"]
    )
    assert [row["story_id"] for row in dependencies] == list(DEPENDENCY_POLICIES)
    for row in dependencies:
        story_id = cast(str, row["story_id"])
        assert row == {
            "story_id": story_id,
            "required_policy": DEPENDENCY_POLICIES[story_id],
            "current_admission_status": "NOT_EVALUATED",
            "current_eligible": False,
            "selected_profile_id": None,
            "selected_provider_name": None,
            "evidence_references": [],
            "dependency_status": "REQUIRED_NOT_SATISFIED",
        }

    mappings = cast(
        list[dict[str, object]], admission["capability_mapping_requirements"]
    )
    assert [row["capability_id"] for row in mappings] == list(CAPABILITY_OUTCOMES)
    for row in mappings:
        capability_id = cast(str, row["capability_id"])
        assert row == {
            "capability_id": capability_id,
            "required_outcome": CAPABILITY_OUTCOMES[capability_id],
            "selected_mapping": None,
            "evidence_references": [],
            "mapping_status": "REQUIRED_NOT_CONFIGURED",
        }


def test_aws_remains_current_canonical_reference_without_admission_shortcut(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    reference = _mapping(staging_model.contract["reference_architecture"])
    assert reference["cloud"] == "AWS"
    assert reference["region"] == "ap-northeast-1"
    assert reference["classification"] == (
        "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    )
    assert reference["inherited_from"] == "INT-DEC-007"
    assert reference["portable_core_required"] is True
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        assert reference[field] is False

    admission = _mapping(staging_model.contract["provider_neutral_staging_admission"])
    assert admission["aws_reference_boundary"] == {
        "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "canonical_story_deliverables": (
            "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
        ),
        "non_aws_owner_managed_profiles": ("ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"),
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    }
    assert staging_model.contract["environment_boundary"]["reference_region_use"] == (
        "METADATA_ONLY"
    )
    equivalence = _mapping(admission["evidence_equivalence_policy"])
    forbidden_fields = {
        "provider_label_as_evidence",
        "aws_label_as_evidence",
        "service_label_as_evidence",
        "predecessor_completion_as_evidence",
        "reference_metadata_as_evidence",
        "local_test_as_live_evidence",
    }
    for field in forbidden_fields:
        assert equivalence[field] == "FORBIDDEN"
    assert {
        value for key, value in equivalence.items() if key not in forbidden_fields
    } == {"REQUIRED"}


def test_every_target_runtime_release_and_rollback_selection_is_unset(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    selected = _mapping(staging_model.contract["selected_bindings"])
    list_fields = {
        "target_provider_plugins",
        "target_resource_bindings",
        "domain_names",
        "notification_channels",
    }
    assert list_fields <= set(selected)
    assert all(
        value == [] if field in list_fields else value is None
        for field, value in selected.items()
    )
    assert set(selected) == {
        "target_provider_name",
        "target_profile_id",
        "target_profile_kind",
        "target_account_project_or_tenant",
        "target_region",
        "target_backup_region",
        "target_data_residency_policy",
        "target_state_backend",
        "target_deployment_identity",
        "target_federation_audience",
        "target_adapter",
        "target_provider_plugins",
        "target_resource_bindings",
        "github_repository",
        "github_ref",
        "github_workflow",
        "github_environment",
        "artifact_digest",
        "artifact_sbom_reference",
        "artifact_scan_reference",
        "artifact_provenance_reference",
        "release_id",
        "commit_sha",
        "contract_hash",
        "migration_version",
        "migration_task_reference",
        "domain_names",
        "public_endpoint",
        "admin_endpoint",
        "internal_endpoint",
        "liveness_endpoint",
        "readiness_endpoint",
        "smoke_endpoint",
        "health_matcher",
        "browser_base_url",
        "browser_project",
        "telemetry_source",
        "alert_policy",
        "notification_channels",
        "budget_limit",
        "automatic_stop_policy",
        "rollback_artifact_digest",
        "rollback_configuration_version",
        "rollback_snapshot_id",
        "rollback_migration_version",
    }


def test_provider_neutral_evidence_intents_remain_required_and_unconfigured(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    contract = staging_model.contract
    classifications = {
        "artifact_admission_intent": (
            "IMMUTABLE_PROVIDER_NEUTRAL_SUPPLY_CHAIN_REQUIREMENTS_ONLY"
        ),
        "protected_environment_intent": (
            "EXACT_BINDING_AND_INDEPENDENT_HUMAN_APPROVAL_REQUIREMENTS_ONLY"
        ),
        "migration_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_COMPATIBILITY_REQUIREMENTS_ONLY"
        ),
        "health_security_runtime_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_RUNTIME_GATES_ONLY"
        ),
        "transport_security_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_CROSS_CAPABILITY_TRANSPORT_SECURITY_"
            "GATES_ONLY"
        ),
        "observability_alerting_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_OBSERVABILITY_GATES_ONLY"
        ),
        "isolation_residency_budget_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_ISOLATION_RESIDENCY_BUDGET_GATES_ONLY"
        ),
        "target_adapter_intent": "PROVIDER_NEUTRAL_TARGET_ADAPTER_REQUIREMENTS_ONLY",
        "rollback_restore_intent": (
            "DECLARATIVE_PROVIDER_NEUTRAL_ROLLBACK_RESTORE_REQUIREMENTS_ONLY"
        ),
    }
    for section, classification in classifications.items():
        assert _mapping(contract[section])["classification"] == classification

    artifact = _mapping(contract["artifact_admission_intent"])
    for field in (
        "build_once",
        "immutable_digest",
        "sbom",
        "vulnerability_scan",
        "signed_provenance",
        "promote_without_rebuild",
    ):
        assert artifact[field] == "REQUIRED_NOT_CONFIGURED"
    assert artifact["critical_high_findings"] == "ZERO_REQUIRED_NOT_CONFIGURED"
    migration = _mapping(contract["migration_intent"])
    for field in (
        "migration_owner_assignment",
        "independent_migration_review",
        "independent_migration_approval",
    ):
        assert migration[field] == "REQUIRED_NOT_CONFIGURED"
    assert migration["migration_self_approval"] == "FORBIDDEN"
    assert migration["migration_review_bypass"] == "FORBIDDEN"
    transport = _mapping(contract["transport_security_intent"])
    required_transport = {
        "all_staging_network_flows",
        "artifact_and_promotion_transport",
        "identity_federation_transport",
        "deployment_control_transport",
        "migration_transport",
        "smoke_and_runtime_transport",
        "telemetry_and_alert_transport",
        "rollback_and_restore_transport",
        "target_adapter_transport",
        "authenticated_encryption",
        "certificate_identity_and_hostname_verification",
        "downgrade_resistance",
        "approved_protocol_and_cipher_policy",
    }
    for field in required_transport:
        assert transport[field] == "REQUIRED_NOT_CONFIGURED"
    for field in (
        "plaintext_transport",
        "insecure_skip_verification",
        "provider_managed_label_as_evidence",
        "local_fixture_as_transport_evidence",
    ):
        assert transport[field] == "FORBIDDEN"
    target = _mapping(contract["target_adapter_intent"])
    for field in (
        "interface_contract",
        "capability_mapping",
        "security_evidence",
        "operations_evidence",
        "release_evidence",
        "audit_and_revocation",
    ):
        assert target[field] == "REQUIRED_NOT_CONFIGURED"
    assert target["provider_sdk_types_in_domain"] == "FORBIDDEN"
    assert target["provider_name_only_admission"] == "FORBIDDEN"
    assert target["implicit_adapter"] == "FORBIDDEN"
    assert target["provider_call"] == "FORBIDDEN"


def test_environment_activation_phases_and_actions_are_fail_closed(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    contract = staging_model.contract
    environment = _mapping(contract["environment_boundary"])
    assert environment["label"] == "STAGING"
    assert environment["classification"] == "INERT_CANONICAL_LABEL_ONLY"
    assert environment["configuration_status"] == "NOT_CONFIGURED"
    assert environment["activation_status"] == "DISABLED"
    assert environment["runtime_status"] == "NOT_EXECUTED"
    assert environment["live_status"] == "NOT_EXECUTED"
    assert environment["formal_verification_status"] == "NOT_EXECUTED"
    assert environment["apply_target"] is None
    assert environment["credential_material"] == "ABSENT"
    for field in (
        "external_access",
        "staging_action",
        "release_action",
        "production_action",
    ):
        assert environment[field] == "FORBIDDEN"

    phases = cast(list[dict[str, object]], contract["logical_phases"])
    assert [phase["name"] for phase in phases] == list(PHASE_NAMES)
    assert phases == [
        {
            "name": name,
            "status": "DISABLED",
            "execution_status": "NOT_EXECUTED",
            "external_action": "FORBIDDEN",
            "action_count": 0,
        }
        for name in PHASE_NAMES
    ]

    execution = _mapping(contract["execution_boundary"])
    assert execution["activation_enabled"] is False
    assert execution["activation_status"] == "DISABLED"
    assert execution["runtime_status"] == "NOT_EXECUTED"
    assert execution["operations"] == {name: "FORBIDDEN" for name in OPERATION_NAMES}
    assert execution["action_counts"] == {name: 0 for name in ACTION_COUNT_NAMES}
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "staging_action",
        "deploy_action",
        "migration_action",
        "migration_review_action",
        "transport_security_action",
        "rollback_action",
        "release_action",
        "production_action",
    ):
        assert execution[field] == "FORBIDDEN"


def test_evidence_boundary_never_promotes_local_work_to_formal_or_live_evidence(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    evidence = _mapping(staging_model.contract["evidence_boundary"])
    assert evidence["deliverable_classification"] == (
        "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
        "REFERENCE_PLAN"
    )
    for field in (
        "executable_pipeline",
        "workflow",
        "target_adapter_runtime",
        "terraform_or_provider_runtime",
        "migration_runtime",
        "browser_runtime",
        "credentials",
    ):
        assert evidence[field] == "ABSENT"
    for field in (
        "predecessor_dependency_admission",
        "target_profile_admission",
        "build_sbom_scan_provenance",
        "protected_environment_approval",
        "formal_tst_009",
        "formal_tst_022",
        "migration_database",
        "independent_migration_review",
        "smoke_security_runtime",
        "transport_security",
        "observability_alerting",
        "rollback_restore",
        "hosted_ci",
        "live_provider",
        "staging",
        "release",
        "production",
    ):
        assert evidence[field] == "NOT_EXECUTED"
    assert evidence["effective_canonical_status"] == "UNCHANGED"


def test_reference_plan_is_a_v1_1_non_executable_projection(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    plan = generator.reference_plan_document(staging_model)
    assert tuple(plan) == (
        "document",
        "predecessor_bindings",
        "reference_architecture",
        "provider_neutral_staging_admission",
        "open_decision_boundary",
        "environment",
        "selected_bindings",
        "artifact_admission",
        "protected_environment",
        "migration",
        "health_security_runtime",
        "transport_security",
        "observability_alerting",
        "isolation_residency_budget",
        "target_adapter",
        "rollback_restore",
        "logical_phases",
        "action_counts",
        "activation",
        "verification_boundary",
    )
    assert plan["document"] == {
        "id": "RAOS-STAGING-DEPLOYMENT-REFERENCE-PLAN-001",
        "version": "1.1.0",
        "story_id": "ST-1505",
        "source_contract": (
            "repo://changes/st-1505/contracts/staging-deployment.v1.yaml"
        ),
        "generated_by": "repo://scripts/build_st1505_staging_deployment.py",
        "generation_command": (
            "uv run --locked --no-sync python "
            "scripts/build_st1505_staging_deployment.py"
        ),
        "artifact_kind": (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
            "REFERENCE_PLAN"
        ),
        "executable": False,
        "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    }
    assert (
        plan["provider_neutral_staging_admission"]
        == staging_model.contract["provider_neutral_staging_admission"]
    )
    assert plan["selected_bindings"] == staging_model.contract["selected_bindings"]
    assert json.loads(generator.render_reference_plan(staging_model)) == plan
