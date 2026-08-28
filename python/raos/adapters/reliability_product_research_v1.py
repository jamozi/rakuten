"""Recorded and fail-closed live adapters for product research V1."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
import tempfile
import time
from typing import Final, NoReturn, Protocol, cast, final, runtime_checkable
from urllib.parse import urlencode, urlsplit, urlunsplit

from raos.domain.reliability.contracts_v1 import (
    AcquisitionMethodV1,
    ArtifactRefV1,
    DiscoveryOfferV1,
    OfficialPageEvidenceV1,
    ProviderPageV1,
    ReviewThemeSetV1,
    SocialSignalSetV1,
    SourceDecisionV1,
    SourcePolicyV1,
    StrictContractV1,
    artifact_ref,
    canonical_json_bytes,
)


RAKUTEN_SOURCE_ID: Final = "RAKUTEN_ICHIBA"
YAHOO_SOURCE_ID: Final = "YAHOO_SHOPPING"
RAKUTEN_HOST: Final = "openapi.rakuten.co.jp"
RAKUTEN_PATH: Final = "/ichibams/api/IchibaItem/Search/20260701"
YAHOO_HOST: Final = "shopping.yahooapis.jp"
YAHOO_PATH: Final = "/ShoppingWebService/V3/itemSearch"
RAKUTEN_CREDENTIAL_PATH: Final = Path(
    ".secrets/rakuten-owner-local/credentials.v1.json"
)
YAHOO_CREDENTIAL_PATH: Final = Path(
    ".secrets/yahoo-shopping-owner-local/credentials.v1.json"
)
MAX_RESPONSE_BYTES: Final = 8_388_608
MAX_CREDENTIAL_BYTES: Final = 4096
MAX_HTML_BYTES: Final = 4_194_304
USER_AGENT: Final = "RAOS-reliability-product-research/1"
_FORBIDDEN_PROXY_ENV: Final = frozenset(
    {
        "ALL_PROXY",
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "SSLKEYLOGFILE",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
        "sslkeylogfile",
    }
)
_JSON_MIME = re.compile(
    r'application/json(?:\s*;\s*charset="?(?:utf-8|UTF-8)"?)?\Z',
    re.ASCII,
)


class ResearchAdapterFailureCodeV1(str):
    POLICY_BLOCKED = "POLICY_BLOCKED"
    TERMS_RECORD_REQUIRED = "TERMS_RECORD_REQUIRED"
    TERMS_RECORD_EXPIRED = "TERMS_RECORD_EXPIRED"
    CREDENTIAL_UNAVAILABLE = "CREDENTIAL_UNAVAILABLE"
    CREDENTIAL_UNSAFE = "CREDENTIAL_UNSAFE"
    NETWORK_UNSAFE = "NETWORK_UNSAFE"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    CREDENTIAL_REFLECTION = "CREDENTIAL_REFLECTION"
    FIXTURE_UNAVAILABLE = "FIXTURE_UNAVAILABLE"
    STORE_UNSAFE = "STORE_UNSAFE"


class ResearchAdapterFailureV1(RuntimeError):
    """Sanitized adapter failure with no provider or credential material."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _fail(code: str) -> NoReturn:
    raise ResearchAdapterFailureV1(code) from None


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return value.astimezone(timezone.utc)


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
        result[key] = value
    return result


def _json(raw: bytes) -> Mapping[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_RESPONSE_BYTES:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs)
    except Exception:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    if type(value) is not dict:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return cast(Mapping[str, object], value)


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return cast(list[object], value)


def _text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return value


def _optional_text(value: object, *, maximum: int) -> str | None:
    if value in {None, ""}:
        return None
    return _text(value, maximum=maximum)


def _integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return value


def _decimal(value: object) -> Decimal:
    if type(value) in {int, str}:
        rendered = str(value)
    elif type(value) is float:
        rendered = repr(value)
    else:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    if len(rendered) > 40:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    try:
        return Decimal(rendered)
    except Exception:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)


