#!/usr/bin/env python3
"""Build the disabled, provider-free ST-1503 logical compute/edge module."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.raos_build_core import input_hash_required  # noqa: E402

CONTRACT_PATH: Final = Path("changes/st-1503/contracts/compute-edge-foundation.v1.yaml")
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json"
)
LOGICAL_PLAN_PATH: Final = Path(
    "infra/terraform/compute-edge/compute-edge.logical-plan.v1.json"
)
TOOLCHAIN_LOCK_PATH: Final = Path(
    "infra/terraform/compute-edge/terraform-validation-toolchain.lock.v1.json"
)
HCL_PATHS: Final = tuple(
    Path("infra/terraform/compute-edge") / name
    for name in ("versions.tf", "variables.tf", "locals.tf", "checks.tf", "outputs.tf")
)
MANIFEST_PATH: Final = Path("changes/st-1503/manifest.yaml")
GENERATED_ARTIFACT_PATHS: Final = (
    REFERENCE_PLAN_PATH,
    LOGICAL_PLAN_PATH,
    TOOLCHAIN_LOCK_PATH,
    *HCL_PATHS,
)
GENERATED_PATHS: Final = (*GENERATED_ARTIFACT_PATHS, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1503_compute_edge.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1503_compute_edge.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"
NATIVE_CHECK_COMMAND: Final = (
    f"{GENERATION_COMMAND} --native-check --terraform /absolute/path/to/terraform"
)

TERRAFORM_VERSION: Final = "1.15.9"
TERRAFORM_PLATFORM: Final = "linux_amd64"
TERRAFORM_REQUIRED_VERSION: Final = f"= {TERRAFORM_VERSION}"
TERRAFORM_BINARY_SHA256: Final = (
    "c39d41adb17963bac5dd610ad47815dd81e945371a7cabc344a45d63b1b093bd"
)
ALLOWED_NATIVE_ARGUMENTS: Final = (
    ("version", "-json"),
    ("fmt", "-check", "-recursive"),
    ("validate", "-json"),
)
HCL_IDENTIFIER_PATTERN: Final = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")

AUTHORITY_SOURCES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md": (
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3"
    ),
    "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml": (
        "2cdc9afb4b9a1fc7cb44b78dc5198bc443a219ca895713b75220f8625aea6305"
    ),
    "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md": (
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml": (
        "2a6da0fa771153cafe2aa79f01b09843832e032ec13a29dd34884a31ae0c519d"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "5f13094d18dfbece65ccf36a68928fc9d602d316068aa5f1b538f14d90136e1e"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "bb5a6bb86ab13cf465a980eccea75bc3742eb818af142dc74ba6cea90aef6a72"
    ),
    "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json": (
        "696c1e06b4dbb93c952a32e181d145ce8cdf6980b3434fee7e4795296f887f44"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    Path("changes/st-1503/IMPLEMENTATION_RECORD_V2_ST1503_LOGICAL_HCL.yaml"),
    Path("changes/st-1503/LOCAL_COMPLETION_EVIDENCE_V2.md"),
    Path("changes/st-1503/PREFLIGHT_LOCAL_CODE_COMPLETE_V2.md"),
    Path("changes/st-1503/README.md"),
    Path("scripts/build_st1503_compute_edge.py"),
    Path("tests/st1503/conftest.py"),
    Path("tests/st1503/test_contract.py"),
    Path("tests/st1503/test_generation.py"),
    Path("tests/st1503/test_logical_hcl.py"),
    Path("tests/st1503/test_negative_cases.py"),
)

EXPECTED_PREDECESSOR_TOOLCHAIN_SEMANTIC_SHA256: Final = (
    "db631e5421d5eea0534737b1df03425ccb873cfe981ad96409d3c90aeef4de1a"
)
EXPECTED_HANDOFF_SOURCE_DESIGN_REFS: Final = (
    "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    "repo://docs/canonical/01_integration/"
    "RAOS_07_canonical_decisions_v1.0.yaml#INT-DEC-007",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-002",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-009",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-010",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-011",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-015",
    "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-1503",
    "repo://changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "repo://docs/upstream/key_documents/"
    "RAOS_02_system_architecture_v0.1.md#RAOS-ARCH-001",
    "repo://docs/canonical/06_ops/"
    "RAOS_12_operations_reliability_design_v1.0.md#RAOS-OPS-001",
    "repo://docs/canonical/04_security/"
    "RAOS_10_security_privacy_design_v1.0.md#RAOS-SEC-001",
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-026",
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-027",
)

EXPECTED_STORY: Final = {
    "id": "ST-1503",
    "epic_id": "EPIC-15",
    "title": "Compute/CDN/WAF infrastructure",
    "objective": "ECS/CloudFront/WAF/routeをIaC化",
    "depends_on": ["ST-1501"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["modules"],
    "acceptance_criteria": ["public/admin boundary", "health"],
    "test_suites": ["TST-026", "TST-027"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_INT_DEC_007: Final = {
    "id": "INT-DEC-007",
    "title": "Reference Cloud",
    "status": "RESOLVED",
    "decision": (
        "AWS東京リージョンをReference ArchitectureとするがCoreをAWS固有Domain Modelへ密結合させない"
    ),
    "implementation_effect": "TerraformとAdapter境界を用意。実AWS Accountは未設定",
}
EXPECTED_OPEN_DECISIONS: Final = {
    "OD-002": {
        "id": "OD-002",
        "topic": "site_name_and_domain",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Staging public UI",
        "owner": "Product Owner",
        "decision_needed": "ブランド名、ドメイン、運営者表記を決定",
        "default_behavior": "example.invalidと仮ブランドを使用し外部公開禁止",
        "blocking": True,
    },
    "OD-009": {
        "id": "OD-009",
        "topic": "budget_and_acceptable_loss",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Cloud/LLM release",
        "owner": "Business Owner",
        "decision_needed": "AWS、LLM、外部Providerの月次上限と自動停止閾値を設定",
        "default_behavior": "低い開発用上限、Production無効",
        "blocking": True,
    },
    "OD-010": {
        "id": "OD-010",
        "topic": "oidc_provider",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Admin authentication",
        "owner": "Security Owner",
        "decision_needed": "Cognitoまたは承認済みOIDC Providerを選定",
        "default_behavior": "Local fake authはdevelopmentのみ。外部公開不可",
        "blocking": True,
    },
    "OD-011": {
        "id": "OD-011",
        "topic": "notification_channels",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Incident operations",
        "owner": "Operations Owner",
        "decision_needed": "Critical/High通知先とEscalation連絡先を設定",
        "default_behavior": "Local logのみ。Production不可",
        "blocking": True,
    },
    "OD-013": {
        "id": "OD-013",
        "topic": "production_region_and_data_residency",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Terraform production",
        "owner": "Security/Business Owner",
        "decision_needed": "AWS Region、Backup Region、越境移転の扱いを承認",
        "default_behavior": "Referenceはap-northeast-1、Production apply禁止",
        "blocking": True,
    },
    "OD-015": {
        "id": "OD-015",
        "topic": "production_provider_credentials",
        "status": "EXTERNAL_EVIDENCE_REQUIRED",
        "required_by": "Live adapter test",
        "owner": "Operations Owner",
        "decision_needed": "楽天、OpenAI、Google、AWSの専用Account/権限/Secretを設定",
        "default_behavior": "Recorded fixtureのみ",
        "blocking": True,
    },
}
EXPECTED_TESTS: Final = {
    "TST-026": {
        "id": "TST-026",
        "name": "Security verification",
        "layer": "security",
        "purpose": "ASVS control、SAST/SCA/DAST、manual abuse",
        "candidate_tools": ["security tools", "manual"],
        "release_blocking": True,
        "environments": ["CI", "staging"],
        "owner": "Security",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    "TST-027": {
        "id": "TST-027",
        "name": "Performance and load",
        "layer": "performance",
        "purpose": "Public/Admin/API/workerのSLO capacity",
        "candidate_tools": ["k6相当", "browser RUM lab"],
        "release_blocking": True,
        "environments": ["staging"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-004": "Role/Scope/Siteで最小権限",
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-APP-003": "nonce/hashベースのCSPを適用",
    "SEC-APP-009": "Public/Admin/Internalを別Policyで制限",
    "SEC-APP-014": "HSTS、nosniff、frame-ancestors、referrer policy",
    "SEC-APP-015": "Admin/Confidential responseをshared cacheしない",
    "SEC-DATA-001": "TLSをPublic/Internal/Providerで要求",
    "SEC-DATA-002": "RDS/S3/backup/logを暗号化",
    "SEC-DATA-003": "SecretをDB/Repo/Logへ置かない",
    "SEC-DATA-006": "Public roleはreadmodelのみ",
    "SEC-INFRA-001": "RDS/worker/object admin endpointをPublicにしない",
    "SEC-INFRA-002": "Public ingressを管理Pointへ限定",
    "SEC-INFRA-003": "Workload別にProvider allowlist",
    "SEC-INFRA-004": "ProductionとDevelopmentを分離",
    "SEC-INFRA-005": "Manual driftを検知し原則IaCで変更",
    "SEC-SDLC-007": "Release artifactのSBOM生成",
    "SEC-SDLC-008": "Build provenance/attestationを生成",
    "SEC-SDLC-012": "Production deployはHuman approval",
    "SEC-OPS-001": "Auth failure、privilege、secret、WAF、kill switchを監視",
    "SEC-OPS-003": "SEVとresponse ownerを定義",
    "SEC-OPS-004": "Artifact、log、timelineを保全",
}

WORKLOAD_ROLES: Final = (
    "public_web",
    "admin_web",
    "core_api",
    "worker_pool",
)
SURFACE_ROLES: Final = ("public", "admin", "internal")
ELIGIBLE_PROFILE_KINDS: Final = (
    "AWS",
    "OTHER_CLOUD",
    "OWNER_MANAGED_INFRASTRUCTURE",
)
COMPUTE_EDGE_CAPABILITY_OUTCOMES: Final = (
    (
        "workload_runtime_scheduling_and_supply_chain",
        "ISOLATED_SCHEDULING_IMMUTABLE_IMAGE_PROVENANCE_SCALING_HEALTH_AND_SAFE_ROLLBACK",
    ),
    (
        "public_ingress_edge_cdn_and_origin_control",
        "EDGE_MEDIATED_PUBLIC_INGRESS_WITH_PRIVATE_AUTHENTICATED_ORIGINS_AND_CACHE_CONTROL",
    ),
    (
        "dns_tls_certificate_and_transport_security",
        "CONTROLLED_DNS_CERTIFICATE_LIFECYCLE_AND_TLS_FOR_"
        "PUBLIC_INTERNAL_PROVIDER_AND_ORIGIN_TRANSPORT",
    ),
    (
        "waf_abuse_rate_limiting_and_attack_controls",
        "MANAGED_WAF_RATE_LIMIT_ABUSE_ATTACK_TELEMETRY_AND_TESTED_RESPONSE",
    ),
    (
        "public_admin_internal_surface_and_data_plane_isolation",
        "DISTINCT_ROUTE_HOST_CACHE_COOKIE_IDENTITY_AND_PRIVATE_DATA_PLANE_POLICIES",
    ),
    (
        "workload_identity_secrets_and_controlled_egress",
        "LEAST_PRIVILEGE_NON_AMBIENT_IDENTITY_SECRETS_AUDIT_AND_DESTINATION_CONTROL",
    ),
    (
        "observability_health_canary_and_rollback",
        "TELEMETRY_SLO_HEALTH_ALERT_OWNER_RUNBOOK_CANARY_PROMOTION_AND_ROLLBACK_EVIDENCE",
    ),
    (
        "region_data_residency_and_failure_domain_evidence",
        "APPROVED_REGION_RESIDENCY_FAILURE_DOMAIN_CAPACITY_AND_RECOVERY_EVIDENCE",
    ),
)
NATIVE_COMMANDS: Final = ("init", "plan", "apply", "destroy", "import", "refresh")
ACTION_NAMES: Final = (
    "create",
    "update",
    "delete",
    "deploy",
    "promote",
    "rollback",
    "route",
    "scale",
)
PREDECESSOR_ACTION_NAMES: Final = ("create", "update", "delete")
WORKLOAD_COMPONENT_IDS: Final = tuple(f"workload_{role}" for role in WORKLOAD_ROLES)
IDENTITY_COMPONENT_IDS: Final = tuple(f"identity_{role}" for role in WORKLOAD_ROLES)
EGRESS_COMPONENT_IDS: Final = tuple(f"egress_{role}" for role in WORKLOAD_ROLES)
LIVENESS_COMPONENT_IDS: Final = tuple(f"liveness_{role}" for role in WORKLOAD_ROLES)
READINESS_COMPONENT_IDS: Final = tuple(f"readiness_{role}" for role in WORKLOAD_ROLES)
EDGE_COMPONENT_IDS: Final = ("edge_public", "edge_admin")
INGRESS_COMPONENT_IDS: Final = (
    "ingress_public",
    "ingress_admin",
    "ingress_internal",
)
WAF_COMPONENT_IDS: Final = ("waf_public", "waf_admin")
RATE_LIMIT_COMPONENT_IDS: Final = ("rate_limit_public", "rate_limit_admin")
IDENTITY_PERMISSIONS: Final = {
    "identity_public_web": ("public_projection.read", "telemetry.write"),
    "identity_admin_web": ("core_api.admin.invoke", "telemetry.write"),
    "identity_core_api": (
        "data_plane.command",
        "object.metadata.read",
        "queue.send",
        "telemetry.write",
    ),
    "identity_worker_pool": (
        "data_plane.job",
        "object.artifact.read",
        "object.artifact.write",
        "provider.egress.invoke",
        "queue.consume",
        "telemetry.write",
    ),
    "identity_edge_origin": ("origin.admin.invoke", "origin.public.invoke"),
}
SUCCESSOR_GATE_EVIDENCE: Final = (
    "OD-002_SITE_DOMAIN_RESOLVED",
    "OD-009_BUDGET_AND_CAP_RESOLVED",
    "OD-010_ADMIN_IDENTITY_PROVIDER_RESOLVED",
    "OD-011_ALERT_CHANNEL_AND_ESCALATION_RESOLVED",
    "OD-013_REGION_RESIDENCY_RESOLVED",
    "OD-015_ACCOUNT_CREDENTIAL_EVIDENCE",
    "TST-026_FORMAL_SECURITY_EVIDENCE",
    "TST-027_FORMAL_STAGING_PERFORMANCE_LOAD_EVIDENCE",
    "PROVIDER_SCHEMA_PLUGIN_AND_DISTRIBUTION_PROVENANCE",
    "PRIVATE_NETWORK_ACCOUNT_AND_ORIGIN_ISOLATION_EVIDENCE",
    "IMMUTABLE_IMAGE_DIGEST_SIGNATURE_SBOM_AND_SCAN_EVIDENCE",
    "LEAST_PRIVILEGE_WORKLOAD_IDENTITY_SECRET_AND_EGRESS_REVIEW",
    "DNS_TLS_WAF_RATE_LIMIT_AND_ORIGIN_AUTHENTICATION_EVIDENCE",
    "DISTINCT_LIVENESS_READINESS_AND_MIGRATION_FAILURE_EVIDENCE",
    "OBSERVABILITY_ALERT_OWNER_RUNBOOK_AND_CAPACITY_EVIDENCE",
    "HUMAN_APPROVED_CANARY_PROMOTION_ROLLBACK_AND_RELEASE_EVIDENCE",
)
HCL_ALLOWED_BLOCKS_BY_FILE: Final = {
    "versions.tf": ("terraform",),
    "variables.tf": ("variable",) * 19,
    "locals.tf": ("locals",),
    "checks.tf": ("check",) * 12,
    "outputs.tf": ("output",) * 7,
}
HCL_FORBIDDEN_TOP_LEVEL_BLOCKS: Final = {
    "provider",
    "backend",
    "module",
    "data",
    "resource",
    "provisioner",
    "import",
    "moved",
    "removed",
}
HCL_TOP_LEVEL_BLOCK_PATTERN: Final = re.compile(
    r"(?m)^(terraform|variable|locals|check|output|provider|backend|module|data|resource|provisioner|import|moved|removed)\b"
)
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
MAX_HCL_BYTES: Final = 512 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _logical_component(
    component_id: str,
    kind: str,
    *,
    reference_services: tuple[str, ...] = (),
    trust_boundary: str = "CONTROL",
    publicly_addressable: bool = False,
    edge_mediated: bool = False,
    private_origin: bool = True,
    public_projection_only: bool = False,
    direct_data_plane_access: bool = False,
    approved_identity_required: bool = False,
    service_identity_required: bool = False,
    controlled_egress_required: bool = False,
    transport_encryption_required: bool = True,
    immutable_image_required: bool = False,
    digest_selection_required: bool = False,
    signed_provenance_required: bool = False,
    sbom_required: bool = False,
    image_scan_required: bool = False,
    secret_material_present: bool = False,
    waf_required: bool = False,
    rate_limit_required: bool = False,
    shared_cache_allowed: bool = False,
    observability_required: bool = True,
    canary_required: bool = False,
    rollback_required: bool = False,
    liveness_purpose: str = "NOT_APPLICABLE",
    readiness_purpose: str = "NOT_APPLICABLE",
    external_dependency_in_liveness: bool = False,
) -> dict[str, object]:
    return {
        "component_id": component_id,
        "kind": kind,
        "reference_services": list(reference_services),
        "trust_boundary": trust_boundary,
        "publicly_addressable": publicly_addressable,
        "edge_mediated": edge_mediated,
        "private_origin": private_origin,
        "public_projection_only": public_projection_only,
        "direct_data_plane_access": direct_data_plane_access,
        "approved_identity_required": approved_identity_required,
        "service_identity_required": service_identity_required,
        "controlled_egress_required": controlled_egress_required,
        "transport_encryption_required": transport_encryption_required,
        "immutable_image_required": immutable_image_required,
        "digest_selection_required": digest_selection_required,
        "signed_provenance_required": signed_provenance_required,
        "sbom_required": sbom_required,
        "image_scan_required": image_scan_required,
        "secret_material_present": secret_material_present,
        "waf_required": waf_required,
        "rate_limit_required": rate_limit_required,
        "shared_cache_allowed": shared_cache_allowed,
        "observability_required": observability_required,
        "canary_required": canary_required,
        "rollback_required": rollback_required,
        "liveness_purpose": liveness_purpose,
        "readiness_purpose": readiness_purpose,
        "external_dependency_in_liveness": external_dependency_in_liveness,
    }


def logical_compute_edge_components() -> list[dict[str, object]]:
    components = [
        _logical_component(
            "registry_supply_chain",
            "IMMUTABLE_IMAGE_SUPPLY_CHAIN",
            reference_services=("ECR",),
            immutable_image_required=True,
            digest_selection_required=True,
            signed_provenance_required=True,
            sbom_required=True,
            image_scan_required=True,
        )
    ]
    for role, trust_boundary in zip(
        WORKLOAD_ROLES, ("PUBLIC", "ADMIN", "INTERNAL", "INTERNAL"), strict=True
    ):
        components.append(
            _logical_component(
                f"workload_{role}",
                "ISOLATED_WORKLOAD",
                reference_services=("ECS", "Fargate"),
                trust_boundary=trust_boundary,
                public_projection_only=role == "public_web",
                approved_identity_required=role == "admin_web",
                service_identity_required=role in {"core_api", "worker_pool"},
                controlled_egress_required=True,
                immutable_image_required=True,
                digest_selection_required=True,
                signed_provenance_required=True,
                sbom_required=True,
                image_scan_required=True,
                canary_required=True,
                rollback_required=True,
            )
        )
    components.extend(
        [
            _logical_component(
                "edge_public",
                "MANAGED_EDGE",
                reference_services=("CloudFront", "WAF"),
                trust_boundary="PUBLIC",
                publicly_addressable=True,
                edge_mediated=True,
                public_projection_only=True,
                waf_required=True,
                rate_limit_required=True,
                shared_cache_allowed=True,
                canary_required=True,
                rollback_required=True,
            ),
            _logical_component(
                "edge_admin",
                "MANAGED_EDGE",
                reference_services=("CloudFront", "WAF"),
                trust_boundary="ADMIN",
                publicly_addressable=True,
                edge_mediated=True,
                approved_identity_required=True,
                waf_required=True,
                rate_limit_required=True,
                shared_cache_allowed=False,
                canary_required=True,
                rollback_required=True,
            ),
            _logical_component(
                "ingress_public",
                "PRIVATE_AUTHENTICATED_ORIGIN_INGRESS",
                reference_services=("ALB",),
                trust_boundary="PUBLIC",
                edge_mediated=True,
                public_projection_only=True,
            ),
            _logical_component(
                "ingress_admin",
                "PRIVATE_AUTHENTICATED_ORIGIN_INGRESS",
                reference_services=("ALB",),
                trust_boundary="ADMIN",
                edge_mediated=True,
                approved_identity_required=True,
            ),
            _logical_component(
                "ingress_internal",
                "PRIVATE_SERVICE_INGRESS",
                reference_services=("ALB",),
                trust_boundary="INTERNAL",
                service_identity_required=True,
            ),
            _logical_component(
                "dns_tls_public",
                "DNS_TLS_CERTIFICATE_LIFECYCLE",
                reference_services=("Route53", "ACM"),
                trust_boundary="PUBLIC",
                publicly_addressable=True,
                edge_mediated=True,
            ),
            _logical_component(
                "dns_tls_admin",
                "DNS_TLS_CERTIFICATE_LIFECYCLE",
                reference_services=("Route53", "ACM"),
                trust_boundary="ADMIN",
                publicly_addressable=True,
                edge_mediated=True,
                approved_identity_required=True,
            ),
        ]
    )
    for surface, trust_boundary in (("public", "PUBLIC"), ("admin", "ADMIN")):
        components.extend(
            [
                _logical_component(
                    f"waf_{surface}",
                    "WAF_ATTACK_POLICY",
                    reference_services=("WAF",),
                    trust_boundary=trust_boundary,
                    waf_required=True,
                    rate_limit_required=True,
                ),
                _logical_component(
                    f"rate_limit_{surface}",
                    "DISTINCT_RATE_LIMIT_POLICY",
                    reference_services=("WAF",),
                    trust_boundary=trust_boundary,
                    rate_limit_required=True,
                ),
                _logical_component(
                    f"cache_{surface}",
                    "DISTINCT_CACHE_COOKIE_CSP_POLICY",
                    reference_services=("CloudFront",),
                    trust_boundary=trust_boundary,
                    public_projection_only=surface == "public",
                    approved_identity_required=surface == "admin",
                    shared_cache_allowed=surface == "public",
                ),
            ]
        )
    for role, trust_boundary in zip(
        WORKLOAD_ROLES, ("PUBLIC", "ADMIN", "INTERNAL", "INTERNAL"), strict=True
    ):
        components.extend(
            [
                _logical_component(
                    f"identity_{role}",
                    "LEAST_PRIVILEGE_WORKLOAD_IDENTITY",
                    trust_boundary=trust_boundary,
                    approved_identity_required=role == "admin_web",
                    service_identity_required=role in {"core_api", "worker_pool"},
                ),
                _logical_component(
                    f"egress_{role}",
                    "CONTROLLED_DESTINATION_EGRESS_POLICY",
                    trust_boundary=trust_boundary,
                    controlled_egress_required=True,
                ),
                _logical_component(
                    f"liveness_{role}",
                    "PROCESS_LIVENESS_CONTRACT",
                    trust_boundary=trust_boundary,
                    liveness_purpose="PROCESS_ONLY",
                    external_dependency_in_liveness=False,
                ),
                _logical_component(
                    f"readiness_{role}",
                    "DEPENDENCY_MIGRATION_READINESS_CONTRACT",
                    trust_boundary=trust_boundary,
                    readiness_purpose="DEPENDENCY_AND_MIGRATION_READINESS",
                    external_dependency_in_liveness=False,
                ),
            ]
        )
    components.extend(
        [
            _logical_component(
                "observability_boundary",
                "LOG_METRIC_TRACE_SECURITY_TELEMETRY",
                observability_required=True,
            ),
            _logical_component(
                "canary_release_boundary",
                "HUMAN_APPROVED_BOUNDED_CANARY",
                canary_required=True,
                rollback_required=True,
            ),
            _logical_component(
                "rollback_boundary",
                "HUMAN_APPROVED_IMMUTABLE_ROLLBACK",
                rollback_required=True,
            ),
        ]
    )
    return components


def logical_compute_edge_edges() -> list[dict[str, str]]:
    edges: list[dict[str, str]] = []
    for role in WORKLOAD_ROLES:
        workload = f"workload_{role}"
        edges.extend(
            [
                {
                    "from": "registry_supply_chain",
                    "to": workload,
                    "relationship": "SUPPLIES_IMMUTABLE_IMAGE",
                },
                {
                    "from": f"identity_{role}",
                    "to": workload,
                    "relationship": "AUTHORIZES",
                },
                {
                    "from": f"egress_{role}",
                    "to": workload,
                    "relationship": "CONTROLS_EGRESS",
                },
                {
                    "from": f"liveness_{role}",
                    "to": workload,
                    "relationship": "PROBES_PROCESS_ONLY",
                },
                {
                    "from": f"readiness_{role}",
                    "to": workload,
                    "relationship": "PROBES_DEPENDENCY_AND_MIGRATION",
                },
                {
                    "from": "observability_boundary",
                    "to": workload,
                    "relationship": "OBSERVES",
                },
                {
                    "from": "canary_release_boundary",
                    "to": workload,
                    "relationship": "GATES_PROMOTION",
                },
                {
                    "from": "rollback_boundary",
                    "to": workload,
                    "relationship": "RESTORES_IMMUTABLE_RELEASE",
                },
            ]
        )
    for surface in ("public", "admin"):
        edge = f"edge_{surface}"
        ingress = f"ingress_{surface}"
        edges.extend(
            [
                {
                    "from": f"dns_tls_{surface}",
                    "to": edge,
                    "relationship": "TERMINATES_CONTROLLED_TLS",
                },
                {"from": f"waf_{surface}", "to": edge, "relationship": "PROTECTS"},
                {
                    "from": f"rate_limit_{surface}",
                    "to": edge,
                    "relationship": "RATE_LIMITS",
                },
                {
                    "from": f"cache_{surface}",
                    "to": edge,
                    "relationship": "GOVERNS_CACHE_COOKIE_CSP",
                },
                {
                    "from": edge,
                    "to": ingress,
                    "relationship": "ROUTES_TO_PRIVATE_ORIGIN",
                },
                {
                    "from": "observability_boundary",
                    "to": edge,
                    "relationship": "OBSERVES",
                },
                {
                    "from": "canary_release_boundary",
                    "to": edge,
                    "relationship": "GATES_PROMOTION",
                },
                {
                    "from": "rollback_boundary",
                    "to": edge,
                    "relationship": "RESTORES_IMMUTABLE_RELEASE",
                },
            ]
        )
    edges.extend(
        [
            {
                "from": "ingress_public",
                "to": "workload_public_web",
                "relationship": "TARGETS",
            },
            {
                "from": "ingress_admin",
                "to": "workload_admin_web",
                "relationship": "TARGETS",
            },
            {
                "from": "ingress_internal",
                "to": "workload_core_api",
                "relationship": "TARGETS",
            },
            {
                "from": "workload_admin_web",
                "to": "ingress_internal",
                "relationship": "CALLS_PRIVATE_CORE_API",
            },
            {
                "from": "workload_worker_pool",
                "to": "egress_worker_pool",
                "relationship": "USES_CONTROLLED_PROVIDER_EGRESS",
            },
        ]
    )
    return edges


def _health_contracts() -> dict[str, dict[str, object]]:
    return {
        role: {
            "liveness": {
                "purpose": "PROCESS_ONLY",
                "external_provider_dependency": "FORBIDDEN",
                "database_dependency": "FORBIDDEN",
                "generic_http_200_inference": "FORBIDDEN",
                "endpoint_path": None,
                "listener_port": None,
                "matcher": None,
            },
            "readiness": {
                "purpose": "DEPENDENCY_AND_MIGRATION_READINESS",
                "required_checks": [
                    "REQUIRED_CONFIGURATION",
                    "SCHEMA_COMPATIBILITY",
                    "DEPENDENCY_AVAILABILITY",
                    "KILL_SWITCH_CACHE",
                ],
                "generic_http_200_inference": "FORBIDDEN",
                "bounded_failure_behavior": "REQUIRED",
                "endpoint_path": None,
                "listener_port": None,
                "matcher": None,
            },
        }
        for role in WORKLOAD_ROLES
    }


def _aws_reference_service_mappings() -> list[dict[str, str]]:
    return [
        {
            "reference_name": reference_name,
            "capability_id": capability_id,
        }
        for reference_name, capability_id in (
            ("ECS", "workload_runtime_scheduling_and_supply_chain"),
            ("Fargate", "workload_runtime_scheduling_and_supply_chain"),
            ("ECR", "workload_runtime_scheduling_and_supply_chain"),
            ("ALB", "public_ingress_edge_cdn_and_origin_control"),
            ("CloudFront", "public_ingress_edge_cdn_and_origin_control"),
            ("Route53", "dns_tls_certificate_and_transport_security"),
            ("ACM", "dns_tls_certificate_and_transport_security"),
            ("WAF", "waf_abuse_rate_limiting_and_attack_controls"),
        )
    ]


def _binding_policy() -> dict[str, object]:
    policy: dict[str, object] = {
        name: {"selected": None, "default": None, "fallback": None}
        for name in (
            "provider",
            "account_or_project",
            "region",
            "workload_runtime_or_scheduler",
            "image_registry",
            "ingress_or_edge",
            "dns_or_tls",
            "waf_or_abuse_control",
            "compute_edge_plugin_or_adapter",
        )
    }
    policy.update(
        {
            "implicit_binding": "FORBIDDEN",
            "name_or_reference_only_eligibility": "FORBIDDEN",
        }
    )
    return policy


def _capability_mapping_requirements() -> list[dict[str, object]]:
    return [
        {
            "capability_id": capability_id,
            "required_outcome": required_outcome,
            "selected_mapping": None,
            "evidence_refs": [],
            "mapping_status": "REQUIRED_NOT_CONFIGURED",
        }
        for capability_id, required_outcome in COMPUTE_EDGE_CAPABILITY_OUTCOMES
    ]


def _workload_selection() -> dict[str, object]:
    return {
        "runtime_resource_reference": None,
        "scheduler_resource_reference": None,
        "image_registry_reference": None,
        "image_digest": None,
        "listener_port": None,
        "cpu_allocation": None,
        "memory_allocation_mib": None,
        "desired_instances": None,
        "scaling_minimum": None,
        "scaling_maximum": None,
        "failure_domain_ids": [],
        "network_segment_ids": [],
        "ingress_policy_ids": [],
        "egress_policy_ids": [],
        "workload_identity_reference": None,
        "secret_references": [],
        "log_destination_reference": None,
    }


def _workload_intent(
    role: str,
    trust_boundary: str,
    origin_exposure: str,
    data_plane_access: str,
    public_projection: str,
    identity_authorization: str,
) -> dict[str, object]:
    return {
        "role": role,
        "trust_boundary": trust_boundary,
        "origin_exposure": origin_exposure,
        "direct_public_access": "FORBIDDEN",
        "direct_internal_data_plane_access": data_plane_access,
        "public_projection_only": public_projection,
        "approved_identity_authorization": identity_authorization,
        "selected": _workload_selection(),
    }


def _surface_selection() -> dict[str, object]:
    return {
        "domain": None,
        "host": None,
        "route_patterns": [],
        "cache_policy_reference": None,
        "cookie_policy_reference": None,
        "csp_policy_reference": None,
        "authentication_policy_reference": None,
    }


def _surface_intent(
    surface: str,
    trust_boundary: str,
    data_plane_access: str,
    public_projection: str,
    identity_authorization: str,
) -> dict[str, object]:
    return {
        "surface": surface,
        "trust_boundary": trust_boundary,
        "public_projection_only": public_projection,
        "direct_internal_data_plane_access": data_plane_access,
        "approved_identity_authorization": identity_authorization,
        "selected": _surface_selection(),
    }


def _health_selection(*, readiness: bool = False) -> dict[str, object]:
    selected: dict[str, object] = {
        "endpoint_path": None,
        "listener_port": None,
        "success_status_codes": [],
        "response_schema": None,
    }
    if readiness:
        selected["dependency_set"] = []
    selected.update(
        {
            "interval_seconds": None,
            "timeout_seconds": None,
            "healthy_threshold": None,
            "unhealthy_threshold": None,
        }
    )
    return selected


EXPECTED_LOGICAL_HCL_MODULE: Final = {
    "classification": "PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_COMPUTE_EDGE_GRAPH",
    "module_path": "infra/terraform/compute-edge",
    "terraform_required_version": TERRAFORM_REQUIRED_VERSION,
    "toolchain_lock_source": "ST-1501_PINNED_VALIDATION_ONLY_TOOLCHAIN",
    "generated": True,
    "default_disabled": True,
    "provider_schema_binding": None,
    "provider_requirements": [],
    "provider_blocks": [],
    "backend_blocks": [],
    "cloud_blocks": [],
    "module_blocks": [],
    "data_blocks": [],
    "resource_blocks": [],
    "provisioners": [],
    "physical_resource_materialization": "FORBIDDEN_IN_CURRENT_REVISION",
    "logical_component_count": len(logical_compute_edge_components()),
    "logical_edge_count": len(logical_compute_edge_edges()),
    "logical_workload_count": len(WORKLOAD_COMPONENT_IDS),
    "logical_identity_count": len(IDENTITY_COMPONENT_IDS),
    "logical_health_contract_count": len(WORKLOAD_ROLES),
    "deterministic_no_apply_plan_fixture": LOGICAL_PLAN_PATH.as_posix(),
    "generated_files": [path.name for path in HCL_PATHS],
    "allowed_top_level_blocks": ["terraform", "variable", "locals", "check", "output"],
    "policy_validation": "EXACT_CLOSED_BUNDLE_FORBIDDEN_BLOCK_AND_SAFETY_SCAN",
    "semantic_validation": "TERRAFORM_VALIDATE_JSON_INIT_FREE_PROVIDER_FREE",
}
EXPECTED_SUCCESSOR_ACTIVATION_PORT: Final = {
    "classification": "CLOSED_PHYSICAL_COMPUTE_EDGE_ACTIVATION_PORT",
    "current_revision_activation": "FORBIDDEN",
    "successor_contract_revision_required": True,
    "selected_provider_schema": None,
    "selected_provider_plugin": None,
    "selected_account_or_project": None,
    "selected_region": None,
    "selected_state_backend": None,
    "selected_credential_source": None,
    "selected_network_segments": [],
    "selected_domain_names": [],
    "selected_host_names": [],
    "selected_dns_certificate_references": [],
    "selected_image_digests": [],
    "selected_workload_identity_references": [],
    "selected_secret_references": [],
    "selected_waf_rule_definitions": [],
    "selected_rate_limit_thresholds": [],
    "selected_health_endpoint_bindings": [],
    "required_gate_evidence": list(SUCCESSOR_GATE_EVIDENCE),
    "supplied_gate_evidence": [],
    "complete_gate_evidence": False,
    "provider_binding": "FORBIDDEN_IN_CURRENT_REVISION",
    "physical_resource_materialization": "FORBIDDEN_IN_CURRENT_REVISION",
    "infrastructure_plan": "FORBIDDEN",
    "infrastructure_apply": "FORBIDDEN",
}


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-COMPUTE-EDGE-FOUNDATION-001",
        "version": "1.2.0",
        "story_id": "ST-1503",
        "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_binding": {
        "story_id": "ST-1501",
        "extension_kind": "COMPUTE_CDN_WAF",
        "design_handoff_uri": (
            "repo://changes/st-1501/"
            "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
        ),
        "owner_id": "build_st1501_terraform_foundation",
        "owner_version": 2,
        "contract_uri": (
            "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
        ),
        "reference_plan_uri": (
            "repo://infra/terraform/foundation/"
            "terraform-foundation.reference-plan.v1.json"
        ),
        "toolchain_lock_uri": (
            "repo://infra/terraform/foundation/"
            "terraform-validation-toolchain.lock.v1.json"
        ),
        "toolchain_lock_sha256": PREDECESSOR_SOURCES[
            "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"
        ],
        "required_validation_tool": "Terraform",
        "required_validation_version": TERRAFORM_VERSION,
        "required_validation_platform": TERRAFORM_PLATFORM,
        "required_validation_binary_sha256": TERRAFORM_BINARY_SHA256,
        "required_validation_mode": "PINNED_VALIDATION_ONLY_NO_INFRASTRUCTURE_AUTHORITY",
        "required_provider_policy": (
            "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION"
        ),
        "required_admission_status": "NOT_EVALUATED",
        "required_eligible": False,
        "required_activation_status": "DISABLED",
        "required_resource_payloads": "FORBIDDEN",
        "required_planned_actions": {"create": 0, "update": 0, "delete": 0},
    },
    "reference_architecture": {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
        "inherited_from": "INT-DEC-007",
        "portable_core_required": True,
        "service_mappings": _aws_reference_service_mappings(),
        "default": False,
        "implicit_fallback": False,
        "selected_binding": False,
        "eligibility_shortcut": False,
        "admission_requirement": False,
        "evidence_substitute": False,
    },
    "provider_neutral_compute_edge_admission": {
        "classification": ("STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION"),
        "admission_status": "NOT_EVALUATED",
        "eligible": False,
        "selected_profile_id": None,
        "selected_profile_kind": None,
        "selected_provider_name": None,
        "default_profile_id": None,
        "fallback_profile_id": None,
        "concrete_alternate_provider_selected": False,
        "eligible_profile_kinds": list(ELIGIBLE_PROFILE_KINDS),
        "eligibility_condition": (
            "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE"
        ),
        "binding_policy": _binding_policy(),
        "cross_capability_transport_security_policy": {
            "public_transport": "TLS_REQUIRED_NOT_CONFIGURED",
            "internal_transport": "TLS_REQUIRED_NOT_CONFIGURED",
            "provider_transport": "TLS_REQUIRED_NOT_CONFIGURED",
            "origin_transport": "TLS_REQUIRED_NOT_CONFIGURED",
            "selected_exceptions": [],
        },
        "mapping_policy": {
            "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
            "required_capability_count": len(COMPUTE_EDGE_CAPABILITY_OUTCOMES),
            "configured_mapping_count": 0,
            "complete_mapping": False,
            "missing_mapping": "REJECT",
            "unknown_mapping": "REJECT",
            "duplicate_mapping": "REJECT",
            "implicit_mapping": "REJECT",
            "partial_mapping": "REJECT",
            "provider_label_only_mapping": "REJECT",
            "service_label_only_mapping": "REJECT",
            "reference_only_mapping": "REJECT",
        },
        "aws_reference_boundary": {
            "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "canonical_story_deliverables": (
                "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
            ),
            "non_aws_owner_managed_profiles": (
                "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
            ),
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "evidence_equivalence_policy": {
            "identical_security_evidence": "REQUIRED",
            "identical_operations_evidence": "REQUIRED",
            "identical_release_evidence": "REQUIRED",
            "identical_performance_load_evidence": "REQUIRED",
            "identical_health_slo_alerting_evidence": "REQUIRED",
            "identical_canary_rollback_evidence": "REQUIRED",
            "identical_identity_secret_egress_evidence": "REQUIRED",
            "identical_isolation_evidence": "REQUIRED",
            "identical_region_residency_evidence": "REQUIRED",
            "identical_transport_security_evidence": "REQUIRED",
            "provider_label_as_evidence": "FORBIDDEN",
            "service_label_as_evidence": "FORBIDDEN",
            "reference_metadata_as_evidence": "FORBIDDEN",
            "local_test_as_live_evidence": "FORBIDDEN",
        },
        "capability_mapping_requirements": _capability_mapping_requirements(),
    },
    "selected_configuration": {
        "provider_name": None,
        "provider_account_or_project": None,
        "production_region": None,
        "workload_runtime_binding": None,
        "scheduler_binding": None,
        "image_registry_binding": None,
        "ingress_edge_binding": None,
        "dns_binding": None,
        "tls_certificate_binding": None,
        "waf_abuse_control_binding": None,
        "compute_edge_plugin_or_adapter": None,
        "credential_source": None,
        "network_segment_ids": [],
        "ingress_policy_ids": [],
        "egress_policy_ids": [],
        "workload_identity_references": [],
        "secret_references": [],
        "physical_resource_definitions": [],
    },
    "workload_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_WORKLOAD_INTENT_ONLY",
        "runtime_and_scheduler": "REQUIRED_NOT_CONFIGURED",
        "immutable_digest_selected_images": "REQUIRED_NOT_CONFIGURED",
        "signed_provenance": "REQUIRED_NOT_CONFIGURED",
        "sbom": "REQUIRED_NOT_CONFIGURED",
        "image_scanning": "REQUIRED_NOT_CONFIGURED",
        "bounded_scaling": "REQUIRED_NOT_CONFIGURED",
        "failure_domain_distribution": "REQUIRED_NOT_CONFIGURED",
        "least_privilege_workload_identities": "REQUIRED_NOT_CONFIGURED",
        "controlled_egress": "REQUIRED_NOT_CONFIGURED",
        "encrypted_logs": "REQUIRED_NOT_CONFIGURED",
        "graceful_shutdown": "REQUIRED_NOT_CONFIGURED",
        "secret_material": "ABSENT",
        "roles": [
            _workload_intent(
                "public_web",
                "PUBLIC",
                "EDGE_MEDIATED_REQUIRED_NOT_CONFIGURED",
                "FORBIDDEN",
                "REQUIRED",
                "NOT_APPLICABLE",
            ),
            _workload_intent(
                "admin_web",
                "ADMIN",
                "EDGE_MEDIATED_REQUIRED_NOT_CONFIGURED",
                "PRIVATE_CORE_API_ONLY_NOT_CONFIGURED",
                "NOT_APPLICABLE",
                "REQUIRED_NOT_CONFIGURED",
            ),
            _workload_intent(
                "core_api",
                "INTERNAL",
                "PRIVATE_ONLY_REQUIRED",
                "LEAST_PRIVILEGE_REQUIRED_NOT_CONFIGURED",
                "NOT_APPLICABLE",
                "REQUIRED_NOT_CONFIGURED",
            ),
            _workload_intent(
                "worker_pool",
                "INTERNAL",
                "PRIVATE_ONLY_REQUIRED",
                "LEAST_PRIVILEGE_REQUIRED_NOT_CONFIGURED",
                "NOT_APPLICABLE",
                "SERVICE_IDENTITY_REQUIRED_NOT_CONFIGURED",
            ),
        ],
    },
    "surface_boundary_intent": {
        "classification": (
            "DISTINCT_PROVIDER_NEUTRAL_SURFACE_BOUNDARIES_REQUIRED_NOT_CONFIGURED"
        ),
        "trust_boundary_separation": "REQUIRED_NOT_CONFIGURED",
        "route_separation": "REQUIRED_NOT_CONFIGURED",
        "cache_separation": "REQUIRED_NOT_CONFIGURED",
        "cookie_separation": "REQUIRED_NOT_CONFIGURED",
        "host_separation": "REQUIRED_NOT_CONFIGURED",
        "csp_separation": "REQUIRED_NOT_CONFIGURED",
        "authentication_separation": "REQUIRED_NOT_CONFIGURED",
        "public_data_plane_access": "FORBIDDEN",
        "surfaces": [
            _surface_intent(
                "public", "PUBLIC", "FORBIDDEN", "REQUIRED", "NOT_APPLICABLE"
            ),
            _surface_intent(
                "admin",
                "ADMIN",
                "PRIVATE_CORE_API_ONLY_NOT_CONFIGURED",
                "NOT_APPLICABLE",
                "REQUIRED_NOT_CONFIGURED",
            ),
            _surface_intent(
                "internal",
                "INTERNAL",
                "LEAST_PRIVILEGE_REQUIRED_NOT_CONFIGURED",
                "NOT_APPLICABLE",
                "SERVICE_IDENTITY_REQUIRED_NOT_CONFIGURED",
            ),
        ],
    },
    "edge_routing_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_EDGE_ROUTING_INTENT_ONLY",
        "edge_only_public_entry": "REQUIRED_NOT_CONFIGURED",
        "origin_private_only": "REQUIRED",
        "origin_authentication": "REQUIRED_NOT_CONFIGURED",
        "api_worker_data_origins_private_only": "REQUIRED",
        "direct_origin_public_access": "FORBIDDEN",
        "dns_zone_control": "REQUIRED_NOT_CONFIGURED",
        "tls_transport_security": "REQUIRED_NOT_CONFIGURED",
        "certificate_lifecycle": "REQUIRED_NOT_CONFIGURED",
        "waf_attack_controls": "REQUIRED_NOT_CONFIGURED",
        "abuse_rate_limiting": "REQUIRED_NOT_CONFIGURED",
        "cache_policy_separation": "REQUIRED_NOT_CONFIGURED",
        "selected": {
            "edge_resource_reference": None,
            "ingress_resource_reference": None,
            "origin_references": [],
            "route_definitions": [],
            "tls_certificate_reference": None,
            "dns_zone_reference": None,
            "dns_record_references": [],
            "domain_names": [],
            "host_names": [],
            "waf_policy_reference": None,
            "waf_rule_definitions": [],
            "rate_limit_thresholds": [],
            "cache_policy_references": [],
        },
    },
    "health_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_HEALTH_RELEASE_INTENT_ONLY",
        "roles": list(WORKLOAD_ROLES),
        "telemetry": "REQUIRED_NOT_CONFIGURED",
        "slo_capacity": "REQUIRED_NOT_CONFIGURED",
        "alert_owner": "REQUIRED_NOT_CONFIGURED",
        "alert_runbook": "REQUIRED_NOT_CONFIGURED",
        "canary_promotion": "REQUIRED_NOT_CONFIGURED",
        "human_release_approval": "REQUIRED",
        "rollback": "REQUIRED_NOT_CONFIGURED",
        "kill_switch_change": "HUMAN_APPROVAL_REQUIRED",
        "liveness": {
            "purpose": "PROCESS_ONLY",
            "external_dependency_coupling": "FORBIDDEN",
            "bounded_failure_behavior": "REQUIRED_NOT_CONFIGURED",
            "selected": _health_selection(),
        },
        "readiness": {
            "purpose": "DEPENDENCY_AND_MIGRATION_READINESS",
            "dependency_check": "REQUIRED_NOT_CONFIGURED",
            "migration_compatibility_check": "REQUIRED_NOT_CONFIGURED",
            "bounded_failure_behavior": "REQUIRED_NOT_CONFIGURED",
            "infer_from_http_200_body": "FORBIDDEN",
            "selected": _health_selection(readiness=True),
        },
    },
    "logical_hcl_module": copy.deepcopy(EXPECTED_LOGICAL_HCL_MODULE),
    "successor_activation_port": copy.deepcopy(EXPECTED_SUCCESSOR_ACTIVATION_PORT),
    "open_decision_boundary": {
        "OD-002": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": (
                "EXAMPLE_INVALID_PROVISIONAL_BRAND_EXTERNAL_PUBLICATION_FORBIDDEN"
            ),
        },
        "OD-009": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "LOW_DEVELOPMENT_CAP_PRODUCTION_DISABLED",
        },
        "OD-010": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": (
                "LOCAL_FAKE_AUTH_DEVELOPMENT_ONLY_EXTERNAL_PUBLICATION_FORBIDDEN"
            ),
        },
        "OD-011": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "LOCAL_LOG_ONLY_PRODUCTION_UNAVAILABLE",
        },
        "OD-013": {
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": "REFERENCE_REGION_ONLY_PRODUCTION_APPLY_FORBIDDEN",
        },
        "OD-015": {
            "status": "EXTERNAL_EVIDENCE_REQUIRED",
            "resolved": False,
            "blocking": True,
            "safe_default": (
                "RECORDED_FIXTURE_ONLY_CREDENTIALS_ABSENT_PROVIDER_CALLS_FORBIDDEN"
            ),
        },
    },
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "commands": {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
        "planned_actions": {action: 0 for action in ACTION_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_COMPUTE_EDGE_MODULE"
        ),
        "executable_terraform": "VALIDATION_ONLY_PROVIDER_FREE_LOGICAL_MODULE",
        "terraform_cli": "PINNED_1_15_9_VALIDATION_ONLY",
        "provider_plugins": "ABSENT_NO_PROVIDER_REQUIRED_OR_SELECTED",
        "provider_account_or_project": "UNSET",
        "credentials": "ABSENT",
        "native_iac_validation": "EXECUTED_LOCAL_NOT_FORMAL",
        "formal_tst_026": "NOT_EXECUTED",
        "formal_tst_027": "NOT_EXECUTED",
        "performance_load_validation": "NOT_EXECUTED",
        "health_slo_alert_validation": "NOT_EXECUTED",
        "canary_rollback_validation": "NOT_EXECUTED",
        "identity_secret_egress_validation": "NOT_EXECUTED",
        "region_residency_validation": "NOT_EXECUTED",
        "transport_security_validation": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}

TOP_LEVEL_KEYS: Final = {"sources", *EXPECTED_SECTIONS}


class ComputeEdgeContractError(RuntimeError):
    """A sanitized validation failure that never includes rejected values."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class NoAliasDumper(yaml.SafeDumper):
    """Deterministic YAML dumper without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    construct_object = cast(
        Callable[[object, bool], Any], getattr(loader, "construct_object")
    )
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = construct_object(key_node, deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found duplicate key",
                key_node.start_mark,
            )
        result[key] = construct_object(value_node, deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class ComputeEdgeModel:
    """A fully validated, closed ST-1503 contract."""

    contract: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class NativeValidationResult:
    """Sanitized result of the validation-only Terraform execution."""

    terraform_version: str
    platform: str
    provider_selections: tuple[str, ...]
    format_valid: bool
    semantic_valid: bool
    network_namespace: bool
    repository_unchanged: bool


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def semantic_sha256(document: object) -> str:
    try:
        content = json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        _fail("SEMANTIC_DOCUMENT_INVALID", "semantic_document")
    return sha256_bytes(content)


def _fail(code: str, field: str) -> NoReturn:
    raise ComputeEdgeContractError(code, field)


def _as_object(value: Any) -> object:
    """Erase incomplete third-party generic types at a checked boundary."""
    return value


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("TYPE_MISMATCH", field)
    untyped_mapping = cast(Mapping[object, object], value)
    if not all(type(key) is str for key in untyped_mapping):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[object]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return cast(list[object], value)


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("CLOSED_SCHEMA_VIOLATION", field)


def _strict_match(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        value = _mapping(actual, field)
        expected_mapping = _mapping(_as_object(expected), field)
        _exact_keys(value, set(expected_mapping), field)
        for key, expected_value in expected_mapping.items():
            _strict_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(_as_object(expected), field)
        if not expected_list and value_list:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        if len(value_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_match(value_list[index], expected_value, f"{field}.item")
        return
    if expected is None:
        if actual is not None:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        return
    if type(actual) is not type(expected):
        _fail("TYPE_MISMATCH", field)
    if actual != expected:
        if type(expected) is bool or (type(expected) is int and expected == 0):
            _fail("SAFE_BOUNDARY_VIOLATION", field)
        _fail("FIXED_VALUE_VIOLATION", field)


def _regular_file(path: Path, field: str) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("UNSAFE_FILE_TYPE", field)


def _real_repository_root(root: Path) -> Path:
    try:
        metadata = root.lstat()
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    try:
        return root.resolve(strict=True)
    except OSError:
        _fail("ROOT_UNAVAILABLE", "repository")


def _repository_regular_file(root: Path, relative: Path, field: str) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except OSError:
            _fail("FILE_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_ANCESTOR", field)
    target = current / relative.name
    _regular_file(target, field)
    return target


def load_yaml(path: Path) -> Any:
    _regular_file(path, "yaml")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "yaml")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("YAML_SIZE_LIMIT", "yaml")
    try:
        text = content.decode("utf-8")
        scan_yaml = cast(Callable[[str], Iterable[object]], getattr(yaml, "scan"))
        for token in scan_yaml(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", "yaml")
        return yaml.load(text, Loader=UniqueKeyLoader)
    except ComputeEdgeContractError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", "yaml")


def load_json(path: Path) -> Any:
    _regular_file(path, "json")
    try:
        content = path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "json")
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("JSON_SIZE_LIMIT", "json")

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("JSON_DUPLICATE_KEY", "json")
            result[key] = value
        return result

    try:
        return json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _fail("JSON_INVALID", "json"),
        )
    except ComputeEdgeContractError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", "json")


def _repo_relative_uri(value: object) -> Path:
    if type(value) is not str or not value.startswith("repo://"):
        _fail("SOURCE_URI_INVALID", "sources")
    raw = value.removeprefix("repo://")
    if not raw or "\\" in raw:
        _fail("SOURCE_URI_INVALID", "sources")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        _fail("SOURCE_URI_INVALID", "sources")
    return Path(*pure.parts)


def _validate_sources(contract: Mapping[str, Any], root: Path) -> None:
    rows = _list(contract["sources"], "sources")
    observed: dict[str, str] = {}
    observed_order: list[str] = []
    for raw_row in rows:
        row = _mapping(raw_row, "sources.item")
        _exact_keys(row, {"uri", "sha256"}, "sources.item")
        relative = _repo_relative_uri(row["uri"])
        digest = row["sha256"]
        if type(digest) is not str or SHA256_PATTERN.fullmatch(digest) is None:
            _fail("SOURCE_DIGEST_INVALID", "sources.item.sha256")
        key = relative.as_posix()
        if key in observed:
            _fail("SOURCE_DUPLICATE", "sources")
        observed[key] = digest
        observed_order.append(key)
    if tuple(observed_order) != tuple(PINNED_SOURCES):
        _fail("SOURCE_INVENTORY_DRIFT", "sources")
    for source_name, expected_digest in PINNED_SOURCES.items():
        source = _repository_regular_file(root, Path(source_name), "pinned_source")
        if input_hash_required(source_name) and (
            observed[source_name] != expected_digest
            or sha256_file(source) != expected_digest
        ):
            _fail("SOURCE_DIGEST_MISMATCH", "pinned_source")


def _find_exact_record(
    document: Mapping[str, Any], collection: str, record_id: str, field: str
) -> Mapping[str, Any]:
    rows = _list(document.get(collection), field)
    matches: list[Mapping[str, Any]] = []
    for raw_row in rows:
        row = _mapping(raw_row, field)
        if row.get("id") == record_id:
            matches.append(row)
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_MISSING", field)
    return matches[0]


def _validate_design_handoff(root: Path) -> None:
    handoff = _mapping(
        load_yaml(_repository_regular_file(root, DESIGN_HANDOFF_PATH, "handoff")),
        "handoff",
    )
    _exact_keys(
        handoff,
        {
            "schema",
            "version",
            "record_status",
            "approved_story",
            "approved_scope",
            "source_design_refs",
            "decision",
            "rationale",
            "rejected_alternatives",
            "constraints",
            "security_and_approval_gates",
            "acceptance_criteria",
            "required_test_evidence",
            "open_decision_state",
        },
        "handoff",
    )
    _strict_match(handoff.get("schema"), "DESIGN_HANDOFF_V1", "handoff.schema")
    _strict_match(handoff.get("version"), 1, "handoff.version")
    _strict_match(
        handoff.get("record_status"),
        "RECORDED_DURABLE_OWNER_DECISION",
        "handoff.record_status",
    )
    _strict_match(handoff.get("approved_story"), "ST-1503", "handoff.story")
    _strict_match(
        handoff.get("source_design_refs"),
        list(EXPECTED_HANDOFF_SOURCE_DESIGN_REFS),
        "handoff.source_design_refs",
    )
    _strict_match(
        handoff.get("decision"),
        {
            "compute_edge_provider_policy": (
                "STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION"
            ),
            "selected_profile": None,
            "default_profile": None,
            "fallback_profile": None,
            "concrete_alternate_provider_selected": False,
            "eligible_profile_kinds": list(ELIGIBLE_PROFILE_KINDS),
            "eligibility_condition": (
                "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE"
            ),
            "aws_reference_mapping_boundary": {
                "canonical_decision_id": "INT-DEC-007",
                "architecture_id": "RAOS-ARCH-001",
                "classification": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
                "canonical_story_deliverables": (
                    "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
                ),
                "non_aws_owner_managed_profiles": (
                    "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
                ),
                "mappings": _aws_reference_service_mappings(),
                "default": False,
                "implicit_fallback": False,
                "selected_binding": False,
                "eligibility_shortcut": False,
                "admission_requirement": False,
                "evidence_substitute": False,
            },
            "binding_policy": _binding_policy(),
            "cross_capability_transport_security_requirements": {
                "public_transport": "TLS_REQUIRED_NOT_CONFIGURED",
                "internal_transport": "TLS_REQUIRED_NOT_CONFIGURED",
                "provider_transport": "TLS_REQUIRED_NOT_CONFIGURED",
                "origin_transport": "TLS_REQUIRED_NOT_CONFIGURED",
                "selected_exceptions": [],
            },
            "required_capability_ids": [
                capability_id
                for capability_id, _required_outcome in (
                    COMPUTE_EDGE_CAPABILITY_OUTCOMES
                )
            ],
        },
        "handoff.decision",
    )
    _strict_match(
        handoff.get("open_decision_state"),
        EXPECTED_SECTIONS["open_decision_boundary"],
        "handoff.open_decision_state",
    )
def _validate_authority_semantics(root: Path) -> None:
    backlog = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
                "backlog",
            )
        ),
        "backlog",
    )
    story = _find_exact_record(backlog, "stories", "ST-1503", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1503")

    canonical_decisions = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path(
                    "docs/canonical/01_integration/"
                    "RAOS_07_canonical_decisions_v1.0.yaml"
                ),
                "canonical_decisions",
            )
        ),
        "canonical_decisions",
    )
    int_dec_007 = _find_exact_record(
        canonical_decisions,
        "decisions",
        "INT-DEC-007",
        "canonical_decisions.decisions",
    )
    _strict_match(int_dec_007, EXPECTED_INT_DEC_007, "INT-DEC-007")

    decisions = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
                "open_decisions",
            )
        ),
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        decision = _find_exact_record(
            decisions, "items", decision_id, "open_decisions.items"
        )
        _strict_match(decision, expected, f"open_decisions.{decision_id}")

    test_catalog = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
                "test_catalog",
            )
        ),
        "test_catalog",
    )
    for test_id, expected in EXPECTED_TESTS.items():
        test = _find_exact_record(test_catalog, "suites", test_id, "test_catalog")
        _strict_match(test, expected, f"test_catalog.{test_id}")

    controls = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path(
                    "docs/canonical/04_security/"
                    "RAOS_10_security_control_catalog_v1.0.yaml"
                ),
                "security_controls",
            )
        ),
        "security_controls",
    )
    for control_id, requirement in EXPECTED_SECURITY_CONTROLS.items():
        control = _find_exact_record(
            controls, "controls", control_id, "security_controls.controls"
        )
        if (
            type(control.get("requirement")) is not str
            or control.get("requirement") != requirement
            or control.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or control.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_CONTROL_DRIFT", control_id)

    architecture = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path(
                    "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml"
                ),
                "architecture_catalog",
            )
        ),
        "architecture_catalog",
    )
    architecture_document = _mapping(architecture.get("document"), "architecture")
    if architecture_document.get("id") != "RAOS-ARCH-001":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "RAOS-ARCH-001")
    architecture_body = _mapping(architecture.get("architecture"), "architecture")
    _strict_match(
        architecture_body.get("cloud_reference"),
        {
            "provider": "AWS",
            "region": "ap-northeast-1",
            "portable_core_required": True,
        },
        "architecture.cloud_reference",
    )
    deployment = _mapping(architecture.get("deployment"), "architecture.deployment")
    aws_mapping = _mapping(deployment.get("aws_mapping"), "deployment.aws_mapping")
    for key, expected_service in {
        "dns": "Route53",
        "cdn_waf_tls": "CloudFront_WAF_ACM",
        "load_balancer": "ALB",
        "compute": "ECS_Fargate",
        "registry": "ECR",
    }.items():
        if aws_mapping.get(key) != expected_service:
            _fail("AUTHORITY_ARCHITECTURE_DRIFT", f"aws_mapping.{key}")
    if deployment.get("infrastructure_as_code") != "Terraform":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "infrastructure_as_code")
    security = _mapping(architecture.get("security"), "architecture.security")
    _strict_match(
        security.get("network"),
        [
            "cdn_waf_public_entry",
            "private_api_worker_db",
            "db_not_public",
            "object_public_access_block",
            "controlled_egress",
        ],
        "architecture.security.network",
    )
    web = _find_exact_record(architecture, "containers", "web", "containers")
    api = _find_exact_record(architecture, "containers", "api", "containers")
    worker = _find_exact_record(architecture, "containers", "worker", "containers")
    if web.get("technology") != "Next.js_TypeScript":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "containers.web")
    if api.get("technology") != "FastAPI_Python":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "containers.api")
    if worker.get("technology") != "Python":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "containers.worker")
    web_responsibilities = _list(web.get("responsibilities"), "containers.web")
    api_responsibilities = _list(api.get("responsibilities"), "containers.api")
    if not {"public_ssr_or_static_rendering", "admin_ui"}.issubset(
        set(web_responsibilities)
    ):
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "containers.web")
    if not {
        "admin_public_internal_rest_api",
        "authentication_authorization",
    }.issubset(set(api_responsibilities)):
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "containers.api")
    _validate_design_handoff(root)


def _validate_predecessor_semantics_v1(  # pyright: ignore[reportUnusedFunction]
    root: Path,
) -> None:
    contract = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path("changes/st-1501/contracts/terraform-foundation.v1.yaml"),
                "predecessor_contract",
            )
        ),
        "predecessor_contract",
    )
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-TERRAFORM-FOUNDATION-001",
            "version": "1.1.0",
            "story_id": "ST-1501",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.document",
    )
    _strict_match(
        contract.get("reference_architecture"),
        {
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
        },
        "predecessor.reference_architecture",
    )
    admission = _mapping(
        contract.get("provider_neutral_foundation_admission"),
        "predecessor.admission",
    )
    _strict_match(
        admission.get("classification"),
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
        "predecessor.admission.classification",
    )
    _strict_match(
        admission.get("admission_status"),
        "NOT_EVALUATED",
        "predecessor.admission.status",
    )
    _strict_match(admission.get("eligible"), False, "predecessor.admission.eligible")
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(admission.get(field), None, f"predecessor.admission.{field}")
    _strict_match(
        admission.get("concrete_alternate_provider_selected"),
        False,
        "predecessor.admission.concrete_alternate_provider_selected",
    )
    _strict_match(
        admission.get("aws_reference_boundary"),
        {
            "role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "canonical_story_deliverables": (
                "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
            ),
            "non_aws_owner_managed_profiles": (
                "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
            ),
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "predecessor.admission.aws_reference_boundary",
    )
    _strict_match(
        contract.get("selected_configuration"),
        {
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
        },
        "predecessor.selected_configuration",
    )
    execution = _mapping(contract.get("execution_boundary"), "predecessor.execution")
    _strict_match(
        execution,
        {
            "activation_enabled": False,
            "activation_status": "DISABLED",
            "native_plan_status": "NOT_EXECUTED",
            "network_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "live_provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "deploy_action": "FORBIDDEN",
            "release_action": "FORBIDDEN",
            "production_action": "FORBIDDEN",
            "commands": {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
            "planned_actions": {action: 0 for action in PREDECESSOR_ACTION_NAMES},
        },
        "predecessor.execution",
    )
    extension = _mapping(contract.get("extension_contract"), "predecessor.extension")
    _strict_match(
        extension,
        {
            "current_resource_payloads": "FORBIDDEN",
            "successor_contract_revision_required": True,
            "native_toolchain_pin_required_before_hcl": True,
            "successors": {
                "ST-1502": "DATA_SERVICES",
                "ST-1503": "COMPUTE_CDN_WAF",
            },
        },
        "predecessor.extension",
    )
    evidence = _mapping(contract.get("evidence_boundary"), "predecessor.evidence")
    _strict_match(
        evidence,
        {
            "deliverable_classification": "SOURCE_DERIVED_REFERENCE_STATE_PLAN",
            "executable_terraform": "ABSENT",
            "terraform_cli": "UNPINNED_NOT_INVOKED",
            "provider_plugins": "UNPINNED_NOT_INVOKED",
            "remote_state": "NOT_CONFIGURED",
            "provider_account_or_project": "UNSET",
            "credentials": "ABSENT",
            "formal_tst_026": "NOT_EXECUTED",
            "live_staging_release_production": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
        "predecessor.evidence",
    )

    plan_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"),
        "predecessor_plan",
    )
    plan = _mapping(load_json(plan_path), "predecessor_plan")
    expected_plan = {
        "document": {
            "id": "RAOS-TERRAFORM-FOUNDATION-REFERENCE-PLAN-001",
            "version": "1.1.0",
            "story_id": "ST-1501",
            "source_contract": (
                "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
            ),
            "generated_by": "repo://scripts/build_st1501_terraform_foundation.py",
            "generation_command": (
                "uv run --locked --no-sync python "
                "scripts/build_st1501_terraform_foundation.py"
            ),
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "reference_architecture": copy.deepcopy(contract["reference_architecture"]),
        "provider_neutral_foundation_admission": copy.deepcopy(admission),
        "selected_configuration": copy.deepcopy(contract["selected_configuration"]),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "native_commands": copy.deepcopy(execution["commands"]),
        },
        "future_requirements": {
            "remote_state": copy.deepcopy(contract["state_requirements"]),
            "account_separation": {
                "requirement": contract["account_requirements"][
                    "separate_development_and_production"
                ],
                "development_account_id": contract["account_requirements"][
                    "development_account_id"
                ],
                "production_account_id": contract["account_requirements"][
                    "production_account_id"
                ],
            },
            "production_change_control": copy.deepcopy(
                contract["production_change_requirements"]
            ),
        },
        "extension_contract": copy.deepcopy(extension),
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }
    _strict_match(plan, expected_plan, "predecessor_plan")
    expected_plan_bytes = (
        json.dumps(
            expected_plan,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    try:
        actual_plan_bytes = plan_path.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", "predecessor_plan")
    if actual_plan_bytes != expected_plan_bytes:
        _fail("PREDECESSOR_GENERATED_DRIFT", "predecessor_plan")


def _validate_predecessor_semantics(root: Path) -> None:
    paths = (
        (
            Path(
                "changes/st-1501/"
                "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
            ),
            "predecessor_handoff",
            True,
        ),
        (
            Path("changes/st-1501/contracts/terraform-foundation.v1.yaml"),
            "predecessor_contract",
            True,
        ),
        (
            Path(
                "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
            ),
            "predecessor_plan",
            False,
        ),
        (
            Path(
                "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"
            ),
            "predecessor_toolchain",
            False,
        ),
    )
    documents: dict[str, Mapping[str, Any]] = {}
    for relative, field, is_yaml in paths:
        path = _repository_regular_file(root, relative, field)
        loaded = load_yaml(path) if is_yaml else load_json(path)
        document = _mapping(loaded, field)
        if input_hash_required(relative.as_posix()) and semantic_sha256(
            document
        ) != EXPECTED_PREDECESSOR_TOOLCHAIN_SEMANTIC_SHA256:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", field)
        documents[field] = document

    for field, relative in (
        (
            "predecessor_plan",
            Path(
                "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
            ),
        ),
        (
            "predecessor_toolchain",
            Path(
                "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"
            ),
        ),
    ):
        expected_bytes = (
            json.dumps(documents[field], ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        actual_path = _repository_regular_file(root, relative, field)
        if actual_path.read_bytes() != expected_bytes:
            _fail("PREDECESSOR_GENERATED_DRIFT", field)

    contract = documents["predecessor_contract"]
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-TERRAFORM-FOUNDATION-001",
            "version": "1.2.0",
            "story_id": "ST-1501",
            "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.document",
    )
    execution = _mapping(contract.get("execution_boundary"), "predecessor.execution")
    _strict_match(execution.get("activation_enabled"), False, "predecessor.activation")
    _strict_match(
        execution.get("planned_actions"),
        {action: 0 for action in PREDECESSOR_ACTION_NAMES},
        "predecessor.planned_actions",
    )
    toolchain = documents["predecessor_toolchain"]
    tool = _mapping(toolchain.get("toolchain"), "predecessor.toolchain")
    _strict_match(tool.get("product"), "Terraform", "predecessor.toolchain.product")
    _strict_match(
        tool.get("version"), TERRAFORM_VERSION, "predecessor.toolchain.version"
    )
    _strict_match(
        tool.get("platform"), TERRAFORM_PLATFORM, "predecessor.toolchain.platform"
    )
    release = _mapping(
        tool.get("official_release"), "predecessor.toolchain.official_release"
    )
    _strict_match(
        release.get("extracted_binary_sha256"),
        TERRAFORM_BINARY_SHA256,
        "predecessor.toolchain.binary",
    )
    boundary = _mapping(
        tool.get("validation_boundary"), "predecessor.toolchain.validation_boundary"
    )
    _strict_match(
        boundary.get("allowed_commands"),
        ["version -json", "fmt -check -recursive", "validate -json"],
        "predecessor.toolchain.allowed_commands",
    )
    for key in (
        "initialization",
        "provider_installation",
        "module_downloads",
        "backend_access",
        "credential_inheritance",
        "repository_writes",
    ):
        _strict_match(boundary.get(key), "FORBIDDEN", f"predecessor.toolchain.{key}")
    _strict_match(
        boundary.get("network_namespace"), "REQUIRED", "predecessor.toolchain.network"
    )
    _strict_match(
        boundary.get("provider_plugins"), [], "predecessor.toolchain.providers"
    )


def _validate_capability_inventory(contract: Mapping[str, Any]) -> None:
    admission = _mapping(
        contract["provider_neutral_compute_edge_admission"],
        "provider_neutral_compute_edge_admission",
    )
    rows = _list(
        admission["capability_mapping_requirements"],
        "provider_neutral_compute_edge_admission.capability_mapping_requirements",
    )
    observed: list[str] = []
    for row in rows:
        item = _mapping(
            row,
            "provider_neutral_compute_edge_admission."
            "capability_mapping_requirements.item",
        )
        capability_id = item.get("capability_id")
        if type(capability_id) is not str:
            _fail("TYPE_MISMATCH", "capability_mapping.capability_id")
        observed.append(capability_id)
    expected = [
        capability_id
        for capability_id, _required_outcome in COMPUTE_EDGE_CAPABILITY_OUTCOMES
    ]
    if len(observed) != len(set(observed)):
        _fail("DUPLICATE_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in expected for capability_id in observed):
        _fail("UNKNOWN_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in observed for capability_id in expected):
        _fail("MISSING_CAPABILITY_MAPPING", "capability_mapping")
    if observed != expected:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "capability_mapping")


def validate_contract(contract: object, root: Path = REPO_ROOT) -> ComputeEdgeModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    _validate_capability_inventory(value)
    for section, expected in EXPECTED_SECTIONS.items():
        _strict_match(value[section], expected, section)
    return ComputeEdgeModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> ComputeEdgeModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: ComputeEdgeModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: ComputeEdgeModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-COMPUTE-EDGE-REFERENCE-PLAN-001",
            "version": "1.2.0",
            "story_id": "ST-1503",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        },
        "predecessor_binding": _section(model, "predecessor_binding"),
        "reference_architecture": _section(model, "reference_architecture"),
        "provider_neutral_compute_edge_admission": _section(
            model, "provider_neutral_compute_edge_admission"
        ),
        "selected_configuration": _section(model, "selected_configuration"),
        "logical_compute_edge": {
            "workloads": _section(model, "workload_intent"),
            "surfaces": _section(model, "surface_boundary_intent"),
            "edge_routing": _section(model, "edge_routing_intent"),
            "health": _section(model, "health_intent"),
        },
        "logical_hcl_module": _section(model, "logical_hcl_module"),
        "successor_activation_port": _section(model, "successor_activation_port"),
        "open_decision_boundary": _section(model, "open_decision_boundary"),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "native_commands": copy.deepcopy(execution["commands"]),
        },
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }


def render_reference_plan(model: ComputeEdgeModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def logical_plan_document(model: ComputeEdgeModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    return {
        "document": {
            "id": "RAOS-COMPUTE-EDGE-LOGICAL-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-1503",
            "classification": "DETERMINISTIC_NO_APPLY_LOGICAL_COMPUTE_EDGE_GRAPH",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "terraform_version": TERRAFORM_VERSION,
            "provider_schema_bound": False,
            "provider_plugin_required": False,
            "physical_resources": False,
            "terraform_state": False,
        },
        "reference_architecture": _section(model, "reference_architecture"),
        "module": _section(model, "logical_hcl_module"),
        "components": logical_compute_edge_components(),
        "edges": logical_compute_edge_edges(),
        "identity_permissions": {
            identity: list(permissions)
            for identity, permissions in IDENTITY_PERMISSIONS.items()
        },
        "health_contracts": _health_contracts(),
        "surface_policies": {
            "public": {
                "trust_boundary": "PUBLIC",
                "public_projection_only": True,
                "shared_cache_allowed": True,
                "cookie_boundary": "DISTINCT",
                "csp_boundary": "DISTINCT",
                "authentication": "NOT_APPLICABLE",
                "direct_internal_data_plane_access": "FORBIDDEN",
            },
            "admin": {
                "trust_boundary": "ADMIN",
                "public_projection_only": False,
                "shared_cache_allowed": False,
                "cookie_boundary": "DISTINCT",
                "csp_boundary": "DISTINCT",
                "authentication": "APPROVED_IDENTITY_REQUIRED_NOT_CONFIGURED",
                "direct_internal_data_plane_access": "PRIVATE_CORE_API_ONLY",
            },
            "internal": {
                "trust_boundary": "INTERNAL",
                "public_projection_only": False,
                "shared_cache_allowed": False,
                "cookie_boundary": "NOT_APPLICABLE",
                "csp_boundary": "NOT_APPLICABLE",
                "authentication": "SERVICE_IDENTITY_REQUIRED_NOT_CONFIGURED",
                "direct_internal_data_plane_access": "LEAST_PRIVILEGE_ONLY",
            },
        },
        "successor_activation_port": _section(model, "successor_activation_port"),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "execution_boundary": {
            "activation_enabled": False,
            "network_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "init": "FORBIDDEN",
            "plan": "FORBIDDEN",
            "apply": "FORBIDDEN",
        },
    }


def validate_logical_plan_document(document: object) -> None:
    plan = _mapping(document, "logical_plan")
    _exact_keys(
        plan,
        {
            "document",
            "reference_architecture",
            "module",
            "components",
            "edges",
            "identity_permissions",
            "health_contracts",
            "surface_policies",
            "successor_activation_port",
            "planned_actions",
            "execution_boundary",
        },
        "logical_plan",
    )
    metadata = _mapping(plan["document"], "logical_plan.document")
    for field in (
        "provider_schema_bound",
        "provider_plugin_required",
        "physical_resources",
        "terraform_state",
    ):
        if metadata.get(field) is not False:
            _fail("LOGICAL_PLAN_PHYSICAL_BINDING_FORBIDDEN", "logical_plan")
    components = [
        _mapping(row, "logical_plan.component")
        for row in _list(plan["components"], "logical_plan.components")
    ]
    expected_components = logical_compute_edge_components()
    component_ids = [component.get("component_id") for component in components]
    expected_ids = [component["component_id"] for component in expected_components]
    if component_ids != expected_ids or len(component_ids) != len(set(component_ids)):
        _fail("LOGICAL_PLAN_COMPONENT_INVENTORY_DRIFT", "logical_plan")
    for component in components:
        component_id = component.get("component_id")
        if component.get("secret_material_present") is not False:
            _fail("LOGICAL_PLAN_SECRET_MATERIAL_FORBIDDEN", "logical_plan")
        if component.get("direct_data_plane_access") is not False:
            _fail("LOGICAL_PLAN_DATA_PLANE_EXPOSURE", "logical_plan")
        if component.get("transport_encryption_required") is not True:
            _fail("LOGICAL_PLAN_TRANSPORT_ENCRYPTION_DISABLED", "logical_plan")
        if component_id in WORKLOAD_COMPONENT_IDS:
            for required in (
                "immutable_image_required",
                "digest_selection_required",
                "signed_provenance_required",
                "sbom_required",
                "image_scan_required",
                "controlled_egress_required",
                "canary_required",
                "rollback_required",
            ):
                if component.get(required) is not True:
                    _fail("LOGICAL_PLAN_WORKLOAD_SUPPLY_CHAIN_WEAKENED", "logical_plan")
            if component.get("publicly_addressable") is not False:
                _fail("LOGICAL_PLAN_PRIVATE_ORIGIN_EXPOSED", "logical_plan")
        if component_id in EDGE_COMPONENT_IDS:
            if (
                component.get("publicly_addressable") is not True
                or component.get("edge_mediated") is not True
                or component.get("waf_required") is not True
                or component.get("rate_limit_required") is not True
            ):
                _fail("LOGICAL_PLAN_EDGE_BOUNDARY_WEAKENED", "logical_plan")
        elif component.get("publicly_addressable") is True and not str(
            component_id
        ).startswith("dns_tls_"):
            _fail("LOGICAL_PLAN_PUBLIC_ENTRY_EXPANDED", "logical_plan")
        if (
            component.get("trust_boundary") in {"ADMIN", "INTERNAL"}
            and component.get("shared_cache_allowed") is not False
        ):
            _fail("LOGICAL_PLAN_SHARED_CACHE_ISOLATION", "logical_plan")
    _strict_match(components, expected_components, "logical_plan.components")
    _strict_match(plan["edges"], logical_compute_edge_edges(), "logical_plan.edges")
    permissions = _mapping(
        plan["identity_permissions"], "logical_plan.identity_permissions"
    )
    _exact_keys(permissions, set(IDENTITY_PERMISSIONS), "logical_plan.permissions")
    for identity, expected_permissions in IDENTITY_PERMISSIONS.items():
        observed = _list(permissions[identity], "logical_plan.permissions")
        if any(
            type(permission) is not str
            or permission == "*"
            or permission.endswith(":*")
            or permission.endswith(".*")
            for permission in observed
        ):
            _fail("LOGICAL_PLAN_WILDCARD_IAM", "logical_plan")
        if observed != list(expected_permissions):
            _fail("LOGICAL_PLAN_IAM_POLICY_DRIFT", "logical_plan")
    health = _mapping(plan["health_contracts"], "logical_plan.health_contracts")
    _exact_keys(health, set(WORKLOAD_ROLES), "logical_plan.health_contracts")
    for role in WORKLOAD_ROLES:
        role_health = _mapping(health[role], "logical_plan.health_contract")
        liveness = _mapping(role_health.get("liveness"), "logical_plan.liveness")
        readiness = _mapping(role_health.get("readiness"), "logical_plan.readiness")
        if (
            liveness.get("purpose") != "PROCESS_ONLY"
            or liveness.get("external_provider_dependency") != "FORBIDDEN"
            or liveness.get("database_dependency") != "FORBIDDEN"
            or readiness.get("purpose") != "DEPENDENCY_AND_MIGRATION_READINESS"
            or readiness.get("generic_http_200_inference") != "FORBIDDEN"
            or liveness.get("endpoint_path") is not None
            or readiness.get("endpoint_path") is not None
        ):
            _fail("LOGICAL_PLAN_HEALTH_SEMANTICS_WEAKENED", "logical_plan")
    _strict_match(health, _health_contracts(), "logical_plan.health_contracts")
    surfaces = _mapping(plan["surface_policies"], "logical_plan.surface_policies")
    if (
        _mapping(surfaces.get("public"), "surface.public").get("public_projection_only")
        is not True
        or _mapping(surfaces.get("admin"), "surface.admin").get("shared_cache_allowed")
        is not False
        or _mapping(surfaces.get("internal"), "surface.internal").get(
            "shared_cache_allowed"
        )
        is not False
    ):
        _fail("LOGICAL_PLAN_SURFACE_ISOLATION_WEAKENED", "logical_plan")
    _strict_match(
        plan["successor_activation_port"],
        EXPECTED_SUCCESSOR_ACTIVATION_PORT,
        "logical_plan.successor_activation_port",
    )
    _strict_match(
        plan["planned_actions"],
        {action: 0 for action in ACTION_NAMES},
        "logical_plan.planned_actions",
    )
    _strict_match(
        plan["execution_boundary"],
        {
            "activation_enabled": False,
            "network_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "init": "FORBIDDEN",
            "plan": "FORBIDDEN",
            "apply": "FORBIDDEN",
        },
        "logical_plan.execution_boundary",
    )
    expected_contract: dict[str, Any] = {"sources": []}
    expected_contract.update(copy.deepcopy(EXPECTED_SECTIONS))
    expected = logical_plan_document(ComputeEdgeModel(contract=expected_contract))
    if dict(plan) != expected:
        _fail("LOGICAL_PLAN_SEMANTIC_DRIFT", "logical_plan")


def render_logical_plan(model: ComputeEdgeModel) -> bytes:
    document = logical_plan_document(model)
    validate_logical_plan_document(document)
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_toolchain_lock(model: ComputeEdgeModel, root: Path) -> bytes:
    del model
    predecessor_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"),
        "predecessor_toolchain_lock",
    )
    predecessor = _mapping(load_json(predecessor_path), "predecessor_toolchain_lock")
    document = {
        "document": {
            "id": "RAOS-COMPUTE-EDGE-TERRAFORM-VALIDATION-LOCK-001",
            "version": "1.0.0",
            "story_id": "ST-1503",
            "classification": "INHERITED_PINNED_VALIDATION_ONLY_NO_INFRASTRUCTURE_AUTHORITY",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "predecessor": {
            "story_id": "ST-1501",
            "uri": "repo://infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json",
            "sha256": PREDECESSOR_SOURCES[
                "infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"
            ],
        },
        "toolchain": copy.deepcopy(predecessor["toolchain"]),
        "module": {
            "path": EXPECTED_LOGICAL_HCL_MODULE["module_path"],
            "required_version": TERRAFORM_REQUIRED_VERSION,
            "provider_schema": "ABSENT_UNTIL_SUCCESSOR_CONTRACT",
            "provider_lock": "ABSENT_BY_DESIGN_NO_PROVIDER_REQUIRED_OR_SELECTED",
            "provider_requirements": [],
            "backend": "ABSENT",
            "physical_resources": [],
            "logical_component_count": len(logical_compute_edge_components()),
        },
        "authority_boundary": {
            "activation": "DISABLED",
            "provider_selection": "FORBIDDEN",
            "account_or_project_selection": "FORBIDDEN",
            "region_selection": "FORBIDDEN",
            "backend_selection": "FORBIDDEN",
            "domain_and_route_selection": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "network_during_normal_checks": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "infrastructure_actions": "FORBIDDEN",
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_027": "NOT_EXECUTED",
        },
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _hcl_expression(value: object, indent: int = 0) -> str:
    prefix = " " * indent
    if value is None:
        return "null"
    if type(value) is bool:
        return str(value).lower()
    if type(value) is int:
        return str(value)
    if type(value) is str:
        return json.dumps(value, ensure_ascii=False)
    if type(value) is list:
        values = cast(list[object], value)
        if not values:
            return "[]"
        return (
            "[\n"
            + "".join(
                f"{prefix}  {_hcl_expression(item, indent + 2)},\n" for item in values
            )
            + f"{prefix}]"
        )
    if isinstance(value, Mapping):
        mapping = _mapping(_as_object(value), "hcl.expression")
        if not mapping:
            return "{}"
        if any(HCL_IDENTIFIER_PATTERN.fullmatch(key) is None for key in mapping):
            _fail("HCL_OBJECT_KEY_INVALID", "hcl.expression")
        rows = [
            (key, _hcl_expression(item, indent + 2)) for key, item in mapping.items()
        ]
        rendered_rows: list[str] = []
        index = 0
        while index < len(rows):
            key, expression = rows[index]
            if "\n" in expression:
                rendered_rows.append(f"{prefix}  {key} = {expression}")
                index += 1
                continue
            end = index
            while end < len(rows) and "\n" not in rows[end][1]:
                end += 1
            width = max(len(row_key) for row_key, _expression in rows[index:end])
            rendered_rows.extend(
                f"{prefix}  {row_key.ljust(width)} = {row_expression}"
                for row_key, row_expression in rows[index:end]
            )
            index = end
        return "{\n" + "\n".join(rendered_rows) + f"\n{prefix}}}"
    _fail("HCL_EXPRESSION_TYPE_INVALID", "hcl")


def _unvalidated_hcl_bundle() -> dict[Path, bytes]:
    header = (
        "# Generated by repo://scripts/build_st1503_compute_edge.py; do not edit.\n"
    )
    versions = (
        header
        + f'''terraform {{
  required_version = "{TERRAFORM_REQUIRED_VERSION}"
}}
'''
    )
    variable_specs = (
        ("activation_enabled", "bool", "false", "var.activation_enabled == false"),
        (
            "production_apply_authorized",
            "bool",
            "false",
            "var.production_apply_authorized == false",
        ),
        (
            "selected_provider_schema",
            "string",
            "null",
            "var.selected_provider_schema == null",
        ),
        (
            "selected_provider_plugin",
            "string",
            "null",
            "var.selected_provider_plugin == null",
        ),
        (
            "selected_account_or_project",
            "string",
            "null",
            "var.selected_account_or_project == null",
        ),
        ("selected_region", "string", "null", "var.selected_region == null"),
        (
            "selected_state_backend",
            "string",
            "null",
            "var.selected_state_backend == null",
        ),
        (
            "selected_credential_source",
            "string",
            "null",
            "var.selected_credential_source == null",
        ),
        (
            "selected_network_segments",
            "list(string)",
            "[]",
            "length(var.selected_network_segments) == 0",
        ),
        (
            "selected_domain_names",
            "list(string)",
            "[]",
            "length(var.selected_domain_names) == 0",
        ),
        (
            "selected_host_names",
            "list(string)",
            "[]",
            "length(var.selected_host_names) == 0",
        ),
        (
            "selected_dns_certificate_references",
            "list(string)",
            "[]",
            "length(var.selected_dns_certificate_references) == 0",
        ),
        (
            "selected_image_digests",
            "list(string)",
            "[]",
            "length(var.selected_image_digests) == 0",
        ),
        (
            "selected_workload_identity_references",
            "list(string)",
            "[]",
            "length(var.selected_workload_identity_references) == 0",
        ),
        (
            "selected_secret_references",
            "list(string)",
            "[]",
            "length(var.selected_secret_references) == 0",
        ),
        (
            "selected_waf_rule_definitions",
            "list(string)",
            "[]",
            "length(var.selected_waf_rule_definitions) == 0",
        ),
        (
            "selected_rate_limit_thresholds",
            "list(number)",
            "[]",
            "length(var.selected_rate_limit_thresholds) == 0",
        ),
        (
            "selected_health_endpoint_bindings",
            "list(string)",
            "[]",
            "length(var.selected_health_endpoint_bindings) == 0",
        ),
        (
            "supplied_gate_evidence",
            "set(string)",
            "[]",
            "length(var.supplied_gate_evidence) == 0",
        ),
    )
    variable_blocks: list[str] = []
    for name, type_name, default, condition in variable_specs:
        nullable = "\n  nullable    = true" if default == "null" else ""
        variable_blocks.append(
            f'''variable "{name}" {{
  description = "Current ST-1503 revision keeps this successor binding unset."
  type        = {type_name}
  default     = {default}{nullable}

  validation {{
    condition     = {condition}
    error_message = "Physical compute-edge activation requires a successor contract and external evidence."
  }}
}}
'''
        )
    variables = header + "\n".join(variable_blocks)
    locals_document = {
        "reference_architecture": {
            "provider": "AWS_REFERENCE_ONLY",
            "region": "ap-northeast-1_REFERENCE_ONLY",
            "selected": False,
            "services": [
                "ECS",
                "Fargate",
                "ECR",
                "ALB",
                "CloudFront",
                "WAF",
                "Route53",
                "ACM",
            ],
        },
        "logical_components": {
            cast(str, component["component_id"]): component
            for component in logical_compute_edge_components()
        },
        "logical_edges": logical_compute_edge_edges(),
        "identity_permissions": {
            identity: list(permissions)
            for identity, permissions in IDENTITY_PERMISSIONS.items()
        },
        "health_contracts": _health_contracts(),
        "surface_policies": logical_plan_document(
            ComputeEdgeModel(
                contract={
                    "reference_architecture": EXPECTED_SECTIONS[
                        "reference_architecture"
                    ],
                    "logical_hcl_module": EXPECTED_LOGICAL_HCL_MODULE,
                    "successor_activation_port": EXPECTED_SUCCESSOR_ACTIVATION_PORT,
                    "execution_boundary": {
                        "planned_actions": {action: 0 for action in ACTION_NAMES}
                    },
                }
            )
        )["surface_policies"],
        "successor_activation_port": EXPECTED_SUCCESSOR_ACTIVATION_PORT,
        "execution_boundary": {
            "activation_enabled": False,
            "production_apply_authorized": False,
            "planned_actions": {action: 0 for action in ACTION_NAMES},
        },
    }
    locals_content = header + "locals " + _hcl_expression(locals_document, 0) + "\n"
    checks = (
        header
        + f"""check "activation_and_bindings_remain_disabled" {{
  assert {{
    condition     = var.activation_enabled == false && var.production_apply_authorized == false && var.selected_provider_schema == null && var.selected_provider_plugin == null && var.selected_account_or_project == null && var.selected_region == null && var.selected_state_backend == null && var.selected_credential_source == null
    error_message = "Activation and physical provider bindings must remain disabled."
  }}
}}

