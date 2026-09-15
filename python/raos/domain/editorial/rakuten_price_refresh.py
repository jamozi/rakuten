"""Rakuten Ichiba price refresh core (KS-020 / KS-304).

API price and availability values never enter git-tracked files. The only
durable product of a run is an owner-private overlay under the owner checkout
``.secrets`` directory; the publisher injects it into price-free bodies right
before sending them to WordPress and re-sends the price-free bodies before the
overlay expires. See ``changes/reader-purchase-support-v1/price-refresh-contract.md``.

This module is pure: no file, network, clock or credential access.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
from html import escape, unescape
import json
import re
from typing import Any, Final, NoReturn
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit

# Official request format, verified 2026-09-15 against
# https://webservice.rakuten.co.jp/documentation/ichiba-item-search (version 2026-07-01).
API_HOST: Final = "openapi.rakuten.co.jp"
API_PATH: Final = "/ichibams/api/IchibaItem/Search/20260701"
API_VERSION_ID: Final = "rakuten_ws_item_search_20260701"
REQUEST_ELEMENTS: Final = (
    "itemCode",
    "itemName",
    "itemUrl",
    "shopCode",
    "itemPrice",
    "itemPriceMin1",
    "itemPriceMax1",
    "itemPriceMin3",
    "itemPriceMax3",
    "availability",
    "taxFlag",
    "postageFlag",
)
MAX_CACHE_AGE: Final = timedelta(hours=24)
GATE_MIN_REMAINING: Final = timedelta(hours=2)
MAX_RESPONSE_BYTES: Final = 4_000_000
MAX_REQUESTS_PER_RUN: Final = 60
MIN_REQUEST_INTERVAL_SECONDS: Final = 1.1

PLAN_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_REFRESH_PLAN_V1"
OBSERVATION_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_REFRESH_OBSERVATION_V1"
OVERLAY_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_V1"
PURGED_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_OVERLAY_PURGED_V1"
APPROVAL_SCHEMA: Final = "RAOS_RAKUTEN_PRICE_REFRESH_APPROVAL_V1"

PRIVATE_ROOT_RELATIVE: Final = ".secrets/rakuten-price-refresh"
CREDENTIAL_RELATIVE: Final = ".secrets/rakuten-owner-local/credentials.v1.json"
CREDENTIAL_PROFILE: Final = "OWNER_LOCAL_RAKUTEN_PRODUCTION_API"

# Injection attribute names are assembled, so no tracked source contains a
# complete injected attribute (the tracked-file scan looks for those).
_PS: Final = "data-ps-"
ATTR_PRICE_YEN: Final = _PS + "price-yen"
ATTR_TAX_INCLUDED: Final = _PS + "tax-included"
ATTR_PRICE_SOURCE: Final = _PS + "price-source"
ATTR_OVERLAY_RUN: Final = _PS + "overlay-run"
ATTR_REFERENCE_PRICE: Final = _PS + "reference-price"
ATTR_REFERENCE_OFFER: Final = _PS + "reference-offer"
# RWS help 900001974343 (3): the disclaimer must sit next to (or be linked from) the
# dated price. RWS credit guide: the text credit links developers.rakuten.com.
DISCLAIMER_HREF: Final = "/about-ad-policy/#production-about-rakuten-price"
_PRICE_DATE_PARAGRAPH: Final = re.compile(
    r'<p class="ps-price-date">(?:(?!</p>).)*</p>', re.S
)
_RAKUTEN_CREDIT: Final = re.compile(
    r'<p class="[^"]*\bps-media-credit\b[^"]*">(?:(?!</p>).)*?'
    r'<a href="https://developers\.rakuten\.com/"[^>]*>Supported by Rakuten Developers</a>',
    re.S,
)

RUN_ID_PATTERN: Final = re.compile(r"[a-z0-9][a-z0-9-]{7,63}\Z", re.ASCII)
_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_ITEM_PATH: Final = re.compile(
    r"/([A-Za-z0-9._~-]{1,100})/([A-Za-z0-9._~-]{1,200})/?\Z", re.ASCII
)
# "+" is part of a model name (K11+ / j9+ are different products), so it is not a separator.
_TOKEN_SEPARATOR: Final = re.compile(r"[\s*・_.\-/＆&]+")
_TOKEN_SEPARATOR_PATTERN: Final = r"[\s*・_.\-/＆&]*"
_MULTI_SKU_TEXT: Final = re.compile(
    r"共通販売ページ|を選択|選択SKU|色は未確認|カラーを選|サイズを選"
)
_COLOR_CODE_PREFIX: Final = re.compile(r"\s*[0-9]{2}[：:]")
_MODEL_TOKEN: Final = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9+*\-_.]*[0-9][A-Za-z0-9+*\-_.]*"
)
DEFAULT_FORBIDDEN_TITLE_TOKENS: Final = (
    "セット",
    "中古",
    "訳あり",
    "アウトレット",
    "展示品",
    "延長保証",
    "ソーラーパネル",
    "レンタル",
    "福袋",
    "まとめ買い",
    "まとめ売り",
    "交換用",
    "互換",
    "消耗品",
    "本体なし",
    "本体別売",
    "並行輸入",
    "リファービッシュ",
    "整備済",
    "再生品",
    "ジャンク",
    "訳アリ",
    "開封品",
)
# Colour groups: (group, terms matched in API titles, extra terms accepted only in editorial text).
# Kanji other than 白/黒 are never matched in titles (赤ちゃん, お茶 ...).
_COLOR_GROUPS: Final = (
    ("white", ("ホワイト", "white", "白"), ("シロ", "shiro")),
    ("black", ("ブラック", "black", "黒"), ("クロ", "kuro")),
    ("gray", ("グレー", "グレイ", "gray", "grey"), ("灰",)),
    ("silver", ("シルバー", "silver"), ("銀",)),
    ("gold", ("ゴールド", "gold"), ()),
    ("red", ("レッド", "red"), ("赤",)),
    ("blue", ("ブルー", "blue"), ("青",)),
    ("navy", ("ネイビー", "navy"), ()),
    ("green", ("グリーン", "green"), ("緑",)),
    ("yellow", ("イエロー", "yellow"), ("黄",)),
    ("pink", ("ピンク", "pink"), ()),
    ("beige", ("ベージュ", "beige"), ()),
    ("brown", ("ブラウン", "brown"), ("茶",)),
    ("purple", ("パープル", "purple"), ()),
    ("orange", ("オレンジ", "orange"), ()),
    ("khaki", ("カーキ", "khaki"), ()),
    ("ivory", ("アイボリー", "ivory"), ()),
)
_TITLE_MULTI_VARIANT: Final = re.compile(
    r"全\s*[0-9]+\s*(?:色|カラー|タイプ|サイズ)|[0-9]+\s*色(?:展開|から)"
    r"|(?:色|カラー|サイズ|タイプ)(?:が|を)?選べる|選べる\s*[0-9]*\s*(?:色|カラー|サイズ|タイプ)"
    r"|(?:カラー|サイズ|タイプ)\s*選択"
)
_TITLE_QUANTITY: Final = re.compile(
    r"[×✕]\s*[2-9](?![0-9.])\s*(?:個|台|本|点|組|箱|枚|袋|パック|セット|$|[\s）)】」\]])"
    r"|(?<![0-9.])[2-9]\s*(?:個|台|点)\s*(?:組|パック|入り?|まとめ)"
)
# Keys that only API responses (or values derived from them) may carry. A plan is
# editorial and git-storable, so it must never contain any of them.
API_VALUE_KEYS: Final = frozenset(
    {
        "price_yen",
        "amount_yen",
        "itemPrice",
        "itemPriceMin3",
        "itemPriceMax3",
        "itemPriceMin1",
        "itemPriceMax1",
        "tax_included",
        "taxFlag",
        "postageFlag",
        "postage_included",
        "availability",
        "state",
        "itemName",
        "observed_at",
        "cache_expires_at",
        "reference_price",
        "response_row_sha256",
    }
)
VALUE_STATES: Final = frozenset({"AVAILABLE", "SOLD_OUT", "UNKNOWN"})
UTC: Final = timezone.utc
JST: Final = timezone(timedelta(hours=9))


class RefreshError(ValueError):
    """A refusal with a stable code and no value or credential material."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def fail(code: str) -> NoReturn:
    raise RefreshError(code)


