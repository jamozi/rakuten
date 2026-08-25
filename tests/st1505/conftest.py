"""Shared fixtures for the isolated ST-1505 suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from scripts import build_st1505_staging_deployment as generator
from raos.domain.ops.staging_admission import LocalStagingAdmissionSpec


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def contract_document() -> dict[str, Any]:
    document = generator.load_yaml(REPOSITORY_ROOT / generator.CONTRACT_PATH)
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


@pytest.fixture
def staging_model() -> generator.StagingDeploymentModel:
    return generator.load_and_validate_contract(REPOSITORY_ROOT)


@pytest.fixture
def runtime_document() -> dict[str, Any]:
    document = generator.load_yaml(REPOSITORY_ROOT / generator.RUNTIME_CONTRACT_PATH)
    assert isinstance(document, dict)
    return cast(dict[str, Any], document)


@pytest.fixture
def runtime_spec() -> LocalStagingAdmissionSpec:
    _document, specification = generator.load_and_validate_runtime_contract(
        REPOSITORY_ROOT
    )
    return specification


@pytest.fixture
def owner_private_root(tmp_path: Path) -> Path:
    root = tmp_path / "owner-private-st1505"
    root.mkdir(mode=0o700)
    return root
