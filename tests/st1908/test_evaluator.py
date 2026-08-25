"""Deterministic behavior tests for the ST-1908 evaluator."""

from __future__ import annotations

from dataclasses import replace
import json

import pytest

from raos.adapters.recorded_fine_tuning_evaluation import (
    RecordedFineTuningEvidenceSource,
)
from raos.application.ai.fine_tuning_evaluation import (
    FineTuningEvaluationService,
    evaluate_recorded_fine_tuning,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.fine_tuning_evaluation import (
    FineTuningFailure,
    FineTuningFailureCode,
    FineTuningOutcome,
    FineTuningScope,
    GateStatus,
    RecordedFineTuningBundle,
)
from tests.st1908.support import (
    command,
    fixture_bytes,
    recorded_bundle,
    verified_research_bundle,
)


def test_recorded_fixture_is_deterministic_refusal_with_unavailable_not_zero() -> None:
    bundle = recorded_bundle()
    first = evaluate_recorded_fine_tuning(bundle)
    second = evaluate_recorded_fine_tuning(bundle)
    assert first == second
    assert first.canonical_bytes() == second.canonical_bytes()
    assert json.loads(first.canonical_bytes())["report_sha256"] == first.report_sha256
    assert first.outcome is FineTuningOutcome.REFUSED_UNAVAILABLE_EVIDENCE
    assert first.quality_gain_micros is None
    assert first.baseline_lifecycle_cost_jpy_micros is None
    assert first.candidate_lifecycle_cost_jpy_micros is None
    assert first.lifecycle_savings_jpy_micros is None
    statuses = {gate.code: gate.status for gate in first.gates}
    assert statuses["DATASET_RIGHTS"] is GateStatus.UNAVAILABLE
    assert statuses["DATASET_GOVERNANCE"] is GateStatus.UNAVAILABLE
    assert statuses["EVALUATION_BINDING"] is GateStatus.UNAVAILABLE
    assert statuses["COST_PARETO_BENEFIT"] is GateStatus.UNAVAILABLE
    assert statuses["ZERO_TOLERANCE"] is GateStatus.UNAVAILABLE


def test_even_complete_synthetic_projection_has_no_consideration_or_authority() -> None:
    report = evaluate_recorded_fine_tuning(verified_research_bundle())
    statuses = {gate.code: gate.status for gate in report.gates}
    for code in (
        "COST_PARETO_BENEFIT",
        "DATASET_GOVERNANCE",
        "DATASET_RIGHTS",
        "EVALUATION_BINDING",
        "HOLDOUT_INTEGRITY",
        "MINIMUM_HOLDOUT_CASES",
        "PROMPT_ROUTE_OPTIMIZATION",
        "QUALITY_PARETO_BENEFIT",
        "REPRESENTATIVE_DATASET",
        "ZERO_TOLERANCE",
    ):
        assert statuses[code] is GateStatus.PASS
    assert statuses["ACTUAL_FINE_TUNING_EXECUTION"] is GateStatus.UNAVAILABLE
    assert statuses["SEPARATE_RELEASE_DECISION"] is GateStatus.UNAVAILABLE
    assert report.outcome is FineTuningOutcome.REFUSED_UNAVAILABLE_EVIDENCE
    assert report.quality_gain_micros == 30_000
    assert report.baseline_lifecycle_cost_jpy_micros == 100_000_000
    assert report.candidate_lifecycle_cost_jpy_micros == 70_000_000
    assert report.lifecycle_savings_jpy_micros == 30_000_000
    assert report.consideration_candidate is False
    assert report.training_authorized is False
    assert report.provider_call_authorized is False
    assert report.model_or_route_mutation_authorized is False
    assert report.editorial_mutation_authorized is False
    assert report.recommendation_mutation_authorized is False
    assert report.publication_snapshot_mutation_authorized is False
    assert report.publication_authorized is False
    assert report.release_authorized is False
    assert report.production_eligible is False
    assert report.external_action_count == 0


def test_zero_tolerance_failure_precedes_all_other_outcomes() -> None:
    original = verified_research_bundle()
    candidate = replace(original.candidate, zero_tolerance_failures=1)
    bundle = RecordedFineTuningBundle(
        recording_id=original.recording_id,
        fixture_profile=original.fixture_profile,
        task_code=original.task_code,
        candidate_id=original.candidate_id,
        synthetic=original.synthetic,
        actual_training_executed=original.actual_training_executed,
        dataset=original.dataset,
        optimization=original.optimization,
        baseline=original.baseline,
        candidate=candidate,
        cost=original.cost,
    )
    report = evaluate_recorded_fine_tuning(bundle)
    assert report.outcome is FineTuningOutcome.REFUSED_ZERO_TOLERANCE
    assert {gate.code: gate.status for gate in report.gates}["ZERO_TOLERANCE"] is (
        GateStatus.FAIL
    )


def test_quality_or_cost_nonbenefit_is_refused_without_utility_weighting() -> None:
    original = verified_research_bundle()
    candidate = replace(
        original.candidate,
        human_acceptance_rate_micros=original.baseline.human_acceptance_rate_micros,
    )
    bundle = RecordedFineTuningBundle(
        recording_id=original.recording_id,
        fixture_profile=original.fixture_profile,
        task_code=original.task_code,
        candidate_id=original.candidate_id,
        synthetic=original.synthetic,
        actual_training_executed=original.actual_training_executed,
        dataset=original.dataset,
        optimization=original.optimization,
        baseline=original.baseline,
        candidate=candidate,
        cost=original.cost,
    )
    report = evaluate_recorded_fine_tuning(bundle)
    assert report.outcome is FineTuningOutcome.REFUSED_NOT_BENEFICIAL
    assert report.quality_gain_micros is None
    assert report.baseline_lifecycle_cost_jpy_micros is None
    assert report.candidate_lifecycle_cost_jpy_micros is None
    assert report.lifecycle_savings_jpy_micros is None


class _CountingSource:
    def __init__(self, bundle: RecordedFineTuningBundle) -> None:
        self.bundle = bundle
        self.calls = 0

    def read(self, command: object) -> RecordedFineTuningBundle:
        del command
        self.calls += 1
        return self.bundle


def test_disabled_scope_fails_before_port_call() -> None:
    source = _CountingSource(recorded_bundle())
    service = FineTuningEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(FineTuningFailure) as caught:
        service.evaluate(command(scope=FineTuningScope.DISABLED))
    assert caught.value.code is FineTuningFailureCode.FEATURE_DISABLED
    assert source.calls == 0


def test_service_accepts_only_local_environments_and_one_shot_source() -> None:
    source = RecordedFineTuningEvidenceSource(fixture_bytes())
    service = FineTuningEvaluationService(
        environment=RuntimeEnvironment.ENV_DEV,
        source=source,
    )
    assert service.evaluate(command()).outcome is (
        FineTuningOutcome.REFUSED_UNAVAILABLE_EVIDENCE
    )
    with pytest.raises(FineTuningFailure) as caught:
        service.evaluate(command())
    assert caught.value.code is FineTuningFailureCode.SOURCE_EXHAUSTED
    with pytest.raises(FineTuningFailure):
        FineTuningEvaluationService(
            environment=RuntimeEnvironment.STAGING,
            source=RecordedFineTuningEvidenceSource(fixture_bytes()),
        )
