"""Shared fixtures for the isolated ST-0905 reference-plan suite."""

from __future__ import annotations

from pathlib import Path
import shutil
import sys

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPOSITORY_ROOT, REPOSITORY_ROOT / "python"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from scripts import build_st0905_publication_commands_reference_plan as generator  # noqa: E402
from scripts import (  # noqa: E402
    build_st0905_publication_commands_runtime_v2 as runtime_generator,
)
from raos.adapters.publishing.recorded_publication_command_fixture_v2 import (  # noqa: E402
    RecordedPublicationCommandScenarioV2,
    build_recorded_publication_command_scenario_v2,
)


def read(relative: Path) -> bytes:
    return (REPOSITORY_ROOT / relative).read_bytes()


@pytest.fixture(scope="session")
def runtime_scenario() -> RecordedPublicationCommandScenarioV2:
    return build_recorded_publication_command_scenario_v2(
        st0903_fixture=read(runtime_generator.ST0903_FIXTURE_PATH),
        st0904_fixture=read(runtime_generator.ST0904_FIXTURE_PATH),
        final_approval_fixture=read(runtime_generator.FINAL_APPROVAL_FIXTURE_PATH),
        policy_fixture=read(runtime_generator.POLICY_FIXTURE_PATH),
        review_fixture=read(runtime_generator.REVIEW_FIXTURE_PATH),
        seo_fixture=read(runtime_generator.SEO_FIXTURE_PATH),
    )


@pytest.fixture()
def isolated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    required = {
        *generator.SOURCE_PATHS,
        generator.HELPER_PATH,
        *(Path(path) for _role, path, _digest in generator.EXPECTED_SOURCES),
        *(Path(path) for _story_id, path, _digest in generator.DEPENDENCY_INPUTS),
    }
    for relative in required:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / relative, target)
    return root
