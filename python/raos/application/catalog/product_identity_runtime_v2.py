"""Authorization-first durable ST-0504 product identity application V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import final
from uuid import UUID

from raos.application.iam.authorization import DurableAuthorizationService
from raos.domain.catalog.product_identity_runtime_v2 import (
    PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2,
    PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2,
    PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2,
    PersistedProductIdentityDecisionV2,
    PersistedProductIdentityReviewQueueV2,
    PrepareProductIdentityReviewQueueCommandV2,
    ProductIdentityAuthorizationProofV2,
    ProductIdentityCommitRecoveryOutcomeV2,
    ProductIdentityDecisionCommandV2,
    ProductIdentityDecisionCommitRecoveryV2,
    ProductIdentityDecisionResultV2,
    ProductIdentityDecisionTypeV2,
    ProductIdentityHumanDecisionV2,
    ProductIdentityOutboxEventV2,
    ProductIdentityQueueCommitRecoveryV2,
    ProductIdentityReplayStatusV2,
    ProductIdentityReviewQueueV2,
    ProductIdentityReviewQueueResultV2,
    ProductIdentityRuntimeFailureCodeV2,
    ProductIdentityRuntimeFailureV2,
    build_product_identity_human_decision_v2,
    build_product_identity_review_queue_v2,
    fail_product_identity_runtime_v2,
    persisted_product_identity_decision_from_mapping_v2,
    persisted_product_identity_decision_mapping_v2,
    persisted_product_identity_review_queue_from_mapping_v2,
    persisted_product_identity_review_queue_mapping_v2,
    product_identity_authorization_proof_mapping_v2,
    product_identity_outbox_event_mapping_v2,
    product_identity_review_queue_mapping_v2,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    persisted_catalog_normalization_mapping_v2,
)
from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import (
    AuthorizationCommandResult,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    DecisionEffect,
    ResourceScopeKind,
    RuleId,
)
from raos.ports.product_identity_runtime_v2 import ProductIdentityUnitOfWorkStoreV2


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold != 0
    ):
        fail_product_identity_runtime_v2()
    return value


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except Exception:
        return False


def _exact_queue(
    value: object,
    *,
    failure_code: ProductIdentityRuntimeFailureCodeV2,
) -> PersistedProductIdentityReviewQueueV2:
    if type(value) is not PersistedProductIdentityReviewQueueV2:
        fail_product_identity_runtime_v2(failure_code)
    try:
        parsed = persisted_product_identity_review_queue_from_mapping_v2(
            persisted_product_identity_review_queue_mapping_v2(value)
        )
    except Exception:
        fail_product_identity_runtime_v2(failure_code)
    if parsed != value:
        fail_product_identity_runtime_v2(failure_code)
    return parsed


def _exact_decision(
    value: object,
    *,
    failure_code: ProductIdentityRuntimeFailureCodeV2,
) -> PersistedProductIdentityDecisionV2:
    if type(value) is not PersistedProductIdentityDecisionV2:
        fail_product_identity_runtime_v2(failure_code)
    try:
        parsed = persisted_product_identity_decision_from_mapping_v2(
            persisted_product_identity_decision_mapping_v2(value)
        )
    except Exception:
        fail_product_identity_runtime_v2(failure_code)
    if parsed != value:
        fail_product_identity_runtime_v2(failure_code)
    return parsed


def _authorization_audit_digest(result: AuthorizationCommandResult) -> str:
    audit = result.audit
    try:
        payload = json.dumps(
            {
                "schema": "ST0403_AUTHORIZATION_AUDIT_V1",
                "sequence": audit.sequence,
                "command_fingerprint": audit.command_fingerprint,
                "request_digest": audit.request_digest,
                "effect": audit.effect.value,
                "occurred_at": audit.occurred_at.isoformat(
                    timespec="microseconds"
                ).replace("+00:00", "Z"),
                "previous_digest": audit.previous_digest,
            },
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii")
    except Exception:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
        )
    return hashlib.sha256(payload).hexdigest()


def _authorization_command_material(
    command: AuthorizationEvaluationCommand,
) -> tuple[object, ...]:
    try:
        return (
            command.command_id.value,
            command.operation_id.value,
            command.target.canonical_key,
            command.correlation_id.value,
            command.expected_policy_revision.value,
            command.expected_entitlement_revision.value,
            command.observed_at.isoformat(timespec="microseconds"),
            None
            if command.step_up_command_id is None
            else command.step_up_command_id.fingerprint(),
            None
            if command.step_up_grant_id is None
            else command.step_up_grant_id.fingerprint(),
            None
            if command.independent_actor_evidence_id is None
            else command.independent_actor_evidence_id.hex,
        )
    except Exception:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
        )


def _authorization_result_material(
    result: AuthorizationCommandResult,
) -> tuple[object, ...]:
    try:
        decision = result.decision
        audit = result.audit
        return (
            result.command_id.value,
            result.command_id_fingerprint,
            result.request_digest,
            result.session_fingerprint,
            decision.canonical_key,
            audit.sequence,
            audit.command_fingerprint,
            audit.request_digest,
            audit.effect.value,
            audit.occurred_at.isoformat(timespec="microseconds"),
            audit.previous_digest,
            audit.digest,
            result.step_up_receipt_fingerprint,
        )
    except Exception:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
        )


def _canonical_material_hash(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except Exception:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return hashlib.sha256(payload).hexdigest()


def _queue_call_hash(
    command: PrepareProductIdentityReviewQueueCommandV2,
    queue: object,
    event: ProductIdentityOutboxEventV2,
) -> str:
    if type(queue) is not ProductIdentityReviewQueueV2:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
    return _canonical_material_hash(
        {
            "command": {
                "operation_id": str(command.operation_id),
                "site_id": str(command.site_id),
                "source": persisted_catalog_normalization_mapping_v2(command.source),
                "expected_history_version": command.expected_history_version,
                "prepared_at": command.prepared_at.isoformat(timespec="microseconds"),
                "payload_fingerprint": command.payload_fingerprint,
            },
            "queue": product_identity_review_queue_mapping_v2(queue),
            "event": product_identity_outbox_event_mapping_v2(event),
        }
    )


def _decision_call_hash(
    command: ProductIdentityDecisionCommandV2,
    decision: ProductIdentityHumanDecisionV2,
    event: ProductIdentityOutboxEventV2,
) -> str:
    return _canonical_material_hash(
        {
            "command": {
                "operation_id": str(command.operation_id),
                "queue_id": str(command.queue_id),
                "pair_id": str(command.pair_id),
                "decision_type": command.decision_type.value,
                "reason": command.reason,
                "reason_sha256": command.reason_sha256,
                "expected_history_version": command.expected_history_version,
                "supersedes_decision_id": None
                if command.supersedes_decision_id is None
                else str(command.supersedes_decision_id),
                "decided_at": command.decided_at.isoformat(timespec="microseconds"),
                "authorization": product_identity_authorization_proof_mapping_v2(
                    command.authorization
                ),
                "payload_fingerprint": command.payload_fingerprint,
            },
            "decision_sha256": decision.sha256,
            "event": product_identity_outbox_event_mapping_v2(event),
        }
    )


@dataclass(frozen=True, slots=True, repr=False)
class ProductIdentityHumanDecisionRequestV2:
    """One human intent plus an exact already-recorded ST-0403 decision."""

    operation_id: UUID
    persisted_queue: PersistedProductIdentityReviewQueueV2
    pair_id: UUID
    decision_type: ProductIdentityDecisionTypeV2
    reason: str
    expected_history_version: int
    supersedes_decision_id: UUID | None
    decided_at: datetime
    session_id: SessionId
    authorization_command: AuthorizationEvaluationCommand
    authorization_result: AuthorizationCommandResult
    authorization_checked_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.operation_id) is not UUID
            or self.operation_id.int == 0
            or type(self.persisted_queue) is not PersistedProductIdentityReviewQueueV2
            or type(self.pair_id) is not UUID
            or self.pair_id.int == 0
            or type(self.decision_type) is not ProductIdentityDecisionTypeV2
            or type(self.reason) is not str
            or not self.reason
            or self.reason != self.reason.strip()
            or type(self.expected_history_version) is not int
            or self.expected_history_version < 1
            or (
                self.supersedes_decision_id is not None
                and (
                    type(self.supersedes_decision_id) is not UUID
                    or self.supersedes_decision_id.int == 0
                )
            )
            or type(self.session_id) is not SessionId
            or type(self.authorization_command) is not AuthorizationEvaluationCommand
            or type(self.authorization_result) is not AuthorizationCommandResult
        ):
            fail_product_identity_runtime_v2()
        _utc(self.decided_at)
        checked = _utc(self.authorization_checked_at)
        if checked < self.authorization_command.observed_at:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_REQUIRED
            )


@final
class DurableProductIdentityRuntimeV2:
    """Create a generic queue and append authorized recorded decisions only."""

    __slots__ = ("_authorization", "_store")

    def __init__(
        self,
        *,
        authorization_service: DurableAuthorizationService,
        store: ProductIdentityUnitOfWorkStoreV2,
    ) -> None:
        if type(
            authorization_service
        ) is not DurableAuthorizationService or not _implements(
            store, ProductIdentityUnitOfWorkStoreV2
        ):
            fail_product_identity_runtime_v2()
        self._authorization = authorization_service
        self._store = store
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
        )

    @property
    def external_action_count(self) -> int:
        return 0

    def _require_store_idle(
        self, *, failure_code: ProductIdentityRuntimeFailureCodeV2
    ) -> None:
        try:
            count = self._store.action_count
        except Exception:
            fail_product_identity_runtime_v2(failure_code)
        if type(count) is not int or count != 0:
            fail_product_identity_runtime_v2(failure_code)

    def prepare_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> ProductIdentityReviewQueueResultV2:
        if type(command) is not PrepareProductIdentityReviewQueueCommandV2:
            fail_product_identity_runtime_v2()
        try:
            queue = build_product_identity_review_queue_v2(command)
            event = ProductIdentityOutboxEventV2.from_queue(queue)
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY
            )
        call_hash = _queue_call_hash(command, queue, event)
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        try:
            existing = self._store.lookup_review_queue(command)
        except ProductIdentityRuntimeFailureV2:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _queue_call_hash(command, queue, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            raise
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _queue_call_hash(command, queue, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        if existing is not None:
            exact = _exact_queue(
                existing,
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
            )
            if (
                exact.operation_id != command.operation_id
                or not hmac.compare_digest(
                    exact.payload_fingerprint, command.payload_fingerprint
                )
                or exact.queue != queue
                or exact.event != event
                or exact.history_version != 1
                or exact.committed_at != command.prepared_at
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                )
            return ProductIdentityReviewQueueResultV2(
                persisted=exact,
                replay_status=ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY,
                external_actions=0,
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        try:
            persisted = self._store.commit_review_queue(
                command=command,
                queue=queue,
                event=event,
            )
        except ProductIdentityRuntimeFailureV2 as error:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _queue_call_hash(command, queue, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            if error.code is not ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN:
                raise
            return self._recover_queue(command=command, queue=queue, event=event)
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _queue_call_hash(command, queue, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        exact = _exact_queue(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
        )
        if (
            exact.operation_id != command.operation_id
            or not hmac.compare_digest(
                exact.payload_fingerprint, command.payload_fingerprint
            )
            or exact.history_version != 1
            or exact.queue != queue
            or exact.event != event
            or exact.committed_at != command.prepared_at
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        return ProductIdentityReviewQueueResultV2(
            persisted=exact,
            replay_status=ProductIdentityReplayStatusV2.DIRECT_COMMIT,
            external_actions=0,
        )

    def _recover_queue(
        self,
        *,
        command: PrepareProductIdentityReviewQueueCommandV2,
        queue: object,
        event: ProductIdentityOutboxEventV2,
    ) -> ProductIdentityReviewQueueResultV2:
        call_hash = _queue_call_hash(command, queue, event)
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        try:
            recovered = self._store.recover_review_queue_commit(command)
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
            if _queue_call_hash(command, queue, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
        )
        if _queue_call_hash(command, queue, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        try:
            if (
                type(recovered) is not ProductIdentityQueueCommitRecoveryV2
                or recovered.outcome
                is not ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
                or recovered.persisted is None
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            persisted = recovered.persisted
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        exact = _exact_queue(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN,
        )
        if (
            exact.operation_id != command.operation_id
            or not hmac.compare_digest(
                exact.payload_fingerprint, command.payload_fingerprint
            )
            or exact.history_version != 1
            or exact.queue != queue
            or exact.event != event
            or exact.committed_at != command.prepared_at
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        return ProductIdentityReviewQueueResultV2(
            persisted=exact,
            replay_status=ProductIdentityReplayStatusV2.RECOVERED_COMMIT,
            external_actions=0,
        )

    def record_human_decision(
        self, request: ProductIdentityHumanDecisionRequestV2
    ) -> ProductIdentityDecisionResultV2:
        if type(request) is not ProductIdentityHumanDecisionRequestV2:
            fail_product_identity_runtime_v2()
        queue_record = _exact_queue(
            request.persisted_queue,
            failure_code=ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY,
        )
        proof = self._recover_authorization(request=request, queue=queue_record)
        command = ProductIdentityDecisionCommandV2.create(
            operation_id=request.operation_id,
            queue_id=queue_record.queue.queue_id,
            pair_id=request.pair_id,
            decision_type=request.decision_type,
            reason=request.reason,
            expected_history_version=request.expected_history_version,
            supersedes_decision_id=request.supersedes_decision_id,
            decided_at=request.decided_at,
            authorization=proof,
        )
        decision = build_product_identity_human_decision_v2(
            command=command,
            queue=queue_record.queue,
        )
        event = ProductIdentityOutboxEventV2.from_decision(
            decision=decision,
            queue=queue_record.queue,
        )
        call_hash = _decision_call_hash(command, decision, event)
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        try:
            existing = self._store.lookup_decision(command)
        except ProductIdentityRuntimeFailureV2:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            raise
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        if existing is not None:
            exact_existing = _exact_decision(
                existing,
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
            )
            if (
                exact_existing.operation_id != command.operation_id
                or not hmac.compare_digest(
                    exact_existing.payload_fingerprint, command.payload_fingerprint
                )
                or exact_existing.decision != decision
                or exact_existing.event != event
                or exact_existing.history_version != decision.history_version
                or exact_existing.committed_at != decision.decided_at
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                )
            return ProductIdentityDecisionResultV2(
                persisted=exact_existing,
                replay_status=ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY,
                external_actions=0,
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        try:
            persisted = self._store.commit_decision(
                command=command,
                decision=decision,
                event=event,
            )
        except ProductIdentityRuntimeFailureV2 as error:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            if error.code is not ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN:
                raise
            return self._recover_decision(
                command=command,
                decision=decision,
                event=event,
            )
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        exact = _exact_decision(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
        )
        if (
            exact.operation_id != command.operation_id
            or not hmac.compare_digest(
                exact.payload_fingerprint, command.payload_fingerprint
            )
            or exact.history_version != decision.history_version
            or exact.decision != decision
            or exact.event != event
            or exact.committed_at != decision.decided_at
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED
            )
        return ProductIdentityDecisionResultV2(
            persisted=exact,
            replay_status=ProductIdentityReplayStatusV2.DIRECT_COMMIT,
            external_actions=0,
        )

    def _recover_decision(
        self,
        *,
        command: ProductIdentityDecisionCommandV2,
        decision: ProductIdentityHumanDecisionV2,
        event: ProductIdentityOutboxEventV2,
    ) -> ProductIdentityDecisionResultV2:
        call_hash = _decision_call_hash(command, decision, event)
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        try:
            recovered = self._store.recover_decision_commit(command)
        except Exception:
            self._require_store_idle(
                failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        self._require_store_idle(
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
        )
        if _decision_call_hash(command, decision, event) != call_hash:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        try:
            if (
                type(recovered) is not ProductIdentityDecisionCommitRecoveryV2
                or recovered.outcome
                is not ProductIdentityCommitRecoveryOutcomeV2.COMMITTED
                or recovered.persisted is None
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            persisted = recovered.persisted
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            if _decision_call_hash(command, decision, event) != call_hash:
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        exact = _exact_decision(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN,
        )
        if (
            exact.operation_id != command.operation_id
            or not hmac.compare_digest(
                exact.payload_fingerprint, command.payload_fingerprint
            )
            or exact.history_version != decision.history_version
            or exact.decision != decision
            or exact.event != event
            or exact.committed_at != decision.decided_at
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        return ProductIdentityDecisionResultV2(
            persisted=exact,
            replay_status=ProductIdentityReplayStatusV2.RECOVERED_COMMIT,
            external_actions=0,
        )

    def _recover_authorization(
        self,
        *,
        request: ProductIdentityHumanDecisionRequestV2,
        queue: PersistedProductIdentityReviewQueueV2,
    ) -> ProductIdentityAuthorizationProofV2:
        command_material = _authorization_command_material(
            request.authorization_command
        )
        result_material = _authorization_result_material(request.authorization_result)
        queue_material = persisted_product_identity_review_queue_mapping_v2(queue)
        try:
            recovered = self._authorization.recover_admin(
                command_id=request.authorization_command.command_id,
                session_id=request.session_id,
                now=request.authorization_checked_at,
            )
        except Exception:
            if (
                _authorization_command_material(request.authorization_command)
                != command_material
                or _authorization_result_material(request.authorization_result)
                != result_material
                or persisted_product_identity_review_queue_mapping_v2(queue)
                != queue_material
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
                )
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
            )
        if (
            _authorization_command_material(request.authorization_command)
            != command_material
            or _authorization_result_material(request.authorization_result)
            != result_material
            or persisted_product_identity_review_queue_mapping_v2(queue)
            != queue_material
        ):
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
            )
        if type(recovered) is not AuthorizationCommandResult:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
            )
        try:
            exact = recovered
            command = request.authorization_command
            decision = exact.decision
            target = command.target
            recomputed = command.request_digest(
                session_fingerprint=exact.session_fingerprint
            )
            matched_rule_id = decision.matched_rule_id
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE
            )
        try:
            if (
                exact != request.authorization_result
                or exact.command_id != command.command_id
                or not hmac.compare_digest(recomputed, exact.request_digest)
                or command.operation_id.value
                != PRODUCT_IDENTITY_AUTHORIZATION_OPERATION_V2
                or decision.effect is not DecisionEffect.ALLOW
                or decision.reason is not AuthorizationDecisionReason.RULE_MATCH
                or decision.action.value != PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2
                or decision.target != target
                or target.scope.kind is not ResourceScopeKind.PRODUCT
                or target.scope.kind.value
                != PRODUCT_IDENTITY_AUTHORIZATION_RESOURCE_KIND_V2
                or target.scope.site_id != queue.queue.site_id
                or target.state is not None
                or type(matched_rule_id) is not RuleId
                or exact.audit.command_fingerprint != exact.command_id_fingerprint
                or exact.audit.request_digest != exact.request_digest
                or exact.audit.effect is not DecisionEffect.ALLOW
                or exact.audit.occurred_at != command.observed_at
                or not hmac.compare_digest(
                    exact.audit.digest, _authorization_audit_digest(exact)
                )
                or command.step_up_command_id is not None
                or command.step_up_grant_id is not None
                or command.independent_actor_evidence_id is not None
                or exact.step_up_receipt_fingerprint is not None
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH
                )
            proof = ProductIdentityAuthorizationProofV2(
                authorization_command_id=exact.command_id.value,
                authorization_command_id_fingerprint=exact.command_id_fingerprint,
                authorization_request_digest=exact.request_digest,
                authorization_session_fingerprint=exact.session_fingerprint,
                authorization_audit_sequence=exact.audit.sequence,
                authorization_audit_digest=exact.audit.digest,
                authorization_policy_revision=decision.policy_revision.value,
                authorization_policy_fingerprint=decision.policy_fingerprint,
                authorization_entitlement_revision=decision.entitlement_revision.value,
                authorization_matched_rule_id=matched_rule_id.value,
                authorization_checked_at=request.authorization_checked_at,
                operation_id=command.operation_id.value,
                action=decision.action.value,
                site_id=target.scope.site_id,
                resource_kind=target.scope.kind.value,
                resource_id=target.scope.resource_id,
                resource_state=None,
                step_up_receipt_fingerprint=None,
            )
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH
            )
        return proof


__all__ = [
    "DurableProductIdentityRuntimeV2",
    "ProductIdentityHumanDecisionRequestV2",
]
