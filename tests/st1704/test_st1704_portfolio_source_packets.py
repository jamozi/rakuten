"""Direct contracts for the ten-article source-packet owner."""

from __future__ import annotations

from copy import deepcopy
import json

import pytest

from scripts import build_st1704_portfolio_source_packets as owner


def _documents() -> tuple[dict[str, object], dict[str, object]]:
    registry_raw, locator_raw = owner._documents()
    return json.loads(registry_raw), json.loads(locator_raw)


def _packets(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {packet["article_id"]: packet for packet in registry["source_packets"]}


def _claims(registry: dict[str, object]) -> dict[str, dict[str, object]]:
    return {
        claim["claim_id"]: claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
    }


def test_toshiba_locators_bind_values_to_their_specification_rows() -> None:
    _registry, locator = _documents()
    sources = {source["source_ref"]: source for source in locator["sources"]}
    expected = {
        "SRC-TOSHIBA-DWS-33B": {
            '<h1><div class="text">DWS-33B</div></h1>',
            "<tr><th>外形寸法</th><td>420(幅)×435(奥行)×465(高さ)mm</td></tr>",
            "<tr><th>使用水量</th><td>約6L</td></tr>",
            "<tr><th>乾燥方式</th><td>ヒーターとファンによる強制排気乾燥</td></tr>",
            "<tr><th>運転音<sup>※8</sup>(50Hz/60Hz)</th><td>約41dB/約43dB</td></tr>",
        },
        "SRC-TOSHIBA-PARTS-RETENTION": {
            '<tr><th class="th-2"><big><b>食器洗い乾燥機</b></big></th><th class="th-2"><big><b>６年</b></big></th></tr>',
        },
    }
    obsolete = {"幅420×奥行435×高さ465mm", "41／43dB", "6年"}
    for source_ref, required in expected.items():
        for item in sources[source_ref]["locators"]:
            fragments = set(item["exact_utf8_fragments"])
            assert required <= fragments
            assert not fragments & obsolete


@pytest.mark.parametrize(
    ("source_ref", "required", "ambiguous"),
    (
        (
            "SRC-ANKER-SOLIX-C800",
            {
                owner.ANKER_STOCK_BOUND_PURCHASE_FRAGMENT,
                "<h2>業界最高水準の高出力<sup>※</sup>\n</h2>\n<p>768Whの中容量帯ながら、1200Wを安定して出力できる",
                '<td class="product-specs-heading">サイズ</td>\n                  <td>約37.1 x 20.5 x 25.0cm （ 幅 x 奥行 x 高さ )</td>',
                '<td class="product-specs-heading">重さ</td>\n                <td>約10.5kg</td>',
                "<p><small>※電池容量が初期容量の80%まで劣化するまでのサイクル回数は3,000回以上",
                "<h3>購入後も安心のアフターサービス</h3>\n<p>専門スタッフのサポートや、ご使用済みポータブル電源の回収サービス",
            },
            {
                'aria-label="カートに入れる"',
                "768Whの中容量帯ながら、1200Wを安定して出力できる",
                "約37.1 x 20.5 x 25.0cm （ 幅 x 奥行 x 高さ )",
                "約10.5kg",
                "電池容量が初期容量の80%まで劣化するまでのサイクル回数は3,000回以上",
                "ご使用済みポータブル電源の回収サービス",
            },
        ),
        (
            "SRC-EUFY-AUTOEMPTY-C10-T2292",
            {"<h2>吸引は強力、角まで綺麗に</h2>\n<p>最大4000Paの強力な吸引力"},
            {"最大4000Paの強力な吸引力"},
        ),
    ),
)
def test_anker_repeated_claims_are_bound_to_visible_sections(
    source_ref: str, required: set[str], ambiguous: set[str]
) -> None:
    """A repeated spec, metadata description, or footer is not a unique locator."""
    _registry, locator = _documents()
    source = next(row for row in locator["sources"] if row["source_ref"] == source_ref)
    for item in source["locators"]:
        fragments = set(item["exact_utf8_fragments"])
        assert required <= fragments
        assert not fragments & ambiguous


def test_locator_text_fragments_reject_embedded_meta_markup() -> None:
    _registry, locator = _documents()
    owner._validate_locator_text_fragments(locator)
    gen2 = next(
        source
        for source in locator["sources"]
        if source["source_ref"] == "SRC-ANKER-SOLIX-C1000-GEN2"
    )
    feature = next(
        item
        for item in gen2["locators"]
        if item["claim_id"] == "CLM-ST1704-ANKER-C1000-FEATURE-DIFF"
    )
    assert "停電時に約0.01秒で自動切り替えする機能搭載" in feature[
        "exact_utf8_fragments"
    ]
    assert all(
        "<meta" not in fragment.lower()
        for fragment in feature["exact_utf8_fragments"]
        if not fragment.lstrip().lower().startswith("<meta")
    )

    tampered = deepcopy(locator)
    tampered_gen2 = next(
        source
        for source in tampered["sources"]
        if source["source_ref"] == "SRC-ANKER-SOLIX-C1000-GEN2"
    )
    tampered_feature = next(
        item
        for item in tampered_gen2["locators"]
        if item["claim_id"] == "CLM-ST1704-ANKER-C1000-FEATURE-DIFF"
    )
    tampered_feature["exact_utf8_fragments"][0] = (
        '停電時に約<meta charset="utf-8">0.01秒で自動切り替え'
    )
    with pytest.raises(ValueError, match="embedded <meta markup"):
        owner._validate_locator_text_fragments(tampered)


def test_exact_model_claim_rejects_sibling_sku_binding() -> None:
    registry, _locator = _documents()
    owner._validate_exact_model_claim_bindings(registry)

    tampered = deepcopy(registry)
    claim = _claims(tampered)["CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060"]
    claim["statement"] = f"{claim['statement']} 別SKU F115260の固有仕様。"
    with pytest.raises(ValueError, match="exact model is outside subject product scope"):
        owner._validate_exact_model_claim_bindings(tampered)


def test_html_used_primary_sources_are_packet_locator_and_hash_bound() -> None:
    registry, locator = _documents()
    sources = {source["source_ref"]: source for source in registry["sources"]}
    packets = _packets(registry)
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    expected_sources = {
        "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY": (
            "https://store.irobot-jp.com/item/F155260.html",
            "2026-08-31",
        ),
        "SRC-EUFY-AUTOEMPTY-C10-T2292": (
            "https://www.ankerjapan.com/products/t2292",
            "2026-08-31",
        ),
        "SRC-ANA-DOMESTIC-CARRY-ON": (
            "https://www.ana.co.jp/ja/jp/guide/boarding-procedures/"
            "baggage/domestic/carry-rule/",
            "2026-08-29",
        ),
        "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE": (
            "https://support.switch-bot.com/hc/en-us/articles/"
            "14956880082967-How-Much-Space-Should-Be-Left-When-Installing-"
            "the-Auto-Empty-Station-for-SwitchBot-Mini-Robot-Vacuum-"
            "K10-K10-Pro-K11-K11-Pro",
            "2026-08-30",
        ),
        "SRC-PANASONIC-NP-TMLK1": (
            "https://panasonic.jp/dish/products/NP-TMLK1.html",
            "2026-08-23",
        ),
    }
    for source_ref, (url, retrieved_on) in expected_sources.items():
        source = sources[source_ref]
        assert source["url"] == url
        assert source["retrieved_on"] == retrieved_on
        assert source["immutable_capture_sha256"] == owner._source_capture_hash(
            source,
            [
                claim
                for claim in claims.values()
                if source_ref in claim["evidence_refs"]
            ],
        )
        locator_source = locator_sources[source_ref]
        assert locator_source["locator_status"] == "READY"
        assert locator_source["locators"]
        assert all(item["exact_utf8_fragments"] for item in locator_source["locators"])

    expected_packet_sources = {
        "carry-on-suitcase-under-100-seats": {
            "SRC-ANA-DOMESTIC-CARRY-ON",
        },
        "lightweight-carry-on-suitcase-under-3kg": {
            "SRC-ANA-DOMESTIC-CARRY-ON",
        },
        "front-open-carry-on-suitcase-with-stopper": {
            "SRC-ANA-DOMESTIC-CARRY-ON",
        },
        "roomba-mini-vs-switchbot-k11-pro": {
            "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060",
            "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE",
        },
        "solota-vs-rakua-mini-plus": {"SRC-PANASONIC-NP-TMLK1"},
    }
    for article_id, required in expected_packet_sources.items():
        packet = packets[article_id]
        assert required <= set(packet["source_refs"])
        assert packet["fact_packet_sha256"] == owner._packet_hash(packet)

    required_claims = {
        "CLM-PORTFOLIO-UNDER100-ANA-RULE": "SRC-ANA-DOMESTIC-CARRY-ON",
        "CLM-PORTFOLIO-LIGHT-ANA-RULE": "SRC-ANA-DOMESTIC-CARRY-ON",
        "CLM-PORTFOLIO-FRONT-ANA-RULE": "SRC-ANA-DOMESTIC-CARRY-ON",
        "CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060": (
            "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060"
        ),
        "CLM-PORTFOLIO-ROBOT-K11-INSTALLATION-SPACE": (
            "SRC-SWITCHBOT-AUTOEMPTY-INSTALLATION-SPACE"
        ),
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE": ("SRC-PANASONIC-NP-TMLK1"),
    }
    for claim_id, source_ref in required_claims.items():
        assert claims[claim_id]["evidence_refs"] == [source_ref]
        assert any(
            item["claim_id"] == claim_id
            for item in locator_sources[source_ref]["locators"]
        )

    assert locator["source_registry_sha256"] == owner._canonical_sha256(registry)


def test_rebuild_preserves_existing_observation_dates() -> None:
    tracked = json.loads(owner.REGISTRY_PATH.read_text(encoding="utf-8"))
    generated, _locator = _documents()
    tracked_dates = {
        source["source_ref"]: source["retrieved_on"] for source in tracked["sources"]
    }
    generated_dates = {
        source["source_ref"]: source["retrieved_on"] for source in generated["sources"]
    }
    for source in owner.NEW_SOURCES:
        source_ref = source["source_ref"]
        if source_ref in tracked_dates:
            assert generated_dates[source_ref] == tracked_dates[source_ref]


def test_claim_subjects_are_explicit_closed_and_packet_scoped() -> None:
    registry, _locator = _documents()
    claims = _claims(registry)
    assert set(claims) == set(owner.CLAIM_SUBJECT_PRODUCT_IDS)
    for claim_id, expected in owner.CLAIM_SUBJECT_PRODUCT_IDS.items():
        assert claims[claim_id]["subject_product_ids"] == list(expected)
    owner._validate_claim_subject_contract(registry)

    outside = deepcopy(registry)
    _claims(outside)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"][
        "subject_product_ids"
    ] = ["PRD-ANKER-SOLIX-C300"]
    with pytest.raises(ValueError, match="outside packet product scope"):
        owner._validate_claim_subject_contract(outside)

    empty = deepcopy(registry)
    _claims(empty)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"]["subject_product_ids"] = []
    with pytest.raises(ValueError, match="product claim subject cannot be empty"):
        owner._validate_claim_subject_contract(empty)

    duplicate = deepcopy(registry)
    _claims(duplicate)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"][
        "subject_product_ids"
    ] = ["PRD-PROTECA-TRI-AIR-01541", "PRD-PROTECA-TRI-AIR-01541"]
    with pytest.raises(ValueError, match="duplicate claim subject product"):
        owner._validate_claim_subject_contract(duplicate)

    wrong_sibling = deepcopy(registry)
    _claims(wrong_sibling)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"][
        "subject_product_ids"
    ] = ["PRD-ACE-DIFFERENCE-05721"]
    with pytest.raises(ValueError, match="claim subject product mismatch"):
        owner._validate_claim_subject_contract(wrong_sibling)


