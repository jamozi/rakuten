"""Pure create-only WordPress REST values for the self-hosted draft path."""

from __future__ import annotations

import json
from typing import NoReturn, final

from raos.adapters.wordpress_rest import (
    OfficialWordPressRestRequestBuilder,
    WordPressDraftResponseMetadata,
    WordPressRestRequest,
)
from raos.domain.editorial.market_learning_pilot import MarketLearningPilotFailure
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
        return self._validator.validate_response(
            request=request,
            http_status=http_status,
            body=body,
        )


__all__ = ["SelfHostedWordPressRestRequestBuilder"]
