"""Shared fixtures for the additive ST-1704 publication operator."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, cast

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/publication-operator-v2"
PYTHON_ROOT = ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


@pytest.fixture
def publication_contract() -> dict[str, Any]:
    value = yaml.safe_load(
        (
            SLICE / "contracts/self-hosted-wordpress-publication-operator.v2.yaml"
        ).read_bytes()
    )
    assert type(value) is dict
    return cast(dict[str, Any], value)


@pytest.fixture
def canonical_addendum() -> dict[str, Any]:
    value = yaml.safe_load(
        (
            ROOT / "changes/st-1704/publication-operator-v2/"
            "INT-DEC-016-ADDITIVE-CLARIFICATION.yaml"
        ).read_bytes()
    )
    assert type(value) is dict
    return cast(dict[str, Any], value)
