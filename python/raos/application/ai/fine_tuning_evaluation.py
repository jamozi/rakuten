"""Fail-closed ENV-DEV/CI research evaluator for Canonical ST-1908."""

from __future__ import annotations

from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.fine_tuning_evaluation import (
    MAX_COST_JPY_MICROS,
    MINIMUM_HIGH_RISK_HOLDOUT_CASES,
    AggregateModelEvaluation,
    CostEvidence,
    DataGovernanceStatus,
    DatasetRightsStatus,
    EvaluationGate,
    EvidenceStatus,
    FineTuningEvaluationCommand,
    FineTuningEvaluationReport,
    FineTuningFailure,
    FineTuningFailureCode,
    FineTuningOutcome,
    FineTuningScope,
    GateStatus,
    RecordedFineTuningBundle,
    fail_fine_tuning,
    finalize_report,
)
from raos.ports.fine_tuning_evaluation import FineTuningEvidenceSource


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _validated_command(candidate: object) -> FineTuningEvaluationCommand:
    if type(candidate) is not FineTuningEvaluationCommand:
        fail_fine_tuning()
    try:
        return FineTuningEvaluationCommand(
            recording_id=candidate.recording_id,
            source_sha256=candidate.source_sha256,
            source_bytes=candidate.source_bytes,
            scope=candidate.scope,
            method_version=candidate.method_version,
            parser_version=candidate.parser_version,
            st0707_contract_sha256=candidate.st0707_contract_sha256,
            st0707_manifest_sha256=candidate.st0707_manifest_sha256,
            st0707_suite_sha256=candidate.st0707_suite_sha256,
            st0707_holdout_sha256=candidate.st0707_holdout_sha256,
        )
    except FineTuningFailure:
        raise
    except Exception:
        fail_fine_tuning()


def _evaluation_available(value: AggregateModelEvaluation) -> bool:
    return value.status is EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED


def _quality_projection(
    baseline: AggregateModelEvaluation,
    candidate: AggregateModelEvaluation,
) -> tuple[GateStatus, int | None]:
    if not _evaluation_available(baseline) or not _evaluation_available(candidate):
        return GateStatus.UNAVAILABLE, None
    baseline_values = (
        baseline.schema_valid_rate_micros,
        baseline.critical_claim_support_rate_micros,
        baseline.human_acceptance_rate_micros,
    )
    candidate_values = (
        candidate.schema_valid_rate_micros,
        candidate.critical_claim_support_rate_micros,
        candidate.human_acceptance_rate_micros,
    )
    if any(value is None for value in baseline_values + candidate_values):
        fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
    base = cast(tuple[int, int, int], baseline_values)
    fine_tuned = cast(tuple[int, int, int], candidate_values)
    gains = tuple(
        after - before for before, after in zip(base, fine_tuned, strict=True)
    )
    if any(gain <= 0 for gain in gains):
        return GateStatus.FAIL, None
    return GateStatus.PASS, min(gains)


def _cost_projection(
    value: CostEvidence,
) -> tuple[GateStatus, int | None, int | None, int | None]:
    if value.status is EvidenceStatus.UNAVAILABLE:
        return GateStatus.UNAVAILABLE, None, None, None
    raw = (
        value.workload_requests,
        value.baseline_inference_jpy_micros_per_request,
        value.candidate_inference_jpy_micros_per_request,
        value.training_jpy_micros,
        value.curation_jpy_micros,
        value.evaluation_jpy_micros,
        value.human_labor_jpy_micros,
    )
    if any(item is None for item in raw):
        fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
    (
        workload,
        baseline_per_request,
        candidate_per_request,
        training,
        curation,
        evaluation,
        human_labor,
    ) = cast(tuple[int, int, int, int, int, int, int], raw)
    baseline_total = workload * baseline_per_request
    candidate_total = (
        workload * candidate_per_request
        + training
        + curation
        + evaluation
        + human_labor
    )
    if baseline_total > MAX_COST_JPY_MICROS or candidate_total > MAX_COST_JPY_MICROS:
        fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
    if candidate_total >= baseline_total:
        return GateStatus.FAIL, baseline_total, candidate_total, None
    return (
        GateStatus.PASS,
        baseline_total,
        candidate_total,
        baseline_total - candidate_total,
    )