def test_decision_critical_dimensions_are_named_and_deebot_axes_are_explicit() -> None:
    registry, _locator = _documents()
    claims = _claims(registry)

    for claim_id, expected_dimensions in owner.FIRST_FIVE_DIMENSION_CLAIMS.items():
        assert claims[claim_id]["dimensions"] == [
            dict(value) for value in expected_dimensions
        ]
    for claim in claims.values():
        assert "dimension_values" not in claim
        assert "dimensions_cm" not in claim
        for dimensions in claim.get("dimensions", []):
            assert set(dimensions) == {
                "subject",
                "width_cm",
                "depth_cm",
                "height_cm",
            }

    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    external_claim_ids = {
        (article["article_id"], candidate["candidate_id"]): (
            owner.MARKET_CANDIDATE_CLAIM_IDS[
                (article["article_id"], candidate["candidate_id"])
            ]
        )
        for article in audit["articles"]
        for candidate in article["considered_external_candidates"]
    }
    for key, expected_dimensions in owner.MARKET_CANDIDATE_DIMENSIONS.items():
        claim = claims[external_claim_ids[key]]
        assert claim["dimensions"] == [
            dict(value) for value in expected_dimensions
        ]
    assert (
        "dimensions"
        not in claims["CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED"]
    )

    assert claims["CLM-ST1704-POWER-DJI-1000-V2-SPECS"]["dimensions"] == [
        {
            "subject": "DJI Power 1000 V2本体（公式L×W×Hを幅・奥行・高さへ正規化）",
            "width_cm": 22.5,
            "depth_cm": 44.8,
            "height_cm": 23.0,
        }
    ]
    assert claims["CLM-ST1704-POWER-ANKER-C800-SPECS"]["dimensions"] == [
        {
            "subject": "Anker Solix C800本体",
            "width_cm": 37.1,
            "depth_cm": 20.5,
            "height_cm": 25.0,
        }
    ]

    deebot = claims["CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS"]
    assert deebot["dimensions"] == [
        {
            "subject": "ECOVACS DEEBOT mini 2本体",
            "width_cm": 28.6,
            "depth_cm": 28.6,
            "height_cm": 9.98,
        },
        {
            "subject": "ECOVACS DEEBOT mini 2ステーション",
            "width_cm": 32.0,
            "depth_cm": 40.0,
            "height_cm": 38.5,
        },
    ]
    assert "10000Pa" in deebot["statement"]
    assert "63℃熱風乾燥" in deebot["statement"]
    robot_decision = claims["CLM-ST1704-ROBOT-CONDITIONAL-CHOICES"]
    assert "29.7cm" not in robot_decision["statement"]
    assert "現行4候補から除外" in robot_decision["statement"]
    assert "Eufy Auto-Empty C10" in robot_decision["statement"]
    assert "幅32.5×奥行32.3×高さ7.2cm" in robot_decision["statement"]
    assert "ステーションが幅27.5×奥行19.1×高さ21.2cm" in robot_decision[
        "statement"
    ]
    assert "Roomba Plus 515 Comboは本体29.8×30.3×8.4cm" in robot_decision[
        "statement"
    ]
    assert "薄型本体と設置面積を混同しない" in robot_decision["statement"]
    assert "4モデルで設置面積が最大" not in robot_decision["statement"]
    assert all(
        "K10+ Pro Combo" not in dimensions["subject"]
        for dimensions in robot_decision["dimensions"]
    )


