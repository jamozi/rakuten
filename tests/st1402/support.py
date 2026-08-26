"""Synthetic exact builders for isolated ST-1402 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_safe_degradation import (  # noqa: E402
    RecordedSafeDegradationAdapter,
    RecordedSafeDegradationFixture,
)
from raos.application.freshness.safe_degradation import (  # noqa: E402
    SafeDegradationService,
    bind_safe_degradation_request,
)
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.freshness.freshness import (  # noqa: E402
    FreshnessEvaluation,
    FreshnessEvaluationRequest,
    FreshnessObservationStatus,
    evaluate_freshness,
)
from raos.domain.freshness.safe_degradation import (  # noqa: E402
    AvailabilityAggregate,
    SafeDegradationRequest,
    decide_safe_degradation,
)


EVALUATED_AT = datetime(2026, 8, 16, 3, 0, tzinfo=timezone.utc)


def freshness_request(
    *,
    freshness_class_id: str = "FRESH-001",
    observation_status: FreshnessObservationStatus = (
        FreshnessObservationStatus.VALIDATED
    ),
    age: timedelta = timedelta(hours=73),
    recommendation_basis_affected: bool = False,
) -> FreshnessEvaluationRequest:
    observed_at: datetime | None = EVALUATED_AT - age
    if observation_status is FreshnessObservationStatus.MISSING:
        observed_at = None
    return FreshnessEvaluationRequest(
        freshness_class_id=freshness_class_id,
        observation_status=observation_status,
        observed_at=observed_at,
        evaluated_at=EVALUATED_AT,
        recommendation_basis_affected=recommendation_basis_affected,
    )


def freshness_result(
    request: FreshnessEvaluationRequest | None = None,
) -> FreshnessEvaluation:
    request_value = freshness_request() if request is None else request
    return evaluate_freshness(request_value)


def bound_request(
    *,
    request: FreshnessEvaluationRequest | None = None,
    result: FreshnessEvaluation | None = None,
    availability_aggregate: AvailabilityAggregate = (
        AvailabilityAggregate.NOT_APPLICABLE
    ),
) -> SafeDegradationRequest:
    request_value = freshness_request() if request is None else request
    result_value = freshness_result(request_value) if result is None else result
    return bind_safe_degradation_request(
        freshness_request=request_value,
        freshness_result=result_value,
        availability_aggregate=availability_aggregate,
    )


def recorded_adapter(
    *,
    request: FreshnessEvaluationRequest | None = None,
    result: FreshnessEvaluation | None = None,
    availability_aggregate: AvailabilityAggregate = (
        AvailabilityAggregate.NOT_APPLICABLE
    ),
) -> RecordedSafeDegradationAdapter:
    safe_request = bound_request(
        request=request,
        result=result,
        availability_aggregate=availability_aggregate,
    )
    decision = decide_safe_degradation(safe_request)
    return RecordedSafeDegradationAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=1,
        fixtures=(
            RecordedSafeDegradationFixture(
                request=safe_request,
                decision=decision,
            ),
        ),
    )


def safe_degradation_service(
    *,
    request: FreshnessEvaluationRequest | None = None,
    result: FreshnessEvaluation | None = None,
    availability_aggregate: AvailabilityAggregate = (
        AvailabilityAggregate.NOT_APPLICABLE
    ),
) -> SafeDegradationService:
    return SafeDegradationService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=recorded_adapter(
            request=request,
            result=result,
            availability_aggregate=availability_aggregate,
        ),
    )
