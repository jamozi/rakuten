"""KS-117 (2026-09-15 batch 3): offer notes name the price states the runtime shows.

After the display deadline the theme runtime shows 「販売条件の表示期限切れ。」 in a
seller panel and 「価格は販売先で確認」 in a reference-price cell. 「販売条件を再確認中。」
is the state for an unverified identity/stock/condition, not for expiry.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raos.application.editorial.reader_html import fragment
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_JS = (
    ROOT
    / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/purchase-support.js"
)
EXPIRED = "販売条件の表示期限切れ"
SELLER = "価格は販売先で確認"


@pytest.fixture(scope="module")
def bodies():
    return {
        path.stem: text
        for path, text in builder.build().items()
        if path.suffix == ".html"
    }


def test_offer_panel_lead_names_the_expired_and_seller_states(bodies):
    js = RUNTIME_JS.read_text(encoding="utf-8")
    assert f"'EXPIRED' ? '{EXPIRED}。'" in js
    assert f"text: '{SELLER}'" in js
    leads = {
        slug: next(p.text() for p in node.find(tag="p") if "価格の表示期限" in p.text())
        for slug, body in bodies.items()
        for node in fragment(body).walk()
        if node.tag == "section" and node.attrs.get("id") == "ps-offers"
    }
    assert leads
    for slug, lead in leads.items():
        assert "再確認中と示します" not in lead, slug
        assert f"期限後は価格を表示せず、「{EXPIRED}」または「{SELLER}」と示します。" in lead, slug


def test_offer_notes_do_not_name_a_single_recheck_state(bodies):
    """Template-dependent: compact-robot-vacuum-shortlist carries an authored copy of the note."""
    assert sorted(slug for slug, body in bodies.items() if "再確認中と示します" in body) == []


# --- Template/policy parts (test_tpl_*): policy wording matches renderer, runtime JS and analytics code.
import re  # noqa: E402

from raos.application.editorial.reader_html import Element  # noqa: E402

ANALYTICS_JS = RUNTIME_JS.with_name("purchase-analytics.js")
# Each policy page carries the date of the revision it was last published with;
# next30 Wave 0 (2026-09-16) revises the operating policy only.
POLICY_REVISED_ON = {
    "about-ad-policy": "2026-09-16",
    "comparison-policy": "2026-09-15",
    "privacy-policy": "2026-09-15",
}
POLICY_SLUGS = tuple(POLICY_REVISED_ON)
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})
DISCLOSURE = re.compile(
    r'<(?:p|aside)\b[^>]*class="[^"]*\b(?:ps-disclosure|ks-reader-ad-note|sc-ad|raos-disclosure)\b'
)


@pytest.fixture(scope="module")
def outputs(bodies) -> dict[str, str]:
    return bodies


@pytest.fixture(scope="module")
def roots(outputs: dict[str, str]) -> dict[str, Element]:
    return {slug: fragment(body) for slug, body in outputs.items()}


def visible_text(node: Element) -> str:
    parts: list[str] = []

    def collect(element: Element) -> None:
        if element.tag in SKIPPED_TAGS:
            return
        for child in element.children:
            if isinstance(child, Element):
                collect(child)
            elif not child.startswith("<!--"):
                parts.append(child)

    collect(node)
    return re.sub(r"\s+", " ", "".join(parts))


def by_id(root: Element, element_id: str) -> list[Element]:
    return [n for n in root.walk() if n.attrs.get("id") == element_id]


def labelled_section(root: Element, heading_id: str) -> Element:
    sections = [
        n for n in root.find(tag="section") if n.attrs.get("aria-labelledby") == heading_id
    ]
    assert len(sections) == 1, heading_id
    return sections[0]


def sentences(text: str) -> list[str]:
    """Split on 。 outside 「」 so quoted status strings stay inside their sentence."""
    out, depth, current = [], 0, ""
    for char in text:
        current += char
        if char == "「":
            depth += 1
        elif char == "」":
            depth = max(0, depth - 1)
        elif char == "。" and depth == 0:
            out.append(current.strip())
            current = ""
    if current.strip():
        out.append(current.strip())
    return out


def price_state_sentences(roots) -> list[str]:
    about = visible_text(labelled_section(roots["about-ad-policy"], "production-about-editors"))
    cost = visible_text(labelled_section(roots["comparison-policy"], "purchase-cost-policy"))
    return [s for s in sentences(about) + sentences(cost) if "販売条件" in s or SELLER in s]


def test_tpl_policy_does_not_promise_a_visible_deadline_after_expiry(roots) -> None:
    """KS-117: after expiry only the check time remains; the deadline itself is not shown."""
    cost = visible_text(labelled_section(roots["comparison-policy"], "purchase-cost-policy"))
    assert "確認日時と期限を示" not in cost
    # The display deadline applies to the seller column and the reference price column.
    assert "販売先ごとの欄" in cost and "参考価格の欄" in cost


def test_tpl_policies_tie_each_price_state_to_its_runtime_condition(roots) -> None:
    """KS-117: 再確認中 is the identity/state gap, 期限切れ is expiry (purchase-support.js offerCost)."""
    runtime = RUNTIME_JS.read_text(encoding="utf-8")
    assert f"{EXPIRED}。" in runtime and "販売条件を再確認中。" in runtime
    assert f"text: '{SELLER}'" in runtime
    found = price_state_sentences(roots)
    assert found
    for sentence in found:
        for quoted in re.findall(r"「([^」]+)」", sentence):
            if quoted.startswith("販売条件") or quoted.startswith("価格は販売先"):
                assert quoted.rstrip("。") in runtime, quoted
        if "販売条件を再確認中" in sentence:
            assert "期限後" not in sentence, sentence
            assert "型番" in sentence, sentence
    joined = "".join(found)
    assert EXPIRED in joined and SELLER in joined


def test_tpl_offer_notes_do_not_name_a_single_recheck_state(roots) -> None:
    """KS-117: the authored notes in 30 do not collapse expiry into 再確認中."""
    assert "再確認中と示します" not in visible_text(roots["compact-robot-vacuum-shortlist"])


def test_tpl_about_policy_ad_notice_precedes_comparison_and_purchase_links(roots, outputs) -> None:
    """KS-118/126 (A1): the notice is placed before the product comparison and purchase links."""
    advertising = visible_text(labelled_section(roots["about-ad-policy"], "production-about-advertising"))
    assert "冒頭に「" not in advertising
    assert "商品比較・購入リンクより前に" in advertising
    checked = 0
    for slug, body in outputs.items():
        purchase = [m.start() for m in re.finditer(r'hb\.afl\.rakuten\.co\.jp|data-raos-cta-type="offer"', body)]
        if not purchase:
            continue
        rows = [m.start() for m in re.finditer(r"<tr\b[^>]*data-product-id=", body)]
        notices = [m.start() for m in DISCLOSURE.finditer(body)]
        assert notices, slug
        assert notices[0] < min(purchase + rows), slug
        checked += 1
    assert checked >= 15


def test_tpl_about_policy_rws_paragraph_keeps_availability_and_dates(roots, outputs) -> None:
    """KS-118 (Q7): only the site's own last sentence changes; 販売可能情報 stays."""
    paragraphs = by_id(roots["about-ad-policy"], "production-about-rakuten-price")
    assert len(paragraphs) == 1
    text = visible_text(paragraphs[0])
    assert "価格、販売可能情報は、変更される場合があります。" in text
    assert "購入時に楽天市場店舗（www.rakuten.co.jp）に表示されている価格が、その商品の販売に適用されます。" in text
    assert "価格・販売状況の確認日時を表示" not in text
    # Decision 5: the site's own sentence covers only the seller and reference price
    # cells — and only for the products whose seller conditions were recorded. The
    # 17 next30 products have no approved offer, so the dated promise is conditional
    # and the products without one are named in the sentence that follows it.
    assert sentences(text)[-2].startswith(
        "販売条件を記録した商品では、販売先ごとの欄と参考価格の欄に確認日時を併記し、"
        "確認から24時間または販売先の期限を過ぎた価格は表示しません"
    )
    assert sentences(text)[-1].startswith("照合できた販売先がない商品は、参考価格の欄に")
    # Every static seller-status line keeps a dated line beside it.
    for slug, body in outputs.items():
        assert body.count('class="ps-price-status"') <= body.count('class="ps-price-date"'), slug


