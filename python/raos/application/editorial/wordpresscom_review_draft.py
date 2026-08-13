"""Build the one hash-bound WordPress.com review-copy candidate."""

from __future__ import annotations

import hashlib
import html
import re
from typing import Final, NoReturn
from urllib.parse import urlsplit

from raos.domain.editorial.wordpresscom_review_draft import (
    WORDPRESSCOM_REVIEW_DRAFT_API_PATH,
    WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_OPERATION,
    WORDPRESSCOM_REVIEW_DRAFT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailureCode,
    fail_wordpresscom_review_draft,
    review_draft_operation_binding_sha256,
)


ARTICLE_FILE_SHA256: Final = WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256
SOURCE_PACKET_SHA256: Final = WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256
EXTRACTED_MARKDOWN_BYTES: Final = 8789
EXTRACTED_MARKDOWN_SHA256: Final = (
    "5a47d98a7dfb081529c58f362e85862de936c2f38e65c023cf8116391dc7d0ea"
)
_KNOWN_LINKS: Final = frozenset(
    {
        "https://item.rakuten.co.jp/ace-store/01471/",
        "https://item.rakuten.co.jp/ace-store/05721/",
        "https://item.rakuten.co.jp/ace-store/06316/",
        "https://store.ace.jp/shop/g/g01471-08",
        "https://store.ace.jp/shop/g/g05721-01",
        "https://store.ace.jp/shop/g/g06316-01/",
        "https://www.ana.co.jp/ja/tr/travel-information/baggage-information/",
    }
)
_LINK = re.compile(r"\[([^\[\]\n]+)\]\(([^()\s]+)\)", re.ASCII)
_STRONG = re.compile(r"\*\*([^*\n]+)\*\*", re.ASCII)
_CODE = re.compile(r"`([^`\n]+)`", re.ASCII)
_UNORDERED = re.compile(r"- (.+)\Z")
_ORDERED = re.compile(r"[1-9][0-9]*\. (.+)\Z", re.ASCII)
_HEADING = re.compile(r"(#{1,3}) ([^#].*)\Z")
_TABLE_DELIMITER = re.compile(r":?-{3,}:?", re.ASCII)


def _fail_source() -> NoReturn:
    fail_wordpresscom_review_draft(
        WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID
    )


def _fail_markdown() -> NoReturn:
    fail_wordpresscom_review_draft(WordPressComReviewDraftFailureCode.MARKDOWN_INVALID)


def _decode_bound(value: object, expected_sha256: str) -> str:
    if type(value) is not bytes or hashlib.sha256(value).hexdigest() != expected_sha256:
        _fail_source()
    encoded = value
    try:
        decoded = encoded.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail_source()
    if decoded.encode("utf-8") != encoded or "\r" in decoded or "\x00" in decoded:
        _fail_source()
    return decoded


def extract_bound_article_markdown(article_bytes: bytes) -> str:
    """Extract exactly the UTF-8 region between the first two standalone rules."""

    document = _decode_bound(article_bytes, ARTICLE_FILE_SHA256)
    lines = document.splitlines()
    delimiter_positions = [index for index, line in enumerate(lines) if line == "---"]
    if len(delimiter_positions) != 2:
        _fail_source()
    markdown = "\n".join(
        lines[delimiter_positions[0] + 1 : delimiter_positions[1]]
    ).strip()
    markdown = f"{markdown}\n"
    encoded = markdown.encode("utf-8")
    if (
        len(encoded) != EXTRACTED_MARKDOWN_BYTES
        or hashlib.sha256(encoded).hexdigest() != EXTRACTED_MARKDOWN_SHA256
    ):
        _fail_source()
    return markdown


def _validate_link(value: str) -> str:
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError:
        _fail_markdown()
    if (
        value not in _KNOWN_LINKS
        or not value.startswith("https://")
        or parts.scheme != "https"
        or parts.hostname is None
        or parts.hostname != parts.hostname.lower()
        or parts.username is not None
        or parts.password is not None
        or port not in {None, 443}
        or parts.query
        or parts.fragment
    ):
        _fail_markdown()
    return value


def _inline(value: str) -> str:
    if (
        not value
        or value != value.strip()
        or "<" in value
        or ">" in value
        or "![" in value
        or "_" in value
    ):
        _fail_markdown()
    tokens: dict[str, str] = {}

    def reserve(rendered: str) -> str:
        marker = f"\x00{len(tokens)}\x00"
        tokens[marker] = rendered
        return marker

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        if any(character in label for character in "*`[]<>"):
            _fail_markdown()
        href = _validate_link(match.group(2))
        return reserve(
            f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'
        )

    working = _LINK.sub(replace_link, value)

    def replace_strong(match: re.Match[str]) -> str:
        payload = match.group(1)
        if any(character in payload for character in "*`[]<>"):
            _fail_markdown()
        return reserve(f"<strong>{html.escape(payload)}</strong>")

    working = _STRONG.sub(replace_strong, working)

    def replace_code(match: re.Match[str]) -> str:
        payload = match.group(1)
        if "\x00" in payload:
            _fail_markdown()
        return reserve(f"<code>{html.escape(payload)}</code>")

    working = _CODE.sub(replace_code, working)
    if any(character in working for character in "*`[]<>"):
        _fail_markdown()
    rendered = html.escape(working, quote=True)
    for marker, replacement in tokens.items():
        rendered = rendered.replace(marker, replacement)
    if "\x00" in rendered:
        _fail_markdown()
    return rendered


