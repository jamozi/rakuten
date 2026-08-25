from __future__ import annotations

import pytest
from typing import cast

from raos.adapters.publishing.recorded_partial_auto_publication import (
    RecordedPartialAutoPublicationSource,
)
from raos.application.publishing.partial_auto_publication import (
    PartialAutoPublicationEvaluationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.publishing.partial_auto_publication import (
    PartialAutoPublicationCommand,
    PartialAutoPublicationFailure,
    PartialAutoPublicationFailureCode,
    PartialAutoPublicationOutcome,
    PartialAutoPublicationScope,
    RecordedPartialAutoPublicationBundle,
)
from tests.st1903.support import command_for


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(
        self, command: PartialAutoPublicationCommand
    ) -> RecordedPartialAutoPublicationBundle:
        del command
        self.calls += 1
        return cast(RecordedPartialAutoPublicationBundle, object())


class _RaisingSource:
    def read(
        self, command: PartialAutoPublicationCommand
    ) -> RecordedPartialAutoPublicationBundle:
        del command
        raise OSError("hostile source details")


def test_disabled_fails_before_port_call(fixture_bytes: bytes) -> None:
    source = _CountingSource()
    service = PartialAutoPublicationEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        service.evaluate(
            command_for(fixture_bytes, scope=PartialAutoPublicationScope.DISABLED)
        )
    assert caught.value.code is PartialAutoPublicationFailureCode.FEATURE_DISABLED
    assert source.calls == 0


def test_only_dev_and_ci_are_accepted(fixture_bytes: bytes) -> None:
    with pytest.raises(PartialAutoPublicationFailure):
        PartialAutoPublicationEvaluationService(
            environment=RuntimeEnvironment.STAGING,
            source=RecordedPartialAutoPublicationSource(fixture_bytes),
        )


def test_recorded_service_returns_refusal(fixture_bytes: bytes) -> None:
    service = PartialAutoPublicationEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=RecordedPartialAutoPublicationSource(fixture_bytes),
    )
    report = service.evaluate(command_for(fixture_bytes))
    assert report.outcome is PartialAutoPublicationOutcome.REFUSED_DEPENDENCY_BLOCKED


def test_hostile_source_failure_is_sanitized(fixture_bytes: bytes) -> None:
    service = PartialAutoPublicationEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=_RaisingSource(),
    )
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        service.evaluate(command_for(fixture_bytes))
    assert caught.value.code is PartialAutoPublicationFailureCode.SOURCE_UNAVAILABLE
    assert "hostile" not in str(caught.value)


def test_wrong_source_result_is_rejected(fixture_bytes: bytes) -> None:
    service = PartialAutoPublicationEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=_CountingSource(),
    )
    with pytest.raises(PartialAutoPublicationFailure) as caught:
        service.evaluate(command_for(fixture_bytes))
    assert caught.value.code is PartialAutoPublicationFailureCode.SOURCE_RESULT_INVALID
