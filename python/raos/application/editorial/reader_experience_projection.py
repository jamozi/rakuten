"""Project tracked editorial inputs into a reusable, non-publishing reader view."""

from __future__ import annotations

from collections.abc import Mapping
from html import escape
import json
import re
from pathlib import Path
from typing import Any, cast

from raos.application.editorial.reader_experience_v1 import CheckedFact, CtaEvidence, ROLE_TYPES, cta_visible, validate_experience


from raos.application.editorial.reader_html import Element, block, fragment
from raos.application.editorial import reader_components as components

REGISTRY_PATH = Path("changes/editorial-portfolio-v3/reader-experience.v1.json")


def load_experiences(root: Path) -> dict[str, object]:
    path = root / REGISTRY_PATH
    if not path.exists():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "RAOS_READER_EXPERIENCE_V1" or not isinstance(value.get("articles"), dict):
        raise ValueError("READER_EXPERIENCE_REGISTRY_INVALID")
    portfolio = json.loads((root / "changes/editorial-portfolio-v2/editorial-portfolio.v2.json").read_text())
    identities = json.loads((root / "changes/editorial-portfolio-v3/editorial-identities.v1.json").read_text())
    sources = json.loads((root / "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json").read_text())
    bindings = {row["article_id"]: row for row in portfolio["articles"]}
    roles = {row["article_id"]: ROLE_TYPES[row["content_role"]] for row in identities["articles"]}
    for article_id, experience in value["articles"].items():
        if article_id not in bindings or not isinstance(experience, dict):
            raise ValueError("READER_EXPERIENCE_UNKNOWN_ARTICLE")
        if experience.get("article_type") != roles[article_id]:
            raise ValueError("READER_EXPERIENCE_INTENT_MISMATCH:" + article_id)
        references = frozenset(
            claim["claim_id"] for packet in sources["source_packets"] if packet["article_id"] == article_id
            for claim in packet["claims"]
        )
        checked_refs = frozenset(
            claim['claim_id'] for packet in sources['source_packets'] if packet['article_id'] == article_id
            for claim in packet['claims']
            if claim['classification'] == 'MAJOR_VERIFIABLE' and claim['status'] == 'BOUND_TO_OFFICIAL_SOURCE'
            and any(source['source_ref'] in claim['evidence_refs']
                    and source.get('authority') in {'MANUFACTURER_OFFICIAL', 'CARRIER_OFFICIAL', 'GOVERNMENT_OFFICIAL'}
                    and CheckedFact(claim['claim_id'], source['source_ref'], source.get('retrieved_on'), 'KNOWN').usable
                    for source in sources['sources'])
        )
        issues = validate_experience(experience, product_refs=frozenset(bindings[article_id]["product_ids"]), evidence_refs=references, checked_fact_refs=checked_refs)
        if issues:
            raise ValueError("READER_EXPERIENCE_INVALID:" + article_id + ":" + ",".join(issues))
    return cast(dict[str, object], value["articles"])


def _clean_media_and_actions(root: Element, evidence: CtaEvidence, article_type: str, images: frozenset[str]) -> None:
    for node in list(root.walk()):
        if node.has("hero-photo") or node.has("raos-first-article-lead-image"):
            node.remove()
        if node.attrs.get("data-raos-product-image-id") not in images and (
            "data-raos-product-image-id" in node.attrs or node.has("raos-product-image-status")
        ):
            node.remove()
        if node.has("raos-product-card__media") and not node.find(tag="img"):
            node.remove()
        if node.tag == "a" and "data-raos-placement" in node.attrs:
            product = node.attrs.get("data-raos-product-id")
            url = node.attrs.get("href") or ""
            if not cta_visible("offer", url, product, evidence, article_type="status_check" if article_type == "status_check" else "shortlist"):
                wrapper = node.parent
                action = None
                while wrapper is not None and wrapper.tag not in {"article", "section"}:
                    if wrapper.has("raos-product-card__actions"):
                        action = wrapper
                        break
                    if any(wrapper.has(c) for c in ("summary-action", "final-summary-action", "product-purchase-action")):
                        action = wrapper
                    wrapper = wrapper.parent
                (action if action is not None else node).remove()
            else:
                node.attrs["data-raos-cta-type"] = "offer"
                node.children = ["型番・同梱品・保証・現在の販売条件を確認する"]
    for node in list(root.walk()):
        if node.has("raos-product-card__media") and not node.find(tag="img"):
            node.remove()


