"""Pure official WordPress REST request and response boundary tests."""

from __future__ import annotations

import json

import pytest

from raos.adapters.wordpress_rest import (
    OfficialWordPressRestRequestBuilder,
    WordPressRestRequest,
)
from raos.domain.editorial.market_learning_pilot import (
    BoundWordPressDraft,
    DraftDisposition,
    DraftOperation,
    MarketLearningPilotFailure,
    MarketLearningPilotFailureCode,
    PilotEconomics,
    PilotExecutionStatus,
    WordPressDraftIntent,
    WordPressDraftReceipt,
)


ORIGIN = "https://wordpress.example.invalid"
SECRET_ALIAS = "wordpress_application_password"
_DIRECT_BODY = '{"content":"body","status":"draft","title":"title"}'


def _candidate(
    *,
    operation: DraftOperation = DraftOperation.CREATE_DRAFT,
    existing_draft_id: int | None = None,
) -> BoundWordPressDraft:
    return BoundWordPressDraft.bind(
        intent=WordPressDraftIntent(
            operation=operation,
            article_version_id="ARTICLE-VERSION-1703",
            title="Synthetic WordPress draft",
            content="<p>Structured RAOS content.</p>",
            existing_draft_id=existing_draft_id,
        ),
        pilot=PilotEconomics(),
        policy_local_result_digest="a" * 64,
        rakuten_request_fingerprint="b" * 64,
        rakuten_raw_response_sha256="c" * 64,
    )


def _recorded_create_receipt(*, draft_id: int = 1703) -> WordPressDraftReceipt:
    candidate = _candidate()
    return WordPressDraftReceipt(
        draft_id=draft_id,
        operation=DraftOperation.CREATE_DRAFT,
        disposition=DraftDisposition.CREATED,
        status="draft",
        content_binding_sha256=candidate.content_binding_sha256,
        operation_binding_sha256=candidate.operation_binding_sha256,
        logical_draft_sha256="d" * 64,
        network_status=PilotExecutionStatus.NOT_EXECUTED,
        publication_authorized=False,
        production_eligible=False,
    )


def _direct_create_request(**overrides: object) -> WordPressRestRequest:
    values: dict[str, object] = {
        "method": "POST",
        "url": f"{ORIGIN}/wp-json/wp/v2/posts",
        "path": "/wp-json/wp/v2/posts",
        "logical_route": "/wp/v2/posts",
        "headers": (("Content-Type", "application/json"),),
        "body_json": _DIRECT_BODY,
        "credential_secret_alias": SECRET_ALIAS,
        "idempotency_key": "a" * 64,
        "expected_http_status": 201,
        "existing_draft_receipt": None,
    }
    values.update(overrides)
    return WordPressRestRequest(**values)  # type: ignore[arg-type]


def test_builder_emits_only_exact_post_create_draft_request() -> None:
    request = OfficialWordPressRestRequestBuilder(origin=ORIGIN).build(
        candidate=_candidate(),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
        credential_secret_alias=SECRET_ALIAS,
    )

    assert request.method == "POST"
    assert request.path == "/wp-json/wp/v2/posts"
    assert request.logical_route == "/wp/v2/posts"
    assert request.headers == (("Content-Type", "application/json"),)
    assert request.expected_http_status == 201
    assert json.loads(request.body_json) == {
        "content": "<p>Structured RAOS content.</p>",
        "status": "draft",
        "title": "Synthetic WordPress draft",
    }
    assert request.credential_secret_alias == SECRET_ALIAS
    assert "Authorization" not in request.headers


def test_builder_emits_only_exact_post_update_draft_request() -> None:
    request = OfficialWordPressRestRequestBuilder(origin=ORIGIN).build(
        candidate=_candidate(
            operation=DraftOperation.UPDATE_DRAFT,
            existing_draft_id=1703,
        ),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts/1703",
        credential_secret_alias=SECRET_ALIAS,
        existing_draft_receipt=_recorded_create_receipt(),
    )

    assert request.method == "POST"
    assert request.path == "/wp-json/wp/v2/posts/1703"
    assert request.logical_route == "/wp/v2/posts/1703"
    assert request.expected_http_status == 200
    assert json.loads(request.body_json)["status"] == "draft"


