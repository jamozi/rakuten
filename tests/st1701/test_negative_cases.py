"""ST-1701 fail-closed boundary checks."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st1701_business_inputs as generator


def test_external_action_authorization_is_rejected(
    decision_package: dict[str, object],
) -> None:
    candidate = copy.deepcopy(decision_package)
    actions = candidate["action_boundary"]
    assert isinstance(actions, dict)
    actions["production"] = "AUTHORIZED"
    with pytest.raises(generator.BusinessInputBuildError) as error:
        generator.validate_decision_package(candidate)
    assert error.value.code == "SAFETY_BOUNDARY_DRIFT"


def test_governance_hash_binding_is_rejected(
    decision_package: dict[str, object],
) -> None:
    candidate = copy.deepcopy(decision_package)
    context = candidate["development_context"]
    assert isinstance(context, dict)
    context["handoff_sha256"] = "0" * 64
    with pytest.raises(generator.BusinessInputBuildError) as error:
        generator.validate_decision_package(candidate)
    assert error.value.code in {
        "DECISION_PACKAGE_INVALID",
        "GOVERNANCE_BINDING_FORBIDDEN",
    }


def test_canonical_checksum_drift_is_rejected(
    tmp_path,
    contract_document: dict[str, object],
) -> None:
    root = tmp_path / "repository"
    for row in contract_document["sources"]:  # type: ignore[index]
        relative = row["uri"].removeprefix("repo://")
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"drift")
    with pytest.raises(generator.BusinessInputBuildError) as error:
        generator.validate_contract(contract_document, root)
    assert error.value.code == "CANONICAL_INPUT_DRIFT"