def _table_cells(line: str) -> list[str]:
    if not line.startswith("| ") or not line.endswith(" |"):
        _fail_markdown()
    cells = [cell.strip() for cell in line[1:-1].split("|")]
    if not cells or any(not cell for cell in cells):
        _fail_markdown()
    return cells


def render_closed_markdown(markdown: str) -> str:
    """Render only the handoff-approved closed Markdown vocabulary."""

    if (
        type(markdown) is not str
        or not markdown.endswith("\n")
        or markdown != markdown.strip() + "\n"
        or "\r" in markdown
        or "\x00" in markdown
        or "<" in markdown
    ):
        _fail_markdown()
    lines = markdown[:-1].split("\n")
    output: list[str] = []
    index = 0
    title_count = 0
    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        heading = _HEADING.fullmatch(line)
        if heading is not None:
            level = len(heading.group(1))
            if level == 1:
                title_count += 1
                if title_count != 1 or index != 0:
                    _fail_markdown()
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue
        if line == "---":
            output.append("<hr>")
            index += 1
            continue
        if line.startswith("> "):
            output.append(f"<blockquote><p>{_inline(line[2:])}</p></blockquote>")
            index += 1
            continue
        unordered = _UNORDERED.fullmatch(line)
        ordered = _ORDERED.fullmatch(line)
        if unordered is not None or ordered is not None:
            tag = "ul" if unordered is not None else "ol"
            items: list[str] = []
            while index < len(lines):
                match = (
                    _UNORDERED.fullmatch(lines[index])
                    if tag == "ul"
                    else _ORDERED.fullmatch(lines[index])
                )
                if match is None:
                    break
                items.append(f"<li>{_inline(match.group(1))}</li>")
                index += 1
            output.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        if line.startswith("|"):
            if index + 2 >= len(lines):
                _fail_markdown()
            headers = _table_cells(line)
            delimiters = _table_cells(lines[index + 1])
            if len(headers) != len(delimiters) or any(
                _TABLE_DELIMITER.fullmatch(cell) is None for cell in delimiters
            ):
                _fail_markdown()
            index += 2
            rows: list[list[str]] = []
            while index < len(lines) and lines[index].startswith("|"):
                row = _table_cells(lines[index])
                if len(row) != len(headers):
                    _fail_markdown()
                rows.append(row)
                index += 1
            if not rows:
                _fail_markdown()
            head = "".join(f"<th>{_inline(cell)}</th>" for cell in headers)
            body = "".join(
                f"<tr>{''.join(f'<td>{_inline(cell)}</td>' for cell in row)}</tr>"
                for row in rows
            )
            output.append(
                f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            )
            continue
        paragraph: list[str] = []
        while index < len(lines) and lines[index]:
            candidate = lines[index]
            if (
                _HEADING.fullmatch(candidate) is not None
                or candidate == "---"
                or candidate.startswith("> ")
                or _UNORDERED.fullmatch(candidate) is not None
                or _ORDERED.fullmatch(candidate) is not None
                or candidate.startswith("|")
            ):
                break
            paragraph.append(candidate)
            index += 1
        if not paragraph:
            _fail_markdown()
        output.append(f"<p>{_inline(' '.join(paragraph))}</p>")
    if title_count != 1 or not output:
        _fail_markdown()
    return "\n".join(output) + "\n"


def build_bound_review_draft(
    *,
    article_bytes: bytes,
    source_packet_bytes: bytes,
    base_handoff_bytes: bytes,
    amendment_handoff_bytes: bytes,
    activation_handoff_bytes: bytes,
) -> WordPressComReviewDraft:
    """Verify all immutable inputs and create the sole approved candidate."""

    markdown = extract_bound_article_markdown(article_bytes)
    _decode_bound(source_packet_bytes, SOURCE_PACKET_SHA256)
    _decode_bound(base_handoff_bytes, WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256)
    _decode_bound(
        amendment_handoff_bytes,
        WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256,
    )
    _decode_bound(activation_handoff_bytes, WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256)
    first_line = markdown.split("\n", 1)[0]
    if not first_line.startswith("# "):
        _fail_source()
    title = f"{WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX}{first_line[2:]}"
    rendered = render_closed_markdown(markdown)
    content_sha256 = hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    return WordPressComReviewDraft(
        schema=WORDPRESSCOM_REVIEW_DRAFT_SCHEMA,
        target_origin=WORDPRESSCOM_REVIEW_DRAFT_TARGET,
        api_path=WORDPRESSCOM_REVIEW_DRAFT_API_PATH,
        operation=WORDPRESSCOM_REVIEW_DRAFT_OPERATION,
        title=title,
        rendered_content=rendered,
        content_sha256=content_sha256,
        operation_binding_sha256=review_draft_operation_binding_sha256(
            title=title,
            content_sha256=content_sha256,
        ),
        handoff_sha256=WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
    )


__all__ = [
    "ARTICLE_FILE_SHA256",
    "EXTRACTED_MARKDOWN_BYTES",
    "EXTRACTED_MARKDOWN_SHA256",
    "SOURCE_PACKET_SHA256",
    "build_bound_review_draft",
    "extract_bound_article_markdown",
    "render_closed_markdown",
]
