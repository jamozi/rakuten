"""Fixed first-article content packet loader for self-hosted Minimum Start."""

from __future__ import annotations

import json
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import stat
from typing import Any, NoReturn, cast

from raos.domain.editorial.self_hosted_wordpress import (
    SELF_HOSTED_WORDPRESS_ORIGIN,
    SelfHostedWordPressDraft,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    fail_self_hosted_wordpress,
)


CONTENT_PACKET_RELATIVE_PATH = Path(
    "changes/st-1703/self-hosted-minimum-start-v1/content/"
    "first-suitcase-comparison.v1.json"
)
MAX_CONTENT_PACKET_BYTES = 256 * 1024
FIRST_ARTICLE_THEME_IMAGE_RELATIVE_PATH = "assets/images/article-suitcase-guide.webp"
FIRST_ARTICLE_THEME_IMAGE_ALT = (
    "機内持ち込み手荷物の寸法を考えるための抽象的な旅支度の情景"
)
FIRST_ARTICLE_THEME_IMAGE_USAGE = "first article inline lead image"
FIRST_ARTICLE_SHORTCODE_TAG = "kurashinoshirube_first_article_lead_image"
FIRST_ARTICLE_THEME_SHORTCODE = f"[{FIRST_ARTICLE_SHORTCODE_TAG}]"
FIRST_ARTICLE_THEME_SLUG = "kurashinoshirube-child"
FIRST_ARTICLE_SLUG = "carry-on-suitcase-comparison"
FIRST_ARTICLE_TARGET_ORIGIN = SELF_HOSTED_WORDPRESS_ORIGIN
FIRST_ARTICLE_TITLE = (
    "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
)

_TOP_KEYS = frozenset(
    {
        "schema",
        "story_id",
        "slice_id",
        "target_origin",
        "publication_authority",
        "article",
        "sources",
    }
)
_ARTICLE_KEYS = frozenset(
    {
        "title",
        "slug",
        "canonical_url",
        "meta_title",
        "meta_description",
        "freshness_checked_on",
        "lead_image",
        "content_html",
        "affiliate_slots",
        "structured_data",
    }
)
_LEAD_IMAGE_KEYS = frozenset(
    {
        "alt",
        "delivery",
        "shortcode",
        "target_origin",
        "theme_asset_path",
        "theme_slug",
    }
)
_SLOT_KEYS = frozenset(
    {"slot_id", "product_name", "status", "destination_policy", "required_rel"}
)
_SOURCE_KEYS = frozenset({"title", "url", "retrieved_on"})
_ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "store.ace.jp",
        "item.rakuten.co.jp",
        "www.ana.co.jp",
    }
)
_FAKE_EXPERIENCE = re.compile(
    r"(?:実際に使って|使ってみた|購入して|愛用して|試したところ|手に取って)",
)
_SLOT_COMMENT = re.compile(
    r"RAOS-AFFILIATE-SLOT:[a-z0-9]+(?:-[a-z0-9]+)* (?:BEGIN|END)\Z",
    re.ASCII,
)
_EXPECTED_SLOTS = (
    ("ace-cresta-06316", "ACE クレスタ 06316"),
    ("ace-difference-05721", "ace.TOKYO LABEL ディフェレンス 05721"),
    ("proteca-maxpass4-01471", "PROTECA マックスパス4 01471"),
)
_ALLOWED_TAG_ATTRIBUTES: dict[str, frozenset[str]] = {
    "aside": frozenset({"aria-label", "class"}),
    "br": frozenset(),
    "caption": frozenset(),
    "div": frozenset({"class", "data-raos-affiliate-slot"}),
    "h2": frozenset(),
    "li": frozenset(),
    "ol": frozenset(),
    "p": frozenset({"class"}),
    "strong": frozenset(),
    "table": frozenset(),
    "tbody": frozenset(),
    "td": frozenset(),
    "th": frozenset({"scope"}),
    "thead": frozenset(),
    "tr": frozenset(),
    "ul": frozenset(),
}


