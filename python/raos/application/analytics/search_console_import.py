"""Application boundary for one source-bound recorded Search Console page."""

from __future__ import annotations

from typing import final

from raos.domain.analytics.search_console import (
    RecordedPageComparison,
    RecordedSearchConsolePage,
    SearchConsoleBoundaryStatus,
    SearchConsoleCommand,
    SearchConsoleFailure,
    SearchConsoleFailureCode,
    SearchConsoleImportReference,
    SearchConsoleRequest,
    SearchConsoleRow,
    compare_recorded_pages,
    fail_search_console,
)
from raos.domain.portfolio.workflow import UtcTimestamp
from raos.ports.search_console import RecordedSearchConsoleExchange


def _validated_command(candidate: object) -> SearchConsoleCommand:
    if type(candidate) is not SearchConsoleCommand:
        fail_search_console()
    normalized: SearchConsoleCommand | None = None
    invalid = False
    try:
        request = SearchConsoleRequest(
            site_url=candidate.request.site_url,
            start_date=candidate.request.start_date,
            end_date=candidate.request.end_date,
            dimensions=tuple(candidate.request.dimensions),
            search_type=candidate.request.search_type,
            aggregation_type=candidate.request.aggregation_type,
            data_state=candidate.request.data_state,
            row_limit=candidate.request.row_limit,
            start_row=candidate.request.start_row,
            dimension_filter_groups=tuple(candidate.request.dimension_filter_groups),
        )
        normalized = SearchConsoleCommand(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            request=request,
        )
    except SearchConsoleFailure:
        raise
    except Exception:
        invalid = True
    if invalid or normalized is None:
        fail_search_console()
    return normalized


def _validated_page(
    candidate: object,
    command: SearchConsoleCommand,
) -> RecordedSearchConsolePage:
    if type(candidate) is not RecordedSearchConsolePage:
        fail_search_console(SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH)
    page: RecordedSearchConsolePage | None = None
    invalid = False
    try:
        rows = tuple(
            SearchConsoleRow(
                site_id=row.site_id,
                date_from=row.date_from,
                date_to=row.date_to,
                dimensions=tuple(row.dimensions),
                keys=tuple(row.keys),
                clicks=row.clicks,
                impressions=row.impressions,
                ctr=row.ctr,
                position=row.position,
                data_state=row.data_state,
                imported_at=UtcTimestamp(row.imported_at.value),
                is_top_rows_limited=row.is_top_rows_limited,
                source_request_sha256=row.source_request_sha256,
            )
            for row in candidate.rows
            if type(row) is SearchConsoleRow
        )
        if len(rows) != len(candidate.rows):
            fail_search_console(SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH)
        page = RecordedSearchConsolePage(
            recording_id=candidate.recording_id,
            fixture_digest=candidate.fixture_digest,
            fixture_length=candidate.fixture_length,
            request=candidate.request,
            request_digest=candidate.request_digest,
            response_aggregation_type=candidate.response_aggregation_type,
            recorded_at=UtcTimestamp(candidate.recorded_at.value),
            pagination=candidate.pagination,
            rows=rows,
            top_rows_only=candidate.top_rows_only,
            rows_not_guaranteed_complete=candidate.rows_not_guaranteed_complete,
        )
    except SearchConsoleFailure:
        raise
    except Exception:
        invalid = True
    if invalid or page is None:
        fail_search_console(SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH)
    if (
        page.recording_id != command.recording_id
        or page.fixture_digest != command.fixture_digest
        or page.fixture_length != command.fixture_length
        or page.request != command.request
        or page.request_digest != command.request.sha256
    ):
        fail_search_console(SearchConsoleFailureCode.RECORDED_RESULT_MISMATCH)
    return page


@final
class SearchConsoleRecordedImport:
    """Validate and consume exactly one recorded fixture exchange."""

    __slots__ = ("_exchange",)

    def __init__(self, *, exchange: RecordedSearchConsoleExchange) -> None:
        if not callable(getattr(exchange, "exchange", None)):
            fail_search_console()
        self._exchange = exchange

    def import_recording(
        self,
        command: SearchConsoleCommand,
    ) -> SearchConsoleImportReference:
        normalized = _validated_command(command)
        observed: object = None
        unavailable = False
        try:
            observed = self._exchange.exchange(normalized)
        except Exception:
            unavailable = True
        if unavailable:
            fail_search_console(SearchConsoleFailureCode.RECORDED_EXCHANGE_UNAVAILABLE)
        page = _validated_page(observed, normalized)
        return SearchConsoleImportReference(
            page=page,
            execution=SearchConsoleBoundaryStatus.RECORDED_FIXTURE_ONLY,
            provider=SearchConsoleBoundaryStatus.NOT_EXECUTED,
            credentials=SearchConsoleBoundaryStatus.NOT_USED,
            import_run=SearchConsoleBoundaryStatus.NOT_CREATED,
            persistence=SearchConsoleBoundaryStatus.NOT_EXECUTED,
            supersession=SearchConsoleBoundaryStatus.NOT_DEFINED,
            audit=SearchConsoleBoundaryStatus.NOT_EXECUTED,
            outbox=SearchConsoleBoundaryStatus.NOT_EXECUTED,
            formal_tst_030=SearchConsoleBoundaryStatus.NOT_EXECUTED,
            decision=SearchConsoleBoundaryStatus.NOT_READY,
        )


def compare_recorded_imports(
    baseline: SearchConsoleImportReference,
    revised: SearchConsoleImportReference,
) -> RecordedPageComparison:
    if (
        type(baseline) is not SearchConsoleImportReference
        or type(revised) is not SearchConsoleImportReference
    ):
        fail_search_console()
    return compare_recorded_pages(baseline.page, revised.page)


__all__ = ["SearchConsoleRecordedImport", "compare_recorded_imports"]
