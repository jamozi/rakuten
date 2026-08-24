"""Authorization-first durable ST-0504 product identity application V2."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
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

    @property
    def external_action_count(self) -> int:
        return 0

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
        try:
            existing = self._store.lookup_review_queue(command)
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
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
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                )
            return ProductIdentityReviewQueueResultV2(
                persisted=exact,
                replay_status=ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY,
                external_actions=0,
            )
        try:
            persisted = self._store.commit_review_queue(
                command=command,
                queue=queue,
                event=event,
            )
        except ProductIdentityRuntimeFailureV2 as error:
            if error.code is not ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN:
                raise
            return self._recover_queue(command=command, queue=queue, event=event)
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        exact = _exact_queue(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
        )
        if exact.queue != queue or exact.event != event:
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
        try:
            recovered = self._store.recover_review_queue_commit(command)
        except Exception:
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
        if exact.queue != queue or exact.event != event:
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
        try:
            existing = self._store.lookup_decision(command)
        except ProductIdentityRuntimeFailureV2:
            raise
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
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
            ):
                fail_product_identity_runtime_v2(
                    ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT
                )
            return ProductIdentityDecisionResultV2(
                persisted=exact_existing,
                replay_status=ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY,
                external_actions=0,
            )
        try:
            persisted = self._store.commit_decision(
                command=command,
                decision=decision,
                event=event,
            )
        except ProductIdentityRuntimeFailureV2 as error:
            if error.code is not ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN:
                raise
            return self._recover_decision(
                command=command,
                decision=decision,
                event=event,
            )
        except Exception:
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE
            )
        exact = _exact_decision(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
        )
        if exact.decision != decision or exact.event != event:
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
        try:
            recovered = self._store.recover_decision_commit(command)
        except Exception:
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
            fail_product_identity_runtime_v2(
                ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
            )
        exact = _exact_decision(
            persisted,
            failure_code=ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN,
        )
        if exact.decision != decision or exact.event != event:
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
        try:
            recovered = self._authorization.recover_admin(
                command_id=request.authorization_command.command_id,
                session_id=request.session_id,
                now=request.authorization_checked_at,
            )
        except Exception:
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
