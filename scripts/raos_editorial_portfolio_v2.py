#!/usr/bin/env python3
"""Capture, generate, and locally materialize EditorialPortfolioV2."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from typing import Any, Literal, Mapping, NoReturn, Sequence, cast
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = ROOT / "python"
if PYTHON_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, PYTHON_ROOT.as_posix())

from raos.adapters import self_hosted_editorial_rakuten_capture as rakuten_capture  # noqa: E402
from raos.adapters.self_hosted_editorial_pilot_json import (  # noqa: E402
    read_rakuten_product_evidence,
)
from raos.application.editorial import self_hosted_editorial_pilot as st1704  # noqa: E402
from raos.application.editorial.editorial_portfolio_v2 import (  # noqa: E402
    LOCAL_FIXTURE_RELATIVE_PATH,
    LOCAL_MEDIA_RELATIVE_PATH,
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
    product_evidence_views_v2,
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
MAX_BYTES = 4 * 1024 * 1024


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
    except (TypeError, ValueError, UnicodeError):
        fail("RAOS_EDITORIAL_PORTFOLIO_JSON_INVALID")


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
        jan=binding.official_jan,
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
    _atomic_write(
        output_directory / f"{binding.product_id}.fixed-item-response.v2.json",
        raw,
        mode=0o600,
    )
    return ("not_found" if not rows else "ambiguous"), hashlib.sha256(raw).hexdigest()


def capture() -> dict[str, int]:
    portfolio = load_editorial_portfolio_v2(ROOT)
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
                _validate_rakuten_identity(binding, existing)
                existing_at = datetime.fromisoformat(
                    existing.retrieved_at.replace("Z", "+00:00")
                ).astimezone(UTC)
            except (EditorialPilotFailure, EditorialPortfolioV2Failure, ValueError):
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
                if error.code is rakuten_capture.RakutenProductCaptureFailureCode.PRODUCT_NOT_FOUND:
                    state = "not_found"
                elif error.code is rakuten_capture.RakutenProductCaptureFailureCode.PRODUCT_IDENTITY_AMBIGUOUS:
                    state = "ambiguous"
                else:
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

    EditorialPortfolioV2 immediately rewrites the rendered CTA and image to the
    official/neutral fallback. Provider evidence is acquired only by `capture`,
    so source fixture generation cannot be blocked by an expired private row.
    """

    allowed_variants = cast(list[object], identity["allowed_variants"])
    if binding.representative_model not in allowed_variants:
        fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    raw_item_code = identity.get("item_code") or binding.rakuten_item_code
    item_code = (
        cast(str, raw_item_code)
        if type(raw_item_code) is str
        else f"raos-neutral:{10_000_000 + sequence}"
    )
    shop, item = item_code.split(":", 1)
    item_url = f"https://item.rakuten.co.jp/{shop}/{item}/"
    mobile_url = f"https://m.rakuten.co.jp/{shop}/i/{item}/"
    destination_url = "https://hb.afl.rakuten.co.jp/hgc/raos-local-render/?" + urlencode(
        {"pc": item_url, "m": mobile_url, "rafcid": "raos-local-render"}
    )
    image_url = (
        f"https://thumbnail.image.rakuten.co.jp/@0_mall/{shop}/"
        "cabinet/raos-local-render.jpg?_ex=128x128"
    )
    title_tokens = [
        cast(str, value) for value in cast(list[object], identity["required_title_tokens"])
    ]
    kind_tokens = [
        cast(str, value) for value in cast(list[object], identity["product_kind_tokens"])
    ]
    item_name = " ".join(dict.fromkeys([product_name, *title_tokens, kind_tokens[0]]))
    official_jan = identity.get("jan")
    if official_jan is not None and type(official_jan) is not str:
        fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    request_base = {
        "api_version": "2026-07-01",
        "endpoint": (
            "https://openapi.rakuten.co.jp/ichibams/api/"
            "IchibaItem/Search/20260701"
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
    _registry, sources, _packets, affiliates, claims = st1704._validate_sources(
        st1704._read_fixed_json(ROOT, st1704.SOURCE_REGISTRY_RELATIVE_PATH)
    )
    media = st1704._validate_media(
        st1704._read_fixed_json(ROOT, st1704.MEDIA_REGISTRY_RELATIVE_PATH)
    )
    article = articles[article_id]
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
            cast(Mapping[str, object], private_media[media_ref])["identity"],
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
    )
    content = st1704._Renderer(
        article=article,
        routes=routes,
        sources=sources,
        claims=claims,
        cards=cards,
        evidences=evidences,
        alts={cast(str, asset["product_id"]): cast(str, asset["alt"]) for asset in media_records},
    ).render(ast)
    neutral = (
        "/wp-content/themes/kurashinoshirube-child/assets/images/"
        + ("article-portable-power-guide.webp" if "power" in article_id or "anker" in article_id else "home-hero.webp")
    )
    for evidence in evidences.values():
        content = content.replace(evidence.image_url, neutral)
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


def sanitize_source_fixtures(
    portfolio: EditorialPortfolioV2 | None = None,
) -> int:
    portfolio = portfolio or load_editorial_portfolio_v2(ROOT)
    views = _fallback_views(portfolio)
    sanitized = 0
    for article in portfolio.articles:
        path = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        try:
            markup = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
        content = materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views=views,
            mode="local",
        )
        _atomic_write(path, content.encode("utf-8"), mode=0o644)
        sanitized += 1
    return sanitized


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
    except (OSError, UnicodeError, json.JSONDecodeError):
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
        }
    else:
        material = {
            "product_id": binding.product_id,
            "state": view.state,
            "official_url": binding.official_url,
        }
    return hashlib.sha256(_canonical_bytes(material)).hexdigest()


