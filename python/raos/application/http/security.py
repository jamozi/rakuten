"""Framework-neutral HTTP request guard and conservative response headers."""

from __future__ import annotations

from collections.abc import Callable
import hmac
from typing import TypeVar

from raos.domain.http.security import (
    HttpCredentialMode,
    HttpMethod,
    HttpRequestMetadata,
    HttpSecurityFailureCode,
    HttpSecurityPolicy,
    fail_http_security,
)


_ResponseT = TypeVar("_ResponseT")
_SAFE_METHODS = frozenset({HttpMethod.GET, HttpMethod.HEAD, HttpMethod.OPTIONS})
_BASE_RESPONSE_HEADERS = (
    ("Cache-Control", "no-store"),
    (
        "Content-Security-Policy",
        "default-src 'none'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'",
    ),
    (
        "Permissions-Policy",
        "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    ),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
)


class HttpSecurityGuard:
    """Validate request metadata before invoking exactly one local handler."""

    __slots__ = ("_policy",)

    def __init__(self, *, policy: HttpSecurityPolicy) -> None:
        if type(policy) is not HttpSecurityPolicy:
            raise TypeError("policy must be an exact HttpSecurityPolicy")
        self._policy = HttpSecurityPolicy(
            max_content_length=policy.max_content_length,
            allowed_origins=policy.allowed_origins,
            allowed_methods=policy.allowed_methods,
            allowed_content_types=policy.allowed_content_types,
            allowed_request_headers=policy.allowed_request_headers,
            hsts_max_age_seconds=policy.hsts_max_age_seconds,
            allow_credentials=policy.allow_credentials,
        )

    def require(self, request: HttpRequestMetadata) -> HttpRequestMetadata:
        """Return a defensive normalized copy when every request check passes."""

        if type(request) is not HttpRequestMetadata:
            fail_http_security(HttpSecurityFailureCode.MALFORMED_INPUT)
        normalized = HttpRequestMetadata(
            method=request.method,
            origin=request.origin,
            credential_mode=request.credential_mode,
            content_type=request.content_type,
            content_length=request.content_length,
            request_header_names=request.request_header_names,
            presented_csrf_proof=request.presented_csrf_proof,
            expected_csrf_proof=request.expected_csrf_proof,
            correlation_id=request.correlation_id,
        )
        policy = self._policy

        if normalized.method not in policy.allowed_methods:
            fail_http_security(HttpSecurityFailureCode.METHOD_DENIED)
        if (
            normalized.origin is not None
            and normalized.origin not in policy.allowed_origins
        ):
            fail_http_security(HttpSecurityFailureCode.ORIGIN_DENIED)
        if not set(normalized.request_header_names).issubset(
            policy.allowed_request_headers
        ):
            fail_http_security(HttpSecurityFailureCode.HEADER_DENIED)
        if normalized.content_length > policy.max_content_length:
            fail_http_security(HttpSecurityFailureCode.CONTENT_LENGTH_DENIED)

        if normalized.method not in _SAFE_METHODS:
            if (
                normalized.content_type is None
                or normalized.content_type not in policy.allowed_content_types
            ):
                fail_http_security(HttpSecurityFailureCode.CONTENT_TYPE_DENIED)
            if normalized.credential_mode is HttpCredentialMode.COOKIE:
                if (
                    normalized.origin is None
                    or normalized.origin not in policy.allowed_origins
                    or normalized.presented_csrf_proof is None
                    or normalized.expected_csrf_proof is None
                ):
                    fail_http_security(HttpSecurityFailureCode.CSRF_DENIED)
                if not hmac.compare_digest(
                    normalized.presented_csrf_proof.reveal_for_comparison(),
                    normalized.expected_csrf_proof.reveal_for_comparison(),
                ):
                    fail_http_security(HttpSecurityFailureCode.CSRF_DENIED)
        return normalized

    def invoke(
        self,
        *,
        request: HttpRequestMetadata,
        handler: Callable[[], _ResponseT],
    ) -> _ResponseT:
        """Validate first, invoke once, and sanitize every handler exception."""

        self.require(request)
        if not callable(handler):
            fail_http_security(HttpSecurityFailureCode.MALFORMED_INPUT)
        try:
            return handler()
        except Exception:
            pass
        fail_http_security(HttpSecurityFailureCode.HANDLER_FAILED)

    def response_headers(
        self, request: HttpRequestMetadata
    ) -> tuple[tuple[str, str], ...]:
        """Return deterministic response and exact-origin CORS headers."""

        normalized = self.require(request)
        headers = list(_BASE_RESPONSE_HEADERS)
        if self._policy.hsts_max_age_seconds is not None:
            headers.append(
                (
                    "Strict-Transport-Security",
                    f"max-age={self._policy.hsts_max_age_seconds}",
                )
            )
        if normalized.origin is not None:
            headers.extend(
                (
                    ("Access-Control-Allow-Origin", normalized.origin.reveal()),
                    ("Vary", "Origin"),
                    (
                        "Access-Control-Allow-Methods",
                        ", ".join(
                            sorted(
                                method.value for method in self._policy.allowed_methods
                            )
                        ),
                    ),
                )
            )
            if self._policy.allowed_request_headers:
                headers.append(
                    (
                        "Access-Control-Allow-Headers",
                        ", ".join(sorted(self._policy.allowed_request_headers)),
                    )
                )
            if self._policy.allow_credentials:
                headers.append(("Access-Control-Allow-Credentials", "true"))
        return tuple(headers)


__all__ = ["HttpSecurityGuard"]
