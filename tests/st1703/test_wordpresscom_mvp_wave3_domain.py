"""Focused authority and domain-boundary checks for approved ST-1703 Wave 3."""

from __future__ import annotations

from dataclasses import fields

import pytest

from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    MvpDraftBaseState,
    MvpDraftManualReviewState,
    MvpDraftObservation,
    MvpDraftOperationPreview,
    MvpDraftOperationState,
    MvpDraftPreview,
    MvpDraftReasonCode,
    MvpDraftResponseContext,
    MvpDraftResponseStage,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
)
from raos.ports.wordpresscom_mvp_drafts import WordPressComMvpDraftsPort


def test_wave3_authority_and_operation_order_are_closed() -> None:
    assert WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER == (
        "article-7-update",
        "page-about-create",
        "page-editorial-policy-create",
        "page-privacy-policy-create",
        "page-advertising-policy-create",
        "page-contact-create",
    )
    assert WORDPRESSCOM_MVP_WAVE3_PUBLICATION_AUTHORITY == "NONE"
    assert {member.value for member in MvpDraftOperationState} == {
        "NO_STATE",
        "REUSED_EXACT",
        "INTENT",
        "COMMITTED",
        "MUTATION_AMBIGUOUS",
        "RECONCILED_COMMITTED",
        "REFUSED_MISMATCH",
    }
    assert [field.name for field in fields(MvpDraftPreview)] == [
        "operations",
        "base_state",
        "affiliate_state",
        "affiliate_slot_count",
        "manual_review_state",
        "publication_authority",
    ]
    assert set(WordPressComMvpDraftsPort.__dict__) >= {"prepare", "preview"}
    assert "publish" not in WordPressComMvpDraftsPort.__dict__


def test_preview_is_redacted_and_cannot_gain_publication_authority() -> None:
    operations = tuple(
        MvpDraftOperationPreview(
            operation_id=operation_id,
            observation=MvpDraftObservation.EXACT,
            reason_code=MvpDraftReasonCode.EXACT_DESIRED,
        )
        for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
    )
    preview = MvpDraftPreview(
        operations=operations,
        base_state=MvpDraftBaseState.PREPARED,
        affiliate_state=MvpDraftAffiliateState.SLOTS_PENDING,
        affiliate_slot_count=0,
        manual_review_state=MvpDraftManualReviewState.NOT_READY,
    )
    assert str(preview) == "<redacted-wordpresscom-wave3>"
    assert "EXACT" not in repr(preview)
    assert preview.publication_authority == "NONE"
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        MvpDraftPreview(
            operations=operations,
            base_state=MvpDraftBaseState.PREPARED,
            affiliate_state=MvpDraftAffiliateState.SLOTS_VALIDATED,
            affiliate_slot_count=3,
            manual_review_state=MvpDraftManualReviewState.READY,
            publication_authority="PUBLISH",
        )
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"


def test_preview_rejects_mismatched_observation_reason_pair() -> None:
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        MvpDraftOperationPreview(
            operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
            observation=MvpDraftObservation.EXACT,
            reason_code=MvpDraftReasonCode.OBJECT_MISSING,
        )
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"


def test_preview_response_diagnostics_are_closed_value_free_reasons() -> None:
    diagnostic_reasons = {
        reason.value
        for reason in MvpDraftReasonCode
        if reason.value.startswith(("FULL_GET_", "PAGE_SCAN_"))
    }
    assert {
        "FULL_GET_TRANSPORT_INVALID",
        "FULL_GET_STATUS_INVALID",
        "FULL_GET_CONTENT_TYPE_INVALID",
        "FULL_GET_BOUNDED_JSON_INVALID",
        "FULL_GET_TOP_LEVEL_KEYS_INVALID",
        "FULL_GET_SITE_ID_INVALID",
        "FULL_GET_NESTED_SHAPE_INVALID",
        "FULL_GET_AUTHOR_SHAPE_INVALID",
        "FULL_GET_DISCUSSION_SHAPE_INVALID",
        "FULL_GET_DISCUSSION_TYPE_INVALID",
        "FULL_GET_DISCUSSION_REQUIRED_KEYS_MISSING",
        "FULL_GET_DISCUSSION_EXTRA_KEYS",
        "FULL_GET_PUBLICIZE_URLS_INVALID",
        "FULL_GET_IDENTIFIER_INVALID",
        "FULL_GET_SCALAR_FIELD_TYPE_INVALID",
        "FULL_GET_URL_INVALID",
        "FULL_GET_APPLICATION_INVARIANT_INVALID",
        "PAGE_SCAN_TRANSPORT_INVALID",
        "PAGE_SCAN_STATUS_INVALID",
        "PAGE_SCAN_CONTENT_TYPE_INVALID",
        "PAGE_SCAN_BOUNDED_JSON_INVALID",
        "PAGE_SCAN_TOP_LEVEL_KEYS_INVALID",
        "PAGE_SCAN_COLLECTION_SHAPE_INVALID",
        "PAGE_SCAN_ENTRY_SHAPE_INVALID",
        "PAGE_SCAN_SITE_ID_INVALID",
        "PAGE_SCAN_IDENTIFIER_INVALID",
        "PAGE_SCAN_SCALAR_FIELD_TYPE_INVALID",
        "PAGE_SCAN_APPLICATION_INVARIANT_INVALID",
    } == diagnostic_reasons
    for reason in diagnostic_reasons:
        assert all(
            forbidden not in reason
            for forbidden in (
                "HTTP://",
                "HTTPS://",
                "256699520",
                "283672805",
                "SHA256",
                "HTML",
                "BODY",
            )
        )


