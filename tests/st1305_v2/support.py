from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from raos.adapters.recorded_finance_reconciliation import (
    RecordedFinanceReconciliationScenario,
    load_recorded_finance_reconciliation_fixture,
)
from raos.domain.finance.attribution import MeasurementAttributionContract
from raos.domain.finance.reconciliation import (
    FinanceReconciliationFailure,
    FinanceReconciliationFailureCode,
)
from scripts import build_st1303_attribution_engine as st1303


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = (
    ROOT / "changes/st-1305/fixtures/finance-reconciliation-recorded.synthetic.v2.json"
)
UNIT_ECONOMICS_FIXTURE = (
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
) -> RecordedFinanceReconciliationScenario:
    return load_recorded_finance_reconciliation_fixture(
        FIXTURE.resolve(),
        unit_economics_fixture_path=UNIT_ECONOMICS_FIXTURE.resolve(),
        attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
        contract=measurement_contract,
    )


def failure_code(action: Callable[[], object]) -> FinanceReconciliationFailureCode:
    with pytest.raises(FinanceReconciliationFailure) as captured:
        action()
    assert str(captured.value) == captured.value.code.value
    assert "{" not in str(captured.value)
    return captured.value.code
