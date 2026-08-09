"""Exact-development scripted source of synthetic verified assurance."""

from __future__ import annotations

from datetime import datetime
import hmac
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.authentication import Session
from raos.domain.iam.step_up import (
    StepUpFailureCode,
    StepUpGrant,
    StepUpVerificationOutcome,
    fail_step_up,
    require_step_up_utc,
)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_step_up(StepUpFailureCode.DEVELOPMENT_ONLY)
    return environment


@final
class DevelopmentScriptedStepUpVerifier:
    """Deterministically expose only pre-verified synthetic development grants."""

    __slots__ = ("_environment", "_grants")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        grants: tuple[StepUpGrant, ...],
    ) -> None:
        self._environment = _require_development(environment)
        if type(grants) is not tuple or any(
            type(grant) is not StepUpGrant for grant in grants
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        fingerprints = tuple(grant.session_id.fingerprint() for grant in grants)
        if len(fingerprints) != len(set(fingerprints)):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        self._grants = grants

    def verify(
        self, *, session: Session, now: datetime
    ) -> StepUpGrant | StepUpVerificationOutcome | None:
        """Return the pre-scripted grant for an exact session, if present."""

        self._guard()
        if type(session) is not Session:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        require_step_up_utc(now)
        session_fingerprint = session.session_id.fingerprint()
        for grant in self._grants:
            if hmac.compare_digest(session_fingerprint, grant.session_id.fingerprint()):
                return grant
        return None

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return (
            "DevelopmentScriptedStepUpVerifier("
            "environment='ENV-DEV', grants=<redacted>)"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("development step-up verifier serialization is not supported")


__all__ = ["DevelopmentScriptedStepUpVerifier"]
