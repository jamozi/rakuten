#!/usr/bin/env python3
"""Build the disabled, non-executable ST-1506 Production reference artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTRACT_PATH: Final = Path(
    "changes/st-1506/contracts/production-deployment-definition.v1.yaml"
)
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1506/DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/deployment-production/production-deployment.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1506/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1506_production_deployment.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1506_production_deployment.py"
)

AUTHORITY_SOURCES: Final = {
    "docs/canonical/00_master/RAOS_MASTER_README_v1.0.md": (
        "a0b27b491ee120767a59dd0c7822ab10e30cf17738960a919116623415ff8e40"
    ),
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
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml": (
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984"
    ),
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
    ),
    "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md": (
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8"
    ),
    "docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml": (
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0"
    ),
    "docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml": (
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_release_evidence_template_v1.0.yaml": (
        "3354001be5fc0f7f7ef6a265fdd3112618ee943092755745d8cd62986487e95a"
    ),
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234"
    ),
    "changes/st-1506/DESIGN_HANDOFF_V1_ST1506_PROVIDER_NEUTRAL_PRODUCTION.yaml": (
        "91fabd10025a866796de62ad65072cb6a7d2c39c26c9f43ad802bffe45e8065f"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "ec01dcb05f6176c21ba8b9947bed60b88ce9a2622e1c358478f4f79a633bda61"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "c16287606c4d73982ead82c9f8e111b327b0447ed8c06a6630c6ce5ac22f07c6"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "c486637559457aedd24fbdd752d624a754dc69ed399bbed83ecaebd037c4f559"
    ),
    "scripts/build_st1501_terraform_foundation.py": (
        "558e1f8dc20331730582e62018cd88579f4b82e295bffad617049a925ab466a7"
    ),
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml": (
        "40d866ae30199748c9d91b8152aaa4fb4ca2721e5e722bcff05cf97760f1c228"
    ),
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "4d0ca4188c4a4ee7c8f6c8417afc6880b9ac0f89b6e4bd63703eb98d8368dddb"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "28f4ae25fd66f0bb999a1918e72a5d108f38991bb5104e2726b01a0997a6087c"
    ),
    "scripts/build_st1502_data_services.py": (
        "fcb488254a09bf5ac686a66d75865ccef8ee0e027360e3131c8aacea8de01484"
    ),
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml": (
        "de21922772e9e88ba830fc33c82848a9423d492fc9696027b91febf9aebb0646"
    ),
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml": (
        "7d742065c5ffda0dbecf04c144af7daf0de2fdc0d2598e85bc9af656c4ac242d"
    ),
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json": (
        "a894504b51f2cc5f77d05a00c12fdcbd854a49d74d80822c9564f08957bd3888"
    ),
    "scripts/build_st1503_compute_edge.py": (
        "554d00a82f1a48d1e154e5aaff63fad7330e46a81e862e6bc0a2b30385029a7b"
    ),
    "changes/st-0107/contracts/pr-governance.v1.yaml": (
        "b387255fa65577051203b0fb1f935d5340c0d00f1285fd25557a38776fb07d92"
    ),
    "changes/st-0107/ruleset-policy.v1.json": (
        "e999838c2f592e3795aa79222bcfbc8cedf4b59bad06024f0328ebd65b3e11f5"
    ),
    "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml": (
        "f6a89722b86a8a47288da86c09214a3a926061d16489737170edc07398b2be61"
    ),
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml": (
        "d7e6922ff953434435509a4bd3aca0251b57dc699e990fae3ae06c75af229b4c"
    ),
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json": (
        "7566adbe5a9eff81144ceffb9ec233ba98322c2d01f399e5a103a033d0b35974"
    ),
    "scripts/build_st1504_github_oidc.py": (
        "3972533552bf2e1d3265ae4a41571872a5c0aa6fd537fa69c7afd3736eb53a28"
    ),
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml": (
        "146351e1ba13970b33bccc0df3683c8b650769b1357f829424f1d53bce8a3937"
    ),
    "changes/st-1505/contracts/staging-deployment.v1.yaml": (
        "c70deefd72bd84f4196bea7f078a70f511397f1d759846c200cfb9224468cc69"
    ),
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json": (
        "ba65ac0776c4dd811a2918843e8984945ab92e370892b164bb8099df67950cac"
    ),
    "scripts/build_st1505_staging_deployment.py": (
        "77212cd87cb2f88363552c6d29b4d900137afd35f591d524b7e1528a1073e522"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}
PREDECESSOR_SEMANTIC_SHA256: Final = {
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "0915d6ec4949babebf43f307b2ac1569fa76213c96a3be9009dfaec660e34030"
    ),
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "715fbdd46467ac282333c486850a5571d27836d5d028f971e5840f755e338a6e"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "6521f7396e8b076177cd00d297342a482ac664809c432dde48c8c7d55d01d32f"
    ),
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml": (
        "53a640dd58c222296da2c079a374daf55e6a55e40fb1944bae6070b7ef559450"
    ),
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "3b696b86edd9b0a04e85c99f3306deb4879a935c381351276136a49e7423f440"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "777368a0ee051d9f74f1bb4b25216ddf4ea4b1000f16a283e387df197b1095d7"
    ),
    "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml": (
        "0e3d26dc01e244034567bbd6fe13ace689447cc5f835e6b3581b64120cfbc7fe"
    ),
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml": (
        "4ee5dfb892be42119d4f2c77c07e850a93785458e47c496e0e953fd83fc276ac"
    ),
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json": (
        "50d334f3d28a0c0b56623b3960a6b1d3398d861aeda72d6abee1339f84b4e6a8"
    ),
    "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml": (
        "8afd193ddc98a0193e21032a3058c157fe75f12151cb06d80a9ea198efbc5f8c"
    ),
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml": (
        "795f7ec4218e029feef40aee6d6616ff62e3f9cc847a8383f4f847514c8c3d22"
    ),
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json": (
        "256550caaf1c7fba5aca5b4c74015590d052941e87e9fcaf4c2eb3db7af25697"
    ),
    "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml": (
        "30eaec3fbeceec8b3b4043777d7c3fe8b97082e36f585e70899ba6104fa3bc32"
    ),
    "changes/st-1505/contracts/staging-deployment.v1.yaml": (
        "a7d9a9cb6f791116b30d086f824101bf547782f2b785a538a331f83b16b8eeff"
    ),
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json": (
        "72337829f619da5a266b09bbe14017ade796e38b2394fb2e7fe5dc15c2d6ec96"
    ),
}
DEPENDENCY_POLICIES: Final = {
    "ST-1501": "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
    "ST-1502": "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION",
    "ST-1503": "STRICT_PROVIDER_NEUTRAL_COMPUTE_EDGE_CAPABILITY_ADMISSION",
    "ST-1504": "STRICT_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY_CAPABILITY_ADMISSION",
    "ST-1505": "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION",
}
DEPENDENCY_STORIES: Final = tuple(DEPENDENCY_POLICIES)
PREDECESSOR_SPECIFICATIONS: Final = (
    (
        "foundation",
        "ST-1501",
        "scripts/build_st1501_terraform_foundation.py",
        "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json",
        "provider_neutral_foundation_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
    (
        "data_services",
        "ST-1502",
        "scripts/build_st1502_data_services.py",
        "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml",
        "changes/st-1502/contracts/data-services-foundation.v1.yaml",
        "infra/terraform/data-services/data-services.reference-plan.v1.json",
        "provider_neutral_data_services_admission",
        {
            "create": 0,
            "update": 0,
            "delete": 0,
            "migrate": 0,
            "backup": 0,
            "restore": 0,
            "redrive": 0,
            "rotate": 0,
        },
    ),
    (
        "compute_edge",
        "ST-1503",
        "scripts/build_st1503_compute_edge.py",
        "changes/st-1503/DESIGN_HANDOFF_V1_ST1503_PROVIDER_NEUTRAL_COMPUTE_EDGE.yaml",
        "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
        "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        "provider_neutral_compute_edge_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
    (
        "deployment_identity",
        "ST-1504",
        "scripts/build_st1504_github_oidc.py",
        "changes/st-1504/DESIGN_HANDOFF_V1_ST1504_PROVIDER_NEUTRAL_DEPLOYMENT_IDENTITY.yaml",
        "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
        "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
        "provider_neutral_deployment_identity_admission",
        {"create": 0, "update": 0, "delete": 0},
    ),
    (
        "staging",
        "ST-1505",
        "scripts/build_st1505_staging_deployment.py",
        "changes/st-1505/DESIGN_HANDOFF_V1_ST1505_PROVIDER_NEUTRAL_STAGING.yaml",
        "changes/st-1505/contracts/staging-deployment.v1.yaml",
        "infra/terraform/staging/staging-deployment.reference-plan.v1.json",
        "provider_neutral_staging_admission",
        {
            "create": 0,
            "update": 0,
            "delete": 0,
            "build": 0,
            "promote": 0,
            "approve": 0,
            "deploy": 0,
            "migrate": 0,
            "migration_review": 0,
            "smoke": 0,
            "security": 0,
            "runtime": 0,
            "browser": 0,
            "transport_security": 0,
            "telemetry": 0,
            "alert": 0,
            "rollback": 0,
            "restore": 0,
            "release": 0,
            "production": 0,
        },
    ),
)

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    Path("changes/st-1506/README.md"),
    Path("scripts/build_st1506_production_deployment.py"),
    Path("tests/st1506/conftest.py"),
    Path("tests/st1506/test_contract.py"),
    Path("tests/st1506/test_generation.py"),
    Path("tests/st1506/test_negative_cases.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1506",
    "epic_id": "EPIC-15",
    "title": "Production deployment definition",
    "objective": "Production env保護とcanary",
    "depends_on": ["ST-1505"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["production pipeline disabled by default"],
    "acceptance_criteria": ["GATE/security/ops approvals required"],
    "test_suites": ["TST-032"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": ["OD-009", "OD-011", "OD-013", "OD-015"],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_OPEN_DECISIONS: Final = {
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
EXPECTED_TST_032: Final = {
    "id": "TST-032",
    "name": "GATE acceptance pack",
    "layer": "acceptance",
    "purpose": "GATE-0..4のEvidenceをSnapshot化",
    "candidate_tools": ["custom report generator"],
    "release_blocking": True,
    "environments": ["staging"],
    "owner": "Product Owner",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_bindings",
    "provider_neutral_admission",
    "open_decision_defaults",
    "environment_boundary",
    "selected_bindings",
    "human_approval_gates",
    "artifact_admission_intent",
    "protected_environment_intent",
    "migration_intent",
    "transport_security_intent",
    "canary_intent",
    "observability_intent",
    "health_and_smoke_intent",
    "rollback_intent",
    "logical_phases",
    "execution_boundary",
    "evidence_boundary",
)
PROVIDER_NEUTRAL_ADMISSION_KEYS: Final = (
    "classification",
    "admission_status",
    "eligible",
    "selected_profile_id",
    "selected_profile_kind",
    "selected_provider_name",
    "default_profile_id",
    "fallback_profile_id",
    "concrete_alternate_provider_selected",
    "eligible_profile_kinds",
    "dependency_admission_policy",
    "dependency_admission_requirements",
    "mapping_policy",
    "aws_reference_boundary",
    "predecessor_reference_boundary",
    "evidence_equivalence_policy",
    "capability_mapping_requirements",
)
REQUIRED_CAPABILITY_OUTCOMES: Final = {
    "workload_runtime": "PORTABLE_WEB_API_WORKER_SCHEDULER_WORKLOAD_RUNTIME",
    "relational_persistence": (
        "POSTGRESQL_COMPATIBLE_TRANSACTIONAL_PERSISTENCE_AND_MIGRATION_CONTROLS"
    ),
    "immutable_object_storage": (
        "S3_COMPATIBLE_VERSIONED_AND_IMMUTABLE_WHERE_DATA_CONTRACT_REQUIRES"
    ),
    "asynchronous_queue": "AT_LEAST_ONCE_WITH_DLQ_AND_IDEMPOTENT_CONSUMERS",
    "public_edge": "DNS_TLS_WAF_AND_PUBLIC_ADMIN_INTERNAL_ISOLATION",
    "workload_identity_and_secrets": (
        "LEAST_PRIVILEGE_WORKLOAD_IDENTITY_AND_AUDITED_SECRET_DELIVERY"
    ),
    "telemetry_and_alerting": (
        "TRACES_METRICS_LOGS_RELEASE_MARKERS_ALERTS_AND_NOTIFICATION_ROUTING"
    ),
    "backup_and_restore": (
        "PITR_SNAPSHOTS_OBJECT_VERSION_RESTORE_DRILL_AND_INTEGRITY_VERIFICATION"
    ),
    "deployment_and_release": (
        "IMMUTABLE_PROMOTION_MIGRATION_CANARY_OBSERVE_ROLLBACK_AND_HUMAN_RELEASE"
    ),
    "region_and_data_residency": (
        "EXPLICIT_PRIMARY_BACKUP_LOCATION_AND_DATA_RESIDENCY_EVIDENCE"
    ),
}
REQUIRED_CAPABILITY_IDS: Final = tuple(REQUIRED_CAPABILITY_OUTCOMES)
PHASE_NAMES: Final = (
    "PREDECESSOR_DEPENDENCY_ADMISSION_GATE",
    "INDEPENDENT_MIGRATION_REVIEW_GATE",
    "TRANSPORT_SECURITY_GATE",
    "CANARY",
    "OBSERVE",
    "ROLLBACK",
)
ACTION_COUNT_NAMES: Final = (
    "create",
    "update",
    "delete",
    "dependency_admission",
    "promote",
    "deploy",
    "migrate",
    "migration_review",
    "traffic",
    "canary",
    "transport_security",
    "rollback",
    "release",
    "status",
)
OPERATION_NAMES: Final = ACTION_COUNT_NAMES
APPROVAL_ARTIFACT_NAMES: Final = (
    "release_decision",
    "gate_report",
    "security_approval",
    "operations_approval",
)
EXPECTED_CONTRACT_FINGERPRINT: Final = (
    "585ecdc4ea352fa78d83ddcb1491c483ada74289b2a72eb1915be7c92dcb369e"
)
EXPECTED_HANDOFF_SEMANTIC_SHA256: Final = (
    "19235956b20edbc0ad3363ae5b65752f7715f3af021c24a449ac5d2bdc19506b"
)
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class ProductionDeploymentContractError(RuntimeError):
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
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
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
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


@dataclass(frozen=True, slots=True)
class ProductionDeploymentModel:
    """A fully validated, closed ST-1506 contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def semantic_sha256(document: object) -> str:
    try:
        canonical = json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail("TYPE_MISMATCH", "semantic_document")
    return sha256_bytes(canonical)


