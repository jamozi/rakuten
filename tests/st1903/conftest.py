"""Shared fixtures for the isolated ST-1903 policy-candidate suite."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts import (  # noqa: E402
    build_st1903_autonomous_publication_policy as generator,
)


@pytest.fixture(scope="session")
def loaded_inputs() -> tuple[dict[str, Any], dict[str, Any]]:
    """Load and validate the exact source contract and pending handoff."""

    return generator.load_inputs()


@pytest.fixture()
def contract(
    loaded_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    """Return a detached policy-contract copy for each test."""

    return deepcopy(loaded_inputs[0])


@pytest.fixture()
def handoff(
    loaded_inputs: tuple[dict[str, Any], dict[str, Any]],
) -> dict[str, Any]:
    """Return a detached pending handoff copy for each test."""

    return deepcopy(loaded_inputs[1])
