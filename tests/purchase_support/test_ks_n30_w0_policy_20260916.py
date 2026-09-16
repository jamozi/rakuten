"""next30 Wave 0 (2026-09-16): the policy page's own claims survive the 25 new articles.

Wave 0 publishes no article. It makes the site's statements true before the
programme starts: 「扱う領域」 has to name the four groups the programme adds
(水切りラック / 衣類乾燥除湿機 / ノンフライヤー・熱風調理器 / 軽量コードレス掃除機),
and 「根拠の確認手順」 must stop promising a dated seller-condition record for every
product, because the 17 new products have no approved offer and carry official
information links only (purchase_support.py renders 「価格は確認中」 and
「公式の商品情報を見る」 for them).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from raos.application.editorial.reader_html import Element, fragment
from scripts import build_reader_purchase_support_v1 as builder

ROOT = Path(__file__).resolve().parents[2]
RENDERER = ROOT / "python/raos/application/editorial/purchase_support.py"
SKIPPED_TAGS = frozenset({"script", "style", "template", "code", "pre"})
# The groups the programme adds, beside the four the page already declared.
ADDED_GROUPS = ("水切りラック", "衣類乾燥除湿機", "ノンフライヤー・熱風調理器", "軽量コードレス掃除機")
DECLARED_GROUPS = ("卓上食洗機", "機内持ち込みスーツケース", "ロボット掃除機", "ポータブル電源")
# Wave 0 revises the operating policy only; the other two policy pages are untouched.
REVISED_ON = "2026-09-16"


@pytest.fixture(scope="module")
def roots() -> dict[str, Element]:
    return {
        path.stem: fragment(text)
        for path, text in builder.build().items()
        if path.suffix == ".html"
    }


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
    return "".join(parts)


def sentences(text: str) -> list[str]:
    """Split on 。 outside 「」 so a quoted status string stays in its sentence."""
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


def labelled_section(root: Element, heading_id: str) -> Element:
    found = [n for n in root.find(tag="section") if n.attrs.get("aria-labelledby") == heading_id]
    assert len(found) == 1, heading_id
    return found[0]


def bullet(root: Element, label: str) -> Element:
    items = [
        li
        for li in labelled_section(root, "production-about-editors").find(tag="li")
        if visible_text(li).startswith(label)
    ]
    assert len(items) == 1, label
    return items[0]


def test_scope_covers_every_group_the_programme_adds(roots) -> None:
    """The 25 new articles are inside the declared scope before the first one is published."""
    scope = visible_text(bullet(roots["about-ad-policy"], "扱う領域："))
    for group in DECLARED_GROUPS + ADDED_GROUPS:
        assert group in scope, group
    assert "4分野" not in scope


def test_scope_does_not_claim_a_published_article_for_every_group(roots) -> None:
    """Wave 0 publishes no article, so the scope points at the index instead of implying one."""
    item = bullet(roots["about-ad-policy"], "扱う領域：")
    assert "/categories/" in [a.attrs.get("href") for a in item.find(tag="a")]
    assert "公開" in visible_text(item)


def test_evidence_procedure_limits_seller_conditions_to_products_with_a_seller(roots) -> None:
    """The new products have no approved offer: the seller step cannot be unconditional."""
    procedure = visible_text(bullet(roots["about-ad-policy"], "根拠の確認手順："))
    seller = [s for s in sentences(procedure) if "販売店の商品ページ" in s]
    assert len(seller) == 1, procedure
    assert "購入先を案内する商品" in seller[0], seller
    unmatched = [s for s in sentences(procedure) if "照合できた販売先がない商品" in s]
    assert len(unmatched) == 1, procedure
    assert "公式の商品情報" in unmatched[0], unmatched
    renderer = RENDERER.read_text(encoding="utf-8")
    assert "公式の商品情報を見る</a></p>" in renderer


def test_about_policy_records_the_wave_zero_revision(roots) -> None:
    """The page records this revision the way it records every other one."""
    root = roots["about-ad-policy"]
    times = [t for t in root.find(tag="time") if "最終更新日" in visible_text(t.parent)]
    assert [t.attrs.get("datetime") for t in times] == [REVISED_ON]
    note = visible_text(times[0].parent)
    assert "改定内容：" in note
    assert "扱う領域" in note
    for group in ADDED_GROUPS:
        assert group in note, group


def test_untouched_policy_pages_keep_their_own_revision_date(roots) -> None:
    """Wave 0 changes no wording on the other two pages, so their dates stay put."""
    for slug in ("comparison-policy", "privacy-policy"):
        times = [t for t in roots[slug].find(tag="time") if "最終更新日" in visible_text(t.parent)]
        assert [t.attrs.get("datetime") for t in times] == ["2026-09-15"], slug


def paragraph(root: Element, identifier: str) -> Element:
    items = [p for p in root.find(tag="p") if p.attrs.get("id") == identifier]
    assert len(items) == 1, identifier
    return items[0]


def test_scope_says_which_declared_groups_have_no_article_yet(roots) -> None:
    """The scope is declared before the articles exist, so it has to say so.

    Between W0 and W7 the page names eight fields while four of them hold no
    published article. Naming them keeps the present-tense claim exact in that
    window; the deferral record removes each one as its wave lands.
    """
    scope = visible_text(bullet(roots["about-ad-policy"], "扱う領域："))
    pending = [s for s in sentences(scope) if "準備中" in s]
    assert len(pending) == 1, scope
    for group in ADDED_GROUPS:
        assert group in pending[0], group
    for group in DECLARED_GROUPS:
        assert group not in pending[0], group


def test_reference_price_promise_covers_only_products_with_recorded_conditions(
    roots,
) -> None:
    """No new product has an approved offer, so the dated price note is conditional."""
    text = visible_text(
        paragraph(roots["about-ad-policy"], "production-about-rakuten-price")
    )
    dated = [s for s in sentences(text) if "確認日時を併記" in s]
    assert len(dated) == 1, text
    assert "販売条件を記録した商品" in dated[0], dated
    unmatched = [s for s in sentences(text) if "照合できた販売先がない商品" in s]
    assert len(unmatched) == 1, text
    assert "価格は確認中" in unmatched[0], unmatched


# --- 改定内容 is a reader's sentence ---------------------------------------
# The revision note is published text, not a work log. Wave 0 let three working
# words into it: 「群」 for the fields the same page counts as 「分野」,
# 「表示名」 for the name the reader sees, and the tautology 「カテゴリページの名前を
# 表示名にそろえ」. 「波」 is banned with them because the programme's own unit of
# work has no meaning on a reader's page.
WORKING_WORDS = ("群", "表示名", "波")
# The page counts its subject in 分野; the note may not rename that unit.
SCOPE_UNIT = "分野"


def revision_note(root: Element) -> str:
    times = [t for t in root.find(tag="time") if "最終更新日" in visible_text(t.parent)]
    assert len(times) == 1, times
    return visible_text(times[0].parent)


def test_the_revision_note_uses_no_working_vocabulary(roots) -> None:
    note = revision_note(roots["about-ad-policy"])
    for word in WORKING_WORDS:
        assert word not in note, (word, note)


def test_the_whole_policy_page_keeps_the_working_vocabulary_out(roots) -> None:
    """A word the site never uses elsewhere is a leak wherever it lands."""
    page = visible_text(roots["about-ad-policy"])
    for word in WORKING_WORDS:
        assert word not in page, (word, page)


def test_the_revision_note_counts_the_scope_the_way_the_page_counts_it(roots) -> None:
    """One page, one unit: 「8分野」 above, so 「4分野」 — never 「4群」 — below."""
    root = roots["about-ad-policy"]
    scope = visible_text(bullet(root, "扱う領域："))
    assert f"8{SCOPE_UNIT}" in scope, scope
    note = revision_note(root)
    pending = [s for s in sentences(note) if "まだ記事のない" in s or "準備中" in s]
    assert len(pending) == 1, note
    assert f"4{SCOPE_UNIT}" in pending[0], pending


# What this wave did to the two category pages, and the sentence a reader needs
# in order to recognise the page they had bookmarked. 「名前を…そろえ」 named only
# the destination; 「メニューやカードで使っている名前」 named a standard that did not
# exist — the cards were renamed by this same wave, and the menus never carried
# either page at all.
RENAMED_PAGES = (
    ("食洗機の選び方・比較", "台所の道具の選び方・比較"),
    ("ロボット掃除機の選び方・比較", "掃除の道具の選び方・比較"),
)
MENU_PARTS = (
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
    "/kurashinoshirube-child/parts/header.html",
    "changes/st-1704/self-hosted-editorial-pilot-v1/theme"
    "/kurashinoshirube-child/parts/footer.html",
)


def test_the_revision_note_names_the_old_and_the_new_page_names(roots) -> None:
    """A reader who bookmarked the old name has to find it in the note."""
    note = revision_note(roots["about-ad-policy"])
    renamed = [s for s in sentences(note) if "改称" in s]
    assert len(renamed) == 1, note
    for before, after in RENAMED_PAGES:
        assert before in renamed[0], (before, renamed)
        assert after in renamed[0], (after, renamed)


def test_the_revision_note_claims_no_menu_that_never_carried_these_pages(
    roots,
) -> None:
    """The menus hold five links, and neither category page is one of them."""
    note = revision_note(roots["about-ad-policy"])
    assert "メニュー" not in note, note
    menus = "".join(
        (ROOT / part).read_text(encoding="utf-8") for part in MENU_PARTS
    )
    for before, after in RENAMED_PAGES:
        assert before not in menus, before
        assert after not in menus, after
    for label in ("台所", "掃除"):
        assert f'"label":"{label}"' not in menus, label


def test_the_revision_note_covers_both_pages_the_wave_rewrote(roots) -> None:
    """/cleaning/ changed its lead and its headings too, not only /kitchen/."""
    note = revision_note(roots["about-ad-policy"])
    headings = [s for s in sentences(note) if "見出し" in s]
    assert len(headings) == 1, note
    for label in ("台所", "掃除"):
        assert label in headings[0], (label, headings)
