"""Transport-neutral active-session and step-up assurance guard."""

from __future__ import annotations

from datetime import datetime
import hmac
from collections.abc import Callable
from typing import TypeVar, cast
from uuid import UUID

from raos.application.iam.authentication import AuthenticationService
from raos.domain.iam.authentication import (
    Session,
    SessionId,
    snapshot_session,
    snapshot_session_id,
)
from raos.domain.iam.step_up import (
    BoundStepUpGrant,
    BoundStepUpGrantId,
    CriticalStepUpAction,
    CriticalStepUpPolicyRegistry,
    StepUpAssuranceType,
    StepUpBinding,
    StepUpChallenge,
    StepUpChallengeId,
    StepUpCommandId,
    StepUpCommandResult,
    StepUpFailure,
    StepUpFailureCode,
    StepUpGrant,
    StepUpResource,
    StepUpResourceType,
    StepUpVerificationOutcome,
    StepUpVerificationReceipt,
    StepUpVerificationReceiptId,
    fail_step_up,
    require_step_up_utc,
    snapshot_bound_step_up_grant,
    snapshot_bound_step_up_grant_id,
    snapshot_step_up_binding,
    snapshot_step_up_challenge,
    snapshot_step_up_challenge_id,
    snapshot_step_up_command_id,
    snapshot_step_up_command_result,
    snapshot_step_up_grant,
    snapshot_step_up_receipt_id,
    snapshot_step_up_verification,
)
from raos.ports.step_up import (
    StepUpChallengeVerifier,
    StepUpEntropySource,
    StepUpLifecycleRepository,
    StepUpVerifier,
)


def _normalize_grant(candidate: StepUpGrant) -> StepUpGrant:
    try:
        return snapshot_step_up_grant(candidate)
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def _require_unchanged(before: object, after: object, code: StepUpFailureCode) -> None:
    try:
        unchanged = type(before) is type(after) and before == after
    except Exception:
        unchanged = False
    if not unchanged:
        fail_step_up(code)


def _require_zero_external_actions(
    verifier: StepUpChallengeVerifier, *, failure: StepUpFailureCode
) -> None:
    try:
        first = verifier.external_action_count
        second = verifier.external_action_count
    except Exception:
        fail_step_up(failure)
    if type(first) is not int or type(second) is not int or first != 0 or second != 0:
        fail_step_up(failure)


def _same_session(grant: StepUpGrant, session: Session) -> bool:
    return hmac.compare_digest(
        grant.session_id.fingerprint(), session.session_id.fingerprint()
    )


def _same_principal(grant: StepUpGrant, session: Session) -> bool:
    return hmac.compare_digest(
        grant.issuer.reveal(), session.principal.issuer.reveal()
    ) and hmac.compare_digest(
        grant.subject.reveal(), session.principal.subject.reveal()
    )