def _sanitized_url(value: object) -> str:
    raw = _text(value, maximum=2048)
    try:
        parsed = urlsplit(raw)
    except ValueError:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", ""))


def _fingerprint(source_id: str, query_index: int, query: str, page: int) -> str:
    material = json.dumps(
        {
            "page": page,
            "query": query,
            "query_index": query_index,
            "source_id": source_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def parse_rakuten_page_v1(
    raw: bytes,
    *,
    query_index: int,
    query: str,
    page: int,
    observed_at: datetime,
) -> ProviderPageV1:
    document = _json(raw)
    rows_value = document.get("Items", document.get("items"))
    if rows_value is None:
        _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
    rows = _list(rows_value)
    offers: list[DiscoveryOfferV1] = []
    for raw_row in rows:
        row = _mapping(raw_row)
        if set(row) == {"Item"}:
            row = _mapping(row["Item"])
        item_id = _text(row.get("itemCode"), maximum=300)
        title = _text(row.get("itemName"), maximum=500)
        url = _sanitized_url(row.get("itemUrl"))
        review_average = row.get("reviewAverage")
        review_count = row.get("reviewCount")
        price = row.get("itemPrice")
        offers.append(
            DiscoveryOfferV1(
                source_id=RAKUTEN_SOURCE_ID,
                provider_item_id=item_id,
                item_url=url,
                title=title,
                jan_gtin=_optional_text(row.get("jan"), maximum=14),
                brand=_optional_text(
                    row.get("brandName", row.get("shopName")), maximum=120
                ),
                manufacturer_part_number=_optional_text(
                    row.get("manufacturerPartNumber"), maximum=120
                ),
                variant_label=_optional_text(row.get("variantLabel"), maximum=160),
                displayed_price_jpy=(
                    None if price is None else _integer(price, minimum=1)
                ),
                review_average=(
                    None if review_average is None else _decimal(review_average)
                ),
                review_count=(
                    None
                    if review_count is None
                    else _integer(review_count, minimum=0)
                ),
                observed_at=_utc(observed_at),
            )
        )
    page_count = document.get("pageCount")
    is_last = not rows
    if page_count is not None:
        is_last = page >= _integer(page_count, minimum=0)
    return ProviderPageV1(
        source_id=RAKUTEN_SOURCE_ID,
        query_index=query_index,
        page=page,
        offers=tuple(offers),
        request_fingerprint=_fingerprint(
            RAKUTEN_SOURCE_ID, query_index, query, page
        ),
        response_sha256=hashlib.sha256(raw).hexdigest(),
        is_last_page=is_last,
    )


def parse_yahoo_page_v1(
    raw: bytes,
    *,
    query_index: int,
    query: str,
    page: int,
    observed_at: datetime,
) -> ProviderPageV1:
    document = _json(raw)
    rows = _list(document.get("hits", []))
    offers: list[DiscoveryOfferV1] = []
    for raw_row in rows:
        row = _mapping(raw_row)
        review = _mapping(row.get("review", {}))
        brand_value = row.get("brand")
        brand = None
        if brand_value is not None:
            brand_row = _mapping(brand_value)
            brand = _optional_text(brand_row.get("name"), maximum=120)
        price_value = row.get("price")
        if type(price_value) is dict:
            price_value = _mapping(cast(object, price_value)).get("value")
        offers.append(
            DiscoveryOfferV1(
                source_id=YAHOO_SOURCE_ID,
                provider_item_id=_text(
                    row.get("code", row.get("index")), maximum=300
                ),
                item_url=_sanitized_url(row.get("url")),
                title=_text(row.get("name"), maximum=500),
                jan_gtin=_optional_text(row.get("janCode"), maximum=14),
                brand=brand,
                manufacturer_part_number=_optional_text(
                    row.get("model"), maximum=120
                ),
                variant_label=None,
                displayed_price_jpy=(
                    None
                    if price_value is None
                    else int(_decimal(price_value))
                ),
                review_average=(
                    None
                    if review.get("rate") is None
                    else _decimal(review["rate"])
                ),
                review_count=(
                    None
                    if review.get("count") is None
                    else _integer(review["count"], minimum=0)
                ),
                observed_at=_utc(observed_at),
            )
        )
    total = _integer(document.get("totalResultsAvailable", len(rows)), minimum=0)
    first = _integer(document.get("firstResultsPosition", 1), minimum=0)
    returned = _integer(document.get("totalResultsReturned", len(rows)), minimum=0)
    is_last = not rows or first + returned > total
    return ProviderPageV1(
        source_id=YAHOO_SOURCE_ID,
        query_index=query_index,
        page=page,
        offers=tuple(offers),
        request_fingerprint=_fingerprint(YAHOO_SOURCE_ID, query_index, query, page),
        response_sha256=hashlib.sha256(raw).hexdigest(),
        is_last_page=is_last,
    )


@final
class RecordedProductSearchAdapterV1:
    """Exact recorded-page lookup with no filesystem or network behavior."""

    __slots__ = ("_pages",)

    def __init__(self, pages: tuple[ProviderPageV1, ...]) -> None:
        mapping = {
            (item.source_id, item.query_index, item.page): item for item in pages
        }
        if not pages or len(mapping) != len(pages):
            raise ValueError("INVALID_RECORDED_PAGE_SET")
        self._pages = mapping

    def fetch_page(
        self,
        *,
        source_id: str,
        query_index: int,
        query: str,
        page: int,
    ) -> ProviderPageV1:
        del query
        result = self._pages.get((source_id, query_index, page))
        if result is None:
            _fail(ResearchAdapterFailureCodeV1.FIXTURE_UNAVAILABLE)
        return result


@runtime_checkable
class BoundedJsonTransportV1(Protocol):
    def get(self, *, host: str, path: str, headers: Mapping[str, str]) -> bytes: ...


@runtime_checkable
class BoundedHtmlTransportV1(Protocol):
    def get(self, *, host: str, path: str, headers: Mapping[str, str]) -> bytes: ...


@final
class SystemBoundedJsonTransportV1:
    """HTTPS-only transport rejecting proxies and non-public DNS results."""

    __slots__ = ()

    def get(self, *, host: str, path: str, headers: Mapping[str, str]) -> bytes:
        if host not in {RAKUTEN_HOST, YAHOO_HOST} or not path.startswith("/"):
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        if any(name in os.environ for name in _FORBIDDEN_PROXY_ENV):
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        try:
            addresses = socket.getaddrinfo(
                host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
            if not addresses:
                _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
            for address in addresses:
                ip = ipaddress.ip_address(address[4][0])
                if not ip.is_global:
                    _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
            context = ssl.create_default_context()
            connection = http.client.HTTPSConnection(
                host,
                port=443,
                timeout=10,
                context=context,
            )
            connection.request("GET", path, headers=dict(headers))
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "")
            if response.status != 200 or _JSON_MIME.fullmatch(content_type) is None:
                _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
            body = response.read(MAX_RESPONSE_BYTES + 1)
            connection.close()
        except ResearchAdapterFailureV1:
            raise
        except Exception:
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        if len(body) > MAX_RESPONSE_BYTES:
            _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
        return body


@final
class SystemBoundedHtmlTransportV1:
    """Credential-free HTML transport for an adapter-authorized exact URL."""

    __slots__ = ()

    def get(self, *, host: str, path: str, headers: Mapping[str, str]) -> bytes:
        if not host or not path.startswith("/"):
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        if any(name in os.environ for name in _FORBIDDEN_PROXY_ENV):
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        try:
            addresses = socket.getaddrinfo(
                host, 443, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP
            )
            if not addresses or any(
                not ipaddress.ip_address(address[4][0]).is_global
                for address in addresses
            ):
                _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
            connection = http.client.HTTPSConnection(
                host,
                port=443,
                timeout=10,
                context=ssl.create_default_context(),
            )
            connection.request("GET", path, headers=dict(headers))
            response = connection.getresponse()
            content_type = response.getheader("Content-Type", "").split(";", 1)[0]
            if response.status != 200 or content_type.casefold() != "text/html":
                _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
            body = response.read(MAX_HTML_BYTES + 1)
            connection.close()
        except ResearchAdapterFailureV1:
            raise
        except Exception:
            _fail(ResearchAdapterFailureCodeV1.NETWORK_UNSAFE)
        if len(body) > MAX_HTML_BYTES or b"\x00" in body:
            _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
        lowered = body[:4096].lower()
        if b"<html" not in lowered and b"<!doctype html" not in lowered:
            _fail(ResearchAdapterFailureCodeV1.RESPONSE_INVALID)
        return body


def _read_credential(root: Path, relative: Path) -> Mapping[str, object]:
    path = root / relative
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= MAX_CREDENTIAL_BYTES
        ):
            _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNSAFE)
        payload = os.read(descriptor, metadata.st_size + 1)
        if len(payload) != metadata.st_size:
            _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNSAFE)
        document = _json(payload)
    except ResearchAdapterFailureV1:
        raise
    except OSError:
        _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNAVAILABLE)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return document


