"""Explicit, existing-content-only publication scope; never a full-mode fallback.

This module is pure: callers provide revalidated official/provider evidence and
the current MCP inventory. A manifest describes a scope, not permission to write.
Raw evidence, URLs and live backups belong in the owner-private workflow.
The immutable audit subject can remain reviewable for at most 24 hours. It is
not an activation receipt: every new apply separately requires the release
adapter's revalidated, at-most-15-minute activation envelope and owner approval.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
import re
from types import MappingProxyType
from typing import NoReturn, cast
from urllib.parse import urlsplit

PROFILE = "verified-incremental"
SCHEMA = "RAOS_WORDPRESS_VERIFIED_INCREMENTAL_MANIFEST_V1"
AUDIT_SUBJECT_MAX_AGE = timedelta(hours=24)
HASH = re.compile(r"[0-9a-f]{64}\Z")
HTML_ASCII_WHITESPACE = "\t\n\f\r "
_RAW_HTML_ATTRIBUTES = re.compile(
    r"""([^\t\n\f\r /=>]+)(?:[\t\n\f\r ]*=[\t\n\f\r ]*(?:"([^"]*)"|'([^']*)'|([^\t\n\f\r >]*)))?"""
)
VOID = frozenset(
    "area base br col embed hr img input link meta param source track wbr".split()
)
# The article is an HTML fragment, not a foreign-content/XML or executable
# document. HTML diagrams use figure/div/table/text; no inline SVG is needed.
# picture/source remain parseable so commerce validation can reject responsive
# alternatives with its existing, specific evidence error.
ARTICLE_HTML_TAGS = frozenset(
    "a abbr address article aside b bdi bdo blockquote br caption cite code col "
    "colgroup data dd del details dfn div dl dt em figcaption figure footer "
    "h1 h2 h3 h4 h5 h6 header hgroup hr i img ins kbd li main mark nav ol p "
    "picture pre q rp rt ruby s samp section small source span strong sub "
    "summary sup table tbody td tfoot th thead time tr u ul var wbr".split()
)
# Article attributes are a closed surface. CSS/background/ping and alternate
# resource hooks have no evidence contract; do not try to sanitize CSS escapes.
ARTICLE_GLOBAL_ATTRIBUTES = frozenset(
    "class id title lang dir role hidden inert tabindex".split()
)
ARTICLE_TAG_ATTRIBUTES = {
    "a": frozenset("href rel target hreflang type referrerpolicy".split()),
    "img": frozenset(
        "src alt width height loading decoding fetchpriority crossorigin "
        "referrerpolicy srcset sizes".split()
    ),
    "source": frozenset("src srcset sizes media type width height".split()),
    "table": frozenset("width height border cellpadding cellspacing".split()),
    "col": frozenset("span width".split()),
    "colgroup": frozenset("span width".split()),
    "td": frozenset("colspan rowspan headers width height".split()),
    "th": frozenset("colspan rowspan headers scope abbr width height".split()),
    "ol": frozenset("start reversed type".split()),
    "li": frozenset({"value"}),
    "time": frozenset({"datetime"}),
    "data": frozenset({"value"}),
    "del": frozenset({"datetime"}),
    "ins": frozenset({"datetime"}),
    "details": frozenset("open name".split()),
}
TABLE_CHILDREN = {
    "table": frozenset("caption colgroup col thead tbody tfoot tr".split()),
    "thead": frozenset({"tr"}),
    "tbody": frozenset({"tr"}),
    "tfoot": frozenset({"tr"}),
    "tr": frozenset({"td", "th"}),
    "colgroup": frozenset({"col"}),
}
TABLE_PARENTS = {
    "caption": frozenset({"table"}),
    "colgroup": frozenset({"table"}),
    "col": frozenset({"table", "colgroup"}),
    "thead": frozenset({"table"}),
    "tbody": frozenset({"table"}),
    "tfoot": frozenset({"table"}),
    "tr": frozenset("table thead tbody tfoot".split()),
    "td": frozenset({"tr"}),
    "th": frozenset({"tr"}),
}
PHRASING_TAGS = frozenset(
    "a abbr b bdi bdo br cite code data del dfn em i img ins kbd mark picture "
    "q rp rt ruby s samp small source span strong sub sup time u var wbr".split()
)
HEADING_TAGS = frozenset("h1 h2 h3 h4 h5 h6".split())
PURCHASE_CLASSES = frozenset(
    {
        "final-summary-action",
        "product-purchase-action",
        "raos-product-card__actions",
        "summary-action",
        "raos-cta",
        "rakuten-cta",
        "official-product-link",
    }
)
PURCHASE_HOSTS = frozenset(
    {
        "item.rakuten.co.jp",
        "basket.step.rakuten.co.jp",
        "search.rakuten.co.jp",
        "books.rakuten.co.jp",
        "kobo.rakuten.co.jp",
        "ichiba.rakuten.co.jp",
    }
)


