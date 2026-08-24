"""Headless recorded analytics/finance read model for Canonical ST-1104.

The module combines two already calculated, caller-supplied synthetic snapshots.
It never fetches, persists, allocates, ranks, publishes, or registers an admin
route.  Source periods remain independent and unavailable values remain null.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import re
from typing import Final, NoReturn, SupportsIndex

from raos.domain.analytics.kpi_read_model import (
    KpiAvailability,
    KpiReadModelRow,
    KpiReadModelSnapshot,
    RAKUTEN_BLOG_PROGRAM,
)
from raos.domain.finance.unit_economics import (
    MetricAvailability as UnitMetricAvailability,
    UnitEconomicsMetric,
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
)


PROFILE: Final = "RAOS_ST1104_RECORDED_SYNTHETIC_DASHBOARD_V2"
SCHEMA_VERSION: Final = "2.0.0"
STORY_ID: Final = "ST-1104"
SCREEN_ORDER: Final = (
    "ANA-001",
    "ANA-002",
    "ANA-003",
    "FIN-001",
    "FIN-002",
    "FIN-003",
)
EXPECTED_VIEW_MAPPING: Final = (
    ("ANA-001", ("KPI-012", "KPI-014", "KPI-006", "KPI-018", "KPI-020")),
    ("ANA-002", ("KPI-012", "KPI-014")),
    ("ANA-003", ("KPI-006", "KPI-007")),
    ("FIN-001", ("REVENUE_IMPORT_STATUS",)),
    (
        "FIN-002",
        (
            "PROVIDER_CONFIRMED_REWARD",
            "DIRECT_CONFIRMED_REWARD",
            "ESTIMATED_CONFIRMED_REWARD",
            "UNATTRIBUTED_CONFIRMED_REWARD",
            "REWARD_CONSERVATION_DIFFERENCE",
        ),
    ),
    (
        "FIN-003",
        (
            "KPI-001",
            "SUPPLEMENTAL-DIRECT-REWARD",
            "KPI-002-DIRECT-VIEW",
            "KPI-003",
            "KPI-004",
            "KPI-022",
            "KPI-023",
            "KPI-025",
            "SUPPLEMENTAL-CONTENT-HOUR",
        ),
    ),
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_REDACTED = "<redacted-st1104-dashboard>"
_MAX_CANONICAL_BYTES: Final = 4 * 1024 * 1024


class DashboardFailureCode(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    RESULT_MISMATCH = "RESULT_MISMATCH"
    RECORDED_SOURCE_UNAVAILABLE = "RECORDED_SOURCE_UNAVAILABLE"
    FIXTURE_INVALID = "FIXTURE_INVALID"
    FIXTURE_HASH_MISMATCH = "FIXTURE_HASH_MISMATCH"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"


class DashboardFailure(RuntimeError):
    """Closed, non-reflecting failure for untrusted recorded input."""

    __slots__ = ("_code",)

    def __init__(self, code: DashboardFailureCode) -> None:
        if type(code) is not DashboardFailureCode:
            raise TypeError("invalid dashboard failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> DashboardFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"DashboardFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("dashboard failure serialization is forbidden")


def fail_dashboard(
    code: DashboardFailureCode = DashboardFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise DashboardFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("dashboard value serialization is forbidden")


def _utc_second(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
        or value.microsecond != 0
        or value.fold != 0
    ):
        fail_dashboard()
    return value.replace(tzinfo=timezone.utc)


def _instant(value: datetime) -> str:
    return _utc_second(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _decimal(value: Decimal) -> str:
    if type(value) is not Decimal or not value.is_finite():
        fail_dashboard()
    return format(value, "f")


def _canonical_bytes(value: object) -> bytes:
    try:
        content = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except Exception:
        fail_dashboard()
    if not content or len(content) > _MAX_CANONICAL_BYTES:
        fail_dashboard()
    return content


@dataclass(frozen=True, slots=True, repr=False)
class DashboardDigest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            fail_dashboard()

    @classmethod
    def of(cls, content: bytes) -> DashboardDigest:
        if type(content) is not bytes:
            fail_dashboard()
        return cls(hashlib.sha256(content).hexdigest())


@dataclass(frozen=True, slots=True, repr=False)
class RecordedDashboardCommand(_Redacted):
    fixture_sha256: DashboardDigest
    fixture_bytes: int
    expected_kpi_input_sha256: DashboardDigest
    expected_unit_input_sha256: DashboardDigest
    expected_unit_result_sha256: DashboardDigest

    def __post_init__(self) -> None:
        if (
            type(self.fixture_sha256) is not DashboardDigest
            or type(self.fixture_bytes) is not int
            or not 0 < self.fixture_bytes <= _MAX_CANONICAL_BYTES
            or type(self.expected_kpi_input_sha256) is not DashboardDigest
            or type(self.expected_unit_input_sha256) is not DashboardDigest
            or type(self.expected_unit_result_sha256) is not DashboardDigest
        ):
            fail_dashboard()


@dataclass(frozen=True, slots=True, repr=False)
class RecordedDashboardSources(_Redacted):
    recording_id: str
    fixture_sha256: DashboardDigest
    evaluated_at: datetime
    screen_order: tuple[str, ...]
    view_mapping: tuple[tuple[str, tuple[str, ...]], ...]
    kpi_snapshot: KpiReadModelSnapshot
    unit_request: UnitEconomicsRunRequest
    unit_result: UnitEconomicsRunResult

    def __post_init__(self) -> None:
        if (
            self.recording_id != "st1104-six-screen-recorded-v2"
            or type(self.fixture_sha256) is not DashboardDigest
            or type(self.screen_order) is not tuple
            or self.screen_order != SCREEN_ORDER
            or type(self.view_mapping) is not tuple
            or self.view_mapping != EXPECTED_VIEW_MAPPING
            or type(self.kpi_snapshot) is not KpiReadModelSnapshot
            or type(self.unit_request) is not UnitEconomicsRunRequest
            or type(self.unit_result) is not UnitEconomicsRunResult
        ):
            fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
        object.__setattr__(self, "evaluated_at", _utc_second(self.evaluated_at))
        if (
            self.kpi_snapshot.context.program_id.value != RAKUTEN_BLOG_PROGRAM
            or self.unit_request.attribution_request.program != RAKUTEN_BLOG_PROGRAM
            or self.unit_result.input_sha256.value
            != self.unit_request.input_sha256.value
        ):
            fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)


class MetricAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"


class MetricFreshness(str, Enum):
    RECORDED_SYNTHETIC_NO_LIVE_ATTESTATION = "RECORDED_SYNTHETIC_NO_LIVE_ATTESTATION"
    UNKNOWN_SOURCE_HAS_NO_APPROVED_FRESHNESS_POLICY = (
        "UNKNOWN_SOURCE_HAS_NO_APPROVED_FRESHNESS_POLICY"
    )
    UNAVAILABLE = "UNAVAILABLE"


class MetricVerification(str, Enum):
    RECORDED_SYNTHETIC_INPUTS_VERIFIED = "RECORDED_SYNTHETIC_INPUTS_VERIFIED"
    RECORDED_SYNTHETIC_UNAVAILABLE = "RECORDED_SYNTHETIC_UNAVAILABLE"
    LIVE_NOT_EXECUTED = "LIVE_NOT_EXECUTED"


class ScreenAvailability(str, Enum):
    AVAILABLE_RECORDED = "AVAILABLE_RECORDED"
    PARTIAL_RECORDED = "PARTIAL_RECORDED"
    UNAVAILABLE_DEPENDENCY = "UNAVAILABLE_DEPENDENCY"


@dataclass(frozen=True, slots=True, repr=False)
class MetricReadModel(_Redacted):
    metric_id: str
    name: str
    availability: MetricAvailability
    value: Decimal | None
    unit: str
    basis: str
    source_story_id: str
    source_sha256s: tuple[DashboardDigest, ...]
    period_start: str | None
    period_end: str | None
    period_end_inclusive: bool | None
    source_timestamp: datetime | None
    freshness: MetricFreshness
    upstream_freshness: str | None
    verification: MetricVerification
    unavailable_reason: str | None
    synthetic: bool = True
    live_verified: bool = False
    unknown_as_zero_allowed: bool = False

    def __post_init__(self) -> None:
        available = (
            self.availability is MetricAvailability.AVAILABLE
            and type(self.value) is Decimal
            and self.value.is_finite()
            and self.unavailable_reason is None
            and bool(self.source_sha256s)
        )
        unavailable = (
            self.availability is MetricAvailability.UNAVAILABLE
            and self.value is None
            and type(self.unavailable_reason) is str
            and bool(self.unavailable_reason)
        )
        if (
            type(self.metric_id) is not str
            or not self.metric_id
            or type(self.name) is not str
            or not self.name
            or type(self.availability) is not MetricAvailability
            or not (available or unavailable)
            or type(self.unit) is not str
            or not self.unit
            or type(self.basis) is not str
            or not self.basis
            or self.source_story_id not in {"ST-1205", "ST-1304", "ST-1301"}
            or type(self.source_sha256s) is not tuple
            or any(type(item) is not DashboardDigest for item in self.source_sha256s)
            or (
                self.source_timestamp is not None
                and type(self.source_timestamp) is not datetime
            )
            or type(self.freshness) is not MetricFreshness
            or type(self.verification) is not MetricVerification
            or self.synthetic is not True
            or self.live_verified is not False
            or self.unknown_as_zero_allowed is not False
        ):
            fail_dashboard(DashboardFailureCode.RESULT_MISMATCH)
        if self.source_timestamp is not None:
            object.__setattr__(
                self, "source_timestamp", _utc_second(self.source_timestamp)
            )

    def payload(self) -> dict[str, object]:
        return {
            "availability": self.availability.value,
            "basis": self.basis,
            "freshness": self.freshness.value,
            "live_verified": False,
            "metric_id": self.metric_id,
            "name": self.name,
            "period": (
                None
                if self.period_start is None
                else {
                    "end": self.period_end,
                    "end_inclusive": self.period_end_inclusive,
                    "start": self.period_start,
                }
            ),
            "source_sha256s": [item.value for item in self.source_sha256s],
            "source_story_id": self.source_story_id,
            "source_timestamp": (
                None
                if self.source_timestamp is None
                else _instant(self.source_timestamp)
            ),
            "synthetic": True,
            "unit": self.unit,
            "unknown_as_zero_allowed": False,
            "unavailable_reason": self.unavailable_reason,
            "upstream_freshness": self.upstream_freshness,
            "value_decimal": None if self.value is None else _decimal(self.value),
            "verification": self.verification.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ScreenReadModel(_Redacted):
    screen_id: str
    name: str
    route: str
    availability: ScreenAvailability
    metric_rows: tuple[MetricReadModel, ...]
    status_code: str
    status_text: str
    status_icon: str
    canonical_metric_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_ids = dict(EXPECTED_VIEW_MAPPING).get(self.screen_id)
        if (
            self.screen_id not in SCREEN_ORDER
            or type(self.name) is not str
            or not self.name
            or type(self.route) is not str
            or not self.route.startswith("/admin/")
            or type(self.availability) is not ScreenAvailability
            or type(self.metric_rows) is not tuple
            or not self.metric_rows
            or any(type(item) is not MetricReadModel for item in self.metric_rows)
            or type(self.canonical_metric_ids) is not tuple
            or self.canonical_metric_ids != expected_ids
            or tuple(item.metric_id for item in self.metric_rows) != expected_ids
            or any(
                type(value) is not str or not value
                for value in (self.status_code, self.status_text, self.status_icon)
            )
        ):
            fail_dashboard(DashboardFailureCode.RESULT_MISMATCH)
        unavailable = sum(
            item.availability is MetricAvailability.UNAVAILABLE
            for item in self.metric_rows
        )
        expected = (
            ScreenAvailability.UNAVAILABLE_DEPENDENCY
            if unavailable == len(self.metric_rows)
            else (
                ScreenAvailability.PARTIAL_RECORDED
                if unavailable
                else ScreenAvailability.AVAILABLE_RECORDED
            )
        )
        if self.availability is not expected:
            fail_dashboard(DashboardFailureCode.RESULT_MISMATCH)

    def payload(self) -> dict[str, object]:
        return {
            "accessibility": {
                "chart_alternative": "TABLE_OR_TEXT_REQUIRED",
                "color_only": False,
                "column_headers_required": True,
                "keyboard_model_required": True,
                "row_headers_required": True,
                "status_code": self.status_code,
                "status_icon": self.status_icon,
                "status_text": self.status_text,
                "table_caption_required": True,
            },
            "availability": self.availability.value,
            "canonical_metric_ids": list(self.canonical_metric_ids),
            "component_mapping_authority": "LOCAL_HEADLESS_CANDIDATE_ONLY",
            "metric_rows": [item.payload() for item in self.metric_rows],
            "name": self.name,
            "route": self.route,
            "route_registered": False,
            "screen_id": self.screen_id,
        }


@dataclass(frozen=True, slots=True, repr=False)
class DashboardAuthority(_Redacted):
    authentication: bool = False
    authorization: bool = False
    mfa: bool = False
    step_up: bool = False
    route_registration: bool = False
    render: bool = False
    file_intake: bool = False
    import_commit: bool = False
    reconciliation_commit: bool = False
    mutation: bool = False
    persistence: bool = False
    database: bool = False
    network: bool = False
    provider: bool = False
    telemetry: bool = False
    financial_allocation: bool = False
    ranking_or_editorial_mutation: bool = False
    publication: bool = False
    staging: bool = False
    release: bool = False
    production: bool = False

    def __post_init__(self) -> None:
        if any(getattr(self, name) is not False for name in self.__slots__):
            fail_dashboard(DashboardFailureCode.RESULT_MISMATCH)

    def payload(self) -> dict[str, bool]:
        return {name: False for name in self.__slots__}


@dataclass(frozen=True, slots=True, repr=False)
class AnalyticsFinanceDashboardSnapshot(_Redacted):
    recording_id: str
    evaluated_at: datetime
    fixture_sha256: DashboardDigest
    kpi_input_sha256: DashboardDigest
    unit_input_sha256: DashboardDigest
    unit_result_sha256: DashboardDigest
    screens: tuple[ScreenReadModel, ...]
    cross_source_comparison: str
    authority: DashboardAuthority
    result_sha256: DashboardDigest = field(init=False)

    def __post_init__(self) -> None:
        if (
            self.recording_id != "st1104-six-screen-recorded-v2"
            or type(self.fixture_sha256) is not DashboardDigest
            or type(self.kpi_input_sha256) is not DashboardDigest
            or type(self.unit_input_sha256) is not DashboardDigest
            or type(self.unit_result_sha256) is not DashboardDigest
            or type(self.screens) is not tuple
            or tuple(item.screen_id for item in self.screens) != SCREEN_ORDER
            or any(type(item) is not ScreenReadModel for item in self.screens)
            or self.cross_source_comparison != "UNAVAILABLE_PERIOD_MISMATCH"
            or type(self.authority) is not DashboardAuthority
        ):
            fail_dashboard(DashboardFailureCode.RESULT_MISMATCH)
        object.__setattr__(self, "evaluated_at", _utc_second(self.evaluated_at))
        object.__setattr__(
            self,
            "result_sha256",
            DashboardDigest.of(
                _canonical_bytes(self.payload(include_result_hash=False))
            ),
        )

    def payload(self, *, include_result_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "accessibility": {
                "browser_verified": False,
                "color_only": False,
                "landmarks_required": True,
                "one_h1_required": True,
                "screen_reader_verified": False,
                "skip_link_required": True,
                "zoom_target_percent": 200,
            },
            "authority": self.authority.payload(),
            "canonical_dashboard_references": [
                {
                    "dashboard_id": "DASH-002",
                    "mapping_authority": "REFERENCE_ONLY_NOT_SCREEN_OWNERSHIP",
                    "runtime_verification": "NOT_EXECUTED",
                    "tile_ids": ["KPI-012", "KPI-014", "KPI-006", "KPI-018", "KPI-020"],
                },
                {
                    "dashboard_id": "DASH-003",
                    "mapping_authority": "REFERENCE_ONLY_NOT_SCREEN_OWNERSHIP",
                    "runtime_verification": "NOT_EXECUTED",
                    "tile_ids": [
                        "KPI-001",
                        "KPI-002",
                        "KPI-003",
                        "KPI-004",
                        "KPI-010",
                        "KPI-011",
                    ],
                },
            ],
            "classification": (
                "LOCAL_RECORDED_SYNTHETIC_ANALYTICS_FINANCE_DASHBOARD_V2"
            ),
            "cross_source_comparison": self.cross_source_comparison,
            "data_classification": "CONFIDENTIAL",
            "evaluated_at": _instant(self.evaluated_at),
            "fixture_sha256": self.fixture_sha256.value,
            "freshness_policy": ("SHOW_SOURCE_TIMESTAMPS_NO_INFERRED_CURRENT_OR_STALE"),
            "kpi_input_sha256": self.kpi_input_sha256.value,
            "live_verification": "NOT_EXECUTED",
            "program": RAKUTEN_BLOG_PROGRAM,
            "recording_id": self.recording_id,
            "schema_version": SCHEMA_VERSION,
            "screens": [item.payload() for item in self.screens],
            "story_id": STORY_ID,
            "synthetic": True,
            "unit_input_sha256": self.unit_input_sha256.value,
            "unit_result_sha256": self.unit_result_sha256.value,
            "verification": {
                "TST-022": "NOT_EXECUTED",
                "TST-024": "NOT_EXECUTED",
                "TST-030": "NOT_EXECUTED",
                "browser": "NOT_EXECUTED",
                "formal": "NOT_EXECUTED",
                "live": "NOT_EXECUTED",
                "production": "NOT_EXECUTED",
                "release": "NOT_EXECUTED",
                "staging": "NOT_EXECUTED",
            },
        }
        if include_result_hash:
            payload["result_sha256"] = self.result_sha256.value
        return payload

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.payload())


_SCREEN_METADATA: Final = {
    "ANA-001": ("Content Performance", "/admin/analytics/content"),
    "ANA-002": ("Search Performance", "/admin/analytics/search"),
    "ANA-003": ("Affiliate Clicks", "/admin/analytics/clicks"),
    "FIN-001": ("成果Import", "/admin/finance/imports"),
    "FIN-002": ("Reconciliation", "/admin/finance/reconciliation/{id}"),
    "FIN-003": ("Unit Economics", "/admin/finance/unit-economics"),
}


def _kpi_metric(
    row: KpiReadModelRow, snapshot: KpiReadModelSnapshot
) -> MetricReadModel:
    available = row.availability is KpiAvailability.AVAILABLE
    return MetricReadModel(
        metric_id=row.kpi_id,
        name=row.name,
        availability=(
            MetricAvailability.AVAILABLE
            if available
            else MetricAvailability.UNAVAILABLE
        ),
        value=row.value if available else None,
        unit=row.unit.value,
        basis=row.attribution_basis.value,
        source_story_id="ST-1205",
        source_sha256s=(DashboardDigest(snapshot.input_digest.value),),
        period_start=row.period.start_date.isoformat(),
        period_end=row.period.end_date.isoformat(),
        period_end_inclusive=True,
        source_timestamp=snapshot.recorded_at,
        freshness=MetricFreshness.RECORDED_SYNTHETIC_NO_LIVE_ATTESTATION,
        upstream_freshness=row.freshness,
        verification=(
            MetricVerification.RECORDED_SYNTHETIC_INPUTS_VERIFIED
            if available
            else MetricVerification.RECORDED_SYNTHETIC_UNAVAILABLE
        ),
        unavailable_reason=(
            None if row.unavailable_reason is None else row.unavailable_reason.value
        ),
    )


def _unit_metric(
    row: UnitEconomicsMetric,
    request: UnitEconomicsRunRequest,
    result: UnitEconomicsRunResult,
) -> MetricReadModel:
    available = row.availability is UnitMetricAvailability.AVAILABLE
    return MetricReadModel(
        metric_id=row.metric_id,
        name=row.name,
        availability=(
            MetricAvailability.AVAILABLE
            if available
            else MetricAvailability.UNAVAILABLE
        ),
        value=row.value if available else None,
        unit=row.unit.value,
        basis=row.basis.value,
        source_story_id="ST-1304",
        source_sha256s=(DashboardDigest(result.result_sha256.value),),
        period_start=row.period.start_date.isoformat(),
        period_end=row.period.end_exclusive_date.isoformat(),
        period_end_inclusive=False,
        source_timestamp=request.requested_at,
        freshness=MetricFreshness.UNKNOWN_SOURCE_HAS_NO_APPROVED_FRESHNESS_POLICY,
        upstream_freshness=None,
        verification=(
            MetricVerification.RECORDED_SYNTHETIC_INPUTS_VERIFIED
            if available
            else MetricVerification.RECORDED_SYNTHETIC_UNAVAILABLE
        ),
        unavailable_reason=(
            None if row.unavailable_reason is None else row.unavailable_reason.value
        ),
    )


def _unavailable_import_metric() -> MetricReadModel:
    return MetricReadModel(
        metric_id="REVENUE_IMPORT_STATUS",
        name="revenue_import_status",
        availability=MetricAvailability.UNAVAILABLE,
        value=None,
        unit="STATUS",
        basis="UNAVAILABLE_DEPENDENCY",
        source_story_id="ST-1301",
        source_sha256s=(),
        period_start=None,
        period_end=None,
        period_end_inclusive=None,
        source_timestamp=None,
        freshness=MetricFreshness.UNAVAILABLE,
        upstream_freshness=None,
        verification=MetricVerification.LIVE_NOT_EXECUTED,
        unavailable_reason="UNAVAILABLE_UNDECLARED_DEPENDENCY",
    )


def _total_metric(
    *,
    metric_id: str,
    name: str,
    value: Decimal,
    basis: str,
    request: UnitEconomicsRunRequest,
    result: UnitEconomicsRunResult,
) -> MetricReadModel:
    period = request.attribution_request.period
    return MetricReadModel(
        metric_id=metric_id,
        name=name,
        availability=MetricAvailability.AVAILABLE,
        value=value,
        unit="JPY",
        basis=basis,
        source_story_id="ST-1304",
        source_sha256s=(DashboardDigest(result.result_sha256.value),),
        period_start=period.start_date.isoformat(),
        period_end=period.end_exclusive_date.isoformat(),
        period_end_inclusive=False,
        source_timestamp=request.requested_at,
        freshness=MetricFreshness.UNKNOWN_SOURCE_HAS_NO_APPROVED_FRESHNESS_POLICY,
        upstream_freshness=None,
        verification=MetricVerification.RECORDED_SYNTHETIC_INPUTS_VERIFIED,
        unavailable_reason=None,
    )


def _screen(screen_id: str, rows: tuple[MetricReadModel, ...]) -> ScreenReadModel:
    unavailable = sum(
        item.availability is MetricAvailability.UNAVAILABLE for item in rows
    )
    availability = (
        ScreenAvailability.UNAVAILABLE_DEPENDENCY
        if unavailable == len(rows)
        else ScreenAvailability.PARTIAL_RECORDED
        if unavailable
        else ScreenAvailability.AVAILABLE_RECORDED
    )
    code = availability.value
    text = {
        ScreenAvailability.AVAILABLE_RECORDED: "Recorded synthetic data is available.",
        ScreenAvailability.PARTIAL_RECORDED: "Some recorded synthetic data is unavailable.",
        ScreenAvailability.UNAVAILABLE_DEPENDENCY: "The required data source is unavailable.",
    }[availability]
    icon = {
        ScreenAvailability.AVAILABLE_RECORDED: "STATUS_INFO",
        ScreenAvailability.PARTIAL_RECORDED: "STATUS_WARNING",
        ScreenAvailability.UNAVAILABLE_DEPENDENCY: "STATUS_UNKNOWN",
    }[availability]
    name, route = _SCREEN_METADATA[screen_id]
    return ScreenReadModel(
        screen_id=screen_id,
        name=name,
        route=route,
        availability=availability,
        metric_rows=rows,
        status_code=code,
        status_text=text,
        status_icon=icon,
        canonical_metric_ids=dict(EXPECTED_VIEW_MAPPING)[screen_id],
    )


def build_analytics_finance_dashboard(
    sources: RecordedDashboardSources,
) -> AnalyticsFinanceDashboardSnapshot:
    """Project exact recorded dependency results without effects or allocation."""

    if type(sources) is not RecordedDashboardSources:
        fail_dashboard()
    kpi = {row.kpi_id: row for row in sources.kpi_snapshot.rows}
    unit = {row.metric_id: row for row in sources.unit_result.metrics}
    if (
        len(kpi) != len(sources.kpi_snapshot.rows)
        or len(unit) != len(sources.unit_result.metrics)
        or any(
            metric_id not in kpi
            for metric_id in (
                "KPI-012",
                "KPI-014",
                "KPI-006",
                "KPI-018",
                "KPI-020",
                "KPI-007",
            )
        )
        or any(
            metric_id not in unit
            for metric_id in dict(EXPECTED_VIEW_MAPPING)["FIN-003"]
        )
    ):
        fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)

    def kpi_metric(metric_id: str) -> MetricReadModel:
        return _kpi_metric(kpi[metric_id], sources.kpi_snapshot)

    def unit_metric(metric_id: str) -> MetricReadModel:
        return _unit_metric(unit[metric_id], sources.unit_request, sources.unit_result)

    totals = sources.unit_result.totals
    fin002 = (
        _total_metric(
            metric_id="PROVIDER_CONFIRMED_REWARD",
            name="provider_confirmed_reward_jpy",
            value=Decimal(totals.provider_confirmed_reward_jpy.value),
            basis="VERIFIED_PROVIDER_FACT_TOTAL",
            request=sources.unit_request,
            result=sources.unit_result,
        ),
        _total_metric(
            metric_id="DIRECT_CONFIRMED_REWARD",
            name="direct_confirmed_reward_jpy",
            value=Decimal(totals.direct_confirmed_reward_jpy.value),
            basis="VERIFIED_DIRECT_ONLY",
            request=sources.unit_request,
            result=sources.unit_result,
        ),
        _total_metric(
            metric_id="ESTIMATED_CONFIRMED_REWARD",
            name="estimated_confirmed_reward_jpy",
            value=Decimal(totals.estimated_confirmed_reward_jpy.value),
            basis="ESTIMATED_SEPARATE_NOT_PROVIDER_ATTRIBUTION",
            request=sources.unit_request,
            result=sources.unit_result,
        ),
        _total_metric(
            metric_id="UNATTRIBUTED_CONFIRMED_REWARD",
            name="unattributed_confirmed_reward_jpy",
            value=Decimal(totals.unattributed_confirmed_reward_jpy.value),
            basis="UNATTRIBUTED_SEPARATE_NOT_ALLOCATED",
            request=sources.unit_request,
            result=sources.unit_result,
        ),
        _total_metric(
            metric_id="REWARD_CONSERVATION_DIFFERENCE",
            name="reward_conservation_difference_jpy",
            value=Decimal(0),
            basis="RECORDED_SYNTHETIC_CONSERVATION",
            request=sources.unit_request,
            result=sources.unit_result,
        ),
    )
    screens = (
        _screen(
            "ANA-001",
            tuple(kpi_metric(item) for item in dict(EXPECTED_VIEW_MAPPING)["ANA-001"]),
        ),
        _screen(
            "ANA-002",
            tuple(kpi_metric(item) for item in dict(EXPECTED_VIEW_MAPPING)["ANA-002"]),
        ),
        _screen(
            "ANA-003",
            tuple(kpi_metric(item) for item in dict(EXPECTED_VIEW_MAPPING)["ANA-003"]),
        ),
        _screen("FIN-001", (_unavailable_import_metric(),)),
        _screen("FIN-002", fin002),
        _screen(
            "FIN-003",
            tuple(unit_metric(item) for item in dict(EXPECTED_VIEW_MAPPING)["FIN-003"]),
        ),
    )
    kpi_period = (
        sources.kpi_snapshot.context.period.start_date,
        sources.kpi_snapshot.context.period.end_date,
    )
    unit_period = (
        sources.unit_request.attribution_request.period.start_date,
        sources.unit_request.attribution_request.period.end_exclusive_date,
    )
    if kpi_period == unit_period:
        fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
    return AnalyticsFinanceDashboardSnapshot(
        recording_id=sources.recording_id,
        evaluated_at=sources.evaluated_at,
        fixture_sha256=sources.fixture_sha256,
        kpi_input_sha256=DashboardDigest(sources.kpi_snapshot.input_digest.value),
        unit_input_sha256=DashboardDigest(sources.unit_request.input_sha256.value),
        unit_result_sha256=DashboardDigest(sources.unit_result.result_sha256.value),
        screens=screens,
        cross_source_comparison="UNAVAILABLE_PERIOD_MISMATCH",
        authority=DashboardAuthority(),
    )


__all__ = (
    "AnalyticsFinanceDashboardSnapshot",
    "DashboardAuthority",
    "DashboardDigest",
    "DashboardFailure",
    "DashboardFailureCode",
    "EXPECTED_VIEW_MAPPING",
    "MetricAvailability",
    "MetricFreshness",
    "MetricReadModel",
    "MetricVerification",
    "PROFILE",
    "RecordedDashboardCommand",
    "RecordedDashboardSources",
    "SCHEMA_VERSION",
    "SCREEN_ORDER",
    "STORY_ID",
    "ScreenAvailability",
    "ScreenReadModel",
    "build_analytics_finance_dashboard",
    "fail_dashboard",
)
