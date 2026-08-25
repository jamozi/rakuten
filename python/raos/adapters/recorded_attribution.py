"""Strict tracked-fixture adapter for the ST-1303 local attribution seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
from typing import Any, Final, NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.domain.finance.attribution import (
    ARTICLE_METRICS,
    PROFILE,
    ArticleMeasurement,
    AttributionFailure,
    AttributionFailureCode,
    AttributionRunRequest,
    AttributionRunResult,
    CohortMaturity,
    CohortStatus,
    ContractArticle,
    EstimationSignal,
    MeasurementAttributionContract,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    MeasurementVerification,
    ProgramMeasurement,
    ProviderRewardFact,
    VerificationState,
    build_attribution_run,
    fail_attribution,
)
from raos.domain.finance.provider_fact_commit import JpyAmount
from raos.domain.ops.object_intake import Sha256Digest


MAX_FIXTURE_BYTES: Final = 2 * 1024 * 1024
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z", re.ASCII)
_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,127}\Z", re.ASCII)


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1303-fixture>)"

    def __str__(self) -> str:
        return "<redacted-st1303-fixture>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded attribution serialization is forbidden")


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if (
        type(value) is not dict
        or tuple(cast(dict[object, object], value)) != keys
        or any(type(key) is not str for key in cast(dict[object, object], value))
    ):
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


def _sequence(
    value: object, *, minimum: int = 0, maximum: int = 10_000
) -> list[object]:
    if type(value) is not list:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    result = cast(list[object], value)
    if not minimum <= len(result) <= maximum:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return result


def _string(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return value


def _sha(value: object) -> Sha256Digest:
    try:
        rendered = value.value if type(value) is Sha256Digest else value
        return Sha256Digest(_string(rendered, maximum=64))
    except Exception:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)


def _timestamp(value: object) -> datetime:
    rendered = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return parsed


def _date(value: object) -> date:
    rendered = _string(value, maximum=10)
    try:
        parsed = date.fromisoformat(rendered)
    except ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    if parsed.isoformat() != rendered:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return parsed


def _period(value: object) -> MeasurementPeriod:
    source = _mapping(value, ("start_date", "end_exclusive_date", "duration_days"))
    if source["duration_days"] != 14:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return MeasurementPeriod(
        start_date=_date(source["start_date"]),
        end_exclusive_date=_date(source["end_exclusive_date"]),
    )


def _verification(value: object) -> MeasurementVerification:
    source = _mapping(value, ("state", "input_sha256"))
    try:
        state = VerificationState(source["state"])
    except TypeError, ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return MeasurementVerification(
        state=state,
        input_sha256=(
            None if source["input_sha256"] is None else _sha(source["input_sha256"])
        ),
    )


def _cohort(value: object) -> CohortStatus:
    source = _mapping(value, ("state", "input_sha256"))
    try:
        state = CohortMaturity(source["state"])
    except TypeError, ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return CohortStatus(
        state=state,
        input_sha256=(
            None if source["input_sha256"] is None else _sha(source["input_sha256"])
        ),
    )


def _measurement_value(value: object) -> MeasurementValue:
    source = _mapping(value, ("state", "value", "input_sha256"))
    try:
        state = MeasurementValueState(source["state"])
    except TypeError, ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    raw_value = source["value"]
    if raw_value is not None and type(raw_value) is not int:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return MeasurementValue(
        state=state,
        value=raw_value,
        input_sha256=(
            None if source["input_sha256"] is None else _sha(source["input_sha256"])
        ),
    )


def _article(value: object) -> ContractArticle:
    source = _mapping(
        value,
        ("slot", "article_id", "slug", "packet_sha256", "intent_classification"),
    )
    return ContractArticle(
        slot=cast(int, source["slot"]),
        article_id=cast(str, source["article_id"]),
        slug=cast(str, source["slug"]),
        packet_sha256=_sha(source["packet_sha256"]),
        intent_classification=cast(str, source["intent_classification"]),
    )


def _article_measurement(value: object) -> ArticleMeasurement:
    source = _mapping(
        value,
        ("article", "program", "period", "verification", "cohort", "metrics"),
    )
    metric_source = _mapping(source["metrics"], ARTICLE_METRICS)
    return ArticleMeasurement(
        article=_article(source["article"]),
        program=_string(source["program"], maximum=64),
        period=_period(source["period"]),
        verification=_verification(source["verification"]),
        cohort=_cohort(source["cohort"]),
        metrics=tuple(
            (name, _measurement_value(metric_source[name])) for name in ARTICLE_METRICS
        ),
    )


def _program_measurement(value: object) -> ProgramMeasurement:
    source = _mapping(
        value,
        (
            "program",
            "period",
            "verification",
            "cohort",
            "unattributed_confirmed_reward_jpy",
        ),
    )
    return ProgramMeasurement(
        program=_string(source["program"], maximum=64),
        period=_period(source["period"]),
        verification=_verification(source["verification"]),
        cohort=_cohort(source["cohort"]),
        unattributed_confirmed_reward_jpy=_measurement_value(
            source["unattributed_confirmed_reward_jpy"]
        ),
    )


def _amount(value: object) -> JpyAmount:
    rendered = _string(value, maximum=19)
    if _AMOUNT.fullmatch(rendered) is None:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return JpyAmount(Decimal(rendered))


def _provider_fact(value: object) -> ProviderRewardFact:
    source = _mapping(
        value,
        (
            "fact_sha256",
            "program",
            "period",
            "confirmed_reward_jpy",
            "verification",
            "direct_article_id",
            "direct_key_sha256",
            "estimation_signal",
        ),
    )
    try:
        signal = EstimationSignal(source["estimation_signal"])
    except TypeError, ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    direct_article = source["direct_article_id"]
    if direct_article is not None and type(direct_article) is not str:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return ProviderRewardFact(
        fact_sha256=_sha(source["fact_sha256"]),
        program=_string(source["program"], maximum=64),
        period=_period(source["period"]),
        confirmed_reward_jpy=_amount(source["confirmed_reward_jpy"]),
        verification=_verification(source["verification"]),
        direct_article_id=direct_article,
        direct_key_sha256=(
            None
            if source["direct_key_sha256"] is None
            else _sha(source["direct_key_sha256"])
        ),
        estimation_signal=signal,
    )


def _read_fixture(path: Path) -> bytes:
    if not path.is_absolute():
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
        if stat.S_ISLNK(metadata.st_mode):
            fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    try:
        metadata = path.stat()
        payload = path.read_bytes()
    except OSError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not payload
        or len(payload) != metadata.st_size
        or len(payload) > MAX_FIXTURE_BYTES
    ):
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return payload


def _unique_json(payload: bytes) -> Mapping[str, object]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        del value
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)

    def reject_float(value: str) -> NoReturn:
        del value
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)

    try:
        value = json.loads(
            payload,
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except AttributionFailure:
        raise
    except Exception:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    if type(value) is not dict:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAttributionScenario(_Redacted):
    scenario_id: str
    fixture_sha256: Sha256Digest
    request: AttributionRunRequest

    def __post_init__(self) -> None:
        if (
            type(self.scenario_id) is not str
            or _REFERENCE.fullmatch(self.scenario_id) is None
            or type(self.request) is not AttributionRunRequest
        ):
            fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
        object.__setattr__(self, "fixture_sha256", _sha(self.fixture_sha256))


def load_recorded_attribution_fixture(
    path: object,
    *,
    contract: MeasurementAttributionContract,
) -> RecordedAttributionScenario:
    """Load one strict tracked synthetic scenario without retaining raw bytes."""

    if (
        not isinstance(path, Path)
        or type(contract) is not MeasurementAttributionContract
    ):
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    payload = _read_fixture(path)
    root = _mapping(
        _unique_json(payload),
        (
            "schema_version",
            "profile",
            "scenario_id",
            "contract_sha256",
            "request",
            "expected_input_sha256",
        ),
    )
    if (
        root["schema_version"] != "2.0.0"
        or root["profile"] != PROFILE
        or root["contract_sha256"] != contract.sha256.value
    ):
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    request_source = _mapping(
        root["request"],
        (
            "run_id",
            "requested_at",
            "program",
            "period",
            "article_measurements",
            "program_measurement",
            "provider_facts",
        ),
    )
    try:
        run_id = UUID(_string(request_source["run_id"], maximum=36))
    except ValueError:
        fail_attribution(AttributionFailureCode.FIXTURE_INVALID)
    request = AttributionRunRequest(
        run_id=run_id,
        requested_at=_timestamp(request_source["requested_at"]),
        contract=contract,
        program=_string(request_source["program"], maximum=64),
        period=_period(request_source["period"]),
        article_measurements=tuple(
            _article_measurement(item)
            for item in _sequence(
                request_source["article_measurements"], minimum=1, maximum=5
            )
        ),
        program_measurement=_program_measurement(request_source["program_measurement"]),
        provider_facts=tuple(
            _provider_fact(item)
            for item in _sequence(
                request_source["provider_facts"], minimum=1, maximum=100
            )
        ),
    )
    if request.input_sha256 != _sha(root["expected_input_sha256"]):
        fail_attribution(AttributionFailureCode.INPUT_HASH_MISMATCH)
    return RecordedAttributionScenario(
        scenario_id=_string(root["scenario_id"], maximum=128),
        fixture_sha256=Sha256Digest(hashlib.sha256(payload).hexdigest()),
        request=request,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedAttributionSnapshot(_Redacted):
    run_count: int
    replay_count: int

    def __post_init__(self) -> None:
        if (
            type(self.run_count) is not int
            or self.run_count < 0
            or type(self.replay_count) is not int
            or self.replay_count < 0
        ):
            fail_attribution()


@final
class RecordedAttributionAdapter(_Redacted):
    """Idempotent process-local adapter; it has no persistence or provider I/O."""

    __slots__ = ("_lock", "_replays", "_runs")

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[UUID, tuple[Sha256Digest, AttributionRunResult]] = {}
        self._replays = 0

    def run(self, request: AttributionRunRequest) -> AttributionRunResult:
        if type(request) is not AttributionRunRequest:
            fail_attribution()
        with self._lock:
            prior = self._runs.get(request.run_id)
            if prior is not None:
                prior_input, prior_result = prior
                if prior_input != request.input_sha256:
                    fail_attribution(AttributionFailureCode.RUN_ID_CONFLICT)
                self._replays += 1
                return prior_result
            result = build_attribution_run(request)
            self._runs[request.run_id] = (request.input_sha256, result)
            return result

    def snapshot(self) -> RecordedAttributionSnapshot:
        with self._lock:
            return RecordedAttributionSnapshot(
                run_count=len(self._runs), replay_count=self._replays
            )


__all__ = (
    "MAX_FIXTURE_BYTES",
    "RecordedAttributionAdapter",
    "RecordedAttributionScenario",
    "RecordedAttributionSnapshot",
    "load_recorded_attribution_fixture",
)