class IncrementalPublicationFailure(ValueError):
    """Stable errors contain no private document or provider content."""


def fail(reason: str) -> NoReturn:
    raise IncrementalPublicationFailure(f"RAOS_INCREMENTAL_{reason}")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode()


def _mapping(value: object, reason: str = "FIELDS_INVALID") -> dict[str, object]:
    if type(value) is not dict:
        fail(reason)
    raw = cast(dict[object, object], value)
    if any(type(key) is not str for key in raw):
        fail(reason)
    return cast(dict[str, object], raw)


def _object(value: object, fields: set[str]) -> dict[str, object]:
    result = _mapping(value)
    if set(result) != fields:
        fail("FIELDS_INVALID")
    return result


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or value.strip() != value:
        fail("TEXT_INVALID")
    return value


def _hash(value: object) -> str:
    result = _text(value)
    if HASH.fullmatch(result) is None:
        fail("HASH_INVALID")
    return result


def _strings(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        fail("SET_INVALID")
    result = tuple(_text(item) for item in cast(list[object], value))
    if len(set(result)) != len(result) or list(result) != sorted(result):
        fail("SET_INVALID")
    return result


def _instant(value: object) -> datetime:
    raw = _text(value)
    try:
        result = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        fail("TIME_INVALID")
    if result.strftime("%Y-%m-%dT%H:%M:%SZ") != raw:
        fail("TIME_INVALID")
    return result


def validate_hash(value: object) -> str:
    """Validate the shared lowercase SHA-256 representation."""
    return _hash(value)


def validate_text(value: object) -> str:
    """Validate nonempty text without silently normalizing its identity."""
    return _text(value)


def parse_instant(value: object) -> datetime:
    """Parse the exact UTC instant representation used by release evidence."""
    return _instant(value)


@dataclass(frozen=True)
class ExistingDocument:
    """Identity obtained from bounded MCP readback, never a draft-to-create ID."""

    post_id: int
    slug: str
    post_type: str
    content_sha256: str
    status: str = "publish"


@dataclass(frozen=True)
class ArticleScope:
    article_id: str
    post_id: int
    slug: str
    baseline_sha256: str
    editorial_product_ids: tuple[str, ...]
    image_ids: tuple[str, ...]
    cta_ids: tuple[str, ...]
    local_sha256: str
    production_sha256: str

    @property
    def monetization_state(self) -> str:
        return "VERIFIED_PRESENT" if self.cta_ids else "NOT_INCLUDED"


@dataclass(frozen=True)
class VerifiedIncrementalManifest:
    manifest_sha256: str
    articles: tuple[ArticleScope, ...]
    unchanged_sha256: Mapping[str, str]
    shared_artifact_sha256: Mapping[str, str]
    evaluated_at: datetime
    expires_at: datetime

    @property
    def counts(self) -> dict[str, int]:
        return {
            "articles": len(self.articles),
            "editorial_products": len(
                {p for a in self.articles for p in a.editorial_product_ids}
            ),
            "images": sum(len(a.image_ids) for a in self.articles),
            "ctas": sum(len(a.cta_ids) for a in self.articles),
            "monetized_articles": sum(bool(a.cta_ids) for a in self.articles),
        }


def validate_manifest(
    document: object,
    *,
    inventory: Mapping[str, ExistingDocument],
    article_targets: Mapping[str, tuple[str, int]],
    shared_baseline_sha256: Mapping[str, str],
    article_products: Mapping[str, Sequence[str]],
    article_claims: Mapping[str, Sequence[str]],
    claim_sources: Mapping[str, Sequence[str]],
    source_receipt_sha256: Mapping[str, str],
    verified_image_sha256: Mapping[str, str],
    verified_cta_sha256: Mapping[str, str],
    image_article_products: Mapping[str, tuple[str, str]],
    cta_article_products: Mapping[str, tuple[str, str]],
    artifact_bytes: Mapping[str, bytes],
    now: datetime,
) -> VerifiedIncrementalManifest:
    """Replay exact selected sets against trusted adapters, not supplied counters.

    Evidence mappings must be produced by the official/API replay validators at
    `now` (including 24-hour freshness, identity, safety and media rights). A
    manifest cannot promote an unverified row by calling it `verified`.
    """
    value = _object(
        document,
        {
            "schema",
            "publication_profile",
            "link_mode",
            "measurement_collection_enabled",
            "publication_authority",
            "evaluated_at",
            "expires_at",
            "articles",
            "unchanged_documents",
            "shared_artifacts",
            "rendered_document_slugs",
        },
    )
    if (
        value["schema"] != SCHEMA
        or value["publication_profile"] != PROFILE
        or value["link_mode"] != "standard-api"
        or value["measurement_collection_enabled"] is not False
        or value["publication_authority"] is not False
    ):
        fail("PROFILE_INVALID")
    if now.tzinfo is None:
        fail("TIME_INVALID")
    evaluated, expires = _instant(value["evaluated_at"]), _instant(value["expires_at"])
    if not evaluated <= now < expires <= evaluated + AUDIT_SUBJECT_MAX_AGE:
        fail("EXPIRED")
    if type(value["articles"]) is not list or not value["articles"]:
        fail("ARTICLE_SET_INVALID")
    if len({entry.post_id for entry in inventory.values()}) != len(inventory):
        fail("INVENTORY_INVALID")
    for slug, existing in inventory.items():
        if (
            existing.slug != slug
            or type(existing.post_id) is not int
            or existing.post_id < 1
            or existing.post_type not in {"post", "page"}
            or existing.status != "publish"
        ):
            fail("INVENTORY_INVALID")
        _hash(existing.content_sha256)
    articles: list[ArticleScope] = []
    selected: set[str] = set()
    article_ids: set[str] = set()
    used_artifacts: set[str] = set()
    used_images: set[str] = set()
    used_ctas: set[str] = set()
    for raw in cast(list[object], value["articles"]):
        row = _object(
            raw,
            {
                "article_id",
                "post_id",
                "slug",
                "baseline_sha256",
                "editorial_product_ids",
                "claim_ids",
                "source_receipts",
                "images",
                "ctas",
                "excluded_commerce",
                "local_artifact",
                "production_artifact",
            },
        )
        article_id, slug = _text(row["article_id"]), _text(row["slug"])
        entry = inventory.get(slug)
        if (
            entry is None
            or entry.post_type != "post"
            or type(row["post_id"]) is not int
            or row["post_id"] != entry.post_id
            or slug in selected
            or article_id in article_ids
            or article_id not in article_products
            or article_targets.get(article_id) != (slug, entry.post_id)
            or row["baseline_sha256"] != entry.content_sha256
        ):
            fail("EXISTING_TARGET_MISMATCH")
        selected.add(slug)
        article_ids.add(article_id)
        products = _strings(row["editorial_product_ids"])
        # Editorial product removals require a new reviewed authoring contract,
        # not a commerce lookup failure hidden in the release manifest.
        if set(products) != set(article_products[article_id]):
            fail("EDITORIAL_SET_MISMATCH")
        claims = _strings(row["claim_ids"])
        if not claims or set(claims) != set(article_claims.get(article_id, ())):
            fail("CLAIM_SET_MISMATCH")
        required_sources: set[str] = set()
        for claim in claims:
            sources = claim_sources.get(claim)
            if not sources:
                fail("CLAIM_WITHOUT_SOURCE")
            required_sources.update(sources)
        source_proofs = _mapping(row["source_receipts"], "SOURCE_SET_MISMATCH")
        if set(source_proofs) != required_sources:
            fail("SOURCE_SET_MISMATCH")
        for source, proof in source_proofs.items():
            if _hash(proof) != source_receipt_sha256.get(source):
                fail("SOURCE_UNVERIFIED")
        chosen: dict[str, tuple[str, ...]] = {}
        for kind, trusted, identities, used in (
            ("images", verified_image_sha256, image_article_products, used_images),
            ("ctas", verified_cta_sha256, cta_article_products, used_ctas),
        ):
            entries = _mapping(row[kind], "COMMERCE_INVALID")
            for identifier, proof in entries.items():
                _text(identifier)
                identity = identities.get(identifier)
                if (
                    identifier in used
                    or identity is None
                    or identity[0] != article_id
                    or identity[1] not in products
                    or _hash(proof) != trusted.get(identifier)
                ):
                    fail("COMMERCE_UNVERIFIED")
                used.add(identifier)
            chosen[kind] = tuple(sorted(entries))
        # Every unselected commercial placement has an explicit reason. Image
        # omission does not imply that the product was excluded editorially.
        possible = {
            key
            for identities in (image_article_products, cta_article_products)
            for key, pair in identities.items()
            if pair[0] == article_id
        }
        omitted = possible - set(chosen["images"]) - set(chosen["ctas"])
        omissions = _mapping(row["excluded_commerce"], "OMISSION_SET_MISMATCH")
        if set(omissions) != omitted:
            fail("OMISSION_SET_MISMATCH")
        for reason in omissions.values():
            if len(_text(reason)) < 8:
                fail("OMISSION_REASON_INVALID")
        hashes: list[str] = []
        for mode in ("local", "production"):
            artifact = _object(row[f"{mode}_artifact"], {"key", "sha256"})
            key, expected = _text(artifact["key"]), _hash(artifact["sha256"])
            if (
                key in used_artifacts
                or key not in artifact_bytes
                or digest(artifact_bytes[key]) != expected
            ):
                fail("ARTIFACT_MISMATCH")
            used_artifacts.add(key)
            hashes.append(expected)
        articles.append(
            ArticleScope(
                article_id,
                entry.post_id,
                slug,
                entry.content_sha256,
                products,
                chosen["images"],
                chosen["ctas"],
                hashes[0],
                hashes[1],
            )
        )
    unchanged = _mapping(value["unchanged_documents"], "DOCUMENT_SET_INVALID")
    shared = _mapping(value["shared_artifacts"], "DOCUMENT_SET_INVALID")
    shared_slugs: set[str] = set()
    shared_hashes: dict[str, str] = {}
    for identifier, raw in shared.items():
        if identifier not in {
            "theme",
            "seo",
            "home",
            "about-ad-policy",
            "comparison-policy",
            "privacy-policy",
        }:
            fail("SHARED_TARGET_INVALID")
        row = _object(raw, {"key", "sha256", "baseline_sha256", "post_id"})
        key, expected = _text(row["key"]), _hash(row["sha256"])
        if (
            key in used_artifacts
            or key not in artifact_bytes
            or digest(artifact_bytes[key]) != expected
        ):
            fail("ARTIFACT_MISMATCH")
        used_artifacts.add(key)
        _hash(row["baseline_sha256"])
        if identifier in {"theme", "seo"}:
            if row["post_id"] is not None or row[
                "baseline_sha256"
            ] != shared_baseline_sha256.get(identifier):
                fail("SHARED_TARGET_INVALID")
        else:
            entry = inventory.get(identifier)
            if (
                entry is None
                or entry.post_type != "page"
                or type(row["post_id"]) is not int
                or row["post_id"] != entry.post_id
                or row["baseline_sha256"] != entry.content_sha256
            ):
                fail("EXISTING_TARGET_MISMATCH")
            shared_slugs.add(identifier)
        shared_hashes[identifier] = expected
    if set(unchanged) != set(inventory) - selected - shared_slugs:
        fail("UNCHANGED_SET_MISMATCH")
    for slug, proof in unchanged.items():
        if _hash(proof) != inventory[slug].content_sha256:
            fail("UNCHANGED_BASELINE_MISMATCH")
    rendered = set(_strings(value["rendered_document_slugs"]))
    if not selected <= rendered <= set(inventory) or (
        shared and rendered != set(inventory)
    ):
        fail("MIXED_PREVIEW_REQUIRED")
    if used_artifacts != set(artifact_bytes):
        fail("ARTIFACT_SET_MISMATCH")
    return VerifiedIncrementalManifest(
        digest(canonical(value)),
        tuple(articles),
        {key: _hash(proof) for key, proof in unchanged.items()},
        shared_hashes,
        evaluated,
        expires,
    )


def verify_untouched_documents(
    manifest: VerifiedIncrementalManifest,
    current: Mapping[str, ExistingDocument],
    before: Mapping[str, ExistingDocument],
) -> None:
    """After apply, ID, URL and stored-content hashes of omitted pages must hold."""
    if set(current) != set(before):
        fail("UNEXPECTED_DOCUMENT_CREATED_OR_REMOVED")
    for slug, previous in before.items():
        entry = current[slug]
        if (entry.post_id, entry.slug, entry.post_type, entry.status) != (
            previous.post_id,
            previous.slug,
            previous.post_type,
            previous.status,
        ):
            fail("IDENTITY_CHANGED")
    for slug, expected in manifest.unchanged_sha256.items():
        if current[slug].content_sha256 != expected:
            fail("UNTOUCHED_DOCUMENT_CHANGED")


@dataclass
class _Element:
    tag: str
    attrs: dict[str, str | None]
    start: int
    opening_end: int
    product: str | None
    card_product: str | None
    card_depth: int
    purchase_action: bool
    end: int = 0


def html_attribute_tokens(value: str | None) -> frozenset[str]:
    """Tokenize decoded class/rel using HTML ASCII whitespace only.

    NBSP, vertical tab and other Unicode whitespace are token characters in
    HTML, not separators. Article validation separately refuses those ambiguous
    characters; theme lookup must still use the browser's exact token boundary.
    """
    return frozenset(re.findall(r"[^\t\n\f\r ]+", value or ""))


def supported_html_token_attributes(starttag: str) -> bool:
    """Refuse references HTMLParser erases from raw class/rel values.

    Python's unescape drops numeric VT and some other control references while
    browsers retain them as token characters. Inspect raw token attributes before
    that information is lost. This is not a second decoding pass: ordinary
    text/alt and escaped literal reference text remain unchanged.
    """
    opening = re.match(r"<[a-zA-Z][^\t\n\f\r />]*", starttag)
    if opening is None:
        return False
    for attribute in _RAW_HTML_ATTRIBUTES.finditer(starttag, opening.end()):
        if attribute[1].lower() not in {"class", "rel"}:
            continue
        value = next((part for part in attribute.groups()[1:] if part is not None), "")
        for reference in re.findall(r"&#(?:[xX][0-9a-fA-F]+|[0-9]+);?", value):
            try:
                if not unescape(reference):
                    return False
            except ValueError:
                return False
    return True


def supported_article_element(tag: str, attrs: Mapping[str, str | None]) -> bool:
    """Closed article grammar; never apply this to the surrounding theme/head.

    HTMLParser lowercases names but does not implement browser SVG/MathML
    namespace transitions. Refuse those transitions, qualified names, namespace
    declarations, and custom-element upgrades instead of treating them as HTML.
    """
    # A deliberately stricter article subset: do not let a visually ambiguous
    # non-HTML separator disguise card/purchase/runtime classes or rel tokens.
    # Unicode identifiers and ordinary reader text remain supported.
    if any(
        character.isspace() and character not in HTML_ASCII_WHITESPACE
        for name in ("class", "rel")
        for character in attrs.get(name) or ""
    ):
        return False
    allowed = ARTICLE_GLOBAL_ATTRIBUTES | ARTICLE_TAG_ATTRIBUTES.get(tag, frozenset())
    return tag in ARTICLE_HTML_TAGS and all(
        ":" not in name
        and name not in {"xmlns", "is"}
        and (
            name in allowed
            or re.fullmatch(r"(?:aria-[a-z-]+|data-[a-z0-9_.-]+)", name) is not None
        )
        for name in attrs
    )


class _Markup(HTMLParser):
    def __init__(self, markup: str) -> None:
        super().__init__(convert_charrefs=False)
        self.markup = markup
        self.offsets = [0]
        for match in re.finditer("\n", markup):
            self.offsets.append(match.end())
        self.elements: list[_Element] = []
        self.stack: list[_Element] = []

    def absolute_offset(self) -> int:
        line, column = self.getpos()
        return self.offsets[line - 1] + column

    def close(self) -> None:
        # The whole fragment is fed at once. A remaining tokenizer buffer is an
        # incomplete tag/comment/entity, not validated text to silently discard.
        if self.rawdata:
            fail("MARKUP_INVALID")
        super().close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if (
            len(values) != len(attrs)
            or not supported_html_token_attributes(self.get_starttag_text() or "")
            or not supported_article_element(tag, values)
            or any(name.startswith("on") or name == "srcdoc" for name in values)
            or any(
                re.sub(r"[\x00-\x20\x7f]+", "", value or "")
                .casefold()
                .startswith(("javascript:", "vbscript:", "data:text/html"))
                for name, value in values.items()
                if name in {"href", "src", "action", "formaction", "xlink:href"}
            )
        ):
            fail("MARKUP_INVALID")
        self._require_browser_stable_parent(tag)
        start = self.absolute_offset()
        product = values.get("data-raos-product-id") or (
            self.stack[-1].product if self.stack else None
        )
        parent = self.stack[-1] if self.stack else None
        classes = html_attribute_tokens(values.get("class"))
        is_card = tag == "article" and "product-profile" in classes
        # Descendant attributes cannot change the identity of their actual card.
        card_product = (
            values.get("data-raos-product-id")
            if is_card
            else parent.card_product
            if parent
            else None
        )
        card_depth = (parent.card_depth if parent else 0) + int(is_card)
        purchase_action = (
            "data-raos-purchase-action" in values
            or bool(classes & PURCHASE_CLASSES)
            or bool(parent and parent.purchase_action)
        )
        element = _Element(
            tag,
            values,
            start,
            start + len(self.get_starttag_text() or ""),
            product,
            card_product,
            card_depth,
            purchase_action,
        )
        self.elements.append(element)
        if tag in VOID:
            element.end = element.opening_end
        else:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Browsers ignore the slash on ordinary HTML elements. Treating it as
        # a close would manufacture a different product-card ancestry.
        if tag not in VOID:
            fail("MARKUP_INVALID")
        self.handle_starttag(tag, attrs)

    def _require_browser_stable_parent(self, tag: str) -> None:
        """Accept a strict article subset, not a replacement HTML5 tree builder.

        Refuse structures that need implicit closure or table foster parenting
        before lexical ancestry is used to bind a product image or purchase link.
        """
        parent = self.stack[-1].tag if self.stack else None
        ancestors = {element.tag for element in self.stack}
        if (
            (parent in TABLE_CHILDREN and tag not in TABLE_CHILDREN[parent])
            or (tag in TABLE_PARENTS and parent not in TABLE_PARENTS[tag])
            or ("p" in ancestors and tag not in PHRASING_TAGS)
            or (tag == "a" and "a" in ancestors)
            or (tag in HEADING_TAGS and ancestors & HEADING_TAGS)
            or (tag == "table" and "caption" in ancestors)
            or (parent in {"ul", "ol"} and tag != "li")
            or (tag == "li" and parent not in {"ul", "ol"})
            or (
                tag in {"dt", "dd"}
                and parent != "dl"
                and not (
                    parent == "div"
                    and len(self.stack) >= 2
                    and self.stack[-2].tag == "dl"
                )
            )
            or (tag in {"rt", "rp"} and parent != "ruby")
        ):
            fail("MARKUP_INVALID")

    def _require_table_text(self, data: str) -> None:
        if self.stack and self.stack[-1].tag in TABLE_CHILDREN:
            # HTML table insertion mode fosters non-ASCII-whitespace text out
            # of the table. NBSP is not HTML whitespace, even though str.strip
            # treats it as whitespace. Decode references before this check.
            if data.strip(HTML_ASCII_WHITESPACE):
                fail("MARKUP_INVALID")

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1].tag != tag:
            fail("MARKUP_INVALID")
        element = self.stack.pop()
        element.end = self.markup.index(">", self.absolute_offset()) + 1

    def handle_comment(self, data: str) -> None:
        # HTMLParser accepts some abrupt/loose comment endings differently from
        # browsers. Never let active tags hide in that disagreement. Ordinary
        # WordPress block comments retain their exact spelling and byte offsets.
        if (
            not self.markup.startswith("<!--" + data + "-->", self.absolute_offset())
            or data.startswith((">", "->"))
            or "--" in data
            or data.endswith("<!-")
        ):
            fail("MARKUP_INVALID")

    def handle_data(self, data: str) -> None:
        # Incomplete declarations/comments/tags can otherwise be returned as
        # text by HTMLParser but interpreted as markup in the browser. Authors
        # can represent a literal less-than sign with the normal &lt; reference.
        if "<" in data:
            fail("MARKUP_INVALID")
        self._require_table_text(data)

    def handle_entityref(self, name: str) -> None:
        self._require_table_text(unescape("&" + name + ";"))

    def handle_charref(self, name: str) -> None:
        self._require_table_text(unescape("&#" + name + ";"))

    def handle_decl(self, decl: str) -> None:
        fail("MARKUP_INVALID")

    def handle_pi(self, data: str) -> None:
        fail("MARKUP_INVALID")

    def unknown_decl(self, data: str) -> None:
        fail("MARKUP_INVALID")


