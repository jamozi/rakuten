"""Public-safe entry pages projected from the article ledger.

Lists, counts, roles, anchors and dates come from each ledger row's `listing`;
page-specific editorial choices come from entry-pages and name article keys.
Editorial dates are explicit facts: never inferred from file, WP, or price timestamps.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
import re
from typing import Any

from raos.application.editorial.reader_html import Element, fragment, readable_tables

PURPOSES = {
    "small-space": (
        "一人暮らし・省スペース",
        "どこを測れば候補を絞れる？",
        "本体・可動部・周囲空間を分けて採寸します。",
    ),
    "save-housework": (
        "家事を短くしたい",
        "家電に任せても残る作業は？",
        "洗い物と床掃除で、準備・片づけ・手入れを比べます。",
    ),
    "without-installation": (
        "工事なしの食洗機",
        "タンクとポンプ給水、続けやすいのは？",
        "タンク式と外部容器からのポンプ給水を、水運び・容器の置き場所・設置条件で比べます。",
    ),
    "easy-maintenance": (
        "手入れを続けやすいものを選びたい",
        "自分に残る作業と部品代は？",
        "食洗機・掃除機・スーツケースごとに確認できます。",
    ),
    "comfortable-travel": (
        "旅行の荷物・移動を楽にしたい",
        "旅のどの場面で困る？",
        "階段・車内・小型機の便・宿・帰路の荷物で考えます。",
    ),
    "prepare-outage": (
        "停電に備えたい",
        "手持ちの備えで足りる？",
        "使う機器・必要時間・場所から、買い足す必要を考えます。",
    ),
}
PURPOSE_GROUPS = {
    "before": ("購入前に", "purpose-before"),
    "in_use": ("使い始めてからの手間で選ぶ", "purpose-in-use"),
}
HOME_CATEGORIES = (
    ("kitchen", "食器と食洗機のあるキッチンのイメージ"),
    ("travel", "スーツケースと衣類を揃えた旅支度のイメージ"),
    ("cleaning", "ロボット掃除機を置いた部屋のイメージ"),
    ("preparedness", "ポータブル電源とランタンを並べた備えのイメージ"),
)
LISTING_KEYS = frozenset(
    {
        "state",
        "role",
        "category",
        "short_title",
        "task_label",
        "main_label",
        "main_count",
        "reference_count",
        "reference_label",
        "reference_unit",
        "comparison_anchor",
        "offers_anchor",
        "card_image",
        "published_at_gmt",
        "published_on",
        "home_order",
        "change_log",
        "specification_checked_on",
        "sales_checked_at",
    }
)
LISTING_STATES = frozenset({"published", "draft", "withdrawn"})
CHANGE_KINDS = frozenset({"content", "correction"})
REFERENCE_UNITS = frozenset({"製品", "件"})
# Reader questions whose link is owed by a later batch; all of them end by J2.
PLANNED_BATCHES = ("H", "I", "J1", "J2")
COMPARISON_PAGE_KINDS = frozenset(
    {
        "capacity_comparison",
        "tank_workflow_comparison",
        "head_to_head",
        "broad_comparison",
        "condition_comparison",
        "brand_comparison",
    }
)
COLLECTION_PAGE_KINDS = frozenset({"home", "directory"})
READER_PAGE_KINDS = (
    COMPARISON_PAGE_KINDS
    | COLLECTION_PAGE_KINDS
    | {"category_hub", "purpose_hub", "policy", "task_guide"}
)
ROLE_FIELDS = (
    "page_kind",
    "primary_intent",
    "reader",
    "decision_after_reading",
    "main_cta",
    "next_question",
)
ROLE_TEXT_LIMITS = {"primary_intent": 80, "reader": 60, "decision_after_reading": 60}
JST = timezone(timedelta(hours=9))
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
ID_ATTRIBUTE = re.compile(r'\sid="([^"]*)"')
SPONSORED = re.compile(r'rel=["\'][^"\']*sponsored', re.I)
ADVERTISING = re.compile(
    r'rel=["\'][^"\']*sponsored|https://(?:a|hb)\.rakuten\.co\.jp|data-affiliate', re.I
)


def link(url: str, text: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def table(
    headers: list[str], rows: list[list[str]], label: str = "確認項目の表"
) -> str:
    return (
        '<div class="ks-editorial-table" role="region" aria-label="'
        + escape(label, quote=True)
        + '" tabindex="0"><table><thead><tr>'
        + "".join(f'<th scope="col">{escape(h)}</th>' for h in headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>"
            + "".join(
                f"<{'th scope=' + chr(34) + 'row' + chr(34) if i == 0 else 'td'}>{c}</{'th' if i == 0 else 'td'}>"
                for i, c in enumerate(row)
            )
            + "</tr>"
            for row in rows
        )
        + "</tbody></table></div>"
    )


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _count(value: Any) -> bool:
    return type(value) is int and bool(value >= 0)


def is_published(row: dict[str, Any]) -> bool:
    """Pages are public once existing; posts also need a published listing."""
    if row.get("mode") != "existing":
        return False
    if row["post_type"] == "page":
        return True
    return bool((row.get("listing") or {}).get("state") == "published")


def _check_listing(
    row: dict[str, Any], listing: dict[str, Any], data: dict[str, Any]
) -> None:
    slug = row["slug"]

    def invalid() -> None:
        raise ValueError("EDITORIAL_LISTING_INVALID: " + slug)

    if set(listing) != LISTING_KEYS or listing["category"] not in data["categories"]:
        invalid()
    if not _text(listing["short_title"]) or not all(
        _count(listing[k]) for k in ("main_count", "reference_count")
    ):
        invalid()
    if listing["role"] == "comparison":
        if (
            listing["main_count"] < 1
            or not _text(listing["main_label"])
            or not _text(listing["comparison_anchor"])
            or not (listing["offers_anchor"] is None or _text(listing["offers_anchor"]))
            or listing["task_label"] is not None
        ):
            invalid()
    elif listing["role"] == "guide":
        if (
            not _text(listing["task_label"])
            or listing["main_count"]
            or listing["reference_count"]
            or any(
                listing[k] is not None
                for k in ("main_label", "comparison_anchor", "offers_anchor")
            )
        ):
            invalid()
    else:
        invalid()
    if listing["reference_count"]:
        if (
            not _text(listing["reference_label"])
            or listing["reference_unit"] not in REFERENCE_UNITS
        ):
            invalid()
    elif (
        listing["reference_label"] is not None or listing["reference_unit"] is not None
    ):
        invalid()
    image = listing["card_image"]
    if image is not None and (
        not isinstance(image, dict)
        or set(image) != {"src", "width", "height", "alt"}
        or not isinstance(image["src"], str)
        or not image["src"].startswith("/wp-content/themes/")
        or not all(type(image[k]) is int and image[k] > 0 for k in ("width", "height"))
        or not _text(image["alt"])
    ):
        invalid()
    order = listing["home_order"]
    if order is not None and (type(order) is not int or order < 1):
        invalid()
    for key, pattern in (
        ("published_on", DATE),
        ("specification_checked_on", DATE),
        ("published_at_gmt", TIMESTAMP),
        ("sales_checked_at", TIMESTAMP),
    ):
        if listing[key] is not None and not (
            isinstance(listing[key], str) and pattern.fullmatch(listing[key])
        ):
            raise ValueError("Invalid editorial date")
    if listing["published_on"] and listing["published_at_gmt"]:
        local = (
            datetime.strptime(listing["published_at_gmt"], "%Y-%m-%dT%H:%M:%SZ")
            .replace(tzinfo=timezone.utc)
            .astimezone(JST)
        )
        if local.date().isoformat() != listing["published_on"]:
            raise ValueError("EDITORIAL_PUBLISHED_ON_MISMATCH: " + slug)
    if not isinstance(listing["change_log"], list):
        invalid()
    for entry in listing["change_log"]:
        if (
            not isinstance(entry, dict)
            or set(entry) != {"date", "kind", "summary"}
            or entry["kind"] not in CHANGE_KINDS
            or not _text(entry["summary"])
        ):
            invalid()
        if not (isinstance(entry["date"], str) and DATE.fullmatch(entry["date"])):
            raise ValueError("Invalid editorial date")


def metadata(
    registry: dict[str, Any],
    catalog: dict[str, Any],
    data: dict[str, Any],
    bodies: dict[str, str],
) -> dict[str, Any]:
    catalog_articles = {a["slug"]: a for a in catalog["articles"]}
    products = {p["product_id"]: p for p in catalog["products"]}
    result = {}
    for row in registry["articles"]:
        if row["post_type"] != "post":
            continue
        listing = row.get("listing")
        if row.get("mode") != "existing":
            # Owner-direct drafts have no verified publication identity yet.
            if isinstance(listing, dict) and listing.get("state") == "published":
                raise ValueError("LEDGER_IDENTITY_STALE: " + row["slug"])
            continue
        if not isinstance(listing, dict):
            raise ValueError(f"Missing editorial listing: {row['slug']}")
        if listing.get("state") not in LISTING_STATES:
            raise ValueError("EDITORIAL_LISTING_INVALID: " + row["slug"])
        if listing["state"] != "published":
            continue
        if type(row.get("post_id")) is not int:
            raise ValueError("LEDGER_IDENTITY_STALE: " + row["slug"])
        _check_listing(row, listing, data)
        article = catalog_articles.get(row["slug"])
        product_ids = list(article.get("product_ids", [])) if article else []
        if listing["role"] == "comparison" and product_ids:
            listed = len(product_ids) + len(
                (article or {}).get("supplementary_product_ids", [])
            )
            if listing["main_count"] + listing["reference_count"] != listed:
                raise ValueError("EDITORIAL_COUNT_MISMATCH: " + row["slug"])
        change_log = [dict(entry) for entry in listing["change_log"]]
        latest = (
            max(change_log, key=lambda entry: entry["date"]) if change_log else None
        )
        result[row["slug"]] = {
            "article_key": row["article_key"],
            "slug": row["slug"],
            "post_id": row["post_id"],
            "title": row["title"],
            "excerpt": row.get("excerpt", ""),
            "category": listing["category"],
            "role": listing["role"],
            "short_title": listing["short_title"],
            "task_label": listing["task_label"],
            "main_label": listing["main_label"],
            "comparison_count": listing["main_count"],
            "reference_count": listing["reference_count"],
            "reference_label": listing["reference_label"],
            "reference_unit": listing["reference_unit"],
            "models": [products[p]["exact_model"] for p in product_ids],
            "comparison_anchor": listing["comparison_anchor"],
            "offers_anchor": listing["offers_anchor"],
            "card_image": listing["card_image"],
            "home_order": listing["home_order"],
            "has_ads": bool(ADVERTISING.search(bodies.get(row["slug"], ""))),
            "published_at": listing["published_at_gmt"],
            "published_on": listing["published_on"],
            "updated_on": latest["date"] if latest else None,
            "change_summary": latest["summary"] if latest else None,
            "change_log": change_log,
            "specification_checked_on": listing["specification_checked_on"],
            "sales_checked_at": listing["sales_checked_at"],
        }
    return result


def publication_order(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Newest publication day first; same-day posts follow the editorial home_order."""
    ordered = sorted(
        articles, key=lambda a: (a["published_at"] or "", a["post_id"]), reverse=True
    )
    ordered = sorted(
        ordered, key=lambda a: (a["home_order"] is None, a["home_order"] or 0)
    )
    return sorted(ordered, key=lambda a: a["published_on"] or "", reverse=True)