class _ClosedArticleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.affiliate_div_ids: list[str] = []
        self.affiliate_comments: list[str] = []

    def _validate_attributes(
        self, tag: str, attributes: list[tuple[str, str | None]]
    ) -> None:
        allowed = _ALLOWED_TAG_ATTRIBUTES.get(tag)
        names = [name for name, _ in attributes]
        if (
            allowed is None
            or len(names) != len(set(names))
            or not set(names) <= allowed
        ):
            raise ValueError("article HTML boundary")
        values = dict(attributes)
        if any(value is None for value in values.values()):
            raise ValueError("article HTML boundary")
        if tag == "aside" and values != {
            "aria-label": "広告と編集について",
            "class": "raos-disclosure",
        }:
            raise ValueError("article HTML boundary")
        if tag == "p" and values not in (
            {},
            {"class": "lead"},
            {"class": "raos-freshness"},
        ):
            raise ValueError("article HTML boundary")
        if tag == "th" and values not in (
            {"scope": "col"},
            {"scope": "row"},
        ):
            raise ValueError("article HTML boundary")
        if tag == "div":
            valid_div = values == {"class": "wp-block-table raos-comparison"}
            if not valid_div:
                slot = values.get("data-raos-affiliate-slot")
                valid_div = (
                    values.get("class") == "raos-affiliate-slot"
                    and type(slot) is str
                    and re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slot, re.ASCII)
                    is not None
                    and len(values) == 2
                )
            if not valid_div:
                raise ValueError("article HTML boundary")
        if tag not in {"aside", "div", "p", "th"} and values:
            raise ValueError("article HTML boundary")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_attributes(tag, attrs)
        values = dict(attrs)
        if tag == "div" and values.get("class") == "raos-affiliate-slot":
            slot_id = values.get("data-raos-affiliate-slot")
            if type(slot_id) is not str:
                raise ValueError("article HTML boundary")
            self.affiliate_div_ids.append(slot_id)
        if tag != "br":
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_attributes(tag, attrs)
        if tag != "br":
            raise ValueError("article HTML boundary")

    def handle_endtag(self, tag: str) -> None:
        if tag == "br" or not self.stack or self.stack.pop() != tag:
            raise ValueError("article HTML boundary")

    def handle_comment(self, data: str) -> None:
        comment = data.strip()
        if _SLOT_COMMENT.fullmatch(comment) is None:
            raise ValueError("article HTML boundary")
        self.affiliate_comments.append(comment)

    def handle_decl(self, decl: str) -> None:
        del decl
        raise ValueError("article HTML boundary")

    def unknown_decl(self, data: str) -> None:
        del data
        raise ValueError("article HTML boundary")

    def handle_pi(self, data: str) -> None:
        del data
        raise ValueError("article HTML boundary")


def _validate_article_html(
    content: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    try:
        parser = _ClosedArticleHtmlParser()
        parser.feed(content)
        parser.close()
        if parser.stack:
            raise ValueError("article HTML boundary")
        return tuple(parser.affiliate_div_ids), tuple(parser.affiliate_comments)
    except ValueError:
        _fail()


def _fail() -> NoReturn:
    fail_self_hosted_wordpress(SelfHostedWordPressFailureCode.CONTENT_PACKET_INVALID)


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _read_stable(path: Path) -> bytes:
    if not path.is_absolute():
        _fail()
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        )
    except OSError:
        _fail()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 1 <= before.st_size <= MAX_CONTENT_PACKET_BYTES
        ):
            _fail()
        raw = os.read(descriptor, MAX_CONTENT_PACKET_BYTES + 1)
        after = os.fstat(descriptor)
        named = os.stat(path, follow_symlinks=False)
        if (
            len(raw) != before.st_size
            or len(raw) > MAX_CONTENT_PACKET_BYTES
            or before.st_dev != after.st_dev
            or before.st_ino != after.st_ino
            or after.st_dev != named.st_dev
            or after.st_ino != named.st_ino
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail()
        return raw
    finally:
        os.close(descriptor)


def _text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 32 and character not in "\t\n\r" for character in value)
    ):
        _fail()
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail()
    return value


