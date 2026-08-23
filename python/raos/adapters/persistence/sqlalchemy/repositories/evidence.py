"""Concrete scalar codecs and aggregate-specific SQLAlchemy repositories for EVIDENCE."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import json
from typing import NoReturn, TypeVar, cast
from uuid import UUID

from sqlalchemy import Table, insert, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

import raos.adapters.persistence.sqlalchemy.mappers.evidence as domain_mappers
from raos.adapters.persistence.sqlalchemy.session_runtime import (
    fail_session_operation,
    guard_repository_class,
    persistence_context,
    register_pending_events,
    stage_registered_events,
    transaction_timestamp,
)
from raos.domain.ai.ids import (
    AiAttemptId,
)
from raos.domain.catalog.ids import (
    CanonicalProductId,
    OfferId,
    ProviderEndpointId,
)
from raos.domain.editorial.ids import (
    ArticleBlockId,
    ArticlePlanId,
    ArticleVersionId,
)
from raos.domain.evidence.aggregates import (
    Claim,
    ClaimEvidenceLink,
    ClaimState,
    Fact,
    FactDerivation,
    FactState,
    FirstHandExperienceAsset,
    FirstHandExperienceRecord,
    FirstHandExperienceRecordState,
    Source,
    SourcePacket,
    SourcePacketFact,
    SourcePacketProduct,
    SourcePacketState,
    SourcePacketVersion,
    SourcePacketVersionState,
    SourceSnapshot,
    SourceState,
)
from raos.domain.evidence.enums import (
    ClaimClaimType,
    ClaimCriticality,
    ClaimEvidenceLinkSupportType,
    ClaimSupportStatus,
    FactDerivationDerivationRole,
    FactFactKind,
    FactSubjectType,
    FirstHandExperienceAssetRole,
    FirstHandExperienceStatus,
    SourceAuthorityLevel,
    SourcePacketFactUsageRole,
    SourcePacketPacketType,
    SourcePacketProductProductRole,
    SourcePacketStatus,
    SourcePacketVersionStatus,
    SourceSnapshotValidationStatus,
    SourceSourceType,
    SourceStatus,
)
from raos.domain.evidence.ids import (
    ClaimId,
    FactId,
    FirstHandExperienceRecordId,
    SourceId,
    SourcePacketId,
    SourcePacketVersionId,
    SourceSnapshotId,
)
from raos.domain.evidence.values import (
    FactLocatorJson,
    FactValueJsonJson,
    FirstHandExperienceRecordEnvironmentJson,
    FirstHandExperienceRecordProductVariantIdentityJson,
    SourceMetadataJson,
)
from raos.domain.iam.ids import (
    PrincipalId,
)
from raos.domain.ops.ids import (
    JobId,
    ObjectArtifactId,
)
from raos.domain.shared.identity import (
    ActorType,
    SubjectId,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    EmailAddress,
    GitCommitDigest,
    PersistedVersion,
    Sha256Digest,
    UriReference,
    YenMinor,
)
from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonObject, canonical_json_bytes
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode


T = TypeVar("T")


def _fail(code: PersistenceErrorCode) -> NoReturn:
    raise PersistenceError(code) from None


def _context_principal_id(session: Session, *, human: bool = False) -> PrincipalId:
    """Resolve an actor only from the immutable transaction context."""

    actor = persistence_context(session).actor
    if actor.actor_id is None or (human and actor.actor_type is not ActorType.USER):
        _fail(PersistenceErrorCode.STATE_CONFLICT)
    return PrincipalId(actor.actor_id)


def _table(relation: str) -> Table:
    try:
        from raos.adapters.persistence.sqlalchemy.generated.catalog import (
            TABLES_BY_RELATION,
        )

        table = TABLES_BY_RELATION[relation]
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


def _optional(row: Mapping[str, object], key: str, expected: type[T]) -> T | None:
    try:
        value = row[key]
    except KeyError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    if value is None:
        return None
    if type(value) is not expected:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
    return value


def _json_object(row: Mapping[str, object], key: str) -> FrozenJsonObject:
    value = _exact(row, key, dict)
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
    if type(value) is tuple and all(type(item) is str for item in value):
        return list(value)
    if type(value) in {
        FactLocatorJson,
        FactValueJsonJson,
        FirstHandExperienceRecordEnvironmentJson,
        FirstHandExperienceRecordProductVariantIdentityJson,
        SourceMetadataJson,
    }:
        wrapped = cast(
            FactLocatorJson
            | FactValueJsonJson
            | FirstHandExperienceRecordEnvironmentJson
            | FirstHandExperienceRecordProductVariantIdentityJson
            | SourceMetadataJson,
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


def _decode_evidence_claim(row: Mapping[str, object]) -> ClaimState:
    columns = (
        "id",
        "display_id",
        "article_version_id",
        "block_id",
        "claim_key",
        "claim_type",
        "claim_text",
        "criticality",
        "support_status",
        "generated_by_ai_attempt_id",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_claim_from_row(
            id=ClaimId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            article_version_id=ArticleVersionId(
                _exact(row, "article_version_id", UUID)
            ),
            block_id=(
                None
                if row["block_id"] is None
                else ArticleBlockId(_exact(row, "block_id", UUID))
            ),
            claim_key=_exact(row, "claim_key", str),
            claim_type=ClaimClaimType(_exact(row, "claim_type", str)),
            claim_text=_exact(row, "claim_text", str),
            criticality=ClaimCriticality(_exact(row, "criticality", str)),
            support_status=ClaimSupportStatus(_exact(row, "support_status", str)),
            generated_by_ai_attempt_id=(
                None
                if row["generated_by_ai_attempt_id"] is None
                else AiAttemptId(_exact(row, "generated_by_ai_attempt_id", UUID))
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_claim(value: ClaimState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "article_version_id",
            "block_id",
            "claim_key",
            "claim_type",
            "claim_text",
            "criticality",
            "support_status",
            "generated_by_ai_attempt_id",
            "created_at",
        ),
        domain_mappers.map_evidence_claim_to_row(value),
    )


def _decode_evidence_claim_evidence_link(
    row: Mapping[str, object],
) -> ClaimEvidenceLink:
    columns = (
        "claim_id",
        "fact_id",
        "support_type",
        "support_strength",
        "note",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_claim_evidence_link_from_row(
            claim_id=ClaimId(_exact(row, "claim_id", UUID)),
            fact_id=FactId(_exact(row, "fact_id", UUID)),
            support_type=ClaimEvidenceLinkSupportType(_exact(row, "support_type", str)),
            support_strength=_exact(row, "support_strength", Decimal),
            note=(None if row["note"] is None else _exact(row, "note", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_claim_evidence_link(value: ClaimEvidenceLink) -> dict[str, object]:
    return _encoded(
        (
            "claim_id",
            "fact_id",
            "support_type",
            "support_strength",
            "note",
            "created_at",
        ),
        domain_mappers.map_evidence_claim_evidence_link_to_row(value),
    )


def _decode_evidence_fact(row: Mapping[str, object]) -> FactState:
    columns = (
        "id",
        "display_id",
        "source_snapshot_id",
        "subject_type",
        "subject_id",
        "predicate",
        "value_text",
        "value_numeric",
        "value_boolean",
        "value_date",
        "value_timestamp",
        "value_json",
        "unit_code",
        "locale",
        "fact_kind",
        "confidence",
        "valid_from",
        "valid_to",
        "locator",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_fact_from_row(
            id=FactId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            source_snapshot_id=SourceSnapshotId(
                _exact(row, "source_snapshot_id", UUID)
            ),
            subject_type=FactSubjectType(_exact(row, "subject_type", str)),
            subject_id=SubjectId(_exact(row, "subject_id", UUID)),
            predicate=_exact(row, "predicate", str),
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
            value_timestamp=(
                None
                if row["value_timestamp"] is None
                else AwareUtcDateTime(_exact(row, "value_timestamp", datetime))
            ),
            value_json=(
                None
                if row["value_json"] is None
                else FactValueJsonJson(_json_object(row, "value_json"))
            ),
            unit_code=(
                None if row["unit_code"] is None else _exact(row, "unit_code", str)
            ),
            locale=(None if row["locale"] is None else _exact(row, "locale", str)),
            fact_kind=FactFactKind(_exact(row, "fact_kind", str)),
            confidence=_exact(row, "confidence", Decimal),
            valid_from=(
                None
                if row["valid_from"] is None
                else AwareUtcDateTime(_exact(row, "valid_from", datetime))
            ),
            valid_to=(
                None
                if row["valid_to"] is None
                else AwareUtcDateTime(_exact(row, "valid_to", datetime))
            ),
            locator=FactLocatorJson(_json_object(row, "locator")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_fact(value: FactState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "source_snapshot_id",
            "subject_type",
            "subject_id",
            "predicate",
            "value_text",
            "value_numeric",
            "value_boolean",
            "value_date",
            "value_timestamp",
            "value_json",
            "unit_code",
            "locale",
            "fact_kind",
            "confidence",
            "valid_from",
            "valid_to",
            "locator",
            "created_at",
        ),
        domain_mappers.map_evidence_fact_to_row(value),
    )


def _decode_evidence_fact_derivation(row: Mapping[str, object]) -> FactDerivation:
    columns = (
        "derived_fact_id",
        "input_fact_id",
        "derivation_role",
        "algorithm_version",
        "formula_description",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_fact_derivation_from_row(
            derived_fact_id=FactId(_exact(row, "derived_fact_id", UUID)),
            input_fact_id=FactId(_exact(row, "input_fact_id", UUID)),
            derivation_role=FactDerivationDerivationRole(
                _exact(row, "derivation_role", str)
            ),
            algorithm_version=_exact(row, "algorithm_version", str),
            formula_description=(
                None
                if row["formula_description"] is None
                else _exact(row, "formula_description", str)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_fact_derivation(value: FactDerivation) -> dict[str, object]:
    return _encoded(
        (
            "derived_fact_id",
            "input_fact_id",
            "derivation_role",
            "algorithm_version",
            "formula_description",
            "created_at",
        ),
        domain_mappers.map_evidence_fact_derivation_to_row(value),
    )


def _decode_evidence_first_hand_experience_asset(
    row: Mapping[str, object],
) -> FirstHandExperienceAsset:
    columns = (
        "experience_record_id",
        "artifact_id",
        "role",
        "artifact_sha256",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_first_hand_experience_asset_from_row(
            experience_record_id=FirstHandExperienceRecordId(
                _exact(row, "experience_record_id", UUID)
            ),
            artifact_id=ObjectArtifactId(_exact(row, "artifact_id", UUID)),
            role=FirstHandExperienceAssetRole(_exact(row, "role", str)),
            artifact_sha256=Sha256Digest(_exact(row, "artifact_sha256", str)),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_first_hand_experience_asset(
    value: FirstHandExperienceAsset,
) -> dict[str, object]:
    return _encoded(
        (
            "experience_record_id",
            "artifact_id",
            "role",
            "artifact_sha256",
            "created_at",
        ),
        domain_mappers.map_evidence_first_hand_experience_asset_to_row(value),
    )


def _decode_evidence_first_hand_experience_record(
    row: Mapping[str, object],
) -> FirstHandExperienceRecordState:
    columns = (
        "id",
        "display_id",
        "product_id",
        "product_variant_identity",
        "tester_principal_id",
        "procedure_version",
        "started_at",
        "ended_at",
        "environment",
        "limitations",
        "review_status",
        "reviewed_by_principal_id",
        "reviewed_at",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_first_hand_experience_record_from_row(
            id=FirstHandExperienceRecordId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            product_variant_identity=FirstHandExperienceRecordProductVariantIdentityJson(
                _json_object(row, "product_variant_identity")
            ),
            tester_principal_id=PrincipalId(_exact(row, "tester_principal_id", UUID)),
            procedure_version=_exact(row, "procedure_version", str),
            started_at=AwareUtcDateTime(_exact(row, "started_at", datetime)),
            ended_at=AwareUtcDateTime(_exact(row, "ended_at", datetime)),
            environment=FirstHandExperienceRecordEnvironmentJson(
                _json_object(row, "environment")
            ),
            limitations=_exact(row, "limitations", str),
            review_status=FirstHandExperienceStatus(_exact(row, "review_status", str)),
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


def _encode_evidence_first_hand_experience_record(
    value: FirstHandExperienceRecordState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "product_id",
            "product_variant_identity",
            "tester_principal_id",
            "procedure_version",
            "started_at",
            "ended_at",
            "environment",
            "limitations",
            "review_status",
            "reviewed_by_principal_id",
            "reviewed_at",
            "created_at",
        ),
        domain_mappers.map_evidence_first_hand_experience_record_to_row(value),
    )


def _decode_evidence_source(row: Mapping[str, object]) -> SourceState:
    columns = (
        "id",
        "display_id",
        "source_type",
        "provider_endpoint_id",
        "name",
        "base_url",
        "authority_level",
        "permitted_use",
        "terms_checked_at",
        "terms_checked_by_principal_id",
        "status",
        "metadata",
        "created_at",
        "updated_at",
        "lock_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_from_row(
            id=SourceId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            source_type=SourceSourceType(_exact(row, "source_type", str)),
            provider_endpoint_id=(
                None
                if row["provider_endpoint_id"] is None
                else ProviderEndpointId(_exact(row, "provider_endpoint_id", UUID))
            ),
            name=_exact(row, "name", str),
            base_url=(
                None
                if row["base_url"] is None
                else UriReference(_exact(row, "base_url", str))
            ),
            authority_level=SourceAuthorityLevel(_exact(row, "authority_level", str)),
            permitted_use=_exact(row, "permitted_use", str),
            terms_checked_at=(
                None
                if row["terms_checked_at"] is None
                else AwareUtcDateTime(_exact(row, "terms_checked_at", datetime))
            ),
            terms_checked_by_principal_id=(
                None
                if row["terms_checked_by_principal_id"] is None
                else PrincipalId(_exact(row, "terms_checked_by_principal_id", UUID))
            ),
            status=SourceStatus(_exact(row, "status", str)),
            metadata=SourceMetadataJson(_json_object(row, "metadata")),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source(value: SourceState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "source_type",
            "provider_endpoint_id",
            "name",
            "base_url",
            "authority_level",
            "permitted_use",
            "terms_checked_at",
            "terms_checked_by_principal_id",
            "status",
            "metadata",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_evidence_source_to_row(value),
    )


def _decode_evidence_source_packet(row: Mapping[str, object]) -> SourcePacketState:
    columns = (
        "id",
        "display_id",
        "article_plan_id",
        "packet_type",
        "status",
        "current_version_no",
        "created_at",
        "updated_at",
        "lock_version",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_packet_from_row(
            id=SourcePacketId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            article_plan_id=ArticlePlanId(_exact(row, "article_plan_id", UUID)),
            packet_type=SourcePacketPacketType(_exact(row, "packet_type", str)),
            status=SourcePacketStatus(_exact(row, "status", str)),
            current_version_no=_exact(row, "current_version_no", int),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
            updated_at=AwareUtcDateTime(_exact(row, "updated_at", datetime)),
            lock_version=AggregateVersion(_exact(row, "lock_version", int)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source_packet(value: SourcePacketState) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "article_plan_id",
            "packet_type",
            "status",
            "current_version_no",
            "created_at",
            "updated_at",
            "lock_version",
        ),
        domain_mappers.map_evidence_source_packet_to_row(value),
    )


def _decode_evidence_source_packet_fact(row: Mapping[str, object]) -> SourcePacketFact:
    columns = (
        "source_packet_version_id",
        "fact_id",
        "usage_role",
        "display_order",
        "is_required",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_packet_fact_from_row(
            source_packet_version_id=SourcePacketVersionId(
                _exact(row, "source_packet_version_id", UUID)
            ),
            fact_id=FactId(_exact(row, "fact_id", UUID)),
            usage_role=SourcePacketFactUsageRole(_exact(row, "usage_role", str)),
            display_order=_exact(row, "display_order", int),
            is_required=_exact(row, "is_required", bool),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source_packet_fact(value: SourcePacketFact) -> dict[str, object]:
    return _encoded(
        (
            "source_packet_version_id",
            "fact_id",
            "usage_role",
            "display_order",
            "is_required",
            "created_at",
        ),
        domain_mappers.map_evidence_source_packet_fact_to_row(value),
    )


def _decode_evidence_source_packet_product(
    row: Mapping[str, object],
) -> SourcePacketProduct:
    columns = (
        "source_packet_version_id",
        "product_id",
        "offer_id",
        "product_role",
        "display_order",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_packet_product_from_row(
            source_packet_version_id=SourcePacketVersionId(
                _exact(row, "source_packet_version_id", UUID)
            ),
            product_id=CanonicalProductId(_exact(row, "product_id", UUID)),
            offer_id=(
                None
                if row["offer_id"] is None
                else OfferId(_exact(row, "offer_id", UUID))
            ),
            product_role=SourcePacketProductProductRole(
                _exact(row, "product_role", str)
            ),
            display_order=_exact(row, "display_order", int),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source_packet_product(
    value: SourcePacketProduct,
) -> dict[str, object]:
    return _encoded(
        (
            "source_packet_version_id",
            "product_id",
            "offer_id",
            "product_role",
            "display_order",
            "created_at",
        ),
        domain_mappers.map_evidence_source_packet_product_to_row(value),
    )


def _decode_evidence_source_packet_version(
    row: Mapping[str, object],
) -> SourcePacketVersionState:
    columns = (
        "id",
        "display_id",
        "source_packet_id",
        "version_no",
        "artifact_id",
        "content_sha256",
        "schema_version",
        "status",
        "built_by_job_id",
        "reviewed_by_principal_id",
        "reviewed_at",
        "review_note",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_packet_version_from_row(
            id=SourcePacketVersionId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            source_packet_id=SourcePacketId(_exact(row, "source_packet_id", UUID)),
            version_no=_exact(row, "version_no", int),
            artifact_id=ObjectArtifactId(_exact(row, "artifact_id", UUID)),
            content_sha256=Sha256Digest(_exact(row, "content_sha256", str)),
            schema_version=_exact(row, "schema_version", int),
            status=SourcePacketVersionStatus(_exact(row, "status", str)),
            built_by_job_id=(
                None
                if row["built_by_job_id"] is None
                else JobId(_exact(row, "built_by_job_id", UUID))
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
            review_note=(
                None if row["review_note"] is None else _exact(row, "review_note", str)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source_packet_version(
    value: SourcePacketVersionState,
) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "source_packet_id",
            "version_no",
            "artifact_id",
            "content_sha256",
            "schema_version",
            "status",
            "built_by_job_id",
            "reviewed_by_principal_id",
            "reviewed_at",
            "review_note",
            "created_at",
        ),
        domain_mappers.map_evidence_source_packet_version_to_row(value),
    )


def _decode_evidence_source_snapshot(row: Mapping[str, object]) -> SourceSnapshot:
    columns = (
        "id",
        "display_id",
        "source_id",
        "artifact_id",
        "external_reference",
        "acquired_at",
        "effective_at",
        "expires_at",
        "content_sha256",
        "parser_version",
        "validation_status",
        "validation_message",
        "created_at",
    )
    _shape(row, columns)
    try:
        return domain_mappers.map_evidence_source_snapshot_from_row(
            id=SourceSnapshotId(_exact(row, "id", UUID)),
            display_id=_exact(row, "display_id", str),
            source_id=SourceId(_exact(row, "source_id", UUID)),
            artifact_id=ObjectArtifactId(_exact(row, "artifact_id", UUID)),
            external_reference=(
                None
                if row["external_reference"] is None
                else _exact(row, "external_reference", str)
            ),
            acquired_at=AwareUtcDateTime(_exact(row, "acquired_at", datetime)),
            effective_at=(
                None
                if row["effective_at"] is None
                else AwareUtcDateTime(_exact(row, "effective_at", datetime))
            ),
            expires_at=(
                None
                if row["expires_at"] is None
                else AwareUtcDateTime(_exact(row, "expires_at", datetime))
            ),
            content_sha256=Sha256Digest(_exact(row, "content_sha256", str)),
            parser_version=_exact(row, "parser_version", str),
            validation_status=SourceSnapshotValidationStatus(
                _exact(row, "validation_status", str)
            ),
            validation_message=(
                None
                if row["validation_message"] is None
                else _exact(row, "validation_message", str)
            ),
            created_at=AwareUtcDateTime(_exact(row, "created_at", datetime)),
        )
    except KeyError, TypeError, ValueError:
        _fail(PersistenceErrorCode.STORAGE_CORRUPTION)


def _encode_evidence_source_snapshot(value: SourceSnapshot) -> dict[str, object]:
    return _encoded(
        (
            "id",
            "display_id",
            "source_id",
            "artifact_id",
            "external_reference",
            "acquired_at",
            "effective_at",
            "expires_at",
            "content_sha256",
            "parser_version",
            "validation_status",
            "validation_message",
            "created_at",
        ),
        domain_mappers.map_evidence_source_snapshot_to_row(value),
    )


# Aggregate-specific Session/Table-bound classes are the only DML surface.


def _require_session(session: Session) -> None:
    if not isinstance(session, Session):
        raise ValueError("INVALID_EVIDENCE_REPOSITORY") from None


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


def _cas_bump(
    session: Session,
    table: Table,
    aggregate_id: UUID,
    expected_version: AggregateVersion,
) -> AggregateVersion:
    persisted = _scalar_one(
        session,
        update(table)
        .where(
            table.c.id == aggregate_id,
            table.c.lock_version == expected_version.value,
        )
        .values(lock_version=expected_version.value + 1)
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
        raise ValueError("INVALID_EVIDENCE_LATEST_VERSION") from None


@guard_repository_class
class SqlAlchemySourceRepository:
    __slots__ = ("_session", "_source")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._source = _table("evidence.source")

    def get(self, source_id: SourceId) -> Source | None:
        if type(source_id) is not SourceId:
            raise ValueError("INVALID_SOURCE_ID") from None
        row = _execute_one(
            self._session,
            select(self._source).where(self._source.c.id == source_id.value),
        )
        if row is None:
            return None
        source = Source(_decode_evidence_source(row))
        register_pending_events(
            self._session,
            aggregate_type="evidence.source",
            aggregate_id=source.state.id.value,
            buffer=source._events,
        )
        return source

    def add(self, source: Source) -> PersistedVersion:
        if type(source) is not Source or source.state.lock_version.value != 0:
            raise ValueError("INVALID_SOURCE") from None
        register_pending_events(
            self._session,
            aggregate_type="evidence.source",
            aggregate_id=source.state.id.value,
            buffer=source._events,
        )
        _execute(
            self._session,
            insert(self._source).values(**_encode_evidence_source(source.state)),
        )
        return AggregateVersion(0)

    def save(
        self,
        source: Source,
        expected_version: AggregateVersion,
    ) -> PersistedVersion:
        if (
            type(source) is not Source
            or type(expected_version) is not AggregateVersion
            or source.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_SOURCE") from None
        register_pending_events(
            self._session,
            aggregate_type="evidence.source",
            aggregate_id=source.state.id.value,
            buffer=source._events,
        )
        return _cas_update(
            self._session,
            self._source,
            source.state.id.value,
            expected_version,
            _encode_evidence_source(source.state),
        )


@guard_repository_class
class SqlAlchemySourceSnapshotRepository:
    __slots__ = ("_session", "_snapshot", "_source")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._source = _table("evidence.source")
        self._snapshot = _table("evidence.source_snapshot")

    def get(self, snapshot_id: SourceSnapshotId) -> SourceSnapshot | None:
        if type(snapshot_id) is not SourceSnapshotId:
            raise ValueError("INVALID_SOURCE_SNAPSHOT_ID") from None
        row = _execute_one(
            self._session,
            select(self._snapshot).where(self._snapshot.c.id == snapshot_id.value),
        )
        return None if row is None else _decode_evidence_source_snapshot(row)

    def append(
        self,
        source_id: SourceId,
        snapshot: SourceSnapshot,
        expected_source_version: AggregateVersion,
    ) -> PersistedVersion:
        if (
            type(source_id) is not SourceId
            or type(snapshot) is not SourceSnapshot
            or type(expected_source_version) is not AggregateVersion
            or snapshot.source_id != source_id
        ):
            raise ValueError("INVALID_SOURCE_SNAPSHOT_APPEND") from None
        persisted = _cas_bump(
            self._session,
            self._source,
            source_id.value,
            expected_source_version,
        )
        _execute(
            self._session,
            insert(self._snapshot).values(**_encode_evidence_source_snapshot(snapshot)),
        )
        stage_registered_events(
            self._session,
            aggregate_type="evidence.source",
            aggregate_id=source_id.value,
            owning_method="SourceSnapshotRepository.append",
            persisted_version=persisted,
            expected_event_type="jp.raos.evidence.source_snapshot_captured.v1",
        )
        return persisted


@guard_repository_class
class SqlAlchemyFactRepository:
    __slots__ = ("_derivation", "_fact", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._fact = _table("evidence.fact")
        self._derivation = _table("evidence.fact_derivation")

    def get(self, fact_id: FactId) -> Fact | None:
        if type(fact_id) is not FactId:
            raise ValueError("INVALID_FACT_ID") from None
        row = _execute_one(
            self._session,
            select(self._fact).where(self._fact.c.id == fact_id.value),
        )
        if row is None:
            return None
        children = tuple(
            _decode_evidence_fact_derivation(item)
            for item in _execute_many(
                self._session,
                select(self._derivation)
                .where(self._derivation.c.derived_fact_id == fact_id.value)
                .order_by(
                    self._derivation.c.derived_fact_id,
                    self._derivation.c.input_fact_id,
                    self._derivation.c.derivation_role,
                ),
            )
        )
        return Fact(
            state=_decode_evidence_fact(row),
            fact_derivation_rows=children,
        )

    def append(
        self,
        fact: Fact,
        derivations: tuple[FactDerivation, ...],
    ) -> None:
        if (
            type(fact) is not Fact
            or type(derivations) is not tuple
            or any(type(item) is not FactDerivation for item in derivations)
            or fact.fact_derivation_rows != derivations
            or any(item.derived_fact_id != fact.state.id for item in derivations)
        ):
            raise ValueError("INVALID_FACT_APPEND") from None
        _execute(
            self._session,
            insert(self._fact).values(**_encode_evidence_fact(fact.state)),
        )
        for derivation in derivations:
            _execute(
                self._session,
                insert(self._derivation).values(
                    **_encode_evidence_fact_derivation(derivation)
                ),
            )


@guard_repository_class
class SqlAlchemyClaimRepository:
    __slots__ = ("_claim", "_link", "_session")

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._claim = _table("evidence.claim")
        self._link = _table("evidence.claim_evidence_link")

    def get(self, claim_id: ClaimId) -> Claim | None:
        if type(claim_id) is not ClaimId:
            raise ValueError("INVALID_CLAIM_ID") from None
        row = _execute_one(
            self._session,
            select(self._claim).where(self._claim.c.id == claim_id.value),
        )
        if row is None:
            return None
        links = tuple(
            _decode_evidence_claim_evidence_link(item)
            for item in _execute_many(
                self._session,
                select(self._link)
                .where(self._link.c.claim_id == claim_id.value)
                .order_by(
                    self._link.c.claim_id,
                    self._link.c.fact_id,
                    self._link.c.support_type,
                ),
            )
        )
        return Claim(
            state=_decode_evidence_claim(row),
            claim_evidence_link_rows=links,
        )

    def append(
        self,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
    ) -> None:
        if (
            type(claim) is not Claim
            or type(links) is not tuple
            or any(type(item) is not ClaimEvidenceLink for item in links)
            or claim.claim_evidence_link_rows != links
            or any(item.claim_id != claim.state.id for item in links)
        ):
            raise ValueError("INVALID_CLAIM_APPEND") from None
        _execute(
            self._session,
            insert(self._claim).values(**_encode_evidence_claim(claim.state)),
        )
        for link in links:
            _execute(
                self._session,
                insert(self._link).values(**_encode_evidence_claim_evidence_link(link)),
            )


@guard_repository_class
class SqlAlchemySourcePacketRepository:
    __slots__ = ("_fact", "_packet", "_product", "_session", "_version")

    _VERSION_EDGES = frozenset(
        {
            ("BUILDING", "READY"),
            ("BUILDING", "INVALID"),
            ("READY", "IN_REVIEW"),
            ("READY", "INVALID"),
            ("IN_REVIEW", "APPROVED"),
            ("IN_REVIEW", "REJECTED"),
            ("IN_REVIEW", "INVALID"),
            ("APPROVED", "SUPERSEDED"),
            ("APPROVED", "INVALID"),
            ("REJECTED", "INVALID"),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._packet = _table("evidence.source_packet")
        self._version = _table("evidence.source_packet_version")
        self._fact = _table("evidence.source_packet_fact")
        self._product = _table("evidence.source_packet_product")

    def _version_children(
        self,
        version_ids: tuple[UUID, ...],
    ) -> tuple[tuple[SourcePacketFact, ...], tuple[SourcePacketProduct, ...]]:
        if not version_ids:
            return (), ()
        facts = tuple(
            _decode_evidence_source_packet_fact(item)
            for item in _execute_many(
                self._session,
                select(self._fact)
                .where(self._fact.c.source_packet_version_id.in_(version_ids))
                .order_by(
                    self._fact.c.source_packet_version_id,
                    self._fact.c.fact_id,
                ),
            )
        )
        products = tuple(
            _decode_evidence_source_packet_product(item)
            for item in _execute_many(
                self._session,
                select(self._product)
                .where(self._product.c.source_packet_version_id.in_(version_ids))
                .order_by(
                    self._product.c.source_packet_version_id,
                    self._product.c.product_id,
                    self._product.c.product_role,
                ),
            )
        )
        return facts, products

    def get(self, packet_id: SourcePacketId) -> SourcePacket | None:
        if type(packet_id) is not SourcePacketId:
            raise ValueError("INVALID_SOURCE_PACKET_ID") from None
        row = _execute_one(
            self._session,
            select(self._packet).where(self._packet.c.id == packet_id.value),
        )
        if row is None:
            return None
        versions = tuple(
            _decode_evidence_source_packet_version(item)
            for item in _execute_many(
                self._session,
                select(self._version)
                .where(self._version.c.source_packet_id == packet_id.value)
                .order_by(self._version.c.id),
            )
        )
        version_ids = tuple(item.id.value for item in versions)
        facts, products = self._version_children(version_ids)
        packet = SourcePacket(
            state=_decode_evidence_source_packet(row),
            source_packet_version_rows=versions,
            source_packet_fact_rows=facts,
            source_packet_product_rows=products,
        )
        try:
            self._validate_packet(packet)
        except ValueError:
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        return packet

    @staticmethod
    def _validate_packet(packet: SourcePacket) -> None:
        if type(packet) is not SourcePacket:
            raise ValueError("INVALID_SOURCE_PACKET") from None
        ordered_version_ids = tuple(
            item.id for item in packet.source_packet_version_rows
        )
        version_ids = frozenset(ordered_version_ids)
        version_numbers = tuple(
            item.version_no for item in packet.source_packet_version_rows
        )
        if (
            len(version_ids) != len(ordered_version_ids)
            or len(frozenset(version_numbers)) != len(version_numbers)
            or packet.state.current_version_no
            != (0 if not version_numbers else max(version_numbers))
            or any(
                item.source_packet_id != packet.state.id
                for item in packet.source_packet_version_rows
            )
            or any(
                item.source_packet_version_id not in version_ids
                for item in packet.source_packet_fact_rows
            )
            or any(
                item.source_packet_version_id not in version_ids
                for item in packet.source_packet_product_rows
            )
        ):
            raise ValueError("INVALID_SOURCE_PACKET") from None

    def add(self, packet: SourcePacket) -> PersistedVersion:
        self._validate_packet(packet)
        if packet.state.lock_version.value != 0:
            raise ValueError("INVALID_SOURCE_PACKET") from None
        _execute(
            self._session,
            insert(self._packet).values(**_encode_evidence_source_packet(packet.state)),
        )
        for version in packet.source_packet_version_rows:
            _execute(
                self._session,
                insert(self._version).values(
                    **_encode_evidence_source_packet_version(version)
                ),
            )
        for fact in packet.source_packet_fact_rows:
            _execute(
                self._session,
                insert(self._fact).values(**_encode_evidence_source_packet_fact(fact)),
            )
        for product in packet.source_packet_product_rows:
            _execute(
                self._session,
                insert(self._product).values(
                    **_encode_evidence_source_packet_product(product)
                ),
            )
        return AggregateVersion(0)

    def save(
        self,
        packet: SourcePacket,
        expected_version: AggregateVersion,
    ) -> PersistedVersion:
        self._validate_packet(packet)
        if (
            type(expected_version) is not AggregateVersion
            or packet.state.lock_version != expected_version
        ):
            raise ValueError("INVALID_SOURCE_PACKET") from None
        current = self.get(packet.state.id)
        if current is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if (
            current.source_packet_version_rows != packet.source_packet_version_rows
            or current.source_packet_fact_rows != packet.source_packet_fact_rows
            or current.source_packet_product_rows != packet.source_packet_product_rows
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        return _cas_update(
            self._session,
            self._packet,
            packet.state.id.value,
            expected_version,
            _encode_evidence_source_packet(packet.state),
        )

    def append_version(
        self,
        packet_id: SourcePacketId,
        version: SourcePacketVersion,
        expected_version: AggregateVersion,
        expected_latest_version: int | None,
    ) -> PersistedVersion:
        _validate_latest(expected_latest_version)
        if (
            type(packet_id) is not SourcePacketId
            or type(version) is not SourcePacketVersion
            or type(expected_version) is not AggregateVersion
            or version.state.source_packet_id != packet_id
            or any(
                item.source_packet_version_id != version.state.id
                for item in version.source_packet_fact_rows
            )
            or any(
                item.source_packet_version_id != version.state.id
                for item in version.source_packet_product_rows
            )
        ):
            raise ValueError("INVALID_SOURCE_PACKET_VERSION_APPEND") from None
        latest_row = _execute_one(
            self._session,
            select(self._version.c.version_no)
            .where(self._version.c.source_packet_id == packet_id.value)
            .order_by(self._version.c.version_no.desc(), self._version.c.id.desc())
            .limit(1),
        )
        observed = None if latest_row is None else _exact(latest_row, "version_no", int)
        if observed != expected_latest_version:
            _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
        required_version = 1 if observed is None else observed + 1
        if version.state.version_no != required_version:
            raise ValueError("INVALID_SOURCE_PACKET_VERSION_APPEND") from None
        persisted = _scalar_one(
            self._session,
            update(self._packet)
            .where(
                self._packet.c.id == packet_id.value,
                self._packet.c.lock_version == expected_version.value,
            )
            .values(
                current_version_no=required_version,
                lock_version=expected_version.value + 1,
            )
            .returning(self._packet.c.lock_version),
        )
        if type(persisted) is not int:
            observed_packet = _execute_one(
                self._session,
                select(self._packet.c.id, self._packet.c.lock_version).where(
                    self._packet.c.id == packet_id.value
                ),
            )
            if observed_packet is None:
                _fail(PersistenceErrorCode.NOT_FOUND)
            if _exact(observed_packet, "lock_version", int) != expected_version.value:
                _fail(PersistenceErrorCode.CONCURRENCY_CONFLICT)
            _fail(PersistenceErrorCode.STORAGE_CORRUPTION)
        _execute(
            self._session,
            insert(self._version).values(
                **_encode_evidence_source_packet_version(version.state)
            ),
        )
        for fact in version.source_packet_fact_rows:
            _execute(
                self._session,
                insert(self._fact).values(**_encode_evidence_source_packet_fact(fact)),
            )
        for product in version.source_packet_product_rows:
            _execute(
                self._session,
                insert(self._product).values(
                    **_encode_evidence_source_packet_product(product)
                ),
            )
        return AggregateVersion(persisted)

    def transition_version(
        self,
        version_id: SourcePacketVersionId,
        transition: SourcePacketVersion,
        expected_status: SourcePacketVersionStatus,
    ) -> SourcePacketVersion:
        if (
            type(version_id) is not SourcePacketVersionId
            or type(transition) is not SourcePacketVersion
            or type(expected_status) is not SourcePacketVersionStatus
            or transition.state.id != version_id
        ):
            raise ValueError("INVALID_SOURCE_PACKET_VERSION_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._version).where(self._version.c.id == version_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_evidence_source_packet_version(current_row)
        current_facts, current_products = self._version_children((version_id.value,))
        if (
            transition.source_packet_fact_rows != current_facts
            or transition.source_packet_product_rows != current_products
        ):
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        target = transition.state.status.value
        edge = (expected_status.value, target)
        mutable = ("status", "reviewed_by_principal_id", "reviewed_at")
        if (
            current.status is not expected_status
            or edge not in self._VERSION_EDGES
            or not _same_except(
                _encode_evidence_source_packet_version(current),
                _encode_evidence_source_packet_version(transition.state),
                mutable,
            )
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        reviewed_edge = edge in {
            ("IN_REVIEW", "APPROVED"),
            ("IN_REVIEW", "REJECTED"),
        }
        reviewed_by = transition.state.reviewed_by_principal_id
        reviewed_at = transition.state.reviewed_at
        if reviewed_edge:
            context_principal = _context_principal_id(self._session)
            at = transaction_timestamp(self._session)
            if (
                current.reviewed_by_principal_id is not None
                or current.reviewed_at is not None
                or reviewed_by != context_principal
                or reviewed_at != at
            ):
                _fail(PersistenceErrorCode.STATE_CONFLICT)
        elif (
            transition.state.reviewed_by_principal_id
            != current.reviewed_by_principal_id
            or transition.state.reviewed_at != current.reviewed_at
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        values: dict[str, object] = {"status": target}
        predicates = [
            self._version.c.id == version_id.value,
            self._version.c.status == expected_status.value,
        ]
        if reviewed_edge:
            predicates.extend(
                [
                    self._version.c.reviewed_by_principal_id.is_(None),
                    self._version.c.reviewed_at.is_(None),
                ]
            )
            values.update(
                reviewed_by_principal_id=context_principal.value,
                reviewed_at=at.value,
            )
        row = _execute_one(
            self._session,
            update(self._version)
            .where(*predicates)
            .values(**values)
            .returning(self._version),
        )
        if row is None:
            _state_zero(
                self._session,
                self._version,
                "id",
                version_id.value,
                "status",
                expected_status.value,
            )
        return SourcePacketVersion(
            state=_decode_evidence_source_packet_version(row),
            source_packet_fact_rows=current_facts,
            source_packet_product_rows=current_products,
        )


@guard_repository_class
class SqlAlchemyFirstHandExperienceRepository:
    __slots__ = ("_asset", "_record", "_session")

    _EDGES = frozenset(
        {
            ("DRAFT", "REVIEWED"),
            ("DRAFT", "REJECTED"),
            ("REVIEWED", "APPROVED"),
            ("REVIEWED", "REJECTED"),
        }
    )

    def __init__(self, session: Session) -> None:
        _require_session(session)
        self._session = session
        self._record = _table("evidence.first_hand_experience_record")
        self._asset = _table("evidence.first_hand_experience_asset")

    def _load_assets(
        self,
        record_id: FirstHandExperienceRecordId,
    ) -> tuple[FirstHandExperienceAsset, ...]:
        return tuple(
            _decode_evidence_first_hand_experience_asset(item)
            for item in _execute_many(
                self._session,
                select(self._asset)
                .where(self._asset.c.experience_record_id == record_id.value)
                .order_by(
                    self._asset.c.experience_record_id,
                    self._asset.c.artifact_id,
                    self._asset.c.role,
                ),
            )
        )

    def get(
        self,
        record_id: FirstHandExperienceRecordId,
    ) -> FirstHandExperienceRecord | None:
        if type(record_id) is not FirstHandExperienceRecordId:
            raise ValueError("INVALID_FIRST_HAND_EXPERIENCE_ID") from None
        row = _execute_one(
            self._session,
            select(self._record).where(self._record.c.id == record_id.value),
        )
        if row is None:
            return None
        assets = self._load_assets(record_id)
        return FirstHandExperienceRecord(
            state=_decode_evidence_first_hand_experience_record(row),
            first_hand_experience_asset_rows=assets,
        )

    def add(self, record: FirstHandExperienceRecord) -> None:
        if type(record) is not FirstHandExperienceRecord or any(
            item.experience_record_id != record.state.id
            for item in record.first_hand_experience_asset_rows
        ):
            raise ValueError("INVALID_FIRST_HAND_EXPERIENCE") from None
        _execute(
            self._session,
            insert(self._record).values(
                **_encode_evidence_first_hand_experience_record(record.state)
            ),
        )
        for asset in record.first_hand_experience_asset_rows:
            _execute(
                self._session,
                insert(self._asset).values(
                    **_encode_evidence_first_hand_experience_asset(asset)
                ),
            )

    def transition(
        self,
        record_id: FirstHandExperienceRecordId,
        transition: FirstHandExperienceRecord,
        expected_status: FirstHandExperienceStatus,
    ) -> FirstHandExperienceRecord:
        if (
            type(record_id) is not FirstHandExperienceRecordId
            or type(transition) is not FirstHandExperienceRecord
            or type(expected_status) is not FirstHandExperienceStatus
            or transition.state.id != record_id
        ):
            raise ValueError("INVALID_FIRST_HAND_EXPERIENCE_TRANSITION") from None
        current_row = _execute_one(
            self._session,
            select(self._record).where(self._record.c.id == record_id.value),
        )
        if current_row is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        current = _decode_evidence_first_hand_experience_record(current_row)
        assets = self._load_assets(record_id)
        if transition.first_hand_experience_asset_rows != assets:
            _fail(PersistenceErrorCode.APPEND_ONLY_RELATION)
        edge = (expected_status.value, transition.state.review_status.value)
        mutable = ("review_status", "reviewed_by_principal_id", "reviewed_at")
        context_principal = _context_principal_id(self._session, human=True)
        at = transaction_timestamp(self._session)
        if (
            current.review_status is not expected_status
            or edge not in self._EDGES
            or not _same_except(
                _encode_evidence_first_hand_experience_record(current),
                _encode_evidence_first_hand_experience_record(transition.state),
                mutable,
            )
            or transition.state.reviewed_by_principal_id != context_principal
            or transition.state.reviewed_at != at
            or context_principal == current.tester_principal_id
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if expected_status.value == "DRAFT" and (
            current.reviewed_by_principal_id is not None
            or current.reviewed_at is not None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        if expected_status.value == "REVIEWED" and (
            current.reviewed_by_principal_id is None or current.reviewed_at is None
        ):
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        predicates = [
            self._record.c.id == record_id.value,
            self._record.c.review_status == expected_status.value,
        ]
        if expected_status.value == "DRAFT":
            predicates.extend(
                [
                    self._record.c.reviewed_by_principal_id.is_(None),
                    self._record.c.reviewed_at.is_(None),
                ]
            )
        else:
            predicates.extend(
                [
                    self._record.c.reviewed_by_principal_id.is_not(None),
                    self._record.c.reviewed_at.is_not(None),
                ]
            )
        row = _execute_one(
            self._session,
            update(self._record)
            .where(*predicates)
            .values(
                review_status=transition.state.review_status.value,
                reviewed_by_principal_id=context_principal.value,
                reviewed_at=at.value,
            )
            .returning(self._record),
        )
        if row is None:
            _state_zero(
                self._session,
                self._record,
                "id",
                record_id.value,
                "review_status",
                expected_status.value,
            )
        return FirstHandExperienceRecord(
            state=_decode_evidence_first_hand_experience_record(row),
            first_hand_experience_asset_rows=assets,
        )

    def append_assets(
        self,
        record_id: FirstHandExperienceRecordId,
        assets: tuple[FirstHandExperienceAsset, ...],
        expected_status: FirstHandExperienceStatus,
    ) -> None:
        if (
            type(record_id) is not FirstHandExperienceRecordId
            or type(assets) is not tuple
            or any(type(item) is not FirstHandExperienceAsset for item in assets)
            or any(item.experience_record_id != record_id for item in assets)
            or type(expected_status) is not FirstHandExperienceStatus
            or expected_status.value not in {"DRAFT", "REVIEWED"}
        ):
            raise ValueError("INVALID_FIRST_HAND_EXPERIENCE_ASSETS") from None
        state = _execute_one(
            self._session,
            select(self._record.c.id, self._record.c.review_status)
            .where(self._record.c.id == record_id.value)
            .with_for_update(),
        )
        if state is None:
            _fail(PersistenceErrorCode.NOT_FOUND)
        if _exact(state, "review_status", str) != expected_status.value:
            _fail(PersistenceErrorCode.STATE_CONFLICT)
        for asset in assets:
            _execute(
                self._session,
                insert(self._asset).values(
                    **_encode_evidence_first_hand_experience_asset(asset)
                ),
            )


__all__ = [
    "SqlAlchemyClaimRepository",
    "SqlAlchemyFactRepository",
    "SqlAlchemyFirstHandExperienceRepository",
    "SqlAlchemySourcePacketRepository",
    "SqlAlchemySourceRepository",
    "SqlAlchemySourceSnapshotRepository",
]
