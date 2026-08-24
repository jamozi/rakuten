"""Strict caller-bytes adapter for the ST-1104 synthetic dashboard fixture."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
import json
from typing import Any, NoReturn, cast, final

from raos.domain.analytics.analytics_finance_dashboard import (
    EXPECTED_VIEW_MAPPING,
    PROFILE,
    SCHEMA_VERSION,
    SCREEN_ORDER,
    DashboardDigest,
    DashboardFailure,
    DashboardFailureCode,
    RecordedDashboardCommand,
    RecordedDashboardSources,
    fail_dashboard,
)
from raos.domain.analytics.kpi_read_model import KpiReadModelSnapshot
from raos.domain.finance.unit_economics import (
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
)


_ROOT_KEYS = (
    "schema_version",
    "profile",
    "recording_id",
    "synthetic",
    "environment",
    "evaluated_at",
    "screen_order",
    "source_bindings",
    "view_mapping",
    "freshness_policy",
    "cross_source_comparison",
    "route_registered",
    "publication_authorized",
    "production_eligible",
)
_BINDING_KEYS = (
    "st1205_fixture_sha256",
    "st1205_input_sha256",
    "st1304_fixture_sha256",
    "st1304_input_sha256",
    "st1304_result_sha256",
)


def _invalid() -> NoReturn:
    fail_dashboard(DashboardFailureCode.FIXTURE_INVALID)


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _invalid()


def _mapping(value: object, keys: tuple[str, ...]) -> Mapping[str, object]:
    if type(value) is not dict or tuple(cast(dict[object, object], value)) != keys:
        _invalid()
    if any(type(key) is not str for key in cast(dict[object, object], value)):
        _invalid()
    return cast(Mapping[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str:
        _invalid()
    return value


def _string_array(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        _invalid()
    return tuple(cast(list[str], value))


def _timestamp(value: object) -> datetime:
    rendered = _text(value)
    if len(rendered) != 20 or not rendered.endswith("Z"):
        _invalid()
    try:
        parsed = datetime.strptime(rendered, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _invalid()
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != rendered:
        _invalid()
    return parsed


def _parse_fixture(
    fixture_bytes: bytes,
    command: RecordedDashboardCommand,
) -> tuple[datetime, tuple[tuple[str, tuple[str, ...]], ...]]:
    if (
        type(fixture_bytes) is not bytes
        or len(fixture_bytes) != command.fixture_bytes
        or DashboardDigest.of(fixture_bytes) != command.fixture_sha256
    ):
        fail_dashboard(DashboardFailureCode.FIXTURE_HASH_MISMATCH)
    try:
        value = json.loads(
            fixture_bytes.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except DashboardFailure:
        raise
    except Exception:
        _invalid()
    root = _mapping(value, _ROOT_KEYS)
    if (
        root["schema_version"] != SCHEMA_VERSION
        or root["profile"] != PROFILE
        or root["recording_id"] != "st1104-six-screen-recorded-v2"
        or root["synthetic"] is not True
        or root["environment"] != "ENV-CI"
        or _string_array(root["screen_order"]) != SCREEN_ORDER
        or root["freshness_policy"]
        != "SHOW_SOURCE_TIMESTAMPS_NO_INFERRED_CURRENT_OR_STALE"
        or root["cross_source_comparison"] != "UNAVAILABLE_PERIOD_MISMATCH"
        or root["route_registered"] is not False
        or root["publication_authorized"] is not False
        or root["production_eligible"] is not False
    ):
        _invalid()
    bindings = _mapping(root["source_bindings"], _BINDING_KEYS)
    try:
        binding_digests = {
            name: DashboardDigest(_text(bindings[name])) for name in _BINDING_KEYS
        }
    except DashboardFailure:
        raise
    if (
        binding_digests["st1205_input_sha256"] != command.expected_kpi_input_sha256
        or binding_digests["st1304_input_sha256"] != command.expected_unit_input_sha256
        or binding_digests["st1304_result_sha256"]
        != command.expected_unit_result_sha256
    ):
        fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
    mapping = _mapping(root["view_mapping"], SCREEN_ORDER)
    view_mapping = tuple(
        (screen_id, _string_array(mapping[screen_id])) for screen_id in SCREEN_ORDER
    )
    if view_mapping != EXPECTED_VIEW_MAPPING:
        _invalid()
    return _timestamp(root["evaluated_at"]), view_mapping


@final
class RecordedAnalyticsFinanceDashboardAdapter:
    """Bind one immutable fixture to already-calculated dependency snapshots."""

    __slots__ = ("_fixture_bytes", "_kpi_snapshot", "_unit_request", "_unit_result")

    def __init__(
        self,
        *,
        fixture_bytes: bytes,
        kpi_snapshot: KpiReadModelSnapshot,
        unit_request: UnitEconomicsRunRequest,
        unit_result: UnitEconomicsRunResult,
    ) -> None:
        if (
            type(fixture_bytes) is not bytes
            or type(kpi_snapshot) is not KpiReadModelSnapshot
            or type(unit_request) is not UnitEconomicsRunRequest
            or type(unit_result) is not UnitEconomicsRunResult
        ):
            fail_dashboard()
        self._fixture_bytes = fixture_bytes
        self._kpi_snapshot = kpi_snapshot
        self._unit_request = unit_request
        self._unit_result = unit_result

    def read(self, command: RecordedDashboardCommand) -> RecordedDashboardSources:
        if type(command) is not RecordedDashboardCommand:
            fail_dashboard()
        evaluated_at, view_mapping = _parse_fixture(self._fixture_bytes, command)
        if (
            self._kpi_snapshot.input_digest.value
            != command.expected_kpi_input_sha256.value
            or self._unit_request.input_sha256.value
            != command.expected_unit_input_sha256.value
            or self._unit_result.result_sha256.value
            != command.expected_unit_result_sha256.value
        ):
            fail_dashboard(DashboardFailureCode.SOURCE_MISMATCH)
        return RecordedDashboardSources(
            recording_id="st1104-six-screen-recorded-v2",
            fixture_sha256=command.fixture_sha256,
            evaluated_at=evaluated_at,
            screen_order=SCREEN_ORDER,
            view_mapping=view_mapping,
            kpi_snapshot=self._kpi_snapshot,
            unit_request=self._unit_request,
            unit_result=self._unit_result,
        )


__all__ = ("RecordedAnalyticsFinanceDashboardAdapter",)
