"""Reader-first additions using the same model-bound guide evidence as the tables."""

from collections.abc import Mapping, Sequence
from html import escape
from typing import Any

# Plastic heat limit, its course exception and the finish-damage reason, per exact
# manual. Shared by the answer-table summary and the per-model material table so
# the two cannot diverge. Only these four manuals establish the restrictions.
MATERIAL_LIMITS: dict[str, tuple[str, str, str]] = {
    "NP-TMLK1-K": (
        "80℃未満・表示なしは不可",
        "80℃以上でも食器側の食洗機対応表示を確認",
        "変色、塗装はがれ、白濁",
    ),
    "TDWS25SBL / TDWS25SRD": (
        "75℃未満・表示なしは不可",
        "75℃以上は使用可と記載。食器側の食洗機対応表示にも従う",
        "変形など",
    ),
    # SS-MA251 manual p.8 bans plastic below 90℃ and plastic without a heat label,
    # except 65℃ or higher in the soft course; p.25 bans plastic below 65℃.
    "SS-MA251": (
        "耐熱65℃未満・表示なしは不可",
        "65℃以上90℃未満はソフトコースで洗う",
        "変色など",
    ),
    # NP-TSP1 manual p.2 and p.7: plastic below 90℃ or without a heat label is banned,
    # except 60℃ to below 90℃ in 低温ソフト; 90℃ or higher suits every course.
    "NP-TSP1-W": (
        "耐熱60℃未満・表示なしは不可",
        "60℃以上90℃未満は低温ソフトで洗う",
        "変色、塗装はがれ、白濁",
    ),
}


def _source(product: Mapping[str, Any], field: str) -> str:
    facts = [f for f in product.get("guide_facts", []) if f["field"] == field]
    return " ／ ".join(
        '<a href="'
        + escape(f["source_url"], quote=True)
        + '">'
        + escape(f["locator"])
        + "</a>（確認 "
        + escape(f["checked_at"])
        + "）"
        for f in facts
    )


def _prohibited_summary(product: Mapping[str, Any]) -> str:
    """Main items that must not go in, keeping the plastic exception; full list per model."""
    limits = MATERIAL_LIMITS.get(product.get("exact_model"))
    if limits is None:
        return "未確認"
    limit, exception, _ = limits
    return (
        "強化ガラス、飛ばされやすい軽いもの。プラスチック："
        + escape(limit)
        + "（"
        + escape(exception)
        + '）ほか。<a href="#'
        + escape(product["anchor"], quote=True)
        + '">全項目と例外</a>'
    )


