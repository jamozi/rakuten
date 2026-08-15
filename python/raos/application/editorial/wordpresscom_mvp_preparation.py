"""Fail-closed prepare and read-only preview orchestration for WordPress.com Wave 3."""

from __future__ import annotations

from enum import Enum, auto
import re
from typing import NoReturn, cast
from urllib.parse import urlsplit

from raos.application.editorial.wordpresscom_mvp_affiliate import (
    validate_wordpresscom_mvp_affiliate_content,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftAffiliateState,
    MvpDraftBaseState,
    MvpDraftContentBundle,
    MvpDraftManualReviewState,
    MvpDraftObservation,
    MvpDraftOperation,
    MvpDraftOperationPreview,
    MvpDraftOperationState,
    MvpDraftPreview,
    MvpDraftReasonCode,
    MvpDraftResponseContext,
    MvpDraftResponseStage,
    MvpMutationAcknowledgement,
    MvpPageEntry,
    MvpPageScan,
    MvpRemoteObject,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_MODIFIED,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
    WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID,
    WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME,
    WORDPRESSCOM_MVP_WAVE3_SITE_ID,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
    normalize_wordpresscom_mvp_id,
    normalize_wordpresscom_mvp_line_endings,
)
from raos.ports.wordpresscom_mvp_draft_journal import (
    MvpDraftJournalEntry,
    WordPressComMvpDraftJournalPort,
)
from raos.ports.wordpresscom_mvp_drafts import WordPressComMvpFixedProviderPort


_EXACT_TERMINAL = {
    MvpDraftOperationState.REUSED_EXACT,
    MvpDraftOperationState.COMMITTED,
    MvpDraftOperationState.RECONCILED_COMMITTED,
}
_TARGET_HOST = "kurashierabinote.wordpress.com"
_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})", re.ASCII)
_FULL_GET_PREVIEW_REASON_BY_STAGE = {
    MvpDraftResponseStage.TRANSPORT: MvpDraftReasonCode.FULL_GET_TRANSPORT_INVALID,
    MvpDraftResponseStage.STATUS: MvpDraftReasonCode.FULL_GET_STATUS_INVALID,
    MvpDraftResponseStage.CONTENT_TYPE: (
        MvpDraftReasonCode.FULL_GET_CONTENT_TYPE_INVALID
    ),
    MvpDraftResponseStage.BOUNDED_JSON: (
        MvpDraftReasonCode.FULL_GET_BOUNDED_JSON_INVALID
    ),
    MvpDraftResponseStage.TOP_LEVEL_KEYS: (
        MvpDraftReasonCode.FULL_GET_TOP_LEVEL_KEYS_INVALID
    ),
    MvpDraftResponseStage.SITE_ID: MvpDraftReasonCode.FULL_GET_SITE_ID_INVALID,
    MvpDraftResponseStage.NESTED_SHAPE: (
        MvpDraftReasonCode.FULL_GET_NESTED_SHAPE_INVALID
    ),
    MvpDraftResponseStage.AUTHOR_SHAPE: (
        MvpDraftReasonCode.FULL_GET_AUTHOR_SHAPE_INVALID
    ),
    MvpDraftResponseStage.DISCUSSION_SHAPE: (
        MvpDraftReasonCode.FULL_GET_DISCUSSION_SHAPE_INVALID
    ),
    MvpDraftResponseStage.DISCUSSION_TYPE: (
        MvpDraftReasonCode.FULL_GET_DISCUSSION_TYPE_INVALID
    ),
    MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING: (
        MvpDraftReasonCode.FULL_GET_DISCUSSION_REQUIRED_KEYS_MISSING
    ),
    MvpDraftResponseStage.DISCUSSION_EXTRA_KEYS: (
        MvpDraftReasonCode.FULL_GET_DISCUSSION_EXTRA_KEYS
    ),
    MvpDraftResponseStage.PUBLICIZE_URLS: (
        MvpDraftReasonCode.FULL_GET_PUBLICIZE_URLS_INVALID
    ),
    MvpDraftResponseStage.IDENTIFIER: (MvpDraftReasonCode.FULL_GET_IDENTIFIER_INVALID),
    MvpDraftResponseStage.SCALAR_FIELD_TYPE: (
        MvpDraftReasonCode.FULL_GET_SCALAR_FIELD_TYPE_INVALID
    ),
    MvpDraftResponseStage.URL: MvpDraftReasonCode.FULL_GET_URL_INVALID,
    MvpDraftResponseStage.APPLICATION_INVARIANT: (
        MvpDraftReasonCode.FULL_GET_APPLICATION_INVARIANT_INVALID
    ),
}
_PAGE_SCAN_PREVIEW_REASON_BY_STAGE = {
    MvpDraftResponseStage.TRANSPORT: MvpDraftReasonCode.PAGE_SCAN_TRANSPORT_INVALID,
    MvpDraftResponseStage.STATUS: MvpDraftReasonCode.PAGE_SCAN_STATUS_INVALID,
    MvpDraftResponseStage.CONTENT_TYPE: (
        MvpDraftReasonCode.PAGE_SCAN_CONTENT_TYPE_INVALID
    ),
    MvpDraftResponseStage.BOUNDED_JSON: (
        MvpDraftReasonCode.PAGE_SCAN_BOUNDED_JSON_INVALID
    ),
    MvpDraftResponseStage.TOP_LEVEL_KEYS: (
        MvpDraftReasonCode.PAGE_SCAN_TOP_LEVEL_KEYS_INVALID
    ),
    MvpDraftResponseStage.COLLECTION_SHAPE: (
        MvpDraftReasonCode.PAGE_SCAN_COLLECTION_SHAPE_INVALID
    ),
    MvpDraftResponseStage.ENTRY_SHAPE: (
        MvpDraftReasonCode.PAGE_SCAN_ENTRY_SHAPE_INVALID
    ),
    MvpDraftResponseStage.SITE_ID: MvpDraftReasonCode.PAGE_SCAN_SITE_ID_INVALID,
    MvpDraftResponseStage.IDENTIFIER: (MvpDraftReasonCode.PAGE_SCAN_IDENTIFIER_INVALID),
    MvpDraftResponseStage.SCALAR_FIELD_TYPE: (
        MvpDraftReasonCode.PAGE_SCAN_SCALAR_FIELD_TYPE_INVALID
    ),
    MvpDraftResponseStage.APPLICATION_INVARIANT: (
        MvpDraftReasonCode.PAGE_SCAN_APPLICATION_INVARIANT_INVALID
    ),
}


