"""Fail-closed malformed, insufficient, unbalanced, and leaky paths."""

from __future__ import annotations

from dataclasses import replace
import json
import pickle

import pytest

from .support import (
    CONTRACT_PATH,
    REPOSITORY_ROOT,
    batch_with_cases,
    fixture_bytes,
    load_batch,
    relabel,
    source_bytes,
)
from raos.adapters.recorded_model_judge_calibration import (
    RecordedModelJudgeCalibrationError,
    load_recorded_model_judge_calibration,
)
from raos.application.ai.model_judge_calibration import ModelJudgeCalibrationHarness
from raos.domain.ai.model_judge_calibration import (
    CalibrationMetricResult,
    CalibrationOutcome,
    CalibrationRisk,
    HumanLabelResolution,
    MetricStatus,
    ModelJudgeCalibrationError,
    RecordedHumanLabelBatch,
    canonical_json_bytes,
)


def _load(payload: bytes) -> RecordedHumanLabelBatch:
    return load_recorded_model_judge_calibration(
        fixture_bytes=payload,
        runtime_contract_bytes=(REPOSITORY_ROOT / CONTRACT_PATH).read_bytes(),
        source_bytes=source_bytes(),
    )


@pytest.mark.parametrize(
    "payload",
    [
        b"{}\n",
        b'{"dataset":1,"dataset":2}\n',
        b'{"float":1.0}\n',
        b'{"not":"canonical", "spacing":true}\n',
        b"[]\n",
        b"null\n",
        b"",
    ],
)
def test_malformed_ambiguous_and_noncanonical_fixture_bytes_are_rejected(
    payload: bytes,
) -> None:
    with pytest.raises(RecordedModelJudgeCalibrationError):
        _load(payload)


def test_unknown_or_leaky_fixture_fields_are_rejected_without_echo() -> None:
    document = json.loads(fixture_bytes())
    canary = "SECRET_CANARY_ST1901"
    document["dataset"]["raw_prompt"] = canary
    payload = canonical_json_bytes(document) + b"\n"
    with pytest.raises(RecordedModelJudgeCalibrationError) as captured:
        _load(payload)
    assert canary not in str(captured.value)
    assert canary not in repr(captured.value)
    with pytest.raises(TypeError):
        pickle.dumps(captured.value)


def test_tracked_contract_and_provenance_are_not_digest_authorities() -> None:
    contract = (REPOSITORY_ROOT / CONTRACT_PATH).read_bytes()
    loaded = load_recorded_model_judge_calibration(
        fixture_bytes=fixture_bytes(),
        runtime_contract_bytes=contract + b"\n",
        source_bytes=source_bytes(),
    )
    assert loaded.cases
    sources = source_bytes()
    sources["evaluation_catalog"] += b"\n"
    loaded = load_recorded_model_judge_calibration(
        fixture_bytes=fixture_bytes(),
        runtime_contract_bytes=contract,
        source_bytes=sources,
    )
    assert loaded.cases


def test_ambiguous_or_fabricated_human_label_resolution_is_rejected() -> None:
    label = load_batch().cases[1]
    with pytest.raises(ModelJudgeCalibrationError):
        relabel(
            label,
            secondary_score=(label.primary_score + 1) % 5,
            adjudicated_score=label.primary_score,
            resolution=HumanLabelResolution.AGREED,
            adjudicator_role=None,
        )
    with pytest.raises(ModelJudgeCalibrationError):
        relabel(
            label,
            candidate_identity_blinded=False,
        )
    with pytest.raises(ModelJudgeCalibrationError):
        relabel(label, prompt_author_conflict=True)


def test_insufficient_labels_are_refused_not_zero_filled() -> None:
    original = load_batch()
    reduced = batch_with_cases(original, original.cases[:100])
    report = ModelJudgeCalibrationHarness().evaluate(reduced)
    assert report.case_count == 100
    assert report.decision.outcome is CalibrationOutcome.REFUSED_INSUFFICIENT_EVIDENCE
    assert report.decision.local_metric_criteria_met is False
    assert "MINIMUM_DOUBLE_LABELED_CASES_UNMET" in report.decision.reasons


def test_unbalanced_labels_are_refused() -> None:
    original = load_batch()
    cases = tuple(
        relabel(
            item,
            primary_score=1,
            secondary_score=1,
            adjudicated_score=1,
            resolution=HumanLabelResolution.AGREED,
            adjudicator_role=None,
            human_zero_tolerance=False,
            judge_score=1,
            judge_zero_tolerance=False,
            judge_needs_human_adjudication=False,
            risk=CalibrationRisk.HIGH,
        )
        for item in original.cases
    )
    report = ModelJudgeCalibrationHarness().evaluate(batch_with_cases(original, cases))
    assert report.decision.outcome is CalibrationOutcome.REFUSED_INSUFFICIENT_EVIDENCE
    assert "SCORE_LABELS_UNBALANCED" in report.decision.reasons
    assert "CRITICAL_LABELS_UNBALANCED" in report.decision.reasons


def test_threshold_failure_is_refused_and_never_overrides_human_gold() -> None:
    original = load_batch()
    changed = tuple(
        relabel(
            item,
            judge_score=4 - item.adjudicated_score,
            judge_zero_tolerance=False,
            judge_needs_human_adjudication=(
                4 - item.adjudicated_score != item.adjudicated_score
                or item.human_zero_tolerance
            ),
        )
        for item in original.cases
    )
    report = ModelJudgeCalibrationHarness().evaluate(
        batch_with_cases(original, changed)
    )
    assert report.decision.outcome is CalibrationOutcome.REFUSED_CALIBRATION_THRESHOLDS
    assert report.decision.human_labels_authoritative is True
    assert "CALIBRATION_THRESHOLDS_UNMET" in report.decision.reasons


def test_batch_cannot_be_rebound_to_release_or_actual_human_evidence() -> None:
    batch = load_batch()
    with pytest.raises(ModelJudgeCalibrationError):
        replace(batch, actual_human_activity=True)
    with pytest.raises(ModelJudgeCalibrationError):
        replace(batch, representative_dataset=True)
    with pytest.raises(ModelJudgeCalibrationError):
        replace(batch, release_eligible=True)
    assert len(batch.batch_sha256) == 64


def test_metric_and_report_semantic_drift_are_rejected() -> None:
    with pytest.raises(ModelJudgeCalibrationError):
        CalibrationMetricResult(
            code="weighted_kappa",
            status=MetricStatus.PASS,
            numerator=1,
            denominator=2,
            value_micros=500_000,
            threshold_micros=700_000,
            operator=">=",
        )
    report = ModelJudgeCalibrationHarness().evaluate(load_batch())
    tampered = replace(report, human_score_counts=(39, 41, 40, 40, 40))
    with pytest.raises(ModelJudgeCalibrationError):
        tampered.canonical_bytes()
