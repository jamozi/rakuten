"""Fixed WordPress.com REST v1.1 transport for the approved ST-1703 Wave 3."""

from __future__ import annotations

import json
import math
import re
import ssl
from typing import Any, NoReturn, cast, final
from urllib.parse import quote_plus, urlencode, urlsplit

from raos.adapters.wordpresscom_review_draft_https import (
    SystemWordPressComHttpsConnectionFactory,
    WORDPRESSCOM_ACCESS_TOKEN_ALIAS,
    WordPressComAccessTokenReader,
    WordPressComBearerToken,
    WordPressComHttpsConnection,
    WordPressComHttpsConnectionFactory,
    WordPressComHttpsResponse,
    require_clean_wordpresscom_tls_environment,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftOperation,
    MvpDraftResponseStage,
    MvpMutationAcknowledgement,
    MvpPageEntry,
    MvpPageScan,
    MvpRemoteObject,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID,
    WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH,
    WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER,
    WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH,
    WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH,
    WORDPRESSCOM_MVP_WAVE3_SITE_ID,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
    normalize_wordpresscom_mvp_id,
)


_HOST = "public-api.wordpress.com"
_TARGET_HOST = "kurashierabinote.wordpress.com"
_PORT = 443
_CONNECT_TIMEOUT_SECONDS = 5
_READ_TIMEOUT_SECONDS = 20
_MAX_RESPONSE_BYTES = 1_000_000
_MAX_REQUEST_BYTES = 1_100_000
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_CONTENT_TYPE = re.compile(
    r"application/json(?:[ \t]*;[ \t]*charset=(?:utf-8|UTF-8))?\Z", re.ASCII
)
_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_PERCENT_ESCAPE = re.compile(r"%([0-9A-Fa-f]{2})", re.ASCII)
_FULL_OBJECT_KEYS = {
    "ID",
    "site_ID",
    "author",
    "modified",
    "title",
    "content",
    "URL",
    "slug",
    "status",
    "type",
    "discussion",
    "likes_enabled",
    "sharing_enabled",
    "publicize_URLs",
}


def _fail(code: WordPressComMvpDraftFailureCode) -> NoReturn:
    fail_wordpresscom_mvp_draft(code)


def _response_fail(stage: MvpDraftResponseStage) -> NoReturn:
    fail_wordpresscom_mvp_draft(
        WordPressComMvpDraftFailureCode.REMOTE_RESPONSE_INVALID,
        response_stage=stage,
    )


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    del value
    _response_fail(MvpDraftResponseStage.BOUNDED_JSON)


def _validate_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
            continue
        _response_fail(MvpDraftResponseStage.BOUNDED_JSON)


def _decode_json(body: bytes) -> object:
    if type(body) is not bytes or not 2 <= len(body) <= _MAX_RESPONSE_BYTES:
        _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
    try:
        value = json.loads(
            body.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeError, ValueError, RecursionError:
        _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
    _validate_tree(value)
    return value


def _read_bounded(response: WordPressComHttpsResponse) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(65_536, _MAX_RESPONSE_BYTES + 1 - total))
        if type(chunk) is not bytes:
            _response_fail(MvpDraftResponseStage.TRANSPORT)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            _response_fail(MvpDraftResponseStage.BOUNDED_JSON)
        chunks.append(chunk)
    return b"".join(chunks)


def _target_url(value: object) -> str:
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


def _exact_bool(mapping: dict[str, object], key: str) -> bool:
    value = mapping.get(key)
    if type(value) is not bool:
        _response_fail(MvpDraftResponseStage.SCALAR_FIELD_TYPE)
    return value


def _exact_string(mapping: dict[str, object], key: str) -> str:
    value = mapping.get(key)
    if type(value) is not str:
        _response_fail(MvpDraftResponseStage.SCALAR_FIELD_TYPE)
    return value


def _normalized_response_id(value: object, stage: MvpDraftResponseStage) -> str:
    try:
        return normalize_wordpresscom_mvp_id(value)
    except WordPressComMvpDraftFailure:
        _response_fail(stage)


