"""Synthetic, content-free fixtures for the isolated ST-0704 suite."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.development_ai_controls import (  # noqa: E402
    InMemoryDevelopmentAiControls,
    SyntheticRouteEligibilityFixture,
)
from raos.application.ai.routing import DevelopmentAiRoutingService  # noqa: E402
from raos.config.runtime import RuntimeEnvironment  # noqa: E402
from raos.domain.ai.contracts import (  # noqa: E402
    OutputSchemaContract,
    PromptContract,
    RouteContract,
    TaskContract,
)
from raos.domain.ai.routing import (  # noqa: E402
    RouteIdentity,
    RouteReservationRequest,
    SyntheticRouteCertification,
    SyntheticRouteQuote,
)
from raos.ports.task_registry import UnknownTaskContract  # noqa: E402


NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
VALID_FROM = NOW - timedelta(minutes=5)
EXPIRES_AT = NOW + timedelta(minutes=5)
TASK_CODE = "ai.article_draft.v1"
ROUTE_CODE = "route.editorial_balanced.v1"
ROUTE_VERSION = "synthetic.route-version.local.v1"
MODEL_ID = "synthetic.model.local.v1"
CERTIFICATION_ID = "synthetic.certification.local.v1"
TASK_SHA256 = "1" * 64
TASK_BINDING_SHA256 = "2" * 64
ROUTE_SHA256 = "3" * 64
PROMPT_SHA256 = "4" * 64
SCHEMA_SHA256 = "5" * 64
IDENTITY = RouteIdentity(
    task_code=TASK_CODE,
    route_code=ROUTE_CODE,
    route_version=ROUTE_VERSION,
    model_id=MODEL_ID,
)


class SyntheticTaskRegistry:
    """Small in-memory task registry that never authorizes a route itself."""

    def __init__(self, tasks: tuple[TaskContract, ...]) -> None:
        self._tasks = {task.task_code: task for task in tasks}

    def get(self, task_code: str) -> TaskContract:
        task = self._tasks.get(task_code)
        if task is None:
            raise UnknownTaskContract("synthetic task is not registered")
        return task


def task_contract(
    *,
    task_code: str = TASK_CODE,
    route_code: str = ROUTE_CODE,
    prompt_status: str = "CANDIDATE",
    lifecycle: str = "MVP",
    route_enabled: bool = True,
    binding_sha256: str = TASK_BINDING_SHA256,
    route_sha256: str = ROUTE_SHA256,
) -> TaskContract:
    prompt = PromptContract(
        prompt_code="PROMPT-SYNTHETIC-TEST-ONLY",
        version=1,
        task_code=task_code,
        status=prompt_status,
        locale="ja-JP",
        artifact_path="contracts/ai/prompts/synthetic-test-only.md",
        sha256=PROMPT_SHA256,
        content="SYNTHETIC_TEST_ONLY",
        metadata={"task_code": task_code},
    )
    output_schema = OutputSchemaContract(
        schema_id="https://schemas.raos.local/ai/synthetic-test-only/v1",
        artifact_path="contracts/ai/schemas/synthetic-test-only.json",
        sha256=SCHEMA_SHA256,
        document={
            "$id": "https://schemas.raos.local/ai/synthetic-test-only/v1",
            "type": "object",
        },
        metadata={"kind": "task_output"},
    )
    route = RouteContract(
        route_code=route_code,
        sha256=route_sha256,
        metadata={
            "route_code": route_code,
            "enabled": route_enabled,
            "store": False,
            "strict_structured_output": True,
            "status_boundary": "CANDIDATE_METADATA_ONLY",
        },
    )
    return TaskContract(
        task_code=task_code,
        catalog_id="AIT-SYNTHETIC-TEST-ONLY",
        lifecycle=lifecycle,
        risk_level="CRITICAL",
        sha256=TASK_SHA256,
        binding_sha256=binding_sha256,
        prompt=prompt,
        output_schema=output_schema,
        route=route,
        metadata={"task_code": task_code, "route_code": route_code},
    )


def route_identity(
    *,
    task_code: str = TASK_CODE,
    route_code: str = ROUTE_CODE,
    route_version: str = ROUTE_VERSION,
    model_id: str = MODEL_ID,
) -> RouteIdentity:
    return RouteIdentity(
        task_code=task_code,
        route_code=route_code,
        route_version=route_version,
        model_id=model_id,
    )


def certification(
    *,
    identity: RouteIdentity = IDENTITY,
    certification_id: str = CERTIFICATION_ID,
    task_binding_sha256: str = TASK_BINDING_SHA256,
    route_sha256: str = ROUTE_SHA256,
    eligible: bool = True,
    valid_from: datetime = VALID_FROM,
    expires_at: datetime = EXPIRES_AT,
    selection_rank: int = 0,
) -> SyntheticRouteCertification:
    return SyntheticRouteCertification(
        identity=identity,
        certification_id=certification_id,
        task_binding_sha256=task_binding_sha256,
        route_sha256=route_sha256,
        eligible=eligible,
        valid_from=valid_from,
        expires_at=expires_at,
        selection_rank=selection_rank,
    )


def quote(
    *,
    identity: RouteIdentity = IDENTITY,
    certification_id: str = CERTIFICATION_ID,
    quote_id: str = "synthetic.quote.local.v1",
    amount_jpy: int = 7,
    valid_from: datetime = VALID_FROM,
    expires_at: datetime = EXPIRES_AT,
) -> SyntheticRouteQuote:
    return SyntheticRouteQuote(
        identity=identity,
        certification_id=certification_id,
        quote_id=quote_id,
        estimated_cost_jpy=amount_jpy,
        valid_from=valid_from,
        expires_at=expires_at,
    )


def reservation_request(
    *,
    operation_id: str = "operation.synthetic.local.v1",
    task_code: str = TASK_CODE,
    route_quote: SyntheticRouteQuote | None = None,
    amount_jpy: int = 7,
    reservation_expires_at: datetime = NOW + timedelta(minutes=1),
) -> RouteReservationRequest:
    return RouteReservationRequest(
        operation_id=operation_id,
        task_code=task_code,
        quote=route_quote or quote(amount_jpy=amount_jpy),
        reservation_expires_at=reservation_expires_at,
    )


def routing_service(
    *,
    cap_jpy: int = 10,
    candidates: tuple[SyntheticRouteCertification, ...] | None = None,
    closed_routes: tuple[RouteIdentity, ...] = (IDENTITY,),
    task: TaskContract | None = None,
) -> tuple[
    DevelopmentAiRoutingService,
    SyntheticRouteEligibilityFixture,
    InMemoryDevelopmentAiControls,
]:
    registry = SyntheticTaskRegistry((task or task_contract(),))
    eligibility = SyntheticRouteEligibilityFixture(
        environment=RuntimeEnvironment.ENV_DEV,
        candidates=(certification(),) if candidates is None else candidates,
    )
    controls = InMemoryDevelopmentAiControls(
        environment=RuntimeEnvironment.ENV_DEV,
        synthetic_cap_jpy=cap_jpy,
        initially_closed_routes=closed_routes,
    )
    service = DevelopmentAiRoutingService(
        environment=RuntimeEnvironment.ENV_DEV,
        task_registry=registry,
        eligibility=eligibility,
        controls=controls,
    )
    return service, eligibility, controls