class _ArticleDriftProfile(Enum):
    """Closed in-memory profile selector; no remote value can escape through it."""

    DESIRED = auto()
    BASELINE = auto()
    MIXED = auto()
    UNKNOWN = auto()


def _fail(code: WordPressComMvpDraftFailureCode) -> NoReturn:
    fail_wordpresscom_mvp_draft(code)


def _response_fail(stage: MvpDraftResponseStage) -> NoReturn:
    fail_wordpresscom_mvp_draft(
        WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
        response_stage=stage,
    )


def _raise_with_response_context(
    error: WordPressComMvpDraftFailure,
    context: MvpDraftResponseContext,
) -> NoReturn:
    if (
        type(error) is WordPressComMvpDraftFailure
        and error.code
        in {
            WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID,
            WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
        }
        and type(error.response_stage) is MvpDraftResponseStage
        and type(context) is MvpDraftResponseContext
    ):
        fail_wordpresscom_mvp_draft(
            error.code,
            response_stage=error.response_stage,
            response_context=context,
        )
    raise error from None


def _preview_response_reason(
    operation: MvpDraftOperation,
    error: WordPressComMvpDraftFailure,
) -> MvpDraftReasonCode:
    """Project only exact stage/context pairs; every unknown form stays generic."""

    if (
        type(operation) is not MvpDraftOperation
        or type(error) is not WordPressComMvpDraftFailure
        or type(error.response_stage) is not MvpDraftResponseStage
        or type(error.response_context) is not MvpDraftResponseContext
    ):
        return MvpDraftReasonCode.RESPONSE_INVALID
    if (
        operation.object_type == "post"
        and error.response_context is MvpDraftResponseContext.ARTICLE_FULL_GET
    ) or (
        operation.object_type == "page"
        and error.response_context is MvpDraftResponseContext.PAGE_FULL_GET
    ):
        return _FULL_GET_PREVIEW_REASON_BY_STAGE.get(
            error.response_stage, MvpDraftReasonCode.RESPONSE_INVALID
        )
    if (
        operation.object_type == "page"
        and error.response_context is MvpDraftResponseContext.PAGE_SCAN
    ):
        return _PAGE_SCAN_PREVIEW_REASON_BY_STAGE.get(
            error.response_stage, MvpDraftReasonCode.RESPONSE_INVALID
        )
    return MvpDraftReasonCode.RESPONSE_INVALID


