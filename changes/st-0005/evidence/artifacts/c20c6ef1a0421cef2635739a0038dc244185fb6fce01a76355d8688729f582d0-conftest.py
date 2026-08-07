"""Shared fixtures for the isolated ST-0205 suite."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st0205_synthetic_data as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def contract() -> dict[str, Any]:
    return generator.load_and_validate_contract()


@pytest.fixture(scope="session")
def bundle() -> dict[str, Any]:
    return generator.build_seed_bundle()


@pytest.fixture(scope="session")
def fixtures_by_pair(bundle: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (fixture["schema_domain"], fixture["scenario"]): fixture
        for fixture in bundle["fixtures"]
    }


@pytest.fixture
def mutable_catalog_fixture(bundle: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(bundle["fixtures"][5])


@pytest.fixture
def secret_canary() -> str:
    return "".join(("sk", "-", "A" * 28))


@pytest.fixture
def email_canary() -> str:
    return "".join(("fixture-person", "@", "example.invalid"))
