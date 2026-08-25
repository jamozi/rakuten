"""Deterministic process-local publication command values for ST-0905.

The module models a recorded/synthetic transaction only.  It accepts exact
ST-0903 snapshot and ST-0904 projection values, retains event/audit/outbox
*intents* in memory, and carries no transport, persistence, route activation,
CMS, publication, release, or Production authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import hashlib
import hmac
import re
from typing import Final, NoReturn, SupportsIndex, cast
from uuid import RFC_4122, UUID

from raos.domain.iam.authentication import SessionId
from raos.domain.iam.step_up import StepUpAssuranceType, StepUpGrant
from raos.domain.publishing.final_approval import (
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
)
from raos.domain.publishing.public_projection_v2 import (
    PublicProjectionInputV2,
    PublicProjectionRequestV2,
    PublicProjectionResultV2,
    build_public_projection_v2,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotBuildRequestV2,
    PublicationSnapshotResultV2,
    canonical_json_bytes,
)
from raos.domain.shared.persistence import Sha256Digest


PROFILE: Final = "ST0905_PUBLICATION_COMMANDS_RECORDED_LOCAL_V2"
MAX_REASON_LENGTH: Final = 4000
MAX_KNOWN_SNAPSHOTS: Final = 32
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{7,199}\Z", re.ASCII)
_SAFE_REASON = re.compile(r"[^\x00-\x08\x0b\x0c\x0e-\x1f\x7f]+\Z")


class PublicationCommandAction(StrEnum):
    PUBLISH = "PUBLISH"
    ROLLBACK = "ROLLBACK"
    UNPUBLISH = "UNPUBLISH"


class PublicationCommandRole(StrEnum):
    MANAGING_EDITOR = "MANAGING_EDITOR"
    OPERATOR = "OPERATOR"


class PublicationLocalState(StrEnum):
    UNPUBLISHED = "UNPUBLISHED"
    PUBLISHED = "PUBLISHED"


class PublicationCommandExecution(StrEnum):
    RECORDED_SYNTHETIC_PROCESS_LOCAL = "RECORDED_SYNTHETIC_PROCESS_LOCAL"


class ExternalGateStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"


class PublicationCommandFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    ACTIVE_HUMAN_REQUIRED = "ACTIVE_HUMAN_REQUIRED"
    ROLE_FORBIDDEN = "ROLE_FORBIDDEN"
    MFA_REQUIRED = "MFA_REQUIRED"
    STEP_UP_REQUIRED = "STEP_UP_REQUIRED"
    STEP_UP_STALE = "STEP_UP_STALE"
    SITE_SCOPE_MISMATCH = "SITE_SCOPE_MISMATCH"
    SEPARATION_OF_DUTIES_REQUIRED = "SEPARATION_OF_DUTIES_REQUIRED"
    FINAL_APPROVAL_INVALID = "FINAL_APPROVAL_INVALID"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    PROJECTION_INVALID = "PROJECTION_INVALID"
    SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"
    KILL_SWITCH_DENIED = "KILL_SWITCH_DENIED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    CONCURRENCY_CONFLICT = "CONCURRENCY_CONFLICT"
    PUBLICATION_STATE_DRIFT = "PUBLICATION_STATE_DRIFT"
    ROLLBACK_TARGET_UNKNOWN = "ROLLBACK_TARGET_UNKNOWN"
    ROLLBACK_TARGET_CURRENT = "ROLLBACK_TARGET_CURRENT"
    ROLLBACK_TARGET_NOT_PREVIOUS = "ROLLBACK_TARGET_NOT_PREVIOUS"
    UNPUBLISH_ROLE_ACTION_UNDEFINED = "UNPUBLISH_ROLE_ACTION_UNDEFINED"
    TRANSACTION_FAILED = "TRANSACTION_FAILED"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class PublicationCommandFailure(RuntimeError):
    __slots__ = ("_code",)

    def __init__(self, code: PublicationCommandFailureCode) -> None:
        if type(code) is not PublicationCommandFailureCode:
            raise TypeError("invalid publication command failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> PublicationCommandFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"PublicationCommandFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication command failure serialization is forbidden")


def fail_publication_command(
    code: PublicationCommandFailureCode = PublicationCommandFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise PublicationCommandFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0905-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0905-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication command value serialization is forbidden")


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_publication_command()
    try:
        return Sha256Digest(value.value)
    except Exception:
        fail_publication_command()


def _digest_bytes(payload: bytes) -> Sha256Digest:
    if type(payload) is not bytes or not payload:
        fail_publication_command()
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _digest(value: object) -> Sha256Digest:
    return _digest_bytes(canonical_json_bytes(value))


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_publication_command()
    return value


def _uuid(value: object) -> UUID:
    if type(value) is not UUID or value.variant != RFC_4122:
        fail_publication_command()
    return value


def _instant(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC or value.fold:
        fail_publication_command()
    return value


def _instant_text(value: datetime) -> str:
    return _instant(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _reason(value: object) -> str:
    if (
        type(value) is not str
        or not 10 <= len(value) <= MAX_REASON_LENGTH
        or value != value.strip()
        or _SAFE_REASON.fullmatch(value) is None
    ):
        fail_publication_command()
    return value


def _idempotency(value: object) -> str:
    if type(value) is not str or _IDEMPOTENCY.fullmatch(value) is None:
        fail_publication_command()
    return value


def _copy_step_up(value: object) -> StepUpGrant:
    if type(value) is not StepUpGrant:
        fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)
    try:
        return StepUpGrant(
            session_id=value.session_id,
            issuer=value.issuer,
            subject=value.subject,
            assurance_type=value.assurance_type,
            authenticated_at=value.authenticated_at,
            expires_at=value.expires_at,
        )
    except Exception:
        fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)


@dataclass(frozen=True, slots=True, repr=False)
class PublicationCommandAuthorizationV2(_Redacted):
    actor_id: UUID
    site_id: UUID
    role: PublicationCommandRole
    session_id: SessionId
    step_up_grant: StepUpGrant
    observed_at: datetime
    active_human: bool = True
    mfa_verified: bool = True
    provider_identity_mapping: str = "RECORDED_SYNTHETIC_LOCAL_ONLY"
    external_authority: bool = False
    authorization_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        actor = _uuid7(self.actor_id)
        site = _uuid7(self.site_id)
        if type(self.role) is not PublicationCommandRole:
            fail_publication_command(PublicationCommandFailureCode.ROLE_FORBIDDEN)
        if type(self.session_id) is not SessionId:
            fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)
        grant = _copy_step_up(self.step_up_grant)
        observed = _instant(self.observed_at)
        if self.active_human is not True:
            fail_publication_command(
                PublicationCommandFailureCode.ACTIVE_HUMAN_REQUIRED
            )
        if self.mfa_verified is not True:
            fail_publication_command(PublicationCommandFailureCode.MFA_REQUIRED)
        if (
            grant.assurance_type is not StepUpAssuranceType.MULTI_FACTOR
            or not hmac.compare_digest(
                grant.session_id.fingerprint(), self.session_id.fingerprint()
            )
        ):
            fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)
        if observed < grant.authenticated_at or observed >= grant.expires_at:
            fail_publication_command(PublicationCommandFailureCode.STEP_UP_STALE)
        if (
            self.provider_identity_mapping != "RECORDED_SYNTHETIC_LOCAL_ONLY"
            or self.external_authority is not False
        ):
            fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)
        principal_material = (
            grant.issuer.reveal().encode("utf-8")
            + b"\x00"
            + grant.subject.reveal().encode("utf-8")
        )
        object.__setattr__(self, "actor_id", actor)
        object.__setattr__(self, "site_id", site)
        object.__setattr__(self, "step_up_grant", grant)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(
            self,
            "authorization_sha256",
            _digest(
                {
                    "active_human": True,
                    "actor_id": str(actor),
                    "external_authority": False,
                    "mfa_verified": True,
                    "observed_at": _instant_text(observed),
                    "principal_binding_sha256": hashlib.sha256(
                        principal_material
                    ).hexdigest(),
                    "profile": PROFILE,
                    "provider_identity_mapping": self.provider_identity_mapping,
                    "role": self.role.value,
                    "session_fingerprint": self.session_id.fingerprint(),
                    "site_id": str(site),
                    "step_up_authenticated_at": _instant_text(grant.authenticated_at),
                    "step_up_expires_at": _instant_text(grant.expires_at),
                }
            ),
        )

    def require_valid(self) -> None:
        rebuilt = PublicationCommandAuthorizationV2(
            actor_id=self.actor_id,
            site_id=self.site_id,
            role=self.role,
            session_id=self.session_id,
            step_up_grant=self.step_up_grant,
            observed_at=self.observed_at,
            active_human=self.active_human,
            mfa_verified=self.mfa_verified,
            provider_identity_mapping=self.provider_identity_mapping,
            external_authority=self.external_authority,
        )
        if rebuilt.authorization_sha256 != self.authorization_sha256:
            fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)


@dataclass(frozen=True, slots=True, repr=False)
class PublicationKillSwitchSafeStateV2(_Redacted):
    observation_id: UUID
    generation: int
    observed_at: datetime
    fresh_until: datetime
    source_sha256: Sha256Digest
    complete: bool = True
    engaged: bool = False
    publication_commands_allowed: bool = True
    mode: str = "RECORDED_SYNTHETIC_LOCAL_ONLY"
    external_authority: bool = False
    state_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        identity = _uuid7(self.observation_id)
        observed = _instant(self.observed_at)
        fresh_until = _instant(self.fresh_until)
        source = _sha(self.source_sha256)
        if (
            type(self.generation) is not int
            or not 1 <= self.generation <= (1 << 63) - 1
            or observed >= fresh_until
            or self.complete is not True
            or self.engaged is not False
            or self.publication_commands_allowed is not True
            or self.mode != "RECORDED_SYNTHETIC_LOCAL_ONLY"
            or self.external_authority is not False
        ):
            fail_publication_command(PublicationCommandFailureCode.KILL_SWITCH_DENIED)
        object.__setattr__(self, "observation_id", identity)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "fresh_until", fresh_until)
        object.__setattr__(self, "source_sha256", source)
        object.__setattr__(
            self,
            "state_sha256",
            _digest(
                {
                    "complete": True,
                    "engaged": False,
                    "external_authority": False,
                    "fresh_until": _instant_text(fresh_until),
                    "generation": self.generation,
                    "mode": self.mode,
                    "observation_id": str(identity),
                    "observed_at": _instant_text(observed),
                    "profile": PROFILE,
                    "publication_commands_allowed": True,
                    "source_sha256": source.value,
                }
            ),
        )

    def require_valid_at(self, now: datetime) -> None:
        observed_now = _instant(now)
        rebuilt = PublicationKillSwitchSafeStateV2(
            observation_id=self.observation_id,
            generation=self.generation,
            observed_at=self.observed_at,
            fresh_until=self.fresh_until,
            source_sha256=self.source_sha256,
            complete=self.complete,
            engaged=self.engaged,
            publication_commands_allowed=self.publication_commands_allowed,
            mode=self.mode,
            external_authority=self.external_authority,
        )
        if (
            rebuilt.state_sha256 != self.state_sha256
            or observed_now < self.observed_at
            or observed_now >= self.fresh_until
        ):
            fail_publication_command(PublicationCommandFailureCode.KILL_SWITCH_DENIED)


@dataclass(frozen=True, slots=True, repr=False)
class KnownPublicationSnapshotV2(_Redacted):
    final_approval_request: FinalApprovalRequestV2
    final_approval_result: FinalApprovalResultV2
    snapshot_request: PublicationSnapshotBuildRequestV2
    snapshot_result: PublicationSnapshotResultV2
    projection_request: PublicProjectionRequestV2
    projection_result: PublicProjectionResultV2
    snapshot_fixture_sha256: Sha256Digest
    projection_fixture_sha256: Sha256Digest
    source_binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.final_approval_request) is not FinalApprovalRequestV2
            or type(self.final_approval_result) is not FinalApprovalResultV2
            or type(self.snapshot_request) is not PublicationSnapshotBuildRequestV2
            or type(self.snapshot_result) is not PublicationSnapshotResultV2
            or type(self.projection_request) is not PublicProjectionRequestV2
            or type(self.projection_result) is not PublicProjectionResultV2
        ):
            fail_publication_command(PublicationCommandFailureCode.SNAPSHOT_INVALID)
        try:
            self.final_approval_request.require_valid()
            self.final_approval_result.require_valid()
            self.snapshot_request.require_valid()
            expected_projection = build_public_projection_v2(
                request=self.projection_request,
                source=PublicProjectionInputV2(
                    snapshot_request=self.snapshot_request,
                    snapshot_result=self.snapshot_result,
                    source_fixture_sha256=self.snapshot_fixture_sha256,
                ),
            )
        except Exception:
            fail_publication_command(PublicationCommandFailureCode.SNAPSHOT_INVALID)
        snapshot_source = _sha(self.snapshot_fixture_sha256)
        projection_source = _sha(self.projection_fixture_sha256)
        try:
            snapshot = self.snapshot_result.snapshot()
            projection = self.projection_result.projection()
            article = cast(dict[str, object], projection["article"])
        except Exception:
            fail_publication_command(PublicationCommandFailureCode.PROJECTION_INVALID)
        if (
            self.final_approval_result.request_sha256
            != self.final_approval_request.request_sha256
            or self.final_approval_result.record.decision != "APPROVED"
            or self.final_approval_result.local_final_approval_recorded is not True
            or self.final_approval_result.publication_authorized is not False
            or self.final_approval_result.production_authorized is not False
            or self.snapshot_result.request_sha256
            != self.snapshot_request.request_sha256
            or self.snapshot_result.publication_authorized is not False
            or self.snapshot_result.production_authorized is not False
            or snapshot.get("approval_ids")
            != [str(self.final_approval_result.record.approval_id.value)]
            or snapshot.get("article_version_id")
            != str(self.final_approval_result.record.article_version_id.value)
            or snapshot.get("publication_id")
            != str(self.snapshot_request.publication_id)
            or article.get("publication_id")
            != str(self.snapshot_request.publication_id)
            or article.get("publication_snapshot_id")
            != str(self.snapshot_request.snapshot_artifact_id)
            or self.projection_result.canonical_bytes()
            != expected_projection.canonical_bytes()
            or self.projection_result.projection_bytes
            != expected_projection.projection_bytes
            or self.projection_result.route_activated is not False
            or self.projection_result.public_read_served is not False
            or self.projection_result.publication_authorized is not False
            or self.projection_result.production_authorized is not False
        ):
            fail_publication_command(PublicationCommandFailureCode.PROJECTION_INVALID)
        object.__setattr__(self, "snapshot_fixture_sha256", snapshot_source)
        object.__setattr__(self, "projection_fixture_sha256", projection_source)
        object.__setattr__(
            self,
            "source_binding_sha256",
            _digest(
                {
                    "approval_record_sha256": (
                        self.final_approval_result.record.record_sha256.value
                    ),
                    "approval_result_sha256": self.final_approval_result.result_sha256.value,
                    "profile": PROFILE,
                    "projection_fixture_sha256": projection_source.value,
                    "projection_request_sha256": self.projection_request.request_sha256.value,
                    "projection_result_sha256": self.projection_result.result_sha256.value,
                    "projection_sha256": self.projection_result.projection_sha256.value,
                    "snapshot_artifact_id": str(
                        self.snapshot_request.snapshot_artifact_id
                    ),
                    "snapshot_artifact_sha256": (
                        self.snapshot_result.snapshot_artifact_sha256.value
                    ),
                    "snapshot_fixture_sha256": snapshot_source.value,
                    "snapshot_request_sha256": self.snapshot_request.request_sha256.value,
                    "snapshot_result_sha256": self.snapshot_result.result_sha256.value,
                    "snapshot_sha256": self.snapshot_result.snapshot_sha256.value,
                }
            ),
        )

    @property
    def snapshot_id(self) -> UUID:
        return self.snapshot_request.snapshot_artifact_id

    @property
    def publication_id(self) -> UUID:
        return self.snapshot_request.publication_id

    def require_valid(self) -> None:
        rebuilt = KnownPublicationSnapshotV2(
            final_approval_request=self.final_approval_request,
            final_approval_result=self.final_approval_result,
            snapshot_request=self.snapshot_request,
            snapshot_result=self.snapshot_result,
            projection_request=self.projection_request,
            projection_result=self.projection_result,
            snapshot_fixture_sha256=self.snapshot_fixture_sha256,
            projection_fixture_sha256=self.projection_fixture_sha256,
        )
        if rebuilt.source_binding_sha256 != self.source_binding_sha256:
            fail_publication_command(PublicationCommandFailureCode.SOURCE_HASH_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class PublicationCommandSourcesV2(_Redacted):
    snapshots: tuple[KnownPublicationSnapshotV2, ...]
    sources_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.snapshots) is not tuple
            or not 2 <= len(self.snapshots) <= MAX_KNOWN_SNAPSHOTS
            or any(
                type(item) is not KnownPublicationSnapshotV2 for item in self.snapshots
            )
        ):
            fail_publication_command(PublicationCommandFailureCode.SNAPSHOT_INVALID)
        for item in self.snapshots:
            item.require_valid()
        publication_ids = {item.publication_id for item in self.snapshots}
        snapshot_ids = tuple(item.snapshot_id for item in self.snapshots)
        request_hashes = tuple(
            item.snapshot_request.request_sha256.value for item in self.snapshots
        )
        created = tuple(item.snapshot_request.created_at for item in self.snapshots)
        if (
            len(publication_ids) != 1
            or len(set(snapshot_ids)) != len(snapshot_ids)
            or len(set(request_hashes)) != len(request_hashes)
            or created != tuple(sorted(created))
            or len(set(created)) != len(created)
        ):
            fail_publication_command(PublicationCommandFailureCode.SNAPSHOT_INVALID)
        object.__setattr__(
            self,
            "sources_sha256",
            _digest(
                {
                    "ordered_source_bindings": [
                        item.source_binding_sha256.value for item in self.snapshots
                    ],
                    "profile": PROFILE,
                    "publication_id": str(self.snapshots[0].publication_id),
                }
            ),
        )

    @property
    def publication_id(self) -> UUID:
        return self.snapshots[0].publication_id

    @property
    def latest(self) -> KnownPublicationSnapshotV2:
        return self.snapshots[-1]

    def by_id(self, value: UUID) -> KnownPublicationSnapshotV2 | None:
        if type(value) is not UUID:
            return None
        for item in self.snapshots:
            if item.snapshot_id == value:
                return item
        return None

    def index(self, value: UUID) -> int | None:
        for index, item in enumerate(self.snapshots):
            if item.snapshot_id == value:
                return index
        return None

    def require_valid(self) -> None:
        rebuilt = PublicationCommandSourcesV2(snapshots=self.snapshots)
        if rebuilt.sources_sha256 != self.sources_sha256:
            fail_publication_command(PublicationCommandFailureCode.SOURCE_HASH_MISMATCH)


def _common_payload(
    *,
    action: PublicationCommandAction,
    publication_id: UUID,
    expected_generation: int,
    idempotency_key: str,
    authorization: PublicationCommandAuthorizationV2,
    kill_switch: PublicationKillSwitchSafeStateV2,
    occurred_at: datetime,
    correlation_id: UUID,
    event_id: UUID,
    audit_id: UUID,
    outbox_id: UUID,
) -> dict[str, object]:
    return {
        "action": action.value,
        "audit_id": str(audit_id),
        "authorization_sha256": authorization.authorization_sha256.value,
        "correlation_id": str(correlation_id),
        "event_id": str(event_id),
        "expected_generation": expected_generation,
        "idempotency_key_sha256": hashlib.sha256(
            idempotency_key.encode("ascii")
        ).hexdigest(),
        "kill_switch_state_sha256": kill_switch.state_sha256.value,
        "occurred_at": _instant_text(occurred_at),
        "outbox_id": str(outbox_id),
        "profile": PROFILE,
        "publication_id": str(publication_id),
    }


def _validate_common(
    *,
    action: object,
    publication_id: object,
    expected_generation: object,
    idempotency_key: object,
    authorization: object,
    kill_switch: object,
    occurred_at: object,
    correlation_id: object,
    event_id: object,
    audit_id: object,
    outbox_id: object,
) -> tuple[
    PublicationCommandAction,
    UUID,
    int,
    str,
    PublicationCommandAuthorizationV2,
    PublicationKillSwitchSafeStateV2,
    datetime,
    UUID,
    UUID,
    UUID,
    UUID,
]:
    if type(action) is not PublicationCommandAction:
        fail_publication_command()
    publication = _uuid7(publication_id)
    if (
        type(expected_generation) is not int
        or not 0 <= expected_generation <= (1 << 63) - 2
    ):
        fail_publication_command()
    key = _idempotency(idempotency_key)
    if type(authorization) is not PublicationCommandAuthorizationV2:
        fail_publication_command(PublicationCommandFailureCode.STEP_UP_REQUIRED)
    authorization.require_valid()
    if type(kill_switch) is not PublicationKillSwitchSafeStateV2:
        fail_publication_command(PublicationCommandFailureCode.KILL_SWITCH_DENIED)
    when = _instant(occurred_at)
    kill_switch.require_valid_at(when)
    if when != authorization.observed_at:
        fail_publication_command(PublicationCommandFailureCode.STEP_UP_STALE)
    if action in {PublicationCommandAction.PUBLISH, PublicationCommandAction.ROLLBACK}:
        if authorization.role not in {
            PublicationCommandRole.MANAGING_EDITOR,
            PublicationCommandRole.OPERATOR,
        }:
            fail_publication_command(PublicationCommandFailureCode.ROLE_FORBIDDEN)
    elif action is not PublicationCommandAction.UNPUBLISH:
        fail_publication_command()
    return (
        action,
        publication,
        expected_generation,
        key,
        authorization,
        kill_switch,
        when,
        _uuid(correlation_id),
        _uuid(event_id),
        _uuid(audit_id),
        _uuid(outbox_id),
    )


@dataclass(frozen=True, slots=True, repr=False)
class PublishCommandV2(_Redacted):
    publication_id: UUID
    publication_candidate_id: UUID
    snapshot_id: UUID
    expected_source_binding_sha256: Sha256Digest
    expected_generation: int
    idempotency_key: str
    authorization: PublicationCommandAuthorizationV2
    kill_switch: PublicationKillSwitchSafeStateV2
    occurred_at: datetime
    correlation_id: UUID
    event_id: UUID
    audit_id: UUID
    outbox_id: UUID
    scheduled_for: None = None
    verify_after_publish: bool = True
    action: PublicationCommandAction = PublicationCommandAction.PUBLISH
    command_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        (
            action,
            publication,
            generation,
            key,
            authorization,
            kill_switch,
            occurred,
            correlation,
            event,
            audit,
            outbox,
        ) = _validate_common(
            action=self.action,
            publication_id=self.publication_id,
            expected_generation=self.expected_generation,
            idempotency_key=self.idempotency_key,
            authorization=self.authorization,
            kill_switch=self.kill_switch,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            event_id=self.event_id,
            audit_id=self.audit_id,
            outbox_id=self.outbox_id,
        )
        candidate = _uuid7(self.publication_candidate_id)
        snapshot = _uuid7(self.snapshot_id)
        source = _sha(self.expected_source_binding_sha256)
        if self.scheduled_for is not None or self.verify_after_publish is not True:
            fail_publication_command()
        for name, value in (
            ("publication_id", publication),
            ("publication_candidate_id", candidate),
            ("snapshot_id", snapshot),
            ("expected_source_binding_sha256", source),
            ("expected_generation", generation),
            ("idempotency_key", key),
            ("authorization", authorization),
            ("kill_switch", kill_switch),
            ("occurred_at", occurred),
            ("correlation_id", correlation),
            ("event_id", event),
            ("audit_id", audit),
            ("outbox_id", outbox),
            ("action", action),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "command_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        value = _common_payload(
            action=self.action,
            publication_id=self.publication_id,
            expected_generation=self.expected_generation,
            idempotency_key=self.idempotency_key,
            authorization=self.authorization,
            kill_switch=self.kill_switch,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            event_id=self.event_id,
            audit_id=self.audit_id,
            outbox_id=self.outbox_id,
        )
        value.update(
            {
                "expected_source_binding_sha256": (
                    self.expected_source_binding_sha256.value
                ),
                "publication_candidate_id": str(self.publication_candidate_id),
                "scheduled_for": None,
                "snapshot_id": str(self.snapshot_id),
                "verify_after_publish": True,
            }
        )
        return value

    def canonical_bytes(self) -> bytes:
        value = self._payload()
        value["command_sha256"] = self.command_sha256.value
        return canonical_json_bytes(value)


@dataclass(frozen=True, slots=True, repr=False)
class RollbackCommandV2(_Redacted):
    publication_id: UUID
    from_snapshot_id: UUID
    to_snapshot_id: UUID
    expected_from_source_binding_sha256: Sha256Digest
    expected_to_source_binding_sha256: Sha256Digest
    expected_generation: int
    reason: str
    rollback_record_id: UUID
    idempotency_key: str
    authorization: PublicationCommandAuthorizationV2
    kill_switch: PublicationKillSwitchSafeStateV2
    occurred_at: datetime
    correlation_id: UUID
    event_id: UUID
    audit_id: UUID
    outbox_id: UUID
    verification_required: bool = True
    action: PublicationCommandAction = PublicationCommandAction.ROLLBACK
    command_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        (
            action,
            publication,
            generation,
            key,
            authorization,
            kill_switch,
            occurred,
            correlation,
            event,
            audit,
            outbox,
        ) = _validate_common(
            action=self.action,
            publication_id=self.publication_id,
            expected_generation=self.expected_generation,
            idempotency_key=self.idempotency_key,
            authorization=self.authorization,
            kill_switch=self.kill_switch,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            event_id=self.event_id,
            audit_id=self.audit_id,
            outbox_id=self.outbox_id,
        )
        from_snapshot = _uuid7(self.from_snapshot_id)
        to_snapshot = _uuid7(self.to_snapshot_id)
        from_source = _sha(self.expected_from_source_binding_sha256)
        to_source = _sha(self.expected_to_source_binding_sha256)
        reason = _reason(self.reason)
        rollback_record = _uuid(self.rollback_record_id)
        if self.verification_required is not True:
            fail_publication_command()
        for name, value in (
            ("publication_id", publication),
            ("from_snapshot_id", from_snapshot),
            ("to_snapshot_id", to_snapshot),
            ("expected_from_source_binding_sha256", from_source),
            ("expected_to_source_binding_sha256", to_source),
            ("expected_generation", generation),
            ("reason", reason),
            ("rollback_record_id", rollback_record),
            ("idempotency_key", key),
            ("authorization", authorization),
            ("kill_switch", kill_switch),
            ("occurred_at", occurred),
            ("correlation_id", correlation),
            ("event_id", event),
            ("audit_id", audit),
            ("outbox_id", outbox),
            ("action", action),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "command_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        value = _common_payload(
            action=self.action,
            publication_id=self.publication_id,
            expected_generation=self.expected_generation,
            idempotency_key=self.idempotency_key,
            authorization=self.authorization,
            kill_switch=self.kill_switch,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            event_id=self.event_id,
            audit_id=self.audit_id,
            outbox_id=self.outbox_id,
        )
        value.update(
            {
                "expected_from_source_binding_sha256": (
                    self.expected_from_source_binding_sha256.value
                ),
                "expected_to_source_binding_sha256": (
                    self.expected_to_source_binding_sha256.value
                ),
                "from_snapshot_id": str(self.from_snapshot_id),
                "reason_sha256": hashlib.sha256(
                    self.reason.encode("utf-8")
                ).hexdigest(),
                "rollback_record_id": str(self.rollback_record_id),
                "to_snapshot_id": str(self.to_snapshot_id),
                "verification_required": True,
            }
        )
        return value

    def canonical_bytes(self) -> bytes:
        value = self._payload()
        value["command_sha256"] = self.command_sha256.value
        return canonical_json_bytes(value)


@dataclass(frozen=True, slots=True, repr=False)
class UnpublishCommandV2(_Redacted):
    publication_id: UUID
    expected_generation: int
    reason: str
    idempotency_key: str
    authorization: PublicationCommandAuthorizationV2
    kill_switch: PublicationKillSwitchSafeStateV2
    occurred_at: datetime
    correlation_id: UUID
    event_id: UUID
    audit_id: UUID
    outbox_id: UUID
    action: PublicationCommandAction = PublicationCommandAction.UNPUBLISH

    def __post_init__(self) -> None:
        _reason(self.reason)
        _validate_common(
            action=self.action,
            publication_id=self.publication_id,
            expected_generation=self.expected_generation,
            idempotency_key=self.idempotency_key,
            authorization=self.authorization,
            kill_switch=self.kill_switch,
            occurred_at=self.occurred_at,
            correlation_id=self.correlation_id,
            event_id=self.event_id,
            audit_id=self.audit_id,
            outbox_id=self.outbox_id,
        )


def _event_envelope(
    *,
    command: PublishCommandV2 | RollbackCommandV2,
    event_type: str,
    dataschema: str,
    generation: int,
    data: dict[str, object],
) -> bytes:
    return canonical_json_bytes(
        {
            "actor": {
                "actor_id": str(command.authorization.actor_id),
                "actor_type": "USER",
                "service_name": None,
            },
            "aggregate": {
                "id": str(command.publication_id),
                "type": "publication",
                "version": generation,
            },
            "causation_id": None,
            "classification": "INTERNAL",
            "correlation_id": str(command.correlation_id),
            "data": data,
            "datacontenttype": "application/json",
            "dataschema": dataschema,
            "event_version": 1,
            "id": str(command.event_id),
            "partition_key": str(command.publication_id),
            "producer": "publishing",
            "site_id": str(command.authorization.site_id),
            "source": "urn:raos:publishing",
            "specversion": "1.0",
            "subject": f"urn:raos:publication:{command.publication_id}",
            "time": _instant_text(command.occurred_at),
            "traceparent": None,
            "type": event_type,
        }
    )


def _audit_bytes(
    *,
    command: PublishCommandV2 | RollbackCommandV2,
    action: str,
    generation: int,
    from_snapshot_id: UUID | None,
    to_snapshot_id: UUID,
    approval_id: UUID,
) -> bytes:
    payload: dict[str, object] = {
        "action": action,
        "actor_id": str(command.authorization.actor_id),
        "approval_id": str(approval_id),
        "audit_id": str(command.audit_id),
        "authorization_sha256": command.authorization.authorization_sha256.value,
        "command_sha256": command.command_sha256.value,
        "external_write": False,
        "from_snapshot_id": str(from_snapshot_id)
        if from_snapshot_id is not None
        else None,
        "generation": generation,
        "kill_switch_state_sha256": command.kill_switch.state_sha256.value,
        "occurred_at": _instant_text(command.occurred_at),
        "profile": PROFILE,
        "publication_id": str(command.publication_id),
        "result": "LOCAL_SIMULATED_COMMIT",
        "to_snapshot_id": str(to_snapshot_id),
    }
    if type(command) is RollbackCommandV2:
        payload["reason_sha256"] = hashlib.sha256(
            command.reason.encode("utf-8")
        ).hexdigest()
        payload["rollback_record_id"] = str(command.rollback_record_id)
    return canonical_json_bytes(payload)


def _outbox_bytes(
    *,
    command: PublishCommandV2 | RollbackCommandV2,
    event_type: str,
    generation: int,
    event_bytes: bytes,
) -> bytes:
    return canonical_json_bytes(
        {
            "aggregate_id": str(command.publication_id),
            "aggregate_type": "publication",
            "aggregate_version": generation,
            "event_sha256": _digest_bytes(event_bytes).value,
            "event_type": event_type,
            "outbox_id": str(command.outbox_id),
            "profile": PROFILE,
            "published": False,
            "status": "PROCESS_LOCAL_NOT_PUBLISHED",
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class PublicationCommandResultV2(_Redacted):
    action: PublicationCommandAction
    command_sha256: Sha256Digest
    publication_id: UUID
    from_snapshot_id: UUID | None
    to_snapshot_id: UUID
    generation: int
    projection_bytes: bytes
    projection_sha256: Sha256Digest
    event_bytes: bytes
    event_sha256: Sha256Digest
    audit_bytes: bytes
    audit_sha256: Sha256Digest
    outbox_bytes: bytes
    outbox_sha256: Sha256Digest
    execution: PublicationCommandExecution = (
        PublicationCommandExecution.RECORDED_SYNTHETIC_PROCESS_LOCAL
    )
    local_transaction_committed: bool = True
    projection_persisted: bool = False
    event_emitted: bool = False
    audit_persisted: bool = False
    outbox_persisted: bool = False
    route_activated: bool = False
    public_read_served: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    formal_tst_012_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_013_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_021_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    live_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    staging_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    publication_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    release_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    production_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    result_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if self.action not in {
            PublicationCommandAction.PUBLISH,
            PublicationCommandAction.ROLLBACK,
        }:
            fail_publication_command(PublicationCommandFailureCode.OUTCOME_MISMATCH)
        command_sha = _sha(self.command_sha256)
        publication = _uuid7(self.publication_id)
        if self.from_snapshot_id is not None:
            _uuid7(self.from_snapshot_id)
        target = _uuid7(self.to_snapshot_id)
        if (
            type(self.generation) is not int
            or not 1 <= self.generation <= (1 << 63) - 1
        ):
            fail_publication_command(PublicationCommandFailureCode.OUTCOME_MISMATCH)
        projection_sha = _sha(self.projection_sha256)
        event_sha = _sha(self.event_sha256)
        audit_sha = _sha(self.audit_sha256)
        outbox_sha = _sha(self.outbox_sha256)
        if (
            _digest_bytes(self.projection_bytes) != projection_sha
            or _digest_bytes(self.event_bytes) != event_sha
            or _digest_bytes(self.audit_bytes) != audit_sha
            or _digest_bytes(self.outbox_bytes) != outbox_sha
            or self.execution
            is not PublicationCommandExecution.RECORDED_SYNTHETIC_PROCESS_LOCAL
            or self.local_transaction_committed is not True
            or any(
                value is not False
                for value in (
                    self.projection_persisted,
                    self.event_emitted,
                    self.audit_persisted,
                    self.outbox_persisted,
                    self.route_activated,
                    self.public_read_served,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_authorized,
                )
            )
            or any(
                status is not ExternalGateStatus.NOT_EXECUTED
                for status in (
                    self.formal_tst_012_status,
                    self.formal_tst_013_status,
                    self.formal_tst_021_status,
                    self.live_status,
                    self.staging_status,
                    self.publication_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_publication_command(PublicationCommandFailureCode.OUTCOME_MISMATCH)
        object.__setattr__(self, "command_sha256", command_sha)
        object.__setattr__(self, "publication_id", publication)
        object.__setattr__(self, "to_snapshot_id", target)
        object.__setattr__(self, "projection_sha256", projection_sha)
        object.__setattr__(self, "event_sha256", event_sha)
        object.__setattr__(self, "audit_sha256", audit_sha)
        object.__setattr__(self, "outbox_sha256", outbox_sha)
        object.__setattr__(self, "result_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "action": self.action.value,
            "audit_persisted": False,
            "audit_sha256": self.audit_sha256.value,
            "command_sha256": self.command_sha256.value,
            "event_emitted": False,
            "event_sha256": self.event_sha256.value,
            "execution": self.execution.value,
            "external_gates": {
                "formal_tst_012": self.formal_tst_012_status.value,
                "formal_tst_013": self.formal_tst_013_status.value,
                "formal_tst_021": self.formal_tst_021_status.value,
                "live": self.live_status.value,
                "production": self.production_status.value,
                "publication": self.publication_status.value,
                "release": self.release_status.value,
                "staging": self.staging_status.value,
            },
            "from_snapshot_id": str(self.from_snapshot_id)
            if self.from_snapshot_id is not None
            else None,
            "generation": self.generation,
            "local_transaction_committed": True,
            "outbox_persisted": False,
            "outbox_sha256": self.outbox_sha256.value,
            "production_authorized": False,
            "profile": PROFILE,
            "projection_persisted": False,
            "projection_sha256": self.projection_sha256.value,
            "public_read_served": False,
            "publication_authorized": False,
            "publication_id": str(self.publication_id),
            "release_authorized": False,
            "route_activated": False,
            "to_snapshot_id": str(self.to_snapshot_id),
        }

    def canonical_bytes(self) -> bytes:
        value = self._payload()
        value["result_sha256"] = self.result_sha256.value
        return canonical_json_bytes(value)


def build_publish_result_v2(
    *,
    command: PublishCommandV2,
    source: KnownPublicationSnapshotV2,
    generation: int,
) -> PublicationCommandResultV2:
    if (
        type(command) is not PublishCommandV2
        or type(source) is not KnownPublicationSnapshotV2
    ):
        fail_publication_command()
    source.require_valid()
    if (
        command.publication_id != source.publication_id
        or command.publication_candidate_id
        != source.snapshot_request.publication_candidate_id
        or command.snapshot_id != source.snapshot_id
        or command.expected_source_binding_sha256 != source.source_binding_sha256
    ):
        fail_publication_command(PublicationCommandFailureCode.SOURCE_HASH_MISMATCH)
    if (
        command.authorization.site_id
        != source.final_approval_result.record.site_id.value
    ):
        fail_publication_command(PublicationCommandFailureCode.SITE_SCOPE_MISMATCH)
    if (
        command.authorization.actor_id
        == source.final_approval_result.record.approved_by.value
    ):
        fail_publication_command(
            PublicationCommandFailureCode.SEPARATION_OF_DUTIES_REQUIRED
        )
    projection = source.projection_result.projection()
    article = cast(dict[str, object], projection["article"])
    event_type = "jp.raos.publishing.article_published.v1"
    event = _event_envelope(
        command=command,
        event_type=event_type,
        dataschema=(
            "https://schemas.raos.local/events/"
            "jp-raos-publishing-article-published-v1.schema.json"
        ),
        generation=generation,
        data={
            "article_id": article["article_id"],
            "canonical_path": article["canonical_path"],
            "projection_generation": article["projection_generation"],
            "publication_id": str(command.publication_id),
            "publication_snapshot_id": str(source.snapshot_id),
            "published_at": _instant_text(command.occurred_at),
        },
    )
    audit = _audit_bytes(
        command=command,
        action="publication_publish_local_simulated",
        generation=generation,
        from_snapshot_id=None,
        to_snapshot_id=source.snapshot_id,
        approval_id=source.final_approval_result.record.approval_id.value,
    )
    outbox = _outbox_bytes(
        command=command,
        event_type=event_type,
        generation=generation,
        event_bytes=event,
    )
    return PublicationCommandResultV2(
        action=PublicationCommandAction.PUBLISH,
        command_sha256=command.command_sha256,
        publication_id=command.publication_id,
        from_snapshot_id=None,
        to_snapshot_id=source.snapshot_id,
        generation=generation,
        projection_bytes=source.projection_result.projection_bytes,
        projection_sha256=source.projection_result.projection_sha256,
        event_bytes=event,
        event_sha256=_digest_bytes(event),
        audit_bytes=audit,
        audit_sha256=_digest_bytes(audit),
        outbox_bytes=outbox,
        outbox_sha256=_digest_bytes(outbox),
    )


def build_rollback_result_v2(
    *,
    command: RollbackCommandV2,
    current: KnownPublicationSnapshotV2,
    target: KnownPublicationSnapshotV2,
    generation: int,
) -> PublicationCommandResultV2:
    if (
        type(command) is not RollbackCommandV2
        or type(current) is not KnownPublicationSnapshotV2
        or type(target) is not KnownPublicationSnapshotV2
    ):
        fail_publication_command()
    current.require_valid()
    target.require_valid()
    if (
        command.publication_id != current.publication_id
        or command.publication_id != target.publication_id
        or command.from_snapshot_id != current.snapshot_id
        or command.to_snapshot_id != target.snapshot_id
        or command.expected_from_source_binding_sha256 != current.source_binding_sha256
        or command.expected_to_source_binding_sha256 != target.source_binding_sha256
    ):
        fail_publication_command(PublicationCommandFailureCode.PUBLICATION_STATE_DRIFT)
    if (
        command.authorization.site_id
        != target.final_approval_result.record.site_id.value
    ):
        fail_publication_command(PublicationCommandFailureCode.SITE_SCOPE_MISMATCH)
    event_type = "jp.raos.publishing.article_rolled_back.v1"
    event = _event_envelope(
        command=command,
        event_type=event_type,
        dataschema=(
            "https://schemas.raos.local/events/"
            "jp-raos-publishing-article-rolled-back-v1.schema.json"
        ),
        generation=generation,
        data={
            "executed_at": _instant_text(command.occurred_at),
            "from_snapshot_id": str(current.snapshot_id),
            "publication_id": str(command.publication_id),
            "rollback_record_id": str(command.rollback_record_id),
            "to_snapshot_id": str(target.snapshot_id),
        },
    )
    audit = _audit_bytes(
        command=command,
        action="publication_rollback_local_simulated",
        generation=generation,
        from_snapshot_id=current.snapshot_id,
        to_snapshot_id=target.snapshot_id,
        approval_id=target.final_approval_result.record.approval_id.value,
    )
    outbox = _outbox_bytes(
        command=command,
        event_type=event_type,
        generation=generation,
        event_bytes=event,
    )
    return PublicationCommandResultV2(
        action=PublicationCommandAction.ROLLBACK,
        command_sha256=command.command_sha256,
        publication_id=command.publication_id,
        from_snapshot_id=current.snapshot_id,
        to_snapshot_id=target.snapshot_id,
        generation=generation,
        projection_bytes=target.projection_result.projection_bytes,
        projection_sha256=target.projection_result.projection_sha256,
        event_bytes=event,
        event_sha256=_digest_bytes(event),
        audit_bytes=audit,
        audit_sha256=_digest_bytes(audit),
        outbox_bytes=outbox,
        outbox_sha256=_digest_bytes(outbox),
    )


@dataclass(frozen=True, slots=True, repr=False)
class PublicationStoreSnapshotV2(_Redacted):
    state: PublicationLocalState
    generation: int
    current_snapshot_id: UUID | None
    current_source_binding_sha256: Sha256Digest | None
    current_projection_sha256: Sha256Digest | None
    idempotency_receipts: int
    projection_records: int
    event_intents: int
    audit_intents: int
    outbox_intents: int
    snapshot_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if type(self.state) is not PublicationLocalState:
            fail_publication_command()
        if type(self.generation) is not int or self.generation < 0:
            fail_publication_command()
        if self.current_snapshot_id is not None:
            _uuid7(self.current_snapshot_id)
        for value in (
            self.current_source_binding_sha256,
            self.current_projection_sha256,
        ):
            if value is not None:
                _sha(value)
        counts = (
            self.idempotency_receipts,
            self.projection_records,
            self.event_intents,
            self.audit_intents,
            self.outbox_intents,
        )
        if any(type(value) is not int or value < 0 for value in counts):
            fail_publication_command()
        if self.state is PublicationLocalState.UNPUBLISHED:
            if self.generation != 0 or any(
                value is not None
                for value in (
                    self.current_snapshot_id,
                    self.current_source_binding_sha256,
                    self.current_projection_sha256,
                )
            ):
                fail_publication_command()
        else:
            if self.generation < 1 or any(
                value is None
                for value in (
                    self.current_snapshot_id,
                    self.current_source_binding_sha256,
                    self.current_projection_sha256,
                )
            ):
                fail_publication_command()
        object.__setattr__(
            self,
            "snapshot_sha256",
            _digest(
                {
                    "audit_intents": self.audit_intents,
                    "current_projection_sha256": (
                        self.current_projection_sha256.value
                        if self.current_projection_sha256 is not None
                        else None
                    ),
                    "current_snapshot_id": str(self.current_snapshot_id)
                    if self.current_snapshot_id is not None
                    else None,
                    "current_source_binding_sha256": (
                        self.current_source_binding_sha256.value
                        if self.current_source_binding_sha256 is not None
                        else None
                    ),
                    "event_intents": self.event_intents,
                    "generation": self.generation,
                    "idempotency_receipts": self.idempotency_receipts,
                    "outbox_intents": self.outbox_intents,
                    "profile": PROFILE,
                    "projection_records": self.projection_records,
                    "state": self.state.value,
                }
            ),
        )


__all__ = (
    "ExternalGateStatus",
    "KnownPublicationSnapshotV2",
    "MAX_KNOWN_SNAPSHOTS",
    "PROFILE",
    "PublicationCommandAction",
    "PublicationCommandAuthorizationV2",
    "PublicationCommandExecution",
    "PublicationCommandFailure",
    "PublicationCommandFailureCode",
    "PublicationCommandResultV2",
    "PublicationCommandRole",
    "PublicationCommandSourcesV2",
    "PublicationKillSwitchSafeStateV2",
    "PublicationLocalState",
    "PublicationStoreSnapshotV2",
    "PublishCommandV2",
    "RollbackCommandV2",
    "UnpublishCommandV2",
    "build_publish_result_v2",
    "build_rollback_result_v2",
    "fail_publication_command",
)
