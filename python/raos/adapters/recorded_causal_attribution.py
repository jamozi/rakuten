"""One-shot caller-bytes adapter for the ST-1906 synthetic aggregate fixture."""

from __future__ import annotations

from datetime import date
import json
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final

from raos.domain.analytics.causal_attribution import (
    CAUSAL_METHOD_VERSION,
    CAUSAL_PARSER_VERSION,
    MAX_SOURCE_BYTES,
    OUTCOME_CODE,
    SYNTHETIC_CAUSAL_PROFILE,
    AggregateExperimentCell,
    CausalAttributionCommand,
    CausalAttributionFailure,
    CausalAttributionFailureCode,
    PrivacyReviewEvidence,
    PrivacyReviewStatus,
    RecordedCausalAttributionBatch,
    canonical_json_bytes,
    digest_bytes,
    fail_causal_attribution,
)
from raos.domain.finance.attribution import (
    CohortMaturity,
    MeasurementPeriod,
    VerificationState,
)
from raos.domain.ops.object_intake import Sha256Digest


_REDACTED: Final = "<redacted-recorded-causal-source>"
_ROOT_KEYS = frozenset({"cells", "document"})
_DOCUMENT_KEYS = frozenset(
    {
        "contract",
        "experiment_id",
        "fixture_profile",
        "method_version",
        "outcome_code",
        "parser_version",
        "period",
        "preregistration_sha256",
        "privacy_review",
        "program",
        "recording_id",
        "synthetic",
    }
)
_PRIVACY_KEYS = frozenset(
    {
        "aggregate_only",
        "free_text",
        "full_user_agent",
        "personal_data",
        "persistent_identifier",
        "raw_ip",
        "review_sha256",
        "scope",
        "status",
        "synthetic",
        "tracking_activation",
    }
)
_PERIOD_KEYS = frozenset({"duration_days", "end_exclusive_date", "start_date"})
_CELL_KEYS = frozenset(
    {
        "article_id",
        "assignment_sha256",
        "assignment_verified",
        "cohort",
        "control_exposures",
        "control_outcomes",
        "packet_sha256",
        "period",
        "program",
        "slot",
        "source_sha256",
        "treatment_exposures",
        "treatment_outcomes",
        "verification",
    }
)


def _invalid() -> NoReturn:
    fail_causal_attribution(CausalAttributionFailureCode.SOURCE_DOCUMENT_INVALID)


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
    if type(value) is not dict or frozenset(value) != keys:
        _invalid()
    return cast(dict[str, object], value)


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


def _integer(value: object, maximum: int = 100_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _invalid()
    return value


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _sha(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value, 64))
    except CausalAttributionFailure:
        raise
    except Exception:
        _invalid()


def _date(value: object) -> date:
    raw = _string(value, 10)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _invalid()
    if parsed.isoformat() != raw:
        _invalid()
    return parsed


def _period(value: object) -> MeasurementPeriod:
    row = _mapping(value, _PERIOD_KEYS)
    if _integer(row["duration_days"], 14) != 14:
        _invalid()
    try:
        return MeasurementPeriod(
            start_date=_date(row["start_date"]),
            end_exclusive_date=_date(row["end_exclusive_date"]),
        )
    except CausalAttributionFailure:
        raise
    except Exception:
        _invalid()


def _enum(enum_type: type[PrivacyReviewStatus], value: object) -> PrivacyReviewStatus:
    try:
        return enum_type(_string(value))
    except ValueError:
        _invalid()


def _privacy(value: object) -> PrivacyReviewEvidence:
    row = _mapping(value, _PRIVACY_KEYS)
    review_value = row["review_sha256"]
    review_sha256 = None if review_value is None else _sha(review_value)
    try:
        return PrivacyReviewEvidence(
            status=_enum(PrivacyReviewStatus, row["status"]),
            review_sha256=review_sha256,
            scope=_string(row["scope"]),
            synthetic=_boolean(row["synthetic"]),
            aggregate_only=_boolean(row["aggregate_only"]),
            personal_data=_boolean(row["personal_data"]),
            persistent_identifier=_boolean(row["persistent_identifier"]),
            raw_ip=_boolean(row["raw_ip"]),
            full_user_agent=_boolean(row["full_user_agent"]),
            free_text=_boolean(row["free_text"]),
            tracking_activation=_boolean(row["tracking_activation"]),
        )
    except CausalAttributionFailure:
        raise
    except Exception:
        _invalid()


