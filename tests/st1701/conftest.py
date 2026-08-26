"""Shared ST-1701 semantic fixtures."""

from __future__ import annotations

import copy

import pytest

from scripts import build_st1701_business_inputs as generator


@pytest.fixture
def contract_document() -> dict[str, object]:
    return copy.deepcopy(generator.load_contract())


@pytest.fixture
def decision_package() -> dict[str, object]:
    return copy.deepcopy(generator.load_decision_package())
