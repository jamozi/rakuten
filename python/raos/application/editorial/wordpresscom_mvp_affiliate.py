"""In-memory grammar for the three manually filled Wave 3 affiliate slots."""

from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import re
from typing import NoReturn
from urllib.parse import urlsplit

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
    normalize_wordpresscom_mvp_line_endings,
)


_WHITESPACE = re.compile(r"[ \t\n]*\Z", re.ASCII)
_POSITIVE = re.compile(r"[1-9][0-9]{0,4}\Z", re.ASCII)
_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})", re.ASCII)
_REL = frozenset({"nofollow", "sponsored", "noopener", "noreferrer"})


def _fail() -> NoReturn:
    fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.AFFILIATE_INVALID)


def _https_url(value: str) -> None:
    if (
        type(value) is not str
        or not value
        or len(value) > 4096
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or "\\" in value
        or _MALFORMED_PERCENT.search(value) is not None
    ):
        _fail()
    if any(
        int(match.group(1), 16) <= 32 or int(match.group(1), 16) in {92, 127}
        for match in _PERCENT_ESCAPE.finditer(value)
    ):
        _fail()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail()
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or value.startswith("//")
        or parsed.netloc.endswith(":")
    ):
        _fail()


class _AffiliateParser(HTMLParser):
    def __init__(self, product_name: str) -> None:
        super().__init__(convert_charrefs=False)
        self.product_name = product_name
        self.stack: list[str] = []
        self.outer: str | None = None
        self.outer_closed = False
        self.anchor_kinds: list[str] = []
        self.current_anchor: str | None = None
        self.current_anchor_text = ""
        self.current_anchor_images = 0
        self.image_count = 0
        self.br_count = 0

    def _attributes(
        self, attrs: list[tuple[str, str | None]], allowed: frozenset[str]
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        for key, value in attrs:
            if (
                type(key) is not str
                or key not in allowed
                or key in result
                or type(value) is not str
            ):
                _fail()
            result[key] = value
        return result

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "div"}:
            if self.stack or self.outer is not None or attrs or self.outer_closed:
                _fail()
            self.outer = tag
            self.stack.append(tag)
            return
        if self.outer_closed or tag not in {"a", "img", "br"}:
            _fail()
        if tag == "br":
            if attrs or self.current_anchor is not None or self.br_count >= 1:
                _fail()
            self.br_count += 1
            return
        if tag == "a":
            if self.current_anchor is not None or "a" in self.stack:
                _fail()
            values = self._attributes(attrs, frozenset({"href", "target", "rel"}))
            if set(values) - {"href", "target", "rel"} or "href" not in values:
                _fail()
            _https_url(values["href"])
            target = values.get("target")
            if target not in {None, "_blank"}:
                _fail()
            rel_tokens = values.get("rel", "").split()
            if len(rel_tokens) != len(set(rel_tokens)) or any(
                token not in _REL for token in rel_tokens
            ):
                _fail()
            if target == "_blank" and not {"noopener", "noreferrer"}.issubset(
                rel_tokens
            ):
                _fail()
            self.current_anchor = "pending"
            self.current_anchor_text = ""
            self.current_anchor_images = 0
            self.stack.append("a")
            return
        if tag == "img":
            if self.current_anchor is None or self.current_anchor_text:
                _fail()
            values = self._attributes(
                attrs,
                frozenset(
                    {
                        "src",
                        "alt",
                        "width",
                        "height",
                        "border",
                        "loading",
                        "decoding",
                    }
                ),
            )
            if "src" not in values or values.get("width") != "128":
                _fail()
            _https_url(values["src"])
            if values.get("alt", "") not in {"", self.product_name}:
                _fail()
            if "height" in values and _POSITIVE.fullmatch(values["height"]) is None:
                _fail()
            if values.get("border", "0") != "0":
                _fail()
            if values.get("loading", "lazy") not in {"lazy", "eager", "auto"}:
                _fail()
            if values.get("decoding", "auto") not in {"async", "sync", "auto"}:
                _fail()
            self.current_anchor_images += 1
            self.image_count += 1
            if self.current_anchor_images > 1 or self.image_count > 1:
                _fail()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in {"img", "br"}:
            _fail()
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            if not self.stack or self.stack[-1] != "a" or self.current_anchor is None:
                _fail()
            self.stack.pop()
            if self.current_anchor_images == 1 and not self.current_anchor_text:
                kind = "image"
            elif (
                self.current_anchor_images == 0
                and self.current_anchor_text == self.product_name
            ):
                kind = "product"
            else:
                _fail()
            self.anchor_kinds.append(kind)
            self.current_anchor = None
            self.current_anchor_text = ""
            self.current_anchor_images = 0
            return
        if tag in {"p", "div"}:
            if (
                self.outer != tag
                or self.outer_closed
                or self.stack != [tag]
                or self.current_anchor is not None
            ):
                _fail()
            self.stack.pop()
            self.outer_closed = True
            return
        _fail()

    def handle_data(self, data: str) -> None:
        if not data:
            return
        if self.current_anchor is not None:
            if self.current_anchor_images or self.current_anchor_text:
                _fail()
            self.current_anchor_text = data
            return
        if _WHITESPACE.fullmatch(data) is None:
            _fail()

    def handle_entityref(self, name: str) -> None:
        del name
        _fail()

    def handle_charref(self, name: str) -> None:
        del name
        _fail()

    def handle_comment(self, data: str) -> None:
        del data
        _fail()

    def handle_decl(self, decl: str) -> None:
        del decl
        _fail()

    def unknown_decl(self, data: str) -> None:
        del data
        _fail()

    def close_and_validate(self) -> None:
        try:
            super().close()
        except Exception:
            _fail()
        if (
            self.stack
            or self.current_anchor is not None
            or (self.outer is None) != (not self.outer_closed)
            or sorted(self.anchor_kinds) != ["image", "product"]
            or len(self.anchor_kinds) != 2
            or self.image_count != 1
        ):
            _fail()


