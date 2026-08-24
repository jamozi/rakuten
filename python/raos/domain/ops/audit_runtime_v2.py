"""Durable, authorization-bound audit records for ST-0405 V2.

This module is pure.  It accepts only the fixed fields already owned by the
ST-0405 audit event and the exact hashes emitted by the durable ST-0403
authorization service.  It has no database, filesystem, network, retention,
export, or outward query authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex
from uuid import UUID

from raos.domain.iam.authorization import MatrixAction, ResourceScopeKind
from raos.domain.ops.audit import (
    AuditActorType,
    AuditEvent,
    AuditOutcome,
    AuditSeverity,
)


AUDIT_RUNTIME_SCHEMA_VERSION_V2 = "ST0405_RECORDED_AUDIT_RUNTIME_V2"
AUDIT_RUNTIME_GENESIS_SHA256_V2 = "0" * 64
AUDIT_QUERY_BLOCK_REASON_V2 = "ST0403_OPS012_SITE_SCOPE_CONFLICT"
AUDIT_RUNTIME_CONTRACT_SHA256_V2 = (
    "b39b35db127592ca9bc59b3b45796036731a55d617459095a1382fd3b7559eb6"
)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,126}[A-Za-z0-9])?\Z", re.ASCII)
_MAX_SEQUENCE = (1 << 63) - 1
_REDACTED = "<redacted-durable-audit-runtime-v2>"


class _RedactedValue:
    __slots__ = ()

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit runtime values cannot be serialized")


class AuditRuntimeFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    AUTHORIZATION_MISMATCH = "AUTHORIZATION_MISMATCH"
    QUERY_AUTHORIZATION_UNAVAILABLE = "QUERY_AUTHORIZATION_UNAVAILABLE"
    STORE_UNAVAILABLE = "STORE_UNAVAILABLE"
    STORAGE_ROLLED_BACK = "STORAGE_ROLLED_BACK"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    SCHEMA_DRIFT = "SCHEMA_DRIFT"


class AuditRuntimeFailureV2(RuntimeError):
    """Closed failure that can safely receive Python traceback metadata."""

    __slots__ = ("_code",)

    def __init__(self, code: AuditRuntimeFailureCodeV2) -> None:
        if type(code) is not AuditRuntimeFailureCodeV2:
            raise TypeError("invalid audit runtime failure code")
        super().__init__(code.value)
        self._code = code

    @property
    def code(self) -> AuditRuntimeFailureCodeV2:
        return self._code

    def __repr__(self) -> str:
        return f"AuditRuntimeFailureV2(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("audit runtime failures cannot be serialized")


def fail_audit_runtime_v2(
    code: AuditRuntimeFailureCodeV2 = AuditRuntimeFailureCodeV2.INVALID_ARGUMENT,
) -> NoReturn:
    raise AuditRuntimeFailureV2(code) from None


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_audit_runtime_v2()
    return value


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_audit_runtime_v2()
    return value


def _token(value: object) -> str:
    if type(value) is not str or _TOKEN.fullmatch(value) is None:
        fail_audit_runtime_v2()
    return value


def _optional_token(value: object) -> str | None:
    if value is None:
        return None
    return _token(value)


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_audit_runtime_v2()
    return value


def _utc_text(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        fail_audit_runtime_v2()


def canonical_sha256_v2(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class AuditAuthorizationProofV2(_RedactedValue):
    command_id_fingerprint: str
    request_digest: str
    session_fingerprint: str
    authorization_audit_digest: str

    def __post_init__(self) -> None:
        _sha256(self.command_id_fingerprint)
        _sha256(self.request_digest)
        _sha256(self.session_fingerprint)
        _sha256(self.authorization_audit_digest)

    def __repr__(self) -> str:
        return f"AuditAuthorizationProofV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class AuditEventCandidateV2(_RedactedValue):
    authorization: AuditAuthorizationProofV2
    request_sha256: str
    event_id: UUID
    occurred_at: datetime
    actor_type: str
    actor_id: UUID | None
    action: str
    target_type: str
    target_id: UUID
    outcome: str
    severity: str
    correlation_id: UUID
    request_id: str | None
    reason_code: str
    before_hash: str | None
    after_hash: str | None
    event_digest: str

    def __post_init__(self) -> None:
        if type(self.authorization) is not AuditAuthorizationProofV2:
            fail_audit_runtime_v2()
        _sha256(self.request_sha256)
        _uuid(self.event_id)
        _utc(self.occurred_at)
        _token(self.actor_type)
        if self.actor_id is not None:
            _uuid(self.actor_id)
        _token(self.action)
        _token(self.target_type)
        _uuid(self.target_id)
        _token(self.outcome)
        _token(self.severity)
        _uuid(self.correlation_id)
        _optional_token(self.request_id)
        _token(self.reason_code)
        if self.before_hash is not None:
            _sha256(self.before_hash)
        if self.after_hash is not None:
            _sha256(self.after_hash)
        _sha256(self.event_digest)
        identified_actor = self.actor_type in {
            AuditActorType.USER.value,
            AuditActorType.SERVICE.value,
            AuditActorType.SCHEDULE.value,
        }
        anonymous_actor = self.actor_type in {
            AuditActorType.SYSTEM.value,
            AuditActorType.ANONYMOUS.value,
        }
        if (
            not (identified_actor or anonymous_actor)
            or identified_actor != (self.actor_id is not None)
            or self.action != MatrixAction.EDIT_ARTICLE_DRAFT.value
            or self.target_type != ResourceScopeKind.ARTICLE_VERSION.value
            or self.outcome not in {value.value for value in AuditOutcome}
            or self.severity not in {value.value for value in AuditSeverity}
            or self.event_digest != self.calculate_event_digest()
        ):
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def calculate_event_digest(self) -> str:
        parts = (
            "RAOS_AUDIT_EVENT_V1",
            self.event_id.hex,
            _utc(self.occurred_at).isoformat(timespec="microseconds"),
            self.actor_type,
            "" if self.actor_id is None else self.actor_id.hex,
            self.action,
            self.target_type,
            self.target_id.hex,
            self.outcome,
            self.severity,
            self.correlation_id.hex,
            "" if self.request_id is None else self.request_id,
            self.reason_code,
            "" if self.before_hash is None else self.before_hash,
            "" if self.after_hash is None else self.after_hash,
        )
        return hashlib.sha256("\x1f".join(parts).encode("ascii")).hexdigest()

    @classmethod
    def from_event(
        cls,
        *,
        authorization: AuditAuthorizationProofV2,
        request_sha256: str,
        event: AuditEvent,
    ) -> AuditEventCandidateV2:
        if type(event) is not AuditEvent:
            fail_audit_runtime_v2()
        try:
            event.require_valid()
            return cls(
                authorization=authorization,
                request_sha256=request_sha256,
                event_id=event.event_id.value,
                occurred_at=event.occurred_at,
                actor_type=event.actor_type.value,
                actor_id=event.actor_id,
                action=event.action.value,
                target_type=event.target_type.value,
                target_id=event.target_id,
                outcome=event.outcome.value,
                severity=event.severity.value,
                correlation_id=event.correlation_id,
                request_id=None if event.request_id is None else event.request_id.value,
                reason_code=event.reason_code.value,
                before_hash=event.before_hash,
                after_hash=event.after_hash,
                event_digest=event.digest,
            )
        except AuditRuntimeFailureV2:
            raise
        except Exception:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "authorization_audit_digest": self.authorization.authorization_audit_digest,
            "authorization_command_id_fingerprint": self.authorization.command_id_fingerprint,
            "authorization_request_digest": self.authorization.request_digest,
            "authorization_session_fingerprint": self.authorization.session_fingerprint,
            "request_sha256": self.request_sha256,
            "event_id": str(self.event_id),
            "occurred_at": _utc_text(self.occurred_at),
            "actor_type": self.actor_type,
            "actor_id": None if self.actor_id is None else str(self.actor_id),
            "action": self.action,
            "target_type": self.target_type,
            "target_id": str(self.target_id),
            "outcome": self.outcome,
            "severity": self.severity,
            "correlation_id": str(self.correlation_id),
            "request_id": self.request_id,
            "reason_code": self.reason_code,
            "before_hash": self.before_hash,
            "after_hash": self.after_hash,
            "event_digest": self.event_digest,
        }

    def __repr__(self) -> str:
        return f"AuditEventCandidateV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class PersistedAuditEventV2(_RedactedValue):
    candidate: AuditEventCandidateV2
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    atomic_marker_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.candidate) is not AuditEventCandidateV2
            or type(self.sequence) is not int
            or not 1 <= self.sequence <= _MAX_SEQUENCE
        ):
            fail_audit_runtime_v2()
        _sha256(self.previous_entry_sha256)
        _sha256(self.entry_sha256)
        _sha256(self.atomic_marker_sha256)
        if self.entry_sha256 != self.calculate_entry_sha256():
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def calculate_entry_sha256(self) -> str:
        return audit_entry_sha256_v2(
            candidate=self.candidate,
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
            atomic_marker_sha256=self.atomic_marker_sha256,
        )

    def __repr__(self) -> str:
        return f"PersistedAuditEventV2({_REDACTED})"


@dataclass(frozen=True, slots=True, repr=False)
class AuditAppendReceiptV2(_RedactedValue):
    event_id: UUID
    request_sha256: str
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        _uuid(self.event_id)
        _sha256(self.request_sha256)
        if type(self.sequence) is not int or not 1 <= self.sequence <= _MAX_SEQUENCE:
            fail_audit_runtime_v2()
        _sha256(self.previous_entry_sha256)
        _sha256(self.entry_sha256)
        if type(self.replayed) is not bool:
            fail_audit_runtime_v2()

    def __repr__(self) -> str:
        return f"AuditAppendReceiptV2({_REDACTED})"


def audit_request_sha256_v2(
    *,
    authorization: AuditAuthorizationProofV2,
    outcome: str,
    severity: str,
    reason_code: str,
    before_hash: str | None,
    after_hash: str | None,
) -> str:
    if type(authorization) is not AuditAuthorizationProofV2:
        fail_audit_runtime_v2()
    _token(outcome)
    _token(severity)
    _token(reason_code)
    if before_hash is not None:
        _sha256(before_hash)
    if after_hash is not None:
        _sha256(after_hash)
    return canonical_sha256_v2(
        {
            "schema": "RAOS_ST0405_AUDIT_REQUEST_V2",
            "authorization": {
                "command_id_fingerprint": authorization.command_id_fingerprint,
                "request_digest": authorization.request_digest,
                "session_fingerprint": authorization.session_fingerprint,
                "authorization_audit_digest": authorization.authorization_audit_digest,
            },
            "outcome": outcome,
            "severity": severity,
            "reason_code": reason_code,
            "before_hash": before_hash,
            "after_hash": after_hash,
        }
    )


def audit_entry_sha256_v2(
    *,
    candidate: AuditEventCandidateV2,
    sequence: int,
    previous_entry_sha256: str,
    atomic_marker_sha256: str,
) -> str:
    if (
        type(candidate) is not AuditEventCandidateV2
        or type(sequence) is not int
        or not 1 <= sequence <= _MAX_SEQUENCE
    ):
        fail_audit_runtime_v2()
    _sha256(previous_entry_sha256)
    _sha256(atomic_marker_sha256)
    return canonical_sha256_v2(
        {
            "schema": AUDIT_RUNTIME_SCHEMA_VERSION_V2,
            "sequence": sequence,
            "previous_entry_sha256": previous_entry_sha256,
            "atomic_marker_sha256": atomic_marker_sha256,
            "event": candidate.canonical_material,
        }
    )


__all__ = [
    "AUDIT_QUERY_BLOCK_REASON_V2",
    "AUDIT_RUNTIME_CONTRACT_SHA256_V2",
    "AUDIT_RUNTIME_GENESIS_SHA256_V2",
    "AUDIT_RUNTIME_SCHEMA_VERSION_V2",
    "AuditAppendReceiptV2",
    "AuditAuthorizationProofV2",
    "AuditEventCandidateV2",
    "AuditRuntimeFailureCodeV2",
    "AuditRuntimeFailureV2",
    "PersistedAuditEventV2",
    "audit_entry_sha256_v2",
    "audit_request_sha256_v2",
    "canonical_sha256_v2",
    "fail_audit_runtime_v2",
]
