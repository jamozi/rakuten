from __future__ import annotations

# pyright: reportPrivateUsage=false

import json
from pathlib import Path
import sys
from typing import Any, cast

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import build_st0807_seo_render_runtime as generator  # noqa: E402


@pytest.fixture
def contract() -> dict[str, Any]:
    return dict(generator._load_contract(REPO_ROOT))


@pytest.fixture
def result_document(contract: dict[str, Any]) -> dict[str, object]:
    return generator._result_document(REPO_ROOT, contract)


@pytest.fixture
def generated_document() -> dict[str, Any]:
    value = cast(
        object,
        json.loads((REPO_ROOT / generator.RESULT_PATH).read_bytes()),
    )
    assert type(value) is dict
    return cast(dict[str, Any], value)


@pytest.fixture
def runtime_manifest() -> dict[str, Any]:
    value = cast(
        object,
        yaml.safe_load((REPO_ROOT / generator.MANIFEST_PATH).read_bytes()),
    )
    assert type(value) is dict
    return cast(dict[str, Any], value)
