#!/usr/bin/env python3
"""Build the deterministic, non-attesting ST-1705 blocked sign-off record."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import stat
import sys

if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print(
            "ST1705_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1705_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1705/contracts/pilot-security-recovery-signoff.v1.yaml"
)
FORMAL_SCHEMA_PATH: Final = Path(
    "changes/st-1705/contracts/pilot-signoff-evidence-input.v1.schema.json"
)
DECISION_PATH: Final = Path(
    "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1705/manifest.yaml")
README_PATH: Final = Path("changes/st-1705/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1705/PREFLIGHT.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1705/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1705_pilot_signoff.py")
TEST_PATHS: Final = (
    Path("tests/st1705/conftest.py"),
    Path("tests/st1705/test_contract.py"),
    Path("tests/st1705/test_decision.py"),
    Path("tests/st1705/test_generation.py"),
    Path("tests/st1705/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FORMAL_SCHEMA_PATH,
    README_PATH,
    PREFLIGHT_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (DECISION_PATH, MANIFEST_PATH)

MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 1024 * 1024
OUTPUT_MODE: Final = 0o644
PRIVATE_MODE: Final = 0o600
NEXT_SUFFIX: Final = ".st1705.next"
PREVIOUS_SUFFIX: Final = ".st1705.previous"
ABSENT_SUFFIX: Final = ".st1705.absent"
TRANSACTION_NAME: Final = ".manifest.yaml.st1705.transaction.json"
TRANSACTION_NEXT_NAME: Final = f"{TRANSACTION_NAME}.next"
ABSENT_MARKER: Final = b"ST1705_OUTPUT_WAS_ABSENT_V1\n"
TRANSACTION_SCHEMA: Final = "ST1705_OUTPUT_TRANSACTION_V1"

GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1705_pilot_signoff.py"
)
LOCAL_BASE_COMMIT: Final = "9894d87a19b0ad407d070ea9dbe43ea39f36e935"

TOP_LEVEL_KEYS: Final = (
    "document",
    "source_bindings",
    "dependency_bindings",
    "formal_evidence_port",
    "decision_inputs",
    "article_artifact_boundary",
    "runtime_evidence",
    "blockers",
    "decision",
    "authority_boundary",
    "execution_boundary",
    "evidence_boundary",
)

EXPECTED_SOURCE_HASHES: Final = {
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
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_release_evidence_template_v1.0.yaml": (
        "3354001be5fc0f7f7ef6a265fdd3112618ee943092755745d8cd62986487e95a"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md": (
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8"
    ),
    "docs/canonical/06_ops/RAOS_12_backup_restore_matrix_v1.0.yaml": (
        "60ab681822e1aa7c63584bb1b1f4cb6202f4f0dcbea572462dd3a3e7fa8c15f6"
    ),
}

EXPECTED_DEPENDENCY_HASHES: Final = {
    "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json": (
        "b22dc4587a80cd2e679af7f0c038194812573c77a9e635ce074c40665a147261"
    ),
    "changes/st-1607/manifest.yaml": (
        "5ffad284b6c97d404f10ba5d1708550d5c511d54c67749d66fd565500c5b8a40"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml": (
        "49902bbbbfe791f313c68c7d450c47271972bbf94f7486d2837040fdbceb0371"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json": (
        "e5a9b3d8dcc16204594c7906dd232f6cadfb32a3e2def70cfe1f901773f4d022"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json": (
        "cc9c0057a1f42546988596ad02891d638471370997eadf50d55bbe61fe884c88"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json": (
        "53db8c8277da9dbd3b5b98a107327845307f58a9e3b767042ea9e64757f0e163"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json": (
        "1a1827f0296f1bdd7c983d141b2c2eae87a4ad9f327e68062e036adde289c73c"
    ),
    "changes/st-1704/affiliate-learning-v2/DESIGN_HANDOFF_V1.yaml": (
        "c99f444a7ed4e1c5ee4d27f74e930b8e874cb5a79d4c81f0b8509371c353d247"
    ),
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json": (
        "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8"
    ),
    "changes/st-1704/affiliate-learning-v2/runtime-manifest.v2.json": (
        "d4583a62fd4db0cc7845b80bc9375d401861541afd5ae225abe33f628d76c5e9"
    ),
}

FORMAL_SCHEMA_SHA256: Final = (
    "3a38ab7c4f57db962b07c5cb78782f5fa42a2d787eb78da3f954772352a684c1"
)
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)
ACTIVE_BLOCKER_IDS: Final = (
    "OD-001",
    "OD-002",
    "OD-003",
    "OD-005",
    "OD-006",
    "OD-007",
    "OD-008",
    "OD-009",
    "OD-010",
    "OD-011",
    "OD-012",
    "OD-013",
    "OD-014",
    "OD-015",
)
BLOCKERS: Final = (
    "ACTIVE_BLOCKING_OPEN_DECISIONS_14",
    "ST1607_GATE_0_BLOCKED",
    "FORMAL_TST_026_NOT_EXECUTED",
    "FORMAL_TST_029_NOT_EXECUTED",
    "FORMAL_TST_032_NOT_EXECUTED",
    "SECURITY_RUNTIME_EVIDENCE_UNAVAILABLE",
    "BACKUP_RESTORE_RUNTIME_EVIDENCE_UNAVAILABLE",
    "SOURCE_FREEZE_UNAVAILABLE",
    "REVIEWED_IMPLEMENTATION_TREE_UNAVAILABLE",
    "HUMAN_SIGNOFF_MISSING",
    "REAL_PILOT_OBSERVATIONS_UNAVAILABLE",
    "PUBLICATION_SNAPSHOTS_UNAVAILABLE",
)


class PilotSignoffError(RuntimeError):
    """Sanitized, fail-closed ST-1705 validation error."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"ST1705_ERROR code={code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader rejecting duplicate keys."""


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


def _fail(code: str, field: str) -> NoReturn:
    raise PilotSignoffError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail("INVALID_MAPPING", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("INVALID_LIST", field)
    return value


def _exact(value: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        if tuple(observed) != tuple(expected):
            _fail("CLOSED_SCHEMA_DRIFT", field)
        for key, expected_value in expected.items():
            _exact(observed[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        observed_list = _list(value, field)
        expected_list = _list(expected, field)
        if len(observed_list) != len(expected_list):
            _fail("FIXED_INVENTORY_DRIFT", field)
        for index, expected_value in enumerate(expected_list):
            _exact(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        if (
            expected is None
            or type(expected) is bool
            or expected
            in {
                "BLOCKED",
                "NOT_SIGNED_OFF",
                "NOT_ELIGIBLE",
                "NOT_EXECUTED",
                "NONE",
                "UNAVAILABLE",
            }
        ):
            _fail("SAFE_BOUNDARY_DRIFT", field)
        _fail("FIXED_VALUE_DRIFT", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _required_flag(name: str) -> int:
    value = getattr(os, name, None)
    if type(value) is not int or value == 0:
        _fail("UNSUPPORTED_SAFE_IO", "filesystem")
    return value


def _close(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _validate_relative(relative: Path, field: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)


def _absolute_root(root: Path) -> Path:
    absolute = root if root.is_absolute() else Path.cwd() / root
    normalized = Path(os.path.abspath(os.fspath(absolute)))
    if not normalized.is_absolute() or any(
        part in {"", ".", ".."} for part in normalized.parts[1:]
    ):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    return normalized


def _open_root(root: Path, field: str) -> int:
    flags = (
        os.O_RDONLY
        | _required_flag("O_CLOEXEC")
        | _required_flag("O_DIRECTORY")
        | _required_flag("O_NOFOLLOW")
    )
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, flags))
        for part in _absolute_root(root).parts[1:]:
            try:
                descriptors.append(os.open(part, flags, dir_fd=descriptors[-1]))
            except FileNotFoundError:
                _fail("ROOT_UNAVAILABLE", field)
            except OSError:
                _fail("UNSAFE_ROOT_TYPE", field)
        result = descriptors.pop()
        return result
    finally:
        while descriptors:
            _close(descriptors.pop())


def _input_path_walk_checkpoint(_root_descriptor: int, _relative: Path) -> None:
    """Test-only race checkpoint after the physical root is captured."""


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read(root: Path, relative: Path, field: str) -> bytes:
    _validate_relative(relative, field)
    directory_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    directories = [_open_root(root, field)]
    descriptor = -1
    try:
        _input_path_walk_checkpoint(directories[0], relative)
        for part in relative.parts[:-1]:
            try:
                directories.append(
                    os.open(part, directory_flags, dir_fd=directories[-1])
                )
            except FileNotFoundError:
                _fail("FILE_UNAVAILABLE", field)
            except OSError:
                _fail("UNSAFE_ANCESTOR", field)
        try:
            path_before = os.stat(
                relative.name, dir_fd=directories[-1], follow_symlinks=False
            )
            descriptor = os.open(relative.name, file_flags, dir_fd=directories[-1])
        except FileNotFoundError:
            _fail("FILE_UNAVAILABLE", field)
        except OSError:
            _fail("UNSAFE_FILE_TYPE", field)
        metadata_before = os.fstat(descriptor)
        for metadata in (path_before, metadata_before):
            if not stat.S_ISREG(metadata.st_mode):
                _fail("UNSAFE_FILE_TYPE", field)
            if metadata.st_uid != os.geteuid():
                _fail("UNSAFE_FILE_OWNER", field)
            if metadata.st_nlink != 1:
                _fail("UNSAFE_FILE_LINK_COUNT", field)
            if stat.S_IMODE(metadata.st_mode) & 0o022:
                _fail("UNSAFE_FILE_MODE", field)
        if _identity(path_before) != _identity(metadata_before):
            _fail("INPUT_CHANGED_DURING_READ", field)
        if metadata_before.st_size < 0 or metadata_before.st_size > MAX_INPUT_BYTES:
            _fail("INPUT_SIZE_LIMIT", field)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, MAX_INPUT_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                _fail("INPUT_SIZE_LIMIT", field)
        content = b"".join(chunks)
        metadata_after = os.fstat(descriptor)
        path_after = os.stat(
            relative.name, dir_fd=directories[-1], follow_symlinks=False
        )
        if (
            len(
                {
                    _identity(path_before),
                    _identity(metadata_before),
                    _identity(metadata_after),
                    _identity(path_after),
                }
            )
            != 1
            or len(content) != metadata_before.st_size
        ):
            _fail("INPUT_CHANGED_DURING_READ", field)
        return content
    except PilotSignoffError:
        raise
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    finally:
        if descriptor >= 0:
            _close(descriptor)
        while directories:
            _close(directories.pop())


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("JSON_DUPLICATE_KEY", field)
            result[key] = value
        return result

    try:
        value = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _fail("JSON_INVALID", field),
        )
    except PilotSignoffError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(value, field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", field)
        value = yaml.load(text, Loader=UniqueKeyLoader)
    except PilotSignoffError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


def _artifact(kind: str, path: str) -> dict[str, object]:
    return {
        "kind": kind,
        "uri": f"repo://{path}",
        "sha256": EXPECTED_DEPENDENCY_HASHES[path],
    }


def _expected_dependency_bindings() -> dict[str, object]:
    return {
        "st_1607": {
            "story_id": "ST-1607",
            "role": "BLOCKED_GATE_PACK_INPUT",
            "artifacts": [
                _artifact(
                    "GENERATED_LOCAL_BLOCKED_GATE_PACK",
                    "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json",
                ),
                _artifact("MANIFEST", "changes/st-1607/manifest.yaml"),
            ],
        },
        "st_1704_self_hosted": {
            "story_id": "ST-1704",
            "role": "LOCAL_ARTICLE_ARTIFACT_INPUT",
            "artifacts": [
                _artifact(
                    "DESIGN_RECORD",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/DESIGN_HANDOFF_V1.yaml",
                ),
                _artifact(
                    "RUNTIME_MANIFEST",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json",
                ),
                _artifact(
                    "ARTICLE_COLLECTION",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
                ),
                _artifact(
                    "PUBLICATION_PLAN",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json",
                ),
                _artifact(
                    "IMMUTABLE_MEASUREMENT_TEMPLATE",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/measurement-ledger.v1.json",
                ),
            ],
        },
        "st_1704_measurement": {
            "story_id": "ST-1704",
            "role": "LOCAL_MEASUREMENT_INTERFACE_INPUT",
            "artifacts": [
                _artifact(
                    "DESIGN_RECORD",
                    "changes/st-1704/affiliate-learning-v2/DESIGN_HANDOFF_V1.yaml",
                ),
                _artifact(
                    "MEASUREMENT_CONTRACT",
                    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",
                ),
                _artifact(
                    "RUNTIME_MANIFEST",
                    "changes/st-1704/affiliate-learning-v2/runtime-manifest.v2.json",
                ),
            ],
        },
    }


def _expected_contract_sections() -> dict[str, object]:
    return {
        "document": {
            "id": "RAOS-ST1705-PILOT-SECURITY-RECOVERY-SIGNOFF-001",
            "version": "1.0.0",
            "story_id": "ST-1705",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "classification": "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING",
            "acceptance_criteria_satisfied": False,
            "formal_verification": "NOT_EXECUTED",
        },
        "source_bindings": [
            {"uri": f"repo://{path}", "sha256": digest}
            for path, digest in EXPECTED_SOURCE_HASHES.items()
        ],
        "dependency_bindings": _expected_dependency_bindings(),
        "formal_evidence_port": {
            "schema_uri": f"repo://{FORMAL_SCHEMA_PATH.as_posix()}",
            "schema_sha256": FORMAL_SCHEMA_SHA256,
            "schema_behavior": "CLOSED_ADDITIONAL_PROPERTIES_FALSE",
            "activation": "DISABLED",
            "current_input_uri": None,
            "current_input_sha256": None,
            "current_input_status": "ABSENT",
            "dynamic_input_path": "FORBIDDEN",
            "authenticity_policy": "INDEPENDENT_FORMAL_OWNER_PIPELINE_REQUIRED",
            "default_decision": "BLOCKED",
            "evidence_cannot_self_authorize": True,
        },
        "decision_inputs": {
            "st_1607_gate_pack": {
                "classification": "LOCAL_BLOCKED_GATE_EVIDENCE_PACK_NON_ATTESTING",
                "gate_0_status": "BLOCKED",
                "all_gate_status": "BLOCKED",
                "active_blocking_open_decisions": 14,
                "qualifying_gate_evidence_count": 0,
                "source_freeze_status": "ABSENT",
                "reviewed_implementation_tree_status": "ABSENT",
                "human_gate_approval_status": "NONE",
                "formal_tst_032": "NOT_EXECUTED",
            },
            "st_1704_local_artifacts": {
                "tracked_article_packet_count": 5,
                "tracked_article_artifact_status": "PRESENT_LOCAL_ONLY",
                "immutable_publication_snapshot_count": 0,
                "public_verification_count": 0,
                "real_pilot_observation_status": "UNAVAILABLE",
                "revenue_observation_status": "UNAVAILABLE",
                "owner_private_measurement_ledger_read": False,
                "qualifies_as_runtime_pilot_evidence": False,
            },
            "required_formal_evidence": {
                "formal_tst_026": "NOT_EXECUTED",
                "formal_tst_029": "NOT_EXECUTED",
                "formal_tst_032": "NOT_EXECUTED",
                "security_runtime_evidence": "UNAVAILABLE",
                "backup_restore_runtime_evidence": "UNAVAILABLE",
                "source_freeze": "UNAVAILABLE",
                "reviewed_implementation_tree": "UNAVAILABLE",
                "human_security_approval": "MISSING",
                "human_operations_approval": "MISSING",
                "human_product_owner_approval": "MISSING",
            },
        },
        "article_artifact_boundary": {
            "exact_article_ids": list(ARTICLE_IDS),
            "local_artifacts_exist": True,
            "local_artifacts_are_pilot_observations": False,
            "local_artifacts_are_publication_evidence": False,
            "local_artifacts_are_revenue_evidence": False,
            "local_artifacts_are_gate_evidence": False,
            "missing_observations_must_not_be_inferred": True,
        },
        "runtime_evidence": [
            {
                "suite_id": "TST-026",
                "required_environment": ["CI", "STAGING"],
                "execution_status": "NOT_EXECUTED",
                "artifact_uri": None,
                "artifact_sha256": None,
                "eligible": False,
            },
            {
                "suite_id": "TST-029",
                "required_environment": ["STAGING_RECOVERY"],
                "execution_status": "NOT_EXECUTED",
                "artifact_uri": None,
                "artifact_sha256": None,
                "eligible": False,
            },
            {
                "suite_id": "TST-032",
                "required_environment": ["STAGING"],
                "execution_status": "NOT_EXECUTED",
                "artifact_uri": None,
                "artifact_sha256": None,
                "eligible": False,
            },
        ],
        "blockers": list(BLOCKERS),
        "decision": {
            "overall": "BLOCKED",
            "gate_0": "BLOCKED",
            "technical_pilot": "BLOCKED",
            "security_sign_off": "NOT_SIGNED_OFF",
            "recovery_sign_off": "NOT_SIGNED_OFF",
            "pilot_eligibility": "NOT_ELIGIBLE",
            "downstream_st_1801_eligibility": "NOT_ELIGIBLE",
            "qualifying_evidence_references": [],
            "approval_artifacts": [],
            "accepted_exceptions": [],
        },
        "authority_boundary": {
            "external_authority": "NONE",
            "formal_evidence_acceptance_authority": "NONE",
            "gate_approval_authority": "NONE",
            "status_propose_authority": "NONE",
            "status_apply_authority": "NONE",
            "publication_authority": "NONE",
            "staging_authority": "NONE",
            "release_authority": "NONE",
            "deployment_authority": "NONE",
            "production_authority": "NONE",
        },
        "execution_boundary": {
            "local_generation_only": True,
            "input_size_limit_bytes": MAX_INPUT_BYTES,
            "input_read_model": "ROOT_FD_DESCRIPTOR_RELATIVE_CAPTURED_LEAF",
            "writer_model": "SINGLE_PROCESS_DIRECTORY_LOCK",
            "output_transaction": "TWO_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "check_pending_recovery_behavior": "READ_ONLY_REJECT",
            "network_access": "FORBIDDEN",
            "environment_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "subprocess_execution": "FORBIDDEN",
            "status_registry_mutation": "FORBIDDEN",
            "publication_actions": "FORBIDDEN",
            "staging_actions": "FORBIDDEN",
            "release_actions": "FORBIDDEN",
            "deployment_actions": "FORBIDDEN",
            "production_actions": "FORBIDDEN",
            "external_action_count": 0,
        },
        "evidence_boundary": {
            "classification": "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING",
            "local_base_commit": LOCAL_BASE_COMMIT,
            "local_base_commit_status": "RECORDED_IMPLEMENTATION_BASE_ONLY",
            "local_base_commit_qualifying_evidence": False,
            "source_freeze_status": "UNAVAILABLE",
            "source_freeze_identifier": None,
            "reviewed_implementation_tree_status": "UNAVAILABLE",
            "reviewed_implementation_tree_commit": None,
            "canonical_status": "UNCHANGED",
            "registry_propose_or_apply": "NOT_EXECUTED",
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "hosted_ci": "NOT_EXECUTED",
            "live_provider": "NOT_EXECUTED",
            "live_pilot": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "deployment": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "validated_claim": False,
            "gate_pass_claim": False,
            "sign_off_claim": False,
            "story_acceptance": False,
            "release_eligible": False,
            "production_ready": False,
        },
    }


def _find_record(rows: object, identity: str, field: str) -> Mapping[str, Any]:
    records = _list(rows, field)
    matches = [
        row for row in records if isinstance(row, Mapping) and row.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_DRIFT", field)
    return _mapping(matches[0], field)


def _verify_hashes(root: Path) -> None:
    for path, expected in EXPECTED_SOURCE_HASHES.items():
        if _sha256(_read(root, Path(path), "source_binding")) != expected:
            _fail("SOURCE_HASH_DRIFT", "source_binding")
    for path, expected in EXPECTED_DEPENDENCY_HASHES.items():
        if _sha256(_read(root, Path(path), "dependency_binding")) != expected:
            _fail("DEPENDENCY_HASH_DRIFT", "dependency_binding")
    if (
        _sha256(_read(root, FORMAL_SCHEMA_PATH, "formal_schema"))
        != FORMAL_SCHEMA_SHA256
    ):
        _fail("FORMAL_SCHEMA_HASH_DRIFT", "formal_schema")


def _validate_canonical_semantics(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "backlog",
    )
    story = _find_record(backlog.get("stories"), "ST-1705", "backlog.stories")
    expected_story = {
        "id": "ST-1705",
        "epic_id": "EPIC-17",
        "title": "Pilot security/recovery sign-off",
        "objective": "GATE-0/技術PilotのEvidence",
        "depends_on": ["ST-1607", "ST-1704"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["decision record"],
        "acceptance_criteria": ["blocking decisions resolved", "runtime evidence"],
        "test_suites": ["TST-026", "TST-029", "TST-032"],
        "priority": "P0",
        "mvp": True,
        "size": "M",
        "open_decisions": [],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }
    _exact(story, expected_story, "backlog.ST-1705")

    catalog = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    for suite_id, layer, environments in (
        ("TST-026", "security", ["CI", "staging"]),
        ("TST-029", "recovery", ["staging/recovery"]),
        ("TST-032", "acceptance", ["staging"]),
    ):
        suite = _find_record(catalog.get("suites"), suite_id, "test_catalog.suites")
        if (
            suite.get("layer") != layer
            or suite.get("environments") != environments
            or suite.get("release_blocking") is not True
            or suite.get("execution_status") != "NOT_EXECUTED"
        ):
            _fail("FORMAL_SUITE_SEMANTIC_DRIFT", suite_id)

    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "open_decisions",
    )
    active = [
        row.get("id")
        for row in _list(decisions.get("items"), "open_decisions.items")
        if isinstance(row, Mapping)
        and row.get("blocking") is True
        and row.get("status")
        in {"HUMAN_DECISION_REQUIRED", "EXTERNAL_EVIDENCE_REQUIRED"}
    ]
    if active != list(ACTIVE_BLOCKER_IDS):
        _fail("OPEN_DECISION_SEMANTIC_DRIFT", "open_decisions")

    controls = _load_yaml(
        root,
        Path("docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"),
        "security_controls",
    )
    control_rows = _list(controls.get("controls"), "security_controls.controls")
    if len(control_rows) != 83 or any(
        not isinstance(row, Mapping)
        or row.get("gate") != "GATE-0"
        or row.get("verification_status") != "NOT_EXECUTED"
        for row in control_rows
    ):
        _fail("SECURITY_CONTROL_SEMANTIC_DRIFT", "security_controls")

    recovery = _load_yaml(
        root,
        Path("docs/canonical/06_ops/RAOS_12_backup_restore_matrix_v1.0.yaml"),
        "backup_restore",
    )
    assets = _list(recovery.get("assets"), "backup_restore.assets")
    if len(assets) != 5 or any(
        not isinstance(row, Mapping) or row.get("status") != "NOT_CONFIGURED"
        for row in assets
    ):
        _fail("RECOVERY_AUTHORITY_DRIFT", "backup_restore")


def _validate_st1607(root: Path) -> None:
    pack = _load_json(
        root,
        Path("changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json"),
        "st1607_pack",
    )
    if pack.get("classification") != "LOCAL_BLOCKED_GATE_EVIDENCE_PACK_NON_ATTESTING":
        _fail("ST1607_SEMANTIC_DRIFT", "classification")
    decision = _mapping(pack.get("decision_input"), "st1607.decision_input")
    if (
        decision.get("unresolved_blocking_count") != 14
        or decision.get("active_blocker_ids") != list(ACTIVE_BLOCKER_IDS)
        or decision.get("decision_clearance") != "NOT_AVAILABLE"
    ):
        _fail("ST1607_SEMANTIC_DRIFT", "decision_input")
    snapshot = _mapping(pack.get("snapshot_boundary"), "st1607.snapshot")
    if (
        snapshot.get("source_freeze_status") != "ABSENT"
        or snapshot.get("source_freeze_identifier") is not None
        or snapshot.get("reviewed_implementation_tree_commit_status") != "ABSENT"
        or snapshot.get("reviewed_implementation_tree_commit") is not None
    ):
        _fail("ST1607_SEMANTIC_DRIFT", "snapshot_boundary")
    gate_report = _mapping(pack.get("gate_report"), "st1607.gate_report")
    gates = _list(gate_report.get("gates"), "st1607.gates")
    if len(gates) != 5 or any(
        not isinstance(row, Mapping)
        or row.get("status") != "BLOCKED"
        or row.get("qualifying_evidence_references") != []
        for row in gates
    ):
        _fail("ST1607_SEMANTIC_DRIFT", "gate_report")
    authority = _mapping(pack.get("authority_boundary"), "st1607.authority")
    if any(
        value != "NONE"
        for key, value in authority.items()
        if key != "approval_artifacts"
    ):
        _fail("ST1607_SEMANTIC_DRIFT", "authority_boundary")
    evidence = _mapping(pack.get("evidence_boundary"), "st1607.evidence")
    if (
        evidence.get("formal_tst_032") != "NOT_EXECUTED"
        or evidence.get("gate_pass_claim") is not False
        or evidence.get("release_eligible") is not False
    ):
        _fail("ST1607_SEMANTIC_DRIFT", "evidence_boundary")


def _validate_st1704(root: Path) -> None:
    manifest = _load_json(
        root,
        Path("changes/st-1704/self-hosted-editorial-pilot-v1/runtime-manifest.v1.json"),
        "st1704_self_hosted_manifest",
    )
    if (
        manifest.get("schema") != "SELF_HOSTED_EDITORIAL_PILOT_MANIFEST_V1"
        or manifest.get("story_id") != "ST-1704"
        or manifest.get("slice_id") != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or manifest.get("article_ids") != list(ARTICLE_IDS)
        or manifest.get("publication_authority") != "NONE"
        or manifest.get("external_action_authority") != "NONE"
    ):
        _fail("ST1704_ARTIFACT_SEMANTIC_DRIFT", "runtime_manifest")

    articles = _load_json(
        root,
        Path("changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"),
        "st1704_articles",
    )
    rows = _list(articles.get("articles"), "st1704_articles.articles")
    if (
        articles.get("publication_authority") != "NONE"
        or articles.get("article_order") != list(ARTICLE_IDS)
        or len(rows) != 5
        or [row.get("article_id") for row in rows if isinstance(row, Mapping)]
        != list(ARTICLE_IDS)
        or any(
            not isinstance(row, Mapping) or row.get("publication_authority") != "NONE"
            for row in rows
        )
    ):
        _fail("ST1704_ARTIFACT_SEMANTIC_DRIFT", "article_collection")

    publication = _load_json(
        root,
        Path(
            "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json"
        ),
        "st1704_publication_plan",
    )
    publication_rows = _list(publication.get("articles"), "publication_plan.articles")
    if (
        publication.get("publication_authority") != "NONE"
        or len(publication_rows) != 5
        or [
            row.get("article_id")
            for row in publication_rows
            if isinstance(row, Mapping)
        ]
        != list(ARTICLE_IDS)
        or any(
            not isinstance(row, Mapping)
            or row.get("immutable_snapshot_sha256") is not None
            or row.get("public_verification") != "NOT_EXECUTED"
            or row.get("status") != "BLOCKED_PENDING_EXACT_SNAPSHOT_HUMAN_CONFIRMATION"
            for row in publication_rows
        )
    ):
        _fail("ST1704_ARTIFACT_SEMANTIC_DRIFT", "publication_plan")

    measurement = _load_json(
        root,
        Path("changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"),
        "st1704_measurement",
    )
    measurement_rows = _list(measurement.get("articles"), "measurement.articles")
    guardrails = _mapping(measurement.get("guardrails"), "measurement.guardrails")
    if (
        measurement.get("schema") != "ST1704_AFFILIATE_LEARNING_MEASUREMENT_CONTRACT_V2"
        or measurement.get("program") != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or len(measurement_rows) != 5
        or [
            row.get("article_id")
            for row in measurement_rows
            if isinstance(row, Mapping)
        ]
        != list(ARTICLE_IDS)
        or any(
            guardrails.get(key) is not False
            for key in (
                "arbitrary_total_allocation",
                "article_html_mutation",
                "automatic_publication",
                "cta_mutation",
                "live_provider_calls",
                "network_requests",
                "product_selection_mutation",
                "publication_snapshot_mutation",
                "recommendation_order_mutation",
                "tracking_activation",
                "unattributed_reward_article_allocation",
            )
        )
        or guardrails.get("recommendation_inputs_excluded")
        != ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"]
    ):
        _fail("ST1704_MEASUREMENT_SEMANTIC_DRIFT", "measurement_contract")

    measurement_manifest = _load_json(
        root,
        Path("changes/st-1704/affiliate-learning-v2/runtime-manifest.v2.json"),
        "st1704_measurement_manifest",
    )
    measurement_authority = _mapping(
        measurement_manifest.get("authority"), "measurement_manifest.authority"
    )
    if (
        measurement_manifest.get("schema")
        != "ST1704_AFFILIATE_LEARNING_RUNTIME_MANIFEST_V2"
        or measurement_manifest.get("program") != "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
        or any(value is not False for value in measurement_authority.values())
    ):
        _fail("ST1704_MEASUREMENT_SEMANTIC_DRIFT", "measurement_manifest")


def _validate_formal_schema(root: Path) -> None:
    schema = _load_json(root, FORMAL_SCHEMA_PATH, "formal_schema")
    if (
        schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        or schema.get("type") != "object"
        or schema.get("additionalProperties") is not False
        or schema.get("required")
        != [
            "schema",
            "target",
            "source_freeze",
            "reviewed_implementation_tree",
            "suite_evidence",
            "open_decision_clearance",
            "security_findings",
            "backup_restore",
            "human_approvals",
        ]
    ):
        _fail("FORMAL_SCHEMA_SEMANTIC_DRIFT", "formal_schema")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    expected = _expected_contract_sections()
    _exact(contract, expected, "contract")
    _verify_hashes(root)
    _validate_canonical_semantics(root)
    _validate_st1607(root)
    _validate_st1704(root)
    _validate_formal_schema(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def decision_record(contract: Mapping[str, Any]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": GENERATION_COMMAND,
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
        },
        "story": {
            "id": "ST-1705",
            "scope": "LOCAL_BLOCKED_SIGNOFF_DECISION_ONLY",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "classification": "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING",
        "source_bindings": copy.deepcopy(contract["source_bindings"]),
        "dependency_bindings": copy.deepcopy(contract["dependency_bindings"]),
        "formal_evidence_port": copy.deepcopy(contract["formal_evidence_port"]),
        "decision_inputs": copy.deepcopy(contract["decision_inputs"]),
        "article_artifact_boundary": copy.deepcopy(
            contract["article_artifact_boundary"]
        ),
        "runtime_evidence": copy.deepcopy(contract["runtime_evidence"]),
        "blockers": copy.deepcopy(contract["blockers"]),
        "decision": copy.deepcopy(contract["decision"]),
        "authority_boundary": copy.deepcopy(contract["authority_boundary"]),
        "execution_boundary": copy.deepcopy(contract["execution_boundary"]),
        "evidence_boundary": copy.deepcopy(contract["evidence_boundary"]),
        "prohibited_interpretations": [
            "FIVE_TRACKED_ARTICLE_PACKETS_ARE_NOT_REAL_PILOT_OBSERVATIONS",
            "LOCAL_ARTICLE_ARTIFACTS_ARE_NOT_PUBLICATION_OR_REVENUE_EVIDENCE",
            "MEASUREMENT_INTERFACE_IS_NOT_AN_OBSERVED_OWNER_PRIVATE_LEDGER",
            "LOCAL_GENERATION_IS_NOT_TST_026_TST_029_OR_TST_032",
            "SCHEMA_SHAPED_INPUT_CANNOT_SELF_AUTHORIZE_FORMAL_EVIDENCE",
            "RECORDED_BASE_COMMIT_IS_NOT_A_SOURCE_FREEZE_OR_REVIEWED_TREE",
            "BLOCKED_RECORD_IS_NOT_GATE_APPROVAL_OR_SECURITY_SIGN_OFF",
            "NO_STATUS_PUBLICATION_STAGING_RELEASE_DEPLOYMENT_OR_PRODUCTION_AUTHORITY",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _source_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest_source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, record_bytes: bytes) -> bytes:
    manifest = {
        "story_id": "ST-1705",
        "schema_version": 1,
        "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
        "generation_command": GENERATION_COMMAND,
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_source_row(root, path) for path in SOURCE_PATHS],
        "bound_input_count": len(EXPECTED_SOURCE_HASHES)
        + len(EXPECTED_DEPENDENCY_HASHES),
        "bound_inputs": [
            {
                "uri": f"repo://{path}",
                "sha256": digest,
                "classification": "CANONICAL_AUTHORITY",
            }
            for path, digest in EXPECTED_SOURCE_HASHES.items()
        ]
        + [
            {
                "uri": f"repo://{path}",
                "sha256": digest,
                "classification": "NON_ATTESTING_DEPENDENCY_INPUT",
            }
            for path, digest in EXPECTED_DEPENDENCY_HASHES.items()
        ],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{DECISION_PATH.as_posix()}",
                "bytes": len(record_bytes),
                "sha256": _sha256(record_bytes),
            }
        ],
        "transaction": {
            "model": "TWO_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "writer_lock": "STORY_DIRECTORY_FLOCK",
            "check_pending_recovery": "READ_ONLY_REJECT",
        },
        "boundary": {
            "classification": "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING",
            "decision": "BLOCKED",
            "sign_off": "NOT_SIGNED_OFF",
            "pilot_eligibility": "NOT_ELIGIBLE",
            "active_blocking_open_decisions": 14,
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "source_freeze": "UNAVAILABLE",
            "reviewed_implementation_tree": "UNAVAILABLE",
            "publication_authority": "NONE",
            "release_authority": "NONE",
            "production_authority": "NONE",
        },
    }
    return yaml.safe_dump(
        manifest,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    record_bytes = _json_bytes(decision_record(contract))
    return {
        DECISION_PATH: record_bytes,
        MANIFEST_PATH: _manifest_bytes(root, record_bytes),
    }


@dataclass(frozen=True, slots=True)
class _Snapshot:
    content: bytes
    device: int
    inode: int
    mode: int
    owner: int
    links: int
    mtime_ns: int


@dataclass(slots=True)
class _Slot:
    relative: Path
    parent_fd: int
    parent_identity: tuple[int, int]
    target: str
    stage: str
    previous: str
    absent: str


@dataclass(slots=True)
class _DirectoryLock:
    descriptor: int
    identity: tuple[int, int]


def _validate_output_directory(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("UNSAFE_OUTPUT_ANCESTOR", "output")


def _open_output_parent(root: Path, relative: Path) -> tuple[int, tuple[int, int]]:
    _validate_relative(relative, "output")
    descriptor = _open_root(root, "output")
    try:
        _validate_output_directory(os.fstat(descriptor))
        for part in relative.parts[:-1]:
            try:
                path_metadata = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                _validate_output_directory(path_metadata)
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except FileNotFoundError:
                _fail("OUTPUT_PARENT_UNAVAILABLE", "output")
            except OSError:
                _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            child_metadata = os.fstat(child)
            if (child_metadata.st_dev, child_metadata.st_ino) != (
                path_metadata.st_dev,
                path_metadata.st_ino,
            ):
                _close(child)
                _fail("OUTPUT_ANCESTOR_CHANGED", "output")
            _close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        result = descriptor
        descriptor = -1
        return result, (metadata.st_dev, metadata.st_ino)
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _open_slots(root: Path) -> list[_Slot]:
    slots: list[_Slot] = []
    try:
        for relative in GENERATED_PATHS:
            parent_fd, identity = _open_output_parent(root, relative)
            slots.append(
                _Slot(
                    relative=relative,
                    parent_fd=parent_fd,
                    parent_identity=identity,
                    target=relative.name,
                    stage=f".{relative.name}{NEXT_SUFFIX}",
                    previous=f".{relative.name}{PREVIOUS_SUFFIX}",
                    absent=f".{relative.name}{ABSENT_SUFFIX}",
                )
            )
        return slots
    except BaseException:
        _close_slots(slots)
        raise


def _close_slots(slots: Sequence[_Slot]) -> None:
    for slot in slots:
        if slot.parent_fd >= 0:
            _close(slot.parent_fd)
            slot.parent_fd = -1


def _manifest_slot(slots: Sequence[_Slot]) -> _Slot:
    matches = [slot for slot in slots if slot.relative == MANIFEST_PATH]
    if len(matches) != 1:
        _fail("OUTPUT_INVENTORY_DRIFT", "output")
    return matches[0]


def _snapshot(
    slot: _Slot,
    name: str,
    field: str,
    *,
    missing_ok: bool,
    expected_mode: int | None = None,
) -> _Snapshot | None:
    try:
        path_metadata = os.stat(name, dir_fd=slot.parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        _fail("OUTPUT_RECOVERY_REQUIRED", field)
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", field)
    if (
        not stat.S_ISREG(path_metadata.st_mode)
        or path_metadata.st_uid != os.geteuid()
        or path_metadata.st_nlink != 1
    ):
        _fail("UNSAFE_OUTPUT_TARGET", field)
    mode = stat.S_IMODE(path_metadata.st_mode)
    if expected_mode is not None:
        if mode != expected_mode:
            _fail("UNSAFE_OUTPUT_MODE", field)
    elif mode & 0o022:
        _fail("UNSAFE_OUTPUT_MODE", field)
    if path_metadata.st_size < 0 or path_metadata.st_size > MAX_INPUT_BYTES:
        _fail("OUTPUT_SIZE_LIMIT", field)
    descriptor = -1
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=slot.parent_fd
        )
        metadata = os.fstat(descriptor)
        if _identity(path_metadata) != _identity(metadata):
            _fail("OUTPUT_TARGET_CHANGED", field)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(
                descriptor,
                min(READ_CHUNK_BYTES, MAX_INPUT_BYTES + 1 - total),
            )
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT_BYTES:
                _fail("OUTPUT_SIZE_LIMIT", field)
        content = b"".join(chunks)
        after = os.stat(name, dir_fd=slot.parent_fd, follow_symlinks=False)
        if _identity(metadata) != _identity(after) or len(content) != metadata.st_size:
            _fail("OUTPUT_TARGET_CHANGED", field)
        return _Snapshot(
            content=content,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            mode=mode,
            owner=metadata.st_uid,
            links=metadata.st_nlink,
            mtime_ns=metadata.st_mtime_ns,
        )
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _assert_parent(root: Path, slot: _Slot) -> None:
    descriptor, identity = _open_output_parent(root, slot.relative)
    try:
        if identity != slot.parent_identity:
            _fail("OUTPUT_ANCESTOR_CHANGED", "output")
    finally:
        _close(descriptor)


def _fsync(slot: _Slot) -> None:
    try:
        os.fsync(slot.parent_fd)
    except OSError:
        _fail("OUTPUT_FSYNC_FAILED", "output")


def _write_exclusive(
    slot: _Slot, name: str, content: bytes, mode: int, field: str
) -> None:
    descriptor = -1
    created = False
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=slot.parent_fd,
        )
        created = True
        os.fchmod(descriptor, mode)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write")
            view = view[written:]
        os.fsync(descriptor)
        _close(descriptor)
        descriptor = -1
        _fsync(slot)
        observed = _snapshot(slot, name, field, missing_ok=False, expected_mode=mode)
        if observed is None or observed.content != content:
            _fail("OUTPUT_COMPANION_DRIFT", field)
    except PilotSignoffError:
        raise
    except OSError:
        if created:
            try:
                os.unlink(name, dir_fd=slot.parent_fd)
                _fsync(slot)
            except OSError:
                _fail("OUTPUT_RECOVERY_REQUIRED", field)
        _fail("OUTPUT_WRITE_FAILED", field)
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _unlink(slot: _Slot, name: str) -> None:
    try:
        os.unlink(name, dir_fd=slot.parent_fd)
        _fsync(slot)
    except OSError:
        _fail("OUTPUT_RECOVERY_REQUIRED", "output")


def _transaction_path_state(
    slots: Sequence[_Slot], name: str, *, missing_ok: bool
) -> Mapping[str, Any] | None:
    slot = _manifest_slot(slots)
    snapshot = _snapshot(
        slot,
        name,
        "transaction",
        missing_ok=missing_ok,
        expected_mode=PRIVATE_MODE,
    )
    if snapshot is None:
        return None

    def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                _fail("TRANSACTION_INVALID", "transaction")
            result[key] = value
        return result

    try:
        value = json.loads(
            snapshot.content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _fail("TRANSACTION_INVALID", "transaction"),
        )
    except PilotSignoffError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("TRANSACTION_INVALID", "transaction")
    return _mapping(value, "transaction")


def _expected_transaction(
    state: str,
    outputs: Mapping[Path, bytes],
    originals: Mapping[Path, _Snapshot | None],
) -> dict[str, object]:
    return {
        "schema": TRANSACTION_SCHEMA,
        "state": state,
        "outputs": [
            {
                "path": relative.as_posix(),
                "next_sha256": _sha256(outputs[relative]),
                "original_present": originals[relative] is not None,
                "original_sha256": _optional_snapshot_hash(originals[relative]),
            }
            for relative in GENERATED_PATHS
        ],
    }


def _transaction_bytes(value: Mapping[str, object]) -> bytes:
    return _json_bytes(value)


def _optional_snapshot_hash(snapshot: _Snapshot | None) -> str | None:
    return _sha256(snapshot.content) if snapshot is not None else None


def _decode_transaction_rows(
    transaction: Mapping[str, Any], state: str
) -> tuple[dict[Path, str], dict[Path, str | None]]:
    if tuple(transaction) != ("schema", "state", "outputs"):
        _fail("TRANSACTION_INVALID", "transaction")
    if (
        transaction.get("schema") != TRANSACTION_SCHEMA
        or transaction.get("state") != state
    ):
        _fail("TRANSACTION_INVALID", "transaction")
    rows = _list(transaction.get("outputs"), "transaction.outputs")
    if len(rows) != len(GENERATED_PATHS):
        _fail("TRANSACTION_INVALID", "transaction.outputs")
    next_hashes: dict[Path, str] = {}
    original_hashes: dict[Path, str | None] = {}
    for index, relative in enumerate(GENERATED_PATHS):
        row = _mapping(rows[index], f"transaction.outputs[{index}]")
        if (
            tuple(row)
            != (
                "path",
                "next_sha256",
                "original_present",
                "original_sha256",
            )
            or row.get("path") != relative.as_posix()
        ):
            _fail("TRANSACTION_INVALID", "transaction.outputs")
        next_digest = row.get("next_sha256")
        original_present = row.get("original_present")
        original_digest = row.get("original_sha256")
        if (
            type(next_digest) is not str
            or len(next_digest) != 64
            or any(character not in "0123456789abcdef" for character in next_digest)
            or type(original_present) is not bool
            or (
                original_present
                and (
                    type(original_digest) is not str
                    or len(original_digest) != 64
                    or any(
                        character not in "0123456789abcdef"
                        for character in original_digest
                    )
                )
            )
            or (not original_present and original_digest is not None)
        ):
            _fail("TRANSACTION_INVALID", "transaction.outputs")
        next_hashes[relative] = next_digest
        original_hashes[relative] = original_digest
    return next_hashes, original_hashes


def _fixed_companions_present(slots: Sequence[_Slot]) -> bool:
    coordinator = _manifest_slot(slots)
    if (
        _snapshot(
            coordinator,
            TRANSACTION_NAME,
            "transaction",
            missing_ok=True,
            expected_mode=PRIVATE_MODE,
        )
        is not None
        or _snapshot(
            coordinator,
            TRANSACTION_NEXT_NAME,
            "transaction",
            missing_ok=True,
            expected_mode=PRIVATE_MODE,
        )
        is not None
    ):
        return True
    for slot in slots:
        for name, mode in (
            (slot.stage, OUTPUT_MODE),
            (slot.previous, None),
            (slot.absent, PRIVATE_MODE),
        ):
            if (
                _snapshot(
                    slot,
                    name,
                    "output_companion",
                    missing_ok=True,
                    expected_mode=mode,
                )
                is not None
            ):
                return True
    return False


def _recover_pending(root: Path, slots: Sequence[_Slot], *, mutate: bool) -> None:
    transaction = _transaction_path_state(slots, TRANSACTION_NAME, missing_ok=True)
    transaction_next = _transaction_path_state(
        slots, TRANSACTION_NEXT_NAME, missing_ok=True
    )
    if transaction is None:
        if transaction_next is not None or _fixed_companions_present(slots):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction")
        return
    if not mutate:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction")
    state = transaction.get("state")
    if state not in {"PREPARED", "COMMITTED"}:
        _fail("TRANSACTION_INVALID", "transaction")
    next_hashes, original_hashes = _decode_transaction_rows(transaction, state)
    coordinator = _manifest_slot(slots)
    if transaction_next is not None:
        if state != "PREPARED":
            _fail("TRANSACTION_INVALID", "transaction")
        committed_next_hashes, committed_original_hashes = _decode_transaction_rows(
            transaction_next, "COMMITTED"
        )
        if (
            committed_next_hashes != next_hashes
            or committed_original_hashes != original_hashes
        ):
            _fail("TRANSACTION_INVALID", "transaction")

    if state == "COMMITTED":
        for slot in slots:
            _assert_parent(root, slot)
            target = _snapshot(slot, slot.target, "generated_output", missing_ok=False)
            if target is None or _sha256(target.content) != next_hashes[slot.relative]:
                _fail("COMMITTED_OUTPUT_DRIFT", "generated_output")
            if (
                _snapshot(slot, slot.stage, "output_companion", missing_ok=True)
                is not None
            ):
                _fail("TRANSACTION_INVALID", "output_companion")
        for slot in slots:
            previous = _snapshot(
                slot, slot.previous, "output_companion", missing_ok=True
            )
            absent = _snapshot(
                slot,
                slot.absent,
                "output_companion",
                missing_ok=True,
                expected_mode=PRIVATE_MODE,
            )
            if (previous is None) == (absent is None):
                _fail("TRANSACTION_INVALID", "output_companion")
            if previous is not None:
                _unlink(slot, slot.previous)
            if absent is not None:
                if absent.content != ABSENT_MARKER:
                    _fail("TRANSACTION_INVALID", "output_companion")
                _unlink(slot, slot.absent)
        _unlink(coordinator, TRANSACTION_NAME)
        return

    for slot in slots:
        _assert_parent(root, slot)
        stage = _snapshot(
            slot,
            slot.stage,
            "output_companion",
            missing_ok=True,
            expected_mode=OUTPUT_MODE,
        )
        if stage is not None and _sha256(stage.content) != next_hashes[slot.relative]:
            _fail("TRANSACTION_INVALID", "output_companion")
        previous = _snapshot(slot, slot.previous, "output_companion", missing_ok=True)
        absent = _snapshot(
            slot,
            slot.absent,
            "output_companion",
            missing_ok=True,
            expected_mode=PRIVATE_MODE,
        )
        target = _snapshot(slot, slot.target, "generated_output", missing_ok=True)
        original_digest = original_hashes[slot.relative]
        if original_digest is not None:
            if absent is not None:
                _fail("TRANSACTION_INVALID", "output_companion")
            if previous is not None:
                if _sha256(previous.content) != original_digest:
                    _fail("TRANSACTION_INVALID", "output_companion")
                if target is not None:
                    if _sha256(target.content) != next_hashes[slot.relative]:
                        _fail("TRANSACTION_INVALID", "generated_output")
                    _unlink(slot, slot.target)
                try:
                    os.replace(
                        slot.previous,
                        slot.target,
                        src_dir_fd=slot.parent_fd,
                        dst_dir_fd=slot.parent_fd,
                    )
                    _fsync(slot)
                except OSError:
                    _fail("OUTPUT_RECOVERY_REQUIRED", "output")
            elif target is None or _sha256(target.content) != original_digest:
                _fail("TRANSACTION_INVALID", "generated_output")
        else:
            if previous is not None:
                _fail("TRANSACTION_INVALID", "output_companion")
            if absent is not None:
                if absent.content != ABSENT_MARKER:
                    _fail("TRANSACTION_INVALID", "output_companion")
                if target is not None:
                    if _sha256(target.content) != next_hashes[slot.relative]:
                        _fail("TRANSACTION_INVALID", "generated_output")
                    _unlink(slot, slot.target)
                _unlink(slot, slot.absent)
            elif target is not None:
                _fail("TRANSACTION_INVALID", "generated_output")
        if stage is not None:
            _unlink(slot, slot.stage)
    if transaction_next is not None:
        _unlink(coordinator, TRANSACTION_NEXT_NAME)
    _unlink(coordinator, TRANSACTION_NAME)


def _transaction_checkpoint(_name: str) -> None:
    """Test-only crash boundary; production execution is inert."""


def _write_transaction(
    root: Path, outputs: Mapping[Path, bytes], slots: Sequence[_Slot]
) -> None:
    if tuple(outputs) != GENERATED_PATHS:
        _fail("OUTPUT_INVENTORY_DRIFT", "output")
    if _fixed_companions_present(slots):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction")
    originals: dict[Path, _Snapshot | None] = {}
    for slot in slots:
        _assert_parent(root, slot)
        originals[slot.relative] = _snapshot(
            slot, slot.target, "generated_output", missing_ok=True
        )
    prepared = _expected_transaction("PREPARED", outputs, originals)
    coordinator = _manifest_slot(slots)
    _write_exclusive(
        coordinator,
        TRANSACTION_NAME,
        _transaction_bytes(prepared),
        PRIVATE_MODE,
        "transaction",
    )
    _transaction_checkpoint("PREPARED")
    for slot in slots:
        _write_exclusive(
            slot, slot.stage, outputs[slot.relative], OUTPUT_MODE, "output_stage"
        )
        _transaction_checkpoint(f"STAGED_{slot.relative.as_posix()}")
    for slot in slots:
        _assert_parent(root, slot)
        observed = _snapshot(slot, slot.target, "generated_output", missing_ok=True)
        original = originals[slot.relative]
        if (observed is None) != (original is None) or (
            observed is not None
            and original is not None
            and _sha256(observed.content) != _sha256(original.content)
        ):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        try:
            if original is None:
                _write_exclusive(
                    slot,
                    slot.absent,
                    ABSENT_MARKER,
                    PRIVATE_MODE,
                    "output_companion",
                )
            else:
                os.replace(
                    slot.target,
                    slot.previous,
                    src_dir_fd=slot.parent_fd,
                    dst_dir_fd=slot.parent_fd,
                )
                _fsync(slot)
            _transaction_checkpoint(f"BACKED_UP_{slot.relative.as_posix()}")
            os.replace(
                slot.stage,
                slot.target,
                src_dir_fd=slot.parent_fd,
                dst_dir_fd=slot.parent_fd,
            )
            _fsync(slot)
        except PilotSignoffError:
            raise
        except OSError:
            _fail("OUTPUT_TRANSACTION_FAILED", "output")
        target = _snapshot(slot, slot.target, "generated_output", missing_ok=False)
        if target is None or target.content != outputs[slot.relative]:
            _fail("OUTPUT_PUBLISH_DRIFT", "output")
        _transaction_checkpoint(f"PUBLISHED_{slot.relative.as_posix()}")
    committed = _expected_transaction("COMMITTED", outputs, originals)
    _write_exclusive(
        coordinator,
        TRANSACTION_NEXT_NAME,
        _transaction_bytes(committed),
        PRIVATE_MODE,
        "transaction",
    )
    try:
        os.replace(
            TRANSACTION_NEXT_NAME,
            TRANSACTION_NAME,
            src_dir_fd=coordinator.parent_fd,
            dst_dir_fd=coordinator.parent_fd,
        )
        _fsync(coordinator)
    except OSError:
        _fail("OUTPUT_TRANSACTION_FAILED", "transaction")
    _transaction_checkpoint("COMMITTED")
    _recover_pending(root, slots, mutate=True)


def _acquire_lock(root: Path, *, shared: bool) -> _DirectoryLock:
    descriptor, identity = _open_output_parent(root, MANIFEST_PATH)
    try:
        fcntl.flock(
            descriptor,
            (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB,
        )
        return _DirectoryLock(descriptor=descriptor, identity=identity)
    except BlockingIOError:
        _close(descriptor)
        _fail("CONCURRENT_OUTPUT_WRITER", "writer_lock")
    except OSError:
        _close(descriptor)
        _fail("OUTPUT_LOCK_FAILED", "writer_lock")


def _release_lock(lock: _DirectoryLock) -> None:
    try:
        metadata = os.fstat(lock.descriptor)
        if (metadata.st_dev, metadata.st_ino) != lock.identity:
            _fail("OUTPUT_LOCK_DRIFT", "writer_lock")
        fcntl.flock(lock.descriptor, fcntl.LOCK_UN)
    except OSError:
        _fail("OUTPUT_LOCK_FAILED", "writer_lock")
    finally:
        _close(lock.descriptor)
        lock.descriptor = -1


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    for relative in GENERATED_PATHS:
        if _read(root, relative, "generated_output") != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "generated_output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    lock = _acquire_lock(root, shared=check)
    slots: list[_Slot] = []
    try:
        slots = _open_slots(root)
        _recover_pending(root, slots, mutate=not check)
        outputs = render_outputs(root)
        if check:
            check_outputs(root, outputs)
        else:
            try:
                _write_transaction(root, outputs, slots)
            except Exception:
                _recover_pending(root, slots, mutate=True)
                raise
    finally:
        _close_slots(slots)
        _release_lock(lock)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the local blocked ST-1705 sign-off decision."
    )
    parser.add_argument(
        "--check", action="store_true", help="verify outputs without writing"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except PilotSignoffError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
