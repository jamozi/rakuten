"""Pure create-only WordPress REST values for the self-hosted draft path."""

from __future__ import annotations

import json
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
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    fail_self_hosted_wordpress,
)


_CREATE_PATH = "/wp-json/wp/v2/posts"
_CREATE_ROUTE = "/wp/v2/posts"


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


__all__ = ["SelfHostedWordPressRestRequestBuilder"]
