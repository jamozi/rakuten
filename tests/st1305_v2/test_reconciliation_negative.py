from __future__ import annotations

import ast
from dataclasses import replace
from datetime import timedelta
import json
import os
from pathlib import Path
from typing import cast

import pytest

from raos.adapters.recorded_finance_reconciliation import (
    RecordedFinanceReconciliationAdapter,
    RecordedFinanceReconciliationScenario,
    load_recorded_finance_reconciliation_fixture,
)
from raos.application.finance.reconciliation import FinanceReconciliationService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import (
    AttributionAvailability,
    CohortMaturity,
    CohortStatus,
    DerivedMetric,
    MeasurementAttributionContract,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    UnavailableReason as AttributionUnavailableReason,
    VerificationState,
    build_attribution_run,
)
from raos.domain.finance.reconciliation import (
    FinanceReconciliationFailureCode,
    FinanceReconciliationRunRequest,
    FinanceReconciliationRunResult,
    LearningAvailability,
    ReconciliationComparison,
    ReconciliationUnavailableReason,
    build_finance_reconciliation,
)
from raos.domain.finance.unit_economics import (
    UnitEconomicsRunRequest,
    build_unit_economics,
)
from raos.domain.ops.object_intake import Sha256Digest

from .conftest import (
    ATTRIBUTION_FIXTURE,
    FIXTURE,
    ROOT,
    UNIT_ECONOMICS_FIXTURE,
    failure_code,
)


HASH = Sha256Digest("f" * 64)


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


def _finance_request(
    base: FinanceReconciliationRunRequest,
    unit_request: UnitEconomicsRunRequest,
) -> FinanceReconciliationRunRequest:
    return replace(
        base,
        unit_economics_request=unit_request,
        unit_economics_result=build_unit_economics(unit_request),
    )


def _measurement_metric(
    result: FinanceReconciliationRunResult, name: str
) -> DerivedMetric:
    return next(item for item in result.measurement_metrics if item.name == name)


@pytest.mark.parametrize(
    ("state", "value", "digest", "reason"),
    [
        (
            MeasurementValueState.NOT_OBSERVED,
            None,
            None,
            ReconciliationUnavailableReason.MISSING_INPUT,
        ),
        (
            MeasurementValueState.UNVERIFIED,
            600,
            HASH,
            ReconciliationUnavailableReason.UNVERIFIED_INPUT,
        ),
    ],
)
def test_missing_or_unverified_measurement_makes_learning_unavailable_never_zero(
    scenario: RecordedFinanceReconciliationScenario,
    state: MeasurementValueState,
    value: int | None,
    digest: Sha256Digest | None,
    reason: ReconciliationUnavailableReason,
) -> None:
    unit = _replace_attribution_metric(
        scenario.request.unit_economics_request,
        slot=1,
        name="search_impressions",
        value=MeasurementValue(state, value, digest),
    )
    result = build_finance_reconciliation(_finance_request(scenario.request, unit))
    metric = _measurement_metric(result, "search_ctr")
    assert metric.availability is AttributionAvailability.UNAVAILABLE
    assert metric.value_decimal is None
    assert result.learning_availability is LearningAvailability.UNAVAILABLE
    assert result.learning_unavailable_reason is reason
    assert result.learning_candidates == ()


def test_zero_denominator_is_unavailable_and_cannot_create_learning_candidate(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    unit = scenario.request.unit_economics_request
    zero = MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 0, HASH)
    for slot in range(1, 6):
        unit = _replace_attribution_metric(
            unit, slot=slot, name="search_clicks", value=zero
        )
        unit = _replace_attribution_metric(
            unit, slot=slot, name="search_impressions", value=zero
        )
    result = build_finance_reconciliation(_finance_request(scenario.request, unit))
    metric = _measurement_metric(result, "search_ctr")
    assert metric.availability is AttributionAvailability.UNAVAILABLE
    assert metric.unavailable_reason is AttributionUnavailableReason.ZERO_DENOMINATOR
    assert metric.value_decimal is None
    assert result.learning_availability is LearningAvailability.UNAVAILABLE
    assert result.learning_unavailable_reason is (
        ReconciliationUnavailableReason.ZERO_DENOMINATOR
    )
    assert result.learning_candidates == ()


