from dataclasses import asdict, replace
from pathlib import Path

from raos.application.editorial.reader_experience_projection import fragment, project_article

from raos.application.editorial.reader_experience_v1 import (
    COMPARISON_REQUIREMENTS,
    CheckedFact,
    CtaEvidence,
    MediaAsset,
    approved_media_record,
    comparison_issues,
    cta_visible,
    validate_experience,
)


def test_unknown_or_undated_fact_never_completes_a_comparison() -> None:
    fact = CheckedFact("fact", "official", "2026-09-01", "KNOWN")
    products = {p: dict.fromkeys(COMPARISON_REQUIREMENTS, fact) for p in ("a", "b")}
    assert comparison_issues(products) == ()
    products["a"]["sales_state"] = replace(fact, state="UNKNOWN")
    products["b"]["door_or_installation_space"] = replace(fact, checked_at=None)
    assert comparison_issues(products) == ("a.sales_state", "b.door_or_installation_space")


def test_offer_requires_the_exact_product_url_and_sales_eligibility() -> None:
    url = "https://example.test/offer"
    evidence = CtaEvidence(
        existing_targets=frozenset({"#installation"}),
        official_urls=frozenset({"https://manufacturer.test/manual"}),
        verified_offers=frozenset({("a", url)}),
        eligible_products=frozenset({"a"}),
    )
    assert cta_visible("offer", url, "a", evidence, article_type="shortlist")
    assert not cta_visible("offer", url, "b", evidence, article_type="shortlist")
    assert not cta_visible("offer", url, "a", replace(evidence, eligible_products=frozenset()), article_type="shortlist")
    assert not cta_visible("offer", url, "a", evidence, article_type="status_check")
    assert cta_visible("learn", "#installation", None, evidence, article_type="shortlist")
    assert not cta_visible("learn", "/missing/", None, evidence, article_type="shortlist")
    assert cta_visible("verify", "https://manufacturer.test/manual", None, evidence, article_type="status_check")


def test_media_needs_approval_and_complete_usage_metadata() -> None:
    asset = MediaAsset("diagram", "https://manufacturer.test/manual", "original specification diagram", "2026-09-01", "approved", "Door clearance diagram", "Official dimensions; not a product photo", (4, 3), "dimension", "svg")
    assert asset.displayable
    for change in ({"approval": "pending"}, {"checked_at": None}, {"usage_basis": ""}, {"alt": ""}, {"aspect_ratio": (0, 3)}):
        assert not replace(asset, **change).displayable


def test_media_records_preserve_raw_json_eligibility_rules() -> None:
    asset = MediaAsset("diagram", "https://manufacturer.test/manual", "original diagram", "2026-09-01", "approved", "Dimensions", "Official dimensions", (4, 3), "dimension", "svg")
    raw = asdict(asset)
    assert approved_media_record(raw)
    assert approved_media_record({**raw, "aspect_ratio": [4, 3], "extra": "ignored"})
    for key in raw:
        assert not approved_media_record({k: v for k, v in raw.items() if k != key})
    for change in (
        {"approval": "pending"}, {"approval": []}, {"asset_type": ""},
        {"asset_type": []}, {"checked_at": None}, {"checked_at": "2026-02-30"},
        {"checked_at": 20260901}, {"source": "http://manufacturer.test/manual"},
        {"source": 42}, {"alt": " "}, {"caption": None}, {"usage_basis": []},
        {"aspect_ratio": [True, 3]}, {"aspect_ratio": [4.0, 3]},
        {"aspect_ratio": [0, 3]}, {"aspect_ratio": [4]},
        {"aspect_ratio": [4, 3, 2]}, {"aspect_ratio": "4:3"},
    ):
        assert not approved_media_record({**raw, **change}), change


def test_status_article_cannot_become_a_recommendation_via_the_view_model() -> None:
    experience = {
        "article_type": "status_check",
        "research_status": {"ranking_uses_commission": False, "real_world_tested": False},
        "decision_summary": {"options": [{"product_ref": "a", "condition": "条件", "reason": "理由", "tradeoff": "妥協点"}]},
        "evidence": ["unknown-evidence"],
    }
    assert validate_experience(experience, product_refs=frozenset({"a"}), evidence_refs=frozenset()) == (
        "status_check.recommendation_forbidden", "evidence.unresolved_reference",
    )