def render_pages(
    registry: dict[str, Any],
    catalog: dict[str, Any],
    data: dict[str, Any],
    bodies: dict[str, str],
    home_media: dict[int, str] | None = None,
    page_sources: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, str]]]:
    meta = metadata(registry, catalog, data, bodies)
    published: list[dict[str, Any]] = list(meta.values())
    by_key: dict[str, dict[str, Any]] = {a["article_key"]: a for a in published}
    pages = {}
    updates = []

    def ref(key: str) -> dict[str, Any]:
        article: dict[str, Any] | None = by_key.get(key)
        if article is None:
            raise ValueError("EDITORIAL_REFERENCE_UNPUBLISHED: " + key)
        return article

    def in_category(key: str, category: str) -> dict[str, Any]:
        article = ref(key)
        if article["category"] != category:
            raise ValueError("EDITORIAL_REFERENCE_CATEGORY_MISMATCH: " + key)
        return article

    def article_url(key: str, anchor: str = "") -> str:
        return "/" + str(ref(key)["slug"]) + "/" + ("#" + anchor if anchor else "")

    def count_text(a: dict[str, Any]) -> str:
        if a["role"] != "comparison":
            return "ガイド記事"
        text = f"{a['main_label']}{a['comparison_count']}製品"
        if a["reference_count"]:
            text += (
                f"・{a['reference_label']}{a['reference_count']}{a['reference_unit']}"
            )
        return text

    def card(
        key: str,
        label: str = "",
        anchor: str = "",
        summary: str = "",
        date: str = "",
        ident: str = "",
    ) -> str:
        a = ref(key)
        badge = (
            '<span class="ks-pr-badge">PR・広告リンクあり</span>'
            if a["has_ads"]
            else '<span class="ks-card-kind">広告リンクなし</span>'
        )
        if not date:
            date = (
                "内容更新日：" + a["updated_on"]
                if a["updated_on"]
                else "公開日：" + (a["published_on"] or "未確認")
            )
        opening = (
            f'<article id="{escape(ident, quote=True)}" class="ks-editorial-card">'
            if ident
            else '<article class="ks-editorial-card">'
        )
        return (
            opening
            + badge
            + f'<h3>{link(article_url(key, anchor), label or a["title"])}</h3><p>{escape(summary or a["excerpt"])}</p><p class="ks-card-meta">{escape(count_text(a))} ／ {escape(date)}</p></article>'
        )

    def cards(keys: list[str]) -> str:
        return '<div class="ks-route-grid">' + "".join(card(k) for k in keys) + "</div>"

    def category_articles(category: str) -> list[dict[str, Any]]:
        return [a for a in published if a["category"] == category]

    def representative(category: str) -> dict[str, Any]:
        article = in_category(data["categories"][category]["representative"], category)
        if article["role"] != "comparison":
            raise ValueError("EDITORIAL_REPRESENTATIVE_INVALID: " + category)
        return article

    def category_cards(heading: str = "h3") -> str:
        out = ""
        for slug, cat in data["categories"].items():
            articles = category_articles(slug)
            comparisons = [a for a in articles if a["role"] == "comparison"]
            guides = [a for a in articles if a["role"] == "guide"]
            main = representative(slug)
            choice = cat["choose"]
            chosen = in_category(choice["article_key"], slug)
            routes = [
                link("/" + slug + "/", "カテゴリを見る"),
                al(main["article_key"], "代表比較を読む"),
                al(chosen["article_key"], choice["label"], choice["anchor"]),
            ]
            kinds = [f"比較{len(comparisons)}本"] + (
                [f"ガイド{len(guides)}本"] if guides else []
            )
            summary = f"{cat['name']}の記事 {len(articles)}本（{'・'.join(kinds)}）"
            out += (
                f'<article class="ks-editorial-card"><{heading}>{escape(cat["name"])}</{heading}><p>{escape(cat["lead"])}</p><ul>'
                + "".join("<li>" + route + "</li>" for route in routes)
                + f"</ul><details><summary>{escape(summary)}</summary><ul>"
                + "".join(
                    "<li>" + al(a["article_key"], a["title"]) + "</li>"
                    for a in comparisons + guides
                )
                + "</ul></details></article>"
            )
        return '<div class="ks-route-grid">' + out + "</div>"

    def purpose_cards(home: bool = False) -> str:
        if home:
            labels = [
                "省スペース",
                "家事を短く",
                "分岐水栓工事を避ける",
                "手入れを楽に",
                "旅行の荷物を楽に",
                "停電に備える",
            ]
            return (
                '<div class="ks-route-grid">'
                + "".join(
                    '<article class="ks-editorial-card"><h3>'
                    + link("/" + slug + "/", label)
                    + "</h3></article>"
                    for slug, label in zip(PURPOSES, labels, strict=True)
                )
                + "</div>"
            )
        groups = data["purpose_groups"]
        grouped = [slug for group in PURPOSE_GROUPS for slug in groups.get(group, [])]
        if set(groups) != set(PURPOSE_GROUPS) or sorted(grouped) != sorted(PURPOSES):
            raise ValueError("EDITORIAL_PURPOSE_GROUPS_INVALID")
        return "".join(
            section(
                title,
                '<div class="ks-route-grid">'
                + "".join(
                    f'<article class="ks-editorial-card"><h3>{link("/" + slug + "/", PURPOSES[slug][0])}</h3><p>{escape(PURPOSES[slug][1])}</p><p>{escape(PURPOSES[slug][2])}</p></article>'
                    for slug in groups[group]
                )
                + "</div>",
                ident,
            )
            for group, (title, ident) in PURPOSE_GROUPS.items()
        )

    def section(title: str, content: str, anchor: str = "") -> str:
        return (
            "<section"
            + (f' id="{anchor}"' if anchor else "")
            + f"><h2>{escape(title)}</h2>{content}</section>"
        )

    def al(key: str, text: str, anchor: str = "") -> str:
        return link(article_url(key, anchor), text)

    def specs(key: str) -> str:
        return str(ref(key)["comparison_anchor"])

    flight = (
        "<p>まず利用する運航会社・便・機材を確認します。通常の便、小型機、LCCで条件は共通ではありません。各辺・3辺合計・荷物込み重量・個数・拡張状態を照合します。</p><p>"
        + al("carry-on-suitcase-under-100-seats", "小型機の寸法条件を比べる")
        + " ／ "
        + al("lightweight-carry-on-suitcase-under-3kg", "通常サイズの軽さを比べる")
        + "</p><p>会社別の規定と確認日は各比較記事の公式出典へ。一般的な「機内持ち込み対応」の表示だけでは搭乗便への適合を保証しません。</p>"
    )
    for slug, page in data["pages"].items():
        title = PURPOSES[slug][0] if slug in PURPOSES else page["title"]
        body = ""
        if slug == "home":

            def feature(image_category: str, caption: str) -> str:
                category = data["categories"][image_category]
                destination = "/" + image_category + "/"
                label_link = link(destination, category["name"])
                legacy_anchor = {
                    "kitchen": "cluster-home",
                    "travel": "cluster-mobility",
                    "preparedness": "cluster-ready",
                }.get(image_category)
                if legacy_anchor:
                    label_link = label_link.replace(
                        "<a ", f'<a id="{legacy_anchor}" ', 1
                    )
                main = representative(image_category)
                markup = (
                    '<article class="ks-editorial-card"><h3>'
                    + label_link
                    + "</h3><p>"
                    + escape(category["decides"])
                    + "</p><p>"
                    + al(main["article_key"], main["short_title"])
                    + "</p></article>"
                )
                media = (
                    '<figure class="ks-feature-image"><img src="https://kurashinoshirube.com/wp-content/uploads/2026/09/ks-'
                    + image_category
                    + '-editorial-ai-20260910.webp" width="762" height="506" alt="'
                    + escape(caption, quote=True)
                    + '" loading="lazy"></figure>'
                )
                media = media.replace(
                    "<img ", '<a href="' + destination + '"><img ', 1
                ).replace("</figure>", "</a></figure>", 1)
                product_media = next(
                    (
                        home_media[a["post_id"]]
                        for a in category_articles(image_category)
                        if home_media and a["post_id"] in home_media
                    ),
                    None,
                )
                if product_media:
                    media = (
                        '<div class="ks-home-product-images">'
                        + product_media
                        + "</div>"
                    )
                return markup.replace(
                    '<article class="ks-editorial-card">',
                    '<article class="ks-editorial-card">' + media,
                    1,
                )

            body = (
                '<section class="ks-home-feature"><div class="ks-home-masthead"><div class="ks-home-intro"><p class="km-tag">暮らしの道具を、納得して選ぶ</p><h1 id="km-hero-title">あなたの暮らしに、<br>合うものを。</h1><p>'
                + escape(page["lead"])
                + '</p></div><figure class="ks-home-mood"><img src="/wp-content/themes/kurashinoshirube-child/assets/images/home-lifestyle-20260913.webp" width="1672" height="941" alt="朝の光が差す一人暮らしのキッチンと食卓のAI編集イメージ"></figure></div><section id="km-categories-title"><h2 id="km-articles-title">商品カテゴリー</h2><div class="ks-home-feature-grid ks-home-category-grid">'
                + "".join(feature(c, caption) for c, caption in HOME_CATEGORIES)
                + "</div></section></section>"
            )
            recent = publication_order([a for a in published if a["published_on"]])[:4]

            def recent_image(article: dict[str, Any]) -> str:
                image = article["card_image"]
                if image is None:
                    image = {
                        "src": "https://kurashinoshirube.com/wp-content/uploads/2026/09/ks-"
                        + article["category"]
                        + "-editorial-ai-20260910.webp",
                        "width": 762,
                        "height": 506,
                        "alt": data["categories"][article["category"]]["name"]
                        + "のある暮らしの編集イメージ",
                    }
                return (
                    f'<img src="{escape(image["src"], quote=True)}"'
                    f' width="{int(image["width"])}" height="{int(image["height"])}"'
                    f' alt="{escape(image["alt"], quote=True)}" loading="lazy">'
                )

            body += section(
                "新着記事",
                '<div class="ks-home-updates">'
                + "".join(
                    '<article class="ks-editorial-card">'
                    + '<a class="ks-recent-image" href="'
                    + article_url(a["article_key"])
                    + '">'
                    + recent_image(a)
                    + "</a><h3>"
                    + al(a["article_key"], a["title"])
                    + "</h3></article>"
                    for a in recent
                )
                + "</div>"
                if recent
                else "<p>公開日の記録を照合中です。</p>",
                "km-updates-title",
            )
            body += (
                '<p class="ks-home-more">' + link("/updates/", "記事一覧へ") + "</p>"
            )
        elif slug == "categories":
            body = (
                "<p>商品名が決まっていれば代表比較へ。まだ決まっていなければ、各カードの3つめのリンクから、条件で候補を絞る節へ進めます。</p>"
                # The page has no section heading above the cards (KS-028-d).
                + category_cards(heading="h2")
            )
        elif slug == "purposes":
            body = (
                "<p>知りたいことに近い問いから選べます。順番に全ページを読む必要はありません。</p>"
                + purpose_cards()
            )
        elif slug == "comparisons":
            title = "商品比較の記事一覧"
            body = (
                '<nav id="ks-comparison-jump" aria-label="比較する商品カテゴリ">'
                + " ／ ".join(
                    link("#compare-" + c, v["name"])
                    for c, v in data["categories"].items()
                )
                + "</nav>"
            )
            for category, cat in data["categories"].items():
                contents = ""
                for a in category_articles(category):
                    if a["role"] != "comparison":
                        continue
                    key = a["article_key"]
                    routes = (
                        al(key, "比較表へ", a["comparison_anchor"])
                        + " ／ "
                        + al(key, "販売条件へ", a["offers_anchor"])
                        if a["offers_anchor"]
                        else al(key, "比較表・販売条件へ", a["comparison_anchor"])
                    )
                    contents += card(key) + "<p>" + routes + "</p>"
                body += section(cat["name"], contents, "compare-" + category)
            body += section(
                "購入前の4項目",
                "<ul><li>型番・セット構成</li><li>自宅や利用便への適合条件</li><li>送料・必要品を含む総額</li><li>納期・販売元・保証</li></ul><p>ポイントや条件付きクーポンは、支払額と分けて確認します。条件が残る場合は買わずに保留できます。</p>",
                "purchase-checks",
            )
        elif slug == "guides":
            body = section(
                "ガイド記事：知りたい作業から",
                '<div class="ks-route-grid">'
                + "".join(
                    card(a["article_key"], a["task_label"])
                    for a in published
                    if a["role"] == "guide"
                )
                + "</div>",
                "kitchen-guides",
            )
            body += section(
                "比較記事内の説明：採寸と条件整理",
                '<div class="ks-route-grid">'
                + "".join(
                    card(
                        in_category(item["article_key"], item["category"])[
                            "article_key"
                        ],
                        item["label"],
                        item["anchor"],
                        ident=item["category"] + "-guides",
                    )
                    for item in data["guides_in_article"]
                )
                + "</div>",
            )
        elif slug == "updates":
            title = "新着・内容を更新した記事"
            body = "<p>公開日・内容更新日・仕様確認日・販売条件確認日は別に管理し、誤字・見た目の修正や価格だけの再取得では内容更新日を進めません。</p>"
            entries = sorted(
                ((a, entry) for a in published for entry in a["change_log"]),
                key=lambda pair: pair[1]["date"],
                reverse=True,
            )
            body += section(
                "内容を更新・訂正した記事",
                "".join(
                    card(
                        a["article_key"],
                        summary=("訂正：" if entry["kind"] == "correction" else "")
                        + entry["summary"],
                        date="内容更新日："
                        + entry["date"]
                        + " ／ 公開日："
                        + (a["published_on"] or "未確認"),
                    )
                    for a, entry in entries
                )
                or "<p>内容更新の記録はまだありません。</p>",
                "updated-content",
            )
            body += section(
                "公開した記事（新しい順）",
                "".join(
                    card(
                        a["article_key"],
                        date="公開日：" + (a["published_on"] or "未確認"),
                    )
                    for a in publication_order(published)
                ),
                "new-articles",
            )
        elif slug == "travel":
            travel_routes = [
                (
                    "carry-on-suitcase-under-100-seats",
                    "小型機の寸法条件を比較表で確認する",
                ),
                (
                    "lightweight-carry-on-suitcase-under-3kg",
                    "本体の軽さを比較表で確認する",
                ),
                (
                    "front-open-carry-on-suitcase-with-stopper",
                    "前面収納とストッパーを比較表で確認する",
                ),
                (
                    "carry-on-suitcase-comparison",
                    "容量・拡張・車輪の違いを比較表で確認する",
                ),
            ]
            body = (
                section("利用便の制約から選ぶ", flight, "travel-axes")
                + section(
                    "製品の比較軸",
                    table(
                        ["軸", "比べること"],
                        [
                            [
                                "外寸",
                                "車輪・持ち手を含む各辺と3辺合計。拡張時は別条件。",
                            ],
                            ["重量", "本体重量と荷物を入れた総重量を分けます。"],
                            ["容量", "泊数ではなく普段の荷物を基準にします。"],
                            [
                                "開口構造",
                                "前開き・両開き・立てたまま取り出す際の条件。",
                            ],
                        ],
                    ),
                )
                + "<ul>"
                + "".join(
                    "<li>" + al(key, label, specs(key)) + "</li>"
                    for key, label in travel_routes
                )
                + "</ul>"
                + cards([key for key, _ in travel_routes])
                + "<p>"
                + link("/comfortable-travel/", "旅の場面から荷物・移動を考える")
                + "</p>"
            )
        elif slug == "cleaning":
            body = (
                section(
                    "機械に任せる作業と自分に残る作業",
                    "<p>床の片づけは自分に残る作業です。吸引・水拭き・自動ゴミ収集・モップ洗浄乾燥は別の機能です。</p>",
                    "cleaning-axes",
                )
                + section(
                    "必要な空間を分けて測る",
                    '<div class="ks-space-diagram"><span>本体</span><span>台</span><span>帰還経路</span><span>蓋・タンク交換</span></div><p>色枠は測る範囲を示す編集上の概念図です。縮尺・実測値・設置保証ではありません。公表寸法と未確認の余白は機種別の比較表で分けています。</p>'
                    + al(
                        "compact-robot-vacuum-shortlist",
                        "機種別の寸法と余白を見る",
                        specs("compact-robot-vacuum-shortlist"),
                    ),
                )
                + section(
                    "構成の違いで比較する",
                    table(
                        ["構成", "比較先"],
                        [
                            [
                                "小さい台＋自動収集の2候補",
                                al(
                                    "roomba-mini-vs-switchbot-k11-pro",
                                    "Mini + AutoEmpty / K11+ Pro",
                                ),
                            ],
                            [
                                "充電台のみ",
                                al(
                                    "roomba-mini-vs-switchbot-k11-pro",
                                    "Mini Slim + SlimCharge",
                                ),
                            ],
                            [
                                "掃除機収納の統合",
                                al("compact-robot-vacuum-shortlist", "K10+ Pro Combo"),
                            ],
                            [
                                "水拭きの手入れ自動化",
                                al(
                                    "compact-robot-vacuum-shortlist",
                                    "Roomba Plus 515 Combo + AutoWash",
                                ),
                            ],
                        ],
                    ),
                )
                + cards(
                    [
                        "compact-robot-vacuum-shortlist",
                        "roomba-mini-vs-switchbot-k11-pro",
                    ]
                )
            )
        elif slug == "preparedness":
            body = (
                section(
                    "容量と出力を別に比較する",
                    table(
                        ["必要な条件", "調べること"],
                        [
                            [
                                "必要Wh",
                                "何を・何時間使うか。変換損失もあるため公称容量は使用時間の保証ではありません。",
                            ],
                            ["同時使用W", "同時につなぐ機器の消費電力。"],
                            [
                                "起動W",
                                "定格出力とは別に、機器の起動負荷と電源の対応条件。",
                            ],
                            ["端子・制限", "接続機器の指定、波形、端子、使用環境。"],
                        ],
                    )
                    + "<p>次の3項目を紙やメモに書き出してから、計算例に当てはめられます。未記入のまま特定の機種に決める必要はありません。</p>"
                    + table(
                        [
                            "用途：何を使うか",
                            "時間：何時間使うか",
                            "同時使用：一緒に動かす機器",
                        ],
                        [
                            [
                                "記入：＿＿＿＿＿＿",
                                "記入：＿＿時間",
                                "記入：＿＿＿＿＿＿",
                            ]
                        ],
                    )
                    + al(
                        "portable-power-station-guide",
                        "必要Whの計算例へ",
                        "ps-decision-steps",
                    ),
                )
                + cards(
                    [
                        "portable-power-station-guide",
                        "anker-solix-c300-c800-c1000-differences",
                    ]
                )
                + "<p>接続機器への適合が未確認なら「使える」とは判断できません。住宅全体・医療機器への給電は対象外です。</p><p>"
                + link("/prepare-outage/", "停電時の使い道と買い足す必要を考える")
                + "</p>"
            )
        elif slug == "small-space":
            body = (
                section(
                    "本体・可動部・周囲空間の3枠",
                    "<p>同じ測定軸・同じ状態で比べます。本体奥行と開扉時奥行を直接比べず、余白・給排水・電源を別に確かめます。</p>",
                )
                + section(
                    "キッチンに置く",
                    card(
                        "dishwasher-installation-measurement", "食洗機の置き場所を測る"
                    )
                    + card(
                        "solota-vs-rakua-mini-plus",
                        "本体寸法と開扉時寸法を別々に比較する",
                    ),
                )
                + section(
                    "床に置く",
                    card(
                        "compact-robot-vacuum-shortlist",
                        "本体・台・帰還経路を測る",
                        specs("compact-robot-vacuum-shortlist"),
                    )
                    + card("roomba-mini-vs-switchbot-k11-pro"),
                )
            )
        elif slug == "save-housework":
            body = (
                section(
                    "任せる作業／残る作業",
                    table(
                        ["商品", "任せる作業", "残る作業"],
                        [
                            [
                                "食洗機",
                                "洗浄・すすぎ。乾燥方式は機種別。",
                                "食器の下準備・出し入れ・給水・清掃。",
                            ],
                            [
                                "ロボット掃除機",
                                "吸引。水拭き・自動収集・洗浄乾燥は構成別。",
                                "床の片づけ・タンク補給・部品の手入れ。",
                            ],
                        ],
                    )
                    + "<p>運転時間と人の作業時間は異なります。実測の削減時間や購入価値は断定していません。清掃頻度は機種で異なります。</p>",
                )
                + section(
                    "洗い物を減らす",
                    card("countertop-dishwasher-for-small-households")
                    + al("dishwasher-cleaning-guide", "型番別の清掃頻度へ"),
                )
                + section(
                    "床掃除を任せる",
                    cards(
                        [
                            "compact-robot-vacuum-shortlist",
                            "roomba-mini-vs-switchbot-k11-pro",
                        ]
                    ),
                )
            )
        elif slug == "without-installation":
            body = section(
                "分岐水栓なしでも残る設置条件",
                table(
                    ["項目", "本人が測れること", "確認する相手・資料"],
                    [
                        ["分岐水栓", "希望する給水方式", "型番別の説明書・メーカー"],
                        [
                            "電源・接地",
                            "コンセントと接地端子の有無",
                            "施工業者・賃貸管理者。接地を省略・改造しません。",
                        ],
                        [
                            "排水固定",
                            "排水先までの経路と距離",
                            "説明書の固定方法・メーカー",
                        ],
                        [
                            "台と耐荷重",
                            "設置面の幅・奥行と可動部の空間",
                            "台のメーカーの耐荷重と機種の運転時重量。",
                        ],
                    ],
                )
                + "<p>問い合わせには型番、採寸値、設備の状況を用意します。住所や室内写真などの個人情報を公開投稿する必要はありません。</p>",
            ) + cards(
                [
                    "dishwasher-installation-measurement",
                    "dishwasher-water-supply-methods",
                    "countertop-dishwasher-for-small-households",
                    "solota-vs-rakua-mini-plus",
                ]
            )
        elif slug == "easy-maintenance":
            body = "<p>頻度は型番別の公式指定を優先します。毎回・週次・汚れに応じて・交換通知時などを共通の月次作業へ置き換えません。</p>"
            for label, keys, work in [
                (
                    "食洗機",
                    [
                        "dishwasher-cleaning-guide",
                        "dishwasher-detergent-guide",
                        "dishwasher-running-cost",
                    ],
                    "フィルター・ノズル・洗剤",
                ),
                (
                    "掃除機",
                    [
                        "compact-robot-vacuum-shortlist",
                        "roomba-mini-vs-switchbot-k11-pro",
                    ],
                    "紙パック・ブラシ・フィルター・モップ",
                ),
                (
                    "スーツケース",
                    [
                        "front-open-carry-on-suitcase-with-stopper",
                        "carry-on-suitcase-comparison",
                    ],
                    "車輪・鍵・外装",
                ),
            ]:
                body += section(
                    label,
                    table(
                        ["残る作業", "頻度・部品品番・確認時価格・購入先", "不明点"],
                        [
                            [
                                work,
                                "対象型番の記事の公式資料・確認日・販売条件を参照。",
                                "未確認の費用は0円ではありません。将来の部品供給は保証しません。",
                            ]
                        ],
                    )
                    + cards(keys),
                )
        elif slug == "comfortable-travel":
            body = (
                section("利用便の条件を先に確認", flight)
                + section(
                    "旅の場面から絞る",
                    table(
                        ["場面", "気になること", "記事へ"],
                        [
                            [
                                "駅の階段",
                                "荷物込みで持ち上げられるか",
                                al(
                                    "lightweight-carry-on-suitcase-under-3kg",
                                    "本体の軽さを比較",
                                ),
                            ],
                            [
                                "車内",
                                "立てたまま取り出す物",
                                al(
                                    "front-open-carry-on-suitcase-with-stopper",
                                    "前面収納を比較",
                                ),
                            ],
                            [
                                "小型機の便",
                                "各辺・3辺合計・重量・個数の条件",
                                al(
                                    "carry-on-suitcase-under-100-seats",
                                    "小型機の寸法条件",
                                ),
                            ],
                            [
                                "宿",
                                "開く場所と収納",
                                al(
                                    "carry-on-suitcase-comparison", "容量・開き方を比較"
                                ),
                            ],
                            [
                                "帰路",
                                "増えた荷物と拡張後の外寸",
                                al(
                                    "carry-on-suitcase-comparison", "拡張時の条件を確認"
                                ),
                            ],
                        ],
                    ),
                )
                + "<p>重視する条件で候補を絞り、便の規定・収納・予算を最後に照合します。手持ちの鞄で足りるなら買い足さない選択もあります。</p>"
            )
        elif slug == "prepare-outage":
            # KS-116: a paper worksheet; the worked example reuses article 28's
            # recorded assumption (10W x 8h + 40W x 4h = 240Wh, 50W together).
            body = section(
                "停電時に不足する用途を整理する",
                "<p>この表は紙やメモに書き写して使う記入式です。ページ上で自動で計算はしません。記入例の2行を参考に、手元の機器に置き換えてください。起動時の条件は説明書で確かめ、未確認なら空欄のままにします。</p>"
                + table(
                    [
                        "使う機器",
                        "消費電力W・同時に使うか",
                        "必要時間",
                        "起動時の条件",
                        "動かす場所・手持ちの備え",
                    ],
                    [
                        [
                            "記入例：照明",
                            "10W<br>扇風機と同時",
                            "8時間",
                            "説明書で確認",
                            "＿＿",
                        ],
                        [
                            "記入例：扇風機",
                            "40W<br>合わせて50W",
                            "4時間",
                            "説明書で確認",
                            "＿＿",
                        ],
                        ["＿＿", "＿＿W", "＿＿時間", "＿＿", "＿＿"],
                        ["＿＿", "＿＿W", "＿＿時間", "＿＿", "＿＿"],
                    ],
                    label="停電時の用途の記入表（記入式・自動計算なし）",
                )
                + "<p>記入例は説明用の仮定で、実測値や機器の対応を示すものではありません。例の合計は10W×8時間＋40W×4時間＝240Whです。変換で失われる分を含めた必要容量の考え方は"
                + al(
                    "portable-power-station-guide",
                    "必要Whの計算例",
                    "ps-decision-steps",
                )
                + "で確認できます。</p>"
                + "<p>既に持つ充電手段や照明で必要な用途を満たせるなら、電源を買い足す必要はありません。住宅全体・医療機器への給電は対象外です。</p>",
            ) + section(
                "不足する用途がある場合",
                "<p>容量Wh、同時使用W、起動時の負荷、端子と機器メーカーの対応条件を別々に照合します。定格1000W・1500Wなどの階級だけで起動を保証しません。</p>"
                + cards(
                    [
                        "portable-power-station-guide",
                        "anker-solix-c300-c800-c1000-differences",
                    ]
                ),
            )
        elif slug == "kitchen":
            body = (
                section(
                    "買う前に",
                    cards(
                        [
                            "dishwasher-installation-measurement",
                            "dishwasher-water-supply-methods",
                            "countertop-dishwasher-for-small-households",
                            "solota-vs-rakua-mini-plus",
                        ]
                    ),
                )
                + section(
                    "購入後に続ける作業",
                    cards(
                        [
                            "dishwasher-detergent-guide",
                            "dishwasher-cleaning-guide",
                            "dishwasher-running-cost",
                        ]
                    ),
                )
                + "<p>比較記事は主比較・参考モデル・販売条件を区別しています。人数だけで食器の収納や安全な設置を保証しません。</p>"
            )
        policy = section(
            "編集方針",
            '<p>公式仕様・計算・編集判断を分け、未確認の性能を実測したように評価しません。記事ごとの広告表示は実際のリンクに基づきます。掲載順・評価は報酬条件と切り離しています。</p><nav aria-label="編集方針">'
            + link("/comparison-policy/", "比較・編集方針")
            + " ／ "
            + link("/about-ad-policy/", "運営・広告方針")
            + "</nav>",
            "site-editorial-policy",
        )

        # Legacy hashes bind to readable destinations, never empty page-top placeholders.
        def wrap(content: str, *ids: str) -> str:
            for ident in reversed(ids):
                content = f'<div id="{escape(ident, quote=True)}">{content}</div>'
            return content

        if slug == "home":
            policy = section(
                "編集方針",
                '<p>公式情報をもとに、置き場所・使い方・手入れを比べます。</p><nav aria-label="編集方針">'
                + link("/comparison-policy/", "比較方針")
                + " ／ "
                + link("/about-ad-policy/", "運営・広告方針")
                + "</nav>",
                "site-editorial-policy",
            )
            # Keep old URLs useful without restoring removed homepage sections.
            body = body.replace(
                "</div></section></section>",
                '</div><nav class="ks-home-more" aria-label="ほかの探し方"><a id="km-purposes-title" href="/purposes/">目的から探す</a><span id="home-purchase-check"> ／ <a id="home-purchase-check-title" href="/comparisons/#purchase-checks">購入前の4項目</a></span></nav></section></section>',
                1,
            )
            policy = wrap(policy, "km-editorial-title")
        elif slug in data["categories"] and slug != "kitchen":
            # Category-specific explanations remain first; compare hashes land on cards.
            if f'id="{slug}-axes"' not in body:
                body = body.replace("<section>", f'<section id="{slug}-axes">', 1)
            first_card = body.find('<div class="ks-route-grid">')
            if first_card >= 0:
                body = wrap(
                    body[:first_card], slug + "-start", slug + "-start-title", "choose"
                ) + wrap(body[first_card:], "compare", slug + "-comparisons")
            body += section(
                "購入条件を確認する",
                "<p>"
                + " ／ ".join(
                    al(
                        a["article_key"],
                        a["title"],
                        a["offers_anchor"] or a["comparison_anchor"],
                    )
                    for a in category_articles(slug)
                    if a["role"] == "comparison"
                )
                + "</p>",
                "purchase-checks",
            )
        elif slug == "categories":
            body = wrap(body, "category-cards") + wrap(
                "<p>" + link("/purposes/", "商品が未定なら悩み・目的から探す") + "</p>",
                "category-undecided",
            )
        elif slug == "purposes":
            body = wrap(body, "purpose-cards")
        elif slug in PURPOSES:
            first_end = body.find("</section>") + len("</section>")
            body = wrap(body[:first_end], "first-read") + wrap(
                body[first_end:], "purpose-articles"
            )
            policy = wrap(policy, "next-step")
        elif slug == "guides":
            body = (
                '<nav id="ks-guide-jump" aria-label="採寸と条件整理">'
                + " ／ ".join(
                    link("#" + c + "-guides", v["name"])
                    for c, v in data["categories"].items()
                )
                + "</nav>"
                + body
            )
        elif slug == "comparisons":
            body = body.replace(
                '<section id="purchase-checks"><h2>',
                '<section id="purchase-checks"><h2 id="buyer-offer-check-title">',
                1,
            )
            purchase_start = body.index('<section id="purchase-checks">')
            body = body[:purchase_start] + wrap(
                body[purchase_start:], "buyer-offer-check"
            )
        if slug != "home":
            parent = (
                "categories"
                if slug in data["categories"]
                else "purposes"
                if slug in PURPOSES
                else None
            )
            crumbs = link("/", "ホーム") + " ＞ "
            if parent:
                crumbs += (
                    link("/" + parent + "/", data["pages"][parent]["title"]) + " ＞ "
                )
            crumbs += '<span aria-current="page">' + escape(title) + "</span>"
            body = (
                '<header class="ks-reader-hub-lead"><nav aria-label="このサイトの入口">'
                + crumbs
                + '</nav><p class="ks-directory-lead">'
                + escape(page["description"])
                + "</p></header>"
                + body
            )
            body += "".join(page.get("images", []))
        present = set(re.findall(r'\bid="([^\"]+)"', body + policy)) | (
            {"ks-magazine"} if slug == "home" else set()
        )
        # Consolidated heading/date aliases wrap the corresponding readable content.
        for ident in page["anchors"]:
            if ident not in present:
                if ident.endswith("-axes-title") and f'id="{slug}-axes"' in body:
                    body = body.replace(
                        f'id="{slug}-axes"><h2>',
                        f'id="{slug}-axes"><h2 id="{ident}">',
                        1,
                    )
                else:
                    body = wrap(body, ident)
        pages[slug] = (
            '<!-- wp:html -->\n<div class="ks-reader-hub ks-editorial-page"'
            + (' id="ks-magazine"' if slug == "home" else "")
            + ">"
            + body
            + policy
            + "</div>\n<!-- /wp:html -->\n"
        )
        if slug in (page_sources or {}):
            source = (page_sources or {})[slug]
            tree = fragment(source)
            roots = [node for node in tree.children if isinstance(node, Element)]
            anchor_ids = [
                node.attrs["id"] for node in tree.walk() if node.attrs.get("id")
            ]
            required = {*page["anchors"], "site-editorial-policy"}
            if (
                len(roots) != 1
                or len(anchor_ids) != len(set(anchor_ids))
                or not required.issubset(anchor_ids)
                or tree.find(tag="h1")
                or tree.find(tag="script")
            ):
                raise ValueError("EDITORIAL_PAGE_SOURCE_INVALID: " + slug)
            pages[slug] = source
        updates.append(
            {
                "article_key": slug,
                "title": title,
                "excerpt": PURPOSES[slug][2]
                if slug in PURPOSES
                else page["description"],
            }
        )
    return (
        {
            slug: readable_tables(body) if slug != "home" else body
            for slug, body in pages.items()
        },
        meta,
        updates,
    )


