#!/usr/bin/env python3
"""Verify three immutable FINAL ST-1703 affiliate evidence records.

This is an import-only verifier for the verified ST-1703 runtime.  It never
reads Rakuten credentials, performs a provider request, mutates the tracked
article, or prints destination URLs.  The operational input is three owner-only
request files; matching provider evidence is discovered only in the fixed
owner-local Result V3 store.  This is historical evidence verification, not a
freshness check or live re-attestation: only the exact Result bytes committed
into each FINAL slot can satisfy the verifier.
"""

from __future__ import annotations

import sys


_DIRECT_EXECUTION_REFUSAL = (
    '{"external_writes":0,"reason_code":"AFFILIATE_DIRECT_EXECUTION_DISABLED",'
    '"status":"BLOCKED"}\n'
)
if __name__ == "__main__":
    sys.stdout.write(_DIRECT_EXECUTION_REFUSAL)
    raise SystemExit(2)


# Security ordering: direct execution must stop before any shadowable import.
# ruff: noqa: E402
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, NoReturn, cast
from urllib.parse import parse_qsl, urlsplit


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if "raos" not in sys.modules and str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.rakuten_owner_local import (  # noqa: E402
    MAX_REQUEST_BYTES,
    MAX_RESULT_BYTES,
)
from raos.application.editorial.self_hosted_minimum_start import (  # noqa: E402
    CONTENT_PACKET_RELATIVE_PATH,
    RAKUTEN_CREDIT_SNIPPET,
    affiliate_destination_attestation_sha256,
    affiliate_cta_html,
    load_first_article_candidate_with_affiliate_status,
)
from raos.domain.catalog.rakuten_item_search_live_request_v1 import (  # noqa: E402
    LIVE_ITEM_SEARCH_ELEMENTS_V1,
    LiveItemSearchSortV1,
    RakutenItemSearchLiveRequestV1,
)
from raos.domain.catalog.rakuten_owner_local import (  # noqa: E402
    RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY,
    RAKUTEN_OWNER_LOCAL_FORMAL_TST_016,
    RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES,
    RAKUTEN_OWNER_LOCAL_OD_015,
    RAKUTEN_OWNER_LOCAL_PRODUCTION,
    RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION,
    RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA,
    RAKUTEN_OWNER_LOCAL_STAGING,
    RakutenOwnerLocalApi,
    RakutenOwnerLocalItemSearchRequest,
    RakutenOwnerLocalProviderResult,
    api_definition,
    normalized_record,
)
from raos.domain.editorial.self_hosted_wordpress import (  # noqa: E402
    SelfHostedWordPressOperation,
)


OWNER_REPOSITORY_ROOT = Path("/home/minami/rakuten")
OWNER_RESULT_STORE = OWNER_REPOSITORY_ROOT / ".secrets/rakuten-owner-local/results"
OWNER_REQUEST_ROOT = OWNER_REPOSITORY_ROOT / ".secrets/rakuten-owner-local/requests"
MAX_FUTURE_SKEW = timedelta(minutes=5)
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000
PRIVATE_DIRECTORY_MODE = 0o700
PRIVATE_FILE_MODE = 0o600

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_RUN_FILE = re.compile(
    r"(?P<run_id>[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{32})\.json\Z",
    re.ASCII,
)
_MALFORMED_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})", re.ASCII)
_CLOSED_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "keyword",
        "shop_code",
        "item_code",
        "genre_id",
        "hits",
        "page",
        "sort",
    }
)
_DIRECT_HOST = "hb.afl.rakuten.co.jp"
_RAKUTEN_AFFILIATE_PATH = re.compile(
    r"/hgc/[A-Za-z0-9._~-]{1,256}/\Z",
    re.ASCII,
)
_RAKUTEN_MOBILE_ITEM_PATH = re.compile(
    r"/ace-store/i/[0-9]{1,32}/\Z",
    re.ASCII,
)
_RESULT_KEYS = frozenset(
    {
        "schema",
        "version",
        "run_id",
        "started_at",
        "finished_at",
        "api",
        "endpoint_id",
        "api_version",
        "outcome",
        "diagnostic_code",
        "validation_stage_code",
        "validation_detail_code",
        "request_fingerprint",
        "request_disposition",
        "request_count",
        "retry_count",
        "pagination_count",
        "http_status",
        "body_byte_count",
        "response_sha256",
        "count",
        "page",
        "first",
        "last",
        "hits",
        "pageCount",
        "items",
        "products",
        "provider_data_classification",
        "evidence_authority",
        "formal_tst_016",
        "staging",
        "production",
        "od_015",
    }
)
_EVIDENCE_KEYS = frozenset(
    {
        "api",
        "api_version",
        "destination_attestation_sha256",
        "endpoint_id",
        "evidence_authority",
        "request_fingerprint",
        "response_sha256",
        "result_sha256",
        "retrieved_at",
    }
)


