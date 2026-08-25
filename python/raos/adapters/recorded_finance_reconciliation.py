"""Strict tracked-fixture adapter for the ST-1305 local report seam."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from threading import Lock
from typing import Any, Final, NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.adapters.recorded_unit_economics import (
    load_recorded_unit_economics_fixture,
)
from raos.domain.finance.attribution import MeasurementAttributionContract
from raos.domain.finance.reconciliation import (
    PROFILE,
    FinanceReconciliationFailure,
    FinanceReconciliationFailureCode,
    FinanceReconciliationRunRequest,
    FinanceReconciliationRunResult,
    build_finance_reconciliation,
    fail_finance_reconciliation,
)
from raos.domain.finance.unit_economics import build_unit_economics
from raos.domain.ops.object_intake import Sha256Digest


MAX_FIXTURE_BYTES: Final = 128 * 1024
_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{0,127}\Z", re.ASCII)


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st1305-fixture>)"

    def __str__(self) -> str:
        return "<redacted-st1305-fixture>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("recorded finance-reconciliation serialization is forbidden")


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if (
        type(value) is not dict
        or tuple(cast(dict[object, object], value)) != keys
        or any(type(key) is not str for key in cast(dict[object, object], value))
    ):
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


def _string(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not 1 <= len(value) <= maximum:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    return value


def _sha(value: object) -> Sha256Digest:
    try:
        rendered = value.value if type(value) is Sha256Digest else value
        return Sha256Digest(_string(rendered, maximum=64))
    except Exception:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)


def _timestamp(value: object) -> datetime:
    rendered = _string(value, maximum=20)
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    return parsed


def _read_fixture(path: Path) -> bytes:
    if not path.is_absolute():
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.FIXTURE_INVALID
            )
        if stat.S_ISLNK(metadata.st_mode):
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.FIXTURE_INVALID
            )
    try:
        metadata = path.stat()
        payload = path.read_bytes()
    except OSError:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not payload
        or len(payload) != metadata.st_size
        or len(payload) > MAX_FIXTURE_BYTES
    ):
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    return payload


def _unique_json(payload: bytes) -> Mapping[str, object]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                fail_finance_reconciliation(
                    FinanceReconciliationFailureCode.FIXTURE_INVALID
                )
            result[key] = value
        return result

    def reject_number(value: str) -> NoReturn:
        del value
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)

    try:
        value = json.loads(
            payload,
            object_pairs_hook=pairs,
            parse_constant=reject_number,
            parse_float=reject_number,
        )
    except FinanceReconciliationFailure:
        raise
    except Exception:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    if type(value) is not dict:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    return cast(Mapping[str, object], value)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinanceReconciliationScenario(_Redacted):
    scenario_id: str
    fixture_sha256: Sha256Digest
    unit_economics_fixture_sha256: Sha256Digest
    request: FinanceReconciliationRunRequest

    def __post_init__(self) -> None:
        if (
            type(self.scenario_id) is not str
            or _REFERENCE.fullmatch(self.scenario_id) is None
            or type(self.request) is not FinanceReconciliationRunRequest
        ):
            fail_finance_reconciliation(
                FinanceReconciliationFailureCode.FIXTURE_INVALID
            )
        object.__setattr__(self, "fixture_sha256", _sha(self.fixture_sha256))
        object.__setattr__(
            self,
            "unit_economics_fixture_sha256",
            _sha(self.unit_economics_fixture_sha256),
        )


def load_recorded_finance_reconciliation_fixture(
    path: object,
    *,
    unit_economics_fixture_path: object,
    attribution_fixture_path: object,
    contract: MeasurementAttributionContract,
) -> RecordedFinanceReconciliationScenario:
    """Load one strict tracked synthetic report request."""

    if (
        not isinstance(path, Path)
        or not isinstance(unit_economics_fixture_path, Path)
        or not isinstance(attribution_fixture_path, Path)
        or type(contract) is not MeasurementAttributionContract
    ):
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    payload = _read_fixture(path)
    unit_payload = _read_fixture(unit_economics_fixture_path)
    root = _mapping(
        _unique_json(payload),
        (
            "schema_version",
            "profile",
            "scenario_id",
            "synthetic",
            "unit_economics_fixture_sha256",
            "expected_unit_economics_input_sha256",
            "expected_unit_economics_result_sha256",
            "request",
            "expected_input_sha256",
            "expected_result_sha256",
        ),
    )
    unit_fixture_sha256 = Sha256Digest(hashlib.sha256(unit_payload).hexdigest())
    if (
        root["schema_version"] != "2.0.0"
        or root["profile"] != PROFILE
        or root["synthetic"] is not True
        or _sha(root["unit_economics_fixture_sha256"]) != unit_fixture_sha256
    ):
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    unit_scenario = load_recorded_unit_economics_fixture(
        unit_economics_fixture_path,
        attribution_fixture_path=attribution_fixture_path,
        contract=contract,
    )
    unit_result = build_unit_economics(unit_scenario.request)
    if unit_scenario.request.input_sha256 != _sha(
        root["expected_unit_economics_input_sha256"]
    ) or unit_result.result_sha256 != _sha(
        root["expected_unit_economics_result_sha256"]
    ):
        fail_finance_reconciliation(
            FinanceReconciliationFailureCode.DEPENDENCY_RESULT_MISMATCH
        )
    request_source = _mapping(root["request"], ("run_id", "requested_at"))
    try:
        run_id = UUID(_string(request_source["run_id"], maximum=36))
    except ValueError:
        fail_finance_reconciliation(FinanceReconciliationFailureCode.FIXTURE_INVALID)
    request = FinanceReconciliationRunRequest(
        run_id=run_id,
        requested_at=_timestamp(request_source["requested_at"]),
        unit_economics_request=unit_scenario.request,
        unit_economics_result=unit_result,
    )
    if request.input_sha256 != _sha(root["expected_input_sha256"]):
        fail_finance_reconciliation(
            FinanceReconciliationFailureCode.INPUT_HASH_MISMATCH
        )
    result = build_finance_reconciliation(request)
    if result.result_sha256 != _sha(root["expected_result_sha256"]):
        fail_finance_reconciliation(FinanceReconciliationFailureCode.RESULT_MISMATCH)
    return RecordedFinanceReconciliationScenario(
        scenario_id=_string(root["scenario_id"], maximum=128),
        fixture_sha256=Sha256Digest(hashlib.sha256(payload).hexdigest()),
        unit_economics_fixture_sha256=unit_fixture_sha256,
        request=request,
    )


@dataclass(frozen=True, slots=True, repr=False)
class RecordedFinanceReconciliationSnapshot(_Redacted):
    run_count: int
    replay_count: int

    def __post_init__(self) -> None:
        if (
            type(self.run_count) is not int
            or self.run_count < 0
            or type(self.replay_count) is not int
            or self.replay_count < 0
        ):
            fail_finance_reconciliation()


@final
class RecordedFinanceReconciliationAdapter(_Redacted):
    """Idempotent process-local adapter with no persistence or provider I/O."""

    __slots__ = ("_lock", "_replays", "_runs")

    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[UUID, tuple[Sha256Digest, FinanceReconciliationRunResult]] = {}
        self._replays = 0

    def run(
        self, request: FinanceReconciliationRunRequest
    ) -> FinanceReconciliationRunResult:
        if type(request) is not FinanceReconciliationRunRequest:
            fail_finance_reconciliation()
        with self._lock:
            prior = self._runs.get(request.run_id)
            if prior is not None:
                prior_input, prior_result = prior
                if prior_input != request.input_sha256:
                    fail_finance_reconciliation(
                        FinanceReconciliationFailureCode.RUN_ID_CONFLICT
                    )
                self._replays += 1
                return prior_result
            result = build_finance_reconciliation(request)
            self._runs[request.run_id] = (request.input_sha256, result)
            return result

    def snapshot(self) -> RecordedFinanceReconciliationSnapshot:
        with self._lock:
            return RecordedFinanceReconciliationSnapshot(
                run_count=len(self._runs), replay_count=self._replays
            )


__all__ = (
    "MAX_FIXTURE_BYTES",
    "RecordedFinanceReconciliationAdapter",
    "RecordedFinanceReconciliationScenario",
    "RecordedFinanceReconciliationSnapshot",
    "load_recorded_finance_reconciliation_fixture",
)