class Status(StrEnum):
    MATCHED = "MATCHED"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    MULTI_SKU_NO_PRICE = "MULTI_SKU_NO_PRICE"
    SOLD_OUT = "SOLD_OUT"
    NOT_FOUND_PENDING = "NOT_FOUND_PENDING"
    REQUEST_FAILED = "REQUEST_FAILED"


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def canonical_json(value: object) -> str:
    """Same serialization as the purchase-support ``canonical()`` attribute JSON."""
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        fail("TIMESTAMP_NAIVE")
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        fail("TIMESTAMP_INVALID")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail("TIMESTAMP_INVALID")
    if moment.tzinfo is None:
        fail("TIMESTAMP_NAIVE")
    return moment


def jp_datetime(moment: datetime) -> str:
    local = moment.astimezone(JST)
    return f"{local.year}年{local.month}月{local.day}日 {local.hour:02d}:{local.minute:02d}"


def require_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or RUN_ID_PATTERN.fullmatch(run_id) is None:
        fail("RUN_ID_INVALID")
    return run_id


def title_has_token(title: str, token: str) -> bool:
    """ST-1704 capture-adapter boundary rule, except that "+" must match literally and a
    model token never matches a "+" variant (``SYN-100A`` does not match ``SYN-100A+``)."""
    if not title or not token:
        return False
    normalized_title = unicodedata.normalize("NFKC", title).casefold()
    normalized_token = unicodedata.normalize("NFKC", token).casefold()
    components = [c for c in _TOKEN_SEPARATOR.split(normalized_token) if c]
    if not components:
        return False
    pattern = _TOKEN_SEPARATOR_PATTERN.join(re.escape(c) for c in components)
    prefix = (
        r"(?<![a-z0-9])"
        if re.fullmatch(r"[a-z0-9]", components[0][0], re.ASCII)
        else ""
    )
    suffix = (
        r"(?![a-z0-9+])"
        if re.fullmatch(r"[a-z0-9]", components[-1][-1], re.ASCII)
        else ""
    )
    return re.search(prefix + pattern + suffix, normalized_title) is not None


def _squash(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s+*・_.\-/＆&()（）]+", "", text)


def strong_title_token(token: str) -> bool:
    """A title token must be specific enough to reject a reused item page (not "500")."""
    core = re.sub(r"[^0-9a-z]", "", unicodedata.normalize("NFKC", token).casefold())
    return len(core) >= 4 and not (core.isdigit() and len(core) < 5)


def _color_term_pattern(term: str) -> str:
    if term.isascii():
        return r"(?<![a-z])" + re.escape(term) + r"(?![a-z])"
    if len(term) == 1:
        return r"(?<![\u4e00-\u9fff々])" + re.escape(term) + r"色?(?![\u4e00-\u9fff々])"
    return (
        r"(?<![\u30a1-\u30fa\u30fc])" + re.escape(term) + r"(?![\u30a1-\u30fa\u30fc])"
    )


def color_groups(text: str, *, editorial: bool) -> frozenset[str]:
    """Colour groups named by editorial text (substring) or by an API title (standalone words)."""
    found = set()
    normalized = unicodedata.normalize("NFKC", text).casefold()
    squashed = _squash(text)
    for name, title_terms, editorial_terms in _COLOR_GROUPS:
        if editorial:
            if any(_squash(t) in squashed for t in (*title_terms, *editorial_terms)):
                found.add(name)
        elif any(re.search(_color_term_pattern(t), normalized) for t in title_terms):
            found.add(name)
    return frozenset(found)


def link_item_url(href: str) -> str | None:
    """Canonical item page behind a CTA href (direct, or the hb.afl ``pc`` target)."""
    raw = unescape(href)
    direct = canonical_item_url(raw)
    if direct is not None:
        return direct[0]
    try:
        parts = urlsplit(raw)
    except ValueError:
        return None
    if parts.scheme != "https" or parts.hostname != "hb.afl.rakuten.co.jp":
        return None
    targets = [
        v for k, v in parse_qsl(parts.query, keep_blank_values=True) if k == "pc"
    ]
    inner = canonical_item_url(targets[0]) if len(targets) == 1 else None
    return inner[0] if inner is not None else None


def canonical_item_url(url: object) -> tuple[str, str, str] | None:
    """Return (canonical item URL, shop code, item id) for an item.rakuten.co.jp page."""
    if not isinstance(url, str) or any(c.isspace() for c in url):
        return None
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if (
        parts.scheme != "https"
        or (parts.hostname or "") != "item.rakuten.co.jp"
        or parts.username
        or parts.password
        or port is not None
    ):
        return None
    match = _ITEM_PATH.fullmatch(parts.path)
    if match is None:
        return None
    shop, item = match.group(1), match.group(2)
    return f"https://item.rakuten.co.jp/{shop}/{item}/", shop, item


def _variant_id_in_url(url: str) -> str | None:
    values = [
        v
        for k, v in parse_qsl(urlsplit(url).query, keep_blank_values=True)
        if k == "variantId"
    ]
    if len(values) > 1:
        fail("PLAN_VARIANT_ID_AMBIGUOUS")
    return values[0] if values else None


def _model_tokens(model: str) -> list[str]:
    head = model.split(" / ")[0]
    head = re.sub(r"\(.*?\)|（.*?）", "", head).strip()
    if head and head.isascii():
        return [head]
    found = _MODEL_TOKEN.findall(unicodedata.normalize("NFKC", head))
    return [found[0]] if found else []


def multi_sku_reasons(offer: Mapping[str, Any], item_id: str) -> list[str]:
    reasons = []
    merchant = str(offer.get("merchant_url") or "")
    variant = str(offer.get("variant") or "")
    model = str(offer.get("product_model") or "")
    variant_id = offer.get("variant_id")
    if _variant_id_in_url(merchant) is not None:
        reasons.append("VARIANT_ID_IN_URL")
    if _MULTI_SKU_TEXT.search(variant):
        reasons.append("VARIANT_TEXT_SELECTION")
    if _COLOR_CODE_PREFIX.match(variant):
        reasons.append("VARIANT_COLOR_CODE")
    if " / " in model:
        reasons.append("MULTIPLE_MODELS")
    if (
        isinstance(variant_id, str)
        and variant_id
        and not variant_id.startswith("observed-")
        and _squash(variant_id) != _squash(item_id)
        and _squash(variant_id) not in _squash(model)
    ):
        reasons.append("SKU_ID_DIFFERS_FROM_ITEM")
    return reasons


