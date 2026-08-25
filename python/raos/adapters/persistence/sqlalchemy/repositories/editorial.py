"""Concrete scalar codecs and aggregate-specific SQLAlchemy repositories for EDITORIAL."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar, cast
from uuid import UUID

from sqlalchemy import Table, insert, or_, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable
from sqlalchemy.sql.elements import ColumnElement

import raos.adapters.persistence.sqlalchemy.mappers.editorial as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    aggregate_events_buffer,
    fail_session_operation,
    guard_repository_class,
    persistence_context,
    register_pending_events,
    stage_registered_events,
    transaction_timestamp,
)
from raos.domain.ai.ids import (
    AiJobId,
)
from raos.domain.catalog.ids import (
    CanonicalProductId,
    OfferId,
)
from raos.domain.editorial.aggregates import (
    Article,
    ArticleBlock,
    ArticleBlockProduct,
    ArticleDisclosureContext,
    ArticleLinkState,
    ArticleMethodologyBinding,
    ArticlePlan,
    ArticlePlanState,
    ArticleSlug,
    ArticleSlugState,
    ArticleState,
    ArticleTemplateVersion,
    ArticleTemplateVersionState,
    ArticleTypeVersion,
    ArticleTypeVersionState,
    ArticleVersion,
    ArticleVersionState,
    ComparisonAxis,
    ComparisonValue,
    ContentSchemaVersion,
    ContentSchemaVersionState,
    EditorialMethodologyVersion,
    EditorialMethodologyVersionState,
    MediaAsset,
    MediaAssetState,
    Recommendation,
    RecommendationRationale,
    RecommendationSet,
    ReviewComment,
    ReviewCommentState,
    SeoMetadataVersion,
    SeoMetadataVersionState,
    StructuredDataManifest,
)
from raos.domain.editorial.enums import (
    ArticleArticleType,
    ArticleBlockBlockType,
    ArticleBlockProductPlacementRole,
    ArticleLinkLinkType,
    ArticleLinkStatus,
    ArticlePlanArticleType,
    ArticlePlanStatus,
    ArticleSlugStatus,
    ArticleStatus,
    ArticleTemplateVersionStatus,
    ArticleTypeVersionStatus,
    ArticleVersionCreatedByActorType,
    ArticleVersionStatus,
    ComparisonAxisDataType,
    ComparisonValueValidationStatus,
    ContentSchemaVersionStatus,
    EditorialMethodologyVersionStatus,
    MediaAssetAssetClass,
    MediaAssetLicenseStatus,
    MediaAssetStatus,
    RecommendationRationaleRationaleType,
    RecommendationStatus,
    ReviewCommentStatus,
    SeoMetadataVersionStatus,
    StructuredDataManifestValidationStatus,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticleId,
    ArticleLinkId,
    ArticlePlanId,
    ArticleSlugId,
    ArticleTemplateVersionId,
    ArticleTypeVersionId,
    ArticleVersionId,
    ComparisonAxisId,
    ComparisonValueId,
    ContentSchemaVersionId,
    EditorialMethodologyVersionId,
    MediaAssetId,
    RecommendationId,
    RecommendationRationaleId,
    RecommendationSetId,
    ReviewCommentId,
    SeoMetadataVersionId,
    StructuredDataManifestId,
    ThreadId,
)
from raos.domain.editorial.values import (
    ArticleBlockContentJson,
    ArticlePlanBriefJson,
    ArticleTemplateVersionTemplateJson,
    ArticleTypeVersionContractJson,
    EditorialMethodologyVersionDefinitionJson,
    SeoMetadataVersionMetadataJson,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    SourceId,
    SourcePacketVersionId,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    ObjectArtifactId,
)
from raos.domain.portfolio.ids import (
    CategoryId,
    IntentClusterId,
    KeywordId,
    OpportunityAssessmentId,
    SiteId,
)
from raos.domain.shared.identity import (
    ActorId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    EmailAddress,
    GitCommitDigest,
    Sha256Digest,
    UriReference,
    YenMinor,
)
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


T = TypeVar("T")


def _is_exact_tuple(value: object) -> bool:
    return type(value) is tuple


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _context_principal_id(session: Session) -> PrincipalId:
    """Resolve an actor only from the immutable transaction context."""

    actor_id = persistence_context(session).actor.actor_id
    if actor_id is None:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    return PrincipalId(actor_id)


def _context_approval(
    session: Session,
    principal_id: PrincipalId | None,
    approved_at: AwareUtcDateTime | None,
) -> tuple[PrincipalId, AwareUtcDateTime]:
    principal = _context_principal_id(session)
    at = transaction_timestamp(session)
    if principal_id != principal or approved_at != at:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    return principal, at


def _context_time(
    session: Session,
    proposed: AwareUtcDateTime | None,
) -> AwareUtcDateTime:
    at = transaction_timestamp(session)
    if proposed != at:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    return at


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = cast(object, TABLES_BY_RELATION[relation])
    except ImportError, KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if not isinstance(table, Table) or table.fullname != relation:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return table


def _shape(row: Mapping[str, object], columns: tuple[str, ...]) -> None:
    if frozenset(row) != frozenset(columns) or len(row) != len(columns):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _exact(row: Mapping[str, object], key: str, expected: type[T]) -> T:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: Mapping[str, object], key: str) -> FrozenJsonObject:
    value = cast(dict[str, object], _exact(row, key, dict))
    try:
        return FrozenJsonObject.from_mapping(value)
    except ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _string_array(row: Mapping[str, object], key: str) -> tuple[str, ...]:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if type(value) not in {list, tuple}:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    items = cast(list[object] | tuple[object, ...], value)
    if any(type(item) is not str for item in items):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return tuple(cast(str, item) for item in items)


def _encode_scalar(value: object) -> object:
    if value is None or type(value) in {str, int, bool, Decimal, date}:
        return value
    if isinstance(value, EntityId):
        return value.value
    if isinstance(value, Enum):
        return value.value
    if type(value) is AwareUtcDateTime:
        return value.value
    if type(value) in {
        AggregateVersion,
        YenMinor,
        Sha256Digest,
        GitCommitDigest,
        EmailAddress,
        UriReference,
    }:
        return cast(
            AggregateVersion
            | YenMinor
            | Sha256Digest
            | GitCommitDigest
            | EmailAddress
            | UriReference,
            value,
        ).value
    if _is_exact_tuple(value):
        items = cast(tuple[object, ...], value)
        if all(type(item) is str for item in items):
            return [cast(str, item) for item in items]
    if type(value) in {
        ArticleBlockContentJson,
        ArticlePlanBriefJson,
        ArticleTemplateVersionTemplateJson,
        ArticleTypeVersionContractJson,
        EditorialMethodologyVersionDefinitionJson,
        SeoMetadataVersionMetadataJson,
    }:
        wrapped = cast(
            ArticleBlockContentJson
            | ArticlePlanBriefJson
            | ArticleTemplateVersionTemplateJson
            | ArticleTypeVersionContractJson
            | EditorialMethodologyVersionDefinitionJson
            | SeoMetadataVersionMetadataJson,
            value,
        )
        return json.loads(canonical_json_bytes(wrapped.value))
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encoded(
    columns: tuple[str, ...],
    values: tuple[object, ...],
) -> dict[str, object]:
    if len(columns) != len(values):
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return {
        column: _encode_scalar(value)
        for column, value in zip(columns, values, strict=True)
    }


def _execute_one(
    session: Session,
    statement: Executable,
) -> Mapping[str, object] | None:
    try:
        return cast(
            Mapping[str, object] | None,
            session.execute(statement).mappings().one_or_none(),
        )
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _execute_many(
    session: Session,
    statement: Executable,
) -> tuple[Mapping[str, object], ...]:
    try:
        return cast(
            tuple[Mapping[str, object], ...],
            tuple(session.execute(statement).mappings()),
        )
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _execute(session: Session, statement: Executable) -> None:
    try:
        session.execute(statement)
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _decode_editorial_article(row: Mapping[str, object]) -> ArticleState:
    columns = (
        "id",
        "display_id",
        "site_id",
        "article_plan_id",
        "article_type",
        "status",
        "current_version_id",
        "published_version_id",
        "archived_at",
        "archive_reason",
        "created_at",
        "updated_at",
        "lock_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_from_row(
            id=ArticleId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            article_plan_id=ArticlePlanId(_exact(row, "article_plan_id", UUID)),
            article_type=ArticleArticleType(_exact(row, "article_type", str)),
            status=ArticleStatus(_exact(row, "status", str)),
            current_version_id=(
                None
                if row["current_version_id"] is None
                else ArticleVersionId(_exact(row, "current_version_id", UUID))
            ),
            published_version_id=(
                None
                if row["published_version_id"] is None
                else ArticleVersionId(_exact(row, "published_version_id", UUID))
            ),
            archived_at=(
                None
                if row["archived_at"] is None
                else AwareUtcDateTime(_exact(row, "archived_at", datetime))
            ),
            archive_reason=(
                None
                if row["archive_reason"] is None
                else _exact(row, "archive_reason", str)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article(value: ArticleState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_id",
            "article_plan_id",
            "article_type",
            "status",
            "current_version_id",
            "published_version_id",
            "archived_at",
            "archive_reason",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_editorial_article_to_row(value),
    )


def _decode_editorial_article_block(row: Mapping[str, object]) -> ArticleBlock:
    columns = (
        "id",
        "article_version_id",
        "block_key",
        "block_type",
        "position",
        "heading_level",
        "content",
        "plain_text",
        "content_sha256",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_block_from_row(
            id=ArticleBlockId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            block_key=_exact(row, "block_key", str),
            block_type=ArticleBlockBlockType(_exact(row, "block_type", str)),
            position=_exact(row, "position", int),
            heading_level=(
                None
                if row["heading_level"] is None
                else _exact(row, "heading_level", int)
            ),
            content=ArticleBlockContentJson(_json_object(row, "content")),
            plain_text=_exact(row, "plain_text", str),
            content_sha256=Sha256Digest(_exact(row, "content_sha256", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_block(value: ArticleBlock) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "block_key",
            "block_type",
            "position",
            "heading_level",
            "content",
            "plain_text",
            "content_sha256",
            "created_at",
        ),
        domain_mappers.map_editorial_article_block_to_row(value),
    )


def _decode_editorial_article_block_product(
    row: Mapping[str, object],
) -> ArticleBlockProduct:
    columns = (
        "article_block_id",
        "product_id",
        "offer_id",
        "placement_role",
        "position",
        "placement_id",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_block_product_from_row(
            article_block_id=ArticleBlockId(_exact(row, "article_block_id", UUID)),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            offer_id=(
                None
                if row["offer_id"] is None
                else OfferId(_exact(row, "offer_id", UUID))
            ),
            placement_role=ArticleBlockProductPlacementRole(
                _exact(row, "placement_role", str)
            ),
            position=_exact(row, "position", int),
            placement_id=_exact(row, "placement_id", str),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_block_product(
    value: ArticleBlockProduct,
) -> dict[str, object]:
    return _encoded(
        (
            "article_block_id",
            "product_id",
            "offer_id",
            "placement_role",
            "position",
            "placement_id",
            "created_at",
        ),
        domain_mappers.map_editorial_article_block_product_to_row(value),
    )


def _decode_editorial_article_disclosure_context(
    row: Mapping[str, object],
) -> ArticleDisclosureContext:
    columns = (
        "article_version_id",
        "affiliate_relationship",
        "material_benefit_relationship",
        "benefit_types",
        "disclosure_policy_version",
        "additional_disclosure_text",
        "reviewed_by_principal_id",
        "reviewed_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_disclosure_context_from_row(
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            affiliate_relationship=_exact(row, "affiliate_relationship", bool),
            material_benefit_relationship=_exact(
                row, "material_benefit_relationship", bool
            ),
            benefit_types=_string_array(row, "benefit_types"),
            disclosure_policy_version=_exact(row, "disclosure_policy_version", str),
            additional_disclosure_text=(
                None
                if row["additional_disclosure_text"] is None
                else _exact(row, "additional_disclosure_text", str)
            ),
            reviewed_by_principal_id=(
                None
                if row["reviewed_by_principal_id"] is None
                else PrincipalId(_exact(row, "reviewed_by_principal_id", UUID))
            ),
            reviewed_at=(
                None
                if row["reviewed_at"] is None
                else AwareUtcDateTime(_exact(row, "reviewed_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_disclosure_context(
    value: ArticleDisclosureContext,
) -> dict[str, object]:
    return _encoded(
        (
            "article_version_id",
            "affiliate_relationship",
            "material_benefit_relationship",
            "benefit_types",
            "disclosure_policy_version",
            "additional_disclosure_text",
            "reviewed_by_principal_id",
            "reviewed_at",
            "created_at",
        ),
        domain_mappers.map_editorial_article_disclosure_context_to_row(value),
    )


def _decode_editorial_article_link(row: Mapping[str, object]) -> ArticleLinkState:
    columns = (
        "id",
        "from_article_id",
        "to_article_id",
        "link_type",
        "anchor_text",
        "source_block_key",
        "status",
        "reason",
        "created_at",
        "updated_at",
        "lock_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_link_from_row(
            id=ArticleLinkId(_exact(row, "id", UUID)),
            from_article_id=ArticleId(_exact(row, "from_article_id", UUID)),
            to_article_id=ArticleId(_exact(row, "to_article_id", UUID)),
            link_type=ArticleLinkLinkType(_exact(row, "link_type", str)),
            anchor_text=(
                None if row["anchor_text"] is None else _exact(row, "anchor_text", str)
            ),
            source_block_key=(
                None
                if row["source_block_key"] is None
                else _exact(row, "source_block_key", str)
            ),
            status=ArticleLinkStatus(_exact(row, "status", str)),
            reason=(None if row["reason"] is None else _exact(row, "reason", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_link(value: ArticleLinkState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "from_article_id",
            "to_article_id",
            "link_type",
            "anchor_text",
            "source_block_key",
            "status",
            "reason",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_editorial_article_link_to_row(value),
    )


def _decode_editorial_article_methodology_binding(
    row: Mapping[str, object],
) -> ArticleMethodologyBinding:
    columns = (
        "article_version_id",
        "methodology_version_id",
        "candidate_universe_artifact_id",
        "candidate_universe_sha256",
        "bound_at",
        "bound_by_principal_id",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_methodology_binding_from_row(
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            methodology_version_id=EditorialMethodologyVersionId(
                _exact(row, "methodology_version_id", UUID)
            ),
            candidate_universe_artifact_id=ObjectArtifactId(
                _exact(row, "candidate_universe_artifact_id", UUID)
            ),
            candidate_universe_sha256=Sha256Digest(
                _exact(row, "candidate_universe_sha256", str)
            ),
            bound_at=AwareUtcDateTime(_exact(row, "bound_at", datetime)),
            bound_by_principal_id=PrincipalId(
                _exact(row, "bound_by_principal_id", UUID)
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_methodology_binding(
    value: ArticleMethodologyBinding,
) -> dict[str, object]:
    return _encoded(
        (
            "article_version_id",
            "methodology_version_id",
            "candidate_universe_artifact_id",
            "candidate_universe_sha256",
            "bound_at",
            "bound_by_principal_id",
        ),
        domain_mappers.map_editorial_article_methodology_binding_to_row(value),
    )


def _decode_editorial_article_plan(row: Mapping[str, object]) -> ArticlePlanState:
    columns = (
        "id",
        "display_id",
        "site_id",
        "category_id",
        "intent_cluster_id",
        "primary_keyword_id",
        "article_type",
        "working_title",
        "objective",
        "status",
        "priority",
        "opportunity_assessment_id",
        "created_by_principal_id",
        "approved_by_principal_id",
        "approved_at",
        "brief",
        "created_at",
        "updated_at",
        "lock_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_plan_from_row(
            id=ArticlePlanId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            category_id=CategoryId(_exact(row, "category_id", UUID)),
            intent_cluster_id=IntentClusterId(_exact(row, "intent_cluster_id", UUID)),
            primary_keyword_id=KeywordId(_exact(row, "primary_keyword_id", UUID)),
            article_type=ArticlePlanArticleType(_exact(row, "article_type", str)),
            working_title=_exact(row, "working_title", str),
            objective=_exact(row, "objective", str),
            status=ArticlePlanStatus(_exact(row, "status", str)),
            priority=_exact(row, "priority", int),
            opportunity_assessment_id=(
                None
                if row["opportunity_assessment_id"] is None
                else OpportunityAssessmentId(
                    _exact(row, "opportunity_assessment_id", UUID)
                )
            ),
            created_by_principal_id=PrincipalId(
                _exact(row, "created_by_principal_id", UUID)
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            brief=ArticlePlanBriefJson(_json_object(row, "brief")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_plan(value: ArticlePlanState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "site_id",
            "category_id",
            "intent_cluster_id",
            "primary_keyword_id",
            "article_type",
            "working_title",
            "objective",
            "status",
            "priority",
            "opportunity_assessment_id",
            "created_by_principal_id",
            "approved_by_principal_id",
            "approved_at",
            "brief",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_editorial_article_plan_to_row(value),
    )


def _decode_editorial_article_slug(row: Mapping[str, object]) -> ArticleSlugState:
    columns = (
        "id",
        "site_id",
        "article_id",
        "slug",
        "normalized_path",
        "status",
        "valid_from",
        "valid_to",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_slug_from_row(
            id=ArticleSlugId(_exact(row, "id", UUID)),
            site_id=SiteId(_exact(row, "site_id", UUID)),
            article_id=ArticleId(_exact(row, "article_id", UUID)),
            slug=_exact(row, "slug", str),
            normalized_path=_exact(row, "normalized_path", str),
            status=ArticleSlugStatus(_exact(row, "status", str)),
            valid_from=AwareUtcDateTime(_exact(row, "valid_from", datetime)),
            valid_to=(
                None
                if row["valid_to"] is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_slug(value: ArticleSlugState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "site_id",
            "article_id",
            "slug",
            "normalized_path",
            "status",
            "valid_from",
            "valid_to",
            "created_at",
        ),
        domain_mappers.map_editorial_article_slug_to_row(value),
    )


def _decode_editorial_article_template_version(
    row: Mapping[str, object],
) -> ArticleTemplateVersionState:
    columns = (
        "id",
        "article_type_version_id",
        "semantic_version",
        "template",
        "template_sha256",
        "status",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_template_version_from_row(
            id=ArticleTemplateVersionId(_exact(row, "id", UUID)),
            article_type_version_id=ArticleTypeVersionId(
                _exact(row, "article_type_version_id", UUID)
            ),
            semantic_version=_exact(row, "semantic_version", str),
            template=ArticleTemplateVersionTemplateJson(_json_object(row, "template")),
            template_sha256=Sha256Digest(_exact(row, "template_sha256", str)),
            status=ArticleTemplateVersionStatus(_exact(row, "status", str)),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_template_version(
    value: ArticleTemplateVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_type_version_id",
            "semantic_version",
            "template",
            "template_sha256",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_article_template_version_to_row(value),
    )


def _decode_editorial_article_type_version(
    row: Mapping[str, object],
) -> ArticleTypeVersionState:
    columns = (
        "id",
        "article_type_code",
        "semantic_version",
        "contract",
        "contract_sha256",
        "status",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_type_version_from_row(
            id=ArticleTypeVersionId(_exact(row, "id", UUID)),
            article_type_code=_exact(row, "article_type_code", str),
            semantic_version=_exact(row, "semantic_version", str),
            contract=ArticleTypeVersionContractJson(_json_object(row, "contract")),
            contract_sha256=Sha256Digest(_exact(row, "contract_sha256", str)),
            status=ArticleTypeVersionStatus(_exact(row, "status", str)),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_type_version(
    value: ArticleTypeVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_type_code",
            "semantic_version",
            "contract",
            "contract_sha256",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_article_type_version_to_row(value),
    )


def _decode_editorial_article_version(row: Mapping[str, object]) -> ArticleVersionState:
    columns = (
        "id",
        "display_id",
        "article_id",
        "version_no",
        "content_schema_version",
        "title",
        "meta_title",
        "meta_description",
        "excerpt",
        "body_sha256",
        "status",
        "source_packet_version_id",
        "based_on_version_id",
        "ai_job_id",
        "created_by_actor_type",
        "created_by_actor_id",
        "submitted_at",
        "reviewed_at",
        "created_at",
        "updated_at",
        "lock_version",
        "content_schema_version_id",
        "article_type_version_id",
        "article_template_version_id",
        "seo_metadata_version_id",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_article_version_from_row(
            id=ArticleVersionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            article_id=ArticleId(_exact(row, "article_id", UUID)),
            version_no=_exact(row, "version_no", int),
            content_schema_version=_exact(row, "content_schema_version", int),
            title=_exact(row, "title", str),
            meta_title=(
                None if row["meta_title"] is None else _exact(row, "meta_title", str)
            ),
            meta_description=(
                None
                if row["meta_description"] is None
                else _exact(row, "meta_description", str)
            ),
            excerpt=(None if row["excerpt"] is None else _exact(row, "excerpt", str)),
            body_sha256=Sha256Digest(_exact(row, "body_sha256", str)),
            status=ArticleVersionStatus(_exact(row, "status", str)),
            source_packet_version_id=SourcePacketVersionId(
                _exact(row, "source_packet_version_id", UUID)
            ),
            based_on_version_id=(
                None
                if row["based_on_version_id"] is None
                else ArticleVersionId(_exact(row, "based_on_version_id", UUID))
            ),
            ai_job_id=(
                None
                if row["ai_job_id"] is None
                else AiJobId(_exact(row, "ai_job_id", UUID))
            ),
            created_by_actor_type=ArticleVersionCreatedByActorType(
                _exact(row, "created_by_actor_type", str)
            ),
            created_by_actor_id=(
                None
                if row["created_by_actor_id"] is None
                else ActorId(_exact(row, "created_by_actor_id", UUID))
            ),
            submitted_at=(
                None
                if row["submitted_at"] is None
                else AwareUtcDateTime(_exact(row, "submitted_at", datetime))
            ),
            reviewed_at=(
                None
                if row["reviewed_at"] is None
                else AwareUtcDateTime(_exact(row, "reviewed_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
            content_schema_version_id=ContentSchemaVersionId(
                _exact(row, "content_schema_version_id", UUID)
            ),
            article_type_version_id=ArticleTypeVersionId(
                _exact(row, "article_type_version_id", UUID)
            ),
            article_template_version_id=ArticleTemplateVersionId(
                _exact(row, "article_template_version_id", UUID)
            ),
            seo_metadata_version_id=SeoMetadataVersionId(
                _exact(row, "seo_metadata_version_id", UUID)
            ),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_article_version(value: ArticleVersionState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "article_id",
            "version_no",
            "content_schema_version",
            "title",
            "meta_title",
            "meta_description",
            "excerpt",
            "body_sha256",
            "status",
            "source_packet_version_id",
            "based_on_version_id",
            "ai_job_id",
            "created_by_actor_type",
            "created_by_actor_id",
            "submitted_at",
            "reviewed_at",
            "created_at",
            "updated_at",
            "lock_version",
            "content_schema_version_id",
            "article_type_version_id",
            "article_template_version_id",
            "seo_metadata_version_id",
        ),
        domain_mappers.map_editorial_article_version_to_row(value),
    )


def _decode_editorial_comparison_axis(row: Mapping[str, object]) -> ComparisonAxis:
    columns = (
        "id",
        "article_version_id",
        "axis_code",
        "name",
        "description",
        "data_type",
        "unit_code",
        "position",
        "is_required",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_comparison_axis_from_row(
            id=ComparisonAxisId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            axis_code=_exact(row, "axis_code", str),
            name=_exact(row, "name", str),
            description=_exact(row, "description", str),
            data_type=ComparisonAxisDataType(_exact(row, "data_type", str)),
            unit_code=(
                None if row["unit_code"] is None else _exact(row, "unit_code", str)
            ),
            position=_exact(row, "position", int),
            is_required=_exact(row, "is_required", bool),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_comparison_axis(value: ComparisonAxis) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "axis_code",
            "name",
            "description",
            "data_type",
            "unit_code",
            "position",
            "is_required",
            "created_at",
        ),
        domain_mappers.map_editorial_comparison_axis_to_row(value),
    )


def _decode_editorial_comparison_value(row: Mapping[str, object]) -> ComparisonValue:
    columns = (
        "id",
        "comparison_axis_id",
        "product_id",
        "value_text",
        "value_numeric",
        "value_boolean",
        "value_date",
        "value_code",
        "display_value",
        "source_fact_id",
        "validation_status",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_comparison_value_from_row(
            id=ComparisonValueId(_exact(row, "id", UUID)),
            comparison_axis_id=ComparisonAxisId(
                _exact(row, "comparison_axis_id", UUID)
            ),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            value_text=(
                None if row["value_text"] is None else _exact(row, "value_text", str)
            ),
            value_numeric=(
                None
                if row["value_numeric"] is None
                else _exact(row, "value_numeric", Decimal)
            ),
            value_boolean=(
                None
                if row["value_boolean"] is None
                else _exact(row, "value_boolean", bool)
            ),
            value_date=(
                None if row["value_date"] is None else _exact(row, "value_date", date)
            ),
            value_code=(
                None if row["value_code"] is None else _exact(row, "value_code", str)
            ),
            display_value=_exact(row, "display_value", str),
            source_fact_id=(
                None
                if row["source_fact_id"] is None
                else FactId(_exact(row, "source_fact_id", UUID))
            ),
            validation_status=ComparisonValueValidationStatus(
                _exact(row, "validation_status", str)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_comparison_value(value: ComparisonValue) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "comparison_axis_id",
            "product_id",
            "value_text",
            "value_numeric",
            "value_boolean",
            "value_date",
            "value_code",
            "display_value",
            "source_fact_id",
            "validation_status",
            "created_at",
        ),
        domain_mappers.map_editorial_comparison_value_to_row(value),
    )


def _decode_editorial_content_schema_version(
    row: Mapping[str, object],
) -> ContentSchemaVersionState:
    columns = (
        "id",
        "schema_code",
        "semantic_version",
        "artifact_id",
        "schema_sha256",
        "status",
        "effective_from",
        "effective_to",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_content_schema_version_from_row(
            id=ContentSchemaVersionId(_exact(row, "id", UUID)),
            schema_code=_exact(row, "schema_code", str),
            semantic_version=_exact(row, "semantic_version", str),
            artifact_id=ObjectArtifactId(_exact(row, "artifact_id", UUID)),
            schema_sha256=Sha256Digest(_exact(row, "schema_sha256", str)),
            status=ContentSchemaVersionStatus(_exact(row, "status", str)),
            effective_from=AwareUtcDateTime(_exact(row, "effective_from", datetime)),
            effective_to=(
                None
                if row["effective_to"] is None
                else AwareUtcDateTime(_exact(row, "effective_to", datetime))
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_content_schema_version(
    value: ContentSchemaVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "schema_code",
            "semantic_version",
            "artifact_id",
            "schema_sha256",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_content_schema_version_to_row(value),
    )


def _decode_editorial_editorial_methodology_version(
    row: Mapping[str, object],
) -> EditorialMethodologyVersionState:
    columns = (
        "id",
        "methodology_code",
        "semantic_version",
        "article_type_code",
        "article_type_version_id",
        "definition",
        "definition_sha256",
        "excludes_finance_inputs",
        "status",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_editorial_methodology_version_from_row(
            id=EditorialMethodologyVersionId(_exact(row, "id", UUID)),
            methodology_code=_exact(row, "methodology_code", str),
            semantic_version=_exact(row, "semantic_version", str),
            article_type_code=_exact(row, "article_type_code", str),
            article_type_version_id=ArticleTypeVersionId(
                _exact(row, "article_type_version_id", UUID)
            ),
            definition=EditorialMethodologyVersionDefinitionJson(
                _json_object(row, "definition")
            ),
            definition_sha256=Sha256Digest(_exact(row, "definition_sha256", str)),
            excludes_finance_inputs=_exact(row, "excludes_finance_inputs", bool),
            status=EditorialMethodologyVersionStatus(_exact(row, "status", str)),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_editorial_methodology_version(
    value: EditorialMethodologyVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "methodology_code",
            "semantic_version",
            "article_type_code",
            "article_type_version_id",
            "definition",
            "definition_sha256",
            "excludes_finance_inputs",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_editorial_methodology_version_to_row(value),
    )


def _decode_editorial_media_asset(row: Mapping[str, object]) -> MediaAssetState:
    columns = (
        "id",
        "display_id",
        "asset_class",
        "source_id",
        "raw_artifact_id",
        "asset_sha256",
        "license_status",
        "modification_policy",
        "alt_text",
        "decorative",
        "long_description_artifact_id",
        "width",
        "height",
        "captured_or_observed_at",
        "status",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_media_asset_from_row(
            id=MediaAssetId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            asset_class=MediaAssetAssetClass(_exact(row, "asset_class", str)),
            source_id=SourceId(_exact(row, "source_id", UUID)),
            raw_artifact_id=ObjectArtifactId(_exact(row, "raw_artifact_id", UUID)),
            asset_sha256=Sha256Digest(_exact(row, "asset_sha256", str)),
            license_status=MediaAssetLicenseStatus(_exact(row, "license_status", str)),
            modification_policy=_exact(row, "modification_policy", str),
            alt_text=_exact(row, "alt_text", str),
            decorative=_exact(row, "decorative", bool),
            long_description_artifact_id=(
                None
                if row["long_description_artifact_id"] is None
                else ObjectArtifactId(_exact(row, "long_description_artifact_id", UUID))
            ),
            width=_exact(row, "width", int),
            height=_exact(row, "height", int),
            captured_or_observed_at=AwareUtcDateTime(
                _exact(row, "captured_or_observed_at", datetime)
            ),
            status=MediaAssetStatus(_exact(row, "status", str)),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_media_asset(value: MediaAssetState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "asset_class",
            "source_id",
            "raw_artifact_id",
            "asset_sha256",
            "license_status",
            "modification_policy",
            "alt_text",
            "decorative",
            "long_description_artifact_id",
            "width",
            "height",
            "captured_or_observed_at",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_media_asset_to_row(value),
    )


def _decode_editorial_recommendation(row: Mapping[str, object]) -> Recommendation:
    columns = (
        "id",
        "recommendation_set_id",
        "product_id",
        "rank_position",
        "suitability_score",
        "status",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_recommendation_from_row(
            id=RecommendationId(_exact(row, "id", UUID)),
            recommendation_set_id=RecommendationSetId(
                _exact(row, "recommendation_set_id", UUID)
            ),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            rank_position=_exact(row, "rank_position", int),
            suitability_score=_exact(row, "suitability_score", Decimal),
            status=RecommendationStatus(_exact(row, "status", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_recommendation(value: Recommendation) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "recommendation_set_id",
            "product_id",
            "rank_position",
            "suitability_score",
            "status",
            "created_at",
        ),
        domain_mappers.map_editorial_recommendation_to_row(value),
    )


def _decode_editorial_recommendation_rationale(
    row: Mapping[str, object],
) -> RecommendationRationale:
    columns = (
        "id",
        "recommendation_id",
        "rationale_type",
        "rationale_text",
        "claim_id",
        "source_fact_id",
        "position",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_recommendation_rationale_from_row(
            id=RecommendationRationaleId(_exact(row, "id", UUID)),
            recommendation_id=RecommendationId(_exact(row, "recommendation_id", UUID)),
            rationale_type=RecommendationRationaleRationaleType(
                _exact(row, "rationale_type", str)
            ),
            rationale_text=_exact(row, "rationale_text", str),
            claim_id=(
                None
                if row["claim_id"] is None
                else ClaimId(_exact(row, "claim_id", UUID))
            ),
            source_fact_id=(
                None
                if row["source_fact_id"] is None
                else FactId(_exact(row, "source_fact_id", UUID))
            ),
            position=_exact(row, "position", int),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_recommendation_rationale(
    value: RecommendationRationale,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "recommendation_id",
            "rationale_type",
            "rationale_text",
            "claim_id",
            "source_fact_id",
            "position",
            "created_at",
        ),
        domain_mappers.map_editorial_recommendation_rationale_to_row(value),
    )


def _decode_editorial_recommendation_set(
    row: Mapping[str, object],
) -> RecommendationSet:
    columns = (
        "id",
        "article_version_id",
        "set_code",
        "name",
        "target_segment",
        "methodology",
        "editorial_policy_version",
        "position",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_recommendation_set_from_row(
            id=RecommendationSetId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            set_code=_exact(row, "set_code", str),
            name=_exact(row, "name", str),
            target_segment=_exact(row, "target_segment", str),
            methodology=_exact(row, "methodology", str),
            editorial_policy_version=_exact(row, "editorial_policy_version", str),
            position=_exact(row, "position", int),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_recommendation_set(value: RecommendationSet) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "set_code",
            "name",
            "target_segment",
            "methodology",
            "editorial_policy_version",
            "position",
            "created_at",
        ),
        domain_mappers.map_editorial_recommendation_set_to_row(value),
    )


def _decode_editorial_review_comment(row: Mapping[str, object]) -> ReviewCommentState:
    columns = (
        "id",
        "article_version_id",
        "article_block_id",
        "claim_id",
        "thread_id",
        "parent_comment_id",
        "author_principal_id",
        "comment_text",
        "status",
        "resolved_by_principal_id",
        "resolved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_review_comment_from_row(
            id=ReviewCommentId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            article_block_id=(
                None
                if row["article_block_id"] is None
                else ArticleBlockId(_exact(row, "article_block_id", UUID))
            ),
            claim_id=(
                None
                if row["claim_id"] is None
                else ClaimId(_exact(row, "claim_id", UUID))
            ),
            thread_id=ThreadId(_exact(row, "thread_id", UUID)),
            parent_comment_id=(
                None
                if row["parent_comment_id"] is None
                else ReviewCommentId(_exact(row, "parent_comment_id", UUID))
            ),
            author_principal_id=PrincipalId(_exact(row, "author_principal_id", UUID)),
            comment_text=_exact(row, "comment_text", str),
            status=ReviewCommentStatus(_exact(row, "status", str)),
            resolved_by_principal_id=(
                None
                if row["resolved_by_principal_id"] is None
                else PrincipalId(_exact(row, "resolved_by_principal_id", UUID))
            ),
            resolved_at=(
                None
                if row["resolved_at"] is None
                else AwareUtcDateTime(_exact(row, "resolved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_review_comment(value: ReviewCommentState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "article_block_id",
            "claim_id",
            "thread_id",
            "parent_comment_id",
            "author_principal_id",
            "comment_text",
            "status",
            "resolved_by_principal_id",
            "resolved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_review_comment_to_row(value),
    )


def _decode_editorial_seo_metadata_version(
    row: Mapping[str, object],
) -> SeoMetadataVersionState:
    columns = (
        "id",
        "article_version_id",
        "semantic_version",
        "metadata",
        "metadata_sha256",
        "status",
        "validated_at",
        "approved_by_principal_id",
        "approved_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_seo_metadata_version_from_row(
            id=SeoMetadataVersionId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            semantic_version=_exact(row, "semantic_version", str),
            metadata=SeoMetadataVersionMetadataJson(_json_object(row, "metadata")),
            metadata_sha256=Sha256Digest(_exact(row, "metadata_sha256", str)),
            status=SeoMetadataVersionStatus(_exact(row, "status", str)),
            validated_at=(
                None
                if row["validated_at"] is None
                else AwareUtcDateTime(_exact(row, "validated_at", datetime))
            ),
            approved_by_principal_id=(
                None
                if row["approved_by_principal_id"] is None
                else PrincipalId(_exact(row, "approved_by_principal_id", UUID))
            ),
            approved_at=(
                None
                if row["approved_at"] is None
                else AwareUtcDateTime(_exact(row, "approved_at", datetime))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_seo_metadata_version(
    value: SeoMetadataVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "semantic_version",
            "metadata",
            "metadata_sha256",
            "status",
            "validated_at",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        domain_mappers.map_editorial_seo_metadata_version_to_row(value),
    )


def _decode_editorial_structured_data_manifest(
    row: Mapping[str, object],
) -> StructuredDataManifest:
    columns = (
        "id",
        "article_version_id",
        "seo_metadata_version_id",
        "generator_version",
        "visible_content_sha256",
        "jsonld_artifact_id",
        "jsonld_sha256",
        "enabled_types",
        "disabled_types",
        "validation_status",
        "validated_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_editorial_structured_data_manifest_from_row(
            id=StructuredDataManifestId(_exact(row, "id", UUID)),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            seo_metadata_version_id=SeoMetadataVersionId(
                _exact(row, "seo_metadata_version_id", UUID)
            ),
            generator_version=_exact(row, "generator_version", str),
            visible_content_sha256=Sha256Digest(
                _exact(row, "visible_content_sha256", str)
            ),
            jsonld_artifact_id=ObjectArtifactId(
                _exact(row, "jsonld_artifact_id", UUID)
            ),
            jsonld_sha256=Sha256Digest(_exact(row, "jsonld_sha256", str)),
            enabled_types=_string_array(row, "enabled_types"),
            disabled_types=_string_array(row, "disabled_types"),
            validation_status=StructuredDataManifestValidationStatus(
                _exact(row, "validation_status", str)
            ),
            validated_at=AwareUtcDateTime(_exact(row, "validated_at", datetime)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_editorial_structured_data_manifest(
    value: StructuredDataManifest,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "article_version_id",
            "seo_metadata_version_id",
            "generator_version",
            "visible_content_sha256",
            "jsonld_artifact_id",
            "jsonld_sha256",
            "enabled_types",
            "disabled_types",
            "validation_status",
            "validated_at",
            "created_at",
        ),
        domain_mappers.map_editorial_structured_data_manifest_to_row(value),
    )


# Aggregate-specific Session/Table-bound classes are the only DML surface.


def _require_session(session: Session) -> None:
    if not isinstance(cast(object, session), Session):
        raise ValueError("INVALID_EDITORIAL_REPOSITORY") from None


def _scalar_one(session: Session, statement: Executable) -> object | None:
    try:
        return cast(object | None, session.execute(statement).scalar_one_or_none())
    except IntegrityError:
        fail_session_operation(session, PersistenceErrorCode.INTEGRITY_CONFLICT)
    except DBAPIError:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)
    except PersistenceError as error:
        fail_session_operation(session, error.code)
    except Exception:
        fail_session_operation(session, PersistenceErrorCode.STORAGE_CORRUPTION)


def _cas_update(
    session: Session,
    table: Table,
    aggregate_id: UUID,
    expected_version: AggregateVersion,
    values: dict[str, object],
) -> AggregateVersion:
    proposed = dict(values)
    proposed.pop("id", None)
    proposed["lock_version"] = expected_version.value + 1
    persisted = _scalar_one(
        session,
        update(table)
        .where(
            table.c.id == aggregate_id,
            table.c.lock_version == expected_version.value,
        )
        .values(**proposed)
        .returning(table.c.lock_version),
    )
    if type(persisted) is int:
        return AggregateVersion(persisted)
    observed = _execute_one(
        session,
        select(table.c.id, table.c.lock_version).where(table.c.id == aggregate_id),
    )
    if observed is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    if _exact(observed, "lock_version", int) != expected_version.value:
        _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _state_zero(
    session: Session,
    table: Table,
    identity_column: str,
    identity: object,
    state_column: str,
    expected_state: str,
) -> NoReturn:
    row = _execute_one(
        session,
        select(table.c[identity_column], table.c[state_column]).where(
            table.c[identity_column] == identity
        ),
    )
    if row is None:
        _fail(PersistenceErrorCode.NOT_FOUND)
    if _exact(row, state_column, str) != expected_state:
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _same_except(
    current: dict[str, object],
    proposed: dict[str, object],
    mutable: tuple[str, ...],
) -> bool:
    current_copy = dict(current)
    proposed_copy = dict(proposed)
    for name in mutable:
        current_copy.pop(name, None)
        proposed_copy.pop(name, None)
    return current_copy == proposed_copy


def _validate_latest(expected_latest_version: int | None) -> None:
    if expected_latest_version is not None and (
        type(expected_latest_version) is not int or expected_latest_version < 1
    ):
        raise ValueError("INVALID_EDITORIAL_LATEST_VERSION") from None


@guard_repository_class
class SqlAlchemyArticlePlanRepository:
    __slots__ = ("_plan", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._plan = _table("editorial.article_plan")

    def get(self, plan_id: ArticlePlanId) -> ArticlePlan | None:
        if type(plan_id) is not ArticlePlanId:
            raise ValueError("INVALID_ARTICLE_PLAN_ID") from None
        row = _execute_one(
            self._session,
            select(self._plan).where(self._plan.c.id == plan_id.value),
        )
        if row is None:
            return None
        plan = ArticlePlan(_decode_editorial_article_plan(row))
        register_pending_events(
            self._session,
            aggregate_type="editorial.article_plan",
            aggregate_id=plan.state.id.value,
            buffer=aggregate_events_buffer(plan),
        )
        return plan

    def add(self, plan: ArticlePlan) -> AggregateVersion:
        if type(plan) is not ArticlePlan or plan.state.lock_version.value != 0:
            raise ValueError("INVALID_ARTICLE_PLAN") from None
        register_pending_events(
            self._session,
            aggregate_type="editorial.article_plan",
            aggregate_id=plan.state.id.value,
            buffer=aggregate_events_buffer(plan),
        )
        _execute(
            self._session,
            insert(self._plan).values(**_encode_editorial_article_plan(plan.state)),
        )
        return AggregateVersion(0)

    def save(
        self,
        plan: ArticlePlan,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(plan) is not ArticlePlan
            or type(expected_version) is not AggregateVersion
            or plan.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_ARTICLE_PLAN") from None
        register_pending_events(
            self._session,
            aggregate_type="editorial.article_plan",
            aggregate_id=plan.state.id.value,
            buffer=aggregate_events_buffer(plan),
        )
        persisted = _cas_update(
            self._session,
            self._plan,
            plan.state.id.value,
            expected_version,
            _encode_editorial_article_plan(plan.state),
        )
        if plan.pending_events():
            stage_registered_events(
                self._session,
                aggregate_type="editorial.article_plan",
                aggregate_id=plan.state.id.value,
                owning_method="ArticlePlanRepository.save",
                persisted_version=persisted,
                expected_event_type="jp.raos.editorial.article_plan_approved.v1",
            )
        return persisted


@guard_repository_class
class SqlAlchemyArticleRepository:
    __slots__ = (
        "_article",
        "_axis",
        "_binding",
        "_block",
        "_block_product",
        "_comment",
        "_disclosure",
        "_link",
        "_manifest",
        "_rationale",
        "_recommendation",
        "_recommendation_set",
        "_seo",
        "_session",
        "_slug",
        "_value",
        "_version",
    )

    _SLUG_EDGES = frozenset(
        {
            ("ACTIVE", "REDIRECTED"),
            ("ACTIVE", "RETIRED"),
            ("REDIRECTED", "RETIRED"),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._article = _table("editorial.article")
        self._slug = _table("editorial.article_slug")
        self._version = _table("editorial.article_version")
        self._block = _table("editorial.article_block")
        self._block_product = _table("editorial.article_block_product")
        self._disclosure = _table("editorial.article_disclosure_context")
        self._binding = _table("editorial.article_methodology_binding")
        self._axis = _table("editorial.comparison_axis")
        self._value = _table("editorial.comparison_value")
        self._recommendation_set = _table("editorial.recommendation_set")
        self._recommendation = _table("editorial.recommendation")
        self._rationale = _table("editorial.recommendation_rationale")
        self._comment = _table("editorial.review_comment")
        self._seo = _table("editorial.seo_metadata_version")
        self._manifest = _table("editorial.structured_data_manifest")
        self._link = _table("editorial.article_link")

    @staticmethod
    def _validate_article(article: Article) -> None:
        if type(article) is not Article:
            raise ValueError("INVALID_ARTICLE") from None
        article_id = article.state.id
        version_ids = frozenset(item.id for item in article.article_version_rows)
        block_ids = frozenset(item.id for item in article.article_block_rows)
        axis_ids = frozenset(item.id for item in article.comparison_axis_rows)
        set_ids = frozenset(item.id for item in article.recommendation_set_rows)
        recommendation_ids = frozenset(item.id for item in article.recommendation_rows)
        if (
            any(item.article_id != article_id for item in article.article_slug_rows)
            or any(
                item.article_id != article_id for item in article.article_version_rows
            )
            or any(
                item.article_version_id not in version_ids
                for item in article.article_block_rows
            )
            or any(
                item.article_block_id not in block_ids
                for item in article.article_block_product_rows
            )
            or any(
                item.article_version_id not in version_ids
                for item in article.comparison_axis_rows
            )
            or any(
                item.comparison_axis_id not in axis_ids
                for item in article.comparison_value_rows
            )
            or any(
                item.article_version_id not in version_ids
                for item in article.recommendation_set_rows
            )
            or any(
                item.recommendation_set_id not in set_ids
                for item in article.recommendation_rows
            )
            or any(
                item.recommendation_id not in recommendation_ids
                for item in article.recommendation_rationale_rows
            )
            or any(
                item.from_article_id != article_id and item.to_article_id != article_id
                for item in article.article_link_rows
            )
        ):
            raise ValueError("INVALID_ARTICLE") from None

    def get(self, article_id: ArticleId) -> Article | None:
        article = self._get(article_id)
        if article is not None:
            register_pending_events(
                self._session,
                aggregate_type="editorial.article",
                aggregate_id=article.state.id.value,
                buffer=aggregate_events_buffer(article),
            )
        return article

    def _get(self, article_id: ArticleId) -> Article | None:
        if type(article_id) is not ArticleId:
            raise ValueError("INVALID_ARTICLE_ID") from None
        row = _execute_one(
            self._session,
            select(self._article).where(self._article.c.id == article_id.value),
        )
        if row is None:
            return None
        slugs = tuple(
            _decode_editorial_article_slug(item)
            for item in _execute_many(
                self._session,
                select(self._slug)
                .where(self._slug.c.article_id == article_id.value)
                .order_by(self._slug.c.id),
            )
        )
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.article_id == article_id.value)
                .order_by(self._version.c.id),
            )
        )
        version_ids = tuple(item.id.value for item in versions)
        if version_ids:
            blocks = tuple(
                _decode_editorial_article_block(item)
                for item in _execute_many(
                    self._session,
                    select(self._block)
                    .where(self._block.c.article_version_id.in_(version_ids))
                    .order_by(self._block.c.id),
                )
            )
            axes = tuple(
                _decode_editorial_comparison_axis(item)
                for item in _execute_many(
                    self._session,
                    select(self._axis)
                    .where(self._axis.c.article_version_id.in_(version_ids))
                    .order_by(self._axis.c.id),
                )
            )
            sets = tuple(
                _decode_editorial_recommendation_set(item)
                for item in _execute_many(
                    self._session,
                    select(self._recommendation_set)
                    .where(
                        self._recommendation_set.c.article_version_id.in_(version_ids)
                    )
                    .order_by(self._recommendation_set.c.id),
                )
            )
        else:
            blocks, axes, sets = (), (), ()
        block_ids = tuple(item.id.value for item in blocks)
        products = (
            tuple(
                _decode_editorial_article_block_product(item)
                for item in _execute_many(
                    self._session,
                    select(self._block_product)
                    .where(self._block_product.c.article_block_id.in_(block_ids))
                    .order_by(
                        self._block_product.c.article_block_id,
                        self._block_product.c.product_id,
                        self._block_product.c.placement_role,
                    ),
                )
            )
            if block_ids
            else ()
        )
        axis_ids = tuple(item.id.value for item in axes)
        values = (
            tuple(
                _decode_editorial_comparison_value(item)
                for item in _execute_many(
                    self._session,
                    select(self._value)
                    .where(self._value.c.comparison_axis_id.in_(axis_ids))
                    .order_by(self._value.c.id),
                )
            )
            if axis_ids
            else ()
        )
        set_ids = tuple(item.id.value for item in sets)
        recommendations = (
            tuple(
                _decode_editorial_recommendation(item)
                for item in _execute_many(
                    self._session,
                    select(self._recommendation)
                    .where(self._recommendation.c.recommendation_set_id.in_(set_ids))
                    .order_by(self._recommendation.c.id),
                )
            )
            if set_ids
            else ()
        )
        recommendation_ids = tuple(item.id.value for item in recommendations)
        rationales = (
            tuple(
                _decode_editorial_recommendation_rationale(item)
                for item in _execute_many(
                    self._session,
                    select(self._rationale)
                    .where(self._rationale.c.recommendation_id.in_(recommendation_ids))
                    .order_by(self._rationale.c.id),
                )
            )
            if recommendation_ids
            else ()
        )
        links = tuple(
            _decode_editorial_article_link(item)
            for item in _execute_many(
                self._session,
                select(self._link)
                .where(
                    or_(
                        self._link.c.from_article_id == article_id.value,
                        self._link.c.to_article_id == article_id.value,
                    )
                )
                .order_by(self._link.c.id),
            )
        )
        article = Article(
            state=_decode_editorial_article(row),
            article_slug_rows=slugs,
            article_version_rows=versions,
            article_block_rows=blocks,
            article_block_product_rows=products,
            comparison_axis_rows=axes,
            comparison_value_rows=values,
            recommendation_set_rows=sets,
            recommendation_rows=recommendations,
            recommendation_rationale_rows=rationales,
            article_link_rows=links,
        )
        try:
            self._validate_article(article)
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return article

    def add(self, article: Article) -> AggregateVersion:
        self._validate_article(article)
        if (
            article.state.lock_version.value != 0
            or any(
                item.lock_version.value != 0 for item in article.article_version_rows
            )
            or any(item.lock_version.value != 0 for item in article.article_link_rows)
        ):
            raise ValueError("INVALID_ARTICLE") from None
        register_pending_events(
            self._session,
            aggregate_type="editorial.article",
            aggregate_id=article.state.id.value,
            buffer=aggregate_events_buffer(article),
        )
        _execute(
            self._session,
            insert(self._article).values(**_encode_editorial_article(article.state)),
        )
        for slug_state in article.article_slug_rows:
            _execute(
                self._session,
                insert(self._slug).values(**_encode_editorial_article_slug(slug_state)),
            )
        for version_state in article.article_version_rows:
            _execute(
                self._session,
                insert(self._version).values(
                    **_encode_editorial_article_version(version_state)
                ),
            )
        for block in article.article_block_rows:
            _execute(
                self._session,
                insert(self._block).values(**_encode_editorial_article_block(block)),
            )
        for block_product in article.article_block_product_rows:
            _execute(
                self._session,
                insert(self._block_product).values(
                    **_encode_editorial_article_block_product(block_product)
                ),
            )
        for axis in article.comparison_axis_rows:
            _execute(
                self._session,
                insert(self._axis).values(**_encode_editorial_comparison_axis(axis)),
            )
        for comparison_value in article.comparison_value_rows:
            _execute(
                self._session,
                insert(self._value).values(
                    **_encode_editorial_comparison_value(comparison_value)
                ),
            )
        for recommendation_set in article.recommendation_set_rows:
            _execute(
                self._session,
                insert(self._recommendation_set).values(
                    **_encode_editorial_recommendation_set(recommendation_set)
                ),
            )
        for recommendation in article.recommendation_rows:
            _execute(
                self._session,
                insert(self._recommendation).values(
                    **_encode_editorial_recommendation(recommendation)
                ),
            )
        for rationale in article.recommendation_rationale_rows:
            _execute(
                self._session,
                insert(self._rationale).values(
                    **_encode_editorial_recommendation_rationale(rationale)
                ),
            )
        for link_state in article.article_link_rows:
            _execute(
                self._session,
                insert(self._link).values(**_encode_editorial_article_link(link_state)),
            )
        persisted = AggregateVersion(0)
        stage_registered_events(
            self._session,
            aggregate_type="editorial.article",
            aggregate_id=article.state.id.value,
            owning_method="ArticleRepository.add",
            persisted_version=persisted,
            expected_event_type="jp.raos.editorial.article_created.v1",
        )
        return persisted

    def save(
        self,
        article: Article,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        self._validate_article(article)
        if (
            type(expected_version) is not AggregateVersion
            or article.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_ARTICLE") from None
        current = self._get(article.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if (
            current.article_slug_rows != article.article_slug_rows
            or current.article_version_rows != article.article_version_rows
            or current.article_block_rows != article.article_block_rows
            or current.article_block_product_rows != article.article_block_product_rows
            or current.comparison_axis_rows != article.comparison_axis_rows
            or current.comparison_value_rows != article.comparison_value_rows
            or current.recommendation_set_rows != article.recommendation_set_rows
            or current.recommendation_rows != article.recommendation_rows
            or current.recommendation_rationale_rows
            != article.recommendation_rationale_rows
            or current.article_link_rows != article.article_link_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        register_pending_events(
            self._session,
            aggregate_type="editorial.article",
            aggregate_id=article.state.id.value,
            buffer=aggregate_events_buffer(article),
        )
        return _cas_update(
            self._session,
            self._article,
            article.state.id.value,
            expected_version,
            _encode_editorial_article(article.state),
        )

    def get_version(self, version_id: ArticleVersionId) -> ArticleVersion | None:
        version = self._get_version(version_id)
        if version is not None:
            register_pending_events(
                self._session,
                aggregate_type="editorial.article_version",
                aggregate_id=version.state.id.value,
                buffer=aggregate_events_buffer(version),
            )
        return version

    def _get_version(self, version_id: ArticleVersionId) -> ArticleVersion | None:
        if type(version_id) is not ArticleVersionId:
            raise ValueError("INVALID_ARTICLE_VERSION_ID") from None
        row = _execute_one(
            self._session,
            select(self._version).where(self._version.c.id == version_id.value),
        )
        if row is None:
            return None
        state = _decode_editorial_article_version(row)
        article_rows = tuple(
            _decode_editorial_article(item)
            for item in _execute_many(
                self._session,
                select(self._article)
                .where(self._article.c.id == state.article_id.value)
                .order_by(self._article.c.id),
            )
        )
        blocks = tuple(
            _decode_editorial_article_block(item)
            for item in _execute_many(
                self._session,
                select(self._block)
                .where(self._block.c.article_version_id == version_id.value)
                .order_by(self._block.c.id),
            )
        )
        block_ids = tuple(item.id.value for item in blocks)
        block_products = (
            tuple(
                _decode_editorial_article_block_product(item)
                for item in _execute_many(
                    self._session,
                    select(self._block_product)
                    .where(self._block_product.c.article_block_id.in_(block_ids))
                    .order_by(
                        self._block_product.c.article_block_id,
                        self._block_product.c.product_id,
                        self._block_product.c.placement_role,
                    ),
                )
            )
            if block_ids
            else ()
        )
        disclosures = tuple(
            _decode_editorial_article_disclosure_context(item)
            for item in _execute_many(
                self._session,
                select(self._disclosure)
                .where(self._disclosure.c.article_version_id == version_id.value)
                .order_by(self._disclosure.c.article_version_id),
            )
        )
        bindings = tuple(
            _decode_editorial_article_methodology_binding(item)
            for item in _execute_many(
                self._session,
                select(self._binding)
                .where(self._binding.c.article_version_id == version_id.value)
                .order_by(self._binding.c.article_version_id),
            )
        )
        axes = tuple(
            _decode_editorial_comparison_axis(item)
            for item in _execute_many(
                self._session,
                select(self._axis)
                .where(self._axis.c.article_version_id == version_id.value)
                .order_by(self._axis.c.id),
            )
        )
        axis_ids = tuple(item.id.value for item in axes)
        values = (
            tuple(
                _decode_editorial_comparison_value(item)
                for item in _execute_many(
                    self._session,
                    select(self._value)
                    .where(self._value.c.comparison_axis_id.in_(axis_ids))
                    .order_by(self._value.c.id),
                )
            )
            if axis_ids
            else ()
        )
        sets = tuple(
            _decode_editorial_recommendation_set(item)
            for item in _execute_many(
                self._session,
                select(self._recommendation_set)
                .where(
                    self._recommendation_set.c.article_version_id == version_id.value
                )
                .order_by(self._recommendation_set.c.id),
            )
        )
        set_ids = tuple(item.id.value for item in sets)
        recommendations = (
            tuple(
                _decode_editorial_recommendation(item)
                for item in _execute_many(
                    self._session,
                    select(self._recommendation)
                    .where(self._recommendation.c.recommendation_set_id.in_(set_ids))
                    .order_by(self._recommendation.c.id),
                )
            )
            if set_ids
            else ()
        )
        recommendation_ids = tuple(item.id.value for item in recommendations)
        rationales = (
            tuple(
                _decode_editorial_recommendation_rationale(item)
                for item in _execute_many(
                    self._session,
                    select(self._rationale)
                    .where(self._rationale.c.recommendation_id.in_(recommendation_ids))
                    .order_by(self._rationale.c.id),
                )
            )
            if recommendation_ids
            else ()
        )
        comments = tuple(
            _decode_editorial_review_comment(item)
            for item in _execute_many(
                self._session,
                select(self._comment)
                .where(self._comment.c.article_version_id == version_id.value)
                .order_by(self._comment.c.id),
            )
        )
        metadata = tuple(
            _decode_editorial_seo_metadata_version(item)
            for item in _execute_many(
                self._session,
                select(self._seo)
                .where(self._seo.c.article_version_id == version_id.value)
                .order_by(self._seo.c.id),
            )
        )
        manifests = tuple(
            _decode_editorial_structured_data_manifest(item)
            for item in _execute_many(
                self._session,
                select(self._manifest)
                .where(self._manifest.c.article_version_id == version_id.value)
                .order_by(self._manifest.c.id),
            )
        )
        version = ArticleVersion(
            state=state,
            article_rows=article_rows,
            article_block_rows=blocks,
            article_block_product_rows=block_products,
            article_disclosure_context_rows=disclosures,
            article_methodology_binding_rows=bindings,
            comparison_axis_rows=axes,
            comparison_value_rows=values,
            recommendation_set_rows=sets,
            recommendation_rows=recommendations,
            recommendation_rationale_rows=rationales,
            review_comment_rows=comments,
            seo_metadata_version_rows=metadata,
            structured_data_manifest_rows=manifests,
        )
        try:
            self._validate_version(version)
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return version

    @staticmethod
    def _validate_version(version: ArticleVersion) -> None:
        if type(version) is not ArticleVersion:
            raise ValueError("INVALID_ARTICLE_VERSION") from None
        version_id = version.state.id
        article_ids = frozenset(item.id for item in version.article_rows)
        block_ids = frozenset(item.id for item in version.article_block_rows)
        block_product_ids = frozenset(
            (item.article_block_id, item.product_id, item.placement_role)
            for item in version.article_block_product_rows
        )
        axis_ids = frozenset(item.id for item in version.comparison_axis_rows)
        value_ids = frozenset(item.id for item in version.comparison_value_rows)
        set_ids = frozenset(item.id for item in version.recommendation_set_rows)
        recommendation_ids = frozenset(item.id for item in version.recommendation_rows)
        rationale_ids = frozenset(
            item.id for item in version.recommendation_rationale_rows
        )
        if (
            len(article_ids) != len(version.article_rows)
            or len(block_ids) != len(version.article_block_rows)
            or len(block_product_ids) != len(version.article_block_product_rows)
            or len(axis_ids) != len(version.comparison_axis_rows)
            or len(value_ids) != len(version.comparison_value_rows)
            or len(set_ids) != len(version.recommendation_set_rows)
            or len(recommendation_ids) != len(version.recommendation_rows)
            or len(rationale_ids) != len(version.recommendation_rationale_rows)
            or any(item.id != version.state.article_id for item in version.article_rows)
            or any(
                item.article_version_id != version_id
                for item in version.article_block_rows
            )
            or any(
                item.article_block_id not in block_ids
                for item in version.article_block_product_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.article_disclosure_context_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.article_methodology_binding_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.comparison_axis_rows
            )
            or any(
                item.comparison_axis_id not in axis_ids
                for item in version.comparison_value_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.recommendation_set_rows
            )
            or any(
                item.recommendation_set_id not in set_ids
                for item in version.recommendation_rows
            )
            or any(
                item.recommendation_id not in recommendation_ids
                for item in version.recommendation_rationale_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.review_comment_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.seo_metadata_version_rows
            )
            or any(
                item.article_version_id != version_id
                for item in version.structured_data_manifest_rows
            )
        ):
            raise ValueError("INVALID_ARTICLE_VERSION") from None

    def add_version(self, version: ArticleVersion) -> AggregateVersion:
        self._validate_version(version)
        if (
            version.state.lock_version.value != 0
            or version.article_rows
            or version.article_disclosure_context_rows
            or version.article_methodology_binding_rows
            or version.review_comment_rows
            or version.seo_metadata_version_rows
            or version.structured_data_manifest_rows
        ):
            raise ValueError("INVALID_ARTICLE_VERSION") from None
        register_pending_events(
            self._session,
            aggregate_type="editorial.article_version",
            aggregate_id=version.state.id.value,
            buffer=aggregate_events_buffer(version),
        )
        _execute(
            self._session,
            insert(self._version).values(
                **_encode_editorial_article_version(version.state)
            ),
        )
        for block in version.article_block_rows:
            _execute(
                self._session,
                insert(self._block).values(**_encode_editorial_article_block(block)),
            )
        for block_product in version.article_block_product_rows:
            _execute(
                self._session,
                insert(self._block_product).values(
                    **_encode_editorial_article_block_product(block_product)
                ),
            )
        for axis in version.comparison_axis_rows:
            _execute(
                self._session,
                insert(self._axis).values(**_encode_editorial_comparison_axis(axis)),
            )
        for comparison_value in version.comparison_value_rows:
            _execute(
                self._session,
                insert(self._value).values(
                    **_encode_editorial_comparison_value(comparison_value)
                ),
            )
        for recommendation_set in version.recommendation_set_rows:
            _execute(
                self._session,
                insert(self._recommendation_set).values(
                    **_encode_editorial_recommendation_set(recommendation_set)
                ),
            )
        for recommendation in version.recommendation_rows:
            _execute(
                self._session,
                insert(self._recommendation).values(
                    **_encode_editorial_recommendation(recommendation)
                ),
            )
        for rationale in version.recommendation_rationale_rows:
            _execute(
                self._session,
                insert(self._rationale).values(
                    **_encode_editorial_recommendation_rationale(rationale)
                ),
            )
        persisted = AggregateVersion(0)
        stage_registered_events(
            self._session,
            aggregate_type="editorial.article_version",
            aggregate_id=version.state.id.value,
            owning_method="ArticleRepository.add_version",
            persisted_version=persisted,
            expected_event_type="jp.raos.editorial.draft_generated.v1",
        )
        return persisted

    def save_version(
        self,
        version: ArticleVersion,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        self._validate_version(version)
        if (
            type(expected_version) is not AggregateVersion
            or version.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_ARTICLE_VERSION") from None
        current = self._get_version(version.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current_blocks = {item.id: item for item in current.article_block_rows}
        proposed_blocks = {item.id: item for item in version.article_block_rows}
        current_block_products = {
            (item.article_block_id, item.product_id, item.placement_role): item
            for item in current.article_block_product_rows
        }
        proposed_block_products = {
            (item.article_block_id, item.product_id, item.placement_role): item
            for item in version.article_block_product_rows
        }
        current_axes = {item.id: item for item in current.comparison_axis_rows}
        proposed_axes = {item.id: item for item in version.comparison_axis_rows}
        current_values = {item.id: item for item in current.comparison_value_rows}
        proposed_values = {item.id: item for item in version.comparison_value_rows}
        current_sets = {item.id: item for item in current.recommendation_set_rows}
        proposed_sets = {item.id: item for item in version.recommendation_set_rows}
        current_recommendations = {
            item.id: item for item in current.recommendation_rows
        }
        proposed_recommendations = {
            item.id: item for item in version.recommendation_rows
        }
        current_rationales = {
            item.id: item for item in current.recommendation_rationale_rows
        }
        proposed_rationales = {
            item.id: item for item in version.recommendation_rationale_rows
        }
        if (
            len(current_blocks) != len(current.article_block_rows)
            or len(proposed_blocks) != len(version.article_block_rows)
            or len(current_block_products) != len(current.article_block_product_rows)
            or len(proposed_block_products) != len(version.article_block_product_rows)
            or len(current_axes) != len(current.comparison_axis_rows)
            or len(proposed_axes) != len(version.comparison_axis_rows)
            or len(current_values) != len(current.comparison_value_rows)
            or len(proposed_values) != len(version.comparison_value_rows)
            or len(current_sets) != len(current.recommendation_set_rows)
            or len(proposed_sets) != len(version.recommendation_set_rows)
            or len(current_recommendations) != len(current.recommendation_rows)
            or len(proposed_recommendations) != len(version.recommendation_rows)
            or len(current_rationales) != len(current.recommendation_rationale_rows)
            or len(proposed_rationales) != len(version.recommendation_rationale_rows)
        ):
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        if (
            not current_blocks.keys() <= proposed_blocks.keys()
            or any(
                proposed_blocks[key] != value for key, value in current_blocks.items()
            )
            or not current_block_products.keys() <= proposed_block_products.keys()
            or any(
                proposed_block_products[key] != value
                for key, value in current_block_products.items()
            )
            or not current_axes.keys() <= proposed_axes.keys()
            or any(proposed_axes[key] != value for key, value in current_axes.items())
            or not current_values.keys() <= proposed_values.keys()
            or any(
                proposed_values[key] != value for key, value in current_values.items()
            )
            or not current_sets.keys() <= proposed_sets.keys()
            or any(proposed_sets[key] != value for key, value in current_sets.items())
            or not current_recommendations.keys() <= proposed_recommendations.keys()
            or any(
                proposed_recommendations[key] != value
                for key, value in current_recommendations.items()
            )
            or not current_rationales.keys() <= proposed_rationales.keys()
            or any(
                proposed_rationales[key] != value
                for key, value in current_rationales.items()
            )
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        new_blocks = tuple(
            item for key, item in proposed_blocks.items() if key not in current_blocks
        )
        new_block_products = tuple(
            item
            for key, item in proposed_block_products.items()
            if key not in current_block_products
        )
        new_axes = tuple(
            item for key, item in proposed_axes.items() if key not in current_axes
        )
        new_values = tuple(
            item for key, item in proposed_values.items() if key not in current_values
        )
        new_sets = tuple(
            item for key, item in proposed_sets.items() if key not in current_sets
        )
        new_recommendations = tuple(
            item
            for key, item in proposed_recommendations.items()
            if key not in current_recommendations
        )
        new_rationales = tuple(
            item
            for key, item in proposed_rationales.items()
            if key not in current_rationales
        )
        if (
            current.article_rows != version.article_rows
            or current.article_disclosure_context_rows
            != version.article_disclosure_context_rows
            or current.article_methodology_binding_rows
            != version.article_methodology_binding_rows
            or current.review_comment_rows != version.review_comment_rows
            or current.seo_metadata_version_rows != version.seo_metadata_version_rows
            or current.structured_data_manifest_rows
            != version.structured_data_manifest_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        register_pending_events(
            self._session,
            aggregate_type="editorial.article_version",
            aggregate_id=version.state.id.value,
            buffer=aggregate_events_buffer(version),
        )
        persisted = _cas_update(
            self._session,
            self._version,
            version.state.id.value,
            expected_version,
            _encode_editorial_article_version(version.state),
        )
        for block in new_blocks:
            if type(block) is not ArticleBlock:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._block).values(**_encode_editorial_article_block(block)),
            )
        for block_product in new_block_products:
            if type(block_product) is not ArticleBlockProduct:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._block_product).values(
                    **_encode_editorial_article_block_product(block_product)
                ),
            )
        for axis in new_axes:
            if type(axis) is not ComparisonAxis:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._axis).values(**_encode_editorial_comparison_axis(axis)),
            )
        for comparison_value in new_values:
            if type(comparison_value) is not ComparisonValue:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._value).values(
                    **_encode_editorial_comparison_value(comparison_value)
                ),
            )
        for recommendation_set in new_sets:
            if type(recommendation_set) is not RecommendationSet:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._recommendation_set).values(
                    **_encode_editorial_recommendation_set(recommendation_set)
                ),
            )
        for recommendation in new_recommendations:
            if type(recommendation) is not Recommendation:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._recommendation).values(
                    **_encode_editorial_recommendation(recommendation)
                ),
            )
        for rationale in new_rationales:
            if type(rationale) is not RecommendationRationale:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            _execute(
                self._session,
                insert(self._rationale).values(
                    **_encode_editorial_recommendation_rationale(rationale)
                ),
            )
        if version.pending_events():
            stage_registered_events(
                self._session,
                aggregate_type="editorial.article_version",
                aggregate_id=version.state.id.value,
                owning_method="ArticleRepository.save_version",
                persisted_version=persisted,
                expected_event_type="jp.raos.editorial.article_version_submitted.v1",
            )
        return persisted

    def assign_slug(self, slug: ArticleSlug) -> None:
        if type(slug) is not ArticleSlug:
            raise ValueError("INVALID_ARTICLE_SLUG") from None
        _execute(
            self._session,
            insert(self._slug).values(**_encode_editorial_article_slug(slug.state)),
        )

    def transition_slug(
        self,
        slug_id: ArticleSlugId,
        transition: ArticleSlug,
        expected_status: ArticleSlugStatus,
    ) -> ArticleSlug:
        if (
            type(slug_id) is not ArticleSlugId
            or type(transition) is not ArticleSlug
            or type(expected_status) is not ArticleSlugStatus
            or transition.state.id != slug_id
        ):
            raise ValueError("INVALID_ARTICLE_SLUG_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._slug).where(self._slug.c.id == slug_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_article_slug(current_row)
        edge = (expected_status.value, transition.state.status.value)
        at = transaction_timestamp(self._session)
        if (
            current.status is not expected_status
            or edge not in self._SLUG_EDGES
            or not _same_except(
                _encode_editorial_article_slug(current),
                _encode_editorial_article_slug(transition.state),
                ("status", "valid_to"),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if expected_status.value == "ACTIVE" and (
            current.valid_to is not None or transition.state.valid_to != at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if expected_status.value == "REDIRECTED" and (
            transition.state.valid_to != current.valid_to
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        row = _execute_one(
            self._session,
            update(self._slug)
            .where(
                self._slug.c.id == slug_id.value,
                self._slug.c.status == expected_status.value,
                *(
                    (self._slug.c.valid_to.is_(None),)
                    if expected_status.value == "ACTIVE"
                    else ()
                ),
            )
            .values(
                status=transition.state.status.value,
                valid_to=(at.value if transition.state.valid_to is not None else None),
            )
            .returning(self._slug),
        )
        if row is None:
            _state_zero(
                self._session,
                self._slug,
                "id",
                slug_id.value,
                "status",
                expected_status.value,
            )
        return ArticleSlug(_decode_editorial_article_slug(row))

    def add_link(self, link: ArticleLinkState) -> AggregateVersion:
        if type(link) is not ArticleLinkState or link.lock_version.value != 0:
            raise ValueError("INVALID_ARTICLE_LINK") from None
        _execute(
            self._session,
            insert(self._link).values(**_encode_editorial_article_link(link)),
        )
        return AggregateVersion(0)

    def save_link(
        self,
        link: ArticleLinkState,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(link) is not ArticleLinkState
            or type(expected_version) is not AggregateVersion
            or link.lock_version != expected_version
        ):
            raise ValueError("INVALID_ARTICLE_LINK") from None
        return _cas_update(
            self._session,
            self._link,
            link.id.value,
            expected_version,
            _encode_editorial_article_link(link),
        )


@guard_repository_class
class SqlAlchemyReviewCommentRepository:
    __slots__ = ("_comment", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._comment = _table("editorial.review_comment")

    def get(self, comment_id: ReviewCommentId) -> ReviewComment | None:
        if type(comment_id) is not ReviewCommentId:
            raise ValueError("INVALID_REVIEW_COMMENT_ID") from None
        row = _execute_one(
            self._session,
            select(self._comment).where(self._comment.c.id == comment_id.value),
        )
        return (
            None
            if row is None
            else ReviewComment(_decode_editorial_review_comment(row))
        )

    def append(self, comment: ReviewComment) -> None:
        if type(comment) is not ReviewComment:
            raise ValueError("INVALID_REVIEW_COMMENT") from None
        _execute(
            self._session,
            insert(self._comment).values(
                **_encode_editorial_review_comment(comment.state)
            ),
        )

    def close(
        self,
        comment_id: ReviewCommentId,
        resolution: ReviewComment,
        expected_status: ReviewCommentStatus,
    ) -> ReviewComment:
        if (
            type(comment_id) is not ReviewCommentId
            or type(resolution) is not ReviewComment
            or type(expected_status) is not ReviewCommentStatus
            or resolution.state.id != comment_id
        ):
            raise ValueError("INVALID_REVIEW_COMMENT_CLOSE") from None
        current_row = _execute_one(
            self._session,
            select(self._comment).where(self._comment.c.id == comment_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_review_comment(current_row)
        context_principal = _context_principal_id(self._session)
        if (
            current.status is not expected_status
            or expected_status.value != "OPEN"
            or resolution.state.status.value not in {"RESOLVED", "WONT_FIX"}
            or not _same_except(
                _encode_editorial_review_comment(current),
                _encode_editorial_review_comment(resolution.state),
                ("status", "resolved_by_principal_id", "resolved_at"),
            )
            or current.resolved_by_principal_id is not None
            or current.resolved_at is not None
            or resolution.state.resolved_by_principal_id != context_principal
            or resolution.state.resolved_at is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        row = _execute_one(
            self._session,
            update(self._comment)
            .where(
                self._comment.c.id == comment_id.value,
                self._comment.c.status == expected_status.value,
                self._comment.c.resolved_by_principal_id.is_(None),
                self._comment.c.resolved_at.is_(None),
            )
            .values(
                status=resolution.state.status.value,
                resolved_by_principal_id=context_principal.value,
                resolved_at=resolution.state.resolved_at.value,
            )
            .returning(self._comment),
        )
        if row is None:
            _state_zero(
                self._session,
                self._comment,
                "id",
                comment_id.value,
                "status",
                expected_status.value,
            )
        return ReviewComment(_decode_editorial_review_comment(row))


@guard_repository_class
class SqlAlchemyMediaAssetRepository:
    __slots__ = ("_asset", "_session")

    _EDGES = frozenset(
        {
            ("DRAFT", "APPROVED"),
            ("DRAFT", "BLOCKED"),
            ("DRAFT", "RETIRED"),
            ("APPROVED", "BLOCKED"),
            ("APPROVED", "RETIRED"),
            ("BLOCKED", "RETIRED"),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._asset = _table("editorial.media_asset")

    def get(self, asset_id: MediaAssetId) -> MediaAsset | None:
        if type(asset_id) is not MediaAssetId:
            raise ValueError("INVALID_MEDIA_ASSET_ID") from None
        row = _execute_one(
            self._session,
            select(self._asset).where(self._asset.c.id == asset_id.value),
        )
        return None if row is None else MediaAsset(_decode_editorial_media_asset(row))

    def add(self, asset: MediaAsset) -> None:
        if type(asset) is not MediaAsset:
            raise ValueError("INVALID_MEDIA_ASSET") from None
        _execute(
            self._session,
            insert(self._asset).values(**_encode_editorial_media_asset(asset.state)),
        )

    def transition(
        self,
        asset_id: MediaAssetId,
        transition: MediaAsset,
        expected_status: MediaAssetStatus,
    ) -> MediaAsset:
        if (
            type(asset_id) is not MediaAssetId
            or type(transition) is not MediaAsset
            or type(expected_status) is not MediaAssetStatus
            or transition.state.id != asset_id
        ):
            raise ValueError("INVALID_MEDIA_ASSET_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._asset).where(self._asset.c.id == asset_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_media_asset(current_row)
        edge = (expected_status.value, transition.state.status.value)
        context_principal = (
            _context_principal_id(self._session)
            if edge == ("DRAFT", "APPROVED")
            else None
        )
        at = (
            transaction_timestamp(self._session)
            if edge == ("DRAFT", "APPROVED")
            else None
        )
        if (
            current.status is not expected_status
            or edge not in self._EDGES
            or not _same_except(
                _encode_editorial_media_asset(current),
                _encode_editorial_media_asset(transition.state),
                ("status", "approved_by_principal_id", "approved_at"),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approving = edge == ("DRAFT", "APPROVED")
        if approving:
            if (
                current.approved_by_principal_id is not None
                or current.approved_at is not None
                or transition.state.approved_by_principal_id != context_principal
                or transition.state.approved_at != at
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        values: dict[str, object] = {"status": transition.state.status.value}
        predicates = [
            self._asset.c.id == asset_id.value,
            self._asset.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._asset.c.approved_by_principal_id.is_(None),
                    self._asset.c.approved_at.is_(None),
                ]
            )
        if approving:
            if context_principal is None or at is None:
                _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
            values.update(
                approved_by_principal_id=context_principal.value,
                approved_at=at.value,
            )
        row = _execute_one(
            self._session,
            update(self._asset)
            .where(*predicates)
            .values(**values)
            .returning(self._asset),
        )
        if row is None:
            _state_zero(
                self._session,
                self._asset,
                "id",
                asset_id.value,
                "status",
                expected_status.value,
            )
        return MediaAsset(_decode_editorial_media_asset(row))


@guard_repository_class
class SqlAlchemyEditorialContractRepository:
    __slots__ = (
        "_article",
        "_article_type",
        "_binding",
        "_content_schema",
        "_disclosure",
        "_manifest",
        "_methodology",
        "_seo",
        "_session",
        "_template",
        "_version",
    )

    _APPROVAL_EDGES = frozenset(
        {
            ("DRAFT", "ACTIVE"),
            ("DRAFT", "RETIRED"),
            ("ACTIVE", "DEPRECATED"),
            ("ACTIVE", "RETIRED"),
            ("DEPRECATED", "RETIRED"),
        }
    )
    _SEO_EDGES = frozenset(
        {
            ("DRAFT", "VALIDATED"),
            ("DRAFT", "REJECTED"),
            ("VALIDATED", "APPROVED"),
            ("VALIDATED", "REJECTED"),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._article = _table("editorial.article")
        self._version = _table("editorial.article_version")
        self._disclosure = _table("editorial.article_disclosure_context")
        self._binding = _table("editorial.article_methodology_binding")
        self._template = _table("editorial.article_template_version")
        self._article_type = _table("editorial.article_type_version")
        self._content_schema = _table("editorial.content_schema_version")
        self._methodology = _table("editorial.editorial_methodology_version")
        self._seo = _table("editorial.seo_metadata_version")
        self._manifest = _table("editorial.structured_data_manifest")

    def _observed_series(
        self,
        table: Table,
        predicates: tuple[ColumnElement[bool], ...],
    ) -> int | None:
        rows = _execute_many(
            self._session,
            select(table.c.id)
            .where(*predicates)
            .order_by(table.c.created_at, table.c.id)
            .with_for_update(),
        )
        return None if not rows else len(rows)

    def get_disclosure_context(
        self,
        article_version_id: ArticleVersionId,
    ) -> ArticleDisclosureContext | None:
        if type(article_version_id) is not ArticleVersionId:
            raise ValueError("INVALID_DISCLOSURE_CONTEXT_ID") from None
        row = _execute_one(
            self._session,
            select(self._disclosure).where(
                self._disclosure.c.article_version_id == article_version_id.value
            ),
        )
        return (
            None if row is None else _decode_editorial_article_disclosure_context(row)
        )

    def add_disclosure_context(
        self,
        context: ArticleDisclosureContext,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(context) is not ArticleDisclosureContext
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_DISCLOSURE_CONTEXT") from None
        persisted = _cas_update(
            self._session,
            self._version,
            context.article_version_id.value,
            expected_version,
            {},
        )
        _execute(
            self._session,
            insert(self._disclosure).values(
                **_encode_editorial_article_disclosure_context(context)
            ),
        )
        return persisted

    def record_disclosure_review(
        self,
        article_version_id: ArticleVersionId,
        review: ArticleDisclosureContext,
        expected_version: AggregateVersion,
    ) -> ArticleDisclosureContext:
        if (
            type(article_version_id) is not ArticleVersionId
            or type(review) is not ArticleDisclosureContext
            or type(expected_version) is not AggregateVersion
            or review.article_version_id != article_version_id
            or review.reviewed_by_principal_id is None
            or review.reviewed_at is None
        ):
            raise ValueError("INVALID_DISCLOSURE_REVIEW") from None
        current_row = _execute_one(
            self._session,
            select(self._disclosure).where(
                self._disclosure.c.article_version_id == article_version_id.value
            ),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_article_disclosure_context(current_row)
        context_principal = _context_principal_id(self._session)
        if (
            current.reviewed_by_principal_id is not None
            or current.reviewed_at is not None
            or not _same_except(
                _encode_editorial_article_disclosure_context(current),
                _encode_editorial_article_disclosure_context(review),
                ("reviewed_by_principal_id", "reviewed_at"),
            )
            or review.reviewed_by_principal_id != context_principal
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        _cas_update(
            self._session,
            self._version,
            article_version_id.value,
            expected_version,
            {},
        )
        row = _execute_one(
            self._session,
            update(self._disclosure)
            .where(
                self._disclosure.c.article_version_id == article_version_id.value,
                self._disclosure.c.reviewed_by_principal_id.is_(None),
                self._disclosure.c.reviewed_at.is_(None),
            )
            .values(
                reviewed_by_principal_id=context_principal.value,
                reviewed_at=review.reviewed_at.value,
            )
            .returning(self._disclosure),
        )
        if row is None:
            observed = _execute_one(
                self._session,
                select(
                    self._disclosure.c.article_version_id,
                    self._disclosure.c.reviewed_by_principal_id,
                    self._disclosure.c.reviewed_at,
                ).where(
                    self._disclosure.c.article_version_id == article_version_id.value
                ),
            )
            if observed is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            if (
                observed["reviewed_by_principal_id"] is not None
                or observed["reviewed_at"] is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return _decode_editorial_article_disclosure_context(row)

    def append_methodology_binding(
        self,
        binding: ArticleMethodologyBinding,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(binding) is not ArticleMethodologyBinding
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_METHODOLOGY_BINDING") from None
        persisted = _cas_update(
            self._session,
            self._version,
            binding.article_version_id.value,
            expected_version,
            {},
        )
        _execute(
            self._session,
            insert(self._binding).values(
                **_encode_editorial_article_methodology_binding(binding)
            ),
        )
        return persisted

    def get_current_article_type(self, code: str) -> ArticleTypeVersion | None:
        if type(code) is not str or not code:
            raise ValueError("INVALID_ARTICLE_TYPE_CODE") from None
        row = _execute_one(
            self._session,
            select(self._article_type)
            .where(
                self._article_type.c.article_type_code == code,
                self._article_type.c.status == "ACTIVE",
            )
            .order_by(
                self._article_type.c.created_at.desc(),
                self._article_type.c.id.desc(),
            )
            .limit(1),
        )
        if row is None:
            return None
        state = _decode_editorial_article_type_version(row)
        templates = tuple(
            _decode_editorial_article_template_version(item)
            for item in _execute_many(
                self._session,
                select(self._template)
                .where(self._template.c.article_type_version_id == state.id.value)
                .order_by(self._template.c.id),
            )
        )
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.article_type_version_id == state.id.value)
                .order_by(self._version.c.id),
            )
        )
        methodologies = tuple(
            _decode_editorial_editorial_methodology_version(item)
            for item in _execute_many(
                self._session,
                select(self._methodology)
                .where(self._methodology.c.article_type_version_id == state.id.value)
                .order_by(self._methodology.c.id),
            )
        )
        return ArticleTypeVersion(
            state=state,
            article_template_version_rows=templates,
            article_version_rows=versions,
            editorial_methodology_version_rows=methodologies,
        )

    def append_article_type_version(
        self,
        version: ArticleTypeVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        _validate_latest(expected_latest_version)
        if (
            type(version) is not ArticleTypeVersion
            or version.article_template_version_rows
            or version.article_version_rows
            or version.editorial_methodology_version_rows
        ):
            raise ValueError("INVALID_ARTICLE_TYPE_VERSION_APPEND") from None
        observed = self._observed_series(
            self._article_type,
            (
                self._article_type.c.article_type_code
                == version.state.article_type_code,
            ),
        )
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        _execute(
            self._session,
            insert(self._article_type).values(
                **_encode_editorial_article_type_version(version.state)
            ),
        )
        return AggregateVersion(1 if observed is None else observed + 1)

    def _wrap_article_type(
        self,
        state: ArticleTypeVersionState,
    ) -> ArticleTypeVersion:
        templates = tuple(
            _decode_editorial_article_template_version(item)
            for item in _execute_many(
                self._session,
                select(self._template)
                .where(self._template.c.article_type_version_id == state.id.value)
                .order_by(self._template.c.id),
            )
        )
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.article_type_version_id == state.id.value)
                .order_by(self._version.c.id),
            )
        )
        methodologies = tuple(
            _decode_editorial_editorial_methodology_version(item)
            for item in _execute_many(
                self._session,
                select(self._methodology)
                .where(self._methodology.c.article_type_version_id == state.id.value)
                .order_by(self._methodology.c.id),
            )
        )
        return ArticleTypeVersion(
            state=state,
            article_template_version_rows=templates,
            article_version_rows=versions,
            editorial_methodology_version_rows=methodologies,
        )

    def transition_article_type_version(
        self,
        id: ArticleTypeVersionId,
        transition: ArticleTypeVersion,
        expected_status: ArticleTypeVersionStatus,
    ) -> ArticleTypeVersion:
        if (
            type(id) is not ArticleTypeVersionId
            or type(transition) is not ArticleTypeVersion
            or type(expected_status) is not ArticleTypeVersionStatus
            or transition.state.id != id
        ):
            raise ValueError("INVALID_ARTICLE_TYPE_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._article_type).where(self._article_type.c.id == id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_article_type_version(current_row)
        edge = (expected_status.value, transition.state.status.value)
        if (
            current.status is not expected_status
            or edge not in self._APPROVAL_EDGES
            or not _same_except(
                _encode_editorial_article_type_version(current),
                _encode_editorial_article_type_version(transition.state),
                ("status", "approved_by_principal_id", "approved_at"),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approving = edge == ("DRAFT", "ACTIVE")
        approval: tuple[PrincipalId, AwareUtcDateTime] | None = None
        if approving:
            if (
                current.approved_by_principal_id is not None
                or current.approved_at is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            approval = _context_approval(
                self._session,
                transition.state.approved_by_principal_id,
                transition.state.approved_at,
            )
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        predicates = [
            self._article_type.c.id == id.value,
            self._article_type.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._article_type.c.approved_by_principal_id.is_(None),
                    self._article_type.c.approved_at.is_(None),
                ]
            )
        else:
            predicates.extend(
                [
                    self._article_type.c.approved_by_principal_id.is_not(None),
                    self._article_type.c.approved_at.is_not(None),
                ]
            )
        values: dict[str, object] = {"status": transition.state.status.value}
        if approval is not None:
            principal, approved_at = approval
            values.update(
                approved_by_principal_id=principal.value,
                approved_at=approved_at.value,
            )
        current_aggregate = self._wrap_article_type(current)
        if (
            transition.article_template_version_rows
            != current_aggregate.article_template_version_rows
            or transition.article_version_rows != current_aggregate.article_version_rows
            or transition.editorial_methodology_version_rows
            != current_aggregate.editorial_methodology_version_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        row = _execute_one(
            self._session,
            update(self._article_type)
            .where(*predicates)
            .values(**values)
            .returning(self._article_type),
        )
        if row is None:
            _state_zero(
                self._session,
                self._article_type,
                "id",
                id.value,
                "status",
                expected_status.value,
            )
        return self._wrap_article_type(_decode_editorial_article_type_version(row))

    def get_current_content_schema(
        self,
        code: str,
    ) -> ContentSchemaVersion | None:
        if type(code) is not str or not code:
            raise ValueError("INVALID_CONTENT_SCHEMA_CODE") from None
        row = _execute_one(
            self._session,
            select(self._content_schema)
            .where(
                self._content_schema.c.schema_code == code,
                self._content_schema.c.status == "ACTIVE",
            )
            .order_by(
                self._content_schema.c.created_at.desc(),
                self._content_schema.c.id.desc(),
            )
            .limit(1),
        )
        if row is None:
            return None
        return self._wrap_content_schema(_decode_editorial_content_schema_version(row))

    def _wrap_content_schema(
        self,
        state: ContentSchemaVersionState,
    ) -> ContentSchemaVersion:
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.content_schema_version_id == state.id.value)
                .order_by(self._version.c.id),
            )
        )
        return ContentSchemaVersion(state=state, article_version_rows=versions)

    def append_content_schema_version(
        self,
        version: ContentSchemaVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        _validate_latest(expected_latest_version)
        if type(version) is not ContentSchemaVersion or version.article_version_rows:
            raise ValueError("INVALID_CONTENT_SCHEMA_APPEND") from None
        observed = self._observed_series(
            self._content_schema,
            (self._content_schema.c.schema_code == version.state.schema_code,),
        )
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        _execute(
            self._session,
            insert(self._content_schema).values(
                **_encode_editorial_content_schema_version(version.state)
            ),
        )
        return AggregateVersion(1 if observed is None else observed + 1)

    def transition_content_schema_version(
        self,
        id: ContentSchemaVersionId,
        transition: ContentSchemaVersion,
        expected_status: ContentSchemaVersionStatus,
    ) -> ContentSchemaVersion:
        if (
            type(id) is not ContentSchemaVersionId
            or type(transition) is not ContentSchemaVersion
            or type(expected_status) is not ContentSchemaVersionStatus
            or transition.state.id != id
        ):
            raise ValueError("INVALID_CONTENT_SCHEMA_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._content_schema).where(self._content_schema.c.id == id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_content_schema_version(current_row)
        edge = (expected_status.value, transition.state.status.value)
        if (
            current.status is not expected_status
            or edge not in self._APPROVAL_EDGES
            or not _same_except(
                _encode_editorial_content_schema_version(current),
                _encode_editorial_content_schema_version(transition.state),
                (
                    "status",
                    "effective_to",
                    "approved_by_principal_id",
                    "approved_at",
                ),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approving = edge == ("DRAFT", "ACTIVE")
        closing = edge in {
            ("ACTIVE", "DEPRECATED"),
            ("ACTIVE", "RETIRED"),
        }
        approval: tuple[PrincipalId, AwareUtcDateTime] | None = None
        if approving:
            if (
                current.effective_to is not None
                or transition.state.effective_to is not None
                or current.approved_by_principal_id is not None
                or current.approved_at is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            approval = _context_approval(
                self._session,
                transition.state.approved_by_principal_id,
                transition.state.approved_at,
            )
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if closing:
            if (
                current.effective_to is not None
                or transition.state.effective_to is None
                or transition.state.effective_to.value <= current.effective_from.value
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
        elif transition.state.effective_to != current.effective_to:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        predicates = [
            self._content_schema.c.id == id.value,
            self._content_schema.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._content_schema.c.approved_by_principal_id.is_(None),
                    self._content_schema.c.approved_at.is_(None),
                ]
            )
            if approving:
                predicates.append(self._content_schema.c.effective_to.is_(None))
        else:
            predicates.extend(
                [
                    self._content_schema.c.approved_by_principal_id.is_not(None),
                    self._content_schema.c.approved_at.is_not(None),
                ]
            )
        if expected_status.value == "ACTIVE":
            predicates.append(self._content_schema.c.effective_to.is_(None))
        values: dict[str, object] = {"status": transition.state.status.value}
        if approval is not None:
            principal, approved_at = approval
            values.update(
                approved_by_principal_id=principal.value,
                approved_at=approved_at.value,
                effective_to=None,
            )
        if closing:
            transition_effective_to = cast(
                AwareUtcDateTime, transition.state.effective_to
            )
            values["effective_to"] = transition_effective_to.value
            predicates.append(
                self._content_schema.c.effective_from < transition_effective_to.value
            )
        current_aggregate = self._wrap_content_schema(current)
        if transition.article_version_rows != current_aggregate.article_version_rows:
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        row = _execute_one(
            self._session,
            update(self._content_schema)
            .where(*predicates)
            .values(**values)
            .returning(self._content_schema),
        )
        if row is None:
            _state_zero(
                self._session,
                self._content_schema,
                "id",
                id.value,
                "status",
                expected_status.value,
            )
        return self._wrap_content_schema(_decode_editorial_content_schema_version(row))

    def get_current_template(
        self,
        article_type_id: ArticleTypeVersionId,
    ) -> ArticleTemplateVersion | None:
        if type(article_type_id) is not ArticleTypeVersionId:
            raise ValueError("INVALID_ARTICLE_TYPE_ID") from None
        row = _execute_one(
            self._session,
            select(self._template)
            .where(
                self._template.c.article_type_version_id == article_type_id.value,
                self._template.c.status == "ACTIVE",
            )
            .order_by(
                self._template.c.created_at.desc(),
                self._template.c.id.desc(),
            )
            .limit(1),
        )
        if row is None:
            return None
        return self._wrap_template(_decode_editorial_article_template_version(row))

    def _wrap_template(
        self,
        state: ArticleTemplateVersionState,
    ) -> ArticleTemplateVersion:
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.article_template_version_id == state.id.value)
                .order_by(self._version.c.id),
            )
        )
        return ArticleTemplateVersion(state=state, article_version_rows=versions)

    def append_template_version(
        self,
        version: ArticleTemplateVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        _validate_latest(expected_latest_version)
        if type(version) is not ArticleTemplateVersion or version.article_version_rows:
            raise ValueError("INVALID_TEMPLATE_VERSION_APPEND") from None
        observed = self._observed_series(
            self._template,
            (
                self._template.c.article_type_version_id
                == version.state.article_type_version_id.value,
            ),
        )
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        _execute(
            self._session,
            insert(self._template).values(
                **_encode_editorial_article_template_version(version.state)
            ),
        )
        return AggregateVersion(1 if observed is None else observed + 1)

    def transition_template_version(
        self,
        id: ArticleTemplateVersionId,
        transition: ArticleTemplateVersion,
        expected_status: ArticleTemplateVersionStatus,
    ) -> ArticleTemplateVersion:
        if (
            type(id) is not ArticleTemplateVersionId
            or type(transition) is not ArticleTemplateVersion
            or type(expected_status) is not ArticleTemplateVersionStatus
            or transition.state.id != id
        ):
            raise ValueError("INVALID_TEMPLATE_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._template).where(self._template.c.id == id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_article_template_version(current_row)
        edge = (expected_status.value, transition.state.status.value)
        if (
            current.status is not expected_status
            or edge not in self._APPROVAL_EDGES
            or not _same_except(
                _encode_editorial_article_template_version(current),
                _encode_editorial_article_template_version(transition.state),
                ("status", "approved_by_principal_id", "approved_at"),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approving = edge == ("DRAFT", "ACTIVE")
        approval: tuple[PrincipalId, AwareUtcDateTime] | None = None
        if approving:
            if (
                current.approved_by_principal_id is not None
                or current.approved_at is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            approval = _context_approval(
                self._session,
                transition.state.approved_by_principal_id,
                transition.state.approved_at,
            )
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        predicates = [
            self._template.c.id == id.value,
            self._template.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._template.c.approved_by_principal_id.is_(None),
                    self._template.c.approved_at.is_(None),
                ]
            )
        else:
            predicates.extend(
                [
                    self._template.c.approved_by_principal_id.is_not(None),
                    self._template.c.approved_at.is_not(None),
                ]
            )
        values: dict[str, object] = {"status": transition.state.status.value}
        if approval is not None:
            principal, approved_at = approval
            values.update(
                approved_by_principal_id=principal.value,
                approved_at=approved_at.value,
            )
        current_aggregate = self._wrap_template(current)
        if transition.article_version_rows != current_aggregate.article_version_rows:
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        row = _execute_one(
            self._session,
            update(self._template)
            .where(*predicates)
            .values(**values)
            .returning(self._template),
        )
        if row is None:
            _state_zero(
                self._session,
                self._template,
                "id",
                id.value,
                "status",
                expected_status.value,
            )
        return self._wrap_template(_decode_editorial_article_template_version(row))

    def get_current_methodology(
        self,
        code: str,
    ) -> EditorialMethodologyVersion | None:
        if type(code) is not str or not code:
            raise ValueError("INVALID_METHODOLOGY_CODE") from None
        row = _execute_one(
            self._session,
            select(self._methodology)
            .where(
                self._methodology.c.methodology_code == code,
                self._methodology.c.status == "ACTIVE",
            )
            .order_by(
                self._methodology.c.created_at.desc(),
                self._methodology.c.id.desc(),
            )
            .limit(1),
        )
        if row is None:
            return None
        return self._wrap_methodology(
            _decode_editorial_editorial_methodology_version(row)
        )

    def _wrap_methodology(
        self,
        state: EditorialMethodologyVersionState,
    ) -> EditorialMethodologyVersion:
        bindings = tuple(
            _decode_editorial_article_methodology_binding(item)
            for item in _execute_many(
                self._session,
                select(self._binding)
                .where(self._binding.c.methodology_version_id == state.id.value)
                .order_by(self._binding.c.article_version_id),
            )
        )
        return EditorialMethodologyVersion(
            state=state,
            article_methodology_binding_rows=bindings,
        )

    def append_methodology_version(
        self,
        version: EditorialMethodologyVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        _validate_latest(expected_latest_version)
        if (
            type(version) is not EditorialMethodologyVersion
            or version.article_methodology_binding_rows
        ):
            raise ValueError("INVALID_METHODOLOGY_VERSION_APPEND") from None
        observed = self._observed_series(
            self._methodology,
            (self._methodology.c.methodology_code == version.state.methodology_code,),
        )
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        _execute(
            self._session,
            insert(self._methodology).values(
                **_encode_editorial_editorial_methodology_version(version.state)
            ),
        )
        return AggregateVersion(1 if observed is None else observed + 1)

    def transition_methodology_version(
        self,
        id: EditorialMethodologyVersionId,
        transition: EditorialMethodologyVersion,
        expected_status: EditorialMethodologyVersionStatus,
    ) -> EditorialMethodologyVersion:
        if (
            type(id) is not EditorialMethodologyVersionId
            or type(transition) is not EditorialMethodologyVersion
            or type(expected_status) is not EditorialMethodologyVersionStatus
            or transition.state.id != id
        ):
            raise ValueError("INVALID_METHODOLOGY_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._methodology).where(self._methodology.c.id == id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_editorial_methodology_version(current_row)
        edge = (expected_status.value, transition.state.status.value)
        if (
            current.status is not expected_status
            or edge not in self._APPROVAL_EDGES
            or not _same_except(
                _encode_editorial_editorial_methodology_version(current),
                _encode_editorial_editorial_methodology_version(transition.state),
                ("status", "approved_by_principal_id", "approved_at"),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approving = edge == ("DRAFT", "ACTIVE")
        approval: tuple[PrincipalId, AwareUtcDateTime] | None = None
        if approving:
            if (
                current.approved_by_principal_id is not None
                or current.approved_at is not None
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
            approval = _context_approval(
                self._session,
                transition.state.approved_by_principal_id,
                transition.state.approved_at,
            )
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        predicates = [
            self._methodology.c.id == id.value,
            self._methodology.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._methodology.c.approved_by_principal_id.is_(None),
                    self._methodology.c.approved_at.is_(None),
                ]
            )
        else:
            predicates.extend(
                [
                    self._methodology.c.approved_by_principal_id.is_not(None),
                    self._methodology.c.approved_at.is_not(None),
                ]
            )
        values: dict[str, object] = {"status": transition.state.status.value}
        if approval is not None:
            principal, approved_at = approval
            values.update(
                approved_by_principal_id=principal.value,
                approved_at=approved_at.value,
            )
        current_aggregate = self._wrap_methodology(current)
        if (
            transition.article_methodology_binding_rows
            != current_aggregate.article_methodology_binding_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        row = _execute_one(
            self._session,
            update(self._methodology)
            .where(*predicates)
            .values(**values)
            .returning(self._methodology),
        )
        if row is None:
            _state_zero(
                self._session,
                self._methodology,
                "id",
                id.value,
                "status",
                expected_status.value,
            )
        return self._wrap_methodology(
            _decode_editorial_editorial_methodology_version(row)
        )

    def _wrap_seo(self, state: SeoMetadataVersionState) -> SeoMetadataVersion:
        versions = tuple(
            _decode_editorial_article_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.seo_metadata_version_id == state.id.value)
                .order_by(self._version.c.id),
            )
        )
        manifests = tuple(
            _decode_editorial_structured_data_manifest(item)
            for item in _execute_many(
                self._session,
                select(self._manifest)
                .where(self._manifest.c.seo_metadata_version_id == state.id.value)
                .order_by(self._manifest.c.id),
            )
        )
        return SeoMetadataVersion(
            state=state,
            article_version_rows=versions,
            structured_data_manifest_rows=manifests,
        )

    def append_seo_metadata_version(
        self,
        metadata: SeoMetadataVersion,
        expected_latest_version: int | None,
    ) -> AggregateVersion:
        _validate_latest(expected_latest_version)
        if (
            type(metadata) is not SeoMetadataVersion
            or metadata.article_version_rows
            or metadata.structured_data_manifest_rows
        ):
            raise ValueError("INVALID_SEO_METADATA_APPEND") from None
        observed = self._observed_series(
            self._seo,
            (
                self._seo.c.article_version_id
                == metadata.state.article_version_id.value,
            ),
        )
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        _execute(
            self._session,
            insert(self._seo).values(
                **_encode_editorial_seo_metadata_version(metadata.state)
            ),
        )
        return AggregateVersion(1 if observed is None else observed + 1)

    def transition_seo_metadata_version(
        self,
        id: SeoMetadataVersionId,
        transition: SeoMetadataVersion,
        expected_status: SeoMetadataVersionStatus,
    ) -> SeoMetadataVersion:
        if (
            type(id) is not SeoMetadataVersionId
            or type(transition) is not SeoMetadataVersion
            or type(expected_status) is not SeoMetadataVersionStatus
            or transition.state.id != id
        ):
            raise ValueError("INVALID_SEO_METADATA_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._seo).where(self._seo.c.id == id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_editorial_seo_metadata_version(current_row)
        edge = (expected_status.value, transition.state.status.value)
        if (
            current.status is not expected_status
            or edge not in self._SEO_EDGES
            or not _same_except(
                _encode_editorial_seo_metadata_version(current),
                _encode_editorial_seo_metadata_version(transition.state),
                (
                    "status",
                    "validated_at",
                    "approved_by_principal_id",
                    "approved_at",
                ),
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        validating = edge in {
            ("DRAFT", "VALIDATED"),
            ("DRAFT", "REJECTED"),
        }
        approving = edge == ("VALIDATED", "APPROVED")
        validation_at = (
            _context_time(self._session, transition.state.validated_at)
            if validating
            else None
        )
        if expected_status.value == "DRAFT" and (
            current.validated_at is not None
            or current.approved_by_principal_id is not None
            or current.approved_at is not None
            or transition.state.validated_at is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if expected_status.value == "VALIDATED" and (
            current.validated_at is None
            or current.approved_by_principal_id is not None
            or current.approved_at is not None
            or transition.state.validated_at != current.validated_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        approval: tuple[PrincipalId, AwareUtcDateTime] | None = None
        if approving:
            approval = _context_approval(
                self._session,
                transition.state.approved_by_principal_id,
                transition.state.approved_at,
            )
        elif (
            transition.state.approved_by_principal_id
            != current.approved_by_principal_id
            or transition.state.approved_at != current.approved_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        values: dict[str, object] = {"status": transition.state.status.value}
        predicates = [
            self._seo.c.id == id.value,
            self._seo.c.status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._seo.c.validated_at.is_(None),
                    self._seo.c.approved_by_principal_id.is_(None),
                    self._seo.c.approved_at.is_(None),
                ]
            )
        else:
            predicates.extend(
                [
                    self._seo.c.validated_at.is_not(None),
                    self._seo.c.approved_by_principal_id.is_(None),
                    self._seo.c.approved_at.is_(None),
                ]
            )
        if validation_at is not None:
            values["validated_at"] = validation_at.value
        if approval is not None:
            principal, approved_at = approval
            values.update(
                approved_by_principal_id=principal.value,
                approved_at=approved_at.value,
            )
        current_aggregate = self._wrap_seo(current)
        if (
            transition.article_version_rows != current_aggregate.article_version_rows
            or transition.structured_data_manifest_rows
            != current_aggregate.structured_data_manifest_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        row = _execute_one(
            self._session,
            update(self._seo).where(*predicates).values(**values).returning(self._seo),
        )
        if row is None:
            _state_zero(
                self._session,
                self._seo,
                "id",
                id.value,
                "status",
                expected_status.value,
            )
        return self._wrap_seo(_decode_editorial_seo_metadata_version(row))

    def append_structured_data_manifest(
        self,
        manifest: StructuredDataManifest,
        expected_version: AggregateVersion,
    ) -> AggregateVersion:
        if (
            type(manifest) is not StructuredDataManifest
            or type(expected_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_STRUCTURED_DATA_MANIFEST") from None
        persisted = _cas_update(
            self._session,
            self._version,
            manifest.article_version_id.value,
            expected_version,
            {},
        )
        _execute(
            self._session,
            insert(self._manifest).values(
                **_encode_editorial_structured_data_manifest(manifest)
            ),
        )
        return persisted


__all__ = [
    "SqlAlchemyArticlePlanRepository",
    "SqlAlchemyArticleRepository",
    "SqlAlchemyEditorialContractRepository",
    "SqlAlchemyMediaAssetRepository",
    "SqlAlchemyReviewCommentRepository",
]
