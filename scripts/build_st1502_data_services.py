#!/usr/bin/env python3
"""Build the disabled, non-executable ST-1502 data-services artifacts."""

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
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1502/contracts/data-services-foundation.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/data-services/data-services.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1502/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1502_data_services.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1502_data_services.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"

AUTHORITY_SOURCES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
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
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-1501/contracts/terraform-foundation.v1.yaml": (
        "3907d814f3be891d7652a77e8478428ede79d9dc9cfbd48f871962150ef459d2"
    ),
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json": (
        "877248753e5498c6fdc94e6700c2ac64fc5f12aabce61abfd19e8cfb7d7c8e2f"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-1502/README.md"),
    Path("scripts/build_st1502_data_services.py"),
    Path("tests/st1502/conftest.py"),
    Path("tests/st1502/test_contract.py"),
    Path("tests/st1502/test_generation.py"),
    Path("tests/st1502/test_negative_cases.py"),
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
NATIVE_COMMANDS: Final = ("init", "plan", "apply", "destroy", "import", "refresh")
ACTION_NAMES: Final = ("create", "update", "delete")
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _queue_selection() -> dict[str, object]:
    return {
        "physical_name": None,
        "queue_url": None,
        "queue_arn": None,
        "dlq_name": None,
        "dlq_url": None,
        "dlq_arn": None,
        "delay_seconds": None,
        "visibility_timeout_seconds": None,
        "retention_seconds": None,
        "max_receive_count": None,
        "fifo": None,
        "policy_document": None,
    }


