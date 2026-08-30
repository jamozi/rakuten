"""Shared exact ST-1804 fixture and typed mutation helpers."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable, cast

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "python"))

from raos.adapters.recorded_gate3_economics import (  # noqa: E402
    RecordedGate3EconomicsAdapter,
)
from raos.application.analytics.gate3_economics import (  # noqa: E402
    RecordedGate3EconomicsJob,
)
from raos.domain.analytics.gate3_economics import (  # noqa: E402
    CohortMaturity,
    FixtureByteLength,
    Gate3Command,
    Gate3EconomicsReport,
    MetricValue,
    MonthObservation,
    MonthPeriod,
    PROGRAM,
    RecordedEconomicsBatch,
    Sha256Digest,
    ValueState,
    canonical_entry_digest,
    canonical_input_digest,
)


CONTRACT_DIGEST = Sha256Digest(
    "7a5a43f3ef8c42ea2fcff3ebe53f8d38a2c30491b19fd163fa2b468197d2484a"
)
INPUT_DIGEST = Sha256Digest(
    "a532e84c3be3d656978a8168047a8e4df94c872fd78d703137f399c77e0199b2"
)
FIXTURE_PATH = REPOSITORY_ROOT / (
    "changes/st-1804/fixtures/recorded-synthetic-gate3-economics.v1.json"
)


@pytest.fixture
def fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


@pytest.fixture
def command(fixture_bytes: bytes) -> Gate3Command:
    return Gate3Command(
        recording_id="three-month-synthetic-threshold-vector",
        fixture_digest=Sha256Digest.of(fixture_bytes),
        fixture_length=FixtureByteLength(len(fixture_bytes)),
        contract_digest=CONTRACT_DIGEST,
        expected_input_digest=INPUT_DIGEST,
        program_id=PROGRAM,
    )


@pytest.fixture
def batch(fixture_bytes: bytes, command: Gate3Command) -> RecordedEconomicsBatch:
    return RecordedGate3EconomicsAdapter(fixture_bytes).read(command)


@pytest.fixture
def report(fixture_bytes: bytes, command: Gate3Command) -> Gate3EconomicsReport:
    return RecordedGate3EconomicsJob(
        exchange=RecordedGate3EconomicsAdapter(fixture_bytes)
    ).evaluate(command)


def clone_month(
    source: MonthObservation,
    *,
    previous_entry_sha256: Sha256Digest | None = None,
    period: MonthPeriod | None = None,
    program_id: str | None = None,
    cohort_maturity: CohortMaturity | None = None,
    attribution_verified: bool | None = None,
    cost_basis_verified: bool | None = None,
    metrics: tuple[MetricValue, ...] | None = None,
) -> MonthObservation:
    previous = previous_entry_sha256 or source.previous_entry_sha256
    observed_period = period or source.period
    observed_program = program_id or source.program_id
    maturity = cohort_maturity or source.cohort_maturity
    attribution = (
        source.attribution_verified
        if attribution_verified is None
        else attribution_verified
    )
    cost = (
        source.cost_basis_verified
        if cost_basis_verified is None
        else cost_basis_verified
    )
    observed_metrics = metrics or source.metrics
    payload: dict[str, object] = {
        "attribution_verified": attribution,
        "cohort_maturity": maturity.value,
        "cost_basis_verified": cost,
        "metrics": [metric.payload() for metric in observed_metrics],
        "period": observed_period.payload(),
        "program": observed_program,
    }
    entry = canonical_entry_digest(
        sequence=source.sequence,
        previous_entry_sha256=previous,
        payload=payload,
    )
    return MonthObservation(
        sequence=source.sequence,
        previous_entry_sha256=previous,
        entry_sha256=entry,
        period=observed_period,
        program_id=observed_program,
        cohort_maturity=maturity,
        attribution_verified=attribution,
        cost_basis_verified=cost,
        metrics=observed_metrics,
    )


_UNSET = object()


def replace_metric(
    source: MonthObservation,
    key: str,
    *,
    state: ValueState | None = None,
    value: int | None | object = _UNSET,
    source_sha256: Sha256Digest | None | object = _UNSET,
) -> MonthObservation:
    metrics = tuple(
        MetricValue(
            metric_key=metric.metric_key,
            state=metric.state if state is None else state,
            value=(metric.value if value is _UNSET else cast(int | None, value)),
            source=metric.source,
            source_sha256=(
                metric.source_sha256
                if source_sha256 is _UNSET
                else cast(Sha256Digest | None, source_sha256)
            ),
        )
        if metric.metric_key == key
        else metric
        for metric in source.metrics
    )
    return clone_month(source, metrics=metrics)


def rebuild_batch(
    source: RecordedEconomicsBatch,
    transform: Callable[[MonthObservation], MonthObservation],
) -> RecordedEconomicsBatch:
    months: list[MonthObservation] = []
    previous = Sha256Digest("0" * 64)
    for original in source.months:
        changed = transform(original)
        changed = clone_month(changed, previous_entry_sha256=previous)
        months.append(changed)
        previous = changed.entry_sha256
    normalized = tuple(months)
    return RecordedEconomicsBatch(
        recording_id=source.recording_id,
        recorded_at=source.recorded_at,
        fixture_digest=source.fixture_digest,
        fixture_length=source.fixture_length,
        contract_digest=source.contract_digest,
        input_digest=canonical_input_digest(normalized),
        context_program=source.context_program,
        months=normalized,
        synthetic=True,
        actual_observation=False,
        append_only=True,
        immutable=True,
    )


__all__ = [
    "CONTRACT_DIGEST",
    "FIXTURE_PATH",
    "INPUT_DIGEST",
    "REPOSITORY_ROOT",
    "clone_month",
    "rebuild_batch",
    "replace_metric",
]
