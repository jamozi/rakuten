"""Data-driven coverage of the structural CONT-SLICE-002 block matrix."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import csv
import json

import pytest

from .support import (
    BLOCK_SCHEMA_ROOT,
    BLOCK_TEXT_PATHS,
    BLOCK_TYPES,
    TEST_MATRIX_PATH,
    block_payload,
    block_payload_with_text,
    encoded,
    nested_value,
    payload_with_block,
)
from raos.domain.editorial import (
    ContentAstValidationError,
    dump_content_ast_json,
    load_content_ast,
)


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
def test_minimum_payload_and_round_trip_for_all_24_blocks(
    baseline_payload, block_type: str
) -> None:
    payload = payload_with_block(baseline_payload, block_type)

    first = dump_content_ast_json(load_content_ast(encoded(payload)))
    second = dump_content_ast_json(load_content_ast(first))

    assert json.loads(first) == payload
    assert first == second


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("raw_html", "<script>synthetic</script>"),
        ("manual_affiliate_url", "https://example.invalid/synthetic"),
        ("revenue", 1),
        ("review_body", "synthetic-review-canary"),
        ("review_text", "synthetic-review-canary"),
    ),
)
def test_unknown_security_sensitive_fields_are_rejected_on_every_block(
    baseline_payload, block_type: str, field: str, value: object
) -> None:
    payload = payload_with_block(baseline_payload, block_type)
    payload["blocks"][0][field] = value

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    assert captured.value.category == "SCHEMA"


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
def test_required_type_and_limit_failures_for_all_24_blocks(
    baseline_payload, block_type: str
) -> None:
    schema = json.loads(
        (BLOCK_SCHEMA_ROOT / f"{block_type}.schema.json").read_text(encoding="utf-8")
    )
    required_field = next(
        field
        for field in reversed(schema["required"])
        if field not in {"block_id", "type"}
        and not any(
            option.get("type") == "null"
            for option in schema["properties"].get(field, {}).get("oneOf", [])
        )
    )

    missing = payload_with_block(baseline_payload, block_type)
    del missing["blocks"][0][required_field]
    wrong_type = payload_with_block(baseline_payload, block_type)
    wrong_type["blocks"][0][required_field] = None
    over_limit = payload_with_block(baseline_payload, block_type)
    over_limit["blocks"][0]["block_id"] = "A" * 201

    for payload in (missing, wrong_type, over_limit):
        with pytest.raises(ContentAstValidationError):
            load_content_ast(encoded(payload))


@pytest.mark.parametrize("block_type", BLOCK_TYPES)
def test_duplicate_block_id_is_rejected_for_each_block_type(
    baseline_payload, block_type: str
) -> None:
    payload = payload_with_block(baseline_payload, block_type)
    duplicate = deepcopy(payload["blocks"][0])
    payload["blocks"].insert(1, duplicate)

    with pytest.raises(ContentAstValidationError) as captured:
        load_content_ast(encoded(payload))

    assert captured.value.category == "AST_POLICY"


@pytest.mark.parametrize(
    ("block_type", "expected_path"), tuple(BLOCK_TEXT_PATHS.items())
)
def test_block_specific_text_is_preserved_while_renderer_escaping_is_deferred(
    baseline_payload, block_type: str, expected_path: tuple[str | int, ...]
) -> None:
    payload = deepcopy(baseline_payload)
    canary = '<script data-x="1"></script><iframe onload="synthetic">'
    block, path = block_payload_with_text(block_type, canary, 999)
    payload["blocks"] = [block, *payload["blocks"]]

    rendered = dump_content_ast_json(load_content_ast(encoded(payload)))

    assert path == expected_path
    assert nested_value(json.loads(rendered)["blocks"][0], path) == canary


def test_installed_matrix_has_exact_24_by_12_cont_slice_002_rows() -> None:
    with TEST_MATRIX_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["implementation_slice"] == "CONT-SLICE-002"
        ]

    scenarios = (
        ("最小有効Payload", "PASS", "P0"),
        ("未知Property追加", "FAIL_SCHEMA", "P0"),
        ("必須Property欠落", "FAIL_SCHEMA", "P0"),
        ("type不一致", "FAIL_SCHEMA", "P1"),
        ("記事内Block ID重複", "FAIL_POLICY", "P1"),
        ("Public Snapshotにadmin_only", "FAIL_PUBLICATION", "P1"),
        ("存在しないClaim参照", "FAIL", "P1"),
        ("Finance関連Field混入", "FAIL_SCHEMA", "P0"),
        ("Raw URL混入", "FAIL_SCHEMA", "P0"),
        ("Script風文字列をTextとして安全Escaping", "PASS_ESCAPED", "P1"),
        ("上限超過", "FAIL_SCHEMA", "P1"),
        ("JSON→Domain→JSON", "PASS", "P1"),
    )
    expected_rows = []
    for block_offset, block_type in enumerate(BLOCK_TYPES):
        for scenario_offset, (scenario, expected_result, priority) in enumerate(
            scenarios
        ):
            expected_rows.append(
                {
                    "test_id": f"CT-{101 + block_offset * 12 + scenario_offset:04d}",
                    "area": "content_block",
                    "artifact_or_rule": f"BLK-{block_offset + 1:03d}",
                    "scenario": f"{block_type}: {scenario}",
                    "expected_result": expected_result,
                    "priority": priority,
                    "test_type": "schema",
                    "requirement_ids": "FR-007,FR-008,FR-009",
                    "implementation_slice": "CONT-SLICE-002",
                }
            )

    assert rows == expected_rows


def test_block_fixture_catalog_has_exact_24_types() -> None:
    assert len(BLOCK_TYPES) == 24
    assert len({block_payload(name)["type"] for name in BLOCK_TYPES}) == 24


def test_matrix_rows_have_an_explicit_runtime_or_deferred_owner() -> None:
    with TEST_MATRIX_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = [
            row
            for row in csv.DictReader(handle)
            if row["implementation_slice"] == "CONT-SLICE-002"
        ]
    structural_runtime_scenarios = {
        "最小有効Payload",
        "未知Property追加",
        "必須Property欠落",
        "type不一致",
        "記事内Block ID重複",
        "Finance関連Field混入",
        "Raw URL混入",
        "上限超過",
        "JSON→Domain→JSON",
    }
    classifications: list[str] = []
    for row in rows:
        block_type, separator, scenario = row["scenario"].partition(": ")
        assert separator == ": "
        if scenario in structural_runtime_scenarios:
            classifications.append("EXECUTED_STRUCTURAL_LOADER")
        elif scenario == "Public Snapshotにadmin_only":
            classifications.append("DEFERRED_PUBLICATION")
        elif scenario == "存在しないClaim参照":
            classifications.append("DEFERRED_CLAIM_EVIDENCE")
        elif scenario == "Script風文字列をTextとして安全Escaping":
            if block_type in BLOCK_TEXT_PATHS:
                classifications.append(
                    "LOADER_TEXT_PRESERVATION_RENDERER_ESCAPE_DEFERRED"
                )
            else:
                classifications.append("DEFERRED_RENDERER_NO_BLOCK_TEXT_FIELD")
        else:
            raise AssertionError(f"unclassified matrix scenario: {row['test_id']}")

    assert Counter(classifications) == {
        "EXECUTED_STRUCTURAL_LOADER": 216,
        "DEFERRED_PUBLICATION": 24,
        "DEFERRED_CLAIM_EVIDENCE": 24,
        "LOADER_TEXT_PRESERVATION_RENDERER_ESCAPE_DEFERRED": 18,
        "DEFERRED_RENDERER_NO_BLOCK_TEXT_FIELD": 6,
    }
