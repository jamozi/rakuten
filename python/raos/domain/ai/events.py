"""Hash-bound AI event classes admitted by the ST-0308 registry."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.ai.ids import (
    AiJobId,
    EvaluationRunId,
    ReleaseDecisionId,
)
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventDescriptor,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time


_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)


def _invalid_payload() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


def _uuid(value: object) -> UUID:
    if type(value) is not str:
        _invalid_payload()
    try:
        parsed = UUID(value)
    except ValueError:
        _invalid_payload()
    if str(parsed) != value:
        _invalid_payload()
    return parsed


def _artifact(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        _invalid_payload()
    allowed = frozenset({"artifact_id", "uri", "sha256", "content_type", "byte_size"})
    if not {"artifact_id", "sha256"}.issubset(value):
        _invalid_payload()
    if not frozenset(value).issubset(allowed):
        _invalid_payload()
    _uuid(value["artifact_id"])
    sha256 = value["sha256"]
    if type(sha256) is not str or _SHA256.fullmatch(sha256) is None:
        _invalid_payload()
    uri = value["uri"] if "uri" in value else None
    if uri is not None and (
        type(uri) is not str or re.match(r"(?:s3|file)://", uri) is None
    ):
        _invalid_payload()
    content_type = value["content_type"] if "content_type" in value else None
    if content_type is not None and (
        type(content_type) is not str or len(content_type) > 120
    ):
        _invalid_payload()
    byte_size = value["byte_size"] if "byte_size" in value else None
    if byte_size is not None and (type(byte_size) is not int or byte_size < 0):
        _invalid_payload()


def _validate_AiJobRequested(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "ai_job_id",
            "max_cost_jpy",
            "ops_job_id",
            "source_packet_version_id",
            "task_code",
        )
    ):
        _invalid_payload()
    parsed_ai_job_id = _uuid(payload["ai_job_id"])
    if parsed_ai_job_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["ops_job_id"])
    if type(payload["task_code"]) is not str:
        _invalid_payload()
    _uuid(payload["source_packet_version_id"])
    if type(payload["max_cost_jpy"]) is not int:
        _invalid_payload()


class AiJobRequested(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.job_requested.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "9937ac30df245d120ccf06aaaf406a8b29cdc9773307e9c9c61d9fc025abd42c"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not AiJobId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_AiJobSucceeded(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "ai_job_id",
            "ops_job_id",
            "output_artifact",
            "task_code",
            "usage_cost_jpy",
            "validation_passed",
        )
    ):
        _invalid_payload()
    parsed_ai_job_id = _uuid(payload["ai_job_id"])
    if parsed_ai_job_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["ops_job_id"])
    if type(payload["task_code"]) is not str:
        _invalid_payload()
    _artifact(payload["output_artifact"])
    usage_cost_jpy = payload["usage_cost_jpy"]
    if type(usage_cost_jpy) is not int or usage_cost_jpy < 0:
        _invalid_payload()
    if payload["validation_passed"] is not True:
        _invalid_payload()


class AiJobSucceeded(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.job_succeeded.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "670dbd4036129bb41284eafa6fb8809b260593f9aab4bc270384509d41d2057a"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not AiJobId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_AiJobFailed(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "ai_job_id",
            "attempt_count",
            "error_class",
            "ops_job_id",
            "retryable",
            "task_code",
        )
    ):
        _invalid_payload()
    parsed_ai_job_id = _uuid(payload["ai_job_id"])
    if parsed_ai_job_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["ops_job_id"])
    if type(payload["task_code"]) is not str:
        _invalid_payload()
    if type(payload["error_class"]) is not str:
        _invalid_payload()
    if type(payload["retryable"]) is not bool:
        _invalid_payload()
    if type(payload["attempt_count"]) is not int:
        _invalid_payload()


class AiJobFailed(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.job_failed.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "5cb07491fe735a9e1724b7539f50763928a32befb96627d642c1ad30e39fa2c7"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not AiJobId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_AiPolicyAssistCompleted(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "ai_job_id",
            "finding_candidate_count",
            "output_artifact",
            "quality_check_run_id",
        )
    ):
        _invalid_payload()
    _uuid(payload["quality_check_run_id"])
    parsed_ai_job_id = _uuid(payload["ai_job_id"])
    if parsed_ai_job_id != aggregate_id:
        _invalid_payload()
    _artifact(payload["output_artifact"])
    if type(payload["finding_candidate_count"]) is not int:
        _invalid_payload()


class AiPolicyAssistCompleted(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.policy_assist_completed.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "689bd2b267e83d0b9b46acc884526ea87a051bf7bde57221d14893ea13d27033"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not AiJobId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_AiEvaluationCompletedV2(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "baseline_evaluation_run_id",
            "code_git_sha",
            "completed_at",
            "dataset_version_id",
            "evaluation_run_id",
            "model_route_version_id",
            "output_schema_version_id",
            "passed",
            "policy_bundle_version_id",
            "prompt_version_id",
            "resolved_model_id",
            "result_manifest_sha256",
            "suite_id",
            "suite_version",
            "task_definition_id",
        )
    ):
        _invalid_payload()
    parsed_evaluation_run_id = _uuid(payload["evaluation_run_id"])
    if parsed_evaluation_run_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["suite_id"])
    suite_version = payload["suite_version"]
    if type(suite_version) is not int or suite_version < 1:
        _invalid_payload()
    _uuid(payload["dataset_version_id"])
    if payload["baseline_evaluation_run_id"] is not None:
        _uuid(payload["baseline_evaluation_run_id"])
    _uuid(payload["task_definition_id"])
    _uuid(payload["prompt_version_id"])
    _uuid(payload["model_route_version_id"])
    _uuid(payload["resolved_model_id"])
    _uuid(payload["output_schema_version_id"])
    _uuid(payload["policy_bundle_version_id"])
    code_git_sha = payload["code_git_sha"]
    if (
        type(code_git_sha) is not str
        or not 40 <= len(code_git_sha) <= 64
        or re.fullmatch("^[0-9a-f]{40,64}$", code_git_sha) is None
    ):
        _invalid_payload()
    if type(payload["passed"]) is not bool:
        _invalid_payload()
    result_manifest_sha256 = payload["result_manifest_sha256"]
    if (
        type(result_manifest_sha256) is not str
        or len(result_manifest_sha256) != 64
        or re.fullmatch("^[0-9a-f]{64}$", result_manifest_sha256) is None
    ):
        _invalid_payload()
    try:
        require_rfc3339_date_time(payload["completed_at"])
    except ValueError:
        _invalid_payload()


class AiEvaluationCompletedV2(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.evaluation_completed.v2"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "49d495fd47a2638cd6c008fa04823617af784b7991dad65d27f2c724c0725f39"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not EvaluationRunId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_AiReleaseDecisionApproved(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "aggregate_version",
            "approved_at",
            "canary_completed_at",
            "canary_completed_txid",
            "canary_evidence_sha256",
            "canary_monitoring_sha256",
            "canary_started_at",
            "canary_started_txid",
            "code_git_sha",
            "dataset_version_id",
            "decision_manifest_sha256",
            "evaluation_run_id",
            "judge_calibration_id",
            "model_route_version_id",
            "output_schema_version_id",
            "phase",
            "policy_bundle_version_id",
            "prompt_version_id",
            "release_approval_id",
            "release_decision_id",
            "resolved_model_id",
            "rollback_release_decision_id",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "rollback_strategy",
            "task_definition_id",
        )
    ):
        _invalid_payload()
    parsed_release_decision_id = _uuid(payload["release_decision_id"])
    if parsed_release_decision_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["release_approval_id"])
    _uuid(payload["task_definition_id"])
    _uuid(payload["prompt_version_id"])
    _uuid(payload["model_route_version_id"])
    _uuid(payload["resolved_model_id"])
    _uuid(payload["policy_bundle_version_id"])
    _uuid(payload["dataset_version_id"])
    _uuid(payload["output_schema_version_id"])
    _uuid(payload["evaluation_run_id"])
    if payload["judge_calibration_id"] is not None:
        _uuid(payload["judge_calibration_id"])
    code_git_sha = payload["code_git_sha"]
    if (
        type(code_git_sha) is not str
        or not 40 <= len(code_git_sha) <= 64
        or re.fullmatch("^[0-9a-f]{40,64}$", code_git_sha) is None
    ):
        _invalid_payload()
    if type(payload["phase"]) is not str or payload["phase"] not in (
        "CANARY",
        "ACTIVE",
    ):
        _invalid_payload()
    decision_manifest_sha256 = payload["decision_manifest_sha256"]
    if (
        type(decision_manifest_sha256) is not str
        or len(decision_manifest_sha256) != 64
        or re.fullmatch("^[0-9a-f]{64}$", decision_manifest_sha256) is None
    ):
        _invalid_payload()
    if type(payload["rollback_strategy"]) is not str or payload[
        "rollback_strategy"
    ] not in ("PREVIOUS_RELEASE", "DISABLE_ROUTE"):
        _invalid_payload()
    if payload["rollback_release_decision_id"] is not None:
        _uuid(payload["rollback_release_decision_id"])
    if payload["rollback_runbook_artifact_id"] is not None:
        _uuid(payload["rollback_runbook_artifact_id"])
    rollback_runbook_sha256 = payload["rollback_runbook_sha256"]
    if rollback_runbook_sha256 is not None:
        if (
            type(rollback_runbook_sha256) is not str
            or len(rollback_runbook_sha256) != 64
            or re.fullmatch("^[0-9a-f]{64}$", rollback_runbook_sha256) is None
        ):
            _invalid_payload()
    canary_evidence_sha256 = payload["canary_evidence_sha256"]
    if canary_evidence_sha256 is not None:
        if (
            type(canary_evidence_sha256) is not str
            or len(canary_evidence_sha256) != 64
            or re.fullmatch("^[0-9a-f]{64}$", canary_evidence_sha256) is None
        ):
            _invalid_payload()
    canary_monitoring_sha256 = payload["canary_monitoring_sha256"]
    if (
        type(canary_monitoring_sha256) is not str
        or len(canary_monitoring_sha256) != 64
        or re.fullmatch("^[0-9a-f]{64}$", canary_monitoring_sha256) is None
    ):
        _invalid_payload()
    try:
        require_rfc3339_date_time(payload["canary_started_at"])
    except ValueError:
        _invalid_payload()
    canary_started_txid = payload["canary_started_txid"]
    if type(canary_started_txid) is not int or canary_started_txid < 1:
        _invalid_payload()
    if payload["canary_completed_at"] is not None:
        try:
            require_rfc3339_date_time(payload["canary_completed_at"])
        except ValueError:
            _invalid_payload()
    canary_completed_txid = payload["canary_completed_txid"]
    if canary_completed_txid is not None:
        if type(canary_completed_txid) is not int or canary_completed_txid < 1:
            _invalid_payload()
    try:
        require_rfc3339_date_time(payload["approved_at"])
    except ValueError:
        _invalid_payload()
    aggregate_version = payload["aggregate_version"]
    if type(aggregate_version) is not int or aggregate_version < 1:
        _invalid_payload()


class AiReleaseDecisionApproved(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.release_decision_approved.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "947685c9cf295997629fe0acd27df88e0f78a581ca146dea445948d9f3632fa4"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ReleaseDecisionId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()
        payload_version = self.data["aggregate_version"]
        if (
            type(payload_version) is not int
            or payload_version != self.aggregate_version.value
        ):
            raise ValueError("INVALID_DOMAIN_EVENT") from None


def _validate_AiReleaseDecisionRevoked(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "aggregate_version",
            "canary_completed_txid",
            "reason_code",
            "release_decision_id",
            "revoked_at",
            "rollback_release_decision_id",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "rollback_strategy",
            "task_definition_id",
        )
    ):
        _invalid_payload()
    parsed_release_decision_id = _uuid(payload["release_decision_id"])
    if parsed_release_decision_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["task_definition_id"])
    reason_code = payload["reason_code"]
    if type(reason_code) is not str or not 1 <= len(reason_code) <= 100:
        _invalid_payload()
    if type(payload["rollback_strategy"]) is not str or payload[
        "rollback_strategy"
    ] not in ("PREVIOUS_RELEASE", "DISABLE_ROUTE"):
        _invalid_payload()
    if payload["rollback_release_decision_id"] is not None:
        _uuid(payload["rollback_release_decision_id"])
    if payload["rollback_runbook_artifact_id"] is not None:
        _uuid(payload["rollback_runbook_artifact_id"])
    rollback_runbook_sha256 = payload["rollback_runbook_sha256"]
    if rollback_runbook_sha256 is not None:
        if (
            type(rollback_runbook_sha256) is not str
            or len(rollback_runbook_sha256) != 64
            or re.fullmatch("^[0-9a-f]{64}$", rollback_runbook_sha256) is None
        ):
            _invalid_payload()
    canary_completed_txid = payload["canary_completed_txid"]
    if canary_completed_txid is not None:
        if type(canary_completed_txid) is not int or canary_completed_txid < 1:
            _invalid_payload()
    try:
        require_rfc3339_date_time(payload["revoked_at"])
    except ValueError:
        _invalid_payload()
    aggregate_version = payload["aggregate_version"]
    if type(aggregate_version) is not int or aggregate_version < 1:
        _invalid_payload()


class AiReleaseDecisionRevoked(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.ai.release_decision_revoked.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "c1a671dd2849a92c4078f726aa82f720be6349e67f123df1dd35d5455f77b7a3"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ReleaseDecisionId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()
        payload_version = self.data["aggregate_version"]
        if (
            type(payload_version) is not int
            or payload_version != self.aggregate_version.value
        ):
            raise ValueError("INVALID_DOMAIN_EVENT") from None


_AI_JOB_REQUESTED_DESCRIPTOR = EVENT_BY_TYPE[AiJobRequested.DESCRIPTOR_TYPE]
if (
    _AI_JOB_REQUESTED_DESCRIPTOR.schema_sha256 != AiJobRequested.DATA_SCHEMA_SHA256
    or _AI_JOB_REQUESTED_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiJobRequested"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_JOB_REQUESTED_BINDING = EventRuntimeBinding(
    descriptor=_AI_JOB_REQUESTED_DESCRIPTOR,
    event_class=AiJobRequested,
    payload_schema_sha256=AiJobRequested.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiJobRequested,
)

_AI_JOB_SUCCEEDED_DESCRIPTOR = EVENT_BY_TYPE[AiJobSucceeded.DESCRIPTOR_TYPE]
if (
    _AI_JOB_SUCCEEDED_DESCRIPTOR.schema_sha256 != AiJobSucceeded.DATA_SCHEMA_SHA256
    or _AI_JOB_SUCCEEDED_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiJobSucceeded"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_JOB_SUCCEEDED_BINDING = EventRuntimeBinding(
    descriptor=_AI_JOB_SUCCEEDED_DESCRIPTOR,
    event_class=AiJobSucceeded,
    payload_schema_sha256=AiJobSucceeded.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiJobSucceeded,
)

_AI_JOB_FAILED_DESCRIPTOR = EVENT_BY_TYPE[AiJobFailed.DESCRIPTOR_TYPE]
if (
    _AI_JOB_FAILED_DESCRIPTOR.schema_sha256 != AiJobFailed.DATA_SCHEMA_SHA256
    or _AI_JOB_FAILED_DESCRIPTOR.python_class != "raos.domain.ai.events.AiJobFailed"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_JOB_FAILED_BINDING = EventRuntimeBinding(
    descriptor=_AI_JOB_FAILED_DESCRIPTOR,
    event_class=AiJobFailed,
    payload_schema_sha256=AiJobFailed.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiJobFailed,
)

_AI_POLICY_ASSIST_COMPLETED_DESCRIPTOR = EVENT_BY_TYPE[
    AiPolicyAssistCompleted.DESCRIPTOR_TYPE
]
if (
    _AI_POLICY_ASSIST_COMPLETED_DESCRIPTOR.schema_sha256
    != AiPolicyAssistCompleted.DATA_SCHEMA_SHA256
    or _AI_POLICY_ASSIST_COMPLETED_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiPolicyAssistCompleted"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_POLICY_ASSIST_COMPLETED_BINDING = EventRuntimeBinding(
    descriptor=_AI_POLICY_ASSIST_COMPLETED_DESCRIPTOR,
    event_class=AiPolicyAssistCompleted,
    payload_schema_sha256=AiPolicyAssistCompleted.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiPolicyAssistCompleted,
)

_AI_EVALUATION_COMPLETED_V2_DESCRIPTOR = EVENT_BY_TYPE[
    AiEvaluationCompletedV2.DESCRIPTOR_TYPE
]
if (
    _AI_EVALUATION_COMPLETED_V2_DESCRIPTOR.schema_sha256
    != AiEvaluationCompletedV2.DATA_SCHEMA_SHA256
    or _AI_EVALUATION_COMPLETED_V2_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiEvaluationCompletedV2"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_EVALUATION_COMPLETED_V2_BINDING = EventRuntimeBinding(
    descriptor=_AI_EVALUATION_COMPLETED_V2_DESCRIPTOR,
    event_class=AiEvaluationCompletedV2,
    payload_schema_sha256=AiEvaluationCompletedV2.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiEvaluationCompletedV2,
)

_AI_RELEASE_DECISION_APPROVED_DESCRIPTOR = EVENT_BY_TYPE[
    AiReleaseDecisionApproved.DESCRIPTOR_TYPE
]
if (
    _AI_RELEASE_DECISION_APPROVED_DESCRIPTOR.schema_sha256
    != AiReleaseDecisionApproved.DATA_SCHEMA_SHA256
    or _AI_RELEASE_DECISION_APPROVED_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiReleaseDecisionApproved"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_RELEASE_DECISION_APPROVED_BINDING = EventRuntimeBinding(
    descriptor=_AI_RELEASE_DECISION_APPROVED_DESCRIPTOR,
    event_class=AiReleaseDecisionApproved,
    payload_schema_sha256=AiReleaseDecisionApproved.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiReleaseDecisionApproved,
)

_AI_RELEASE_DECISION_REVOKED_DESCRIPTOR = EVENT_BY_TYPE[
    AiReleaseDecisionRevoked.DESCRIPTOR_TYPE
]
if (
    _AI_RELEASE_DECISION_REVOKED_DESCRIPTOR.schema_sha256
    != AiReleaseDecisionRevoked.DATA_SCHEMA_SHA256
    or _AI_RELEASE_DECISION_REVOKED_DESCRIPTOR.python_class
    != "raos.domain.ai.events.AiReleaseDecisionRevoked"
):
    raise RuntimeError("ST0308_AI_EVENT_BINDING_INVALID")
_AI_RELEASE_DECISION_REVOKED_BINDING = EventRuntimeBinding(
    descriptor=_AI_RELEASE_DECISION_REVOKED_DESCRIPTOR,
    event_class=AiReleaseDecisionRevoked,
    payload_schema_sha256=AiReleaseDecisionRevoked.DATA_SCHEMA_SHA256,
    payload_validator=_validate_AiReleaseDecisionRevoked,
)

EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(
    {
        AiJobRequested: _AI_JOB_REQUESTED_BINDING,
        AiJobSucceeded: _AI_JOB_SUCCEEDED_BINDING,
        AiJobFailed: _AI_JOB_FAILED_BINDING,
        AiPolicyAssistCompleted: _AI_POLICY_ASSIST_COMPLETED_BINDING,
        AiEvaluationCompletedV2: _AI_EVALUATION_COMPLETED_V2_BINDING,
        AiReleaseDecisionApproved: _AI_RELEASE_DECISION_APPROVED_BINDING,
        AiReleaseDecisionRevoked: _AI_RELEASE_DECISION_REVOKED_BINDING,
    }
)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final[MappingProxyType[str, EventRuntimeBinding]] = (
    MappingProxyType(
        {
            AiJobRequested.DESCRIPTOR_TYPE: _AI_JOB_REQUESTED_BINDING,
            AiJobSucceeded.DESCRIPTOR_TYPE: _AI_JOB_SUCCEEDED_BINDING,
            AiJobFailed.DESCRIPTOR_TYPE: _AI_JOB_FAILED_BINDING,
            AiPolicyAssistCompleted.DESCRIPTOR_TYPE: _AI_POLICY_ASSIST_COMPLETED_BINDING,
            AiEvaluationCompletedV2.DESCRIPTOR_TYPE: _AI_EVALUATION_COMPLETED_V2_BINDING,
            AiReleaseDecisionApproved.DESCRIPTOR_TYPE: _AI_RELEASE_DECISION_APPROVED_BINDING,
            AiReleaseDecisionRevoked.DESCRIPTOR_TYPE: _AI_RELEASE_DECISION_REVOKED_BINDING,
        }
    )
)
EVENT_CLASS_DESCRIPTORS: Final[MappingProxyType[type[object], EventDescriptor]] = (
    MappingProxyType(
        {
            event_class: binding.descriptor
            for event_class, binding in EVENT_RUNTIME_BINDINGS_BY_CLASS.items()
        }
    )
)


__all__ = [
    "EVENT_CLASS_DESCRIPTORS",
    "EVENT_RUNTIME_BINDINGS_BY_CLASS",
    "EVENT_RUNTIME_BINDINGS_BY_TYPE",
    "AiJobRequested",
    "AiJobSucceeded",
    "AiJobFailed",
    "AiPolicyAssistCompleted",
    "AiEvaluationCompletedV2",
    "AiReleaseDecisionApproved",
    "AiReleaseDecisionRevoked",
]
