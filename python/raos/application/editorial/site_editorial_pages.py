"""Public-safe entry pages projected from article identity and comparison records.

Editorial dates are explicit facts: never inferred from file, WP, or price timestamps.
"""

from __future__ import annotations

from html import escape
import re
from typing import Any, cast

from raos.application.editorial.reader_html import Element, fragment

PURPOSES = {
    "small-space": (
        "一人暮らし・省スペース",
        "どこを測れば候補を絞れる？",
        "本体・可動部・周囲空間を分けて採寸します。",
        [262, 86, 30, 85],
    ),
    "save-housework": (
        "家事を短くしたい",
        "家電に任せても残る作業は？",
        "洗い物と床掃除で、準備・片づけ・手入れを比べます。",
        [41, 263, 265, 266, 30, 85],
    ),
    "without-installation": (
        "工事なしの食洗機",
        "タンクとポンプ給水、続けやすいのは？",
        "タンク式と外部容器からのポンプ給水を、水運び・容器の置き場所・設置条件で比べます。",
        [262, 263, 41, 86],
    ),
    "easy-maintenance": (
        "手入れを続けやすいものを選びたい",
        "自分に残る作業と部品代は？",
        "食洗機・掃除機・スーツケースごとに確認できます。",
        [264, 265, 266, 41, 30, 85, 84, 19],
    ),
    "comfortable-travel": (
        "旅行の荷物・移動を楽にしたい",
        "旅のどの場面で困る？",
        "階段・車内・保安検査・宿・帰路の荷物で考えます。",
        [82, 83, 84, 19],
    ),
    "prepare-outage": (
        "停電に備えたい",
        "手持ちの備えで足りる？",
        "使う機器・必要時間・場所から、買い足す必要を考えます。",
        [28, 29],
    ),
}


def link(url: str, text: str) -> str:
    return f'<a href="{escape(url, quote=True)}">{escape(text)}</a>'


def table(headers: list[str], rows: list[list[str]]) -> str:
    return (
        '<div class="ks-editorial-table" role="region" aria-label="確認項目の表" tabindex="0"><table><thead><tr>'
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


def metadata(
    registry: dict[str, Any],
    catalog: dict[str, Any],
    data: dict[str, Any],
    bodies: dict[str, str],
) -> dict[str, Any]:
    comparisons = {
        a["slug"]: a for a in catalog["articles"] if a.get("kind") == "comparison"
    }
    products = {p["product_id"]: p for p in catalog["products"]}
    result = {}
    for row in registry["articles"]:
        # New owner-direct drafts have no verified publication identity yet.
        # They can be previewed without entering published lists or counts.
        if row["post_type"] != "post" or row.get("mode") == "new":
            continue
        own = data["articles"].get(str(row["post_id"]))
        if own is None:
            raise ValueError(f"Missing editorial category: {row['slug']}")
        item = dict(
            own,
            slug=row["slug"],
            post_id=row["post_id"],
            title=row["title"],
            excerpt=row.get("excerpt", ""),
        )
        article = comparisons.get(row["slug"])
        if article:
            item.update(
                title=article["title"], excerpt=article.get("excerpt", item["excerpt"])
            )
        product_ids = article.get("product_ids", []) if article else []
        refs = (
            article.get(
                "supplementary_product_ids", article.get("reference_product_ids", [])
            )
            if article
            else []
        )
        item["comparison_count"] = len(product_ids)
        item["reference_count"] = len(refs)
        item["models"] = [products[p]["exact_model"] for p in product_ids]
        item["comparison_anchor"] = (
            "ps-specs" if article else own.get("comparison_anchor")
        )
        item["has_ads"] = bool(
            re.search(
                r'rel=["\'][^"\']*sponsored|https://(?:a|hb)\.rakuten\.co\.jp|data-affiliate',
                bodies.get(row["slug"], ""),
                re.I,
            )
        )
        for key in ("published_on", "updated_on"):
            if item.get(key) is not None and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", item[key]
            ):
                raise ValueError("Invalid editorial date")
        result[row["slug"]] = item
    return result


