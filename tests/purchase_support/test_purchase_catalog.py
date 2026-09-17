"""Exact identity, date/price and public projection boundaries across the 19 candidates."""

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from raos.application.editorial.purchase_support import (
    compile_articles,
    validate_catalog,
    PLACEMENTS,
)
from raos.application.editorial.purchase_offer_import import (
    approved_offer_from_normalized,
)
from raos.application.editorial.reader_html import fragment
from tools.affiliate_ingestion.normalize import normalize_record

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "changes/reader-purchase-support-v1"
# Offers checked on 2026-09-12 are current at this instant; the 2026-09-10 checks are expired.
NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


@pytest.fixture
def catalog():
    return json.loads((BASE / "purchase-support.v1.json").read_text())


def compile(catalog):
    return compile_articles(
        catalog,
        {p.stem: p.read_text() for p in (BASE / "articles").glob("*.html")},
        json.loads(
            (
                ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
            ).read_text()
        ),
        now=NOW,
    )


def test_all_thirty_one_identities_preserve_actionable_research_and_routes(
    catalog,
):
    validate_catalog(catalog)
    html, runtime = compile(catalog)
    assert len(html) == 23 and len(catalog["products"]) == 54
    roots = {slug: fragment(body) for slug, body in html.items()}
    for slug, root in roots.items():
        ids = [n.attrs["id"] for n in root.walk() if "id" in n.attrs]
        assert len(ids) == len(set(ids)), slug
        old = fragment((BASE / "articles" / f"{slug}.html").read_text())
        assert {n.attrs["id"] for n in old.walk() if "id" in n.attrs} <= set(ids), slug
        for a in root.find(tag="a"):
            link = urlsplit(a.attrs.get("href", ""))
            target = link.path.strip("/") or slug
            if not link.netloc and target in roots and link.fragment:
                assert link.fragment in {
                    n.attrs.get("id") for n in roots[target].walk()
                }, (slug, a.attrs)
    for route in catalog["routes"]:
        product = next(
            p for p in catalog["products"] if p["product_id"] == route["product_id"]
        )
        assert route["anchor"] == product["anchor"]
    for a in runtime["articles"]:
        links = [
            n
            for n in roots[a["slug"]].find(tag="a")
            if n.attrs.get("data-raos-cta-type") == "offer"
        ]
        assert len(links) == len(a["bindings"])
        for b in a["bindings"]:
            assert set(b) == (
                {
                    "article_id",
                    "product_id",
                    "seller_id",
                    "offer_id",
                    "cta_id",
                    "placement",
                    "snapshot_id",
                    "href",
                }
                | {"link_purpose", "affiliate"}
            )
            if len(b) == 10:
                assert (b["link_purpose"], b["affiliate"]) in {
                    ("merchant_purchase", "false"),
                    ("affiliate_purchase", "true"),
                }
            link = next(n for n in links if n.attrs["data-raos-cta-id"] == b["cta_id"])
            assert link.attrs["href"] == b["href"]
            assert all(
                link.attrs["data-raos-" + k.replace("_", "-")] == b[k]
                for k in b
                if k != "href"
            )
        if a["bindings"]:
            placements = {b["placement"] for b in a["bindings"]}
            assert placements <= {"top_summary", "comparison_table", "final_summary"}
            assert "comparison_table" in placements
            assert placements <= set(PLACEMENTS)


@pytest.mark.parametrize("state", ["SOLD_OUT", "AVAILABLE", "UNKNOWN"])
def test_comparison_sale_status_matches_verified_offers(catalog, state):
    product = catalog["products"][0]
    pid = product["product_id"]
    for offer in catalog["offers"]:
        if offer["product_id"] == pid:
            offer.update(state=state, identity_verified=True)
    html, _ = compile(catalog)
    root = fragment(html["countertop-dishwasher-for-small-households"])
    row = next(n for n in root.find(tag="tr") if n.attrs.get("data-product-id") == pid)
    links = [n for n in row.find(tag="a") if n.has("ps-offer-link")]
    assert len(links) == 1
    assert links[0].attrs["data-raos-product-id"] == pid
    assert links[0].attrs["data-raos-placement"] == "comparison_table"
    assert not any(term in links[0].text() for term in ("在庫あり", "購入可能", "最安"))


