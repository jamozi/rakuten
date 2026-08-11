"""Closed values for the ST-0806 recorded AI draft integration seam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import NoReturn, SupportsIndex, final
from uuid import UUID

from raos.domain.ai.job_orchestration import (
    AiJobResult,
    JobDisposition,
    ValidationStatus,
)
from raos.domain.editorial.article_lifecycle import (
    ArticleState,
    ArticleVersionState,
    BodySha256,
    VersionSnapshot,
)
from raos.domain.editorial.content_ast import ContentAst


AI_ARTICLE_DRAFT_TASK = "ai.article_draft.v1"
_SAFE_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_REFERENCES = 1_000
_MAX_CHANGED_BLOCKS = 1_000
_REDACTED = "<redacted-ai-draft-integration>"


class AiDraftEnvironment(str, Enum):
    ENV_DEV = "ENV_DEV"
    CI = "CI"


class AiDraftIntegrationFailureCode(str, Enum):
    INVALID_REQUEST = "INVALID_REQUEST"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    UPSTREAM_JOB_INVALID = "UPSTREAM_JOB_INVALID"
    BINDING_MISMATCH = "BINDING_MISMATCH"
    CANDIDATE_INVALID = "CANDIDATE_INVALID"
    COLLABORATOR_FAILURE = "COLLABORATOR_FAILURE"
    RESULT_MISMATCH = "RESULT_MISMATCH"


class AiDraftDisposition(str, Enum):
    HUMAN_EDITABLE_RECORDED_ONLY = "HUMAN_EDITABLE_RECORDED_ONLY"


class CoverageStatus(str, Enum):
    UNEVALUABLE = "UNEVALUABLE"


class ExecutionStatus(str, Enum):
    RECORDED_ONLY = "RECORDED_ONLY"
    NOT_EXECUTED = "NOT_EXECUTED"


@final
class AiDraftIntegrationFailure(RuntimeError):
    """Stable failure which never retains rejected or collaborator material."""

    __slots__ = ("_code",)
    _code: AiDraftIntegrationFailureCode

    def __init__(self, code: AiDraftIntegrationFailureCode) -> None:
        if type(code) is not AiDraftIntegrationFailureCode:
            raise TypeError("code must be an exact AiDraftIntegrationFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)

    @property
    def code(self) -> AiDraftIntegrationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if name == "__traceback__":
            BaseException.__setattr__(self, name, value)
            return
        del name, value
        raise AttributeError("AiDraftIntegrationFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("AiDraftIntegrationFailure is immutable")

    def __repr__(self) -> str:
        return f"AiDraftIntegrationFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("AI draft integration failure serialization is unsupported")


def fail_ai_draft_integration(code: AiDraftIntegrationFailureCode) -> NoReturn:
    raise AiDraftIntegrationFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("AI draft integration value serialization is unsupported")


def _require_uuid(value: object) -> UUID:
    if type(value) is not UUID:
        fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
    return value


def _require_token(value: object) -> str:
    if type(value) is not str or _SAFE_TOKEN.fullmatch(value) is None:
        fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
    return value


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
    return value


@final
@dataclass(frozen=True, slots=True, repr=False)
class ClaimFactReference(_RedactedValue):
    """One explicitly supplied ordered Claim-to-Fact identity binding."""

    ordinal: int
    claim_id: UUID
    fact_id: UUID
    source_packet_version_id: UUID

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or not 1 <= self.ordinal <= _MAX_REFERENCES:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.claim_id)
        _require_uuid(self.fact_id)
        _require_uuid(self.source_packet_version_id)


@final
@dataclass(frozen=True, slots=True, repr=False)
class MinimalDraftDiff(_RedactedValue):
    """Metadata-only before/after body diff; it never carries content bytes."""

    before_body_sha256: str
    after_body_sha256: str
    changed: bool
    changed_block_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_sha256(self.before_body_sha256)
        _require_sha256(self.after_body_sha256)
        if type(self.changed) is not bool or type(self.changed_block_ids) is not tuple:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        if not len(self.changed_block_ids) <= _MAX_CHANGED_BLOCKS:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        if any(
            _SAFE_TOKEN.fullmatch(block_id) is None
            for block_id in self.changed_block_ids
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        if len(set(self.changed_block_ids)) != len(self.changed_block_ids):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        if self.changed:
            if (
                self.before_body_sha256 == self.after_body_sha256
                or not self.changed_block_ids
            ):
                fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        elif (
            self.before_body_sha256 != self.after_body_sha256 or self.changed_block_ids
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)


@final
@dataclass(frozen=True, slots=True, repr=False)
class RecordedDraftCandidate(_RedactedValue):
    """Synthetic hash-bound candidate returned by the one-shot adapter."""

    ai_job_id: UUID
    task_code: str
    validation_status: ValidationStatus
    output_artifact_id: UUID
    output_artifact_sha256: str
    source_packet_version_id: UUID
    article_id: UUID
    article_version_id: UUID
    site_id: UUID
    category_id: UUID
    body_sha256: str
    content_ast: ContentAst
    diff: MinimalDraftDiff
    claim_fact_references: tuple[ClaimFactReference, ...]

    def __post_init__(self) -> None:
        _require_uuid(self.ai_job_id)
        if self.task_code != AI_ARTICLE_DRAFT_TASK:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if self.validation_status is not ValidationStatus.PASS:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        _require_uuid(self.output_artifact_id)
        _require_sha256(self.output_artifact_sha256)
        _require_uuid(self.source_packet_version_id)
        _require_uuid(self.article_id)
        _require_uuid(self.article_version_id)
        _require_uuid(self.site_id)
        _require_uuid(self.category_id)
        _require_sha256(self.body_sha256)
        if (
            type(self.content_ast) is not ContentAst
            or type(self.diff) is not MinimalDraftDiff
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        try:
            ast_body_sha256 = BodySha256.of(self.content_ast).value
            block_ids = tuple(block.block_id for block in self.content_ast.blocks)
        except Exception:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if (
            self.content_ast.article_id != str(self.article_id)
            or self.content_ast.article_version_id != str(self.article_version_id)
            or self.content_ast.source_packet_version_ref
            != str(self.source_packet_version_id)
            or self.body_sha256 != ast_body_sha256
            or self.diff.after_body_sha256 != self.body_sha256
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.BINDING_MISMATCH)
        changed_ids = self.diff.changed_block_ids
        if any(block_id not in block_ids for block_id in changed_ids):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if (
            tuple(block_id for block_id in block_ids if block_id in set(changed_ids))
            != changed_ids
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if type(self.claim_fact_references) is not tuple:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if not 1 <= len(self.claim_fact_references) <= _MAX_REFERENCES:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if any(
            type(item) is not ClaimFactReference for item in self.claim_fact_references
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        if tuple(item.ordinal for item in self.claim_fact_references) != tuple(
            range(1, len(self.claim_fact_references) + 1)
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.CANDIDATE_INVALID)
        pairs = tuple(
            (item.claim_id, item.fact_id) for item in self.claim_fact_references
        )
        if len(set(pairs)) != len(pairs) or any(
            item.source_packet_version_id != self.source_packet_version_id
            for item in self.claim_fact_references
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.BINDING_MISMATCH)


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiDraftIntegrationRequest(_RedactedValue):
    """All explicit identities needed for one recorded draft-candidate call."""

    environment: AiDraftEnvironment
    operation_id: str
    ai_job_result: AiJobResult
    source_version: VersionSnapshot
    article_state: ArticleState
    site_id: UUID
    category_id: UUID

    def __post_init__(self) -> None:
        if type(self.environment) is not AiDraftEnvironment:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.DEVELOPMENT_ONLY)
        _require_token(self.operation_id)
        if type(self.ai_job_result) is not AiJobResult:
            fail_ai_draft_integration(
                AiDraftIntegrationFailureCode.UPSTREAM_JOB_INVALID
            )
        if (
            self.ai_job_result.operation_id != self.operation_id
            or self.ai_job_result.task_code != AI_ARTICLE_DRAFT_TASK
            or self.ai_job_result.disposition is not JobDisposition.SUCCEEDED
            or self.ai_job_result.validation_status is not ValidationStatus.PASS
            or self.ai_job_result.retryable
            or self.ai_job_result.attempt_number != 1
            or self.ai_job_result.output_artifact_id is None
            or self.ai_job_result.output_artifact_sha256 is None
        ):
            fail_ai_draft_integration(
                AiDraftIntegrationFailureCode.UPSTREAM_JOB_INVALID
            )
        if type(self.source_version) is not VersionSnapshot:
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        if (
            self.article_state is not ArticleState.DRAFT
            or self.source_version.state is not ArticleVersionState.DRAFT
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.INVALID_REQUEST)
        _require_uuid(self.site_id)
        _require_uuid(self.category_id)


@final
@dataclass(frozen=True, slots=True, repr=False)
class AiDraftIntegrationResult(_RedactedValue):
    request: AiDraftIntegrationRequest
    candidate: RecordedDraftCandidate
    disposition: AiDraftDisposition
    article_state: ArticleState
    version_state: ArticleVersionState
    coverage_status: CoverageStatus
    execution: ExecutionStatus
    approval_permitted: bool
    publication_permitted: bool
    merge_performed: bool
    apply_performed: bool
    persistence: ExecutionStatus
    event_emission: ExecutionStatus
    release: ExecutionStatus
    formal_validation: ExecutionStatus
    production_eligible: bool

    def __post_init__(self) -> None:
        if (
            type(self.request) is not AiDraftIntegrationRequest
            or type(self.candidate) is not RecordedDraftCandidate
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.RESULT_MISMATCH)
        job = self.request.ai_job_result
        source = self.request.source_version
        candidate = self.candidate
        if (
            candidate.ai_job_id != job.ai_job_id
            or candidate.task_code != job.task_code
            or candidate.validation_status is not job.validation_status
            or candidate.output_artifact_id != job.output_artifact_id
            or candidate.output_artifact_sha256 != job.output_artifact_sha256
            or candidate.source_packet_version_id != source.source_packet_version_id
            or candidate.article_id != source.article_id
            or candidate.article_version_id != source.version_id
            or candidate.site_id != self.request.site_id
            or candidate.category_id != self.request.category_id
            or candidate.diff.before_body_sha256 != source.body_sha256.value
            or candidate.content_ast.article_type.value
            != source.content_ast.article_type.value
            or candidate.content_ast.title != source.title
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.BINDING_MISMATCH)
        if (
            self.disposition is not AiDraftDisposition.HUMAN_EDITABLE_RECORDED_ONLY
            or self.article_state is not ArticleState.DRAFT
            or self.version_state is not ArticleVersionState.DRAFT
            or self.coverage_status is not CoverageStatus.UNEVALUABLE
            or self.execution is not ExecutionStatus.RECORDED_ONLY
            or self.approval_permitted
            or self.publication_permitted
            or self.merge_performed
            or self.apply_performed
            or self.persistence is not ExecutionStatus.NOT_EXECUTED
            or self.event_emission is not ExecutionStatus.NOT_EXECUTED
            or self.release is not ExecutionStatus.NOT_EXECUTED
            or self.formal_validation is not ExecutionStatus.NOT_EXECUTED
            or self.production_eligible
        ):
            fail_ai_draft_integration(AiDraftIntegrationFailureCode.RESULT_MISMATCH)


__all__ = [
    "AI_ARTICLE_DRAFT_TASK",
    "AiDraftDisposition",
    "AiDraftEnvironment",
    "AiDraftIntegrationFailure",
    "AiDraftIntegrationFailureCode",
    "AiDraftIntegrationRequest",
    "AiDraftIntegrationResult",
    "ClaimFactReference",
    "CoverageStatus",
    "ExecutionStatus",
    "MinimalDraftDiff",
    "RecordedDraftCandidate",
    "fail_ai_draft_integration",
]