def test_dimension_contract_rejects_unlabeled_or_missing_deebot_station_axes() -> None:
    registry, _locator = _documents()

    for legacy_key in ("dimension_values", "legacy_axis_values"):
        unlabeled = deepcopy(registry)
        _claims(unlabeled)["CLM-ST1704-POWER-C300-SPECS"][legacy_key] = [
            16.4,
            16.1,
            24.0,
        ]
        with pytest.raises(ValueError, match="unlabeled three-value"):
            owner._validate_dimension_contract(unlabeled)

    missing_station = deepcopy(registry)
    _claims(missing_station)["CLM-ST1704-ROBOT-DEEBOT-MINI2-SPECS"]["dimensions"].pop()
    with pytest.raises(ValueError, match="body and station axes must remain explicit"):
        owner._validate_dimension_contract(missing_station)

    missing_market_axes = deepcopy(registry)
    _claims(missing_market_axes)["CLM-ST1704-ROBOT-SAROS10-EXCLUDED"].pop(
        "dimensions"
    )
    with pytest.raises(ValueError, match="market candidate dimension mismatch"):
        owner._validate_dimension_contract(missing_market_axes)

    inferred_decision_copy = deepcopy(registry)
    inferred_decision = _claims(inferred_decision_copy)[
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES"
    ]
    inferred_decision["statement"] += (
        " K10+ Pro Comboのステーションは幅29.7×奥行19.5×高さ41.0cmである。"
    )
    with pytest.raises(ValueError, match="decision claim"):
        owner._validate_dimension_contract(inferred_decision_copy)


def test_source_capture_hash_binds_named_dimension_values_and_axes() -> None:
    registry, _locator = _documents()
    source_ref = "SRC-ACE-DIFFERENCE-05721"
    source = next(
        value for value in registry["sources"] if value["source_ref"] == source_ref
    )
    bound_claims = [
        claim
        for packet in registry["source_packets"]
        for claim in packet["claims"]
        if source_ref in claim["evidence_refs"]
    ]
    baseline = owner._source_capture_hash(source, bound_claims)
    assert baseline == source["immutable_capture_sha256"]

    tampered_claims = deepcopy(bound_claims)
    difference = next(
        claim
        for claim in tampered_claims
        if claim["claim_id"] == "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS"
    )
    difference["dimensions"][0]["width_cm"] = 999
    assert owner._source_capture_hash(source, tampered_claims) != baseline


def test_later_article_selection_facts_are_bound_or_explicitly_unconfirmed() -> None:
    registry, locator = _documents()
    packets = _packets(registry)
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    expected_claim_tokens = {
        "CLM-PORTFOLIO-UNDER100-CONDITIONAL-CHOICES": (
            "100席以上便",
            "1cm",
            "高さと奥行は各辺の上限と同じ",
        ),
        "CLM-PORTFOLIO-LIGHT-CONDITIONAL-CHOICES": (
            "30L以上・3kg以下",
            "APPLITE 4.0の38Lが5候補で最大",
            "C-Liteが2.1kg",
            "拡張時42L",
        ),
        "CLM-PORTFOLIO-FRONT-INNOVATOR-INV50": ("ワイドオープン",),
        "CLM-PORTFOLIO-FRONT-BERMAS-60570": (
            "W36×H54×D24cm",
            "2in1構造",
            "55mm静音キャスター",
        ),
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE": (
            "NP-TMLK1-K",
            "正確な型番",
        ),
        "CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED": (
            "再入荷通知",
            "商品カードや購入導線",
        ),
        "CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE": (
            "以前の比較対象2機種はいずれも仕様参考に限定",
            "現行品の仕様表",
            "商品カード、購入導線",
            "少人数向け卓上食洗機4候補の記事へ集約",
        ),
    }
    for claim_id, tokens in expected_claim_tokens.items():
        claim = claims[claim_id]
        assert all(token in claim["statement"] for token in tokens)
        for source_ref in claim["evidence_refs"]:
            assert any(
                item["claim_id"] == claim_id
                for item in locator_sources[source_ref]["locators"]
            )

    selected = claims["CLM-PORTFOLIO-FRONT-BERMAS-60570"]
    assert selected["subject_product_ids"] == [
        "PRD-BERMAS-INTER-CITY-III-60570"
    ]
    assert selected["dimensions"] == [
        {
            "subject": "INTER CITY III 60570",
            "width_cm": 36,
            "depth_cm": 24,
            "height_cm": 54,
        }
    ]
    old_model = claims["CLM-PORTFOLIO-FRONT-BERMAS-60561-EXCLUDED"]
    assert old_model["market_candidate_id"] == "EXT-BERMAS-INTER-CITY-II-60561"
    assert old_model["effective_lifecycle"] == "AVAILABLE"
    assert "終売を意味しません" in old_model["statement"]
    assert "終売のため" not in old_model["statement"]
    assert old_model["dimensions"] == [
        {
            "subject": "BERMAS INTER CITY II 60561",
            "width_cm": 35.0,
            "depth_cm": 25.0,
            "height_cm": 55.0,
        }
    ]
    front_packet = packets["front-open-carry-on-suitcase-with-stopper"]
    assert "SRC-ANA-MOBILE-BATTERY-2026" not in front_packet["source_refs"]
    assert "USB" not in selected["statement"]
    assert "USB" not in claims["CLM-PORTFOLIO-FRONT-CONDITIONAL-CHOICES"][
        "statement"
    ]


def test_c_lite_is_selected_and_frequenter_is_reference_only() -> None:
    registry, locator = _documents()
    packets = _packets(registry)
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}
    article_id = "lightweight-carry-on-suitcase-under-3kg"
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    audit_article = next(
        article for article in audit["articles"] if article["article_id"] == article_id
    )

    c_lite_id = "PRD-SAMSONITE-C-LITE-SPINNER55EXP-134679-1549"
    frequenter_id = "PRD-FREQUENTER-LIEVE-1-250"
    assert c_lite_id in audit_article["selected_product_ids"]
    assert frequenter_id not in audit_article["selected_product_ids"]
    candidate = next(
        value
        for value in audit_article["considered_external_candidates"]
        if value["candidate_id"]
        == "EXT-FREQUENTER-LIEVE-1-250-MAINTAINABILITY"
    )
    assert "交換可能な車輪" in candidate["reason"]

    c_lite = claims["CLM-PORTFOLIO-LIGHT-SAMSONITE-C-LITE-134679-1549"]
    assert c_lite["subject_product_ids"] == [c_lite_id]
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
    for token in (
        "SKU CS2*31007",
        "36L",
        "42L",
        "2.1kg",
        "条件付き10年保証",
        "電子機器部分は購入後1年",
        "カートに入れる",
    ):
        assert token in c_lite["statement"]
    assert c_lite["manufacturer_sales_state"] == (
        owner.C_LITE_134679_1549_SALES_STATE
    )
    manufacturer_sales_state = json.loads(
        owner.MANUFACTURER_SALES_STATE_PATH.read_text(encoding="utf-8")
    )
    c_lite_mss = next(
        row
        for row in manufacturer_sales_state["products"]
        if row["product_id"] == c_lite_id
    )
    assert c_lite["manufacturer_sales_state"]["product_id"] == c_lite_id
    assert (
        c_lite["manufacturer_sales_state"]["reader_visible_label"]
        == "カートに入れる"
    )
    assert c_lite["manufacturer_sales_state"]["variant_caveat"] is None
    assert (
        c_lite["manufacturer_sales_state"]["variant_caveat"]
        == c_lite_mss["variant_caveat"]
    )
    assert "other_variant_caveat" not in c_lite["manufacturer_sales_state"]
    japan_ref = "SRC-SAMSONITE-C-LITE-SPINNER55EXP-MIDNIGHT"
    assert japan_ref in c_lite["evidence_refs"]
    japan_locator = next(
        item
        for item in locator_sources[japan_ref]["locators"]
        if item["claim_id"] == c_lite["claim_id"]
    )
    locator_material = "\n".join(japan_locator["exact_utf8_fragments"])
    for token in (
        "CS2*31007",
        "条件付き10年",
        "※電子機器部分の保証期間は購入後1年です。",
        "カートに入れる",
    ):
        assert token in locator_material

    frequenter = claims["CLM-PORTFOLIO-LIGHT-FREQUENTER-REFERENCE"]
    assert frequenter["subject_product_ids"] == []
    assert frequenter["market_candidate_id"] == candidate["candidate_id"]
    assert frequenter["statement"] == candidate["reason"]
    assert "SRC-FREQUENTER-LIEVE-1-250" in frequenter["evidence_refs"]
    assert japan_ref in frequenter["evidence_refs"]
    packet = packets[article_id]
    selected_subjects = {
        product_id
        for claim in packet["claims"]
        for product_id in claim["subject_product_ids"]
    }
    assert c_lite_id in selected_subjects
    assert frequenter_id not in selected_subjects
    recall_gate = next(
        claim["product_specific_recall_query_gate"]
        for claim in packet["claims"]
        if "product_specific_recall_query_gate" in claim
    )
    assert c_lite_id in recall_gate["required_product_ids"]
    assert frequenter_id not in recall_gate["required_product_ids"]