def test_projection_omits_unverified_commerce_and_preserves_sources_and_dates() -> None:
    root = Path(__file__).resolve().parents[2]
    markup = (root / "changes/wordpress-local-preview-v1/fixtures/articles/countertop-dishwasher-for-small-households.html").read_text()
    result = project_article(markup, article_id="st1704-countertop-dishwasher-for-small-households", experience={"article_type": "shortlist"})
    parsed = fragment(result)
    assert not parsed.find(cls="raos-product-card__media")
    assert not parsed.find(cls="raos-product-image-status")
    assert not any("data-raos-placement" in e.attrs for e in parsed.find(tag="a"))
    assert "2026年9月1日" in result
    assert "SS-M171" in result and "TK-MDW22W" in result
    original_sources = {n.attrs["href"] for n in fragment(markup).find(tag="a") if "data-raos-placement" not in n.attrs and str(n.attrs.get("href", "")).startswith("https://")}
    assert original_sources <= {n.attrs.get("href") for n in parsed.find(tag="a")}
    assert len(parsed.find(cls="raos-article-facts")) == 1
    assert project_article(result, article_id="st1704-countertop-dishwasher-for-small-households", experience={"article_type": "shortlist"}) == result


def test_repeated_projection_rechecks_offers_when_evidence_is_removed() -> None:
    markup = '<div class="raos-editorial-v2"><span class="raos-reader-view" hidden></span><p class="summary-action"><a data-raos-product-id="a" data-raos-placement="product_card" href="https://example.test/offer">Offer</a></p><p>UNKNOWN</p></div>'
    result = project_article(markup, article_id="example")
    assert "example.test" not in result and "UNKNOWN" in result


def test_registered_view_cannot_relabel_a_status_article(tmp_path) -> None:
    import json
    import shutil
    import pytest
    from raos.application.editorial.reader_experience_projection import load_experiences, REGISTRY_PATH
    root = Path(__file__).resolve().parents[2]
    for relative in (REGISTRY_PATH, Path('changes/editorial-portfolio-v2/editorial-portfolio.v2.json'), Path('changes/editorial-portfolio-v3/editorial-identities.v1.json'), Path('changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json')):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    assert load_experiences(tmp_path)['solota-vs-rakua-mini-plus']['article_type'] == 'status_check'
    path = tmp_path / REGISTRY_PATH
    registry = json.loads(path.read_text())
    registry['articles']['solota-vs-rakua-mini-plus']['article_type'] = 'comparison'
    path.write_text(json.dumps(registry))
    with pytest.raises(ValueError, match='INTENT_MISMATCH'):
        load_experiences(tmp_path)


def test_unverified_experience_rejects_positive_claims_but_accepts_limits() -> None:
    base = {'article_type':'shortlist', 'research_status':{'real_world_tested':False,'ranking_uses_commission':False}}
    for statement in ('実際に使って洗浄力を確認しました。', '使ってみると音が静かでした。', '耐久性は未確認ですが、使ってみると音が静かでした。', '音が静かでしたが、耐久性は未確認です。', '音が静かですが耐久性は未確認です。'):
        assert 'research_status.unverified_experience_claim' in validate_experience({**base,'dek':statement},product_refs=frozenset(),evidence_refs=frozenset())
    for statement in ('実際に使ってはいません。', '使ってみたときの洗浄力は未確認です。', '実際に使える時間は条件で変わります。', '実際に使う機器を先に決めます。', '音が静かでしたという評価は未確認です。'):
        assert not validate_experience({**base,'dek':statement},product_refs=frozenset(),evidence_refs=frozenset())


def test_reader_components_preserve_table_sources_and_unknowns() -> None:
    from raos.application.editorial.reader_components import enhance_specification_tables
    root = fragment('<div><div class="comparison-table-wrap"><table><caption>仕様</caption><thead><tr><th scope="col">商品</th><th scope="col">重量</th><th scope="col">方式</th></tr></thead><tbody><tr><th scope="row">A</th><td>UNKNOWN</td><td>同じ方式</td></tr><tr><th scope="row">B</th><td>2kg</td><td>同じ方式</td></tr></tbody></table></div><a id="source-a" href="https://manufacturer.test/manual">確認日2026-09-01の出典</a></div>')
    enhance_specification_tables(root)
    assert len(root.find(cls='raos-common-specifications')) == 1
    assert root.find(tag='td')[0].attrs['data-raos-value-state'] == 'UNKNOWN'
    assert root.find(tag='a')[0].attrs['id'] == 'source-a'
    assert '2026-09-01' in root.text()
    assert 'UNKNOWN' in root.text() and '2kg' in root.text()
    assert len(root.find(tag='table')) == 2