@pytest.mark.parametrize(
    "mutation", ["model", "rights", "private", "missing_research", "route"]
)
def test_reject_misbinding_or_missing_management(catalog, mutation):
    if mutation == "model":
        catalog["offers"][0]["product_model"] = "OTHER-MODEL"
    elif mutation == "rights":
        catalog["offers"][0]["affiliate"] = True
    elif mutation == "private":
        catalog["offers"][0]["provider_measurement_id"] = "PRIVATE"
    elif mutation == "missing_research":
        pid = catalog["products"][0]["product_id"]
        catalog["offers"] = [o for o in catalog["offers"] if o["product_id"] != pid]
        catalog["research_issues"] = [
            i for i in catalog["research_issues"] if i["product_id"] != pid
        ]
    else:
        catalog["routes"][0]["anchor"] = "another-product"
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def test_asp_normalized_record_requires_independent_permission_and_never_projects_finance(
    catalog,
):
    offer = deepcopy(catalog["offers"][0])
    offer.update(
        affiliate=True,
        advertiser_authorized=True,
        link_usage_authorized=True,
        site_origin="https://kurashinoshirube.com",
    )
    record = normalize_record(
        "a8net",
        "products",
        {
            "product_id": "private-source-id",
            "affiliate_url": offer["url"],
            "commission": "9999",
            "raw_secret": "never public",
        },
    )
    review = {
        "schema": "RAOS_PURCHASE_ASP_REVIEW_V1",
        "source_fingerprint_sha256": record["fingerprint_sha256"],
        "material_storage_authorized": True,
        "offer": offer,
    }
    assert approved_offer_from_normalized(record, review) == offer
    for key, value in [
        ("advertiser_authorized", False),
        ("link_usage_authorized", False),
        ("identity_verified", False),
        ("url", "https://example.invalid/other"),
    ]:
        bad = deepcopy(review)
        bad["offer"][key] = value
        with pytest.raises(ValueError):
            approved_offer_from_normalized(record, bad)
    bad = deepcopy(review)
    bad["source_fingerprint_sha256"] = "x" * 64
    with pytest.raises(ValueError):
        approved_offer_from_normalized(record, bad)


def test_advertising_changes_do_not_change_conditions_or_model_selection(catalog):
    before, _ = compile(catalog)
    for offer in catalog["offers"]:
        offer.update(
            affiliate=True,
            advertiser_authorized=True,
            link_usage_authorized=True,
            site_origin="https://kurashinoshirube.com",
        )
    after, _ = compile(catalog)
    for slug in before:
        for cls in ("ps-condition-grid", "ps-product-grid"):
            # Ads may change link disclosure attributes; readable recommendation reasons stay identical.
            assert [n.text() for n in fragment(before[slug]).walk() if n.has(cls)] == [
                n.text() for n in fragment(after[slug]).walk() if n.has(cls)
            ]


@pytest.mark.parametrize(
    ("checked_at", "display"),
    [
        ("2026-09-10T01:43:00+00:00", "2026年9月10日 10:43（日本時間）"),
        ("2026-09-10T23:30:00+00:00", "2026年9月11日 08:30（日本時間）"),
        ("2026-09-11T08:30:00+09:00", "2026年9月11日 08:30（日本時間）"),
    ],
)
def test_offer_time_displays_japan_time_without_changing_expiry_metadata(
    catalog, checked_at, display
):
    offer = catalog["offers"][0]
    offer["checked_at"] = checked_at
    html, _ = compile(catalog)
    matched = 0
    for body in html.values():
        for node in fragment(body).walk():
            if node.attrs.get("data-ps-offer") != offer["offer_id"]:
                continue
            matched += 1
            assert node.attrs["data-ps-checked-at"] == checked_at
            assert node.attrs["data-ps-valid-until"] == offer["valid_until"]
            times = node.find(tag="time")
            assert len(times) == 1
            assert times[0].attrs["datetime"] == checked_at
            assert times[0].text() == display
    assert matched


def test_published_water_conditions_and_unknowns_reach_guides(catalog):
    html, _ = compile(catalog)
    cost = fragment(html["dishwasher-running-cost"])
    profile = next(
        n
        for n in cost.walk()
        if n.attrs.get("data-raos-cost-profile") == "ss-ma251-spec"
    )
    assert profile.attrs["data-raos-water-litres"] == "6"
    assert (
        profile.attrs["data-raos-cost-course"] == "仕様掲載条件（コース別値は未確認）"
    )
    assert "data-raos-energy-wh" not in profile.attrs
    unknown = next(
        n
        for n in cost.walk()
        if n.attrs.get("data-raos-cost-profile") == "dws-33b-unknown"
    )
    assert unknown.attrs["data-raos-water-litres"] == "6"
    assert (
        unknown.attrs["data-raos-cost-course"] == "標準（食器18点・小物12点、水温20℃）"
    )
    assert "data-raos-energy-wh" not in unknown.attrs
    installation = fragment(html["dishwasher-installation-measurement"])
    values = [
        json.loads(n.attrs["data-ps-installation"])
        for n in installation.walk()
        if "data-ps-installation" in n.attrs
    ]
    assert any(
        v.get("width_mm") == 420 and v.get("door_depth_mm") == 760 for v in values
    )
    steps = next(
        n for n in installation.walk() if n.attrs.get("id") == "guide-measurement-steps"
    )
    assert len(steps.find(tag="li")) == 5
    article = next(
        a
        for a in catalog["articles"]
        if a["slug"] == "dishwasher-installation-measurement"
    )
    article["reader_steps"]["steps"][0] = "<script>not markup</script>"
    updated, _ = compile(catalog)
    assert "<script>not markup</script>" not in updated[article["slug"]]
    assert "&lt;script&gt;not markup&lt;/script&gt;" in updated[article["slug"]]


