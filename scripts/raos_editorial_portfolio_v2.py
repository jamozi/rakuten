#!/usr/bin/env python3
"""Capture, generate, and locally materialize EditorialPortfolioV2."""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import sys
from typing import Any, Final, Literal, Mapping, NoReturn, Sequence, cast
from urllib.parse import urlencode, urlsplit


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if PYTHON_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, PYTHON_ROOT.as_posix())

from raos.adapters import self_hosted_editorial_rakuten_capture as rakuten_capture  # noqa: E402
from raos.adapters.self_hosted_editorial_source_capture import (  # noqa: E402
    OfficialSourceCaptureFailure,
    SourceCapturePlan,
    load_source_capture_plan,
)
from raos.adapters.self_hosted_editorial_pilot_json import (  # noqa: E402
    read_rakuten_product_evidence,
)
from raos.application.editorial import self_hosted_editorial_pilot as st1704  # noqa: E402
from raos.application.editorial.editorial_portfolio_v2 import (  # noqa: E402
    ArticleBindingV2,
    LOCAL_FIXTURE_RELATIVE_PATH,
    LOCAL_MEDIA_RELATIVE_PATH,
    PORTFOLIO_RELATIVE_PATH,
    PRODUCTION_FIXTURE_RELATIVE_PATH,
    STATUS_RELATIVE_PATH,
    _validate_rakuten_identity,
    EditorialPortfolioV2Failure,
    EditorialPortfolioV2,
    ProductBindingV2,
    ProductEvidenceViewV2,
    load_editorial_portfolio_v2,
    materialize_article_v2,
    portfolio_sha256,
    product_jan_evidence_bindings_v1,
    product_evidence_readiness_v2,
    product_evidence_views_v2,
    require_manufacturer_sales_state_for_products_v1,
)
from raos.application.editorial.product_safety_receipts import (  # noqa: E402
    PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH,
    PRODUCT_SAFETY_RECEIPTS_SCHEMA,
    REQUIRED_AUTHORITY_KINDS,
    ProductSafetyOfficialSource,
    ProductSafetyProductStatus,
    ProductSafetyReceiptAudit,
    ProductSafetyReceiptFailure,
    ProductSafetyRequirement,
    ProductSafetySourceRegistryContext,
    load_product_safety_receipt_audit,
)
from raos.domain.editorial.content_ast import load_content_ast  # noqa: E402
from raos.domain.editorial.self_hosted_editorial_pilot import (  # noqa: E402
    EditorialPilotFailure,
    PILOT_RAKUTEN_AFFILIATE_IDENTITY_SCHEMA,
    PILOT_RAKUTEN_IDENTITY_SCHEMA,
    PILOT_RAKUTEN_REQUEST_SCHEMA,
    RakutenProductEvidence,
    canonical_json_bytes,
    canonical_sha256,
)


FIXTURE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures"
ST1704_ROOT = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
SOURCE_LOCATOR_RELATIVE_PATH = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "source-locator-contract.v1.json"
)
SALES_STATUS_RELATIVE_PATH = Path(
    "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
)
MARKET_CANDIDATE_AUDIT_RELATIVE_PATH = Path(
    "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
)
EDITORIAL_IDENTITIES_RELATIVE_PATH = Path(
    "changes/editorial-portfolio-v3/editorial-identities.v1.json"
)
MAX_BYTES = 4 * 1024 * 1024
SALES_STATUS_SCHEMA = "RAOS_MANUFACTURER_SALES_STATE_AUDIT_V1"
SALES_STATUS_SNAPSHOT_KIND = "STRUCTURED_OFFICIAL_SALES_STATE_SNAPSHOT_V1"
SALES_STATUS_HASH_FIELDS = (
    "checked_at_utc",
    "product_id",
    "state",
    "availability_scope",
    "official_url",
    "status_evidence_urls",
    "locator",
    "basis",
    "variant_caveat",
    "alternative",
)
SALES_STATES = frozenset({"AVAILABLE", "OUT_OF_STOCK", "DISCONTINUED", "UNKNOWN"})
PUBLICATION_ELIGIBLE_SALES_STATES = frozenset({"AVAILABLE"})
PRODUCT_SAFETY_GATE_SCHEMA = "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2"
PRODUCT_SAFETY_PUBLICATION_BINDING_SCHEMA = (
    "RAOS_PRODUCT_SAFETY_PUBLICATION_BINDING_V1"
)
PRODUCT_SAFETY_ADMINISTRATIVE_CAPTURE_COUNT_PER_PRODUCT = 3
PRODUCT_SAFETY_GATE_CAVEAT = (
    "NONE_FOUNDは、receiptに記録した公式source・型番token・query・"
    "確認日時の範囲だけを示し、安全情報が存在しないことを"
    "一般に証明しません。"
)
MANUFACTURER_SAFETY_NOTICE_SOURCE_TYPES = frozenset(
    {
        "IMPORTANT_NOTICE_PAGE",
        "PRODUCT_SAFETY_NOTICE_PAGE",
        "RECALL_INDEX_PAGE",
        "RECALL_NOTICE_PAGE",
        "SAFETY_NOTICE_PAGE",
    }
)
SELECTION_RECHECK_INTERVAL = timedelta(days=30)
SELECTION_MAX_FUTURE_SKEW = timedelta(minutes=5)
EDITORIAL_TIMEZONE = timezone(timedelta(hours=9))


