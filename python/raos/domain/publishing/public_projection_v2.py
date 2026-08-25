"""Pure, deterministic, process-local public projection candidate for ST-0904.

Only the exact immutable ST-0903 V2 request/result pair is accepted.  The
projector emits the closed public API shapes needed by a later renderer, but it
does not persist rows, activate a route, serve a public read, emit an event, or
carry publication/release/Production authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import hashlib
import re
from typing import Final, NoReturn, SupportsIndex, cast
from uuid import RFC_4122, UUID

from raos.domain.editorial.content_ast import (
    dump_content_ast_json,
    load_content_ast,
)
from raos.domain.publishing.publication_snapshot_v2 import (
    PublicationSnapshotBuildRequestV2,
    PublicationSnapshotResultV2,
    SnapshotContractCompatibility,
    canonical_json_bytes,
    parse_canonical_object,
)
from raos.domain.shared.persistence import Sha256Digest


PROFILE: Final = "ST0904_PUBLIC_PROJECTION_RECORDED_LOCAL_V2"
LOCAL_DISCLOSURE_TEXT: Final = "この記事にはアフィリエイト広告が含まれます。"
MAX_PUBLIC_PROJECTION_BYTES: Final = 8 * 1024 * 1024
PUBLIC_ARTICLE_FIELDS: Final = (
    "article_id",
    "publication_id",
    "publication_snapshot_id",
    "canonical_path",
    "title",
    "meta_title",
    "meta_description",
    "excerpt",
    "disclosure_text",
    "article_type",
    "language_tag",
    "structured_data",
    "freshness_status",
    "published_at",
    "updated_public_at",
    "projection_generation",
    "is_indexable",
    "blocks",
    "product_cards",
)
PUBLIC_BLOCK_FIELDS: Final = (
    "block_key",
    "block_type",
    "position",
    "heading_level",
    "heading_text",
    "rendered_html",
    "render_payload",
)
PUBLIC_ROUTE_FIELDS: Final = (
    "path",
    "route_type",
    "article_id",
    "redirect_path",
    "http_status",
    "is_indexable",
    "projection_generation",
)
PUBLIC_PROJECTION_FIELDS: Final = (
    "article",
    "projection_generation",
    "route",
    "row_counts",
)
ROW_COUNT_FIELDS: Final = (
    "public_article",
    "public_article_block",
    "public_offer",
    "public_product_card",
    "public_route",
)
_BLOCK_TYPE_MAP: Final = {
    "lead": "paragraph",
    "decision_summary": "summary",
    "intended_reader": "suitable_unsuitable",
    "methodology": "source_note",
    "selection_criteria": "selection_criteria",
    "comparison_table": "comparison_table",
    "recommendation_group": "summary",
    "caution": "warning",
    "source_summary": "source_note",
}
_PUBLIC_BLOCK_TYPES: Final = frozenset(
    {
        "heading",
        "paragraph",
        "summary",
        "selection_criteria",
        "comparison_table",
        "product_card",
        "pros_cons",
        "suitable_unsuitable",
        "warning",
        "faq_content",
        "source_note",
        "call_to_action",
    }
)
_PROHIBITED_PUBLIC_KEYS: Final = frozenset(
    {
        "access_token",
        "affiliate_rate",
        "approval_ids",
        "article_version_id",
        "commission",
        "credential",
        "epc",
        "evidence",
        "finance",
        "input_hashes",
        "methodology_ref",
        "password",
        "policy_bundle_version",
        "private_key",
        "profit",
        "quality_result_id",
        "raw_prompt",
        "raw_review",
        "recommendation_ref",
        "recommendation_refs",
        "revenue",
        "review_body",
        "rpm",
        "safe_offer_projection_version",
        "secret",
        "source_packet_version_ref",
        "source_uri",
        "token",
    }
)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,199}\Z", re.ASCII)
_SEO_FIELDS: Final = frozenset(
    {
        "article_version_id",
        "breadcrumb_refs",
        "canonical_route_ref",
        "canonical_url",
        "index_state",
        "meta_description",
        "robots",
        "seo_metadata_id",
        "sitemap_inclusion",
        "slug",
        "structured_data_manifest_ref",
        "substantive_updated_at",
        "title",
    }
)


class PublicProjectionFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    SNAPSHOT_INVALID = "SNAPSHOT_INVALID"
    SNAPSHOT_BINDING_MISMATCH = "SNAPSHOT_BINDING_MISMATCH"
    PUBLIC_ALLOWLIST_VIOLATION = "PUBLIC_ALLOWLIST_VIOLATION"
    PUBLIC_FIELD_UNAVAILABLE = "PUBLIC_FIELD_UNAVAILABLE"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class PublicProjectionFailure(RuntimeError):
    __slots__ = ("_code",)

    def __init__(self, code: PublicProjectionFailureCode) -> None:
        if type(code) is not PublicProjectionFailureCode:
            raise TypeError("invalid public projection failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> PublicProjectionFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"PublicProjectionFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("public projection failure serialization is forbidden")


def fail_public_projection(
    code: PublicProjectionFailureCode = PublicProjectionFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise PublicProjectionFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0904-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0904-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("public projection serialization is forbidden")


class ProjectionExecution(StrEnum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


class ProjectionReadiness(StrEnum):
    NOT_READY = "NOT_READY"


class ExternalGateStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"


class ProjectionCompatibility(StrEnum):
    COMMON_PUBLIC_SUBSET_LEGACY_RECONCILIATION_REQUIRED = (
        "COMMON_PUBLIC_SUBSET_LEGACY_RECONCILIATION_REQUIRED"
    )


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_public_projection()
    try:
        return Sha256Digest(value.value)
    except Exception:
        fail_public_projection()


def _digest(payload: bytes) -> Sha256Digest:
    if type(payload) is not bytes or not payload:
        fail_public_projection()
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _digest_object(value: object) -> Sha256Digest:
    return _digest(canonical_json_bytes(value))


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_public_projection()
    return value


def _idempotency(value: object) -> str:
    if type(value) is not str or _IDEMPOTENCY.fullmatch(value) is None:
        fail_public_projection()
    return value


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    result: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if type(key) is not str:
            fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
        result[key] = item
    return result


def _list(value: object) -> list[object]:
    if type(value) is not list:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_FIELD_UNAVAILABLE)
    return value


def _optional_text(value: object, *, maximum: int = 4096) -> str | None:
    if value is None:
        return None
    return _text(value, maximum=maximum)


def _validate_snapshot_result(result: object) -> PublicationSnapshotResultV2:
    if type(result) is not PublicationSnapshotResultV2:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    try:
        rebuilt = PublicationSnapshotResultV2(
            request_sha256=result.request_sha256,
            input_bundle_sha256=result.input_bundle_sha256,
            content_manifest_bytes=result.content_manifest_bytes,
            content_manifest_sha256=result.content_manifest_sha256,
            snapshot_bytes=result.snapshot_bytes,
            snapshot_sha256=result.snapshot_sha256,
            snapshot_artifact_sha256=result.snapshot_artifact_sha256,
            seo_binding_sha256=result.seo_binding_sha256,
            media_binding_sha256=result.media_binding_sha256,
            idempotency_receipt_sha256=result.idempotency_receipt_sha256,
            compatibility=result.compatibility,
            execution=result.execution,
            readiness=result.readiness,
            local_snapshot_candidate_built=result.local_snapshot_candidate_built,
            immutable=result.immutable,
            persisted=result.persisted,
            event_emitted=result.event_emitted,
            public_projection_authorized=result.public_projection_authorized,
            publication_authorized=result.publication_authorized,
            release_authorized=result.release_authorized,
            production_authorized=result.production_authorized,
            formal_tst_014_status=result.formal_tst_014_status,
            formal_tst_021_status=result.formal_tst_021_status,
            live_status=result.live_status,
            staging_status=result.staging_status,
            publication_status=result.publication_status,
            release_status=result.release_status,
            production_status=result.production_status,
        )
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    if (
        rebuilt.result_sha256 != result.result_sha256
        or rebuilt.canonical_bytes() != result.canonical_bytes()
        or rebuilt.snapshot_bytes != result.snapshot_bytes
        or result.compatibility
        is not SnapshotContractCompatibility.CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED
        or result.public_projection_authorized is not False
        or result.publication_authorized is not False
        or result.release_authorized is not False
        or result.production_authorized is not False
    ):
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    return result


@dataclass(frozen=True, slots=True, repr=False)
class PublicProjectionInputV2(_Redacted):
    snapshot_request: PublicationSnapshotBuildRequestV2
    snapshot_result: PublicationSnapshotResultV2
    source_fixture_sha256: Sha256Digest
    binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if type(self.snapshot_request) is not PublicationSnapshotBuildRequestV2:
            fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
        try:
            self.snapshot_request.require_valid()
        except Exception:
            fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
        result = _validate_snapshot_result(self.snapshot_result)
        source_sha = _sha(self.source_fixture_sha256)
        snapshot = _mapping(result.snapshot())
        if (
            result.request_sha256 != self.snapshot_request.request_sha256
            or result.input_bundle_sha256
            != self.snapshot_request.expected_input_bundle_sha256
            or snapshot.get("article_id") != str(self.snapshot_request.article_id)
            or snapshot.get("article_version_id")
            != str(self.snapshot_request.article_version_id)
            or snapshot.get("publication_id")
            != str(self.snapshot_request.publication_id)
            or snapshot.get("publication_version")
            != self.snapshot_request.publication_version
            or snapshot.get("quality_result_id")
            != str(self.snapshot_request.quality_result_id)
        ):
            fail_public_projection(
                PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH
            )
        object.__setattr__(self, "source_fixture_sha256", source_sha)
        object.__setattr__(
            self,
            "binding_sha256",
            _digest_object(
                {
                    "profile": PROFILE,
                    "snapshot_artifact_sha256": result.snapshot_artifact_sha256.value,
                    "snapshot_request_sha256": self.snapshot_request.request_sha256.value,
                    "snapshot_result_sha256": result.result_sha256.value,
                    "snapshot_sha256": result.snapshot_sha256.value,
                    "source_fixture_sha256": source_sha.value,
                }
            ),
        )

    def require_valid(self) -> None:
        rebuilt = PublicProjectionInputV2(
            snapshot_request=self.snapshot_request,
            snapshot_result=self.snapshot_result,
            source_fixture_sha256=self.source_fixture_sha256,
        )
        if rebuilt.binding_sha256 != self.binding_sha256:
            fail_public_projection(
                PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH
            )


@dataclass(frozen=True, slots=True, repr=False)
class PublicProjectionRequestV2(_Redacted):
    expected_source_binding_sha256: Sha256Digest
    idempotency_key: str
    projection_generation: int = 1
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        source = _sha(self.expected_source_binding_sha256)
        key = _idempotency(self.idempotency_key)
        if (
            type(self.projection_generation) is not int
            or self.projection_generation != 1
        ):
            fail_public_projection()
        object.__setattr__(self, "expected_source_binding_sha256", source)
        object.__setattr__(self, "idempotency_key", key)
        object.__setattr__(self, "request_sha256", _digest_object(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "expected_source_binding_sha256": self.expected_source_binding_sha256.value,
            "idempotency_key_sha256": hashlib.sha256(
                self.idempotency_key.encode("ascii")
            ).hexdigest(),
            "profile": PROFILE,
            "projection_generation": self.projection_generation,
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        value = self._payload()
        value["request_sha256"] = self.request_sha256.value
        return canonical_json_bytes(value)

    def require_valid(self) -> None:
        rebuilt = PublicProjectionRequestV2(
            expected_source_binding_sha256=self.expected_source_binding_sha256,
            idempotency_key=self.idempotency_key,
            projection_generation=self.projection_generation,
        )
        if rebuilt.request_sha256 != self.request_sha256:
            fail_public_projection(PublicProjectionFailureCode.OUTCOME_MISMATCH)


def _collect_public_text(value: object) -> tuple[str, ...]:
    fragments: list[str] = []

    def visit(current: object, parent_key: str | None = None) -> None:
        if len(fragments) > 64:
            fail_public_projection(
                PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION
            )
        if type(current) is dict:
            for key, item in cast(dict[str, object], current).items():
                if key in {"text", "condition", "label"} and type(item) is str:
                    fragments.append(_text(item, maximum=2048))
                elif key not in {
                    "block_id",
                    "claim_id",
                    "claim_ids",
                    "comparison_axis_ref",
                    "comparison_axis_refs",
                    "comparison_table_ref",
                    "disclosure_policy_version_ref",
                    "editorial_policy_route_ref",
                    "group_id",
                    "methodology_ref",
                    "product_selection_ref",
                    "product_selection_refs",
                    "rationale_claim_ids",
                    "recommendation_ref",
                    "recommendation_refs",
                    "seo_metadata_ref",
                    "source_packet_version_ref",
                    "type",
                }:
                    visit(item, key)
        elif type(current) is list:
            for item in cast(list[object], current):
                visit(item, parent_key)

    visit(value)
    return tuple(fragments)


def _public_blocks(ast: dict[str, object]) -> list[object]:
    source_blocks = _list(ast.get("blocks"))
    projected: list[object] = []
    for source in source_blocks:
        block = _mapping(source)
        source_type = block.get("type")
        if source_type == "disclosure_slot":
            continue
        if type(source_type) is not str or source_type not in _BLOCK_TYPE_MAP:
            fail_public_projection(
                PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION
            )
        public_type = _BLOCK_TYPE_MAP[source_type]
        if public_type not in _PUBLIC_BLOCK_TYPES:
            fail_public_projection(
                PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION
            )
        position = len(projected)
        projected.append(
            {
                "block_key": f"block-{position + 1:03d}",
                "block_type": public_type,
                "position": position,
                "heading_level": None,
                "heading_text": None,
                "rendered_html": None,
                "render_payload": {
                    "source_type": source_type,
                    "text": list(_collect_public_text(block)),
                },
            }
        )
    if not projected or len(projected) > 128:
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_FIELD_UNAVAILABLE)
    return projected


def _validate_current_content_ast(ast: dict[str, object]) -> None:
    try:
        model = load_content_ast(canonical_json_bytes(ast))
        round_trip = parse_canonical_object(
            dump_content_ast_json(model).encode("utf-8")
        )
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)
    if round_trip != ast:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_INVALID)


def _canonical_path(seo: dict[str, object]) -> str:
    slug = seo.get("slug")
    if type(slug) is not str or _SLUG.fullmatch(slug) is None:
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_FIELD_UNAVAILABLE)
    return f"/{slug}/"


def _ensure_public_tree(value: object) -> None:
    def visit(current: object) -> None:
        if type(current) is dict:
            for key, item in cast(dict[str, object], current).items():
                normalized = key.casefold().replace("-", "_")
                if normalized in _PROHIBITED_PUBLIC_KEYS:
                    fail_public_projection(
                        PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION
                    )
                visit(item)
        elif type(current) is list:
            for item in cast(list[object], current):
                visit(item)

    visit(value)


def _validate_public_shapes(projection: dict[str, object]) -> None:
    if frozenset(projection) != frozenset(PUBLIC_PROJECTION_FIELDS):
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION)
    article = _mapping(projection["article"])
    route = _mapping(projection["route"])
    counts = _mapping(projection["row_counts"])
    blocks = _list(article.get("blocks"))
    if (
        frozenset(article) != frozenset(PUBLIC_ARTICLE_FIELDS)
        or frozenset(route) != frozenset(PUBLIC_ROUTE_FIELDS)
        or frozenset(counts) != frozenset(ROW_COUNT_FIELDS)
        or projection["projection_generation"] != 1
        or article["projection_generation"] != 1
        or route["projection_generation"] != 1
        or article["canonical_path"] != route["path"]
        or article["article_id"] != route["article_id"]
        or article["is_indexable"] is not False
        or route["is_indexable"] is not False
        or route["route_type"] != "ARTICLE"
        or route["redirect_path"] is not None
        or route["http_status"] != 200
        or article["product_cards"] != []
        or article["structured_data"] != {}
        or article["freshness_status"] != "UNKNOWN"
        or article["disclosure_text"] != LOCAL_DISCLOSURE_TEXT
        or counts
        != {
            "public_article": 1,
            "public_article_block": len(blocks),
            "public_offer": 0,
            "public_product_card": 0,
            "public_route": 1,
        }
    ):
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION)
    try:
        for field_name in ("article_id", "publication_id", "publication_snapshot_id"):
            _uuid7(UUID(_text(article[field_name], maximum=36)))
    except Exception:
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION)
    for index, item in enumerate(blocks):
        block = _mapping(item)
        payload = _mapping(block.get("render_payload"))
        if (
            frozenset(block) != frozenset(PUBLIC_BLOCK_FIELDS)
            or block["block_key"] != f"block-{index + 1:03d}"
            or block["position"] != index
            or block["block_type"] not in _PUBLIC_BLOCK_TYPES
            or block["heading_level"] is not None
            or block["heading_text"] is not None
            or block["rendered_html"] is not None
            or frozenset(payload) != frozenset(("source_type", "text"))
            or payload["source_type"] not in _BLOCK_TYPE_MAP
            or type(payload["text"]) is not list
            or any(
                type(fragment) is not str
                for fragment in cast(list[object], payload["text"])
            )
        ):
            fail_public_projection(
                PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION
            )
    _ensure_public_tree(projection)
    canonical_payload = canonical_json_bytes(projection)
    if len(canonical_payload) > MAX_PUBLIC_PROJECTION_BYTES:
        fail_public_projection(PublicProjectionFailureCode.PUBLIC_ALLOWLIST_VIOLATION)


@dataclass(frozen=True, slots=True, repr=False)
class PublicProjectionResultV2(_Redacted):
    request_sha256: Sha256Digest
    source_binding_sha256: Sha256Digest
    snapshot_sha256: Sha256Digest
    snapshot_artifact_sha256: Sha256Digest
    projection_bytes: bytes
    projection_sha256: Sha256Digest
    execution: ProjectionExecution = ProjectionExecution.RECORDED_SYNTHETIC_ONLY
    readiness: ProjectionReadiness = ProjectionReadiness.NOT_READY
    compatibility: ProjectionCompatibility = (
        ProjectionCompatibility.COMMON_PUBLIC_SUBSET_LEGACY_RECONCILIATION_REQUIRED
    )
    process_local_projection_built: bool = True
    persisted: bool = False
    event_emitted: bool = False
    route_activated: bool = False
    public_read_served: bool = False
    public_projection_authorized: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    formal_tst_011_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_021_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    hosted_ci_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    live_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    staging_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    publication_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    release_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    production_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    result_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "request_sha256",
            "source_binding_sha256",
            "snapshot_sha256",
            "snapshot_artifact_sha256",
            "projection_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        try:
            projection = parse_canonical_object(self.projection_bytes)
        except Exception:
            fail_public_projection(PublicProjectionFailureCode.OUTCOME_MISMATCH)
        if (
            canonical_json_bytes(projection) != self.projection_bytes
            or _digest(self.projection_bytes) != self.projection_sha256
            or type(self.execution) is not ProjectionExecution
            or self.readiness is not ProjectionReadiness.NOT_READY
            or self.compatibility
            is not ProjectionCompatibility.COMMON_PUBLIC_SUBSET_LEGACY_RECONCILIATION_REQUIRED
            or self.process_local_projection_built is not True
            or any(
                flag is not False
                for flag in (
                    self.persisted,
                    self.event_emitted,
                    self.route_activated,
                    self.public_read_served,
                    self.public_projection_authorized,
                    self.publication_authorized,
                    self.release_authorized,
                    self.production_authorized,
                )
            )
            or any(
                status is not ExternalGateStatus.NOT_EXECUTED
                for status in (
                    self.formal_tst_011_status,
                    self.formal_tst_021_status,
                    self.hosted_ci_status,
                    self.live_status,
                    self.staging_status,
                    self.publication_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_public_projection(PublicProjectionFailureCode.OUTCOME_MISMATCH)
        _validate_public_shapes(projection)
        object.__setattr__(self, "result_sha256", _digest_object(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "compatibility": self.compatibility.value,
            "event_emitted": False,
            "execution": self.execution.value,
            "external_gates": {
                "formal_tst_011": self.formal_tst_011_status.value,
                "formal_tst_021": self.formal_tst_021_status.value,
                "hosted_ci": self.hosted_ci_status.value,
                "live": self.live_status.value,
                "production": self.production_status.value,
                "publication": self.publication_status.value,
                "release": self.release_status.value,
                "staging": self.staging_status.value,
            },
            "persisted": False,
            "process_local_projection_built": True,
            "production_authorized": False,
            "profile": PROFILE,
            "projection_sha256": self.projection_sha256.value,
            "public_projection_authorized": False,
            "public_read_served": False,
            "publication_authorized": False,
            "readiness": self.readiness.value,
            "release_authorized": False,
            "request_sha256": self.request_sha256.value,
            "route_activated": False,
            "snapshot_artifact_sha256": self.snapshot_artifact_sha256.value,
            "snapshot_sha256": self.snapshot_sha256.value,
            "source_binding_sha256": self.source_binding_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        value = self._payload()
        value["result_sha256"] = self.result_sha256.value
        return canonical_json_bytes(value)

    def projection(self) -> dict[str, object]:
        return parse_canonical_object(self.projection_bytes)


def build_public_projection_v2(
    *,
    request: PublicProjectionRequestV2,
    source: PublicProjectionInputV2,
) -> PublicProjectionResultV2:
    """Project the exact ST-0903 candidate into a closed local public shape."""

    if (
        type(request) is not PublicProjectionRequestV2
        or type(source) is not PublicProjectionInputV2
    ):
        fail_public_projection()
    request.require_valid()
    source.require_valid()
    if request.expected_source_binding_sha256 != source.binding_sha256:
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH)
    snapshot = _mapping(source.snapshot_result.snapshot())
    ast = _mapping(snapshot.get("renderable_content"))
    seo = _mapping(snapshot.get("seo_metadata"))
    _validate_current_content_ast(ast)
    article_id = _text(snapshot.get("article_id"), maximum=36)
    publication_id = _text(snapshot.get("publication_id"), maximum=36)
    title = _text(seo.get("title"), maximum=512)
    ast_title = _text(ast.get("title"), maximum=512)
    if (
        frozenset(seo) != _SEO_FIELDS
        or title != ast_title
        or seo.get("index_state") != "noindex"
        or seo.get("robots") != ["noindex", "nofollow"]
        or seo.get("sitemap_inclusion") is not False
        or seo.get("canonical_url") is not None
        or snapshot.get("safe_offer_projection_version") != 0
    ):
        fail_public_projection(PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH)
    blocks = _public_blocks(ast)
    path = _canonical_path(seo)
    published_at = source.snapshot_request.created_at.isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z")
    article: dict[str, object] = {
        "article_id": article_id,
        "publication_id": publication_id,
        "publication_snapshot_id": str(source.snapshot_request.snapshot_artifact_id),
        "canonical_path": path,
        "title": title,
        "meta_title": _optional_text(seo.get("title"), maximum=512),
        "meta_description": _optional_text(seo.get("meta_description"), maximum=1024),
        "excerpt": None,
        "disclosure_text": LOCAL_DISCLOSURE_TEXT,
        "article_type": _text(ast.get("article_type"), maximum=128),
        "language_tag": _text(ast.get("locale"), maximum=32),
        "structured_data": {},
        "freshness_status": "UNKNOWN",
        "published_at": published_at,
        "updated_public_at": None,
        "projection_generation": request.projection_generation,
        "is_indexable": False,
        "blocks": blocks,
        "product_cards": [],
    }
    route: dict[str, object] = {
        "path": path,
        "route_type": "ARTICLE",
        "article_id": article_id,
        "redirect_path": None,
        "http_status": 200,
        "is_indexable": False,
        "projection_generation": request.projection_generation,
    }
    projection: dict[str, object] = {
        "article": article,
        "projection_generation": request.projection_generation,
        "route": route,
        "row_counts": {
            "public_article": 1,
            "public_article_block": len(blocks),
            "public_offer": 0,
            "public_product_card": 0,
            "public_route": 1,
        },
    }
    _validate_public_shapes(projection)
    projection_bytes = canonical_json_bytes(projection)
    return PublicProjectionResultV2(
        request_sha256=request.request_sha256,
        source_binding_sha256=source.binding_sha256,
        snapshot_sha256=source.snapshot_result.snapshot_sha256,
        snapshot_artifact_sha256=(source.snapshot_result.snapshot_artifact_sha256),
        projection_bytes=projection_bytes,
        projection_sha256=_digest(projection_bytes),
    )


__all__ = (
    "ExternalGateStatus",
    "LOCAL_DISCLOSURE_TEXT",
    "MAX_PUBLIC_PROJECTION_BYTES",
    "PROFILE",
    "PUBLIC_ARTICLE_FIELDS",
    "PUBLIC_BLOCK_FIELDS",
    "PUBLIC_PROJECTION_FIELDS",
    "PUBLIC_ROUTE_FIELDS",
    "ProjectionCompatibility",
    "ProjectionExecution",
    "ProjectionReadiness",
    "PublicProjectionFailure",
    "PublicProjectionFailureCode",
    "PublicProjectionInputV2",
    "PublicProjectionRequestV2",
    "PublicProjectionResultV2",
    "ROW_COUNT_FIELDS",
    "build_public_projection_v2",
    "fail_public_projection",
)