def _require_exact_target_url(value: object) -> str:
    """Revalidate the approved target independently of any outward adapter."""

    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or not value.isascii()
        or any(ord(character) <= 32 or ord(character) == 127 for character in value)
        or "\\" in value
        or _MALFORMED_PERCENT.search(value) is not None
    ):
        _response_fail(MvpDraftResponseStage.URL)
    if any(
        int(match.group(1), 16) <= 32 or int(match.group(1), 16) in {92, 127}
        for match in _PERCENT_ESCAPE.finditer(value)
    ):
        _response_fail(MvpDraftResponseStage.URL)
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _response_fail(MvpDraftResponseStage.URL)
    if (
        parsed.scheme != "https"
        or parsed.hostname != _TARGET_HOST
        or parsed.netloc != _TARGET_HOST
        or port is not None
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or parsed.fragment
        or not value.startswith(f"https://{_TARGET_HOST}/")
    ):
        _response_fail(MvpDraftResponseStage.URL)
    return value


def _validate_remote(value: object) -> MvpRemoteObject:
    if type(value) is not MvpRemoteObject:
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
    try:
        value.__post_init__()
        normalize_wordpresscom_mvp_id(value.object_id)
        normalize_wordpresscom_mvp_id(value.site_id)
        normalize_wordpresscom_mvp_id(value.author_id)
    except WordPressComMvpDraftFailure:
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
    _require_exact_target_url(value.url)
    return value


def _validate_scan(value: object) -> MvpPageScan:
    if type(value) is not MvpPageScan:
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
    try:
        value.__post_init__()
        for entry in value.entries:
            if type(entry) is not MvpPageEntry:
                _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
            entry.__post_init__()
            normalize_wordpresscom_mvp_id(entry.object_id)
            normalize_wordpresscom_mvp_id(entry.site_id)
    except WordPressComMvpDraftFailure:
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
    return value


def _validate_acknowledgement(value: object) -> MvpMutationAcknowledgement:
    if type(value) is not MvpMutationAcknowledgement:
        _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
    value.__post_init__()
    normalize_wordpresscom_mvp_id(value.object_id)
    normalize_wordpresscom_mvp_id(value.site_id)
    return value


def _history(
    entries: tuple[MvpDraftJournalEntry, ...], operation: MvpDraftOperation
) -> tuple[MvpDraftJournalEntry, ...]:
    result = tuple(
        entry for entry in entries if entry.operation_id == operation.operation_id
    )
    if any(
        entry.operation_binding_sha256 != operation.binding_sha256() for entry in result
    ):
        _fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    return result


def _exact_common(remote: MvpRemoteObject, operation: MvpDraftOperation) -> bool:
    return (
        remote.site_id == WORDPRESSCOM_MVP_WAVE3_SITE_ID
        and remote.author_id == WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID
        and remote.author_name == WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME
        and remote.title == operation.title
        and normalize_wordpresscom_mvp_line_endings(remote.content) == operation.content
        and remote.slug == operation.slug
        and remote.status == "draft"
        and remote.object_type == operation.object_type
        and remote.comments_open is False
        and remote.pings_open is False
        and remote.likes_enabled is False
        and remote.sharing_enabled is False
        and remote.publicize_urls_empty is True
    )


def _exact_common_outside_slots(
    remote: MvpRemoteObject, operation: MvpDraftOperation, bundle: MvpDraftContentBundle
) -> bool:
    if not _article_non_content_exact(remote, operation):
        return False
    try:
        state, count = validate_wordpresscom_mvp_affiliate_content(
            content=remote.content,
            placeholder_content=operation.content,
            product_names=bundle.affiliate_product_names,
        )
    except WordPressComMvpDraftFailure:
        return False
    return state is MvpDraftAffiliateState.SLOTS_VALIDATED and count == 3


def _article_non_content_exact(
    remote: MvpRemoteObject, operation: MvpDraftOperation
) -> bool:
    return (
        remote.object_id == WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID
        and remote.site_id == WORDPRESSCOM_MVP_WAVE3_SITE_ID
        and remote.author_id == WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID
        and remote.author_name == WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME
        and remote.title == operation.title
        and remote.slug == operation.slug
        and remote.status == "draft"
        and remote.object_type == operation.object_type
        and remote.comments_open is False
        and remote.pings_open is False
        and remote.likes_enabled is False
        and remote.sharing_enabled is False
        and remote.publicize_urls_empty is True
    )


def _article_is_desired(remote: MvpRemoteObject, operation: MvpDraftOperation) -> bool:
    return remote.object_id == WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID and _exact_common(
        remote, operation
    )