def load_first_article_candidate(
    repository_root: object,
    *,
    operation: SelfHostedWordPressOperation,
    existing_draft_id: int | None = None,
    packet_bytes: bytes | None = None,
) -> SelfHostedWordPressDraft:
    if not isinstance(repository_root, Path) or not repository_root.is_absolute():
        _fail()
    path = repository_root / CONTENT_PACKET_RELATIVE_PATH
    if packet_bytes is None:
        raw = _read_stable(path)
    elif (
        type(packet_bytes) is bytes
        and 1 <= len(packet_bytes) <= MAX_CONTENT_PACKET_BYTES
    ):
        raw = packet_bytes
    else:
        _fail()
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail()
    if type(value) is not dict:
        _fail()
    packet = cast(dict[str, object], value)
    if (
        frozenset(packet) != _TOP_KEYS
        or packet["schema"] != "SELF_HOSTED_FIRST_ARTICLE_V1"
        or packet["story_id"] != "ST-1703"
        or packet["slice_id"] != "SELF_HOSTED_MINIMUM_START_V1"
        or packet["target_origin"] != SELF_HOSTED_WORDPRESS_ORIGIN
        or packet["publication_authority"] != "NONE"
        or type(packet["article"]) is not dict
        or type(packet["sources"]) is not list
    ):
        _fail()
    article = cast(dict[str, object], packet["article"])
    if frozenset(article) != _ARTICLE_KEYS:
        _fail()
    title = _text(article["title"], maximum=512)
    slug = _text(article["slug"], maximum=200)
    source_content = _text(article["content_html"], maximum=1_000_000)
    lead_image = article["lead_image"]
    if (
        type(lead_image) is not dict
        or frozenset(cast(dict[str, object], lead_image)) != _LEAD_IMAGE_KEYS
        or cast(dict[str, object], lead_image)
        != {
            "alt": FIRST_ARTICLE_THEME_IMAGE_ALT,
            "delivery": "FIRST_ARTICLE_THEME_SHORTCODE",
            "shortcode": FIRST_ARTICLE_THEME_SHORTCODE,
            "target_origin": FIRST_ARTICLE_TARGET_ORIGIN,
            "theme_asset_path": FIRST_ARTICLE_THEME_IMAGE_RELATIVE_PATH,
            "theme_slug": FIRST_ARTICLE_THEME_SLUG,
        }
    ):
        _fail()
    content = f"{FIRST_ARTICLE_THEME_SHORTCODE}\n{source_content}"
    html_slot_ids, html_slot_comments = _validate_article_html(content)
    if (
        title != FIRST_ARTICLE_TITLE
        or slug != FIRST_ARTICLE_SLUG
        or article["canonical_url"]
        != f"{FIRST_ARTICLE_TARGET_ORIGIN}/{FIRST_ARTICLE_SLUG}/"
        or article["freshness_checked_on"] != "2026-08-12"
        or not content.startswith(f"{FIRST_ARTICLE_THEME_SHORTCODE}\n")
        or content.count(FIRST_ARTICLE_THEME_SHORTCODE) != 1
        or "[" in source_content
        or "]" in source_content
        or _FAKE_EXPERIENCE.search(content) is not None
        or "報酬率、価格、ポイント、在庫は評価や掲載順に使いません" not in content
        or "構成と表現整理にはAIを補助的に利用しています" not in content
        or "確認できた事実" not in content
        or "編集部の整理" not in content
        or "仕様・航空会社条件の確認日" not in content
    ):
        _fail()
    slots = article["affiliate_slots"]
    if type(slots) is not list:
        _fail()
    slot_values = cast(list[object], slots)
    if len(slot_values) != 3:
        _fail()
    for item, expected_slot in zip(slot_values, _EXPECTED_SLOTS, strict=True):
        if type(item) is not dict:
            _fail()
        slot = cast(dict[str, object], item)
        slot_id = slot.get("slot_id")
        pending_slot = (
            f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} BEGIN -->"
            f'<div class="raos-affiliate-slot" '
            f'data-raos-affiliate-slot="{slot_id}">'
            "<p>公式楽天アフィリエイトリンク未設定</p></div>"
            f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} END -->"
        )
        if (
            frozenset(slot) != _SLOT_KEYS
            or type(slot_id) is not str
            or (slot_id, slot.get("product_name")) != expected_slot
            or slot["status"] != "PENDING_OFFICIAL_RAKUTEN_LINK"
            or slot["destination_policy"] != "DIRECT_RAKUTEN_AFFILIATE_URL"
            or slot["required_rel"] != "sponsored nofollow"
            or content.count(f"RAOS-AFFILIATE-SLOT:{slot_id} BEGIN") != 1
            or content.count(f"RAOS-AFFILIATE-SLOT:{slot_id} END") != 1
            or content.count(pending_slot) != 1
        ):
            _fail()
    expected_slot_ids = tuple(slot_id for slot_id, _ in _EXPECTED_SLOTS)
    expected_slot_comments = tuple(
        comment
        for slot_id in expected_slot_ids
        for comment in (
            f"RAOS-AFFILIATE-SLOT:{slot_id} BEGIN",
            f"RAOS-AFFILIATE-SLOT:{slot_id} END",
        )
    )
    if (
        html_slot_ids != expected_slot_ids
        or html_slot_comments != expected_slot_comments
    ):
        _fail()
    structured = article["structured_data"]
    if type(structured) is not dict or structured != {
        "allowed_types": ["Article", "BreadcrumbList"],
        "forbidden_types": ["Product", "Review", "AggregateRating", "FAQPage"],
        "visible_content_must_match": True,
    }:
        _fail()
    sources = cast(list[object], packet["sources"])
    if len(sources) != 7:
        _fail()
    for item in sources:
        if type(item) is not dict:
            _fail()
        source = cast(dict[str, object], item)
        url = source.get("url")
        if (
            frozenset(source) != _SOURCE_KEYS
            or source.get("retrieved_on") != "2026-08-12"
            or type(url) is not str
            or not url.startswith("https://")
            or url.split("/", 3)[2] not in _ALLOWED_SOURCE_HOSTS
        ):
            _fail()
    return SelfHostedWordPressDraft.bind(
        operation=operation,
        title=title,
        slug=slug,
        content_html=content,
        existing_draft_id=existing_draft_id,
    )


__all__ = [
    "CONTENT_PACKET_RELATIVE_PATH",
    "FIRST_ARTICLE_THEME_IMAGE_ALT",
    "FIRST_ARTICLE_THEME_IMAGE_RELATIVE_PATH",
    "FIRST_ARTICLE_THEME_IMAGE_USAGE",
    "FIRST_ARTICLE_SHORTCODE_TAG",
    "FIRST_ARTICLE_SLUG",
    "FIRST_ARTICLE_THEME_SHORTCODE",
    "FIRST_ARTICLE_THEME_SLUG",
    "FIRST_ARTICLE_TARGET_ORIGIN",
    "FIRST_ARTICLE_TITLE",
    "MAX_CONTENT_PACKET_BYTES",
    "load_first_article_candidate",
]