def materialize(
    output_root: Path,
    *,
    mode: Literal["local", "production"],
) -> dict[str, int]:
    if not output_root.is_absolute():
        fail("RAOS_EDITORIAL_PORTFOLIO_OUTPUT_ROOT_INVALID")
    if mode not in {"local", "production"}:
        fail("RAOS_EDITORIAL_PORTFOLIO_OUTPUT_MODE_INVALID")
    portfolio = load_editorial_portfolio_v2(ROOT)
    views = product_evidence_views_v2(
        ROOT, require_fresh_set=mode == "production"
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
    by_local_slug = {
        row.get("slug"): row for row in source_rows if type(row) is dict
    }
    article_receipts: list[dict[str, str]] = []
    for article in portfolio.articles:
        if article.local_slug not in by_local_slug:
            fail("RAOS_EDITORIAL_PORTFOLIO_FIXTURE_INVALID")
        source = FIXTURE_ROOT / "articles" / f"{article.production_slug}.html"
        try:
            markup = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
        materialized = materialize_article_v2(
            markup,
            article=article,
            portfolio=portfolio,
            evidence_views=views,
            mode=mode,
        )
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
    for product in portfolio.products:
        view = views[product.product_id]
        if (
            mode != "local"
            or view.state != "verified"
            or view.evidence is None
        ):
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
        _atomic_write(media_output / f"{product.product_id}.image", payload, mode=0o644)
        verified += 1
    status_path = ROOT / STATUS_RELATIVE_PATH
    try:
        status_sha256 = hashlib.sha256(status_path.read_bytes()).hexdigest()
    except OSError:
        status_sha256 = "0" * 64
    receipt = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_MATERIALIZATION_RECEIPT_V2",
        "mode": mode,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "portfolio_sha256": portfolio_sha256(ROOT),
        "evidence_status_sha256": status_sha256,
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
    }
    _atomic_write(
        fixture_output / "materialization-receipt.v2.json",
        _canonical_bytes(receipt) + b"\n",
        mode=0o600,
    )
    return {"articles": len(portfolio.articles), "verified_images": verified}


def materialize_local(output_root: Path) -> dict[str, int]:
    return materialize(output_root, mode="local")


def materialize_production(output_root: Path) -> dict[str, int]:
    return materialize(output_root, mode="production")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(allow_abbrev=False)
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("validate")
    subcommands.add_parser("capture")
    subcommands.add_parser("generate-old-fixtures")
    subcommands.add_parser("sanitize-source-fixtures")
    local = subcommands.add_parser("materialize-local")
    local.add_argument(
        "--output-root",
        type=Path,
        default=ROOT / ".secrets/wordpress-local-preview",
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
            print(
                f"EditorialPortfolioV2: {len(portfolio.articles)} articles / "
                f"{len(portfolio.products)} products / "
                f"{sum(len(article.product_ids) for article in portfolio.articles)} cards"
            )
        elif arguments.command == "capture":
            counts = capture()
            print(
                "Rakuten evidence: "
                + " / ".join(f"{key}={counts[key]}" for key in sorted(counts))
            )
        elif arguments.command == "generate-old-fixtures":
            print(f"Generated {generate_old_fixtures()} Editorial V2 fixtures")
        elif arguments.command == "sanitize-source-fixtures":
            print(f"Sanitized {sanitize_source_fixtures()} Editorial V2 fixtures")
        elif arguments.command == "materialize-local":
            counts = materialize_local(arguments.output_root.resolve())
            print(
                f"Local materialization: {counts['articles']} articles / "
                f"{counts['verified_images']} verified images"
            )
        else:
            counts = materialize_production(arguments.output_root.resolve())
            print(
                f"Production materialization: {counts['articles']} articles"
            )
        return 0
    except (EditorialPortfolioV2Failure, EditorialPilotFailure) as error:
        sys.stderr.write(f"{error}\n")
        return 69
    except rakuten_capture.RakutenProductCaptureFailure as error:
        sys.stderr.write(f"RAOS_EDITORIAL_PORTFOLIO_CAPTURE_{error.code.value}\n")
        return 69


if __name__ == "__main__":
    raise SystemExit(main())