check "physical_selections_remain_empty" {{
  assert {{
    condition     = length(var.selected_network_segments) == 0 && length(var.selected_domain_names) == 0 && length(var.selected_host_names) == 0 && length(var.selected_dns_certificate_references) == 0 && length(var.selected_image_digests) == 0 && length(var.selected_workload_identity_references) == 0 && length(var.selected_secret_references) == 0 && length(var.selected_waf_rule_definitions) == 0 && length(var.selected_rate_limit_thresholds) == 0 && length(var.selected_health_endpoint_bindings) == 0 && length(var.supplied_gate_evidence) == 0
    error_message = "Physical compute-edge selections require a reviewed successor contract."
  }}
}}

check "logical_component_inventory_is_exact" {{
  assert {{
    condition     = length(local.logical_components) == {len(logical_compute_edge_components())} && length(local.logical_edges) == {len(logical_compute_edge_edges())}
    error_message = "The closed logical compute-edge graph inventory cannot drift."
  }}
}}

check "public_entry_is_edge_only" {{
  assert {{
    condition     = alltrue([for component in values(local.logical_components) : !component.publicly_addressable || contains(["edge_public", "edge_admin", "dns_tls_public", "dns_tls_admin"], component.component_id)]) && alltrue([for id in ["edge_public", "edge_admin"] : local.logical_components[id].edge_mediated && local.logical_components[id].waf_required && local.logical_components[id].rate_limit_required])
    error_message = "Only DNS/TLS and managed WAF edge declarations may be publicly addressable."
  }}
}}