PLAN_ENTRY_KEYS: Final = (
    "offer_id",
    "product_id",
    "exact_model",
    "seller",
    "seller_id",
    "variant",
    "variant_id",
    "merchant_url",
    "item_code",
    "shop_code",
    "item_url",
    "sku_variant_id",
    "multi_sku",
    "multi_sku_reasons",
    "required_title_tokens",
    "forbidden_title_tokens",
    "seller_shop_consistent",
)


def build_plan(catalog: Mapping[str, Any], catalog_sha256: str) -> dict[str, Any]:
    """Derive editorial identity bindings from tracked catalog links (no API data)."""
    if _SHA256.fullmatch(catalog_sha256) is None:
        fail("CATALOG_SHA256_INVALID")
    products = {
        p.get("product_id"): p
        for p in catalog.get("products", [])
        if isinstance(p, Mapping)
    }
    entries: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for offer in catalog.get("offers", []):
        offer_id = str(offer.get("offer_id"))
        parsed = canonical_item_url(offer.get("merchant_url"))
        if parsed is None:
            host = ""
            try:
                host = urlsplit(str(offer.get("merchant_url") or "")).hostname or ""
            except ValueError:
                host = ""
            reason = (
                "MERCHANT_URL_UNPARSEABLE"
                if host == "item.rakuten.co.jp"
                else "NOT_RAKUTEN_ITEM_PAGE"
            )
            skipped.append({"offer_id": offer_id, "reason": reason})
            continue
        item_url, shop, item = parsed
        product = products.get(offer.get("product_id"))
        model = str(offer.get("product_model") or "")
        tokens = _model_tokens(model)
        if (
            product is None
            or not tokens
            or not offer.get("variant")
            or not offer.get("seller_id")
        ):
            skipped.append(
                {"offer_id": offer_id, "reason": "EDITORIAL_IDENTITY_INCOMPLETE"}
            )
            continue
        if not all(strong_title_token(t) for t in tokens):
            skipped.append({"offer_id": offer_id, "reason": "TITLE_TOKEN_TOO_WEAK"})
            continue
        own_text = _squash(model + str(offer.get("variant")))
        reasons = multi_sku_reasons(offer, item)
        entries.append(
            {
                "offer_id": offer_id,
                "product_id": str(offer["product_id"]),
                "exact_model": str(product.get("exact_model") or ""),
                "seller": str(offer.get("seller") or ""),
                "seller_id": str(offer["seller_id"]),
                "variant": str(offer["variant"]),
                "variant_id": offer.get("variant_id")
                if isinstance(offer.get("variant_id"), str)
                else None,
                "merchant_url": str(offer["merchant_url"]),
                "item_code": f"{shop}:{item}",
                "shop_code": shop,
                "item_url": item_url,
                "sku_variant_id": _variant_id_in_url(str(offer["merchant_url"])),
                "multi_sku": bool(reasons),
                "multi_sku_reasons": reasons,
                "required_title_tokens": tokens,
                "forbidden_title_tokens": [
                    t
                    for t in DEFAULT_FORBIDDEN_TITLE_TOKENS
                    if _squash(t) not in own_text
                ],
                "seller_shop_consistent": offer["seller_id"]
                in {f"rakuten-{shop}", f"{shop}-rakuten"},
            }
        )
    plan = {
        "schema": PLAN_SCHEMA,
        "catalog_sha256": catalog_sha256,
        "api": {"endpoint_path": API_PATH, "elements": list(REQUEST_ELEMENTS)},
        "entries": sorted(entries, key=lambda e: e["offer_id"]),
        "skipped": sorted(skipped, key=lambda s: s["offer_id"]),
    }
    validate_plan(plan)
    return plan


@dataclass(frozen=True, slots=True)
class PlanEntry:
    offer_id: str
    product_id: str
    exact_model: str
    seller: str
    seller_id: str
    variant: str
    variant_id: str | None
    merchant_url: str
    item_code: str
    shop_code: str
    item_url: str
    sku_variant_id: str | None
    multi_sku: bool
    multi_sku_reasons: tuple[str, ...]
    required_title_tokens: tuple[str, ...]
    forbidden_title_tokens: tuple[str, ...]
    seller_shop_consistent: bool


def _walk_keys(value: object) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def _strings(
    value: object, *, maximum: int, limit: int, allow_empty: bool
) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or len(value) > limit
        or (not value and not allow_empty)
    ):
        fail("PLAN_ENTRY_INVALID")
    if any(not isinstance(v, str) or not 0 < len(v) <= maximum for v in value):
        fail("PLAN_ENTRY_INVALID")
    return tuple(value)


def validate_plan(plan: object) -> list[PlanEntry]:
    if not isinstance(plan, Mapping) or set(plan) != {
        "schema",
        "catalog_sha256",
        "api",
        "entries",
        "skipped",
    }:
        fail("PLAN_INVALID")
    if any(key in API_VALUE_KEYS for key in _walk_keys(plan)):
        fail("PLAN_CONTAINS_API_VALUE_FIELD")
    if (
        plan["schema"] != PLAN_SCHEMA
        or not isinstance(plan["catalog_sha256"], str)
        or _SHA256.fullmatch(plan["catalog_sha256"]) is None
        or plan["api"]
        != {"endpoint_path": API_PATH, "elements": list(REQUEST_ELEMENTS)}
        or not isinstance(plan["entries"], list)
        or not isinstance(plan["skipped"], list)
    ):
        fail("PLAN_INVALID")
    result: list[PlanEntry] = []
    for raw in plan["entries"]:
        if not isinstance(raw, Mapping) or tuple(sorted(raw)) != tuple(
            sorted(PLAN_ENTRY_KEYS)
        ):
            fail("PLAN_ENTRY_INVALID")
        text_fields = (
            "offer_id",
            "product_id",
            "seller_id",
            "variant",
            "merchant_url",
            "item_code",
            "shop_code",
            "item_url",
        )
        if any(not isinstance(raw[k], str) or not raw[k] for k in text_fields):
            fail("PLAN_ENTRY_INVALID")
        if not isinstance(raw["seller"], str) or not isinstance(
            raw["exact_model"], str
        ):
            fail("PLAN_ENTRY_INVALID")
        parsed = canonical_item_url(raw["merchant_url"])
        sku = _variant_id_in_url(raw["merchant_url"]) if parsed else None
        if (
            parsed is None
            or parsed[0] != raw["item_url"]
            or parsed[1] != raw["shop_code"]
            or f"{parsed[1]}:{parsed[2]}" != raw["item_code"]
            or raw["sku_variant_id"] != sku
            or type(raw["multi_sku"]) is not bool
            or (sku is not None and raw["multi_sku"] is not True)
            or type(raw["seller_shop_consistent"]) is not bool
            or (
                raw["variant_id"] is not None and not isinstance(raw["variant_id"], str)
            )
        ):
            fail("PLAN_ENTRY_BINDING_INVALID")
        reasons = _strings(
            raw["multi_sku_reasons"], maximum=64, limit=8, allow_empty=True
        )
        required = _strings(
            raw["required_title_tokens"], maximum=64, limit=8, allow_empty=False
        )
        if not all(strong_title_token(t) for t in required):
            fail("PLAN_TITLE_TOKEN_WEAK")
        if bool(reasons) and raw["multi_sku"] is not True:
            fail("PLAN_ENTRY_BINDING_INVALID")
        result.append(
            PlanEntry(
                offer_id=raw["offer_id"],
                product_id=raw["product_id"],
                exact_model=raw["exact_model"],
                seller=raw["seller"],
                seller_id=raw["seller_id"],
                variant=raw["variant"],
                variant_id=raw["variant_id"],
                merchant_url=raw["merchant_url"],
                item_code=raw["item_code"],
                shop_code=raw["shop_code"],
                item_url=raw["item_url"],
                sku_variant_id=raw["sku_variant_id"],
                multi_sku=raw["multi_sku"],
                multi_sku_reasons=reasons,
                required_title_tokens=required,
                forbidden_title_tokens=_strings(
                    raw["forbidden_title_tokens"],
                    maximum=64,
                    limit=32,
                    allow_empty=True,
                ),
                seller_shop_consistent=raw["seller_shop_consistent"],
            )
        )
    if len({e.offer_id for e in result}) != len(result):
        fail("PLAN_OFFER_DUPLICATE")
    return result


