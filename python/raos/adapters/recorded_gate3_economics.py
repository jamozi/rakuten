"""Strict caller-bytes adapter for the ST-1804 synthetic GATE-3 vector."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
import json
from threading import Lock
from typing import NoReturn, cast, final

from raos.domain.analytics.gate3_economics import (
    FIXTURE_SCHEMA,
    MONTH_METRICS,
    CohortMaturity,
    FixtureByteLength,
    Gate3Command,
    Gate3Failure,
    Gate3FailureCode,
    MetricValue,
    MonthObservation,
    MonthPeriod,
    RecordedEconomicsBatch,
    Sha256Digest,
    ValueState,
    canonical_input_digest,
    expected_metric_source,
    fail_gate3,
)


_MAX_BYTES = 1024 * 1024
_TOP_KEYS = {
    "actual_observation",
    "append_only",
    "context",
    "contract_sha256",
    "entries",
    "immutable",
    "input_sha256",
    "recorded_at",
    "recording_id",
    "schema",
    "synthetic",
}
_CONTEXT_KEYS = {"program"}
_ENTRY_KEYS = {
    "entry_sha256",
    "payload",
    "previous_entry_sha256",
    "sequence",
    "type",
}
_PAYLOAD_KEYS = {
    "attribution_verified",
    "cohort_maturity",
    "cost_basis_verified",
    "metrics",
    "period",
    "program",
    "source_bundle_sha256",
}
_PERIOD_KEYS = {"end_exclusive_date", "start_date"}
_METRIC_KEYS = {"state", "value"}
_PROHIBITED_KEYS = {
    "article_body",
    "cookie",
    "email",
    "full_user_agent",
    "name",
    "phone",
    "raw_ip",
    "raw_provider_row",
    "raw_search_query",
    "secret",
    "source_packet_text",
    "token",
}


def _fail() -> NoReturn:
    fail_gate3(Gate3FailureCode.FIXTURE_DOCUMENT_INVALID)


def _pairs(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            _fail()
        result[key] = value
    return result


def _mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw) or set(raw) != keys:
        _fail()
    if any(cast(str, key).lower() in _PROHIBITED_KEYS for key in raw):
        _fail()
    return cast(Mapping[str, object], value)


def _string(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        _fail()
    return value


def _integer(value: object) -> int:
    if type(value) is not int:
        _fail()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _fail()
    return value


def _digest(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value, maximum=64))
    except Gate3Failure:
        _fail()


def _date(value: object) -> date:
    rendered = _string(value, maximum=10)
    try:
        parsed = date.fromisoformat(rendered)
    except ValueError:
        _fail()
    if parsed.isoformat() != rendered:
        _fail()
    return parsed


def _period(value: object) -> MonthPeriod:
    source = _mapping(value, _PERIOD_KEYS)
    try:
        return MonthPeriod(
            start_date=_date(source["start_date"]),
            end_exclusive_date=_date(source["end_exclusive_date"]),
        )
    except Gate3Failure:
        _fail()


def _timestamp(value: object) -> str:
    rendered = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        _fail()
    return rendered


def _metric(
    value: object,
    key: str,
    source_bundle_sha256: Sha256Digest,
) -> MetricValue:
    source = _mapping(value, _METRIC_KEYS)
    try:
        state = ValueState(_string(source["state"]))
    except ValueError:
        _fail()
    raw_value = source["value"]
    parsed_value = None if raw_value is None else _integer(raw_value)
    try:
        return MetricValue(
            metric_key=key,
            state=state,
            value=parsed_value,
            source=expected_metric_source(key),
            source_sha256=(
                None
                if state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}
                else source_bundle_sha256
            ),
        )
    except Gate3Failure:
        _fail()


def _month(value: object, expected_sequence: int) -> MonthObservation:
    source = _mapping(value, _ENTRY_KEYS)
    sequence = _integer(source["sequence"])
    if sequence != expected_sequence or _string(source["type"]) != "MONTH":
        _fail()
    payload = _mapping(source["payload"], _PAYLOAD_KEYS)
    metrics_source = _mapping(payload["metrics"], set(MONTH_METRICS))
    source_bundle_sha256 = _digest(payload["source_bundle_sha256"])
    try:
        return MonthObservation(
            sequence=sequence,
            previous_entry_sha256=_digest(source["previous_entry_sha256"]),
            entry_sha256=_digest(source["entry_sha256"]),
            period=_period(payload["period"]),
            program_id=_string(payload["program"]),
            cohort_maturity=CohortMaturity(_string(payload["cohort_maturity"])),
            attribution_verified=_boolean(payload["attribution_verified"]),
            cost_basis_verified=_boolean(payload["cost_basis_verified"]),
            metrics=tuple(
                _metric(metrics_source[key], key, source_bundle_sha256)
                for key in MONTH_METRICS
            ),
        )
    except Gate3Failure, ValueError:
        _fail()


def parse_recorded_gate3_fixture(
    fixture_bytes: bytes,
    command: Gate3Command,
) -> RecordedEconomicsBatch:
    if type(fixture_bytes) is not bytes or type(command) is not Gate3Command:
        fail_gate3()
    if (
        not 0 < len(fixture_bytes) <= _MAX_BYTES
        or Sha256Digest.of(fixture_bytes) != command.fixture_digest
        or FixtureByteLength(len(fixture_bytes)) != command.fixture_length
    ):
        fail_gate3(Gate3FailureCode.FIXTURE_BYTES_MISMATCH)
    try:
        decoded = fixture_bytes.decode("utf-8", errors="strict")
        document = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail(),
            parse_float=lambda _: _fail(),
        )
    except Gate3Failure, UnicodeDecodeError, ValueError, RecursionError:
        _fail()
    source = _mapping(document, _TOP_KEYS)
    if (
        _string(source["schema"]) != FIXTURE_SCHEMA
        or _string(source["recording_id"]) != command.recording_id
        or _timestamp(source["recorded_at"]) != "2026-04-01T00:00:00Z"
        or _boolean(source["synthetic"]) is not True
        or _boolean(source["actual_observation"]) is not False
        or _boolean(source["append_only"]) is not True
        or _boolean(source["immutable"]) is not True
        or _digest(source["contract_sha256"]) != command.contract_digest
    ):
        _fail()
    context = _mapping(source["context"], _CONTEXT_KEYS)
    program_id = _string(context["program"])
    entries_value = source["entries"]
    if type(entries_value) is not list:
        _fail()
    entries = cast(list[object], entries_value)
    if len(entries) != 3:
        _fail()
    months = tuple(_month(entries[index], index + 1) for index in range(3))
    input_digest = canonical_input_digest(months)
    if (
        _digest(source["input_sha256"]) != input_digest
        or input_digest != command.expected_input_digest
        or program_id != command.program_id
    ):
        _fail()
    try:
        return RecordedEconomicsBatch(
            recording_id=command.recording_id,
            recorded_at=cast(str, source["recorded_at"]),
            fixture_digest=command.fixture_digest,
            fixture_length=command.fixture_length,
            contract_digest=command.contract_digest,
            input_digest=input_digest,
            context_program=program_id,
            months=months,
            synthetic=True,
            actual_observation=False,
            append_only=True,
            immutable=True,
        )
    except Gate3Failure:
        _fail()


@final
class RecordedGate3EconomicsAdapter:
    """Consume one exact caller-owned fixture once; no filesystem/provider I/O."""

    __slots__ = ("_fixture", "_lock", "_used")

    def __init__(self, fixture_bytes: bytes) -> None:
        if type(fixture_bytes) is not bytes or not 0 < len(fixture_bytes) <= _MAX_BYTES:
            fail_gate3()
        self._fixture = fixture_bytes
        self._lock = Lock()
        self._used = False

    def read(self, command: Gate3Command) -> RecordedEconomicsBatch:
        with self._lock:
            if self._used:
                fail_gate3(Gate3FailureCode.RECORDED_EXCHANGE_EXHAUSTED)
            self._used = True
        return parse_recorded_gate3_fixture(self._fixture, command)


__all__ = ["RecordedGate3EconomicsAdapter", "parse_recorded_gate3_fixture"]