def _fail(code: str, field: str) -> NoReturn:
    raise ProductionDeploymentContractError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        type(key) is str for key in value.keys()
    ):
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _strict_match(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        value = _mapping(actual, field)
        expected_mapping = _mapping(expected, field)
        if set(value) != set(expected_mapping):
            _fail("CLOSED_SCHEMA_VIOLATION", field)
        for key, expected_value in expected_mapping.items():
            _strict_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(expected, field)
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


def _assert_unset_tree(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, nested in _mapping(value, field).items():
            _assert_unset_tree(nested, f"{field}.{key}")
        return
    if type(value) is list:
        if value:
            _fail("SELECTION_MUST_REMAIN_UNSET", field)
        return
    _fail("SELECTION_MUST_REMAIN_UNSET", field)


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
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", "yaml")
        return yaml.load(text, Loader=UniqueKeyLoader)
    except ProductionDeploymentContractError:
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
    except ProductionDeploymentContractError:
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
    rows = _list(contract.get("sources"), "sources")
    observed: dict[str, str] = {}
    observed_order: list[str] = []
    for raw_row in rows:
        row = _mapping(raw_row, "sources.item")
        if tuple(row) != ("uri", "sha256"):
            _fail("CLOSED_SCHEMA_VIOLATION", "sources.item")
        relative = _repo_relative_uri(row["uri"])
        digest = row["sha256"]
        if type(digest) is not str or SHA256_PATTERN.fullmatch(digest) is None:
            _fail("SOURCE_DIGEST_INVALID", "sources.item.sha256")
        key = relative.as_posix()
        if key in observed:
            _fail("SOURCE_DUPLICATE", "sources")
        observed[key] = digest
        observed_order.append(key)
    if observed != PINNED_SOURCES or tuple(observed_order) != tuple(PINNED_SOURCES):
        _fail("SOURCE_INVENTORY_DRIFT", "sources")
    for source_name, expected_digest in PINNED_SOURCES.items():
        source = _repository_regular_file(root, Path(source_name), "pinned_source")
        if sha256_file(source) != expected_digest:
            _fail("SOURCE_DIGEST_MISMATCH", "pinned_source")


def _find_exact_record(
    document: Mapping[str, Any], collection: str, record_id: str, field: str
) -> Mapping[str, Any]:
    rows = _list(document.get(collection), field)
    matches = [
        _mapping(row, field)
        for row in rows
        if isinstance(row, Mapping) and row.get("id") == record_id
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_MISSING", field)
    return matches[0]


def _load_repo_yaml(root: Path, relative: str, field: str) -> Mapping[str, Any]:
    return _mapping(
        load_yaml(_repository_regular_file(root, Path(relative), field)), field
    )


def _validate_authority_semantics(root: Path) -> None:
    backlog = _load_repo_yaml(
        root,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    _strict_match(
        _find_exact_record(backlog, "stories", "ST-1506", "backlog.stories"),
        EXPECTED_STORY,
        "backlog.ST-1506",
    )

    decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        _strict_match(
            _find_exact_record(decisions, "items", decision_id, "open_decisions.items"),
            expected,
            f"open_decisions.{decision_id}",
        )

    tests = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    _strict_match(
        _find_exact_record(tests, "suites", "TST-032", "test_catalog.suites"),
        EXPECTED_TST_032,
        "test_catalog.TST-032",
    )

    release = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_release_evidence_template_v1.0.yaml",
        "release_evidence",
    )
    evidence_rows = _list(
        release.get("test_evidence"), "release_evidence.test_evidence"
    )
    evidence_matches = [
        _mapping(row, "release_evidence.test_evidence")
        for row in evidence_rows
        if isinstance(row, Mapping) and row.get("suite_id") == "TST-032"
    ]
    if len(evidence_matches) != 1:
        _fail("AUTHORITY_RECORD_MISSING", "release_evidence.test_evidence")
    evidence = evidence_matches[0]
    _strict_match(
        evidence,
        {
            "suite_id": "TST-032",
            "required": True,
            "status": "NOT_EXECUTED",
            "artifact_uri": None,
            "executed_at": None,
            "executor": None,
        },
        "release_evidence.TST-032",
    )
    _strict_match(release.get("decision"), "NOT_READY", "release_evidence.decision")
    _strict_match(
        release.get("approvals"),
        {
            "engineering": None,
            "security": None,
            "operations": None,
            "product_owner": None,
        },
        "release_evidence.approvals",
    )

    handoff = _load_repo_yaml(
        root,
        DESIGN_HANDOFF_PATH.as_posix(),
        "provider_neutral_design_handoff",
    )
    if tuple(handoff) != (
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
    ):
        _fail("CLOSED_SCHEMA_VIOLATION", "provider_neutral_design_handoff")
    _strict_match(handoff.get("schema"), "DESIGN_HANDOFF_V1", "handoff.schema")
    _strict_match(handoff.get("version"), 1, "handoff.version")
    _strict_match(
        handoff.get("record_status"),
        "RECORDED_DURABLE_OWNER_DECISION",
        "handoff.record_status",
    )
    _strict_match(handoff.get("approved_story"), "ST-1506", "handoff.story")
    for field in (
        "approved_scope",
        "source_design_refs",
        "rationale",
        "rejected_alternatives",
        "constraints",
        "security_and_approval_gates",
        "acceptance_criteria",
        "required_test_evidence",
    ):
        if not _list(handoff.get(field), f"handoff.{field}"):
            _fail("FIXED_VALUE_VIOLATION", f"handoff.{field}")
    decision = _mapping(handoff.get("decision"), "handoff.decision")
    _strict_match(
        decision.get("full_production_provider_policy"),
        "STRICT_PROVIDER_NEUTRAL_CAPABILITY_ADMISSION",
        "handoff.decision.provider_policy",
    )
    for field in ("selected_profile", "default_profile", "fallback_profile"):
        _strict_match(decision.get(field), None, f"handoff.decision.{field}")
    _strict_match(
        decision.get("required_capability_ids"),
        list(REQUIRED_CAPABILITY_IDS),
        "handoff.decision.required_capability_ids",
    )
    _strict_match(
        decision.get("required_dependency_stories"),
        list(DEPENDENCY_STORIES),
        "handoff.decision.required_dependency_stories",
    )
    _strict_match(
        decision.get("predecessor_boundary"),
        {
            "st_1501_through_st_1505": (
                "CURRENT_PROVIDER_NEUTRAL_DEPENDENCY_CONTRACTS"
            ),
            "mandatory_provider_neutral_semantics_for_st_1506": True,
            "complete_capability_and_evidence_chain_required": True,
            "provider_selection_authority": "NONE",
            "eligibility_shortcut": False,
            "evidence_substitute": False,
        },
        "handoff.decision.predecessor_boundary",
    )
    _strict_match(
        handoff.get("open_decision_state"),
        {
            "OD-009": {
                "status": "HUMAN_DECISION_REQUIRED",
                "resolved": False,
                "blocking": True,
                "safe_default": "PRODUCTION_DISABLED",
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
                "safe_default": ("REFERENCE_METADATA_ONLY_PRODUCTION_APPLY_FORBIDDEN"),
            },
            "OD-015": {
                "status": "EXTERNAL_EVIDENCE_REQUIRED",
                "resolved": False,
                "blocking": True,
                "safe_default": "RECORDED_FIXTURES_ONLY",
            },
        },
        "handoff.open_decision_state",
    )
    if semantic_sha256(handoff) != EXPECTED_HANDOFF_SEMANTIC_SHA256:
        _fail("HANDOFF_SEMANTIC_DRIFT", "provider_neutral_design_handoff")


def _expected_predecessor_binding(
    story_id: str,
    owner_generator_path: str,
    handoff_path: str,
    contract_path: str,
    plan_path: str,
    action_counts: Mapping[str, int],
) -> dict[str, object]:
    expected: dict[str, object] = {
        "story_id": story_id,
        "owner_generator_uri": f"repo://{owner_generator_path}",
        "owner_generator_sha256": PREDECESSOR_SOURCES[owner_generator_path],
        "design_handoff_uri": f"repo://{handoff_path}",
        "design_handoff_sha256": PREDECESSOR_SOURCES[handoff_path],
        "design_handoff_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[handoff_path],
        "contract_uri": f"repo://{contract_path}",
        "contract_sha256": PREDECESSOR_SOURCES[contract_path],
        "contract_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[contract_path],
        "reference_plan_uri": f"repo://{plan_path}",
        "reference_plan_sha256": PREDECESSOR_SOURCES[plan_path],
        "reference_plan_semantic_sha256": PREDECESSOR_SEMANTIC_SHA256[plan_path],
        "required_provider_policy": DEPENDENCY_POLICIES[story_id],
        "required_admission_status": "NOT_EVALUATED",
        "required_eligible": False,
        "required_complete_mapping": False,
        "required_selected_values": "UNSET",
        "required_activation_status": "DISABLED",
        "required_network_access": "FORBIDDEN",
        "required_credential_access": "FORBIDDEN",
        "required_live_provider_calls": "FORBIDDEN",
        "required_external_writes": "FORBIDDEN",
    }
    if story_id == "ST-1504":
        expected["required_credential_issuance"] = "FORBIDDEN"
    expected["required_reference_plan_executable"] = False
    expected["required_action_counts"] = copy.deepcopy(dict(action_counts))
    return expected


def _validate_predecessor_bindings(contract: Mapping[str, Any]) -> None:
    bindings = _mapping(contract.get("predecessor_bindings"), "predecessor_bindings")
    expected_keys = tuple(
        specification[0] for specification in PREDECESSOR_SPECIFICATIONS
    )
    if tuple(bindings) != expected_keys:
        _fail("CLOSED_SCHEMA_VIOLATION", "predecessor_bindings")
    for (
        binding_name,
        story_id,
        owner_generator_path,
        handoff_path,
        contract_path,
        plan_path,
        _admission_name,
        action_counts,
    ) in PREDECESSOR_SPECIFICATIONS:
        _strict_match(
            bindings.get(binding_name),
            _expected_predecessor_binding(
                story_id,
                owner_generator_path,
                handoff_path,
                contract_path,
                plan_path,
                action_counts,
            ),
            f"predecessor_bindings.{binding_name}",
        )


def _load_predecessor_document(
    root: Path, relative: str, *, is_json: bool = False
) -> Mapping[str, Any]:
    path = _repository_regular_file(root, Path(relative), "predecessor")
    document = _mapping(load_json(path) if is_json else load_yaml(path), "predecessor")
    if semantic_sha256(document) != PREDECESSOR_SEMANTIC_SHA256[relative]:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    return document


def _render_predecessor_plan(
    story_id: str, contract: Mapping[str, Any], root: Path
) -> bytes:
    try:
        if story_id == "ST-1501":
            from scripts import build_st1501_terraform_foundation as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1502":
            from scripts import build_st1502_data_services as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1503":
            from scripts import build_st1503_compute_edge as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1504":
            from scripts import build_st1504_github_oidc as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
        if story_id == "ST-1505":
            from scripts import build_st1505_staging_deployment as owner

            model = owner.validate_contract(copy.deepcopy(dict(contract)), root)
            return owner.render_reference_plan(model)
    except Exception:  # noqa: BLE001
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    _fail("PREDECESSOR_STORY_UNKNOWN", "predecessor")


def _validate_predecessor_semantics(root: Path) -> None:
    for (
        _binding_name,
        story_id,
        _owner_generator_path,
        handoff_path,
        contract_path,
        plan_path,
        _admission_name,
        _action_counts,
    ) in PREDECESSOR_SPECIFICATIONS:
        handoff = _load_predecessor_document(root, handoff_path)
        _strict_match(
            handoff.get("approved_story"), story_id, "predecessor.handoff.story"
        )
        contract = _load_predecessor_document(root, contract_path)
        plan_path_value = _repository_regular_file(
            root, Path(plan_path), "predecessor_plan"
        )
        plan = _load_predecessor_document(root, plan_path, is_json=True)
        plan_document = _mapping(plan.get("document"), "predecessor.plan.document")
        _strict_match(plan_document.get("story_id"), story_id, "predecessor.plan.story")
        _strict_match(
            plan_document.get("executable"), False, "predecessor.plan.executable"
        )
        expected_bytes = _render_predecessor_plan(story_id, contract, root)
        try:
            actual_bytes = plan_path_value.read_bytes()
        except OSError:
            _fail("FILE_UNAVAILABLE", "predecessor_plan")
        if actual_bytes != expected_bytes:
            _fail("PREDECESSOR_GENERATED_DRIFT", "predecessor_plan")


def _object_fingerprint(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        ).encode("utf-8")
    except TypeError, ValueError:
        _fail("TYPE_MISMATCH", "contract")
    return sha256_bytes(encoded)


def _validate_provider_neutral_admission(contract: Mapping[str, Any]) -> None:
    admission = _mapping(
        contract.get("provider_neutral_admission"), "provider_neutral_admission"
    )
    if tuple(admission) != PROVIDER_NEUTRAL_ADMISSION_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "provider_neutral_admission")
    _strict_match(
        admission.get("classification"),
        "STRICT_PROVIDER_NEUTRAL_CAPABILITY_ADMISSION",
        "provider_neutral_admission.classification",
    )
    _strict_match(
        admission.get("admission_status"),
        "NOT_EVALUATED",
        "provider_neutral_admission.admission_status",
    )
    _strict_match(
        admission.get("eligible"), False, "provider_neutral_admission.eligible"
    )
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(admission.get(field), None, f"provider_neutral_admission.{field}")
    _strict_match(
        admission.get("concrete_alternate_provider_selected"),
        False,
        "provider_neutral_admission.concrete_alternate_provider_selected",
    )
    _strict_match(
        admission.get("eligible_profile_kinds"),
        ["AWS", "OTHER_CLOUD", "OWNER_MANAGED_INFRASTRUCTURE"],
        "provider_neutral_admission.eligible_profile_kinds",
    )
    _strict_match(
        admission.get("dependency_admission_policy"),
        {
            "cardinality": "EXACTLY_ONE_CURRENT_BINDING_PER_REQUIRED_DEPENDENCY",
            "required_dependency_count": len(DEPENDENCY_STORIES),
            "satisfied_dependency_count": 0,
            "complete_dependency_chain": False,
            "missing_dependency": "REJECT",
            "unknown_dependency": "REJECT",
            "duplicate_dependency": "REJECT",
            "reordered_dependency": "REJECT",
            "partial_dependency": "REJECT",
            "implicit_dependency": "REJECT",
            "predecessor_completion_only": "REJECT",
            "provider_label_only": "REJECT",
            "dependency_shortcut": "FORBIDDEN",
        },
        "provider_neutral_admission.dependency_admission_policy",
    )
    dependency_rows = _list(
        admission.get("dependency_admission_requirements"),
        "provider_neutral_admission.dependencies",
    )
    observed_dependencies: list[str] = []
    for raw_row in dependency_rows:
        row = _mapping(raw_row, "provider_neutral_admission.dependency")
        if tuple(row) != (
            "story_id",
            "required_policy",
            "current_admission_status",
            "current_eligible",
            "selected_profile_id",
            "selected_provider_name",
            "evidence_references",
            "dependency_status",
        ):
            _fail("CLOSED_SCHEMA_VIOLATION", "provider_neutral_admission.dependency")
        story_id = row.get("story_id")
        if type(story_id) is not str or story_id not in DEPENDENCY_POLICIES:
            _fail("UNKNOWN_DEPENDENCY_MAPPING", "provider_neutral_admission.dependency")
        if story_id in observed_dependencies:
            _fail(
                "DUPLICATE_DEPENDENCY_MAPPING",
                "provider_neutral_admission.dependency",
            )
        observed_dependencies.append(story_id)
        _strict_match(
            row,
            {
                "story_id": story_id,
                "required_policy": DEPENDENCY_POLICIES[story_id],
                "current_admission_status": "NOT_EVALUATED",
                "current_eligible": False,
                "selected_profile_id": None,
                "selected_provider_name": None,
                "evidence_references": [],
                "dependency_status": "REQUIRED_NOT_SATISFIED",
            },
            "provider_neutral_admission.dependency",
        )
    if set(observed_dependencies) != set(DEPENDENCY_STORIES):
        _fail("MISSING_DEPENDENCY_MAPPING", "provider_neutral_admission.dependencies")
    if tuple(observed_dependencies) != DEPENDENCY_STORIES:
        _fail(
            "DEPENDENCY_MAPPING_ORDER_DRIFT",
            "provider_neutral_admission.dependencies",
        )
    _strict_match(
        admission.get("mapping_policy"),
        {
            "cardinality": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
            "required_mapping_count": len(REQUIRED_CAPABILITY_IDS),
            "configured_mapping_count": 0,
            "complete_mapping": False,
            "missing_mapping": "REJECT",
            "unknown_mapping": "REJECT",
            "duplicate_mapping": "REJECT",
            "implicit_mapping": "REJECT",
            "partial_mapping": "REJECT",
            "provider_label_only": "REJECT",
            "unmapped_eligibility": "FORBIDDEN",
        },
        "provider_neutral_admission.mapping_policy",
    )
    _strict_match(
        admission.get("aws_reference_boundary"),
        {
            "canonical_decision_id": "INT-DEC-007",
            "reference_profile": "AWS_TOKYO",
            "reference_region_metadata": "ap-northeast-1",
            "role": "OPTIONAL_HISTORICAL_REFERENCE_ONLY",
            "default": False,
            "implicit_fallback": False,
            "selected_binding": False,
            "eligibility_shortcut": False,
            "admission_requirement": False,
            "evidence_substitute": False,
        },
        "provider_neutral_admission.aws_reference_boundary",
    )
    _strict_match(
        admission.get("predecessor_reference_boundary"),
        {
            "st_1501_through_st_1505": (
                "CURRENT_PROVIDER_NEUTRAL_DEPENDENCY_CONTRACTS"
            ),
            "mandatory_provider_neutral_semantics": True,
            "complete_capability_and_evidence_chain_required": True,
            "provider_selection_authority": "NONE",
            "eligibility_shortcut": "FORBIDDEN",
            "evidence_substitute": False,
        },
        "provider_neutral_admission.predecessor_reference_boundary",
    )
    _strict_match(
        admission.get("evidence_equivalence_policy"),
        {
            "dependency_chain_evidence": "REQUIRED_NOT_CONFIGURED",
            "capability_evidence": "REQUIRED_NOT_CONFIGURED",
            "security_evidence": "REQUIRED_NOT_CONFIGURED",
            "operations_evidence": "REQUIRED_NOT_CONFIGURED",
            "release_evidence": "REQUIRED_NOT_CONFIGURED",
            "independent_migration_review_evidence": "REQUIRED_NOT_CONFIGURED",
            "transport_security_evidence": "REQUIRED_NOT_CONFIGURED",
            "backup_restore_evidence": "REQUIRED_NOT_CONFIGURED",
            "region_and_data_residency_evidence": "REQUIRED_NOT_CONFIGURED",
            "same_requirements_for_all_profile_kinds": True,
            "provider_label_as_evidence": "FORBIDDEN",
            "reference_metadata_as_evidence": "FORBIDDEN",
            "partial_predecessor_chain_as_evidence": "FORBIDDEN",
            "predecessor_completion_as_evidence": "FORBIDDEN",
            "local_test_as_live_evidence": "FORBIDDEN",
        },
        "provider_neutral_admission.evidence_equivalence_policy",
    )

    mappings = _list(
        admission.get("capability_mapping_requirements"),
        "provider_neutral_admission.capability_mapping_requirements",
    )
    observed_ids: list[str] = []
    for raw_mapping in mappings:
        mapping = _mapping(raw_mapping, "provider_neutral_admission.mapping")
        if tuple(mapping) != (
            "capability_id",
            "required_outcome",
            "selected_mapping",
            "evidence_references",
            "mapping_status",
        ):
            _fail("CLOSED_SCHEMA_VIOLATION", "provider_neutral_admission.mapping")
        capability_id = mapping.get("capability_id")
        if type(capability_id) is not str or capability_id not in (
            REQUIRED_CAPABILITY_OUTCOMES
        ):
            _fail("UNKNOWN_CAPABILITY_MAPPING", "provider_neutral_admission.mapping")
        if capability_id in observed_ids:
            _fail("DUPLICATE_CAPABILITY_MAPPING", "provider_neutral_admission.mapping")
        observed_ids.append(capability_id)
        _strict_match(
            mapping.get("required_outcome"),
            REQUIRED_CAPABILITY_OUTCOMES[capability_id],
            "provider_neutral_admission.mapping.required_outcome",
        )
        _strict_match(
            mapping.get("selected_mapping"),
            None,
            "provider_neutral_admission.mapping.selected_mapping",
        )
        _strict_match(
            mapping.get("evidence_references"),
            [],
            "provider_neutral_admission.mapping.evidence_references",
        )
        _strict_match(
            mapping.get("mapping_status"),
            "REQUIRED_NOT_CONFIGURED",
            "provider_neutral_admission.mapping.mapping_status",
        )
    if set(observed_ids) != set(REQUIRED_CAPABILITY_IDS):
        _fail("MISSING_CAPABILITY_MAPPING", "provider_neutral_admission.mapping")
    if tuple(observed_ids) != REQUIRED_CAPABILITY_IDS:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "provider_neutral_admission.mapping")


def _validate_local_safety_invariants(contract: Mapping[str, Any]) -> None:
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "contract")
    document = _mapping(contract.get("document"), "document")
    _strict_match(document.get("version"), "1.2.0", "document.version")
    _strict_match(document.get("story_id"), "ST-1506", "document.story_id")
    _strict_match(document.get("executable"), False, "document.executable")
    _strict_match(document.get("activation_status"), "DISABLED", "document.activation")
    _strict_match(
        document.get("formal_verification"),
        "NOT_EXECUTED",
        "document.formal_verification",
    )

    _validate_predecessor_bindings(contract)
    _validate_provider_neutral_admission(contract)

    environment = _mapping(contract.get("environment_boundary"), "environment")
    _strict_match(environment.get("label"), "PRODUCTION", "environment.label")
    _strict_match(environment.get("apply_target"), None, "environment.apply_target")
    _strict_match(
        environment.get("reference_region_metadata"),
        "ap-northeast-1",
        "environment.reference_region",
    )
    _strict_match(
        environment.get("reference_region_use"),
        "METADATA_ONLY",
        "environment.reference_use",
    )

    _assert_unset_tree(contract.get("selected_bindings"), "selected_bindings")
    approvals = _mapping(contract.get("human_approval_gates"), "human_approval_gates")
    seen_types: set[str] = set()
    for artifact_name in APPROVAL_ARTIFACT_NAMES:
        artifact = _mapping(approvals.get(artifact_name), artifact_name)
        _strict_match(artifact.get("artifact_value"), None, f"{artifact_name}.value")
        _strict_match(artifact.get("artifact_digest"), None, f"{artifact_name}.digest")
        _strict_match(artifact.get("human_reviewer"), None, f"{artifact_name}.reviewer")
        _strict_match(
            artifact.get("approval_status"),
            "NOT_PROVIDED",
            f"{artifact_name}.status",
        )
        artifact_type = artifact.get("artifact_type")
        if type(artifact_type) is not str or artifact_type in seen_types:
            _fail("APPROVAL_ARTIFACT_NOT_DISTINCT", artifact_name)
        seen_types.add(artifact_type)
    _strict_match(
        approvals.get("populated_artifact_count"),
        0,
        "human_approval_gates.populated_artifact_count",
    )
    for field in (
        "self_approval",
        "automation_as_approval",
        "synthesized_approval",
        "forged_approval",
        "shared_artifact_slots",
        "bypass",
        "override",
    ):
        _strict_match(approvals.get(field), "FORBIDDEN", f"approvals.{field}")

    _strict_match(
        contract.get("migration_intent"),
        {
            "classification": "DECLARATIVE_COMPATIBILITY_REQUIREMENTS_ONLY",
            "strategy": "EXPAND_MIGRATE_CONTRACT",
            "migration_owner_assignment": "REQUIRED_NOT_CONFIGURED",
            "independent_migration_review": "REQUIRED_NOT_CONFIGURED",
            "independent_migration_approval": "REQUIRED_NOT_CONFIGURED",
            "compatibility_gate": "REQUIRED_NOT_CONFIGURED",
            "backward_compatibility": "REQUIRED_NOT_CONFIGURED",
            "forward_compatibility": "REQUIRED_NOT_CONFIGURED",
            "migration_dry_run": "REQUIRED_NOT_CONFIGURED",
            "lock_duration_measurement": "REQUIRED_NOT_CONFIGURED",
            "rollback_compatibility": "REQUIRED_NOT_CONFIGURED",
            "execution": "FORBIDDEN",
            "migration_self_approval": "FORBIDDEN",
            "migration_review_bypass": "FORBIDDEN",
            "destructive_change": "FORBIDDEN",
            "contract_before_expand": "FORBIDDEN",
            "direct_ddl": "FORBIDDEN",
            "down_migration_primary_recovery": "FORBIDDEN",
            "external_api_during_migration": "FORBIDDEN",
        },
        "migration_intent",
    )
    _strict_match(
        contract.get("transport_security_intent"),
        {
            "classification": (
                "DECLARATIVE_PROVIDER_NEUTRAL_CROSS_CAPABILITY_TRANSPORT_"
                "SECURITY_GATES_ONLY"
            ),
            "all_production_network_flows": "REQUIRED_NOT_CONFIGURED",
            "artifact_and_promotion_transport": "REQUIRED_NOT_CONFIGURED",
            "identity_federation_transport": "REQUIRED_NOT_CONFIGURED",
            "deployment_control_transport": "REQUIRED_NOT_CONFIGURED",
            "migration_transport": "REQUIRED_NOT_CONFIGURED",
            "canary_and_runtime_transport": "REQUIRED_NOT_CONFIGURED",
            "telemetry_and_alert_transport": "REQUIRED_NOT_CONFIGURED",
            "rollback_and_restore_transport": "REQUIRED_NOT_CONFIGURED",
            "infrastructure_provider_transport": "REQUIRED_NOT_CONFIGURED",
            "authenticated_encryption": "REQUIRED_NOT_CONFIGURED",
            "certificate_identity_and_hostname_verification": (
                "REQUIRED_NOT_CONFIGURED"
            ),
            "downgrade_resistance": "REQUIRED_NOT_CONFIGURED",
            "approved_protocol_and_cipher_policy": "REQUIRED_NOT_CONFIGURED",
            "plaintext_transport": "FORBIDDEN",
            "insecure_skip_verification": "FORBIDDEN",
            "provider_managed_label_as_evidence": "FORBIDDEN",
            "local_fixture_as_transport_evidence": "FORBIDDEN",
        },
        "transport_security_intent",
    )

    phases = _list(contract.get("logical_phases"), "logical_phases")
    if [_mapping(phase, "logical_phases.item").get("name") for phase in phases] != list(
        PHASE_NAMES
    ):
        _fail("FIXED_VALUE_VIOLATION", "logical_phases")
    for phase in phases:
        row = _mapping(phase, "logical_phases.item")
        _strict_match(row.get("status"), "DISABLED", "logical_phases.status")
        _strict_match(
            row.get("execution_status"),
            "NOT_EXECUTED",
            "logical_phases.execution",
        )
        _strict_match(row.get("action"), "FORBIDDEN", "logical_phases.action")
        _strict_match(
            row.get("auto_advance"), "FORBIDDEN", "logical_phases.auto_advance"
        )
        _strict_match(row.get("action_count"), 0, "logical_phases.action_count")

    execution = _mapping(contract.get("execution_boundary"), "execution_boundary")
    _strict_match(execution.get("activation_enabled"), False, "execution.enabled")
    _strict_match(execution.get("activation_status"), "DISABLED", "execution.status")
    _strict_match(execution.get("runtime_status"), "NOT_EXECUTED", "execution.runtime")
    _strict_match(execution.get("live_status"), "NOT_EXECUTED", "execution.live")
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "github_action",
        "provider_action",
        "aws_action",
        "iam_action",
        "staging_action",
        "deploy_action",
        "migration_review_action",
        "transport_security_action",
        "release_action",
        "production_action",
    ):
        _strict_match(execution.get(field), "FORBIDDEN", f"execution.{field}")
    _strict_match(
        execution.get("operations"),
        {name: "FORBIDDEN" for name in OPERATION_NAMES},
        "execution.operations",
    )
    _strict_match(
        execution.get("action_counts"),
        {name: 0 for name in ACTION_COUNT_NAMES},
        "execution.action_counts",
    )
    evidence = _mapping(contract.get("evidence_boundary"), "evidence_boundary")
    _strict_match(evidence.get("formal_tst_032"), "NOT_EXECUTED", "evidence.tst032")
    for field in (
        "predecessor_dependency_admission",
        "production_profile_admission",
        "hosted_ci",
        "staging",
        "live_provider",
        "migration",
        "independent_migration_review",
        "transport_security",
        "smoke",
        "canary",
        "rollback",
        "release",
        "production",
        "status_transition",
    ):
        _strict_match(evidence.get(field), "NOT_EXECUTED", f"evidence.{field}")


