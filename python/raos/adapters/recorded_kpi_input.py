"""Strict caller-bytes adapter for the ST-1205 synthetic KPI fixture."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from threading import RLock
from typing import NoReturn, TypeVar, cast, final

from raos.domain.analytics.kpi_read_model import (
    AttributionBasis,
    CalculationContext,
    CohortState,
    InputSource,
    KPI_IDS,
    KpiCalculationCommand,
    KpiFailure,
    KpiFailureCode,
    KpiInputFrame,
    MeasurementPeriod,
    MetricObservation,
    ProgramId,
    RecordedKpiInputBatch,
    Sha256Digest,
    fail_kpi,
)


COMPLETE_FIXTURE_SHA256 = (
    "da6d51ccd7ba56411ec81e316994659849e4ea7fa11e5458982a99a6f2317676"
)
COMPLETE_FIXTURE_BYTES = 11_343

_ROOT_KEYS = frozenset(
    {
        "schema_version",
        "recording_id",
        "synthetic",
        "recorded_at",
        "period",
        "program_id",
        "selected_attribution_basis",
        "observations",
        "expected_results",
        "expected_learning_results",
    }
)
_PERIOD_KEYS = frozenset({"start_date", "end_date"})
_OBSERVATION_KEYS = frozenset(
    {
        "metric_key",
        "value",
        "source",
        "verified",
        "cohort_state",
        "attribution_basis",
        "attribution_verified",
    }
)
_EXPECTED_KPI_KEYS = frozenset({"kpi_id", "value"})
_EXPECTED_LEARNING_KEYS = frozenset({"metric_id", "value"})
_LEARNING_IDS = (
    "search_ctr",
    "affiliate_click_rate",
    "confirmed_reward_per_click",
    "confirmation_rate",
    "confirmed_reward_per_content_hour",
)


def _invalid() -> NoReturn:
    fail_kpi(KpiFailureCode.FIXTURE_DOCUMENT_INVALID)


def _reject_constant(value: str) -> NoReturn:
    del value
    _invalid()


def _strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _document(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    document = cast(dict[str, object], value)
    if frozenset(document) != keys:
        _invalid()
    return document


def _array(value: object) -> list[object]:
    if type(value) is not list:
        _invalid()
    return cast(list[object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _decimal(value: object) -> Decimal:
    raw = _text(value)
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        _invalid()
    if (
        not parsed.is_finite()
        or str(parsed) != raw
        or len(parsed.as_tuple().digits) > 38
    ):
        _invalid()
    return parsed


def _calendar_date(value: object) -> date:
    raw = _text(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _invalid()
    if parsed.isoformat() != raw:
        _invalid()
    return parsed


def _utc_timestamp(value: object) -> datetime:
    raw = _text(value)
    if len(raw) != 20 or not raw.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError:
        _invalid()
    normalized = parsed.astimezone(timezone.utc)
    if normalized.isoformat(timespec="seconds") != raw[:-1] + "+00:00":
        _invalid()
    return normalized


_EnumValue = TypeVar("_EnumValue", InputSource, CohortState, AttributionBasis)


def _enum(enum_type: type[_EnumValue], value: object) -> _EnumValue:
    raw = _text(value)
    try:
        return enum_type(raw)
    except ValueError:
        _invalid()


def _expected_results(value: object) -> None:
    rows = _array(value)
    if len(rows) != 30:
        _invalid()
    ids: list[str] = []
    for item in rows:
        row = _document(item, _EXPECTED_KPI_KEYS)
        ids.append(_text(row["kpi_id"]))
        _decimal(row["value"])
    if tuple(ids) != KPI_IDS:
        _invalid()


def _expected_learning_results(value: object) -> None:
    rows = _array(value)
    if len(rows) != 5:
        _invalid()
    ids: list[str] = []
    for item in rows:
        row = _document(item, _EXPECTED_LEARNING_KEYS)
        ids.append(_text(row["metric_id"]))
        _decimal(row["value"])
    if tuple(ids) != _LEARNING_IDS:
        _invalid()


def _parse_fixture(
    command: KpiCalculationCommand, fixture_bytes: bytes
) -> RecordedKpiInputBatch:
    if (
        type(fixture_bytes) is not bytes
        or len(fixture_bytes) != COMPLETE_FIXTURE_BYTES
        or Sha256Digest.of(fixture_bytes).value != COMPLETE_FIXTURE_SHA256
        or command.fixture_length.value != COMPLETE_FIXTURE_BYTES
        or command.fixture_digest.value != COMPLETE_FIXTURE_SHA256
    ):
        fail_kpi(KpiFailureCode.FIXTURE_BYTES_MISMATCH)
    try:
        value = json.loads(
            fixture_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except KpiFailure:
        raise
    except Exception:
        _invalid()
    root = _document(value, _ROOT_KEYS)
    if (
        root["schema_version"] != "2.0.0"
        or type(root["schema_version"]) is not str
        or root["recording_id"] != "complete"
        or type(root["recording_id"]) is not str
        or root["synthetic"] is not True
    ):
        _invalid()
    period_document = _document(root["period"], _PERIOD_KEYS)
    period = MeasurementPeriod(
        _calendar_date(period_document["start_date"]),
        _calendar_date(period_document["end_date"]),
    )
    program_id = ProgramId(_text(root["program_id"]))
    selected_basis_value = _enum(AttributionBasis, root["selected_attribution_basis"])
    if type(selected_basis_value) is not AttributionBasis:
        _invalid()
    context = CalculationContext(period, program_id, selected_basis_value)
    if context != command.context:
        _invalid()
    observations: list[MetricObservation] = []
    for raw in _array(root["observations"]):
        row = _document(raw, _OBSERVATION_KEYS)
        source = _enum(InputSource, row["source"])
        cohort = _enum(CohortState, row["cohort_state"])
        attribution = _enum(AttributionBasis, row["attribution_basis"])
        if (
            type(source) is not InputSource
            or type(cohort) is not CohortState
            or type(attribution) is not AttributionBasis
        ):
            _invalid()
        observations.append(
            MetricObservation(
                metric_key=_text(row["metric_key"]),
                value=_decimal(row["value"]),
                source=source,
                period=period,
                program_id=program_id,
                verified=_boolean(row["verified"]),
                cohort_state=cohort,
                attribution_basis=attribution,
                attribution_verified=_boolean(row["attribution_verified"]),
            )
        )
    _expected_results(root["expected_results"])
    _expected_learning_results(root["expected_learning_results"])
    frame = KpiInputFrame(tuple(observations))
    if frame.sha256 != command.expected_input_digest:
        _invalid()
    return RecordedKpiInputBatch(
        recording_id="complete",
        fixture_digest=command.fixture_digest,
        fixture_length=command.fixture_length,
        recorded_at=_utc_timestamp(root["recorded_at"]),
        context=context,
        input_frame=frame,
    )


@final
class RecordedKpiInputAdapter:
    """Consume one exact caller-supplied fixture byte sequence once."""

    __slots__ = ("_consumed", "_fixture_bytes", "_lock")

    def __init__(self, fixture_bytes: bytes) -> None:
        if type(fixture_bytes) is not bytes:
            fail_kpi()
        self._fixture_bytes = fixture_bytes
        self._consumed = False
        self._lock = RLock()

    def read(self, command: KpiCalculationCommand) -> RecordedKpiInputBatch:
        if type(command) is not KpiCalculationCommand:
            fail_kpi()
        with self._lock:
            if self._consumed:
                fail_kpi(KpiFailureCode.RECORDED_EXCHANGE_EXHAUSTED)
            self._consumed = True
            fixture_bytes = self._fixture_bytes
            self._fixture_bytes = b""
        return _parse_fixture(command, fixture_bytes)


__all__ = [
    "COMPLETE_FIXTURE_BYTES",
    "COMPLETE_FIXTURE_SHA256",
    "RecordedKpiInputAdapter",
]
