#!/usr/bin/env python3
"""Build the disabled, provider-free ST-1502 logical data-services module."""

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

CONTRACT_PATH: Final = Path(
    "changes/st-1502/contracts/data-services-foundation.v1.yaml"
)
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/data-services/data-services.reference-plan.v1.json"
)
LOGICAL_PLAN_PATH: Final = Path(
    "infra/terraform/data-services/data-services.logical-plan.v1.json"
)
TOOLCHAIN_LOCK_PATH: Final = Path(
    "infra/terraform/data-services/terraform-validation-toolchain.lock.v1.json"
)
HCL_PATHS: Final = tuple(
    Path("infra/terraform/data-services") / name
    for name in ("versions.tf", "variables.tf", "locals.tf", "checks.tf", "outputs.tf")
)
MANIFEST_PATH: Final = Path("changes/st-1502/manifest.yaml")
GENERATED_ARTIFACT_PATHS: Final = (
    REFERENCE_PLAN_PATH,
    LOGICAL_PLAN_PATH,
    TOOLCHAIN_LOCK_PATH,
    *HCL_PATHS,
)
GENERATED_PATHS: Final = (*GENERATED_ARTIFACT_PATHS, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1502_data_services.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1502_data_services.py"
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
    "changes/st-1502/DESIGN_HANDOFF_V1_ST1502_PROVIDER_NEUTRAL_DATA_SERVICES.yaml": (
        "2826ec76994e6fb1d4e1c41bc0ce7affecc96351d1fcf527e45c2909bb89f97c"
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
    Path("changes/st-1502/IMPLEMENTATION_RECORD_V2_ST1502_LOGICAL_HCL.yaml"),
    Path("changes/st-1502/LOCAL_COMPLETION_EVIDENCE_V2.md"),
    Path("changes/st-1502/README.md"),
    Path("scripts/build_st1502_data_services.py"),
    Path("tests/st1502/conftest.py"),
    Path("tests/st1502/test_contract.py"),
    Path("tests/st1502/test_generation.py"),
    Path("tests/st1502/test_logical_hcl.py"),
    Path("tests/st1502/test_negative_cases.py"),
)

EXPECTED_PREDECESSOR_TOOLCHAIN_SEMANTIC_SHA256: Final = (
    "db631e5421d5eea0534737b1df03425ccb873cfe981ad96409d3c90aeef4de1a"
)
EXPECTED_HANDOFF_SOURCE_DESIGN_REFS: Final = (
    "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
    "repo://docs/canonical/01_integration/"
    "RAOS_07_canonical_decisions_v1.0.yaml#INT-DEC-007",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-014",
    "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-015",
    "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-1502",
    "repo://changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml",
    "repo://docs/upstream/key_documents/"
    "RAOS_02_system_architecture_v0.1.md#RAOS-ARCH-001",
    "repo://docs/canonical/06_ops/"
    "RAOS_12_operations_reliability_design_v1.0.md#RAOS-OPS-001",
    "repo://docs/canonical/04_security/"
    "RAOS_10_security_privacy_design_v1.0.md#RAOS-SEC-001",
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-026",
    "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-029",
)

EXPECTED_STORY: Final = {
    "id": "ST-1502",
    "epic_id": "EPIC-15",
    "title": "Data services infrastructure",
    "objective": "RDS/S3/SQS/Secrets/KMSをIaC化",
    "depends_on": ["ST-1501"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["modules/config"],
    "acceptance_criteria": ["private/encrypted/backups/policies"],
    "test_suites": ["TST-026", "TST-029"],
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
    "OD-014": {
        "id": "OD-014",
        "topic": "retention_periods",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Deletion jobs",
        "owner": "Privacy/Finance/Legal",
        "decision_needed": (
            "Analytics個票、Security Log、AI Artifact、成果データの保持期間を承認"
        ),
        "default_behavior": "自動削除Jobは無効、最小収集",
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
    "TST-029": {
        "id": "TST-029",
        "name": "Backup restore drill",
        "layer": "recovery",
        "purpose": "RDS/Object/Configのrestoreと整合",
        "candidate_tools": ["isolated restore environment"],
        "release_blocking": True,
        "environments": ["staging/recovery"],
        "owner": "Operations",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-004": "Role/Scope/Siteで最小権限",
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-DATA-001": "TLSをPublic/Internal/Providerで要求",
    "SEC-DATA-002": "RDS/S3/backup/logを暗号化",
    "SEC-DATA-003": "SecretをDB/Repo/Logへ置かない",
    "SEC-DATA-004": "Raw/SnapshotへSHA-256とVersionを記録",
    "SEC-DATA-009": "Backup access/rotation/deleteを分離",
    "SEC-INFRA-001": "RDS/worker/object admin endpointをPublicにしない",
    "SEC-INFRA-006": "Artifact bucketのpublic accessを遮断",
    "SEC-INFRA-007": "publiclyAccessible=false、backup、deletion protection",
    "SEC-INFRA-008": "Producer/consumer queue権限を分離",
    "SEC-OPS-002": "Provider/AWS/DB secretのrotation手順",
    "SEC-OPS-006": "Restore環境を隔離しAccessを制御",
}

QUEUE_CLASSES: Final = (
    "ingestion",
    "ai",
    "quality",
    "publication",
    "freshness",
    "analytics",
    "notification",
)
BUCKET_ROLES: Final = (
    "raw",
    "publication",
    "uploads_quarantine",
    "exports",
    "audit_logs",
)
ELIGIBLE_PROFILE_KINDS: Final = (
    "AWS",
    "OTHER_CLOUD",
    "OWNER_MANAGED_INFRASTRUCTURE",
)
DATA_SERVICE_BINDING_NAMES: Final = (
    "provider",
    "account_or_project",
    "region",
    "relational_persistence",
    "object_storage",
    "queue",
    "secrets",
    "key_management",
    "data_services_plugin_or_adapter",
)
DATA_SERVICE_CAPABILITY_OUTCOMES: Final = (
    (
        "relational_postgresql_compatible_persistence_and_migrations",
        "PRIVATE_ENCRYPTED_POSTGRESQL_COMPATIBLE_PERSISTENCE_WITH_CONTROLLED_MIGRATIONS",
    ),
    (
        "immutable_versioned_object_storage_and_integrity",
        "PRIVATE_ENCRYPTED_VERSIONED_OBJECT_STORAGE_WITH_REQUIRED_IMMUTABILITY_AND_INTEGRITY",
    ),
    (
        "at_least_once_queue_dlq_and_idempotency",
        "AT_LEAST_ONCE_DELIVERY_WITH_DLQ_REDIVE_ALERTING_AND_IDEMPOTENT_CONSUMERS",
    ),
    (
        "workload_secrets_and_key_management",
        "NON_AMBIENT_LEAST_PRIVILEGE_ROTATABLE_SECRETS_AND_KEYS_WITH_AUDIT",
    ),
    (
        "data_service_backup_restore_and_recovery",
        "RELATIONAL_OBJECT_CONFIGURATION_AND_SECRET_RECOVERY_WITH_ISOLATED_RESTORE_DRILL",
    ),
    (
        "data_service_observability_audit_and_alerting",
        "DATABASE_STORAGE_QUEUE_SECRET_KEY_TELEMETRY_AUDIT_ALERTING_AND_DRIFT_EVIDENCE",
    ),
    (
        "environment_and_private_data_plane_isolation",
        "SEPARATE_DEVELOPMENT_PRODUCTION_AND_PRIVATE_DATA_PLANE_BOUNDARIES",
    ),
    (
        "region_and_data_residency",
        "APPROVED_PRIMARY_BACKUP_CROSS_BORDER_AND_DATA_RESIDENCY_EVIDENCE",
    ),
    (
        "human_approved_release_migration_and_rollback",
        "HUMAN_APPROVED_IAC_MIGRATION_PROMOTION_ROLLBACK_AND_RECOVERY",
    ),
)
AWS_REFERENCE_SERVICE_MAPPINGS: Final = (
    (
        "RDS",
        "relational_postgresql_compatible_persistence_and_migrations",
    ),
    ("S3", "immutable_versioned_object_storage_and_integrity"),
    ("SQS", "at_least_once_queue_dlq_and_idempotency"),
    ("Secrets Manager", "workload_secrets_and_key_management"),
    ("KMS", "workload_secrets_and_key_management"),
)
NATIVE_COMMANDS: Final = ("init", "plan", "apply", "destroy", "import", "refresh")
PREDECESSOR_ACTION_NAMES: Final = ("create", "update", "delete")
ACTION_NAMES: Final = (
    "create",
    "update",
    "delete",
    "migrate",
    "backup",
    "restore",
    "redrive",
    "rotate",
)
OBJECT_NODE_IDS: Final = tuple(f"object_{role}" for role in BUCKET_ROLES)
PRIMARY_QUEUE_NODE_IDS: Final = tuple(
    f"queue_{queue_class}" for queue_class in QUEUE_CLASSES
)
DLQ_NODE_IDS: Final = tuple(f"queue_{queue_class}_dlq" for queue_class in QUEUE_CLASSES)
KMS_NODE_IDS: Final = (
    "kms_relational",
    "kms_object_storage",
    "kms_queue",
    "kms_secret_metadata",
)
BACKUP_NODE_IDS: Final = (
    "backup_relational_pitr",
    "backup_object_versions",
    "backup_configuration",
)
IAM_ROLE_IDS: Final = (
    "iam_db_workload",
    "iam_object_writer",
    "iam_object_reader",
    "iam_queue_producer",
    "iam_queue_consumer",
    "iam_queue_redrive_operator",
    "iam_secret_reader",
    "iam_backup_operator",
    "iam_restore_operator",
)
SUCCESSOR_GATE_EVIDENCE: Final = (
    "OD-013_RESOLVED_REGION_RESIDENCY",
    "OD-014_RESOLVED_RETENTION_DELETION",
    "OD-015_PROVIDER_CREDENTIAL_EVIDENCE",
    "TST-026_FORMAL_SECURITY_EVIDENCE",
    "TST-029_ISOLATED_RESTORE_EVIDENCE",
    "PROVIDER_SCHEMA_AND_PLUGIN_PROVENANCE",
    "PRIVATE_NETWORK_AND_ACCOUNT_ISOLATION",
    "LEAST_PRIVILEGE_POLICY_REVIEW",
    "BACKUP_RESTORE_AND_KEY_RECOVERY",
    "HUMAN_APPROVED_RELEASE_AND_ROLLBACK",
)
IAM_PERMISSIONS: Final = {
    "iam_db_workload": ("database.connect", "database.read", "database.write"),
    "iam_object_writer": ("object.create", "object.version.read"),
    "iam_object_reader": ("object.read", "object.version.read"),
    "iam_queue_producer": ("queue.send",),
    "iam_queue_consumer": (
        "queue.receive",
        "queue.delete",
        "queue.visibility.change",
    ),
    "iam_queue_redrive_operator": ("queue.redrive",),
    "iam_secret_reader": ("secret.metadata.read", "secret.value.resolve_by_workload"),
    "iam_backup_operator": ("backup.create", "backup.verify"),
    "iam_restore_operator": ("restore.isolated", "restore.verify"),
}
HCL_ALLOWED_BLOCKS_BY_FILE: Final = {
    "versions.tf": ("terraform",),
    "variables.tf": ("variable",) * 13,
    "locals.tf": ("locals",),
    "checks.tf": ("check",) * 8,
    "outputs.tf": ("output",) * 5,
}
HCL_FORBIDDEN_TOP_LEVEL_BLOCKS: Final = {
    "provider",
    "backend",
    "cloud",
    "module",
    "data",
    "resource",
    "import",
    "run",
    "provisioner",
}
HCL_TOP_LEVEL_BLOCK_PATTERN: Final = re.compile(
    r'(?m)^(terraform|variable|locals|check|output|provider|backend|cloud|module|data|resource|import|run|provisioner)(?:\s+"[^"]+")?(?:\s+"[^"]+")?\s*\{'
)
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
MAX_HCL_BYTES: Final = 512 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _logical_node(
    node_id: str,
    kind: str,
    reference_service: str,
    *,
    persisted_data: bool = False,
    network_interaction: bool = False,
    backup_required: bool = False,
    backup_declared: bool = False,
    immutable_required: bool = False,
    immutable_declared: bool = False,
    dlq_required: bool = False,
    dlq_declared: bool = False,
    key_rotation_required: bool = False,
) -> dict[str, object]:
    return {
        "node_id": node_id,
        "kind": kind,
        "reference_service": reference_service,
        "persisted_data": persisted_data,
        "network_interaction": network_interaction,
        "public_access": False,
        "encryption_at_rest": persisted_data,
        "transport_encryption": network_interaction,
        "backup_required": backup_required,
        "backup_declared": backup_declared,
        "immutable_required": immutable_required,
        "immutable_declared": immutable_declared,
        "dlq_required": dlq_required,
        "dlq_declared": dlq_declared,
        "contains_secret_material": False,
        "key_rotation_required": key_rotation_required,
        "key_rotation_declared": key_rotation_required,
        "least_privilege": True,
        "wildcard_iam": False,
    }


def logical_resource_nodes() -> list[dict[str, object]]:
    nodes = [
        _logical_node(
            "relational_database",
            "RELATIONAL_DATABASE",
            "RDS",
            persisted_data=True,
            network_interaction=True,
            backup_required=True,
            backup_declared=True,
        )
    ]
    nodes.extend(
        _logical_node(
            node_id,
            "OBJECT_STORAGE",
            "S3",
            persisted_data=True,
            network_interaction=True,
            backup_required=True,
            backup_declared=True,
            immutable_required=True,
            immutable_declared=True,
        )
        for node_id in OBJECT_NODE_IDS
    )
    nodes.extend(
        _logical_node(
            node_id,
            "PRIMARY_QUEUE",
            "SQS",
            persisted_data=True,
            network_interaction=True,
            dlq_required=True,
            dlq_declared=True,
        )
        for node_id in PRIMARY_QUEUE_NODE_IDS
    )
    nodes.extend(
        _logical_node(
            node_id,
            "DEAD_LETTER_QUEUE",
            "SQS",
            persisted_data=True,
            network_interaction=True,
        )
        for node_id in DLQ_NODE_IDS
    )
    nodes.append(
        _logical_node(
            "secret_metadata",
            "SECRET_METADATA_BOUNDARY",
            "Secrets Manager",
            persisted_data=True,
            network_interaction=True,
            backup_required=True,
            backup_declared=True,
        )
    )
    nodes.extend(
        _logical_node(
            node_id,
            "ENCRYPTION_KEY",
            "KMS",
            network_interaction=True,
            key_rotation_required=True,
        )
        for node_id in KMS_NODE_IDS
    )
    nodes.extend(
        _logical_node(node_id, "RECOVERY_DECLARATION", "LOGICAL")
        for node_id in BACKUP_NODE_IDS
    )
    nodes.extend(
        _logical_node(node_id, "IAM_PERMISSION_SET", "LOGICAL")
        for node_id in IAM_ROLE_IDS
    )
    return nodes


def logical_resource_edges() -> list[dict[str, str]]:
    edges: list[dict[str, str]] = [
        {
            "from": "relational_database",
            "to": "kms_relational",
            "relationship": "ENCRYPTED_BY",
        }
    ]
    edges.extend(
        {"from": node_id, "to": "kms_object_storage", "relationship": "ENCRYPTED_BY"}
        for node_id in OBJECT_NODE_IDS
    )
    edges.extend(
        {"from": node_id, "to": "kms_queue", "relationship": "ENCRYPTED_BY"}
        for node_id in (*PRIMARY_QUEUE_NODE_IDS, *DLQ_NODE_IDS)
    )
    edges.append(
        {
            "from": "secret_metadata",
            "to": "kms_secret_metadata",
            "relationship": "ENCRYPTED_BY",
        }
    )
    edges.extend(
        {"from": primary, "to": dlq, "relationship": "REDRIVES_TO"}
        for primary, dlq in zip(PRIMARY_QUEUE_NODE_IDS, DLQ_NODE_IDS, strict=True)
    )
    edges.append(
        {
            "from": "backup_relational_pitr",
            "to": "relational_database",
            "relationship": "PROTECTS",
        }
    )
    edges.extend(
        {"from": "backup_object_versions", "to": node_id, "relationship": "PROTECTS"}
        for node_id in OBJECT_NODE_IDS
    )
    edges.extend(
        {"from": "backup_configuration", "to": node_id, "relationship": "RECONSTRUCTS"}
        for node_id in ("secret_metadata", *KMS_NODE_IDS)
    )
    role_targets = {
        "iam_db_workload": ("relational_database",),
        "iam_object_writer": OBJECT_NODE_IDS,
        "iam_object_reader": OBJECT_NODE_IDS,
        "iam_queue_producer": PRIMARY_QUEUE_NODE_IDS,
        "iam_queue_consumer": PRIMARY_QUEUE_NODE_IDS,
        "iam_queue_redrive_operator": (*PRIMARY_QUEUE_NODE_IDS, *DLQ_NODE_IDS),
        "iam_secret_reader": ("secret_metadata",),
        "iam_backup_operator": BACKUP_NODE_IDS,
        "iam_restore_operator": BACKUP_NODE_IDS,
    }
    for role_id, targets in role_targets.items():
        edges.extend(
            {"from": role_id, "to": target, "relationship": "AUTHORIZES"}
            for target in targets
        )
    return edges


def _queue_selection() -> dict[str, object]:
    return {
        "physical_name": None,
        "endpoint": None,
        "resource_identifier": None,
        "dlq_name": None,
        "dlq_endpoint": None,
        "dlq_resource_identifier": None,
        "delay_seconds": None,
        "visibility_timeout_seconds": None,
        "retention_seconds": None,
        "max_receive_count": None,
        "ordering_mode": None,
        "policy_document": None,
    }


def _queue_intent(queue_class: str) -> dict[str, object]:
    return {
        "class": queue_class,
        "dlq": "REQUIRED_NOT_CONFIGURED",
        "producer_consumer_separation": "REQUIRED_NOT_CONFIGURED",
        "redrive_role_separation": "REQUIRED_NOT_CONFIGURED",
        "redrive_control": "REQUIRED_NOT_CONFIGURED",
        "selected": _queue_selection(),
    }


def _binding_policy() -> dict[str, object]:
    policy: dict[str, object] = {
        name: {"selected": None, "default": None, "fallback": None}
        for name in DATA_SERVICE_BINDING_NAMES
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
        for capability_id, required_outcome in DATA_SERVICE_CAPABILITY_OUTCOMES
    ]


def _aws_reference_service_mappings() -> list[dict[str, str]]:
    return [
        {"reference_name": reference_name, "capability_id": capability_id}
        for reference_name, capability_id in AWS_REFERENCE_SERVICE_MAPPINGS
    ]


def _provider_neutral_admission() -> dict[str, object]:
    return {
        "classification": "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION",
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
        "cross_capability_security_policy": {
            "transport_encryption": ("REQUIRED_FOR_ALL_DATA_SERVICE_INTERACTIONS"),
            "encryption_at_rest": "REQUIRED_FOR_ALL_PERSISTED_DATA",
            "selected_exceptions": [],
        },
        "mapping_policy": {
            "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
            "required_capability_count": len(DATA_SERVICE_CAPABILITY_OUTCOMES),
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
            "identical_backup_restore_evidence": "REQUIRED",
            "identical_region_residency_evidence": "REQUIRED",
            "identical_migration_compatibility_evidence": "REQUIRED",
            "identical_isolation_evidence": "REQUIRED",
            "identical_transport_encryption_evidence": "REQUIRED",
            "provider_label_as_evidence": "FORBIDDEN",
            "service_label_as_evidence": "FORBIDDEN",
            "reference_metadata_as_evidence": "FORBIDDEN",
            "local_test_as_live_evidence": "FORBIDDEN",
        },
        "capability_mapping_requirements": _capability_mapping_requirements(),
    }


EXPECTED_LOGICAL_HCL_MODULE: Final = {
    "classification": "PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_RESOURCE_GRAPH",
    "module_path": "infra/terraform/data-services",
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
    "logical_resource_node_count": len(logical_resource_nodes()),
    "logical_iam_role_count": len(IAM_ROLE_IDS),
    "logical_primary_queue_count": len(PRIMARY_QUEUE_NODE_IDS),
    "logical_dlq_count": len(DLQ_NODE_IDS),
    "logical_object_storage_role_count": len(OBJECT_NODE_IDS),
    "deterministic_no_apply_plan_fixture": LOGICAL_PLAN_PATH.as_posix(),
    "generated_files": [path.name for path in HCL_PATHS],
    "allowed_top_level_blocks": ["terraform", "variable", "locals", "check", "output"],
    "policy_validation": "EXACT_CLOSED_BUNDLE_FORBIDDEN_BLOCK_AND_SAFETY_SCAN",
    "semantic_validation": "TERRAFORM_VALIDATE_JSON_INIT_FREE_PROVIDER_FREE",
}
EXPECTED_SUCCESSOR_ACTIVATION_PORT: Final = {
    "classification": "CLOSED_PHYSICAL_RESOURCE_ACTIVATION_PORT",
    "current_revision_activation": "FORBIDDEN",
    "successor_contract_revision_required": True,
    "selected_provider_schema": None,
    "selected_provider_plugin": None,
    "selected_account_or_project": None,
    "selected_primary_region": None,
    "selected_backup_region": None,
    "selected_state_backend": None,
    "selected_credential_source": None,
    "selected_network_segments": [],
    "selected_security_policy_bindings": [],
    "selected_retention_policy_id": None,
    "required_gate_evidence": list(SUCCESSOR_GATE_EVIDENCE),
    "supplied_gate_evidence": [],
    "complete_gate_evidence": False,
    "provider_binding": "FORBIDDEN_IN_CURRENT_REVISION",
    "resource_materialization": "FORBIDDEN_IN_CURRENT_REVISION",
    "infrastructure_plan": "FORBIDDEN",
    "infrastructure_apply": "FORBIDDEN",
}


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-DATA-SERVICES-FOUNDATION-001",
        "version": "1.2.0",
        "story_id": "ST-1502",
        "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_binding": {
        "story_id": "ST-1501",
        "extension_kind": "DATA_SERVICES",
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
        "required_terraform_version": TERRAFORM_VERSION,
        "required_terraform_binary_sha256": TERRAFORM_BINARY_SHA256,
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
    "provider_neutral_data_services_admission": _provider_neutral_admission(),
    "logical_hcl_module": EXPECTED_LOGICAL_HCL_MODULE,
    "successor_activation_port": EXPECTED_SUCCESSOR_ACTIVATION_PORT,
    "selected_configuration": {
        "provider_name": None,
        "provider_account_or_project": None,
        "production_region": None,
        "backup_region": None,
        "relational_service_binding": None,
        "object_storage_service_binding": None,
        "queue_service_binding": None,
        "secrets_service_binding": None,
        "key_management_service_binding": None,
        "data_services_plugin_or_adapter": None,
        "credential_source": None,
        "network_segment_ids": [],
        "traffic_control_policy_ids": [],
        "physical_resource_definitions": [],
    },
    "relational_persistence_intent": {
        "service_contract": "POSTGRESQL_COMPATIBLE_RELATIONAL_PERSISTENCE",
        "classification": "LOGICAL_PROVIDER_NEUTRAL_SERVICE_INTENT_ONLY",
        "private_only": "REQUIRED",
        "publicly_accessible": False,
        "transport_encryption": "REQUIRED_NOT_CONFIGURED",
        "tls_in_transit": "REQUIRED_NOT_CONFIGURED",
        "encryption_at_rest": "REQUIRED_NOT_CONFIGURED",
        "backup": "REQUIRED_NOT_CONFIGURED",
        "point_in_time_recovery": "REQUIRED_NOT_CONFIGURED",
        "deletion_protection": "REQUIRED_NOT_CONFIGURED",
        "final_snapshot_or_equivalent": "REQUIRED_NOT_CONFIGURED",
        "migration_framework_compatibility": "REQUIRED_NOT_CONFIGURED",
        "expand_migrate_contract": "REQUIRED",
        "restore_test": "REQUIRED_NOT_EXECUTED",
        "selected": {
            "engine_version": None,
            "deployment_class": None,
            "storage_capacity_gib": None,
            "storage_profile": None,
            "network_segment_ids": [],
            "endpoint": None,
            "database_name": None,
            "username": None,
            "password_secret_reference": None,
            "port": None,
            "high_availability_mode": None,
            "backup_retention_days": None,
            "backup_region": None,
            "encryption_key_reference": None,
        },
    },
    "object_storage_intent": {
        "service_contract": "PRIVATE_VERSIONED_OBJECT_STORAGE",
        "classification": "LOGICAL_PROVIDER_NEUTRAL_SERVICE_INTENT_ONLY",
        "public_access": "FORBIDDEN",
        "transport_encryption": "REQUIRED_NOT_CONFIGURED",
        "encryption_at_rest": "REQUIRED_NOT_CONFIGURED",
        "versioning": "REQUIRED_NOT_CONFIGURED",
        "force_destroy": "FORBIDDEN",
        "lifecycle_deletion": "FORBIDDEN",
        "automatic_deletion": "FORBIDDEN",
        "selected_encryption_key_reference": None,
        "retention_days": None,
        "lifecycle_rules": [],
        "roles": [
            {
                "role": "raw",
                "physical_name": None,
                "resource_identifier": None,
                "immutability": "REQUIRED_NOT_CONFIGURED",
                "integrity_metadata": "REQUIRED_NOT_CONFIGURED",
                "deletion_role_separation": "REQUIRED_NOT_CONFIGURED",
            },
            *[
                {"role": role, "physical_name": None, "resource_identifier": None}
                for role in BUCKET_ROLES[1:]
            ],
        ],
    },
    "queue_intent": {
        "service_contract": "AT_LEAST_ONCE_MESSAGE_QUEUE_WITH_DLQ",
        "classification": "LOGICAL_PROVIDER_NEUTRAL_SERVICE_INTENT_ONLY",
        "delivery_semantics": "AT_LEAST_ONCE_REQUIRED_NOT_CONFIGURED",
        "duplicate_delivery": "EXPECTED",
        "consumer_idempotency": "REQUIRED_NOT_CONFIGURED",
        "transport_encryption": "REQUIRED_NOT_CONFIGURED",
        "classes": [_queue_intent(queue_class) for queue_class in QUEUE_CLASSES],
    },
    "secrets_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_METADATA_INTENT_ONLY",
        "transport_encryption": "REQUIRED_NOT_CONFIGURED",
        "secret_values": "ABSENT",
        "secret_names": [],
        "secret_references": [],
        "ambient_credential_resolution": "FORBIDDEN",
        "environment_credential_resolution": "FORBIDDEN",
        "rotation": "REQUIRED_NOT_CONFIGURED",
        "workload_least_privilege": "REQUIRED_NOT_CONFIGURED",
        "access_audit": "REQUIRED_NOT_CONFIGURED",
        "recovery_or_reissuance": "REQUIRED_NOT_CONFIGURED",
    },
    "key_management_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_ENCRYPTION_INTENT_ONLY",
        "transport_encryption": "REQUIRED_NOT_CONFIGURED",
        "encryption": "REQUIRED",
        "rotation": "REQUIRED_NOT_CONFIGURED",
        "audit_logging": "REQUIRED_NOT_CONFIGURED",
        "workload_least_privilege": "REQUIRED_NOT_CONFIGURED",
        "recovery": "REQUIRED_NOT_CONFIGURED",
        "key_deletion": "FORBIDDEN",
        "key_identifiers": [],
        "key_references": [],
        "aliases": [],
        "policy_document": None,
        "deletion_window_days": None,
    },
    "recovery_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_RECOVERY_INTENT_ONLY",
        "relational_backup_and_pitr": "REQUIRED_NOT_CONFIGURED",
        "relational_snapshot_or_equivalent": "REQUIRED_NOT_CONFIGURED",
        "object_version_and_manifest_recovery": "REQUIRED_NOT_CONFIGURED",
        "configuration_reconstruction": "REQUIRED_NOT_CONFIGURED",
        "secret_reissuance": "REQUIRED_NOT_CONFIGURED",
        "isolated_restore_environment": "REQUIRED_NOT_CONFIGURED",
        "role_grant_and_integrity_validation": "REQUIRED_NOT_CONFIGURED",
        "rpo_rto_measurement": "REQUIRED_NOT_EXECUTED",
        "formal_tst_029": "NOT_EXECUTED",
        "selected_restore_environment": None,
    },
    "observability_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_OBSERVABILITY_INTENT_ONLY",
        "database_health_capacity_backup_metrics": "REQUIRED_NOT_CONFIGURED",
        "object_integrity_version_backup_metrics": "REQUIRED_NOT_CONFIGURED",
        "queue_depth_age_retry_dlq_metrics": "REQUIRED_NOT_CONFIGURED",
        "secret_and_key_access_audit": "REQUIRED_NOT_CONFIGURED",
        "actionable_alert_owner_and_runbook": "REQUIRED_NOT_CONFIGURED",
        "configuration_drift_detection": "REQUIRED_NOT_CONFIGURED",
        "sensitive_telemetry": "FORBIDDEN",
    },
    "data_boundary_intent": {
        "classification": "LOGICAL_PROVIDER_NEUTRAL_DATA_BOUNDARY_INTENT_ONLY",
        "development_production_isolation": "REQUIRED_NOT_CONFIGURED",
        "private_data_plane": "REQUIRED_NOT_CONFIGURED",
        "direct_public_database_access": "FORBIDDEN",
        "direct_public_object_admin_access": "FORBIDDEN",
        "direct_public_queue_admin_access": "FORBIDDEN",
        "production_region": None,
        "backup_region": None,
        "cross_border_transfer": "NOT_EVALUATED",
        "data_residency_evidence": "REQUIRED_NOT_CONFIGURED",
        "od_013_status": "HUMAN_DECISION_REQUIRED",
        "od_014_status": "HUMAN_DECISION_REQUIRED",
        "od_015_status": "EXTERNAL_EVIDENCE_REQUIRED",
    },
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "migration_action": "FORBIDDEN",
        "backup_action": "FORBIDDEN",
        "restore_action": "FORBIDDEN",
        "redrive_action": "FORBIDDEN",
        "destructive_action": "FORBIDDEN",
        "deploy_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "commands": {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
        "planned_actions": {action: 0 for action in ACTION_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "SOURCE_DERIVED_PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_DATA_SERVICES_HCL"
        ),
        "executable_iac": "VALIDATABLE_NO_PROVIDER_NO_RESOURCE_HCL_LOGICAL_GRAPH",
        "iac_toolchain": "PINNED_FROM_ST1501_VALIDATION_ONLY_1_15_9",
        "provider_plugins_or_adapters": "NONE_REQUIRED_NOT_SELECTED",
        "provider_account_or_project": "UNSET",
        "provider_profile": "UNSET",
        "credentials": "ABSENT",
        "offline_native_validation_path": "IMPLEMENTED",
        "local_native_validation": "EXECUTED_LOCAL_NOT_FORMAL",
        "logical_plan_validation": "EXECUTED_LOCAL_NOT_FORMAL",
        "transport_encryption_validation": "NOT_EXECUTED",
        "relational_migration_validation": "NOT_EXECUTED",
        "queue_delivery_validation": "NOT_EXECUTED",
        "formal_tst_026": "NOT_EXECUTED",
        "formal_tst_029": "NOT_EXECUTED",
        "restore_validation": "NOT_EXECUTED",
        "provider_validation": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}
