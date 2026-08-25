"""Synthetic exact builders for isolated ST-1401 tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_freshness import (  # noqa: E402
    RecordedFreshnessAdapter,
    RecordedFreshnessEvaluationFixture,
    RecordedFreshnessScheduleFixture,
)
from raos.application.freshness.freshness import FreshnessService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.freshness.freshness import (  # noqa: E402
    FreshnessEvaluationRequest,
    FreshnessObservationStatus,
    FreshnessScheduleEntry,
    FreshnessScheduleRequest,
    FreshnessScheduleStatus,
    evaluate_freshness,
    select_due_freshness,
)


UTC = timezone.utc
JST = timezone(timedelta(hours=9))
EVALUATED_AT = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
SCHEDULE_IDS = tuple(
    UUID(f"018f3e90-7b00-7000-8000-{number:012d}") for number in range(301, 311)
)


def synthetic_fingerprint(label: str) -> str:
    return hashlib.sha256(f"st1401:{label}".encode()).hexdigest()


def evaluation_request(
    *,
    freshness_class_id: str = "FRESH-001",
    observation_status: FreshnessObservationStatus = (
        FreshnessObservationStatus.VALIDATED
    ),
    age: timedelta = timedelta(hours=1),
    evaluated_at: datetime = EVALUATED_AT,
    observed_at: datetime | None = None,
    explicit_observed_at: bool = False,
    recommendation_basis_affected: bool = False,
) -> FreshnessEvaluationRequest:
    candidate_observed_at = observed_at
    if not explicit_observed_at:
        candidate_observed_at = (
            None
            if observation_status is FreshnessObservationStatus.MISSING
            else evaluated_at - age
        )
    return FreshnessEvaluationRequest(
        freshness_class_id=freshness_class_id,
        observation_status=observation_status,
        observed_at=candidate_observed_at,
        evaluated_at=evaluated_at,
        recommendation_basis_affected=recommendation_basis_affected,
    )


def schedule_entry(
    ordinal: int,
    *,
    freshness_class_id: str = "FRESH-001",
    status: FreshnessScheduleStatus = FreshnessScheduleStatus.ACTIVE,
    next_due_at: datetime | None = None,
    priority: int = 10,
) -> FreshnessScheduleEntry:
    return FreshnessScheduleEntry(
        schedule_id=SCHEDULE_IDS[ordinal - 1],
        subject_fingerprint=synthetic_fingerprint(f"subject-{ordinal}"),
        freshness_class_id=freshness_class_id,
        status=status,
        next_due_at=(
            EVALUATED_AT - timedelta(minutes=ordinal)
            if next_due_at is None
            else next_due_at
        ),
        priority=priority,
    )


def schedule_request(
    *,
    evaluated_at: datetime = EVALUATED_AT,
    limit: int = 10,
    schedules: tuple[FreshnessScheduleEntry, ...] | None = None,
) -> FreshnessScheduleRequest:
    return FreshnessScheduleRequest(
        evaluated_at=evaluated_at,
        limit=limit,
        schedules=(schedule_entry(1),) if schedules is None else schedules,
    )


def recorded_adapter(
    *,
    evaluation: FreshnessEvaluationRequest | None = None,
    schedule: FreshnessScheduleRequest | None = None,
) -> RecordedFreshnessAdapter:
    evaluation_value = evaluation_request() if evaluation is None else evaluation
    schedule_value = schedule_request() if schedule is None else schedule
    return RecordedFreshnessAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixture_capacity=2,
        evaluation_fixtures=(
            RecordedFreshnessEvaluationFixture(
                request=evaluation_value,
                evaluation=evaluate_freshness(evaluation_value),
            ),
        ),
        schedule_fixtures=(
            RecordedFreshnessScheduleFixture(
                request=schedule_value,
                selection=select_due_freshness(schedule_value),
            ),
        ),
    )


def freshness_service(
    *,
    evaluation: FreshnessEvaluationRequest | None = None,
    schedule: FreshnessScheduleRequest | None = None,
) -> FreshnessService:
    return FreshnessService(
        environment=RuntimeEnvironment.ENV_DEV,
        exchange=recorded_adapter(evaluation=evaluation, schedule=schedule),
    )
