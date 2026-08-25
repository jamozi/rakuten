"""Deterministic refusal-only ST-1901 model-Judge calibration harness."""

from __future__ import annotations

from fractions import Fraction
from typing import cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.model_judge_calibration import (
    MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS,
    MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS,
    METRIC_SCALE,
    MINIMUM_CASES_PER_SCORE,
    MINIMUM_CRITICAL_NEGATIVE_CASES,
    MINIMUM_CRITICAL_POSITIVE_CASES,
    MINIMUM_DOUBLE_LABELED_CASES,
    REQUIRED_WEIGHTED_KAPPA_MICROS,
    CalibrationDecision,
    CalibrationGate,
    CalibrationMetricResult,
    CalibrationOutcome,
    GateStatus,
    HumanLabelResolution,
    JudgeCalibrationReadCommand,
    MetricStatus,
    ModelJudgeCalibrationFailureCode,
    ModelJudgeCalibrationReport,
    ModelJudgeCalibrationScope,
    RecordedHumanJudgeLabel,
    RecordedHumanLabelBatch,
    fail_calibration,
    finalize_report,
)
from raos.ports.model_judge_calibration import RecordedHumanLabelReader


def _local_environment(value: object) -> bool:
    return type(value) is RuntimeEnvironment and value in {
        RuntimeEnvironment.ENV_DEV,
        RuntimeEnvironment.CI,
    }


def _micros(value: Fraction) -> int:
    return value.numerator * METRIC_SCALE // value.denominator


def _quadratic_weighted_kappa(
    matrix: tuple[tuple[int, ...], ...],
) -> Fraction | None:
    total = sum(sum(row) for row in matrix)
    if total <= 0:
        return None
    rows = tuple(sum(row) for row in matrix)
    columns = tuple(sum(matrix[row][column] for row in range(5)) for column in range(5))
    observed_disagreement = sum(
        (
            Fraction((row - column) ** 2, 16) * matrix[row][column]
            for row in range(5)
            for column in range(5)
        ),
        start=Fraction(0),
    ) / Fraction(total)
    expected_disagreement = sum(
        (
            Fraction((row - column) ** 2, 16) * rows[row] * columns[column]
            for row in range(5)
            for column in range(5)
        ),
        start=Fraction(0),
    ) / Fraction(total * total)
    if expected_disagreement == 0:
        return None
    value = Fraction(1) - observed_disagreement / expected_disagreement
    if value < -1 or value > 1:
        return None
    return value


def _unavailable_metric(
    code: str, *, threshold_micros: int, operator: str
) -> CalibrationMetricResult:
    return CalibrationMetricResult(
        code=code,
        status=MetricStatus.UNAVAILABLE,
        numerator=None,
        denominator=None,
        value_micros=None,
        threshold_micros=threshold_micros,
        operator=operator,
    )


def _fraction_metric(
    code: str,
    *,
    value: Fraction | None,
    threshold_micros: int,
    operator: str,
) -> CalibrationMetricResult:
    if value is None:
        return _unavailable_metric(
            code, threshold_micros=threshold_micros, operator=operator
        )
    threshold = Fraction(threshold_micros, METRIC_SCALE)
    passed = value >= threshold if operator == ">=" else value <= threshold
    return CalibrationMetricResult(
        code=code,
        status=MetricStatus.PASS if passed else MetricStatus.FAIL,
        numerator=value.numerator,
        denominator=value.denominator,
        value_micros=_micros(value),
        threshold_micros=threshold_micros,
        operator=operator,
    )


def _matrix(
    cases: tuple[RecordedHumanJudgeLabel, ...],
) -> tuple[
    tuple[int, int, int, int, int],
    tuple[int, int, int, int, int],
    tuple[int, int, int, int, int],
    tuple[int, int, int, int, int],
    tuple[int, int, int, int, int],
]:
    rows = [[0 for _ in range(5)] for _ in range(5)]
    for item in cases:
        rows[item.adjudicated_score][item.judge_score] += 1
    return cast(
        tuple[
            tuple[int, int, int, int, int],
            tuple[int, int, int, int, int],
            tuple[int, int, int, int, int],
            tuple[int, int, int, int, int],
            tuple[int, int, int, int, int],
        ],
        tuple(tuple(row) for row in rows),
    )


