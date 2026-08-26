"""Semantic contract assertions for the ST-1703 low-cost pilot."""

from __future__ import annotations

from scripts import build_st1703_low_cost_publication_pilot as generator


def test_contract_is_semantic_and_non_executable(
    contract_document: dict[str, object],
) -> None:
    generator.validate_contract(contract_document)
    document = contract_document["document"]
    assert isinstance(document, dict)
    assert document["development_status"] == "CONTINUOUS_LOCAL_IMPLEMENTATION"
    assert document["production_readiness"] == "NOT_READY"
    serialized = str(contract_document).lower()
    assert "approved_base_commit" not in serialized
    assert "handoff_sha256" not in serialized
    assert "approval_sha256" not in serialized


def test_external_effect_boundaries_remain_closed(
    contract_document: dict[str, object],
) -> None:
    actions = contract_document["action_boundary"]
    effects = contract_document["effect_boundary"]
    assert isinstance(actions, dict)
    assert isinstance(effects, dict)
    assert all(value == [] for value in actions.values())
    assert all(value == [] for value in effects.values())
