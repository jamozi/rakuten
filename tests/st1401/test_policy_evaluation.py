"""Exact provisional-policy and evaluation behavior for ST-1401."""

from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
import hashlib
from io import StringIO
from typing import cast
from zoneinfo import ZoneInfo

import pytest
import yaml

from raos.domain.freshness.freshness import (
    FRESHNESS_MATRIX_BYTES,
    FRESHNESS_MATRIX_SHA256,
    FRESHNESS_OPEN_DECISION_ID,
    FRESHNESS_POLICY_BYTES,
    FRESHNESS_POLICY_DOCUMENT_VERSION,
    FRESHNESS_POLICY_ID,
    FRESHNESS_POLICY_SHA256,
    FRESHNESS_POLICY_VERSION,
    FRESHNESS_THRESHOLD_STATUS,
    FreshnessEvaluationRequest,
    FreshnessFailure,
    FreshnessObservationStatus,
    FreshnessPolicyActivation,
    FreshnessPolicyAuthority,
    FreshnessPolicyClass,
    FreshnessProjectionAction,
    FreshnessReviewAction,
    FreshnessState,
    FreshnessUnknownReason,
    OpenDecisionStatus,
    RecommendationOrderAction,
    evaluate_freshness,
    freshness_policy_classes,
    provisional_freshness_policy_binding,
)

from .support import EVALUATED_AT, JST, REPOSITORY_ROOT, evaluation_request


POLICY_PATH = (
    REPOSITORY_ROOT
    / "contracts/raos-v0.4/contracts/content/"
    / "RAOS_06_freshness_update_policy_v0.1.yaml"
)
MATRIX_PATH = (
    REPOSITORY_ROOT
    / "contracts/raos-v0.4/contracts/content/"
    / "RAOS_06_content_test_matrix_v0.1.csv"
)

SCENARIOS = (
    ("warning前", "DISPLAY"),
    ("warning後block前", "DISPLAY_WITH_WARNING_QUEUE"),
    ("blocking後", "SAFE_DEGRADE"),
    ("取得失敗", "KEEP_LAST_WITH_STALE_STATE_NOT_LATEST"),
    ("JST/UTC境界", "CORRECT"),
    ("再取得成功", "RESTORE_FIELD_AFTER_VALIDATION"),
    ("失効で推薦自動並替え", "FORBIDDEN"),
    ("推薦根拠へ影響", "CREATE_REVIEW_CANDIDATE"),
)


def _policy_document() -> dict[str, object]:
    value = yaml.safe_load(POLICY_PATH.read_bytes())
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _freshness_matrix_rows() -> tuple[dict[str, str], ...]:
    text = MATRIX_PATH.read_bytes().decode("utf-8-sig")
    reader = csv.DictReader(StringIO(text, newline=""))
    return tuple(row for row in reader if row["area"] == "freshness")


def test_exact_installed_policy_and_matrix_byte_bindings_are_preserved() -> None:
    policy_bytes = POLICY_PATH.read_bytes()
    matrix_bytes = MATRIX_PATH.read_bytes()
    assert len(policy_bytes) == FRESHNESS_POLICY_BYTES == 5_428
    assert hashlib.sha256(policy_bytes).hexdigest() == FRESHNESS_POLICY_SHA256
    assert len(matrix_bytes) == FRESHNESS_MATRIX_BYTES == 142_924
    assert hashlib.sha256(matrix_bytes).hexdigest() == FRESHNESS_MATRIX_SHA256

    binding = provisional_freshness_policy_binding()
    assert binding.policy_id == FRESHNESS_POLICY_ID == "RAOS-CONTENT-FRESH-001"
    assert binding.document_version == FRESHNESS_POLICY_DOCUMENT_VERSION == "0.1"
    assert binding.policy_version == FRESHNESS_POLICY_VERSION == "1.0.0"
    assert binding.threshold_status == FRESHNESS_THRESHOLD_STATUS
    assert binding.class_count == 12
    assert binding.authority is (
        FreshnessPolicyAuthority.PROVISIONAL_CANONICAL_SAFE_DEFAULT
    )
    assert binding.activation is (FreshnessPolicyActivation.DISABLED_UNRESOLVED_OD_007)
    assert binding.open_decision_id == FRESHNESS_OPEN_DECISION_ID == "OD-007"
    assert binding.open_decision_status is OpenDecisionStatus.HUMAN_DECISION_REQUIRED
    assert binding.policy_active is False