def test_immature_cohort_is_unavailable_for_learning(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    unit = scenario.request.unit_economics_request
    attribution_rows = list(unit.attribution_request.article_measurements)
    attribution_rows[0] = replace(
        attribution_rows[0], cohort=CohortStatus(CohortMaturity.IMMATURE, HASH)
    )
    attribution_request = replace(
        unit.attribution_request, article_measurements=tuple(attribution_rows)
    )
    cost_rows = list(unit.cost_observations)
    cost_rows[0] = replace(cost_rows[0], cohort_state=CohortMaturity.IMMATURE)
    unit = replace(
        unit,
        attribution_request=attribution_request,
        attribution_result=build_attribution_run(attribution_request),
        cost_observations=tuple(cost_rows),
    )
    result = build_finance_reconciliation(_finance_request(scenario.request, unit))
    assert result.learning_availability is LearningAvailability.UNAVAILABLE
    assert result.learning_unavailable_reason is (
        ReconciliationUnavailableReason.COHORT_IMMATURE
    )
    assert result.learning_candidates == ()


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("period", ReconciliationUnavailableReason.PERIOD_MISMATCH),
        ("program", ReconciliationUnavailableReason.PROGRAM_MISMATCH),
    ],
)
def test_mixed_program_or_period_is_unavailable_for_learning(
    scenario: RecordedFinanceReconciliationScenario,
    change: str,
    reason: ReconciliationUnavailableReason,
) -> None:
    unit = scenario.request.unit_economics_request
    rows = list(unit.cost_observations)
    if change == "period":
        old = rows[0].period
        rows[0] = replace(
            rows[0],
            period=MeasurementPeriod(
                start_date=old.start_date + timedelta(days=1),
                end_exclusive_date=old.end_exclusive_date + timedelta(days=1),
            ),
        )
    else:
        rows[0] = replace(rows[0], program="OTHER_AFFILIATE_PROGRAM")
    unit = replace(unit, cost_observations=tuple(rows))
    result = build_finance_reconciliation(_finance_request(scenario.request, unit))
    assert result.learning_availability is LearningAvailability.UNAVAILABLE
    assert result.learning_unavailable_reason is reason
    assert result.learning_candidates == ()


