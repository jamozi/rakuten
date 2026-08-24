#!/usr/bin/env python3
"""Build the non-executable ST-1702 category fixtures/rules reference plan."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.resolver import BaseResolver
from yaml.tokens import AliasToken, AnchorToken


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1702/contracts/category-fixtures-rules-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1702/generated/category-fixtures-rules-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1702/manifest.yaml")
README_PATH: Final = Path("changes/st-1702/README.md")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1702_category_fixtures_rules_reference_plan.py"
)
TEST_PATHS: Final = (
    Path("tests/st1702/conftest.py"),
    Path("tests/st1702/test_contract.py"),
    Path("tests/st1702/test_generation.py"),
    Path("tests/st1702/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python "
    "scripts/build_st1702_category_fixtures_rules_reference_plan.py"
)
INTEGRATION_BASE_COMMIT: Final = "53d23dd8f6782c9a68ed27234f9c0719916d5707"
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
NEXT_SUFFIX: Final = ".st1702.next"
PREVIOUS_SUFFIX: Final = ".st1702.previous"
ABSENT_SUFFIX: Final = ".st1702.absent"
TRANSACTION_STATE_NAME: Final = f".{MANIFEST_PATH.name}.st1702.transaction"
TRANSACTION_STATE_NEXT_NAME: Final = f"{TRANSACTION_STATE_NAME}.next"
TRANSACTION_SCHEMA: Final = "ST1702_OUTPUT_TRANSACTION_V2"
ROLLBACK_PHASE: Final = "ROLLBACK"
COMMIT_PHASE: Final = "COMMIT"
ABSENT_MARKER: Final = b"ST1702_OUTPUT_WAS_ABSENT_V1\n"
OUTPUT_MODE: Final = 0o644
PRIVATE_COMPANION_MODE: Final = 0o600

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
CANONICAL_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
SECURITY_CONTROLS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)

EXPECTED_SOURCES: Final = (
    (
        "integration",
        INTEGRATION_PATH,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "canonical_decisions",
        CANONICAL_DECISIONS_PATH,
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "open_decisions",
        OPEN_DECISIONS_PATH,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "story",
        STORY_PATH,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "security_controls",
        SECURITY_CONTROLS_PATH,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
)

ST1701_ARTIFACTS: Final = (
    (
        Path("changes/st-1701/contracts/mvp-business-decision-package.v1.yaml"),
        "7fa28f95bb3e36abd139052afadda72877129d244697ae3de91319a840022d9f",
    ),
    (
        Path("changes/st-1701/MVP-BUSINESS-DECISION-PACKAGE-APPROVAL-v1.yaml"),
        "749a9296837c58ea25a5a3e4a57b0aefd2dc41e94a0b5b34871ddce353d95c34",
    ),
    (
        Path("changes/st-1701/generated/gold-evidence-validation.v1.json"),
        "cbf7b267ccd1d51b9d2ab0a0d379529a2b2dc237cf65921468999968d677e4da",
    ),
)
ST0504_ARTIFACTS: Final = (
    (
        Path(
            "changes/st-0504/contracts/"
            "product-identity-human-review-reference-plan.v1.yaml"
        ),
        "246c21aa1d79489ed8c8a02fe0b7d1a50ffe1b2f7e85fcc4ba210369477512b8",
    ),
    (
        Path(
            "changes/st-0504/generated/"
            "product-identity-human-review-reference-plan.v1.json"
        ),
        "8c30308b4f18e250f2117b78d37a72059c9a36646c31e9906d565bee80d4ef90",
    ),
    (
        Path("changes/st-0504/manifest.yaml"),
        "f2f7478512c857b4ecd24e3ae360a7dc5ad0ff65829b5754d730b055c247b333",
    ),
)
ST1401_ARTIFACTS: Final = (
    (
        Path("changes/st-1401/README.md"),
        "ff02077940493d640b305e3a6f8ac0f6198bed01d88d64100f737814d3a565ed",
    ),
    (
        Path(
            "contracts/raos-v0.4/contracts/content/"
            "RAOS_06_freshness_update_policy_v0.1.yaml"
        ),
        "a4d490d2a54b3def63c9c240b09d34a759ebd3924e60cfcca438ee979334cea2",
    ),
    (
        Path("python/raos/domain/freshness/freshness.py"),
        "3a33b44d99f92fce6417257de8c170d4622dd900fe7cc7cbac0b67494469dd95",
    ),
    (
        Path("python/raos/ports/freshness.py"),
        "8b72de55a697bee06b4d43f3cda3b9dc12b1532091755876b6cab891aaa07d91",
    ),
    (
        Path("python/raos/application/freshness/freshness.py"),
        "f716a703af1581d6bb0ed2cde8db4a82848dd6d143bc5bb27ae4ad4353302c43",
    ),
    (
        Path("python/raos/adapters/recorded_freshness.py"),
        "83ad91d3301c48d3db3efa40c5835ae97dddaf22ebae4c5aa466bed8a0261ff5",
    ),
)
DEPENDENCY_ARTIFACTS: Final = (
    ("ST-1701", ST1701_ARTIFACTS),
    ("ST-0504", ST0504_ARTIFACTS),
    ("ST-1401", ST1401_ARTIFACTS),
)
DEPENDENCY_PATHS: Final = tuple(
    path for _story_id, artifacts in DEPENDENCY_ARTIFACTS for path, _digest in artifacts
)
INPUT_PATHS: Final = tuple(
    dict.fromkeys(
        (
            *SOURCE_PATHS,
            *(path for _role, path, _digest in EXPECTED_SOURCES),
            *DEPENDENCY_PATHS,
        )
    )
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "security_controls",
    "dependencies",
    "runtime_blockers",
    "open_decisions",
    "category_candidate",
    "fixture_boundary",
    "identity_boundary",
    "freshness_boundary",
    "human_review",
    "execution_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "security_controls",
    "dependency_bindings",
    "runtime_blockers",
    "open_decisions",
    "test_suites",
    "category_candidate",
    "fixture_boundary",
    "identity_boundary",
    "freshness_boundary",
    "human_review",
    "execution_boundary",
    "verification_boundary",
)
ACTION_COUNT_KEYS: Final = (
    "configure_category",
    "create_fixture",
    "create_golden_product",
    "evaluate_identity",
    "merge",
    "split",
    "apply_freshness_override",
    "assign_review",
    "review",
    "approve",
    "persist",
    "enqueue",
    "emit",
    "publish",
    "external",
)


class CategoryFixturesRulesReferenceError(RuntimeError):
    """Stable sanitized ST-1702 contract or generation failure."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"ST-1702 build failed: {code} field={field}")


def _fail(code: str, field: str) -> NoReturn:
    raise CategoryFixturesRulesReferenceError(code, field)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate and merge keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    if any(
        key_node.tag == "tag:yaml.org,2002:merge"
        or getattr(key_node, "value", None) == "<<"
        for key_node, _value_node in node.value
    ):
        raise ConstructorError(
            "while constructing a mapping",
            node.start_mark,
            "found forbidden merge key",
            node.start_mark,
        )
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
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(left_item, right_item)
            for left_item, right_item in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validate_relative(relative: Path, field: str) -> None:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        _fail("UNSAFE_PATH", field)


def _validate_owned_directory(metadata: os.stat_result, field: str) -> None:
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        _fail("UNSAFE_DIRECTORY", field)


def _validate_owned_regular(metadata: os.stat_result, field: str) -> None:
    prohibited = stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | 0o022
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) & prohibited
        or metadata.st_nlink != 1
    ):
        _fail("UNSAFE_FILE", field)


def _absolute_lexical_root(root: Path, field: str) -> Path:
    if not root.parts or any(part in {"", ".", ".."} for part in root.parts):
        _fail("UNSAFE_ROOT", field)
    absolute = root if root.is_absolute() else Path.cwd() / root
    normalized = Path(os.path.abspath(os.fspath(absolute)))
    if not normalized.is_absolute() or any(
        part in {"", ".", ".."} for part in normalized.parts[1:]
    ):
        _fail("UNSAFE_ROOT", field)
    return normalized


def _close_descriptor(descriptor: int) -> None:
    try:
        os.close(descriptor)
    except OSError:
        pass


def _close_descriptors(descriptors: list[int]) -> None:
    while descriptors:
        _close_descriptor(descriptors.pop())


def _before_repository_root_component_open(
    _absolute: Path,
    _component: str,
    _parent_descriptor: int,
) -> None:
    """Test-only race boundary in the physical repository-root walk."""


def _open_repository_root(root: Path, field: str) -> int:
    absolute = _absolute_lexical_root(root, field)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    descriptors: list[int] = []
    try:
        descriptors.append(os.open(os.path.sep, flags))
        for part in absolute.parts[1:]:
            _before_repository_root_component_open(
                absolute,
                part,
                descriptors[-1],
            )
            descriptors.append(os.open(part, flags, dir_fd=descriptors[-1]))
        return descriptors.pop()
    except CategoryFixturesRulesReferenceError:
        raise
    except OSError:
        _fail("UNSAFE_ROOT", field)
    finally:
        _close_descriptors(descriptors)


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


def _after_input_open(_root: Path, _relative: Path, _descriptor: int) -> None:
    """Test-only source-race boundary; production execution is inert."""


def _after_input_component_stat(
    _root: Path,
    _relative: Path,
    _component: str,
    _parent_descriptor: int,
) -> None:
    """Test-only ancestor-race boundary; production execution is inert."""


def _after_input_leaf_stat(
    _root: Path,
    _relative: Path,
    _parent_descriptor: int,
) -> None:
    """Test-only leaf-race boundary; production execution is inert."""


