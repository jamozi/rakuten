from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "changes/wordpress-local-preview-v1/fixtures"
ARTICLES = FIXTURES / "articles"
LATER_SLUGS = (
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)
LATER_DECISION_AND_PRODUCTS = {
    "carry-on-suitcase-under-100-seats": (
        "under-100-decision-title",
        (
            ("PRD-PROTECA-STARIA-CXR-02350", "staria-cxr-02350"),
            ("PRD-PROTECA-FRESTER-EX-01550", "frester-ex-01550"),
            ("PRD-ACE-PALISADES3-Z-06910", "palisades3-z-06910"),
            ("PRD-BERMAS-INTER-CITY-60524", "bermas-inter-city-60524"),
        ),
    ),
    "lightweight-carry-on-suitcase-under-3kg": (
        "under-3kg-decision-title",
        (
            ("PRD-PROTECA-AEROFLEX-DX2-01521", "aeroflex-dx2-01521"),
            ("PRD-PROTECA-TRI-AIR-01541", "tri-air-01541"),
            (
                "PRD-RIMOWA-ESSENTIAL-LITE-CABIN-82353171",
                "rimowa-essential-lite-cabin-82353171",
            ),
            (
                "PRD-AMERICAN-TOURISTER-APPLITE-4-QJ6-68002",
                "american-tourister-applite-qj6-68002",
            ),
            (
                "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549",
                "samsonite-c-lite-spinner55exp-134679-1549",
            ),
        ),
    ),
    "front-open-carry-on-suitcase-with-stopper": (
        "decision-title",
        (
            ("PRD-INNOVATOR-INV50", "innovator-inv50"),
            ("PRD-ACE-DIFFERENCE-05721", "ace-difference-05721"),
            ("PRD-PROTECA-FRESTER-EX-01551", "proteca-frester-ex-01551"),
            ("PRD-BERMAS-INTER-CITY-III-60570", "bermas-inter-city-iii-60570"),
        ),
    ),
    "roomba-mini-vs-switchbot-k11-pro": (
        "robot-decision-title",
        (
            ("PRD-EUFY-AUTOEMPTY-C10-T2292", "eufy-autoempty-c10-t2292511"),
            ("PRD-SWITCHBOT-K11-PRO", "switchbot-k11-pro"),
            (
                "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060",
                "roomba-mini-slim-f115060",
            ),
            ("PRD-ECOVACS-DEEBOT-MINI2", "deebot-mini2"),
        ),
    ),
}


def _markup(slug: str) -> str:
    return (ARTICLES / f"{slug}.html").read_text(encoding="utf-8")


def _section(markup: str, section_id: str) -> str:
    start = markup.index(f'aria-labelledby="{section_id}"')
    end = markup.find('<section class="', start + 1)
    if end == -1:
        end = markup.find("<aside ", start + 1)
    assert end != -1
    return markup[start:end]


def test_later_five_keep_existing_posts_products_and_cta_slots() -> None:
    fixture = json.loads((FIXTURES / "posts.json").read_text(encoding="utf-8"))
    posts = fixture["posts"]

    assert fixture["seed_version"] == "2026-08-31.1"
    assert len(posts) == 10
    assert {row["slug"] for row in posts if row["slug"].removeprefix("local-preview-") in LATER_SLUGS} == {
        f"local-preview-{slug}" for slug in LATER_SLUGS
    }

    all_markup = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(ARTICLES.glob("*.html"))
    )
    assert len(re.findall(r'<article\b[^>]*class="[^"]*\bproduct-profile\b', all_markup)) == 37
    assert len(re.findall(r'<a\b[^>]*class="[^"]*\braos-cta\b', all_markup)) == 74


def test_front_open_article_applies_the_100_plus_seat_rule_to_each_state() -> None:
    markup = _markup("front-open-carry-on-suitcase-with-stopper")

    assert "幅40×奥行25×高さ55cm以内、かつ3辺合計115cm以内" in markup
    assert "通常時115cm" in markup
    assert "拡張時118cm（比較対象外）" in markup
    assert "拡張時119cm（比較対象外）" in markup
    assert "拡張状態は機内持ち込み候補から除外します" in markup
    assert "3ROOM（3室）" in markup
    assert "3room" not in markup
    assert "PRD-BERMAS-INTER-CITY-III-60570" in markup
    assert 'data-raos-product-id="PRD-BERMAS-INTER-CITY-II-60561"' not in markup
    assert "INTER CITY II 60561" in markup
    assert "掲載外であることは性能の劣位や終売を意味しません" in markup
    assert (
        "楽天市場の商品同一性・画像の照合を完了していないため、公式リンクのみ掲載"
        in markup
    )
    assert markup.count("一致する楽天商品を確認できなかったため") == 4
    assert "モバイルバッテリー" not in markup
    assert re.search(
        r"通常時寸法（幅×奥行×高さ）.*?35×25×55cm.*?36×24×55cm.*?"
        r"37×23×55cm.*?36×24×54cm",
        markup,
        re.DOTALL,
    )
    assert re.search(
        r"3辺合計.*?通常時115cm.*?通常時115cm.*?通常時115cm.*?通常時114cm",
        markup,
        re.DOTALL,
    )


