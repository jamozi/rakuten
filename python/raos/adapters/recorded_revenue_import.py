"""One-shot parser for the exact synthetic ST-1301 CSV profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import re
from threading import Lock
from typing import NoReturn, SupportsIndex, final

from raos.domain.finance.revenue_import import (
    FormulaDetectionStatus,
    RevenueDecision,
    RevenueDryRunState,
    RevenueEventType,
    RevenueExecutionStatus,
    RevenueFactStatus,
    RevenueImportFailure,
    RevenueImportFailureCode,
    RevenueMappingStatus,
    RevenueObservedSum,
    RevenueProviderCode,
    RevenueRowCode,
    RevenueRowParseStatus,
    RevenueRowPreview,
    RevenueSourceStatus,
    SyntheticPeriodLabel,
    SyntheticRevenueDryRun,
    SyntheticRevenueParseCommand,
    SyntheticRevenuePeriod,
    SyntheticRevenueProfile,
    SyntheticRevenueSourceReference,
    fail_revenue_import,
)
from raos.domain.ops.object_intake import Sha256Digest


_HEADER = (
    b"synthetic_fixture,provider_code,provider_event_key,event_type,event_at,"
    b"currency,generated_commission_jpy,confirmed_commission_jpy"
)
_EVENT_KEY = re.compile(r"synthetic-event-[0-9]{4}\Z")
_UTC_SECOND = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
_MAX_AMOUNT = (1 << 63) - 1
_FORMULA_PREFIXES = (b"=", b"+", b"-", b"@")
_REDACTED = "<redacted-recorded-revenue-fixture>"


@dataclass(frozen=True, slots=True, repr=False)
class RecordedRevenueFixture:
    """Private synthetic bytes bound to one exact command."""

    command: SyntheticRevenueParseCommand
    payload: bytes

    def __post_init__(self) -> None:
        if (
            type(self.command) is not SyntheticRevenueParseCommand
            or type(self.payload) is not bytes
            or not self.payload
        ):
            fail_revenue_import()

    def __repr__(self) -> str:
        return f"RecordedRevenueFixture({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded revenue fixture serialization is not supported")


def _row_preview(
    *,
    row_no: int,
    row_bytes: bytes,
    status: RevenueRowParseStatus,
    code: RevenueRowCode,
    event_type: RevenueEventType | None = None,
    event_at: datetime | None = None,
    generated: int | None = None,
    confirmed: int | None = None,
) -> RevenueRowPreview:
    return RevenueRowPreview(
        row_no=row_no,
        row_sha256=Sha256Digest(hashlib.sha256(row_bytes).hexdigest()),
        status=status,
        code=code,
        event_type=event_type,
        event_at=event_at,
        generated_commission_jpy=generated,
        confirmed_commission_jpy=confirmed,
    )


def _amount(value: str) -> int:
    if _DECIMAL.fullmatch(value) is None:
        fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
    parsed = int(value)
    if parsed > _MAX_AMOUNT:
        fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
    return parsed


def _timestamp(value: str) -> datetime:
    if _UTC_SECOND.fullmatch(value) is None:
        fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)


@final
class RecordedRevenueParserAdapter:
    """Consume one exact fixture once; never read a path, provider, or repository."""

    __slots__ = ("_command", "_consumed", "_lock", "_payload")

    def __init__(self, fixture: RecordedRevenueFixture) -> None:
        if type(fixture) is not RecordedRevenueFixture:
            fail_revenue_import()
        self._command = fixture.command
        self._payload = fixture.payload
        self._consumed = False
        self._lock = Lock()

    def _consume(self, command: SyntheticRevenueParseCommand) -> bytes:
        with self._lock:
            if self._consumed or type(command) is not SyntheticRevenueParseCommand:
                fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
            self._consumed = True
            if command != self._command:
                fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
            return self._payload

    @staticmethod
    def _validate_document(
        payload: bytes, command: SyntheticRevenueParseCommand
    ) -> list[bytes]:
        if (
            len(payload) != command.source_size
            or hashlib.sha256(payload).hexdigest() != command.source_sha256.value
            or payload.startswith(b"\xef\xbb\xbf")
            or not payload.endswith(b"\n")
            or b"\r" in payload
            or b"\x00" in payload
            or any(byte < 32 and byte not in {10} for byte in payload)
        ):
            fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
        lines = payload[:-1].split(b"\n")
        if (
            not lines
            or lines[0] != _HEADER
            or any(not line for line in lines)
            or len(lines) != command.expected_row_count
        ):
            fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
        cells = tuple(cell for line in lines for cell in line.split(b","))
        if max(len(cell) for cell in cells) != command.expected_max_cell_bytes or any(
            cell.startswith(_FORMULA_PREFIXES) for cell in cells
        ):
            fail_revenue_import(RevenueImportFailureCode.PARSER_REJECTED)
        return lines

    @staticmethod
    def _parse_rows(lines: list[bytes]) -> tuple[RevenueRowPreview, ...]:
        previews: list[RevenueRowPreview] = []
        row_hashes: set[str] = set()
        event_keys: dict[str, str] = {}
        for row_no, row_bytes in enumerate(lines[1:], start=2):
            row_digest = hashlib.sha256(row_bytes).hexdigest()
            if row_digest in row_hashes:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.DUPLICATE,
                        code=RevenueRowCode.EXACT_ROW_DUPLICATE,
                    )
                )
                continue
            row_hashes.add(row_digest)
            if b'"' in row_bytes:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.REJECTED,
                        code=RevenueRowCode.INVALID_ROW,
                    )
                )
                continue
            cells = row_bytes.decode("utf-8").split(",")
            if len(cells) != 8:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.REJECTED,
                        code=RevenueRowCode.INVALID_ROW,
                    )
                )
                continue
            (
                marker,
                provider,
                event_key,
                event_name,
                event_time,
                currency,
                generated_raw,
                confirmed_raw,
            ) = cells
            valid_identity = (
                marker == SyntheticRevenueProfile.RAOS_ST1301_SYNTHETIC_V1.value
                and provider == RevenueProviderCode.RAKUTEN_AFFILIATE.value
                and _EVENT_KEY.fullmatch(event_key) is not None
                and event_name in {value.value for value in RevenueEventType}
                and currency == "JPY"
            )
            if not valid_identity:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.REJECTED,
                        code=RevenueRowCode.INVALID_ROW,
                    )
                )
                continue
            previous_digest = event_keys.get(event_key)
            if previous_digest is not None and previous_digest != row_digest:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.REJECTED,
                        code=RevenueRowCode.EVENT_KEY_CONFLICT,
                    )
                )
                continue
            try:
                event_at = _timestamp(event_time)
                generated = _amount(generated_raw)
                confirmed = None if confirmed_raw == "" else _amount(confirmed_raw)
                event_type = RevenueEventType(event_name)
            except RevenueImportFailure:
                previews.append(
                    _row_preview(
                        row_no=row_no,
                        row_bytes=row_bytes,
                        status=RevenueRowParseStatus.REJECTED,
                        code=RevenueRowCode.INVALID_ROW,
                    )
                )
                continue
            event_keys[event_key] = row_digest
            previews.append(
                _row_preview(
                    row_no=row_no,
                    row_bytes=row_bytes,
                    status=RevenueRowParseStatus.ACCEPTED,
                    code=RevenueRowCode.ACCEPTED,
                    event_type=event_type,
                    event_at=event_at,
                    generated=generated,
                    confirmed=confirmed,
                )
            )
        return tuple(previews)

    @staticmethod
    def _build(
        command: SyntheticRevenueParseCommand, previews: tuple[RevenueRowPreview, ...]
    ) -> SyntheticRevenueDryRun:
        accepted = tuple(
            value
            for value in previews
            if value.status is RevenueRowParseStatus.ACCEPTED
        )
        summaries: list[RevenueObservedSum] = []
        for event_type in RevenueEventType:
            rows = tuple(value for value in accepted if value.event_type is event_type)
            confirmed_values = tuple(
                value.confirmed_commission_jpy
                for value in rows
                if value.confirmed_commission_jpy is not None
            )
            summaries.append(
                RevenueObservedSum(
                    event_type=event_type,
                    row_count=len(rows),
                    generated_commission_jpy=sum(
                        value.generated_commission_jpy or 0 for value in rows
                    ),
                    confirmed_commission_jpy=(
                        sum(confirmed_values) if confirmed_values else None
                    ),
                    confirmed_missing_count=sum(
                        value.confirmed_commission_jpy is None for value in rows
                    ),
                )
            )
        dates = tuple(
            value.event_at.date()
            for value in accepted
            if type(value.event_at) is datetime
        )
        source = SyntheticRevenueSourceReference(
            intake_id=command.intake_id,
            site_id=command.site_id,
            source_sha256=command.source_sha256,
            source_size=command.source_size,
            profile=command.profile,
            command_fingerprint=command.canonical_fingerprint,
            csv_row_count=command.expected_row_count,
            csv_column_count=command.expected_column_count,
            csv_max_cell_bytes=command.expected_max_cell_bytes,
            is_dry_run=True,
        )
        return SyntheticRevenueDryRun(
            source=source,
            state=RevenueDryRunState.SYNTHETIC_DRY_RUN_READY,
            previews=previews,
            row_count=len(previews),
            accepted_count=sum(
                value.status is RevenueRowParseStatus.ACCEPTED for value in previews
            ),
            rejected_count=sum(
                value.status is RevenueRowParseStatus.REJECTED for value in previews
            ),
            duplicate_count=sum(
                value.status is RevenueRowParseStatus.DUPLICATE for value in previews
            ),
            ignored_count=sum(
                value.status is RevenueRowParseStatus.IGNORED for value in previews
            ),
            observed_sums=tuple(summaries),
            period=SyntheticRevenuePeriod(
                label=SyntheticPeriodLabel.SYNTHETIC_OBSERVED_RANGE,
                period_from=min(dates) if dates else None,
                period_to=max(dates) if dates else None,
            ),
            formula_detection=FormulaDetectionStatus.NOT_DETECTED,
            source_status=RevenueSourceStatus.NEW,
            execution=RevenueExecutionStatus.SYNTHETIC_FIXTURE_ONLY,
            mapping=RevenueMappingStatus.UNVERIFIED,
            reconciliation=RevenueExecutionStatus.NOT_EXECUTED,
            persistence=RevenueExecutionStatus.NOT_EXECUTED,
            audit=RevenueExecutionStatus.NOT_EXECUTED,
            outbox=RevenueExecutionStatus.NOT_EXECUTED,
            events=RevenueExecutionStatus.NOT_EXECUTED,
            facts=RevenueFactStatus.NOT_CREATED,
            tst026=RevenueExecutionStatus.NOT_EXECUTED,
            tst030=RevenueExecutionStatus.NOT_EXECUTED,
            decision=RevenueDecision.NOT_READY,
            provider_total_jpy=None,
            revenue_import_id=None,
            source_artifact_id=None,
            approval_id=None,
        )

    def parse(self, command: SyntheticRevenueParseCommand) -> SyntheticRevenueDryRun:
        payload = self._consume(command)
        lines = self._validate_document(payload, command)
        previews = self._parse_rows(lines)
        return self._build(command, previews)


__all__ = ["RecordedRevenueFixture", "RecordedRevenueParserAdapter"]