def _article_is_baseline(
    remote: MvpRemoteObject, bundle: MvpDraftContentBundle
) -> bool:
    return (
        remote.object_id == WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID
        and remote.site_id == WORDPRESSCOM_MVP_WAVE3_SITE_ID
        and remote.author_id == WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID
        and remote.author_name == WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME
        and remote.modified == WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_MODIFIED
        and remote.title == WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE
        and normalize_wordpresscom_mvp_line_endings(remote.content)
        == bundle.article_baseline_content
        and remote.slug == ""
        and remote.status == "draft"
        and remote.object_type == "post"
        and remote.comments_open is True
        and remote.pings_open is True
        and remote.likes_enabled is True
        and remote.sharing_enabled is True
        and remote.publicize_urls_empty is True
    )


def _article_drift_profile(
    remote: MvpRemoteObject,
    operation: MvpDraftOperation,
    bundle: MvpDraftContentBundle,
) -> _ArticleDriftProfile:
    """Select a fixed desired/baseline profile without retaining remote values."""

    comparisons = (
        (remote.title, operation.title, WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE),
        (
            normalize_wordpresscom_mvp_line_endings(remote.content),
            operation.content,
            bundle.article_baseline_content,
        ),
        (remote.comments_open, False, True),
        (remote.pings_open, False, True),
        (remote.likes_enabled, False, True),
        (remote.sharing_enabled, False, True),
    )
    desired_count = 0
    baseline_count = 0
    for actual, desired, baseline in comparisons:
        if actual == desired:
            desired_count += 1
        elif actual == baseline:
            baseline_count += 1
    if desired_count >= len(comparisons) - 1:
        return _ArticleDriftProfile.DESIRED
    if baseline_count >= len(comparisons) - 1:
        return _ArticleDriftProfile.BASELINE
    if desired_count and baseline_count:
        return _ArticleDriftProfile.MIXED
    if desired_count:
        return _ArticleDriftProfile.DESIRED
    if baseline_count:
        return _ArticleDriftProfile.BASELINE
    return _ArticleDriftProfile.UNKNOWN


def _preview_drift_inputs_are_valid(
    operation: object, remote: object, bundle: object
) -> bool:
    """Revalidate exact fixed inputs before projecting any detailed reason."""

    if (
        type(operation) is not MvpDraftOperation
        or type(remote) is not MvpRemoteObject
        or type(bundle) is not MvpDraftContentBundle
    ):
        return False
    try:
        bundle.__post_init__()
        operation.__post_init__()
        remote.__post_init__()
        normalize_wordpresscom_mvp_id(remote.object_id)
        normalize_wordpresscom_mvp_id(remote.site_id)
        normalize_wordpresscom_mvp_id(remote.author_id)
        _require_exact_target_url(remote.url)
    except Exception:
        return False
    return any(candidate is operation for candidate in bundle.operations)


def _article_preview_drift_reason(
    remote: MvpRemoteObject,
    operation: MvpDraftOperation,
    bundle: MvpDraftContentBundle,
) -> MvpDraftReasonCode:
    if _article_is_baseline(remote, bundle):
        return MvpDraftReasonCode.ARTICLE_APPROVED_BASELINE
    profile = _article_drift_profile(remote, operation, bundle)
    if type(profile) is not _ArticleDriftProfile:
        return MvpDraftReasonCode.OBJECT_DRIFT
    if profile is _ArticleDriftProfile.MIXED:
        return MvpDraftReasonCode.ARTICLE_MIXED_DESIRED_BASELINE_DRIFT
    if profile is _ArticleDriftProfile.UNKNOWN:
        return MvpDraftReasonCode.OBJECT_DRIFT

    if remote.object_id != WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID:
        return MvpDraftReasonCode.ARTICLE_OBJECT_ID_DRIFT
    if remote.site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID:
        return MvpDraftReasonCode.ARTICLE_SITE_ID_DRIFT
    if remote.author_id != WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID:
        return MvpDraftReasonCode.ARTICLE_AUTHOR_ID_DRIFT
    if remote.author_name != WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME:
        return MvpDraftReasonCode.ARTICLE_AUTHOR_NAME_DRIFT
    if (
        profile is _ArticleDriftProfile.BASELINE
        and remote.modified != WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_MODIFIED
    ):
        return MvpDraftReasonCode.ARTICLE_BASELINE_MODIFIED_DRIFT

    expected_title = (
        operation.title
        if profile is _ArticleDriftProfile.DESIRED
        else WORDPRESSCOM_MVP_WAVE3_ARTICLE_BASELINE_TITLE
    )
    expected_content = (
        operation.content
        if profile is _ArticleDriftProfile.DESIRED
        else bundle.article_baseline_content
    )
    expected_safe_setting = profile is _ArticleDriftProfile.BASELINE
    if remote.title != expected_title:
        return MvpDraftReasonCode.ARTICLE_TITLE_DRIFT
    if normalize_wordpresscom_mvp_line_endings(remote.content) != expected_content:
        return MvpDraftReasonCode.ARTICLE_CONTENT_DRIFT
    if remote.slug != operation.slug:
        return MvpDraftReasonCode.ARTICLE_SLUG_DRIFT
    if remote.status != "draft":
        return MvpDraftReasonCode.ARTICLE_STATUS_DRIFT
    if remote.object_type != "post":
        return MvpDraftReasonCode.ARTICLE_TYPE_DRIFT
    if remote.comments_open is not expected_safe_setting:
        return MvpDraftReasonCode.ARTICLE_COMMENTS_OPEN_DRIFT
    if remote.pings_open is not expected_safe_setting:
        return MvpDraftReasonCode.ARTICLE_PINGS_OPEN_DRIFT
    if remote.likes_enabled is not expected_safe_setting:
        return MvpDraftReasonCode.ARTICLE_LIKES_ENABLED_DRIFT
    if remote.sharing_enabled is not expected_safe_setting:
        return MvpDraftReasonCode.ARTICLE_SHARING_ENABLED_DRIFT
    if remote.publicize_urls_empty is not True:
        return MvpDraftReasonCode.ARTICLE_PUBLICIZE_URLS_DRIFT
    return MvpDraftReasonCode.OBJECT_DRIFT


