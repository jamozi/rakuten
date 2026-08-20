"""Pure live-safe Item Search request-policy checks for ST-0502."""

from __future__ import annotations

import ast
from dataclasses import MISSING, fields, replace
import hashlib
from pathlib import Path
import pickle
from typing import Callable, cast

import pytest

from raos.domain.catalog.rakuten_item_search import RakutenItemSearchFailure
from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    LIVE_ITEM_SEARCH_ELEMENTS_V1,
    LiveItemSearchElementV1,
    LiveItemSearchSortV1,
    ProviderTextTrustV1,
    RakutenItemSearchLiveRequestV1,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE = (
    REPOSITORY_ROOT
    / "python/raos/domain/catalog/rakuten_item_search_live_request_v1.py"
)
EXPECTED_ELEMENTS = (
    "affiliateUrl",
    "availability",
    "catchcopy",
    "count",
    "first",
    "genreId",
    "hits",
    "itemCaption",
    "itemCode",
    "itemName",
    "itemPrice",
    "itemUrl",
    "last",
    "mediumImageUrls",
    "page",
    "pageCount",
    "postageFlag",
    "shopCode",
    "shopName",
    "smallImageUrls",
)
EXPECTED_CANONICAL_JSON = (
    b'{"api_version":"2026-07-01","appoint_delivery_date_only":false,'
    b'"attribute_flag":false,"availability":true,"elements":["affiliateUrl",'
    b'"availability","catchcopy","count","first","genreId","hits",'
    b'"itemCaption","itemCode","itemName","itemPrice","itemUrl","last",'
    b'"mediumImageUrls","page","pageCount","postageFlag","shopCode",'
    b'"shopName","smallImageUrls"],'
    b'"format_version":2,"genre_information_flag":false,"hits":1,'
    b'"keyword":"synthetic suitcase","or_flag":false,"page":1,'
    b'"postage_included_only":false,"sort":"standard"}'
)
EXPECTED_FINGERPRINT = (
    "651137dbec8681df712115ba10b5d18a5065937780f06b1fc5679085d154653e"
)
REJECTED_CANARY = "REJECTED_PROVIDER_TEXT_CANARY_ST0502"


def _request() -> RakutenItemSearchLiveRequestV1:
    return RakutenItemSearchLiveRequestV1(
        api_version="2026-07-01",
        format_version=2,
        keyword="synthetic suitcase",
        shop_code=None,
        item_code=None,
        genre_id=None,
        hits=1,
        page=1,
        sort=LiveItemSearchSortV1.STANDARD,
        elements=LIVE_ITEM_SEARCH_ELEMENTS_V1,
        min_price_jpy=None,
        max_price_jpy=None,
        or_flag=False,
        availability=True,
        postage_included_only=False,
        has_review_only=False,
        appoint_delivery_date_only=False,
        attribute_flag=False,
        genre_information_flag=False,
    )


def test_live_safe_request_has_exact_non_review_non_rate_vocabulary() -> None:
    request = _request()

    assert {sort.value for sort in LiveItemSearchSortV1} == {
        "standard",
        "+itemPrice",
        "-itemPrice",
        "+updateTimestamp",
        "-updateTimestamp",
    }
    assert tuple(element.value for element in LIVE_ITEM_SEARCH_ELEMENTS_V1) == (
        EXPECTED_ELEMENTS
    )
    assert LIVE_ITEM_SEARCH_ELEMENTS_V1 == tuple(sorted(LiveItemSearchElementV1))
    assert {element.value for element in LIVE_ITEM_SEARCH_ELEMENTS_V1}.isdisjoint(
        {"reviewAverage", "reviewCount", "affiliateRate"}
    )
    assert "affiliateUrl" in EXPECTED_ELEMENTS
    assert request.page == request.hits == 1
    assert request.retry_limit == request.pagination_followup_limit == 0
    assert request.provider_text_trust is ProviderTextTrustV1.UNTRUSTED_DATA
    assert request.provider_derived_recommendation_inputs == ()
    assert request.has_review_only is False
    assert "has_review_only" not in request.canonical_parameters