@final
class LiveProductSearchAdapterV1:
    """Live Rakuten/Yahoo adapter authorized only by exact SourcePolicy rules."""

    __slots__ = ("_clock", "_last_request", "_policy", "_root", "_transport")

    def __init__(
        self,
        *,
        repository_root: Path,
        policy: SourcePolicyV1,
        transport: object,
        clock: Callable[[], datetime],
    ) -> None:
        if (
            not repository_root.is_absolute()
            or not isinstance(transport, BoundedJsonTransportV1)
            or not callable(clock)
        ):
            raise TypeError("INVALID_LIVE_RESEARCH_ADAPTER")
        self._root = repository_root
        self._policy = policy
        self._transport = transport
        self._clock = clock
        self._last_request = 0.0

    def _authorize(self, source_id: str, host: str, path: str) -> int:
        try:
            rule = self._policy.rule_for(source_id)
        except ValueError:
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        if (
            rule.decision is not SourceDecisionV1.ALLOW_AGGREGATE_ONLY
            or rule.acquisition_method is not AcquisitionMethodV1.JSON_API
            or host not in rule.allowed_hosts
            or not any(path.startswith(prefix) for prefix in rule.allowed_path_prefixes)
        ):
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        if rule.terms_checked_by is None or rule.terms_checked_at is None:
            _fail(ResearchAdapterFailureCodeV1.TERMS_RECORD_REQUIRED)
        terms_age = _utc(self._clock()) - _utc(rule.terms_checked_at)
        if terms_age < timedelta(0) or terms_age > timedelta(
            days=self._policy.terms_attestation_days
        ):
            _fail(ResearchAdapterFailureCodeV1.TERMS_RECORD_EXPIRED)
        if rule.credential_ref is None:
            _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNAVAILABLE)
        return rule.minimum_request_interval_ms

    def _pace(self, interval_ms: int) -> None:
        interval = interval_ms / 1000
        remaining = self._last_request + interval - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
        self._last_request = time.monotonic()

    def fetch_page(
        self,
        *,
        source_id: str,
        query_index: int,
        query: str,
        page: int,
    ) -> ProviderPageV1:
        if source_id == RAKUTEN_SOURCE_ID:
            host, base_path = RAKUTEN_HOST, RAKUTEN_PATH
            interval = self._authorize(source_id, host, base_path)
            credential = _read_credential(self._root, RAKUTEN_CREDENTIAL_PATH)
            if set(credential) != {
                "schema_version",
                "profile",
                "application_id",
                "access_key",
                "affiliate_id",
            }:
                _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNSAFE)
            application_id = _text(credential["application_id"], maximum=256)
            request_header_value = _text(
                credential["access_key"], maximum=256
            )
            query_string = urlencode(
                {
                    "applicationId": application_id,
                    "keyword": query,
                    "hits": "30",
                    "page": str(page),
                    "format": "json",
                    "formatVersion": "2",
                    "elements": (
                        "itemCode,itemName,itemUrl,itemPrice,reviewAverage,"
                        "reviewCount,shopCode,shopName,jan"
                    ),
                }
            )
            headers: dict[str, str] = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": host,
                "User-Agent": USER_AGENT,
            }
            headers["accessKey"] = request_header_value
            secrets: tuple[bytes, ...] = (
                application_id.encode(),
                request_header_value.encode(),
            )
            parser = parse_rakuten_page_v1
        elif source_id == YAHOO_SOURCE_ID:
            host, base_path = YAHOO_HOST, YAHOO_PATH
            interval = self._authorize(source_id, host, base_path)
            credential = _read_credential(self._root, YAHOO_CREDENTIAL_PATH)
            if set(credential) != {"schema_version", "profile", "client_id"}:
                _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_UNSAFE)
            client_id = _text(credential["client_id"], maximum=256)
            query_string = urlencode(
                {
                    "appid": client_id,
                    "query": query,
                    "results": "100",
                    "start": str((page - 1) * 100 + 1),
                }
            )
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": host,
                "User-Agent": USER_AGENT,
            }
            secrets = (client_id.encode(),)
            parser = parse_yahoo_page_v1
        else:
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        self._pace(interval)
        raw = self._transport.get(
            host=host,
            path=f"{base_path}?{query_string}",
            headers=headers,
        )
        if any(secret and secret in raw for secret in secrets):
            _fail(ResearchAdapterFailureCodeV1.CREDENTIAL_REFLECTION)
        return parser(
            raw,
            query_index=query_index,
            query=query,
            page=page,
            observed_at=_utc(self._clock()),
        )


