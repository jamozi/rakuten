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
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


def _lexical_repository_root(script_path: str | os.PathLike[str]) -> Path:
    """Bind the invocation path without following any repository symlink."""

    return Path(os.path.abspath(os.fspath(script_path))).parents[1]


REPO_ROOT: Final = _lexical_repository_root(__file__)
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONTRACT_PATH: Final = Path(
    "changes/st-1506/contracts/production-deployment-definition.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "infra/terraform/deployment-production/production-deployment.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1506/manifest.yaml")
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HANDOFF_PATH: Final = Path(
    "changes/st-1506/"
    "DESIGN_HANDOFF_V1_ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1.yaml"
)
APPROVAL_PATH: Final = Path(
    "changes/st-1506/"
    "DESIGN-HANDOFF-APPROVAL-WORDPRESS-SIGNED-DELIVERY-INTERFACE-v1.yaml"
)
WORKLOG_PATH: Final = Path("docs/worklogs/ST-1506.md")

SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = "repo://scripts/build_st1506_production_deployment.py"
HANDOFF_URI: Final = f"repo://{HANDOFF_PATH.as_posix()}"
APPROVAL_URI: Final = f"repo://{APPROVAL_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1506_production_deployment.py"
)
HANDOFF_BYTES: Final = 30_568
HANDOFF_SHA256: Final = (
    "7973f7d4dca452da3325ecbfbd78d34faf6acdcd7d931de6d314ee2ef4a1acb3"
)
APPROVAL_BYTES: Final = 2_298
APPROVAL_SHA256: Final = (
    "89a8d77ca319a51d38bf7662c4d7a38763b13f66e5a33176ecaf93e598fd25bb"
)
EXPECTED_HANDOFF_OBJECT_FINGERPRINT: Final = (
    "02a87ef1d840a88ffe16f0349733e9a168154f4e781a838ff24399bffa785205"
)
EXPECTED_APPROVAL_OBJECT_FINGERPRINT: Final = (
    "280f1a897eca354274245f4294ee62aef6f153dab59636c8e8704bfef26ed4b3"
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
        "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b"
    ),
}
PREDECESSOR_SOURCES: Final = {
    "changes/st-1505/contracts/staging-deployment.v1.yaml": (
        "1fc7aeb4fc21add4401bed21f767da135b240091bf8440d15185b1ee82c808e2"
    ),
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json": (
        "33ac838087edededb2ab389d87a4e7c2f0d0bab9e66dc19d40689db827265a7f"
    ),
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
IMPLEMENTATION_AUTHORITY_SOURCES: Final = {
    HANDOFF_PATH.as_posix(): HANDOFF_SHA256,
    APPROVAL_PATH.as_posix(): APPROVAL_SHA256,
}
PINNED_SOURCES: Final = {
    **AUTHORITY_SOURCES,
    **IMPLEMENTATION_AUTHORITY_SOURCES,
    **PREDECESSOR_SOURCES,
}

SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    HANDOFF_PATH,
    APPROVAL_PATH,
    Path("changes/st-1506/README.md"),
    Path("scripts/build_st1506_production_deployment.py"),
    Path("tests/st1506/conftest.py"),
    Path("tests/st1506/test_contract.py"),
    Path("tests/st1506/test_generation.py"),
    Path("tests/st1506/test_negative_cases.py"),
    WORKLOG_PATH,
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
    "predecessor_binding",
    "open_decision_defaults",
    "environment_boundary",
    "selected_bindings",
    "human_approval_gates",
    "artifact_admission_intent",
    "protected_environment_intent",
    "migration_intent",
    "canary_intent",
    "observability_intent",
    "health_and_smoke_intent",
    "rollback_intent",
    "logical_phases",
    "execution_boundary",
    "evidence_boundary",
    "wordpress_signed_delivery_interface",
)
WORDPRESS_INTERFACE_KEYS: Final = (
    "interface_status",
    "trust_bootstrap",
    "canonical_encoding",
    "keyring",
    "release_set",
    "components",
    "package_admission",
    "replay_and_journal",
    "transaction_state_machine",
    "wordpress_filesystem",
    "health_and_restore",
    "authorization",
    "availability",
    "automatic_delivery_classification",
    "receipts",
    "control_plane_separation",
    "evidence_boundary",
)
EXPECTED_HANDOFF_KEYS: Final = (
    "document_version",
    "proposal_status",
    "authority",
    "approved_story",
    "approved_scope",
    "source_design_refs",
    "pro_advice_binding",
    "decision",
    "rationale",
    "rejected_alternatives",
    "constraints",
    "security_and_approval_gates",
    "acceptance_criteria",
    "required_test_evidence",
    "inherited_open_decisions",
    "open_decisions",
    "approval",
)
EXPECTED_OWNED_PATHS: Final = (
    HANDOFF_PATH.as_posix(),
    APPROVAL_PATH.as_posix(),
    "changes/st-1506/README.md",
    CONTRACT_PATH.as_posix(),
    MANIFEST_PATH.as_posix(),
    REFERENCE_PLAN_PATH.as_posix(),
    "scripts/build_st1506_production_deployment.py",
    "tests/st1506/test_contract.py",
    "tests/st1506/test_generation.py",
    "tests/st1506/test_negative_cases.py",
    WORKLOG_PATH.as_posix(),
)
HANDOFF_SOURCE_REF_COUNT: Final = 22
HANDOFF_LIVE_REPOSITORY_REF_COUNT: Final = 13
PHASE_NAMES: Final = ("CANARY", "OBSERVE", "ROLLBACK")
ACTION_COUNT_NAMES: Final = (
    "create",
    "update",
    "delete",
    "promote",
    "deploy",
    "migrate",
    "traffic",
    "canary",
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
    "4df983411ed0df97d66e4ee074faf82e0d3da60a59d3b789e27c60cbbce87d6a"
)
EXPECTED_ST1505_CONTRACT_FINGERPRINT: Final = (
    "d930e38a8b5b74a7fc8230b6edea4fcfea240080eaaf9623d6f4a0068d9bebe3"
)
ST1505_ACTION_COUNT_NAMES: Final = (
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
MAX_DOCUMENT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 64 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
YAML_PARSE_ERRORS: Final = (UnicodeError, yaml.YAMLError)
JSON_PARSE_ERRORS: Final = (UnicodeError, json.JSONDecodeError)
OBJECT_FINGERPRINT_ERRORS: Final = (TypeError, ValueError)


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
    if any(
        key_node.tag == "tag:yaml.org,2002:merge"
        for key_node, _value_node in node.value
    ):
        raise ConstructorError(
            "while constructing a mapping",
            node.start_mark,
            "found forbidden merge key",
            node.start_mark,
        )
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
    approved_preimplementation_inputs: tuple[Mapping[str, Any], ...]
    source_artifact_contents: tuple[tuple[Path, bytes], ...]


@dataclass(frozen=True, slots=True)
class ImplementationAuthorityModel:
    """Exact detached authority material used to derive the additive section."""

    wordpress_interface: Mapping[str, Any]
    source_design_refs: tuple[Mapping[str, Any], ...]
    validated_contents: tuple[tuple[str, bytes], ...]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(
        _read_bounded_regular_file(
            path,
            "sha256_source",
            max_bytes=MAX_DOCUMENT_BYTES,
            size_error_code="FILE_SIZE_LIMIT",
        )
    )


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


def _strict_ordered_match(actual: object, expected: object, field: str) -> None:
    """Match a closed value while treating every mapping order as contract data."""

    if isinstance(expected, Mapping):
        value = _mapping(actual, field)
        expected_mapping = _mapping(expected, field)
        if tuple(value) != tuple(expected_mapping):
            _fail("CLOSED_SCHEMA_VIOLATION", field)
        for key, expected_value in expected_mapping.items():
            _strict_ordered_match(value[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        value_list = _list(actual, field)
        expected_list = _list(expected, field)
        if len(value_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_ordered_match(value_list[index], expected_value, f"{field}.item")
        return
    _strict_match(actual, expected, field)


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


def _read_bounded_descriptor(
    descriptor: int,
    field: str,
    *,
    max_bytes: int,
    size_error_code: str,
) -> bytes:
    before = os.fstat(descriptor)
    if not stat.S_ISREG(before.st_mode):
        _fail("UNSAFE_FILE_TYPE", field)
    if before.st_size < 0 or before.st_size > max_bytes:
        _fail(size_error_code, field)

    chunks: list[bytes] = []
    total = 0
    while True:
        remaining = max_bytes + 1 - total
        if remaining <= 0:
            _fail(size_error_code, field)
        chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_bytes:
            _fail(size_error_code, field)

    after = os.fstat(descriptor)
    identity_before = (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )
    identity_after = (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )
    if identity_before != identity_after or total != before.st_size:
        _fail("FILE_CHANGED_DURING_READ", field)
    return b"".join(chunks)


def _validate_relative_path(relative: Path, field: str, path_error_code: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail(path_error_code, field)


def _absolute_lexical_path(path: Path, field: str) -> Path:
    absolute = path if path.is_absolute() else Path.cwd() / path
    if any(part in {"", ".", ".."} for part in absolute.parts[1:]):
        _fail("UNSAFE_ROOT_TYPE", field)
    return absolute


def _required_safe_io_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        _fail("UNSUPPORTED_SAFE_IO", "filesystem")
    return value


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _close_descriptors(descriptors: list[int]) -> None:
    while descriptors:
        _close_descriptor(descriptors.pop())


def _open_physical_directory(root: Path, field: str) -> int:
    absolute = _absolute_lexical_path(root, field)
    directory_flags = (
        os.O_RDONLY
        | _required_safe_io_flag("O_CLOEXEC")
        | _required_safe_io_flag("O_DIRECTORY")
        | _required_safe_io_flag("O_NOFOLLOW")
    )
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, directory_flags))
        for part in absolute.parts[1:]:
            try:
                child = os.open(part, directory_flags, dir_fd=descriptors[-1])
            except FileNotFoundError:
                _fail("ROOT_UNAVAILABLE", field)
            except OSError:
                _fail("UNSAFE_ROOT_TYPE", field)
            descriptors.append(child)
        return descriptors.pop()
    except ProductionDeploymentContractError:
        raise
    except OSError:
        _fail("ROOT_UNAVAILABLE", field)
    finally:
        _close_descriptors(descriptors)


def _read_repository_file(
    root: Path,
    relative: Path,
    field: str,
    *,
    max_bytes: int,
    size_error_code: str,
    path_error_code: str = "UNSAFE_REPOSITORY_PATH",
    missing_error_code: str = "FILE_UNAVAILABLE",
    ancestor_error_code: str = "UNSAFE_ANCESTOR",
    file_type_error_code: str = "UNSAFE_FILE_TYPE",
) -> bytes:
    _validate_relative_path(relative, field, path_error_code)
    directory_flags = (
        os.O_RDONLY
        | _required_safe_io_flag("O_CLOEXEC")
        | _required_safe_io_flag("O_DIRECTORY")
        | _required_safe_io_flag("O_NOFOLLOW")
    )
    file_flags = (
        os.O_RDONLY
        | _required_safe_io_flag("O_CLOEXEC")
        | _required_safe_io_flag("O_NOFOLLOW")
        | _required_safe_io_flag("O_NONBLOCK")
    )
    directories = [_open_physical_directory(root, field)]
    descriptor = -1
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            except FileNotFoundError:
                _fail(missing_error_code, field)
            except OSError:
                _fail(ancestor_error_code, field)
            directories.append(child)
        try:
            descriptor = os.open(relative.name, file_flags, dir_fd=directories[-1])
        except FileNotFoundError:
            _fail(missing_error_code, field)
        except OSError:
            _fail(file_type_error_code, field)
        return _read_bounded_descriptor(
            descriptor,
            field,
            max_bytes=max_bytes,
            size_error_code=size_error_code,
        )
    except ProductionDeploymentContractError:
        raise
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor)
        _close_descriptors(directories)


def _read_bounded_regular_file(
    path: Path,
    field: str,
    *,
    max_bytes: int,
    size_error_code: str,
) -> bytes:
    absolute = _absolute_lexical_path(path, field)
    return _read_repository_file(
        Path(os.path.sep),
        Path(*absolute.parts[1:]),
        field,
        max_bytes=max_bytes,
        size_error_code=size_error_code,
    )


def _parse_yaml_bytes(content: bytes, field: str) -> Any:
    if len(content) > MAX_DOCUMENT_BYTES:
        _fail("YAML_SIZE_LIMIT", field)
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", field)
            if isinstance(token, TagToken):
                _fail("YAML_TAG_FORBIDDEN", field)
        return yaml.load(text, Loader=UniqueKeyLoader)
    except ProductionDeploymentContractError:
        raise
    except YAML_PARSE_ERRORS:
        _fail("YAML_INVALID", field)


def load_yaml(path: Path) -> Any:
    content = _read_bounded_regular_file(
        path,
        "yaml",
        max_bytes=MAX_DOCUMENT_BYTES,
        size_error_code="YAML_SIZE_LIMIT",
    )
    return _parse_yaml_bytes(content, "yaml")


def load_json(path: Path) -> Any:
    content = _read_bounded_regular_file(
        path,
        "json",
        max_bytes=MAX_DOCUMENT_BYTES,
        size_error_code="JSON_SIZE_LIMIT",
    )

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
    except JSON_PARSE_ERRORS:
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


def _load_exact_authority_document(
    root: Path,
    relative: Path,
    *,
    expected_bytes: int,
    expected_sha256: str,
    root_key: str,
    field: str,
) -> tuple[Mapping[str, Any], bytes]:
    content = _read_repository_file(
        root,
        relative,
        field,
        max_bytes=expected_bytes,
        size_error_code="IMPLEMENTATION_AUTHORITY_BYTES_MISMATCH",
    )
    if len(content) != expected_bytes or sha256_bytes(content) != expected_sha256:
        _fail("IMPLEMENTATION_AUTHORITY_BYTES_MISMATCH", field)
    document = _mapping(_parse_yaml_bytes(content, field), field)
    if tuple(document) != (root_key,):
        _fail("IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT", field)
    return document, content


def _validate_implementation_authority(root: Path) -> ImplementationAuthorityModel:
    handoff_document, handoff_content = _load_exact_authority_document(
        root,
        HANDOFF_PATH,
        expected_bytes=HANDOFF_BYTES,
        expected_sha256=HANDOFF_SHA256,
        root_key="DESIGN_HANDOFF_V1",
        field="implementation_handoff",
    )
    if _object_fingerprint(handoff_document) != EXPECTED_HANDOFF_OBJECT_FINGERPRINT:
        _fail("IMPLEMENTATION_HANDOFF_SEMANTIC_DRIFT", "implementation_handoff")
    handoff = _mapping(handoff_document["DESIGN_HANDOFF_V1"], "implementation_handoff")
    if tuple(handoff) != EXPECTED_HANDOFF_KEYS:
        _fail("IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT", "implementation_handoff")
    _strict_match(handoff.get("document_version"), 1, "implementation_handoff.version")
    _strict_match(
        handoff.get("approved_story"), "ST-1506", "implementation_handoff.story"
    )
    _strict_match(
        handoff.get("open_decisions"), [], "implementation_handoff.open_decisions"
    )

    source_refs = _list(
        handoff.get("source_design_refs"), "implementation_handoff.source_refs"
    )
    if len(source_refs) != HANDOFF_SOURCE_REF_COUNT:
        _fail(
            "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
            "implementation_handoff.source_refs",
        )
    validated_contents: dict[str, bytes] = {
        HANDOFF_PATH.as_posix(): handoff_content,
    }
    for index, raw_row in enumerate(source_refs[:HANDOFF_LIVE_REPOSITORY_REF_COUNT]):
        row = _mapping(raw_row, "implementation_handoff.source_refs.item")
        if tuple(row) != ("uri", "bytes", "sha256"):
            _fail(
                "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
                "implementation_handoff.source_refs.item",
            )
        relative = _repo_relative_uri(row.get("uri"))
        expected_size = row.get("bytes")
        expected_digest = row.get("sha256")
        if type(expected_size) is not int or expected_size < 0:
            _fail(
                "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
                "implementation_handoff.source_refs.item",
            )
        if (
            type(expected_digest) is not str
            or SHA256_PATTERN.fullmatch(expected_digest) is None
        ):
            _fail(
                "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
                "implementation_handoff.source_refs.item",
            )
        content = _read_repository_file(
            root,
            relative,
            f"implementation_handoff.live_source_{index}",
            max_bytes=expected_size,
            size_error_code="IMPLEMENTATION_HANDOFF_SOURCE_DRIFT",
        )
        if len(content) != expected_size or sha256_bytes(content) != expected_digest:
            _fail(
                "IMPLEMENTATION_HANDOFF_SOURCE_DRIFT",
                "implementation_handoff.live_source",
            )
        validated_contents[relative.as_posix()] = content
    for raw_row in source_refs[
        HANDOFF_LIVE_REPOSITORY_REF_COUNT : HANDOFF_LIVE_REPOSITORY_REF_COUNT + 6
    ]:
        row = _mapping(raw_row, "implementation_handoff.preimplementation_source")
        if tuple(row) != ("uri", "bytes", "sha256"):
            _fail(
                "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
                "implementation_handoff.preimplementation_source",
            )
        _repo_relative_uri(row.get("uri"))
    for raw_row in source_refs[-3:]:
        row = _mapping(raw_row, "implementation_handoff.official_source")
        if tuple(row) != (
            "uri",
            "retrieved_at",
            "evidence_class",
            "relevant_fact",
        ):
            _fail(
                "IMPLEMENTATION_AUTHORITY_SCHEMA_DRIFT",
                "implementation_handoff.official_source",
            )

    pro_binding = _mapping(
        handoff.get("pro_advice_binding"), "implementation_handoff.pro_binding"
    )
    _strict_match(
        pro_binding,
        {
            "run_id": "20260814T190431Z-f766cd4f5994",
            "importance": "gated",
            "status": "CONVERGED_NO_OPEN_GAP",
            "advice_type": "PRO_ADVICE_V1",
            "recommendation": "REVISE",
            "material_delta": True,
            "authority": "UNAPPROVED_ADVICE",
            "provenance": "HUMAN_COPIED_DISPLAYED_RESPONSE",
            "resubmitted": False,
            "response_sha256": (
                "fca5a6fa7370f4f082a5c353fd919ba57845c1a0af83a7ab0067a85bec48eb5c"
            ),
            "proposal_sha256": (
                "1164c2583a586bba79ca48f5c4115e9b847d258d92cf068a3496da551805ec62"
            ),
            "reconciliation": (
                "ACCEPTED_AS_ADVISORY_INPUT_ONLY_AFTER_CANONICAL_AND_LOCAL_REVIEW"
            ),
        },
        "implementation_handoff.pro_binding",
    )
    decision = _mapping(handoff.get("decision"), "implementation_handoff.decision")
    _strict_match(
        decision.get("base"),
        {
            "commit": "8c8b9c4567392886f086d3dd69506619e5a83344",
            "tree": "7f8a0f7c0d84282b2824c135f78a708a1cd1ed00",
            "source_ref": "origin/main",
            "worktree_branch": "codex/st-1506-wordpress-signed-delivery-interface-v1",
        },
        "implementation_handoff.base",
    )
    contract_revision = _mapping(
        decision.get("contract_revision"), "implementation_handoff.contract_revision"
    )
    _strict_match(
        contract_revision,
        {
            "source_path": CONTRACT_PATH.as_posix(),
            "current_version": "1.0.0",
            "proposed_version": "1.1.0",
            "compatibility": (
                "ADDITIVE_STRICT_SCHEMA_REVISION_WITH_EXACT_OWNER_APPROVAL"
            ),
            "new_top_level_section": "wordpress_signed_delivery_interface",
            "generated_projection_path": REFERENCE_PLAN_PATH.as_posix(),
            "generator_path": "scripts/build_st1506_production_deployment.py",
            "generated_files_hand_edited": False,
        },
        "implementation_handoff.contract_revision",
    )
    constraints = _mapping(
        handoff.get("constraints"), "implementation_handoff.constraints"
    )
    _strict_match(
        constraints.get("exact_owned_paths"),
        list(EXPECTED_OWNED_PATHS),
        "implementation_handoff.owned_paths",
    )
    _strict_match(
        constraints.get("exact_story_id"),
        "ST-1506",
        "implementation_handoff.story_id",
    )

    approval_document, approval_content = _load_exact_authority_document(
        root,
        APPROVAL_PATH,
        expected_bytes=APPROVAL_BYTES,
        expected_sha256=APPROVAL_SHA256,
        root_key="DESIGN_HANDOFF_APPROVAL_V1",
        field="implementation_approval",
    )
    if _object_fingerprint(approval_document) != EXPECTED_APPROVAL_OBJECT_FINGERPRINT:
        _fail("IMPLEMENTATION_APPROVAL_SEMANTIC_DRIFT", "implementation_approval")
    validated_contents[APPROVAL_PATH.as_posix()] = approval_content
    approval = _mapping(
        approval_document["DESIGN_HANDOFF_APPROVAL_V1"], "implementation_approval"
    )
    _strict_match(approval.get("story_id"), "ST-1506", "implementation_approval.story")
    _strict_match(
        approval.get("handoff_uri"), HANDOFF_URI, "implementation_approval.uri"
    )
    _strict_match(
        approval.get("handoff_bytes"), HANDOFF_BYTES, "implementation_approval.bytes"
    )
    _strict_match(
        approval.get("handoff_sha256"),
        HANDOFF_SHA256,
        "implementation_approval.sha256",
    )
    _strict_match(
        approval.get("status"),
        "APPROVED_FOR_IMPLEMENTATION",
        "implementation_approval.status",
    )
    _strict_match(
        approval.get("implementation_authority"),
        "ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1_ONLY",
        "implementation_approval.authority",
    )
    _strict_match(
        approval.get("open_decisions"), [], "implementation_approval.open_decisions"
    )
    approval_boundaries = _mapping(
        approval.get("boundaries"), "implementation_approval.boundaries"
    )
    _strict_match(
        approval_boundaries.get("exact_base_commit"),
        "8c8b9c4567392886f086d3dd69506619e5a83344",
        "implementation_approval.base_commit",
    )
    _strict_match(
        approval_boundaries.get("exact_base_tree"),
        "7f8a0f7c0d84282b2824c135f78a708a1cd1ed00",
        "implementation_approval.base_tree",
    )

    expected_interface = {
        key: copy.deepcopy(decision[key]) for key in WORDPRESS_INTERFACE_KEYS
    }
    copied_source_refs = tuple(
        copy.deepcopy(_mapping(row, "implementation_handoff.source_refs.item"))
        for row in source_refs
    )
    return ImplementationAuthorityModel(
        wordpress_interface=copy.deepcopy(
            _mapping(expected_interface, "implementation_handoff.interface")
        ),
        source_design_refs=copied_source_refs,
        validated_contents=tuple(validated_contents.items()),
    )


def _validate_sources(
    contract: Mapping[str, Any],
    root: Path,
    validated_contents: dict[str, bytes],
) -> None:
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
        content = validated_contents.get(source_name)
        if content is None:
            content = _read_repository_file(
                root,
                Path(source_name),
                "pinned_source",
                max_bytes=MAX_DOCUMENT_BYTES,
                size_error_code="SOURCE_DIGEST_MISMATCH",
            )
        if sha256_bytes(content) != expected_digest:
            _fail("SOURCE_DIGEST_MISMATCH", "pinned_source")
        validated_contents[source_name] = content


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


def _load_validated_yaml(
    validated_contents: Mapping[str, bytes], relative: str, field: str
) -> Mapping[str, Any]:
    content = validated_contents.get(relative)
    if content is None:
        _fail("SOURCE_SNAPSHOT_INCOMPLETE", field)
    return _mapping(_parse_yaml_bytes(content, field), field)


def _validate_authority_semantics(
    validated_contents: Mapping[str, bytes],
) -> None:
    backlog = _load_validated_yaml(
        validated_contents,
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        "backlog",
    )
    _strict_match(
        _find_exact_record(backlog, "stories", "ST-1506", "backlog.stories"),
        EXPECTED_STORY,
        "backlog.ST-1506",
    )

    decisions = _load_validated_yaml(
        validated_contents,
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "open_decisions",
    )
    for decision_id, expected in EXPECTED_OPEN_DECISIONS.items():
        _strict_match(
            _find_exact_record(decisions, "items", decision_id, "open_decisions.items"),
            expected,
            f"open_decisions.{decision_id}",
        )

    tests = _load_validated_yaml(
        validated_contents,
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        "test_catalog",
    )
    _strict_match(
        _find_exact_record(tests, "suites", "TST-032", "test_catalog.suites"),
        EXPECTED_TST_032,
        "test_catalog.TST-032",
    )

    release = _load_validated_yaml(
        validated_contents,
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


def _render_st1505_reference_plan(contract: Mapping[str, Any]) -> bytes:
    """Project the exact pinned ST-1505 contract without executing predecessor code."""

    execution = _mapping(contract.get("execution_boundary"), "predecessor.execution")
    evidence = _mapping(contract.get("evidence_boundary"), "predecessor.evidence")
    document = {
        "document": {
            "id": "RAOS-STAGING-DEPLOYMENT-REFERENCE-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-1505",
            "source_contract": (
                "repo://changes/st-1505/contracts/staging-deployment.v1.yaml"
            ),
            "generated_by": "repo://scripts/build_st1505_staging_deployment.py",
            "generation_command": (
                "uv run --locked --no-sync python "
                "scripts/build_st1505_staging_deployment.py"
            ),
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "predecessor_bindings": copy.deepcopy(contract["predecessor_bindings"]),
        "environment": copy.deepcopy(contract["environment_boundary"]),
        "selected_bindings": copy.deepcopy(contract["selected_bindings"]),
        "artifact_admission": copy.deepcopy(contract["artifact_admission_intent"]),
        "migration": copy.deepcopy(contract["migration_intent"]),
        "health_and_smoke": copy.deepcopy(contract["health_and_smoke_intent"]),
        "rollback": copy.deepcopy(contract["rollback_intent"]),
        "logical_phases": copy.deepcopy(contract["logical_phases"]),
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
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _validate_predecessor_semantics(
    contract: Mapping[str, Any], validated_contents: Mapping[str, bytes]
) -> None:
    binding = _mapping(contract.get("predecessor_binding"), "predecessor_binding")
    transitive = _mapping(
        binding.get("transitive_predecessor_bindings"),
        "predecessor_binding.transitive",
    )
    if tuple(transitive) != ("data_services", "compute_edge", "deployment_identity"):
        _fail("PREDECESSOR_BINDING_ORDER_DRIFT", "predecessor_binding.transitive")
    stage_contract_relative = "changes/st-1505/contracts/staging-deployment.v1.yaml"
    stage_plan_relative = (
        "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
    )
    stage_contract_content = validated_contents.get(stage_contract_relative)
    actual_plan = validated_contents.get(stage_plan_relative)
    if stage_contract_content is None or actual_plan is None:
        _fail("SOURCE_SNAPSHOT_INCOMPLETE", "predecessor")
    stage_contract = _mapping(
        _parse_yaml_bytes(stage_contract_content, "predecessor_contract"),
        "predecessor_contract",
    )
    if _object_fingerprint(stage_contract) != EXPECTED_ST1505_CONTRACT_FINGERPRINT:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    expected_plan = _render_st1505_reference_plan(stage_contract)
    expected_transitive = _mapping(
        stage_contract.get("predecessor_bindings"),
        "predecessor.predecessor_bindings",
    )
    if tuple(expected_transitive) != (
        "data_services",
        "compute_edge",
        "deployment_identity",
    ):
        _fail("PREDECESSOR_BINDING_ORDER_DRIFT", "predecessor.bindings")
    _strict_match(
        transitive,
        expected_transitive,
        "predecessor_binding.transitive",
    )
    if actual_plan != expected_plan:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor_plan")

    _assert_unset_tree(
        stage_contract.get("selected_bindings"), "predecessor.selected_bindings"
    )
    execution = _mapping(
        stage_contract.get("execution_boundary"), "predecessor.execution"
    )
    _strict_match(execution.get("activation_enabled"), False, "predecessor.enabled")
    _strict_match(execution.get("activation_status"), "DISABLED", "predecessor.status")
    _strict_match(
        execution.get("live_provider_calls"),
        "FORBIDDEN",
        "predecessor.provider",
    )
    _strict_match(execution.get("external_writes"), "FORBIDDEN", "predecessor.writes")
    _strict_match(
        execution.get("action_counts"),
        {name: 0 for name in ST1505_ACTION_COUNT_NAMES},
        "predecessor.action_counts",
    )
    for operation in _mapping(
        execution.get("operations"), "predecessor.operations"
    ).values():
        _strict_match(operation, "FORBIDDEN", "predecessor.operation")
    predecessor_evidence = _mapping(
        stage_contract.get("evidence_boundary"), "predecessor.evidence"
    )
    _strict_match(
        predecessor_evidence.get("formal_tst_009"),
        "NOT_EXECUTED",
        "predecessor.tst_009",
    )
    _strict_match(
        predecessor_evidence.get("formal_tst_022"),
        "NOT_EXECUTED",
        "predecessor.tst_022",
    )
    _strict_match(
        predecessor_evidence.get("executable_pipeline"),
        "ABSENT",
        "predecessor.executable",
    )


def _object_fingerprint(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=False,
        ).encode("utf-8")
    except OBJECT_FINGERPRINT_ERRORS:
        _fail("TYPE_MISMATCH", "contract")
    return sha256_bytes(encoded)


def _validate_local_safety_invariants(
    contract: Mapping[str, Any], expected_wordpress_interface: Mapping[str, Any]
) -> None:
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CLOSED_SCHEMA_VIOLATION", "contract")
    document = _mapping(contract.get("document"), "document")
    _strict_match(document.get("version"), "1.1.0", "document.version")
    _strict_match(document.get("story_id"), "ST-1506", "document.story_id")
    _strict_match(document.get("executable"), False, "document.executable")
    _strict_match(document.get("activation_status"), "DISABLED", "document.activation")
    _strict_match(
        document.get("formal_verification"),
        "NOT_EXECUTED",
        "document.formal_verification",
    )

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
        "hosted_ci",
        "staging",
        "live_provider",
        "migration",
        "smoke",
        "canary",
        "rollback",
        "release",
        "production",
        "status_transition",
    ):
        _strict_match(evidence.get(field), "NOT_EXECUTED", f"evidence.{field}")

    wordpress_interface = _mapping(
        contract.get("wordpress_signed_delivery_interface"),
        "wordpress_signed_delivery_interface",
    )
    _strict_ordered_match(
        wordpress_interface,
        expected_wordpress_interface,
        "wordpress_signed_delivery_interface",
    )
    interface_status = _mapping(
        wordpress_interface.get("interface_status"),
        "wordpress_signed_delivery_interface.interface_status",
    )
    _strict_match(
        interface_status.get("executable"),
        False,
        "wordpress_signed_delivery_interface.executable",
    )
    _strict_match(
        interface_status.get("activation_status"),
        "DISABLED",
        "wordpress_signed_delivery_interface.activation",
    )
    _strict_match(
        interface_status.get("automatic_delivery_authority"),
        "NONE",
        "wordpress_signed_delivery_interface.automatic_authority",
    )
    _strict_match(
        interface_status.get("manual_delivery_authority"),
        "NONE",
        "wordpress_signed_delivery_interface.manual_authority",
    )
    _strict_match(
        interface_status.get("action_count"),
        0,
        "wordpress_signed_delivery_interface.action_count",
    )
    control_plane = _mapping(
        wordpress_interface.get("control_plane_separation"),
        "wordpress_signed_delivery_interface.control_plane_separation",
    )
    for field in (
        "code_delivery_may_publish_content",
        "publication_may_trigger_deployment",
        "failed_code_delivery_may_modify_public_content",
    ):
        _strict_match(
            control_plane.get(field),
            False,
            f"wordpress_signed_delivery_interface.control_plane_separation.{field}",
        )
    interface_evidence = _mapping(
        wordpress_interface.get("evidence_boundary"),
        "wordpress_signed_delivery_interface.evidence_boundary",
    )
    for field in (
        "hosted_ci",
        "staging",
        "target_filesystem_proof",
        "crash_recovery",
        "live_wordpress",
        "release",
        "production",
        "status_transition",
    ):
        _strict_match(
            interface_evidence.get(field),
            "NOT_EXECUTED",
            f"wordpress_signed_delivery_interface.evidence_boundary.{field}",
        )


def validate_contract(
    contract: object,
    root: Path = REPO_ROOT,
    *,
    contract_content: bytes | None = None,
) -> ProductionDeploymentModel:
    value = _mapping(contract, "contract")
    if contract_content is not None:
        parsed_content = _mapping(
            _parse_yaml_bytes(contract_content, "contract_content"),
            "contract_content",
        )
        try:
            _strict_ordered_match(parsed_content, value, "contract_content")
        except ProductionDeploymentContractError:
            _fail("CONTRACT_CONTENT_MISMATCH", "contract_content")
    implementation_authority = _validate_implementation_authority(root)
    _validate_local_safety_invariants(
        value, implementation_authority.wordpress_interface
    )
    validated_contents = dict(implementation_authority.validated_contents)
    _validate_sources(value, root, validated_contents)
    _validate_authority_semantics(validated_contents)
    _validate_predecessor_semantics(value, validated_contents)
    if _object_fingerprint(value) != EXPECTED_CONTRACT_FINGERPRINT:
        _fail("CONTRACT_DEFINITION_DRIFT", "contract")
    source_artifact_contents: tuple[tuple[Path, bytes], ...] = ()
    if contract_content is not None:
        validated_contents[CONTRACT_PATH.as_posix()] = contract_content
        source_artifact_contents = _capture_source_artifact_contents(
            root, validated_contents
        )
    return ProductionDeploymentModel(
        contract=copy.deepcopy(dict(value)),
        approved_preimplementation_inputs=(implementation_authority.source_design_refs),
        source_artifact_contents=source_artifact_contents,
    )


def load_and_validate_contract(root: Path = REPO_ROOT) -> ProductionDeploymentModel:
    content = _read_repository_file(
        root,
        CONTRACT_PATH,
        "contract",
        max_bytes=MAX_DOCUMENT_BYTES,
        size_error_code="YAML_SIZE_LIMIT",
    )
    return validate_contract(
        _parse_yaml_bytes(content, "contract"),
        root,
        contract_content=content,
    )


def _section(model: ProductionDeploymentModel, name: str) -> Any:
    return copy.deepcopy(model.contract[name])


def reference_plan_document(model: ProductionDeploymentModel) -> dict[str, object]:
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    return {
        "document": {
            "id": "RAOS-PRODUCTION-DEPLOYMENT-REFERENCE-PLAN-001",
            "version": "1.1.0",
            "story_id": "ST-1506",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "artifact_kind": evidence["deliverable_classification"],
            "executable": False,
            "implementation_scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        },
        "implementation_authority": {
            "story_id": "ST-1506",
            "handoff_uri": HANDOFF_URI,
            "handoff_bytes": HANDOFF_BYTES,
            "handoff_sha256": HANDOFF_SHA256,
            "approval_uri": APPROVAL_URI,
            "approval_bytes": APPROVAL_BYTES,
            "approval_sha256": APPROVAL_SHA256,
            "status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_authority": (
                "ST1506_WORDPRESS_SIGNED_DELIVERY_INTERFACE_V1_ONLY"
            ),
            "open_decisions": [],
        },
        "predecessor_binding": _section(model, "predecessor_binding"),
        "open_decision_defaults": _section(model, "open_decision_defaults"),
        "environment": _section(model, "environment_boundary"),
        "selected_bindings": _section(model, "selected_bindings"),
        "human_approval_gates": _section(model, "human_approval_gates"),
        "artifact_admission": _section(model, "artifact_admission_intent"),
        "protected_environment": _section(model, "protected_environment_intent"),
        "migration": _section(model, "migration_intent"),
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
            "aws_action": execution["aws_action"],
            "iam_action": execution["iam_action"],
            "deploy_action": execution["deploy_action"],
            "release_action": execution["release_action"],
            "production_action": execution["production_action"],
            "operations": copy.deepcopy(execution["operations"]),
        },
        "verification_boundary": {
            key: copy.deepcopy(value)
            for key, value in evidence.items()
            if key != "deliverable_classification"
        },
        "wordpress_signed_delivery_interface": _section(
            model, "wordpress_signed_delivery_interface"
        ),
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


def _capture_source_artifact_contents(
    root: Path, validated_contents: Mapping[str, bytes]
) -> tuple[tuple[Path, bytes], ...]:
    captured: list[tuple[Path, bytes]] = []
    for relative in SOURCE_ARTIFACT_PATHS:
        content = validated_contents.get(relative.as_posix())
        if content is None:
            content = _read_repository_file(
                root,
                relative,
                "source_artifact",
                max_bytes=MAX_DOCUMENT_BYTES,
                size_error_code="SOURCE_ARTIFACT_SIZE_LIMIT",
            )
        captured.append((relative, content))
    return tuple(captured)


def _artifact_row(relative: Path, content: bytes) -> dict[str, object]:
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(
    model: ProductionDeploymentModel,
    reference_plan: bytes,
) -> bytes:
    source_contents = dict(model.source_artifact_contents)
    if tuple(source_contents) != SOURCE_ARTIFACT_PATHS:
        _fail("SOURCE_SNAPSHOT_INCOMPLETE", "source_artifacts")
    source_artifacts = [
        _artifact_row(relative, source_contents[relative])
        for relative in SOURCE_ARTIFACT_PATHS
    ]
    execution = _mapping(model.contract["execution_boundary"], "execution_boundary")
    evidence = _mapping(model.contract["evidence_boundary"], "evidence_boundary")
    environment = _mapping(model.contract["environment_boundary"], "environment")
    selection = _mapping(model.contract["selected_bindings"], "selected_bindings")
    approvals = _mapping(model.contract["human_approval_gates"], "human_approval_gates")
    document: dict[str, object] = {
        "document": {
            "id": "RAOS-PRODUCTION-DEPLOYMENT-MANIFEST-001",
            "version": "1.1.0",
            "story_id": "ST-1506",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_uri": SOURCE_CONTRACT_URI,
            "contract_sha256": sha256_bytes(source_contents[CONTRACT_PATH]),
            "authority_inputs": [
                {"uri": f"repo://{relative}", "sha256": digest}
                for relative, digest in AUTHORITY_SOURCES.items()
            ],
            "implementation_authority_inputs": [
                {
                    "uri": HANDOFF_URI,
                    "bytes": HANDOFF_BYTES,
                    "sha256": HANDOFF_SHA256,
                },
                {
                    "uri": APPROVAL_URI,
                    "bytes": APPROVAL_BYTES,
                    "sha256": APPROVAL_SHA256,
                },
            ],
            "approved_preimplementation_inputs": copy.deepcopy(
                list(model.approved_preimplementation_inputs)
            ),
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
            "formal_tst_032": evidence["formal_tst_032"],
            "hosted_ci": evidence["hosted_ci"],
            "live_provider": evidence["live_provider"],
            "migration": evidence["migration"],
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
        MANIFEST_PATH: render_manifest(model, reference_plan),
    }


def _open_output_parent(root: Path, relative: Path, *, create: bool) -> int:
    _validate_relative_path(relative, "output", "UNSAFE_OUTPUT_PATH")
    directory_flags = (
        os.O_RDONLY
        | _required_safe_io_flag("O_CLOEXEC")
        | _required_safe_io_flag("O_DIRECTORY")
        | _required_safe_io_flag("O_NOFOLLOW")
    )
    directories = [_open_physical_directory(root, "repository")]
    try:
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            except FileNotFoundError:
                if not create:
                    _fail("GENERATED_OUTPUT_MISSING", "output")
                try:
                    os.mkdir(part, mode=0o755, dir_fd=directories[-1])
                    os.fsync(directories[-1])
                except FileExistsError:
                    pass
                except OSError:
                    _fail("OUTPUT_DIRECTORY_FAILED", "output")
                try:
                    child = os.open(part, directory_flags, dir_fd=directories[-1])
                except OSError:
                    _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            except OSError:
                _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            directories.append(child)
        return directories.pop()
    except ProductionDeploymentContractError:
        raise
    except OSError:
        _fail("OUTPUT_DIRECTORY_FAILED", "output")
    finally:
        _close_descriptors(directories)


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    parent_descriptor = _open_output_parent(root, relative, create=True)
    descriptor = -1
    temporary_name: str | None = None
    try:
        try:
            target_metadata = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            _fail("UNSAFE_FILE_TYPE", "generated_output")

        for attempt in range(100):
            candidate = f".{relative.name}.st1506-{os.getpid()}-{attempt}.tmp"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | _required_safe_io_flag("O_CLOEXEC")
                    | _required_safe_io_flag("O_NOFOLLOW"),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            _fail("OUTPUT_WRITE_FAILED", "output")

        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("OUTPUT_WRITE_FAILED", "output")
            view = view[written:]
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
        completed_descriptor = descriptor
        descriptor = -1
        os.close(completed_descriptor)
        os.replace(
            temporary_name,
            relative.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    except ProductionDeploymentContractError:
        raise
    except OSError:
        _fail("OUTPUT_WRITE_FAILED", "output")
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor)
        try:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name, dir_fd=parent_descriptor)
                except OSError:
                    pass
        finally:
            _close_descriptor(parent_descriptor)


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        actual = _read_repository_file(
            root,
            relative,
            "output",
            max_bytes=MAX_DOCUMENT_BYTES,
            size_error_code="GENERATED_OUTPUT_DRIFT",
            path_error_code="UNSAFE_OUTPUT_PATH",
            missing_error_code="GENERATED_OUTPUT_MISSING",
            ancestor_error_code="UNSAFE_OUTPUT_ANCESTOR",
            file_type_error_code="UNSAFE_FILE_TYPE",
        )
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