def decode_wordpresscom_mvp_full_object(body: bytes) -> MvpRemoteObject:
    """Strictly decode one edit-context object without retaining provider bytes."""

    value = _decode_json(body)
    if type(value) is not dict:
        _response_fail(MvpDraftResponseStage.TOP_LEVEL_KEYS)
    mapping = cast(dict[str, object], value)
    if set(mapping) != _FULL_OBJECT_KEYS:
        _response_fail(MvpDraftResponseStage.TOP_LEVEL_KEYS)
    site_id = _normalized_response_id(mapping["site_ID"], MvpDraftResponseStage.SITE_ID)
    if site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID:
        _response_fail(MvpDraftResponseStage.SITE_ID)
    author_value = mapping["author"]
    discussion_value = mapping["discussion"]
    if type(author_value) is not dict:
        _response_fail(MvpDraftResponseStage.AUTHOR_SHAPE)
    author = cast(dict[str, object], author_value)
    if not {"ID", "name"}.issubset(author):
        _response_fail(MvpDraftResponseStage.AUTHOR_SHAPE)
    if type(discussion_value) is not dict:
        _response_fail(MvpDraftResponseStage.DISCUSSION_TYPE)
    discussion = cast(dict[str, object], discussion_value)
    if "comments_open" not in discussion or "pings_open" not in discussion:
        _response_fail(MvpDraftResponseStage.DISCUSSION_REQUIRED_KEYS_MISSING)
    publicize_urls = mapping["publicize_URLs"]
    if type(publicize_urls) is not list or publicize_urls != []:
        _response_fail(MvpDraftResponseStage.PUBLICIZE_URLS)
    object_id = _normalized_response_id(mapping["ID"], MvpDraftResponseStage.IDENTIFIER)
    author_id = _normalized_response_id(author["ID"], MvpDraftResponseStage.IDENTIFIER)
    try:
        return MvpRemoteObject(
            object_id=object_id,
            site_id=site_id,
            author_id=author_id,
            author_name=_exact_string(author, "name"),
            modified=_exact_string(mapping, "modified"),
            title=_exact_string(mapping, "title"),
            content=_exact_string(mapping, "content"),
            url=_target_url(mapping["URL"]),
            slug=_exact_string(mapping, "slug"),
            status=_exact_string(mapping, "status"),
            object_type=_exact_string(mapping, "type"),
            comments_open=_exact_bool(discussion, "comments_open"),
            pings_open=_exact_bool(discussion, "pings_open"),
            likes_enabled=_exact_bool(mapping, "likes_enabled"),
            sharing_enabled=_exact_bool(mapping, "sharing_enabled"),
            publicize_urls_empty=True,
        )
    except WordPressComMvpDraftFailure as error:
        if type(error.response_stage) is MvpDraftResponseStage:
            raise error
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)


def decode_wordpresscom_mvp_page_scan(body: bytes) -> MvpPageScan:
    """Decode the one bounded collection shape used for slug uniqueness."""

    value = _decode_json(body)
    if type(value) is not dict:
        _response_fail(MvpDraftResponseStage.TOP_LEVEL_KEYS)
    mapping = cast(dict[str, object], value)
    if set(mapping) != {"found", "meta", "posts"}:
        _response_fail(MvpDraftResponseStage.TOP_LEVEL_KEYS)
    found = mapping["found"]
    posts = mapping["posts"]
    if (
        type(found) is not int
        or not 0 <= found <= 100
        or type(mapping["meta"]) is not dict
        or type(posts) is not list
        or len(posts) != found
    ):
        _response_fail(MvpDraftResponseStage.COLLECTION_SHAPE)
    entries: list[MvpPageEntry] = []
    for value in cast(list[object], posts):
        if type(value) is not dict:
            _response_fail(MvpDraftResponseStage.ENTRY_SHAPE)
        post = cast(dict[str, object], value)
        if set(post) != {"ID", "site_ID", "type", "slug", "status"}:
            _response_fail(MvpDraftResponseStage.ENTRY_SHAPE)
        object_id = _normalized_response_id(
            post["ID"], MvpDraftResponseStage.IDENTIFIER
        )
        site_id = _normalized_response_id(
            post["site_ID"], MvpDraftResponseStage.SITE_ID
        )
        if site_id != WORDPRESSCOM_MVP_WAVE3_SITE_ID:
            _response_fail(MvpDraftResponseStage.SITE_ID)
        try:
            entries.append(
                MvpPageEntry(
                    object_id=object_id,
                    site_id=site_id,
                    object_type=_exact_string(post, "type"),
                    slug=_exact_string(post, "slug"),
                    status=_exact_string(post, "status"),
                )
            )
        except WordPressComMvpDraftFailure as error:
            if type(error.response_stage) is MvpDraftResponseStage:
                raise error
            _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)
    try:
        return MvpPageScan(tuple(entries))
    except WordPressComMvpDraftFailure:
        _response_fail(MvpDraftResponseStage.APPLICATION_INVARIANT)