class StepUpGuard:
    """Require an active ST-0401 session before evaluating MFA assurance."""

    def __init__(
        self, *, session_service: AuthenticationService, verifier: StepUpVerifier
    ) -> None:
        if type(session_service) is not AuthenticationService:
            raise TypeError("session_service must be an exact AuthenticationService")
        if not isinstance(cast(object, verifier), StepUpVerifier):
            raise TypeError("verifier must implement StepUpVerifier")
        self._session_service = session_service
        self._verifier = verifier

    def require(self, *, session_id: SessionId, now: datetime) -> StepUpGrant:
        """Return matching, current MFA assurance or fail closed.

        Session loading, revocation, rotation, idle expiry, and absolute expiry
        are intentionally checked by ST-0401 before the verifier is invoked.
        """

        try:
            requested_session_id = snapshot_session_id(session_id)
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=requested_session_id, now=now
            )
        )
        observed_at = require_step_up_utc(now)

        outcome: object = None
        verifier_failure: StepUpFailureCode | None = None
        verifier_session = snapshot_session(session)
        verifier_baseline = snapshot_session(verifier_session)
        try:
            outcome = self._verifier.verify(session=verifier_session, now=observed_at)
            _require_unchanged(
                verifier_baseline,
                snapshot_session(verifier_session),
                StepUpFailureCode.VERIFIER_FAILURE,
            )
        except StepUpFailure as error:
            if (
                type(error) is StepUpFailure
                and type(error.code) is StepUpFailureCode
                and error.code is StepUpFailureCode.DEVELOPMENT_ONLY
            ):
                verifier_failure = StepUpFailureCode.DEVELOPMENT_ONLY
            else:
                verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        except Exception:
            verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        if verifier_failure is not None:
            fail_step_up(verifier_failure)

        if outcome is None:
            fail_step_up(StepUpFailureCode.CLAIM_MISSING)
        if type(outcome) is StepUpVerificationOutcome:
            if outcome is StepUpVerificationOutcome.REJECTED:
                fail_step_up(StepUpFailureCode.CLAIM_REJECTED)
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        if type(outcome) is not StepUpGrant:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        grant = _normalize_grant(outcome)

        if grant.assurance_type is not StepUpAssuranceType.MULTI_FACTOR:
            fail_step_up(StepUpFailureCode.ASSURANCE_TYPE_MISMATCH)
        if observed_at < grant.authenticated_at:
            fail_step_up(StepUpFailureCode.CLAIM_NOT_YET_VALID)
        if observed_at >= grant.expires_at:
            fail_step_up(StepUpFailureCode.CLAIM_EXPIRED)
        if not _same_session(grant, session):
            fail_step_up(StepUpFailureCode.SESSION_MISMATCH)
        if not _same_principal(grant, session):
            fail_step_up(StepUpFailureCode.PRINCIPAL_MISMATCH)
        return snapshot_step_up_grant(grant)


_IdentifierT = TypeVar(
    "_IdentifierT",
    StepUpChallengeId,
    StepUpVerificationReceiptId,
    BoundStepUpGrantId,
    StepUpCommandId,
)
_RepositoryValueT = TypeVar("_RepositoryValueT")


def _lifecycle_failure(
    operation: Callable[[], object],
    *,
    fallback: StepUpFailureCode = StepUpFailureCode.STORAGE_FAILURE,
) -> StepUpCommandResult:
    try:
        result = operation()
    except StepUpFailure as error:
        if type(error) is StepUpFailure and type(error.code) is StepUpFailureCode:
            fail_step_up(error.code)
        fail_step_up(fallback)
    except Exception:
        fail_step_up(fallback)
    if type(result) is not StepUpCommandResult:
        fail_step_up(fallback)
    try:
        return snapshot_step_up_command_result(result)
    except Exception:
        fail_step_up(fallback)


def _repository_read(
    operation: Callable[[], object], expected_type: type[_RepositoryValueT]
) -> _RepositoryValueT:
    try:
        result = operation()
    except StepUpFailure as error:
        if type(error) is StepUpFailure and type(error.code) is StepUpFailureCode:
            fail_step_up(error.code)
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    except Exception:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    if type(result) is not expected_type:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    detached: object
    try:
        if expected_type is StepUpChallenge:
            detached = snapshot_step_up_challenge(result)
        elif expected_type is StepUpVerificationReceipt:
            detached = snapshot_step_up_verification(result)
        elif expected_type is BoundStepUpGrant:
            detached = snapshot_bound_step_up_grant(result)
        else:
            fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    except Exception:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    return cast(_RepositoryValueT, detached)


def _repository_command(
    operation: Callable[[], object],
    tracked: tuple[tuple[object, Callable[[object], object]], ...],
) -> StepUpCommandResult:
    """Invoke a repository only with detached values that it cannot mutate."""

    baselines: list[object] = []
    try:
        baselines = [snapshotter(value) for value, snapshotter in tracked]
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    result = _lifecycle_failure(operation)
    try:
        for baseline, (value, snapshotter) in zip(baselines, tracked, strict=True):
            _require_unchanged(
                baseline,
                snapshotter(value),
                StepUpFailureCode.STORAGE_FAILURE,
            )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    return result