@pytest.mark.parametrize(
    ("model", "slug", "primary", "secondary"),
    [
        ("NP-TSP1-W", "dishwasher-detergent-guide", "detergent", "prohibited"),
        ("SS-MA251", "dishwasher-installation-measurement", "installation", "drainage"),
    ],
)
def test_new_procedure_details_stay_together_before_other_topics(
    catalog, model, slug, primary, secondary
):
    product = next(p for p in catalog["products"] if p["exact_model"] == model)
    first = next(f for f in product["guide_facts"] if f["field"] == primary)
    other = next(f for f in product["guide_facts"] if f["field"] == secondary)
    later = deepcopy(first)
    first = {**first, "text": "最初の作業手順"}
    other = {**other, "text": "別の確認事項"}
    later["text"] = "追加確認した作業手順"
    # Keep the other fields: installation numbers must stay restated (KS-010).
    product["guide_facts"] = [first, other, later] + [
        f for f in product["guide_facts"] if f["field"] not in {primary, secondary}
    ]
    html, _ = compile(catalog)
    section = next(
        n for n in fragment(html[slug]).walk() if n.attrs.get("id") == product["anchor"]
    )
    text = section.text()
    assert (
        text.index(first["text"])
        < text.index(later["text"])
        < text.index(other["text"])
    )
    for fact in (first, later, other):
        assert text.count(fact["text"]) == 1
    assert (
        len(
            [
                a
                for a in section.find(tag="a")
                if a.attrs.get("href") == first["source_url"]
            ]
        )
        >= 2
    )


def test_guides_keep_unconfirmed_facts_without_repeating_seller_research(catalog):
    catalog = deepcopy(catalog)
    product = next(
        p for p in catalog["products"] if p["product_id"] == "PRD-PANASONIC-NP-TMLK1"
    )
    drainage = next(f for f in product["guide_facts"] if f["field"] == "drainage")
    drainage.update(state="UNKNOWN", text="排水条件は未確認です。")
    clearance = next(f for f in product["guide_facts"] if f["field"] == "clearance")
    clearance.update(state="UNKNOWN", text="必要余白は追加確認中です。")
    # A withdrawn clearance record cannot leave its numbers in the fit check (KS-010).
    for key in ("above_mm", "left_mm", "right_mm", "rear_mm"):
        product["installation"][key] = None
    html, _ = compile(catalog)
    for article in catalog["articles"]:
        if article["kind"] == "guide":
            assert 'class="ps-research"' not in html[article["slug"]]
    # The water comparison now includes drainage and must propagate withdrawn facts.
    assert "排水条件は未確認です。" in html["dishwasher-installation-measurement"]
    water = fragment(html["dishwasher-water-supply-methods"])
    row = next(
        n for n in water.find(tag="tr") if n.attrs.get("id") == product["anchor"]
    )
    assert "排水条件は未確認です。" in row.text()
    assert "20cm" not in row.text()
    assert "必要余白は追加確認中" in html["dishwasher-installation-measurement"]
    assert "コース別の消費電力量は未確認" in html["dishwasher-running-cost"]
    assert 'class="ps-research"' in html["countertop-dishwasher-for-small-households"]
    for article in catalog["articles"]:
        if article["kind"] != "comparison":
            continue
        root = fragment(html[article["slug"]])
        for product_id in article["product_ids"]:
            product = next(
                p for p in catalog["products"] if p["product_id"] == product_id
            )
            seller = next(
                n
                for n in root.walk()
                if n.attrs.get("id") == "ps-seller-" + product["anchor"]
            )
            if not article.get("authored_comparison"):
                assert len([n for n in seller.walk() if n.has("ps-research")]) == 1
        if not article.get("authored_comparison"):
            assert len([n for n in root.walk() if n.has("ps-research")]) == len(
                article["product_ids"]
            )
        else:
            assert not root.find(cls="ps-research")


