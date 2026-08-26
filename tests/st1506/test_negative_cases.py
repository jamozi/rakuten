"""Focused safety and semantic-owner rejection tests for ST-1506."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st1506_production_deployment as generator


def test_current_contract_is_valid() -> None:
    model = generator.load_and_validate_contract()
    assert model.contract["execution_boundary"]["runtime_status"] == "NOT_EXECUTED"


@pytest.mark.parametrize("specification", generator.PREDECESSOR_SPECIFICATIONS)
def test_predecessor_owner_version_rebind_is_rejected(
    contract_document: dict[str, object], specification: tuple[object, ...]
) -> None:
    name = specification[0]
    assert isinstance(name, str)
    mutated = copy.deepcopy(contract_document)
    bindings = mutated["predecessor_bindings"]
    assert isinstance(bindings, dict)
    binding = bindings[name]
    assert isinstance(binding, dict)
    binding["owner_version"] = 3
    with pytest.raises(generator.ProductionDeploymentContractError):
        generator.validate_contract(mutated)


def test_production_enablement_is_rejected(
    contract_document: dict[str, object],
) -> None:
    mutated = copy.deepcopy(contract_document)
    boundary = mutated["execution_boundary"]
    assert isinstance(boundary, dict)
    boundary["production_action"] = "EXECUTED"
    with pytest.raises(generator.ProductionDeploymentContractError):
        generator.validate_contract(mutated)
