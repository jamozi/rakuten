"""Shared fixtures for the isolated ST-1503 suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from scripts import build_st1503_compute_edge as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def contract_document() -> dict[str, Any]:
    document = generator.load_yaml(REPOSITORY_ROOT / generator.CONTRACT_PATH)
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


@pytest.fixture
def compute_edge_model() -> generator.ComputeEdgeModel:
    return generator.load_and_validate_contract(REPOSITORY_ROOT)
