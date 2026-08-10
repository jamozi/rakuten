"""Redacted values for the synthetic-only ST-1301 revenue dry-run seam."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
import hashlib
import json
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.ops.object_intake import Sha256Digest


_MAX_EXACT_INTEGER = (1 << 63) - 1
_REDACTED = "<redacted-revenue-import>"
MAX_SYNTHETIC_SOURCE_BYTES = 1_048_576
MAX_SYNTHETIC_CSV_ROWS = 10_000
SYNTHETIC_CSV_COLUMNS = 8
MAX_SYNTHETIC_CELL_BYTES = 4_096


class SyntheticRevenueProfile(str, Enum):
    """The only format supported by this local reference seam."""

    RAOS_ST1301_SYNTHETIC_V1 = "RAOS_ST1301_SYNTHETIC_V1"


class RevenueProviderCode(str, Enum):
    """Canonical provider vocabulary, not evidence of provider compatibility."""

    RAKUTEN_AFFILIATE = "RAKUTEN_AFFILIATE"


class RevenueEventType(str, Enum):
    GENERATED = "GENERATED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    ADJUSTED = "ADJUSTED"


class RevenueRowParseStatus(str, Enum):
    """ST-0305 parse-status vocabulary projected into a redacted preview."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    IGNORED = "IGNORED"


class RevenueRowCode(str, Enum):
    ACCEPTED = "ACCEPTED"
    INVALID_ROW = "INVALID_ROW"
    EXACT_ROW_DUPLICATE = "EXACT_ROW_DUPLICATE"
    EVENT_KEY_CONFLICT = "EVENT_KEY_CONFLICT"
    IGNORED_ROW = "IGNORED_ROW"


class RevenueDryRunState(str, Enum):
    SYNTHETIC_DRY_RUN_READY = "SYNTHETIC_DRY_RUN_READY"


class RevenueSourceStatus(str, Enum):
    NEW = "NEW"


class FormulaDetectionStatus(str, Enum):
    NOT_DETECTED = "NOT_DETECTED"


class RevenueMappingStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"


class RevenueExecutionStatus(str, Enum):
    SYNTHETIC_FIXTURE_ONLY = "SYNTHETIC_FIXTURE_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


class RevenueFactStatus(str, Enum):
    NOT_CREATED = "NOT_CREATED"


class RevenueDecision(str, Enum):
    NOT_READY = "NOT_READY"


class SyntheticPeriodLabel(str, Enum):
    SYNTHETIC_OBSERVED_RANGE = "SYNTHETIC_OBSERVED_RANGE"


class RevenueImportFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SOURCE_DUPLICATE_REJECTED = "SOURCE_DUPLICATE_REJECTED"
    PARSER_UNAVAILABLE = "PARSER_UNAVAILABLE"
    PARSER_REJECTED = "PARSER_REJECTED"
    PARSER_RESULT_INVALID = "PARSER_RESULT_INVALID"


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("revenue import serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class RevenueImportFailure(ValueError):
    """Closed failure which cannot retain rejected CSV material."""

    code: RevenueImportFailureCode

    def __post_init__(self) -> None:
        if type(self.code) is not RevenueImportFailureCode:
            raise TypeError("code must be an exact RevenueImportFailureCode")
        ValueError.__init__(self, self.code.value)

    def __repr__(self) -> str:
        return f"RevenueImportFailure(code={self.code.value})"

    def __str__(self) -> str:
        return self.code.value

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("revenue import failure serialization is not supported")


def fail_revenue_import(
    code: RevenueImportFailureCode = RevenueImportFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise RevenueImportFailure(code) from None


def _positive_exact_int(value: object) -> int:
    if type(value) is not int or not 0 < value <= _MAX_EXACT_INTEGER:
        fail_revenue_import()
    return value


def _nonnegative_exact_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_EXACT_INTEGER:
        fail_revenue_import()
    return value


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_revenue_import()
    return value


def _nonzero_uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_revenue_import()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRevenueParseCommand(_RedactedValue):
    """Identity-only parse command. It deliberately contains no bytes or path."""

    intake_id: UUID
    site_id: UUID
    source_sha256: Sha256Digest
    source_size: int
    profile: SyntheticRevenueProfile
    expected_row_count: int
    expected_column_count: int
    expected_max_cell_bytes: int

    def __post_init__(self) -> None:
        _nonzero_uuid(self.intake_id)
        _nonzero_uuid(self.site_id)
        if (
            type(self.source_sha256) is not Sha256Digest
            or type(self.profile) is not SyntheticRevenueProfile
        ):
            fail_revenue_import()
        _positive_exact_int(self.source_size)
        _positive_exact_int(self.expected_row_count)
        _positive_exact_int(self.expected_column_count)
        _positive_exact_int(self.expected_max_cell_bytes)
        if (
            self.source_size > MAX_SYNTHETIC_SOURCE_BYTES
            or not 2 <= self.expected_row_count <= MAX_SYNTHETIC_CSV_ROWS
            or self.expected_column_count != SYNTHETIC_CSV_COLUMNS
            or self.expected_max_cell_bytes > MAX_SYNTHETIC_CELL_BYTES
        ):
            fail_revenue_import()

    @property
    def canonical_fingerprint(self) -> Sha256Digest:
        payload = {
            "expected_column_count": self.expected_column_count,
            "expected_max_cell_bytes": self.expected_max_cell_bytes,
            "expected_row_count": self.expected_row_count,
            "intake_id": str(self.intake_id),
            "profile": self.profile.value,
            "site_id": str(self.site_id),
            "source_sha256": self.source_sha256.value,
            "source_size": self.source_size,
        }
        encoded = json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
        return Sha256Digest(hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRevenueSourceReference(_RedactedValue):
    intake_id: UUID
    site_id: UUID
    source_sha256: Sha256Digest
    source_size: int
    profile: SyntheticRevenueProfile
    command_fingerprint: Sha256Digest
    csv_row_count: int
    csv_column_count: int
    csv_max_cell_bytes: int
    is_dry_run: bool

    def __post_init__(self) -> None:
        _nonzero_uuid(self.intake_id)
        _nonzero_uuid(self.site_id)
        if (
            type(self.source_sha256) is not Sha256Digest
            or type(self.profile) is not SyntheticRevenueProfile
            or type(self.command_fingerprint) is not Sha256Digest
            or type(self.is_dry_run) is not bool
            or not self.is_dry_run
        ):
            fail_revenue_import()
        _positive_exact_int(self.source_size)
        _positive_exact_int(self.csv_row_count)
        _positive_exact_int(self.csv_column_count)
        _positive_exact_int(self.csv_max_cell_bytes)
        if (
            self.source_size > MAX_SYNTHETIC_SOURCE_BYTES
            or not 2 <= self.csv_row_count <= MAX_SYNTHETIC_CSV_ROWS
            or self.csv_column_count != SYNTHETIC_CSV_COLUMNS
            or self.csv_max_cell_bytes > MAX_SYNTHETIC_CELL_BYTES
        ):
            fail_revenue_import()


@dataclass(frozen=True, slots=True, repr=False)
class RevenueRowPreview(_RedactedValue):
    """A redacted preview. Provider keys and source cells never leave the adapter."""

    row_no: int
    row_sha256: Sha256Digest
    status: RevenueRowParseStatus
    code: RevenueRowCode
    event_type: RevenueEventType | None
    event_at: datetime | None
    generated_commission_jpy: int | None
    confirmed_commission_jpy: int | None

    def __post_init__(self) -> None:
        if (
            type(self.row_sha256) is not Sha256Digest
            or type(self.status) is not RevenueRowParseStatus
            or type(self.code) is not RevenueRowCode
            or (
                self.event_type is not None
                and type(self.event_type) is not RevenueEventType
            )
        ):
            fail_revenue_import()
        if _positive_exact_int(self.row_no) < 2:
            fail_revenue_import()
        accepted = self.status is RevenueRowParseStatus.ACCEPTED
        if accepted:
            if (
                self.code is not RevenueRowCode.ACCEPTED
                or type(self.event_type) is not RevenueEventType
                or self.event_at is None
                or self.generated_commission_jpy is None
            ):
                fail_revenue_import()
            _utc_second(self.event_at)
            _nonnegative_exact_int(self.generated_commission_jpy)
            if self.confirmed_commission_jpy is not None:
                _nonnegative_exact_int(self.confirmed_commission_jpy)
            return
        if (
            self.event_type is not None
            or self.event_at is not None
            or self.generated_commission_jpy is not None
            or self.confirmed_commission_jpy is not None
        ):
            fail_revenue_import()
        expected_codes = {
            RevenueRowParseStatus.REJECTED: {
                RevenueRowCode.INVALID_ROW,
                RevenueRowCode.EVENT_KEY_CONFLICT,
            },
            RevenueRowParseStatus.DUPLICATE: {RevenueRowCode.EXACT_ROW_DUPLICATE},
            RevenueRowParseStatus.IGNORED: {RevenueRowCode.IGNORED_ROW},
        }
        if self.code not in expected_codes[self.status]:
            fail_revenue_import()


@dataclass(frozen=True, slots=True, repr=False)
class RevenueObservedSum(_RedactedValue):
    """Observed synthetic values only; a missing confirmed value is never zero."""

    event_type: RevenueEventType
    row_count: int
    generated_commission_jpy: int
    confirmed_commission_jpy: int | None
    confirmed_missing_count: int

    def __post_init__(self) -> None:
        if type(self.event_type) is not RevenueEventType:
            fail_revenue_import()
        _nonnegative_exact_int(self.row_count)
        _nonnegative_exact_int(self.generated_commission_jpy)
        _nonnegative_exact_int(self.confirmed_missing_count)
        if self.confirmed_missing_count > self.row_count:
            fail_revenue_import()
        known_count = self.row_count - self.confirmed_missing_count
        if known_count == 0:
            if self.confirmed_commission_jpy is not None:
                fail_revenue_import()
        elif self.confirmed_commission_jpy is None:
            fail_revenue_import()
        else:
            _nonnegative_exact_int(self.confirmed_commission_jpy)


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRevenuePeriod(_RedactedValue):
    label: SyntheticPeriodLabel
    period_from: date | None
    period_to: date | None

    def __post_init__(self) -> None:
        if type(self.label) is not SyntheticPeriodLabel:
            fail_revenue_import()
        if (self.period_from is None) != (self.period_to is None):
            fail_revenue_import()
        if self.period_from is not None:
            if (
                type(self.period_from) is not date
                or type(self.period_to) is not date
                or self.period_from > self.period_to
            ):
                fail_revenue_import()


@dataclass(frozen=True, slots=True, repr=False)
class SyntheticRevenueDryRun(_RedactedValue):
    """A non-persistent preview; READY here never means import approval."""

    source: SyntheticRevenueSourceReference
    state: RevenueDryRunState
    previews: tuple[RevenueRowPreview, ...]
    row_count: int
    accepted_count: int
    rejected_count: int
    duplicate_count: int
    ignored_count: int
    observed_sums: tuple[RevenueObservedSum, ...]
    period: SyntheticRevenuePeriod
    formula_detection: FormulaDetectionStatus
    source_status: RevenueSourceStatus
    execution: RevenueExecutionStatus
    mapping: RevenueMappingStatus
    reconciliation: RevenueExecutionStatus
    persistence: RevenueExecutionStatus
    audit: RevenueExecutionStatus
    outbox: RevenueExecutionStatus
    events: RevenueExecutionStatus
    facts: RevenueFactStatus
    tst026: RevenueExecutionStatus
    tst030: RevenueExecutionStatus
    decision: RevenueDecision
    provider_total_jpy: int | None
    revenue_import_id: UUID | None
    source_artifact_id: UUID | None
    approval_id: UUID | None

    def __post_init__(self) -> None:
        if (
            type(self.source) is not SyntheticRevenueSourceReference
            or self.state is not RevenueDryRunState.SYNTHETIC_DRY_RUN_READY
            or type(self.previews) is not tuple
            or any(type(value) is not RevenueRowPreview for value in self.previews)
            or len({value.row_no for value in self.previews}) != len(self.previews)
            or tuple(value.row_no for value in self.previews)
            != tuple(sorted(value.row_no for value in self.previews))
            or type(self.observed_sums) is not tuple
            or any(
                type(value) is not RevenueObservedSum for value in self.observed_sums
            )
            or tuple(value.event_type for value in self.observed_sums)
            != tuple(RevenueEventType)
            or type(self.period) is not SyntheticRevenuePeriod
            or self.formula_detection is not FormulaDetectionStatus.NOT_DETECTED
            or self.source_status is not RevenueSourceStatus.NEW
            or self.execution is not RevenueExecutionStatus.SYNTHETIC_FIXTURE_ONLY
            or self.mapping is not RevenueMappingStatus.UNVERIFIED
            or self.reconciliation is not RevenueExecutionStatus.NOT_EXECUTED
            or self.persistence is not RevenueExecutionStatus.NOT_EXECUTED
            or self.audit is not RevenueExecutionStatus.NOT_EXECUTED
            or self.outbox is not RevenueExecutionStatus.NOT_EXECUTED
            or self.events is not RevenueExecutionStatus.NOT_EXECUTED
            or self.facts is not RevenueFactStatus.NOT_CREATED
            or self.tst026 is not RevenueExecutionStatus.NOT_EXECUTED
            or self.tst030 is not RevenueExecutionStatus.NOT_EXECUTED
            or self.decision is not RevenueDecision.NOT_READY
            or self.provider_total_jpy is not None
            or self.revenue_import_id is not None
            or self.source_artifact_id is not None
            or self.approval_id is not None
        ):
            fail_revenue_import()
        for value in (
            self.row_count,
            self.accepted_count,
            self.rejected_count,
            self.duplicate_count,
            self.ignored_count,
        ):
            _nonnegative_exact_int(value)
        if (
            self.row_count != len(self.previews)
            or self.source.csv_row_count != self.row_count + 1
            or self.row_count
            != self.accepted_count
            + self.rejected_count
            + self.duplicate_count
            + self.ignored_count
            or self.accepted_count
            != sum(
                value.status is RevenueRowParseStatus.ACCEPTED
                for value in self.previews
            )
            or self.rejected_count
            != sum(
                value.status is RevenueRowParseStatus.REJECTED
                for value in self.previews
            )
            or self.duplicate_count
            != sum(
                value.status is RevenueRowParseStatus.DUPLICATE
                for value in self.previews
            )
            or self.ignored_count
            != sum(
                value.status is RevenueRowParseStatus.IGNORED for value in self.previews
            )
            or sum(value.row_count for value in self.observed_sums)
            != self.accepted_count
        ):
            fail_revenue_import()
        accepted = tuple(
            value
            for value in self.previews
            if value.status is RevenueRowParseStatus.ACCEPTED
        )
        for summary in self.observed_sums:
            matching = tuple(
                value for value in accepted if value.event_type is summary.event_type
            )
            confirmed_values = tuple(
                value.confirmed_commission_jpy
                for value in matching
                if value.confirmed_commission_jpy is not None
            )
            expected_confirmed = sum(confirmed_values) if confirmed_values else None
            if (
                summary.row_count != len(matching)
                or summary.generated_commission_jpy
                != sum(value.generated_commission_jpy or 0 for value in matching)
                or summary.confirmed_commission_jpy != expected_confirmed
                or summary.confirmed_missing_count
                != sum(value.confirmed_commission_jpy is None for value in matching)
            ):
                fail_revenue_import()
        accepted_dates = tuple(
            value.event_at.date()
            for value in accepted
            if type(value.event_at) is datetime
        )
        expected_period = (
            (min(accepted_dates), max(accepted_dates))
            if accepted_dates
            else (None, None)
        )
        if (self.period.period_from, self.period.period_to) != expected_period:
            fail_revenue_import()


__all__ = [
    "FormulaDetectionStatus",
    "MAX_SYNTHETIC_CELL_BYTES",
    "MAX_SYNTHETIC_CSV_ROWS",
    "MAX_SYNTHETIC_SOURCE_BYTES",
    "RevenueDecision",
    "RevenueDryRunState",
    "RevenueEventType",
    "RevenueExecutionStatus",
    "RevenueFactStatus",
    "RevenueImportFailure",
    "RevenueImportFailureCode",
    "RevenueMappingStatus",
    "RevenueObservedSum",
    "RevenueProviderCode",
    "RevenueRowCode",
    "RevenueRowParseStatus",
    "RevenueRowPreview",
    "RevenueSourceStatus",
    "SyntheticPeriodLabel",
    "SyntheticRevenueDryRun",
    "SyntheticRevenueParseCommand",
    "SyntheticRevenuePeriod",
    "SyntheticRevenueProfile",
    "SyntheticRevenueSourceReference",
    "SYNTHETIC_CSV_COLUMNS",
    "fail_revenue_import",
]