def test_front_open_bermas_swap_is_identity_complete_and_rakuten_fail_closed() -> None:
    portfolio = json.loads(
        (ROOT / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_text(
            encoding="utf-8"
        )
    )
    sales = json.loads(
        (
            ROOT
            / "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
        ).read_text(encoding="utf-8")
    )
    identities = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/editorial-identities.v1.json"
        ).read_text(encoding="utf-8")
    )
    market = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
        ).read_text(encoding="utf-8")
    )
    new_id = "PRD-BERMAS-INTER-CITY-III-60570"
    old_id = "PRD-BERMAS-INTER-CITY-II-60561"

    product = next(row for row in portfolio["products"] if row["product_id"] == new_id)
    article = next(
        row
        for row in portfolio["articles"]
        if row["article_id"] == "front-open-carry-on-suitcase-with-stopper"
    )
    sales_row = next(row for row in sales["products"] if row["product_id"] == new_id)
    market_article = next(
        row
        for row in market["articles"]
        if row["article_id"] == "front-open-carry-on-suitcase-with-stopper"
    )
    old_candidate = next(
        row
        for row in market_article["considered_external_candidates"]
        if row["candidate_id"] == "EXT-BERMAS-INTER-CITY-II-60561"
    )

    assert product["official_name"] == "BERMAS INTER CITY III 60570"
    assert product["rakuten_shop_code"] is None
    assert product["rakuten_item_code"] is None
    assert new_id in article["product_ids"]
    assert old_id not in {row["product_id"] for row in portfolio["products"]}
    assert old_id not in article["product_ids"]
    assert {row["product_id"]: row["product_code"] for row in identities["products"]}[
        new_id
    ] == "p29"
    assert sales_row["state"] == "AVAILABLE"
    assert sales_row["availability_scope"] == "MODEL"
    assert sales_row["variant_caveat"]["establishes_exact_rakuten_variant"] is False
    assert new_id in market_article["selected_product_ids"]
    assert old_candidate["effective_lifecycle"] == "AVAILABLE"
    assert old_candidate["disposition"] == "EXCLUDED"


def test_robot_copy_uses_four_current_setups_without_repeating_caveats() -> None:
    fixture = json.loads((FIXTURES / "posts.json").read_text(encoding="utf-8"))
    post = next(
        row
        for row in fixture["posts"]
        if row["slug"] == "local-preview-roomba-mini-vs-switchbot-k11-pro"
    )
    markup = _markup("roomba-mini-vs-switchbot-k11-pro")
    reader_copy = markup.split('<section class="sources-section"', maxsplit=1)[0]
    note = re.search(r'<p class="table-note">(.*?)</p>', reader_copy, re.DOTALL)
    card = re.search(
        r'<article id="switchbot-k11-pro".*?</article>', reader_copy, re.DOTALL
    )

    assert "本体単品" not in post["excerpt"]
    assert "Eufy Auto-Empty C10" in post["excerpt"]
    assert "Roomba Mini Slim" in post["excerpt"]
    assert "現行4構成" in markup
    assert "2製品3構成" not in markup
    assert "販売終了状況" not in markup
    assert "在庫切れ／販売状態の確認内容" in markup
    assert "Eufy C10のブラックT2292511への入替" in markup
    assert "同型番・同色の現行販売状態" in markup
    assert note is not None
    assert card is not None
    assert "最大12,000Pa" in note.group(1)
    assert "左右各1m・前方1.5m" in note.group(1)
    assert "最大12,000Pa" in card.group(0)
    assert "左右各1m・前方1.5m" in card.group(0)
    copy_outside_allowed = reader_copy.replace(note.group(0), "").replace(
        card.group(0), ""
    )
    assert "12,000Pa" not in copy_outside_allowed
    assert "左右各1m・前方1.5m" not in copy_outside_allowed