check "origins_and_data_plane_remain_private" {{
  assert {{
    condition     = alltrue([for component in values(local.logical_components) : component.direct_data_plane_access == false]) && alltrue([for id in {json.dumps(list(WORKLOAD_COMPONENT_IDS))} : local.logical_components[id].publicly_addressable == false && local.logical_components[id].private_origin == true])
    error_message = "Workloads, origins, and the data plane must remain private."
  }}
}}

check "surface_boundaries_are_distinct" {{
  assert {{
    condition     = local.surface_policies.public.public_projection_only == true && local.surface_policies.admin.shared_cache_allowed == false && local.surface_policies.internal.shared_cache_allowed == false && local.surface_policies.public.cookie_boundary == "DISTINCT" && local.surface_policies.admin.cookie_boundary == "DISTINCT" && local.surface_policies.public.csp_boundary == "DISTINCT" && local.surface_policies.admin.csp_boundary == "DISTINCT"
    error_message = "Public, Admin, and Internal cache, cookie, CSP, identity, and data boundaries must remain distinct."
  }}
}}

check "images_are_immutable_and_provenanced" {{
  assert {{
    condition     = alltrue([for id in {json.dumps(list(WORKLOAD_COMPONENT_IDS))} : local.logical_components[id].immutable_image_required && local.logical_components[id].digest_selection_required && local.logical_components[id].signed_provenance_required && local.logical_components[id].sbom_required && local.logical_components[id].image_scan_required])
    error_message = "Every workload requires digest-selected images, provenance, SBOM, and scanning."
  }}
}}

