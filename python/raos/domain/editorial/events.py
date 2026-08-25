"""Hash-bound EDITORIAL event classes admitted by the ST-0308 registry."""

from __future__ import annotations

import re
from types import MappingProxyType
from typing import ClassVar, Final, NoReturn
from uuid import UUID

from raos.domain.editorial.ids import (
    ArticleId,
    ArticlePlanId,
    ArticleVersionId,
)
from raos.domain.shared.events import (
    DomainEvent,
    EVENT_BY_TYPE,
    EventDescriptor,
    EventRuntimeBinding,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import require_rfc3339_date_time


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


def _validate_EditorialArticlePlanApproved(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != ("approved_at", "article_plan_id", "category_id", "site_id")
    ):
        _invalid_payload()
    parsed_article_plan_id = _uuid(payload["article_plan_id"])
    if parsed_article_plan_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["site_id"])
    _uuid(payload["category_id"])
    try:
        require_rfc3339_date_time(payload["approved_at"])
    except ValueError:
        _invalid_payload()


class EditorialArticlePlanApproved(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.editorial.article_plan_approved.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "831be3d8bc7713a9fada02b9d06792dbdf4b1def00f360aebe7d8a0307260d2b"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ArticlePlanId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_EditorialArticleCreated(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != ("article_id", "article_plan_id", "article_type", "site_id")
    ):
        _invalid_payload()
    parsed_article_id = _uuid(payload["article_id"])
    if parsed_article_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["article_plan_id"])
    _uuid(payload["site_id"])
    if type(payload["article_type"]) is not str:
        _invalid_payload()


class EditorialArticleCreated(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.editorial.article_created.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "b257eed50005023f07ad252b6676e41f8b1deb41090014a405285947a8e1fbde"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ArticleId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_EditorialDraftGenerated(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != (
            "ai_job_id",
            "article_id",
            "article_plan_id",
            "article_version_id",
            "body_sha256",
            "source_packet_version_id",
        )
    ):
        _invalid_payload()
    _uuid(payload["article_id"])
    parsed_article_version_id = _uuid(payload["article_version_id"])
    if parsed_article_version_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["article_plan_id"])
    _uuid(payload["source_packet_version_id"])
    body_sha256 = payload["body_sha256"]
    if (
        type(body_sha256) is not str
        or re.fullmatch("^[0-9a-f]{64}$", body_sha256) is None
    ):
        _invalid_payload()
    _uuid(payload["ai_job_id"])