def test_comparison_decision_details_follow_summary_and_specs_and_escape_text(catalog):
    article = next(
        a for a in catalog["articles"] if a["slug"] == "portable-power-station-guide"
    )
    html, _ = compile(catalog)
    page = html[article["slug"]]
    assert (
        page.index('id="ps-choose"')
        < page.index('id="ps-specs"')
        < page.index('id="ps-decision-steps"')
    )
    assert (
        "240Wh" in page and "80%なら必要容量300Wh" in page and "70%なら約343Wh" in page
    )
    assert "稼働時間を保証しません" in page
    article["decision_steps"]["steps"][0] = "<script>not markup</script>"
    updated, _ = compile(catalog)
    assert "<script>not markup</script>" not in updated[article["slug"]]
    assert "&lt;script&gt;not markup&lt;/script&gt;" in updated[article["slug"]]


def test_reviewed_bookmarks_land_in_current_section_and_reject_missing_targets(catalog):
    html, _ = compile(catalog)
    for article in catalog["articles"]:
        if not article.get("legacy_anchor_targets"):
            continue
        root = fragment(html[article["slug"]])
        for identity, target in article["legacy_anchor_targets"].items():
            aliases = [n for n in root.walk() if n.attrs.get("id") == identity]
            assert len(aliases) == 1
            ancestor = aliases[0].parent
            if ancestor.tag == "th":
                ancestor = ancestor.parent
            assert ancestor.attrs.get("id") == (
                "ps-choose" if target == "ps-products" else target
            )
            assert ancestor.text()
    article = next(
        a
        for a in catalog["articles"]
        if a.get("legacy_anchor_targets") and not a.get("authored_comparison")
    )
    identity = next(iter(article["legacy_anchor_targets"]))
    article["legacy_anchor_targets"][identity] = "missing-section"
    with pytest.raises(ValueError, match="PURCHASE_LEGACY_ALIAS_TARGET_INVALID"):
        compile(catalog)


def test_guides_and_comparisons_preserve_next_reading_links_as_visible_content(catalog):
    html, _ = compile(catalog)
    for article in catalog["articles"]:
        if article["kind"] not in {"guide", "comparison"}:
            continue
        slug = article["slug"]
        old = fragment((BASE / "articles" / f"{slug}.html").read_text())
        root = fragment(html[slug])
        source = next(
            (n for n in old.find(tag="section") if n.attrs.get("id") == "ks-next-read"),
            None,
        )
        if source is None:
            assert article["kind"] == "comparison"
            continue
        section = next(
            n for n in root.find(tag="section") if n.attrs.get("id") == "ks-next-read"
        )
        assert section.text() == source.text()
        assert [a.attrs["href"] for a in section.find(tag="a")] == [
            a.attrs["href"] for a in source.find(tag="a")
        ]
        assert any(
            n.attrs.get("id") == "ks-next-read-title" for n in section.find(tag="h2")
        )
        assert sum(n.attrs.get("id") == "ks-next-read" for n in root.walk()) == 1
        if article["kind"] == "guide":
            nav = next(
                n for n in root.find(tag="nav") if n.attrs.get("id") == "ks-article-nav"
            )
            assert nav.find(tag="a") and nav.text()


def test_legacy_source_notes_preserve_identity_without_reintroducing_old_specs(catalog):
    from raos.application.editorial.purchase_support import legacy_source_notes

    registry = json.loads(
        (
            ROOT / "changes/editorial-portfolio-v3/local-reader-guides.v1.json"
        ).read_text()
    )
    for article in catalog["articles"]:
        notes = article.get("legacy_source_notes", [])
        if not notes:
            continue
        body = legacy_source_notes(article, registry)
        root = fragment(body)
        for note in notes:
            fact = next(
                f
                for f in registry["facts"]
                if f["evidence_ref"] == note["evidence_ref"]
            )
            target = next(
                n
                for n in root.walk()
                if n.attrs.get("id") == "guide-evidence-" + note["evidence_ref"]
            )
            assert target.tag == "li"
            assert target.find(tag="a")
            assert fact["locator"] in target.text()
            assert fact["text"] not in body
        altered = deepcopy(registry)
        ref = notes[0]["evidence_ref"]
        next(f for f in altered["facts"] if f["evidence_ref"] == ref)["exact_model"] = (
            "WRONG-MODEL"
        )
        with pytest.raises(ValueError, match="GUIDE_LEGACY_SOURCE_MODEL_MISMATCH"):
            legacy_source_notes(article, altered)


