from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, cast

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPO_ROOT, REPO_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import (  # noqa: E402
    build_st0904_public_projection_runtime_v2 as generator,
)
from raos.adapters.recorded_public_projection_v2 import (  # noqa: E402
    RecordedPublicProjectionStep,
    build_recorded_public_projection_step,
)
from raos.adapters.recorded_publication_snapshot_v2 import (  # noqa: E402
    load_recorded_publication_snapshot_fixture,
)


def read(path: Path) -> bytes:
    return (REPO_ROOT / path).read_bytes()


@pytest.fixture(scope="session")
def contract() -> dict[str, Any]:
    return cast(dict[str, Any], generator.load_contract(REPO_ROOT))


@pytest.fixture(scope="session")
def step() -> RecordedPublicProjectionStep:
    snapshot = read(generator.ST0903_FIXTURE_PATH)
    snapshot_step = load_recorded_publication_snapshot_fixture(
        snapshot,
        final_approval_fixture=read(generator.FINAL_APPROVAL_FIXTURE_PATH),
        policy_fixture=read(generator.POLICY_FIXTURE_PATH),
        review_fixture=read(generator.REVIEW_FIXTURE_PATH),
        seo_fixture=read(generator.SEO_FIXTURE_PATH),
    )
    return build_recorded_public_projection_step(
        snapshot_step,
        source_fixture_sha256=__import__("hashlib").sha256(snapshot).hexdigest(),
    )
