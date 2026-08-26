"""Import isolation and synthetic builders for the ST-0404 security suite."""

from __future__ import annotations

from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"

if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))


from raos.domain.http.security import (  # noqa: E402
    CanonicalOrigin,
    CsrfProof,
    HttpCredentialMode,
    HttpMethod,
    HttpRequestMetadata,
    HttpSecurityPolicy,
)


ADMIN_ORIGIN = CanonicalOrigin("https://admin.example.invalid")
LOCAL_ORIGIN = CanonicalOrigin("http://127.0.0.1:3000")
CSRF_PROOF = CsrfProof.from_bytes(bytes(range(32)))
OTHER_CSRF_PROOF = CsrfProof.from_bytes(bytes(range(1, 33)))


def make_policy(
    *,
    allowed_origins: frozenset[CanonicalOrigin] = frozenset({ADMIN_ORIGIN}),
    allowed_methods: frozenset[HttpMethod] = frozenset(
        {HttpMethod.GET, HttpMethod.POST}
    ),
    allowed_content_types: frozenset[str] = frozenset({"application/json"}),
    allowed_request_headers: frozenset[str] = frozenset(
        {"content-type", "x-csrf-token"}
    ),
    max_content_length: int = 1024,
    hsts_max_age_seconds: int | None = 31536000,
    allow_credentials: bool = True,
) -> HttpSecurityPolicy:
    return HttpSecurityPolicy(
        max_content_length=max_content_length,
        allowed_origins=allowed_origins,
        allowed_methods=allowed_methods,
        allowed_content_types=allowed_content_types,
        allowed_request_headers=allowed_request_headers,
        hsts_max_age_seconds=hsts_max_age_seconds,
        allow_credentials=allow_credentials,
    )


def make_request(
    *,
    method: HttpMethod = HttpMethod.POST,
    origin: CanonicalOrigin | None = ADMIN_ORIGIN,
    credential_mode: HttpCredentialMode = HttpCredentialMode.COOKIE,
    content_type: str | None = "application/json",
    content_length: int = 16,
    request_header_names: tuple[str, ...] = ("content-type", "x-csrf-token"),
    presented_csrf_proof: CsrfProof | None = CSRF_PROOF,
    expected_csrf_proof: CsrfProof | None = CSRF_PROOF,
    correlation_id: str = "synthetic-correlation-0404",
) -> HttpRequestMetadata:
    return HttpRequestMetadata(
        method=method,
        origin=origin,
        credential_mode=credential_mode,
        content_type=content_type,
        content_length=content_length,
        request_header_names=request_header_names,
        presented_csrf_proof=presented_csrf_proof,
        expected_csrf_proof=expected_csrf_proof,
        correlation_id=correlation_id,
    )