def _queue_intent(queue_class: str) -> dict[str, object]:
    return {
        "class": queue_class,
        "dlq": "REQUIRED_NOT_CONFIGURED",
        "producer_consumer_separation": "REQUIRED_NOT_CONFIGURED",
        "redrive_role_separation": "REQUIRED_NOT_CONFIGURED",
        "selected": _queue_selection(),
    }


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-DATA-SERVICES-FOUNDATION-001",
        "version": "1.0.0",
        "story_id": "ST-1502",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_binding": {
        "story_id": "ST-1501",
        "extension_kind": "DATA_SERVICES",
        "contract_uri": (
            "repo://changes/st-1501/contracts/terraform-foundation.v1.yaml"
        ),
        "contract_sha256": PREDECESSOR_SOURCES[
            "changes/st-1501/contracts/terraform-foundation.v1.yaml"
        ],
        "reference_plan_uri": (
            "repo://infra/terraform/foundation/"
            "terraform-foundation.reference-plan.v1.json"
        ),
        "reference_plan_sha256": PREDECESSOR_SOURCES[
            "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
        ],
        "required_activation_status": "DISABLED",
        "required_resource_payloads": "FORBIDDEN",
        "required_planned_actions": {"create": 0, "update": 0, "delete": 0},
    },
    "reference_architecture": {
        "cloud": "AWS",
        "region": "ap-northeast-1",
        "classification": "INHERITED_REFERENCE_METADATA_ONLY",
        "portable_core_required": True,
    },
    "selected_configuration": {
        "cloud_provider": None,
        "production_region": None,
        "backup_region": None,
        "aws_account_id": None,
        "terraform_cli_version": None,
        "provider_plugins": [],
        "state_backend": None,
        "credential_source": None,
        "network_cidrs": [],
        "availability_zones": [],
        "subnet_ids": [],
        "security_group_ids": [],
        "physical_resource_definitions": [],
    },
    "rds_intent": {
        "service": "PostgreSQL",
        "classification": "LOGICAL_SERVICE_INTENT_ONLY",
        "private_only": "REQUIRED",
        "publicly_accessible": False,
        "encryption_at_rest": "REQUIRED_NOT_CONFIGURED",
        "backup": "REQUIRED_NOT_CONFIGURED",
        "point_in_time_recovery": "REQUIRED_NOT_CONFIGURED",
        "deletion_protection": "REQUIRED_NOT_CONFIGURED",
        "final_snapshot": "REQUIRED_NOT_CONFIGURED",
        "restore_test": "REQUIRED_NOT_EXECUTED",
        "selected": {
            "engine_version": None,
            "instance_class": None,
            "storage_gib": None,
            "storage_class": None,
            "subnet_ids": [],
            "endpoint": None,
            "database_name": None,
            "username": None,
            "password_secret_reference": None,
            "port": None,
            "multi_az": None,
            "backup_retention_days": None,
            "backup_region": None,
            "kms_key_reference": None,
        },
    },
    "s3_intent": {
        "classification": "LOGICAL_BUCKET_ROLE_INTENT_ONLY",
        "public_access_block": "REQUIRED",
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
                "arn": None,
                "immutability": "REQUIRED_NOT_CONFIGURED",
                "integrity_metadata": "REQUIRED_NOT_CONFIGURED",
                "deletion_role_separation": "REQUIRED_NOT_CONFIGURED",
            },
            *[
                {"role": role, "physical_name": None, "arn": None}
                for role in BUCKET_ROLES[1:]
            ],
        ],
    },
    "sqs_intent": {
        "classification": "LOGICAL_QUEUE_CLASS_INTENT_ONLY",
        "classes": [_queue_intent(queue_class) for queue_class in QUEUE_CLASSES],
    },
    "secrets_manager_intent": {
        "classification": "METADATA_INTENT_ONLY",
        "secret_values": "ABSENT",
        "secret_names": [],
        "secret_arns": [],
        "ambient_credential_resolution": "FORBIDDEN",
        "environment_credential_resolution": "FORBIDDEN",
        "rotation": "REQUIRED_NOT_CONFIGURED",
        "workload_least_privilege": "REQUIRED_NOT_CONFIGURED",
    },
    "kms_intent": {
        "classification": "LOGICAL_ENCRYPTION_INTENT_ONLY",
        "encryption": "REQUIRED",
        "rotation": "REQUIRED_NOT_CONFIGURED",
        "audit_logging": "REQUIRED_NOT_CONFIGURED",
        "workload_least_privilege": "REQUIRED_NOT_CONFIGURED",
        "key_deletion": "FORBIDDEN",
        "key_ids": [],
        "key_arns": [],
        "aliases": [],
        "policy_document": None,
        "deletion_window_days": None,
    },
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "commands": {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
        "planned_actions": {action: 0 for action in ACTION_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_DATA_SERVICES_REFERENCE_PLAN"
        ),
        "executable_terraform": "ABSENT",
        "terraform_cli": "UNPINNED_NOT_INVOKED",
        "provider_plugins": "UNPINNED_NOT_INVOKED",
        "aws_account": "UNSET",
        "credentials": "ABSENT",
        "native_iac_validation": "NOT_EXECUTED",
        "formal_tst_026": "NOT_EXECUTED",
        "formal_tst_029": "NOT_EXECUTED",
        "restore_validation": "NOT_EXECUTED",
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
class DataServicesModel:
    """A fully validated, closed ST-1502 contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _fail(code: str, field: str) -> NoReturn:
    raise DataServicesContractError(code, field)


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


def _exact_keys(value: Mapping[str, Any], expected: set[str], field: str) -> None:
    if set(value) != expected:
        _fail("CLOSED_SCHEMA_VIOLATION", field)


def _strict_match(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        value = _mapping(actual, field)
        expected_mapping = _mapping(expected, field)
        _exact_keys(value, set(expected_mapping), field)
        for key, expected_value in expected_mapping.items():
            _strict_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(expected, field)
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
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
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


def _validate_predecessor_semantics(root: Path) -> None:
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
            "version": "1.0.0",
            "story_id": "ST-1501",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.document",
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
    _strict_match(execution.get("activation_enabled"), False, "predecessor.activation")
    _strict_match(
        execution.get("activation_status"), "DISABLED", "predecessor.activation"
    )
    _strict_match(
        execution.get("live_provider_calls"), "FORBIDDEN", "predecessor.execution"
    )
    _strict_match(
        execution.get("external_writes"), "FORBIDDEN", "predecessor.execution"
    )
    _strict_match(
        execution.get("commands"),
        {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
        "predecessor.commands",
    )
    _strict_match(
        execution.get("planned_actions"),
        {action: 0 for action in ACTION_NAMES},
        "predecessor.planned_actions",
    )
    extension = _mapping(contract.get("extension_contract"), "predecessor.extension")
    _strict_match(
        extension.get("current_resource_payloads"),
        "FORBIDDEN",
        "predecessor.resources",
    )
    successors = _mapping(extension.get("successors"), "predecessor.successors")
    _strict_match(successors.get("ST-1502"), "DATA_SERVICES", "predecessor.ST-1502")

    plan = _mapping(
        load_json(
            _repository_regular_file(
                root,
                Path(
                    "infra/terraform/foundation/"
                    "terraform-foundation.reference-plan.v1.json"
                ),
                "predecessor_plan",
            )
        ),
        "predecessor_plan",
    )
    plan_document = _mapping(plan.get("document"), "predecessor_plan.document")
    _strict_match(
        plan_document.get("artifact_kind"),
        "SOURCE_DERIVED_REFERENCE_STATE_PLAN",
        "predecessor_plan.artifact_kind",
    )
    _strict_match(plan_document.get("executable"), False, "predecessor_plan.executable")
    activation = _mapping(plan.get("activation"), "predecessor_plan.activation")
    _strict_match(activation.get("enabled"), False, "predecessor_plan.activation")
    _strict_match(activation.get("status"), "DISABLED", "predecessor_plan.activation")
    _strict_match(
        activation.get("native_commands"),
        {command: "FORBIDDEN" for command in NATIVE_COMMANDS},
        "predecessor_plan.commands",
    )
    _strict_match(
        plan.get("planned_actions"),
        {action: 0 for action in ACTION_NAMES},
        "predecessor_plan.planned_actions",
    )
    _strict_match(
        plan.get("selected_configuration"),
        contract.get("selected_configuration"),
        "predecessor_plan.selected_configuration",
    )


def validate_contract(contract: object, root: Path = REPO_ROOT) -> DataServicesModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
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
            "version": "1.0.0",
            "story_id": "ST-1502",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_binding": _section(model, "predecessor_binding"),
        "reference_architecture": _section(model, "reference_architecture"),
        "selected_configuration": _section(model, "selected_configuration"),
        "logical_data_services": {
            "rds": _section(model, "rds_intent"),
            "s3": _section(model, "s3_intent"),
            "sqs": _section(model, "sqs_intent"),
            "secrets_manager": _section(model, "secrets_manager_intent"),
            "kms": _section(model, "kms_intent"),
        },
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
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


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    path = _repository_regular_file(root, relative, "source_artifact")
    content = path.read_bytes()
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: DataServicesModel, reference_plan: bytes, root: Path = REPO_ROOT
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    selection = _mapping(model.contract["selected_configuration"], "selection")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-DATA-SERVICES-MANIFEST-001",
            "version": "1.0.0",
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
            "activation": execution["activation_status"],
            "planned_actions": copy.deepcopy(execution["planned_actions"]),
            "selected_cloud_provider": selection["cloud_provider"],
            "selected_production_region": selection["production_region"],
            "selected_aws_account": selection["aws_account_id"],
            "selected_state_backend": selection["state_backend"],
            "credentials": evidence["credentials"],
            "physical_resource_definitions": copy.deepcopy(
                selection["physical_resource_definitions"]
            ),
            "native_iac_validation": evidence["native_iac_validation"],
            "formal_tst_026": evidence["formal_tst_026"],
            "formal_tst_029": evidence["formal_tst_029"],
            "restore_validation": evidence["restore_validation"],
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
        description="Build the disabled ST-1502 data-services reference artifacts."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed generated bytes without writing",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except DataServicesContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1502 data-services check passed")
    else:
        print("ST-1502 data-services artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
