"""Project tracked editorial inputs into a reusable, non-publishing reader view."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
from typing import cast

from raos.application.editorial.reader_experience_v1 import CtaEvidence, ROLE_TYPES, cta_visible, validate_experience


VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
REGISTRY_PATH = Path("changes/editorial-portfolio-v3/reader-experience.v1.json")


@dataclass(eq=False)
class Element:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Element | str] = field(default_factory=list)
    parent: Element | None = field(default=None, repr=False)

    def has(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()

    def walk(self) -> Iterable[Element]:
        yield self
        for child in self.children:
            if isinstance(child, Element):
                yield from child.walk()

    def find(self, *, tag: str | None = None, cls: str | None = None) -> list[Element]:
        return [e for e in self.walk() if (tag is None or e.tag == tag) and (cls is None or e.has(cls))]

    def text(self) -> str:
        return unescape("".join(c.text() if isinstance(c, Element) else c for c in self.children)).strip()

    def html(self) -> str:
        content = "".join(c.html() if isinstance(c, Element) else c for c in self.children)
        if not self.tag:
            return content
        attrs = "".join(f" {key}" if value is None else f' {key}="{escape(value, quote=True)}"' for key, value in self.attrs.items())
        return f"<{self.tag}{attrs}>" + ("" if self.tag in VOID else content + f"</{self.tag}>")

    def remove(self) -> None:
        if self.parent is not None and self in self.parent.children:
            self.parent.children.remove(self)
        self.parent = None

    def append(self, child: Element | str) -> None:
        if isinstance(child, Element):
            child.remove()
            child.parent = self
        self.children.append(child)

    def insert_before(self, child: Element) -> None:
        parent = self.parent
        if parent is None:
            raise ValueError("READER_VIEW_PARENT_MISSING")
        child.remove()
        child.parent = parent
        parent.children.insert(parent.children.index(self), child)


class FragmentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.root = Element("")
        self.current = self.root

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.current.append(element)
        if tag not in VOID:
            self.current = element

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self.current.tag != tag or self.current.parent is None:
            raise ValueError("READER_VIEW_UNBALANCED_MARKUP")
        self.current = self.current.parent

    def handle_data(self, data: str) -> None:
        self.current.append(data)

    def handle_entityref(self, name: str) -> None:
        self.handle_data(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self.handle_data(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        self.handle_data(f"<!--{data}-->")


def fragment(markup: str) -> Element:
    parser = FragmentParser()
    parser.feed(markup)
    parser.close()
    if parser.current is not parser.root:
        raise ValueError("READER_VIEW_UNBALANCED_MARKUP")
    return parser.root


def block(markup: str) -> Element:
    return next(c for c in fragment(markup).children if isinstance(c, Element))


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
        issues = validate_experience(experience, product_refs=frozenset(bindings[article_id]["product_ids"]), evidence_refs=references)
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
    panel = block('<details class="raos-evidence-panel" id="reader-evidence"><summary>調査範囲・型番・確認日を詳しく見る</summary></details>')
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
        _research(root, article, article_id)
        _summary(root, settings)
    marker = block(f'<span class="raos-reader-view" data-raos-article-id="{escape(article_id, quote=True)}" hidden></span>')
    article.children.insert(0, marker)
    marker.parent = article
    return root.html()


def project_registered_article(root: Path, markup: str, *, article_id: str, evidence: CtaEvidence = CtaEvidence(), approved_product_images: frozenset[str] = frozenset()) -> str:
    experience = load_experiences(root).get(article_id)
    return project_article(markup, article_id=article_id, experience=experience if isinstance(experience, dict) else None, evidence=evidence, approved_product_images=approved_product_images)
