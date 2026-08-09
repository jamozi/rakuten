"""Framework-neutral HTTP security values and sanitized failures."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from enum import Enum
import ipaddress
import re
from typing import NoReturn, Self, SupportsIndex, final


_ORIGIN = re.compile(
    r"^(?P<scheme>https|http)://"
    r"(?P<host>[a-z0-9.-]+)"
    r"(?::(?P<port>[0-9]{1,5}))?$"
)
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_BASE64URL_32 = re.compile(r"^[A-Za-z0-9_-]{43}$")
_RFC_TOKEN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_CORRELATION_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_REDACTED_ORIGIN = "<redacted-http-origin>"
_REDACTED_CSRF = "<redacted-csrf-proof>"
_REDACTED_REQUEST = "<redacted-http-request-metadata>"


class HttpSecurityFailureCode(str, Enum):
    """Closed, stable classifications safe to expose at the HTTP boundary."""

    MALFORMED_INPUT = "MALFORMED_INPUT"
    ORIGIN_DENIED = "ORIGIN_DENIED"
    METHOD_DENIED = "METHOD_DENIED"
    HEADER_DENIED = "HEADER_DENIED"
    CONTENT_TYPE_DENIED = "CONTENT_TYPE_DENIED"
    CONTENT_LENGTH_DENIED = "CONTENT_LENGTH_DENIED"
    CSRF_DENIED = "CSRF_DENIED"
    HANDLER_FAILED = "HANDLER_FAILED"


@final
class HttpSecurityFailure(RuntimeError):
    """Immutable failure retaining only one sanitized classification."""

    __slots__ = ("_code", "_sealed")
    _code: HttpSecurityFailureCode
    _sealed: bool

    def __init__(self, code: HttpSecurityFailureCode) -> None:
        if type(code) is not HttpSecurityFailureCode:
            raise TypeError("code must be an exact HttpSecurityFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> HttpSecurityFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("HttpSecurityFailure is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("HttpSecurityFailure is immutable")
        super().__delattr__(name)

    def __repr__(self) -> str:
        return f"HttpSecurityFailure(code={self.code!r})"


def fail_http_security(code: HttpSecurityFailureCode) -> NoReturn:
    """Raise one sanitized HTTP security failure without an exception chain."""

    raise HttpSecurityFailure(code) from None


def _malformed() -> NoReturn:
    fail_http_security(HttpSecurityFailureCode.MALFORMED_INPUT)


def _is_canonical_host(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        address = None
    if address is not None:
        return str(address) == host
    if len(host) > 253 or host.startswith(".") or host.endswith("."):
        return False
    labels = host.split(".")
    return not all(label.isdigit() for label in labels) and all(
        _DNS_LABEL.fullmatch(label) is not None for label in labels
    )


class _RedactedValue:
    __slots__ = ()

    _redacted: str

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self._redacted})"

    def __str__(self) -> str:
        return self._redacted

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("HTTP security value serialization is not supported")


@final
class CanonicalOrigin(_RedactedValue):
    """An exact canonical ASCII origin with narrowly scoped local HTTP."""

    __slots__ = ("_value", "_sealed")
    _redacted = _REDACTED_ORIGIN
    _value: str
    _sealed: bool

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not 1 <= len(value) <= 512
            or any(
                ord(character) < 0x21 or ord(character) > 0x7E for character in value
            )
        ):
            _malformed()
        match = _ORIGIN.fullmatch(value)
        if match is None:
            _malformed()
        scheme = match.group("scheme")
        host = match.group("host")
        port_text = match.group("port")
        if not _is_canonical_host(host):
            _malformed()
        if scheme == "http" and host not in {"localhost", "127.0.0.1"}:
            _malformed()
        if port_text is not None:
            port = int(port_text)
            if not 1 <= port <= 65535 or str(port) != port_text:
                _malformed()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    def reveal(self) -> str:
        """Expose the canonical public origin at an explicit delivery boundary."""

        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("CanonicalOrigin is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("CanonicalOrigin is immutable")
        super().__delattr__(name)

    def __eq__(self, other: object) -> bool:
        return type(other) is CanonicalOrigin and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@final
class CsrfProof(_RedactedValue):
    """A canonical 256-bit CSRF proof that forbids implicit disclosure."""

    __slots__ = ("_value", "_sealed")
    _redacted = _REDACTED_CSRF
    _value: str
    _sealed: bool

    def __init__(self, value: str) -> None:
        if type(value) is not str or _BASE64URL_32.fullmatch(value) is None:
            _malformed()
        decoded: bytes | None = None
        try:
            decoded = base64.b64decode(value + "=", altchars=b"-_", validate=True)
        except binascii.Error, ValueError, UnicodeError:
            pass
        if (
            decoded is None
            or len(decoded) != 32
            or base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii") != value
        ):
            _malformed()
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        if cls is not CsrfProof or type(value) is not bytes or len(value) != 32:
            _malformed()
        return cls(base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii"))

    def reveal_for_comparison(self) -> str:
        """Reveal only to a constant-time comparison at the application boundary."""

        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("CsrfProof is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("CsrfProof is immutable")
        super().__delattr__(name)

    def __eq__(self, other: object) -> NoReturn:
        del other
        raise TypeError("CSRF proofs require constant-time comparison")


class HttpMethod(str, Enum):
    """Closed HTTP methods understood by the security boundary."""

    GET = "GET"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class HttpCredentialMode(str, Enum):
    """Closed credential transport modes used by the request guard."""

    ANONYMOUS = "ANONYMOUS"
    BEARER = "BEARER"
    COOKIE = "COOKIE"


def _normalize_content_type(value: object) -> str:
    if type(value) is not str or value.count("/") != 1:
        _malformed()
    major, minor = value.split("/", 1)
    if (
        _RFC_TOKEN.fullmatch(major) is None
        or _RFC_TOKEN.fullmatch(minor) is None
        or "*" in major
        or "*" in minor
    ):
        _malformed()
    return f"{major.lower()}/{minor.lower()}"


def _require_header_name(value: object) -> str:
    if (
        type(value) is not str
        or value != value.lower()
        or value == "*"
        or _RFC_TOKEN.fullmatch(value) is None
    ):
        _malformed()
    return value


def _require_correlation_id(value: object) -> str:
    if type(value) is not str or _CORRELATION_ID.fullmatch(value) is None:
        _malformed()
    return value


@final
@dataclass(frozen=True, slots=True, repr=False, eq=False)
class HttpRequestMetadata:
    """Validated request metadata that intentionally excludes raw credentials."""

    method: HttpMethod
    origin: CanonicalOrigin | None
    credential_mode: HttpCredentialMode
    content_type: str | None
    content_length: int
    request_header_names: tuple[str, ...]
    presented_csrf_proof: CsrfProof | None
    expected_csrf_proof: CsrfProof | None
    correlation_id: str

    def __post_init__(self) -> None:
        if (
            type(self.method) is not HttpMethod
            or (self.origin is not None and type(self.origin) is not CanonicalOrigin)
            or type(self.credential_mode) is not HttpCredentialMode
            or type(self.content_length) is not int
            or self.content_length < 0
            or type(self.request_header_names) is not tuple
            or (
                self.presented_csrf_proof is not None
                and type(self.presented_csrf_proof) is not CsrfProof
            )
            or (
                self.expected_csrf_proof is not None
                and type(self.expected_csrf_proof) is not CsrfProof
            )
        ):
            _malformed()
        normalized_content_type = (
            None
            if self.content_type is None
            else _normalize_content_type(self.content_type)
        )
        header_names = tuple(
            _require_header_name(value) for value in self.request_header_names
        )
        if len(header_names) != len(set(header_names)):
            _malformed()
        object.__setattr__(self, "content_type", normalized_content_type)
        object.__setattr__(self, "request_header_names", header_names)
        object.__setattr__(
            self, "correlation_id", _require_correlation_id(self.correlation_id)
        )

    def __repr__(self) -> str:
        return f"HttpRequestMetadata({_REDACTED_REQUEST})"

    def __str__(self) -> str:
        return _REDACTED_REQUEST


@final
@dataclass(frozen=True, slots=True, repr=False, kw_only=True)
class HttpSecurityPolicy:
    """Caller-supplied exact allowlists and limits; every default fails closed."""

    max_content_length: int
    allowed_origins: frozenset[CanonicalOrigin] = field(default_factory=frozenset)
    allowed_methods: frozenset[HttpMethod] = field(default_factory=frozenset)
    allowed_content_types: frozenset[str] = field(default_factory=frozenset)
    allowed_request_headers: frozenset[str] = field(default_factory=frozenset)
    hsts_max_age_seconds: int | None = None
    allow_credentials: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.max_content_length) is not int
            or self.max_content_length < 0
            or type(self.allowed_origins) is not frozenset
            or type(self.allowed_methods) is not frozenset
            or type(self.allowed_content_types) is not frozenset
            or type(self.allowed_request_headers) is not frozenset
            or type(self.allow_credentials) is not bool
            or (
                self.hsts_max_age_seconds is not None
                and (
                    type(self.hsts_max_age_seconds) is not int
                    or self.hsts_max_age_seconds < 0
                )
            )
        ):
            _malformed()
        if any(type(origin) is not CanonicalOrigin for origin in self.allowed_origins):
            _malformed()
        if any(type(method) is not HttpMethod for method in self.allowed_methods):
            _malformed()
        normalized_content_types = frozenset(
            _normalize_content_type(value) for value in self.allowed_content_types
        )
        if len(normalized_content_types) != len(self.allowed_content_types):
            _malformed()
        normalized_headers = frozenset(
            _require_header_name(value) for value in self.allowed_request_headers
        )
        if len(normalized_headers) != len(self.allowed_request_headers):
            _malformed()
        if self.allow_credentials and not self.allowed_origins:
            _malformed()
        object.__setattr__(self, "allowed_content_types", normalized_content_types)
        object.__setattr__(self, "allowed_request_headers", normalized_headers)

    def __repr__(self) -> str:
        return "HttpSecurityPolicy(<redacted-http-security-policy>)"


def _problem_definition(code: HttpSecurityFailureCode) -> tuple[str, str, int]:
    if code is HttpSecurityFailureCode.MALFORMED_INPUT:
        return ("urn:raos:problem:http-security:malformed-input", "Bad request", 400)
    if code is HttpSecurityFailureCode.ORIGIN_DENIED:
        return ("urn:raos:problem:http-security:origin-denied", "Forbidden", 403)
    if code is HttpSecurityFailureCode.METHOD_DENIED:
        return (
            "urn:raos:problem:http-security:method-denied",
            "Method not allowed",
            405,
        )
    if code is HttpSecurityFailureCode.HEADER_DENIED:
        return ("urn:raos:problem:http-security:header-denied", "Bad request", 400)
    if code is HttpSecurityFailureCode.CONTENT_TYPE_DENIED:
        return (
            "urn:raos:problem:http-security:content-type-denied",
            "Unsupported media type",
            415,
        )
    if code is HttpSecurityFailureCode.CONTENT_LENGTH_DENIED:
        return (
            "urn:raos:problem:http-security:content-length-denied",
            "Content too large",
            413,
        )
    if code is HttpSecurityFailureCode.CSRF_DENIED:
        return ("urn:raos:problem:http-security:csrf-denied", "Forbidden", 403)
    if code is HttpSecurityFailureCode.HANDLER_FAILED:
        return (
            "urn:raos:problem:http-security:handler-failed",
            "Internal server error",
            500,
        )
    raise AssertionError("unreachable HTTP security failure code")


@final
@dataclass(frozen=True, slots=True, repr=False)
class ProblemDetails:
    """Closed RFC 9457 response containing only allowlisted safe members."""

    type: str
    title: str
    status: int
    code: HttpSecurityFailureCode
    correlation_id: str

    def __post_init__(self) -> None:
        if (
            type(self.code) is not HttpSecurityFailureCode
            or type(self.type) is not str
            or type(self.title) is not str
            or type(self.status) is not int
        ):
            _malformed()
        expected = _problem_definition(self.code)
        if (self.type, self.title, self.status) != expected:
            _malformed()
        object.__setattr__(
            self, "correlation_id", _require_correlation_id(self.correlation_id)
        )

    @classmethod
    def from_failure(cls, failure: HttpSecurityFailure, *, correlation_id: str) -> Self:
        if cls is not ProblemDetails or type(failure) is not HttpSecurityFailure:
            _malformed()
        problem_type, title, status = _problem_definition(failure.code)
        return cls(
            type=problem_type,
            title=title,
            status=status,
            code=failure.code,
            correlation_id=correlation_id,
        )

    def as_dict(self) -> dict[str, str | int]:
        """Return the complete and closed RFC 9457 serialization surface."""

        return {
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "code": self.code.value,
            "correlation_id": self.correlation_id,
        }

    def __repr__(self) -> str:
        return f"ProblemDetails(code={self.code!r}, status={self.status!r})"


__all__ = [
    "CanonicalOrigin",
    "CsrfProof",
    "HttpCredentialMode",
    "HttpMethod",
    "HttpRequestMetadata",
    "HttpSecurityFailure",
    "HttpSecurityFailureCode",
    "HttpSecurityPolicy",
    "ProblemDetails",
    "fail_http_security",
]
