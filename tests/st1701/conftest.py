"""Shared fixtures for the isolated ST-1701 suite."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest

from scripts import build_st1701_business_inputs as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def contract_document() -> dict[str, Any]:
    return copy.deepcopy(cast(dict[str, Any], generator.load_contract(REPOSITORY_ROOT)))


@pytest.fixture
def reference_document(contract_document: dict[str, Any]) -> dict[str, object]:
    return generator.reference_document(contract_document)


@pytest.fixture
def decision_package() -> dict[str, Any]:
    return copy.deepcopy(
        cast(dict[str, Any], generator.load_decision_package(REPOSITORY_ROOT))
    )


@pytest.fixture
def final_package_approval() -> dict[str, Any]:
    return copy.deepcopy(
        cast(dict[str, Any], generator.load_final_package_approval(REPOSITORY_ROOT))
    )


@pytest.fixture
def gold_validation_document() -> dict[str, object]:
    return copy.deepcopy(generator.gold_evidence_validation_document(REPOSITORY_ROOT))


@pytest.fixture
def decision_read_model(
    decision_package: dict[str, Any], contract_document: dict[str, Any]
) -> dict[str, object]:
    return generator.decision_read_model(
        decision_package, contract_document, REPOSITORY_ROOT
    )
