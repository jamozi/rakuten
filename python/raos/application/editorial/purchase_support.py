"""Compile the adopted purchase-support contract to bounded public article fragments."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from datetime import timezone
from hashlib import sha256
from html import escape
import json
import re
from typing import Any, cast
from urllib.parse import urlsplit

from raos.domain.editorial.purchase_support import POLICY, PLACEMENTS, money, timestamp
from raos.application.editorial.reader_html import Element, fragment
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
LABELS = {
    "price_yen": "税込本体",
    "shipping_yen": "送料",
    "required_items_yen": "必須品",
}
GUIDE_REQUIREMENTS = {
    "installation": ("dimensions", "door", "clearance", "installation"),
    "water": ("water_supply", "drainage"),
    "cost": ("energy", "water", "detergent"),
    "detergent": ("detergent", "prohibited", "accessories"),
    "maintenance": ("maintenance", "warranty"),
}


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
    for o in offers:
        p = next((p for p in products if p["product_id"] == o.get("product_id")), None)
        if (
            not p
            or o.get("product_model") != p["exact_model"]
            or not https(o.get("url"))
            or not https(o.get("source_url"))
        ):
            raise ValueError("PURCHASE_OFFER_IDENTITY_MISMATCH")
        for key in ("price_yen", "shipping_yen", "required_items_yen"):
            if o.get(key) is not None and not money(o[key]):
                raise ValueError("PURCHASE_MONEY_INVALID")
        if not timestamp(o.get("checked_at")) or not timestamp(o.get("valid_until")):
            raise ValueError("PURCHASE_OFFER_DATE_REQUIRED")
        if o.get("affiliate") is True and (
            o.get("advertiser_authorized") is not True
            or o.get("link_usage_authorized") is not True
            or o.get("site_origin") != ORIGIN
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
    return (
        o.get("identity_verified") is True
        and o.get("state") in {"AVAILABLE", "PREORDER"}
        and o.get("condition") == "new"
        and bool(o.get("variant"))
        and bool(o.get("warranty"))
        and o.get("warranty") != "UNKNOWN"
    )


def attrs(values: Mapping[str, object]) -> str:
    return "".join(f' {k}="{escape(str(v), quote=True)}"' for k, v in values.items())


def route_links(p: Mapping[str, Any]) -> str:
    return (
        '<nav class="ps-model-routes" aria-label="'
        + escape(p["name"])
        + 'の確認先">'
        + " ".join(
            f'<a href="/{slug}/#{p["anchor"]}">{label}</a>'
            for label, slug in STAGES.values()
        )
        + "</nav>"
    )


def cta(
    o: Mapping[str, Any], article: Mapping[str, Any], snapshot: str, placement: str
) -> tuple[str, dict[str, str]]:
    if placement not in PLACEMENTS or not eligible_link(o):
        raise ValueError("PURCHASE_CTA_INELIGIBLE")
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
        }.items()
    }
    attributes = {
        "data-raos-cta-type": "offer",
        **{"data-raos-" + k.replace("_", "-"): v for k, v in binding.items()},
    }
    rel = (
        "sponsored nofollow noopener noreferrer"
        if o.get("affiliate")
        else "noopener noreferrer"
    )
    link = (
        '<a class="ps-offer-link"'
        + attrs(attributes)
        + ' href="'
        + escape(o["url"], quote=True)
        + '" rel="'
        + rel
        + '">'
        + escape(o["seller"])
        + "で購入条件を見る</a>"
    )
    return link, {**binding, "href": o["url"]}


def offer_panel(
    p: Mapping[str, Any],
    catalog: Mapping[str, Any],
    article: Mapping[str, Any],
    snapshot: str,
    placement: str,
) -> tuple[str, list[dict[str, str]]]:
    offers = [o for o in catalog["offers"] if o["product_id"] == p["product_id"]]
    bindings: list[dict[str, str]] = []
    parts = []
    for o in offers:
        # This is an explicitly dated observation, never a claim of live/current price.
        cells = " ／ ".join(
            f"{LABELS[k]}：{o[k]:,}円"
            if o.get(k) is not None
            else f"{LABELS[k]}：未確認"
            for k in LABELS
        )
        observed = timestamp(o["checked_at"])
        day = (
            observed.astimezone(timezone.utc).isoformat(timespec="minutes")
            if observed
            else "未確認"
        )
        data = {
            "data-ps-offer": o["offer_id"],
            "data-ps-checked-at": o["checked_at"],
            "data-ps-valid-until": o["valid_until"],
            "data-ps-identity": str(o.get("identity_verified") is True).lower(),
            "data-ps-state": o["state"],
            "data-ps-complete": str(o.get("total_scope_complete") is True).lower(),
            "data-ps-condition": o["condition"],
        }
        for key in LABELS:
            if o.get(key) is not None:
                data["data-ps-" + key.replace("_", "-")] = o[key]
        rows = (
            '<div class="ps-seller"'
            + attrs(data)
            + "><h4>"
            + escape(o["seller"])
            + "</h4><p>"
            + escape(o["variant"])
            + "</p><p>"
            + escape(cells)
            + "</p>"
        )
        rows += '<p class="ps-price-status">確認時の販売条件です。現在価格の再確認が必要です。</p>'
        rows += (
            '<p class="ps-price-date">販売条件確認：<time datetime="'
            + escape(o["checked_at"])
            + '">'
            + escape(day)
            + "</time> ／ "
            + escape(o.get("price_scope", "本体と記載した費目の範囲"))
            + "</p>"
        )
        rows += (
            "<p>納期："
            + escape(o.get("delivery") or "未確認")
            + " ／ 保証："
            + escape(o.get("warranty") or "未確認")
            + "</p>"
        )
        if eligible_link(o):
            link, binding = cta(o, article, snapshot, placement)
            bindings.append(binding)
            rows += link
        else:
            rows += (
                '<p class="ps-unavailable">'
                + escape(
                    o.get("unavailable_reason")
                    or "販売条件の確認が完了していないため、購入先としての案内を保留しています。"
                )
                + "</p>"
            )
        rows += (
            '<p class="ps-source"><a href="'
            + escape(o["source_url"], quote=True)
            + '">販売条件の確認元</a></p></div>'
        )
        parts.append(rows)
    if not parts:
        parts.append(
            '<p class="ps-unavailable">販売先未確認。型番・構成・販売条件を照合できるまで、購入先の案内を保留しています。</p>'
        )
    return "".join(parts), bindings


def research_panel(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> str:
    rows = [
        i
        for i in catalog["research_issues"]
        if i["product_id"] == p["product_id"] and i["status"] != "RESOLVED"
    ]
    if not rows:
        return ""
    return (
        '<details class="ps-research"><summary>残る確認と、判断を保留する条件</summary>'
        + "".join(
            "<p><strong>"
            + escape(i["topic"])
            + "</strong>："
            + escape(i["impact"])
            + "</p><p>"
            + escape(i["alternative"])
            + '</p><p class="ps-source"><a href="'
            + escape(i["target_url"], quote=True)
            + '">確認先</a> ／ 次回確認 '
            + escape(i["next_check_on"])
            + "</p>"
            for i in rows
        )
        + "</details>"
    )


def specification_table(
    article: Mapping[str, Any], products: list[dict[str, Any]]
) -> str:
    labels = article["spec_labels"]
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
            cells.append(
                '<td data-ps-fact-state="'
                + escape(f["state"] if f else "UNKNOWN")
                + '" data-ps-product="'
                + p["product_id"]
                + '">'
                + escape(value)
                + "</td>"
            )
        rows.append(
            '<tr><th scope="row">' + escape(label) + "</th>" + "".join(cells) + "</tr>"
        )
    return (
        '<div class="ps-table-scroll" tabindex="0" role="region" aria-label="候補の仕様比較"><table class="ps-comparison"><caption>決め手になる仕様。公表値の条件・確認日は商品ごとの出典に記載</caption><thead><tr><th scope="col">比較項目</th>'
        + heads
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
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
    result = "".join(n.html() for n in selected)
    # Evidence classifications stay in the data; no repeated badges in reader prose.
    result = re.sub(
        r'<span[^>]*class="raos-evidence-badge"[^>]*>.*?</span>', "", result
    )
    return result


def render_comparison(
    article: Mapping[str, Any], catalog: Mapping[str, Any], template: str, snapshot: str
) -> tuple[str, list[dict[str, str]]]:
    products = [
        next(p for p in catalog["products"] if p["product_id"] == pid)
        for pid in article["product_ids"]
    ]
    bindings: list[dict[str, str]] = []
    out = [
        '<div class="raos-editorial-v2 ps-article"'
        + attrs(
            {
                "data-raos-purchase-support": "v1",
                "data-raos-article-id": article["article_id"],
                "data-raos-snapshot-id": snapshot,
            }
        )
        + ">"
    ]
    out.append(
        '<p class="ps-disclosure">この記事には広告・アフィリエイトリンクを含む場合があります。実機で使用した評価ではなく、公式資料から用途に合う条件を整理しています。</p>'
    )
    out.append(
        '<p class="ps-lead">'
        + escape(article["intro"])
        + '</p><nav class="ps-toc" aria-label="記事の近道"><a href="#ps-choose">候補を絞る</a><a href="#ps-specs">仕様を比べる</a><a href="#ps-products">向く・向かない条件</a><a href="#ps-offers">購入総額と販売先</a><a href="#ps-evidence">詳細・出典</a></nav>'
    )
    out.append(
        '<section id="ps-choose"><h2>条件別の結論</h2><div class="ps-condition-grid">'
    )
    for c in article["conditions"]:
        names = "、".join(
            next(p["name"] for p in products if p["product_id"] == pid)
            for pid in c["product_ids"]
        )
        out.append(
            "<div><h3>" + escape(c["label"]) + "</h3><p>" + escape(names) + "</p>"
        )
        for pid in c["product_ids"]:
            o = next(
                (
                    o
                    for o in catalog["offers"]
                    if o["product_id"] == pid and eligible_link(o)
                ),
                None,
            )
            if o:
                link, binding = cta(o, article, snapshot, "top_summary")
                out.append(link)
                bindings.append(binding)
        out.append("</div>")
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
        + '></div><p class="ps-note">予算と自宅の入力は保存・送信しません。購入総額に不足がある候補は「予算未判定」として残します。ポイントや条件付きクーポンを一律に差し引きません。</p><p>JavaScriptなしでも、以下の仕様・販売条件・出典を比較できます。予算は確認済み費目を合計して照合してください。</p></section>'
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
        o = next(
            (
                o
                for o in catalog["offers"]
                if o["product_id"] == p["product_id"] and eligible_link(o)
            ),
            None,
        )
        link = "販売先未確認"
        if o:
            link, binding = cta(o, article, snapshot, "comparison_table")
            bindings.append(binding)
        cells.append('<td data-ps-product="' + p["product_id"] + '">' + link + "</td>")
    table = table.replace(
        "</tbody>",
        '<tr data-ps-keep-row><th scope="row">購入条件</th>'
        + "".join(cells)
        + "</tr></tbody>",
    )
    out.append(
        table
        + '</section><section id="ps-products"><h2>向く・向かない理由</h2><div class="ps-product-grid">'
    )
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
        if p["image_markup"]:
            out.append('<div class="ps-product-image">' + p["image_markup"] + "</div>")
        out.append(
            "<p>"
            + escape(p["lead"])
            + "</p><h4>合いやすい条件</h4><ul>"
            + "".join("<li>" + escape(x) + "</li>" for x in p["fit"])
            + "</ul><h4>別の候補も考えたい条件</h4><ul>"
            + "".join("<li>" + escape(x) + "</li>" for x in p["avoid"])
            + "</ul>"
        )
        out.append('<p data-ps-product-budget role="status"></p>')
        if article["slug"] == MAIN_SLUG:
            out.append(route_links(p))
        out.append(
            '<p><a href="#ps-seller-' + p["anchor"] + '">購入総額と販売先へ</a></p>'
        )
        o = next(
            (
                o
                for o in catalog["offers"]
                if o["product_id"] == p["product_id"] and eligible_link(o)
            ),
            None,
        )
        if o:
            link, binding = cta(o, article, snapshot, "product_card")
            out.append(link)
            bindings.append(binding)
        out.append(research_panel(p, catalog) + "</article>")
    out.append(
        '</div></section><section id="ps-offers"><h2>購入総額と販売先</h2><p>構成・送料・必須品・納期・保証を販売先ごとに確認します。異なる構成の価格を同じ商品価格として比べません。</p>'
    )
    for p in products:
        panel, b = offer_panel(p, catalog, article, snapshot, "final_summary")
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
            + research_panel(p, catalog)
            + "</section>"
        )
    out.append(
        '</section><section id="ps-evidence"><h2>必要な詳細と出典</h2><p>性能の評価に価格や広告報酬を加点しません。購入費用は用途・予算に合う候補を選ぶために別に比較します。掲載候補は市場全体の順位ではありません。</p><details><summary>仕様の確認元・適用条件</summary>'
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
                + escape(f["locator"])
                + "</a> ／ 仕様確認 "
                + escape(f["checked_at"])
                + "</li>"
            )
        out.append("</ul>")
    out.append(
        "</details>"
        + preserved_details(template)
        + '</section><p class="ps-note">設置・利用条件が合わない、または必要な情報が確認できない場合は、別候補・別方式・購入保留を選んでください。</p></div>'
    )
    return "".join(out), bindings


def render_guide(
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    guide_registry: Mapping[str, Any],
) -> str:
    stage = next(k for k, (_, slug) in STAGES.items() if slug == article["slug"])
    dish = next(a for a in catalog["articles"] if a["slug"] == MAIN_SLUG)["product_ids"]
    products = [p for p in catalog["products"] if p["product_id"] in dish]
    out = [
        '<div class="raos-editorial-v2 ps-article" data-raos-purchase-support="v1"><nav class="ps-toc"><a href="/kitchen/">食洗機の選び方</a><a href="/'
        + MAIN_SLUG
        + '/">4機種の比較に戻る</a></nav><p class="ps-lead">比較記事と同じ機種で、'
        + STAGES[stage][0]
        + "を確認できます。型番と使う条件をそろえて照合してください。</p>"
    ]
    if stage == "cost":
        cost_article = next(
            a for a in guide_registry["articles"] if a["article_id"] == article["slug"]
        )
        out.append(
            render_cost_profiles(
                cost_article, {f["evidence_ref"]: f for f in guide_registry["facts"]}
            )
        )
        out.append(
            '<section id="build-formula"><h2>確認できた費目の小計と、必要な入力</h2><p>電気代はWh÷1000×電気単価、上下水道代はL÷1000×上下水道の従量単価、洗剤代は適用する一回分の量から計算します。未確認の費目はゼロ円にしません。すべての費目がそろっても、請求総額や手洗いからの節約額を示すものではありません。</p><p>基本料金・調整額・料金段階、使用回数、使うコースは家庭ごとに異なります。定格W×運転時間やタンク容量を一回の消費量へ代用しません。</p><details><summary>仮の単価による記入例</summary><p>入力例に限り、電気30円/kWh・上下水道300円/m³・洗剤5円/回・月30回と仮定します。230Wh・2.5Lの公表条件なら、電気6.9円＋上下水道0.75円＋洗剤5円＝12.65円/回、30回で379.5円です。これらの単価は相場や推奨値ではなく、自宅の金額へ置き換える説明用です。</p></details></section>'
        )
    for p in products:
        out.append(
            '<section class="ps-guide-model" id="'
            + p["anchor"]
            + '"><h2>'
            + escape(p["name"])
            + "："
            + STAGES[stage][0]
            + "</h2><p>"
            + escape(p["exact_model"])
            + "</p>"
        )
        selected = [
            f
            for f in p.get("guide_facts", [])
            if f["field"] in GUIDE_REQUIREMENTS[stage]
        ]
        for f in selected:
            out.append(
                "<p>"
                + escape(f["text"])
                + '</p><p class="ps-source"><a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(f["locator"])
                + "</a> ／ 仕様確認 "
                + escape(f["checked_at"])
                + "</p>"
            )
        if not selected:
            out.append(
                "<p>この型番に適用できる具体条件を、公式資料で追加確認しています。確認できるまで他機種の数値や手順は使いません。</p>"
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
                + '><div class="ps-installation-controls" hidden></div><p>本体寸法・開扉時・必要余白は別々に確保します。数値の照合だけでは、台の強度、排水、電源・アース、水平や熱源との距離を含めた安全な設置を保証しません。</p></div>'
            )
        if stage == "cost":
            out.append(
                '<p><a href="#guide-cost-calculator" data-ps-cost-model="'
                + escape(p["exact_model"], quote=True)
                + '">この機種の公表条件を計算フォームで選ぶ</a></p>'
            )
        out.append(
            research_panel(p, catalog)
            + route_links(p)
            + '<p><a href="/'
            + MAIN_SLUG
            + "/#ps-seller-"
            + p["anchor"]
            + '">この機種の購入総額と販売先</a></p></section>'
        )
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
        out.append(source_section.html())
    out.append(
        "<p>実機使用時の静音性、収納のしやすさ、洗浄・乾燥の実感、耐久性は確認していません。</p></div>"
    )
    return "".join(out)


def add_compatibility_anchors(rendered: str, template: str) -> str:
    old = {
        n.attrs["id"]
        for n in fragment(template).walk()
        if isinstance(n.attrs.get("id"), str)
    }
    new = {
        n.attrs["id"]
        for n in fragment(rendered).walk()
        if isinstance(n.attrs.get("id"), str)
    }
    # Keep incoming bookmarks valid without retaining duplicate introductory prose.
    return (
        rendered
        + '<div class="ps-compat-anchors" aria-hidden="true">'
        + "".join(
            '<span id="' + escape(str(i), quote=True) + '"></span>'
            for i in sorted(str(v) for v in old - new)
        )
        + "</div>"
    )


def compile_articles(
    catalog: Mapping[str, Any],
    templates: Mapping[str, str],
    guide_registry: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, Any]]:
    validate_catalog(catalog)
    outputs = {}
    runtime: dict[str, Any] = {
        "schema": "RAOS_PURCHASE_ARTICLE_RUNTIME_V1",
        "articles": [],
    }
    for a in catalog["articles"]:
        template = templates[a["slug"]]
        snapshot = "ps-pending-content-digest"
        bindings: list[dict[str, str]] = []
        if a["kind"] == "comparison":
            html, bindings = render_comparison(a, catalog, template, snapshot)
        elif a["kind"] == "guide":
            html = render_guide(a, catalog, guide_registry)
        elif a["kind"] == "hub":
            dish = next(x for x in catalog["articles"] if x["slug"] == MAIN_SLUG)
            conditions = "".join(
                "<li>"
                + escape(c["label"])
                + '：<a href="/'
                + MAIN_SLUG
                + '/#ps-choose">'
                + escape(
                    "、".join(
                        next(
                            p["name"]
                            for p in catalog["products"]
                            if p["product_id"] == pid
                        )
                        for pid in c["product_ids"]
                    )
                )
                + "</a></li>"
                for c in dish["conditions"]
            )
            html = (
                '<div class="ps-article"><p class="ps-lead">いつもの一食分・置き場所・予算から、食洗機の候補を絞れます。</p><section id="choose"><h2>条件から候補を見る</h2><ul>'
                + conditions
                + '</ul><p><a href="/'
                + MAIN_SLUG
                + '/#ps-choose">4機種を、予算と置き場所から比較する</a></p></section><section id="compare"><h2>残った疑問を確認する</h2><ul>'
                + "".join(
                    '<li><a href="/'
                    + slug
                    + '/">'
                    + label
                    + "を機種ごとに確認</a></li>"
                    for label, slug in STAGES.values()
                )
                + '</ul><p><a href="/solota-vs-rakua-mini-plus/">SOLOTAとラクアmini Plusの対象・違いを確認</a></p></section><p>比較の中心はSOLOTA・ラクアmini color・SS-MA251・NP-TSP1です。mini Plusはmini colorと別の型番として扱います。</p></div>'
            )
        else:
            html = template
        if a["kind"] != "policy":
            html = add_compatibility_anchors(html, template)
        rendered = "<!-- wp:html -->\n" + html + "\n<!-- /wp:html -->\n"
        final_snapshot = "ps-" + sha256(rendered.encode()).hexdigest()[:32]
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
            }
        )
    return outputs, runtime