def request_path(item_code: str, application_id: str) -> str:
    """One itemCode lookup. accessKey travels in a header; affiliateId is never sent."""
    if (
        re.fullmatch(
            r"[A-Za-z0-9._~-]{1,100}:[A-Za-z0-9._~-]{1,200}", item_code, re.ASCII
        )
        is None
    ):
        fail("ITEM_CODE_INVALID")
    pairs = [
        ("applicationId", application_id),
        ("itemCode", item_code),
        ("hits", "1"),
        ("availability", "0"),
        ("format", "json"),
        ("formatVersion", "2"),
        ("elements", ",".join(REQUEST_ELEMENTS)),
    ]
    return API_PATH + "?" + urlencode(pairs, safe="")


# ---------------------------------------------------------------------------
# Response classification
# ---------------------------------------------------------------------------


def _reject_constant(value: str) -> NoReturn:
    fail("RESPONSE_INVALID")


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            fail("RESPONSE_INVALID")
        result[key] = value
    return result


def strict_json(text: str) -> Any:
    try:
        return json.loads(
            text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant
        )
    except (ValueError, RecursionError) as error:
        if isinstance(error, RefreshError):
            raise
        fail("RESPONSE_INVALID")


def _flag(value: object) -> int:
    if type(value) is not int or value not in (0, 1):
        fail("ROW_INVALID")
    return value


def _yen(value: object) -> int:
    if type(value) is not int or not 0 < value <= 1_000_000_000:
        fail("ROW_INVALID")
    return value


def _entry(
    entry: PlanEntry, status: Status, observed_at: datetime, reasons: Sequence[str]
) -> dict[str, Any]:
    return {
        "offer_id": entry.offer_id,
        "item_url": entry.item_url,
        "status": status.value,
        "observed_at": iso(observed_at),
        "cache_expires_at": iso(observed_at + MAX_CACHE_AGE),
        "price_yen": None,
        "tax_included": None,
        "postage_included": None,
        "state": None,
        "reference_price": None,
        "response_row_sha256": None,
        "reasons": list(reasons),
    }


def classify_observation(
    entry: PlanEntry, http_status: int, body: str | None, observed_at: datetime
) -> dict[str, Any]:
    """Map one itemCode response to an overlay entry. 400/401/403 abort the run."""
    if observed_at.tzinfo is None:
        fail("TIMESTAMP_NAIVE")
    if http_status == 400:
        fail("RAKUTEN_WRONG_PARAMETER")
    if http_status in (401, 403):
        fail("RAKUTEN_AUTH_REJECTED")
    if http_status == 404:
        return {
            **_entry(entry, Status.NOT_FOUND_PENDING, observed_at, ["HTTP_404"]),
            "state": "UNKNOWN",
        }
    if http_status != 200:
        code = "TRANSPORT_FAILED" if http_status == 0 else f"HTTP_{http_status}"
        return _entry(entry, Status.REQUEST_FAILED, observed_at, [code])
    if body is None:
        return _entry(
            entry, Status.REQUEST_FAILED, observed_at, ["RESPONSE_BODY_MISSING"]
        )
    try:
        document = strict_json(body)
        items = document.get("items") if isinstance(document, Mapping) else None
        if not isinstance(items, list):
            fail("RESPONSE_INVALID")
        if not items:
            return {
                **_entry(entry, Status.NOT_FOUND_PENDING, observed_at, ["ZERO_HITS"]),
                "state": "UNKNOWN",
            }
        if len(items) != 1:
            return _entry(
                entry, Status.IDENTITY_MISMATCH, observed_at, ["MULTIPLE_ROWS"]
            )
        row = items[0]
        if not isinstance(row, Mapping):
            fail("ROW_INVALID")
        texts = [row.get(k) for k in ("itemCode", "shopCode", "itemUrl", "itemName")]
        if any(not isinstance(t, str) or not t for t in texts):
            fail("ROW_INVALID")
        price = _yen(row.get("itemPrice"))
        low = row.get("itemPriceMin3")
        high = row.get("itemPriceMax3")
        low_all = row.get("itemPriceMin1")
        high_all = row.get("itemPriceMax1")
        availability = _flag(row.get("availability"))
        tax_flag = _flag(row.get("taxFlag"))
        postage_flag = _flag(row.get("postageFlag"))
    except RefreshError as error:
        return _entry(entry, Status.REQUEST_FAILED, observed_at, [error.code])
    row_sha = sha256_hex(canonical_json(row).encode("utf-8"))
    title = str(row["itemName"])
    reasons = []
    if row["itemCode"] != entry.item_code:
        reasons.append("ITEM_CODE_MISMATCH")
    if row["shopCode"] != entry.shop_code:
        reasons.append("SHOP_CODE_MISMATCH")
    returned = canonical_item_url(row["itemUrl"])
    if returned is None or returned[0] != entry.item_url:
        reasons.append("ITEM_URL_MISMATCH")
    if not all(title_has_token(title, t) for t in entry.required_title_tokens):
        reasons.append("TITLE_TOKEN_MISSING")
    if any(title_has_token(title, t) for t in entry.forbidden_title_tokens):
        reasons.append("TITLE_FORBIDDEN_TOKEN")
    if not entry.seller_shop_consistent:
        reasons.append("SELLER_SHOP_INCONSISTENT")
    own_colors = color_groups(entry.variant + " " + entry.exact_model, editorial=True)
    title_colors = color_groups(title, editorial=False)
    other_colors = title_colors - own_colors
    if own_colors and other_colors and not own_colors & title_colors:
        reasons.append("TITLE_COLOR_CONFLICT")
    if reasons:
        return {
            **_entry(entry, Status.IDENTITY_MISMATCH, observed_at, reasons),
            "response_row_sha256": row_sha,
        }
    # The API has no SKU fields: a page is priced only when nothing suggests another SKU.
    why = list(entry.multi_sku_reasons) if entry.multi_sku else []
    if entry.multi_sku and not why:
        why.append("PLAN_MULTI_SKU")
    normalized_title = unicodedata.normalize("NFKC", title)
    if other_colors and (
        own_colors & title_colors or (not own_colors and len(title_colors) > 1)
    ):
        why.append("TITLE_LISTS_OTHER_COLORS")
    if _TITLE_MULTI_VARIANT.search(normalized_title):
        why.append("TITLE_MULTI_VARIANT")
    if _TITLE_QUANTITY.search(normalized_title):
        why.append("TITLE_QUANTITY_PACK")
    if not (type(low) is int and type(high) is int and low == high == price):
        why.append("PURCHASABLE_PRICE_RANGE")
    if not (
        type(low_all) is int and type(high_all) is int and low_all == high_all == price
    ):
        why.append("ALL_SKU_PRICE_RANGE")
    if why:
        return {
            **_entry(entry, Status.MULTI_SKU_NO_PRICE, observed_at, why),
            "state": "UNKNOWN",
            "response_row_sha256": row_sha,
        }
    if availability == 0:
        return {
            **_entry(entry, Status.SOLD_OUT, observed_at, ["AVAILABILITY_0"]),
            "state": "SOLD_OUT",
            "response_row_sha256": row_sha,
        }
    result = {
        **_entry(entry, Status.MATCHED, observed_at, []),
        "price_yen": price,
        "tax_included": tax_flag == 0,
        "postage_included": postage_flag == 0,
        "state": "AVAILABLE",
        "response_row_sha256": row_sha,
    }
    if tax_flag == 0 and entry.variant_id and entry.exact_model and entry.seller:
        result["reference_price"] = {
            "schema": "RAOS_REFERENCE_PRICE_V1",
            "verified": True,
            "product_id": entry.product_id,
            "exact_model": entry.exact_model,
            "variant": entry.variant,
            "variant_id": entry.variant_id,
            "amount_yen": price,
            "currency": "JPY",
            "tax_included": True,
            "scope": "base_unit",
            "pricing_basis": "listed_sale_price",
            "source_url": entry.merchant_url,
            "source_locator": "楽天市場商品検索API（2026-07-01版）itemPrice／itemCode "
            + entry.item_code,
            "evidence_sha256": row_sha,
            "checked_at": result["observed_at"],
            "valid_until": result["cache_expires_at"],
            "seller": entry.seller,
            "seller_id": entry.seller_id,
        }
    return result