@dataclass(frozen=True, slots=True)
class _SlotDefinition:
    slot_id: str
    product_name: str
    model_code: str
    mobile_item_id: str

    @property
    def request_file_name(self) -> str:
        return f"keyword-{self.slot_id}.json"

    @property
    def exact_item_path(self) -> str:
        return f"/ace-store/{self.model_code}/"

    @property
    def exact_mobile_item_path(self) -> str:
        return f"/ace-store/i/{self.mobile_item_id}/"

    @property
    def exact_item_code(self) -> str:
        return f"ace-store:{self.mobile_item_id}"


_SLOTS = (
    _SlotDefinition("ace-cresta-06316", "ACE クレスタ 06316", "06316", "10007275"),
    _SlotDefinition(
        "ace-difference-05721",
        "ace.TOKYO LABEL ディフェレンス 05721",
        "05721",
        "10009372",
    ),
    _SlotDefinition(
        "proteca-maxpass4-01471",
        "PROTECA マックスパス4 01471",
        "01471",
        "10009099",
    ),
)
OWNER_REQUEST_PATHS = {
    slot.slot_id: OWNER_REQUEST_ROOT / slot.request_file_name for slot in _SLOTS
}

_FAILURE_CODES = frozenset(
    {
        "AFFILIATE_ARGUMENT_INVALID",
        "AFFILIATE_CONTENT_STATE_INVALID",
        "AFFILIATE_REQUEST_INVALID",
        "AFFILIATE_RESULT_STORE_INVALID",
        "AFFILIATE_RESULT_INVALID",
        "AFFILIATE_RESULT_STALE",
        "AFFILIATE_RESULT_MISSING_OR_DUPLICATE",
        "AFFILIATE_RESULT_IDENTITY_MISMATCH",
        "AFFILIATE_DESTINATION_INVALID",
        "AFFILIATE_OUTPUT_INVALID",
    }
)


class AffiliateFinalizationFailure(RuntimeError):
    """Closed value-free failure for the local affiliate verifier."""

    __slots__ = ("code",)

    def __init__(self, code: str) -> None:
        if type(code) is not str or code not in _FAILURE_CODES:
            raise TypeError("invalid affiliate finalization failure")
        self.code = code
        super().__init__(code)

    def __str__(self) -> str:
        return self.code


def _fail(code: str) -> NoReturn:
    raise AffiliateFinalizationFailure(code) from None


class _DuplicateKey(ValueError):
    pass


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _json_shape(value: object, *, code: str) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _fail(code)
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            if any(type(key) is not str for key in mapping):
                _fail(code)
            pending.extend((item, depth + 1) for item in mapping.values())
        elif type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
        elif current is not None and type(current) not in {bool, int, str}:
            _fail(code)


def _strict_json(raw: bytes, *, code: str) -> dict[str, object]:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(code)
    if type(value) is not dict:
        _fail(code)
    _json_shape(value, code=code)
    return cast(dict[str, object], value)


def _parse_utc(value: object) -> datetime:
    if type(value) is not str or len(value) != 27 or not value.endswith("Z"):
        _fail("AFFILIATE_RESULT_INVALID")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        _fail("AFFILIATE_RESULT_INVALID")
    if parsed.fold != 0:
        _fail("AFFILIATE_RESULT_INVALID")
    return parsed


def _open_absolute_directory(
    path: Path,
    *,
    require_private: bool,
    code: str = "AFFILIATE_RESULT_STORE_INVALID",
) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail(code)
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        current = os.open("/", flags)
        for part in path.parts[1:]:
            child = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = child
        details = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if (
            not stat.S_ISDIR(details.st_mode)
            or details.st_dev != named.st_dev
            or details.st_ino != named.st_ino
            or (
                require_private
                and (
                    details.st_uid != os.getuid()
                    or stat.S_IMODE(details.st_mode) != PRIVATE_DIRECTORY_MODE
                    or details.st_nlink < 2
                )
            )
        ):
            raise OSError
        return current
    except BaseException:
        try:
            os.close(current)
        except UnboundLocalError, OSError:
            pass
        _fail(code)


def _identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
        details.st_size,
        details.st_mtime_ns,
        details.st_ctime_ns,
    )


def _directory_object_identity(details: os.stat_result) -> tuple[int, ...]:
    return (
        details.st_dev,
        details.st_ino,
        details.st_mode,
        details.st_uid,
        details.st_gid,
        details.st_nlink,
    )


