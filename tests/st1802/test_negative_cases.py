from __future__ import annotations

import copy
import json
import os
from pathlib import Path

import pytest

from scripts import build_st1802_gate1_decision as builder


def _st1801_record() -> dict[str, object]:
    value = builder._load_json(
        builder.REPO_ROOT,
        Path("changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"),
        "st1801",
    )
    return copy.deepcopy(dict(value))


def test_st1801_hash_drift_fails_closed(repository_copy: Path) -> None:
    path = (
        repository_copy
        / "changes/st-1801/generated/portfolio-expansion.local-blocked.v1.json"
    )
    document = json.loads(path.read_text())
    document["decision"]["overall"] = "PASS"
    path.write_text(json.dumps(document))
    with pytest.raises(builder.Gate1DecisionError, match="PINNED_INPUT_DRIFT"):
        builder.load_contract(repository_copy)


def test_mixed_portfolio_category_is_rejected() -> None:
    record = _st1801_record()
    record["portfolio"]["planned_slots"][0]["category_ref"] = "OTHER"
    with pytest.raises(
        builder.Gate1DecisionError, match="MIXED_OR_DUPLICATE_PORTFOLIO_INPUT"
    ):
        builder._validate_st1801(record)


def test_mixed_portfolio_program_is_rejected() -> None:
    record = _st1801_record()
    record["portfolio"]["planned_slots"][0]["program"] = "OTHER"
    with pytest.raises(
        builder.Gate1DecisionError, match="MIXED_OR_DUPLICATE_PORTFOLIO_INPUT"
    ):
        builder._validate_st1801(record)


def test_fabricated_article_state_is_rejected() -> None:
    record = _st1801_record()
    record["portfolio"]["planned_slots"][0]["publication_status"] = "PUBLIC"
    with pytest.raises(builder.Gate1DecisionError):
        builder._validate_st1801(record)


def test_dependency_authority_escalation_is_rejected() -> None:
    record = _st1801_record()
    record["authority_boundary"]["gate_authority"] = "AUTOMATION"
    with pytest.raises(builder.Gate1DecisionError, match="AUTHORITY_ESCALATION"):
        builder._validate_st1801(record)


def test_unknown_synthetic_input_field_is_rejected() -> None:
    value = {key: None for key in builder.INPUT_KEYS}
    value["invented"] = 1
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder.evaluate_recorded_synthetic(value)


def test_missing_synthetic_input_field_is_rejected() -> None:
    value = {key: None for key in builder.INPUT_KEYS}
    del value["rollback_verified"]
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder.evaluate_recorded_synthetic(value)


def test_contract_unknown_field_is_rejected(contract: dict[str, object]) -> None:
    contract["invented"] = True
    with pytest.raises(builder.Gate1DecisionError, match="UNKNOWN_OR_MISSING_FIELD"):
        builder._validate_contract_structure(contract)


def test_json_duplicate_key_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1802/fixtures/duplicate.json")
    path = repository_copy / relative
    path.write_text('{"value": 1, "value": 2}\n')
    with pytest.raises(builder.Gate1DecisionError, match="JSON_DUPLICATE_KEY"):
        builder._load_json(repository_copy, relative, "duplicate")


def test_yaml_duplicate_key_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1802/fixtures/duplicate.yaml")
    path = repository_copy / relative
    path.write_text("value: 1\nvalue: 2\n")
    with pytest.raises(builder.Gate1DecisionError, match="YAML_INVALID"):
        builder._load_yaml(repository_copy, relative, "duplicate")


def test_yaml_alias_is_rejected(repository_copy: Path) -> None:
    relative = Path("changes/st-1802/fixtures/alias.yaml")
    path = repository_copy / relative
    path.write_text("value: &anchor 1\ncopy: *anchor\n")
    with pytest.raises(builder.Gate1DecisionError, match="YAML_ALIAS_FORBIDDEN"):
        builder._load_yaml(repository_copy, relative, "alias")


def test_input_symlink_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    moved = target.with_suffix(".real")
    target.rename(moved)
    target.symlink_to(moved.name)
    with pytest.raises(builder.Gate1DecisionError, match="UNSAFE_FILE_TYPE"):
        builder.load_contract(repository_copy)


def test_input_hardlink_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    linked = target.with_suffix(".linked")
    os.link(target, linked)
    with pytest.raises(builder.Gate1DecisionError, match="UNSAFE_FILE_TYPE"):
        builder.load_contract(repository_copy)


def test_oversized_input_is_rejected(repository_copy: Path) -> None:
    target = repository_copy / builder.CONTRACT_PATH
    target.write_bytes(b"x" * (builder.MAX_INPUT_BYTES + 1))
    with pytest.raises(builder.Gate1DecisionError, match="INPUT_SIZE_LIMIT"):
        builder.load_contract(repository_copy)


@pytest.mark.parametrize("target_path", builder.GENERATED_PATHS)
def test_output_symlink_is_rejected(repository_copy: Path, target_path: Path) -> None:
    destination = repository_copy / target_path
    destination.write_text("foreign")
    moved = destination.with_suffix(destination.suffix + ".real")
    destination.rename(moved)
    destination.symlink_to(moved.name)
    with pytest.raises(builder.Gate1DecisionError, match="UNSAFE_OUTPUT_TARGET"):
        builder.build(repository_copy)


def test_tampered_generated_output_fails_check(repository_copy: Path) -> None:
    builder.build(repository_copy)
    target = repository_copy / builder.PACK_PATH
    target.write_text("{}\n")
    with pytest.raises(builder.Gate1DecisionError, match="GENERATED_OUTPUT_DRIFT"):
        builder.build(repository_copy, check=True)