check "identity_secrets_and_egress_are_closed" {{
  assert {{
    condition     = alltrue([for component in values(local.logical_components) : component.secret_material_present == false && component.transport_encryption_required == true]) && alltrue([for id in {json.dumps(list(WORKLOAD_COMPONENT_IDS))} : local.logical_components[id].controlled_egress_required == true])
    error_message = "Secret material is forbidden and every workload requires controlled encrypted egress."
  }}
}}

check "health_semantics_are_distinct" {{
  assert {{
    condition     = alltrue([for health in values(local.health_contracts) : health.liveness.purpose == "PROCESS_ONLY" && health.liveness.external_provider_dependency == "FORBIDDEN" && health.liveness.database_dependency == "FORBIDDEN" && health.readiness.purpose == "DEPENDENCY_AND_MIGRATION_READINESS" && health.readiness.generic_http_200_inference == "FORBIDDEN" && health.liveness.endpoint_path == null && health.readiness.endpoint_path == null])
    error_message = "Liveness is process-only; readiness must cover dependencies and migration compatibility without invented endpoints."
  }}
}}

check "waf_and_rate_limits_are_distinct" {{
  assert {{
    condition     = alltrue([for id in {json.dumps(list(WAF_COMPONENT_IDS))} : local.logical_components[id].waf_required && local.logical_components[id].rate_limit_required]) && alltrue([for id in {json.dumps(list(RATE_LIMIT_COMPONENT_IDS))} : local.logical_components[id].rate_limit_required])
    error_message = "Public and Admin require distinct WAF and rate-limit declarations."
  }}
}}

