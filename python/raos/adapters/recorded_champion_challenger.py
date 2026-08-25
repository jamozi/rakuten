"""One-shot caller-bytes adapter for the ST-1902 synthetic shadow fixture."""

from __future__ import annotations

import json
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final

from raos.domain.ai.champion_challenger import (
    EXPECTED_ST0708_OUTCOME,
    MAX_SHADOW_OBSERVATIONS,
    MAX_SHADOW_SOURCE_BYTES,
    SHADOW_PARSER_VERSION,
    SYNTHETIC_SHADOW_PROFILE,
    RecordedShadowBatch,
    RecordedShadowObservation,
    Sha256Digest,
    ShadowRoutingCommand,
    ShadowRoutingFailure,
    ShadowRoutingFailureCode,
    canonical_json_bytes,
    fail_shadow_routing,
)


TRUSTED_ROUTE_CATALOG_SHA256: Final = (
    "dc76ed6d2586eec9bf18b8ac2e95eb76971179fe87fa1ee07b1ba8702f8faa96"
)
TRUSTED_ST0708_REPORT_SHA256: Final = (
    "65ca1c03208c2be6ab34caa449d5f7bc5f28c760c60d20b3af0f066f338c6635"
)
_REDACTED: Final = "<redacted-recorded-champion-challenger-source>"
_ROOT_KEYS = frozenset({"document", "observations"})
_DOCUMENT_KEYS = frozenset(
    {
        "critical_effective_canary_max_percent",
        "fixture_profile",
        "parser_version",
        "recording_id",
        "route_catalog_canary_max_percent",
        "route_catalog_sha256",
        "st0708_report_outcome",
        "st0708_report_sha256",
        "synthetic",
    }
)
_OBSERVATION_KEYS = frozenset(
    {
        "assignment_sha256",
        "case_id",
        "challenger_output_sha256",
        "challenger_schema_valid",
        "challenger_score_micros",
        "challenger_zero_tolerance_failures",
        "champion_output_sha256",
        "champion_schema_valid",
        "champion_score_micros",
        "champion_zero_tolerance_failures",
        "human_label_available",
    }
)


def _invalid() -> NoReturn:
    fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_DOCUMENT_INVALID)


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
    candidate = cast(dict[object, object], value)
    if frozenset(candidate) != keys:
        _invalid()
    return cast(dict[str, object], candidate)


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


def _integer(value: object, maximum: int = 1_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _parse(payload: bytes, command: ShadowRoutingCommand) -> RecordedShadowBatch:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_SHADOW_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or Sha256Digest.of(payload) != command.source_sha256
        or not payload.endswith(b"\n")
    ):
        fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_BYTES_MISMATCH)
    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except ShadowRoutingFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != payload:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    if (
        document["synthetic"] is not True
        or document["fixture_profile"] != SYNTHETIC_SHADOW_PROFILE
        or document["parser_version"] != SHADOW_PARSER_VERSION
        or document["recording_id"] != command.recording_id
        or document["route_catalog_sha256"] != TRUSTED_ROUTE_CATALOG_SHA256
        or document["st0708_report_sha256"] != TRUSTED_ST0708_REPORT_SHA256
        or document["st0708_report_outcome"] != EXPECTED_ST0708_OUTCOME
        or document["route_catalog_canary_max_percent"] != 5
        or document["critical_effective_canary_max_percent"] != 1
    ):
        fail_shadow_routing(ShadowRoutingFailureCode.DEPENDENCY_EVIDENCE_DRIFT)
    raw_observations = root["observations"]
    if type(raw_observations) is not list:
        _invalid()
    observation_values = cast(list[object], raw_observations)
    if not 1 <= len(observation_values) <= MAX_SHADOW_OBSERVATIONS:
        _invalid()
    observations = tuple(
        RecordedShadowObservation(
            case_id=_string(item["case_id"]),
            assignment_sha256=Sha256Digest(_string(item["assignment_sha256"], 64)),
            champion_output_sha256=Sha256Digest(
                _string(item["champion_output_sha256"], 64)
            ),
            challenger_output_sha256=Sha256Digest(
                _string(item["challenger_output_sha256"], 64)
            ),
            champion_score_micros=_integer(item["champion_score_micros"]),
            challenger_score_micros=_integer(item["challenger_score_micros"]),
            champion_schema_valid=_boolean(item["champion_schema_valid"]),
            challenger_schema_valid=_boolean(item["challenger_schema_valid"]),
            champion_zero_tolerance_failures=_integer(
                item["champion_zero_tolerance_failures"],
                MAX_SHADOW_OBSERVATIONS,
            ),
            challenger_zero_tolerance_failures=_integer(
                item["challenger_zero_tolerance_failures"],
                MAX_SHADOW_OBSERVATIONS,
            ),
            human_label_available=_boolean(item["human_label_available"]),
        )
        for raw in observation_values
        for item in (_mapping(raw, _OBSERVATION_KEYS),)
    )
    return RecordedShadowBatch(
        recording_id=command.recording_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        fixture_profile=SYNTHETIC_SHADOW_PROFILE,
        parser_version=SHADOW_PARSER_VERSION,
        route_catalog_sha256=Sha256Digest(TRUSTED_ROUTE_CATALOG_SHA256),
        route_catalog_canary_max_percent=5,
        critical_effective_canary_max_percent=1,
        st0708_report_sha256=Sha256Digest(TRUSTED_ST0708_REPORT_SHA256),
        st0708_report_outcome=EXPECTED_ST0708_OUTCOME,
        observations=observations,
    )


@final
class RecordedChampionChallengerSource:
    """Consume one immutable caller-supplied synthetic recording exactly once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if (
            type(payload) is not bytes
            or not payload
            or len(payload) > MAX_SHADOW_SOURCE_BYTES
        ):
            _invalid()
        self._payload = bytes(payload)
        self._consumed = False
        self._lock = RLock()

    def read(self, command: ShadowRoutingCommand) -> RecordedShadowBatch:
        if type(command) is not ShadowRoutingCommand:
            fail_shadow_routing()
        with self._lock:
            if self._consumed:
                fail_shadow_routing(ShadowRoutingFailureCode.SOURCE_EXHAUSTED)
            self._consumed = True
            return _parse(self._payload, command)

    def __repr__(self) -> str:
        return f"RecordedChampionChallengerSource({_REDACTED})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded shadow sources cannot be serialized")


__all__ = [
    "RecordedChampionChallengerSource",
    "TRUSTED_ROUTE_CATALOG_SHA256",
    "TRUSTED_ST0708_REPORT_SHA256",
]