def test_all_twelve_policy_classes_equal_the_installed_policy_in_source_order() -> None:
    document = _policy_document()
    metadata = cast(dict[str, object], document["document"])
    source_classes = cast(list[dict[str, object]], document["freshness_classes"])
    assert metadata["id"] == FRESHNESS_POLICY_ID
    assert metadata["version"] == FRESHNESS_POLICY_DOCUMENT_VERSION
    assert document["policy_version"] == FRESHNESS_POLICY_VERSION
    assert document["threshold_status"] == FRESHNESS_THRESHOLD_STATUS
    assert tuple(
        (
            item.class_id,
            item.code,
            item.warning_after_hours,
            item.blocking_after_hours,
            item.safe_degradation,
            item.editorial_impact,
        )
        for item in freshness_policy_classes()
    ) == tuple(
        (
            row["id"],
            row["code"],
            row["warning_after_hours"],
            row["blocking_after_hours"],
            row["safe_degradation"],
            row["editorial_impact"],
        )
        for row in source_classes
    )
    assert tuple(item.class_id for item in freshness_policy_classes()) == tuple(
        f"FRESH-{number:03d}" for number in range(1, 13)
    )


def test_exact_ct0791_through_ct0886_matrix_is_twelve_by_eight_parity() -> None:
    rows = _freshness_matrix_rows()
    assert len(rows) == 96
    assert tuple(row["test_id"] for row in rows) == tuple(
        f"CT-{number:04d}" for number in range(791, 887)
    )
    classes = freshness_policy_classes()
    for class_index, policy_class in enumerate(classes):
        group = rows[class_index * 8 : (class_index + 1) * 8]
        assert (
            tuple(row["artifact_or_rule"] for row in group)
            == (policy_class.class_id,) * 8
        )
        assert tuple(
            row["scenario"].removeprefix(f"{policy_class.code}: ") for row in group
        ) == tuple(scenario for scenario, _expected in SCENARIOS)
        assert tuple(row["expected_result"] for row in group) == tuple(
            expected for _scenario, expected in SCENARIOS
        )
        assert tuple(row["priority"] for row in group) == (
            "P1",
            "P1",
            "P0",
            "P0",
            "P1",
            "P1",
            "P0",
            "P1",
        )
        assert all(row["test_type"] == "policy" for row in group)
        assert all(row["implementation_slice"] == "CONT-SLICE-011" for row in group)
        assert all(
            row["requirement_ids"] == "FR-004,FR-011,FR-012,FR-019" for row in group
        )


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
def test_warning_and_blocking_edges_are_inclusive_and_exact(
    policy_class: FreshnessPolicyClass,
) -> None:
    policy = policy_class
    if policy.warning_after_hours > 0:
        before_warning = evaluate_freshness(
            evaluation_request(
                freshness_class_id=policy.class_id,
                age=timedelta(hours=policy.warning_after_hours)
                - timedelta(microseconds=1),
            )
        )
        assert before_warning.state is FreshnessState.FRESH
        assert before_warning.projection_action is FreshnessProjectionAction.DISPLAY
        assert before_warning.stale is False
        assert before_warning.latest is True

    at_warning = evaluate_freshness(
        evaluation_request(
            freshness_class_id=policy.class_id,
            age=timedelta(hours=policy.warning_after_hours),
        )
    )
    if policy.warning_after_hours == policy.blocking_after_hours:
        assert at_warning.state is FreshnessState.CRITICAL
        assert at_warning.projection_action is FreshnessProjectionAction.SAFE_DEGRADE
    else:
        assert at_warning.state is FreshnessState.WARNING
        assert at_warning.projection_action is (
            FreshnessProjectionAction.DISPLAY_WITH_WARNING_QUEUE
        )
        before_block = evaluate_freshness(
            evaluation_request(
                freshness_class_id=policy.class_id,
                age=timedelta(hours=policy.blocking_after_hours)
                - timedelta(microseconds=1),
            )
        )
        assert before_block.state is FreshnessState.WARNING

    at_block = evaluate_freshness(
        evaluation_request(
            freshness_class_id=policy.class_id,
            age=timedelta(hours=policy.blocking_after_hours),
        )
    )
    assert at_block.state is FreshnessState.CRITICAL
    assert at_block.projection_action is FreshnessProjectionAction.SAFE_DEGRADE
    assert at_block.stale is True
    assert at_block.latest is False
    assert at_block.policy_class.safe_degradation == policy.safe_degradation


