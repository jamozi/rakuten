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
SOURCE_CAPTURE_CLAIM_OPTIONAL_KEYS = (
    "dimensions",
    "market_candidate_id",
    "market_disposition",
    "official_url",
    "exact_model",
    "exact_variant_scope",
    "evaluated_at",
    "model_lifecycle",
    "variant_lifecycle",
    "reader_visible_lifecycle",
    "embedded_structured_lifecycle",
    "lifecycle_evidence_state",
    "effective_lifecycle",
    "negative_claim_evidence",
    "product_specific_recall_query_gate",
    "manufacturer_sales_state",
    "portfolio_candidate_disposition",
    "portfolio_candidate_reason",
    "route_article_id",
)
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
        "ロボット掃除機4モデルを設置寸法と自動手入れで比べる",
    ),
)
ALLOWED_SOURCE_HOSTS = {
    "affiliate.rakuten.co.jp",
    "cdn.shopify.com",
    "developers.google.com",
    "help.ecovacs.com",
    "item.rakuten.co.jp",
    "jp.ecoflow.com",
    "lp.ankerjapan.com",
    "dl.djicdn.com",
    "panasonic.jp",
    "shop.toshiba-lifestyle.com",
    "store.dji.com",
    "store.ace.jp",
    "store.irobot-jp.com",
    "store.siroca.jp",
    "support.switch-bot.com",
    "shop.innovator.co.jp",
    "aqua-has.com",
    "jp.roborock.com",
    "www.americantourister.jp",
    "www.ana.co.jp",
    "www.ankerjapan.com",
    "www.bagworld.co.jp",
    "www.bermas.co.jp",
    "www.bluetti.jp",
    "www.caa.go.jp",
    "www.dji.com",
    "www.dreametech.jp",
    "www.ecovacs.com",
    "www.elecom.co.jp",
    "www.irisohyama.co.jp",
    "www.jackery.jp",
    "www.jal.co.jp",
    "www.meti.go.jp",
    "www.muji.com",
    "www.rimowa.com",
    "www.samsonite.co.jp",
    "www.samsonite.az",
    "www.samsonite.ro",
    "www.siroca.co.jp",
    "www.switchbot.jp",
    "www.thanko.jp",
    "www.toshiba-lifestyle.com",
}

WORDPRESS_ARTICLE_ROOT = ROOT / "changes/wordpress-local-preview-v1/fixtures/articles"
ALL_ARTICLE_SLUGS = (
    "carry-on-suitcase-comparison",
    "portable-power-station-guide",
    "anker-solix-c300-c800-c1000-differences",
    "countertop-dishwasher-for-small-households",
    "compact-robot-vacuum-shortlist",
    "carry-on-suitcase-under-100-seats",
    "lightweight-carry-on-suitcase-under-3kg",
    "front-open-carry-on-suitcase-with-stopper",
    "roomba-mini-vs-switchbot-k11-pro",
    "solota-vs-rakua-mini-plus",
)


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


def test_editorial_sequence_and_twenty_product_card_placements_are_closed() -> None:
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
    assert card_count == 22


def test_each_lead_opens_with_a_unique_reader_failure_then_names_the_models() -> None:
    articles = _load(CONTENT_PATH)["articles"]
    hooks: set[str] = set()
    expected_decision_terms = {
        "st1703-first-suitcase-comparison": ("軽さ", "開け"),
        "st1704-portable-power-station-guide": ("容量だけ", "動かせない"),
        "st1704-anker-solix-c300-c800-c1000-differences": ("新しい世代", "容量拡張"),
        "st1704-countertop-dishwasher-for-small-households": ("本体幅だけ", "扉"),
        "st1704-compact-robot-vacuum-shortlist": ("本体", "ステーション"),
    }
    for article in articles:
        lead = article["content_ast"]["blocks"][1]
        lead_node_types = [node["type"] for node in lead["content"]]
        assert lead_node_types in (
            ["text", "line_break", "text"],
            ["text", "line_break", "text", "line_break", "text"],
        )
        hook = lead["content"][0]["text"]
        scope = "".join(node["text"] for node in lead["content"][2::2])
        assert hook not in hooks
        hooks.add(hook)
        assert hook.endswith("。")
        assert "比較するのは" not in hook
        assert scope.startswith("比較するのは")
        assert len(hook + scope) <= 250, article["article_id"]
        for term in expected_decision_terms[article["article_id"]]:
            assert term in hook


