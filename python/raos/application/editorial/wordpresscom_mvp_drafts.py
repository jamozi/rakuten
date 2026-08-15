"""Construct the exact ST-1703 Wave 3 article and page draft objects."""

from __future__ import annotations

import hashlib
from typing import Any, NoReturn, cast

import yaml

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftContentBundle,
    MvpDraftOperation,
    WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256,
    WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256,
    WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WORDPRESSCOM_MVP_WAVE3_PAGE_SLUGS,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
    normalize_wordpresscom_mvp_line_endings,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    WordPressComReviewDraft,
    require_exact_wordpresscom_review_draft,
)


_HANDOFF_BYTES = 29_041
_CONTENT_PACKET_BYTES = 12_670
_APPROVAL_BYTES = 1_991
_ARTICLE_DESIRED_BYTES = 9_919
_EXPECTED_PAGE_HASHES = {
    "about": "147bfe03a538872597a014c41742d57f410355988c10fe246b92b5adcc1387d5",
    "editorial-policy": "6a824c6cbda474db4921db134e9cb8adf6678221d3913b863f3ec81e729eb159",
    "privacy-policy": "09c1442ab4479b582c2974e0f32512ff03e118e1a78848c6bf0bf57f5a4e8868",
    "advertising-policy": "6731018bb1dfadcd83a82b3fc36dd288e5b3a2c946530a0ab36a88718337737f",
    "contact": "03bb8256d4d93199f699c0919aa35570a29e7da4dd47d2b5d620f89970b98176",
}
_EXPECTED_PAGE_BYTES = {
    "about": 842,
    "editorial-policy": 1178,
    "privacy-policy": 1993,
    "advertising-policy": 1234,
    "contact": 426,
}


def _fail() -> NoReturn:
    fail_wordpresscom_mvp_draft(WordPressComMvpDraftFailureCode.CONTENT_INVALID)


def _bound_utf8(value: object, *, size: int, sha256: str) -> str:
    if type(value) is not bytes or len(value) != size:
        _fail()
    raw = value
    if hashlib.sha256(raw).hexdigest() != sha256:
        _fail()
    try:
        decoded = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail()
    if decoded.encode("utf-8") != raw or "\x00" in decoded:
        _fail()
    return decoded


def _mapping(value: object, exact_keys: set[str]) -> dict[str, object]:
    if type(value) is not dict or set(cast(dict[object, object], value)) != exact_keys:
        _fail()
    mapping = cast(dict[object, object], value)
    if any(type(key) is not str for key in mapping):
        _fail()
    return cast(dict[str, object], mapping)


def _string(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if type(value) is not str:
        _fail()
    return value


def _integer(mapping: dict[str, object], key: str) -> int:
    value = mapping.get(key)
    if type(value) is not int:
        _fail()
    return value


def _load_packet(text: str) -> dict[str, object]:
    try:
        parsed: Any = yaml.safe_load(text)
    except yaml.YAMLError:
        _fail()
    outer = _mapping(parsed, {"wordpresscom_mvp_draft_content"})
    packet = outer["wordpresscom_mvp_draft_content"]
    if type(packet) is not dict:
        _fail()
    return cast(dict[str, object], packet)


def _build_article(
    packet: dict[str, object], baseline: WordPressComReviewDraft
) -> tuple[MvpDraftOperation, tuple[str, str, str]]:
    article_value = packet.get("article")
    if type(article_value) is not dict:
        _fail()
    article = cast(dict[str, object], article_value)
    if article.get("operation_id") != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]:
        _fail()
    desired_value = article.get("desired")
    if type(desired_value) is not dict:
        _fail()
    desired = cast(dict[str, object], desired_value)
    transform_value = desired.get("transform")
    if type(transform_value) is not dict:
        _fail()
    transform = cast(dict[str, object], transform_value)
    replacements_value = transform.get("exact_replacements")
    replacements = cast(list[object], replacements_value)
    if type(replacements_value) is not list or len(replacements) != 4:
        _fail()
    rendered = normalize_wordpresscom_mvp_line_endings(baseline.rendered_content)
    replacement_ids: list[str] = []
    for replacement_value in replacements:
        if type(replacement_value) is not dict:
            _fail()
        replacement = cast(dict[str, object], replacement_value)
        if set(replacement) != {"replacement_id", "exact_old", "exact_new"}:
            _fail()
        replacement_id = _string(replacement, "replacement_id")
        old = _string(replacement, "exact_old")
        new = normalize_wordpresscom_mvp_line_endings(_string(replacement, "exact_new"))
        if not old or rendered.count(old) != 1:
            _fail()
        replacement_ids.append(replacement_id)
        rendered = rendered.replace(old, new, 1)
    if replacement_ids != [
        "advertising-disclosure",
        "affiliate-slot-1",
        "affiliate-slot-2",
        "affiliate-slot-3",
    ]:
        _fail()
    encoded = rendered.encode("utf-8", errors="strict")
    if (
        len(encoded) != _ARTICLE_DESIRED_BYTES
        or hashlib.sha256(encoded).hexdigest()
        != WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256
        or desired.get("desired_content_sha256")
        != WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256
        or desired.get("outside_slots_sha256")
        != WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256
        or desired.get("title") != WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE
    ):
        _fail()
    slots_value = desired.get("affiliate_slots")
    slots = cast(list[object], slots_value)
    if type(slots_value) is not list or len(slots) != 3:
        _fail()
    product_names: list[str] = []
    for index, slot_value in enumerate(slots, start=1):
        if type(slot_value) is not dict:
            _fail()
        slot = cast(dict[str, object], slot_value)
        if set(slot) != {"slot", "product_name"} or slot.get("slot") != index:
            _fail()
        product_names.append(_string(slot, "product_name"))
    operation = MvpDraftOperation(
        operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
        object_type="post",
        object_id=WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
        slug="",
        title=WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_TITLE,
        content=rendered,
        content_sha256=WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256,
    )
    return operation, cast(tuple[str, str, str], tuple(product_names))