def test_preview_object_drift_diagnostics_are_closed_value_free_reasons() -> None:
    article_reasons = {
        reason
        for reason in MvpDraftReasonCode
        if reason is MvpDraftReasonCode.ARTICLE_APPROVED_BASELINE
        or reason.value.startswith("ARTICLE_")
    }
    page_reasons = {
        reason
        for reason in MvpDraftReasonCode
        if reason.value.startswith("PAGE_")
        and not reason.value.startswith("PAGE_SCAN_")
    }
    assert {reason.value for reason in article_reasons} == {
        "ARTICLE_APPROVED_BASELINE",
        "ARTICLE_MIXED_DESIRED_BASELINE_DRIFT",
        "ARTICLE_OBJECT_ID_DRIFT",
        "ARTICLE_SITE_ID_DRIFT",
        "ARTICLE_AUTHOR_ID_DRIFT",
        "ARTICLE_AUTHOR_NAME_DRIFT",
        "ARTICLE_BASELINE_MODIFIED_DRIFT",
        "ARTICLE_TITLE_DRIFT",
        "ARTICLE_CONTENT_DRIFT",
        "ARTICLE_SLUG_DRIFT",
        "ARTICLE_STATUS_DRIFT",
        "ARTICLE_TYPE_DRIFT",
        "ARTICLE_COMMENTS_OPEN_DRIFT",
        "ARTICLE_PINGS_OPEN_DRIFT",
        "ARTICLE_LIKES_ENABLED_DRIFT",
        "ARTICLE_SHARING_ENABLED_DRIFT",
        "ARTICLE_PUBLICIZE_URLS_DRIFT",
    }
    assert {reason.value for reason in page_reasons} == {
        "PAGE_SITE_ID_DRIFT",
        "PAGE_AUTHOR_ID_DRIFT",
        "PAGE_AUTHOR_NAME_DRIFT",
        "PAGE_TITLE_DRIFT",
        "PAGE_CONTENT_DRIFT",
        "PAGE_SLUG_DRIFT",
        "PAGE_STATUS_DRIFT",
        "PAGE_TYPE_DRIFT",
        "PAGE_COMMENTS_OPEN_DRIFT",
        "PAGE_PINGS_OPEN_DRIFT",
        "PAGE_LIKES_ENABLED_DRIFT",
        "PAGE_SHARING_ENABLED_DRIFT",
        "PAGE_PUBLICIZE_URLS_DRIFT",
    }
    for reason in article_reasons | page_reasons:
        rendered = reason.value
        assert rendered == rendered.upper()
        assert all(
            forbidden not in rendered
            for forbidden in (
                "HTTP://",
                "HTTPS://",
                "256699520",
                "283672805",
                "184A6214",
                "<A ",
                "PROVIDER_BODY",
            )
        )


@pytest.mark.parametrize(
    ("operation_id", "reason"),
    [
        (
            WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[1],
            MvpDraftReasonCode.ARTICLE_TITLE_DRIFT,
        ),
        (
            WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
            MvpDraftReasonCode.PAGE_TITLE_DRIFT,
        ),
    ],
)
def test_preview_rejects_object_drift_reason_for_wrong_operation_kind(
    operation_id: str, reason: MvpDraftReasonCode
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        MvpDraftOperationPreview(
            operation_id=operation_id,
            observation=MvpDraftObservation.DRIFT,
            reason_code=reason,
        )
    assert failure.value.code is WordPressComMvpDraftFailureCode.BINDING_INVALID


def test_preview_revalidates_mutated_object_drift_reason_operation_pair() -> None:
    value = MvpDraftOperationPreview(
        operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
        observation=MvpDraftObservation.DRIFT,
        reason_code=MvpDraftReasonCode.ARTICLE_TITLE_DRIFT,
    )
    object.__setattr__(value, "operation_id", WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[1])
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        value.__post_init__()
    assert failure.value.code is WordPressComMvpDraftFailureCode.BINDING_INVALID


def test_page_scan_reason_is_rejected_for_article_operation() -> None:
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        MvpDraftOperationPreview(
            operation_id=WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0],
            observation=MvpDraftObservation.DRIFT,
            reason_code=MvpDraftReasonCode.PAGE_SCAN_STATUS_INVALID,
        )
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"


