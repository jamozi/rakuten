"""Import isolation and reusable inputs for the ST-0204 config suite."""

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

from scripts import build_st0204_config_loader as generator  # noqa: E402


Contract = dict[str, Any]
RejectContract = Callable[[Contract, str], None]


CANONICAL_ENVIRONMENTS = (
    "ENV-DEV",
    "ENV-CI",
    "ENV-INTEGRATION",
    "ENV-STAGING",
    "ENV-RECOVERY",
    "ENV-PRODUCTION",
)

EXPECTED_TOOLCHAIN = {
    "python": "3.14.6",
    "pydantic": "2.13.4",
    "pydantic_core": "2.46.4",
    "pyyaml": "6.0.3",
    "uv": "0.12.1",
}

TOOLCHAIN_SOURCE_PATHS = (
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
    Path("scripts/build_st0201_postgres_service.py"),
)


def logical_reference(target: str) -> str:
    """Build a logical reference without resembling a maintained credential."""

    return "".join(("sec", "ret", "://", target))


@pytest.fixture
def minimal_source() -> dict[str, object]:
    """Return the smallest valid explicit environment mapping."""

    return {
        "RAOS_ENVIRONMENT": "ENV-DEV",
        "RAOS_SERVICE_NAME": "catalog-worker",
    }


@pytest.fixture
def reference_canary() -> str:
    """Return a harmless marker whose disclosure would fail privacy tests."""

    return "-".join(("marker", "must", "stay", "private", "91"))


@pytest.fixture(scope="session")
def config_contract() -> Contract:
    """Return the checksum-pinned reviewed ST-0204 contract."""

    return generator.load_and_validate_contract(REPOSITORY_ROOT)


@pytest.fixture
def mutable_config_contract(config_contract: Contract) -> Contract:
    """Return one isolated contract copy for semantic drift tests."""

    return deepcopy(config_contract)


@pytest.fixture
def reject_config_contract(monkeypatch: pytest.MonkeyPatch) -> RejectContract:
    """Assert that the generator rejects a supplied semantic mutation."""

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
