#!/usr/bin/env python3
"""Build the disabled, non-executable ST-1504 GitHub OIDC artifacts."""

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
CONTRACT_PATH: Final = Path("changes/st-1504/contracts/github-oidc-deployment.v1.yaml")
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/deployment-identity/github-oidc.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1504/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1504_github_oidc.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1504_github_oidc.py"
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
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
    "docs/canonical/04_security/RAOS_10_implementation_slices_v1.0.yaml": (
        "3db3aeeb3cfd0cbb4ab91e3490956cae17d60e43950e48fdf50c1609019e1b22"
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
    "changes/st-0107/contracts/pr-governance.v1.yaml": (
        "ce6114ff9ae7e76e746e5b1eed5a045ee0982f18bd0d4e8614c73056ec3cdcb1"
    ),
    "changes/st-0107/ruleset-policy.v1.json": (
        "e999838c2f592e3795aa79222bcfbc8cedf4b59bad06024f0328ebd65b3e11f5"
    ),
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
    Path("changes/st-1504/README.md"),
    Path("scripts/build_st1504_github_oidc.py"),
    Path("tests/st1504/conftest.py"),
    Path("tests/st1504/test_contract.py"),
    Path("tests/st1504/test_generation.py"),
    Path("tests/st1504/test_negative_cases.py"),
)

