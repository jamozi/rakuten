"""Compile the adopted purchase-support contract to bounded public article fragments."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from hashlib import sha256
from html import escape
import json
import re
from typing import Any, cast
from urllib.parse import urlsplit

from raos.domain.editorial.purchase_support import (
    POLICY,
    PLACEMENTS,
    MAX_PRICE_AGE,
    money,
    timestamp,
    resolve_offer,
    offer_states,
)
from raos.application.editorial.reader_html import Element, block, fragment
from raos.application.editorial.local_reader_guides import build_local_guides
from raos.application.editorial.reader_running_cost import render_cost_profiles

STAGES = {
    "installation": ("設置", "dishwasher-installation-measurement"),
    "water": ("給水・排水", "dishwasher-water-supply-methods"),
    "cost": ("維持費", "dishwasher-running-cost"),
    "detergent": ("洗剤", "dishwasher-detergent-guide"),
    "maintenance": ("手入れ", "dishwasher-cleaning-guide"),
}
MAIN_SLUG = "countertop-dishwasher-for-small-households"
ORIGIN = "https://kurashinoshirube.com"
JST = timezone(timedelta(hours=9))
EDITOR = "暮らしのしるべ編集部"
LABELS = {
    "price_yen": "税込本体",
    "shipping_yen": "送料",
    "required_items_yen": "必須品",
}
# Each guide renders only the facts of its own stage; shared conditions are
# linked to the guide that owns them instead of being repeated verbatim.
GUIDE_REQUIREMENTS = {
    "installation": ("dimensions", "door", "clearance", "installation", "drainage"),
    "water": ("water_supply",),
    "cost": ("energy", "water"),
    "detergent": ("detergent", "detergent_test", "prohibited", "accessories"),
    "maintenance": ("maintenance",),
}
# Rows of the four-model decision table placed under the first heading.
GUIDE_TABLE_ROWS = {
    "water": ("給水方式", "1回の給水量と止める合図", "排水ホース"),
    "detergent": ("使える洗剤の種類", "1回分の目安", "タブレットの条件", "公表試験条件の洗剤量"),
    "maintenance": ("毎回", "月1回程度", "長く使わないとき"),
    "cost": ("1回の消費電力量", "1回の使用水量", "洗剤の1回分", "計算できる費目"),
}
DISCLOSURE = (
    "この記事には広告・アフィリエイトリンク（楽天アフィリエイトの購入・商品画像リンク）が含まれます。"
    "運営者は購入リンクから成果報酬を受け取る場合があります。"
    "実機で使用した評価ではなく、性能の評価に価格や広告報酬を加点しません。"
)
BYLINE = '<p class="ps-byline">執筆・商品情報確認：' + EDITOR + "</p>"
EDITOR_LINE = (
    '<p class="ps-editor">編集・確認：'
    + EDITOR
    + '／訂正依頼：<a href="/about-ad-policy/#production-about-correction">運営・広告方針のお問い合わせ先</a></p>'
)
RAKUTEN_CREDIT = (
    '<p class="ps-note ps-media-credit">商品画像と商品情報の取得に Rakuten Developers API を利用しています'
    '（<a href="https://developers.rakuten.com/">Supported by Rakuten Developers</a>）。</p>'
)
MEDIA_WITHHELD = (
    '<p class="ps-product-media-note">商品写真：販売先を照合できるまで未掲載。</p>'
)


def canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def https(url: object) -> bool:
    if not isinstance(url, str):
        return False
    u = urlsplit(url)
    return (
        u.scheme == "https" and bool(u.hostname) and not u.username and not u.password
    )


def tidy(text: object) -> str:
    """Reader-facing notation: wave dash, no space after a full stop, no ideographic space."""
    return (
        str(text)
        .replace("～", "〜")
        .replace("。 ", "。")
        .replace("　", " ")
    )


def jp_date(value: object) -> str:
    """'2026-09-11', an ISO timestamp or a datetime (shown in JST) as '2026年9月11日'."""
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        day = date.fromisoformat(value)
    else:
        moment = value if isinstance(value, datetime) else timestamp(value)
        if moment is None or moment.tzinfo is None:
            return "未確認"
        day = moment.astimezone(JST).date()
    return f"{day.year}年{day.month}月{day.day}日"


def jp_datetime(value: object) -> str:
    moment = value if isinstance(value, datetime) else timestamp(value)
    if moment is None or moment.tzinfo is None:
        return "未確認"
    local = moment.astimezone(JST)
    return f"{local.year}年{local.month}月{local.day}日 {local.hour:02d}:{local.minute:02d}"


def current_time(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("PURCHASE_NOW_TIMEZONE_REQUIRED")
    return now


def validate_catalog(catalog: Mapping[str, Any]) -> None:
    if (
        catalog.get("schema") != "RAOS_READER_PURCHASE_SUPPORT_V1"
        or catalog.get("policy") != POLICY
    ):
        raise ValueError("PURCHASE_POLICY_INVALID")
    products = catalog.get("products", [])
    ids = [p["product_id"] for p in products]
    if len(ids) != 16 or len(set(ids)) != 16:
        raise ValueError("PURCHASE_SIXTEEN_IDENTITIES_REQUIRED")
    articles = catalog.get("articles", [])
    if len({a["article_id"] for a in articles}) != len(articles):
        raise ValueError("PURCHASE_DUPLICATE_ARTICLE")
    comparisons = [a for a in articles if a["kind"] == "comparison"]
    if len(comparisons) != 4 or any(
        len(a["product_ids"]) != 4 or not set(a["product_ids"]) <= set(ids)
        for a in comparisons
    ):
        raise ValueError("PURCHASE_FOUR_COMPARISONS_REQUIRED")
    for p in products:
        if not p["exact_model"] or not https(p["official_url"]):
            raise ValueError("PURCHASE_IDENTITY_SOURCE_REQUIRED")
        for f in p["facts"]:
            if f.get("exact_model") != p["exact_model"]:
                raise ValueError("PURCHASE_FACT_MODEL_MISMATCH")
            if (
                f["state"] not in {"KNOWN", "PRESERVED", "UNKNOWN"}
                or not https(f["source_url"])
                or not f["locator"]
                or not f["checked_at"]
            ):
                raise ValueError("PURCHASE_FACT_SOURCE_REQUIRED")
        for f in p.get("guide_facts", []):
            if (
                f["exact_model"] != p["exact_model"]
                or not https(f["source_url"])
                or not f["locator"]
                or not f["checked_at"]
            ):
                raise ValueError("PURCHASE_GUIDE_MODEL_SOURCE_MISMATCH")
        for key, field in p.get("installation", {}).items():
            if key not in {
                "width_mm",
                "depth_mm",
                "height_mm",
                "door_depth_mm",
                "door_height_mm",
                "above_mm",
                "left_mm",
                "right_mm",
                "rear_mm",
            }:
                raise ValueError("PURCHASE_INSTALLATION_KEY_INVALID")
            if field is not None and (not money(field) or field > 10000):
                raise ValueError("PURCHASE_INSTALLATION_VALUE_INVALID")
    offers = catalog.get("offers", [])
    if len({o["offer_id"] for o in offers}) != len(offers):
        raise ValueError("PURCHASE_DUPLICATE_OFFER")
    if len(
        {
            (o["product_id"], o.get("variant_id", o.get("variant")), o["seller_id"])
            for o in offers
        }
    ) != len(offers):
        raise ValueError("PURCHASE_DUPLICATE_SELLER_VARIANT")
    for o in offers:
        p = next((p for p in products if p["product_id"] == o.get("product_id")), None)
        if (
            not p
            or o.get("product_model") != p["exact_model"]
            or not https(
                o.get("merchant_url") or o.get("affiliate_url") or o.get("url")
            )
            or not https(o.get("source_url"))
        ):
            raise ValueError("PURCHASE_OFFER_IDENTITY_MISMATCH")
        for key in ("price_yen", "shipping_yen", "required_items_yen"):
            if o.get(key) is not None and not money(o[key]):
                raise ValueError("PURCHASE_MONEY_INVALID")
        if not timestamp(o.get("checked_at")) or not timestamp(o.get("valid_until")):
            raise ValueError("PURCHASE_OFFER_DATE_REQUIRED")
        if (o.get("affiliate") is True or o.get("affiliate_ready") is True) and (
            o.get("advertiser_authorized") is not True
            or o.get("link_usage_authorized") is not True
            or o.get("site_origin") != ORIGIN
            or not resolve_offer(o)["affiliate_ready"]
        ):
            raise ValueError("PURCHASE_AFFILIATE_RIGHTS_REQUIRED")
        if any(
            k in o
            for k in (
                "raw",
                "reward_rate",
                "commission",
                "credential",
                "provider_measurement_id",
            )
        ):
            raise ValueError("PURCHASE_PRIVATE_OFFER_FIELD")
    issues = catalog.get("research_issues", [])
    for pid in ids:
        if not any(
            o["product_id"] == pid and o.get("identity_verified") for o in offers
        ) and not any(i["product_id"] == pid for i in issues):
            raise ValueError("PURCHASE_DESTINATION_OR_ISSUE_REQUIRED")
    for i in issues:
        if (
            i.get("product_id") not in ids
            or i.get("kind")
            not in {"official_documents", "manufacturer_inquiry", "home_or_hands_on"}
            or not all(
                i.get(k)
                for k in (
                    "status",
                    "impact",
                    "target_url",
                    "next_check_on",
                    "alternative",
                )
            )
        ):
            raise ValueError("PURCHASE_RESEARCH_MANAGEMENT_REQUIRED")
    targets = {a["article_id"] for a in articles}
    anchors = {p["product_id"]: p["anchor"] for p in products}
    for r in catalog.get("routes", []):
        if (
            r["product_id"] not in ids
            or r["article_id"] not in targets
            or r["stage"] not in STAGES
            or r["anchor"] != anchors.get(r["product_id"])
        ):
            raise ValueError("PURCHASE_ROUTE_INVALID")


def eligible_link(o: Mapping[str, Any]) -> bool:
    return resolve_offer(o)["href"] is not None


def product_offers(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [o for o in catalog["offers"] if o["product_id"] == p["product_id"]]


def purchasable_offer(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> dict[str, Any] | None:
    return next((o for o in product_offers(p, catalog) if eligible_link(o)), None)


def verified_offers(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [o for o in product_offers(p, catalog) if o.get("identity_verified") is True]


def media_allowed(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> bool:
    """A Rakuten image block is an affiliate link, so it needs a matched, orderable seller.

    Products the article itself describes as 販売先未確認 or 売り切れ get no
    image link at all; the same offer data drives both decisions.
    """
    return purchasable_offer(p, catalog) is not None


def price_expiry(o: Mapping[str, Any]) -> datetime | None:
    checked, deadline = timestamp(o.get("checked_at")), timestamp(o.get("valid_until"))
    if not checked or not deadline:
        return None
    return min(deadline, checked + MAX_PRICE_AGE)


def price_expired(o: Mapping[str, Any], now: datetime) -> bool:
    expiry = price_expiry(o)
    checked, deadline = timestamp(o.get("checked_at")), timestamp(o.get("valid_until"))
    return expiry is None or checked is None or deadline is None or deadline <= checked or now >= expiry


def attrs(values: Mapping[str, object]) -> str:
    return "".join(f' {k}="{escape(str(v), quote=True)}"' for k, v in values.items())


def internal_link(href: str, product_id: str, label: str) -> str:
    return (
        '<a href="'
        + escape(href, quote=True)
        + '" data-raos-product-id="'
        + escape(product_id, quote=True)
        + '" data-raos-link-purpose="internal_navigation">'
        + escape(label)
        + "</a>"
    )


def condition_product_links(
    condition: Mapping[str, Any],
    products: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
    main_slug: str,
) -> str:
    """Link every product of a hub condition to its own comparison anchor.

    The anchors already exist in the published comparison, so the category page
    never sends all products back to one shared entry.
    """
    index = {p["product_id"]: p for p in products}
    links = []
    for pid in condition["product_ids"]:
        if pid not in index:
            raise ValueError("PURCHASE_CONDITION_PRODUCT_MISSING")
        product = index[pid]
        if not product.get("anchor"):
            raise ValueError("PURCHASE_CONDITION_ANCHOR_MISSING")
        href = f"/{main_slug}/#{product['anchor']}"
        links.append(
            '<a href="'
            + escape(href, quote=True)
            + '">'
            + escape(product["name"])
            + "</a>"
        )
    return "、".join(links)


def route_links(p: Mapping[str, Any], *, current_slug: str | None = None) -> str:
    """Stage links for one model as a headed list, not a navigation landmark."""
    links = [
        f'<li><a href="/{slug}/#{p["anchor"]}">{label}</a></li>'
        for label, slug in STAGES.values()
        if slug != current_slug
    ]
    if not links:
        return ""
    return (
        '<div class="ps-model-routes-block"><h4>ほかのガイドで'
        + escape(p["name"])
        + 'を確認</h4><ul class="ps-model-routes">'
        + "".join(links)
        + "</ul></div>"
    )


def cta(
    o: Mapping[str, Any], article: Mapping[str, Any], snapshot: str, placement: str
) -> tuple[str, dict[str, str]]:
    if placement not in PLACEMENTS or not eligible_link(o):
        raise ValueError("PURCHASE_CTA_INELIGIBLE")
    resolved = resolve_offer(o)
    binding = {
        k: str(v)
        for k, v in {
            "article_id": article["article_id"],
            "product_id": o["product_id"],
            "seller_id": o["seller_id"],
            "offer_id": o["offer_id"],
            "cta_id": f"purchase-{article['post_id']}-{o['offer_id']}-{placement}",
            "placement": placement,
            "snapshot_id": snapshot,
            "link_purpose": resolved["link_purpose"],
            "affiliate": str(resolved["affiliate_ready"]).lower(),
        }.items()
    }
    if article.get("purchase_normalization", True) is False:
        binding.pop("link_purpose")
        binding.pop("affiliate")
    attributes = {
        "data-raos-cta-type": "offer",
        **{"data-raos-" + k.replace("_", "-"): v for k, v in binding.items()},
    }
    rel = (
        "sponsored nofollow noopener noreferrer"
        if resolved["affiliate_ready"]
        else "noopener noreferrer"
    )
    link = (
        '<a class="ps-offer-link"'
        + attrs(attributes)
        + ' href="'
        + escape(resolved["href"], quote=True)
        + '" rel="'
        + rel
        + '">'
        + escape(tidy(o["seller"]))
        + "で購入条件を見る</a>"
    )
    return link, {**binding, "href": resolved["href"]}


def offer_panel(
    p: Mapping[str, Any],
    catalog: Mapping[str, Any],
    article: Mapping[str, Any],
    snapshot: str,
    placement: str,
    *,
    now: datetime | None = None,
) -> tuple[str, list[dict[str, str]]]:
    now = current_time(now)
    offers = product_offers(p, catalog)
    bindings: list[dict[str, str]] = []
    parts = []
    for o in offers:
        checked = timestamp(o["checked_at"])
        if checked is None:
            raise ValueError("PURCHASE_OFFER_DATE_REQUIRED")
        expired = price_expired(o, now)
        expiry = price_expiry(o)
        data = {
            "data-ps-offer": o["offer_id"],
            "data-ps-checked-at": o["checked_at"],
            "data-ps-valid-until": o["valid_until"],
            "data-ps-identity": str(o.get("identity_verified") is True).lower(),
            "data-ps-state": o["state"],
            "data-ps-complete": str(o.get("total_scope_complete") is True).lower(),
            "data-ps-condition": o["condition"],
        }
        if article.get("purchase_normalization", True):
            states = offer_states(o, checked)
            states["price_state"] = "EXPIRED" if expired else "RECHECK_REQUIRED"
            data.update(
                {
                    "data-ps-" + key.replace("_", "-"): value
                    for key, value in states.items()
                }
            )
        else:
            data["data-ps-price-state"] = "EXPIRED" if expired else "RECHECK_REQUIRED"
        for key in LABELS:
            if o.get(key) is not None:
                data["data-ps-" + key.replace("_", "-")] = o[key]
        rows = (
            '<div class="ps-seller"'
            + attrs(data)
            + "><h4>"
            + escape(tidy(o["seller"]))
            + "</h4><p>"
            + escape(tidy(o["variant"]))
            + "</p>"
        )
        # This is an explicitly dated observation, never a claim of live/current price.
        if expired:
            label = o.get("price_label")
            rows += (
                '<p class="ps-price-expired">'
                + (
                    escape(str(label))
                    + "（"
                    + escape(jp_datetime(expiry))
                    + "まで）は終了しました。現在の価格は未確認です。"
                    if label
                    else "販売条件の期限切れ・再確認中（確認日 "
                    + escape(jp_datetime(checked))
                    + "、期限 "
                    + escape(jp_datetime(expiry))
                    + "）。現在の価格・送料は未確認です。"
                )
                + "</p>"
            )
        else:
            cells = " ／ ".join(
                (
                    f"{LABELS[k]}：{o[k]:,}円"
                    if o.get(k) is not None
                    else f"{LABELS[k]}：未確認"
                )
                for k in LABELS
            )
            rows += (
                "<p>"
                + escape(cells)
                + "（"
                + escape(jp_datetime(expiry))
                + "まで有効な確認値）</p>"
                + '<p class="ps-price-status">確認時の販売条件です。現在価格の再確認が必要です。</p>'
            )
        rows += (
            '<p class="ps-price-date">販売条件確認：<time datetime="'
            + escape(o["checked_at"])
            + '">'
            + escape(jp_datetime(checked) + "（日本時間）")
            + "</time>"
            + ("（期限切れ）" if expired else "")
            + "／"
            + escape(tidy(o.get("price_scope", "本体と記載した費目の範囲")))
            + "</p>"
        )
        rows += (
            "<p>納期："
            + escape(tidy(o.get("delivery") or "未確認"))
            + "／保証："
            + escape(tidy(o.get("warranty") or "未確認"))
            + "</p>"
        )
        href = None
        if eligible_link(o):
            link, binding = cta(o, article, snapshot, placement)
            bindings.append(binding)
            rows += link
            href = binding["href"]
        else:
            rows += (
                '<p class="ps-unavailable">'
                + escape(
                    tidy(
                        o.get("unavailable_reason")
                        or (
                            "確認時は売り切れでした。現在の販売状態は、確認日時と販売先の案内を参照してください。"
                            if o.get("state") == "SOLD_OUT"
                            else "販売条件の確認が完了していないため、購入先としての案内を保留しています。"
                        )
                    )
                )
                + "</p>"
            )
        if href != o["source_url"]:
            rows += (
                '<p class="ps-source"><a href="'
                + escape(o["source_url"], quote=True)
                + '">販売条件の確認元：'
                + escape(tidy(o["seller"]))
                + "の商品ページ</a></p>"
            )
        rows += "</div>"
        parts.append(rows)
    if not parts:
        parts.append(
            '<p class="ps-unavailable">販売先未確認。型番・構成・販売条件を照合できるまで、購入先の案内を保留しています。</p>'
        )
    return "".join(parts), bindings


def next_check_date(
    issue: Mapping[str, Any], offers: list[dict[str, Any]], today: date
) -> date:
    """A planned check never sits in the past: it follows the latest offer deadline."""
    planned = date.fromisoformat(issue["next_check_on"])
    for o in offers:
        deadline = timestamp(o.get("valid_until"))
        if deadline is not None:
            planned = max(planned, deadline.astimezone(JST).date() + timedelta(days=1))
    if planned <= today:
        planned = today + timedelta(days=1)
    return planned


def active_issues(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        i
        for i in catalog["research_issues"]
        if i["product_id"] == p["product_id"] and i["status"] != "RESOLVED"
    ]


def common_alternatives(
    products: list[dict[str, Any]], catalog: Mapping[str, Any]
) -> list[str]:
    """Hold conditions shared by two or more candidates are stated once per article."""
    counts: dict[str, int] = {}
    for p in products:
        for i in active_issues(p, catalog):
            counts[i["alternative"]] = counts.get(i["alternative"], 0) + 1
    return [text for text, count in counts.items() if count >= 2]


def research_panel(
    p: Mapping[str, Any],
    catalog: Mapping[str, Any],
    *,
    show_next_check: bool = True,
    now: datetime | None = None,
    shared: list[str] | tuple[str, ...] = (),
) -> str:
    rows = active_issues(p, catalog)
    if not rows:
        return ""
    today = current_time(now).astimezone(JST).date()
    offers = product_offers(p, catalog)
    items = []
    for i in rows:
        item = (
            "<p><strong>"
            + escape(i["topic"])
            + "</strong>："
            + escape(tidy(i["impact"]))
            + "</p>"
        )
        if i["alternative"] not in shared:
            item += "<p>" + escape(tidy(i["alternative"])) + "</p>"
        item += (
            '<p class="ps-source"><a href="'
            + escape(i["target_url"], quote=True)
            + '">'
            + escape(i.get("target_label") or (i["topic"] + "の確認先"))
            + "</a>"
            + (
                " ／ 次回確認 " + escape(jp_date(next_check_date(i, offers, today).isoformat()))
                if show_next_check
                else ""
            )
            + "</p>"
        )
        items.append(item)
    return (
        '<details class="ps-research"><summary>残る確認と、判断を保留する条件</summary>'
        + "".join(items)
        + "</details>"
    )


def specification_table(
    article: Mapping[str, Any],
    products: list[dict[str, Any]],
    *,
    labels: list[str] | None = None,
    table_class: str = "ps-comparison",
    region_label: str = "候補の仕様比較",
    caption: str = "決め手になる仕様。公表値の条件・確認日は商品ごとの出典に記載",
    with_sources: bool = False,
) -> str:
    labels = article["spec_labels"] if labels is None else labels
    heads = "".join(
        '<th scope="col" data-ps-product="'
        + p["product_id"]
        + '"><a href="#'
        + p["anchor"]
        + '">'
        + escape(p["name"])
        + "</a></th>"
        for p in products
    )
    rows = []
    for label in labels:
        cells = []
        for p in products:
            f = next((f for f in p["facts"] if f["label"] == label), None)
            value = f["text"] if f else "未確認"
            source = ""
            if with_sources and f:
                # Moved rows keep their own source and check date next to the value.
                source = (
                    '<span class="ps-source"><a href="'
                    + escape(f["source_url"], quote=True)
                    + '">'
                    + escape(locator_label(f["locator"]))
                    + "</a> ／ 仕様確認 "
                    + escape(jp_date(f["checked_at"]))
                    + "</span>"
                )
            cells.append(
                '<td data-ps-fact-state="'
                + escape(f["state"] if f else "UNKNOWN")
                + '" data-ps-product="'
                + p["product_id"]
                + '">'
                + escape(tidy(value))
                + source
                + "</td>"
            )
        rows.append(
            '<tr><th scope="row">' + escape(label) + "</th>" + "".join(cells) + "</tr>"
        )
    return (
        '<div class="ps-table-scroll" tabindex="0" role="region" aria-label="'
        + escape(region_label, quote=True)
        + '"><table class="'
        + escape(table_class, quote=True)
        + '"><caption>'
        + escape(caption)
        + '</caption><thead><tr><th scope="col">比較項目</th>'
        + heads
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def locator_label(locator: str) -> str:
    return locator.replace("既存公開記事の比較表に紐づく公式仕様", "公式仕様・製品情報")


_SLOT_IDS = {"task-fit": "ps-task-fit", "hold-reasons": "ps-hold-reasons"}


def editorial_slot(template: str, slot_name: str) -> str:
    """Extract one static editorial section kept only for the main comparison.

    The template marks the two sections with ``data-ps-editorial-slot``. Unknown,
    duplicate, nested or mis-identified slots stop the generation instead of
    silently dropping or doubling reader-facing copy. This is not a sanitizer;
    the existing HTML checks still apply to the extracted markup.
    """
    if slot_name not in _SLOT_IDS:
        raise ValueError("PURCHASE_EDITORIAL_SLOT_UNKNOWN")
    root = fragment(template)
    nodes = [n for n in root.walk() if n.tag]
    by_name: dict[str, Element] = {}
    for node in nodes:
        if "data-ps-editorial-slot" not in node.attrs:
            continue
        name = node.attrs["data-ps-editorial-slot"] or ""
        if name not in _SLOT_IDS or name in by_name:
            raise ValueError("PURCHASE_EDITORIAL_SLOT_UNKNOWN_OR_DUPLICATE")
        if node.tag != "section" or node.attrs.get("id") != _SLOT_IDS[name]:
            raise ValueError("PURCHASE_EDITORIAL_SLOT_ID_MISMATCH")
        parent = node.parent
        while parent is not None:
            if "data-ps-editorial-slot" in parent.attrs:
                raise ValueError("PURCHASE_EDITORIAL_SLOT_NESTED")
            parent = parent.parent
        by_name[name] = node
    if set(by_name) != set(_SLOT_IDS):
        raise ValueError("PURCHASE_EDITORIAL_SLOT_REQUIRED_ONCE")
    ids = [n.attrs["id"] for n in nodes if n.attrs.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("PURCHASE_EDITORIAL_SLOT_ID_COLLISION")
    node = by_name[slot_name]
    node.attrs.pop("data-ps-editorial-slot")
    return node.html()


def installation_context(
    article: Mapping[str, Any], products: list[dict[str, Any]]
) -> str:
    """Always-visible home for the rows moved out of the main comparison table."""
    table = specification_table(
        article,
        products,
        labels=article["spec_detail_labels"],
        table_class="ps-installation-details",
        region_label="設置条件の詳細",
        caption="開扉時の寸法・必要な余白・使用水量。各欄に同じ型番の確認元と確認日を記載",
        with_sources=True,
    )
    return (
        '<section id="ps-installation-context"><h2>設置条件の詳細</h2><p>主表から移した項目です。本体寸法だけでは設置可否を判断せず、開扉時の寸法、周囲の余白、給排水・電源の条件を同じ型番の公表条件で確認してください。使用水量は機種ごとの公表条件つきの値で、同じ食器量・同じコースでの実測比較ではありません。型番ごとの注意は上の商品カードに1回だけ記載しています。</p>'
        + table
        + '<p><a href="/dishwasher-installation-measurement/">置き場所を測る順番のガイドへ</a></p></section>'
    )


INSTALLATION_LABELS = {
    "width_mm": "幅",
    "depth_mm": "奥行",
    "height_mm": "高さ",
    "door_depth_mm": "開扉時の奥行",
    "door_height_mm": "開扉時の高さ",
    "above_mm": "上の余白",
    "left_mm": "左の余白",
    "right_mm": "右の余白",
    "rear_mm": "後ろの余白",
}


def installation_reference_note(p: Mapping[str, Any]) -> str:
    """Static list of known and missing site-side references, readable without JS.

    A missing reference is the site's gap, not the reader's: the note names the
    model, the items the official material does not give, and the page to check.
    """
    values = p.get("installation", {})
    known = [
        escape(INSTALLATION_LABELS[key]) + escape(f"{values[key]:g}") + "mm"
        for key in INSTALLATION_LABELS
        if money(values.get(key))
    ]
    unknown = [
        escape(INSTALLATION_LABELS[key])
        for key in INSTALLATION_LABELS
        if not money(values.get(key))
    ]
    note = (
        '<p class="ps-installation-reference">'
        + escape(p["exact_model"])
        + "の照合基準（公表値）："
        + ("／".join(known) if known else "未確認")
        + "。"
    )
    if unknown:
        note += (
            "公式資料で数値を確認できていない項目："
            + "、".join(unknown)
            + "。この項目は数値で照合できないため、設置場所の実測と公式資料で個別に確認してください。"
        )
    return (
        note
        + '<a href="'
        + escape(p["official_url"], quote=True)
        + '">型番の公式仕様で確認する</a></p>'
    )


def preserved_details(template: str) -> str:
    root = fragment(template)
    selected: list[Element] = []
    for node in root.find(tag="section"):
        heading = next(iter(node.find(tag="h2")), None)
        text = heading.text() if heading else ""
        if (
            node.has("sources-section")
            or re.search("一次情報|確認した公式", text)
            or re.search("FAQ|迷いやすい|拡張機能", text)
        ):
            if not any(parent is node for old in selected for parent in old.walk()):
                selected.append(node)
    for node in selected:
        # English section labels and the API credit are not part of the sources.
        for label in node.find(tag="p", cls="section-number"):
            label.remove()
        for credit in node.find(tag="p", cls="raos-source-link"):
            if any(
                a.attrs.get("href") == "https://developers.rakuten.com/"
                for a in credit.find(tag="a")
            ):
                credit.remove()
    # Removing the English label leaves an indentation-only line behind; drop it.
    result = re.sub(r"(?m)^[ \t]+$", "", "".join(n.html() for n in selected))
    # Evidence classifications stay in the data; no repeated badges in reader prose.
    result = re.sub(
        r'<span[^>]*class="raos-evidence-badge"[^>]*>.*?</span>', "", result
    )
    return result


def resolve_product_media(
    catalog: Mapping[str, Any], registry: list[dict[str, Any]], official_image: bytes
) -> dict[str, Any]:
    """Freeze authorized source bytes; never load media registries on the public path."""
    resolved = {}
    for product in catalog["products"]:
        review = product.get("image_review", {})
        pid = product["product_id"]
        if review.get("state") != "VERIFIED_REGISTERED_MEDIA":
            raise ValueError("PURCHASE_MEDIA_REVIEW_REQUIRED")
        if review.get("basis") == "OFFICIAL_PUBLICATION_KIT":
            if pid != "PRD-IROBOT-ROOMBA-MINI-AUTOEMPTY" or sha256(
                official_image
            ).hexdigest() != review.get("source_sha256"):
                raise ValueError("PURCHASE_OFFICIAL_MEDIA_DRIFT")
            resolved[pid] = {"official": True, "sha256": review["source_sha256"]}
            continue
        records = [r for r in registry if r.get("product_id") == pid]
        if len(records) != 1 or review.get("basis") != "RAKUTEN_GENERATED_VERBATIM":
            raise ValueError("PURCHASE_MEDIA_IDENTITY_REQUIRED")
        record = records[0]
        if sha256(canonical(record).encode()).hexdigest() != review.get(
            "record_sha256"
        ):
            raise ValueError("PURCHASE_MEDIA_RECORD_DRIFT")
        source_url = urlsplit(record.get("item_url", ""))
        shop = source_url.path.strip("/").split("/")[0]
        if (
            source_url.scheme != "https"
            or source_url.hostname != "item.rakuten.co.jp"
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", shop)
        ):
            raise ValueError("PURCHASE_MEDIA_SHOP_INVALID")
        sizes = {}
        for size in ("240", "300"):
            raw = record.get("sources", {}).get(size)
            if not isinstance(raw, str) or sha256(
                raw.encode()
            ).hexdigest() != review.get("source_sha256", {}).get(size):
                raise ValueError("PURCHASE_MEDIA_SOURCE_DRIFT")
            nodes = list(fragment(raw).walk())
            anchors = [n for n in nodes if n.tag == "a"]
            if len(anchors) != 1 or not https(anchors[0].attrs.get("href")):
                raise ValueError("PURCHASE_MEDIA_LINK_INVALID")
            sizes[size] = {"raw": raw, "href": anchors[0].attrs["href"]}
        resolved[pid] = {
            "official": False,
            "sizes": sizes,
            "seller_id": "rakuten-" + shop,
            "shop_name": record["shop_name"],
            "slugs": record["slugs"],
        }
    return resolved


def render_product_media(
    product: Mapping[str, Any],
    article: Mapping[str, Any],
    snapshot: str,
    media: Mapping[str, Any],
) -> tuple[str, list[dict[str, str]]]:
    if media.get("official"):
        return (
            '<figure class="ps-product-image ps-official-product-photo" data-ps-media-sha256="'
            + escape(media["sha256"], quote=True)
            + '"><img src="'
            + '/wp-content/themes/kurashinoshirube-child/assets/images/roomba-mini-official.jpg"'
            + ' width="2048" height="2048" loading="lazy" decoding="async"'
            + ' alt="Roomba Mini（白）とAutoEmpty充電ステーション。公式提供写真。">'
            + "<figcaption>アイロボット Roomba® Mini 掃除機＆床拭きロボット + AutoEmpty™ 充電ステーション"
            + '<br>写真：<a href="https://irobotjp.mediaroom.com/media-kits?item=28">'
            + "アイロボットジャパン 公式掲載用素材</a></figcaption></figure>",
            [],
        )
    if article["slug"] not in media["slugs"]:
        raise ValueError("PURCHASE_MEDIA_ARTICLE_SCOPE_MISMATCH")
    bindings = []
    parts = ['<figure class="ps-product-image ps-rakuten-product-photo">']
    for size in ("300", "240"):
        source = media["sizes"][size]
        binding = {
            "article_id": article["article_id"],
            "product_id": product["product_id"],
            "seller_id": media["seller_id"],
            "offer_id": "image-" + product["product_id"] + "-" + size,
            "cta_id": "purchase-image-" + product["product_id"] + "-" + size,
            "placement": "product_card",
            "snapshot_id": snapshot,
            "link_purpose": "affiliate_purchase",
            "affiliate": "true",
        }
        if article.get("purchase_normalization", True) is False:
            binding.pop("link_purpose")
            binding.pop("affiliate")
        parts.append(
            '<div class="raos-rakuten-image-'
            + size
            + '"'
            + attrs(
                {
                    "data-raos-cta-type": "offer",
                    **{
                        "data-raos-" + k.replace("_", "-"): v
                        for k, v in binding.items()
                    },
                }
            )
            + ">"
            + source["raw"]
            + "</div>"
        )
        bindings.append({**binding, "href": source["href"]})
    parts.append(
        "<figcaption>広告リンク：楽天市場（"
        + escape(tidy(media["shop_name"]))
        + "）の販売ページへ進みます。構成・送料・保証は未確認。</figcaption></figure>"
    )
    return "".join(parts), bindings


def condition_summary(
    p: Mapping[str, Any],
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    now: datetime,
) -> str:
    """One line of decisive published values plus the next in-page action."""
    labels = article.get("condition_fact_labels") or [
        label for label in article["spec_labels"] if label != "選ぶ理由"
    ][:3]
    facts = {f["label"]: f for f in p["facts"]}
    parts = [
        re.sub(r"（.*）$", "", label) + "：" + tidy(facts[label]["text"])
        for label in labels
        if label in facts
    ]
    offer = purchasable_offer(p, catalog)
    verified = verified_offers(p, catalog)
    if offer:
        if price_expired(offer, now):
            parts.append(
                "税込本体：確認値が期限切れのため再確認中（"
                + jp_date(offer["checked_at"])
                + "確認）"
            )
        else:
            parts.append(
                f"税込本体：{offer['price_yen']:,}円（{jp_date(offer['checked_at'])}確認）"
                if offer.get("price_yen") is not None
                else "税込本体：未確認"
            )
        action = internal_link("#ps-seller-" + p["anchor"], p["product_id"], "購入総額と販売先へ")
    elif verified:
        parts.append(
            "確認した販売先は売り切れ・再入荷待ち（"
            + jp_date(max(o["checked_at"] for o in verified))
            + "確認）"
        )
        action = internal_link("#ps-seller-" + p["anchor"], p["product_id"], "販売状態と保留条件へ")
    else:
        parts.append("販売先未確認")
        action = (
            '<a href="' + escape(p["official_url"], quote=True) + '">公式仕様を見る</a>'
        )
    return (
        '<p class="ps-condition-product"><a href="#'
        + str(p["anchor"])
        + '">'
        + escape(str(p["name"]))
        + '</a></p><p class="ps-condition-facts">'
        + escape("／".join(parts))
        + '</p><p class="ps-condition-links">'
        + str(action)
        + "</p>"
    )


def history_block(article: Mapping[str, Any]) -> str:
    """Dated confirmation history and the editor line, shared by comparisons and guides."""
    entries = article.get("history", [])
    if not entries:
        return EDITOR_LINE
    return (
        '<details class="ps-history"><summary>確認・更新履歴</summary><ul>'
        + "".join(
            '<li><time datetime="'
            + escape(e["date"], quote=True)
            + '">'
            + escape(jp_date(e["date"]))
            + "</time>："
            + escape(tidy(e["text"]))
            + "</li>"
            for e in entries
        )
        + "</ul></details>"
        + EDITOR_LINE
    )


def render_comparison(
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    template: str,
    snapshot: str,
    product_media: Mapping[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, list[dict[str, str]]]:
    now = current_time(now)
    products = [
        next(p for p in catalog["products"] if p["product_id"] == pid)
        for pid in article["product_ids"]
    ]
    bindings: list[dict[str, str]] = []
    main = article["slug"] == MAIN_SLUG
    root_attrs = {
        "data-raos-purchase-support": "v1",
        "data-raos-article-id": article["article_id"],
        "data-raos-snapshot-id": snapshot,
    }
    if main:
        # The main comparison keeps four condition links; purpose and budget
        # inputs are not generated, so no script version can bring them back.
        root_attrs["data-ps-purpose-mode"] = "links"
        root_attrs["data-ps-budget-mode"] = "off"
    out = ['<div class="raos-editorial-v2 ps-article"' + attrs(root_attrs) + ">"]
    out.append('<p class="ps-disclosure">' + DISCLOSURE + "</p>")
    out.append(
        '<p class="ps-lead">'
        + escape(article["intro"])
        + "</p>"
        + BYLINE
        + '<nav class="ps-toc" aria-label="記事の近道"><a href="#ps-choose">候補を絞る</a><a href="#ps-specs">仕様を比べる</a><a href="#ps-products">向く・向かない条件</a>'
        + ('<a href="#ps-installation-context">設置の詳細</a>' if main else "")
        + '<a href="#ps-offers">購入総額と販売先</a><a href="#ps-evidence">詳細・出典</a></nav>'
    )
    decision_steps_html = ""
    decision_steps_placement = "before_conditions"
    if article.get("decision_steps"):
        steps = article["decision_steps"]
        decision_steps_placement = steps.get("placement", "before_conditions")
        if decision_steps_placement not in {"before_conditions", "after_conditions"}:
            raise ValueError("PURCHASE_DECISION_STEPS_PLACEMENT_INVALID")
        decision_steps_html = (
            '<section id="ps-decision-steps"><h2>'
            + escape(steps["title"])
            + "</h2><ol>"
            + "".join("<li>" + escape(step) + "</li>" for step in steps["steps"])
            + '</ol><p><a href="'
            + escape(steps["source_url"], quote=True)
            + '">'
            + escape(steps["source_label"])
            + "</a></p></section>"
        )
    if decision_steps_placement == "before_conditions":
        out.append(decision_steps_html)
    out.append(
        '<section id="ps-choose"><h2>条件別の結論</h2><div class="ps-condition-grid">'
    )
    for c in article["conditions"]:
        chosen = [
            next(p for p in products if p["product_id"] == pid)
            for pid in c["product_ids"]
        ]
        out.append("<div><h3>" + escape(c["label"]) + "</h3>")
        for p in chosen:
            out.append(condition_summary(p, article, catalog, now))
        if c.get("alternative"):
            alternative = c["alternative"]
            out.append(
                '<p class="ps-note">'
                + escape(tidy(alternative["text"]))
                + '<a href="'
                + escape(alternative["href"], quote=True)
                + '">'
                + escape(alternative["label"])
                + "</a></p>"
            )
        out.append("</div>")
    if main:
        out.append(
            '</div><p class="ps-note">条件ごとの商品名から、その商品の理由・代償・販売条件へ進めます。決め手の値は公表仕様と、確認日つきの販売条件です。</p></section>'
        )
    else:
        out.append(
            '</div><div class="ps-budget-controls" hidden'
            + attrs(
                {
                    "data-ps-purpose-options": canonical(
                        [
                            {"id": c["id"], "label": c["label"]}
                            for c in article["conditions"]
                        ]
                    )
                }
            )
            + '></div><p class="ps-note">条件や予算を入力した場合も、その内容は保存・送信しません。購入総額を確認できない候補は、理由を付けて残します。ポイントや条件付きクーポンを一律に差し引きません。</p></section>'
        )
    if decision_steps_placement == "after_conditions":
        out.append(decision_steps_html)
    if article.get("preserved_method_heading"):
        method_id = article["preserved_method_heading"]
        methods = [
            section
            for section in fragment(template).find(tag="section")
            if any(n.attrs.get("id") == method_id for n in section.walk())
        ]
        if len(methods) != 1:
            raise ValueError("PURCHASE_METHOD_SECTION_REQUIRED")
        for label in methods[0].find(tag="p", cls="section-number"):
            if label.parent is not None:
                label.parent.children.remove(label)
        out.append(re.sub(r"(?m)^[ \t]+$", "", methods[0].html()))
    if article.get("comparison_scope"):
        scope = article["comparison_scope"]
        out.append(
            '<section><h2 id="'
            + escape(scope["heading_id"], quote=True)
            + '">比較のしかた</h2><p>'
            + escape(scope["intro"])
            + '</p><h3>比較対象にした条件</h3><ul>'
            + "".join("<li>" + escape(item) + "</li>" for item in scope["included"])
            + '</ul><h3>比較に含めていないもの</h3><ul>'
            + "".join("<li>" + escape(item) + "</li>" for item in scope["excluded"])
            + '</ul><p>市場全体の順位ではありません。性能評価に価格・在庫・ポイント・広告報酬を加点せず、購入費用は別に確認します。</p></section>'
        )
    out.append('<section id="ps-specs"><h2>決め手になる比較表</h2>')
    if article["slug"] == MAIN_SLUG:
        out.append(
            '<div class="ps-pair-controls" hidden'
            + attrs(
                {
                    "data-ps-pair-options": canonical(
                        [{"id": p["product_id"], "label": p["name"]} for p in products]
                    )
                }
            )
            + "></div>"
        )
    table = specification_table(article, products)
    cells = []
    for p in products:
        # The table sends readers to the dated seller panel; external purchase
        # links only follow the reasons and the seller conditions.
        if purchasable_offer(p, catalog):
            link = internal_link(
                "#ps-seller-" + p["anchor"], p["product_id"], "販売先と確認日を見る"
            )
        elif verified_offers(p, catalog):
            link = internal_link(
                "#ps-seller-" + p["anchor"],
                p["product_id"],
                "確認した販売先は売り切れ・再入荷待ち。確認日と販売条件を見る",
            )
        else:
            link = (
                '販売先未確認 ／ <a href="'
                + escape(p["official_url"], quote=True)
                + '">公式仕様を見る</a>'
            )
        cells.append('<td data-ps-product="' + p["product_id"] + '">' + link + "</td>")
    table = table.replace(
        "</tbody>",
        '<tr data-ps-keep-row><th scope="row">購入条件</th>'
        + "".join(cells)
        + "</tr></tbody>",
    )
    out.append(table)
    if main:
        out.append(
            '<p class="ps-note">本体寸法だけでは設置可否を判断しません。<a href="#ps-installation-context">開扉時の寸法と必要な余白</a>を、同じ型番の公表条件で確認してください。</p>'
        )
    out.append("</section>")
    if main:
        out.append(editorial_slot(template, "task-fit"))
    out.append(
        '<section id="ps-products"><h2>向く・向かない理由</h2><div class="ps-product-grid">'
    )
    media_shown = False
    for p in products:
        out.append(
            '<article class="ps-product" id="'
            + p["anchor"]
            + '"'
            + attrs(
                {
                    "data-ps-product": p["product_id"],
                    "data-ps-use-cases": " ".join(p["use_cases"]),
                }
            )
            + "><h3>"
            + escape(p["name"])
            + '</h3><p class="ps-model">'
            + escape(p["exact_model"])
            + "</p>"
        )
        if product_media is not None:
            if media_allowed(p, catalog):
                photo, photo_bindings = render_product_media(
                    p, article, snapshot, product_media[p["product_id"]]
                )
                out.append(
                    '<div class="ps-product-media" data-ps-media-product="'
                    + escape(p["product_id"], quote=True)
                    + '"></div>'
                )
                bindings.extend(photo_bindings)
                media_shown = True
            else:
                out.append(MEDIA_WITHHELD)
        out.append(
            "<p>"
            + escape(tidy(p["lead"]))
            + "</p><h4>合いやすい条件</h4><ul>"
            + "".join("<li>" + escape(tidy(x)) + "</li>" for x in p["fit"])
            + "</ul><h4>別の候補も考えたい条件</h4><ul>"
            + "".join("<li>" + escape(tidy(x)) + "</li>" for x in p["avoid"])
            + "</ul>"
        )
        if main:
            out.append(
                '<p class="ps-product-caution">'
                + escape(tidy(p["caution"]))
                + '<a href="#ps-installation-context">設置条件の詳細へ</a></p>'
            )
        out.append('<p data-ps-product-budget role="status"></p>')
        if article["slug"] == MAIN_SLUG:
            out.append(route_links(p))
        out.append(
            "<p>"
            + internal_link("#ps-seller-" + p["anchor"], p["product_id"], "購入総額と販売先へ")
            + "</p>"
        )
        o = purchasable_offer(p, catalog)
        if o:
            link, binding = cta(o, article, snapshot, "product_card")
            out.append(link)
            bindings.append(binding)
        out.append("</article>")
    out.append("</div>")
    if media_shown:
        out.append(RAKUTEN_CREDIT)
    out.append("</section>")
    if main:
        out.append(installation_context(article, products))
    shared = common_alternatives(products, catalog)
    out.append(
        '<section id="ps-offers"><h2>購入総額と販売先</h2><p>構成・送料・必須品・納期・保証を販売先ごとに確認します。異なる構成の価格を同じ商品価格として比べません。確認日から24時間、または販売先の期限までを価格の表示期限とし、期限後は価格を表示せず再確認中と示します。</p>'
        + (
            '<p class="ps-note">'
            + "".join(escape(tidy(text)) for text in shared)
            + "</p>"
            if shared
            else ""
        )
    )
    for p in products:
        panel, b = offer_panel(p, catalog, article, snapshot, "final_summary", now=now)
        bindings.extend(b)
        out.append(
            '<section class="ps-product-offers" id="ps-seller-'
            + p["anchor"]
            + '"'
            + attrs({"data-ps-product": p["product_id"]})
            + "><h3>"
            + escape(p["name"])
            + "</h3>"
            + panel
            + '<p><a href="'
            + escape(p["official_url"], quote=True)
            + '">公式仕様を見る</a></p>'
            + research_panel(
                p, catalog, show_next_check=not main, now=now, shared=shared
            )
            + "</section>"
        )
    out.append("</section>")
    if main:
        out.append(editorial_slot(template, "hold-reasons"))
        out.append(
            '<section id="ps-guides"><h2 id="dish-related-title">残る問いに対応する5ガイド</h2><p>全員に必読ではありません。残った疑問のガイドだけを、同じ4機種の条件で確認できます。</p><ul>'
            + "".join(
                '<li><a href="/' + slug + '/">' + label + "を機種ごとに確認</a></li>"
                for label, slug in STAGES.values()
            )
            + "</ul></section>"
        )
    out.append(
        '<section id="ps-evidence"><h2>必要な詳細と出典</h2><p>性能の評価に価格や広告報酬を加点しません。購入費用は用途・予算に合う候補を選ぶために別に比較します。掲載候補は市場全体の順位ではありません。</p><details><summary>仕様の確認元・適用条件</summary>'
    )
    for p in products:
        seen = set()
        out.append("<h3>" + escape(p["name"]) + "</h3><ul>")
        for f in p["facts"]:
            key = (f["source_url"], f["locator"], f["checked_at"])
            if key in seen:
                continue
            seen.add(key)
            out.append(
                '<li><a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(locator_label(f["locator"]))
                + "</a> ／ 仕様確認 "
                + escape(jp_date(f["checked_at"]))
                + "</li>"
            )
        out.append("</ul>")
    out.append(
        "</details>"
        + preserved_details(template)
        + '</section><p class="ps-note">使う場所や目的に合わない、または必要な情報が確認できない場合は、別の候補を検討するか、購入を見送ってください。</p>'
    )
    for caution in fragment(template).find(tag="aside"):
        if any(n.attrs.get("id") == "under-3kg-caution-title" for n in caution.walk()):
            caution.attrs["id"] = "ps-flight-purchase-check"
            out.append(caution.html())
    out.append(history_block(article))
    for note in article.get("historical_link_notes", []):
        # Old bookmarks keep their ids as small footnotes, not as headed sections.
        out.append(
            '<aside class="ps-legacy-note" id="'
            + escape(note["id"], quote=True)
            + '"><p><strong>'
            + escape(note["title"])
            + "</strong>："
            + escape(tidy(note["text"]))
            + '<a href="#ps-specs">現在の比較候補と型番を確認する</a></p></aside>'
        )
    for navigation in fragment(template).find(tag="nav"):
        if navigation.attrs.get("id") == "ks-article-nav":
            out.append(navigation.html())
    for section in fragment(template).find(tag="section"):
        if section.attrs.get("id") == "ks-next-read":
            out.append(section.html())
    out.append("</div>")
    return "".join(out), bindings


def legacy_source_notes(
    article: Mapping[str, Any], registry: Mapping[str, Any], *, stage_label: str = ""
) -> str:
    notes = article.get("legacy_source_notes", [])
    if not notes:
        return ""
    facts = {f["evidence_ref"]: f for f in registry["facts"]}
    sources = {s["source_ref"]: s for s in registry["sources"]}
    groups: dict[str, list[str]] = {}
    seen = set()
    for note in notes:
        ref = note["evidence_ref"]
        if ref in seen or ref not in facts:
            raise ValueError("GUIDE_LEGACY_SOURCE_REFERENCE_INVALID")
        seen.add(ref)
        fact = facts[ref]
        source = sources[fact["source_ref"]]
        model = fact["exact_model"]
        if model not in source["models"] or not https(source["url"]):
            raise ValueError("GUIDE_LEGACY_SOURCE_MODEL_MISMATCH")
        groups.setdefault(model, []).append(
            '<li id="guide-evidence-'
            + escape(ref, quote=True)
            + '">'
            + escape(note["label"])
            + '：<a href="'
            + escape(source["url"], quote=True)
            + '">'
            + escape(source["title"])
            + "</a>（"
            + escape(tidy(fact["locator"]))
            + "）</li>"
        )
    models = "・".join(groups)
    return (
        '<section id="guide-previous-models"><h2>以前掲載した機種の資料</h2>'
        "<details><summary>型番別の説明書・確認項目を開く</summary>"
        "<p>"
        + escape(stage_label)
        + "について以前掲載した"
        + escape(models)
        + "の資料です。機種名や外観が似ていても、別の型番へ数値や手順を流用しないでください。</p>"
        + "".join(
            "<h3>" + escape(model) + "</h3><ul>" + "".join(items) + "</ul>"
            for model, items in groups.items()
        )
        + "</details></section>"
    )


def summary_cell(p: Mapping[str, Any], stage: str, row: str) -> str:
    value = p.get("guide_summary", {}).get(stage, {}).get(row)
    return tidy(value) if value else "未確認"


def guide_decision_table(stage: str, products: list[dict[str, Any]]) -> str:
    """Four-model table under the first heading so the title question is answered at once."""
    if stage == "installation":
        rows: list[tuple[str, list[str]]] = []
        dims, doors, gaps, weights = [], [], [], []
        for p in products:
            v = p.get("installation", {})

            def mm(key: str) -> str:
                return f"{v[key]:g}mm" if money(v.get(key)) else "未確認"

            dims.append(f"{mm('width_mm')}×{mm('depth_mm')}×{mm('height_mm')}")
            doors.append(f"奥行 {mm('door_depth_mm')}／高さ {mm('door_height_mm')}")
            gaps.append(
                f"上 {mm('above_mm')}／左右 {mm('left_mm')}・{mm('right_mm')}／後ろ {mm('rear_mm')}"
            )
            weights.append(summary_cell(p, stage, "質量"))
        rows = [
            ("本体寸法（幅×奥行×高さ）", dims),
            ("扉を開いたとき", doors),
            ("必要な余白", gaps),
            ("質量", weights),
        ]
    else:
        rows = [
            (row, [summary_cell(p, stage, row) for p in products])
            for row in GUIDE_TABLE_ROWS[stage]
        ]
    heads = "".join(
        '<th scope="col" data-ps-product="'
        + p["product_id"]
        + '"><a href="#'
        + p["anchor"]
        + '">'
        + escape(p["name"])
        + "</a></th>"
        for p in products
    )
    body = "".join(
        '<tr><th scope="row">'
        + escape(label)
        + "</th>"
        + "".join(
            '<td data-ps-product="'
            + p["product_id"]
            + '"'
            + (' data-ps-fact-state="UNKNOWN"' if cell == "未確認" else "")
            + ">"
            + escape(cell)
            + "</td>"
            for p, cell in zip(products, cells, strict=True)
        )
        + "</tr>"
        for label, cells in rows
    )
    label = STAGES[stage][0]
    return (
        '<div class="ps-table-scroll" tabindex="0" role="region" aria-label="4機種の'
        + escape(label, quote=True)
        + 'の比較"><table class="ps-comparison ps-guide-table"><caption>4機種の'
        + escape(label)
        + "を決めるための表。値は下の機種別欄の出典から転記した公表条件で、同じ条件での実測比較ではありません。"
        + '</caption><thead><tr><th scope="col">比較項目</th>'
        + heads
        + "</tr></thead><tbody>"
        + body
        + "</tbody></table></div>"
    )


def shared_guide_facts(
    stage: str, products: list[dict[str, Any]]
) -> tuple[str, set[tuple[str, str]]]:
    """Identical official conditions shared by several models are stated once."""
    groups: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = {}
    for p in products:
        for f in p.get("guide_facts", []):
            if f["field"] in GUIDE_REQUIREMENTS[stage]:
                groups.setdefault((f["field"], tidy(f["text"])), []).append((p, f))
    shared = {key: rows for key, rows in groups.items() if len(rows) >= 2}
    if not shared:
        return "", set()
    parts = [
        '<section class="ps-guide-shared" id="guide-'
        + stage
        + '-shared"><h3>複数機種で共通の条件</h3>'
    ]
    for (field, text), rows in shared.items():
        parts.append(
            "<p><strong>対象："
            + escape("・".join(p["name"] for p, _ in rows))
            + "</strong></p><p>"
            + escape(text)
            + "</p>"
            + "".join(
                '<p class="ps-source">'
                + escape(p["exact_model"])
                + '：<a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(locator_label(f["locator"]))
                + "</a> ／ 仕様確認 "
                + escape(jp_date(f["checked_at"]))
                + "</p>"
                for p, f in rows
            )
        )
    parts.append("</section>")
    return "".join(parts), set(shared)


def render_guide(
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    guide_registry: Mapping[str, Any],
    template: str,
    *,
    now: datetime | None = None,
) -> str:
    now = current_time(now)
    stage = next(k for k, (_, slug) in STAGES.items() if slug == article["slug"])
    stage_label = STAGES[stage][0]
    dish = next(a for a in catalog["articles"] if a["slug"] == MAIN_SLUG)["product_ids"]
    products = [p for p in catalog["products"] if p["product_id"] in dish]
    steps_id = (
        "guide-measurement-steps" if stage == "installation" else f"guide-{stage}-steps"
    )
    first_id = "guide-cost-scope" if stage == "cost" else steps_id
    out = [
        '<div class="raos-editorial-v2 ps-article" data-raos-purchase-support="v1">'
        '<nav class="ps-toc" id="ks-article-nav" aria-label="ガイドの近道"><a href="/kitchen/">食洗機の選び方</a><a href="#'
        + first_id
        + '">4機種の比較表へ</a></nav><p class="ps-lead">'
        + escape(
            article.get("reader_intro")
            or "比較記事と同じ機種で、"
            + stage_label
            + "を確認できます。型番と使う条件をそろえて照合してください。"
        )
        + "</p>"
        + BYLINE
    ]
    # FD-09: the model index follows the lead regardless of a reader_intro override.
    out.append(
        '<nav class="ps-model-index" aria-label="機種別の手順"><p>'
        + escape(stage_label)
        + "を確認する機種を選ぶ：</p>"
        + "".join(
            '<a href="#' + p["anchor"] + '">' + escape(p["name"]) + "</a>"
            for p in products
        )
        + "</nav>"
    )
    table = guide_decision_table(stage, products)
    if article.get("reader_steps"):
        steps = article["reader_steps"]
        out.append(
            '<section id="'
            + steps_id
            + '"><h2>'
            + escape(steps["title"])
            + "</h2>"
            + table
            + "<ol>"
            + "".join(
                f'<li id="guide-{stage}-step-{index}">' + escape(step) + "</li>"
                for index, step in enumerate(steps["steps"], start=1)
            )
            + "</ol></section>"
        )
    if stage == "installation":
        out.append(
            '<p class="ps-installation-safety">本体寸法・開扉時・必要余白は別々に確保します。寸法の数値照合だけでは、食器の収納・性能や安全な設置を保証しません。台の強度・水平、排水、電源・アース、熱源との距離も別途確認してください。</p>'
        )
    if stage == "cost":
        cost_article = next(
            a for a in guide_registry["articles"] if a["article_id"] == article["slug"]
        )
        out.append(
            '<section id="guide-cost-scope"><h2>4機種で計算できる費目と、できない費目</h2>'
            + "".join(
                "<p>" + escape(tidy(text)) + "</p>"
                for text in article.get("scope_notes", [])
            )
            + table
            + "</section>"
        )
        out.append(
            render_cost_profiles(
                cost_article, {f["evidence_ref"]: f for f in guide_registry["facts"]}
            )
        )
        out.append(
            '<section id="build-formula"><h2>確認できた費目の小計と、必要な入力</h2><p>電気代はWh÷1000×電気単価、上下水道代はL÷1000×上下水道の従量単価、洗剤代は購入価格÷内容量（g）×1回分の量（g）で計算します。未確認の費目はゼロ円にしません。すべての費目がそろっても、請求総額や手洗いからの節約額を示すものではありません。</p><p>基本料金・調整額・料金段階、使用回数、使うコースは家庭ごとに異なります。定格W×運転時間やタンク容量を一回の消費量へ代用しません。</p><details><summary>仮の単価による記入例</summary><p>入力例に限り、電気30円/kWh・上下水道300円/m³・洗剤5円/回・月30回と仮定します。230Wh・2.5Lの公表条件なら、電気6.9円＋上下水道0.75円＋洗剤5円＝12.65円/回、30回で379.5円です。洗剤の1回分は、例えば600gで660円の粉末を1回4g使う場合、660÷600×4＝4.4円/回のように換算します。これらの単価や価格は相場や推奨値ではなく、自宅の金額へ置き換える説明用です。</p></details></section>'
        )
    if stage != "cost":
        out.append(
            '<section id="guide-evidence" aria-labelledby="guide-evidence-title"><h2 id="guide-evidence-title">機種別の条件と確認元</h2>'
        )
    shared_html, shared_keys = shared_guide_facts(stage, products)
    out.append(shared_html)
    model_heading = "h2" if stage == "cost" else "h3"
    for p in products:
        out.append(
            '<section class="ps-guide-model" id="'
            + p["anchor"]
            + '"><'
            + model_heading
            + ">"
            + escape(p["name"])
            + "："
            + stage_label
            + "</"
            + model_heading
            + "><p>"
            + escape(p["exact_model"])
            + "</p>"
        )
        selected = [
            f
            for field in GUIDE_REQUIREMENTS[stage]
            for f in p.get("guide_facts", [])
            if f["field"] == field
        ]
        shared_here = False
        for f in selected:
            if (f["field"], tidy(f["text"])) in shared_keys:
                shared_here = True
                continue
            out.append(
                "<p>"
                + escape(tidy(f["text"]))
                + '</p><p class="ps-source"><a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(locator_label(f["locator"]))
                + "</a> ／ 仕様確認 "
                + escape(jp_date(f["checked_at"]))
                + "</p>"
            )
        if shared_here:
            out.append(
                '<p>複数機種で共通の条件は<a href="#guide-'
                + stage
                + '-shared">上の共通欄</a>を参照してください。</p>'
            )
        if not selected:
            out.append(
                "<p>この型番に適用できる具体条件を、公式資料で追加確認しています。確認できるまで他機種の数値や手順は使いません。</p>"
            )
        if stage == "water":
            out.append(
                '<p>排水ホース・アースの条件は<a href="/dishwasher-installation-measurement/#'
                + p["anchor"]
                + '">設置ガイドの'
                + escape(p["name"])
                + "の欄</a>に、同じ型番の確認元つきで掲載しています。</p>"
            )
        if stage == "cost":
            out.append(
                "<p>洗剤：1回分の目安は"
                + escape(summary_cell(p, "cost", "洗剤の1回分"))
                + '（<a href="/dishwasher-detergent-guide/#'
                + p["anchor"]
                + '">洗剤ガイドの'
                + escape(p["name"])
                + "の欄</a>）。</p>"
            )
        if stage == "installation":
            out.append(
                '<div class="ps-installation"'
                + attrs(
                    {
                        "data-ps-installation": json.dumps(
                            p.get("installation", {}),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                    }
                )
                + '><div class="ps-installation-controls" hidden></div>'
                + installation_reference_note(p)
                + "</div>"
            )
        if stage == "cost":
            out.append(
                '<p><a href="#guide-cost-calculator" data-ps-cost-model="'
                + escape(p["exact_model"], quote=True)
                + '">この機種の公表条件を計算フォームで選ぶ</a></p>'
            )
        out.append(
            route_links(p, current_slug=article["slug"])
            + '<p><a href="/'
            + MAIN_SLUG
            + "/#"
            + p["anchor"]
            + '">比較記事の'
            + escape(p["name"])
            + "の欄へ</a></p></section>"
        )
    if stage != "cost":
        out.append("</section>")
    if stage == "cost":
        legacy = build_local_guides(
            guide_registry, today=date.fromisoformat(catalog["editorial_updated_on"])
        )
        approved = next(
            (
                a
                for a in cast(list[dict[str, Any]], legacy["articles"])
                if a["article_id"] == article["slug"]
            ),
            None,
        )
        if not approved:
            raise ValueError("PURCHASE_COST_SOURCE_VALIDATION_FAILED")
        source_section = next(
            n
            for n in fragment(approved["html"]).walk()
            if n.attrs.get("id") == "guide-evidence"
        )
        out.append(
            re.sub(
                r"確認日：(\d{4}-\d{2}-\d{2})",
                lambda m: "確認日：" + jp_date(m.group(1)),
                tidy(source_section.html()),
            )
        )
    out.append(
        '<section id="reader-unknowns"><h2>実機での確認状況</h2><p>'
        + escape(
            tidy(
                article.get("reader_unknowns_note")
                or "実機使用時の静音性、収納のしやすさ、洗浄・乾燥の実感、耐久性は確認していません。"
            )
        )
        + "</p></section>"
    )
    out.append(legacy_source_notes(article, guide_registry, stage_label=stage_label))
    out.append(history_block(article))
    for section in fragment(template).find(tag="section"):
        if section.attrs.get("id") == "ks-next-read":
            out.append(section.html())
    out.append("</div>")
    return "".join(out)


def add_compatibility_anchors(
    rendered: str,
    template: str,
    *,
    normalize: bool = True,
    anchor_targets: Mapping[str, str] | None = None,
) -> str:
    old_root, root = fragment(template), fragment(rendered)
    old_nodes = {
        str(n.attrs["id"]): n
        for n in old_root.walk()
        if isinstance(n.attrs.get("id"), str)
    }
    old = set(old_nodes)
    new = {
        str(n.attrs["id"]) for n in root.walk() if isinstance(n.attrs.get("id"), str)
    }
    sections = {
        n.attrs.get("data-ps-product"): n
        for n in root.walk()
        if n.has("ps-product-offers")
    }
    aliases = {}
    for identity in sorted(old - new) if normalize and sections else []:
        node = old_nodes[identity]
        if not (
            str(identity).endswith("-purchase")
            or "data-raos-purchase-action" in node.attrs
        ):
            continue
        products = {
            n.attrs["data-raos-product-id"]
            for n in node.walk()
            if n.attrs.get("data-raos-product-id")
        }
        parent = node.parent
        while not products and parent:
            product = parent.attrs.get("data-raos-product-id") or parent.attrs.get(
                "data-ps-product"
            )
            if product:
                products.add(product)
            parent = parent.parent
        if len(products) != 1 or next(iter(products)) not in sections:
            raise ValueError("PURCHASE_LEGACY_ANCHOR_IDENTITY_REQUIRED")
        product = next(iter(products))
        alias = Element("span", {"id": str(identity), "data-ps-purchase-alias": "true"})
        section = sections[product]
        section.children.insert(0, alias)
        alias.parent = section
        aliases[str(identity)] = product
        new.add(identity)
    section_ids = {str(n.attrs["id"]): product for product, n in sections.items()}
    for link in root.find(tag="a") if normalize and sections else []:
        href = link.attrs.get("href") or ""
        if href.startswith("#") and href[1:] in {**aliases, **section_ids}:
            product = {**aliases, **section_ids}[href[1:]]
            source: Element | None = link
            while source:
                owner = source.attrs.get("data-raos-product-id") or source.attrs.get(
                    "data-ps-product"
                )
                if owner and owner != product:
                    raise ValueError("PURCHASE_ANCHOR_PRODUCT_MISMATCH")
                source = source.parent
            link.attrs.update(
                {
                    "data-raos-product-id": product,
                    "data-raos-link-purpose": "internal_navigation",
                }
            )
            # Preserve incoming bookmarks, but in-article actions go directly to the section.
            link.attrs["href"] = "#" + str(sections[product].attrs["id"])
        elif not href.startswith("#") and "公式仕様を見る" in link.text():
            parent = link.parent
            while parent and not parent.attrs.get("data-ps-product"):
                parent = parent.parent
            link.attrs["data-raos-link-purpose"] = "official_verify"
            if parent:
                link.attrs["data-raos-product-id"] = parent.attrs["data-ps-product"]
    # Reviewed aliases land beside the corresponding current content, not at the footer.
    for identity, target_id in (anchor_targets or {}).items():
        if identity not in old or identity in new:
            raise ValueError("PURCHASE_LEGACY_ALIAS_SOURCE_INVALID")
        targets = [n for n in root.walk() if n.attrs.get("id") == target_id]
        if len(targets) != 1 or targets[0].tag not in {"section", "article", "li", "aside"}:
            raise ValueError("PURCHASE_LEGACY_ALIAS_TARGET_INVALID")
        section = targets[0]
        alias = Element(
            "span",
            {"id": identity, "data-ps-content-alias": target_id, "tabindex": "-1"},
        )
        section.children.insert(0, alias)
        alias.parent = section
        new.add(identity)
    # Unmapped bookmarks are retained until their individual migration is reviewed.
    return (
        (root.html() if (normalize and sections) or anchor_targets else rendered)
        + '<div class="ps-compat-anchors" aria-hidden="true">'
        + "".join(
            '<span id="' + escape(str(i), quote=True) + '"></span>'
            for i in sorted(str(v) for v in old - new)
        )
        + "</div>"
    )


def render_hub(
    article: Mapping[str, Any], catalog: Mapping[str, Any], template: str
) -> str:
    """The category hub keeps the shared hub skeleton; only the condition list is generated."""
    dish = next(x for x in catalog["articles"] if x["slug"] == MAIN_SLUG)
    hub_template = fragment(template)
    roots = [n for n in hub_template.children if isinstance(n, Element) and n.tag]
    if len(roots) != 1 or not roots[0].has("ks-directory"):
        raise ValueError("PURCHASE_HUB_ROOT_INVALID")
    root = roots[0]
    hub_sections = {node.attrs.get("id"): node for node in root.find(tag="section")}
    for identity in ("kitchen-start", "kitchen-axes", "choose", "compare", "purchase-checks"):
        if identity not in hub_sections:
            raise ValueError("PURCHASE_HUB_SECTION_MISSING")
    navs = {node.attrs.get("aria-label"): node for node in root.find(tag="nav")}
    for label in ("このサイトの入口", "このページの読み方", "ほかの商品カテゴリ", "編集方針"):
        if label not in navs:
            raise ValueError("PURCHASE_HUB_NAV_MISSING")
    if len(root.find(tag="p", cls="ks-reader-note")) != 1:
        raise ValueError("PURCHASE_HUB_NOTE_MISSING")
    visuals = root.find(tag="figure", cls="ks-category-visual")
    if len(visuals) != 1:
        raise ValueError("PURCHASE_HUB_VISUAL_MISSING")
    for visual_image in visuals[0].find(tag="img"):
        # wp_kses_post removes this hint from normal post content.
        visual_image.attrs.pop("decoding", None)
    conditions = "".join(
        "<li>"
        + escape(c["label"])
        + "："
        + condition_product_links(c, catalog["products"], MAIN_SLUG)
        + "</li>"
        for c in dish["conditions"]
    )
    choose = hub_sections["choose"]
    choose.children = []
    choose.append(
        block(
            "<div><h2>条件から候補を見る</h2><p>条件に合う機種の説明へ直接進めます。リンク先は広告リンクを含む比較記事です。設置・給排水・費用などの作業別ガイドは、下の記事一覧から確かめたい作業で選べます。</p><ul>"
            + conditions
            + '</ul><p><a href="/'
            + MAIN_SLUG
            + '/#ps-specs">決め手になる比較表（4機種）</a></p><p>比較の中心はSOLOTA・ラクアmini color・SS-MA251・NP-TSP1です。mini Plusはmini colorと別の型番として扱います。</p></div>'
        )
    )
    inner = choose.children[0]
    if not isinstance(inner, Element):
        raise ValueError("PURCHASE_HUB_CHOOSE_INVALID")
    choose.children = list(inner.children)
    for child in choose.children:
        if isinstance(child, Element):
            child.parent = choose
    return root.html()


def compile_articles(
    catalog: Mapping[str, Any],
    templates: Mapping[str, str],
    guide_registry: Mapping[str, Any],
    product_media: Mapping[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[dict[str, str], dict[str, Any]]:
    validate_catalog(catalog)
    now = current_time(now)
    outputs = {}
    runtime: dict[str, Any] = {
        "schema": "RAOS_PURCHASE_ARTICLE_RUNTIME_V1",
        "articles": [],
    }
    for a in catalog["articles"]:
        a = {
            **a,
            "purchase_normalization": a["post_id"]
            in catalog.get("normalization_pilot_post_ids", [30, 83, 41]),
        }
        template = templates[a["slug"]]
        snapshot = "ps-pending-content-digest"
        bindings: list[dict[str, str]] = []
        display_media: dict[str, str] = {}
        if a["kind"] == "comparison":
            html, bindings = render_comparison(
                a, catalog, template, snapshot, product_media, now=now
            )
            if product_media is not None:
                for pid in a["product_ids"]:
                    product = next(
                        p for p in catalog["products"] if p["product_id"] == pid
                    )
                    if not media_allowed(product, catalog):
                        continue
                    display_media[pid], _ = render_product_media(
                        product, a, snapshot, product_media[pid]
                    )
        elif a["kind"] == "guide":
            html = render_guide(a, catalog, guide_registry, template, now=now)
        elif a["kind"] == "hub":
            html = render_hub(a, catalog, template)
        else:
            html = template
        if a["kind"] != "policy":
            html = add_compatibility_anchors(
                html,
                template,
                normalize=a["purchase_normalization"],
                anchor_targets=a.get("legacy_anchor_targets"),
            )
        rendered = "<!-- wp:html -->\n" + html + "\n<!-- /wp:html -->\n"
        final_snapshot = (
            "ps-"
            + sha256((rendered + canonical(display_media)).encode()).hexdigest()[:32]
        )
        outputs[a["slug"]] = rendered.replace(snapshot, final_snapshot)
        for binding in bindings:
            binding["snapshot_id"] = final_snapshot
        snapshot = final_snapshot
        runtime["articles"].append(
            {
                "article_id": a["article_id"],
                "slug": a["slug"],
                "post_type": a["post_type"],
                "kind": a["kind"],
                "snapshot_id": snapshot,
                "body_sha256": sha256(outputs[a["slug"]].encode()).hexdigest(),
                "bindings": bindings,
                "media": {
                    pid: markup.replace("ps-pending-content-digest", final_snapshot)
                    for pid, markup in display_media.items()
                },
            }
        )
    return outputs, runtime