def test_every_reader_visible_external_candidate_is_exact_url_and_locator_bound() -> (
    None
):
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    packets = _packets(registry)
    sources_by_ref = {source["source_ref"]: source for source in registry["sources"]}
    refs_by_url = {
        source["url"]: source["source_ref"] for source in registry["sources"]
    }
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    observed: set[tuple[str, str]] = set()
    for article in audit["articles"]:
        article_id = article["article_id"]
        packet_claims = {
            claim["market_candidate_id"]: claim
            for claim in packets[article_id]["claims"]
            if "market_candidate_id" in claim
        }
        for candidate in article["considered_external_candidates"]:
            key = (article_id, candidate["candidate_id"])
            observed.add(key)
            claim_id = owner.MARKET_CANDIDATE_CLAIM_IDS[key]
            claim = packet_claims[candidate["candidate_id"]]
            assert claim["claim_id"] == claim_id
            assert claim["statement"] == candidate["reason"]
            assert claim["official_url"] == candidate["official_url"]
            assert claim["exact_model"] == candidate["exact_model"]
            assert claim["exact_variant_scope"] == candidate["exact_variant_scope"]
            assert claim["evaluated_at"] == candidate["evaluated_at"]
            assert claim["effective_lifecycle"] == candidate["effective_lifecycle"]
            official_ref = refs_by_url[candidate["official_url"]]
            assert official_ref in claim["evidence_refs"]
            assert sources_by_ref[official_ref]["url"] == candidate["official_url"]
            for evidence_url in candidate["evidence_refs"]:
                source_ref = refs_by_url[evidence_url]
                assert source_ref in claim["evidence_refs"]
                locator_claims = {
                    item["claim_id"] for item in locator_sources[source_ref]["locators"]
                }
                assert claim_id in locator_claims
    assert observed == set(owner.MARKET_CANDIDATE_CLAIM_IDS)


def test_compact_robot_external_tradeoffs_bind_candidate_and_selected_boundaries() -> (
    None
):
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    claims = _claims(registry)
    locators = {source["source_ref"]: source for source in locator["sources"]}
    article = next(
        value
        for value in audit["articles"]
        if value["article_id"] == "st1704-compact-robot-vacuum-shortlist"
    )
    candidates = {
        value["candidate_id"]: value
        for value in article["considered_external_candidates"]
    }
    expected = {
        "EXT-ROBOROCK-SAROS-10": (
            "CLM-ST1704-ROBOT-SAROS10-EXCLUDED",
            "SRC-ROBOROCK-SAROS-10",
            ("35.0", "35.3", "7.98", "40.9", "44.0", "47.0", "全自動ドック"),
        ),
        "EXT-EUFY-OMNI-E25-T2353": (
            "CLM-ST1704-ROBOT-E25-EXCLUDED",
            "SRC-EUFY-OMNI-E25-T2353",
            ("32.7", "34.6", "11.1", "37.0", "46.2", "43.7", "走行中のモップ洗浄"),
        ),
        "EXT-DREAME-X50-ULTRA": (
            "CLM-ST1704-ROBOT-X50-EXCLUDED",
            "SRC-DREAME-X50-ULTRA",
            ("35.0", "35.0", "8.9", "45.7", "34.0", "59.0", "段差対応"),
        ),
        "EXT-ECOVACS-DEEBOT-X8-PRO": (
            "CLM-ST1704-ROBOT-X8-EXCLUDED",
            "SRC-ECOVACS-DEEBOT-X8-PRO",
            ("35.3", "35.15", "9.8", "35.0", "47.7", "53.3", "自動洗浄・乾燥"),
        ),
    }
    for candidate_id, (claim_id, source_ref, tokens) in expected.items():
        claim = claims[claim_id]
        assert claim["statement"] == candidates[candidate_id]["reason"]
        assert all(token in claim["statement"] for token in tokens)
        assert {source_ref, "SRC-EUFY-AUTOEMPTY-C10-T2292", "SRC-ECOVACS-DEEBOT-MINI2"} <= set(
            claim["evidence_refs"]
        )
        for required_ref in (
            source_ref,
            "SRC-EUFY-AUTOEMPTY-C10-T2292",
            "SRC-ECOVACS-DEEBOT-MINI2",
        ):
            item = next(
                value
                for value in locators[required_ref]["locators"]
                if value["claim_id"] == claim_id
            )
            assert item["exact_utf8_fragments"]

    k10 = claims["CLM-ST1704-ROBOT-K10-COMBO-EXCLUDED"]
    assert k10["market_candidate_id"] == "EXT-SWITCHBOT-K10-PRO-COMBO"
    assert k10["exact_model"] == "ロボット掃除機 K10+ Pro Combo"
    assert k10["statement"] == candidates["EXT-SWITCHBOT-K10-PRO-COMBO"]["reason"]


def test_current_muji_variants_and_fair_alternatives_are_exactly_bound() -> None:
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    sources = {source["source_ref"]: source for source in registry["sources"]}
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    cases = {
        "EXT-MUJI-HARD-CARRY-20L": (
            "CLM-PORTFOLIO-UNDER100-MUJI20-EXCLUDED",
            "SRC-MUJI-HARD-CARRY-20L",
            "https://www.muji.com/jp/ja/store/cmdty/detail/4550723184182",
            ("商品番号23184182", "タテ４７×ヨコ３２×マチ２０．５ｃｍ", "ストッパー機能付き"),
        ),
        "EXT-MUJI-FRONT-OPEN-32L": (
            "CLM-PORTFOLIO-FRONT-MUJI32-EXCLUDED",
            "SRC-MUJI-FRONT-OPEN-32L",
            "https://www.muji.com/jp/ja/store/cmdty/detail/4550584950087",
            (
                "商品番号84950087",
                "タテ５４×ヨコ３７×マチ２４ｃｍ",
                "フルオーブンも可能",
                "高さ1cmきざみ",
                "静かな双輪キャスター",
            ),
        ),
    }
    candidates = {
        candidate["candidate_id"]: candidate
        for article in audit["articles"]
        for candidate in article["considered_external_candidates"]
    }
    for candidate_id, (claim_id, source_ref, url, fragments) in cases.items():
        candidate = candidates[candidate_id]
        claim = claims[claim_id]
        assert claim["statement"] == candidate["reason"]
        assert claim["exact_variant_scope"] == candidate["exact_variant_scope"]
        assert sources[source_ref]["url"] == url
        item = next(
            value
            for value in locator_sources[source_ref]["locators"]
            if value["claim_id"] == claim_id
        )
        material = "\n".join(item["exact_utf8_fragments"])
        assert all(fragment in material for fragment in fragments)


