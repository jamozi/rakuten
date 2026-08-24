#!/usr/bin/env python3
"""Build the deterministic, fail-closed ST-1802 local GATE-1 decision."""

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
            "ST1802_ERROR code=ISOLATED_MODE_REQUIRED field=cli.python", file=sys.stderr
        )
        raise SystemExit(1)
    if sys.flags.dont_write_bytecode != 1:
        print(
            "ST1802_ERROR code=NO_BYTECODE_MODE_REQUIRED field=cli.python",
            file=sys.stderr,
        )
        raise SystemExit(1)


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-1802/contracts/gate1-decision.v1.yaml")
FIXTURE_SCHEMA_PATH: Final = Path(
    "changes/st-1802/contracts/recorded-synthetic-gate1-evaluation.v1.schema.json"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1802/fixtures/recorded-synthetic-gate1-evaluation.v1.json"
)
EVALUATION_PATH: Final = Path(
    "changes/st-1802/generated/recorded-synthetic-gate1-evaluation.v1.json"
)
PACK_PATH: Final = Path(
    "changes/st-1802/generated/gate1-decision.local-blocked.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1802/generated/runtime-manifest.v1.yaml")
GENERATED_PATHS: Final = (EVALUATION_PATH, PACK_PATH, MANIFEST_PATH)
README_PATH: Final = Path("changes/st-1802/README.md")
PREFLIGHT_PATH: Final = Path("changes/st-1802/PREFLIGHT.md")
COMPLETION_PATH: Final = Path(
    "changes/st-1802/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v1.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1802_gate1_decision.py")
TEST_PATHS: Final = (
    Path("tests/st1802/conftest.py"),
    Path("tests/st1802/test_contract.py"),
    Path("tests/st1802/test_evaluator.py"),
    Path("tests/st1802/test_decision.py"),
    Path("tests/st1802/test_generation.py"),
    Path("tests/st1802/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_SCHEMA_PATH,
    FIXTURE_PATH,
    README_PATH,
    PREFLIGHT_PATH,
    COMPLETION_PATH,
    GENERATOR_PATH,
    *TEST_PATHS,
)

MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 64 * 1024
OUTPUT_MODE: Final = 0o644
PRIVATE_MODE: Final = 0o600
TRANSACTION_NAME: Final = ".st1802-gate1.transaction.json"
TRANSACTION_NEXT_NAME: Final = f"{TRANSACTION_NAME}.next"
TRANSACTION_SCHEMA: Final = "ST1802_OUTPUT_TRANSACTION_V1"
STAGE_SUFFIX: Final = ".st1802.next"
PREVIOUS_SUFFIX: Final = ".st1802.previous"
ABSENT_SUFFIX: Final = ".st1802.absent"
ABSENT_MARKER: Final = b"ST1802_OUTPUT_WAS_ABSENT_V1\n"
GENERATION_COMMAND: Final = (
    "/home/minami/rakuten/.venv/bin/python -I -B scripts/build_st1802_gate1_decision.py"
)
PROGRAM: Final = "WORDPRESS_BLOG_RAKUTEN_AFFILIATE"
SYNTHETIC_CLASSIFICATION: Final = "RECORDED_SYNTHETIC_ONLY_NON_ATTESTING"
STATUS_VOCABULARY: Final = (
    "PASS",
    "FAIL",
    "UNAVAILABLE",
    "NOT_EXECUTED",
    "BLOCKED",
    "INELIGIBLE_NON_ATTESTING",
)
SCORE_PATTERN: Final = re.compile(r"^(0|[1-9][0-9]?|100)(\.[0-9]{1,6})?$")
QUALITY_THRESHOLD: Final = Decimal("85")

EXPECTED_SOURCE_HASHES: Final = {
    "docs/upstream/key_documents/RAOS_01_requirements_purpose_success_v0.1.md": (
        "5890c616fdaaf02022a524c91b0ae91a8bf5c6b297338f8c958be0d49b3b62ea"
    ),
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md": (
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3"
    ),
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
    "docs/canonical/05_test/RAOS_11_release_evidence_template_v1.0.yaml": (
        "3354001be5fc0f7f7ef6a265fdd3112618ee943092755745d8cd62986487e95a"
    ),
    "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md": (
        "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
}
EXPECTED_DEPENDENCY_HASHES: Final = {
    "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json": (
        "03fe1dddea0df61c73f30c3192d290806ba99a48e7a0be3f38c7378e9c77449f"
    ),
    "changes/st-1801/generated/runtime-manifest.v1.yaml": (
        "2d6d301749bc67e355342d0d398ab7530324591bc197e9db257a6607cdf8921f"
    ),
    "scripts/build_st1801_portfolio_expansion.py": (
        "308f83b01e612b66547cd1b90433b6b48ba8f3c60040f4dde036fb42394213dd"
    ),
    "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json": (
        "81e776375b6faaaa55a4f2d45bf75750f3bbcf03450b6b3d8ba07723b1d82909"
    ),
    "changes/st-1705/manifest.yaml": (
        "b21c4a683237cefb0f215e2bb17b3438bee314f5d716d180a0963c9e3cba698d"
    ),
    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json": (
        "cc9c0057a1f42546988596ad02891d638471370997eadf50d55bbe61fe884c88"
    ),
    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json": (
        "9559d3d79175145a940a38a471aa7ce3d33238827a144eb809b617b1c34ae0d8"
    ),
}
FIXTURE_SCHEMA_SHA256: Final = (
    "b671401b5859690052217c1caefb6001828a841c0f57064658ecd1d158148c52"
)
FIXTURE_SHA256: Final = (
    "30327d0a85580e10b5114e36076f545c7c81efd4917fa7e42f42719fc56bfa10"
)

EXPECTED_GATE_DEFINITION: Final = {
    "gate_id": "GATE-1",
    "objective": "EDITORIAL_AND_TECHNICAL_PILOT",
    "revenue_required": False,
    "category_count": 1,
    "intent_cluster_count": 3,
    "minimum_article_count": 30,
    "maximum_article_count": 45,
    "minimum_article_type_count": 3,
    "maximum_article_type_count": 5,
    "minimum_quality_score": "85",
    "minimum_all_claim_coverage_numerator": 95,
    "minimum_all_claim_coverage_denominator": 100,
    "major_claim_coverage_numerator": 1,
    "major_claim_coverage_denominator": 1,
    "minimum_first_pass_approval_numerator": 80,
    "minimum_first_pass_approval_denominator": 100,
    "freshness_timestamp_coverage_numerator": 1,
    "freshness_timestamp_coverage_denominator": 1,
    "zero_denominator": "UNAVAILABLE",
    "missing_input": "UNAVAILABLE",
    "arithmetic": "INTEGER_CROSS_MULTIPLICATION_AND_BOUNDED_DECIMAL",
    "excluded_decision_inputs": [
        "AFFILIATE_COMMISSION_RATE",
        "EPC",
        "RPM",
        "REWARD",
        "PROFIT",
    ],
}

