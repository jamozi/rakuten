#!/usr/bin/env python3
"""Build the deterministic, non-attesting ST-1607 blocked gate report."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys

if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print(
            "ST1607_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1607_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
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
CONTRACT_PATH: Final = Path("changes/st-1607/contracts/gate-evidence-pack.v1.yaml")
REPORT_PATH: Final = Path(
    "changes/st-1607/generated/gate-evidence-pack.local-blocked.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1607/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1607_gate_evidence_pack.py")
README_PATH: Final = Path("changes/st-1607/README.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1607/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
TEST_PATHS: Final = (
    Path("tests/st1607/conftest.py"),
    Path("tests/st1607/test_contract.py"),
    Path("tests/st1607/test_generation.py"),
    Path("tests/st1607/test_negative_cases.py"),
    Path("tests/st1607/test_gate_report.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    README_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)
GENERATED_PATHS: Final = (REPORT_PATH, MANIFEST_PATH)

NEXT_SUFFIX: Final = ".st1607.next"
PREVIOUS_SUFFIX: Final = ".st1607.previous"
ABSENT_SUFFIX: Final = ".st1607.absent"
TRANSACTION_STATE_NAME: Final = f".{MANIFEST_PATH.name}.st1607.transaction"
TRANSACTION_STATE_NEXT_NAME: Final = f"{TRANSACTION_STATE_NAME}.next"
ROLLBACK_STATE: Final = b"ST1607_OUTPUT_TRANSACTION_ROLLBACK_V1\n"
COMMIT_STATE: Final = b"ST1607_OUTPUT_TRANSACTION_COMMIT_V1\n"
ABSENT_MARKER: Final = b"ST1607_OUTPUT_WAS_ABSENT_V1\n"
OUTPUT_MODE: Final = 0o644
PRIVATE_COMPANION_MODE: Final = 0o600

SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run "
    "--locked --offline --no-cache --no-sync --no-env-file "
    "python -I -B scripts/build_st1607_gate_evidence_pack.py"
)
LOCAL_BASE_COMMIT: Final = "a3ea6d1a1e8621d9ff198c9dea31b0c6f7a768d5"
LOCAL_BASE_COMMIT_TYPE: Final = "GIT_SHA1_LOWER_HEX_40"
LOCAL_BASE_COMMIT_STATUS: Final = "RECORDED_PREDECESSOR_CHECKOUT_ONLY"
REVIEWED_TREE_COMMIT_TYPE: Final = "OPTIONAL_GIT_SHA1_LOWER_HEX_40"
SOURCE_FREEZE_ID_TYPE: Final = "OPTIONAL_SHA256_LOWER_HEX_64"
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 1024 * 1024

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "dependency_bindings",
    "decision_gate_binding",
    "status_input",
    "decision_input",
    "snapshot_boundary",
    "required_evidence",
    "global_blockers",
    "gate_report",
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
    "docs/canonical/01_integration/RAOS_07_status_taxonomy_v1.0.yaml": (
        "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b"
    ),
    "docs/canonical/00_master/RAOS_implementation_status_registry_v1.0.yaml": (
        "1411f55ce60f6316e83567110fb2847e0db49239cb63dcabf9e81612c3b72ab8"
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
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": (
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
}

EXPECTED_DEPENDENCY_HASHES: Final = {
    "changes/st-0005/contracts/status-policy.v1.yaml": (
        "15969f4d5db3aee48059ece1fb572786f25bc0807eb34458b36f97f63f8ccfaf"
    ),
    "changes/st-0005/status-overlay.v1.yaml": (
        "d8f432c8fe79d6e4066a33c55d00527f23f93c2a810f88b0d8555bd317b77b90"
    ),
    "changes/st-0005/manifest.yaml": (
        "10bcbe759f9c1aa89d064748136b88a6694500956f049a6679041fe44e0785ce"
    ),
    "changes/st-1603/contracts/security-verification-pack.v1.yaml": (
        "582ccca3eaf82b1b04a48bee7f4b68f6592517b72d8758423ae0235650f2fd55"
    ),
    "changes/st-1603/generated/security-verification-pack.reference-plan.v1.json": (
        "8fb4460e5e1b6c6439ac9b34dd7735f05b8fefa89fae1589f592d4f3a2fd38f3"
    ),
    "changes/st-1603/manifest.yaml": (
        "bce4c04cbba7ae8bfa927e0cf7a580a7089fa5e2bc3bd037643fbb0a6b27d3c1"
    ),
    "changes/st-1605/contracts/failure-injection-drill.v1.yaml": (
        "38a2510ee368938227fe3b20b25671e6f0df42b105314650badcbe374e04d706"
    ),
    "changes/st-1605/generated/failure-injection-drill.local-synthetic-evidence.v1.json": (
        "898df290a5bcfc738e4c7e12405b5478bb4dd659a58a68c77f1a542e48aa722d"
    ),
    "changes/st-1605/manifest.yaml": (
        "553b56a102645c81963732954ab2664a7206fc7648ff4cdacff10d565c260594"
    ),
    "changes/st-1606/contracts/backup-restore-drill.v1.yaml": (
        "fad487c3c241f1105056fbd1f7d5a5ce936b404496dfdda392473a92af657363"
    ),
    "changes/st-1606/generated/backup-restore-drill.reference-plan.v1.json": (
        "2e8c1c801e4f3dce50677d7c29e6eb20dcaa604db6499b4b5d8f01512a055903"
    ),
    "changes/st-1606/manifest.yaml": (
        "64b75ebe1418896458c980bbfcb3bc5f1ac47f7b99809a4a55d7333a3b80becc"
    ),
}

EXPECTED_DECISION_GATE_HASHES: Final = {
    "changes/st-0006/contracts/decision-gate-policy.v1.yaml": (
        "127da325fa02682f2d3ce13bedfb0830e47eb17db401fa4d94b73c698d08d989"
    ),
    "changes/st-0006/gate-blocker-report.v1.yaml": (
        "92fc3fdbe021db08508bc0cc5ee1f6542de94d5fc336b40e45ace30037bdff15"
    ),
    "changes/st-0006/manifest.yaml": (
        "bbff3aee2fb89a4ecf45bfb92550d06b3936cceb7f3bce247f45daf5b9ca82be"
    ),
}

EXPECTED_IMPLEMENTATION_HASHES: Final = {
    "scripts/build_st1505_staging_deployment.py": (
        "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
    )
}

GATE_IDS: Final = ("GATE-0", "GATE-1", "GATE-2", "GATE-3", "GATE-4")
DECISION_TARGETS: Final = (*GATE_IDS, "PRODUCTION_RELEASE")
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
GLOBAL_BLOCKERS: Final = (
    "TARGET_SNAPSHOT_CONTEXT_MISSING",
    "ST_1603_SECURITY_EVIDENCE_INELIGIBLE",
    "ST_1605_FAILURE_INJECTION_EVIDENCE_INELIGIBLE",
    "ST_1606_BACKUP_RESTORE_EVIDENCE_INELIGIBLE",
    "ACTIVE_BLOCKING_OPEN_DECISIONS",
    "FORMAL_TST_032_NOT_EXECUTED",
    "HUMAN_GATE_APPROVALS_MISSING",
)


class GateEvidencePackError(RuntimeError):
    """Closed, sanitized ST-1607 validation failure."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"ST1607_ERROR code={code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


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
    raise GateEvidencePackError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_TYPE", field)
    if any(type(key) is not str for key in value):
        _fail("INVALID_KEY", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("INVALID_TYPE", field)
    return value


def _exact(value: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        if tuple(observed.keys()) != tuple(expected.keys()):
            _fail("CLOSED_SCHEMA_DRIFT", field)
        for key, expected_value in expected.items():
            _exact(observed[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        observed_list = _list(value, field)
        expected_list = _list(expected, field)
        if not expected_list and observed_list:
            _fail("SAFE_BOUNDARY_DRIFT", field)
        if len(observed_list) != len(expected_list):
            _fail("FIXED_INVENTORY_DRIFT", field)
        for index, expected_value in enumerate(expected_list):
            _exact(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        if expected is None or type(expected) is bool or expected == 0:
            _fail("SAFE_BOUNDARY_DRIFT", field)
        _fail("FIXED_VALUE_DRIFT", field)


def _strict_lower_hex(value: object, length: int, field: str) -> str:
    if (
        type(value) is not str
        or len(value) != length
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail("INVALID_TYPED_IDENTITY", field)
    return value


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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


def _absolute_lexical_root(root: Path) -> Path:
    if not root.parts or any(part in {"", ".", ".."} for part in root.parts):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    absolute = root if root.is_absolute() else Path.cwd() / root
    normalized = Path(os.path.abspath(os.fspath(absolute)))
    if not normalized.is_absolute() or any(
        part in {"", ".", ".."} for part in normalized.parts[1:]
    ):
        _fail("UNSAFE_ROOT_TYPE", "repository")
    return normalized


def _open_repository_root(root: Path, field: str) -> int:
    absolute = _absolute_lexical_root(root)
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
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("ROOT_UNAVAILABLE", field)
    finally:
        _close_descriptors(descriptors)


def _validate_repository_relative(relative: Path, field: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_REPOSITORY_PATH", field)


def _input_path_walk_checkpoint(_root_descriptor: int, _relative: Path) -> None:
    """Test-only race boundary after the physical repository root is captured."""


def _stable_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
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
    _validate_repository_relative(relative, field)
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
    directories = [_open_repository_root(root, field)]
    descriptor = -1
    try:
        _input_path_walk_checkpoint(directories[0], relative)
        for part in relative.parts[:-1]:
            try:
                child = os.open(part, directory_flags, dir_fd=directories[-1])
            except FileNotFoundError:
                _fail("FILE_UNAVAILABLE", field)
            except OSError:
                _fail("UNSAFE_ANCESTOR", field)
            directories.append(child)
        try:
            path_before = os.stat(
                relative.name,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
        except FileNotFoundError:
            _fail("FILE_UNAVAILABLE", field)
        except OSError:
            _fail("UNSAFE_FILE_TYPE", field)
        if not stat.S_ISREG(path_before.st_mode):
            _fail("UNSAFE_FILE_TYPE", field)
        try:
            descriptor = os.open(
                relative.name,
                file_flags,
                dir_fd=directories[-1],
            )
        except FileNotFoundError:
            _fail("FILE_UNAVAILABLE", field)
        except OSError:
            _fail("UNSAFE_FILE_TYPE", field)
        metadata_before = os.fstat(descriptor)
        if not stat.S_ISREG(metadata_before.st_mode):
            _fail("UNSAFE_FILE_TYPE", field)
        if _stable_file_identity(path_before) != _stable_file_identity(metadata_before):
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
        if len(content) > MAX_INPUT_BYTES:
            _fail("INPUT_SIZE_LIMIT", field)
        metadata_after = os.fstat(descriptor)
        try:
            path_after = os.stat(
                relative.name,
                dir_fd=directories[-1],
                follow_symlinks=False,
            )
        except OSError:
            _fail("INPUT_CHANGED_DURING_READ", field)
        identities = {
            _stable_file_identity(path_before),
            _stable_file_identity(metadata_before),
            _stable_file_identity(metadata_after),
            _stable_file_identity(path_after),
        }
        if len(identities) != 1 or len(content) != metadata_before.st_size:
            _fail("INPUT_CHANGED_DURING_READ", field)
        return content
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    finally:
        if descriptor >= 0:
            _close_descriptor(descriptor)
        _close_descriptors(directories)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", field)
        loaded = yaml.load(text, Loader=UniqueKeyLoader)
    except GateEvidencePackError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", field)
    return _mapping(loaded, field)


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
        loaded = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: _fail("JSON_INVALID", field),
        )
    except GateEvidencePackError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(loaded, field)


def _uri_path(value: object, field: str) -> Path:
    if type(value) is not str or not value.startswith("repo://"):
        _fail("INVALID_URI", field)
    relative = Path(value.removeprefix("repo://"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("INVALID_URI", field)
    return relative


def _verify_hash_rows(
    root: Path, rows: object, expected: Mapping[str, str], field: str
) -> None:
    records = _list(rows, field)
    if len(records) != len(expected):
        _fail("SOURCE_INVENTORY_DRIFT", field)
    observed: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        row = _mapping(raw, f"{field}[{index}]")
        if tuple(row.keys()) != ("uri", "sha256"):
            _fail("SOURCE_SCHEMA_DRIFT", f"{field}[{index}]")
        relative = _uri_path(row["uri"], f"{field}[{index}].uri")
        digest = row["sha256"]
        if type(digest) is not str:
            _fail("INVALID_TYPE", f"{field}[{index}].sha256")
        observed.append((relative.as_posix(), digest))
    if observed != list(expected.items()):
        _fail("SOURCE_INVENTORY_DRIFT", field)
    _verify_files(root, expected, "SOURCE_HASH_DRIFT", field)


def _verify_files(
    root: Path,
    expected: Mapping[str, str],
    error_code: str,
    field: str,
) -> None:
    for path, digest in expected.items():
        if _sha256_bytes(_read(root, Path(path), f"{field}.input")) != digest:
            _fail(error_code, field)


def _artifact_rows(
    rows: Sequence[tuple[str, str]], expected: Mapping[str, str]
) -> list[dict[str, object]]:
    return [
        {
            "kind": kind,
            "uri": f"repo://{path}",
            "sha256": expected[path],
        }
        for kind, path in rows
    ]


def _expected_dependency_bindings() -> dict[str, object]:
    return {
        "st_0005": {
            "story_id": "ST-0005",
            "role": "STATUS_SOURCE",
            "artifacts": _artifact_rows(
                (
                    ("CONTRACT", "changes/st-0005/contracts/status-policy.v1.yaml"),
                    (
                        "GENERATED_STATUS_OVERLAY",
                        "changes/st-0005/status-overlay.v1.yaml",
                    ),
                    ("MANIFEST", "changes/st-0005/manifest.yaml"),
                ),
                EXPECTED_DEPENDENCY_HASHES,
            ),
        },
        "st_1603": {
            "story_id": "ST-1603",
            "role": "SECURITY_VERIFICATION_INPUT",
            "artifacts": _artifact_rows(
                (
                    (
                        "CONTRACT",
                        "changes/st-1603/contracts/security-verification-pack.v1.yaml",
                    ),
                    (
                        "GENERATED_REFERENCE_PLAN",
                        "changes/st-1603/generated/"
                        "security-verification-pack.reference-plan.v1.json",
                    ),
                    ("MANIFEST", "changes/st-1603/manifest.yaml"),
                ),
                EXPECTED_DEPENDENCY_HASHES,
            ),
        },
        "st_1605": {
            "story_id": "ST-1605",
            "role": "FAILURE_INJECTION_INPUT",
            "artifacts": _artifact_rows(
                (
                    (
                        "CONTRACT",
                        "changes/st-1605/contracts/failure-injection-drill.v1.yaml",
                    ),
                    (
                        "GENERATED_LOCAL_SYNTHETIC_EVIDENCE",
                        "changes/st-1605/generated/"
                        "failure-injection-drill.local-synthetic-evidence.v1.json",
                    ),
                    ("MANIFEST", "changes/st-1605/manifest.yaml"),
                ),
                EXPECTED_DEPENDENCY_HASHES,
            ),
        },
        "st_1606": {
            "story_id": "ST-1606",
            "role": "BACKUP_RESTORE_INPUT",
            "artifacts": _artifact_rows(
                (
                    (
                        "CONTRACT",
                        "changes/st-1606/contracts/backup-restore-drill.v1.yaml",
                    ),
                    (
                        "GENERATED_REFERENCE_PLAN",
                        "changes/st-1606/generated/"
                        "backup-restore-drill.reference-plan.v1.json",
                    ),
                    ("MANIFEST", "changes/st-1606/manifest.yaml"),
                ),
                EXPECTED_DEPENDENCY_HASHES,
            ),
        },
    }


EXPECTED_DOCUMENT: Final[dict[str, object]] = {
    "id": "RAOS-GATE-EVIDENCE-PACK-001",
    "version": "1.0.0",
    "story_id": "ST-1607",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "classification": "LOCAL_BLOCKED_GATE_EVIDENCE_PACK_NON_ATTESTING",
    "acceptance_criteria_satisfied": False,
    "formal_verification": "NOT_EXECUTED",
}


def _expected_decision_gate_binding() -> dict[str, object]:
    return {
        "story_id": "ST-0006",
        "role": "OPEN_DECISION_BLOCKER_INPUT",
        "artifacts": _artifact_rows(
            (
                (
                    "POLICY",
                    "changes/st-0006/contracts/decision-gate-policy.v1.yaml",
                ),
                (
                    "GENERATED_BLOCKER_REPORT",
                    "changes/st-0006/gate-blocker-report.v1.yaml",
                ),
                ("MANIFEST", "changes/st-0006/manifest.yaml"),
            ),
            EXPECTED_DECISION_GATE_HASHES,
        ),
        "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
        "target_policy": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
        "clear_means_gate_pass": False,
    }


EXPECTED_DECISION_GATE_BINDING: Final[dict[str, object]] = (
    _expected_decision_gate_binding()
)

EXPECTED_STATUS_INPUT: Final[dict[str, object]] = {
    "source_story": "ST-0005",
    "applied_transition_count": 0,
    "effective_story_statuses": [
        {
            "story_id": "ST-1603",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
            "required_suites": ["TST-026", "TST-031"],
        },
        {
            "story_id": "ST-1605",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
            "required_suites": ["TST-028"],
        },
        {
            "story_id": "ST-1606",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
            "required_suites": ["TST-029"],
        },
        {
            "story_id": "ST-1607",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
            "required_suites": ["TST-032"],
        },
    ],
    "formal_suite": {
        "suite_id": "TST-032",
        "required_environment": "STAGING",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    "effective_canonical_status": "UNCHANGED",
}

EXPECTED_DECISION_INPUT: Final[dict[str, object]] = {
    "overall_open_decision_check": "BLOCKED",
    "unresolved_blocking_count": 14,
    "active_blocker_ids": list(ACTIVE_BLOCKER_IDS),
    "blocker_targets": list(DECISION_TARGETS),
    "decision_clearance": "NOT_AVAILABLE",
}

EXPECTED_SNAPSHOT: Final[dict[str, object]] = {
    "pack_scope": list(GATE_IDS),
    "local_base_commit": LOCAL_BASE_COMMIT,
    "local_base_commit_type": LOCAL_BASE_COMMIT_TYPE,
    "local_base_commit_status": LOCAL_BASE_COMMIT_STATUS,
    "local_base_commit_scope": "PREDECESSOR_CHECKOUT_PROVENANCE_ONLY",
    "local_base_commit_qualifying_evidence": False,
    "source_freeze_identifier_type": SOURCE_FREEZE_ID_TYPE,
    "source_freeze_status": "ABSENT",
    "source_freeze_identifier": None,
    "source_freeze_qualifying_evidence": False,
    "reviewed_implementation_tree_commit_type": REVIEWED_TREE_COMMIT_TYPE,
    "reviewed_implementation_tree_commit_status": "ABSENT",
    "reviewed_implementation_tree_commit": None,
    "reviewed_implementation_tree_commit_qualifying_evidence": False,
    "target_release_version": None,
    "target_environment": "STAGING",
    "staging_execution_identifier": None,
    "snapshot_observed_at": None,
    "data_snapshot_identifier": None,
    "release_identifier": None,
    "approved_exceptions": [],
    "human_approval_artifacts": [],
}

EXPECTED_REQUIRED_EVIDENCE: Final[list[dict[str, object]]] = [
    {
        "evidence_id": "TARGET_SNAPSHOT_CONTEXT",
        "status": "MISSING",
        "source_references": [],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "ST_1603_SECURITY_VERIFICATION",
        "status": "INELIGIBLE_NON_ATTESTING_REFERENCE_PLAN",
        "source_references": [
            "repo://changes/st-1603/generated/"
            "security-verification-pack.reference-plan.v1.json"
        ],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "ST_1605_FAILURE_INJECTION",
        "status": "INELIGIBLE_LOCAL_SYNTHETIC_NON_ATTESTING",
        "source_references": [
            "repo://changes/st-1605/generated/"
            "failure-injection-drill.local-synthetic-evidence.v1.json"
        ],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "ST_1606_BACKUP_RESTORE",
        "status": "INELIGIBLE_NON_ATTESTING_REFERENCE_PLAN",
        "source_references": [
            "repo://changes/st-1606/generated/"
            "backup-restore-drill.reference-plan.v1.json"
        ],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "OPEN_DECISION_CLEARANCE",
        "status": "BLOCKED",
        "source_references": ["repo://changes/st-0006/gate-blocker-report.v1.yaml"],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "FORMAL_TST_032_STAGING",
        "status": "NOT_EXECUTED",
        "source_references": [
            "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
        ],
        "qualifying_evidence_references": [],
    },
    {
        "evidence_id": "HUMAN_GATE_APPROVALS",
        "status": "MISSING",
        "source_references": [],
        "qualifying_evidence_references": [],
    },
]


def _expected_gate_report() -> dict[str, object]:
    return {
        "mapping_policy": {
            "suite_to_gate_mapping": "NOT_DEFINED_BY_CANONICAL",
            "inferred_suite_to_gate_mapping": "FORBIDDEN",
            "blocker_application": "GLOBAL_BLOCKERS_APPLY_TO_EVERY_GATE",
        },
        "gates": [
            {
                "gate_id": gate_id,
                "status": "BLOCKED",
                "blocker_scope": "GLOBAL_ONLY",
                "blocker_codes": list(GLOBAL_BLOCKERS),
                "qualifying_evidence_references": [],
                "approval_status": "NOT_REQUESTED",
            }
            for gate_id in GATE_IDS
        ],
    }


EXPECTED_AUTHORITY: Final[dict[str, object]] = {
    "external_authority": "NONE",
    "owner_gate_approval_authority": "NONE",
    "status_apply_authority": "NONE",
    "staging_authority": "NONE",
    "publication_authority": "NONE",
    "release_authority": "NONE",
    "production_authority": "NONE",
    "approval_artifacts": [],
}

EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "executable": False,
    "local_report_generation_only": True,
    "input_size_limit_bytes": MAX_INPUT_BYTES,
    "input_read_model": "ROOT_FD_DESCRIPTOR_RELATIVE_CAPTURED_LEAF",
    "implementation_input_behavior": ("HASH_VERIFY_ONLY_NEVER_IMPORT_OR_EXECUTE"),
    "writer_model": "SINGLE_PROCESS_SAME_UID_EXCLUSIVE_LOCK",
    "concurrent_writer_behavior": "FAIL_CLOSED",
    "output_transaction": "TWO_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
    "pending_recovery_before_source_validation": True,
    "check_pending_recovery_behavior": "READ_ONLY_REJECT",
    "network_access": "FORBIDDEN",
    "environment_access": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "provider_calls": "FORBIDDEN",
    "subprocess_execution": "FORBIDDEN",
    "external_writes": "FORBIDDEN",
    "staging_actions": "FORBIDDEN",
    "status_actions": "FORBIDDEN",
    "publication_actions": "FORBIDDEN",
    "release_actions": "FORBIDDEN",
    "production_actions": "FORBIDDEN",
    "external_action_count": 0,
}

EXPECTED_EVIDENCE: Final[dict[str, object]] = {
    "classification": "LOCAL_BLOCKED_GATE_EVIDENCE_PACK_NON_ATTESTING",
    "formal_tst_032": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "live_provider": "NOT_EXECUTED",
    "owner_gate_approvals": "NONE",
    "approved_exceptions": "NONE",
    "release": "NOT_AUTHORIZED",
    "production": "NOT_AUTHORIZED",
    "validated_claim": False,
    "gate_pass_claim": False,
    "story_acceptance": False,
    "release_eligible": False,
    "production_ready": False,
    "effective_canonical_status": "UNCHANGED",
}


def _find_record(
    document: Mapping[str, Any],
    collection: str,
    key: str,
    record_id: str,
    field: str,
) -> Mapping[str, Any]:
    matches = [
        _mapping(row, field)
        for row in _list(document.get(collection), field)
        if isinstance(row, Mapping) and row.get(key) == record_id
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_DRIFT", field)
    return matches[0]


def _selected_fields(
    value: Mapping[str, Any], keys: Sequence[str], field: str
) -> dict[str, object]:
    if any(key not in value for key in keys):
        _fail("SEMANTIC_INPUT_DRIFT", field)
    return {key: value[key] for key in keys}


def _validate_authority(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "backlog",
    )
    story = _find_record(backlog, "stories", "id", "ST-1607", "backlog.stories")
    _exact(
        story,
        {
            "id": "ST-1607",
            "epic_id": "EPIC-16",
            "title": "Gate evidence generator",
            "objective": "Suite/decision/artifactを不変Pack化",
            "depends_on": ["ST-0005", "ST-1603", "ST-1605", "ST-1606"],
            "requirement_ids": [],
            "design_refs": [],
            "deliverables": ["gate report"],
            "acceptance_criteria": ["missing evidence blocks"],
            "test_suites": ["TST-032"],
            "priority": "P0",
            "mvp": True,
            "size": "M",
            "open_decisions": [],
            "one_pr_preferred": True,
            "design_status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
        },
        "backlog.ST-1607",
    )
    catalog = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    suite = _find_record(catalog, "suites", "id", "TST-032", "catalog.suites")
    _exact(
        suite,
        {
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
        },
        "catalog.TST-032",
    )


def _validate_status_input(contract: Mapping[str, Any], root: Path) -> None:
    _exact(contract["status_input"], EXPECTED_STATUS_INPUT, "status_input")
    overlay = _load_yaml(
        root, Path("changes/st-0005/status-overlay.v1.yaml"), "status_overlay"
    )
    if _list(overlay.get("applied_transitions"), "status.applied_transitions"):
        _fail("STATUS_APPLY_DRIFT", "status.applied_transitions")
    for expected in _list(
        EXPECTED_STATUS_INPUT["effective_story_statuses"], "expected.statuses"
    ):
        expected_row = _mapping(expected, "expected.status")
        story_id = expected_row["story_id"]
        if type(story_id) is not str:
            _fail("INVALID_TYPE", "expected.story_id")
        observed = _find_record(
            overlay, "stories", "story_id", story_id, "status.stories"
        )
        _exact(
            _selected_fields(
                observed,
                (
                    "story_id",
                    "effective_implementation_status",
                    "effective_verification_status",
                    "required_suites",
                ),
                "status.story",
            ),
            {
                "story_id": story_id,
                "effective_implementation_status": expected_row[
                    "implementation_status"
                ],
                "effective_verification_status": expected_row["verification_status"],
                "required_suites": expected_row["required_suites"],
            },
            f"status.{story_id}",
        )
    suite = _find_record(
        overlay, "test_suites", "suite_id", "TST-032", "status.test_suites"
    )
    _exact(
        _selected_fields(
            suite,
            (
                "suite_id",
                "effective_implementation_status",
                "effective_execution_status",
                "canonical_environments",
            ),
            "status.TST-032",
        ),
        {
            "suite_id": "TST-032",
            "effective_implementation_status": "NOT_STARTED",
            "effective_execution_status": "NOT_EXECUTED",
            "canonical_environments": ["STAGING"],
        },
        "status.TST-032",
    )


def _validate_decision_input(contract: Mapping[str, Any], root: Path) -> None:
    _exact(
        contract["decision_gate_binding"],
        _expected_decision_gate_binding(),
        "decision_gate_binding",
    )
    _exact(contract["decision_input"], EXPECTED_DECISION_INPUT, "decision_input")
    policy = _load_yaml(
        root,
        Path("changes/st-0006/contracts/decision-gate-policy.v1.yaml"),
        "decision_policy",
    )
    _exact(
        _selected_fields(
            _mapping(policy.get("mapping"), "decision_policy.mapping"),
            (
                "targets",
                "target_policy",
                "required_by_interpretation",
                "clear_means_gate_pass",
            ),
            "decision_policy.mapping",
        ),
        {
            "targets": list(DECISION_TARGETS),
            "target_policy": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
            "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
            "clear_means_gate_pass": False,
        },
        "decision_policy.mapping",
    )
    boundaries = _mapping(policy.get("boundaries"), "decision_policy.boundaries")
    if (
        boundaries.get("full_gate_pack_story") != "ST-1607"
        or boundaries.get("formal_tst_032") != "NOT_EXECUTED"
        or boundaries.get("live_status_apply") != "NOT_ACTIVATED"
        or boundaries.get("deployment") != "NOT_ACTIVATED"
    ):
        _fail("DECISION_POLICY_DRIFT", "decision_policy.boundaries")

    report = _load_yaml(
        root, Path("changes/st-0006/gate-blocker-report.v1.yaml"), "decision_report"
    )
    counts = _mapping(report.get("counts"), "decision_report.counts")
    if (
        report.get("overall_open_decision_check") != "BLOCKED"
        or counts.get("unresolved_blocking") != 14
    ):
        _fail("DECISION_REPORT_DRIFT", "decision_report")
    active = [
        row
        for row in _list(report.get("decisions"), "decision_report.decisions")
        if isinstance(row, Mapping) and row.get("active_blocker") is True
    ]
    if [row.get("id") for row in active] != list(ACTIVE_BLOCKER_IDS):
        _fail("DECISION_REPORT_DRIFT", "decision_report.active_blockers")
    for row in active:
        if row.get("blocked_targets") != list(DECISION_TARGETS):
            _fail("DECISION_REPORT_DRIFT", "decision_report.blocked_targets")


def _assert_semantic_fields(
    observed: Mapping[str, Any], expected: Mapping[str, object], field: str
) -> None:
    for key, value in expected.items():
        if (
            key not in observed
            or type(observed[key]) is not type(value)
            or observed[key] != value
        ):
            _fail("DEPENDENCY_SEMANTIC_DRIFT", field)


def _validate_dependency_semantics(root: Path) -> None:
    security = _load_json(
        root,
        Path(
            "changes/st-1603/generated/"
            "security-verification-pack.reference-plan.v1.json"
        ),
        "st1603.report",
    )
    _assert_semantic_fields(
        _mapping(security.get("evidence_boundary"), "st1603.evidence"),
        {
            "classification": (
                "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN"
            ),
            "verified_controls": "0/83",
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_031": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "st_1607_eligible": False,
            "release_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
        "st1603.evidence",
    )
    security_manifest = _load_yaml(
        root, Path("changes/st-1603/manifest.yaml"), "st1603.manifest"
    )
    _assert_semantic_fields(
        _mapping(security_manifest.get("boundary"), "st1603.manifest.boundary"),
        {
            "verified_controls": 0,
            "open_critical": None,
            "open_high": None,
            "decision": "NOT_READY",
            "st_1607_eligible": False,
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_031": "NOT_EXECUTED",
        },
        "st1603.manifest.boundary",
    )

    failure = _load_json(
        root,
        Path(
            "changes/st-1605/generated/"
            "failure-injection-drill.local-synthetic-evidence.v1.json"
        ),
        "st1605.report",
    )
    _assert_semantic_fields(
        _mapping(failure.get("evidence_boundary"), "st1605.evidence"),
        {
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
            "formal_tst_028": "NOT_EXECUTED",
            "owner_response": "NOT_EXECUTED",
            "runbook_validation": "NOT_EXECUTED",
            "staging_drill": "NOT_EXECUTED",
            "release": "NOT_AUTHORIZED",
            "production": "NOT_AUTHORIZED",
            "story_acceptance": False,
            "st_1607_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
        "st1605.evidence",
    )
    failure_manifest = _load_yaml(
        root, Path("changes/st-1605/manifest.yaml"), "st1605.manifest"
    )
    _assert_semantic_fields(
        _mapping(failure_manifest.get("boundary"), "st1605.manifest.boundary"),
        {
            "classification": "LOCAL_SYNTHETIC_NON_ATTESTING",
            "formal_tst_028": "NOT_EXECUTED",
            "owner_response": "NOT_EXECUTED",
            "runbook_validation": "NOT_EXECUTED",
            "staging_drill": "NOT_EXECUTED",
            "story_acceptance": False,
            "st_1607_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
        "st1605.manifest.boundary",
    )

    restore = _load_json(
        root,
        Path("changes/st-1606/generated/backup-restore-drill.reference-plan.v1.json"),
        "st1606.report",
    )
    _assert_semantic_fields(
        _mapping(restore.get("evidence_boundary"), "st1606.evidence"),
        {
            "classification": "PLAN_INVENTORY_PROJECTION_ONLY_NOT_RECOVERY_EVIDENCE",
            "restore_drill": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_AUTHORIZED",
            "production": "NOT_AUTHORIZED",
            "validated_claim": False,
            "acceptance_criteria_satisfied": False,
            "st_1607_eligible": False,
            "release_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
        "st1606.evidence",
    )
    restore_manifest = _load_yaml(
        root, Path("changes/st-1606/manifest.yaml"), "st1606.manifest"
    )
    _assert_semantic_fields(
        _mapping(restore_manifest.get("boundary"), "st1606.manifest.boundary"),
        {
            "restore_drill": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
            "recoverability_claim": False,
            "st_1607_eligible": False,
            "release_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
        "st1606.manifest.boundary",
    )


def _validate_snapshot_identity_boundary(snapshot: object) -> None:
    observed = _mapping(snapshot, "snapshot_boundary")
    _strict_lower_hex(observed.get("local_base_commit"), 40, "snapshot.local_base")
    if (
        observed.get("local_base_commit_type") != LOCAL_BASE_COMMIT_TYPE
        or observed.get("local_base_commit_status") != LOCAL_BASE_COMMIT_STATUS
        or observed.get("local_base_commit_scope")
        != "PREDECESSOR_CHECKOUT_PROVENANCE_ONLY"
        or observed.get("local_base_commit_qualifying_evidence") is not False
    ):
        _fail("IDENTITY_PROMOTION_FORBIDDEN", "snapshot.local_base")
    if (
        observed.get("source_freeze_identifier_type") != SOURCE_FREEZE_ID_TYPE
        or observed.get("source_freeze_status") != "ABSENT"
        or observed.get("source_freeze_identifier") is not None
        or observed.get("source_freeze_qualifying_evidence") is not False
    ):
        _fail("IDENTITY_PROMOTION_FORBIDDEN", "snapshot.source_freeze")
    if (
        observed.get("reviewed_implementation_tree_commit_type")
        != REVIEWED_TREE_COMMIT_TYPE
        or observed.get("reviewed_implementation_tree_commit_status") != "ABSENT"
        or observed.get("reviewed_implementation_tree_commit") is not None
        or observed.get("reviewed_implementation_tree_commit_qualifying_evidence")
        is not False
    ):
        _fail("IDENTITY_PROMOTION_FORBIDDEN", "snapshot.reviewed_tree")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _verify_hash_rows(root, contract["sources"], EXPECTED_SOURCE_HASHES, "sources")
    _exact(
        contract["dependency_bindings"],
        _expected_dependency_bindings(),
        "dependency_bindings",
    )
    _verify_files(
        root,
        EXPECTED_DEPENDENCY_HASHES,
        "DEPENDENCY_HASH_DRIFT",
        "dependencies",
    )
    _verify_files(
        root,
        EXPECTED_DECISION_GATE_HASHES,
        "DECISION_INPUT_HASH_DRIFT",
        "decision_inputs",
    )
    _verify_files(
        root,
        EXPECTED_IMPLEMENTATION_HASHES,
        "IMPLEMENTATION_DEPENDENCY_DRIFT",
        "implementation",
    )
    _validate_authority(root)
    _validate_status_input(contract, root)
    _validate_decision_input(contract, root)
    _validate_dependency_semantics(root)
    _validate_snapshot_identity_boundary(contract["snapshot_boundary"])
    _exact(contract["snapshot_boundary"], EXPECTED_SNAPSHOT, "snapshot_boundary")
    _exact(
        contract["required_evidence"],
        EXPECTED_REQUIRED_EVIDENCE,
        "required_evidence",
    )
    _exact(contract["global_blockers"], list(GLOBAL_BLOCKERS), "global_blockers")
    _exact(contract["gate_report"], _expected_gate_report(), "gate_report")
    _exact(contract["authority_boundary"], EXPECTED_AUTHORITY, "authority_boundary")
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution_boundary")
    _exact(contract["evidence_boundary"], EXPECTED_EVIDENCE, "evidence_boundary")
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def gate_evidence_pack(contract: Mapping[str, Any]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": GENERATOR_URI,
            "command": GENERATION_COMMAND,
            "source_contract": SOURCE_URI,
        },
        "story": {
            "id": "ST-1607",
            "scope": "LOCAL_BLOCKED_REPORT_ONLY",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "document": contract["document"],
        "classification": EXPECTED_DOCUMENT["classification"],
        "source_bindings": contract["sources"],
        "dependency_bindings": contract["dependency_bindings"],
        "decision_gate_binding": contract["decision_gate_binding"],
        "status_input": contract["status_input"],
        "decision_input": contract["decision_input"],
        "snapshot_boundary": contract["snapshot_boundary"],
        "required_evidence": contract["required_evidence"],
        "global_blockers": contract["global_blockers"],
        "gate_report": contract["gate_report"],
        "authority_boundary": contract["authority_boundary"],
        "execution_boundary": contract["execution_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "prohibited_interpretations": [
            "LOCAL_GENERATION_IS_NOT_FORMAL_TST_032",
            "NON_ATTESTING_DEPENDENCY_ARTIFACT_IS_NOT_QUALIFYING_GATE_EVIDENCE",
            "NO_SUITE_TO_GATE_MAPPING_MAY_BE_INFERRED",
            "BLOCKED_REPORT_IS_NOT_GATE_OWNER_APPROVAL",
            "LOCAL_BASE_COMMIT_IS_NOT_REVIEWED_IMPLEMENTATION_TREE_EVIDENCE",
            "RECORDED_BASE_COMMIT_IS_NOT_A_SOURCE_FREEZE_OR_QUALIFYING_GATE_EVIDENCE",
            "ABSENT_SOURCE_FREEZE_OR_REVIEWED_TREE_IDENTITY_CANNOT_BE_PROMOTED",
            "NO_STATUS_APPLY_STAGING_RELEASE_OR_PRODUCTION_AUTHORITY_MAY_BE_INFERRED",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.input")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _manifest_bytes(root: Path, report_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-GATE-EVIDENCE-PACK-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1607",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "local_base_commit": LOCAL_BASE_COMMIT,
            "local_base_commit_type": LOCAL_BASE_COMMIT_TYPE,
            "local_base_commit_status": LOCAL_BASE_COMMIT_STATUS,
            "local_base_commit_scope": "PREDECESSOR_CHECKOUT_PROVENANCE_ONLY",
            "local_base_commit_qualifying_evidence": False,
            "source_freeze_identifier_type": SOURCE_FREEZE_ID_TYPE,
            "source_freeze_status": "ABSENT",
            "source_freeze_identifier": None,
            "source_freeze_qualifying_evidence": False,
            "reviewed_implementation_tree_commit_type": REVIEWED_TREE_COMMIT_TYPE,
            "reviewed_implementation_tree_commit_status": "ABSENT",
            "reviewed_implementation_tree_commit": None,
            "reviewed_implementation_tree_commit_qualifying_evidence": False,
            "contract_sha256": _sha256_bytes(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_SOURCE_HASHES.items()
            ],
            "dependency_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_DEPENDENCY_HASHES.items()
            ],
            "decision_gate_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_DECISION_GATE_HASHES.items()
            ],
            "implementation_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_IMPLEMENTATION_HASHES.items()
            ],
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REPORT_PATH.as_posix()}",
                "bytes": len(report_bytes),
                "sha256": _sha256_bytes(report_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": EXPECTED_EVIDENCE["classification"],
            "input_size_limit_bytes": MAX_INPUT_BYTES,
            "gate_status": "BLOCKED",
            "formal_tst_032": "NOT_EXECUTED",
            "active_blocking_open_decisions": 14,
            "owner_gate_approvals": "NONE",
            "release_authority": "NONE",
            "production_authority": "NONE",
            "acceptance_criteria_satisfied": False,
            "release_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    report_bytes = _json_bytes(gate_evidence_pack(contract))
    return {
        REPORT_PATH: report_bytes,
        MANIFEST_PATH: _manifest_bytes(root, report_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        actual = _read(root, relative, "generated_output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


@dataclass(frozen=True, slots=True)
class _FileSnapshot:
    content: bytes
    device: int
    inode: int
    mode: int
    mtime_ns: int
    owner: int
    links: int


@dataclass(slots=True)
class _OutputSlot:
    relative: Path
    parent_descriptor: int
    parent_identity: tuple[int, int]
    target_name: str
    next_name: str
    previous_name: str
    absent_name: str
    original: _FileSnapshot | None = None
    staged: _FileSnapshot | None = None


@dataclass(slots=True)
class _WriterLock:
    slot: _OutputSlot


def _companion_name(target_name: str, suffix: str) -> str:
    return f".{target_name}{suffix}"


def _validate_output_relative(relative: Path) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_OUTPUT_PATH", "output")


def _validate_directory(metadata: os.stat_result) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("UNSAFE_OUTPUT_ANCESTOR", "output")


def _open_output_parent(
    root: Path, relative: Path, *, create: bool
) -> tuple[int, tuple[int, int]] | None:
    _validate_output_relative(relative)
    current_descriptor = -1
    try:
        current_descriptor = _open_repository_root(root, "output")
        _validate_directory(os.fstat(current_descriptor))
        for part in relative.parts[:-1]:
            try:
                metadata = os.stat(
                    part,
                    dir_fd=current_descriptor,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                if not create:
                    os.close(current_descriptor)
                    current_descriptor = -1
                    return None
                os.mkdir(part, mode=0o755, dir_fd=current_descriptor)
                os.fsync(current_descriptor)
                metadata = os.stat(
                    part,
                    dir_fd=current_descriptor,
                    follow_symlinks=False,
                )
            _validate_directory(metadata)
            child_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=current_descriptor,
            )
            child_metadata = os.fstat(child_descriptor)
            if (child_metadata.st_dev, child_metadata.st_ino) != (
                metadata.st_dev,
                metadata.st_ino,
            ):
                os.close(child_descriptor)
                _fail("OUTPUT_ANCESTOR_CHANGED", "output")
            os.close(current_descriptor)
            current_descriptor = child_descriptor
        metadata = os.fstat(current_descriptor)
        _validate_directory(metadata)
        result_descriptor = current_descriptor
        current_descriptor = -1
        return result_descriptor, (metadata.st_dev, metadata.st_ino)
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", "output")
    finally:
        if current_descriptor >= 0:
            os.close(current_descriptor)


def _open_slots(root: Path, *, create: bool) -> list[_OutputSlot]:
    slots: list[_OutputSlot] = []
    try:
        for relative in GENERATED_PATHS:
            opened = _open_output_parent(root, relative, create=create)
            if opened is None:
                continue
            parent_descriptor, parent_identity = opened
            slots.append(
                _OutputSlot(
                    relative=relative,
                    parent_descriptor=parent_descriptor,
                    parent_identity=parent_identity,
                    target_name=relative.name,
                    next_name=_companion_name(relative.name, NEXT_SUFFIX),
                    previous_name=_companion_name(relative.name, PREVIOUS_SUFFIX),
                    absent_name=_companion_name(relative.name, ABSENT_SUFFIX),
                )
            )
        return slots
    except BaseException:
        _close_slots(slots)
        raise


def _close_slots(slots: Sequence[_OutputSlot]) -> None:
    for slot in slots:
        if slot.parent_descriptor >= 0:
            os.close(slot.parent_descriptor)
            slot.parent_descriptor = -1


def _slot_by_relative(slots: Sequence[_OutputSlot], relative: Path) -> _OutputSlot:
    matches = [slot for slot in slots if slot.relative == relative]
    if len(matches) != 1:
        _fail("OUTPUT_PARENT_UNAVAILABLE", "output")
    return matches[0]


def _safe_regular_mode(mode: int) -> bool:
    prohibited = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | 0o022
    return not bool(mode & prohibited)


def _snapshot_at(
    slot: _OutputSlot,
    name: str,
    *,
    field: str,
    missing_ok: bool,
    expected_mode: int | None = None,
    allowed_links: frozenset[int] = frozenset({1}),
) -> _FileSnapshot | None:
    try:
        path_metadata = os.stat(
            name,
            dir_fd=slot.parent_descriptor,
            follow_symlinks=False,
        )
    except FileNotFoundError:
        if missing_ok:
            return None
        _fail("OUTPUT_RECOVERY_REQUIRED", field)
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", field)
    mode = stat.S_IMODE(path_metadata.st_mode)
    if not stat.S_ISREG(path_metadata.st_mode):
        _fail("UNSAFE_OUTPUT_TARGET", field)
    if path_metadata.st_uid != os.geteuid():
        _fail("UNSAFE_OUTPUT_OWNER", field)
    if expected_mode is not None:
        if mode != expected_mode:
            _fail("UNSAFE_OUTPUT_MODE", field)
    elif not _safe_regular_mode(mode):
        _fail("UNSAFE_OUTPUT_MODE", field)
    if path_metadata.st_nlink not in allowed_links:
        _fail("UNSAFE_OUTPUT_LINK_COUNT", field)
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=slot.parent_descriptor,
        )
        metadata = os.fstat(descriptor)
        if (metadata.st_dev, metadata.st_ino) != (
            path_metadata.st_dev,
            path_metadata.st_ino,
        ):
            _fail("OUTPUT_TARGET_CHANGED", field)
        if metadata.st_size > MAX_INPUT_BYTES:
            _fail("OUTPUT_SIZE_LIMIT", field)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            content = stream.read(MAX_INPUT_BYTES + 1)
        if len(content) > MAX_INPUT_BYTES:
            _fail("OUTPUT_SIZE_LIMIT", field)
        final_metadata = os.stat(
            name,
            dir_fd=slot.parent_descriptor,
            follow_symlinks=False,
        )
        if (
            final_metadata.st_dev,
            final_metadata.st_ino,
            final_metadata.st_mode,
            final_metadata.st_size,
            final_metadata.st_mtime_ns,
            final_metadata.st_nlink,
        ) != (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_nlink,
        ):
            _fail("OUTPUT_TARGET_CHANGED", field)
        return _FileSnapshot(
            content=content,
            device=metadata.st_dev,
            inode=metadata.st_ino,
            mode=stat.S_IMODE(metadata.st_mode),
            mtime_ns=metadata.st_mtime_ns,
            owner=metadata.st_uid,
            links=metadata.st_nlink,
        )
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", field)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _same_file(left: _FileSnapshot, right: _FileSnapshot) -> bool:
    return (left.device, left.inode) == (right.device, right.inode)


def _same_original(left: _FileSnapshot, right: _FileSnapshot) -> bool:
    return (
        left.content,
        left.device,
        left.inode,
        left.mode,
        left.mtime_ns,
        left.owner,
    ) == (
        right.content,
        right.device,
        right.inode,
        right.mode,
        right.mtime_ns,
        right.owner,
    )


def _assert_parent_identity(root: Path, slot: _OutputSlot) -> None:
    opened = _open_output_parent(root, slot.relative, create=False)
    if opened is None:
        _fail("OUTPUT_ANCESTOR_CHANGED", "output")
    descriptor, identity = opened
    try:
        if identity != slot.parent_identity:
            _fail("OUTPUT_ANCESTOR_CHANGED", "output")
    finally:
        os.close(descriptor)


def _fsync_slot(slot: _OutputSlot) -> None:
    try:
        os.fsync(slot.parent_descriptor)
    except OSError:
        _fail("OUTPUT_FSYNC_FAILED", "output")


def _write_companion(
    slot: _OutputSlot,
    name: str,
    content: bytes,
    *,
    mode: int,
    field: str,
) -> _FileSnapshot:
    descriptor = -1
    created = False
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=slot.parent_descriptor,
        )
        created = True
        os.fchmod(descriptor, mode)
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short companion write")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        _fsync_slot(slot)
        snapshot = _snapshot_at(
            slot,
            name,
            field=field,
            missing_ok=False,
            expected_mode=mode,
        )
        if snapshot is None or snapshot.content != content:
            _fail("OUTPUT_COMPANION_DRIFT", field)
        return snapshot
    except GateEvidencePackError:
        raise
    except OSError:
        if created:
            try:
                os.unlink(name, dir_fd=slot.parent_descriptor)
                os.fsync(slot.parent_descriptor)
            except OSError:
                _fail("OUTPUT_RECOVERY_REQUIRED", field)
        _fail("OUTPUT_STAGE_FAILED", field)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _assert_absent(slot: _OutputSlot, name: str, field: str) -> None:
    try:
        os.stat(name, dir_fd=slot.parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", field)
    _fail("OUTPUT_COMPANION_PRESENT", field)


def _unlink_snapshot(slot: _OutputSlot, name: str, expected: _FileSnapshot) -> None:
    observed = _snapshot_at(
        slot,
        name,
        field="output",
        missing_ok=False,
        expected_mode=expected.mode,
        allowed_links=frozenset({expected.links}),
    )
    if observed is None or not _same_original(observed, expected):
        _fail("OUTPUT_COMPANION_DRIFT", "output")
    try:
        os.unlink(name, dir_fd=slot.parent_descriptor)
        _fsync_slot(slot)
    except OSError:
        _fail("OUTPUT_RECOVERY_REQUIRED", "output")


def _state_slot(slots: Sequence[_OutputSlot]) -> _OutputSlot:
    return _slot_by_relative(slots, MANIFEST_PATH)


def _state_snapshot(
    slots: Sequence[_OutputSlot], name: str, *, missing_ok: bool
) -> _FileSnapshot | None:
    return _snapshot_at(
        _state_slot(slots),
        name,
        field="transaction_state",
        missing_ok=missing_ok,
        expected_mode=PRIVATE_COMPANION_MODE,
    )


def _marker_snapshot(
    slot: _OutputSlot, name: str, *, missing_ok: bool
) -> _FileSnapshot | None:
    snapshot = _snapshot_at(
        slot,
        name,
        field="output_companion",
        missing_ok=missing_ok,
        expected_mode=PRIVATE_COMPANION_MODE,
    )
    if snapshot is not None and snapshot.content != ABSENT_MARKER:
        _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
    return snapshot


def _next_snapshot(slot: _OutputSlot, *, missing_ok: bool) -> _FileSnapshot | None:
    return _snapshot_at(
        slot,
        slot.next_name,
        field="output_companion",
        missing_ok=missing_ok,
        expected_mode=OUTPUT_MODE,
        allowed_links=frozenset({1, 2}),
    )


def _previous_snapshot(slot: _OutputSlot, *, missing_ok: bool) -> _FileSnapshot | None:
    return _snapshot_at(
        slot,
        slot.previous_name,
        field="output_companion",
        missing_ok=missing_ok,
    )


def _target_snapshot(
    slot: _OutputSlot, *, missing_ok: bool, linked_ok: bool = False
) -> _FileSnapshot | None:
    return _snapshot_at(
        slot,
        slot.target_name,
        field="generated_output",
        missing_ok=missing_ok,
        allowed_links=frozenset({1, 2}) if linked_ok else frozenset({1}),
    )


def _lock_slot(root: Path, *, create: bool) -> _OutputSlot:
    opened = _open_output_parent(root, MANIFEST_PATH, create=create)
    if opened is None:
        _fail("OUTPUT_PARENT_UNAVAILABLE", "writer_lock")
    parent_descriptor, parent_identity = opened
    return _OutputSlot(
        relative=MANIFEST_PATH,
        parent_descriptor=parent_descriptor,
        parent_identity=parent_identity,
        target_name=MANIFEST_PATH.name,
        next_name="",
        previous_name="",
        absent_name="",
    )


def _acquire_process_lock(root: Path, *, shared: bool) -> _WriterLock:
    slot = _lock_slot(root, create=not shared)
    try:
        try:
            fcntl.flock(
                slot.parent_descriptor,
                (fcntl.LOCK_SH if shared else fcntl.LOCK_EX) | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            _fail("CONCURRENT_OUTPUT_WRITER", "writer_lock")
        return _WriterLock(slot=slot)
    except GateEvidencePackError:
        os.close(slot.parent_descriptor)
        slot.parent_descriptor = -1
        raise
    except OSError:
        os.close(slot.parent_descriptor)
        slot.parent_descriptor = -1
        _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")


def _acquire_writer_lock(root: Path) -> _WriterLock:
    return _acquire_process_lock(root, shared=False)


def _acquire_check_lock(root: Path) -> _WriterLock:
    return _acquire_process_lock(root, shared=True)


def _release_writer_lock(lock: _WriterLock) -> None:
    release_error = False
    try:
        metadata = os.fstat(lock.slot.parent_descriptor)
        if (metadata.st_dev, metadata.st_ino) != lock.slot.parent_identity:
            _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")
    except GateEvidencePackError, OSError:
        release_error = True
    finally:
        try:
            fcntl.flock(lock.slot.parent_descriptor, fcntl.LOCK_UN)
        except OSError:
            release_error = True
        try:
            os.close(lock.slot.parent_descriptor)
        except OSError:
            release_error = True
        lock.slot.parent_descriptor = -1
    if release_error:
        _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")


def _transaction_checkpoint(_name: str) -> None:
    """Test-only crash boundary; production execution is intentionally inert."""


def _before_transaction_commit(_slots: Sequence[_OutputSlot]) -> None:
    """Test-only race boundary immediately before the final revalidation."""


def _preflight_slots(root: Path, slots: Sequence[_OutputSlot]) -> None:
    if tuple(slot.relative for slot in slots) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    state = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if state is None or state.content != ROLLBACK_STATE:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _assert_absent(_state_slot(slots), TRANSACTION_STATE_NEXT_NAME, "transaction_state")
    for slot in slots:
        _assert_parent_identity(root, slot)
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")
        observed_target = _target_snapshot(slot, missing_ok=True)
        if (observed_target is None) != (slot.original is None):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        if (
            observed_target is not None
            and slot.original is not None
            and not _same_original(observed_target, slot.original)
        ):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        slot.staged = _next_snapshot(slot, missing_ok=False)


def _revalidate_slots(root: Path, slots: Sequence[_OutputSlot]) -> None:
    for slot in slots:
        _assert_parent_identity(root, slot)
        observed_target = _target_snapshot(slot, missing_ok=True)
        if (observed_target is None) != (slot.original is None):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        if (
            observed_target is not None
            and slot.original is not None
            and not _same_original(observed_target, slot.original)
        ):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        observed_next = _next_snapshot(slot, missing_ok=False)
        if (
            observed_next is None
            or slot.staged is None
            or not _same_original(observed_next, slot.staged)
        ):
            _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")


def _stage_outputs(root: Path, outputs: Mapping[Path, bytes]) -> list[_OutputSlot]:
    if tuple(outputs) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    slots = _open_slots(root, create=True)
    state_created = False
    try:
        if tuple(slot.relative for slot in slots) != GENERATED_PATHS:
            _fail("OUTPUT_PARENT_UNAVAILABLE", "output")
        coordinator = _state_slot(slots)
        _assert_absent(coordinator, TRANSACTION_STATE_NAME, "transaction_state")
        _assert_absent(coordinator, TRANSACTION_STATE_NEXT_NAME, "transaction_state")
        for slot in slots:
            _assert_parent_identity(root, slot)
            _assert_absent(slot, slot.next_name, "output_companion")
            _assert_absent(slot, slot.previous_name, "output_companion")
            _assert_absent(slot, slot.absent_name, "output_companion")
            slot.original = _target_snapshot(slot, missing_ok=True)
        _write_rollback_state(slots)
        state_created = True
        for slot in slots:
            slot.staged = _write_companion(
                slot,
                slot.next_name,
                outputs[slot.relative],
                mode=OUTPUT_MODE,
                field="output_stage",
            )
            _transaction_checkpoint(f"STAGED_{slot.relative.as_posix()}")
        _preflight_slots(root, slots)
        return slots
    except (GateEvidencePackError, OSError) as stage_error:
        if state_created:
            originals = {slot.relative: slot.original for slot in slots}
            try:
                _recover_rollback(
                    root,
                    slots,
                    expected_originals=originals,
                )
            except (GateEvidencePackError, OSError) as recovery_error:
                _best_effort_restore_uncontested_slots(slots, originals)
                raise GateEvidencePackError(
                    "OUTPUT_ROLLBACK_REQUIRED", "output"
                ) from recovery_error
        _close_slots(slots)
        raise stage_error
    except BaseException:
        # A crash intentionally leaves fixed companions for next-run recovery.
        _close_slots(slots)
        raise


def _write_rollback_state(slots: Sequence[_OutputSlot]) -> None:
    coordinator = _state_slot(slots)
    _write_companion(
        coordinator,
        TRANSACTION_STATE_NAME,
        ROLLBACK_STATE,
        mode=PRIVATE_COMPANION_MODE,
        field="transaction_state",
    )


def _backup_output(root: Path, slot: _OutputSlot) -> None:
    _assert_parent_identity(root, slot)
    observed = _target_snapshot(slot, missing_ok=True)
    if (observed is None) != (slot.original is None):
        _fail("OUTPUT_TARGET_CHANGED", "generated_output")
    if (
        observed is not None
        and slot.original is not None
        and not _same_original(observed, slot.original)
    ):
        _fail("OUTPUT_TARGET_CHANGED", "generated_output")
    _assert_absent(slot, slot.previous_name, "output_companion")
    _assert_absent(slot, slot.absent_name, "output_companion")
    try:
        if slot.original is None:
            _write_companion(
                slot,
                slot.absent_name,
                ABSENT_MARKER,
                mode=PRIVATE_COMPANION_MODE,
                field="output_companion",
            )
        else:
            os.replace(
                slot.target_name,
                slot.previous_name,
                src_dir_fd=slot.parent_descriptor,
                dst_dir_fd=slot.parent_descriptor,
            )
            _fsync_slot(slot)
            previous = _previous_snapshot(slot, missing_ok=False)
            if previous is None or not _same_original(previous, slot.original):
                _fail("OUTPUT_TARGET_CHANGED", "generated_output")
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("OUTPUT_TRANSACTION_FAILED", "output")
    _transaction_checkpoint(f"BACKED_UP_{slot.relative.as_posix()}")


def _publish_output(root: Path, slot: _OutputSlot) -> None:
    _assert_parent_identity(root, slot)
    if _target_snapshot(slot, missing_ok=True, linked_ok=True) is not None:
        _fail("OUTPUT_TARGET_CHANGED", "generated_output")
    next_snapshot = _next_snapshot(slot, missing_ok=False)
    previous = _previous_snapshot(slot, missing_ok=True)
    absent = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
    if next_snapshot is None or (previous is None) == (absent is None):
        _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
    if next_snapshot.links != 1:
        _fail("UNSAFE_OUTPUT_LINK_COUNT", "output_companion")
    try:
        os.link(
            slot.next_name,
            slot.target_name,
            src_dir_fd=slot.parent_descriptor,
            dst_dir_fd=slot.parent_descriptor,
            follow_symlinks=False,
        )
        _fsync_slot(slot)
    except OSError:
        _fail("OUTPUT_TRANSACTION_FAILED", "output")
    target = _target_snapshot(slot, missing_ok=False, linked_ok=True)
    linked_next = _next_snapshot(slot, missing_ok=False)
    if (
        target is None
        or linked_next is None
        or not _same_file(target, linked_next)
        or target.mode != OUTPUT_MODE
        or target.links != 2
        or linked_next.links != 2
    ):
        _fail("OUTPUT_PUBLISH_DRIFT", "output")
    _transaction_checkpoint(f"PUBLISHED_{slot.relative.as_posix()}")


def _mark_commit(slots: Sequence[_OutputSlot]) -> None:
    coordinator = _state_slot(slots)
    rollback = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if rollback is None or rollback.content != ROLLBACK_STATE:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _write_companion(
        coordinator,
        TRANSACTION_STATE_NEXT_NAME,
        COMMIT_STATE,
        mode=PRIVATE_COMPANION_MODE,
        field="transaction_state",
    )
    try:
        os.replace(
            TRANSACTION_STATE_NEXT_NAME,
            TRANSACTION_STATE_NAME,
            src_dir_fd=coordinator.parent_descriptor,
            dst_dir_fd=coordinator.parent_descriptor,
        )
        _fsync_slot(coordinator)
    except OSError:
        _fail("OUTPUT_TRANSACTION_FAILED", "transaction_state")
    committed = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if committed is None or committed.content != COMMIT_STATE:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _transaction_checkpoint("COMMIT_MARKED")


def _inspect_recovery_companions(
    slots: Sequence[_OutputSlot],
) -> dict[
    Path, tuple[_FileSnapshot | None, _FileSnapshot | None, _FileSnapshot | None]
]:
    companions = {}
    for slot in slots:
        next_snapshot = _next_snapshot(slot, missing_ok=True)
        previous = _previous_snapshot(slot, missing_ok=True)
        absent = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
        if previous is not None and absent is not None:
            _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
        companions[slot.relative] = (next_snapshot, previous, absent)
    return companions


def _recover_rollback(
    root: Path,
    slots: Sequence[_OutputSlot],
    *,
    expected_originals: Mapping[Path, _FileSnapshot | None] | None = None,
) -> None:
    state = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if state is None or state.content != ROLLBACK_STATE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    state_next = _state_snapshot(slots, TRANSACTION_STATE_NEXT_NAME, missing_ok=True)
    if state_next is not None and state_next.content != COMMIT_STATE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    companions = _inspect_recovery_companions(slots)
    observations: dict[Path, _FileSnapshot | None] = {}
    for slot in slots:
        _assert_parent_identity(root, slot)
        next_snapshot, previous, absent = companions[slot.relative]
        target = _target_snapshot(slot, missing_ok=True, linked_ok=True)
        observations[slot.relative] = target
        if previous is not None or absent is not None:
            if next_snapshot is None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
            if target is not None and not _same_file(target, next_snapshot):
                _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        elif (
            target is not None
            and next_snapshot is not None
            and _same_file(target, next_snapshot)
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
    try:
        for slot in reversed(slots):
            next_snapshot, previous, absent = companions[slot.relative]
            target = observations[slot.relative]
            if previous is not None:
                if target is not None:
                    if next_snapshot is None or not _same_file(target, next_snapshot):
                        _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
                os.replace(
                    slot.previous_name,
                    slot.target_name,
                    src_dir_fd=slot.parent_descriptor,
                    dst_dir_fd=slot.parent_descriptor,
                )
                _fsync_slot(slot)
                restored = _target_snapshot(slot, missing_ok=False)
                if restored is None or not _same_original(restored, previous):
                    _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
                _transaction_checkpoint(f"RESTORED_{slot.relative.as_posix()}")
            elif absent is not None and target is not None:
                if next_snapshot is None or not _same_file(target, next_snapshot):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
                os.unlink(slot.target_name, dir_fd=slot.parent_descriptor)
                _fsync_slot(slot)
                _transaction_checkpoint(f"RESTORED_{slot.relative.as_posix()}")
        if expected_originals is not None:
            for slot in slots:
                expected = expected_originals[slot.relative]
                observed = _target_snapshot(slot, missing_ok=True)
                if (observed is None) != (expected is None):
                    _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
                if (
                    observed is not None
                    and expected is not None
                    and not _same_original(observed, expected)
                ):
                    _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
        for slot in slots:
            marker = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
            if marker is not None:
                _unlink_snapshot(slot, slot.absent_name, marker)
        if state_next is not None:
            _unlink_snapshot(
                _state_slot(slots), TRANSACTION_STATE_NEXT_NAME, state_next
            )
        for slot in slots:
            staged = _next_snapshot(slot, missing_ok=True)
            if staged is not None:
                _unlink_snapshot(slot, slot.next_name, staged)
        current_state = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
        if current_state is None or current_state.content != ROLLBACK_STATE:
            _fail("OUTPUT_ROLLBACK_REQUIRED", "transaction_state")
        _unlink_snapshot(_state_slot(slots), TRANSACTION_STATE_NAME, current_state)
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("OUTPUT_ROLLBACK_REQUIRED", "output")


def _recover_commit(root: Path, slots: Sequence[_OutputSlot]) -> None:
    state = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if state is None or state.content != COMMIT_STATE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    if _state_snapshot(slots, TRANSACTION_STATE_NEXT_NAME, missing_ok=True) is not None:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    companions = _inspect_recovery_companions(slots)
    for slot in slots:
        _assert_parent_identity(root, slot)
        next_snapshot, _previous, _absent = companions[slot.relative]
        target = _target_snapshot(slot, missing_ok=False, linked_ok=True)
        if (
            next_snapshot is None
            or target is None
            or not _same_file(target, next_snapshot)
            or target.mode != OUTPUT_MODE
            or target.links != 2
            or next_snapshot.links != 2
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
    try:
        for slot in slots:
            _next, previous, absent = companions[slot.relative]
            if previous is not None:
                _unlink_snapshot(slot, slot.previous_name, previous)
            if absent is not None:
                _unlink_snapshot(slot, slot.absent_name, absent)
        current_state = _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=False)
        if current_state is None or current_state.content != COMMIT_STATE:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        _unlink_snapshot(_state_slot(slots), TRANSACTION_STATE_NAME, current_state)
        for slot in slots:
            staged = _next_snapshot(slot, missing_ok=False)
            if staged is None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
            _unlink_snapshot(slot, slot.next_name, staged)
            target = _target_snapshot(slot, missing_ok=False)
            if target is None or target.mode != OUTPUT_MODE or target.links != 1:
                _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
    except GateEvidencePackError:
        raise
    except OSError:
        _fail("OUTPUT_RECOVERY_REQUIRED", "output")


def _best_effort_restore_uncontested_slots(
    slots: Sequence[_OutputSlot],
    expected_originals: Mapping[Path, _FileSnapshot | None],
) -> None:
    """Restore only slots whose current target still matches transaction state."""

    for slot in reversed(slots):
        try:
            previous = _previous_snapshot(slot, missing_ok=True)
            absent = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
            next_snapshot = _next_snapshot(slot, missing_ok=True)
            target = _target_snapshot(slot, missing_ok=True, linked_ok=True)
            if previous is not None:
                if target is not None and (
                    next_snapshot is None or not _same_file(target, next_snapshot)
                ):
                    continue
                os.replace(
                    slot.previous_name,
                    slot.target_name,
                    src_dir_fd=slot.parent_descriptor,
                    dst_dir_fd=slot.parent_descriptor,
                )
                _fsync_slot(slot)
            elif absent is not None and target is not None:
                if next_snapshot is None or not _same_file(target, next_snapshot):
                    continue
                os.unlink(slot.target_name, dir_fd=slot.parent_descriptor)
                _fsync_slot(slot)
            expected = expected_originals[slot.relative]
            observed = _target_snapshot(slot, missing_ok=True)
            if (observed is None) != (expected is None):
                continue
            if (
                observed is not None
                and expected is not None
                and not _same_original(observed, expected)
            ):
                continue
        except GateEvidencePackError, OSError:
            # The coordinator remains and the caller reports rollback-required.
            continue


def _recover_uncoordinated_stage(root: Path, slots: Sequence[_OutputSlot]) -> None:
    companions = _inspect_recovery_companions(slots)
    if any(
        previous is not None or absent is not None
        for _, previous, absent in companions.values()
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    for slot in slots:
        _assert_parent_identity(root, slot)
        next_snapshot, _previous, _absent = companions[slot.relative]
        if next_snapshot is None:
            continue
        target = _target_snapshot(slot, missing_ok=True, linked_ok=True)
        if (
            target is None
            or target.links != 2
            or next_snapshot.links != 2
            or not _same_file(target, next_snapshot)
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        _unlink_snapshot(slot, slot.next_name, next_snapshot)


def _recover_pending_transaction(root: Path, *, mutate: bool) -> None:
    slots = _open_slots(root, create=False)
    try:
        if not slots:
            return
        state_slot_matches = [slot for slot in slots if slot.relative == MANIFEST_PATH]
        state = (
            _state_snapshot(slots, TRANSACTION_STATE_NAME, missing_ok=True)
            if len(state_slot_matches) == 1
            else None
        )
        state_next = (
            _state_snapshot(slots, TRANSACTION_STATE_NEXT_NAME, missing_ok=True)
            if len(state_slot_matches) == 1
            else None
        )
        has_output_companion = False
        for slot in slots:
            for name in (slot.next_name, slot.previous_name, slot.absent_name):
                try:
                    os.stat(
                        name,
                        dir_fd=slot.parent_descriptor,
                        follow_symlinks=False,
                    )
                except FileNotFoundError:
                    continue
                except OSError:
                    _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
                has_output_companion = True
        if state is None and state_next is None and not has_output_companion:
            return
        if not mutate:
            _fail("OUTPUT_RECOVERY_REQUIRED", "output")
        if state is None:
            if state_next is not None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            _recover_uncoordinated_stage(root, slots)
            return
        if state.content == ROLLBACK_STATE:
            _recover_rollback(root, slots)
            return
        if state.content == COMMIT_STATE:
            _recover_commit(root, slots)
            return
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    finally:
        _close_slots(slots)


def _write_output_transaction(root: Path, outputs: Mapping[Path, bytes]) -> None:
    slots: list[_OutputSlot] = []
    state_started = False
    commit_marked = False
    try:
        slots = _stage_outputs(root, outputs)
        state_started = True
        _before_transaction_commit(slots)
        _revalidate_slots(root, slots)
        for slot in slots:
            _backup_output(root, slot)
        for slot in slots:
            _publish_output(root, slot)
        _mark_commit(slots)
        commit_marked = True
        _recover_commit(root, slots)
    except (GateEvidencePackError, OSError) as error:
        if state_started and not commit_marked:
            try:
                observed_state = _state_snapshot(
                    slots, TRANSACTION_STATE_NAME, missing_ok=True
                )
                commit_marked = (
                    observed_state is not None
                    and observed_state.content == COMMIT_STATE
                )
            except GateEvidencePackError, OSError:
                commit_marked = False
        if commit_marked:
            if isinstance(error, GateEvidencePackError) and error.code == (
                "OUTPUT_RECOVERY_REQUIRED"
            ):
                raise
            _fail("OUTPUT_RECOVERY_REQUIRED", "output")
        if state_started:
            originals = {slot.relative: slot.original for slot in slots}
            try:
                _recover_rollback(
                    root,
                    slots,
                    expected_originals=originals,
                )
            except (GateEvidencePackError, OSError) as rollback_error:
                _best_effort_restore_uncontested_slots(slots, originals)
                raise GateEvidencePackError(
                    "OUTPUT_ROLLBACK_REQUIRED", "output"
                ) from rollback_error
        else:
            # No owned companion is created before the rollback coordinator.
            pass
        if isinstance(error, GateEvidencePackError):
            raise error
        _fail("OUTPUT_TRANSACTION_FAILED", "output")
    finally:
        _close_slots(slots)


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    if check:
        check_lock = _acquire_check_lock(root)
        try:
            _recover_pending_transaction(root, mutate=False)
            outputs = render_outputs(root)
            check_outputs(root, outputs)
        finally:
            _release_writer_lock(check_lock)
        return
    writer_lock = _acquire_writer_lock(root)
    try:
        _recover_pending_transaction(root, mutate=True)
        outputs = render_outputs(root)
        _write_output_transaction(root, outputs)
    finally:
        _release_writer_lock(writer_lock)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def _require_hardened_cli() -> None:
    if sys.flags.isolated != 1:
        _fail("ISOLATED_MODE_REQUIRED", "cli.python")
    if sys.flags.dont_write_bytecode != 1:
        _fail("NO_BYTECODE_MODE_REQUIRED", "cli.python")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        _require_hardened_cli()
        build(check=args.check)
    except GateEvidencePackError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1607 blocked gate evidence pack checked"
        if args.check
        else "ST-1607 blocked gate evidence pack generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