def _page_preview_drift_reason(
    remote: MvpRemoteObject, operation: MvpDraftOperation
) -> MvpDraftReasonCode:
    if remote.site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID:
        return MvpDraftReasonCode.PAGE_SITE_ID_DRIFT
    if remote.author_id != WORDPRESSCOM_MVP_WAVE3_AUTHOR_ID:
        return MvpDraftReasonCode.PAGE_AUTHOR_ID_DRIFT
    if remote.author_name != WORDPRESSCOM_MVP_WAVE3_AUTHOR_NAME:
        return MvpDraftReasonCode.PAGE_AUTHOR_NAME_DRIFT
    if remote.title != operation.title:
        return MvpDraftReasonCode.PAGE_TITLE_DRIFT
    if normalize_wordpresscom_mvp_line_endings(remote.content) != operation.content:
        return MvpDraftReasonCode.PAGE_CONTENT_DRIFT
    if remote.slug != operation.slug:
        return MvpDraftReasonCode.PAGE_SLUG_DRIFT
    if remote.status != "draft":
        return MvpDraftReasonCode.PAGE_STATUS_DRIFT
    if remote.object_type != "page":
        return MvpDraftReasonCode.PAGE_TYPE_DRIFT
    if remote.comments_open is not False:
        return MvpDraftReasonCode.PAGE_COMMENTS_OPEN_DRIFT
    if remote.pings_open is not False:
        return MvpDraftReasonCode.PAGE_PINGS_OPEN_DRIFT
    if remote.likes_enabled is not False:
        return MvpDraftReasonCode.PAGE_LIKES_ENABLED_DRIFT
    if remote.sharing_enabled is not False:
        return MvpDraftReasonCode.PAGE_SHARING_ENABLED_DRIFT
    if remote.publicize_urls_empty is not True:
        return MvpDraftReasonCode.PAGE_PUBLICIZE_URLS_DRIFT
    return MvpDraftReasonCode.OBJECT_DRIFT


def _preview_object_drift_reason(
    operation: object, remote: object, bundle: object
) -> MvpDraftReasonCode:
    """Return only a closed value-free preview reason, falling back generically."""

    if (
        not _preview_drift_inputs_are_valid(operation, remote, bundle)
        or type(operation) is not MvpDraftOperation
        or type(remote) is not MvpRemoteObject
        or type(bundle) is not MvpDraftContentBundle
    ):
        return MvpDraftReasonCode.OBJECT_DRIFT
    try:
        if operation.object_type == "post":
            if _article_is_desired(remote, operation) or _exact_common_outside_slots(
                remote, operation, bundle
            ):
                return MvpDraftReasonCode.OBJECT_DRIFT
            return _article_preview_drift_reason(remote, operation, bundle)
        if operation.object_type == "page":
            if remote.object_id != "" and _exact_common(remote, operation):
                return MvpDraftReasonCode.OBJECT_DRIFT
            return _page_preview_drift_reason(remote, operation)
    except Exception:
        return MvpDraftReasonCode.OBJECT_DRIFT
    return MvpDraftReasonCode.OBJECT_DRIFT


