"""Fixtures for the isolated ST-1205 recorded KPI suite."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
import shutil
import sys
from typing import Any, cast

import pytest
import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
for candidate in (REPOSITORY_ROOT / "python", REPOSITORY_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))


from raos.adapters.recorded_kpi_input import (  # noqa: E402
    COMPLETE_FIXTURE_BYTES,
    COMPLETE_FIXTURE_SHA256,
    RecordedKpiInputAdapter,
)
from raos.application.analytics.kpi_read_model import (  # noqa: E402
    RecordedKpiCalculationJob,
)
from raos.domain.analytics.kpi_read_model import (  # noqa: E402
    AttributionBasis,
    CalculationContext,
    COMPLETE_RECORDED_INPUT_SHA256,
    FixtureByteLength,
    KpiCalculationCommand,
    KpiReadModelSnapshot,
    MeasurementPeriod,
    ProgramId,
    RAKUTEN_BLOG_PROGRAM,
    Sha256Digest,
)
from scripts import build_st1205_kpi_read_model_reference_plan as builder  # noqa: E402


@pytest.fixture
def fixture_bytes() -> bytes:
    return (REPOSITORY_ROOT / builder.FIXTURE_PATH).read_bytes()


@pytest.fixture
def fixture_document(fixture_bytes: bytes) -> dict[str, Any]:
    value = json.loads(fixture_bytes)
    if type(value) is not dict:
        raise TypeError("invalid ST-1205 fixture")
    return cast(dict[str, Any], value)


@pytest.fixture
def command() -> KpiCalculationCommand:
    return KpiCalculationCommand(
        recording_id="complete",
        fixture_digest=Sha256Digest(COMPLETE_FIXTURE_SHA256),
        fixture_length=FixtureByteLength(COMPLETE_FIXTURE_BYTES),
        expected_input_digest=Sha256Digest(COMPLETE_RECORDED_INPUT_SHA256),
        context=CalculationContext(
            MeasurementPeriod(date(2026, 7, 1), date(2026, 7, 31)),
            ProgramId(RAKUTEN_BLOG_PROGRAM),
            AttributionBasis.DIRECT,
        ),
    )


@pytest.fixture
def snapshot(
    fixture_bytes: bytes, command: KpiCalculationCommand
) -> KpiReadModelSnapshot:
    return RecordedKpiCalculationJob(
        exchange=RecordedKpiInputAdapter(fixture_bytes)
    ).calculate(command)


@pytest.fixture
def contract() -> dict[str, Any]:
    value = yaml.safe_load((REPOSITORY_ROOT / builder.CONTRACT_PATH).read_text())
    if type(value) is not dict:
        raise TypeError("invalid ST-1205 contract")
    return cast(dict[str, Any], value)


def copy_owner_root(destination: Path, *, include_outputs: bool = True) -> Path:
    paths = {
        *builder.SOURCE_PATHS,
        *builder.AUTHORITY_HASHES,
        *builder.PREDECESSOR_HASHES,
        builder.LEGACY_CONTRACT_PATH,
        builder.LEGACY_REFERENCE_PATH,
        Path("scripts/build_st1505_staging_deployment.py"),
    }
    if include_outputs:
        paths.update(builder.GENERATED_PATHS)
    for relative in paths:
        source = REPOSITORY_ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return destination


@pytest.fixture
def isolated_root(tmp_path: Path) -> Path:
    return copy_owner_root(tmp_path)