def test_selected_anker_sales_states_use_visible_cart_ui_and_exact_owner_rows() -> None:
    registry, locator = _documents()
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}
    expected = {
        "CLM-ST1704-POWER-C300-SPECS": owner.ANKER_C300_SALES_STATE,
        "CLM-ST1704-ANKER-C300-SPECS": owner.ANKER_C300_SALES_STATE,
        "CLM-ST1704-ANKER-C800-SPECS": owner.ANKER_C800_PLUS_SALES_STATE,
        "CLM-ST1704-ANKER-C1000-SPECS": owner.ANKER_C1000_SALES_STATE,
        "CLM-ST1704-ANKER-C1000-GEN2-SPECS": owner.ANKER_C1000_GEN2_SALES_STATE,
    }
    for claim_id, sales_state in expected.items():
        claim = claims[claim_id]
        assert claim["manufacturer_sales_state"] == sales_state
        assert sales_state["reader_visible_label"] == "在庫わずか"
        assert sales_state["variant_caveat"] is None
        source_ref = sales_state["source_ref"]
        item = next(
            value
            for value in locator_sources[source_ref]["locators"]
            if value["claim_id"] == claim_id
        )
        material = "\n".join(item["exact_utf8_fragments"])
        assert "在庫わずか" in material
        assert (
            'aria-label="カートに入れる"' in material
            or 'value="カートに入れる"' in material
        )
        for model_token in str(sales_state["exact_variant"]).split("A")[1:]:
            assert f"A{model_token.split()[0].rstrip('）/')}" in material


def test_difference_05721_uses_the_exact_available_white_variant() -> None:
    registry, locator = _documents()
    claims = _claims(registry)
    sources = {source["source_ref"]: source for source in registry["sources"]}
    locators = {source["source_ref"]: source for source in locator["sources"]}
    source_ref = "SRC-ACE-DIFFERENCE-05721"

    assert sources[source_ref]["url"] == (
        "https://store.ace.jp/shop/g/g05721-06/"
    )
    assert sources[source_ref]["retrieved_on"] == "2026-08-31"
    assert "06：ホワイト" in sources[source_ref]["title"]
    owner_row = owner._manufacturer_sales_state_row("PRD-ACE-DIFFERENCE-05721")
    assert owner_row["state"] == "AVAILABLE"
    assert owner_row["availability_scope"] == "VARIANT"
    assert owner_row["official_url"] == sources[source_ref]["url"]
    assert owner_row["variant_caveat"] is None

    for claim_id in (
        "CLM-ST1704-SUITCASE-DIFFERENCE-SPECS",
        "CLM-PORTFOLIO-FRONT-DIFFERENCE-05721",
    ):
        claim = claims[claim_id]
        assert claim["manufacturer_sales_state"] == (
            owner.DIFFERENCE_05721_06_SALES_STATE
        )
        sales_state = claim["manufacturer_sales_state"]
        assert sales_state["exact_variant"] == "ホワイト・05721-06"
        assert sales_state["reader_visible_label"] == "在庫あります"
        assert sales_state["checked_at"] == owner_row["checked_at_utc"]
        item = next(
            value
            for value in locators[source_ref]["locators"]
            if value["claim_id"] == claim_id
        )
        material = "\n".join(item["exact_utf8_fragments"])
        for token in (
            "05721-06",
            "06：ホワイト",
            "在庫あります",
            'value="カートに入れる">カートに入れる',
            "H55×W36×D24/27 cm",
        ):
            assert token in material


def test_every_reader_visible_portfolio_candidate_is_article_local_and_locator_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    packets = _packets(registry)
    sources = {source["source_ref"]: source for source in registry["sources"]}
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}
    selected_by_article = {
        article["article_id"]: set(article["selected_product_ids"])
        for article in audit["articles"]
    }

    observed: set[tuple[str, str]] = set()
    for article in audit["articles"]:
        article_id = article["article_id"]
        local_claims = {
            claim["subject_product_ids"][0]: claim
            for claim in packets[article_id]["claims"]
            if "portfolio_candidate_disposition" in claim
        }
        for candidate in article["considered_portfolio_candidates"]:
            product_id = candidate["product_id"]
            key = (article_id, product_id)
            observed.add(key)
            claim_id, source_refs = owner.PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS[key]
            claim = local_claims[product_id]
            assert claim["claim_id"] == claim_id
            assert claim["subject_product_ids"] == [product_id]
            assert claim["portfolio_candidate_disposition"] == "REFERENCE_ONLY"
            assert claim["portfolio_candidate_reason"] == candidate["reason"]
            assert candidate["reason"] in claim["statement"]
            assert claim["route_article_id"] == candidate["route_article_id"]
            assert product_id not in selected_by_article[article_id]
            assert product_id in selected_by_article[candidate["route_article_id"]]
            assert set(source_refs) <= set(claim["evidence_refs"])
            for source_ref in claim["evidence_refs"]:
                assert source_ref in sources
                assert any(
                    item["claim_id"] == claim_id
                    for item in locator_sources[source_ref]["locators"]
                )
    assert observed == set(owner.PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS)

    missing = dict(owner.PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS)
    missing.pop(next(iter(missing)))
    with monkeypatch.context() as context:
        context.setattr(owner, "PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS", missing)
        with pytest.raises(ValueError, match="portfolio candidate inventory drift"):
            owner._apply_portfolio_candidate_claims(deepcopy(registry))

    wrong_source = dict(owner.PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS)
    key = (
        "st1704-portable-power-station-guide",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    )
    claim_id, _source_refs = wrong_source[key]
    wrong_source[key] = (claim_id, ("SRC-JACKERY-500-NEW",))
    with monkeypatch.context() as context:
        context.setattr(owner, "PORTFOLIO_CANDIDATE_REFERENCE_BINDINGS", wrong_source)
        with pytest.raises(ValueError, match="product/source URL mismatch"):
            owner._apply_portfolio_candidate_claims(deepcopy(registry))