def evaluate_recorded_fine_tuning(
    bundle: RecordedFineTuningBundle,
) -> FineTuningEvaluationReport:
    """Evaluate sanitized aggregate metadata with no training/release authority."""

    if type(bundle) is not RecordedFineTuningBundle:
        fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
    bundle.require_valid()
    dataset = bundle.dataset
    rights_status = (
        GateStatus.PASS
        if dataset.rights_status
        is DatasetRightsStatus.RECORDED_SYNTHETIC_RIGHTS_REVIEWED
        else GateStatus.UNAVAILABLE
    )
    governance_status = (
        GateStatus.PASS
        if dataset.governance_status
        is DataGovernanceStatus.RECORDED_SYNTHETIC_GOVERNANCE_REVIEWED
        else GateStatus.UNAVAILABLE
    )
    optimization_status = (
        GateStatus.PASS
        if bundle.optimization.status is EvidenceStatus.RECORDED_SYNTHETIC_VERIFIED
        else GateStatus.UNAVAILABLE
    )
    evaluation_status = (
        GateStatus.PASS
        if _evaluation_available(bundle.baseline)
        and _evaluation_available(bundle.candidate)
        else GateStatus.UNAVAILABLE
    )
    zero_status = GateStatus.UNAVAILABLE
    if evaluation_status is GateStatus.PASS:
        zero_counts = (
            bundle.baseline.zero_tolerance_failures,
            bundle.candidate.zero_tolerance_failures,
        )
        if any(value is None for value in zero_counts):
            fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
        zero_status = (
            GateStatus.PASS
            if all(value == 0 for value in zero_counts)
            else GateStatus.FAIL
        )
    quality_status, quality_gain = _quality_projection(
        bundle.baseline, bundle.candidate
    )
    cost_status, baseline_cost, candidate_cost, savings = _cost_projection(bundle.cost)
    gates = tuple(
        sorted(
            (
                EvaluationGate("ACTUAL_FINE_TUNING_EXECUTION", GateStatus.UNAVAILABLE),
                EvaluationGate("COST_PARETO_BENEFIT", cost_status),
                EvaluationGate("DATASET_GOVERNANCE", governance_status),
                EvaluationGate("DATASET_RIGHTS", rights_status),
                EvaluationGate("EVALUATION_BINDING", evaluation_status),
                EvaluationGate(
                    "HOLDOUT_INTEGRITY",
                    GateStatus.PASS
                    if dataset.holdout_locked and not dataset.holdout_compromised
                    else GateStatus.FAIL,
                ),
                EvaluationGate(
                    "MINIMUM_HOLDOUT_CASES",
                    GateStatus.PASS
                    if dataset.case_count >= MINIMUM_HIGH_RISK_HOLDOUT_CASES
                    else GateStatus.FAIL,
                ),
                EvaluationGate("PROMPT_ROUTE_OPTIMIZATION", optimization_status),
                EvaluationGate("QUALITY_PARETO_BENEFIT", quality_status),
                EvaluationGate(
                    "REPRESENTATIVE_DATASET",
                    GateStatus.PASS if dataset.representative else GateStatus.FAIL,
                ),
                EvaluationGate("SEPARATE_RELEASE_DECISION", GateStatus.UNAVAILABLE),
                EvaluationGate("ZERO_TOLERANCE", zero_status),
            ),
            key=lambda gate: gate.code,
        )
    )
    status_by_code = {gate.code: gate.status for gate in gates}
    reasons = {
        "ACTUAL_FINE_TUNING_NOT_EXECUTED",
        "FORMAL_TST_032_NOT_EXECUTED",
        "RECORDED_SYNTHETIC_RESEARCH_ONLY",
        "SEPARATE_RELEASE_DECISION_REQUIRED",
    }
    for code, status in status_by_code.items():
        if status is GateStatus.UNAVAILABLE:
            reasons.add(f"{code}_UNAVAILABLE")
        elif status is GateStatus.FAIL:
            reasons.add(f"{code}_FAILED")
    outcome = FineTuningOutcome.REFUSED_UNAVAILABLE_EVIDENCE
    if zero_status is GateStatus.FAIL:
        outcome = FineTuningOutcome.REFUSED_ZERO_TOLERANCE
    elif quality_status is GateStatus.FAIL or cost_status is GateStatus.FAIL:
        outcome = FineTuningOutcome.REFUSED_NOT_BENEFICIAL
    provisional = FineTuningEvaluationReport(
        bundle_sha256=bundle.bundle_sha256,
        outcome=outcome,
        reasons=tuple(sorted(reasons)),
        gates=gates,
        quality_gain_micros=(
            quality_gain
            if quality_gain is not None
            and baseline_cost is not None
            and candidate_cost is not None
            and savings is not None
            else None
        ),
        baseline_lifecycle_cost_jpy_micros=(
            baseline_cost
            if quality_gain is not None
            and candidate_cost is not None
            and savings is not None
            else None
        ),
        candidate_lifecycle_cost_jpy_micros=(
            candidate_cost
            if quality_gain is not None
            and baseline_cost is not None
            and savings is not None
            else None
        ),
        lifecycle_savings_jpy_micros=(
            savings
            if quality_gain is not None
            and baseline_cost is not None
            and candidate_cost is not None
            else None
        ),
        report_sha256="0" * 64,
    )
    return finalize_report(provisional)


@final
class FineTuningEvaluationService:
    """Read one caller recording only when the closed local scope is explicit."""

    __slots__ = ("_source",)

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        source: FineTuningEvidenceSource,
    ) -> None:
        try:
            implements = isinstance(
                cast(object, source), FineTuningEvidenceSource
            ) and callable(getattr(source, "read", None))
        except Exception:
            implements = False
        if not _local_environment(environment) or not implements:
            fail_fine_tuning()
        self._source = source

    def evaluate(
        self, command: FineTuningEvaluationCommand
    ) -> FineTuningEvaluationReport:
        normalized = _validated_command(command)
        if normalized.scope is not FineTuningScope.RECORDED_SYNTHETIC_EVALUATION_ONLY:
            fail_fine_tuning(FineTuningFailureCode.FEATURE_DISABLED)
        observed: object = None
        try:
            observed = self._source.read(normalized)
        except FineTuningFailure:
            raise
        except Exception:
            fail_fine_tuning(FineTuningFailureCode.SOURCE_UNAVAILABLE)
        if type(observed) is not RecordedFineTuningBundle:
            fail_fine_tuning(FineTuningFailureCode.SOURCE_RESULT_INVALID)
        return evaluate_recorded_fine_tuning(observed)


__all__ = (
    "FineTuningEvaluationService",
    "evaluate_recorded_fine_tuning",
)
