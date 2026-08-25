from __future__ import annotations

from pathlib import Path

import pytest

from scripts import build_st1903_partial_auto_publication as builder


@pytest.fixture
def fixture_bytes() -> bytes:
    return (builder.REPO_ROOT / builder.FIXTURE_PATH).read_bytes()


@pytest.fixture
def report_path() -> Path:
    return builder.REPO_ROOT / builder.REPORT_PATH


@pytest.fixture
def manifest_path() -> Path:
    return builder.REPO_ROOT / builder.MANIFEST_PATH