@dataclass(frozen=True, slots=True)
class FactDateContract:
    """Conservative display dates bound to the sources for each scope."""

    article_dates: Mapping[str, str]
    product_dates: Mapping[str, Mapping[str, str]]
    product_source_refs: Mapping[str, Mapping[str, tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class SalesStatusEvidence:
    product_id: str
    state: str
    availability_scope: str | None
    official_url: str | None
    status_evidence_urls: tuple[str, ...]
    locator: str | None
    basis: str | None
    variant_caveat: object | None
    alternative: object | None
    snapshot_sha256: str | None


def fail(code: str) -> NoReturn:
    raise EditorialPortfolioV2Failure(code) from None


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeError:
        fail("RAOS_EDITORIAL_PORTFOLIO_JSON_INVALID")


def _read_source_snapshot(path: Path, *, optional: bool = False) -> bytes | None:
    """Read one immutable regular-file snapshot without following symlinks."""

    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_BYTES
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
    except FileNotFoundError:
        if optional:
            return None
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    except OSError:
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
    if len(payload) != before.st_size or (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    return payload


def _require_materialization_sources_current(
    *,
    portfolio_raw: bytes,
    status_raw: bytes | None,
    sales_state_raw: bytes,
    portfolio: EditorialPortfolioV2,
    views: Mapping[str, ProductEvidenceViewV2],
    now: datetime,
    require_complete: bool,
) -> None:
    """Revalidate portfolio, status, sales state and every provider binding."""

    if (
        _read_source_snapshot(ROOT / PORTFOLIO_RELATIVE_PATH) != portfolio_raw
        or _read_source_snapshot(ROOT / STATUS_RELATIVE_PATH, optional=True)
        != status_raw
        or _read_source_snapshot(ROOT / SALES_STATUS_RELATIVE_PATH) != sales_state_raw
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    try:
        current_portfolio = load_editorial_portfolio_v2(ROOT)
        current_views = product_evidence_views_v2(
            ROOT,
            now=now,
            require_fresh_set=require_complete,
            require_verified_set=require_complete,
        )
        if require_complete:
            require_manufacturer_sales_state_for_products_v1(
                current_portfolio,
                tuple(product.product_id for product in current_portfolio.products),
                now=now,
            )
    except EditorialPortfolioV2Failure:
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    if current_portfolio != portfolio or current_views != views:
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")
    if (
        _read_source_snapshot(ROOT / PORTFOLIO_RELATIVE_PATH) != portfolio_raw
        or _read_source_snapshot(ROOT / STATUS_RELATIVE_PATH, optional=True)
        != status_raw
        or _read_source_snapshot(ROOT / SALES_STATUS_RELATIVE_PATH) != sales_state_raw
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_CHANGED")


def _ensure_directory(path: Path, *, mode: int) -> None:
    try:
        path.mkdir(parents=True, mode=mode, exist_ok=True)
        os.chmod(path, mode)
        metadata = path.lstat()
    except OSError:
        fail("RAOS_EDITORIAL_PORTFOLIO_DIRECTORY_INVALID")
    if path.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
        fail("RAOS_EDITORIAL_PORTFOLIO_DIRECTORY_INVALID")


def _atomic_write(path: Path, payload: bytes, *, mode: int) -> None:
    if not 0 <= len(payload) <= MAX_BYTES:
        fail("RAOS_EDITORIAL_PORTFOLIO_WRITE_INVALID")
    _ensure_directory(path.parent, mode=0o700 if mode == 0o600 else 0o755)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode,
        )
        os.fchmod(descriptor, mode)
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written < 1:
                fail("RAOS_EDITORIAL_PORTFOLIO_WRITE_INVALID")
            view = view[written:]
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
    except EditorialPortfolioV2Failure:
        raise
    except OSError:
        fail("RAOS_EDITORIAL_PORTFOLIO_WRITE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _target(binding: ProductBindingV2) -> Any:
    if binding.rakuten_shop_code is None or binding.rakuten_item_code is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_CAPTURE_TARGET_INVALID")
    return rakuten_capture.ProductCaptureTarget(
        product_id=binding.product_id,
        shop_code=binding.rakuten_shop_code,
        affiliate_ref=binding.affiliate_ref,
        media_asset_ref=binding.media_asset_ref,
        variants=(binding.representative_model,),
        required_title_tokens=binding.required_title_tokens,
        product_kind_tokens=binding.product_kind_tokens,
        forbidden_title_tokens=binding.forbidden_title_tokens,
        # Item Search does not return JAN. Exact JAN identity is supplied by
        # the separately hashed owner-private official-source snapshot.
        jan=None,
        fixed_item_code=binding.rakuten_item_code,
        fixed_destination_url=None,
    )


def _missing_listing_status(
    binding: ProductBindingV2,
    credentials: Any,
    factory: Any,
    *,
    output_directory: Path,
) -> tuple[str, str, int]:
    parameters = [
        ("applicationId", credentials.application_id),
        ("keyword", binding.representative_model),
        ("hits", "30"),
        ("page", "1"),
        ("format", "json"),
        ("formatVersion", "2"),
        ("imageFlag", "1"),
        ("elements", ",".join(rakuten_capture._DISCOVERY_ELEMENTS)),
    ]
    raw = rakuten_capture._fetch(
        host=rakuten_capture.RAKUTEN_API_HOST,
        path=f"{rakuten_capture.RAKUTEN_API_PATH}?{urlencode(parameters)}",
        headers=rakuten_capture._api_headers(credentials),
        expected_mime=rakuten_capture._JSON_CONTENT_TYPE,
        maximum=rakuten_capture.MAX_RESPONSE_BYTES,
        connection_factory=factory,
    )
    rows = rakuten_capture._item_rows(
        raw,
        expected_fields=frozenset(rakuten_capture._DISCOVERY_ELEMENTS),
        expected_hits=30,
    )
    rakuten_capture._reject_credential_reflection(rows, credentials)
    for row in rows:
        rakuten_capture._validate_provider_row_structure(row, affiliate=False)
    target = rakuten_capture.ProductCaptureTarget(
        product_id=binding.product_id,
        shop_code="missing-evidence",
        affiliate_ref=binding.affiliate_ref,
        media_asset_ref=binding.media_asset_ref,
        variants=(binding.representative_model,),
        required_title_tokens=binding.required_title_tokens,
        product_kind_tokens=binding.product_kind_tokens,
        forbidden_title_tokens=binding.forbidden_title_tokens,
        jan=None,
        fixed_item_code=None,
        fixed_destination_url=None,
    )
    matches = [row for row in rows if rakuten_capture._valid_identity(target, row)]
    _atomic_write(
        output_directory / f"{binding.product_id}.search-response.v2.json",
        raw,
        mode=0o600,
    )
    state = "not_found" if len(matches) == 0 else "ambiguous"
    return state, hashlib.sha256(raw).hexdigest(), len(matches)


def _fixed_listing_failure_status(
    binding: ProductBindingV2,
    credentials: Any,
    factory: Any,
    *,
    output_directory: Path,
) -> tuple[str, str]:
    if binding.rakuten_item_code is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_CAPTURE_TARGET_INVALID")
    raw = rakuten_capture._api_request(
        credentials,
        selector_name="itemCode",
        selector_value=binding.rakuten_item_code,
        affiliate=False,
        elements=rakuten_capture._REQUEST_ELEMENTS,
        hits=1,
        connection_factory=factory,
        shop_code=None,
    )
    rows = rakuten_capture._item_rows(
        raw,
        expected_fields=frozenset(rakuten_capture._REQUEST_ELEMENTS),
        expected_hits=1,
    )
    rakuten_capture._reject_credential_reflection(rows, credentials)
    for row in rows:
        rakuten_capture._validate_provider_row_structure(row, affiliate=False)
    _atomic_write(
        output_directory / f"{binding.product_id}.fixed-item-response.v2.json",
        raw,
        mode=0o600,
    )
    return ("not_found" if not rows else "ambiguous"), hashlib.sha256(raw).hexdigest()


def _is_product_listing_fallback(error: object) -> bool:
    """Limit per-product fallback to provider listing identity outcomes."""

    return bool(
        type(error) is rakuten_capture.RakutenProductCaptureFailure
        and error.code
        in {
            rakuten_capture.RakutenProductCaptureFailureCode.PRODUCT_NOT_FOUND,
            rakuten_capture.RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS,
            rakuten_capture.RakutenProductCaptureFailureCode.PRODUCT_LISTING_MISMATCH,
        }
    )


def capture() -> dict[str, int]:
    portfolio = load_editorial_portfolio_v2(ROOT)
    jan_evidence_bindings = product_jan_evidence_bindings_v1(
        ROOT,
        portfolio=portfolio,
    )
    if any(
        product.official_jan is not None
        and product.product_id not in jan_evidence_bindings
        for product in portfolio.products
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INCOMPLETE")
    rakuten_capture.require_clean_capture_environment()
    credentials = rakuten_capture.read_owner_credentials(ROOT)
    factory = rakuten_capture.SystemRakutenHttpsConnectionFactory(ROOT)
    status_root = ROOT / STATUS_RELATIVE_PATH.parent
    provider_root = status_root / "provider"
    _ensure_directory(status_root, mode=0o700)
    _ensure_directory(provider_root, mode=0o700)
    records: list[dict[str, object]] = []
    counts = {"verified": 0, "not_found": 0, "ambiguous": 0}

    def now() -> datetime:
        return datetime.now(UTC)

    for index, binding in enumerate(portfolio.products, start=1):
        print(
            f"Capturing product evidence {index}/{len(portfolio.products)}: "
            f"{binding.product_id}",
            flush=True,
        )
        if binding.rakuten_item_code is not None:
            try:
                existing = read_rakuten_product_evidence(
                    ROOT, product_id=binding.product_id
                )
                _validate_rakuten_identity(
                    binding,
                    existing,
                    jan_evidence_sha256=jan_evidence_bindings.get(binding.product_id),
                )
                existing_at = datetime.fromisoformat(
                    existing.retrieved_at.replace("Z", "+00:00")
                ).astimezone(UTC)
            except EditorialPilotFailure, EditorialPortfolioV2Failure, ValueError:
                existing = None
            if (
                existing is not None
                and datetime.now(UTC) >= existing_at
                and datetime.now(UTC) - existing_at <= portfolio.freshness
            ):
                records.append(
                    {
                        "product_id": binding.product_id,
                        "state": "verified",
                        "retrieved_at": existing.retrieved_at,
                        "item_code": existing.item_code,
                        "response_sha256": existing.response_sha256,
                        "affiliate_response_sha256": existing.affiliate_response_sha256,
                        "image_sha256": existing.image_sha256,
                    }
                )
                counts["verified"] += 1
                continue
            try:
                result = rakuten_capture._capture_product(
                    ROOT,
                    _target(binding),
                    credentials,
                    connection_factory=factory,
                    clock=now,
                )
            except rakuten_capture.RakutenProductCaptureFailure as error:
                if not _is_product_listing_fallback(error):
                    raise
                state, response_sha256 = _fixed_listing_failure_status(
                    binding,
                    credentials,
                    factory,
                    output_directory=provider_root,
                )
                timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                records.append(
                    {
                        "product_id": binding.product_id,
                        "state": state,
                        "retrieved_at": timestamp,
                        "item_code": None,
                        "response_sha256": response_sha256,
                        "affiliate_response_sha256": None,
                        "image_sha256": None,
                    }
                )
                counts[state] += 1
                continue
            records.append(
                {
                    "product_id": binding.product_id,
                    "state": "verified",
                    "retrieved_at": result.retrieved_at,
                    "item_code": result.item_code,
                    "response_sha256": result.response_sha256,
                    "affiliate_response_sha256": result.affiliate_response_sha256,
                    "image_sha256": result.image_sha256,
                }
            )
            counts["verified"] += 1
            continue
        state, response_sha256, _match_count = _missing_listing_status(
            binding,
            credentials,
            factory,
            output_directory=provider_root,
        )
        timestamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        records.append(
            {
                "product_id": binding.product_id,
                "state": state,
                "retrieved_at": timestamp,
                "item_code": None,
                "response_sha256": response_sha256,
                "affiliate_response_sha256": None,
                "image_sha256": None,
            }
        )
        counts[state] += 1
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2",
        "captured_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "portfolio_sha256": portfolio_sha256(ROOT),
        "products": records,
    }
    _atomic_write(
        ROOT / STATUS_RELATIVE_PATH,
        _canonical_bytes(receipt) + b"\n",
        mode=0o600,
    )
    product_evidence_views_v2(ROOT, require_fresh_set=True)
    return counts


def _synthetic_render_evidence(
    binding: ProductBindingV2,
    *,
    affiliate_ref: str,
    media_ref: str,
    product_name: str,
    identity: Mapping[str, object],
    sequence: int,
) -> RakutenProductEvidence:
    """Create deterministic in-memory renderer input that is never published.

    EditorialPortfolioV2 immediately rewrites the rendered CTA to the official
    fallback and renders a non-image blocked state for product media. Provider
    evidence is acquired only by `capture`, so source fixture generation cannot
    be blocked by an expired private row or pretend to have a product image.
    """

    allowed_variants = cast(list[object], identity["allowed_variants"])
    if binding.representative_model not in allowed_variants:
        fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    raw_item_code = identity.get("item_code") or binding.rakuten_item_code
    item_code = (
        raw_item_code
        if type(raw_item_code) is str
        else f"raos-neutral:{10_000_000 + sequence}"
    )
    shop, item = item_code.split(":", 1)
    item_url = f"https://item.rakuten.co.jp/{shop}/{item}/"
    mobile_url = f"https://m.rakuten.co.jp/{shop}/i/{item}/"
    destination_url = (
        "https://hb.afl.rakuten.co.jp/hgc/raos-local-render/?"
        + urlencode({"pc": item_url, "m": mobile_url, "rafcid": "raos-local-render"})
    )
    image_url = (
        f"https://thumbnail.image.rakuten.co.jp/@0_mall/{shop}/"
        "cabinet/raos-local-render.jpg?_ex=128x128"
    )
    title_tokens = [
        cast(str, value)
        for value in cast(list[object], identity["required_title_tokens"])
    ]
    kind_tokens = [
        cast(str, value)
        for value in cast(list[object], identity["product_kind_tokens"])
    ]
    item_name = " ".join(dict.fromkeys([product_name, *title_tokens, kind_tokens[0]]))
    official_jan = identity.get("jan")
    if official_jan is not None and type(official_jan) is not str:
        fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    request_base = {
        "api_version": "2026-07-01",
        "endpoint": (
            "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
        ),
        "format": "json",
        "format_version": 2,
        "image_flag": 1,
        "item_code": item_code,
        "schema": PILOT_RAKUTEN_REQUEST_SCHEMA,
        "secret_fields_excluded": ["accessKey", "affiliateId", "applicationId"],
    }
    request_without_affiliate = {
        **request_base,
        "elements": ["itemCode", "itemName", "itemUrl", "mediumImageUrls"],
        "affiliate_id_supplied": False,
    }
    request_with_affiliate = {
        **request_base,
        "elements": [
            "affiliateUrl",
            "itemCode",
            "itemName",
            "itemUrl",
            "mediumImageUrls",
        ],
        "affiliate_id_supplied": True,
    }
    # Item Search does not return JAN. The official JAN stays in the tracked
    # product registry and must not be presented as provider-returned evidence.
    normalized_jan: str | None = None
    return RakutenProductEvidence(
        product_id=binding.product_id,
        affiliate_ref=affiliate_ref,
        media_asset_ref=media_ref,
        item_code=item_code,
        item_name=item_name,
        jan=normalized_jan,
        variant=binding.representative_model,
        source_url=item_url,
        destination_url=destination_url,
        image_url=image_url,
        width=128,
        height=128,
        retrieved_at="2026-08-29T00:00:00Z",
        request_fingerprint=canonical_sha256(request_without_affiliate),
        response_sha256=hashlib.sha256(
            f"source-render:{binding.product_id}".encode("ascii")
        ).hexdigest(),
        selected_result_sha256=canonical_sha256(
            {
                "image_url": image_url,
                "item_code": item_code,
                "item_name": item_name,
                "jan": normalized_jan,
                "schema": PILOT_RAKUTEN_IDENTITY_SCHEMA,
                "source_url": item_url,
            }
        ),
        affiliate_request_fingerprint=canonical_sha256(request_with_affiliate),
        affiliate_response_sha256=hashlib.sha256(
            f"source-render-affiliate:{binding.product_id}".encode("ascii")
        ).hexdigest(),
        affiliate_selected_result_sha256=canonical_sha256(
            {
                "affiliate_url": destination_url,
                "image_url": image_url,
                "item_code": item_code,
                "item_name": item_name,
                "item_url": destination_url,
                "jan": normalized_jan,
                "schema": PILOT_RAKUTEN_AFFILIATE_IDENTITY_SCHEMA,
            }
        ),
        image_sha256=hashlib.sha256(
            f"source-render-image:{binding.product_id}".encode("ascii")
        ).hexdigest(),
        no_modification_policy=(
            ("aspect_ratio_change_allowed", False),
            ("crop_allowed", False),
            ("modification_allowed", False),
            ("text_overlay_allowed", False),
            ("upscale_allowed", False),
        ),
    )


def _render_st1704_article(
    article_id: str,
    portfolio: EditorialPortfolioV2,
) -> str:
    collection, routes, articles = st1704._validate_articles(
        st1704._read_fixed_json(ROOT, st1704.ARTICLE_COLLECTION_RELATIVE_PATH)
    )
    _registry, sources, packets, affiliates, claims = st1704._validate_sources(
        st1704._read_fixed_json(ROOT, st1704.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    media = st1704._validate_media(
        st1704._read_fixed_json(ROOT, st1704.MEDIA_REGISTRY_RELATIVE_PATH)
    )
    article = articles[article_id]
    packet_ref = cast(str, article["source_packet_ref"])
    packet = packets.get(packet_ref)
    if packet is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    try:
        selected_sources = [
            sources[cast(str, source_ref)]
            for source_ref in cast(list[object], packet["source_refs"])
        ]
    except KeyError:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    freshness = cast(Mapping[str, object], article["freshness"])
    facts_checked_on = portfolio.editorial_reviewed_on
    if freshness.get("facts_checked_on") != facts_checked_on or any(
        _source_display_date(source) > facts_checked_on for source in selected_sources
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
    ast = cast(
        Mapping[str, object],
        load_content_ast(canonical_json_bytes(article["content_ast"])).model_dump(
            mode="json", by_alias=True, warnings=False
        ),
    )
    # The legacy registry is an immutable rendering input and can contain an older
    # provider snapshot (notably JAN/image metadata).  Validate it first, then bind
    # a private in-memory copy to the freshly captured evidence.  The portfolio
    # contract independently enforces the fixed item code, model and title tokens.
    private_affiliates = deepcopy(affiliates)
    private_media = deepcopy(media)
    synthetic_evidence: dict[str, RakutenProductEvidence] = {}
    render_model = cast(Mapping[str, object], article["render_model"])
    for sequence, raw_card in enumerate(
        cast(list[object], render_model["product_cards"]), start=1
    ):
        card = cast(Mapping[str, object], raw_card)
        product_id = cast(str, card["product_id"])
        affiliate_ref = cast(str, card["affiliate_ref"])
        media_ref = cast(str, card["media_asset_ref"])
        binding = portfolio.product_by_id.get(product_id)
        if binding is None:
            fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_INVALID")
        identity = cast(
            Mapping[str, object],
            private_media[media_ref]["identity"],
        )
        evidence = _synthetic_render_evidence(
            binding,
            affiliate_ref=affiliate_ref,
            media_ref=media_ref,
            product_name=cast(str, card["product_name"]),
            identity=identity,
            sequence=sequence,
        )
        synthetic_evidence[product_id] = evidence
        private_affiliate = cast(dict[str, object], private_affiliates[affiliate_ref])
        private_affiliate["destination_url"] = evidence.destination_url
        private_asset = cast(dict[str, object], private_media[media_ref])
        private_identity = cast(dict[str, object], private_asset["identity"])
        private_identity["jan"] = evidence.jan
        for key, observed in (
            ("source_url", evidence.source_url),
            ("image_url", evidence.image_url),
            ("width", evidence.width),
            ("height", evidence.height),
            ("retrieved_at", evidence.retrieved_at),
            ("response_sha256", evidence.response_sha256),
            ("image_sha256", evidence.image_sha256),
        ):
            private_asset[key] = observed
    cards, evidences, _affiliate_records, media_records = st1704._bind_product_evidence(
        ROOT,
        article,
        private_affiliates,
        private_media,
        lambda _root, *, product_id: synthetic_evidence[product_id],
        facts_checked_on=facts_checked_on,
    )
    content = st1704._Renderer(
        article=article,
        routes=routes,
        sources=sources,
        claims=claims,
        cards=cards,
        evidences=evidences,
        alts={
            cast(str, asset["product_id"]): cast(str, asset["alt"])
            for asset in media_records
        },
        facts_checked_on=facts_checked_on,
        product_media_verified=False,
    ).render(ast)
    # WordPress 7.1's post-content KSES profile removes this image hint.  Keep
    # tracked and production markup byte-stable with the writer projection.
    content = content.replace(' decoding="async"', "")
    if 'class="raos-editorial-v2"' not in content:
        content = '<div class="raos-editorial-v2">\n' + content + "</div>\n"
    del collection
    return content


def _fallback_views(
    portfolio: EditorialPortfolioV2,
) -> dict[str, ProductEvidenceViewV2]:
    return {
        product.product_id: ProductEvidenceViewV2(
            product_id=product.product_id,
            state="expired",
            retrieved_at="1970-01-01T00:00:00Z",
            evidence=None,
        )
        for product in portfolio.products
    }


def _source_display_date(source: Mapping[str, object]) -> str:
    """Return a date that never postdates a tracked retrieval/observation."""

    candidates: list[date] = []
    for field in ("retrieved_on", "observed_on"):
        raw = source.get(field)
        if raw is None:
            continue
        if type(raw) is not str:
            fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
        try:
            candidates.append(date.fromisoformat(raw[:10]))
        except ValueError:
            fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
    if not candidates:
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
    return min(candidates).isoformat()


def _normalized_source_identity(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", re.sub(r"^(?:PRD|SRC)-", "", value.upper()))


def _product_source_refs_for_article(
    *,
    article_id: str,
    product_id: str,
    official_url: str,
    packet_source_refs: tuple[str, ...],
    rendered_articles: Mapping[str, Mapping[str, object]],
    sources: Mapping[str, Mapping[str, object]],
) -> tuple[str, ...]:
    rendered = rendered_articles.get(article_id)
    if rendered is not None:
        render_model = cast(Mapping[str, object], rendered["render_model"])
        for raw_card in cast(list[object], render_model["product_cards"]):
            card = cast(Mapping[str, object], raw_card)
            if card.get("product_id") == product_id:
                refs = tuple(
                    cast(str, value)
                    for value in cast(list[object], card["source_refs"])
                )
                if not refs or not set(refs).issubset(packet_source_refs):
                    fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SOURCE_INVALID")
                return refs

    # Some products use more than one official page for identity/specification or
    # installation facts.  These relations are explicit so a similarly named
    # product can never be picked by a fuzzy match.
    overrides = {
        (
            "lightweight-carry-on-suitcase-under-3kg",
            "PRD-PROTECA-AEROFLEX-DX2-01521",
        ): (
            "SRC-PROTECA-AEROFLEX-DX2-01521",
            "SRC-PROTECA-SUITCASE-WARRANTY",
        ),
        (
            "lightweight-carry-on-suitcase-under-3kg",
            "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
        ): (
            "SRC-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
            "SRC-RIMOWA-LIFETIME-GUARANTEE",
            "SRC-RIMOWA-WARRANTY-FAQ",
        ),
        (
            "lightweight-carry-on-suitcase-under-3kg",
            "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
        ): (
            "SRC-SAMSONITE-C-LITE-CS2-09007",
            "SRC-SAMSONITE-CATALOG-2025",
            "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT",
        ),
        (
            "solota-vs-rakua-mini-plus",
            "PRD-PANASONIC-SOLOTA-NP-TML1-W",
        ): (
            "SRC-PANASONIC-NP-TML1",
            "SRC-PANASONIC-SOLOTA-IDENTITY",
        ),
        (
            "solota-vs-rakua-mini-plus",
            "PRD-SIROCA-SS-M171",
        ): (
            "SRC-SIROCA-SS-M171",
            "SRC-SIROCA-SS-M171-MANUAL",
            "SRC-SIROCA-DISHWASHER-INSTALLATION",
        ),
    }
    explicit = overrides.get((article_id, product_id))
    if explicit is not None:
        if not set(explicit).issubset(packet_source_refs):
            fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SOURCE_INVALID")
        return explicit

    exact_url = tuple(
        source_ref
        for source_ref in packet_source_refs
        if sources[source_ref].get("url") == official_url
    )
    if len(exact_url) == 1:
        return exact_url
    normalized_product = _normalized_source_identity(product_id)
    normalized = tuple(
        source_ref
        for source_ref in packet_source_refs
        if _normalized_source_identity(source_ref) == normalized_product
    )
    if len(normalized) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SOURCE_INVALID")
    return normalized


def _source_fact_date_contract(portfolio: EditorialPortfolioV2) -> FactDateContract:
    """Bind editorial review and product-source dates to distinct scopes.

    The article-wide date records the actual final editorial review. Product
    cards use only their own source refs, so that review date is never presented
    as though every manufacturer page had been retrieved on the same day.
    """

    _registry, sources, packets, _affiliates, _claims = st1704._validate_sources(
        st1704._read_fixed_json(ROOT, st1704.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    _collection, _routes, rendered_articles = st1704._validate_articles(
        st1704._read_fixed_json(ROOT, st1704.ARTICLE_COLLECTION_RELATIVE_PATH)
    )
    packets_by_article: dict[str, Mapping[str, object]] = {}
    for packet in packets.values():
        article_id = cast(str, packet["article_id"])
        if article_id in packets_by_article:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
        packets_by_article[article_id] = packet

    article_dates: dict[str, str] = {}
    product_dates: dict[str, dict[str, str]] = {}
    product_source_refs: dict[str, dict[str, tuple[str, ...]]] = {}
    for article in portfolio.articles:
        packet = packets_by_article.get(article.article_id)
        if packet is None:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
        packet_refs = tuple(
            cast(str, value) for value in cast(list[object], packet["source_refs"])
        )
        try:
            source_dates = tuple(
                _source_display_date(sources[source_ref]) for source_ref in packet_refs
            )
        except KeyError, ValueError:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
        if not source_dates or max(source_dates) > portfolio.editorial_reviewed_on:
            fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
        article_dates[article.article_id] = portfolio.editorial_reviewed_on
        product_dates[article.article_id] = {}
        product_source_refs[article.article_id] = {}
        for product_id in article.product_ids:
            binding = portfolio.product_by_id[product_id]
            refs = _product_source_refs_for_article(
                article_id=article.article_id,
                product_id=product_id,
                official_url=binding.official_url,
                packet_source_refs=packet_refs,
                rendered_articles=rendered_articles,
                sources=sources,
            )
            product_source_refs[article.article_id][product_id] = refs
            product_dates[article.article_id][product_id] = min(
                _source_display_date(sources[source_ref]) for source_ref in refs
            )
    return FactDateContract(
        article_dates=article_dates,
        product_dates=product_dates,
        product_source_refs=product_source_refs,
    )


def _source_fact_dates(
    portfolio: EditorialPortfolioV2 | None = None,
) -> dict[str, str]:
    """Backward-compatible article-date view for final editorial review."""

    contract = _source_fact_date_contract(
        portfolio or load_editorial_portfolio_v2(ROOT)
    )
    return dict(contract.article_dates)


def _japanese_date(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_DATE_INVALID")
    return f"{parsed.year}年{parsed.month}月{parsed.day}日"


def _replace_product_card_date(markup: str, product_id: str, value: str) -> str:
    product_pattern = re.compile(
        r'(<article\b(?=[^>]*\bdata-raos-product-id="'
        + re.escape(product_id)
        + r'")[^>]*>)(.*?)(</article>)',
        flags=re.DOTALL,
    )
    replacement = f"情報確認日 {_japanese_date(value)}"

    def replace_card(match: re.Match[str]) -> str:
        body, count = re.subn(
            r"情報確認日\s+\d{4}年\d{1,2}月\d{1,2}日",
            replacement,
            match.group(2),
        )
        if count == 0:
            body, count = re.subn(
                r"(\s*)(<div\b[^>]*\bdata-raos-purchase-action(?=\s|>|=)[^>]*>)",
                rf'\g<1><p class="raos-source-link">{replacement}</p>'
                rf"\g<1>\g<2>",
                body,
                count=1,
            )
        if count != 1:
            fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_DATE_INVALID")
        return match.group(1) + body + match.group(3)

    normalized, count = product_pattern.subn(replace_card, markup)
    if count != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_DATE_INVALID")
    return normalized


def _replace_displayed_fact_date(
    markup: str,
    facts_checked_on: str,
    *,
    product_dates: Mapping[str, str] | None = None,
) -> str:
    """Update only declared date scopes; never blanket-replace calendar text."""

    japanese = _japanese_date(facts_checked_on)
    dotted = date.fromisoformat(facts_checked_on).strftime("%Y.%m.%d")
    normalized, metadata_count = re.subn(
        r"(<dt>最終確認日</dt><dd>)\d{4}年\d{1,2}月\d{1,2}日(</dd>)",
        rf"\g<1>{japanese}\g<2>",
        markup,
    )
    if metadata_count != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    normalized = re.sub(
        r"((?:SPECIFICATIONS CHECKED|一次情報確認日)\s*/\s*)\d{4}\.\d{2}\.\d{2}",
        rf"\g<1>{dotted}",
        normalized,
    )
    normalized = re.sub(
        r"((?:商品情報の確認日|情報確認日)[：:]\s*)"
        r"\d{4}年\d{1,2}月\d{1,2}日",
        rf"\g<1>{japanese}",
        normalized,
    )
    for product_id, product_date in (product_dates or {}).items():
        normalized = _replace_product_card_date(
            normalized,
            product_id,
            product_date,
        )
    if normalized.count(f"<dt>最終確認日</dt><dd>{japanese}</dd>") != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    return normalized


def _visible_intent_metadata() -> Mapping[str, tuple[str, str]]:
    """Project reader-visible roles and intents from the V3 identity owner."""

    raw = _read_source_snapshot(ROOT / EDITORIAL_IDENTITIES_RELATIVE_PATH)
    if raw is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
    if not isinstance(document, dict) or document.get("schema") != (
        "RAOS_EDITORIAL_V3_IDENTITIES_V1"
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
    rows = document.get("articles")
    if not isinstance(rows, list) or len(rows) != 10:
        fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
    metadata: dict[str, tuple[str, str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
        article_id = row.get("article_id")
        role = row.get("content_role_label")
        intent = row.get("primary_query_intent")
        if (
            not all(
                isinstance(value, str) and value.strip()
                for value in (article_id, role, intent)
            )
            or article_id in metadata
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
        metadata[cast(str, article_id)] = (cast(str, role), cast(str, intent))
    return metadata


def _ensure_visible_intent_metadata(markup: str, article_id: str) -> str:
    expected = _visible_intent_metadata().get(article_id)
    if expected is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_IDENTITY_INVALID")
    role, intent = expected
    role_fragment = f"<div><dt>記事分類</dt><dd>{role}</dd></div>"
    intent_fragment = f"<div><dt>この記事で答えること</dt><dd>{intent}</dd></div>"
    role_count = markup.count("<dt>記事分類</dt>")
    intent_count = markup.count("<dt>この記事で答えること</dt>")
    if role_count or intent_count:
        if role_count != 1 or intent_count != 1:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
        markup, role_replacements = re.subn(
            r"<div><dt>記事分類</dt><dd>[^<]+</dd></div>",
            role_fragment,
            markup,
            count=1,
        )
        markup, intent_replacements = re.subn(
            r"<div><dt>この記事で答えること</dt><dd>[^<]+</dd></div>",
            intent_fragment,
            markup,
            count=1,
        )
        if role_replacements != 1 or intent_replacements != 1:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
        return markup
    marker = "<div><dt>執筆担当</dt>"
    if markup.count(marker) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    return markup.replace(
        marker,
        role_fragment + intent_fragment + marker,
        1,
    )


_READER_LIFECYCLE_LABELS: Final[dict[str, str]] = {
    "AVAILABLE": "メーカー公式で現行表示を確認",
    "OUT_OF_STOCK": "メーカー公式で在庫切れを確認",
    "SOLD_OUT": "メーカー公式で売り切れを確認",
    "PRODUCTION_ENDED": "メーカー公式で生産終了を確認",
    "PREORDER": "メーカー公式で予約受付段階を確認",
    "RESTOCK_NOTIFICATION_ONLY": "メーカー公式で再入荷通知のみを確認",
    "UNKNOWN": "販売状態は未確認（推奨根拠に使用しない）",
}

_RAKUTEN_CREDIT_ANCHOR: Final = (
    '<a href="https://developers.rakuten.com/" target="_blank" rel="noopener noreferrer">'
    "Supported by Rakuten Developers</a>"
)
_RAKUTEN_CREDIT_SNIPPET: Final = (
    "<!-- Rakuten Web Services Attribution Snippet FROM HERE -->\n"
    + _RAKUTEN_CREDIT_ANCHOR
    + "\n<!-- Rakuten Web Services Attribution Snippet TO HERE -->"
)
_RAKUTEN_CREDIT_BLOCK: Final = (
    '<div class="raos-rakuten-credit">'
    "<p>商品情報の取得には楽天ウェブサービスを利用しています。</p>"
    + _RAKUTEN_CREDIT_SNIPPET
    + "</div>"
)


def _ensure_exact_rakuten_credit(markup: str) -> str:
    """Keep Rakuten's required attribution snippet unmodified on every article."""

    if markup.count(_RAKUTEN_CREDIT_BLOCK) == 1:
        if (
            markup.count(_RAKUTEN_CREDIT_ANCHOR) != 1
            or markup.count("Rakuten Web Services Attribution Snippet FROM HERE") != 1
            or markup.count("Rakuten Web Services Attribution Snippet TO HERE") != 1
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_RAKUTEN_CREDIT_INVALID")
        return markup

    credit_pattern = re.compile(
        r'(?:<div class="raos-rakuten-credit">.*?'
        r"Rakuten Web Services Attribution Snippet TO HERE -->.*?</div>|"
        r'<p class="raos-source-link"><a href="https://developers\.rakuten\.com/"'
        r"[^>]*>.*?</a></p>)",
        flags=re.DOTALL,
    )
    without_credit, removed = credit_pattern.subn("", markup)
    if removed > 1 or "https://developers.rakuten.com/" in without_credit:
        fail("RAOS_EDITORIAL_PORTFOLIO_RAKUTEN_CREDIT_INVALID")

    source_starts = [
        match.start()
        for match in re.finditer(
            r'<section\b[^>]*class="[^"]*\bsources-section\b[^"]*"[^>]*>',
            without_credit,
        )
    ]
    if len(source_starts) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_RAKUTEN_CREDIT_INVALID")
    source_end = without_credit.find("</section>", source_starts[0])
    if source_end < 0:
        fail("RAOS_EDITORIAL_PORTFOLIO_RAKUTEN_CREDIT_INVALID")
    return (
        without_credit[:source_end]
        + _RAKUTEN_CREDIT_BLOCK
        + without_credit[source_end:]
    )


def _market_candidate_audit_for(article_id: str) -> Mapping[str, object]:
    raw = _read_source_snapshot(ROOT / MARKET_CANDIDATE_AUDIT_RELATIVE_PATH)
    if raw is None:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    try:
        document = json.loads(raw.decode("utf-8", errors="strict"))
    except UnicodeError, json.JSONDecodeError:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    if not isinstance(document, dict) or document.get("schema") != (
        "RAOS_EDITORIAL_MARKET_CANDIDATE_AUDIT_V1"
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    rows = document.get("articles")
    if not isinstance(rows, list):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    matches = [
        row
        for row in rows
        if isinstance(row, dict) and row.get("article_id") == article_id
    ]
    if len(matches) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    return cast(Mapping[str, object], matches[0])


_LEGACY_MARKET_EXCLUSION_CONTAINERS: Final[Mapping[str, tuple[str, str]]] = {
    "carry-on-suitcase-under-100-seats": (
        '<section class="method-section" aria-labelledby="under-100-exclusions-title">',
        "section",
    ),
    "lightweight-carry-on-suitcase-under-3kg": (
        '<aside class="purchase-caution" aria-labelledby="under-3kg-candidate-title">',
        "aside",
    ),
    "front-open-carry-on-suitcase-with-stopper": (
        '<section class="method-section" aria-labelledby="scope-exclusions-title">',
        "section",
    ),
    "solota-vs-rakua-mini-plus": (
        '<aside class="disclosure" aria-labelledby="dish-history-title">',
        "aside",
    ),
}


def _balanced_element_end(markup: str, start: int, tag: str) -> int:
    element_pattern = re.compile(rf"</?{re.escape(tag)}\b[^>]*>", re.IGNORECASE)
    depth = 0
    for match in element_pattern.finditer(markup, start):
        depth += -1 if match.group(0).startswith("</") else 1
        if depth == 0:
            return match.end()
    fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")


def _reader_visible_market_exclusions(
    markup: str,
    article_id: str,
    portfolio: EditorialPortfolioV2 | None = None,
) -> str:
    """Bind the rendered exclusion explanation to the market audit source."""

    portfolio = portfolio or load_editorial_portfolio_v2(ROOT)
    audit = _market_candidate_audit_for(article_id)
    if audit.get("reader_visible_required") is not True:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    raw_candidates = audit.get("considered_external_candidates")
    if not isinstance(raw_candidates, list) or not raw_candidates:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    section_heading = audit.get("reader_visible_exclusions_heading")
    if (
        not isinstance(section_heading, str)
        or not 8 <= len(section_heading) <= 60
        or section_heading != section_heading.strip()
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")

    entries: list[str] = []
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        candidate = cast(Mapping[str, object], raw_candidate)
        brand = candidate.get("brand")
        exact_model = candidate.get("exact_model")
        exact_variant_scope = candidate.get("exact_variant_scope")
        official_url = candidate.get("official_url")
        reason = candidate.get("reason")
        lifecycle = candidate.get("effective_lifecycle")
        evaluated_at = candidate.get("evaluated_at")
        disposition = candidate.get("disposition")
        if (
            not all(
                isinstance(value, str) and value.strip()
                for value in (
                    brand,
                    exact_model,
                    exact_variant_scope,
                    official_url,
                    reason,
                    lifecycle,
                    evaluated_at,
                    disposition,
                )
            )
            or disposition not in {"EXCLUDED", "DEFERRED"}
            or lifecycle not in _READER_LIFECYCLE_LABELS
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        parsed = urlsplit(cast(str, official_url))
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        try:
            checked_on = _japanese_date(cast(str, evaluated_at))
        except ValueError:
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        heading = f"{brand} {exact_model}"
        entries.append(
            "<section><h3>"
            + escape(heading)
            + '</h3><p><a href="'
            + escape(cast(str, official_url), quote=True)
            + '" rel="noopener noreferrer">メーカー公式情報を確認する</a>。'
            + escape(_READER_LIFECYCLE_LABELS[cast(str, lifecycle)])
            + "。確認日："
            + escape(checked_on)
            + "。型番・対象範囲："
            + escape(cast(str, exact_variant_scope))
            + "。</p><p>比較表に含めなかった理由："
            + escape(cast(str, reason))
            + "</p></section>"
        )

    raw_portfolio_candidates = audit.get("considered_portfolio_candidates")
    if not isinstance(raw_portfolio_candidates, list):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    products = portfolio.product_by_id
    articles = {article.article_id: article for article in portfolio.articles}
    emitted_route_links: set[str] = set()
    for raw_candidate in raw_portfolio_candidates:
        if not isinstance(raw_candidate, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        product_id = raw_candidate.get("product_id")
        route_article_id = raw_candidate.get("route_article_id")
        reason = raw_candidate.get("reason")
        product = products.get(cast(str, product_id))
        route = articles.get(cast(str, route_article_id))
        if (
            raw_candidate.get("disposition") != "REFERENCE_ONLY"
            or not isinstance(product_id, str)
            or product is None
            or not isinstance(route_article_id, str)
            or route is None
            or route.article_id == article_id
            or not isinstance(reason, str)
            or not reason.strip()
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        route_href = f"/{route.production_slug}/"
        if route_href in emitted_route_links:
            route_copy = "同じ比較記事で確認できます。"
        else:
            emitted_route_links.add(route_href)
            route_copy = (
                '<a href="'
                + escape(route_href, quote=True)
                + '">関連する比較記事を確認する</a>。'
            )
        entries.append(
            "<section><h3>"
            + escape(product.official_name)
            + "</h3><p>"
            + route_copy
            + escape(reason)
            + "</p></section>"
        )

    safe_id = re.sub(r"[^a-z0-9-]", "-", article_id.lower())
    heading_id = f"raos-market-exclusions-{safe_id}-title"
    canonical = (
        '<section class="method-section raos-market-exclusions" aria-labelledby="'
        + heading_id
        + '"><header class="section-heading section-heading--side"><h2 id="'
        + heading_id
        + '">'
        + escape(section_heading)
        + "</h2>"
        + "<p>市場全体の順位ではありません。比較表の外に置いた候補も、販売状態と理由を公式情報へたどれる形で示します。</p>"
        + '</header><div class="raos-market-exclusions__list">'
        + "".join(entries)
        + "</div></section>"
    )

    canonical_start = '<section class="method-section raos-market-exclusions"'
    if canonical_start in markup:
        start = markup.index(canonical_start)
        end = _balanced_element_end(markup, start, "section")
        return markup[:start] + canonical + markup[end:]

    legacy = _LEGACY_MARKET_EXCLUSION_CONTAINERS.get(article_id)
    if legacy is not None and legacy[0] in markup:
        start = markup.index(legacy[0])
        end = _balanced_element_end(markup, start, legacy[1])
        return markup[:start] + canonical + markup[end:]

    legacy_start = (
        '<section class="method-section" aria-labelledby="anker-exclusions-title">'
    )
    if legacy_start in markup:
        start = markup.index(legacy_start)
        end = markup.index("</section>", start) + len("</section>")
        markup = markup[:start] + markup[end:]

    method_start = markup.find('<section class="method-section"')
    if method_start < 0:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    method_end = markup.find("</section>", method_start)
    if method_end < 0:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    method_end += len("</section>")
    return markup[:method_end] + canonical + markup[method_end:]


def _deduplicate_market_candidate_routes(
    markup: str,
    article_id: str,
) -> str:
    """Keep one intentional internal link per audited destination.

    The canonical candidate section owns the link and surrounding rationale. Any
    older prose elsewhere in the article keeps its words but no longer repeats the
    same destination. Multiple candidates may intentionally share a broader
    article, but repeating the same link for every candidate adds no navigation
    value and makes lifecycle-route articles unnecessarily repetitive.
    """

    audit = _market_candidate_audit_for(article_id)
    candidates = audit.get("considered_portfolio_candidates")
    if not isinstance(candidates, list):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    portfolio = load_editorial_portfolio_v2(ROOT)
    articles = {article.article_id: article for article in portfolio.articles}
    canonical_start = '<section class="method-section raos-market-exclusions"'
    if markup.count(canonical_start) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE")
    start = markup.index(canonical_start)
    end = _balanced_element_end(markup, start, "section")
    prefix = markup[:start]
    canonical = markup[start:end]
    suffix = markup[end:]
    expected_links_by_href: dict[str, int] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        route = articles.get(cast(str, candidate.get("route_article_id")))
        if route is None:
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        href = f"/{route.production_slug}/"
        anchor = re.compile(
            r'<a\b(?=[^>]*\bhref="' + re.escape(href) + r'")[^>]*>(.*?)</a>',
            re.DOTALL,
        )
        prefix = anchor.sub(r"\1", prefix)
        suffix = anchor.sub(r"\1", suffix)
        expected_links_by_href[href] = 1
    for href, expected_count in expected_links_by_href.items():
        if canonical.count(f'href="{href}"') != expected_count:
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE")
    return prefix + canonical + suffix


def _validate_reader_visible_market_exclusions(
    markup: str,
    article_id: str,
    portfolio: EditorialPortfolioV2 | None = None,
) -> str:
    """Reject a fixture when an audited external candidate is hidden from readers."""

    portfolio = portfolio or load_editorial_portfolio_v2(ROOT)
    audit = _market_candidate_audit_for(article_id)
    if audit.get("reader_visible_required") is not True:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    candidates = audit.get("considered_external_candidates")
    if not isinstance(candidates, list) or not candidates:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    canonical_start = '<section class="method-section raos-market-exclusions"'
    if markup.count(canonical_start) != 1:
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE")
    start = markup.index(canonical_start)
    end = _balanced_element_end(markup, start, "section")
    rendered = markup[start:end]
    for candidate in candidates:
        if not isinstance(candidate, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        exact_model = candidate.get("exact_model")
        official_url = candidate.get("official_url")
        reason = candidate.get("reason")
        lifecycle = candidate.get("effective_lifecycle")
        evaluated_at = candidate.get("evaluated_at")
        try:
            checked_on = _japanese_date(cast(str, evaluated_at))
        except TypeError, ValueError:
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        if (
            not isinstance(exact_model, str)
            or not exact_model.strip()
            or not isinstance(official_url, str)
            or not official_url.startswith("https://")
            or not isinstance(reason, str)
            or not reason.strip()
            or lifecycle not in _READER_LIFECYCLE_LABELS
            or exact_model not in rendered
            or f'href="{escape(official_url, quote=True)}"' not in rendered
            or escape(reason) not in rendered
            or escape(_READER_LIFECYCLE_LABELS[cast(str, lifecycle)]) not in rendered
            or f"確認日：{escape(checked_on)}" not in rendered
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE")
    products = portfolio.product_by_id
    articles = {article.article_id: article for article in portfolio.articles}
    raw_portfolio_candidates = audit.get("considered_portfolio_candidates")
    if not isinstance(raw_portfolio_candidates, list):
        fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
    for candidate in raw_portfolio_candidates:
        if not isinstance(candidate, dict):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_INVALID")
        product = products.get(cast(str, candidate.get("product_id")))
        route = articles.get(cast(str, candidate.get("route_article_id")))
        reason = candidate.get("reason")
        if (
            product is None
            or route is None
            or not isinstance(reason, str)
            or product.official_name not in rendered
            or f'href="/{escape(route.production_slug, quote=True)}/"' not in rendered
            or escape(reason) not in rendered
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_MARKET_AUDIT_NOT_READER_VISIBLE")
    return markup


def _anker_feature_claim_is_bound() -> bool:
    _registry, _sources, _packets, _affiliates, claims = st1704._validate_sources(
        st1704._read_fixed_json(ROOT, st1704.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    claim = claims.get("CLM-ST1704-ANKER-C1000-FEATURE-DIFF")
    if claim is None:
        return False
    statement = cast(str, claim.get("statement", ""))
    required = (
        "C1000 Gen 2は拡張バッテリー非対応",
        "AC出力5口",
        "USB-C 3口",
        "C1000は拡張バッテリー対応",
        "AC出力6口",
        "USB-C 2口",
        "SurgePad 2000W",
    )
    if (
        claim.get("classification") != "MAJOR_VERIFIABLE"
        or claim.get("evidence_level") != "A"
        or claim.get("status") != "BOUND_TO_OFFICIAL_SOURCE"
        or claim.get("evidence_refs") != ["SRC-ANKER-SOLIX-C1000-GEN2"]
        or not all(value in statement for value in required)
    ):
        return False
    locator_document = st1704._read_fixed_json(ROOT, SOURCE_LOCATOR_RELATIVE_PATH)
    if type(locator_document) is not dict:
        return False
    for raw_source in cast(list[object], locator_document.get("sources", [])):
        if type(raw_source) is not dict:
            continue
        source = cast(Mapping[str, object], raw_source)
        if (
            source.get("source_ref") != "SRC-ANKER-SOLIX-C1000-GEN2"
            or source.get("locator_status") != "READY"
        ):
            continue
        return any(
            type(raw_locator) is dict
            and raw_locator.get("claim_id") == "CLM-ST1704-ANKER-C1000-FEATURE-DIFF"
            and bool(raw_locator.get("exact_utf8_fragments"))
            for raw_locator in cast(list[object], source.get("locators", []))
        )
    return False


def _normalize_anker_compatibility(markup: str, article_id: str) -> str:
    """Project the packet's confirmed C1000 generation facts into the table."""

    if article_id != "st1704-anker-solix-c300-c800-c1000-differences":
        return markup
    if not _anker_feature_claim_is_bound():
        fail("RAOS_EDITORIAL_PORTFOLIO_ANKER_COMPATIBILITY_UNBOUND")
    normalized = markup.replace("付属品・互換性", "世代固有機能・拡張性")
    badge = (
        '<span class="raos-evidence-badge" '
        'data-raos-evidence-level="A">公式確認済み</span>'
    )
    unknown_badge = (
        '<span class="raos-evidence-badge" '
        'data-raos-evidence-level="UNKNOWN">未確認</span>'
    )
    c1000_text = "拡張バッテリー対応・AC出力6口・USB-C 2口・SurgePad 2000W"
    gen2_text = "拡張バッテリー非対応・AC出力5口・USB-C 3口・電池4,000回サイクル"
    normalized = (
        normalized.replace(
            "C1000 Gen 2との互換性は未確認</span>" + unknown_badge,
            c1000_text + "</span>" + badge,
        )
        .replace(
            "C1000（第1世代）との互換性は未確認</span>" + unknown_badge,
            gen2_text + "</span>" + badge,
        )
        .replace(
            "C1000 Gen 2との互換性は未確認" + unknown_badge,
            c1000_text + badge,
        )
        .replace(
            "C1000（第1世代）との互換性は未確認" + unknown_badge,
            gen2_text + badge,
        )
    )
    normalized = normalized.replace(
        "型番ごとの公式対応情報を確認</span>" + unknown_badge,
        "アクセサリ互換性は未確認（推奨根拠外）</span>" + unknown_badge,
    ).replace(
        "型番ごとの公式対応情報を確認" + unknown_badge,
        "アクセサリ互換性は未確認（推奨根拠外）" + unknown_badge,
    )
    if (
        "C1000 Gen 2との互換性は未確認" in normalized
        or "C1000（第1世代）との互換性は未確認" in normalized
        or normalized.count(c1000_text) < 2
        or normalized.count(gen2_text) < 2
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_ANKER_COMPATIBILITY_INVALID")
    return normalized


def _read_sales_json(path: Path) -> Mapping[str, object]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or not 1 <= metadata.st_size <= MAX_BYTES
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        raw = os.read(descriptor, metadata.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != metadata.st_size or (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
            metadata.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except EditorialPortfolioV2Failure:
        raise
    except OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if type(value) is not dict:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    return cast(Mapping[str, object], value)


def _unknown_sales_statuses(
    portfolio: EditorialPortfolioV2,
) -> dict[str, SalesStatusEvidence]:
    return {
        product.product_id: SalesStatusEvidence(
            product_id=product.product_id,
            state="UNKNOWN",
            availability_scope=None,
            official_url=None,
            status_evidence_urls=(),
            locator=None,
            basis=None,
            variant_caveat=None,
            alternative=None,
            snapshot_sha256=None,
        )
        for product in portfolio.products
    }


def _load_sales_statuses(
    portfolio: EditorialPortfolioV2,
    fact_dates: FactDateContract,
    *,
    now: datetime | None = None,
) -> dict[str, SalesStatusEvidence]:
    """Load the structured official model-sales audit, or return UNKNOWN.

    A product page merely existing is not treated as proof that a model is
    currently sold.  MODEL availability is also never treated as proof that a
    particular Rakuten CTA variant is eligible.
    """

    evaluated_at = now or datetime.now(UTC)
    if (
        type(evaluated_at) is not datetime
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() != timedelta(0)
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    evaluated_at = evaluated_at.astimezone(UTC)
    path = ROOT / SALES_STATUS_RELATIVE_PATH
    try:
        path.lstat()
    except FileNotFoundError:
        return _unknown_sales_statuses(portfolio)
    except OSError:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    document = _read_sales_json(path)
    if (
        set(document)
        != {
            "schema",
            "checked_at_utc",
            "snapshot_kind",
            "hash_contract",
            "availability_scope_policy",
            "evidence_resolution_policy",
            "publication_policy",
            "products",
        }
        or document.get("schema") != SALES_STATUS_SCHEMA
        or document.get("snapshot_kind") != SALES_STATUS_SNAPSHOT_KIND
        or document.get("hash_contract")
        != {
            "algorithm": "SHA-256",
            "canonicalization": (
                "UTF-8 JSON with recursively sorted object keys, no insignificant "
                "whitespace, and unescaped Unicode"
            ),
            "fields": list(SALES_STATUS_HASH_FIELDS),
        }
        or document.get("availability_scope_policy")
        != {
            "MODEL": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
            "VARIANT": {
                "establishes_exact_rakuten_variant": False,
                "cta_requires_separate_exact_variant_evidence": True,
            },
        }
        or document.get("evidence_resolution_policy")
        != {
            "exact_variant_reader_visible_purchase_ui_required": True,
            "reader_visible_sold_out_discontinued_or_preorder_precedes_hidden_structured_availability": True,
            "structured_data_alone_cannot_establish_available": True,
            "conflict_resolution": "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK",
            "preorder_resolution": "FAIL_CLOSED_TO_UNKNOWN",
        }
        or document.get("publication_policy")
        != {
            "AVAILABLE": {
                "state_gate": "CONDITIONAL",
                "known_state": True,
                "recheck_required": True,
            },
            "OUT_OF_STOCK": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
            "UNKNOWN": {
                "state_gate": "INELIGIBLE",
                "known_state": False,
                "recheck_required": True,
            },
            "DISCONTINUED": {
                "state_gate": "INELIGIBLE",
                "known_state": True,
                "recheck_required": True,
            },
        }
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    checked_at_value = document["checked_at_utc"]
    if type(checked_at_value) is not str or not checked_at_value.endswith("Z"):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    try:
        checked_at = datetime.fromisoformat(checked_at_value.replace("Z", "+00:00"))
    except ValueError:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    if (
        checked_at.tzinfo is None
        or checked_at.utcoffset() != datetime.min.replace(tzinfo=UTC).utcoffset()
        or checked_at - evaluated_at > SELECTION_MAX_FUTURE_SKEW
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    expected_products = {product.product_id: product for product in portfolio.products}
    if set(fact_dates.product_dates) != {
        article.article_id for article in portfolio.articles
    }:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")

    raw_products = document["products"]
    if type(raw_products) is not list:
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
    result: dict[str, SalesStatusEvidence] = {}
    row_checked_at_values: list[datetime] = []
    for raw_row in cast(list[object], raw_products):
        if type(raw_row) is not dict:
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        row = cast(Mapping[str, object], raw_row)
        if set(row) != {
            "checked_at_utc",
            "product_id",
            "state",
            "availability_scope",
            "official_url",
            "status_evidence_urls",
            "locator",
            "basis",
            "variant_caveat",
            "alternative",
            "snapshot_kind",
            "structured_snapshot_sha256",
        }:
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        product_id = row["product_id"]
        state_value = row["state"]
        row_checked_at_value = row["checked_at_utc"]
        if type(row_checked_at_value) is not str or not row_checked_at_value.endswith(
            "Z"
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        try:
            row_checked_at = datetime.fromisoformat(
                row_checked_at_value.replace("Z", "+00:00")
            )
        except ValueError:
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        if (
            type(product_id) is not str
            or product_id not in expected_products
            or product_id in result
            or type(state_value) is not str
            or state_value not in SALES_STATES
            or row_checked_at.tzinfo is None
            or row_checked_at.utcoffset()
            != datetime.min.replace(tzinfo=UTC).utcoffset()
            or row_checked_at < checked_at
            or row_checked_at - evaluated_at > SELECTION_MAX_FUTURE_SKEW
            or row["availability_scope"] not in {"MODEL", "VARIANT"}
            or row["snapshot_kind"] != SALES_STATUS_SNAPSHOT_KIND
            or row["official_url"] != expected_products[product_id].official_url
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        row_checked_at_values.append(row_checked_at)
        official_url = cast(str, row["official_url"])
        raw_evidence_urls = row["status_evidence_urls"]
        locator = row["locator"]
        basis = row["basis"]
        variant_caveat = row["variant_caveat"]
        alternative = row["alternative"]
        snapshot_sha256 = row["structured_snapshot_sha256"]
        if type(raw_evidence_urls) is not list:
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        evidence_urls = tuple(cast(list[object], raw_evidence_urls))
        if (
            not evidence_urls
            or len(evidence_urls) != len(set(evidence_urls))
            or any(
                type(url) is not str
                or urlsplit(cast(str, url)).scheme != "https"
                or not urlsplit(cast(str, url)).hostname
                for url in evidence_urls
            )
            or type(locator) is not str
            or not 3 <= len(locator) <= 2000
            or locator != locator.strip()
            or type(basis) is not str
            or not 3 <= len(basis) <= 4000
            or basis != basis.strip()
            or type(snapshot_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", snapshot_sha256) is None
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        if variant_caveat is not None:
            if (
                type(variant_caveat) is not dict
                or set(variant_caveat)
                != {"code", "detail", "establishes_exact_rakuten_variant"}
                or variant_caveat.get("establishes_exact_rakuten_variant") is not False
                or type(variant_caveat.get("code")) is not str
                or type(variant_caveat.get("detail")) is not str
            ):
                fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        hash_material = {field: row[field] for field in SALES_STATUS_HASH_FIELDS}
        if (
            hashlib.sha256(_canonical_bytes(hash_material)).hexdigest()
            != snapshot_sha256
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INVALID")
        result[product_id] = SalesStatusEvidence(
            product_id=product_id,
            state=state_value,
            availability_scope=cast(str, row["availability_scope"]),
            official_url=official_url,
            status_evidence_urls=cast(tuple[str, ...], evidence_urls),
            locator=locator,
            basis=basis,
            variant_caveat=variant_caveat,
            alternative=alternative,
            snapshot_sha256=snapshot_sha256,
        )
    if (
        set(result) != {product.product_id for product in portfolio.products}
        or not row_checked_at_values
        or min(row_checked_at_values) != checked_at
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_EVIDENCE_INCOMPLETE")
    return result


def _validated_capture_plan() -> SourceCapturePlan:
    """Load the registry/locator pair through the closed capture-plan validator."""

    try:
        return load_source_capture_plan(ROOT)
    except OfficialSourceCaptureFailure:
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")


def _validated_locator_claims(plan: SourceCapturePlan) -> dict[str, set[str]]:
    """Return only claims whose reviewed locator survived cross-document validation."""

    return {
        target.source_ref: (
            {locator.claim_id for locator in target.locators}
            if target.locator_status == "READY"
            else set()
        )
        for target in plan.targets
    }


def _selection_audit_now(now: datetime | None) -> datetime:
    evaluated_at = now or datetime.now(UTC)
    if (
        type(evaluated_at) is not datetime
        or evaluated_at.tzinfo is None
        or evaluated_at.utcoffset() != timedelta(0)
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    return evaluated_at.astimezone(UTC)


def _product_safety_requirements_from_gates(
    portfolio: EditorialPortfolioV2,
    packets: Mapping[str, Mapping[str, object]],
) -> tuple[ProductSafetyRequirement, ...]:
    """Bind each V2 article gate to its exact selected-product identities."""

    articles = {article.article_id: article for article in portfolio.articles}
    seen_articles: set[str] = set()
    gated_product_ids: set[str] = set()
    expected_gate_fields = {
        "schema",
        "required_product_ids",
        "required_authority_kinds",
        "receipt_document_ref",
        "receipt_document_schema",
        "coverage_caveat",
        "general_safety_guidance_is_not_a_receipt",
    }
    for packet in packets.values():
        article_id = packet.get("article_id")
        if type(article_id) is not str or article_id not in articles:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        if article_id in seen_articles:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        seen_articles.add(article_id)
        raw_claims = packet.get("claims")
        if type(raw_claims) is not list:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        gates = [
            raw_claim["product_specific_recall_query_gate"]
            for raw_claim in cast(list[object], raw_claims)
            if type(raw_claim) is dict
            and raw_claim.get("product_specific_recall_query_gate") is not None
        ]
        required_product_ids = list(articles[article_id].product_ids)
        if not required_product_ids:
            if gates:
                fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
            continue
        if len(gates) != 1 or type(gates[0]) is not dict:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        gate = cast(Mapping[str, object], gates[0])
        if (
            set(gate) != expected_gate_fields
            or gate.get("schema") != PRODUCT_SAFETY_GATE_SCHEMA
            or gate.get("required_product_ids") != required_product_ids
            or gate.get("required_authority_kinds") != list(REQUIRED_AUTHORITY_KINDS)
            or gate.get("receipt_document_ref")
            != PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH.as_posix()
            or gate.get("receipt_document_schema") != PRODUCT_SAFETY_RECEIPTS_SCHEMA
            or gate.get("coverage_caveat") != PRODUCT_SAFETY_GATE_CAVEAT
            or gate.get("general_safety_guidance_is_not_a_receipt") is not True
        ):
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        gated_product_ids.update(required_product_ids)
    expected_product_ids = {product.product_id for product in portfolio.products}
    if seen_articles != set(articles) or gated_product_ids != expected_product_ids:
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    return tuple(
        ProductSafetyRequirement(
            product_id=product.product_id,
            exact_model_tokens=product.official_models,
        )
        for product in portfolio.products
    )


def _product_safety_registry_context(
    *,
    requirements: Sequence[ProductSafetyRequirement],
    sources: Mapping[str, Mapping[str, object]],
    claims: Mapping[str, Mapping[str, object]],
    plan: SourceCapturePlan,
) -> ProductSafetySourceRegistryContext:
    """Project only reviewed recall/safety-notice sources into receipt authority."""

    required_product_ids = frozenset(value.product_id for value in requirements)
    target_by_ref = {target.source_ref: target for target in plan.targets}
    if len(target_by_ref) != len(plan.targets):
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    manufacturer_hosts = frozenset(
        target_by_ref[source_ref].host
        for source_ref, source in sources.items()
        if source.get("authority") == "MANUFACTURER_OFFICIAL"
        and source_ref in target_by_ref
    )
    administrative_hosts = frozenset(
        target_by_ref[source_ref].host
        for source_ref, source in sources.items()
        if source.get("authority") == "GOVERNMENT_OFFICIAL"
        and source_ref in target_by_ref
        and target_by_ref[source_ref].host.endswith(".go.jp")
    )
    if not manufacturer_hosts or not administrative_hosts:
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")

    official_sources: dict[str, ProductSafetyOfficialSource] = {}
    for source_ref, source in sources.items():
        target = target_by_ref.get(source_ref)
        capture_sha256 = source.get("immutable_capture_sha256")
        if (
            target is None
            or target.locator_status != "READY"
            or not target.locators
            or target.url != source.get("url")
            or source.get("capture_status") != "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
            or type(capture_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", capture_sha256) is None
        ):
            continue
        authority = source.get("authority")
        source_type = source.get("source_type")
        if authority == "GOVERNMENT_OFFICIAL" and source_type == "RECALL_INDEX_PAGE":
            authority_kind = "JAPAN_ADMINISTRATIVE_OFFICIAL"
            covered_product_ids = required_product_ids
        elif (
            authority == "MANUFACTURER_OFFICIAL"
            and source_type in MANUFACTURER_SAFETY_NOTICE_SOURCE_TYPES
        ):
            located_claim_ids = {locator.claim_id for locator in target.locators}
            covered_product_ids = frozenset(
                product_id
                for claim_id, claim in claims.items()
                if claim_id in located_claim_ids
                and source_ref in cast(list[str], claim.get("evidence_refs", []))
                and claim.get("classification") == "MAJOR_VERIFIABLE"
                and claim.get("evidence_level") == "A"
                and claim.get("status") == "BOUND_TO_OFFICIAL_SOURCE"
                for product_id in cast(list[str], claim.get("subject_product_ids", []))
                if product_id in required_product_ids
            )
            if not covered_product_ids:
                continue
            authority_kind = "MANUFACTURER_OFFICIAL"
        else:
            # Product pages, manuals and general safety guidance are evidence for
            # specifications or safe use, not proof that a model-specific recall
            # query was executed.
            continue
        official_sources[source_ref] = ProductSafetyOfficialSource(
            source_ref=source_ref,
            url=target.url,
            authority_kind=authority_kind,
            capture_sha256=capture_sha256,
            covered_product_ids=covered_product_ids,
        )
    return ProductSafetySourceRegistryContext(
        sources=official_sources,
        allowed_hosts_by_authority={
            "MANUFACTURER_OFFICIAL": manufacturer_hosts,
            "JAPAN_ADMINISTRATIVE_OFFICIAL": administrative_hosts,
        },
    )


def _product_safety_receipt_refs(
    status: ProductSafetyProductStatus,
) -> list[dict[str, object]]:
    """Expose receipt identities and hashes once, without copying receipt bodies."""

    return [
        {
            "authority_kind": receipt.authority_kind,
            "official_source_ref": receipt.official_source_ref,
            "checked_at_utc": receipt.checked_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "result": receipt.result,
            "capture_sha256": receipt.capture_sha256,
            "receipt_sha256": receipt.receipt_sha256,
        }
        for receipt in status.receipts
    ]


def _product_safety_publication_binding(
    audit: object,
    *,
    required_product_count: int,
) -> dict[str, object]:
    """Project the replay audit to a URL-free, non-secret publication binding."""

    if (
        type(audit) is not ProductSafetyReceiptAudit
        or type(required_product_count) is not int
        or required_product_count != 31
        or len(audit.products) != required_product_count
        or len({row.product_id for row in audit.products}) != required_product_count
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SAFETY_INVALID")
    administrative_bundle_sha256 = audit.administrative_bundle_sha256
    administrative_capture_count = audit.administrative_capture_count
    if (
        type(administrative_capture_count) is not int
        or administrative_capture_count < 0
        or (
            administrative_bundle_sha256 is None
            and administrative_capture_count != 0
        )
        or (
            administrative_bundle_sha256 is not None
            and (
                type(administrative_bundle_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", administrative_bundle_sha256)
                is None
                or administrative_capture_count
                != required_product_count
                * PRODUCT_SAFETY_ADMINISTRATIVE_CAPTURE_COUNT_PER_PRODUCT
            )
        )
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SAFETY_INVALID")
    administrative_verified_product_count = sum(
        "JAPAN_ADMINISTRATIVE_OFFICIAL" in row.verified_authority_kinds
        for row in audit.products
    )
    manufacturer_verified_product_count = sum(
        "MANUFACTURER_OFFICIAL" in row.verified_authority_kinds
        for row in audit.products
    )
    complete_product_count = sum(
        row.status == "COMPLETE_NONE_FOUND" for row in audit.products
    )
    complete = (
        audit.complete
        and administrative_capture_count
        == required_product_count
        * PRODUCT_SAFETY_ADMINISTRATIVE_CAPTURE_COUNT_PER_PRODUCT
        and administrative_verified_product_count == required_product_count
        and manufacturer_verified_product_count == required_product_count
        and complete_product_count == required_product_count
    )
    binding = {
        "schema": PRODUCT_SAFETY_PUBLICATION_BINDING_SCHEMA,
        "required_product_count": required_product_count,
        "required_authority_kinds": list(REQUIRED_AUTHORITY_KINDS),
        "required_administrative_capture_count": (
            required_product_count
            * PRODUCT_SAFETY_ADMINISTRATIVE_CAPTURE_COUNT_PER_PRODUCT
        ),
        "administrative_bundle_sha256": administrative_bundle_sha256,
        "administrative_capture_count": administrative_capture_count,
        "administrative_verified_product_count": (
            administrative_verified_product_count
        ),
        "manufacturer_verified_product_count": manufacturer_verified_product_count,
        "complete_product_count": complete_product_count,
        "complete": complete,
    }
    return {
        **binding,
        "binding_sha256": hashlib.sha256(_canonical_bytes(binding)).hexdigest(),
    }


def _selection_inclusion_reason(product_id: str, original: str) -> str:
    # Previous prose asserted sales observations that had no structured sales
    # evidence.  Keep the use-case rationale while removing that unsupported
    # assertion; sales eligibility is handled only by the separate receipt.
    replacements = {
        "PRD-ACE-CRESTA-06316": (
            "機内持ち込み候補3モデルの中で、拡張時39Lと3.2kgを両立し、"
            "容量と本体重量のバランスを比較できるため。"
        ),
        "PRD-ACE-DIFFERENCE-05721": (
            "2WAYオープン、拡張、キャスターストッパーを備え、前開き構造を"
            "重視する条件を比較できるため。"
        ),
        "PRD-ACE-MAXPASS4-01471": (
            "非拡張40Lとフロント収納を備え、拡張機能を使わず収納量を"
            "優先する条件を比較できるため。"
        ),
    }
    return replacements.get(product_id, original)


def _selection_axis_statement_is_resolved(statement: str) -> bool:
    """Reject partial evidence whose own wording records an unresolved state."""

    return (
        re.search(
            r"未確認|未照合|未実施|未記録|不明|矛盾|競合|不一致|"
            r"要確認|再確認|判断できず|特定できず|"
            r"解消(?:していない|できない|不能)|"
            r"確認(?:していない|できない)|"
            r"(?:記載|掲載)(?:が)?(?:ない|なし)|"
            r"行いません|していません|"
            r"CONFLICT|UNKNOWN|UNVERIFIED|RECHECK_REQUIRED",
            statement,
            re.IGNORECASE,
        )
        is None
    )


def _selection_performance_statement_is_substantive(statement: str) -> bool:
    """Accept a measurable product specification, never identity/support prose."""

    if not _selection_axis_statement_is_resolved(statement):
        return False
    return (
        re.search(
            r"\d+(?:\.\d+)?\s*(?:Wh|mAh|Ah|W|V|kg|g|L|dB|Pa|点|回|分)"
            r"(?![A-Za-z])",
            statement,
            re.IGNORECASE,
        )
        is not None
    )


def _selection_claim_subjects_product(
    claim: Mapping[str, object], product_id: str
) -> bool:
    subjects = claim.get("subject_product_ids")
    return type(subjects) is list and product_id in cast(list[object], subjects)


def _selection_dimension_claim_is_product_scoped(
    claim: Mapping[str, object], product_id: str
) -> bool:
    dimensions = claim.get("dimensions")
    return (
        _selection_claim_subjects_product(claim, product_id)
        and type(dimensions) is list
        and bool(dimensions)
    )


def _selection_performance_claim_is_product_scoped(
    claim_id: str, claim: Mapping[str, object], product_id: str
) -> bool:
    return (
        re.search(
            r"WARRANTY|SUPPORT|SAFETY|IDENTITY|LIFECYCLE|SALES|AVAILABILITY",
            claim_id,
            re.IGNORECASE,
        )
        is None
        and _selection_claim_subjects_product(claim, product_id)
        and _selection_performance_statement_is_substantive(
            cast(str, claim.get("statement", ""))
        )
    )


def _selection_audit_report(
    portfolio: EditorialPortfolioV2,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Build a product-specific seven-axis audit from bound source evidence."""

    evaluated_at = _selection_audit_now(now)
    fact_dates = _source_fact_date_contract(portfolio)
    sales = _load_sales_statuses(portfolio, fact_dates, now=evaluated_at)
    _registry, sources, packets, _affiliates, claims = st1704._validate_sources(
        st1704._read_fixed_json(ROOT, st1704.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    evaluated_local_date = (
        (evaluated_at + SELECTION_MAX_FUTURE_SKEW).astimezone(EDITORIAL_TIMEZONE).date()
    )
    if any(
        date.fromisoformat(_source_display_date(source)) > evaluated_local_date
        for source in sources.values()
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    capture_plan = _validated_capture_plan()
    locator_claims = _validated_locator_claims(capture_plan)
    safety_requirements = _product_safety_requirements_from_gates(portfolio, packets)
    safety_registry_context = _product_safety_registry_context(
        requirements=safety_requirements,
        sources=sources,
        claims=claims,
        plan=capture_plan,
    )
    try:
        safety_audit = load_product_safety_receipt_audit(
            ROOT,
            requirements=safety_requirements,
            registry_context=safety_registry_context,
            now=evaluated_at,
        )
    except ProductSafetyReceiptFailure:
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    safety_by_product = {status.product_id: status for status in safety_audit.products}
    if set(safety_by_product) != {product.product_id for product in portfolio.products}:
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    audit_by_product = {audit.product_id: audit for audit in portfolio.selection_audits}
    articles_by_product = {
        product.product_id: tuple(
            article
            for article in portfolio.articles
            if product.product_id in article.product_ids
        )
        for product in portfolio.products
    }
    products: list[dict[str, object]] = []
    for product in portfolio.products:
        audit = audit_by_product.get(product.product_id)
        if audit is None:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        article_claim_ids = {
            cast(str, raw_claim["claim_id"])
            for article in articles_by_product[product.product_id]
            for packet in packets.values()
            if packet["article_id"] == article.article_id
            for raw_claim in cast(list[dict[str, object]], packet["claims"])
        }
        claim_ids = tuple(
            claim_id
            for claim_id, claim in claims.items()
            if claim_id in article_claim_ids
            and claim.get("classification") == "MAJOR_VERIFIABLE"
            and claim.get("evidence_level") == "A"
            and claim.get("status") == "BOUND_TO_OFFICIAL_SOURCE"
            and bool(claim.get("evidence_refs"))
            and set(cast(list[str], claim["evidence_refs"])).issubset(sources)
        )
        published_spec_claims = tuple(
            claim_id
            for claim_id in claim_ids
            if any(
                claim_id in locator_claims.get(source_ref, set())
                for source_ref in cast(list[str], claims[claim_id]["evidence_refs"])
            )
        )
        product_published_claims = tuple(
            claim_id
            for claim_id in published_spec_claims
            if _selection_claim_subjects_product(claims[claim_id], product.product_id)
        )
        locator_refs = [
            {"source_ref": source_ref, "claim_id": claim_id}
            for claim_id in product_published_claims
            for source_ref in cast(list[str], claims[claim_id]["evidence_refs"])
            if claim_id in locator_claims.get(source_ref, set())
        ]
        dimension_claims = tuple(
            claim_id
            for claim_id in product_published_claims
            if _selection_dimension_claim_is_product_scoped(
                claims[claim_id], product.product_id
            )
        )
        performance_claims = tuple(
            claim_id
            for claim_id in product_published_claims
            if _selection_performance_claim_is_product_scoped(
                claim_id, claims[claim_id], product.product_id
            )
        )
        inclusion_reason = _selection_inclusion_reason(
            product.product_id,
            audit.inclusion_reason,
        )
        evaluated_on = min(
            fact_dates.product_dates[article.article_id][product.product_id]
            for article in articles_by_product[product.product_id]
        )
        evaluated_on_date = date.fromisoformat(evaluated_on)
        if evaluated_on_date > evaluated_local_date:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        recheck_by_date = evaluated_on_date + SELECTION_RECHECK_INTERVAL
        recheck_by = recheck_by_date.isoformat()
        source_evidence_current = (
            evaluated_at.astimezone(EDITORIAL_TIMEZONE).date() <= recheck_by_date
        )
        product_source_refs = tuple(
            dict.fromkeys(value["source_ref"] for value in locator_refs)
        )
        source_ready = (
            bool(product_source_refs)
            and source_evidence_current
            and all(
                sources[source_ref].get("capture_status")
                == "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
                and bool(locator_claims.get(source_ref))
                for source_ref in product_source_refs
            )
        )

        def product_axis_claims(
            pattern: str, *, reject_unresolved: bool = False
        ) -> tuple[str, ...]:
            return tuple(
                claim_id
                for claim_id in product_published_claims
                if (
                    not reject_unresolved
                    or _selection_axis_statement_is_resolved(
                        cast(str, claims[claim_id]["statement"])
                    )
                )
                and re.search(
                    pattern,
                    cast(str, claims[claim_id]["statement"]),
                    re.IGNORECASE,
                )
            )

        def axis_locator_refs(claim_ids: tuple[str, ...]) -> list[dict[str, str]]:
            return [value for value in locator_refs if value["claim_id"] in claim_ids]

        def axis_source_refs(claim_ids: tuple[str, ...]) -> list[str]:
            return list(
                dict.fromkeys(
                    value["source_ref"] for value in axis_locator_refs(claim_ids)
                )
            )

        warranty_period_claims = product_axis_claims(
            r"保証.{0,80}(?:\d+(?:年|か月|ヶ月)|生涯|lifetime)|"
            r"(?:\d+(?:年|か月|ヶ月)|生涯|lifetime).{0,80}保証",
            reject_unresolved=True,
        )
        warranty_region_claims = product_axis_claims(
            r"日本|国内|正規(?:販売|代理)|Japan",
            reject_unresolved=True,
        )
        warranty_channel_claims = product_axis_claims(
            r"修理|サポート|窓口|問い合わせ|受付|サービスセンター",
            reject_unresolved=True,
        )
        warranty_claims = tuple(
            dict.fromkeys(
                (
                    *warranty_period_claims,
                    *warranty_region_claims,
                    *warranty_channel_claims,
                )
            )
        )
        repair_path_claims = product_axis_claims(
            r"修理|アフターサービス|サービスセンター|修理窓口|修理受付",
            reject_unresolved=True,
        )
        maintenance_supply_claims = product_axis_claims(
            r"補修用性能部品|"
            r"(?:部品|消耗品).{0,60}(?:保有|供給|販売|交換|一覧)|"
            r"(?:交換用|交換可能|交換できる).{0,40}"
            r"(?:バッテリー|フィルター|紙パック|キャスター|ブラシ|モップ)|"
            r"(?:バッテリー|フィルター|紙パック|キャスター|ブラシ|モップ)"
            r".{0,40}(?:交換用|交換可能|交換できる|販売)|"
            r"回収|リサイクル|廃棄",
            reject_unresolved=True,
        )
        maintainability_claims = tuple(
            dict.fromkeys((*repair_path_claims, *maintenance_supply_claims))
        )
        connected_privacy_claims = product_axis_claims(
            r"ビデオマネージャー|遠隔見守り|声かけ|スクリーンショット"
        )
        connected_privacy_recheck_required = bool(connected_privacy_claims)
        shared_safety_claims = tuple(
            claim_id
            for claim_id in article_claim_ids
            if claim_id in claims
            and re.search(
                r"リコール|製品安全|安全性要求|事故情報",
                cast(str, claims[claim_id]["statement"]),
            )
            and any(
                claim_id in locator_claims.get(source_ref, set())
                for source_ref in cast(list[str], claims[claim_id]["evidence_refs"])
            )
        )
        shared_safety_locator_refs = [
            {"source_ref": source_ref, "claim_id": claim_id}
            for claim_id in shared_safety_claims
            for source_ref in cast(list[str], claims[claim_id]["evidence_refs"])
            if claim_id in locator_claims.get(source_ref, set())
        ]
        shared_safety_source_refs = list(
            dict.fromkeys(value["source_ref"] for value in shared_safety_locator_refs)
        )
        safety_status = safety_by_product[product.product_id]
        recall_query_complete = safety_status.status == "COMPLETE_NONE_FOUND"
        safety_axis_complete = (
            recall_query_complete and not connected_privacy_recheck_required
        )
        receipt_refs = _product_safety_receipt_refs(safety_status)
        receipt_locator_refs = [
            {"source_ref": receipt["official_source_ref"], "claim_id": claim_id}
            for receipt in receipt_refs
            for claim_id in sorted(
                locator_claims.get(cast(str, receipt["official_source_ref"]), set())
            )
        ]
        receipt_source_refs = list(
            dict.fromkeys(
                cast(str, receipt["official_source_ref"]) for receipt in receipt_refs
            )
        )
        safety_recheck_by = (
            min(
                receipt.checked_at + SELECTION_RECHECK_INTERVAL
                for receipt in safety_status.receipts
            )
            .date()
            .isoformat()
            if safety_status.receipts
            else recheck_by
        )
        use_case_complete = bool(locator_refs) and source_evidence_current
        dimensions_complete = bool(dimension_claims) and source_evidence_current
        performance_complete = bool(performance_claims) and source_evidence_current
        axes = [
            {
                "axis": "use_case_fit",
                "state": (
                    "EDITORIAL_JUDGMENT_FROM_BOUND_FACTS"
                    if use_case_complete
                    else "NOT_EVALUATED"
                ),
                "reason": (
                    f"{product.official_name}: {inclusion_reason}"
                    if use_case_complete
                    else f"{product.official_name}の用途適合に使う商品別一次情報が"
                    "未確認か再確認期限超過のため、推奨根拠に使いません。"
                ),
                "source_refs": list(product_source_refs) if use_case_complete else [],
                "locator_refs": locator_refs if use_case_complete else [],
                "recheck_by": recheck_by,
            },
            {
                "axis": "safety",
                "state": (
                    "OFFICIAL_SAFETY_NOTICE_CHECK_BOUND"
                    if safety_axis_complete
                    else "OFFICIAL_SAFETY_GUIDANCE_BOUND_RECHECK_REQUIRED"
                    if shared_safety_claims
                    else "NOT_EXECUTED"
                ),
                "reason": (
                    f"{product.official_name}について、型番に結び付くメーカーまたは行政の"
                    "安全・リコール確認をlocator付きで実施済みです。選定の優位性ではなく"
                    "適格性確認にだけ使います。"
                    if safety_axis_complete
                    else f"{product.official_name}は遠隔見守り・音声・カメラ・"
                    "アプリ連携によるprivacy/connected featureの利用条件と"
                    "データ取扱いの商品別照合が未完了です。"
                    "リコールreceiptが完了してもこの軸は自動完了とせず、"
                    "推奨根拠には使いません。"
                    if connected_privacy_recheck_required
                    else f"{product.official_name}の記事には行政の安全・リコール確認導線が"
                    f"ありますが、receipt状態は{safety_status.status}で、当該型番の"
                    "メーカー重要情報と行政リコールの両方の照合は未完了です。"
                    "推奨根拠には使わず、公開前に再確認します。"
                    if shared_safety_claims
                    else f"{product.official_name}の型番別リコール・重要なお知らせの"
                    f"receipt状態は{safety_status.status}で、メーカーと行政の両方の"
                    "NONE_FOUNDは成立していません。推奨根拠には使わず、公開をfail-closedにします。"
                ),
                "source_refs": (
                    receipt_source_refs
                    if safety_axis_complete
                    else shared_safety_source_refs
                ),
                "locator_refs": (
                    receipt_locator_refs
                    if safety_axis_complete
                    else shared_safety_locator_refs
                ),
                "recheck_by": safety_recheck_by,
                "receipt_status": safety_status.status,
                "missing_authority_kinds": list(safety_status.missing_authority_kinds),
                "stale_authority_kinds": list(safety_status.stale_authority_kinds),
                "matched_notice_ids": list(safety_status.matched_notice_ids),
                "receipt_refs": receipt_refs,
                "connected_privacy_recheck_required": (
                    connected_privacy_recheck_required
                ),
                "connected_privacy_source_refs": axis_source_refs(
                    connected_privacy_claims
                ),
                "connected_privacy_locator_refs": axis_locator_refs(
                    connected_privacy_claims
                ),
            },
            {
                "axis": "dimensions",
                "state": (
                    "OFFICIAL_SPEC_CONFIRMED"
                    if dimensions_complete
                    else "NOT_EVALUATED"
                ),
                "reason": (
                    f"{product.official_name}の寸法は公式sourceのlocator付き公表値で確認。"
                    if dimensions_complete
                    else f"{product.official_name}の寸法は、商品IDに結び付く"
                    "構造化寸法とlocatorがないか再確認期限超過のため未評価。"
                ),
                "source_refs": (
                    axis_source_refs(dimension_claims) if dimensions_complete else []
                ),
                "locator_refs": (
                    axis_locator_refs(dimension_claims) if dimensions_complete else []
                ),
                "recheck_by": recheck_by,
            },
            {
                "axis": "performance",
                "state": (
                    "PUBLISHED_SPEC_ONLY" if performance_complete else "NOT_EVALUATED"
                ),
                "reason": (
                    f"{product.official_name}は公表仕様だけを比較し、実使用性能は確認済みとしません。"
                    if performance_complete
                    else f"{product.official_name}の比較可能な性能一次情報がないため未評価。"
                ),
                "source_refs": (
                    axis_source_refs(performance_claims) if performance_complete else []
                ),
                "locator_refs": (
                    axis_locator_refs(performance_claims)
                    if performance_complete
                    else []
                ),
                "recheck_by": recheck_by,
            },
            {
                "axis": "warranty_and_support",
                "state": "NOT_EXECUTED",
                "reason": (
                    f"{product.official_name}の保証期間・日本向け適用条件・"
                    "修理窓口を軸別に示す構造化claimがないため未完了です。"
                    "文章の単語一致だけで完了とせず、部分情報は推奨根拠に使いません。"
                ),
                "source_refs": [],
                "locator_refs": [],
                "partial_source_refs": axis_source_refs(warranty_claims),
                "partial_locator_refs": axis_locator_refs(warranty_claims),
                "recheck_by": recheck_by,
            },
            {
                "axis": "maintainability",
                "state": "NOT_EXECUTED",
                "reason": (
                    f"{product.official_name}の修理経路と部品・消耗品・回収を"
                    "軸別に示す構造化claimがないため未完了です。"
                    "否定文や単語一致を完了証跡にせず、部分情報は推奨根拠に使いません。"
                ),
                "source_refs": [],
                "locator_refs": [],
                "partial_source_refs": axis_source_refs(maintainability_claims),
                "partial_locator_refs": axis_locator_refs(maintainability_claims),
                "recheck_by": recheck_by,
            },
            {
                "axis": "primary_source_confidence",
                "state": (
                    "OFFICIAL_SOURCE_LOCATOR_BOUND" if source_ready else "UNVERIFIED"
                ),
                "reason": (
                    f"{product.official_name}の採用根拠を公式snapshotとlocatorへ結び付けています。"
                    if source_ready
                    else f"{product.official_name}の商品別公式snapshotまたはlocatorが"
                    "不足するか、再確認期限を超えています。"
                ),
                "source_refs": list(product_source_refs) if source_ready else [],
                "locator_refs": locator_refs if source_ready else [],
                "recheck_by": recheck_by,
            },
        ]
        candidates = []
        seen_candidates: set[str] = set()
        for article in articles_by_product[product.product_id]:
            for candidate_id in article.product_ids:
                if (
                    candidate_id == product.product_id
                    or candidate_id in seen_candidates
                ):
                    continue
                candidate = portfolio.product_by_id[candidate_id]
                candidates.append(
                    {
                        "product_id": candidate.product_id,
                        "official_name": candidate.official_name,
                        "article_id": article.article_id,
                        "reason": (
                            f"{candidate.official_name}を同じ検索意図の実在候補として比較し、"
                            f"{product.official_name}は「{inclusion_reason.removesuffix('。')}」"
                            "という用途条件で残しました。"
                        ),
                    }
                )
                seen_candidates.add(candidate_id)
        if len(axes) != 7 or not candidates:
            fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        status = sales[product.product_id]
        products.append(
            {
                "product_id": product.product_id,
                "evaluated_on": evaluated_on,
                "inclusion_reason": inclusion_reason,
                "considered_candidates": candidates,
                "axes": axes,
                "manufacturer_sales_state": {
                    "state": status.state,
                    "availability_scope": status.availability_scope,
                    "official_url": status.official_url,
                    "status_evidence_urls": list(status.status_evidence_urls),
                    "locator": status.locator,
                    "basis": status.basis,
                    "variant_caveat": status.variant_caveat,
                    "alternative": status.alternative,
                    "structured_snapshot_sha256": status.snapshot_sha256,
                    "affiliate_variant_eligibility": "NOT_ATTESTED",
                },
            }
        )
    if len(products) != len(portfolio.products) or len(
        {row["product_id"] for row in products}
    ) != len(portfolio.products):
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    available = sum(
        row["manufacturer_sales_state"]["state"] == "AVAILABLE" for row in products
    )
    out_of_stock = sum(
        row["manufacturer_sales_state"]["state"] == "OUT_OF_STOCK" for row in products
    )
    discontinued = sum(
        row["manufacturer_sales_state"]["state"] == "DISCONTINUED" for row in products
    )
    verified = sum(
        row["manufacturer_sales_state"]["state"] != "UNKNOWN" for row in products
    )
    eligible = sum(
        row["manufacturer_sales_state"]["state"] in PUBLICATION_ELIGIBLE_SALES_STATES
        for row in products
    )
    completed_axis_states = {
        "EDITORIAL_JUDGMENT_FROM_BOUND_FACTS",
        "OFFICIAL_SPEC_CONFIRMED",
        "PUBLISHED_SPEC_ONLY",
        "OFFICIAL_SOURCE_LOCATOR_BOUND",
        "OFFICIAL_SAFETY_NOTICE_CHECK_BOUND",
    }
    axis_incomplete_product_ids = [
        cast(str, row["product_id"])
        for row in products
        if any(
            axis["state"] not in completed_axis_states
            or not axis["source_refs"]
            or not axis["locator_refs"]
            for axis in cast(list[dict[str, object]], row["axes"])
        )
    ]
    axis_complete = len(products) - len(axis_incomplete_product_ids)
    safety_receipt_complete = sum(
        safety_by_product[cast(str, row["product_id"])].status == "COMPLETE_NONE_FOUND"
        for row in products
    )
    safety_publication_binding = _product_safety_publication_binding(
        safety_audit,
        required_product_count=len(portfolio.products),
    )
    return {
        "schema": "RAOS_PRODUCT_SELECTION_AUDIT_V2",
        "evaluated_at_utc": evaluated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "product_safety_receipt_contract": {
            "schema": PRODUCT_SAFETY_RECEIPTS_SCHEMA,
            "document_ref": PRODUCT_SAFETY_RECEIPTS_RELATIVE_PATH.as_posix(),
            "required_authority_kinds": list(REQUIRED_AUTHORITY_KINDS),
            "complete_product_count": safety_receipt_complete,
            "incomplete_product_ids": [
                product.product_id
                for product in portfolio.products
                if safety_by_product[product.product_id].status != "COMPLETE_NONE_FOUND"
            ],
        },
        "product_safety_publication_binding": safety_publication_binding,
        "axis_order": [
            "use_case_fit",
            "safety",
            "dimensions",
            "performance",
            "warranty_and_support",
            "maintainability",
            "primary_source_confidence",
        ],
        "products": products,
        "completion": {
            "state": (
                "COMPLETE"
                if eligible == len(products) and axis_complete == len(products)
                else "INCOMPLETE"
            ),
            "product_count": len(products),
            "axis_complete_product_count": axis_complete,
            "axis_incomplete_product_ids": axis_incomplete_product_ids,
            "product_safety_receipt_complete_product_count": (safety_receipt_complete),
            "sales_state_verified_product_count": verified,
            "sales_state_available_product_count": available,
            "sales_state_out_of_stock_product_count": out_of_stock,
            "sales_state_discontinued_product_count": discontinued,
            "required_sales_evidence": "AVAILABLE_MODEL_STATE",
            "affiliate_variant_eligibility": "NOT_ATTESTED_BY_MODEL_SALES_STATE",
            "out_of_stock_recheck_product_ids": [
                cast(str, row["product_id"])
                for row in products
                if row["manufacturer_sales_state"]["state"] == "OUT_OF_STOCK"
            ],
            "unknown_product_ids": [
                cast(str, row["product_id"])
                for row in products
                if row["manufacturer_sales_state"]["state"] == "UNKNOWN"
            ],
            "ineligible_product_ids": [
                cast(str, row["product_id"])
                for row in products
                if row["manufacturer_sales_state"]["state"]
                not in PUBLICATION_ELIGIBLE_SALES_STATES
            ],
        },
    }


def _require_selection_completion(
    portfolio: EditorialPortfolioV2, *, now: datetime | None = None
) -> dict[str, object]:
    evaluated_at = _selection_audit_now(now)
    report = _selection_audit_report(portfolio, now=evaluated_at)
    completion = cast(Mapping[str, object], report["completion"])
    safety = cast(
        Mapping[str, object], report["product_safety_publication_binding"]
    )
    if (
        safety.get("complete") is not True
        or safety.get("required_product_count") != len(portfolio.products)
        or safety.get("required_administrative_capture_count")
        != len(portfolio.products)
        * PRODUCT_SAFETY_ADMINISTRATIVE_CAPTURE_COUNT_PER_PRODUCT
        or safety.get("administrative_capture_count")
        != safety.get("required_administrative_capture_count")
        or safety.get("administrative_verified_product_count")
        != len(portfolio.products)
        or safety.get("manufacturer_verified_product_count")
        != len(portfolio.products)
        or safety.get("complete_product_count") != len(portfolio.products)
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_PRODUCT_SAFETY_INCOMPLETE")
    if completion.get("axis_complete_product_count") != completion.get("product_count"):
        fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INCOMPLETE")
    if completion.get("state") != "COMPLETE":
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED")
    require_manufacturer_sales_state_for_products_v1(
        portfolio,
        tuple(product.product_id for product in portfolio.products),
        now=evaluated_at,
    )
    return report


def sanitize_source_fixtures(
    portfolio: EditorialPortfolioV2 | None = None,
) -> int:
    portfolio = portfolio or load_editorial_portfolio_v2(ROOT)
    views = _fallback_views(portfolio)
    fact_dates = _source_fact_date_contract(portfolio)
    if set(fact_dates.article_dates) != {
        article.article_id for article in portfolio.articles
    }:
        fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    sanitized = 0
    for article in portfolio.articles:
        path = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        try:
            markup = path.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
        content = _sanitize_source_markup(
            markup,
            article=article,
            portfolio=portfolio,
            views=views,
            fact_dates=fact_dates,
        )
        _atomic_write(path, content.encode("utf-8"), mode=0o644)
        sanitized += 1
    return sanitized


def _sanitize_source_markup(
    markup: str,
    *,
    article: ArticleBindingV2,
    portfolio: EditorialPortfolioV2,
    views: Mapping[str, ProductEvidenceViewV2],
    fact_dates: FactDateContract,
) -> str:
    markup = _replace_displayed_fact_date(
        markup,
        fact_dates.article_dates[article.article_id],
        product_dates=fact_dates.product_dates[article.article_id],
    )
    markup = _normalize_anker_compatibility(markup, article.article_id)
    content = materialize_article_v2(
        markup,
        article=article,
        portfolio=portfolio,
        evidence_views=views,
        mode="local",
    )
    content = _ensure_visible_intent_metadata(content, article.article_id)
    content = _reader_visible_market_exclusions(
        content,
        article.article_id,
        portfolio,
    )
    content = _deduplicate_market_candidate_routes(content, article.article_id)
    content = _validate_reader_visible_market_exclusions(
        content,
        article.article_id,
        portfolio,
    )
    return _ensure_exact_rakuten_credit(content)


def check_source_fixtures() -> int:
    """Verify all fixtures are idempotent and renderer articles match their owner."""

    portfolio = load_editorial_portfolio_v2(ROOT)
    views = _fallback_views(portfolio)
    fact_dates = _source_fact_date_contract(portfolio)
    checked = 0
    for article in portfolio.articles:
        path = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        try:
            observed = path.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
        idempotent = _sanitize_source_markup(
            observed,
            article=article,
            portfolio=portfolio,
            views=views,
            fact_dates=fact_dates,
        )
        if idempotent != observed:
            fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_FIXTURE_DRIFT")
        if article.source_kind == "st1704_renderer":
            expected = _sanitize_source_markup(
                _render_st1704_article(article.source_ref, portfolio),
                article=article,
                portfolio=portfolio,
                views=views,
                fact_dates=fact_dates,
            )
            if expected != observed:
                fail("RAOS_EDITORIAL_PORTFOLIO_SOURCE_FIXTURE_DRIFT")
        checked += 1
    return checked


def generate_old_fixtures() -> int:
    portfolio = load_editorial_portfolio_v2(ROOT)
    generated = 0
    for article in portfolio.articles:
        if article.source_kind != "st1704_renderer":
            continue
        content = _render_st1704_article(article.source_ref, portfolio)
        path = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        _atomic_write(path, content.encode("utf-8"), mode=0o644)
        generated += 1
    # Reuse the already validated registry while owner-generated bodies change.
    # Materialization receipts bind the generated output hashes privately.
    sanitize_source_fixtures(portfolio)
    return generated


def _read_posts() -> dict[str, object]:
    try:
        document = json.loads((FIXTURE_ROOT / "posts.json").read_text(encoding="utf-8"))
    except OSError, UnicodeError, json.JSONDecodeError:
        fail("RAOS_EDITORIAL_PORTFOLIO_FIXTURE_INVALID")
    if type(document) is not dict:
        fail("RAOS_EDITORIAL_PORTFOLIO_FIXTURE_INVALID")
    return cast(dict[str, object], document)


def _materialization_binding_sha256(
    binding: ProductBindingV2,
    view: ProductEvidenceViewV2,
) -> str:
    if view.state == "verified" and view.evidence is not None:
        material: object = {
            "product_id": binding.product_id,
            "state": view.state,
            "item_code": view.evidence.item_code,
            "destination_url": view.evidence.destination_url,
            "image_url": view.evidence.image_url,
            "image_sha256": view.evidence.image_sha256,
            "jan_evidence_sha256": view.jan_evidence_sha256,
        }
    else:
        material = {
            "product_id": binding.product_id,
            "state": view.state,
            "official_url": binding.official_url,
        }
    return hashlib.sha256(_canonical_bytes(material)).hexdigest()


def _materialized_cta_kind_counts(
    markup: str,
    *,
    article: ArticleBindingV2,
) -> tuple[int, int]:
    """Count the CTA kinds actually emitted for every required placement."""

    expected = {
        (product_id, placement)
        for product_id in article.product_ids
        for placement in ("product_card", "final_summary")
    }
    seen: set[tuple[str, str]] = set()
    affiliate_count = 0
    manufacturer_count = 0
    for tag in re.findall(r"<a\b[^>]*>", markup, flags=re.IGNORECASE | re.DOTALL):
        attributes = {
            name.casefold(): value
            for name, _quote, value in re.findall(
                r"([:\w-]+)\s*=\s*([\"'])(.*?)\2",
                tag,
                flags=re.DOTALL,
            )
        }
        product_id = attributes.get("data-raos-product-id")
        placement = attributes.get("data-raos-placement")
        key = (product_id or "", placement or "")
        if key not in expected:
            continue
        classes = set(attributes.get("class", "").split())
        is_affiliate = "rakuten-cta" in classes
        is_manufacturer = "official-product-link" in classes
        if key in seen or is_affiliate == is_manufacturer:
            fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
        seen.add(key)
        if is_affiliate:
            if set(attributes.get("rel", "").split()) != {"sponsored", "nofollow"}:
                fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
            affiliate_count += 1
        else:
            manufacturer_count += 1
    if seen != expected:
        fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
    return affiliate_count, manufacturer_count


def materialize(
    output_root: Path,
    *,
    mode: Literal["local", "production"],
    require_complete: bool = False,
) -> dict[str, int]:
    if not output_root.is_absolute():
        fail("RAOS_EDITORIAL_PORTFOLIO_OUTPUT_ROOT_INVALID")
    if mode not in {"local", "production"}:
        fail("RAOS_EDITORIAL_PORTFOLIO_OUTPUT_MODE_INVALID")
    portfolio_raw = cast(
        bytes,
        _read_source_snapshot(ROOT / PORTFOLIO_RELATIVE_PATH),
    )
    status_raw = _read_source_snapshot(
        ROOT / STATUS_RELATIVE_PATH,
        optional=True,
    )
    sales_state_raw = cast(
        bytes,
        _read_source_snapshot(ROOT / SALES_STATUS_RELATIVE_PATH),
    )
    portfolio = load_editorial_portfolio_v2(ROOT)
    sales_audit = portfolio.manufacturer_sales_state_audit
    if (
        portfolio_sha256(ROOT) != hashlib.sha256(portfolio_raw).hexdigest()
        or sales_audit is None
        or sales_audit.document_sha256 != hashlib.sha256(sales_state_raw).hexdigest()
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_SALES_STATE_UNVERIFIED")
    generated_at = datetime.now(UTC)
    strict_completion = mode == "production" or require_complete
    selection_report = (
        _require_selection_completion(portfolio, now=generated_at)
        if strict_completion
        else _selection_audit_report(portfolio, now=generated_at)
    )
    product_safety_binding = cast(
        Mapping[str, object],
        selection_report["product_safety_publication_binding"],
    )
    views = product_evidence_views_v2(
        ROOT,
        now=generated_at,
        require_fresh_set=strict_completion,
        require_verified_set=strict_completion,
    )
    _require_materialization_sources_current(
        portfolio_raw=portfolio_raw,
        status_raw=status_raw,
        sales_state_raw=sales_state_raw,
        portfolio=portfolio,
        views=views,
        now=generated_at,
        require_complete=strict_completion,
    )
    fixture_output = output_root / (
        LOCAL_FIXTURE_RELATIVE_PATH.name
        if mode == "local"
        else PRODUCTION_FIXTURE_RELATIVE_PATH.name
    )
    media_output = output_root / LOCAL_MEDIA_RELATIVE_PATH.name
    _ensure_directory(fixture_output / "articles", mode=0o755)
    if mode == "local":
        _ensure_directory(media_output, mode=0o755)
    posts = _read_posts()
    source_rows = posts.get("posts")
    if type(source_rows) is not list or len(source_rows) != 10:
        fail("RAOS_EDITORIAL_PORTFOLIO_FIXTURE_INVALID")
    by_local_slug = {row.get("slug"): row for row in source_rows if type(row) is dict}
    article_receipts: list[dict[str, str]] = []
    actual_affiliate_cta_count = 0
    actual_manufacturer_cta_count = 0
    for article in portfolio.articles:
        if article.local_slug not in by_local_slug:
            fail("RAOS_EDITORIAL_PORTFOLIO_FIXTURE_INVALID")
        source = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        try:
            markup = source.read_text(encoding="utf-8")
        except OSError, UnicodeError:
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
        materialized = materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views=views,
            mode=mode,
        )
        article_affiliate_ctas, article_manufacturer_ctas = (
            _materialized_cta_kind_counts(materialized, article=article)
        )
        actual_affiliate_cta_count += article_affiliate_ctas
        actual_manufacturer_cta_count += article_manufacturer_ctas
        _atomic_write(
            fixture_output / "articles" / f"{article.production_slug}.html",
            materialized.encode("utf-8"),
            mode=0o644,
        )
        article_receipts.append(
            {
                "article_id": article.article_id,
                "production_slug": article.production_slug,
                "content_sha256": hashlib.sha256(
                    materialized.encode("utf-8")
                ).hexdigest(),
            }
        )
    _atomic_write(
        fixture_output / "posts.json",
        json.dumps(posts, ensure_ascii=False, indent=2).encode("utf-8") + b"\n",
        mode=0o644,
    )
    verified = 0
    media_receipts: list[dict[str, str]] = []
    for product in portfolio.products:
        view = views[product.product_id]
        if view.state != "verified" or view.evidence is None:
            continue
        if view.image_extension is None:
            fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_INVALID")
        media_receipts.append(
            {
                "product_id": product.product_id,
                "image_sha256": view.evidence.image_sha256,
                "image_extension": view.image_extension,
            }
        )
        verified += 1
        if mode != "local":
            continue
        source = (
            ROOT
            / ".secrets/st1704-self-hosted-editorial-pilot/rakuten"
            / f"{product.product_id}.image"
        )
        try:
            payload = source.read_bytes()
        except OSError:
            fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_UNAVAILABLE")
        if hashlib.sha256(payload).hexdigest() != view.evidence.image_sha256:
            fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_INVALID")
        _atomic_write(
            media_output / f"{product.product_id}.{view.image_extension}",
            payload,
            mode=0o644,
        )
    status_sha256 = (
        hashlib.sha256(status_raw).hexdigest() if status_raw is not None else "0" * 64
    )
    verified_product_ids = {
        product_id
        for product_id, view in views.items()
        if view.state == "verified" and view.evidence is not None
    }
    product_card_count = sum(len(article.product_ids) for article in portfolio.articles)
    verified_product_card_count = sum(
        1
        for article in portfolio.articles
        for product_id in article.product_ids
        if product_id in verified_product_ids
    )
    affiliate_cta_count = product_card_count * 2
    sales_available_product_ids = {
        row.product_id for row in sales_audit.products if row.state == "AVAILABLE"
    }
    verified_affiliate_cta_count = (
        sum(
            1
            for article in portfolio.articles
            for product_id in article.product_ids
            if product_id in verified_product_ids
            and product_id in sales_available_product_ids
        )
        * 2
    )
    if (
        actual_affiliate_cta_count != verified_affiliate_cta_count
        or actual_affiliate_cta_count + actual_manufacturer_cta_count
        != affiliate_cta_count
    ):
        fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
    completion = {
        "state": (
            "COMPLETE"
            if len(verified_product_ids) == len(portfolio.products)
            and verified_product_card_count == product_card_count
            and verified_affiliate_cta_count == affiliate_cta_count
            else "INCOMPLETE"
        ),
        "product_count": len(portfolio.products),
        "verified_product_count": len(verified_product_ids),
        "product_card_count": product_card_count,
        "verified_product_card_count": verified_product_card_count,
        "affiliate_cta_count": affiliate_cta_count,
        "verified_affiliate_cta_count": actual_affiliate_cta_count,
        # Missing evidence is represented by visible non-image status, never by
        # a neutral or article-level image masquerading as product media.
        "neutral_product_image_count": 0,
        "manufacturer_fallback_cta_count": actual_manufacturer_cta_count,
        "measurement_collection_enabled": False,
    }
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
        "mode": mode,
        "generated_at": generated_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "portfolio_sha256": hashlib.sha256(portfolio_raw).hexdigest(),
        "evidence_status_sha256": status_sha256,
        "manufacturer_sales_state_sha256": sales_audit.document_sha256,
        "manufacturer_sales_state_checked_at_utc": sales_audit.checked_at_utc,
        "product_safety": dict(product_safety_binding),
        "articles": article_receipts,
        "products": [
            {
                "product_id": product.product_id,
                "state": views[product.product_id].state,
                "provider_binding_sha256": _materialization_binding_sha256(
                    product, views[product.product_id]
                ),
            }
            for product in portfolio.products
        ],
        "media": media_receipts,
        "completion": completion,
    }
    _require_materialization_sources_current(
        portfolio_raw=portfolio_raw,
        status_raw=status_raw,
        sales_state_raw=sales_state_raw,
        portfolio=portfolio,
        views=views,
        now=datetime.now(UTC),
        require_complete=strict_completion,
    )
    _atomic_write(
        fixture_output / "materialization-receipt.v2.json",
        _canonical_bytes(receipt) + b"\n",
        mode=0o600,
    )
    return {
        "articles": len(portfolio.articles),
        "verified_images": verified,
        "verified_product_cards": verified_product_card_count,
        "affiliate_ctas": verified_affiliate_cta_count,
    }


def materialize_local(
    output_root: Path,
    *,
    require_complete: bool = False,
) -> dict[str, int]:
    return materialize(
        output_root,
        mode="local",
        require_complete=require_complete,
    )


def materialize_production(output_root: Path) -> dict[str, int]:
    return materialize(output_root, mode="production")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate")
    subcommands.add_parser("capture")
    subcommands.add_parser("validate-readiness")
    subcommands.add_parser("selection-audit")
    subcommands.add_parser("generate-old-fixtures")
    subcommands.add_parser("sanitize-source-fixtures")
    subcommands.add_parser("check-source-fixtures")
    local = subcommands.add_parser("materialize-local")
    local.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / ".secrets/wordpress-local-preview",
    )
    local.add_argument(
        "--require-complete",
        action="store_true",
        help=(
            "require every owner-registered product, all 37 product images and "
            "all 74 CTA bindings to be verified"
        ),
    )
    production = subcommands.add_parser("materialize-production")
    production.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / PRODUCTION_FIXTURE_RELATIVE_PATH.parent,
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    try:
        arguments = parser().parse_args(argv)
        if arguments.command == "validate":
            portfolio = load_editorial_portfolio_v2(ROOT)
            selection = _selection_audit_report(portfolio)
            completion = cast(Mapping[str, object], selection["completion"])
            print(
                f"EditorialPortfolioV2: {len(portfolio.articles)} articles / "
                f"{len(portfolio.products)} products / "
                f"{sum(len(article.product_ids) for article in portfolio.articles)} cards / "
                "manufacturer sales states "
                f"{completion['sales_state_verified_product_count']}/"
                f"{completion['product_count']} verified"
            )
        elif arguments.command == "capture":
            counts = capture()
            print(
                "Rakuten evidence: "
                + " / ".join(f"{key}={counts[key]}" for key in sorted(counts))
            )
        elif arguments.command == "validate-readiness":
            readiness = product_evidence_readiness_v2(ROOT)
            selection = _selection_audit_report(load_editorial_portfolio_v2(ROOT))
            selection_completion = cast(Mapping[str, object], selection["completion"])
            print(
                json.dumps(
                    {
                        "complete": (
                            readiness.complete
                            and selection_completion["state"] == "COMPLETE"
                        ),
                        "product_count": readiness.product_count,
                        "verified_product_count": readiness.verified_product_count,
                        "product_card_count": readiness.product_card_count,
                        "verified_product_card_count": (
                            readiness.verified_product_card_count
                        ),
                        "affiliate_cta_count": readiness.affiliate_cta_count,
                        "verified_affiliate_cta_count": (
                            readiness.verified_affiliate_cta_count
                        ),
                        "missing_registry_product_ids": list(
                            readiness.missing_registry_product_ids
                        ),
                        "unverified_product_ids": list(
                            readiness.unverified_product_ids
                        ),
                        "manufacturer_sales_state": selection_completion,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            if not readiness.complete or selection_completion["state"] != "COMPLETE":
                fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INCOMPLETE")
        elif arguments.command == "selection-audit":
            report = _selection_audit_report(load_editorial_portfolio_v2(ROOT))
            print(_canonical_bytes(report).decode("utf-8"))
        elif arguments.command == "generate-old-fixtures":
            print(f"Generated {generate_old_fixtures()} Editorial V2 fixtures")
        elif arguments.command == "sanitize-source-fixtures":
            print(f"Sanitized {sanitize_source_fixtures()} Editorial V2 fixtures")
        elif arguments.command == "check-source-fixtures":
            print(f"Checked {check_source_fixtures()} Editorial V2 fixtures")
        elif arguments.command == "materialize-local":
            counts = materialize_local(
                arguments.output_root.resolve(),
                require_complete=arguments.require_complete,
            )
            print(
                f"Local materialization: {counts['articles']} articles / "
                f"{counts['verified_images']} verified images / "
                f"{counts['verified_product_cards']} verified cards / "
                f"{counts['affiliate_ctas']} affiliate CTAs"
            )
        else:
            counts = materialize_production(arguments.output_root.resolve())
            print(f"Production materialization: {counts['articles']} articles")
        return 0
    except (EditorialPortfolioV2Failure, EditorialPilotFailure) as error:
        sys.stderr.write(f"{error}\n")
        return 69
    except rakuten_capture.RakutenProductCaptureFailure as error:
        sys.stderr.write(f"RAOS_EDITORIAL_PORTFOLIO_CAPTURE_{error.code.value}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