def test_decision_steps_follow_the_scope_the_reader_has_selected(catalog):
    html, _ = compile(catalog)
    robot = html["compact-robot-vacuum-shortlist"]
    power = html["portable-power-station-guide"]
    assert (
        robot.index('id="ps-choose"')
        < robot.index('id="ps-specs"')
        < robot.index('id="ps-decision-steps"')
    )
    assert (
        power.index('id="ps-choose"')
        < power.index('id="ps-specs"')
        < power.index('id="ps-decision-steps"')
    )
    assert robot.count('id="ps-decision-steps"') == 1
    assert power.count('id="ps-decision-steps"') == 1


def test_historical_product_bookmarks_do_not_become_current_purchase_links(catalog):
    articles, _ = compile(catalog)
    root = fragment(articles["lightweight-carry-on-suitcase-under-3kg"])
    for identity in ["under-3kg-cta-02-note", "under-3kg-cta-04-note"]:
        alias = next(n for n in root.walk() if n.attrs.get("id") == identity)
        # Historical bookmarks lead to the whole comparison, never to a
        # different product's identity cell or merchant CTA.
        assert alias.parent.attrs.get("id") == "ps-specs"
        assert not alias.children
        assert not alias.attrs.get("data-raos-product-id")
        assert not alias.attrs.get("href")
    rows = root.find(tag="tr")
    assert not any("82353171" in n.text() or "134679-1549" in n.text() for n in rows)
    caution = next(
        n for n in root.walk() if n.attrs.get("id") == "under-3kg-caution-title"
    )
    assert caution.tag == "h2"
    assert "運航会社" in caution.parent.text()
    assert all(not n.children for n in root.walk() if n.has("ps-compat-anchors"))


def test_kitchen_keeps_readable_preconditions_and_original_destinations(catalog):
    articles, _ = compile(catalog)
    root = fragment(articles["kitchen"])
    for identity, phrase in [
        ("kitchen-start", "台所の道具を、洗う量と手間から。"),
        ("kitchen-start", "いま掲載しているのは卓上食洗機です。"),
        ("kitchen-axes", "普段の食器の量と形"),
        ("kitchen-comparisons", "大容量を比べる"),
        ("purchase-checks", "送料・必要品を含む総額"),
    ]:
        node = next(n for n in root.walk() if n.attrs.get("id") == identity)
        assert phrase in node.text()
    assert all(not n.children for n in root.walk() if n.has("ps-compat-anchors"))
    assert len(root.find(tag="figure", cls="ks-category-visual")) == 1
    assert "SS-MA251" not in root.text()
    assert "工事なし（タンク式など）" in root.text()
    assert len(root.find(tag="img")) == 5


def test_luggage_bookmarks_reach_weight_formula_and_flight_checks(catalog):
    articles, _ = compile(catalog)
    html = articles["lightweight-carry-on-suitcase-under-3kg"]
    root = fragment(html)
    caution = next(n for n in root.walk() if n.attrs.get("id") == "purchase-check")
    assert caution.parent.attrs["id"] == "ps-flight-purchase-check"
    assert "運航会社" in caution.parent.text()
    method = next(
        n for n in root.walk() if n.attrs.get("id") == "under-3kg-method-title"
    )
    assert method.parent.attrs["id"] == "carry-on-rules"
    assert "航空会社" in method.parent.text()
    calculation = next(
        n for n in root.walk() if n.attrs.get("id") == "suitcase-weight-example-title"
    )
    assert "総重量上限から身の回り品とケース本体を引いた計算例" in calculation.text()
    assert "7−1−2.1＝3.9kg" in calculation.text()
    assert "7−1−2.7＝3.3kg" in calculation.text()
    assert (
        html.index('id="carry-on-rules"')
        < html.index('id="ps-choose"')
        < html.index('id="ps-specs"')
        < html.index('id="suitcase-weight-example-title"')
        < html.index('id="ps-evidence"')
    )


def test_comparison_method_bookmarks_explain_scope_in_details_after_sellers(catalog):
    articles, _ = compile(catalog)
    for slug, key, limitation in [
        ("countertop-dishwasher-for-small-households", "dish", "公表条件が異なります"),
        ("compact-robot-vacuum-shortlist", "robot", "軸名が未確認"),
        ("portable-power-station-guide", "power", "使用時間の保証ではありません"),
    ]:
        html = articles[slug]
        root = fragment(html)
        method = next(
            n for n in root.walk() if n.attrs.get("id") == f"blk-{key}-005-title"
        )
        article = next(a for a in catalog["articles"] if a["slug"] == slug)
        if article.get("authored_comparison"):
            assert method.tag == "span"
            assert limitation.replace(
                "軸名が未確認", "軸名未確認"
            ) in root.text().replace("軸名が未確認", "軸名未確認")
            assert not root.find(cls="ps-comparison-method")
            assert len(root.find(tag="section", cls="ps-source-product")) == 0
        else:
            assert method.tag == "h2"
            assert limitation in method.parent.text()
            assert "広告報酬を加点せず" in method.parent.text()
            assert (
                html.index('id="ps-offers"')
                < html.index(f'id="blk-{key}-005-title"')
                < html.index('id="ps-evidence"')
            )