def _read(root: Path, relative: Path, field: str) -> bytes:
    _validate_relative(relative, field)
    parent_descriptor = -1
    descriptor = -1
    try:
        parent_descriptor = _open_repository_root(root, field)
        _validate_owned_directory(os.fstat(parent_descriptor), field)
        for part in relative.parts[:-1]:
            before = os.stat(
                part,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            _validate_owned_directory(before, field)
            _after_input_component_stat(root, relative, part, parent_descriptor)
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
            opened = os.fstat(child)
            _validate_owned_directory(opened, field)
            if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                os.close(child)
                _fail("PATH_CHANGED", field)
            os.close(parent_descriptor)
            parent_descriptor = child
        name = relative.parts[-1]
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        _validate_owned_regular(before, field)
        if before.st_size > MAX_SOURCE_BYTES:
            _fail("FILE_SIZE_LIMIT", field)
        _after_input_leaf_stat(root, relative, parent_descriptor)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_descriptor,
        )
        opened = os.fstat(descriptor)
        _validate_owned_regular(opened, field)
        if _stable_file_identity(opened) != _stable_file_identity(before):
            _fail("PATH_CHANGED", field)
        if opened.st_size > MAX_SOURCE_BYTES:
            _fail("FILE_SIZE_LIMIT", field)
        _after_input_open(root, relative, descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_SOURCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                _fail("FILE_SIZE_LIMIT", field)
        content = b"".join(chunks)
        if len(content) > MAX_SOURCE_BYTES:
            _fail("FILE_SIZE_LIMIT", field)
        after_open = os.fstat(descriptor)
        after_descriptor = os.stat(
            name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        _validate_owned_regular(after_descriptor, field)
        if (
            _stable_file_identity(opened) != _stable_file_identity(after_open)
            or _stable_file_identity(opened) != _stable_file_identity(after_descriptor)
            or len(content) != opened.st_size
        ):
            _fail("PATH_CHANGED", field)
        return content
    except CategoryFixturesRulesReferenceError:
        raise
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)


def _parse_yaml(content: bytes, field: str) -> Mapping[str, Any]:
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                _fail("YAML_ALIAS_FORBIDDEN", field)
        loaded = yaml.load(text, Loader=UniqueKeyLoader)
    except CategoryFixturesRulesReferenceError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", field)
    return _mapping(loaded, field)


def _parse_json(content: bytes, field: str) -> Mapping[str, Any]:
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
    except CategoryFixturesRulesReferenceError:
        raise
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(loaded, field)


def _input(inputs: Mapping[Path, bytes], relative: Path, field: str) -> bytes:
    try:
        return inputs[relative]
    except KeyError:
        _fail("INPUT_INVENTORY_DRIFT", field)


def _load_yaml(
    inputs: Mapping[Path, bytes], relative: Path, field: str
) -> Mapping[str, Any]:
    return _parse_yaml(_input(inputs, relative, field), field)


def _load_json(
    inputs: Mapping[Path, bytes], relative: Path, field: str
) -> Mapping[str, Any]:
    return _parse_json(_input(inputs, relative, field), field)


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path.as_posix()}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _artifact_rows(
    artifacts: tuple[tuple[Path, str], ...],
) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in artifacts
    ]


def _dependency_row(
    story_id: str,
    status: str,
    connection_status: str,
    artifacts: tuple[tuple[Path, str], ...],
) -> dict[str, object]:
    return {
        "story_id": story_id,
        "status": status,
        "canonical_story_status": "NOT_STARTED",
        "canonical_verification_status": "NOT_EXECUTED",
        "canonical_acceptance": "NOT_ACHIEVED",
        "st1702_ready": False,
        "connection_status": connection_status,
        "artifacts": _artifact_rows(artifacts),
    }