def test_legacy_dishwasher_copy_is_lifecycle_only_and_routes_to_current_guide() -> None:
    markup = _markup("solota-vs-rakua-mini-plus")
    assert (
        'class="lead-section" '
        'data-raos-article-id="solota-vs-rakua-mini-plus"'
    ) in markup
    post = next(
        row
        for row in json.loads((FIXTURES / "posts.json").read_text(encoding="utf-8"))[
            "posts"
        ]
        if row["article_id"] == "local-preview-solota-vs-rakua-mini-plus"
    )
    assert post["title"] == "SOLOTA・ラクアmini Plusの販売状況｜現行比較への案内"
    assert post["category"] == "家事"
    assert "ラクアmini Plusは再入荷通知のみ" in post["excerpt"]
    assert "旧SOLOTAは正確な対象型番の販売状態を確認できず" in post["excerpt"]
    assert "両機種を仕様参考に限定" in post["excerpt"]
    assert "少人数向け卓上食洗機4候補の記事へ案内" in post["excerpt"]
    assert "記事分類" in markup
    assert "この記事で答えること" in markup
    assert "THANKO ラクアmini Plus" in markup
    assert "再入荷通知だけが表示" in markup
    assert "メーカー公式で売り切れを確認" not in markup
    assert "メーカー公式で再入荷通知のみを確認" in markup
    assert "購入候補・商品カード・購入導線から外しました" in markup
    assert "アイリスオーヤマ ISHT-5000-W" not in markup
    assert "旧候補の販売状態と現行比較への案内" in markup
    assert "市場全体の順位ではありません" in markup
    assert "/countertop-dishwasher-for-small-households/" in markup
    assert (
        markup.count(
            '<a href="/countertop-dishwasher-for-small-households/">'
            "関連する比較記事を確認する</a>"
        )
        == 1
    )
    assert markup.count("同じ比較記事で確認できます。") == 3
    assert "A04" not in markup
    assert "現行4候補の比較" in markup
    assert "PRD-THANKO-RAKUA-MINI-PLUS-TK-MDW22B" not in markup
    assert "PRD-PANASONIC-SOLOTA-NP-TML1-W" not in markup
    assert "通常商品SS-MA251（シルバー）" in markup
    assert "仕様表、個別の選定理由" in markup
    assert 'data-raos-product-id="' not in markup
    assert 'class="raos-cta' not in markup
    assert "dish-running-cost-title" not in markup
    assert "後継機です" not in markup
    assert "後継モデル" not in markup
    assert "後継・同等品とは断定しません" in markup
    assert "drop-in" not in markup


def test_legacy_dishwasher_intent_is_resolved_in_the_opening() -> None:
    markup = _markup("solota-vs-rakua-mini-plus")
    lead_start = markup.index('<div class="lead-copy">')
    first_paragraph = re.search(r"<p>(.*?)</p>", markup[lead_start:], re.DOTALL)
    post = next(
        row
        for row in json.loads((FIXTURES / "posts.json").read_text(encoding="utf-8"))[
            "posts"
        ]
        if row["article_id"] == "local-preview-solota-vs-rakua-mini-plus"
    )

    assert first_paragraph is not None
    assert "このURLで以前比較していたTHANKO ラクアmini Plus" in first_paragraph.group(1)
    assert "公式ストアで再入荷通知のみ" in first_paragraph.group(1)
    assert "SOLOTA NP-TML1-Wは正確な白色型番の販売状態を確認できません" in first_paragraph.group(1)
    assert "両機種は仕様参考に限定し、購入候補・商品カード・購入導線から外しました" in first_paragraph.group(1)
    assert "現行比較へ迷わず移る" in markup
    assert "THANKO ラクアmini TK-MDW22W" in markup
    assert "siroca SS-M171" in markup
    assert "公式ストア通常商品SS-MA251（シルバー）" in markup
    assert post["excerpt"].startswith(
        "旧SOLOTAは正確な対象型番の販売状態を確認できず"
    )


def test_later_five_show_proof_before_external_final_summary_actions() -> None:
    for slug, (decision_title, products) in LATER_DECISION_AND_PRODUCTS.items():
        markup = _markup(slug)
        decision = _section(markup, decision_title)
        final_actions_start = markup.index('<div class="raos-final-summary-actions"')
        product_details_start = min(markup.index(f'<article id="{target}"') for _, target in products)
        final_actions_end = markup.index("</section>", final_actions_start)
        final_actions = markup[final_actions_start:final_actions_end]

        assert 'data-raos-placement="final_summary"' not in decision, slug
        assert final_actions_start > product_details_start, slug
        assert final_actions.count('data-raos-placement="final_summary"') == len(products), slug
        for product_id, target in products:
            assert f'href="#{target}"' in decision, (slug, target)
            assert final_actions.count(f'data-raos-product-id="{product_id}"') == 2, (
                slug,
                product_id,
            )


def test_later_five_use_japanese_labels_specific_headings_and_consistent_terms() -> None:
    markups = [_markup(slug) for slug in LATER_SLUGS]
    headings: list[str] = []
    for markup in markups:
        headings.extend(
            re.sub(r"<[^>]+>", "", heading).strip()
            for heading in re.findall(r"<h2\b[^>]*>(.*?)</h2>", markup, re.DOTALL)
        )
        assert "SPECIFICATIONS CHECKED" not in markup

    assert len(headings) == len(set(headings))
    posts = (FIXTURES / "posts.json").read_text(encoding="utf-8")
    assert "奥行き" not in posts
    assert "2製品3構成" not in posts