def validate_listing_anchors(
    registry: dict[str, Any], bodies: dict[str, str], pages: dict[str, str]
) -> list[str]:
    """Every listing anchor and every generated deep link lands on exactly one id."""
    counts = {
        row["slug"]: Counter(ID_ATTRIBUTE.findall(bodies.get(row["slug"], "")))
        for row in registry["articles"]
        if row["post_type"] == "post" and is_published(row)
    }
    issues: list[str] = []

    def require(slug: str, anchor: str) -> None:
        issue = f"EDITORIAL_ANCHOR_MISSING: {slug}#{anchor}"
        if counts[slug][anchor] != 1 and issue not in issues:
            issues.append(issue)

    for row in registry["articles"]:
        if row["slug"] in counts:
            for key in ("comparison_anchor", "offers_anchor"):
                if row["listing"].get(key):
                    require(row["slug"], row["listing"][key])
    for html in pages.values():
        for slug, anchor in re.findall(r'href="/([^/"#]+)/#([^"]+)"', html):
            if slug in counts:
                require(slug, anchor)
    return issues


def _linked(document: str, slug: str, anchor: str) -> bool:
    path = "/" if slug == "home" else "/" + slug + "/"
    for prefix in ('href="', 'href="https://kurashinoshirube.com'):
        if anchor and f'{prefix}{path}#{anchor}"' in document:
            return True
        if not anchor and (
            f'{prefix}{path}"' in document or f"{prefix}{path}#" in document
        ):
            return True
    return False


