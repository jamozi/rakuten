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

from raos.adapters.recorded_attribution import (
    RecordedAttributionAdapter,
    load_recorded_attribution_fixture,
)
from raos.application.finance.attribution import AttributionService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.finance.attribution import (
    AllocationReason,
    AttributionAvailability,
    AttributionFailureCode,
    AttributionRunRequest,
    AttributionRunResult,
    CohortMaturity,
    CohortStatus,
    EstimationSignal,
    MeasurementAttributionContract,
    MeasurementPeriod,
    MeasurementValue,
    MeasurementValueState,
    MeasurementVerification,
    UnavailableReason,
    VerificationState,
    allocate_exact_jpy,
    build_attribution_run,
)
from raos.domain.finance.provider_fact_commit import JpyAmount
from raos.domain.ops.object_intake import Sha256Digest

from .conftest import FIXTURE, ROOT, failure_code


HASH = Sha256Digest("f" * 64)


def _replace_article_metric(
    request: AttributionRunRequest,
    *,
    slot: int,
    name: str,
    value: MeasurementValue,
) -> AttributionRunRequest:
    articles = list(request.article_measurements)
    selected = articles[slot - 1]
    metrics = tuple(
        (metric_name, value if metric_name == name else metric_value)
        for metric_name, metric_value in selected.metrics
    )
    articles[slot - 1] = replace(selected, metrics=metrics)
    return replace(request, article_measurements=tuple(articles))


def test_missing_required_signal_is_unavailable_not_zero(scenario: object) -> None:
    request = _replace_article_metric(
        scenario.request,  # type: ignore[attr-defined]
        slot=2,
        name="affiliate_clicks",
        value=MeasurementValue(MeasurementValueState.NOT_OBSERVED, None, None),
    )
    result = build_attribution_run(request)
    assert result.availability is AttributionAvailability.UNAVAILABLE
    assert result.unavailable_reason is UnavailableReason.MISSING_INPUT
    assert all(
        item.attribution_class.value == "UNATTRIBUTED" for item in result.allocations
    )
    assert all(
        item.reason is AllocationReason.UNATTRIBUTED_MISSING_INPUT
        for item in result.allocations
    )
    affiliate_rate = result.measurement_evaluation.metrics[1]
    assert affiliate_rate.availability is AttributionAvailability.UNAVAILABLE
    assert affiliate_rate.value_decimal is None
    assert affiliate_rate.numerator is None
    assert affiliate_rate.denominator is None


def test_unverified_required_signal_is_unavailable(scenario: object) -> None:
    request = _replace_article_metric(
        scenario.request,  # type: ignore[attr-defined]
        slot=1,
        name="direct_confirmed_reward_jpy",
        value=MeasurementValue(MeasurementValueState.UNVERIFIED, 120, HASH),
    )
    result = build_attribution_run(request)
    assert result.unavailable_reason is UnavailableReason.UNVERIFIED_INPUT
    assert all(
        item.reason is AllocationReason.UNATTRIBUTED_UNVERIFIED_INPUT
        for item in result.allocations
    )


@pytest.mark.parametrize(
    ("numerator", "denominator", "metric_index"),
    [
        ("search_clicks", "search_impressions", 0),
        ("affiliate_clicks", "article_views", 1),
        ("confirmed_outcomes", "rejected_outcomes", 3),
        (None, "work_minutes", 4),
    ],
)
def test_zero_denominator_metric_is_unavailable(
    scenario: object, numerator: str | None, denominator: str, metric_index: int
) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    for slot in range(1, 6):
        if numerator is not None:
            request = _replace_article_metric(
                request,
                slot=slot,
                name=numerator,
                value=MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 0, HASH),
            )
        request = _replace_article_metric(
            request,
            slot=slot,
            name=denominator,
            value=MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 0, HASH),
        )
    evaluation = build_attribution_run(request).measurement_evaluation
    metric = evaluation.metrics[metric_index]
    assert metric.availability is AttributionAvailability.UNAVAILABLE
    assert metric.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR
    assert metric.value_decimal is None
    if denominator == "article_views":
        result = build_attribution_run(request)
        assert result.availability is AttributionAvailability.UNAVAILABLE
        assert result.unavailable_reason is UnavailableReason.ZERO_DENOMINATOR


