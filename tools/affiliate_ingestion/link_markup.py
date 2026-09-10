"""Validate creatives and edit a bounded slot while preserving all other bytes."""

from __future__ import annotations

from html import escape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit


class LinkError(ValueError):
    """Only fixed diagnostic codes are safe to print."""


def https_url(value: object, hosts: set[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 8192:
        raise LinkError("LINK_URL_INVALID")
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme == "https"
            and parsed.hostname
            and parsed.port in (None, 443)
            and not parsed.username
            and not parsed.password
        )
    except ValueError:
        valid = False
    if (
        not valid
        or any(ord(c) < 33 for c in value)
        or "\\" in value
        or (hosts is not None and parsed.hostname not in hosts)
    ):
        raise LinkError("LINK_URL_NOT_ALLOWED")
    return value


class CreativeParser(HTMLParser):
    def __init__(self, hosts: set[str]):
        super().__init__(convert_charrefs=False)
        self.hosts = hosts
        self.stack: list[str] = []
        self.anchors = 0
        self.destinations: list[str] = []

    def handle_starttag(self, tag, attrs):
        allowed = {
            "a": {"href", "rel", "target", "title", "class"},
            "img": {"src", "width", "height", "border", "alt", "title", "class"},
            "span": {"class"},
            "strong": set(),
            "em": set(),
            "br": set(),
        }
        if tag not in allowed or len(dict(attrs)) != len(attrs):
            raise LinkError("CREATIVE_MARKUP_NOT_ALLOWED")
        for key, value in attrs:
            if (
                key not in allowed[tag]
                or value is None
                or any(ord(c) < 32 for c in value)
            ):
                raise LinkError("CREATIVE_ATTRIBUTE_NOT_ALLOWED")
            if key in {"href", "src"}:
                https_url(value, self.hosts)
            if key == "target" and value not in {"_blank", "_self"}:
                raise LinkError("CREATIVE_TARGET_NOT_ALLOWED")
            if key in {"width", "height", "border"} and not re.fullmatch(
                r"[0-9]{1,4}", value
            ):
                raise LinkError("CREATIVE_DIMENSION_INVALID")
        values = dict(attrs)
        if tag == "a":
            if "href" not in values or "a" in self.stack:
                raise LinkError("CREATIVE_LINK_INVALID")
            self.anchors += 1
            self.destinations.append(values["href"])
        if tag == "img" and "src" not in values:
            raise LinkError("CREATIVE_IMAGE_INVALID")
        if tag not in {"img", "br"}:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag not in {"img", "br"}:
            raise LinkError("CREATIVE_SELF_CLOSING_NONVOID")
        self.handle_starttag(tag, attrs)

    def handle_data(self, data):
        # HTMLParser treats an unfinished tag as text on close(). Do not emit it
        # unchanged where a browser could consume the following article markup.
        if "<" in data:
            raise LinkError("CREATIVE_INCOMPLETE_MARKUP")

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            raise LinkError("CREATIVE_UNBALANCED")

    def handle_comment(self, data):
        raise LinkError("CREATIVE_COMMENT_NOT_ALLOWED")

    def handle_decl(self, decl):
        raise LinkError("CREATIVE_DECLARATION_NOT_ALLOWED")

    def unknown_decl(self, data):
        raise LinkError("CREATIVE_DECLARATION_NOT_ALLOWED")

    def handle_pi(self, data):
        raise LinkError("CREATIVE_DECLARATION_NOT_ALLOWED")


def creative(value: object, hosts: set[str], destination: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 65536:
        raise LinkError("CREATIVE_MISSING_OR_TOO_LARGE")
    parser = CreativeParser(hosts)
    parser.feed(value)
    if parser.rawdata:
        raise LinkError("CREATIVE_INCOMPLETE_MARKUP")
    parser.close()
    if parser.stack or parser.anchors != 1:
        raise LinkError("CREATIVE_REQUIRES_ONE_COMPLETE_LINK")
    if parser.destinations != [destination]:
        raise LinkError("CREATIVE_DESTINATION_MISMATCH")
    return value


class AnchorParser(HTMLParser):
    def __init__(self, source: str, anchor: str, product: str):
        super().__init__(convert_charrefs=True)
        # HTMLParser advances its line number on LF only, not Unicode separators.
        self.offsets = [0, *(match.end() for match in re.finditer("\n", source))]
        self.anchor, self.product = anchor, product
        self.stack: list[tuple[str, int | None]] = []
        self.ranges: list[tuple[int, int]] = []
        self.matches = 0

    def char_offset(self):
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        start = None
        if values.get("id") == self.anchor:
            self.matches += 1
            if (
                tag not in {"article", "section", "div"}
                or values.get("data-raos-product-id") != self.product
                or len(values) != len(attrs)
            ):
                raise LinkError("ARTICLE_PRODUCT_ANCHOR_INVALID")
            start = self.char_offset() + len(self.get_starttag_text())
        if tag not in {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }:
            self.stack.append((tag, start))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if self.stack and self.stack[-1][0] == tag:
            raise LinkError("ARTICLE_SELF_CLOSING_NONVOID")

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1][0] != tag:
            raise LinkError("ARTICLE_MARKUP_UNBALANCED")
        _, start = self.stack.pop()
        if start is not None:
            self.ranges.append((start, self.char_offset()))


def insert_slot(source: str, placement: dict, ad: str) -> str:
    parser = AnchorParser(source, placement["anchor_id"], placement["product_ref"])
    parser.feed(source)
    parser.close()
    if parser.stack or parser.matches != 1 or len(parser.ranges) != 1:
        raise LinkError("ARTICLE_ANCHOR_MISSING_OR_AMBIGUOUS")
    start, end = parser.ranges[0]
    slot = placement["slot_id"]
    begin = f"<!-- raos-affiliate:{slot}:start -->"
    finish = f"<!-- raos-affiliate:{slot}:end -->"
    rendered = (
        begin
        + f'<div class="raos-product-card__actions" data-raos-affiliate-slot="{escape(slot, quote=True)}">'
        '<p class="raos-disclosure">広告・PR</p>' + ad + "</div>" + finish
    )
    if begin in source or finish in source:
        if source.count(begin) != 1 or source.count(finish) != 1:
            raise LinkError("ARTICLE_SLOT_AMBIGUOUS")
        left, right = source.index(begin), source.index(finish) + len(finish)
        if not start <= left < right <= end:
            raise LinkError("ARTICLE_SLOT_OUTSIDE_PRODUCT")
        return source[:left] + rendered + source[right:]
    return source[:end] + rendered + source[end:]