EXPECTED_STORY: Final = {
    "id": "ST-1504",
    "epic_id": "EPIC-15",
    "title": "GitHub OIDC deployment",
    "objective": "short-lived deploy identityとenvironment approval",
    "depends_on": ["ST-0107", "ST-1501"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["workflow/IAM trust"],
    "acceptance_criteria": ["fork PR no credential", "production approval"],
    "test_suites": ["TST-026"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_OD_013: Final = {
    "id": "OD-013",
    "topic": "production_region_and_data_residency",
    "status": "HUMAN_DECISION_REQUIRED",
    "required_by": "Terraform production",
    "owner": "Security/Business Owner",
    "decision_needed": "AWS Region、Backup Region、越境移転の扱いを承認",
    "default_behavior": "Referenceはap-northeast-1、Production apply禁止",
    "blocking": True,
}
EXPECTED_TST_026: Final = {
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
}
EXPECTED_SECURITY_CONTROLS: Final = {
    "SEC-IAM-009": "Worker/CIは人間Credentialを共有しない",
    "SEC-IAM-010": "長期AWS keyをActions secretに置かない",
    "SEC-SDLC-001": "Rulesetとrequired review/checks",
    "SEC-SDLC-002": "Security、migration、contractsへowner review",
    "SEC-SDLC-004": "Dependency/container vulnerability scan",
    "SEC-SDLC-006": "History/PR/artifactをscan",
    "SEC-SDLC-007": "Release artifactのSBOM生成",
    "SEC-SDLC-008": "Build provenance/attestationを生成",
}
EXPECTED_THREATS: Final = {
    "THR-007": {
        "id": "THR-007",
        "threat": "Dependency compromise",
        "scenario": "Package/Action汚染",
        "impact": "Build/Production侵害",
        "controls": "pin、SCA、SBOM、provenance",
        "residual_risk": "TO_BE_ASSESSED_AFTER_IMPLEMENTATION",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    "THR-008": {
        "id": "THR-008",
        "threat": "CI credential abuse",
        "scenario": "PRからCloud credential取得",
        "impact": "Infrastructure侵害",
        "controls": "OIDC trust condition、environment approval",
        "residual_risk": "TO_BE_ASSESSED_AFTER_IMPLEMENTATION",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
}
EXPECTED_SECURITY_SLICE: Final = {
    "id": "SEC-SLICE-009",
    "name": "Supply chain and deployment",
    "depends_on": ["SEC-SLICE-001", "SEC-SLICE-007"],
    "deliverables": ["SBOM", "provenance", "OIDC deploy", "environment approval"],
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}

REQUIRED_CLAIM_BINDINGS: Final = (
    "repository_identity",
    "trusted_ref",
    "workflow_identity",
    "environment",
    "audience",
    "subject",
)
EXPECTED_REQUIRED_CHECKS: Final = (
    "Static",
    "Unit",
    "Contracts",
    "Database",
    "Storage",
    "Secrets",
    "Validate status overlay",
)
FOUNDATION_NATIVE_COMMANDS: Final = (
    "init",
    "plan",
    "apply",
    "destroy",
    "import",
    "refresh",
)
NATIVE_OPERATIONS: Final = (
    "github_api_mutation",
    "github_ruleset_mutation",
    "github_workflow_mutation",
    "github_environment_mutation",
    "aws_api_call",
    "iam_policy_apply",
    "credential_issue",
    "deploy",
    "terraform_plan",
    "terraform_apply",
)
ACTION_NAMES: Final = ("create", "update", "delete")
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


def _selected_bindings() -> dict[str, object]:
    return {
        "oidc_issuer_url": None,
        "oidc_audience": None,
        "oidc_subject": None,
        "github_organization": None,
        "github_repository": None,
        "github_repository_numeric_id": None,
        "default_branch_ref": None,
        "deploy_ref": None,
        "workflow_ref": None,
        "workflow_sha": None,
        "workflow_file_path": None,
        "deploy_job_id": None,
        "github_environment_name": None,
        "github_environment_reviewer_ids": [],
        "github_environment_allowed_refs": [],
        "reusable_workflow_callers": [],
        "aws_account_id": None,
        "aws_role_arn": None,
        "aws_role_name": None,
        "session_duration_seconds": None,
        "session_name": None,
        "session_tags": [],
        "oidc_thumbprints": [],
        "trust_policy_payload": None,
        "permission_policy_payload": None,
        "environment_protection_payload": None,
        "workflow_permissions_payload": None,
        "workflow_trigger_events": [],
        "external_action_references": [],
        "terraform_cli_version": None,
        "provider_plugins": [],
    }


EXPECTED_SECTIONS: Final[dict[str, Any]] = {
    "document": {
        "id": "RAOS-GITHUB-OIDC-DEPLOYMENT-001",
        "version": "1.0.0",
        "story_id": "ST-1504",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    },
    "predecessor_bindings": {
        "pr_governance": {
            "story_id": "ST-0107",
            "contract_uri": "repo://changes/st-0107/contracts/pr-governance.v1.yaml",
            "contract_sha256": PREDECESSOR_SOURCES[
                "changes/st-0107/contracts/pr-governance.v1.yaml"
            ],
            "desired_state_uri": "repo://changes/st-0107/ruleset-policy.v1.json",
            "desired_state_sha256": PREDECESSOR_SOURCES[
                "changes/st-0107/ruleset-policy.v1.json"
            ],
            "required_artifact_kind": "DESIRED_STATE_NOT_API_PAYLOAD",
            "required_target": "branch",
            "required_include": ["~DEFAULT_BRANCH"],
            "required_desired_enforcement": "active",
            "required_local_application_status": "NOT_EXECUTED",
            "required_remote_mutation": "FORBIDDEN",
            "required_bypass_actors": [],
            "required_protected_pr_controls": {
                "prohibit_deletion": True,
                "prohibit_force_push": True,
                "require_linear_history": True,
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
            },
        },
        "terraform_foundation": {
            "story_id": "ST-1501",
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
            "required_planned_actions": {action: 0 for action in ACTION_NAMES},
        },
    },
    "reference_intent": {
        "classification": "LOGICAL_IDENTITY_PATH_REFERENCE_ONLY",
        "source": "GITHUB_ACTIONS_OIDC",
        "destination": "AWS_SHORT_LIVED_WORKLOAD_SESSION",
        "github_workload_identity": "REQUIRED_NOT_CONFIGURED",
        "aws_role_session": "REQUIRED_NOT_CONFIGURED",
        "executable_workflow": "ABSENT",
        "iam_trust_policy": "ABSENT",
        "provider_sdk_types": "ABSENT",
        "production_deployment": "FORBIDDEN",
    },
    "selected_bindings": _selected_bindings(),
    "trust_constraints": {
        "status": "REQUIRED_NOT_CONFIGURED",
        "required_claim_bindings": list(REQUIRED_CLAIM_BINDINGS),
        "exact_repository_identity": "REQUIRED_NOT_CONFIGURED",
        "exact_trusted_ref": "REQUIRED_NOT_CONFIGURED",
        "exact_workflow_identity": "REQUIRED_NOT_CONFIGURED",
        "exact_environment": "REQUIRED_NOT_CONFIGURED",
        "exact_audience": "REQUIRED_NOT_CONFIGURED",
        "exact_subject": "REQUIRED_NOT_CONFIGURED",
        "wildcard_trust": "FORBIDDEN",
        "fork_pull_request": "FORBIDDEN",
        "untrusted_pull_request": "FORBIDDEN",
        "untrusted_ref": "FORBIDDEN",
        "untrusted_environment": "FORBIDDEN",
        "pull_request_target_credential_path": "FORBIDDEN",
        "unbounded_reusable_workflow_caller": "FORBIDDEN",
        "broad_organization_subject": "FORBIDDEN",
        "broad_repository_subject": "FORBIDDEN",
        "broad_ref_subject": "FORBIDDEN",
    },
    "credential_boundary": {
        "classification": "MATERIAL_FREE_REQUIREMENTS_ONLY",
        "long_lived_cloud_key": "FORBIDDEN",
        "repository_secret_cloud_credential": "FORBIDDEN",
        "fork_pr_credential_issuance": "FORBIDDEN",
        "untrusted_ref_credential_issuance": "FORBIDDEN",
        "untrusted_environment_credential_issuance": "FORBIDDEN",
        "oidc_session": "SHORT_LIVED_REQUIRED_NOT_CONFIGURED",
        "least_privilege": "REQUIRED_NOT_CONFIGURED",
        "role_chaining": "FORBIDDEN",
        "privilege_escalation": "FORBIDDEN",
        "credential_material": "ABSENT",
        "credential_issuance_capability": "ABSENT",
        "secret_names": [],
        "secret_values": [],
    },
    "workflow_permission_intent": {
        "classification": "INTENT_ONLY_WORKFLOW_ABSENT",
        "actual_workflow": "ABSENT",
        "id_token_write_scope": "FUTURE_EXACT_APPROVED_DEPLOY_JOB_ONLY",
        "contents_permission": "READ_MINIMUM_REQUIRED_NOT_CONFIGURED",
        "write_all": "FORBIDDEN",
        "admin_permissions": "FORBIDDEN",
        "secrets_access": "FORBIDDEN",
        "mutable_external_action_references": "FORBIDDEN",
        "unbounded_reusable_workflow_callers": "FORBIDDEN",
        "pull_request_target_credential_path": "FORBIDDEN",
    },
    "environment_protection_intent": {
        "classification": "PRODUCTION_PROTECTION_INTENT_ONLY",
        "production_environment": "REQUIRED_NOT_CONFIGURED",
        "distinct_human_approval": "REQUIRED_NOT_CONFIGURED",
        "protected_environment": "REQUIRED_NOT_CONFIGURED",
        "exact_allowed_refs": "REQUIRED_NOT_CONFIGURED",
        "self_approval": "FORBIDDEN",
        "approval_bypass": "FORBIDDEN",
        "deployment_without_approval": "FORBIDDEN",
    },
    "execution_boundary": {
        "activation_enabled": False,
        "activation_status": "DISABLED",
        "native_plan_status": "NOT_EXECUTED",
        "live_provider_calls": "FORBIDDEN",
        "external_writes": "FORBIDDEN",
        "credential_issuance": "FORBIDDEN",
        "operations": {operation: "FORBIDDEN" for operation in NATIVE_OPERATIONS},
        "planned_actions": {action: 0 for action in ACTION_NAMES},
    },
    "evidence_boundary": {
        "deliverable_classification": (
            "SOURCE_DERIVED_NON_EXECUTABLE_GITHUB_OIDC_REFERENCE_PLAN"
        ),
        "executable_workflow": "ABSENT",
        "iam_trust_policy": "ABSENT",
        "github_repository": "UNSET",
        "github_environment": "UNSET",
        "aws_account": "UNSET",
        "aws_role": "UNSET",
        "credentials": "ABSENT",
        "credential_issuance": "NOT_EXECUTED",
        "native_iac_validation": "NOT_EXECUTED",
        "workflow_inspection": "NOT_EXECUTED",
        "formal_tst_026": "NOT_EXECUTED",
        "hosted_github_aws": "NOT_EXECUTED",
        "live_oidc": "NOT_EXECUTED",
        "live_staging_release_production": "NOT_EXECUTED",
        "effective_canonical_status": "UNCHANGED",
    },
}
TOP_LEVEL_KEYS: Final = {"sources", *EXPECTED_SECTIONS}


class GithubOidcContractError(RuntimeError):
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
class GithubOidcModel:
    """A fully validated, closed ST-1504 contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _fail(code: str, field: str) -> NoReturn:
    raise GithubOidcContractError(code, field)


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
    except GithubOidcContractError:
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
    except GithubOidcContractError:
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


def _validate_authority_semantics(root: Path) -> None:
    backlog = _load_repo_yaml(
        root,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    story = _find_exact_record(backlog, "stories", "ST-1504", "backlog.stories")
    _strict_match(story, EXPECTED_STORY, "backlog.ST-1504")

    open_decisions = _load_repo_yaml(
        root,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    decision = _find_exact_record(
        open_decisions, "items", "OD-013", "open_decisions.items"
    )
    _strict_match(decision, EXPECTED_OD_013, "open_decisions.OD-013")

    tests = _load_repo_yaml(
        root,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    test = _find_exact_record(tests, "suites", "TST-026", "test_catalog.suites")
    _strict_match(test, EXPECTED_TST_026, "test_catalog.TST-026")

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
    for threat_id, expected in EXPECTED_THREATS.items():
        threat = _find_exact_record(
            threats, "threats", threat_id, "threat_register.threats"
        )
        _strict_match(threat, expected, f"threat_register.{threat_id}")

    slices = _load_repo_yaml(
        root,
        "docs/canonical/04_security/RAOS_10_implementation_slices_v1.0.yaml",
        "security_slices",
    )
    security_slice = _find_exact_record(
        slices, "slices", "SEC-SLICE-009", "security_slices.slices"
    )
    _strict_match(security_slice, EXPECTED_SECURITY_SLICE, "SEC-SLICE-009")

    architecture = _load_repo_yaml(
        root,
        "docs/upstream/key_documents/RAOS_02_architecture_catalog_v0.1.yaml",
        "architecture_catalog",
    )
    architecture_document = _mapping(architecture.get("document"), "architecture")
    if architecture_document.get("id") != "RAOS-ARCH-001":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "RAOS-ARCH-001")
    deployment = _mapping(architecture.get("deployment"), "architecture.deployment")
    aws_mapping = _mapping(deployment.get("aws_mapping"), "deployment.aws_mapping")
    if aws_mapping.get("ci_cd") != "GitHub_Actions_OIDC":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.ci_cd")
    if deployment.get("infrastructure_as_code") != "Terraform":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.iac")
    if deployment.get("production_data_in_nonprod") is not False:
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "deployment.production_data")


def _validate_pr_governance_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-0107/contracts/pr-governance.v1.yaml",
        "pr_governance_contract",
    )
    _strict_match(
        contract.get("document"),
        {
            "id": "RAOS-PR-GOVERNANCE-001",
            "version": "1.0.0",
            "story_id": "ST-0107",
            "status": "LOCAL_DESIRED_STATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "predecessor.pr_governance.document",
    )
    policy = _mapping(contract.get("ruleset_policy"), "predecessor.ruleset")
    _strict_match(policy.get("target"), "branch", "predecessor.ruleset.target")
    _strict_match(
        policy.get("include"), ["~DEFAULT_BRANCH"], "predecessor.ruleset.include"
    )
    _strict_match(
        policy.get("desired_enforcement"), "active", "predecessor.ruleset.enforcement"
    )
    _strict_match(
        policy.get("local_application_status"),
        "NOT_EXECUTED",
        "predecessor.ruleset.application",
    )
    _strict_match(policy.get("bypass_actors"), [], "predecessor.ruleset.bypass")
    for field in ("prohibit_deletion", "prohibit_force_push", "require_linear_history"):
        _strict_match(policy.get(field), True, f"predecessor.ruleset.{field}")
    pull_request = _mapping(policy.get("pull_request"), "predecessor.pull_request")
    for field in (
        "dismiss_stale_reviews_on_push",
        "require_code_owner_review",
        "require_last_push_approval",
        "required_review_thread_resolution",
    ):
        _strict_match(
            pull_request.get(field), True, f"predecessor.pull_request.{field}"
        )
    _strict_match(
        pull_request.get("allowed_merge_methods"),
        ["squash"],
        "predecessor.pull_request.merge_methods",
    )
    _strict_match(
        pull_request.get("required_approving_review_count"),
        1,
        "predecessor.pull_request.review_count",
    )
    required_checks = _list(
        policy.get("required_status_checks"), "predecessor.required_status_checks"
    )
    if len(required_checks) != len(EXPECTED_REQUIRED_CHECKS):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "required_status_checks")
    for index, context in enumerate(EXPECTED_REQUIRED_CHECKS):
        _strict_match(
            required_checks[index],
            {
                "context": context,
                "expected_source": "github-actions",
                "integration_id_binding": "REQUIRED_AT_ACTIVATION",
            },
            "predecessor.required_status_checks.item",
        )
    _strict_match(
        policy.get("strict_required_status_checks_policy"),
        True,
        "predecessor.strict_checks",
    )
    _strict_match(
        policy.get("do_not_enforce_on_create"),
        False,
        "predecessor.enforce_on_create",
    )
    owner_categories = _mapping(
        policy.get("required_owner_categories"), "predecessor.owner_categories"
    )
    deployment = _mapping(owner_categories.get("deployment"), "predecessor.deployment")
    if "/infra/" not in _list(deployment.get("patterns"), "predecessor.patterns"):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "deployment.patterns")
    _strict_match(
        deployment.get("roles"),
        ["operations", "security"],
        "predecessor.deployment.roles",
    )

    activation = _mapping(contract.get("activation"), "predecessor.activation")
    _strict_match(
        activation.get("generator_remote_mutation"),
        "FORBIDDEN",
        "predecessor.remote_mutation",
    )
    _strict_match(
        activation.get("live_status"), "NOT_EXECUTED", "predecessor.live_status"
    )
    _strict_match(
        activation.get("formal_tst_001"),
        "NOT_EXECUTED",
        "predecessor.formal_tst_001",
    )
    prerequisites = _list(
        activation.get("prerequisites"), "predecessor.activation.prerequisites"
    )
    if not prerequisites or prerequisites[-1] != (
        "a distinct human reviewer approves the governance change"
    ):
        _fail("PREDECESSOR_GOVERNANCE_DRIFT", "activation.prerequisites")

    desired_state = _mapping(
        load_json(
            _repository_regular_file(
                root,
                Path("changes/st-0107/ruleset-policy.v1.json"),
                "pr_governance_desired_state",
            )
        ),
        "pr_governance_desired_state",
    )
    document = _mapping(desired_state.get("document"), "predecessor.desired.document")
    _strict_match(
        document.get("artifact_kind"),
        "DESIRED_STATE_NOT_API_PAYLOAD",
        "predecessor.desired.kind",
    )
    _strict_match(
        document.get("live_status"), "NOT_EXECUTED", "predecessor.desired.live"
    )
    _strict_match(desired_state.get("ruleset"), policy, "predecessor.desired.ruleset")
    _strict_match(
        desired_state.get("activation"), activation, "predecessor.desired.activation"
    )


def _validate_foundation_predecessor(root: Path) -> None:
    contract = _load_repo_yaml(
        root,
        "changes/st-1501/contracts/terraform-foundation.v1.yaml",
        "foundation_contract",
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
        "predecessor.foundation.document",
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
        "predecessor.foundation.selection",
    )
    execution = _mapping(contract.get("execution_boundary"), "predecessor.foundation")
    _strict_match(
        execution.get("activation_enabled"), False, "predecessor.foundation.enabled"
    )
    _strict_match(
        execution.get("activation_status"),
        "DISABLED",
        "predecessor.foundation.status",
    )
    _strict_match(
        execution.get("live_provider_calls"),
        "FORBIDDEN",
        "predecessor.foundation.live",
    )
    _strict_match(
        execution.get("external_writes"),
        "FORBIDDEN",
        "predecessor.foundation.writes",
    )
    _strict_match(
        execution.get("native_plan_status"),
        "NOT_EXECUTED",
        "predecessor.foundation.native_plan",
    )
    _strict_match(
        execution.get("commands"),
        {command: "FORBIDDEN" for command in FOUNDATION_NATIVE_COMMANDS},
        "predecessor.foundation.commands",
    )
    _strict_match(
        execution.get("planned_actions"),
        {action: 0 for action in ACTION_NAMES},
        "predecessor.foundation.actions",
    )
    extension = _mapping(contract.get("extension_contract"), "predecessor.extension")
    _strict_match(
        extension.get("current_resource_payloads"),
        "FORBIDDEN",
        "predecessor.foundation.resources",
    )

    plan = _mapping(
        load_json(
            _repository_regular_file(
                root,
                Path(
                    "infra/terraform/foundation/"
                    "terraform-foundation.reference-plan.v1.json"
                ),
                "foundation_plan",
            )
        ),
        "foundation_plan",
    )
    plan_document = _mapping(plan.get("document"), "predecessor.foundation.plan")
    _strict_match(
        plan_document.get("artifact_kind"),
        "SOURCE_DERIVED_REFERENCE_STATE_PLAN",
        "predecessor.foundation.plan.kind",
    )
    _strict_match(
        plan_document.get("executable"), False, "predecessor.foundation.plan.executable"
    )
    activation = _mapping(plan.get("activation"), "predecessor.foundation.activation")
    _strict_match(
        activation.get("enabled"), False, "predecessor.foundation.activation.enabled"
    )
    _strict_match(
        activation.get("status"), "DISABLED", "predecessor.foundation.activation"
    )
    _strict_match(
        activation.get("native_commands"),
        {command: "FORBIDDEN" for command in FOUNDATION_NATIVE_COMMANDS},
        "predecessor.foundation.commands",
    )
    _strict_match(
        plan.get("planned_actions"),
        {action: 0 for action in ACTION_NAMES},
        "predecessor.foundation.plan.actions",
    )
    _strict_match(
        plan.get("selected_configuration"),
        contract.get("selected_configuration"),
        "predecessor.foundation.selection",
    )


def _validate_predecessor_semantics(root: Path) -> None:
    _validate_pr_governance_predecessor(root)
    _validate_foundation_predecessor(root)


def validate_contract(contract: object, root: Path = REPO_ROOT) -> GithubOidcModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    _validate_sources(value, root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    for section, expected in EXPECTED_SECTIONS.items():
        _strict_match(value[section], expected, section)
    return GithubOidcModel(contract=copy.deepcopy(dict(value)))


def load_and_validate_contract(root: Path = REPO_ROOT) -> GithubOidcModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _section(model: GithubOidcModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: GithubOidcModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-GITHUB-OIDC-REFERENCE-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-1504",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_bindings": _section(model, "predecessor_bindings"),
        "logical_identity_path": _section(model, "reference_intent"),
        "selected_bindings": _section(model, "selected_bindings"),
        "trust_constraints": _section(model, "trust_constraints"),
        "credential_boundary": _section(model, "credential_boundary"),
        "workflow_permissions": _section(model, "workflow_permission_intent"),
        "environment_protection": _section(model, "environment_protection_intent"),
        "planned_actions": copy.deepcopy(execution["planned_actions"]),
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "native_plan_status": execution["native_plan_status"],
            "live_provider_calls": execution["live_provider_calls"],
            "external_writes": execution["external_writes"],
            "credential_issuance": execution["credential_issuance"],
            "operations": copy.deepcopy(execution["operations"]),
        },
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
    }


def render_reference_plan(model: GithubOidcModel) -> bytes:
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
    model: GithubOidcModel, reference_plan: bytes, root: Path = REPO_ROOT
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-GITHUB-OIDC-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1504",
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
            "selected_repository": selection["github_repository"],
            "selected_environment": selection["github_environment_name"],
            "selected_aws_account": selection["aws_account_id"],
            "selected_aws_role": selection["aws_role_arn"],
            "trust_policy_payload": selection["trust_policy_payload"],
            "workflow_file_path": selection["workflow_file_path"],
            "credentials": evidence["credentials"],
            "credential_issuance": evidence["credential_issuance"],
            "workflow_inspection": evidence["workflow_inspection"],
            "formal_tst_026": evidence["formal_tst_026"],
            "hosted_github_aws": evidence["hosted_github_aws"],
            "live_oidc": evidence["live_oidc"],
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
        description="Build the disabled ST-1504 GitHub OIDC reference artifacts."
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
    except GithubOidcContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1504 GitHub OIDC check passed")
    else:
        print("ST-1504 GitHub OIDC artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