TOP_LEVEL_KEYS: Final = {"sources", *EXPECTED_SECTIONS}


class DataServicesContractError(RuntimeError):
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
class DataServicesModel:
    """A fully validated, closed ST-1502 contract."""

    contract: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class NativeValidationResult:
    """Sanitized result from the pinned, network-isolated validator."""

    terraform_version: str
    platform: str
    provider_selections: tuple[tuple[str, str], ...]
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
    raise DataServicesContractError(code, field)


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
    except DataServicesContractError:
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
    except DataServicesContractError:
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
    _strict_match(handoff.get("approved_story"), "ST-1502", "handoff.approved_story")
    _strict_match(
        handoff.get("source_design_refs"),
        list(EXPECTED_HANDOFF_SOURCE_DESIGN_REFS),
        "handoff.source_design_refs",
    )
    _strict_match(
        handoff.get("decision"),
        {
            "data_services_provider_policy": (
                "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION"
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
            "cross_capability_security_requirements": {
                "transport_encryption": ("REQUIRED_FOR_ALL_DATA_SERVICE_INTERACTIONS"),
                "encryption_at_rest": "REQUIRED_FOR_ALL_PERSISTED_DATA",
                "selected_exceptions": [],
            },
            "required_capability_ids": [
                capability_id
                for capability_id, _required_outcome in DATA_SERVICE_CAPABILITY_OUTCOMES
            ],
            "local_hcl_implementation": {
                "classification": (
                    "PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_RESOURCE_GRAPH"
                ),
                "terraform_version_source": (
                    "ST-1501_PINNED_VALIDATION_ONLY_TOOLCHAIN"
                ),
                "provider_requirements": [],
                "provider_blocks": [],
                "backend_blocks": [],
                "module_blocks": [],
                "data_blocks": [],
                "resource_blocks": [],
                "provisioners": [],
                "default_disabled": True,
                "planned_actions": {action: 0 for action in ACTION_NAMES},
                "successor_contract_revision_required": True,
                "physical_resource_materialization": ("FORBIDDEN_IN_CURRENT_REVISION"),
                "production_apply": "FORBIDDEN",
            },
        },
        "handoff.decision",
    )
    _strict_match(
        handoff.get("open_decision_state"),
        {
            "OD-013": {
                "status": "HUMAN_DECISION_REQUIRED",
                "resolved": False,
                "blocking": True,
                "safe_default": ("REFERENCE_REGION_ONLY_PRODUCTION_APPLY_FORBIDDEN"),
            },
            "OD-014": {
                "status": "HUMAN_DECISION_REQUIRED",
                "resolved": False,
                "blocking": True,
                "safe_default": "RETENTION_UNSET_AUTOMATIC_DELETION_FORBIDDEN",
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
    story = _find_exact_record(backlog, "stories", "ST-1502", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1502")

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

    open_decisions = _mapping(
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
            open_decisions, "items", decision_id, "open_decisions.items"
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
    expected_services = {
        "database": "RDS_PostgreSQL",
        "object_store": "S3",
        "queue": "SQS_with_DLQ",
        "secrets": "Secrets_Manager",
    }
    for key, expected_service in expected_services.items():
        if (
            type(aws_mapping.get(key)) is not str
            or aws_mapping.get(key) != expected_service
        ):
            _fail("AUTHORITY_ARCHITECTURE_DRIFT", f"aws_mapping.{key}")
    if deployment.get("infrastructure_as_code") != "Terraform":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "infrastructure_as_code")
    _validate_design_handoff(root)


def _validate_predecessor_semantics(root: Path) -> None:
    predecessor_handoff = _mapping(
        load_yaml(
            _repository_regular_file(
                root,
                Path(
                    "changes/st-1501/"
                    "DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
                ),
                "predecessor_handoff",
            )
        ),
        "predecessor_handoff",
    )
    _strict_match(
        {
            "schema": predecessor_handoff.get("schema"),
            "version": predecessor_handoff.get("version"),
            "approved_story": predecessor_handoff.get("approved_story"),
        },
        {"schema": "DESIGN_HANDOFF_V1", "version": 1, "approved_story": "ST-1501"},
        "predecessor_handoff.identity",
    )
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
            "version": "1.2.0",
            "story_id": "ST-1501",
            "status": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.document",
    )
    reference = _mapping(
        contract.get("reference_architecture"), "predecessor.reference"
    )
    for field in (
        "default",
        "implicit_fallback",
        "selected_binding",
        "eligibility_shortcut",
        "admission_requirement",
        "evidence_substitute",
    ):
        _strict_match(reference.get(field), False, f"predecessor.reference.{field}")
    admission = _mapping(
        contract.get("provider_neutral_foundation_admission"),
        "predecessor.admission",
    )
    _strict_match(
        admission.get("admission_status"), "NOT_EVALUATED", "predecessor.admission"
    )
    _strict_match(admission.get("eligible"), False, "predecessor.admission")
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _strict_match(admission.get(field), None, f"predecessor.admission.{field}")
    mapping_policy = _mapping(admission.get("mapping_policy"), "predecessor.mapping")
    _strict_match(
        mapping_policy.get("configured_mapping_count"), 0, "predecessor.mapping"
    )
    _strict_match(mapping_policy.get("complete_mapping"), False, "predecessor.mapping")
    selected = _mapping(contract.get("selected_configuration"), "predecessor.selection")
    if any(value not in (None, []) for value in selected.values()):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.selection")
    execution = _mapping(contract.get("execution_boundary"), "predecessor.execution")
    _strict_match(execution.get("activation_enabled"), False, "predecessor.execution")
    _strict_match(
        execution.get("activation_status"), "DISABLED", "predecessor.execution"
    )
    _strict_match(
        execution.get("planned_actions"),
        {action: 0 for action in PREDECESSOR_ACTION_NAMES},
        "predecessor.execution",
    )
    for field in (
        "network_access",
        "credential_access",
        "live_provider_calls",
        "external_writes",
        "deploy_action",
        "release_action",
        "production_action",
    ):
        _strict_match(execution.get(field), "FORBIDDEN", f"predecessor.{field}")
    hcl_module = _mapping(contract.get("hcl_foundation_module"), "predecessor.hcl")
    _strict_match(hcl_module.get("default_disabled"), True, "predecessor.hcl")
    for field in (
        "provider_requirements",
        "provider_blocks",
        "backend_blocks",
        "cloud_blocks",
        "module_blocks",
        "data_blocks",
        "resource_blocks",
        "provisioners",
        "selected_bindings",
        "capability_mappings",
    ):
        _strict_match(hcl_module.get(field), [], f"predecessor.hcl.{field}")
    toolchain = _mapping(
        contract.get("iac_validation_toolchain"), "predecessor.toolchain"
    )
    _strict_match(toolchain.get("version"), TERRAFORM_VERSION, "predecessor.toolchain")
    boundary = _mapping(toolchain.get("validation_boundary"), "predecessor.toolchain")
    _strict_match(boundary.get("provider_plugins"), [], "predecessor.toolchain")
    _strict_match(boundary.get("initialization"), "FORBIDDEN", "predecessor.toolchain")
    _strict_match(
        boundary.get("allowed_commands"),
        ["version -json", "fmt -check -recursive", "validate -json"],
        "predecessor.toolchain",
    )
    _strict_match(
        boundary.get("forbidden_commands"),
        ["init", "plan", "apply", "destroy", "import", "refresh", "test", "console"],
        "predecessor.toolchain",
    )

    plan_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"),
        "predecessor_plan",
    )
    plan = _mapping(load_json(plan_path), "predecessor_plan")
    plan_document = _mapping(plan.get("document"), "predecessor_plan.document")
    _strict_match(
        {
            "id": plan_document.get("id"),
            "version": plan_document.get("version"),
            "story_id": plan_document.get("story_id"),
        },
        {
            "id": "RAOS-TERRAFORM-FOUNDATION-REFERENCE-PLAN-001",
            "version": "1.2.0",
            "story_id": "ST-1501",
        },
        "predecessor_plan.identity",
    )
    canonical_plan = (
        json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if plan_path.read_bytes() != canonical_plan:
        _fail("PREDECESSOR_GENERATED_DRIFT", "predecessor_plan")

    lock_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"),
        "predecessor_toolchain_lock",
    )
    lock = _mapping(load_json(lock_path), "predecessor_toolchain_lock")
    if semantic_sha256(lock) != EXPECTED_PREDECESSOR_TOOLCHAIN_SEMANTIC_SHA256:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor_toolchain_lock")
    lock_toolchain = _mapping(lock.get("toolchain"), "predecessor_toolchain_lock")
    _strict_match(
        lock_toolchain.get("version"), TERRAFORM_VERSION, "predecessor_toolchain_lock"
    )
    _strict_match(
        _mapping(
            lock_toolchain.get("official_release"), "predecessor_toolchain_lock"
        ).get("extracted_binary_sha256"),
        TERRAFORM_BINARY_SHA256,
        "predecessor_toolchain_lock",
    )
    canonical_lock = (
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    if lock_path.read_bytes() != canonical_lock:
        _fail("PREDECESSOR_GENERATED_DRIFT", "predecessor_toolchain_lock")


def _validate_capability_inventory(contract: Mapping[str, Any]) -> None:
    admission = _mapping(
        contract["provider_neutral_data_services_admission"],
        "provider_neutral_data_services_admission",
    )
    rows = _list(
        admission["capability_mapping_requirements"],
        "provider_neutral_data_services_admission.capability_mapping_requirements",
    )
    observed: list[str] = []
    for row in rows:
        item = _mapping(
            row,
            "provider_neutral_data_services_admission.capability_mapping_requirements.item",
        )
        capability_id = item.get("capability_id")
        if type(capability_id) is not str:
            _fail("TYPE_MISMATCH", "capability_mapping.capability_id")
        observed.append(capability_id)
    expected = [
        capability_id
        for capability_id, _required_outcome in DATA_SERVICE_CAPABILITY_OUTCOMES
    ]
    if len(observed) != len(set(observed)):
        _fail("DUPLICATE_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in expected for capability_id in observed):
        _fail("UNKNOWN_CAPABILITY_MAPPING", "capability_mapping")
    if any(capability_id not in observed for capability_id in expected):
        _fail("MISSING_CAPABILITY_MAPPING", "capability_mapping")
    if observed != expected:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "capability_mapping")


def validate_contract(contract: object, root: Path = REPO_ROOT) -> DataServicesModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    _validate_capability_inventory(value)
    for section, expected in EXPECTED_SECTIONS.items():
        _strict_match(value[section], expected, section)
    return DataServicesModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> DataServicesModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: DataServicesModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: DataServicesModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-DATA-SERVICES-REFERENCE-PLAN-001",
            "version": "1.2.0",
            "story_id": "ST-1502",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": True,
            "implementation_scope": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "execution_kind": "PROVIDER_FREE_VALIDATION_ONLY_LOGICAL_HCL",
        },
        "predecessor_binding": _section(model, "predecessor_binding"),
        "reference_architecture": _section(model, "reference_architecture"),
        "provider_neutral_data_services_admission": _section(
            model, "provider_neutral_data_services_admission"
        ),
        "logical_hcl_module": _section(model, "logical_hcl_module"),
        "successor_activation_port": _section(model, "successor_activation_port"),
        "selected_configuration": _section(model, "selected_configuration"),
        "logical_data_services": {
            "relational_persistence": _section(model, "relational_persistence_intent"),
            "object_storage": _section(model, "object_storage_intent"),
            "queue": _section(model, "queue_intent"),
            "secrets": _section(model, "secrets_intent"),
            "key_management": _section(model, "key_management_intent"),
            "recovery": _section(model, "recovery_intent"),
            "observability": _section(model, "observability_intent"),
            "data_boundary": _section(model, "data_boundary_intent"),
        },
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "migration_action": execution["migration_action"],
            "backup_action": execution["backup_action"],
            "restore_action": execution["restore_action"],
            "redrive_action": execution["redrive_action"],
            "destructive_action": execution["destructive_action"],
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


def render_reference_plan(model: DataServicesModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def logical_plan_document(model: DataServicesModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    return {
        "document": {
            "id": "RAOS-DATA-SERVICES-LOGICAL-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-1502",
            "classification": "DETERMINISTIC_NO_APPLY_LOGICAL_RESOURCE_GRAPH",
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
        "nodes": logical_resource_nodes(),
        "edges": logical_resource_edges(),
        "iam_permissions": {
            role_id: list(permissions)
            for role_id, permissions in IAM_PERMISSIONS.items()
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
            "nodes",
            "edges",
            "iam_permissions",
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
    nodes = [
        _mapping(row, "logical_plan.node") for row in _list(plan["nodes"], "nodes")
    ]
    expected_nodes = logical_resource_nodes()
    node_ids = [node.get("node_id") for node in nodes]
    expected_ids = [node["node_id"] for node in expected_nodes]
    if node_ids != expected_ids or len(node_ids) != len(set(node_ids)):
        _fail("LOGICAL_PLAN_NODE_INVENTORY_DRIFT", "logical_plan")
    for node in nodes:
        if node.get("public_access") is not False:
            _fail("LOGICAL_PLAN_PUBLIC_EXPOSURE", "logical_plan")
        if (
            node.get("persisted_data") is True
            and node.get("encryption_at_rest") is not True
        ):
            _fail("LOGICAL_PLAN_ENCRYPTION_DISABLED", "logical_plan")
        if (
            node.get("network_interaction") is True
            and node.get("transport_encryption") is not True
        ):
            _fail("LOGICAL_PLAN_TRANSPORT_ENCRYPTION_DISABLED", "logical_plan")
        if (
            node.get("backup_required") is True
            and node.get("backup_declared") is not True
        ):
            _fail("LOGICAL_PLAN_BACKUP_MISSING", "logical_plan")
        if (
            node.get("immutable_required") is True
            and node.get("immutable_declared") is not True
        ):
            _fail("LOGICAL_PLAN_IMMUTABILITY_MISSING", "logical_plan")
        if node.get("dlq_required") is True and node.get("dlq_declared") is not True:
            _fail("LOGICAL_PLAN_DLQ_MISSING", "logical_plan")
        if node.get("contains_secret_material") is not False:
            _fail("LOGICAL_PLAN_SECRET_MATERIAL_FORBIDDEN", "logical_plan")
        if (
            node.get("least_privilege") is not True
            or node.get("wildcard_iam") is not False
        ):
            _fail("LOGICAL_PLAN_WILDCARD_IAM", "logical_plan")
        if (
            node.get("key_rotation_required") is True
            and node.get("key_rotation_declared") is not True
        ):
            _fail("LOGICAL_PLAN_KEY_ROTATION_MISSING", "logical_plan")
    edges = [
        _mapping(row, "logical_plan.edge") for row in _list(plan["edges"], "edges")
    ]
    edge_triples = {
        (edge.get("from"), edge.get("to"), edge.get("relationship")) for edge in edges
    }
    for primary, dlq in zip(PRIMARY_QUEUE_NODE_IDS, DLQ_NODE_IDS, strict=True):
        if (primary, dlq, "REDRIVES_TO") not in edge_triples:
            _fail("LOGICAL_PLAN_DLQ_MISSING", "logical_plan")
    _strict_match(edges, logical_resource_edges(), "logical_plan.edges")
    permissions = _mapping(plan["iam_permissions"], "logical_plan.iam_permissions")
    _exact_keys(permissions, set(IAM_PERMISSIONS), "logical_plan.iam_permissions")
    for role_id, expected_permissions in IAM_PERMISSIONS.items():
        actual = _list(permissions[role_id], "logical_plan.iam_permissions")
        if any(
            type(permission) is not str
            or permission == "*"
            or permission.endswith(":*")
            or permission.endswith(".*")
            for permission in actual
        ):
            _fail("LOGICAL_PLAN_WILDCARD_IAM", "logical_plan")
        if actual != list(expected_permissions):
            _fail("LOGICAL_PLAN_IAM_POLICY_DRIFT", "logical_plan")
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
    expected = logical_plan_document(DataServicesModel(contract=expected_contract))
    if dict(plan) != expected:
        _fail("LOGICAL_PLAN_SEMANTIC_DRIFT", "logical_plan")


def render_logical_plan(model: DataServicesModel) -> bytes:
    document = logical_plan_document(model)
    validate_logical_plan_document(document)
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def render_toolchain_lock(model: DataServicesModel, root: Path) -> bytes:
    predecessor_path = _repository_regular_file(
        root,
        Path("infra/terraform/foundation/terraform-validation-toolchain.lock.v1.json"),
        "predecessor_toolchain_lock",
    )
    predecessor = _mapping(load_json(predecessor_path), "predecessor_toolchain_lock")
    document = {
        "document": {
            "id": "RAOS-DATA-SERVICES-TERRAFORM-VALIDATION-LOCK-001",
            "version": "1.0.0",
            "story_id": "ST-1502",
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
            "logical_resource_node_count": len(logical_resource_nodes()),
        },
        "authority_boundary": {
            "activation": "DISABLED",
            "provider_selection": "FORBIDDEN",
            "account_or_project_selection": "FORBIDDEN",
            "region_selection": "FORBIDDEN",
            "backend_selection": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "network_during_normal_checks": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "infrastructure_actions": "FORBIDDEN",
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
        },
    }
    return (
        json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def _hcl_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _render_hcl_node(node: Mapping[str, object]) -> str:
    lines = [f"    {node['node_id']} = {{"]
    keys = (
        "kind",
        "reference_service",
        "persisted_data",
        "network_interaction",
        "public_access",
        "encryption_at_rest",
        "transport_encryption",
        "backup_required",
        "backup_declared",
        "immutable_required",
        "immutable_declared",
        "dlq_required",
        "dlq_declared",
        "contains_secret_material",
        "key_rotation_required",
        "key_rotation_declared",
        "least_privilege",
        "wildcard_iam",
    )
    width = max(len(key) for key in keys)
    for key in keys:
        value = node[key]
        rendered = _hcl_string(value) if type(value) is str else str(value).lower()
        lines.append(f"      {key:<{width}} = {rendered}")
    lines.append("    }")
    return "\n".join(lines)


def render_hcl_bundle(model: DataServicesModel) -> dict[Path, bytes]:
    del model
    header = (
        "# Generated by repo://scripts/build_st1502_data_services.py; do not edit.\n"
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
        (
            "selected_primary_region",
            "string",
            "null",
            "var.selected_primary_region == null",
        ),
        (
            "selected_backup_region",
            "string",
            "null",
            "var.selected_backup_region == null",
        ),
        (
            "selected_state_backend",
            "string",
            "null",
            "var.selected_state_backend == null",
        ),
        ("credential_source", "string", "null", "var.credential_source == null"),
        (
            "network_segment_ids",
            "list(string)",
            "[]",
            "length(var.network_segment_ids) == 0",
        ),
        (
            "security_policy_bindings",
            "list(string)",
            "[]",
            "length(var.security_policy_bindings) == 0",
        ),
        (
            "selected_retention_policy_id",
            "string",
            "null",
            "var.selected_retention_policy_id == null",
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
  description = "Current ST-1502 revision keeps this successor binding unset."
  type        = {type_name}
  default     = {default}{nullable}

  validation {{
    condition     = {condition}
    error_message = "Physical activation requires a successor contract and external evidence."
  }}
}}
'''
        )
    variables = header + "\n".join(variable_blocks)
    node_text = "\n".join(_render_hcl_node(node) for node in logical_resource_nodes())
    edge_text = "\n".join(
        "    { from = %s, to = %s, relationship = %s },"
        % (
            _hcl_string(edge["from"]),
            _hcl_string(edge["to"]),
            _hcl_string(edge["relationship"]),
        )
        for edge in logical_resource_edges()
    )
    permission_width = max(len(role_id) for role_id in IAM_PERMISSIONS)
    permission_text = "\n".join(
        f"    {role_id:<{permission_width}} = toset([{', '.join(_hcl_string(permission) for permission in permissions)}])"
        for role_id, permissions in IAM_PERMISSIONS.items()
    )
    required_evidence_text = ",\n      ".join(
        _hcl_string(value) for value in SUCCESSOR_GATE_EVIDENCE
    )
    locals_content = (
        header
        + f"""locals {{
  reference_architecture = {{
    cloud               = "AWS"
    region              = "ap-northeast-1"
    classification      = "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
    selected_binding    = false
    evidence_substitute = false
  }}

  logical_resources = {{
{node_text}
  }}

  logical_edges = [
{edge_text}
  ]

  iam_permissions = {{
{permission_text}
  }}

  selected_configuration = {{
    provider_schema          = var.selected_provider_schema
    provider_plugin          = var.selected_provider_plugin
    account_or_project       = var.selected_account_or_project
    primary_region           = var.selected_primary_region
    backup_region            = var.selected_backup_region
    state_backend            = var.selected_state_backend
    credential_source        = var.credential_source
    network_segments         = var.network_segment_ids
    security_policy_bindings = var.security_policy_bindings
    retention_policy_id      = var.selected_retention_policy_id
  }}

  successor_activation_port = {{
    classification                       = "CLOSED_PHYSICAL_RESOURCE_ACTIVATION_PORT"
    current_revision_activation          = "FORBIDDEN"
    successor_contract_revision_required = true
    required_gate_evidence = toset([
      {required_evidence_text}
    ])
    supplied_gate_evidence   = var.supplied_gate_evidence
    complete_gate_evidence   = false
    provider_binding         = "FORBIDDEN_IN_CURRENT_REVISION"
    resource_materialization = "FORBIDDEN_IN_CURRENT_REVISION"
    infrastructure_plan      = "FORBIDDEN"
    infrastructure_apply     = "FORBIDDEN"
  }}

  execution_boundary = {{
    activation_enabled          = var.activation_enabled
    production_apply_authorized = var.production_apply_authorized
    provider_calls              = "FORBIDDEN"
    external_writes             = "FORBIDDEN"
    planned_actions = {{
      create  = 0
      update  = 0
      delete  = 0
      migrate = 0
      backup  = 0
      restore = 0
      redrive = 0
      rotate  = 0
    }}
  }}
}}
"""
    )
    checks = (
        header
        + f"""check "execution_is_disabled" {{
  assert {{
    condition     = var.activation_enabled == false && var.production_apply_authorized == false
    error_message = "Activation and Production apply authority must remain disabled."
  }}
}}

check "bindings_and_gate_evidence_are_unset" {{
  assert {{
    condition = alltrue([
      var.selected_provider_schema == null,
      var.selected_provider_plugin == null,
      var.selected_account_or_project == null,
      var.selected_primary_region == null,
      var.selected_backup_region == null,
      var.selected_state_backend == null,
      var.credential_source == null,
      length(var.network_segment_ids) == 0,
      length(var.security_policy_bindings) == 0,
      var.selected_retention_policy_id == null,
      length(var.supplied_gate_evidence) == 0,
    ])
    error_message = "Provider, account, region, backend, credential, network, policy, retention, and evidence bindings remain unset."
  }}
}}

check "private_and_encrypted_data_services" {{
  assert {{
    condition = alltrue([
      for node in values(local.logical_resources) :
      node.public_access == false &&
      (node.persisted_data == false || node.encryption_at_rest == true) &&
      (node.network_interaction == false || node.transport_encryption == true)
    ])
    error_message = "Every persisted or interacting data service must remain private and encrypted."
  }}
}}

check "backup_and_immutability_declarations" {{
  assert {{
    condition = alltrue([
      for node in values(local.logical_resources) :
      (node.backup_required == false || node.backup_declared == true) &&
      (node.immutable_required == false || node.immutable_declared == true)
    ])
    error_message = "Required backup, PITR, version, and immutability declarations cannot be omitted."
  }}
}}

check "primary_queues_have_dlqs" {{
  assert {{
    condition = alltrue([
      for node_id in {json.dumps(list(PRIMARY_QUEUE_NODE_IDS))} :
      local.logical_resources[node_id].dlq_required == true &&
      local.logical_resources[node_id].dlq_declared == true &&
      length([for edge in local.logical_edges : edge if edge.from == node_id && edge.relationship == "REDRIVES_TO"]) == 1
    ])
    error_message = "Every primary queue requires exactly one declared DLQ relationship."
  }}
}}

check "secrets_and_keys_are_material_free_and_rotatable" {{
  assert {{
    condition = alltrue([
      for node in values(local.logical_resources) :
      node.contains_secret_material == false &&
      (node.key_rotation_required == false || node.key_rotation_declared == true)
    ])
    error_message = "Generated configuration cannot contain secret material or an unrotatable required key."
  }}
}}

check "iam_is_least_privilege_and_wildcard_free" {{
  assert {{
    condition = alltrue([
      for node in values(local.logical_resources) : node.least_privilege == true && node.wildcard_iam == false
      ]) && alltrue(flatten([
        for permissions in values(local.iam_permissions) : [
          for permission in permissions : permission != "*" && !endswith(permission, ":*") && !endswith(permission, ".*")
        ]
    ]))
    error_message = "Logical IAM permission sets must remain explicit and wildcard-free."
  }}
}}

check "logical_plan_has_zero_actions" {{
  assert {{
    condition = length(local.logical_resources) == {len(logical_resource_nodes())} && alltrue([
      for count in values(local.execution_boundary.planned_actions) : count == 0
    ]) && local.successor_activation_port.complete_gate_evidence == false
    error_message = "The logical graph cannot plan or authorize physical infrastructure actions."
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

output "logical_resources" {
  description = "Provider-schema-free logical resource declarations."
  value       = local.logical_resources
}

output "logical_edges" {
  description = "Deterministic dependency, recovery, redrive, encryption, and authorization edges."
  value       = local.logical_edges
}

output "iam_permissions" {
  description = "Wildcard-free logical permission sets."
  value       = local.iam_permissions
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
    bundle = {
        HCL_PATHS[0]: versions.encode("utf-8"),
        HCL_PATHS[1]: variables.encode("utf-8"),
        HCL_PATHS[2]: locals_content.encode("utf-8"),
        HCL_PATHS[3]: checks.encode("utf-8"),
        HCL_PATHS[4]: outputs.encode("utf-8"),
    }
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
        required_counts = {
            ("public_access", "false"): len(logical_resource_nodes()),
            ("wildcard_iam", "false"): len(logical_resource_nodes()),
            ("contains_secret_material", "false"): len(logical_resource_nodes()),
            ("backup_required", "true"): 7,
            ("backup_declared", "true"): 7,
            ("dlq_required", "true"): len(PRIMARY_QUEUE_NODE_IDS),
            ("dlq_declared", "true"): len(PRIMARY_QUEUE_NODE_IDS),
            ("key_rotation_required", "true"): len(KMS_NODE_IDS),
            ("key_rotation_declared", "true"): len(KMS_NODE_IDS),
            ("encryption_at_rest", "true"): sum(
                node["persisted_data"] is True for node in logical_resource_nodes()
            ),
            ("transport_encryption", "true"): sum(
                node["network_interaction"] is True for node in logical_resource_nodes()
            ),
        }
        if any(
            len(re.findall(rf"(?m)^\s+{field}\s+=\s+{value}$", text)) != count
            for (field, value), count in required_counts.items()
        ):
            _fail("HCL_SAFETY_DECLARATION_DRIFT", "hcl")
        if '"*"' in text or '":*"' in text or '".*"' in text:
            _fail("HCL_WILDCARD_IAM", "hcl")


def validate_hcl_bundle(bundle: Mapping[Path, bytes]) -> None:
    if set(bundle) != set(HCL_PATHS):
        _fail("HCL_FILE_INVENTORY_DRIFT", "hcl")
    for relative in HCL_PATHS:
        validate_hcl_file_policy(relative, bundle[relative])


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _repository_regular_file(root, relative, "source_artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: DataServicesModel,
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
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-DATA-SERVICES-MANIFEST-001",
            "version": "1.2.0",
            "story_id": "ST-1502",
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
        "generated_artifact_count": len(GENERATED_ARTIFACT_PATHS),
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
            "activation": execution["activation_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "migration_action": execution["migration_action"],
            "backup_action": execution["backup_action"],
            "restore_action": execution["restore_action"],
            "redrive_action": execution["redrive_action"],
            "destructive_action": execution["destructive_action"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "admission_status": model.contract[
                "provider_neutral_data_services_admission"
            ]["admission_status"],
            "eligible": model.contract["provider_neutral_data_services_admission"][
                "eligible"
            ],
            "planned_actions": copy.deepcopy(execution["planned_actions"]),
            "selected_provider_profile": model.contract[
                "provider_neutral_data_services_admission"
            ]["selected_profile_id"],
            "default_provider_profile": model.contract[
                "provider_neutral_data_services_admission"
            ]["default_profile_id"],
            "fallback_provider_profile": model.contract[
                "provider_neutral_data_services_admission"
            ]["fallback_profile_id"],
            "selected_provider_name": selection["provider_name"],
            "selected_provider_account_or_project": selection[
                "provider_account_or_project"
            ],
            "selected_production_region": selection["production_region"],
            "selected_backup_region": selection["backup_region"],
            "selected_relational_service_binding": selection[
                "relational_service_binding"
            ],
            "selected_object_storage_service_binding": selection[
                "object_storage_service_binding"
            ],
            "selected_queue_service_binding": selection["queue_service_binding"],
            "selected_secrets_service_binding": selection["secrets_service_binding"],
            "selected_key_management_service_binding": selection[
                "key_management_service_binding"
            ],
            "selected_data_services_plugin_or_adapter": selection[
                "data_services_plugin_or_adapter"
            ],
            "required_capability_count": len(DATA_SERVICE_CAPABILITY_OUTCOMES),
            "configured_mapping_count": 0,
            "complete_mapping": False,
            "aws_reference_role": model.contract[
                "provider_neutral_data_services_admission"
            ]["aws_reference_boundary"]["role"],
            "canonical_story_deliverables": model.contract[
                "provider_neutral_data_services_admission"
            ]["aws_reference_boundary"]["canonical_story_deliverables"],
            "portable_implementation_paths": model.contract[
                "provider_neutral_data_services_admission"
            ]["aws_reference_boundary"]["non_aws_owner_managed_profiles"],
            "aws_reference_default": False,
            "aws_reference_implicit_fallback": False,
            "aws_reference_selected_binding": False,
            "aws_reference_eligibility_shortcut": False,
            "aws_reference_admission_requirement": False,
            "aws_reference_evidence_substitute": False,
            "credentials": evidence["credentials"],
            "physical_resource_definitions": copy.deepcopy(
                selection["physical_resource_definitions"]
            ),
            "hcl_module": "PROVIDER_SCHEMA_FREE_VALIDATION_ONLY_LOGICAL_GRAPH",
            "hcl_file_count": len(HCL_PATHS),
            "logical_resource_node_count": len(logical_resource_nodes()),
            "logical_edge_count": len(logical_resource_edges()),
            "logical_iam_role_count": len(IAM_ROLE_IDS),
            "terraform_cli_version": TERRAFORM_VERSION,
            "terraform_binary_sha256": TERRAFORM_BINARY_SHA256,
            "provider_schema": None,
            "provider_plugins": [],
            "backend": None,
            "physical_resources": [],
            "offline_native_validation_path": evidence[
                "offline_native_validation_path"
            ],
            "local_native_validation": evidence["local_native_validation"],
            "logical_plan_validation": evidence["logical_plan_validation"],
            "transport_encryption_validation": evidence[
                "transport_encryption_validation"
            ],
            "relational_migration_validation": evidence[
                "relational_migration_validation"
            ],
            "queue_delivery_validation": evidence["queue_delivery_validation"],
            "formal_tst_026": evidence["formal_tst_026"],
            "formal_tst_029": evidence["formal_tst_029"],
            "restore_validation": evidence["restore_validation"],
            "provider_validation": evidence["provider_validation"],
            "live_staging_release_production": evidence[
                "live_staging_release_production"
            ],
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
    with tempfile.TemporaryDirectory(prefix="raos-st1502-native-") as directory:
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
        description="Build and validate the disabled ST-1502 logical HCL module."
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
    except DataServicesContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.native_check:
        print("ST-1502 native HCL validation passed")
    elif args.check:
        print("ST-1502 data-services check passed")
    else:
        print("ST-1502 data-services artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
