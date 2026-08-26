"""Shared ST-1702 semantic fixtures."""

from __future__ import annotations

import shutil

import pytest

from scripts import build_st1702_category_fixtures_rules_reference_plan as generator


@pytest.fixture
def isolated_repository(tmp_path):
    root = tmp_path / "repository"
    contract = generator.load_contract()
    paths = [generator.CONTRACT_PATH]
    paths.extend(
        row["uri"].removeprefix("repo://") for row in contract["authority"]["sources"]
    )
    for relative in paths:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(generator.REPO_ROOT / relative, target)
    return root