@final
class ModelJudgeCalibrationHarness:
    """Compute local metrics while retaining a refusal-only authority boundary."""

    __slots__ = ()

    def evaluate(self, batch: RecordedHumanLabelBatch) -> ModelJudgeCalibrationReport:
        if type(batch) is not RecordedHumanLabelBatch:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        batch.require_valid()
        cases = batch.cases
        matrix = _matrix(cases)
        score_counts = cast(
            tuple[int, int, int, int, int],
            tuple(sum(row) for row in matrix),
        )
        critical_positive = sum(item.human_zero_tolerance for item in cases)
        critical_negative = len(cases) - critical_positive
        false_passes = sum(
            item.human_zero_tolerance and not item.judge_zero_tolerance
            for item in cases
        )
        false_fails = sum(
            not item.human_zero_tolerance and item.judge_zero_tolerance
            for item in cases
        )
        kappa = _quadratic_weighted_kappa(matrix)
        false_pass_rate = (
            Fraction(false_passes, critical_positive) if critical_positive else None
        )
        false_fail_rate = (
            Fraction(false_fails, critical_negative) if critical_negative else None
        )
        metrics = tuple(
            sorted(
                (
                    _fraction_metric(
                        "critical_false_fail_rate",
                        value=false_fail_rate,
                        threshold_micros=(MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS),
                        operator="<=",
                    ),
                    _fraction_metric(
                        "critical_false_pass_rate",
                        value=false_pass_rate,
                        threshold_micros=(MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS),
                        operator="<=",
                    ),
                    _fraction_metric(
                        "weighted_kappa",
                        value=kappa,
                        threshold_micros=REQUIRED_WEIGHTED_KAPPA_MICROS,
                        operator=">=",
                    ),
                ),
                key=lambda item: item.code,
            )
        )
        metric_by_code = {item.code: item for item in metrics}
        sample_complete = len(cases) >= MINIMUM_DOUBLE_LABELED_CASES
        scores_balanced = all(
            count >= MINIMUM_CASES_PER_SCORE for count in score_counts
        )
        critical_balanced = (
            critical_positive >= MINIMUM_CRITICAL_POSITIVE_CASES
            and critical_negative >= MINIMUM_CRITICAL_NEGATIVE_CASES
        )
        labels_resolved = all(
            item.resolution
            in {HumanLabelResolution.AGREED, HumanLabelResolution.ADJUDICATED}
            for item in cases
        )
        thresholds_met = all(item.status is MetricStatus.PASS for item in metrics)
        local_criteria_met = (
            sample_complete
            and scores_balanced
            and critical_balanced
            and labels_resolved
            and thresholds_met
        )

        gates = tuple(
            sorted(
                (
                    CalibrationGate("ACTUAL_HUMAN_PROVENANCE", GateStatus.UNAVAILABLE),
                    CalibrationGate(
                        "CRITICAL_FALSE_FAIL",
                        GateStatus.PASS
                        if metric_by_code["critical_false_fail_rate"].status
                        is MetricStatus.PASS
                        else GateStatus.FAIL
                        if metric_by_code["critical_false_fail_rate"].status
                        is MetricStatus.FAIL
                        else GateStatus.UNAVAILABLE,
                    ),
                    CalibrationGate(
                        "CRITICAL_FALSE_PASS",
                        GateStatus.PASS
                        if metric_by_code["critical_false_pass_rate"].status
                        is MetricStatus.PASS
                        else GateStatus.FAIL
                        if metric_by_code["critical_false_pass_rate"].status
                        is MetricStatus.FAIL
                        else GateStatus.UNAVAILABLE,
                    ),
                    CalibrationGate(
                        "CRITICAL_LABEL_BALANCE",
                        GateStatus.PASS if critical_balanced else GateStatus.FAIL,
                    ),
                    CalibrationGate(
                        "DOUBLE_LABELED_CASES",
                        GateStatus.PASS if sample_complete else GateStatus.FAIL,
                    ),
                    CalibrationGate(
                        "HUMAN_LABEL_RESOLUTION",
                        GateStatus.PASS if labels_resolved else GateStatus.FAIL,
                    ),
                    CalibrationGate("RECORDED_LABEL_SHAPE", GateStatus.PASS),
                    CalibrationGate("REPRESENTATIVE_DATASET", GateStatus.FAIL),
                    CalibrationGate("RESOLVED_MODEL_BINDING", GateStatus.UNAVAILABLE),
                    CalibrationGate(
                        "SCORE_LABEL_BALANCE",
                        GateStatus.PASS if scores_balanced else GateStatus.FAIL,
                    ),
                    CalibrationGate(
                        "SEPARATE_RELEASE_DECISION", GateStatus.UNAVAILABLE
                    ),
                    CalibrationGate(
                        "WEIGHTED_KAPPA",
                        GateStatus.PASS
                        if metric_by_code["weighted_kappa"].status is MetricStatus.PASS
                        else GateStatus.FAIL
                        if metric_by_code["weighted_kappa"].status is MetricStatus.FAIL
                        else GateStatus.UNAVAILABLE,
                    ),
                ),
                key=lambda item: item.code,
            )
        )

        reasons = {
            "ACTUAL_HUMAN_PROVENANCE_UNAVAILABLE",
            "FORMAL_TST_032_NOT_EXECUTED",
            "REPRESENTATIVE_DATASET_UNAVAILABLE",
            "RESOLVED_MODEL_BINDING_UNAVAILABLE",
            "SEPARATE_RELEASE_DECISION_REQUIRED",
            "SYNTHETIC_FIXTURE_NOT_RELEASE_EVIDENCE",
        }
        if not sample_complete:
            reasons.add("MINIMUM_DOUBLE_LABELED_CASES_UNMET")
        if not scores_balanced:
            reasons.add("SCORE_LABELS_UNBALANCED")
        if not critical_balanced:
            reasons.add("CRITICAL_LABELS_UNBALANCED")
        if not labels_resolved:
            reasons.add("HUMAN_LABELS_AMBIGUOUS")
        if not thresholds_met:
            reasons.add("CALIBRATION_THRESHOLDS_UNMET")

        if not (
            sample_complete
            and scores_balanced
            and critical_balanced
            and labels_resolved
        ):
            outcome = CalibrationOutcome.REFUSED_INSUFFICIENT_EVIDENCE
        elif not thresholds_met:
            outcome = CalibrationOutcome.REFUSED_CALIBRATION_THRESHOLDS
        else:
            outcome = CalibrationOutcome.REFUSED_UNVERIFIABLE_CALIBRATION
        decision = CalibrationDecision(
            outcome=outcome,
            reasons=tuple(sorted(reasons)),
            local_metric_criteria_met=local_criteria_met,
        )
        provisional = ModelJudgeCalibrationReport(
            batch_sha256=batch.batch_sha256,
            fixture_file_sha256=batch.fixture_file_sha256,
            dataset_sha256=batch.dataset_sha256,
            calibration_scope_sha256=batch.calibration_scope_sha256,
            case_count=len(cases),
            human_score_counts=score_counts,
            confusion_matrix=matrix,
            human_reviewer_disagreement_count=sum(
                item.resolution is HumanLabelResolution.ADJUDICATED for item in cases
            ),
            judge_human_disagreement_count=sum(
                item.judge_needs_human_adjudication for item in cases
            ),
            critical_positive_count=critical_positive,
            critical_negative_count=critical_negative,
            metrics=metrics,
            gates=gates,
            decision=decision,
            report_sha256="0" * 64,
        )
        return finalize_report(provisional)


