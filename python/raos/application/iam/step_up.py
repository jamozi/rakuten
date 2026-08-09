"""Transport-neutral active-session and step-up assurance guard."""

from __future__ import annotations

from datetime import datetime
import hmac

from raos.application.iam.authentication import AuthenticationService
from raos.domain.iam.authentication import Session, SessionId
from raos.domain.iam.step_up import (
    StepUpAssuranceType,
    StepUpFailure,
    StepUpFailureCode,
    StepUpGrant,
    StepUpVerificationOutcome,
    fail_step_up,
    require_step_up_utc,
)
from raos.ports.step_up import StepUpVerifier


def _normalize_grant(candidate: StepUpGrant) -> StepUpGrant:
    failed = False
    normalized: StepUpGrant | None = None
    try:
        normalized = StepUpGrant(
            session_id=candidate.session_id,
            issuer=candidate.issuer,
            subject=candidate.subject,
            assurance_type=candidate.assurance_type,
            authenticated_at=candidate.authenticated_at,
            expires_at=candidate.expires_at,
        )
    except Exception:
        failed = True
    if failed or normalized is None:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    return normalized


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
        if not isinstance(verifier, StepUpVerifier):
            raise TypeError("verifier must implement StepUpVerifier")
        self._session_service = session_service
        self._verifier = verifier

    def require(self, *, session_id: SessionId, now: datetime) -> StepUpGrant:
        """Return matching, current MFA assurance or fail closed.

        Session loading, revocation, rotation, idle expiry, and absolute expiry
        are intentionally checked by ST-0401 before the verifier is invoked.
        """

        session = self._session_service.require_session(session_id=session_id, now=now)
        observed_at = require_step_up_utc(now)

        outcome: object = None
        verifier_failure: StepUpFailureCode | None = None
        try:
            outcome = self._verifier.verify(session=session, now=observed_at)
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
        return grant


__all__ = ["StepUpGuard"]