def test_live_safe_request_canonical_json_and_fingerprint_are_exact() -> None:
    request = _request()

    assert request.canonical_json == EXPECTED_CANONICAL_JSON
    assert request.fingerprint == EXPECTED_FINGERPRINT
    assert hashlib.sha256(request.canonical_json).hexdigest() == request.fingerprint
    assert request.canonical_json.decode("utf-8").encode("utf-8") == (
        request.canonical_json
    )
    assert b"reviewCount" not in request.canonical_json
    assert b"reviewAverage" not in request.canonical_json
    assert b"affiliateRate" not in request.canonical_json
    assert b"review" not in request.canonical_json.lower()


@pytest.mark.parametrize(
    ("keyword", "shop_code", "item_code", "genre_id"),
    (
        ("synthetic", None, None, None),
        (None, "synthetic-shop", None, None),
        (None, None, "synthetic-shop:item-1", None),
        (None, None, None, 0),
    ),
)
def test_each_installed_selector_remains_available_without_live_execution(
    keyword: str | None,
    shop_code: str | None,
    item_code: str | None,
    genre_id: int | None,
) -> None:
    request = replace(
        _request(),
        keyword=keyword,
        shop_code=shop_code,
        item_code=item_code,
        genre_id=genre_id,
    )

    assert request.canonical_json
    assert request.retry_limit == request.pagination_followup_limit == 0


@pytest.mark.parametrize(
    "keyword",
    (
        "ab",
        "鞄",
        "Ａ",
        "あい",
        "アイ",
        "ｱｲ",
        "★★",
        "a鞄",
        "鞄a",
        "aあ",
        "!鞄",
        "ab 鞄",
        "鞄 suitcase",
    ),
)
def test_keyword_accepts_only_documented_minimum_term_shapes(keyword: str) -> None:
    request = replace(_request(), keyword=keyword)

    assert request.canonical_parameters["keyword"] == keyword


