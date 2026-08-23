"""Focused domain and recorded-response tests for SELF_HOSTED_EDITORIAL_PILOT_V1."""

from __future__ import annotations

import json

import pytest

from raos.adapters.self_hosted_editorial_pilot_json import (
    RecordedWordPressPublicReadAdapter,
    RecordedWordPressReviewDraftAdapter,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    PILOT_ARTICLE_IDS,
    PILOT_AUTHOR_NAME,
    PILOT_ORIGIN,
    PILOT_SNAPSHOT_META_KEY,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    ReviewDraftDisposition,
    ReviewDraftRequest,
    article_identity,
    bytes_sha256,
    canonical_json_bytes,
)


def request(
    *,
    packet_sha256: str = "a" * 64,
    content: str = '<p class="ks-lead">停電時に必要な条件を整理します。</p>',
) -> ReviewDraftRequest:
    article_id = "st1704-portable-power-station-guide"
    snapshot = PublicationSnapshot.bind(
        PublicationSnapshotPayload(
            article_id=article_id,
            packet_sha256=packet_sha256,
            slug="portable-power-station-guide",
            title="停電対策用ポータブル電源の選び方",
            seo_title="停電対策用ポータブル電源4モデル比較",
            description="容量・定格出力・持ち運びの条件から候補を整理します。",
            canonical_url=f"{PILOT_ORIGIN}/portable-power-station-guide/",
            og_title="停電対策用ポータブル電源の選び方",
            og_description="容量・定格出力・持ち運びの条件から候補を整理します。",
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
        public_slug=snapshot.payload.slug,
        excerpt=snapshot.payload.description,
        content=content,
        snapshot=snapshot,
    )


def recorded_post(
    candidate: ReviewDraftRequest, *, status: str = "draft"
) -> dict[str, object]:
    return {
        "content_raw": candidate.content,
        "excerpt_raw": candidate.excerpt,
        "id": 1704,
        "meta": {PILOT_SNAPSHOT_META_KEY: candidate.snapshot.json_string()},
        "slug": candidate.slug if status == "draft" else candidate.public_slug,
        "status": status,
        "title_raw": candidate.title,
        "type": "post",
    }


def envelope(
    candidate: ReviewDraftRequest,
    *,
    schema: str,
    response: object,
    status: int,
) -> bytes:
    return canonical_json_bytes(
        {
            "http_status": status,
            "origin": PILOT_ORIGIN,
            "request_sha256": candidate.request_sha256,
            "response": response,
            "schema": schema,
        }
    )


def test_allowlist_and_snapshot_request_are_closed_and_deterministic() -> None:
    candidate = request()

    assert len(PILOT_ARTICLE_IDS) == 5
    assert article_identity(candidate.article_id).article_type_code == "AT-001"
    assert set(candidate.wordpress_body()) == {
        "content",
        "excerpt",
        "meta",
        "slug",
        "status",
        "title",
    }
    assert candidate.wordpress_body()["status"] == "draft"
    assert set(candidate.wordpress_body()["meta"]) == {PILOT_SNAPSHOT_META_KEY}  # type: ignore[arg-type]
    wrapper = json.loads(candidate.snapshot.json_string())
    assert set(wrapper) == {"payload", "payload_sha256", "schema"}
    assert set(wrapper["payload"]) == {
        "article_id",
        "author_name",
        "canonical_url",
        "description",
        "modified_at",
        "og_description",
        "og_title",
        "packet_sha256",
        "published_at",
        "section",
        "seo_title",
        "slug",
        "title",
        "visible_content_sha256",
    }
    assert wrapper["payload"]["published_at"] is None
    assert wrapper["payload"]["modified_at"] is None
    assert wrapper["payload"]["seo_title"] == "停電対策用ポータブル電源4モデル比較"
    assert wrapper["payload"]["visible_content_sha256"] == bytes_sha256(
        candidate.content.encode()
    )


def test_same_visible_copy_with_new_evidence_packet_gets_new_snapshot_and_review_slug() -> (
    None
):
    first = request(packet_sha256="a" * 64)
    second = request(packet_sha256="b" * 64)

    assert first.content == second.content
    assert first.snapshot.payload.visible_content_sha256 == (
        second.snapshot.payload.visible_content_sha256
    )
    assert first.snapshot.payload.packet_sha256 == "a" * 64
    assert second.snapshot.payload.packet_sha256 == "b" * 64
    assert first.snapshot.payload_sha256 != second.snapshot.payload_sha256
    assert first.slug != second.slug
    assert first.request_sha256 != second.request_sha256
    assert (
        first.request_sha256
        == ReviewDraftRequest.bind(
            article_id=first.article_id,
            packet_sha256=first.packet_sha256,
            title=first.title,
            public_slug=first.public_slug,
            excerpt=first.excerpt,
            content=first.content,
            snapshot=first.snapshot,
        ).request_sha256
    )


@pytest.mark.parametrize(
    ("article_id", "slug", "section"),
    [
        ("not-allowlisted", "portable-power-station-guide", "備え"),
        (
            "st1704-portable-power-station-guide",
            "compact-robot-vacuum-shortlist",
            "備え",
        ),
        (
            "st1704-portable-power-station-guide",
            "portable-power-station-guide",
            "家事",
        ),
    ],
)
def test_snapshot_rejects_non_allowlisted_or_cross_article_identity(
    article_id: str, slug: str, section: str
) -> None:
    with pytest.raises(EditorialPilotFailure):
        PublicationSnapshotPayload(
            article_id=article_id,
            packet_sha256="b" * 64,
            slug=slug,
            title="記事タイトル",
            seo_title="SEO記事タイトル",
            description="記事の説明です。",
            canonical_url=f"{PILOT_ORIGIN}/{slug}/",
            og_title="記事タイトル",
            og_description="記事の説明です。",
            published_at=None,
            modified_at=None,
            author_name=PILOT_AUTHOR_NAME,
            section=section,
            visible_content_sha256="b" * 64,
        )


def test_recorded_create_and_public_verification_are_exact_and_non_live() -> None:
    candidate = request()
    create_bytes = envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_CREATE_REVIEW_DRAFT_V1",
        response=recorded_post(candidate),
        status=201,
    )
    receipt = RecordedWordPressReviewDraftAdapter().create(candidate, create_bytes)
    assert receipt.disposition is ReviewDraftDisposition.RECORDED_CREATED
    assert receipt.draft_id == 1704
    assert receipt.response_sha256 == bytes_sha256(create_bytes)
    assert receipt.recorded_evidence_only
    assert not receipt.live_authority
    assert not receipt.publication_authority

    public_bytes = envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_VERIFY_PUBLIC_V1",
        response=recorded_post(candidate, status="publish"),
        status=200,
    )
    verification = RecordedWordPressPublicReadAdapter().verify(candidate, public_bytes)
    assert verification.status == "publish"
    assert verification.recorded_evidence_only
    assert not verification.production_evidence


def test_recorded_adapter_rejects_extra_fields_status_and_ambiguous_recovery() -> None:
    candidate = request()
    post = recorded_post(candidate)
    post["publish"] = True
    invalid = envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_CREATE_REVIEW_DRAFT_V1",
        response=post,
        status=201,
    )
    with pytest.raises(EditorialPilotFailure) as extra:
        RecordedWordPressReviewDraftAdapter().create(candidate, invalid)
    assert extra.value.code is EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID

    recovery = envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_RECOVER_REVIEW_DRAFT_V1",
        response=[],
        status=200,
    )
    with pytest.raises(EditorialPilotFailure) as ambiguous:
        RecordedWordPressReviewDraftAdapter().recover(candidate, recovery)
    assert ambiguous.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS


def test_values_and_failures_do_not_disclose_article_content() -> None:
    candidate = request()
    assert "停電時" not in repr(candidate)
    failure = EditorialPilotFailure(EditorialPilotFailureCode.JOURNAL_AMBIGUOUS)
    assert "停電時" not in repr(failure)
    assert str(failure) == "JOURNAL_AMBIGUOUS"
