"""Positive, missing, stale, and invalid-edge AI/POLICY repository paths."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Column, MetaData, String, Table
from sqlalchemy.orm import Session

from raos.adapters.persistence.sqlalchemy.repositories import ai as ai_adapters
from raos.adapters.persistence.sqlalchemy.repositories import policy as policy_adapters
from raos.domain.ai.aggregates import (
    AiJob,
    AiJobState,
    AiTaskDefinition,
    AiTaskDefinitionState,
    ModelRouteVersion,
    ModelRouteVersionState,
    ReleaseDecision,
    ReleaseDecisionState,
)
from raos.domain.ai.enums import (
    AiJobStatus,
    AiTaskDefinitionRiskLevel,
    AiTaskDefinitionStatus,
    ModelRouteVersionStatus,
    ReleaseDecisionReleaseScope,
    ReleaseDecisionRollbackStrategy,
    ReleaseDecisionStatus,
)
from raos.domain.ai.events import (
    AiJobFailed,
    AiJobSucceeded,
    AiPolicyAssistCompleted,
    AiReleaseDecisionApproved,
    AiReleaseDecisionRevoked,
)
from raos.domain.ai.ids import (
    AiJobId,
    AiTaskDefinitionId,
    EvaluationDatasetVersionId,
    EvaluationRunId,
    ModelDefinitionId,
    ModelRouteVersionId,
    OutputSchemaVersionId,
    PromptVersionId,
    ReleaseApprovalId,
    ReleaseDecisionId,
)
from raos.domain.ai.values import (
    AiJobRequestConfigJson,
    ModelRouteVersionRouteConfigJson,
)
from raos.domain.evidence.ids import SourcePacketVersionId
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.ids import JobId, ObjectArtifactId
from raos.domain.policy.aggregates import (
    RuleVersion,
    RuleVersionState,
    Waiver,
    WaiverState,
)
from raos.domain.policy.enums import (
    RuleVersionImplementationType,
    RuleVersionRuleCategory,
    RuleVersionSeverity,
    RuleVersionStatus,
    WaiverScopeType,
    WaiverStatus,
)
from raos.domain.policy.ids import FindingId, PolicyBundleId, RuleVersionId, WaiverId
from raos.domain.policy.values import RuleVersionDefinitionJson
from raos.domain.shared.identity import Actor, ActorType, ScopeId
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    GitCommitDigest,
    Sha256Digest,
    YenMinor,
)
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.context import PersistenceContext


T0 = datetime(2026, 8, 24, 3, 0, tzinfo=timezone.utc)


def _uuid(suffix: int) -> UUID:
    return UUID(f"018f0000-0000-7000-8000-{suffix:012d}")


class _Result:
    def __init__(
        self,
        *,
        row: dict[str, object] | None = None,
        rows: tuple[dict[str, object], ...] = (),
        rowcount: int = 1,
    ) -> None:
        self._row = row
        self._rows = rows
        self.rowcount = rowcount

    def mappings(self) -> _Result:
        return self

    def one_or_none(self) -> dict[str, object] | None:
        return self._row

    def __iter__(self) -> object:
        return iter(self._rows)


class _ScriptedSession(Session):
    def __init__(self, *results: _Result) -> None:
        super().__init__()
        self._results = list(results)
        self.statements: list[object] = []

    def execute(self, statement: object, *args: object, **kwargs: object) -> Any:
        del args, kwargs
        self.statements.append(statement)
        if not self._results:
            raise AssertionError("unexpected SQL execution")
        return self._results.pop(0)


def _table(relation: str, columns: tuple[str, ...]) -> Table:
    schema, name = relation.split(".", 1)
    return Table(
        name,
        MetaData(schema=schema),
        *(Column(column, String) for column in columns),
    )


def _task(status: AiTaskDefinitionStatus) -> AiTaskDefinition:
    return AiTaskDefinition(
        AiTaskDefinitionState(
            id=AiTaskDefinitionId(_uuid(1)),
            task_code="ARTICLE_DRAFT",
            name="Article draft",
            description="Draft from evidence",
            risk_level=AiTaskDefinitionRiskLevel.HIGH,
            output_schema_code="article.v1",
            default_max_tokens=4096,
            default_max_cost_jpy=YenMinor(500),
            human_review_required=True,
            status=status,
            created_at=AwareUtcDateTime(T0),
        )
    )


def _route(
    *,
    version_no: int = 1,
    status: ModelRouteVersionStatus = ModelRouteVersionStatus.DRAFT,
    lock_version: int = 0,
) -> ModelRouteVersion:
    return ModelRouteVersion(
        ModelRouteVersionState(
            id=ModelRouteVersionId(_uuid(10 + version_no)),
            route_code="ARTICLE_DRAFT",
            version_no=version_no,
            task_definition_id=AiTaskDefinitionId(_uuid(1)),
            primary_model_id=ModelDefinitionId(_uuid(20)),
            fallback_model_id=None,
            route_config=ModelRouteVersionRouteConfigJson(
                FrozenJsonObject.from_mapping({"live_enabled": False})
            ),
            monthly_budget_jpy=YenMinor(10000),
            per_job_budget_jpy=YenMinor(500),
            status=status,
            effective_from=None,
            effective_to=None,
            approved_by_principal_id=None,
            created_at=AwareUtcDateTime(T0),
            lock_version=AggregateVersion(lock_version),
            updated_at=AwareUtcDateTime(T0),
        )
    )


def _ai_job(
    *,
    status: AiJobStatus,
    lock_version: int,
) -> AiJob:
    completed_at = (
        AwareUtcDateTime(T0 + timedelta(minutes=1))
        if status in {AiJobStatus.SUCCEEDED, AiJobStatus.FAILED_TERMINAL}
        else None
    )
    return AiJob(
        AiJobState(
            id=AiJobId(_uuid(100)),
            display_id="AIJ-001",
            ops_job_id=JobId(_uuid(101)),
            task_definition_id=AiTaskDefinitionId(_uuid(102)),
            article_plan_id=None,
            article_version_id=ArticleVersionId(_uuid(107)),
            source_packet_version_id=SourcePacketVersionId(_uuid(103)),
            prompt_version_id=PromptVersionId(_uuid(104)),
            output_schema_version_id=OutputSchemaVersionId(_uuid(105)),
            model_route_version_id=ModelRouteVersionId(_uuid(106)),
            status=status,
            max_cost_jpy=YenMinor(500),
            completed_at=completed_at,
            created_at=AwareUtcDateTime(T0),
            policy_bundle_version_id=None,
            release_decision_id=None,
            request_config=AiJobRequestConfigJson(FrozenJsonObject()),
            input_manifest_sha256=None,
            budget_reserved_jpy=YenMinor(500),
            lock_version=AggregateVersion(lock_version),
            updated_at=AwareUtcDateTime(T0 + timedelta(minutes=lock_version)),
        )
    )


def _artifact(*, suffix: int) -> dict[str, object]:
    return {
        "artifact_id": str(_uuid(suffix)),
        "sha256": f"{suffix % 16:x}" * 64,
    }


def _job_succeeded_event(job: AiJob, *, task_code: str) -> AiJobSucceeded:
    return AiJobSucceeded(
        event_id=_uuid(120),
        aggregate_id=job.state.id,
        aggregate_version=AggregateVersion(1),
        occurred_at=T0,
        causation_id=None,
        data=FrozenJsonObject.from_mapping(
            {
                "ai_job_id": str(job.state.id.value),
                "ops_job_id": str(job.state.ops_job_id.value),
                "output_artifact": _artifact(suffix=121),
                "task_code": task_code,
                "usage_cost_jpy": 100,
                "validation_passed": True,
            }
        ),
    )


def _policy_assist_event(job: AiJob) -> AiPolicyAssistCompleted:
    return AiPolicyAssistCompleted(
        event_id=_uuid(122),
        aggregate_id=job.state.id,
        aggregate_version=AggregateVersion(1),
        occurred_at=T0,
        causation_id=None,
        data=FrozenJsonObject.from_mapping(
            {
                "ai_job_id": str(job.state.id.value),
                "finding_candidate_count": 2,
                "output_artifact": _artifact(suffix=123),
                "quality_check_run_id": str(_uuid(124)),
            }
        ),
    )


def _job_failed_event(job: AiJob, *, task_code: str) -> AiJobFailed:
    return AiJobFailed(
        event_id=_uuid(125),
        aggregate_id=job.state.id,
        aggregate_version=AggregateVersion(1),
        occurred_at=T0,
        causation_id=None,
        data=FrozenJsonObject.from_mapping(
            {
                "ai_job_id": str(job.state.id.value),
                "attempt_count": 2,
                "error_class": "VALIDATION_FAILURE",
                "ops_job_id": str(job.state.ops_job_id.value),
                "retryable": False,
                "task_code": task_code,
            }
        ),
    )


def _release_decision(*, status: ReleaseDecisionStatus) -> ReleaseDecision:
    approved = status in {
        ReleaseDecisionStatus.APPROVED_CANARY,
        ReleaseDecisionStatus.APPROVED_ACTIVE,
        ReleaseDecisionStatus.REVOKED,
    }
    canary_started = status in {
        ReleaseDecisionStatus.APPROVED_CANARY,
        ReleaseDecisionStatus.REVOKED,
    }
    revoked = status is ReleaseDecisionStatus.REVOKED
    return ReleaseDecision(
        ReleaseDecisionState(
            id=ReleaseDecisionId(_uuid(130)),
            display_id="REL-001",
            task_definition_id=AiTaskDefinitionId(_uuid(131)),
            prompt_version_id=PromptVersionId(_uuid(132)),
            model_route_version_id=ModelRouteVersionId(_uuid(133)),
            output_schema_version_id=OutputSchemaVersionId(_uuid(134)),
            resolved_model_id=ModelDefinitionId(_uuid(135)),
            policy_bundle_version_id=PolicyBundleId(_uuid(136)),
            dataset_version_id=EvaluationDatasetVersionId(_uuid(137)),
            evaluation_run_id=EvaluationRunId(_uuid(138)),
            code_git_sha=GitCommitDigest("a" * 40),
            release_scope=ReleaseDecisionReleaseScope.CANARY,
            status=status,
            maximum_canary_percent=10,
            decision_manifest_sha256=Sha256Digest("b" * 64),
            rollback_release_decision_id=None,
            approved_by_principal_id=(PrincipalId(_uuid(145)) if approved else None),
            second_approver_principal_id=(
                PrincipalId(_uuid(146)) if approved else None
            ),
            approved_at=(AwareUtcDateTime(T0) if approved else None),
            revoked_by_principal_id=(PrincipalId(_uuid(147)) if revoked else None),
            revoked_at=(AwareUtcDateTime(T0) if revoked else None),
            revocation_reason=("CANARY_REGRESSION" if revoked else None),
            lock_version=AggregateVersion(1),
            created_at=AwareUtcDateTime(T0),
            updated_at=AwareUtcDateTime(T0 + timedelta(minutes=1)),
            judge_calibration_id=None,
            rollback_strategy=ReleaseDecisionRollbackStrategy.DISABLE_ROUTE,
            rollback_runbook_artifact_id=ObjectArtifactId(_uuid(139)),
            rollback_runbook_sha256=Sha256Digest("d" * 64),
            canary_monitoring_artifact_id=ObjectArtifactId(_uuid(144)),
            canary_monitoring_sha256=Sha256Digest("c" * 64),
            canary_evidence_artifact_id=None,
            canary_evidence_sha256=None,
            canary_started_at=(AwareUtcDateTime(T0) if canary_started else None),
            canary_completed_at=None,
            canary_started_txid=(1 if canary_started else None),
            canary_completed_txid=None,
            canary_approval_id=(
                ReleaseApprovalId(_uuid(141)) if canary_started else None
            ),
            active_approval_id=None,
        )
    )


def _release_approved_event(
    decision: ReleaseDecision,
) -> AiReleaseDecisionApproved:
    state = decision.state
    return AiReleaseDecisionApproved(
        event_id=_uuid(140),
        aggregate_id=state.id,
        aggregate_version=AggregateVersion(1),
        occurred_at=T0,
        causation_id=None,
        data=FrozenJsonObject.from_mapping(
            {
                "aggregate_version": 1,
                "approved_at": "2026-08-24T03:00:00Z",
                "canary_completed_at": None,
                "canary_completed_txid": None,
                "canary_evidence_sha256": None,
                "canary_monitoring_sha256": "c" * 64,
                "canary_started_at": "2026-08-24T03:00:00Z",
                "canary_started_txid": 1,
                "code_git_sha": "a" * 40,
                "dataset_version_id": str(state.dataset_version_id.value),
                "decision_manifest_sha256": "b" * 64,
                "evaluation_run_id": str(state.evaluation_run_id.value),
                "judge_calibration_id": None,
                "model_route_version_id": str(state.model_route_version_id.value),
                "output_schema_version_id": str(state.output_schema_version_id.value),
                "phase": "CANARY",
                "policy_bundle_version_id": str(state.policy_bundle_version_id.value),
                "prompt_version_id": str(state.prompt_version_id.value),
                "release_approval_id": str(_uuid(141)),
                "release_decision_id": str(state.id.value),
                "resolved_model_id": str(state.resolved_model_id.value),
                "rollback_release_decision_id": None,
                "rollback_runbook_artifact_id": str(_uuid(139)),
                "rollback_runbook_sha256": "d" * 64,
                "rollback_strategy": "DISABLE_ROUTE",
                "task_definition_id": str(state.task_definition_id.value),
            }
        ),
    )


def _release_revoked_event(
    decision: ReleaseDecision,
) -> AiReleaseDecisionRevoked:
    state = decision.state
    return AiReleaseDecisionRevoked(
        event_id=_uuid(142),
        aggregate_id=state.id,
        aggregate_version=AggregateVersion(1),
        occurred_at=T0,
        causation_id=None,
        data=FrozenJsonObject.from_mapping(
            {
                "aggregate_version": 1,
                "canary_completed_txid": None,
                "reason_code": "CANARY_REGRESSION",
                "release_decision_id": str(state.id.value),
                "revoked_at": "2026-08-24T03:00:00Z",
                "rollback_release_decision_id": None,
                "rollback_runbook_artifact_id": str(_uuid(139)),
                "rollback_runbook_sha256": "d" * 64,
                "rollback_strategy": "DISABLE_ROUTE",
                "task_definition_id": str(state.task_definition_id.value),
            }
        ),
    )


def _rule(
    *,
    version_no: int = 1,
    status: RuleVersionStatus = RuleVersionStatus.DRAFT,
    approved: bool = False,
) -> RuleVersion:
    return RuleVersion(
        RuleVersionState(
            id=RuleVersionId(_uuid(30 + version_no)),
            rule_code="NO_UNSUPPORTED_PRICE",
            version_no=version_no,
            rule_category=RuleVersionRuleCategory.FACTUAL,
            severity=RuleVersionSeverity.HIGH,
            is_blocking=True,
            implementation_type=RuleVersionImplementationType.PYTHON,
            definition=RuleVersionDefinitionJson(
                FrozenJsonObject.from_mapping({"entrypoint": "rules.price"})
            ),
            definition_sha256=Sha256Digest("1" * 64),
            status=status,
            created_by_principal_id=PrincipalId(_uuid(40)),
            approved_by_principal_id=(PrincipalId(_uuid(41)) if approved else None),
            created_at=AwareUtcDateTime(T0),
        )
    )


def _approved_waiver() -> Waiver:
    return Waiver(
        WaiverState(
            id=WaiverId(_uuid(50)),
            display_id="WVR-001",
            finding_id=FindingId(_uuid(51)),
            scope_type=WaiverScopeType.FINDING,
            scope_id=ScopeId(_uuid(51)),
            justification="Temporary upstream mismatch",
            status=WaiverStatus.APPROVED,
            requested_by_principal_id=PrincipalId(_uuid(52)),
            requested_at=AwareUtcDateTime(T0),
            decided_by_principal_id=PrincipalId(_uuid(53)),
            decided_at=AwareUtcDateTime(T0 + timedelta(minutes=5)),
            decision_reason="Bounded exception",
            expires_at=AwareUtcDateTime(T0 + timedelta(hours=1)),
            revoked_at=None,
            created_at=AwareUtcDateTime(T0),
        )
    )


def test_ai_state_repository_positive_get_add_transition_and_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _task(AiTaskDefinitionStatus.ACTIVE)
    target = _task(AiTaskDefinitionStatus.PAUSED)
    current_row = ai_adapters._encode_ai_task_definition(current.state)
    target_row = ai_adapters._encode_ai_task_definition(target.state)
    table = _table("ai.task_definition", tuple(current_row))
    monkeypatch.setattr(ai_adapters, "_table", lambda relation: table)

    read_session = _ScriptedSession(_Result(row=current_row))
    assert (
        ai_adapters.SqlAlchemyAiTaskDefinitionRepository(read_session).get(
            current.state.id
        )
        == current
    )

    add_session = _ScriptedSession(_Result())
    ai_adapters.SqlAlchemyAiTaskDefinitionRepository(add_session).add(current)
    assert len(add_session.statements) == 1

    transition_session = _ScriptedSession(
        _Result(row=current_row), _Result(row=target_row)
    )
    assert (
        ai_adapters.SqlAlchemyAiTaskDefinitionRepository(transition_session).transition(
            current.state.id, target, AiTaskDefinitionStatus.ACTIVE
        )
        == target
    )

    missing_session = _ScriptedSession(_Result(row=None))
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyAiTaskDefinitionRepository(missing_session).transition(
            current.state.id, target, AiTaskDefinitionStatus.ACTIVE
        )
    assert captured.value.code is PersistenceErrorCode.NOT_FOUND


def test_ai_state_repository_rejects_unlisted_edge_before_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _task(AiTaskDefinitionStatus.ACTIVE)
    row = ai_adapters._encode_ai_task_definition(current.state)
    table = _table("ai.task_definition", tuple(row))
    monkeypatch.setattr(ai_adapters, "_table", lambda relation: table)
    session = _ScriptedSession()
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyAiTaskDefinitionRepository(session).transition(
            current.state.id, current, AiTaskDefinitionStatus.ACTIVE
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert session.statements == []


def test_ai_lock_cas_version_series_and_race_classification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _route()
    target = ModelRouteVersion(
        replace(
            current.state,
            status=ModelRouteVersionStatus.EVALUATING,
            lock_version=AggregateVersion(1),
        )
    )
    current_row = ai_adapters._encode_ai_model_route_version(current.state)
    target_row = ai_adapters._encode_ai_model_route_version(target.state)
    table = _table("ai.model_route_version", tuple(current_row))
    monkeypatch.setattr(ai_adapters, "_table", lambda relation: table)

    success = _ScriptedSession(_Result(row=current_row), _Result(row=target_row))
    assert (
        ai_adapters.SqlAlchemyModelRouteVersionRepository(success).transition(
            current.state.id, target, AggregateVersion(0)
        )
        == target
    )

    race = _ScriptedSession(
        _Result(row=current_row),
        _Result(row=None),
        _Result(row={"id": current.state.id.value, "lock_version": 2}),
    )
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyModelRouteVersionRepository(race).transition(
            current.state.id, target, AggregateVersion(0)
        )
    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT

    version_two = _route(version_no=2)
    append = _ScriptedSession(_Result(row={"version_no": 1}), _Result())
    assert ai_adapters.SqlAlchemyModelRouteVersionRepository(append).append_version(
        version_two, 1
    ) == AggregateVersion(0)

    stale = _ScriptedSession(_Result(row={"version_no": 1}))
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyModelRouteVersionRepository(stale).append_version(
            version_two, 2
        )
    assert captured.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT


def test_ai_job_event_specializations_stage_exact_type_after_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _ai_job(status=AiJobStatus.VALIDATING_OUTPUT, lock_version=0)
    current_row = ai_adapters._encode_ai_ai_job(current.state)
    job_table = _table("ai.ai_job", tuple(current_row))
    task_table = _table("ai.task_definition", ("id", "task_code"))

    def resolve(relation: str) -> Table:
        if relation == "ai.ai_job":
            return job_table
        if relation == "ai.task_definition":
            return task_table
        return _table(relation, ("id",))

    monkeypatch.setattr(ai_adapters, "_table", resolve)
    monkeypatch.setattr(
        ai_adapters,
        "register_pending_events",
        lambda _session, **_kwargs: None,
    )
    stages: list[dict[str, object]] = []

    def stage(session: Session, **kwargs: object) -> None:
        assert isinstance(session, _ScriptedSession)
        stages.append({**kwargs, "statement_count": len(session.statements)})

    monkeypatch.setattr(ai_adapters, "stage_registered_events", stage)

    ordinary = _ai_job(status=AiJobStatus.SUCCEEDED, lock_version=1)
    ordinary._record_event(
        _job_succeeded_event(ordinary, task_code="ai.article_draft.v1")
    )
    policy_assist = _ai_job(status=AiJobStatus.SUCCEEDED, lock_version=1)
    policy_assist._record_event(_policy_assist_event(policy_assist))
    failed = _ai_job(status=AiJobStatus.FAILED_TERMINAL, lock_version=1)
    failed._record_event(_job_failed_event(failed, task_code="ai.article_draft.v1"))

    cases = (
        (
            ordinary,
            "ai.article_draft.v1",
            "jp.raos.ai.job_succeeded.v1",
            3,
        ),
        (
            policy_assist,
            "ai.policy_assist.v1",
            "jp.raos.ai.policy_assist_completed.v1",
            3,
        ),
        (
            failed,
            None,
            "jp.raos.ai.job_failed.v1",
            2,
        ),
    )
    for target, task_code, event_type, statement_count in cases:
        target_row = ai_adapters._encode_ai_ai_job(target.state)
        scripted = [_Result(row=current_row)]
        if task_code is not None:
            scripted.append(_Result(row={"task_code": task_code}))
        scripted.append(_Result(row=target_row))
        session = _ScriptedSession(*scripted)
        result = ai_adapters.SqlAlchemyAiJobRepository(session).transition(
            current.state.id,
            target,
            AggregateVersion(0),
        )
        assert result == target
        assert stages[-1] == {
            "aggregate_type": "ai.ai_job",
            "aggregate_id": target.state.id.value,
            "owning_method": "AiJobRepository.transition",
            "persisted_version": AggregateVersion(1),
            "expected_event_type": event_type,
            "statement_count": statement_count,
        }


@pytest.mark.parametrize("task_code", ("ai.article_draft.v1", "ai.policy_assist.v1"))
def test_ai_job_success_rejects_wrong_event_specialization_before_cas(
    monkeypatch: pytest.MonkeyPatch,
    task_code: str,
) -> None:
    current = _ai_job(status=AiJobStatus.VALIDATING_OUTPUT, lock_version=0)
    target = _ai_job(status=AiJobStatus.SUCCEEDED, lock_version=1)
    if task_code == "ai.policy_assist.v1":
        target._record_event(
            _job_succeeded_event(target, task_code="ai.policy_assist.v1")
        )
    else:
        target._record_event(_policy_assist_event(target))
    current_row = ai_adapters._encode_ai_ai_job(current.state)
    job_table = _table("ai.ai_job", tuple(current_row))
    task_table = _table("ai.task_definition", ("id", "task_code"))

    def resolve(relation: str) -> Table:
        if relation == "ai.ai_job":
            return job_table
        if relation == "ai.task_definition":
            return task_table
        return _table(relation, ("id",))

    monkeypatch.setattr(ai_adapters, "_table", resolve)
    monkeypatch.setattr(
        ai_adapters,
        "register_pending_events",
        lambda _session, **_kwargs: None,
    )
    monkeypatch.setattr(
        ai_adapters,
        "stage_registered_events",
        lambda _session, **_kwargs: pytest.fail("event staged before specialization"),
    )
    session = _ScriptedSession(
        _Result(row=current_row),
        _Result(row={"task_code": task_code}),
    )
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyAiJobRepository(session).transition(
            current.state.id,
            target,
            AggregateVersion(0),
        )
    assert captured.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
    assert len(session.statements) == 2


def test_release_event_specializations_stage_exact_type_after_cas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved = _release_decision(status=ReleaseDecisionStatus.APPROVED_CANARY)
    approved._record_event(_release_approved_event(approved))
    revoked = _release_decision(status=ReleaseDecisionStatus.REVOKED)
    revoked._record_event(_release_revoked_event(revoked))
    decision_table = _table(
        "ai.release_decision",
        tuple(ai_adapters._encode_ai_release_decision(approved.state)),
    )

    def resolve(relation: str) -> Table:
        if relation == "ai.release_decision":
            return decision_table
        return _table(relation, ("id",))

    monkeypatch.setattr(ai_adapters, "_table", resolve)
    monkeypatch.setattr(
        ai_adapters,
        "register_pending_events",
        lambda _session, **_kwargs: None,
    )
    stages: list[dict[str, object]] = []
    monkeypatch.setattr(
        ai_adapters,
        "stage_registered_events",
        lambda _session, **kwargs: stages.append(kwargs),
    )
    cases = (
        (
            ReleaseDecisionStatus.READY_FOR_REVIEW,
            approved,
            "jp.raos.ai.release_decision_approved.v1",
        ),
        (
            ReleaseDecisionStatus.APPROVED_CANARY,
            revoked,
            "jp.raos.ai.release_decision_revoked.v1",
        ),
    )
    for current_status, target, event_type in cases:
        current = _release_decision(status=current_status)
        current = ReleaseDecision(
            replace(current.state, lock_version=AggregateVersion(0))
        )
        session = _ScriptedSession(
            _Result(row=ai_adapters._encode_ai_release_decision(current.state)),
            _Result(row=ai_adapters._encode_ai_release_decision(target.state)),
        )
        result = ai_adapters.SqlAlchemyReleaseDecisionRepository(session).transition(
            target.state.id,
            target,
            AggregateVersion(0),
        )
        assert result == target
        assert stages[-1]["expected_event_type"] == event_type
        assert stages[-1]["persisted_version"] == AggregateVersion(1)


@pytest.mark.parametrize(
    "target_status",
    (ReleaseDecisionStatus.APPROVED_CANARY, ReleaseDecisionStatus.REVOKED),
)
def test_release_transition_rejects_wrong_event_specialization_before_io(
    monkeypatch: pytest.MonkeyPatch,
    target_status: ReleaseDecisionStatus,
) -> None:
    target = _release_decision(status=target_status)
    if target_status is ReleaseDecisionStatus.APPROVED_CANARY:
        target._record_event(_release_revoked_event(target))
    else:
        target._record_event(_release_approved_event(target))
    monkeypatch.setattr(
        ai_adapters,
        "_table",
        lambda relation: _table(relation, ("id",)),
    )
    session = _ScriptedSession()
    with pytest.raises(PersistenceError) as captured:
        ai_adapters.SqlAlchemyReleaseDecisionRepository(session).transition(
            target.state.id,
            target,
            AggregateVersion(0),
        )
    assert captured.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
    assert session.statements == []


def test_policy_version_series_state_cas_and_invalid_edge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _rule()
    context = PersistenceContext(
        command_id=_uuid(91),
        correlation_id=_uuid(92),
        causation_id=_uuid(93),
        actor=Actor(ActorType.USER, _uuid(94)),
        source="tests.st0308.policy",
        occurred_at=T0,
    )
    actor_id = context.actor.actor_id
    assert actor_id is not None
    target = RuleVersion(
        replace(
            current.state,
            status=RuleVersionStatus.ACTIVE,
            approved_by_principal_id=PrincipalId(actor_id),
        )
    )
    current_row = policy_adapters._encode_policy_rule_version(current.state)
    target_row = policy_adapters._encode_policy_rule_version(target.state)
    table = _table("policy.rule_version", tuple(current_row))
    monkeypatch.setattr(policy_adapters, "_table", lambda relation: table)
    monkeypatch.setattr(
        policy_adapters,
        "persistence_context",
        lambda _session: context,
    )

    success = _ScriptedSession(_Result(row=current_row), _Result(row=target_row))
    assert (
        policy_adapters.SqlAlchemyRuleVersionRepository(success).transition(
            current.state.id, target, RuleVersionStatus.DRAFT
        )
        == target
    )

    invalid = _ScriptedSession()
    with pytest.raises(PersistenceError) as captured:
        policy_adapters.SqlAlchemyRuleVersionRepository(invalid).transition(
            current.state.id, current, RuleVersionStatus.DRAFT
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert invalid.statements == []

    version_two = _rule(version_no=2)
    append = _ScriptedSession(_Result(row={"version_no": 1}), _Result())
    assert policy_adapters.SqlAlchemyRuleVersionRepository(append).append_version(
        version_two, 1
    ) == AggregateVersion(2)


def test_policy_expiry_positive_missing_and_guarded_invalid_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = _approved_waiver()
    expired = Waiver(replace(current.state, status=WaiverStatus.EXPIRED))
    current_row = policy_adapters._encode_policy_waiver(current.state)
    expired_row = policy_adapters._encode_policy_waiver(expired.state)
    table = _table("policy.waiver", tuple(current_row))
    monkeypatch.setattr(policy_adapters, "_table", lambda relation: table)
    evaluated_at = AwareUtcDateTime(T0 + timedelta(hours=2))

    success = _ScriptedSession(_Result(row=current_row), _Result(row=expired_row))
    assert (
        policy_adapters.SqlAlchemyWaiverRepository(success).mark_expired(
            current.state.id, evaluated_at, WaiverStatus.APPROVED
        )
        == expired
    )

    missing = _ScriptedSession(_Result(row=None))
    with pytest.raises(PersistenceError) as captured:
        policy_adapters.SqlAlchemyWaiverRepository(missing).mark_expired(
            current.state.id, evaluated_at, WaiverStatus.APPROVED
        )
    assert captured.value.code is PersistenceErrorCode.NOT_FOUND

    invalid = _ScriptedSession()
    with pytest.raises(PersistenceError) as captured:
        policy_adapters.SqlAlchemyWaiverRepository(invalid).mark_expired(
            current.state.id, evaluated_at, WaiverStatus.REQUESTED
        )
    assert captured.value.code is PersistenceErrorCode.STATE_CONFLICT
    assert invalid.statements == []
