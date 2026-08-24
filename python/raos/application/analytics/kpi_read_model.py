"""Application job for the recorded-only ST-1205 KPI read model."""

from __future__ import annotations

from typing import final

from raos.domain.analytics.kpi_read_model import (
    CalculationContext,
    KpiBoundaryStatus,
    KpiCalculationCommand,
    KpiFailure,
    KpiFailureCode,
    KpiInputFrame,
    KpiReadModelSnapshot,
    MetricObservation,
    RecordedKpiInputBatch,
    calculate_learning_rows,
    calculate_rows,
    fail_kpi,
)
from raos.ports.kpi_read_model import RecordedKpiInputExchange


def _validated_command(candidate: object) -> KpiCalculationCommand:
    if type(candidate) is not KpiCalculationCommand:
        fail_kpi()
    try:
        return KpiCalculationCommand(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            expected_input_digest=candidate.expected_input_digest,
            context=CalculationContext(
                period=candidate.context.period,
                program_id=candidate.context.program_id,
                selected_attribution_basis=candidate.context.selected_attribution_basis,
            ),
            definition_version=candidate.definition_version,
            calculation_version=candidate.calculation_version,
        )
    except KpiFailure:
        raise
    except Exception:
        fail_kpi()


def _validated_batch(
    candidate: object, command: KpiCalculationCommand
) -> RecordedKpiInputBatch:
    if type(candidate) is not RecordedKpiInputBatch:
        fail_kpi(KpiFailureCode.RECORDED_RESULT_MISMATCH)
    try:
        observations = tuple(
            MetricObservation(
                metric_key=item.metric_key,
                value=item.value,
                source=item.source,
                period=item.period,
                program_id=item.program_id,
                verified=item.verified,
                cohort_state=item.cohort_state,
                attribution_basis=item.attribution_basis,
                attribution_verified=item.attribution_verified,
            )
            for item in candidate.input_frame.observations
            if type(item) is MetricObservation
        )
        if len(observations) != len(candidate.input_frame.observations):
            fail_kpi(KpiFailureCode.RECORDED_RESULT_MISMATCH)
        normalized = RecordedKpiInputBatch(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            recorded_at=candidate.recorded_at,
            context=CalculationContext(
                period=candidate.context.period,
                program_id=candidate.context.program_id,
                selected_attribution_basis=candidate.context.selected_attribution_basis,
            ),
            input_frame=KpiInputFrame(observations),
        )
    except KpiFailure:
        raise
    except Exception:
        fail_kpi(KpiFailureCode.RECORDED_RESULT_MISMATCH)
    if (
        normalized.recording_id != command.recording_id
        or normalized.fixture_digest != command.fixture_digest
        or normalized.fixture_length != command.fixture_length
        or normalized.input_frame.sha256 != command.expected_input_digest
        or normalized.context != command.context
    ):
        fail_kpi(KpiFailureCode.RECORDED_RESULT_MISMATCH)
    return normalized


@final
class RecordedKpiCalculationJob:
    """Consume one recorded batch and return a non-persisted immutable snapshot."""

    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: RecordedKpiInputExchange) -> None:
        if not callable(getattr(exchange, "read", None)):
            fail_kpi()
        self._exchange = exchange

    def calculate(self, command: KpiCalculationCommand) -> KpiReadModelSnapshot:
        normalized_command = _validated_command(command)
        observed: object = None
        try:
            observed = self._exchange.read(normalized_command)
        except KpiFailure:
            raise
        except Exception:
            fail_kpi(KpiFailureCode.RECORDED_EXCHANGE_UNAVAILABLE)
        batch = _validated_batch(observed, normalized_command)
        rows = calculate_rows(batch.input_frame, batch.context)
        learning_rows = calculate_learning_rows(rows, batch.input_frame, batch.context)
        return KpiReadModelSnapshot(
            recording_id=batch.recording_id,
            fixture_digest=batch.fixture_digest,
            input_digest=batch.input_frame.sha256,
            recorded_at=batch.recorded_at,
            context=batch.context,
            rows=rows,
            learning_rows=learning_rows,
            execution=KpiBoundaryStatus.RECORDED_FIXTURE_ONLY,
            read_model=KpiBoundaryStatus.IN_MEMORY_ONLY,
            persistence=KpiBoundaryStatus.NOT_EXECUTED,
            provider=KpiBoundaryStatus.NOT_EXECUTED,
            network=KpiBoundaryStatus.NOT_EXECUTED,
            public_projection=KpiBoundaryStatus.NOT_EXECUTED,
            recommendation_input=KpiBoundaryStatus.DISABLED,
            formal_tst_030=KpiBoundaryStatus.NOT_EXECUTED,
            decision=KpiBoundaryStatus.NOT_READY,
        )


__all__ = ["RecordedKpiCalculationJob"]
