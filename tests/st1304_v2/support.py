from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from raos.adapters.recorded_unit_economics import (
    RecordedUnitEconomicsScenario,
    load_recorded_unit_economics_fixture,
)
from raos.domain.finance.attribution import MeasurementAttributionContract
from raos.domain.finance.unit_economics import (
    UnitEconomicsFailure,
    UnitEconomicsFailureCode,
)
from scripts import build_st1303_attribution_engine as st1303


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "changes/st-1304/fixtures/cost-unit-economics-recorded.synthetic.v2.json"
)
ATTRIBUTION_FIXTURE = (
    ROOT / "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)


@pytest.fixture(scope="session")
def measurement_contract() -> MeasurementAttributionContract:
    return st1303.load_contract(ROOT)[1]


@pytest.fixture()
def scenario(
    measurement_contract: MeasurementAttributionContract,
) -> RecordedUnitEconomicsScenario:
    return load_recorded_unit_economics_fixture(
        FIXTURE.resolve(),
        attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
        contract=measurement_contract,
    )


def failure_code(action: Callable[[], object]) -> UnitEconomicsFailureCode:
    with pytest.raises(UnitEconomicsFailure) as captured:
        action()
    assert str(captured.value) == captured.value.code.value
    assert "{" not in str(captured.value)
    return captured.value.code