@final
class EvaluateRecordedModelJudgeCalibrationService:
    """Read one local fixture only after an explicit non-default safe scope."""

    __slots__ = ("_reader", "_scope")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        reader: RecordedHumanLabelReader,
        scope: ModelJudgeCalibrationScope = ModelJudgeCalibrationScope.DISABLED,
    ) -> None:
        try:
            implements = isinstance(cast(object, reader), RecordedHumanLabelReader)
        except Exception:
            implements = False
        if (
            not _local_environment(environment)
            or type(scope) is not ModelJudgeCalibrationScope
            or not implements
        ):
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_COMMAND)
        self._scope = scope
        self._reader = reader

    def evaluate(
        self, command: JudgeCalibrationReadCommand
    ) -> ModelJudgeCalibrationReport:
        if self._scope is ModelJudgeCalibrationScope.DISABLED:
            fail_calibration(ModelJudgeCalibrationFailureCode.FEATURE_DISABLED)
        if type(command) is not JudgeCalibrationReadCommand:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_COMMAND)
        try:
            batch = self._reader.read(command)
        except Exception:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        if type(batch) is not RecordedHumanLabelBatch:
            fail_calibration(ModelJudgeCalibrationFailureCode.INVALID_BATCH)
        return ModelJudgeCalibrationHarness().evaluate(batch)


__all__ = [
    "EvaluateRecordedModelJudgeCalibrationService",
    "ModelJudgeCalibrationHarness",
]
