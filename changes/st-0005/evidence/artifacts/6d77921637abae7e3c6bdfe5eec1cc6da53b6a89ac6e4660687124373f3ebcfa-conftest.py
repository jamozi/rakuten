"""Import isolation and contract fixtures for the ST-0203 queue suite."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
import sys
from typing import Any

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from scripts import build_st0203_queue_fake as generator  # noqa: E402


Contract = dict[str, Any]
RejectContract = Callable[[Contract, str], None]


@pytest.fixture(scope="session")
def queue_contract() -> Contract:
    return generator.load_and_validate_contract(REPOSITORY_ROOT)


@pytest.fixture
def mutable_contract(queue_contract: Contract) -> Contract:
    return deepcopy(queue_contract)


@pytest.fixture
def reject_contract(monkeypatch: pytest.MonkeyPatch) -> RejectContract:
    real_load = generator.shared.load_yaml

    def reject(mutated: Contract, match: str) -> None:
        def load(path: Path) -> object:
            if path == REPOSITORY_ROOT / generator.CONTRACT_PATH:
                return mutated
            return real_load(path)

        monkeypatch.setattr(generator.shared, "load_yaml", load)
        with pytest.raises(RuntimeError, match=match):
            generator.load_and_validate_contract(REPOSITORY_ROOT)

    return reject