@dataclass(frozen=True)
class MarkupElement:
    """Public read-only element projection; not verification of commerce."""

    tag: str
    attrs: Mapping[str, str | None]
    product: str | None
    start: int
    opening_end: int
    end: int


def parse_markup_elements(markup: str) -> tuple[MarkupElement, ...]:
    """Reuse strict shared syntax checks without exposing parser internals."""
    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail("MARKUP_INVALID")
    return tuple(
        MarkupElement(
            element.tag,
            MappingProxyType(dict(element.attrs)),
            element.product,
            element.start,
            element.opening_end,
            element.end,
        )
        for element in parser.elements
    )


def verify_commerce_markup(
    markup: str,
    *,
    article_id: str,
    editorial_product_ids: frozenset[str],
    expected_ctas: Mapping[str, tuple[str, str, str]],
    expected_images: Mapping[str, str],
) -> None:
    """Exact materialized placement/URL parity with revalidated API evidence.

    CTA keys retain the V3 placement identifier, values are product, placement,
    and the exact API destination. Image keys are product IDs within this article.
    Different placements may use the same unmodified API URL for one product.
    """
    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail("MARKUP_INVALID")
    cards: set[str] = set()
    seen_ctas: set[str] = set()
    seen_images: set[str] = set()
    for element in parser.elements:
        attrs = element.attrs
        classes = html_attribute_tokens(attrs.get("class"))
        # Responsive alternatives need their own image evidence. Until that
        # contract exists, an otherwise verified src must not hide another image.
        if element.tag in {"picture", "source"} or "srcset" in attrs:
            fail("HTML_IMAGE_UNVERIFIED")
        if element.tag == "img" and "data-raos-product-image-id" not in attrs:
            fail("HTML_IMAGE_UNVERIFIED")
        if element.tag == "article" and "product-profile" in classes:
            product = attrs.get("data-raos-product-id")
            if (
                not product
                or product in cards
                or product not in editorial_product_ids
                or element.card_depth != 1
            ):
                fail("HTML_EDITORIAL_SET_MISMATCH")
            cards.add(product)
        if "data-raos-product-image-id" in attrs:
            product = attrs["data-raos-product-image-id"]
            if (
                element.tag != "img"
                or not product
                or product in seen_images
                or product not in editorial_product_ids
                or product not in expected_images
                or element.card_product != product
                or element.product != product
                or attrs.get("src") != expected_images[product]
                or attrs.get("data-raos-product-image-state") != "verified"
                or not (attrs.get("alt") or "").strip()
                or attrs.get("loading") != "lazy"
                or any(
                    not (attrs.get(key) or "").isdigit() or int(attrs[key] or "0") < 1
                    for key in ("width", "height")
                )
            ):
                fail("HTML_IMAGE_UNVERIFIED")
            seen_images.add(product)
        href = attrs.get("href") or ""
        hostname = urlsplit(href).hostname or ""
        if element.tag == "a" and (
            "data-raos-placement" in attrs
            or "data-raos-cta-id" in attrs
            or element.purchase_action
            or hostname in PURCHASE_HOSTS
            or hostname == "afl.rakuten.co.jp"
            or hostname.endswith(".afl.rakuten.co.jp")
        ):
            identifier = attrs.get("data-raos-cta-id") or ""
            expected = expected_ctas.get(identifier)
            if (
                expected is None
                or identifier in seen_ctas
                or attrs.get("data-raos-article-id") != article_id
                or attrs.get("data-raos-product-id") != expected[0]
                or expected[0] not in editorial_product_ids
                or (
                    element.card_product is not None
                    and element.card_product != expected[0]
                )
                or (
                    expected[1] == "product_card"
                    and element.card_product != expected[0]
                )
                or attrs.get("data-raos-placement") != expected[1]
                or href != expected[2]
                or urlsplit(href).scheme != "https"
                or urlsplit(href).hostname != "hb.afl.rakuten.co.jp"
                or html_attribute_tokens(attrs.get("rel"))
                != frozenset({"sponsored", "nofollow"})
                or any(
                    key in attrs
                    for key in (
                        "data-raos-provider-measurement-id",
                        "data-raos-provider-slot-id",
                    )
                )
            ):
                fail("HTML_CTA_UNVERIFIED")
            seen_ctas.add(identifier)
    if cards != set(editorial_product_ids):
        fail("HTML_EDITORIAL_SET_MISMATCH")
    if seen_ctas != set(expected_ctas) or seen_images != set(expected_images):
        fail("HTML_COMMERCE_SET_MISMATCH")