def test_update_requires_an_existing_typed_draft_receipt() -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)
    candidate = _candidate(
        operation=DraftOperation.UPDATE_DRAFT,
        existing_draft_id=1703,
    )

    with pytest.raises(MarketLearningPilotFailure) as missing:
        builder.build(
            candidate=candidate,
            endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts/1703",
            credential_secret_alias=SECRET_ALIAS,
        )
    assert (
        missing.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )

    with pytest.raises(MarketLearningPilotFailure) as wrong_target:
        builder.build(
            candidate=candidate,
            endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts/1703",
            credential_secret_alias=SECRET_ALIAS,
            existing_draft_receipt=_recorded_create_receipt(draft_id=1704),
        )
    assert (
        wrong_target.value.code
        is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


def test_create_rejects_an_existing_receipt_to_keep_operations_disjoint() -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        OfficialWordPressRestRequestBuilder(origin=ORIGIN).build(
            candidate=_candidate(),
            endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
            credential_secret_alias=SECRET_ALIAS,
            existing_draft_receipt=_recorded_create_receipt(),
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


def test_response_validation_returns_only_sanitized_draft_metadata() -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)
    request = builder.build(
        candidate=_candidate(),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
        credential_secret_alias=SECRET_ALIAS,
    )

    metadata = builder.validate_response(
        request=request,
        http_status=201,
        body=b'{"id":1703,"status":"draft","title":{"rendered":"ignored"}}',
    )

    assert metadata.draft_id == 1703
    assert metadata.status == "draft"
    assert metadata.http_status == 201
    assert "rendered" not in repr(metadata)


@pytest.mark.parametrize(
    "origin",
    [
        "http://wordpress.example.invalid",
        "HTTPS://wordpress.example.invalid",
        "https://WORDPRESS.example.invalid",
        "https://wordpress..example.invalid",
        "https://-wordpress.example.invalid",
        "https://user@wordpress.example.invalid",
        "https://user:password@wordpress.example.invalid",
        "https://wordpress.example.invalid/",
        "https://wordpress.example.invalid/wp-json",
        "https://wordpress.example.invalid?x=1",
        "https://wordpress.example.invalid#fragment",
        "",
        " https://wordpress.example.invalid",
    ],
)
def test_builder_rejects_nonexact_https_origins(origin: str) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        OfficialWordPressRestRequestBuilder(origin=origin)

    assert failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID


@pytest.mark.parametrize(
    "endpoint_url",
    [
        "https://foreign.example.invalid/wp-json/wp/v2/posts",
        f"{ORIGIN}/wp/v2/posts",
        f"{ORIGIN}/wp-json/wp/v2/posts/",
        f"{ORIGIN}/wp-json/wp/v2/posts?context=edit",
        f"{ORIGIN}/wp-json/wp/v2/posts#fragment",
        f"{ORIGIN}/wp-json/wp/v2/pages",
        f"{ORIGIN}/wp-json/wp/v2/posts%2f1703",
    ],
)
def test_builder_rejects_foreign_or_nonexact_paths(endpoint_url: str) -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)

    with pytest.raises(MarketLearningPilotFailure):
        builder.build(
            candidate=_candidate(),
            endpoint_url=endpoint_url,
            credential_secret_alias=SECRET_ALIAS,
        )