def test_fresh010_zero_zero_is_immediately_critical_and_never_warning() -> None:
    at_zero = evaluate_freshness(
        evaluation_request(freshness_class_id="FRESH-010", age=timedelta(0))
    )
    assert at_zero.age_microseconds == 0
    assert at_zero.state is FreshnessState.CRITICAL
    assert at_zero.projection_action is FreshnessProjectionAction.SAFE_DEGRADE
    assert at_zero.stale is True
    assert at_zero.latest is False

    future = evaluate_freshness(
        evaluation_request(
            freshness_class_id="FRESH-010", age=-timedelta(microseconds=1)
        )
    )
    assert future.state is FreshnessState.UNKNOWN
    assert future.unknown_reason is FreshnessUnknownReason.FUTURE_OBSERVATION


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
@pytest.mark.parametrize(
    ("status", "reason"),
    (
        (FreshnessObservationStatus.MISSING, FreshnessUnknownReason.MISSING),
        (
            FreshnessObservationStatus.FETCH_FAILED,
            FreshnessUnknownReason.FETCH_FAILED,
        ),
        (
            FreshnessObservationStatus.RECOVERY_UNVALIDATED,
            FreshnessUnknownReason.RECOVERY_NOT_VALIDATED,
        ),
    ),
)
def test_missing_failure_and_unvalidated_recovery_are_unknown_not_latest(
    policy_class: FreshnessPolicyClass,
    status: FreshnessObservationStatus,
    reason: FreshnessUnknownReason,
) -> None:
    policy = policy_class
    request = evaluation_request(
        freshness_class_id=policy.class_id,
        observation_status=status,
        age=timedelta(hours=1),
    )
    result = evaluate_freshness(request)
    assert result.state is FreshnessState.UNKNOWN
    assert result.unknown_reason is reason
    assert result.age_microseconds is None
    assert result.projection_action is (
        FreshnessProjectionAction.KEEP_LAST_WITH_STALE_STATE_NOT_LATEST
    )
    assert result.stale is True
    assert result.latest is False


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
def test_future_validated_observation_is_unknown_not_latest(
    policy_class: FreshnessPolicyClass,
) -> None:
    policy = policy_class
    result = evaluate_freshness(
        evaluation_request(
            freshness_class_id=policy.class_id,
            age=-timedelta(microseconds=1),
        )
    )
    assert result.state is FreshnessState.UNKNOWN
    assert result.unknown_reason is FreshnessUnknownReason.FUTURE_OBSERVATION
    assert result.stale is True
    assert result.latest is False


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
def test_timezone_offsets_compare_by_instant_at_warning_edge(
    policy_class: FreshnessPolicyClass,
) -> None:
    policy = policy_class
    observed_utc = EVALUATED_AT - timedelta(hours=policy.warning_after_hours)
    request = evaluation_request(
        freshness_class_id=policy.class_id,
        evaluated_at=EVALUATED_AT,
        observed_at=observed_utc.astimezone(JST),
        explicit_observed_at=True,
    )
    result = evaluate_freshness(request)
    assert result.age_microseconds == (policy.warning_after_hours * 3_600_000_000)
    assert result.state is (
        FreshnessState.CRITICAL
        if policy.warning_after_hours == policy.blocking_after_hours
        else FreshnessState.WARNING
    )


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
def test_only_validated_noncritical_recovery_restores(
    policy_class: FreshnessPolicyClass,
) -> None:
    policy = policy_class
    recovered = evaluate_freshness(
        evaluation_request(
            freshness_class_id=policy.class_id,
            observation_status=FreshnessObservationStatus.RECOVERY_VALIDATED,
            age=timedelta(0),
        )
    )
    if policy.blocking_after_hours == 0:
        assert recovered.state is FreshnessState.CRITICAL
        assert recovered.projection_action is FreshnessProjectionAction.SAFE_DEGRADE
    else:
        assert recovered.state is FreshnessState.FRESH
        assert recovered.projection_action is (
            FreshnessProjectionAction.RESTORE_FIELD_AFTER_VALIDATION
        )


