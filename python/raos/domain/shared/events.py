"""Closed ST-0308 Domain-event registry and immutable envelope values.

Only the eighteen hash-bound event classes in ``EVENT_DESCRIPTORS`` can cross
the Outbox inward port.  Event type, schema, version, producer, aggregate root,
and persisted version source are class-owned constants, never caller strings.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from functools import cache
from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import RFC_4122, UUID

from raos.domain.shared.identity import EntityId, require_uuid
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import AggregateVersion


class EventClassification(str, Enum):
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"


class AggregateVersionSource(str, Enum):
    POST_INSERT_LOCK_VERSION_0 = "POST_INSERT_LOCK_VERSION_0"
    POST_CAS_LOCK_VERSION = "POST_CAS_LOCK_VERSION"
    PERSISTED_VERSION_NO = "PERSISTED_VERSION_NO"


@dataclass(frozen=True, slots=True)
class EventDescriptor:
    event_type: str
    schema_path: str
    schema_sha256: str
    event_version: int
    producer: str
    classification: EventClassification
    aggregate_type: str
    version_source: AggregateVersionSource
    owning_method: str
    required_data: tuple[str, ...]
    python_class: str


EVENT_DESCRIPTORS: Final[tuple[EventDescriptor, ...]] = (
    EventDescriptor(
        "jp.raos.ops.job_requested.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ops-job-requested-v1.schema.json",
        "c10f9773b621000705684bec152bdc8f037c46b688f390216effa2872ab8e671",
        1,
        "ops",
        EventClassification.INTERNAL,
        "ops.job",
        AggregateVersionSource.POST_INSERT_LOCK_VERSION_0,
        "JobRepository.add",
        ("job_id", "job_type", "queue", "available_at"),
        "raos.domain.ops.events.OpsJobRequested",
    ),
    EventDescriptor(
        "jp.raos.portfolio.action_candidate_decided.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-portfolio-action-candidate-decided-v1.schema.json",
        "3ae2f73207c27bd019d9fd55e0d24c794e4a0d711265af902c4d38ec63bf2528",
        1,
        "portfolio",
        EventClassification.INTERNAL,
        "portfolio.action_candidate",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "ActionCandidateRepository.save",
        ("action_candidate_id", "decision", "decided_at"),
        "raos.domain.portfolio.events.PortfolioActionCandidateDecided",
    ),
    EventDescriptor(
        "jp.raos.catalog.offer_observed.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-offer-observed-v1.schema.json",
        "c3e38d1c0cf17c475ca5d70a922b4ddcdfcdc8b2e381750a2b32c21fe1622f04",
        1,
        "catalog",
        EventClassification.INTERNAL,
        "catalog.offer",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "OfferRepository.append_observations",
        (
            "offer_id",
            "observation_types",
            "observed_at",
            "freshness_status",
            "changed_fields",
        ),
        "raos.domain.catalog.events.CatalogOfferObserved",
    ),
    EventDescriptor(
        "jp.raos.catalog.offer_unavailable.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-offer-unavailable-v1.schema.json",
        "d8a2df0bfcdb0056a3056d95350a77697a6f8659daea5e264ca9ad13487175b7",
        1,
        "catalog",
        EventClassification.INTERNAL,
        "catalog.offer",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "OfferRepository.append_observations",
        ("offer_id", "reason_code", "observed_at", "alternative_search_required"),
        "raos.domain.catalog.events.CatalogOfferUnavailable",
    ),
    EventDescriptor(
        "jp.raos.catalog.affiliate_link_invalid.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-catalog-affiliate-link-invalid-v1.schema.json",
        "0787d7d44ef70f0a002be9c8ed4768ee19f6f833e5dd81e3399436593f72940a",
        1,
        "catalog",
        EventClassification.INTERNAL,
        "catalog.offer",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "OfferRepository.append_observations",
        ("offer_id", "link_observation_id", "risk_code", "cta_disabled"),
        "raos.domain.catalog.events.CatalogAffiliateLinkInvalid",
    ),
    EventDescriptor(
        "jp.raos.editorial.article_plan_approved.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-plan-approved-v1.schema.json",
        "831be3d8bc7713a9fada02b9d06792dbdf4b1def00f360aebe7d8a0307260d2b",
        1,
        "editorial",
        EventClassification.INTERNAL,
        "editorial.article_plan",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "ArticlePlanRepository.save",
        ("article_plan_id", "site_id", "category_id", "approved_at"),
        "raos.domain.editorial.events.EditorialArticlePlanApproved",
    ),
    EventDescriptor(
        "jp.raos.editorial.article_created.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-created-v1.schema.json",
        "b257eed50005023f07ad252b6676e41f8b1deb41090014a405285947a8e1fbde",
        1,
        "editorial",
        EventClassification.INTERNAL,
        "editorial.article",
        AggregateVersionSource.POST_INSERT_LOCK_VERSION_0,
        "ArticleRepository.add",
        ("article_id", "article_plan_id", "site_id", "article_type"),
        "raos.domain.editorial.events.EditorialArticleCreated",
    ),
    EventDescriptor(
        "jp.raos.editorial.draft_generated.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-draft-generated-v1.schema.json",
        "6128ccaac3fabca2bfc4cfa4c1047c424124e353f5115495431b087b9e9a7012",
        1,
        "editorial",
        EventClassification.INTERNAL,
        "editorial.article_version",
        AggregateVersionSource.POST_INSERT_LOCK_VERSION_0,
        "ArticleRepository.add_version",
        (
            "article_id",
            "article_version_id",
            "article_plan_id",
            "source_packet_version_id",
            "body_sha256",
            "ai_job_id",
        ),
        "raos.domain.editorial.events.EditorialDraftGenerated",
    ),
    EventDescriptor(
        "jp.raos.editorial.article_version_submitted.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-editorial-article-version-submitted-v1.schema.json",
        "c1cd3bcc629575880f98091c721416c98cf24062858f3750ed426058b324808d",
        1,
        "editorial",
        EventClassification.INTERNAL,
        "editorial.article_version",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "ArticleRepository.save_version",
        ("article_version_id", "article_id", "submitted_at", "quality_check_run_id"),
        "raos.domain.editorial.events.EditorialArticleVersionSubmitted",
    ),
    EventDescriptor(
        "jp.raos.evidence.source_snapshot_captured.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-evidence-source-snapshot-captured-v1.schema.json",
        "f00bb94cea83ca3aede34fb6fe4531121ad356896414f3dddaa435dc8b104e93",
        1,
        "evidence",
        EventClassification.INTERNAL,
        "evidence.source",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "SourceSnapshotRepository.append",
        (
            "source_snapshot_id",
            "source_id",
            "artifact",
            "validation_status",
            "acquired_at",
        ),
        "raos.domain.evidence.events.EvidenceSourceSnapshotCaptured",
    ),
    EventDescriptor(
        "jp.raos.ai.job_requested.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-requested-v1.schema.json",
        "9937ac30df245d120ccf06aaaf406a8b29cdc9773307e9c9c61d9fc025abd42c",
        1,
        "ai",
        EventClassification.INTERNAL,
        "ai.ai_job",
        AggregateVersionSource.POST_INSERT_LOCK_VERSION_0,
        "AiJobRepository.add",
        (
            "ai_job_id",
            "ops_job_id",
            "task_code",
            "source_packet_version_id",
            "max_cost_jpy",
        ),
        "raos.domain.ai.events.AiJobRequested",
    ),
    EventDescriptor(
        "jp.raos.ai.job_succeeded.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-succeeded-v1.schema.json",
        "670dbd4036129bb41284eafa6fb8809b260593f9aab4bc270384509d41d2057a",
        1,
        "ai",
        EventClassification.INTERNAL,
        "ai.ai_job",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "AiJobRepository.transition",
        (
            "ai_job_id",
            "ops_job_id",
            "task_code",
            "output_artifact",
            "usage_cost_jpy",
            "validation_passed",
        ),
        "raos.domain.ai.events.AiJobSucceeded",
    ),
    EventDescriptor(
        "jp.raos.ai.job_failed.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-job-failed-v1.schema.json",
        "5cb07491fe735a9e1724b7539f50763928a32befb96627d642c1ad30e39fa2c7",
        1,
        "ai",
        EventClassification.INTERNAL,
        "ai.ai_job",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "AiJobRepository.transition",
        (
            "ai_job_id",
            "ops_job_id",
            "task_code",
            "error_class",
            "retryable",
            "attempt_count",
        ),
        "raos.domain.ai.events.AiJobFailed",
    ),
    EventDescriptor(
        "jp.raos.ai.policy_assist_completed.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-policy-assist-completed-v1.schema.json",
        "689bd2b267e83d0b9b46acc884526ea87a051bf7bde57221d14893ea13d27033",
        1,
        "ai",
        EventClassification.INTERNAL,
        "ai.ai_job",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "AiJobRepository.transition",
        (
            "quality_check_run_id",
            "ai_job_id",
            "output_artifact",
            "finding_candidate_count",
        ),
        "raos.domain.ai.events.AiPolicyAssistCompleted",
    ),
    EventDescriptor(
        "jp.raos.ai.evaluation_completed.v2",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-evaluation-completed-v2.schema.json",
        "49d495fd47a2638cd6c008fa04823617af784b7991dad65d27f2c724c0725f39",
        2,
        "ai",
        EventClassification.CONFIDENTIAL,
        "ai.evaluation_run",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "EvaluationRunRepository.transition",
        (
            "evaluation_run_id",
            "suite_id",
            "suite_version",
            "dataset_version_id",
            "baseline_evaluation_run_id",
            "task_definition_id",
            "prompt_version_id",
            "model_route_version_id",
            "resolved_model_id",
            "output_schema_version_id",
            "policy_bundle_version_id",
            "code_git_sha",
            "passed",
            "result_manifest_sha256",
            "completed_at",
        ),
        "raos.domain.ai.events.AiEvaluationCompletedV2",
    ),
    EventDescriptor(
        "jp.raos.ai.release_decision_approved.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-release-decision-approved-v1.schema.json",
        "947685c9cf295997629fe0acd27df88e0f78a581ca146dea445948d9f3632fa4",
        1,
        "ai",
        EventClassification.CONFIDENTIAL,
        "ai.release_decision",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "ReleaseDecisionRepository.transition",
        (
            "release_decision_id",
            "release_approval_id",
            "task_definition_id",
            "prompt_version_id",
            "model_route_version_id",
            "resolved_model_id",
            "policy_bundle_version_id",
            "dataset_version_id",
            "output_schema_version_id",
            "evaluation_run_id",
            "judge_calibration_id",
            "code_git_sha",
            "phase",
            "decision_manifest_sha256",
            "rollback_strategy",
            "rollback_release_decision_id",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "canary_evidence_sha256",
            "canary_monitoring_sha256",
            "canary_started_at",
            "canary_started_txid",
            "canary_completed_at",
            "canary_completed_txid",
            "approved_at",
            "aggregate_version",
        ),
        "raos.domain.ai.events.AiReleaseDecisionApproved",
    ),
    EventDescriptor(
        "jp.raos.ai.release_decision_revoked.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-ai-release-decision-revoked-v1.schema.json",
        "c1a671dd2849a92c4078f726aa82f720be6349e67f123df1dd35d5455f77b7a3",
        1,
        "ai",
        EventClassification.CONFIDENTIAL,
        "ai.release_decision",
        AggregateVersionSource.POST_CAS_LOCK_VERSION,
        "ReleaseDecisionRepository.transition",
        (
            "release_decision_id",
            "task_definition_id",
            "reason_code",
            "rollback_strategy",
            "rollback_release_decision_id",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "canary_completed_txid",
            "revoked_at",
            "aggregate_version",
        ),
        "raos.domain.ai.events.AiReleaseDecisionRevoked",
    ),
    EventDescriptor(
        "jp.raos.policy.policy_bundle_activated.v1",
        "contracts/raos-v0.4/contracts/schemas/events/jp-raos-policy-policy-bundle-activated-v1.schema.json",
        "cb6c7233454a08ab0eea46e12fd4ff353205763393853f16d812bfe0cadbd461",
        1,
        "policy",
        EventClassification.INTERNAL,
        "policy.policy_bundle",
        AggregateVersionSource.PERSISTED_VERSION_NO,
        "PolicyBundleRepository.transition",
        (
            "policy_bundle_id",
            "bundle_code",
            "version_no",
            "bundle_sha256",
            "effective_from",
        ),
        "raos.domain.policy.events.PolicyPolicyBundleActivated",
    ),
)

EVENT_BY_TYPE: Final = MappingProxyType(
    {descriptor.event_type: descriptor for descriptor in EVENT_DESCRIPTORS}
)
if len(EVENT_BY_TYPE) != 18:
    raise RuntimeError("ST0308_EVENT_REGISTRY_INVALID")

EXCLUDED_EVENT_ROOTS: Final = (
    "policy.finding",
    "policy.waiver",
    "policy.quality_check_run",
    "policy.gate_decision",
    "evidence.source_packet_version",
    "catalog.ingestion_request",
    "catalog.grouping_decision",
    "portfolio.opportunity_assessment",
    "evidence.fact_or_claim",
)


def _invalid() -> NoReturn:
    raise ValueError("INVALID_DOMAIN_EVENT") from None


@dataclass(frozen=True, slots=True, repr=False)
class DomainEvent:
    """Sealed base; concrete module-owned subclasses fix one descriptor."""

    DESCRIPTOR_TYPE: ClassVar[str] = ""
    event_id: UUID
    aggregate_id: EntityId
    aggregate_version: AggregateVersion
    occurred_at: datetime
    causation_id: UUID | None
    data: FrozenJsonObject

    def __post_init__(self) -> None:
        if type(self) is DomainEvent:
            _invalid()
        binding = _runtime_binding_for_exact_event(self)
        descriptor = binding.descriptor
        if (
            type(self.event_id) is not UUID
            or self.event_id.version != 7
            or self.event_id.variant != RFC_4122
        ):
            _invalid()
        if type(self.aggregate_id) is EntityId or not isinstance(
            self.aggregate_id, EntityId
        ):
            _invalid()
        if type(self.aggregate_version) is not AggregateVersion:
            _invalid()
        if (
            descriptor.version_source
            is AggregateVersionSource.POST_INSERT_LOCK_VERSION_0
        ):
            if self.aggregate_version.value != 0:
                _invalid()
        elif descriptor.version_source is AggregateVersionSource.PERSISTED_VERSION_NO:
            if self.aggregate_version.value < 1:
                _invalid()
        if (
            type(self.occurred_at) is not datetime
            or self.occurred_at.tzinfo is not timezone.utc
            or self.occurred_at.fold
        ):
            _invalid()
        if self.causation_id is not None:
            require_uuid(self.causation_id)
        if type(self.data) is not FrozenJsonObject:
            _invalid()
        if tuple(self.data) != tuple(sorted(descriptor.required_data)):
            _invalid()
        binding.validate_payload(self.data, self.aggregate_id.value)

    @property
    def descriptor(self) -> EventDescriptor:
        return _descriptor_for_exact_event(self)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"


type EventPayloadValidator = Callable[[FrozenJsonObject, UUID], None]


@dataclass(frozen=True, slots=True)
class EventRuntimeBinding:
    """One immutable class/descriptor/payload-validator authority tuple."""

    descriptor: EventDescriptor
    event_class: type[DomainEvent]
    payload_schema_sha256: str
    payload_validator: EventPayloadValidator

    def __post_init__(self) -> None:
        if (
            type(self.descriptor) is not EventDescriptor
            or not isinstance(self.event_class, type)
            or self.event_class is DomainEvent
            or not issubclass(self.event_class, DomainEvent)
            or type(self.payload_schema_sha256) is not str
            or self.payload_schema_sha256 != self.descriptor.schema_sha256
            or getattr(self.event_class, "DESCRIPTOR_TYPE", None)
            != self.descriptor.event_type
            or getattr(self.event_class, "DATA_SCHEMA_SHA256", None)
            != self.payload_schema_sha256
            or not callable(self.payload_validator)
        ):
            raise RuntimeError("ST0308_EVENT_RUNTIME_BINDING_INVALID") from None

    def validate_payload(
        self,
        payload: FrozenJsonObject,
        aggregate_id: UUID,
    ) -> None:
        if type(payload) is not FrozenJsonObject:
            _invalid()
        require_uuid(aggregate_id)
        try:
            self.payload_validator(payload, aggregate_id)
        except KeyError, OverflowError, TypeError, ValueError:
            _invalid()


@cache
def _runtime_bindings_by_class() -> MappingProxyType[type[object], EventRuntimeBinding]:
    """Load all eight module-owned registries once without creating a cycle."""

    from raos.domain.ai.events import (
        EVENT_RUNTIME_BINDINGS_BY_CLASS as AI_BINDINGS,
    )
    from raos.domain.editorial.events import (
        EVENT_RUNTIME_BINDINGS_BY_CLASS as EDITORIAL_BINDINGS,
    )
    from raos.domain.evidence.events import (
        EVENT_RUNTIME_BINDINGS_BY_CLASS as EVIDENCE_BINDINGS,
    )
    from raos.domain.ops.events import EVENT_RUNTIME_BINDINGS_BY_CLASS as OPS_BINDINGS
    from raos.domain.policy.events import (
        EVENT_RUNTIME_BINDINGS_BY_CLASS as POLICY_BINDINGS,
    )

    merged = {
        **OPS_BINDINGS,
        **EVIDENCE_BINDINGS,
        **EDITORIAL_BINDINGS,
        **AI_BINDINGS,
        **POLICY_BINDINGS,
    }
    event_types = {binding.descriptor.event_type for binding in merged.values()}
    if len(merged) != 18 or event_types != set(EVENT_BY_TYPE):
        raise RuntimeError("ST0308_EVENT_RUNTIME_BINDING_INVALID") from None
    return MappingProxyType(merged)


@cache
def _runtime_bindings_by_type() -> MappingProxyType[str, EventRuntimeBinding]:
    by_type = {
        binding.descriptor.event_type: binding
        for binding in _runtime_bindings_by_class().values()
    }
    if len(by_type) != 18:
        raise RuntimeError("ST0308_EVENT_RUNTIME_BINDING_INVALID") from None
    return MappingProxyType(by_type)


def _runtime_binding_for_exact_event(event: object) -> EventRuntimeBinding:
    """Resolve only module-owned runtime classes through the closed registry."""

    binding = _runtime_bindings_by_class().get(type(event))
    if (
        type(binding) is not EventRuntimeBinding
        or binding.event_class is not type(event)
        or EVENT_BY_TYPE.get(binding.descriptor.event_type) is not binding.descriptor
    ):
        _invalid()
    return binding


def _descriptor_for_exact_event(event: object) -> EventDescriptor:
    return _runtime_binding_for_exact_event(event).descriptor


def require_allowed_event(event: object) -> DomainEvent:
    if not isinstance(event, DomainEvent):
        _invalid()
    _descriptor_for_exact_event(event)
    return event


def require_allowed_outbox_metadata(
    *,
    event_type: object,
    event_version: object,
    producer: object,
    aggregate_type: object,
    schema_sha256: object,
) -> EventDescriptor:
    """Require one exact hash-bound descriptor tuple for a stored Outbox row."""

    if type(event_type) is not str:
        _invalid()
    descriptor = EVENT_BY_TYPE.get(event_type)
    if (
        descriptor is None
        or type(event_version) is not int
        or event_version != descriptor.event_version
        or type(producer) is not str
        or producer != descriptor.producer
        or type(aggregate_type) is not str
        or aggregate_type != descriptor.aggregate_type
        or type(schema_sha256) is not str
        or schema_sha256 != descriptor.schema_sha256
    ):
        _invalid()
    return descriptor


def require_allowed_outbox_payload(
    *,
    event_type: object,
    event_version: object,
    producer: object,
    aggregate_type: object,
    aggregate_id: object,
    schema_sha256: object,
    payload: object,
) -> EventDescriptor:
    """Validate a stored payload through its exact hash-bound runtime binding."""

    descriptor = require_allowed_outbox_metadata(
        event_type=event_type,
        event_version=event_version,
        producer=producer,
        aggregate_type=aggregate_type,
        schema_sha256=schema_sha256,
    )
    if type(event_type) is not str:
        _invalid()
    binding = _runtime_bindings_by_type().get(event_type)
    if (
        type(binding) is not EventRuntimeBinding
        or binding.descriptor is not descriptor
        or binding.payload_schema_sha256 != schema_sha256
        or type(aggregate_id) is not UUID
        or type(payload) is not FrozenJsonObject
    ):
        _invalid()
    binding.validate_payload(payload, aggregate_id)
    return descriptor


__all__ = [
    "AggregateVersionSource",
    "DomainEvent",
    "EVENT_BY_TYPE",
    "EVENT_DESCRIPTORS",
    "EXCLUDED_EVENT_ROOTS",
    "EventClassification",
    "EventDescriptor",
    "EventPayloadValidator",
    "EventRuntimeBinding",
    "require_allowed_event",
    "require_allowed_outbox_metadata",
    "require_allowed_outbox_payload",
]
