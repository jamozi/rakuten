"""Content, source, and product-resource contracts for the ST-1704 pilot."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1"
CONTENT_PATH = SLICE / "content/articles.v1.json"
SOURCE_PATH = SLICE / "sources/source-registry.v1.json"
MEDIA_PATH = SLICE / "media/product-media-registry.v1.json"
CONTENT_AST_SCHEMA_PATH = (
    ROOT / "changes/st-0004/contracts/content/schemas/content-ast.schema.json"
)

CTA_COPY = "楽天市場で現在の価格・在庫・カラーを見る"
ARTICLE_ROWS = (
    (
        "st1703-first-suitcase-comparison",
        "AT-003",
        "product_comparison",
        "carry-on-suitcase-comparison",
        "エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方で選ぶ",
    ),
    (
        "st1704-portable-power-station-guide",
        "AT-001",
        "selection_guide",
        "portable-power-station-guide",
        "停電対策用ポータブル電源の選び方｜容量・定格出力・持ち運びで決める",
    ),
    (
        "st1704-anker-solix-c300-c800-c1000-differences",
        "AT-004",
        "model_generation_capacity_difference",
        "anker-solix-c300-c800-c1000-differences",
        "Anker Solix C300・C800 Plus・C1000・C1000 Gen 2の違い",
    ),
    (
        "st1704-countertop-dishwasher-for-small-households",
        "AT-002",
        "use_case_recommendation",
        "countertop-dishwasher-for-small-households",
        "工事不要の食洗機を1〜2人暮らし向けに比較",
    ),
    (
        "st1704-compact-robot-vacuum-shortlist",
        "AT-005",
        "condition_filtering",
        "compact-robot-vacuum-shortlist",
        "省スペースのロボット掃除機を条件で絞る",
    ),
)
ALLOWED_SOURCE_HOSTS = {
    "affiliate.rakuten.co.jp",
    "developers.google.com",
    "item.rakuten.co.jp",
    "jp.ecoflow.com",
    "panasonic.jp",
    "store.ace.jp",
    "store.irobot-jp.com",
    "www.ana.co.jp",
    "www.ankerjapan.com",
    "www.bluetti.jp",
    "www.caa.go.jp",
    "www.jackery.jp",
    "www.siroca.co.jp",
    "www.switchbot.jp",
    "www.thanko.jp",
}


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _strings(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)


def _claim_ids(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, list):
        for item in value:
            found.update(_claim_ids(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in {"claim_ids", "rationale_claim_ids"}:
                assert isinstance(item, list)
                found.update(item)
            else:
                found.update(_claim_ids(item))
    return found


def _records(value: object) -> Iterable[dict[str, object]]:
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from _records(item)
    elif isinstance(value, list):
        for item in value:
            yield from _records(item)


def test_exact_five_article_identity_order_and_frozen_content_ast_schema() -> None:
    collection = _load(CONTENT_PATH)
    schema = _load(CONTENT_AST_SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    assert collection["publication_authority"] == "NONE"
    assert collection["article_order"] == [row[0] for row in ARTICLE_ROWS]
    articles = collection["articles"]
    assert isinstance(articles, list) and len(articles) == 5
    for slot, (article, expected) in enumerate(zip(articles, ARTICLE_ROWS), start=1):
        assert article["slot"] == slot
        assert (
            article["article_id"],
            article["article_type_code"],
            article["content_ast"]["article_type"],
            article["slug"],
            article["title"],
        ) == expected
        assert article["publication_authority"] == "NONE"
        assert article["category"] == "暮らしの道具"
        assert article["content_ast"]["article_id"] == article["article_id"]
        assert article["content_ast"]["title"] == article["title"]
        assert list(validator.iter_errors(article["content_ast"])) == []


def test_editorial_sequence_and_nineteen_product_card_placements_are_closed() -> None:
    articles = _load(CONTENT_PATH)["articles"]
    card_count = 0
    for article in articles:
        blocks = article["content_ast"]["blocks"]
        block_types = [block["type"] for block in blocks]
        assert block_types[:5] == [
            "disclosure_slot",
            "lead",
            "decision_summary",
            "intended_reader",
            "methodology",
        ]
        comparison_index = block_types.index("comparison_table")
        card_indexes = [
            index for index, value in enumerate(block_types) if value == "product_card"
        ]
        assert card_indexes == list(range(card_indexes[0], card_indexes[-1] + 1))
        assert comparison_index < card_indexes[0]
        assert card_indexes[-1] < block_types.index("recommendation_group")
        assert block_types.index("recommendation_group") < block_types.index("caution")
        assert block_types[-2:] == ["source_summary", "internal_links"]
        assert blocks[-2]["source_packet_version_ref"] == article["source_packet_ref"]
        assert len(card_indexes) == len(article["render_model"]["product_cards"])
        card_count += len(card_indexes)
    assert card_count == 19


def test_source_fact_packets_are_ready_hash_bound_and_cover_every_claim() -> None:
    collection = _load(CONTENT_PATH)
    registry = _load(SOURCE_PATH)
    articles = {article["article_id"]: article for article in collection["articles"]}
    packets = {
        packet["source_packet_ref"]: packet for packet in registry["source_packets"]
    }
    sources = {source["source_ref"]: source for source in registry["sources"]}
    all_claims = {
        claim["claim_id"]: claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }

    assert len(packets) == 5
    assert len(sources) == 19
    assert sources["SRC-ACE-CRESTA-06316"]["url"] == (
        "https://store.ace.jp/shop/g/g06316-01/"
    )
    assert sources["SRC-ACE-DIFFERENCE-05721"]["url"] == (
        "https://store.ace.jp/shop/g/g05721-04"
    )
    assert sources["SRC-ACE-MAXPASS4-01471"]["url"] == (
        "https://store.ace.jp/shop/g/g01471-02"
    )
    assert sources["SRC-ANA-CARRY-ON-BAGGAGE"]["url"] == (
        "https://www.ana.co.jp/ja/jp/notice/carry-on-baggage/20260601/"
    )
    assert len(registry["policy_sources"]) == 3
    assert registry["source_policy"]["immutable_capture_hash_algorithm"] == (
        "SHA256_CANONICAL_UTF8_JSON_V1"
    )
    assert "PENDING_IMMUTABLE_SOURCE_CAPTURE" not in SOURCE_PATH.read_text(
        encoding="utf-8"
    )
    for packet in packets.values():
        assert packet["approval_status"] == "READY_FOR_HUMAN_PUBLICATION_REVIEW"
        assert packet["capture_status"] == "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
        preimage = {
            "schema": "STRUCTURED_ARTICLE_SOURCE_PACKET_V1",
            "source_packet_ref": packet["source_packet_ref"],
            "article_id": packet["article_id"],
            "source_refs": packet["source_refs"],
            "claims": packet["claims"],
            "draft_claim_coverage": packet["draft_claim_coverage"],
        }
        assert packet["fact_packet_sha256"] == _canonical_sha256(preimage)
        coverage = packet["draft_claim_coverage"]
        assert (
            coverage["major_claim_count"]
            == coverage["official_source_bound_major_claim_count"]
        )
        assert (
            coverage["verifiable_claim_count"]
            == coverage["official_source_bound_verifiable_claim_count"]
        )
        assert packet["article_id"] in articles
        assert (
            articles[packet["article_id"]]["source_packet_ref"]
            == packet["source_packet_ref"]
        )
        defined_claims = {claim["claim_id"] for claim in packet["claims"]}
        for claim in packet["claims"]:
            expected_level = (
                "A" if claim["classification"] == "MAJOR_VERIFIABLE" else "D"
            )
            assert claim["evidence_level"] == expected_level
        ast_claims = _claim_ids(articles[packet["article_id"]]["content_ast"])
        render_claims = _claim_ids(articles[packet["article_id"]]["render_model"])
        assert ast_claims <= defined_claims
        assert render_claims <= defined_claims
        assert ast_claims | render_claims == defined_claims

    for source in sources.values():
        parsed = urlsplit(source["url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in ALLOWED_SOURCE_HOSTS
        assert parsed.fragment == ""
        assert source["capture_status"] == "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
        assert source["review_body_excluded_from_claim_evidence"] is True
        claims = [
            {
                key: claim[key]
                for key in ("claim_id", "classification", "statement", "status")
            }
            for claim in all_claims.values()
            if source["source_ref"] in claim["evidence_refs"]
        ]
        claims.sort(key=lambda claim: claim["claim_id"])
        preimage = {
            "schema": "STRUCTURED_SOURCE_FACT_PACKET_V1",
            "source_ref": source["source_ref"],
            "authority": source["authority"],
            "source_type": source["source_type"],
            "title": source["title"],
            "url": source["url"],
            "retrieved_on": source["retrieved_on"],
            "claims": claims,
        }
        assert source["immutable_capture_sha256"] == _canonical_sha256(preimage)

    for source in registry["policy_sources"]:
        parsed = urlsplit(source["url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in ALLOWED_SOURCE_HOSTS
        assert source["source_type"] == "POLICY_PAGE"
        assert source["capture_status"] == "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
        assert source["review_body_excluded_from_claim_evidence"] is True
        preimage = {
            "schema": "STRUCTURED_SOURCE_FACT_PACKET_V1",
            "source_ref": source["source_ref"],
            "authority": source["authority"],
            "source_type": source["source_type"],
            "title": source["title"],
            "url": source["url"],
            "retrieved_on": source["retrieved_on"],
            "claims": [],
        }
        assert source["immutable_capture_sha256"] == _canonical_sha256(preimage)


def test_every_article_has_explicit_reader_led_product_presentation() -> None:
    collection = _load(CONTENT_PATH)
    for article in collection["articles"]:
        render = cast(dict[str, object], article["render_model"])
        presentation = cast(dict[str, object], render["presentation"])
        assert set(presentation) == {
            "fact_checker",
            "first_hand_test",
            "reader_summary",
            "scope_label",
            "scope_note",
        }
        assert presentation["first_hand_test"] == "未実施"
        assert all(cast(str, value).strip() for value in presentation.values())

        cards = cast(list[dict[str, object]], render["product_cards"])
        anchors: set[str] = set()
        for card in cards:
            detail = cast(dict[str, object], card["presentation_v2"])
            assert set(detail) == {
                "benefit",
                "cta_context",
                "detail_anchor",
                "facts_checked_on",
                "fits",
                "not_fits",
                "official_source_ref",
                "recommendation_reason",
            }
            assert detail["facts_checked_on"] == article["freshness"][
                "facts_checked_on"
            ]
            assert detail["official_source_ref"] in card["source_refs"]
            assert cast(list[object], detail["fits"])
            assert cast(list[object], detail["not_fits"])
            assert detail["benefit"] != detail["recommendation_reason"]
            assert card["caution"] not in cast(list[object], detail["not_fits"])
            anchor = cast(str, detail["detail_anchor"])
            assert anchor not in anchors
            anchors.add(anchor)

        recommendations = {
            value["recommendation_ref"]: value
            for value in render["recommendations"]
        }
        cards_by_ref = {
            value["product_selection_ref"]: value for value in cards
        }
        decision = article["content_ast"]["blocks"][2]
        for item in decision["items"]:
            recommendation = recommendations[item["recommendation_ref"]]
            card = cards_by_ref[recommendation["product_selection_ref"]]
            summary = "".join(part["text"] for part in item["summary"])
            assert card["product_name"] not in summary

        body = json.dumps(article, ensure_ascii=False)
        for prohibited in (
            "今すぐ購入",
            "絶対に買うべき",
            "残りわずか",
            "最安",
            "最強",
            "これを選べば間違いない",
            "構成と表現整理にはAIを補助的に使います",
        ):
            assert prohibited not in body

    suitcase = collection["articles"][0]
    suitcase_presentation = suitcase["render_model"]["presentation"]
    assert suitcase["title"] == (
        "エースの機内持ち込みスーツケース3モデル比較｜軽さ・容量・開き方で選ぶ"
    )
    assert suitcase_presentation["scope_label"] == "エース系3モデル"
    assert "市場全体" in suitcase_presentation["scope_note"]


def test_product_cards_bind_only_exact_rakuten_resources_and_pending_media_blocks() -> (
    None
):
    collection = _load(CONTENT_PATH)
    sources = _load(SOURCE_PATH)
    media = _load(MEDIA_PATH)
    affiliates = {
        resource["affiliate_ref"]: resource
        for resource in sources["affiliate_resources"]
    }
    assets = {asset["media_asset_ref"]: asset for asset in media["assets"]}
    placements = [
        (article, card)
        for article in collection["articles"]
        for card in article["render_model"]["product_cards"]
    ]

    assert len(placements) == 19
    assert len({card["product_id"] for _, card in placements}) == 18
    assert len(affiliates) == len(assets) == 18
    for article, card in placements:
        affiliate = affiliates[card["affiliate_ref"]]
        asset = assets[card["media_asset_ref"]]
        assert affiliate["product_id"] == asset["product_id"] == card["product_id"]
        assert (
            affiliate["product_name"] == asset["product_name"] == card["product_name"]
        )
        assert card["cta"] == {
            "copy": CTA_COPY,
            "destination_label": "楽天市場",
            "required_rel": "sponsored nofollow",
            "data_article_id": article["article_id"],
            "data_product_id": card["product_id"],
            "data_placement": "product_card",
        }
        assert affiliate["cta_copy"] == CTA_COPY
        assert affiliate["required_rel"] == "sponsored nofollow"
        assert asset["required_width"] == asset["required_height"] == 128
        assert asset["alt"] == f"{card['product_name']}の商品画像"

    pending = [
        resource
        for resource in affiliates.values()
        if resource["status"] == "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE"
    ]
    assert len(pending) == 18
    for resource in pending:
        assert resource["destination_url"] is None
        assert resource["evidence"] is None
        assert resource["publication_blocker"] == "PENDING_AFFILIATE_EVIDENCE"

    assert media["policy"] == {
        "allowed_asset_class": "rakuten_api_product_image",
        "exact_provider_resource_required": True,
        "modification_allowed": False,
        "crop_allowed": False,
        "text_overlay_allowed": False,
        "aspect_ratio_change_allowed": False,
        "upscale_allowed": False,
        "object_fit": "contain",
        "missing_asset_behavior": "BLOCK_PUBLICATION",
    }
    for asset in assets.values():
        assert asset["status"] == "PENDING_OWNER_LOCAL_RAKUTEN_EVIDENCE"
        assert asset["publication_blocker"] == "PENDING_PRODUCT_MEDIA_EVIDENCE"
        for key in (
            "source_url",
            "image_url",
            "width",
            "height",
            "retrieved_at",
            "response_sha256",
            "image_sha256",
        ):
            assert asset[key] is None
        assert asset["identity"]["status"] == "PENDING_EXACT_MATCH"


def test_disclosure_seo_and_copy_keep_editorial_independence() -> None:
    collection = _load(CONTENT_PATH)
    expected_allowed = ["Article", "BreadcrumbList", "Organization", "WebSite"]
    expected_forbidden = ["Product", "Offer", "Review", "AggregateRating", "FAQPage"]
    meta_titles: set[str] = set()
    meta_descriptions: set[str] = set()
    for article in collection["articles"]:
        flags = article["content_ast"]["publication_flags"]
        assert flags == {
            "affiliate_content": True,
            "human_approval_required": True,
            "allow_auto_publish": False,
        }
        assert article["readiness"]["status"].startswith("BLOCKED_")
        assert (
            "HUMAN_PUBLICATION_APPROVAL_REQUIRED"
            in article["readiness"]["blocking_reasons"]
        )
        seo = article["seo"]
        assert seo["draft_robots"] == "noindex,nofollow"
        assert seo["published_robots"] == "index,follow"
        assert seo["structured_data_allowed"] == expected_allowed
        assert seo["structured_data_forbidden"] == expected_forbidden
        assert seo["visible_content_must_match"] is True
        meta_titles.add(seo["meta_title"])
        meta_descriptions.add(seo["meta_description"])

        disclosure = article["render_model"]["disclosure"]
        disclosure_text = " ".join(disclosure["paragraphs"])
        assert disclosure["label"] == "広告と編集について"
        for required in ("楽天アフィリエイト", "報酬率", "編集部", "実機"):
            assert required in disclosure_text
        assert article["render_model"]["cta_policy"] == {
            "copy": CTA_COPY,
            "destination_label": "楽天市場",
            "required_rel": "sponsored nofollow",
            "direct_link_only": True,
            "fixed_price_inventory_points_in_body": False,
            "independent_from_finance": True,
        }

        editorial = json.dumps(
            {
                "ast": article["content_ast"],
                "render": article["render_model"],
            },
            ensure_ascii=False,
        )
        assert re.search(r"https?://", editorial) is None
        assert not any(
            token in editorial for token in ("<script", "<iframe", "onload=")
        )
        assert not any(
            token in editorial for token in ("¥", "￥", "総合1位", "万能1位")
        )
        assert not any(
            phrase in editorial
            for phrase in (
                "実際に使",
                "使ってみた",
                "愛用",
                "実機で検証",
                "試用しました",
            )
        )
        ranking_material = json.dumps(
            {
                "decision": article["content_ast"]["blocks"][2],
                "recommendations": article["render_model"]["recommendations"],
                "cards": article["render_model"]["product_cards"],
            },
            ensure_ascii=False,
        )
        assert not any(
            term in ranking_material for term in ("報酬率", "EPC", "RPM", "利益")
        )
    assert len(meta_titles) == len(meta_descriptions) == 5


def test_reader_copy_and_dimension_notation_are_normalized() -> None:
    forbidden_copy = (
        "公開前",
        "構成です",
        "自分で確認",
        "できない人",
        "確認せず",
        "推測しない",
        "公式表記順",
        "定格定格",
        "条件には合",
        "楽天の商品ページ",
        "楽天の商品名",
    )
    expected_disclosure = [
        "型番が一致する楽天商品を確認できた場合に、楽天アフィリエイトの購入リンクを掲載します。リンク経由で商品を購入すると、運営者が成果報酬を受け取る場合があります。",
        "成果報酬の有無や報酬率、価格、ポイント、在庫は、商品の評価や掲載順に影響しません。",
        "掲載内容はメーカーなどの一次情報をもとに編集部が確認しています。実機を使用したレビューではありません。",
    ]
    dimension_axes = {
        "AXIS-SUITCASE-DIMENSIONS",
        "AXIS-POWER-SIZE",
        "AXIS-ANKER-SIZE",
        "AXIS-DISH-SIZE",
        "AXIS-ROBOT-BODY",
        "AXIS-ROBOT-STATION",
    }
    dimension_pattern = re.compile(
        r"幅(?:約)?\d+(?:\.\d+)?×"
        r"奥行(?:約)?\d+(?:\.\d+)?×"
        r"高さ(?:約)?\d+(?:\.\d+)?cm"
    )
    observed_dimensions = 0
    collection = _load(CONTENT_PATH)

    for article in collection["articles"]:
        article_text = " ".join(_strings(article))
        for forbidden in forbidden_copy:
            assert forbidden not in article_text
        assert "<br" not in article_text.casefold()
        assert article["render_model"]["disclosure"]["paragraphs"] == expected_disclosure
        for table in article["render_model"]["comparison_tables"]:
            for row in table["rows"]:
                for cell in row["cells"]:
                    if cell["axis_ref"] not in dimension_axes:
                        continue
                    observed_dimensions += 1
                    assert cell["state"] == "KNOWN"
                    assert dimension_pattern.fullmatch(cell["value"])

    assert observed_dimensions == 23
    collection_text = CONTENT_PATH.read_text(encoding="utf-8")
    assert "購入前に型番とカラー構成を確認" in collection_text
    assert "購入する型番の公式対応情報と取扱説明書を確認してください" in collection_text
    articles = {article["article_id"]: article for article in collection["articles"]}
    dishwasher = articles["st1704-countertop-dishwasher-for-small-households"]
    dishwasher_text = " ".join(_strings(dishwasher))
    for formal_name in (
        "Panasonic SOLOTA NP-TMLK1-K",
        "THANKO ラクアmini color（型番：TDWS25SBL）",
        "siroca 食器洗い乾燥機 SS-MA251",
        "Panasonic NP-TSP1-W",
    ):
        assert formal_name in dishwasher_text
    assert (
        "以降は順に「SOLOTA」「ラクアmini color」「SS-MA251」"
        "「NP-TSP1」と表記します。"
    ) in dishwasher_text
    assert [
        card["product_name"]
        for card in dishwasher["render_model"]["product_cards"]
    ] == ["SOLOTA", "ラクアmini color", "SS-MA251", "NP-TSP1"]
    robot = articles["st1704-compact-robot-vacuum-shortlist"]
    robot_text = " ".join(_strings(robot))
    assert (
        "iRobot「Roomba Mini 掃除機＆床拭きロボット + "
        "AutoEmpty 充電ステーション」（型番：F155260）"
    ) in robot_text
    assert (
        "iRobot「Roomba Plus 515 Combo ロボット + "
        "AutoWash 充電ステーション」（型番：N285060）"
    ) in robot_text
    assert (
        "以降は順に「Roomba Mini」「K11+ Pro」「K10+ Pro Combo」"
        "「Roomba Plus 515 Combo」と表記します。"
    ) in robot_text
    assert "幅条件" not in robot_text
    power_text = " ".join(
        _strings(articles["st1704-portable-power-station-guide"])
    )
    assert "約5.7kg" not in power_text
    assert power_text.count("5.7kg") >= 7
    assert "容量（Wh）÷機器の消費電力（W）" in power_text
    assert "AC変換損失" in power_text
    assert "起動時電力" in power_text

    suitcase_text = " ".join(
        _strings(articles["st1703-first-suitcase-comparison"])
    )
    assert suitcase_text.count("2026年8月30日のメーカー公式通販では在庫切れ") >= 4
    assert "販売状況は変動" in suitcase_text

    anker_text = " ".join(
        _strings(articles["st1704-anker-solix-c300-c800-c1000-differences"])
    )
    for official_difference in (
        "別売り拡張バッテリー",
        "AC出力6口",
        "SurgePad 2000W",
        "停電時約10ミリ秒切り替え",
        "4000回以上の充放電サイクル",
        "USB-C 3口",
        "拡張バッテリーには対応しません",
    ):
        assert official_difference in anker_text

    assert "標準食器点数は各社の想定した食器構成による参考値" in dishwasher_text
    assert "24点モデルを1〜2人向けの上位候補と決め打ちせず" in dishwasher_text
    assert "公式設置案内の帰還余白" in robot_text
    assert "K11+ Proより本体は0.3cm" in robot_text


def test_internal_routes_are_closed_and_topic_pairs_cross_link() -> None:
    collection = _load(CONTENT_PATH)
    routes = {route["route_ref"]: route for route in collection["routes"]}
    links = {
        article["article_id"]: {
            link["route_ref"] for link in article["content_ast"]["blocks"][-1]["links"]
        }
        for article in collection["articles"]
    }
    for article in collection["articles"]:
        assert article["render_model"]["internal_link_policy"] == {
            "resolve_only_when_target_is_published": True,
            "unresolved_behavior": "OMIT_LINK",
        }
        assert links[article["article_id"]] <= routes.keys()
        assert "ROUTE-HOME-GUIDES" in links[article["article_id"]]
    assert (
        "ROUTE-ARTICLE-ANKER-DIFFERENCES"
        in links["st1704-portable-power-station-guide"]
    )
    assert (
        "ROUTE-ARTICLE-PORTABLE-POWER"
        in links["st1704-anker-solix-c300-c800-c1000-differences"]
    )
    assert (
        "ROUTE-ARTICLE-ROBOT-VACUUM"
        in links["st1704-countertop-dishwasher-for-small-households"]
    )
    assert "ROUTE-ARTICLE-DISHWASHER" in links["st1704-compact-robot-vacuum-shortlist"]


def test_relative_comparisons_bind_the_complete_comparison_evidence_set() -> None:
    required_by_article = {
        "st1703-first-suitcase-comparison": {"CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES"},
        "st1704-portable-power-station-guide": {"CLM-ST1704-POWER-CONDITIONAL-CHOICES"},
        "st1704-countertop-dishwasher-for-small-households": {
            "CLM-ST1704-DISH-CONDITIONAL-CHOICES"
        },
        "st1704-compact-robot-vacuum-shortlist": {
            "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES"
        },
        "st1704-anker-solix-c300-c800-c1000-differences": {
            "CLM-ST1704-ANKER-C300-SPECS",
            "CLM-ST1704-ANKER-C800-SPECS",
            "CLM-ST1704-ANKER-C1000-SPECS",
            "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
        },
    }
    relative_language = re.compile(r"最軽量|最も軽|最小|最大|中間|条件から外")
    carry_on_exclusion = re.compile(
        r"機内持ち込み[^。]{0,40}(?:外れ|外れる)|"
        r"(?:外れ|外れる)[^。]{0,40}機内持ち込み"
    )
    observed_relative_records = 0
    observed_carry_on_records = 0

    for article in _load(CONTENT_PATH)["articles"]:
        required = required_by_article[article["article_id"]]
        for record in _records(
            {
                "content_ast": article["content_ast"],
                "render_model": article["render_model"],
            }
        ):
            raw_claims = record.get("claim_ids")
            if not isinstance(raw_claims, list) or not raw_claims:
                continue
            claims = set(raw_claims)
            material = " ".join(_strings(record))
            if relative_language.search(material):
                observed_relative_records += 1
                assert required <= claims
            if carry_on_exclusion.search(material):
                observed_carry_on_records += 1
                assert "CLM-ST1704-SUITCASE-CARRYON-LIMITS" in claims

    assert observed_relative_records >= 23
    assert observed_carry_on_records == 2


def test_jackery_dimensions_and_k11_sheet_fact_remain_source_bound() -> None:
    articles = {
        article["article_id"]: article for article in _load(CONTENT_PATH)["articles"]
    }

    def cell(article_id: str, product_ref: str, axis_ref: str) -> dict[str, object]:
        article = articles[article_id]
        matches = [
            candidate
            for table in article["render_model"]["comparison_tables"]
            for row in table["rows"]
            if row["product_selection_ref"] == product_ref
            for candidate in row["cells"]
            if candidate["axis_ref"] == axis_ref
        ]
        assert len(matches) == 1
        return matches[0]

    assert cell(
        "st1704-portable-power-station-guide",
        "PSEL-POWER-JACKERY",
        "AXIS-POWER-SIZE",
    ) == {
        "axis_ref": "AXIS-POWER-SIZE",
        "value": "幅31.1×奥行20.5×高さ15.7cm",
        "claim_ids": ["CLM-ST1704-POWER-JACKERY-SPECS"],
        "state": "KNOWN",
    }
    assert cell(
        "st1704-countertop-dishwasher-for-small-households",
        "PSEL-DISH-RAKUA",
        "AXIS-DISH-DRY",
    ) == {
        "axis_ref": "AXIS-DISH-DRY",
        "value": "温風乾燥",
        "claim_ids": ["CLM-ST1704-DISH-RAKUA-SPECS"],
        "state": "KNOWN",
    }
    assert cell(
        "st1704-compact-robot-vacuum-shortlist",
        "PSEL-ROBOT-K11-PRO",
        "AXIS-ROBOT-MOP",
    ) == {
        "axis_ref": "AXIS-ROBOT-MOP",
        "value": "市販のお掃除シート式",
        "claim_ids": ["CLM-ST1704-ROBOT-K11-PRO-SPECS"],
        "state": "KNOWN",
    }


def test_regressions_for_ecoflow_roomba_and_switchbot_dimension_semantics() -> None:
    collection_text = CONTENT_PATH.read_text(encoding="utf-8")
    registry = _load(SOURCE_PATH)
    source_by_ref = {source["source_ref"]: source for source in registry["sources"]}
    claims = {
        claim["claim_id"]: claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    assert source_by_ref["SRC-ECOFLOW-DELTA3-CLASSIC"]["url"] == (
        "https://jp.ecoflow.com/products/delta-3-classic"
    )
    assert "自動給排水" not in collection_text
    assert "自動給排水" not in SOURCE_PATH.read_text(encoding="utf-8")
    assert "自動給水" in claims["CLM-ST1704-ROBOT-ROOMBA-515-SPECS"]["statement"]
    assert (
        "温水洗浄・温風乾燥" in claims["CLM-ST1704-ROBOT-ROOMBA-515-SPECS"]["statement"]
    )
    assert (
        "底面240×180mm、高さ250mm"
        in claims["CLM-ST1704-ROBOT-K11-PRO-SPECS"]["statement"]
    )
    assert "195×297×410mm" in claims["CLM-ST1704-ROBOT-K10-COMBO-SPECS"]["statement"]
    robot = next(
        article
        for article in _load(CONTENT_PATH)["articles"]
        if article["article_id"] == "st1704-compact-robot-vacuum-shortlist"
    )
    robot_text = " ".join(_strings(robot))
    assert "ステーション幅" not in robot_text
    assert "最大底面辺" in robot_text
    assert "公式表記順" not in robot_text
    assert "幅24.0×奥行18.0×高さ25.0cm" in robot_text
    assert "幅19.5×奥行29.7×高さ41.0cm" in robot_text