@pytest.mark.parametrize(
    "stage",
    [
        MvpDraftResponseStage.AUTHOR_SHAPE,
        MvpDraftResponseStage.DISCUSSION_SHAPE,
        MvpDraftResponseStage.DISCUSSION_TYPE,
        MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING,
        MvpDraftResponseStage.DISCUSSION_EXTRA_KEYS,
    ],
)
def test_response_failure_rendering_is_generic_and_value_free(
    stage: MvpDraftResponseStage,
) -> None:
    failure = WordPressComMvpDraftFailure(
        WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
        response_stage=stage,
        response_context=MvpDraftResponseContext.ARTICLE_FULL_GET,
    )
    assert str(failure) == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert repr(failure) == (
        "WordPressComMvpDraftFailure('MVP_DRAFT_REMOTE_RESPONSE_INVALID')"
    )
    for forbidden in (
        "URL",
        "AUTHOR_SHAPE",
        "DISCUSSION_SHAPE",
        "DISCUSSION_TYPE",
        "DISCUSSION_REQUIRED_KEYS_MISSING",
        "DISCUSSION_EXTRA_KEYS",
        "ARTICLE_FULL_GET",
        "kurashierabinote",
        "provider-body",
        "256699520",
    ):
        assert forbidden not in str(failure)
        assert forbidden not in repr(failure)


@pytest.mark.parametrize(
    ("affiliate_state", "count", "manual_state"),
    [
        (
            MvpDraftAffiliateState.SLOTS_VALIDATED,
            0,
            MvpDraftManualReviewState.NOT_READY,
        ),
        (MvpDraftAffiliateState.SLOTS_PENDING, 3, MvpDraftManualReviewState.NOT_READY),
        (MvpDraftAffiliateState.SLOTS_INVALID, 1, MvpDraftManualReviewState.NOT_READY),
        (MvpDraftAffiliateState.NOT_EVALUATED, 1, MvpDraftManualReviewState.NOT_READY),
        (MvpDraftAffiliateState.SLOTS_PENDING, 0, MvpDraftManualReviewState.READY),
    ],
)
def test_preview_rejects_logically_inconsistent_affiliate_combinations(
    affiliate_state: MvpDraftAffiliateState,
    count: int,
    manual_state: MvpDraftManualReviewState,
) -> None:
    operations = tuple(
        MvpDraftOperationPreview(
            operation_id=operation_id,
            observation=MvpDraftObservation.EXACT,
            reason_code=MvpDraftReasonCode.EXACT_DESIRED,
        )
        for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        MvpDraftPreview(
            operations=operations,
            base_state=MvpDraftBaseState.PREPARED,
            affiliate_state=affiliate_state,
            affiliate_slot_count=count,
            manual_review_state=manual_state,
        )
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"


def test_preview_revalidates_object_setattr_mutations_with_sanitized_failure() -> None:
    operations = tuple(
        MvpDraftOperationPreview(
            operation_id=operation_id,
            observation=MvpDraftObservation.EXACT,
            reason_code=MvpDraftReasonCode.EXACT_DESIRED,
        )
        for operation_id in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER
    )
    preview = MvpDraftPreview(
        operations=operations,
        base_state=MvpDraftBaseState.PREPARED,
        affiliate_state=MvpDraftAffiliateState.SLOTS_PENDING,
        affiliate_slot_count=0,
        manual_review_state=MvpDraftManualReviewState.NOT_READY,
    )
    object.__setattr__(preview, "affiliate_slot_count", "0")
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        preview.__post_init__()
    assert failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"

    object.__setattr__(preview, "affiliate_slot_count", 0)
    object.__setattr__(operations[0], "reason_code", MvpDraftReasonCode.OBJECT_MISSING)
    with pytest.raises(WordPressComMvpDraftFailure) as operation_failure:
        preview.__post_init__()
    assert operation_failure.value.code.value == "MVP_DRAFT_BINDING_INVALID"
