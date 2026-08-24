"""Typed catalog and pure evaluator coverage for ST-1602 V2."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import sys
from typing import Any, cast

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.domain.ops.slo_alert_runtime_v2 import (  # noqa: E402
    ALERT_IDS,
    RUNBOOK_IDS,
    SLO_IDS,
    AlertConditionState,
    AlertDecision,
    AlertLifecycleState,
    AlertObservation,
    AlertSnapshot,
    AlertTransitionOutcome,
    DataBlockReason,
    HoldVariant,
    RuntimeCatalog,
    SloEvaluationState,
    SloAlertFailure,
    SloMetricWindow,
    alert_instance_key,
    compile_runtime_catalog,
    evaluate_alert,
    evaluate_slo,
)
from scripts import build_st1602_slo_alert_runtime as generator  # noqa: E402


def _catalog() -> RuntimeCatalog:
    return compile_runtime_catalog(generator.runtime_catalog())


def _slo_window(slo_id: str) -> SloMetricWindow:
    fixture = generator.recorded_fixture(generator.runtime_catalog())
    windows = cast(list[dict[str, Any]], fixture["slo_windows"])
    raw = next(item for item in windows if item["slo_id"] == slo_id)
    return SloMetricWindow(
        slo_id=raw["slo_id"],
        source=raw["source"],
        observed_at_epoch_seconds=raw["observed_at_epoch_seconds"],
        evaluated_at_epoch_seconds=raw["evaluated_at_epoch_seconds"],
        fresh_until_epoch_seconds=raw["fresh_until_epoch_seconds"],
        window_start_epoch_seconds=raw["window_start_epoch_seconds"],
        window_end_epoch_seconds=raw["window_end_epoch_seconds"],
        sample_count=raw["sample_count"],
        mature=raw["mature"],
        values=tuple((value["name"], value["value"]) for value in raw["values"]),
    )


def _alert_observation(alert_id: str) -> tuple[str, AlertObservation]:
    fixture = generator.recorded_fixture(generator.runtime_catalog())
    observations = cast(list[dict[str, Any]], fixture["alert_observations"])
    raw = next(item for item in observations if item["alert_id"] == alert_id)
    return raw["instance_id"], AlertObservation(
        alert_id=raw["alert_id"],
        source=raw["source"],
        observed_at_epoch_seconds=raw["observed_at_epoch_seconds"],
        evaluated_at_epoch_seconds=raw["evaluated_at_epoch_seconds"],
        fresh_until_epoch_seconds=raw["fresh_until_epoch_seconds"],
        sample_count=raw["sample_count"],
        mature=raw["mature"],
        condition_state=AlertConditionState(raw["condition_state"]),
        hold_variant=HoldVariant(raw["hold_variant"]),
        condition_started_at_epoch_seconds=raw["condition_started_at_epoch_seconds"],
        cycle_complete=raw["cycle_complete"],
        observation_sha256=raw["observation_sha256"],
    )


def test_exact_14_slo_20_alert_and_20_runbook_inventory_compiles() -> None:
    catalog = _catalog()

    assert tuple(rule.slo_id for rule in catalog.slo_rules) == SLO_IDS
    assert tuple(rule.alert_id for rule in catalog.alert_rules) == ALERT_IDS
    assert catalog.runbook_ids == RUNBOOK_IDS
    assert len({rule.dedup_fingerprint for rule in catalog.alert_rules}) == 20
    assert all(rule.owner_id == "Operations Owner" for rule in catalog.alert_rules)
    assert all(rule.runbook_id in RUNBOOK_IDS for rule in catalog.alert_rules)


def test_runtime_compiler_rejects_condition_route_hold_or_threshold_drift() -> None:
    documents = [
        cast(dict[str, Any], deepcopy(generator.runtime_catalog())) for _ in range(4)
    ]
    documents[0]["alerts"][0]["condition"] = "forged"
    documents[1]["alerts"][0]["route"]["runbook_id"] = "RB-020"
    documents[2]["alerts"][4]["hold"]["variants"][0]["duration_seconds"] = 0
    documents[3]["slos"][0]["evaluation"]["thresholds"][0] = 0
    for document in documents:
        with pytest.raises(SloAlertFailure):
            compile_runtime_catalog(document)


def test_all_recorded_slo_windows_use_the_typed_path_without_attainment_claim() -> None:
    catalog = _catalog()
    evaluations = [
        evaluate_slo(catalog.slo(slo_id), _slo_window(slo_id)) for slo_id in SLO_IDS
    ]

    assert {result.state for result in evaluations} == {SloEvaluationState.PASS}
    assert all(result.reason is DataBlockReason.NONE for result in evaluations)
    assert all(result.actual_measurement_claim is False for result in evaluations)


def test_missing_stale_immature_invalid_and_zero_denominator_are_unavailable() -> None:
    catalog = _catalog()
    base = _slo_window("SLO-001")
    cases = (
        (
            replace(base, values=(("numerator", None), ("denominator", 1))),
            DataBlockReason.MISSING,
        ),
        (replace(base, evaluated_at_epoch_seconds=20_001), DataBlockReason.STALE),
        (replace(base, mature=False), DataBlockReason.IMMATURE),
        (
            replace(base, values=(("numerator", -1), ("denominator", 1))),
            DataBlockReason.INVALID,
        ),
        (
            replace(base, values=(("numerator", 0), ("denominator", 0))),
            DataBlockReason.ZERO_DENOMINATOR,
        ),
    )

    for window, reason in cases:
        result = evaluate_slo(catalog.slo("SLO-001"), window)
        assert result.state is SloEvaluationState.UNAVAILABLE
        assert result.reason is reason


def test_threshold_failure_is_not_converted_to_unavailable_or_zero() -> None:
    catalog = _catalog()
    ratio = replace(
        _slo_window("SLO-001"),
        values=(("numerator", 994_999), ("denominator", 1_000_000)),
    )
    upper = replace(_slo_window("SLO-003"), values=(("p95_milliseconds", 501),))

    assert evaluate_slo(catalog.slo("SLO-001"), ratio).state is SloEvaluationState.FAIL
    assert evaluate_slo(catalog.slo("SLO-003"), upper).state is SloEvaluationState.FAIL


def test_all_twenty_recorded_alerts_reach_firing_with_exact_routes() -> None:
    catalog = _catalog()
    results: list[AlertDecision] = []
    for alert_id in ALERT_IDS:
        instance_id, observation = _alert_observation(alert_id)
        rule = catalog.alert(alert_id)
        results.append(
            evaluate_alert(
                rule,
                alert_instance_key(alert_id, instance_id),
                observation,
                None,
            )
        )

    assert {result.state for result in results} == {AlertLifecycleState.FIRING}
    assert all(result.outcome is AlertTransitionOutcome.FIRING for result in results)
    assert all(result.owner_id == "Operations Owner" for result in results)
    assert all(result.runbook_id in RUNBOOK_IDS for result in results)
    assert all(result.notification_delivery_claim is False for result in results)
    assert all(result.external_action_count == 0 for result in results)


def test_duration_alert_transitions_pending_firing_and_resolved() -> None:
    catalog = _catalog()
    rule = catalog.alert("ALT-005")
    instance_id, base = _alert_observation("ALT-005")
    key = alert_instance_key("ALT-005", instance_id)
    pending_observation = replace(
        base,
        observed_at_epoch_seconds=100,
        evaluated_at_epoch_seconds=200,
        condition_started_at_epoch_seconds=100,
    )
    pending = evaluate_alert(rule, key, pending_observation, None)
    assert pending.state is AlertLifecycleState.PENDING
    assert pending.outcome is AlertTransitionOutcome.PENDING
    snapshot = AlertSnapshot(
        key,
        "ALT-005",
        rule.dedup_fingerprint,
        1,
        pending.state,
        pending.pending_since_epoch_seconds,
        "1" * 64,
        1,
        "2" * 64,
    )
    firing_observation = replace(
        pending_observation,
        observed_at_epoch_seconds=400,
        evaluated_at_epoch_seconds=401,
    )
    firing = evaluate_alert(rule, key, firing_observation, snapshot)
    assert firing.state is AlertLifecycleState.FIRING
    assert firing.outcome is AlertTransitionOutcome.FIRING
    firing_snapshot = replace(
        snapshot,
        current_version=2,
        state=AlertLifecycleState.FIRING,
        pending_since_epoch_seconds=None,
        latest_sequence=2,
        latest_entry_sha256="3" * 64,
    )
    clear = replace(
        firing_observation,
        condition_state=AlertConditionState.CLEAR,
        condition_started_at_epoch_seconds=None,
    )
    resolved = evaluate_alert(rule, key, clear, firing_snapshot)
    assert resolved.state is AlertLifecycleState.RESOLVED
    assert resolved.outcome is AlertTransitionOutcome.RESOLVED


def test_stale_or_unavailable_alert_data_blocks_without_state_change() -> None:
    catalog = _catalog()
    rule = catalog.alert("ALT-001")
    instance_id, base = _alert_observation("ALT-001")
    key = alert_instance_key("ALT-001", instance_id)
    prior = AlertSnapshot(
        key,
        "ALT-001",
        rule.dedup_fingerprint,
        1,
        AlertLifecycleState.FIRING,
        None,
        "1" * 64,
        1,
        "2" * 64,
    )
    result = evaluate_alert(
        rule,
        key,
        replace(base, evaluated_at_epoch_seconds=20_001),
        prior,
    )
    assert result.state is AlertLifecycleState.FIRING
    assert result.outcome is AlertTransitionOutcome.DATA_BLOCKED
    assert result.reason is DataBlockReason.STALE