def test_missing_slot_and_unverified_batch_are_unavailable_for_learning(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    base = scenario.request.unit_economics_request
    missing = replace(base, cost_observations=base.cost_observations[:-1])
    missing_result = build_finance_reconciliation(
        _finance_request(scenario.request, missing)
    )
    assert missing_result.learning_unavailable_reason is (
        ReconciliationUnavailableReason.MISSING_ARTICLE_SLOTS
    )

    rows = list(base.cost_observations)
    rows[0] = replace(rows[0], verification_state=VerificationState.UNVERIFIED)
    unverified = replace(base, cost_observations=tuple(rows))
    unverified_result = build_finance_reconciliation(
        _finance_request(scenario.request, unverified)
    )
    assert unverified_result.learning_unavailable_reason is (
        ReconciliationUnavailableReason.UNVERIFIED_INPUT
    )
    assert unverified_result.learning_candidates == ()


def test_input_and_dependency_result_tamper_are_rejected(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    request = scenario.request
    object.__setattr__(request, "input_sha256", Sha256Digest("0" * 64))
    assert failure_code(lambda: build_finance_reconciliation(request)) is (
        FinanceReconciliationFailureCode.INPUT_HASH_MISMATCH
    )


def test_dependency_result_mismatch_is_rejected(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    hostile = replace(
        scenario.request.unit_economics_result,
        result_sha256=Sha256Digest("0" * 64),
    )
    request = replace(scenario.request, unit_economics_result=hostile)
    assert failure_code(lambda: build_finance_reconciliation(request)) is (
        FinanceReconciliationFailureCode.DEPENDENCY_RESULT_MISMATCH
    )


def test_hostile_result_shape_fails_with_closed_code(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    result = build_finance_reconciliation(scenario.request)
    hostile = cast(tuple[ReconciliationComparison, ...], (object(),))
    assert failure_code(lambda: replace(result, comparisons=hostile)) is (
        FinanceReconciliationFailureCode.INVALID_ARGUMENT
    )


def test_run_id_conflict_and_nonlocal_or_hostile_runner_are_rejected(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    adapter = RecordedFinanceReconciliationAdapter()
    adapter.run(scenario.request)
    changed = replace(
        scenario.request,
        requested_at=scenario.request.requested_at + timedelta(seconds=1),
    )
    assert failure_code(lambda: adapter.run(changed)) is (
        FinanceReconciliationFailureCode.RUN_ID_CONFLICT
    )
    assert (
        failure_code(
            lambda: FinanceReconciliationService(
                environment=RuntimeEnvironment.PRODUCTION,
                runner=RecordedFinanceReconciliationAdapter(),
            )
        )
        is FinanceReconciliationFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )

    class HostileRunner:
        def run(
            self, request: FinanceReconciliationRunRequest
        ) -> FinanceReconciliationRunResult:
            del request
            return cast(FinanceReconciliationRunResult, object())

    service = FinanceReconciliationService(
        environment=RuntimeEnvironment.CI, runner=HostileRunner()
    )
    assert failure_code(lambda: service.execute(scenario.request)) is (
        FinanceReconciliationFailureCode.RESULT_MISMATCH
    )


def _write_fixture(tmp_path: Path, payload: bytes) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "fixture.json"
    target.write_bytes(payload)
    return target


def test_fixture_duplicate_unknown_float_and_hash_drift_are_rejected(
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
        payload.replace(b'"synthetic": true', b'"synthetic": 1.5', 1),
    )
    for index, variant in enumerate(variants):
        path = _write_fixture(tmp_path / str(index), variant)
        assert failure_code(
            lambda: load_recorded_finance_reconciliation_fixture(
                path.resolve(),
                unit_economics_fixture_path=UNIT_ECONOMICS_FIXTURE.resolve(),
                attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
                contract=measurement_contract,
            )
        ) in {
            FinanceReconciliationFailureCode.FIXTURE_INVALID,
            FinanceReconciliationFailureCode.INPUT_HASH_MISMATCH,
            FinanceReconciliationFailureCode.RESULT_MISMATCH,
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
                lambda: load_recorded_finance_reconciliation_fixture(
                    path.absolute(),
                    unit_economics_fixture_path=UNIT_ECONOMICS_FIXTURE.resolve(),
                    attribution_fixture_path=ATTRIBUTION_FIXTURE.resolve(),
                    contract=measurement_contract,
                )
            )
            is FinanceReconciliationFailureCode.FIXTURE_INVALID
        )


def test_runtime_imports_exclude_provider_editorial_and_public_capabilities() -> None:
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
        ROOT / "python/raos/domain/finance/reconciliation.py",
        ROOT / "python/raos/ports/finance_reconciliation.py",
        ROOT / "python/raos/application/finance/reconciliation.py",
        ROOT / "python/raos/adapters/recorded_finance_reconciliation.py",
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


def test_no_arbitrary_unattributed_reward_allocation_surface(
    scenario: RecordedFinanceReconciliationScenario,
) -> None:
    payload = json.loads(
        build_finance_reconciliation(scenario.request).canonical_bytes()
    )
    attribution = payload["totals"]["attribution_totals"]
    assert attribution["unattributed_confirmed_reward_jpy"] == "79"
    assert attribution["unattributed_reward_allocated_to_articles"] is False
    for candidate in payload["learning_report"]["candidates"]:
        assert "reward" not in json.dumps(candidate, sort_keys=True).lower()
