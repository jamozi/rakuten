from __future__ import annotations

from dataclasses import replace

import pytest

from raos.adapters.recorded_live_evaluation import RecordedLiveEvaluationAdapter
from raos.application.ai.live_evaluation import EvaluateRecordedLiveCandidateService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.live_evaluation import (
    AssessmentStatus,
    EvidenceStatus,
    LiveEvaluationError,
    MetricObservation,
    RecordedLiveEvaluationResult,
    ReleaseDecisionOutcome,
    ZeroToleranceObservation,
    evaluate_recorded_live_evidence,
    finalize_candidate_binding,
    finalize_evidence,
    finalize_request,
)


def _available_evidence(
    source: RecordedLiveEvaluationResult,
) -> RecordedLiveEvaluationResult:
    candidate = finalize_candidate_binding(
        replace(
            source.candidate,
            canonical_route_selected=True,
            canonical_model_selected=True,
            canonical_prompt_selected=True,
            live_binding=True,
            binding_sha256="0" * 64,
        )
    )
    source_report = replace(
        source.source_report,
        source_task_code=source.target_task_code,
        suite_code=source.target_suite_code,
        observed_case_count=200,
        observed_splits=tuple(sorted(source.required_splits)),
        dataset_provenance="SANITIZED_RECORDED_EVALUATION",
        human_label_status=EvidenceStatus.AVAILABLE,
        release_eligible=True,
    )
    metrics: list[MetricObservation] = []
    for threshold in source.thresholds:
        if threshold.threshold_micros == 0:
            numerator = 0
        else:
            numerator = threshold.threshold_micros * 200 // 1_000_000
        metrics.append(MetricObservation(threshold.code, numerator, 200))
    zero = tuple(
        ZeroToleranceObservation(item, 0, 200) for item in source.zero_tolerance_classes
    )
    return finalize_evidence(
        replace(
            source,
            candidate=candidate,
            source_report=source_report,
            metric_observations=tuple(metrics),
            zero_tolerance_observations=zero,
            formal_tst_018_executed=True,
            od_015_resolved=True,
            evidence_sha256="0" * 64,
        )
    )


def test_installed_recorded_result_is_exact_refusal_without_pass_coercion(
    recorded_result: RecordedLiveEvaluationResult,
    recorded_adapter: RecordedLiveEvaluationAdapter,
) -> None:
    service = EvaluateRecordedLiveCandidateService(
        environment=RuntimeEnvironment.CI,
        executor=recorded_adapter,
    )
    report = service.evaluate(recorded_result.request)
    assert report.outcome is ReleaseDecisionOutcome.REFUSED_INCOMPLETE_EVIDENCE
    assert report.source_bundle_sha256 == (
        "200c8378d8312133b838f6d167d6b2532f8c28e0d3d1c446c122536b76c355ed"
    )
    assert report.source_report_sha256 == (
        "4458db297cb5f0d324dfde5c22fc4847b5c74e148326c32dfc77ff27aba54962"
    )
    assert all(item.status is AssessmentStatus.UNAVAILABLE for item in report.metrics)
    assert all(
        item.status is AssessmentStatus.UNAVAILABLE for item in report.zero_tolerance
    )
    assert "TARGET_TASK_BINDING_MISMATCH" in report.reasons
    assert "MINIMUM_ADJUDICATED_CASES_UNMET" in report.reasons
    assert "SOURCE_REPORT_REFUSED_INCOMPLETE_EVIDENCE" in report.reasons
    assert "OD_015_EXTERNAL_EVIDENCE_REQUIRED" in report.reasons
    assert not any(
        (
            report.provider_called,
            report.network_used,
            report.credential_read,
            report.route_mutated,
            report.activated,
            report.approved,
            report.published,
            report.released,
            report.production_written,
        )
    )


@pytest.mark.parametrize("denominator", (1, 2, 17, 199))
def test_insufficient_denominator_stays_unavailable(
    recorded_result: RecordedLiveEvaluationResult, denominator: int
) -> None:
    evidence = _available_evidence(recorded_result)
    observations = tuple(
        MetricObservation(item.code, 0, denominator) for item in evidence.thresholds
    )
    insufficient = finalize_evidence(
        replace(
            evidence,
            metric_observations=observations,
            evidence_sha256="0" * 64,
        )
    )
    report = evaluate_recorded_live_evidence(insufficient)
    assert all(item.status is AssessmentStatus.UNAVAILABLE for item in report.metrics)
    assert report.outcome is ReleaseDecisionOutcome.REFUSED_INCOMPLETE_EVIDENCE
    assert "RISK_THRESHOLD_EVIDENCE_UNAVAILABLE" in report.reasons


def test_observed_metric_failure_is_never_rewritten_to_zero_or_pass(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    evidence = _available_evidence(recorded_result)
    first = evidence.metric_observations[0]
    failed = finalize_evidence(
        replace(
            evidence,
            metric_observations=(
                replace(first, numerator=first.denominator),
                *evidence.metric_observations[1:],
            ),
            evidence_sha256="0" * 64,
        )
    )
    report = evaluate_recorded_live_evidence(failed)
    metric = next(item for item in report.metrics if item.code == first.code)
    assert metric.status is AssessmentStatus.FAIL
    assert "RISK_THRESHOLD_FAILURE_OBSERVED" in report.reasons
    assert report.outcome is ReleaseDecisionOutcome.REFUSED_INCOMPLETE_EVIDENCE


def test_zero_tolerance_failure_has_precedence_and_no_waiver(
    recorded_result: RecordedLiveEvaluationResult,
) -> None:
    evidence = _available_evidence(recorded_result)
    first = evidence.zero_tolerance_observations[0]
    failed = finalize_evidence(
        replace(
            evidence,
            zero_tolerance_observations=(
                replace(first, observed_failures=1),
                *evidence.zero_tolerance_observations[1:],
            ),
            evidence_sha256="0" * 64,
        )
    )
    report = evaluate_recorded_live_evidence(failed)
    assert report.zero_tolerance[0].status is AssessmentStatus.FAIL
    assert report.outcome is ReleaseDecisionOutcome.REFUSED_ZERO_TOLERANCE
    assert "ZERO_TOLERANCE_FAILURE_OBSERVED" in report.reasons


def test_unknown_request_and_nonlocal_environment_fail_closed(
    recorded_result: RecordedLiveEvaluationResult,
    recorded_adapter: RecordedLiveEvaluationAdapter,
) -> None:
    changed = finalize_request(
        replace(
            recorded_result.request,
            evaluation_id="unknown-recorded-evaluation",
            request_sha256="0" * 64,
        )
    )
    assert recorded_adapter.execute(changed) is None
    with pytest.raises(LiveEvaluationError):
        EvaluateRecordedLiveCandidateService(
            environment=RuntimeEnvironment.PRODUCTION,
            executor=recorded_adapter,
        )