class EditorialDraftGenerated(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.editorial.draft_generated.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "6128ccaac3fabca2bfc4cfa4c1047c424124e353f5115495431b087b9e9a7012"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ArticleVersionId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


def _validate_EditorialArticleVersionSubmitted(
    payload: FrozenJsonObject,
    aggregate_id: UUID,
) -> None:
    if (
        type(payload) is not FrozenJsonObject
        or type(aggregate_id) is not UUID
        or tuple(payload)
        != ("article_id", "article_version_id", "quality_check_run_id", "submitted_at")
    ):
        _invalid_payload()
    parsed_article_version_id = _uuid(payload["article_version_id"])
    if parsed_article_version_id != aggregate_id:
        _invalid_payload()
    _uuid(payload["article_id"])
    try:
        require_rfc3339_date_time(payload["submitted_at"])
    except ValueError:
        _invalid_payload()
    _uuid(payload["quality_check_run_id"])


class EditorialArticleVersionSubmitted(DomainEvent):
    DESCRIPTOR_TYPE: ClassVar[str] = "jp.raos.editorial.article_version_submitted.v1"
    DATA_SCHEMA_SHA256: ClassVar[str] = (
        "c1cd3bcc629575880f98091c721416c98cf24062858f3750ed426058b324808d"
    )

    def __post_init__(self) -> None:
        if type(self.aggregate_id) is not ArticleVersionId:
            raise ValueError("INVALID_DOMAIN_EVENT") from None
        super().__post_init__()


_EDITORIAL_ARTICLE_PLAN_APPROVED_DESCRIPTOR = EVENT_BY_TYPE[
    EditorialArticlePlanApproved.DESCRIPTOR_TYPE
]
if (
    _EDITORIAL_ARTICLE_PLAN_APPROVED_DESCRIPTOR.schema_sha256
    != EditorialArticlePlanApproved.DATA_SCHEMA_SHA256
    or _EDITORIAL_ARTICLE_PLAN_APPROVED_DESCRIPTOR.python_class
    != "raos.domain.editorial.events.EditorialArticlePlanApproved"
):
    raise RuntimeError("ST0308_EDITORIAL_EVENT_BINDING_INVALID")
_EDITORIAL_ARTICLE_PLAN_APPROVED_BINDING = EventRuntimeBinding(
    descriptor=_EDITORIAL_ARTICLE_PLAN_APPROVED_DESCRIPTOR,
    event_class=EditorialArticlePlanApproved,
    payload_schema_sha256=EditorialArticlePlanApproved.DATA_SCHEMA_SHA256,
    payload_validator=_validate_EditorialArticlePlanApproved,
)

_EDITORIAL_ARTICLE_CREATED_DESCRIPTOR = EVENT_BY_TYPE[
    EditorialArticleCreated.DESCRIPTOR_TYPE
]
if (
    _EDITORIAL_ARTICLE_CREATED_DESCRIPTOR.schema_sha256
    != EditorialArticleCreated.DATA_SCHEMA_SHA256
    or _EDITORIAL_ARTICLE_CREATED_DESCRIPTOR.python_class
    != "raos.domain.editorial.events.EditorialArticleCreated"
):
    raise RuntimeError("ST0308_EDITORIAL_EVENT_BINDING_INVALID")
_EDITORIAL_ARTICLE_CREATED_BINDING = EventRuntimeBinding(
    descriptor=_EDITORIAL_ARTICLE_CREATED_DESCRIPTOR,
    event_class=EditorialArticleCreated,
    payload_schema_sha256=EditorialArticleCreated.DATA_SCHEMA_SHA256,
    payload_validator=_validate_EditorialArticleCreated,
)

_EDITORIAL_DRAFT_GENERATED_DESCRIPTOR = EVENT_BY_TYPE[
    EditorialDraftGenerated.DESCRIPTOR_TYPE
]
if (
    _EDITORIAL_DRAFT_GENERATED_DESCRIPTOR.schema_sha256
    != EditorialDraftGenerated.DATA_SCHEMA_SHA256
    or _EDITORIAL_DRAFT_GENERATED_DESCRIPTOR.python_class
    != "raos.domain.editorial.events.EditorialDraftGenerated"
):
    raise RuntimeError("ST0308_EDITORIAL_EVENT_BINDING_INVALID")
_EDITORIAL_DRAFT_GENERATED_BINDING = EventRuntimeBinding(
    descriptor=_EDITORIAL_DRAFT_GENERATED_DESCRIPTOR,
    event_class=EditorialDraftGenerated,
    payload_schema_sha256=EditorialDraftGenerated.DATA_SCHEMA_SHA256,
    payload_validator=_validate_EditorialDraftGenerated,
)

_EDITORIAL_ARTICLE_VERSION_SUBMITTED_DESCRIPTOR = EVENT_BY_TYPE[
    EditorialArticleVersionSubmitted.DESCRIPTOR_TYPE
]
if (
    _EDITORIAL_ARTICLE_VERSION_SUBMITTED_DESCRIPTOR.schema_sha256
    != EditorialArticleVersionSubmitted.DATA_SCHEMA_SHA256
    or _EDITORIAL_ARTICLE_VERSION_SUBMITTED_DESCRIPTOR.python_class
    != "raos.domain.editorial.events.EditorialArticleVersionSubmitted"
):
    raise RuntimeError("ST0308_EDITORIAL_EVENT_BINDING_INVALID")
_EDITORIAL_ARTICLE_VERSION_SUBMITTED_BINDING = EventRuntimeBinding(
    descriptor=_EDITORIAL_ARTICLE_VERSION_SUBMITTED_DESCRIPTOR,
    event_class=EditorialArticleVersionSubmitted,
    payload_schema_sha256=EditorialArticleVersionSubmitted.DATA_SCHEMA_SHA256,
    payload_validator=_validate_EditorialArticleVersionSubmitted,
)

EVENT_RUNTIME_BINDINGS_BY_CLASS: Final[
    MappingProxyType[type[object], EventRuntimeBinding]
] = MappingProxyType(
    {
        EditorialArticlePlanApproved: _EDITORIAL_ARTICLE_PLAN_APPROVED_BINDING,
        EditorialArticleCreated: _EDITORIAL_ARTICLE_CREATED_BINDING,
        EditorialDraftGenerated: _EDITORIAL_DRAFT_GENERATED_BINDING,
        EditorialArticleVersionSubmitted: _EDITORIAL_ARTICLE_VERSION_SUBMITTED_BINDING,
    }
)
EVENT_RUNTIME_BINDINGS_BY_TYPE: Final[MappingProxyType[str, EventRuntimeBinding]] = (
    MappingProxyType(
        {
            EditorialArticlePlanApproved.DESCRIPTOR_TYPE: _EDITORIAL_ARTICLE_PLAN_APPROVED_BINDING,
            EditorialArticleCreated.DESCRIPTOR_TYPE: _EDITORIAL_ARTICLE_CREATED_BINDING,
            EditorialDraftGenerated.DESCRIPTOR_TYPE: _EDITORIAL_DRAFT_GENERATED_BINDING,
            EditorialArticleVersionSubmitted.DESCRIPTOR_TYPE: _EDITORIAL_ARTICLE_VERSION_SUBMITTED_BINDING,
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
    "EditorialArticlePlanApproved",
    "EditorialArticleCreated",
    "EditorialDraftGenerated",
    "EditorialArticleVersionSubmitted",
]