# ---------------------------------------------------------------------------
# Overlay
# ---------------------------------------------------------------------------

OVERLAY_KEYS: Final = frozenset(
    {
        "schema",
        "run_id",
        "plan_sha256",
        "api_version",
        "created_at",
        "cache_expires_at",
        "entries",
    }
)
ENTRY_KEYS: Final = frozenset(
    {
        "offer_id",
        "item_url",
        "status",
        "observed_at",
        "cache_expires_at",
        "price_yen",
        "tax_included",
        "postage_included",
        "state",
        "reference_price",
        "response_row_sha256",
        "reasons",
    }
)


def carries_values(entry: Mapping[str, Any]) -> bool:
    return any(
        entry.get(k) is not None
        for k in ("price_yen", "tax_included", "state", "reference_price")
    )


def build_overlay(
    run_id: str,
    plan_sha256: str,
    entries: Sequence[Mapping[str, Any]],
    created_at: datetime,
) -> dict[str, Any]:
    require_run_id(run_id)
    if not entries:
        fail("OVERLAY_EMPTY")
    for entry in entries:
        observed = parse_time(entry["observed_at"])
        if observed > created_at or created_at - observed >= MAX_CACHE_AGE:
            fail("OBSERVATION_OUTSIDE_CACHE_WINDOW")
    overlay = {
        "schema": OVERLAY_SCHEMA,
        "run_id": run_id,
        "plan_sha256": plan_sha256,
        "api_version": API_VERSION_ID,
        "created_at": iso(created_at),
        "cache_expires_at": min(str(e["cache_expires_at"]) for e in entries),
        "entries": sorted((dict(e) for e in entries), key=lambda e: str(e["offer_id"])),
    }
    overlay["cache_expires_at"] = iso(
        min(parse_time(e["cache_expires_at"]) for e in entries)
    )
    validate_overlay(overlay)
    return overlay


def validate_overlay(overlay: object) -> list[dict[str, Any]]:
    """Structural validation. Missing tax_included is left for the gate to refuse."""
    if (
        not isinstance(overlay, Mapping)
        or set(overlay) != OVERLAY_KEYS
        or overlay["schema"] != OVERLAY_SCHEMA
    ):
        fail("OVERLAY_INVALID")
    require_run_id(overlay["run_id"])
    if (
        not isinstance(overlay["plan_sha256"], str)
        or _SHA256.fullmatch(overlay["plan_sha256"]) is None
        or overlay["api_version"] != API_VERSION_ID
        or not isinstance(overlay["entries"], list)
        or not overlay["entries"]
    ):
        fail("OVERLAY_INVALID")
    parse_time(overlay["created_at"])
    expiries = []
    seen = set()
    for entry in overlay["entries"]:
        if not isinstance(entry, Mapping) or set(entry) != ENTRY_KEYS:
            fail("OVERLAY_ENTRY_INVALID")
        if entry["offer_id"] in seen or not isinstance(entry["offer_id"], str):
            fail("OVERLAY_ENTRY_INVALID")
        seen.add(entry["offer_id"])
        bound = canonical_item_url(entry["item_url"])
        if bound is None or bound[0] != entry["item_url"]:
            fail("OVERLAY_ENTRY_INVALID")
        try:
            status = Status(entry["status"])
        except ValueError:
            fail("OVERLAY_ENTRY_INVALID")
        observed, expires = (
            parse_time(entry["observed_at"]),
            parse_time(entry["cache_expires_at"]),
        )
        if not observed < expires <= observed + MAX_CACHE_AGE:
            fail("OVERLAY_CACHE_WINDOW_INVALID")
        expiries.append(expires)
        price, state, tax = entry["price_yen"], entry["state"], entry["tax_included"]
        if price is not None and (
            type(price) is not int or not 0 < price <= 1_000_000_000
        ):
            fail("OVERLAY_ENTRY_INVALID")
        if tax is not None and type(tax) is not bool:
            fail("OVERLAY_ENTRY_INVALID")
        if state is not None and state not in VALUE_STATES:
            fail("OVERLAY_ENTRY_INVALID")
        allowed_states: dict[Status, set[str | None]] = {
            Status.MATCHED: {"AVAILABLE"},
            Status.SOLD_OUT: {"SOLD_OUT"},
            Status.MULTI_SKU_NO_PRICE: {"UNKNOWN"},
            Status.NOT_FOUND_PENDING: {"UNKNOWN"},
            Status.IDENTITY_MISMATCH: {None},
            Status.REQUEST_FAILED: {None},
        }
        if state not in allowed_states[status]:
            fail("OVERLAY_STATUS_STATE_MISMATCH")
        if status is not Status.MATCHED and (
            price is not None or tax is not None or entry["reference_price"] is not None
        ):
            fail("OVERLAY_PRICE_WITHOUT_MATCH")
        if status is Status.MATCHED and price is None:
            fail("OVERLAY_ENTRY_INVALID")
        ref = entry["reference_price"]
        if ref is not None and (
            not isinstance(ref, Mapping)
            or ref.get("amount_yen") != price
            or ref.get("tax_included") is not True
            or tax is not True
            or ref.get("evidence_sha256") != entry["response_row_sha256"]
        ):
            fail("OVERLAY_REFERENCE_INVALID")
        row_sha = entry["response_row_sha256"]
        if row_sha is not None and (
            not isinstance(row_sha, str) or _SHA256.fullmatch(row_sha) is None
        ):
            fail("OVERLAY_ENTRY_INVALID")
        if not isinstance(entry["reasons"], list) or any(
            not isinstance(r, str) for r in entry["reasons"]
        ):
            fail("OVERLAY_ENTRY_INVALID")
    if parse_time(overlay["cache_expires_at"]) != min(expiries):
        fail("OVERLAY_CACHE_WINDOW_INVALID")
    return [dict(e) for e in overlay["entries"]]


