"""Pure create-only WordPress REST values for the self-hosted draft path."""

from __future__ import annotations

import json
import hashlib
from typing import NoReturn, cast, final

from raos.adapters.wordpress_rest import (
    OfficialWordPressRestRequestBuilder,
    WordPressDraftResponseMetadata,
    WordPressRestRequest,
)
from raos.domain.editorial.market_learning_pilot import (
    MarketLearningPilotFailure,
    MarketLearningPilotFailureCode,
    fail_market_learning_pilot,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SELF_HOSTED_WORDPRESS_ORIGIN,
    SELF_HOSTED_WORDPRESS_STATUS,
    SelfHostedWordPressDraft,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    SelfHostedWordPressRecoveryObservation,
    SelfHostedWordPressRecoveryObservationDisposition,
    fail_self_hosted_wordpress,
)


_CREATE_PATH = "/wp-json/wp/v2/posts"
_CREATE_ROUTE = "/wp/v2/posts"
_RECOVERY_RELEVANT_STATUSES = "publish%2Cfuture%2Cdraft%2Cpending%2Cprivate%2Ctrash"
_RECOVERY_FIELDS = "id%2Ctype%2Cslug%2Cstatus%2Ctitle.raw%2Ccontent.raw"
_RECOVERY_MAX_RESULTS = 100


def _fail() -> NoReturn:
    fail_self_hosted_wordpress(SelfHostedWordPressFailureCode.REQUEST_INVALID)


def _response_fail() -> NoReturn:
    fail_market_learning_pilot(
        MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )


def _response_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            _response_fail()
        value[key] = item
    return value


def _reject_response_constant(value: str) -> NoReturn:
    del value
    _response_fail()


def _recovery_fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


def _recovery_pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        value[key] = item
    return value


def _reject_recovery_constant(value: str) -> NoReturn:
    del value
    _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)


