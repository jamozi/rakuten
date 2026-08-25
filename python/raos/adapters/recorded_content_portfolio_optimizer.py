"""One-shot strict adapter for ST-1907 recorded-synthetic portfolio signals."""

from __future__ import annotations

from datetime import date
import json
from threading import RLock
from typing import Final, NoReturn, SupportsIndex, cast, final

from raos.domain.portfolio.content_optimizer import (
    FIXTURE_PROFILE,
    MAX_SIGNALS,
    MAX_SOURCE_BYTES,
    METHOD_VERSION,
    PARSER_VERSION,
    CohortMaturity,
    DependencyReadiness,
    ObservationPeriod,
    PortfolioDecisionDependency,
    PortfolioOptimizationSignal,
    PortfolioOptimizerCommand,
    PortfolioOptimizerFailure,
    PortfolioOptimizerFailureCode,
    ProposalAction,
    ProposalBasis,
    RecordedPortfolioOptimizationBatch,
    Sha256Digest,
    SignalVerification,
    canonical_json_bytes,
    digest_bytes,
    fail_portfolio_optimizer,
)


_REDACTED: Final = "<redacted-recorded-content-portfolio-optimizer>"
_ROOT_KEYS: Final = frozenset({"document", "signals"})
_DOCUMENT_KEYS: Final = frozenset(
    {
        "dependency",
        "fixture_profile",
        "measurement_contract_sha256",
        "method_version",
        "parser_version",
        "period",
        "program",
        "recording_id",
        "signal_policy_sha256",
        "synthetic",
    }
)
_DEPENDENCY_KEYS: Final = frozenset(
    {
        "acceptance_criteria_satisfied",
        "actual_observation_count",
        "human_decision_present",
        "local_integration_complete",
        "pack_sha256",
        "readiness",
        "source_authorized",
        "source_outcome",
        "source_overall",
        "story_id",
    }
)
_PERIOD_KEYS: Final = frozenset({"duration_days", "end_exclusive_date", "start_date"})
_SIGNAL_KEYS: Final = frozenset(
    {
        "action",
        "article_ids",
        "basis",
        "cohort",
        "denominator_count",
        "finance_signal_present",
        "period",
        "personal_data_present",
        "program",
        "publication_mutation_requested",
        "recommendation_order_change_requested",
        "signal_id",
        "signal_policy_sha256",
        "source_sha256",
        "verification",
    }
)


def _invalid() -> NoReturn:
    fail_portfolio_optimizer(PortfolioOptimizerFailureCode.SOURCE_DOCUMENT_INVALID)