@final
class OfficialPageCaptureAdapterV1:
    """Capture one exact allowlisted page and retain only bounded metadata."""

    __slots__ = ("_clock", "_policy", "_transport")

    def __init__(
        self,
        *,
        policy: SourcePolicyV1,
        transport: object,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(transport, BoundedHtmlTransportV1) or not callable(clock):
            raise TypeError("INVALID_OFFICIAL_PAGE_ADAPTER")
        self._policy = policy
        self._transport = transport
        self._clock = clock

    def capture(
        self,
        *,
        source_id: str,
        exact_url: str,
        artifact_id: str,
    ) -> OfficialPageEvidenceV1:
        captured_at = _utc(self._clock())
        try:
            rule = self._policy.rule_for(source_id)
        except ValueError:
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        if (
            rule.decision is not SourceDecisionV1.ALLOW_STRUCTURED_FIELDS
            or rule.acquisition_method is not AcquisitionMethodV1.EXACT_URL_HTML
            or exact_url not in rule.allowed_exact_urls
            or rule.terms_checked_by is None
            or rule.terms_checked_at is None
        ):
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        assert rule.terms_checked_at is not None
        terms_age = captured_at - _utc(rule.terms_checked_at)
        if terms_age < timedelta(0) or terms_age > timedelta(
            days=self._policy.terms_attestation_days
        ):
            _fail(ResearchAdapterFailureCodeV1.TERMS_RECORD_EXPIRED)
        try:
            parsed = urlsplit(exact_url)
        except ValueError:
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        if (
            parsed.scheme != "https"
            or parsed.hostname is None
            or parsed.hostname not in rule.allowed_hosts
            or parsed.query
            or parsed.fragment
            or not any(
                parsed.path.startswith(prefix)
                for prefix in rule.allowed_path_prefixes
            )
        ):
            _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)
        body = self._transport.get(
            host=parsed.hostname,
            path=parsed.path,
            headers={
                "Accept": "text/html",
                "Accept-Encoding": "identity",
                "Connection": "close",
                "Host": parsed.hostname,
                "User-Agent": USER_AGENT,
            },
        )
        return OfficialPageEvidenceV1(
            artifact_id=artifact_id,
            source_id=source_id,
            exact_url=exact_url,
            body_sha256=hashlib.sha256(body).hexdigest(),
            byte_size=len(body),
            captured_at=captured_at,
        )