EXPECTED_DOCUMENT: Final[dict[str, object]] = {
    "id": "RAOS-ST1702-CATEGORY-FIXTURES-RULES-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-1702",
    "classification": (
        "SOURCE_DERIVED_NON_EXECUTABLE_CATEGORY_FIXTURES_RULES_REFERENCE_PLAN"
    ),
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "st1702_ready": False,
    "production_eligible": False,
    "approval": None,
    "canonical_mutation_authority": "NONE",
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_AUTHORITY: Final[dict[str, object]] = {
    "precedence": (
        "CANONICAL_INTEGRATION_THEN_DECISIONS_STORY_TEST_SECURITY_AND_BOUND_DEPENDENCIES"
    ),
    "integration_base_commit": INTEGRATION_BASE_COMMIT,
    "sources": _source_rows(),
}
SECURITY_CONTROL_IDS: Final = (
    "SEC-DATA-003",
    "SEC-DATA-004",
    "SEC-DATA-006",
    "SEC-AI-007",
    "SEC-SDLC-002",
    "SEC-SDLC-006",
    "SEC-SDLC-009",
    "SEC-SDLC-012",
)
EXPECTED_SECURITY_BOUNDARY: Final[dict[str, object]] = {
    "formal_verification": "NOT_EXECUTED",
    "evidence": None,
    "required": list(SECURITY_CONTROL_IDS),
}
EXPECTED_DEPENDENCIES: Final = (
    _dependency_row(
        "ST-1701",
        "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "SOURCE_BOUND_NOT_ACTIVATED",
        ST1701_ARTIFACTS,
    ),
    _dependency_row(
        "ST-0504",
        ("SOURCE_DERIVED_NON_EXECUTABLE_PRODUCT_IDENTITY_HUMAN_REVIEW_REFERENCE_PLAN"),
        "SOURCE_BOUND_NOT_CONNECTED",
        ST0504_ARTIFACTS,
    ),
    _dependency_row(
        "ST-1401",
        "PROVISIONAL_CANONICAL_SAFE_DEFAULT_DISABLED_RECORDED_FRESHNESS_INTERFACE",
        "SOURCE_BOUND_NOT_CONNECTED",
        ST1401_ARTIFACTS,
    ),
)
EXPECTED_BLOCKER_CONDITIONS: Final = (
    ("OD001_CANONICAL_RESOLUTION", "NOT_OBTAINED"),
    ("OD005_ALTERNATE_REVIEWER_OR_APPROVED_EXCEPTION", "NOT_SATISFIED"),
    ("OD006_GOLD_EVIDENCE", "NOT_OBTAINED"),
    ("OD006_DOMAIN_EDITOR_ACCEPTANCE", "NOT_OBTAINED"),
    ("OD007_CANONICAL_RESOLUTION", "NOT_OBTAINED"),
    ("ST1701_CANONICAL_REVISION_APPROVAL_AND_IMPORT", "NOT_EXECUTED"),
    ("TST032_FORMAL", "NOT_EXECUTED"),
    ("ST0504_RUNTIME_IDENTITY_ENGINE", "NOT_CREATED"),
    ("TST007_FORMAL", "NOT_EXECUTED"),
    ("ST1401_CATEGORY_FRESHNESS_ACTIVATION", "DISABLED_UNRESOLVED_OD_007"),
    ("TST005_FORMAL", "NOT_EXECUTED"),
    ("TST028_FORMAL", "NOT_EXECUTED"),
    ("RUNTIME_CATEGORY_CONFIG", "NOT_CREATED"),
    ("GOLDEN_PRODUCTS", "NOT_CREATED"),
    ("ST1702_DOMAIN_REVIEWER_APPROVAL", "NOT_OBTAINED"),
    ("TST020_FORMAL", "NOT_EXECUTED"),
)
EXPECTED_RUNTIME_BLOCKERS: Final[dict[str, object]] = {
    "status": "BLOCKED",
    "canonical_global_unresolved_blocker_count": 14,
    "canonical_scoped_unresolved_count": 7,
    "gate_state": "BLOCKED",
    "st1701_acceptance": "NOT_ACHIEVED",
    "st1702_ready": False,
    "required_conditions": [
        {"id": identity, "status": status}
        for identity, status in EXPECTED_BLOCKER_CONDITIONS
    ],
}
EXPECTED_OPEN_DECISIONS: Final = (
    {
        "id": "OD-001",
        "canonical_status": "HUMAN_DECISION_REQUIRED",
        "blocking": True,
        "resolved": False,
        "candidate_authority": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "safe_default": (
            "STOP_CATEGORY_SPECIFIC_IMPLEMENTATION_SYNTHETIC_FIXTURES_ONLY"
        ),
        "runtime_activation": "DISABLED",
    },
    {
        "id": "OD-006",
        "canonical_status": "EXTERNAL_EVIDENCE_REQUIRED",
        "blocking": True,
        "resolved": False,
        "candidate_authority": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "safe_default": "NO_AUTOMATIC_MERGE_HUMAN_REVIEW_REQUIRED",
        "runtime_activation": "DISABLED",
    },
    {
        "id": "OD-007",
        "canonical_status": "HUMAN_DECISION_REQUIRED",
        "blocking": True,
        "resolved": False,
        "candidate_authority": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "safe_default": "PROVISIONAL_SAFE_DEFAULT_STALE_HIDE_NO_CATEGORY_OVERRIDE",
        "runtime_activation": "DISABLED",
    },
)
EXPECTED_CATEGORY_CANDIDATE: Final[dict[str, object]] = {
    "source_story": "ST-1701",
    "category_id": "suitcase_and_carry_bags",
    "display_name_ja": "スーツケース・キャリーバッグ",
    "classification": "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
    "candidate_record_status": "OWNER_APPROVED",
    "canonical_resolution": "UNCHANGED_UNRESOLVED",
    "runtime_activation": "DISABLED",
    "category_specific_implementation": "STOPPED",
    "runtime_category_config": "NOT_CREATED",
    "golden_products": "NOT_CREATED",
    "attribute_schema": "NOT_CREATED",
    "category_attributes": [],
    "source_observations": [],
    "provider_evidence": [],
    "allowed_test_data": "SYNTHETIC_VALIDATOR_FIXTURES_ONLY",
    "production_data": "FORBIDDEN",
}
EXPECTED_FIXTURE_BOUNDARY: Final[dict[str, object]] = {
    "reference_only": True,
    "runtime_category_config": "NOT_CREATED",
    "fixture_schema": "NOT_CREATED",
    "fixture_records": [],
    "golden_products": "NOT_CREATED",
    "golden_product_records": [],
    "runtime_loader": "NOT_CREATED",
    "source_snapshots": [],
    "provider_observations": [],
    "evidence_records": [],
    "creation_authority": "NONE",
    "empty_interpretation": "NO_CATEGORY_FIXTURE_OR_GOLDEN_PRODUCT_ARTIFACT_EXISTS",
}
EXPECTED_IDENTITY_BOUNDARY: Final[dict[str, object]] = {
    "source_story": "ST-0504",
    "open_decision_id": "OD-006",
    "canonical_status": "EXTERNAL_EVIDENCE_REQUIRED",
    "gold_evidence_status": "EVIDENCE_INSUFFICIENT",
    "gold_evidence_stop_code": "STOP_EVIDENCE_INSUFFICIENT",
    "domain_editor_approval": "NOT_OBTAINED",
    "human_review_required": True,
    "automatic_merge_enabled": False,
    "automatic_split_enabled": False,
    "candidate_rule_source_bound_not_applied": True,
    "rule_config": "NOT_CREATED",
    "rules": [],
    "thresholds": [],
    "scores": [],
    "identity_decisions": [],
    "membership_records": [],
    "merge_records": [],
    "split_records": [],
    "rule_engine": "NOT_EXECUTED",
}
EXPECTED_FRESHNESS_BOUNDARY: Final[dict[str, object]] = {
    "source_story": "ST-1401",
    "open_decision_id": "OD-007",
    "canonical_status": "HUMAN_DECISION_REQUIRED",
    "policy_authority": "PROVISIONAL_CANONICAL_SAFE_DEFAULT",
    "policy_activation": "DISABLED_UNRESOLVED_OD_007",
    "policy_active": False,
    "st1701_candidate_sla_bound_not_applied": True,
    "runtime_freshness_config": "NOT_CREATED",
    "category_overrides": [],
    "provider_overrides": [],
    "category_override_applied": False,
    "provider_override_applied": False,
    "stale_never_treated_as_fresh": True,
    "recommendation_auto_reorder": "FORBIDDEN",
    "scheduler_connection": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
}
EXPECTED_HUMAN_REVIEW: Final[dict[str, object]] = {
    "required": True,
    "status": "REQUIRED_NOT_EXECUTED",
    "domain_reviewer_approval": "NOT_OBTAINED",
    "routing_status": "NOT_CONFIGURED",
    "queue": None,
    "route": None,
    "reviewer": None,
    "actor": None,
    "role": None,
    "assignment": None,
    "sla": None,
    "approval": None,
    "review_records": [],
    "delivery_records": [],
}
EXPECTED_ACTION_COUNTS: Final = {name: 0 for name in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION_BOUNDARY: Final[dict[str, object]] = {
    "enabled": False,
    "status": "DISABLED",
    "runtime_category_config": "NOT_CREATED",
    "golden_products": "NOT_CREATED",
    "category_rule_engine": "NOT_EXECUTED",
    "freshness_scheduler": "NOT_EXECUTED",
    "human_review": "NOT_EXECUTED",
    "repository": "ABSENT",
    "database": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "external_authority": "NONE",
    "action_counts": EXPECTED_ACTION_COUNTS,
}
EXPECTED_VERIFICATION_BOUNDARY: Final[dict[str, object]] = {
    "local_generation": "IMPLEMENTATION_ONLY_NOT_FORMAL_VALIDATION",
    "formal_tst_020": "NOT_EXECUTED",
    "dependency_tst_032": "NOT_EXECUTED",
    "dependency_tst_007": "NOT_EXECUTED",
    "dependency_tst_005": "NOT_EXECUTED",
    "dependency_tst_028": "NOT_EXECUTED",
    "domain_reviewer_approval": "NOT_EXECUTED",
    "runtime": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "decision": "NOT_READY",
    "approval": None,
    "story_acceptance": False,
    "st1702_ready": False,
    "production_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}

EXPECTED_STORIES: Final = (
    {
        "id": "ST-1702",
        "epic_id": "EPIC-17",
        "title": "Create category fixtures and rules",
        "objective": "初期カテゴリの属性/identity/freshnessを実装",
        "depends_on": ["ST-1701", "ST-0504", "ST-1401"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["category config", "golden products"],
        "acceptance_criteria": ["domain reviewer approval"],
        "test_suites": ["TST-020"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": [],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    {
        "id": "ST-1701",
        "epic_id": "EPIC-17",
        "title": "Resolve MVP business inputs",
        "objective": "カテゴリ/ブランド/reviewer/SLA/budgetを確定",
        "depends_on": ["ST-0006"],
        "requirement_ids": [],
        "design_refs": [],
        "deliverables": ["approved decisions"],
        "acceptance_criteria": ["OD-001/002/005/006/007/008/009 resolved"],
        "test_suites": ["TST-032"],
        "priority": "P0",
        "mvp": True,
        "size": "M",
        "open_decisions": [
            "OD-001",
            "OD-002",
            "OD-005",
            "OD-006",
            "OD-007",
            "OD-008",
            "OD-009",
        ],
        "one_pr_preferred": True,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    {
        "id": "ST-0504",
        "epic_id": "EPIC-05",
        "title": "Product identity decision engine",
        "objective": "自動候補とHuman統合/分離Decision",
        "depends_on": ["ST-0503"],
        "requirement_ids": ["FR-003"],
        "design_refs": [],
        "deliverables": ["rule engine", "decision history"],
        "acceptance_criteria": [
            "ambiguous defaults to review",
            "supersede not mutate",
        ],
        "test_suites": ["TST-007", "TST-020"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": ["OD-006"],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
    {
        "id": "ST-1401",
        "epic_id": "EPIC-14",
        "title": "Freshness scheduler and state",
        "objective": "Fact/Offer/Link/articleの期限を評価",
        "depends_on": ["ST-0503", "ST-0605"],
        "requirement_ids": ["FR-012"],
        "design_refs": [],
        "deliverables": ["scheduler", "state"],
        "acceptance_criteria": ["category SLA version", "stale not fresh"],
        "test_suites": ["TST-005", "TST-028"],
        "priority": "P0",
        "mvp": True,
        "size": "L",
        "open_decisions": ["OD-007"],
        "one_pr_preferred": False,
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    },
)
EXPECTED_OPEN_DECISION_ROWS: Final = (
    {
        "id": "OD-001",
        "topic": "initial_category",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "MVP vertical slice",
        "owner": "Product Owner",
        "decision_needed": "低リスクで比較軸が構造化可能な最初のカテゴリを1つ選定",
        "default_behavior": "カテゴリ固有実装を停止し合成Fixtureのみ使用",
        "blocking": True,
    },
    {
        "id": "OD-006",
        "topic": "category_product_identity_rules",
        "status": "EXTERNAL_EVIDENCE_REQUIRED",
        "required_by": "Catalog grouping",
        "owner": "Domain Editor",
        "decision_needed": "型番、容量、色、セット、JAN等の統合/分離ルールをカテゴリごとに定義",
        "default_behavior": "自動統合せずHuman Reviewへ送る",
        "blocking": True,
    },
    {
        "id": "OD-007",
        "topic": "category_freshness_sla",
        "status": "HUMAN_DECISION_REQUIRED",
        "required_by": "Publication and refresh",
        "owner": "Managing Editor",
        "decision_needed": "価格、在庫、仕様、画像、リンクの最大許容Ageを定義",
        "default_behavior": "保守的な暫定値を適用しStale時は非表示",
        "blocking": True,
    },
)
EXPECTED_TEST_SUITES: Final = (
    {
        "id": "TST-020",
        "name": "Content AST and policy",
        "layer": "content",
        "purpose": "5記事型、Block、Claim、Recommendation、Disclosure",
        "candidate_tools": ["pytest", "schema fixtures"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
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
    {
        "id": "TST-007",
        "name": "Property-based domain tests",
        "layer": "unit",
        "purpose": "冪等性、状態遷移、金額、正規化の不変条件",
        "candidate_tools": ["hypothesis", "fast-check"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    {
        "id": "TST-005",
        "name": "Python unit",
        "layer": "unit",
        "purpose": "Domain value/object/policyの局所Test",
        "candidate_tools": ["pytest"],
        "release_blocking": True,
        "environments": ["CI"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
    {
        "id": "TST-028",
        "name": "Reliability failure injection",
        "layer": "reliability",
        "purpose": "provider/queue/db/timeouts/retry/kill switch",
        "candidate_tools": ["fault proxy", "scripts"],
        "release_blocking": True,
        "environments": ["staging"],
        "owner": "Engineering",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "execution_status": "NOT_EXECUTED",
    },
)


def _security_control(
    identity: str, category: str, title: str, requirement: str, verification: str
) -> dict[str, object]:
    return {
        "id": identity,
        "category": category,
        "title": title,
        "requirement": requirement,
        "verification": verification,
        "priority": "P0" if category in {"DATA", "AI"} else "P1",
        "gate": "GATE-0",
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }


EXPECTED_SECURITY_CONTROLS: Final = (
    _security_control(
        "SEC-DATA-003",
        "DATA",
        "Secret storage",
        "SecretをDB/Repo/Logへ置かない",
        "secret scan",
    ),
    _security_control(
        "SEC-DATA-004",
        "DATA",
        "Object integrity",
        "Raw/SnapshotへSHA-256とVersionを記録",
        "tamper test",
    ),
    _security_control(
        "SEC-DATA-006",
        "DATA",
        "Public projection isolation",
        "Public roleはreadmodelのみ",
        "DB grant test",
    ),
    _security_control(
        "SEC-AI-007",
        "AI",
        "Human gate",
        "Critical Task出力は承認・公開できない",
        "authorization/E2E",
    ),
    _security_control(
        "SEC-SDLC-002",
        "SDLC",
        "CODEOWNERS",
        "Security、migration、contractsへowner review",
        "PR test",
    ),
    _security_control(
        "SEC-SDLC-006",
        "SDLC",
        "Secret scanning",
        "History/PR/artifactをscan",
        "CI evidence",
    ),
    _security_control(
        "SEC-SDLC-009",
        "SDLC",
        "Reproducible generation",
        "OpenAPI/Schema生成のdriftを検知",
        "CI evidence",
    ),
    _security_control(
        "SEC-SDLC-012",
        "SDLC",
        "Environment protection",
        "Production deployはHuman approval",
        "GitHub environment evidence",
    ),
)
EXPECTED_CANONICAL_DECISIONS: Final = (
    {
        "id": "INT-DEC-009",
        "title": "自動更新境界",
        "status": "RESOLVED",
        "decision": "取得済みFactの決定的更新と安全な非表示は自動化可。Claim、Recommendation順位、公開本文変更は人間承認を要する",
        "implementation_effect": "auto-publishはMVPで無効",
    },
    {
        "id": "INT-DEC-013",
        "title": "Codexの権限",
        "status": "RESOLVED",
        "decision": "Codexは実装者であり、法務、公開、Production Secret、Kill Switch解除、最終承認の権限を持たない",
        "implementation_effect": "PRとHuman Approvalを必須化",
    },
    {
        "id": "INT-DEC-015",
        "title": "Production Readiness",
        "status": "RESOLVED",
        "decision": "全設計完了後もRuntime Test、Security Review、Backup Restore、GATE-0合格までProduction Readyとしない",
        "implementation_effect": "Master StatusはNOT_READYから開始",
    },
)


def _validate_hashes(inputs: Mapping[Path, bytes]) -> None:
    for _role, path, digest in EXPECTED_SOURCES:
        if _sha256(_input(inputs, path, "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for _story_id, artifacts in DEPENDENCY_ARTIFACTS:
        for path, digest in artifacts:
            if _sha256(_input(inputs, path, "dependency.artifact")) != digest:
                _fail("DEPENDENCY_HASH_DRIFT", "dependency.artifact")


def _validate_authority_semantics(inputs: Mapping[Path, bytes]) -> None:
    stories = _load_yaml(inputs, STORY_PATH, "story")
    for expected in EXPECTED_STORIES:
        _exact(
            _find(stories.get("stories"), cast(str, expected["id"]), "story"),
            expected,
            "story",
        )
    decisions = _load_yaml(inputs, OPEN_DECISIONS_PATH, "open_decision")
    for expected in EXPECTED_OPEN_DECISION_ROWS:
        _exact(
            _find(
                decisions.get("items"),
                cast(str, expected["id"]),
                "open_decision",
            ),
            expected,
            "open_decision",
        )
    catalog = _load_yaml(inputs, TEST_CATALOG_PATH, "test_suites")
    for expected in EXPECTED_TEST_SUITES:
        _exact(
            _find(catalog.get("suites"), cast(str, expected["id"]), "test_suites"),
            expected,
            "test_suites",
        )
    controls = _load_yaml(inputs, SECURITY_CONTROLS_PATH, "security_controls")
    for expected in EXPECTED_SECURITY_CONTROLS:
        _exact(
            _find(
                controls.get("controls"),
                cast(str, expected["id"]),
                "security_controls",
            ),
            expected,
            "security_controls",
        )
    canonical = _load_yaml(inputs, CANONICAL_DECISIONS_PATH, "canonical_decisions")
    for expected_decision in EXPECTED_CANONICAL_DECISIONS:
        _exact(
            _find(
                canonical.get("decisions"),
                expected_decision["id"],
                "canonical_decisions",
            ),
            expected_decision,
            "canonical_decisions",
        )


def _validate_st1701_semantics(inputs: Mapping[Path, bytes]) -> None:
    package = _load_yaml(inputs, ST1701_ARTIFACTS[0][0], "dependency.st1701.package")
    package_document = _mapping(package.get("document"), "dependency.st1701.document")
    _exact(
        package_document.get("classification"),
        "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "dependency.st1701.document",
    )
    _exact(package_document.get("executable"), False, "dependency.st1701.document")
    _exact(
        package_document.get("canonical_resolution_authority"),
        "NONE",
        "dependency.st1701.document",
    )
    truth = _mapping(package.get("canonical_truth_boundary"), "dependency.st1701.truth")
    for key, expected in (
        ("scoped_unresolved_count", 7),
        ("global_unresolved_blocker_count", 14),
        ("global_blocked_target_count", 6),
        ("activation", "BLOCKED_UNRESOLVED_INPUTS"),
        ("gate_state", "BLOCKED"),
        ("st1701_acceptance", "NOT_ACHIEVED"),
        ("effective_canonical_status", "UNCHANGED"),
    ):
        _exact(truth.get(key), expected, "dependency.st1701.truth")
    od001 = _find(package.get("scoped_decisions"), "OD-001", "dependency.st1701.od001")
    _exact(
        od001.get("selected_value"),
        {
            "category_id": "suitcase_and_carry_bags",
            "display_name_ja": "スーツケース・キャリーバッグ",
        },
        "dependency.st1701.od001",
    )
    _exact(od001.get("runtime_activation"), "DISABLED", "dependency.st1701.od001")
    _exact(od001.get("synthetic_fixture_use_only"), True, "dependency.st1701.od001")
    od006 = _find(package.get("scoped_decisions"), "OD-006", "dependency.st1701.od006")
    _exact(od006.get("record_status"), "EVIDENCE_PENDING", "dependency.st1701.od006")
    _exact(
        od006.get("runtime_automatic_merge"),
        "DISABLED_PENDING_EVIDENCE_AND_CANONICAL_REVISION",
        "dependency.st1701.od006",
    )
    od007 = _find(package.get("scoped_decisions"), "OD-007", "dependency.st1701.od007")
    _exact(
        od007.get("runtime_activation"),
        "DISABLED_PENDING_CANONICAL_REVISION",
        "dependency.st1701.od007",
    )
    implementation = _mapping(
        package.get("implementation_boundary"), "dependency.st1701.implementation"
    )
    suitcase = _mapping(
        implementation.get("suitcase_candidate_boundary"),
        "dependency.st1701.suitcase",
    )
    for key, expected in (
        ("runtime_config", "NOT_CREATED"),
        ("golden_products", "NOT_CREATED"),
        ("production_data", "FORBIDDEN"),
        ("external_fetch", "FORBIDDEN"),
        ("st1702_authority", "NOT_GRANTED"),
        ("allowed_test_data", "SYNTHETIC_VALIDATOR_FIXTURES_ONLY"),
    ):
        _exact(suitcase.get(key), expected, "dependency.st1701.suitcase")
    actions = _mapping(package.get("action_boundary"), "dependency.st1701.actions")
    for key, expected in (
        ("runtime_category_config", "NOT_CREATED"),
        ("golden_products", "NOT_CREATED"),
        ("external_actions", "NOT_AUTHORIZED"),
        ("provider_actions", "NOT_AUTHORIZED"),
        ("publication", "NOT_AUTHORIZED"),
        ("staging", "NOT_AUTHORIZED"),
        ("release", "NOT_AUTHORIZED"),
        ("production", "NOT_AUTHORIZED"),
    ):
        _exact(actions.get(key), expected, "dependency.st1701.actions")

    approval_wrapper = _load_yaml(
        inputs, ST1701_ARTIFACTS[1][0], "dependency.st1701.approval"
    )
    approval = _mapping(
        approval_wrapper.get("MVP_BUSINESS_DECISION_PACKAGE_APPROVAL_V1"),
        "dependency.st1701.approval",
    )
    _exact(
        approval.get("status"),
        "APPROVED_AS_NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE",
        "dependency.st1701.approval",
    )
    _exact(
        approval.get("authority"),
        "OWNER_APPROVED_CANONICAL_REVISION_EVIDENCE_CANDIDATE_ONLY",
        "dependency.st1701.approval",
    )
    effective = _mapping(
        approval.get("effective_boundary"), "dependency.st1701.effective"
    )
    _exact(effective.get("st1702_ready"), False, "dependency.st1701.effective")
    _exact(
        effective.get("canonical_mutation_authority"),
        "NONE",
        "dependency.st1701.effective",
    )
    _exact(effective.get("gate_state"), "BLOCKED", "dependency.st1701.effective")
    remaining = _mapping(
        approval.get("remaining_prerequisites"), "dependency.st1701.remaining"
    )
    _exact(
        remaining,
        {
            "od005_alternate_reviewer_or_approved_exception": "NOT_SATISFIED",
            "od006_gold_evidence": "NOT_OBTAINED",
            "od006_domain_editor_acceptance": "NOT_OBTAINED",
            "formal_tst_032": "NOT_EXECUTED",
            "canonical_revision_approval_and_import": "NOT_EXECUTED",
        },
        "dependency.st1701.remaining",
    )

    gold = _load_json(inputs, ST1701_ARTIFACTS[2][0], "dependency.st1701.gold")
    for key, expected in (
        ("status", "EVIDENCE_INSUFFICIENT"),
        ("stop_code", "STOP_EVIDENCE_INSUFFICIENT"),
        ("authority", "PROPOSAL_ONLY_NON_CANONICAL"),
    ):
        _exact(gold.get(key), expected, "dependency.st1701.gold")
    ledger = _mapping(gold.get("ledger_boundary"), "dependency.st1701.ledger")
    _exact(ledger.get("ledger_present"), False, "dependency.st1701.ledger")
    _exact(
        ledger.get("domain_editor_approval_present"),
        False,
        "dependency.st1701.ledger",
    )
    non_promotion = _mapping(
        gold.get("non_promotion_boundary"), "dependency.st1701.non_promotion"
    )
    for key, expected in (
        ("global_unresolved_blocker_count", 14),
        ("gate_state", "BLOCKED"),
        ("st1701_acceptance", "NOT_ACHIEVED"),
        ("tst_032", "NOT_EXECUTED"),
        ("st1702_ready", False),
        ("publication", "NOT_EXECUTED"),
        ("staging", "NOT_EXECUTED"),
        ("release", "NOT_EXECUTED"),
        ("production", "NOT_EXECUTED"),
    ):
        _exact(non_promotion.get(key), expected, "dependency.st1701.non_promotion")


def _validate_st0504_semantics(inputs: Mapping[Path, bytes]) -> None:
    contract = _load_yaml(inputs, ST0504_ARTIFACTS[0][0], "dependency.st0504.contract")
    document = _mapping(contract.get("document"), "dependency.st0504.document")
    _exact(document.get("executable"), False, "dependency.st0504.document")
    _exact(document.get("story_acceptance"), False, "dependency.st0504.document")
    decision = _mapping(contract.get("open_decision"), "dependency.st0504.od006")
    _exact(decision.get("resolved"), False, "dependency.st0504.od006")
    _exact(decision.get("blocking"), True, "dependency.st0504.od006")
    review = _mapping(contract.get("human_review_default"), "dependency.st0504.review")
    _exact(review.get("required"), True, "dependency.st0504.review")
    _exact(review.get("status"), "REQUIRED_NOT_EXECUTED", "dependency.st0504.review")
    identity = _mapping(contract.get("identity_defaults"), "dependency.st0504.identity")
    _exact(identity.get("automatic_merge_enabled"), False, "dependency.st0504.identity")
    _exact(identity.get("automatic_split_enabled"), False, "dependency.st0504.identity")
    _exact(identity.get("identity_decisions"), [], "dependency.st0504.identity")
    execution = _mapping(
        contract.get("execution_boundary"), "dependency.st0504.execution"
    )
    _exact(execution.get("enabled"), False, "dependency.st0504.execution")
    _exact(execution.get("rule_engine"), "NOT_EXECUTED", "dependency.st0504.execution")
    _exact(execution.get("database"), "NOT_EXECUTED", "dependency.st0504.execution")

    plan = _load_json(inputs, ST0504_ARTIFACTS[1][0], "dependency.st0504.plan")
    _exact(
        _mapping(plan.get("document"), "dependency.st0504.plan").get("executable"),
        False,
        "dependency.st0504.plan",
    )
    plan_identity = _mapping(
        plan.get("identity_boundary"), "dependency.st0504.plan_identity"
    )
    _exact(
        plan_identity.get("automatic_merge_enabled"),
        False,
        "dependency.st0504.plan_identity",
    )
    _exact(
        plan_identity.get("automatic_split_enabled"),
        False,
        "dependency.st0504.plan_identity",
    )
    manifest = _load_yaml(inputs, ST0504_ARTIFACTS[2][0], "dependency.st0504.manifest")
    boundary = _mapping(manifest.get("boundary"), "dependency.st0504.boundary")
    for key, expected in (
        ("human_review", "NOT_EXECUTED"),
        ("rule_engine", "NOT_EXECUTED"),
        ("formal_tst_007", "NOT_EXECUTED"),
        ("formal_tst_020", "NOT_EXECUTED"),
        ("story_acceptance", False),
    ):
        _exact(boundary.get(key), expected, "dependency.st0504.boundary")


def _validate_st1401_semantics(inputs: Mapping[Path, bytes]) -> None:
    readme = _input(inputs, ST1401_ARTIFACTS[0][0], "dependency.st1401.readme").decode(
        "utf-8", errors="strict"
    )
    required_readme = (
        "PROVISIONAL_CANONICAL_SAFE_DEFAULT_DISABLED_RECORDED_FRESHNESS_INTERFACE",
        "`DISABLED_UNRESOLVED_OD_007`",
        "Category/provider",
        "overrides remain unapplied",
        "Formal/hosted TST-005",
        "staging reliability TST-028",
    )
    if any(fragment not in readme for fragment in required_readme):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1401.readme")
    policy = _load_yaml(inputs, ST1401_ARTIFACTS[1][0], "dependency.st1401.policy")
    metadata = _mapping(policy.get("document"), "dependency.st1401.policy")
    _exact(metadata.get("id"), "RAOS-CONTENT-FRESH-001", "dependency.st1401.policy")
    _exact(policy.get("policy_version"), "1.0.0", "dependency.st1401.policy")
    _exact(
        policy.get("threshold_status"),
        "PROVISIONAL; category and provider overrides require approval and measurement",
        "dependency.st1401.policy",
    )
    priorities = _list(
        policy.get("safe_degradation_priority"), "dependency.st1401.policy"
    )
    if "never_auto_reorder_recommendations" not in priorities:
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1401.policy")
    domain = _input(inputs, ST1401_ARTIFACTS[2][0], "dependency.st1401.domain").decode(
        "utf-8", errors="strict"
    )
    required_domain = (
        'FRESHNESS_OPEN_DECISION_ID = "OD-007"',
        'PROVISIONAL_CANONICAL_SAFE_DEFAULT = "PROVISIONAL_CANONICAL_SAFE_DEFAULT"',
        'DISABLED_UNRESOLVED_OD_007 = "DISABLED_UNRESOLVED_OD_007"',
        "category_override_applied=False",
        "provider_override_applied=False",
        "persistence=FreshnessPersistenceStatus.NOT_EXECUTED",
        "recommendation_order_action=RecommendationOrderAction.FORBIDDEN",
    )
    if any(fragment not in domain for fragment in required_domain):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1401.domain")
    port = _input(inputs, ST1401_ARTIFACTS[3][0], "dependency.st1401.port").decode(
        "utf-8", errors="strict"
    )
    if (
        "def evaluate(" not in port
        or "def select_due(" not in port
        or any(
            fragment in port
            for fragment in ("def publish(", "def persist(", "def save(")
        )
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1401.port")


def _validate_dependency_semantics(inputs: Mapping[Path, bytes]) -> None:
    _validate_st1701_semantics(inputs)
    _validate_st0504_semantics(inputs)
    _validate_st1401_semantics(inputs)


def _capture_inputs(root: Path) -> dict[Path, bytes]:
    captured = {relative: _read(root, relative, "input") for relative in INPUT_PATHS}
    if tuple(captured) != INPUT_PATHS:
        _fail("INPUT_INVENTORY_DRIFT", "input")
    return captured


def _validate_contract_with_inputs(
    contract: Mapping[str, Any], inputs: Mapping[Path, bytes]
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _exact(contract["authority"], EXPECTED_AUTHORITY, "authority")
    _exact(
        contract["security_controls"],
        EXPECTED_SECURITY_BOUNDARY,
        "security_controls",
    )
    _exact(contract["dependencies"], list(EXPECTED_DEPENDENCIES), "dependencies")
    _exact(contract["runtime_blockers"], EXPECTED_RUNTIME_BLOCKERS, "runtime_blockers")
    _exact(contract["open_decisions"], list(EXPECTED_OPEN_DECISIONS), "open_decisions")
    _exact(
        contract["category_candidate"],
        EXPECTED_CATEGORY_CANDIDATE,
        "category_candidate",
    )
    _exact(contract["fixture_boundary"], EXPECTED_FIXTURE_BOUNDARY, "fixture_boundary")
    _exact(
        contract["identity_boundary"],
        EXPECTED_IDENTITY_BOUNDARY,
        "identity_boundary",
    )
    _exact(
        contract["freshness_boundary"],
        EXPECTED_FRESHNESS_BOUNDARY,
        "freshness_boundary",
    )
    _exact(contract["human_review"], EXPECTED_HUMAN_REVIEW, "human_review")
    _exact(
        contract["execution_boundary"],
        EXPECTED_EXECUTION_BOUNDARY,
        "execution_boundary",
    )
    _exact(
        contract["verification_boundary"],
        EXPECTED_VERIFICATION_BOUNDARY,
        "verification_boundary",
    )
    _validate_hashes(inputs)
    _validate_authority_semantics(inputs)
    _validate_dependency_semantics(inputs)
    return contract


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    return _validate_contract_with_inputs(contract, _capture_inputs(root))


def _validated_contract_and_inputs(
    root: Path,
) -> tuple[Mapping[str, Any], Mapping[Path, bytes]]:
    inputs = _capture_inputs(root)
    contract = _load_yaml(inputs, CONTRACT_PATH, "contract")
    return _validate_contract_with_inputs(contract, inputs), inputs


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    contract, _inputs = _validated_contract_and_inputs(root)
    return contract


def reference_plan(contract: Mapping[str, Any]) -> dict[str, Any]:
    verification = _mapping(contract["verification_boundary"], "verification")
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "integration_base_commit": INTEGRATION_BASE_COMMIT,
            "implementation_io": (
                "SELF_CONTAINED_DESCRIPTOR_CAPTURED_BOUNDED_INPUTS_AND_"
                "RECOVERABLE_PAIRED_OUTPUT_TRANSACTION"
            ),
        },
        "security_controls": {
            "formal_verification": "NOT_EXECUTED",
            "evidence": None,
            "controls": [
                {
                    **dict(row),
                    "formal_verification": "NOT_EXECUTED",
                    "evidence": None,
                }
                for row in EXPECTED_SECURITY_CONTROLS
            ],
        },
        "dependency_bindings": contract["dependencies"],
        "runtime_blockers": contract["runtime_blockers"],
        "open_decisions": contract["open_decisions"],
        "test_suites": [
            {
                **dict(row),
                "formal_execution": "NOT_EXECUTED",
                "evidence": None,
            }
            for row in EXPECTED_TEST_SUITES
        ],
        "category_candidate": contract["category_candidate"],
        "fixture_boundary": contract["fixture_boundary"],
        "identity_boundary": contract["identity_boundary"],
        "freshness_boundary": contract["freshness_boundary"],
        "human_review": contract["human_review"],
        "execution_boundary": contract["execution_boundary"],
        "verification_boundary": {
            "projection_only": True,
            "dependency_connections": "NOT_EXECUTED",
            **dict(verification),
        },
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(inputs: Mapping[Path, bytes], relative: Path) -> dict[str, object]:
    content = _input(inputs, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(inputs: Mapping[Path, bytes], reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST1702-CATEGORY-FIXTURES-RULES-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1702",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_input(inputs, CONTRACT_PATH, "contract")),
            "integration_base_commit": INTEGRATION_BASE_COMMIT,
            "authority_inputs": _source_rows(),
            "dependency_inputs": [
                {
                    "story_id": story_id,
                    "artifacts": _artifact_rows(artifacts),
                }
                for story_id, artifacts in DEPENDENCY_ARTIFACTS
            ],
            "implementation_io": (
                "SELF_CONTAINED_DESCRIPTOR_CAPTURED_BOUNDED_INPUTS_AND_"
                "RECOVERABLE_PAIRED_OUTPUT_TRANSACTION"
            ),
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(inputs, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "input_capture": "DESCRIPTOR_CAPTURED_SINGLE_PASS_SAME_BYTES",
            "repository_root_capture": "COMPONENT_DESCRIPTOR_WALK_O_NOFOLLOW",
            "input_size_limit_bytes": MAX_SOURCE_BYTES,
            "output_pair_transaction": "RECOVERABLE_ALL_OR_NOTHING",
            "transaction_inventory_binding": (
                "ORDERED_PATH_PARENT_IDENTITY_ORIGINAL_AND_STAGED"
            ),
            "commit_revalidation": "TARGET_NEXT_PARENT_AND_LOCK_IDENTITY",
            "recovery_parent_drift": "FAIL_CLOSED_STATE_RETAINED",
            "pending_check_behavior": "READ_ONLY_REFUSAL",
            "executable": False,
            "interface_only": True,
            "canonical_mutation_authority": "NONE",
            "od_001": "HUMAN_DECISION_REQUIRED",
            "od_006": "EXTERNAL_EVIDENCE_REQUIRED",
            "od_007": "HUMAN_DECISION_REQUIRED",
            "category_candidate_authority": (
                "NON_AUTHORITATIVE_OWNER_DECISION_CANDIDATE"
            ),
            "runtime_category_config": "NOT_CREATED",
            "golden_products": "NOT_CREATED",
            "automatic_merge_enabled": False,
            "automatic_split_enabled": False,
            "human_review_required": True,
            "domain_reviewer_approval": "NOT_OBTAINED",
            "freshness_policy_activation": "DISABLED_UNRESOLVED_OD_007",
            "category_override_applied": False,
            "provider_override_applied": False,
            "repository": "ABSENT",
            "database": "NOT_EXECUTED",
            "job": "NOT_EXECUTED",
            "event": "NOT_EXECUTED",
            "provider": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "story_acceptance": False,
            "st1702_ready": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract, inputs = _validated_contract_and_inputs(root)
    reference_bytes = _json_bytes(reference_plan(contract))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(inputs, reference_bytes),
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


@dataclass(frozen=True, slots=True)
class _TransactionOriginal:
    present: bool
    bytes_count: int | None
    sha256: str | None
    device: int | None
    inode: int | None
    mode: int | None
    mtime_ns: int | None
    owner: int | None


@dataclass(frozen=True, slots=True)
class _TransactionEntry:
    relative: Path
    parent_identity: tuple[int, int]
    staged_bytes: int
    staged_sha256: str
    staged_device: int | None
    staged_inode: int | None
    staged_mtime_ns: int | None
    staged_owner: int | None
    original: _TransactionOriginal


@dataclass(frozen=True, slots=True)
class _TransactionState:
    phase: str
    entries: tuple[_TransactionEntry, ...]


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
    root: Path
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
    except CategoryFixturesRulesReferenceError:
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
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=slot.parent_descriptor,
        )
        metadata = os.fstat(descriptor)
        if _stable_file_identity(metadata) != _stable_file_identity(path_metadata):
            _fail("OUTPUT_TARGET_CHANGED", field)
        if metadata.st_size > MAX_SOURCE_BYTES:
            _fail("OUTPUT_SIZE_LIMIT", field)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_SOURCE_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_SOURCE_BYTES:
                _fail("OUTPUT_SIZE_LIMIT", field)
        content = b"".join(chunks)
        if len(content) > MAX_SOURCE_BYTES:
            _fail("OUTPUT_SIZE_LIMIT", field)
        metadata_after = os.fstat(descriptor)
        final_metadata = os.stat(
            name,
            dir_fd=slot.parent_descriptor,
            follow_symlinks=False,
        )
        if (
            _stable_file_identity(metadata) != _stable_file_identity(metadata_after)
            or _stable_file_identity(metadata) != _stable_file_identity(final_metadata)
            or len(content) != metadata.st_size
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
    except CategoryFixturesRulesReferenceError:
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
    except CategoryFixturesRulesReferenceError:
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


def _transaction_original(snapshot: _FileSnapshot | None) -> _TransactionOriginal:
    if snapshot is None:
        return _TransactionOriginal(False, None, None, None, None, None, None, None)
    return _TransactionOriginal(
        present=True,
        bytes_count=len(snapshot.content),
        sha256=_sha256(snapshot.content),
        device=snapshot.device,
        inode=snapshot.inode,
        mode=snapshot.mode,
        mtime_ns=snapshot.mtime_ns,
        owner=snapshot.owner,
    )


def _transaction_entry(
    slot: _OutputSlot,
    staged_content: bytes,
    staged_snapshot: _FileSnapshot | None,
) -> _TransactionEntry:
    return _TransactionEntry(
        relative=slot.relative,
        parent_identity=slot.parent_identity,
        staged_bytes=len(staged_content),
        staged_sha256=_sha256(staged_content),
        staged_device=(staged_snapshot.device if staged_snapshot is not None else None),
        staged_inode=(staged_snapshot.inode if staged_snapshot is not None else None),
        staged_mtime_ns=(
            staged_snapshot.mtime_ns if staged_snapshot is not None else None
        ),
        staged_owner=(staged_snapshot.owner if staged_snapshot is not None else None),
        original=_transaction_original(slot.original),
    )


def _transaction_state_payload(state: _TransactionState) -> dict[str, object]:
    return {
        "schema": TRANSACTION_SCHEMA,
        "phase": state.phase,
        "outputs": [
            {
                "relative": entry.relative.as_posix(),
                "parent_device": entry.parent_identity[0],
                "parent_inode": entry.parent_identity[1],
                "staged_bytes": entry.staged_bytes,
                "staged_sha256": entry.staged_sha256,
                "staged_device": entry.staged_device,
                "staged_inode": entry.staged_inode,
                "staged_mtime_ns": entry.staged_mtime_ns,
                "staged_owner": entry.staged_owner,
                "original": {
                    "present": entry.original.present,
                    "bytes": entry.original.bytes_count,
                    "sha256": entry.original.sha256,
                    "device": entry.original.device,
                    "inode": entry.original.inode,
                    "mode": entry.original.mode,
                    "mtime_ns": entry.original.mtime_ns,
                    "owner": entry.original.owner,
                },
            }
            for entry in state.entries
        ],
    }


def _transaction_state_bytes(state: _TransactionState) -> bytes:
    return _json_bytes(_transaction_state_payload(state))


def _state_int(value: object) -> int:
    if type(value) is not int or value < 0:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    return value


def _state_optional_int(value: object) -> int | None:
    if value is None:
        return None
    return _state_int(value)


def _state_sha256(value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or value != value.lower()
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    return value


def _parse_transaction_original(value: object) -> _TransactionOriginal:
    original = _mapping(value, "transaction_state")
    if tuple(original) != (
        "present",
        "bytes",
        "sha256",
        "device",
        "inode",
        "mode",
        "mtime_ns",
        "owner",
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    present = original["present"]
    if type(present) is not bool:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    if not present:
        if any(original[key] is not None for key in tuple(original)[1:]):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        return _TransactionOriginal(False, None, None, None, None, None, None, None)
    bytes_count = _state_int(original["bytes"])
    sha256 = _state_sha256(original["sha256"])
    device = _state_int(original["device"])
    inode = _state_int(original["inode"])
    mode = _state_int(original["mode"])
    mtime_ns = _state_int(original["mtime_ns"])
    owner = _state_int(original["owner"])
    if (
        bytes_count > MAX_SOURCE_BYTES
        or device == 0
        or inode == 0
        or owner != os.geteuid()
        or mode > 0o7777
        or mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX | 0o022)
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    return _TransactionOriginal(
        True,
        bytes_count,
        sha256,
        device,
        inode,
        mode,
        mtime_ns,
        owner,
    )


def _parse_transaction_state(content: bytes) -> _TransactionState:
    try:
        raw = _parse_json(content, "transaction_state")
        if tuple(raw) != ("schema", "phase", "outputs"):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        if raw["schema"] != TRANSACTION_SCHEMA:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        phase = raw["phase"]
        if type(phase) is not str or phase not in {ROLLBACK_PHASE, COMMIT_PHASE}:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        outputs = _list(raw["outputs"], "transaction_state")
        if len(outputs) != len(GENERATED_PATHS):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        entries: list[_TransactionEntry] = []
        for expected_relative, raw_entry in zip(
            GENERATED_PATHS,
            outputs,
            strict=True,
        ):
            entry = _mapping(raw_entry, "transaction_state")
            if tuple(entry) != (
                "relative",
                "parent_device",
                "parent_inode",
                "staged_bytes",
                "staged_sha256",
                "staged_device",
                "staged_inode",
                "staged_mtime_ns",
                "staged_owner",
                "original",
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            if entry["relative"] != expected_relative.as_posix():
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            staged_identity = (
                _state_optional_int(entry["staged_device"]),
                _state_optional_int(entry["staged_inode"]),
                _state_optional_int(entry["staged_mtime_ns"]),
                _state_optional_int(entry["staged_owner"]),
            )
            if phase == ROLLBACK_PHASE and any(
                value is not None for value in staged_identity
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            if phase == COMMIT_PHASE and any(
                value is None for value in staged_identity
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            parent_device = _state_int(entry["parent_device"])
            parent_inode = _state_int(entry["parent_inode"])
            staged_bytes = _state_int(entry["staged_bytes"])
            if (
                parent_device == 0
                or parent_inode == 0
                or staged_bytes > MAX_SOURCE_BYTES
                or (
                    phase == COMMIT_PHASE
                    and (
                        staged_identity[0] == 0
                        or staged_identity[1] == 0
                        or staged_identity[3] != os.geteuid()
                    )
                )
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            entries.append(
                _TransactionEntry(
                    relative=expected_relative,
                    parent_identity=(parent_device, parent_inode),
                    staged_bytes=staged_bytes,
                    staged_sha256=_state_sha256(entry["staged_sha256"]),
                    staged_device=staged_identity[0],
                    staged_inode=staged_identity[1],
                    staged_mtime_ns=staged_identity[2],
                    staged_owner=staged_identity[3],
                    original=_parse_transaction_original(entry["original"]),
                )
            )
        state = _TransactionState(phase=phase, entries=tuple(entries))
        if content != _transaction_state_bytes(state):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        return state
    except CategoryFixturesRulesReferenceError as error:
        if error.code == "OUTPUT_RECOVERY_REQUIRED":
            raise
        raise CategoryFixturesRulesReferenceError(
            "OUTPUT_RECOVERY_REQUIRED", "transaction_state"
        ) from None


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


def _transaction_state_at(
    slots: Sequence[_OutputSlot], name: str, *, missing_ok: bool
) -> tuple[_FileSnapshot, _TransactionState] | None:
    snapshot = _state_snapshot(slots, name, missing_ok=missing_ok)
    if snapshot is None:
        return None
    return snapshot, _parse_transaction_state(snapshot.content)


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


def _entry_by_relative(
    state: _TransactionState,
    relative: Path,
) -> _TransactionEntry:
    matches = [entry for entry in state.entries if entry.relative == relative]
    if len(matches) != 1:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    return matches[0]


def _snapshot_matches_original(
    snapshot: _FileSnapshot | None,
    original: _TransactionOriginal,
) -> bool:
    if not original.present:
        return snapshot is None
    if snapshot is None:
        return False
    return (
        len(snapshot.content),
        _sha256(snapshot.content),
        snapshot.device,
        snapshot.inode,
        snapshot.mode,
        snapshot.mtime_ns,
        snapshot.owner,
    ) == (
        original.bytes_count,
        original.sha256,
        original.device,
        original.inode,
        original.mode,
        original.mtime_ns,
        original.owner,
    )


def _snapshot_matches_staged(
    snapshot: _FileSnapshot | None,
    entry: _TransactionEntry,
    *,
    expected_snapshot: _FileSnapshot | None = None,
    require_recorded_identity: bool = False,
) -> bool:
    if snapshot is None:
        return False
    if (
        len(snapshot.content) != entry.staged_bytes
        or _sha256(snapshot.content) != entry.staged_sha256
        or snapshot.mode != OUTPUT_MODE
        or snapshot.owner != os.geteuid()
    ):
        return False
    if expected_snapshot is not None and not _same_original(
        snapshot,
        expected_snapshot,
    ):
        return False
    recorded_identity = (
        entry.staged_device,
        entry.staged_inode,
        entry.staged_mtime_ns,
        entry.staged_owner,
    )
    if require_recorded_identity:
        if any(value is None for value in recorded_identity):
            return False
        return (
            snapshot.device,
            snapshot.inode,
            snapshot.mtime_ns,
            snapshot.owner,
        ) == recorded_identity
    return True


def _validate_transaction_inventory(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    if (
        tuple(slot.relative for slot in slots) != GENERATED_PATHS
        or tuple(entry.relative for entry in state.entries) != GENERATED_PATHS
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    for slot, entry in zip(slots, state.entries, strict=True):
        if slot.parent_identity != entry.parent_identity:
            _fail("OUTPUT_ANCESTOR_CHANGED", "output")
        _assert_parent_identity(root, slot)


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
        return _WriterLock(root=root, slot=slot)
    except CategoryFixturesRulesReferenceError:
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
        _assert_parent_identity(lock.root, lock.slot)
        metadata = os.fstat(lock.slot.parent_descriptor)
        if (metadata.st_dev, metadata.st_ino) != lock.slot.parent_identity:
            _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")
    except CategoryFixturesRulesReferenceError, OSError:
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


def _preflight_slots(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    if state.phase != ROLLBACK_PHASE:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _validate_transaction_inventory(root, slots, state)
    observed_state = _transaction_state_at(
        slots,
        TRANSACTION_STATE_NAME,
        missing_ok=False,
    )
    if observed_state is None or observed_state[1] != state:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _assert_absent(_state_slot(slots), TRANSACTION_STATE_NEXT_NAME, "transaction_state")
    for slot, entry in zip(slots, state.entries, strict=True):
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")
        observed_target = _target_snapshot(slot, missing_ok=True)
        if not _snapshot_matches_original(observed_target, entry.original):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        if not _snapshot_matches_original(slot.original, entry.original):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        observed_next = _next_snapshot(slot, missing_ok=False)
        if not _snapshot_matches_staged(
            observed_next,
            entry,
            expected_snapshot=slot.staged,
        ):
            _fail("OUTPUT_COMPANION_DRIFT", "output_companion")


def _revalidate_slots(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    _validate_transaction_inventory(root, slots, state)
    for slot, entry in zip(slots, state.entries, strict=True):
        observed_target = _target_snapshot(slot, missing_ok=True)
        if not _snapshot_matches_original(observed_target, entry.original):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        observed_next = _next_snapshot(slot, missing_ok=False)
        if not _snapshot_matches_staged(
            observed_next,
            entry,
            expected_snapshot=slot.staged,
        ):
            _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")


def _stage_outputs(
    root: Path,
    outputs: Mapping[Path, bytes],
    coordinator_parent_identity: tuple[int, int],
) -> tuple[list[_OutputSlot], _TransactionState]:
    if tuple(outputs) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    slots = _open_slots(root, create=True)
    state_created = False
    state: _TransactionState | None = None
    try:
        if tuple(slot.relative for slot in slots) != GENERATED_PATHS:
            _fail("OUTPUT_PARENT_UNAVAILABLE", "output")
        coordinator = _state_slot(slots)
        if coordinator.parent_identity != coordinator_parent_identity:
            _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")
        _assert_absent(coordinator, TRANSACTION_STATE_NAME, "transaction_state")
        _assert_absent(coordinator, TRANSACTION_STATE_NEXT_NAME, "transaction_state")
        for slot in slots:
            _assert_parent_identity(root, slot)
            _assert_absent(slot, slot.next_name, "output_companion")
            _assert_absent(slot, slot.previous_name, "output_companion")
            _assert_absent(slot, slot.absent_name, "output_companion")
            slot.original = _target_snapshot(slot, missing_ok=True)
        state = _TransactionState(
            phase=ROLLBACK_PHASE,
            entries=tuple(
                _transaction_entry(slot, outputs[slot.relative], None) for slot in slots
            ),
        )
        _write_rollback_state(slots, state)
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
        _preflight_slots(root, slots, state)
        return slots, state
    except (CategoryFixturesRulesReferenceError, OSError) as stage_error:
        if state_created and state is not None:
            try:
                _recover_rollback(root, slots, state)
            except (CategoryFixturesRulesReferenceError, OSError) as recovery_error:
                _best_effort_restore_uncontested_slots(slots, state)
                raise CategoryFixturesRulesReferenceError(
                    "OUTPUT_ROLLBACK_REQUIRED", "output"
                ) from recovery_error
        _close_slots(slots)
        raise stage_error
    except BaseException:
        # A crash intentionally leaves fixed companions for next-run recovery.
        _close_slots(slots)
        raise


def _write_rollback_state(
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    if state.phase != ROLLBACK_PHASE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    coordinator = _state_slot(slots)
    _write_companion(
        coordinator,
        TRANSACTION_STATE_NAME,
        _transaction_state_bytes(state),
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
    except CategoryFixturesRulesReferenceError:
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
    if (
        next_snapshot is None
        or slot.staged is None
        or not _same_original(next_snapshot, slot.staged)
        or (previous is None) == (absent is None)
    ):
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
        or slot.staged is None
        or not _same_original(target, slot.staged)
        or not _same_original(linked_next, slot.staged)
        or target.mode != OUTPUT_MODE
        or target.links != 2
        or linked_next.links != 2
    ):
        _fail("OUTPUT_PUBLISH_DRIFT", "output")
    _transaction_checkpoint(f"PUBLISHED_{slot.relative.as_posix()}")


def _validate_published_slots(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
    *,
    require_recorded_identity: bool,
) -> None:
    _validate_transaction_inventory(root, slots, state)
    for slot, entry in zip(slots, state.entries, strict=True):
        next_snapshot = _next_snapshot(slot, missing_ok=False)
        target = _target_snapshot(slot, missing_ok=False, linked_ok=True)
        previous = _previous_snapshot(slot, missing_ok=True)
        absent = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
        if (
            target is None
            or next_snapshot is None
            or not _same_file(target, next_snapshot)
            or not _snapshot_matches_staged(
                target,
                entry,
                expected_snapshot=slot.staged,
                require_recorded_identity=require_recorded_identity,
            )
            or not _snapshot_matches_staged(
                next_snapshot,
                entry,
                expected_snapshot=slot.staged,
                require_recorded_identity=require_recorded_identity,
            )
            or target.links != 2
            or next_snapshot.links != 2
        ):
            _fail("OUTPUT_PUBLISH_DRIFT", "output")
        if entry.original.present:
            if absent is not None or not _snapshot_matches_original(
                previous,
                entry.original,
            ):
                _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
        elif previous is not None or absent is None:
            _fail("OUTPUT_COMPANION_DRIFT", "output_companion")


def _commit_state(
    slots: Sequence[_OutputSlot],
    rollback_state: _TransactionState,
) -> _TransactionState:
    entries: list[_TransactionEntry] = []
    for slot, entry in zip(slots, rollback_state.entries, strict=True):
        staged = slot.staged
        if staged is None or not _snapshot_matches_staged(
            staged,
            entry,
            expected_snapshot=staged,
        ):
            _fail("OUTPUT_COMPANION_DRIFT", "output_companion")
        entries.append(
            _TransactionEntry(
                relative=entry.relative,
                parent_identity=entry.parent_identity,
                staged_bytes=entry.staged_bytes,
                staged_sha256=entry.staged_sha256,
                staged_device=staged.device,
                staged_inode=staged.inode,
                staged_mtime_ns=staged.mtime_ns,
                staged_owner=staged.owner,
                original=entry.original,
            )
        )
    return _TransactionState(phase=COMMIT_PHASE, entries=tuple(entries))


def _mark_commit(
    root: Path,
    slots: Sequence[_OutputSlot],
    rollback_state: _TransactionState,
) -> _TransactionState:
    if rollback_state.phase != ROLLBACK_PHASE:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _validate_published_slots(
        root,
        slots,
        rollback_state,
        require_recorded_identity=False,
    )
    coordinator = _state_slot(slots)
    rollback = _transaction_state_at(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if rollback is None or rollback[1] != rollback_state:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _assert_absent(coordinator, TRANSACTION_STATE_NEXT_NAME, "transaction_state")
    commit_state = _commit_state(slots, rollback_state)
    _write_companion(
        coordinator,
        TRANSACTION_STATE_NEXT_NAME,
        _transaction_state_bytes(commit_state),
        mode=PRIVATE_COMPANION_MODE,
        field="transaction_state",
    )
    _validate_published_slots(
        root,
        slots,
        commit_state,
        require_recorded_identity=True,
    )
    state_next = _transaction_state_at(
        slots,
        TRANSACTION_STATE_NEXT_NAME,
        missing_ok=False,
    )
    if state_next is None or state_next[1] != commit_state:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
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
    committed = _transaction_state_at(slots, TRANSACTION_STATE_NAME, missing_ok=False)
    if committed is None or committed[1] != commit_state:
        _fail("OUTPUT_COMPANION_DRIFT", "transaction_state")
    _validate_published_slots(
        root,
        slots,
        commit_state,
        require_recorded_identity=True,
    )
    _transaction_checkpoint("COMMIT_MARKED")
    return commit_state


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


def _same_transaction(
    rollback_state: _TransactionState,
    commit_state: _TransactionState,
) -> bool:
    if (
        rollback_state.phase != ROLLBACK_PHASE
        or commit_state.phase != COMMIT_PHASE
        or len(rollback_state.entries) != len(commit_state.entries)
    ):
        return False
    for rollback_entry, commit_entry in zip(
        rollback_state.entries,
        commit_state.entries,
        strict=True,
    ):
        if (
            rollback_entry.relative,
            rollback_entry.parent_identity,
            rollback_entry.staged_bytes,
            rollback_entry.staged_sha256,
            rollback_entry.original,
        ) != (
            commit_entry.relative,
            commit_entry.parent_identity,
            commit_entry.staged_bytes,
            commit_entry.staged_sha256,
            commit_entry.original,
        ) or any(
            value is None
            for value in (
                commit_entry.staged_device,
                commit_entry.staged_inode,
                commit_entry.staged_mtime_ns,
                commit_entry.staged_owner,
            )
        ):
            return False
    return True


def _validate_rolled_back_targets(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    _validate_transaction_inventory(root, slots, state)
    for slot, entry in zip(slots, state.entries, strict=True):
        if not _snapshot_matches_original(
            _target_snapshot(slot, missing_ok=True),
            entry.original,
        ):
            _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
        _assert_absent(slot, slot.next_name, "output_companion")
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")


def _validate_committed_targets(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    _validate_transaction_inventory(root, slots, state)
    for slot, entry in zip(slots, state.entries, strict=True):
        target = _target_snapshot(slot, missing_ok=False)
        if (
            target is None
            or target.links != 1
            or not _snapshot_matches_staged(
                target,
                entry,
                require_recorded_identity=True,
            )
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        _assert_absent(slot, slot.next_name, "output_companion")
        _assert_absent(slot, slot.previous_name, "output_companion")
        _assert_absent(slot, slot.absent_name, "output_companion")


def _recover_rollback(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    if state.phase != ROLLBACK_PHASE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    _validate_transaction_inventory(root, slots, state)
    observed_state = _transaction_state_at(
        slots,
        TRANSACTION_STATE_NAME,
        missing_ok=False,
    )
    if observed_state is None or observed_state[1] != state:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    state_next = _transaction_state_at(
        slots,
        TRANSACTION_STATE_NEXT_NAME,
        missing_ok=True,
    )
    if state_next is not None and not _same_transaction(
        state,
        state_next[1],
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    companions = _inspect_recovery_companions(slots)
    observations: dict[Path, _FileSnapshot | None] = {}
    for slot, entry in zip(slots, state.entries, strict=True):
        next_snapshot, previous, absent = companions[slot.relative]
        target = _target_snapshot(slot, missing_ok=True, linked_ok=True)
        observations[slot.relative] = target
        if entry.original.present:
            if absent is not None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
            if previous is None:
                if not _snapshot_matches_original(target, entry.original):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
            else:
                if not _snapshot_matches_original(previous, entry.original):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
                if target is not None and (
                    next_snapshot is None or not _same_file(target, next_snapshot)
                ):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        else:
            if previous is not None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
            if absent is None:
                if target is not None:
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
            elif target is not None and (
                next_snapshot is None or not _same_file(target, next_snapshot)
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
    try:
        for slot, entry in reversed(tuple(zip(slots, state.entries, strict=True))):
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
                if not _snapshot_matches_original(restored, entry.original):
                    _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
                _transaction_checkpoint(f"RESTORED_{slot.relative.as_posix()}")
            elif absent is not None and target is not None:
                if next_snapshot is None or not _same_file(target, next_snapshot):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
                os.unlink(slot.target_name, dir_fd=slot.parent_descriptor)
                _fsync_slot(slot)
                _transaction_checkpoint(f"RESTORED_{slot.relative.as_posix()}")
        for slot, entry in zip(slots, state.entries, strict=True):
            observed = _target_snapshot(slot, missing_ok=True)
            if not _snapshot_matches_original(observed, entry.original):
                _fail("OUTPUT_ROLLBACK_REQUIRED", "generated_output")
        _validate_transaction_inventory(root, slots, state)
        for slot in slots:
            marker = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
            if marker is not None:
                _unlink_snapshot(slot, slot.absent_name, marker)
        if state_next is not None:
            _unlink_snapshot(
                _state_slot(slots),
                TRANSACTION_STATE_NEXT_NAME,
                state_next[0],
            )
        for slot in slots:
            staged = _next_snapshot(slot, missing_ok=True)
            if staged is not None:
                _unlink_snapshot(slot, slot.next_name, staged)
        _validate_rolled_back_targets(root, slots, state)
        current_state = _transaction_state_at(
            slots,
            TRANSACTION_STATE_NAME,
            missing_ok=False,
        )
        if current_state is None or current_state[1] != state:
            _fail("OUTPUT_ROLLBACK_REQUIRED", "transaction_state")
        _unlink_snapshot(
            _state_slot(slots),
            TRANSACTION_STATE_NAME,
            current_state[0],
        )
    except CategoryFixturesRulesReferenceError:
        raise
    except OSError:
        _fail("OUTPUT_ROLLBACK_REQUIRED", "output")


def _recover_commit(
    root: Path,
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    if state.phase != COMMIT_PHASE:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    _validate_transaction_inventory(root, slots, state)
    observed_state = _transaction_state_at(
        slots,
        TRANSACTION_STATE_NAME,
        missing_ok=False,
    )
    if observed_state is None or observed_state[1] != state:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    if (
        _transaction_state_at(
            slots,
            TRANSACTION_STATE_NEXT_NAME,
            missing_ok=True,
        )
        is not None
    ):
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    companions = _inspect_recovery_companions(slots)
    for slot, entry in zip(slots, state.entries, strict=True):
        next_snapshot, previous, absent = companions[slot.relative]
        target = _target_snapshot(slot, missing_ok=False, linked_ok=True)
        if target is None or not _snapshot_matches_staged(
            target,
            entry,
            require_recorded_identity=True,
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        if next_snapshot is None:
            if target.links != 1:
                _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        elif (
            not _same_file(target, next_snapshot)
            or not _snapshot_matches_staged(
                next_snapshot,
                entry,
                require_recorded_identity=True,
            )
            or target.links != 2
            or next_snapshot.links != 2
        ):
            _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        if entry.original.present:
            if absent is not None or (
                previous is not None
                and not _snapshot_matches_original(previous, entry.original)
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
        elif previous is not None:
            _fail("OUTPUT_RECOVERY_REQUIRED", "output_companion")
    try:
        for slot, entry in zip(slots, state.entries, strict=True):
            _next, previous, absent = companions[slot.relative]
            if previous is not None:
                _unlink_snapshot(slot, slot.previous_name, previous)
            if absent is not None:
                _unlink_snapshot(slot, slot.absent_name, absent)
            staged = _next_snapshot(slot, missing_ok=True)
            if staged is not None:
                target = _target_snapshot(slot, missing_ok=False, linked_ok=True)
                if (
                    target is None
                    or not _same_file(target, staged)
                    or not _snapshot_matches_staged(
                        target,
                        entry,
                        require_recorded_identity=True,
                    )
                    or not _snapshot_matches_staged(
                        staged,
                        entry,
                        require_recorded_identity=True,
                    )
                ):
                    _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
                _unlink_snapshot(slot, slot.next_name, staged)
            target = _target_snapshot(slot, missing_ok=False)
            if (
                not _snapshot_matches_staged(
                    target,
                    entry,
                    require_recorded_identity=True,
                )
                or target is None
                or target.links != 1
            ):
                _fail("OUTPUT_RECOVERY_REQUIRED", "generated_output")
        _validate_committed_targets(root, slots, state)
        current_state = _transaction_state_at(
            slots,
            TRANSACTION_STATE_NAME,
            missing_ok=False,
        )
        if current_state is None or current_state[1] != state:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        _unlink_snapshot(
            _state_slot(slots),
            TRANSACTION_STATE_NAME,
            current_state[0],
        )
    except CategoryFixturesRulesReferenceError:
        raise
    except OSError:
        _fail("OUTPUT_RECOVERY_REQUIRED", "output")


def _best_effort_restore_uncontested_slots(
    slots: Sequence[_OutputSlot],
    state: _TransactionState,
) -> None:
    """Restore only slots whose current target still matches transaction state."""

    for slot, entry in reversed(tuple(zip(slots, state.entries, strict=True))):
        try:
            if slot.parent_identity != entry.parent_identity:
                continue
            previous = _previous_snapshot(slot, missing_ok=True)
            absent = _marker_snapshot(slot, slot.absent_name, missing_ok=True)
            next_snapshot = _next_snapshot(slot, missing_ok=True)
            target = _target_snapshot(slot, missing_ok=True, linked_ok=True)
            if previous is not None and _snapshot_matches_original(
                previous,
                entry.original,
            ):
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
            elif (
                not entry.original.present and absent is not None and target is not None
            ):
                if next_snapshot is None or not _same_file(target, next_snapshot):
                    continue
                os.unlink(slot.target_name, dir_fd=slot.parent_descriptor)
                _fsync_slot(slot)
            observed = _target_snapshot(slot, missing_ok=True)
            if not _snapshot_matches_original(observed, entry.original):
                continue
        except CategoryFixturesRulesReferenceError, OSError:
            # The coordinator remains and the caller reports rollback-required.
            continue


def _recover_pending_transaction(
    root: Path,
    *,
    mutate: bool,
    coordinator_parent_identity: tuple[int, int] | None = None,
) -> None:
    slots = _open_slots(root, create=False)
    try:
        if not slots:
            return
        state_slot_matches = [slot for slot in slots if slot.relative == MANIFEST_PATH]
        if coordinator_parent_identity is not None and (
            len(state_slot_matches) != 1
            or state_slot_matches[0].parent_identity != coordinator_parent_identity
        ):
            _fail("OUTPUT_LOCK_RECOVERY_REQUIRED", "writer_lock")
        state_pair = (
            _transaction_state_at(slots, TRANSACTION_STATE_NAME, missing_ok=True)
            if len(state_slot_matches) == 1
            else None
        )
        state_next_pair = (
            _transaction_state_at(
                slots,
                TRANSACTION_STATE_NEXT_NAME,
                missing_ok=True,
            )
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
        if state_pair is None and state_next_pair is None and not has_output_companion:
            return
        if not mutate:
            _fail("OUTPUT_RECOVERY_REQUIRED", "output")
        if state_pair is None:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        if tuple(slot.relative for slot in slots) != GENERATED_PATHS:
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
        state = state_pair[1]
        _validate_transaction_inventory(root, slots, state)
        if state.phase == ROLLBACK_PHASE:
            _recover_rollback(root, slots, state)
            return
        if state.phase == COMMIT_PHASE:
            if state_next_pair is not None:
                _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
            _recover_commit(root, slots, state)
            return
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction_state")
    finally:
        _close_slots(slots)


def _write_output_transaction(
    root: Path,
    outputs: Mapping[Path, bytes],
    coordinator_parent_identity: tuple[int, int],
) -> None:
    slots: list[_OutputSlot] = []
    rollback_state: _TransactionState | None = None
    commit_state: _TransactionState | None = None
    state_started = False
    commit_marked = False
    try:
        slots, rollback_state = _stage_outputs(
            root,
            outputs,
            coordinator_parent_identity,
        )
        state_started = True
        _before_transaction_commit(slots)
        _revalidate_slots(root, slots, rollback_state)
        for slot in slots:
            _backup_output(root, slot)
        for slot in slots:
            _publish_output(root, slot)
        commit_state = _mark_commit(root, slots, rollback_state)
        commit_marked = True
        _recover_commit(root, slots, commit_state)
    except (CategoryFixturesRulesReferenceError, OSError) as error:
        if state_started and not commit_marked:
            try:
                observed_state = _transaction_state_at(
                    slots, TRANSACTION_STATE_NAME, missing_ok=True
                )
                commit_marked = (
                    observed_state is not None
                    and observed_state[1].phase == COMMIT_PHASE
                )
                if commit_marked and observed_state is not None:
                    commit_state = observed_state[1]
            except CategoryFixturesRulesReferenceError, OSError:
                commit_marked = False
        if commit_marked:
            if isinstance(
                error, CategoryFixturesRulesReferenceError
            ) and error.code == ("OUTPUT_RECOVERY_REQUIRED"):
                raise
            _fail("OUTPUT_RECOVERY_REQUIRED", "output")
        if state_started and rollback_state is not None:
            try:
                _recover_rollback(root, slots, rollback_state)
            except (CategoryFixturesRulesReferenceError, OSError) as rollback_error:
                _best_effort_restore_uncontested_slots(slots, rollback_state)
                raise CategoryFixturesRulesReferenceError(
                    "OUTPUT_ROLLBACK_REQUIRED", "output"
                ) from rollback_error
        else:
            # No owned companion is created before the rollback coordinator.
            pass
        if isinstance(error, CategoryFixturesRulesReferenceError):
            raise error
        _fail("OUTPUT_TRANSACTION_FAILED", "output")
    finally:
        _close_slots(slots)


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    if check:
        check_lock = _acquire_check_lock(root)
        try:
            _assert_parent_identity(root, check_lock.slot)
            _recover_pending_transaction(
                root,
                mutate=False,
                coordinator_parent_identity=check_lock.slot.parent_identity,
            )
            outputs = render_outputs(root)
            _assert_parent_identity(root, check_lock.slot)
            check_outputs(root, outputs)
            _assert_parent_identity(root, check_lock.slot)
        finally:
            _release_writer_lock(check_lock)
        return
    writer_lock = _acquire_writer_lock(root)
    try:
        _assert_parent_identity(root, writer_lock.slot)
        _recover_pending_transaction(
            root,
            mutate=True,
            coordinator_parent_identity=writer_lock.slot.parent_identity,
        )
        outputs = render_outputs(root)
        _assert_parent_identity(root, writer_lock.slot)
        _write_output_transaction(
            root,
            outputs,
            writer_lock.slot.parent_identity,
        )
        _assert_parent_identity(root, writer_lock.slot)
    finally:
        _release_writer_lock(writer_lock)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except CategoryFixturesRulesReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1702 category fixtures/rules reference plan checked"
        if args.check
        else "ST-1702 category fixtures/rules reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
