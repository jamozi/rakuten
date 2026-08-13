"""Adversarial in-memory affiliate slot grammar tests for ST-1703 Wave 3."""

from __future__ import annotations

from pathlib import Path

import pytest

from raos.application.editorial.wordpresscom_mvp_affiliate import (
    validate_wordpresscom_mvp_affiliate_content,
)
from raos.application.editorial.wordpresscom_mvp_drafts import (
    build_bound_wordpresscom_mvp_content,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    WordPressComMvpDraftFailure,
)


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def _bundle():
    baseline = build_bound_review_draft(
        article_bytes=_read("changes/st-1703/first-article-review-draft.v1.md"),
        source_packet_bytes=_read(
            "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
        ),
        base_handoff_bytes=_read(
            "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
        ),
        amendment_handoff_bytes=_read(
            "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
        ),
        activation_handoff_bytes=_read(
            "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
        ),
    )
    return build_bound_wordpresscom_mvp_content(
        handoff_bytes=_read(
            "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3.yaml"
        ),
        approval_bytes=_read(
            "changes/st-1703/DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3-v1.yaml"
        ),
        content_packet_bytes=_read(
            "changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml"
        ),
        baseline_draft=baseline,
    )


def _filled(content: str) -> str:
    bundle = _bundle()
    for slot, product in enumerate(bundle.affiliate_product_names, start=1):
        old = (
            f"<p>楽天公式アフィリエイトHTMLをここに貼り付け：{product}"
            "（画像幅128、価格表示なし）</p>"
        )
        new = (
            '<div><a href="https://img.example/item" target="_blank" '
            'rel="sponsored noopener noreferrer"><img src="https://img.example/x.jpg" '
            f'alt="{product}" width="128" border="0"></a><br>'
            f'<a href="https://shop.example/item" rel="sponsored">{product}</a></div>'
        )
        content = content.replace(old, new, 1)
    return content


def test_exact_placeholders_are_pending_without_parsing_urls() -> None:
    bundle = _bundle()
    assert validate_wordpresscom_mvp_affiliate_content(
        content=bundle.operations[0].content,
        placeholder_content=bundle.operations[0].content,
        product_names=bundle.affiliate_product_names,
    ) == (MvpDraftAffiliateState.SLOTS_PENDING, 0)


def test_three_valid_filled_slots_are_validated() -> None:
    bundle = _bundle()
    assert validate_wordpresscom_mvp_affiliate_content(
        content=_filled(bundle.operations[0].content),
        placeholder_content=bundle.operations[0].content,
        product_names=bundle.affiliate_product_names,
    ) == (MvpDraftAffiliateState.SLOTS_VALIDATED, 3)


@pytest.mark.parametrize(
    ("needle", "replacement"),
    [
        ('width="128"', 'width="127"'),
        ("https://img.example/x.jpg", "http://img.example/x.jpg"),
        ("https://shop.example/item", "javascript:alert(1)"),
        ("https://img.example/x.jpg", "https://good.example\\evil/x"),
        ("https://shop.example/item", "https://good.example:/x"),
        ("https://img.example/x.jpg", "https://good.example/%0a"),
        ("https://shop.example/item", "https://good.example/%ZZ"),
        ('rel="sponsored noopener noreferrer"', 'rel="sponsored"'),
        ("<img src=", "<script></script><img src="),
        ('border="0"', 'style="width:128px"'),
        ("<br>", "<br><br>"),
    ],
)
def test_adversarial_slot_fragments_fail_closed(needle: str, replacement: str) -> None:
    bundle = _bundle()
    value = _filled(bundle.operations[0].content).replace(needle, replacement, 1)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        validate_wordpresscom_mvp_affiliate_content(
            content=value,
            placeholder_content=bundle.operations[0].content,
            product_names=bundle.affiliate_product_names,
        )
    assert str(failure.value) == "MVP_DRAFT_AFFILIATE_INVALID"
    assert "example" not in str(failure.value)


def test_outside_edit_marker_change_mixed_slots_and_price_fail_closed() -> None:
    bundle = _bundle()
    valid = _filled(bundle.operations[0].content)
    cases = (
        valid.replace("<h1>", "<h1>changed", 1),
        valid.replace("RAOS-W3-AFFILIATE-SLOT-2-BEGIN", "changed", 1),
        valid.replace("<div><a", "<div>100円<a", 1),
        valid.replace(
            '<div><a href="https://img.example/item"',
            "<p>楽天公式アフィリエイトHTMLをここに貼り付け："
            f'{bundle.affiliate_product_names[0]}（画像幅128、価格表示なし）</p><a href="https://img.example/item"',
            1,
        ),
    )
    for value in cases:
        with pytest.raises(WordPressComMvpDraftFailure):
            validate_wordpresscom_mvp_affiliate_content(
                content=value,
                placeholder_content=bundle.operations[0].content,
                product_names=bundle.affiliate_product_names,
            )