def _pairs(values: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in values:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _invalid()
    untyped = cast(dict[object, object], value)
    if any(type(key) is not str for key in untyped) or frozenset(untyped) != keys:
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


def _optional_string(value: object, maximum: int = 160) -> str | None:
    return None if value is None else _string(value, maximum)


def _boolean(value: object) -> bool:
    if type(value) is not bool:
        _invalid()
    return value


def _integer(value: object, maximum: int = 10_000_000) -> int:
    if type(value) is not int or not 0 <= value <= maximum:
        _invalid()
    return value


def _optional_integer(value: object) -> int | None:
    return None if value is None else _integer(value, (1 << 63) - 1)


def _sha(value: object) -> Sha256Digest:
    try:
        return Sha256Digest(_string(value, 64))
    except PortfolioOptimizerFailure:
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


def _period(value: object) -> ObservationPeriod:
    row = _mapping(value, _PERIOD_KEYS)
    if _integer(row["duration_days"], 14) != 14:
        _invalid()
    try:
        return ObservationPeriod(
            start_date=_date(row["start_date"]),
            end_exclusive_date=_date(row["end_exclusive_date"]),
        )
    except PortfolioOptimizerFailure:
        raise
    except Exception:
        _invalid()


def _dependency(value: object) -> PortfolioDecisionDependency:
    row = _mapping(value, _DEPENDENCY_KEYS)
    try:
        return PortfolioDecisionDependency(
            story_id=_string(row["story_id"], 16),
            pack_sha256=_sha(row["pack_sha256"]),
            readiness=DependencyReadiness(_string(row["readiness"], 64)),
            acceptance_criteria_satisfied=_boolean(
                row["acceptance_criteria_satisfied"]
            ),
            actual_observation_count=_integer(row["actual_observation_count"]),
            human_decision_present=_boolean(row["human_decision_present"]),
            local_integration_complete=_boolean(row["local_integration_complete"]),
            source_authorized=_boolean(row["source_authorized"]),
            source_overall=_optional_string(row["source_overall"], 64),
            source_outcome=_optional_string(row["source_outcome"], 64),
        )
    except PortfolioOptimizerFailure:
        raise
    except ValueError:
        _invalid()


def _article_ids(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        _invalid()
    values = cast(list[object], value)
    if not values or len(values) > 20:
        _invalid()
    return tuple(_string(article_id, 160) for article_id in values)


def _signal(value: object) -> PortfolioOptimizationSignal:
    row = _mapping(value, _SIGNAL_KEYS)
    try:
        return PortfolioOptimizationSignal(
            signal_id=_string(row["signal_id"], 96),
            action=ProposalAction(_string(row["action"], 32)),
            basis=ProposalBasis(_string(row["basis"], 64)),
            article_ids=_article_ids(row["article_ids"]),
            source_sha256=_sha(row["source_sha256"]),
            signal_policy_sha256=_sha(row["signal_policy_sha256"]),
            program=_string(row["program"], 64),
            period=_period(row["period"]),
            verification=SignalVerification(_string(row["verification"], 32)),
            cohort=CohortMaturity(_string(row["cohort"], 32)),
            denominator_count=_optional_integer(row["denominator_count"]),
            finance_signal_present=_boolean(row["finance_signal_present"]),
            personal_data_present=_boolean(row["personal_data_present"]),
            recommendation_order_change_requested=_boolean(
                row["recommendation_order_change_requested"]
            ),
            publication_mutation_requested=_boolean(
                row["publication_mutation_requested"]
            ),
        )
    except PortfolioOptimizerFailure:
        raise
    except ValueError:
        _invalid()


def _parse(
    payload: bytes, command: PortfolioOptimizerCommand
) -> RecordedPortfolioOptimizationBatch:
    if (
        type(payload) is not bytes
        or not payload
        or len(payload) > MAX_SOURCE_BYTES
        or len(payload) != command.source_bytes
        or digest_bytes(payload) != command.source_sha256
        or not payload.endswith(b"\n")
    ):
        fail_portfolio_optimizer(PortfolioOptimizerFailureCode.SOURCE_BYTES_MISMATCH)
    try:
        parsed = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except PortfolioOptimizerFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(parsed, _ROOT_KEYS)
    if canonical_json_bytes(root) + b"\n" != payload:
        _invalid()
    document = _mapping(root["document"], _DOCUMENT_KEYS)
    period = _period(document["period"])
    dependency = _dependency(document["dependency"])
    if (
        document["synthetic"] is not True
        or document["fixture_profile"] != FIXTURE_PROFILE
        or document["method_version"] != METHOD_VERSION
        or document["parser_version"] != PARSER_VERSION
        or document["recording_id"] != command.recording_id
        or document["program"] != command.program
        or period != command.period
        or document["measurement_contract_sha256"]
        != command.measurement_contract_sha256.value
        or document["signal_policy_sha256"] != command.signal_policy_sha256.value
    ):
        fail_portfolio_optimizer(PortfolioOptimizerFailureCode.CONTRACT_DRIFT)
    raw_signals = root["signals"]
    if type(raw_signals) is not list:
        _invalid()
    signal_values = cast(list[object], raw_signals)
    if len(signal_values) > MAX_SIGNALS:
        _invalid()
    signals = tuple(_signal(value) for value in signal_values)
    return RecordedPortfolioOptimizationBatch(
        recording_id=command.recording_id,
        command_sha256=command.canonical_sha256,
        source_sha256=command.source_sha256,
        source_bytes=command.source_bytes,
        contract_sha256=command.contract_sha256,
        dependency=dependency,
        measurement_contract_sha256=_sha(document["measurement_contract_sha256"]),
        signal_policy_sha256=_sha(document["signal_policy_sha256"]),
        program=_string(document["program"], 64),
        period=period,
        fixture_profile=FIXTURE_PROFILE,
        parser_version=PARSER_VERSION,
        signals=signals,
    )


@final
class RecordedContentPortfolioOptimizerSource:
    """Consume one immutable caller-supplied recording once."""

    __slots__ = ("_consumed", "_lock", "_payload")

    def __init__(self, payload: bytes) -> None:
        if type(payload) is not bytes or not payload or len(payload) > MAX_SOURCE_BYTES:
            _invalid()
        self._payload = bytes(payload)
        self._consumed = False
        self._lock = RLock()

    def read(
        self, command: PortfolioOptimizerCommand
    ) -> RecordedPortfolioOptimizationBatch:
        if type(command) is not PortfolioOptimizerCommand:
            fail_portfolio_optimizer()
        with self._lock:
            if self._consumed:
                fail_portfolio_optimizer(PortfolioOptimizerFailureCode.SOURCE_EXHAUSTED)
            self._consumed = True
            return _parse(self._payload, command)

    def __repr__(self) -> str:
        return f"RecordedContentPortfolioOptimizerSource({_REDACTED})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded portfolio optimizer sources cannot be serialized")


__all__ = ("RecordedContentPortfolioOptimizerSource",)
