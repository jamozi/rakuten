"""Deterministic metric and disabled-service behavior for ST-1901."""

from __future__ import annotations

import json

import pytest

from conftest import (
    REPORT_PATH,
    REPOSITORY_ROOT,
    command_for,
    load_batch,
    reader_for,
)
from raos.application.ai.model_judge_calibration import (
    EvaluateRecordedModelJudgeCalibrationService,
    ModelJudgeCalibrationHarness,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.model_judge_calibration import (
    CalibrationOutcome,
    ExecutionStatus,
    MetricStatus,
    ModelJudgeCalibrationError,
    ModelJudgeCalibrationFailureCode,
    ModelJudgeCalibrationScope,
)


def test_recorded_fixture_has_expected_resolved_human_label_profile() -> None:
    batch = load_batch()
    assert len(batch.cases) == 200
    assert batch.actual_human_activity is False
    assert batch.representative_dataset is False
    assert batch.release_eligible is False
    assert sum(item.primary_score != item.secondary_score for item in batch.cases) == 25
    assert sum(item.judge_needs_human_adjudication for item in batch.cases) == 20
    assert all(item.candidate_identity_blinded for item in batch.cases)
    assert not any(item.prompt_author_conflict for item in batch.cases)


def test_metrics_are_exact_deterministic_and_human_labels_remain_authority() -> None:
    batch = load_batch()
    first = ModelJudgeCalibrationHarness().evaluate(batch)
    second = ModelJudgeCalibrationHarness().evaluate(batch)
    assert first == second
    assert first.report_sha256 == second.report_sha256
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.human_score_counts == (40, 40, 40, 40, 40)
    assert first.confusion_matrix == (
        (36, 4, 0, 0, 0),
        (0, 36, 4, 0, 0),
        (0, 0, 36, 4, 0),
        (0, 0, 0, 36, 4),
        (0, 0, 0, 4, 36),
    )
    assert first.critical_positive_count == 40
    assert first.critical_negative_count == 160
    metrics = {item.code: item for item in first.metrics}
    assert metrics["weighted_kappa"].status is MetricStatus.PASS
    assert (
        metrics["weighted_kappa"].numerator,
        metrics["weighted_kappa"].denominator,
    ) == (192, 197)
    assert metrics["weighted_kappa"].value_micros == 974619
    assert metrics["critical_false_pass_rate"].value_micros == 0
    assert metrics["critical_false_fail_rate"].value_micros == 0
    assert first.decision.local_metric_criteria_met is True
    assert first.decision.human_labels_authoritative is True
    assert first.decision.outcome is CalibrationOutcome.REFUSED_UNVERIFIABLE_CALIBRATION
    assert first.decision.authority == "NONE"
    assert first.decision.external_action_count == 0
    assert not any(
        (
            first.decision.provider_call_authorized,
            first.decision.model_call_authorized,
            first.decision.persistence_authorized,
            first.decision.route_mutation_authorized,
            first.decision.model_mutation_authorized,
            first.decision.activation_authorized,
            first.decision.approval_authorized,
            first.decision.publication_authorized,
            first.decision.release_authorized,
            first.decision.production_eligible,
        )
    )
    assert all(
        status is ExecutionStatus.NOT_EXECUTED
        for status in (
            first.actual_human_labeling,
            first.formal_tst_032,
            first.live,
            first.staging,
            first.release,
            first.production,
        )
    )


def test_checked_in_report_is_exact_harness_output() -> None:
    report = ModelJudgeCalibrationHarness().evaluate(load_batch())
    expected = report.canonical_bytes() + b"\n"
    payload = (REPOSITORY_ROOT / REPORT_PATH).read_bytes()
    assert payload == expected
    assert json.loads(payload)["decision"]["outcome"] == (
        "REFUSED_UNVERIFIABLE_CALIBRATION"
    )


def test_default_disabled_fails_before_any_port_read() -> None:
    class ExplodingReader:
        calls = 0

        def read(self, command: object) -> None:
            del command
            self.calls += 1
            raise AssertionError("port must not be called")

    reader = ExplodingReader()
    service = EvaluateRecordedModelJudgeCalibrationService(
        environment=RuntimeEnvironment.CI,
        reader=reader,
    )
    with pytest.raises(ModelJudgeCalibrationError) as captured:
        service.evaluate(command_for(load_batch()))
    assert captured.value.code is ModelJudgeCalibrationFailureCode.FEATURE_DISABLED
    assert reader.calls == 0


def test_explicit_recorded_scope_is_process_local_and_idempotent() -> None:
    batch = load_batch()
    service = EvaluateRecordedModelJudgeCalibrationService(
        environment=RuntimeEnvironment.ENV_DEV,
        scope=ModelJudgeCalibrationScope.RECORDED_SYNTHETIC_CALIBRATION_ONLY,
        reader=reader_for(batch),
    )
    command = command_for(batch)
    assert service.evaluate(command) == service.evaluate(command)
