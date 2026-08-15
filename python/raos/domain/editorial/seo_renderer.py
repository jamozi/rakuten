"""Pure, local-only SEO rendering boundary for ST-0807.

This module consumes only explicit, pre-resolved values.  It does not select a
site origin, inspect a publication snapshot, perform I/O, or authorize any
publication, release, or production action.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import re
from typing import NoReturn, TypeAlias, cast


LOCAL_RENDER_PROFILE = "ST0807_LOCAL_RENDER_V1"
SEO_POLICY_ID = "RAOS-CONTENT-SEO-001"
SEO_POLICY_VERSION = "1.0.0"
SEO_POLICY_SHA256 = "2fa67e012c67f8a6a90b39cfd64f27da9fb76534e57ebbff60ccd78ba51bb98a"
SEO_METADATA_SCHEMA_ID = (
    "https://schemas.raos.local/content/v1/seo-metadata.schema.json"
)
SEO_METADATA_SCHEMA_SHA256 = (
    "347820081caec76faea9d44d379b86bfacb539c69e048a55c658f3a78b2263ad"
)
STRUCTURED_DATA_MANIFEST_SCHEMA_ID = (
    "https://schemas.raos.local/content/v1/structured-data-manifest.schema.json"
)
STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256 = (
    "6a564e994b9ccfbefca62e3ef2245a56b96514ba35608ae3a1919bf27c7d312e"
)
CONTENT_TEST_MATRIX_SHA256 = (
    "9be140d6f7015bf8c464993a34d127b2e8c118fd0ed49d20d113fb399ed8a564"
)

_REFERENCE = re.compile(r"[A-Z0-9][A-Z0-9_.:-]{2,126}\Z", re.ASCII)
_ROUTE = re.compile(r"/(?:[a-z0-9](?:[a-z0-9/_-]*[a-z0-9])?)?\Z", re.ASCII)
_SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,158}[a-z0-9])?\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_HOST = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z",
    re.ASCII,
)

JsonScalar: TypeAlias = str | int | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class RenderMode(str, Enum):
    PUBLIC_CANDIDATE = "PUBLIC_CANDIDATE"
    PREVIEW = "PREVIEW"


class OriginMode(str, Enum):
    ROUTE_ONLY = "ROUTE_ONLY"
    CALLER_SUPPLIED_ORIGIN = "CALLER_SUPPLIED_ORIGIN"


class OriginSource(str, Enum):
    NONE = "NONE"
    CALLER_SUPPLIED_UNAPPROVED = "CALLER_SUPPLIED_UNAPPROVED"


class ExternalAssessmentState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class ExternalCheck(str, Enum):
    TITLE_UNIQUENESS = "TITLE_UNIQUENESS"
    CANONICAL_GRAPH = "CANONICAL_GRAPH"
    ST_0805_POLICY_ELIGIBILITY = "ST_0805_POLICY_ELIGIBILITY"
    BROWSER_VISIBLE_EQUALITY = "BROWSER_VISIBLE_EQUALITY"
    SUBSTANTIVE_CHANGE_CLASSIFICATION = "SUBSTANTIVE_CHANGE_CLASSIFICATION"
    ROUTE_EXISTENCE = "ROUTE_EXISTENCE"
    HTTP_200 = "HTTP_200"
    RUNTIME_INDEXABILITY = "RUNTIME_INDEXABILITY"
    PAUSE_OR_REDIRECT_SOURCE_STATE = "PAUSE_OR_REDIRECT_SOURCE_STATE"
    PUBLICATION_SNAPSHOT_CURRENCY = "PUBLICATION_SNAPSHOT_CURRENCY"
    IMAGE_PUBLICABILITY = "IMAGE_PUBLICABILITY"
    AUTH_CACHE_CTA_BEHAVIOR = "AUTH_CACHE_CTA_BEHAVIOR"
    AFFILIATE_REL = "AFFILIATE_REL"
    AFFILIATE_REDIRECT_BEHAVIOR = "AFFILIATE_REDIRECT_BEHAVIOR"


class RenderStatus(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    RENDERED_LOCAL = "RENDERED_LOCAL"


class IndexState(str, Enum):
    INDEX = "index"
    NOINDEX = "noindex"


class RobotsDirective(str, Enum):
    INDEX = "index"
    NOINDEX = "noindex"
    FOLLOW = "follow"
    NOFOLLOW = "nofollow"
    MAX_IMAGE_PREVIEW_LARGE = "max-image-preview:large"


class ArticleSchemaType(str, Enum):
    ARTICLE = "Article"
    BLOG_POSTING = "BlogPosting"


class AuthorKind(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"


class DisabledSchemaType(str, Enum):
    PRODUCT = "Product"
    OFFER = "Offer"
    REVIEW = "Review"
    AGGREGATE_RATING = "AggregateRating"
    FAQ_PAGE = "FAQPage"


class ChangeClassification(str, Enum):
    INITIAL_PUBLICATION = "INITIAL_PUBLICATION"
    SUBSTANTIVE = "SUBSTANTIVE"
    PRICE_ONLY = "PRICE_ONLY"
    NONE = "NONE"


class BindingField(str, Enum):
    METADATA_TITLE = "METADATA_TITLE"
    VISIBLE_H1 = "VISIBLE_H1"
    JSONLD_HEADLINE = "JSONLD_HEADLINE"
    JSONLD_AUTHOR = "JSONLD_AUTHOR"
    JSONLD_DATE_PUBLISHED = "JSONLD_DATE_PUBLISHED"
    JSONLD_DATE_MODIFIED = "JSONLD_DATE_MODIFIED"
    JSONLD_SCHEMA_TYPE = "JSONLD_SCHEMA_TYPE"
    JSONLD_CANONICAL_URL = "JSONLD_CANONICAL_URL"
    JSONLD_PROFILE_SHAPE = "JSONLD_PROFILE_SHAPE"
    CANONICAL_ROUTE = "CANONICAL_ROUTE"
    BREADCRUMB_NAME = "BREADCRUMB_NAME"
    BREADCRUMB_ROUTE = "BREADCRUMB_ROUTE"
    BREADCRUMB_POSITION = "BREADCRUMB_POSITION"


class VisibleSourcePointer(str, Enum):
    VISIBLE_TITLE = "VISIBLE_TITLE"
    VISIBLE_H1 = "VISIBLE_H1"
    VISIBLE_AUTHOR = "VISIBLE_AUTHOR"
    VISIBLE_DATE_PUBLISHED = "VISIBLE_DATE_PUBLISHED"
    VISIBLE_DATE_MODIFIED = "VISIBLE_DATE_MODIFIED"
    CURRENT_ROUTE = "CURRENT_ROUTE"
    CALLER_ARTICLE_SCHEMA_TYPE = "CALLER_ARTICLE_SCHEMA_TYPE"
    CANONICAL_ROUTE = "CANONICAL_ROUTE"
    LOCAL_RENDER_PROFILE = "LOCAL_RENDER_PROFILE"
    VISIBLE_BREADCRUMB_NAME = "VISIBLE_BREADCRUMB_NAME"
    VISIBLE_BREADCRUMB_ROUTE = "VISIBLE_BREADCRUMB_ROUTE"
    VISIBLE_BREADCRUMB_POSITION = "VISIBLE_BREADCRUMB_POSITION"


class ComparisonKind(str, Enum):
    EXACT_TEXT = "EXACT_TEXT"
    EXACT_TIMESTAMP = "EXACT_TIMESTAMP"
    EXACT_ROUTE = "EXACT_ROUTE"
    EXACT_TYPE = "EXACT_TYPE"
    EXACT_URL = "EXACT_URL"
    EXACT_STRUCTURE = "EXACT_STRUCTURE"
    ORDERED_POSITION = "ORDERED_POSITION"


class ComparisonResult(str, Enum):
    MATCH = "MATCH"
    MISMATCH = "MISMATCH"


class LocalValidationResult(str, Enum):
    PASS = "pass"
    FAIL = "fail"


class InputFindingCode(str, Enum):
    INPUT_TYPE_INVALID = "INPUT_TYPE_INVALID"
    ROUTE_INVALID = "ROUTE_INVALID"
    ROUTE_MISMATCH = "ROUTE_MISMATCH"
    MODE_INVALID = "MODE_INVALID"
    CONTRACT_BINDING_INVALID = "CONTRACT_BINDING_INVALID"
    METADATA_INVALID = "METADATA_INVALID"
    ARTICLE_BINDING_MISMATCH = "ARTICLE_BINDING_MISMATCH"
    ORIGIN_INVALID = "ORIGIN_INVALID"
    ORIGIN_MODE_INVALID = "ORIGIN_MODE_INVALID"
    ORIGIN_MODE_MISMATCH = "ORIGIN_MODE_MISMATCH"
    ARTICLE_SCHEMA_TYPE_INVALID = "ARTICLE_SCHEMA_TYPE_INVALID"
    VISIBLE_PROJECTION_INVALID = "VISIBLE_PROJECTION_INVALID"
    AUTHOR_INVALID = "AUTHOR_INVALID"
    ROBOTS_INVALID = "ROBOTS_INVALID"
    BREADCRUMB_COLLECTION_INVALID = "BREADCRUMB_COLLECTION_INVALID"
    BREADCRUMB_RECORD_INVALID = "BREADCRUMB_RECORD_INVALID"
    BREADCRUMB_DUPLICATE = "BREADCRUMB_DUPLICATE"
    BREADCRUMB_SET_MISMATCH = "BREADCRUMB_SET_MISMATCH"
    BREADCRUMB_POSITION_INVALID = "BREADCRUMB_POSITION_INVALID"
    SITE_PROJECTION_INVALID = "SITE_PROJECTION_INVALID"
    CHANGE_ASSESSMENT_INVALID = "CHANGE_ASSESSMENT_INVALID"
    LASTMOD_INVALID = "LASTMOD_INVALID"
    ASSESSMENT_COLLECTION_INVALID = "ASSESSMENT_COLLECTION_INVALID"
    ASSESSMENT_RECORD_INVALID = "ASSESSMENT_RECORD_INVALID"
    ASSESSMENT_DUPLICATE = "ASSESSMENT_DUPLICATE"
    ASSESSMENT_SET_MISMATCH = "ASSESSMENT_SET_MISMATCH"
    ASSESSMENT_PROOF_INVALID = "ASSESSMENT_PROOF_INVALID"
    VALIDATED_AT_INVALID = "VALIDATED_AT_INVALID"
    PROHIBITED_INPUT = "PROHIBITED_INPUT"


class EligibilityReason(str, Enum):
    ROUTE_ONLY_ORIGIN_UNAVAILABLE = "ROUTE_ONLY_ORIGIN_UNAVAILABLE"
    ROUTE_MISMATCH = "ROUTE_MISMATCH"
    PREVIEW_NOINDEX = "PREVIEW_NOINDEX"
    EXTERNAL_ASSESSMENT_FAILED = "EXTERNAL_ASSESSMENT_FAILED"
    EXTERNAL_ASSESSMENT_NOT_EVALUATED = "EXTERNAL_ASSESSMENT_NOT_EVALUATED"
    LOCAL_VALIDATION_FAILED = "LOCAL_VALIDATION_FAILED"
    INDEX_INTENT_INCONSISTENT = "INDEX_INTENT_INCONSISTENT"
    LASTMOD_INCONSISTENT = "LASTMOD_INCONSISTENT"
    VISIBLE_BINDING_MISMATCH = "VISIBLE_BINDING_MISMATCH"


class ExecutionStatus(str, Enum):
    NOT_EXECUTED = "NOT_EXECUTED"


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


class SeoValueConstructionError(ValueError):
    """Closed value-construction error that never echoes caller material."""

    __slots__ = ()

    def __init__(self) -> None:
        super().__init__("INVALID_EXACT_VALUE")


def _fail_value_construction() -> NoReturn:
    raise SeoValueConstructionError() from None


@dataclass(frozen=True, slots=True, repr=False)
class ReferenceId(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _REFERENCE.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class Sha256Digest(_Redacted):
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or _SHA256.fullmatch(self.value) is None:
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class UtcInstant(_Redacted):
    value: datetime

    def __post_init__(self) -> None:
        if not _valid_datetime(self.value):
            _fail_value_construction()


@dataclass(frozen=True, slots=True, repr=False)
class BoundEvidence(_Redacted):
    reference: ReferenceId
    sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class ContractBindings(_Redacted):
    seo_policy_id: str
    seo_policy_version: str
    seo_policy_sha256: Sha256Digest
    seo_metadata_schema_id: str
    seo_metadata_schema_sha256: Sha256Digest
    structured_data_manifest_schema_id: str
    structured_data_manifest_schema_sha256: Sha256Digest
    content_test_matrix_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class SeoMetadataCandidate(_Redacted):
    seo_metadata_id: ReferenceId
    article_version_id: ReferenceId
    slug: str
    title: str
    meta_description: str
    canonical_route_ref: ReferenceId
    index_state: IndexState
    robots: tuple[RobotsDirective, ...]
    breadcrumb_refs: tuple[ReferenceId, ...]
    sitemap_inclusion: bool
    substantive_updated_at: UtcInstant
    structured_data_manifest_ref: ReferenceId


@dataclass(frozen=True, slots=True, repr=False)
class RouteBinding(_Redacted):
    article_version_id: ReferenceId
    current_route_ref: ReferenceId
    current_route: str
    canonical_route_ref: ReferenceId
    canonical_route: str


@dataclass(frozen=True, slots=True, repr=False)
class AuthorProjection(_Redacted):
    kind: AuthorKind
    display_name: str


@dataclass(frozen=True, slots=True, repr=False)
class VisibleArticleProjection(_Redacted):
    article_version_id: ReferenceId
    title: str
    h1: str
    author: AuthorProjection
    date_published: UtcInstant
    date_modified: UtcInstant
    visible_content_hash: Sha256Digest
    visible_content_profile: ReferenceId
    visible_content_source_sha256: Sha256Digest


@dataclass(frozen=True, slots=True, repr=False)
class BreadcrumbProjection(_Redacted):
    article_version_id: ReferenceId
    breadcrumb_ref: ReferenceId
    position: int
    name: str
    route: str


@dataclass(frozen=True, slots=True, repr=False)
class SiteProjection(_Redacted):
    website_name: str
    organization_name: str
    home_route: str


@dataclass(frozen=True, slots=True, repr=False)
class ChangeAssessment(_Redacted):
    article_version_id: ReferenceId
    classification: ChangeClassification
    previous_substantive_updated_at: UtcInstant | None


@dataclass(frozen=True, slots=True, repr=False)
class ExternalAssessment(_Redacted):
    article_version_id: ReferenceId
    check: ExternalCheck
    state: ExternalAssessmentState
    assessor_ref: ReferenceId
    evidence: BoundEvidence | None


@dataclass(frozen=True, slots=True, repr=False)
class SeoRenderRequest(_Redacted):
    contracts: ContractBindings
    metadata: SeoMetadataCandidate
    route: RouteBinding
    visible: VisibleArticleProjection
    breadcrumbs: tuple[BreadcrumbProjection, ...]
    site_projection: SiteProjection | None
    article_schema_type: ArticleSchemaType
    mode: RenderMode
    origin_mode: OriginMode
    caller_origin: str | None
    change: ChangeAssessment
    external_assessments: tuple[ExternalAssessment, ...]
    validated_at: UtcInstant


@dataclass(frozen=True, slots=True, repr=False)
class FieldBindingLedgerEntry(_Redacted):
    field: BindingField
    source_pointer: VisibleSourcePointer
    comparison: ComparisonKind
    result: ComparisonResult
    position: int | None


@dataclass(frozen=True, slots=True, repr=False)
class RenderedSeoMetadata(_Redacted):
    seo_metadata_id: ReferenceId
    article_version_id: ReferenceId
    slug: str
    title: str
    meta_description: str
    canonical_route_ref: ReferenceId
    canonical_url: str | None
    index_state: IndexState
    robots: tuple[RobotsDirective, ...]
    breadcrumb_refs: tuple[ReferenceId, ...]
    sitemap_inclusion: bool
    substantive_updated_at: UtcInstant
    structured_data_manifest_ref: ReferenceId


@dataclass(frozen=True, slots=True, repr=False)
class LocalStructuredDataManifest(_Redacted):
    manifest_id: ReferenceId
    article_version_id: ReferenceId
    generator_version: str
    enabled_types: tuple[str, ...]
    disabled_types: tuple[DisabledSchemaType, ...]
    visible_content_hash: Sha256Digest
    jsonld_sha256: Sha256Digest
    validated_at: UtcInstant
    validation_result: LocalValidationResult


@dataclass(frozen=True, slots=True, repr=False)
class SeoRenderResult(_Redacted):
    status: RenderStatus
    input_findings: tuple[InputFindingCode, ...]
    raw_metadata_candidate: SeoMetadataCandidate | None
    rendered_metadata: RenderedSeoMetadata | None
    jsonld_json: str | None
    structured_data_manifest: LocalStructuredDataManifest | None
    binding_ledger: tuple[FieldBindingLedgerEntry, ...]
    external_assessments: tuple[ExternalAssessment, ...]
    conditional_local_eligibility: bool
    eligibility_reasons: tuple[EligibilityReason, ...]
    local_render_profile: str
    local_result_json: str
    local_result_digest: str
    origin_source: OriginSource
    domain_approved: bool
    production_domain_selected: bool
    approval_authorized: bool
    publication_authorized: bool
    release_authorized: bool
    production_authorized: bool
    production_eligible: bool
    formal_evidence: bool
    browser_executed: bool
    staging_executed: bool
    tst_020_executed: bool
    tst_022_executed: bool
    formal_test_status: ExecutionStatus
    tst_020_status: ExecutionStatus
    tst_022_status: ExecutionStatus
    runtime_status: ExecutionStatus
    live_validation_status: ExecutionStatus
    browser_status: ExecutionStatus
    staging_status: ExecutionStatus
    release_status: ExecutionStatus
    production_status: ExecutionStatus


def _valid_datetime(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is timezone.utc
        and value.utcoffset() == timezone.utc.utcoffset(value)
        and value.fold == 0
    )


def _valid_reference(value: object) -> bool:
    return (
        type(value) is ReferenceId
        and type(value.value) is str
        and _REFERENCE.fullmatch(value.value) is not None
    )


def _valid_sha256(value: object) -> bool:
    return (
        type(value) is Sha256Digest
        and type(value.value) is str
        and _SHA256.fullmatch(value.value) is not None
    )


def _valid_instant(value: object) -> bool:
    return type(value) is UtcInstant and _valid_datetime(value.value)


def _valid_bound_evidence(value: object) -> bool:
    return (
        type(value) is BoundEvidence
        and _valid_reference(value.reference)
        and _valid_sha256(value.sha256)
    )


def _reference_components(value: str) -> tuple[str, ...]:
    return tuple(part for part in re.split(r"[^A-Z0-9]+", value.upper()) if part)


def _has_prohibited_reference(value: ReferenceId) -> bool:
    parts = _reference_components(value.value)
    direct = {
        "COMMISSION",
        "CREDENTIAL",
        "EARNINGS",
        "EPC",
        "FINANCE",
        "MARGIN",
        "PASSWORD",
        "PAYOUT",
        "PROFIT",
        "PROMPT",
        "REVENUE",
        "RPM",
        "SECRET",
        "TOKEN",
    }
    if any(part in direct for part in parts):
        return True
    return bool(
        set(zip(parts, parts[1:], strict=False))
        & {
            ("AFFILIATE", "RATE"),
            ("API", "KEY"),
            ("PRIVATE", "KEY"),
            ("RAW", "CONTENT"),
            ("RAW", "PROMPT"),
            ("RAW", "REVIEW"),
            ("REVIEW", "BODY"),
            ("SOURCE", "BODY"),
        }
    )


def _valid_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and bool(value)
        and len(value) <= maximum
        and value == value.strip()
        and not any(ord(character) < 32 or ord(character) == 127 for character in value)
    )


def _valid_route(value: object) -> bool:
    return (
        type(value) is str
        and _ROUTE.fullmatch(value) is not None
        and "//" not in value
        and "/./" not in value
        and "/../" not in value
        and not value.endswith("/.")
        and not value.endswith("/..")
    )


def _normalize_origin(value: object) -> tuple[bool, str | None]:
    if value is None:
        return True, None
    if type(value) is not str or not value.startswith("https://"):
        return False, None
    normalized = value[:-1] if value.endswith("/") else value
    authority = normalized.removeprefix("https://")
    if (
        not authority
        or len(authority) > 259
        or any(marker in authority for marker in ("/", "?", "#", "@"))
    ):
        return False, None
    host, separator, port = authority.rpartition(":")
    if not separator:
        host = authority
    elif (
        not port
        or not port.isascii()
        or not port.isdecimal()
        or port.startswith("0")
        or int(port) > 65535
        or int(port) == 443
    ):
        return False, None
    if _HOST.fullmatch(host) is None or len(host) > 253:
        return False, None
    return True, normalized


def _valid_contracts(value: object) -> bool:
    return (
        type(value) is ContractBindings
        and type(value.seo_policy_id) is str
        and value.seo_policy_id == SEO_POLICY_ID
        and type(value.seo_policy_version) is str
        and value.seo_policy_version == SEO_POLICY_VERSION
        and _valid_sha256(value.seo_policy_sha256)
        and value.seo_policy_sha256.value == SEO_POLICY_SHA256
        and type(value.seo_metadata_schema_id) is str
        and value.seo_metadata_schema_id == SEO_METADATA_SCHEMA_ID
        and _valid_sha256(value.seo_metadata_schema_sha256)
        and value.seo_metadata_schema_sha256.value == SEO_METADATA_SCHEMA_SHA256
        and type(value.structured_data_manifest_schema_id) is str
        and value.structured_data_manifest_schema_id
        == STRUCTURED_DATA_MANIFEST_SCHEMA_ID
        and _valid_sha256(value.structured_data_manifest_schema_sha256)
        and value.structured_data_manifest_schema_sha256.value
        == STRUCTURED_DATA_MANIFEST_SCHEMA_SHA256
        and _valid_sha256(value.content_test_matrix_sha256)
        and value.content_test_matrix_sha256.value == CONTENT_TEST_MATRIX_SHA256
    )


def _valid_metadata(value: object, findings: set[InputFindingCode]) -> bool:
    if type(value) is not SeoMetadataCandidate:
        findings.add(InputFindingCode.METADATA_INVALID)
        return False
    valid_references = (
        value.seo_metadata_id,
        value.article_version_id,
        value.canonical_route_ref,
        value.structured_data_manifest_ref,
    )
    valid = (
        all(_valid_reference(item) for item in valid_references)
        and type(value.slug) is str
        and _SLUG.fullmatch(value.slug) is not None
        and _valid_text(value.title, maximum=300)
        and _valid_text(value.meta_description, maximum=500)
        and type(value.index_state) is IndexState
        and type(value.robots) is tuple
        and bool(value.robots)
        and all(type(item) is RobotsDirective for item in value.robots)
        and len(set(value.robots)) == len(value.robots)
        and type(value.breadcrumb_refs) is tuple
        and 1 <= len(value.breadcrumb_refs) <= 10
        and all(_valid_reference(item) for item in value.breadcrumb_refs)
        and len({item.value for item in value.breadcrumb_refs})
        == len(value.breadcrumb_refs)
        and type(value.sitemap_inclusion) is bool
        and _valid_instant(value.substantive_updated_at)
    )
    if not valid:
        findings.add(InputFindingCode.METADATA_INVALID)
    if type(value.robots) is not tuple or (
        type(value.robots) is tuple
        and (
            not value.robots
            or any(type(item) is not RobotsDirective for item in value.robots)
            or len(set(value.robots)) != len(value.robots)
        )
    ):
        findings.add(InputFindingCode.ROBOTS_INVALID)
    if all(_valid_reference(item) for item in valid_references) and any(
        _has_prohibited_reference(item) for item in valid_references
    ):
        findings.add(InputFindingCode.PROHIBITED_INPUT)
    return valid


def _valid_route_binding(value: object, findings: set[InputFindingCode]) -> bool:
    if type(value) is not RouteBinding:
        findings.add(InputFindingCode.ROUTE_INVALID)
        return False
    valid = (
        _valid_reference(value.article_version_id)
        and _valid_reference(value.current_route_ref)
        and _valid_reference(value.canonical_route_ref)
        and _valid_route(value.current_route)
        and _valid_route(value.canonical_route)
    )
    if not valid:
        findings.add(InputFindingCode.ROUTE_INVALID)
    if _valid_reference(value.article_version_id) and _has_prohibited_reference(
        value.article_version_id
    ):
        findings.add(InputFindingCode.PROHIBITED_INPUT)
    return valid


def _valid_visible(value: object, findings: set[InputFindingCode]) -> bool:
    if type(value) is not VisibleArticleProjection:
        findings.add(InputFindingCode.VISIBLE_PROJECTION_INVALID)
        return False
    author_valid = (
        type(value.author) is AuthorProjection
        and type(value.author.kind) is AuthorKind
        and _valid_text(value.author.display_name, maximum=300)
    )
    if not author_valid:
        findings.add(InputFindingCode.AUTHOR_INVALID)
    valid = (
        _valid_reference(value.article_version_id)
        and _valid_text(value.title, maximum=300)
        and _valid_text(value.h1, maximum=300)
        and author_valid
        and _valid_instant(value.date_published)
        and _valid_instant(value.date_modified)
        and value.date_modified.value >= value.date_published.value
        and _valid_sha256(value.visible_content_hash)
        and _valid_reference(value.visible_content_profile)
        and _valid_sha256(value.visible_content_source_sha256)
    )
    if not valid:
        findings.add(InputFindingCode.VISIBLE_PROJECTION_INVALID)
    if (
        _valid_reference(value.article_version_id)
        and _valid_reference(value.visible_content_profile)
        and (
            _has_prohibited_reference(value.article_version_id)
            or _has_prohibited_reference(value.visible_content_profile)
        )
    ):
        findings.add(InputFindingCode.PROHIBITED_INPUT)
    return valid


def _validate_breadcrumbs(
    value: object,
    *,
    article_version_id: ReferenceId,
    expected_refs: tuple[ReferenceId, ...],
    route: RouteBinding,
    findings: set[InputFindingCode],
) -> tuple[BreadcrumbProjection, ...]:
    if type(value) is not tuple:
        findings.add(InputFindingCode.BREADCRUMB_COLLECTION_INVALID)
        return ()
    records: list[BreadcrumbProjection] = []
    seen_refs: set[str] = set()
    seen_positions: set[int] = set()
    for item in cast(tuple[object, ...], value):
        if type(item) is not BreadcrumbProjection:
            findings.add(InputFindingCode.BREADCRUMB_RECORD_INVALID)
            continue
        if (
            not _valid_reference(item.article_version_id)
            or not _valid_reference(item.breadcrumb_ref)
            or type(item.position) is not int
            or item.position <= 0
            or not _valid_text(item.name, maximum=300)
            or not _valid_route(item.route)
        ):
            findings.add(InputFindingCode.BREADCRUMB_RECORD_INVALID)
            continue
        if item.article_version_id != article_version_id:
            findings.add(InputFindingCode.ARTICLE_BINDING_MISMATCH)
        if item.breadcrumb_ref.value in seen_refs or item.position in seen_positions:
            findings.add(InputFindingCode.BREADCRUMB_DUPLICATE)
        seen_refs.add(item.breadcrumb_ref.value)
        seen_positions.add(item.position)
        if _has_prohibited_reference(item.breadcrumb_ref):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
        records.append(item)
    ordered = tuple(sorted(records, key=lambda item: item.position))
    if tuple(item.position for item in ordered) != tuple(range(1, len(ordered) + 1)):
        findings.add(InputFindingCode.BREADCRUMB_POSITION_INVALID)
    if {item.breadcrumb_ref.value for item in ordered} != {
        item.value for item in expected_refs
    } or len(ordered) != len(expected_refs):
        findings.add(InputFindingCode.BREADCRUMB_SET_MISMATCH)
    if ordered and (
        ordered[-1].breadcrumb_ref != route.current_route_ref
        or ordered[-1].route != route.current_route
    ):
        findings.add(InputFindingCode.ROUTE_MISMATCH)
    return ordered


def _valid_site_projection(value: object, findings: set[InputFindingCode]) -> bool:
    if value is None:
        return True
    valid = (
        type(value) is SiteProjection
        and _valid_text(value.website_name, maximum=300)
        and _valid_text(value.organization_name, maximum=300)
        and _valid_route(value.home_route)
        and value.home_route == "/"
    )
    if not valid:
        findings.add(InputFindingCode.SITE_PROJECTION_INVALID)
    return valid


def _validate_external_assessments(
    value: object,
    *,
    article_version_id: ReferenceId,
    findings: set[InputFindingCode],
) -> tuple[ExternalAssessment, ...]:
    if type(value) is not tuple:
        findings.add(InputFindingCode.ASSESSMENT_COLLECTION_INVALID)
        return ()
    records: dict[ExternalCheck, ExternalAssessment] = {}
    for item in cast(tuple[object, ...], value):
        if type(item) is not ExternalAssessment:
            findings.add(InputFindingCode.ASSESSMENT_RECORD_INVALID)
            continue
        if (
            not _valid_reference(item.article_version_id)
            or type(item.check) is not ExternalCheck
            or type(item.state) is not ExternalAssessmentState
            or not _valid_reference(item.assessor_ref)
        ):
            findings.add(InputFindingCode.ASSESSMENT_RECORD_INVALID)
            continue
        if item.article_version_id != article_version_id:
            findings.add(InputFindingCode.ARTICLE_BINDING_MISMATCH)
        if item.check in records:
            findings.add(InputFindingCode.ASSESSMENT_DUPLICATE)
        records[item.check] = item
        proof_valid = (
            item.evidence is None
            if item.state is ExternalAssessmentState.NOT_EVALUATED
            else _valid_bound_evidence(item.evidence)
        )
        if not proof_valid:
            findings.add(InputFindingCode.ASSESSMENT_PROOF_INVALID)
        evidence = item.evidence
        if _valid_bound_evidence(evidence):
            assert type(evidence) is BoundEvidence
            if _has_prohibited_reference(evidence.reference):
                findings.add(InputFindingCode.PROHIBITED_INPUT)
        if _valid_reference(item.assessor_ref) and _has_prohibited_reference(
            item.assessor_ref
        ):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
    if set(records) != set(ExternalCheck):
        findings.add(InputFindingCode.ASSESSMENT_SET_MISMATCH)
    return tuple(records[item] for item in ExternalCheck if item in records)


def _lastmod_is_valid(
    metadata: SeoMetadataCandidate,
    visible: VisibleArticleProjection,
    change: object,
) -> bool:
    if (
        type(change) is not ChangeAssessment
        or not _valid_reference(change.article_version_id)
        or type(change.classification) is not ChangeClassification
        or (
            change.previous_substantive_updated_at is not None
            and not _valid_instant(change.previous_substantive_updated_at)
        )
    ):
        return False
    previous = change.previous_substantive_updated_at
    current = metadata.substantive_updated_at
    if change.classification is ChangeClassification.INITIAL_PUBLICATION:
        return previous is None and current == visible.date_modified
    if change.classification is ChangeClassification.SUBSTANTIVE:
        return (
            previous is not None
            and current == visible.date_modified
            and current.value > previous.value
        )
    return (
        previous is not None
        and current == previous
        and visible.date_modified == previous
    )


def _public_index_intent_is_consistent(value: SeoMetadataCandidate) -> bool:
    directives = set(value.robots)
    if RobotsDirective.FOLLOW in directives and RobotsDirective.NOFOLLOW in directives:
        return False
    if value.index_state is IndexState.INDEX:
        return (
            RobotsDirective.INDEX in directives
            and RobotsDirective.NOINDEX not in directives
        )
    return (
        RobotsDirective.NOINDEX in directives
        and RobotsDirective.INDEX not in directives
        and value.sitemap_inclusion is False
    )


def _instant_text(value: UtcInstant) -> str:
    return value.value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _safe_json(value: JsonValue) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def _sha256_text(value: str) -> Sha256Digest:
    return Sha256Digest(hashlib.sha256(value.encode("utf-8")).hexdigest())


_FORBIDDEN_STRUCTURED_TYPES = {item.value for item in DisabledSchemaType}
_ALLOWED_STRUCTURED_TYPES = {
    "Article",
    "BlogPosting",
    "BreadcrumbList",
    "ListItem",
    "Organization",
    "Person",
    "WebSite",
}
_FORBIDDEN_STRUCTURED_PROPERTIES = {
    "aggregateRating",
    "availability",
    "bestRating",
    "description",
    "highPrice",
    "image",
    "keywords",
    "logo",
    "lowPrice",
    "offer",
    "offers",
    "price",
    "priceCurrency",
    "publisher",
    "rating",
    "ratingCount",
    "ratingValue",
    "review",
    "reviewBody",
    "reviewCount",
    "reviewRating",
    "sameAs",
    "worstRating",
}
_ALLOWED_STRUCTURED_PROPERTIES = {
    "@context",
    "@graph",
    "@type",
    "author",
    "dateModified",
    "datePublished",
    "headline",
    "item",
    "itemListElement",
    "mainEntityOfPage",
    "name",
    "position",
    "url",
}


def _structured_data_tree_is_valid(
    value: object,
    *,
    expected_author: dict[str, JsonValue],
) -> bool:
    if value is None or type(value) in {str, int, bool}:
        return True
    if type(value) is list:
        return all(
            _structured_data_tree_is_valid(item, expected_author=expected_author)
            for item in cast(list[object], value)
        )
    if type(value) is not dict:
        return False
    for key, item in cast(dict[object, object], value).items():
        if (
            type(key) is not str
            or key in _FORBIDDEN_STRUCTURED_PROPERTIES
            or key not in _ALLOWED_STRUCTURED_PROPERTIES
        ):
            return False
        if key == "@type":
            if (
                type(item) is not str
                or item in _FORBIDDEN_STRUCTURED_TYPES
                or item not in _ALLOWED_STRUCTURED_TYPES
            ):
                return False
        if key == "author" and item != expected_author:
            return False
        if not _structured_data_tree_is_valid(item, expected_author=expected_author):
            return False
    return True


def _absolute_url(origin: str, route: str) -> str:
    return f"{origin}{route}"


def _build_jsonld(
    request: SeoRenderRequest,
    *,
    origin: str | None,
    breadcrumbs: tuple[BreadcrumbProjection, ...],
) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    author: dict[str, JsonValue] = {
        "@type": request.visible.author.kind.value,
        "name": request.visible.author.display_name,
    }
    article: dict[str, JsonValue] = {
        "@type": request.article_schema_type.value,
        "author": author,
        "dateModified": _instant_text(request.visible.date_modified),
        "datePublished": _instant_text(request.visible.date_published),
        "headline": request.visible.h1,
    }
    if origin is not None:
        canonical_url = _absolute_url(origin, request.route.canonical_route)
        article["mainEntityOfPage"] = canonical_url
        article["url"] = canonical_url

    graph: list[JsonValue] = [article]
    enabled: list[str] = [request.article_schema_type.value]
    if origin is not None:
        graph.append(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "item": _absolute_url(origin, item.route),
                        "name": item.name,
                        "position": item.position,
                    }
                    for item in breadcrumbs
                ],
            }
        )
        enabled.append("BreadcrumbList")
    if origin is not None and request.site_projection is not None:
        graph.extend(
            (
                {
                    "@type": "Organization",
                    "name": request.site_projection.organization_name,
                    "url": _absolute_url(origin, request.site_projection.home_route),
                },
                {
                    "@type": "WebSite",
                    "name": request.site_projection.website_name,
                    "url": _absolute_url(origin, request.site_projection.home_route),
                },
            )
        )
        enabled.extend(("Organization", "WebSite"))
    enabled_order = (
        "Article",
        "BlogPosting",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    )
    return (
        {"@context": "https://schema.org", "@graph": graph},
        tuple(item for item in enabled_order if item in set(enabled)),
    )


def _expected_jsonld_profile(
    request: SeoRenderRequest,
    *,
    origin: str | None,
    breadcrumbs: tuple[BreadcrumbProjection, ...],
) -> tuple[dict[str, JsonValue], tuple[str, ...]]:
    article: dict[str, JsonValue] = {
        "@type": request.article_schema_type.value,
        "author": {
            "@type": request.visible.author.kind.value,
            "name": request.visible.author.display_name,
        },
        "dateModified": _instant_text(request.visible.date_modified),
        "datePublished": _instant_text(request.visible.date_published),
        "headline": request.visible.h1,
    }
    graph: list[JsonValue] = [article]
    enabled: list[str] = [request.article_schema_type.value]
    if origin is not None:
        canonical_url = _absolute_url(origin, request.route.canonical_route)
        article["mainEntityOfPage"] = canonical_url
        article["url"] = canonical_url
        graph.append(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "item": _absolute_url(origin, item.route),
                        "name": item.name,
                        "position": item.position,
                    }
                    for item in breadcrumbs
                ],
            }
        )
        enabled.append("BreadcrumbList")
    if origin is not None and request.site_projection is not None:
        home_url = _absolute_url(origin, request.site_projection.home_route)
        graph.extend(
            (
                {
                    "@type": "Organization",
                    "name": request.site_projection.organization_name,
                    "url": home_url,
                },
                {
                    "@type": "WebSite",
                    "name": request.site_projection.website_name,
                    "url": home_url,
                },
            )
        )
        enabled.extend(("Organization", "WebSite"))
    enabled_order = (
        "Article",
        "BlogPosting",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    )
    return (
        {"@context": "https://schema.org", "@graph": graph},
        tuple(item for item in enabled_order if item in set(enabled)),
    )


def _mapping_value(value: object, key: str) -> object:
    if type(value) is not dict:
        return None
    return cast(dict[object, object], value).get(key)


def _mapping_omits(value: object, first: str, second: str) -> bool:
    if type(value) is not dict:
        return False
    mapping = cast(dict[object, object], value)
    return first not in mapping and second not in mapping


def _exact_json_equal(actual: object, expected: object) -> bool:
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        if type(actual) is not dict:
            return False
        actual_mapping = cast(dict[object, object], actual)
        expected_mapping = cast(dict[object, object], expected)
        if actual_mapping.keys() != expected_mapping.keys():
            return False
        return all(
            _exact_json_equal(actual_mapping[key], expected_mapping[key])
            for key in expected_mapping
        )
    if type(expected) is list:
        if type(actual) is not list:
            return False
        actual_items = cast(list[object], actual)
        expected_items = cast(list[object], expected)
        if len(actual_items) != len(expected_items):
            return False
        return all(
            _exact_json_equal(actual_item, expected_item)
            for actual_item, expected_item in zip(
                actual_items,
                expected_items,
                strict=True,
            )
        )
    return actual == expected


def _comparison(value: bool) -> ComparisonResult:
    return ComparisonResult.MATCH if value else ComparisonResult.MISMATCH


def _binding_ledger(
    request: SeoRenderRequest,
    *,
    origin: str | None,
    breadcrumbs: tuple[BreadcrumbProjection, ...],
    jsonld: object,
    enabled_types: object,
    expected_jsonld: dict[str, JsonValue],
    expected_enabled_types: tuple[str, ...],
) -> tuple[FieldBindingLedgerEntry, ...]:
    graph_value = _mapping_value(jsonld, "@graph")
    graph = cast(list[object], graph_value) if type(graph_value) is list else []
    article: object = graph[0] if graph else None
    expected_author: dict[str, JsonValue] = {
        "@type": request.visible.author.kind.value,
        "name": request.visible.author.display_name,
    }
    expected_canonical_url = (
        _absolute_url(origin, request.route.canonical_route)
        if origin is not None
        else None
    )
    canonical_url_matches = (
        _mapping_value(article, "url") == expected_canonical_url
        and _mapping_value(article, "mainEntityOfPage") == expected_canonical_url
        if origin is not None
        else _mapping_omits(article, "url", "mainEntityOfPage")
    )
    entries = [
        FieldBindingLedgerEntry(
            BindingField.METADATA_TITLE,
            VisibleSourcePointer.VISIBLE_TITLE,
            ComparisonKind.EXACT_TEXT,
            (
                ComparisonResult.MATCH
                if request.metadata.title == request.visible.title
                else ComparisonResult.MISMATCH
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.VISIBLE_H1,
            VisibleSourcePointer.VISIBLE_TITLE,
            ComparisonKind.EXACT_TEXT,
            (
                ComparisonResult.MATCH
                if request.visible.h1 == request.visible.title
                else ComparisonResult.MISMATCH
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_HEADLINE,
            VisibleSourcePointer.VISIBLE_H1,
            ComparisonKind.EXACT_TEXT,
            _comparison(_mapping_value(article, "headline") == request.visible.h1),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_AUTHOR,
            VisibleSourcePointer.VISIBLE_AUTHOR,
            ComparisonKind.EXACT_STRUCTURE,
            _comparison(
                _exact_json_equal(_mapping_value(article, "author"), expected_author)
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_DATE_PUBLISHED,
            VisibleSourcePointer.VISIBLE_DATE_PUBLISHED,
            ComparisonKind.EXACT_TIMESTAMP,
            _comparison(
                _mapping_value(article, "datePublished")
                == _instant_text(request.visible.date_published)
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_DATE_MODIFIED,
            VisibleSourcePointer.VISIBLE_DATE_MODIFIED,
            ComparisonKind.EXACT_TIMESTAMP,
            _comparison(
                _mapping_value(article, "dateModified")
                == _instant_text(request.visible.date_modified)
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_SCHEMA_TYPE,
            VisibleSourcePointer.CALLER_ARTICLE_SCHEMA_TYPE,
            ComparisonKind.EXACT_TYPE,
            _comparison(
                _mapping_value(article, "@type") == request.article_schema_type.value
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_CANONICAL_URL,
            VisibleSourcePointer.CANONICAL_ROUTE,
            ComparisonKind.EXACT_URL,
            _comparison(canonical_url_matches),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.JSONLD_PROFILE_SHAPE,
            VisibleSourcePointer.LOCAL_RENDER_PROFILE,
            ComparisonKind.EXACT_STRUCTURE,
            _comparison(
                _exact_json_equal(jsonld, expected_jsonld)
                and type(enabled_types) is tuple
                and enabled_types == expected_enabled_types
            ),
            None,
        ),
        FieldBindingLedgerEntry(
            BindingField.CANONICAL_ROUTE,
            VisibleSourcePointer.CURRENT_ROUTE,
            ComparisonKind.EXACT_ROUTE,
            (
                ComparisonResult.MATCH
                if request.route.current_route == request.route.canonical_route
                else ComparisonResult.MISMATCH
            ),
            None,
        ),
    ]
    breadcrumb_node = graph[1] if origin is not None and len(graph) > 1 else None
    item_list_value = _mapping_value(breadcrumb_node, "itemListElement")
    item_list = (
        cast(list[object], item_list_value) if type(item_list_value) is list else []
    )
    if origin is not None:
        for item in breadcrumbs:
            actual = (
                item_list[item.position - 1]
                if len(item_list) >= item.position
                else None
            )
            entries.extend(
                (
                    FieldBindingLedgerEntry(
                        BindingField.BREADCRUMB_NAME,
                        VisibleSourcePointer.VISIBLE_BREADCRUMB_NAME,
                        ComparisonKind.EXACT_TEXT,
                        _comparison(_mapping_value(actual, "name") == item.name),
                        item.position,
                    ),
                    FieldBindingLedgerEntry(
                        BindingField.BREADCRUMB_ROUTE,
                        VisibleSourcePointer.VISIBLE_BREADCRUMB_ROUTE,
                        ComparisonKind.EXACT_URL,
                        _comparison(
                            _mapping_value(actual, "item")
                            == _absolute_url(origin, item.route)
                        ),
                        item.position,
                    ),
                    FieldBindingLedgerEntry(
                        BindingField.BREADCRUMB_POSITION,
                        VisibleSourcePointer.VISIBLE_BREADCRUMB_POSITION,
                        ComparisonKind.ORDERED_POSITION,
                        _comparison(
                            type(_mapping_value(actual, "position")) is int
                            and _mapping_value(actual, "position") == item.position
                        ),
                        item.position,
                    ),
                )
            )
    return tuple(entries)


def _authority_payload(origin_source: OriginSource) -> dict[str, JsonValue]:
    return {
        "approval_authorized": False,
        "browser": ExecutionStatus.NOT_EXECUTED.value,
        "browser_executed": False,
        "domain_approved": False,
        "formal_evidence": False,
        "formal_test": ExecutionStatus.NOT_EXECUTED.value,
        "live_validation": ExecutionStatus.NOT_EXECUTED.value,
        "origin_source": origin_source.value,
        "production": ExecutionStatus.NOT_EXECUTED.value,
        "production_authorized": False,
        "production_domain_selected": False,
        "production_eligible": False,
        "publication_authorized": False,
        "release": ExecutionStatus.NOT_EXECUTED.value,
        "release_authorized": False,
        "runtime": ExecutionStatus.NOT_EXECUTED.value,
        "staging": ExecutionStatus.NOT_EXECUTED.value,
        "staging_executed": False,
        "tst_020": ExecutionStatus.NOT_EXECUTED.value,
        "tst_020_executed": False,
        "tst_022": ExecutionStatus.NOT_EXECUTED.value,
        "tst_022_executed": False,
    }


def _invalid_local_result(
    findings: set[InputFindingCode],
    *,
    origin_source: OriginSource,
) -> SeoRenderResult:
    ordered = tuple(item for item in InputFindingCode if item in findings)
    payload: dict[str, JsonValue] = {
        "authority": _authority_payload(origin_source),
        "input_findings": [item.value for item in ordered],
        "profile": LOCAL_RENDER_PROFILE,
        "status": RenderStatus.INVALID_INPUT.value,
    }
    local_json = _safe_json(payload)
    return SeoRenderResult(
        status=RenderStatus.INVALID_INPUT,
        input_findings=ordered,
        raw_metadata_candidate=None,
        rendered_metadata=None,
        jsonld_json=None,
        structured_data_manifest=None,
        binding_ledger=(),
        external_assessments=(),
        conditional_local_eligibility=False,
        eligibility_reasons=(EligibilityReason.LOCAL_VALIDATION_FAILED,),
        local_render_profile=LOCAL_RENDER_PROFILE,
        local_result_json=local_json,
        local_result_digest=_sha256_text(local_json).value,
        origin_source=origin_source,
        domain_approved=False,
        production_domain_selected=False,
        approval_authorized=False,
        publication_authorized=False,
        release_authorized=False,
        production_authorized=False,
        production_eligible=False,
        formal_evidence=False,
        browser_executed=False,
        staging_executed=False,
        tst_020_executed=False,
        tst_022_executed=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        tst_020_status=ExecutionStatus.NOT_EXECUTED,
        tst_022_status=ExecutionStatus.NOT_EXECUTED,
        runtime_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        browser_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )


def _metadata_payload(value: SeoMetadataCandidate) -> dict[str, JsonValue]:
    return {
        "article_version_id": value.article_version_id.value,
        "breadcrumb_refs": [item.value for item in value.breadcrumb_refs],
        "canonical_route_ref": value.canonical_route_ref.value,
        "index_state": value.index_state.value,
        "meta_description": value.meta_description,
        "robots": [item.value for item in _ordered_robots(value.robots)],
        "seo_metadata_id": value.seo_metadata_id.value,
        "sitemap_inclusion": value.sitemap_inclusion,
        "slug": value.slug,
        "structured_data_manifest_ref": value.structured_data_manifest_ref.value,
        "substantive_updated_at": _instant_text(value.substantive_updated_at),
        "title": value.title,
    }


def _rendered_metadata_payload(value: RenderedSeoMetadata) -> dict[str, JsonValue]:
    return {
        "article_version_id": value.article_version_id.value,
        "breadcrumb_refs": [item.value for item in value.breadcrumb_refs],
        "canonical_route_ref": value.canonical_route_ref.value,
        "canonical_url": value.canonical_url,
        "index_state": value.index_state.value,
        "meta_description": value.meta_description,
        "robots": [item.value for item in _ordered_robots(value.robots)],
        "seo_metadata_id": value.seo_metadata_id.value,
        "sitemap_inclusion": value.sitemap_inclusion,
        "slug": value.slug,
        "structured_data_manifest_ref": value.structured_data_manifest_ref.value,
        "substantive_updated_at": _instant_text(value.substantive_updated_at),
        "title": value.title,
    }


def _evidence_payload(value: BoundEvidence | None) -> JsonValue:
    if value is None:
        return None
    return {"ref": value.reference.value, "sha256": value.sha256.value}


def _ordered_robots(
    value: tuple[RobotsDirective, ...],
) -> tuple[RobotsDirective, ...]:
    selected = set(value)
    return tuple(item for item in RobotsDirective if item in selected)


def _result_payload(
    request: SeoRenderRequest,
    *,
    origin: str | None,
    breadcrumbs: tuple[BreadcrumbProjection, ...],
    assessments: tuple[ExternalAssessment, ...],
    rendered: RenderedSeoMetadata,
    manifest: LocalStructuredDataManifest,
    ledger: tuple[FieldBindingLedgerEntry, ...],
    jsonld_json: str,
    eligibility: bool,
    reasons: tuple[EligibilityReason, ...],
) -> dict[str, JsonValue]:
    origin_source = (
        OriginSource.NONE if origin is None else OriginSource.CALLER_SUPPLIED_UNAPPROVED
    )
    return {
        "article_schema_type": request.article_schema_type.value,
        "authority": _authority_payload(origin_source),
        "binding_ledger": [
            {
                "comparison": item.comparison.value,
                "field": item.field.value,
                "position": item.position,
                "result": item.result.value,
                "source_pointer": item.source_pointer.value,
            }
            for item in ledger
        ],
        "breadcrumbs": [
            {
                "article_version_id": item.article_version_id.value,
                "breadcrumb_ref": item.breadcrumb_ref.value,
                "name": item.name,
                "position": item.position,
                "route": item.route,
            }
            for item in breadcrumbs
        ],
        "caller_origin": origin,
        "change": {
            "article_version_id": request.change.article_version_id.value,
            "classification": request.change.classification.value,
            "previous_substantive_updated_at": (
                _instant_text(request.change.previous_substantive_updated_at)
                if request.change.previous_substantive_updated_at is not None
                else None
            ),
        },
        "conditional_local_eligibility": eligibility,
        "contracts": {
            "content_test_matrix_sha256": (
                request.contracts.content_test_matrix_sha256.value
            ),
            "seo_metadata_schema_id": request.contracts.seo_metadata_schema_id,
            "seo_metadata_schema_sha256": (
                request.contracts.seo_metadata_schema_sha256.value
            ),
            "seo_policy_id": request.contracts.seo_policy_id,
            "seo_policy_sha256": request.contracts.seo_policy_sha256.value,
            "seo_policy_version": request.contracts.seo_policy_version,
            "structured_data_manifest_schema_id": (
                request.contracts.structured_data_manifest_schema_id
            ),
            "structured_data_manifest_schema_sha256": (
                request.contracts.structured_data_manifest_schema_sha256.value
            ),
        },
        "eligibility_reasons": [item.value for item in reasons],
        "external_assessments": [
            {
                "article_version_id": item.article_version_id.value,
                "assessor_ref": item.assessor_ref.value,
                "check": item.check.value,
                "evidence": _evidence_payload(item.evidence),
                "state": item.state.value,
            }
            for item in assessments
        ],
        "jsonld_json": jsonld_json,
        "manifest": {
            "article_version_id": manifest.article_version_id.value,
            "disabled_types": [item.value for item in manifest.disabled_types],
            "enabled_types": list(manifest.enabled_types),
            "generator_version": manifest.generator_version,
            "jsonld_sha256": manifest.jsonld_sha256.value,
            "manifest_id": manifest.manifest_id.value,
            "validated_at": _instant_text(manifest.validated_at),
            "validation_result": manifest.validation_result.value,
            "visible_content_hash": manifest.visible_content_hash.value,
        },
        "mode": request.mode.value,
        "origin_mode": request.origin_mode.value,
        "profile": LOCAL_RENDER_PROFILE,
        "raw_metadata_candidate": _metadata_payload(request.metadata),
        "rendered_metadata": _rendered_metadata_payload(rendered),
        "route": {
            "article_version_id": request.route.article_version_id.value,
            "canonical_route": request.route.canonical_route,
            "canonical_route_ref": request.route.canonical_route_ref.value,
            "current_route": request.route.current_route,
            "current_route_ref": request.route.current_route_ref.value,
        },
        "site_projection": (
            {
                "home_route": request.site_projection.home_route,
                "organization_name": request.site_projection.organization_name,
                "website_name": request.site_projection.website_name,
            }
            if request.site_projection is not None
            else None
        ),
        "status": RenderStatus.RENDERED_LOCAL.value,
        "validated_at": _instant_text(request.validated_at),
        "visible": {
            "article_version_id": request.visible.article_version_id.value,
            "author": {
                "display_name": request.visible.author.display_name,
                "kind": request.visible.author.kind.value,
            },
            "date_modified": _instant_text(request.visible.date_modified),
            "date_published": _instant_text(request.visible.date_published),
            "h1": request.visible.h1,
            "title": request.visible.title,
            "visible_content_hash": request.visible.visible_content_hash.value,
            "visible_content_profile": request.visible.visible_content_profile.value,
            "visible_content_source_sha256": (
                request.visible.visible_content_source_sha256.value
            ),
        },
    }


def _validate_render_request(
    value: object,
) -> tuple[
    SeoRenderRequest | None,
    set[InputFindingCode],
    str | None,
    tuple[BreadcrumbProjection, ...],
    tuple[ExternalAssessment, ...],
]:
    findings: set[InputFindingCode] = set()
    if type(value) is not SeoRenderRequest:
        findings.add(InputFindingCode.INPUT_TYPE_INVALID)
        return None, findings, None, (), ()
    if not _valid_contracts(value.contracts):
        findings.add(InputFindingCode.CONTRACT_BINDING_INVALID)
    metadata_valid = _valid_metadata(value.metadata, findings)
    route_valid = _valid_route_binding(value.route, findings)
    visible_valid = _valid_visible(value.visible, findings)
    if type(value.article_schema_type) is not ArticleSchemaType:
        findings.add(InputFindingCode.ARTICLE_SCHEMA_TYPE_INVALID)
    if type(value.mode) is not RenderMode:
        findings.add(InputFindingCode.MODE_INVALID)
    if type(value.origin_mode) is not OriginMode:
        findings.add(InputFindingCode.ORIGIN_MODE_INVALID)
    origin_valid, origin = _normalize_origin(value.caller_origin)
    if not origin_valid:
        findings.add(InputFindingCode.ORIGIN_INVALID)
    if type(value.origin_mode) is OriginMode and (
        (value.origin_mode is OriginMode.ROUTE_ONLY and value.caller_origin is not None)
        or (
            value.origin_mode is OriginMode.CALLER_SUPPLIED_ORIGIN
            and value.caller_origin is None
        )
    ):
        findings.add(InputFindingCode.ORIGIN_MODE_MISMATCH)
    _valid_site_projection(value.site_projection, findings)
    if not _valid_instant(value.validated_at):
        findings.add(InputFindingCode.VALIDATED_AT_INVALID)

    article_version_id = (
        value.metadata.article_version_id
        if metadata_valid
        else ReferenceId("INVALID-ARTICLE-VERSION")
    )
    breadcrumbs = _validate_breadcrumbs(
        value.breadcrumbs,
        article_version_id=article_version_id,
        expected_refs=(value.metadata.breadcrumb_refs if metadata_valid else ()),
        route=(
            value.route
            if route_valid
            else RouteBinding(
                article_version_id,
                ReferenceId("INVALID-CURRENT-ROUTE"),
                "/",
                ReferenceId("INVALID-CANONICAL-ROUTE"),
                "/",
            )
        ),
        findings=findings,
    )
    assessments = _validate_external_assessments(
        value.external_assessments,
        article_version_id=article_version_id,
        findings=findings,
    )
    change_valid = (
        type(value.change) is ChangeAssessment
        and _valid_reference(value.change.article_version_id)
        and type(value.change.classification) is ChangeClassification
        and (
            value.change.previous_substantive_updated_at is None
            or _valid_instant(value.change.previous_substantive_updated_at)
        )
    )
    if not change_valid:
        findings.add(InputFindingCode.CHANGE_ASSESSMENT_INVALID)

    if metadata_valid and route_valid and visible_valid and change_valid:
        bound_ids = (
            value.route.article_version_id,
            value.visible.article_version_id,
            value.change.article_version_id,
        )
        if any(item != value.metadata.article_version_id for item in bound_ids):
            findings.add(InputFindingCode.ARTICLE_BINDING_MISMATCH)
        if value.metadata.canonical_route_ref != value.route.canonical_route_ref:
            findings.add(InputFindingCode.ROUTE_MISMATCH)
        if tuple(item.breadcrumb_ref for item in breadcrumbs) != (
            value.metadata.breadcrumb_refs
        ):
            findings.add(InputFindingCode.BREADCRUMB_SET_MISMATCH)
        if not _lastmod_is_valid(value.metadata, value.visible, value.change):
            findings.add(InputFindingCode.LASTMOD_INVALID)
        if _has_prohibited_reference(
            value.change.article_version_id
        ) or _has_prohibited_reference(value.metadata.article_version_id):
            findings.add(InputFindingCode.PROHIBITED_INPUT)
    return value, findings, origin, breadcrumbs, assessments


def _request_origin_source(value: object) -> OriginSource:
    if type(value) is SeoRenderRequest and value.caller_origin is not None:
        return OriginSource.CALLER_SUPPLIED_UNAPPROVED
    return OriginSource.NONE


def render_seo(value: object) -> SeoRenderResult:
    """Render one strict, pre-resolved local SEO and JSON-LD candidate."""

    request, findings, origin, breadcrumbs, assessments = _validate_render_request(
        value
    )
    if request is None or findings:
        return _invalid_local_result(
            findings,
            origin_source=_request_origin_source(value),
        )

    route_matches = request.route.current_route == request.route.canonical_route
    lastmod_valid = _lastmod_is_valid(
        request.metadata,
        request.visible,
        request.change,
    )
    preview = request.mode is RenderMode.PREVIEW
    rendered_index_state = (
        IndexState.NOINDEX if preview else request.metadata.index_state
    )
    rendered_robots = (
        (RobotsDirective.NOINDEX, RobotsDirective.NOFOLLOW)
        if preview
        else _ordered_robots(request.metadata.robots)
    )
    rendered_sitemap = False if preview else request.metadata.sitemap_inclusion
    rendered = RenderedSeoMetadata(
        seo_metadata_id=request.metadata.seo_metadata_id,
        article_version_id=request.metadata.article_version_id,
        slug=request.metadata.slug,
        title=request.metadata.title,
        meta_description=request.metadata.meta_description,
        canonical_route_ref=request.metadata.canonical_route_ref,
        canonical_url=(
            _absolute_url(origin, request.route.canonical_route)
            if origin is not None
            else None
        ),
        index_state=rendered_index_state,
        robots=rendered_robots,
        breadcrumb_refs=request.metadata.breadcrumb_refs,
        sitemap_inclusion=rendered_sitemap,
        substantive_updated_at=request.metadata.substantive_updated_at,
        structured_data_manifest_ref=(request.metadata.structured_data_manifest_ref),
    )
    index_intent_valid = _public_index_intent_is_consistent(
        SeoMetadataCandidate(
            seo_metadata_id=rendered.seo_metadata_id,
            article_version_id=rendered.article_version_id,
            slug=rendered.slug,
            title=rendered.title,
            meta_description=rendered.meta_description,
            canonical_route_ref=rendered.canonical_route_ref,
            index_state=rendered.index_state,
            robots=rendered.robots,
            breadcrumb_refs=rendered.breadcrumb_refs,
            sitemap_inclusion=rendered.sitemap_inclusion,
            substantive_updated_at=rendered.substantive_updated_at,
            structured_data_manifest_ref=rendered.structured_data_manifest_ref,
        )
    )
    jsonld, enabled_types = _build_jsonld(
        request,
        origin=origin,
        breadcrumbs=breadcrumbs,
    )
    expected_jsonld, expected_enabled_types = _expected_jsonld_profile(
        request,
        origin=origin,
        breadcrumbs=breadcrumbs,
    )
    expected_author: dict[str, JsonValue] = {
        "@type": request.visible.author.kind.value,
        "name": request.visible.author.display_name,
    }
    structured_data_valid = _structured_data_tree_is_valid(
        jsonld,
        expected_author=expected_author,
    ) and (
        _exact_json_equal(jsonld, expected_jsonld)
        and type(enabled_types) is tuple
        and enabled_types == expected_enabled_types
    )
    ledger = _binding_ledger(
        request,
        origin=origin,
        breadcrumbs=breadcrumbs,
        jsonld=jsonld,
        enabled_types=enabled_types,
        expected_jsonld=expected_jsonld,
        expected_enabled_types=expected_enabled_types,
    )
    visible_field_matches = all(
        item.result is ComparisonResult.MATCH
        for item in ledger
        if item.field is not BindingField.CANONICAL_ROUTE
    )
    visible_matches = all(item.result is ComparisonResult.MATCH for item in ledger)
    jsonld_json = _safe_json(jsonld)
    local_validation_passed = (
        visible_matches
        and lastmod_valid
        and index_intent_valid
        and structured_data_valid
    )
    manifest = LocalStructuredDataManifest(
        manifest_id=request.metadata.structured_data_manifest_ref,
        article_version_id=request.metadata.article_version_id,
        generator_version=LOCAL_RENDER_PROFILE,
        enabled_types=enabled_types,
        disabled_types=tuple(DisabledSchemaType),
        visible_content_hash=request.visible.visible_content_hash,
        jsonld_sha256=_sha256_text(jsonld_json),
        validated_at=request.validated_at,
        validation_result=(
            LocalValidationResult.PASS
            if local_validation_passed
            else LocalValidationResult.FAIL
        ),
    )

    reasons: list[EligibilityReason] = []
    if preview:
        reasons.append(EligibilityReason.PREVIEW_NOINDEX)
    if origin is None:
        reasons.append(EligibilityReason.ROUTE_ONLY_ORIGIN_UNAVAILABLE)
    if not route_matches:
        reasons.append(EligibilityReason.ROUTE_MISMATCH)
    if not visible_field_matches:
        reasons.append(EligibilityReason.VISIBLE_BINDING_MISMATCH)
    if not index_intent_valid:
        reasons.append(EligibilityReason.INDEX_INTENT_INCONSISTENT)
    if not lastmod_valid:
        reasons.append(EligibilityReason.LASTMOD_INCONSISTENT)
    if not structured_data_valid:
        reasons.append(EligibilityReason.LOCAL_VALIDATION_FAILED)
    if any(item.state is ExternalAssessmentState.FAIL for item in assessments):
        reasons.append(EligibilityReason.EXTERNAL_ASSESSMENT_FAILED)
    if any(item.state is ExternalAssessmentState.NOT_EVALUATED for item in assessments):
        reasons.append(EligibilityReason.EXTERNAL_ASSESSMENT_NOT_EVALUATED)
    ordered_reasons = tuple(item for item in EligibilityReason if item in set(reasons))
    eligibility = not ordered_reasons
    payload = _result_payload(
        request,
        origin=origin,
        breadcrumbs=breadcrumbs,
        assessments=assessments,
        rendered=rendered,
        manifest=manifest,
        ledger=ledger,
        jsonld_json=jsonld_json,
        eligibility=eligibility,
        reasons=ordered_reasons,
    )
    local_json = _safe_json(payload)
    origin_source = (
        OriginSource.NONE if origin is None else OriginSource.CALLER_SUPPLIED_UNAPPROVED
    )
    return SeoRenderResult(
        status=RenderStatus.RENDERED_LOCAL,
        input_findings=(),
        raw_metadata_candidate=request.metadata,
        rendered_metadata=rendered,
        jsonld_json=jsonld_json,
        structured_data_manifest=manifest,
        binding_ledger=ledger,
        external_assessments=assessments,
        conditional_local_eligibility=eligibility,
        eligibility_reasons=ordered_reasons,
        local_render_profile=LOCAL_RENDER_PROFILE,
        local_result_json=local_json,
        local_result_digest=_sha256_text(local_json).value,
        origin_source=origin_source,
        domain_approved=False,
        production_domain_selected=False,
        approval_authorized=False,
        publication_authorized=False,
        release_authorized=False,
        production_authorized=False,
        production_eligible=False,
        formal_evidence=False,
        browser_executed=False,
        staging_executed=False,
        tst_020_executed=False,
        tst_022_executed=False,
        formal_test_status=ExecutionStatus.NOT_EXECUTED,
        tst_020_status=ExecutionStatus.NOT_EXECUTED,
        tst_022_status=ExecutionStatus.NOT_EXECUTED,
        runtime_status=ExecutionStatus.NOT_EXECUTED,
        live_validation_status=ExecutionStatus.NOT_EXECUTED,
        browser_status=ExecutionStatus.NOT_EXECUTED,
        staging_status=ExecutionStatus.NOT_EXECUTED,
        release_status=ExecutionStatus.NOT_EXECUTED,
        production_status=ExecutionStatus.NOT_EXECUTED,
    )
