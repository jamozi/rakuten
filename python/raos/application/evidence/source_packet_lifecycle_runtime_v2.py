"""Authorization-first application service for ST-0604 Source Packets."""

from __future__ import annotations

import hmac
from typing import final
from uuid import UUID
from datetime import datetime

from raos.application.iam.authorization import DurableAuthorizationService
from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    RecordedSourcePacketAuthorizationV2,
    SourcePacketCommandIdV2,
    SourcePacketCommandKindV2,
    SourcePacketCommandResultV2,
    SourcePacketCommandV2,
    SourcePacketContentV2,
    SourcePacketFailureCodeV2,
    SourcePacketFailureV2,
    SourcePacketReviewDecisionV2,
    fail_source_packet_v2,
)
from raos.domain.iam.authentication import SessionId
from raos.domain.iam.authorization import (
    ActionCode,
    AuthorizationCommandResult,
    AuthorizationDecisionReason,
    AuthorizationEvaluationCommand,
    DecisionEffect,
    OperationId,
    ResourceScopeKind,
    ResourceState,
)
from raos.ports.source_packet_lifecycle_runtime_v2 import (
    SourcePacketLifecycleStoreV2,
)


_OPERATION = OperationId("PUBADM-004")
_ACTION = ActionCode("review_article")
_STATE = ResourceState("IN_PROGRESS")


def _implements(value: object, protocol: type[object]) -> bool:
    try:
        return isinstance(value, protocol)
    except TypeError:
        return False