# ---------------------------------------------------------------------------
# Injection into price-free bodies (reference implementation for the publisher)
# ---------------------------------------------------------------------------

_SELLER_TAG: Final = re.compile(r'<div class="ps-seller"(?P<attrs>[^>]*)>')
_PRICE_DATE_TIME: Final = re.compile(
    r'(<p class="ps-price-date">販売条件確認：<time datetime=")[^"]*(">)[^<]*(</time>)'
)
_REFERENCE_PLACEHOLDER: Final = (
    '<p class="ps-reference-price" role="status">価格は販売先で確認</p>'
)


def _set_attr(attributes: str, name: str, value: str) -> str:
    rendered = f' {name}="{escape(value, quote=True)}"'
    pattern = re.compile(r"\s" + re.escape(name) + r'="[^"]*"')
    if pattern.search(attributes):
        return pattern.sub(lambda _m: rendered, attributes, count=1)
    return attributes + rendered


def _has_attr(attributes: str, name: str, value: str | None = None) -> bool:
    if value is None:
        return re.search(r"\s" + re.escape(name) + r'="', attributes) is not None
    return f' {name}="{escape(value, quote=True)}"' in attributes


@dataclass(frozen=True, slots=True)
class InjectionResult:
    body: str
    seller_offer_ids: tuple[str, ...]
    reference_offer_ids: tuple[str, ...]


def inject_body(body: str, overlay: Mapping[str, Any]) -> InjectionResult:
    """Inject overlay values into one price-free body. Unknown targets are left untouched."""
    entries = {e["offer_id"]: e for e in validate_overlay(overlay) if carries_values(e)}
    run_id = str(overlay["run_id"])
    if _has_attr(body, ATTR_OVERLAY_RUN) or _has_attr(body, ATTR_PRICE_SOURCE):
        fail("BODY_ALREADY_INJECTED")
    sellers: set[str] = set()
    parts: list[str] = []
    cursor = 0
    for match in _SELLER_TAG.finditer(body):
        attributes = match.group("attrs")
        offer = re.search(r' data-ps-offer="([^"]*)"', attributes)
        entry = entries.get(unescape(offer.group(1))) if offer else None
        if entry is None:
            continue
        if _has_attr(attributes, ATTR_PRICE_YEN) or _has_attr(
            attributes, ATTR_TAX_INCLUDED
        ):
            fail("BODY_PRICE_CONFLICT")
        observed = parse_time(entry["observed_at"])
        attributes = _set_attr(attributes, _PS + "checked-at", entry["observed_at"])
        attributes = _set_attr(
            attributes, _PS + "valid-until", entry["cache_expires_at"]
        )
        state = entry["state"]
        attributes = _set_attr(attributes, _PS + "state", state)
        if _has_attr(attributes, _PS + "purchasability-state"):
            attributes = _set_attr(attributes, _PS + "purchasability-state", state)
        if entry["price_yen"] is not None:
            attributes = _set_attr(attributes, ATTR_PRICE_YEN, str(entry["price_yen"]))
            if entry["tax_included"] is not None:
                attributes = _set_attr(
                    attributes, ATTR_TAX_INCLUDED, str(entry["tax_included"]).lower()
                )
        attributes = _set_attr(attributes, ATTR_PRICE_SOURCE, API_VERSION_ID)
        attributes = _set_attr(attributes, ATTR_OVERLAY_RUN, run_id)
        block_end = body.find("</div>", match.end())
        if block_end < 0:
            fail("BODY_SELLER_BLOCK_UNTERMINATED")
        block = body[match.end() : block_end]
        stamp = escape(str(entry["observed_at"]), quote=True)
        label = escape(jp_datetime(observed) + "（日本時間）")
        block, count = _PRICE_DATE_TIME.subn(
            lambda m: m.group(1) + stamp + m.group(2) + label + m.group(3),
            block,
            count=1,
        )
        if count != 1:
            fail("BODY_PRICE_DATE_MISSING")
        parts.append(body[cursor : match.start()])
        parts.append('<div class="ps-seller"' + attributes + ">" + block)
        cursor = block_end
        sellers.add(entry["offer_id"])
    parts.append(body[cursor:])
    injected = "".join(parts)
    references: set[str] = set()
    for offer_id, entry in entries.items():
        ref = entry["reference_price"]
        if ref is None:
            continue
        payload = (
            f' {ATTR_REFERENCE_PRICE}="{escape(canonical_json(ref), quote=True)}"'
            f' {ATTR_OVERLAY_RUN}="{escape(run_id, quote=True)}"'
        )
        explicit = f'<p class="ps-reference-price" role="status" {ATTR_REFERENCE_OFFER}="{escape(offer_id, quote=True)}">'
        adjacent = re.compile(
            re.escape(_REFERENCE_PLACEHOLDER)
            + r'(?=<p><a class="ps-offer-link"[^>]*\sdata-raos-offer-id="'
            + re.escape(escape(offer_id, quote=True))
            + '")'
        )
        if explicit in injected:
            injected = injected.replace(explicit, explicit[:-1] + payload + ">")
            references.add(offer_id)
        injected, count = adjacent.subn(
            lambda _m: (
                '<p class="ps-reference-price" role="status"'
                + payload
                + ">価格は販売先で確認</p>"
            ),
            injected,
        )
        if count:
            references.add(offer_id)
    return InjectionResult(injected, tuple(sorted(sellers)), tuple(sorted(references)))


def body_sha256(body: str) -> str:
    """Hash compared by inc/purchase-support.php against post_content (UTF-8 bytes)."""
    return sha256_hex(body.encode("utf-8"))


