#!/usr/bin/env python3
"""Build the deterministic, blocked-only ST-1801 local portfolio plan."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Any, Final, NoReturn

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


if __name__ == "__main__":
    if sys.flags.isolated != 1:
        print(
            "ST1801_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python", file=sys.stderr
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1801_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1801/contracts/portfolio-expansion-plan.v1.yaml"
)
FIXTURE_SCHEMA_PATH: Final = Path(
    "changes/st-1801/contracts/recorded-synthetic-quality-evaluation.v1.schema.json"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1801/fixtures/recorded-synthetic-quality-evaluation.v1.json"
)
PACK_PATH: Final = Path(
    "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1801/generated/runtime-manifest.v1.yaml")
GENERATED_PATHS: Final = (PACK_PATH, MANIFEST_PATH)
README_PATH: Final = Path("changes/st-1801/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1801/PREFLIGHT.md")
GENERATOR_PATH: Final = Path("scripts/build_st1801_portfolio_expansion.py")
TEST_PATHS: Final = (
    Path("tests/st1801/conftest.py"),
    Path("tests/st1801/test_contract.py"),
    Path("tests/st1801/test_evaluation.py"),
    Path("tests/st1801/test_generation.py"),
    Path("tests/st1801/test_negative_cases.py"),
    Path("tests/st1801/test_plan.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_SCHEMA_PATH,
    FIXTURE_PATH,
    README_PATH,
    PREFLIGHT_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)

MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 64 * 1024
OUTPUT_MODE: Final = 0o644
PRIVATE_MODE: Final = 0o600
TRANSACTION_NAME: Final = ".st1801-portfolio.transaction.json"
TRANSACTION_NEXT_NAME: Final = f"{TRANSACTION_NAME}.next"
TRANSACTION_SCHEMA: Final = "ST1801_OUTPUT_TRANSACTION_V1"
STAGE_SUFFIX: Final = ".st1801.next"
PREVIOUS_SUFFIX: Final = ".st1801.previous"
ABSENT_SUFFIX: Final = ".st1801.absent"
ABSENT_MARKER: Final = b"ST1801_OUTPUT_WAS_ABSENT_V1\n"
GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B "
    "scripts/build_st1801_portfolio_expansion.py"
)

PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
CATEGORY_REF: Final = "SYNTHETIC_CATEGORY_PLACEHOLDER_OD001_UNRESOLVED"
SLOT_PREFIX: Final = "synthetic-st1801-slot-"
SLOT_COUNT: Final = 30
QUALITY_THRESHOLD: Final = Decimal("85")
QUALITY_MINIMUM: Final = Decimal("0")
QUALITY_MAXIMUM: Final = Decimal("100")
SCORE_PATTERN: Final = re.compile(r"^(0|[1-9][0-9]?|100)(\.[0-9]{1,6})?$")

EXPECTED_SOURCE_HASHES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
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
    "contracts/raos-v0.4/contracts/content/RAOS_06_quality_gate_catalog_v0.1.yaml": (
        "90ab554aa55dda335ba69bbb306772306494e2e4ba899c3d22af4a9d9a030efb"
    ),
    "contracts/raos-v0.4/contracts/content/RAOS_06_claim_evidence_policy_v0.1.yaml": (
        "fbf2d0ad6e7821a0059f9ceeb53d57268031e2e42b4aad988af9a42378aec5ba"
    ),
    "changes/st-0605/contracts/claim-evidence-runtime.v1.yaml": (
        "7d84f3a4883a226eff782e976aa72169646be67bf1fc798af5b1b65367d2c3cb"
    ),
}

EXPECTED_DEPENDENCY_HASHES: Final = {
    "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json": (
        "012f5f1eb930105c7d1bbc19500d6133afd60a717dc453aec4993ff9137bb5d4"
    ),
    "changes/st-1705/manifest.yaml": (
        "5efaba638a756839bbd2067e54e2504bbf285bc3e93b2f1c49c89e26db29df30"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json": (
        "cc9c0057a1f42546988596ad02891d638471370997eadf50d55bbe61fe884c88"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json": (
        "53db8c8277da9dbd3b5b98a107327845307f58a9e3b767042ea9e64757f0e163"
    ),
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json": (
        "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8"
    ),
}

FIXTURE_SCHEMA_SHA256: Final = (
    "65ad1ecd3acd4995f5f591620cd29449c4aafb271083a29096fdd5e327387bd8"
)
FIXTURE_SHA256: Final = (
    "d48628804b66007258daeca4a31ff416f87f190cddcdd23c8b35b1de58fbde46"
)
ARTICLE_IDS: Final = (
    "st1703-first-suitcase-comparison",
    "st1704-portable-power-station-guide",
    "st1704-anker-solix-c300-c800-c1000-differences",
    "st1704-countertop-dishwasher-for-small-households",
    "st1704-compact-robot-vacuum-shortlist",
)


class PortfolioExpansionError(RuntimeError):
    """Sanitized, fail-closed ST-1801 validation error."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"ST1801_ERROR code={code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate keys."""


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
    raise PortfolioExpansionError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or any(type(key) is not str for key in value):
        _fail("INVALID_MAPPING", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("INVALID_LIST", field)
    return value


def _closed(value: object, keys: tuple[str, ...], field: str) -> Mapping[str, Any]:
    result = _mapping(value, field)
    if tuple(result) != keys:
        _fail("CLOSED_SCHEMA_DRIFT", field)
    return result


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
            expected
            in {
                "BLOCKED",
                "NOT_ELIGIBLE",
                "UNAVAILABLE",
                "NOT_EXECUTED",
                "NONE",
            }
            or type(expected) is bool
        ):
            _fail("SAFE_BOUNDARY_DRIFT", field)
        _fail("FIXED_VALUE_DRIFT", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


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
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
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
        return descriptors.pop()
    finally:
        while descriptors:
            _close(descriptors.pop())


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
                descriptor, min(READ_CHUNK_BYTES, MAX_INPUT_BYTES + 1 - total)
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
    except PortfolioExpansionError:
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
    except PortfolioExpansionError:
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
    except PortfolioExpansionError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


def _hash_rows(paths: Mapping[str, str], *, kind: str) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path}", "sha256": digest, "classification": kind}
        for path, digest in paths.items()
    ]


def _expected_contract_sections() -> dict[str, object]:
    return {
        "document": {
            "id": "RAOS-ST1801-PORTFOLIO-EXPANSION-001",
            "version": "1.0.0",
            "story_id": "ST-1801",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "classification": "LOCAL_BLOCKED_SYNTHETIC_PORTFOLIO_PLAN_NON_ATTESTING",
            "acceptance_criteria_satisfied": False,
            "formal_verification": "NOT_EXECUTED",
        },
        "source_bindings": [
            {"uri": f"repo://{path}", "sha256": digest}
            for path, digest in EXPECTED_SOURCE_HASHES.items()
        ],
        "dependency_bindings": {
            "st_1705": {
                "story_id": "ST-1705",
                "role": "BLOCKED_PILOT_SIGNOFF_PREDECESSOR",
                "artifacts": [
                    {
                        "kind": "GENERATED_BLOCKED_SIGNOFF",
                        "uri": "repo://changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json",
                        "sha256": EXPECTED_DEPENDENCY_HASHES[
                            "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json"
                        ],
                    },
                    {
                        "kind": "MANIFEST",
                        "uri": "repo://changes/st-1705/manifest.yaml",
                        "sha256": EXPECTED_DEPENDENCY_HASHES[
                            "changes/st-1705/manifest.yaml"
                        ],
                    },
                ],
            },
            "st_1704": {
                "story_id": "ST-1704",
                "role": "FIVE_ARTICLE_LOCAL_NON_ATTESTING_INPUT",
                "artifacts": [
                    {
                        "kind": "ARTICLE_COLLECTION",
                        "uri": "repo://changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
                        "sha256": EXPECTED_DEPENDENCY_HASHES[
                            "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
                        ],
                    },
                    {
                        "kind": "PUBLICATION_PLAN",
                        "uri": "repo://changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json",
                        "sha256": EXPECTED_DEPENDENCY_HASHES[
                            "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json"
                        ],
                    },
                    {
                        "kind": "MEASUREMENT_CONTRACT",
                        "uri": "repo://changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",
                        "sha256": EXPECTED_DEPENDENCY_HASHES[
                            "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
                        ],
                    },
                ],
            },
        },
        "portfolio_policy": {
            "category": {
                "decision_id": "OD-001",
                "decision_status": "HUMAN_DECISION_REQUIRED",
                "actual_category": "UNAVAILABLE",
                "planning_category_ref": CATEGORY_REF,
                "placeholder_only": True,
            },
            "program": PROGRAM,
            "same_category_required": True,
            "same_program_required": True,
            "minimum_slot_count": 30,
            "maximum_slot_count": 45,
            "selected_placeholder_slot_count": SLOT_COUNT,
            "placeholder_id_prefix": SLOT_PREFIX,
            "slot_identity_classification": "SYNTHETIC_PLACEHOLDER_NOT_AN_ARTICLE",
            "slot_states": {
                "creation": "NOT_CREATED",
                "approval": "NOT_APPROVED",
                "publication": "NOT_PUBLIC",
            },
            "actual_article_fields": "UNAVAILABLE",
            "selection_inputs_excluded": [
                "AFFILIATE_COMMISSION_RATE",
                "EPC",
                "RPM",
                "REWARD",
                "COST",
                "PROFIT",
            ],
        },
        "quality_policy": {
            "evaluation_mode": "RECORDED_SYNTHETIC_ONLY",
            "aggregate_quality_threshold": "85",
            "aggregate_quality_minimum": "0",
            "aggregate_quality_maximum": "100",
            "major_claim_coverage_numerator": 1,
            "major_claim_coverage_denominator": 1,
            "arithmetic": "DECIMAL_AND_INTEGER_CROSS_MULTIPLICATION",
            "missing_input": "UNAVAILABLE",
            "zero_denominator": "UNAVAILABLE",
            "synthetic_pass_is_formal_evidence": False,
            "synthetic_pass_can_approve_article": False,
            "synthetic_pass_can_satisfy_story": False,
        },
        "recorded_synthetic_harness": {
            "schema_uri": f"repo://{FIXTURE_SCHEMA_PATH.as_posix()}",
            "schema_sha256": FIXTURE_SCHEMA_SHA256,
            "schema_behavior": "CLOSED_ADDITIONAL_PROPERTIES_FALSE",
            "fixture_uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "fixture_sha256": FIXTURE_SHA256,
            "fixed_path_only": True,
            "dynamic_input_path": "FORBIDDEN",
            "network": "FORBIDDEN",
            "provider": "FORBIDDEN",
            "repository_result_write": "FORBIDDEN",
        },
        "decision": {
            "overall": "BLOCKED",
            "dependency_eligibility": "NOT_ELIGIBLE",
            "downstream_gate_1_eligible": False,
            "acceptance_criteria_satisfied": False,
            "qualifying_evidence_references": [],
            "actual_observations": [],
        },
        "authority_boundary": {
            "external_authority": "NONE",
            "article_creation_authority": "NONE",
            "approval_authority": "NONE",
            "publication_authority": "NONE",
            "gate_authority": "NONE",
            "status_propose_authority": "NONE",
            "status_apply_authority": "NONE",
            "staging_authority": "NONE",
            "release_authority": "NONE",
            "production_authority": "NONE",
        },
        "execution_boundary": {
            "local_generation_only": True,
            "input_size_limit_bytes": MAX_INPUT_BYTES,
            "input_read_model": "ROOT_FD_DESCRIPTOR_RELATIVE_CAPTURED_LEAF",
            "writer_model": "SINGLE_PROCESS_DIRECTORY_LOCK",
            "output_transaction": "TWO_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "check_pending_recovery_behavior": "READ_ONLY_REJECT",
            "environment_access": "FORBIDDEN",
            "subprocess_execution": "FORBIDDEN",
            "external_action_count": 0,
        },
        "evidence_boundary": {
            "classification": "RECORDED_SYNTHETIC_ONLY_NON_ATTESTING",
            "actual_materialized_article_count": "UNAVAILABLE",
            "actual_approved_article_count": "UNAVAILABLE",
            "actual_published_article_count": "UNAVAILABLE",
            "actual_quality_observations": "UNAVAILABLE",
            "actual_major_claim_coverage_observations": "UNAVAILABLE",
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "actual_portfolio_execution": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
        },
    }


def _find_by_id(rows: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        row
        for index, value in enumerate(_list(rows, field))
        if (row := _mapping(value, f"{field}[{index}]")).get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_DRIFT", field)
    return matches[0]


def _validate_hashes(root: Path) -> None:
    for path, expected in {
        **EXPECTED_SOURCE_HASHES,
        **EXPECTED_DEPENDENCY_HASHES,
    }.items():
        if _sha256(_read(root, Path(path), f"binding.{path}")) != expected:
            _fail("PINNED_INPUT_DRIFT", f"binding.{path}")
    if (
        _sha256(_read(root, FIXTURE_SCHEMA_PATH, "fixture_schema"))
        != FIXTURE_SCHEMA_SHA256
    ):
        _fail("PINNED_INPUT_DRIFT", "fixture_schema")
    if _sha256(_read(root, FIXTURE_PATH, "fixture")) != FIXTURE_SHA256:
        _fail("PINNED_INPUT_DRIFT", "fixture")


def _validate_canonical_semantics(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "canonical.backlog",
    )
    story = _find_by_id(backlog.get("stories"), "ST-1801", "canonical.backlog.stories")
    for field, expected in {
        "depends_on": ["ST-1705"],
        "acceptance_criteria": ["quality>=85", "major claim coverage 100%"],
        "test_suites": ["TST-020", "TST-032"],
        "design_status": "APPROVED_FOR_IMPLEMENTATION",
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }.items():
        _exact(story.get(field), expected, f"canonical.story.{field}")

    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "canonical.open_decisions",
    )
    od001 = _find_by_id(
        decisions.get("items"), "OD-001", "canonical.open_decisions.items"
    )
    _exact(od001.get("status"), "HUMAN_DECISION_REQUIRED", "canonical.od001.status")
    _exact(od001.get("blocking"), True, "canonical.od001.blocking")
    _exact(
        od001.get("default_behavior"),
        "カテゴリ固有実装を停止し合成Fixtureのみ使用",
        "canonical.od001.default_behavior",
    )

    tests = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "canonical.tests",
    )
    for suite_id, environment in (("TST-020", ["CI"]), ("TST-032", ["staging"])):
        suite = _find_by_id(tests.get("suites"), suite_id, "canonical.tests.suites")
        _exact(
            suite.get("environments"), environment, f"canonical.{suite_id}.environment"
        )
        _exact(
            suite.get("execution_status"),
            "NOT_EXECUTED",
            f"canonical.{suite_id}.status",
        )

    quality = _load_yaml(
        root,
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_quality_gate_catalog_v0.1.yaml"
        ),
        "quality.catalog",
    )
    _exact(quality.get("publish_threshold"), 85, "quality.publish_threshold")
    gates = _list(quality.get("gates"), "quality.gates")
    qg004 = _find_by_id(gates, "QG-CONT-004", "quality.gates")
    qg006 = _find_by_id(gates, "QG-CONT-006", "quality.gates")
    _exact(qg004.get("failure_action"), "BLOCK", "quality.qg004.failure")
    _exact(qg006.get("failure_action"), "BLOCK", "quality.qg006.failure")

    claims = _load_yaml(
        root,
        Path(
            "contracts/raos-v0.4/contracts/content/RAOS_06_claim_evidence_policy_v0.1.yaml"
        ),
        "claim.policy",
    )
    coverage = _mapping(claims.get("coverage_rules"), "claim.coverage_rules")
    _exact(
        coverage.get("major_claim_evidence_coverage_required"),
        1.0,
        "claim.major_coverage",
    )
    _exact(coverage.get("ai_output_is_never_evidence"), True, "claim.ai_evidence")

    runtime = _load_yaml(
        root,
        Path("changes/st-0605/contracts/claim-evidence-runtime.v1.yaml"),
        "claim.runtime",
    )
    _exact(
        runtime.get("runtime"),
        {
            "executable": True,
            "provider_mode": "RECORDED_SYNTHETIC_ONLY",
            "repository_write": False,
            "publication_authorized": False,
            "production_eligible": False,
        },
        "claim.runtime.boundary",
    )
    thresholds = _mapping(runtime.get("thresholds"), "claim.runtime.thresholds")
    _exact(
        thresholds.get("major"),
        {"evidenced_numerator": 1, "total_denominator": 1},
        "claim.runtime.major",
    )
    _exact(thresholds.get("zero_denominator"), "UNEVALUABLE", "claim.runtime.zero")


def _validate_dependencies(root: Path) -> None:
    signoff = _load_json(
        root,
        Path(
            "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json"
        ),
        "dependency.st1705",
    )
    story = _mapping(signoff.get("story"), "dependency.st1705.story")
    decision = _mapping(signoff.get("decision"), "dependency.st1705.decision")
    _exact(story.get("id"), "ST-1705", "dependency.st1705.story.id")
    _exact(
        story.get("acceptance_criteria_satisfied"),
        False,
        "dependency.st1705.acceptance",
    )
    _exact(decision.get("overall"), "BLOCKED", "dependency.st1705.overall")
    _exact(decision.get("pilot_eligibility"), "NOT_ELIGIBLE", "dependency.st1705.pilot")
    _exact(
        decision.get("downstream_st_1801_eligibility"),
        "NOT_ELIGIBLE",
        "dependency.st1705.downstream",
    )
    _exact(
        decision.get("qualifying_evidence_references"), [], "dependency.st1705.evidence"
    )
    _exact(decision.get("approval_artifacts"), [], "dependency.st1705.approvals")

    articles = _load_json(
        root,
        Path("changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"),
        "dependency.st1704.articles",
    )
    _exact(articles.get("story_id"), "ST-1704", "dependency.st1704.story")
    _exact(articles.get("publication_authority"), "NONE", "dependency.st1704.authority")
    rows = _list(articles.get("articles"), "dependency.st1704.articles.rows")
    if len(rows) != 5:
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1704.articles.count")
    observed_ids: list[object] = []
    for index, value in enumerate(rows):
        row = _mapping(value, f"dependency.st1704.articles[{index}]")
        observed_ids.append(row.get("article_id"))
        _exact(
            row.get("publication_authority"),
            "NONE",
            f"dependency.st1704.articles[{index}].authority",
        )
    _exact(observed_ids, list(ARTICLE_IDS), "dependency.st1704.article_ids")

    publication = _load_json(
        root,
        Path(
            "changes/st-1704/self-hosted-editorial-pilot-v1/operations/publication-plan.v1.json"
        ),
        "dependency.st1704.publication",
    )
    _exact(
        publication.get("publication_authority"),
        "NONE",
        "dependency.st1704.publication.authority",
    )
    publication_rows = _list(
        publication.get("articles"), "dependency.st1704.publication.rows"
    )
    if len(publication_rows) != 5:
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "dependency.st1704.publication.count")
    for index, value in enumerate(publication_rows):
        row = _mapping(value, f"dependency.st1704.publication[{index}]")
        _exact(
            row.get("immutable_snapshot_sha256"),
            None,
            f"dependency.st1704.publication[{index}].snapshot",
        )
        _exact(
            row.get("public_verification"),
            "NOT_EXECUTED",
            f"dependency.st1704.publication[{index}].verification",
        )

    measurement = _load_json(
        root,
        Path("changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"),
        "dependency.st1704.measurement",
    )
    _exact(
        measurement.get("story_id"), "ST-1704", "dependency.st1704.measurement.story"
    )
    _exact(measurement.get("program"), PROGRAM, "dependency.st1704.measurement.program")
    measured = _list(
        measurement.get("articles"), "dependency.st1704.measurement.articles"
    )
    _exact(
        [
            _mapping(row, "dependency.st1704.measurement.article").get("article_id")
            for row in measured
        ],
        list(ARTICLE_IDS),
        "dependency.st1704.measurement.ids",
    )
    guardrails = _mapping(
        measurement.get("guardrails"), "dependency.st1704.measurement.guardrails"
    )
    _exact(
        guardrails.get("recommendation_inputs_excluded"),
        ["AFFILIATE_COMMISSION_RATE", "EPC", "RPM", "PROFIT"],
        "dependency.st1704.measurement.excluded",
    )
    _exact(
        guardrails.get("automatic_publication"),
        False,
        "dependency.st1704.measurement.publication",
    )


def evaluate_recorded_synthetic(
    quality_score: object,
    major_claim_count: object,
    evidenced_major_claim_count: object,
) -> dict[str, object]:
    """Evaluate only the two ST-1801 numeric thresholds with no authority."""

    if quality_score is None:
        quality_status = "UNAVAILABLE"
        normalized_score: str = "UNAVAILABLE"
    else:
        if (
            type(quality_score) is not str
            or SCORE_PATTERN.fullmatch(quality_score) is None
        ):
            _fail("INVALID_QUALITY_SCORE", "evaluation.quality_score")
        try:
            score = Decimal(quality_score)
        except InvalidOperation:
            _fail("INVALID_QUALITY_SCORE", "evaluation.quality_score")
        if not score.is_finite() or score < QUALITY_MINIMUM or score > QUALITY_MAXIMUM:
            _fail("INVALID_QUALITY_SCORE", "evaluation.quality_score")
        normalized_score = format(score, "f")
        quality_status = "PASS" if score >= QUALITY_THRESHOLD else "FAIL"

    if major_claim_count is None:
        total_count: int | None = None
    elif type(major_claim_count) is int:
        total_count = major_claim_count
        if total_count < 0 or total_count > 1_000_000:
            _fail("INVALID_CLAIM_COUNT", "evaluation.major_claim_count")
    else:
        _fail("INVALID_CLAIM_COUNT", "evaluation.major_claim_count")
    if evidenced_major_claim_count is None:
        evidenced_count: int | None = None
    elif type(evidenced_major_claim_count) is int:
        evidenced_count = evidenced_major_claim_count
        if evidenced_count < 0 or evidenced_count > 1_000_000:
            _fail("INVALID_CLAIM_COUNT", "evaluation.evidenced_major_claim_count")
    else:
        _fail("INVALID_CLAIM_COUNT", "evaluation.evidenced_major_claim_count")
    if (
        total_count is not None
        and evidenced_count is not None
        and evidenced_count > total_count
    ):
        _fail("INVALID_CLAIM_COUNT", "evaluation.evidenced_major_claim_count")

    if total_count is None or evidenced_count is None or total_count == 0:
        coverage_status = "UNAVAILABLE"
        coverage_percent: str = "UNAVAILABLE"
    else:
        coverage_status = "PASS" if evidenced_count * 1 == total_count * 1 else "FAIL"
        coverage_percent = format(
            (Decimal(evidenced_count) * Decimal(100) / Decimal(total_count)).quantize(
                Decimal("0.000001")
            ),
            "f",
        )

    if "UNAVAILABLE" in {quality_status, coverage_status}:
        status = "UNAVAILABLE"
    elif quality_status == "PASS" and coverage_status == "PASS":
        status = "PASS"
    else:
        status = "FAIL"
    return {
        "status": status,
        "quality_status": quality_status,
        "major_claim_coverage_status": coverage_status,
        "normalized_quality_score": normalized_score,
        "major_claim_coverage_percent": coverage_percent,
        "classification": "RECORDED_SYNTHETIC_ONLY_NOT_ARTICLE_EVIDENCE",
        "formal_evidence_eligible": False,
        "article_approval_eligible": False,
        "story_acceptance_eligible": False,
    }


def _validate_fixture(root: Path) -> list[dict[str, object]]:
    schema = _load_json(root, FIXTURE_SCHEMA_PATH, "fixture_schema")
    _closed(
        schema,
        (
            "$schema",
            "$id",
            "title",
            "type",
            "additionalProperties",
            "required",
            "properties",
            "$defs",
        ),
        "fixture_schema",
    )
    _exact(schema.get("type"), "object", "fixture_schema.type")
    _exact(schema.get("additionalProperties"), False, "fixture_schema.closed")

    fixture = _load_json(root, FIXTURE_PATH, "fixture")
    _closed(fixture, ("schema", "classification", "cases"), "fixture")
    _exact(
        fixture.get("schema"),
        "ST1801_RECORDED_SYNTHETIC_QUALITY_EVALUATION_V1",
        "fixture.schema",
    )
    _exact(
        fixture.get("classification"),
        "RECORDED_SYNTHETIC_ONLY_NOT_ARTICLE_EVIDENCE",
        "fixture.classification",
    )
    cases = _list(fixture.get("cases"), "fixture.cases")
    if not 1 <= len(cases) <= 32:
        _fail("FIXTURE_CASE_COUNT", "fixture.cases")
    results: list[dict[str, object]] = []
    identities: set[str] = set()
    for index, value in enumerate(cases):
        case = _closed(
            value, ("case_id", "input", "expected"), f"fixture.cases[{index}]"
        )
        identity = case.get("case_id")
        if (
            type(identity) is not str
            or re.fullmatch(r"synthetic-[a-z0-9-]{1,64}", identity) is None
            or identity in identities
        ):
            _fail("FIXTURE_CASE_ID_INVALID", f"fixture.cases[{index}].case_id")
        identities.add(identity)
        inputs = _closed(
            case.get("input"),
            ("quality_score", "major_claim_count", "evidenced_major_claim_count"),
            f"fixture.cases[{index}].input",
        )
        expected = _closed(
            case.get("expected"),
            ("status", "quality_status", "major_claim_coverage_status"),
            f"fixture.cases[{index}].expected",
        )
        result = evaluate_recorded_synthetic(
            inputs.get("quality_score"),
            inputs.get("major_claim_count"),
            inputs.get("evidenced_major_claim_count"),
        )
        _exact(
            {
                key: result[key]
                for key in ("status", "quality_status", "major_claim_coverage_status")
            },
            dict(expected),
            f"fixture.cases[{index}].expected",
        )
        results.append({"case_id": identity, **result})
    return results


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    _validate_hashes(root)
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    expected = _expected_contract_sections()
    _exact(contract, expected, "contract")
    _validate_canonical_semantics(root)
    _validate_dependencies(root)
    _validate_fixture(root)
    return contract


def _slot(index: int) -> dict[str, object]:
    return {
        "slot_number": index,
        "placeholder_slot_id": f"{SLOT_PREFIX}{index:03d}",
        "identity_classification": "SYNTHETIC_PLACEHOLDER_NOT_AN_ARTICLE",
        "category_ref": CATEGORY_REF,
        "program": PROGRAM,
        "creation_status": "NOT_CREATED",
        "approval_status": "NOT_APPROVED",
        "publication_status": "NOT_PUBLIC",
        "article_id": None,
        "slug": None,
        "url": None,
        "schedule": None,
        "quality_score": "UNAVAILABLE",
        "major_claim_count": "UNAVAILABLE",
        "evidenced_major_claim_count": "UNAVAILABLE",
        "major_claim_coverage_percent": "UNAVAILABLE",
        "actual_observations": [],
        "evidence_references": [],
    }


def portfolio_record(
    contract: Mapping[str, Any], fixture_results: list[dict[str, object]]
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "story": {
            "id": "ST-1801",
            "scope": "LOCAL_BLOCKED_SYNTHETIC_PORTFOLIO_PLANNING_ONLY",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "classification": "LOCAL_BLOCKED_SYNTHETIC_PORTFOLIO_PLAN_NON_ATTESTING",
        "source_bindings": contract["source_bindings"],
        "dependency_bindings": contract["dependency_bindings"],
        "portfolio": {
            "category_decision": "OD-001_UNRESOLVED",
            "actual_category": "UNAVAILABLE",
            "planning_category_ref": CATEGORY_REF,
            "program": PROGRAM,
            "minimum_slot_count": 30,
            "maximum_slot_count": 45,
            "planned_placeholder_slot_count": SLOT_COUNT,
            "planned_slots": [_slot(index) for index in range(1, SLOT_COUNT + 1)],
            "actual_materialized_article_count": "UNAVAILABLE",
            "actual_approved_article_count": "UNAVAILABLE",
            "actual_published_article_count": "UNAVAILABLE",
            "same_real_category_validated": False,
            "same_program_validated_for_placeholders": True,
        },
        "acceptance_evaluation": {
            "actual_portfolio_quality_status": "UNAVAILABLE",
            "actual_portfolio_major_claim_coverage_status": "UNAVAILABLE",
            "actual_quality_observations": [],
            "actual_major_claim_coverage_observations": [],
            "recorded_synthetic_harness": {
                "classification": "RECORDED_SYNTHETIC_ONLY_NOT_ARTICLE_EVIDENCE",
                "fixture_uri": f"repo://{FIXTURE_PATH.as_posix()}",
                "fixture_sha256": FIXTURE_SHA256,
                "case_count": len(fixture_results),
                "results": fixture_results,
                "qualifies_as_article_evidence": False,
                "qualifies_as_portfolio_evidence": False,
                "qualifies_as_gate_evidence": False,
            },
        },
        "decision": contract["decision"],
        "blockers": [
            "ST1705_DOWNSTREAM_ST1801_NOT_ELIGIBLE",
            "OD001_INITIAL_CATEGORY_UNRESOLVED",
            "ACTUAL_30_TO_45_ARTICLE_EXECUTION_NOT_EXECUTED",
            "ACTUAL_QUALITY_OBSERVATIONS_UNAVAILABLE",
            "ACTUAL_MAJOR_CLAIM_COVERAGE_OBSERVATIONS_UNAVAILABLE",
            "FORMAL_TST_020_NOT_EXECUTED",
            "FORMAL_TST_032_NOT_EXECUTED",
            "HUMAN_APPROVAL_MISSING",
            "PUBLICATION_NOT_EXECUTED",
        ],
        "actual_observations": [],
        "qualifying_evidence_references": [],
        "authority_boundary": contract["authority_boundary"],
        "execution_boundary": contract["execution_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "prohibited_interpretations": [
            "PLACEHOLDER_SLOTS_ARE_NOT_ARTICLES",
            "ST1704_TRACKED_ARTIFACTS_ARE_NOT_EXPANSION_OR_PUBLICATION_EVIDENCE",
            "SYNTHETIC_PASS_IS_NOT_ARTICLE_APPROVAL_OR_GATE_EVIDENCE",
            "UNAVAILABLE_COUNTS_MUST_NOT_BE_COERCED_TO_ZERO",
            "NO_CATEGORY_CONTENT_URL_SCHEDULE_OR_QUALITY_VALUE_WAS_INFERRED",
            "NO_STATUS_GATE_PUBLICATION_STAGING_RELEASE_OR_PRODUCTION_AUTHORITY",
        ],
    }


def validate_portfolio_record(
    record: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    expected = portfolio_record(contract, _validate_fixture(REPO_ROOT))
    _exact(record, expected, "portfolio_record")


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _source_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, f"source.{relative.as_posix()}")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, pack_bytes: bytes) -> bytes:
    manifest = {
        "story_id": "ST-1801",
        "schema_version": 1,
        "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
        "generation_command": GENERATION_COMMAND,
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_source_row(root, path) for path in SOURCE_PATHS],
        "bound_input_count": len(EXPECTED_SOURCE_HASHES)
        + len(EXPECTED_DEPENDENCY_HASHES),
        "bound_inputs": [
            *_hash_rows(EXPECTED_SOURCE_HASHES, kind="CANONICAL_OR_QUALITY_AUTHORITY"),
            *_hash_rows(
                EXPECTED_DEPENDENCY_HASHES, kind="NON_ATTESTING_DEPENDENCY_INPUT"
            ),
        ],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{PACK_PATH.as_posix()}",
                "bytes": len(pack_bytes),
                "sha256": _sha256(pack_bytes),
            }
        ],
        "transaction": {
            "model": "TWO_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "writer_lock": "GENERATED_DIRECTORY_FLOCK",
            "check_pending_recovery": "READ_ONLY_REJECT",
        },
        "boundary": {
            "classification": "LOCAL_BLOCKED_SYNTHETIC_PORTFOLIO_PLAN_NON_ATTESTING",
            "decision": "BLOCKED",
            "planned_placeholder_slots": SLOT_COUNT,
            "actual_articles": "UNAVAILABLE",
            "downstream_gate_1_eligible": False,
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "publication_authority": "NONE",
            "release_authority": "NONE",
            "production_authority": "NONE",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    fixture_results = _validate_fixture(root)
    record = portfolio_record(contract, fixture_results)
    _exact(record, portfolio_record(contract, fixture_results), "portfolio_record")
    pack_bytes = _json_bytes(record)
    return {PACK_PATH: pack_bytes, MANIFEST_PATH: _manifest_bytes(root, pack_bytes)}


@dataclass(frozen=True, slots=True)
class _Snapshot:
    content: bytes
    identity: tuple[int, ...]


@dataclass(slots=True)
class _OutputDirectory:
    descriptor: int
    identity: tuple[int, int]


def _open_output_directory(root: Path) -> _OutputDirectory:
    relative = PACK_PATH.parent
    descriptor = _open_root(root, "output")
    try:
        for part in relative.parts:
            before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o022
            ):
                _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
            child = os.open(
                part,
                os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                dir_fd=descriptor,
            )
            after = os.fstat(child)
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                _close(child)
                _fail("OUTPUT_ANCESTOR_CHANGED", "output")
            _close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        result = _OutputDirectory(descriptor, (metadata.st_dev, metadata.st_ino))
        descriptor = -1
        return result
    except OSError:
        _fail("UNSAFE_OUTPUT_ANCESTOR", "output")
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _assert_output_directory(root: Path, output: _OutputDirectory) -> None:
    fresh = _open_output_directory(root)
    try:
        if fresh.identity != output.identity:
            _fail("OUTPUT_ANCESTOR_CHANGED", "output")
    finally:
        _close(fresh.descriptor)


def _snapshot(
    output: _OutputDirectory,
    name: str,
    field: str,
    *,
    missing_ok: bool,
    expected_mode: int | None = None,
) -> _Snapshot | None:
    try:
        before = os.stat(name, dir_fd=output.descriptor, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        _fail("OUTPUT_RECOVERY_REQUIRED", field)
    except OSError:
        _fail("OUTPUT_PREFLIGHT_FAILED", field)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != 1
    ):
        _fail("UNSAFE_OUTPUT_TARGET", field)
    mode = stat.S_IMODE(before.st_mode)
    if (expected_mode is not None and mode != expected_mode) or (
        expected_mode is None and mode & 0o022
    ):
        _fail("UNSAFE_OUTPUT_MODE", field)
    if before.st_size < 0 or before.st_size > MAX_INPUT_BYTES:
        _fail("OUTPUT_SIZE_LIMIT", field)
    descriptor = -1
    try:
        descriptor = os.open(
            name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=output.descriptor
        )
        opened = os.fstat(descriptor)
        if _identity(before) != _identity(opened):
            _fail("OUTPUT_TARGET_CHANGED", field)
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, READ_CHUNK_BYTES))
            if not chunk:
                _fail("OUTPUT_TARGET_CHANGED", field)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail("OUTPUT_TARGET_CHANGED", field)
        after = os.stat(name, dir_fd=output.descriptor, follow_symlinks=False)
        if _identity(opened) != _identity(after):
            _fail("OUTPUT_TARGET_CHANGED", field)
        return _Snapshot(b"".join(chunks), _identity(opened))
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _fsync(output: _OutputDirectory) -> None:
    try:
        os.fsync(output.descriptor)
    except OSError:
        _fail("OUTPUT_FSYNC_FAILED", "output")


def _write_exclusive(
    output: _OutputDirectory, name: str, content: bytes, mode: int, field: str
) -> None:
    descriptor = -1
    created = False
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            mode,
            dir_fd=output.descriptor,
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
        _fsync(output)
        observed = _snapshot(output, name, field, missing_ok=False, expected_mode=mode)
        if observed is None or observed.content != content:
            _fail("OUTPUT_COMPANION_DRIFT", field)
    except PortfolioExpansionError:
        raise
    except OSError:
        if created:
            try:
                os.unlink(name, dir_fd=output.descriptor)
                _fsync(output)
            except OSError:
                _fail("OUTPUT_RECOVERY_REQUIRED", field)
        _fail("OUTPUT_WRITE_FAILED", field)
    finally:
        if descriptor >= 0:
            _close(descriptor)


def _unlink(output: _OutputDirectory, name: str) -> None:
    try:
        os.unlink(name, dir_fd=output.descriptor)
        _fsync(output)
    except OSError:
        _fail("OUTPUT_RECOVERY_REQUIRED", "output")


def _target_name(path: Path) -> str:
    if path.parent != PACK_PATH.parent or path not in GENERATED_PATHS:
        _fail("OUTPUT_INVENTORY_DRIFT", "output")
    return path.name


def _stage_name(path: Path) -> str:
    return f".{_target_name(path)}{STAGE_SUFFIX}"


def _previous_name(path: Path) -> str:
    return f".{_target_name(path)}{PREVIOUS_SUFFIX}"


def _absent_name(path: Path) -> str:
    return f".{_target_name(path)}{ABSENT_SUFFIX}"


def _journal_bytes(
    state: str,
    outputs: Mapping[Path, bytes],
    originals: Mapping[Path, _Snapshot | None],
) -> bytes:
    value = {
        "schema": TRANSACTION_SCHEMA,
        "state": state,
        "outputs": [
            {
                "path": path.as_posix(),
                "next_sha256": _sha256(outputs[path]),
                "original_present": originals[path] is not None,
                "original_sha256": _sha256(snapshot.content)
                if (snapshot := originals[path]) is not None
                else None,
            }
            for path in GENERATED_PATHS
        ],
    }
    return _json_bytes(value)


def _load_journal(
    output: _OutputDirectory, name: str, *, missing_ok: bool
) -> Mapping[str, Any] | None:
    snapshot = _snapshot(
        output, name, "transaction", missing_ok=missing_ok, expected_mode=PRIVATE_MODE
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
            snapshot.content.decode("utf-8"), object_pairs_hook=unique_pairs
        )
    except UnicodeError, json.JSONDecodeError:
        _fail("TRANSACTION_INVALID", "transaction")
    return _mapping(value, "transaction")


def _decode_journal(
    value: Mapping[str, Any], expected_state: str
) -> tuple[dict[Path, str], dict[Path, str | None]]:
    _closed(value, ("schema", "state", "outputs"), "transaction")
    _exact(value.get("schema"), TRANSACTION_SCHEMA, "transaction.schema")
    _exact(value.get("state"), expected_state, "transaction.state")
    rows = _list(value.get("outputs"), "transaction.outputs")
    if len(rows) != len(GENERATED_PATHS):
        _fail("TRANSACTION_INVALID", "transaction.outputs")
    next_hashes: dict[Path, str] = {}
    original_hashes: dict[Path, str | None] = {}
    for index, path in enumerate(GENERATED_PATHS):
        row = _closed(
            rows[index],
            ("path", "next_sha256", "original_present", "original_sha256"),
            f"transaction.outputs[{index}]",
        )
        _exact(row.get("path"), path.as_posix(), f"transaction.outputs[{index}].path")
        next_digest = row.get("next_sha256")
        original_present = row.get("original_present")
        original_digest = row.get("original_sha256")
        if (
            type(next_digest) is not str
            or re.fullmatch(r"[0-9a-f]{64}", next_digest) is None
            or type(original_present) is not bool
        ):
            _fail("TRANSACTION_INVALID", f"transaction.outputs[{index}]")
        if original_present:
            if (
                type(original_digest) is not str
                or re.fullmatch(r"[0-9a-f]{64}", original_digest) is None
            ):
                _fail("TRANSACTION_INVALID", f"transaction.outputs[{index}]")
        elif original_digest is not None:
            _fail("TRANSACTION_INVALID", f"transaction.outputs[{index}]")
        next_hashes[path] = next_digest
        original_hashes[path] = original_digest
    return next_hashes, original_hashes


def _companions_present(output: _OutputDirectory) -> bool:
    for name, mode in (
        (TRANSACTION_NAME, PRIVATE_MODE),
        (TRANSACTION_NEXT_NAME, PRIVATE_MODE),
    ):
        if (
            _snapshot(output, name, "transaction", missing_ok=True, expected_mode=mode)
            is not None
        ):
            return True
    for path in GENERATED_PATHS:
        companion_specs: tuple[tuple[str, int | None], ...] = (
            (_stage_name(path), OUTPUT_MODE),
            (_previous_name(path), None),
            (_absent_name(path), PRIVATE_MODE),
        )
        for name, expected_mode in companion_specs:
            if (
                _snapshot(
                    output,
                    name,
                    "output_companion",
                    missing_ok=True,
                    expected_mode=expected_mode,
                )
                is not None
            ):
                return True
    return False


def _recover(root: Path, output: _OutputDirectory, *, mutate: bool) -> None:
    journal = _load_journal(output, TRANSACTION_NAME, missing_ok=True)
    journal_next = _load_journal(output, TRANSACTION_NEXT_NAME, missing_ok=True)
    if journal is None:
        if journal_next is not None or _companions_present(output):
            _fail("OUTPUT_RECOVERY_REQUIRED", "transaction")
        return
    if not mutate:
        _fail("OUTPUT_RECOVERY_REQUIRED", "transaction")
    state = journal.get("state")
    if state not in {"PREPARED", "COMMITTED"}:
        _fail("TRANSACTION_INVALID", "transaction")
    next_hashes, original_hashes = _decode_journal(journal, state)
    if journal_next is not None:
        if state != "PREPARED":
            _fail("TRANSACTION_INVALID", "transaction")
        next2, original2 = _decode_journal(journal_next, "COMMITTED")
        if next2 != next_hashes or original2 != original_hashes:
            _fail("TRANSACTION_INVALID", "transaction")
    _assert_output_directory(root, output)

    if state == "COMMITTED":
        for path in GENERATED_PATHS:
            target = _snapshot(
                output, _target_name(path), "generated_output", missing_ok=False
            )
            if target is None or _sha256(target.content) != next_hashes[path]:
                _fail("COMMITTED_OUTPUT_DRIFT", "generated_output")
            if (
                _snapshot(
                    output,
                    _stage_name(path),
                    "output_companion",
                    missing_ok=True,
                    expected_mode=OUTPUT_MODE,
                )
                is not None
            ):
                _fail("TRANSACTION_INVALID", "output_companion")
        for path in GENERATED_PATHS:
            previous = _snapshot(
                output, _previous_name(path), "output_companion", missing_ok=True
            )
            absent = _snapshot(
                output,
                _absent_name(path),
                "output_companion",
                missing_ok=True,
                expected_mode=PRIVATE_MODE,
            )
            if (previous is None) == (absent is None):
                _fail("TRANSACTION_INVALID", "output_companion")
            if previous is not None:
                _unlink(output, _previous_name(path))
            if absent is not None:
                if absent.content != ABSENT_MARKER:
                    _fail("TRANSACTION_INVALID", "output_companion")
                _unlink(output, _absent_name(path))
        _unlink(output, TRANSACTION_NAME)
        return

    for path in GENERATED_PATHS:
        stage = _snapshot(
            output,
            _stage_name(path),
            "output_companion",
            missing_ok=True,
            expected_mode=OUTPUT_MODE,
        )
        if stage is not None and _sha256(stage.content) != next_hashes[path]:
            _fail("TRANSACTION_INVALID", "output_companion")
        previous = _snapshot(
            output, _previous_name(path), "output_companion", missing_ok=True
        )
        absent = _snapshot(
            output,
            _absent_name(path),
            "output_companion",
            missing_ok=True,
            expected_mode=PRIVATE_MODE,
        )
        target = _snapshot(
            output, _target_name(path), "generated_output", missing_ok=True
        )
        original_digest = original_hashes[path]
        if original_digest is not None:
            if absent is not None:
                _fail("TRANSACTION_INVALID", "output_companion")
            if previous is not None:
                if _sha256(previous.content) != original_digest:
                    _fail("TRANSACTION_INVALID", "output_companion")
                if target is not None:
                    if _sha256(target.content) != next_hashes[path]:
                        _fail("TRANSACTION_INVALID", "generated_output")
                    _unlink(output, _target_name(path))
                try:
                    os.replace(
                        _previous_name(path),
                        _target_name(path),
                        src_dir_fd=output.descriptor,
                        dst_dir_fd=output.descriptor,
                    )
                    _fsync(output)
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
                    if _sha256(target.content) != next_hashes[path]:
                        _fail("TRANSACTION_INVALID", "generated_output")
                    _unlink(output, _target_name(path))
                _unlink(output, _absent_name(path))
            elif target is not None:
                _fail("TRANSACTION_INVALID", "generated_output")
        if stage is not None:
            _unlink(output, _stage_name(path))
    if journal_next is not None:
        _unlink(output, TRANSACTION_NEXT_NAME)
    _unlink(output, TRANSACTION_NAME)


def _transaction_checkpoint(_name: str) -> None:
    """Test-only crash checkpoint; production execution is inert."""


def _write_transaction(
    root: Path, output: _OutputDirectory, outputs: Mapping[Path, bytes]
) -> None:
    if tuple(outputs) != GENERATED_PATHS or _companions_present(output):
        _fail("OUTPUT_INVENTORY_DRIFT", "output")
    originals = {
        path: _snapshot(output, _target_name(path), "generated_output", missing_ok=True)
        for path in GENERATED_PATHS
    }
    _write_exclusive(
        output,
        TRANSACTION_NAME,
        _journal_bytes("PREPARED", outputs, originals),
        PRIVATE_MODE,
        "transaction",
    )
    _transaction_checkpoint("PREPARED")
    for path in GENERATED_PATHS:
        _write_exclusive(
            output, _stage_name(path), outputs[path], OUTPUT_MODE, "output_stage"
        )
        _transaction_checkpoint(f"STAGED_{path.as_posix()}")
    for path in GENERATED_PATHS:
        _assert_output_directory(root, output)
        observed = _snapshot(
            output, _target_name(path), "generated_output", missing_ok=True
        )
        original = originals[path]
        if (observed is None) != (original is None) or (
            observed is not None
            and original is not None
            and _sha256(observed.content) != _sha256(original.content)
        ):
            _fail("OUTPUT_TARGET_CHANGED", "generated_output")
        if original is None:
            _write_exclusive(
                output,
                _absent_name(path),
                ABSENT_MARKER,
                PRIVATE_MODE,
                "output_companion",
            )
        else:
            try:
                os.replace(
                    _target_name(path),
                    _previous_name(path),
                    src_dir_fd=output.descriptor,
                    dst_dir_fd=output.descriptor,
                )
                _fsync(output)
            except OSError:
                _fail("OUTPUT_TRANSACTION_FAILED", "output")
        _transaction_checkpoint(f"BACKED_UP_{path.as_posix()}")
        try:
            os.replace(
                _stage_name(path),
                _target_name(path),
                src_dir_fd=output.descriptor,
                dst_dir_fd=output.descriptor,
            )
            _fsync(output)
        except OSError:
            _fail("OUTPUT_TRANSACTION_FAILED", "output")
        target = _snapshot(
            output, _target_name(path), "generated_output", missing_ok=False
        )
        if target is None or target.content != outputs[path]:
            _fail("OUTPUT_PUBLISH_DRIFT", "output")
        _transaction_checkpoint(f"PUBLISHED_{path.as_posix()}")
    _write_exclusive(
        output,
        TRANSACTION_NEXT_NAME,
        _journal_bytes("COMMITTED", outputs, originals),
        PRIVATE_MODE,
        "transaction",
    )
    try:
        os.replace(
            TRANSACTION_NEXT_NAME,
            TRANSACTION_NAME,
            src_dir_fd=output.descriptor,
            dst_dir_fd=output.descriptor,
        )
        _fsync(output)
    except OSError:
        _fail("OUTPUT_TRANSACTION_FAILED", "transaction")
    _transaction_checkpoint("COMMITTED")
    _recover(root, output, mutate=True)


def _check_outputs(root: Path, outputs: Mapping[Path, bytes]) -> None:
    for path in GENERATED_PATHS:
        if _read(root, path, "generated_output") != outputs[path]:
            _fail("GENERATED_OUTPUT_DRIFT", "generated_output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    output = _open_output_directory(root)
    try:
        try:
            fcntl.flock(
                output.descriptor,
                (fcntl.LOCK_SH if check else fcntl.LOCK_EX) | fcntl.LOCK_NB,
            )
        except BlockingIOError:
            _fail("CONCURRENT_OUTPUT_WRITER", "writer_lock")
        _recover(root, output, mutate=not check)
        outputs = render_outputs(root)
        if check:
            _check_outputs(root, outputs)
        else:
            try:
                _write_transaction(root, output, outputs)
            except Exception:
                _recover(root, output, mutate=True)
                raise
    finally:
        try:
            fcntl.flock(output.descriptor, fcntl.LOCK_UN)
        except OSError:
            pass
        _close(output.descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the local blocked ST-1801 portfolio plan."
    )
    parser.add_argument(
        "--check", action="store_true", help="verify generated outputs without writing"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except PortfolioExpansionError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