@final
class SelfHostedWordPressRestRequestBuilder:
    """Adapt self-hosted create values to the existing pure REST validator."""

    __slots__ = ("_validator",)

    def __init__(self) -> None:
        self._validator = OfficialWordPressRestRequestBuilder(
            origin=SELF_HOSTED_WORDPRESS_ORIGIN
        )

    def build_create(
        self,
        *,
        candidate: SelfHostedWordPressDraft,
        credential_secret_alias: str,
    ) -> WordPressRestRequest:
        if (
            type(candidate) is not SelfHostedWordPressDraft
            or candidate.operation is not SelfHostedWordPressOperation.CREATE_DRAFT
        ):
            _fail()
        try:
            body_json = json.dumps(
                {
                    "content": candidate.content_html,
                    "slug": candidate.slug,
                    "status": SELF_HOSTED_WORDPRESS_STATUS,
                    "title": candidate.title,
                },
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            return WordPressRestRequest(
                method="POST",
                url=f"{SELF_HOSTED_WORDPRESS_ORIGIN}{_CREATE_PATH}",
                path=_CREATE_PATH,
                logical_route=_CREATE_ROUTE,
                headers=(("Content-Type", "application/json"),),
                body_json=body_json,
                credential_secret_alias=credential_secret_alias,
                idempotency_key=candidate.operation_sha256,
                expected_http_status=201,
                existing_draft_receipt=None,
            )
        except MarketLearningPilotFailure, TypeError, ValueError, UnicodeError:
            _fail()

    def validate_response(
        self,
        *,
        request: WordPressRestRequest,
        http_status: int,
        body: bytes,
    ) -> WordPressDraftResponseMetadata:
        metadata = self._validator.validate_response(
            request=request,
            http_status=http_status,
            body=body,
        )
        try:
            request_payload = json.loads(request.body_json)
            response_payload = json.loads(
                body.decode("utf-8", errors="strict"),
                object_pairs_hook=_response_pairs,
                parse_constant=_reject_response_constant,
            )
        except UnicodeError, ValueError, TypeError, RecursionError:
            _response_fail()
        if (
            type(request_payload) is not dict
            or type(response_payload) is not dict
            or frozenset(cast(dict[str, object], request_payload))
            != frozenset({"content", "slug", "status", "title"})
            or cast(dict[str, object], response_payload).get("slug")
            != cast(dict[str, object], request_payload).get("slug")
        ):
            _response_fail()
        return metadata


@final
class SelfHostedWordPressRecoveryRequestBuilder:
    """Build and validate the single exact read-before-recovery collection."""

    __slots__ = ()

    def build_path(self, candidate: SelfHostedWordPressDraft) -> str:
        if (
            type(candidate) is not SelfHostedWordPressDraft
            or candidate.operation is not SelfHostedWordPressOperation.CREATE_DRAFT
        ):
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE)
        return (
            f"{_CREATE_PATH}?context=edit&slug={candidate.slug}"
            f"&status={_RECOVERY_RELEVANT_STATUSES}"
            f"&_fields={_RECOVERY_FIELDS}&per_page={_RECOVERY_MAX_RESULTS}"
        )

    def validate_response(
        self,
        *,
        candidate: SelfHostedWordPressDraft,
        path: str,
        body: bytes,
    ) -> SelfHostedWordPressRecoveryObservation:
        expected_path = self.build_path(candidate)
        if (
            type(path) is not str
            or path != expected_path
            or type(body) is not bytes
            or not 2 <= len(body) <= 4_000_000
        ):
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        try:
            parsed = json.loads(
                body.decode("utf-8", errors="strict"),
                object_pairs_hook=_recovery_pairs,
                parse_constant=_reject_recovery_constant,
            )
        except SelfHostedWordPressFailure:
            raise
        except UnicodeError, ValueError, TypeError, RecursionError:
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        if type(parsed) is not list:
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        results = cast(list[object], parsed)
        if len(results) > _RECOVERY_MAX_RESULTS:
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        response_sha256 = hashlib.sha256(body).hexdigest()
        query_sha256 = hashlib.sha256(expected_path.encode("ascii")).hexdigest()
        if not results:
            return SelfHostedWordPressRecoveryObservation(
                disposition=(
                    SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE
                ),
                draft_id=None,
                status=None,
                content_sha256=candidate.content_sha256,
                operation_sha256=candidate.operation_sha256,
                query_sha256=query_sha256,
                response_sha256=response_sha256,
            )
        if len(results) != 1 or type(results[0]) is not dict:
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH)
        result = cast(dict[str, object], results[0])
        if frozenset(result) != frozenset(
            {"content", "id", "slug", "status", "title", "type"}
        ):
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        title = result["title"]
        content = result["content"]
        if (
            type(title) is not dict
            or frozenset(cast(dict[str, object], title)) != frozenset({"raw"})
            or type(content) is not dict
            or frozenset(cast(dict[str, object], content)) != frozenset({"raw"})
        ):
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN)
        draft_id = result["id"]
        if (
            type(draft_id) is not int
            or not 1 <= draft_id <= (1 << 63) - 1
            or result["type"] != "post"
            or result["slug"] != candidate.slug
            or result["status"] != SELF_HOSTED_WORDPRESS_STATUS
            or cast(dict[str, object], title)["raw"] != candidate.title
            or cast(dict[str, object], content)["raw"] != candidate.content_html
        ):
            _recovery_fail(SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH)
        return SelfHostedWordPressRecoveryObservation(
            disposition=SelfHostedWordPressRecoveryObservationDisposition.EXACT_DRAFT,
            draft_id=draft_id,
            status=SELF_HOSTED_WORDPRESS_STATUS,
            content_sha256=candidate.content_sha256,
            operation_sha256=candidate.operation_sha256,
            query_sha256=query_sha256,
            response_sha256=response_sha256,
        )


__all__ = [
    "SelfHostedWordPressRecoveryRequestBuilder",
    "SelfHostedWordPressRestRequestBuilder",
]
