"""Focused domain tests for the publication-only v2 client."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pytest

from raos.domain.editorial.self_hosted_editorial_pilot import (
    PILOT_AUTHOR_NAME,
    PILOT_ORIGIN,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    ReviewDraftRequest,
    bytes_sha256,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PUBLICATION_OPERATOR_RESULT_CODE,
    PublicationApplyReceipt,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationOperatorOperation,
    PublicationOperatorStatus,
    PublicationProposal,
    PublicationProposalReceipt,
    PublicationProposalState,
    ST1704_PUBLISH_NEW_ARTICLE_IDS,
)


ROOT = Path(__file__).resolve().parents[2]


def review_request(
    *,
    article_id: str = "st1704-portable-power-station-guide",
    slug: str = "portable-power-station-guide",
    packet_sha256: str = "1" * 64,
) -> ReviewDraftRequest:
    content = '<p class="ks-lead">条件を一次情報から整理します。</p>'
    snapshot = PublicationSnapshot.bind(
        PublicationSnapshotPayload(
            article_id=article_id,
            packet_sha256=packet_sha256,
            slug=slug,
            title="停電対策用ポータブル電源の選び方",
            seo_title="停電対策用ポータブル電源4モデル比較",
            description="容量・定格出力・持ち運びの条件を整理します。",
            canonical_url=f"{PILOT_ORIGIN}/{slug}/",
            og_title="停電対策用ポータブル電源の選び方",
            og_description="容量・定格出力・持ち運びの条件を整理します。",
            published_at=None,
            modified_at=None,
            author_name=PILOT_AUTHOR_NAME,
            section="備え",
            visible_content_sha256=bytes_sha256(content.encode()),
        )
    )
    return ReviewDraftRequest.bind(
        article_id=article_id,
        packet_sha256=packet_sha256,
        title=snapshot.payload.title,
        public_slug=slug,
        excerpt=snapshot.payload.description,
        content=content,
        snapshot=snapshot,
    )


def proposal() -> PublicationProposal:
    return PublicationProposal.bind(
        CommittedReviewDraftBinding(
            article_id="st1704-portable-power-station-guide",
            draft_post_id=28,
            packet_sha256="1" * 64,
            request_sha256="2" * 64,
            snapshot_payload_sha256="3" * 64,
            visible_content_sha256="4" * 64,
            public_slug="portable-power-station-guide",
        ),
        "5" * 64,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_canonical_proposal_matches_php_golden_vector_byte_for_byte() -> None:
    golden = json.loads(
        (
            ROOT / "changes/st-1704/publication-operator-v2/contracts/"
            "canonical-publication-proposal-golden.v2.json"
        ).read_bytes()
    )
    candidate = proposal()

    assert candidate.canonical_bytes() == golden["canonical_ascii_json"].encode("ascii")
    assert len(candidate.canonical_bytes()) == golden["canonical_byte_length"] == 748
    assert candidate.proposal_id == golden["proposal_id"]
    assert (
        candidate.proposal_id == hashlib.sha256(candidate.canonical_bytes()).hexdigest()
    )
    assert set(candidate.payload()) == {
        "article_id",
        "category_contract",
        "draft_post_id",
        "operation",
        "operator_contract_version",
        "packet_sha256",
        "profile_version",
        "public_slug",
        "request_sha256",
        "request_token",
        "site_origin",
        "snapshot_payload_sha256",
        "ttl_seconds",
        "visible_content_sha256",
    }
    assert not set(candidate.payload()) & {
        "title",
        "excerpt",
        "content",
        "snapshot",
        "media",
        "category_id",
        "categories",
        "url",
    }


def test_exact_four_publish_new_articles_and_at003_is_unrepresentable() -> None:
    assert ST1704_PUBLISH_NEW_ARTICLE_IDS == (
        "st1704-portable-power-station-guide",
        "st1704-anker-solix-c300-c800-c1000-differences",
        "st1704-countertop-dishwasher-for-small-households",
        "st1704-compact-robot-vacuum-shortlist",
    )
    with pytest.raises(PublicationOperatorFailure) as refused:
        CommittedReviewDraftBinding(
            article_id="st1703-first-suitcase-comparison",
            draft_post_id=19,
            packet_sha256="1" * 64,
            request_sha256="2" * 64,
            snapshot_payload_sha256="3" * 64,
            visible_content_sha256="4" * 64,
            public_slug="carry-on-suitcase-comparison",
        )
    assert refused.value.code is PublicationOperatorFailureCode.ARTICLE_NOT_ALLOWLISTED


def test_receipts_bind_exact_ttl_state_operation_and_success_code() -> None:
    candidate = proposal()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
        state=PublicationProposalState.PROPOSED,
        created_at=_timestamp(now),
        expires_at=_timestamp(now + timedelta(seconds=900)),
        replayed=False,
    )
    assert not receipt.is_expired(now)
    applied = PublicationApplyReceipt(
        proposal_id=candidate.proposal_id,
        operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
        result_code=PUBLICATION_OPERATOR_RESULT_CODE,
        replayed=False,
    )
    assert applied.public_payload()["state"] == "APPLIED"

    with pytest.raises(PublicationOperatorFailure) as invalid:
        PublicationApplyReceipt(
            proposal_id=candidate.proposal_id,
            operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
            result_code="THEME_UPDATE_APPLIED",
            replayed=False,
        )
    assert invalid.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


def test_status_requires_exact_gate_and_closed_state_counts() -> None:
    counts = tuple((state, 0) for state in PublicationProposalState)
    status = PublicationOperatorStatus(
        master_writes_enabled=True,
        publication_writes_enabled=False,
        writes_enabled=False,
        proposal_counts=counts,
    )
    assert status.public_payload()["supported_operations"] == ["PUBLISH_ST1704_ARTICLE"]
    with pytest.raises(PublicationOperatorFailure):
        PublicationOperatorStatus(
            master_writes_enabled=True,
            publication_writes_enabled=False,
            writes_enabled=True,
            proposal_counts=counts,
        )