def serialize_runtime(runtime: Mapping[str, Any]) -> bytes:
    """Byte-identical to scripts/build_reader_purchase_support_v1.py output."""
    return (json.dumps(runtime, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def inject_runtime(
    runtime_bytes: bytes, injected_bodies: Mapping[str, str]
) -> tuple[bytes, str]:
    """Rebind body_sha256 for injected slugs; return (runtime bytes, runtime sha256)."""
    runtime = json.loads(runtime_bytes.decode("utf-8"))
    if (
        not isinstance(runtime, dict)
        or runtime.get("schema") != "RAOS_PURCHASE_ARTICLE_RUNTIME_V1"
        or serialize_runtime(runtime) != runtime_bytes
    ):
        fail("RUNTIME_NOT_CANONICAL")
    slugs = [a.get("slug") for a in runtime.get("articles", []) if isinstance(a, dict)]
    for slug, body in injected_bodies.items():
        if slugs.count(slug) != 1:
            fail("RUNTIME_SLUG_UNBOUND")
        for article in runtime["articles"]:
            if isinstance(article, dict) and article.get("slug") == slug:
                article["body_sha256"] = body_sha256(body)
    payload = serialize_runtime(runtime)
    return payload, sha256_hex(payload)


def rebind_runtime_constant(functions_php: str, runtime_sha256: str) -> str:
    if _SHA256.fullmatch(runtime_sha256) is None:
        fail("RUNTIME_SHA256_INVALID")
    pattern = re.compile(
        r"(^const KURASHINOSHIRUBE_PURCHASE_RUNTIME_SHA256 = ')[0-9a-f]{64}(';$)", re.M
    )
    result, count = pattern.subn(
        lambda m: m.group(1) + runtime_sha256 + m.group(2), functions_php
    )
    if count != 1:
        fail("RUNTIME_CONSTANT_NOT_UNIQUE")
    return result


def price_free_violations(body: str, overlay: Mapping[str, Any]) -> list[str]:
    """Codes proving a body still carries this overlay (used after the purge publish)."""
    codes = []
    run_id = str(overlay["run_id"])
    if f'{ATTR_OVERLAY_RUN}="{escape(run_id, quote=True)}"' in body:
        codes.append("OVERLAY_RUN_MARKER")
    if f'{ATTR_PRICE_SOURCE}="{API_VERSION_ID}"' in body:
        codes.append("API_PRICE_SOURCE_MARKER")
    for entry in overlay.get("entries", []):
        if not isinstance(entry, Mapping):
            continue
        for key in ("observed_at", "cache_expires_at", "response_row_sha256"):
            value = entry.get(key)
            if isinstance(value, str) and value in body:
                codes.append("OVERLAY_" + key.upper())
    return sorted(set(codes))


# ---------------------------------------------------------------------------
# Approval unit: one fetch + one publish + one purge publish before expiry
# ---------------------------------------------------------------------------


def new_approval(run_id: str, plan_sha256: str, now: datetime) -> dict[str, Any]:
    require_run_id(run_id)
    if _SHA256.fullmatch(plan_sha256) is None:
        fail("PLAN_SHA256_INVALID")
    return {
        "schema": APPROVAL_SCHEMA,
        "run_id": run_id,
        "approval_flag": "--owner-approved-run",
        "scope": ["fetch", "publish", "purge_publish_before_expiry"],
        "plan_sha256": plan_sha256,
        "approved_at": iso(now),
        "fetch_deadline": iso(now + MAX_CACHE_AGE),
        "cache_expires_at": None,
        "publish": None,
        "purge_publish": None,
    }


def validate_approval(approval: object, run_id: str) -> dict[str, Any]:
    keys = {
        "schema",
        "run_id",
        "approval_flag",
        "scope",
        "plan_sha256",
        "approved_at",
        "fetch_deadline",
        "cache_expires_at",
        "publish",
        "purge_publish",
    }
    if (
        not isinstance(approval, Mapping)
        or set(approval) != keys
        or approval["schema"] != APPROVAL_SCHEMA
    ):
        fail("APPROVAL_INVALID")
    if approval["run_id"] != run_id:
        fail("APPROVAL_RUN_MISMATCH")
    return dict(approval)


def record_publish(
    approval: Mapping[str, Any],
    overlay: Mapping[str, Any],
    *,
    candidate_id: str,
    article_keys: Sequence[str],
    injected_body_sha256: Mapping[str, str],
    runtime_sha256: str,
    now: datetime,
) -> dict[str, Any]:
    record = validate_approval(approval, str(overlay.get("run_id")))
    validate_overlay(overlay)
    if record["publish"] is not None:
        fail("APPROVAL_PUBLISH_ALREADY_USED")
    if parse_time(overlay["cache_expires_at"]) - now < GATE_MIN_REMAINING:
        fail("OVERLAY_VALUE_EXPIRING")
    hashes = [candidate_id, runtime_sha256, *injected_body_sha256.values()]
    if any(not isinstance(h, str) or _SHA256.fullmatch(h) is None for h in hashes):
        fail("PUBLISH_RECORD_INVALID")
    record["cache_expires_at"] = overlay["cache_expires_at"]
    record["publish"] = {
        "candidate_id": candidate_id,
        "published_at": iso(now),
        "article_keys": sorted(article_keys),
        "injected_body_sha256": dict(sorted(injected_body_sha256.items())),
        "runtime_sha256": runtime_sha256,
        "purge_publish_due_by": overlay["cache_expires_at"],
    }
    return record


def record_purge_publish(
    approval: Mapping[str, Any], *, candidate_id: str, now: datetime
) -> dict[str, Any]:
    record = validate_approval(approval, str(approval.get("run_id")))
    if record["publish"] is None:
        fail("APPROVAL_PURGE_WITHOUT_PUBLISH")
    if record["purge_publish"] is not None:
        fail("APPROVAL_PURGE_ALREADY_USED")
    if _SHA256.fullmatch(candidate_id) is None:
        fail("PUBLISH_RECORD_INVALID")
    due = parse_time(record["publish"]["purge_publish_due_by"])
    record["purge_publish"] = {
        "candidate_id": candidate_id,
        "published_at": iso(now),
        "before_expiry": now < due,
    }
    return record


def redact_approval(approval: Mapping[str, Any]) -> dict[str, Any]:
    """Drop injected hashes (price-recoverable by brute force) once values are purged."""
    record = dict(approval)
    if isinstance(record.get("publish"), Mapping):
        publish = dict(record["publish"])
        publish["injected_body_sha256"] = {
            k: "PURGED" for k in publish.get("injected_body_sha256", {})
        }
        publish["runtime_sha256"] = "PURGED"
        if "candidate_id" in publish:
            # The candidate hash covers the injected bodies, so it is price-recoverable too.
            publish["candidate_id"] = "PURGED"
        record["publish"] = publish
    return record


# ---------------------------------------------------------------------------
# Gate (immediately before the publish that carries overlay values)
# ---------------------------------------------------------------------------


_OFFER_LINK_TAG: Final = re.compile(r'<a class="ps-offer-link"(?P<attrs>[^>]*)>')
_ANY_LINK_TAG: Final = re.compile(r"<a\s(?P<attrs>[^>]*)>")
_HREF_ATTR: Final = re.compile(r'(?:^|\s)href="([^"]*)"')


def offer_cta_targets(body: str, offer_id: str) -> list[str | None]:
    """Canonical item page of every ``ps-offer-link`` CTA bound to the offer (None: not an item page)."""
    marker = f' data-raos-offer-id="{escape(offer_id, quote=True)}"'
    targets: list[str | None] = []
    for tag in _OFFER_LINK_TAG.finditer(body):
        attributes = tag.group("attrs")
        if marker in attributes:
            href = _HREF_ATTR.search(attributes)
            targets.append(link_item_url(href.group(1)) if href else None)
    return targets


def linked_item_urls(body: str) -> set[str]:
    """Canonical item pages linked from any anchor, with or without the CTA class."""
    found = set()
    for tag in _ANY_LINK_TAG.finditer(body):
        href = _HREF_ATTR.search(tag.group("attrs"))
        target = link_item_url(href.group(1)) if href else None
        if target is not None:
            found.add(target)
    return found


@dataclass(frozen=True, slots=True)
class GateFinding:
    code: str
    subject: str


def leak_needles(
    overlay: Mapping[str, Any], approval: Mapping[str, Any] | None = None
) -> list[str]:
    """Exact strings whose presence in a tracked file proves an overlay leak."""
    needles = {f'{ATTR_OVERLAY_RUN}="{overlay["run_id"]}"'}
    for entry in overlay.get("entries", []):
        if not isinstance(entry, Mapping) or not carries_values(entry):
            continue
        for key in ("observed_at", "cache_expires_at", "response_row_sha256"):
            if isinstance(entry.get(key), str):
                needles.add(entry[key])
    publish = approval.get("publish") if approval else None
    if isinstance(publish, Mapping):
        for value in [
            publish.get("candidate_id"),
            publish.get("runtime_sha256"),
            *dict(publish.get("injected_body_sha256") or {}).values(),
        ]:
            if isinstance(value, str) and _SHA256.fullmatch(value):
                needles.add(value)
    return sorted(needles)


def contextual_leaks(text: str, overlay: Mapping[str, Any]) -> list[str]:
    """Price values of overlay offers written into tracked HTML attributes or JSON fields."""
    codes: set[str] = set()
    for entry in overlay.get("entries", []):
        if not isinstance(entry, Mapping) or entry.get("price_yen") is None:
            continue
        offer = escape(str(entry["offer_id"]), quote=True)
        if f'data-ps-offer="{offer}"' in text:
            for tag in _SELLER_TAG.finditer(text):
                attributes = tag.group("attrs")
                if (
                    f' data-ps-offer="{offer}"' in attributes
                    and f' {ATTR_PRICE_YEN}="{entry["price_yen"]}"' in attributes
                ):
                    codes.add("PRICE_ATTRIBUTE")
        if f'"{entry["offer_id"]}"' in text:
            try:
                document = json.loads(text)
            except ValueError:
                continue
            stack: list[Any] = [document]
            while stack:
                node = stack.pop()
                if isinstance(node, Mapping):
                    if (
                        node.get("offer_id") == entry["offer_id"]
                        and node.get("price_yen") == entry["price_yen"]
                    ):
                        codes.add("PRICE_JSON_FIELD")
                    stack.extend(node.values())
                elif isinstance(node, list):
                    stack.extend(node)
    return sorted(codes)


def gate(
    overlay: Mapping[str, Any],
    *,
    now: datetime,
    bodies: Mapping[str, str],
    tracked_leaks: Sequence[str],
    approval: Mapping[str, Any] | None,
) -> list[GateFinding]:
    findings: list[GateFinding] = []
    if now.tzinfo is None:
        fail("TIMESTAMP_NAIVE")
    try:
        entries = validate_overlay(overlay)
    except RefreshError as error:
        return [GateFinding("OVERLAY_INVALID", error.code)]
    run_id = str(overlay["run_id"])
    if approval is None:
        findings.append(GateFinding("APPROVAL_MISSING", run_id))
    else:
        try:
            record = validate_approval(approval, run_id)
            if record["plan_sha256"] != overlay["plan_sha256"]:
                findings.append(GateFinding("APPROVAL_PLAN_MISMATCH", run_id))
            if record["publish"] is not None:
                findings.append(GateFinding("APPROVAL_PUBLISH_ALREADY_USED", run_id))
        except RefreshError as error:
            findings.append(GateFinding(error.code, run_id))
    if not bodies:
        findings.append(GateFinding("BODIES_REQUIRED", run_id))
    for entry in entries:
        offer_id = entry["offer_id"]
        if carries_values(entry):
            observed, expires = (
                parse_time(entry["observed_at"]),
                parse_time(entry["cache_expires_at"]),
            )
            if observed > now:
                findings.append(GateFinding("OVERLAY_OBSERVED_IN_FUTURE", offer_id))
            if now - observed > MAX_CACHE_AGE:
                findings.append(GateFinding("OVERLAY_VALUE_OLDER_THAN_24H", offer_id))
            if expires - now < GATE_MIN_REMAINING:
                findings.append(GateFinding("OVERLAY_VALUE_EXPIRING", offer_id))
        if entry["price_yen"] is not None and type(entry["tax_included"]) is not bool:
            findings.append(GateFinding("TAX_INCLUDED_MISSING", offer_id))
        if entry["price_yen"] is not None and entry["tax_included"] is False:
            # The theme labels every price as tax-included until batch G adds the distinction.
            findings.append(GateFinding("TAX_EXCLUDED_PRICE_UNSUPPORTED", offer_id))
        escaped = escape(offer_id, quote=True)
        for key, body in bodies.items():
            ctas = offer_cta_targets(body, offer_id)
            if entry["status"] == Status.IDENTITY_MISMATCH.value and (
                ctas or entry["item_url"] in linked_item_urls(body)
            ):
                findings.append(
                    GateFinding("IDENTITY_MISMATCH_WITH_CTA", f"{key}:{offer_id}")
                )
            if not carries_values(entry):
                continue
            targeted = (
                f'data-ps-offer="{escaped}"' in body
                or f'data-raos-offer-id="{escaped}"' in body
            )
            if targeted:
                # Values were observed for the plan's item page; the CTA must still lead there.
                if not ctas:
                    findings.append(
                        GateFinding("CTA_TARGET_UNVERIFIED", f"{key}:{offer_id}")
                    )
                elif any(target != entry["item_url"] for target in ctas):
                    findings.append(
                        GateFinding("CTA_TARGET_MISMATCH", f"{key}:{offer_id}")
                    )
                for tag in _SELLER_TAG.finditer(body):
                    attributes = tag.group("attrs")
                    if f' data-ps-offer="{escaped}"' not in attributes:
                        continue
                    if _has_attr(attributes, ATTR_PRICE_YEN) or _has_attr(
                        attributes, ATTR_TAX_INCLUDED
                    ):
                        findings.append(
                            GateFinding("BODY_NOT_PRICE_FREE", f"{key}:{offer_id}")
                        )
                    block_end = body.find("</div>", tag.end())
                    block = body[tag.end() : block_end if block_end >= 0 else len(body)]
                    price_date = _PRICE_DATE_PARAGRAPH.search(block)
                    if (
                        price_date is None
                        or f'href="{DISCLAIMER_HREF}"' not in price_date.group(0)
                    ):
                        findings.append(
                            GateFinding(
                                "RAKUTEN_PRICE_DISCLAIMER_MISSING", f"{key}:{offer_id}"
                            )
                        )
                if f'href="{DISCLAIMER_HREF}"' not in body:
                    findings.append(
                        GateFinding("RAKUTEN_PRICE_DISCLAIMER_MISSING", key)
                    )
                if _RAKUTEN_CREDIT.search(body) is None:
                    findings.append(GateFinding("RAKUTEN_CREDIT_MISSING", key))
    for key, body in bodies.items():
        if price_free_violations(body, overlay) or _has_attr(body, ATTR_PRICE_SOURCE):
            findings.append(GateFinding("BODY_ALREADY_INJECTED", key))
    findings.extend(
        GateFinding("GIT_TRACKED_OVERLAY_VALUE", path) for path in tracked_leaks
    )
    unique = {(f.code, f.subject): f for f in findings}
    return [unique[k] for k in sorted(unique)]
