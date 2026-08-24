from __future__ import annotations

# pyright: reportPrivateUsage=false

from pathlib import Path
import sys
from typing import Any, cast

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import (  # noqa: E402
    build_st0903_publication_snapshot_runtime_v2 as generator,
)
from raos.adapters.recorded_publication_snapshot_v2 import (  # noqa: E402
    RecordedPublicationSnapshotStep,
    build_recorded_publication_snapshot_step,
)


def read(path: Path) -> bytes:
    return (REPO_ROOT / path).read_bytes()


@pytest.fixture(scope="session")
def contract() -> dict[str, Any]:
    return cast(dict[str, Any], generator.load_contract(REPO_ROOT))


@pytest.fixture(scope="session")
def seed(contract: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], contract["fixture"]["seed"])


@pytest.fixture(scope="session")
def step(seed: dict[str, Any]) -> RecordedPublicationSnapshotStep:
    return build_recorded_publication_snapshot_step(
        seed,
        final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
        policy_fixture=read(generator.POLICY_FIXTURE_PATH),
        review_fixture=read(generator.REVIEW_FIXTURE_PATH),
        seo_fixture=read(generator.SEO_FIXTURE_PATH),
    )
