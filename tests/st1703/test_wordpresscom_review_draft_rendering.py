"""Hash binding and closed rendering tests for the approved review copy."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re

import pytest

from raos.application.editorial.wordpresscom_review_draft import (
    ARTICLE_FILE_SHA256,
    EXTRACTED_MARKDOWN_BYTES,
    EXTRACTED_MARKDOWN_SHA256,
    SOURCE_PACKET_SHA256,
    build_bound_review_draft,
    extract_bound_article_markdown,
    render_closed_markdown,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX,
    WordPressComReviewDraftFailure,
)


ROOT = Path(__file__).resolve().parents[2]
ARTICLE = ROOT / "changes/st-1703/first-article-review-draft.v1.md"
SOURCE_PACKET = ROOT / "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
BASE_HANDOFF = (
    ROOT / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
)
AMENDMENT_HANDOFF = (
    ROOT
    / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
)
ACTIVATION_HANDOFF = (
    ROOT
    / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
)
ALLOWED_TAGS = {
    "a",
    "blockquote",
    "code",
    "h1",
    "h2",
    "h3",
    "hr",
    "li",
    "ol",
    "p",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
}


def _inputs() -> tuple[bytes, bytes, bytes, bytes, bytes]:
    return (
        ARTICLE.read_bytes(),
        SOURCE_PACKET.read_bytes(),
        BASE_HANDOFF.read_bytes(),
        AMENDMENT_HANDOFF.read_bytes(),
        ACTIVATION_HANDOFF.read_bytes(),
    )


def test_exact_sources_extract_render_and_bind_deterministically() -> None:
    article, source_packet, base_handoff, amendment_handoff, activation_handoff = (
        _inputs()
    )

    markdown = extract_bound_article_markdown(article)
    first = build_bound_review_draft(
        article_bytes=article,
        source_packet_bytes=source_packet,
        base_handoff_bytes=base_handoff,
        amendment_handoff_bytes=amendment_handoff,
        activation_handoff_bytes=activation_handoff,
    )
    second = build_bound_review_draft(
        article_bytes=article,
        source_packet_bytes=source_packet,
        base_handoff_bytes=base_handoff,
        amendment_handoff_bytes=amendment_handoff,
        activation_handoff_bytes=activation_handoff,
    )

    assert len(markdown.encode()) == EXTRACTED_MARKDOWN_BYTES
    assert hashlib.sha256(markdown.encode()).hexdigest() == EXTRACTED_MARKDOWN_SHA256
    assert hashlib.sha256(article).hexdigest() == ARTICLE_FILE_SHA256
    assert hashlib.sha256(source_packet).hexdigest() == SOURCE_PACKET_SHA256
    assert (
        hashlib.sha256(base_handoff).hexdigest()
        == WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256
    )
    assert (
        hashlib.sha256(amendment_handoff).hexdigest()
        == WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256
    )
    assert (
        hashlib.sha256(activation_handoff).hexdigest()
        == WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256
    )
    assert first == second
    assert first.title.startswith(WORDPRESSCOM_REVIEW_DRAFT_TITLE_PREFIX)
    assert first.rendered_content.startswith("<h1>")
    assert "<table><thead>" in first.rendered_content
    assert "<strong>" in first.rendered_content
    assert 'href="https://store.ace.jp/' in first.rendered_content
    assert (
        hashlib.sha256(first.rendered_content.encode()).hexdigest()
        == first.content_sha256
    )


def test_rendered_output_uses_only_closed_tags_and_href_attribute() -> None:
    article, source_packet, base_handoff, amendment_handoff, activation_handoff = (
        _inputs()
    )
    candidate = build_bound_review_draft(
        article_bytes=article,
        source_packet_bytes=source_packet,
        base_handoff_bytes=base_handoff,
        amendment_handoff_bytes=amendment_handoff,
        activation_handoff_bytes=activation_handoff,
    )
    tags = re.findall(r"</?([a-z0-9]+)(?: [^>]*)?>", candidate.rendered_content)
    attributes = re.findall(r"<[a-z0-9]+ ([^>]*)>", candidate.rendered_content)

    assert set(tags) <= ALLOWED_TAGS
    assert attributes
    assert all(re.fullmatch(r'href="https://[^"<>]+"', value) for value in attributes)
    assert "script" not in candidate.rendered_content.lower()
    assert "javascript:" not in candidate.rendered_content.lower()


@pytest.mark.parametrize("index", range(5))
def test_any_bound_input_change_fails_before_candidate(index: int) -> None:
    values = list(_inputs())
    values[index] += b"\n"

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        build_bound_review_draft(
            article_bytes=values[0],
            source_packet_bytes=values[1],
            base_handoff_bytes=values[2],
            amendment_handoff_bytes=values[3],
            activation_handoff_bytes=values[4],
        )

    assert str(caught.value) == "REVIEW_DRAFT_SOURCE_BINDING_INVALID"


@pytest.mark.parametrize(
    "markdown",
    [
        "# title\n\n<script>alert(1)</script>\n",
        "# title\n\n[x](http://example.com)\n",
        "# title\n\n[x](https://example.com)\n",
        "# title\n\n[x](https://store.ace.jp/shop/g/g06316-01/?affiliate=1)\n",
        "# title\n\n_unapproved emphasis_\n",
        "# title\n\n![media](https://store.ace.jp/shop/g/g06316-01/)\n",
        "# title\n\n| malformed |\n| -- |\n| row |\n",
        "# title\n\n# second title\n",
        "## missing title\n",
        "# title\n\ntrailing without LF",
    ],
)
def test_renderer_fails_closed_on_raw_html_links_and_unsupported_syntax(
    markdown: str,
) -> None:
    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        render_closed_markdown(markdown)

    assert str(caught.value) == "REVIEW_DRAFT_MARKDOWN_INVALID"


def test_renderer_escapes_plain_text_and_inline_code() -> None:
    rendered = render_closed_markdown("# title & safety\n\nUse `a&b` safely.\n")

    assert rendered == (
        "<h1>title &amp; safety</h1>\n<p>Use <code>a&amp;b</code> safely.</p>\n"
    )
