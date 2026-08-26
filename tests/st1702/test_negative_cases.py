"""ST-1702 fail-closed boundary checks."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st1702_category_fixtures_rules_reference_plan as generator


def test_external_execution_enablement_is_rejected() -> None:
    candidate = copy.deepcopy(generator.load_contract())
    candidate["execution_boundary"]["enabled"] = True
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as error:
        generator.validate_contract(candidate)
    assert error.value.code == "SAFETY_BOUNDARY_DRIFT"


def test_governance_hash_binding_is_rejected() -> None:
    candidate = copy.deepcopy(generator.load_contract())
    candidate["dependencies"][0]["approval_sha256"] = "0" * 64
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as error:
        generator.validate_contract(candidate)
    assert error.value.code == "GOVERNANCE_BINDING_FORBIDDEN"


def test_canonical_checksum_drift_is_rejected(isolated_repository) -> None:
    contract = generator._load_yaml(isolated_repository, generator.CONTRACT_PATH)
    source = contract["authority"]["sources"][0]["uri"].removeprefix("repo://")
    (isolated_repository / source).write_bytes(b"drift")
    with pytest.raises(generator.CategoryFixturesRulesReferenceError) as error:
        generator.validate_contract(contract, isolated_repository)
    assert error.value.code == "CANONICAL_INPUT_DRIFT"