check "observability_canary_and_rollback_are_required" {{
  assert {{
    condition     = alltrue([for component in values(local.logical_components) : component.observability_required]) && local.logical_components.canary_release_boundary.canary_required && local.logical_components.canary_release_boundary.rollback_required && local.logical_components.rollback_boundary.rollback_required && local.successor_activation_port.complete_gate_evidence == false
    error_message = "Observability and human-gated canary/rollback requirements cannot be weakened."
  }}
}}

check "permissions_are_wildcard_free_and_actions_zero" {{
  assert {{
    condition     = alltrue(flatten([for permissions in values(local.identity_permissions) : [for permission in permissions : permission != "*" && !endswith(permission, ":*") && !endswith(permission, ".*")]])) && alltrue([for count in values(local.execution_boundary.planned_actions) : count == 0])
    error_message = "Logical identities must be wildcard-free and infrastructure actions must remain zero."
  }}
}}
"""
    )
    outputs = (
        header
        + """output "reference_architecture" {
  description = "Canonical AWS reference metadata; never a selected provider binding."
  value       = local.reference_architecture
}

output "logical_components" {
  description = "Provider-schema-free logical compute and edge declarations."
  value       = local.logical_components
}

output "logical_edges" {
  description = "Deterministic isolation, routing, identity, health, and release edges."
  value       = local.logical_edges
}

