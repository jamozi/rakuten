"""Hostile fail-closed tests for ST-1701."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1506_production_deployment as base_generator
from scripts import build_st1701_business_inputs as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MARKER = "REJECTED_BUSINESS_INPUT_1701"


def _validate(document: dict[str, Any]) -> None:
    generator.validate_contract(document, REPOSITORY_ROOT)


@pytest.mark.parametrize("field", tuple(generator.EXPECTED_BUSINESS_INPUTS))
def test_no_business_value_or_resolution_payload_can_be_selected(
    contract_document: dict[str, Any], field: str
) -> None:
    document = copy.deepcopy(contract_document)
    document["business_inputs"][field] = MARKER
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("blocking", False),
        ("resolution_state", "RESOLVED"),
        ("active_blocker", False),
        ("blocked_targets", ["GATE-0"]),
        ("safe_default_is_resolution", True),
        ("selected_value", MARKER),
        ("resolution_payload", {"value": MARKER}),
    ),
)
def test_decision_rows_cannot_be_resolved_or_weakened(
    contract_document: dict[str, Any], field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["decisions"][0][field] = value
    with pytest.raises(generator.BusinessInputsError) as captured:
        _validate(document)
    assert MARKER not in str(captured.value)


@pytest.mark.parametrize("mutation", ("remove", "duplicate", "reorder", "extra"))
def test_exact_decision_inventory_cannot_change(
    contract_document: dict[str, Any], mutation: str
) -> None:
    document = copy.deepcopy(contract_document)
    decisions = document["decisions"]
    if mutation == "remove":
        decisions.pop()
    elif mutation == "duplicate":
        decisions[1] = copy.deepcopy(decisions[0])
    elif mutation == "reorder":
        decisions[0], decisions[1] = decisions[1], decisions[0]
    else:
        decisions.append(copy.deepcopy(decisions[-1]))
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


@pytest.mark.parametrize("value", (1, True, 0.0, "0"))
def test_action_counts_require_exact_builtin_zero(
    contract_document: dict[str, Any], value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document["action_boundary"]["action_counts"]["production"] = value
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    (
        ("safe_defaults", "selected_values", "ALLOWED"),
        ("safe_defaults", "safe_defaults_are_resolutions", True),
        ("safe_defaults", "external_publication", "ALLOWED"),
        ("safe_defaults", "production", "ENABLED"),
        ("activation", "enabled", True),
        ("activation", "status", "ACTIVE"),
        ("action_boundary", "external_actions", "ALLOWED"),
        ("action_boundary", "publication", "ALLOWED"),
        ("action_boundary", "staging", "ALLOWED"),
        ("action_boundary", "release", "ALLOWED"),
        ("action_boundary", "production", "ALLOWED"),
        ("evidence_boundary", "formal_tst_032", "PASS"),
        ("evidence_boundary", "human_approvals", "OBTAINED"),
        ("evidence_boundary", "st_1701_acceptance_achieved", True),
        ("downstream_boundary", "st_1702_ready", True),
        ("downstream_boundary", "publication_ready", True),
        ("downstream_boundary", "release_ready", True),
        ("downstream_boundary", "production_ready", True),
    ),
)
def test_safe_gate_evidence_and_downstream_boundaries_cannot_be_promoted(
    contract_document: dict[str, Any], section: str, field: str, value: object
) -> None:
    document = copy.deepcopy(contract_document)
    document[section][field] = value
    with pytest.raises(generator.BusinessInputsError):
        _validate(document)


def test_source_inventory_is_ordered_unique_and_hash_bound(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("reorder", "duplicate", "hash", "bytes"):
        document = copy.deepcopy(contract_document)
        sources = document["sources"]
        if mutation == "reorder":
            sources[0], sources[1] = sources[1], sources[0]
        elif mutation == "duplicate":
            sources[0] = copy.deepcopy(sources[1])
        elif mutation == "hash":
            sources[0]["sha256"] = "0" * 64
        else:
            sources[0]["bytes"] = 1
        with pytest.raises(generator.BusinessInputsError):
            _validate(document)


def test_unknown_missing_and_reordered_contract_keys_are_rejected(
    contract_document: dict[str, Any],
) -> None:
    for mutation in ("unknown", "missing", "reorder"):
        document = copy.deepcopy(contract_document)
        if mutation == "unknown":
            document[MARKER] = MARKER
        elif mutation == "missing":
            document.pop("downstream_boundary")
        else:
            first = document.pop("document")
            document["document"] = first
        with pytest.raises(generator.BusinessInputsError) as captured:
            _validate(document)
        assert MARKER not in str(captured.value)


def test_strict_yaml_rejects_duplicates_aliases_and_unsafe_tags(tmp_path: Path) -> None:
    payloads = (
        "document: safe\ndocument: blocked\n",
        "value: &blocked safe\ncopy: *blocked\n",
        "value: !!python/object/apply:os.system ['blocked']\n",
    )
    for index, payload in enumerate(payloads):
        path = tmp_path / f"hostile-{index}.yaml"
        path.write_text(payload, encoding="utf-8")
        with pytest.raises(base_generator.ProductionDeploymentContractError):
            base_generator.load_yaml(path)