def _page_candidates(
    entries: tuple[MvpPageEntry, ...], slug: str
) -> tuple[MvpPageEntry, ...]:
    return tuple(entry for entry in entries if entry.slug == slug)


class WordPressComMvpDraftPreparationService:
    """Run fixed-order preparation with one durable POST budget per operation."""

    __slots__ = ("_bundle", "_journal", "_provider")

    def __init__(
        self,
        *,
        bundle: MvpDraftContentBundle,
        provider: WordPressComMvpFixedProviderPort,
        journal: WordPressComMvpDraftJournalPort,
    ) -> None:
        if (
            type(bundle) is not MvpDraftContentBundle
            or not isinstance(cast(object, provider), WordPressComMvpFixedProviderPort)
            or not isinstance(cast(object, journal), WordPressComMvpDraftJournalPort)
        ):
            _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        bundle.__post_init__()
        for operation in bundle.operations:
            operation.__post_init__()
        self._bundle = bundle
        self._provider = provider
        self._journal = journal

    def __repr__(self) -> str:
        return "WordPressComMvpDraftPreparationService(<redacted-wordpresscom-wave3>)"

    def _read(self, operation: MvpDraftOperation) -> MvpRemoteObject | None:
        if operation.object_type == "post":
            return self._read_article()
        scan = self._scan_pages()
        candidates = _page_candidates(scan.entries, operation.slug)
        if not candidates:
            return None
        if len(candidates) != 1:
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        return self._read_page(operation, candidates[0].object_id)

    def _read_article(self) -> MvpRemoteObject:
        try:
            return _validate_remote(self._provider.read_article())
        except WordPressComMvpDraftFailure as error:
            _raise_with_response_context(
                error, MvpDraftResponseContext.ARTICLE_FULL_GET
            )

    def _scan_pages(self) -> MvpPageScan:
        try:
            return _validate_scan(self._provider.scan_pages())
        except WordPressComMvpDraftFailure as error:
            _raise_with_response_context(error, MvpDraftResponseContext.PAGE_SCAN)

    def _read_page(
        self, operation: MvpDraftOperation, expected_object_id: str
    ) -> MvpRemoteObject:
        expected = normalize_wordpresscom_mvp_id(expected_object_id)
        try:
            remote = _validate_remote(self._provider.read_page(operation, expected))
        except WordPressComMvpDraftFailure as error:
            _raise_with_response_context(error, MvpDraftResponseContext.PAGE_FULL_GET)
        if remote.object_id != expected:
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        return remote

    def _is_mutation_exact(
        self, operation: MvpDraftOperation, remote: MvpRemoteObject | None
    ) -> bool:
        if remote is None:
            return False
        return (
            _article_is_desired(remote, operation)
            if operation.object_type == "post"
            else remote.object_id != "" and _exact_common(remote, operation)
        )

    def _is_preview_exact(
        self, operation: MvpDraftOperation, remote: MvpRemoteObject | None
    ) -> bool:
        if remote is None:
            return False
        return self._is_mutation_exact(operation, remote) or (
            operation.object_type == "post"
            and _exact_common_outside_slots(remote, operation, self._bundle)
        )

    def _reconcile(
        self,
        operation: MvpDraftOperation,
    ) -> bool:
        try:
            remote = self._read(operation)
        except BaseException:
            _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        if self._is_mutation_exact(operation, remote):
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.RECONCILED_COMMITTED,
                reason_code="EXACT_RECONCILIATION",
                object_id=remote.object_id if remote is not None else None,
            )
            return True
        _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)

    def _prepare_article(
        self,
        operation: MvpDraftOperation,
        history: tuple[MvpDraftJournalEntry, ...],
    ) -> None:
        if history:
            if history[-1].state in _EXACT_TERMINAL:
                remote = self._read_article()
                if not _article_is_desired(remote, operation):
                    _fail(WordPressComMvpDraftFailureCode.DRIFT)
                return
            if history[-1].state in {
                MvpDraftOperationState.INTENT,
                MvpDraftOperationState.MUTATION_AMBIGUOUS,
            }:
                self._reconcile(operation)
                return
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        first = self._read_article()
        if _article_is_desired(first, operation):
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REUSED_EXACT,
                reason_code="EXACT_DESIRED",
                object_id=first.object_id,
            )
            return
        if not _article_is_baseline(first, self._bundle):
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REFUSED_MISMATCH,
                reason_code="BASELINE_MISMATCH",
                object_id=None,
            )
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        self._journal.append(
            operation_id=operation.operation_id,
            operation_binding_sha256=operation.binding_sha256(),
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id=WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
        )
        second = self._read_article()
        if not _article_is_baseline(second, self._bundle):
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REFUSED_MISMATCH,
                reason_code="SECOND_BASELINE_MISMATCH",
                object_id=None,
            )
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        try:
            acknowledgement = _validate_acknowledgement(
                self._provider.update_article_once(operation)
            )
            if acknowledgement.object_id != WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID:
                _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
            readback = self._read_article()
            if not _article_is_desired(readback, operation):
                _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        except BaseException:
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.MUTATION_AMBIGUOUS,
                reason_code="READBACK_UNCERTAIN",
                object_id=WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
            )
            _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        self._journal.append(
            operation_id=operation.operation_id,
            operation_binding_sha256=operation.binding_sha256(),
            state=MvpDraftOperationState.COMMITTED,
            reason_code="EXACT_READBACK",
            object_id=WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
        )

    def _prepare_page(
        self,
        operation: MvpDraftOperation,
        history: tuple[MvpDraftJournalEntry, ...],
    ) -> None:
        if history:
            if history[-1].state in _EXACT_TERMINAL:
                remote = self._read(operation)
                if not self._is_mutation_exact(operation, remote):
                    _fail(WordPressComMvpDraftFailureCode.DRIFT)
                return
            if history[-1].state in {
                MvpDraftOperationState.INTENT,
                MvpDraftOperationState.MUTATION_AMBIGUOUS,
            }:
                self._reconcile(operation)
                return
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        first_scan = self._scan_pages()
        candidates = _page_candidates(first_scan.entries, operation.slug)
        if len(candidates) > 1:
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REFUSED_MISMATCH,
                reason_code="DUPLICATE_SLUG",
                object_id=None,
            )
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        if len(candidates) == 1:
            remote = self._read_page(operation, candidates[0].object_id)
            if not self._is_mutation_exact(operation, remote):
                self._journal.append(
                    operation_id=operation.operation_id,
                    operation_binding_sha256=operation.binding_sha256(),
                    state=MvpDraftOperationState.REFUSED_MISMATCH,
                    reason_code="EXISTING_PAGE_MISMATCH",
                    object_id=None,
                )
                _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REUSED_EXACT,
                reason_code="EXACT_DESIRED",
                object_id=remote.object_id,
            )
            return
        self._journal.append(
            operation_id=operation.operation_id,
            operation_binding_sha256=operation.binding_sha256(),
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id=None,
        )
        second_scan = self._scan_pages()
        if _page_candidates(second_scan.entries, operation.slug):
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.REFUSED_MISMATCH,
                reason_code="SECOND_SCAN_COLLISION",
                object_id=None,
            )
            _fail(WordPressComMvpDraftFailureCode.REFUSED_MISMATCH)
        try:
            acknowledgement = _validate_acknowledgement(
                self._provider.create_page_once(operation)
            )
            readback = self._read_page(operation, acknowledgement.object_id)
            if not self._is_mutation_exact(operation, readback):
                _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        except BaseException:
            self._journal.append(
                operation_id=operation.operation_id,
                operation_binding_sha256=operation.binding_sha256(),
                state=MvpDraftOperationState.MUTATION_AMBIGUOUS,
                reason_code="READBACK_UNCERTAIN",
                object_id=None,
            )
            _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        self._journal.append(
            operation_id=operation.operation_id,
            operation_binding_sha256=operation.binding_sha256(),
            state=MvpDraftOperationState.COMMITTED,
            reason_code="EXACT_READBACK",
            object_id=readback.object_id,
        )

    def prepare(self) -> MvpDraftPreview:
        """Execute under one lock; only a newly appended INTENT may lead to POST."""

        with self._journal.locked():
            for operation in self._bundle.operations:
                entries = self._journal.entries()
                history = _history(entries, operation)
                if operation.object_type == "post":
                    self._prepare_article(operation, history)
                else:
                    self._prepare_page(operation, history)
        return self._preview(
            detailed_response_reasons=False,
            detailed_object_drift_reasons=False,
        )

    def preview(self) -> MvpDraftPreview:
        """Perform only bounded reads and inspect the journal without writing it."""

        return self._preview(
            detailed_response_reasons=True,
            detailed_object_drift_reasons=True,
        )

    def _preview(
        self,
        *,
        detailed_response_reasons: bool,
        detailed_object_drift_reasons: bool,
    ) -> MvpDraftPreview:
        if (
            type(detailed_response_reasons) is not bool
            or type(detailed_object_drift_reasons) is not bool
        ):
            _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)

        entries = self._journal.inspect()
        results: list[MvpDraftOperationPreview] = []
        article_remote: MvpRemoteObject | None = None
        for operation in self._bundle.operations:
            history = _history(entries, operation)
            try:
                remote = self._read(operation)
                if operation.object_type == "post":
                    article_remote = remote
                exact = self._is_preview_exact(operation, remote)
                if history and history[-1].state in {
                    MvpDraftOperationState.INTENT,
                    MvpDraftOperationState.MUTATION_AMBIGUOUS,
                }:
                    observation = MvpDraftObservation.AMBIGUOUS
                    reason = MvpDraftReasonCode.JOURNAL_AMBIGUOUS
                elif (
                    history
                    and history[-1].state is MvpDraftOperationState.REFUSED_MISMATCH
                ):
                    observation = MvpDraftObservation.REFUSED
                    reason = MvpDraftReasonCode.JOURNAL_REFUSED
                elif exact:
                    observation = MvpDraftObservation.EXACT
                    reason = (
                        MvpDraftReasonCode.EXACT_PLACEHOLDERS
                        if operation.object_type == "post"
                        and remote is not None
                        and normalize_wordpresscom_mvp_line_endings(remote.content)
                        == operation.content
                        else MvpDraftReasonCode.EXACT_AFFILIATE_SLOTS
                        if operation.object_type == "post"
                        else MvpDraftReasonCode.EXACT_DESIRED
                    )
                elif remote is None:
                    observation = MvpDraftObservation.MISSING
                    reason = MvpDraftReasonCode.OBJECT_MISSING
                else:
                    observation = MvpDraftObservation.DRIFT
                    reason = (
                        _preview_object_drift_reason(operation, remote, self._bundle)
                        if detailed_object_drift_reasons
                        else MvpDraftReasonCode.OBJECT_DRIFT
                    )
            except WordPressComMvpDraftFailure as error:
                observation = (
                    MvpDraftObservation.REFUSED
                    if error.code is WordPressComMvpDraftFailureCode.REFUSED_MISMATCH
                    else MvpDraftObservation.DRIFT
                )
                reason = (
                    MvpDraftReasonCode.OBJECT_DUPLICATE
                    if observation is MvpDraftObservation.REFUSED
                    else _preview_response_reason(operation, error)
                    if detailed_response_reasons
                    else MvpDraftReasonCode.RESPONSE_INVALID
                )
            results.append(
                MvpDraftOperationPreview(operation.operation_id, observation, reason)
            )
        affiliate_state = MvpDraftAffiliateState.NOT_EVALUATED
        affiliate_count = 0
        if article_remote is not None and _article_non_content_exact(
            article_remote, self._bundle.operations[0]
        ):
            try:
                affiliate_state, affiliate_count = (
                    validate_wordpresscom_mvp_affiliate_content(
                        content=article_remote.content,
                        placeholder_content=self._bundle.operations[0].content,
                        product_names=self._bundle.affiliate_product_names,
                    )
                )
            except WordPressComMvpDraftFailure:
                affiliate_state = MvpDraftAffiliateState.SLOTS_INVALID
                affiliate_count = 0
                if results[0].observation is MvpDraftObservation.DRIFT:
                    results[0] = MvpDraftOperationPreview(
                        results[0].operation_id,
                        MvpDraftObservation.DRIFT,
                        MvpDraftReasonCode.AFFILIATE_INVALID,
                    )
        observations = {result.observation for result in results}
        if observations == {MvpDraftObservation.EXACT}:
            base_state = MvpDraftBaseState.PREPARED
        elif MvpDraftObservation.REFUSED in observations:
            base_state = MvpDraftBaseState.REFUSED
        elif MvpDraftObservation.AMBIGUOUS in observations:
            base_state = MvpDraftBaseState.AMBIGUOUS
        elif MvpDraftObservation.DRIFT in observations:
            base_state = MvpDraftBaseState.DRIFT
        else:
            base_state = MvpDraftBaseState.MISSING
        ready = (
            base_state is MvpDraftBaseState.PREPARED
            and affiliate_state is MvpDraftAffiliateState.SLOTS_VALIDATED
            and affiliate_count == 3
        )
        return MvpDraftPreview(
            operations=tuple(results),
            base_state=base_state,
            affiliate_state=affiliate_state,
            affiliate_slot_count=affiliate_count,
            manual_review_state=(
                MvpDraftManualReviewState.READY
                if ready
                else MvpDraftManualReviewState.NOT_READY
            ),
        )


__all__ = ["WordPressComMvpDraftPreparationService"]
