#!/usr/bin/env python3
"""Build the disabled, non-executable ST-1505 staging reference artifacts."""

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
CONTRACT_PATH: Final = Path("changes/st-1505/contracts/staging-deployment.v1.yaml")
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1505/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1505_staging_deployment.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1505_staging_deployment.py"
)

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
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml": (
        "59854810967b8fa1f0df759bf5160d128fc4dea00084a95f6b4f11876a415ab0"
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
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "ee54088ea4dc84888fbbfd44259f015e7a27ee18c9e9cdbeb1b074aca905d502"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "ae44e618b5ef8fa261c098f6b64852b69d8de996cf0bd33b726021783c4b9d41"
    ),
    "changes/st-1503/contracts/compute-edge-foundation.v1.yaml": (
        "54d60c741c7531b39f09fd90406bdd203985214086f092370b1ebb2ba79d13a3"
    ),
    "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json": (
        "551d11aefa10526054190770467067dd71751f7249d3ddcdd534c0c359f509ed"
    ),
    "changes/st-1504/contracts/github-oidc-deployment.v1.yaml": (
        "58352939268565ede5c6d48682013c3fac1134587d1665f4236f389f0c15527d"
    ),
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json": (
        "6774c1e2553df4e1f3e7a85dc122b2462ddb575503a7c03b4ec8d9e18baecfbc"
    ),
}
PINNED_SOURCES: Final = {**AUTHORITY_SOURCES, **PREDECESSOR_SOURCES}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-1505/README.md"),
    Path("scripts/build_st1505_staging_deployment.py"),
    Path("tests/st1505/conftest.py"),
    Path("tests/st1505/test_contract.py"),
    Path("tests/st1505/test_generation.py"),
    Path("tests/st1505/test_negative_cases.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1505",
    "epic_id": "EPIC-15",
    "title": "Staging deployment pipeline",
    "objective": "artifact promotion、migration、smoke、rollback",
    "depends_on": ["ST-1502", "ST-1503", "ST-1504"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["staging pipeline"],
    "acceptance_criteria": ["repeatable deployment"],
    "test_suites": ["TST-009", "TST-022"],
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
    "TST-009": {
        "id": "TST-009",
        "name": "Migration zero-to-latest",
        "layer": "database",
        "purpose": "空DBから最新版へ到達",
        "candidate_tools": ["migration runner", "PostgreSQL 18"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    "TST-022": {
        "id": "TST-022",
        "name": "Browser functional E2E",
        "layer": "ui",
        "purpose": "主要WorkflowとPublic view",
        "candidate_tools": ["Playwright"],
        "release_blocking": True,
        "environments": ["CI", "staging"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-IAM-010": "長期AWS keyをActions secretに置かない",
    "SEC-INFRA-001": "RDS/worker/object admin endpointをPublicにしない",
    "SEC-INFRA-002": "Public ingressを管理Pointへ限定",
    "SEC-SDLC-002": "Security、migration、contractsへowner review",
    "SEC-SDLC-004": "Dependency/container vulnerability scan",
    "SEC-SDLC-006": "History/PR/artifactをscan",
    "SEC-SDLC-007": "Release artifactのSBOM生成",
    "SEC-SDLC-008": "Build provenance/attestationを生成",
    "SEC-SDLC-010": "DDL/role/data migrationを独立review",
    "SEC-SDLC-011": "Critical/High未解決でRelease禁止",
}
EXPECTED_THREATS: Final = {
    "THR-007": "pin、SCA、SBOM、provenance",
    "THR-008": "OIDC trust condition、environment approval",
    "THR-019": "separate OpenAPI/role/readmodel、schema scan",
    "THR-020": "structured redacted logs、log tests",
}

PHASE_NAMES: Final = (
    "PREDECESSOR_GATE",
    "ARTIFACT_ADMISSION",
    "EXPAND_COMPATIBILITY_GATE",
    "ROLLBACK_READINESS_GATE",
    "ARTIFACT_PROMOTION",
    "STAGING_DEPLOYMENT",
    "MIGRATION_DRY_RUN_GATE",
    "MIGRATE",
    "STAGING_SMOKE_GATE",
    "BROWSER_E2E_GATE",
    "CONTRACT_DEFERRED",
)
PREDECESSOR_ACTION_NAMES: Final = ("create", "update", "delete")
ACTION_COUNT_NAMES: Final = (
    "create",
    "update",
    "delete",
    "promote",
    "deploy",
    "migrate",
    "smoke",
    "browser",
    "rollback",
    "production",
)
OPERATION_NAMES: Final = (
    "artifact_promote",
    "deploy",
    "migration_dry_run",
    "migrate",
    "smoke",
    "browser",
    "rollback",
    "production",
)
FOUNDATION_NATIVE_COMMANDS: Final = (
    "init",
    "plan",
    "apply",
    "destroy",
    "import",
    "refresh",
)
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _selected_bindings() -> dict[str, object]:
    return {
        "cloud_provider": None,
        "cloud_account_id": None,
        "cloud_region": None,
        "state_backend": None,
        "github_repository": None,
        "github_environment": None,
        "deployment_role": None,
        "credential_source": None,
        "provider_plugins": [],
        "external_action_references": [],
        "artifact_digest": None,
        "artifact_sbom_reference": None,
        "artifact_scan_reference": None,
        "artifact_provenance_reference": None,
        "release_id": None,
        "commit_sha": None,
        "contract_hash": None,
        "migration_version": None,
        "migration_task_reference": None,
        "domain_names": [],
        "public_url": None,
        "admin_url": None,
        "internal_url": None,
        "liveness_url": None,
        "readiness_url": None,
        "health_matcher": None,
        "browser_base_url": None,
        "browser_project": None,
        "rollback_artifact_digest": None,
        "rollback_configuration_version": None,
        "rollback_snapshot_id": None,
        "rollback_migration_version": None,
    }


def _predecessor_binding(
    story_id: str, contract_path: str, plan_path: str, *, oidc: bool = False
) -> dict[str, object]:
    binding: dict[str, object] = {
        "story_id": story_id,
        "contract_uri": f"repo://{contract_path}",
        "contract_sha256": PREDECESSOR_SOURCES[contract_path],
        "reference_plan_uri": f"repo://{plan_path}",
        "reference_plan_sha256": PREDECESSOR_SOURCES[plan_path],
        "required_contract_non_executable": True,
        "required_reference_plan_executable": False,
        "required_activation_status": "DISABLED",
        "required_live_provider_calls": "FORBIDDEN",
        "required_external_writes": "FORBIDDEN",
    }
    if oidc:
        binding["required_credential_issuance"] = "FORBIDDEN"
    binding["required_selected_values"] = "UNSET"
    binding["required_planned_actions"] = {
        action: 0 for action in PREDECESSOR_ACTION_NAMES
    }
    return binding


def _phase(name: str) -> dict[str, object]:
    return {
        "name": name,
        "status": "DISABLED",
        "execution_status": "NOT_EXECUTED",
        "external_action": "FORBIDDEN",
        "action_count": 0,
    }


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-STAGING-DEPLOYMENT-001",
        "version": "1.0.0",
        "story_id": "ST-1505",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_bindings": {
        "data_services": _predecessor_binding(
            "ST-1502",
            "changes/st-1502/contracts/data-services-foundation.v1.yaml",
            "infra/terraform/data-services/data-services.reference-plan.v1.json",
        ),
        "compute_edge": _predecessor_binding(
            "ST-1503",
            "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
            "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        ),
        "deployment_identity": _predecessor_binding(
            "ST-1504",
            "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
            "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
            oidc=True,
        ),
    },
    "environment_boundary": {
        "label": "STAGING",
        "classification": "INERT_CANONICAL_LABEL_ONLY",
        "configuration_status": "NOT_CONFIGURED",
        "runtime_status": "NOT_EXECUTED",
        "formal_verification_status": "NOT_EXECUTED",
        "allowed_data_classes": ["SYNTHETIC", "APPROVED_ANONYMIZED"],
        "production_data": "FORBIDDEN",
        "dedicated_credentials": "REQUIRED_NOT_CONFIGURED",
        "credential_material": "ABSENT",
        "external_access": "FORBIDDEN",
        "production_action": "FORBIDDEN",
    },
    "selected_bindings": _selected_bindings(),
    "artifact_admission_intent": {
        "classification": "IMMUTABLE_SUPPLY_CHAIN_REQUIREMENTS_ONLY",
        "immutable_digest": "REQUIRED_NOT_CONFIGURED",
        "sbom": "REQUIRED_NOT_CONFIGURED",
        "vulnerability_scan": "REQUIRED_NOT_CONFIGURED",
        "signed_provenance": "REQUIRED_NOT_CONFIGURED",
        "promote_without_rebuild": "REQUIRED_NOT_CONFIGURED",
        "mutable_artifact": "FORBIDDEN",
        "rebuild_between_environments": "FORBIDDEN",
        "unsigned_artifact": "FORBIDDEN",
        "unscanned_artifact": "FORBIDDEN",
    },
    "migration_intent": {
        "classification": "DECLARATIVE_COMPATIBILITY_REQUIREMENTS_ONLY",
        "strategy": "EXPAND_MIGRATE_CONTRACT",
        "expand": "REQUIRED_NOT_CONFIGURED",
        "migrate": "REQUIRED_NOT_CONFIGURED",
        "contract": "DEFERRED_TO_LATER_RELEASE",
        "migration_dry_run": "REQUIRED_NOT_CONFIGURED",
        "compatibility_gate": "REQUIRED_NOT_CONFIGURED",
        "lock_duration_measurement": "REQUIRED_NOT_CONFIGURED",
        "forward_fix": "REQUIRED_NOT_CONFIGURED",
        "destructive_contract_current_release": "FORBIDDEN",
        "contract_before_expand": "FORBIDDEN",
        "direct_ddl": "FORBIDDEN",
        "down_migration_primary_recovery": "FORBIDDEN",
        "external_api_during_migration": "FORBIDDEN",
    },
    "health_and_smoke_intent": {
        "classification": "DECLARATIVE_RUNTIME_GATES_ONLY",
        "liveness_check": "REQUIRED_NOT_CONFIGURED",
        "readiness_check": "REQUIRED_NOT_CONFIGURED",
        "dependency_check": "REQUIRED_NOT_CONFIGURED",
        "migration_compatibility_check": "REQUIRED_NOT_CONFIGURED",
        "public_admin_internal_isolation_check": "REQUIRED_NOT_CONFIGURED",
        "smoke_check": "REQUIRED_NOT_CONFIGURED",
        "browser_e2e": "REQUIRED_NOT_CONFIGURED",
        "infer_readiness_from_generic_http_200": "FORBIDDEN",
        "external_provider_probe": "FORBIDDEN",
    },
    "rollback_intent": {
        "classification": "DECLARATIVE_ROLLBACK_REQUIREMENTS_ONLY",
        "execution": "FORBIDDEN",
        "prior_immutable_artifact": "REQUIRED_NOT_CONFIGURED",
        "prior_configuration": "REQUIRED_NOT_CONFIGURED",
        "known_safe_snapshot": "REQUIRED_NOT_CONFIGURED",
        "migration_compatibility": "REQUIRED_NOT_CONFIGURED",
        "pitr_for_ordinary_application_error": "FORBIDDEN",
        "destructive_reversal": "FORBIDDEN",
    },
    "logical_phases": [_phase(name) for name in PHASE_NAMES],
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "runtime_status": "NOT_EXECUTED",
        "network_access": "FORBIDDEN",
        "credential_access": "FORBIDDEN",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "staging_action": "FORBIDDEN",
        "release_action": "FORBIDDEN",
        "production_action": "FORBIDDEN",
        "operations": {name: "FORBIDDEN" for name in OPERATION_NAMES},
        "action_counts": {name: 0 for name in ACTION_COUNT_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_STAGING_DEPLOYMENT_REFERENCE_PLAN"
        ),
        "executable_pipeline": "ABSENT",
        "workflow": "ABSENT",
        "terraform_or_cloud_runtime": "ABSENT",
        "migration_runtime": "ABSENT",
        "browser_runtime": "ABSENT",
        "credentials": "ABSENT",
        "formal_tst_009": "NOT_EXECUTED",
        "formal_tst_022": "NOT_EXECUTED",
        "migration_database": "NOT_EXECUTED",
        "http_smoke": "NOT_EXECUTED",
        "playwright": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "rollback": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}
TOP_LEVEL_KEYS: Final = {"sources", *EXPECTED_SECTIONS}


class StagingDeploymentContractError(RuntimeError):
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
class StagingDeploymentModel:
    """A fully validated, closed ST-1505 contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _fail(code: str, field: str) -> NoReturn:
    raise StagingDeploymentContractError(code, field)


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


def _assert_unset_tree(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, Mapping):
        mapping = _mapping(value, field)
        for key, nested in mapping.items():
            _assert_unset_tree(nested, f"{field}.{key}")
        return
    if type(value) is list:
        if value:
            _fail("PREDECESSOR_SELECTION_SET", field)
        return
    _fail("PREDECESSOR_SELECTION_SET", field)


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
    except StagingDeploymentContractError:
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
    except StagingDeploymentContractError:
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


def _load_repo_yaml(root: Path, relative: str, field: str) -> Mapping[str, Any]:
    return _mapping(
        load_yaml(_repository_regular_file(root, Path(relative), field)), field
    )


def _load_repo_json(root: Path, relative: str, field: str) -> Mapping[str, Any]:
    return _mapping(
        load_json(_repository_regular_file(root, Path(relative), field)), field
    )


def _require_text(root: Path, relative: str, snippets: tuple[str, ...]) -> None:
    path = _repository_regular_file(root, Path(relative), "authority_text")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeError:
        _fail("AUTHORITY_TEXT_UNAVAILABLE", "authority_text")
    if any(snippet not in text for snippet in snippets):
        _fail("AUTHORITY_SEMANTIC_DRIFT", "authority_text")


def _validate_authority_semantics(root: Path) -> None:
    backlog = _load_repo_yaml(
        root,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    story = _find_exact_record(backlog, "stories", "ST-1505", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1505")

    decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        decision = _find_exact_record(
            decisions, "items", decision_id, "open_decisions.items"
        )
        _strict_match(decision, expected, f"open_decisions.{decision_id}")

    test_catalog = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    for suite_id, expected in EXPECTED_TESTS.items():
        suite = _find_exact_record(
            test_catalog, "suites", suite_id, "test_catalog.suites"
        )
        _strict_match(suite, expected, f"test_catalog.{suite_id}")

    controls = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        "security_controls",
    )
    for control_id, requirement in EXPECTED_SECURITY_CONTROLS.items():
        control = _find_exact_record(
            controls, "controls", control_id, "security_controls.controls"
        )
        if (
            control.get("requirement") != requirement
            or control.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or control.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_CONTROL_DRIFT", control_id)

    threats = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml",
        "threat_register",
    )
    for threat_id, required_controls in EXPECTED_THREATS.items():
        threat = _find_exact_record(
            threats, "threats", threat_id, "threat_register.threats"
        )
        if (
            threat.get("controls") != required_controls
            or threat.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or threat.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_THREAT_DRIFT", threat_id)

    architecture = _load_repo_yaml(
        root,
        "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml",
        "architecture_catalog",
    )
    deployment = _mapping(architecture.get("deployment"), "deployment")
    _strict_match(
        deployment.get("environments"),
        {
            "local": {"data": "synthetic", "external": "mock_or_sandbox"},
            "ci": {"data": "ephemeral", "external": "fixture"},
            "dev": {"data": "synthetic", "external": "limited"},
            "staging": {
                "data": "sanitized_fixtures",
                "external": "sandbox_or_limited_read",
            },
            "production": {"data": "production", "external": "production"},
        },
        "deployment.environments",
    )
    _strict_match(
        deployment.get("migration"),
        "expand_migrate_contract",
        "deployment.migration",
    )
    _strict_match(
        deployment.get("infrastructure_as_code"), "Terraform", "deployment.iac"
    )
    _strict_match(
        deployment.get("production_data_in_nonprod"),
        False,
        "deployment.production_data",
    )
    aws = _mapping(deployment.get("aws_mapping"), "deployment.aws")
    _strict_match(aws.get("ci_cd"), "GitHub_Actions_OIDC", "deployment.ci_cd")

    _require_text(
        root,
        "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md",
        (
            "| staging | 本番相当検証 | Sanitized Fixture | Sandbox/限定本番Read |",
            "7. Deploy Staging",
            "8. Migration Dry Run",
            "Immutable Image Build",
            "Expand-Migrate-Contract",
            "破壊的変更は複数Release",
            "PITRは重大災害時に使用し、通常の内容誤りには使わない。",
        ),
    )
    _require_text(
        root,
        "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md",
        (
            "B --> S[Deploy Staging]",
            "S --> T[Runtime / Security / Migration / Smoke]",
            "Database changeはBackward-compatibleなExpandを先に出し",
            "Releaseごと: Contract/migration/security/evidence/rollback review",
        ),
    )
    _require_text(
        root,
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        (
            "Worker、CI、Migration、Projection、Public Webは異なるWorkload Identityを使う。",
            "ReleaseにSBOM、Build provenance、Commit SHA、Contract hash、Migration versionを含める。",
            "Raw Secret、Prompt本文、Source本文、個人情報をLogに出さない。",
        ),
    )
    _require_text(
        root,
        "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md",
        (
            "Production dataをCIへ持ち込まない。",
            "Migration zero-to-latest/upgrade失敗",
            "Browser/Accessibility/Security/Load Test",
        ),
    )
    _require_text(
        root,
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        (
            "Status: `OWNER_APPROVED_FOR_LOCAL_IMPLEMENTATION`",
            "`ST-1504`, `ST-1505`, `ST-1506`",
            "Open-Decision and infrastructure Stories remain disabled/synthetic",
        ),
    )


def _validate_disabled_execution(
    execution: Mapping[str, Any], *, command_field: str | None = None
) -> None:
    _strict_match(execution.get("activation_enabled"), False, "predecessor.enabled")
    _strict_match(execution.get("activation_status"), "DISABLED", "predecessor.status")
    _strict_match(
        execution.get("native_plan_status"),
        "NOT_EXECUTED",
        "predecessor.native_plan",
    )
    _strict_match(
        execution.get("live_provider_calls"),
        "FORBIDDEN",
        "predecessor.provider",
    )
    _strict_match(execution.get("external_writes"), "FORBIDDEN", "predecessor.writes")
    _strict_match(
        execution.get("planned_actions"),
        {action: 0 for action in PREDECESSOR_ACTION_NAMES},
        "predecessor.actions",
    )
    if command_field is not None:
        _strict_match(
            execution.get(command_field),
            {command: "FORBIDDEN" for command in FOUNDATION_NATIVE_COMMANDS},
            "predecessor.commands",
        )


def _validate_plan_activation(plan: Mapping[str, Any]) -> None:
    document = _mapping(plan.get("document"), "predecessor.plan.document")
    _strict_match(document.get("executable"), False, "predecessor.plan.executable")
    activation = _mapping(plan.get("activation"), "predecessor.plan.activation")
    _strict_match(activation.get("enabled"), False, "predecessor.plan.enabled")
    _strict_match(activation.get("status"), "DISABLED", "predecessor.plan.status")
    _strict_match(
        activation.get("native_plan_status"),
        "NOT_EXECUTED",
        "predecessor.plan.native_plan",
    )
    _strict_match(
        activation.get("live_provider_calls"),
        "FORBIDDEN",
        "predecessor.plan.provider",
    )
    _strict_match(
        activation.get("external_writes"),
        "FORBIDDEN",
        "predecessor.plan.writes",
    )
    _strict_match(
        plan.get("planned_actions"),
        {action: 0 for action in PREDECESSOR_ACTION_NAMES},
        "predecessor.plan.actions",
    )


def _validate_data_services_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-1502/contracts/data-services-foundation.v1.yaml",
        "data_services_contract",
    )
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-DATA-SERVICES-FOUNDATION-001",
            "version": "1.0.0",
            "story_id": "ST-1502",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.data_services.document",
    )
    _assert_unset_tree(
        contract.get("selected_configuration"), "predecessor.data_services.selected"
    )
    rds = _mapping(contract.get("rds_intent"), "predecessor.data_services.rds")
    for key, expected in {
        "private_only": "REQUIRED",
        "publicly_accessible": False,
        "encryption_at_rest": "REQUIRED_NOT_CONFIGURED",
        "backup": "REQUIRED_NOT_CONFIGURED",
        "point_in_time_recovery": "REQUIRED_NOT_CONFIGURED",
        "deletion_protection": "REQUIRED_NOT_CONFIGURED",
        "final_snapshot": "REQUIRED_NOT_CONFIGURED",
        "restore_test": "REQUIRED_NOT_EXECUTED",
    }.items():
        _strict_match(rds.get(key), expected, f"predecessor.data_services.rds.{key}")
    _assert_unset_tree(rds.get("selected"), "predecessor.data_services.rds.selected")

    s3 = _mapping(contract.get("s3_intent"), "predecessor.data_services.s3")
    for key, expected in {
        "public_access_block": "REQUIRED",
        "encryption_at_rest": "REQUIRED_NOT_CONFIGURED",
        "versioning": "REQUIRED_NOT_CONFIGURED",
        "force_destroy": "FORBIDDEN",
        "lifecycle_deletion": "FORBIDDEN",
        "automatic_deletion": "FORBIDDEN",
    }.items():
        _strict_match(s3.get(key), expected, f"predecessor.data_services.s3.{key}")
    _assert_unset_tree(
        {
            "selected_encryption_key_reference": s3.get(
                "selected_encryption_key_reference"
            ),
            "retention_days": s3.get("retention_days"),
            "lifecycle_rules": s3.get("lifecycle_rules"),
        },
        "predecessor.data_services.s3.selected",
    )
    roles = _list(s3.get("roles"), "predecessor.data_services.s3.roles")
    if [row.get("role") for row in roles if isinstance(row, Mapping)] != [
        "raw",
        "publication",
        "uploads_quarantine",
        "exports",
        "audit_logs",
    ]:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.data_services.s3.roles")
    for raw_role in roles:
        role = _mapping(raw_role, "predecessor.data_services.s3.role")
        _assert_unset_tree(
            {"physical_name": role.get("physical_name"), "arn": role.get("arn")},
            "predecessor.data_services.s3.role.selected",
        )

    sqs = _mapping(contract.get("sqs_intent"), "predecessor.data_services.sqs")
    queues = _list(sqs.get("classes"), "predecessor.data_services.sqs.classes")
    expected_classes = [
        "ingestion",
        "ai",
        "quality",
        "publication",
        "freshness",
        "analytics",
        "notification",
    ]
    if [
        row.get("class") for row in queues if isinstance(row, Mapping)
    ] != expected_classes:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.data_services.sqs.classes")
    for raw_queue in queues:
        queue = _mapping(raw_queue, "predecessor.data_services.sqs.queue")
        for key in ("dlq", "producer_consumer_separation", "redrive_role_separation"):
            _strict_match(
                queue.get(key),
                "REQUIRED_NOT_CONFIGURED",
                f"predecessor.data_services.sqs.{key}",
            )
        _assert_unset_tree(
            queue.get("selected"), "predecessor.data_services.sqs.selected"
        )

    secrets = _mapping(
        contract.get("secrets_manager_intent"), "predecessor.data_services.secrets"
    )
    _strict_match(secrets.get("secret_values"), "ABSENT", "predecessor.secrets")
    _strict_match(
        secrets.get("ambient_credential_resolution"),
        "FORBIDDEN",
        "predecessor.secrets.ambient",
    )
    _strict_match(
        secrets.get("environment_credential_resolution"),
        "FORBIDDEN",
        "predecessor.secrets.environment",
    )
    _assert_unset_tree(
        {
            "secret_names": secrets.get("secret_names"),
            "secret_arns": secrets.get("secret_arns"),
        },
        "predecessor.data_services.secrets.selected",
    )
    kms = _mapping(contract.get("kms_intent"), "predecessor.data_services.kms")
    _strict_match(kms.get("key_deletion"), "FORBIDDEN", "predecessor.kms.delete")
    _assert_unset_tree(
        {
            key: kms.get(key)
            for key in (
                "key_ids",
                "key_arns",
                "aliases",
                "policy_document",
                "deletion_window_days",
            )
        },
        "predecessor.data_services.kms.selected",
    )
    execution = _mapping(
        contract.get("execution_boundary"), "predecessor.data_services.execution"
    )
    _validate_disabled_execution(execution, command_field="commands")
    evidence = _mapping(
        contract.get("evidence_boundary"), "predecessor.data_services.evidence"
    )
    _strict_match(
        evidence.get("executable_terraform"), "ABSENT", "predecessor.executable"
    )
    _strict_match(evidence.get("credentials"), "ABSENT", "predecessor.credentials")

    plan = _load_repo_json(
        root,
        "infra/terraform/data-services/data-services.reference-plan.v1.json",
        "data_services_plan",
    )
    _validate_plan_activation(plan)
    plan_document = _mapping(plan.get("document"), "predecessor.data_services.plan")
    _strict_match(plan_document.get("story_id"), "ST-1502", "predecessor.plan.story")
    _assert_unset_tree(
        plan.get("selected_configuration"), "predecessor.data_services.plan.selected"
    )
    logical = _mapping(
        plan.get("logical_data_services"), "predecessor.data_services.logical"
    )
    for plan_key, contract_key in (
        ("rds", "rds_intent"),
        ("s3", "s3_intent"),
        ("sqs", "sqs_intent"),
        ("secrets_manager", "secrets_manager_intent"),
        ("kms", "kms_intent"),
    ):
        _strict_match(
            logical.get(plan_key),
            contract.get(contract_key),
            f"predecessor.data_services.{plan_key}",
        )


def _validate_compute_edge_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-1503/contracts/compute-edge-foundation.v1.yaml",
        "compute_edge_contract",
    )
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-COMPUTE-EDGE-FOUNDATION-001",
            "version": "1.0.0",
            "story_id": "ST-1503",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.compute_edge.document",
    )
    _assert_unset_tree(
        contract.get("selected_configuration"), "predecessor.compute_edge.selected"
    )
    workloads = _mapping(
        contract.get("workload_intent"), "predecessor.compute_edge.workloads"
    )
    for key in (
        "immutable_digest_selected_images",
        "signed_provenance",
        "sbom",
        "image_scanning",
        "least_privilege_workload_identities",
    ):
        _strict_match(
            workloads.get(key),
            "REQUIRED_NOT_CONFIGURED",
            f"predecessor.compute_edge.workloads.{key}",
        )
    _strict_match(workloads.get("secret_material"), "ABSENT", "predecessor.secret")
    roles = _list(workloads.get("roles"), "predecessor.compute_edge.roles")
    if [row.get("role") for row in roles if isinstance(row, Mapping)] != [
        "public_web",
        "admin_web",
        "core_api",
        "worker_pool",
    ]:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.compute_edge.roles")
    for raw_role in roles:
        role = _mapping(raw_role, "predecessor.compute_edge.role")
        _strict_match(
            role.get("direct_public_access"), "FORBIDDEN", "predecessor.public"
        )
        _assert_unset_tree(
            role.get("selected"), "predecessor.compute_edge.role.selected"
        )

    surfaces = _mapping(
        contract.get("surface_boundary_intent"), "predecessor.compute_edge.surfaces"
    )
    surface_rows = _list(surfaces.get("surfaces"), "predecessor.compute_edge.surfaces")
    if [row.get("surface") for row in surface_rows if isinstance(row, Mapping)] != [
        "public",
        "admin",
        "internal",
    ]:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.compute_edge.surfaces")
    for raw_surface in surface_rows:
        surface = _mapping(raw_surface, "predecessor.compute_edge.surface")
        _assert_unset_tree(
            surface.get("selected"), "predecessor.compute_edge.surface.selected"
        )
    edge = _mapping(
        contract.get("edge_routing_intent"), "predecessor.compute_edge.edge"
    )
    _strict_match(
        edge.get("direct_origin_public_access"), "FORBIDDEN", "predecessor.edge.public"
    )
    _assert_unset_tree(edge.get("selected"), "predecessor.compute_edge.edge.selected")
    health = _mapping(contract.get("health_intent"), "predecessor.compute_edge.health")
    _strict_match(
        _mapping(health.get("liveness"), "predecessor.liveness").get(
            "external_dependency_coupling"
        ),
        "FORBIDDEN",
        "predecessor.liveness.external",
    )
    readiness = _mapping(health.get("readiness"), "predecessor.readiness")
    _strict_match(
        readiness.get("infer_from_http_200_body"),
        "FORBIDDEN",
        "predecessor.readiness.http_200",
    )
    _strict_match(
        readiness.get("dependency_check"),
        "REQUIRED_NOT_CONFIGURED",
        "predecessor.readiness.dependency",
    )
    _strict_match(
        readiness.get("migration_compatibility_check"),
        "REQUIRED_NOT_CONFIGURED",
        "predecessor.readiness.migration",
    )
    _assert_unset_tree(
        _mapping(health.get("liveness"), "predecessor.liveness").get("selected"),
        "predecessor.compute_edge.liveness.selected",
    )
    _assert_unset_tree(
        readiness.get("selected"), "predecessor.compute_edge.readiness.selected"
    )
    execution = _mapping(
        contract.get("execution_boundary"), "predecessor.compute_edge.execution"
    )
    _validate_disabled_execution(execution, command_field="commands")
    evidence = _mapping(
        contract.get("evidence_boundary"), "predecessor.compute_edge.evidence"
    )
    _strict_match(
        evidence.get("executable_terraform"), "ABSENT", "predecessor.executable"
    )
    _strict_match(evidence.get("credentials"), "ABSENT", "predecessor.credentials")

    plan = _load_repo_json(
        root,
        "infra/terraform/compute-edge/compute-edge.reference-plan.v1.json",
        "compute_edge_plan",
    )
    _validate_plan_activation(plan)
    plan_document = _mapping(plan.get("document"), "predecessor.compute_edge.plan")
    _strict_match(plan_document.get("story_id"), "ST-1503", "predecessor.plan.story")
    _assert_unset_tree(
        plan.get("selected_configuration"), "predecessor.compute_edge.plan.selected"
    )
    logical = _mapping(
        plan.get("logical_compute_edge"), "predecessor.compute_edge.logical"
    )
    for plan_key, contract_key in (
        ("workloads", "workload_intent"),
        ("surfaces", "surface_boundary_intent"),
        ("edge_routing", "edge_routing_intent"),
        ("health", "health_intent"),
    ):
        _strict_match(
            logical.get(plan_key),
            contract.get(contract_key),
            f"predecessor.compute_edge.{plan_key}",
        )


def _validate_deployment_identity_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-1504/contracts/github-oidc-deployment.v1.yaml",
        "deployment_identity_contract",
    )
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-GITHUB-OIDC-DEPLOYMENT-001",
            "version": "1.0.0",
            "story_id": "ST-1504",
            "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.deployment_identity.document",
    )
    _assert_unset_tree(
        contract.get("selected_bindings"), "predecessor.deployment_identity.selected"
    )
    reference = _mapping(
        contract.get("reference_intent"), "predecessor.deployment_identity.reference"
    )
    for key in ("executable_workflow", "iam_trust_policy", "provider_sdk_types"):
        _strict_match(reference.get(key), "ABSENT", f"predecessor.identity.{key}")
    _strict_match(
        reference.get("production_deployment"),
        "FORBIDDEN",
        "predecessor.identity.production",
    )
    trust = _mapping(
        contract.get("trust_constraints"), "predecessor.deployment_identity.trust"
    )
    for key in (
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
        _strict_match(trust.get(key), "FORBIDDEN", f"predecessor.identity.trust.{key}")
    credential = _mapping(
        contract.get("credential_boundary"),
        "predecessor.deployment_identity.credential",
    )
    _strict_match(
        credential.get("credential_material"), "ABSENT", "predecessor.credential"
    )
    _strict_match(
        credential.get("credential_issuance_capability"),
        "ABSENT",
        "predecessor.credential.capability",
    )
    _strict_match(credential.get("secret_names"), [], "predecessor.secret_names")
    _strict_match(credential.get("secret_values"), [], "predecessor.secret_values")
    permissions = _mapping(
        contract.get("workflow_permission_intent"),
        "predecessor.deployment_identity.permissions",
    )
    _strict_match(permissions.get("actual_workflow"), "ABSENT", "predecessor.workflow")
    for key in (
        "write_all",
        "admin_permissions",
        "secrets_access",
        "mutable_external_action_references",
        "unbounded_reusable_workflow_callers",
        "pull_request_target_credential_path",
    ):
        _strict_match(
            permissions.get(key), "FORBIDDEN", f"predecessor.permissions.{key}"
        )
    protection = _mapping(
        contract.get("environment_protection_intent"),
        "predecessor.deployment_identity.protection",
    )
    for key in ("self_approval", "approval_bypass", "deployment_without_approval"):
        _strict_match(protection.get(key), "FORBIDDEN", f"predecessor.protection.{key}")
    execution = _mapping(
        contract.get("execution_boundary"),
        "predecessor.deployment_identity.execution",
    )
    _validate_disabled_execution(execution)
    _strict_match(
        execution.get("credential_issuance"),
        "FORBIDDEN",
        "predecessor.identity.issuance",
    )
    expected_operations = {
        "github_api_mutation": "FORBIDDEN",
        "github_ruleset_mutation": "FORBIDDEN",
        "github_workflow_mutation": "FORBIDDEN",
        "github_environment_mutation": "FORBIDDEN",
        "aws_api_call": "FORBIDDEN",
        "iam_policy_apply": "FORBIDDEN",
        "credential_issue": "FORBIDDEN",
        "deploy": "FORBIDDEN",
        "terraform_plan": "FORBIDDEN",
        "terraform_apply": "FORBIDDEN",
    }
    _strict_match(
        execution.get("operations"),
        expected_operations,
        "predecessor.identity.operations",
    )

    plan = _load_repo_json(
        root,
        "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json",
        "deployment_identity_plan",
    )
    _validate_plan_activation(plan)
    plan_document = _mapping(plan.get("document"), "predecessor.identity.plan")
    _strict_match(plan_document.get("story_id"), "ST-1504", "predecessor.plan.story")
    activation = _mapping(plan.get("activation"), "predecessor.identity.activation")
    _strict_match(
        activation.get("credential_issuance"),
        "FORBIDDEN",
        "predecessor.plan.issuance",
    )
    _strict_match(
        activation.get("operations"), expected_operations, "predecessor.plan.operations"
    )
    _assert_unset_tree(
        plan.get("selected_bindings"), "predecessor.deployment_identity.plan.selected"
    )
    for plan_key, contract_key in (
        ("logical_identity_path", "reference_intent"),
        ("trust_constraints", "trust_constraints"),
        ("credential_boundary", "credential_boundary"),
        ("workflow_permissions", "workflow_permission_intent"),
        ("environment_protection", "environment_protection_intent"),
    ):
        _strict_match(
            plan.get(plan_key),
            contract.get(contract_key),
            f"predecessor.identity.{plan_key}",
        )


def _validate_predecessor_semantics(root: Path) -> None:
    _validate_data_services_predecessor(root)
    _validate_compute_edge_predecessor(root)
    _validate_deployment_identity_predecessor(root)


def validate_contract(
    contract: object, root: Path = REPO_ROOT
) -> StagingDeploymentModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    for section, expected in EXPECTED_SECTIONS.items():
        _strict_match(value[section], expected, section)
    return StagingDeploymentModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> StagingDeploymentModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: StagingDeploymentModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: StagingDeploymentModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-STAGING-DEPLOYMENT-REFERENCE-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-1505",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_bindings": _section(model, "predecessor_bindings"),
        "environment": _section(model, "environment_boundary"),
        "selected_bindings": _section(model, "selected_bindings"),
        "artifact_admission": _section(model, "artifact_admission_intent"),
        "migration": _section(model, "migration_intent"),
        "health_and_smoke": _section(model, "health_and_smoke_intent"),
        "rollback": _section(model, "rollback_intent"),
        "logical_phases": _section(model, "logical_phases"),
        "action_counts": copy.deepcopy(execution["action_counts"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "runtime_status": execution["runtime_status"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "staging_action": execution["staging_action"],
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


def render_reference_plan(model: StagingDeploymentModel) -> bytes:
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
    model: StagingDeploymentModel, reference_plan: bytes, root: Path = REPO_ROOT
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    environment = _mapping(model.contract["environment_boundary"], "environment")
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-STAGING-DEPLOYMENT-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1505",
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
            "activation": execution["activation_status"],
            "action_counts": copy.deepcopy(execution["action_counts"]),
            "selected_provider": selection["cloud_provider"],
            "selected_account": selection["cloud_account_id"],
            "selected_region": selection["cloud_region"],
            "selected_repository": selection["github_repository"],
            "selected_environment": selection["github_environment"],
            "selected_role": selection["deployment_role"],
            "selected_artifact": selection["artifact_digest"],
            "credentials": evidence["credentials"],
            "formal_tst_009": evidence["formal_tst_009"],
            "formal_tst_022": evidence["formal_tst_022"],
            "migration_database": evidence["migration_database"],
            "http_smoke": evidence["http_smoke"],
            "playwright": evidence["playwright"],
            "staging": evidence["staging"],
            "rollback": evidence["rollback"],
            "release": evidence["release"],
            "production": evidence["production"],
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
        description="Build the disabled ST-1505 staging reference artifacts."
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
    except StagingDeploymentContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1505 staging deployment check passed")
    else:
        print("ST-1505 staging deployment artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
