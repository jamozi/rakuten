"""Early immutable-domain checkpoint for the approved Wave 2 slice."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

import pytest

from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WORDPRESSCOM_REVIEW_DRAFT_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_TITLE,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftReceipt,
)
from raos.ports.wordpresscom_review_draft import WordPressComReviewDraftPort


ROOT = Path(__file__).resolve().parents[2]


def _candidate() -> WordPressComReviewDraft:
    return build_bound_review_draft(
        article_bytes=(
            ROOT / "changes/st-1703/first-article-review-draft.v1.md"
        ).read_bytes(),
        source_packet_bytes=(
            ROOT / "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
        ).read_bytes(),
        base_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
        ).read_bytes(),
        amendment_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
        ).read_bytes(),
        activation_handoff_bytes=(
            ROOT
            / "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
        ).read_bytes(),
    )


class OneCreatePort:
    def create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt:
        return WordPressComReviewDraftReceipt(
            schema=WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
            authority=WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
            network_status=WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
            target_origin=candidate.target_origin,
            draft_id=1703,
            status=WORDPRESSCOM_REVIEW_DRAFT_STATUS,
            operation_binding_sha256=candidate.operation_binding_sha256,
            content_sha256=candidate.content_sha256,
            response_body_sha256="c" * 64,
            disposition=ReviewDraftDisposition.CREATED,
            publication_authorized=False,
            production_eligible=False,
        )


def test_port_exposes_only_one_create_or_replay_operation() -> None:
    assert isinstance(OneCreatePort(), WordPressComReviewDraftPort)
    public_members = {
        name for name in vars(WordPressComReviewDraftPort) if not name.startswith("_")
    }
    assert public_members == {"create_review_draft"}


def test_candidate_and_receipt_are_immutable_and_non_authorizing() -> None:
    candidate = _candidate()
    receipt = OneCreatePort().create_review_draft(candidate)

    assert receipt.draft_id == 1703
    assert receipt.status == "draft"
    assert receipt.publication_authorized is False
    assert receipt.production_eligible is False
    assert candidate.title == WORDPRESSCOM_REVIEW_DRAFT_TITLE
    assert candidate.content_sha256 == WORDPRESSCOM_REVIEW_DRAFT_CONTENT_SHA256
    assert candidate.api_path == "/rest/v1.1/sites/256699520/posts/new"
    assert (
        candidate.handoff_sha256
        == "0a10b777ccd1e786f34890458621a21a9684feb73cee2b6808a5facefeef65ee"
        == WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256
    )
    assert (
        candidate.operation_binding_sha256
        == WORDPRESSCOM_REVIEW_DRAFT_OPERATION_BINDING_SHA256
    )
    assert candidate.rendered_content not in repr(candidate)
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.title = "publish"  # type: ignore[misc]


def test_operation_binding_is_independently_bound_to_numeric_route_amendment() -> None:
    candidate = _candidate()
    encoded = json.dumps(
        {
            "api_path": "/rest/v1.1/sites/256699520/posts/new",
            "article_sha256": (
                "58e225050d2bf30593fdd039ed9a307cd35db928b946bec470acbb7aa442a233"
            ),
            "content_sha256": (
                "6eab149a4057d3f21dad6fa9efdbe66aadfafa00f100038541a3971693a8503d"
            ),
            "handoff_sha256": (
                "0a10b777ccd1e786f34890458621a21a9684feb73cee2b6808a5facefeef65ee"
            ),
            "operation": "CREATE_REVIEW_DRAFT",
            "source_packet_sha256": (
                "730de77b730afd692ca734746a7321d29a5191244832e4f44fb0d84a871707b2"
            ),
            "target_origin": "https://kurashierabinote.wordpress.com",
            "title": WORDPRESSCOM_REVIEW_DRAFT_TITLE,
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    assert hashlib.sha256(encoded).hexdigest() == (
        "794cee08b70ea1762f2c78b9be9826a486ab1beec44844a9fbd013e740ee2abd"
    )
    assert hashlib.sha256(encoded).hexdigest() == candidate.operation_binding_sha256


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_origin", "https://example.com"),
        ("api_path", "/wp/v2/sites/256699520/posts/1"),
        ("operation", "UPDATE"),
        ("title", "review without the exact prefix"),
        ("handoff_sha256", "0" * 64),
    ],
)
def test_candidate_rejects_any_widened_operation(field: str, value: str) -> None:
    values = {
        item.name: getattr(_candidate(), item.name)
        for item in dataclasses.fields(WordPressComReviewDraft)
    }
    values[field] = value

    with pytest.raises(WordPressComReviewDraftFailure) as caught:
        WordPressComReviewDraft(**values)

    assert str(caught.value) == "REVIEW_DRAFT_CANDIDATE_INVALID"
