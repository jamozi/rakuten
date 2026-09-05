from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTICLES = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
ARTICLE_SOURCE = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json"
)
COMPARISON_POLICY = (
    ROOT
    / "changes/wordpress-local-preview-v1/fixtures/pages/comparison-policy.html"
)
PRODUCTION_COMPARISON_POLICY = (
    ROOT
    / "changes/wordpress-local-preview-v1/fixtures/production-pages/comparison-policy.html"
)


def _documents() -> dict[str, str]:
    return {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(ARTICLES.glob("*.html"))
    }


def test_all_existing_articles_explain_role_accountability_and_limits() -> None:
    documents = _documents()

    assert len(documents) == 10
    for slug, markup in documents.items():
        for label in (
            "対象読者",
            "比較範囲",
            "記事分類",
            "この記事で答えること",
            "執筆担当",
            "事実確認担当",
            "最終確認日",
            "実機確認",
        ):
            assert markup.count(f"<dt>{label}</dt>") == 1, (slug, label)
        assert "未実施（公式仕様比較）" in markup, slug
        checked_on = (
            "2026年9月5日" if slug == "solota-vs-rakua-mini-plus" else "2026年9月1日"
        )
        assert markup.count(f"<dt>最終確認日</dt><dd>{checked_on}</dd>") == 1, slug
        disclosure_heading = (
            "購入リンクなし"
            if slug == "solota-vs-rakua-mini-plus"
            else "広告・アフィリエイト開示"
        )
        assert disclosure_heading in markup, slug
        assert "/comparison-policy/" in markup, slug
        assert markup.index(disclosure_heading) < markup.index("decision-section"), slug


def test_reader_copy_has_no_internal_workflow_labels_or_pressure_language() -> None:
    prohibited = (
        "<dt>検索意図</dt>",
        "固定した4型番",
        "固定4型番",
        "4枠から外しました",
        "今すぐ購入",
        "絶対におすすめ",
        "必ずお得",
    )
    for slug, markup in _documents().items():
        for phrase in prohibited:
            assert phrase not in markup, (slug, phrase)
        assert "AggregateRating" not in markup, slug
        assert not re.search(r'"@type"\s*:\s*"(?:Product|Offer|Review)"', markup), slug


def test_third_party_blog_boundary_is_explicit_and_non_experiential() -> None:
    local = COMPARISON_POLICY.read_text(encoding="utf-8")
    production = PRODUCTION_COMPARISON_POLICY.read_text(encoding="utf-8")
    shared_statements = (
        "第三者ブログや比較記事は、選定軸や候補を洗い出す探索にだけ使い",
        "推奨根拠には使いません",
        "「第三者による報告」と明示します",
        "目的に必要な最小限の範囲",
        "ReviewやAggregateRatingなどのレビュー系構造化データを出力しません",
    )
    for policy in (local, production):
        for statement in shared_statements:
            assert statement in policy
    assert "編集部自身の使用感へ置き換えることもしません" in local
    assert "編集者自身の使用感へ置き換えることもしません" in production
    for policy in (local, production):
        assert '<time datetime="2026-09-05">2026年9月5日</time>' in policy
        for field in (
            "対象型番",
            "発行者・媒体",
            "掲載日",
            "確認日",
            "使用条件",
            "原典URL",
            "該当箇所",
        ):
            assert field in policy
        for field in (
            "直接使用",
            "入手経路",
            "提供・貸与の有無",
            "利益相反",
            "使用期間",
            "使用環境",
            "確認方法",
            "実機証拠",
        ):
            assert field in policy
        assert "他者の体験談しかない場合は、この表記を使いません" in policy
        assert "一項目でも欠ける場合" in policy
        assert "写真・動画・音声・測定記録" in policy
        assert "第三者報告だけを根拠に当サイトのReviewラベル" in policy
        assert "「best」「最良」と断定" in policy
        for quotation_rule in (
            "公表済み",
            "引用の必要性",
            "引用部分の明確化",
            "本文との主従関係",
            "目的に必要な最小限",
            "出所の明示",
        ):
            assert quotation_rule in policy


