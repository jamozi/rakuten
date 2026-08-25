"""Strict caller-bytes adapter for the ST-1803 recorded synthetic fixture."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timezone
import json
from threading import Lock
from typing import NoReturn, cast, final

from raos.domain.analytics.gate2_observation import (
    ARTICLE_METRICS,
    FIXTURE_SCHEMA,
    PROGRAM_METRICS,
    ArticleObservation,
    AttributionBasis,
    CohortMaturity,
    FixtureByteLength,
    MetricValue,
    ObservationCommand,
    ObservationFailure,
    ObservationFailureCode,
    ObservationPeriod,
    ProgramObservation,
    RecordedObservationBatch,
    Sha256Digest,
    ValueState,
    canonical_input_digest,
    expected_metric_source,
    fail_observation,
)


_MAX_BYTES = 4 * 1024 * 1024
_TOP_KEYS = {
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
_CONTEXT_KEYS = {"period", "program"}
_PERIOD_KEYS = {"as_of_date", "elapsed_days", "end_exclusive_date", "start_date"}
_ENTRY_KEYS = {"entry_sha256", "payload", "previous_entry_sha256", "sequence", "type"}
_ARTICLE_PAYLOAD_KEYS = {
    "article_id",
    "attribution_basis",
    "attribution_verified",
    "cohort_maturity",
    "metrics",
    "packet_sha256",
    "period",
    "program",
    "source_bundle_sha256",
    "slot",
    "slug",
}
_PROGRAM_PAYLOAD_KEYS = {"metrics", "period", "program", "source_bundle_sha256"}
_METRIC_KEYS = {"state", "value"}
_PROHIBITED_KEYS = {
    "article_body",
    "email",
    "full_user_agent",
    "name",
    "phone",
    "raw_ip",
    "raw_search_query",
    "secret",
    "source_packet_text",
    "token",
}


def _fail() -> NoReturn:
    fail_observation(ObservationFailureCode.FIXTURE_DOCUMENT_INVALID)


def _pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
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


def _string(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= 256:
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
        return Sha256Digest(_string(value))
    except ObservationFailure:
        _fail()


def _parse_date(value: object) -> date:
    rendered = _string(value)
    try:
        parsed = date.fromisoformat(rendered)
    except ValueError:
        _fail()
    if parsed.isoformat() != rendered:
        _fail()
    return parsed


def _period(value: object) -> ObservationPeriod:
    source = _mapping(value, _PERIOD_KEYS)
    period = ObservationPeriod(
        start_date=_parse_date(source["start_date"]),
        end_exclusive_date=_parse_date(source["end_exclusive_date"]),
        as_of_date=_parse_date(source["as_of_date"]),
    )
    if _integer(source["elapsed_days"]) != period.elapsed_days:
        _fail()
    return period


def _timestamp(value: object) -> str:
    rendered = _string(value)
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
    value: object, expected_key: str, source_bundle_sha256: Sha256Digest
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
            metric_key=expected_key,
            state=state,
            value=parsed_value,
            source=expected_metric_source(expected_key),
            input_sha256=(
                None
                if state in {ValueState.NOT_OBSERVED, ValueState.UNAVAILABLE}
                else source_bundle_sha256
            ),
        )
    except ObservationFailure:
        _fail()


def _metrics(
    value: object,
    expected: tuple[str, ...],
    source_bundle_sha256: Sha256Digest,
) -> tuple[MetricValue, ...]:
    source = _mapping(value, set(expected))
    return tuple(_metric(source[key], key, source_bundle_sha256) for key in expected)


def _entry_common(
    value: object,
) -> tuple[Mapping[str, object], int, str, Sha256Digest, Sha256Digest]:
    source = _mapping(value, _ENTRY_KEYS)
    sequence = _integer(source["sequence"])
    entry_type = _string(source["type"])
    previous = _digest(source["previous_entry_sha256"])
    entry = _digest(source["entry_sha256"])
    return source, sequence, entry_type, previous, entry


def _article(value: object, expected_sequence: int) -> ArticleObservation:
    source, sequence, entry_type, previous, entry = _entry_common(value)
    if sequence != expected_sequence or entry_type != "ARTICLE":
        _fail()
    payload = _mapping(source["payload"], _ARTICLE_PAYLOAD_KEYS)
    source_bundle_sha256 = _digest(payload["source_bundle_sha256"])
    try:
        return ArticleObservation(
            sequence=sequence,
            previous_entry_sha256=previous,
            entry_sha256=entry,
            slot=_integer(payload["slot"]),
            article_id=_string(payload["article_id"]),
            slug=_string(payload["slug"]),
            packet_sha256=_digest(payload["packet_sha256"]),
            period=_period(payload["period"]),
            program_id=_string(payload["program"]),
            cohort_maturity=CohortMaturity(_string(payload["cohort_maturity"])),
            attribution_basis=AttributionBasis(_string(payload["attribution_basis"])),
            attribution_verified=_boolean(payload["attribution_verified"]),
            metrics=_metrics(payload["metrics"], ARTICLE_METRICS, source_bundle_sha256),
        )
    except ObservationFailure, ValueError:
        _fail()


def _program(value: object) -> ProgramObservation:
    source, sequence, entry_type, previous, entry = _entry_common(value)
    if sequence != 6 or entry_type != "PROGRAM":
        _fail()
    payload = _mapping(source["payload"], _PROGRAM_PAYLOAD_KEYS)
    source_bundle_sha256 = _digest(payload["source_bundle_sha256"])
    try:
        return ProgramObservation(
            sequence=sequence,
            previous_entry_sha256=previous,
            entry_sha256=entry,
            period=_period(payload["period"]),
            program_id=_string(payload["program"]),
            metrics=_metrics(payload["metrics"], PROGRAM_METRICS, source_bundle_sha256),
        )
    except ObservationFailure:
        _fail()


def parse_recorded_fixture(
    fixture_bytes: bytes, command: ObservationCommand
) -> RecordedObservationBatch:
    if type(fixture_bytes) is not bytes or type(command) is not ObservationCommand:
        fail_observation()
    if (
        not 0 < len(fixture_bytes) <= _MAX_BYTES
        or Sha256Digest.of(fixture_bytes) != command.fixture_digest
        or FixtureByteLength(len(fixture_bytes)) != command.fixture_length
    ):
        fail_observation(ObservationFailureCode.FIXTURE_BYTES_MISMATCH)
    try:
        decoded = fixture_bytes.decode("utf-8", errors="strict")
        document = json.loads(
            decoded,
            object_pairs_hook=_pairs,
            parse_constant=lambda _: _fail(),
            parse_float=lambda _: _fail(),
        )
    except ObservationFailure, UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        _fail()
    source = _mapping(document, _TOP_KEYS)
    if (
        _string(source["schema"]) != FIXTURE_SCHEMA
        or _string(source["recording_id"]) != command.recording_id
        or _timestamp(source["recorded_at"]) != "2026-04-01T00:00:00Z"
        or _boolean(source["synthetic"]) is not True
        or _boolean(source["append_only"]) is not True
        or _boolean(source["immutable"]) is not True
        or _digest(source["contract_sha256"]) != command.contract_digest
    ):
        _fail()
    context = _mapping(source["context"], _CONTEXT_KEYS)
    period = _period(context["period"])
    program_id = _string(context["program"])
    entries_value = source["entries"]
    if type(entries_value) is not list:
        _fail()
    entries = cast(list[object], entries_value)
    if len(entries) != 6:
        _fail()
    articles = tuple(_article(entries[index], index + 1) for index in range(5))
    program = _program(entries[5])
    input_digest = canonical_input_digest(articles, program)
    if (
        _digest(source["input_sha256"]) != input_digest
        or input_digest != command.expected_input_digest
        or period != command.period
        or program_id != command.program_id
    ):
        _fail()
    try:
        return RecordedObservationBatch(
            recording_id=command.recording_id,
            recorded_at=cast(str, source["recorded_at"]),
            fixture_digest=command.fixture_digest,
            fixture_length=command.fixture_length,
            contract_digest=command.contract_digest,
            input_digest=input_digest,
            context_period=period,
            program_id=program_id,
            articles=articles,
            program_observation=program,
            synthetic=True,
            append_only=True,
            immutable=True,
        )
    except ObservationFailure:
        _fail()


@final
class RecordedGate2ObservationAdapter:
    """Consume exactly one caller-supplied fixture; replay is rejected."""

    __slots__ = ("_fixture", "_lock", "_used")

    def __init__(self, fixture_bytes: bytes) -> None:
        if type(fixture_bytes) is not bytes or not 0 < len(fixture_bytes) <= _MAX_BYTES:
            fail_observation()
        self._fixture = fixture_bytes
        self._lock = Lock()
        self._used = False

    def read(self, command: ObservationCommand) -> RecordedObservationBatch:
        with self._lock:
            if self._used:
                fail_observation(ObservationFailureCode.RECORDED_EXCHANGE_EXHAUSTED)
            self._used = True
        return parse_recorded_fixture(self._fixture, command)


__all__ = ["RecordedGate2ObservationAdapter", "parse_recorded_fixture"]
