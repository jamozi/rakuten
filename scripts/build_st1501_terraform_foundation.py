#!/usr/bin/env python3
"""Build the disabled, reference-only ST-1501 foundation artifacts."""

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
CONTRACT_PATH: Final = Path("changes/st-1501/contracts/terraform-foundation.v1.yaml")
DESIGN_HANDOFF_PATH: Final = Path(
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/foundation/terraform-foundation.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1501/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1501_terraform_foundation.py"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1501_terraform_foundation.py"
)
CHECK_COMMAND: Final = f"{GENERATION_COMMAND} --check"

PINNED_SOURCES: Final = {
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
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234"
    ),
    "changes/st-1501/DESIGN_HANDOFF_V1_ST1501_PROVIDER_NEUTRAL_FOUNDATION.yaml": (
        "cbbf28700a9ce019cb821bb4bfadf529393c8c948101b205d74be898c7599d7f"
    ),
}

EXPECTED_HANDOFF_LIST_SECTIONS: Final[dict[str, tuple[str, ...]]] = {
    "approved_scope": (
        "Define an additional provider-neutral foundation admission boundary for "
        "Full RAOS without making AWS or any provider a selected, default, fallback, "
        "or Production-admission binding.",
        "Preserve AWS Tokyo as the current Canonical Reference Architecture inherited "
        "from INT-DEC-007 and RAOS-ARCH-001 without making it a selected binding or "
        "Production admission prerequisite.",
        "Preserve the Canonical AWS-specific ST-1501 backlog objective and deliverable "
        "as authoritative, not erased, replaced, or completed by this portability "
        "overlay.",
        "Admit non-AWS and owner-managed profiles only as additional portable "
        "implementation paths with identical complete capabilities and evidence.",
        "Require every future foundation profile to map the same closed capability "
        "inventory and provide equivalent security, operations, release, recovery, "
        "and residency evidence.",
        "Keep every provider, account or project, region, plugin, backend, "
        "credential, network, budget, and resource binding unset while OD-013 "
        "remains unresolved.",
    ),
    "source_design_refs": (
        "repo://docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "repo://docs/canonical/01_integration/"
        "RAOS_07_canonical_decisions_v1.0.yaml#INT-DEC-007",
        "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml#OD-013",
        "repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml#ST-1501",
        "repo://docs/upstream/key_documents/"
        "RAOS_02_system_architecture_v0.1.md#RAOS-ARCH-001",
        "repo://docs/canonical/06_ops/"
        "RAOS_12_operations_reliability_design_v1.0.md#RAOS-OPS-001",
        "repo://docs/canonical/04_security/"
        "RAOS_10_security_privacy_design_v1.0.md#RAOS-SEC-001",
        "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml#TST-026",
    ),
    "rationale": (
        "INT-DEC-007 makes AWS Tokyo a Reference Architecture while requiring a "
        "portable Core, so provider admission must evaluate capabilities and "
        "evidence rather than a provider name.",
        "Provider, account, region, plugin, or backend defaults would silently turn "
        "the current Canonical Reference Architecture into a live selected "
        "infrastructure choice.",
        "A closed foundation capability inventory permits AWS, another cloud, or "
        "owner-managed infrastructure without selecting an unreviewed provider or "
        "topology now.",
        "Keeping all bindings null and eligibility unevaluated preserves OD-013 and "
        "every external security, operations, release, and Production gate.",
    ),
    "rejected_alternatives": (
        "Require AWS, an AWS account, or ap-northeast-1 merely because Canonical "
        "sources record them as the reference architecture.",
        "Select a different cloud or owner-managed platform before capability "
        "mapping, residency, budget, credentials, operations, and recovery evidence "
        "exist.",
        "Infer a provider, account, region, plugin, or backend from names, reference "
        "metadata, defaults, ambient configuration, or fallback behavior.",
        "Permit partial, unknown, duplicate, implicit, provider-label-only, or "
        "reference-only capability mappings.",
        "Lower security, operations, release, backup, restore, rollback, or residency "
        "evidence for any provider kind.",
    ),
    "constraints": (
        "Exactly one explicit mapping is required for every required foundation "
        "capability before a future profile can be eligible.",
        "Missing, unknown, duplicate, partial, implicit, or provider-label-only "
        "mappings fail closed.",
        "IaC toolchain and provider plugins require exact version, integrity, "
        "provenance, and offline-verifiable evidence before native infrastructure "
        "payloads are admitted.",
        "Remote state requires encryption, locking, audit logging, backup, restore, "
        "and recovery evidence without selecting a backend now.",
        "Development and Production require separated accounts, projects, tenants, "
        "or equivalent isolation semantics independent of provider vocabulary.",
        "Network capability must prove public, admin, internal, data-plane, ingress, "
        "egress, and control-plane boundaries without assuming AWS service names.",
        "Workload identity and secrets must be least-privilege, non-ambient, "
        "auditable, and short-lived or otherwise explicitly reviewed.",
        "Telemetry, audit, drift detection, backup/restore, recovery, budget/stop "
        "controls, rollback, and region/data-residency evidence are mandatory and "
        "provider-neutral.",
        "No credential, provider call, network access, external write, infrastructure "
        "init, plan, apply, deployment, release, or status transition is authorized "
        "by this record.",
    ),
    "security_and_approval_gates": (
        "Preserve IaC-only Production changes, explicit human approval, manual-change "
        "prohibition, drift detection, and formal TST-026 requirements.",
        "Preserve separation of Development and Production, private data-plane "
        "boundaries, controlled ingress/egress, workload identity, auditability, "
        "backup/restore, and rollback evidence.",
        "Preserve OD-013 region, backup-region, cross-border transfer, and "
        "data-residency blocking state until its human owners provide valid "
        "evidence.",
        "Require the same security, operations, release, recovery, and residency "
        "evidence for AWS, another cloud, and owner-managed infrastructure.",
        "Never infer eligibility from a provider label, account or project name, "
        "region, plugin, backend, Canonical Reference Architecture status, local "
        "generator success, or predecessor completion.",
    ),
    "acceptance_criteria": (
        "The ST-1501 source and generated reference expose a closed provider-neutral "
        "foundation capability inventory with no selected, default, or fallback "
        "profile or binding.",
        "Every future eligible profile must have exactly one explicit mapping for "
        "every required capability and complete equivalent evidence.",
        "Unknown, missing, duplicate, partial, implicit, defaulted, fallback, "
        "label-only, or reference-only mappings are rejected before eligibility.",
        "AWS Tokyo remains the current Canonical Reference Architecture, while its "
        "status alone cannot select a provider, account, region, plugin, backend, or "
        "satisfy admission or evidence.",
        "The Canonical AWS-specific ST-1501 objective and Terraform modules/state-plan "
        "deliverable remain authoritative and NOT_STARTED/NOT_EXECUTED; this overlay "
        "neither erases, replaces, nor completes them.",
        "Non-AWS and owner-managed profiles are additional portable implementation "
        "paths only and require the same complete capability mapping and evidence as "
        "AWS.",
        "Existing disabled activation, forbidden native commands, zero action counts, "
        "unresolved OD-013, and NOT_EXECUTED evidence remain unchanged.",
    ),
    "required_test_evidence": (
        "Isolated tests/st1501 positive contract and generated-plan assertions.",
        "Hostile tests for missing, unknown, duplicate, reordered, partial, "
        "defaulted, fallback, provider-binding, and AWS-label-only admission "
        "attempts.",
        "Existing hostile filesystem, closed-schema, exact-type, no-provider-call, "
        "and no-write tests remain passing.",
        "Owner generator regeneration and read-only --check, Ruff for changed Python, "
        "and git diff --check.",
        "Formal TST-026, hosted CI, native IaC, provider, staging, release, "
        "deployment, and Production evidence remain separately unexecuted.",
    ),
}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    DESIGN_HANDOFF_PATH,
    Path("changes/st-1501/README.md"),
    Path("scripts/build_st1501_terraform_foundation.py"),
    Path("tests/st1501/conftest.py"),
    Path("tests/st1501/test_contract.py"),
    Path("tests/st1501/test_generation.py"),
    Path("tests/st1501/test_negative_cases.py"),
)

EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-TERRAFORM-FOUNDATION-001",
    "version": "1.1.0",
    "story_id": "ST-1501",
    "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
    "formal_verification": "NOT_EXECUTED",
}
EXPECTED_STORY: Final = {
    "id": "ST-1501",
    "epic_id": "EPIC-15",
    "title": "Terraform foundation",
    "objective": "AWS account/region/network/provider setup",
    "depends_on": ["ST-0106"],
    "requirement_ids": [],
    "design_refs": ["RAOS-ARCH-001", "RAOS-OPS-001"],
    "deliverables": ["Terraform modules/state plan"],
    "acceptance_criteria": ["no production apply without approval"],
    "test_suites": ["TST-026"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": ["OD-013"],
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
EXPECTED_INFRA_CONTROLS: Final = {
    "SEC-INFRA-001": "RDS/worker/object admin endpointをPublicにしない",
    "SEC-INFRA-002": "Public ingressを管理Pointへ限定",
    "SEC-INFRA-003": "Workload別にProvider allowlist",
    "SEC-INFRA-004": "ProductionとDevelopmentを分離",
    "SEC-INFRA-005": "Manual driftを検知し原則IaCで変更",
    "SEC-INFRA-009": "Control plane操作を記録",
    "SEC-INFRA-010": "急増時のAlertと停止手順",
}

TOP_LEVEL_KEYS: Final = {
    "document",
    "sources",
    "reference_architecture",
    "provider_neutral_foundation_admission",
    "selected_configuration",
    "execution_boundary",
    "state_requirements",
    "account_requirements",
    "production_change_requirements",
    "extension_contract",
    "evidence_boundary",
}
SELECTION_KEYS: Final = {
    "cloud_provider",
    "production_region",
    "backup_region",
    "development_account_id",
    "production_account_id",
    "terraform_cli_version",
    "provider_plugins",
    "state_backend",
    "credential_source",
    "network_cidrs",
    "availability_zones",
    "kms_key_reference",
    "monthly_budget_jpy",
    "resource_definitions",
}
NULL_SELECTION_FIELDS: Final = (
    "cloud_provider",
    "production_region",
    "backup_region",
    "development_account_id",
    "production_account_id",
    "terraform_cli_version",
    "state_backend",
    "credential_source",
    "kms_key_reference",
    "monthly_budget_jpy",
)
EMPTY_SELECTION_FIELDS: Final = (
    "provider_plugins",
    "network_cidrs",
    "availability_zones",
    "resource_definitions",
)
NATIVE_COMMANDS: Final = ("init", "plan", "apply", "destroy", "import", "refresh")
ACTION_NAMES: Final = ("create", "update", "delete")
ELIGIBLE_PROFILE_KINDS: Final = (
    "AWS",
    "OTHER_CLOUD",
    "OWNER_MANAGED_INFRASTRUCTURE",
)
FOUNDATION_BINDING_NAMES: Final = (
    "provider",
    "account_or_project",
    "region",
    "provider_plugin",
    "state_backend",
)
FOUNDATION_CAPABILITY_OUTCOMES: Final = (
    (
        "iac_toolchain_and_plugin_provenance",
        "PINNED_INTEGRITY_VERIFIED_TOOLCHAIN_AND_PLUGIN_PROVENANCE",
    ),
    (
        "remote_state_integrity_and_recovery",
        "ENCRYPTED_LOCKED_AUDITED_BACKED_UP_AND_RECOVERABLE_STATE",
    ),
    (
        "environment_tenant_isolation",
        "DEVELOPMENT_AND_PRODUCTION_ACCOUNT_PROJECT_TENANT_OR_EQUIVALENT_ISOLATION",
    ),
    (
        "network_segmentation_and_traffic_control",
        "PUBLIC_ADMIN_INTERNAL_DATA_INGRESS_EGRESS_AND_CONTROL_PLANE_BOUNDARIES",
    ),
    (
        "workload_identity_and_secret_boundary",
        "LEAST_PRIVILEGE_NON_AMBIENT_AUDITABLE_IDENTITY_AND_SECRETS",
    ),
    (
        "observability_audit_and_drift_detection",
        "TELEMETRY_CONTROL_PLANE_AUDIT_ALERTING_AND_DRIFT_DETECTION",
    ),
    (
        "infrastructure_backup_restore_and_recovery",
        "VERSIONED_CONFIGURATION_BACKUP_RESTORE_DRILL_AND_RECOVERY_EVIDENCE",
    ),
    (
        "cost_budget_alert_and_stop_controls",
        "ATTRIBUTABLE_COST_BUDGET_ALERT_AND_BOUNDED_STOP_CONTROLS",
    ),
    (
        "region_and_data_residency",
        "APPROVED_PRIMARY_BACKUP_CROSS_BORDER_AND_DATA_RESIDENCY_EVIDENCE",
    ),
    (
        "human_approved_change_and_rollback",
        "IAC_ONLY_HUMAN_APPROVED_PROMOTION_ROLLBACK_AND_RECOVERY",
    ),
)
REQUIRED_FOUNDATION_CAPABILITY_IDS: Final = tuple(
    capability_id for capability_id, _outcome in FOUNDATION_CAPABILITY_OUTCOMES
)
MAX_YAML_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class FoundationContractError(RuntimeError):
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
class ReferenceArchitecture:
    cloud: str
    region: str
    classification: str
    inherited_from: str
    portable_core_required: bool
    default: bool
    implicit_fallback: bool
    selected_binding: bool
    eligibility_shortcut: bool
    admission_requirement: bool
    evidence_substitute: bool


@dataclass(frozen=True, slots=True)
class ProviderNeutralFoundationAdmission:
    definition: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SelectedConfiguration:
    cloud_provider: None
    production_region: None
    backup_region: None
    development_account_id: None
    production_account_id: None
    terraform_cli_version: None
    provider_plugins: tuple[str, ...]
    state_backend: None
    credential_source: None
    network_cidrs: tuple[str, ...]
    availability_zones: tuple[str, ...]
    kms_key_reference: None
    monthly_budget_jpy: None
    resource_definitions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionBoundary:
    activation_enabled: bool
    activation_status: str
    native_plan_status: str
    network_access: str
    credential_access: str
    live_provider_calls: str
    external_writes: str
    deploy_action: str
    release_action: str
    production_action: str
    commands: tuple[tuple[str, str], ...]
    planned_actions: tuple[tuple[str, int], ...]


@dataclass(frozen=True, slots=True)
class StateRequirements:
    encryption: str
    locking: str
    audit_logging: str
    backup_and_restore: str
    selected_backend: None


@dataclass(frozen=True, slots=True)
class AccountRequirements:
    separate_development_and_production: str
    development_account_id: None
    production_account_id: None


@dataclass(frozen=True, slots=True)
class ProductionChangeRequirements:
    iac_only: str
    human_approval: str
    drift_detection: str
    manual_change: str
    od_013_status: str
    production_apply: str


@dataclass(frozen=True, slots=True)
class ExtensionContract:
    current_resource_payloads: str
    successor_contract_revision_required: bool
    native_toolchain_pin_required_before_hcl: bool
    successors: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class EvidenceBoundary:
    deliverable_classification: str
    executable_terraform: str
    terraform_cli: str
    provider_plugins: str
    remote_state: str
    provider_account_or_project: str
    credentials: str
    formal_tst_026: str
    live_staging_release_production: str
    effective_canonical_status: str


@dataclass(frozen=True, slots=True)
class FoundationModel:
    reference: ReferenceArchitecture
    admission: ProviderNeutralFoundationAdmission
    selection: SelectedConfiguration
    execution: ExecutionBoundary
    state: StateRequirements
    accounts: AccountRequirements
    production: ProductionChangeRequirements
    extension: ExtensionContract
    evidence: EvidenceBoundary


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _fail(code: str, field: str) -> NoReturn:
    raise FoundationContractError(code, field)


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
        if len(value_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_match(value_list[index], expected_value, f"{field}.item")
        return
    if expected is None:
        _unset(actual, field)
        return
    if type(expected) is bool:
        _boolean(actual, expected, field)
        return
    if type(expected) is int:
        _integer(actual, expected, field)
        return
    if type(expected) is str:
        _string(actual, expected, field)
        return
    _fail("TYPE_MISMATCH", field)


def _string(value: object, expected: str, field: str) -> str:
    if type(value) is not str:
        _fail("TYPE_MISMATCH", field)
    if value != expected:
        _fail("FIXED_VALUE_VIOLATION", field)
    return value


def _boolean(value: object, expected: bool, field: str) -> bool:
    if type(value) is not bool:
        _fail("TYPE_MISMATCH", field)
    if value is not expected:
        _fail("SAFE_BOUNDARY_VIOLATION", field)
    return value


def _integer(value: object, expected: int, field: str) -> int:
    if type(value) is not int:
        _fail("TYPE_MISMATCH", field)
    if value != expected:
        _fail("SAFE_BOUNDARY_VIOLATION", field)
    return value


def _unset(value: object, field: str) -> None:
    if value is not None:
        _fail("SELECTION_MUST_REMAIN_UNSET", field)
    return None


def _empty_list(value: object, field: str) -> tuple[str, ...]:
    rows = _list(value, field)
    if rows:
        _fail("SELECTION_MUST_REMAIN_UNSET", field)
    return ()


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
    if len(content) > MAX_YAML_BYTES:
        _fail("YAML_SIZE_LIMIT", "yaml")
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", "yaml")
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", "yaml")
        return yaml.load(text, Loader=UniqueKeyLoader)
    except FoundationContractError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", "yaml")


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


def _validate_design_handoff(root: Path) -> None:
    handoff = _mapping(
        load_yaml(_repository_regular_file(root, DESIGN_HANDOFF_PATH, "handoff")),
        "handoff",
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
        _fail("CLOSED_SCHEMA_VIOLATION", "handoff")
    _string(handoff.get("schema"), "DESIGN_HANDOFF_V1", "handoff.schema")
    _integer(handoff.get("version"), 1, "handoff.version")
    _string(
        handoff.get("record_status"),
        "RECORDED_DURABLE_OWNER_DECISION",
        "handoff.record_status",
    )
    _string(handoff.get("approved_story"), "ST-1501", "handoff.approved_story")
    for field, expected_rows in EXPECTED_HANDOFF_LIST_SECTIONS.items():
        _strict_match(handoff.get(field), list(expected_rows), f"handoff.{field}")

    decision = _mapping(handoff.get("decision"), "handoff.decision")
    _exact_keys(
        decision,
        {
            "foundation_provider_policy",
            "selected_profile",
            "default_profile",
            "fallback_profile",
            "concrete_alternate_provider_selected",
            "eligible_profile_kinds",
            "eligibility_condition",
            "aws_reference_boundary",
            "binding_policy",
            "required_capability_ids",
        },
        "handoff.decision",
    )
    _string(
        decision.get("foundation_provider_policy"),
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
        "handoff.decision.foundation_provider_policy",
    )
    for field in ("selected_profile", "default_profile", "fallback_profile"):
        _unset(decision.get(field), f"handoff.decision.{field}")
    _boolean(
        decision.get("concrete_alternate_provider_selected"),
        False,
        "handoff.decision.concrete_alternate_provider_selected",
    )
    _strict_match(
        decision.get("eligible_profile_kinds"),
        list(ELIGIBLE_PROFILE_KINDS),
        "handoff.decision.eligible_profile_kinds",
    )
    _string(
        decision.get("eligibility_condition"),
        "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE",
        "handoff.decision.eligibility_condition",
    )
    _strict_match(
        decision.get("aws_reference_boundary"),
        {
            "canonical_decision_id": "INT-DEC-007",
            "reference_profile": "AWS_TOKYO",
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
        "handoff.decision.aws_reference_boundary",
    )
    expected_binding_policy: dict[str, object] = {
        name: {"selected": None, "default": None, "fallback": None}
        for name in FOUNDATION_BINDING_NAMES
    }
    expected_binding_policy.update(
        {
            "implicit_binding": "FORBIDDEN",
            "name_or_reference_only_eligibility": "FORBIDDEN",
        }
    )
    _strict_match(
        decision.get("binding_policy"),
        expected_binding_policy,
        "handoff.decision.binding_policy",
    )
    _strict_match(
        decision.get("required_capability_ids"),
        list(REQUIRED_FOUNDATION_CAPABILITY_IDS),
        "handoff.decision.required_capability_ids",
    )
    _strict_match(
        handoff.get("open_decision_state"),
        {
            "OD-013": {
                "status": "HUMAN_DECISION_REQUIRED",
                "resolved": False,
                "blocking": True,
                "safe_default": ("REFERENCE_METADATA_ONLY_PRODUCTION_APPLY_FORBIDDEN"),
            }
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
    story = _find_exact_record(backlog, "stories", "ST-1501", "backlog.stories")
    if dict(story) != EXPECTED_STORY:
        _fail("AUTHORITY_STORY_DRIFT", "backlog.ST-1501")

    decisions = _mapping(
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
    decision = _find_exact_record(
        decisions, "decisions", "INT-DEC-007", "canonical_decisions.decisions"
    )
    if dict(decision) != EXPECTED_INT_DEC_007:
        _fail("AUTHORITY_DECISION_DRIFT", "INT-DEC-007")

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
    od_013 = _find_exact_record(
        open_decisions, "items", "OD-013", "open_decisions.items"
    )
    if dict(od_013) != EXPECTED_OD_013:
        _fail("AUTHORITY_OPEN_DECISION_DRIFT", "OD-013")

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
    tst_026 = _find_exact_record(test_catalog, "suites", "TST-026", "test_catalog")
    if dict(tst_026) != EXPECTED_TST_026:
        _fail("AUTHORITY_TEST_DRIFT", "TST-026")

    control_catalog = _mapping(
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
    for control_id, requirement in EXPECTED_INFRA_CONTROLS.items():
        control = _find_exact_record(
            control_catalog, "controls", control_id, "security_controls.controls"
        )
        if (
            control.get("requirement") != requirement
            or control.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or control.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("AUTHORITY_CONTROL_DRIFT", control_id)

    architecture_catalog = _mapping(
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
    document = _mapping(architecture_catalog.get("document"), "architecture.document")
    if document.get("id") != "RAOS-ARCH-001":
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "RAOS-ARCH-001")
    architecture = _mapping(architecture_catalog.get("architecture"), "architecture")
    cloud_reference = _mapping(
        architecture.get("cloud_reference"), "architecture.cloud_reference"
    )
    if dict(cloud_reference) != {
        "provider": "AWS",
        "region": "ap-northeast-1",
        "portable_core_required": True,
    }:
        _fail("AUTHORITY_ARCHITECTURE_DRIFT", "RAOS-ARCH-001.cloud_reference")
    _validate_design_handoff(root)


def _parse_reference(contract: Mapping[str, Any]) -> ReferenceArchitecture:
    value = _mapping(contract["reference_architecture"], "reference_architecture")
    _exact_keys(
        value,
        {
            "cloud",
            "region",
            "classification",
            "inherited_from",
            "portable_core_required",
            "default",
            "implicit_fallback",
            "selected_binding",
            "eligibility_shortcut",
            "admission_requirement",
            "evidence_substitute",
        },
        "reference_architecture",
    )
    return ReferenceArchitecture(
        cloud=_string(value["cloud"], "AWS", "reference_architecture.cloud"),
        region=_string(
            value["region"], "ap-northeast-1", "reference_architecture.region"
        ),
        classification=_string(
            value["classification"],
            "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
            "reference_architecture.classification",
        ),
        inherited_from=_string(
            value["inherited_from"],
            "INT-DEC-007",
            "reference_architecture.inherited_from",
        ),
        portable_core_required=_boolean(
            value["portable_core_required"],
            True,
            "reference_architecture.portable_core_required",
        ),
        default=_boolean(value["default"], False, "reference_architecture.default"),
        implicit_fallback=_boolean(
            value["implicit_fallback"],
            False,
            "reference_architecture.implicit_fallback",
        ),
        selected_binding=_boolean(
            value["selected_binding"],
            False,
            "reference_architecture.selected_binding",
        ),
        eligibility_shortcut=_boolean(
            value["eligibility_shortcut"],
            False,
            "reference_architecture.eligibility_shortcut",
        ),
        admission_requirement=_boolean(
            value["admission_requirement"],
            False,
            "reference_architecture.admission_requirement",
        ),
        evidence_substitute=_boolean(
            value["evidence_substitute"],
            False,
            "reference_architecture.evidence_substitute",
        ),
    )


def _parse_provider_neutral_admission(
    contract: Mapping[str, Any],
) -> ProviderNeutralFoundationAdmission:
    value = _mapping(
        contract["provider_neutral_foundation_admission"],
        "provider_neutral_foundation_admission",
    )
    _exact_keys(
        value,
        {
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
            "eligibility_condition",
            "binding_policy",
            "mapping_policy",
            "aws_reference_boundary",
            "evidence_equivalence_policy",
            "capability_mapping_requirements",
        },
        "provider_neutral_foundation_admission",
    )
    _string(
        value["classification"],
        "STRICT_PROVIDER_NEUTRAL_FOUNDATION_CAPABILITY_ADMISSION",
        "provider_neutral_foundation_admission.classification",
    )
    _string(
        value["admission_status"],
        "NOT_EVALUATED",
        "provider_neutral_foundation_admission.admission_status",
    )
    _boolean(value["eligible"], False, "provider_neutral_foundation_admission.eligible")
    for field in (
        "selected_profile_id",
        "selected_profile_kind",
        "selected_provider_name",
        "default_profile_id",
        "fallback_profile_id",
    ):
        _unset(value[field], f"provider_neutral_foundation_admission.{field}")
    _boolean(
        value["concrete_alternate_provider_selected"],
        False,
        "provider_neutral_foundation_admission.concrete_alternate_provider_selected",
    )
    _strict_match(
        value["eligible_profile_kinds"],
        list(ELIGIBLE_PROFILE_KINDS),
        "provider_neutral_foundation_admission.eligible_profile_kinds",
    )
    _string(
        value["eligibility_condition"],
        "COMPLETE_EXACT_CAPABILITY_MAPPING_AND_EQUIVALENT_EVIDENCE",
        "provider_neutral_foundation_admission.eligibility_condition",
    )

    binding_policy = _mapping(
        value["binding_policy"],
        "provider_neutral_foundation_admission.binding_policy",
    )
    _exact_keys(
        binding_policy,
        {
            *FOUNDATION_BINDING_NAMES,
            "implicit_binding",
            "name_or_reference_only_eligibility",
        },
        "provider_neutral_foundation_admission.binding_policy",
    )
    for binding_name in FOUNDATION_BINDING_NAMES:
        binding = _mapping(
            binding_policy[binding_name],
            f"provider_neutral_foundation_admission.binding_policy.{binding_name}",
        )
        _exact_keys(
            binding,
            {"selected", "default", "fallback"},
            f"provider_neutral_foundation_admission.binding_policy.{binding_name}",
        )
        for field in ("selected", "default", "fallback"):
            _unset(
                binding[field],
                (
                    "provider_neutral_foundation_admission.binding_policy."
                    f"{binding_name}.{field}"
                ),
            )
    _string(
        binding_policy["implicit_binding"],
        "FORBIDDEN",
        "provider_neutral_foundation_admission.binding_policy.implicit_binding",
    )
    _string(
        binding_policy["name_or_reference_only_eligibility"],
        "FORBIDDEN",
        (
            "provider_neutral_foundation_admission.binding_policy."
            "name_or_reference_only_eligibility"
        ),
    )

    _strict_match(
        value["mapping_policy"],
        {
            "required_mapping_mode": "EXACTLY_ONE_PER_REQUIRED_CAPABILITY",
            "required_capability_count": len(REQUIRED_FOUNDATION_CAPABILITY_IDS),
            "configured_mapping_count": 0,
            "complete_mapping": False,
            "missing_mapping": "REJECT",
            "unknown_mapping": "REJECT",
            "duplicate_mapping": "REJECT",
            "implicit_mapping": "REJECT",
            "partial_mapping": "REJECT",
            "provider_label_only_mapping": "REJECT",
        },
        "provider_neutral_foundation_admission.mapping_policy",
    )
    _strict_match(
        value["aws_reference_boundary"],
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
        "provider_neutral_foundation_admission.aws_reference_boundary",
    )
    _strict_match(
        value["evidence_equivalence_policy"],
        {
            "identical_security_evidence": "REQUIRED",
            "identical_operations_evidence": "REQUIRED",
            "identical_release_evidence": "REQUIRED",
            "identical_backup_restore_evidence": "REQUIRED",
            "identical_region_residency_evidence": "REQUIRED",
            "provider_label_as_evidence": "FORBIDDEN",
            "reference_metadata_as_evidence": "FORBIDDEN",
            "local_test_as_live_evidence": "FORBIDDEN",
        },
        "provider_neutral_foundation_admission.evidence_equivalence_policy",
    )

    rows = _list(
        value["capability_mapping_requirements"],
        "provider_neutral_foundation_admission.capability_mapping_requirements",
    )
    row_mappings = [
        _mapping(
            row,
            "provider_neutral_foundation_admission.capability_mapping_requirements.item",
        )
        for row in rows
    ]
    capability_ids = [row.get("capability_id") for row in row_mappings]
    if any(
        type(capability_id) is not str
        or capability_id not in REQUIRED_FOUNDATION_CAPABILITY_IDS
        for capability_id in capability_ids
    ):
        _fail("UNKNOWN_CAPABILITY_MAPPING", "foundation_capability_mapping")
    if len(set(capability_ids)) != len(capability_ids):
        _fail("DUPLICATE_CAPABILITY_MAPPING", "foundation_capability_mapping")
    if len(capability_ids) != len(REQUIRED_FOUNDATION_CAPABILITY_IDS) or any(
        capability_id not in capability_ids
        for capability_id in REQUIRED_FOUNDATION_CAPABILITY_IDS
    ):
        _fail("MISSING_CAPABILITY_MAPPING", "foundation_capability_mapping")
    if tuple(capability_ids) != REQUIRED_FOUNDATION_CAPABILITY_IDS:
        _fail("CAPABILITY_MAPPING_ORDER_DRIFT", "foundation_capability_mapping")
    for row, (capability_id, required_outcome) in zip(
        row_mappings, FOUNDATION_CAPABILITY_OUTCOMES, strict=True
    ):
        _exact_keys(
            row,
            {
                "capability_id",
                "required_outcome",
                "selected_mapping",
                "evidence_refs",
                "mapping_status",
            },
            "provider_neutral_foundation_admission.capability_mapping",
        )
        _string(
            row["capability_id"],
            capability_id,
            "provider_neutral_foundation_admission.capability_id",
        )
        _string(
            row["required_outcome"],
            required_outcome,
            "provider_neutral_foundation_admission.required_outcome",
        )
        _unset(
            row["selected_mapping"],
            "provider_neutral_foundation_admission.selected_mapping",
        )
        _empty_list(
            row["evidence_refs"],
            "provider_neutral_foundation_admission.evidence_refs",
        )
        _string(
            row["mapping_status"],
            "REQUIRED_NOT_CONFIGURED",
            "provider_neutral_foundation_admission.mapping_status",
        )
    return ProviderNeutralFoundationAdmission(definition=copy.deepcopy(dict(value)))


def _parse_selection(contract: Mapping[str, Any]) -> SelectedConfiguration:
    value = _mapping(contract["selected_configuration"], "selected_configuration")
    _exact_keys(value, SELECTION_KEYS, "selected_configuration")
    for field in NULL_SELECTION_FIELDS:
        _unset(value[field], f"selected_configuration.{field}")
    empty = {
        field: _empty_list(value[field], f"selected_configuration.{field}")
        for field in EMPTY_SELECTION_FIELDS
    }
    return SelectedConfiguration(
        cloud_provider=None,
        production_region=None,
        backup_region=None,
        development_account_id=None,
        production_account_id=None,
        terraform_cli_version=None,
        provider_plugins=empty["provider_plugins"],
        state_backend=None,
        credential_source=None,
        network_cidrs=empty["network_cidrs"],
        availability_zones=empty["availability_zones"],
        kms_key_reference=None,
        monthly_budget_jpy=None,
        resource_definitions=empty["resource_definitions"],
    )


def _parse_execution(contract: Mapping[str, Any]) -> ExecutionBoundary:
    value = _mapping(contract["execution_boundary"], "execution_boundary")
    _exact_keys(
        value,
        {
            "activation_enabled",
            "activation_status",
            "native_plan_status",
            "network_access",
            "credential_access",
            "live_provider_calls",
            "external_writes",
            "deploy_action",
            "release_action",
            "production_action",
            "commands",
            "planned_actions",
        },
        "execution_boundary",
    )
    commands = _mapping(value["commands"], "execution_boundary.commands")
    _exact_keys(commands, set(NATIVE_COMMANDS), "execution_boundary.commands")
    parsed_commands = tuple(
        (
            command,
            _string(
                commands[command],
                "FORBIDDEN",
                f"execution_boundary.commands.{command}",
            ),
        )
        for command in NATIVE_COMMANDS
    )
    actions = _mapping(value["planned_actions"], "execution_boundary.planned_actions")
    _exact_keys(actions, set(ACTION_NAMES), "execution_boundary.planned_actions")
    parsed_actions = tuple(
        (
            action,
            _integer(
                actions[action], 0, f"execution_boundary.planned_actions.{action}"
            ),
        )
        for action in ACTION_NAMES
    )
    return ExecutionBoundary(
        activation_enabled=_boolean(
            value["activation_enabled"],
            False,
            "execution_boundary.activation_enabled",
        ),
        activation_status=_string(
            value["activation_status"],
            "DISABLED",
            "execution_boundary.activation_status",
        ),
        native_plan_status=_string(
            value["native_plan_status"],
            "NOT_EXECUTED",
            "execution_boundary.native_plan_status",
        ),
        network_access=_string(
            value["network_access"],
            "FORBIDDEN",
            "execution_boundary.network_access",
        ),
        credential_access=_string(
            value["credential_access"],
            "FORBIDDEN",
            "execution_boundary.credential_access",
        ),
        live_provider_calls=_string(
            value["live_provider_calls"],
            "FORBIDDEN",
            "execution_boundary.live_provider_calls",
        ),
        external_writes=_string(
            value["external_writes"],
            "FORBIDDEN",
            "execution_boundary.external_writes",
        ),
        deploy_action=_string(
            value["deploy_action"],
            "FORBIDDEN",
            "execution_boundary.deploy_action",
        ),
        release_action=_string(
            value["release_action"],
            "FORBIDDEN",
            "execution_boundary.release_action",
        ),
        production_action=_string(
            value["production_action"],
            "FORBIDDEN",
            "execution_boundary.production_action",
        ),
        commands=parsed_commands,
        planned_actions=parsed_actions,
    )


def _parse_state(contract: Mapping[str, Any]) -> StateRequirements:
    value = _mapping(contract["state_requirements"], "state_requirements")
    _exact_keys(
        value,
        {
            "encryption",
            "locking",
            "audit_logging",
            "backup_and_restore",
            "selected_backend",
        },
        "state_requirements",
    )
    _unset(value["selected_backend"], "state_requirements.selected_backend")
    return StateRequirements(
        encryption=_string(
            value["encryption"],
            "REQUIRED_NOT_CONFIGURED",
            "state_requirements.encryption",
        ),
        locking=_string(
            value["locking"],
            "REQUIRED_NOT_CONFIGURED",
            "state_requirements.locking",
        ),
        audit_logging=_string(
            value["audit_logging"],
            "REQUIRED_NOT_CONFIGURED",
            "state_requirements.audit_logging",
        ),
        backup_and_restore=_string(
            value["backup_and_restore"],
            "REQUIRED_NOT_CONFIGURED",
            "state_requirements.backup_and_restore",
        ),
        selected_backend=None,
    )


def _parse_accounts(contract: Mapping[str, Any]) -> AccountRequirements:
    value = _mapping(contract["account_requirements"], "account_requirements")
    _exact_keys(
        value,
        {
            "separate_development_and_production",
            "development_account_id",
            "production_account_id",
        },
        "account_requirements",
    )
    _unset(
        value["development_account_id"], "account_requirements.development_account_id"
    )
    _unset(value["production_account_id"], "account_requirements.production_account_id")
    return AccountRequirements(
        separate_development_and_production=_string(
            value["separate_development_and_production"],
            "REQUIRED",
            "account_requirements.separate_development_and_production",
        ),
        development_account_id=None,
        production_account_id=None,
    )


def _parse_production(contract: Mapping[str, Any]) -> ProductionChangeRequirements:
    value = _mapping(
        contract["production_change_requirements"],
        "production_change_requirements",
    )
    expected = {
        "iac_only": "REQUIRED",
        "human_approval": "REQUIRED",
        "drift_detection": "REQUIRED_NOT_CONFIGURED",
        "manual_change": "FORBIDDEN",
        "od_013_status": "HUMAN_DECISION_REQUIRED",
        "production_apply": "FORBIDDEN",
    }
    _exact_keys(value, set(expected), "production_change_requirements")
    parsed = {
        field: _string(
            value[field], expected_value, f"production_change_requirements.{field}"
        )
        for field, expected_value in expected.items()
    }
    return ProductionChangeRequirements(**parsed)


def _parse_extension(contract: Mapping[str, Any]) -> ExtensionContract:
    value = _mapping(contract["extension_contract"], "extension_contract")
    _exact_keys(
        value,
        {
            "current_resource_payloads",
            "successor_contract_revision_required",
            "native_toolchain_pin_required_before_hcl",
            "successors",
        },
        "extension_contract",
    )
    successors = _mapping(value["successors"], "extension_contract.successors")
    expected_successors = {"ST-1502": "DATA_SERVICES", "ST-1503": "COMPUTE_CDN_WAF"}
    _exact_keys(successors, set(expected_successors), "extension_contract.successors")
    parsed_successors = tuple(
        (
            story,
            _string(successors[story], role, f"extension_contract.successors.{story}"),
        )
        for story, role in expected_successors.items()
    )
    return ExtensionContract(
        current_resource_payloads=_string(
            value["current_resource_payloads"],
            "FORBIDDEN",
            "extension_contract.current_resource_payloads",
        ),
        successor_contract_revision_required=_boolean(
            value["successor_contract_revision_required"],
            True,
            "extension_contract.successor_contract_revision_required",
        ),
        native_toolchain_pin_required_before_hcl=_boolean(
            value["native_toolchain_pin_required_before_hcl"],
            True,
            "extension_contract.native_toolchain_pin_required_before_hcl",
        ),
        successors=parsed_successors,
    )


def _parse_evidence(contract: Mapping[str, Any]) -> EvidenceBoundary:
    value = _mapping(contract["evidence_boundary"], "evidence_boundary")
    expected = {
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
    }
    _exact_keys(value, set(expected), "evidence_boundary")
    parsed = {
        field: _string(value[field], expected_value, f"evidence_boundary.{field}")
        for field, expected_value in expected.items()
    }
    return EvidenceBoundary(**parsed)


def validate_contract(contract: object, root: Path = REPO_ROOT) -> FoundationModel:
    value = _mapping(contract, "contract")
    _exact_keys(value, TOP_LEVEL_KEYS, "contract")
    document = _mapping(value["document"], "document")
    _exact_keys(document, set(EXPECTED_DOCUMENT), "document")
    for field, expected in EXPECTED_DOCUMENT.items():
        _string(document[field], expected, f"document.{field}")

    _validate_sources(value, root)
    _validate_authority_semantics(root)
    return FoundationModel(
        reference=_parse_reference(value),
        admission=_parse_provider_neutral_admission(value),
        selection=_parse_selection(value),
        execution=_parse_execution(value),
        state=_parse_state(value),
        accounts=_parse_accounts(value),
        production=_parse_production(value),
        extension=_parse_extension(value),
        evidence=_parse_evidence(value),
    )


def load_and_validate_contract(root: Path = REPO_ROOT) -> FoundationModel:
    contract_path = _repository_regular_file(root, CONTRACT_PATH, "contract")
    return validate_contract(load_yaml(contract_path), root)


def _selection_document(selection: SelectedConfiguration) -> dict[str, object]:
    return {
        "cloud_provider": selection.cloud_provider,
        "production_region": selection.production_region,
        "backup_region": selection.backup_region,
        "development_account_id": selection.development_account_id,
        "production_account_id": selection.production_account_id,
        "terraform_cli_version": selection.terraform_cli_version,
        "provider_plugins": list(selection.provider_plugins),
        "state_backend": selection.state_backend,
        "credential_source": selection.credential_source,
        "network_cidrs": list(selection.network_cidrs),
        "availability_zones": list(selection.availability_zones),
        "kms_key_reference": selection.kms_key_reference,
        "monthly_budget_jpy": selection.monthly_budget_jpy,
        "resource_definitions": list(selection.resource_definitions),
    }


def reference_plan_document(model: FoundationModel) -> dict[str, object]:
    return {
        "document": {
            "id": "RAOS-TERRAFORM-FOUNDATION-REFERENCE-PLAN-001",
            "version": "1.1.0",
            "story_id": "ST-1501",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": model.evidence.deliverable_classification,
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "reference_architecture": {
            "cloud": model.reference.cloud,
            "region": model.reference.region,
            "classification": model.reference.classification,
            "inherited_from": model.reference.inherited_from,
            "portable_core_required": model.reference.portable_core_required,
            "default": model.reference.default,
            "implicit_fallback": model.reference.implicit_fallback,
            "selected_binding": model.reference.selected_binding,
            "eligibility_shortcut": model.reference.eligibility_shortcut,
            "admission_requirement": model.reference.admission_requirement,
            "evidence_substitute": model.reference.evidence_substitute,
        },
        "provider_neutral_foundation_admission": copy.deepcopy(
            model.admission.definition
        ),
        "selected_configuration": _selection_document(model.selection),
        "planned_actions": dict(model.execution.planned_actions),
        "activation": {
            "enabled": model.execution.activation_enabled,
            "status": model.execution.activation_status,
            "native_plan_status": model.execution.native_plan_status,
            "network_access": model.execution.network_access,
            "credential_access": model.execution.credential_access,
            "live_provider_calls": model.execution.live_provider_calls,
            "external_writes": model.execution.external_writes,
            "deploy_action": model.execution.deploy_action,
            "release_action": model.execution.release_action,
            "production_action": model.execution.production_action,
            "native_commands": dict(model.execution.commands),
        },
        "future_requirements": {
            "remote_state": {
                "encryption": model.state.encryption,
                "locking": model.state.locking,
                "audit_logging": model.state.audit_logging,
                "backup_and_restore": model.state.backup_and_restore,
                "selected_backend": model.state.selected_backend,
            },
            "account_separation": {
                "requirement": model.accounts.separate_development_and_production,
                "development_account_id": model.accounts.development_account_id,
                "production_account_id": model.accounts.production_account_id,
            },
            "production_change_control": {
                "iac_only": model.production.iac_only,
                "human_approval": model.production.human_approval,
                "drift_detection": model.production.drift_detection,
                "manual_change": model.production.manual_change,
                "od_013_status": model.production.od_013_status,
                "production_apply": model.production.production_apply,
            },
        },
        "extension_contract": {
            "current_resource_payloads": model.extension.current_resource_payloads,
            "successor_contract_revision_required": (
                model.extension.successor_contract_revision_required
            ),
            "native_toolchain_pin_required_before_hcl": (
                model.extension.native_toolchain_pin_required_before_hcl
            ),
            "successors": dict(model.extension.successors),
        },
        "verification_boundary": {
            "executable_terraform": model.evidence.executable_terraform,
            "terraform_cli": model.evidence.terraform_cli,
            "provider_plugins": model.evidence.provider_plugins,
            "remote_state": model.evidence.remote_state,
            "provider_account_or_project": (model.evidence.provider_account_or_project),
            "credentials": model.evidence.credentials,
            "formal_tst_026": model.evidence.formal_tst_026,
            "live_staging_release_production": (
                model.evidence.live_staging_release_production
            ),
            "effective_canonical_status": model.evidence.effective_canonical_status,
        },
    }


def render_reference_plan(model: FoundationModel) -> bytes:
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
    model: FoundationModel, reference_plan: bytes, root: Path = REPO_ROOT
) -> bytes:
    source_artifacts = [
        _artifact_row(root, relative) for relative in SOURCE_ARTIFACT_PATHS
    ]
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-TERRAFORM-FOUNDATION-MANIFEST-001",
            "version": "1.1.0",
            "story_id": "ST-1501",
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
                for relative, digest in PINNED_SOURCES.items()
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
            "classification": model.evidence.deliverable_classification,
            "provider_policy": model.admission.definition["classification"],
            "admission_status": model.admission.definition["admission_status"],
            "eligible": model.admission.definition["eligible"],
            "selected_profile": model.admission.definition["selected_profile_id"],
            "default_profile": model.admission.definition["default_profile_id"],
            "fallback_profile": model.admission.definition["fallback_profile_id"],
            "required_capability_count": len(REQUIRED_FOUNDATION_CAPABILITY_IDS),
            "configured_mapping_count": 0,
            "aws_reference_role": model.admission.definition["aws_reference_boundary"][
                "role"
            ],
            "canonical_story_deliverables": model.admission.definition[
                "aws_reference_boundary"
            ]["canonical_story_deliverables"],
            "portable_implementation_paths": model.admission.definition[
                "aws_reference_boundary"
            ]["non_aws_owner_managed_profiles"],
            "aws_reference_default": False,
            "aws_reference_fallback": False,
            "aws_reference_selected": False,
            "aws_reference_eligibility_shortcut": False,
            "aws_reference_admission_requirement": False,
            "aws_reference_evidence_substitute": False,
            "activation": model.execution.activation_status,
            "planned_actions": dict(model.execution.planned_actions),
            "selected_cloud_provider": model.selection.cloud_provider,
            "selected_production_region": model.selection.production_region,
            "selected_production_account": model.selection.production_account_id,
            "selected_state_backend": model.selection.state_backend,
            "credentials": model.evidence.credentials,
            "provider_account_or_project": (model.evidence.provider_account_or_project),
            "resource_definitions": list(model.selection.resource_definitions),
            "native_iac_validation": "NOT_EXECUTED",
            "formal_tst_026": model.evidence.formal_tst_026,
            "effective_canonical_status": model.evidence.effective_canonical_status,
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
        description="Build the disabled ST-1501 reference-only foundation artifacts."
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
    except FoundationContractError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-1501 foundation check passed")
    else:
        print("ST-1501 foundation artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
