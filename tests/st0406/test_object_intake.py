"""Focused success and pre-I/O authorization denial for ST-0406."""

from __future__ import annotations

from uuid import UUID

import pytest

from .support import (
    CONTENT,
    DIGEST,
    SITE_B,
    authorization_grant,
    intake_descriptor,
    make_recorded_adapter,
    service_for,
    synthetic_source,
)
from raos.adapters.recorded_object_intake import RecordedObjectIntakeAdapter
from raos.application.ops.object_intake import ObjectIntakeService
from raos.domain.ops.object_intake import (
    IntakeOutcome,
    DuplicateStatus,
    ObjectIntakeFailure,
    ObjectIntakeFailureCode,
    QuarantineDisposition,
)


def test_clean_synthetic_csv_remains_quarantined(
    intake_service: ObjectIntakeService,
    recorded_adapter: RecordedObjectIntakeAdapter,
) -> None:
    source = synthetic_source()

    result = intake_service.intake(
        grant=authorization_grant(),
        descriptor=intake_descriptor(),
        source=source,
    )

    assert result.outcome is IntakeOutcome.CLEAN_QUARANTINED
    assert result.quarantine.disposition is QuarantineDisposition.CLEAN_QUARANTINED
    assert source.remaining_bytes == 0
    assert recorded_adapter.quarantine_snapshot()[-1] == result.quarantine
    assert len(recorded_adapter.duplicate_snapshot()) == 1
    assert not hasattr(recorded_adapter, "read")
    assert not hasattr(recorded_adapter, "release")


def test_wrong_site_is_denied_before_source_or_quarantine_io(
    intake_service: ObjectIntakeService,
    recorded_adapter: RecordedObjectIntakeAdapter,
) -> None:
    source = synthetic_source()

    with pytest.raises(ObjectIntakeFailure) as caught:
        intake_service.intake(
            grant=authorization_grant(site_id=SITE_B),
            descriptor=intake_descriptor(),
            source=source,
        )

    assert caught.value.code is ObjectIntakeFailureCode.NOT_AUTHORIZED
    assert source.remaining_bytes == len(CONTENT)
    assert recorded_adapter.quarantine_snapshot() == ()
    assert repr(caught.value) == "ObjectIntakeFailure(code=NOT_AUTHORIZED)"


def test_wrong_action_is_denied_before_source_or_quarantine_io(
    intake_service: ObjectIntakeService,
    recorded_adapter: RecordedObjectIntakeAdapter,
) -> None:
    source = synthetic_source()

    with pytest.raises(ObjectIntakeFailure) as caught:
        intake_service.intake(
            grant=authorization_grant(action="artifact:read"),
            descriptor=intake_descriptor(),
            source=source,
        )

    assert caught.value.code is ObjectIntakeFailureCode.NOT_AUTHORIZED
    assert source.remaining_bytes == len(CONTENT)
    assert recorded_adapter.quarantine_snapshot() == ()


def test_exact_duplicate_still_completes_all_clean_checks_in_quarantine() -> None:
    adapter = make_recorded_adapter()
    first = intake_descriptor()
    assert adapter.record_clean(first, DIGEST).status is DuplicateStatus.NEW
    second = intake_descriptor(intake_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"))

    result = service_for(adapter).intake(
        grant=authorization_grant(),
        descriptor=second,
        source=synthetic_source(),
    )

    assert result.duplicate.status is DuplicateStatus.EXACT_DUPLICATE
    assert result.outcome is IntakeOutcome.CLEAN_QUARANTINED
    assert result.quarantine.disposition is QuarantineDisposition.CLEAN_QUARANTINED
    assert len(adapter.duplicate_snapshot()) == 1
