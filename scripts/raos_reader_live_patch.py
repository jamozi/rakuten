"""Bounded, offline edits against a freshly read WordPress document.

Never grants publication authority. Merchant links remain opaque; no network,
credentials, tracking configuration, source dates, or product claims are added.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import unquote, urlsplit


class PatchFailure(ValueError):
    """Closed, non-sensitive failure code; never include document content."""


VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
SAFE = frozenset("nav section div p h2 h3 a strong em span small br ul ol li aside details summary".split())
DATE = re.compile(r"20\d{2}(?:年\d{1,2}月\d{1,2}日|[-./]\d{1,2}[-./]\d{1,2})")


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None]
    start: int
    open_end: int
    end: int
    close_start: int
    parent: int | None


class Document(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=False)
        self.text = text
        self.nodes: list[Node] = []
        self.stack: list[int] = []
        self.lines = [0] + [m.end() for m in re.finditer("\n", text)]
        self.ids: dict[str, Node] = {}
        try:
            self.feed(text)
            self.close()
        except (ValueError, AssertionError) as exc:
            raise PatchFailure("HTML_INVALID") from exc
        if self.stack:
            raise PatchFailure("HTML_UNCLOSED")

    def position(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        start = self.position()
        end = start + len(self.get_starttag_text() or "")
        if len({k for k, _ in attrs}) != len(attrs):
            raise PatchFailure("ATTRIBUTE_DUPLICATE")
        node = Node(tag, dict(attrs), start, end, end, end,
                    self.stack[-1] if self.stack else None)
        ident = node.attrs.get("id")
        if ident:
            if ident in self.ids:
                raise PatchFailure("ID_DUPLICATE")
            self.ids[ident] = node
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(len(self.nodes) - 1)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.nodes[self.stack[-1]].tag != tag:
            raise PatchFailure("HTML_NESTING")
        node = self.nodes[self.stack.pop()]
        node.close_start = self.position()
        finish = self.text.find(">", node.close_start)
        if finish < 0:
            raise PatchFailure("HTML_INVALID")
        node.end = finish + 1


def _internal(href: str) -> bool:
    decoded = unquote(href)
    if not href or any(c in decoded for c in ("\\", "\n", "\r", "\t")):
        return False
    parsed = urlsplit(decoded)
    return (
        not parsed.scheme and not parsed.netloc
        and (decoded.startswith("#") or (decoded.startswith("/") and not decoded.startswith("//")))
        and not any(p in {"..", "wp-admin", "wp-json"} for p in parsed.path.split("/"))
    )


def _fragment(text: str, marker: str, tag: str) -> Document:
    doc = Document(text)
    roots = [n for n in doc.nodes if n.parent is None]
    if len(roots) != 1 or roots[0].tag != tag or roots[0].attrs.get("id") != marker:
        raise PatchFailure("FRAGMENT_ROOT_INVALID")
    for node in doc.nodes:
        if node.tag not in SAFE:
            raise PatchFailure("FRAGMENT_ELEMENT_FORBIDDEN")
        for key, value in node.attrs.items():
            if key.startswith("on") or key in {"src", "srcdoc", "action", "formaction"}:
                raise PatchFailure("FRAGMENT_ATTRIBUTE_FORBIDDEN")
            if key == "href" and not _internal(value or ""):
                raise PatchFailure("FRAGMENT_LINK_FORBIDDEN")
            if key == "style" and re.search(r"url\s*\(|expression\s*\(|@import|behavior\s*:", value or "", re.I):
                raise PatchFailure("FRAGMENT_STYLE_FORBIDDEN")
    return doc


def _protected(doc: Document) -> tuple[Any, ...]:
    links = tuple(doc.text[n.start:n.open_end] for n in doc.nodes
                  if n.tag == "a" and not _internal(n.attrs.get("href") or ""))
    images = tuple(doc.text[n.start:n.open_end] for n in doc.nodes
                   if n.tag == "img" and n.attrs.get("data-raos-product-image-state") == "verified")
    models = frozenset(n.attrs["data-raos-product-id"] for n in doc.nodes
                       if n.attrs.get("data-raos-product-id"))
    dates = Counter(DATE.findall(doc.text))
    return links, images, models, dates


def _edit(text: str, edits: list[tuple[int, int, str]]) -> str:
    ordered = sorted(edits, reverse=True)
    previous = len(text) + 1
    for start, end, replacement in ordered:
        if start < 0 or end < start or end > previous:
            raise PatchFailure("EDIT_OVERLAP")
        text = text[:start] + replacement + text[end:]
        previous = start
    return text


def apply_patch(body: str, patch: dict[str, Any], *, article_key: str, post_id: int) -> str:
    if not isinstance(body, str) or not body.strip() or len(body.encode("utf-8")) > 4 * 1024 * 1024:
        raise PatchFailure("BASELINE_INVALID")
    if (not isinstance(patch, dict) or patch.get("schema") != "RAOSReaderLivePatchV1"
            or patch.get("article_key") != article_key
            or type(post_id) is not int or patch.get("post_id") != post_id):
        raise PatchFailure("TARGET_MISMATCH")
    before = Document(body)
    protected = _protected(before)
    required = patch.get("required_ids")
    models = patch.get("required_product_ids")
    if not isinstance(required, list) or not isinstance(models, list):
        raise PatchFailure("PATCH_SCHEMA_INVALID")
    if not set(required).issubset(before.ids):
        raise PatchFailure("REQUIRED_ANCHOR_MISSING")
    if set(models) != protected[2]:
        raise PatchFailure("MODEL_SET_MISMATCH")
    for text in patch.get("required_text", []):
        if not isinstance(text, str) or text not in body:
            raise PatchFailure("REQUIRED_TEXT_MISSING")
    for change in patch.get("replacements", []):
        old, new, maximum = change.get("old"), change.get("new"), change.get("max_count", 1)
        if not isinstance(old, str) or not old or not isinstance(new, str) or not new:
            raise PatchFailure("REPLACEMENT_INVALID")
        if any(c in old + new for c in "<>"):
            raise PatchFailure("REPLACEMENT_MARKUP_FORBIDDEN")
        count = body.count(old)
        if type(maximum) is not int or maximum < 1 or count > maximum:
            raise PatchFailure("REPLACEMENT_COUNT_MISMATCH")
        if count:
            body = body.replace(old, new)
        elif new not in body:
            raise PatchFailure("REPLACEMENT_NOT_FOUND")

    # Remove only explicitly neutral pictures or known decorative table images.
    doc = Document(body)
    removals: list[tuple[int, int, str]] = []
    for node in doc.nodes:
        if node.tag != "img" or node.attrs.get("data-raos-product-image-state") == "verified":
            continue
        neutral = node.attrs.get("data-raos-product-image-state") == "neutral"
        decorative = ("raos-comparison__product-image" in (node.attrs.get("class") or "").split()
                      and (node.attrs.get("src") or "").endswith(("/home-hero.webp", "/article-portable-power-guide.png")))
        if not (neutral or decorative):
            continue
        parent = doc.nodes[node.parent] if node.parent is not None else None
        if parent and parent.tag in {"figure", "div"}:
            rest = body[parent.open_end:node.start] + body[node.end:parent.close_start]
            if not re.sub(r"<!--.*?-->", "", rest, flags=re.S).strip():
                removals.append((parent.start, parent.end, "<!-- 商品写真は未掲載 -->"))
                continue
        removals.append((node.start, node.end, "<!-- 装飾画像を商品写真に使用しない -->"))
    body = _edit(body, removals)

    for field, marker, tag in (("nav_html", "ks-article-nav", "nav"),
                               ("next_html", "ks-next-read", "section")):
        fragment = patch.get(field, "")
        if not isinstance(fragment, str):
            raise PatchFailure("FRAGMENT_INVALID")
        if not fragment:
            continue
        additions = _fragment(fragment, marker, tag)
        doc = Document(body)
        old = doc.ids.get(marker)
        replaced_ids = {n.attrs.get("id") for n in doc.nodes
                        if old and old.start <= n.start < old.end}
        if (set(additions.ids) - replaced_ids) & set(doc.ids):
            raise PatchFailure("FRAGMENT_ID_CONFLICT")
        if old:
            if patch.get("keep_existing_fragments") is True:
                continue
            body = _edit(body, [(old.start, old.end, fragment)])
        else:
            roots = [n for n in doc.nodes if n.tag == "div"
                     and "raos-editorial-v2" in (n.attrs.get("class") or "").split()]
            if len(roots) != 1:
                raise PatchFailure("ARTICLE_ROOT_INVALID")
            point = roots[0].open_end if field == "nav_html" else roots[0].close_start
            body = body[:point] + fragment + body[point:]
    body = inline_reader_styles(body)
    after = Document(body)
    if _protected(after) != protected:
        raise PatchFailure("PROTECTED_CONTENT_CHANGED")
    if not set(required).issubset(after.ids):
        raise PatchFailure("REQUIRED_ANCHOR_REMOVED")
    for field in ("nav_html", "next_html"):
        if patch.get(field):
            for node in Document(patch[field]).nodes:
                href = node.attrs.get("href") or ""
                if href.startswith("#") and unquote(href[1:]) not in after.ids:
                    raise PatchFailure("FRAGMENT_DESTINATION_MISSING")
    return body


def inline_reader_styles(body: str) -> str:
    """Retain reader layout in authored markup, independent of Additional CSS.

    Existing inline declarations win. Never alters a link, image, source claim,
    tracking attribute or the magazine homepage. Only known reader components.
    """
    styles = {
        "ks-reader-start": "box-sizing:border-box;max-width:76rem;padding:24px;margin:24px auto;border-top:3px solid #8b3f2b;background:#faf9f6;color:#1b1b18;line-height:1.85;overflow-wrap:anywhere;",
        "ks-route-grid": "display:flex;flex-wrap:wrap;gap:20px;margin:16px 0;",
        "ks-route-links": "display:flex;flex-direction:column;gap:6px;",
        "ks-inline-links": "display:flex;flex-wrap:wrap;gap:12px;margin:16px 0;",
        "ks-reader-ad-note": "font-size:.9rem;line-height:1.8;",
    }
    doc = Document(body)
    edits = []
    for node in doc.nodes:
        if node.tag not in {"div", "nav", "section", "article", "p"}:
            continue
        if node.attrs.get("data-ks-inline-style") == "v1":
            continue
        classes = (node.attrs.get("class") or "").split()
        css = "".join(styles[c] for c in classes if c in styles)
        parent = doc.nodes[node.parent] if node.parent is not None else None
        if node.tag == "article" and parent and "ks-route-grid" in (parent.attrs.get("class") or "").split():
            css += "flex:1 1 240px;min-width:0;max-width:100%;padding:16px;border:1px solid #d7d3cb;background:#fff;box-sizing:border-box;"
        if not css:
            continue
        raw = body[node.start:node.open_end]
        raw = re.sub(r"\sstyle\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+)", "", raw, count=1, flags=re.I)
        css += node.attrs.get("style") or ""
        replacement = raw[:-1] + ' style="' + escape(css, quote=True) + '" data-ks-inline-style="v1">'
        edits.append((node.start, node.open_end, replacement))
    return _edit(body, edits)
