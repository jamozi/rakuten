"""Hostile identity, idempotency, drift, and atomicity checks for ST-0905 V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest

from raos.adapters.publishing.recorded_publication_command_fixture_v2 import (
    RecordedPublicationCommandScenarioV2,
)
from raos.adapters.publishing.recorded_publication_commands_v2 import (
    RecordedPublicationCommandStoreV2,
    TransactionFailurePoint,
)
from raos.application.publishing.publication_commands_v2 import (
    PublicationCommandServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.step_up import StepUpAssuranceType, StepUpGrant
from raos.domain.publishing.publication_commands_v2 import (
    PublicationCommandAuthorizationV2,
    PublicationCommandFailure,
    PublicationCommandFailureCode,
    PublicationCommandRole,
    PublicationKillSwitchSafeStateV2,
    RollbackCommandV2,
)
from raos.domain.shared.persistence import Sha256Digest


def _service(
    scenario: RecordedPublicationCommandScenarioV2,
) -> tuple[PublicationCommandServiceV2, RecordedPublicationCommandStoreV2]:
    store = RecordedPublicationCommandStoreV2(
        environment=RuntimeEnvironment.CI,
        sources=scenario.sources,
    )
    service = PublicationCommandServiceV2(
        environment=RuntimeEnvironment.CI,
        store=store,
    )
    return service, store


def _assert_code(code: PublicationCommandFailureCode, operation: object) -> None:
    with pytest.raises(PublicationCommandFailure) as captured:
        assert callable(operation)
        operation()
    assert captured.value.code is code


def test_same_key_different_request_conflicts_without_mutation(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    before = store.snapshot()
    conflicting = replace(
        runtime_scenario.publish,
        expected_generation=1,
    )
    _assert_code(
        PublicationCommandFailureCode.IDEMPOTENCY_CONFLICT,
        lambda: service.publish(conflicting),
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256


def test_wrong_snapshot_source_and_generation_fail_closed(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    before = store.snapshot()
    wrong_source = replace(
        runtime_scenario.publish,
        expected_source_binding_sha256=Sha256Digest("a" * 64),
    )
    _assert_code(
        PublicationCommandFailureCode.SOURCE_HASH_MISMATCH,
        lambda: service.publish(wrong_source),
    )
    wrong_generation = replace(runtime_scenario.publish, expected_generation=1)
    _assert_code(
        PublicationCommandFailureCode.CONCURRENCY_CONFLICT,
        lambda: service.publish(wrong_generation),
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256


def test_unknown_current_reverse_and_drifted_rollback_targets_do_not_mutate(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    baseline = store.snapshot()
    latest = runtime_scenario.sources.latest
    previous = runtime_scenario.sources.snapshots[0]
    cases: tuple[tuple[PublicationCommandFailureCode, RollbackCommandV2], ...] = (
        (
            PublicationCommandFailureCode.ROLLBACK_TARGET_UNKNOWN,
            replace(
                runtime_scenario.rollback,
                to_snapshot_id=UUID("018f3e90-7b00-7000-8000-000000000999"),
            ),
        ),
        (
            PublicationCommandFailureCode.ROLLBACK_TARGET_CURRENT,
            replace(
                runtime_scenario.rollback,
                to_snapshot_id=latest.snapshot_id,
                expected_to_source_binding_sha256=latest.source_binding_sha256,
            ),
        ),
        (
            PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT,
            replace(
                runtime_scenario.rollback,
                from_snapshot_id=previous.snapshot_id,
                to_snapshot_id=latest.snapshot_id,
                expected_from_source_binding_sha256=previous.source_binding_sha256,
                expected_to_source_binding_sha256=latest.source_binding_sha256,
            ),
        ),
        (
            PublicationCommandFailureCode.SOURCE_HASH_MISMATCH,
            replace(
                runtime_scenario.rollback,
                expected_to_source_binding_sha256=Sha256Digest("b" * 64),
            ),
        ),
    )
    for expected, command in cases:
        _assert_code(expected, lambda command=command: service.rollback(command))
        assert store.snapshot().snapshot_sha256 == baseline.snapshot_sha256


@pytest.mark.parametrize("point", tuple(TransactionFailurePoint))
def test_publish_partial_failure_is_atomic_and_retryable(
    point: TransactionFailurePoint,
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    store.plan_failure(point)
    before = store.snapshot()
    _assert_code(
        PublicationCommandFailureCode.TRANSACTION_FAILED,
        lambda: service.publish(runtime_scenario.publish),
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256
    result = service.publish(runtime_scenario.publish)
    assert result.generation == 1


@pytest.mark.parametrize("point", tuple(TransactionFailurePoint))
def test_rollback_partial_failure_is_atomic_and_retryable(
    point: TransactionFailurePoint,
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    store.plan_failure(point)
    before = store.snapshot()
    _assert_code(
        PublicationCommandFailureCode.TRANSACTION_FAILED,
        lambda: service.rollback(runtime_scenario.rollback),
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256
    result = service.rollback(runtime_scenario.rollback)
    assert result.generation == 2


def test_active_human_mfa_step_up_and_kill_switch_are_explicit_gates(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    auth = runtime_scenario.publish.authorization
    with pytest.raises(PublicationCommandFailure) as active:
        replace(auth, active_human=False)
    assert active.value.code is PublicationCommandFailureCode.ACTIVE_HUMAN_REQUIRED
    with pytest.raises(PublicationCommandFailure) as mfa:
        replace(auth, mfa_verified=False)
    assert mfa.value.code is PublicationCommandFailureCode.MFA_REQUIRED
    unsupported_grant = StepUpGrant(
        session_id=auth.session_id,
        issuer=auth.step_up_grant.issuer,
        subject=auth.step_up_grant.subject,
        assurance_type=StepUpAssuranceType.UNSUPPORTED,
        authenticated_at=auth.step_up_grant.authenticated_at,
        expires_at=auth.step_up_grant.expires_at,
    )
    with pytest.raises(PublicationCommandFailure) as step_up:
        replace(auth, step_up_grant=unsupported_grant)
    assert step_up.value.code is PublicationCommandFailureCode.STEP_UP_REQUIRED
    with pytest.raises(PublicationCommandFailure) as kill:
        replace(runtime_scenario.publish.kill_switch, engaged=True)
    assert kill.value.code is PublicationCommandFailureCode.KILL_SWITCH_DENIED


def test_site_scope_separation_role_and_freshness_fail_closed(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    original = runtime_scenario.publish.authorization
    wrong_site = replace(
        original,
        site_id=UUID("018f3e90-7b00-7000-8000-000000000998"),
    )
    service, store = _service(runtime_scenario)
    command = replace(runtime_scenario.publish, authorization=wrong_site)
    _assert_code(
        PublicationCommandFailureCode.SITE_SCOPE_MISMATCH,
        lambda: service.publish(command),
    )
    assert store.snapshot().generation == 0

    approver = (
        runtime_scenario.sources.latest.final_approval_result.record.approved_by.value
    )
    same_actor = replace(original, actor_id=approver)
    command = replace(runtime_scenario.publish, authorization=same_actor)
    _assert_code(
        PublicationCommandFailureCode.SEPARATION_OF_DUTIES_REQUIRED,
        lambda: service.publish(command),
    )
    assert store.snapshot().generation == 0

    stale_at = original.step_up_grant.expires_at
    with pytest.raises(PublicationCommandFailure) as stale:
        PublicationCommandAuthorizationV2(
            actor_id=original.actor_id,
            site_id=original.site_id,
            role=PublicationCommandRole.OPERATOR,
            session_id=original.session_id,
            step_up_grant=original.step_up_grant,
            observed_at=stale_at,
        )
    assert stale.value.code is PublicationCommandFailureCode.STEP_UP_STALE

    with pytest.raises(PublicationCommandFailure) as kill_stale:
        PublicationKillSwitchSafeStateV2(
            observation_id=runtime_scenario.publish.kill_switch.observation_id,
            generation=1,
            observed_at=runtime_scenario.publish.occurred_at,
            fresh_until=runtime_scenario.publish.occurred_at - timedelta(seconds=1),
            source_sha256=runtime_scenario.publish.kill_switch.source_sha256,
        )
    assert kill_stale.value.code is PublicationCommandFailureCode.KILL_SWITCH_DENIED


def test_reverse_rollback_to_a_newer_known_snapshot_is_denied_without_mutation(
    runtime_scenario: RecordedPublicationCommandScenarioV2,
) -> None:
    service, store = _service(runtime_scenario)
    service.publish(runtime_scenario.publish)
    service.rollback(runtime_scenario.rollback)
    previous, latest = runtime_scenario.sources.snapshots
    reverse = replace(
        runtime_scenario.rollback,
        from_snapshot_id=previous.snapshot_id,
        to_snapshot_id=latest.snapshot_id,
        expected_from_source_binding_sha256=previous.source_binding_sha256,
        expected_to_source_binding_sha256=latest.source_binding_sha256,
        expected_generation=2,
        idempotency_key="st0905-v2-reverse-rollback-denied-0001",
    )
    before = store.snapshot()
    _assert_code(
        PublicationCommandFailureCode.ROLLBACK_TARGET_NOT_PREVIOUS,
        lambda: service.rollback(reverse),
    )
    assert store.snapshot().snapshot_sha256 == before.snapshot_sha256
