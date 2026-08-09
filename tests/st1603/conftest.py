"""Shared fixtures for the isolated ST-1603 suite."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, cast

import pytest

from scripts import build_st1603_security_verification_pack as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def contract_document() -> dict[str, Any]:
    return copy.deepcopy(cast(dict[str, Any], generator.load_contract(REPOSITORY_ROOT)))


@pytest.fixture
def reference_document() -> dict[str, Any]:
    contract = generator.load_contract(REPOSITORY_ROOT)
    controls = generator._project_controls(REPOSITORY_ROOT)  # noqa: SLF001
    return generator.reference_plan(contract, controls)
