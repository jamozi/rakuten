from __future__ import annotations

import ast
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from typing import cast

import pytest

from raos.adapters.recorded_unit_economics import (
    RecordedUnitEconomicsAdapter,
    RecordedUnitEconomicsScenario,
    load_recorded_unit_economics_fixture,
)
from raos.application.finance.unit_economics import UnitEconomicsService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import (
    CohortMaturity,
    MeasurementAttributionContract,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    VerificationState,
    build_attribution_run,
)
from raos.domain.finance.unit_economics import (
    EconomicsAvailability,
    MetricAvailability,
    UnavailableReason,
    UnitEconomicsFailureCode,
    UnitEconomicsMetric,
    UnitEconomicsRunRequest,
    UnitEconomicsRunResult,
    build_unit_economics,
)
from raos.domain.ops.object_intake import Sha256Digest

from .conftest import (
    ATTRIBUTION_FIXTURE,
    FIXTURE,
    ROOT,
    failure_code,
)


HASH = Sha256Digest("f" * 64)


def _replace_cost_metric(
    request: UnitEconomicsRunRequest,
    *,
    slot: int,
    name: str,
    value: MeasurementValue,
) -> UnitEconomicsRunRequest:
    rows = list(request.cost_observations)
    selected = rows[slot - 1]
    rows[slot - 1] = replace(
        selected,
        metrics=tuple(
            (metric_name, value if metric_name == name else metric_value)
            for metric_name, metric_value in selected.metrics
        ),
    )
    return replace(request, cost_observations=tuple(rows))


def _replace_attribution_metric(
    request: UnitEconomicsRunRequest,
    *,
    slot: int,
    name: str,
    value: MeasurementValue,
) -> UnitEconomicsRunRequest:
    rows = list(request.attribution_request.article_measurements)
    selected = rows[slot - 1]
    rows[slot - 1] = replace(
        selected,
        metrics=tuple(
            (metric_name, value if metric_name == name else metric_value)
            for metric_name, metric_value in selected.metrics
        ),
    )
    attribution_request = replace(
        request.attribution_request, article_measurements=tuple(rows)
    )
    return replace(
        request,
        attribution_request=attribution_request,
        attribution_result=build_attribution_run(attribution_request),
    )


def _metric(result: UnitEconomicsRunResult, name: str) -> UnitEconomicsMetric:
    return next(item for item in result.metrics if item.name == name)


def test_unknown_labor_is_unavailable_never_zero(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = _replace_cost_metric(
        scenario.request,
        slot=1,
        name="labor_hourly_cost_jpy",
        value=MeasurementValue(MeasurementValueState.NOT_OBSERVED, None, None),
    )
    result = build_unit_economics(request)
    contribution = _metric(result, "direct_confirmed_contribution_profit_jpy")
    assert result.availability is EconomicsAvailability.PARTIAL
    assert contribution.availability is MetricAvailability.UNAVAILABLE
    assert contribution.unavailable_reason is UnavailableReason.LABOR_RATE_UNKNOWN
    assert contribution.value is None
    assert result.totals.human_labor_cost_jpy is None
    assert _metric(result, "confirmed_epc_jpy").value == Decimal("2.40")


@pytest.mark.parametrize(
    ("state", "value", "reason"),
    [
        (MeasurementValueState.NOT_OBSERVED, None, UnavailableReason.MISSING_INPUT),
        (MeasurementValueState.UNVERIFIED, 300, UnavailableReason.UNVERIFIED_INPUT),
    ],
)
def test_missing_or_unverified_metric_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
    state: MeasurementValueState,
    value: int | None,
    reason: UnavailableReason,
) -> None:
    request = _replace_cost_metric(
        scenario.request,
        slot=1,
        name="qualified_sessions",
        value=MeasurementValue(
            state, value, None if state is MeasurementValueState.NOT_OBSERVED else HASH
        ),
    )
    rpm = _metric(build_unit_economics(request), "confirmed_rpm_jpy")
    assert rpm.availability is MetricAvailability.UNAVAILABLE
    assert rpm.unavailable_reason is reason
    assert rpm.value is None


@pytest.mark.parametrize(
    ("state", "value", "digest", "reason"),
    [
        (
            MeasurementValueState.NOT_OBSERVED,
            None,
            None,
            UnavailableReason.MISSING_INPUT,
        ),
        (
            MeasurementValueState.UNVERIFIED,
            0,
            HASH,
            UnavailableReason.UNVERIFIED_INPUT,
        ),
    ],
)
def test_incomplete_actual_cost_components_make_profit_unavailable(
    scenario: RecordedUnitEconomicsScenario,
    state: MeasurementValueState,
    value: int | None,
    digest: Sha256Digest | None,
    reason: UnavailableReason,
) -> None:
    request = _replace_cost_metric(
        scenario.request,
        slot=1,
        name="ai_actual_cost_jpy",
        value=MeasurementValue(state, value, digest),
    )
    result = build_unit_economics(request)
    contribution = _metric(result, "direct_confirmed_contribution_profit_jpy")
    assert result.availability is EconomicsAvailability.PARTIAL
    assert result.totals.incremental_external_cost_jpy is None
    assert contribution.availability is MetricAvailability.UNAVAILABLE
    assert contribution.unavailable_reason is reason
    assert contribution.value is None