@pytest.mark.parametrize(
    "keyword",
    (
        "a",
        "1",
        "あ",
        "ア",
        "ｱ",
        "★",
        "！",
        " ab",
        "ab ",
        "ab a",
        "a 鞄",
        "ab  鞄",
        "ab\t鞄",
        "ab\u3000鞄",
        "ab\u00a0鞄",
        "ab\u200b鞄",
        "a\u0301",
        "か\u3099",
        "★\ufe0f",
    ),
)
def test_keyword_rejects_short_or_non_ascii_space_delimited_terms(
    keyword: str,
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        replace(_request(), keyword=keyword)


def test_keyword_enforces_the_pre_encoding_utf8_byte_boundary() -> None:
    ascii_boundary = "a" * 128
    multibyte_boundary = "界" * 42 + "ab"

    assert len(ascii_boundary.encode("utf-8")) == 128
    assert len(multibyte_boundary.encode("utf-8")) == 128
    assert replace(_request(), keyword=ascii_boundary).keyword == ascii_boundary
    assert replace(_request(), keyword=multibyte_boundary).keyword == (
        multibyte_boundary
    )

    for keyword in ("a" * 129, "界" * 42 + "abc"):
        assert len(keyword.encode("utf-8")) == 129
        with pytest.raises(RakutenItemSearchFailure):
            replace(_request(), keyword=keyword)


def test_keyword_case_and_bytes_are_preserved_without_normalization() -> None:
    upper = replace(_request(), keyword="AB")
    lower = replace(_request(), keyword="ab")
    full_width = replace(_request(), keyword="Ａ")

    assert upper.canonical_parameters["keyword"] == "AB"
    assert lower.canonical_parameters["keyword"] == "ab"
    assert full_width.canonical_parameters["keyword"] == "Ａ"
    assert full_width.canonical_json != upper.canonical_json
    assert upper.canonical_json != lower.canonical_json
    assert upper.fingerprint != lower.fingerprint


def test_or_flag_is_available_only_for_multiple_valid_keyword_terms() -> None:
    and_request = replace(_request(), keyword="ab 鞄", or_flag=False)
    or_request = replace(_request(), keyword="ab 鞄", or_flag=True)

    assert and_request.canonical_parameters["or_flag"] is False
    assert or_request.canonical_parameters["or_flag"] is True
    assert and_request.canonical_json != or_request.canonical_json
    assert and_request.fingerprint != or_request.fingerprint

    for changes in (
        {"keyword": "ab", "or_flag": True},
        {"keyword": None, "shop_code": "synthetic-shop", "or_flag": True},
    ):
        with pytest.raises(RakutenItemSearchFailure):
            replace(_request(), **changes)


def test_attribute_output_requires_an_exact_nonzero_genre_selector() -> None:
    request = replace(
        _request(),
        keyword=None,
        genre_id=1,
        attribute_flag=True,
    )

    assert request.attribute_flag is True
    assert request.genre_id == 1


@pytest.mark.parametrize("hits", (1, 30))
@pytest.mark.parametrize("sort", tuple(LiveItemSearchSortV1))
def test_hits_boundaries_and_every_safe_sort_are_accepted(
    hits: int, sort: LiveItemSearchSortV1
) -> None:
    request = replace(_request(), hits=hits, sort=sort)

    assert request.hits == hits
    assert request.sort is sort


@pytest.mark.parametrize(
    "factory",
    (
        lambda: replace(_request(), hits=0),
        lambda: replace(_request(), hits=True),
        lambda: replace(_request(), hits=31),
        lambda: replace(_request(), page=True),
        lambda: replace(_request(), page=2),
        lambda: replace(_request(), api_version="2026-07-01 "),
        lambda: replace(_request(), format_version=True),
        lambda: replace(
            _request(),
            keyword=None,
            shop_code=None,
            item_code=None,
            genre_id=None,
        ),
        lambda: replace(_request(), keyword=" leading"),
        lambda: replace(_request(), item_code="missing-colon"),
        lambda: replace(_request(), genre_id=True),
        lambda: replace(_request(), min_price_jpy=0),
        lambda: replace(_request(), max_price_jpy=999_999_999),
        lambda: replace(_request(), min_price_jpy=100, max_price_jpy=99),
        lambda: replace(_request(), min_price_jpy=100, max_price_jpy=100),
        lambda: replace(_request(), availability=cast(bool, 1)),
        lambda: replace(_request(), has_review_only=cast(bool, 0)),
        lambda: replace(_request(), has_review_only=True),
        lambda: replace(_request(), attribute_flag=True),
        lambda: replace(_request(), keyword=None, genre_id=0, attribute_flag=True),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "+reviewCount")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "-reviewCount")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "+reviewAverage")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "-reviewAverage")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "+affiliateRate")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "-affiliateRate")),
        lambda: replace(_request(), sort=cast(LiveItemSearchSortV1, "Standard")),
        lambda: replace(
            _request(), elements=tuple(reversed(LIVE_ITEM_SEARCH_ELEMENTS_V1))
        ),
        lambda: replace(
            _request(),
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1 + (LIVE_ITEM_SEARCH_ELEMENTS_V1[-1],),
        ),
        lambda: replace(_request(), elements=LIVE_ITEM_SEARCH_ELEMENTS_V1[:-1]),
        lambda: replace(
            _request(),
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1
            + (cast(LiveItemSearchElementV1, "reviewCount"),),
        ),
        lambda: replace(
            _request(),
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1
            + (cast(LiveItemSearchElementV1, "reviewCounts"),),
        ),
        lambda: replace(
            _request(),
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1
            + (cast(LiveItemSearchElementV1, "affiliateRate"),),
        ),
    ),
)
def test_live_safe_request_rejects_unbounded_review_rate_or_shape_drift(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(RakutenItemSearchFailure):
        factory()


def test_live_safe_request_is_redacted_non_pickleable_and_non_executable() -> None:
    request = _request()
    field_names = {field.name for field in fields(request)}

    assert "synthetic suitcase" not in repr(request)
    assert "synthetic suitcase" not in str(request)
    with pytest.raises(TypeError):
        pickle.dumps(request)
    assert field_names.isdisjoint(
        {
            "endpoint",
            "endpoint_url",
            "credential",
            "secret",
            "storage",
            "persistence",
            "min_affiliate_rate",
            "max_affiliate_rate",
            "purpose",
        }
    )
    assert all(field.default is MISSING for field in fields(request))
    assert not any(
        hasattr(request, name)
        for name in (
            "execute",
            "pagination_followups_executed",
            "persist",
            "request",
            "retries_executed",
            "save",
            "send",
            "store",
        )
    )


def test_rejected_external_text_never_reaches_failure_or_pickle_diagnostics() -> None:
    with pytest.raises(RakutenItemSearchFailure) as captured:
        replace(_request(), keyword=f"{REJECTED_CANARY}\n")

    diagnostic = f"{captured.value!s} {captured.value!r}"
    assert REJECTED_CANARY not in diagnostic
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None

    request = replace(_request(), keyword=REJECTED_CANARY)
    assert REJECTED_CANARY not in f"{request!s} {request!r}"
    with pytest.raises(TypeError) as pickle_failure:
        pickle.dumps(request)
    assert REJECTED_CANARY not in str(pickle_failure.value)


def test_invalid_unicode_is_rejected_outside_the_encoding_exception_context() -> None:
    rejected_text = f"{REJECTED_CANARY}\ud800"

    with pytest.raises(RakutenItemSearchFailure) as captured:
        replace(_request(), keyword=rejected_text)

    diagnostic = f"{captured.value!s} {captured.value!r}"
    assert REJECTED_CANARY not in diagnostic
    assert "Unicode" not in diagnostic
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None

    with pytest.raises(TypeError) as pickle_failure:
        pickle.dumps(captured.value)
    pickle_diagnostic = f"{pickle_failure.value!s} {pickle_failure.value!r}"
    assert REJECTED_CANARY not in pickle_diagnostic
    assert "Unicode" not in pickle_diagnostic


def test_module_has_no_network_environment_filesystem_or_action_surface() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_imports = {
        "boto3",
        "botocore",
        "http",
        "httpx",
        "os",
        "pathlib",
        "requests",
        "socket",
        "sqlalchemy",
        "sqlite3",
        "subprocess",
        "urllib",
    }
    imported: set[str] = set()
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.partition(".")[0])
        elif isinstance(node, ast.Call) and isinstance(
            node.func, (ast.Attribute, ast.Name)
        ):
            calls.add(
                node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            )

    assert imported.isdisjoint(forbidden_imports)
    assert calls.isdisjoint(
        {
            "commit",
            "execute",
            "getenv",
            "open",
            "persist",
            "publish",
            "request",
            "save",
            "send",
            "store",
            "unlink",
            "upload",
            "urlopen",
            "write",
        }
    )
    assert all(
        token not in source
        for token in (
            "applicationId",
            "accessKey",
            "affiliateId",
            "endpoint",
            "credential",
            "os.environ",
            "os.getenv",
        )
    )


def test_provider_parameter_surface_has_no_rate_or_active_review_filter() -> None:
    request = _request()
    parameters = request.canonical_parameters
    field_names = {field.name for field in fields(request)}

    assert request.has_review_only is False
    assert "has_review_only" not in parameters
    assert field_names.isdisjoint(
        {
            "affiliate_rate",
            "min_affiliate_rate",
            "max_affiliate_rate",
            "review_average",
            "review_count",
            "ng_keyword",
        }
    )
    assert not any("affiliate_rate" in key for key in parameters)
    assert not any(key in parameters for key in ("review_average", "review_count"))
    assert not any(key in parameters for key in ("ng_keyword", "NGKeyword"))
    assert "purpose" not in parameters