def render_pages(
    registry: dict[str, Any],
    catalog: dict[str, Any],
    data: dict[str, Any],
    bodies: dict[str, str],
    home_media: dict[int, str] | None = None,
    page_sources: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, Any], list[dict[str, str]]]:
    meta = metadata(registry, catalog, data, bodies)
    by_id = {a["post_id"]: a for a in meta.values()}
    pages = {}
    updates = []

    def article_url(pid: int, anchor: str = "") -> str:
        return (
            "/" + cast(str, by_id[pid]["slug"]) + "/" + ("#" + anchor if anchor else "")
        )

    def card(pid: int, label: str = "", anchor: str = "", summary: str = "") -> str:
        a = by_id[pid]
        badge = (
            '<span class="ks-pr-badge">PR・広告リンクあり</span>'
            if a["has_ads"]
            else '<span class="ks-card-kind">広告リンクなし</span>'
        )
        count = (
            f"主比較{a['comparison_count']}製品"
            if a["comparison_count"]
            else "ガイド記事"
        )
        if a["reference_count"]:
            count += f"・別構成{a['reference_count']}件"
        date = (
            "内容更新日：" + escape(a["updated_on"])
            if a.get("updated_on")
            else "内容更新日：未確認"
        )
        return (
            '<article class="ks-editorial-card">'
            + badge
            + f'<h3>{link(article_url(pid, anchor), label or a["title"])}</h3><p>{escape(summary or a["excerpt"])}</p><p class="ks-card-meta">{count} ／ {date}</p></article>'
        )

    def cards(ids: list[int]) -> str:
        return '<div class="ks-route-grid">' + "".join(card(i) for i in ids) + "</div>"

    def category_cards(home: bool = False) -> str:
        reps = {"travel": 83, "kitchen": 41, "cleaning": 30, "preparedness": 28}
        guides = {
            "travel": (82, "ps-choose"),
            "kitchen": (262, "guide-measurement-steps"),
            "cleaning": (30, "ps-choose"),
            "preparedness": (28, "ps-decision-steps"),
        }
        out = ""
        for slug, cat in data["categories"].items():
            ids = [a["post_id"] for a in meta.values() if a["category"] == slug]
            ads = sum(by_id[i]["has_ads"] for i in ids)
            pid, anchor = guides[slug]
            category_link = link("/" + slug + "/", "カテゴリを見る")
            legacy = {
                "travel": "cluster-mobility",
                "kitchen": "cluster-home",
                "preparedness": "cluster-ready",
            }
            if home and slug in legacy:
                category_link = category_link.replace(
                    "<a ", f'<a id="{legacy[slug]}" ', 1
                )
            if home:
                label_link = category_link.replace(
                    "カテゴリを見る", escape(cat["name"])
                )
                out += (
                    '<article class="ks-editorial-card"><h3>'
                    + label_link
                    + "</h3></article>"
                )
                continue
            out += f'<article class="ks-editorial-card"><h3>{escape(cat["name"])}</h3><p>{len(ids)}記事・広告リンクを含む記事 {ads}本</p><ul><li>{category_link}</li><li>{link(article_url(reps[slug]), "代表比較を読む")}</li><li>{link(article_url(pid, anchor), "採寸・条件整理")}</li></ul></article>'
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
        return (
            '<div class="ks-route-grid">'
            + "".join(
                f'<article class="ks-editorial-card"><h3>{link("/" + slug + "/", p[0])}</h3><p>{escape(p[1])}</p><p>{escape(p[2])}</p><small>関連 {len([i for i in p[3] if i in by_id])}記事</small></article>'
                for slug, p in PURPOSES.items()
            )
            + "</div>"
        )

    def section(title: str, content: str, anchor: str = "") -> str:
        return (
            "<section"
            + (f' id="{anchor}"' if anchor else "")
            + f"><h2>{escape(title)}</h2>{content}</section>"
        )

    def al(pid: int, text: str, anchor: str = "") -> str:
        return link(article_url(pid, anchor), text)

    flight = (
        "<p>まず利用する運航会社・便・機材を確認します。通常の便、小型機、LCCで条件は共通ではありません。各辺・3辺合計・荷物込み重量・個数・拡張状態を照合します。</p><p>"
        + al(82, "小型機の寸法条件を比べる")
        + " ／ "
        + al(83, "通常サイズの軽さを比べる")
        + "</p><p>会社別の規定と確認日は各比較記事の公式出典へ。一般的な「機内持ち込み対応」の表示だけでは搭乗便への適合を保証しません。</p>"
    )
    for slug, page in data["pages"].items():
        title = PURPOSES[slug][0] if slug in PURPOSES else page["title"]
        body = ""
        if slug == "home":

            def feature(pid: int, image_category: str, caption: str) -> str:
                label = data["categories"][image_category]["name"]
                destination = "/" + image_category + "/"
                label_link = link(destination, label)
                legacy_anchor = {
                    "kitchen": "cluster-home",
                    "travel": "cluster-mobility",
                    "preparedness": "cluster-ready",
                }.get(image_category)
                if legacy_anchor:
                    label_link = label_link.replace(
                        "<a ", f'<a id="{legacy_anchor}" ', 1
                    )
                markup = (
                    '<article class="ks-editorial-card"><h3>'
                    + label_link
                    + "</h3></article>"
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
                if home_media and pid in home_media:
                    media = (
                        '<div class="ks-home-product-images">'
                        + home_media[pid]
                        + "</div>"
                    )
                return markup.replace(
                    '<article class="ks-editorial-card">',
                    '<article class="ks-editorial-card">' + media,
                    1,
                )

            body = (
                '<section class="ks-home-feature"><div class="ks-home-masthead"><div class="ks-home-intro"><p class="km-tag">暮らしの道具を、納得して選ぶ</p><h1 id="km-hero-title">あなたの暮らしに、<br>合うものを。</h1><p>置き場所と使い方から、道具を選ぶ。</p></div><figure class="ks-home-mood"><img src="/wp-content/themes/kurashinoshirube-child/assets/images/home-lifestyle-20260913.webp" width="1672" height="941" fetchpriority="high" alt="朝の光が差す一人暮らしのキッチンと食卓のAI編集イメージ"></figure></div><section id="km-categories-title"><h2 id="km-articles-title">商品カテゴリー</h2><div class="ks-home-feature-grid ks-home-category-grid">'
                + feature(41, "kitchen", "食器と食洗機のあるキッチンのイメージ")
                + feature(83, "travel", "スーツケースと衣類を揃えた旅支度のイメージ")
                + feature(30, "cleaning", "ロボット掃除機を置いた部屋のイメージ")
                + feature(
                    28, "preparedness", "ポータブル電源とランタンを並べた備えのイメージ"
                )
                + "</div></section></section>"
            )
            recent = sorted(
                (a for a in meta.values() if a.get("published_on")),
                key=lambda a: (a["published_on"], a["post_id"]),
                reverse=True,
            )[:4]

            def recent_image(article: dict[str, Any]) -> str:
                image = data.get("home_article_images", {}).get(str(article["post_id"]))
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
                    + article_url(a["post_id"])
                    + '">'
                    + recent_image(a)
                    + "</a><h3>"
                    + link(
                        article_url(a["post_id"]),
                        data["home_short_titles"].get(str(a["post_id"]), a["title"]),
                    )
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
                "<p>商品名が決まっていれば代表比較へ。置き場所や条件が不安なら採寸・条件整理へ進めます。</p>"
                + category_cards()
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
                for a in meta.values():
                    if a["category"] != category or not a["comparison_count"]:
                        continue
                    contents += (
                        card(a["post_id"])
                        + "<p>"
                        + al(a["post_id"], "比較表へ", a["comparison_anchor"])
                        + " ／ "
                        + al(a["post_id"], "販売条件へ", "ps-offers")
                        + "</p>"
                    )
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
                    card(pid, label)
                    for pid, label in [
                        (262, "置き場所を測る"),
                        (263, "給水作業を比べる"),
                        (264, "専用洗剤と量を確かめる"),
                        (265, "型番別の清掃を確かめる"),
                        (266, "1回・月額を試算する"),
                    ]
                )
                + "</div>",
            )
            body += section(
                "比較記事の選び方：採寸と条件整理はこちら",
                '<div class="ks-route-grid">'
                + card(83, "荷物の重さを数える", "ps-choose")
                + card(30, "本体・台・帰還経路を測る", "ps-choose")
                + card(28, "機器と必要時間を整理する", "ps-decision-steps")
                + "</div>",
            )
        elif slug == "updates":
            title = "新着・内容を更新した記事"
            body = "<p>公開日、実質的な本文更新日、仕様確認日、販売条件の確認日時は別に管理します。誤字・見た目の修正や価格だけの再取得では内容更新日を進めません。</p>"
            for a in sorted(
                meta.values(),
                key=lambda a: (a.get("updated_on") or "", a["post_id"]),
                reverse=True,
            ):
                body += (
                    card(
                        a["post_id"],
                        summary=a.get("change_summary")
                        or "実質的な本文変更履歴は未確認です。",
                    )
                    + "<p>公開日："
                    + escape(a.get("published_on") or "未確認")
                    + " ／ "
                    + ("内容を更新" if a.get("updated_on") else "内容更新の記録未確認")
                    + "</p>"
                )
        elif slug == "travel":
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
                    "<li>" + al(pid, label, "ps-specs") + "</li>"
                    for pid, label in [
                        (82, "小型機の寸法条件を比較表で確認する"),
                        (83, "本体の軽さを比較表で確認する"),
                        (84, "前面収納とストッパーを比較表で確認する"),
                        (19, "容量・拡張・車輪の違いを比較表で確認する"),
                    ]
                )
                + "</ul>"
                + cards([82, 83, 84, 19])
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
                    + al(30, "機種別の寸法と余白を見る", "ps-specs"),
                )
                + section(
                    "構成の違いで比較する",
                    table(
                        ["構成", "比較先"],
                        [
                            [
                                "小さい台＋自動収集の2候補",
                                al(85, "Mini + AutoEmpty / K11+ Pro"),
                            ],
                            ["充電台のみ", al(85, "Mini Slim + SlimCharge")],
                            ["掃除機収納の統合", al(30, "K10+ Pro Combo")],
                            [
                                "水拭きの手入れ自動化",
                                al(30, "Roomba Plus 515 Combo + AutoWash"),
                            ],
                        ],
                    ),
                )
                + cards([30, 85])
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
                    + al(28, "必要Whの計算例へ", "ps-decision-steps"),
                )
                + cards([28, 29])
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
                    card(262, "食洗機の置き場所を測る")
                    + card(86, "本体寸法と開扉時寸法を別々に比較する"),
                )
                + section(
                    "床に置く",
                    card(30, "本体・台・帰還経路を測る", "ps-specs") + card(85),
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
                + section("洗い物を減らす", card(41) + al(265, "型番別の清掃頻度へ"))
                + section("床掃除を任せる", cards([30, 85]))
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
            ) + cards([262, 263, 41, 86])
        elif slug == "easy-maintenance":
            body = "<p>頻度は型番別の公式指定を優先します。毎回・週次・汚れに応じて・交換通知時などを共通の月次作業へ置き換えません。</p>"
            for label, ids, work in [
                ("食洗機", [265, 264, 266], "フィルター・ノズル・洗剤"),
                ("掃除機", [30, 85], "紙パック・ブラシ・フィルター・モップ"),
                ("スーツケース", [84, 19], "車輪・鍵・外装"),
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
                    + cards(ids),
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
                                al(83, "本体の軽さを比較"),
                            ],
                            ["車内", "立てたまま取り出す物", al(84, "前面収納を比較")],
                            [
                                "保安検査",
                                "取り出す順番と便の規定",
                                al(82, "小型機の制約"),
                            ],
                            ["宿", "開く場所と収納", al(19, "容量・開き方を比較")],
                            [
                                "帰路",
                                "増えた荷物と拡張後の外寸",
                                al(19, "拡張時の条件を確認"),
                            ],
                        ],
                    ),
                )
                + "<p>重視する条件で候補を絞り、便の規定・収納・予算を最後に照合します。手持ちの鞄で足りるなら買い足さない選択もあります。</p>"
            )
        elif slug == "prepare-outage":
            body = section(
                "停電時に不足する用途を整理する",
                table(
                    ["使う機器", "必要時間", "動かす場所・手持ちの備え"],
                    [
                        ["メモ：＿＿＿＿", "＿＿時間", "＿＿＿＿"],
                        ["メモ：＿＿＿＿", "＿＿時間", "＿＿＿＿"],
                    ],
                )
                + "<p>既に持つ充電手段や照明で必要な用途を満たせるなら、電源を買い足す必要はありません。住宅全体・医療機器への給電は対象外です。</p>",
            ) + section(
                "不足する用途がある場合",
                "<p>容量Wh、同時使用W、起動時の負荷、端子と機器メーカーの対応条件を別々に照合します。定格1000W・1500Wなどの階級だけで起動を保証しません。</p>"
                + cards([28, 29]),
            )
        elif slug == "kitchen":
            body = (
                section("買う前に", cards([262, 263, 41, 86]))
                + section("購入後に続ける作業", cards([264, 265, 266]))
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
                '</div><nav class="ks-home-more" aria-label="ほかの探し方"><a id="km-purposes-title" href="/purposes/">目的から探す</a><span id="home-purchase-check"> ／ <a id="home-purchase-check-title" href="/comparisons/#purchase-checks">購入前の確認</a></span></nav></section></section>',
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
                    al(a["post_id"], a["title"], "ps-offers")
                    for a in meta.values()
                    if a["category"] == slug and a["comparison_count"]
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
            body = body.replace("<section>", '<section id="kitchen-guides">', 1)
            for category, pid in [
                ("travel", 83),
                ("cleaning", 30),
                ("preparedness", 28),
            ]:
                marker = '<article class="ks-editorial-card">'
                target = body.index(
                    article_url(pid, "ps-decision-steps" if pid == 28 else "ps-choose")
                )
                pos = body.rfind(marker, 0, target)
                body = body[:pos] + body[pos:].replace(
                    marker,
                    f'<article id="{category}-guides" class="ks-editorial-card">',
                    1,
                )
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
            ids = [node.attrs["id"] for node in tree.walk() if node.attrs.get("id")]
            required = {*page["anchors"], "site-editorial-policy"}
            if (
                len(roots) != 1
                or len(ids) != len(set(ids))
                or not required.issubset(ids)
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
    return pages, meta, updates
