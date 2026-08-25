"""Sanitized value factories for ST-1908 focused tests."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from raos.adapters.recorded_fine_tuning_evaluation import (
    load_recorded_fine_tuning_bundle,
)
from raos.domain.ai.fine_tuning_evaluation import (
    AggregateModelEvaluation,
    CostEvidence,
    DataGovernanceStatus,
    DatasetRightsStatus,
    EvaluationRole,
    EvidenceStatus,
    FineTuningEvaluationCommand,
    FineTuningScope,
    OptimizationEvidence,
    RecordedFineTuningBundle,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / (
    "changes/st-1908/fixtures/recorded/fine-tuning-candidate.synthetic.v1.json"
)


def fixture_bytes() -> bytes:
    return FIXTURE.read_bytes()


def command(
    *, scope: FineTuningScope = FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY
) -> FineTuningEvaluationCommand:
    content = fixture_bytes()
    return FineTuningEvaluationCommand(
        recording_id="st1908_recorded_evaluation_v1",
        source_sha256=sha256_bytes(content),
        source_bytes=content,
        scope=scope,
    )


def recorded_bundle() -> RecordedFineTuningBundle:
    return load_recorded_fine_tuning_bundle(fixture_bytes())


def verified_research_bundle() -> RecordedFineTuningBundle:
    original = recorded_bundle()
    dataset = replace(
        original.dataset,
        rights_status=DatasetRightsStatus.RECORDED_SYNTHETIC_RIGHTS_REVIEWED,
        license_review_sha256="4" * 64,
        governance_status=(DataGovernanceStatus.RECORDED_SYNTHETIC_GOVERNANCE_REVIEWED),
        data_inventory_sha256="5" * 64,
        retention_policy_sha256="6" * 64,
        deletion_policy_sha256="7" * 64,
        representative=True,
    )
    optimization = OptimizationEvidence(
        status=EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED,
        evidence_sha256="8" * 64,
        prompt_optimization_exhausted=True,
        route_optimization_exhausted=True,
        repeated_error_code="RECORDED_SYNTHETIC_RECURRING_ERROR",
        repeated_error_count=20,
    )
    baseline = AggregateModelEvaluation(
        role=EvaluationRole.BASELINE,
        status=EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED,
        evaluation_sha256="9" * 64,
        model_binding_sha256="a" * 64,
        dataset_sha256=dataset.dataset_sha256,
        holdout_sha256=dataset.holdout_sha256,
        sample_size=150,
        schema_valid_rate_micros=950_000,
        critical_claim_support_rate_micros=930_000,
        human_acceptance_rate_micros=800_000,
        zero_tolerance_failures=0,
    )
    candidate = AggregateModelEvaluation(
        role=EvaluationRole.CANDIDATE,
        status=EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED,
        evaluation_sha256="b" * 64,
        model_binding_sha256="c" * 64,
        dataset_sha256=dataset.dataset_sha256,
        holdout_sha256=dataset.holdout_sha256,
        sample_size=150,
        schema_valid_rate_micros=980_000,
        critical_claim_support_rate_micros=960_000,
        human_acceptance_rate_micros=850_000,
        zero_tolerance_failures=0,
    )
    cost = CostEvidence(
        status=EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED,
        evidence_sha256="d" * 64,
        forecast_sha256="e" * 64,
        workload_requests=10_000,
        baseline_inference_jpy_micros_per_request=10_000,
        candidate_inference_jpy_micros_per_request=5_000,
        training_jpy_micros=5_000_000,
        curation_jpy_micros=5_000_000,
        evaluation_jpy_micros=5_000_000,
        human_labor_jpy_micros=5_000_000,
    )
    return RecordedFineTuningBundle(
        recording_id=original.recording_id,
        fixture_profile=original.fixture_profile,
        task_code=original.task_code,
        candidate_id=original.candidate_id,
        synthetic=original.synthetic,
        actual_training_executed=original.actual_training_executed,
        dataset=dataset,
        optimization=optimization,
        baseline=baseline,
        candidate=candidate,
        cost=cost,
    )


__all__ = (
    "FIXTURE",
    "ROOT",
    "command",
    "fixture_bytes",
    "recorded_bundle",
    "verified_research_bundle",
)
