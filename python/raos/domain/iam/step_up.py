"""Factor-neutral assurance values for the ST-0402 step-up boundary."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import NoReturn, SupportsIndex, final

from raos.domain.iam.authentication import Issuer, SessionId, Subject


_REDACTED = "<redacted-step-up-value>"


class StepUpAssuranceType(str, Enum):
    """Normalized assurance classifications understood by the local guard."""

    MULTI_FACTOR = "MULTI_FACTOR"
    UNSUPPORTED = "UNSUPPORTED"


class StepUpVerificationOutcome(str, Enum):
    """A verifier outcome that intentionally carries no claim data."""

    REJECTED = "REJECTED"


class StepUpFailureCode(str, Enum):
    """Stable, sanitized step-up failure classifications."""

    CLAIM_MISSING = "CLAIM_MISSING"
    CLAIM_REJECTED = "CLAIM_REJECTED"
    CLAIM_MALFORMED = "CLAIM_MALFORMED"
    CLAIM_NOT_YET_VALID = "CLAIM_NOT_YET_VALID"
    CLAIM_EXPIRED = "CLAIM_EXPIRED"
    SESSION_MISMATCH = "SESSION_MISMATCH"
    PRINCIPAL_MISMATCH = "PRINCIPAL_MISMATCH"
    ASSURANCE_TYPE_MISMATCH = "ASSURANCE_TYPE_MISMATCH"
    VERIFIER_FAILURE = "VERIFIER_FAILURE"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"


@final
class StepUpFailure(RuntimeError):
    """Immutable failure that retains only one stable classification."""

    __slots__ = ("_code", "_sealed")
    _code: StepUpFailureCode
    _sealed: bool

    def __init__(self, code: StepUpFailureCode) -> None:
        if type(code) is not StepUpFailureCode:
            raise TypeError("code must be an exact StepUpFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> StepUpFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("StepUpFailure is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("StepUpFailure is immutable")
        super().__delattr__(name)

    def __repr__(self) -> str:
        return f"StepUpFailure(code={self.code!r})"


def fail_step_up(code: StepUpFailureCode) -> NoReturn:
    """Raise one sanitized step-up failure without an exception chain."""

    raise StepUpFailure(code) from None


def require_step_up_utc(value: object) -> datetime:
    """Normalize an exact UTC instant without echoing rejected input."""

    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(None)
    ):
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    return value.replace(tzinfo=timezone.utc)


@final
class StepUpGrant:
    """Immutable verified assurance bound to one session and principal.

    The grant deliberately carries no provider, factor, credential, challenge,
    or policy-action data. Its validity interval must be supplied explicitly by
    the verifier; ST-0402 does not choose a default freshness lifetime.
    """

    __slots__ = (
        "_session_id",
        "_issuer",
        "_subject",
        "_assurance_type",
        "_authenticated_at",
        "_expires_at",
        "_sealed",
    )
    _session_id: SessionId
    _issuer: Issuer
    _subject: Subject
    _assurance_type: StepUpAssuranceType
    _authenticated_at: datetime
    _expires_at: datetime
    _sealed: bool

    def __init__(
        self,
        *,
        session_id: SessionId,
        issuer: Issuer,
        subject: Subject,
        assurance_type: StepUpAssuranceType,
        authenticated_at: datetime,
        expires_at: datetime,
    ) -> None:
        if (
            type(session_id) is not SessionId
            or type(issuer) is not Issuer
            or type(subject) is not Subject
            or type(assurance_type) is not StepUpAssuranceType
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        normalized_authenticated_at = require_step_up_utc(authenticated_at)
        normalized_expires_at = require_step_up_utc(expires_at)
        if normalized_authenticated_at >= normalized_expires_at:
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        object.__setattr__(self, "_session_id", session_id)
        object.__setattr__(self, "_issuer", issuer)
        object.__setattr__(self, "_subject", subject)
        object.__setattr__(self, "_assurance_type", assurance_type)
        object.__setattr__(self, "_authenticated_at", normalized_authenticated_at)
        object.__setattr__(self, "_expires_at", normalized_expires_at)
        object.__setattr__(self, "_sealed", True)

    @property
    def session_id(self) -> SessionId:
        return self._session_id

    @property
    def issuer(self) -> Issuer:
        return self._issuer

    @property
    def subject(self) -> Subject:
        return self._subject

    @property
    def assurance_type(self) -> StepUpAssuranceType:
        return self._assurance_type

    @property
    def authenticated_at(self) -> datetime:
        return self._authenticated_at

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("StepUpGrant is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("StepUpGrant is immutable")
        super().__delattr__(name)

    def __eq__(self, other: object) -> bool:
        if type(other) is not StepUpGrant:
            return False
        return (
            self.session_id == other.session_id
            and self.issuer == other.issuer
            and self.subject == other.subject
            and self.assurance_type is other.assurance_type
            and self.authenticated_at == other.authenticated_at
            and self.expires_at == other.expires_at
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.session_id,
                self.issuer,
                self.subject,
                self.assurance_type,
                self.authenticated_at,
                self.expires_at,
            )
        )

    def __repr__(self) -> str:
        return f"StepUpGrant({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("step-up grant serialization is not supported")


__all__ = [
    "StepUpAssuranceType",
    "StepUpFailure",
    "StepUpFailureCode",
    "StepUpGrant",
    "StepUpVerificationOutcome",
    "fail_step_up",
    "require_step_up_utc",
]