def test_ten_comparisons_share_exact_identities_and_keep_slim_supplementary(catalog):
    comparisons = {
        a["post_id"]: a for a in catalog["articles"] if a["kind"] == "comparison"
    }
    assert {pid: len(a["product_ids"]) for pid, a in comparisons.items()} == {
        41: 4,
        83: 4,
        30: 4,
        28: 4,
        19: 3,
        82: 4,
        84: 4,
        85: 2,
        86: 2,
        29: 4,
    }
    assert set(catalog["target_post_ids"]) == set(comparisons)
    products = {p["product_id"]: p for p in catalog["products"]}
    assert len(products) == len(catalog["products"]) == 54
    assert set(comparisons[85]["product_ids"]) <= set(comparisons[30]["product_ids"])
    assert "PRD-ANKER-SOLIX-C300" in set(comparisons[28]["product_ids"]) & set(
        comparisons[29]["product_ids"]
    )
    assert "PRD-ACE-DIFFERENCE-05721" in set(comparisons[19]["product_ids"]) & set(
        comparisons[84]["product_ids"]
    )
    assert "PRD-PANASONIC-NP-TMLK1" in set(comparisons[41]["product_ids"]) & set(
        comparisons[86]["product_ids"]
    )
    assert products["PRD-THANKO-RAKUA-MINI-PLUS"]["exact_model"] == "TK-MDW22B"
    assert "PRD-THANKO-RAKUA-MINI-PLUS" not in comparisons[41]["product_ids"]
    slim = "PRD-IROBOT-ROOMBA-MINI-SLIM-F115060"
    assert comparisons[85]["supplementary_product_ids"] == [slim]
    assert all(slim not in a["product_ids"] for a in comparisons.values())
    bodies, _ = compile(catalog)
    root = fragment(bodies[comparisons[85]["slug"]])
    primary = next(n for n in root.walk() if n.attrs.get("id") == "ps-specs")
    assert "F115060" not in primary.text()
    supplemental = next(
        n for n in root.walk() if n.attrs.get("id") == "ps-other-configurations"
    )
    assert "F115060" in supplemental.text() and "主比較とは別" in supplemental.text()
    assert "自動ゴミ収集はなく" in supplemental.text()


def test_rejects_overlap_between_primary_and_supplementary_identities(catalog):
    article = next(a for a in catalog["articles"] if a["post_id"] == 85)
    article["supplementary_product_ids"] = [article["product_ids"][0]]
    with pytest.raises(ValueError):
        validate_catalog(catalog)


def _product(catalog, pid):
    return next(p for p in catalog["products"] if p["product_id"] == pid)


def _fact(product, label):
    return next(f for f in product["facts"] if f["label"].startswith(label))


def _guide(product, field):
    return next(f for f in product["guide_facts"] if f["field"] == field)


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("fact_width_text", "PURCHASE_DIMENSION_SOURCE_MISMATCH"),
        ("guide_width_text", "PURCHASE_DIMENSION_SOURCE_MISMATCH"),
        ("installation_width", "PURCHASE_DIMENSION_SOURCE_MISMATCH"),
        ("installation_door_depth", "PURCHASE_DIMENSION_SOURCE_MISMATCH"),
        ("installation_rear", "PURCHASE_DIMENSION_SOURCE_MISMATCH"),
        ("guide_dimensions_removed", "PURCHASE_DIMENSION_SOURCE_REQUIRED"),
        ("fact_dimensions_removed", "PURCHASE_DIMENSION_SOURCE_REQUIRED"),
    ],
)
def test_installation_numbers_agree_with_dimension_facts_and_guide_facts(
    catalog, mutation, code
):
    # installation is the numeric source; fact and guide texts restate it.
    # Door and clearance use containment only (486 and 18 occur in no text).
    product = _product(catalog, "PRD-PANASONIC-NP-TMLK1")
    if mutation == "fact_width_text":
        _fact(product, "本体寸法")["text"] = "311×225×435mm"
    elif mutation == "guide_width_text":
        _guide(product, "dimensions")["text"] = "本体は幅311×奥行225×高さ435mm。"
    elif mutation == "installation_width":
        product["installation"]["width_mm"] = 311
    elif mutation == "installation_door_depth":
        product["installation"]["door_depth_mm"] = 486
    elif mutation == "installation_rear":
        product["installation"]["rear_mm"] = 18
    elif mutation == "guide_dimensions_removed":
        product["guide_facts"].remove(_guide(product, "dimensions"))
    else:
        product["facts"].remove(_fact(product, "本体寸法"))
    with pytest.raises(ValueError, match=code):
        validate_catalog(catalog)