def test_immature_cohort_is_unavailable(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    articles = list(request.article_measurements)
    articles[0] = replace(
        articles[0], cohort=CohortStatus(CohortMaturity.IMMATURE, HASH)
    )
    result = build_attribution_run(
        replace(request, article_measurements=tuple(articles))
    )
    assert result.unavailable_reason is UnavailableReason.COHORT_IMMATURE


def test_mixed_period_is_unavailable(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    period = MeasurementPeriod(
        start_date=request.period.start_date + timedelta(days=1),
        end_exclusive_date=request.period.end_exclusive_date + timedelta(days=1),
    )
    articles = list(request.article_measurements)
    articles[0] = replace(articles[0], period=period)
    result = build_attribution_run(
        replace(request, article_measurements=tuple(articles))
    )
    assert result.unavailable_reason is UnavailableReason.PERIOD_MISMATCH


def test_mixed_program_is_unavailable(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    articles = list(request.article_measurements)
    articles[0] = replace(articles[0], program="OTHER_AFFILIATE_PROGRAM")
    result = build_attribution_run(
        replace(request, article_measurements=tuple(articles))
    )
    assert result.unavailable_reason is UnavailableReason.PROGRAM_MISMATCH


def test_provider_verification_is_required(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    facts = list(request.provider_facts)
    facts[0] = replace(
        facts[0],
        verification=MeasurementVerification(VerificationState.UNVERIFIED, HASH),
    )
    result = build_attribution_run(replace(request, provider_facts=tuple(facts)))
    assert result.unavailable_reason is UnavailableReason.UNVERIFIED_INPUT


def test_measurement_provider_fact_mismatch_fails_closed(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    facts = list(request.provider_facts)
    facts[0] = replace(facts[0], confirmed_reward_jpy=JpyAmount(Decimal(121)))
    assert (
        failure_code(
            lambda: build_attribution_run(replace(request, provider_facts=tuple(facts)))
        )
        is AttributionFailureCode.FACT_MEASUREMENT_MISMATCH
    )


def test_unattributed_program_total_is_never_arbitrarily_allocated(
    scenario: object,
) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    program = replace(
        request.program_measurement,
        unattributed_confirmed_reward_jpy=MeasurementValue(
            MeasurementValueState.OBSERVED_VALUE, 80, HASH
        ),
    )
    assert (
        failure_code(
            lambda: build_attribution_run(replace(request, program_measurement=program))
        )
        is AttributionFailureCode.FACT_MEASUREMENT_MISMATCH
    )


def test_unknown_direct_binding_fails_closed(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    facts = list(request.provider_facts)
    facts[0] = replace(facts[0], direct_article_id="unknown-article")
    assert (
        failure_code(
            lambda: build_attribution_run(replace(request, provider_facts=tuple(facts)))
        )
        is AttributionFailureCode.DIRECT_KEY_INVALID
    )


def test_duplicate_fact_is_rejected(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    assert (
        failure_code(
            lambda: replace(
                request,
                provider_facts=(request.provider_facts[0], request.provider_facts[0]),
            )
        )
        is AttributionFailureCode.FACT_DUPLICATE
    )


def test_duplicate_direct_provider_key_is_rejected(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    facts = list(request.provider_facts)
    facts[1] = replace(
        facts[1],
        direct_article_id=facts[0].direct_article_id,
        direct_key_sha256=facts[0].direct_key_sha256,
        estimation_signal=EstimationSignal.DIRECT_PROVIDER_KEY,
    )
    assert (
        failure_code(lambda: replace(request, provider_facts=tuple(facts)))
        is AttributionFailureCode.FACT_DUPLICATE
    )


def test_input_hash_tamper_is_detected(scenario: object) -> None:
    request = scenario.request  # type: ignore[attr-defined]
    object.__setattr__(request, "input_sha256", Sha256Digest("0" * 64))
    assert (
        failure_code(lambda: build_attribution_run(request))
        is AttributionFailureCode.INPUT_HASH_MISMATCH
    )


def test_same_run_id_with_different_input_is_rejected(scenario: object) -> None:
    first = scenario.request  # type: ignore[attr-defined]
    adapter = RecordedAttributionAdapter()
    adapter.run(first)
    second = replace(first, requested_at=first.requested_at + timedelta(seconds=1))
    assert (
        failure_code(lambda: adapter.run(second))
        is AttributionFailureCode.RUN_ID_CONFLICT
    )


def test_application_rejects_nonlocal_environment_and_hostile_result(
    scenario: object,
) -> None:
    assert (
        failure_code(
            lambda: AttributionService(
                environment=RuntimeEnvironment.PRODUCTION,
                runner=RecordedAttributionAdapter(),
            )
        )
        is AttributionFailureCode.LOCAL_ENVIRONMENT_REQUIRED
    )

    class HostileRunner:
        def run(self, request: AttributionRunRequest) -> AttributionRunResult:
            del request
            return cast(AttributionRunResult, object())

    service = AttributionService(
        environment=RuntimeEnvironment.CI, runner=HostileRunner()
    )
    assert (
        failure_code(lambda: service.execute(scenario.request))  # type: ignore[attr-defined]
        is AttributionFailureCode.RESULT_MISMATCH
    )


@pytest.mark.parametrize(
    "action",
    [
        lambda: JpyAmount(1.0),  # type: ignore[arg-type]
        lambda: JpyAmount(Decimal("1.5")),
        lambda: JpyAmount(Decimal("-1")),
        lambda: allocate_exact_jpy(JpyAmount(Decimal(1)), ((1, 0),)),
        lambda: MeasurementValue(MeasurementValueState.OBSERVED_ZERO, 1, HASH),
        lambda: MeasurementValue(MeasurementValueState.OBSERVED_VALUE, 0, HASH),
    ],
)
def test_invalid_numeric_or_state_shapes_are_rejected(action: object) -> None:
    with pytest.raises(Exception):
        action()  # type: ignore[operator]


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
        payload.replace(b'"value": 1000', b'"value": 1.5', 1),
    )
    for index, variant in enumerate(variants):
        path = _write_fixture(tmp_path / str(index), variant)
        assert failure_code(
            lambda: load_recorded_attribution_fixture(
                path.resolve(), contract=measurement_contract
            )
        ) in {
            AttributionFailureCode.FIXTURE_INVALID,
            AttributionFailureCode.INPUT_HASH_MISMATCH,
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
                lambda: load_recorded_attribution_fixture(
                    path.absolute(), contract=measurement_contract
                )
            )
            is AttributionFailureCode.FIXTURE_INVALID
        )


def test_runtime_imports_exclude_external_and_editorial_capabilities() -> None:
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
        ROOT / "python/raos/domain/finance/attribution.py",
        ROOT / "python/raos/ports/attribution.py",
        ROOT / "python/raos/application/finance/attribution.py",
        ROOT / "python/raos/adapters/recorded_attribution.py",
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
        assert imported.isdisjoint(forbidden_roots)
