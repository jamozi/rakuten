"""Fail-closed checks for the ST-1703 low-cost pilot."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st1703_low_cost_publication_pilot as generator


@pytest.mark.parametrize(
    ("section", "key", "value"),
    (
        ("spend_boundary", "purchase_authority", "AUTHORIZED"),
        ("evidence_boundary", "publication", "EXECUTED"),
        ("evidence_boundary", "production", "EXECUTED"),
    ),
)
def test_external_boundary_drift_is_rejected(
    contract_document: dict[str, object],
    section: str,
    key: str,
    value: str,
) -> None:
    candidate = copy.deepcopy(contract_document)
    target = candidate[section]
    assert isinstance(target, dict)
    target[key] = value
    with pytest.raises(generator.LowCostPublicationPilotError) as error:
        generator.validate_contract(candidate)
    assert error.value.code == "SAFETY_BOUNDARY_DRIFT"


def test_governance_hash_binding_is_rejected(
    contract_document: dict[str, object],
) -> None:
    candidate = copy.deepcopy(contract_document)
    candidate["decision_context"]["handoff_sha256"] = "0" * 64  # type: ignore[index]
    with pytest.raises(generator.LowCostPublicationPilotError) as error:
        generator.validate_contract(candidate)
    assert error.value.code in {"CONTRACT_INVALID", "GOVERNANCE_BINDING_FORBIDDEN"}
