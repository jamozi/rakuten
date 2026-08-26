from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from raos.adapters.recorded_attribution import (
    RecordedAttributionScenario,
    load_recorded_attribution_fixture,
)
from raos.domain.finance.attribution import (
    AttributionFailure,
    AttributionFailureCode,
    MeasurementAttributionContract,
)
from scripts import build_st1303_attribution_engine as generator


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)


@pytest.fixture(scope="session")
def measurement_contract() -> MeasurementAttributionContract:
    return generator.load_contract(ROOT)[1]


@pytest.fixture()
def scenario(
    measurement_contract: MeasurementAttributionContract,
) -> RecordedAttributionScenario:
    return load_recorded_attribution_fixture(
        FIXTURE.resolve(), contract=measurement_contract
    )


def failure_code(action: Callable[[], object]) -> AttributionFailureCode:
    with pytest.raises(AttributionFailure) as captured:
        action()
    assert str(captured.value) == captured.value.code.value
    assert "{" not in str(captured.value)
    return captured.value.code
