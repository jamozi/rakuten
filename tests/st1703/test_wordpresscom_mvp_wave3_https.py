"""Fixed transport and strict response tests for ST-1703 WordPress.com Wave 3."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qsl

import pytest

from raos.adapters.wordpresscom_mvp_draft_https import (
    OfficialWordPressComMvpDraftAdapter,
    decode_wordpresscom_mvp_acknowledgement,
    decode_wordpresscom_mvp_full_object,
    decode_wordpresscom_mvp_page_scan,
)
from raos.adapters.wordpresscom_review_draft_https import WordPressComBearerToken
from raos.application.editorial.wordpresscom_mvp_drafts import (
    build_bound_wordpresscom_mvp_content,
)
from raos.application.editorial.wordpresscom_review_draft import (
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftOperation,
    MvpDraftResponseStage,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH,
    WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH,
    WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
)
from raos.ports.wordpresscom_mvp_drafts import WordPressComMvpDraftsPort


ROOT = Path(__file__).resolve().parents[2]


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


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _full_object(**changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "ID": 7,
        "site_ID": "256699520",
        "author": {"ID": "283672805", "name": "暮らし選びノート編集部"},
        "modified": "2026-08-13T02:34:35+09:00",
        "title": "title",
        "content": "content",
        "URL": "https://kurashierabinote.wordpress.com/?p=7",
        "slug": "",
        "status": "draft",
        "type": "post",
        "discussion": {"comments_open": False, "pings_open": False},
        "likes_enabled": False,
        "sharing_enabled": False,
        "publicize_URLs": [],
    }
    value.update(changes)
    return value


class _TokenReader:
    def read(self, alias: str) -> WordPressComBearerToken:
        assert alias == "wordpresscom_oauth_access_token"
        return WordPressComBearerToken(b"x" * 16)


class _ForbiddenTokenReader:
    def read(self, alias: str) -> WordPressComBearerToken:
        del alias
        raise AssertionError("forged operation reached token access")


class _Response:
    def __init__(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str | None = "application/json; charset=utf-8",
    ) -> None:
        self.status = status
        self._body = body
        self._offset = 0
        self._content_type = content_type

    def getheader(self, name: str, default: str | None = None) -> str | None:
        return self._content_type if name == "Content-Type" else default

    def read(self, amount: int | None = None) -> bytes:
        effective = len(self._body) if amount is None else amount
        chunk = self._body[self._offset : self._offset + effective]
        self._offset += len(chunk)
        return chunk


class _NonBytesResponse(_Response):
    def read(self, amount: int | None = None) -> bytes:
        del amount
        return "provider-body"  # type: ignore[return-value]


class _Connection:
    def __init__(
        self, responses: list[_Response], calls: list[tuple[object, ...]]
    ) -> None:
        self._responses = responses
        self._calls = calls

    def connect(self) -> None:
        self._calls.append(("connect",))

    def set_read_timeout(self, seconds: int) -> None:
        self._calls.append(("timeout", seconds))

    def request(
        self, method: str, path: str, body: bytes, headers: dict[str, str]
    ) -> None:
        self._calls.append((method, path, body, tuple(headers)))

    def getresponse(self) -> _Response:
        return self._responses.pop(0)

    def close(self) -> None:
        self._calls.append(("close",))


class _Factory:
    def __init__(self, responses: list[_Response]) -> None:
        self.responses = responses
        self.calls: list[tuple[object, ...]] = []

    def open(self, **kwargs: object) -> _Connection:
        assert kwargs["host"] == "public-api.wordpress.com"
        assert kwargs["port"] == 443
        assert kwargs["connect_timeout_seconds"] == 5
        return _Connection(self.responses, self.calls)


def _operation(*, page: bool = False) -> MvpDraftOperation:
    return _bundle().operations[1 if page else 0]


@pytest.mark.parametrize("wire", [7, "7"])
def test_full_object_accepts_only_the_two_canonical_id_wire_forms(wire: object) -> None:
    value = decode_wordpresscom_mvp_full_object(_json(_full_object(ID=wire)))
    assert value.object_id == "7"
    assert str(value) == "<redacted-wordpresscom-wave3>"


@pytest.mark.parametrize("wire", [True, 7.0, "07", "+7", " 7", "7.0", "7e0"])
def test_full_object_rejects_noncanonical_ids(wire: object) -> None:
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(_json(_full_object(ID=wire)))


def test_duplicate_json_keys_and_unknown_top_level_fields_are_rejected() -> None:
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(b'{"ID":7,"ID":7}')
    value = _full_object(extra="forbidden")
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(_json(value))


@pytest.mark.parametrize(
    "body",
    [
        b"\xff{}",
        b"[]",
        b'{"ID":7,"author":{"ID":1,"ID":1}}',
        (b"[" * 65) + b"0" + (b"]" * 65),
        b"{" + (b" " * 1_000_000) + b"}",
    ],
)
def test_non_utf8_wrong_shape_duplicate_nested_depth_and_size_are_rejected(
    body: bytes,
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(body)


@pytest.mark.parametrize(
    "changes",
    [
        {"site_ID": "256699521"},
        {"author": {"ID": "283672805", "name": 1}},
        {"discussion": {"comments_open": 0, "pings_open": False}},
        {
            "discussion": {
                "comments_open": False,
                "pings_open": "false",
                "synthetic-extension": {"opaque-value": True},
            }
        },
        {"likes_enabled": 0},
        {"sharing_enabled": "false"},
        {"publicize_URLs": ["https://example.invalid"]},
    ],
)
def test_full_object_strict_identity_boolean_and_publicize_shapes(
    changes: dict[str, object],
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(_json(_full_object(**changes)))


@pytest.mark.parametrize(
    "url",
    [
        "http://kurashierabinote.wordpress.com/?p=7",
        "https://user@kurashierabinote.wordpress.com/?p=7",
        "https://kurashierabinote.wordpress.com:443/?p=7",
        "https://kurashierabinote.wordpress.com:444/?p=7",
        "https://kurashierabinote.wordpress.com/?p=7#fragment",
        "https://kurashierabinote.wordpress.com/\\evil",
        "https://kurashierabinote.wordpress.com/\ncontrol",
        "https://kurashierabinote.wordpress.com/%0a",
        "https://kurashierabinote.wordpress.com/%ZZ",
        "https://example.invalid/?p=7",
    ],
)
def test_full_object_url_rejects_wrong_origin_fragment_port_userinfo_and_controls(
    url: str,
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure):
        decode_wordpresscom_mvp_full_object(_json(_full_object(URL=url)))


def test_full_object_url_allows_target_origin_query_form() -> None:
    remote = decode_wordpresscom_mvp_full_object(
        _json(_full_object(URL="https://kurashierabinote.wordpress.com/?p=7"))
    )
    assert remote.object_id == "7"


def test_full_object_discussion_exact_two_key_set_remains_accepted() -> None:
    remote = decode_wordpresscom_mvp_full_object(
        _json(_full_object(discussion={"comments_open": False, "pings_open": False}))
    )
    assert remote.comments_open is False
    assert remote.pings_open is False


@pytest.mark.parametrize(
    "extension_value",
    [
        None,
        True,
        17,
        1.25,
        "opaque-value",
        {"nested": [None, False, 9, "opaque-value"]},
        [None, {"nested": True}, [1, 2, 3]],
    ],
)
def test_full_object_accepts_bounded_opaque_discussion_extensions_without_projection(
    extension_value: object,
) -> None:
    extension_name = "synthetic-opaque-extension"
    discussion = {
        "comments_open": False,
        extension_name: extension_value,
        "pings_open": False,
    }
    remote = decode_wordpresscom_mvp_full_object(
        _json(_full_object(discussion=discussion))
    )
    exact = decode_wordpresscom_mvp_full_object(_json(_full_object()))
    assert remote == exact
    assert remote.comments_open is False
    assert remote.pings_open is False
    assert not hasattr(remote, extension_name)
    rendered = f"{remote!s} {remote!r}"
    assert extension_name not in rendered
    assert "opaque-value" not in rendered


def test_full_object_ignores_extension_names_values_and_insertion_order() -> None:
    first = decode_wordpresscom_mvp_full_object(
        _json(
            _full_object(
                discussion={
                    "synthetic-before": {"opaque-value": [1, 2]},
                    "comments_open": False,
                    "pings_open": False,
                    "synthetic-after": None,
                }
            )
        )
    )
    second = decode_wordpresscom_mvp_full_object(
        _json(
            _full_object(
                discussion={
                    "pings_open": False,
                    "synthetic-renamed": [True, False],
                    "comments_open": False,
                }
            )
        )
    )
    exact = decode_wordpresscom_mvp_full_object(_json(_full_object()))
    assert first == second == exact


def test_opaque_discussion_extension_duplicate_key_is_rejected_globally() -> None:
    body = _json(_full_object())
    exact = b'"discussion":{"comments_open":false,"pings_open":false}'
    duplicate = (
        b'"discussion":{"comments_open":false,"pings_open":false,'
        b'"synthetic-duplicate":1,"synthetic-duplicate":2}'
    )
    assert exact in body
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_full_object(body.replace(exact, duplicate))
    assert failure.value.response_stage is MvpDraftResponseStage.BOUNDED_JSON


@pytest.mark.parametrize(
    "extension_fragment",
    [b'"\xff"', b"undefined"],
)
def test_opaque_discussion_extension_utf8_and_json_grammar_remain_globally_strict(
    extension_fragment: bytes,
) -> None:
    body = _json(_full_object())
    exact = b'"discussion":{"comments_open":false,"pings_open":false}'
    replacement = (
        b'"discussion":{"comments_open":false,"pings_open":false,'
        b'"synthetic-invalid":' + extension_fragment + b"}"
    )
    assert exact in body
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_full_object(body.replace(exact, replacement))
    assert failure.value.response_stage is MvpDraftResponseStage.BOUNDED_JSON


@pytest.mark.parametrize("extension_value", [float("nan"), float("inf")])
def test_opaque_discussion_extension_nonfinite_number_is_rejected_globally(
    extension_value: float,
) -> None:
    discussion = {
        "comments_open": False,
        "pings_open": False,
        "synthetic-nonfinite": extension_value,
    }
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_full_object(_json(_full_object(discussion=discussion)))
    assert failure.value.response_stage is MvpDraftResponseStage.BOUNDED_JSON


def test_opaque_discussion_extension_depth_and_nodes_remain_globally_bounded() -> None:
    deep: object = None
    for _ in range(64):
        deep = [deep]
    for extension in (deep, [None] * 100_000):
        discussion = {
            "comments_open": False,
            "pings_open": False,
            "synthetic-bounded": extension,
        }
        with pytest.raises(WordPressComMvpDraftFailure) as failure:
            decode_wordpresscom_mvp_full_object(
                _json(_full_object(discussion=discussion))
            )
        assert failure.value.response_stage is MvpDraftResponseStage.BOUNDED_JSON


def test_opaque_discussion_extension_response_size_remains_globally_bounded() -> None:
    discussion = {
        "comments_open": False,
        "pings_open": False,
        "synthetic-oversized": "x" * 1_000_000,
    }
    body = _json(_full_object(discussion=discussion))
    assert len(body) > 1_000_000
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_full_object(body)
    assert failure.value.response_stage is MvpDraftResponseStage.BOUNDED_JSON


@pytest.mark.parametrize(
    ("body", "expected_stage"),
    [
        (b"\xff{}", MvpDraftResponseStage.BOUNDED_JSON),
        (_json(_full_object(extra="forbidden")), MvpDraftResponseStage.TOP_LEVEL_KEYS),
        (_json(_full_object(site_ID="256699521")), MvpDraftResponseStage.SITE_ID),
        (_json(_full_object(author=[])), MvpDraftResponseStage.AUTHOR_SHAPE),
        (
            _json(_full_object(author={"ID": "283672805"})),
            MvpDraftResponseStage.AUTHOR_SHAPE,
        ),
        (_json(_full_object(discussion=[])), MvpDraftResponseStage.DISCUSSION_TYPE),
        (
            _json(_full_object(discussion={"comments_open": False})),
            MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING,
        ),
        (
            _json(
                _full_object(
                    discussion={
                        "comments_open": False,
                        "provider-value": False,
                    }
                )
            ),
            MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING,
        ),
        (
            _json(_full_object(publicize_URLs=["provider-value"])),
            MvpDraftResponseStage.PUBLICIZE_URLS,
        ),
        (_json(_full_object(ID="07")), MvpDraftResponseStage.IDENTIFIER),
        (
            _json(
                _full_object(
                    author={"ID": "283672805", "name": "provider-value"},
                    likes_enabled=0,
                )
            ),
            MvpDraftResponseStage.SCALAR_FIELD_TYPE,
        ),
        (
            _json(_full_object(URL="https://example.invalid/provider-value")),
            MvpDraftResponseStage.URL,
        ),
        (_json(_full_object(modified="")), MvpDraftResponseStage.APPLICATION_INVARIANT),
    ],
)
def test_full_object_failure_stages_are_closed_and_keep_generic_failure_contract(
    body: bytes,
    expected_stage: MvpDraftResponseStage,
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_full_object(body)
    assert failure.value.code is WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
    assert failure.value.response_stage is expected_stage
    assert failure.value.response_context is None
    rendered = f"{failure.value!s} {failure.value!r}"
    assert "provider-value" not in rendered
    assert "example.invalid" not in rendered


@pytest.mark.parametrize(
    ("body", "expected_stage"),
    [
        (b"[]", MvpDraftResponseStage.TOP_LEVEL_KEYS),
        (
            _json({"found": 0, "meta": {}, "posts": [], "extra": 1}),
            MvpDraftResponseStage.TOP_LEVEL_KEYS,
        ),
        (
            _json({"found": "0", "meta": {}, "posts": []}),
            MvpDraftResponseStage.COLLECTION_SHAPE,
        ),
        (
            _json({"found": 1, "meta": {}, "posts": [[]]}),
            MvpDraftResponseStage.ENTRY_SHAPE,
        ),
        (
            _json(
                {
                    "found": 1,
                    "meta": {},
                    "posts": [
                        {
                            "ID": "11",
                            "site_ID": "256699521",
                            "type": "page",
                            "slug": "about",
                            "status": "draft",
                        }
                    ],
                }
            ),
            MvpDraftResponseStage.SITE_ID,
        ),
        (
            _json(
                {
                    "found": 1,
                    "meta": {},
                    "posts": [
                        {
                            "ID": "011",
                            "site_ID": "256699520",
                            "type": "page",
                            "slug": "about",
                            "status": "draft",
                        }
                    ],
                }
            ),
            MvpDraftResponseStage.IDENTIFIER,
        ),
        (
            _json(
                {
                    "found": 1,
                    "meta": {},
                    "posts": [
                        {
                            "ID": "11",
                            "site_ID": "256699520",
                            "type": 1,
                            "slug": "about",
                            "status": "draft",
                        }
                    ],
                }
            ),
            MvpDraftResponseStage.SCALAR_FIELD_TYPE,
        ),
    ],
)
def test_page_scan_failure_stages_are_closed(
    body: bytes,
    expected_stage: MvpDraftResponseStage,
) -> None:
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_page_scan(body)
    assert failure.value.code is WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
    assert failure.value.response_stage is expected_stage


def test_collection_requires_canonical_found_and_complete_bounded_posts() -> None:
    body = _json(
        {
            "found": 1,
            "meta": {},
            "posts": [
                {
                    "ID": "11",
                    "site_ID": 256699520,
                    "type": "page",
                    "slug": "about",
                    "status": "draft",
                }
            ],
        }
    )
    assert decode_wordpresscom_mvp_page_scan(body).entries[0].object_id == "11"
    for found in ("1", 0, 101):
        malformed = json.loads(body)
        malformed["found"] = found
        with pytest.raises(WordPressComMvpDraftFailure):
            decode_wordpresscom_mvp_page_scan(_json(malformed))


def test_fixed_get_routes_are_exact_and_argument_free() -> None:
    responses = [
        _Response(_json(_full_object())),
        _Response(_json({"found": 0, "meta": {}, "posts": []})),
    ]
    factory = _Factory(responses)
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    adapter.read_article()
    adapter.scan_pages()
    network = [call for call in factory.calls if call[0] in {"GET", "POST"}]
    assert [(call[0], call[1], call[2]) for call in network] == [
        ("GET", WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH, b""),
        ("GET", WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH, b""),
    ]


def test_raw_https_adapter_is_not_the_inward_prepare_port() -> None:
    factory = _Factory([])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    assert not isinstance(adapter, WordPressComMvpDraftsPort)
    assert not hasattr(adapter, "prepare")
    assert not hasattr(adapter, "preview")
    assert not hasattr(adapter, "publish")
    assert factory.calls == []


@pytest.mark.parametrize("page", [False, True])
def test_forged_operation_is_rejected_before_token_or_connection(page: bool) -> None:
    operation = _operation(page=page)
    object.__setattr__(operation, "title", "forged")
    factory = _Factory([])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_ForbiddenTokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        (
            adapter.create_page_once(operation)
            if page
            else adapter.update_article_once(operation)
        )
    assert failure.value.code.value == "MVP_DRAFT_CONTENT_INVALID"
    assert factory.calls == []


def test_article_form_order_and_members_are_exact() -> None:
    factory = _Factory([_Response(_json({"ID": 7, "site_ID": "256699520"}))])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    operation = _operation()
    adapter.update_article_once(operation)
    call = next(call for call in factory.calls if call[0] == "POST")
    assert call[1] == WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH
    assert parse_qsl(call[2].decode("ascii"), keep_blank_values=True) == [
        ("title", operation.title),
        ("content", operation.content),
        ("status", "draft"),
        ("publicize", "false"),
        ("discussion[comments_open]", "false"),
        ("discussion[pings_open]", "false"),
        ("likes_enabled", "false"),
        ("sharing_enabled", "false"),
    ]


def test_page_form_order_and_members_are_exact() -> None:
    factory = _Factory([_Response(_json({"ID": "11", "site_ID": 256699520}))])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    operation = _operation(page=True)
    assert adapter.create_page_once(operation).object_id == "11"
    call = next(call for call in factory.calls if call[0] == "POST")
    assert call[1] == WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH
    assert parse_qsl(call[2].decode("ascii"), keep_blank_values=True) == [
        ("type", "page"),
        ("slug", operation.slug),
        ("title", operation.title),
        ("content", operation.content),
        ("author", "283672805"),
        ("status", "draft"),
        ("publicize", "false"),
        ("discussion[comments_open]", "false"),
        ("discussion[pings_open]", "false"),
        ("likes_enabled", "false"),
        ("sharing_enabled", "false"),
    ]


def test_post_response_is_only_acknowledgement_not_commitment() -> None:
    acknowledgement = decode_wordpresscom_mvp_acknowledgement(
        _json({"ID": "11", "site_ID": "256699520"})
    )
    assert acknowledgement.object_id == "11"
    assert not hasattr(acknowledgement, "committed")
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        decode_wordpresscom_mvp_acknowledgement(
            _json({"ID": "11", "site_ID": "256699520", "status": "draft"})
        )
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"


def test_post_failure_after_request_is_ambiguous_and_never_retried() -> None:
    factory = _Factory([_Response(b"{}", status=302)])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        adapter.update_article_once(_operation())
    assert failure.value.code.value == "MVP_DRAFT_MUTATION_AMBIGUOUS"
    assert len([call for call in factory.calls if call[0] == "POST"]) == 1


def test_get_redirect_is_rejected_without_retry() -> None:
    factory = _Factory([_Response(b"{}", status=302)])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        adapter.read_article()
    assert failure.value.code.value == "MVP_DRAFT_REMOTE_RESPONSE_INVALID"
    assert failure.value.response_stage is MvpDraftResponseStage.STATUS
    assert len([call for call in factory.calls if call[0] == "GET"]) == 1


@pytest.mark.parametrize(
    ("response", "expected_stage"),
    [
        (
            _Response(_json(_full_object()), content_type="text/html"),
            MvpDraftResponseStage.CONTENT_TYPE,
        ),
        (_NonBytesResponse(b"provider-body"), MvpDraftResponseStage.TRANSPORT),
        (_Response(b"x" * 1_000_001), MvpDraftResponseStage.BOUNDED_JSON),
    ],
)
def test_get_transport_and_content_type_stages_remain_generic_failures(
    response: _Response,
    expected_stage: MvpDraftResponseStage,
) -> None:
    factory = _Factory([response])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        adapter.read_article()
    assert failure.value.code is WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID
    assert failure.value.response_stage is expected_stage
    assert "provider-body" not in str(failure.value)
    assert "provider-body" not in repr(failure.value)
    assert len([call for call in factory.calls if call[0] == "GET"]) == 1


@pytest.mark.parametrize("name", ["SSL_CERT_FILE", "SSLKEYLOGFILE"])
def test_inherited_tls_override_refuses_before_token_or_connection(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(name, "/untrusted")
    factory = _Factory([])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_ForbiddenTokenReader(), connection_factory=factory
    )
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        adapter.read_article()
    assert failure.value.code.value == "MVP_DRAFT_HTTPS_SETUP_INVALID"
    assert factory.calls == []


def test_proxy_environment_is_never_used_by_direct_fixed_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.invalid:444")
    factory = _Factory([_Response(_json(_full_object()))])
    adapter = OfficialWordPressComMvpDraftAdapter(
        token_reader=_TokenReader(), connection_factory=factory
    )
    assert adapter.read_article().object_id == "7"
    assert next(call for call in factory.calls if call[0] == "GET")[1] == (
        WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH
    )
