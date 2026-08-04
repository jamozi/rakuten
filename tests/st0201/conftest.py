"""Shared fixtures for the isolated ST-0201 PostgreSQL service suite."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts import build_st0201_postgres_service as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_FILE = REPOSITORY_ROOT / generator.CONTRACT_PATH

Contract = dict[str, Any]
RejectContract = Callable[[Contract, str], None]


@pytest.fixture(scope="session")
def postgres_contract() -> Contract:
    """Load the maintained contract through the production validator."""

    return generator.load_and_validate_contract(REPOSITORY_ROOT)


@pytest.fixture
def mutable_contract(postgres_contract: Contract) -> Contract:
    """Return a private mutable copy for one adversarial case."""

    return deepcopy(postgres_contract)


@pytest.fixture
def reject_contract(monkeypatch: pytest.MonkeyPatch) -> RejectContract:
    """Validate a mutated contract while retaining real pinned inputs."""

    real_load_yaml = generator.load_yaml

    def reject(mutated: Contract, message_pattern: str) -> None:
        def load_yaml(path: Path) -> object:
            if path == CONTRACT_FILE:
                return mutated
            return real_load_yaml(path)

        monkeypatch.setattr(generator, "load_yaml", load_yaml)
        with pytest.raises(RuntimeError, match=message_pattern):
            generator.load_and_validate_contract(REPOSITORY_ROOT)

    return reject