def validate_reader_roles(
    registry: dict[str, Any], documents: dict[str, str], catalog: dict[str, Any]
) -> list[str]:
    """Check each row's reader role against the public documents that carry it.

    `documents` maps article_key to the generated or tracked public body.
    A planned next question names the batch that owes the link.
    """
    rows = {row["article_key"]: row for row in registry["articles"]}
    published = {key for key, row in rows.items() if is_published(row)}
    models = {p["product_id"]: p["exact_model"] for p in catalog.get("products", [])}
    intents: dict[str, str] = {}
    issues: list[str] = []
    for key, row in rows.items():

        def issue(code: str, detail: str = "") -> None:
            issues.append(f"{code}: {key}" + (f" ({detail})" if detail else ""))

        role = row.get("reader_role")
        if (
            not isinstance(role, dict)
            or any(field not in role for field in ROLE_FIELDS)
            or not all(_text(role[field]) for field in ROLE_TEXT_LIMITS)
        ):
            issue("READER_ROLE_INCOMPLETE")
            continue
        kind = role["page_kind"]
        cta = role["main_cta"]
        question = role["next_question"]
        if (
            kind not in READER_PAGE_KINDS
            or set(role) - set(ROLE_FIELDS) - {"scope"}
            or ("scope" in role) != (kind == "task_guide")
            or any(len(role[f]) > limit for f, limit in ROLE_TEXT_LIMITS.items())
            or not isinstance(cta, dict)
            or set(cta) != {"kind", "target", "anchor", "label"}
            or not isinstance(question, dict)
            or set(question) != {"question", "target", "anchor", "status"}
            or not isinstance(cta["anchor"], str)
            or not isinstance(question["anchor"], str)
        ):
            issue("READER_ROLE_INVALID")
            continue
        if role["primary_intent"] in intents:
            issue("READER_PRIMARY_INTENT_DUPLICATE", intents[role["primary_intent"]])
        intents.setdefault(role["primary_intent"], key)
        if key not in published:
            continue
        document = documents.get(key, "")
        if cta["kind"] == "none":
            if cta["target"] is not None or cta["anchor"] or cta["label"]:
                issue("READER_ROLE_INVALID")
        elif cta["kind"] not in {"offer", "internal"}:
            issue("READER_ROLE_INVALID")
        elif not _text(cta["label"]):
            issue("READER_ROLE_INCOMPLETE")
        elif cta["kind"] == "offer":
            if (
                kind not in COMPARISON_PAGE_KINDS
                or cta["target"] is not None
                or cta["anchor"] not in ID_ATTRIBUTE.findall(document)
                or not SPONSORED.search(document)
            ):
                issue("READER_MAIN_CTA_OFFER_INVALID")
        elif cta["target"] is None:
            if kind not in COLLECTION_PAGE_KINDS:
                issue("READER_MAIN_CTA_TARGET_INVALID")
        elif cta["target"] == key or cta["target"] not in published:
            issue("READER_MAIN_CTA_TARGET_INVALID")
        elif not _linked(document, rows[cta["target"]]["slug"], cta["anchor"]):
            issue("READER_MAIN_CTA_UNLINKED", cta["target"])
        target = question["target"]
        status = question["status"]
        if not _text(question["question"]):
            issue("READER_ROLE_INCOMPLETE")
        elif target == key or target not in published:
            issue("READER_NEXT_QUESTION_TARGET_INVALID")
        else:
            linked = _linked(document, rows[target]["slug"], question["anchor"])
            if status == "live":
                if not linked:
                    issue("READER_NEXT_QUESTION_UNLINKED", target)
            elif (
                isinstance(status, str)
                and status.startswith("planned:")
                and status.removeprefix("planned:") in PLANNED_BATCHES
            ):
                if linked:
                    issue("READER_NEXT_QUESTION_ALREADY_LIVE", target)
            else:
                issue("READER_NEXT_QUESTION_STATUS_INVALID")
        if kind == "task_guide":
            scope = role["scope"]
            if (
                not isinstance(scope, dict)
                or set(scope) != {"primary_product_ids", "reference_product_ids"}
                or not all(isinstance(ids, list) for ids in scope.values())
            ):
                issue("READER_ROLE_INVALID")
                continue
            text = re.sub(r"<[^>]+>", " ", document)
            for product_id in (
                scope["primary_product_ids"] + scope["reference_product_ids"]
            ):
                model = models.get(product_id)
                if model is None or model not in text:
                    issue("READER_SCOPE_MODEL_MISSING", product_id)
    return issues
