"""One-call application boundary for the recorded ST-1204 GA4 seam."""

from __future__ import annotations

from typing import final

from raos.domain.analytics.ga4 import (
    Ga4BoundaryStatus,
    Ga4Failure,
    Ga4FailureCode,
    Ga4ImportResult,
    Ga4MetricRow,
    Ga4PropertyConfigSnapshot,
    Ga4RecordedExchange,
    Ga4RecordedImportCommand,
    Ga4RecordedOutcome,
    Ga4RecordedRequest,
    Ga4UtcTimestamp,
    fail_ga4,
)
from raos.ports.ga4 import RecordedGa4ReportPort


def _validated_command(candidate: object) -> Ga4RecordedImportCommand:
    if type(candidate) is not Ga4RecordedImportCommand:
        fail_ga4()
    normalized: Ga4RecordedImportCommand | None = None
    invalid = False
    try:
        request = Ga4RecordedRequest(
            property_id=candidate.request.property_id,
            date_ranges=tuple(candidate.request.date_ranges),
            dimensions=tuple(candidate.request.dimensions),
            metrics=tuple(candidate.request.metrics),
            dimension_filter=candidate.request.dimension_filter,
            metric_filter=candidate.request.metric_filter,
            order_bys=tuple(candidate.request.order_bys),
            limit=candidate.request.limit,
            offset=candidate.request.offset,
            keep_empty_rows=candidate.request.keep_empty_rows,
            return_property_quota=candidate.request.return_property_quota,
        )
        normalized = Ga4RecordedImportCommand(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            site_id=candidate.site_id,
            date_from=candidate.date_from,
            date_to=candidate.date_to,
            dimensions=tuple(candidate.dimensions),
            metrics=tuple(candidate.metrics),
            force_reimport=candidate.force_reimport,
            request=request,
        )
    except Ga4Failure:
        raise
    except Exception:
        invalid = True
    if invalid or normalized is None:
        fail_ga4()
    return normalized


def _copy_exchange(candidate: object) -> Ga4RecordedExchange:
    if type(candidate) is not Ga4RecordedExchange:
        fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
    copied: Ga4RecordedExchange | None = None
    invalid = False
    try:
        rows = tuple(
            Ga4MetricRow(
                site_id=row.site_id,
                property_id=row.property_id,
                date_from=row.date_from,
                date_to=row.date_to,
                date_range_index=row.date_range_index,
                dimensions=tuple(row.dimensions),
                metrics=tuple(row.metrics),
                dimension_values=tuple(row.dimension_values),
                metric_values=tuple(row.metric_values),
                imported_at=Ga4UtcTimestamp(row.imported_at.value),
                reporting_identity=row.reporting_identity,
                thresholding_applied=row.thresholding_applied,
                source_request_sha256=row.source_request_sha256,
            )
            for row in candidate.rows
            if type(row) is Ga4MetricRow
        )
        if len(rows) != len(candidate.rows):
            fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
        configuration = candidate.configuration
        if type(configuration) is Ga4PropertyConfigSnapshot:
            configuration = Ga4PropertyConfigSnapshot(
                property_resource=configuration.property_resource,
                reporting_identity=configuration.reporting_identity,
                reporting_identity_response_digest=(
                    configuration.reporting_identity_response_digest
                ),
                reporting_identity_retrieved_at=Ga4UtcTimestamp(
                    configuration.reporting_identity_retrieved_at.value
                ),
                currency_code=configuration.currency_code,
                time_zone=configuration.time_zone,
                subject_to_thresholding=configuration.subject_to_thresholding,
                data_loss_from_other_row=configuration.data_loss_from_other_row,
                empty_reason=configuration.empty_reason,
                sampling_metadata=tuple(configuration.sampling_metadata),
                quota=tuple(configuration.quota),
            )
        copied = Ga4RecordedExchange(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            request=candidate.request,
            response_digest=candidate.response_digest,
            run_report_retrieved_at=Ga4UtcTimestamp(
                candidate.run_report_retrieved_at.value
            ),
            recorded_at=Ga4UtcTimestamp(candidate.recorded_at.value),
            outcome=candidate.outcome,
            rows=rows,
            provider_row_count=candidate.provider_row_count,
            returned_row_count=candidate.returned_row_count,
            row_count_independent_of_pagination=(
                candidate.row_count_independent_of_pagination
            ),
            configuration=configuration,
            http_status=candidate.http_status,
        )
    except Ga4Failure:
        raise
    except Exception:
        invalid = True
    if invalid or copied is None:
        fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
    return copied


@final
class RecordedGa4Import:
    """Validate one exact command and consume one recorded port step."""

    __slots__ = ("_port",)

    def __init__(self, *, port: RecordedGa4ReportPort) -> None:
        if not callable(getattr(port, "read", None)):
            fail_ga4()
        self._port = port

    def import_recording(self, command: Ga4RecordedImportCommand) -> Ga4ImportResult:
        normalized = _validated_command(command)
        observed: object = None
        unavailable = False
        try:
            observed = self._port.read(
                recording_id=normalized.recording_id,
                request=normalized.request,
            )
        except Exception:
            unavailable = True
        if unavailable:
            fail_ga4(Ga4FailureCode.RECORDED_EXCHANGE_UNAVAILABLE)
        exchange = _copy_exchange(observed)
        if (
            exchange.recording_id != normalized.recording_id
            or exchange.fixture_digest != normalized.fixture_digest
            or exchange.fixture_length != normalized.fixture_length
            or exchange.request != normalized.request
        ):
            fail_ga4(Ga4FailureCode.RECORDED_RESULT_MISMATCH)
        configuration_status = (
            Ga4BoundaryStatus.IN_FIXTURE_ONLY
            if exchange.outcome is Ga4RecordedOutcome.RECORDED_SUCCESS
            else Ga4BoundaryStatus.NOT_CAPTURED_AFTER_ERROR
        )
        return Ga4ImportResult(
            exchange=exchange,
            execution_mode=Ga4BoundaryStatus.RECORDED_FIXTURE_ONLY,
            tracking=Ga4BoundaryStatus.DISABLED_OD_012,
            credentials=Ga4BoundaryStatus.NOT_USED,
            provider_execution=Ga4BoundaryStatus.NOT_EXECUTED,
            property_configuration=configuration_status,
            persistence=Ga4BoundaryStatus.NOT_EXECUTED,
            job_dispatch=Ga4BoundaryStatus.NOT_EXECUTED,
            event_publication=Ga4BoundaryStatus.NOT_EXECUTED,
            supersession=Ga4BoundaryStatus.NOT_DEFINED,
            formal_tst_030=Ga4BoundaryStatus.NOT_EXECUTED,
            decision=Ga4BoundaryStatus.NOT_READY,
        )


__all__ = ["RecordedGa4Import"]