def omit_unverified_commerce(
    markup: str,
    *,
    image_product_ids: frozenset[str],
    cta_product_ids: frozenset[str],
    article_id: str | None = None,
) -> str:
    """Local projection only: remove whole unselected media/action wrappers.

    Retained URLs/images are never invented or rewritten. Callers must still
    verify each retained placement using the evidence adapter. This function
    alone does not mark an article or any commercial feature verified.
    """
    parser = _Markup(markup)
    parser.feed(markup)
    parser.close()
    if parser.stack:
        fail("MARKUP_INVALID")
    removals: list[tuple[int, int]] = []
    removed_ids: dict[str, str | None] = {}
    for element in parser.elements:
        classes = html_attribute_tokens(element.attrs.get("class"))
        product = element.product
        media = "raos-product-card__media" in classes
        action = "data-raos-purchase-action" in element.attrs or bool(
            classes
            & {
                "final-summary-action",
                "product-purchase-action",
                "raos-product-card__actions",
                "summary-action",
            }
        )
        if action and product is None:
            nested_products = {
                child.product
                for child in parser.elements
                if element.start < child.start < element.end
                and child.tag == "a"
                and "data-raos-placement" in child.attrs
                and child.product is not None
            }
            if len(nested_products) == 1:
                product = next(iter(nested_products))
        if (media and product not in image_product_ids) or (
            action and product not in cta_product_ids
        ):
            removals.append((element.start, element.end))
            identifier = element.attrs.get("id")
            if identifier:
                removed_ids[identifier] = next(
                    (
                        e.attrs.get("id")
                        for e in parser.elements
                        if e.tag == "article" and e.product == product
                    ),
                    None,
                )
    # Legacy single figure markup must be treated exactly like a media wrapper.
    for element in parser.elements:
        image_product = element.attrs.get("data-raos-product-image-id")
        if image_product and image_product not in image_product_ids:
            parent = next(
                (
                    e
                    for e in reversed(parser.elements)
                    if e.tag == "figure"
                    and e.start < element.start
                    and e.end >= element.end
                ),
                element,
            )
            removals.append((parent.start, parent.end))
        if element.tag == "a" and "data-raos-placement" in element.attrs:
            if element.product not in cta_product_ids:
                removals.append((element.start, element.end))
    edits: list[tuple[int, int, str]] = []
    if article_id is not None:
        # Discovery must not depend on the presence of a purchase link. Bind
        # the existing non-commercial facts block without changing the exact
        # legacy root prefix or inventing a product/CTA identifier.
        if re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", article_id) is None:
            fail("ARTICLE_ID_INVALID")
        existing_ids = {
            element.attrs["data-raos-article-id"]
            for element in parser.elements
            if "data-raos-article-id" in element.attrs
        }
        facts = [
            element
            for element in parser.elements
            if "raos-article-facts" in html_attribute_tokens(element.attrs.get("class"))
        ]
        if existing_ids - {article_id} or len(facts) != 1:
            fail("ARTICLE_ID_INVALID")
        fact = facts[0]
        if "data-raos-article-id" not in fact.attrs:
            raw = markup[fact.start : fact.opening_end]
            edits.append(
                (
                    fact.start,
                    fact.opening_end,
                    raw[:-1] + f' data-raos-article-id="{article_id}">',
                )
            )
    merged: list[tuple[int, int]] = []
    for start, end in sorted(removals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    edits.extend((start, end, "") for start, end in merged)
    for element in parser.elements:
        if any(start <= element.start < end for start, end in merged):
            continue
        href = element.attrs.get("href") or ""
        if element.tag == "a" and href.startswith("#") and href[1:] in removed_ids:
            target = removed_ids[href[1:]]
            if not target:
                fail("REMOVED_ANCHOR_WITHOUT_TARGET")
            escaped_target = escape(target, quote=True)
            raw = markup[element.start : element.opening_end]
            updated = re.sub(
                r"""(\bhref\s*=\s*)(?:"[^"]*"|'[^']*'|[^\s>]+)""",
                lambda m: f'{m[1]}"#{escaped_target}"',
                raw,
            )
            edits.append((element.start, element.opening_end, updated))
    result = markup
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result
