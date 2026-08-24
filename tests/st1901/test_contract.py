"""Canonical and closed-authority contract checks for ST-1901."""

from __future__ import annotations

import hashlib

import yaml

from conftest import CONTRACT_PATH, REPOSITORY_ROOT
from raos.domain.ai.model_judge_calibration import (
    DEFAULT_MODEL_JUDGE_CALIBRATION_SCOPE,
    MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS,
    MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS,
    MINIMUM_DOUBLE_LABELED_CASES,
    REQUIRED_WEIGHTED_KAPPA_MICROS,
    TRUSTED_RUNTIME_CONTRACT_SHA256,
    CalibrationOutcome,
    ModelJudgeCalibrationScope,
)


def test_contract_preserves_canonical_deferred_status_and_default_disabled() -> None:
    payload = (REPOSITORY_ROOT / CONTRACT_PATH).read_bytes()
    contract = yaml.safe_load(payload)
    document = contract["document"]
    assert document["story_id"] == "ST-1901"
    assert document["mvp"] is False
    assert document["canonical_implementation_status"] == "DEFERRED_POST_MVP"
    assert document["canonical_status_changed"] is False
    assert document["formal_validation"] == "NOT_EXECUTED"
    assert document["authority"] == "NONE"
    assert document["approval"] is None
    assert hashlib.sha256(payload).hexdigest() == TRUSTED_RUNTIME_CONTRACT_SHA256
    assert DEFAULT_MODEL_JUDGE_CALIBRATION_SCOPE == "DISABLED"
    assert tuple(ModelJudgeCalibrationScope) == (
        ModelJudgeCalibrationScope.DISABLED,
        ModelJudgeCalibrationScope.RECORDED_SYNTHETIC_CALIBRATION_ONLY,
    )
    assert contract["feature_scope"] == {
        "default": "DISABLED",
        "closed_states": [
            "DISABLED",
            "RECORDED_SYNTHETIC_CALIBRATION_ONLY",
        ],
        "live_enabled_state_exists": False,
        "activation_interface_exists": False,
        "disabled_fails_before_port_call": True,
        "canonical_deferred_status_preserved": True,
    }


def test_contract_uses_exact_canonical_thresholds_and_refusal_only_outcomes() -> None:
    contract = yaml.safe_load((REPOSITORY_ROOT / CONTRACT_PATH).read_bytes())
    calibration = contract["calibration_contract"]
    assert calibration["minimum_double_labeled_cases"] == MINIMUM_DOUBLE_LABELED_CASES
    assert calibration["required_weighted_kappa_micros"] == (
        REQUIRED_WEIGHTED_KAPPA_MICROS
    )
    assert calibration["maximum_critical_false_pass_rate_micros"] == (
        MAXIMUM_CRITICAL_FALSE_PASS_RATE_MICROS
    )
    assert calibration["maximum_critical_false_fail_rate_micros"] == (
        MAXIMUM_CRITICAL_FALSE_FAIL_RATE_MICROS
    )
    expected = [item.value for item in CalibrationOutcome]
    assert contract["evaluation_contract"]["possible_outcomes"] == expected
    assert (
        contract["evaluation_contract"]["accepted_or_release_ready_outcome_exists"]
        is False
    )
    assert (
        contract["evaluation_contract"]["human_labels_overrideable_by_judge"] is False
    )
    assert contract["evaluation_contract"]["separate_release_decision_required"] is True


def test_contract_has_no_external_or_operational_authority() -> None:
    contract = yaml.safe_load((REPOSITORY_ROOT / CONTRACT_PATH).read_bytes())
    boundary = contract["execution_boundary"]
    assert boundary["provider"] == "NOT_EXECUTED"
    assert boundary["credentials"] == "NOT_USED"
    assert boundary["network"] == "NOT_EXECUTED"
    assert boundary["persistence"] == "NOT_EXECUTED"
    assert boundary["route_or_model_mutation"] == "FORBIDDEN"
    assert boundary["approval"] == "NOT_AUTHORIZED"
    assert boundary["publication"] == "NOT_AUTHORIZED"
    assert boundary["formal_TST-032"] == "NOT_EXECUTED"
    assert boundary["story_acceptance"] is False
    port = contract["port_contract"]
    for field in (
        "provider_sdk_types",
        "provider_name_field",
        "model_name_field",
        "url_field",
        "credential_field",
        "filesystem_path_field",
        "raw_content_field",
        "persistence",
        "retry",
        "fallback",
    ):
        assert port[field] is False