def test_installation_consistency_checker_lists_every_mismatch_without_raising(
    catalog,
):
    from raos.application.editorial.purchase_support import (
        installation_consistency_mismatches,
        validate_installation_consistency,
    )

    validate_catalog(catalog)
    assert all(
        installation_consistency_mismatches(p) == [] for p in catalog["products"]
    )
    product = _product(catalog, "PRD-PANASONIC-NP-TMLK1")
    product["installation"]["width_mm"] = 311
    product["installation"]["rear_mm"] = 18
    # A model number digit next to ASCII letters is not a dimension token.
    guide = _guide(_product(catalog, "PRD-THANKO-RAKUA-MINI-COLOR"), "dimensions")
    assert "TDWS25SBL" in guide["text"]
    rows = installation_consistency_mismatches(product)
    assert {(r["group"], r["source"], tuple(r["keys"])) for r in rows} == {
        ("dimensions", "facts", ("width_mm",)),
        ("dimensions", "guide_facts", ("width_mm",)),
        ("clearance", "facts", ("rear_mm",)),
        ("clearance", "guide_facts", ("rear_mm",)),
    }
    assert {r["code"] for r in rows} == {"PURCHASE_DIMENSION_SOURCE_MISMATCH"}
    assert all(r["product_id"] == "PRD-PANASONIC-NP-TMLK1" for r in rows)
    with pytest.raises(ValueError, match="PURCHASE_DIMENSION_SOURCE_MISMATCH"):
        validate_installation_consistency(product)


def _conflict_door(catalog):
    """In-memory CONFLICT fixture; the tracked NP-TSP1 record stays UNKNOWN."""
    product = _product(catalog, "PRD-PANASONIC-NP-TSP1")
    sources = [
        {
            "value": "開扉奥行 上386mm・下362mm",
            "source_url": "https://panasonic.jp/dish/products/NP-TSP1/spec.html",
            "locator": "個別仕様の本体外形寸法",
            "checked_at": "2026-09-13",
        },
        {
            "value": "開閉時最大433mm",
            "source_url": "https://panasonic.jp/dish/comparison.html",
            "locator": "公式比較表の開閉時最大寸法",
            "checked_at": "2026-09-13",
        },
    ]
    for record in (_fact(product, "開扉時の寸法"), _guide(product, "door")):
        record["state"] = "CONFLICT"
        record["conflict_sources"] = deepcopy(sources)
        record["conflict_installation_keys"] = ["door_depth_mm"]
    return product


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("one_source", "PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"),
        ("duplicate_source", "PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"),
        ("http_source", "PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"),
        ("empty_value", "PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"),
        ("guide_one_source", "PURCHASE_FACT_CONFLICT_SOURCES_REQUIRED"),
        ("door_depth_433", "PURCHASE_CONFLICT_VALUE_ASSERTED"),
        ("door_depth_400", "PURCHASE_CONFLICT_VALUE_ASSERTED"),
        ("keys_missing", "PURCHASE_CONFLICT_INSTALLATION_KEYS_REQUIRED"),
        ("keys_outside_group", "PURCHASE_CONFLICT_INSTALLATION_KEYS_INVALID"),
        ("known_with_sources", "PURCHASE_FACT_CONFLICT_SOURCES_UNEXPECTED"),
        ("known_with_keys", "PURCHASE_FACT_CONFLICT_SOURCES_UNEXPECTED"),
        ("guide_state_invalid", "PURCHASE_FACT_SOURCE_REQUIRED"),
    ],
)
def test_source_conflict_is_a_distinct_fact_state(catalog, mutation, code):
    from raos.application.editorial.purchase_support import (
        FACT_STATES,
        UNSETTLED_FACT_STATES,
    )

    assert FACT_STATES == {"KNOWN", "PRESERVED", "UNKNOWN", "CONFLICT"}
    assert UNSETTLED_FACT_STATES == {"UNKNOWN", "CONFLICT"}
    product = _conflict_door(catalog)
    validate_catalog(deepcopy(catalog))
    fact, guide = _fact(product, "開扉時の寸法"), _guide(product, "door")
    if mutation == "one_source":
        fact["conflict_sources"].pop()
    elif mutation == "duplicate_source":
        fact["conflict_sources"][1].update(
            source_url=fact["conflict_sources"][0]["source_url"],
            locator=fact["conflict_sources"][0]["locator"],
        )
    elif mutation == "http_source":
        fact["conflict_sources"][1]["source_url"] = "http://panasonic.jp/dish/"
    elif mutation == "empty_value":
        fact["conflict_sources"][0]["value"] = " "
    elif mutation == "guide_one_source":
        guide["conflict_sources"].pop()
    elif mutation == "door_depth_433":
        product["installation"]["door_depth_mm"] = 433
    elif mutation == "door_depth_400":
        product["installation"]["door_depth_mm"] = 400
    elif mutation == "keys_missing":
        del fact["conflict_installation_keys"]
    elif mutation == "keys_outside_group":
        guide["conflict_installation_keys"] = ["width_mm"]
    elif mutation == "known_with_sources":
        other = _fact(product, "本体寸法")
        other["conflict_sources"] = deepcopy(fact["conflict_sources"])
    elif mutation == "known_with_keys":
        _guide(product, "dimensions")["conflict_installation_keys"] = ["width_mm"]
    else:
        guide["state"] = "SETTLED"
    with pytest.raises(ValueError, match=code):
        validate_catalog(catalog)


