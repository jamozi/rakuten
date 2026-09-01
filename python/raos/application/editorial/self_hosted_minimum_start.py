"""Fixed first-article content packet loader for self-hosted Minimum Start."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from html import escape
import hashlib
import json
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import stat
from typing import Any, NoReturn, cast
from urllib.parse import parse_qsl, urlsplit

from raos.domain.editorial.self_hosted_wordpress import (
    SELF_HOSTED_WORDPRESS_ORIGIN,
    SelfHostedWordPressDraft,
    SelfHostedWordPressFailure,
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
RAKUTEN_CREDIT_FROM_COMMENT = "Rakuten Web Services Attribution Snippet FROM HERE"
RAKUTEN_CREDIT_TO_COMMENT = "Rakuten Web Services Attribution Snippet TO HERE"
RAKUTEN_CREDIT_ANCHOR = (
    '<a href="https://developers.rakuten.com/" target="_blank" rel="noopener noreferrer">'
    "Supported by Rakuten Developers</a>"
)
RAKUTEN_CREDIT_SNIPPET = (
    f"<!-- {RAKUTEN_CREDIT_FROM_COMMENT} -->\n"
    f"{RAKUTEN_CREDIT_ANCHOR}\n"
    f"<!-- {RAKUTEN_CREDIT_TO_COMMENT} -->"
)
AFFILIATE_CTA_LABEL = "楽天市場でこの商品の詳細を見る"
AFFILIATE_PENDING_STATUS = "PENDING"
AFFILIATE_FINAL_STATUS = "FINAL"
AFFILIATE_PENDING_DISCLOSURE_HTML = (
    "<p><strong>広告・アフィリエイトについて</strong>：この記事には楽天アフィリエイトの"
    "リンクを掲載する予定です。リンク経由の購入により運営者が成果報酬を受け取る場合が"
    "ありますが、報酬率、価格、ポイント、在庫は評価や掲載順に使いません。</p>"
)
AFFILIATE_FINAL_DISCLOSURE_HTML = (
    "<p><strong>広告・アフィリエイトについて</strong>：この記事には楽天アフィリエイトの"
    "リンクを掲載しています。リンク経由の購入により運営者が成果報酬を受け取る場合が"
    "ありますが、報酬率、価格、ポイント、在庫は評価や掲載順に使いません。</p>"
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
_PENDING_SLOT_KEYS = frozenset(
    {"slot_id", "product_name", "status", "destination_policy", "required_rel"}
)
_FINAL_SLOT_KEYS = frozenset(
    {
        "slot_id",
        "product_name",
        "status",
        "destination_policy",
        "required_rel",
        "destination_url",
        "evidence",
    }
)
_AFFILIATE_PROVIDER_EVIDENCE_KEYS = frozenset(
    {
        "api",
        "api_version",
        "endpoint_id",
        "evidence_authority",
        "request_fingerprint",
        "response_sha256",
        "result_sha256",
        "retrieved_at",
    }
)
_AFFILIATE_ATTESTATION_KEY = "destination_attestation_sha256"
_AFFILIATE_EVIDENCE_KEYS = _AFFILIATE_PROVIDER_EVIDENCE_KEYS | frozenset(
    {_AFFILIATE_ATTESTATION_KEY}
)
_SOURCE_KEYS = frozenset({"title", "url", "retrieved_on"})
_ALLOWED_SOURCE_HOSTS = frozenset(
    {
        "store.ace.jp",
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
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_UTC_MICROSECONDS = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z",
    re.ASCII,
)
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_RAKUTEN_AFFILIATE_PATH = re.compile(
    r"/hgc/[A-Za-z0-9._~-]{1,256}/\Z",
    re.ASCII,
)
_RAKUTEN_MOBILE_ITEM_PATH = re.compile(
    r"/ace-store/i/[0-9]{1,32}/\Z",
    re.ASCII,
)
_EXPECTED_SLOTS = (
    ("ace-cresta-06316", "ACE クレスタ 06316"),
    ("ace-difference-05721", "ace.TOKYO LABEL ディフェレンス 05721"),
    ("proteca-maxpass4-01471", "PROTECA マックスパス4 01471"),
)
_EXPECTED_AFFILIATE_PATHS = {
    "ace-cresta-06316": "/ace-store/06316/",
    "ace-difference-05721": "/ace-store/05721/",
    "proteca-maxpass4-01471": "/ace-store/01471/",
}
_EXPECTED_AFFILIATE_MOBILE_PATHS = {
    "ace-cresta-06316": "/ace-store/i/10007275/",
    "ace-difference-05721": "/ace-store/i/10009372/",
    "proteca-maxpass4-01471": "/ace-store/i/10009099/",
}
_EXPECTED_SLOT_MODEL_CODES = {
    "ace-cresta-06316": "06316",
    "ace-difference-05721": "05721",
    "proteca-maxpass4-01471": "01471",
}
_EXPECTED_AFFILIATE_ATTESTATIONS = {
    "ace-cresta-06316": (
        "103334aac9f8856524d50cdc43f7e321767cb6944f11ac71f65c4e48b03d895b"
    ),
    "ace-difference-05721": (
        "cc29a4323bed079013b24acbe3f6f7a7bce368eb5c6fca82b656fc4e7d0b5087"
    ),
    "proteca-maxpass4-01471": (
        "737ccd609ed98fda741c921a79b1bff6106c72e7299a47c9e50791e07e858b5e"
    ),
}
_ITEM_SEARCH_ELEMENTS = (
    "affiliateUrl",
    "availability",
    "catchcopy",
    "count",
    "first",
    "genreId",
    "hits",
    "itemCaption",
    "itemCode",
    "itemName",
    "itemPrice",
    "itemUrl",
    "last",
    "mediumImageUrls",
    "page",
    "pageCount",
    "postageFlag",
    "shopCode",
    "shopName",
    "smallImageUrls",
)
_ALLOWED_TAG_ATTRIBUTES: dict[str, frozenset[str]] = {
    "a": frozenset({"class", "href", "rel", "target"}),
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


def _validated_affiliate_url(value: object, slot_id: str | None = None) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or value != value.strip()
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x21 for character in value)
        or any(character in value for character in "\\\"'<>[]")
        or _MALFORMED_PERCENT_ESCAPE.search(value) is not None
    ):
        _fail()
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail()
    if (
        parsed.scheme != "https"
        or parsed.netloc != "hb.afl.rakuten.co.jp"
        or parsed.hostname != "hb.afl.rakuten.co.jp"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or _RAKUTEN_AFFILIATE_PATH.fullmatch(parsed.path) is None
        or parsed.fragment
    ):
        _fail()
    try:
        query_pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
    except ValueError:
        _fail()
    query = dict(query_pairs)
    if (
        len(query_pairs) != 3
        or len(query) != 3
        or frozenset(query) != frozenset({"m", "pc", "rafcid"})
        or not query["rafcid"]
        or not query["rafcid"].isascii()
        or len(query["rafcid"]) > 512
    ):
        _fail()
    expected_paths = (
        frozenset(_EXPECTED_AFFILIATE_PATHS.values())
        if slot_id is None
        else frozenset({_EXPECTED_AFFILIATE_PATHS.get(slot_id)})
    )
    expected_mobile_paths = (
        frozenset(_EXPECTED_AFFILIATE_MOBILE_PATHS.values())
        if slot_id is None
        else frozenset({_EXPECTED_AFFILIATE_MOBILE_PATHS.get(slot_id)})
    )
    try:
        desktop = urlsplit(query["pc"])
        mobile = urlsplit(query["m"])
        desktop_port = desktop.port
        mobile_port = mobile.port
    except ValueError:
        _fail()
    if (
        None in expected_paths
        or None in expected_mobile_paths
        or desktop.scheme != "https"
        or desktop.netloc != "item.rakuten.co.jp"
        or desktop.hostname != "item.rakuten.co.jp"
        or desktop.username is not None
        or desktop.password is not None
        or desktop_port is not None
        or desktop.path not in expected_paths
        or desktop.query
        or desktop.fragment
        or mobile.scheme not in {"http", "https"}
        or mobile.netloc != "m.rakuten.co.jp"
        or mobile.hostname != "m.rakuten.co.jp"
        or mobile.username is not None
        or mobile.password is not None
        or mobile_port is not None
        or _RAKUTEN_MOBILE_ITEM_PATH.fullmatch(mobile.path) is None
        or mobile.path not in expected_mobile_paths
        or mobile.query
        or mobile.fragment
    ):
        _fail()
    return value


def _canonical_sha256(value: object) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except UnicodeError, TypeError, ValueError:
        _fail()
    return hashlib.sha256(payload).hexdigest()


def _expected_affiliate_request_fingerprint(slot_id: str) -> str:
    model_code = _EXPECTED_SLOT_MODEL_CODES.get(slot_id)
    if type(model_code) is not str:
        _fail()
    policy = {
        "api_version": "2026-07-01",
        "appoint_delivery_date_only": False,
        "attribute_flag": False,
        "availability": True,
        "elements": list(_ITEM_SEARCH_ELEMENTS),
        "format_version": 2,
        "genre_information_flag": False,
        "hits": 30,
        "keyword": model_code,
        "or_flag": False,
        "page": 1,
        "postage_included_only": False,
        "sort": "standard",
    }
    return _canonical_sha256(
        {
            "api": "item-search",
            "endpoint_id": "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701",
            "policy": policy,
        }
    )


def affiliate_destination_attestation_sha256(
    slot_id: str,
    destination_url: str,
    provider_evidence: Mapping[str, object],
) -> str:
    """Bind one unchanged destination to its complete provider evidence."""

    if (
        type(slot_id) is not str
        or slot_id not in _EXPECTED_SLOT_MODEL_CODES
        or type(provider_evidence) is not dict
    ):
        _fail()
    evidence = cast(dict[str, object], provider_evidence)
    if frozenset(evidence) != _AFFILIATE_PROVIDER_EVIDENCE_KEYS:
        _fail()
    destination = _validated_affiliate_url(destination_url, slot_id)
    attestation_material: dict[str, object] = {
        "destination_url": destination,
        "provider_evidence": dict(evidence),
        "schema": "RAOS_ST1703_AFFILIATE_DESTINATION_ATTESTATION_V1",
        "slot_id": slot_id,
    }
    return _canonical_sha256(attestation_material)


def affiliate_cta_html(slot_id: str, destination_url: str) -> str:
    """Render one exact direct CTA while preserving the provider destination."""

    if type(slot_id) is not str or slot_id not in _EXPECTED_AFFILIATE_PATHS:
        _fail()
    validated_url = _validated_affiliate_url(destination_url, slot_id)
    escaped_url = escape(validated_url, quote=True)
    return (
        f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} BEGIN -->"
        f'<div class="raos-affiliate-slot" data-raos-affiliate-slot="{slot_id}">'
        f'<p><a class="raos-affiliate-cta" href="{escaped_url}" '
        f'rel="sponsored nofollow">{AFFILIATE_CTA_LABEL}</a></p></div>'
        f"<!-- RAOS-AFFILIATE-SLOT:{slot_id} END -->"
    )


class _ClosedArticleHtmlParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.affiliate_div_ids: list[str] = []
        self.affiliate_comments: list[str] = []
        self.affiliate_anchor_hrefs: list[str] = []
        self.credit_anchor_count = 0
        self.credit_comments: list[str] = []

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
        if tag == "a":
            if values == {
                "href": "https://developers.rakuten.com/",
                "target": "_blank",
            }:
                return
            if (
                frozenset(values) != frozenset({"class", "href", "rel"})
                or values.get("class") != "raos-affiliate-cta"
                or values.get("rel") != "sponsored nofollow"
                or type(values.get("href")) is not str
            ):
                raise ValueError("article HTML boundary")
            try:
                _validated_affiliate_url(values["href"])
            except SelfHostedWordPressFailure:
                raise ValueError("article HTML boundary") from None
        if tag not in {"a", "aside", "div", "p", "th"} and values:
            raise ValueError("article HTML boundary")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._validate_attributes(tag, attrs)
        values = dict(attrs)
        if tag == "div" and values.get("class") == "raos-affiliate-slot":
            slot_id = values.get("data-raos-affiliate-slot")
            if type(slot_id) is not str:
                raise ValueError("article HTML boundary")
            self.affiliate_div_ids.append(slot_id)
        if tag == "a":
            href = values.get("href")
            if href == "https://developers.rakuten.com/":
                self.credit_anchor_count += 1
            elif type(href) is str:
                self.affiliate_anchor_hrefs.append(href)
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
        if _SLOT_COMMENT.fullmatch(comment) is not None:
            self.affiliate_comments.append(comment)
            return
        if comment in {RAKUTEN_CREDIT_FROM_COMMENT, RAKUTEN_CREDIT_TO_COMMENT}:
            self.credit_comments.append(comment)
            return
        if _SLOT_COMMENT.fullmatch(comment) is None:
            raise ValueError("article HTML boundary")

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
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    int,
    tuple[str, ...],
]:
    try:
        parser = _ClosedArticleHtmlParser()
        parser.feed(content)
        parser.close()
        if parser.stack:
            raise ValueError("article HTML boundary")
        return (
            tuple(parser.affiliate_div_ids),
            tuple(parser.affiliate_comments),
            tuple(parser.affiliate_anchor_hrefs),
            parser.credit_anchor_count,
            tuple(parser.credit_comments),
        )
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


def load_first_article_candidate_with_affiliate_status(
    repository_root: object,
    *,
    operation: SelfHostedWordPressOperation,
    existing_draft_id: int | None = None,
    packet_bytes: bytes | None = None,
) -> tuple[SelfHostedWordPressDraft, str]:
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
    (
        html_slot_ids,
        html_slot_comments,
        html_affiliate_hrefs,
        html_credit_anchor_count,
        html_credit_comments,
    ) = _validate_article_html(content)
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
    affiliate_states: list[str] = []
    expected_affiliate_hrefs: list[str] = []
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
            type(slot_id) is not str
            or (slot_id, slot.get("product_name")) != expected_slot
            or content.count(f"RAOS-AFFILIATE-SLOT:{slot_id} BEGIN") != 1
            or content.count(f"RAOS-AFFILIATE-SLOT:{slot_id} END") != 1
        ):
            _fail()
        common_valid = (
            slot.get("destination_policy") == "DIRECT_RAKUTEN_AFFILIATE_URL"
            and slot.get("required_rel") == "sponsored nofollow"
        )
        if (
            frozenset(slot) == _PENDING_SLOT_KEYS
            and slot.get("status") == "PENDING_OFFICIAL_RAKUTEN_LINK"
            and common_valid
            and content.count(pending_slot) == 1
        ):
            affiliate_states.append(AFFILIATE_PENDING_STATUS)
            continue
        if (
            frozenset(slot) != _FINAL_SLOT_KEYS
            or slot.get("status") != "FINAL_OFFICIAL_RAKUTEN_LINK"
            or not common_valid
            or type(slot.get("evidence")) is not dict
        ):
            _fail()
        destination = _validated_affiliate_url(slot.get("destination_url"), slot_id)
        evidence = cast(dict[str, object], slot["evidence"])
        retrieved_at = evidence.get("retrieved_at")
        request_fingerprint = evidence.get("request_fingerprint")
        attestation = evidence.get(_AFFILIATE_ATTESTATION_KEY)
        if (
            frozenset(evidence) != _AFFILIATE_EVIDENCE_KEYS
            or evidence.get("api") != "item-search"
            or evidence.get("api_version") != "2026-07-01"
            or evidence.get("endpoint_id") != "RAKUTEN_ICHIBA_ITEM_SEARCH_20260701"
            or evidence.get("evidence_authority")
            != "OWNER_LOCAL_NON_FORMAL_LIVE_EVIDENCE"
            or request_fingerprint != _expected_affiliate_request_fingerprint(slot_id)
            or any(
                type(evidence.get(key)) is not str
                or _SHA256.fullmatch(cast(str, evidence[key])) is None
                for key in (
                    "request_fingerprint",
                    "response_sha256",
                    "result_sha256",
                    _AFFILIATE_ATTESTATION_KEY,
                )
            )
            or type(retrieved_at) is not str
            or _UTC_MICROSECONDS.fullmatch(retrieved_at) is None
        ):
            _fail()
        try:
            datetime.strptime(retrieved_at, "%Y-%m-%dT%H:%M:%S.%fZ")
        except ValueError:
            _fail()
        provider_evidence = {
            key: evidence[key] for key in _AFFILIATE_PROVIDER_EVIDENCE_KEYS
        }
        if attestation != affiliate_destination_attestation_sha256(
            slot_id,
            destination,
            provider_evidence,
        ) or attestation != _EXPECTED_AFFILIATE_ATTESTATIONS.get(slot_id):
            _fail()
        if content.count(affiliate_cta_html(slot_id, destination)) != 1:
            _fail()
        affiliate_states.append(AFFILIATE_FINAL_STATUS)
        expected_affiliate_hrefs.append(destination)
    if len(set(affiliate_states)) != 1:
        _fail()
    affiliate_status = affiliate_states[0]
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
    if affiliate_status == AFFILIATE_PENDING_STATUS:
        if (
            html_affiliate_hrefs
            or html_credit_anchor_count != 0
            or html_credit_comments
            or RAKUTEN_CREDIT_SNIPPET in content
            or content.count(AFFILIATE_PENDING_DISCLOSURE_HTML) != 1
            or AFFILIATE_FINAL_DISCLOSURE_HTML in content
        ):
            _fail()
    elif (
        html_affiliate_hrefs != tuple(expected_affiliate_hrefs)
        or html_credit_anchor_count != 1
        or html_credit_comments
        != (RAKUTEN_CREDIT_FROM_COMMENT, RAKUTEN_CREDIT_TO_COMMENT)
        or content.count(RAKUTEN_CREDIT_SNIPPET) != 1
        or content.count(RAKUTEN_CREDIT_ANCHOR) != 1
        or content.count(AFFILIATE_FINAL_DISCLOSURE_HTML) != 1
        or AFFILIATE_PENDING_DISCLOSURE_HTML in content
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
    if len(sources) != 4:
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
    return (
        SelfHostedWordPressDraft.bind(
            operation=operation,
            title=title,
            slug=slug,
            content_html=content,
            existing_draft_id=existing_draft_id,
        ),
        affiliate_status,
    )


def load_first_article_candidate(
    repository_root: object,
    *,
    operation: SelfHostedWordPressOperation,
    existing_draft_id: int | None = None,
    packet_bytes: bytes | None = None,
) -> SelfHostedWordPressDraft:
    candidate, _affiliate_status = load_first_article_candidate_with_affiliate_status(
        repository_root,
        operation=operation,
        existing_draft_id=existing_draft_id,
        packet_bytes=packet_bytes,
    )
    return candidate


__all__ = [
    "AFFILIATE_CTA_LABEL",
    "AFFILIATE_FINAL_STATUS",
    "AFFILIATE_PENDING_STATUS",
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
    "RAKUTEN_CREDIT_SNIPPET",
    "affiliate_destination_attestation_sha256",
    "affiliate_cta_html",
    "load_first_article_candidate",
    "load_first_article_candidate_with_affiliate_status",
]