def render_guide_intro(stage: str, products: Sequence[Mapping[str, Any]]) -> str:
    if stage == "cost":
        return '<section class="ps-guide-answer" id="guide-cost-example"><h2>まず費用感を知る：仮の計算例</h2><p>以下は計算の説明用に置いた架空の条件で、特定機種の実測費用・推奨洗剤量・請求額ではありません。コースは特定しない計算練習です。</p><p>230Wh/回・2.5L/回、電気30円/kWh、上下水道300円/m³、洗剤5円/回、月30回と仮定すると、230÷1000×30＋2.5÷1000×300＋5＝<strong>12.65円/回</strong>、12.65×30＝<strong>379.5円/月</strong>です。</p><p><a href="/compact-dishwasher-comparison/#compact-cost">小型食洗機の比較</a>にあるSOLOTA・標準コースの計算例（約9.48円/回）は、電気31円/kWh・上下水道300円/m³・洗剤0.8円/g・2gという別の仮定による試算です。単価の仮定が違うため、この例の金額とは比べません。</p><p>実際の試算は下の型番別の公表コースを選びます。電気代が未確認の機種は、水道・洗剤の小計だけが分かり、合計は不明です。入力せずに公表条件と式を読むこともできます。</p></section>'
    if stage == "installation":
        return (
            '<section class="ps-guide-answer" id="guide-measurement-diagram"><h2>採寸する位置を3方向から確認</h2><p>編集者作成の模式図です。縮尺なし・実物の外観や設置実績を表す図ではありません。番号は下の採寸メモと対応し、機種の寸法・必要余白は比較表と公式出典で照合します。</p><div class="ps-guide-diagrams"><figure><figcaption>上面：①幅・②奥行・⑥背面余白・⑦左右余白</figcaption><pre>       壁\n    ↕ ⑥背面余白\n⑦ ↔ ┌────────┐ ↔ ⑦\n    │  本体  │ ↕②\n    └────────┘\n       ↔ ①幅\n       手前・扉側</pre></figure><figure><figcaption>正面：①幅・③高さ・⑤上方余白</figcaption><pre>     上棚\n     ↕⑤上方余白\n   ┌────────┐\n   │  本体  │ ↕③高さ\n   └────────┘\n   ━━━置き台━━━\n      ↔①幅</pre></figure><figure><figcaption>側面：④開扉時の必要範囲・⑧ホース経路</figcaption><pre>背面基準線\n│ ┌─────┐\n│ │本体 │  扉の動く範囲\n│ └─────┴ ┄ ┄ ┄\n│←───④開扉時奥行──→\n└⑧排水先への経路</pre></figure></div><p>④は背面から開いた扉の先端までの全体寸法で、本体奥行へもう一度足しません。上へ開く扉は開扉時高さも別に確認します。⑧の排水先・高さは型番ごとに異なります。</p><p><strong>NP-TSP1-W：</strong>メーカーの可燃物離隔は上115mm、別に設置面から720mm以上。本体600mmとの差120mmは入力照合用の計算値です。「メーカー指定120mm」ではありません。</p><p>'
            + "".join(
                _source(p, "clearance")
                for p in products
                if p["exact_model"] == "NP-TSP1-W"
            )
            + '</p><p class="ps-guide-print">採寸メモ（mm）：①幅＿＿ ②奥行＿＿ ③高さ＿＿ ④開扉時＿＿ ⑤上＿＿ ⑥後＿＿ ⑦左＿＿・右＿＿ ⑧排水先＿＿。未確認欄は空欄のまま残し、設置可と判定しません。印刷または紙への転記で使えます。</p></section>'
        )
    if stage == "detergent":
        rows = []
        for p in products:
            d = p.get("guide_summary", {}).get("detergent", {})
            position = d.get(
                "投入位置", "当該型番の説明書の洗剤投入図を確認（下の出典）"
            )
            amounts = (
                ("通常", d.get("通常量", "未確認")),
                ("汚れが多いとき", d.get("汚れが多いときの量", "未確認")),
                ("タブレット", d.get("タブレットの条件", "未確認")),
            )
            rows.append(
                '<tr><th scope="row"><a href="#'
                + escape(p["anchor"], quote=True)
                + '">'
                + escape(p["exact_model"])
                + "</a></th><td>"
                + escape(d.get("使える洗剤の種類", "未確認"))
                + '</td><td><ul class="ps-detergent-amounts">'
                + "".join(
                    "<li>" + escape(label) + "：" + escape(value) + "</li>"
                    for label, value in amounts
                )
                + "</ul></td><td>"
                + escape(position)
                + "</td><td>"
                + _prohibited_summary(p)
                + "</td></tr>"
            )
        return (
            '<section class="ps-guide-answer" id="guide-detergent-answer"><h2>型番から、専用洗剤と入れる場所を確認</h2><p><strong>手洗い用の台所用洗剤は使いません。</strong>下洗いに使った場合も十分にすすぎます。試験時の洗剤量は通常量とは別に、下の型番別根拠で確認できます。</p><div class="ps-table-scroll" tabindex="0" role="region" aria-label="洗剤の最初の答え"><table><caption>通常使用の案内。投入場所は給水口と別です</caption><thead><tr><th scope="col">型番</th><th scope="col">使える洗剤</th><th scope="col">1回の量</th><th scope="col">入れる位置</th><th scope="col">使えないもの（主なもの）</th></tr></thead><tbody>'
            + "".join(rows)
            + "</tbody></table></div><p>ラクアmini color（TDWS25SBL / TDWS25SRD）とmini Plus（TK-MDW22B / TK-STTDPSWH）は別機種です。色名・シリーズ名だけで説明書を共用しません。</p></section>"
        )
    if stage == "water":
        return '<section class="ps-guide-answer" id="guide-water-route"><h2>水を入れる作業と、排水先の固定は別です</h2><p>通常のタンク給水に洗剤を混ぜません。満水の合図で止める量と、特定コースで使う水量は区別します。タンク清掃時だけの指定クリーナー使用は<a href="/dishwasher-cleaning-guide/">型番別の清掃手順</a>に限る例外です。</p><p>タンク運用では分岐水栓の取り付け工事は不要でも、アースや排水先の確保が必要です。2WAY機の分岐水栓運用は、適合する水栓・給水ホース・設備条件・設定変更を下の型番別出典で確認します。</p></section>'
    return ""