def test_reader_semantic_p0_boundaries_are_explicit() -> None:
    registry, locator = _documents()
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    tri_air = claims["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"]
    assert "キャスターストッパー" in tri_air["statement"]
    assert "容量拡張" in tri_air["statement"]
    assert "未確認" in tri_air["statement"]
    assert "推奨根拠に使わない" in tri_air["statement"]
    assert "ストッパーなし" not in tri_air["statement"]
    assert "拡張機能なし" not in tri_air["statement"]
    assert (
        "3モデルで最軽量"
        in claims["CLM-ST1704-SUITCASE-CONDITIONAL-CHOICES"]["statement"]
    )

    power = claims["CLM-ST1704-POWER-CONDITIONAL-CHOICES"]
    for token in (
        "比較した7モデル",
        "AORA 30 V2が288Wh・定格600W・約4.3kg",
        "AORA 100 V2が1024Wh・定格1800W・約11.5kg",
        "Jackery 1000 New V3が1024Wh・AC定格1500W・約10.6kg",
        "各社公表の連続供給目安",
        "呼称・試験条件が異なる",
        "同一指標として大小比較しない",
        "必要容量",
        "保管条件",
        "約3.7kg軽い",
    ):
        assert token in power["statement"]

    k11 = claims["CLM-PORTFOLIO-ROBOT-K11-PRO"]
    assert "2.4GHz Wi-Fi" in k11["statement"]
    assert "SwitchBotアプリ" in k11["statement"]
    assert "スケジュール" in k11["statement"]
    assert {
        "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS",
        "SRC-SWITCHBOT-K11-SETUP",
    } <= set(k11["evidence_refs"])
    for source_ref in (
        "SRC-SWITCHBOT-K11-WIFI-FUNCTIONS",
        "SRC-SWITCHBOT-K11-SETUP",
    ):
        assert any(
            item["claim_id"] == k11["claim_id"]
            for item in locator_sources[source_ref]["locators"]
        )

    t2292_claim_ids = (
        "CLM-ST1704-ROBOT-EUFY-C10-SPECS",
        "CLM-ST1704-ROBOT-CONDITIONAL-CHOICES",
    )
    for claim_id in t2292_claim_ids:
        claim = claims[claim_id]
        assert claim["manufacturer_sales_state"] == owner.EUFY_T2292511_SALES_STATE
        assert any(
            item["claim_id"] == claim_id
            for item in locator_sources["SRC-EUFY-AUTOEMPTY-C10-T2292"][
                "locators"
            ]
        )

    f155260_claim_ids = (
        "CLM-ST1704-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
        "CLM-PORTFOLIO-ROBOT-ROOMBA-MINI-F155260-EXCLUDED",
    )
    f155260_locators = {
        item["claim_id"]: item
        for item in locator_sources["SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY"]["locators"]
    }
    for claim_id in f155260_claim_ids:
        claim = claims[claim_id]
        assert "在庫切れ" in claim["statement"]
        assert claim["manufacturer_sales_state"] == {
            "exact_variant": "F155260",
            "status": "OUT_OF_STOCK",
            "checked_at": "2026-08-31T12:39:34Z",
            "source_ref": "SRC-IROBOT-ROOMBA-MINI-AUTOEMPTY",
            "reader_visible_label": "在庫切れ",
            "recommendation_gate": "BLOCKED",
            "cta_gate": "BLOCKED",
        }
        material = "\n".join(f155260_locators[claim_id]["exact_utf8_fragments"])
        assert 'name="item_cd" value="F155260"' in material
        assert 'purchase_btn-buy soldout">在庫切れ' in material

    ss_m171 = claims["CLM-ST1704-DISH-SS-M171-SPECS"]["statement"]
    for token in (
        "幅42×奥行43.5×高さ43.5cm",
        "ドア開放時奥行は76cm",
        "標準収納16点",
        "2WAY",
        "送風乾燥",
    ):
        assert token in ss_m171
    solota = claims[
        "CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE"
    ]["statement"]
    assert "NP-TMLK1-K" in solota
    assert "正確な型番" in solota
    dish_decision = claims["CLM-PORTFOLIO-DISH-LIFECYCLE-REFERENCE"]["statement"]
    for token in (
        "以前の比較対象2機種はいずれも仕様参考",
        "現行品の仕様表",
        "少人数向け卓上食洗機4候補の記事へ集約",
        "公式な後継・同等品を意味しない",
    ):
        assert token in dish_decision
    assert claims["CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED"][
        "effective_lifecycle"
    ] == "RESTOCK_NOTIFICATION_ONLY"


def test_article_local_reader_facts_keep_known_specs_separate_from_unknowns() -> (
    None
):
    registry, locator = _documents()
    claims = _claims(registry)
    locator_sources = {source["source_ref"]: source for source in locator["sources"]}

    cresta = claims["CLM-ST1704-SUITCASE-CRESTA-06316-EXCLUDED"]
    for token in ("通常34L", "拡張時39L", "3.2kg"):
        assert token in cresta["statement"]

    power = claims["CLM-ST1704-POWER-CONDITIONAL-CHOICES"]
    for token in (
        "比較した7モデル",
        "C300が288Wh・定格300W",
        "C300の288Whは7モデルで最小容量",
        "C300が7モデルで最軽量",
        "同一指標として大小比較しない",
    ):
        assert token in power["statement"]

    np_tsp2 = claims["CLM-ST1704-DISH-NP-TSP2-LAUNCH-REFERENCE"]
    for token in ("2026年9月発売予定", "予約受付中", "9月中旬以降"):
        assert token in np_tsp2["statement"]
    dws_support = claims["CLM-ST1704-DISH-TOSHIBA-DWS-33B-SUPPORT"]
    assert dws_support["subject_product_ids"] == ["PRD-TOSHIBA-DWS-33B-W"]
    assert "製造打ち切り後6年" in dws_support["statement"]
    assert dws_support["evidence_refs"] == ["SRC-TOSHIBA-PARTS-RETENTION"]

    first_robot = claims["CLM-ST1704-ROBOT-CONDITIONAL-CHOICES"]
    for token in (
        "4候補の役割",
        "使い捨てお掃除シート",
        "モップ自動洗浄・熱風乾燥",
        "モップ温水洗浄・温風乾燥",
    ):
        assert token in first_robot["statement"]

    c_lite_known = claims[
        "CLM-PORTFOLIO-FRONT-C-LITE-KNOWN-SPECS-REFERENCE"
    ]
    c_lite_unknown = claims["CLM-PORTFOLIO-FRONT-C-LITE-REFERENCE"]
    assert c_lite_known["classification"] == "MAJOR_VERIFIABLE"
    assert "market_candidate_id" not in c_lite_known
    assert c_lite_unknown["classification"] == "DECISION_CRITICAL_UNKNOWN"
    assert c_lite_unknown["market_candidate_id"] == "EXT-SAMSONITE-C-LITE-FEATURE"
    for token in (
        "C-Lite Spinner 55 EXP",
        "134679-1041",
        "CS2*09007",
        "36L",
        "在庫あり",
        "カートに入れる",
    ):
        assert token in c_lite_known["statement"]
    assert c_lite_known["dimensions"] == [
        {
            "subject": "Samsonite C-Lite 134679-1041（通常時）",
            "width_cm": 40,
            "depth_cm": 20,
            "height_cm": 55,
        },
        {
            "subject": "Samsonite C-Lite 134679-1041（拡張時）",
            "width_cm": 40,
            "depth_cm": 23,
            "height_cm": 55,
        },
    ]

    eufy = claims["CLM-ST1704-ROBOT-EUFY-C10-SPECS"]
    k11 = claims["CLM-PORTFOLIO-ROBOT-K11-PRO"]
    mini = claims["CLM-PORTFOLIO-ROBOT-ROOMBA-SLIM-F115060"]
    robot_decision = claims["CLM-PORTFOLIO-ROBOT-CONDITIONAL-CHOICES"]
    assert "高さ7.2cm" in eufy["statement"]
    assert "使用後に捨てる" in k11["statement"]
    assert "専用の使い捨てお掃除シート" in mini["statement"]
    for token in (
        "2製品",
        "幅22.2×奥行8.6cm",
        "左右各1m・前方1.5m",
        "最大12,000Pa",
        "使い捨てシート式",
        "別記事の4モデル比較",
    ):
        assert token in robot_decision["statement"]

    locator_expectations = {
        "SRC-ACE-CRESTA-06316": (cresta["claim_id"], ("34/39 L", "3.2kg")),
        "SRC-TOSHIBA-PARTS-RETENTION": (
            dws_support["claim_id"],
            ("６年", "製造打ち切り後"),
        ),
        "SRC-SAMSONITE-C-LITE-SPINNER55EXP-BLACK": (
            c_lite_known["claim_id"],
            ("36 /42", "在庫あり", "カートに入れる", "CS2*09007"),
        ),
        "SRC-EUFY-AUTOEMPTY-C10-T2292": (
            eufy["claim_id"],
            ("約32.5 x 32.3 x 7.2cm", "水拭き", "2.4GHz"),
        ),
        "SRC-IROBOT-ROOMBA-MINI-SLIM-F115060": (
            mini["claim_id"],
            ("専用使い捨てお掃除シート", "市販の床拭きシートも使用可能"),
        ),
    }
    for source_ref, (claim_id, tokens) in locator_expectations.items():
        locator_item = next(
            item
            for item in locator_sources[source_ref]["locators"]
            if item["claim_id"] == claim_id
        )
        material = "\n".join(locator_item["exact_utf8_fragments"])
        assert all(token in material for token in tokens)