def test_tpl_privacy_names_every_offer_click_parameter(roots) -> None:
    """KS-119: the policy lists what purchase-analytics.js sends, and only after consent."""
    code = ANALYTICS_JS.read_text(encoding="utf-8")
    keys = re.search(r"const keys = \[([^\]]+)\]", code)
    assert keys
    names = re.findall(r"'([a-z_]+)'", keys.group(1))
    assert len(names) == 7
    assert "window.gtag('event', 'offer_click'" in code
    assert "params.link_purpose = " in code and "params.affiliate = " in code
    assert "consent.categories.analytics !== true" in code
    assert "window.wp_has_consent('statistics') !== true" in code
    section = visible_text(labelled_section(roots["privacy-policy"], "production-privacy-measurement"))
    statement = [s for s in sentences(section) if "offer_click" in s]
    assert len(statement) == 1, section
    for name in names:
        assert name in statement[0], name
    # Decision 8: the classification fields and the debug flag are sent as well.
    assert "debug_mode: config.debug_mode" in code
    for name in ("link_purpose", "affiliate", "debug_mode"):
        assert name in statement[0], name
    assert "広告リンク" in statement[0]
    assert "同意" in statement[0]


def test_tpl_privacy_rights_heading_leads_its_section(roots) -> None:
    """KS-119: the rights heading opens its section."""
    section = labelled_section(roots["privacy-policy"], "production-privacy-rights")
    first = next(c for c in section.children if isinstance(c, Element))
    assert first.tag == "h2" and first.attrs.get("id") == "production-privacy-rights"