def render_model_handout(stage: str, product: Mapping[str, Any]) -> str:
    if stage == "detergent":
        return render_material_table(product)
    if stage == "water":
        summary = product.get("guide_summary", {}).get("water", {})
        values = [
            summary.get(k, "未確認")
            for k in ("給水方式", "1回の給水量と止める合図", "排水ホース")
        ]
        return (
            '<figure class="ps-water-route"><figcaption>'
            + escape(product["exact_model"])
            + " の給排水経路（縮尺なしの説明図・適合設置例ではありません）</figcaption><ol><li>給水元 → "
            + escape(values[0])
            + "</li><li>満水確認 → "
            + escape(values[1])
            + "</li><li>本体 → 排水ホース → 排水先："
            + escape(values[2])
            + "</li></ol><p>"
            + _source(product, "water_supply")
            + " ／ "
            + _source(product, "drainage")
            + "</p></figure>"
        )
    if stage == "maintenance":
        facts = [
            f for f in product.get("guide_facts", []) if f["field"] == "maintenance"
        ]
        return (
            '<details class="ps-guide-print"><summary>'
            + escape(product["exact_model"])
            + " の印刷・作業用チェック欄</summary><p>印刷するときはこの欄を開いてください。ブラウザの印刷機能から紙に残せます。作業時間は実測していません。</p><ul>"
            + "".join("<li>□ " + escape(f["text"]) + "</li>" for f in facts)
            + '</ul><p>通常給水ではタンクに洗剤を入れません。清掃時の例外は、この型番に記載された手順だけです。<a href="/dishwasher-water-supply-methods/#'
            + escape(product["anchor"], quote=True)
            + '">同じ型番の通常給水へ</a></p></details>'
        )
    return ""


def render_material_table(product: Mapping[str, Any]) -> str:
    """Only the four exact manuals below establish these material restrictions."""
    model = product.get("exact_model")
    if model not in MATERIAL_LIMITS:
        return ""
    limit, exception, finish_reason = MATERIAL_LIMITS[model]
    rows = [
        (
            "強化ガラス",
            "粉々に割れ、破片が飛び散ってけがをするおそれ",
            "入れない。耐熱ガラスと同一視しない",
        ),
        ("プラスチック食器", "熱による変形", limit + "。" + exception),
        (
            "軽いふた・スプーン、ふきん・スポンジなど",
            "噴射水で飛び、変形・破損等のおそれ",
            "食器側が対応でも、飛ばされやすい軽いものは入れない",
        ),
        (
            "銀・洋銀・アルミ・銅、木・竹・とう、漆・金箔・上絵、クリスタル",
            finish_reason,
            "原典の洗えないものに該当。汚れを落とすコース変更で許可されるとは扱わない",
        ),
        (
            "傷やひびのある食器、木製の柄の鍋",
            "破損のおそれ",
            "入れない。傷やひびの状態も確認する",
        ),
        (
            "鉄製フライパン、傷のあるフッ素加工品",
            "さびや表面加工のはがれのおそれ",
            "入れない。無傷なら一律使用可という意味ではない",
        ),
        ("口の狭いびん・徳利", "内側が洗えない", "食洗機の洗浄対象にしない"),
    ]
    if model in {"SS-MA251", "TDWS25SBL / TDWS25SRD"}:
        rows[-2] = (
            rows[-2][0],
            "鉄はさびのおそれ。傷のある加工品の個別理由は原典に記載なし",
            rows[-2][2],
        )
        rows[-1] = (
            rows[-1][0],
            "原典は洗えないものに列挙（個別理由は未記載）",
            rows[-1][2],
        )
    source = _source(product, "prohibited") or _source(product, "detergent")
    return (
        '<details class="ps-material-guide"><summary>'
        + escape(model)
        + '：材質・禁止の理由・コースの例外</summary><p>次は原典の禁止事項を材質別に整理した表です。洗剤メーカーと食器側の表示にも従い、記載のない材質を自動的に使用可とは判断しません。</p><div class="ps-table-scroll" tabindex="0" role="region" aria-label="材質と禁止理由"><table><caption>'
        + escape(model)
        + 'の食器を入れる前の確認</caption><thead><tr><th scope="col">材質・状態</th><th scope="col">禁止・制限の理由</th><th scope="col">対象・例外</th></tr></thead><tbody>'
        + "".join(
            '<tr><th scope="row">'
            + escape(a)
            + "</th><td>"
            + escape(b)
            + "</td><td>"
            + escape(c)
            + "</td></tr>"
            for a, b, c in rows
        )
        + '</tbody></table></div><p class="ps-source">'
        + source
        + "</p></details>"
    )
