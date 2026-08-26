"""Fail-closed collaborator and cross-binding behavior."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from .support import candidate, request, service_and_adapter
from raos.application.editorial.ai_draft_integration import AiDraftIntegrationService
from raos.domain.editorial.ai_draft_integration import (
    AiDraftEnvironment,
    AiDraftIntegrationFailure,
    AiDraftIntegrationFailureCode,
    AiDraftIntegrationRequest,
    RecordedDraftCandidate,
)


class _ThrowingPort:
    calls = 0

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> RecordedDraftCandidate:
        del request
        self.calls += 1
        raise RuntimeError("collaborator-secret-value")


class _WrongCandidatePort:
    calls = 0

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> RecordedDraftCandidate:
        del request
        self.calls += 1
        return replace(candidate(), site_id=candidate().category_id)


class _ExplodingRepr:
    def __repr__(self) -> str:
        raise RuntimeError("repr-secret-value")


class _MalformedPort:
    calls = 0

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> RecordedDraftCandidate:
        del request
        self.calls += 1
        return cast(RecordedDraftCandidate, _ExplodingRepr())


@pytest.mark.parametrize("port", [_ThrowingPort(), _MalformedPort()])
def test_collaborator_failure_is_one_call_and_suppresses_cause_context(
    port: _ThrowingPort | _MalformedPort,
) -> None:
    service = AiDraftIntegrationService(
        environment=AiDraftEnvironment.ENV_DEV,
        port=port,
    )
    with pytest.raises(AiDraftIntegrationFailure) as caught:
        service.integrate(request=request())
    assert caught.value.code in {
        AiDraftIntegrationFailureCode.COLLABORATOR_FAILURE,
        AiDraftIntegrationFailureCode.CANDIDATE_INVALID,
    }
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert port.calls == 1
    assert "secret" not in str(caught.value)


def test_cross_field_mismatch_fails_without_second_call() -> None:
    port = _WrongCandidatePort()
    service = AiDraftIntegrationService(
        environment=AiDraftEnvironment.ENV_DEV,
        port=port,
    )
    with pytest.raises(AiDraftIntegrationFailure) as caught:
        service.integrate(request=request())
    assert caught.value.code is AiDraftIntegrationFailureCode.BINDING_MISMATCH
    assert port.calls == 1


def test_consumed_fixture_has_no_retry_or_fallback() -> None:
    service, adapter = service_and_adapter()
    service.integrate(request=request())
    with pytest.raises(AiDraftIntegrationFailure) as caught:
        service.integrate(request=request())
    assert caught.value.code is AiDraftIntegrationFailureCode.COLLABORATOR_FAILURE
    assert adapter.call_count == 1
