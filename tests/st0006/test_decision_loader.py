"""Strict canonical-source tests for ST-0006."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError
import pytest
import yaml

from scripts import build_st0006_decision_gates as gates

from .support import clone, write_csv_source, write_yaml_source


def canonical_yaml_document() -> dict[str, Any]:
    return gates.load_open_decision_yaml()


def test_pinned_current_catalog_has_exact_inventory_and_parity(
    canonical_catalog: dict[str, Any],
) -> None:
    assert (
        gates.sha256_file(gates.OPEN_DECISIONS_YAML)
        == (
            gates.PINNED_INPUT_HASHES[
                gates.relative_repo_path(gates.OPEN_DECISIONS_YAML)
            ]
        )
    )
    assert (
        gates.sha256_file(gates.OPEN_DECISIONS_CSV)
        == (
            gates.PINNED_INPUT_HASHES[
                gates.relative_repo_path(gates.OPEN_DECISIONS_CSV)
            ]
        )
    )
    items = canonical_catalog["items"]
    assert [item["id"] for item in items] == list(gates.CURRENT_DECISION_IDS)
    assert len(items) == 15
    assert sum(item["blocking"] for item in items) == 14
    assert sum(gates.is_resolved(item["status"]) for item in items) == 0
    assert [item["id"] for item in items if not item["blocking"]] == ["OD-004"]
    assert canonical_catalog["source"]["yaml_sha256"] == gates.sha256_file(
        gates.OPEN_DECISIONS_YAML
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("RESOLVED", True),
        ("PROVISIONAL", False),
        ("HUMAN_DECISION_REQUIRED", False),
        ("EXTERNAL_EVIDENCE_REQUIRED", False),
    ],
)
def test_only_resolved_status_clears(status: str, expected: bool) -> None:
    assert gates.is_resolved(status) is expected


def test_unknown_status_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="unknown decision status"):
        gates.is_resolved("APPROVED")


def test_source_json_schema_accepts_canonical_yaml() -> None:
    schema = gates.open_decision_source_schema()
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(canonical_yaml_document())

    duplicate = clone(canonical_yaml_document())
    duplicate["items"][1]["id"] = duplicate["items"][0]["id"]
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(duplicate)


def test_duplicate_yaml_key_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.yaml"
    source.write_text(
        "document: {}\ndocument: {}\nrules: []\nitems: []\n", encoding="utf-8"
    )
    with pytest.raises(yaml.YAMLError, match="duplicate key"):
        gates.load_yaml(source)


def test_yaml_anchor_or_alias_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "alias.yaml"
    source.write_text(
        "document: &item {}\nrules: []\nitems: [*item]\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="anchors and aliases"):
        gates.load_yaml(source)


def test_yaml_complexity_limit_is_enforced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "complex.yaml"
    source.write_text("root:\n  child:\n    leaf: value\n", encoding="utf-8")
    monkeypatch.setattr(gates, "MAX_YAML_DEPTH", 1)
    with pytest.raises(RuntimeError, match="complexity limits"):
        gates.load_yaml(source)


def test_deep_yaml_is_rejected_before_construction(tmp_path: Path) -> None:
    source = tmp_path / "deep.yaml"
    source.write_text("[" * 500 + "value" + "]" * 500, encoding="utf-8")
    with pytest.raises(RuntimeError, match="nesting exceeds"):
        gates.load_yaml(source)


def test_oversized_missing_and_symlink_sources_are_rejected(tmp_path: Path) -> None:
    missing = tmp_path / "missing.yaml"
    with pytest.raises(RuntimeError, match="regular YAML file is missing"):
        gates.load_yaml(missing)

    oversized = tmp_path / "oversized.yaml"
    oversized.write_bytes(b"x" * (gates.MAX_YAML_BYTES + 1))
    with pytest.raises(RuntimeError, match="exceeds"):
        gates.load_yaml(oversized)

    target = tmp_path / "target.yaml"
    target.write_text("document: {}\n", encoding="utf-8")
    linked = tmp_path / "linked.yaml"
    linked.symlink_to(target)
    with pytest.raises(RuntimeError, match="regular YAML file is missing"):
        gates.load_yaml(linked)

    special = tmp_path / "special.yaml"
    os.mkfifo(special)
    with pytest.raises(RuntimeError, match="missing or unsafe"):
        gates.load_yaml(special)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda item: item.update({"unknown": "field"}), "strict field violation"),
        (lambda item: item.pop("owner"), "strict field violation"),
        (lambda item: item.update({"id": "OD-1"}), "invalid decision id"),
        (lambda item: item.update({"status": "APPROVED"}), "unknown decision status"),
        (lambda item: item.update({"blocking": "true"}), "strict boolean"),
        (lambda item: item.update({"topic": ""}), "bounded non-empty string"),
    ],
)
def test_item_contract_rejects_bad_fields_and_types(
    mutation: Any, message: str
) -> None:
    item = clone(canonical_yaml_document()["items"][0])
    mutation(item)
    with pytest.raises(RuntimeError, match=message):
        gates._validate_item(item, source="fixture")


def test_duplicate_unsorted_and_inventory_drift_are_rejected(tmp_path: Path) -> None:
    document = canonical_yaml_document()
    duplicate = clone(document)
    duplicate["items"][1]["id"] = duplicate["items"][0]["id"]
    source = tmp_path / "duplicate-id.yaml"
    write_yaml_source(source, duplicate)
    with pytest.raises(RuntimeError, match="sorted|duplicate"):
        gates.load_open_decision_yaml(
            source, require_pinned=False, require_current_inventory=False
        )

    unsorted = clone(document)
    unsorted["items"][0], unsorted["items"][1] = (
        unsorted["items"][1],
        unsorted["items"][0],
    )
    source = tmp_path / "unsorted.yaml"
    write_yaml_source(source, unsorted)
    with pytest.raises(RuntimeError, match="sorted"):
        gates.load_open_decision_yaml(
            source, require_pinned=False, require_current_inventory=False
        )

    shortened = clone(document)
    shortened["items"].pop()
    source = tmp_path / "shortened.yaml"
    write_yaml_source(source, shortened)
    with pytest.raises(RuntimeError, match="inventory drift"):
        gates.load_open_decision_yaml(source, require_pinned=False)


def test_document_identity_rules_and_unknown_top_level_are_rejected(
    tmp_path: Path,
) -> None:
    document = canonical_yaml_document()
    document["document"]["status"] = "DRAFT"
    source = tmp_path / "identity.yaml"
    write_yaml_source(source, document)
    with pytest.raises(RuntimeError, match="identity drift"):
        gates.load_open_decision_yaml(
            source, require_pinned=False, require_current_inventory=False
        )

    document = canonical_yaml_document()
    document["rules"] = list(reversed(document["rules"]))
    source = tmp_path / "rules.yaml"
    write_yaml_source(source, document)
    with pytest.raises(RuntimeError, match="safety rules drift"):
        gates.load_open_decision_yaml(
            source, require_pinned=False, require_current_inventory=False
        )

    document = canonical_yaml_document()
    document["unknown"] = True
    source = tmp_path / "unknown.yaml"
    write_yaml_source(source, document)
    with pytest.raises(RuntimeError, match="strict field violation"):
        gates.load_open_decision_yaml(
            source, require_pinned=False, require_current_inventory=False
        )


def test_csv_header_boolean_and_semantic_parity_are_strict(tmp_path: Path) -> None:
    document = canonical_yaml_document()
    csv_source = tmp_path / "decisions.csv"
    write_csv_source(csv_source, document["items"])
    loaded = gates.load_open_decision_csv(
        csv_source, require_pinned=False, require_current_inventory=True
    )
    assert loaded == document["items"]

    bad_header = tmp_path / "bad-header.csv"
    bad_header.write_text("topic,id,status\nvalue,OD-001,RESOLVED\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="header drift"):
        gates.load_open_decision_csv(
            bad_header, require_pinned=False, require_current_inventory=False
        )

    bad_boolean = tmp_path / "bad-boolean.csv"
    write_csv_source(bad_boolean, document["items"])
    bad_boolean.write_text(
        bad_boolean.read_text(encoding="utf-8").replace(",True\n", ",true\n", 1),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="True or False"):
        gates.load_open_decision_csv(
            bad_boolean, require_pinned=False, require_current_inventory=False
        )


def test_yaml_csv_value_drift_is_rejected(tmp_path: Path) -> None:
    document = canonical_yaml_document()
    yaml_source = tmp_path / "decisions.yaml"
    csv_source = tmp_path / "decisions.csv"
    write_yaml_source(yaml_source, document)
    drifted = clone(document["items"])
    drifted[0]["owner"] = "Different Owner"
    write_csv_source(csv_source, drifted)
    with pytest.raises(RuntimeError, match="parity mismatch"):
        gates.load_decision_catalog(
            yaml_source,
            csv_source,
            require_pinned=False,
            require_current_inventory=True,
        )


def test_pinned_loader_rejects_noncanonical_or_drifted_path(tmp_path: Path) -> None:
    copied = tmp_path / "open-decisions.yaml"
    copied.write_bytes(gates.OPEN_DECISIONS_YAML.read_bytes())
    with pytest.raises(RuntimeError, match="hash drift"):
        gates.load_open_decision_yaml(copied, require_pinned=True)