def test_editorial_summaries_are_not_marked_up_as_third_party_quotations() -> None:
    for slug, markup in _documents().items():
        assert "<blockquote" not in markup, slug

    expected_summaries = {
        "carry-on-suitcase-under-100-seats": "公称値が規格内でも",
        "front-open-carry-on-suitcase-with-stopper": "公称外寸で候補を絞ったあと",
        "lightweight-carry-on-suitcase-under-3kg": "同じ型番について、公称重量",
        "roomba-mini-vs-switchbot-k11-pro": "家具下の高さ、家具脚の間隔",
        "solota-vs-rakua-mini-plus": "気になる商品の型番を控え",
    }
    documents = _documents()
    for slug, summary in expected_summaries.items():
        assert f'<p class="editorial-summary">{summary}' in documents[slug]


def test_experiential_shortcuts_are_replaced_by_measurable_conditions() -> None:
    documents = _documents()
    prohibited = (
        "持ち出しやすさを優先",
        "容量と持ち運びやすさのバランス",
        "前開きの取り出しやすさ",
        "少量と置きやすさを優先",
        "容量を増やすほど便利",
        "移動負担が最大",
        "持ち出しやすくしたい",
        "持ち出す負担を抑えたい",
        "「移動中に荷物を取り出しやすい」",
    )
    for slug, markup in documents.items():
        for phrase in prohibited:
            assert phrase not in markup, (slug, phrase)

    assert "本体5.7kgを運べる場合の候補" in documents[
        "portable-power-station-guide"
    ]
    assert "本体約4.1kgを保管場所から運べる場合" in documents[
        "portable-power-station-guide"
    ]
    assert "21Lで足り、前開き部に入れる物と収納寸法が一致" in documents[
        "carry-on-suitcase-under-100-seats"
    ]
    assert "後継機・同等品とは断定しません" in documents[
        "solota-vs-rakua-mini-plus"
    ]


def test_quietness_wording_is_attributed_and_never_used_as_measured_evidence() -> None:
    documents = _documents()
    front = documents["front-open-carry-on-suitcase-with-stopper"]
    assert "メーカー表記「ストッパー付き55mm静音キャスター」" in front
    assert "走行音は未実測・選定根拠外" in front
    assert "当サイトは走行音を実測しておらず、静音性を選定根拠に使いません" in front
    assert "静音双輪を優先する場合" not in front

    for slug, markup in documents.items():
        if "静音" not in markup:
            continue
        if slug == "portable-power-station-guide":
            assert "静音性は比較対象外" in markup
        elif slug == "roomba-mini-vs-switchbot-k11-pro":
            assert "静音性を順位付けしません" in markup
        elif slug == "front-open-carry-on-suitcase-with-stopper":
            assert "静音性を選定根拠に使いません" in markup
            assert "静音性は選定根拠外" in markup
        else:
            raise AssertionError((slug, "unexpected quietness claim"))


def test_rakuten_web_service_credit_is_exact_and_explained_in_japanese() -> None:
    exact_anchor = (
        '<a href="https://developers.rakuten.com/" target="_blank" rel="noopener noreferrer">'
        "Supported by Rakuten Developers</a>"
    )
    for slug, markup in _documents().items():
        # Lifecycle-only pages intentionally have no affiliate product data or
        # Rakuten attribution (the V2 contract requires this fail-closed route).
        if slug == "solota-vs-rakua-mini-plus":
            assert "https://developers.rakuten.com/" not in markup, slug
            assert "Rakuten Web Services Attribution Snippet" not in markup, slug
            assert "商品情報の取得には楽天ウェブサービスを利用しています。" not in markup, slug
            continue
        assert markup.count(exact_anchor) == 1, slug
        assert (
            markup.count("Rakuten Web Services Attribution Snippet FROM HERE") == 1
        ), slug
        assert (
            markup.count("Rakuten Web Services Attribution Snippet TO HERE") == 1
        ), slug
        assert "商品情報の取得には楽天ウェブサービスを利用しています。" in markup, slug


def test_in_page_decision_links_resolve_to_unique_article_targets() -> None:
    for slug, markup in _documents().items():
        ids = re.findall(r'\sid=["\']([^"\']+)["\']', markup)
        fragments = re.findall(r'href=["\']#([^"\']+)["\']', markup)

        assert len(ids) == len(set(ids)), (slug, "duplicate-id")
        assert set(fragments) <= set(ids), (slug, sorted(set(fragments) - set(ids)))


