"""Synthetic one-shot fixtures for ST-0806."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import cast
from uuid import UUID


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.adapters.recorded_ai_draft_integration import (  # noqa: E402
    RecordedAiDraftIntegrationAdapter,
    RecordedAiDraftIntegrationStep,
)
from raos.application.editorial.ai_draft_integration import (  # noqa: E402
    AiDraftIntegrationService,
)
from raos.domain.ai.job_orchestration import (  # noqa: E402
    AiJobResult,
    JobDisposition,
    ValidationStatus,
)
from raos.domain.ai.routing import BudgetCommit  # noqa: E402
from raos.domain.editorial.ai_draft_integration import (  # noqa: E402
    AI_ARTICLE_DRAFT_TASK,
    AiDraftEnvironment,
    AiDraftIntegrationRequest,
    ClaimFactReference,
    MinimalDraftDiff,
    RecordedDraftCandidate,
)
from raos.domain.editorial.article_lifecycle import (  # noqa: E402
    ArticleState,
    ArticleVersionState,
    BodySha256,
    SourcePacketVerification,
    VersionDisplayId,
    VersionSnapshot,
)
from raos.domain.editorial.article_plan import ArticlePlanType  # noqa: E402
from raos.domain.editorial.content_ast import (  # noqa: E402
    ContentAst,
    load_content_ast,
)
from raos.domain.portfolio.workflow import (  # noqa: E402
    EntityVersion,
    StrongEtag,
    UtcTimestamp,
)


ARTICLE_ID = UUID("018f3e90-7b00-7000-8000-000000000806")
VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000807")
SOURCE_PACKET_VERSION_ID = UUID("018f3e90-7b00-7000-8000-000000000808")
SITE_ID = UUID("018f3e90-7b00-7000-8000-000000000809")
CATEGORY_ID = UUID("018f3e90-7b00-7000-8000-000000000810")
AI_JOB_ID = UUID("00000000-0000-4000-8000-000000000806")
OPS_JOB_ID = UUID("00000000-0000-4000-8000-000000030806")
OUTPUT_ARTIFACT_ID = UUID("00000000-0000-4000-8000-000000070806")
CLAIM_ID_1 = UUID("00000000-0000-4000-8000-000000060511")
CLAIM_ID_2 = UUID("00000000-0000-4000-8000-000000060512")
FACT_ID_1 = UUID("00000000-0000-4000-8000-000000060521")
FACT_ID_2 = UUID("00000000-0000-4000-8000-000000060522")
OUTPUT_ARTIFACT_SHA256 = "8" * 64
OPERATION_ID = "operation.st0806.recorded.v1"
TITLE = "Synthetic AI draft integration article"
NOW = UtcTimestamp(datetime(2026, 8, 12, 3, 0, tzinfo=UTC))


def _payload() -> dict[str, object]:
    fixture = (
        REPOSITORY_ROOT
        / "contracts/raos-v0.4/contracts/content/fixtures/valid/selection_guide.json"
    )
    payload: dict[str, object] = json.loads(fixture.read_text(encoding="utf-8"))
    payload["article_id"] = str(ARTICLE_ID)
    payload["article_version_id"] = str(VERSION_ID)
    payload["source_packet_version_ref"] = str(SOURCE_PACKET_VERSION_ID)
    payload["title"] = TITLE
    return payload


def source_ast() -> ContentAst:
    return load_content_ast(json.dumps(_payload(), ensure_ascii=False))


def candidate_ast() -> ContentAst:
    payload = _payload()
    blocks = payload["blocks"]
    assert isinstance(blocks, list)
    lead = cast(dict[str, object], blocks[1])
    content = cast(list[object], lead["content"])
    text = cast(dict[str, object], content[0])
    text["text"] = "この合成候補は、人間が編集するための記録済みドラフトです。"
    return load_content_ast(json.dumps(payload, ensure_ascii=False))


def source_version() -> VersionSnapshot:
    ast = source_ast()
    return VersionSnapshot(
        version_id=VERSION_ID,
        display_id=VersionDisplayId("ARV-TEST-0806"),
        article_id=ARTICLE_ID,
        version_no=1,
        article_type=ArticlePlanType.SELECTION_GUIDE,
        title=TITLE,
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        source_packet_verification=SourcePacketVerification.NOT_VERIFIED,
        based_on_version_id=None,
        content_ast=ast,
        body_sha256=BodySha256.of(ast),
        state=ArticleVersionState.DRAFT,
        submitted_at=None,
        reviewed_at=None,
        approved_at=None,
        published_at=None,
        version=EntityVersion(0),
        etag=StrongEtag('"test-only-st0806-version-v0"'),
        created_at=NOW,
        updated_at=NOW,
    )


def successful_job() -> AiJobResult:
    return AiJobResult(
        operation_id=OPERATION_ID,
        command_fingerprint_sha256="7" * 64,
        ai_job_id=AI_JOB_ID,
        ops_job_id=OPS_JOB_ID,
        task_code=AI_ARTICLE_DRAFT_TASK,
        attempt_number=1,
        disposition=JobDisposition.SUCCEEDED,
        failure_code=None,
        retryable=False,
        actual_cost_jpy=7,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256=OUTPUT_ARTIFACT_SHA256,
        provider_request_id="synthetic.st0806.request.v1",
        validation_status=ValidationStatus.PASS,
        budget_receipt=BudgetCommit(
            reservation_id="5" * 64,
            intent_sha256="6" * 64,
            committed_jpy=7,
            committed_at=NOW.value,
        ),
    )


def request(
    *, environment: AiDraftEnvironment = AiDraftEnvironment.ENV_DEV
) -> AiDraftIntegrationRequest:
    return AiDraftIntegrationRequest(
        environment=environment,
        operation_id=OPERATION_ID,
        ai_job_result=successful_job(),
        source_version=source_version(),
        article_state=ArticleState.DRAFT,
        site_id=SITE_ID,
        category_id=CATEGORY_ID,
    )


def candidate() -> RecordedDraftCandidate:
    ast = candidate_ast()
    version = source_version()
    return RecordedDraftCandidate(
        ai_job_id=AI_JOB_ID,
        task_code=AI_ARTICLE_DRAFT_TASK,
        validation_status=ValidationStatus.PASS,
        output_artifact_id=OUTPUT_ARTIFACT_ID,
        output_artifact_sha256=OUTPUT_ARTIFACT_SHA256,
        source_packet_version_id=SOURCE_PACKET_VERSION_ID,
        article_id=ARTICLE_ID,
        article_version_id=VERSION_ID,
        site_id=SITE_ID,
        category_id=CATEGORY_ID,
        body_sha256=BodySha256.of(ast).value,
        content_ast=ast,
        diff=MinimalDraftDiff(
            before_body_sha256=version.body_sha256.value,
            after_body_sha256=BodySha256.of(ast).value,
            changed=True,
            changed_block_ids=("BLK-FIX-002",),
        ),
        claim_fact_references=(
            ClaimFactReference(1, CLAIM_ID_1, FACT_ID_1, SOURCE_PACKET_VERSION_ID),
            ClaimFactReference(2, CLAIM_ID_2, FACT_ID_2, SOURCE_PACKET_VERSION_ID),
        ),
    )


def service_and_adapter(
    *, environment: AiDraftEnvironment = AiDraftEnvironment.ENV_DEV
) -> tuple[AiDraftIntegrationService, RecordedAiDraftIntegrationAdapter]:
    bound_request = request(environment=environment)
    adapter = RecordedAiDraftIntegrationAdapter(
        environment=environment,
        script_capacity=1,
        scripts=(
            RecordedAiDraftIntegrationStep(
                request=bound_request,
                candidate=candidate(),
            ),
        ),
    )
    return AiDraftIntegrationService(environment=environment, port=adapter), adapter