@pytest.mark.parametrize(
    "name",
    [
        "qualified_sessions",
        "approved_article_versions",
        "trailing_monthly_confirmed_contribution_jpy",
    ],
)
def test_zero_denominator_is_unavailable(
    scenario: RecordedUnitEconomicsScenario, name: str
) -> None:
    request = scenario.request
    for slot in range(1, 6):
        request = _replace_cost_metric(
            request,
            slot=slot,
            name=name,
            value=MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 0, HASH),
        )
    result = build_unit_economics(request)
    target = {
        "qualified_sessions": "confirmed_rpm_jpy",
        "approved_article_versions": "ai_cost_per_approved_article_jpy",
        "trailing_monthly_confirmed_contribution_jpy": "content_payback_months",
    }[name]
    metric = _metric(result, target)
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR


def test_zero_work_minutes_is_unavailable_after_exact_measurement_binding(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    for slot in range(1, 6):
        zero = MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 0, HASH)
        request = _replace_attribution_metric(
            request, slot=slot, name="work_minutes", value=zero
        )
        request = _replace_cost_metric(
            request, slot=slot, name="work_minutes", value=zero
        )
    metric = _metric(
        build_unit_economics(request), "confirmed_reward_per_content_hour_jpy"
    )
    assert metric.availability is MetricAvailability.UNAVAILABLE
    assert metric.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR


def test_nonzero_actual_cost_is_exact_and_conserved(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    observed = MeasurementValue(MeasurementValueState.OBSERVED_VALUE, 7, HASH)
    request = _replace_attribution_metric(
        scenario.request,
        slot=1,
        name="incremental_cost_jpy",
        value=observed,
    )
    rows = list(request.cost_observations)
    selected = rows[0]
    rows[0] = replace(
        selected,
        metrics=tuple(
            (
                metric_name,
                observed
                if metric_name in {"incremental_cost_jpy", "ai_actual_cost_jpy"}
                else metric_value,
            )
            for metric_name, metric_value in selected.metrics
        ),
    )
    request = replace(request, cost_observations=tuple(rows))
    result = build_unit_economics(request)
    assert result.totals.incremental_external_cost_jpy == Decimal(7)
    assert _metric(result, "direct_confirmed_contribution_profit_jpy").value == Decimal(
        "-5887.00"
    )


def test_cost_component_conservation_failure_is_rejected(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    assert (
        failure_code(
            lambda: _replace_cost_metric(
                scenario.request,
                slot=1,
                name="ai_actual_cost_jpy",
                value=MeasurementValue(MeasurementValueState.OBSERVED_VALUE, 1, HASH),
            )
        )
        is UnitEconomicsFailureCode.COST_CONSERVATION_FAILED
    )


def test_measurement_cost_mismatch_is_rejected(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = _replace_cost_metric(
        scenario.request,
        slot=1,
        name="work_minutes",
        value=MeasurementValue(MeasurementValueState.OBSERVED_VALUE, 61, HASH),
    )
    assert (
        failure_code(lambda: build_unit_economics(request))
        is UnitEconomicsFailureCode.MEASUREMENT_COST_MISMATCH
    )


def test_immature_cohort_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    rows = list(request.cost_observations)
    rows[0] = replace(rows[0], cohort_state=CohortMaturity.IMMATURE)
    result = build_unit_economics(replace(request, cost_observations=tuple(rows)))
    assert result.availability is EconomicsAvailability.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.COHORT_IMMATURE
    assert all(item.value is None for item in result.metrics)


def test_mixed_period_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    rows = list(request.cost_observations)
    period = MeasurementPeriod(
        start_date=rows[0].period.start_date + timedelta(days=1),
        end_exclusive_date=rows[0].period.end_exclusive_date + timedelta(days=1),
    )
    rows[0] = replace(rows[0], period=period)
    result = build_unit_economics(replace(request, cost_observations=tuple(rows)))
    assert result.availability is EconomicsAvailability.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.PERIOD_MISMATCH


def test_mixed_program_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    rows = list(request.cost_observations)
    rows[0] = replace(rows[0], program="OTHER_AFFILIATE_PROGRAM")
    result = build_unit_economics(replace(request, cost_observations=tuple(rows)))
    assert result.availability is EconomicsAvailability.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.PROGRAM_MISMATCH


def test_missing_article_slot_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    result = build_unit_economics(
        replace(request, cost_observations=request.cost_observations[:-1])
    )
    assert result.availability is EconomicsAvailability.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.MISSING_ARTICLE_SLOTS


def test_unverified_cost_batch_is_unavailable(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    rows = list(request.cost_observations)
    rows[0] = replace(rows[0], verification_state=VerificationState.UNVERIFIED)
    result = build_unit_economics(replace(request, cost_observations=tuple(rows)))
    assert result.unavailable_reason is UnavailableReason.UNVERIFIED_INPUT


def test_input_hash_tamper_is_detected(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    object.__setattr__(request, "input_sha256", Sha256Digest("0" * 64))
    assert (
        failure_code(lambda: build_unit_economics(request))
        is UnitEconomicsFailureCode.INPUT_HASH_MISMATCH
    )


def test_attribution_result_tamper_is_detected(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    request = scenario.request
    hostile = replace(request.attribution_result, result_sha256=Sha256Digest("0" * 64))
    changed = replace(request, attribution_result=hostile)
    assert (
        failure_code(lambda: build_unit_economics(changed))
        is UnitEconomicsFailureCode.ATTRIBUTION_RESULT_MISMATCH
    )


def test_same_run_id_changed_input_is_rejected(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    first = scenario.request
    adapter = RecordedUnitEconomicsAdapter()
    adapter.run(first)
    second = replace(first, requested_at=first.requested_at + timedelta(seconds=1))
    assert (
        failure_code(lambda: adapter.run(second))
        is UnitEconomicsFailureCode.RUN_ID_CONFLICT
    )


def test_application_rejects_nonlocal_environment_and_hostile_result(
    scenario: RecordedUnitEconomicsScenario,
) -> None:
    assert (
        failure_code(
            lambda: UnitEconomicsService(
                environment=RuntimeEnvironment.PRODUCTION,
                runner=RecordedUnitEconomicsAdapter(),
            )
        )
        is UnitEconomicsFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )

    class HostileRunner:
        def run(self, request: UnitEconomicsRunRequest) -> UnitEconomicsRunResult:
            del request
            return cast(UnitEconomicsRunResult, object())

    service = UnitEconomicsService(
        environment=RuntimeEnvironment.CI, runner=HostileRunner()
    )
    assert (
        failure_code(lambda: service.execute(scenario.request))
        is UnitEconomicsFailureCode.RESULT_MISMATCH
    )


def _write_fixture(tmp_path: Path, payload: bytes) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "fixture.json"
    target.write_bytes(payload)
    return target


def test_fixture_duplicate_unknown_and_hash_tamper_are_rejected(
    tmp_path: Path, measurement_contract: MeasurementAttributionContract
) -> None:
    payload = FIXTURE.read_bytes()
    variants = (
        payload.replace(
            b'"schema_version":', b'"schema_version":"2.0.0", "schema_version":', 1
        ),
        payload.replace(b'"profile":', b'"unknown":true, "profile":', 1),
        payload.replace(
            json.loads(payload)["expected_input_sha256"].encode("ascii"),
            b"0" * 64,
            1,
        ),
        payload.replace(b'"value": 300', b'"value": 1.5', 1),
    )
    for index, variant in enumerate(variants):
        path = _write_fixture(tmp_path / str(index), variant)
        assert failure_code(
            lambda: load_recorded_unit_economics_fixture(
                path.resolve(),
                attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
                contract=measurement_contract,
            )
        ) in {
            UnitEconomicsFailureCode.FIXTURE_INVALID,
            UnitEconomicsFailureCode.INPUT_HASH_MISMATCH,
            UnitEconomicsFailureCode.RESULT_MISMATCH,
        }


def test_fixture_symlink_and_hardlink_are_rejected(
    tmp_path: Path, measurement_contract: MeasurementAttributionContract
) -> None:
    regular = _write_fixture(tmp_path, FIXTURE.read_bytes())
    symlink = tmp_path / "symlink.json"
    symlink.symlink_to(regular)
    hardlink = tmp_path / "hardlink.json"
    os.link(regular, hardlink)
    for path in (symlink, hardlink):
        assert (
            failure_code(
                lambda: load_recorded_unit_economics_fixture(
                    path.absolute(),
                    attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
                    contract=measurement_contract,
                )
            )
            is UnitEconomicsFailureCode.FIXTURE_INVALID
        )


def test_runtime_imports_exclude_external_editorial_and_public_capabilities() -> None:
    forbidden_roots = {
        "boto3",
        "botocore",
        "django",
        "httpx",
        "psycopg",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib",
        "wordpress",
    }
    paths = (
        ROOT / "python/raos/domain/finance/unit_economics.py",
        ROOT / "python/raos/ports/unit_economics.py",
        ROOT / "python/raos/application/finance/unit_economics.py",
        ROOT / "python/raos/adapters/recorded_unit_economics.py",
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
                assert ".editorial" not in node.module
                assert ".publishing" not in node.module
        assert imported.isdisjoint(forbidden_roots)