def test_every_article_supports_a_no_purchase_or_keep_existing_decision() -> None:
    documents = _documents()
    expected = {
        "carry-on-suitcase-comparison": r"手持ちのケース.*(?:買い替えない|買い替え不要)",
        "portable-power-station-guide": r"手持ちのモバイルバッテリーで足りる",
        "anker-solix-c300-c800-c1000-differences": r"手元のモバイルバッテリーで足りる",
        "countertop-dishwasher-for-small-households": r"購入を見送る",
        "compact-robot-vacuum-shortlist": r"購入を見送る",
        "carry-on-suitcase-under-100-seats": r"手持ちのケース.*(?:買い替えない|買い替え不要)",
        "lightweight-carry-on-suitcase-under-3kg": r"手持ちのケース.*(?:買い替えない|買い替え不要)",
        "front-open-carry-on-suitcase-with-stopper": r"手持ちのケース.*(?:買い替えない|買い替え不要)",
        "roomba-mini-vs-switchbot-k11-pro": r"(?:購入を見送る|買い足さない|今の掃除方法)",
        "solota-vs-rakua-mini-plus": r"設置条件を満たせない場合は、購入を見送る選択",
    }
    assert set(documents) == set(expected)
    for slug, pattern in expected.items():
        assert re.search(pattern, documents[slug], re.DOTALL), slug


def test_market_scope_and_article_roles_are_explained_in_reader_language() -> None:
    documents = _documents()
    ace = documents["carry-on-suitcase-comparison"]
    lightweight = documents["lightweight-carry-on-suitcase-under-3kg"]
    robot_shortlist = documents["compact-robot-vacuum-shortlist"]
    robot_direct = documents["roomba-mini-vs-switchbot-k11-pro"]
    dishwasher = documents["countertop-dishwasher-for-small-households"]

    assert "RIMOWA Essential Lite" in ace
    assert "Samsonite C-Lite" in ace
    assert "市場横断の比較" in ace
    assert "RIMOWA Essential Lite キャビン 82353171" in lightweight
    assert "Samsonite C-Lite" in lightweight
    assert "FREQUENTER LIEVE 1-250" in lightweight
    assert "交換可能な車輪を優先する場合は有力な代替候補" in lightweight
    assert (
        "置き場所優先のEufy C10・K11+ Proと、モップ自動手入れ優先の"
        "DEEBOT mini 2・Roomba Plus 515 Combo"
    ) in robot_shortlist
    assert "/roomba-mini-vs-switchbot-k11-pro/" in robot_shortlist
    assert robot_direct.index('id="robot-setup-title"') < robot_direct.index('id="robot-app-title"')
    assert "Panasonic RULO mini" in robot_direct
    assert "販売状態は未確認（推奨根拠に使用しない）" in robot_direct
    assert "RULO miniは次回確認へ回します" in robot_direct
    assert "この比較だけでは決めにくい人" in dishwasher
    assert "洗浄力、乾き具合、運転音" in dishwasher


def test_anker_purchase_caution_is_a_scannable_four_step_checklist() -> None:
    markup = _documents()["anker-solix-c300-c800-c1000-differences"]
    source = json.loads(ARTICLE_SOURCE.read_text(encoding="utf-8"))
    anker = next(
        article
        for article in source["articles"]
        if article["article_id"]
        == "st1704-anker-solix-c300-c800-c1000-differences"
    )
    caution_source = next(
        block
        for block in anker["content_ast"]["blocks"]
        if block["block_id"] == "BLK-ANKER-016"
    )
    caution = re.search(
        r'<aside class="raos-caution purchase-caution">(.*?)</aside>',
        markup,
        re.DOTALL,
    )

    assert caution is not None
    assert len(caution_source["content"]) == 4
    assert caution.group(1).count("<li>") == 4
    for label in (
        "型番と拡張性：",
        "出力と停電時切り替え：",
        "安全・保証・修理：",
        "適用外と最終照合：",
    ):
        assert any(
            node["text"].startswith(label) for node in caution_source["content"]
        )
        assert label in caution.group(1)
    assert caution.group(1).rstrip().endswith("公式対応情報と取扱説明書で照合してください。</li></ul>")