_CRITERIA_ROWS: Final = (
    (
        "G1-C01-SINGLE-CATEGORY",
        "ACTUAL_CATEGORY_COUNT_EQUALS_1",
        "INELIGIBLE_NON_ATTESTING",
        "SYNTHETIC_PLACEHOLDER_CATEGORY_ONLY",
        "NON_ATTESTING_SYNTHETIC_DEPENDENCY",
        ("repo://changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json",),
    ),
    (
        "G1-C02-INTENT-CLUSTERS",
        "ACTUAL_INTENT_CLUSTER_COUNT_EQUALS_3",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C03-ARTICLE-COUNT",
        "ACTUAL_ARTICLE_COUNT_BETWEEN_30_AND_45",
        "INELIGIBLE_NON_ATTESTING",
        "30_SYNTHETIC_NOT_CREATED_PLACEHOLDERS",
        "NON_ATTESTING_SYNTHETIC_DEPENDENCY",
        ("repo://changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json",),
    ),
    (
        "G1-C04-ARTICLE-TYPES",
        "ACTUAL_ARTICLE_TYPE_COUNT_BETWEEN_3_AND_5",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C05-ALL-QUALITY-85",
        "EVERY_ACTUAL_ARTICLE_QUALITY_SCORE_AT_LEAST_85",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C06-CRITICAL-FACTUAL-ERRORS",
        "CRITICAL_FACTUAL_ERROR_COUNT_EQUALS_0",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C07-ALL-CLAIM-COVERAGE",
        "EVIDENCED_VERIFIABLE_CLAIMS_AT_LEAST_95_PERCENT",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C08-MAJOR-CLAIM-COVERAGE",
        "EVIDENCED_MAJOR_CLAIMS_EQUALS_100_PERCENT",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C09-FABRICATED-EXPERIENCE",
        "FABRICATED_EXPERIENCE_COUNT_EQUALS_0",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C10-PRODUCT-IDENTITY",
        "PRODUCT_IDENTITY_ERRORS_EQUAL_0_AND_ALL_ITEMS_VERIFIED",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_VERIFICATION_ABSENT",
        (),
    ),
    (
        "G1-C11-LINK-ERRORS",
        "LINK_ERROR_COUNT_EQUALS_0",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_VERIFICATION_ABSENT",
        (),
    ),
    (
        "G1-C12-FIRST-PASS-HUMAN-APPROVAL",
        "FIRST_PASS_HUMAN_APPROVAL_RATE_AT_LEAST_80_PERCENT",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C13-FRESHNESS-TIMESTAMPS",
        "PRICE_AND_STOCK_FINAL_CHECK_TIMESTAMP_DISPLAYED_100_PERCENT",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "ACTUAL_OBSERVATION_ABSENT",
        (),
    ),
    (
        "G1-C14-MEASUREMENT-CONNECTED",
        "ARTICLE_PRODUCT_AND_CLICK_MEASUREMENT_CONNECTED",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "INTERFACE_ONLY_NO_OBSERVATION",
        ("repo://changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",),
    ),
    (
        "G1-C15-PER-ARTICLE-COST",
        "COST_PER_ARTICLE_MEASURABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "OWNER_PRIVATE_OBSERVATION_NOT_READ",
        (),
    ),
    (
        "G1-C16-HUMAN-TIME",
        "HUMAN_TIME_PER_ARTICLE_MEASURABLE",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "OWNER_PRIVATE_OBSERVATION_NOT_READ",
        (),
    ),
    (
        "G1-C17-CHANGE-HISTORY-AUDIT",
        "CHANGE_HISTORY_AND_AUDIT_VERIFIED",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_VERIFICATION_ABSENT",
        (),
    ),
    (
        "G1-C18-ROLLBACK",
        "PUBLICATION_ROLLBACK_VERIFIED",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_VERIFICATION_ABSENT",
        (),
    ),
    (
        "G1-C19-SECURITY-RECOVERY-SIGNOFF",
        "ST1705_SECURITY_AND_RECOVERY_SIGNOFF_ELIGIBLE",
        "BLOCKED",
        "NOT_SIGNED_OFF",
        "BLOCKED_NON_ATTESTING_DEPENDENCY",
        (
            "repo://changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json",
        ),
    ),
    (
        "G1-C20-FORMAL-TST020",
        "FORMAL_TST020_COMPLETED_FOR_ACTUAL_PORTFOLIO",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_SUITE_ABSENT",
        ("repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",),
    ),
    (
        "G1-C21-FORMAL-TST032-STAGING",
        "FORMAL_TST032_EXECUTED_IN_STAGING",
        "NOT_EXECUTED",
        "NOT_EXECUTED",
        "FORMAL_SUITE_ABSENT",
        ("repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",),
    ),
    (
        "G1-C22-BLOCKING-DECISIONS",
        "ALL_APPLICABLE_BLOCKING_OPEN_DECISIONS_CLEARED",
        "BLOCKED",
        "ACTIVE_BLOCKING_DECISIONS_PRESENT",
        "CANONICAL_BLOCKER",
        ("repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",),
    ),
    (
        "G1-C23-HUMAN-GATE-APPROVAL",
        "PRODUCT_OWNER_GATE_APPROVAL_PRESENT",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "HUMAN_APPROVAL_ABSENT",
        (),
    ),
    (
        "G1-C24-TARGET-SNAPSHOT-CONTEXT",
        "TARGET_VERSION_ENVIRONMENT_TIME_DATA_AND_ARTIFACT_HASH_BOUND",
        "UNAVAILABLE",
        "UNAVAILABLE",
        "TARGET_SNAPSHOT_CONTEXT_ABSENT",
        (),
    ),
    (
        "G1-C25-GATE0-PREREQUISITE",
        "GATE0_AND_TECHNICAL_PILOT_PREREQUISITES_SIGNED_OFF",
        "BLOCKED",
        "BLOCKED",
        "BLOCKED_NON_ATTESTING_DEPENDENCY",
        (
            "repo://changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json",
        ),
    ),
)

INPUT_KEYS: Final = (
    "category_count",
    "intent_cluster_count",
    "article_count",
    "article_type_count",
    "quality_evaluated_article_count",
    "quality_passing_article_count",
    "minimum_quality_score",
    "critical_factual_error_count",
    "evidenced_claim_count",
    "verifiable_claim_count",
    "evidenced_major_claim_count",
    "major_claim_count",
    "fabricated_experience_count",
    "product_identity_error_count",
    "link_error_count",
    "first_pass_approved_count",
    "human_reviewed_count",
    "freshness_displayed_count",
    "freshness_eligible_article_count",
    "measurement_connected",
    "per_article_cost_measurable",
    "human_time_measurable",
    "change_history_audit_verified",
    "rollback_verified",
)