class DurableStepUpService:
    """Issue and consume exact single-use grants through an atomic repository.

    Lifetimes are always explicit caller inputs.  This application service does
    not choose an MFA factor, provider claim, HTTP delivery, role, or
    Production freshness policy.
    """

    def __init__(
        self,
        *,
        session_service: AuthenticationService,
        repository: StepUpLifecycleRepository,
        verifier: StepUpChallengeVerifier,
        entropy: StepUpEntropySource,
        policy: CriticalStepUpPolicyRegistry,
    ) -> None:
        if type(session_service) is not AuthenticationService:
            raise TypeError("session_service must be an exact AuthenticationService")
        if not isinstance(cast(object, repository), StepUpLifecycleRepository):
            raise TypeError("repository must implement StepUpLifecycleRepository")
        if not isinstance(cast(object, verifier), StepUpChallengeVerifier):
            raise TypeError("verifier must implement StepUpChallengeVerifier")
        if not isinstance(cast(object, entropy), StepUpEntropySource):
            raise TypeError("entropy must implement StepUpEntropySource")
        if type(policy) is not CriticalStepUpPolicyRegistry:
            raise TypeError("policy must be an exact CriticalStepUpPolicyRegistry")
        _require_zero_external_actions(
            verifier, failure=StepUpFailureCode.CLAIM_MALFORMED
        )
        self._session_service = session_service
        self._repository = repository
        self._verifier = verifier
        self._entropy = entropy
        self._policy = policy

    def _identifier(self, identifier_type: type[_IdentifierT]) -> _IdentifierT:
        try:
            value = self._entropy.token_bytes(32)
        except Exception:
            fail_step_up(StepUpFailureCode.ENTROPY_FAILURE)
        if type(value) is not bytes or len(value) != 32:
            fail_step_up(StepUpFailureCode.ENTROPY_FAILURE)
        try:
            return identifier_type.from_bytes(value)
        except StepUpFailure:
            raise
        except Exception:
            fail_step_up(StepUpFailureCode.ENTROPY_FAILURE)

    @staticmethod
    def _binding_for(
        *,
        session: Session,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
    ) -> StepUpBinding:
        if type(session) is not Session:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        return StepUpBinding(
            session_id=session.session_id,
            issuer=session.principal.issuer,
            subject=session.principal.subject,
            action=action,
            resource=StepUpResource(
                resource_type=resource_type,
                resource_id=resource_id,
            ),
        )

    @staticmethod
    def _require_session_binding(binding: StepUpBinding, session: Session) -> None:
        if type(binding) is not StepUpBinding or type(session) is not Session:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        if not hmac.compare_digest(
            binding.session_id.fingerprint(), session.session_id.fingerprint()
        ):
            fail_step_up(StepUpFailureCode.SESSION_MISMATCH)
        if not (
            hmac.compare_digest(
                binding.issuer.reveal(), session.principal.issuer.reveal()
            )
            and hmac.compare_digest(
                binding.subject.reveal(), session.principal.subject.reveal()
            )
        ):
            fail_step_up(StepUpFailureCode.PRINCIPAL_MISMATCH)

    def begin_challenge(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpCommandResult:
        observed_at = require_step_up_utc(now)
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
            received_session_id = snapshot_session_id(session_id)
            if type(resource_id) is not UUID:
                fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
            received_resource_id = UUID(str(resource_id))
        except StepUpFailure:
            raise
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        self._policy.require(action=action, resource_type=resource_type)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=received_session_id, now=observed_at
            )
        )
        binding = self._binding_for(
            session=session,
            action=action,
            resource_type=resource_type,
            resource_id=received_resource_id,
        )
        challenge = StepUpChallenge(
            challenge_id=self._identifier(StepUpChallengeId),
            binding=binding,
            created_at=observed_at,
            expires_at=expires_at,
        )
        repository_command = snapshot_step_up_command_id(received_command_id)
        repository_challenge = snapshot_step_up_challenge(challenge)
        return _repository_command(
            lambda: self._repository.create_challenge(
                command_id=repository_command, challenge=repository_challenge
            ),
            (
                (repository_command, snapshot_step_up_command_id),
                (repository_challenge, snapshot_step_up_challenge),
            ),
        )

    def verify_challenge(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        challenge_id: StepUpChallengeId,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpCommandResult:
        observed_at = require_step_up_utc(now)
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
            received_session_id = snapshot_session_id(session_id)
            received_challenge_id = snapshot_step_up_challenge_id(challenge_id)
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=received_session_id, now=observed_at
            )
        )
        repository_challenge_id = snapshot_step_up_challenge_id(received_challenge_id)
        challenge_id_baseline = snapshot_step_up_challenge_id(repository_challenge_id)
        challenge = _repository_read(
            lambda: self._repository.load_challenge(repository_challenge_id),
            StepUpChallenge,
        )
        _require_unchanged(
            challenge_id_baseline,
            snapshot_step_up_challenge_id(repository_challenge_id),
            StepUpFailureCode.STORAGE_FAILURE,
        )
        self._require_session_binding(challenge.binding, session)
        if observed_at < challenge.created_at or observed_at >= challenge.expires_at:
            fail_step_up(StepUpFailureCode.CHALLENGE_EXPIRED)
        normalized_expiry = require_step_up_utc(expires_at)
        if not observed_at < normalized_expiry <= challenge.expires_at:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        receipt_id = self._identifier(StepUpVerificationReceiptId)
        verifier_challenge = snapshot_step_up_challenge(challenge)
        verifier_challenge_baseline = snapshot_step_up_challenge(verifier_challenge)
        verifier_receipt_id = snapshot_step_up_receipt_id(receipt_id)
        verifier_receipt_baseline = snapshot_step_up_receipt_id(verifier_receipt_id)
        _require_zero_external_actions(
            self._verifier, failure=StepUpFailureCode.VERIFIER_FAILURE
        )
        verification: object = None
        verifier_failure: StepUpFailureCode | None = None
        try:
            verification = self._verifier.verify(
                challenge=verifier_challenge,
                receipt_id=verifier_receipt_id,
                now=observed_at,
                expires_at=normalized_expiry,
            )
        except StepUpFailure as error:
            if type(error) is StepUpFailure and type(error.code) is StepUpFailureCode:
                verifier_failure = error.code
            else:
                verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        except Exception:
            verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        try:
            _require_zero_external_actions(
                self._verifier, failure=StepUpFailureCode.VERIFIER_FAILURE
            )
            _require_unchanged(
                verifier_challenge_baseline,
                snapshot_step_up_challenge(verifier_challenge),
                StepUpFailureCode.VERIFIER_FAILURE,
            )
            _require_unchanged(
                verifier_receipt_baseline,
                snapshot_step_up_receipt_id(verifier_receipt_id),
                StepUpFailureCode.VERIFIER_FAILURE,
            )
        except StepUpFailure:
            verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        except Exception:
            verifier_failure = StepUpFailureCode.VERIFIER_FAILURE
        if verifier_failure is not None:
            fail_step_up(verifier_failure)
        try:
            verification = snapshot_step_up_verification(verification)
        except Exception:
            fail_step_up(StepUpFailureCode.VERIFIER_FAILURE)
        if (
            type(verification) is not StepUpVerificationReceipt
            or verification.receipt_id != receipt_id
            or verification.challenge_id != challenge.challenge_id
            or verification.binding != challenge.binding
            or verification.verified_at != observed_at
            or verification.expires_at != normalized_expiry
        ):
            fail_step_up(StepUpFailureCode.VERIFIER_FAILURE)
        repository_command = snapshot_step_up_command_id(received_command_id)
        repository_verification = snapshot_step_up_verification(verification)
        return _repository_command(
            lambda: self._repository.record_verification(
                command_id=repository_command,
                verification=repository_verification,
                now=observed_at,
            ),
            (
                (repository_command, snapshot_step_up_command_id),
                (repository_verification, snapshot_step_up_verification),
            ),
        )

    def issue_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        receipt_id: StepUpVerificationReceiptId,
        now: datetime,
        expires_at: datetime,
    ) -> StepUpCommandResult:
        observed_at = require_step_up_utc(now)
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
            received_session_id = snapshot_session_id(session_id)
            received_receipt_id = snapshot_step_up_receipt_id(receipt_id)
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=received_session_id, now=observed_at
            )
        )
        repository_receipt_id = snapshot_step_up_receipt_id(received_receipt_id)
        receipt_id_baseline = snapshot_step_up_receipt_id(repository_receipt_id)
        verification = _repository_read(
            lambda: self._repository.load_verification(repository_receipt_id),
            StepUpVerificationReceipt,
        )
        _require_unchanged(
            receipt_id_baseline,
            snapshot_step_up_receipt_id(repository_receipt_id),
            StepUpFailureCode.STORAGE_FAILURE,
        )
        self._require_session_binding(verification.binding, session)
        if (
            observed_at < verification.verified_at
            or observed_at >= verification.expires_at
        ):
            fail_step_up(StepUpFailureCode.RECEIPT_EXPIRED)
        normalized_expiry = require_step_up_utc(expires_at)
        if not observed_at < normalized_expiry <= verification.expires_at:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        grant = BoundStepUpGrant(
            grant_id=self._identifier(BoundStepUpGrantId),
            receipt_id=verification.receipt_id,
            binding=verification.binding,
            issued_at=observed_at,
            expires_at=normalized_expiry,
        )
        repository_command = snapshot_step_up_command_id(received_command_id)
        repository_grant = snapshot_bound_step_up_grant(grant)
        return _repository_command(
            lambda: self._repository.issue_grant(
                command_id=repository_command,
                grant=repository_grant,
                now=observed_at,
            ),
            (
                (repository_command, snapshot_step_up_command_id),
                (repository_grant, snapshot_bound_step_up_grant),
            ),
        )

    def consume_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        grant_id: BoundStepUpGrantId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
    ) -> StepUpCommandResult:
        observed_at = require_step_up_utc(now)
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
            received_session_id = snapshot_session_id(session_id)
            received_grant_id = snapshot_bound_step_up_grant_id(grant_id)
            if type(resource_id) is not UUID:
                fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
            received_resource_id = UUID(str(resource_id))
        except StepUpFailure:
            raise
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        self._policy.require(action=action, resource_type=resource_type)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=received_session_id, now=observed_at
            )
        )
        binding = self._binding_for(
            session=session,
            action=action,
            resource_type=resource_type,
            resource_id=received_resource_id,
        )
        repository_command = snapshot_step_up_command_id(received_command_id)
        repository_grant_id = snapshot_bound_step_up_grant_id(received_grant_id)
        repository_binding = snapshot_step_up_binding(binding)
        return _repository_command(
            lambda: self._repository.consume_grant(
                command_id=repository_command,
                grant_id=repository_grant_id,
                expected_binding=repository_binding,
                now=observed_at,
            ),
            (
                (repository_command, snapshot_step_up_command_id),
                (repository_grant_id, snapshot_bound_step_up_grant_id),
                (repository_binding, snapshot_step_up_binding),
            ),
        )

    def revoke_grant(
        self,
        *,
        command_id: StepUpCommandId,
        session_id: SessionId,
        grant_id: BoundStepUpGrantId,
        action: CriticalStepUpAction,
        resource_type: StepUpResourceType,
        resource_id: UUID,
        now: datetime,
    ) -> StepUpCommandResult:
        observed_at = require_step_up_utc(now)
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
            received_session_id = snapshot_session_id(session_id)
            received_grant_id = snapshot_bound_step_up_grant_id(grant_id)
            if type(resource_id) is not UUID:
                fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
            received_resource_id = UUID(str(resource_id))
        except StepUpFailure:
            raise
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        self._policy.require(action=action, resource_type=resource_type)
        session = snapshot_session(
            self._session_service.require_session(
                session_id=received_session_id, now=observed_at
            )
        )
        binding = self._binding_for(
            session=session,
            action=action,
            resource_type=resource_type,
            resource_id=received_resource_id,
        )
        repository_command = snapshot_step_up_command_id(received_command_id)
        repository_grant_id = snapshot_bound_step_up_grant_id(received_grant_id)
        repository_binding = snapshot_step_up_binding(binding)
        return _repository_command(
            lambda: self._repository.revoke_grant(
                command_id=repository_command,
                grant_id=repository_grant_id,
                expected_binding=repository_binding,
                now=observed_at,
            ),
            (
                (repository_command, snapshot_step_up_command_id),
                (repository_grant_id, snapshot_bound_step_up_grant_id),
                (repository_binding, snapshot_step_up_binding),
            ),
        )

    def recover(self, *, command_id: StepUpCommandId) -> StepUpCommandResult:
        try:
            received_command_id = snapshot_step_up_command_id(command_id)
        except Exception:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        repository_command = snapshot_step_up_command_id(received_command_id)
        return _repository_command(
            lambda: self._repository.recover(repository_command),
            ((repository_command, snapshot_step_up_command_id),),
        )


__all__ = ["DurableStepUpService", "StepUpGuard"]