def test_rakua_mini_plus_restocks_without_claiming_sold_out() -> None:
    registry, _locator = _documents()
    claim = _claims(registry)["CLM-PORTFOLIO-DISH-RAKUA-MINI-PLUS-EXCLUDED"]
    assert claim["model_lifecycle"] == "AVAILABLE"
    assert claim["variant_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert claim["reader_visible_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert claim["effective_lifecycle"] == "RESTOCK_NOTIFICATION_ONLY"
    assert "売り切れ" not in claim["statement"]
    assert "再入荷通知" in claim["statement"]
    assert "カート導線を確認できません" in claim["statement"]


def test_nestout_numeric_exclusion_is_bound_to_both_official_products() -> None:
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    sources = {source["source_ref"]: source for source in registry["sources"]}
    packet = next(
        value
        for value in registry["source_packets"]
        if value["article_id"] == "st1704-portable-power-station-guide"
    )
    claim = next(
        value
        for value in packet["claims"]
        if value["claim_id"] == "CLM-ST1704-POWER-NESTOUT-700N-EXCLUDED"
    )
    audit_article = next(
        value
        for value in audit["articles"]
        if value["article_id"] == "st1704-portable-power-station-guide"
    )
    candidate = next(
        value
        for value in audit_article["considered_external_candidates"]
        if value["candidate_id"] == "EXT-ELECOM-NESTOUT-700N"
    )

    assert claim["statement"] == candidate["reason"]
    for token in (
        "712.25Wh",
        "定格700W",
        "約6.2kg",
        "768Wh",
        "定格1200W",
        "約10.5kg",
        "判定条件がそろっていない",
        "直接比較せず選定根拠にも使いません",
        "約4.3kg軽く",
    ):
        assert token in claim["statement"]
    assert "充電池500回" not in claim["statement"]
    assert "電池3,000回" not in claim["statement"]
    assert set(claim["evidence_refs"]) == {
        "SRC-ELECOM-NESTOUT-700N",
        "SRC-ANKER-SOLIX-C800",
    }
    assert sources["SRC-JACKERY-500-NEW"]["url"] == (
        "https://www.jackery.jp/products/explorer-500-new"
    )
    assert sources["SRC-ELECOM-NESTOUT-700N"]["url"] == (
        "https://www.elecom.co.jp/products/DE-NEPS700NBE.html"
    )
    assert {
        "https://www.jackery.jp/products/explorer-500-new",
        "https://www.elecom.co.jp/products/DE-NEPS700NBE.html",
    } <= set(audit_article["official_category_sources"])

    locator_sources = {source["source_ref"]: source for source in locator["sources"]}
    for source_ref, tokens in {
        "SRC-ELECOM-NESTOUT-700N": ("712.25Wh", "約6.2kg", "約500回"),
        "SRC-ANKER-SOLIX-C800": ("768Wh", "約10.5kg", "3,000回"),
    }.items():
        item = next(
            value
            for value in locator_sources[source_ref]["locators"]
            if value["claim_id"] == claim["claim_id"]
        )
        material = "\n".join(item["exact_utf8_fragments"])
        assert all(token in material for token in tokens)


def test_jackery_1000_new_v3_is_selected_with_exact_official_specs() -> None:
    registry, locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    sources = {source["source_ref"]: source for source in registry["sources"]}
    packet = next(
        value
        for value in registry["source_packets"]
        if value["article_id"] == "st1704-portable-power-station-guide"
    )
    claim = next(
        value
        for value in packet["claims"]
        if value["claim_id"] == "CLM-ST1704-POWER-JACKERY-1000-NEW-V3-SPECS"
    )
    audit_article = next(
        value
        for value in audit["articles"]
        if value["article_id"] == "st1704-portable-power-station-guide"
    )
    assert "PRD-JACKERY-1000-NEW-V3" in audit_article["selected_product_ids"]
    assert all(
        value["candidate_id"] != "EXT-JACKERY-1000-NEW-V3"
        for value in audit_article["considered_external_candidates"]
    )
    assert claim["classification"] == "MAJOR_VERIFIABLE"
    assert claim["subject_product_ids"] == ["PRD-JACKERY-1000-NEW-V3"]
    for token in (
        "1024Wh",
        "AC定格出力1500W",
        "約10.6kg",
        "呼称・試験条件が異なる",
        "数値だけで順位付けしない",
    ):
        assert token in claim["statement"]
    assert set(claim["evidence_refs"]) == {
        "SRC-JACKERY-1000-NEW-V3",
        "SRC-JACKERY-1000-NEW-V3-LAUNCH",
    }
    assert sources["SRC-JACKERY-1000-NEW-V3"]["url"] == (
        "https://www.jackery.jp/products/explorer-1000-new-v3"
    )
    assert sources["SRC-JACKERY-1000-NEW-V3-LAUNCH"]["url"] == (
        "https://www.jackery.jp/blogs/news/jackery-news20260724"
    )
    assert {
        sources["SRC-JACKERY-1000-NEW-V3"]["url"],
        sources["SRC-JACKERY-1000-NEW-V3-LAUNCH"]["url"],
    } <= set(audit_article["official_category_sources"])

    locator_sources = {source["source_ref"]: source for source in locator["sources"]}
    for source_ref, tokens in {
        "SRC-JACKERY-1000-NEW-V3": ("1000 New V3", "10.6kg"),
        "SRC-JACKERY-1000-NEW-V3-LAUNCH": (
            "2026年7月24日",
            "AC定格出力1500W",
            "容量1024Wh",
        ),
    }.items():
        item = next(
            value
            for value in locator_sources[source_ref]["locators"]
            if value["claim_id"] == claim["claim_id"]
        )
        material = "\n".join(item["exact_utf8_fragments"])
        assert all(token in material for token in tokens)


def test_negative_claims_require_explicit_official_evidence_not_page_omission() -> None:
    registry, _locator = _documents()
    owner._validate_negative_claim_contract(registry)
    claims = _claims(registry)
    assert set(owner.NEGATIVE_CLAIM_EVIDENCE) == {
        claim_id
        for claim_id, claim in claims.items()
        if "negative_claim_evidence" in claim
    }
    assert (
        "negative_claim_evidence" not in claims["CLM-PORTFOLIO-FRONT-C-LITE-REFERENCE"]
    )

    tampered = deepcopy(registry)
    tri_air = _claims(tampered)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"]
    tri_air["statement"] += " キャスターストッパーなし。"
    with pytest.raises(ValueError, match="lacks explicit official"):
        owner._validate_negative_claim_contract(tampered)

    unsupported_mode = deepcopy(registry)
    config = dict(owner.NEGATIVE_CLAIM_EVIDENCE)
    config["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"] = (
        "PRODUCT_PAGE_OMISSION",
        ("SRC-PROTECA-TRI-AIR-01541",),
    )
    tri_air = _claims(unsupported_mode)["CLM-ST1704-SUITCASE-TRIAIR-01541-SPECS"]
    tri_air["statement"] += " キャスターストッパーなし。"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(owner, "NEGATIVE_CLAIM_EVIDENCE", config)
        with pytest.raises(ValueError, match="invalid negative-claim evidence mode"):
            owner._validate_negative_claim_contract(unsupported_mode)


def test_product_specific_recall_queries_use_one_central_fail_closed_contract() -> None:
    registry, _locator = _documents()
    audit = json.loads(owner.MARKET_AUDIT_PATH.read_text(encoding="utf-8"))
    required = {
        product_id
        for article in audit["articles"]
        for product_id in article["selected_product_ids"]
    }
    gated: set[str] = set()
    gates = []
    for packet in registry["source_packets"]:
        packet_gates = [
            claim["product_specific_recall_query_gate"]
            for claim in packet["claims"]
            if "product_specific_recall_query_gate" in claim
        ]
        selected_for_packet = next(
            article["selected_product_ids"]
            for article in audit["articles"]
            if article["article_id"] == packet["article_id"]
        )
        assert len(packet_gates) == (1 if selected_for_packet else 0)
        if not packet_gates:
            continue
        gate = packet_gates[0]
        gates.append(gate)
        gated.update(gate["required_product_ids"])
        assert gate["schema"] == "PRODUCT_SPECIFIC_RECALL_QUERY_REQUIREMENT_V2"
        assert gate["receipt_document_ref"] == (
            owner.PRODUCT_SAFETY_RECEIPT_DOCUMENT_REF
        )
        assert gate["receipt_document_schema"] == (
            owner.PRODUCT_SAFETY_RECEIPT_SCHEMA
        )
        assert gate["required_authority_kinds"] == list(
            owner.PRODUCT_SAFETY_REQUIRED_AUTHORITIES
        )
        assert gate["general_safety_guidance_is_not_a_receipt"] is True
    assert gated == required
    assert len(required) == 33
    assert len(gates) == 9


def test_selected_power_stations_have_article_local_official_due_diligence() -> None:
    registry, locator = _documents()
    owner._validate_power_station_due_diligence_contract(registry)
    claims = _claims(registry)
    sources = {source["source_ref"]: source for source in registry["sources"]}
    locator_sources = {
        source["source_ref"]: source for source in locator["sources"]
    }

    assert {
        group["product_id"] for group in owner.POWER_STATION_DUE_DILIGENCE_GROUPS
    } == {
        "PRD-ANKER-SOLIX-C300",
        "PRD-JACKERY-500-NEW",
        "PRD-ANKER-SOLIX-C800",
        "PRD-BLUETTI-AORA30-V2",
        "PRD-BLUETTI-AORA100-V2",
        "PRD-DJI-POWER-1000-V2",
        "PRD-ANKER-SOLIX-C800-PLUS",
        "PRD-ANKER-SOLIX-C1000",
        "PRD-ANKER-SOLIX-C1000-GEN2",
    }
    assert len(owner.POWER_STATION_DUE_DILIGENCE_GROUPS) == 10
    for group in owner.POWER_STATION_DUE_DILIGENCE_GROUPS:
        for source_ref in group["required_source_refs"]:
            assert sources[source_ref]["authority"] == "MANUFACTURER_OFFICIAL"
            locator_claim_ids = {
                item["claim_id"]
                for item in locator_sources[source_ref]["locators"]
            }
            assert locator_claim_ids & set(group["claim_ids"])

    anker_warranty = (
        "※Anker Japan 公式オンラインストア会員を対象に、通常18ヶ月の"
        "製品保証を5年へ自動延長致します。"
    )
    for source_ref, claim_id in (
        ("SRC-ANKER-SOLIX-C300", "CLM-ST1704-POWER-C300-SPECS"),
        ("SRC-ANKER-SOLIX-C800", "CLM-ST1704-POWER-ANKER-C800-SPECS"),
        ("SRC-ANKER-SOLIX-C800-PLUS", "CLM-ST1704-ANKER-C800-SPECS"),
        ("SRC-ANKER-SOLIX-C1000", "CLM-ST1704-ANKER-C1000-SPECS"),
        (
            "SRC-ANKER-SOLIX-C1000-GEN2",
            "CLM-ST1704-ANKER-C1000-GEN2-SPECS",
        ),
    ):
        item = next(
            value
            for value in locator_sources[source_ref]["locators"]
            if value["claim_id"] == claim_id
        )
        assert anker_warranty in item["exact_utf8_fragments"]

    assert "62種類の保護機能" in claims[
        "CLM-ST1704-POWER-JACKERY-SPECS"
    ]["statement"]
    assert "公式文言が一致しない" in claims[
        "CLM-ST1704-POWER-JACKERY-WARRANTY"
    ]["statement"]


def test_power_station_due_diligence_tamper_fails_closed() -> None:
    registry, _locator = _documents()
    statement_tamper = deepcopy(registry)
    claim = _claims(statement_tamper)["CLM-ST1704-POWER-JACKERY-WARRANTY"]
    claim["statement"] = claim["statement"].replace("公開判定は停止", "公開可能")
    with pytest.raises(ValueError, match="statement is incomplete"):
        owner._validate_power_station_due_diligence_contract(statement_tamper)

    evidence_tamper = deepcopy(registry)
    source = next(
        value
        for value in evidence_tamper["sources"]
        if value["source_ref"] == "SRC-DJI-JP-AFTERSALES-POLICY"
    )
    source["authority"] = "UNVERIFIED_SECONDARY"
    with pytest.raises(ValueError, match="not manufacturer official"):
        owner._validate_power_station_due_diligence_contract(evidence_tamper)

    recall_tamper = deepcopy(registry)
    packet = _packets(recall_tamper)["st1704-portable-power-station-guide"]
    gate = next(
        claim["product_specific_recall_query_gate"]
        for claim in packet["claims"]
        if "product_specific_recall_query_gate" in claim
    )
    gate["receipts"] = [{"result": "NONE_FOUND"}]
    with pytest.raises(ValueError, match="recall gate is fail-open"):
        owner._validate_power_station_due_diligence_contract(recall_tamper)


def test_panasonic_black_is_reference_only_and_siroca_common_install_source_is_exact() -> None:
    registry, _locator = _documents()
    claims = _claims(registry)
    sources = {source["source_ref"]: source for source in registry["sources"]}

    assert claims["CLM-PORTFOLIO-DISH-SOLOTA-NP-TMLK1-IDENTITY-REFERENCE"][
        "subject_product_ids"
    ] == []
    assert "PRD-PANASONIC-NP-TMLK1" not in {
        product_id
        for product_ids in owner.CLAIM_SUBJECT_PRODUCT_IDS.values()
        for product_id in product_ids
    }
    assert "SRC-SIROCA-SS-MA251-INSTALL" not in sources
    common = sources["SRC-SIROCA-DISHWASHER-INSTALLATION"]
    assert common["title"] == "siroca 食器洗い乾燥機 共通据え付け案内"
    assert {
        "CLM-ST1704-DISH-SS-M171-SPECS",
    } <= {
        claim_id
        for claim_id, claim in claims.items()
        if common["source_ref"] in claim["evidence_refs"]
    }