def _paragraphs(root: Element) -> None:
    for node in list(root.walk()):
        if node.tag == "br":
            if node.parent is not None:
                position = node.parent.children.index(node)
                node.parent.children[position] = " "


def _normalize_product_profiles(root: Element) -> None:
    """Adapt the later tracked HTML drafts without replacing their editing source."""
    for card in root.find(cls='product-profile'):
        if not card.has('raos-product-card'):
            card.attrs['class'] = (card.attrs.get('class') or '') + ' raos-product-card'
        body = next(iter(card.find(cls='product-profile__body')), card)
        for paragraph in list(body.children):
            if (isinstance(paragraph, Element) and paragraph.tag == 'p'
                and re.search(r'\d', paragraph.text()) and not paragraph.has('raos-source-link')
                and not paragraph.has('section-number')):
                paragraph.attrs['class'] = (paragraph.attrs.get('class') or '') + ' raos-product-card__facts'


def _research(root: Element, article: Element, article_id: str) -> None:
    facts = root.find(cls="raos-article-facts")
    if len(facts) != 1:
        return
    fact = facts[0]
    pairs = {
        node.find(tag="dt")[0].text(): node.find(tag="dd")[0].text()
        for node in fact.children if isinstance(node, Element) and node.find(tag="dt") and node.find(tag="dd")
    }
    checked = pairs.get("最終確認日", "確認日未確認")
    real_world = pairs.get("実機確認", "未確認")
    affiliate = any(n.attrs.get("data-raos-cta-type") == "offer" for n in root.walk())
    label = "広告リンクを含みます" if affiliate else "この記事の販売リンクは掲載していません"
    status = block(f'<p class="raos-research-status" data-raos-article-id="{escape(article_id, quote=True)}"><span>公式情報確認：{escape(checked)} ／ 実機確認：{escape(real_world)}</span><span>{label}。<a href="#reader-evidence">出典・調査範囲</a></span></p>')
    article.children.insert(0, status)
    status.parent = article
    panel = block('<details class="raos-evidence-panel" id="reader-evidence" tabindex="-1"><summary>調査範囲・型番・確認日を詳しく見る</summary></details>')
    panel.append(fact)
    for disclosure in list(article.find(cls="raos-disclosure")):
        panel.append(disclosure)
    article.append(panel)


def _summary(root: Element, settings: Mapping[str, object]) -> None:
    sections = root.find(cls="raos-decision-summary") or root.find(cls="decision-section")
    if not sections:
        return
    section = sections[0]
    if settings.get("article_type") == "status_check":
        headings = section.find(tag="h2")
        if headings:
            headings[0].children = ["30秒で分かる、確認結果と次の行動"]
        return
    headings = section.find(tag="h2")
    if headings:
        headings[0].children = ["30秒で分かる、条件ごとの候補"]
    summary = settings.get("decision_summary")
    if not isinstance(summary, Mapping):
        return
    options = summary.get("options")
    items = section.find(tag="li")
    if isinstance(options, list):
        by_product = {option["product_ref"]: option for option in options if isinstance(option, Mapping)}
        targets = {"#" + str(card.attrs.get("id")): card.attrs.get("data-raos-product-id") for card in root.find(cls="raos-product-card")}
        for item in items:
            product = next((targets.get(link.attrs.get("href") or "") for link in item.find(tag="a") if link.attrs.get("href") in targets), None)
            option = by_product.get(product)
            if option is None:
                continue
            paragraphs = item.find(tag="p")
            if paragraphs:
                paragraphs[0].children = [escape(str(option["reason"]))]
                paragraphs[0].append(block(f'<span class="raos-summary-tradeoff"><strong>妥協点：</strong>{escape(str(option["tradeoff"]))}</span>'))
    difference = summary.get("key_difference")
    if isinstance(difference, str) and difference:
        section.append(block(f'<p class="raos-key-difference"><strong>最大の違い：</strong>{escape(difference)}</p>'))
    exclusion = summary.get("no_purchase_condition")
    if isinstance(exclusion, str) and exclusion:
        section.append(block(f'<p class="raos-no-purchase"><strong>購入を見送る条件：</strong>{escape(exclusion)}</p>'))


