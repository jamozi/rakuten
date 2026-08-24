"""Factor-neutral assurance values for the ST-0402 step-up boundary."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
import re
from types import MappingProxyType
from collections.abc import Mapping
from typing import NoReturn, Self, SupportsIndex, final
from uuid import UUID

from raos.domain.iam.authentication import Issuer, SessionId, Subject


_REDACTED = "<redacted-step-up-value>"
_BASE64URL_32 = re.compile(r"^[A-Za-z0-9_-]{43}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


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
    ENTROPY_FAILURE = "ENTROPY_FAILURE"
    ACTION_RESOURCE_MISMATCH = "ACTION_RESOURCE_MISMATCH"
    CHALLENGE_UNKNOWN = "CHALLENGE_UNKNOWN"
    CHALLENGE_EXPIRED = "CHALLENGE_EXPIRED"
    CHALLENGE_REPLAY = "CHALLENGE_REPLAY"
    CHALLENGE_MISMATCH = "CHALLENGE_MISMATCH"
    RECEIPT_UNKNOWN = "RECEIPT_UNKNOWN"
    RECEIPT_EXPIRED = "RECEIPT_EXPIRED"
    RECEIPT_REPLAY = "RECEIPT_REPLAY"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    GRANT_UNKNOWN = "GRANT_UNKNOWN"
    GRANT_EXPIRED = "GRANT_EXPIRED"
    GRANT_REPLAY = "GRANT_REPLAY"
    GRANT_REVOKED = "GRANT_REVOKED"
    GRANT_MISMATCH = "GRANT_MISMATCH"
    COMMAND_UNKNOWN = "COMMAND_UNKNOWN"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"
    ROUTE_DISABLED = "ROUTE_DISABLED"


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


class CriticalStepUpAction(str, Enum):
    """Closed union of Canonical critical commands requiring fresh step-up.

    ``FINAL_APPROVE`` is intentionally included as the safer interpretation of
    the canonical Security design even though the role matrix only marks MFA.
    This registry never grants role or resource authorization; ST-0403 remains
    the owner of those decisions.
    """

    FINAL_APPROVE = "final_approve"
    PUBLISH = "publish"
    ROLLBACK = "rollback"
    ACTIVATE_PUBLICATION_KILL_SWITCH = "activate_publication_kill_switch"
    DEACTIVATE_PUBLICATION_KILL_SWITCH = "deactivate_publication_kill_switch"
    ACTIVATE_AFFILIATE_KILL_SWITCH = "activate_affiliate_kill_switch"
    DEACTIVATE_AFFILIATE_KILL_SWITCH = "deactivate_affiliate_kill_switch"
    COMMIT_REVENUE_IMPORT = "commit_revenue_import"
    MANAGE_AI_RELEASE = "manage_ai_release"
    MANAGE_SECRETS = "manage_secrets"
    BREAK_GLASS = "break_glass"


class StepUpResourceType(str, Enum):
    """Resource kinds to which a critical command grant can be bound."""

    ARTICLE_VERSION = "ARTICLE_VERSION"
    PUBLICATION_SNAPSHOT = "PUBLICATION_SNAPSHOT"
    PUBLICATION = "PUBLICATION"
    PUBLICATION_SCOPE = "PUBLICATION_SCOPE"
    AFFILIATE_SCOPE = "AFFILIATE_SCOPE"
    REVENUE_IMPORT = "REVENUE_IMPORT"
    AI_RELEASE = "AI_RELEASE"
    SECRET = "SECRET"
    BREAK_GLASS_ACCESS = "BREAK_GLASS_ACCESS"


_CRITICAL_ACTION_RESOURCES: Mapping[CriticalStepUpAction, StepUpResourceType] = (
    MappingProxyType(
        {
            CriticalStepUpAction.FINAL_APPROVE: StepUpResourceType.ARTICLE_VERSION,
            CriticalStepUpAction.PUBLISH: StepUpResourceType.PUBLICATION_SNAPSHOT,
            CriticalStepUpAction.ROLLBACK: StepUpResourceType.PUBLICATION,
            CriticalStepUpAction.ACTIVATE_PUBLICATION_KILL_SWITCH: (
                StepUpResourceType.PUBLICATION_SCOPE
            ),
            CriticalStepUpAction.DEACTIVATE_PUBLICATION_KILL_SWITCH: (
                StepUpResourceType.PUBLICATION_SCOPE
            ),
            CriticalStepUpAction.ACTIVATE_AFFILIATE_KILL_SWITCH: (
                StepUpResourceType.AFFILIATE_SCOPE
            ),
            CriticalStepUpAction.DEACTIVATE_AFFILIATE_KILL_SWITCH: (
                StepUpResourceType.AFFILIATE_SCOPE
            ),
            CriticalStepUpAction.COMMIT_REVENUE_IMPORT: StepUpResourceType.REVENUE_IMPORT,
            CriticalStepUpAction.MANAGE_AI_RELEASE: StepUpResourceType.AI_RELEASE,
            CriticalStepUpAction.MANAGE_SECRETS: StepUpResourceType.SECRET,
            CriticalStepUpAction.BREAK_GLASS: StepUpResourceType.BREAK_GLASS_ACCESS,
        }
    )
)


@final
class CriticalStepUpPolicyRegistry:
    """Non-configurable action/resource mapping; unknowns deny by construction."""

    __slots__ = ()

    def require(
        self, *, action: CriticalStepUpAction, resource_type: StepUpResourceType
    ) -> None:
        if (
            type(action) is not CriticalStepUpAction
            or type(resource_type) is not StepUpResourceType
            or _CRITICAL_ACTION_RESOURCES.get(action) is not resource_type
        ):
            fail_step_up(StepUpFailureCode.ACTION_RESOURCE_MISMATCH)

    def resource_for(self, action: CriticalStepUpAction) -> StepUpResourceType:
        if type(action) is not CriticalStepUpAction:
            fail_step_up(StepUpFailureCode.ACTION_RESOURCE_MISMATCH)
        return _CRITICAL_ACTION_RESOURCES[action]


def _encode_identifier(value: object) -> str:
    if type(value) is not bytes or len(value) != 32:
        fail_step_up(StepUpFailureCode.ENTROPY_FAILURE)
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _require_identifier(value: object) -> str:
    if type(value) is not str or _BASE64URL_32.fullmatch(value) is None:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    decoded: bytes | None = None
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except ValueError, UnicodeError:
        pass
    if decoded is None or len(decoded) != 32 or _encode_identifier(decoded) != value:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class _LifecycleIdentifier:
    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_value", _require_identifier(self._value))

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        return cls(_encode_identifier(value))

    def reveal(self) -> str:
        return self._value

    def fingerprint(self) -> str:
        return hashlib.sha256(self._value.encode("ascii")).hexdigest()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("step-up lifecycle identifier serialization is not supported")


@final
class StepUpChallengeId(_LifecycleIdentifier):
    __slots__ = ()


@final
class StepUpVerificationReceiptId(_LifecycleIdentifier):
    __slots__ = ()


@final
class BoundStepUpGrantId(_LifecycleIdentifier):
    __slots__ = ()


@final
class StepUpCommandId(_LifecycleIdentifier):
    __slots__ = ()


@dataclass(frozen=True, slots=True, repr=False)
class StepUpResource:
    resource_type: StepUpResourceType
    resource_id: UUID

    def __post_init__(self) -> None:
        if (
            type(self.resource_type) is not StepUpResourceType
            or type(self.resource_id) is not UUID
            or self.resource_id.int == 0
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)

    def __repr__(self) -> str:
        return f"StepUpResource({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED


@dataclass(frozen=True, slots=True, repr=False)
class StepUpBinding:
    session_id: SessionId
    issuer: Issuer
    subject: Subject
    action: CriticalStepUpAction
    resource: StepUpResource

    def __post_init__(self) -> None:
        if (
            type(self.session_id) is not SessionId
            or type(self.issuer) is not Issuer
            or type(self.subject) is not Subject
            or type(self.action) is not CriticalStepUpAction
            or type(self.resource) is not StepUpResource
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        CriticalStepUpPolicyRegistry().require(
            action=self.action, resource_type=self.resource.resource_type
        )

    def __repr__(self) -> str:
        return f"StepUpBinding({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED


def _require_interval(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    normalized_start = require_step_up_utc(start)
    normalized_end = require_step_up_utc(end)
    if normalized_start >= normalized_end:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    return normalized_start, normalized_end


@dataclass(frozen=True, slots=True, repr=False)
class StepUpChallenge:
    challenge_id: StepUpChallengeId
    binding: StepUpBinding
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.challenge_id) is not StepUpChallengeId
            or type(self.binding) is not StepUpBinding
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        created_at, expires_at = _require_interval(self.created_at, self.expires_at)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)

    def __repr__(self) -> str:
        return f"StepUpChallenge({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class StepUpVerificationReceipt:
    receipt_id: StepUpVerificationReceiptId
    challenge_id: StepUpChallengeId
    binding: StepUpBinding
    assurance_type: StepUpAssuranceType
    verified_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.receipt_id) is not StepUpVerificationReceiptId
            or type(self.challenge_id) is not StepUpChallengeId
            or type(self.binding) is not StepUpBinding
            or type(self.assurance_type) is not StepUpAssuranceType
            or self.assurance_type is not StepUpAssuranceType.MULTI_FACTOR
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        verified_at, expires_at = _require_interval(self.verified_at, self.expires_at)
        object.__setattr__(self, "verified_at", verified_at)
        object.__setattr__(self, "expires_at", expires_at)

    def __repr__(self) -> str:
        return f"StepUpVerificationReceipt({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class BoundStepUpGrant:
    grant_id: BoundStepUpGrantId
    receipt_id: StepUpVerificationReceiptId
    binding: StepUpBinding
    issued_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.grant_id) is not BoundStepUpGrantId
            or type(self.receipt_id) is not StepUpVerificationReceiptId
            or type(self.binding) is not StepUpBinding
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        issued_at, expires_at = _require_interval(self.issued_at, self.expires_at)
        object.__setattr__(self, "issued_at", issued_at)
        object.__setattr__(self, "expires_at", expires_at)

    def __repr__(self) -> str:
        return f"BoundStepUpGrant({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class StepUpAuthorizationReceipt:
    grant_id: BoundStepUpGrantId
    binding: StepUpBinding
    authorized_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.grant_id) is not BoundStepUpGrantId
            or type(self.binding) is not StepUpBinding
        ):
            fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
        object.__setattr__(
            self, "authorized_at", require_step_up_utc(self.authorized_at)
        )

    def __repr__(self) -> str:
        return f"StepUpAuthorizationReceipt({_REDACTED})"


class StepUpOperation(str, Enum):
    BEGIN_CHALLENGE = "BEGIN_CHALLENGE"
    VERIFY_CHALLENGE = "VERIFY_CHALLENGE"
    ISSUE_GRANT = "ISSUE_GRANT"
    CONSUME_GRANT = "CONSUME_GRANT"
    REVOKE_GRANT = "REVOKE_GRANT"


class StepUpAuditOutcome(str, Enum):
    SUCCEEDED = "SUCCEEDED"


@dataclass(frozen=True, slots=True, repr=False)
class StepUpAuditRecord:
    sequence: int
    command_fingerprint: str
    operation: StepUpOperation
    outcome: StepUpAuditOutcome
    binding: StepUpBinding
    occurred_at: datetime
    previous_digest: str
    digest: str

    def __post_init__(self) -> None:
        if (
            type(self.sequence) is not int
            or self.sequence <= 0
            or type(self.command_fingerprint) is not str
            or _SHA256.fullmatch(self.command_fingerprint) is None
            or type(self.operation) is not StepUpOperation
            or type(self.outcome) is not StepUpAuditOutcome
            or type(self.binding) is not StepUpBinding
            or type(self.previous_digest) is not str
            or _SHA256.fullmatch(self.previous_digest) is None
            or type(self.digest) is not str
            or _SHA256.fullmatch(self.digest) is None
        ):
            fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
        object.__setattr__(self, "occurred_at", require_step_up_utc(self.occurred_at))

    def __repr__(self) -> str:
        return f"StepUpAuditRecord({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class StepUpCommandResult:
    command_id: StepUpCommandId
    operation: StepUpOperation
    audit: StepUpAuditRecord
    challenge: StepUpChallenge | None = None
    verification: StepUpVerificationReceipt | None = None
    grant: BoundStepUpGrant | None = None
    authorization: StepUpAuthorizationReceipt | None = None

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not StepUpCommandId
            or type(self.operation) is not StepUpOperation
            or type(self.audit) is not StepUpAuditRecord
            or self.audit.operation is not self.operation
            or self.audit.command_fingerprint != self.command_id.fingerprint()
        ):
            fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
        values = (self.challenge, self.verification, self.grant, self.authorization)
        if sum(value is not None for value in values) != 1:
            fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
        expected_types: dict[StepUpOperation, type[object]] = {
            StepUpOperation.BEGIN_CHALLENGE: StepUpChallenge,
            StepUpOperation.VERIFY_CHALLENGE: StepUpVerificationReceipt,
            StepUpOperation.ISSUE_GRANT: BoundStepUpGrant,
            StepUpOperation.CONSUME_GRANT: StepUpAuthorizationReceipt,
            StepUpOperation.REVOKE_GRANT: BoundStepUpGrant,
        }
        selected = next(value for value in values if value is not None)
        if type(selected) is not expected_types[self.operation]:
            fail_step_up(StepUpFailureCode.STORAGE_FAILURE)

    def __repr__(self) -> str:
        return f"StepUpCommandResult({_REDACTED})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("step-up command result serialization is not supported")


def snapshot_step_up_grant(value: object) -> StepUpGrant:
    """Return one exact detached legacy assurance grant."""

    if type(value) is not StepUpGrant:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpGrant(
            session_id=SessionId(value.session_id.reveal()),
            issuer=Issuer(value.issuer.reveal()),
            subject=Subject(value.subject.reveal()),
            assurance_type=value.assurance_type,
            authenticated_at=value.authenticated_at,
            expires_at=value.expires_at,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_challenge_id(value: object) -> StepUpChallengeId:
    if type(value) is not StepUpChallengeId:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpChallengeId(value.reveal())
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_receipt_id(value: object) -> StepUpVerificationReceiptId:
    if type(value) is not StepUpVerificationReceiptId:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpVerificationReceiptId(value.reveal())
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_bound_step_up_grant_id(value: object) -> BoundStepUpGrantId:
    if type(value) is not BoundStepUpGrantId:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return BoundStepUpGrantId(value.reveal())
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_command_id(value: object) -> StepUpCommandId:
    if type(value) is not StepUpCommandId:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpCommandId(value.reveal())
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_resource(value: object) -> StepUpResource:
    if type(value) is not StepUpResource:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpResource(
            resource_type=value.resource_type,
            resource_id=UUID(str(value.resource_id)),
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_binding(value: object) -> StepUpBinding:
    if type(value) is not StepUpBinding:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpBinding(
            session_id=SessionId(value.session_id.reveal()),
            issuer=Issuer(value.issuer.reveal()),
            subject=Subject(value.subject.reveal()),
            action=value.action,
            resource=snapshot_step_up_resource(value.resource),
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_challenge(value: object) -> StepUpChallenge:
    if type(value) is not StepUpChallenge:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpChallenge(
            challenge_id=snapshot_step_up_challenge_id(value.challenge_id),
            binding=snapshot_step_up_binding(value.binding),
            created_at=value.created_at,
            expires_at=value.expires_at,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_verification(
    value: object,
) -> StepUpVerificationReceipt:
    if type(value) is not StepUpVerificationReceipt:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpVerificationReceipt(
            receipt_id=snapshot_step_up_receipt_id(value.receipt_id),
            challenge_id=snapshot_step_up_challenge_id(value.challenge_id),
            binding=snapshot_step_up_binding(value.binding),
            assurance_type=value.assurance_type,
            verified_at=value.verified_at,
            expires_at=value.expires_at,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_bound_step_up_grant(value: object) -> BoundStepUpGrant:
    if type(value) is not BoundStepUpGrant:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return BoundStepUpGrant(
            grant_id=snapshot_bound_step_up_grant_id(value.grant_id),
            receipt_id=snapshot_step_up_receipt_id(value.receipt_id),
            binding=snapshot_step_up_binding(value.binding),
            issued_at=value.issued_at,
            expires_at=value.expires_at,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_authorization(
    value: object,
) -> StepUpAuthorizationReceipt:
    if type(value) is not StepUpAuthorizationReceipt:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)
    try:
        return StepUpAuthorizationReceipt(
            grant_id=snapshot_bound_step_up_grant_id(value.grant_id),
            binding=snapshot_step_up_binding(value.binding),
            authorized_at=value.authorized_at,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.CLAIM_MALFORMED)


def snapshot_step_up_audit(value: object) -> StepUpAuditRecord:
    if type(value) is not StepUpAuditRecord:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    try:
        return StepUpAuditRecord(
            sequence=value.sequence,
            command_fingerprint=value.command_fingerprint,
            operation=value.operation,
            outcome=value.outcome,
            binding=snapshot_step_up_binding(value.binding),
            occurred_at=value.occurred_at,
            previous_digest=value.previous_digest,
            digest=value.digest,
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)


def snapshot_step_up_command_result(value: object) -> StepUpCommandResult:
    """Deep-copy one repository result before it crosses a trust boundary."""

    if type(value) is not StepUpCommandResult:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)
    try:
        return StepUpCommandResult(
            command_id=snapshot_step_up_command_id(value.command_id),
            operation=value.operation,
            audit=snapshot_step_up_audit(value.audit),
            challenge=(
                None
                if value.challenge is None
                else snapshot_step_up_challenge(value.challenge)
            ),
            verification=(
                None
                if value.verification is None
                else snapshot_step_up_verification(value.verification)
            ),
            grant=(
                None
                if value.grant is None
                else snapshot_bound_step_up_grant(value.grant)
            ),
            authorization=(
                None
                if value.authorization is None
                else snapshot_step_up_authorization(value.authorization)
            ),
        )
    except StepUpFailure:
        raise
    except Exception:
        fail_step_up(StepUpFailureCode.STORAGE_FAILURE)


__all__ = [
    "BoundStepUpGrant",
    "BoundStepUpGrantId",
    "CriticalStepUpAction",
    "CriticalStepUpPolicyRegistry",
    "StepUpAssuranceType",
    "StepUpAuditOutcome",
    "StepUpAuditRecord",
    "StepUpAuthorizationReceipt",
    "StepUpBinding",
    "StepUpChallenge",
    "StepUpChallengeId",
    "StepUpCommandId",
    "StepUpCommandResult",
    "StepUpFailure",
    "StepUpFailureCode",
    "StepUpGrant",
    "StepUpOperation",
    "StepUpResource",
    "StepUpResourceType",
    "StepUpVerificationReceipt",
    "StepUpVerificationReceiptId",
    "StepUpVerificationOutcome",
    "fail_step_up",
    "require_step_up_utc",
    "snapshot_bound_step_up_grant",
    "snapshot_bound_step_up_grant_id",
    "snapshot_step_up_audit",
    "snapshot_step_up_authorization",
    "snapshot_step_up_binding",
    "snapshot_step_up_challenge",
    "snapshot_step_up_challenge_id",
    "snapshot_step_up_command_id",
    "snapshot_step_up_command_result",
    "snapshot_step_up_grant",
    "snapshot_step_up_receipt_id",
    "snapshot_step_up_resource",
    "snapshot_step_up_verification",
]