def test_optional_components_and_contextual_links_fail_closed() -> None:
    from raos.application.editorial import reader_components as c
    assert c.decision_axes([]) is None
    assert c.unknowns_panel([]) is None
    assert c.purchase_checklist([]) is None
    assert c.contextual_link('置けるか確かめる', '/missing/', 'learn', existing_targets=frozenset()) is None
    url='https://example.test/verified'
    evidence=CtaEvidence(verified_offers=frozenset({('product',url)}),eligible_products=frozenset({'product'}))
    assert not c.contextual_cta('offer','販売条件を確認',url,product_ref='product',evidence=evidence,article_type='shortlist',placement='after_conclusion')
    assert 'sponsored nofollow' in c.contextual_cta('offer','販売条件を確認',url,product_ref='product',evidence=evidence,article_type='shortlist',placement='product_detail')
    assert not c.contextual_cta('offer','販売条件を確認',url,product_ref='product',evidence=evidence,article_type='status_check',placement='final_check')


def test_decision_rows_support_existing_product_counts_and_escape_copy() -> None:
    from raos.application.editorial.reader_components import decision_table
    for count in (2,4,5,7):
        rows=[{'condition':'省スペースで選ぶ','product_name':'長い型番 <MODEL>&'+str(i),'anchor':f'product-{i}','reason':'給水条件を確認','tradeoff':'UNKNOWN','purchase_check':'メーカー公式で確認する'} for i in range(count)]
        table=decision_table(rows)
        assert table is not None
        assert len(table.find(tag='tbody')[0].find(tag='tr')) == count
        assert '&lt;MODEL&gt;&amp;' in table.html()
        assert len(table.find(tag='a')) == count


def test_price_and_fact_copy_require_source_references() -> None:
    base={'article_type':'shortlist','research_status':{'real_world_tested':False,'ranking_uses_commission':False}}
    assert 'price.checked_date_and_evidence_required' in validate_experience({**base,'dek':'29,800円'},product_refs=frozenset(),evidence_refs=frozenset())
    assert 'products.evidence_must_reference_facts' in validate_experience({**base,'products':[{'product_ref':'a','evidence_facts':['重さは2kgです。']}]},product_refs=frozenset({'a'}),evidence_refs=frozenset({'claim-weight'}))
    assert not validate_experience({**base,'dek':'29,800円','price_snapshot':{'checked_at':'2026-09-01','evidence_ref':'claim-price'}},product_refs=frozenset(),evidence_refs=frozenset({'claim-price'}))


def test_common_specs_do_not_equate_unknowns_or_duplicate_identity_ids() -> None:
    from raos.application.editorial.reader_components import enhance_specification_tables
    root = fragment('<div><div class="comparison-table-wrap"><table><thead><tr><th id="model" scope="col">型番</th><th scope="col">給水</th><th scope="col">設置余白</th></tr></thead><tbody><tr><th scope="row" id="a">A</th><td>タンク式</td><td>UNKNOWN</td></tr><tr><th scope="row" id="b">B</th><td>タンク式</td><td>UNKNOWN</td></tr></tbody></table></div></div>')
    enhance_specification_tables(root)
    assert len(root.find(cls='raos-common-specifications')) == 1
    assert 'UNKNOWN' not in root.find(cls='raos-common-specifications')[0].text()
    ids = [n.attrs['id'] for n in root.walk() if n.attrs.get('id')]
    assert len(ids) == len(set(ids))


def test_reader_taxonomy_has_one_primary_category_and_preserves_empty_groups() -> None:
    from raos.application.editorial.reader_experience_v1 import reader_navigation
    import pytest
    articles = [{'article_id': 'a', 'content_role': 'category_guide'}, {'article_id': 'b', 'content_role': 'lifecycle_status_route'}]
    raw = {'groups': [{'slug': 'kitchen', 'label': 'キッチン・家事', 'description': '置ける条件を測る', 'kind': 'category', 'article_ids': ['a','b']}, {'slug': 'empty', 'label': '未制作', 'description': '記事なし', 'kind': 'purpose', 'article_ids': []}]}
    result = reader_navigation(raw, articles)
    assert result['primary_categories'] == {'a': 'kitchen', 'b': 'kitchen'}
    hubs = {h['slug']:h for h in result['hubs']}
    assert hubs['comparisons']['article_ids'] == ['a']
    assert hubs['empty']['article_ids'] == []
    raw['groups'][0]['article_ids'] = ['a']
    with pytest.raises(ValueError, match='PRIMARY_CATEGORY'):
        reader_navigation(raw, articles)


