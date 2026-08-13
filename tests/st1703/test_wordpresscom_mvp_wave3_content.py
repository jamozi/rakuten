"""Exact content-packet and transformation tests for ST-1703 Wave 3."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from raos.application.editorial.wordpresscom_mvp_drafts import (
    build_bound_wordpresscom_mvp_content,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WordPressComMvpDraftFailure,
)


ROOT = Path(__file__).resolve().parents[2]


def _read(relative: str) -> bytes:
    return (ROOT / relative).read_bytes()


def _baseline():
    return build_bound_review_draft(
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


def _build():
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
        baseline_draft=_baseline(),
    )


def test_exact_packet_builds_six_hash_bound_objects() -> None:
    bundle = _build()
    assert tuple(item.operation_id for item in bundle.operations) == (
        WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
    )
    assert len({item.binding_sha256() for item in bundle.operations}) == 6
    assert bundle.operations[0].content_sha256 == (
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256
    )
    assert hashlib.sha256(bundle.operations[0].content.encode()).hexdigest() == (
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_DESIRED_CONTENT_SHA256
    )


def test_article_transform_is_exact_and_slots_are_placeholder_only() -> None:
    article = _build().operations[0]
    assert "［楽天アフィリエイトリンク未設定" not in article.content
    assert article.content.count("<!-- RAOS-W3-AFFILIATE-SLOT-") == 6
    assert article.content.count("楽天公式アフィリエイトHTMLをここに貼り付け") == 3
    for slot in range(1, 4):
        interior = article.content.split(
            f"<!-- RAOS-W3-AFFILIATE-SLOT-{slot}-BEGIN -->\n", 1
        )[1].split(f"\n<!-- RAOS-W3-AFFILIATE-SLOT-{slot}-END -->", 1)[0]
        assert "href=" not in interior
        assert "src=" not in interior


def test_pages_are_exact_and_contact_is_lexical_only() -> None:
    pages = _build().operations[1:]
    assert [page.slug for page in pages] == [
        "about",
        "editorial-policy",
        "privacy-policy",
        "advertising-policy",
        "contact",
    ]
    assert pages[-1].content.count("[contact-form]") == 1
    assert "mailto:" not in pages[-1].content.lower()
    assert "@" not in pages[-1].content


@pytest.mark.parametrize("source", ["handoff", "approval", "packet"])
def test_any_fixed_input_byte_change_refuses_before_construction(source: str) -> None:
    values = {
        "handoff": bytearray(
            _read(
                "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3.yaml"
            )
        ),
        "approval": bytearray(
            _read(
                "changes/st-1703/DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3-v1.yaml"
            )
        ),
        "packet": bytearray(
            _read("changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml")
        ),
    }
    values[source][-1] ^= 1
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        build_bound_wordpresscom_mvp_content(
            handoff_bytes=bytes(values["handoff"]),
            approval_bytes=bytes(values["approval"]),
            content_packet_bytes=bytes(values["packet"]),
            baseline_draft=_baseline(),
        )
    assert failure.value.code.value == "MVP_DRAFT_CONTENT_INVALID"