def project_article(
    markup: str, *, article_id: str, experience: Mapping[str, object] | None = None,
    evidence: CtaEvidence = CtaEvidence(), approved_product_images: frozenset[str] = frozenset(),
) -> str:
    """One projection for local and candidate HTML; URLs and claims stay intact."""
    root = fragment(markup)
    articles = root.find(cls="raos-editorial-v2")
    if len(articles) != 1:
        raise ValueError("READER_VIEW_ROOT_INVALID")
    article = articles[0]
    settings = experience or {}
    _clean_media_and_actions(root, evidence, str(settings.get("article_type", "shortlist")), approved_product_images)
    _paragraphs(root)
    for wrapper in root.find(cls="comparison-table-wrap"):
        wrapper.attrs["tabindex"] = "0"
        wrapper.attrs["role"] = "region"
        if "aria-labelledby" not in wrapper.attrs:
            wrapper.attrs["aria-label"] = "商品別の仕様表。左右にスクロールできます"
    markers = root.find(cls="raos-reader-view")
    if markers:
        markers[0].attrs["data-raos-article-id"] = article_id
        return root.html()
    if settings:
        _normalize_product_profiles(root)
        _research(root, article, article_id)
        _summary(root, settings)
        if settings.get("components_enabled") is True:
            _decision_components(root, article, settings)
    marker = block(f'<span class="raos-reader-view" data-raos-article-id="{escape(article_id, quote=True)}" hidden></span>')
    if settings.get("components_enabled") is True:
        marker.attrs["data-raos-reader-components"] = "true"
    article.children.insert(0, marker)
    marker.parent = article
    return root.html()