@final
class DisabledReviewThemeAdapterV1:
    """Initial fail-closed body adapter; no raw body can enter the process."""

    __slots__ = ()

    def derive_themes(self, *, product_id: str) -> ReviewThemeSetV1:
        del product_id
        _fail(ResearchAdapterFailureCodeV1.POLICY_BLOCKED)


@final
class DisabledSocialSignalAdapterV1:
    __slots__ = ("_clock",)

    def __init__(self, *, clock: Callable[[], datetime]) -> None:
        if not callable(clock):
            raise TypeError("INVALID_SOCIAL_ADAPTER")
        self._clock = clock

    def discover(self) -> SocialSignalSetV1:
        return SocialSignalSetV1(
            artifact_id="social:disabled-v1",
            checked_at=_utc(self._clock()),
        )


@final
class LocalResearchArtifactStoreV1:
    """Private, atomic local store for canonical ObjectArtifact payloads."""

    __slots__ = ("_root",)

    def __init__(self, root: Path) -> None:
        if not root.is_absolute():
            raise TypeError("ABSOLUTE_ARTIFACT_ROOT_REQUIRED")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or not root.is_dir():
            _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
        os.chmod(root, 0o700)
        self._root = root

    def _path(self, reference: ArtifactRefV1) -> Path:
        safe_name = hashlib.sha256(reference.artifact_id.encode()).hexdigest()
        return self._root / f"{safe_name}.json"

    def put(self, artifact: StrictContractV1) -> ArtifactRefV1:
        reference = artifact_ref(artifact)
        payload = canonical_json_bytes(artifact) + b"\n"
        target = self._path(reference)
        if target.exists():
            if target.is_symlink() or target.read_bytes() != payload:
                _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
            return reference
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._root,
            prefix=".research-",
            suffix=".tmp",
        )
        temporary = Path(temporary_name)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, payload)
            os.fsync(descriptor)
            os.close(descriptor)
            descriptor = -1
            os.replace(temporary, target)
            os.chmod(target, 0o600)
        except Exception:
            _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary.unlink(missing_ok=True)
        return reference

    def get(self, reference: ArtifactRefV1) -> bytes:
        target = self._path(reference)
        try:
            metadata = target.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
            payload = target.read_bytes()
        except ResearchAdapterFailureV1:
            raise
        except OSError:
            _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
        canonical = payload.removesuffix(b"\n")
        if (
            len(canonical) != reference.byte_size
            or hashlib.sha256(canonical).hexdigest() != reference.content_sha256
        ):
            _fail(ResearchAdapterFailureCodeV1.STORE_UNSAFE)
        return canonical


__all__ = [
    "BoundedJsonTransportV1",
    "BoundedHtmlTransportV1",
    "DisabledReviewThemeAdapterV1",
    "DisabledSocialSignalAdapterV1",
    "LiveProductSearchAdapterV1",
    "LocalResearchArtifactStoreV1",
    "OfficialPageCaptureAdapterV1",
    "RAKUTEN_SOURCE_ID",
    "RecordedProductSearchAdapterV1",
    "ResearchAdapterFailureCodeV1",
    "ResearchAdapterFailureV1",
    "SystemBoundedJsonTransportV1",
    "SystemBoundedHtmlTransportV1",
    "YAHOO_SOURCE_ID",
    "parse_rakuten_page_v1",
    "parse_yahoo_page_v1",
]
