"""Closed, credential-free official-source capture for the ST-1704 pilot.

This module can issue only one read-only HTTPS ``GET`` to an exact URL loaded
from the tracked ST-1704 source registry.  It has no caller-selected URL,
headers, output path, credentials, WordPress capability, or publication
authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import StrEnum
import fcntl
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
from typing import Final, NoReturn, Protocol, cast, final, runtime_checkable
from urllib.parse import SplitResult, urlsplit

from raos.adapters.self_hosted_editorial_pilot_json import (
    MAX_SOURCE_BODY_BYTES,
    OWNER_DIRECTORY,
    SOURCE_DIRECTORY,
    source_body_relative_path,
    source_evidence_relative_path,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    PILOT_ARTICLE_IDENTITIES,
    PILOT_SOURCE_CAPTURE_SCHEMA,
    OfficialSourceCaptureEvidence,
    bytes_sha256,
    canonical_json_bytes,
    canonical_sha256,
)


SOURCE_REGISTRY_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/source-registry.v1.json"
)
LOCATOR_CONTRACT_RELATIVE_PATH: Final = Path(
    "changes/st-1704/self-hosted-editorial-pilot-v1/sources/"
    "source-locator-contract.v1.json"
)
LOCATOR_CONTRACT_SCHEMA: Final = "SELF_HOSTED_EDITORIAL_SOURCE_LOCATOR_CONTRACT_V1"
RAW_CAPTURE_SCHEMA: Final = "RAOS_ST1704_OFFICIAL_SOURCE_RAW_CAPTURE_V1"
PUBLICATION_AUTHORITY: Final = "NONE"
CAPTURE_USER_AGENT: Final = "RAOS-ST-1704-official-source-capture/1"
CAPTURE_ACCEPT: Final = "text/html"
CONNECT_TIMEOUT_SECONDS: Final = 10
READ_TIMEOUT_SECONDS: Final = 20
MAX_CONTRACT_BYTES: Final = 1_000_000
MAX_REGISTRY_BYTES: Final = 4_000_000
PRIVATE_DIRECTORY_MODE: Final = 0o700
PRIVATE_FILE_MODE: Final = 0o600
CAPTURE_LOCK_FILE: Final = "official-source-capture.lock"

_SOURCE_REF = re.compile(r"SRC-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z", re.ASCII)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CONTENT_LENGTH = re.compile(r"0|[1-9][0-9]*\Z", re.ASCII)
_CONTENT_TYPE = re.compile(
    r'text/html(?:\s*;\s*charset="?([A-Za-z0-9._-]+)"?)?\Z',
    re.ASCII | re.IGNORECASE,
)
_ARTICLE_IDS: Final = frozenset(
    identity.article_id for identity in PILOT_ARTICLE_IDENTITIES
)
_REGISTRY_ROOT_KEYS: Final = frozenset(
    {
        "affiliate_resources",
        "generated_on",
        "policy_sources",
        "publication_authority",
        "schema",
        "slice_id",
        "source_packets",
        "source_policy",
        "sources",
        "story_id",
        "target_origin",
    }
)
_REGISTRY_SOURCE_KEYS: Final = frozenset(
    {
        "authority",
        "capture_status",
        "immutable_capture_sha256",
        "retrieved_on",
        "review_body_excluded_from_claim_evidence",
        "source_ref",
        "source_type",
        "title",
        "url",
    }
)
_REGISTRY_SOURCE_POLICY: Final = {
    "allowed_authority": "OFFICIAL_PRIMARY_SOURCE_ONLY",
    "competitor_sources_as_evidence": False,
    "first_hand_experience_claims": False,
    "immutable_capture_hash_algorithm": "SHA256_CANONICAL_UTF8_JSON_V1",
    "immutable_capture_hash_material": (
        "source metadata plus source-bound claim records; sorted object keys; "
        "compact separators; UTF-8; review bodies excluded from claim-evidence "
        "selection"
    ),
    "immutable_capture_required_for_publication": True,
    "immutable_capture_schema": "STRUCTURED_SOURCE_FACT_PACKET_V1",
    "missing_fact_behavior": "OMIT_OR_MARK_UNKNOWN",
    "review_body_as_evidence": False,
    "source_packet_schema": "STRUCTURED_ARTICLE_SOURCE_PACKET_V1",
}
_LOCATOR_ROOT_KEYS: Final = frozenset(
    {
        "generated_on",
        "locator_policy",
        "publication_authority",
        "schema",
        "slice_id",
        "source_registry_sha256",
        "sources",
        "story_id",
    }
)
_LOCATOR_POLICY: Final = {
    "claim_statement_source": "TRACKED_SOURCE_PACKET_EXACT",
    "fragment_source": "TRACKED_REVIEWED_EXACT_UTF8_FRAGMENT",
    "fragment_match": "RAW_BODY_EXACTLY_ONCE",
    "pending_behavior": "BODY_CAPTURED_LOCATORS_PENDING_PREPARE_BLOCKED",
    "review_body_as_evidence": False,
    "review_body_locator_allowed": False,
}
_LOCATOR_SOURCE_KEYS: Final = frozenset(
    {"charset", "locator_status", "locators", "source_ref"}
)
_LOCATOR_KEYS: Final = frozenset({"claim_id", "exact_utf8_fragments"})
_READY = "READY"
_PENDING = "LOCATORS_PENDING"


class OfficialSourceCaptureFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTRACT_INVALID = "CONTRACT_INVALID"
    ARTICLE_NOT_ALLOWLISTED = "ARTICLE_NOT_ALLOWLISTED"
    SOURCE_NOT_ALLOWLISTED = "SOURCE_NOT_ALLOWLISTED"
    LOCATORS_PENDING = "LOCATORS_PENDING"
    NETWORK_ENVIRONMENT_UNSAFE = "NETWORK_ENVIRONMENT_UNSAFE"
    DNS_FAILED = "DNS_FAILED"
    DNS_ADDRESS_REJECTED = "DNS_ADDRESS_REJECTED"
    TLS_CONTEXT_INVALID = "TLS_CONTEXT_INVALID"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    REQUEST_AMBIGUOUS = "REQUEST_AMBIGUOUS"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    BODY_TOO_LARGE = "BODY_TOO_LARGE"
    MIME_INVALID = "MIME_INVALID"
    HTML_INVALID = "HTML_INVALID"
    LOCATOR_MISMATCH = "LOCATOR_MISMATCH"
    STORE_UNSAFE = "STORE_UNSAFE"
    STORE_CONFLICT = "STORE_CONFLICT"


class OfficialSourceCaptureFailure(RuntimeError):
    """Sanitized failure that never includes source or response material."""

    __slots__ = ("_code",)

    def __init__(self, code: OfficialSourceCaptureFailureCode) -> None:
        if type(code) is not OfficialSourceCaptureFailureCode:
            raise TypeError("invalid official-source capture failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> OfficialSourceCaptureFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"OfficialSourceCaptureFailure(code={self.code.value})"


def _fail(
    code: OfficialSourceCaptureFailureCode = (
        OfficialSourceCaptureFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise OfficialSourceCaptureFailure(code) from None


def _pairs(pairs: list[tuple[object, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    del value
    _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)


def _strict_json(raw: bytes, *, maximum: int) -> object:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= maximum
        or raw.startswith(b"\xef\xbb\xbf")
    ):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except OfficialSourceCaptureFailure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError, RecursionError:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return value


def _exact(value: Mapping[str, object], keys: frozenset[str]) -> None:
    if frozenset(value) != keys:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)


def _absolute_repository_root(value: object) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        _fail()
    return value


def _read_tracked_file(repository_root: Path, relative: Path, maximum: int) -> bytes:
    target = _absolute_repository_root(repository_root) / relative
    descriptor = -1
    try:
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        return b"".join(chunks)
    except OfficialSourceCaptureFailure:
        raise
    except OSError:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _date(value: object) -> date:
    raw = _text(value, maximum=10)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    if parsed.isoformat() != raw:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return parsed


def _source_url(value: object) -> tuple[str, SplitResult]:
    raw = _text(value)
    if (
        not raw.isascii()
        or any(character.isspace() or ord(character) < 0x21 for character in raw)
        or any(character in raw for character in "\\\"'<>[]")
    ):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    if (
        parsed.scheme != "https"
        or parsed.hostname is None
        or parsed.hostname != parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
        or parsed.hostname.endswith(".")
    ):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return raw, parsed


@dataclass(frozen=True, slots=True)
class SourceLocator:
    claim_id: str
    claim_statement_sha256: str
    exact_utf8_fragments: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not _text(self.claim_id, maximum=300)
            or _SHA256.fullmatch(self.claim_statement_sha256) is None
            or type(self.exact_utf8_fragments) is not tuple
            or not self.exact_utf8_fragments
        ):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        observed: set[str] = set()
        for raw_fragment in self.exact_utf8_fragments:
            fragment = _text(raw_fragment, maximum=2000)
            try:
                fragment_bytes = fragment.encode("utf-8", errors="strict")
            except UnicodeError:
                _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
            if not 1 <= len(fragment_bytes) <= 2000 or fragment in observed:
                _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
            observed.add(fragment)


@dataclass(frozen=True, slots=True)
class SourceCaptureTarget:
    source_ref: str
    url: str
    host: str
    path: str
    observed_on: date
    charset: str | None
    locator_status: str
    locators: tuple[SourceLocator, ...]

    def __post_init__(self) -> None:
        raw, parsed = _source_url(self.url)
        if (
            _SOURCE_REF.fullmatch(self.source_ref) is None
            or raw != self.url
            or parsed.hostname != self.host
            or parsed.path != self.path
            or self.charset not in {None, "utf-8", "euc-jp"}
            or self.locator_status not in {_READY, _PENDING}
            or (self.locator_status == _READY and not self.locators)
            or (self.locator_status == _PENDING and self.locators)
        ):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)


@dataclass(frozen=True, slots=True)
class SourceCapturePlan:
    targets: tuple[SourceCaptureTarget, ...]
    article_sources: tuple[tuple[str, tuple[str, ...]], ...]

    def target(self, source_ref: str) -> SourceCaptureTarget:
        matches = [value for value in self.targets if value.source_ref == source_ref]
        if len(matches) != 1:
            _fail(OfficialSourceCaptureFailureCode.SOURCE_NOT_ALLOWLISTED)
        return matches[0]

    def for_article(self, article_id: str) -> tuple[SourceCaptureTarget, ...]:
        if article_id not in _ARTICLE_IDS:
            _fail(OfficialSourceCaptureFailureCode.ARTICLE_NOT_ALLOWLISTED)
        matches = [
            refs for candidate, refs in self.article_sources if candidate == article_id
        ]
        if len(matches) != 1:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        return tuple(self.target(source_ref) for source_ref in matches[0])


def _claim_bindings(
    registry: Mapping[str, object], source_refs: frozenset[str]
) -> tuple[dict[str, dict[str, str]], tuple[tuple[str, tuple[str, ...]], ...]]:
    claims: dict[str, dict[str, str]] = {source_ref: {} for source_ref in source_refs}
    articles: list[tuple[str, tuple[str, ...]]] = []
    observed_articles: set[str] = set()
    for raw_packet in _list(registry["source_packets"]):
        packet = _mapping(raw_packet)
        article_id = _text(packet.get("article_id"), maximum=300)
        if article_id not in _ARTICLE_IDS or article_id in observed_articles:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        observed_articles.add(article_id)
        refs = tuple(
            _text(value, maximum=300) for value in _list(packet.get("source_refs"))
        )
        if (
            not refs
            or len(refs) != len(set(refs))
            or any(ref not in claims for ref in refs)
        ):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        for raw_claim in _list(packet.get("claims")):
            claim = _mapping(raw_claim)
            claim_id = _text(claim.get("claim_id"), maximum=300)
            statement = _text(claim.get("statement"), maximum=4000)
            for source_ref_value in _list(claim.get("evidence_refs")):
                source_ref = _text(source_ref_value, maximum=300)
                if source_ref not in refs or claim_id in claims[source_ref]:
                    _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
                claims[source_ref][claim_id] = bytes_sha256(statement.encode("utf-8"))
        articles.append((article_id, refs))
    if observed_articles != set(_ARTICLE_IDS):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    return claims, tuple(articles)


def load_source_capture_plan(repository_root: Path) -> SourceCapturePlan:
    """Load and cross-bind the tracked registry and reviewed locator contract."""

    registry_raw = _read_tracked_file(
        repository_root, SOURCE_REGISTRY_RELATIVE_PATH, MAX_REGISTRY_BYTES
    )
    contract_raw = _read_tracked_file(
        repository_root, LOCATOR_CONTRACT_RELATIVE_PATH, MAX_CONTRACT_BYTES
    )
    registry = _mapping(_strict_json(registry_raw, maximum=MAX_REGISTRY_BYTES))
    contract = _mapping(_strict_json(contract_raw, maximum=MAX_CONTRACT_BYTES))
    _exact(registry, _REGISTRY_ROOT_KEYS)
    _exact(contract, _LOCATOR_ROOT_KEYS)
    if (
        registry["schema"] != "SELF_HOSTED_EDITORIAL_SOURCE_REGISTRY_V1"
        or registry["story_id"] != "ST-1704"
        or registry["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or registry["publication_authority"] != PUBLICATION_AUTHORITY
        or contract["schema"] != LOCATOR_CONTRACT_SCHEMA
        or contract["story_id"] != "ST-1704"
        or contract["slice_id"] != "SELF_HOSTED_EDITORIAL_PILOT_V1"
        or contract["publication_authority"] != PUBLICATION_AUTHORITY
        or contract["source_registry_sha256"] != canonical_sha256(registry)
        or contract["locator_policy"] != _LOCATOR_POLICY
        or registry["source_policy"] != _REGISTRY_SOURCE_POLICY
    ):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    registry_sources: dict[str, Mapping[str, object]] = {}
    product_refs: list[str] = []
    policy_refs: list[str] = []
    for collection_name, output in (
        ("sources", product_refs),
        ("policy_sources", policy_refs),
    ):
        for raw_source in _list(registry[collection_name]):
            source = _mapping(raw_source)
            _exact(source, _REGISTRY_SOURCE_KEYS)
            source_ref = _text(source["source_ref"], maximum=300)
            if (
                _SOURCE_REF.fullmatch(source_ref) is None
                or source_ref in registry_sources
                or source["review_body_excluded_from_claim_evidence"] is not True
            ):
                _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
            _source_url(source["url"])
            _date(source["retrieved_on"])
            registry_sources[source_ref] = source
            output.append(source_ref)
    if len(product_refs) != 19 or len(policy_refs) != 3:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    claims, article_sources = _claim_bindings(registry, frozenset(product_refs))
    for source_ref in policy_refs:
        title = _text(registry_sources[source_ref]["title"], maximum=500)
        claims[source_ref] = {
            "POLICY-SOURCE-STATEMENT": bytes_sha256(title.encode("utf-8"))
        }
    contract_sources = _list(contract["sources"])
    if len(contract_sources) != len(registry_sources):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    targets: list[SourceCaptureTarget] = []
    observed: set[str] = set()
    for raw_contract_source in contract_sources:
        locator_source = _mapping(raw_contract_source)
        _exact(locator_source, _LOCATOR_SOURCE_KEYS)
        source_ref = _text(locator_source["source_ref"], maximum=300)
        target_source = registry_sources.get(source_ref)
        if target_source is None or source_ref in observed:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        observed.add(source_ref)
        charset_value = locator_source["charset"]
        if charset_value is not None and type(charset_value) is not str:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        locator_status = _text(locator_source["locator_status"], maximum=40)
        locators: list[SourceLocator] = []
        observed_claims: set[str] = set()
        for raw_locator in _list(locator_source["locators"]):
            locator = _mapping(raw_locator)
            _exact(locator, _LOCATOR_KEYS)
            claim_id = _text(locator["claim_id"], maximum=300)
            raw_fragments = _list(locator["exact_utf8_fragments"])
            fragments = tuple(
                _text(fragment, maximum=2000) for fragment in raw_fragments
            )
            statement_sha256 = claims[source_ref].get(claim_id)
            if (
                statement_sha256 is None
                or claim_id in observed_claims
                or not fragments
                or len(fragments) != len(set(fragments))
            ):
                _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
            observed_claims.add(claim_id)
            locators.append(SourceLocator(claim_id, statement_sha256, fragments))
        if locator_status == _READY and observed_claims != set(claims[source_ref]):
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        if locator_status == _PENDING and observed_claims:
            _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
        url, parsed = _source_url(target_source["url"])
        targets.append(
            SourceCaptureTarget(
                source_ref=source_ref,
                url=url,
                host=cast(str, parsed.hostname),
                path=parsed.path,
                observed_on=_date(target_source["retrieved_on"]),
                charset=charset_value,
                locator_status=locator_status,
                locators=tuple(locators),
            )
        )
    if observed != set(registry_sources):
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    policy_tuple = tuple(policy_refs)
    article_with_policy = tuple(
        (article_id, (*refs, *policy_tuple)) for article_id, refs in article_sources
    )
    return SourceCapturePlan(tuple(targets), article_with_policy)


def require_clean_capture_environment(
    environment: Mapping[str, str] | None = None,
) -> None:
    values = os.environ if environment is None else environment
    forbidden = {
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
    if any(key in values for key in forbidden):
        _fail(OfficialSourceCaptureFailureCode.NETWORK_ENVIRONMENT_UNSAFE)


@runtime_checkable
class OfficialSourceHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def getheaders(self) -> list[tuple[str, str]]: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class OfficialSourceHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(self, method: str, path: str, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> OfficialSourceHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class OfficialSourceHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> OfficialSourceHttpsConnection: ...


def _require_connection_factory(
    value: object,
) -> OfficialSourceHttpsConnectionFactory:
    if not isinstance(value, OfficialSourceHttpsConnectionFactory):
        _fail()
    return value


@dataclass(frozen=True, slots=True)
class _ResolvedAddress:
    family: int
    socket_type: int
    protocol: int
    socket_address: tuple[str, int] | tuple[str, int, int, int]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


def _public_ip(
    value: object, *, family: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    if (
        (family == socket.AF_INET and type(address) is not ipaddress.IPv4Address)
        or (family == socket.AF_INET6 and type(address) is not ipaddress.IPv6Address)
        or not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or getattr(address, "is_site_local", False)
        or (
            type(address) is ipaddress.IPv6Address
            and (address.ipv4_mapped is not None or address.scope_id is not None)
        )
    ):
        _fail(OfficialSourceCaptureFailureCode.DNS_ADDRESS_REJECTED)
    return address


def _validated_socket_address(
    value: object, *, family: int
) -> tuple[object, object] | tuple[object, object, object, object]:
    if type(value) is not tuple:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    values = cast(tuple[object, ...], value)
    result: tuple[object, object] | tuple[object, object, object, object]
    if family == socket.AF_INET:
        if len(values) != 2:
            _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
        result = (values[0], values[1])
    elif family == socket.AF_INET6:
        if len(values) != 4 or values[2] != 0 or values[3] != 0:
            _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
        result = (values[0], values[1], values[2], values[3])
    else:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    if type(result[1]) is not int or result[1] != 443:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    return result


def _resolve_public_addresses(host: str) -> tuple[_ResolvedAddress, ...]:
    try:
        rows = socket.getaddrinfo(
            host,
            443,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
            flags=0,
        )
    except OSError, UnicodeError, ValueError, TypeError:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    if type(rows) is not list or not rows or len(rows) > 64:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    results: list[_ResolvedAddress] = []
    for row in rows:
        if type(row) is not tuple or len(row) != 5 or type(row[4]) is not tuple:
            _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
        family, socket_type, protocol, canonical_name, raw_address = row
        if (
            family not in {socket.AF_INET, socket.AF_INET6}
            or socket_type != socket.SOCK_STREAM
            or protocol != socket.IPPROTO_TCP
            or type(canonical_name) is not str
        ):
            _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
        values = _validated_socket_address(raw_address, family=cast(int, family))
        ip = _public_ip(values[0], family=cast(int, family))
        address: tuple[str, int] | tuple[str, int, int, int]
        if family == socket.AF_INET:
            address = (str(ip), 443)
        else:
            address = (str(ip), 443, 0, 0)
        candidate = _ResolvedAddress(
            cast(int, family), cast(int, socket_type), protocol, address, ip
        )
        if candidate not in results:
            results.append(candidate)
    if not results:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    return tuple(results)


def _require_peer(candidate: _ResolvedAddress, peer: object) -> None:
    if type(peer) is not tuple:
        _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
    values = cast(tuple[object, ...], peer)
    if (
        len(values) not in {2, 4}
        or type(values[1]) is not int
        or values[1] != 443
        or (candidate.family == socket.AF_INET and len(values) != 2)
        or (candidate.family == socket.AF_INET6 and len(values) != 4)
    ):
        _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
    if _public_ip(values[0], family=candidate.family) != candidate.ip:
        _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)


@dataclass(slots=True)
class _PinnedConnector:
    host: str
    candidate: _ResolvedAddress
    attempted: bool = False

    def __call__(
        self,
        address: tuple[str, int],
        timeout: object,
        source_address: tuple[str, int] | None,
    ) -> socket.socket:
        if (
            self.attempted
            or address != (self.host, 443)
            or timeout != CONNECT_TIMEOUT_SECONDS
            or source_address is not None
        ):
            _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
        self.attempted = True
        connection = socket.socket(
            self.candidate.family,
            self.candidate.socket_type,
            self.candidate.protocol,
        )
        try:
            connection.settimeout(CONNECT_TIMEOUT_SECONDS)
            connection.connect(self.candidate.socket_address)
            _require_peer(self.candidate, connection.getpeername())
            return connection
        except BaseException:
            connection.close()
            raise


@final
class _SystemConnection:
    __slots__ = ("_candidate", "_connection")

    def __init__(
        self, connection: http.client.HTTPSConnection, candidate: _ResolvedAddress
    ) -> None:
        self._connection = connection
        self._candidate = candidate

    def connect(self) -> None:
        if getattr(self._connection, "_tunnel_host", None) is not None:
            _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
        self._connection.connect()
        if self._connection.sock is None:
            _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
        _require_peer(self._candidate, self._connection.sock.getpeername())

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None or seconds != READ_TIMEOUT_SECONDS:
            _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
        self._connection.sock.settimeout(seconds)

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self._connection.request(method, path, body=None, headers=headers)

    def getresponse(self) -> OfficialSourceHttpsResponse:
        return cast(OfficialSourceHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class _SystemOfficialSourceHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> OfficialSourceHttpsConnection:
        if (
            type(host) is not str
            or port != 443
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(OfficialSourceCaptureFailureCode.TLS_CONTEXT_INVALID)
        candidate = _resolve_public_addresses(host)[0]
        connection = http.client.HTTPSConnection(
            host=host,
            port=443,
            timeout=CONNECT_TIMEOUT_SECONDS,
            context=tls_context,
        )
        setattr(connection, "_create_connection", _PinnedConnector(host, candidate))
        return _SystemConnection(connection, candidate)


def _response_headers(response: OfficialSourceHttpsResponse) -> dict[str, str]:
    result: dict[str, str] = {}
    relevant = {
        "content-encoding",
        "content-length",
        "content-type",
        "location",
        "transfer-encoding",
    }
    try:
        rows = response.getheaders()
    except BaseException:
        _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
    if type(rows) is not list:
        _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
    for key, value in rows:
        if type(key) is not str or type(value) is not str:
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
        normalized = key.casefold()
        if normalized not in relevant:
            continue
        if normalized in result:
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
        result[normalized] = value
    return result


def _bounded_body(
    response: OfficialSourceHttpsResponse, headers: Mapping[str, str]
) -> bytes:
    content_length = headers.get("content-length")
    transfer_encoding = headers.get("transfer-encoding")
    if content_length is not None:
        if _CONTENT_LENGTH.fullmatch(content_length) is None:
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
        expected = int(content_length)
        if expected > MAX_SOURCE_BODY_BYTES:
            _fail(OfficialSourceCaptureFailureCode.BODY_TOO_LARGE)
        if transfer_encoding is not None:
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
    else:
        expected = None
        if transfer_encoding is not None and transfer_encoding.casefold() != "chunked":
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
    chunks: list[bytes] = []
    observed = 0
    while True:
        try:
            chunk = response.read(min(65_536, MAX_SOURCE_BODY_BYTES + 1 - observed))
        except BaseException:
            _fail(OfficialSourceCaptureFailureCode.REQUEST_AMBIGUOUS)
        if type(chunk) is not bytes:
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
        if not chunk:
            break
        chunks.append(chunk)
        observed += len(chunk)
        if observed > MAX_SOURCE_BODY_BYTES:
            _fail(OfficialSourceCaptureFailureCode.BODY_TOO_LARGE)
    if expected is not None and observed != expected:
        _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
    if observed < 1:
        _fail(OfficialSourceCaptureFailureCode.HTML_INVALID)
    return b"".join(chunks)


def _mime(headers: Mapping[str, str], expected_charset: str | None) -> str:
    value = headers.get("content-type")
    if type(value) is not str:
        _fail(OfficialSourceCaptureFailureCode.MIME_INVALID)
    match = _CONTENT_TYPE.fullmatch(value)
    if match is None:
        _fail(OfficialSourceCaptureFailureCode.MIME_INVALID)
    charset = match.group(1)
    normalized = None if charset is None else charset.casefold().replace("_", "-")
    if normalized != expected_charset:
        _fail(OfficialSourceCaptureFailureCode.MIME_INVALID)
    return "text/html"


def _validate_html(body: bytes, *, charset: str | None) -> None:
    stripped = body.strip(b"\t\n\r ")
    prefix = stripped[:4096].lower()
    if (
        not (prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"))
        or b"<html" not in prefix
        or not stripped.lower().endswith(b"</html>")
    ):
        _fail(OfficialSourceCaptureFailureCode.HTML_INVALID)
    codec = "utf-8" if charset in {None, "utf-8"} else "euc_jp"
    try:
        body.decode(codec, errors="strict")
    except UnicodeError:
        _fail(OfficialSourceCaptureFailureCode.HTML_INVALID)


@dataclass(frozen=True, slots=True)
class FetchedSource:
    target: SourceCaptureTarget
    retrieved_at: str
    content_type: str
    body: bytes


def _clock_value(clock: Callable[[], datetime]) -> datetime:
    try:
        value = clock()
    except BaseException:
        _fail(OfficialSourceCaptureFailureCode.INVALID_ARGUMENT)
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        _fail(OfficialSourceCaptureFailureCode.INVALID_ARGUMENT)
    return value.astimezone(timezone.utc).replace(microsecond=0)


def _fetch_source(
    target: SourceCaptureTarget,
    *,
    connection_factory: OfficialSourceHttpsConnectionFactory,
    clock: Callable[[], datetime],
    environment: Mapping[str, str] | None = None,
) -> FetchedSource:
    """Fetch one closed target exactly once without redirects or credentials."""

    if type(target) is not SourceCaptureTarget:
        _fail()
    connection_factory = _require_connection_factory(connection_factory)
    require_clean_capture_environment(environment)
    captured_at = _clock_value(clock)
    if captured_at.date() < target.observed_on:
        _fail(OfficialSourceCaptureFailureCode.CONTRACT_INVALID)
    try:
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except OSError, ssl.SSLError, ValueError:
        _fail(OfficialSourceCaptureFailureCode.TLS_CONTEXT_INVALID)
    connection: OfficialSourceHttpsConnection | None = None
    request_started = False
    try:
        connection = connection_factory.open(
            host=target.host,
            port=443,
            connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            tls_context=context,
        )
        connection.connect()
        connection.set_read_timeout(READ_TIMEOUT_SECONDS)
        request_started = True
        headers = {
            "Accept": CAPTURE_ACCEPT,
            "Accept-Encoding": "identity",
            "Connection": "close",
            "Host": target.host,
            "User-Agent": CAPTURE_USER_AGENT,
        }
        connection.request("GET", target.path, headers)
        response = connection.getresponse()
        response_headers = _response_headers(response)
        if (
            type(response.status) is not int
            or response.status != 200
            or "location" in response_headers
            or response_headers.get("content-encoding") not in {None, "identity"}
        ):
            _fail(OfficialSourceCaptureFailureCode.RESPONSE_INVALID)
        content_type = _mime(response_headers, target.charset)
        body = _bounded_body(response, response_headers)
        _validate_html(body, charset=target.charset)
    except OfficialSourceCaptureFailure:
        raise
    except socket.gaierror:
        _fail(OfficialSourceCaptureFailureCode.DNS_FAILED)
    except ssl.SSLError:
        _fail(OfficialSourceCaptureFailureCode.CONNECTION_FAILED)
    except TimeoutError, socket.timeout:
        _fail(
            OfficialSourceCaptureFailureCode.REQUEST_AMBIGUOUS
            if request_started
            else OfficialSourceCaptureFailureCode.CONNECTION_FAILED
        )
    except http.client.HTTPException, OSError:
        _fail(
            OfficialSourceCaptureFailureCode.REQUEST_AMBIGUOUS
            if request_started
            else OfficialSourceCaptureFailureCode.CONNECTION_FAILED
        )
    except BaseException:
        _fail(
            OfficialSourceCaptureFailureCode.REQUEST_AMBIGUOUS
            if request_started
            else OfficialSourceCaptureFailureCode.CONNECTION_FAILED
        )
    finally:
        if connection is not None:
            try:
                connection.close()
            except BaseException:
                pass
    return FetchedSource(
        target=target,
        retrieved_at=captured_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        content_type=content_type,
        body=body,
    )


def _safe_directory(path: Path, *, create: bool) -> None:
    try:
        if create:
            try:
                path.mkdir(mode=PRIVATE_DIRECTORY_MODE)
            except FileExistsError:
                pass
        observed = path.lstat()
    except OSError:
        _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or stat.S_ISLNK(observed.st_mode)
        or observed.st_uid != os.getuid()
        or stat.S_IMODE(observed.st_mode) != PRIVATE_DIRECTORY_MODE
    ):
        _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)


def _source_directory(repository_root: Path) -> Path:
    validated_root = _absolute_repository_root(repository_root)
    secrets = validated_root / ".secrets"
    owner = secrets / OWNER_DIRECTORY
    sources = owner / SOURCE_DIRECTORY
    _safe_directory(secrets, create=True)
    _safe_directory(owner, create=True)
    _safe_directory(sources, create=True)
    return sources


def _read_private(path: Path, *, maximum: int) -> bytes | None:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return None
    except OSError:
        _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != PRIVATE_FILE_MODE
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _replace_private(directory: Path, name: str, payload: bytes) -> None:
    """Atomically refresh one owner-private artifact.

    The caller holds the capture lock.  A body is replaced before its metadata;
    the existing reader hashes the body and double-reads metadata, so a crash or
    concurrent observation can only yield the old generation, the new
    generation, or a fail-closed mismatch.
    """

    if "/" in name or name in {"", ".", ".."}:
        _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
    target = directory / name
    existing = _read_private(target, maximum=MAX_SOURCE_BODY_BYTES)
    if existing == payload:
        return
    descriptor = -1
    directory_fd = -1
    temporary = f".{name}.{os.getpid()}.{os.urandom(16).hex()}.tmp"
    try:
        descriptor = os.open(
            directory / temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset : offset + 65_536])
            if written <= 0:
                _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
            offset += written
        os.fchmod(descriptor, PRIVATE_FILE_MODE)
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or stat.S_IMODE(observed.st_mode) != PRIVATE_FILE_MODE
            or observed.st_nlink != 1
            or observed.st_size != len(payload)
        ):
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        try:
            directory_fd = os.open(
                directory,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            os.replace(
                temporary,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
        except OSError:
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        os.fsync(directory_fd)
    finally:
        if directory_fd >= 0:
            os.close(directory_fd)
        if descriptor >= 0:
            os.close(descriptor)
        try:
            (directory / temporary).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)


@dataclass(frozen=True, slots=True)
class SourceCaptureResult:
    source_ref: str
    status: str
    retrieved_at: str
    body_sha256: str
    response_sha256: str
    request_count: int = 1
    credentials_used: bool = False
    publication_authority: bool = False
    production_evidence: bool = False


def _raw_capture_document(fetched: FetchedSource) -> dict[str, object]:
    material = {
        "body_sha256": bytes_sha256(fetched.body),
        "content_type": fetched.content_type,
        "credentials_used": False,
        "final_url": fetched.target.url,
        "http_method": "GET",
        "http_status": 200,
        "locator_status": _PENDING,
        "publication_authority": PUBLICATION_AUTHORITY,
        "redirect_count": 0,
        "retrieved_at": fetched.retrieved_at,
        "schema": RAW_CAPTURE_SCHEMA,
        "source_ref": fetched.target.source_ref,
    }
    return {**material, "response_sha256": canonical_sha256(material)}


def _evidence(fetched: FetchedSource) -> OfficialSourceCaptureEvidence:
    locators: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []
    for locator in fetched.target.locators:
        fragments: list[tuple[str, str]] = []
        for exact_fragment in locator.exact_utf8_fragments:
            fragment = exact_fragment.encode("utf-8", errors="strict")
            if fetched.body.count(fragment) != 1:
                _fail(OfficialSourceCaptureFailureCode.LOCATOR_MISMATCH)
            fragments.append((exact_fragment, bytes_sha256(fragment)))
        locators.append(
            (
                locator.claim_id,
                locator.claim_statement_sha256,
                tuple(fragments),
            )
        )
    body_sha256 = bytes_sha256(fetched.body)
    material = {
        "body_sha256": body_sha256,
        "content_type": fetched.content_type,
        "final_url": fetched.target.url,
        "http_status": 200,
        "retrieved_at": fetched.retrieved_at,
        "schema": PILOT_SOURCE_CAPTURE_SCHEMA,
        "source_ref": fetched.target.source_ref,
    }
    return OfficialSourceCaptureEvidence(
        source_ref=fetched.target.source_ref,
        final_url=fetched.target.url,
        retrieved_at=fetched.retrieved_at,
        content_type=fetched.content_type,
        body_sha256=body_sha256,
        response_sha256=canonical_sha256(material),
        locators=tuple(locators),
    )


def _persist_capture(
    repository_root: Path, fetched: FetchedSource
) -> SourceCaptureResult:
    """Atomically refresh the current pair; metadata is the last commit marker."""

    if type(fetched) is not FetchedSource:
        _fail()
    directory = _source_directory(repository_root)
    lock_path = directory / CAPTURE_LOCK_FILE
    lock_descriptor = -1
    try:
        lock_descriptor = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            PRIVATE_FILE_MODE,
        )
        os.fchmod(lock_descriptor, PRIVATE_FILE_MODE)
        lock_stat = os.fstat(lock_descriptor)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or stat.S_IMODE(lock_stat.st_mode) != PRIVATE_FILE_MODE
            or lock_stat.st_nlink != 1
        ):
            _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        if fetched.target.locator_status == _PENDING:
            document = _raw_capture_document(fetched)
            body_name = f"{fetched.target.source_ref}.capture.body"
            metadata_name = f"{fetched.target.source_ref}.capture.v1.json"
            status = "BODY_CAPTURED_LOCATORS_PENDING"
        else:
            evidence = _evidence(fetched)
            document = evidence.value()
            body_name = source_body_relative_path(fetched.target.source_ref).name
            metadata_name = source_evidence_relative_path(
                fetched.target.source_ref
            ).name
            status = "CAPTURED_WITH_VERIFIED_LOCATORS"
        metadata = canonical_json_bytes(document) + b"\n"
        # A body without matching metadata is never accepted by the existing
        # reader.  Replacing metadata last commits the refreshed current pair;
        # any prepared packet remains bound to its immutable evidence hashes.
        _replace_private(directory, body_name, fetched.body)
        _replace_private(directory, metadata_name, metadata)
        return SourceCaptureResult(
            source_ref=fetched.target.source_ref,
            status=status,
            retrieved_at=fetched.retrieved_at,
            body_sha256=bytes_sha256(fetched.body),
            response_sha256=cast(str, document["response_sha256"]),
        )
    except OfficialSourceCaptureFailure:
        raise
    except OSError:
        _fail(OfficialSourceCaptureFailureCode.STORE_UNSAFE)
    finally:
        if lock_descriptor >= 0:
            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(lock_descriptor)


def _capture_targets(
    repository_root: Path,
    targets: Sequence[SourceCaptureTarget],
    *,
    connection_factory: OfficialSourceHttpsConnectionFactory,
    clock: Callable[[], datetime],
    environment: Mapping[str, str] | None = None,
) -> tuple[SourceCaptureResult, ...]:
    if not targets or len({target.source_ref for target in targets}) != len(targets):
        _fail()
    results: list[SourceCaptureResult] = []
    for target in targets:
        fetched = _fetch_source(
            target,
            connection_factory=connection_factory,
            clock=clock,
            environment=environment,
        )
        results.append(_persist_capture(repository_root, fetched))
    return tuple(results)


def capture_source_ref(
    repository_root: Path,
    *,
    source_ref: str,
    clock: Callable[[], datetime],
    connection_factory: OfficialSourceHttpsConnectionFactory | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[SourceCaptureResult, ...]:
    """Capture one exact tracked source reference; no caller URL is accepted."""

    if type(source_ref) is not str:
        _fail()
    plan = load_source_capture_plan(repository_root)
    selected_factory = (
        _SystemOfficialSourceHttpsConnectionFactory()
        if connection_factory is None
        else connection_factory
    )
    return _capture_targets(
        repository_root,
        (plan.target(source_ref),),
        connection_factory=selected_factory,
        clock=clock,
        environment=environment,
    )


def capture_article_sources(
    repository_root: Path,
    *,
    article_id: str,
    clock: Callable[[], datetime],
    connection_factory: OfficialSourceHttpsConnectionFactory | None = None,
    environment: Mapping[str, str] | None = None,
) -> tuple[SourceCaptureResult, ...]:
    """Capture only sources bound to one exact tracked pilot article."""

    if type(article_id) is not str:
        _fail()
    plan = load_source_capture_plan(repository_root)
    selected_factory = (
        _SystemOfficialSourceHttpsConnectionFactory()
        if connection_factory is None
        else connection_factory
    )
    return _capture_targets(
        repository_root,
        plan.for_article(article_id),
        connection_factory=selected_factory,
        clock=clock,
        environment=environment,
    )


__all__ = [
    "CAPTURE_ACCEPT",
    "CAPTURE_USER_AGENT",
    "CONNECT_TIMEOUT_SECONDS",
    "LOCATOR_CONTRACT_RELATIVE_PATH",
    "OfficialSourceCaptureFailure",
    "OfficialSourceCaptureFailureCode",
    "READ_TIMEOUT_SECONDS",
    "SourceCapturePlan",
    "SourceCaptureResult",
    "capture_article_sources",
    "capture_source_ref",
    "load_source_capture_plan",
    "require_clean_capture_environment",
]