def _decision_components(root: Element, article: Element, settings: Mapping[str, object]) -> None:
    summary = next(iter(root.find(cls="decision-section")), None)
    insertion = summary
    rule = settings.get('_resolved_rule_status')
    if settings.get('article_type') == 'safety_rule' and isinstance(rule, dict):
        rule_panel = components.safety_rule_panel(rule)
        if rule_panel is not None:
            summary.insert_before(rule_panel) if summary is not None else article.append(rule_panel)
    axes = settings.get("decision_axes", [])
    if isinstance(axes, list):
        axis_block = components.decision_axes(axes)
        if axis_block is not None:
            if insertion is not None and insertion.parent is not None:
                parent = insertion.parent
                axis_block.parent = parent
                parent.children.insert(parent.children.index(insertion) + 1, axis_block)
            else:
                article.append(axis_block)
            insertion = axis_block
            notes = settings.get('practical_notes', [])
            if isinstance(notes, list) and notes:
                note = block('<div class="raos-practical-notes"><h3>暮らしで確かめること</h3></div>')
                for paragraph in notes:
                    if isinstance(paragraph, str):
                        note.append(block('<p>' + escape(paragraph) + '</p>'))
                axis_block.append(note)
    # The decision table resolves identity, fit, and caution from existing cards.
    cards = root.find(cls="raos-product-card")
    product_entries = settings.get('products', [])
    product_settings = {p['product_ref']: p for p in product_entries} if isinstance(product_entries, list) else {}
    summary_reasons = {}
    if summary is not None:
        for item in summary.find(tag='li'):
            paragraphs = item.find(tag='p')
            if not paragraphs:
                continue
            copy = block(paragraphs[0].html())
            for tradeoff in copy.find(cls='raos-summary-tradeoff'):
                tradeoff.remove()
            for link in item.find(tag='a'):
                if str(link.attrs.get('href', '')).startswith('#'):
                    summary_reasons[link.attrs['href']] = copy.text()
    rows = []
    for card in cards:
        headings = card.find(tag="h3")
        labels = card.find(cls="raos-condition-label")
        fit = card.find(cls="raos-product-card__fit")
        caution = card.find(cls="raos-product-card__caution")
        if not headings or not card.attrs.get("id"):
            continue
        fit_lists = fit[0].find(tag="ul") if fit else []
        fit_items = fit_lists[0].find(tag="li") if fit_lists else []
        exclusions = fit_lists[1].find(tag="li") if len(fit_lists) > 1 else []
        pairs = {pair.find(tag='dt')[0].text(): pair.find(tag='dd')[0].text() for dl in card.find(tag='dl') for pair in dl.children if isinstance(pair, Element) and pair.find(tag='dt') and pair.find(tag='dd')}
        product = product_settings.get(card.attrs.get('data-raos-product-id'), {})
        not_for = product.get('not_for', [])
        if not_for and not pairs.get('別の候補が向く条件') and not exclusions:
            card.append(block('<p class="raos-product-card__caution"><strong>向かない条件：</strong>' + escape('。'.join(not_for)) + '</p>'))
        rows.append({
            "condition": labels[0].text() if labels else (fit_items[0].text() if fit_items else pairs.get('向く条件', "条件を確認して候補にする")),
            "product_name": headings[0].text(), "anchor": str(card.attrs["id"]),
            "reason": summary_reasons.get('#' + str(card.attrs['id']), fit_items[0].text() if fit_items else pairs.get('向く条件', "商品の選択条件を確認してください。")),
            "tradeoff": exclusions[0].text() if exclusions else pairs.get('別の候補が向く条件', not_for[0] if not_for else (caution[0].text() if caution else "未確認")),
            "purchase_check": caution[0].text() if caution else pairs.get('購入前の確認', "型番・同梱品・保証・販売元を確認してください。"),
        })
    if summary is not None:
        by_anchor = {'#' + row['anchor']: row for row in rows}
        for item in summary.find(tag='li'):
            choice = next((by_anchor[str(a.attrs['href'])] for a in item.find(tag='a') if a.attrs.get('href') in by_anchor), None)
            paragraphs = item.find(tag='p')
            if choice is not None and paragraphs and not item.find(cls='raos-summary-tradeoff'):
                paragraphs[0].append(block('<span class="raos-summary-tradeoff"><strong>妥協点：</strong>' + escape(choice['tradeoff']) + '</span>'))
    if settings.get("article_type") != "status_check":
        table = components.decision_table(rows)
        if table is not None and insertion is not None and insertion.parent is not None:
            table.parent = insertion.parent
            table.parent.children.insert(table.parent.children.index(insertion) + 1, table)
    evidence = next(iter(root.find(cls="raos-evidence-panel")), None)
    if evidence is not None:
        for lead in root.find(cls='lead-section'):
            for heading in lead.find(tag='h2'):
                heading.tag = 'p'
                heading.attrs['class'] = 'raos-reader-lead-heading'
            for copy in lead.find(cls='lead-copy'):
                for extra in copy.find(tag='p')[2:]:
                    evidence.append(extra)
        for redundant in root.find(cls="raos-decision-summary")[1:]:
            redundant.attrs["class"] = "raos-evidence-decision-basis"
            for heading in redundant.find(tag="h2"):
                heading.tag = "h3"
            evidence.append(redundant)
        for intro in root.find(cls="raos-article-intro"):
            for extra in intro.find(tag="p")[2:]:
                evidence.append(extra)
        for node in list(root.find(cls="disclosure")) + list(root.find(cls="raos-article-scope")):
            ancestor = node.parent
            while ancestor is not None and ancestor is not evidence:
                ancestor = ancestor.parent
            if ancestor is None:
                evidence.append(node)
        for index, card in enumerate(cards, start=1):
            facts = card.find(cls="raos-product-card__facts")
            if not facts:
                continue
            anchor = f"reader-product-evidence-{index}"
            panel = block(f'<div id="{anchor}" class="raos-product-evidence" role="region" aria-labelledby="{anchor}-title" tabindex="-1"><h3 id="{anchor}-title">{escape(card.find(tag="h3")[0].text())}：確認した根拠</h3></div>')
            for fact in facts:
                panel.append(fact)
            evidence.append(panel)
            card.append(block(f'<p><a href="#{anchor}">型番と仕様の根拠を見る</a></p>'))
        # Preserve source headings/IDs, methods, and update history at the end.
        additional = settings.get("consolidate_sections", [])
        consolidation = ("sources-section", "method-section", *(additional if isinstance(additional, list) else []))
        story = block('<section class="raos-reader-meaning" aria-labelledby="reader-meaning"><h2 id="reader-meaning">暮らしの場面に置き換えて考える</h2></section>')
        for child in list(article.children):
            if isinstance(child, Element) and child is not evidence and any(child.has(cls) for cls in consolidation):
                for heading in child.find(tag="h2"):
                    heading.tag = "h3"
                if settings.get('preserve_story') is True and (child.has('reader-section') or child.has('method-section')) and not child.has('raos-market-exclusions'):
                    story.append(child)
                else:
                    evidence.append(child)
        if story.find(tag='h3'):
            products = root.find(cls='products-section')
            if products:
                products[0].insert_before(story)
            else:
                evidence.insert_before(story)
    unknowns = settings.get("unknowns", [])
    if isinstance(unknowns, list):
        unknown_panel = components.unknowns_panel(unknowns)
        if unknown_panel is not None:
            evidence.insert_before(unknown_panel) if evidence is not None else article.append(unknown_panel)
    checks = settings.get("purchase_checks", [])
    if isinstance(checks, list):
        checklist = components.purchase_checklist(checks)
        if checklist is not None:
            evidence.insert_before(checklist) if evidence is not None else article.append(checklist)
    final_offers = block('<div class="raos-final-offers"></div>')
    for link in list(root.find(tag="a")):
        if link.attrs.get("data-raos-cta-type") == "offer" and link.attrs.get("data-raos-placement") == "final_summary":
            product = link.attrs.get("data-raos-product-id")
            offer_card = next((card for card in cards if card.attrs.get("data-raos-product-id") == product), None)
            if offer_card is not None and offer_card.find(tag="h3"):
                link.children = [escape(offer_card.find(tag="h3")[0].text() + "：型番・同梱品・保証・現在の販売条件を確認する")]
            final_offers.append(link)
    if final_offers.children:
        evidence.insert_before(final_offers) if evidence is not None else article.append(final_offers)
    components.enhance_specification_tables(root)
    differences = settings.get('_resolved_differences', [])
    if isinstance(differences, list) and differences:
        label = str(settings.get('difference_label', '公表値の差を、用途へ置き換える'))
        difference_rows_html = ''.join('<tr><th scope="row">' + escape(r['label']) + '</th><td>' + escape(r['delta']) + '</td><td>' + escape(r['meaning']) + '</td></tr>' for r in differences)
        difference = components.section('reader-model-difference', label, '<p>差は公表値から計算しています。実使用の時間や適合を示す実測値ではありません。</p><div class="comparison-table-wrap" tabindex="0" role="region" aria-label="世代差と用途の表"><table><caption>' + escape(label) + '</caption><thead><tr><th scope="col">項目</th><th scope="col">公表値の差</th><th scope="col">用途で見る意味</th></tr></thead><tbody>' + difference_rows_html + '</tbody></table></div>', 'raos-reader-model-difference')
        specifications = root.find(cls='comparison-section')
        if specifications:
            specifications[0].insert_before(difference)
    media = settings.get('_resolved_dimensions', [])
    if isinstance(media, list):
        diagrams = block('<section class="raos-reader-dimensions" aria-labelledby="reader-dimensions"><h2 id="reader-dimensions">本体と、扉を開く空間を分けて測る</h2></section>')
        for row in media:
            figure = components.dimension_diagram(row['claim'], row['source'], row['asset'])
            if figure is not None:
                diagrams.append(figure)
        if diagrams.find(tag='figure'):
            specifications = root.find(cls='comparison-section')
            if specifications:
                specifications[0].insert_before(diagrams)
    links = settings.get('_resolved_contextual_links', [])
    if isinstance(links, list):
        for link in links:
            related_node = components.contextual_link(link['question'], link['url'], link['journey_stage'], existing_targets=frozenset(item['url'] for item in links))
            if related_node is not None:
                targets = root.find(cls='raos-decision-axes' if link.get('placement') == 'axes' else 'raos-reader-purchase-checklist')
                if targets:
                    targets[0].append(related_node)
    if summary is not None and summary.parent is not None:
        summary.parent.children.insert(summary.parent.children.index(summary) + 1, '<!-- raos-reader-toc -->')