def decode_wordpresscom_mvp_acknowledgement(body: bytes) -> MvpMutationAcknowledgement:
    value = _decode_json(body)
    if type(value) is not dict:
        _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
    mapping = cast(dict[str, object], value)
    if set(mapping) != {"ID", "site_ID"}:
        _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
    try:
        object_id = normalize_wordpresscom_mvp_id(mapping["ID"])
        site_id = normalize_wordpresscom_mvp_id(mapping["site_ID"])
    except WordPressComMvpDraftFailure:
        _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
    return MvpMutationAcknowledgement(object_id=object_id, site_id=site_id)


def _article_body(operation: MvpDraftOperation) -> bytes:
    operation.__post_init__()
    if (
        operation.operation_id != WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[0]
        or operation.object_id != WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID
        or operation.object_type != "post"
        or operation.slug != ""
    ):
        _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return _form_body(
        (
            ("title", operation.title),
            ("content", operation.content),
            ("status", "draft"),
            ("publicize", "false"),
            ("discussion[comments_open]", "false"),
            ("discussion[pings_open]", "false"),
            ("likes_enabled", "false"),
            ("sharing_enabled", "false"),
        )
    )


def _page_body(operation: MvpDraftOperation) -> bytes:
    operation.__post_init__()
    if (
        operation.operation_id not in WORDPRESSCOM_MVP_WAVE3_OPERATION_ORDER[1:]
        or operation.object_id is not None
        or operation.object_type != "page"
        or not operation.slug
    ):
        _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return _form_body(
        (
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
        )
    )