def test_dimension_diagram_requires_approved_official_facts_and_does_not_invent_clearance() -> None:
    from raos.application.editorial.reader_components import dimension_diagram
    asset = dict(asset_ref='diagram', asset_type='html_diagram', source='https://maker.test/spec', usage_basis='original diagram', checked_at='2026-08-31', approval='approved', alt='body dimensions', caption='本体寸法', aspect_ratio=[42,44], role='dimension')
    source = dict(source_ref='source', url=asset['source'], retrieved_on='2026-08-31', authority='MANUFACTURER_OFFICIAL')
    claim = dict(claim_id='claim', classification='MAJOR_VERIFIABLE', status='BOUND_TO_OFFICIAL_SOURCE', evidence_refs=['source'], dimensions=[dict(subject='EXACT-MODEL本体', width_cm=42, depth_cm=44, height_cm=47)])
    figure = dimension_diagram(claim, source, asset)
    assert figure is not None
    assert '幅 42cm × 奥行 44cm' in figure.text()
    assert '扉開放時の寸法：この記事で確認できた資料では未確認' in figure.text()
    assert '公式情報確認：2026-08-31' in figure.text()
    assert dimension_diagram(claim, source, {**asset,'approval':'pending'}) is None
    assert dimension_diagram({**claim,'classification':'EDITORIAL_INFERENCE'}, source, asset) is None
    assert dimension_diagram(claim, {**source,'retrieved_on':None}, asset) is None
    assert dimension_diagram(claim, {**source,'source_ref':'unbound'}, asset) is None


def test_tracked_product_profiles_retain_identity_and_sources_when_migrated() -> None:
    source = (Path(__file__).resolve().parents[2] / 'changes/wordpress-local-preview-v1/fixtures/articles/roomba-mini-vs-switchbot-k11-pro.html').read_text()
    profile = {'article_type':'comparison','components_enabled':True,'preserve_story':True,'decision_axes':[{'label':'台の設置','why_it_matters':'帰還余白が必要','how_to_check':'説明書を確認'}],'consolidate_sections':['reader-section','editors-note']}
    output = fragment(project_article(source,article_id='roomba-mini-vs-switchbot-k11-pro',experience=profile))
    cards = output.find(cls='raos-product-card')
    assert {card.attrs['data-raos-product-id'] for card in cards} == {'PRD-IROBOT-ROOMBA-MINI-SLIM-F115060','PRD-SWITCHBOT-K11-PRO'}
    assert len(output.find(cls='raos-decision-table')[0].find(tag='tbody')[0].find(tag='tr')) == 2
    assert 'F115060' in output.find(cls='raos-evidence-panel')[0].text()
    assert '2026年8月31日' in output.text()
    assert output.find(cls='raos-reader-meaning')
    assert not any(a.attrs.get('data-raos-cta-type') == 'offer' for a in output.find(tag='a'))


def test_model_differences_derive_like_units_and_preserve_unknowns() -> None:
    from raos.application.editorial.reader_components import numerical_difference
    assert numerical_difference('1056Wh', '1024Wh') == '-32Wh（-3.0%）'
    assert numerical_difference('約12.9kg', '約11.3kg') == '約-1.6kg（-12.4%）'
    assert numerical_difference('1500W', '1550W') == '+50W（+3.3%）'
    for left,right in [('UNKNOWN','10W'),('0W','1W'),('300W','300Wh'),('1〜2kg','2kg')]:
        assert numerical_difference(left,right) is None


