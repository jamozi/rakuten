"""Deterministic preparation for the ST-1704 self-hosted editorial pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, NoReturn, cast, final
from urllib.parse import urlsplit

from raos.adapters.self_hosted_editorial_pilot_json import (
    read_official_source_capture_evidence,
    read_rakuten_product_evidence,
)
from raos.domain.editorial.content_ast import (
    ContentAstContractError,
    ContentAstValidationError,
    load_content_ast,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PILOT_ARTICLE_IDENTITIES,
    PILOT_AUTHOR_NAME,
    PILOT_CTA_LABEL,
    PILOT_ORIGIN,
    PILOT_RAKUTEN_CREDIT_LABEL,
    PILOT_RAKUTEN_CREDIT_URL,
    OfficialSourceCaptureEvidence,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    RakutenProductEvidence,
    ReviewDraftRequest,
    article_identity,
    bytes_sha256,
    canonical_json_bytes,
    canonical_sha256,
    fail_editorial_pilot,
    require_sha256,
)


SLICE_RELATIVE_PATH: Final = Path("changes/st-1704/self-hosted-editorial-pilot-v1")
ARTICLE_COLLECTION_RELATIVE_PATH: Final = (
    SLICE_RELATIVE_PATH / "content/articles.v1.json"
)
SOURCE_REGISTRY_RELATIVE_PATH: Final = (
    SLICE_RELATIVE_PATH / "sources/source-registry.v1.json"
)
MEDIA_REGISTRY_RELATIVE_PATH: Final = (
    SLICE_RELATIVE_PATH / "media/product-media-registry.v1.json"
)

_MAX_TRACKED_BYTES: Final = 4_000_000
_ARTICLE_SCHEMA: Final = "SELF_HOSTED_EDITORIAL_ARTICLE_COLLECTION_V1"
_SOURCE_SCHEMA: Final = "SELF_HOSTED_EDITORIAL_SOURCE_REGISTRY_V1"
_MEDIA_SCHEMA: Final = "SELF_HOSTED_EDITORIAL_PRODUCT_MEDIA_REGISTRY_V1"
_RENDERER_SCHEMA: Final = "RAOS_ST1704_DETERMINISTIC_HTML_RENDERER_V1"
_ARTICLE_IDS: Final = tuple(x.article_id for x in PILOT_ARTICLE_IDENTITIES)
_SOURCE_HOSTS: Final = frozenset(
    {
        "affiliate.rakuten.co.jp",
        "developers.google.com",
        "item.rakuten.co.jp",
        "jp.ecoflow.com",
        "panasonic.jp",
        "store.ace.jp",
        "store.irobot-jp.com",
        "www.ana.co.jp",
        "www.ankerjapan.com",
        "www.bluetti.jp",
        "www.caa.go.jp",
        "www.jackery.jp",
        "www.siroca.co.jp",
        "www.switchbot.jp",
        "www.thanko.jp",
    }
)
_ARTICLE_KEYS: Final = {
    "article_id",
    "article_type_code",
    "canonical_url",
    "category",
    "content_ast",
    "freshness",
    "intent_cluster",
    "publication_authority",
    "readiness",
    "render_model",
    "seo",
    "slot",
    "slug",
    "source_packet_ref",
    "title",
}
_RENDER_KEYS: Final = {
    "comparison_axes",
    "comparison_tables",
    "cta_policy",
    "difference_matrices",
    "disclosure",
    "internal_link_policy",
    "primary_source_refs",
    "product_cards",
    "recommendations",
}
_FINAL_SOURCE_STATUS: Final = "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
_FINAL_SOURCE_APPROVAL: Final = "READY_FOR_HUMAN_PUBLICATION_REVIEW"
ARTICLE_FACT_MAX_AGE_DAYS: Final = 14
RAKUTEN_EVIDENCE_MAX_AGE: Final = timedelta(hours=24)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fail(
    code: EditorialPilotFailureCode = EditorialPilotFailureCode.PACKET_INVALID,
) -> NoReturn:
    fail_editorial_pilot(code)


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail()
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail()


def _read_fixed_json(repository_root: Path, relative: Path) -> object:
    if (
        not repository_root.is_absolute()
        or relative.is_absolute()
        or ".." in relative.parts
    ):
        _fail()
    path = repository_root / relative
    descriptor = -1
    try:
        before_path = path.lstat()
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before_path.st_mode)
            or stat.S_ISLNK(before_path.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before_path.st_dev != before.st_dev
            or before_path.st_ino != before.st_ino
            or not 1 <= before.st_size <= _MAX_TRACKED_BYTES
        ):
            _fail()
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail()
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail()
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail()
        raw = b"".join(chunks)
    except EditorialPilotFailure:
        raise
    except OSError:
        _fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except EditorialPilotFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail()


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail()
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail()
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 20_000) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
    ):
        _fail()
    return value


def _exact(value: Mapping[str, object], keys: set[str]) -> None:
    if set(value) != keys:
        _fail()


def _index(
    values: object,
    *,
    key: str,
    exact_keys: set[str],
) -> dict[str, Mapping[str, object]]:
    indexed: dict[str, Mapping[str, object]] = {}
    for raw in _list(values):
        item = _mapping(raw)
        _exact(item, exact_keys)
        identifier = _text(item[key], maximum=300)
        if identifier in indexed:
            _fail()
        indexed[identifier] = item
    return indexed


def _source_url(value: object) -> str:
    raw = _text(value, maximum=4096)
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in _SOURCE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return raw


def _date(value: object) -> str:
    raw = _text(value, maximum=10)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if parsed.isoformat() != raw:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return raw


def _clock_value(clock: Callable[[], datetime]) -> datetime:
    try:
        observed = clock()
    except BaseException:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
    if type(observed) is not datetime or observed.tzinfo is None:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
    try:
        offset = observed.utcoffset()
        normalized = observed.astimezone(timezone.utc)
    except OverflowError, ValueError:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
    if offset is None or offset != timedelta(0):
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
    return normalized


def _require_observed_date_not_future(value: object, *, now: datetime) -> None:
    observed = date.fromisoformat(_date(value))
    age = (now.date() - observed).days
    if age < 0:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)


def _require_fresh_rakuten_timestamp(value: str, *, now: datetime) -> None:
    try:
        observed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except OverflowError, ValueError:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
    age = now - observed
    if age < timedelta(0) or age > RAKUTEN_EVIDENCE_MAX_AGE:
        _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)


def _source_capture_hash(
    source: Mapping[str, object], claims: list[Mapping[str, object]]
) -> str:
    material = {
        "authority": source["authority"],
        "claims": [
            {
                "claim_id": claim["claim_id"],
                "classification": claim["classification"],
                "statement": claim["statement"],
                "status": claim["status"],
            }
            for claim in sorted(claims, key=lambda value: cast(str, value["claim_id"]))
        ],
        "retrieved_on": source["retrieved_on"],
        "schema": "STRUCTURED_SOURCE_FACT_PACKET_V1",
        "source_ref": source["source_ref"],
        "source_type": source["source_type"],
        "title": source["title"],
        "url": source["url"],
    }
    return canonical_sha256(material)


def _source_packet_hash(packet: Mapping[str, object]) -> str:
    return canonical_sha256(
        {
            "article_id": packet["article_id"],
            "claims": packet["claims"],
            "draft_claim_coverage": packet["draft_claim_coverage"],
            "schema": "STRUCTURED_ARTICLE_SOURCE_PACKET_V1",
            "source_packet_ref": packet["source_packet_ref"],
            "source_refs": packet["source_refs"],
        }
    )


def _validate_sources(
    document: object,
) -> tuple[
    Mapping[str, object],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
]:
    registry = _mapping(document)
    _exact(
        registry,
        {
            "affiliate_resources",
            "generated_on",
            "policy_sources",
            "publication_authority",
            "schema",
            "slice_id",
            "source_packets",
            "source_policy",
            "sources",
            "story_id",
            "target_origin",
        },
    )
    if (
        registry["schema"] != _SOURCE_SCHEMA
        or registry["story_id"] != "ST-1704"
        or registry["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or registry["target_origin"] != PILOT_ORIGIN
        or registry["publication_authority"] != "NONE"
    ):
        _fail()
    policy = _mapping(registry["source_policy"])
    _exact(
        policy,
        {
            "allowed_authority",
            "competitor_sources_as_evidence",
            "first_hand_experience_claims",
            "immutable_capture_hash_algorithm",
            "immutable_capture_hash_material",
            "immutable_capture_required_for_publication",
            "immutable_capture_schema",
            "missing_fact_behavior",
            "review_body_as_evidence",
            "source_packet_schema",
        },
    )
    if (
        policy.get("allowed_authority") != "OFFICIAL_PRIMARY_SOURCE_ONLY"
        or policy.get("competitor_sources_as_evidence") is not False
        or policy.get("review_body_as_evidence") is not False
        or policy.get("first_hand_experience_claims") is not False
        or policy.get("immutable_capture_required_for_publication") is not True
        or policy.get("immutable_capture_schema") != "STRUCTURED_SOURCE_FACT_PACKET_V1"
        or policy.get("immutable_capture_hash_algorithm")
        != "SHA256_CANONICAL_UTF8_JSON_V1"
        or policy.get("source_packet_schema") != "STRUCTURED_ARTICLE_SOURCE_PACKET_V1"
        or policy.get("missing_fact_behavior") != "OMIT_OR_MARK_UNKNOWN"
    ):
        _fail()
    sources = _index(
        registry["sources"],
        key="source_ref",
        exact_keys={
            "authority",
            "capture_status",
            "immutable_capture_sha256",
            "retrieved_on",
            "review_body_excluded_from_claim_evidence",
            "source_ref",
            "source_type",
            "title",
            "url",
        },
    )
    policy_sources = _index(
        registry["policy_sources"],
        key="source_ref",
        exact_keys={
            "authority",
            "capture_status",
            "immutable_capture_sha256",
            "retrieved_on",
            "review_body_excluded_from_claim_evidence",
            "source_ref",
            "source_type",
            "title",
            "url",
        },
    )
    if len(sources) != 19 or len(policy_sources) != 3:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    packets = _index(
        registry["source_packets"],
        key="source_packet_ref",
        exact_keys={
            "approval_status",
            "article_id",
            "capture_status",
            "claims",
            "draft_claim_coverage",
            "fact_packet_sha256",
            "source_packet_ref",
            "source_refs",
        },
    )
    affiliates = _index(
        registry["affiliate_resources"],
        key="affiliate_ref",
        exact_keys={
            "affiliate_ref",
            "cta_copy",
            "destination_policy",
            "destination_url",
            "evidence",
            "product_id",
            "product_name",
            "publication_blocker",
            "required_rel",
            "status",
        },
    )
    if len(affiliates) != 18 or len(
        {affiliate["product_id"] for affiliate in affiliates.values()}
    ) != len(affiliates):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for affiliate in affiliates.values():
        if (
            affiliate["destination_policy"] != "DIRECT_RAKUTEN_AFFILIATE_URL"
            or affiliate["required_rel"] != "sponsored nofollow"
            or affiliate["cta_copy"] != PILOT_CTA_LABEL
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        status = affiliate["status"]
        if status == "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE":
            if (
                affiliate["destination_url"] is not None
                or affiliate["evidence"] is not None
                or affiliate["publication_blocker"] != "PENDING_AFFILIATE_EVIDENCE"
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        elif status == "FINAL_OFFICIAL_RAKUTEN_LINK":
            evidence = _mapping(affiliate["evidence"])
            _exact(
                evidence,
                {
                    "api",
                    "api_version",
                    "destination_attestation_sha256",
                    "endpoint_id",
                    "evidence_authority",
                    "request_fingerprint",
                    "response_sha256",
                    "result_sha256",
                    "retrieved_at",
                },
            )
            for key in (
                "destination_attestation_sha256",
                "request_fingerprint",
                "response_sha256",
                "result_sha256",
            ):
                require_sha256(evidence[key])
            if (
                type(affiliate["destination_url"]) is not str
                or affiliate["publication_blocker"] is not None
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        else:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    all_claims: dict[str, Mapping[str, object]] = {}
    for packet in packets.values():
        if (
            packet["approval_status"] != _FINAL_SOURCE_APPROVAL
            or packet["capture_status"] != _FINAL_SOURCE_STATUS
            or require_sha256(packet["fact_packet_sha256"])
            != _source_packet_hash(packet)
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
        packet_refs = [
            _text(value, maximum=300) for value in _list(packet["source_refs"])
        ]
        if len(packet_refs) != len(set(packet_refs)) or any(
            source_ref not in sources for source_ref in packet_refs
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        packet_claims = _list(packet["claims"])
        verifiable_count = 0
        for raw_claim in packet_claims:
            claim = _mapping(raw_claim)
            _exact(
                claim,
                {
                    "claim_id",
                    "classification",
                    "evidence_refs",
                    "statement",
                    "status",
                },
            )
            claim_id = _text(claim["claim_id"], maximum=300)
            if claim_id in all_claims:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            evidence_refs = [
                _text(value, maximum=300) for value in _list(claim["evidence_refs"])
            ]
            if not evidence_refs or any(
                value not in packet_refs for value in evidence_refs
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            classification = claim["classification"]
            status = claim["status"]
            if classification == "MAJOR_VERIFIABLE":
                verifiable_count += 1
                if status not in {
                    "BOUND_TO_OFFICIAL_SOURCE",
                    "BOUND_WITH_EXPLICIT_SOURCE_CONFLICT",
                }:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            elif (
                classification != "EDITORIAL_INFERENCE"
                or status != "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            all_claims[claim_id] = claim
        coverage = _mapping(packet["draft_claim_coverage"])
        _exact(
            coverage,
            {
                "major_claim_count",
                "official_source_bound_major_claim_count",
                "official_source_bound_verifiable_claim_count",
                "verifiable_claim_count",
            },
        )
        if coverage != {
            "major_claim_count": len(packet_claims),
            "official_source_bound_major_claim_count": len(packet_claims),
            "official_source_bound_verifiable_claim_count": verifiable_count,
            "verifiable_claim_count": verifiable_count,
        }:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for source_ref, source in sources.items():
        _source_url(source["url"])
        if (
            source["capture_status"] != _FINAL_SOURCE_STATUS
            or source["review_body_excluded_from_claim_evidence"] is not True
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
        bound_claims = [
            claim
            for claim in all_claims.values()
            if source_ref in cast(list[object], claim["evidence_refs"])
        ]
        if require_sha256(source["immutable_capture_sha256"]) != _source_capture_hash(
            source, bound_claims
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for source in policy_sources.values():
        _source_url(source["url"])
        if (
            source["capture_status"] != _FINAL_SOURCE_STATUS
            or source["review_body_excluded_from_claim_evidence"] is not True
            or require_sha256(source["immutable_capture_sha256"])
            != _source_capture_hash(source, [])
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return registry, sources, packets, affiliates, all_claims


def _validate_media(document: object) -> dict[str, Mapping[str, object]]:
    registry = _mapping(document)
    _exact(
        registry,
        {"assets", "policy", "publication_authority", "schema", "slice_id", "story_id"},
    )
    if (
        registry["schema"] != _MEDIA_SCHEMA
        or registry["story_id"] != "ST-1704"
        or registry["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or registry["publication_authority"] != "NONE"
    ):
        _fail()
    policy = _mapping(registry["policy"])
    if policy != {
        "allowed_asset_class": "rakuten_api_product_image",
        "aspect_ratio_change_allowed": False,
        "crop_allowed": False,
        "exact_provider_resource_required": True,
        "missing_asset_behavior": "BLOCK_PUBLICATION",
        "modification_allowed": False,
        "object_fit": "contain",
        "text_overlay_allowed": False,
        "upscale_allowed": False,
    }:
        _fail()
    assets = _index(
        registry["assets"],
        key="media_asset_ref",
        exact_keys={
            "alt",
            "asset_class",
            "display_policy",
            "height",
            "identity",
            "image_sha256",
            "image_url",
            "media_asset_ref",
            "product_id",
            "product_name",
            "provider",
            "publication_blocker",
            "required_height",
            "required_width",
            "response_sha256",
            "retrieved_at",
            "source_url",
            "status",
            "width",
        },
    )
    if len(assets) != 18 or len(
        {asset["product_id"] for asset in assets.values()}
    ) != len(assets):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for asset in assets.values():
        identity = _mapping(asset["identity"])
        display = _mapping(asset["display_policy"])
        _exact(
            identity,
            {
                "allowed_variants",
                "forbidden_title_tokens",
                "item_code",
                "jan",
                "product_kind_tokens",
                "required_title_tokens",
                "status",
            },
        )
        _exact(display, {"lazy_load", "linked_image", "object_fit"})
        allowed_variants = [
            _text(value, maximum=300) for value in _list(identity["allowed_variants"])
        ]
        required_title_tokens = [
            _text(value, maximum=300)
            for value in _list(identity["required_title_tokens"])
        ]
        product_kind_tokens = [
            _text(value, maximum=300)
            for value in _list(identity["product_kind_tokens"])
        ]
        forbidden_title_tokens = [
            _text(value, maximum=300)
            for value in _list(identity["forbidden_title_tokens"])
        ]
        if (
            asset["asset_class"] != "rakuten_api_product_image"
            or asset["provider"] != "RAKUTEN_ICHIBA_ITEM_SEARCH"
            or asset["required_width"] != 128
            or asset["required_height"] != 128
            or display
            != {"lazy_load": True, "linked_image": False, "object_fit": "contain"}
            or not _text(asset["alt"], maximum=500)
            or not allowed_variants
            or len(allowed_variants) != len(set(allowed_variants))
            or any("_OR_" in value for value in allowed_variants)
            or not required_title_tokens
            or not product_kind_tokens
            or not forbidden_title_tokens
            or len(required_title_tokens) != len(set(required_title_tokens))
            or len(product_kind_tokens) != len(set(product_kind_tokens))
            or len(forbidden_title_tokens) != len(set(forbidden_title_tokens))
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if asset["status"] == "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE":
            if (
                any(
                    asset[key] is not None
                    for key in (
                        "source_url",
                        "image_url",
                        "width",
                        "height",
                        "retrieved_at",
                        "response_sha256",
                        "image_sha256",
                    )
                )
                or identity["item_code"] is not None
                or identity["status"] != "PENDING_EXACT_MATCH"
                or asset["publication_blocker"] != "PENDING_PRODUCT_MEDIA_EVIDENCE"
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        else:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return assets


def _validate_articles(
    document: object,
) -> tuple[
    Mapping[str, object],
    dict[str, Mapping[str, object]],
    dict[str, Mapping[str, object]],
]:
    collection = _mapping(document)
    _exact(
        collection,
        {
            "article_order",
            "articles",
            "publication_authority",
            "routes",
            "schema",
            "slice_id",
            "story_id",
            "target_origin",
        },
    )
    if (
        collection["schema"] != _ARTICLE_SCHEMA
        or collection["story_id"] != "ST-1704"
        or collection["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or collection["target_origin"] != PILOT_ORIGIN
        or collection["publication_authority"] != "NONE"
        or tuple(_list(collection["article_order"])) != _ARTICLE_IDS
    ):
        _fail()
    routes = _index(
        collection["routes"],
        key="route_ref",
        exact_keys={"article_id", "path", "publication_state", "route_ref", "title"},
    )
    articles = _index(
        collection["articles"], key="article_id", exact_keys=_ARTICLE_KEYS
    )
    if tuple(articles) != _ARTICLE_IDS or len(routes) != 6:
        _fail()
    expected_routes = {
        "ROUTE-HOME-GUIDES": (None, "/", "PUBLISHED"),
        **{
            f"ROUTE-ARTICLE-{name}": (
                identity.article_id,
                f"/{identity.slug}/",
                state,
            )
            for name, identity, state in zip(
                (
                    "SUITCASE",
                    "PORTABLE-POWER",
                    "ANKER-DIFFERENCES",
                    "DISHWASHER",
                    "ROBOT-VACUUM",
                ),
                PILOT_ARTICLE_IDENTITIES,
                (
                    "PUBLISHED_EXISTING_REVIEW_UPDATE_PENDING",
                    "DRAFT_PENDING_HUMAN_PUBLICATION",
                    "DRAFT_PENDING_HUMAN_PUBLICATION",
                    "DRAFT_PENDING_HUMAN_PUBLICATION",
                    "DRAFT_PENDING_HUMAN_PUBLICATION",
                ),
                strict=True,
            )
        },
    }
    if set(routes) != set(expected_routes):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for route_ref, (
        expected_article,
        expected_path,
        expected_state,
    ) in expected_routes.items():
        route = routes[route_ref]
        if (
            route["article_id"] != expected_article
            or route["path"] != expected_path
            or not _text(route["title"], maximum=300)
            or route["publication_state"] != expected_state
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for identity in PILOT_ARTICLE_IDENTITIES:
        article = articles[identity.article_id]
        if (
            article["slot"] != identity.slot
            or article["article_type_code"] != identity.article_type_code
            or article["publication_authority"] != "NONE"
            or article["slug"] != identity.slug
            or article["canonical_url"] != f"{PILOT_ORIGIN}/{identity.slug}/"
            or article["category"] != "暮らしの道具"
            or article["intent_cluster"] != identity.section
        ):
            _fail(EditorialPilotFailureCode.ARTICLE_IDENTITY_MISMATCH)
    return collection, routes, articles


def _evidence_value(value: RakutenProductEvidence) -> dict[str, object]:
    return {
        "affiliate_request_fingerprint": value.affiliate_request_fingerprint,
        "affiliate_ref": value.affiliate_ref,
        "affiliate_response_sha256": value.affiliate_response_sha256,
        "affiliate_selected_result_sha256": (value.affiliate_selected_result_sha256),
        "destination_url": value.destination_url,
        "height": value.height,
        "image_sha256": value.image_sha256,
        "image_url": value.image_url,
        "item_code": value.item_code,
        "item_name": value.item_name,
        "jan": value.jan,
        "media_asset_ref": value.media_asset_ref,
        "no_modification_policy": dict(value.no_modification_policy),
        "product_id": value.product_id,
        "request_fingerprint": value.request_fingerprint,
        "response_sha256": value.response_sha256,
        "retrieved_at": value.retrieved_at,
        "schema": value.schema,
        "selected_result_sha256": value.selected_result_sha256,
        "source_url": value.source_url,
        "variant": value.variant,
        "width": value.width,
    }


def _bind_source_capture_evidence(
    repository_root: Path,
    *,
    packet: Mapping[str, object],
    all_registry_claims: Mapping[str, Mapping[str, object]],
    selected_sources: list[Mapping[str, object]],
    policy_sources: list[Mapping[str, object]],
    editorial_facts_checked_on: str,
    reader: Callable[..., OfficialSourceCaptureEvidence],
    now: datetime,
) -> list[OfficialSourceCaptureEvidence]:
    del packet
    claims = list(all_registry_claims.values())
    bound: list[OfficialSourceCaptureEvidence] = []
    for source, is_policy in [
        *((value, False) for value in selected_sources),
        *((value, True) for value in policy_sources),
    ]:
        source_ref = _text(source["source_ref"], maximum=300)
        evidence = reader(repository_root, source_ref=source_ref)
        expected_claim_ids = (
            {"POLICY-SOURCE-STATEMENT"}
            if is_policy
            else {
                _text(claim["claim_id"], maximum=300)
                for claim in claims
                if source_ref in cast(list[object], claim["evidence_refs"])
            }
        )
        locator_claim_ids = {
            claim_id for claim_id, _statement_digest, _fragments in evidence.locators
        }
        expected_statement_sha256 = (
            {
                "POLICY-SOURCE-STATEMENT": bytes_sha256(
                    _text(source["title"], maximum=500).encode("utf-8")
                )
            }
            if is_policy
            else {
                _text(claim["claim_id"], maximum=300): bytes_sha256(
                    _text(claim["statement"], maximum=4000).encode("utf-8")
                )
                for claim in claims
                if source_ref in cast(list[object], claim["evidence_refs"])
            }
        )
        observed_statement_sha256 = {
            claim_id: statement_digest
            for claim_id, statement_digest, _fragments in evidence.locators
        }
        expected_content_type = (
            "application/pdf"
            if source["source_type"] == "PRODUCT_MANUAL"
            else "text/html"
        )
        try:
            captured_at = datetime.fromisoformat(
                evidence.retrieved_at.removesuffix("Z") + "+00:00"
            )
            source_observed_on = date.fromisoformat(_date(source["retrieved_on"]))
            editorial_observed_on = date.fromisoformat(
                _date(editorial_facts_checked_on)
            )
            capture_floor = (
                source_observed_on
                if is_policy
                else max(source_observed_on, editorial_observed_on)
            )
        except OverflowError, ValueError:
            _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
        if (
            type(evidence) is not OfficialSourceCaptureEvidence
            or evidence.source_ref != source_ref
            or evidence.final_url != source["url"]
            or captured_at.date() < capture_floor
            or evidence.content_type != expected_content_type
            or not expected_claim_ids
            or locator_claim_ids != expected_claim_ids
            or observed_statement_sha256 != expected_statement_sha256
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        age = now - captured_at
        if age < timedelta(0) or age > timedelta(days=ARTICLE_FACT_MAX_AGE_DAYS):
            _fail(EditorialPilotFailureCode.RESOURCE_NOT_READY)
        bound.append(evidence)
    if len(bound) != len(selected_sources) + len(policy_sources):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return bound


def _claim_references(value: object, allowed: set[str]) -> set[str]:
    observed: set[str] = set()
    if type(value) is dict:
        mapping = cast(dict[str, object], value)
        for key, child in mapping.items():
            if key in {"claim_ids", "rationale_claim_ids"}:
                references = [
                    _text(reference, maximum=300) for reference in _list(child)
                ]
                if len(references) != len(set(references)) or any(
                    reference not in allowed for reference in references
                ):
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                observed.update(references)
            else:
                observed.update(_claim_references(child, allowed))
    elif type(value) is list:
        for child in cast(list[object], value):
            observed.update(_claim_references(child, allowed))
    return observed


def _provider_title_has_token(title: str, token: str) -> bool:
    normalized_title = title.casefold()
    normalized_token = token.casefold()
    prefix = (
        r"(?<![a-z0-9])"
        if re.fullmatch(r"[a-z0-9]", normalized_token[0], re.ASCII)
        else ""
    )
    suffix = (
        r"(?![a-z0-9])"
        if re.fullmatch(r"[a-z0-9]", normalized_token[-1], re.ASCII)
        else ""
    )
    return (
        re.search(prefix + re.escape(normalized_token) + suffix, normalized_title)
        is not None
    )


def _bind_product_evidence(
    repository_root: Path,
    article: Mapping[str, object],
    affiliates: Mapping[str, Mapping[str, object]],
    media: Mapping[str, Mapping[str, object]],
    reader: Callable[..., RakutenProductEvidence],
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, RakutenProductEvidence],
    list[Mapping[str, object]],
    list[Mapping[str, object]],
]:
    render = _mapping(article["render_model"])
    _exact(render, _RENDER_KEYS)
    disclosure = _mapping(render["disclosure"])
    cta_policy = _mapping(render["cta_policy"])
    internal_link_policy = _mapping(render["internal_link_policy"])
    _exact(disclosure, {"label", "paragraphs"})
    _exact(
        cta_policy,
        {
            "copy",
            "destination_label",
            "direct_link_only",
            "fixed_price_inventory_points_in_body",
            "independent_from_finance",
            "required_rel",
        },
    )
    _exact(
        internal_link_policy,
        {"resolve_only_when_target_is_published", "unresolved_behavior"},
    )
    if (
        cta_policy
        != {
            "copy": PILOT_CTA_LABEL,
            "destination_label": "楽天市場",
            "direct_link_only": True,
            "fixed_price_inventory_points_in_body": False,
            "independent_from_finance": True,
            "required_rel": "sponsored nofollow",
        }
        or internal_link_policy
        != {
            "resolve_only_when_target_is_published": True,
            "unresolved_behavior": "OMIT_LINK",
        }
        or not _text(disclosure["label"], maximum=200)
        or not _list(disclosure["paragraphs"])
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for paragraph in _list(disclosure["paragraphs"]):
        _text(paragraph)
    cards = _index(
        render["product_cards"],
        key="product_selection_ref",
        exact_keys={
            "affiliate_ref",
            "caution",
            "condition_label",
            "confirmed_facts",
            "cta",
            "editorial_fit",
            "media_asset_ref",
            "product_id",
            "product_name",
            "product_selection_ref",
            "source_refs",
        },
    )
    evidences: dict[str, RakutenProductEvidence] = {}
    affiliate_records: list[Mapping[str, object]] = []
    media_records: list[Mapping[str, object]] = []
    for card in cards.values():
        product_id = _text(card["product_id"], maximum=300)
        _text(card["product_name"], maximum=500)
        _text(card["condition_label"], maximum=500)
        _text(card["editorial_fit"], maximum=2000)
        _text(card["caution"], maximum=2000)
        source_refs = [
            _text(value, maximum=300) for value in _list(card["source_refs"])
        ]
        if not source_refs or len(source_refs) != len(set(source_refs)):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        for raw_fact in _list(card["confirmed_facts"]):
            fact = _mapping(raw_fact)
            _exact(fact, {"claim_ids", "label", "value"})
            _text(fact["label"], maximum=300)
            _text(fact["value"], maximum=1000)
        affiliate_ref = _text(card["affiliate_ref"], maximum=300)
        media_ref = _text(card["media_asset_ref"], maximum=300)
        affiliate = affiliates.get(affiliate_ref)
        asset = media.get(media_ref)
        if affiliate is None or asset is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        evidence = reader(repository_root, product_id=product_id)
        identity = _mapping(asset["identity"])
        display = _mapping(asset["display_policy"])
        cta = _mapping(card["cta"])
        if (
            type(evidence) is not RakutenProductEvidence
            or evidence.product_id != product_id
            or evidence.affiliate_ref != affiliate_ref
            or evidence.media_asset_ref != media_ref
            or affiliate["product_id"] != product_id
            or affiliate["product_name"] != card["product_name"]
            or affiliate["destination_policy"] != "DIRECT_RAKUTEN_AFFILIATE_URL"
            or affiliate["required_rel"] != "sponsored nofollow"
            or affiliate["cta_copy"] != PILOT_CTA_LABEL
            or (
                affiliate["destination_url"] is not None
                and affiliate["destination_url"] != evidence.destination_url
            )
            or asset["product_id"] != product_id
            or asset["product_name"] != card["product_name"]
            or asset["asset_class"] != "rakuten_api_product_image"
            or asset["provider"] != "RAKUTEN_ICHIBA_ITEM_SEARCH"
            or asset["required_width"] != 128
            or asset["required_height"] != 128
            or not _text(asset["alt"], maximum=500)
            or evidence.variant not in cast(list[object], identity["allowed_variants"])
            or any(
                not _provider_title_has_token(evidence.item_name, token)
                for token in cast(list[str], identity["required_title_tokens"])
            )
            or not any(
                _provider_title_has_token(evidence.item_name, token)
                for token in cast(list[str], identity["product_kind_tokens"])
            )
            or any(
                token.casefold() in evidence.item_name.casefold()
                for token in cast(list[str], identity["forbidden_title_tokens"])
            )
            or (
                identity.get("item_code") is not None
                and identity.get("item_code") != evidence.item_code
            )
            or (identity.get("jan") is not None and identity.get("jan") != evidence.jan)
            or display
            != {"lazy_load": True, "linked_image": False, "object_fit": "contain"}
            or cta
            != {
                "copy": PILOT_CTA_LABEL,
                "data_article_id": article["article_id"],
                "data_placement": "product_card",
                "data_product_id": product_id,
                "destination_label": "楽天市場",
                "required_rel": "sponsored nofollow",
            }
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        for key, observed in (
            ("source_url", evidence.source_url),
            ("image_url", evidence.image_url),
            ("width", evidence.width),
            ("height", evidence.height),
            ("retrieved_at", evidence.retrieved_at),
            ("response_sha256", evidence.response_sha256),
            ("image_sha256", evidence.image_sha256),
        ):
            if asset[key] is not None and asset[key] != observed:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        evidences[product_id] = evidence
        affiliate_records.append(affiliate)
        media_records.append(asset)
    if len(evidences) != len(cards):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    return cards, evidences, affiliate_records, media_records


def _rich(
    value: object,
    *,
    routes: Mapping[str, Mapping[str, object]],
    sources: Mapping[str, Mapping[str, object]],
) -> str:
    output: list[str] = []
    for raw in _list(value):
        node = _mapping(raw)
        kind = node.get("type")
        if kind == "text":
            output.append(escape(_text(node.get("text"))))
        elif kind == "inline_code":
            output.append(
                f"<code>{escape(_text(node.get('text'), maximum=500))}</code>"
            )
        elif kind in {"strong", "emphasis"}:
            tag = "strong" if kind == "strong" else "em"
            output.append(
                f"<{tag}>{_rich(node.get('children'), routes=routes, sources=sources)}</{tag}>"
            )
        elif kind == "line_break":
            output.append("<br>")
        elif kind == "internal_link":
            route_ref = _text(node.get("route_ref"), maximum=300)
            route = routes.get(route_ref)
            if route is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            label = _rich(node.get("children"), routes=routes, sources=sources)
            if cast(str, route["publication_state"]).startswith("PUBLISHED"):
                output.append(
                    f'<a href="{escape(cast(str, route["path"]), quote=True)}">{label}</a>'
                )
            else:
                output.append(label)
        elif kind == "approved_external_citation":
            source_ref = _text(node.get("source_ref"), maximum=300)
            source = sources.get(source_ref)
            if source is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            label = _rich(node.get("children"), routes=routes, sources=sources)
            output.append(
                '<a class="raos-source-link" '
                f'href="{escape(cast(str, source["url"]), quote=True)}">{label}</a>'
            )
        else:
            _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
    return "".join(output)


def _list_html(
    values: object,
    *,
    routes: Mapping[str, Mapping[str, object]],
    sources: Mapping[str, Mapping[str, object]],
) -> str:
    return "".join(
        f"<li>{_rich(value, routes=routes, sources=sources)}</li>"
        for value in _list(values)
    )


def _require_public_blocks(
    ast: Mapping[str, object],
) -> list[Mapping[str, object]]:
    blocks = [_mapping(value) for value in _list(ast["blocks"])]
    if not blocks or any(block.get("visibility") != "public" for block in blocks):
        _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
    return blocks


@final
class _Renderer:
    __slots__ = (
        "article",
        "alts",
        "axes",
        "cards",
        "evidences",
        "model",
        "recommendations",
        "routes",
        "sources",
        "tables",
    )

    def __init__(
        self,
        *,
        article: Mapping[str, object],
        routes: Mapping[str, Mapping[str, object]],
        sources: Mapping[str, Mapping[str, object]],
        cards: Mapping[str, Mapping[str, object]],
        evidences: Mapping[str, RakutenProductEvidence],
        alts: Mapping[str, str],
    ) -> None:
        self.article = article
        self.routes = routes
        self.sources = sources
        self.cards = cards
        self.evidences = evidences
        self.alts = alts
        self.model = _mapping(article["render_model"])
        self.axes = _index(
            self.model["comparison_axes"],
            key="comparison_axis_ref",
            exact_keys={"comparison_axis_ref", "description", "label"},
        )
        self.tables = _index(
            self.model["comparison_tables"],
            key="comparison_table_ref",
            exact_keys={"axis_refs", "caption", "comparison_table_ref", "rows"},
        )
        self.recommendations = _index(
            self.model["recommendations"],
            key="recommendation_ref",
            exact_keys={
                "claim_ids",
                "condition",
                "product_selection_ref",
                "rationale",
                "recommendation_ref",
            },
        )

    def rich(self, value: object) -> str:
        return _rich(value, routes=self.routes, sources=self.sources)

    def card(self, product_selection_ref: str) -> str:
        card = self.cards.get(product_selection_ref)
        if card is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        product_id = cast(str, card["product_id"])
        evidence = self.evidences[product_id]
        facts = "".join(
            "<li><strong>"
            + escape(_text(_mapping(raw)["label"], maximum=200))
            + "：</strong>"
            + escape(_text(_mapping(raw)["value"], maximum=1000))
            + "</li>"
            for raw in _list(card["confirmed_facts"])
        )
        return (
            '<article class="raos-product-card">'
            '<div class="raos-product-card__media">'
            f'<img src="{escape(evidence.image_url, quote=True)}" '
            f'alt="{escape(self.alts[product_id], quote=True)}" '
            'width="128" height="128" loading="lazy" decoding="async">'
            "</div>"
            '<div class="raos-product-card__body">'
            f"<h3>{escape(cast(str, card['product_name']))}</h3>"
            f'<p class="raos-condition-label">{escape(cast(str, card["condition_label"]))}</p>'
            f'<ul class="raos-product-card__facts">{facts}</ul>'
            f"<p>{escape(cast(str, card['editorial_fit']))}</p>"
            f"<p><strong>向かない条件：</strong>{escape(cast(str, card['caution']))}</p>"
            f'<a class="raos-cta" href="{escape(evidence.destination_url, quote=True)}" '
            'rel="sponsored nofollow" '
            f'data-raos-article-id="{escape(cast(str, self.article["article_id"]), quote=True)}" '
            f'data-raos-product-id="{escape(product_id, quote=True)}" '
            f'data-raos-placement="product_card">{PILOT_CTA_LABEL}</a>'
            "</div></article>"
        )

    def comparison(self, block: Mapping[str, object]) -> str:
        table_ref = _text(block["comparison_table_ref"], maximum=300)
        table = self.tables.get(table_ref)
        if table is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        axis_refs = [_text(value, maximum=300) for value in _list(table["axis_refs"])]
        if axis_refs != [
            _text(value, maximum=300) for value in _list(block["comparison_axis_refs"])
        ]:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        header = "".join(
            f'<th scope="col">{escape(cast(str, self.axes[ref]["label"]))}</th>'
            for ref in axis_refs
            if ref in self.axes
        )
        if len(axis_refs) != len(header.split('<th scope="col">')) - 1:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        rows: list[str] = []
        mobile_cards: list[str] = []
        observed_products: list[str] = []
        for raw_row in _list(table["rows"]):
            row = _mapping(raw_row)
            _exact(row, {"cells", "product_selection_ref"})
            product_ref = _text(row["product_selection_ref"], maximum=300)
            card = self.cards.get(product_ref)
            if card is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            cells = _index(
                row["cells"],
                key="axis_ref",
                exact_keys={"axis_ref", "claim_ids", "state", "value"},
            )
            if tuple(cells) != tuple(axis_refs):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            rendered_cells = "".join(
                f"<td>{escape(cast(str, cells[ref]['value']))}</td>"
                for ref in axis_refs
            )
            rows.append(
                f'<tr><th scope="row">{escape(cast(str, card["product_name"]))}</th>'
                f"{rendered_cells}</tr>"
            )
            mobile_pairs = [
                "<div><dt>商品</dt><dd>"
                + escape(cast(str, card["product_name"]))
                + "</dd></div>"
            ]
            mobile_pairs.extend(
                "<div><dt>"
                + escape(cast(str, self.axes[ref]["label"]))
                + "</dt><dd>"
                + escape(cast(str, cells[ref]["value"]))
                + "</dd></div>"
                for ref in axis_refs
            )
            mobile_cards.append(
                '<article class="raos-comparison-card"><dl>'
                + "".join(mobile_pairs)
                + "</dl></article>"
            )
            observed_products.append(product_ref)
        expected_products = [
            _text(value, maximum=300)
            for value in _list(block["product_selection_refs"])
        ]
        if observed_products != expected_products:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        title_id = f"{cast(str, block['block_id']).lower()}-title"
        return (
            f'<section><h2 id="{title_id}">比較表</h2>'
            f'<div class="raos-comparison" role="region" tabindex="0" aria-labelledby="{title_id}">'
            '<div class="raos-comparison__table-view">'
            f"<table><caption>{escape(cast(str, table['caption']))}</caption>"
            f'<thead><tr><th scope="col">商品</th>{header}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            '<div class="raos-comparison__cards">'
            f"{''.join(mobile_cards)}</div></div></section>"
        )

    def recommendation_group(self, block: Mapping[str, object]) -> str:
        items: list[str] = []
        for raw_ref in _list(block["recommendation_refs"]):
            recommendation_ref = _text(raw_ref, maximum=300)
            recommendation = self.recommendations.get(recommendation_ref)
            if recommendation is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            product_ref = cast(str, recommendation["product_selection_ref"])
            card = self.cards.get(product_ref)
            if card is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            product_id = cast(str, card["product_id"])
            evidence = self.evidences[product_id]
            items.append(
                "<li>"
                f"<strong>{escape(cast(str, recommendation['condition']))}：</strong>"
                f"{escape(cast(str, card['product_name']))}。"
                f"{escape(cast(str, recommendation['rationale']))} "
                f'<a class="raos-cta" href="{escape(evidence.destination_url, quote=True)}" '
                'rel="sponsored nofollow" '
                f'data-raos-article-id="{escape(cast(str, self.article["article_id"]), quote=True)}" '
                f'data-raos-product-id="{escape(product_id, quote=True)}" '
                f'data-raos-placement="final_summary">{PILOT_CTA_LABEL}</a>'
                "</li>"
            )
        return (
            '<section class="raos-decision-summary">'
            f"<h2>{escape(cast(str, block['label']))}</h2>"
            f"<p>{self.rich(block['condition'])}</p><ul>{''.join(items)}</ul></section>"
        )

    def render(self, ast: Mapping[str, object]) -> str:
        blocks = _require_public_blocks(ast)
        if blocks[0].get("type") != "disclosure_slot":
            _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
        output: list[str] = []
        index = 0
        while index < len(blocks):
            block = blocks[index]
            kind = block.get("type")
            if kind == "disclosure_slot":
                disclosure = _mapping(self.model["disclosure"])
                _exact(disclosure, {"label", "paragraphs"})
                paragraphs = "".join(
                    f"<p>{escape(_text(value))}</p>"
                    for value in _list(disclosure["paragraphs"])
                )
                output.append(
                    '<aside class="raos-disclosure" aria-label="広告表示">'
                    f"<h2>{escape(cast(str, disclosure['label']))}</h2>{paragraphs}</aside>"
                )
            elif kind == "lead":
                output.append(f'<p class="raos-lead">{self.rich(block["content"])}</p>')
            elif kind == "decision_summary":
                items = "".join(
                    '<li><strong class="raos-condition-label">'
                    + escape(cast(str, _mapping(raw)["condition"]))
                    + "</strong>"
                    + self.rich(_mapping(raw)["summary"])
                    + "</li>"
                    for raw in _list(block["items"])
                )
                output.append(
                    '<section class="raos-decision-summary"><h2>30秒でわかる条件別の結論</h2>'
                    f"<ul>{items}</ul></section>"
                )
            elif kind == "intended_reader":
                output.append(
                    "<section><h2>この比較が向く人</h2>"
                    f"<ul>{_list_html(block['fits'], routes=self.routes, sources=self.sources)}</ul>"
                    "<h3>向かない人</h3>"
                    f"<ul>{_list_html(block['not_fits'], routes=self.routes, sources=self.sources)}</ul>"
                    "<h3>前提</h3>"
                    f"<ul>{_list_html(block['assumptions'], routes=self.routes, sources=self.sources)}</ul>"
                    "</section>"
                )
            elif kind == "methodology":
                output.append(
                    "<section><h2>比較方法</h2>"
                    f"<p>{self.rich(block['candidate_universe_summary'])}</p>"
                    "<h3>含めた条件</h3>"
                    f"<ul>{_list_html(block['inclusion_rules'], routes=self.routes, sources=self.sources)}</ul>"
                    "<h3>除外した条件</h3>"
                    f"<ul>{_list_html(block['exclusion_rules'], routes=self.routes, sources=self.sources)}</ul>"
                    f"<p>確認日時：{escape(cast(str, block['data_checked_at']))}</p></section>"
                )
            elif kind == "selection_criteria":
                criteria = "".join(
                    "<li><strong>"
                    + escape(cast(str, _mapping(raw)["label"]))
                    + "：</strong>"
                    + self.rich(_mapping(raw)["explanation"])
                    + "</li>"
                    for raw in _list(block["criteria"])
                )
                output.append(
                    f"<section><h2>選び方の基準</h2><ul>{criteria}</ul></section>"
                )
            elif kind == "difference_matrix":
                matrix_ref = _text(block["matrix_ref"], maximum=300)
                matrices = _index(
                    self.model["difference_matrices"],
                    key="matrix_ref",
                    exact_keys={
                        "matrix_ref",
                        "show_equal_values",
                        "show_unknown_values",
                        "table_ref",
                    },
                )
                matrix = matrices.get(matrix_ref)
                if matrix is None or matrix["table_ref"] not in self.tables:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                output.append(
                    "<section><h2>違いの見取り図</h2>"
                    "<p>同じ条件と未確認の項目も省かず、比較表で差を確認します。</p></section>"
                )
            elif kind == "comparison_table":
                output.append(self.comparison(block))
            elif kind == "product_card":
                product_blocks: list[Mapping[str, object]] = []
                while (
                    index < len(blocks) and blocks[index].get("type") == "product_card"
                ):
                    product_blocks.append(blocks[index])
                    index += 1
                output.append(
                    "<section><h2>写真付きの商品候補</h2>"
                    '<div class="raos-product-grid">'
                    + "".join(
                        self.card(cast(str, value["product_selection_ref"]))
                        for value in product_blocks
                    )
                    + "</div></section>"
                )
                continue
            elif kind == "tradeoff":
                card = self.cards.get(cast(str, block["subject_ref"]))
                if card is None:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                output.append(
                    '<section class="raos-tradeoff">'
                    f"<h3>{escape(cast(str, card['product_name']))}の向く条件・向かない条件</h3>"
                    f"<p><strong>向く条件：</strong>{self.rich(block['benefit'])}</p>"
                    f"<p><strong>制約：</strong>{self.rich(block['cost_or_limitation'])}</p>"
                    f"<p><strong>判断条件：</strong>{self.rich(block['applies_when'])}</p></section>"
                )
            elif kind == "recommendation_group":
                output.append(self.recommendation_group(block))
            elif kind == "caution":
                output.append(
                    '<aside class="raos-caution"><h2>購入前の確認</h2>'
                    f"<p>{self.rich(block['content'])}</p></aside>"
                )
            elif kind == "source_summary":
                refs = [
                    _text(value, maximum=300)
                    for value in _list(self.model["primary_source_refs"])
                ]
                source_links: list[str] = []
                for source_ref in refs:
                    source = self.sources.get(source_ref)
                    if source is None:
                        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                    source_links.append(
                        f'<li><a class="raos-source-link" href="{escape(cast(str, source["url"]), quote=True)}">'
                        f"{escape(cast(str, source['title']))}</a></li>"
                    )
                output.append(
                    "<section><h2>一次情報</h2>"
                    f"<ul>{''.join(source_links)}</ul>"
                    f'<p class="raos-source-link"><a href="{PILOT_RAKUTEN_CREDIT_URL}">'
                    f"{PILOT_RAKUTEN_CREDIT_LABEL}</a></p></section>"
                )
            elif kind == "internal_links":
                for raw in _list(block["links"]):
                    link = _mapping(raw)
                    route = self.routes.get(cast(str, link["route_ref"]))
                    if route is None:
                        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                    _text(link["anchor_text"], maximum=300)
                    _text(link["journey_purpose"], maximum=500)
            else:
                _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
            index += 1
        return "\n".join(output) + "\n"


@final
@dataclass(frozen=True, slots=True, repr=False)
class PreparedEditorialArticle:
    article_id: str
    packet_sha256: str
    content_sha256: str
    request: ReviewDraftRequest
    product_count: int
    source_count: int
    network_requests: int = 0
    external_writes: int = 0
    publication_actions: int = 0
    publication_authority: bool = False
    production_evidence: bool = False


def prepare_editorial_article(
    repository_root: Path,
    article_id: str,
    *,
    evidence_reader: Callable[..., RakutenProductEvidence] = (
        read_rakuten_product_evidence
    ),
    source_evidence_reader: Callable[..., OfficialSourceCaptureEvidence] = (
        read_official_source_capture_evidence
    ),
    clock: Callable[[], datetime] = _utc_now,
) -> PreparedEditorialArticle:
    """Prepare one allowlisted immutable draft request without external I/O."""

    identity = article_identity(article_id)
    if (
        not repository_root.is_absolute()
        or not callable(evidence_reader)
        or not callable(source_evidence_reader)
        or not callable(clock)
    ):
        _fail()
    now = _clock_value(clock)
    collection, routes, articles = _validate_articles(
        _read_fixed_json(repository_root, ARTICLE_COLLECTION_RELATIVE_PATH)
    )
    source_registry, sources, packets, affiliates, all_registry_claims = (
        _validate_sources(
            _read_fixed_json(repository_root, SOURCE_REGISTRY_RELATIVE_PATH)
        )
    )
    media = _validate_media(
        _read_fixed_json(repository_root, MEDIA_REGISTRY_RELATIVE_PATH)
    )
    article = articles[identity.article_id]
    readiness = _mapping(article["readiness"])
    freshness = _mapping(article["freshness"])
    _exact(readiness, {"blocking_reasons", "status"})
    _exact(freshness, {"facts_checked_on", "publication_recheck_required"})
    blocking_reasons = [
        _text(value, maximum=100) for value in _list(readiness["blocking_reasons"])
    ]
    if (
        readiness["status"] != "BLOCKED_PENDING_LIVE_EVIDENCE_AND_HUMAN_APPROVAL"
        or not blocking_reasons
        or len(blocking_reasons) != len(set(blocking_reasons))
        or "HUMAN_PUBLICATION_APPROVAL_REQUIRED" not in blocking_reasons
        or any(
            value
            not in {
                "HUMAN_PUBLICATION_APPROVAL_REQUIRED",
                "PENDING_AFFILIATE_EVIDENCE",
                "PENDING_PRODUCT_MEDIA_EVIDENCE",
            }
            for value in blocking_reasons
        )
        or freshness["publication_recheck_required"] is not True
        or not _date(freshness["facts_checked_on"])
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    _require_observed_date_not_future(freshness["facts_checked_on"], now=now)
    seo = _mapping(article["seo"])
    _exact(
        seo,
        {
            "draft_robots",
            "meta_description",
            "meta_title",
            "published_robots",
            "structured_data_allowed",
            "structured_data_forbidden",
            "visible_content_must_match",
        },
    )
    if (
        seo["draft_robots"] != "noindex,nofollow"
        or seo["published_robots"] != "index,follow"
        or seo["structured_data_allowed"]
        != ["Article", "BreadcrumbList", "Organization", "WebSite"]
        or seo["structured_data_forbidden"]
        != ["Product", "Offer", "Review", "AggregateRating", "FAQPage"]
        or seo["visible_content_must_match"] is not True
    ):
        _fail()
    packet_ref = _text(article["source_packet_ref"], maximum=300)
    packet = packets.get(packet_ref)
    if packet is None or packet["article_id"] != article_id:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    try:
        ast_model = load_content_ast(canonical_json_bytes(article["content_ast"]))
        ast = cast(
            Mapping[str, object],
            ast_model.model_dump(mode="json", by_alias=True, warnings=False),
        )
    except ContentAstValidationError, ContentAstContractError:
        _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
    if (
        ast["article_id"] != article_id
        or ast["article_type"] != identity.article_type
        or ast["title"] != article["title"]
        or ast["source_packet_version_ref"] != packet_ref
        or ast["publication_flags"]
        != {
            "affiliate_content": True,
            "allow_auto_publish": False,
            "human_approval_required": True,
        }
    ):
        _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
    _require_public_blocks(ast)
    packet_claim_ids = {
        _text(_mapping(value)["claim_id"], maximum=300)
        for value in _list(packet["claims"])
    }
    observed_claim_ids = _claim_references(ast, packet_claim_ids)
    observed_claim_ids.update(
        _claim_references(article["render_model"], packet_claim_ids)
    )
    if observed_claim_ids != packet_claim_ids:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    cards, evidences, affiliate_records, media_records = _bind_product_evidence(
        repository_root,
        article,
        affiliates,
        media,
        evidence_reader,
    )
    packet_source_refs = set(cast(list[str], packet["source_refs"]))
    render = _mapping(article["render_model"])
    primary_refs = set(cast(list[str], render["primary_source_refs"]))
    if not primary_refs or not primary_refs <= packet_source_refs:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    for card in cards.values():
        refs = set(cast(list[str], card["source_refs"]))
        if not refs or not refs <= packet_source_refs:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    content = _Renderer(
        article=article,
        routes=routes,
        sources=sources,
        cards=cards,
        evidences=evidences,
        alts={
            cast(str, asset["product_id"]): cast(str, asset["alt"])
            for asset in media_records
        },
    ).render(ast)
    content_sha256 = bytes_sha256(content.encode("utf-8", errors="strict"))
    selected_sources = [
        sources[value] for value in cast(list[str], packet["source_refs"])
    ]
    for source in selected_sources:
        _require_observed_date_not_future(source["retrieved_on"], now=now)
    for raw_policy_source in _list(source_registry["policy_sources"]):
        _require_observed_date_not_future(
            _mapping(raw_policy_source)["retrieved_on"], now=now
        )
    policy_sources = [
        _mapping(value) for value in _list(source_registry["policy_sources"])
    ]
    source_evidences = _bind_source_capture_evidence(
        repository_root,
        packet=packet,
        all_registry_claims=all_registry_claims,
        selected_sources=selected_sources,
        policy_sources=policy_sources,
        editorial_facts_checked_on=cast(str, freshness["facts_checked_on"]),
        reader=source_evidence_reader,
        now=now,
    )
    for evidence in evidences.values():
        _require_fresh_rakuten_timestamp(evidence.retrieved_at, now=now)
    packet_material = {
        "affiliate_resources": affiliate_records,
        "article": article,
        "evidence": [
            _evidence_value(evidences[cast(str, card["product_id"])])
            for card in cards.values()
        ],
        "media_resources": media_records,
        "origin": PILOT_ORIGIN,
        "rendered_content_sha256": content_sha256,
        "renderer_schema": _RENDERER_SCHEMA,
        "routes": collection["routes"],
        "schema": "RAOS_ST1704_PREPARED_ARTICLE_PACKET_V1",
        "source_policy": source_registry["source_policy"],
        "source_packet": packet,
        "source_capture_evidence": [value.value() for value in source_evidences],
        "source_policy_sources": source_registry["policy_sources"],
        "sources": selected_sources,
    }
    packet_sha256 = canonical_sha256(packet_material)
    title = _text(article["title"], maximum=300)
    description = _text(seo["meta_description"], maximum=500)
    snapshot = PublicationSnapshot.bind(
        PublicationSnapshotPayload(
            article_id=article_id,
            packet_sha256=packet_sha256,
            slug=identity.slug,
            title=title,
            seo_title=_text(seo["meta_title"], maximum=300),
            description=description,
            canonical_url=f"{PILOT_ORIGIN}/{identity.slug}/",
            og_title=title,
            og_description=description,
            published_at=None,
            modified_at=None,
            author_name=PILOT_AUTHOR_NAME,
            section=identity.section,
            visible_content_sha256=content_sha256,
        )
    )
    request = ReviewDraftRequest.bind(
        article_id=article_id,
        packet_sha256=packet_sha256,
        title=title,
        public_slug=identity.slug,
        excerpt=description,
        content=content,
        snapshot=snapshot,
    )
    return PreparedEditorialArticle(
        article_id=article_id,
        packet_sha256=packet_sha256,
        content_sha256=content_sha256,
        request=request,
        product_count=len(cards),
        source_count=len(selected_sources),
    )


__all__ = [
    "ARTICLE_FACT_MAX_AGE_DAYS",
    "ARTICLE_COLLECTION_RELATIVE_PATH",
    "MEDIA_REGISTRY_RELATIVE_PATH",
    "PreparedEditorialArticle",
    "RAKUTEN_EVIDENCE_MAX_AGE",
    "SLICE_RELATIVE_PATH",
    "SOURCE_REGISTRY_RELATIVE_PATH",
    "prepare_editorial_article",
]
