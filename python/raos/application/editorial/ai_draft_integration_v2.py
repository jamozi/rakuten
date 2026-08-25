"""Receipt-consuming, effect-free application service for ST-0806 V2."""

from __future__ import annotations

from raos.domain.ai.durable_job_queue_v2 import (
    DurableQueueSnapshot,
    RecordedAttemptOutcome,
)
from raos.domain.editorial.ai_draft_integration_v2 import (
    AiDraftIntegrationRequestV2,
    AiDraftIntegrationResultV2,
    AiDraftV2Activation,
    AiDraftV2FailureCode,
    BoundContentAstV2,
    DraftAdoptionIntentV2,
    DraftArticleVersionProposalV2,
    DraftCoverageDecisionV2,
    DraftExecutionV2,
    DraftProposalDispositionV2,
    RecordedDraftMaterialV2,
    bind_coverage_v2,
    bind_durable_succeeded_completion_v2,
    build_content_ast_diff_v2,
    fail_ai_draft_v2,
)
from raos.domain.editorial.article_lifecycle import BodySha256, VersionSnapshot
from raos.ports.ai_draft_integration_v2 import RecordedAiDraftIntegrationPortV2


def _supports_port(candidate: object) -> bool:
    try:
        return isinstance(candidate, RecordedAiDraftIntegrationPortV2)
    except Exception:
        return False


def _normalize_version(candidate: object) -> VersionSnapshot | None:
    if type(candidate) is not VersionSnapshot:
        return None
    result: VersionSnapshot | None = None
    try:
        ast = BoundContentAstV2.from_content_ast(candidate.content_ast).content_ast()
        result = VersionSnapshot(
            version_id=candidate.version_id,
            display_id=candidate.display_id,
            article_id=candidate.article_id,
            version_no=candidate.version_no,
            article_type=candidate.article_type,
            title=candidate.title,
            source_packet_version_id=candidate.source_packet_version_id,
            source_packet_verification=candidate.source_packet_verification,
            based_on_version_id=candidate.based_on_version_id,
            content_ast=ast,
            body_sha256=BodySha256.of(ast),
            state=candidate.state,
            submitted_at=candidate.submitted_at,
            reviewed_at=candidate.reviewed_at,
            approved_at=candidate.approved_at,
            published_at=candidate.published_at,
            version=candidate.version,
            etag=candidate.etag,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        )
    except Exception:
        return None
    if result.body_sha256 != candidate.body_sha256:
        return None
    return result


def _normalize_request(candidate: object) -> AiDraftIntegrationRequestV2:
    if type(candidate) is not AiDraftIntegrationRequestV2:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    version = _normalize_version(candidate.source_version)
    if version is None:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    try:
        snapshot = DurableQueueSnapshot(
            queue_id=candidate.queue_snapshot.queue_id,
            revision=candidate.queue_snapshot.revision,
            state_bytes=bytes(candidate.queue_snapshot.state_bytes),
        )
        observed = candidate.recorded_outcome
        outcome = RecordedAttemptOutcome(
            kind=observed.kind,
            ai_job_id=observed.ai_job_id,
            attempt_number=observed.attempt_number,
            provider_request_id=observed.provider_request_id,
            actual_cost_jpy=observed.actual_cost_jpy,
            provider_failure_class=observed.provider_failure_class,
            validation_status=observed.validation_status,
            validation_failure_class=observed.validation_failure_class,
            retryable=observed.retryable,
            output_artifact_id=observed.output_artifact_id,
            output_artifact_sha256=observed.output_artifact_sha256,
        )
        result = AiDraftIntegrationRequestV2(
            environment=candidate.environment,
            operation_id=candidate.operation_id,
            queue_snapshot=snapshot,
            recorded_outcome=outcome,
            source_version=version,
            article_state=candidate.article_state,
            site_id=candidate.site_id,
            category_id=candidate.category_id,
        )
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    if (
        result.binding_sha256 != candidate.binding_sha256
        or snapshot.state_sha256 != candidate.queue_snapshot.state_sha256
        or outcome.fingerprint_sha256 != candidate.recorded_outcome.fingerprint_sha256
    ):
        fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
    return result


def _normalize_material(candidate: object) -> RecordedDraftMaterialV2:
    if type(candidate) is not RecordedDraftMaterialV2:
        fail_ai_draft_v2(AiDraftV2FailureCode.COLLABORATOR_FAILURE)
    try:
        return RecordedDraftMaterialV2(
            after_ast=BoundContentAstV2(bytes(candidate.after_ast.canonical_bytes)),
            coverage_snapshot=candidate.coverage_snapshot,
            coverage_report=candidate.coverage_report,
            coverage_receipt=candidate.coverage_receipt,
            fixture_sha256=candidate.fixture_sha256,
        )
    except Exception:
        fail_ai_draft_v2(AiDraftV2FailureCode.COLLABORATOR_FAILURE)


