"""Focused state-machine and sanitized preview tests for ST-1703 Wave 3."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import json
from pathlib import Path
from typing import Iterator, cast

import pytest

from raos.adapters.wordpresscom_mvp_draft_https import (
    decode_wordpresscom_mvp_full_object,
)
from raos.application.editorial.wordpresscom_mvp_drafts import (
    build_bound_wordpresscom_mvp_content,
)
from raos.application.editorial.wordpresscom_mvp_preparation import (
    WordPressComMvpDraftPreparationService,
    _preview_object_drift_reason,
    _preview_response_reason,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    MvpDraftBaseState,
    MvpDraftManualReviewState,
    MvpMutationAcknowledgement,
    MvpDraftObservation,
    MvpDraftOperation,
    MvpDraftOperationPreview,
    MvpDraftOperationState,
    MvpDraftReasonCode,
    MvpDraftResponseContext,
    MvpDraftResponseStage,
    MvpPageEntry,
    MvpPageScan,
    MvpRemoteObject,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
)
from raos.ports.wordpresscom_mvp_draft_journal import MvpDraftJournalEntry


ROOT = Path(__file__).resolve().parents[2]
_FULL_GET_REASONS = {
    MvpDraftResponseStage.TRANSPORT: MvpDraftReasonCode.FULL_GET_TRANSPORT_INVALID,
    MvpDraftResponseStage.STATUS: MvpDraftReasonCode.FULL_GET_STATUS_INVALID,
    MvpDraftResponseStage.CONTENT_TYPE: MvpDraftReasonCode.FULL_GET_CONTENT_TYPE_INVALID,
    MvpDraftResponseStage.BOUNDED_JSON: MvpDraftReasonCode.FULL_GET_BOUNDED_JSON_INVALID,
    MvpDraftResponseStage.TOP_LEVEL_KEYS: MvpDraftReasonCode.FULL_GET_TOP_LEVEL_KEYS_INVALID,
    MvpDraftResponseStage.SITE_ID: MvpDraftReasonCode.FULL_GET_SITE_ID_INVALID,
    MvpDraftResponseStage.NESTED_SHAPE: MvpDraftReasonCode.FULL_GET_NESTED_SHAPE_INVALID,
    MvpDraftResponseStage.AUTHOR_SHAPE: MvpDraftReasonCode.FULL_GET_AUTHOR_SHAPE_INVALID,
    MvpDraftResponseStage.DISCUSSION_SHAPE: MvpDraftReasonCode.FULL_GET_DISCUSSION_SHAPE_INVALID,
    MvpDraftResponseStage.DISCUSSION_TYPE: MvpDraftReasonCode.FULL_GET_DISCUSSION_TYPE_INVALID,
    MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING: MvpDraftReasonCode.FULL_GET_DISCUSSION_REQUIRED_KEYS_MISSING,
    MvpDraftResponseStage.DISCUSSION_EXTRA_KEYS: MvpDraftReasonCode.FULL_GET_DISCUSSION_EXTRA_KEYS,
    MvpDraftResponseStage.PUBLICIZE_URLS: MvpDraftReasonCode.FULL_GET_PUBLICIZE_URLS_INVALID,
    MvpDraftResponseStage.IDENTIFIER: MvpDraftReasonCode.FULL_GET_IDENTIFIER_INVALID,
    MvpDraftResponseStage.SCALAR_FIELD_TYPE: MvpDraftReasonCode.FULL_GET_SCALAR_FIELD_TYPE_INVALID,
    MvpDraftResponseStage.URL: MvpDraftReasonCode.FULL_GET_URL_INVALID,
    MvpDraftResponseStage.APPLICATION_INVARIANT: MvpDraftReasonCode.FULL_GET_APPLICATION_INVARIANT_INVALID,
}
_PAGE_SCAN_REASONS = {
    MvpDraftResponseStage.TRANSPORT: MvpDraftReasonCode.PAGE_SCAN_TRANSPORT_INVALID,
    MvpDraftResponseStage.STATUS: MvpDraftReasonCode.PAGE_SCAN_STATUS_INVALID,
    MvpDraftResponseStage.CONTENT_TYPE: MvpDraftReasonCode.PAGE_SCAN_CONTENT_TYPE_INVALID,
    MvpDraftResponseStage.BOUNDED_JSON: MvpDraftReasonCode.PAGE_SCAN_BOUNDED_JSON_INVALID,
    MvpDraftResponseStage.TOP_LEVEL_KEYS: MvpDraftReasonCode.PAGE_SCAN_TOP_LEVEL_KEYS_INVALID,
    MvpDraftResponseStage.COLLECTION_SHAPE: MvpDraftReasonCode.PAGE_SCAN_COLLECTION_SHAPE_INVALID,
    MvpDraftResponseStage.ENTRY_SHAPE: MvpDraftReasonCode.PAGE_SCAN_ENTRY_SHAPE_INVALID,
    MvpDraftResponseStage.SITE_ID: MvpDraftReasonCode.PAGE_SCAN_SITE_ID_INVALID,
    MvpDraftResponseStage.IDENTIFIER: MvpDraftReasonCode.PAGE_SCAN_IDENTIFIER_INVALID,
    MvpDraftResponseStage.SCALAR_FIELD_TYPE: MvpDraftReasonCode.PAGE_SCAN_SCALAR_FIELD_TYPE_INVALID,
    MvpDraftResponseStage.APPLICATION_INVARIANT: MvpDraftReasonCode.PAGE_SCAN_APPLICATION_INVARIANT_INVALID,
}


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


def _remote(
    operation: MvpDraftOperation,
    *,
    object_id: str,
    baseline: bool = False,
) -> MvpRemoteObject:
    bundle = _bundle()
    return MvpRemoteObject(
        object_id=object_id,
        site_id="256699520",
        author_id="283672805",
        author_name="暮らし選びノート編集部",
        modified="2026-08-13T02:34:35+09:00" if baseline else "later",
        title=(
            "[レビュー用・未承認] "
            "機内持ち込み対応スーツケース3モデルを条件別比較｜軽さ・容量・開き方で選ぶ"
            if baseline
            else operation.title
        ),
        content=bundle.article_baseline_content if baseline else operation.content,
        url=(
            "https://kurashierabinote.wordpress.com/"
            if operation.object_type == "post"
            else f"https://kurashierabinote.wordpress.com/{operation.slug}/"
        ),
        slug=operation.slug,
        status="draft",
        object_type=operation.object_type,
        comments_open=baseline,
        pings_open=baseline,
        likes_enabled=baseline,
        sharing_enabled=baseline,
        publicize_urls_empty=True,
    )


def _remote_with_opaque_discussion_extension(
    operation: MvpDraftOperation,
    *,
    extension_name: str,
    extension_value: object,
    comments_open: bool = False,
    pings_open: bool = False,
) -> MvpRemoteObject:
    expected = _remote(operation, object_id="7")
    body = {
        "ID": expected.object_id,
        "site_ID": expected.site_id,
        "author": {"ID": expected.author_id, "name": expected.author_name},
        "modified": expected.modified,
        "title": expected.title,
        "content": expected.content,
        "URL": expected.url,
        "slug": expected.slug,
        "status": expected.status,
        "type": expected.object_type,
        "discussion": {
            extension_name: extension_value,
            "comments_open": comments_open,
            "pings_open": pings_open,
        },
        "likes_enabled": expected.likes_enabled,
        "sharing_enabled": expected.sharing_enabled,
        "publicize_URLs": [],
    }
    return decode_wordpresscom_mvp_full_object(
        json.dumps(
            body,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _filled_article_content() -> str:
    bundle = _bundle()
    content = bundle.operations[0].content
    for product in bundle.affiliate_product_names:
        placeholder = (
            f"<p>楽天公式アフィリエイトHTMLをここに貼り付け：{product}"
            "（画像幅128、価格表示なし）</p>"
        )
        filled = (
            '<div><a href="https://img.example/item" target="_blank" '
            'rel="sponsored noopener noreferrer"><img '
            'src="https://img.example/x.jpg" '
            f'alt="{product}" width="128" border="0"></a><br>'
            f'<a href="https://shop.example/item" rel="sponsored">{product}</a></div>'
        )
        content = content.replace(placeholder, filled, 1)
    return content


def _one_filled_slot() -> str:
    bundle = _bundle()
    product = bundle.affiliate_product_names[0]
    placeholder = (
        f"<p>楽天公式アフィリエイトHTMLをここに貼り付け：{product}"
        "（画像幅128、価格表示なし）</p>"
    )
    filled = (
        '<div><a href="https://img.example/item" target="_blank" '
        'rel="sponsored noopener noreferrer"><img '
        'src="https://img.example/x.jpg" '
        f'alt="{product}" width="128" border="0"></a><br>'
        f'<a href="https://shop.example/item" rel="sponsored">{product}</a></div>'
    )
    return bundle.operations[0].content.replace(placeholder, filled, 1)


class _Journal:
    def __init__(self) -> None:
        self.values: list[MvpDraftJournalEntry] = []
        self.appends: list[MvpDraftOperationState] = []

    @contextmanager
    def locked(self) -> Iterator[None]:
        yield

    def entries(self) -> tuple[MvpDraftJournalEntry, ...]:
        return tuple(self.values)

    def inspect(self) -> tuple[MvpDraftJournalEntry, ...]:
        return tuple(self.values)

    def append(
        self,
        *,
        operation_id: str,
        operation_binding_sha256: str,
        state: MvpDraftOperationState,
        reason_code: str,
        object_id: str | None,
    ) -> MvpDraftJournalEntry:
        previous = self.values[-1].record_sha256 if self.values else "0" * 64
        entry = MvpDraftJournalEntry(
            sequence=len(self.values) + 1,
            operation_id=operation_id,
            operation_binding_sha256=operation_binding_sha256,
            state=state,
            reason_code=reason_code,
            object_id=object_id,
            previous_record_sha256=previous,
            record_sha256=f"{len(self.values) + 1:064x}",
        )
        self.values.append(entry)
        self.appends.append(state)
        return entry


class _Provider:
    def __init__(self, bundle) -> None:
        self.bundle = bundle
        self.article_reads: list[MvpRemoteObject] = [
            _remote(bundle.operations[0], object_id="7")
        ]
        self.pages: dict[str, MvpRemoteObject] = {
            operation.slug: _remote(operation, object_id=str(10 + index))
            for index, operation in enumerate(bundle.operations[1:], start=1)
        }
        self.calls: list[str] = []
        self.posts = 0
        self.scan_override: object | None = None
        self.article_ack_override: object | None = None
        self.page_ack_override: object | None = None
        self.page_read_override: MvpRemoteObject | None = None
        self.scan_sequence: list[MvpPageScan] = []
        self.article_post_error: BaseException | None = None
        self.page_post_error: BaseException | None = None

    def read_article(self) -> MvpRemoteObject:
        self.calls.append("read_article")
        return (
            self.article_reads.pop(0)
            if len(self.article_reads) > 1
            else self.article_reads[0]
        )

    def scan_pages(self) -> MvpPageScan:
        self.calls.append("scan_pages")
        if self.scan_sequence:
            return self.scan_sequence.pop(0)
        if self.scan_override is not None:
            return cast(MvpPageScan, self.scan_override)
        return MvpPageScan(
            tuple(
                MvpPageEntry(remote.object_id, remote.site_id, "page", slug, "draft")
                for slug, remote in self.pages.items()
            )
        )

    def read_page(
        self, operation: MvpDraftOperation, object_id: str
    ) -> MvpRemoteObject:
        self.calls.append("read_page")
        if self.page_read_override is not None:
            return self.page_read_override
        assert self.pages[operation.slug].object_id == object_id
        return self.pages[operation.slug]

    def update_article_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement:
        self.calls.append("update_article_once")
        self.posts += 1
        if self.article_post_error is not None:
            raise self.article_post_error
        if self.article_ack_override is not None:
            return cast(MvpMutationAcknowledgement, self.article_ack_override)
        return MvpMutationAcknowledgement("7", "256699520")

    def create_page_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement:
        self.calls.append("create_page_once")
        self.posts += 1
        if self.page_post_error is not None:
            raise self.page_post_error
        if self.page_ack_override is not None:
            return cast(MvpMutationAcknowledgement, self.page_ack_override)
        object_id = str(100 + len(self.pages))
        self.pages[operation.slug] = _remote(operation, object_id=object_id)
        return MvpMutationAcknowledgement(object_id, "256699520")


class _DiagnosticProvider(_Provider):
    def __init__(
        self,
        bundle: object,
        *,
        failing_call: str,
        response_stage: MvpDraftResponseStage | None,
        fail_after: int = 0,
    ) -> None:
        super().__init__(bundle)
        self._failing_call = failing_call
        self._response_stage = response_stage
        self._fail_after = fail_after
        self._diagnostic_counts: dict[str, int] = {}

    def _maybe_fail(self, call: str) -> None:
        count = self._diagnostic_counts.get(call, 0)
        self._diagnostic_counts[call] = count + 1
        if call == self._failing_call and count >= self._fail_after:
            self.calls.append(call)
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
                response_stage=self._response_stage,
            )

    def read_article(self) -> MvpRemoteObject:
        self._maybe_fail("read_article")
        return super().read_article()

    def scan_pages(self) -> MvpPageScan:
        self._maybe_fail("scan_pages")
        return super().scan_pages()

    def read_page(
        self, operation: MvpDraftOperation, object_id: str
    ) -> MvpRemoteObject:
        self._maybe_fail("read_page")
        return super().read_page(operation, object_id)


def _service(provider: _Provider, journal: _Journal):
    return WordPressComMvpDraftPreparationService(
        bundle=provider.bundle, provider=provider, journal=journal
    )


def test_preview_is_read_only_sanitized_and_exact() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    journal = _Journal()
    preview = _service(provider, journal).preview()
    assert preview.base_state is MvpDraftBaseState.PREPARED
    assert preview.affiliate_state is MvpDraftAffiliateState.SLOTS_PENDING
    assert preview.manual_review_state is MvpDraftManualReviewState.NOT_READY
    assert all(
        item.observation is MvpDraftObservation.EXACT for item in preview.operations
    )
    assert journal.values == []
    assert str(preview) == "<redacted-wordpresscom-wave3>"


def test_opaque_discussion_extensions_are_dropped_before_preview_and_journal() -> None:
    bundle = _bundle()
    operation = bundle.operations[0]
    first_remote = _remote_with_opaque_discussion_extension(
        operation,
        extension_name="synthetic-extension-one",
        extension_value={"opaque-value": [1, 2, 3]},
    )
    second_remote = _remote_with_opaque_discussion_extension(
        operation,
        extension_name="synthetic-extension-two",
        extension_value=[None, True, {"renamed-value": "opaque-value"}],
    )
    assert first_remote == second_remote == _remote(operation, object_id="7")

    previews = []
    for remote in (first_remote, second_remote):
        provider = _Provider(bundle)
        provider.article_reads = [remote]
        journal = _Journal()
        preview = _service(provider, journal).preview()
        previews.append(preview)
        assert journal.values == []
    assert previews[0] == previews[1]

    provider = _Provider(bundle)
    provider.article_reads = [first_remote]
    journal = _Journal()
    prepared = _service(provider, journal).prepare()
    assert provider.posts == 0
    assert len(journal.values) == len(bundle.operations)
    assert all(
        entry.state is MvpDraftOperationState.REUSED_EXACT for entry in journal.values
    )
    rendered = f"{first_remote!s} {first_remote!r} {prepared!s} {journal.values!r}"
    for forbidden in (
        "synthetic-extension-one",
        "synthetic-extension-two",
        "opaque-value",
        "renamed-value",
    ):
        assert forbidden not in rendered


@pytest.mark.parametrize(
    ("comments_open", "pings_open"),
    [(True, False), (False, True)],
)
def test_opaque_extensions_do_not_weaken_required_false_discussion_proof(
    comments_open: bool,
    pings_open: bool,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        _remote_with_opaque_discussion_extension(
            bundle.operations[0],
            extension_name="synthetic-extension",
            extension_value={"opaque-value": True},
            comments_open=comments_open,
            pings_open=pings_open,
        )
    ]
    journal = _Journal()
    preview = _service(provider, journal).preview()
    assert preview.operations[0].observation is MvpDraftObservation.DRIFT
    assert preview.operations[0].reason_code is (
        MvpDraftReasonCode.ARTICLE_COMMENTS_OPEN_DRIFT
        if comments_open
        else MvpDraftReasonCode.ARTICLE_PINGS_OPEN_DRIFT
    )
    assert journal.values == []


@pytest.mark.parametrize(
    ("baseline", "field", "replacement", "expected_reason"),
    [
        (False, "object_id", "8", MvpDraftReasonCode.ARTICLE_OBJECT_ID_DRIFT),
        (False, "site_id", "256699521", MvpDraftReasonCode.ARTICLE_SITE_ID_DRIFT),
        (
            False,
            "author_id",
            "283672806",
            MvpDraftReasonCode.ARTICLE_AUTHOR_ID_DRIFT,
        ),
        (
            False,
            "author_name",
            "remote-author",
            MvpDraftReasonCode.ARTICLE_AUTHOR_NAME_DRIFT,
        ),
        (
            True,
            "modified",
            "remote-modified",
            MvpDraftReasonCode.ARTICLE_BASELINE_MODIFIED_DRIFT,
        ),
        (False, "title", "remote-title", MvpDraftReasonCode.ARTICLE_TITLE_DRIFT),
        (
            True,
            "content",
            "__DESIRED_CONTENT__",
            MvpDraftReasonCode.ARTICLE_CONTENT_DRIFT,
        ),
        (False, "slug", "article", MvpDraftReasonCode.ARTICLE_SLUG_DRIFT),
        (False, "status", "private", MvpDraftReasonCode.ARTICLE_STATUS_DRIFT),
        (False, "object_type", "page", MvpDraftReasonCode.ARTICLE_TYPE_DRIFT),
        (
            False,
            "comments_open",
            True,
            MvpDraftReasonCode.ARTICLE_COMMENTS_OPEN_DRIFT,
        ),
        (
            False,
            "pings_open",
            True,
            MvpDraftReasonCode.ARTICLE_PINGS_OPEN_DRIFT,
        ),
        (
            False,
            "likes_enabled",
            True,
            MvpDraftReasonCode.ARTICLE_LIKES_ENABLED_DRIFT,
        ),
        (
            False,
            "sharing_enabled",
            True,
            MvpDraftReasonCode.ARTICLE_SHARING_ENABLED_DRIFT,
        ),
        (
            False,
            "publicize_urls_empty",
            False,
            MvpDraftReasonCode.ARTICLE_PUBLICIZE_URLS_DRIFT,
        ),
    ],
)
def test_preview_classifies_each_article_exact_comparison_without_values(
    baseline: bool,
    field: str,
    replacement: object,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[0]
    if replacement == "__DESIRED_CONTENT__":
        replacement = operation.content
    provider.article_reads = [
        replace(
            _remote(operation, object_id="7", baseline=baseline),
            **{field: replacement},
        )
    ]
    preview = _service(provider, _Journal()).preview()
    article = preview.operations[0]
    assert article.observation is MvpDraftObservation.DRIFT
    assert article.reason_code is expected_reason
    rendered = f"{preview!s} {preview!r} {article.reason_code.value}"
    for forbidden in (
        "remote-author",
        "remote-modified",
        "remote-title",
        "private",
        "256699521",
        "283672806",
    ):
        assert forbidden not in rendered


def test_preview_distinguishes_exact_approved_article_baseline() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        _remote(bundle.operations[0], object_id="7", baseline=True)
    ]
    preview = _service(provider, _Journal()).preview()
    assert preview.operations[0] == MvpDraftOperationPreview(
        operation_id="article-7-update",
        observation=MvpDraftObservation.DRIFT,
        reason_code=MvpDraftReasonCode.ARTICLE_APPROVED_BASELINE,
    )
    assert preview.manual_review_state is MvpDraftManualReviewState.NOT_READY


def test_article_mixed_profile_precedes_individual_field_drift() -> None:
    bundle = _bundle()
    operation = bundle.operations[0]
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(
            _remote(operation, object_id="7"),
            title="[レビュー用・未承認] " + operation.title,
            comments_open=True,
            site_id="256699521",
        )
    ]
    preview = _service(provider, _Journal()).preview()
    assert preview.operations[0].reason_code is (
        MvpDraftReasonCode.ARTICLE_MIXED_DESIRED_BASELINE_DRIFT
    )


@pytest.mark.parametrize(
    ("field", "replacement", "expected_reason"),
    [
        ("site_id", "256699521", MvpDraftReasonCode.PAGE_SITE_ID_DRIFT),
        ("author_id", "283672806", MvpDraftReasonCode.PAGE_AUTHOR_ID_DRIFT),
        (
            "author_name",
            "remote-author",
            MvpDraftReasonCode.PAGE_AUTHOR_NAME_DRIFT,
        ),
        ("title", "remote-title", MvpDraftReasonCode.PAGE_TITLE_DRIFT),
        ("content", "remote-content", MvpDraftReasonCode.PAGE_CONTENT_DRIFT),
        ("slug", "remote-slug", MvpDraftReasonCode.PAGE_SLUG_DRIFT),
        ("status", "private", MvpDraftReasonCode.PAGE_STATUS_DRIFT),
        ("object_type", "post", MvpDraftReasonCode.PAGE_TYPE_DRIFT),
        ("comments_open", True, MvpDraftReasonCode.PAGE_COMMENTS_OPEN_DRIFT),
        ("pings_open", True, MvpDraftReasonCode.PAGE_PINGS_OPEN_DRIFT),
        ("likes_enabled", True, MvpDraftReasonCode.PAGE_LIKES_ENABLED_DRIFT),
        ("sharing_enabled", True, MvpDraftReasonCode.PAGE_SHARING_ENABLED_DRIFT),
        (
            "publicize_urls_empty",
            False,
            MvpDraftReasonCode.PAGE_PUBLICIZE_URLS_DRIFT,
        ),
    ],
)
def test_preview_classifies_each_existing_page_exact_comparison_without_values(
    field: str,
    replacement: object,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[1]
    exact = provider.pages[operation.slug]
    provider.pages = {operation.slug: exact}
    provider.page_read_override = replace(exact, **{field: replacement})
    preview = _service(provider, _Journal()).preview()
    about = preview.operations[1]
    assert about.observation is MvpDraftObservation.DRIFT
    assert about.reason_code is expected_reason
    rendered = f"{preview!s} {preview!r} {about.reason_code.value}"
    for forbidden in (
        "remote-author",
        "remote-title",
        "remote-content",
        "remote-slug",
        "private",
        "256699521",
        "283672806",
    ):
        assert forbidden not in rendered


def test_preview_object_drift_reason_precedence_and_invalid_input_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _bundle()
    operation = bundle.operations[0]
    remote = replace(
        _remote(operation, object_id="7"),
        site_id="256699521",
        author_id="283672806",
    )
    assert _preview_object_drift_reason(operation, remote, bundle) is (
        MvpDraftReasonCode.ARTICLE_SITE_ID_DRIFT
    )
    assert _preview_object_drift_reason(object(), remote, bundle) is (
        MvpDraftReasonCode.OBJECT_DRIFT
    )
    mutated = _remote(operation, object_id="7")
    object.__setattr__(mutated, "title", object())
    assert _preview_object_drift_reason(operation, mutated, bundle) is (
        MvpDraftReasonCode.OBJECT_DRIFT
    )
    monkeypatch.setattr(
        "raos.application.editorial.wordpresscom_mvp_preparation."
        "_article_drift_profile",
        lambda *_args: object(),
    )
    assert _preview_object_drift_reason(operation, remote, bundle) is (
        MvpDraftReasonCode.OBJECT_DRIFT
    )


def test_post_prepare_preview_keeps_generic_object_drift_reason() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[0]
    provider.article_reads = [
        _remote(operation, object_id="7"),
        replace(_remote(operation, object_id="7"), author_name="remote-author"),
    ]
    preview = _service(provider, _Journal()).prepare()
    assert preview.operations[0].observation is MvpDraftObservation.DRIFT
    assert preview.operations[0].reason_code is MvpDraftReasonCode.OBJECT_DRIFT
    assert provider.posts == 0


@pytest.mark.parametrize(
    ("state", "journal_reason", "expected_observation", "expected_reason"),
    [
        (
            MvpDraftOperationState.INTENT,
            "POST_BUDGET_CONSUMED",
            MvpDraftObservation.AMBIGUOUS,
            MvpDraftReasonCode.JOURNAL_AMBIGUOUS,
        ),
        (
            MvpDraftOperationState.REFUSED_MISMATCH,
            "BASELINE_MISMATCH",
            MvpDraftObservation.REFUSED,
            MvpDraftReasonCode.JOURNAL_REFUSED,
        ),
    ],
)
def test_journal_state_precedes_detailed_object_drift_diagnostic(
    state: MvpDraftOperationState,
    journal_reason: str,
    expected_observation: MvpDraftObservation,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    operation = bundle.operations[0]
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(_remote(operation, object_id="7"), author_name="remote-author")
    ]
    journal = _Journal()
    journal.append(
        operation_id=operation.operation_id,
        operation_binding_sha256=operation.binding_sha256(),
        state=state,
        reason_code=journal_reason,
        object_id="7" if state is MvpDraftOperationState.INTENT else None,
    )
    preview = _service(provider, journal).preview()
    assert preview.operations[0].observation is expected_observation
    assert preview.operations[0].reason_code is expected_reason


@pytest.mark.parametrize(("stage", "expected_reason"), _FULL_GET_REASONS.items())
def test_preview_classifies_article_full_get_stage_without_remote_values(
    stage: MvpDraftResponseStage,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    provider = _DiagnosticProvider(
        bundle, failing_call="read_article", response_stage=stage
    )
    preview = _service(provider, _Journal()).preview()
    article = preview.operations[0]
    assert article.observation is MvpDraftObservation.DRIFT
    assert article.reason_code is expected_reason
    rendered = f"{preview!s} {preview!r}"
    assert "provider-body" not in rendered
    assert "kurashierabinote" not in rendered
    assert "256699520" not in rendered


@pytest.mark.parametrize(("stage", "expected_reason"), _FULL_GET_REASONS.items())
def test_preview_classifies_existing_page_full_get_stage_by_operation(
    stage: MvpDraftResponseStage,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    provider = _DiagnosticProvider(
        bundle, failing_call="read_page", response_stage=stage
    )
    preview = _service(provider, _Journal()).preview()
    about = preview.operations[1]
    assert about.operation_id == "page-about-create"
    assert about.observation is MvpDraftObservation.DRIFT
    assert about.reason_code is expected_reason
    assert preview.operations[0].reason_code is MvpDraftReasonCode.EXACT_PLACEHOLDERS


@pytest.mark.parametrize(("stage", "expected_reason"), _PAGE_SCAN_REASONS.items())
def test_preview_distinguishes_page_scan_stage_from_existing_page_full_get(
    stage: MvpDraftResponseStage,
    expected_reason: MvpDraftReasonCode,
) -> None:
    bundle = _bundle()
    provider = _DiagnosticProvider(
        bundle, failing_call="scan_pages", response_stage=stage
    )
    preview = _service(provider, _Journal()).preview()
    for operation in preview.operations[1:]:
        assert operation.observation is MvpDraftObservation.DRIFT
        assert operation.reason_code is expected_reason


def test_preview_unknown_or_inconsistent_diagnostic_falls_back_to_generic_reason() -> (
    None
):
    bundle = _bundle()
    provider = _DiagnosticProvider(
        bundle, failing_call="read_article", response_stage=None
    )
    preview = _service(provider, _Journal()).preview()
    assert preview.operations[0].reason_code is MvpDraftReasonCode.RESPONSE_INVALID

    mismatch = WordPressComMvpDraftFailure(
        WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
        response_stage=MvpDraftResponseStage.URL,
        response_context=MvpDraftResponseContext.PAGE_FULL_GET,
    )
    assert _preview_response_reason(bundle.operations[0], mismatch) is (
        MvpDraftReasonCode.RESPONSE_INVALID
    )
    object.__setattr__(mismatch, "response_stage", "URL")
    assert _preview_response_reason(bundle.operations[0], mismatch) is (
        MvpDraftReasonCode.RESPONSE_INVALID
    )


def test_prepare_keeps_generic_failure_contract_for_diagnostic_stage() -> None:
    bundle = _bundle()
    provider = _DiagnosticProvider(
        bundle,
        failing_call="read_article",
        response_stage=MvpDraftResponseStage.URL,
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, _Journal()).prepare()
    assert failure.value.code is WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
    assert str(failure.value) == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert "URL" not in str(failure.value)
    assert provider.posts == 0


def test_preview_alone_admits_valid_manual_affiliate_slots() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(
            _remote(bundle.operations[0], object_id="7"),
            content=_filled_article_content(),
        )
    ]
    journal = _Journal()
    preview = _service(provider, journal).preview()
    assert preview.base_state is MvpDraftBaseState.PREPARED
    assert preview.affiliate_state is MvpDraftAffiliateState.SLOTS_VALIDATED
    assert preview.manual_review_state is MvpDraftManualReviewState.READY
    assert journal.values == []


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(_one_filled_slot(), id="mixed-slots"),
        pytest.param(
            _filled_article_content().replace('width="128"', 'width="127"', 1),
            id="invalid-slot",
        ),
        pytest.param(
            _filled_article_content().replace("<h1>", "<h1>outside-edit", 1),
            id="outside-edit",
        ),
    ],
)
def test_preview_classifies_invalid_affiliate_content_independently(
    content: str,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(_remote(bundle.operations[0], object_id="7"), content=content)
    ]
    journal = _Journal()
    preview = _service(provider, journal).preview()
    assert preview.operations[0].observation is MvpDraftObservation.DRIFT
    assert preview.operations[0].reason_code.value == "AFFILIATE_INVALID"
    assert preview.base_state is MvpDraftBaseState.DRIFT
    assert preview.affiliate_state is MvpDraftAffiliateState.SLOTS_INVALID
    assert preview.affiliate_slot_count == 0
    assert preview.manual_review_state is MvpDraftManualReviewState.NOT_READY
    assert journal.values == []


def test_article_new_intent_can_post_once_after_two_exact_baselines() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        _remote(bundle.operations[0], object_id="7", baseline=True),
        _remote(bundle.operations[0], object_id="7", baseline=True),
        _remote(bundle.operations[0], object_id="7"),
    ]
    journal = _Journal()
    _service(provider, journal).prepare()
    assert provider.posts == 1
    assert journal.appends[:2] == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.COMMITTED,
    ]
    assert provider.calls[:4] == [
        "read_article",
        "read_article",
        "update_article_once",
        "read_article",
    ]


@pytest.mark.parametrize(
    "existing_state",
    [MvpDraftOperationState.INTENT, MvpDraftOperationState.MUTATION_AMBIGUOUS],
)
def test_preexisting_intent_or_ambiguity_reconciles_without_post(
    existing_state: MvpDraftOperationState,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    journal = _Journal()
    operation = bundle.operations[0]
    journal.append(
        operation_id=operation.operation_id,
        operation_binding_sha256=operation.binding_sha256(),
        state=existing_state,
        reason_code="PREEXISTING",
        object_id="7",
    )
    _service(provider, journal).prepare()
    assert provider.posts == 0
    assert "update_article_once" not in provider.calls
    assert journal.appends[1] is MvpDraftOperationState.RECONCILED_COMMITTED


def test_preexisting_intent_with_filled_affiliate_slots_stays_ambiguous() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(
            _remote(bundle.operations[0], object_id="7"),
            content=_filled_article_content(),
        )
    ]
    journal = _Journal()
    operation = bundle.operations[0]
    journal.append(
        operation_id=operation.operation_id,
        operation_binding_sha256=operation.binding_sha256(),
        state=MvpDraftOperationState.INTENT,
        reason_code="PREEXISTING",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert provider.posts == 0
    assert journal.appends == [MvpDraftOperationState.INTENT]


@pytest.mark.parametrize("case", ["absent", "duplicate", "malformed", "mismatch"])
def test_page_reconciliation_preserves_ambiguity_for_every_nonexact_read(
    case: str,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[1]
    if case == "absent":
        provider.pages.pop(operation.slug)
    elif case == "duplicate":
        provider.scan_override = MvpPageScan(
            (
                MvpPageEntry("11", "256699520", "page", operation.slug, "draft"),
                MvpPageEntry("12", "256699520", "post", operation.slug, "draft"),
            )
        )
    elif case == "malformed":
        malformed = MvpPageScan(())
        object.__setattr__(malformed, "entries", ("not-an-entry",))
        provider.scan_override = malformed
    else:
        provider.pages[operation.slug] = replace(
            provider.pages[operation.slug], title="mismatch"
        )
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    journal.append(
        operation_id=operation.operation_id,
        operation_binding_sha256=operation.binding_sha256(),
        state=MvpDraftOperationState.INTENT,
        reason_code="POST_BUDGET_CONSUMED",
        object_id=None,
    )
    before = list(journal.appends)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert provider.posts == 0
    assert "create_page_once" not in provider.calls
    assert journal.appends == before


def test_forged_bundle_is_rejected_before_provider_access() -> None:
    bundle = _bundle()
    object.__setattr__(bundle.operations[0], "title", "forged")
    provider = _Provider(_bundle())
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        WordPressComMvpDraftPreparationService(
            bundle=bundle,
            provider=provider,
            journal=journal,
        )
    assert failure.value.code.value == "MVP_DRAFT_CONTENT_INVALID"
    assert provider.calls == []
    assert journal.values == []


def test_second_article_baseline_race_refuses_without_post() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        _remote(bundle.operations[0], object_id="7", baseline=True),
        replace(
            _remote(bundle.operations[0], object_id="7", baseline=True), modified="race"
        ),
    ]
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REFUSED_MISMATCH"
    assert provider.posts == 0
    assert journal.appends == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.REFUSED_MISMATCH,
    ]


def test_page_missing_scan_intent_second_scan_create_and_readback() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    provider.pages.pop("about")
    preview = _service(provider, journal).prepare()
    assert provider.posts == 1
    assert preview.base_state is MvpDraftBaseState.PREPARED
    assert journal.appends[1:3] == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.COMMITTED,
    ]


def test_wrong_author_name_blocks_before_intent_or_post() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(
            _remote(bundle.operations[0], object_id="7", baseline=True),
            author_name="wrong",
        )
    ]
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure):
        _service(provider, journal).prepare()
    assert provider.posts == 0
    assert journal.appends == [MvpDraftOperationState.REFUSED_MISMATCH]


@pytest.mark.parametrize(
    "changes",
    [
        {"object_id": "8"},
        {"site_id": "256699521"},
        {"author_id": "283672806"},
        {"author_name": "wrong"},
        {"title": "wrong"},
        {"slug": "wrong"},
        {"status": "publish"},
        {"object_type": "page"},
        {"comments_open": True},
        {"pings_open": True},
        {"likes_enabled": True},
        {"sharing_enabled": True},
        {"publicize_urls_empty": False},
    ],
)
def test_article_identity_and_safety_mismatch_refuses_without_post(
    changes: dict[str, object],
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(_remote(bundle.operations[0], object_id="7"), **changes)
    ]
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REFUSED_MISMATCH"
    assert provider.posts == 0
    assert journal.appends == [MvpDraftOperationState.REFUSED_MISMATCH]


@pytest.mark.parametrize(
    "url",
    [
        "http://kurashierabinote.wordpress.com/?p=7",
        "https://user@kurashierabinote.wordpress.com/?p=7",
        "https://kurashierabinote.wordpress.com:443/?p=7",
        "https://kurashierabinote.wordpress.com/?p=7#fragment",
        "https://kurashierabinote.wordpress.com/\\evil",
        "https://kurashierabinote.wordpress.com/%0a",
        "https://kurashierabinote.wordpress.com/%ZZ",
        "https://example.invalid/?p=7",
    ],
)
def test_application_boundary_independently_refuses_unsafe_target_url(
    url: str,
) -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(_remote(bundle.operations[0], object_id="7"), url=url)
    ]
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert provider.posts == 0
    assert journal.values == []


def test_application_boundary_allows_target_host_query_metadata() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(
            _remote(bundle.operations[0], object_id="7"),
            url="https://kurashierabinote.wordpress.com/?p=7",
        )
    ]
    journal = _Journal()
    preview = _service(provider, journal).preview()
    assert preview.operations[0].observation is MvpDraftObservation.EXACT
    assert journal.values == []


def test_application_revalidates_mutated_remote_post_init() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    remote = _remote(bundle.operations[0], object_id="7")
    object.__setattr__(remote, "comments_open", "false")
    provider.article_reads = [remote]
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert provider.posts == 0


def test_preview_classifies_mutated_remote_as_application_invariant_only() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    remote = _remote(bundle.operations[0], object_id="7")
    object.__setattr__(remote, "comments_open", "provider-value")
    provider.article_reads = [remote]
    preview = _service(provider, _Journal()).preview()
    assert preview.operations[0].reason_code is (
        MvpDraftReasonCode.FULL_GET_APPLICATION_INVARIANT_INVALID
    )
    assert "provider-value" not in str(preview)
    assert "provider-value" not in repr(preview)


def test_application_revalidates_exact_scan_type_entries_and_post_init() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    entry = MvpPageEntry("11", "256699520", "page", "about", "draft")
    object.__setattr__(entry, "object_id", "011")
    provider.scan_override = MvpPageScan((entry,))
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert provider.posts == 0


def test_article_mutated_acknowledgement_is_ambiguous_and_not_committed() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        _remote(bundle.operations[0], object_id="7", baseline=True),
        _remote(bundle.operations[0], object_id="7", baseline=True),
    ]
    acknowledgement = MvpMutationAcknowledgement("7", "256699520")
    object.__setattr__(acknowledgement, "object_id", "07")
    provider.article_ack_override = acknowledgement
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert provider.posts == 1
    assert journal.appends[-1] is MvpDraftOperationState.MUTATION_AMBIGUOUS
    assert MvpDraftOperationState.COMMITTED not in journal.appends


def test_article_post_uncertainty_persists_and_later_run_never_resends() -> None:
    bundle = _bundle()
    first = _Provider(bundle)
    first.article_reads = [
        _remote(bundle.operations[0], object_id="7", baseline=True),
        _remote(bundle.operations[0], object_id="7", baseline=True),
    ]
    first.article_post_error = OSError("synthetic socket uncertainty")
    journal = _Journal()
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(first, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert first.posts == 1
    assert journal.appends == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.MUTATION_AMBIGUOUS,
    ]

    later = _Provider(bundle)
    later.article_reads = [_remote(bundle.operations[0], object_id="7", baseline=True)]
    with pytest.raises(WordPressComMvpDraftFailure) as later_failure:
        _service(later, journal).prepare()
    assert later_failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert later.posts == 0
    assert "update_article_once" not in later.calls
    assert journal.appends == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.MUTATION_AMBIGUOUS,
    ]


def test_exact_existing_article_and_pages_reuse_without_any_post() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    journal = _Journal()
    preview = _service(provider, journal).prepare()
    assert provider.posts == 0
    assert journal.appends == [MvpDraftOperationState.REUSED_EXACT] * 6
    assert preview.base_state is MvpDraftBaseState.PREPARED


def test_page_duplicate_slug_refuses_before_intent_or_post() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[1]
    provider.scan_sequence = [
        MvpPageScan(
            (
                MvpPageEntry("11", "256699520", "page", operation.slug, "draft"),
                MvpPageEntry("12", "256699520", "post", operation.slug, "draft"),
            )
        )
    ]
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REFUSED_MISMATCH"
    assert provider.posts == 0
    assert journal.appends[-1] is MvpDraftOperationState.REFUSED_MISMATCH


def test_page_second_scan_collision_refuses_after_intent_without_post() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    operation = bundle.operations[1]
    provider.scan_sequence = [
        MvpPageScan(()),
        MvpPageScan(
            (MvpPageEntry("11", "256699520", "page", operation.slug, "draft"),)
        ),
    ]
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_REFUSED_MISMATCH"
    assert provider.posts == 0
    assert journal.appends[-2:] == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.REFUSED_MISMATCH,
    ]


def test_page_post_uncertainty_never_resends_on_later_absent_reconciliation() -> None:
    bundle = _bundle()
    first = _Provider(bundle)
    first.pages.pop("about")
    first.page_post_error = OSError("synthetic page socket uncertainty")
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure):
        _service(first, journal).prepare()
    assert first.posts == 1
    assert journal.appends[-2:] == [
        MvpDraftOperationState.INTENT,
        MvpDraftOperationState.MUTATION_AMBIGUOUS,
    ]

    later = _Provider(bundle)
    later.pages.pop("about")
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(later, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert later.posts == 0
    assert "create_page_once" not in later.calls


def test_terminal_predecessor_drift_stops_before_later_operations() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.article_reads = [
        replace(_remote(bundle.operations[0], object_id="7"), title="drift")
    ]
    journal = _Journal()
    operation = bundle.operations[0]
    journal.append(
        operation_id=operation.operation_id,
        operation_binding_sha256=operation.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_DRIFT"
    assert provider.posts == 0
    assert provider.calls == ["read_article"]


def test_page_readback_must_match_acknowledged_object_id() -> None:
    bundle = _bundle()
    provider = _Provider(bundle)
    provider.pages.pop("about")
    provider.page_ack_override = MvpMutationAcknowledgement("88", "256699520")
    provider.page_read_override = _remote(bundle.operations[1], object_id="89")
    journal = _Journal()
    article = bundle.operations[0]
    journal.append(
        operation_id=article.operation_id,
        operation_binding_sha256=article.binding_sha256(),
        state=MvpDraftOperationState.REUSED_EXACT,
        reason_code="EXACT_DESIRED",
        object_id="7",
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        _service(provider, journal).prepare()
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert provider.posts == 1
    assert journal.appends[-1] is MvpDraftOperationState.MUTATION_AMBIGUOUS
