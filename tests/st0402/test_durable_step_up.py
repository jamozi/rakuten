"""Durability, exact binding, replay, revocation, CAS, and recovery tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import sqlite3
from threading import Barrier, Thread
from typing import Callable
from uuid import UUID

import pytest

from raos.adapters.development_oidc import (
    DevelopmentOidcAdapter,
    InMemoryAuthenticationRepository,
)
from raos.adapters.recorded_step_up import (
    RecordedSqliteStepUpRepository,
    RecordedStepUpCommitFault,
    RecordedSyntheticMfaVerifier,
)
from raos.application.iam.authentication import AuthenticationService
from raos.application.iam.step_up import DurableStepUpService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import (
    Issuer,
    PrincipalIdentity,
    Session,
    SessionId,
    Subject,
)
from raos.domain.iam.step_up import (
    BoundStepUpGrantId,
    CriticalStepUpAction,
    CriticalStepUpPolicyRegistry,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpFailure,
    StepUpFailureCode,
    StepUpResourceType,
)


NOW = datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc)
RESOURCE_ID = UUID("018f3e90-7b00-7000-8000-000000000402")


def _raw(label: str) -> bytes:
    return hashlib.sha256(label.encode("ascii")).digest()


def _command(label: str) -> StepUpCommandId:
    return StepUpCommandId.from_bytes(_raw(f"COMMAND-{label}"))


class _Entropy:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._index = 0

    def token_bytes(self, size: int) -> bytes:
        assert size == 32
        self._index += 1
        return _raw(f"{self._prefix}-{self._index}")


def _session(index: int = 1) -> Session:
    principal = PrincipalIdentity(
        issuer=Issuer(f"https://recorded-step-up-{index}.invalid"),
        subject=Subject(f"recorded-admin-{index}"),
        display_name=f"Recorded administrator {index}",
    )
    return Session(
        session_id=SessionId.from_bytes(_raw(f"SESSION-{index}")),
        principal=principal,
        created_at=NOW - timedelta(minutes=5),
        last_seen_at=NOW - timedelta(minutes=1),
        idle_expires_at=NOW + timedelta(hours=1),
        absolute_expires_at=NOW + timedelta(hours=2),
    )


SESSION = _session()


def _private(path: Path) -> Path:
    path.chmod(0o700)
    return path


def _service(
    root: Path,
    prefix: str,
    *,
    session: Session = SESSION,
    fault: RecordedStepUpCommitFault | None = None,
) -> tuple[RecordedSqliteStepUpRepository, DurableStepUpService]:
    authentication_repository = InMemoryAuthenticationRepository(
        environment=RuntimeEnvironment.ENV_DEV
    )
    authentication_repository.create_session(session)
    provider = DevelopmentOidcAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        principal=session.principal,
    )
    repository = RecordedSqliteStepUpRepository(
        environment=RuntimeEnvironment.ENV_DEV,
        private_root=root,
        fault_once_at=fault,
    )
    return repository, DurableStepUpService(
        session_service=AuthenticationService(
            provider=provider,
            repository=authentication_repository,
            entropy=_Entropy(f"AUTH-{prefix}"),
        ),
        repository=repository,
        verifier=RecordedSyntheticMfaVerifier(environment=RuntimeEnvironment.ENV_DEV),
        entropy=_Entropy(f"STEP-UP-{prefix}"),
        policy=CriticalStepUpPolicyRegistry(),
    )


def _assert_failure(
    code: StepUpFailureCode, operation: Callable[[], object]
) -> StepUpFailure:
    with pytest.raises(StepUpFailure) as caught:
        operation()
    assert caught.value.code is code
    return caught.value


def _issue(
    service: DurableStepUpService,
    prefix: str,
    *,
    action: CriticalStepUpAction = CriticalStepUpAction.PUBLISH,
    resource_type: StepUpResourceType = StepUpResourceType.PUBLICATION_SNAPSHOT,
    resource_id: UUID = RESOURCE_ID,
) -> tuple[StepUpCommandResult, StepUpCommandResult, StepUpCommandResult]:
    begun = service.begin_challenge(
        command_id=_command(f"{prefix}-BEGIN"),
        session_id=SESSION.session_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        now=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    assert begun.challenge is not None
    challenge = begun.challenge
    verified = service.verify_challenge(
        command_id=_command(f"{prefix}-VERIFY"),
        session_id=SESSION.session_id,
        challenge_id=challenge.challenge_id,
        now=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(minutes=4),
    )
    assert verified.verification is not None
    issued = service.issue_grant(
        command_id=_command(f"{prefix}-ISSUE"),
        session_id=SESSION.session_id,
        receipt_id=verified.verification.receipt_id,
        now=NOW + timedelta(minutes=2),
        expires_at=NOW + timedelta(minutes=4),
    )
    assert issued.grant is not None
    return begun, verified, issued


def test_closed_policy_registry_covers_exact_canonical_critical_actions() -> None:
    registry = CriticalStepUpPolicyRegistry()
    assert set(CriticalStepUpAction) == {
        CriticalStepUpAction.FINAL_APPROVE,
        CriticalStepUpAction.PUBLISH,
        CriticalStepUpAction.ROLLBACK,
        CriticalStepUpAction.ACTIVATE_PUBLICATION_KILL_SWITCH,
        CriticalStepUpAction.DEACTIVATE_PUBLICATION_KILL_SWITCH,
        CriticalStepUpAction.ACTIVATE_AFFILIATE_KILL_SWITCH,
        CriticalStepUpAction.DEACTIVATE_AFFILIATE_KILL_SWITCH,
        CriticalStepUpAction.COMMIT_REVENUE_IMPORT,
        CriticalStepUpAction.MANAGE_AI_RELEASE,
        CriticalStepUpAction.MANAGE_SECRETS,
        CriticalStepUpAction.BREAK_GLASS,
    }
    for action in CriticalStepUpAction:
        expected = registry.resource_for(action)
        registry.require(action=action, resource_type=expected)
        wrong = next(value for value in StepUpResourceType if value is not expected)
        _assert_failure(
            StepUpFailureCode.ACTION_RESOURCE_MISMATCH,
            lambda: registry.require(action=action, resource_type=wrong),
        )


def test_full_lifecycle_is_durable_single_use_idempotent_and_hash_chained(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository, service = _service(root, "FULL")
    begun, verified, issued = _issue(service, "FULL")
    assert begun.challenge is not None
    assert verified.verification is not None
    assert issued.grant is not None

    consumed = service.consume_grant(
        command_id=_command("FULL-CONSUME"),
        session_id=SESSION.session_id,
        grant_id=issued.grant.grant_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW + timedelta(minutes=3),
    )
    assert consumed.authorization is not None
    assert consumed.authorization.binding == issued.grant.binding
    assert consumed.audit.sequence == 4

    reopened, retried = _service(root, "REOPENED")
    recovered = retried.recover(command_id=_command("FULL-CONSUME"))
    assert recovered == consumed
    duplicate = retried.consume_grant(
        command_id=_command("FULL-CONSUME"),
        session_id=SESSION.session_id,
        grant_id=issued.grant.grant_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW + timedelta(minutes=3, seconds=30),
    )
    assert duplicate == consumed
    audits = reopened.audit_snapshot()
    assert [event.sequence for event in audits] == [1, 2, 3, 4]
    assert audits[0].previous_digest == "0" * 64
    assert all(
        current.previous_digest == previous.digest
        for previous, current in zip(audits[:-1], audits[1:], strict=True)
    )
    assert (root / "st0402-recorded-step-up.sqlite3").stat().st_mode & 0o777 == 0o600


def test_command_reuse_with_changed_binding_is_rejected_without_second_audit(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    repository, service = _service(root, "CONFLICT")
    first = service.begin_challenge(
        command_id=_command("CONFLICT-BEGIN"),
        session_id=SESSION.session_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    assert first.challenge is not None
    _assert_failure(
        StepUpFailureCode.COMMAND_CONFLICT,
        lambda: service.begin_challenge(
            command_id=_command("CONFLICT-BEGIN"),
            session_id=SESSION.session_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=UUID("018f3e90-7b00-7000-8000-000000000499"),
            now=NOW + timedelta(seconds=1),
            expires_at=NOW + timedelta(minutes=5),
        ),
    )
    assert len(repository.audit_snapshot()) == 1


def test_grant_cannot_move_across_action_resource_session_or_principal(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    _repository, service = _service(root, "BINDING")
    _begun, _verified, issued = _issue(service, "BINDING")
    assert issued.grant is not None
    grant_id = issued.grant.grant_id

    _assert_failure(
        StepUpFailureCode.GRANT_MISMATCH,
        lambda: service.consume_grant(
            command_id=_command("BINDING-WRONG-RESOURCE"),
            session_id=SESSION.session_id,
            grant_id=grant_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=UUID("018f3e90-7b00-7000-8000-000000000498"),
            now=NOW + timedelta(minutes=3),
        ),
    )
    other = _session(2)
    _other_repository, other_service = _service(root, "BINDING-OTHER", session=other)
    _assert_failure(
        StepUpFailureCode.GRANT_MISMATCH,
        lambda: other_service.consume_grant(
            command_id=_command("BINDING-OTHER"),
            session_id=other.session_id,
            grant_id=grant_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=RESOURCE_ID,
            now=NOW + timedelta(minutes=3),
        ),
    )
    accepted = service.consume_grant(
        command_id=_command("BINDING-CORRECT"),
        session_id=SESSION.session_id,
        grant_id=grant_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW + timedelta(minutes=3),
    )
    assert accepted.authorization is not None


def test_each_stage_expires_and_each_single_use_transition_rejects_replay(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    _repository, service = _service(root, "EXPIRY")
    begun = service.begin_challenge(
        command_id=_command("EXPIRY-BEGIN"),
        session_id=SESSION.session_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW,
        expires_at=NOW + timedelta(minutes=1),
    )
    assert begun.challenge is not None
    expired_challenge = begun.challenge
    _assert_failure(
        StepUpFailureCode.CHALLENGE_EXPIRED,
        lambda: service.verify_challenge(
            command_id=_command("EXPIRY-VERIFY"),
            session_id=SESSION.session_id,
            challenge_id=expired_challenge.challenge_id,
            now=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=2),
        ),
    )

    _reopened_repository, replay_service = _service(root, "REPLAY-SERVICE")
    _begin, verification, issued = _issue(replay_service, "REPLAY")
    assert verification.verification is not None
    assert issued.grant is not None
    replay_verification = verification.verification
    replay_grant = issued.grant
    _assert_failure(
        StepUpFailureCode.CHALLENGE_REPLAY,
        lambda: replay_service.verify_challenge(
            command_id=_command("REPLAY-VERIFY-AGAIN"),
            session_id=SESSION.session_id,
            challenge_id=replay_verification.challenge_id,
            now=NOW + timedelta(minutes=2),
            expires_at=NOW + timedelta(minutes=4),
        ),
    )
    _assert_failure(
        StepUpFailureCode.RECEIPT_REPLAY,
        lambda: replay_service.issue_grant(
            command_id=_command("REPLAY-ISSUE-AGAIN"),
            session_id=SESSION.session_id,
            receipt_id=replay_verification.receipt_id,
            now=NOW + timedelta(minutes=2, seconds=1),
            expires_at=NOW + timedelta(minutes=4),
        ),
    )
    replay_service.consume_grant(
        command_id=_command("REPLAY-CONSUME"),
        session_id=SESSION.session_id,
        grant_id=replay_grant.grant_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW + timedelta(minutes=3),
    )
    _assert_failure(
        StepUpFailureCode.GRANT_REPLAY,
        lambda: replay_service.consume_grant(
            command_id=_command("REPLAY-CONSUME-AGAIN"),
            session_id=SESSION.session_id,
            grant_id=replay_grant.grant_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=RESOURCE_ID,
            now=NOW + timedelta(minutes=3, seconds=1),
        ),
    )


def test_revocation_is_durable_and_prevents_consumption(tmp_path: Path) -> None:
    root = _private(tmp_path)
    repository, service = _service(root, "REVOKE")
    _begun, _verified, issued = _issue(service, "REVOKE")
    assert issued.grant is not None
    issued_grant = issued.grant
    revoked = service.revoke_grant(
        command_id=_command("REVOKE-GRANT"),
        session_id=SESSION.session_id,
        grant_id=issued_grant.grant_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW + timedelta(minutes=3),
    )
    assert revoked.grant == issued_grant
    _assert_failure(
        StepUpFailureCode.GRANT_REVOKED,
        lambda: service.consume_grant(
            command_id=_command("REVOKE-CONSUME"),
            session_id=SESSION.session_id,
            grant_id=issued_grant.grant_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=RESOURCE_ID,
            now=NOW + timedelta(minutes=3, seconds=1),
        ),
    )
    assert [event.operation.value for event in repository.audit_snapshot()][-1] == (
        "REVOKE_GRANT"
    )


def test_before_and_after_commit_crashes_have_unambiguous_recovery(
    tmp_path: Path,
) -> None:
    before_root = tmp_path / "before"
    before_root.mkdir(mode=0o700)
    before_root.chmod(0o700)
    before_repository, before = _service(
        before_root,
        "BEFORE",
        fault=RecordedStepUpCommitFault.BEFORE_COMMIT,
    )
    _assert_failure(
        StepUpFailureCode.STORAGE_FAILURE,
        lambda: before.begin_challenge(
            command_id=_command("CRASH-BEFORE"),
            session_id=SESSION.session_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=RESOURCE_ID,
            now=NOW,
            expires_at=NOW + timedelta(minutes=5),
        ),
    )
    _assert_failure(
        StepUpFailureCode.COMMAND_UNKNOWN,
        lambda: before.recover(command_id=_command("CRASH-BEFORE")),
    )
    assert before_repository.audit_snapshot() == ()

    after_root = tmp_path / "after"
    after_root.mkdir(mode=0o700)
    after_root.chmod(0o700)
    _after_repository, after = _service(
        after_root,
        "AFTER",
        fault=RecordedStepUpCommitFault.AFTER_COMMIT,
    )
    _assert_failure(
        StepUpFailureCode.STORAGE_COMMIT_UNKNOWN,
        lambda: after.begin_challenge(
            command_id=_command("CRASH-AFTER"),
            session_id=SESSION.session_id,
            action=CriticalStepUpAction.PUBLISH,
            resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
            resource_id=RESOURCE_ID,
            now=NOW,
            expires_at=NOW + timedelta(minutes=5),
        ),
    )
    reopened, recovery = _service(after_root, "AFTER-RECOVERY")
    recovered = recovery.recover(command_id=_command("CRASH-AFTER"))
    assert recovered.challenge is not None
    assert len(reopened.audit_snapshot()) == 1


def test_concurrent_consumption_has_one_cas_winner(tmp_path: Path) -> None:
    root = _private(tmp_path)
    _repository, service = _service(root, "CAS-PREPARE")
    _begun, _verified, issued = _issue(service, "CAS")
    assert issued.grant is not None
    grant_id = issued.grant.grant_id
    barrier = Barrier(2)
    outcomes: list[StepUpCommandResult | StepUpFailureCode] = []

    def consume(label: str) -> None:
        _repo, contender = _service(root, f"CAS-{label}")
        barrier.wait()
        try:
            outcomes.append(
                contender.consume_grant(
                    command_id=_command(f"CAS-CONSUME-{label}"),
                    session_id=SESSION.session_id,
                    grant_id=grant_id,
                    action=CriticalStepUpAction.PUBLISH,
                    resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
                    resource_id=RESOURCE_ID,
                    now=NOW + timedelta(minutes=3),
                )
            )
        except StepUpFailure as error:
            outcomes.append(error.code)

    threads = (Thread(target=consume, args=("A",)), Thread(target=consume, args=("B",)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert sum(type(value) is StepUpCommandResult for value in outcomes) == 1
    assert outcomes.count(StepUpFailureCode.GRANT_REPLAY) == 1
    reopened, _reopened_service = _service(root, "CAS-READ")
    assert len(reopened.audit_snapshot()) == 4


def test_tampered_object_or_audit_chain_fails_closed_on_restart(
    tmp_path: Path,
) -> None:
    root = _private(tmp_path)
    _repository, service = _service(root, "TAMPER")
    _issue(service, "TAMPER")
    database = root / "st0402-recorded-step-up.sqlite3"
    connection = sqlite3.connect(database)
    try:
        connection.execute(
            "UPDATE recorded_step_up_audit SET digest=? WHERE sequence=2",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    failure = _assert_failure(
        StepUpFailureCode.STORAGE_FAILURE,
        lambda: RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=root,
        ),
    )
    assert "recorded-admin" not in f"{failure!s} {failure!r}"


def test_repository_read_exception_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _private(tmp_path)
    repository, service = _service(root, "READ-FAILURE")
    begun = service.begin_challenge(
        command_id=_command("READ-FAILURE-BEGIN"),
        session_id=SESSION.session_id,
        action=CriticalStepUpAction.PUBLISH,
        resource_type=StepUpResourceType.PUBLICATION_SNAPSHOT,
        resource_id=RESOURCE_ID,
        now=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    assert begun.challenge is not None
    challenge = begun.challenge

    def explode(_challenge_id: object) -> object:
        raise RuntimeError("sensitive-repository-detail")

    monkeypatch.setattr(repository, "load_challenge", explode)
    failure = _assert_failure(
        StepUpFailureCode.STORAGE_FAILURE,
        lambda: service.verify_challenge(
            command_id=_command("READ-FAILURE-VERIFY"),
            session_id=SESSION.session_id,
            challenge_id=challenge.challenge_id,
            now=NOW + timedelta(minutes=1),
            expires_at=NOW + timedelta(minutes=4),
        ),
    )
    assert "sensitive-repository-detail" not in f"{failure!s} {failure!r}"


def test_private_root_symlink_non_dev_and_diagnostics_fail_closed(
    tmp_path: Path,
) -> None:
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    public.chmod(0o755)
    _assert_failure(
        StepUpFailureCode.STORAGE_FAILURE,
        lambda: RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=public,
        ),
    )
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private.chmod(0o700)
    link = tmp_path / "link"
    os.symlink(private, link)
    _assert_failure(
        StepUpFailureCode.STORAGE_FAILURE,
        lambda: RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.ENV_DEV,
            private_root=link,
        ),
    )
    _assert_failure(
        StepUpFailureCode.DEVELOPMENT_ONLY,
        lambda: RecordedSqliteStepUpRepository(
            environment=RuntimeEnvironment.STAGING,
            private_root=private,
        ),
    )
    repository, _service_value = _service(private, "REPR")
    rendered = f"{repository!s} {repository!r}"
    assert str(private) not in rendered
    assert SESSION.session_id.reveal() not in rendered
    assert BoundStepUpGrantId.from_bytes(_raw("REPR-GRANT")).reveal() not in rendered
