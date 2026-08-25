"""Deterministic, evidence-bounded Source Packet lifecycle for ST-0604 V2.

The module contains no provider, AI, publication, ranking, revenue, network, or
credential capability.  A generation input is a distinct value that can only
validate when its exact current packet version is approved and locked.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex, cast, final
from uuid import UUID

from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FactConflictScanCommandV2,
    PersistedFactConflictDetectionV2,
    canonical_sha256_v2 as conflict_sha256_v2,
    persisted_from_mapping_v2 as conflict_from_mapping_v2,
    persisted_mapping_v2 as conflict_mapping_v2,
)
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    PersistedFactExtractionV2,
    canonical_sha256_v2 as fact_sha256_v2,
    fact_mapping_v2,
    persisted_from_mapping_v2 as fact_from_mapping_v2,
    persisted_mapping_v2 as fact_mapping_persisted_v2,
)
from raos.domain.shared.identity import deterministic_uuid7


SOURCE_PACKET_SCHEMA_VERSION_V2 = "ST0604_SOURCE_PACKET_LIFECYCLE_V2"
SOURCE_PACKET_GENESIS_SHA256_V2 = "0" * 64
SOURCE_PACKET_AUTHORIZATION_OPERATION_V2 = "PUBADM-004"
SOURCE_PACKET_AUTHORIZATION_ACTION_V2 = "review_article"
SOURCE_PACKET_AUTHORIZATION_RESOURCE_KIND_V2 = "REVIEW_ASSIGNMENT"
SOURCE_PACKET_AUTHORIZATION_RESOURCE_STATE_V2 = "IN_PROGRESS"
SOURCE_PACKET_EXTERNAL_ACTION_COUNT_V2 = 0
SOURCE_PACKET_PROVIDER_ACTION_COUNT_V2 = 0
SOURCE_PACKET_AI_ACTION_COUNT_V2 = 0
SOURCE_PACKET_PUBLICATION_ACTION_COUNT_V2 = 0

_ID_NAMESPACE = UUID("3e8f17ab-a5be-45c7-9020-34f7950389e4")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_TOKEN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._:/-]{0,126}[A-Za-z0-9])?\Z", re.ASCII)
_REDACTED = "<redacted-source-packet-value>"


class SourcePacketFailureCodeV2(str, Enum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    DEPENDENCY_MISMATCH = "DEPENDENCY_MISMATCH"
    UNRESOLVED_CONFLICT = "UNRESOLVED_CONFLICT"
    AUTHORIZATION_REQUIRED = "AUTHORIZATION_REQUIRED"
    STATE_CONFLICT = "STATE_CONFLICT"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    IMMUTABLE_VERSION = "IMMUTABLE_VERSION"
    NOT_GENERATION_READY = "NOT_GENERATION_READY"
    COMMAND_UNKNOWN = "COMMAND_UNKNOWN"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    STORAGE_FAILED = "STORAGE_FAILED"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"
    TAMPER_DETECTED = "TAMPER_DETECTED"


class SourcePacketStatusV2(str, Enum):
    BUILDING = "BUILDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class SourcePacketPurposeV2(str, Enum):
    ARTICLE_DRAFT = "ARTICLE_DRAFT"
    ARTICLE_UPDATE = "ARTICLE_UPDATE"
    COMPARISON = "COMPARISON"
    QUALITY_REVIEW = "QUALITY_REVIEW"


class SourcePacketReviewDecisionV2(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"


class SourcePacketCommandKindV2(str, Enum):
    CREATE_PACKET = "CREATE_PACKET"
    CREATE_VERSION = "CREATE_VERSION"
    SUBMIT_REVIEW = "SUBMIT_REVIEW"
    RECORD_REVIEW = "RECORD_REVIEW"
    LOCK_VERSION = "LOCK_VERSION"
    READ_GENERATION_INPUT = "READ_GENERATION_INPUT"


class SourcePacketReplayStatusV2(str, Enum):
    COMMITTED = "COMMITTED"
    REPLAYED = "REPLAYED"


@final
class SourcePacketFailureV2(RuntimeError):
    __slots__ = ("_code", "_sealed")

    _code: SourcePacketFailureCodeV2

    def __init__(self, code: SourcePacketFailureCodeV2) -> None:
        if type(code) is not SourcePacketFailureCodeV2:
            raise TypeError("invalid Source Packet failure code")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> SourcePacketFailureCodeV2:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("SourcePacketFailureV2 is immutable")

    def __repr__(self) -> str:
        return f"SourcePacketFailureV2({self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Source Packet failures are not serializable")


def fail_source_packet_v2(
    code: SourcePacketFailureCodeV2 = SourcePacketFailureCodeV2.INVALID_ARGUMENT,
) -> NoReturn:
    raise SourcePacketFailureV2(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("Source Packet values are not serializable")


@final
class SourcePacketCommandIdV2(_RedactedValue):
    __slots__ = ("_value", "_sealed")

    _value: str

    def __init__(self, value: str) -> None:
        if type(value) is not str or _TOKEN.fullmatch(value) is None:
            fail_source_packet_v2()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        return type(other) is SourcePacketCommandIdV2 and self.value == other.value

    def __hash__(self) -> int:
        return hash((type(self), self.value))

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("SourcePacketCommandIdV2 is immutable")


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.int == 0:
        fail_source_packet_v2()
    return value


def _sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return value


def _actor(value: object) -> str:
    digest = _sha256(value)
    if digest == SOURCE_PACKET_GENESIS_SHA256_V2:
        fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
    return digest


def _positive(value: object, *, maximum: int = 2**31 - 1) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        fail_source_packet_v2()
    return value


def _nonnegative(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 2**31 - 1:
        fail_source_packet_v2()
    return value


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_source_packet_v2()
    return value


def utc_text_v2(value: datetime) -> str:
    return _utc(value).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    if utc_text_v2(parsed) != value:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return parsed


def canonical_json_bytes_v2(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except TypeError, ValueError, UnicodeEncodeError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)


def canonical_sha256_v2(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes_v2(value)).hexdigest()


def _stable_id(kind: str, material: object) -> UUID:
    return deterministic_uuid7(
        _ID_NAMESPACE,
        canonical_json_bytes_v2(
            {
                "kind": kind,
                "material": material,
                "schema": SOURCE_PACKET_SCHEMA_VERSION_V2,
            }
        ),
    )


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    data = cast(dict[str, object], value)
    if frozenset(data) != keys:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return data


def _uuid_text(value: object) -> UUID:
    if type(value) is not str:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    try:
        parsed = UUID(value)
    except ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    if parsed.int == 0 or str(parsed) != value:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return parsed


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketContentV2(_RedactedValue):
    purpose: SourcePacketPurposeV2
    fact_batches: tuple[PersistedFactExtractionV2, ...]
    conflict_scan: PersistedFactConflictDetectionV2

    def __post_init__(self) -> None:
        if (
            type(self.purpose) is not SourcePacketPurposeV2
            or type(self.fact_batches) is not tuple
            or not self.fact_batches
            or len(self.fact_batches) > 16
            or any(
                type(item) is not PersistedFactExtractionV2
                for item in self.fact_batches
            )
            or type(self.conflict_scan) is not PersistedFactConflictDetectionV2
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.DEPENDENCY_MISMATCH)
        copied: list[PersistedFactExtractionV2] = []
        try:
            for item in self.fact_batches:
                decoded = fact_from_mapping_v2(fact_mapping_persisted_v2(item))
                if decoded != item or not decoded.batch.facts:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.DEPENDENCY_MISMATCH)
                copied.append(decoded)
            conflict = conflict_from_mapping_v2(conflict_mapping_v2(self.conflict_scan))
            expected_command = FactConflictScanCommandV2.issue(tuple(copied))
        except SourcePacketFailureV2:
            raise
        except Exception:
            fail_source_packet_v2(SourcePacketFailureCodeV2.DEPENDENCY_MISMATCH)
        if (
            tuple(item.batch.batch_id.hex for item in copied)
            != tuple(sorted(item.batch.batch_id.hex for item in copied))
            or len({item.batch.batch_id for item in copied}) != len(copied)
            or conflict != self.conflict_scan
            or conflict.command != expected_command
            or conflict.batch.conflicts
            or conflict.batch.queue
            or conflict.event.conflict_ids
            or conflict.event.queue_ids
            or any(
                value != 0
                for batch in copied
                for value in (
                    batch.batch.external_action_count,
                    batch.batch.provider_action_count,
                    batch.batch.publication_action_count,
                    batch.batch.ai_action_count,
                    batch.event.external_action_count,
                )
            )
            or any(
                value != 0
                for value in (
                    conflict.batch.external_action_count,
                    conflict.batch.provider_action_count,
                    conflict.batch.publication_action_count,
                    conflict.batch.ai_action_count,
                    conflict.event.external_action_count,
                )
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.UNRESOLVED_CONFLICT)

    @property
    def fact_count(self) -> int:
        return sum(len(item.batch.facts) for item in self.fact_batches)

    @property
    def fact_membership(self) -> tuple[tuple[UUID, str], ...]:
        return tuple(
            sorted(
                (
                    (fact.fact_id, fact_sha256_v2(fact_mapping_v2(fact)))
                    for batch in self.fact_batches
                    for fact in batch.batch.facts
                ),
                key=lambda item: item[0].hex,
            )
        )

    @property
    def fact_membership_sha256(self) -> str:
        return canonical_sha256_v2(
            [
                {"fact_id": str(fact_id), "fact_sha256": digest}
                for fact_id, digest in self.fact_membership
            ]
        )

    @property
    def conflict_scan_sha256(self) -> str:
        return conflict_sha256_v2(conflict_mapping_v2(self.conflict_scan))

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "conflict_scan": conflict_mapping_v2(self.conflict_scan),
            "fact_batches": [
                fact_mapping_persisted_v2(item) for item in self.fact_batches
            ],
            "purpose": self.purpose.value,
        }

    @property
    def content_sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)


@dataclass(frozen=True, slots=True, repr=False)
class RecordedSourcePacketAuthorizationV2(_RedactedValue):
    authorization_command_id: str
    operation_id: str
    request_digest: str
    session_fingerprint: str
    audit_sequence: int
    audit_digest: str
    policy_revision: str
    policy_fingerprint: str
    entitlement_revision: str
    matched_rule_id: str
    site_id: UUID
    review_assignment_id: UUID
    observed_at: datetime
    checked_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.authorization_command_id) is not str
            or _TOKEN.fullmatch(self.authorization_command_id) is None
            or self.operation_id != SOURCE_PACKET_AUTHORIZATION_OPERATION_V2
            or type(self.policy_revision) is not str
            or _TOKEN.fullmatch(self.policy_revision) is None
            or type(self.entitlement_revision) is not str
            or _TOKEN.fullmatch(self.entitlement_revision) is None
            or type(self.matched_rule_id) is not str
            or _TOKEN.fullmatch(self.matched_rule_id) is None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        for value in (
            self.request_digest,
            self.session_fingerprint,
            self.audit_digest,
            self.policy_fingerprint,
        ):
            _sha256(value)
        _positive(self.audit_sequence)
        _uuid(self.site_id)
        _uuid(self.review_assignment_id)
        if _utc(self.checked_at) < _utc(self.observed_at):
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)

    @property
    def canonical_material(self) -> dict[str, object]:
        return {
            "audit_digest": self.audit_digest,
            "audit_sequence": self.audit_sequence,
            "authorization_command_id": self.authorization_command_id,
            "checked_at": utc_text_v2(self.checked_at),
            "entitlement_revision": self.entitlement_revision,
            "matched_rule_id": self.matched_rule_id,
            "observed_at": utc_text_v2(self.observed_at),
            "operation_id": self.operation_id,
            "policy_fingerprint": self.policy_fingerprint,
            "policy_revision": self.policy_revision,
            "request_digest": self.request_digest,
            "review_assignment_id": str(self.review_assignment_id),
            "session_fingerprint": self.session_fingerprint,
            "site_id": str(self.site_id),
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketReviewRecordV2(_RedactedValue):
    decision: SourcePacketReviewDecisionV2
    packet_id: UUID
    version_id: UUID
    version_number: int
    content_sha256: str
    fact_membership_sha256: str
    conflict_scan_sha256: str
    authorization: RecordedSourcePacketAuthorizationV2
    reviewed_at: datetime
    binding_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.decision) is not SourcePacketReviewDecisionV2
            or type(self.authorization) is not RecordedSourcePacketAuthorizationV2
        ):
            fail_source_packet_v2()
        _uuid(self.packet_id)
        _uuid(self.version_id)
        _positive(self.version_number, maximum=64)
        for value in (
            self.content_sha256,
            self.fact_membership_sha256,
            self.conflict_scan_sha256,
        ):
            _sha256(value)
        reviewed = _utc(self.reviewed_at)
        if reviewed != self.authorization.checked_at:
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        expected = canonical_sha256_v2(
            {
                "authorization_sha256": self.authorization.sha256,
                "conflict_scan_sha256": self.conflict_scan_sha256,
                "content_sha256": self.content_sha256,
                "decision": self.decision.value,
                "fact_membership_sha256": self.fact_membership_sha256,
                "packet_id": str(self.packet_id),
                "reviewed_at": utc_text_v2(reviewed),
                "version_id": str(self.version_id),
                "version_number": self.version_number,
            }
        )
        if _sha256(self.binding_sha256) != expected:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def issue(
        cls,
        *,
        decision: SourcePacketReviewDecisionV2,
        version: SourcePacketVersionV2,
        authorization: RecordedSourcePacketAuthorizationV2,
        reviewed_at: datetime,
    ) -> SourcePacketReviewRecordV2:
        if (
            type(version) is not SourcePacketVersionV2
            or type(authorization) is not RecordedSourcePacketAuthorizationV2
        ):
            fail_source_packet_v2()
        material = {
            "authorization_sha256": authorization.sha256,
            "conflict_scan_sha256": version.content.conflict_scan_sha256,
            "content_sha256": version.content.content_sha256,
            "decision": decision.value,
            "fact_membership_sha256": version.content.fact_membership_sha256,
            "packet_id": str(version.packet_id),
            "reviewed_at": utc_text_v2(reviewed_at),
            "version_id": str(version.version_id),
            "version_number": version.version_number,
        }
        return cls(
            decision=decision,
            packet_id=version.packet_id,
            version_id=version.version_id,
            version_number=version.version_number,
            content_sha256=version.content.content_sha256,
            fact_membership_sha256=version.content.fact_membership_sha256,
            conflict_scan_sha256=version.content.conflict_scan_sha256,
            authorization=authorization,
            reviewed_at=reviewed_at,
            binding_sha256=canonical_sha256_v2(material),
        )


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketLockV2(_RedactedValue):
    packet_id: UUID
    version_id: UUID
    version_number: int
    content_sha256: str
    approval_binding_sha256: str
    locked_at: datetime
    lock_sha256: str

    def __post_init__(self) -> None:
        _uuid(self.packet_id)
        _uuid(self.version_id)
        _positive(self.version_number, maximum=64)
        _sha256(self.content_sha256)
        _sha256(self.approval_binding_sha256)
        locked = _utc(self.locked_at)
        expected = canonical_sha256_v2(
            {
                "approval_binding_sha256": self.approval_binding_sha256,
                "content_sha256": self.content_sha256,
                "locked_at": utc_text_v2(locked),
                "packet_id": str(self.packet_id),
                "version_id": str(self.version_id),
                "version_number": self.version_number,
            }
        )
        if _sha256(self.lock_sha256) != expected:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def issue(
        cls, version: SourcePacketVersionV2, locked_at: datetime
    ) -> SourcePacketLockV2:
        if (
            type(version) is not SourcePacketVersionV2
            or version.status is not SourcePacketStatusV2.APPROVED
            or version.review is None
            or version.review.decision is not SourcePacketReviewDecisionV2.APPROVE
            or version.lock is not None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.IMMUTABLE_VERSION)
        material = {
            "approval_binding_sha256": version.review.binding_sha256,
            "content_sha256": version.content.content_sha256,
            "locked_at": utc_text_v2(locked_at),
            "packet_id": str(version.packet_id),
            "version_id": str(version.version_id),
            "version_number": version.version_number,
        }
        return cls(
            packet_id=version.packet_id,
            version_id=version.version_id,
            version_number=version.version_number,
            content_sha256=version.content.content_sha256,
            approval_binding_sha256=version.review.binding_sha256,
            locked_at=locked_at,
            lock_sha256=canonical_sha256_v2(material),
        )


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketVersionV2(_RedactedValue):
    packet_id: UUID
    version_id: UUID
    version_number: int
    content: SourcePacketContentV2
    content_sha256: str
    status: SourcePacketStatusV2
    created_at: datetime
    editor_actor_fingerprint: str
    review: SourcePacketReviewRecordV2 | None
    lock: SourcePacketLockV2 | None

    def __post_init__(self) -> None:
        _uuid(self.packet_id)
        _uuid(self.version_id)
        _positive(self.version_number, maximum=64)
        if (
            type(self.content) is not SourcePacketContentV2
            or type(self.status) is not SourcePacketStatusV2
        ):
            fail_source_packet_v2()
        if _sha256(self.content_sha256) != self.content.content_sha256:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        _utc(self.created_at)
        _actor(self.editor_actor_fingerprint)
        expected_id = _stable_id(
            "source_packet_version",
            {
                "content_sha256": self.content_sha256,
                "packet_id": str(self.packet_id),
                "version_number": self.version_number,
            },
        )
        if self.version_id != expected_id:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if self.review is not None:
            if (
                type(self.review) is not SourcePacketReviewRecordV2
                or self.review.packet_id != self.packet_id
                or self.review.version_id != self.version_id
                or self.review.version_number != self.version_number
                or self.review.content_sha256 != self.content_sha256
                or self.review.fact_membership_sha256
                != self.content.fact_membership_sha256
                or self.review.conflict_scan_sha256 != self.content.conflict_scan_sha256
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if self.lock is not None:
            if (
                type(self.lock) is not SourcePacketLockV2
                or self.review is None
                or self.review.decision is not SourcePacketReviewDecisionV2.APPROVE
                or self.lock.packet_id != self.packet_id
                or self.lock.version_id != self.version_id
                or self.lock.version_number != self.version_number
                or self.lock.content_sha256 != self.content_sha256
                or self.lock.approval_binding_sha256 != self.review.binding_sha256
                or self.lock.locked_at < self.review.reviewed_at
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if (
            (
                self.status is SourcePacketStatusV2.BUILDING
                and (self.review is not None or self.lock is not None)
            )
            or (
                self.status is SourcePacketStatusV2.IN_REVIEW
                and (self.review is not None or self.lock is not None)
            )
            or (
                self.status is SourcePacketStatusV2.APPROVED
                and (
                    self.review is None
                    or self.review.decision is not SourcePacketReviewDecisionV2.APPROVE
                )
            )
            or (
                self.status is SourcePacketStatusV2.REJECTED
                and (
                    self.review is None
                    or self.review.decision is not SourcePacketReviewDecisionV2.REJECT
                    or self.lock is not None
                )
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def create(
        cls,
        *,
        packet_id: UUID,
        version_number: int,
        content: SourcePacketContentV2,
        created_at: datetime,
        editor_actor_fingerprint: str,
    ) -> SourcePacketVersionV2:
        content_sha256 = content.content_sha256
        version_id = _stable_id(
            "source_packet_version",
            {
                "content_sha256": content_sha256,
                "packet_id": str(packet_id),
                "version_number": version_number,
            },
        )
        return cls(
            packet_id=packet_id,
            version_id=version_id,
            version_number=version_number,
            content=content,
            content_sha256=content_sha256,
            status=SourcePacketStatusV2.BUILDING,
            created_at=created_at,
            editor_actor_fingerprint=editor_actor_fingerprint,
            review=None,
            lock=None,
        )


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketStateV2(_RedactedValue):
    packet_id: UUID
    site_id: UUID
    article_plan_id: UUID
    review_assignment_id: UUID
    creator_actor_fingerprint: str
    created_at: datetime
    aggregate_revision: int
    versions: tuple[SourcePacketVersionV2, ...]

    def __post_init__(self) -> None:
        for value in (
            self.packet_id,
            self.site_id,
            self.article_plan_id,
            self.review_assignment_id,
        ):
            _uuid(value)
        _actor(self.creator_actor_fingerprint)
        _utc(self.created_at)
        _positive(self.aggregate_revision)
        if (
            type(self.versions) is not tuple
            or len(self.versions) > 64
            or any(type(item) is not SourcePacketVersionV2 for item in self.versions)
            or any(item.packet_id != self.packet_id for item in self.versions)
            or tuple(item.version_number for item in self.versions)
            != tuple(range(1, len(self.versions) + 1))
            or any(
                item.status is not SourcePacketStatusV2.SUPERSEDED
                for item in self.versions[:-1]
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    @property
    def current_version(self) -> SourcePacketVersionV2 | None:
        return None if not self.versions else self.versions[-1]

    @property
    def packet_status(self) -> SourcePacketStatusV2:
        current = self.current_version
        return SourcePacketStatusV2.BUILDING if current is None else current.status

    @property
    def canonical_material(self) -> dict[str, object]:
        return state_mapping_v2(self)

    @property
    def state_sha256(self) -> str:
        return canonical_sha256_v2(self.canonical_material)


@dataclass(frozen=True, slots=True, repr=False)
class ApprovedLockedGenerationInputV2(_RedactedValue):
    packet_id: UUID
    site_id: UUID
    article_plan_id: UUID
    version_id: UUID
    version_number: int
    content: SourcePacketContentV2
    content_sha256: str
    fact_membership_sha256: str
    conflict_scan_sha256: str
    approval: SourcePacketReviewRecordV2
    lock: SourcePacketLockV2
    approval_binding_sha256: str
    lock_sha256: str
    aggregate_revision: int

    def __post_init__(self) -> None:
        for value in (
            self.packet_id,
            self.site_id,
            self.article_plan_id,
            self.version_id,
        ):
            _uuid(value)
        _positive(self.version_number, maximum=64)
        _positive(self.aggregate_revision)
        if (
            type(self.content) is not SourcePacketContentV2
            or type(self.approval) is not SourcePacketReviewRecordV2
            or type(self.lock) is not SourcePacketLockV2
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.NOT_GENERATION_READY)
        if (
            _sha256(self.content_sha256) != self.content.content_sha256
            or _sha256(self.fact_membership_sha256)
            != self.content.fact_membership_sha256
            or _sha256(self.conflict_scan_sha256) != self.content.conflict_scan_sha256
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if (
            _sha256(self.approval_binding_sha256) != self.approval.binding_sha256
            or _sha256(self.lock_sha256) != self.lock.lock_sha256
            or self.approval.decision is not SourcePacketReviewDecisionV2.APPROVE
            or self.approval.packet_id != self.packet_id
            or self.approval.version_id != self.version_id
            or self.approval.version_number != self.version_number
            or self.approval.content_sha256 != self.content_sha256
            or self.approval.fact_membership_sha256 != self.fact_membership_sha256
            or self.approval.conflict_scan_sha256 != self.conflict_scan_sha256
            or self.lock.packet_id != self.packet_id
            or self.lock.version_id != self.version_id
            or self.lock.version_number != self.version_number
            or self.lock.content_sha256 != self.content_sha256
            or self.lock.approval_binding_sha256 != self.approval_binding_sha256
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def from_state(cls, state: SourcePacketStateV2) -> ApprovedLockedGenerationInputV2:
        if type(state) is not SourcePacketStateV2:
            fail_source_packet_v2(SourcePacketFailureCodeV2.NOT_GENERATION_READY)
        current = state.current_version
        if (
            current is None
            or current.status is not SourcePacketStatusV2.APPROVED
            or current.review is None
            or current.review.decision is not SourcePacketReviewDecisionV2.APPROVE
            or current.lock is None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.NOT_GENERATION_READY)
        current.content.__post_init__()
        return cls(
            packet_id=state.packet_id,
            site_id=state.site_id,
            article_plan_id=state.article_plan_id,
            version_id=current.version_id,
            version_number=current.version_number,
            content=current.content,
            content_sha256=current.content_sha256,
            fact_membership_sha256=current.content.fact_membership_sha256,
            conflict_scan_sha256=current.content.conflict_scan_sha256,
            approval=current.review,
            lock=current.lock,
            approval_binding_sha256=current.review.binding_sha256,
            lock_sha256=current.lock.lock_sha256,
            aggregate_revision=state.aggregate_revision,
        )


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketCommandV2(_RedactedValue):
    command_id: SourcePacketCommandIdV2
    kind: SourcePacketCommandKindV2
    packet_id: UUID
    expected_revision: int
    occurred_at: datetime
    actor_fingerprint: str
    site_id: UUID | None = None
    article_plan_id: UUID | None = None
    review_assignment_id: UUID | None = None
    content: SourcePacketContentV2 | None = None
    review_decision: SourcePacketReviewDecisionV2 | None = None
    authorization: RecordedSourcePacketAuthorizationV2 | None = None

    def __post_init__(self) -> None:
        if (
            type(self.command_id) is not SourcePacketCommandIdV2
            or type(self.kind) is not SourcePacketCommandKindV2
        ):
            fail_source_packet_v2()
        _uuid(self.packet_id)
        _nonnegative(self.expected_revision)
        _utc(self.occurred_at)
        _actor(self.actor_fingerprint)
        create_shape = self.kind is SourcePacketCommandKindV2.CREATE_PACKET
        version_shape = self.kind is SourcePacketCommandKindV2.CREATE_VERSION
        review_shape = self.kind is SourcePacketCommandKindV2.RECORD_REVIEW
        if create_shape:
            if (
                self.expected_revision != 0
                or any(
                    type(item) is not UUID or item.int == 0
                    for item in (
                        self.site_id,
                        self.article_plan_id,
                        self.review_assignment_id,
                    )
                )
                or self.content is not None
                or self.review_decision is not None
                or self.authorization is not None
            ):
                fail_source_packet_v2()
        elif version_shape:
            if type(self.content) is not SourcePacketContentV2 or any(
                item is not None
                for item in (
                    self.site_id,
                    self.article_plan_id,
                    self.review_assignment_id,
                    self.review_decision,
                    self.authorization,
                )
            ):
                fail_source_packet_v2()
        elif review_shape:
            if (
                type(self.review_decision) is not SourcePacketReviewDecisionV2
                or type(self.authorization) is not RecordedSourcePacketAuthorizationV2
                or any(
                    item is not None
                    for item in (
                        self.site_id,
                        self.article_plan_id,
                        self.review_assignment_id,
                        self.content,
                    )
                )
            ):
                fail_source_packet_v2()
        elif any(
            item is not None
            for item in (
                self.site_id,
                self.article_plan_id,
                self.review_assignment_id,
                self.content,
                self.review_decision,
                self.authorization,
            )
        ):
            fail_source_packet_v2()

    @property
    def request_sha256(self) -> str:
        return canonical_sha256_v2(command_mapping_v2(self))


def apply_source_packet_command_v2(
    previous: SourcePacketStateV2 | None,
    command: SourcePacketCommandV2,
) -> tuple[SourcePacketStateV2, ApprovedLockedGenerationInputV2 | None]:
    if type(command) is not SourcePacketCommandV2:
        fail_source_packet_v2()
    if command.kind is SourcePacketCommandKindV2.CREATE_PACKET:
        if previous is not None:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
        assert command.site_id is not None
        assert command.article_plan_id is not None
        assert command.review_assignment_id is not None
        return (
            SourcePacketStateV2(
                packet_id=command.packet_id,
                site_id=command.site_id,
                article_plan_id=command.article_plan_id,
                review_assignment_id=command.review_assignment_id,
                creator_actor_fingerprint=command.actor_fingerprint,
                created_at=command.occurred_at,
                aggregate_revision=1,
                versions=(),
            ),
            None,
        )
    if previous is None or previous.packet_id != command.packet_id:
        fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
    if previous.aggregate_revision != command.expected_revision:
        fail_source_packet_v2(SourcePacketFailureCodeV2.VERSION_CONFLICT)
    if command.occurred_at < previous.created_at:
        fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
    versions = previous.versions
    current = previous.current_version
    generation: ApprovedLockedGenerationInputV2 | None = None
    if current is not None:
        latest_version_event = (
            current.lock.locked_at
            if current.lock is not None
            else current.review.reviewed_at
            if current.review is not None
            else current.created_at
        )
        if command.occurred_at < latest_version_event:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
    if command.kind is SourcePacketCommandKindV2.CREATE_VERSION:
        assert command.content is not None
        if len(versions) >= 64:
            fail_source_packet_v2(SourcePacketFailureCodeV2.VERSION_CONFLICT)
        superseded = (
            ()
            if current is None
            else (replace(current, status=SourcePacketStatusV2.SUPERSEDED),)
        )
        prefix = versions if current is None else versions[:-1] + superseded
        created = SourcePacketVersionV2.create(
            packet_id=previous.packet_id,
            version_number=len(versions) + 1,
            content=command.content,
            created_at=command.occurred_at,
            editor_actor_fingerprint=command.actor_fingerprint,
        )
        versions = prefix + (created,)
    elif current is None:
        fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
    elif command.kind is SourcePacketCommandKindV2.SUBMIT_REVIEW:
        if (
            current.status is not SourcePacketStatusV2.BUILDING
            or current.review is not None
            or current.lock is not None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
        current.content.__post_init__()
        versions = versions[:-1] + (
            replace(current, status=SourcePacketStatusV2.IN_REVIEW),
        )
    elif command.kind is SourcePacketCommandKindV2.RECORD_REVIEW:
        if (
            current.status is not SourcePacketStatusV2.IN_REVIEW
            or current.review is not None
            or current.lock is not None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.STATE_CONFLICT)
        assert command.review_decision is not None
        assert command.authorization is not None
        if (
            command.authorization.site_id != previous.site_id
            or command.authorization.review_assignment_id
            != previous.review_assignment_id
            or command.authorization.session_fingerprint != command.actor_fingerprint
            or command.authorization.checked_at != command.occurred_at
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        review = SourcePacketReviewRecordV2.issue(
            decision=command.review_decision,
            version=current,
            authorization=command.authorization,
            reviewed_at=command.occurred_at,
        )
        status = (
            SourcePacketStatusV2.APPROVED
            if command.review_decision is SourcePacketReviewDecisionV2.APPROVE
            else SourcePacketStatusV2.REJECTED
        )
        versions = versions[:-1] + (replace(current, status=status, review=review),)
    elif command.kind is SourcePacketCommandKindV2.LOCK_VERSION:
        if (
            current.status is not SourcePacketStatusV2.APPROVED
            or current.lock is not None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.IMMUTABLE_VERSION)
        lock = SourcePacketLockV2.issue(current, command.occurred_at)
        versions = versions[:-1] + (replace(current, lock=lock),)
    elif command.kind is SourcePacketCommandKindV2.READ_GENERATION_INPUT:
        generation = ApprovedLockedGenerationInputV2.from_state(previous)
    else:
        fail_source_packet_v2()
    next_state = replace(
        previous,
        aggregate_revision=previous.aggregate_revision + 1,
        versions=versions,
    )
    if generation is not None:
        generation = replace(
            generation, aggregate_revision=next_state.aggregate_revision
        )
    return next_state, generation


@dataclass(frozen=True, slots=True, repr=False)
class SourcePacketCommandResultV2(_RedactedValue):
    command: SourcePacketCommandV2
    state: SourcePacketStateV2
    generation_input: ApprovedLockedGenerationInputV2 | None
    sequence: int
    previous_chain_hash: str
    chain_hash: str
    committed_at: datetime
    replay_status: SourcePacketReplayStatusV2
    external_action_count: int = 0
    provider_action_count: int = 0
    publication_action_count: int = 0
    ai_action_count: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.command) is not SourcePacketCommandV2
            or type(self.state) is not SourcePacketStateV2
            or (
                self.generation_input is not None
                and type(self.generation_input) is not ApprovedLockedGenerationInputV2
            )
            or type(self.replay_status) is not SourcePacketReplayStatusV2
            or any(
                value != 0
                for value in (
                    self.external_action_count,
                    self.provider_action_count,
                    self.publication_action_count,
                    self.ai_action_count,
                )
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        sequence = _positive(self.sequence)
        previous = _sha256(self.previous_chain_hash)
        committed = _utc(self.committed_at)
        expected = source_packet_chain_hash_v2(
            previous_chain_hash=previous,
            sequence=sequence,
            command_sha256=self.command.request_sha256,
            state_sha256=self.state.state_sha256,
            generation_input_sha256=(
                None
                if self.generation_input is None
                else canonical_sha256_v2(
                    generation_input_mapping_v2(self.generation_input)
                )
            ),
            committed_at=committed,
        )
        if (
            _sha256(self.chain_hash) != expected
            or self.state.aggregate_revision != self.command.expected_revision + 1
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if (self.command.kind is SourcePacketCommandKindV2.READ_GENERATION_INPUT) != (
            self.generation_input is not None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)


def source_packet_chain_hash_v2(
    *,
    previous_chain_hash: str,
    sequence: int,
    command_sha256: str,
    state_sha256: str,
    generation_input_sha256: str | None,
    committed_at: datetime,
) -> str:
    return canonical_sha256_v2(
        {
            "command_sha256": _sha256(command_sha256),
            "committed_at": utc_text_v2(committed_at),
            "generation_input_sha256": None
            if generation_input_sha256 is None
            else _sha256(generation_input_sha256),
            "previous_chain_hash": _sha256(previous_chain_hash),
            "sequence": _positive(sequence),
            "state_sha256": _sha256(state_sha256),
        }
    )


def content_mapping_v2(value: SourcePacketContentV2) -> dict[str, object]:
    if type(value) is not SourcePacketContentV2:
        fail_source_packet_v2()
    return value.canonical_material


def content_from_mapping_v2(value: object) -> SourcePacketContentV2:
    data = _exact_mapping(
        value, frozenset({"conflict_scan", "fact_batches", "purpose"})
    )
    batches = data["fact_batches"]
    if type(batches) is not list:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    batch_items = cast(list[object], batches)
    try:
        purpose = SourcePacketPurposeV2(cast(str, data["purpose"]))
    except TypeError, ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return SourcePacketContentV2(
        purpose=purpose,
        fact_batches=tuple(fact_from_mapping_v2(item) for item in batch_items),
        conflict_scan=conflict_from_mapping_v2(data["conflict_scan"]),
    )


def authorization_mapping_v2(
    value: RecordedSourcePacketAuthorizationV2,
) -> dict[str, object]:
    if type(value) is not RecordedSourcePacketAuthorizationV2:
        fail_source_packet_v2()
    return value.canonical_material


def authorization_from_mapping_v2(value: object) -> RecordedSourcePacketAuthorizationV2:
    keys = frozenset(
        {
            "audit_digest",
            "audit_sequence",
            "authorization_command_id",
            "checked_at",
            "entitlement_revision",
            "matched_rule_id",
            "observed_at",
            "operation_id",
            "policy_fingerprint",
            "policy_revision",
            "request_digest",
            "review_assignment_id",
            "session_fingerprint",
            "site_id",
        }
    )
    data = _exact_mapping(value, keys)
    return RecordedSourcePacketAuthorizationV2(
        authorization_command_id=cast(str, data["authorization_command_id"]),
        operation_id=cast(str, data["operation_id"]),
        request_digest=cast(str, data["request_digest"]),
        session_fingerprint=cast(str, data["session_fingerprint"]),
        audit_sequence=cast(int, data["audit_sequence"]),
        audit_digest=cast(str, data["audit_digest"]),
        policy_revision=cast(str, data["policy_revision"]),
        policy_fingerprint=cast(str, data["policy_fingerprint"]),
        entitlement_revision=cast(str, data["entitlement_revision"]),
        matched_rule_id=cast(str, data["matched_rule_id"]),
        site_id=_uuid_text(data["site_id"]),
        review_assignment_id=_uuid_text(data["review_assignment_id"]),
        observed_at=_parse_utc(data["observed_at"]),
        checked_at=_parse_utc(data["checked_at"]),
    )


def review_mapping_v2(value: SourcePacketReviewRecordV2) -> dict[str, object]:
    return {
        "authorization": authorization_mapping_v2(value.authorization),
        "binding_sha256": value.binding_sha256,
        "conflict_scan_sha256": value.conflict_scan_sha256,
        "content_sha256": value.content_sha256,
        "decision": value.decision.value,
        "fact_membership_sha256": value.fact_membership_sha256,
        "packet_id": str(value.packet_id),
        "reviewed_at": utc_text_v2(value.reviewed_at),
        "version_id": str(value.version_id),
        "version_number": value.version_number,
    }


def review_from_mapping_v2(value: object) -> SourcePacketReviewRecordV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "authorization",
                "binding_sha256",
                "conflict_scan_sha256",
                "content_sha256",
                "decision",
                "fact_membership_sha256",
                "packet_id",
                "reviewed_at",
                "version_id",
                "version_number",
            }
        ),
    )
    try:
        decision = SourcePacketReviewDecisionV2(cast(str, data["decision"]))
    except TypeError, ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return SourcePacketReviewRecordV2(
        decision=decision,
        packet_id=_uuid_text(data["packet_id"]),
        version_id=_uuid_text(data["version_id"]),
        version_number=cast(int, data["version_number"]),
        content_sha256=cast(str, data["content_sha256"]),
        fact_membership_sha256=cast(str, data["fact_membership_sha256"]),
        conflict_scan_sha256=cast(str, data["conflict_scan_sha256"]),
        authorization=authorization_from_mapping_v2(data["authorization"]),
        reviewed_at=_parse_utc(data["reviewed_at"]),
        binding_sha256=cast(str, data["binding_sha256"]),
    )


def lock_mapping_v2(value: SourcePacketLockV2) -> dict[str, object]:
    return {
        "approval_binding_sha256": value.approval_binding_sha256,
        "content_sha256": value.content_sha256,
        "lock_sha256": value.lock_sha256,
        "locked_at": utc_text_v2(value.locked_at),
        "packet_id": str(value.packet_id),
        "version_id": str(value.version_id),
        "version_number": value.version_number,
    }


def lock_from_mapping_v2(value: object) -> SourcePacketLockV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "approval_binding_sha256",
                "content_sha256",
                "lock_sha256",
                "locked_at",
                "packet_id",
                "version_id",
                "version_number",
            }
        ),
    )
    return SourcePacketLockV2(
        packet_id=_uuid_text(data["packet_id"]),
        version_id=_uuid_text(data["version_id"]),
        version_number=cast(int, data["version_number"]),
        content_sha256=cast(str, data["content_sha256"]),
        approval_binding_sha256=cast(str, data["approval_binding_sha256"]),
        locked_at=_parse_utc(data["locked_at"]),
        lock_sha256=cast(str, data["lock_sha256"]),
    )


def version_mapping_v2(value: SourcePacketVersionV2) -> dict[str, object]:
    return {
        "content": content_mapping_v2(value.content),
        "content_sha256": value.content_sha256,
        "created_at": utc_text_v2(value.created_at),
        "editor_actor_fingerprint": value.editor_actor_fingerprint,
        "lock": None if value.lock is None else lock_mapping_v2(value.lock),
        "packet_id": str(value.packet_id),
        "review": None if value.review is None else review_mapping_v2(value.review),
        "status": value.status.value,
        "version_id": str(value.version_id),
        "version_number": value.version_number,
    }


def version_from_mapping_v2(value: object) -> SourcePacketVersionV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "content",
                "content_sha256",
                "created_at",
                "editor_actor_fingerprint",
                "lock",
                "packet_id",
                "review",
                "status",
                "version_id",
                "version_number",
            }
        ),
    )
    try:
        status = SourcePacketStatusV2(cast(str, data["status"]))
    except TypeError, ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return SourcePacketVersionV2(
        packet_id=_uuid_text(data["packet_id"]),
        version_id=_uuid_text(data["version_id"]),
        version_number=cast(int, data["version_number"]),
        content=content_from_mapping_v2(data["content"]),
        content_sha256=cast(str, data["content_sha256"]),
        status=status,
        created_at=_parse_utc(data["created_at"]),
        editor_actor_fingerprint=cast(str, data["editor_actor_fingerprint"]),
        review=None
        if data["review"] is None
        else review_from_mapping_v2(data["review"]),
        lock=None if data["lock"] is None else lock_from_mapping_v2(data["lock"]),
    )


def state_mapping_v2(value: SourcePacketStateV2) -> dict[str, object]:
    if type(value) is not SourcePacketStateV2:
        fail_source_packet_v2()
    return {
        "aggregate_revision": value.aggregate_revision,
        "article_plan_id": str(value.article_plan_id),
        "created_at": utc_text_v2(value.created_at),
        "creator_actor_fingerprint": value.creator_actor_fingerprint,
        "packet_id": str(value.packet_id),
        "review_assignment_id": str(value.review_assignment_id),
        "site_id": str(value.site_id),
        "versions": [version_mapping_v2(item) for item in value.versions],
    }


def state_from_mapping_v2(value: object) -> SourcePacketStateV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "aggregate_revision",
                "article_plan_id",
                "created_at",
                "creator_actor_fingerprint",
                "packet_id",
                "review_assignment_id",
                "site_id",
                "versions",
            }
        ),
    )
    versions = data["versions"]
    if type(versions) is not list:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    version_items = cast(list[object], versions)
    return SourcePacketStateV2(
        packet_id=_uuid_text(data["packet_id"]),
        site_id=_uuid_text(data["site_id"]),
        article_plan_id=_uuid_text(data["article_plan_id"]),
        review_assignment_id=_uuid_text(data["review_assignment_id"]),
        creator_actor_fingerprint=cast(str, data["creator_actor_fingerprint"]),
        created_at=_parse_utc(data["created_at"]),
        aggregate_revision=cast(int, data["aggregate_revision"]),
        versions=tuple(version_from_mapping_v2(item) for item in version_items),
    )


def generation_input_mapping_v2(
    value: ApprovedLockedGenerationInputV2,
) -> dict[str, object]:
    return {
        "aggregate_revision": value.aggregate_revision,
        "approval": review_mapping_v2(value.approval),
        "approval_binding_sha256": value.approval_binding_sha256,
        "article_plan_id": str(value.article_plan_id),
        "conflict_scan_sha256": value.conflict_scan_sha256,
        "content": content_mapping_v2(value.content),
        "content_sha256": value.content_sha256,
        "fact_membership_sha256": value.fact_membership_sha256,
        "lock_sha256": value.lock_sha256,
        "lock": lock_mapping_v2(value.lock),
        "packet_id": str(value.packet_id),
        "site_id": str(value.site_id),
        "version_id": str(value.version_id),
        "version_number": value.version_number,
    }


def generation_input_from_mapping_v2(value: object) -> ApprovedLockedGenerationInputV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "aggregate_revision",
                "approval",
                "approval_binding_sha256",
                "article_plan_id",
                "conflict_scan_sha256",
                "content",
                "content_sha256",
                "fact_membership_sha256",
                "lock",
                "lock_sha256",
                "packet_id",
                "site_id",
                "version_id",
                "version_number",
            }
        ),
    )
    return ApprovedLockedGenerationInputV2(
        packet_id=_uuid_text(data["packet_id"]),
        site_id=_uuid_text(data["site_id"]),
        article_plan_id=_uuid_text(data["article_plan_id"]),
        version_id=_uuid_text(data["version_id"]),
        version_number=cast(int, data["version_number"]),
        content=content_from_mapping_v2(data["content"]),
        content_sha256=cast(str, data["content_sha256"]),
        fact_membership_sha256=cast(str, data["fact_membership_sha256"]),
        conflict_scan_sha256=cast(str, data["conflict_scan_sha256"]),
        approval=review_from_mapping_v2(data["approval"]),
        lock=lock_from_mapping_v2(data["lock"]),
        approval_binding_sha256=cast(str, data["approval_binding_sha256"]),
        lock_sha256=cast(str, data["lock_sha256"]),
        aggregate_revision=cast(int, data["aggregate_revision"]),
    )


def command_mapping_v2(value: SourcePacketCommandV2) -> dict[str, object]:
    if type(value) is not SourcePacketCommandV2:
        fail_source_packet_v2()
    return {
        "actor_fingerprint": value.actor_fingerprint,
        "article_plan_id": None
        if value.article_plan_id is None
        else str(value.article_plan_id),
        "authorization": None
        if value.authorization is None
        else authorization_mapping_v2(value.authorization),
        "command_id": value.command_id.value,
        "content": None if value.content is None else content_mapping_v2(value.content),
        "expected_revision": value.expected_revision,
        "kind": value.kind.value,
        "occurred_at": utc_text_v2(value.occurred_at),
        "packet_id": str(value.packet_id),
        "review_assignment_id": None
        if value.review_assignment_id is None
        else str(value.review_assignment_id),
        "review_decision": None
        if value.review_decision is None
        else value.review_decision.value,
        "site_id": None if value.site_id is None else str(value.site_id),
    }


def command_from_mapping_v2(value: object) -> SourcePacketCommandV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "actor_fingerprint",
                "article_plan_id",
                "authorization",
                "command_id",
                "content",
                "expected_revision",
                "kind",
                "occurred_at",
                "packet_id",
                "review_assignment_id",
                "review_decision",
                "site_id",
            }
        ),
    )
    try:
        kind = SourcePacketCommandKindV2(cast(str, data["kind"]))
        decision = (
            None
            if data["review_decision"] is None
            else SourcePacketReviewDecisionV2(cast(str, data["review_decision"]))
        )
    except TypeError, ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return SourcePacketCommandV2(
        command_id=SourcePacketCommandIdV2(cast(str, data["command_id"])),
        kind=kind,
        packet_id=_uuid_text(data["packet_id"]),
        expected_revision=cast(int, data["expected_revision"]),
        occurred_at=_parse_utc(data["occurred_at"]),
        actor_fingerprint=cast(str, data["actor_fingerprint"]),
        site_id=None if data["site_id"] is None else _uuid_text(data["site_id"]),
        article_plan_id=None
        if data["article_plan_id"] is None
        else _uuid_text(data["article_plan_id"]),
        review_assignment_id=None
        if data["review_assignment_id"] is None
        else _uuid_text(data["review_assignment_id"]),
        content=None
        if data["content"] is None
        else content_from_mapping_v2(data["content"]),
        review_decision=decision,
        authorization=None
        if data["authorization"] is None
        else authorization_from_mapping_v2(data["authorization"]),
    )


def result_mapping_v2(value: SourcePacketCommandResultV2) -> dict[str, object]:
    if type(value) is not SourcePacketCommandResultV2:
        fail_source_packet_v2()
    return {
        "ai_action_count": value.ai_action_count,
        "chain_hash": value.chain_hash,
        "command": command_mapping_v2(value.command),
        "committed_at": utc_text_v2(value.committed_at),
        "external_action_count": value.external_action_count,
        "generation_input": None
        if value.generation_input is None
        else generation_input_mapping_v2(value.generation_input),
        "previous_chain_hash": value.previous_chain_hash,
        "provider_action_count": value.provider_action_count,
        "publication_action_count": value.publication_action_count,
        "replay_status": value.replay_status.value,
        "sequence": value.sequence,
        "state": state_mapping_v2(value.state),
    }


def result_from_mapping_v2(value: object) -> SourcePacketCommandResultV2:
    data = _exact_mapping(
        value,
        frozenset(
            {
                "ai_action_count",
                "chain_hash",
                "command",
                "committed_at",
                "external_action_count",
                "generation_input",
                "previous_chain_hash",
                "provider_action_count",
                "publication_action_count",
                "replay_status",
                "sequence",
                "state",
            }
        ),
    )
    try:
        replay = SourcePacketReplayStatusV2(cast(str, data["replay_status"]))
    except TypeError, ValueError:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return SourcePacketCommandResultV2(
        command=command_from_mapping_v2(data["command"]),
        state=state_from_mapping_v2(data["state"]),
        generation_input=None
        if data["generation_input"] is None
        else generation_input_from_mapping_v2(data["generation_input"]),
        sequence=cast(int, data["sequence"]),
        previous_chain_hash=cast(str, data["previous_chain_hash"]),
        chain_hash=cast(str, data["chain_hash"]),
        committed_at=_parse_utc(data["committed_at"]),
        replay_status=replay,
        external_action_count=cast(int, data["external_action_count"]),
        provider_action_count=cast(int, data["provider_action_count"]),
        publication_action_count=cast(int, data["publication_action_count"]),
        ai_action_count=cast(int, data["ai_action_count"]),
    )


__all__ = [
    "ApprovedLockedGenerationInputV2",
    "RecordedSourcePacketAuthorizationV2",
    "SOURCE_PACKET_AI_ACTION_COUNT_V2",
    "SOURCE_PACKET_AUTHORIZATION_ACTION_V2",
    "SOURCE_PACKET_AUTHORIZATION_OPERATION_V2",
    "SOURCE_PACKET_AUTHORIZATION_RESOURCE_KIND_V2",
    "SOURCE_PACKET_AUTHORIZATION_RESOURCE_STATE_V2",
    "SOURCE_PACKET_EXTERNAL_ACTION_COUNT_V2",
    "SOURCE_PACKET_GENESIS_SHA256_V2",
    "SOURCE_PACKET_PROVIDER_ACTION_COUNT_V2",
    "SOURCE_PACKET_PUBLICATION_ACTION_COUNT_V2",
    "SOURCE_PACKET_SCHEMA_VERSION_V2",
    "SourcePacketCommandIdV2",
    "SourcePacketCommandKindV2",
    "SourcePacketCommandResultV2",
    "SourcePacketCommandV2",
    "SourcePacketContentV2",
    "SourcePacketFailureCodeV2",
    "SourcePacketFailureV2",
    "SourcePacketLockV2",
    "SourcePacketPurposeV2",
    "SourcePacketReplayStatusV2",
    "SourcePacketReviewDecisionV2",
    "SourcePacketReviewRecordV2",
    "SourcePacketStateV2",
    "SourcePacketStatusV2",
    "SourcePacketVersionV2",
    "apply_source_packet_command_v2",
    "authorization_from_mapping_v2",
    "authorization_mapping_v2",
    "canonical_json_bytes_v2",
    "canonical_sha256_v2",
    "command_from_mapping_v2",
    "command_mapping_v2",
    "content_from_mapping_v2",
    "content_mapping_v2",
    "fail_source_packet_v2",
    "generation_input_from_mapping_v2",
    "generation_input_mapping_v2",
    "lock_from_mapping_v2",
    "lock_mapping_v2",
    "result_from_mapping_v2",
    "result_mapping_v2",
    "review_from_mapping_v2",
    "review_mapping_v2",
    "source_packet_chain_hash_v2",
    "state_from_mapping_v2",
    "state_mapping_v2",
    "utc_text_v2",
    "version_from_mapping_v2",
    "version_mapping_v2",
]