@pytest.mark.parametrize(
    "policy_class", freshness_policy_classes(), ids=lambda value: value.class_id
)
def test_recommendation_impact_emits_review_candidate_never_reorder(
    policy_class: FreshnessPolicyClass,
) -> None:
    policy = policy_class
    result = evaluate_freshness(
        evaluation_request(
            freshness_class_id=policy.class_id,
            recommendation_basis_affected=True,
        )
    )
    assert result.review_action is FreshnessReviewAction.CREATE_REVIEW_CANDIDATE
    assert result.recommendation_order_action is RecommendationOrderAction.FORBIDDEN
    assert result.category_override_applied is False
    assert result.provider_override_applied is False
    assert result.persistence.value == "NOT_EXECUTED"
    assert result.attestation.value == "NOT_ATTESTED"
    assert result.live_eligible is False


def test_equivalent_utc_and_jst_instants_have_the_same_request_fingerprint() -> None:
    observed_utc = EVALUATED_AT - timedelta(hours=12)
    utc_request = evaluation_request(
        observed_at=observed_utc,
        explicit_observed_at=True,
    )
    jst_request = evaluation_request(
        evaluated_at=EVALUATED_AT.astimezone(JST),
        observed_at=observed_utc.astimezone(JST),
        explicit_observed_at=True,
    )
    assert utc_request.fingerprint == jst_request.fingerprint
    assert (
        evaluate_freshness(utc_request).fingerprint
        == evaluate_freshness(jst_request).fingerprint
    )


def test_fold_one_observation_is_owned_as_exact_utc_before_evaluation() -> None:
    new_york = ZoneInfo("America/New_York")
    ambiguous_observed_at = datetime(2026, 11, 1, 1, 30, tzinfo=new_york, fold=1)
    evaluated_at = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc)
    request = FreshnessEvaluationRequest(
        freshness_class_id="FRESH-001",
        observation_status=FreshnessObservationStatus.VALIDATED,
        observed_at=ambiguous_observed_at,
        evaluated_at=evaluated_at,
        recommendation_basis_affected=False,
    )
    assert request.observed_at == datetime(2026, 11, 1, 6, 30, tzinfo=timezone.utc)
    assert request.observed_at is not ambiguous_observed_at
    assert request.observed_at is not None
    assert request.observed_at.tzinfo is timezone.utc
    assert request.observed_at.fold == 0
    result = evaluate_freshness(request)
    assert result.age_microseconds == 3_600_000_000
    assert result.state is FreshnessState.FRESH


@pytest.mark.parametrize(
    "factory",
    (
        lambda: FreshnessEvaluationRequest(
            freshness_class_id="FRESH-999",
            observation_status=FreshnessObservationStatus.VALIDATED,
            observed_at=EVALUATED_AT,
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=False,
        ),
        lambda: FreshnessEvaluationRequest(
            freshness_class_id="FRESH-001",
            observation_status=FreshnessObservationStatus.VALIDATED,
            observed_at=EVALUATED_AT.replace(tzinfo=None),
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=False,
        ),
        lambda: FreshnessEvaluationRequest(
            freshness_class_id="FRESH-001",
            observation_status=FreshnessObservationStatus.MISSING,
            observed_at=EVALUATED_AT,
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=False,
        ),
        lambda: FreshnessEvaluationRequest(
            freshness_class_id="FRESH-001",
            observation_status=FreshnessObservationStatus.VALIDATED,
            observed_at=EVALUATED_AT,
            evaluated_at=EVALUATED_AT,
            recommendation_basis_affected=cast(bool, 1),
        ),
        lambda: FreshnessEvaluationRequest(
            freshness_class_id="FRESH-001",
            observation_status=FreshnessObservationStatus.VALIDATED,
            observed_at=EVALUATED_AT,
            evaluated_at=cast(datetime, "2026-08-15T12:00:00Z"),
            recommendation_basis_affected=False,
        ),
    ),
)
def test_evaluation_request_rejects_unknown_naive_and_wrong_exact_types(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(FreshnessFailure):
        factory()