def project_registered_article(root: Path, markup: str, *, article_id: str, evidence: CtaEvidence = CtaEvidence(), approved_product_images: frozenset[str] = frozenset()) -> str:
    experience = load_experiences(root).get(article_id)
    if isinstance(experience, dict):
        experience = dict(experience)
        portfolio = json.loads((root / 'changes/editorial-portfolio-v2/editorial-portfolio.v2.json').read_text())
        routes = {a['article_id']: '/' + a['production_slug'] + '/' for a in portfolio['articles']}
        experience['_resolved_contextual_links'] = [{**link, 'url': routes[link['target_ref']]} for link in experience.get('contextual_links', []) if link['target_ref'] in routes and link['target_ref'] != article_id]
        sources = json.loads((root / 'changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json').read_text())
        claims = {c['claim_id']: c for p in sources['source_packets'] if p['article_id'] == article_id for c in p['claims']}
        source_refs = {s['source_ref']: s for s in sources['sources']}
        rule = experience.get('rule_status')
        if isinstance(rule, dict):
            claim = claims.get(rule.get('evidence_ref'), {})
            source = next((source_refs[ref] for ref in claim.get('evidence_refs', []) if ref in source_refs), None)
            if source is not None:
                experience['_resolved_rule_status'] = {**rule, 'checked_at': source.get('retrieved_on'), 'url': source['url']}
        registry = json.loads((root / REGISTRY_PATH).read_text())
        assets = {a['asset_ref']: a for a in registry.get('media', [])}
        resolved = []
        for media in experience.get('media', []):
            asset, claim = assets.get(media['asset_ref']), claims.get(media.get('evidence_ref'))
            if asset is not None and claim is not None:
                source = next((source_refs.get(ref) for ref in claim['evidence_refs'] if source_refs.get(ref, {}).get('url') == asset.get('source')), None)
                if source is not None:
                    resolved.append(dict(asset=asset, claim=claim, source=source))
        experience['_resolved_dimensions'] = resolved
        difference = experience.get('difference_pair')
        if isinstance(difference, dict):
            inputs = json.loads((root / 'changes/st-1704/self-hosted-editorial-pilot-v1/content/articles.v1.json').read_text())
            model: dict[str, Any] = next((a['render_model'] for a in inputs['articles'] if a['article_id'] == article_id), {})
            product_facts = {c['product_id']: {f['label']: f['value'] for f in c['confirmed_facts']} for c in model.get('product_cards', [])}
            left, right = product_facts.get(difference.get('baseline_product_ref'), {}), product_facts.get(difference.get('product_ref'), {})
            rows = []
            for label, meaning in difference.get('meaning_by_label', {}).items():
                delta = components.numerical_difference(left.get(label, ''), right.get(label, ''))
                if delta is not None:
                    rows.append(dict(label=label, meaning=meaning, delta=delta))
            experience['_resolved_differences'] = rows
    return project_article(markup, article_id=article_id, experience=experience if isinstance(experience, dict) else None, evidence=evidence, approved_product_images=approved_product_images)
