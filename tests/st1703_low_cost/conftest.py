"""Shared fixtures for the ST-1703 low-cost pilot boundary."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st1703_low_cost_publication_pilot as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def contract_document() -> dict[str, Any]:
    return copy.deepcopy(generator.load_yaml(REPOSITORY_ROOT, generator.CONTRACT_PATH))
