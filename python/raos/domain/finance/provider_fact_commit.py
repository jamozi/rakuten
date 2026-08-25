"""Deterministic recorded/synthetic provider-fact commit boundary for ST-1302.

This module deliberately does not model a real Rakuten report.  It consumes the
exact, redacted ST-1301 dry-run value plus a separately recorded synthetic row
identity fixture.  The local preview binding is an additive reversible contract;
it is not asserted to be the unresolved canonical ``preview_hash``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex
from uuid import RFC_4122, UUID

from raos.domain.finance.revenue_import import (
    RevenueEventType,
    RevenueExecutionStatus,
    RevenueMappingStatus,
    RevenueRowParseStatus,
    RevenueRowPreview,
    SyntheticRevenueDryRun,
    SyntheticRevenueProfile,
)
from raos.domain.ops.object_intake import Sha256Digest


PROFILE: Final = "RAOS_ST1302_RECORDED_SYNTHETIC_V1"
LOCAL_PREVIEW_BINDING_ALGORITHM: Final = "RAOS_ST1302_LOCAL_PREVIEW_BINDING_SHA256_V1"
PROVIDER_CODE: Final = "RAKUTEN_AFFILIATE"
AUDIT_ACTION: Final = "revenue_import_confirm"
LOCAL_COMMITTED_EVENT: Final = (
    "jp.raos.local.recorded.finance.provider_facts_committed.v1"
)
LOCAL_FACT_EVENT: Final = "jp.raos.local.recorded.finance.provider_event_captured.v1"
MAX_STEP_UP_AGE_SECONDS: Final = 300
_MAX_AMOUNT: Final = (1 << 63) - 1
_MAX_ROWS: Final = 10_000
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024
_EVENT_KEY = re.compile(r"synthetic-event-[0-9]{4}\Z", re.ASCII)
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{15,127}\Z", re.ASCII)
_SAFE_REASON = re.compile(r"[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+\Z")


class ProviderFactCommitFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DRY_RUN_INVALID = "DRY_RUN_INVALID"
    ACCEPTED_ROW_BINDING_INVALID = "ACCEPTED_ROW_BINDING_INVALID"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    PREVIEW_BINDING_MISMATCH = "PREVIEW_BINDING_MISMATCH"
    COUNT_MISMATCH = "COUNT_MISMATCH"
    AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
    CURRENCY_MISMATCH = "CURRENCY_MISMATCH"
    PERIOD_MISMATCH = "PERIOD_MISMATCH"
    STATUS_SUMMARY_MISMATCH = "STATUS_SUMMARY_MISMATCH"
    AUTHORIZATION_INVALID = "AUTHORIZATION_INVALID"
    ACTIVE_HUMAN_REQUIRED = "ACTIVE_HUMAN_REQUIRED"
    ROLE_REQUIRED = "ROLE_REQUIRED"
    MFA_REQUIRED = "MFA_REQUIRED"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STEP_UP_STALE = "STEP_UP_STALE"
    SITE_SCOPE_MISMATCH = "SITE_SCOPE_MISMATCH"
    ROLE_SEPARATION_REQUIRED = "ROLE_SEPARATION_REQUIRED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    SOURCE_ALREADY_COMMITTED = "SOURCE_ALREADY_COMMITTED"
    RECORDED_EXCHANGE_UNAVAILABLE = "RECORDED_EXCHANGE_UNAVAILABLE"
    ATOMIC_COMMIT_UNAVAILABLE = "ATOMIC_COMMIT_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class ProviderFactCommitFailure(RuntimeError):
    """Sanitized failure retaining only one closed classification."""

    __slots__ = ("_code",)

    def __init__(self, code: ProviderFactCommitFailureCode) -> None:
        if type(code) is not ProviderFactCommitFailureCode:
            raise TypeError("invalid provider-fact commit failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> ProviderFactCommitFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"ProviderFactCommitFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("provider-fact commit failure serialization is forbidden")


def fail_provider_fact_commit(
    code: ProviderFactCommitFailureCode = ProviderFactCommitFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise ProviderFactCommitFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1302>)"

    def __str__(self) -> str:
        return "<redacted-st1302>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("provider-fact commit serialization is forbidden")


class Currency(str, Enum):
    JPY = "JPY"


class ProviderFactCommitRole(str, Enum):
    PRODUCT_OWNER = "PRODUCT_OWNER"
    ANALYST = "ANALYST"


class RecordedSubjectState(str, Enum):
    ACTIVE_HUMAN_RECORDED_SYNTHETIC = "ACTIVE_HUMAN_RECORDED_SYNTHETIC"


class RecordedMfaState(str, Enum):
    SATISFIED_RECORDED_SYNTHETIC = "SATISFIED_RECORDED_SYNTHETIC"


class RecordedStepUpState(str, Enum):
    SATISFIED_RECORDED_SYNTHETIC = "SATISFIED_RECORDED_SYNTHETIC"


class ProviderFactCommitExecution(str, Enum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


class RecordedCommitState(str, Enum):
    PROCESS_LOCAL_ATOMIC_COMMITTED = "PROCESS_LOCAL_ATOMIC_COMMITTED"


class LocalMappingState(str, Enum):
    UNVERIFIED_PRESERVED_UNMAPPED = "UNVERIFIED_PRESERVED_UNMAPPED"


class ExternalExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class CanonicalCommissionEventType(str, Enum):
    GENERATED = "GENERATED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    AMOUNT_CHANGED = "AMOUNT_CHANGED"
    CORRECTED = "CORRECTED"


def _canonical_bytes(payload: object) -> bytes:
    try:
        value = json.dumps(
            payload,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except Exception:
        fail_provider_fact_commit()
    if not value or len(value) > _MAX_CANONICAL_BYTES:
        fail_provider_fact_commit()
    return value


def _digest(payload: object) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(_canonical_bytes(payload)).hexdigest())


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_provider_fact_commit()
    try:
        return Sha256Digest(value.value)
    except Exception:
        fail_provider_fact_commit()


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_provider_fact_commit()
    return value


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_provider_fact_commit()
    return value.replace(tzinfo=timezone.utc)


def _instant_text(value: datetime) -> str:
    return _utc_second(value).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True, repr=False)
class JpyAmount(_Redacted):
    """Exact integral Decimal JPY; floats and implicit coercion are forbidden."""

    value: Decimal

    def __post_init__(self) -> None:
        if type(self.value) is not Decimal or not self.value.is_finite():
            fail_provider_fact_commit()
        integral = self.value.to_integral_value()
        if self.value != integral or not Decimal(0) <= integral <= Decimal(_MAX_AMOUNT):
            fail_provider_fact_commit()
        object.__setattr__(self, "value", integral.quantize(Decimal(1)))

    @property
    def canonical_text(self) -> str:
        return format(self.value, "f")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderEventKey(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _EVENT_KEY.fullmatch(self.value) is None:
            fail_provider_fact_commit()

    @property
    def sha256(self) -> Sha256Digest:
        return Sha256Digest(hashlib.sha256(self.value.encode("ascii")).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class LocalIdempotencyKey(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or _IDEMPOTENCY_KEY.fullmatch(self.value) is None
        ):
            fail_provider_fact_commit()

    @property
    def sha256(self) -> Sha256Digest:
        return Sha256Digest(hashlib.sha256(self.value.encode("ascii")).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFactCommitReason(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or not 10 <= len(self.value) <= 1000
            or self.value != self.value.strip()
            or _SAFE_REASON.fullmatch(self.value) is None
        ):
            fail_provider_fact_commit()

    @property
    def sha256(self) -> Sha256Digest:
        return Sha256Digest(hashlib.sha256(self.value.encode("utf-8")).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAcceptedRevenueRow(_Redacted):
    row_no: int
    row_sha256: Sha256Digest
    provider_event_key: ProviderEventKey
    event_type: RevenueEventType
    event_at: datetime
    generated_commission_jpy: JpyAmount
    confirmed_commission_jpy: JpyAmount | None

    def __post_init__(self) -> None:
        if (
            type(self.row_no) is not int
            or not 2 <= self.row_no <= _MAX_ROWS + 1
            or type(self.provider_event_key) is not ProviderEventKey
            or type(self.event_type) is not RevenueEventType
            or type(self.generated_commission_jpy) is not JpyAmount
            or (
                self.confirmed_commission_jpy is not None
                and type(self.confirmed_commission_jpy) is not JpyAmount
            )
        ):
            fail_provider_fact_commit()
        object.__setattr__(self, "row_sha256", _sha(self.row_sha256))
        object.__setattr__(self, "event_at", _utc_second(self.event_at))

    def binding_payload(self) -> dict[str, object]:
        return {
            "confirmed_commission_jpy": (
                None
                if self.confirmed_commission_jpy is None
                else self.confirmed_commission_jpy.canonical_text
            ),
            "event_at": _instant_text(self.event_at),
            "event_type": self.event_type.value,
            "generated_commission_jpy": self.generated_commission_jpy.canonical_text,
            "provider_event_key_sha256": self.provider_event_key.sha256.value,
            "row_no": self.row_no,
            "row_sha256": self.row_sha256.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFactStatusSummary(_Redacted):
    event_type: RevenueEventType
    row_count: int
    generated_commission_jpy: JpyAmount
    confirmed_commission_jpy: JpyAmount | None
    confirmed_missing_count: int

    def __post_init__(self) -> None:
        if (
            type(self.event_type) is not RevenueEventType
            or type(self.row_count) is not int
            or not 0 <= self.row_count <= _MAX_ROWS
            or type(self.generated_commission_jpy) is not JpyAmount
            or (
                self.confirmed_commission_jpy is not None
                and type(self.confirmed_commission_jpy) is not JpyAmount
            )
            or type(self.confirmed_missing_count) is not int
            or not 0 <= self.confirmed_missing_count <= self.row_count
        ):
            fail_provider_fact_commit()
        known = self.row_count - self.confirmed_missing_count
        if (known == 0) != (self.confirmed_commission_jpy is None):
            fail_provider_fact_commit()

    def binding_payload(self) -> dict[str, object]:
        return {
            "confirmed_commission_jpy": (
                None
                if self.confirmed_commission_jpy is None
                else self.confirmed_commission_jpy.canonical_text
            ),
            "confirmed_missing_count": self.confirmed_missing_count,
            "event_type": self.event_type.value,
            "generated_commission_jpy": self.generated_commission_jpy.canonical_text,
            "row_count": self.row_count,
        }


def _status_summaries(
    rows: tuple[RecordedAcceptedRevenueRow, ...],
) -> tuple[ProviderFactStatusSummary, ...]:
    result: list[ProviderFactStatusSummary] = []
    for event_type in RevenueEventType:
        selected = tuple(row for row in rows if row.event_type is event_type)
        known_confirmed = tuple(
            row.confirmed_commission_jpy
            for row in selected
            if row.confirmed_commission_jpy is not None
        )
        result.append(
            ProviderFactStatusSummary(
                event_type=event_type,
                row_count=len(selected),
                generated_commission_jpy=JpyAmount(
                    sum(
                        (row.generated_commission_jpy.value for row in selected),
                        Decimal(0),
                    )
                ),
                confirmed_commission_jpy=(
                    JpyAmount(
                        sum((value.value for value in known_confirmed), Decimal(0))
                    )
                    if known_confirmed
                    else None
                ),
                confirmed_missing_count=sum(
                    row.confirmed_commission_jpy is None for row in selected
                ),
            )
        )
    return tuple(result)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedRevenueDryRunBundle(_Redacted):
    dry_run: SyntheticRevenueDryRun
    accepted_rows: tuple[RecordedAcceptedRevenueRow, ...]
    prepared_by_principal_id: UUID
    local_preview_binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.dry_run) is not SyntheticRevenueDryRun
            or type(self.accepted_rows) is not tuple
            or any(
                type(row) is not RecordedAcceptedRevenueRow
                for row in self.accepted_rows
            )
            or not 1 <= len(self.accepted_rows) <= _MAX_ROWS
        ):
            fail_provider_fact_commit(ProviderFactCommitFailureCode.DRY_RUN_INVALID)
        preparer = _uuid7(self.prepared_by_principal_id)
        try:
            # Re-running the frozen constructor catches bypassed/tampered predecessor state.
            SyntheticRevenueDryRun(
                source=self.dry_run.source,
                state=self.dry_run.state,
                previews=self.dry_run.previews,
                row_count=self.dry_run.row_count,
                accepted_count=self.dry_run.accepted_count,
                rejected_count=self.dry_run.rejected_count,
                duplicate_count=self.dry_run.duplicate_count,
                ignored_count=self.dry_run.ignored_count,
                observed_sums=self.dry_run.observed_sums,
                period=self.dry_run.period,
                formula_detection=self.dry_run.formula_detection,
                source_status=self.dry_run.source_status,
                execution=self.dry_run.execution,
                mapping=self.dry_run.mapping,
                reconciliation=self.dry_run.reconciliation,
                persistence=self.dry_run.persistence,
                audit=self.dry_run.audit,
                outbox=self.dry_run.outbox,
                events=self.dry_run.events,
                facts=self.dry_run.facts,
                tst026=self.dry_run.tst026,
                tst030=self.dry_run.tst030,
                decision=self.dry_run.decision,
                provider_total_jpy=self.dry_run.provider_total_jpy,
                revenue_import_id=self.dry_run.revenue_import_id,
                source_artifact_id=self.dry_run.source_artifact_id,
                approval_id=self.dry_run.approval_id,
            )
        except Exception:
            fail_provider_fact_commit(ProviderFactCommitFailureCode.DRY_RUN_INVALID)
        if (
            self.dry_run.source.profile
            is not SyntheticRevenueProfile.RAOS_ST1301_SYNTHETIC_V1
            or self.dry_run.mapping is not RevenueMappingStatus.UNVERIFIED
            or self.dry_run.execution
            is not RevenueExecutionStatus.SYNTHETIC_FIXTURE_ONLY
            or self.dry_run.accepted_count != len(self.accepted_rows)
        ):
            fail_provider_fact_commit(ProviderFactCommitFailureCode.DRY_RUN_INVALID)
        accepted_previews = tuple(
            preview
            for preview in self.dry_run.previews
            if preview.status is RevenueRowParseStatus.ACCEPTED
        )
        if tuple(row.row_no for row in self.accepted_rows) != tuple(
            sorted(row.row_no for row in self.accepted_rows)
        ) or len({row.row_no for row in self.accepted_rows}) != len(self.accepted_rows):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.ACCEPTED_ROW_BINDING_INVALID
            )
        if len({row.provider_event_key.value for row in self.accepted_rows}) != len(
            self.accepted_rows
        ):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.ACCEPTED_ROW_BINDING_INVALID
            )
        for preview, row in zip(accepted_previews, self.accepted_rows, strict=True):
            if not _row_matches_preview(row, preview):
                fail_provider_fact_commit(
                    ProviderFactCommitFailureCode.ACCEPTED_ROW_BINDING_INVALID
                )
        object.__setattr__(self, "prepared_by_principal_id", preparer)
        object.__setattr__(
            self,
            "local_preview_binding_sha256",
            _digest(self._binding_payload()),
        )

    @property
    def status_summaries(self) -> tuple[ProviderFactStatusSummary, ...]:
        return _status_summaries(self.accepted_rows)

    @property
    def generated_commission_jpy(self) -> JpyAmount:
        return JpyAmount(
            sum(
                (row.generated_commission_jpy.value for row in self.accepted_rows),
                Decimal(0),
            )
        )

    @property
    def confirmed_commission_jpy(self) -> JpyAmount | None:
        values = tuple(
            row.confirmed_commission_jpy
            for row in self.accepted_rows
            if row.confirmed_commission_jpy is not None
        )
        if not values:
            return None
        return JpyAmount(sum((value.value for value in values), Decimal(0)))

    @property
    def confirmed_missing_count(self) -> int:
        return sum(row.confirmed_commission_jpy is None for row in self.accepted_rows)

    def _binding_payload(self) -> dict[str, object]:
        return {
            "accepted_rows": [row.binding_payload() for row in self.accepted_rows],
            "algorithm": LOCAL_PREVIEW_BINDING_ALGORITHM,
            "command_fingerprint": self.dry_run.source.command_fingerprint.value,
            "currency": Currency.JPY.value,
            "period_from": (
                None
                if self.dry_run.period.period_from is None
                else self.dry_run.period.period_from.isoformat()
            ),
            "period_to": (
                None
                if self.dry_run.period.period_to is None
                else self.dry_run.period.period_to.isoformat()
            ),
            "profile": PROFILE,
            "source_sha256": self.dry_run.source.source_sha256.value,
            "status_summaries": [
                summary.binding_payload() for summary in self.status_summaries
            ],
        }


def _row_matches_preview(
    row: RecordedAcceptedRevenueRow,
    preview: RevenueRowPreview,
) -> bool:
    return (
        type(preview) is RevenueRowPreview
        and preview.row_no == row.row_no
        and preview.row_sha256 == row.row_sha256
        and preview.event_type is row.event_type
        and preview.event_at == row.event_at
        and preview.generated_commission_jpy == int(row.generated_commission_jpy.value)
        and (
            preview.confirmed_commission_jpy
            == (
                None
                if row.confirmed_commission_jpy is None
                else int(row.confirmed_commission_jpy.value)
            )
        )
    )


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFactCommitRequest(_Redacted):
    revenue_import_id: UUID
    expected_site_id: UUID
    expected_source_sha256: Sha256Digest
    expected_local_preview_binding_sha256: Sha256Digest
    expected_accepted_count: int
    expected_generated_commission_jpy: JpyAmount
    expected_confirmed_commission_jpy: JpyAmount | None
    expected_confirmed_missing_count: int
    expected_currency: Currency
    expected_period_from: date
    expected_period_to: date
    expected_status_summaries: tuple[ProviderFactStatusSummary, ...]
    idempotency_key: LocalIdempotencyKey
    reason: ProviderFactCommitReason
    requested_at: datetime
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        revenue_import_id = _uuid7(self.revenue_import_id)
        site_id = _uuid7(self.expected_site_id)
        if (
            type(self.expected_accepted_count) is not int
            or not 1 <= self.expected_accepted_count <= _MAX_ROWS
            or type(self.expected_generated_commission_jpy) is not JpyAmount
            or (
                self.expected_confirmed_commission_jpy is not None
                and type(self.expected_confirmed_commission_jpy) is not JpyAmount
            )
            or type(self.expected_confirmed_missing_count) is not int
            or not 0
            <= self.expected_confirmed_missing_count
            <= self.expected_accepted_count
            or type(self.expected_currency) is not Currency
            or self.expected_currency is not Currency.JPY
            or type(self.expected_period_from) is not date
            or type(self.expected_period_to) is not date
            or self.expected_period_from > self.expected_period_to
            or type(self.expected_status_summaries) is not tuple
            or any(
                type(item) is not ProviderFactStatusSummary
                for item in self.expected_status_summaries
            )
            or tuple(item.event_type for item in self.expected_status_summaries)
            != tuple(RevenueEventType)
            or type(self.idempotency_key) is not LocalIdempotencyKey
            or type(self.reason) is not ProviderFactCommitReason
        ):
            fail_provider_fact_commit()
        if (
            self.expected_accepted_count - self.expected_confirmed_missing_count == 0
        ) != (self.expected_confirmed_commission_jpy is None):
            fail_provider_fact_commit()
        object.__setattr__(self, "revenue_import_id", revenue_import_id)
        object.__setattr__(self, "expected_site_id", site_id)
        object.__setattr__(
            self, "expected_source_sha256", _sha(self.expected_source_sha256)
        )
        object.__setattr__(
            self,
            "expected_local_preview_binding_sha256",
            _sha(self.expected_local_preview_binding_sha256),
        )
        object.__setattr__(self, "requested_at", _utc_second(self.requested_at))
        object.__setattr__(self, "request_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "expected_accepted_count": self.expected_accepted_count,
            "expected_confirmed_commission_jpy": (
                None
                if self.expected_confirmed_commission_jpy is None
                else self.expected_confirmed_commission_jpy.canonical_text
            ),
            "expected_confirmed_missing_count": self.expected_confirmed_missing_count,
            "expected_currency": self.expected_currency.value,
            "expected_generated_commission_jpy": (
                self.expected_generated_commission_jpy.canonical_text
            ),
            "expected_local_preview_binding_sha256": (
                self.expected_local_preview_binding_sha256.value
            ),
            "expected_period_from": self.expected_period_from.isoformat(),
            "expected_period_to": self.expected_period_to.isoformat(),
            "expected_site_id": str(self.expected_site_id),
            "expected_source_sha256": self.expected_source_sha256.value,
            "expected_status_summaries": [
                item.binding_payload() for item in self.expected_status_summaries
            ],
            "idempotency_key_sha256": self.idempotency_key.sha256.value,
            "profile": PROFILE,
            "reason_sha256": self.reason.sha256.value,
            "requested_at": _instant_text(self.requested_at),
            "revenue_import_id": str(self.revenue_import_id),
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["request_sha256"] = self.request_sha256.value
        return _canonical_bytes(payload)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedProviderFactCommitAuthorization(_Redacted):
    request_sha256: Sha256Digest
    principal_id: UUID
    site_id: UUID
    role: ProviderFactCommitRole
    subject_state: RecordedSubjectState
    mfa_state: RecordedMfaState
    step_up_state: RecordedStepUpState
    step_up_authenticated_at: datetime
    authorized_at: datetime
    prepared_by_principal_id: UUID
    authorization_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.role) is not ProviderFactCommitRole
            or type(self.subject_state) is not RecordedSubjectState
            or type(self.mfa_state) is not RecordedMfaState
            or type(self.step_up_state) is not RecordedStepUpState
        ):
            fail_provider_fact_commit(
                ProviderFactCommitFailureCode.AUTHORIZATION_INVALID
            )
        object.__setattr__(self, "request_sha256", _sha(self.request_sha256))
        object.__setattr__(self, "principal_id", _uuid7(self.principal_id))
        object.__setattr__(self, "site_id", _uuid7(self.site_id))
        object.__setattr__(
            self, "prepared_by_principal_id", _uuid7(self.prepared_by_principal_id)
        )
        object.__setattr__(
            self, "step_up_authenticated_at", _utc_second(self.step_up_authenticated_at)
        )
        object.__setattr__(self, "authorized_at", _utc_second(self.authorized_at))
        object.__setattr__(self, "authorization_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "authorized_at": _instant_text(self.authorized_at),
            "mfa_state": self.mfa_state.value,
            "prepared_by_principal_id": str(self.prepared_by_principal_id),
            "principal_id": str(self.principal_id),
            "request_sha256": self.request_sha256.value,
            "role": self.role.value,
            "site_id": str(self.site_id),
            "step_up_authenticated_at": _instant_text(self.step_up_authenticated_at),
            "step_up_state": self.step_up_state.value,
            "subject_state": self.subject_state.value,
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["authorization_sha256"] = self.authorization_sha256.value
        return _canonical_bytes(payload)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedProviderFact(_Redacted):
    fact_sha256: Sha256Digest
    revenue_import_id: UUID
    site_id: UUID
    provider_code: str
    provider_event_key: ProviderEventKey
    source_row_no: int
    source_row_sha256: Sha256Digest
    status: RevenueEventType
    occurred_at: datetime
    generated_commission_jpy: JpyAmount
    confirmed_commission_jpy: JpyAmount | None
    currency: Currency
    source_sha256: Sha256Digest
    local_preview_binding_sha256: Sha256Digest
    mapping: LocalMappingState

    def __post_init__(self) -> None:
        if (
            type(self.provider_code) is not str
            or self.provider_code != PROVIDER_CODE
            or type(self.provider_event_key) is not ProviderEventKey
            or type(self.source_row_no) is not int
            or not 2 <= self.source_row_no <= _MAX_ROWS + 1
            or type(self.status) is not RevenueEventType
            or type(self.generated_commission_jpy) is not JpyAmount
            or (
                self.confirmed_commission_jpy is not None
                and type(self.confirmed_commission_jpy) is not JpyAmount
            )
            or type(self.currency) is not Currency
            or self.currency is not Currency.JPY
            or self.mapping is not LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED
        ):
            fail_provider_fact_commit()
        object.__setattr__(self, "fact_sha256", _sha(self.fact_sha256))
        object.__setattr__(self, "revenue_import_id", _uuid7(self.revenue_import_id))
        object.__setattr__(self, "site_id", _uuid7(self.site_id))
        object.__setattr__(self, "source_row_sha256", _sha(self.source_row_sha256))
        object.__setattr__(self, "occurred_at", _utc_second(self.occurred_at))
        object.__setattr__(self, "source_sha256", _sha(self.source_sha256))
        object.__setattr__(
            self,
            "local_preview_binding_sha256",
            _sha(self.local_preview_binding_sha256),
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedCommissionEvent(_Redacted):
    event_sha256: Sha256Digest
    fact_sha256: Sha256Digest
    source_event_type: RevenueEventType
    canonical_event_type: CanonicalCommissionEventType | None
    mapping: LocalMappingState
    provider_occurred_at: datetime
    generated_commission_jpy: JpyAmount
    confirmed_commission_jpy: JpyAmount | None

    def __post_init__(self) -> None:
        if (
            type(self.source_event_type) is not RevenueEventType
            or self.canonical_event_type is not None
            or self.mapping is not LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED
            or type(self.generated_commission_jpy) is not JpyAmount
            or (
                self.confirmed_commission_jpy is not None
                and type(self.confirmed_commission_jpy) is not JpyAmount
            )
        ):
            fail_provider_fact_commit()
        object.__setattr__(self, "event_sha256", _sha(self.event_sha256))
        object.__setattr__(self, "fact_sha256", _sha(self.fact_sha256))
        object.__setattr__(
            self, "provider_occurred_at", _utc_second(self.provider_occurred_at)
        )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAuditRecord(_Redacted):
    audit_sha256: Sha256Digest
    action: str
    principal_id: UUID
    site_id: UUID
    request_sha256: Sha256Digest
    authorization_sha256: Sha256Digest
    result_sha256: Sha256Digest
    reason_sha256: Sha256Digest
    recorded_at: datetime

    def __post_init__(self) -> None:
        if type(self.action) is not str or self.action != AUDIT_ACTION:
            fail_provider_fact_commit()
        for name in (
            "audit_sha256",
            "request_sha256",
            "authorization_sha256",
            "result_sha256",
            "reason_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        object.__setattr__(self, "principal_id", _uuid7(self.principal_id))
        object.__setattr__(self, "site_id", _uuid7(self.site_id))
        object.__setattr__(self, "recorded_at", _utc_second(self.recorded_at))


@dataclass(frozen=True, slots=True, repr=False)
class RecordedOutboxRecord(_Redacted):
    outbox_sha256: Sha256Digest
    event_type: str
    aggregate_sha256: Sha256Digest
    payload_sha256: Sha256Digest
    recorded_at: datetime

    def __post_init__(self) -> None:
        if type(self.event_type) is not str or self.event_type not in {
            LOCAL_COMMITTED_EVENT,
            LOCAL_FACT_EVENT,
        }:
            fail_provider_fact_commit()
        object.__setattr__(self, "outbox_sha256", _sha(self.outbox_sha256))
        object.__setattr__(self, "aggregate_sha256", _sha(self.aggregate_sha256))
        object.__setattr__(self, "payload_sha256", _sha(self.payload_sha256))
        object.__setattr__(self, "recorded_at", _utc_second(self.recorded_at))


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFactCommitAuthority(_Redacted):
    database_write_authorized: bool = False
    provider_call_authorized: bool = False
    network_authorized: bool = False
    publication_authorized: bool = False
    live_authorized: bool = False
    staging_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    database: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    provider: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    network: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    publication: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    live: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    staging: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    release: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED
    production: ExternalExecutionStatus = ExternalExecutionStatus.NOT_EXECUTED

    def __post_init__(self) -> None:
        for name in (
            "database_write_authorized",
            "provider_call_authorized",
            "network_authorized",
            "publication_authorized",
            "live_authorized",
            "staging_authorized",
            "release_authorized",
            "production_authorized",
        ):
            if getattr(self, name) is not False:
                fail_provider_fact_commit()
        for name in (
            "database",
            "provider",
            "network",
            "publication",
            "live",
            "staging",
            "release",
            "production",
        ):
            if getattr(self, name) is not ExternalExecutionStatus.NOT_EXECUTED:
                fail_provider_fact_commit()


@dataclass(frozen=True, slots=True, repr=False)
class ProviderFactCommitResult(_Redacted):
    result_sha256: Sha256Digest
    request_sha256: Sha256Digest
    local_preview_binding_sha256: Sha256Digest
    execution: ProviderFactCommitExecution
    commit_state: RecordedCommitState
    facts: tuple[RecordedProviderFact, ...]
    commission_events: tuple[RecordedCommissionEvent, ...]
    status_summaries: tuple[ProviderFactStatusSummary, ...]
    audit: RecordedAuditRecord
    outbox: tuple[RecordedOutboxRecord, ...]
    authority: ProviderFactCommitAuthority
    mapping: LocalMappingState

    def __post_init__(self) -> None:
        if (
            self.execution is not ProviderFactCommitExecution.RECORDED_SYNTHETIC_ONLY
            or self.commit_state
            is not RecordedCommitState.PROCESS_LOCAL_ATOMIC_COMMITTED
            or type(self.facts) is not tuple
            or not self.facts
            or any(type(item) is not RecordedProviderFact for item in self.facts)
            or type(self.commission_events) is not tuple
            or len(self.commission_events) != len(self.facts)
            or any(
                type(item) is not RecordedCommissionEvent
                for item in self.commission_events
            )
            or type(self.status_summaries) is not tuple
            or any(
                type(item) is not ProviderFactStatusSummary
                for item in self.status_summaries
            )
            or tuple(item.event_type for item in self.status_summaries)
            != tuple(RevenueEventType)
            or type(self.audit) is not RecordedAuditRecord
            or type(self.outbox) is not tuple
            or len(self.outbox) != len(self.facts) + 1
            or any(type(item) is not RecordedOutboxRecord for item in self.outbox)
            or type(self.authority) is not ProviderFactCommitAuthority
            or self.mapping is not LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED
        ):
            fail_provider_fact_commit()
        object.__setattr__(self, "result_sha256", _sha(self.result_sha256))
        object.__setattr__(self, "request_sha256", _sha(self.request_sha256))
        object.__setattr__(
            self,
            "local_preview_binding_sha256",
            _sha(self.local_preview_binding_sha256),
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(_result_payload(self, include_audit=True))


def _require_request_matches_bundle(
    request: ProviderFactCommitRequest,
    bundle: RecordedRevenueDryRunBundle,
) -> None:
    if request.expected_source_sha256 != bundle.dry_run.source.source_sha256:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.SOURCE_HASH_MISMATCH)
    if (
        request.expected_local_preview_binding_sha256
        != bundle.local_preview_binding_sha256
    ):
        fail_provider_fact_commit(
            ProviderFactCommitFailureCode.PREVIEW_BINDING_MISMATCH
        )
    if request.expected_site_id != bundle.dry_run.source.site_id:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.SITE_SCOPE_MISMATCH)
    if request.expected_accepted_count != len(bundle.accepted_rows):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.COUNT_MISMATCH)
    if (
        request.expected_generated_commission_jpy != bundle.generated_commission_jpy
        or request.expected_confirmed_commission_jpy != bundle.confirmed_commission_jpy
        or request.expected_confirmed_missing_count != bundle.confirmed_missing_count
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.AMOUNT_MISMATCH)
    if request.expected_currency is not Currency.JPY:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.CURRENCY_MISMATCH)
    if (
        request.expected_period_from != bundle.dry_run.period.period_from
        or request.expected_period_to != bundle.dry_run.period.period_to
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.PERIOD_MISMATCH)
    if request.expected_status_summaries != bundle.status_summaries:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.STATUS_SUMMARY_MISMATCH)


def _require_authorization(
    request: ProviderFactCommitRequest,
    bundle: RecordedRevenueDryRunBundle,
    authorization: RecordedProviderFactCommitAuthorization,
) -> None:
    if authorization.request_sha256 != request.request_sha256:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.AUTHORIZATION_INVALID)
    if (
        authorization.subject_state
        is not RecordedSubjectState.ACTIVE_HUMAN_RECORDED_SYNTHETIC
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.ACTIVE_HUMAN_REQUIRED)
    if authorization.role not in {
        ProviderFactCommitRole.PRODUCT_OWNER,
        ProviderFactCommitRole.ANALYST,
    }:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.ROLE_REQUIRED)
    if authorization.mfa_state is not RecordedMfaState.SATISFIED_RECORDED_SYNTHETIC:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.MFA_REQUIRED)
    if (
        authorization.step_up_state
        is not RecordedStepUpState.SATISFIED_RECORDED_SYNTHETIC
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.STEP_UP_REQUIRED)
    if (
        authorization.site_id != request.expected_site_id
        or authorization.site_id != bundle.dry_run.source.site_id
    ):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.SITE_SCOPE_MISMATCH)
    if (
        authorization.prepared_by_principal_id != bundle.prepared_by_principal_id
        or authorization.principal_id == bundle.prepared_by_principal_id
    ):
        fail_provider_fact_commit(
            ProviderFactCommitFailureCode.ROLE_SEPARATION_REQUIRED
        )
    if authorization.authorized_at != request.requested_at:
        fail_provider_fact_commit(ProviderFactCommitFailureCode.AUTHORIZATION_INVALID)
    age = request.requested_at - authorization.step_up_authenticated_at
    if age < timedelta(0) or age > timedelta(seconds=MAX_STEP_UP_AGE_SECONDS):
        fail_provider_fact_commit(ProviderFactCommitFailureCode.STEP_UP_STALE)


def _fact_payload(
    request: ProviderFactCommitRequest,
    bundle: RecordedRevenueDryRunBundle,
    row: RecordedAcceptedRevenueRow,
) -> dict[str, object]:
    return {
        **row.binding_payload(),
        "currency": Currency.JPY.value,
        "local_preview_binding_sha256": bundle.local_preview_binding_sha256.value,
        "mapping": LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED.value,
        "provider_code": PROVIDER_CODE,
        "request_sha256": request.request_sha256.value,
        "revenue_import_id": str(request.revenue_import_id),
        "site_id": str(request.expected_site_id),
        "source_sha256": request.expected_source_sha256.value,
    }


def _result_payload(
    result: ProviderFactCommitResult,
    *,
    include_audit: bool,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "authority": {
            "database": result.authority.database.value,
            "database_write_authorized": False,
            "live": result.authority.live.value,
            "live_authorized": False,
            "network": result.authority.network.value,
            "network_authorized": False,
            "provider": result.authority.provider.value,
            "provider_call_authorized": False,
            "publication": result.authority.publication.value,
            "publication_authorized": False,
            "release": result.authority.release.value,
            "release_authorized": False,
            "staging": result.authority.staging.value,
            "staging_authorized": False,
            "production": result.authority.production.value,
            "production_authorized": False,
        },
        "commission_events": [
            item.event_sha256.value for item in result.commission_events
        ],
        "commit_state": result.commit_state.value,
        "execution": result.execution.value,
        "facts": [item.fact_sha256.value for item in result.facts],
        "local_preview_binding_sha256": result.local_preview_binding_sha256.value,
        "mapping": result.mapping.value,
        "outbox": [item.outbox_sha256.value for item in result.outbox],
        "profile": PROFILE,
        "request_sha256": result.request_sha256.value,
        "status_summaries": [
            item.binding_payload() for item in result.status_summaries
        ],
    }
    if include_audit:
        payload["audit_sha256"] = result.audit.audit_sha256.value
        payload["result_sha256"] = result.result_sha256.value
    return payload


def build_provider_fact_commit_result(
    *,
    request: ProviderFactCommitRequest,
    bundle: RecordedRevenueDryRunBundle,
    authorization: RecordedProviderFactCommitAuthorization,
) -> ProviderFactCommitResult:
    """Pure deterministic local result; it performs no persistence or I/O."""

    if (
        type(request) is not ProviderFactCommitRequest
        or type(bundle) is not RecordedRevenueDryRunBundle
        or type(authorization) is not RecordedProviderFactCommitAuthorization
    ):
        fail_provider_fact_commit()
    _require_request_matches_bundle(request, bundle)
    _require_authorization(request, bundle, authorization)
    facts: list[RecordedProviderFact] = []
    events: list[RecordedCommissionEvent] = []
    for row in bundle.accepted_rows:
        fact_sha = _digest(_fact_payload(request, bundle, row))
        facts.append(
            RecordedProviderFact(
                fact_sha256=fact_sha,
                revenue_import_id=request.revenue_import_id,
                site_id=request.expected_site_id,
                provider_code=PROVIDER_CODE,
                provider_event_key=row.provider_event_key,
                source_row_no=row.row_no,
                source_row_sha256=row.row_sha256,
                status=row.event_type,
                occurred_at=row.event_at,
                generated_commission_jpy=row.generated_commission_jpy,
                confirmed_commission_jpy=row.confirmed_commission_jpy,
                currency=Currency.JPY,
                source_sha256=request.expected_source_sha256,
                local_preview_binding_sha256=bundle.local_preview_binding_sha256,
                mapping=LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED,
            )
        )
        event_sha = _digest(
            {
                "canonical_event_type": None,
                "fact_sha256": fact_sha.value,
                "mapping": LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED.value,
                "profile": PROFILE,
                "source_event_type": row.event_type.value,
            }
        )
        events.append(
            RecordedCommissionEvent(
                event_sha256=event_sha,
                fact_sha256=fact_sha,
                source_event_type=row.event_type,
                canonical_event_type=None,
                mapping=LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED,
                provider_occurred_at=row.event_at,
                generated_commission_jpy=row.generated_commission_jpy,
                confirmed_commission_jpy=row.confirmed_commission_jpy,
            )
        )
    preliminary_payload = {
        "authorization_sha256": authorization.authorization_sha256.value,
        "commission_events": [item.event_sha256.value for item in events],
        "facts": [item.fact_sha256.value for item in facts],
        "local_preview_binding_sha256": bundle.local_preview_binding_sha256.value,
        "profile": PROFILE,
        "request_sha256": request.request_sha256.value,
        "status_summaries": [
            item.binding_payload() for item in bundle.status_summaries
        ],
    }
    result_sha = _digest(preliminary_payload)
    audit_payload = {
        "action": AUDIT_ACTION,
        "authorization_sha256": authorization.authorization_sha256.value,
        "principal_id": str(authorization.principal_id),
        "reason_sha256": request.reason.sha256.value,
        "recorded_at": _instant_text(authorization.authorized_at),
        "request_sha256": request.request_sha256.value,
        "result_sha256": result_sha.value,
        "site_id": str(authorization.site_id),
    }
    audit = RecordedAuditRecord(
        audit_sha256=_digest(audit_payload),
        action=AUDIT_ACTION,
        principal_id=authorization.principal_id,
        site_id=authorization.site_id,
        request_sha256=request.request_sha256,
        authorization_sha256=authorization.authorization_sha256,
        result_sha256=result_sha,
        reason_sha256=request.reason.sha256,
        recorded_at=authorization.authorized_at,
    )
    outbox_payloads = [
        (
            LOCAL_COMMITTED_EVENT,
            result_sha,
            _digest(
                {
                    "accepted_count": len(facts),
                    "result_sha256": result_sha.value,
                    "source_sha256": request.expected_source_sha256.value,
                }
            ),
        ),
        *(
            (
                LOCAL_FACT_EVENT,
                fact.fact_sha256,
                event.event_sha256,
            )
            for fact, event in zip(facts, events, strict=True)
        ),
    ]
    outbox = tuple(
        RecordedOutboxRecord(
            outbox_sha256=_digest(
                {
                    "aggregate_sha256": aggregate.value,
                    "event_type": event_type,
                    "payload_sha256": payload.value,
                    "recorded_at": _instant_text(authorization.authorized_at),
                }
            ),
            event_type=event_type,
            aggregate_sha256=aggregate,
            payload_sha256=payload,
            recorded_at=authorization.authorized_at,
        )
        for event_type, aggregate, payload in outbox_payloads
    )
    return ProviderFactCommitResult(
        result_sha256=result_sha,
        request_sha256=request.request_sha256,
        local_preview_binding_sha256=bundle.local_preview_binding_sha256,
        execution=ProviderFactCommitExecution.RECORDED_SYNTHETIC_ONLY,
        commit_state=RecordedCommitState.PROCESS_LOCAL_ATOMIC_COMMITTED,
        facts=tuple(facts),
        commission_events=tuple(events),
        status_summaries=bundle.status_summaries,
        audit=audit,
        outbox=outbox,
        authority=ProviderFactCommitAuthority(),
        mapping=LocalMappingState.UNVERIFIED_PRESERVED_UNMAPPED,
    )


__all__ = (
    "AUDIT_ACTION",
    "CanonicalCommissionEventType",
    "Currency",
    "ExternalExecutionStatus",
    "JpyAmount",
    "LOCAL_COMMITTED_EVENT",
    "LOCAL_FACT_EVENT",
    "LOCAL_PREVIEW_BINDING_ALGORITHM",
    "LocalIdempotencyKey",
    "LocalMappingState",
    "MAX_STEP_UP_AGE_SECONDS",
    "PROFILE",
    "PROVIDER_CODE",
    "ProviderEventKey",
    "ProviderFactCommitAuthority",
    "ProviderFactCommitExecution",
    "ProviderFactCommitFailure",
    "ProviderFactCommitFailureCode",
    "ProviderFactCommitReason",
    "ProviderFactCommitRequest",
    "ProviderFactCommitResult",
    "ProviderFactCommitRole",
    "ProviderFactStatusSummary",
    "RecordedAcceptedRevenueRow",
    "RecordedAuditRecord",
    "RecordedCommissionEvent",
    "RecordedCommitState",
    "RecordedMfaState",
    "RecordedOutboxRecord",
    "RecordedProviderFact",
    "RecordedProviderFactCommitAuthorization",
    "RecordedRevenueDryRunBundle",
    "RecordedStepUpState",
    "RecordedSubjectState",
    "build_provider_fact_commit_result",
    "fail_provider_fact_commit",
)
