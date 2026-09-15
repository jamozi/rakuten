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
    reference_price,
)
from raos.application.editorial.reader_html import (
    Element,
    block,
    fragment,
    readable_tables,
)
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
    # Everyday amounts, tablets and prohibitions are in the answer table above it.
    "detergent": ("公表試験条件の洗剤量",),
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
FACT_STATES = frozenset({"KNOWN", "PRESERVED", "UNKNOWN", "CONFLICT"})
# A fact in either state is not settled enough for a reader to act on its value.
UNSETTLED_FACT_STATES = frozenset({"UNKNOWN", "CONFLICT"})
# installation keys, fact label prefix, guide_facts field, ordered restatement.
INSTALLATION_FACT_GROUPS: tuple[tuple[tuple[str, ...], str, str, bool], ...] = (
    (("width_mm", "depth_mm", "height_mm"), "本体寸法", "dimensions", True),
    (("door_depth_mm", "door_height_mm"), "開扉時の寸法", "door", False),
    (("above_mm", "left_mm", "right_mm", "rear_mm"), "必要な余白", "clearance", False),
)
# ASCII-bounded decimal numbers. A digit run preceded by an ASCII letter or digit
# (model names such as TDWS25SBL or NP-TSP1) is not a dimension token; a unit
# such as "mm" may follow directly. No \b, because it misreads Japanese text.
NUMBER_TOKEN = re.compile(r"(?<![A-Za-z0-9_.])[0-9]+(?:\.[0-9]+)?(?![0-9]|\.[0-9])")
DECISION_STEPS_PLACEMENTS = frozenset(
    {"before_conditions", "after_conditions", "after_specs"}
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
    return str(text).replace("～", "〜").replace("。 ", "。").replace("　", " ")


INTERNAL_STATE_TOKENS = frozenset({"UNKNOWN", "UNAVAILABLE", "UNVERIFIED", "NONE", "N/A"})


def reader_label(value: object, *, unknown: str = "未確認") -> str:
    """Readable text for a catalog value; internal state enums never reach the reader.

    Machine state stays in data-* attributes. Visible text shows the unverified
    state in Japanese instead of the enum name (KS-008)."""
    if value is None:
        return unknown
    text = tidy(value).strip()
    if not text or text.upper() in INTERNAL_STATE_TOKENS:
        return unknown
    return text


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


def installation_fact_group(
    record: Mapping[str, Any],
) -> tuple[tuple[str, ...], str, str, bool] | None:
    """Return the installation group a fact (by label) or guide fact (by field) restates."""
    for group in INSTALLATION_FACT_GROUPS:
        _, label, field, _ = group
        if "label" in record:
            if str(record["label"]).startswith(label):
                return group
        elif record.get("field") == field:
            return group
    return None


def validate_fact_state(p: Mapping[str, Any], record: Mapping[str, Any]) -> None:
    """Keep a source conflict distinct from an unresearched value.

    CONFLICT needs at least two structured sources with distinct (source_url,
    locator) pairs. A CONFLICT record that restates an installation group of a
    product with installation values must name the contradicted keys in
    conflict_installation_keys, and each named key must stay None so that no
    contradicted value reaches the numeric fit check. Which keys are contradicted
    is an editorial record; keys that are not named are not checked here.
    """
    state = record.get("state")
    if state not in FACT_STATES:
        raise ValueError("PURCHASE_FACT_SOURCE_REQUIRED")
    if state != "CONFLICT":
        if "conflict_sources" in record or "conflict_installation_keys" in record:
            raise ValueError("PURCHASE_FACT_CONFLICT_SOURCES_UNEXPECTED")
        return
    sources = record.get("conflict_sources")

    def text_value(value: object) -> bool:
        return isinstance(value, str) and bool(value.strip())

    if (
        not isinstance(sources, list)
        or len(sources) < 2
        or any(
            not isinstance(source, dict)
            or not text_value(source.get("value"))
            or not https(source.get("source_url"))
            or not text_value(source.get("locator"))
            or not text_value(source.get("checked_at"))
            or ("label" in source and not text_value(source.get("label")))
            for source in sources
        )
        or len({(source["source_url"], source["locator"]) for source in sources})
        != len(sources)
    ):
        raise ValueError("PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED")
    group = installation_fact_group(record)
    installation = p.get("installation") or {}
    keys = record.get("conflict_installation_keys")
    if group is None or not installation:
        if keys is not None:
            raise ValueError("PURCHASE_CONFLICT_INSTALLATION_KEYS_INVALID")
        return
    if not isinstance(keys, list) or not keys:
        raise ValueError("PURCHASE_CONFLICT_INSTALLATION_KEYS_REQUIRED")
    if (
        not all(isinstance(key, str) for key in keys)
        or len(set(keys)) != len(keys)
        or not set(keys) <= set(group[0])
    ):
        raise ValueError("PURCHASE_CONFLICT_INSTALLATION_KEYS_INVALID")
    if any(installation.get(key) is not None for key in keys):
        raise ValueError("PURCHASE_CONFLICT_VALUE_ASSERTED")


def conflict_values(record: Mapping[str, Any]) -> str:
    """Every official value of a CONFLICT record, each named by its source.

    A source is named by its short label when the record has one, otherwise by
    its locator. The values are listed side by side; none is chosen.
    """
    return "、".join(
        (
            tidy(source["label"]).strip() + " " + tidy(source["value"]).strip()
            if source.get("label")
            else locator_label(tidy(source["locator"]).strip())
            + "："
            + tidy(source["value"]).strip()
        )
        for source in record.get("conflict_sources") or []
    )


def conflict_note(record: Mapping[str, Any]) -> str:
    """Reader sentence for a CONFLICT record (KS-009); empty for every other state."""
    if record.get("state") != "CONFLICT":
        return ""
    # The manuals give no value that settles either conflict, so the reader is sent
    # to the manufacturer (amended decision 1).
    return (
        "公式資料で値が異なります（"
        + conflict_values(record)
        + "）。どちらの値かはメーカー（相談窓口）へ確認してください。"
    )


def conflict_source_links(record: Mapping[str, Any]) -> str:
    """Links to every source of a CONFLICT record (KS-009); empty for other states.

    The caller renders the record's own source link; this adds one link per
    conflicting source, named by its short label (or locator), so each official
    value in the note stays reachable.
    """
    if record.get("state") != "CONFLICT":
        return ""
    return " ／ 値が異なる出典：" + "・".join(
        '<a href="'
        + escape(source["source_url"], quote=True)
        + '">'
        + escape(
            tidy(source["label"]).strip()
            if source.get("label")
            else locator_label(tidy(source["locator"]).strip())
        )
        + "</a>"
        for source in record.get("conflict_sources") or []
    )


def fact_text(record: Mapping[str, Any]) -> str:
    """Visible text of a fact or guide fact; a CONFLICT record leads with its note."""
    return conflict_note(record) + str(record["text"])


def installation_conflicts(p: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    """Installation keys left out of the fit check because official sources differ."""
    found: dict[str, Mapping[str, Any]] = {}
    for record in [*p.get("facts", []), *p.get("guide_facts", [])]:
        if record.get("state") == "CONFLICT":
            for key in record.get("conflict_installation_keys") or []:
                found.setdefault(key, record)
    return found


def installation_consistency_mismatches(p: Mapping[str, Any]) -> list[dict[str, Any]]:
    """List where fact and guide texts do not restate the installation numbers.

    installation is the numeric source used by the fit check; facts (label
    prefix) and guide_facts (field) of the same group must restate it.

    - 本体寸法 / dimensions: the first three ASCII number tokens of every text
      must equal (width_mm, depth_mm, height_mm) in that order.
    - 開扉時の寸法 / door and 必要な余白 / clearance: containment only. Every
      non-null value must occur among the text's number tokens. This is a smoke
      check: it cannot detect a value that drifts to a number already present in
      the same text (for example NP-TMLK1 door_depth_mm 485 to 502 or 490,
      above_mm 55 to 50, left_mm 5 to 50; NP-TSP1 above_mm 120 to 115).
    - A group whose keys are all None is skipped, whatever the record state.
    - Digits joined to ASCII letters (model names) are not tokens; numbers written
      in another form (full-width digits, cm) are not recognised and are reported.
    - Only the catalog is read; non-live copies of the same dimensions in other
      files are not checked.

    Rows are ordered by group, then facts before guide_facts. Nothing is raised.
    """
    installation = p.get("installation") or {}
    if not installation:
        return []
    rows: list[dict[str, Any]] = []
    for keys, label, field, ordered in INSTALLATION_FACT_GROUPS:
        values: dict[str, float | None] = {
            key: None if installation.get(key) is None else float(installation[key])
            for key in keys
        }
        asserted = [key for key in keys if values[key] is not None]
        if not asserted:
            continue
        sources = (
            (
                "facts",
                "label",
                label,
                [
                    f
                    for f in p.get("facts", [])
                    if str(f.get("label", "")).startswith(label)
                ],
            ),
            (
                "guide_facts",
                "field",
                field,
                [f for f in p.get("guide_facts", []) if f.get("field") == field],
            ),
        )
        base = {"product_id": p.get("product_id"), "group": field}
        for source, _, name, records in sources:
            if not records:
                rows.append(
                    {
                        **base,
                        "source": source,
                        "name": name,
                        "keys": asserted,
                        "code": "PURCHASE_DIMENSION_SOURCE_REQUIRED",
                    }
                )
        for source, name_key, _, records in sources:
            for record in records:
                numbers = [
                    float(token)
                    for token in NUMBER_TOKEN.findall(str(record.get("text", "")))
                ]
                if ordered:
                    head = numbers[: len(keys)]
                    missing = [
                        key
                        for index, key in enumerate(keys)
                        if values[key] is not None
                        and (index >= len(head) or head[index] != values[key])
                    ]
                else:
                    missing = [key for key in asserted if values[key] not in numbers]
                if missing:
                    rows.append(
                        {
                            **base,
                            "source": source,
                            "name": record.get(name_key),
                            "keys": missing,
                            "code": "PURCHASE_DIMENSION_SOURCE_MISMATCH",
                        }
                    )
    return rows


def validate_installation_consistency(p: Mapping[str, Any]) -> None:
    """Raise the first problem found by installation_consistency_mismatches."""
    codes = {row["code"] for row in installation_consistency_mismatches(p)}
    for code in (
        "PURCHASE_DIMENSION_SOURCE_REQUIRED",
        "PURCHASE_DIMENSION_SOURCE_MISMATCH",
    ):
        if code in codes:
            raise ValueError(code)


CAPACITY_ROUTE_HREF = re.compile(r"/([a-z0-9-]+)/")


def validate_capacity_routes(routes: object, slugs: set[str]) -> None:
    """Capacity routes link only to comparisons that exist in this catalog."""
    if (
        not isinstance(routes, dict)
        or set(routes) != {"title", "intro", "links"}
        or any(
            not isinstance(routes[key], str) or not routes[key].strip()
            for key in ("title", "intro")
        )
        or not isinstance(routes["links"], list)
        or not 1 <= len(routes["links"]) <= 6
        or any(
            not isinstance(link, dict)
            or set(link) != {"href", "label", "note"}
            or any(
                not isinstance(link[key], str) or not link[key].strip()
                for key in ("href", "label", "note")
            )
            for link in routes["links"]
        )
        or len({link["href"] for link in routes["links"]}) != len(routes["links"])
    ):
        raise ValueError("PURCHASE_CAPACITY_ROUTES_INVALID")
    for link in routes["links"]:
        match = CAPACITY_ROUTE_HREF.fullmatch(link["href"])
        if match is None or match.group(1) not in slugs:
            raise ValueError("PURCHASE_CAPACITY_ROUTE_UNKNOWN")


def capacity_routes_markup(routes: Mapping[str, Any]) -> str:
    """Readers who choose by the amount of dishes go to the capacity comparisons."""
    return (
        '<section id="ps-capacity-routes"><h2>'
        + escape(routes["title"])
        + "</h2><p>"
        + escape(tidy(routes["intro"]))
        + "</p><ul>"
        + "".join(
            '<li><a href="'
            + escape(link["href"], quote=True)
            + '">'
            + escape(link["label"])
            + "</a>："
            + escape(tidy(link["note"]))
            + "</li>"
            for link in routes["links"]
        )
        + "</ul></section>"
    )


def validate_catalog(catalog: Mapping[str, Any]) -> None:
    if (
        catalog.get("schema") != "RAOS_READER_PURCHASE_SUPPORT_V1"
        or catalog.get("policy") != POLICY
    ):
        raise ValueError("PURCHASE_POLICY_INVALID")
    products = catalog.get("products", [])
    ids = [p["product_id"] for p in products]
    expanded = "target_post_ids" in catalog
    if not ids or len(ids) != len(set(ids)) or (not expanded and len(ids) != 16):
        raise ValueError("PURCHASE_PRODUCT_IDENTITIES_REQUIRED")
    articles = catalog.get("articles", [])
    if len({a["article_id"] for a in articles}) != len(articles):
        raise ValueError("PURCHASE_DUPLICATE_ARTICLE")
    comparisons = [a for a in articles if a["kind"] == "comparison"]
    expected = (
        {41, 83, 30, 28, 19, 82, 84, 85, 86, 29} if expanded else {41, 83, 30, 28}
    )
    if (
        expanded
        and (
            len(catalog["target_post_ids"]) != len(expected)
            or set(catalog["target_post_ids"]) != expected
        )
    ) or (
        len(comparisons) != len(expected)
        or {a["post_id"] for a in comparisons} != expected
    ):
        raise ValueError("PURCHASE_COMPARISON_SCOPE_REQUIRED")
    used = set()
    for a in comparisons:
        main_ids = a.get("product_ids", [])
        extra_ids = a.get("supplementary_product_ids", [])
        if (
            len(main_ids) not in ({2, 3, 4} if expanded else {4})
            or len(main_ids) != len(set(main_ids))
            or len(extra_ids) != len(set(extra_ids))
            or len(extra_ids) > 4
            or set(main_ids) & set(extra_ids)
            or not set(main_ids + extra_ids) <= set(ids)
        ):
            raise ValueError("PURCHASE_COMPARISON_PRODUCTS_INVALID")
        if any(
            not set(c["product_ids"]) <= set(main_ids) for c in a.get("conditions", [])
        ):
            raise ValueError("PURCHASE_CONDITION_PRODUCT_MISMATCH")
        exclusions = a.get("media_exclusions", {})
        if (
            not isinstance(exclusions, dict)
            or not set(exclusions) <= set(main_ids)
            or any(
                not isinstance(reason, str) or not reason.strip()
                for reason in exclusions.values()
            )
        ):
            raise ValueError("PURCHASE_MEDIA_EXCLUSION_INVALID")
        used.update(main_ids + extra_ids)
    for article in articles:
        note = article.get("choose_note")
        if note is not None and (not isinstance(note, str) or not note.strip()):
            raise ValueError("PURCHASE_CHOOSE_NOTE_INVALID")
    slugs = {a["slug"] for a in articles}
    for article in articles:
        if "capacity_routes" in article:
            validate_capacity_routes(article["capacity_routes"], slugs)
    for article in articles:
        if article["kind"] != "curated_comparison":
            continue
        selected = article.get("product_ids", [])
        if (
            not 2 <= len(selected) <= 32
            or len(selected) != len(set(selected))
            or not set(selected) <= set(ids)
            or not article.get("commerce_anchor")
        ):
            raise ValueError("PURCHASE_CURATED_SCOPE_INVALID")
        used.update(selected)
    if used != set(ids):
        raise ValueError("PURCHASE_UNUSED_PRODUCT")
    for p in products:
        if not p["exact_model"] or not https(p["official_url"]):
            raise ValueError("PURCHASE_IDENTITY_SOURCE_REQUIRED")
        for f in p["facts"]:
            if f.get("exact_model") != p["exact_model"]:
                raise ValueError("PURCHASE_FACT_MODEL_MISMATCH")
            if (
                f.get("state") not in FACT_STATES
                or not https(f["source_url"])
                or not f["locator"]
                or not f["checked_at"]
            ):
                raise ValueError("PURCHASE_FACT_SOURCE_REQUIRED")
            validate_fact_state(p, f)
        for f in p.get("guide_facts", []):
            if (
                f["exact_model"] != p["exact_model"]
                or not https(f["source_url"])
                or not f["locator"]
                or not f["checked_at"]
            ):
                raise ValueError("PURCHASE_GUIDE_MODEL_SOURCE_MISMATCH")
            validate_fact_state(p, f)
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
        validate_installation_consistency(p)
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
    reason_kinds = {
        "research_pending",
        "manufacturer_not_published",
        "source_unavailable",
        "source_conflict",
        "expired",
        "hands_on_required",
        "condition_dependent",
    }
    for issue in issues:
        reason = issue.get("unknown_reason")
        if reason is not None and (
            not isinstance(reason, dict)
            or reason.get("kind") not in reason_kinds
            or not all(
                isinstance(reason.get(k), str) and reason[k].strip()
                for k in ("impact", "next_action", "owner")
            )
        ):
            raise ValueError("PURCHASE_UNKNOWN_REASON_INVALID")
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


def product_offers(
    p: Mapping[str, Any], catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [o for o in catalog["offers"] if o["product_id"] == p["product_id"]]


def purchasable_offer(
    p: Mapping[str, Any], catalog: Mapping[str, Any]
) -> dict[str, Any] | None:
    return next((o for o in product_offers(p, catalog) if eligible_link(o)), None)


def verified_offers(
    p: Mapping[str, Any], catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
    return [o for o in product_offers(p, catalog) if o.get("identity_verified") is True]


def independent_image_review_valid(p: Mapping[str, Any]) -> bool:
    """An exact reviewed photo may come from a different listing than the offer."""
    review = p.get("image_review", {})
    identity = review.get("listing_identity", {})
    return (
        review.get("state") == "VERIFIED_REGISTERED_MEDIA"
        and review.get("basis") == "RAKUTEN_GENERATED_VERBATIM"
        and review.get("display_purpose") == "verified_image_reference"
        and review.get("visual_identity_verified") is True
        and timestamp(review.get("reviewed_at")) is not None
        and https(review.get("listing_url"))
        and identity.get("product_id") == p.get("product_id")
        and identity.get("exact_model") == p.get("exact_model")
        and bool(identity.get("variant"))
        and identity.get("condition") in {"new", "used", "UNKNOWN"}
        and (identity.get("condition") != "used" or "中古" in review.get("caption", ""))
    )


def media_allowed(p: Mapping[str, Any], catalog: Mapping[str, Any]) -> bool:
    """Keep reviewed product identification separate from an orderability claim.

    A newly reviewed listing reference can show the exact authorized picture
    when the listing is sold out or its new condition is still unknown. It must
    identify that same seller and product; it never makes its price eligible.
    Unreviewed media retains the existing closed behavior.
    """
    review = p.get("image_review", {})
    if review.get("state") != "VERIFIED_REGISTERED_MEDIA":
        return False
    if review.get("display_purpose") == "verified_image_reference":
        return independent_image_review_valid(p)
    if review.get("display_purpose") == "verified_listing_reference":
        return any(
            o.get("identity_verified") is True
            and o.get("merchant_url") == review.get("listing_url")
            and o.get("state") in {"AVAILABLE", "PREORDER", "SOLD_OUT", "UNKNOWN"}
            and o.get("condition") in {"new", "UNKNOWN"}
            and review.get("visual_identity_verified") is True
            and timestamp(review.get("reviewed_at")) is not None
            for o in product_offers(p, catalog)
        )
    return purchasable_offer(p, catalog) is not None


def price_expiry(o: Mapping[str, Any]) -> datetime | None:
    checked, deadline = timestamp(o.get("checked_at")), timestamp(o.get("valid_until"))
    if not checked or not deadline:
        return None
    return min(deadline, checked + MAX_PRICE_AGE)


def price_expired(o: Mapping[str, Any], now: datetime) -> bool:
    expiry = price_expiry(o)
    checked, deadline = timestamp(o.get("checked_at")), timestamp(o.get("valid_until"))
    return (
        expiry is None
        or checked is None
        or deadline is None
        or deadline <= checked
        or now >= expiry
    )


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


def route_links(
    p: Mapping[str, Any], *, current_slug: str | None = None, heading: str = "h4"
) -> str:
    """Stage links for one model as a headed list, not a navigation landmark.

    heading is one level below the model heading: h3 under an h2 model section.
    """
    if heading not in {"h3", "h4"}:
        raise ValueError("PURCHASE_ROUTE_HEADING_INVALID")
    links = [
        f'<li><a href="/{slug}/#{p["anchor"]}">{label}</a></li>'
        for label, slug in STAGES.values()
        if slug != current_slug
    ]
    if not links:
        return ""
    return (
        f'<div class="ps-model-routes-block"><{heading}>ほかのガイドで'
        + escape(p["name"])
        + f'を確認</{heading}><ul class="ps-model-routes">'
        + "".join(links)
        + "</ul></div>"
    )


def cta(
    o: Mapping[str, Any],
    article: Mapping[str, Any],
    snapshot: str,
    placement: str,
    *,
    listing_reference: bool = False,
    context_id: str = "",
) -> tuple[str, dict[str, str]]:
    if context_id and (
        placement != "top_summary" or not re.fullmatch(r"[a-z0-9-]{1,32}", context_id)
    ):
        raise ValueError("PURCHASE_CTA_CONTEXT_INVALID")
    if placement not in PLACEMENTS:
        raise ValueError("PURCHASE_CTA_INELIGIBLE")
    resolved = resolve_offer(o)
    if listing_reference:
        href = (
            (o.get("affiliate_url") or o.get("url"))
            if resolved["affiliate_ready"]
            else o.get("merchant_url")
        )
        if (
            o.get("identity_verified") is not True
            or not o.get("variant")
            or o.get("condition") not in {"new", "UNKNOWN"}
            or o.get("state") not in {"AVAILABLE", "PREORDER", "UNKNOWN", "SOLD_OUT"}
            or not https(href)
        ):
            raise ValueError("PURCHASE_CTA_INELIGIBLE")
        resolved = {
            **resolved,
            "href": href,
            "link_purpose": "affiliate_purchase"
            if resolved["affiliate_ready"]
            else "merchant_purchase",
        }
    elif not eligible_link(o):
        raise ValueError("PURCHASE_CTA_INELIGIBLE")
    binding = {
        k: str(v)
        for k, v in {
            "article_id": article["article_id"],
            "product_id": o["product_id"],
            "seller_id": o["seller_id"],
            "offer_id": o["offer_id"],
            "cta_id": f"purchase-{article.get('post_id') or article['slug']}-{o['offer_id']}-{placement}"
            + ("-" + context_id if context_id else ""),
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
        + (
            "楽天で見る"
            if listing_reference
            and urlsplit(o.get("merchant_url", "")).hostname == "item.rakuten.co.jp"
            else "販売先で見る"
            if listing_reference
            else escape(tidy(o["seller"])) + "で購入条件を見る"
        )
        + "</a>"
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
        # Cacheable HTML never contains a price amount in readable content. The
        # clock-checked enhancement is the only owner of ephemeral price text.
        rows += (
            '<p class="ps-price-status" role="status">本体価格・送料・必須品は販売先で確認してください。'
            "確認値は有効期限内に限り補助表示します。</p>"
        )
        if o.get("condition_note"):
            rows += (
                '<p class="ps-condition-note">'
                + escape(tidy(o["condition_note"]))
                + "</p>"
            )
        if o.get("shipping_note"):
            rows += (
                '<p class="ps-shipping-note">'
                + escape(tidy(o["shipping_note"]))
                + "</p>"
            )
        rows += (
            '<p class="ps-price-date">販売条件確認：<time datetime="'
            + escape(o["checked_at"])
            + '">'
            + escape(jp_datetime(checked) + "（日本時間）")
            + "</time>"
            + "／"
            + escape(tidy(o.get("price_scope", "本体と記載した費目の範囲")))
            # Rakuten Web Service terms: the update time and a disclaimer (or a link to it)
            # sit next to price and availability information. The clock script rewrites
            # `.ps-price-status`, so the link lives in this static line instead.
            + '／<a href="/about-ad-policy/#production-about-rakuten-price">価格・販売可能情報の注意</a>'
            + "</p>"
        )
        rows += (
            "<p>納期："
            + escape(reader_label(o.get("delivery")))
            + "／保証："
            + escape(reader_label(o.get("warranty")))
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


def reference_price_markup(
    product: Mapping[str, Any], offer: Mapping[str, Any], now: datetime
) -> str:
    """Emit inert, snapshot-bound price data; readable amounts are clock-owned."""
    ref = reference_price(offer, product, now)
    data: dict[str, object] = {"class": "ps-reference-price", "role": "status"}
    if ref is not None:
        data["data-ps-reference-price"] = canonical(
            {**ref, "seller": offer["seller"], "seller_id": offer["seller_id"]}
        )
    return "<p" + attrs(data) + ">価格は販売先で確認</p>"


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


def active_issues(
    p: Mapping[str, Any], catalog: Mapping[str, Any]
) -> list[dict[str, Any]]:
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
        reason = i.get("unknown_reason")
        if reason:
            label = {
                "research_pending": "追加調査中",
                "manufacturer_not_published": "メーカー未公表",
                "source_unavailable": "資料を再確認中",
                "source_conflict": "公式表記に不一致",
                "expired": "確認期限切れ",
                "hands_on_required": "実機での確認が必要",
                "condition_dependent": "利用条件により異なる",
            }[reason["kind"]]
            item += (
                '<p class="ps-unknown-reason">'
                + escape(label)
                + "："
                + escape(tidy(reason["next_action"]))
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
                " ／ 次回確認 "
                + escape(jp_date(next_check_date(i, offers, today).isoformat()))
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


def fact_reference(
    product: Mapping[str, Any], fact: Mapping[str, Any]
) -> tuple[str, int]:
    keys = list(
        dict.fromkeys(
            (f["source_url"], f["locator"], f["checked_at"]) for f in product["facts"]
        )
    )
    number = keys.index((fact["source_url"], fact["locator"], fact["checked_at"])) + 1
    return "ps-source-" + product["anchor"] + "-" + str(number), number


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
            value = fact_text(f) if f else "未確認"
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
                    + conflict_source_links(f)
                    + "</span>"
                )
            if f and not with_sources:
                source_id, number = fact_reference(p, f)
                source = (
                    '<sup class="ps-reference"><a href="#'
                    + escape(source_id, quote=True)
                    + '" aria-label="'
                )
                source += (
                    escape(
                        p["name"] + "：" + label + "の出典" + str(number), quote=True
                    )
                    + '">['
                    + str(number)
                    + "]</a></sup>"
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
    conflicts = installation_conflicts(p)
    known = [
        escape(INSTALLATION_LABELS[key]) + escape(f"{values[key]:g}") + "mm"
        for key in INSTALLATION_LABELS
        if money(values.get(key))
    ]
    unknown = [
        escape(INSTALLATION_LABELS[key])
        for key in INSTALLATION_LABELS
        if not money(values.get(key)) and key not in conflicts
    ]
    differing = [
        escape(INSTALLATION_LABELS[key])
        + "（"
        + escape(conflict_values(conflicts[key]))
        + "）"
        for key in INSTALLATION_LABELS
        if not money(values.get(key)) and key in conflicts
    ]
    note = (
        '<p class="ps-installation-reference">'
        + escape(p["exact_model"])
        + "の照合基準（公表値・条件を満たす計算値）："
        + ("／".join(known) if known else "未確認")
        + "。"
    )
    if unknown:
        note += (
            "公式資料で数値を確認できていない項目："
            + "、".join(unknown)
            + "。この項目は数値で照合できないため、設置場所の実測と公式資料で個別に確認してください。"
        )
    if differing:
        note += (
            "公式資料で値が異なる項目："
            + "、".join(differing)
            + "。この項目も数値で照合しないため、どちらの値かはメーカー（相談窓口）へ確認してください。"
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
        if (
            review.get("state") == "UNVERIFIED"
            and isinstance(review.get("reason"), str)
            and review["reason"].strip()
        ):
            resolved[pid] = {"withheld": True, "reason": review["reason"]}
            continue
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
        if review.get("display_purpose") == "verified_image_reference" and (
            not independent_image_review_valid(product)
            or review.get("listing_url") != record.get("item_url")
        ):
            raise ValueError("PURCHASE_MEDIA_IMAGE_REVIEW_REQUIRED")
        if review.get("display_purpose") == "verified_listing_reference" and (
            review.get("listing_url") != record.get("item_url")
            or review.get("visual_identity_verified") is not True
            or not timestamp(review.get("reviewed_at"))
        ):
            raise ValueError("PURCHASE_MEDIA_LISTING_REVIEW_REQUIRED")
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


def product_image_label(product: Mapping[str, Any]) -> str:
    """Accessible name for a product photo: the catalog name, plus the model only when absent.

    Most catalog names already carry the model ("… NP-TMLK1-K"). Appending it again would
    repeat the double-concatenation fixed in KS-132, so the model is added only for names
    that do not contain it (for example "Anker Solix C1000 Portable Power Station").
    """
    name = tidy(product["name"]).strip()
    model = str(product.get("exact_model") or "").strip()
    heads = [h for h in re.split(r"\s*/\s*", model) if h]

    def compact(value: str) -> str:
        return re.sub(r"[\s\-_*（）()]", "", value).upper()

    if not heads or any(
        compact(h) in compact(name) or compact(h)[:5] in compact(name) for h in heads
    ):
        return name
    return name + " " + model


def render_product_media(
    product: Mapping[str, Any],
    article: Mapping[str, Any],
    snapshot: str,
    media: Mapping[str, Any],
    *,
    context: str = "product_card",
    context_id: str = "",
) -> tuple[str, list[dict[str, str]]]:
    if context not in {"product_card", "top_summary"} or (
        context == "top_summary" and not re.fullmatch(r"[a-z0-9-]{1,32}", context_id)
    ):
        raise ValueError("PURCHASE_MEDIA_CONTEXT_INVALID")
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
    parts = [
        '<figure class="ps-product-image ps-rakuten-product-photo" aria-label="'
        + escape(product_image_label(product) + "の商品画像", quote=True)
        + '">'
    ]
    for size in ("300", "240"):
        source = media["sizes"][size]
        binding = {
            "article_id": article["article_id"],
            "product_id": product["product_id"],
            "seller_id": media["seller_id"],
            "offer_id": "image-" + product["product_id"] + "-" + size,
            "cta_id": "purchase-image-"
            + product["product_id"]
            + "-"
            + size
            + ("-condition-" + context_id if context == "top_summary" else ""),
            "placement": context,
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
    if article.get("commerce_presentation") in {"images_and_links", "comparison_rows"}:
        parts.append(
            "<figcaption>"
            + escape(product.get("image_review", {}).get("caption", product["name"]))
            + "（広告）</figcaption></figure>"
        )
        return "".join(parts), bindings
    parts.append(
        "<figcaption>広告リンク：楽天市場（"
        + escape(tidy(media["shop_name"]))
        + "）の販売ページへ進みます。構成・送料・保証の適用条件は未確認です。販売先で確認してください。"
        + (
            " " + escape(product["image_link_note"])
            if product.get("image_link_note")
            else ""
        )
        + "</figcaption></figure>"
    )
    return "".join(parts), bindings


def condition_summary(
    p: Mapping[str, Any],
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    now: datetime,
) -> str:
    """One line of decisive published values plus the next in-page action."""
    labels = (
        article.get("condition_fact_labels")
        or [label for label in article["spec_labels"] if label != "選ぶ理由"][:3]
    )
    facts = {f["label"]: f for f in p["facts"]}
    parts = [
        re.sub(r"（.*）$", "", label) + "：" + tidy(fact_text(facts[label]))
        for label in labels
        if label in facts
    ]
    action = internal_link("#" + p["anchor"], p["product_id"], "仕様と注意点を見る")
    return (
        '<p class="ps-condition-product"><a href="#'
        + str(p["anchor"])
        + '">'
        + escape(str(p["name"]))
        + '</a></p><p class="ps-condition-lead">'
        + escape(tidy(p["lead"]))
        + '</p><p class="ps-condition-facts">'
        + escape("／".join(parts))
        + '</p><p class="ps-condition-fit"><strong>向く条件：</strong>'
        + escape(" ".join(tidy(x) for x in p["fit"]))
        + '</p><p class="ps-condition-avoid"><strong>注意点：</strong>'
        + escape(" ".join(tidy(x) for x in p["avoid"]))
        + '</p><p class="ps-condition-caution">'
        + escape(tidy(p["caution"]))
        + (
            '<a href="#ps-installation-context">設置条件の詳細へ</a>'
            if article["slug"] == MAIN_SLUG
            else ""
        )
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


def contain_editorial_tables(html: str) -> str:
    """Give authored comparison tables a keyboard-focusable, local scroll region."""
    root = fragment(html)
    for table in root.find(tag="table"):
        ancestor = table.parent
        contained = False
        while ancestor:
            if any(
                ancestor.has(name)
                for name in ("ps-table-scroll", "comparison-table-wrap", "table-scroll")
            ):
                contained = True
                break
            ancestor = ancestor.parent
        if not contained:
            captions = table.find(tag="caption")
            region = Element(
                "div",
                {
                    "class": "ps-table-scroll",
                    "tabindex": "0",
                    "role": "region",
                    "aria-label": captions[0].text() if captions else "比較表",
                },
            )
            table.insert_before(region)
            region.append(table)
    return root.html()


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
        + '<a href="#ps-offers">購入費用と販売先</a><a href="#ps-evidence">詳細・出典</a></nav>'
    )
    if article.get("capacity_routes"):
        out.append(capacity_routes_markup(article["capacity_routes"]))
    decision_steps_html = ""
    decision_steps_placement = None
    if article.get("decision_steps"):
        steps = article["decision_steps"]
        # No implicit default: the declared position is the rendered position.
        if "placement" not in steps:
            raise ValueError("PURCHASE_DECISION_STEPS_PLACEMENT_REQUIRED")
        decision_steps_placement = steps["placement"]
        if decision_steps_placement not in DECISION_STEPS_PLACEMENTS:
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
        '<section id="ps-choose"><h2>条件別の結論</h2>'
        + (
            '<p class="ps-note">' + escape(tidy(article["choose_note"])) + "</p>"
            if article.get("choose_note")
            else ""
        )
        + '<div class="ps-condition-grid">'
    )
    for c in article["conditions"]:
        chosen = [
            next(p for p in products if p["product_id"] == pid)
            for pid in c["product_ids"]
        ]
        out.append("<div><h3>" + escape(c["label"]) + "</h3>")
        for p in chosen:
            out.append('<div class="ps-condition-item">')
            out.append(condition_media_slot(p["product_id"], c["id"]))
            out.append('<div class="ps-condition-copy">')
            out.append(condition_summary(p, article, catalog, now))
            out.append(condition_purchase_slot(p["product_id"], c["id"]))
            out.append("</div></div>")
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
    method_parts = []
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
        method_parts.append(re.sub(r"(?m)^[ \t]+$", "", methods[0].html()))
    if article.get("comparison_scope"):
        scope = article["comparison_scope"]
        method_parts.append(
            '<section><h2 id="'
            + escape(scope["heading_id"], quote=True)
            + '">比較のしかた</h2><p>'
            + escape(scope["intro"])
            + "</p><h3>比較対象にした条件</h3><ul>"
            + "".join("<li>" + escape(item) + "</li>" for item in scope["included"])
            + "</ul><h3>比較に含めていないもの</h3><ul>"
            + "".join("<li>" + escape(item) + "</li>" for item in scope["excluded"])
            + "</ul><p>市場全体の順位ではありません。性能評価に価格・在庫・ポイント・広告報酬を加点せず、購入費用は別に確認します。</p></section>"
        )
    out.append('<section id="ps-specs"><h2>決め手になる比較表</h2>')
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
                "販売状態と確認条件を見る",
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
    if decision_steps_placement == "after_specs":
        out.append(decision_steps_html)
    for heading_id in article.get("preserved_editorial_sections", []):
        matches = [
            section
            for section in fragment(template).find(tag="section")
            if section.attrs.get("id") == heading_id
            or any(n.attrs.get("id") == heading_id for n in section.find(tag="h2"))
        ]
        if len(matches) != 1:
            raise ValueError("PURCHASE_EDITORIAL_SECTION_REQUIRED")
        out.append(matches[0].html())
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
            if media_allowed(p, catalog) and p["product_id"] not in article.get(
                "media_exclusions", {}
            ):
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
                reason = article.get("media_exclusions", {}).get(
                    p["product_id"]
                ) or p.get("image_review", {}).get("reason")
                out.append(
                    '<p class="ps-media-withheld">商品写真：'
                    + escape(tidy(reason))
                    + "</p>"
                    if reason
                    else MEDIA_WITHHELD
                )
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
            + internal_link(
                "#ps-seller-" + p["anchor"], p["product_id"], "購入費用と販売先へ"
            )
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
    supplementary = [
        p
        for p in catalog["products"]
        if p["product_id"] in article.get("supplementary_product_ids", [])
    ]
    if supplementary:
        out.append(
            '<section class="ps-supplementary" id="ps-other-configurations"><h2>主比較とは別の構成</h2><p>以下は主比較の仕様・付属品・自動化範囲とは区別して確認してください。</p>'
        )
        for p in supplementary:
            out.append(
                '<article id="'
                + escape(p["anchor"], quote=True)
                + '"><h3>'
                + escape(p["name"])
                + "</h3><p>"
                + escape(p["exact_model"])
                + "</p><p>"
                + escape(tidy(p["lead"]))
                + "</p><p>"
                + escape(tidy(p["caution"]))
                + '</p><p><a href="'
                + escape(p["official_url"], quote=True)
                + '">この構成の公式仕様を確認する</a></p>'
            )
            panel, extra_bindings = offer_panel(
                p, catalog, article, snapshot, "final_summary", now=now
            )
            bindings.extend(extra_bindings)
            out.append(
                '<section class="ps-product-offers" id="ps-seller-'
                + escape(p["anchor"], quote=True)
                + '" data-ps-product="'
                + escape(p["product_id"], quote=True)
                + '"><h4>この別構成の販売条件</h4>'
                + panel
                + "</section></article>"
            )
        out.append("</section>")
    if main:
        out.append(installation_context(article, products))
    shared = common_alternatives(products, catalog)
    out.append(
        '<section id="ps-offers"><h2>購入費用と販売先</h2><p>構成・送料・必須品・納期・保証を販売先ごとに確認します。異なる構成の価格を同じ商品価格として比べません。確認日から24時間、または販売先の期限までを価格の表示期限とし、期限後は価格を表示せず、「販売条件の表示期限切れ」または「価格は販売先で確認」と示します。</p>'
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
    if method_parts:
        out.append(
            '<details class="ps-comparison-method"><summary>比較範囲・条件と選び方の詳細</summary>'
            + "".join(method_parts)
            + "</details>"
        )
    out.append(
        '<section id="ps-evidence"><h2>必要な詳細と出典</h2><p>性能の評価に価格や広告報酬を加点しません。購入費用は用途・予算に合う候補を選ぶために別に比較します。掲載候補は市場全体の順位ではありません。</p><details><summary>仕様の確認元・適用条件</summary>'
    )
    for p in products + supplementary:
        seen = set()
        out.append("<h3>" + escape(p["name"]) + "</h3><ul>")
        for f in p["facts"]:
            key = (f["source_url"], f["locator"], f["checked_at"])
            if key in seen:
                continue
            seen.add(key)
            source_id, _ = fact_reference(p, f)
            out.append(
                '<li id="'
                + escape(source_id, quote=True)
                + '"><a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(locator_label(f["locator"]))
                + "</a> ／ 仕様確認 "
                + escape(jp_date(f["checked_at"]))
                + conflict_source_links(f)
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
    if not any(b.get("affiliate") == "true" for b in bindings):
        out[1] = (
            '<p class="ps-disclosure">この記事にアフィリエイトリンクはありません。実機で使用した評価ではなく、型番ごとの公式情報に基づく比較です。</p>'
        )
    html = contain_editorial_tables("".join(out))
    if article.get("commerce_presentation") == "comparison_rows":
        return integrate_product_rows(
            html, article, catalog, snapshot, product_media, now, bindings
        )
    return html, bindings


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
            conflicts = installation_conflicts(p)

            def mm(key: str) -> str:
                if money(v.get(key)):
                    return f"{v[key]:g}mm"
                if key in conflicts:
                    return "公式資料で値が異なる（" + conflict_values(conflicts[key]) + "）"
                return "未確認"

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
    region_label = "4機種の" + label + "の比較"
    caption = (
        "4機種の"
        + label
        + "を決めるための表。値は下の機種別欄の出典から転記した公表条件で、同じ条件での実測比較ではありません。"
    )
    if stage == "installation":
        # Fit-check inputs such as 490−435＝55mm are calculated from published conditions.
        caption = (
            "4機種の"
            + label
            + "を決めるための表。値は下の機種別欄の出典にある公表条件・公表寸法と、その条件から計算した照合用の値（根拠は機種別欄）で、同じ条件での実測比較ではありません。"
        )
    elif stage == "detergent":
        region_label = "4機種の公表試験条件の洗剤量"
        caption = "4機種の公表試験条件の洗剤量。使用量の指示ではなく、公表値の試験で使った洗剤量です。値は下の機種別欄の出典から転記した公表条件です。"
    return (
        '<div class="ps-table-scroll" tabindex="0" role="region" aria-label="'
        + escape(region_label, quote=True)
        + '"><table class="ps-comparison ps-guide-table"><caption>'
        + escape(caption)
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
                groups.setdefault((f["field"], tidy(fact_text(f))), []).append((p, f))
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
                + conflict_source_links(f)
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
    from raos.application.editorial.site_guide_improvements import (
        render_guide_intro,
        render_model_handout,
    )

    out.append(render_guide_intro(stage, products))
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
        out.append(render_model_handout(stage, p))
        selected = [
            f
            for field in GUIDE_REQUIREMENTS[stage]
            for f in p.get("guide_facts", [])
            if f["field"] == field
        ]
        shared_here = False
        for f in selected:
            if (f["field"], tidy(fact_text(f))) in shared_keys:
                shared_here = True
                continue
            out.append(
                "<p>"
                + escape(tidy(fact_text(f)))
                + '</p><p class="ps-source"><a href="'
                + escape(f["source_url"], quote=True)
                + '">'
                + escape(locator_label(f["locator"]))
                + "</a> ／ 仕様確認 "
                + escape(jp_date(f["checked_at"]))
                + conflict_source_links(f)
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
            installation_attrs = {
                "data-ps-installation": json.dumps(
                    p.get("installation", {}),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            }
            # Unset references withheld because official sources differ; the fit
            # check names them as conflicts rather than as missing site data.
            conflict_keys = [
                key for key in INSTALLATION_LABELS if key in installation_conflicts(p)
            ]
            if conflict_keys:
                installation_attrs["data-ps-installation-conflicts"] = json.dumps(
                    conflict_keys, separators=(",", ":")
                )
            out.append(
                '<div class="ps-installation"'
                + attrs(installation_attrs)
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
            route_links(
                p,
                current_slug=article["slug"],
                heading="h3" if model_heading == "h2" else "h4",
            )
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
    rendered = "".join(out)
    if stage == "water" and fragment(template).find(cls="sm-page"):
        return bind_water_guide_layout(template, rendered, article, catalog=catalog)
    return rendered


def bind_water_guide_layout(
    template: str,
    rendered: str,
    article: Mapping[str, Any],
    *,
    catalog: Mapping[str, Any] | None = None,
) -> str:
    """Keep the authored route diagram while sourcing model details from the catalog."""
    authored, canonical = fragment(template), fragment(rendered)
    roots = authored.find(cls="sm-page")
    if len(roots) != 1:
        raise ValueError("PURCHASE_WATER_LAYOUT_INVALID")
    root = roots[0]
    ids = [node.attrs["id"] for node in root.walk() if node.attrs.get("id")]
    if len(ids) != len(set(ids)):
        raise ValueError("PURCHASE_WATER_LAYOUT_INVALID")
    table_layout = article.get("commerce_presentation") == "comparison_rows"
    if table_layout:
        if catalog is None:
            raise ValueError("PURCHASE_WATER_MODEL_SLOT_INVALID")
        bind_water_table_facts(root, canonical, article, catalog)
    else:
        first_model = next(iter(root.find(cls="ps-guide-model")), None)
        model_indexes = canonical.find(cls="ps-model-index")
        if first_model is None or len(model_indexes) != 1:
            raise ValueError("PURCHASE_WATER_MODEL_SLOT_INVALID")
        first_model.insert_before(model_indexes[0])

    def replace(original: Element, replacement: Element) -> None:
        original.insert_before(replacement)
        original.remove()

    for model in [] if table_layout else canonical.find(cls="ps-guide-model"):
        targets = [
            node
            for node in root.find(cls="ps-guide-model")
            if node.attrs.get("id") == model.attrs.get("id")
        ]
        if len(targets) != 1:
            raise ValueError("PURCHASE_WATER_MODEL_SLOT_INVALID")
        details = Element("details", {"class": "sm-model-detail"})
        details.append(Element("summary", children=["給水・排水の条件を見る"]))
        # The heading and exact model remain visible; all verified instructions
        # and their source links stay together inside the disclosure.
        for child in list(model.children)[2:]:
            details.append(child)
        model.append(details)
        replace(targets[0], model)
    for identity in ("reader-unknowns", "guide-previous-models"):
        old = [node for node in root.walk() if node.attrs.get("id") == identity]
        new = [node for node in canonical.walk() if node.attrs.get("id") == identity]
        if len(old) != 1 or len(new) != 1:
            raise ValueError("PURCHASE_WATER_LAYOUT_INVALID")
        replace(old[0], new[0])
    for cls in ("ps-history", "ps-editor"):
        old, new = root.find(cls=cls), canonical.find(cls=cls)
        if len(old) != 1 or len(new) != 1:
            raise ValueError("PURCHASE_WATER_LAYOUT_INVALID")
        replace(old[0], new[0])
    # Reinstall aliases at their canonical targets in add_compatibility_anchors.
    # The source retains them so old incoming URLs remain part of the contract.
    for node in list(root.walk()):
        if node.attrs.get("id") in article.get("legacy_anchor_targets", {}):
            node.remove()
    return root.html()


def bind_water_table_facts(
    root: Element,
    canonical: Element,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
) -> None:
    """Keep the main guide scope and refresh detailed instructions inside its rows."""
    products = {p["product_id"]: p for p in catalog["products"]}
    main = article.get("product_ids", [])
    extras = article.get("supplementary_product_ids", [])
    scope = main + extras
    rows = [r for r in root.find(tag="tr") if r.attrs.get("data-product-id")]
    if (
        not scope
        or len(main) > 4
        or len(extras) > 1
        or len(scope) != len(set(scope))
        or not set(scope) <= products.keys()
        or [products[pid]["anchor"] for pid in main]
        != [m.attrs.get("id") for m in canonical.find(cls="ps-guide-model")]
        or [r.attrs["data-product-id"] for r in rows] != scope
        or any(
            (r.attrs.get("data-ps-supplementary") == "true") != (pid in extras)
            for r, pid in zip(rows, scope, strict=True)
        )
    ):
        raise ValueError("PURCHASE_WATER_TABLE_SCOPE_INVALID")
    for row, pid in zip(rows, scope, strict=True):
        product = products[pid]
        if pid in extras:
            # Supplemental example instructions remain ordinary authored source.
            continue
        slots = row.find(tag="details", cls="ps-guide-facts")
        if row.attrs.get("id") != product["anchor"] or len(slots) != 1:
            raise ValueError("PURCHASE_WATER_MODEL_SLOT_INVALID")
        facts = [
            f
            for f in product.get("guide_facts", [])
            if f["field"] in {"water_supply", "drainage"}
        ]
        # An instruction withdrawn from the catalog must also disappear from
        # the authored quick comparison, rather than leaving an old value visible.
        for group in row.walk():
            field = group.attrs.get("data-ps-guide-field")
            if field not in {"water_supply", "drainage"}:
                continue
            selected = [f for f in facts if f["field"] == field]
            unknown = [f for f in selected if f.get("state") in UNSETTLED_FACT_STATES]
            if selected and not unknown:
                continue
            values = group.find(tag="dd")
            if len(values) != 1:
                raise ValueError("PURCHASE_WATER_MODEL_SLOT_INVALID")
            values[0].children = [
                escape(" ".join(tidy(fact_text(f)) for f in unknown))
                if unknown
                else "この型番の条件は未確認です。"
            ]
        details = slots[0]
        details.children.clear()
        details.append(Element("summary", children=["給排水の手順・出典"]))
        if not facts:
            details.append(
                block(
                    '<p>この型番の給排水条件は未確認です。<a href="'
                    + escape(product["official_url"], quote=True)
                    + '">公式資料を確認する</a></p>'
                )
            )
        for fact in facts:
            details.append(block("<p>" + escape(tidy(fact_text(fact))) + "</p>"))
            details.append(
                block(
                    '<p class="ps-source"><a href="'
                    + escape(fact["source_url"], quote=True)
                    + '">'
                    + escape(locator_label(fact["locator"]))
                    + "</a> ／ 仕様確認 "
                    + escape(jp_date(fact["checked_at"]))
                    + conflict_source_links(fact)
                    + "</p>"
                )
            )


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
        if identity in (anchor_targets or {}):
            if (anchor_targets or {})[identity] != sections[product].attrs.get("id"):
                raise ValueError("PURCHASE_ANCHOR_PRODUCT_MISMATCH")
            continue  # The explicit, identity-checked alias is installed below.
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
        if len(targets) != 1 or targets[0].tag not in {
            "section",
            "article",
            "li",
            "aside",
            "tr",
            "span",
        }:
            raise ValueError("PURCHASE_LEGACY_ALIAS_TARGET_INVALID")
        section = targets[0]
        if section.tag == "tr":
            cells = section.find(tag="th")
            if not cells or cells[0].attrs.get("scope") != "row":
                raise ValueError("PURCHASE_LEGACY_ALIAS_TARGET_INVALID")
            section = cells[0]
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


def hub_sales_record(
    product: Mapping[str, Any], catalog: Mapping[str, Any], now: datetime
) -> str:
    """Historical seller observations only: never a current market availability claim."""
    offers = verified_offers(product, catalog)
    records = []
    labels = {
        "AVAILABLE": "注文可の表示",
        "SOLD_OUT": "売り切れの表示",
        "UNAVAILABLE": "販売条件未確認",
    }
    for offer in offers:
        checked = timestamp(offer.get("checked_at"))
        if (
            checked is None
            or checked > now
            or not offer.get("seller_id")
            or not offer.get("seller")
        ):
            continue
        state = labels.get(str(offer.get("state")), "販売条件未確認")
        deadline = timestamp(offer.get("valid_until"))
        validity = (
            "記録の確認期限は未確認。"
            if deadline is None or deadline <= checked
            else "記録の確認期限切れ。"
            if now >= deadline
            else ""
        )
        deadline_label = (
            jp_datetime(deadline) + " JST"
            if deadline and deadline > checked
            else "未確認"
        )
        records.append(
            escape(offer["seller"])
            + "：確認時は"
            + state
            + "（確認日時："
            + escape(jp_datetime(checked))
            + " JST）。"
            + validity
            + "現在の状況は未確認のため販売先で再確認。記録の有効期限："
            + escape(deadline_label)
            + "。"
        )
    return (
        "<p>"
        + (
            " ／ ".join(records)
            if records
            else "型番と販売先の対応・販売状態・確認日時は未確認。"
        )
        + "市場全体の在庫や終売を示すものではありません。</p>"
    )


def render_hub(
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    template: str,
    *,
    now: datetime | None = None,
) -> str:
    """Validate the source-authored category gateway and preserve its useful routes."""
    hub_template = fragment(template)
    roots = [n for n in hub_template.children if isinstance(n, Element) and n.tag]
    if len(roots) != 1 or not roots[0].has("ks-directory"):
        raise ValueError("PURCHASE_HUB_ROOT_INVALID")
    root = roots[0]
    hub_sections = {node.attrs.get("id"): node for node in root.find(tag="section")}
    for identity in (
        "kitchen-start",
        "kitchen-axes",
        "choose",
        "compare",
        "purchase-checks",
    ):
        if identity not in hub_sections:
            raise ValueError("PURCHASE_HUB_SECTION_MISSING")
    navs = {node.attrs.get("aria-label"): node for node in root.find(tag="nav")}
    for label in (
        "このサイトの入口",
        "このページの読み方",
        "編集方針",
    ):
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
    return root.html()


def render_curated_commerce(
    template: str,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    """Bind one authored commerce section to the common product and offer records."""
    root = fragment(template)
    if article.get("row_products") is not None:
        containers = [node for node in root.children if isinstance(node, Element)]
        if len(containers) != 1:
            raise ValueError("PURCHASE_CURATED_ROOT_REQUIRED")
        container = containers[0]
        container.attrs.update(
            {
                "data-raos-article-id": article["article_id"],
                "data-raos-snapshot-id": snapshot,
            }
        )
        if not container.has("ps-article"):
            container.attrs["class"] = (
                container.attrs.get("class") or ""
            ) + " ps-article"
        notices = [
            node
            for node in container.find(tag="p")
            if node.has("ps-disclosure")
            or node.text().startswith("広告")
            or node.has("std-disclosure")
            or node.has("sc-disclosure")
            or node.has("lg-disclosure")
        ]
        if not notices:
            notice = block('<p class="ps-disclosure">公式資料による比較です。</p>')
            container.children.insert(0, notice)
            notice.parent = container
            notices = [notice]
        if len(notices) != 1:
            raise ValueError("PURCHASE_CURATED_DISCLOSURE_REQUIRED")
        if not notices[0].has("ps-disclosure"):
            notices[0].attrs["class"] = (
                notices[0].attrs.get("class") or ""
            ) + " ps-disclosure"
    if article["kind"] == "curated_comparison":
        # One correction contact (and dated history, when recorded) closes the
        # single article root, as on the generated comparisons and guides.
        article_roots = [
            node
            for node in root.children
            if isinstance(node, Element) and node.has("ps-article")
        ]
        if len(article_roots) != 1:
            raise ValueError("PURCHASE_CURATED_ROOT_REQUIRED")
        for node in list(fragment(history_block(article)).children):
            if isinstance(node, Element):
                article_roots[0].append(node)
    targets = [
        n
        for n in root.find(tag="section")
        if n.attrs.get("id") == article["commerce_anchor"]
    ]
    if len(targets) != 1:
        raise ValueError("PURCHASE_CURATED_ANCHOR_REQUIRED")
    target = targets[0]
    if article.get("commerce_presentation") == "comparison_rows":
        return bind_comparison_rows(
            root, target, article, catalog, snapshot, product_media, now
        )
    target.children.clear()
    target.append(block("<h2>商品画像と販売先</h2>"))
    cards = Element("div", {"class": "ps-product-grid"})
    target.append(cards)
    bindings: list[dict[str, str]] = []
    media: dict[str, str] = {}
    for pid in article["product_ids"]:
        product = next(p for p in catalog["products"] if p["product_id"] == pid)
        card = Element(
            "section",
            {"class": "ps-product", "id": product["anchor"], "data-ps-product": pid},
        )
        card.append(block("<h3>" + escape(product["name"]) + "</h3>"))
        if product_media is not None and media_allowed(product, catalog):
            markup, links = render_product_media(
                product, article, snapshot, product_media[pid]
            )
            card.append(
                Element(
                    "div", {"class": "ps-product-media", "data-ps-media-product": pid}
                )
            )
            media[pid] = markup
            bindings.extend(links)
        if article.get("commerce_presentation") == "images_and_links":
            matching = [
                o
                for o in product_offers(product, catalog)
                if o.get("merchant_url")
                == product.get("image_review", {}).get("listing_url")
            ]
            if len(matching) != 1 or not media_allowed(product, catalog):
                raise ValueError("PURCHASE_CURATED_LISTING_REQUIRED")
            link, binding = cta(
                matching[0], article, snapshot, "product_card", listing_reference=True
            )
            card.append(block("<p>" + link + "</p>"))
            bindings.append(binding)
        else:
            seller, links = offer_panel(
                product, catalog, article, snapshot, "product_card", now=now
            )
            bindings.extend(links)
            card.append(
                block(
                    "<details><summary>販売状況と条件</summary>" + seller + "</details>"
                )
            )
        card.append(
            block(
                '<p><a href="'
                + escape(product["official_url"], quote=True)
                + '" data-raos-link-purpose="official_verify">公式の仕様を見る</a></p>'
            )
        )
        cards.append(card)
    return contain_editorial_tables(root.html()), bindings, media


def row_commerce(
    product: Mapping[str, Any],
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[str, str, list[dict[str, str]], dict[str, str]]:
    """One product's image and seller, independent of table shape or stock state.

    Selection follows an explicit offer id, the reviewed image listing, then the
    catalog's editorial order. Neither commission nor the amount orders offers.
    A missing photo does not remove an independently verified seller link.
    """
    pid = product["product_id"]
    media: dict[str, str] = {}
    bindings: list[dict[str, str]] = []
    photo = ""
    if (
        product_media is not None
        and media_allowed(product, catalog)
        and pid not in article.get("media_exclusions", {})
    ):
        media[pid], links = render_product_media(
            product, article, snapshot, product_media[pid]
        )
        bindings.extend(links)
        photo = (
            '<div class="ps-product-media" data-ps-media-product="'
            + escape(pid, quote=True)
            + '"></div>'
        )
    offers = product_offers(product, catalog)
    explicit = product.get("display_offer_id")
    if explicit:
        offers = [offer for offer in offers if offer["offer_id"] == explicit]
        if len(offers) != 1:
            raise ValueError("PURCHASE_ROW_DISPLAY_OFFER_INVALID")
    else:
        listing = product.get("image_review", {}).get("listing_url")
        offers = sorted(offers, key=lambda offer: offer.get("merchant_url") != listing)
    seller = ""
    for offer in offers:
        if offer.get("product_model") != product["exact_model"]:
            raise ValueError("PURCHASE_ROW_OFFER_MODEL_MISMATCH")
        if (
            offer.get("identity_verified") is not True
            or offer.get("condition") not in {"new", "UNKNOWN"}
            or offer.get("state")
            not in {"AVAILABLE", "PREORDER", "SOLD_OUT", "UNKNOWN"}
            or not offer.get("variant")
        ):
            continue
        link, binding = cta(
            offer, article, snapshot, "comparison_table", listing_reference=True
        )
        seller = reference_price_markup(product, offer, now)
        seller += "<p>" + link + "</p>"
        if article.get("row_products") is not None:
            seller += (
                '<details class="ps-row-variant"><summary>色・構成を確認</summary><p>'
                + escape(tidy(offer["variant"]))
                + "</p></details>"
            )
        bindings.append(binding)
        break
    if not seller:
        seller = (
            '<p class="ps-reference-price" role="status">価格は確認中</p><p><a href="'
            + escape(product["official_url"], quote=True)
            + '" data-raos-link-purpose="official_verify">公式の商品情報を見る</a></p>'
        )
    return photo, seller, bindings, media


def row_fact_cell(product: Mapping[str, Any], labels: list[str]) -> str:
    parts = []
    for label in labels:
        facts = [fact for fact in product["facts"] if fact["label"] == label]
        if len(facts) > 1:
            raise ValueError("PURCHASE_ROW_FACT_DUPLICATE")
        fact = facts[0] if facts else None
        source = ""
        if fact:
            source_id, number = fact_reference(product, fact)
            source = (
                '<sup class="ps-reference"><a href="#'
                + escape(source_id, quote=True)
                + '" aria-label="'
                + escape(product["name"] + "：" + label + "の出典", quote=True)
                + '">['
                + str(number)
                + "]</a></sup>"
            )
        parts.append(
            '<div class="ps-row-fact" data-ps-fact-state="'
            + escape(fact["state"] if fact else "UNKNOWN", quote=True)
            + '"><span class="ps-row-fact-label">'
            + escape(label)
            + "</span>"
            + escape(tidy(fact_text(fact) if fact else "未確認（追加調査中）"))
            + source
            + "</div>"
        )
    return "".join(parts)


def comparison_row_columns(article: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Category axes are data references; future articles use rows by default."""
    columns = article.get("comparison_row_columns")
    if columns is None:
        columns = [{"heading": "仕様", "fact_labels": article["spec_labels"]}]
    if (
        not isinstance(columns, list)
        or not 1 <= len(columns) <= 4
        or any(
            not isinstance(column, dict)
            or not isinstance(column.get("heading"), str)
            or not column["heading"].strip()
            or not isinstance(column.get("fact_labels"), list)
            or not column["fact_labels"]
            or any(
                not isinstance(label, str) or not label
                for label in column["fact_labels"]
            )
            for column in columns
        )
    ):
        raise ValueError("PURCHASE_ROW_COLUMNS_INVALID")
    labels = [label for column in columns for label in column["fact_labels"]]
    if len(labels) != len(set(labels)) or not set(article["spec_labels"]) <= set(
        labels
    ):
        raise ValueError("PURCHASE_ROW_FACT_COVERAGE_INVALID")
    return columns


def integrate_product_rows(
    html: str,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
    bindings: list[dict[str, str]],
) -> tuple[str, list[dict[str, str]]]:
    """Project the same facts and authored rationale into one shared row format.

    Existing editorial sections and source ids remain. Only the main comparison
    and its duplicate image/seller placements move; supplementary scope remains
    separate. All purchase amounts still use the clock-owned renderer.
    """
    root = fragment(html)
    table = root.find(cls="ps-comparison")
    if len(table) != 1 or table[0].parent is None:
        raise ValueError("PURCHASE_ROW_MAIN_TABLE_REQUIRED")
    scroll = table[0].parent
    scroll.attrs["class"] = "ps-table-scroll ps-row-scroll"
    for controls in root.find(cls="ps-pair-controls"):
        controls.remove()
    columns = comparison_row_columns(article)
    headings = "".join(
        '<th scope="col">' + escape(c["heading"]) + "</th>" for c in columns
    )
    markup = (
        '<table class="ps-row-comparison" data-ps-spec-columns="'
        + str(len(columns))
        + '"><caption>商品・仕様・参考価格を横に比較</caption><thead><tr>'
        + '<th scope="col">商品・写真</th>'
        + headings
        + '<th scope="col">参考価格・販売先</th></tr></thead><tbody></tbody></table>'
    )
    replacement = block(markup)
    table[0].insert_before(replacement)
    table[0].remove()
    tbody = replacement.find(tag="tbody")[0]
    by_id = {p["product_id"]: p for p in catalog["products"]}
    new_bindings: list[dict[str, str]] = []
    for pid in article["product_ids"]:
        product = by_id[pid]
        cards = [
            node
            for node in root.find(cls="ps-product")
            if node.attrs.get("id") == product["anchor"]
        ]
        panels = [
            node
            for node in root.find(cls="ps-product-offers")
            if node.attrs.get("id") == "ps-seller-" + product["anchor"]
        ]
        if len(cards) != 1 or len(panels) != 1:
            raise ValueError("PURCHASE_ROW_EXISTING_ANCHORS_REQUIRED")
        card, panel = cards[0], panels[0]
        card.attrs["id"] = "ps-reason-" + product["anchor"]
        for duplicate in (
            card.find(cls="ps-product-media")
            + card.find(cls="ps-media-withheld")
            + card.find(cls="ps-offer-link")
            + panel.find(cls="ps-offer-link")
        ):
            duplicate.remove()
        reasons = Element("details", {"class": "ps-row-reasons"})
        reasons.append(
            block(
                "<summary>" + escape(product["name"]) + "が向く条件・注意点</summary>"
            )
        )
        card.insert_before(reasons)
        reasons.append(card)
        photo, seller, links, _ = row_commerce(
            product, article, catalog, snapshot, product_media, now
        )
        new_bindings.extend(links)
        row = block(
            '<tr id="'
            + escape(product["anchor"], quote=True)
            + '" data-product-id="'
            + escape(pid, quote=True)
            + '">'
            + '<th scope="row" class="ps-row-identity"><strong>'
            + escape(product["name"])
            + '</strong><small class="ps-row-model">'
            + escape(product.get("model_number") or product["exact_model"])
            + "</small>"
            + photo
            + ('<p class="ps-row-image-pending">画像は確認中</p>' if not photo else "")
            + "</th>"
            + "".join(
                "<td>" + row_fact_cell(product, column["fact_labels"]) + "</td>"
                for column in columns
            )
            + '<td class="ps-row-offer">'
            + seller
            + "</td></tr>"
        )
        condition_details = Element("details", {"class": "ps-row-conditions"})
        condition_details.append(block("<summary>送料・必要なもの・保証</summary>"))
        condition_details.append(panel)
        row.find(tag="td")[-1].append(condition_details)
        tbody.append(row)
    # A separately scoped configuration uses the same row commerce without
    # adding it to the main comparison count or discarding its old bookmarks.
    extras = article.get("supplementary_product_ids", [])
    if extras:
        supplementary = root.find(cls="ps-supplementary")[0]
        extra_table = block(
            '<div class="ps-table-scroll ps-row-scroll" tabindex="0" role="region"'
            ' aria-label="主比較とは別の構成"><table class="ps-row-comparison"'
            ' data-ps-spec-columns="1"><caption>主比較とは別の構成</caption>'
            '<thead><tr><th scope="col">商品・写真</th><th scope="col">構成と仕様</th>'
            '<th scope="col">参考価格・販売先</th></tr></thead><tbody></tbody></table></div>'
        )
        supplementary.append(extra_table)
        for pid in extras:
            product = by_id[pid]
            card = next(
                node
                for node in supplementary.find(tag="article")
                if node.attrs.get("id") == product["anchor"]
            )
            panel = card.find(cls="ps-product-offers")[0]
            for link in panel.find(cls="ps-offer-link"):
                link.remove()
            card.attrs["id"] = "ps-reason-" + product["anchor"]
            photo, seller, links, _ = row_commerce(
                product, article, catalog, snapshot, product_media, now
            )
            new_bindings.extend(links)
            row = block(
                '<tr id="'
                + escape(product["anchor"], quote=True)
                + '" data-product-id="'
                + escape(pid, quote=True)
                + '" data-ps-supplementary="true"><th scope="row"><strong>'
                + escape(product["name"])
                + '</strong><small class="ps-row-model">'
                + escape(product["exact_model"])
                + "</small>"
                + photo
                + "</th><td>"
                + row_fact_cell(product, [f["label"] for f in product["facts"]])
                + '</td><td class="ps-row-offer">'
                + seller
                + "</td></tr>"
            )
            reasons = block(
                '<details class="ps-row-reasons"><summary>この構成の注意点</summary></details>'
            )
            reasons.append(card)
            row.find(tag="td")[0].append(reasons)
            conditions = block(
                '<details class="ps-row-conditions"><summary>送料・必要なもの・保証</summary></details>'
            )
            conditions.append(panel)
            row.find(tag="td")[-1].append(conditions)
            extra_table.find(tag="tbody")[0].append(row)
    # Move the old offer section's bookmark to the table; explanatory text stays
    # collapsed with the conditions, rather than leaving an empty lower gallery.
    old_offers = [
        node for node in root.find(tag="section") if node.attrs.get("id") == "ps-offers"
    ]
    if len(old_offers) != 1:
        raise ValueError("PURCHASE_ROW_OFFERS_ANCHOR_REQUIRED")
    offer_notes = old_offers[0]
    offer_notes.attrs.pop("id")
    for heading in offer_notes.find(tag="h2"):
        heading.remove()
    # A stable landing point for navigation to the price and seller explanation.
    details = Element("details", {"class": "ps-row-price-notes", "id": "ps-price-notes"})
    details.append(block("<summary>参考価格と購入費用について</summary>"))
    details.append(offer_notes)
    offer_table = Element("section", {"id": "ps-offers"})
    scroll.insert_before(offer_table)
    offer_table.append(scroll)
    offer_table.append(details)
    remaining_ids = {node.attrs.get("data-raos-cta-id") for node in root.walk()}
    kept = [binding for binding in bindings if binding["cta_id"] in remaining_ids]
    # Media lives in the separately hash-bound projection, so its new bindings
    # are retained explicitly together with the generated row CTAs.
    kept.extend(new_bindings)
    disclosures = root.find(cls="ps-disclosure")
    if disclosures and any(binding.get("affiliate") == "true" for binding in kept):
        disclosures[0].children = [escape(DISCLOSURE)]
    return root.html(), kept


def bind_comparison_rows(
    root: Element,
    target: Element,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    """Keep authored specifications, bind each row to its own vetted commerce."""
    row_products = article.get("row_products")
    if row_products is not None:
        keyed = {entry["key"]: entry["product_id"] for entry in row_products}
        rows_by_key = [
            row for row in target.find(tag="tr") if row.attrs.get("data-product-key")
        ]
        if (
            len(keyed) != len(row_products)
            or [row.attrs["data-product-key"] for row in rows_by_key] != list(keyed)
            or list(keyed.values()) != article["product_ids"]
        ):
            raise ValueError("PURCHASE_COMPARISON_ROW_SCOPE_INVALID")
        for row in rows_by_key:
            key = str(row.attrs["data-product-key"])
            pid = keyed[key]
            if row.attrs.get("data-product-id", pid) != pid:
                raise ValueError("PURCHASE_COMPARISON_ROW_SCOPE_INVALID")
            row.attrs["data-product-id"] = pid
            for node in row.walk():
                classes = (node.attrs.get("class") or "").split()
                for suffix, common in (
                    ("-brand", "ps-row-brand"),
                    ("-product-model", "ps-row-model"),
                    ("-spec-label", "ps-row-spec-label"),
                    ("-dimensions", "ps-row-dimensions"),
                ):
                    if (
                        any(name.endswith(suffix) for name in classes)
                        and common not in classes
                    ):
                        classes.append(common)
                if classes:
                    node.attrs["class"] = " ".join(classes)
            for kind in ("media", "offer"):
                slots = row.find(cls="ps-row-" + kind)
                if len(slots) != 1 or slots[0].attrs.get("data-product-key") != key:
                    raise ValueError("PURCHASE_COMPARISON_ROW_SLOT_INVALID")
                slots[0].attrs["data-product-id"] = pid
                slots[0].attrs.pop("data-ps-media-product", None)
        for table in target.find(tag="table"):
            if not any(
                row.attrs.get("data-product-key") for row in table.find(tag="tr")
            ):
                continue
            heads = table.find(tag="thead")[0].find(tag="th")
            if not 3 <= len(heads) <= 6 or table.parent is None:
                raise ValueError("PURCHASE_ROW_COLUMNS_INVALID")
            table.attrs["class"] = "ps-row-comparison"
            for colgroup in table.find(tag="colgroup"):
                colgroup.remove()
            table.attrs["data-ps-spec-columns"] = str(len(heads) - 2)
            table.parent.attrs["class"] = "ps-table-scroll ps-row-scroll"
    rows = [r for r in target.find(tag="tr") if r.attrs.get("data-product-id")]
    if [r.attrs["data-product-id"] for r in rows] != article["product_ids"]:
        raise ValueError("PURCHASE_COMPARISON_ROW_SCOPE_INVALID")
    bindings: list[dict[str, str]] = []
    media: dict[str, str] = {}
    for row in rows:
        pid = str(row.attrs["data-product-id"])
        product = next(p for p in catalog["products"] if p["product_id"] == pid)
        photos = row.find(
            cls="ps-row-media" if row_products is not None else "compact-product-media"
        )
        sellers = row.find(
            cls="ps-row-offer" if row_products is not None else "compact-product-offer"
        )
        if (
            len(photos) != 1
            or len(sellers) != 1
            or any(
                node.attrs.get("data-product-id") != pid for node in photos + sellers
            )
        ):
            raise ValueError("PURCHASE_COMPARISON_ROW_SLOT_INVALID")
        photos[0].children.clear()
        sellers[0].children.clear()
        photo, seller, links, images = row_commerce(
            product, article, catalog, snapshot, product_media, now
        )
        if photo:
            photos[0].append(block(photo))
        for child in list(fragment(seller).children):
            sellers[0].append(child)
        bindings.extend(links)
        media.update(images)
    if row_products is not None:
        notice = root.find(cls="ps-disclosure")[0]
        notice.children = [
            "広告：この記事にはアフィリエイトリンクが含まれます。広告報酬で評価・掲載順を決めません。"
            if any(binding.get("affiliate") == "true" for binding in bindings)
            else "この記事にアフィリエイトリンクはありません。公式資料による比較で、実機試験ではありません。"
        ]
    return (
        contain_editorial_tables(root.html())
        if row_products is not None
        else root.html(),
        bindings,
        media,
    )


def bind_guide_purchase_slots(
    html: str,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[str, list[dict[str, str]], dict[str, str]]:
    """Attach reviewed purchase information to existing model sections only."""
    slots = article.get("purchase_slots", [])
    if not slots:
        return html, [], {}
    if article["kind"] != "guide" or len(slots) > 4:
        raise ValueError("PURCHASE_GUIDE_SLOT_SCOPE_INVALID")
    root = fragment(html)
    bindings: list[dict[str, str]] = []
    media: dict[str, str] = {}
    seen: set[str] = set()
    for slot in slots:
        pid = slot["product_id"]
        if pid in seen:
            raise ValueError("PURCHASE_GUIDE_SLOT_DUPLICATE")
        seen.add(pid)
        products = [p for p in catalog["products"] if p["product_id"] == pid]
        if len(products) != 1:
            raise ValueError("PURCHASE_GUIDE_SLOT_PRODUCT_INVALID")
        product = products[0]
        sections = [
            n
            for n in root.find(cls="ps-guide-model")
            if n.attrs.get("id") == product["anchor"]
        ]
        if len(sections) != 1:
            raise ValueError("PURCHASE_GUIDE_SLOT_MODEL_REQUIRED")
        section = sections[0]
        seller, links = offer_panel(
            product, catalog, article, snapshot, "product_card", now=now
        )
        bindings.extend(links)
        markup = (
            '<div class="ps-guide-purchase" data-ps-product="'
            + escape(pid, quote=True)
            + '">'
        )
        if (
            product_media is not None
            and media_allowed(product, catalog)
            and pid not in article.get("media_exclusions", {})
        ):
            media[pid], image_links = render_product_media(
                product, article, snapshot, product_media[pid]
            )
            bindings.extend(image_links)
            markup += (
                '<div class="ps-product-media" data-ps-media-product="'
                + escape(pid, quote=True)
                + '"></div>'
            )
        markup += (
            "<details><summary>販売先と購入条件</summary>" + seller + "</details></div>"
        )
        inserted = next(n for n in fragment(markup).children if isinstance(n, Element))
        if slot.get("position") == "before_routes":
            targets = section.find(cls="ps-model-routes-block")
            if len(targets) != 1:
                raise ValueError("PURCHASE_GUIDE_SLOT_ROUTE_REQUIRED")
            targets[0].insert_before(inserted)
        elif slot.get("position") == "after_identity":
            paragraphs = [
                n for n in section.children if isinstance(n, Element) and n.tag == "p"
            ]
            if not paragraphs:
                raise ValueError("PURCHASE_GUIDE_SLOT_IDENTITY_REQUIRED")
            index = section.children.index(paragraphs[0]) + 1
            inserted.parent = section
            section.children.insert(index, inserted)
        else:
            raise ValueError("PURCHASE_GUIDE_SLOT_POSITION_INVALID")
    return root.html(), bindings, media


def condition_media_slot(pid: str, key: str) -> str:
    return (
        '<div class="ps-condition-product-media" data-ps-media-product="'
        + escape(pid, quote=True)
        + '" data-ps-condition="'
        + escape(key, quote=True)
        + '"></div>'
    )


def condition_purchase_slot(pid: str, key: str) -> str:
    return (
        '<div class="ps-condition-product-purchase" data-ps-purchase-product="'
        + escape(pid, quote=True)
        + '" data-ps-condition="'
        + escape(key, quote=True)
        + '"></div>'
    )


def bind_condition_commerce(
    html: str,
    article: Mapping[str, Any],
    catalog: Mapping[str, Any],
    snapshot: str,
    product_media: Mapping[str, Any] | None,
    now: datetime,
) -> tuple[str, list[dict[str, str]], dict[str, Any]]:
    """Bind each authored conclusion occurrence to its own exact CTA context."""
    expected = article["condition_slots"]
    identities = [(entry["key"], entry["product_id"]) for entry in expected]
    if (
        article["kind"] not in {"comparison", "curated_comparison"}
        or not 1 <= len(identities) <= 32
        or len(set(identities)) != len(identities)
        or any(
            not re.fullmatch(r"[a-z0-9-]{1,32}", key)
            or pid not in article["product_ids"]
            for key, pid in identities
        )
    ):
        raise ValueError("PURCHASE_CONDITION_SCOPE_INVALID")
    root = fragment(html)
    photos = root.find(cls="ps-condition-product-media")
    purchases = root.find(cls="ps-condition-product-purchase")
    if (
        [
            (n.attrs.get("data-ps-condition"), n.attrs.get("data-ps-media-product"))
            for n in photos
        ]
        != identities
        or [
            (n.attrs.get("data-ps-condition"), n.attrs.get("data-ps-purchase-product"))
            for n in purchases
        ]
        != identities
        or any(n.children for n in photos + purchases)
    ):
        raise ValueError("PURCHASE_CONDITION_SLOT_INVALID")
    bindings: list[dict[str, str]] = []
    media: dict[str, Any] = {}
    for (key, pid), photo, purchase in zip(identities, photos, purchases, strict=True):
        product = next(p for p in catalog["products"] if p["product_id"] == pid)
        if (
            product_media is not None
            and media_allowed(product, catalog)
            and pid not in article.get("media_exclusions", {})
        ):
            markup, links = render_product_media(
                product,
                article,
                snapshot,
                product_media[pid],
                context="top_summary",
                context_id=key,
            )
            media[key + "--" + pid] = {
                "product_id": pid,
                "condition_id": key,
                "html": markup,
            }
            bindings.extend(links)
        else:
            photo.remove()
        _, _, row_bindings, _ = row_commerce(
            product, article, catalog, snapshot, None, now
        )
        offer_binding = next(
            (b for b in row_bindings if b["placement"] == "comparison_table"), None
        )
        if offer_binding is not None:
            offer = next(
                o
                for o in catalog["offers"]
                if o["offer_id"] == offer_binding["offer_id"]
            )
            link, binding = cta(
                offer,
                article,
                snapshot,
                "top_summary",
                listing_reference=True,
                context_id=key,
            )
            purchase.append(block(link))
            bindings.append(binding)
        else:
            purchase.append(
                block(
                    '<a href="'
                    + escape(product["official_url"], quote=True)
                    + '" data-raos-link-purpose="official_verify">公式の商品情報を見る</a>'
                )
            )
    return root.html(), bindings, media


def consolidate_comparison_details(html: str) -> str:
    """Keep editorial constraints and references, remove repeated presentation."""
    root = fragment(html)
    choices = next(
        n for n in root.find(tag="section") if n.attrs.get("id") == "ps-choose"
    )
    old = [n for n in root.find(tag="section") if n.attrs.get("id") == "ps-products"]
    for section in old:
        # Public bookmarks remain reachable where the reasons now live.
        for n in section.walk():
            if n.attrs.get("id"):
                choices.append(Element("span", {"id": n.attrs["id"], "tabindex": "-1"}))
        # Model guide routes carry useful navigation independent of repeated prose.
        for routes in list(section.find(cls="ps-model-routes-block")):
            choices.append(routes)
        section.remove()
    for link in root.find(tag="a"):
        if link.attrs.get("href") == "#ps-products":
            link.attrs["href"] = "#ps-choose"
    for method in root.find(cls="ps-comparison-method"):
        # Unique selection constraints stay visible; only the enclosing duplicate
        # accordion and its repeated heading disappear.
        for summary in method.find(tag="summary"):
            summary.remove()
        method.tag = "div"
        method.attrs["class"] = "ps-comparison-constraints"
    evidence = next(
        n for n in root.find(tag="section") if n.attrs.get("id") == "ps-evidence"
    )
    evidence.find(tag="h2")[0].children = ["出典・確認した一次情報"]
    for detail in evidence.find(tag="details"):
        summaries = detail.find(tag="summary")
        if summaries and "仕様の確認元" in summaries[0].text():
            summaries[0].remove()
            detail.tag = "div"
    extra = Element("ul", {"class": "ps-additional-sources"})
    # The generated fact sources retain their per-product reference ids. The
    # older source section contributes any URL not present there, once.
    for section in list(evidence.find(tag="section")):
        if section is evidence:
            continue
        headings = section.find(tag="h2")
        if not (
            section.has("sources-section")
            or any(re.search("一次情報|確認した公式", h.text()) for h in headings)
        ):
            continue
        inside = {id(n) for n in section.walk()}
        outside = {
            n.attrs.get("href")
            for n in evidence.walk()
            if id(n) not in inside and n.tag == "a"
        }
        for n in section.walk():
            if n.attrs.get("id"):
                evidence.append(
                    Element("span", {"id": n.attrs["id"], "tabindex": "-1"})
                )
        for link in section.find(tag="a"):
            url = link.attrs.get("href") or ""
            if url.startswith("https://") and url not in outside:
                li = Element("li", {})
                li.append(block(link.html()))
                extra.append(li)
                outside.add(url)
        section.remove()
    if extra.children:
        evidence.append(extra)
    return root.html()


def matrix_comparison_markup(html: str) -> str:
    """Keep each product row and combine its middle specification cells only.

    Opt-in group labels: when a table with more than three columns has a middle
    header carrying data-ps-matrix-label, each row's group for that column starts
    with span.ps-row-fact-label holding the attribute text, unless the cell
    already contains a .ps-row-fact-label. Without the attribute nothing is added.
    """
    root = fragment(html)
    for table in root.find(tag="table"):
        if not (
            table.has("ps-row-comparison") or table.has("compact-integrated-table")
        ):
            continue
        heads = table.find(tag="thead")
        if len(heads) != 1 or table.parent is None:
            raise ValueError("PURCHASE_ROW_HEADERS_REQUIRED")
        header_rows = heads[0].find(tag="tr")
        headers = heads[0].find(tag="th")
        if len(header_rows) != 1 or not 3 <= len(headers) <= 6:
            raise ValueError("PURCHASE_ROW_COLUMNS_INVALID")
        original_columns = len(headers)
        group_labels = [
            (header.attrs.get("data-ps-matrix-label") or "").strip()
            for header in headers
        ]
        for row in table.find(tag="tr"):
            if row is header_rows[0]:
                continue
            cells = [
                n
                for n in row.children
                if isinstance(n, Element) and n.tag in {"th", "td"}
            ]
            if len(cells) == 1 and cells[0].attrs.get("colspan") == str(
                original_columns
            ):
                cells[0].attrs["colspan"] = "3"
                continue
            if len(cells) != original_columns:
                raise ValueError("PURCHASE_ROW_HEADERS_MISMATCH")
            if original_columns > 3:
                combined = Element("td", {"class": "ps-matrix-specs"})
                cells[1].insert_before(combined)
                for index, cell in enumerate(cells[1:-1], start=1):
                    if cell.attrs.get("id"):
                        combined.append(
                            Element("span", {"id": cell.attrs["id"], "tabindex": "-1"})
                        )
                    group = Element(
                        "div",
                        {
                            "class": (
                                (cell.attrs.get("class") or "")
                                + " ps-matrix-spec-group"
                            ).strip()
                        },
                    )
                    if group_labels[index] and not cell.find(cls="ps-row-fact-label"):
                        group.append(
                            Element(
                                "span",
                                {"class": "ps-row-fact-label ps-matrix-spec-label"},
                                [escape(group_labels[index])],
                            )
                        )
                    for child in list(cell.children):
                        group.append(child)
                    combined.append(group)
                    cell.remove()
            else:
                if not cells[1].has("ps-matrix-specs"):
                    cells[1].attrs["class"] = (
                        (cells[1].attrs.get("class") or "") + " ps-matrix-specs"
                    ).strip()
        if original_columns > 3:
            spec = Element("th", {"scope": "col"}, ["仕様"])
            headers[1].insert_before(spec)
            for header in headers[1:-1]:
                if header.attrs.get("id"):
                    spec.append(
                        Element("span", {"id": header.attrs["id"], "tabindex": "-1"})
                    )
                header.remove()
        for colgroup in list(table.find(tag="colgroup")):
            colgroup.remove()
        for row in table.find(tag="tr"):
            row.children = [
                child
                for child in row.children
                if not isinstance(child, str) or child.strip()
            ]
        classes = (table.attrs.get("class") or "").split()
        table.attrs["class"] = " ".join(
            dict.fromkeys(
                [c for c in classes if c != "ps-responsive-comparison"]
                + ["ps-row-comparison", "ps-matrix-comparison"]
            )
        )
        table.attrs["data-ps-spec-columns"] = "1"
        parent_classes = (table.parent.attrs.get("class") or "").split()
        table.parent.attrs["class"] = " ".join(
            dict.fromkeys(
                [c for c in parent_classes if c != "ps-responsive-scroll"]
                + ["ps-row-scroll", "ps-matrix-scroll"]
            )
        )
        label = table.parent.attrs.get("aria-label")
        if label:
            table.parent.attrs["aria-label"] = label.replace(
                "。横にスクロールできます", ""
            )
    return root.html()


def responsive_comparison_markup(html: str) -> str:
    """Keep the real table and its headings when cells stack into product cards."""
    root = fragment(html)
    for table in root.find(tag="table"):
        if table.has("compact-integrated-table"):
            table.attrs["class"] = (
                table.attrs.get("class") or ""
            ) + " ps-row-comparison"
            table.attrs["data-ps-spec-columns"] = "2"
            if table.parent and not table.parent.has("ps-row-scroll"):
                table.parent.attrs["class"] = (
                    table.parent.attrs.get("class") or ""
                ) + " ps-row-scroll"
        if not table.has("ps-row-comparison"):
            continue
        headers = table.find(tag="thead")
        if len(headers) != 1:
            raise ValueError("PURCHASE_ROW_HEADERS_REQUIRED")
        labels = [n.text() for n in headers[0].find(tag="th")]
        table.attrs["class"] = (
            table.attrs.get("class") or ""
        ) + " ps-responsive-comparison"
        if table.parent:
            table.parent.attrs["class"] = (
                table.parent.attrs.get("class") or ""
            ) + " ps-responsive-scroll"
            for attr in ("aria-label",):
                value = table.parent.attrs.get(attr)
                if value:
                    table.parent.attrs[attr] = value.replace(
                        "。横にスクロールできます", ""
                    )
        for row in table.find(tag="tbody")[0].find(tag="tr"):
            cells = [
                n
                for n in row.children
                if isinstance(n, Element) and n.tag in {"th", "td"}
            ]
            if len(cells) != len(labels):
                raise ValueError("PURCHASE_ROW_HEADERS_MISMATCH")
            for cell, label in zip(cells, labels, strict=True):
                cell.attrs["data-ps-column-label"] = label
    for hint in list(root.walk()):
        if (
            any(
                cls.endswith("scroll-hint")
                for cls in (hint.attrs.get("class") or "").split()
            )
            and "横" in hint.text()
        ):
            hint.remove()
    return root.html()


def ensure_rakuten_credit(html: str) -> str:
    """Show the Rakuten Web Service credit on every body that displays its media.

    The product-grid path appends the credit inline, but comparison-row and guide
    articles bind their photos through a different path and were left without it.
    The credit is normalised here so it follows the media placeholder, whichever
    path produced it (KS-006: Rakuten Developers branding guideline).
    """
    if "ps-media-credit" in html or "data-ps-media-product" not in html:
        return html
    for marker in ('<section id="ps-evidence"', '<section id="guide-evidence"'):
        if marker in html:
            return html.replace(marker, RAKUTEN_CREDIT + marker, 1)
    return html + RAKUTEN_CREDIT


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
            "purchase_normalization": True,
        }
        if a["kind"] == "comparison" and a.get("conditions"):
            a["condition_slots"] = [
                {"key": condition["id"], "product_id": pid}
                for condition in a["conditions"]
                for pid in condition["product_ids"]
            ]
        template = templates[a["slug"]]
        snapshot = "ps-pending-content-digest"
        bindings: list[dict[str, str]] = []
        display_media: dict[str, str] = {}
        if a["kind"] == "comparison" and a.get("authored_comparison") is not True:
            html, bindings = render_comparison(
                a, catalog, template, snapshot, product_media, now=now
            )
            if product_media is not None:
                for pid in a["product_ids"] + (
                    a.get("supplementary_product_ids", [])
                    if a.get("commerce_presentation") == "comparison_rows"
                    else []
                ):
                    product = next(
                        p for p in catalog["products"] if p["product_id"] == pid
                    )
                    if not media_allowed(product, catalog) or pid in a.get(
                        "media_exclusions", {}
                    ):
                        continue
                    display_media[pid], _ = render_product_media(
                        product, a, snapshot, product_media[pid]
                    )
        elif a["kind"] == "curated_comparison" or (
            a["kind"] == "comparison" and a.get("authored_comparison") is True
        ):
            html, bindings, display_media = render_curated_commerce(
                template, a, catalog, snapshot, product_media, now
            )
        elif a["kind"] == "guide":
            html = render_guide(a, catalog, guide_registry, template, now=now)
            if a.get("commerce_presentation") == "comparison_rows":
                root = fragment(html)
                targets = [
                    node
                    for node in root.find(tag="section")
                    if node.attrs.get("id") == a.get("commerce_anchor")
                ]
                notices = root.find(cls="ps-disclosure")
                if len(targets) != 1 or len(notices) != 1 or a.get("purchase_slots"):
                    raise ValueError("PURCHASE_GUIDE_TABLE_TARGET_INVALID")
                # Bind commerce to both scopes without reclassifying the guide or
                # counting the supplemental example as one of its main models.
                row_article = {
                    **a,
                    "product_ids": a["product_ids"]
                    + a.get("supplementary_product_ids", []),
                }
                html, bindings, display_media = bind_comparison_rows(
                    root, targets[0], row_article, catalog, snapshot, product_media, now
                )
            else:
                html, bindings, display_media = bind_guide_purchase_slots(
                    html, a, catalog, snapshot, product_media, now
                )
        elif a["kind"] == "hub":
            html = render_hub(a, catalog, template, now=now)
        else:
            html = template
        condition_media: dict[str, Any] = {}
        if a.get("condition_slots") is not None:
            html, condition_bindings, condition_media = bind_condition_commerce(
                html, a, catalog, snapshot, product_media, now
            )
            bindings.extend(condition_bindings)
        if a["kind"] != "policy":
            html = add_compatibility_anchors(
                html,
                template,
                normalize=a["purchase_normalization"],
                anchor_targets=a.get("legacy_anchor_targets"),
            )
        if a.get("commerce_presentation") == "comparison_rows":
            if a["kind"] == "comparison" and a.get("authored_comparison") is not True:
                html = consolidate_comparison_details(html)
            if a.get("responsive_layout") != "authored":
                html = matrix_comparison_markup(html)
        if a.get("responsive_layout") != "authored":
            html = readable_tables(html)
        html = ensure_rakuten_credit(html)
        rendered = "<!-- wp:html -->\n" + html + "\n<!-- /wp:html -->\n"
        final_snapshot = (
            "ps-"
            + sha256(
                (
                    rendered
                    + canonical(display_media)
                    + (canonical(condition_media) if condition_media else "")
                ).encode()
            ).hexdigest()[:32]
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
                **(
                    {
                        "guide_product_scope": {
                            "main": a["product_ids"],
                            "supplementary": a.get("supplementary_product_ids", []),
                        }
                    }
                    if a["kind"] == "guide"
                    and a.get("commerce_presentation") == "comparison_rows"
                    else {}
                ),
                "snapshot_id": snapshot,
                "body_sha256": sha256(outputs[a["slug"]].encode()).hexdigest(),
                "bindings": bindings,
                "media": {
                    pid: markup.replace("ps-pending-content-digest", final_snapshot)
                    for pid, markup in display_media.items()
                },
                **(
                    {
                        "condition_media": {
                            key: {
                                **value,
                                "html": value["html"].replace(
                                    "ps-pending-content-digest", final_snapshot
                                ),
                            }
                            for key, value in condition_media.items()
                        }
                    }
                    if condition_media
                    else {}
                ),
            }
        )
    return outputs, runtime
