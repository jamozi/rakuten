"""Authorization-first durable audit writer and fail-closed query boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, cast
from uuid import UUID

from raos.application.iam.authorization import DurableAuthorizationService
from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import (
    AuthorizationCommandId,
    AuthorizationCommandResult,
    AuthorizationGrant,
    DecisionEffect,
    MatrixAction,
    ResourceScopeKind,
    snapshot_authorization_result,
)
from raos.domain.ops.audit import (
    AuditActor,
    AuditContext,
    AuditEvent,
    AuditEventId,
    AuditOutcome,
    AuditReasonCode,
    AuditRequestId,
    AuditSeverity,
)
from raos.domain.ops.audit_runtime_v2 import (
    AUDIT_QUERY_BLOCK_REASON_V2,
    AuditAppendReceiptV2,
    AuditAuthorizationProofV2,
    AuditEventCandidateV2,
    AuditRuntimeFailureCodeV2,
    AuditRuntimeFailureV2,
    PersistedAuditEventV2,
    audit_request_sha256_v2,
    fail_audit_runtime_v2,
    snapshot_audit_append_receipt_v2,
    snapshot_audit_authorization_proof_v2,
    snapshot_audit_candidate_v2,
    snapshot_persisted_audit_event_v2,
)
from raos.ports.audit_runtime_v2 import (
    AuditRuntimeContextSourceV2,
    AuditRuntimeStoreFactoryV2,
    AuditRuntimeStoreV2,
)


@dataclass(frozen=True, slots=True, repr=False)
class DurableAuditRequestV2:
    authorization_command_id: AuthorizationCommandId
    session_id: SessionId
    now: datetime
    outcome: AuditOutcome
    severity: AuditSeverity
    reason_code: AuditReasonCode
    before_hash: str | None = None
    after_hash: str | None = None

    def __post_init__(self) -> None:
        if (
            type(self.authorization_command_id) is not AuthorizationCommandId
            or type(self.session_id) is not SessionId
            or type(self.now) is not datetime
            or self.now.tzinfo is not timezone.utc
            or self.now.fold != 0
            or type(self.outcome) is not AuditOutcome
            or type(self.severity) is not AuditSeverity
            or type(self.reason_code) is not AuditReasonCode
            or (self.before_hash is not None and type(self.before_hash) is not str)
            or (self.after_hash is not None and type(self.after_hash) is not str)
        ):
            fail_audit_runtime_v2()

    def __repr__(self) -> str:
        return "DurableAuditRequestV2(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class DurableAuditCommitV2:
    record: PersistedAuditEventV2
    receipt: AuditAppendReceiptV2
    recovered_after_commit_ambiguity: bool

    def __post_init__(self) -> None:
        if (
            type(self.record) is not PersistedAuditEventV2
            or type(self.receipt) is not AuditAppendReceiptV2
            or type(self.recovered_after_commit_ambiguity) is not bool
            or self.record.candidate.event_id != self.receipt.event_id
            or self.record.candidate.request_sha256 != self.receipt.request_sha256
            or self.record.sequence != self.receipt.sequence
            or self.record.previous_entry_sha256 != self.receipt.previous_entry_sha256
            or self.record.entry_sha256 != self.receipt.entry_sha256
        ):
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    def __repr__(self) -> str:
        return "DurableAuditCommitV2(<redacted>)"


def _authorization_proof(
    result: object,
    *,
    expected_command_id: AuthorizationCommandId,
) -> tuple[AuthorizationCommandResult, AuditAuthorizationProofV2]:
    if type(result) is not AuthorizationCommandResult:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
    try:
        exact = snapshot_authorization_result(result)
    except Exception:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
    try:
        if (
            exact.command_id != expected_command_id
            or exact.decision.effect is not DecisionEffect.ALLOW
            or exact.decision.action.value != MatrixAction.EDIT_ARTICLE_DRAFT.value
            or exact.decision.target.scope.kind is not ResourceScopeKind.ARTICLE_VERSION
            or exact.decision.target.state is None
            or exact.decision.target.state.value != "DRAFT"
            or exact.audit.command_fingerprint != exact.command_id_fingerprint
            or exact.audit.request_digest != exact.request_digest
            or exact.audit.effect is not DecisionEffect.ALLOW
        ):
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
        proof = AuditAuthorizationProofV2(
            command_id_fingerprint=exact.command_id_fingerprint,
            request_digest=exact.request_digest,
            session_fingerprint=exact.session_fingerprint,
            authorization_audit_digest=exact.audit.digest,
        )
    except AuditRuntimeFailureV2:
        raise
    except Exception:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
    return exact, proof


class _ExternalActionCounter(Protocol):
    @property
    def external_action_count(self) -> int: ...


def _require_zero_external_actions(value: object) -> None:
    """Reject mutable, boolean, nonzero, or unavailable authority counters."""

    try:
        counter = cast(_ExternalActionCounter, value)
        first: object = counter.external_action_count
        second: object = counter.external_action_count
    except Exception:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if type(first) is not int or first != 0 or type(second) is not int or second != 0:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)


def _context_material(value: AuditContext) -> tuple[object, ...]:
    try:
        return (
            value.event_id.value,
            value.actor.actor_type,
            value.actor.actor_id,
            value.occurred_at,
            None if value.request_id is None else value.request_id.value,
            value.action.value,
            value.target_type.value,
            value.target_id,
            value.correlation_id,
        )
    except Exception:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)


def _snapshot_context(value: object, *, grant: AuthorizationGrant) -> AuditContext:
    if type(value) is not AuditContext:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    try:
        before = _context_material(value)
        snapshot = AuditContext(
            grant=grant,
            event_id=AuditEventId(UUID(str(value.event_id.value))),
            actor=AuditActor(
                actor_type=value.actor.actor_type,
                actor_id=(
                    None
                    if value.actor.actor_id is None
                    else UUID(str(value.actor.actor_id))
                ),
            ),
            occurred_at=value.occurred_at.replace(),
            request_id=(
                None
                if value.request_id is None
                else AuditRequestId(value.request_id.value)
            ),
        )
        snapshot.require_bound_to(grant)
        after = _context_material(value)
    except AuditRuntimeFailureV2:
        raise
    except Exception:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    if before != after or _context_material(snapshot) != before:
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    return snapshot


def _issue_context(
    source: AuditRuntimeContextSourceV2, *, grant: AuthorizationGrant
) -> AuditContext:
    _require_zero_external_actions(source)
    try:
        issued = source.issue(grant)
    except Exception:
        _require_zero_external_actions(source)
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
    _require_zero_external_actions(source)
    return _snapshot_context(issued, grant=grant)


def _same_authorization(
    record: PersistedAuditEventV2, proof: AuditAuthorizationProofV2
) -> bool:
    candidate = record.candidate
    return type(candidate) is AuditEventCandidateV2 and candidate.authorization == proof


class DurableAuditWriterV2:
    """Recover one exact ST-0403 result before opening the audit store."""

    __slots__ = ("_authorization", "_context_source", "_store_factory")

    def __init__(
        self,
        *,
        authorization: DurableAuthorizationService,
        context_source: AuditRuntimeContextSourceV2,
        store_factory: AuditRuntimeStoreFactoryV2,
    ) -> None:
        if type(authorization) is not DurableAuthorizationService:
            raise TypeError("authorization must be the exact durable service")
        try:
            valid_context = isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                context_source, AuditRuntimeContextSourceV2
            )
            valid_store = isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                store_factory, AuditRuntimeStoreFactoryV2
            )
        except Exception:
            valid_context = False
            valid_store = False
        if not valid_context or not valid_store:
            raise TypeError("invalid durable audit collaborator")
        self._authorization = authorization
        self._context_source = context_source
        self._store_factory = store_factory

    @property
    def external_action_count(self) -> int:
        return 0

    def record(self, request: DurableAuditRequestV2) -> DurableAuditCommitV2:
        if type(request) is not DurableAuditRequestV2:
            fail_audit_runtime_v2()
        try:
            authorization_result = self._authorization.recover_admin(
                command_id=request.authorization_command_id,
                session_id=request.session_id,
                now=request.now,
            )
        except Exception:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.AUTHORIZATION_DENIED)
        result, proof = _authorization_proof(
            authorization_result,
            expected_command_id=request.authorization_command_id,
        )
        request_sha256 = audit_request_sha256_v2(
            authorization=proof,
            outcome=request.outcome.value,
            severity=request.severity.value,
            reason_code=request.reason_code.value,
            before_hash=request.before_hash,
            after_hash=request.after_hash,
        )
        store = self._open_store()
        existing = self._lookup(store, proof)
        if existing is not None:
            if (
                not _same_authorization(existing, proof)
                or existing.candidate.request_sha256 != request_sha256
            ):
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
            return self._commit_from_record(existing, replayed=True, recovered=False)

        try:
            grant = result.grant()
            context = _issue_context(self._context_source, grant=grant)
            event = AuditEvent(
                grant=grant,
                context=context,
                outcome=request.outcome,
                severity=request.severity,
                reason_code=request.reason_code,
                before_hash=request.before_hash,
                after_hash=request.after_hash,
            )
            candidate = snapshot_audit_candidate_v2(
                AuditEventCandidateV2.from_event(
                    authorization=proof,
                    request_sha256=request_sha256,
                    event=event,
                )
            )
        except AuditRuntimeFailureV2:
            raise
        except Exception:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

        recovered = False
        try:
            receipt = self._append_atomic(store, candidate)
        except AuditRuntimeFailureV2 as error:
            if error.code is not AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN:
                raise
            try:
                receipt = self._recover_exact(store, candidate)
            except AuditRuntimeFailureV2 as recovery_error:
                if recovery_error.code is AuditRuntimeFailureCodeV2.RECOVERY_NOT_FOUND:
                    fail_audit_runtime_v2(
                        AuditRuntimeFailureCodeV2.STORAGE_COMMIT_UNKNOWN
                    )
                raise
            recovered = True
        except Exception:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        receipt = snapshot_audit_append_receipt_v2(receipt)
        persisted = self._load_exact(store, candidate.event_id)
        if persisted is None or persisted.candidate != candidate:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        self._validate_receipt(persisted, receipt)
        self._verify_chain(store, persisted)
        return DurableAuditCommitV2(
            record=persisted,
            receipt=receipt,
            recovered_after_commit_ambiguity=recovered,
        )

    def _open_store(self) -> AuditRuntimeStoreV2:
        _require_zero_external_actions(self._store_factory)
        try:
            store = self._store_factory.open()
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(self._store_factory)
            raise
        except Exception:
            _require_zero_external_actions(self._store_factory)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        _require_zero_external_actions(self._store_factory)
        try:
            if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
                store, AuditRuntimeStoreV2
            ):
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
            _require_zero_external_actions(store)
            return store
        except AuditRuntimeFailureV2:
            raise
        except Exception:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    @staticmethod
    def _lookup(
        store: AuditRuntimeStoreV2, proof: AuditAuthorizationProofV2
    ) -> PersistedAuditEventV2 | None:
        detached = snapshot_audit_authorization_proof_v2(proof)
        try:
            _require_zero_external_actions(store)
            record = store.lookup_authorization(detached)
            _require_zero_external_actions(store)
            if snapshot_audit_authorization_proof_v2(detached) != proof:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(store)
            if snapshot_audit_authorization_proof_v2(detached) != proof:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            raise
        except Exception:
            _require_zero_external_actions(store)
            if snapshot_audit_authorization_proof_v2(detached) != proof:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if record is None:
            return None
        return snapshot_persisted_audit_event_v2(record)

    @staticmethod
    def _load_exact(
        store: AuditRuntimeStoreV2, event_id: UUID
    ) -> PersistedAuditEventV2 | None:
        exact_event_id = UUID(str(event_id))
        try:
            _require_zero_external_actions(store)
            record = store.load_exact(exact_event_id)
            _require_zero_external_actions(store)
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(store)
            raise
        except Exception:
            _require_zero_external_actions(store)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if record is None:
            return None
        return snapshot_persisted_audit_event_v2(record)

    @staticmethod
    def _append_atomic(
        store: AuditRuntimeStoreV2, candidate: AuditEventCandidateV2
    ) -> AuditAppendReceiptV2:
        detached = snapshot_audit_candidate_v2(candidate)
        try:
            _require_zero_external_actions(store)
            receipt = store.append_atomic(detached)
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            return snapshot_audit_append_receipt_v2(receipt)
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            raise
        except Exception:
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    @staticmethod
    def _recover_exact(
        store: AuditRuntimeStoreV2, candidate: AuditEventCandidateV2
    ) -> AuditAppendReceiptV2:
        detached = snapshot_audit_candidate_v2(candidate)
        try:
            _require_zero_external_actions(store)
            receipt = store.recover_exact(detached)
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            return snapshot_audit_append_receipt_v2(receipt)
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            raise
        except Exception:
            _require_zero_external_actions(store)
            if snapshot_audit_candidate_v2(detached) != candidate:
                fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)

    @staticmethod
    def _validate_receipt(
        record: PersistedAuditEventV2, receipt: AuditAppendReceiptV2
    ) -> None:
        if (
            receipt.event_id != record.candidate.event_id
            or receipt.request_sha256 != record.candidate.request_sha256
            or receipt.sequence != record.sequence
            or receipt.previous_entry_sha256 != record.previous_entry_sha256
            or receipt.entry_sha256 != record.entry_sha256
        ):
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)

    @classmethod
    def _commit_from_record(
        cls,
        record: PersistedAuditEventV2,
        *,
        replayed: bool,
        recovered: bool,
    ) -> DurableAuditCommitV2:
        record = snapshot_persisted_audit_event_v2(record)
        receipt = AuditAppendReceiptV2(
            event_id=record.candidate.event_id,
            request_sha256=record.candidate.request_sha256,
            sequence=record.sequence,
            previous_entry_sha256=record.previous_entry_sha256,
            entry_sha256=record.entry_sha256,
            replayed=replayed,
        )
        return DurableAuditCommitV2(
            record=record,
            receipt=receipt,
            recovered_after_commit_ambiguity=recovered,
        )

    @staticmethod
    def _verify_chain(
        store: AuditRuntimeStoreV2, record: PersistedAuditEventV2
    ) -> None:
        try:
            _require_zero_external_actions(store)
            tail, count = store.verify_chain()
            _require_zero_external_actions(store)
        except AuditRuntimeFailureV2:
            _require_zero_external_actions(store)
            raise
        except Exception:
            _require_zero_external_actions(store)
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.STORE_UNAVAILABLE)
        if type(tail) is not str or type(count) is not int or count < record.sequence:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)
        if count == record.sequence and tail != record.entry_sha256:
            fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.TAMPER_DETECTED)


class DisabledAuditQueryServiceV2:
    """Outward query remains unavailable while OPS-012 is canonically blocked."""

    __slots__ = ("_store_factory",)

    def __init__(self, *, store_factory: AuditRuntimeStoreFactoryV2) -> None:
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            store_factory, AuditRuntimeStoreFactoryV2
        ):
            raise TypeError("invalid audit store factory")
        self._store_factory = store_factory

    @property
    def external_action_count(self) -> int:
        return 0

    @property
    def block_reason(self) -> str:
        return AUDIT_QUERY_BLOCK_REASON_V2

    def query(
        self, correlation_id: object, *, limit: object
    ) -> tuple[PersistedAuditEventV2, ...]:
        del correlation_id, limit
        fail_audit_runtime_v2(AuditRuntimeFailureCodeV2.QUERY_AUTHORIZATION_UNAVAILABLE)


__all__ = [
    "DisabledAuditQueryServiceV2",
    "DurableAuditCommitV2",
    "DurableAuditRequestV2",
    "DurableAuditWriterV2",
]