def test_power_recommendation_does_not_use_unresolved_support_as_a_benefit() -> None:
    articles = _load(CONTENT_PATH)["articles"]
    article = next(
        row
        for row in articles
        if row["article_id"] == "st1704-portable-power-station-guide"
    )
    lead = "".join(
        node.get("text", "") for node in article["content_ast"]["blocks"][1]["content"]
    )
    assert "安全・保管・保証・回収" in lead
    assert "推奨根拠には使いません" in lead
    card = next(
        row
        for row in article["render_model"]["product_cards"]
        if row["product_id"] == "PRD-DJI-POWER-1000-V2"
    )
    reason = card["presentation_v2"]["recommendation_reason"]
    assert "接続機器の条件" in reason
    assert "14.2kg" in reason
    assert not any(term in reason for term in ("保証", "サイクル", "寿命"))
    assert card["caution"]


def test_source_fact_packets_are_ready_hash_bound_and_cover_every_claim() -> None:
    collection = _load(CONTENT_PATH)
    registry = _load(SOURCE_PATH)
    articles = {article["article_id"]: article for article in collection["articles"]}
    registry_packets = {
        packet["source_packet_ref"]: packet for packet in registry["source_packets"]
    }
    selected_packet_refs = {
        article["source_packet_ref"] for article in articles.values()
    }
    packets = {
        packet_ref: registry_packets[packet_ref] for packet_ref in selected_packet_refs
    }
    sources = {source["source_ref"]: source for source in registry["sources"]}

    assert len(registry_packets) == 10
    assert len(packets) == len(articles) == 5
    assert len(sources) == 101
    assert (
        _canonical_sha256(
            sorted(
                (
                    {"source_ref": source_ref, "url": source["url"]}
                    for source_ref, source in sources.items()
                ),
                key=lambda value: cast(str, value["source_ref"]),
            )
        )
        == "d6179333137f0faf66526a1eadc86c085ada3d12245b6f16955946996210a70b"
    )
    assert sources["SRC-ACE-CRESTA-06316"]["url"] == (
        "https://store.ace.jp/shop/g/g06316-01/"
    )
    assert sources["SRC-ACE-DIFFERENCE-05721"]["url"] == (
        "https://store.ace.jp/shop/g/g05721-06/"
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
        defined_claims = {claim["claim_id"] for claim in packet["claims"]}
        for claim in packet["claims"]:
            expected_level = {
                "MAJOR_VERIFIABLE": "A",
                "EDITORIAL_INFERENCE": "D",
                "DECISION_CRITICAL_UNKNOWN": "UNKNOWN",
            }[claim["classification"]]
            assert claim["evidence_level"] == expected_level
        article = articles.get(packet["article_id"])
        if article is not None:
            assert article["source_packet_ref"] == packet["source_packet_ref"]
            ast_claims = _claim_ids(article["content_ast"])
            render_claims = _claim_ids(article["render_model"])
            reader_projection_claims = {
                claim["claim_id"]
                for claim in packet["claims"]
                if "market_candidate_id" in claim
                or "portfolio_candidate_disposition" in claim
            }
            assert ast_claims <= defined_claims
            assert render_claims <= defined_claims
            assert reader_projection_claims <= defined_claims
            assert (
                ast_claims | render_claims | reader_projection_claims == defined_claims
            )


def test_ten_packets_cover_all_37_existing_product_placements() -> None:
    registry = _load(SOURCE_PATH)
    packets = registry["source_packets"]
    expected_articles = {
        *(row[0] for row in ARTICLE_ROWS),
        "carry-on-suitcase-under-100-seats",
        "lightweight-carry-on-suitcase-under-3kg",
        "front-open-carry-on-suitcase-with-stopper",
        "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus",
    }

    assert {packet["article_id"] for packet in packets} == expected_articles
    article_products = {
        article["article_id"]: {
            card["product_id"] for card in article["render_model"]["product_cards"]
        }
        for article in _load(CONTENT_PATH)["articles"]
    }
    for article_id, slug in {
        "carry-on-suitcase-under-100-seats": "carry-on-suitcase-under-100-seats",
        "lightweight-carry-on-suitcase-under-3kg": "lightweight-carry-on-suitcase-under-3kg",
        "front-open-carry-on-suitcase-with-stopper": "front-open-carry-on-suitcase-with-stopper",
        "roomba-mini-vs-switchbot-k11-pro": "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus": "solota-vs-rakua-mini-plus",
    }.items():
        html = (WORDPRESS_ARTICLE_ROOT / f"{slug}.html").read_text(encoding="utf-8")
        article_products[article_id] = set(
            re.findall(r'data-raos-product-id="(PRD-[A-Z0-9-]+)"', html)
        )
    packet_products = {
        packet["article_id"]: {
            product_id
            for claim in packet["claims"]
            for product_id in claim["subject_product_ids"]
        }
        for packet in packets
    }
    assert sum(len(products) for products in article_products.values()) == 37
    assert all(
        product_ids <= packet_products[article_id]
        for article_id, product_ids in article_products.items()
    )


def test_all_ten_articles_keep_37_products_and_exactly_74_primary_ctas() -> None:
    article_slugs = {row[0]: row[3] for row in ARTICLE_ROWS} | {
        "carry-on-suitcase-under-100-seats": "carry-on-suitcase-under-100-seats",
        "lightweight-carry-on-suitcase-under-3kg": (
            "lightweight-carry-on-suitcase-under-3kg"
        ),
        "front-open-carry-on-suitcase-with-stopper": (
            "front-open-carry-on-suitcase-with-stopper"
        ),
        "roomba-mini-vs-switchbot-k11-pro": "roomba-mini-vs-switchbot-k11-pro",
        "solota-vs-rakua-mini-plus": "solota-vs-rakua-mini-plus",
    }
    selected_by_article: dict[str, set[str]] = {}
    ctas: list[tuple[str, str, str]] = []

    for article_id, slug in article_slugs.items():
        markup = (WORDPRESS_ARTICLE_ROOT / f"{slug}.html").read_text(encoding="utf-8")
        profiles = []
        for tag in re.findall(r"<article\b[^>]*>", markup):
            class_match = re.search(r'class="([^"]*)"', tag)
            if (
                class_match is None
                or "product-profile" not in class_match.group(1).split()
            ):
                continue
            product_match = re.search(r'data-raos-product-id="(PRD-[A-Z0-9-]+)"', tag)
            assert product_match is not None
            profiles.append(product_match.group(1))
        assert len(profiles) == len(set(profiles))
        selected_by_article[article_id] = set(profiles)

        placement_products: dict[str, list[str]] = {
            "product_card": [],
            "final_summary": [],
        }
        for tag in re.findall(r"<a\b[^>]*>", markup):
            placement_match = re.search(r'data-raos-placement="([^"]+)"', tag)
            if placement_match is None:
                continue
            placement = placement_match.group(1)
            if placement not in placement_products:
                continue
            product_match = re.search(r'data-raos-product-id="(PRD-[A-Z0-9-]+)"', tag)
            assert product_match is not None
            product_id = product_match.group(1)
            placement_products[placement].append(product_id)
            ctas.append((article_id, product_id, placement))

        for products in placement_products.values():
            assert len(products) == len(set(products))
            assert set(products) == selected_by_article[article_id]

    assert sum(map(len, selected_by_article.values())) == 37
    assert len(ctas) == len(set(ctas)) == 74

    a07 = "lightweight-carry-on-suitcase-under-3kg"
    c_lite_id = "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549"
    frequenter_id = "PRD-FREQUENTER-LIEVE-1-250"
    assert len(selected_by_article[a07]) == 5
    assert c_lite_id in selected_by_article[a07]
    assert frequenter_id not in selected_by_article[a07]
    a07_markup = (
        WORDPRESS_ARTICLE_ROOT / "lightweight-carry-on-suitcase-under-3kg.html"
    ).read_text(encoding="utf-8")
    assert 'id="samsonite-c-lite-spinner55exp-134679-1549"' in a07_markup


def test_dimension_claims_are_semantic_and_frequenter_typo_is_not_promoted() -> None:
    registry = _load(SOURCE_PATH)
    claims = {
        claim["claim_id"]: claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }
    frequenter = claims["CLM-PORTFOLIO-LIGHT-FREQUENTER-REFERENCE"]
    c_lite = claims["CLM-PORTFOLIO-LIGHT-SAMSONITE-C-LITE-134679-1549"]

    assert frequenter["market_candidate_id"] == (
        "EXT-FREQUENTER-LIEVE-1-250-MAINTAINABILITY"
    )
    assert frequenter["subject_product_ids"] == []
    assert "33L・2.7kg" in frequenter["statement"]
    assert "交換可能な車輪" in frequenter["statement"]
    assert "奥行23m" not in frequenter["statement"]
    assert "dimensions" not in frequenter
    assert c_lite["dimensions"] == [
        {
            "subject": "Samsonite C-Lite 134679-1549（通常時）",
            "width_cm": 40,
            "depth_cm": 20,
            "height_cm": 55,
        },
        {
            "subject": "Samsonite C-Lite 134679-1549（拡張時）",
            "width_cm": 40,
            "depth_cm": 23,
            "height_cm": 55,
        },
    ]
    assert all(
        set(dimensions) == {"subject", "width_cm", "depth_cm", "height_cm"}
        for claim in claims.values()
        for dimensions in claim.get("dimensions", [])
    )


def test_source_hashes_are_bound_to_all_ten_packet_claims() -> None:
    registry = _load(SOURCE_PATH)
    sources = {source["source_ref"]: source for source in registry["sources"]}
    all_claims = {
        claim["claim_id"]: claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }

    for source in sources.values():
        parsed = urlsplit(source["url"])
        assert parsed.scheme == "https"
        assert parsed.hostname in ALLOWED_SOURCE_HOSTS
        assert parsed.fragment == ""
        assert source["capture_status"] == "STRUCTURED_FACT_SNAPSHOT_CAPTURED"
        assert source["review_body_excluded_from_claim_evidence"] is True
        claims = [
            {
                **{
                    key: claim[key]
                    for key in (
                        "claim_id",
                        "classification",
                        "statement",
                        "status",
                        "subject_product_ids",
                    )
                },
                **{
                    key: claim[key]
                    for key in SOURCE_CAPTURE_CLAIM_OPTIONAL_KEYS
                    if key in claim
                },
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
    source_document = _load(SOURCE_PATH)
    sources = {source["source_ref"]: source for source in source_document["sources"]}
    packets = {
        packet["source_packet_ref"]: packet
        for packet in source_document["source_packets"]
    }
    expected_article_check_dates = {
        "st1703-first-suitcase-comparison": "2026-09-01",
        "st1704-portable-power-station-guide": "2026-09-01",
        "st1704-anker-solix-c300-c800-c1000-differences": "2026-09-01",
        "st1704-countertop-dishwasher-for-small-households": "2026-09-01",
        "st1704-compact-robot-vacuum-shortlist": "2026-09-01",
    }
    for article in collection["articles"]:
        article_id = article["article_id"]
        facts_checked_on = article["freshness"]["facts_checked_on"]
        assert facts_checked_on == expected_article_check_dates[article_id]
        packet = packets[article["source_packet_ref"]]
        assert facts_checked_on >= max(
            sources[source_ref]["retrieved_on"] for source_ref in packet["source_refs"]
        )
        render = cast(dict[str, object], article["render_model"])
        presentation = cast(dict[str, object], render["presentation"])
        assert set(presentation) == {
            "fact_checker",
            "first_hand_test",
            "reader_summary",
            "scope_label",
            "scope_note",
        }
        assert presentation["fact_checker"] == "暮らしのしるべ編集者（一次情報確認）"
        assert presentation["first_hand_test"] == "未実施（公式仕様比較）"
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
            assert detail["facts_checked_on"] >= max(
                sources[source_ref]["retrieved_on"]
                for source_ref in card["source_refs"]
            )
            assert (
                detail["facts_checked_on"] <= article["freshness"]["facts_checked_on"]
            )
            assert detail["official_source_ref"] in card["source_refs"]
            assert cast(list[object], detail["fits"])
            assert cast(list[object], detail["not_fits"])
            assert detail["benefit"] != detail["recommendation_reason"]
            assert card["caution"] not in cast(list[object], detail["not_fits"])
            anchor = cast(str, detail["detail_anchor"])
            assert anchor not in anchors
            anchors.add(anchor)

        recommendations = {
            value["recommendation_ref"]: value for value in render["recommendations"]
        }
        cards_by_ref = {value["product_selection_ref"]: value for value in cards}
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


def test_all_ten_reader_facing_articles_use_one_metadata_vocabulary() -> None:
    forbidden_ornamental_labels = (
        "INTRODUCTION",
        "THE SHORT ANSWER",
        "WHO THIS IS FOR",
        "HOW WE COMPARED",
        "AT A GLANCE",
        "FOUR PORTRAITS",
        "EDITOR'S NOTE",
        "NOTES &amp; SOURCES",
    )
    for slug in ALL_ARTICLE_SLUGS:
        markup = (WORDPRESS_ARTICLE_ROOT / f"{slug}.html").read_text(encoding="utf-8")
        assert markup.count("<dt>対象読者</dt>") == 1
        assert markup.count("<dt>比較範囲</dt>") == 1
        assert markup.count("<dt>執筆担当</dt><dd>暮らしのしるべ編集者</dd>") == 1
        assert (
            markup.count(
                "<dt>事実確認担当</dt><dd>暮らしのしるべ編集者（一次情報確認）</dd>"
            )
            == 1
        )
        assert markup.count("<dt>最終確認日</dt>") == 1
        assert markup.count("<dt>実機確認</dt><dd>未実施（公式仕様比較）</dd>") == 1
        assert not any(label in markup for label in forbidden_ornamental_labels)


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

    assert len(placements) == 22
    assert len({card["product_id"] for _, card in placements}) == 21
    assert len(affiliates) == len(assets) == 21
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
    assert len(pending) == 21
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
        first_hand_claim_check = editorial.replace("実機で検証していない", "")
        assert not any(
            phrase in first_hand_claim_check
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
    unknown_dimensions: set[tuple[str, str]] = set()
    collection = _load(CONTENT_PATH)

    for article in collection["articles"]:
        article_text = " ".join(_strings(article))
        for forbidden in forbidden_copy:
            assert forbidden not in article_text
        assert "<br" not in article_text.casefold()
        assert (
            article["render_model"]["disclosure"]["paragraphs"] == expected_disclosure
        )
        for table in article["render_model"]["comparison_tables"]:
            for row in table["rows"]:
                for cell in row["cells"]:
                    if cell["axis_ref"] not in dimension_axes:
                        continue
                    observed_dimensions += 1
                    if cell["state"] == "UNKNOWN":
                        unknown_dimensions.add(
                            (row["product_selection_ref"], cell["axis_ref"])
                        )
                        if (
                            row["product_selection_ref"],
                            cell["axis_ref"],
                        ) == ("PSEL-ROBOT-K10-COMBO", "AXIS-ROBOT-STATION"):
                            assert cell["claim_ids"] == [
                                "CLM-ST1704-ROBOT-K10-COMBO-SPECS"
                            ]
                            assert "各数値の軸は未確認" in cell["value"]
                        else:
                            assert cell["claim_ids"] == []
                        assert "推奨根拠に不使用" in cell["value"]
                        continue
                    assert cell["state"] == "KNOWN"
                    if (
                        row["product_selection_ref"],
                        cell["axis_ref"],
                    ) == ("PSEL-DISH-NP-TSP2", "AXIS-DISH-SIZE"):
                        assert cell["value"] == (
                            "本体 幅約55×奥行約34.1×高さ約60cm／"
                            "扉開放時 奥行約43.3×高さ約71.2cm"
                        )
                    else:
                        assert dimension_pattern.fullmatch(cell["value"])

    assert observed_dimensions == 26
    assert unknown_dimensions == set()
    collection_text = CONTENT_PATH.read_text(encoding="utf-8")
    assert "購入する本体・付属品・ソーラーパネル・接続機器の型番" in collection_text
    assert "公式対応情報と取扱説明書で照合してください" in collection_text
    articles = {article["article_id"]: article for article in collection["articles"]}
    dishwasher = articles["st1704-countertop-dishwasher-for-small-households"]
    dishwasher_text = " ".join(_strings(dishwasher))
    assert "食洗機4候補を公式仕様で比較" in dishwasher["seo"]["meta_description"]
    assert "SOLOTAは販売状態未確認の仕様参考" in dishwasher["seo"]["meta_description"]
    for formal_name in (
        "SOLOTA NP-TMLK1-K",
        "THANKO ラクアmini TK-MDW22W",
        "siroca 食器洗い乾燥機 SS-MA251",
        "東芝 食器洗い乾燥機 DWS-33B(W)",
    ):
        assert formal_name in dishwasher_text
    assert (
        "以降は順に「SS-M171」「ラクアmini」「SS-MA251」「DWS-33B」と表記します。"
    ) in dishwasher_text
    assert [
        card["product_name"] for card in dishwasher["render_model"]["product_cards"]
    ] == [
        "siroca SS-M171",
        "THANKO ラクアmini TK-MDW22W",
        "SS-MA251",
        "東芝 DWS-33B(W)",
    ]
    suitcase = articles["st1703-first-suitcase-comparison"]
    suitcase_lead = suitcase["content_ast"]["blocks"][1]
    assert suitcase_lead["type"] == "lead"
    assert "軽さ" in suitcase_lead["content"][0]["text"]
    assert "開け" in suitcase_lead["content"][0]["text"]
    robot = articles["st1704-compact-robot-vacuum-shortlist"]
    robot_text = " ".join(_strings(robot))
    assert (
        "Anker「Eufy Robot Vacuum Auto-Empty C10」（ブラック・型番T2292511）"
    ) in robot_text
    assert (
        "iRobot「Roomba Plus 515 Combo ロボット + "
        "AutoWash 充電ステーション」（型番：N285060）"
    ) in robot_text
    assert "ECOVACS DEEBOT mini 2" in robot_text
    assert "小径本体、薄型本体、モップ自動手入れ" in robot_text
    assert "幅条件" not in robot_text
    power_text = " ".join(_strings(articles["st1704-portable-power-station-guide"]))
    assert "約5.7kg" not in power_text
    assert power_text.count("5.7kg") >= 7
    assert "容量（Wh）÷消費電力（W）" in power_text
    assert "AC変換損失" in power_text
    assert "起動時電力" in power_text

    suitcase_text = " ".join(_strings(articles["st1703-first-suitcase-comparison"]))
    assert "メーカー公式通販では在庫切れ" not in suitcase_text
    assert "メーカー公式通販の販売再開" not in suitcase_text
    assert "現在の販売状況" in suitcase_text

    anker_text = " ".join(
        _strings(articles["st1704-anker-solix-c300-c800-c1000-differences"])
    )
    for official_difference in (
        "別売り拡張バッテリー",
        "AC出力6口",
        "SurgePad 2000W",
        "4,000回以上の充放電サイクル",
        "USB-C 3口",
        "拡張バッテリーには対応しません",
    ):
        assert official_difference in anker_text
    assert "公式ページ内に約0.01秒と約0.02秒の記載が併存" in anker_text
    assert "停電時約10ミリ秒切り替え" not in anker_text

    assert "標準食器点数は各社の想定した食器構成による参考値" in dishwasher_text
    assert "18点モデルを1〜2人向けの上位候補と決め打ちせず" in dishwasher_text
    assert "公式設置案内の帰還余白" in robot_text
    assert "Eufy C10は本体高さ7.2cm" in robot_text
    assert "本体の床面はK11+ Proより広い" in robot_text


def test_internal_routes_are_closed_without_forced_low_relevance_pairs() -> None:
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
        assert len(links[article["article_id"]]) <= 2
    assert (
        "ROUTE-ARTICLE-ANKER-DIFFERENCES"
        in links["st1704-portable-power-station-guide"]
    )
    assert (
        "ROUTE-ARTICLE-PORTABLE-POWER"
        in links["st1704-anker-solix-c300-c800-c1000-differences"]
    )
    assert links["st1704-countertop-dishwasher-for-small-households"] == {
        "ROUTE-HOME-GUIDES"
    }
    assert links["st1704-compact-robot-vacuum-shortlist"] == {"ROUTE-HOME-GUIDES"}


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
    relative_language = re.compile(r"最軽量|最も軽|最小|最大(?!連続)|中間|条件から外")
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
            if all(claim_id.endswith("-EXCLUDED") for claim_id in claims):
                continue
            if relative_language.search(material):
                observed_relative_records += 1
                assert required <= claims
            if carry_on_exclusion.search(material):
                observed_carry_on_records += 1
                assert "CLM-ST1704-SUITCASE-CARRYON-LIMITS" in claims

    # The former K10+ station comparisons were deliberately removed because the
    # official page lists three numbers without defining their axes.  The closed
    # five-article projection currently contains fourteen supported relative
    # comparison records; keep a floor so later copy edits cannot silently drop
    # the evidence-binding coverage altogether.
    assert observed_relative_records >= 14
    assert observed_carry_on_records == 2


def test_verified_jackery_dimensions_and_replacement_product_facts_remain_bound() -> (
    None
):
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
        "value": "熱風乾燥",
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


def test_excluded_candidates_and_selected_robot_dimension_semantics() -> None:
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
    assert "幅20.0×奥行39.8×高さ28.3cm" not in collection_text
    assert "幅39.8×奥行20.0×高さ28.3cm" not in collection_text
    delta_exclusion = claims["CLM-ST1704-POWER-DELTA3-CLASSIC-EXCLUDED"]
    assert delta_exclusion["classification"] == "EDITORIAL_INFERENCE"
    assert delta_exclusion["evidence_level"] == "D"
    assert "売り切れ" in delta_exclusion["statement"]
    assert "埋め込み構造化状態" in delta_exclusion["statement"]
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
    k11_warranty = claims["CLM-ST1704-ROBOT-K11-PRO-WARRANTY-UNRESOLVED"]
    assert k11_warranty["classification"] == "EDITORIAL_INFERENCE"
    assert k11_warranty["evidence_level"] == "D"
    assert "1年または2年" in k11_warranty["statement"]
    assert "推奨根拠に使わず" in k11_warranty["statement"]
    assert k11_warranty["evidence_refs"] == ["SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY"]
    assert (
        source_by_ref["SRC-SWITCHBOT-K11-PRO-EXTENDED-WARRANTY"]["retrieved_on"]
        == "2026-09-01"
    )
    deebot_claim = claims["CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS"]
    assert source_by_ref["SRC-ECOVACS-DEEBOT-MINI2"]["retrieved_on"] == ("2026-09-01")
    assert "ビデオマネージャー" in deebot_claim["statement"]
    assert "外出先からの見守り" in deebot_claim["statement"]
    assert "スクリーンショット" in deebot_claim["statement"]
    k10_exclusion = claims["CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED"]
    assert "幅・奥行・高さの軸ラベルがなく" in k10_exclusion["statement"]
    assert k10_exclusion.get("dimensions", []) == []
    assert claims["CLM-ST1704-ROBOT-EUFY-C10-SPECS"]["dimensions"] == [
        {
            "subject": "Eufy Auto-Empty C10本体 T2292511",
            "width_cm": 32.5,
            "depth_cm": 32.3,
            "height_cm": 7.2,
        },
        {
            "subject": "Eufy Auto-Empty C10ステーション",
            "width_cm": 27.5,
            "depth_cm": 19.1,
            "height_cm": 21.2,
        },
    ]
    assert claims["CLM-ST1704-ROBOT-ROOMBA-515-SPECS"]["dimensions"] == [
        {
            "subject": "ルンバ本体",
            "width_cm": 29.8,
            "depth_cm": 30.3,
            "height_cm": 8.4,
        },
        {
            "subject": "AutoWash充電ステーション",
            "width_cm": 33.0,
            "depth_cm": 34.0,
            "height_cm": 48.5,
        },
    ]
    assert all(
        not any(key in claim for key in ("dimension_values", "dimensions_cm"))
        for claim in claims.values()
    )
    robot = next(
        article
        for article in _load(CONTENT_PATH)["articles"]
        if article["article_id"] == "st1704-compact-robot-vacuum-shortlist"
    )
    robot_text = " ".join(_strings(robot))
    assert "ステーションは幅32.0×奥行40.0×高さ38.5cm" in robot_text
    assert "AXIS-ROBOT-CONNECTED-PRIVACY" in json.dumps(robot, ensure_ascii=False)
    assert "カメラ・音声・アプリ利用を許容するか" in robot_text
    assert "住居内の遠隔見守り・声かけ・スクリーンショット機能" in robot_text
    assert "無償保証が1年か2年かを特定できない" in robot_text
    assert "最大底面辺" in robot_text
    assert "公式表記順" not in robot_text
    assert "ステーションは幅27.5×奥行19.1×高さ21.2cm" in robot_text
    assert "ステーションは幅21.2×奥行17.8cm" not in robot_text
    assert "ステーションは幅17.8×奥行21.2cm" not in robot_text
    assert "幅24.0×奥行18.0×高さ25.0cm" in robot_text
    assert "幅19.5×奥行29.7×高さ41.0cm" not in robot_text
    assert "ステーションの最大底面辺は29.7cm" not in robot_text
    assert "195×297×410mm" not in robot_text
    assert "ステーション寸法の軸も未確認" in robot_text
    k10_station_cells = [
        candidate
        for table in robot["render_model"]["comparison_tables"]
        for row in table["rows"]
        if row["product_selection_ref"] == "PSEL-ROBOT-K10-COMBO"
        for candidate in row["cells"]
        if candidate["axis_ref"] == "AXIS-ROBOT-STATION"
    ]
    assert k10_station_cells == []
    deebot_station_cells = [
        candidate
        for table in robot["render_model"]["comparison_tables"]
        for row in table["rows"]
        if row["product_selection_ref"] == "PSEL-ROBOT-DEEBOT-MINI2"
        for candidate in row["cells"]
        if candidate["axis_ref"] == "AXIS-ROBOT-STATION"
    ]
    assert deebot_station_cells == [
        {
            "axis_ref": "AXIS-ROBOT-STATION",
            "value": "幅32.0×奥行40.0×高さ38.5cm",
            "claim_ids": ["CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS"],
            "state": "KNOWN",
        }
    ]