def test_all_tracked_articles_keep_products_official_links_and_original_dates() -> None:
    import json
    import re
    from raos.application.editorial.reader_experience_projection import project_registered_article
    root = Path(__file__).resolve().parents[2]
    portfolio = json.loads((root / 'changes/editorial-portfolio-v2/editorial-portfolio.v2.json').read_text())
    for article in portfolio['articles']:
        original = fragment((root / article['content_ref']).read_text())
        rendered = fragment(project_registered_article(root, original.html(), article_id=article['article_id']))
        sources = {a.attrs['href'] for a in original.find(tag='a') if str(a.attrs.get('href', '')).startswith('https://') and 'data-raos-placement' not in a.attrs}
        assert sources <= {a.attrs.get('href') for a in rendered.find(tag='a')}, article['article_id']
        date_pattern = r'\d{4}(?:年\d{1,2}月\d{1,2}日|-\d{2}-\d{2})'
        assert set(re.findall(date_pattern, original.text())) <= set(re.findall(date_pattern, rendered.text()))
        assert {card.attrs['data-raos-product-id'] for card in rendered.find(cls='raos-product-card')} == set(article['product_ids'])
        assert not any(a.attrs.get('data-raos-cta-type') == 'offer' for a in rendered.find(tag='a'))
        assert len(rendered.find(tag='h2')) <= 9
        assert len(rendered.find(cls='raos-evidence-panel')) == 1


def test_core_facts_require_a_dated_official_source_not_only_a_known_claim_id() -> None:
    experience = {'article_type':'shortlist', 'research_status':{'real_world_tested':False,'ranking_uses_commission':False}, 'products':[{'product_ref':'p','evidence_facts':['known-but-undated']}]}
    assert validate_experience(experience, product_refs=frozenset({'p'}), evidence_refs=frozenset({'known-but-undated'}), checked_fact_refs=frozenset()) == ('products.official_checked_facts_required',)


def test_safety_module_requires_evidence_and_retains_final_authority_and_exceptions() -> None:
    from raos.application.editorial.reader_components import safety_rule_panel
    base = {'article_type':'safety_rule','research_status':{'real_world_tested':False,'ranking_uses_commission':False}}
    assert validate_experience(base, product_refs=frozenset(), evidence_refs=frozenset()) == ('rule_status.required',)
    rule = dict(authority='規定主体', final_decision_by='運航者', exceptions='便・機材・運賃で変わる', scope_limit='専門判断を代替しない', evidence_ref='claim', checked_at='2026-08-31', url='https://official.test/rule')
    assert not validate_experience({**base,'rule_status':rule}, product_refs=frozenset(), evidence_refs=frozenset({'claim'}))
    panel = safety_rule_panel(rule)
    assert panel is not None and '2026-08-31' in panel.text() and '運航者' in panel.text()
    assert '便・機材・運賃' in panel.text()
    assert safety_rule_panel({**rule,'checked_at':''}) is None
    assert safety_rule_panel({**rule,'url':'javascript:alert(1)'}) is None


def test_product_photo_needs_usage_approval_as_well_as_image_evidence(tmp_path) -> None:
    import json
    import shutil
    from raos.application.editorial.reader_experience_projection import REGISTRY_PATH, project_registered_article
    root = Path(__file__).resolve().parents[2]
    for relative in (REGISTRY_PATH, Path('changes/editorial-portfolio-v2/editorial-portfolio.v2.json'), Path('changes/editorial-portfolio-v3/editorial-identities.v1.json'), Path('changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json')):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    source = '<div class="raos-editorial-v2"><div class="raos-product-card__media"><img src="/recorded.jpg" data-raos-product-image-id="fixture-product" data-raos-product-image-placement="product_card" alt="old"></div><p>UNKNOWN</p></div>'
    def render(markup=source):
        return project_registered_article(tmp_path, markup, article_id='legacy-fixture', approved_product_images=frozenset({'fixture-product'}))
    assert not fragment(render()).find(tag='img')
    registry = json.loads((tmp_path / REGISTRY_PATH).read_text())
    registry['media'].append(dict(asset_ref='fixture-product', asset_type='photo', source='https://official.test/photo', usage_basis='recorded fixture permission', checked_at='2026-08-31', approval='approved', alt='許可された商品識別画像', caption='画像出典と利用根拠の注記', aspect_ratio=[1,1], role='product_identity'))
    (tmp_path / REGISTRY_PATH).write_text(json.dumps(registry))
    result = fragment(render())
    assert result.find(tag='img')[0].attrs['alt'] == '許可された商品識別画像'
    assert '画像出典と利用根拠の注記' in result.text()
    assert render(result.html()) == result.html()
    registry['media'][-1]['approval'] = 'pending'
    (tmp_path / REGISTRY_PATH).write_text(json.dumps(registry))
    assert not fragment(render()).find(cls='raos-product-card__media')