def test_conflict_fact_state_reaches_markup_and_counts_as_unsettled(catalog):
    _conflict_door(catalog)
    water = next(
        p
        for p in catalog["products"]
        if any(f["field"] == "water_supply" for f in p.get("guide_facts", []))
        and p.get("installation")
    )
    supply = _guide(water, "water_supply")
    supply.update(
        state="CONFLICT",
        text="給水条件の公式表記が2資料で異なる（テスト用の文）",
        conflict_sources=[
            {
                "value": "資料Aの給水条件",
                "source_url": supply["source_url"],
                "locator": "資料A",
                "checked_at": supply["checked_at"],
            },
            {
                "value": "資料Bの給水条件",
                "source_url": supply["source_url"],
                "locator": "資料B",
                "checked_at": supply["checked_at"],
            },
        ],
    )
    validate_catalog(catalog)
    html, _ = compile(catalog)
    main = fragment(html["countertop-dishwasher-for-small-households"])
    cells = [
        n
        for n in main.walk()
        if n.attrs.get("data-ps-product") == "PRD-PANASONIC-NP-TSP1"
        and n.attrs.get("data-ps-fact-state") == "CONFLICT"
    ]
    assert cells and all("どちらもドア開閉時の最大寸法と表記しています" in n.text() for n in cells)
    guide = fragment(html["dishwasher-water-supply-methods"])
    row = next(n for n in guide.walk() if n.attrs.get("id") == water["anchor"])
    group = next(
        n for n in row.walk() if n.attrs.get("data-ps-guide-field") == "water_supply"
    )
    # A CONFLICT record leads with the note naming both sources (KS-009, decision 12).
    assert group.find(tag="dd")[0].text() == (
        "公式資料で値が異なります（資料A：資料Aの給水条件、資料B：資料Bの給水条件）。"
        "どちらの値かはメーカー（相談窓口）へ確認してください。" + supply["text"]
    )


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            "dimensions_reordered",
            {("dimensions", "facts", ("width_mm", "depth_mm"))},
        ),
        ("model_name_before_dimensions", set()),
        ("all_none_group_without_records", set()),
    ],
)
def test_installation_consistency_order_model_names_and_withdrawn_groups(
    catalog, mutation, expected
):
    from raos.application.editorial.purchase_support import (
        installation_consistency_mismatches,
    )

    product = _product(catalog, "PRD-PANASONIC-NP-TMLK1")
    if mutation == "dimensions_reordered":
        # The same three numbers in another order: containment alone accepts it.
        _fact(product, "本体寸法")["text"] = "225×310×435mm"
    elif mutation == "model_name_before_dimensions":
        # A digit joined to ASCII letters (NP-TMLK1) is not a dimension token.
        _guide(product, "dimensions")["text"] = (
            "NP-TMLK1の本体は幅310×奥行225×高さ435mm。"
        )
    else:
        # A group whose keys are all None is skipped, so no record is required.
        product["installation"].update(door_depth_mm=None, door_height_mm=None)
        product["facts"].remove(_fact(product, "開扉時の寸法"))
        product["guide_facts"].remove(_guide(product, "door"))
    rows = installation_consistency_mismatches(product)
    assert {(r["group"], r["source"], tuple(r["keys"])) for r in rows} == expected
