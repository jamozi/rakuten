"""Deterministic preparation for the ST-1704 self-hosted editorial pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
import json
import math
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
from raos.ports.self_hosted_editorial_pilot import ReviewDraftRevisionBinding


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
_SOURCE_PACKET_ARTICLE_IDS: Final = frozenset(
    {
        *_ARTICLE_IDS,
        "carry-on-suitcase-under-100-seats",
        "front-open-carry-on-suitcase-with-stopper",
        "lightweight-carry-on-suitcase-under-3kg",
        "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus",
    }
)
_SOURCE_HOSTS: Final = frozenset(
    {
        "affiliate.rakuten.co.jp",
        "aqua-has.com",
        "cdn.shopify.com",
        "developers.google.com",
        "help.ecovacs.com",
        "item.rakuten.co.jp",
        "jp.ecoflow.com",
        "jp.roborock.com",
        "lp.ankerjapan.com",
        "panasonic.jp",
        "store.ace.jp",
        "store.irobot-jp.com",
        "support.switch-bot.com",
        "shop.innovator.co.jp",
        "shop.toshiba-lifestyle.com",
        "store.dji.com",
        "www.americantourister.jp",
        "www.ana.co.jp",
        "www.ankerjapan.com",
        "www.bagworld.co.jp",
        "www.bermas.co.jp",
        "www.bluetti.jp",
        "www.caa.go.jp",
        "www.dji.com",
        "dl.djicdn.com",
        "www.dreametech.jp",
        "www.ecovacs.com",
        "www.elecom.co.jp",
        "www.irisohyama.co.jp",
        "www.jackery.jp",
        "www.jal.co.jp",
        "www.meti.go.jp",
        "www.muji.com",
        "www.rimowa.com",
        "www.samsonite.az",
        "www.samsonite.co.jp",
        "www.samsonite.ro",
        "www.siroca.co.jp",
        "www.switchbot.jp",
        "www.thanko.jp",
        "www.toshiba-lifestyle.com",
        "store.siroca.jp",
    }
)
# Independently pin the complete reviewed official-source inventory.  A count
# alone permits an unknown source/URL substitution to pass; hashing the sorted
# source-ref/URL pairs keeps the application boundary closed while allowing
# the generator to expand the reviewed inventory deliberately.
_PRODUCT_SOURCE_INVENTORY_SHA256: Final = (
    "d6179333137f0faf66526a1eadc86c085ada3d12245b6f16955946996210a70b"
)
_POLICY_SOURCE_INVENTORY_SHA256: Final = (
    "5509d907252fe67cbb7aea1fa37ced915cf02d50f5a4a6b2b08341292ddd55c8"
)
_CLAIM_BASE_KEYS: Final = frozenset(
    {
        "claim_id",
        "classification",
        "evidence_level",
        "evidence_refs",
        "statement",
        "status",
        "subject_product_ids",
    }
)
_MARKET_CLAIM_KEYS: Final = frozenset(
    {
        "effective_lifecycle",
        "embedded_structured_lifecycle",
        "evaluated_at",
        "exact_model",
        "exact_variant_scope",
        "lifecycle_evidence_state",
        "market_candidate_id",
        "market_disposition",
        "model_lifecycle",
        "official_url",
        "reader_visible_lifecycle",
        "variant_lifecycle",
    }
)
_PORTFOLIO_REFERENCE_CLAIM_KEYS: Final = frozenset(
    {
        "portfolio_candidate_disposition",
        "portfolio_candidate_reason",
        "route_article_id",
    }
)
_PORTFOLIO_REFERENCE_CLAIMS: Final = {
    "CLM-ST1704-SUITCASE-AEROFLEX-DX2-REFERENCE": (
        "st1703-first-suitcase-comparison",
        "PRD-PROTECA-AEROFLEX-DX2-01521",
        "lightweight-carry-on-suitcase-under-3kg",
    ),
    "CLM-ST1704-POWER-C1000-GEN2-REFERENCE": (
        "st1704-portable-power-station-guide",
        "PRD-ANKER-SOLIX-C1000-GEN2",
        "st1704-anker-solix-c300-c800-c1000-differences",
    ),
    "CLM-ST1704-ANKER-C800-A1753-REFERENCE": (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "PRD-ANKER-SOLIX-C800",
        "st1704-portable-power-station-guide",
    ),
    "CLM-ST1704-ROBOT-F115060-REFERENCE": (
        "st1704-compact-robot-vacuum-shortlist",
        "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
        "roomba-mini-vs-switchbot-k11-pro",
    ),
    "CLM-PORTFOLIO-UNDER100-MAXPASS4-REFERENCE": (
        "carry-on-suitcase-under-100-seats",
        "PRD-ACE-MAXPASS4-01471",
        "st1703-first-suitcase-comparison",
    ),
    "CLM-PORTFOLIO-FRONT-RIMOWA-REFERENCE": (
        "front-open-carry-on-suitcase-with-stopper",
        "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        "lightweight-carry-on-suitcase-under-3kg",
    ),
    "CLM-PORTFOLIO-ROBOT-EUFY-C10-BOUNDARY-REFERENCE": (
        "roomba-mini-vs-switchbot-k11-pro",
        "PRD-EUFY-AUTOEMPTY-C10-T2292",
        "st1704-compact-robot-vacuum-shortlist",
    ),
    "CLM-PORTFOLIO-ROBOT-DEEBOT-MINI2-BOUNDARY-REFERENCE": (
        "roomba-mini-vs-switchbot-k11-pro",
        "PRD-ECOVACS-DEEBOT-MINI2",
        "st1704-compact-robot-vacuum-shortlist",
    ),
}
_CLAIM_OPTIONAL_KEYS: Final = frozenset(
    {
        "dimensions",
        "manufacturer_sales_state",
        "negative_claim_evidence",
        "product_specific_recall_query_gate",
        *_MARKET_CLAIM_KEYS,
        *_PORTFOLIO_REFERENCE_CLAIM_KEYS,
    }
)
_SOURCE_CAPTURE_CLAIM_OPTIONAL_KEYS: Final = (
    "dimensions",
    "market_candidate_id",
    "market_disposition",
    "official_url",
    "exact_model",
    "exact_variant_scope",
    "evaluated_at",
    "model_lifecycle",
    "variant_lifecycle",
    "reader_visible_lifecycle",
    "embedded_structured_lifecycle",
    "lifecycle_evidence_state",
    "effective_lifecycle",
    "negative_claim_evidence",
    "product_specific_recall_query_gate",
    "manufacturer_sales_state",
    "portfolio_candidate_disposition",
    "portfolio_candidate_reason",
    "route_article_id",
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
_EVIDENCE_LEVEL_LABELS: Final = {
    "A": "公式確認済み",
    "B": "第三者による実測",
    "C": "利用者情報の傾向",
    "D": "編集者による条件整理",
    "UNKNOWN": "未確認",
}


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


def _finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        _fail()
    return parsed


def _reject_constant(value: str) -> NoReturn:
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
            parse_float=_finite_float,
            parse_constant=_reject_constant,
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


def _display_date(value: object) -> str:
    parsed = date.fromisoformat(_date(value))
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


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
                **{
                    "claim_id": claim["claim_id"],
                    "classification": claim["classification"],
                    "statement": claim["statement"],
                    "status": claim["status"],
                    "subject_product_ids": claim["subject_product_ids"],
                },
                **{
                    key: claim[key]
                    for key in _SOURCE_CAPTURE_CLAIM_OPTIONAL_KEYS
                    if key in claim
                },
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


def _source_inventory_sha256(
    sources: Mapping[str, Mapping[str, object]],
) -> str:
    return canonical_sha256(
        sorted(
            (
                {"source_ref": source_ref, "url": source["url"]}
                for source_ref, source in sources.items()
            ),
            key=lambda value: cast(str, value["source_ref"]),
        )
    )


def _validate_extended_claim_fields(
    claim: Mapping[str, object],
    *,
    article_id: str,
    sources: Mapping[str, Mapping[str, object]],
    evidence_refs: list[str],
    subject_product_ids: list[str],
) -> None:
    market_keys = set(claim) & _MARKET_CLAIM_KEYS
    if market_keys and market_keys != set(_MARKET_CLAIM_KEYS):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if market_keys:
        candidate_id = _text(claim["market_candidate_id"], maximum=300)
        official_url = _source_url(claim["official_url"])
        lifecycle_values = {
            key: _text(claim[key], maximum=100)
            for key in (
                "model_lifecycle",
                "variant_lifecycle",
                "reader_visible_lifecycle",
                "embedded_structured_lifecycle",
                "effective_lifecycle",
            )
        }
        lifecycle_states = {
            "AVAILABLE",
            "PREORDER",
            "PRODUCTION_ENDED",
            "RESTOCK_NOTIFICATION_ONLY",
            "SOLD_OUT",
            "UNKNOWN",
        }
        embedded_states = {"AVAILABLE", "NOT_PRESENT", "SOLD_OUT"}
        evidence_state = _text(claim["lifecycle_evidence_state"], maximum=100)
        if (
            re.fullmatch(r"EXT-[A-Z0-9]+(?:-[A-Z0-9]+)*", candidate_id) is None
            or claim["market_disposition"] not in {"DEFERRED", "EXCLUDED"}
            or not _text(claim["exact_model"], maximum=500)
            or not _text(claim["exact_variant_scope"], maximum=500)
            or _date(claim["evaluated_at"]) != claim["evaluated_at"]
            or any(
                lifecycle_values[key] not in lifecycle_states
                for key in (
                    "model_lifecycle",
                    "variant_lifecycle",
                    "reader_visible_lifecycle",
                    "effective_lifecycle",
                )
            )
            or lifecycle_values["embedded_structured_lifecycle"]
            not in embedded_states
            or evidence_state not in {
                "CONFLICT",
                "CONSISTENT",
                "READER_VISIBLE_ONLY",
            }
            or lifecycle_values["effective_lifecycle"]
            != lifecycle_values["reader_visible_lifecycle"]
            or (
                evidence_state == "READER_VISIBLE_ONLY"
                and lifecycle_values["embedded_structured_lifecycle"] != "NOT_PRESENT"
            )
            or (
                evidence_state == "CONFLICT"
                and (
                    lifecycle_values["embedded_structured_lifecycle"] == "NOT_PRESENT"
                    or lifecycle_values["embedded_structured_lifecycle"]
                    == lifecycle_values["reader_visible_lifecycle"]
                )
            )
            or (
                evidence_state == "CONSISTENT"
                and (
                    lifecycle_values["embedded_structured_lifecycle"]
                    == "NOT_PRESENT"
                    or lifecycle_values["embedded_structured_lifecycle"]
                    != lifecycle_values["reader_visible_lifecycle"]
                )
            )
            or subject_product_ids
            or official_url
            not in {cast(str, sources[source_ref]["url"]) for source_ref in evidence_refs}
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)

    portfolio_reference_keys = set(claim) & _PORTFOLIO_REFERENCE_CLAIM_KEYS
    if (
        portfolio_reference_keys
        and portfolio_reference_keys != set(_PORTFOLIO_REFERENCE_CLAIM_KEYS)
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    if portfolio_reference_keys:
        reason = _text(claim["portfolio_candidate_reason"], maximum=2000)
        route_article_id = _text(claim["route_article_id"], maximum=300)
        claim_id = _text(claim["claim_id"], maximum=300)
        expected_reference = _PORTFOLIO_REFERENCE_CLAIMS.get(claim_id)
        if (
            claim["portfolio_candidate_disposition"] != "REFERENCE_ONLY"
            or not reason
            or reason not in _text(claim["statement"], maximum=4000)
            or route_article_id not in _SOURCE_PACKET_ARTICLE_IDS
            or route_article_id == article_id
            or len(subject_product_ids) != 1
            or market_keys
            or expected_reference
            != (article_id, subject_product_ids[0], route_article_id)
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)

    if "negative_claim_evidence" in claim:
        negative = _mapping(claim["negative_claim_evidence"])
        _exact(
            negative,
            {"mode", "page_omission_is_not_evidence", "source_refs"},
        )
        negative_refs = [
            _text(value, maximum=300) for value in _list(negative["source_refs"])
        ]
        if (
            negative["mode"]
            not in {
                "EXPLICIT_OFFICIAL_TEXT",
                "OFFICIAL_COMPARISON_TABLE",
                "OFFICIAL_MANUAL",
            }
            or negative["page_omission_is_not_evidence"] is not True
            or not negative_refs
            or len(negative_refs) != len(set(negative_refs))
            or any(source_ref not in evidence_refs for source_ref in negative_refs)
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)

    if "product_specific_recall_query_gate" in claim:
        gate = _mapping(claim["product_specific_recall_query_gate"])
        _exact(
            gate,
            {
                "coverage_caveat",
                "general_safety_guidance_is_not_a_receipt",
                "receipt_document_ref",
                "receipt_document_schema",
                "required_authority_kinds",
                "required_product_ids",
                "schema",
            },
        )
        required_product_ids = [
            _text(value, maximum=300)
            for value in _list(gate["required_product_ids"])
        ]
        if (
            gate["schema"] != "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2"
            or gate["required_authority_kinds"]
            != ["MANUFACTURER_OFFICIAL", "JAPAN_ADMINISTRATIVE_OFFICIAL"]
            or gate["receipt_document_ref"]
            != (
                "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
                "product-safety-query-receipts.v1.json"
            )
            or gate["receipt_document_schema"]
            != "RAOS_PRODUCT_SAFETY_QUERY_RECEIPTS_V1"
            or gate["general_safety_guidance_is_not_a_receipt"] is not True
            or not _text(gate["coverage_caveat"], maximum=1000)
            or not required_product_ids
            or len(required_product_ids) != len(set(required_product_ids))
            or any(
                re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id) is None
                for product_id in required_product_ids
            )
            or not set(subject_product_ids) <= set(required_product_ids)
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)

    if "manufacturer_sales_state" in claim:
        sales = _mapping(claim["manufacturer_sales_state"])
        status = _text(sales.get("status"), maximum=100)
        common_keys = {
            "checked_at",
            "exact_variant",
            "reader_visible_label",
            "source_ref",
            "status",
        }
        expected_keys = (
            common_keys | {"product_id", "selection_gate", "variant_caveat"}
            if status == "AVAILABLE"
            else common_keys | {"cta_gate", "recommendation_gate"}
        )
        _exact(sales, expected_keys)
        checked_at = _text(sales["checked_at"], maximum=100)
        try:
            parsed_checked_at = datetime.fromisoformat(
                checked_at.removesuffix("Z") + "+00:00"
            )
        except (OverflowError, ValueError):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        source_ref = _text(sales["source_ref"], maximum=300)
        variant_caveat = sales.get("variant_caveat")
        if variant_caveat is not None:
            caveat = _mapping(variant_caveat)
            _exact(
                caveat,
                {"code", "detail", "establishes_exact_rakuten_variant"},
            )
            if (
                caveat["code"]
                not in {"OTHER_COLOR_NOT_ATTESTED", "STANDARD_PRODUCT_ONLY"}
                or not _text(caveat["detail"], maximum=1000)
                or caveat["establishes_exact_rakuten_variant"] is not False
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        if (
            not checked_at.endswith("Z")
            or parsed_checked_at.tzinfo is None
            or not _text(sales["exact_variant"], maximum=500)
            or not _text(sales["reader_visible_label"], maximum=300)
            or source_ref not in evidence_refs
            or (
                status == "AVAILABLE"
                and (
                    sales["selection_gate"] != "ELIGIBLE"
                    or _text(sales["product_id"], maximum=300)
                    not in subject_product_ids
                )
            )
            or (
                status == "OUT_OF_STOCK"
                and (
                    sales["recommendation_gate"] != "BLOCKED"
                    or sales["cta_gate"] != "BLOCKED"
                )
            )
            or status not in {"AVAILABLE", "OUT_OF_STOCK"}
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)


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
    if (
        _source_inventory_sha256(sources) != _PRODUCT_SOURCE_INVENTORY_SHA256
        or _source_inventory_sha256(policy_sources)
        != _POLICY_SOURCE_INVENTORY_SHA256
    ):
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
    if len(affiliates) != 21 or len(
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
        if (
            affiliate["status"] != "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE"
            or affiliate["destination_url"] is not None
            or affiliate["evidence"] is not None
            or affiliate["publication_blocker"] != "PENDING_AFFILIATE_EVIDENCE"
        ):
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
            claim_keys = set(claim)
            if (
                not _CLAIM_BASE_KEYS <= claim_keys
                or not claim_keys <= _CLAIM_BASE_KEYS | _CLAIM_OPTIONAL_KEYS
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            subject_product_ids = [
                _text(value, maximum=300)
                for value in _list(claim["subject_product_ids"])
            ]
            if len(subject_product_ids) != len(set(subject_product_ids)) or any(
                re.fullmatch(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*", product_id) is None
                for product_id in subject_product_ids
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            for raw_dimensions in _list(claim.get("dimensions", [])):
                dimensions = _mapping(raw_dimensions)
                _exact(
                    dimensions,
                    {"depth_cm", "height_cm", "subject", "width_cm"},
                )
                if (
                    not _text(dimensions["subject"], maximum=300)
                    or any(
                        type(dimensions[axis]) not in {int, float}
                        or cast(float, dimensions[axis]) <= 0
                        for axis in ("width_cm", "depth_cm", "height_cm")
                    )
                ):
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            claim_id = _text(claim["claim_id"], maximum=300)
            if (
                re.fullmatch(r"CLM-[A-Z0-9]+(?:-[A-Z0-9]+)*", claim_id) is None
                or not _text(claim["statement"], maximum=4000)
                or claim_id in all_claims
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            evidence_refs = [
                _text(value, maximum=300) for value in _list(claim["evidence_refs"])
            ]
            if (
                not evidence_refs
                or len(evidence_refs) != len(set(evidence_refs))
                or any(value not in packet_refs for value in evidence_refs)
            ):
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            _validate_extended_claim_fields(
                claim,
                article_id=_text(packet["article_id"], maximum=300),
                sources=sources,
                evidence_refs=evidence_refs,
                subject_product_ids=subject_product_ids,
            )
            classification = claim["classification"]
            evidence_level = claim["evidence_level"]
            status = claim["status"]
            if classification == "MAJOR_VERIFIABLE":
                verifiable_count += 1
                if (
                    evidence_level != "A"
                    or status != "BOUND_TO_OFFICIAL_SOURCE"
                ):
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            elif classification == "EDITORIAL_INFERENCE":
                if (
                    evidence_level != "D"
                    or status != "INFERENCE_FROM_BOUND_OFFICIAL_FACTS"
                ):
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            elif classification == "DECISION_CRITICAL_UNKNOWN":
                if (
                    evidence_level != "UNKNOWN"
                    or status != "UNCONFIRMED_FROM_BOUND_OFFICIAL_SOURCE"
                ):
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            else:
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
    portfolio_reference_claim_ids = {
        claim_id
        for claim_id, claim in all_claims.items()
        if set(claim) & _PORTFOLIO_REFERENCE_CLAIM_KEYS
    }
    if portfolio_reference_claim_ids != set(_PORTFOLIO_REFERENCE_CLAIMS):
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
    if len(assets) != 21 or len(
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
            _date(editorial_facts_checked_on)
            capture_floor = source_observed_on
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
    *,
    facts_checked_on: str,
) -> tuple[
    dict[str, Mapping[str, object]],
    dict[str, RakutenProductEvidence],
    list[Mapping[str, object]],
    list[Mapping[str, object]],
]:
    _date(facts_checked_on)
    render = _mapping(article["render_model"])
    render_keys = set(_RENDER_KEYS)
    render_keys.add("presentation")
    _exact(render, render_keys)
    presentation_map = _mapping(render["presentation"])
    _exact(
        presentation_map,
        {
            "fact_checker",
            "first_hand_test",
            "reader_summary",
            "scope_label",
            "scope_note",
        },
    )
    for value in presentation_map.values():
        _text(value, maximum=1000)
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
    base_card_keys = {
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
    }
    cards: dict[str, Mapping[str, object]] = {}
    for raw_card in _list(render["product_cards"]):
        card = _mapping(raw_card)
        card_keys = set(base_card_keys)
        card_keys.add("presentation_v2")
        _exact(card, card_keys)
        card_ref = _text(card["product_selection_ref"], maximum=300)
        if card_ref in cards:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        cards[card_ref] = card
    evidences: dict[str, RakutenProductEvidence] = {}
    affiliate_records: list[Mapping[str, object]] = []
    media_records: list[Mapping[str, object]] = []
    detail_anchors: set[str] = set()
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
        card_presentation = _mapping(card["presentation_v2"])
        _exact(
            card_presentation,
            {
                "benefit",
                "cta_context",
                "detail_anchor",
                "facts_checked_on",
                "fits",
                "not_fits",
                "official_source_ref",
                "recommendation_reason",
            },
        )
        benefit = _text(card_presentation["benefit"], maximum=2000)
        _text(card_presentation["cta_context"], maximum=2000)
        recommendation_reason = _text(
            card_presentation["recommendation_reason"], maximum=2000
        )
        if benefit == recommendation_reason:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        presentation_lists: dict[str, list[str]] = {}
        for key in ("fits", "not_fits"):
            values = _list(card_presentation[key])
            if not values:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            presentation_lists[key] = [
                _text(value, maximum=1000) for value in values
            ]
        if _text(card["caution"], maximum=2000) in presentation_lists["not_fits"]:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        _date(card_presentation["facts_checked_on"])
        official_source_ref = _text(
            card_presentation["official_source_ref"], maximum=300
        )
        detail_anchor = _text(card_presentation["detail_anchor"], maximum=80)
        if (
            official_source_ref not in source_refs
            or re.fullmatch(r"[a-z][a-z0-9-]{2,79}", detail_anchor) is None
            or detail_anchor in detail_anchors
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        detail_anchors.add(detail_anchor)
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
            or (
                identity.get("jan") is not None
                and evidence.jan is not None
                and identity.get("jan") != evidence.jan
            )
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


_ARTICLE_SECTION_HEADINGS: Final[Mapping[str, Mapping[str, str]]] = {
    "st1703-first-suitcase-comparison": {
        "decision_summary": "軽さ・容量・開き方で分ける",
        "intended_reader": "機内持ち込み候補を絞れる人・絞れない人",
        "methodology": "外寸・容量・開き方を同じ条件で比べる",
        "selection_criteria": "機内持ち込み候補を絞る4条件",
        "comparison_table": "3モデルの外寸・容量・開き方",
        "product_cards": "3モデルを条件別に見る",
        "caution": "便・機材・運賃種別を最後に確認する",
    },
    "st1704-portable-power-station-guide": {
        "decision_summary": "使う機器・必要時間・運べる重さで分ける",
        "intended_reader": "停電時の使い方から候補を絞る",
        "methodology": "容量・定格出力・重量を同じ条件で比べる",
        "selection_criteria": "使う機器から必要容量を決める",
        "comparison_table": "7モデルの容量・各社公表出力・重量",
        "product_cards": "容量帯ごとの向き・不向き",
        "caution": "接続機器・保管・安全条件を最後に確認する",
    },
    "st1704-anker-solix-c300-c800-c1000-differences": {
        "decision_summary": "容量・定格出力・世代差で分ける",
        "intended_reader": "Anker Solix 4モデルの違いを整理する",
        "methodology": "型番・世代・拡張互換を分けて比べる",
        "selection_criteria": "用途からAnker Solixを絞る",
        "comparison_table": "C300・C800 Plus・C1000 2世代の仕様差",
        "product_cards": "4モデルの向き・互換性・注意点",
        "caution": "型番・拡張互換・安全条件を最後に確認する",
    },
    "st1704-countertop-dishwasher-for-small-households": {
        "decision_summary": "置ける寸法・洗う点数・乾燥方式で分ける",
        "intended_reader": "少人数向けタンク式食洗機を選ぶ前提",
        "methodology": "設置寸法・食器点数・乾燥方式を比べる",
        "selection_criteria": "置き場所と食器量から絞る",
        "comparison_table": "4モデルの設置寸法・容量・給水方式",
        "product_cards": "4モデルの設置条件と注意点",
        "caution": "給排水・扉・耐熱条件を最後に確認する",
    },
    "st1704-compact-robot-vacuum-shortlist": {
        "decision_summary": "設置寸法と手入れ範囲で分ける",
        "intended_reader": "本体・ステーション・帰還余白を確認する",
        "methodology": "本体・ステーション・設置余白を分けて比べる",
        "selection_criteria": "置き場所と手入れ負担から絞る",
        "comparison_table": "4モデルの本体・ステーション寸法",
        "product_cards": "4モデルの設置条件と手入れ範囲",
        "caution": "帰還余白・段差・アプリ条件を最後に確認する",
    },
}


def _article_section_heading(
    article: Mapping[str, object], section: str, fallback: str
) -> str:
    article_id = _text(article.get("article_id"), maximum=300)
    return _ARTICLE_SECTION_HEADINGS.get(article_id, {}).get(section, fallback)


@final
class _Renderer:
    __slots__ = (
        "article",
        "alts",
        "axes",
        "cards",
        "claims",
        "evidences",
        "facts_checked_on",
        "model",
        "product_media_verified",
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
        claims: Mapping[str, Mapping[str, object]],
        cards: Mapping[str, Mapping[str, object]],
        evidences: Mapping[str, RakutenProductEvidence],
        alts: Mapping[str, str],
        facts_checked_on: str,
        product_media_verified: bool = True,
    ) -> None:
        self.article = article
        self.routes = routes
        self.sources = sources
        self.claims = claims
        self.cards = cards
        self.evidences = evidences
        self.alts = alts
        self.facts_checked_on = _date(facts_checked_on)
        self.product_media_verified = product_media_verified
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

    def evidence_badges(self, claim_ids: object) -> str:
        raw_ids = _list(claim_ids)
        if not raw_ids:
            levels = ["UNKNOWN"]
        else:
            observed: set[str] = set()
            for raw_id in raw_ids:
                claim_id = _text(raw_id, maximum=300)
                claim = self.claims.get(claim_id)
                if claim is None:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                level = _text(claim["evidence_level"], maximum=20)
                if level not in _EVIDENCE_LEVEL_LABELS:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                observed.add(level)
            levels = sorted(observed)
        return "".join(
            '<span class="raos-evidence-badge" data-raos-evidence-level="'
            + escape(level, quote=True)
            + '">'
            + escape(_EVIDENCE_LEVEL_LABELS[level])
            + "</span>"
            for level in levels
        )

    def comparison_cell_badges(self, cell: Mapping[str, object]) -> str:
        state = _text(cell["state"], maximum=20)
        claim_ids = _list(cell["claim_ids"])
        if state == "KNOWN":
            if not claim_ids:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            return self.evidence_badges(claim_ids)
        if state != "UNKNOWN":
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        badges = self.evidence_badges(claim_ids)
        if claim_ids:
            badges += (
                '<span class="raos-evidence-badge" '
                'data-raos-evidence-level="UNKNOWN">軸未確認</span>'
            )
        return badges

    def article_facts(self) -> str:
        values = _mapping(self.model["presentation"])
        return (
            '<dl class="raos-article-facts article-meta">'
            "<div><dt>対象読者</dt><dd>"
            + escape(cast(str, values["reader_summary"]))
            + "</dd></div><div><dt>比較範囲</dt><dd>"
            + escape(cast(str, values["scope_label"]))
            + "</dd></div><div><dt>執筆担当</dt><dd>暮らしのしるべ編集者</dd></div>"
            + "<div><dt>事実確認担当</dt><dd>"
            + escape(cast(str, values["fact_checker"]))
            + "</dd></div><div><dt>最終確認日</dt><dd>"
            + escape(_display_date(self.facts_checked_on))
            + "</dd></div><div><dt>実機確認</dt><dd>"
            + escape(cast(str, values["first_hand_test"]))
            + "</dd></div></dl>"
        )

    def article_scope(self) -> str:
        values = _mapping(self.model["presentation"])
        return (
            '<p class="raos-article-scope"><strong>比較範囲：'
            + escape(cast(str, values["scope_label"]))
            + "。</strong>"
            + escape(cast(str, values["scope_note"]))
            + "。</p>"
        )

    def card(self, product_selection_ref: str, *, alternate: bool) -> str:
        card = self.cards.get(product_selection_ref)
        if card is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        product_id = cast(str, card["product_id"])
        evidence = self.evidences[product_id]
        facts = "".join(
            "<div><dt>"
            + escape(_text(_mapping(raw)["label"], maximum=200))
            + "</dt><dd>"
            + escape(_text(_mapping(raw)["value"], maximum=1000))
            + self.evidence_badges(_mapping(raw)["claim_ids"])
            + "</dd></div>"
            for raw in _list(card["confirmed_facts"])
        )
        presentation = _mapping(card["presentation_v2"])
        source = self.sources.get(cast(str, presentation["official_source_ref"]))
        if source is None:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        card_source_dates: list[str] = []
        for raw_source_ref in _list(card["source_refs"]):
            card_source = self.sources.get(_text(raw_source_ref, maximum=300))
            if card_source is None:
                _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            card_source_dates.append(_date(card_source["retrieved_on"]))
        card_checked_on = _date(presentation["facts_checked_on"])
        if (
            not card_source_dates
            or card_checked_on < max(card_source_dates)
            or card_checked_on > self.facts_checked_on
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        detail_anchor = cast(str, presentation["detail_anchor"])
        cta_context_id = f"{detail_anchor}-cta-note"
        fits = "".join(
            f"<li>{escape(_text(value, maximum=1000))}</li>"
            for value in _list(presentation["fits"])
        )
        not_fits = "".join(
            f"<li>{escape(_text(value, maximum=1000))}</li>"
            for value in _list(presentation["not_fits"])
        )
        profile_variant = "product-profile--b" if alternate else "product-profile--a"
        condition_label = cast(str, card["condition_label"])
        reason_label = (
            "仕様上の比較ポイント："
            if any(
                marker in condition_label
                for marker in ("在庫切れ", "販売状態未確認")
            )
            else "おすすめする理由："
        )
        if self.product_media_verified:
            product_media = (
                f'<img src="{escape(evidence.image_url, quote=True)}" '
                f'alt="{escape(self.alts[product_id], quote=True)}" '
                'width="128" height="128" loading="lazy" decoding="async" '
                f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
                'data-raos-product-image-placement="product_card" '
                'data-raos-product-image-state="verified">'
            )
        else:
            product_media = (
                '<p class="raos-product-image-status" '
                f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
                'data-raos-product-image-placement="product_card" '
                'data-raos-product-image-state="unverified">'
                "商品画像未確認・購入導線停止</p>"
            )
        return (
            f'<article id="{escape(detail_anchor, quote=True)}" '
            f'class="raos-product-card product-profile {profile_variant}" '
            f'data-raos-product-id="{escape(product_id, quote=True)}">'
            '<div class="raos-product-card__media">'
            f"{product_media}"
            "</div>"
            '<div class="raos-product-card__body product-profile__body">'
            f"<h3>{escape(cast(str, card['product_name']))}</h3>"
            f'<p class="raos-condition-label">{escape(cast(str, card["condition_label"]))}</p>'
            f'<p class="raos-product-card__lead">{escape(cast(str, presentation["benefit"]))}</p>'
            f"<p><strong>{reason_label}</strong>"
            f'{escape(cast(str, presentation["recommendation_reason"]))}</p>'
            f'<dl class="raos-product-card__facts">{facts}</dl>'
            f'<div class="raos-product-card__fit"><strong>合いやすい条件</strong><ul>{fits}</ul>'
            f'<strong>別の候補も検討したい条件</strong><ul>{not_fits}</ul></div>'
            f'<p id="{escape(detail_anchor, quote=True)}-caution" class="raos-product-card__caution">'
            f'<strong>注意点：</strong>{escape(cast(str, card["caution"]))}</p>'
            '<p class="raos-source-link">情報確認日 '
            f'{escape(_display_date(card_checked_on))}・'
            f'<a href="{escape(cast(str, source["url"]), quote=True)}">公式サイトで仕様を確認する</a></p>'
            '<div class="raos-product-card__actions">'
            f'<p id="{escape(cta_context_id, quote=True)}" class="raos-cta-context cta-note">'
            f'{escape(cast(str, presentation["cta_context"]))}</p>'
            '<p class="summary-action">'
            f'<a class="raos-cta rakuten-cta" href="{escape(evidence.destination_url, quote=True)}" '
            'rel="sponsored nofollow" '
            f'aria-describedby="{escape(cta_context_id, quote=True)}" '
            f'data-raos-article-id="{escape(cast(str, self.article["article_id"]), quote=True)}" '
            f'data-raos-product-id="{escape(product_id, quote=True)}" '
            f'data-raos-placement="product_card">{PILOT_CTA_LABEL}</a></p></div>'
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
        raw_rows = [_mapping(value) for value in _list(table["rows"])]
        difference_axes = {
            ref: len(
                {
                    cast(str, _mapping(value)["value"])
                    for row in raw_rows
                    for value in _list(row["cells"])
                    if _mapping(value).get("axis_ref") == ref
                }
            )
            > 1
            for ref in axis_refs
        }
        rows: list[str] = []
        mobile_cards: list[str] = []
        observed_products: list[str] = []
        for row in raw_rows:
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
                '<td data-raos-difference="'
                + ("true" if difference_axes[ref] else "false")
                + '"><span>'
                + escape(cast(str, cells[ref]["value"]))
                + "</span>"
                + self.comparison_cell_badges(cells[ref])
                + "</td>"
                for ref in axis_refs
            )
            product_id = cast(str, card["product_id"])
            evidence = self.evidences[product_id]
            if self.product_media_verified:
                comparison_media = (
                    '<img class="raos-comparison__product-image" '
                    f'src="{escape(evidence.image_url, quote=True)}" '
                    f'alt="{escape(cast(str, card["product_name"]))}の商品画像" '
                    'width="64" height="64" loading="lazy" decoding="async" '
                    f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
                    'data-raos-product-image-placement="comparison_table" '
                    'data-raos-product-image-state="verified">'
                )
            else:
                comparison_media = (
                    '<span class="raos-product-image-status '
                    'raos-product-image-status--compact" '
                    f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
                    'data-raos-product-image-placement="comparison_table" '
                    'data-raos-product-image-state="unverified">'
                    "商品画像未確認・購入導線停止</span>"
                )
            rows.append(
                '<tr class="has-difference"><th scope="row">'
                f"{comparison_media}<span>"
                f'{escape(cast(str, card["product_name"]))}</span></th>'
                f"{rendered_cells}</tr>"
            )
            mobile_pairs = [
                '<div><dt>商品</dt><dd>'
                + comparison_media
                + "<span>"
                + escape(cast(str, card["product_name"]))
                + "</span></dd></div>"
            ]
            mobile_pairs.extend(
                "<div><dt>"
                + escape(cast(str, self.axes[ref]["label"]))
                + "</dt><dd>"
                + escape(cast(str, cells[ref]["value"]))
                + self.comparison_cell_badges(cells[ref])
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
        row_checked_dates = [
            _date(
                _mapping(self.cards[product_ref]["presentation_v2"])[
                    "facts_checked_on"
                ]
            )
            for product_ref in observed_products
        ]
        if not row_checked_dates:
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
        first_checked_on = _display_date(min(row_checked_dates))
        last_checked_on = _display_date(max(row_checked_dates))
        facts_checked_on = (
            first_checked_on
            if first_checked_on == last_checked_on
            else f"{first_checked_on}〜{last_checked_on}"
        )
        return (
            '<section class="comparison-section">'
            '<header class="section-heading section-heading--inline"><div>'
            f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "comparison_table", "公表仕様を比べる"))}</h2></div>'
            f'<p class="raos-comparison__checked">一次情報の取得期間：{escape(facts_checked_on)}。'
            "価格・在庫・カラーは候補の順序に反映していません。</p></header>"
            f'<div class="raos-comparison comparison-table-wrap" role="region" aria-labelledby="{title_id}" '
            f'data-raos-article-id="{escape(cast(str, self.article["article_id"]), quote=True)}" '
            'data-raos-placement="comparison_table">'
            '<div class="raos-comparison__table-view">'
            f'<table class="comparison-table"><caption>{escape(cast(str, table["caption"]))}</caption>'
            f'<thead><tr><th scope="col">商品</th>{header}</tr></thead>'
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            '<div class="comparison-cards"><div class="raos-comparison__cards">'
            f"{''.join(mobile_cards)}</div></div></div></section>"
        )

    def recommendation_group(self, block: Mapping[str, object]) -> str:
        items: list[str] = []
        for position, raw_ref in enumerate(_list(block["recommendation_refs"]), start=1):
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
            rationale = _text(recommendation["rationale"], maximum=2000)
            if not rationale.endswith(("。", "！", "？")):
                rationale += "。"
            items.append(
                "<li>"
                f'<span class="decision-list__number" aria-hidden="true">{position:02d}</span>'
                "<div><small>"
                f"{escape(cast(str, recommendation['condition']))}</small>"
                f"<strong>{escape(cast(str, card['product_name']))}</strong></div>"
                f'<p class="summary-reason">{escape(rationale)}</p>'
                '<p class="summary-action">'
                f'<a class="raos-cta rakuten-cta" href="{escape(evidence.destination_url, quote=True)}" '
                'rel="sponsored nofollow" '
                f'data-raos-article-id="{escape(cast(str, self.article["article_id"]), quote=True)}" '
                f'data-raos-product-id="{escape(product_id, quote=True)}" '
                f'data-raos-placement="final_summary">{PILOT_CTA_LABEL}</a></p>'
                "</li>"
            )
        title_id = f"{cast(str, block['block_id']).lower()}-title"
        return (
            f'<section class="raos-decision-summary decision-section" aria-labelledby="{title_id}">'
            '<header class="section-heading">'
            f'<h2 id="{title_id}">{escape(cast(str, block["label"]))}</h2>'
            f"<p>{self.rich(block['condition'])}</p></header>"
            f'<ol class="decision-list">{"".join(items)}</ol></section>'
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
                if index + 1 >= len(blocks) or blocks[index + 1].get("type") != "lead":
                    _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
                lead_parts = self.rich(blocks[index + 1]["content"]).split("<br>")
                if len(lead_parts) not in {2, 3} or any(
                    not value.strip() for value in lead_parts
                ):
                    _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
                scope_paragraphs = "".join(
                    f'<p class="raos-article-intro__scope">{part}</p>'
                    for part in lead_parts[1:]
                )
                output.append(
                    '<section class="raos-article-intro" aria-label="比較の要点">'
                    f'<p class="raos-article-intro__hook">{lead_parts[0]}</p>'
                    f"{scope_paragraphs}"
                    "</section>"
                )
                disclosure = _mapping(self.model["disclosure"])
                _exact(disclosure, {"label", "paragraphs"})
                paragraphs = "".join(
                    f"<p>{escape(_text(value))}</p>"
                    for value in _list(disclosure["paragraphs"])
                )
                output.append(self.article_facts())
                output.append(
                    '<aside class="raos-disclosure disclosure" aria-label="広告表示">'
                    "<strong>広告・アフィリエイト開示</strong><div>"
                    "<p>広告を含みます。購入リンクから成果報酬を受け取る場合がありますが、"
                    "選定・掲載順には使いません。</p>"
                    f"<details><summary>{escape(cast(str, disclosure['label']))}の詳細</summary>"
                    f"{paragraphs}<p><a href=\"/comparison-policy/\">"
                    "編集・比較方針（AI支援範囲を含む）を確認する"
                    "</a></p></details></div></aside>"
                )
                output.append(self.article_scope())
                index += 1
            elif kind == "lead":
                _fail(EditorialPilotFailureCode.CONTENT_AST_INVALID)
            elif kind == "decision_summary":
                rendered_items: list[str] = []
                for position, raw in enumerate(_list(block["items"]), start=1):
                    item = _mapping(raw)
                    recommendation = self.recommendations.get(
                        cast(str, item["recommendation_ref"])
                    )
                    if recommendation is None:
                        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                    card = self.cards.get(
                        cast(str, recommendation["product_selection_ref"])
                    )
                    if card is None:
                        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                    presentation = _mapping(card["presentation_v2"])
                    detail_anchor = cast(str, presentation["detail_anchor"])
                    rendered_items.append(
                        '<li><span class="decision-list__number" aria-hidden="true">'
                        + f"{position:02d}"
                        + "</span><div><small>"
                        + escape(cast(str, item["condition"]))
                        + '</small><strong class="raos-decision-summary__product">'
                        + escape(cast(str, card["product_name"]))
                        + "</strong></div><p>"
                        + self.rich(item["summary"])
                        + self.evidence_badges(item["claim_ids"])
                        + '<br><strong>注意点：</strong>'
                        + escape(cast(str, card["caution"]))
                        + '</p><a class="raos-decision-summary__link" href="#'
                        + escape(detail_anchor, quote=True)
                        + '">詳しい理由と注意点を読む</a></li>'
                    )
                title_id = f"{cast(str, block['block_id']).lower()}-title"
                output.append(
                    f'<section class="raos-decision-summary decision-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading">'
                    f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "decision_summary", "条件ごとの結論"))}</h2></header>'
                    f'<ol class="decision-list">{"".join(rendered_items)}</ol></section>'
                )
            elif kind == "intended_reader":
                title_id = f"{cast(str, block['block_id']).lower()}-title"
                output.append(
                    f'<section class="reader-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading">'
                    f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "intended_reader", "この記事でわかること"))}</h2></header>'
                    '<div class="reader-columns"><section><h3>この比較が役立つ人</h3>'
                    f"<ul>{_list_html(block['fits'], routes=self.routes, sources=self.sources)}</ul></section>"
                    '<section><h3>この比較だけでは決めにくい人</h3>'
                    f"<ul>{_list_html(block['not_fits'], routes=self.routes, sources=self.sources)}</ul></section>"
                    '<section><h3>購入前の前提</h3>'
                    f"<ul>{_list_html(block['assumptions'], routes=self.routes, sources=self.sources)}</ul>"
                    "</section></div></section>"
                )
            elif kind == "methodology":
                title_id = f"{cast(str, block['block_id']).lower()}-title"
                checked_at = _text(block["data_checked_at"], maximum=64)
                _date(checked_at[:10])
                output.append(
                    f'<section class="method-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading section-heading--side">'
                    f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "methodology", "比較のしかた"))}</h2>'
                    f"<p>{self.rich(block['candidate_universe_summary'])}</p></header><div>"
                    "<h3>比較対象にした条件</h3>"
                    f"<ul>{_list_html(block['inclusion_rules'], routes=self.routes, sources=self.sources)}</ul>"
                    "<h3>比較に含めていないもの</h3>"
                    f"<ul>{_list_html(block['exclusion_rules'], routes=self.routes, sources=self.sources)}</ul>"
                    f'<p class="table-note">編集内容の最終確認日：{escape(_display_date(self.facts_checked_on))}</p>'
                    "</div></section>"
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
                title_id = f"{cast(str, block['block_id']).lower()}-title"
                output.append(
                    f'<section class="method-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading section-heading--side">'
                    f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "selection_criteria", "選ぶ前に確認するポイント"))}</h2></header>'
                    f"<ul>{criteria}</ul></section>"
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
            elif kind == "comparison_table":
                output.append(self.comparison(block))
            elif kind == "product_card":
                product_blocks: list[Mapping[str, object]] = []
                while (
                    index < len(blocks) and blocks[index].get("type") == "product_card"
                ):
                    product_blocks.append(blocks[index])
                    index += 1
                title_id = f"{cast(str, product_blocks[0]['block_id']).lower()}-title"
                output.append(
                    f'<section class="products-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading">'
                    f'<h2 id="{title_id}">{escape(_article_section_heading(self.article, "product_cards", "候補ごとの特徴と注意点"))}</h2></header>'
                    '<div class="raos-product-grid">'
                    + "".join(
                        self.card(
                            cast(str, value["product_selection_ref"]),
                            alternate=position % 2 == 1,
                        )
                        for position, value in enumerate(product_blocks)
                    )
                    + "</div></section>"
                )
                continue
            elif kind == "tradeoff":
                card = self.cards.get(cast(str, block["subject_ref"]))
                if card is None:
                    _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
            elif kind == "recommendation_group":
                output.append(self.recommendation_group(block))
            elif kind == "caution":
                caution_content = _list(block["content"])
                if len(caution_content) == 1:
                    caution_body = f"<p>{self.rich(caution_content)}</p>"
                else:
                    caution_body = "<ul>" + "".join(
                        f"<li>{self.rich([node])}</li>" for node in caution_content
                    ) + "</ul>"
                output.append(
                    '<aside class="raos-caution purchase-caution"><h2>'
                    f'{escape(_article_section_heading(self.article, "caution", "購入前に確認したいこと"))}</h2>'
                    f"{caution_body}</aside>"
                )
            elif kind == "source_summary":
                refs = [
                    _text(value, maximum=300)
                    for value in _list(self.model["primary_source_refs"])
                ]
                source_links: list[str] = []
                for position, source_ref in enumerate(refs, start=1):
                    source = self.sources.get(source_ref)
                    if source is None:
                        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
                    source_links.append(
                        f'<li><span>{position}</span><p><a class="raos-source-link" '
                        f'href="{escape(cast(str, source["url"]), quote=True)}">'
                        f"{escape(cast(str, source['title']))}</a></p></li>"
                    )
                title_id = f"{cast(str, block['block_id']).lower()}-title"
                output.append(
                    f'<section class="sources-section" aria-labelledby="{title_id}">'
                    '<header class="section-heading section-heading--side">'
                    f'<h2 id="{title_id}">確認に使った一次情報</h2></header><div>'
                    f'<ol class="source-list">{"".join(source_links)}</ol>'
                    f'<p class="raos-source-link"><a href="{PILOT_RAKUTEN_CREDIT_URL}">'
                    f"{PILOT_RAKUTEN_CREDIT_LABEL}</a></p></div></section>"
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
        return '<div class="raos-editorial-v2">\n' + "\n".join(output) + "\n</div>\n"


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


@final
@dataclass(frozen=True, slots=True, repr=False)
class PreparedReviewDraftRevision:
    """Fresh preparation bound to one existing Review Draft generation."""

    prepared: PreparedEditorialArticle
    binding: ReviewDraftRevisionBinding
    network_requests: int = 0
    external_writes: int = 0
    publication_actions: int = 0
    publication_authority: bool = False
    production_evidence: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.prepared) is not PreparedEditorialArticle
            or type(self.binding) is not ReviewDraftRevisionBinding
            or self.prepared.request != self.binding.successor
            or self.prepared.article_id != self.binding.successor.article_id
            or self.network_requests != 0
            or self.external_writes != 0
            or self.publication_actions != 0
            or self.publication_authority is not False
            or self.production_evidence is not False
        ):
            _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)


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
        selected_sources = [
            sources[_text(value, maximum=300)]
            for value in _list(packet["source_refs"])
        ]
    except KeyError:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    facts_checked_on = _date(freshness["facts_checked_on"])
    if any(
        _date(source["retrieved_on"]) > facts_checked_on
        for source in selected_sources
    ):
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    _require_observed_date_not_future(facts_checked_on, now=now)
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
    # External-market and cross-portfolio reference claims are projected by
    # the closed reader ledger rather than duplicated into the authored AST.
    # Their extended fields were validated above, so include exactly that
    # contract-owned projection in the packet coverage set.
    observed_claim_ids.update(
        _text(_mapping(value)["claim_id"], maximum=300)
        for value in _list(packet["claims"])
        if "market_candidate_id" in _mapping(value)
        or "portfolio_candidate_disposition" in _mapping(value)
    )
    if observed_claim_ids != packet_claim_ids:
        _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
    cards, evidences, affiliate_records, media_records = _bind_product_evidence(
        repository_root,
        article,
        affiliates,
        media,
        evidence_reader,
        facts_checked_on=facts_checked_on,
    )
    article_product_ids = {
        _text(card["product_id"], maximum=300) for card in cards.values()
    }
    for raw_claim in _list(packet["claims"]):
        claim = _mapping(raw_claim)
        subject_product_ids = {
            _text(value, maximum=300)
            for value in _list(claim["subject_product_ids"])
        }
        is_portfolio_reference = (
            set(claim) & _PORTFOLIO_REFERENCE_CLAIM_KEYS
        ) == set(_PORTFOLIO_REFERENCE_CLAIM_KEYS)
        if (
            not subject_product_ids <= article_product_ids
            and not is_portfolio_reference
        ):
            _fail(EditorialPilotFailureCode.RESOURCE_REFERENCE_INVALID)
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
        claims=all_registry_claims,
        cards=cards,
        evidences=evidences,
        alts={
            cast(str, asset["product_id"]): cast(str, asset["alt"])
            for asset in media_records
        },
        facts_checked_on=facts_checked_on,
    ).render(ast)
    content_sha256 = bytes_sha256(content.encode("utf-8", errors="strict"))
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
        editorial_facts_checked_on=facts_checked_on,
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


def prepare_review_draft_revision(
    repository_root: Path,
    *,
    predecessor: ReviewDraftRequest,
    draft_id: int,
    generation: int,
    evidence_reader: Callable[..., RakutenProductEvidence] = (
        read_rakuten_product_evidence
    ),
    source_evidence_reader: Callable[..., OfficialSourceCaptureEvidence] = (
        read_official_source_capture_evidence
    ),
    clock: Callable[[], datetime] = _utc_now,
) -> PreparedReviewDraftRevision:
    """Prepare fresh evidence and bind it to an unchanged existing Draft ID."""

    if type(predecessor) is not ReviewDraftRequest:
        _fail(EditorialPilotFailureCode.JOURNAL_MISMATCH)
    prepared = prepare_editorial_article(
        repository_root,
        predecessor.article_id,
        evidence_reader=evidence_reader,
        source_evidence_reader=source_evidence_reader,
        clock=clock,
    )
    binding = ReviewDraftRevisionBinding.bind(
        predecessor=predecessor,
        successor=prepared.request,
        draft_id=draft_id,
        generation=generation,
    )
    return PreparedReviewDraftRevision(prepared=prepared, binding=binding)


__all__ = [
    "ARTICLE_FACT_MAX_AGE_DAYS",
    "ARTICLE_COLLECTION_RELATIVE_PATH",
    "MEDIA_REGISTRY_RELATIVE_PATH",
    "PreparedEditorialArticle",
    "PreparedReviewDraftRevision",
    "RAKUTEN_EVIDENCE_MAX_AGE",
    "SLICE_RELATIVE_PATH",
    "SOURCE_REGISTRY_RELATIVE_PATH",
    "prepare_editorial_article",
    "prepare_review_draft_revision",
]