def validate_contract(
    contract: object, root: Path = REPO_ROOT
) -> ProductionDeploymentModel:
    value = _mapping(contract, "contract")
    _validate_local_safety_invariants(value)
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    if _object_fingerprint(value) != EXPECTED_CONTRACT_FINGERPRINT:
        _fail("CONTRACT_DEFINITION_DRIFT", "contract")
    return ProductionDeploymentModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> ProductionDeploymentModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: ProductionDeploymentModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: ProductionDeploymentModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-PRODUCTION-DEPLOYMENT-REFERENCE-PLAN-001",
            "version": "1.2.0",
            "story_id": "ST-1506",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_bindings": _section(model, "predecessor_bindings"),
        "provider_neutral_admission": _section(model, "provider_neutral_admission"),
        "open_decision_defaults": _section(model, "open_decision_defaults"),
        "environment": _section(model, "environment_boundary"),
        "selected_bindings": _section(model, "selected_bindings"),
        "human_approval_gates": _section(model, "human_approval_gates"),
        "artifact_admission": _section(model, "artifact_admission_intent"),
        "protected_environment": _section(model, "protected_environment_intent"),
        "migration": _section(model, "migration_intent"),
        "transport_security": _section(model, "transport_security_intent"),
        "canary": _section(model, "canary_intent"),
        "observability": _section(model, "observability_intent"),
        "health_and_smoke": _section(model, "health_and_smoke_intent"),
        "rollback": _section(model, "rollback_intent"),
        "logical_phases": _section(model, "logical_phases"),
        "action_counts": copy.deepcopy(execution["action_counts"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "runtime_status": execution["runtime_status"],
            "live_status": execution["live_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "github_action": execution["github_action"],
            "provider_action": execution["provider_action"],
            "aws_action": execution["aws_action"],
            "iam_action": execution["iam_action"],
            "staging_action": execution["staging_action"],
            "deploy_action": execution["deploy_action"],
            "migration_review_action": execution["migration_review_action"],
            "transport_security_action": execution["transport_security_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "operations": copy.deepcopy(execution["operations"]),
        },
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }


def render_reference_plan(model: ProductionDeploymentModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _repository_regular_file(root, relative, "source_artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: ProductionDeploymentModel,
    reference_plan: bytes,
    root: Path = REPO_ROOT,
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    environment = _mapping(model.contract["environment_boundary"], "environment")
    admission = _mapping(
        model.contract["provider_neutral_admission"], "provider_neutral_admission"
    )
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    approvals = _mapping(model.contract["human_approval_gates"], "human_approval_gates")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-PRODUCTION-DEPLOYMENT-MANIFEST-001",
            "version": "1.2.0",
            "story_id": "ST-1506",
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
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_plan),
                "sha256": sha256_bytes(reference_plan),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": evidence["deliverable_classification"],
            "environment_label": environment["label"],
            "configuration_status": environment["configuration_status"],
            "reference_region_metadata": environment["reference_region_metadata"],
            "reference_region_use": environment["reference_region_use"],
            "apply_target": environment["apply_target"],
            "activation": execution["activation_status"],
            "action_counts": copy.deepcopy(execution["action_counts"]),
            "provider_policy": admission["classification"],
            "provider_admission_status": admission["admission_status"],
            "provider_eligible": admission["eligible"],
            "required_dependency_count": len(DEPENDENCY_STORIES),
            "satisfied_dependency_count": admission["dependency_admission_policy"][
                "satisfied_dependency_count"
            ],
            "complete_dependency_chain": admission["dependency_admission_policy"][
                "complete_dependency_chain"
            ],
            "selected_profile": admission["selected_profile_id"],
            "default_profile": admission["default_profile_id"],
            "fallback_profile": admission["fallback_profile_id"],
            "required_capability_count": len(REQUIRED_CAPABILITY_IDS),
            "configured_capability_count": admission["mapping_policy"][
                "configured_mapping_count"
            ],
            "aws_reference_role": admission["aws_reference_boundary"]["role"],
            "aws_reference_default": admission["aws_reference_boundary"]["default"],
            "aws_reference_fallback": admission["aws_reference_boundary"][
                "implicit_fallback"
            ],
            "aws_reference_eligibility_shortcut": admission["aws_reference_boundary"][
                "eligibility_shortcut"
            ],
            "selected_provider": selection["cloud_provider"],
            "selected_account": selection["cloud_account_id"],
            "selected_region": selection["cloud_region"],
            "selected_repository": selection["github_repository"],
            "selected_ref": selection["github_ref"],
            "selected_workflow": selection["github_workflow"],
            "selected_role": selection["deployment_role"],
            "selected_artifact": selection["artifact_digest"],
            "approval_artifact_count": approvals["populated_artifact_count"],
            "credentials": evidence["credentials"],
            "predecessor_dependency_admission": evidence[
                "predecessor_dependency_admission"
            ],
            "production_profile_admission": evidence["production_profile_admission"],
            "formal_tst_032": evidence["formal_tst_032"],
            "hosted_ci": evidence["hosted_ci"],
            "live_provider": evidence["live_provider"],
            "migration": evidence["migration"],
            "independent_migration_review": evidence["independent_migration_review"],
            "transport_security": evidence["transport_security"],
            "smoke": evidence["smoke"],
            "canary": evidence["canary"],
            "rollback": evidence["rollback"],
            "release": evidence["release"],
            "production": evidence["production"],
            "status_transition": evidence["status_transition"],
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
    reference_plan = render_reference_plan(model)
    return {
        REFERENCE_PLAN_PATH: reference_plan,
        MANIFEST_PATH: render_manifest(model, reference_plan, root),
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


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the disabled ST-1506 Production reference artifacts.",
        allow_abbrev=False,
        add_help=False,
    )
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        parser.error("unsupported argument")
    return argparse.Namespace(check=arguments == ["--check"])


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except ProductionDeploymentContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1506 Production deployment check passed")
    else:
        print("ST-1506 Production deployment artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
