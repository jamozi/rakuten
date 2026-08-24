"""Pre-I/O ST-0403 durable authorization and hostile collaborator checks."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, NoReturn

import pytest

from conftest import (
    SITE_B,
    V2_NOW,
    V2_RESOURCE_ID,
    v2_authentication_service,
    v2_authorization_runtime,
    v2_authorization_target,
    v2_descriptor,
    v2_policy,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.adapters.recorded_object_intake_runtime_v2 import (
    DeterministicContentInspectorV2,
    RecordedMalwareScannerV2,
    RecordedPrivacyClassifierV2,
)
from raos.application.iam.authorization import DurableAuthorizationService
from raos.application.ops.object_intake_runtime_v2 import SecureObjectIntakeRuntimeV2
from raos.domain.iam.authentication import Session
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationDecision,
    AuthorizationEvaluationCommand,
)
from raos.domain.ops.object_intake import ObjectIntakeKind
from raos.domain.ops.object_intake_runtime_v2 import (
    DurableIntakeDescriptorV2,
    IntakeCommandId,
    MalwareScanReceiptV2,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
    PrivacyClassificationReceiptV2,
    RecordedMalwareVerdict,
    RecordedPrivacyVerdict,
)


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read_chunk(self, *, maximum_bytes: int) -> bytes:
        del maximum_bytes
        self.calls += 1
        raise AssertionError("SECRET_CANARY_SOURCE_MUST_NOT_RUN")


class _CountingIntakeRepository:
    def __init__(self) -> None:
        self.begin_calls = 0
        self.recover_calls = 0

    def begin(self, **kwargs: object) -> NoReturn:
        del kwargs
        self.begin_calls += 1
        raise AssertionError("SECRET_CANARY_QUARANTINE_MUST_NOT_RUN")

    def recover(self, **kwargs: object) -> NoReturn:
        del kwargs
        self.recover_calls += 1
        raise AssertionError("SECRET_CANARY_QUARANTINE_MUST_NOT_RUN")


class _RaisingAuthorizationRepository:
    def begin(self) -> NoReturn:
        raise RuntimeError("SECRET_CANARY_AUTH_REPOSITORY") from None

    def recover(self, command_id: AuthorizationCommandId) -> NoReturn:
        del command_id
        raise RuntimeError("SECRET_CANARY_AUTH_REPOSITORY") from None


def _runtime(
    *, authorization_service: DurableAuthorizationService
) -> tuple[SecureObjectIntakeRuntimeV2, _CountingIntakeRepository]:
    descriptor = v2_descriptor()
    digest = descriptor.descriptor.declared_sha256
    repository = _CountingIntakeRepository()
    return (
        SecureObjectIntakeRuntimeV2(
            policy=v2_policy(),
            authorization_service=authorization_service,
            repository=repository,
            inspector=DeterministicContentInspectorV2(),
            privacy_classifier=RecordedPrivacyClassifierV2(
                (
                    (
                        digest,
                        PrivacyClassificationReceiptV2(
                            verdict=RecordedPrivacyVerdict.MATCH,
                            classified_as=descriptor.descriptor.privacy_class,
                            classifier_revision="RECORDED-V2",
                        ),
                    ),
                )
            ),
            malware_scanner=RecordedMalwareScannerV2(
                (
                    (
                        digest,
                        MalwareScanReceiptV2(
                            verdict=RecordedMalwareVerdict.CLEAN,
                            engine_revision="RECORDED-V2",
                        ),
                    ),
                )
            ),
        ),
        repository,
    )


def _assert_denied_before_io(
    *,
    runtime: SecureObjectIntakeRuntimeV2,
    repository: _CountingIntakeRepository,
    descriptor: DurableIntakeDescriptorV2,
    session: Session,
    command: AuthorizationEvaluationCommand,
    result: AuthorizationCommandResult,
    checked_at: datetime = V2_NOW,
) -> ObjectIntakeRuntimeFailure:
    source = _CountingSource()
    with pytest.raises(ObjectIntakeRuntimeFailure) as caught:
        runtime.intake(
            command_id=IntakeCommandId("RECORDED:ST0406:NEGATIVE"),
            descriptor=descriptor,
            session_id=session.session_id,
            authorization_command=command,
            authorization_result=result,
            authorization_checked_at=checked_at,
            source=source,
        )
    assert caught.value.code in {
        ObjectIntakeRuntimeFailureCode.AUTHORIZATION_REQUIRED,
        ObjectIntakeRuntimeFailureCode.AUTHORIZATION_NOT_DURABLE,
    }
    assert source.calls == 0
    assert repository.begin_calls == 0
    assert repository.recover_calls == 0
    assert "SECRET_CANARY" not in str(caught.value)
    assert "SECRET_CANARY" not in repr(caught.value)
    assert caught.value.__cause__ is None
    return caught.value


def test_expired_session_is_rechecked_before_any_intake_io(tmp_path: Path) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = _runtime(authorization_service=auth)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=command,
        result=result,
        checked_at=V2_NOW + timedelta(hours=3),
    )


def test_revoked_session_is_rechecked_before_any_intake_io(tmp_path: Path) -> None:
    valid_auth, session, command, result, authorization_repository = (
        v2_authorization_runtime(tmp_path)
    )
    del valid_auth
    revoked = replace(session, revoked_at=V2_NOW)
    ended_auth = DurableAuthorizationService(
        session_service=v2_authentication_service(revoked),
        repository=authorization_repository,
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    runtime, repository = _runtime(authorization_service=ended_auth)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=command,
        result=result,
    )


@pytest.mark.parametrize(
    "descriptor,command_mutator",
    (
        (v2_descriptor(site_id=SITE_B), lambda value: value),
        (
            v2_descriptor(resource_id=SITE_B),
            lambda value: value,
        ),
        (
            v2_descriptor(),
            lambda value: replace(
                value, operation_id=type(value.operation_id)("PUBADM-004")
            ),
        ),
        (
            v2_descriptor(),
            lambda value: replace(
                value,
                target=v2_authorization_target(state="HUMAN_REVIEW"),
            ),
        ),
    ),
    ids=("wrong-site", "wrong-resource", "wrong-operation", "wrong-state"),
)
def test_wrong_binding_or_descriptor_is_denied_before_io(
    tmp_path: Path,
    descriptor: DurableIntakeDescriptorV2,
    command_mutator: Callable[
        [AuthorizationEvaluationCommand], AuthorizationEvaluationCommand
    ],
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = _runtime(authorization_service=auth)
    changed = command_mutator(command)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=descriptor,
        session=session,
        command=changed,
        result=result,
    )


def test_command_result_digest_mismatch_and_forged_result_are_denied(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = _runtime(authorization_service=auth)
    changed = replace(
        command,
        command_id=AuthorizationCommandId("RECORDED:ST0406:AUTH:FORGED-COMMAND"),
    )
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=changed,
        result=result,
    )

    forged = replace(result, session_fingerprint="f" * 64)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=command,
        result=forged,
    )

    decision = result.decision
    wrong_action = AuthorizationDecision(
        correlation_id=decision.correlation_id,
        effect=decision.effect,
        reason=decision.reason,
        policy_revision=decision.policy_revision,
        policy_fingerprint=decision.policy_fingerprint,
        entitlement_revision=decision.entitlement_revision,
        matched_rule_id=decision.matched_rule_id,
        action=ActionCode("review_article"),
        target=decision.target,
    )
    forged_action = replace(result, decision=wrong_action)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=command,
        result=forged_action,
    )


def test_unproven_revenue_report_kind_is_denied_before_any_intake_io(
    tmp_path: Path,
) -> None:
    auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    runtime, repository = _runtime(authorization_service=auth)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(kind=ObjectIntakeKind.REVENUE_REPORT),
        session=session,
        command=command,
        result=result,
    )


def test_durable_denial_is_never_treated_as_intake_authority(tmp_path: Path) -> None:
    auth, session, command, denied, _ = v2_authorization_runtime(
        tmp_path, install_rule=False
    )
    runtime, repository = _runtime(authorization_service=auth)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(),
        session=session,
        command=command,
        result=denied,
    )


def test_arbitrary_authorization_repository_exception_is_sanitized_before_io(
    tmp_path: Path,
) -> None:
    valid_auth, session, command, result, _ = v2_authorization_runtime(tmp_path)
    del valid_auth
    hostile = DurableAuthorizationService(
        session_service=v2_authentication_service(session),
        repository=_RaisingAuthorizationRepository(),
        registry=CANONICAL_AUTHORIZATION_REGISTRY,
        step_up_consumer=None,
    )
    runtime, repository = _runtime(authorization_service=hostile)
    _assert_denied_before_io(
        runtime=runtime,
        repository=repository,
        descriptor=v2_descriptor(resource_id=V2_RESOURCE_ID),
        session=session,
        command=command,
        result=result,
    )
