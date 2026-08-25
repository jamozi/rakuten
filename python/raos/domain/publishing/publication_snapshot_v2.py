"""Deterministic local-only Publication Snapshot candidate for ST-0903.

The builder consumes one exact recorded-synthetic final approval and immutable
Content AST, SEO, structured-data, and media bindings.  It deliberately builds
an in-memory *candidate*: no persistence, event, public projection, CMS action,
publication, release, staging, provider, credential, or Production authority is
present in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
from typing import Any, Final, NoReturn, SupportsIndex, cast
import unicodedata
from uuid import RFC_4122, UUID

from raos.domain.editorial.content_ast import (
    CONTENT_AST_SCHEMA_VERSION,
    dump_content_ast_json,
    load_content_ast,
)
from raos.domain.publishing.final_approval import (
    FinalApprovalRequestV2,
    FinalApprovalResultV2,
)
from raos.domain.shared.persistence import Sha256Digest


PROFILE: Final = "ST0903_PUBLICATION_SNAPSHOT_RECORDED_LOCAL_V2"
CONTENT_MANIFEST_SCHEMA_VERSION: Final = "1.0.0"
SNAPSHOT_CANONICALIZATION: Final = (
    "ST0903_CANONICAL_JSON_ASCII_SORTED_SELF_HASH_EXCLUDED_V2"
)
MAX_CANONICAL_BYTES: Final = 8 * 1024 * 1024
_MAX_JSON_NODES: Final = 100_000
_MAX_JSON_DEPTH: Final = 40
_MAX_SAFE_INTEGER: Final = (1 << 53) - 1
_REFERENCE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@-]{2,199}\Z", re.ASCII)
_IDEMPOTENCY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,199}\Z", re.ASCII)
_PROHIBITED_SNAPSHOT_KEYS: Final = frozenset(
    {
        "access_token",
        "accesstoken",
        "affiliate_rate",
        "api_key",
        "apikey",
        "auth_token",
        "authtoken",
        "commission",
        "credential",
        "epc",
        "finance",
        "password",
        "passwd",
        "personal_data",
        "private_key",
        "privatekey",
        "profit",
        "raw_content",
        "raw_prompt",
        "raw_review",
        "revenue",
        "review_body",
        "rpm",
        "secret",
        "source_body",
        "source_uri",
        "token",
    }
)
INPUT_HASH_KEYS: Final = (
    "approval_gate_bundle_sha256",
    "approval_record_sha256",
    "approval_result_sha256",
    "article_body_sha256",
    "candidate_universe_sha256",
    "canonical_ast_sha256",
    "media_asset_content_sha256",
    "media_validation_binding_sha256",
    "methodology_sha256",
    "policy_bundle_sha256",
    "publication_content_manifest_sha256",
    "quality_result_sha256",
    "seo_jsonld_sha256",
    "seo_render_result_sha256",
    "seo_structured_data_manifest_sha256",
    "seo_visible_content_sha256",
    "source_packet_content_sha256",
)
_CONTENT_MANIFEST_KEYS: Final = frozenset(
    {
        "approval_refs",
        "article_version_id",
        "content_ast_sha256",
        "content_schema_version",
        "created_at",
        "disclosure_policy_version_ref",
        "methodology_version_ref",
        "policy_bundle_version_ref",
        "publication_content_manifest_id",
        "quality_result_ref",
        "renderer_version",
        "seo_metadata_version_ref",
        "source_packet_version_ref",
    }
)
_SNAPSHOT_KEYS: Final = frozenset(
    {
        "approval_ids",
        "article_id",
        "article_version_id",
        "content_schema_version",
        "disclosure_version",
        "input_hashes",
        "policy_bundle_version",
        "product_selection_refs",
        "publication_id",
        "publication_version",
        "quality_result_id",
        "renderable_content",
        "safe_offer_projection_version",
        "seo_metadata",
        "snapshot_sha256",
    }
)


class PublicationSnapshotFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    APPROVAL_INVALID = "APPROVAL_INVALID"
    ARTICLE_BINDING_MISMATCH = "ARTICLE_BINDING_MISMATCH"
    CONTENT_AST_INVALID = "CONTENT_AST_INVALID"
    SEO_BINDING_INVALID = "SEO_BINDING_INVALID"
    MEDIA_BINDING_INVALID = "MEDIA_BINDING_INVALID"
    INPUT_HASH_MISMATCH = "INPUT_HASH_MISMATCH"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    LOCAL_ENVIRONMENT_REQUIRED = "LOCAL_ENVIRONMENT_REQUIRED"
    LOCAL_EXCHANGE_UNAVAILABLE = "LOCAL_EXCHANGE_UNAVAILABLE"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    FIXTURE_INVALID = "FIXTURE_INVALID"


class PublicationSnapshotFailure(RuntimeError):
    __slots__ = ("_code",)

    def __init__(self, code: PublicationSnapshotFailureCode) -> None:
        if type(code) is not PublicationSnapshotFailureCode:
            raise TypeError("invalid publication snapshot failure code") from None
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> PublicationSnapshotFailureCode:
        return self._code

    def __str__(self) -> str:
        return self._code.value

    def __repr__(self) -> str:
        return f"PublicationSnapshotFailure(code={self._code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication snapshot failure serialization is forbidden")


def fail_publication_snapshot(
    code: PublicationSnapshotFailureCode = (
        PublicationSnapshotFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise PublicationSnapshotFailure(code) from None


class _Redacted:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-st0903-v2>)"

    def __str__(self) -> str:
        return "<redacted-st0903-v2>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication snapshot serialization is forbidden")


class SnapshotExecution(StrEnum):
    RECORDED_SYNTHETIC_ONLY = "RECORDED_SYNTHETIC_ONLY"


class SnapshotReadiness(StrEnum):
    NOT_READY = "NOT_READY"


class ExternalGateStatus(StrEnum):
    NOT_EXECUTED = "NOT_EXECUTED"


class SnapshotContractCompatibility(StrEnum):
    CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED = (
        "CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED"
    )


class _DuplicateMember(ValueError):
    pass


class _InvalidNumber(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise _DuplicateMember
        result[key] = value
    return result


def _invalid_number(_value: str) -> NoReturn:
    raise _InvalidNumber


def _validate_json_tree(value: object) -> None:
    remaining = _MAX_JSON_NODES

    def visit(current: object, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > _MAX_JSON_DEPTH:
            fail_publication_snapshot()
        if current is None or type(current) is bool:
            return
        if type(current) is int:
            if not -_MAX_SAFE_INTEGER <= current <= _MAX_SAFE_INTEGER:
                fail_publication_snapshot()
            return
        if type(current) is str:
            text = current
            if (
                len(text) > 1_048_576
                or unicodedata.normalize("NFC", text) != text
                or any(0xD800 <= ord(character) <= 0xDFFF for character in text)
            ):
                fail_publication_snapshot()
            return
        if type(current) is list:
            sequence = cast(list[object], current)
            if len(sequence) > 4096:
                fail_publication_snapshot()
            for item in sequence:
                visit(item, depth + 1)
            return
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            if len(mapping) > 4096:
                fail_publication_snapshot()
            for key, item in mapping.items():
                if (
                    type(key) is not str
                    or not key
                    or len(key) > 200
                    or unicodedata.normalize("NFC", key) != key
                ):
                    fail_publication_snapshot()
                visit(item, depth + 1)
            return
        fail_publication_snapshot()

    visit(value, 0)


def canonical_json_bytes(value: object) -> bytes:
    """Return the closed canonical JSON encoding used by this local profile."""

    _validate_json_tree(value)
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except Exception:
        fail_publication_snapshot()
    if not payload or len(payload) > MAX_CANONICAL_BYTES:
        fail_publication_snapshot()
    return payload


def parse_canonical_object(payload: bytes) -> dict[str, object]:
    if type(payload) is not bytes or not payload or len(payload) > MAX_CANONICAL_BYTES:
        fail_publication_snapshot()
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_invalid_number,
            parse_constant=_invalid_number,
        )
    except PublicationSnapshotFailure:
        raise
    except Exception:
        fail_publication_snapshot()
    if type(value) is not dict:
        fail_publication_snapshot()
    result = cast(dict[str, object], value)
    _validate_json_tree(result)
    return result


def _digest_bytes(payload: bytes) -> Sha256Digest:
    if type(payload) is not bytes or not payload:
        fail_publication_snapshot()
    return Sha256Digest(hashlib.sha256(payload).hexdigest())


def _digest(value: object) -> Sha256Digest:
    return _digest_bytes(canonical_json_bytes(value))


def _sha(value: object) -> Sha256Digest:
    if type(value) is not Sha256Digest:
        fail_publication_snapshot()
    try:
        return Sha256Digest(value.value)
    except Exception:
        fail_publication_snapshot()


def _uuid7(value: object) -> UUID:
    if type(value) is not UUID or value.version != 7 or value.variant != RFC_4122:
        fail_publication_snapshot()
    return value


def _reference(value: object) -> str:
    if type(value) is not str or _REFERENCE.fullmatch(value) is None:
        fail_publication_snapshot()
    return value


def _idempotency_key(value: object) -> str:
    if type(value) is not str or _IDEMPOTENCY.fullmatch(value) is None:
        fail_publication_snapshot()
    return value


def _instant(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is not timezone.utc
        or value.fold
        or value.microsecond != 0
    ):
        fail_publication_snapshot()
    return value


def _instant_text(value: datetime) -> str:
    return _instant(value).isoformat(timespec="seconds").replace("+00:00", "Z")


def _mapping_without_prohibited_keys(value: object) -> None:
    def visit(current: object) -> None:
        if type(current) is dict:
            for key, item in cast(dict[str, object], current).items():
                normalized = "".join(
                    character
                    for character in unicodedata.normalize("NFKC", key).casefold()
                    if character.isalnum() or character == "_"
                )
                if normalized in _PROHIBITED_SNAPSHOT_KEYS:
                    fail_publication_snapshot()
                visit(item)
        elif type(current) is list:
            for item in cast(list[object], current):
                visit(item)

    visit(value)


def _closed_object_mapping(value: object) -> dict[str, object] | None:
    if type(value) is not dict:
        return None
    result: dict[str, object] = {}
    for key, item in cast(dict[object, object], value).items():
        if type(key) is not str:
            return None
        result[key] = item
    return result


def _erase_narrowing(value: object) -> object:
    return value


@dataclass(frozen=True, slots=True, repr=False)
class SeoSnapshotBindingV2(_Redacted):
    source_fixture_sha256: Sha256Digest
    article_version_id: UUID
    rendered_metadata_bytes: bytes
    structured_data_manifest_bytes: bytes
    jsonld_bytes: bytes
    render_result_sha256: Sha256Digest
    visible_content_sha256: Sha256Digest
    jsonld_sha256: Sha256Digest
    preview_only: bool = True
    publication_authorized: bool = False
    binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        source = _sha(self.source_fixture_sha256)
        article_version = _uuid7(self.article_version_id)
        rendered = parse_canonical_object(self.rendered_metadata_bytes)
        structured = parse_canonical_object(self.structured_data_manifest_bytes)
        rendered_article_version = rendered.get("article_version_id")
        render_digest = _sha(self.render_result_sha256)
        visible_digest = _sha(self.visible_content_sha256)
        jsonld_digest = _sha(self.jsonld_sha256)
        if (
            canonical_json_bytes(rendered) != self.rendered_metadata_bytes
            or canonical_json_bytes(structured) != self.structured_data_manifest_bytes
            or type(self.jsonld_bytes) is not bytes
            or not self.jsonld_bytes
            or len(self.jsonld_bytes) > MAX_CANONICAL_BYTES
            or _digest_bytes(self.jsonld_bytes) != jsonld_digest
            or type(rendered_article_version) is not str
            or rendered_article_version.lower() != str(article_version)
            or rendered.get("index_state") != "noindex"
            or rendered.get("robots") != ["noindex", "nofollow"]
            or rendered.get("sitemap_inclusion") is not False
            or rendered.get("canonical_url") is not None
            or structured.get("visible_content_hash") != visible_digest.value
            or structured.get("jsonld_sha256") != jsonld_digest.value
            or structured.get("validation_result") != "pass"
            or self.preview_only is not True
            or self.publication_authorized is not False
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.SEO_BINDING_INVALID
            )
        try:
            jsonld = parse_canonical_object(self.jsonld_bytes)
        except PublicationSnapshotFailure:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.SEO_BINDING_INVALID
            )
        if canonical_json_bytes(jsonld) != self.jsonld_bytes:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.SEO_BINDING_INVALID
            )
        prohibited_types = {
            "Product",
            "Offer",
            "Review",
            "AggregateRating",
            "FAQPage",
        }

        def schema_types(value: object) -> tuple[str, ...]:
            result: list[str] = []
            if type(value) is dict:
                for key, item in cast(dict[str, object], value).items():
                    if key == "@type" and type(item) is str:
                        result.append(item)
                    else:
                        result.extend(schema_types(item))
            elif type(value) is list:
                for item in cast(list[object], value):
                    result.extend(schema_types(item))
            return tuple(result)

        if prohibited_types.intersection(schema_types(jsonld)):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.SEO_BINDING_INVALID
            )
        object.__setattr__(self, "source_fixture_sha256", source)
        object.__setattr__(self, "article_version_id", article_version)
        object.__setattr__(self, "render_result_sha256", render_digest)
        object.__setattr__(self, "visible_content_sha256", visible_digest)
        object.__setattr__(self, "jsonld_sha256", jsonld_digest)
        object.__setattr__(
            self,
            "binding_sha256",
            _digest(
                {
                    "article_version_id": str(article_version),
                    "jsonld_sha256": jsonld_digest.value,
                    "preview_only": True,
                    "publication_authorized": False,
                    "render_result_sha256": render_digest.value,
                    "rendered_metadata_sha256": _digest_bytes(
                        self.rendered_metadata_bytes
                    ).value,
                    "source_fixture_sha256": source.value,
                    "structured_data_manifest_sha256": _digest_bytes(
                        self.structured_data_manifest_bytes
                    ).value,
                    "visible_content_sha256": visible_digest.value,
                }
            ),
        )

    def require_valid(self) -> None:
        rebuilt = SeoSnapshotBindingV2(
            source_fixture_sha256=self.source_fixture_sha256,
            article_version_id=self.article_version_id,
            rendered_metadata_bytes=self.rendered_metadata_bytes,
            structured_data_manifest_bytes=self.structured_data_manifest_bytes,
            jsonld_bytes=self.jsonld_bytes,
            render_result_sha256=self.render_result_sha256,
            visible_content_sha256=self.visible_content_sha256,
            jsonld_sha256=self.jsonld_sha256,
            preview_only=self.preview_only,
            publication_authorized=self.publication_authorized,
        )
        if rebuilt.binding_sha256 != self.binding_sha256:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.SEO_BINDING_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class MediaSnapshotBindingV2(_Redacted):
    article_version_id: UUID
    asset_id: UUID
    asset_content_sha256: Sha256Digest
    candidate_fingerprint: Sha256Digest
    byte_size: int
    visibility: str = "ADMIN_ONLY_REFERENCE"
    public_rendering: bool = False
    renderer_input_available: bool = False
    binding_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        article_version = _uuid7(self.article_version_id)
        asset_id = _uuid7(self.asset_id)
        content_digest = _sha(self.asset_content_sha256)
        fingerprint = _sha(self.candidate_fingerprint)
        if (
            type(self.byte_size) is not int
            or not 1 <= self.byte_size <= _MAX_SAFE_INTEGER
            or self.visibility != "ADMIN_ONLY_REFERENCE"
            or self.public_rendering is not False
            or self.renderer_input_available is not False
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.MEDIA_BINDING_INVALID
            )
        object.__setattr__(self, "article_version_id", article_version)
        object.__setattr__(self, "asset_id", asset_id)
        object.__setattr__(self, "asset_content_sha256", content_digest)
        object.__setattr__(self, "candidate_fingerprint", fingerprint)
        object.__setattr__(
            self,
            "binding_sha256",
            _digest(
                {
                    "article_version_id": str(article_version),
                    "asset_content_sha256": content_digest.value,
                    "asset_id": str(asset_id),
                    "byte_size": self.byte_size,
                    "candidate_fingerprint": fingerprint.value,
                    "public_rendering": False,
                    "renderer_input_available": False,
                    "visibility": self.visibility,
                }
            ),
        )

    def require_valid(self) -> None:
        rebuilt = MediaSnapshotBindingV2(
            article_version_id=self.article_version_id,
            asset_id=self.asset_id,
            asset_content_sha256=self.asset_content_sha256,
            candidate_fingerprint=self.candidate_fingerprint,
            byte_size=self.byte_size,
            visibility=self.visibility,
            public_rendering=self.public_rendering,
            renderer_input_available=self.renderer_input_available,
        )
        if rebuilt.binding_sha256 != self.binding_sha256:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.MEDIA_BINDING_INVALID
            )


@dataclass(frozen=True, slots=True, repr=False)
class PublicationSnapshotInputBundleV2(_Redacted):
    final_approval_request: FinalApprovalRequestV2
    final_approval_result: FinalApprovalResultV2
    content_ast_json: bytes
    source_packet_content_sha256: Sha256Digest
    candidate_universe_sha256: Sha256Digest
    methodology_sha256: Sha256Digest
    policy_bundle_sha256: Sha256Digest
    quality_result_sha256: Sha256Digest
    seo: SeoSnapshotBindingV2
    media: MediaSnapshotBindingV2
    input_bundle_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if (
            type(self.final_approval_request) is not FinalApprovalRequestV2
            or type(self.final_approval_result) is not FinalApprovalResultV2
            or type(self.seo) is not SeoSnapshotBindingV2
            or type(self.media) is not MediaSnapshotBindingV2
        ):
            fail_publication_snapshot(PublicationSnapshotFailureCode.APPROVAL_INVALID)
        try:
            self.final_approval_request.require_valid()
            self.final_approval_result.require_valid()
            self.seo.require_valid()
            self.media.require_valid()
        except Exception:
            fail_publication_snapshot(PublicationSnapshotFailureCode.APPROVAL_INVALID)
        request = self.final_approval_request
        result = self.final_approval_result
        if (
            result.request_sha256 != request.request_sha256
            or result.gate_bundle_sha256 != request.gate_bundle.gate_bundle_sha256
            or result.record.approval_id != request.approval_id
            or result.record.article_version_id != request.article_version_id
            or result.record.decision != "APPROVED"
            or result.local_final_approval_recorded is not True
            or result.real_final_approval_authorized is not False
            or result.publication_snapshot_authorized is not False
            or result.publication_authorized is not False
            or result.release_authorized is not False
            or result.production_authorized is not False
            or result.durable_transaction is not False
            or result.event_emitted is not False
        ):
            fail_publication_snapshot(PublicationSnapshotFailureCode.APPROVAL_INVALID)
        if type(self.content_ast_json) is not bytes or not self.content_ast_json:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.CONTENT_AST_INVALID
            )
        try:
            ast = load_content_ast(self.content_ast_json)
            exact_ast = dump_content_ast_json(ast).encode("utf-8")
        except Exception:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.CONTENT_AST_INVALID
            )
        if (
            exact_ast != self.content_ast_json
            or _digest_bytes(exact_ast) != request.canonical_ast_sha256
            or request.article_body_sha256 != request.canonical_ast_sha256
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.CONTENT_AST_INVALID
            )
        try:
            ast_document = parse_canonical_object(exact_ast)
            article_id = UUID(cast(str, ast_document["article_id"]))
            article_version_id = UUID(cast(str, ast_document["article_version_id"]))
        except Exception:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.ARTICLE_BINDING_MISMATCH
            )
        if (
            article_version_id != request.article_version_id.value
            or self.seo.article_version_id != request.article_version_id.value
            or self.media.article_version_id != request.article_version_id.value
            or self.seo.visible_content_sha256 != request.canonical_ast_sha256
            or request.policy_report.article_id is None
            or article_id != request.policy_report.article_id.value
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.ARTICLE_BINDING_MISMATCH
            )
        source_packet = _sha(self.source_packet_content_sha256)
        universe = _sha(self.candidate_universe_sha256)
        methodology = _sha(self.methodology_sha256)
        policy = _sha(self.policy_bundle_sha256)
        quality = _sha(self.quality_result_sha256)
        report = request.policy_report
        if (
            report.source_packet_content_sha256 != source_packet
            or report.candidate_universe_sha256 != universe
            or report.methodology_sha256 != methodology
            or report.report_sha256 != quality
        ):
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH
            )
        object.__setattr__(self, "source_packet_content_sha256", source_packet)
        object.__setattr__(self, "candidate_universe_sha256", universe)
        object.__setattr__(self, "methodology_sha256", methodology)
        object.__setattr__(self, "policy_bundle_sha256", policy)
        object.__setattr__(self, "quality_result_sha256", quality)
        object.__setattr__(
            self,
            "input_bundle_sha256",
            _digest(
                {
                    "approval_gate_bundle_sha256": result.gate_bundle_sha256.value,
                    "approval_record_sha256": result.record.record_sha256.value,
                    "approval_result_sha256": result.result_sha256.value,
                    "article_body_sha256": request.article_body_sha256.value,
                    "candidate_universe_sha256": universe.value,
                    "canonical_ast_sha256": request.canonical_ast_sha256.value,
                    "media_binding_sha256": self.media.binding_sha256.value,
                    "methodology_sha256": methodology.value,
                    "policy_bundle_sha256": policy.value,
                    "quality_result_sha256": quality.value,
                    "seo_binding_sha256": self.seo.binding_sha256.value,
                    "source_packet_content_sha256": source_packet.value,
                }
            ),
        )

    def require_valid(self) -> None:
        rebuilt = PublicationSnapshotInputBundleV2(
            final_approval_request=self.final_approval_request,
            final_approval_result=self.final_approval_result,
            content_ast_json=self.content_ast_json,
            source_packet_content_sha256=self.source_packet_content_sha256,
            candidate_universe_sha256=self.candidate_universe_sha256,
            methodology_sha256=self.methodology_sha256,
            policy_bundle_sha256=self.policy_bundle_sha256,
            quality_result_sha256=self.quality_result_sha256,
            seo=self.seo,
            media=self.media,
        )
        if rebuilt.input_bundle_sha256 != self.input_bundle_sha256:
            fail_publication_snapshot(
                PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH
            )


@dataclass(frozen=True, slots=True, repr=False)
class PublicationSnapshotBuildRequestV2(_Redacted):
    publication_candidate_id: UUID
    publication_content_manifest_id: UUID
    publication_id: UUID
    snapshot_artifact_id: UUID
    publication_version: int
    article_id: UUID
    article_version_id: UUID
    quality_result_id: UUID
    created_at: datetime
    methodology_version_ref: str
    policy_bundle_version_ref: str
    disclosure_policy_version_ref: str
    renderer_version: str
    expected_input_bundle_sha256: Sha256Digest
    idempotency_key: str
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "publication_candidate_id",
            "publication_content_manifest_id",
            "publication_id",
            "snapshot_artifact_id",
            "article_id",
            "article_version_id",
            "quality_result_id",
        ):
            object.__setattr__(self, name, _uuid7(getattr(self, name)))
        if type(self.publication_version) is not int or self.publication_version != 1:
            fail_publication_snapshot()
        object.__setattr__(self, "created_at", _instant(self.created_at))
        for name in (
            "methodology_version_ref",
            "policy_bundle_version_ref",
            "disclosure_policy_version_ref",
            "renderer_version",
        ):
            object.__setattr__(self, name, _reference(getattr(self, name)))
        expected = _sha(self.expected_input_bundle_sha256)
        object.__setattr__(self, "expected_input_bundle_sha256", expected)
        object.__setattr__(
            self, "idempotency_key", _idempotency_key(self.idempotency_key)
        )
        object.__setattr__(self, "request_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "article_id": str(self.article_id),
            "article_version_id": str(self.article_version_id),
            "created_at": _instant_text(self.created_at),
            "disclosure_policy_version_ref": self.disclosure_policy_version_ref,
            "expected_input_bundle_sha256": self.expected_input_bundle_sha256.value,
            "idempotency_key_sha256": _digest_bytes(
                self.idempotency_key.encode("ascii")
            ).value,
            "methodology_version_ref": self.methodology_version_ref,
            "policy_bundle_version_ref": self.policy_bundle_version_ref,
            "profile": PROFILE,
            "publication_candidate_id": str(self.publication_candidate_id),
            "publication_content_manifest_id": str(
                self.publication_content_manifest_id
            ),
            "publication_id": str(self.publication_id),
            "publication_version": self.publication_version,
            "quality_result_id": str(self.quality_result_id),
            "renderer_version": self.renderer_version,
            "snapshot_artifact_id": str(self.snapshot_artifact_id),
        }

    def canonical_bytes(self) -> bytes:
        self.require_valid()
        payload = self._payload()
        payload["request_sha256"] = self.request_sha256.value
        return canonical_json_bytes(payload)

    def require_valid(self) -> None:
        rebuilt = PublicationSnapshotBuildRequestV2(
            publication_candidate_id=self.publication_candidate_id,
            publication_content_manifest_id=self.publication_content_manifest_id,
            publication_id=self.publication_id,
            snapshot_artifact_id=self.snapshot_artifact_id,
            publication_version=self.publication_version,
            article_id=self.article_id,
            article_version_id=self.article_version_id,
            quality_result_id=self.quality_result_id,
            created_at=self.created_at,
            methodology_version_ref=self.methodology_version_ref,
            policy_bundle_version_ref=self.policy_bundle_version_ref,
            disclosure_policy_version_ref=self.disclosure_policy_version_ref,
            renderer_version=self.renderer_version,
            expected_input_bundle_sha256=self.expected_input_bundle_sha256,
            idempotency_key=self.idempotency_key,
        )
        if rebuilt.request_sha256 != self.request_sha256:
            fail_publication_snapshot(PublicationSnapshotFailureCode.OUTCOME_MISMATCH)


@dataclass(frozen=True, slots=True, repr=False)
class PublicationSnapshotResultV2(_Redacted):
    request_sha256: Sha256Digest
    input_bundle_sha256: Sha256Digest
    content_manifest_bytes: bytes
    content_manifest_sha256: Sha256Digest
    snapshot_bytes: bytes
    snapshot_sha256: Sha256Digest
    snapshot_artifact_sha256: Sha256Digest
    seo_binding_sha256: Sha256Digest
    media_binding_sha256: Sha256Digest
    idempotency_receipt_sha256: Sha256Digest
    compatibility: SnapshotContractCompatibility = SnapshotContractCompatibility.CONTENT_AST_V1_BOUND_LEGACY_SCHEMA_RECONCILIATION_REQUIRED
    execution: SnapshotExecution = SnapshotExecution.RECORDED_SYNTHETIC_ONLY
    readiness: SnapshotReadiness = SnapshotReadiness.NOT_READY
    local_snapshot_candidate_built: bool = True
    immutable: bool = True
    persisted: bool = False
    event_emitted: bool = False
    public_projection_authorized: bool = False
    publication_authorized: bool = False
    release_authorized: bool = False
    production_authorized: bool = False
    formal_tst_014_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    formal_tst_021_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    live_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    staging_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    publication_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    release_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    production_status: ExternalGateStatus = ExternalGateStatus.NOT_EXECUTED
    result_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        for name in (
            "request_sha256",
            "input_bundle_sha256",
            "content_manifest_sha256",
            "snapshot_sha256",
            "snapshot_artifact_sha256",
            "seo_binding_sha256",
            "media_binding_sha256",
            "idempotency_receipt_sha256",
        ):
            object.__setattr__(self, name, _sha(getattr(self, name)))
        manifest = parse_canonical_object(self.content_manifest_bytes)
        snapshot = parse_canonical_object(self.snapshot_bytes)
        input_hashes = snapshot.get("input_hashes")
        typed_input_hashes = _closed_object_mapping(_erase_narrowing(input_hashes))
        snapshot_without_digest = dict(snapshot)
        declared_snapshot_digest = snapshot_without_digest.pop("snapshot_sha256", None)
        if (
            _digest_bytes(self.content_manifest_bytes) != self.content_manifest_sha256
            or _digest(cast(object, snapshot_without_digest)) != self.snapshot_sha256
            or declared_snapshot_digest != self.snapshot_sha256.value
            or _digest_bytes(self.snapshot_bytes) != self.snapshot_artifact_sha256
            or frozenset(manifest) != _CONTENT_MANIFEST_KEYS
            or frozenset(snapshot) != _SNAPSHOT_KEYS
            or typed_input_hashes is None
            or tuple(sorted(typed_input_hashes)) != INPUT_HASH_KEYS
            or typed_input_hashes.get("publication_content_manifest_sha256")
            != self.content_manifest_sha256.value
            or manifest.get("content_schema_version") != CONTENT_MANIFEST_SCHEMA_VERSION
            or snapshot.get("content_schema_version") != CONTENT_AST_SCHEMA_VERSION
            or manifest.get("article_version_id") != snapshot.get("article_version_id")
            or manifest.get("content_ast_sha256")
            != typed_input_hashes.get("canonical_ast_sha256")
            or manifest.get("approval_refs") != snapshot.get("approval_ids")
            or manifest.get("quality_result_ref") != snapshot.get("quality_result_id")
            or manifest.get("policy_bundle_version_ref")
            != snapshot.get("policy_bundle_version")
            or manifest.get("disclosure_policy_version_ref")
            != snapshot.get("disclosure_version")
            or type(self.compatibility) is not SnapshotContractCompatibility
            or self.execution is not SnapshotExecution.RECORDED_SYNTHETIC_ONLY
            or self.readiness is not SnapshotReadiness.NOT_READY
            or self.local_snapshot_candidate_built is not True
            or self.immutable is not True
            or self.persisted is not False
            or self.event_emitted is not False
            or self.public_projection_authorized is not False
            or self.publication_authorized is not False
            or self.release_authorized is not False
            or self.production_authorized is not False
            or any(
                status is not ExternalGateStatus.NOT_EXECUTED
                for status in (
                    self.formal_tst_014_status,
                    self.formal_tst_021_status,
                    self.live_status,
                    self.staging_status,
                    self.publication_status,
                    self.release_status,
                    self.production_status,
                )
            )
        ):
            fail_publication_snapshot(PublicationSnapshotFailureCode.OUTCOME_MISMATCH)
        _mapping_without_prohibited_keys(manifest)
        _mapping_without_prohibited_keys(snapshot)
        object.__setattr__(self, "result_sha256", _digest(self._payload()))

    def _payload(self) -> dict[str, object]:
        return {
            "compatibility": self.compatibility.value,
            "content_manifest_sha256": self.content_manifest_sha256.value,
            "event_emitted": False,
            "execution": self.execution.value,
            "external_gates": {
                "formal_tst_014": self.formal_tst_014_status.value,
                "formal_tst_021": self.formal_tst_021_status.value,
                "live": self.live_status.value,
                "production": self.production_status.value,
                "publication": self.publication_status.value,
                "release": self.release_status.value,
                "staging": self.staging_status.value,
            },
            "idempotency_receipt_sha256": self.idempotency_receipt_sha256.value,
            "immutable": True,
            "input_bundle_sha256": self.input_bundle_sha256.value,
            "local_snapshot_candidate_built": True,
            "media_binding_sha256": self.media_binding_sha256.value,
            "persisted": False,
            "production_authorized": False,
            "profile": PROFILE,
            "public_projection_authorized": False,
            "publication_authorized": False,
            "readiness": self.readiness.value,
            "release_authorized": False,
            "request_sha256": self.request_sha256.value,
            "seo_binding_sha256": self.seo_binding_sha256.value,
            "snapshot_artifact_sha256": self.snapshot_artifact_sha256.value,
            "snapshot_sha256": self.snapshot_sha256.value,
        }

    def canonical_bytes(self) -> bytes:
        payload = self._payload()
        payload["result_sha256"] = self.result_sha256.value
        return canonical_json_bytes(payload)

    def content_manifest(self) -> dict[str, object]:
        return parse_canonical_object(self.content_manifest_bytes)

    def snapshot(self) -> dict[str, object]:
        return parse_canonical_object(self.snapshot_bytes)


def _content_manifest(
    request: PublicationSnapshotBuildRequestV2,
    bundle: PublicationSnapshotInputBundleV2,
) -> bytes:
    approval = bundle.final_approval_result.record.approval_id.value
    source_packet = bundle.final_approval_request.policy_report.source_packet_version_id
    if source_packet is None:
        fail_publication_snapshot(PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH)
    seo_metadata = parse_canonical_object(bundle.seo.rendered_metadata_bytes)
    seo_ref = seo_metadata.get("seo_metadata_id")
    if type(seo_ref) is not str:
        fail_publication_snapshot(PublicationSnapshotFailureCode.SEO_BINDING_INVALID)
    return canonical_json_bytes(
        {
            "approval_refs": [str(approval)],
            "article_version_id": str(request.article_version_id),
            "content_ast_sha256": (
                bundle.final_approval_request.canonical_ast_sha256.value
            ),
            "content_schema_version": CONTENT_MANIFEST_SCHEMA_VERSION,
            "created_at": _instant_text(request.created_at),
            "disclosure_policy_version_ref": request.disclosure_policy_version_ref,
            "methodology_version_ref": request.methodology_version_ref,
            "policy_bundle_version_ref": request.policy_bundle_version_ref,
            "publication_content_manifest_id": str(
                request.publication_content_manifest_id
            ),
            "quality_result_ref": str(request.quality_result_id),
            "renderer_version": request.renderer_version,
            "seo_metadata_version_ref": seo_ref,
            "source_packet_version_ref": source_packet,
        }
    )


def _product_selection_refs(value: object) -> tuple[str, ...]:
    collected: set[str] = set()

    def visit(current: object) -> None:
        if type(current) is dict:
            for key, item in cast(dict[str, object], current).items():
                child: object = item
                if key == "product_selection_ref":
                    collected.add(_reference(item))
                elif key == "product_selection_refs":
                    if type(item) is not list:
                        fail_publication_snapshot(
                            PublicationSnapshotFailureCode.CONTENT_AST_INVALID
                        )
                    for reference in cast(list[object], item):
                        collected.add(_reference(reference))
                visit(child)
        elif type(current) is list:
            for item in cast(list[object], current):
                visit(item)

    visit(value)
    return tuple(sorted(collected))


def build_publication_snapshot_v2(
    *,
    request: PublicationSnapshotBuildRequestV2,
    bundle: PublicationSnapshotInputBundleV2,
) -> PublicationSnapshotResultV2:
    """Build one deterministic immutable local candidate with no side effect."""

    if (
        type(request) is not PublicationSnapshotBuildRequestV2
        or type(bundle) is not PublicationSnapshotInputBundleV2
    ):
        fail_publication_snapshot()
    request.require_valid()
    bundle.require_valid()
    approval_request = bundle.final_approval_request
    approval_result = bundle.final_approval_result
    if (
        request.expected_input_bundle_sha256 != bundle.input_bundle_sha256
        or request.article_version_id != approval_request.article_version_id.value
        or approval_request.policy_report.article_id is None
        or request.article_id != approval_request.policy_report.article_id.value
        or request.created_at < approval_result.record.approved_at.value
        or (
            request.created_at - approval_result.record.approved_at.value
        ).total_seconds()
        > 86_400
    ):
        fail_publication_snapshot(
            PublicationSnapshotFailureCode.ARTICLE_BINDING_MISMATCH
        )

    manifest_bytes = _content_manifest(request, bundle)
    manifest_sha = _digest_bytes(manifest_bytes)
    ast_document = parse_canonical_object(bundle.content_ast_json)
    seo_metadata = parse_canonical_object(bundle.seo.rendered_metadata_bytes)
    input_hash_values = {
        "approval_gate_bundle_sha256": approval_result.gate_bundle_sha256.value,
        "approval_record_sha256": approval_result.record.record_sha256.value,
        "approval_result_sha256": approval_result.result_sha256.value,
        "article_body_sha256": approval_request.article_body_sha256.value,
        "candidate_universe_sha256": bundle.candidate_universe_sha256.value,
        "canonical_ast_sha256": approval_request.canonical_ast_sha256.value,
        "media_asset_content_sha256": bundle.media.asset_content_sha256.value,
        "media_validation_binding_sha256": bundle.media.binding_sha256.value,
        "methodology_sha256": bundle.methodology_sha256.value,
        "policy_bundle_sha256": bundle.policy_bundle_sha256.value,
        "publication_content_manifest_sha256": manifest_sha.value,
        "quality_result_sha256": bundle.quality_result_sha256.value,
        "seo_jsonld_sha256": bundle.seo.jsonld_sha256.value,
        "seo_render_result_sha256": bundle.seo.render_result_sha256.value,
        "seo_structured_data_manifest_sha256": _digest_bytes(
            bundle.seo.structured_data_manifest_bytes
        ).value,
        "seo_visible_content_sha256": bundle.seo.visible_content_sha256.value,
        "source_packet_content_sha256": bundle.source_packet_content_sha256.value,
    }
    if tuple(sorted(input_hash_values)) != INPUT_HASH_KEYS:
        fail_publication_snapshot(PublicationSnapshotFailureCode.INPUT_HASH_MISMATCH)
    snapshot_without_digest: dict[str, object] = {
        "approval_ids": [str(approval_result.record.approval_id.value)],
        "article_id": str(request.article_id),
        "article_version_id": str(request.article_version_id),
        "content_schema_version": CONTENT_AST_SCHEMA_VERSION,
        "disclosure_version": request.disclosure_policy_version_ref,
        "input_hashes": input_hash_values,
        "policy_bundle_version": request.policy_bundle_version_ref,
        "product_selection_refs": list(_product_selection_refs(ast_document)),
        "publication_id": str(request.publication_id),
        "publication_version": request.publication_version,
        "quality_result_id": str(request.quality_result_id),
        "renderable_content": ast_document,
        "safe_offer_projection_version": 0,
        "seo_metadata": seo_metadata,
    }
    snapshot_sha = _digest(snapshot_without_digest)
    snapshot_document = dict(snapshot_without_digest)
    snapshot_document["snapshot_sha256"] = snapshot_sha.value
    snapshot_bytes = canonical_json_bytes(snapshot_document)
    artifact_sha = _digest_bytes(snapshot_bytes)
    receipt = _digest(
        {
            "idempotency_key_sha256": _digest_bytes(
                request.idempotency_key.encode("ascii")
            ).value,
            "request_sha256": request.request_sha256.value,
            "snapshot_artifact_sha256": artifact_sha.value,
        }
    )
    return PublicationSnapshotResultV2(
        request_sha256=request.request_sha256,
        input_bundle_sha256=bundle.input_bundle_sha256,
        content_manifest_bytes=manifest_bytes,
        content_manifest_sha256=manifest_sha,
        snapshot_bytes=snapshot_bytes,
        snapshot_sha256=snapshot_sha,
        snapshot_artifact_sha256=artifact_sha,
        seo_binding_sha256=bundle.seo.binding_sha256,
        media_binding_sha256=bundle.media.binding_sha256,
        idempotency_receipt_sha256=receipt,
    )


__all__ = (
    "CONTENT_MANIFEST_SCHEMA_VERSION",
    "ExternalGateStatus",
    "INPUT_HASH_KEYS",
    "MAX_CANONICAL_BYTES",
    "MediaSnapshotBindingV2",
    "PROFILE",
    "PublicationSnapshotBuildRequestV2",
    "PublicationSnapshotFailure",
    "PublicationSnapshotFailureCode",
    "PublicationSnapshotInputBundleV2",
    "PublicationSnapshotResultV2",
    "SNAPSHOT_CANONICALIZATION",
    "SeoSnapshotBindingV2",
    "SnapshotContractCompatibility",
    "SnapshotExecution",
    "SnapshotReadiness",
    "build_publication_snapshot_v2",
    "canonical_json_bytes",
    "fail_publication_snapshot",
    "parse_canonical_object",
)