class AiDraftIntegrationServiceV2:
    """Create at most one human-editable proposal from exact recorded inputs."""

    __slots__ = ("_activation", "_port")

    def __init__(
        self,
        *,
        activation: AiDraftV2Activation,
        port: RecordedAiDraftIntegrationPortV2,
    ) -> None:
        if type(activation) is not AiDraftV2Activation:
            fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
        try:
            normalized = AiDraftV2Activation(
                environment=activation.environment,
                enabled=activation.enabled,
                policy_id=activation.policy_id,
                contract_sha256=activation.contract_sha256,
                policy_sha256=activation.policy_sha256,
            )
        except Exception:
            fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
        if normalized.fingerprint_sha256 != activation.fingerprint_sha256:
            fail_ai_draft_v2(AiDraftV2FailureCode.INVALID_REQUEST)
        if not _supports_port(port):
            raise TypeError("port must implement RecordedAiDraftIntegrationPortV2")
        self._activation = normalized
        self._port = port

    def integrate(
        self, *, request: AiDraftIntegrationRequestV2
    ) -> AiDraftIntegrationResultV2:
        normalized = _normalize_request(request)
        if not self._activation.enabled:
            fail_ai_draft_v2(AiDraftV2FailureCode.DISABLED)
        if normalized.environment is not self._activation.environment:
            fail_ai_draft_v2(AiDraftV2FailureCode.DEVELOPMENT_ONLY)

        durable = bind_durable_succeeded_completion_v2(normalized)
        observed: object = None
        try:
            observed = self._port.integrate(
                request_binding_sha256=normalized.binding_sha256
            )
        except Exception:
            fail_ai_draft_v2(AiDraftV2FailureCode.COLLABORATOR_FAILURE)
        material = _normalize_material(observed)
        before_ast = BoundContentAstV2.from_content_ast(
            normalized.source_version.content_ast
        )
        after_ast = material.after_ast
        after = after_ast.content_ast()
        if (
            after.article_id != str(normalized.source_version.article_id)
            or after.article_version_id != str(normalized.source_version.version_id)
            or after.article_type.value
            != normalized.source_version.content_ast.article_type.value
            or after.source_packet_version_ref
            != str(normalized.source_version.source_packet_version_id)
            or durable.article_version_id != normalized.source_version.version_id
            or durable.source_packet_version_id
            != normalized.source_version.source_packet_version_id
        ):
            fail_ai_draft_v2(AiDraftV2FailureCode.ARTIFACT_BINDING_MISMATCH)
        diff = build_content_ast_diff_v2(before_ast, after_ast)
        if not diff.changed:
            fail_ai_draft_v2(AiDraftV2FailureCode.DIFF_INVALID)
        decision, status, coverage, report_sha256, receipt_sequence = bind_coverage_v2(
            material=material,
            after_ast=after_ast,
        )

        proposal: DraftArticleVersionProposalV2 | None = None
        intent: DraftAdoptionIntentV2 | None = None
        if decision is DraftCoverageDecisionV2.AVAILABLE:
            assert coverage is not None
            proposal = DraftArticleVersionProposalV2(
                durable=durable,
                fixture_sha256=material.fixture_sha256,
                site_id=normalized.site_id,
                category_id=normalized.category_id,
                article_id=normalized.source_version.article_id,
                article_version_id=normalized.source_version.version_id,
                source_packet_version_id=normalized.source_version.source_packet_version_id,
                before_ast=before_ast,
                after_ast=after_ast,
                diff=diff,
                coverage=coverage,
                article_state=normalized.article_state,
                version_state=normalized.source_version.state,
                human_editable=True,
            )
            intent = DraftAdoptionIntentV2(
                proposal_sha256=proposal.proposal_sha256,
                expected_before_ast_sha256=before_ast.sha256,
                proposed_after_ast_sha256=after_ast.sha256,
                diff_sha256=diff.diff_sha256,
            )
        disposition = {
            DraftCoverageDecisionV2.AVAILABLE: DraftProposalDispositionV2.HUMAN_EDITABLE_PROPOSAL_ONLY,
            DraftCoverageDecisionV2.BLOCKED: DraftProposalDispositionV2.BLOCKED,
            DraftCoverageDecisionV2.UNAVAILABLE: DraftProposalDispositionV2.UNAVAILABLE,
        }[decision]
        return AiDraftIntegrationResultV2(
            request_binding_sha256=normalized.binding_sha256,
            durable_binding=durable,
            fixture_sha256=material.fixture_sha256,
            coverage_decision=decision,
            coverage_status=status,
            coverage_report_sha256=report_sha256,
            coverage_receipt_sequence=receipt_sequence,
            disposition=disposition,
            proposal=proposal,
            adoption_intent=intent,
            execution=DraftExecutionV2.RECORDED_ONLY,
            approval_permitted=False,
            apply_performed=False,
            merge_performed=False,
            persistence=DraftExecutionV2.NOT_EXECUTED,
            event_emission=DraftExecutionV2.NOT_EXECUTED,
            publication_permitted=False,
            recommendation_order_changed=False,
            formal_validation=DraftExecutionV2.NOT_EXECUTED,
            live_validation=DraftExecutionV2.NOT_EXECUTED,
            release=DraftExecutionV2.NOT_EXECUTED,
            production_eligible=False,
        )


__all__ = ["AiDraftIntegrationServiceV2"]
