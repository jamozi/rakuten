"""Closed, redacted idempotency values for the ST-0308 boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import re
from typing import TYPE_CHECKING, Final, NoReturn, SupportsIndex, TypeAlias
import unicodedata
from uuid import UUID

from raos.domain.shared.identity import OpaqueResourceId, require_uuid
from raos.domain.shared.json_values import FrozenJsonObject

if TYPE_CHECKING:
    from raos.domain.ops.ids import ObjectArtifactId


_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RESOURCE_TYPE = re.compile(r"[a-z][a-z0-9_]{1,63}\Z", re.ASCII)
_HANDLE_ISSUER: Final[object] = object()


def _invalid() -> NoReturn:
    raise ValueError("INVALID_IDEMPOTENCY_VALUE") from None


def _utc(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not timezone.utc or value.fold:
        _invalid()
    return value


def _registered_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or unicodedata.normalize("NFC", value) != value
        or any(unicodedata.category(character).startswith("C") for character in value)
    ):
        _invalid()
    return value


def _is_object_artifact_id(value: object) -> bool:
    """Require the exact module-owned nominal type, never a name/module spoof."""

    # This local consumer import follows the matrix's cross-module typed-ID rule
    # without introducing an OPS repository dependency or a module import cycle.
    from raos.domain.ops.ids import ObjectArtifactId

    return type(value) is ObjectArtifactId


@dataclass(frozen=True, slots=True, repr=False)
class ActorFingerprint:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _HASH.fullmatch(self.value) is None:
            _invalid()

    def __repr__(self) -> str:
        return "ActorFingerprint(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RouteKey:
    """Application-registry route key; construction never accepts free-form transport data."""

    value: str

    def __post_init__(self) -> None:
        _registered_text(self.value, maximum=200)

    def __repr__(self) -> str:
        return "RouteKey(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyKey:
    value: str

    def __post_init__(self) -> None:
        _registered_text(self.value, maximum=200)

    def __repr__(self) -> str:
        return "IdempotencyKey(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RequestHash:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _HASH.fullmatch(self.value) is None:
            _invalid()

    def __repr__(self) -> str:
        return "RequestHash(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyIdentity:
    actor_fingerprint: ActorFingerprint
    route_key: RouteKey
    idempotency_key: IdempotencyKey

    def __post_init__(self) -> None:
        if (
            type(self.actor_fingerprint) is not ActorFingerprint
            or type(self.route_key) is not RouteKey
            or type(self.idempotency_key) is not IdempotencyKey
        ):
            _invalid()

    def __repr__(self) -> str:
        return "IdempotencyIdentity(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyClaim:
    identity: IdempotencyIdentity
    request_hash: RequestHash
    expires_at: datetime

    def __post_init__(self) -> None:
        if type(self.identity) is not IdempotencyIdentity:
            _invalid()
        if type(self.request_hash) is not RequestHash:
            _invalid()
        _utc(self.expires_at)

    def __repr__(self) -> str:
        return "IdempotencyClaim(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False, init=False)
class IdempotencyClaimHandle:
    """Adapter-issued, transaction-bound capability with no public field accessors."""

    __record_id: UUID
    __identity: IdempotencyIdentity
    __request_hash: RequestHash
    __transaction_id: UUID

    def __init__(
        self,
        record_id: UUID,
        identity: IdempotencyIdentity,
        request_hash: RequestHash,
        transaction_id: UUID,
        *,
        _issuer: object,
    ) -> None:
        if _issuer is not _HANDLE_ISSUER:
            _invalid()
        require_uuid(record_id)
        require_uuid(transaction_id)
        if type(identity) is not IdempotencyIdentity:
            _invalid()
        if type(request_hash) is not RequestHash:
            _invalid()
        object.__setattr__(self, "_IdempotencyClaimHandle__record_id", record_id)
        object.__setattr__(self, "_IdempotencyClaimHandle__identity", identity)
        object.__setattr__(self, "_IdempotencyClaimHandle__request_hash", request_hash)
        object.__setattr__(
            self, "_IdempotencyClaimHandle__transaction_id", transaction_id
        )

    def __repr__(self) -> str:
        return "IdempotencyClaimHandle(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("idempotency handle serialization is not supported")

    def adapter_fields(
        self, transaction_id: UUID
    ) -> tuple[UUID, IdempotencyIdentity, RequestHash]:
        """Return the exact completion CAS identity to the owning adapter only."""

        require_uuid(transaction_id)
        if transaction_id != self.__transaction_id:
            _invalid()
        return self.__record_id, self.__identity, self.__request_hash

    def _adapter_fields(
        self, transaction_id: UUID
    ) -> tuple[UUID, IdempotencyIdentity, RequestHash]:
        """Compatibility wrapper for the predecessor adapter-private seam."""

        return self.adapter_fields(transaction_id)


def issue_claim_handle(
    *,
    record_id: UUID,
    identity: IdempotencyIdentity,
    request_hash: RequestHash,
    transaction_id: UUID,
) -> IdempotencyClaimHandle:
    """Adapter-private issuer; intentionally absent from ``__all__``."""

    return IdempotencyClaimHandle(
        record_id,
        identity,
        request_hash,
        transaction_id,
        _issuer=_HANDLE_ISSUER,
    )


_issue_claim_handle = issue_claim_handle


@dataclass(frozen=True, slots=True)
class ResourceRef:
    resource_type: str
    resource_id: OpaqueResourceId

    def __post_init__(self) -> None:
        if (
            type(self.resource_type) is not str
            or _RESOURCE_TYPE.fullmatch(self.resource_type) is None
        ):
            _invalid()
        if type(self.resource_id) is not OpaqueResourceId:
            _invalid()


class IdempotencyOutcomeDisposition(str, Enum):
    """Caller assertion required before a terminal idempotency write."""

    SUCCESS = "SUCCESS"
    ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE = (
        "ROUTE_APPROVED_DETERMINISTIC_BUSINESS_FAILURE"
    )


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyOutcome:
    response_status: int
    response_body: FrozenJsonObject | None = None
    response_artifact_id: ObjectArtifactId | None = None
    resource: ResourceRef | None = None
    disposition: IdempotencyOutcomeDisposition = IdempotencyOutcomeDisposition.SUCCESS

    def __post_init__(self) -> None:
        if (
            type(self.response_status) is not int
            or not 100 <= self.response_status <= 599
        ):
            _invalid()
        if (
            self.response_body is not None
            and type(self.response_body) is not FrozenJsonObject
        ):
            _invalid()
        if self.response_artifact_id is not None and not _is_object_artifact_id(
            self.response_artifact_id
        ):
            _invalid()
        if self.response_body is not None and self.response_artifact_id is not None:
            _invalid()
        if self.resource is not None and type(self.resource) is not ResourceRef:
            _invalid()
        if type(self.disposition) is not IdempotencyOutcomeDisposition:
            _invalid()

    def __repr__(self) -> str:
        return "IdempotencyOutcome(<redacted>)"


@dataclass(frozen=True, slots=True)
class ClaimGranted:
    handle: IdempotencyClaimHandle

    def __post_init__(self) -> None:
        if type(self.handle) is not IdempotencyClaimHandle:
            _invalid()


@dataclass(frozen=True, slots=True)
class ReplaySucceeded:
    outcome: IdempotencyOutcome

    def __post_init__(self) -> None:
        if type(self.outcome) is not IdempotencyOutcome:
            _invalid()


@dataclass(frozen=True, slots=True)
class ReplayFailed:
    outcome: IdempotencyOutcome

    def __post_init__(self) -> None:
        if type(self.outcome) is not IdempotencyOutcome:
            _invalid()


@dataclass(frozen=True, slots=True)
class ClaimInProgress:
    expires_at: datetime

    def __post_init__(self) -> None:
        _utc(self.expires_at)


@dataclass(frozen=True, slots=True)
class PayloadMismatch:
    """Mismatch result that intentionally discloses no stored hash."""


@dataclass(frozen=True, slots=True)
class ClaimNotFound:
    """Lookup-only result; lookup can never grant ownership."""


IdempotencyClaimDecision: TypeAlias = (
    ClaimGranted | ReplaySucceeded | ReplayFailed | ClaimInProgress | PayloadMismatch
)
IdempotencyLookupDecision: TypeAlias = (
    ReplaySucceeded | ReplayFailed | ClaimInProgress | PayloadMismatch | ClaimNotFound
)


__all__ = [
    "ActorFingerprint",
    "ClaimGranted",
    "ClaimInProgress",
    "ClaimNotFound",
    "IdempotencyClaim",
    "IdempotencyClaimDecision",
    "IdempotencyClaimHandle",
    "IdempotencyIdentity",
    "IdempotencyKey",
    "IdempotencyLookupDecision",
    "IdempotencyOutcome",
    "IdempotencyOutcomeDisposition",
    "PayloadMismatch",
    "ReplayFailed",
    "ReplaySucceeded",
    "RequestHash",
    "ResourceRef",
    "RouteKey",
]