output "identity_permissions" {
  description = "Wildcard-free logical workload permission sets."
  value       = local.identity_permissions
}

output "health_contracts" {
  description = "Distinct logical liveness and readiness semantics with no physical endpoint."
  value       = local.health_contracts
}

output "surface_policies" {
  description = "Distinct Public, Admin, and Internal trust and cache policies."
  value       = local.surface_policies
}

output "activation_boundary" {
  description = "Closed successor activation port and zero-action execution boundary."
  value = {
    successor = local.successor_activation_port
    execution = local.execution_boundary
  }
}
"""
    )
    return {
        HCL_PATHS[0]: versions.encode("utf-8"),
        HCL_PATHS[1]: variables.encode("utf-8"),
        HCL_PATHS[2]: locals_content.encode("utf-8"),
        HCL_PATHS[3]: checks.encode("utf-8"),
        HCL_PATHS[4]: outputs.encode("utf-8"),
    }


def render_hcl_bundle(model: ComputeEdgeModel) -> dict[Path, bytes]:
    del model
    bundle = _unvalidated_hcl_bundle()
    validate_hcl_bundle(bundle)
    return bundle


def validate_hcl_file_policy(relative: Path, content: bytes) -> None:
    if relative not in HCL_PATHS:
        _fail("HCL_FILE_INVENTORY_DRIFT", "hcl")
    if not content or len(content) > MAX_HCL_BYTES or not content.endswith(b"\n"):
        _fail("HCL_FILE_SHAPE_INVALID", "hcl")
    try:
        text = content.decode("utf-8")
    except UnicodeError:
        _fail("HCL_FILE_ENCODING_INVALID", "hcl")
    if "\x00" in text or "\r" in text:
        _fail("HCL_FILE_ENCODING_INVALID", "hcl")
    blocks = tuple(HCL_TOP_LEVEL_BLOCK_PATTERN.findall(text))
    if any(block in HCL_FORBIDDEN_TOP_LEVEL_BLOCKS for block in blocks):
        _fail("HCL_FORBIDDEN_BLOCK", "hcl")
    if blocks != HCL_ALLOWED_BLOCKS_BY_FILE[relative.name]:
        _fail("HCL_BLOCK_INVENTORY_DRIFT", "hcl")
    forbidden_fragments = (
        'provider "',
        "backend {",
        'module "',
        'data "',
        'resource "',
        'provisioner "',
        "terraform_remote_state",
        "local-exec",
        "remote-exec",
        "registry.terraform.io/",
        "hashicorp/aws",
        "http://",
        "https://",
        "file(",
        "templatefile(",
        "external(",
    )
    if any(fragment in text for fragment in forbidden_fragments):
        _fail("HCL_FORBIDDEN_OPERATION", "hcl")
    if (
        relative.name == "versions.tf"
        and text.count(f'required_version = "{TERRAFORM_REQUIRED_VERSION}"') != 1
    ):
        _fail("HCL_TOOL_VERSION_DRIFT", "hcl")
    if relative.name == "locals.tf":
        safety_declarations = (
            r"(?m)^\s+secret_material_present\s+= false$",
            r"(?m)^\s+direct_data_plane_access\s+= false$",
            r"(?m)^\s+complete_gate_evidence\s+= false$",
            r"(?m)^\s+selected_provider_schema\s+= null$",
        )
        if any(re.search(pattern, text) is None for pattern in safety_declarations):
            _fail("HCL_SAFETY_DECLARATION_DRIFT", "hcl")
    if relative.name == "locals.tf" and (
        '"*"' in text or '":*"' in text or '".*"' in text
    ):
        _fail("HCL_WILDCARD_IAM", "hcl")


def validate_hcl_bundle(bundle: Mapping[Path, bytes]) -> None:
    if set(bundle) != set(HCL_PATHS):
        _fail("HCL_FILE_INVENTORY_DRIFT", "hcl")
    expected = _unvalidated_hcl_bundle()
    for relative in HCL_PATHS:
        validate_hcl_file_policy(relative, bundle[relative])
        if bundle[relative] != expected[relative]:
            _fail("HCL_SEMANTIC_DRIFT", "hcl")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _repository_regular_file(root, relative, "source_artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: ComputeEdgeModel,
    generated_artifacts: Mapping[Path, bytes],
    root: Path = REPO_ROOT,
) -> bytes:
    if set(generated_artifacts) != set(GENERATED_ARTIFACT_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "manifest")
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    selection = _mapping(model.contract["selected_configuration"], "selection")
    admission = _mapping(
        model.contract["provider_neutral_compute_edge_admission"], "admission"
    )
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-COMPUTE-EDGE-MANIFEST-001",
            "version": "1.2.0",
            "story_id": "ST-1503",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "contract_sha256": sha256_file(
                _repository_regular_file(root, CONTRACT_PATH, "contract")
            ),
            "authority_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in AUTHORITY_SOURCES.items()
            ],
            "predecessor_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in PREDECESSOR_SOURCES.items()
            ],
        },
        "source_artifact_count": len(source_artifacts),
        "source_artifacts": source_artifacts,
        "generated_artifact_count": len(generated_artifacts),
        "generated_artifacts": [
            {
                "uri": f"repo://{relative.as_posix()}",
                "bytes": len(generated_artifacts[relative]),
                "sha256": sha256_bytes(generated_artifacts[relative]),
            }
            for relative in GENERATED_ARTIFACT_PATHS
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": evidence["deliverable_classification"],
            "logical_hcl_module": copy.deepcopy(model.contract["logical_hcl_module"]),
            "successor_activation_port": copy.deepcopy(
                model.contract["successor_activation_port"]
            ),
            "activation": execution["activation_status"],
            "planned_actions": copy.deepcopy(execution["planned_actions"]),
            "admission_status": admission["admission_status"],
            "eligible": admission["eligible"],
            "selected_profile_id": admission["selected_profile_id"],
            "selected_profile_kind": admission["selected_profile_kind"],
            "selected_provider_name": admission["selected_provider_name"],
            "default_profile_id": admission["default_profile_id"],
            "fallback_profile_id": admission["fallback_profile_id"],
            "configured_mapping_count": admission["mapping_policy"][
                "configured_mapping_count"
            ],
            "required_capability_count": len(COMPUTE_EDGE_CAPABILITY_OUTCOMES),
            "aws_reference_only": True,
            "aws_reference_role": admission["aws_reference_boundary"]["role"],
            "canonical_story_deliverables": admission["aws_reference_boundary"][
                "canonical_story_deliverables"
            ],
            "portable_implementation_paths": admission["aws_reference_boundary"][
                "non_aws_owner_managed_profiles"
            ],
            "aws_reference_default": admission["aws_reference_boundary"]["default"],
            "aws_reference_implicit_fallback": admission["aws_reference_boundary"][
                "implicit_fallback"
            ],
            "aws_reference_selected_binding": admission["aws_reference_boundary"][
                "selected_binding"
            ],
            "aws_reference_eligibility_shortcut": admission["aws_reference_boundary"][
                "eligibility_shortcut"
            ],
            "aws_reference_admission_requirement": admission["aws_reference_boundary"][
                "admission_requirement"
            ],
            "aws_reference_evidence_substitute": admission["aws_reference_boundary"][
                "evidence_substitute"
            ],
            "selected_provider_account_or_project": selection[
                "provider_account_or_project"
            ],
            "selected_production_region": selection["production_region"],
            "selected_workload_runtime": selection["workload_runtime_binding"],
            "selected_ingress_edge": selection["ingress_edge_binding"],
            "selected_dns": selection["dns_binding"],
            "selected_tls_certificate": selection["tls_certificate_binding"],
            "selected_waf_abuse_control": selection["waf_abuse_control_binding"],
            "credentials": evidence["credentials"],
            "physical_resource_definitions": copy.deepcopy(
                selection["physical_resource_definitions"]
            ),
            "native_iac_validation": evidence["native_iac_validation"],
            "formal_tst_026": evidence["formal_tst_026"],
            "formal_tst_027": evidence["formal_tst_027"],
            "performance_load_validation": evidence["performance_load_validation"],
            "health_slo_alert_validation": evidence["health_slo_alert_validation"],
            "canary_rollback_validation": evidence["canary_rollback_validation"],
            "identity_secret_egress_validation": evidence[
                "identity_secret_egress_validation"
            ],
            "region_residency_validation": evidence["region_residency_validation"],
            "transport_security_validation": evidence["transport_security_validation"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "effective_canonical_status": evidence["effective_canonical_status"],
        },
    }
    return yaml.dump(
        document,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    model = load_and_validate_contract(root)
    generated_artifacts: dict[Path, bytes] = {
        REFERENCE_PLAN_PATH: render_reference_plan(model),
        LOGICAL_PLAN_PATH: render_logical_plan(model),
        TOOLCHAIN_LOCK_PATH: render_toolchain_lock(model, root),
        **render_hcl_bundle(model),
    }
    return {
        **generated_artifacts,
        MANIFEST_PATH: render_manifest(model, generated_artifacts, root),
    }


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_OUTPUT_PATH", "output")
    current = _real_repository_root(root)
    for part in relative.parts[:-1]:
        current /= part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            if not create:
                _fail("GENERATED_OUTPUT_MISSING", "output")
            try:
                current.mkdir(mode=0o755)
                metadata = current.lstat()
            except OSError:
                _fail("OUTPUT_DIRECTORY_FAILED", "output")
        except OSError:
            _fail("OUTPUT_DIRECTORY_FAILED", "output")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
    return current


def _output_file(root: Path, relative: Path) -> Path:
    parent = _safe_output_parent(root, relative, create=False)
    target = parent / relative.name
    _regular_file(target, "generated_output")
    return target


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    parent = _safe_output_parent(root, relative, create=True)
    target = parent / relative.name
    if target.exists() or target.is_symlink():
        _regular_file(target, "generated_output")
    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{relative.name}.", suffix=".tmp", dir=parent
        )
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
        directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except OSError:
        _fail("OUTPUT_WRITE_FAILED", "output")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = _output_file(root, relative)
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative in GENERATED_PATHS:
        _atomic_write(root, relative, outputs[relative])


def _native_command(
    unshare_path: Path,
    terraform_path: Path,
    arguments: tuple[str, ...],
    *,
    working_directory: Path,
    data_directory: Path,
) -> bytes:
    if arguments not in ALLOWED_NATIVE_ARGUMENTS:
        _fail("NATIVE_VALIDATOR_COMMAND_FORBIDDEN", "native_validator")
    if unshare_path != Path("/usr/bin/unshare"):
        _fail("NETWORK_NAMESPACE_RUNNER_FORBIDDEN", "native_validator")
    command = (
        str(unshare_path),
        "--user",
        "--map-root-user",
        "--net",
        "--",
        str(terraform_path),
        *arguments,
    )
    environment = {
        "CHECKPOINT_DISABLE": "1",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TF_DATA_DIR": str(data_directory),
        "TF_IN_AUTOMATION": "1",
        "TF_INPUT": "0",
        "TF_REGISTRY_CLIENT_TIMEOUT": "1",
        "TF_REGISTRY_DISCOVERY_RETRY": "0",
    }
    try:
        result = subprocess.run(
            command,
            cwd=working_directory,
            env=environment,
            check=False,
            capture_output=True,
            timeout=30,
        )
    except OSError, subprocess.SubprocessError:
        _fail("NATIVE_VALIDATOR_EXECUTION_FAILED", "native_validator")
    if result.returncode != 0:
        _fail("NATIVE_VALIDATOR_REJECTED", "native_validator")
    if len(result.stdout) > MAX_HCL_BYTES or len(result.stderr) > MAX_HCL_BYTES:
        _fail("NATIVE_VALIDATOR_OUTPUT_LIMIT", "native_validator")
    return result.stdout


def _json_object(content: bytes, field: str) -> Mapping[str, Any]:
    try:
        decoded = json.loads(content)
    except UnicodeError, json.JSONDecodeError:
        _fail("NATIVE_VALIDATOR_OUTPUT_INVALID", field)
    return _mapping(decoded, field)


def verify_native_hcl(
    root: Path,
    terraform_path: Path,
    *,
    unshare_path: Path = Path("/usr/bin/unshare"),
) -> NativeValidationResult:
    if not terraform_path.is_absolute() or not unshare_path.is_absolute():
        _fail("NATIVE_VALIDATOR_PATH_INVALID", "native_validator")
    _regular_file(terraform_path, "terraform_binary")
    _regular_file(unshare_path, "network_namespace_runner")
    if sha256_file(terraform_path) != TERRAFORM_BINARY_SHA256:
        _fail("NATIVE_VALIDATOR_DIGEST_MISMATCH", "terraform_binary")
    expected = render_outputs(root)
    check_outputs(root, expected)
    repository_snapshot = {
        relative: (
            _output_file(root, relative).read_bytes(),
            _output_file(root, relative).stat().st_mtime_ns,
            _output_file(root, relative).stat().st_mode,
        )
        for relative in GENERATED_PATHS
    }
    hcl_bundle = {relative: expected[relative] for relative in HCL_PATHS}
    validate_hcl_bundle(hcl_bundle)
    with tempfile.TemporaryDirectory(prefix="raos-st1503-native-") as directory:
        validation_root = Path(directory)
        module_directory = validation_root / "module"
        data_directory = validation_root / "terraform-data"
        module_directory.mkdir(mode=0o700)
        data_directory.mkdir(mode=0o700)
        for relative in HCL_PATHS:
            target = module_directory / relative.name
            target.write_bytes(hcl_bundle[relative])
            target.chmod(0o400)
        module_before = {
            path.name: (path.read_bytes(), path.stat().st_mode)
            for path in sorted(module_directory.iterdir())
        }
        version_document = _json_object(
            _native_command(
                unshare_path,
                terraform_path,
                ("version", "-json"),
                working_directory=module_directory,
                data_directory=data_directory,
            ),
            "native_validator.version",
        )
        _strict_match(
            version_document,
            {
                "terraform_version": TERRAFORM_VERSION,
                "platform": TERRAFORM_PLATFORM,
                "provider_selections": {},
                "terraform_outdated": False,
            },
            "native_validator.version",
        )
        _native_command(
            unshare_path,
            terraform_path,
            ("fmt", "-check", "-recursive"),
            working_directory=module_directory,
            data_directory=data_directory,
        )
        validation_document = _json_object(
            _native_command(
                unshare_path,
                terraform_path,
                ("validate", "-json"),
                working_directory=module_directory,
                data_directory=data_directory,
            ),
            "native_validator.validate",
        )
        if (
            validation_document.get("valid") is not True
            or validation_document.get("error_count") != 0
            or validation_document.get("warning_count") != 0
        ):
            _fail("NATIVE_HCL_SEMANTIC_VALIDATION_FAILED", "native_validator")
        module_after = {
            path.name: (path.read_bytes(), path.stat().st_mode)
            for path in sorted(module_directory.iterdir())
        }
        if module_after != module_before:
            _fail("NATIVE_VALIDATOR_MODULE_WRITE", "native_validator")
    repository_after = {
        relative: (
            _output_file(root, relative).read_bytes(),
            _output_file(root, relative).stat().st_mtime_ns,
            _output_file(root, relative).stat().st_mode,
        )
        for relative in GENERATED_PATHS
    }
    if repository_after != repository_snapshot:
        _fail("NATIVE_VALIDATOR_REPOSITORY_WRITE", "native_validator")
    return NativeValidationResult(
        terraform_version=TERRAFORM_VERSION,
        platform=TERRAFORM_PLATFORM,
        provider_selections=(),
        format_valid=True,
        semantic_valid=True,
        network_namespace=True,
        repository_unchanged=True,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build and validate the disabled ST-1503 logical HCL module."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed generated bytes without writing",
    )
    parser.add_argument(
        "--native-check",
        action="store_true",
        help="run pinned offline fmt and semantic validation in a network namespace",
    )
    parser.add_argument(
        "--terraform",
        type=Path,
        help="absolute path to the checksum-verified Terraform 1.15.9 binary",
    )
    parser.add_argument(
        "--unshare",
        type=Path,
        default=Path("/usr/bin/unshare"),
        help="absolute path to the Linux network namespace runner",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        native_check = bool(args.native_check)
        terraform_path = cast(Path | None, args.terraform)
        unshare_path = cast(Path, args.unshare)
        if native_check and terraform_path is None:
            _fail("NATIVE_VALIDATOR_PATH_REQUIRED", "terraform_binary")
        if not native_check and terraform_path is not None:
            _fail("NATIVE_VALIDATOR_MODE_REQUIRED", "terraform_binary")
        build(REPO_ROOT, check=bool(args.check) or native_check)
        if native_check and terraform_path is not None:
            verify_native_hcl(REPO_ROOT, terraform_path, unshare_path=unshare_path)
    except ComputeEdgeContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.native_check:
        print("ST-1503 native HCL validation passed")
    elif args.check:
        print("ST-1503 compute/edge check passed")
    else:
        print("ST-1503 compute/edge artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
