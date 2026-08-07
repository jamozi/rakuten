"""Shared fixtures for the isolated ST-1203 recorded-adapter slice."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
for import_root in (REPOSITORY_ROOT, PYTHON_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts import build_st1203_search_console_recorded_adapter as generator  # noqa: E402


@pytest.fixture(scope="session")
def source_contract() -> dict[str, Any]:
    value = yaml.safe_load((REPOSITORY_ROOT / generator.CONTRACT_PATH).read_bytes())
    assert isinstance(value, dict)
    return value


@pytest.fixture(scope="session")
def recordings(source_contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["recording_id"]: item for item in source_contract["recordings"]}


@pytest.fixture(scope="session")
def generated_fixtures() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name in generator.EXPECTED_FIXTURE_NAMES:
        value = json.loads(
            (REPOSITORY_ROOT / generator.FIXTURE_ROOT / name).read_bytes()
        )
        assert isinstance(value, dict)
        result[name] = value
    return result


@pytest.fixture(scope="session")
def request_schema(source_contract: dict[str, Any]) -> dict[str, Any]:
    return _schema_for_role(source_contract, "acquisition_request")


@pytest.fixture(scope="session")
def row_schema(source_contract: dict[str, Any]) -> dict[str, Any]:
    return _schema_for_role(source_contract, "canonical_row")


def _schema_for_role(source_contract: dict[str, Any], role: str) -> dict[str, Any]:
    entries = [
        item
        for item in source_contract["provenance"]["contract_schemas"]
        if item["role"] == role
    ]
    assert len(entries) == 1
    relative = entries[0]["uri"].removeprefix("repo://")
    value = json.loads((REPOSITORY_ROOT / relative).read_bytes())
    assert isinstance(value, dict)
    return value
