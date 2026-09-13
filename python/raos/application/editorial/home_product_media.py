"""Pure, closed six-product media projection for the registered home page."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from hashlib import sha256
from html import escape
import re
from typing import Any
from urllib.parse import parse_qs, urlsplit

from raos.application.editorial.purchase_support import (
    media_allowed,
    purchasable_offer,
    resolve_product_media,
)
from raos.application.editorial.reader_html import fragment

SCHEMA = "RAOS_HOME_PRODUCT_MEDIA_V1"
GROUPS = {
    "41": ("PRD-PANASONIC-NP-TMLK1", "PRD-SIROCA-SS-MA251"),
    "83": ("PRD-PROTECA-AEROFLEX-DX2-01521", "PRD-SAMSONITE-C-LITE-CS2-09007"),
    "30": ("PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY", "PRD-SWITCHBOT-K11-PRO"),
}
MODELS = {
    "PRD-PANASONIC-NP-TMLK1": "NP-TMLK1-K",
    "PRD-SIROCA-SS-MA251": "SS-MA251",
    "PRD-PROTECA-AEROFLEX-DX2-01521": "01521-09",
    "PRD-SAMSONITE-C-LITE-CS2-09007": "CS2*09007 / 134679-1041",
    "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY": "F155260",
    "PRD-SWITCHBOT-K11-PRO": "K11+ Pro",
}
SLUGS = {
    "41": "countertop-dishwasher-for-small-households",
    "83": "lightweight-carry-on-suitcase-under-3kg",
    "30": "compact-robot-vacuum-shortlist",
}
MINI = "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY"
EVIDENCE = "changes/wordpress-direct-publish-v1/official-media-sources.md"
MINI_IMAGE = (
    "/wp-content/themes/kurashinoshirube-child/assets/images/roomba-mini-official.jpg"
)
MINI_LINK = "/compact-robot-vacuum-shortlist/#product-robot-roomba-mini"
MINI_NAME = (
    "アイロボット Roomba® Mini 掃除機＆床拭きロボット + AutoEmpty™ 充電ステーション"
)


def slot(product_id: str) -> str:
    if product_id not in MODELS:
        raise ValueError("HOME_MEDIA_PRODUCT_NOT_ALLOWED")
    return (
        '<div class="ks-home-product-slot" data-ks-home-product="'
        + product_id
        + '"></div>'
    )


def build_home_product_media(
    catalog: Mapping[str, Any],
    home_config: Mapping[str, Any],
    rakuten_registry: list[dict[str, Any]],
    official_image: bytes,
) -> dict[str, Any]:
    """Return safe slots and verified media, without modifying article bindings.

    The entry owner places only slots in saved HTML, then calls bind with the
    completed body. The existing theme metadata carries the bound projection.
    """
    expected = {
        "schema": SCHEMA,
        "post_id": 15,
        "post_type": "page",
        "slug": "home",
        "groups": {key: list(value) for key, value in GROUPS.items()},
    }
    if dict(home_config) != expected or type(home_config.get("post_id")) is not int:
        raise ValueError("HOME_MEDIA_SCOPE_INVALID")
    selected = [p for p in catalog.get("products", []) if p.get("product_id") in MODELS]
    if len(selected) != len(MODELS) or len({p["product_id"] for p in selected}) != len(
        MODELS
    ):
        raise ValueError("HOME_MEDIA_PRODUCT_IDENTITY_INVALID")
    products = {p["product_id"]: p for p in selected}
    for pid, product in products.items():
        review = product.get("image_review", {})
        offer = purchasable_offer(product, catalog)
        if (
            product.get("exact_model") != MODELS[pid]
            or review.get("evidence") != EVIDENCE
            or not media_allowed(product, catalog)
            or offer is None
            or offer.get("product_model") != MODELS[pid]
        ):
            raise ValueError("HOME_MEDIA_PRODUCT_NOT_VERIFIED")
    resolved = resolve_product_media(
        {"products": selected}, rakuten_registry, official_image
    )
    output: dict[str, Any] = {
        "schema": SCHEMA,
        "post_id": 15,
        "post_type": "page",
        "slug": "home",
        "slots": {},
        "products": {},
    }
    for post_id, ids in GROUPS.items():
        articles = [
            a for a in catalog.get("articles", []) if a.get("post_id") == int(post_id)
        ]
        if (
            len(articles) != 1
            or articles[0].get("slug") != SLUGS[post_id]
            or articles[0].get("kind") != "comparison"
            or not set(ids) <= set(articles[0].get("product_ids", []))
        ):
            raise ValueError("HOME_MEDIA_SOURCE_ARTICLE_INVALID")
        article = articles[0]
        output["slots"][int(post_id)] = "".join(slot(pid) for pid in ids)
        for pid in ids:
            if pid in article.get("media_exclusions", {}):
                raise ValueError("HOME_MEDIA_SOURCE_EXCLUDED")
            product, media = products[pid], resolved[pid]
            chunks = [
                '<figure class="ks-home-product-image" data-ks-home-product="'
                + pid
                + '">'
            ]
            source_digests: dict[str, str] = {}
            if pid == MINI:
                if (
                    not media.get("official")
                    or product.get("anchor") != "product-robot-roomba-mini"
                ):
                    raise ValueError("HOME_MEDIA_OFFICIAL_IDENTITY_INVALID")
                source_digests["official"] = media["sha256"]
                chunks += [
                    '<a href="'
                    + MINI_LINK
                    + '"><img src="'
                    + MINI_IMAGE
                    + '" width="2048" height="2048" loading="lazy" decoding="async"'
                    + ' alt="Roomba Mini（白）とAutoEmpty充電ステーション。公式提供写真。"></a>',
                    "<figcaption>"
                    + MINI_NAME
                    + '<br>写真：<a href="https://irobotjp.mediaroom.com/media-kits?item=28">'
                    + "アイロボットジャパン 公式掲載用素材</a></figcaption>",
                ]
            else:
                if media.get("official") or article["slug"] not in media.get(
                    "slugs", []
                ):
                    raise ValueError("HOME_MEDIA_SOURCE_SCOPE_INVALID")
                record = next(r for r in rakuten_registry if r.get("product_id") == pid)
                for size in ("240",):
                    raw = media["sizes"][size]["raw"]
                    nodes = list(fragment(raw).walk())
                    anchors = [n for n in nodes if n.tag == "a"]
                    images = [n for n in nodes if n.tag == "img"]
                    if (
                        len(anchors) != 1
                        or len(images) != 1
                        or images[0].parent is not anchors[0]
                    ):
                        raise ValueError("HOME_MEDIA_IMAGE_LINK_INVALID")
                    if (
                        anchors[0].text()
                        or any(n.tag not in ("", "a", "img") for n in nodes)
                        or re.search(r"(?:¥|￥)\s*[0-9]|[0-9][0-9,]*\s*円", raw)
                    ):
                        raise ValueError("HOME_MEDIA_IMAGE_ONLY_REQUIRED")
                    link = anchors[0]
                    destination = urlsplit(link.attrs.get("href") or "")
                    merchants = parse_qs(destination.query).get("pc", [])
                    if len(merchants) != 1:
                        raise ValueError("HOME_MEDIA_DESTINATION_INVALID")
                    merchant, registered = (
                        urlsplit(merchants[0]),
                        urlsplit(record["item_url"]),
                    )
                    if (
                        destination.hostname != "hb.afl.rakuten.co.jp"
                        or (merchant.scheme, merchant.hostname, merchant.path)
                        != (registered.scheme, registered.hostname, registered.path)
                        or merchant.username
                        or merchant.password
                        or set((link.attrs.get("rel") or "").split())
                        != {"nofollow", "sponsored", "noopener"}
                        or link.attrs.get("target") != "_blank"
                    ):
                        raise ValueError("HOME_MEDIA_DESTINATION_INVALID")
                    source_digests[size] = sha256(raw.encode()).hexdigest()
                    chunks += [
                        '<div class="ks-home-rakuten-' + size + '">',
                        raw,
                        "</div>",
                    ]
                chunks += [
                    "<figcaption>"
                    + escape(product["name"])
                    + "（楽天市場）</figcaption>"
                ]
            chunks.append("</figure>")
            html = "".join(chunks)
            output["products"][pid] = {
                "exact_model": MODELS[pid],
                "source_article_slug": article["slug"],
                "source_sha256": source_digests,
                "html": html,
                "sha256": sha256(html.encode()).hexdigest(),
            }
    return output


def bind_home_product_media(
    projection: Mapping[str, Any], home_body: str
) -> dict[str, Any]:
    """Bind the exact safe saved body; raw image snippets never pass through KSES."""
    if (
        projection.get("schema") != SCHEMA
        or projection.get("post_id") != 15
        or projection.get("post_type") != "page"
        or projection.get("slug") != "home"
        or set(projection.get("products", {})) != set(MODELS)
    ):
        raise ValueError("HOME_MEDIA_PROJECTION_INVALID")
    if not isinstance(home_body, str) or not home_body:
        raise ValueError("HOME_MEDIA_BODY_REQUIRED")
    for pid in MODELS:
        if home_body.count(slot(pid)) != 1:
            raise ValueError("HOME_MEDIA_SLOT_INVALID")
    actual_slots = [
        n for n in fragment(home_body).walk() if n.has("ks-home-product-slot")
    ]
    if len(actual_slots) != len(MODELS):
        raise ValueError("HOME_MEDIA_SLOT_INVALID")
    result = deepcopy(dict(projection))
    result.pop("slots", None)
    result["body_sha256"] = sha256(home_body.encode()).hexdigest()
    return result