@final
class DurableSourcePacketLifecycleServiceV2:
    """Run deterministic local lifecycle commands with no external actions."""

    __slots__ = ("_authorization", "_store")

    def __init__(
        self,
        *,
        authorization_service: DurableAuthorizationService,
        store: SourcePacketLifecycleStoreV2,
    ) -> None:
        if type(
            authorization_service
        ) is not DurableAuthorizationService or not _implements(
            store, SourcePacketLifecycleStoreV2
        ):
            fail_source_packet_v2()
        self._authorization = authorization_service
        self._store = store
        self._require_idle()

    @property
    def external_action_count(self) -> int:
        return 0

    @property
    def provider_action_count(self) -> int:
        return 0

    @property
    def publication_action_count(self) -> int:
        return 0

    @property
    def ai_action_count(self) -> int:
        return 0

    def _require_idle(self) -> None:
        try:
            count = self._store.action_count
        except Exception:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        if type(count) is not int or count != 0:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)

    def _execute(self, command: SourcePacketCommandV2) -> SourcePacketCommandResultV2:
        self._require_idle()
        try:
            result = self._store.execute(command)
        except SourcePacketFailureV2 as error:
            if error.code is not SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN:
                raise
            try:
                result = self._store.recover(
                    command_id=command.command_id,
                    request_sha256=command.request_sha256,
                )
            except Exception:
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
        except Exception:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        if (
            type(result) is not SourcePacketCommandResultV2
            or result.command != command
            or not hmac.compare_digest(
                result.command.request_sha256, command.request_sha256
            )
            or result.state.packet_id != command.packet_id
            or any(
                value != 0
                for value in (
                    result.external_action_count,
                    result.provider_action_count,
                    result.publication_action_count,
                    result.ai_action_count,
                )
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        self._require_idle()
        return result

    def create_packet(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        site_id: UUID,
        article_plan_id: UUID,
        review_assignment_id: UUID,
        creator_actor_fingerprint: str,
        occurred_at: datetime,
    ) -> SourcePacketCommandResultV2:
        return self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.CREATE_PACKET,
                packet_id=packet_id,
                expected_revision=0,
                occurred_at=occurred_at,
                actor_fingerprint=creator_actor_fingerprint,
                site_id=site_id,
                article_plan_id=article_plan_id,
                review_assignment_id=review_assignment_id,
            )
        )

    def create_version(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        expected_revision: int,
        editor_actor_fingerprint: str,
        content: SourcePacketContentV2,
        occurred_at: datetime,
    ) -> SourcePacketCommandResultV2:
        return self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.CREATE_VERSION,
                packet_id=packet_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                actor_fingerprint=editor_actor_fingerprint,
                content=content,
            )
        )

    def submit_review(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        expected_revision: int,
        editor_actor_fingerprint: str,
        occurred_at: datetime,
    ) -> SourcePacketCommandResultV2:
        return self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.SUBMIT_REVIEW,
                packet_id=packet_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                actor_fingerprint=editor_actor_fingerprint,
            )
        )

    def _recorded_authorization(
        self,
        *,
        site_id: UUID,
        review_assignment_id: UUID,
        session_id: SessionId,
        command: AuthorizationEvaluationCommand,
        supplied: AuthorizationCommandResult,
        checked_at: datetime,
    ) -> RecordedSourcePacketAuthorizationV2:
        if (
            type(session_id) is not SessionId
            or type(command) is not AuthorizationEvaluationCommand
            or type(supplied) is not AuthorizationCommandResult
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        try:
            recovered = self._authorization.recover_admin(
                command_id=command.command_id,
                session_id=session_id,
                now=checked_at,
            )
            request_digest = command.request_digest(
                session_fingerprint=recovered.session_fingerprint
            )
        except Exception:
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        if type(recovered) is not AuthorizationCommandResult:
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        decision = recovered.decision
        target = command.target
        if (
            recovered != supplied
            or recovered.command_id != command.command_id
            or not hmac.compare_digest(request_digest, recovered.request_digest)
            or command.operation_id != _OPERATION
            or decision.effect is not DecisionEffect.ALLOW
            or decision.reason is not AuthorizationDecisionReason.RULE_MATCH
            or decision.action != _ACTION
            or decision.target != target
            or target.scope.kind is not ResourceScopeKind.REVIEW_ASSIGNMENT
            or target.state != _STATE
            or target.scope.site_id != site_id
            or target.scope.resource_id != review_assignment_id
            or recovered.step_up_receipt_fingerprint is not None
            or decision.matched_rule_id is None
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED)
        return RecordedSourcePacketAuthorizationV2(
            authorization_command_id=command.command_id.value,
            operation_id=command.operation_id.value,
            request_digest=recovered.request_digest,
            session_fingerprint=recovered.session_fingerprint,
            audit_sequence=recovered.audit.sequence,
            audit_digest=recovered.audit.digest,
            policy_revision=decision.policy_revision.value,
            policy_fingerprint=decision.policy_fingerprint,
            entitlement_revision=decision.entitlement_revision.value,
            matched_rule_id=decision.matched_rule_id.value,
            site_id=site_id,
            review_assignment_id=review_assignment_id,
            observed_at=command.observed_at,
            checked_at=checked_at,
        )

    def record_review(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        expected_revision: int,
        decision: SourcePacketReviewDecisionV2,
        site_id: UUID,
        review_assignment_id: UUID,
        session_id: SessionId,
        authorization_command: AuthorizationEvaluationCommand,
        authorization_result: AuthorizationCommandResult,
        authorization_checked_at: datetime,
    ) -> SourcePacketCommandResultV2:
        authorization = self._recorded_authorization(
            site_id=site_id,
            review_assignment_id=review_assignment_id,
            session_id=session_id,
            command=authorization_command,
            supplied=authorization_result,
            checked_at=authorization_checked_at,
        )
        return self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.RECORD_REVIEW,
                packet_id=packet_id,
                expected_revision=expected_revision,
                occurred_at=authorization_checked_at,
                actor_fingerprint=authorization.session_fingerprint,
                review_decision=decision,
                authorization=authorization,
            )
        )

    def lock_version(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        expected_revision: int,
        actor_fingerprint: str,
        occurred_at: datetime,
    ) -> SourcePacketCommandResultV2:
        return self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.LOCK_VERSION,
                packet_id=packet_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                actor_fingerprint=actor_fingerprint,
            )
        )

    def read_generation_input(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        packet_id: UUID,
        expected_revision: int,
        actor_fingerprint: str,
        occurred_at: datetime,
    ) -> SourcePacketCommandResultV2:
        result = self._execute(
            SourcePacketCommandV2(
                command_id=command_id,
                kind=SourcePacketCommandKindV2.READ_GENERATION_INPUT,
                packet_id=packet_id,
                expected_revision=expected_revision,
                occurred_at=occurred_at,
                actor_fingerprint=actor_fingerprint,
            )
        )
        if result.generation_input is None:
            fail_source_packet_v2(SourcePacketFailureCodeV2.NOT_GENERATION_READY)
        return result


__all__ = ["DurableSourcePacketLifecycleServiceV2"]