def _verification(value: object) -> VerificationState:
    try:
        return VerificationState(_string(value))
    except ValueError:
        _invalid()


def _cohort(value: object) -> CohortMaturity:
    try:
        return CohortMaturity(_string(value))
    except ValueError:
        _invalid()


def _cell(value: object) -> AggregateExperimentCell:
    row = _mapping(value, _CELL_KEYS)
    try:
        return AggregateExperimentCell(
            slot=_integer(row["slot"], 5),
            article_id=_string(row["article_id"]),
            packet_sha256=_sha(row["packet_sha256"]),
            program=_string(row["program"], 64),
            period=_period(row["period"]),
            verification=_verification(row["verification"]),
            cohort=_cohort(row["cohort"]),
            assignment_verified=_boolean(row["assignment_verified"]),
            assignment_sha256=_sha(row["assignment_sha256"]),
            source_sha256=_sha(row["source_sha256"]),
            control_exposures=_integer(row["control_exposures"]),
            control_outcomes=_integer(row["control_outcomes"]),
            treatment_exposures=_integer(row["treatment_exposures"]),
            treatment_outcomes=_integer(row["treatment_outcomes"]),
        )
    except CausalAttributionFailure:
        raise
    except Exception:
        _invalid()


def _parse(
    payload: bytes, command: CausalAttributionCommand
) -> RecordedCausalAttributionBatch:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or digest_bytes(payload) != command.source_sha256
        or not payload.endswith(b"\n")
    ):
        fail_causal_attribution(CausalAttributionFailureCode.SOURCE_BYTES_MISMATCH)
    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_float,
        )
    except CausalAttributionFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != payload:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    privacy_review = _privacy(document["privacy_review"])
    period = _period(document["period"])
    if (
        document["synthetic"] is not True
        or document["fixture_profile"] != SYNTHETIC_CAUSAL_PROFILE
        or document["parser_version"] != CAUSAL_PARSER_VERSION
        or document["method_version"] != CAUSAL_METHOD_VERSION
        or document["outcome_code"] != OUTCOME_CODE
        or document["recording_id"] != command.recording_id
        or document["experiment_id"] != command.experiment_id
        or document["program"] != command.program
        or period != command.period
        or document["preregistration_sha256"] != command.preregistration_sha256.value
        or privacy_review != command.privacy_review
        or document["contract"] != command.contract.payload()
    ):
        fail_causal_attribution(CausalAttributionFailureCode.DEPENDENCY_CONTRACT_DRIFT)
    raw_cells = root["cells"]
    if type(raw_cells) is not list or len(raw_cells) > 5:
        _invalid()
    cells = tuple(_cell(value) for value in raw_cells)
    return RecordedCausalAttributionBatch(
        recording_id=command.recording_id,
        experiment_id=command.experiment_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        contract_sha256=command.contract.sha256,
        program=_string(document["program"], 64),
        period=period,
        privacy_review=privacy_review,
        preregistration_sha256=_sha(document["preregistration_sha256"]),
        fixture_profile=SYNTHETIC_CAUSAL_PROFILE,
        parser_version=CAUSAL_PARSER_VERSION,
        outcome_code=OUTCOME_CODE,
        cells=cells,
    )


@final
class RecordedCausalAttributionSource:
    """Consume one immutable caller-supplied synthetic recording once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if type(payload) is not bytes or not payload or len(payload) > MAX_SOURCE_BYTES:
            _invalid()
        self._payload = bytes(payload)
        self._consumed = False
        self._lock = RLock()

    def read(self, command: CausalAttributionCommand) -> RecordedCausalAttributionBatch:
        if type(command) is not CausalAttributionCommand:
            fail_causal_attribution()
        with self._lock:
            if self._consumed:
                fail_causal_attribution(CausalAttributionFailureCode.SOURCE_EXHAUSTED)
            self._consumed = True
            return _parse(self._payload, command)

    def __repr__(self) -> str:
        return f"RecordedCausalAttributionSource({_REDACTED})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded causal sources cannot be serialized")


__all__ = ("RecordedCausalAttributionSource",)