@pytest.mark.parametrize("slug", POLICY_SLUGS)
def test_tpl_policy_pages_carry_this_revision_date(roots, slug: str) -> None:
    """KS-117 (Q9): the last-updated date moves with the published revision."""
    assert visible_text(roots[slug]).count("最終更新日") == 1
    times = [t for t in roots[slug].find(tag="time") if "最終更新日" in visible_text(t.parent)]
    assert [t.attrs.get("datetime") for t in times] == [POLICY_REVISED_ON[slug]]


def test_tpl_comparison_policy_links_the_pre_publication_check(roots) -> None:
    """KS-117 work 3: the comparison policy links the pre-publication check it relies on."""
    links = [a.attrs.get("href") for a in roots["comparison-policy"].find(tag="a")]
    assert "/about-ad-policy/#production-about-editors" in links
    target = labelled_section(roots["about-ad-policy"], "production-about-editors")
    assert "公開前の点検" in visible_text(target)
    assert len(by_id(roots["about-ad-policy"], "production-about-editors")) == 1


# --- Amended decisions 5 and 8 (2026-09-15 night) ---
UNRECORDED = "価格は確認中"
RENDERER = ROOT / "python/raos/application/editorial/purchase_support.py"
GATE_JS = RUNTIME_JS.with_name("analytics-consent-gate.js")


def test_tpl_policies_name_every_price_text_the_pages_show(roots) -> None:
    """Decision 5: the unmatched-seller cell and non-available offers are named too."""
    renderer = RENDERER.read_text(encoding="utf-8")
    runtime = RUNTIME_JS.read_text(encoding="utf-8")
    assert f'role="status">{UNRECORDED}</p>' in renderer
    assert "offer.state !== 'AVAILABLE'" in runtime
    about = visible_text(labelled_section(roots["about-ad-policy"], "production-about-editors"))
    cost = visible_text(labelled_section(roots["comparison-policy"], "purchase-cost-policy"))
    for text in (about, cost):
        for quoted in (f"{EXPIRED}。", "販売条件を再確認中。", SELLER, UNRECORDED):
            assert f"「{quoted}」" in text, quoted
        recheck = [s for s in sentences(text) if "販売条件を再確認中" in s]
        assert len(recheck) == 1 and "販売中" in recheck[0] and "売り切れ" in recheck[0], recheck
        unrecorded = [s for s in sentences(text) if UNRECORDED in s]
        assert len(unrecorded) == 1 and "照合できた販売先がない" in unrecorded[0], unrecorded


def test_tpl_privacy_limits_query_removal_to_the_purchase_profile(roots) -> None:
    """Decision 8: analytics-consent-gate.js removes the query only under the purchase profile."""
    gate = GATE_JS.read_text(encoding="utf-8")
    assert (
        "...(configuration.purchaseProfile ? {\n"
        "        page_location: window.location.origin + window.location.pathname,\n"
        "        page_referrer: '',"
    ) in gate
    section = visible_text(labelled_section(roots["privacy-policy"], "production-privacy-measurement"))
    removal = [s for s in sentences(section) if "記事URLのクエリー" in s]
    assert len(removal) == 1 and removal[0].startswith("購入先リンクの計測設定を読み込むページ"), removal
    assert any(s.startswith("それ以外のページでは") and "クエリー" in s for s in sentences(section))
    assert "外部リンクのクエリー" not in section
