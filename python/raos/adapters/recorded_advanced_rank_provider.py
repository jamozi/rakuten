"""One-shot caller-bytes adapter for the ST-1905 synthetic provider fixture."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
from threading import RLock
from typing import NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.domain.analytics.advanced_rank_provider import (
    ADVANCED_RANK_PROVIDER_ADAPTER_VERSION,
    ADVANCED_RANK_PROVIDER_PARSER_VERSION,
    MAX_PROVIDER_OBSERVATIONS,
    MAX_PROVIDER_SOURCE_BYTES,
    SYNTHETIC_PROVIDER_CODE,
    SYNTHETIC_PROVIDER_PROFILE,
    AdvancedRankProviderCommand,
    AdvancedRankProviderFailure,
    AdvancedRankProviderFailureCode,
    AdvancedRankProviderSourceKind,
    RecordedAdvancedRankBatch,
    RecordedAdvancedRankObservation,
    canonical_json_bytes,
    fail_advanced_rank_provider,
)
from raos.domain.analytics.keyword_rank import (
    KeywordRankDevice,
    KeywordRankFailure,
    KeywordRankMetricType,
    KeywordRankObservation,
    Sha256Digest,
)


_REDACTED = "<redacted-recorded-advanced-rank-provider-source>"
_ROOT_KEYS = frozenset({"document", "observations"})
_DOCUMENT_KEYS = frozenset(
    {
        "adapter_version",
        "fixture_profile",
        "parser_version",
        "recording_id",
        "synthetic",
    }
)
_OBSERVATION_KEYS = frozenset(
    {
        "confidence",
        "device",
        "keyword_id",
        "locale",
        "metric_type",
        "observation_date",
        "provider_code",
        "provider_observation_id",
        "unit",
        "value",
    }
)


def _invalid() -> NoReturn:
    fail_advanced_rank_provider(AdvancedRankProviderFailureCode.SOURCE_DOCUMENT_INVALID)


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_float(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    mapping = cast(dict[object, object], value)
    if frozenset(mapping) != keys:
        _invalid()
    return cast(dict[str, object], mapping)


def _string(value: object, maximum: int = 160) -> str:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in "\x00\r\n")
    ):
        _invalid()
    return value


def _nullable_unit(value: object) -> str | None:
    if value is None:
        return None
    return _string(value, 32)


def _decimal(value: object) -> Decimal:
    text = _string(value, 48)
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        _invalid()
    if (
        not parsed.is_finite()
        or str(parsed) != text
        or len(parsed.as_tuple().digits) > 38
    ):
        _invalid()
    return parsed


def _date(value: object) -> date:
    text = _string(value, 10)
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        _invalid()
    if parsed.isoformat() != text:
        _invalid()
    return parsed


def _uuid(value: object) -> UUID:
    text = _string(value, 36)
    try:
        parsed = UUID(text)
    except ValueError:
        _invalid()
    if parsed.int == 0 or str(parsed) != text:
        _invalid()
    return parsed


def _enum[T: KeywordRankDevice | KeywordRankMetricType](
    enum_type: type[T], value: object
) -> T:
    text = _string(value, 32)
    try:
        return enum_type(text)
    except ValueError:
        _invalid()


def _parse(
    payload: bytes,
    command: AdvancedRankProviderCommand,
) -> RecordedAdvancedRankBatch:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_PROVIDER_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or Sha256Digest.of(payload) != command.source_sha256
        or not payload.endswith(b"\n")
    ):
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.SOURCE_BYTES_MISMATCH
        )
    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except AdvancedRankProviderFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != payload:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    if (
        document["synthetic"] is not True
        or document["fixture_profile"] != SYNTHETIC_PROVIDER_PROFILE
        or document["parser_version"] != ADVANCED_RANK_PROVIDER_PARSER_VERSION
        or document["adapter_version"] != ADVANCED_RANK_PROVIDER_ADAPTER_VERSION
        or document["recording_id"] != command.recording_id
    ):
        fail_advanced_rank_provider(
            AdvancedRankProviderFailureCode.DEPENDENCY_CONTRACT_DRIFT
        )
    raw_observations = root["observations"]
    if type(raw_observations) is not list:
        _invalid()
    observation_values = cast(list[object], raw_observations)
    if not 1 <= len(observation_values) <= MAX_PROVIDER_OBSERVATIONS:
        _invalid()
    observations: list[RecordedAdvancedRankObservation] = []
    for raw in observation_values:
        item = _mapping(raw, _OBSERVATION_KEYS)
        if item["provider_code"] != SYNTHETIC_PROVIDER_CODE:
            fail_advanced_rank_provider(
                AdvancedRankProviderFailureCode.DEPENDENCY_CONTRACT_DRIFT
            )
        try:
            canonical = KeywordRankObservation(
                keyword_id=_uuid(item["keyword_id"]),
                locale=_string(item["locale"], 16),
                device=_enum(KeywordRankDevice, item["device"]),
                observation_date=_date(item["observation_date"]),
                metric_type=_enum(KeywordRankMetricType, item["metric_type"]),
                value=_decimal(item["value"]),
                unit=_nullable_unit(item["unit"]),
                provider_code=SYNTHETIC_PROVIDER_CODE,
                confidence=_decimal(item["confidence"]),
                raw_row_sha256=Sha256Digest.of(canonical_json_bytes(item)),
            )
            observations.append(
                RecordedAdvancedRankObservation(
                    provider_observation_id=_string(
                        item["provider_observation_id"], 160
                    ),
                    observation=canonical,
                )
            )
        except AdvancedRankProviderFailure:
            raise
        except KeywordRankFailure:
            _invalid()
        except Exception:
            _invalid()
    return RecordedAdvancedRankBatch(
        recording_id=command.recording_id,
        site_id=command.site_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        source_kind=AdvancedRankProviderSourceKind.RECORDED_SYNTHETIC_PROVIDER_RESPONSE,
        fixture_profile=SYNTHETIC_PROVIDER_PROFILE,
        parser_version=ADVANCED_RANK_PROVIDER_PARSER_VERSION,
        adapter_version=ADVANCED_RANK_PROVIDER_ADAPTER_VERSION,
        observations=tuple(observations),
    )


@final
class RecordedAdvancedRankProviderSource:
    """Consume one immutable caller-supplied synthetic recording exactly once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if (
            type(payload) is not bytes
            or not payload
            or len(payload) > MAX_PROVIDER_SOURCE_BYTES
        ):
            _invalid()
        self._payload = bytes(payload)
        self._consumed = False
        self._lock = RLock()

    def read(self, command: AdvancedRankProviderCommand) -> RecordedAdvancedRankBatch:
        if type(command) is not AdvancedRankProviderCommand:
            fail_advanced_rank_provider()
        with self._lock:
            if self._consumed:
                fail_advanced_rank_provider(
                    AdvancedRankProviderFailureCode.SOURCE_EXHAUSTED
                )
            self._consumed = True
            return _parse(self._payload, command)

    def __repr__(self) -> str:
        return f"RecordedAdvancedRankProviderSource({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded advanced rank provider sources cannot be serialized")


__all__ = ["RecordedAdvancedRankProviderSource"]