def validate_wordpresscom_mvp_affiliate_content(
    *,
    content: object,
    placeholder_content: str,
    product_names: tuple[str, str, str],
) -> tuple[MvpDraftAffiliateState, int]:
    """Classify exact placeholders or three fully valid isolated interiors."""

    normalized = normalize_wordpresscom_mvp_line_endings(content)
    if normalized == placeholder_content:
        return MvpDraftAffiliateState.SLOTS_PENDING, 0
    working = normalized
    outside = normalized
    interiors: list[str] = []
    previous_end = -1
    for slot in range(1, 4):
        begin = f"<!-- RAOS-W3-AFFILIATE-SLOT-{slot}-BEGIN -->"
        end = f"<!-- RAOS-W3-AFFILIATE-SLOT-{slot}-END -->"
        if working.count(begin) != 1 or working.count(end) != 1:
            _fail()
        begin_index = working.index(begin)
        end_index = working.index(end)
        if (
            begin_index <= previous_end
            or end_index <= begin_index
            or working[begin_index + len(begin) : begin_index + len(begin) + 1] != "\n"
            or working[end_index - 1 : end_index] != "\n"
        ):
            _fail()
        interior_start = begin_index + len(begin) + 1
        interior_end = end_index - 1
        interiors.append(working[interior_start:interior_end])
        sentinel = f"<RAOS-W3-AFFILIATE-SLOT-{slot}-CONTENT>"
        outside_begin = outside.index(begin)
        outside_end = outside.index(end)
        outside = (
            outside[: outside_begin + len(begin) + 1]
            + sentinel
            + outside[outside_end - 1 :]
        )
        previous_end = end_index + len(end)
    if hashlib.sha256(outside.encode("utf-8", errors="strict")).hexdigest() != (
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256
    ):
        _fail()
    for interior, product_name in zip(interiors, product_names):
        parser = _AffiliateParser(product_name)
        try:
            parser.feed(interior)
            parser.close_and_validate()
        except WordPressComMvpDraftFailure:
            raise
        except BaseException:
            _fail()
    return MvpDraftAffiliateState.SLOTS_VALIDATED, 3


__all__ = ["validate_wordpresscom_mvp_affiliate_content"]