def _form_body(members: tuple[tuple[str, str], ...]) -> bytes:
    try:
        body = urlencode(
            members,
            doseq=False,
            safe="",
            encoding="utf-8",
            errors="strict",
            quote_via=quote_plus,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError:
        _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if not 2 <= len(body) <= _MAX_REQUEST_BYTES:
        _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return body


@final
class OfficialWordPressComMvpDraftAdapter:
    """Perform only the fixed GETs and one-attempt draft POSTs in Wave 3."""

    __slots__ = ("_connection_factory", "_token_reader")

    def __init__(
        self,
        *,
        token_reader: WordPressComAccessTokenReader,
        connection_factory: WordPressComHttpsConnectionFactory,
    ) -> None:
        if not isinstance(
            token_reader, WordPressComAccessTokenReader
        ) or not isinstance(connection_factory, WordPressComHttpsConnectionFactory):
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        self._token_reader = token_reader
        self._connection_factory = connection_factory

    def __repr__(self) -> str:
        return "OfficialWordPressComMvpDraftAdapter(<redacted-wordpresscom-wave3>)"

    def _request(self, *, method: str, path: str, body: bytes) -> bytes:
        if (
            method not in {"GET", "POST"}
            or type(path) is not str
            or type(body) is not bytes
        ):
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        try:
            require_clean_wordpresscom_tls_environment()
        except BaseException:
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        try:
            token = self._token_reader.read(WORDPRESSCOM_ACCESS_TOKEN_ALIAS)
        except BaseException:
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        if type(token) is not WordPressComBearerToken:
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        context = ssl.create_default_context()
        if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
            _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
        connection: WordPressComHttpsConnection | None = None
        request_attempted = False
        try:
            connection = self._connection_factory.open(
                host=_HOST,
                port=_PORT,
                connect_timeout_seconds=_CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
            if not isinstance(connection, WordPressComHttpsConnection):
                _fail(WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID)
            connection.connect()
            connection.set_read_timeout(_READ_TIMEOUT_SECONDS)
            headers = {
                "Accept": "application/json",
                "Authorization": token._authorization_header(),
            }
            if method == "POST":
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            request_attempted = True
            connection.request(method, path, body, headers)
            response = connection.getresponse()
            if not isinstance(response, WordPressComHttpsResponse):
                _response_fail(MvpDraftResponseStage.TRANSPORT)
            response_body = _read_bounded(response)
            content_type = response.getheader("Content-Type")
            if type(response.status) is not int or response.status != 200:
                _response_fail(MvpDraftResponseStage.STATUS)
            if (
                type(content_type) is not str
                or _CONTENT_TYPE.fullmatch(content_type) is None
            ):
                _response_fail(MvpDraftResponseStage.CONTENT_TYPE)
            return response_body
        except WordPressComMvpDraftFailure as error:
            if method == "POST" and request_attempted:
                _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
            raise error
        except BaseException:
            if method == "POST" and request_attempted:
                _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
            fail_wordpresscom_mvp_draft(
                WordPressComMvpDraftFailureCode.HTTPS_SETUP_INVALID,
                response_stage=MvpDraftResponseStage.TRANSPORT,
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass

    def read_article(self) -> MvpRemoteObject:
        return decode_wordpresscom_mvp_full_object(
            self._request(
                method="GET", path=WORDPRESSCOM_MVP_WAVE3_ARTICLE_GET_PATH, body=b""
            )
        )

    def scan_pages(self) -> MvpPageScan:
        return decode_wordpresscom_mvp_page_scan(
            self._request(
                method="GET", path=WORDPRESSCOM_MVP_WAVE3_PAGE_SCAN_PATH, body=b""
            )
        )

    def read_page(
        self, operation: MvpDraftOperation, object_id: str
    ) -> MvpRemoteObject:
        operation.__post_init__()
        if operation.object_type != "page":
            _fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        normalized = normalize_wordpresscom_mvp_id(object_id)
        path = (
            f"/rest/v1.1/sites/256699520/posts/{normalized}?context=edit&fields="
            "ID,site_ID,author,modified,title,content,URL,slug,status,type,discussion,"
            "likes_enabled,sharing_enabled,publicize_URLs"
        )
        return decode_wordpresscom_mvp_full_object(
            self._request(method="GET", path=path, body=b"")
        )

    def update_article_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement:
        acknowledgement = decode_wordpresscom_mvp_acknowledgement(
            self._request(
                method="POST",
                path=WORDPRESSCOM_MVP_WAVE3_ARTICLE_POST_PATH,
                body=_article_body(operation),
            )
        )
        if acknowledgement.object_id != WORDPRESSCOM_MVP_WAVE3_ARTICLE_ID:
            _fail(WordPressComMvpDraftFailureCode.MUTATION_AMBIGUOUS)
        return acknowledgement

    def create_page_once(
        self, operation: MvpDraftOperation
    ) -> MvpMutationAcknowledgement:
        return decode_wordpresscom_mvp_acknowledgement(
            self._request(
                method="POST",
                path=WORDPRESSCOM_MVP_WAVE3_PAGE_CREATE_PATH,
                body=_page_body(operation),
            )
        )


__all__ = [
    "OfficialWordPressComMvpDraftAdapter",
    "SystemWordPressComHttpsConnectionFactory",
    "decode_wordpresscom_mvp_acknowledgement",
    "decode_wordpresscom_mvp_full_object",
    "decode_wordpresscom_mvp_page_scan",
]
