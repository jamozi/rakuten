"""Exact AI outer, idempotent, joined, and factory surfaces."""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, runtime_checkable

from raos.ports.ai.repositories import (
    AiTaskDefinitionRepository,
    OutputSchemaVersionRepository,
    ModelDefinitionRepository,
    ModelRouteVersionRepository,
    PromptVersionRepository,
    AiJobRepository,
    EvaluationResultRepository,
    EvaluationSuiteRepository,
    EvaluationDatasetRepository,
    EvaluationRunRepository,
    JudgeCalibrationRepository,
    ReleaseDecisionRepository,
)
from raos.ports.persistence.audit import AuditEventAppender
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.idempotency import IdempotencyRepository
from raos.ports.persistence.outbox import OutboxEventAppender
from raos.ports.persistence.transaction import TransactionJoin


@runtime_checkable
class AiUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def task_definitions(self) -> AiTaskDefinitionRepository: ...

    @property
    def output_schemas(self) -> OutputSchemaVersionRepository: ...

    @property
    def model_definitions(self) -> ModelDefinitionRepository: ...

    @property
    def model_routes(self) -> ModelRouteVersionRepository: ...

    @property
    def prompt_versions(self) -> PromptVersionRepository: ...

    @property
    def ai_jobs(self) -> AiJobRepository: ...

    @property
    def evaluation_results(self) -> EvaluationResultRepository: ...

    @property
    def evaluation_suites(self) -> EvaluationSuiteRepository: ...

    @property
    def evaluation_datasets(self) -> EvaluationDatasetRepository: ...

    @property
    def evaluation_runs(self) -> EvaluationRunRepository: ...

    @property
    def judge_calibrations(self) -> JudgeCalibrationRepository: ...

    @property
    def release_decisions(self) -> ReleaseDecisionRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def flush(self) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def mark_rollback_only(self) -> None: ...

    def join_token(self) -> TransactionJoin: ...


@runtime_checkable
class IdempotentAiUnitOfWork(AiUnitOfWork, Protocol):
    @property
    def idempotency(self) -> IdempotencyRepository: ...


@runtime_checkable
class JoinedAiUnitOfWork(Protocol):
    @property
    def context(self) -> PersistenceContext: ...

    @property
    def audit(self) -> AuditEventAppender: ...

    @property
    def outbox(self) -> OutboxEventAppender: ...

    @property
    def task_definitions(self) -> AiTaskDefinitionRepository: ...

    @property
    def output_schemas(self) -> OutputSchemaVersionRepository: ...

    @property
    def model_definitions(self) -> ModelDefinitionRepository: ...

    @property
    def model_routes(self) -> ModelRouteVersionRepository: ...

    @property
    def prompt_versions(self) -> PromptVersionRepository: ...

    @property
    def ai_jobs(self) -> AiJobRepository: ...

    @property
    def evaluation_results(self) -> EvaluationResultRepository: ...

    @property
    def evaluation_suites(self) -> EvaluationSuiteRepository: ...

    @property
    def evaluation_datasets(self) -> EvaluationDatasetRepository: ...

    @property
    def evaluation_runs(self) -> EvaluationRunRepository: ...

    @property
    def judge_calibrations(self) -> JudgeCalibrationRepository: ...

    @property
    def release_decisions(self) -> ReleaseDecisionRepository: ...

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool: ...

    def flush(self) -> None: ...

    def mark_rollback_only(self) -> None: ...


@runtime_checkable
class AiUnitOfWorkFactory(Protocol):
    def begin(self, context: PersistenceContext) -> AiUnitOfWork: ...

    def join(
        self,
        join_capability: TransactionJoin,
        context: PersistenceContext,
    ) -> JoinedAiUnitOfWork: ...


@runtime_checkable
class IdempotentAiUnitOfWorkFactory(AiUnitOfWorkFactory, Protocol):
    def begin_idempotent(
        self,
        context: PersistenceContext,
    ) -> IdempotentAiUnitOfWork: ...


__all__ = [
    "AiUnitOfWork",
    "AiUnitOfWorkFactory",
    "IdempotentAiUnitOfWork",
    "IdempotentAiUnitOfWorkFactory",
    "JoinedAiUnitOfWork",
]