def _same_named_object(
    details: os.stat_result,
    *,
    parent_fd: int,
    name: str,
    code: str,
) -> None:
    try:
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError:
        _fail(code)
    if _identity(named) != _identity(details):
        _fail(code)


def _require_directory_binding(
    path: Path,
    descriptor: int,
    *,
    require_private: bool,
    expected_identity: tuple[int, ...] | None = None,
    code: str,
) -> tuple[int, ...]:
    rebound_fd = -1
    try:
        held = os.fstat(descriptor)
        rebound_fd = _open_absolute_directory(
            path,
            require_private=require_private,
            code=code,
        )
        rebound = os.fstat(rebound_fd)
    except AffiliateFinalizationFailure:
        raise
    except OSError:
        _fail(code)
    finally:
        if rebound_fd >= 0:
            os.close(rebound_fd)
    held_identity = _directory_object_identity(held)
    if held_identity != _directory_object_identity(rebound) or (
        expected_identity is not None and held_identity != expected_identity
    ):
        _fail(code)
    return held_identity


def _read_regular_at(
    parent_fd: int,
    name: str,
    *,
    maximum: int,
    required_mode: int | None,
    code: str,
) -> tuple[bytes, os.stat_result]:
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=parent_fd,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
            or (
                required_mode is not None
                and stat.S_IMODE(before.st_mode) != required_mode
            )
        ):
            _fail(code)
        _same_named_object(before, parent_fd=parent_fd, name=name, code=code)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                _fail(code)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(code)
        after = os.fstat(descriptor)
        if _identity(after) != _identity(before):
            _fail(code)
        _same_named_object(after, parent_fd=parent_fd, name=name, code=code)
        payload = b"".join(chunks)
        if len(payload) != before.st_size:
            _fail(code)
        return payload, before
    except AffiliateFinalizationFailure:
        raise
    except OSError:
        _fail(code)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_private_result(
    directory_fd: int,
    name: str,
) -> tuple[bytes, tuple[int, ...]]:
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = -1
    try:
        descriptor = os.open(name, flags, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_RESULT_BYTES
        ):
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        payload = b""
        while len(payload) <= MAX_RESULT_BYTES:
            chunk = os.read(
                descriptor, min(64 * 1024, MAX_RESULT_BYTES + 1 - len(payload))
            )
            if not chunk:
                break
            payload += chunk
        os.lseek(descriptor, 0, os.SEEK_SET)
        verification = b""
        while len(verification) <= MAX_RESULT_BYTES:
            chunk = os.read(
                descriptor,
                min(64 * 1024, MAX_RESULT_BYTES + 1 - len(verification)),
            )
            if not chunk:
                break
            verification += chunk
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        identity_before = _identity(before)
        identity_after = _identity(after)
        identity_named = _identity(named)
        if (
            len(payload) != before.st_size
            or len(payload) > MAX_RESULT_BYTES
            or verification != payload
            or identity_before != identity_after
            or identity_after != identity_named
        ):
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        return payload, identity_before
    except AffiliateFinalizationFailure:
        raise
    except OSError:
        _fail("AFFILIATE_RESULT_STORE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _validate_direct_destination(value: object, slot: _SlotDefinition) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= 4096
        or value != value.strip()
        or not value.isascii()
        or any(character.isspace() or ord(character) < 0x21 for character in value)
        or any(character in value for character in "\\\"'<>[]")
        or _MALFORMED_PERCENT_ESCAPE.search(value) is not None
    ):
        _fail("AFFILIATE_DESTINATION_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        _fail("AFFILIATE_DESTINATION_INVALID")
    if (
        parsed.scheme != "https"
        or parsed.netloc != _DIRECT_HOST
        or parsed.hostname != _DIRECT_HOST
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or _RAKUTEN_AFFILIATE_PATH.fullmatch(parsed.path) is None
        or parsed.fragment
    ):
        _fail("AFFILIATE_DESTINATION_INVALID")
    try:
        query_pairs = parse_qsl(
            parsed.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
    except ValueError:
        _fail("AFFILIATE_DESTINATION_INVALID")
    query = dict(query_pairs)
    if (
        len(query_pairs) != 3
        or len(query) != 3
        or frozenset(query) != frozenset({"m", "pc", "rafcid"})
        or not query["rafcid"]
        or not query["rafcid"].isascii()
        or len(query["rafcid"]) > 512
    ):
        _fail("AFFILIATE_DESTINATION_INVALID")
    try:
        desktop = urlsplit(query["pc"])
        mobile = urlsplit(query["m"])
        desktop_port = desktop.port
        mobile_port = mobile.port
    except ValueError:
        _fail("AFFILIATE_DESTINATION_INVALID")
    if (
        desktop.scheme != "https"
        or desktop.netloc != "item.rakuten.co.jp"
        or desktop.hostname != "item.rakuten.co.jp"
        or desktop.username is not None
        or desktop.password is not None
        or desktop_port is not None
        or desktop.path != slot.exact_item_path
        or desktop.query
        or desktop.fragment
        or mobile.scheme not in {"http", "https"}
        or mobile.netloc != "m.rakuten.co.jp"
        or mobile.hostname != "m.rakuten.co.jp"
        or mobile.username is not None
        or mobile.password is not None
        or mobile_port is not None
        or _RAKUTEN_MOBILE_ITEM_PATH.fullmatch(mobile.path) is None
        or mobile.path != slot.exact_mobile_item_path
        or mobile.query
        or mobile.fragment
    ):
        _fail("AFFILIATE_DESTINATION_INVALID")
    return value


@dataclass(frozen=True, slots=True)
class _ValidatedResult:
    request_fingerprint: str
    response_sha256: str
    result_sha256: str
    retrieved_at: str
    finished_at: datetime
    items: tuple[dict[str, object], ...]


def _result_fingerprint(
    raw: bytes,
    *,
    file_name: str,
    expected: set[str],
) -> str | None:
    """Validate the closed Result V3 envelope identity before filtering."""

    value = _strict_json(raw, code="AFFILIATE_RESULT_INVALID")
    run_match = _RUN_FILE.fullmatch(file_name)
    fingerprint = value.get("request_fingerprint")
    if (
        run_match is None
        or value.get("run_id") != run_match.group("run_id")
        or type(fingerprint) is not str
        or _SHA256.fullmatch(fingerprint) is None
    ):
        _fail("AFFILIATE_RESULT_INVALID")
    predecessor = (
        ("RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V1", 1),
        ("RAOS_ST0505_RAKUTEN_OWNER_LOCAL_RESULT_V2", 2),
    )
    if (value.get("schema"), value.get("version")) in predecessor:
        if fingerprint in expected:
            _fail("AFFILIATE_RESULT_INVALID")
        return None
    if (
        frozenset(value) != _RESULT_KEYS
        or value.get("schema") != RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA
        or value.get("version") != 3
    ):
        _fail("AFFILIATE_RESULT_INVALID")
    return fingerprint


def _validated_result(
    raw: bytes,
    *,
    file_name: str,
) -> _ValidatedResult:
    value = _strict_json(raw, code="AFFILIATE_RESULT_INVALID")
    definition = api_definition(RakutenOwnerLocalApi.ITEM_SEARCH)
    run_match = _RUN_FILE.fullmatch(file_name)
    request_fingerprint = value.get("request_fingerprint")
    response_sha256 = value.get("response_sha256")
    if (
        frozenset(value) != _RESULT_KEYS
        or run_match is None
        or value.get("schema") != RAKUTEN_OWNER_LOCAL_RESULT_SCHEMA
        or value.get("version") != 3
        or value.get("run_id") != run_match.group("run_id")
        or value.get("api") != RakutenOwnerLocalApi.ITEM_SEARCH.value
        or value.get("endpoint_id") != definition.endpoint_id
        or value.get("api_version") != definition.api_version
        or value.get("outcome") != "SUCCESS"
        or value.get("diagnostic_code") != "PASS"
        or value.get("validation_stage_code") is not None
        or value.get("validation_detail_code") is not None
        or type(request_fingerprint) is not str
        or _SHA256.fullmatch(request_fingerprint) is None
        or value.get("request_disposition") != "RESPONSE_RECEIVED"
        or value.get("request_count") != 1
        or value.get("retry_count") != 0
        or value.get("pagination_count") != 0
        or value.get("http_status") != 200
        or type(value.get("body_byte_count")) is not int
        or not 2
        <= cast(int, value["body_byte_count"])
        <= RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES
        or type(response_sha256) is not str
        or _SHA256.fullmatch(response_sha256) is None
        or value.get("hits") != 30
        or value.get("page") != 1
        or value.get("products") is not None
        or value.get("provider_data_classification")
        != RAKUTEN_OWNER_LOCAL_PROVIDER_DATA_CLASSIFICATION
        or value.get("evidence_authority") != RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY
        or value.get("formal_tst_016") != RAKUTEN_OWNER_LOCAL_FORMAL_TST_016
        or value.get("staging") != RAKUTEN_OWNER_LOCAL_STAGING
        or value.get("production") != RAKUTEN_OWNER_LOCAL_PRODUCTION
        or value.get("od_015") != RAKUTEN_OWNER_LOCAL_OD_015
        or type(value.get("items")) is not list
    ):
        _fail("AFFILIATE_RESULT_INVALID")
    started = _parse_utc(value.get("started_at"))
    finished = _parse_utc(value.get("finished_at"))
    if started > finished:
        _fail("AFFILIATE_RESULT_INVALID")
    raw_items = cast(list[object], value["items"])
    if any(type(item) is not dict for item in raw_items):
        _fail("AFFILIATE_RESULT_INVALID")
    try:
        normalized = tuple(
            normalized_record(
                RakutenOwnerLocalApi.ITEM_SEARCH,
                cast(dict[str, object], item),
            )
            for item in raw_items
        )
        RakutenOwnerLocalProviderResult(
            api=RakutenOwnerLocalApi.ITEM_SEARCH,
            request_fingerprint=request_fingerprint,
            http_status=cast(int, value["http_status"]),
            body_byte_count=cast(int, value["body_byte_count"]),
            response_sha256=response_sha256,
            count=cast(int, value["count"]),
            page=cast(int, value["page"]),
            first=cast(int, value["first"]),
            last=cast(int, value["last"]),
            hits=cast(int, value["hits"]),
            page_count=cast(int, value["pageCount"]),
            records=normalized,
        )
    except BaseException:
        _fail("AFFILIATE_RESULT_INVALID")
    return _ValidatedResult(
        request_fingerprint=request_fingerprint,
        response_sha256=response_sha256,
        result_sha256=hashlib.sha256(raw).hexdigest(),
        retrieved_at=cast(str, value["finished_at"]),
        finished_at=finished,
        items=tuple(cast(dict[str, object], item) for item in raw_items),
    )


def _decode_closed_request_snapshot(
    raw: bytes,
    slot: _SlotDefinition,
) -> RakutenOwnerLocalItemSearchRequest:
    """Decode only the three reviewed ST-1703 request shapes from captured bytes."""

    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        _fail("AFFILIATE_REQUEST_INVALID")
    mapping = _strict_json(raw, code="AFFILIATE_REQUEST_INVALID")
    if (
        frozenset(mapping) != _CLOSED_REQUEST_KEYS
        or type(mapping["schema_version"]) is not int
        or mapping["schema_version"] != 1
        or type(mapping["keyword"]) is not str
        or mapping["keyword"] != slot.model_code
        or mapping["shop_code"] is not None
        or mapping["item_code"] is not None
        or mapping["genre_id"] is not None
        or type(mapping["hits"]) is not int
        or mapping["hits"] != 30
        or type(mapping["page"]) is not int
        or mapping["page"] != 1
        or type(mapping["sort"]) is not str
        or mapping["sort"] != LiveItemSearchSortV1.STANDARD.value
    ):
        _fail("AFFILIATE_REQUEST_INVALID")
    try:
        policy = RakutenItemSearchLiveRequestV1(
            api_version="2026-07-01",
            format_version=2,
            keyword=slot.model_code,
            shop_code=None,
            item_code=None,
            genre_id=None,
            hits=30,
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
        return RakutenOwnerLocalItemSearchRequest(policy=policy)
    except BaseException:
        _fail("AFFILIATE_REQUEST_INVALID")


def _request_fingerprints(
    request_paths: Mapping[str, Path],
) -> dict[str, str]:
    if frozenset(request_paths) != frozenset(slot.slot_id for slot in _SLOTS):
        _fail("AFFILIATE_ARGUMENT_INVALID")
    fingerprints: dict[str, str] = {}
    for slot in _SLOTS:
        path = request_paths[slot.slot_id]
        if not path.is_absolute() or path.name != slot.request_file_name:
            _fail("AFFILIATE_REQUEST_INVALID")
        parent_fd = _open_absolute_directory(
            path.parent,
            require_private=True,
            code="AFFILIATE_REQUEST_INVALID",
        )
        try:
            request_bytes, _request_details = _read_regular_at(
                parent_fd,
                path.name,
                maximum=MAX_REQUEST_BYTES,
                required_mode=PRIVATE_FILE_MODE,
                code="AFFILIATE_REQUEST_INVALID",
            )
            request_parent_identity = _require_directory_binding(
                path.parent,
                parent_fd,
                require_private=True,
                code="AFFILIATE_REQUEST_INVALID",
            )
            request = _decode_closed_request_snapshot(request_bytes, slot)
        except BaseException:
            _fail("AFFILIATE_REQUEST_INVALID")
        finally:
            os.close(parent_fd)
        terminal_parent_fd = _open_absolute_directory(
            path.parent,
            require_private=True,
            code="AFFILIATE_REQUEST_INVALID",
        )
        try:
            terminal_bytes, _terminal_details = _read_regular_at(
                terminal_parent_fd,
                path.name,
                maximum=MAX_REQUEST_BYTES,
                required_mode=PRIVATE_FILE_MODE,
                code="AFFILIATE_REQUEST_INVALID",
            )
            if (
                terminal_bytes != request_bytes
                or _require_directory_binding(
                    path.parent,
                    terminal_parent_fd,
                    require_private=True,
                    expected_identity=request_parent_identity,
                    code="AFFILIATE_REQUEST_INVALID",
                )
                != request_parent_identity
            ):
                _fail("AFFILIATE_REQUEST_INVALID")
        finally:
            os.close(terminal_parent_fd)
        if (
            type(request) is not RakutenOwnerLocalItemSearchRequest
            or request.policy.keyword != slot.model_code
            or request.policy.shop_code is not None
            or request.policy.item_code is not None
            or request.policy.genre_id is not None
            or request.policy.hits != 30
            or request.policy.page != 1
            or request.policy.sort is not LiveItemSearchSortV1.STANDARD
        ):
            _fail("AFFILIATE_REQUEST_INVALID")
        fingerprints[slot.slot_id] = request.fingerprint
    if len(set(fingerprints.values())) != len(_SLOTS):
        _fail("AFFILIATE_REQUEST_INVALID")
    return fingerprints


@dataclass(frozen=True, slots=True)
class _CommittedFinalSlot:
    definition: _SlotDefinition
    destination_url: str
    evidence: dict[str, str]


@dataclass(frozen=True, slots=True)
class _ResultSnapshot:
    verified: tuple[_CommittedFinalSlot, ...]
    store_identity: tuple[int, ...]
    inventory: tuple[tuple[str, str, tuple[int, ...]], ...]


def _provider_evidence(result: _ValidatedResult) -> dict[str, str]:
    definition = api_definition(RakutenOwnerLocalApi.ITEM_SEARCH)
    return {
        "api": RakutenOwnerLocalApi.ITEM_SEARCH.value,
        "api_version": definition.api_version,
        "endpoint_id": definition.endpoint_id,
        "evidence_authority": RAKUTEN_OWNER_LOCAL_EVIDENCE_AUTHORITY,
        "request_fingerprint": result.request_fingerprint,
        "response_sha256": result.response_sha256,
        "result_sha256": result.result_sha256,
        "retrieved_at": result.retrieved_at,
    }


def _verified_slot_from_result(
    slot: _SlotDefinition,
    result: _ValidatedResult,
) -> _CommittedFinalSlot:
    identity_matches: list[dict[str, object]] = []
    for item in result.items:
        item_name = item.get("itemName")
        item_code = item.get("itemCode")
        if (
            item.get("shopCode") == "ace-store"
            and type(item_name) is str
            and slot.model_code in item_name
            and item_code == slot.exact_item_code
        ):
            identity_matches.append(item)
    if len(identity_matches) != 1:
        _fail("AFFILIATE_RESULT_IDENTITY_MISMATCH")
    item = identity_matches[0]
    affiliate_url = item.get("affiliateUrl")
    if affiliate_url != item.get("itemUrl"):
        _fail("AFFILIATE_DESTINATION_INVALID")
    destination = _validate_direct_destination(affiliate_url, slot)
    provider_evidence = _provider_evidence(result)
    evidence = {
        **provider_evidence,
        "destination_attestation_sha256": (
            affiliate_destination_attestation_sha256(
                slot.slot_id,
                destination,
                provider_evidence,
            )
        ),
    }
    if frozenset(evidence) != _EVIDENCE_KEYS:
        _fail("AFFILIATE_OUTPUT_INVALID")
    return _CommittedFinalSlot(
        definition=slot,
        destination_url=destination,
        evidence=evidence,
    )


def _scan_results(
    result_store: Path,
    *,
    committed_slots: tuple[_CommittedFinalSlot, ...],
    now: datetime,
) -> _ResultSnapshot:
    if type(now) is not datetime or now.tzinfo is not timezone.utc or now.fold != 0:
        _fail("AFFILIATE_ARGUMENT_INVALID")
    if (
        type(committed_slots) is not tuple
        or len(committed_slots) != len(_SLOTS)
        or any(
            type(committed) is not _CommittedFinalSlot
            or committed.definition != definition
            for committed, definition in zip(committed_slots, _SLOTS, strict=True)
        )
    ):
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    expected_by_fingerprint: dict[str, _CommittedFinalSlot] = {}
    for committed in committed_slots:
        fingerprint = committed.evidence.get("request_fingerprint")
        if (
            type(fingerprint) is not str
            or _SHA256.fullmatch(fingerprint) is None
            or fingerprint in expected_by_fingerprint
        ):
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        expected_by_fingerprint[fingerprint] = committed
    directory_fd = _open_absolute_directory(result_store, require_private=True)
    try:
        try:
            store_identity = _directory_object_identity(os.fstat(directory_fd))
        except OSError:
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError:
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        if not names or any(_RUN_FILE.fullmatch(name) is None for name in names):
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        expected = set(expected_by_fingerprint)
        matches: dict[str, list[_ValidatedResult]] = {
            fingerprint: [] for fingerprint in expected
        }
        inventory: list[tuple[str, str, tuple[int, ...]]] = []
        for name in names:
            raw, result_identity = _read_private_result(directory_fd, name)
            inventory.append((name, hashlib.sha256(raw).hexdigest(), result_identity))
            fingerprint = _result_fingerprint(
                raw,
                file_name=name,
                expected=expected,
            )
            if fingerprint is None:
                continue
            if fingerprint in expected:
                result = _validated_result(raw, file_name=name)
                committed = expected_by_fingerprint[result.request_fingerprint]
                expected_provider_evidence = {
                    key: committed.evidence[key]
                    for key in _EVIDENCE_KEYS
                    if key != "destination_attestation_sha256"
                }
                if _provider_evidence(result) == expected_provider_evidence:
                    # Only the immutable selected evidence has timestamp authority.
                    if result.finished_at - now > MAX_FUTURE_SKEW:
                        _fail("AFFILIATE_RESULT_STALE")
                    matches[result.request_fingerprint].append(result)
        try:
            terminal_names = sorted(os.listdir(directory_fd))
            terminal_identity = _directory_object_identity(os.fstat(directory_fd))
        except OSError:
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        if terminal_names != names or terminal_identity != store_identity:
            _fail("AFFILIATE_RESULT_STORE_INVALID")
        _require_directory_binding(
            result_store,
            directory_fd,
            require_private=True,
            expected_identity=store_identity,
            code="AFFILIATE_RESULT_STORE_INVALID",
        )
    finally:
        os.close(directory_fd)

    verified: list[_CommittedFinalSlot] = []
    for committed in committed_slots:
        fingerprint = committed.evidence["request_fingerprint"]
        matching_results = matches[fingerprint]
        if len(matching_results) != 1:
            _fail("AFFILIATE_RESULT_MISSING_OR_DUPLICATE")
        result = matching_results[0]
        verified_slot = _verified_slot_from_result(committed.definition, result)
        if verified_slot != committed:
            _fail("AFFILIATE_RESULT_IDENTITY_MISMATCH")
        verified.append(verified_slot)
    return _ResultSnapshot(tuple(verified), store_identity, tuple(inventory))


@dataclass(frozen=True, slots=True)
class _ContentSnapshot:
    raw: bytes
    raw_sha256: str
    target_identity: tuple[int, ...]
    target_mode: int
    parent_identity: tuple[int, ...]


def _read_content_packet(path: Path) -> _ContentSnapshot:
    if not path.is_absolute() or path.name != CONTENT_PACKET_RELATIVE_PATH.name:
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    parent_fd = -1
    try:
        parent_fd = _open_absolute_directory(
            path.parent,
            require_private=False,
            code="AFFILIATE_CONTENT_STATE_INVALID",
        )
        parent_identity = _require_directory_binding(
            path.parent,
            parent_fd,
            require_private=False,
            code="AFFILIATE_CONTENT_STATE_INVALID",
        )
        raw, details = _read_regular_at(
            parent_fd,
            path.name,
            maximum=256 * 1024,
            required_mode=None,
            code="AFFILIATE_CONTENT_STATE_INVALID",
        )
        target_mode = stat.S_IMODE(details.st_mode)
        if target_mode & 0o022:
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        _require_directory_binding(
            path.parent,
            parent_fd,
            require_private=False,
            expected_identity=parent_identity,
            code="AFFILIATE_CONTENT_STATE_INVALID",
        )
    except AffiliateFinalizationFailure:
        raise
    except OSError:
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    finally:
        if parent_fd >= 0:
            os.close(parent_fd)
    return _ContentSnapshot(
        raw=raw,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        target_identity=_identity(details),
        target_mode=target_mode,
        parent_identity=parent_identity,
    )


def _load_committed_final_slots(
    repository_root: Path,
    *,
    snapshot: _ContentSnapshot,
) -> tuple[_CommittedFinalSlot, ...]:
    try:
        _candidate, affiliate_status = (
            load_first_article_candidate_with_affiliate_status(
                repository_root,
                operation=SelfHostedWordPressOperation.CREATE_DRAFT,
                packet_bytes=snapshot.raw,
            )
        )
    except BaseException:
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    if affiliate_status != "FINAL":
        _fail("AFFILIATE_CONTENT_STATE_INVALID")

    parsed = _strict_json(snapshot.raw, code="AFFILIATE_CONTENT_STATE_INVALID")
    article = parsed.get("article")
    if type(article) is not dict:
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    article_mapping = cast(dict[str, object], article)
    slots = article_mapping.get("affiliate_slots")
    content = article_mapping.get("content_html")
    if (
        type(slots) is not list
        or type(content) is not str
        or len(slots) != len(_SLOTS)
        or content.count(RAKUTEN_CREDIT_SNIPPET) != 1
    ):
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    committed_slots: list[_CommittedFinalSlot] = []
    for item, definition in zip(cast(list[object], slots), _SLOTS, strict=True):
        if type(item) is not dict:
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        item_mapping = cast(dict[str, object], item)
        destination = item_mapping.get("destination_url")
        evidence_value = item_mapping.get("evidence")
        if (
            frozenset(item_mapping)
            != frozenset(
                {
                    "destination_policy",
                    "destination_url",
                    "evidence",
                    "product_name",
                    "required_rel",
                    "slot_id",
                    "status",
                }
            )
            or type(destination) is not str
            or type(evidence_value) is not dict
        ):
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        evidence_mapping = cast(dict[str, object], evidence_value)
        if frozenset(evidence_mapping) != _EVIDENCE_KEYS or any(
            type(value) is not str for value in evidence_mapping.values()
        ):
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        evidence = {key: cast(str, evidence_mapping[key]) for key in _EVIDENCE_KEYS}
        expected = {
            "destination_policy": "DIRECT_RAKUTEN_AFFILIATE_URL",
            "destination_url": destination,
            "evidence": evidence,
            "product_name": definition.product_name,
            "required_rel": "sponsored nofollow",
            "slot_id": definition.slot_id,
            "status": "FINAL_OFFICIAL_RAKUTEN_LINK",
        }
        if (
            item_mapping != expected
            or content.count(affiliate_cta_html(definition.slot_id, destination)) != 1
        ):
            _fail("AFFILIATE_CONTENT_STATE_INVALID")
        committed_slots.append(
            _CommittedFinalSlot(
                definition=definition,
                destination_url=destination,
                evidence=evidence,
            )
        )
    return tuple(committed_slots)


def verify(
    *,
    repository_root: Path,
    result_store: Path,
    request_paths: Mapping[str, Path],
    now: datetime,
    expected_content_packet_bytes: bytes | None = None,
) -> dict[str, object]:
    if (
        not repository_root.is_absolute()
        or not result_store.is_absolute()
        or type(request_paths) is not dict
    ):
        _fail("AFFILIATE_ARGUMENT_INVALID")

    content_path = repository_root / CONTENT_PACKET_RELATIVE_PATH
    content_snapshot = _read_content_packet(content_path)
    if expected_content_packet_bytes is not None and (
        type(expected_content_packet_bytes) is not bytes
        or content_snapshot.raw != expected_content_packet_bytes
    ):
        _fail("AFFILIATE_CONTENT_STATE_INVALID")
    committed_slots = _load_committed_final_slots(
        repository_root,
        snapshot=content_snapshot,
    )
    fingerprints = _request_fingerprints(request_paths)
    if any(
        fingerprints[committed.definition.slot_id]
        != committed.evidence["request_fingerprint"]
        for committed in committed_slots
    ):
        _fail("AFFILIATE_REQUEST_INVALID")
    result_snapshot = _scan_results(
        result_store,
        committed_slots=committed_slots,
        now=now,
    )

    terminal_results = _scan_results(
        result_store,
        committed_slots=committed_slots,
        now=now,
    )
    if terminal_results != result_snapshot:
        _fail("AFFILIATE_RESULT_STORE_INVALID")
    terminal_content = _read_content_packet(content_path)
    if terminal_content != content_snapshot:
        _fail("AFFILIATE_CONTENT_STATE_INVALID")

    return {
        "affiliate_slots_verified": len(result_snapshot.verified),
        "credential_value_reads": 0,
        "external_writes": 0,
        "network_requests": 0,
        "packet_sha256": content_snapshot.raw_sha256,
        "provider_urls_printed": 0,
        "status": "AFFILIATE_LINKS_VERIFIED",
    }
