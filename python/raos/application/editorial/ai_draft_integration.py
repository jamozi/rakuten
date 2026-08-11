"""One-call application service for recorded human-editable AI drafts."""

from __future__ import annotations

from raos.domain.ai.job_orchestration import AiJobResult
from raos.domain.editorial.ai_draft_integration import (
    AiDraftDisposition,
    AiDraftEnvironment,
    AiDraftIntegrationFailureCode,
    AiDraftIntegrationRequest,
    AiDraftIntegrationResult,
    ClaimFactReference,
    CoverageStatus,
    ExecutionStatus,
    MinimalDraftDiff,
    RecordedDraftCandidate,
    fail_ai_draft_integration,
)
from raos.domain.editorial.article_lifecycle import VersionSnapshot
from raos.ports.ai_draft_integration import RecordedAiDraftIntegrationPort


def _supports_port(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, RecordedAiDraftIntegrationPort)
    except Exception:
        pass
    return supported


def _normalize_job(candidate: object) -> AiJobResult | None:
    normalized: AiJobResult | None = None
    failed = False
    if type(candidate) is AiJobResult:
        try:
            normalized = AiJobResult(
                operation_id=candidate.operation_id,
                command_fingerprint_sha256=candidate.command_fingerprint_sha256,
                ai_job_id=candidate.ai_job_id,
                ops_job_id=candidate.ops_job_id,
                task_code=candidate.task_code,
                attempt_number=candidate.attempt_number,
                disposition=candidate.disposition,
                failure_code=candidate.failure_code,
                retryable=candidate.retryable,
                actual_cost_jpy=candidate.actual_cost_jpy,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                provider_request_id=candidate.provider_request_id,
                validation_status=candidate.validation_status,
                budget_receipt=candidate.budget_receipt,
            )
        except Exception:
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_version(candidate: object) -> VersionSnapshot | None:
    normalized: VersionSnapshot | None = None
    failed = False
    if type(candidate) is VersionSnapshot:
        try:
            normalized = VersionSnapshot(
                version_id=candidate.version_id,
                display_id=candidate.display_id,
                article_id=candidate.article_id,
                version_no=candidate.version_no,
                article_type=candidate.article_type,
                title=candidate.title,
                source_packet_version_id=candidate.source_packet_version_id,
                source_packet_verification=candidate.source_packet_verification,
                based_on_version_id=candidate.based_on_version_id,
                content_ast=candidate.content_ast,
                body_sha256=candidate.body_sha256,
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
            failed = True
    if failed or normalized != candidate:
        return None
    return normalized


def _normalize_request(candidate: object) -> AiDraftIntegrationRequest:
    normalized: AiDraftIntegrationRequest | None = None
    failed = False
    if type(candidate) is AiDraftIntegrationRequest:
        job = _normalize_job(candidate.ai_job_result)
        version = _normalize_version(candidate.source_version)
        if job is not None and version is not None:
            try:
                normalized = AiDraftIntegrationRequest(
                    environment=candidate.environment,
                    operation_id=candidate.operation_id,
                    ai_job_result=job,
                    source_version=version,
                    article_state=candidate.article_state,
                    site_id=candidate.site_id,
                    category_id=candidate.category_id,
                )
            except Exception:
                failed = True
    if failed or normalized is None or normalized != candidate:
        fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_candidate(candidate: object) -> RecordedDraftCandidate:
    normalized: RecordedDraftCandidate | None = None
    failed = False
    if type(candidate) is RecordedDraftCandidate:
        try:
            diff = MinimalDraftDiff(
                before_body_sha256=candidate.diff.before_body_sha256,
                after_body_sha256=candidate.diff.after_body_sha256,
                changed=candidate.diff.changed,
                changed_block_ids=tuple(candidate.diff.changed_block_ids),
            )
            references = tuple(
                ClaimFactReference(
                    ordinal=item.ordinal,
                    claim_id=item.claim_id,
                    fact_id=item.fact_id,
                    source_packet_version_id=item.source_packet_version_id,
                )
                for item in candidate.claim_fact_references
            )
            normalized = RecordedDraftCandidate(
                ai_job_id=candidate.ai_job_id,
                task_code=candidate.task_code,
                validation_status=candidate.validation_status,
                output_artifact_id=candidate.output_artifact_id,
                output_artifact_sha256=candidate.output_artifact_sha256,
                source_packet_version_id=candidate.source_packet_version_id,
                article_id=candidate.article_id,
                article_version_id=candidate.article_version_id,
                site_id=candidate.site_id,
                category_id=candidate.category_id,
                body_sha256=candidate.body_sha256,
                content_ast=candidate.content_ast,
                diff=diff,
                claim_fact_references=references,
            )
        except Exception:
            failed = True
    if failed or normalized is None or normalized != candidate:
        fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
    return normalized


class AiDraftIntegrationService:
    """Bind one successful job to one unapplied, human-editable candidate."""

    __slots__ = ("_environment", "_port")

    def __init__(
        self,
        *,
        environment: AiDraftEnvironment,
        port: RecordedAiDraftIntegrationPort,
    ) -> None:
        if type(environment) is not AiDraftEnvironment:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.DEVELOPMENT_ONLY)
        if not _supports_port(port):
            raise TypeError("port must implement RecordedAiDraftIntegrationPort")
        self._environment = environment
        self._port = port

    def integrate(
        self, *, request: AiDraftIntegrationRequest
    ) -> AiDraftIntegrationResult:
        normalized_request = _normalize_request(request)
        if normalized_request.environment is not self._environment:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.DEVELOPMENT_ONLY)

        observed: object = None
        collaborator_failed = False
        try:
            observed = self._port.integrate(request=normalized_request)
        except Exception:
            collaborator_failed = True
        if collaborator_failed:
            fail_ai_draft_integration(
                AiDraftIntegrationFailureCode.COLLABORATOR_FAILURE
            )
        candidate = _normalize_candidate(observed)
        return AiDraftIntegrationResult(
            request=normalized_request,
            candidate=candidate,
            disposition=AiDraftDisposition.HUMAN_EDITABLE_RECORDED_ONLY,
            article_state=normalized_request.article_state,
            version_state=normalized_request.source_version.state,
            coverage_status=CoverageStatus.UNEVALUABLE,
            execution=ExecutionStatus.RECORDED_ONLY,
            approval_permitted=False,
            publication_permitted=False,
            merge_performed=False,
            apply_performed=False,
            persistence=ExecutionStatus.NOT_EXECUTED,
            event_emission=ExecutionStatus.NOT_EXECUTED,
            release=ExecutionStatus.NOT_EXECUTED,
            formal_validation=ExecutionStatus.NOT_EXECUTED,
            production_eligible=False,
        )


__all__ = ["AiDraftIntegrationService"]
