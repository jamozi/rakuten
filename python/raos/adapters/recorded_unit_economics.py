"""Strict tracked-fixture adapter for the ST-1304 local calculation seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
from typing import Any, Final, NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.adapters.recorded_attribution import load_recorded_attribution_fixture
from raos.domain.finance.attribution import (
    ContractArticle,
    MeasurementAttributionContract,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    VerificationState,
    CohortMaturity,
    build_attribution_run,
)
from raos.domain.finance.unit_economics import (
    COST_METRICS,
    PROFILE,
    ArticleCostObservation,
    UnitEconomicsFailure,
    UnitEconomicsFailureCode,
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
    build_unit_economics,
    fail_unit_economics,
)
from raos.domain.ops.object_intake import Sha256Digest


MAX_FIXTURE_BYTES: Final = 2 * 1024 * 1024
_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,127}\Z", re.ASCII)


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1304-fixture>)"

    def __str__(self) -> str:
        return "<redacted-st1304-fixture>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded unit-economics serialization is forbidden")


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if (
        type(value) is not dict
        or tuple(cast(dict[object, object], value)) != keys
        or any(type(key) is not str for key in cast(dict[object, object], value))
    ):
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


def _sequence(
    value: object, *, minimum: int = 0, maximum: int = 10_000
) -> list[object]:
    if type(value) is not list:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    result = cast(list[object], value)
    if not minimum <= len(result) <= maximum:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return result


def _string(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return value


def _sha(value: object) -> Sha256Digest:
    try:
        rendered = value.value if type(value) is Sha256Digest else value
        return Sha256Digest(_string(rendered, maximum=64))
    except Exception:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)


def _timestamp(value: object) -> datetime:
    rendered = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return parsed


def _date(value: object) -> date:
    rendered = _string(value, maximum=10)
    try:
        parsed = date.fromisoformat(rendered)
    except ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    if parsed.isoformat() != rendered:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return parsed


def _period(value: object) -> MeasurementPeriod:
    source = _mapping(value, ("start_date", "end_exclusive_date", "duration_days"))
    if source["duration_days"] != 14:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return MeasurementPeriod(
        start_date=_date(source["start_date"]),
        end_exclusive_date=_date(source["end_exclusive_date"]),
    )


def _verification(value: object) -> tuple[VerificationState, Sha256Digest | None]:
    source = _mapping(value, ("state", "input_sha256"))
    try:
        state = VerificationState(source["state"])
    except TypeError, ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    digest = None if source["input_sha256"] is None else _sha(source["input_sha256"])
    return state, digest


def _cohort(value: object) -> tuple[CohortMaturity, Sha256Digest | None]:
    source = _mapping(value, ("state", "input_sha256"))
    try:
        state = CohortMaturity(source["state"])
    except TypeError, ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    digest = None if source["input_sha256"] is None else _sha(source["input_sha256"])
    return state, digest


def _measurement_value(value: object) -> MeasurementValue:
    source = _mapping(value, ("state", "value", "input_sha256"))
    try:
        state = MeasurementValueState(source["state"])
    except TypeError, ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    raw_value = source["value"]
    if raw_value is not None and type(raw_value) is not int:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return MeasurementValue(
        state=state,
        value=raw_value,
        input_sha256=(
            None if source["input_sha256"] is None else _sha(source["input_sha256"])
        ),
    )


def _cost_observation(
    value: object, contract: MeasurementAttributionContract
) -> ArticleCostObservation:
    source = _mapping(
        value,
        ("slot", "program", "period", "verification", "cohort", "metrics"),
    )
    slot = source["slot"]
    if type(slot) is not int or not 1 <= slot <= 5:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    article: ContractArticle = contract.articles[slot - 1]
    verification_state, verification_sha256 = _verification(source["verification"])
    cohort_state, cohort_sha256 = _cohort(source["cohort"])
    metric_source = _mapping(source["metrics"], COST_METRICS)
    return ArticleCostObservation(
        article=article,
        program=_string(source["program"], maximum=64),
        period=_period(source["period"]),
        verification_state=verification_state,
        verification_sha256=verification_sha256,
        cohort_state=cohort_state,
        cohort_sha256=cohort_sha256,
        metrics=tuple(
            (name, _measurement_value(metric_source[name])) for name in COST_METRICS
        ),
    )


def _read_fixture(path: Path) -> bytes:
    if not path.is_absolute():
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
        if stat.S_ISLNK(metadata.st_mode):
            fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    try:
        metadata = path.stat()
        payload = path.read_bytes()
    except OSError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not payload
        or len(payload) != metadata.st_size
        or len(payload) > MAX_FIXTURE_BYTES
    ):
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return payload


def _unique_json(payload: bytes) -> Mapping[str, object]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
            result[key] = value
        return result

    def reject_constant(value: str) -> NoReturn:
        del value
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)

    def reject_float(value: str) -> NoReturn:
        del value
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)

    try:
        value = json.loads(
            payload,
            object_pairs_hook=pairs,
            parse_constant=reject_constant,
            parse_float=reject_float,
        )
    except UnitEconomicsFailure:
        raise
    except Exception:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    if type(value) is not dict:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedUnitEconomicsScenario(_Redacted):
    scenario_id: str
    fixture_sha256: Sha256Digest
    attribution_fixture_sha256: Sha256Digest
    request: UnitEconomicsRunRequest

    def __post_init__(self) -> None:
        if (
            type(self.scenario_id) is not str
            or _REFERENCE.fullmatch(self.scenario_id) is None
            or type(self.request) is not UnitEconomicsRunRequest
        ):
            fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
        object.__setattr__(self, "fixture_sha256", _sha(self.fixture_sha256))
        object.__setattr__(
            self, "attribution_fixture_sha256", _sha(self.attribution_fixture_sha256)
        )


def load_recorded_unit_economics_fixture(
    path: object,
    *,
    attribution_fixture_path: object,
    contract: MeasurementAttributionContract,
) -> RecordedUnitEconomicsScenario:
    """Load one strict tracked synthetic scenario without retaining raw bytes."""

    if (
        not isinstance(path, Path)
        or not isinstance(attribution_fixture_path, Path)
        or type(contract) is not MeasurementAttributionContract
    ):
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    payload = _read_fixture(path)
    attribution_payload = _read_fixture(attribution_fixture_path)
    root = _mapping(
        _unique_json(payload),
        (
            "schema_version",
            "profile",
            "scenario_id",
            "synthetic",
            "attribution_fixture_sha256",
            "attribution_contract_sha256",
            "expected_attribution_input_sha256",
            "expected_attribution_result_sha256",
            "request",
            "expected_input_sha256",
            "expected_result_sha256",
        ),
    )
    attribution_fixture_sha256 = Sha256Digest(
        hashlib.sha256(attribution_payload).hexdigest()
    )
    if (
        root["schema_version"] != "2.0.0"
        or root["profile"] != PROFILE
        or root["synthetic"] is not True
        or _sha(root["attribution_fixture_sha256"]) != attribution_fixture_sha256
        or _sha(root["attribution_contract_sha256"]) != contract.sha256
    ):
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    attribution_scenario = load_recorded_attribution_fixture(
        attribution_fixture_path, contract=contract
    )
    attribution_result = build_attribution_run(attribution_scenario.request)
    if attribution_scenario.request.input_sha256 != _sha(
        root["expected_attribution_input_sha256"]
    ) or attribution_result.result_sha256 != _sha(
        root["expected_attribution_result_sha256"]
    ):
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    request_source = _mapping(
        root["request"],
        ("run_id", "requested_at", "cost_observations"),
    )
    try:
        run_id = UUID(_string(request_source["run_id"], maximum=36))
    except ValueError:
        fail_unit_economics(UnitEconomicsFailureCode.FIXTURE_INVALID)
    request = UnitEconomicsRunRequest(
        run_id=run_id,
        requested_at=_timestamp(request_source["requested_at"]),
        attribution_request=attribution_scenario.request,
        attribution_result=attribution_result,
        cost_observations=tuple(
            _cost_observation(item, contract)
            for item in _sequence(
                request_source["cost_observations"], minimum=1, maximum=5
            )
        ),
    )
    if request.input_sha256 != _sha(root["expected_input_sha256"]):
        fail_unit_economics(UnitEconomicsFailureCode.INPUT_HASH_MISMATCH)
    result = build_unit_economics(request)
    if result.result_sha256 != _sha(root["expected_result_sha256"]):
        fail_unit_economics(UnitEconomicsFailureCode.RESULT_MISMATCH)
    return RecordedUnitEconomicsScenario(
        scenario_id=_string(root["scenario_id"], maximum=128),
        fixture_sha256=Sha256Digest(hashlib.sha256(payload).hexdigest()),
        attribution_fixture_sha256=attribution_fixture_sha256,
        request=request,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedUnitEconomicsSnapshot(_Redacted):
    run_count: int
    replay_count: int

    def __post_init__(self) -> None:
        if (
            type(self.run_count) is not int
            or self.run_count < 0
            or type(self.replay_count) is not int
            or self.replay_count < 0
        ):
            fail_unit_economics()


@final
class RecordedUnitEconomicsAdapter(_Redacted):
    """Idempotent process-local adapter with no persistence or provider I/O."""

    __slots__ = ("_lock", "_replays", "_runs")

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[UUID, tuple[Sha256Digest, UnitEconomicsRunResult]] = {}
        self._replays = 0

    def run(self, request: UnitEconomicsRunRequest) -> UnitEconomicsRunResult:
        if type(request) is not UnitEconomicsRunRequest:
            fail_unit_economics()
        with self._lock:
            prior = self._runs.get(request.run_id)
            if prior is not None:
                prior_input, prior_result = prior
                if prior_input != request.input_sha256:
                    fail_unit_economics(UnitEconomicsFailureCode.RUN_ID_CONFLICT)
                self._replays += 1
                return prior_result
            result = build_unit_economics(request)
            self._runs[request.run_id] = (request.input_sha256, result)
            return result

    def snapshot(self) -> RecordedUnitEconomicsSnapshot:
        with self._lock:
            return RecordedUnitEconomicsSnapshot(
                run_count=len(self._runs), replay_count=self._replays
            )


__all__ = (
    "MAX_FIXTURE_BYTES",
    "RecordedUnitEconomicsAdapter",
    "RecordedUnitEconomicsScenario",
    "RecordedUnitEconomicsSnapshot",
    "load_recorded_unit_economics_fixture",
)