@pytest.mark.parametrize(
    "secret_alias",
    [
        "",
        "WordpressSecret",
        "wordpress-secret",
        "secret" + "://wordpress/application-password",
        "user:application-password",
        " application_password",
        "a" * 65,
    ],
)
def test_builder_rejects_credential_values_and_invalid_aliases(
    secret_alias: str,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        OfficialWordPressRestRequestBuilder(origin=ORIGIN).build(
            candidate=_candidate(),
            endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
            credential_secret_alias=secret_alias,
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


@pytest.mark.parametrize(
    ("path", "expected_status"),
    [
        ("/wp-json/wp/v2/pages", 201),
        ("/wp-json/wp/v2/posts/0", 200),
        ("/wp-json/wp/v2/posts/01", 200),
        ("/wp-json/wp/v2/posts/-1", 200),
        ("/wp-json/wp/v2/posts/1703/delete", 200),
        ("/wp-json/wp/v2/posts", 200),
        ("/wp-json/wp/v2/posts/1703", 201),
    ],
)
def test_direct_request_constructor_rejects_nonexact_path_status_pairs(
    path: str,
    expected_status: int,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        WordPressRestRequest(
            method="POST",
            url=f"{ORIGIN}{path}",
            path=path,
            logical_route=(
                "/wp/v2/posts/1703"
                if path == "/wp-json/wp/v2/posts/1703"
                else "/wp/v2/posts"
            ),
            headers=(("Content-Type", "application/json"),),
            body_json='{"content":"body","status":"draft","title":"title"}',
            credential_secret_alias=SECRET_ALIAS,
            idempotency_key="a" * 64,
            expected_http_status=expected_status,
            existing_draft_receipt=(
                _recorded_create_receipt()
                if path == "/wp-json/wp/v2/posts/1703"
                else None
            ),
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


def test_direct_request_constructor_rejects_logical_route_transport_mismatch() -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        WordPressRestRequest(
            method="POST",
            url=f"{ORIGIN}/wp-json/wp/v2/posts",
            path="/wp-json/wp/v2/posts",
            logical_route="/wp/v2/pages",
            headers=(("Content-Type", "application/json"),),
            body_json='{"content":"body","status":"draft","title":"title"}',
            credential_secret_alias=SECRET_ALIAS,
            idempotency_key="a" * 64,
            expected_http_status=201,
            existing_draft_receipt=None,
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


@pytest.mark.parametrize(
    ("field_name", "unsafe_value", "expected_code"),
    [
        ("method", "DELETE", MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID),
        (
            "url",
            "http://wordpress.example.invalid/wp-json/wp/v2/posts",
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID,
        ),
        (
            "url",
            "https://user@wordpress.example.invalid/wp-json/wp/v2/posts",
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID,
        ),
        (
            "url",
            f"{ORIGIN}/wp-json/wp/v2/posts?context=edit",
            MarketLearningPilotFailureCode.WORDPRESS_ORIGIN_INVALID,
        ),
        (
            "url",
            f"{ORIGIN}/wp-json/wp/v2/pages",
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
        (
            "headers",
            (("Authorization", "credential-canary"),),
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
        (
            "headers",
            (("Content-Type", "application/json"), ("X-Extra", "value")),
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
        (
            "credential_secret_alias",
            "user:credential-canary",
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
        (
            "idempotency_key",
            "not-a-sha256",
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
        (
            "idempotency_key",
            None,
            MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID,
        ),
    ],
)
def test_direct_request_constructor_enforces_transport_and_secret_gates(
    field_name: str,
    unsafe_value: object,
    expected_code: MarketLearningPilotFailureCode,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        _direct_create_request(**{field_name: unsafe_value})

    assert failure.value.code is expected_code
    assert "credential-canary" not in str(failure.value)
    assert "credential-canary" not in repr(failure.value)


@pytest.mark.parametrize(
    "existing_receipt",
    [object(), "1703", 1703],
)
def test_direct_update_constructor_requires_an_exact_typed_receipt(
    existing_receipt: object,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        WordPressRestRequest(
            method="POST",
            url=f"{ORIGIN}/wp-json/wp/v2/posts/1703",
            path="/wp-json/wp/v2/posts/1703",
            logical_route="/wp/v2/posts/1703",
            headers=(("Content-Type", "application/json"),),
            body_json=_DIRECT_BODY,
            credential_secret_alias=SECRET_ALIAS,
            idempotency_key="a" * 64,
            expected_http_status=200,
            existing_draft_receipt=existing_receipt,  # type: ignore[arg-type]
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


@pytest.mark.parametrize("status", ["publish", "future", "private", "pending"])
def test_direct_request_constructor_rejects_every_nondraft_status(
    status: str,
) -> None:
    body = json.dumps(
        {"content": "body", "status": status, "title": "title"},
        sort_keys=True,
        separators=(",", ":"),
    )
    with pytest.raises(MarketLearningPilotFailure) as failure:
        WordPressRestRequest(
            method="POST",
            url=f"{ORIGIN}/wp-json/wp/v2/posts",
            path="/wp-json/wp/v2/posts",
            logical_route="/wp/v2/posts",
            headers=(("Content-Type", "application/json"),),
            body_json=body,
            credential_secret_alias=SECRET_ALIAS,
            idempotency_key="a" * 64,
            expected_http_status=201,
            existing_draft_receipt=None,
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


@pytest.mark.parametrize(
    "body_json",
    [
        '{"content":"body","status":"publish","status":"draft","title":"title"}',
        '{"content":"body","status":"draft","title":"title","x":NaN}',
        '{ "content":"body","status":"draft","title":"title" }',
        '{"content":"","status":"draft","title":"title"}',
        '{"content":"body","status":"draft","title":" title"}',
        '{"content":"\\ud800","status":"draft","title":"title"}',
    ],
)
def test_direct_request_constructor_rejects_noncanonical_or_unsafe_json(
    body_json: str,
) -> None:
    with pytest.raises(MarketLearningPilotFailure) as failure:
        WordPressRestRequest(
            method="POST",
            url=f"{ORIGIN}/wp-json/wp/v2/posts",
            path="/wp-json/wp/v2/posts",
            logical_route="/wp/v2/posts",
            headers=(("Content-Type", "application/json"),),
            body_json=body_json,
            credential_secret_alias=SECRET_ALIAS,
            idempotency_key="a" * 64,
            expected_http_status=201,
            existing_draft_receipt=None,
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_REQUEST_INVALID
    )


def test_response_validation_rejects_request_from_another_origin() -> None:
    foreign_origin = "https://other-wordpress.example.invalid"
    request = OfficialWordPressRestRequestBuilder(origin=foreign_origin).build(
        candidate=_candidate(),
        endpoint_url=f"{foreign_origin}/wp-json/wp/v2/posts",
        credential_secret_alias=SECRET_ALIAS,
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        OfficialWordPressRestRequestBuilder(origin=ORIGIN).validate_response(
            request=request,
            http_status=201,
            body=b'{"id":1703,"status":"draft"}',
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )


@pytest.mark.parametrize(
    ("http_status", "body"),
    [
        (200, b'{"id":1703,"status":"draft"}'),
        (201, b'{"id":1703,"status":"publish"}'),
        (201, b'{"id":true,"status":"draft"}'),
        (201, b'{"id":0,"status":"draft"}'),
        (201, b'{"id":1703,"id":1704,"status":"draft"}'),
        (201, b'{"id":1703,"status":"draft","x":NaN}'),
        (201, b'{"id":1703,"status":"draft","x":1e999}'),
        (201, b"[]"),
        (201, b"{}"),
        (201, b"\xff\xfe"),
        (201, b""),
    ],
)
def test_response_validation_fails_closed_on_malformed_or_unsafe_shapes(
    http_status: int,
    body: bytes,
) -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)
    request = builder.build(
        candidate=_candidate(),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
        credential_secret_alias=SECRET_ALIAS,
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        builder.validate_response(
            request=request,
            http_status=http_status,
            body=body,
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )


def test_response_validation_rejects_excessive_json_depth() -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)
    request = builder.build(
        candidate=_candidate(),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts",
        credential_secret_alias=SECRET_ALIAS,
    )
    body = (
        b'{"id":1703,"status":"draft","x":' + (b"[" * 65) + b"null" + (b"]" * 65) + b"}"
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        builder.validate_response(request=request, http_status=201, body=body)

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )


def test_update_response_must_match_the_exact_existing_draft_id() -> None:
    builder = OfficialWordPressRestRequestBuilder(origin=ORIGIN)
    request = builder.build(
        candidate=_candidate(
            operation=DraftOperation.UPDATE_DRAFT,
            existing_draft_id=1703,
        ),
        endpoint_url=f"{ORIGIN}/wp-json/wp/v2/posts/1703",
        credential_secret_alias=SECRET_ALIAS,
        existing_draft_receipt=_recorded_create_receipt(),
    )

    with pytest.raises(MarketLearningPilotFailure) as failure:
        builder.validate_response(
            request=request,
            http_status=200,
            body=b'{"id":1704,"status":"draft"}',
        )

    assert (
        failure.value.code is MarketLearningPilotFailureCode.WORDPRESS_RESPONSE_INVALID
    )