def _build_pages(packet: dict[str, object]) -> tuple[MvpDraftOperation, ...]:
    pages_value = packet.get("pages")
    pages = cast(list[object], pages_value)
    if type(pages_value) is not list or len(pages) != 5:
        _fail()
    operations: list[MvpDraftOperation] = []
    for index, (slug, value) in enumerate(
        zip(WORDPRESSCOM_MVP_WAVE3_PAGE_SLUGS, pages),
        start=1,
    ):
        if type(value) is not dict:
            _fail()
        page = cast(dict[str, object], value)
        content = normalize_wordpresscom_mvp_line_endings(_string(page, "content"))
        encoded = content.encode("utf-8", errors="strict")
        if (
            page.get("operation_id") != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[index]
            or page.get("slug") != slug
            or page.get("type") != "page"
            or page.get("status") != "draft"
            or page.get("content_sha256") != _EXPECTED_PAGE_HASHES[slug]
            or _integer(page, "content_bytes") != _EXPECTED_PAGE_BYTES[slug]
            or len(encoded) != _EXPECTED_PAGE_BYTES[slug]
            or hashlib.sha256(encoded).hexdigest() != _EXPECTED_PAGE_HASHES[slug]
        ):
            _fail()
        if slug == "contact" and (
            content.count("[contact-form]") != 1
            or "mailto:" in content.lower()
            or "@" in content
        ):
            _fail()
        operations.append(
            MvpDraftOperation(
                operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[index],
                object_type="page",
                object_id=None,
                slug=slug,
                title=_string(page, "title"),
                content=content,
                content_sha256=_EXPECTED_PAGE_HASHES[slug],
            )
        )
    return tuple(operations)


def build_bound_wordpresscom_mvp_content(
    *,
    handoff_bytes: bytes,
    approval_bytes: bytes,
    content_packet_bytes: bytes,
    baseline_draft: WordPressComReviewDraft,
) -> MvpDraftContentBundle:
    """Verify every fixed input before constructing the six desired objects."""

    _bound_utf8(
        handoff_bytes,
        size=_HANDOFF_BYTES,
        sha256=WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256,
    )
    _bound_utf8(
        approval_bytes,
        size=_APPROVAL_BYTES,
        sha256=WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256,
    )
    packet_text = _bound_utf8(
        content_packet_bytes,
        size=_CONTENT_PACKET_BYTES,
        sha256=WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256,
    )
    baseline = require_exact_wordpresscom_review_draft(baseline_draft)
    packet = _load_packet(packet_text)
    if (
        packet.get("schema") != "WORDPRESSCOM_MVP_DRAFT_CONTENT_V1"
        or packet.get("story_id") != "ST-1703"
        or packet.get("slice_id") != "WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3"
        or packet.get("publication_authority") != "NONE"
    ):
        _fail()
    article, product_names = _build_article(packet, baseline)
    pages = _build_pages(packet)
    return MvpDraftContentBundle(
        operations=(article, *pages),
        article_baseline_content=baseline.rendered_content,
        article_outside_slots_sha256=WORDPRESSCOM_MVP_WAVE3_ARTICLE_OUTSIDE_SLOTS_SHA256,
        affiliate_product_names=product_names,
    )


__all__ = ["build_bound_wordpresscom_mvp_content"]
