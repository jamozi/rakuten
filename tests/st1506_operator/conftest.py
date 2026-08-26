"""Shared fixtures for the additive ST-1506 WordPress operator slice."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SLICE_ROOT = (
    REPOSITORY_ROOT / "changes/st-1506/self-hosted-wordpress-operator-bridge-v1"
)


@pytest.fixture
def operator_contract() -> dict[str, Any]:
    value = yaml.safe_load(
        (SLICE_ROOT / "contracts/self-hosted-wordpress-operator.v1.yaml").read_bytes()
    )
    assert type(value) is dict
    return cast(dict[str, Any], value)


@pytest.fixture
def design_handoff() -> dict[str, Any]:
    value = yaml.safe_load((SLICE_ROOT / "DESIGN_HANDOFF_V1.yaml").read_bytes())
    assert type(value) is dict
    return cast(dict[str, Any], value)
