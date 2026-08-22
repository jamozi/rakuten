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
HANDOFF_SHA256 = "146351e1ba13970b33bccc0df3683c8b650769b1357f829424f1d53bce8a3937"
HANDOFF_SEMANTIC_SHA256 = (
    "30eaec3fbeceec8b3b4043777d7c3fe8b97082e36f585e70899ba6104fa3bc32"
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
            "558e1f8dc20331730582e62018cd88579f4b82e295bffad617049a925ab466a7"
        ),
        "handoff_uri": (
            "repo://changes/st-1501/"
            "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
        ),
        "handoff_sha256": (
            "ec01dcb05f6176c21ba8b9947bed60b88ce9a2622e1c358478f4f79a633bda61"
        ),
        "handoff_semantic_sha256": (
            "0915d6ec4949babebf43f307b2ac1569fa76213c96a3be9009dfaec660e34030"
        ),
        "contract_uri": (
            "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "c16287606c4d73982ead82c9f8e111b327b0447ed8c06a6630c6ce5ac22f07c6"
        ),
        "contract_semantic_sha256": (
            "715fbdd46467ac282333c486850a5571d27836d5d028f971e5840f755e338a6e"
        ),
        "plan_uri": (
            "repo://infra/terraform/foundation/"
            "terraform-foundation.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "c486637559457aedd24fbdd752d624a754dc69ed399bbed83ecaebd037c4f559"
        ),
        "plan_semantic_sha256": (
            "6521f7396e8b076177cd00d297342a482ac664809c432dde48c8c7d55d01d32f"
        ),
        "action_counts": {"create": 0, "update": 0, "delete": 0},
    },
    "data_services": {
        "story_id": "ST-1502",
        "owner_generator_uri": "repo://scripts/build_st1502_data_services.py",
        "owner_generator_sha256": (
            "fcb488254a09bf5ac686a66d75865ccef8ee0e027360e3131c8aacea8de01484"
        ),
        "handoff_uri": (
            "repo://changes/st-1502/"
            "DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml"
        ),
        "handoff_sha256": (
            "40d866ae30199748c9d91b8152aaa4fb4ca2721e5e722bcff05cf97760f1c228"
        ),
        "handoff_semantic_sha256": (
            "53a640dd58c222296da2c079a374daf55e6a55e40fb1944bae6070b7ef559450"
        ),
        "contract_uri": (
            "repo://changes/st-1502/contracts/data-services-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "4d0ca4188c4a4ee7c8f6c8417afc6880b9ac0f89b6e4bd63703eb98d8368dddb"
        ),
        "contract_semantic_sha256": (
            "3b696b86edd9b0a04e85c99f3306deb4879a935c381351276136a49e7423f440"
        ),
        "plan_uri": (
            "repo://infra/terraform/data-services/data-services.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "28f4ae25fd66f0bb999a1918e72a5d108f38991bb5104e2726b01a0997a6087c"
        ),
        "plan_semantic_sha256": (
            "777368a0ee051d9f74f1bb4b25216ddf4ea4b1000f16a283e387df197b1095d7"
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
            "554d00a82f1a48d1e154e5aaff63fad7330e46a81e862e6bc0a2b30385029a7b"
        ),
        "handoff_uri": (
            "repo://changes/st-1503/"
            "DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml"
        ),
        "handoff_sha256": (
            "de21922772e9e88ba830fc33c82848a9423d492fc9696027b91febf9aebb0646"
        ),
        "handoff_semantic_sha256": (
            "0e3d26dc01e244034567bbd6fe13ace689447cc5f835e6b3581b64120cfbc7fe"
        ),
        "contract_uri": (
            "repo://changes/st-1503/contracts/compute-edge-foundation.v1.yaml"
        ),
        "contract_sha256": (
            "7d742065c5ffda0dbecf04c144af7daf0de2fdc0d2598e85bc9af656c4ac242d"
        ),
        "contract_semantic_sha256": (
            "4ee5dfb892be42119d4f2c77c07e850a93785458e47c496e0e953fd83fc276ac"
        ),
        "plan_uri": (
            "repo://infra/terraform/compute-edge/compute-edge.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "a894504b51f2cc5f77d05a00c12fdcbd854a49d74d80822c9564f08957bd3888"
        ),
        "plan_semantic_sha256": (
            "50d334f3d28a0c0b56623b3960a6b1d3398d861aeda72d6abee1339f84b4e6a8"
        ),
        "action_counts": {"create": 0, "update": 0, "delete": 0},
    },
    "deployment_identity": {
        "story_id": "ST-1504",
        "owner_generator_uri": "repo://scripts/build_st1504_github_oidc.py",
        "owner_generator_sha256": (
            "3972533552bf2e1d3265ae4a41571872a5c0aa6fd537fa69c7afd3736eb53a28"
        ),
        "handoff_uri": (
            "repo://changes/st-1504/"
            "DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml"
        ),
        "handoff_sha256": (
            "f6a89722b86a8a47288da86c09214a3a926061d16489737170edc07398b2be61"
        ),
        "handoff_semantic_sha256": (
            "8afd193ddc98a0193e21032a3058c157fe75f12151cb06d80a9ea198efbc5f8c"
        ),
        "contract_uri": (
            "repo://changes/st-1504/contracts/github-oidc-deployment.v1.yaml"
        ),
        "contract_sha256": (
            "d7e6922ff953434435509a4bd3aca0251b57dc699e990fae3ae06c75af229b4c"
        ),
        "contract_semantic_sha256": (
            "795f7ec4218e029feef40aee6d6616ff62e3f9cc847a8383f4f847514c8c3d22"
        ),
        "plan_uri": (
            "repo://infra/terraform/deployment-identity/"
            "github-oidc.reference-plan.v1.json"
        ),
        "plan_sha256": (
            "7566adbe5a9eff81144ceffb9ec233ba98322c2d01f399e5a103a033d0b35974"
        ),
        "plan_semantic_sha256": (
            "256550caaf1c7fba5aca5b4c74015590d052941e87e9fcaf4c2eb3db7af25697"
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


def test_design_handoff_is_directly_byte_and_semantic_hash_bound(
    contract_document: dict[str, Any],
) -> None:
    handoff_file = REPOSITORY_ROOT / HANDOFF_PATH
    assert handoff_file.is_file()
    assert not handoff_file.is_symlink()
    assert generator.sha256_file(handoff_file) == HANDOFF_SHA256
    handoff = generator.load_yaml(handoff_file)
    assert generator.semantic_sha256(handoff) == HANDOFF_SEMANTIC_SHA256

    source_rows = cast(list[dict[str, object]], contract_document["sources"])
    assert [
        row for row in source_rows if row["uri"] == f"repo://{HANDOFF_PATH.as_posix()}"
    ] == [
        {
            "uri": f"repo://{HANDOFF_PATH.as_posix()}",
            "sha256": HANDOFF_SHA256,
        }
    ]

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


def test_all_four_predecessors_are_exact_hash_semantic_and_safety_bound(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    bindings = _mapping(staging_model.contract["predecessor_bindings"])
    assert tuple(bindings) == tuple(PREDECESSORS)
    for name, expected in PREDECESSORS.items():
        row = _mapping(bindings[name])
        story_id = cast(str, expected["story_id"])
        assert row["story_id"] == story_id
        assert row["owner_generator_uri"] == expected["owner_generator_uri"]
        assert row["owner_generator_sha256"] == expected["owner_generator_sha256"]
        assert row["design_handoff_uri"] == expected["handoff_uri"]
        assert row["design_handoff_sha256"] == expected["handoff_sha256"]
        assert (
            row["design_handoff_semantic_sha256"] == expected["handoff_semantic_sha256"]
        )
        assert row["contract_uri"] == expected["contract_uri"]
        assert row["contract_sha256"] == expected["contract_sha256"]
        assert row["contract_semantic_sha256"] == expected["contract_semantic_sha256"]
        assert row["reference_plan_uri"] == expected["plan_uri"]
        assert row["reference_plan_sha256"] == expected["plan_sha256"]
        assert row["reference_plan_semantic_sha256"] == expected["plan_semantic_sha256"]
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
        assert row["required_reference_plan_executable"] is False
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
        "historical_reference_only": "REJECT",
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


def test_aws_is_historical_reference_only_and_never_an_admission_shortcut(
    staging_model: generator.StagingDeploymentModel,
) -> None:
    reference = _mapping(staging_model.contract["reference_architecture"])
    assert reference["cloud"] == "AWS"
    assert reference["region"] == "ap-northeast-1"
    assert reference["classification"] == (
        "OPTIONAL_HISTORICAL_AWS_STAGING_REFERENCE_MAPPINGS_ONLY"
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
        "role": "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    }
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