class Gate1DecisionError(RuntimeError):
    """Sanitized, fail-closed ST-1802 validation error."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"ST1802_ERROR code={code} field={field}")


class UniqueKeyLoader(yaml.SafeLoader):
    """YAML loader that rejects duplicate mapping keys."""


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
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def _fail(code: str, field: str) -> NoReturn:
    raise Gate1DecisionError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        _fail("INVALID_MAPPING", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_LIST", field)
    return value


def _closed(value: object, keys: tuple[str, ...], field: str) -> Mapping[str, Any]:
    item = _mapping(value, field)
    if tuple(item) != keys:
        _fail("UNKNOWN_OR_MISSING_FIELD", field)
    return item


def _exact(value: object, expected: object, field: str) -> None:
    if type(value) is not type(expected):
        _fail("EXACT_VALUE_MISMATCH", field)
    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        if tuple(observed) != tuple(expected):
            _fail("UNKNOWN_OR_MISSING_FIELD", field)
        for key, expected_value in expected.items():
            _exact(observed[key], expected_value, f"{field}.{key}")
        return
    if isinstance(expected, list):
        observed_list = _list(value, field)
        if len(observed_list) != len(expected):
            _fail("EXACT_VALUE_MISMATCH", field)
        for index, expected_value in enumerate(expected):
            _exact(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if value != expected:
        _fail("EXACT_VALUE_MISMATCH", field)


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
        _fail("INVALID_RELATIVE_PATH", field)


def _absolute_root(root: Path) -> Path:
    if not root.is_absolute():
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    try:
        resolved = root.resolve(strict=True)
    except OSError:
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    if resolved != root or not root.is_dir():
        _fail("REPOSITORY_ROOT_INVALID", "repository_root")
    return root


def _open_root(root: Path, field: str) -> int:
    absolute = _absolute_root(root)
    try:
        descriptor = os.open(
            absolute, os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW
        )
    except OSError:
        _fail("REPOSITORY_ROOT_INVALID", field)
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.geteuid():
        _close(descriptor)
        _fail("REPOSITORY_ROOT_INVALID", field)
    return descriptor


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
    descriptor = _open_root(root, field)
    try:
        for index, part in enumerate(relative.parts):
            final = index == len(relative.parts) - 1
            try:
                before = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
            except OSError:
                _fail("INPUT_OPEN_FAILED", field)
            if final:
                if (
                    not stat.S_ISREG(before.st_mode)
                    or before.st_uid != os.geteuid()
                    or before.st_nlink != 1
                    or stat.S_IMODE(before.st_mode) & 0o022
                ):
                    _fail("UNSAFE_FILE_TYPE", field)
                if before.st_size < 0 or before.st_size > MAX_INPUT_BYTES:
                    _fail("INPUT_SIZE_LIMIT", field)
                try:
                    leaf = os.open(
                        part,
                        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                        dir_fd=descriptor,
                    )
                except OSError:
                    _fail("INPUT_OPEN_FAILED", field)
                try:
                    opened = os.fstat(leaf)
                    if _identity(before) != _identity(opened):
                        _fail("INPUT_CHANGED", field)
                    chunks: list[bytes] = []
                    remaining = opened.st_size
                    while remaining:
                        chunk = os.read(leaf, min(remaining, READ_CHUNK_BYTES))
                        if not chunk:
                            _fail("INPUT_CHANGED", field)
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    if os.read(leaf, 1):
                        _fail("INPUT_CHANGED", field)
                    after = os.stat(part, dir_fd=descriptor, follow_symlinks=False)
                    if _identity(opened) != _identity(after):
                        _fail("INPUT_CHANGED", field)
                    return b"".join(chunks)
                finally:
                    _close(leaf)
            if (
                not stat.S_ISDIR(before.st_mode)
                or before.st_uid != os.geteuid()
                or stat.S_IMODE(before.st_mode) & 0o022
            ):
                _fail("UNSAFE_PATH_ANCESTOR", field)
            try:
                child = os.open(
                    part,
                    os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
                    dir_fd=descriptor,
                )
            except OSError:
                _fail("INPUT_OPEN_FAILED", field)
            opened_dir = os.fstat(child)
            if (before.st_dev, before.st_ino) != (
                opened_dir.st_dev,
                opened_dir.st_ino,
            ):
                _close(child)
                _fail("INPUT_CHANGED", field)
            _close(descriptor)
            descriptor = child
    finally:
        _close(descriptor)
    _fail("INPUT_OPEN_FAILED", field)


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
        value = json.loads(content.decode("utf-8"), object_pairs_hook=unique_pairs)
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(value, field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)
    try:
        text = content.decode("utf-8")
        if any(
            isinstance(token, (AliasToken, AnchorToken)) for token in yaml.scan(text)
        ):
            _fail("YAML_ALIAS_FORBIDDEN", field)
        value = yaml.load(text, Loader=UniqueKeyLoader)
    except Gate1DecisionError:
        raise
    except UnicodeError, yaml.YAMLError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


def _source_rows(paths: Mapping[str, str]) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path}", "sha256": digest} for path, digest in paths.items()
    ]


def _criteria() -> list[dict[str, object]]:
    return [
        {
            "criterion_id": criterion_id,
            "rule": rule,
            "status": status_value,
            "observed_value": observed,
            "evidence_classification": classification,
            "source_references": list(references),
        }
        for criterion_id, rule, status_value, observed, classification, references in _CRITERIA_ROWS
    ]


def _expected_document() -> dict[str, object]:
    return {
        "id": "RAOS-ST1802-GATE1-DECISION-001",
        "version": "1.0.0",
        "story_id": "ST-1802",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "classification": "LOCAL_BLOCKED_GATE1_DECISION_NON_ATTESTING",
        "acceptance_criteria_satisfied": False,
        "formal_verification": "NOT_EXECUTED",
    }


def _validate_source_bindings(contract: Mapping[str, Any]) -> None:
    _exact(
        contract.get("source_bindings"),
        _source_rows(EXPECTED_SOURCE_HASHES),
        "contract.source_bindings",
    )
    dependencies = _mapping(
        contract.get("dependency_bindings"), "contract.dependency_bindings"
    )
    if tuple(dependencies) != ("st_1801", "st_1705", "st_1704"):
        _fail("UNKNOWN_OR_MISSING_FIELD", "contract.dependency_bindings")
    expected_by_story = {
        "st_1801": (
            "ST-1801",
            "BLOCKED_SYNTHETIC_PORTFOLIO_PREDECESSOR",
            (
                (
                    "GENERATED_BLOCKED_PORTFOLIO",
                    "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json",
                ),
                (
                    "RUNTIME_MANIFEST",
                    "changes/st-1801/generated/runtime-manifest.v1.yaml",
                ),
                ("OWNER_GENERATOR", "scripts/build_st1801_portfolio_expansion.py"),
            ),
        ),
        "st_1705": (
            "ST-1705",
            "BLOCKED_SECURITY_RECOVERY_SIGNOFF_INPUT",
            (
                (
                    "GENERATED_BLOCKED_SIGNOFF",
                    "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json",
                ),
                ("MANIFEST", "changes/st-1705/manifest.yaml"),
            ),
        ),
        "st_1704": (
            "ST-1704",
            "FIVE_ARTICLE_AND_MEASUREMENT_NON_ATTESTING_INPUT",
            (
                (
                    "ARTICLE_COLLECTION",
                    "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json",
                ),
                (
                    "MEASUREMENT_CONTRACT",
                    "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json",
                ),
            ),
        ),
    }
    for key, (story_id, role, artifact_specs) in expected_by_story.items():
        binding = _closed(
            dependencies[key],
            ("story_id", "role", "artifacts"),
            f"contract.dependency_bindings.{key}",
        )
        _exact(
            binding.get("story_id"),
            story_id,
            f"contract.dependency_bindings.{key}.story_id",
        )
        _exact(binding.get("role"), role, f"contract.dependency_bindings.{key}.role")
        artifacts = _list(
            binding.get("artifacts"), f"contract.dependency_bindings.{key}.artifacts"
        )
        if len(artifacts) != len(artifact_specs):
            _fail(
                "EXACT_VALUE_MISMATCH", f"contract.dependency_bindings.{key}.artifacts"
            )
        for index, (kind, path) in enumerate(artifact_specs):
            expected = {
                "kind": kind,
                "uri": f"repo://{path}",
                "sha256": EXPECTED_DEPENDENCY_HASHES[path],
            }
            _exact(
                artifacts[index],
                expected,
                f"contract.dependency_bindings.{key}.artifacts[{index}]",
            )


def _validate_contract_structure(contract: Mapping[str, Any]) -> None:
    _closed(
        contract,
        (
            "document",
            "source_bindings",
            "dependency_bindings",
            "gate_definition",
            "status_vocabulary",
            "mandatory_criteria",
            "recorded_synthetic_harness",
            "decision",
            "authority_boundary",
            "execution_boundary",
            "evidence_boundary",
        ),
        "contract",
    )
    _exact(contract.get("document"), _expected_document(), "contract.document")
    _validate_source_bindings(contract)
    _exact(
        contract.get("gate_definition"),
        EXPECTED_GATE_DEFINITION,
        "contract.gate_definition",
    )
    _exact(
        contract.get("status_vocabulary"),
        list(STATUS_VOCABULARY),
        "contract.status_vocabulary",
    )
    _exact(
        contract.get("mandatory_criteria"), _criteria(), "contract.mandatory_criteria"
    )
    _exact(
        contract.get("recorded_synthetic_harness"),
        {
            "dependency_uri": (
                "repo://changes/st-1801/generated/"
                "portfolio-expansion.local-blocked.v1.json"
            ),
            "dependency_sha256": EXPECTED_DEPENDENCY_HASHES[
                "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
            ],
            "dependency_decision": "BLOCKED",
            "dependency_eligibility": "NOT_ELIGIBLE",
            "planned_synthetic_placeholder_count": 30,
            "actual_article_count": "UNAVAILABLE",
            "placeholders_are_actual_articles": False,
            "schema_uri": f"repo://{FIXTURE_SCHEMA_PATH.as_posix()}",
            "schema_sha256": FIXTURE_SCHEMA_SHA256,
            "fixture_uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "fixture_sha256": FIXTURE_SHA256,
            "schema_behavior": "CLOSED_ADDITIONAL_PROPERTIES_FALSE",
            "classification": SYNTHETIC_CLASSIFICATION,
            "fixed_path_only": True,
            "dynamic_input_path": "FORBIDDEN",
            "formal_evidence_eligible": False,
            "gate_evidence_eligible": False,
            "story_acceptance_eligible": False,
        },
        "contract.recorded_synthetic_harness",
    )
    _exact(
        contract.get("decision"),
        {
            "overall": "BLOCKED",
            "eligibility": "NOT_ELIGIBLE",
            "mandatory_criteria_satisfied": False,
            "next_gate_eligible": False,
            "qualifying_evidence_references": [],
            "approval_artifacts": [],
        },
        "contract.decision",
    )
    _exact(
        contract.get("authority_boundary"),
        {
            "external_authority": "NONE",
            "formal_evidence_acceptance_authority": "NONE",
            "gate_approval_authority": "NONE",
            "status_propose_authority": "NONE",
            "status_apply_authority": "NONE",
            "article_creation_authority": "NONE",
            "article_approval_authority": "NONE",
            "publication_authority": "NONE",
            "staging_authority": "NONE",
            "release_authority": "NONE",
            "deployment_authority": "NONE",
            "production_authority": "NONE",
        },
        "contract.authority_boundary",
    )
    _exact(
        contract.get("execution_boundary"),
        {
            "local_generation_only": True,
            "input_size_limit_bytes": MAX_INPUT_BYTES,
            "input_read_model": "ROOT_FD_DESCRIPTOR_RELATIVE_CAPTURED_LEAF",
            "writer_model": "SINGLE_PROCESS_DIRECTORY_LOCK",
            "output_transaction": "THREE_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "check_pending_recovery_behavior": "READ_ONLY_REJECT",
            "environment_access": "FORBIDDEN",
            "subprocess_execution": "FORBIDDEN",
            "network_access": "FORBIDDEN",
            "credential_access": "FORBIDDEN",
            "provider_calls": "FORBIDDEN",
            "external_action_count": 0,
        },
        "contract.execution_boundary",
    )
    _exact(
        contract.get("evidence_boundary"),
        {
            "classification": "LOCAL_BLOCKED_GATE1_DECISION_NON_ATTESTING",
            "st_1801_actual_portfolio": "UNAVAILABLE",
            "actual_quality_observations": "UNAVAILABLE",
            "actual_claim_coverage_observations": "UNAVAILABLE",
            "actual_first_pass_approval_observations": "UNAVAILABLE",
            "actual_measurement_observations": "UNAVAILABLE",
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "gate_approval": "NOT_EXECUTED",
            "publication": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "deployment": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "gate_pass_claim": False,
            "story_acceptance": False,
            "canonical_status": "UNCHANGED",
        },
        "contract.evidence_boundary",
    )


def _validate_hashes(root: Path) -> None:
    for path, digest in {
        **EXPECTED_SOURCE_HASHES,
        **EXPECTED_DEPENDENCY_HASHES,
    }.items():
        if _sha256(_read(root, Path(path), f"input.{path}")) != digest:
            _fail("PINNED_INPUT_DRIFT", f"input.{path}")
    if (
        _sha256(_read(root, FIXTURE_SCHEMA_PATH, "fixture_schema"))
        != FIXTURE_SCHEMA_SHA256
    ):
        _fail("PINNED_INPUT_DRIFT", "fixture_schema")
    if _sha256(_read(root, FIXTURE_PATH, "fixture")) != FIXTURE_SHA256:
        _fail("PINNED_INPUT_DRIFT", "fixture")


def _find_by_id(rows: object, identity: str, field: str) -> Mapping[str, Any]:
    found = [
        _mapping(row, f"{field}.row")
        for row in _list(rows, field)
        if isinstance(row, Mapping) and row.get("id") == identity
    ]
    if len(found) != 1:
        _fail("CANONICAL_SEMANTIC_DRIFT", field)
    return found[0]


def _validate_canonical_semantics(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "backlog",
    )
    story = _find_by_id(backlog.get("stories"), "ST-1802", "backlog.stories")
    for field, expected_story_value in {
        "title": "GATE-1 decision",
        "objective": "Editorial/technical pilotを判定",
        "depends_on": ["ST-1801"],
        "deliverables": ["GATE-1 pack"],
        "acceptance_criteria": ["all mandatory criteria"],
        "test_suites": ["TST-032"],
        "implementation_status": "NOT_STARTED",
        "verification_status": "NOT_EXECUTED",
    }.items():
        _exact(story.get(field), expected_story_value, f"backlog.ST-1802.{field}")
    suites = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    tst032 = _find_by_id(suites.get("suites"), "TST-032", "test_catalog.suites")
    for field, expected_suite_value in {
        "name": "GATE acceptance pack",
        "layer": "acceptance",
        "release_blocking": True,
        "environments": ["staging"],
        "execution_status": "NOT_EXECUTED",
    }.items():
        _exact(
            tst032.get(field),
            expected_suite_value,
            f"test_catalog.TST-032.{field}",
        )
    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "open_decisions",
    )
    items = _list(decisions.get("items"), "open_decisions.items")
    blockers = [
        row for row in items if isinstance(row, Mapping) and row.get("blocking") is True
    ]
    if len(blockers) != 14:
        _fail("CANONICAL_SEMANTIC_DRIFT", "open_decisions.blockers")
    od005 = _find_by_id(items, "OD-005", "open_decisions.items")
    _exact(
        od005.get("required_by"),
        "GATE-1 and contribution profit",
        "open_decisions.OD-005.required_by",
    )
    _exact(od005.get("blocking"), True, "open_decisions.OD-005.blocking")


def _validate_st1801(record: Mapping[str, Any]) -> None:
    _exact(
        record.get("classification"),
        "LOCAL_BLOCKED_SYNTHETIC_PORTFOLIO_PLAN_NON_ATTESTING",
        "st1801.classification",
    )
    story = _mapping(record.get("story"), "st1801.story")
    _exact(story.get("id"), "ST-1801", "st1801.story.id")
    decision = _mapping(record.get("decision"), "st1801.decision")
    _exact(decision.get("overall"), "BLOCKED", "st1801.decision.overall")
    _exact(
        decision.get("dependency_eligibility"),
        "NOT_ELIGIBLE",
        "st1801.decision.dependency_eligibility",
    )
    _exact(
        decision.get("downstream_gate_1_eligible"),
        False,
        "st1801.decision.downstream_gate_1_eligible",
    )
    _exact(
        decision.get("qualifying_evidence_references"),
        [],
        "st1801.decision.qualifying_evidence_references",
    )
    _exact(
        decision.get("actual_observations"), [], "st1801.decision.actual_observations"
    )
    portfolio = _mapping(record.get("portfolio"), "st1801.portfolio")
    for field, expected in {
        "actual_category": "UNAVAILABLE",
        "program": PROGRAM,
        "minimum_slot_count": 30,
        "maximum_slot_count": 45,
        "planned_placeholder_slot_count": 30,
        "actual_materialized_article_count": "UNAVAILABLE",
        "actual_approved_article_count": "UNAVAILABLE",
        "actual_published_article_count": "UNAVAILABLE",
    }.items():
        _exact(portfolio.get(field), expected, f"st1801.portfolio.{field}")
    slots = _list(portfolio.get("planned_slots"), "st1801.portfolio.planned_slots")
    if len(slots) != 30:
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1801.portfolio.planned_slots")
    category_refs: set[str] = set()
    programs: set[str] = set()
    identities: set[str] = set()
    for index, value in enumerate(slots):
        slot = _mapping(value, f"st1801.portfolio.planned_slots[{index}]")
        category = slot.get("category_ref")
        program = slot.get("program")
        identity = slot.get("placeholder_slot_id")
        if (
            type(category) is not str
            or type(program) is not str
            or type(identity) is not str
        ):
            _fail(
                "DEPENDENCY_SEMANTIC_DRIFT", f"st1801.portfolio.planned_slots[{index}]"
            )
        category_refs.add(category)
        programs.add(program)
        identities.add(identity)
        for field, expected in {
            "identity_classification": "SYNTHETIC_PLACEHOLDER_NOT_AN_ARTICLE",
            "creation_status": "NOT_CREATED",
            "approval_status": "NOT_APPROVED",
            "publication_status": "NOT_PUBLIC",
            "article_id": None,
            "quality_score": "UNAVAILABLE",
            "major_claim_coverage_percent": "UNAVAILABLE",
            "actual_observations": [],
            "evidence_references": [],
        }.items():
            _exact(
                slot.get(field),
                expected,
                f"st1801.portfolio.planned_slots[{index}].{field}",
            )
    if (
        len(category_refs) != 1
        or len(programs) != 1
        or programs != {PROGRAM}
        or len(identities) != 30
    ):
        _fail("MIXED_OR_DUPLICATE_PORTFOLIO_INPUT", "st1801.portfolio.planned_slots")
    authority = _mapping(record.get("authority_boundary"), "st1801.authority_boundary")
    if any(value != "NONE" for value in authority.values()):
        _fail("AUTHORITY_ESCALATION", "st1801.authority_boundary")
    evidence = _mapping(record.get("evidence_boundary"), "st1801.evidence_boundary")
    _exact(
        evidence.get("formal_tst_020"),
        "NOT_EXECUTED",
        "st1801.evidence_boundary.formal_tst_020",
    )
    _exact(
        evidence.get("formal_tst_032"),
        "NOT_EXECUTED",
        "st1801.evidence_boundary.formal_tst_032",
    )


def _validate_dependencies(root: Path) -> None:
    st1801 = _load_json(
        root,
        Path("changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"),
        "st1801",
    )
    _validate_st1801(st1801)
    st1801_manifest = _load_yaml(
        root,
        Path("changes/st-1801/generated/runtime-manifest.v1.yaml"),
        "st1801_manifest",
    )
    _exact(st1801_manifest.get("story_id"), "ST-1801", "st1801_manifest.story_id")
    generated = _list(
        st1801_manifest.get("generated_artifacts"),
        "st1801_manifest.generated_artifacts",
    )
    if len(generated) != 1:
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1801_manifest.generated_artifacts")
    _exact(
        _mapping(generated[0], "st1801_manifest.generated_artifacts[0]").get("sha256"),
        EXPECTED_DEPENDENCY_HASHES[
            "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
        ],
        "st1801_manifest.generated_artifacts[0].sha256",
    )
    st1705 = _load_json(
        root,
        Path(
            "changes/st-1705/generated/pilot-security-recovery-signoff.local-blocked.v1.json"
        ),
        "st1705",
    )
    _exact(
        st1705.get("classification"),
        "LOCAL_BLOCKED_PILOT_SIGNOFF_NON_ATTESTING",
        "st1705.classification",
    )
    signoff = _mapping(st1705.get("decision"), "st1705.decision")
    for field, expected in {
        "overall": "BLOCKED",
        "security_sign_off": "NOT_SIGNED_OFF",
        "recovery_sign_off": "NOT_SIGNED_OFF",
        "downstream_st_1801_eligibility": "NOT_ELIGIBLE",
        "qualifying_evidence_references": [],
        "approval_artifacts": [],
    }.items():
        _exact(signoff.get(field), expected, f"st1705.decision.{field}")
    if any(
        value != "NONE"
        for value in _mapping(
            st1705.get("authority_boundary"), "st1705.authority_boundary"
        ).values()
    ):
        _fail("AUTHORITY_ESCALATION", "st1705.authority_boundary")
    articles = _load_json(
        root,
        Path("changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"),
        "st1704_articles",
    )
    _exact(articles.get("story_id"), "ST-1704", "st1704_articles.story_id")
    _exact(
        articles.get("publication_authority"),
        "NONE",
        "st1704_articles.publication_authority",
    )
    article_rows = _list(articles.get("articles"), "st1704_articles.articles")
    if len(article_rows) != 5 or any(
        _mapping(row, "st1704_articles.article").get("publication_authority") != "NONE"
        for row in article_rows
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1704_articles.articles")
    measurement = _load_json(
        root,
        Path("changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"),
        "st1704_measurement",
    )
    _exact(measurement.get("program"), PROGRAM, "st1704_measurement.program")
    guardrails = _mapping(
        measurement.get("guardrails"), "st1704_measurement.guardrails"
    )
    for field in (
        "automatic_publication",
        "article_html_mutation",
        "product_selection_mutation",
        "recommendation_order_mutation",
    ):
        _exact(guardrails.get(field), False, f"st1704_measurement.guardrails.{field}")


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    _validate_hashes(root)
    _validate_canonical_semantics(root)
    _validate_dependencies(root)
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    _validate_contract_structure(contract)
    return contract


def _count(value: object, field: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0 or value > 1_000_000:
        _fail("INVALID_COUNT", field)
    return value


def _score(value: object, field: str) -> Decimal | None:
    if value is None:
        return None
    if type(value) is not str or SCORE_PATTERN.fullmatch(value) is None:
        _fail("INVALID_SCORE", field)
    try:
        result = Decimal(value)
    except InvalidOperation:
        _fail("INVALID_SCORE", field)
    if result < 0 or result > 100 or not result.is_finite():
        _fail("INVALID_SCORE", field)
    return result


def _boolean(value: object, field: str) -> str:
    if value is None:
        return "UNAVAILABLE"
    if type(value) is not bool:
        _fail("INVALID_BOOLEAN", field)
    return "PASS" if value else "FAIL"


def _count_equals(value: object, expected: int, field: str) -> str:
    observed = _count(value, field)
    return (
        "UNAVAILABLE"
        if observed is None
        else ("PASS" if observed == expected else "FAIL")
    )


def _count_range(value: object, minimum: int, maximum: int, field: str) -> str:
    observed = _count(value, field)
    return (
        "UNAVAILABLE"
        if observed is None
        else ("PASS" if minimum <= observed <= maximum else "FAIL")
    )


def _zero(value: object, field: str) -> str:
    observed = _count(value, field)
    return "UNAVAILABLE" if observed is None else ("PASS" if observed == 0 else "FAIL")


def _ratio(
    numerator: object,
    denominator: object,
    required_numerator: int,
    required_denominator: int,
    field: str,
) -> str:
    num = _count(numerator, f"{field}.numerator")
    den = _count(denominator, f"{field}.denominator")
    if num is None or den is None or den == 0:
        return "UNAVAILABLE"
    if num > den:
        _fail("INVALID_RATIO_COUNTS", field)
    return "PASS" if num * required_denominator >= den * required_numerator else "FAIL"


def evaluate_recorded_synthetic(value: object) -> dict[str, object]:
    inputs = _closed(value, INPUT_KEYS, "synthetic.input")
    article_count = _count(inputs.get("article_count"), "synthetic.input.article_count")
    evaluated = _count(
        inputs.get("quality_evaluated_article_count"),
        "synthetic.input.quality_evaluated_article_count",
    )
    passing = _count(
        inputs.get("quality_passing_article_count"),
        "synthetic.input.quality_passing_article_count",
    )
    score = _score(
        inputs.get("minimum_quality_score"), "synthetic.input.minimum_quality_score"
    )
    if (
        article_count is None
        or evaluated is None
        or passing is None
        or score is None
        or article_count == 0
    ):
        quality_status = "UNAVAILABLE"
    else:
        if evaluated > article_count or passing > evaluated:
            _fail("INVALID_QUALITY_COUNTS", "synthetic.input.quality")
        quality_status = (
            "PASS"
            if evaluated == article_count
            and passing == article_count
            and score >= QUALITY_THRESHOLD
            else "FAIL"
        )
    rows = [
        (
            "SYN-G1-C01-SINGLE-CATEGORY",
            _count_equals(
                inputs.get("category_count"), 1, "synthetic.input.category_count"
            ),
        ),
        (
            "SYN-G1-C02-INTENT-CLUSTERS",
            _count_equals(
                inputs.get("intent_cluster_count"),
                3,
                "synthetic.input.intent_cluster_count",
            ),
        ),
        (
            "SYN-G1-C03-ARTICLE-COUNT",
            _count_range(
                inputs.get("article_count"), 30, 45, "synthetic.input.article_count"
            ),
        ),
        (
            "SYN-G1-C04-ARTICLE-TYPES",
            _count_range(
                inputs.get("article_type_count"),
                3,
                5,
                "synthetic.input.article_type_count",
            ),
        ),
        ("SYN-G1-C05-ALL-QUALITY-85", quality_status),
        (
            "SYN-G1-C06-CRITICAL-FACTUAL-ERRORS",
            _zero(
                inputs.get("critical_factual_error_count"),
                "synthetic.input.critical_factual_error_count",
            ),
        ),
        (
            "SYN-G1-C07-ALL-CLAIM-COVERAGE",
            _ratio(
                inputs.get("evidenced_claim_count"),
                inputs.get("verifiable_claim_count"),
                95,
                100,
                "synthetic.input.all_claim_coverage",
            ),
        ),
        (
            "SYN-G1-C08-MAJOR-CLAIM-COVERAGE",
            _ratio(
                inputs.get("evidenced_major_claim_count"),
                inputs.get("major_claim_count"),
                1,
                1,
                "synthetic.input.major_claim_coverage",
            ),
        ),
        (
            "SYN-G1-C09-FABRICATED-EXPERIENCE",
            _zero(
                inputs.get("fabricated_experience_count"),
                "synthetic.input.fabricated_experience_count",
            ),
        ),
        (
            "SYN-G1-C10-PRODUCT-IDENTITY",
            _zero(
                inputs.get("product_identity_error_count"),
                "synthetic.input.product_identity_error_count",
            ),
        ),
        (
            "SYN-G1-C11-LINK-ERRORS",
            _zero(inputs.get("link_error_count"), "synthetic.input.link_error_count"),
        ),
        (
            "SYN-G1-C12-FIRST-PASS-HUMAN-APPROVAL",
            _ratio(
                inputs.get("first_pass_approved_count"),
                inputs.get("human_reviewed_count"),
                80,
                100,
                "synthetic.input.first_pass_approval",
            ),
        ),
        (
            "SYN-G1-C13-FRESHNESS-TIMESTAMPS",
            _ratio(
                inputs.get("freshness_displayed_count"),
                inputs.get("freshness_eligible_article_count"),
                1,
                1,
                "synthetic.input.freshness_coverage",
            ),
        ),
        (
            "SYN-G1-C14-MEASUREMENT-CONNECTED",
            _boolean(
                inputs.get("measurement_connected"),
                "synthetic.input.measurement_connected",
            ),
        ),
        (
            "SYN-G1-C15-PER-ARTICLE-COST",
            _boolean(
                inputs.get("per_article_cost_measurable"),
                "synthetic.input.per_article_cost_measurable",
            ),
        ),
        (
            "SYN-G1-C16-HUMAN-TIME",
            _boolean(
                inputs.get("human_time_measurable"),
                "synthetic.input.human_time_measurable",
            ),
        ),
        (
            "SYN-G1-C17-CHANGE-HISTORY-AUDIT",
            _boolean(
                inputs.get("change_history_audit_verified"),
                "synthetic.input.change_history_audit_verified",
            ),
        ),
        (
            "SYN-G1-C18-ROLLBACK",
            _boolean(
                inputs.get("rollback_verified"), "synthetic.input.rollback_verified"
            ),
        ),
    ]
    statuses = [status_value for _, status_value in rows]
    overall = (
        "FAIL"
        if "FAIL" in statuses
        else ("UNAVAILABLE" if "UNAVAILABLE" in statuses else "PASS")
    )
    return {
        "classification": SYNTHETIC_CLASSIFICATION,
        "overall_status": overall,
        "criterion_results": [
            {"criterion_id": criterion_id, "status": status_value}
            for criterion_id, status_value in rows
        ],
        "formal_evidence_eligible": False,
        "gate_evidence_eligible": False,
        "story_acceptance_eligible": False,
        "article_approval_eligible": False,
        "publication_eligible": False,
    }


def _validate_fixture(root: Path) -> list[dict[str, object]]:
    fixture = _closed(
        _load_json(root, FIXTURE_PATH, "fixture"),
        ("schema", "classification", "program", "cases"),
        "fixture",
    )
    _exact(
        fixture.get("schema"),
        "ST1802_RECORDED_SYNTHETIC_GATE1_EVALUATION_V1",
        "fixture.schema",
    )
    _exact(
        fixture.get("classification"),
        SYNTHETIC_CLASSIFICATION,
        "fixture.classification",
    )
    _exact(fixture.get("program"), PROGRAM, "fixture.program")
    cases = _list(fixture.get("cases"), "fixture.cases")
    if not 1 <= len(cases) <= 16:
        _fail("FIXTURE_CASE_COUNT", "fixture.cases")
    seen: set[str] = set()
    results: list[dict[str, object]] = []
    for index, value in enumerate(cases):
        case = _closed(
            value,
            ("case_id", "input", "expected_overall_status"),
            f"fixture.cases[{index}]",
        )
        case_id = case.get("case_id")
        if (
            type(case_id) is not str
            or re.fullmatch(r"synthetic-[a-z0-9-]{1,64}", case_id) is None
            or case_id in seen
        ):
            _fail("INVALID_CASE_ID", f"fixture.cases[{index}].case_id")
        seen.add(case_id)
        result = evaluate_recorded_synthetic(case.get("input"))
        expected = case.get("expected_overall_status")
        if (
            expected not in {"PASS", "FAIL", "UNAVAILABLE"}
            or result["overall_status"] != expected
        ):
            _fail("FIXTURE_EXPECTATION_MISMATCH", f"fixture.cases[{index}]")
        results.append({"case_id": case_id, **result})
    return results


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    ).encode("utf-8")


def _evaluation_record(results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "story_id": "ST-1802",
        "classification": SYNTHETIC_CLASSIFICATION,
        "program": PROGRAM,
        "fixture": {
            "uri": f"repo://{FIXTURE_PATH.as_posix()}",
            "sha256": FIXTURE_SHA256,
            "schema_uri": f"repo://{FIXTURE_SCHEMA_PATH.as_posix()}",
            "schema_sha256": FIXTURE_SCHEMA_SHA256,
        },
        "dependency_context": {
            "story_id": "ST-1801",
            "uri": (
                "repo://changes/st-1801/generated/"
                "portfolio-expansion.local-blocked.v1.json"
            ),
            "sha256": EXPECTED_DEPENDENCY_HASHES[
                "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
            ],
            "decision": "BLOCKED",
            "dependency_eligibility": "NOT_ELIGIBLE",
            "planned_synthetic_placeholder_count": 30,
            "actual_article_count": "UNAVAILABLE",
            "placeholders_are_actual_articles": False,
        },
        "results": results,
        "qualifying_evidence_references": [],
        "formal_evidence_eligible": False,
        "gate_evidence_eligible": False,
        "story_acceptance_eligible": False,
        "authority": "NONE",
    }


def validate_evaluation_record(
    record: Mapping[str, Any],
    *,
    expected_results: list[dict[str, object]] | None = None,
) -> None:
    _closed(
        record,
        (
            "schema_version",
            "story_id",
            "classification",
            "program",
            "fixture",
            "dependency_context",
            "results",
            "qualifying_evidence_references",
            "formal_evidence_eligible",
            "gate_evidence_eligible",
            "story_acceptance_eligible",
            "authority",
        ),
        "evaluation_record",
    )
    for field, expected in {
        "schema_version": "1.0.0",
        "story_id": "ST-1802",
        "classification": SYNTHETIC_CLASSIFICATION,
        "program": PROGRAM,
        "qualifying_evidence_references": [],
        "formal_evidence_eligible": False,
        "gate_evidence_eligible": False,
        "story_acceptance_eligible": False,
        "authority": "NONE",
    }.items():
        _exact(record.get(field), expected, f"evaluation_record.{field}")
    results = _list(record.get("results"), "evaluation_record.results")
    if not results:
        _fail("EVALUATION_RESULTS_EMPTY", "evaluation_record.results")
    for index, value in enumerate(results):
        result = _mapping(value, f"evaluation_record.results[{index}]")
        _exact(
            result.get("classification"),
            SYNTHETIC_CLASSIFICATION,
            f"evaluation_record.results[{index}].classification",
        )
        for field in (
            "formal_evidence_eligible",
            "gate_evidence_eligible",
            "story_acceptance_eligible",
            "article_approval_eligible",
            "publication_eligible",
        ):
            _exact(
                result.get(field), False, f"evaluation_record.results[{index}].{field}"
            )
    if expected_results is None:
        expected_results = _validate_fixture(REPO_ROOT)
    _exact(record, _evaluation_record(expected_results), "evaluation_record")


def _criterion_output(row: Mapping[str, Any]) -> dict[str, object]:
    return {
        **dict(row),
        "qualifying_evidence_references": [],
        "qualifies_as_gate_evidence": False,
    }


def _criteria_summary(criteria: list[dict[str, object]]) -> dict[str, object]:
    counts = {status_value: 0 for status_value in STATUS_VOCABULARY}
    for row in criteria:
        status_value = row["status"]
        if type(status_value) is not str or status_value not in counts:
            _fail("STATUS_VOCABULARY_VIOLATION", "criteria.status")
        counts[status_value] += 1
    return {
        "mandatory_criterion_count": len(criteria),
        "status_counts": counts,
        "all_mandatory_pass": False,
        "gate_readiness": "UNAVAILABLE",
        "reason": "MISSING_INELIGIBLE_BLOCKED_OR_NOT_EXECUTED_CRITERIA_PRESENT",
    }


def _gate_pack(
    contract: Mapping[str, Any], evaluation_bytes: bytes
) -> dict[str, object]:
    criteria = [
        _criterion_output(_mapping(row, "contract.mandatory_criteria.row"))
        for row in _list(
            contract.get("mandatory_criteria"), "contract.mandatory_criteria"
        )
    ]
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": f"repo://{GENERATOR_PATH.as_posix()}",
            "command": GENERATION_COMMAND,
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
        },
        "story": {
            "id": "ST-1802",
            "scope": "LOCAL_BLOCKED_GATE1_DECISION_ONLY",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "classification": "LOCAL_BLOCKED_GATE1_DECISION_NON_ATTESTING",
        "source_bindings": contract["source_bindings"],
        "dependency_bindings": contract["dependency_bindings"],
        "gate_definition": contract["gate_definition"],
        "dependency_state": {
            "st_1801_decision": "BLOCKED",
            "st_1801_dependency_eligibility": "NOT_ELIGIBLE",
            "st_1801_downstream_gate_1_eligible": False,
            "st_1801_planned_synthetic_placeholder_count": 30,
            "st_1801_actual_article_count": "UNAVAILABLE",
            "st_1705_security_sign_off": "NOT_SIGNED_OFF",
            "st_1705_recovery_sign_off": "NOT_SIGNED_OFF",
            "st_1704_tracked_article_packet_count": 5,
            "st_1704_actual_pilot_observations": "UNAVAILABLE",
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
        },
        "mandatory_criteria": criteria,
        "criteria_summary": _criteria_summary(criteria),
        "recorded_synthetic_harness": {
            "classification": SYNTHETIC_CLASSIFICATION,
            "dependency_uri": (
                "repo://changes/st-1801/generated/"
                "portfolio-expansion.local-blocked.v1.json"
            ),
            "dependency_sha256": EXPECTED_DEPENDENCY_HASHES[
                "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
            ],
            "dependency_decision": "BLOCKED",
            "dependency_eligibility": "NOT_ELIGIBLE",
            "planned_synthetic_placeholder_count": 30,
            "actual_article_count": "UNAVAILABLE",
            "placeholders_are_actual_articles": False,
            "output_uri": f"repo://{EVALUATION_PATH.as_posix()}",
            "output_sha256": _sha256(evaluation_bytes),
            "contains_synthetic_pass_case": True,
            "qualifies_as_article_evidence": False,
            "qualifies_as_story_evidence": False,
            "qualifies_as_formal_tst_032": False,
            "qualifies_as_gate_evidence": False,
        },
        "blockers": [
            "ST1801_ACTUAL_PORTFOLIO_UNAVAILABLE",
            "ST1801_DEPENDENCY_NOT_ELIGIBLE",
            "SYNTHETIC_PLACEHOLDERS_NOT_ARTICLES",
            "ACTUAL_QUALITY_AND_CLAIM_OBSERVATIONS_UNAVAILABLE",
            "ACTUAL_APPROVAL_COST_TIME_AND_MEASUREMENT_OBSERVATIONS_UNAVAILABLE",
            "FORMAL_TST020_NOT_EXECUTED",
            "FORMAL_TST032_STAGING_NOT_EXECUTED",
            "ST1705_SECURITY_RECOVERY_SIGNOFF_BLOCKED",
            "ACTIVE_BLOCKING_OPEN_DECISIONS",
            "TARGET_SNAPSHOT_CONTEXT_UNAVAILABLE",
            "HUMAN_GATE_APPROVAL_UNAVAILABLE",
        ],
        "decision": contract["decision"],
        "authority_boundary": contract["authority_boundary"],
        "execution_boundary": contract["execution_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "actual_observations": [],
        "qualifying_evidence_references": [],
        "prohibited_interpretations": [
            "THIRTY_SYNTHETIC_PLACEHOLDERS_ARE_NOT_THIRTY_ACTUAL_ARTICLES",
            "RECORDED_SYNTHETIC_PASS_IS_NOT_FORMAL_OR_GATE_EVIDENCE",
            "FIVE_TRACKED_ARTICLE_PACKETS_ARE_NOT_ACTUAL_PILOT_OBSERVATIONS",
            "MEASUREMENT_CONTRACT_IS_NOT_CONNECTED_MEASUREMENT_EVIDENCE",
            "MISSING_VALUES_ARE_NOT_ZERO_OR_PASS",
            "LOCAL_GENERATION_IS_NOT_TST020_OR_TST032",
            "BLOCKED_DECISION_IS_NOT_GATE_APPROVAL",
            "NO_STATUS_PUBLICATION_STAGING_RELEASE_DEPLOYMENT_OR_PRODUCTION_AUTHORITY",
        ],
    }


def validate_gate_pack(
    pack: Mapping[str, Any],
    *,
    expected_contract: Mapping[str, Any] | None = None,
    expected_evaluation_bytes: bytes | None = None,
) -> None:
    _closed(
        pack,
        (
            "schema_version",
            "generator",
            "story",
            "classification",
            "source_bindings",
            "dependency_bindings",
            "gate_definition",
            "dependency_state",
            "mandatory_criteria",
            "criteria_summary",
            "recorded_synthetic_harness",
            "blockers",
            "decision",
            "authority_boundary",
            "execution_boundary",
            "evidence_boundary",
            "actual_observations",
            "qualifying_evidence_references",
            "prohibited_interpretations",
        ),
        "gate_pack",
    )
    _exact(pack.get("schema_version"), "1.0.0", "gate_pack.schema_version")
    _exact(
        pack.get("classification"),
        "LOCAL_BLOCKED_GATE1_DECISION_NON_ATTESTING",
        "gate_pack.classification",
    )
    story = _mapping(pack.get("story"), "gate_pack.story")
    _exact(story.get("id"), "ST-1802", "gate_pack.story.id")
    _exact(
        story.get("acceptance_criteria_satisfied"),
        False,
        "gate_pack.story.acceptance_criteria_satisfied",
    )
    decision = _mapping(pack.get("decision"), "gate_pack.decision")
    _exact(decision.get("overall"), "BLOCKED", "gate_pack.decision.overall")
    _exact(
        decision.get("eligibility"), "NOT_ELIGIBLE", "gate_pack.decision.eligibility"
    )
    _exact(
        decision.get("mandatory_criteria_satisfied"),
        False,
        "gate_pack.decision.mandatory_criteria_satisfied",
    )
    _exact(
        decision.get("qualifying_evidence_references"),
        [],
        "gate_pack.decision.qualifying_evidence_references",
    )
    criteria = _list(pack.get("mandatory_criteria"), "gate_pack.mandatory_criteria")
    if len(criteria) != len(_CRITERIA_ROWS):
        _fail("MANDATORY_CRITERIA_DRIFT", "gate_pack.mandatory_criteria")
    seen: set[str] = set()
    for index, value in enumerate(criteria):
        row = _closed(
            value,
            (
                "criterion_id",
                "rule",
                "status",
                "observed_value",
                "evidence_classification",
                "source_references",
                "qualifying_evidence_references",
                "qualifies_as_gate_evidence",
            ),
            f"gate_pack.mandatory_criteria[{index}]",
        )
        criterion_id = row.get("criterion_id")
        if type(criterion_id) is not str or criterion_id in seen:
            _fail(
                "MANDATORY_CRITERIA_DRIFT",
                f"gate_pack.mandatory_criteria[{index}].criterion_id",
            )
        seen.add(criterion_id)
        status_value = row.get("status")
        if status_value not in STATUS_VOCABULARY or status_value == "PASS":
            _fail(
                "SYNTHETIC_OR_MISSING_EVIDENCE_PROMOTION",
                f"gate_pack.mandatory_criteria[{index}].status",
            )
        _exact(
            row.get("qualifying_evidence_references"),
            [],
            f"gate_pack.mandatory_criteria[{index}].qualifying_evidence_references",
        )
        _exact(
            row.get("qualifies_as_gate_evidence"),
            False,
            f"gate_pack.mandatory_criteria[{index}].qualifies_as_gate_evidence",
        )
    _exact(pack.get("actual_observations"), [], "gate_pack.actual_observations")
    _exact(
        pack.get("qualifying_evidence_references"),
        [],
        "gate_pack.qualifying_evidence_references",
    )
    authority = _mapping(pack.get("authority_boundary"), "gate_pack.authority_boundary")
    if any(value != "NONE" for value in authority.values()):
        _fail("AUTHORITY_ESCALATION", "gate_pack.authority_boundary")
    harness = _mapping(
        pack.get("recorded_synthetic_harness"), "gate_pack.recorded_synthetic_harness"
    )
    for field in (
        "qualifies_as_article_evidence",
        "qualifies_as_story_evidence",
        "qualifies_as_formal_tst_032",
        "qualifies_as_gate_evidence",
    ):
        _exact(
            harness.get(field), False, f"gate_pack.recorded_synthetic_harness.{field}"
        )
    evidence = _mapping(pack.get("evidence_boundary"), "gate_pack.evidence_boundary")
    _exact(
        evidence.get("formal_tst_020"),
        "NOT_EXECUTED",
        "gate_pack.evidence_boundary.formal_tst_020",
    )
    _exact(
        evidence.get("formal_tst_032"),
        "NOT_EXECUTED",
        "gate_pack.evidence_boundary.formal_tst_032",
    )
    _exact(
        evidence.get("gate_pass_claim"),
        False,
        "gate_pack.evidence_boundary.gate_pass_claim",
    )
    if expected_contract is None:
        expected_contract = load_contract(REPO_ROOT)
    if expected_evaluation_bytes is None:
        expected_results = _validate_fixture(REPO_ROOT)
        expected_evaluation_bytes = _json_bytes(_evaluation_record(expected_results))
    _exact(
        pack,
        _gate_pack(expected_contract, expected_evaluation_bytes),
        "gate_pack",
    )


def _source_artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, f"source_artifact.{relative.as_posix()}")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, evaluation_bytes: bytes, pack_bytes: bytes) -> bytes:
    manifest = {
        "story_id": "ST-1802",
        "schema_version": 1,
        "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
        "generation_command": GENERATION_COMMAND,
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_source_artifact(root, path) for path in SOURCE_PATHS],
        "bound_input_count": len(EXPECTED_SOURCE_HASHES)
        + len(EXPECTED_DEPENDENCY_HASHES),
        "bound_inputs": [
            *[
                {
                    "uri": f"repo://{path}",
                    "sha256": digest,
                    "classification": "CANONICAL_OR_GATE_AUTHORITY",
                }
                for path, digest in EXPECTED_SOURCE_HASHES.items()
            ],
            *[
                {
                    "uri": f"repo://{path}",
                    "sha256": digest,
                    "classification": "NON_ATTESTING_DEPENDENCY_INPUT",
                }
                for path, digest in EXPECTED_DEPENDENCY_HASHES.items()
            ],
        ],
        "generated_artifact_count": 2,
        "generated_artifacts": [
            {
                "uri": f"repo://{EVALUATION_PATH.as_posix()}",
                "bytes": len(evaluation_bytes),
                "sha256": _sha256(evaluation_bytes),
            },
            {
                "uri": f"repo://{PACK_PATH.as_posix()}",
                "bytes": len(pack_bytes),
                "sha256": _sha256(pack_bytes),
            },
        ],
        "transaction": {
            "model": "THREE_OUTPUT_RECOVERABLE_ALL_OR_NOTHING",
            "writer_lock": "GENERATED_DIRECTORY_FLOCK",
            "check_pending_recovery": "READ_ONLY_REJECT",
        },
        "boundary": {
            "classification": "LOCAL_BLOCKED_GATE1_DECISION_NON_ATTESTING",
            "decision": "BLOCKED",
            "eligibility": "NOT_ELIGIBLE",
            "mandatory_criteria_satisfied": False,
            "actual_articles": "UNAVAILABLE",
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
    results = _validate_fixture(root)
    evaluation = _evaluation_record(results)
    validate_evaluation_record(evaluation, expected_results=results)
    evaluation_bytes = _json_bytes(evaluation)
    pack = _gate_pack(contract, evaluation_bytes)
    validate_gate_pack(
        pack,
        expected_contract=contract,
        expected_evaluation_bytes=evaluation_bytes,
    )
    pack_bytes = _json_bytes(pack)
    manifest_bytes = _manifest_bytes(root, evaluation_bytes, pack_bytes)
    return {
        EVALUATION_PATH: evaluation_bytes,
        PACK_PATH: pack_bytes,
        MANIFEST_PATH: manifest_bytes,
    }


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
    except Gate1DecisionError:
        raise
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
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=output.descriptor,
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
    except Gate1DecisionError:
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
    return _json_bytes(
        {
            "schema": TRANSACTION_SCHEMA,
            "state": state,
            "outputs": [
                {
                    "path": path.as_posix(),
                    "next_sha256": _sha256(outputs[path]),
                    "original_present": originals[path] is not None,
                    "original_sha256": (
                        _sha256(snapshot.content)
                        if (snapshot := originals[path]) is not None
                        else None
                    ),
                }
                for path in GENERATED_PATHS
            ],
        }
    )


def _load_journal(
    output: _OutputDirectory, name: str, *, missing_ok: bool
) -> Mapping[str, Any] | None:
    snapshot = _snapshot(
        output,
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
    for name in (TRANSACTION_NAME, TRANSACTION_NEXT_NAME):
        if (
            _snapshot(
                output,
                name,
                "transaction",
                missing_ok=True,
                expected_mode=PRIVATE_MODE,
            )
            is not None
        ):
            return True
    for path in GENERATED_PATHS:
        for name, expected_mode in (
            (_stage_name(path), OUTPUT_MODE),
            (_previous_name(path), None),
            (_absent_name(path), PRIVATE_MODE),
        ):
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
        description="Build the local blocked ST-1802 GATE-1 decision."
    )
    parser.add_argument(
        "--check", action="store_true", help="verify generated outputs without writing"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except Gate1DecisionError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
