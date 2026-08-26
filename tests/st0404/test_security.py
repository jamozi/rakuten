"""Focused behavior and hostile-input tests for ST-0404 HTTP security."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import FrozenInstanceError, fields
import pickle
from typing import Any, cast

import pytest

from .support import (
    ADMIN_ORIGIN,
    CSRF_PROOF,
    LOCAL_ORIGIN,
    OTHER_CSRF_PROOF,
    make_policy,
    make_request,
)
from raos.application.http.security import HttpSecurityGuard
from raos.domain.http.security import (
    CanonicalOrigin,
    CsrfProof,
    HttpCredentialMode,
    HttpMethod,
    HttpRequestMetadata,
    HttpSecurityFailure,
    HttpSecurityFailureCode,
    HttpSecurityPolicy,
    ProblemDetails,
)


def _assert_failure(
    code: HttpSecurityFailureCode, operation: Callable[[], object]
) -> HttpSecurityFailure:
    with pytest.raises(HttpSecurityFailure) as captured:
        operation()
    assert captured.value.code is code
    return captured.value


def test_exact_synthetic_origin_and_unsafe_cookie_request_pass_once() -> None:
    guard = HttpSecurityGuard(policy=make_policy())
    calls = 0
    marker = object()

    def handler() -> object:
        nonlocal calls
        calls += 1
        return marker

    assert guard.invoke(request=make_request(), handler=handler) is marker
    assert calls == 1
    normalized = guard.require(make_request(content_type="Application/JSON"))
    assert normalized.content_type == "application/json"
    assert normalized is not make_request()


def test_canonical_origins_are_exact_ascii_and_redacted() -> None:
    assert ADMIN_ORIGIN.reveal() == "https://admin.example.invalid"
    assert LOCAL_ORIGIN.reveal() == "http://127.0.0.1:3000"
    assert ADMIN_ORIGIN.reveal() not in repr(ADMIN_ORIGIN)
    assert ADMIN_ORIGIN.reveal() not in str(ADMIN_ORIGIN)

    malformed = (
        "*",
        "null",
        "HTTPS://admin.example.invalid",
        "https://Admin.example.invalid",
        "https://user@admin.example.invalid",
        "https://admin.example.invalid/",
        "https://admin.example.invalid/path",
        "https://admin.example.invalid?query",
        "https://admin.example.invalid#fragment",
        "http://admin.example.invalid",
        "ftp://admin.example.invalid",
        "https://admin.example.invalid:000443",
        "https://admin.example.invalid:0",
        "https://admin.example.invalid:65536",
        "https://admin.example.invalid\n",
        "https://admin.example.invalid\x7f",
        "https://例.invalid",
    )
    for value in malformed:

        def construct_origin(value: str = value) -> object:
            return CanonicalOrigin(value)

        _assert_failure(
            HttpSecurityFailureCode.MALFORMED_INPUT,
            construct_origin,
        )


@pytest.mark.parametrize(
    "origin",
    (
        "https://prefix-admin.example.invalid",
        "https://admin.example.invalid.attacker.invalid",
        "https://admin.example.invalid:443",
        "https://127.0.0.1:3000",
    ),
)
def test_origin_prefix_suffix_port_and_scheme_variants_are_denied(
    origin: str,
) -> None:
    calls = 0

    def handler() -> None:
        nonlocal calls
        calls += 1

    _assert_failure(
        HttpSecurityFailureCode.ORIGIN_DENIED,
        lambda: HttpSecurityGuard(policy=make_policy()).invoke(
            request=make_request(origin=CanonicalOrigin(origin)), handler=handler
        ),
    )
    assert calls == 0


def test_empty_origin_allowlist_default_denies_present_origins() -> None:
    policy = HttpSecurityPolicy(
        max_content_length=0,
        allowed_methods=frozenset({HttpMethod.GET}),
    )
    guard = HttpSecurityGuard(policy=policy)
    _assert_failure(
        HttpSecurityFailureCode.ORIGIN_DENIED,
        lambda: guard.invoke(
            request=make_request(
                method=HttpMethod.GET,
                origin=ADMIN_ORIGIN,
                credential_mode=HttpCredentialMode.ANONYMOUS,
                content_type=None,
                content_length=0,
                request_header_names=(),
                presented_csrf_proof=None,
                expected_csrf_proof=None,
            ),
            handler=lambda: None,
        ),
    )
    assert (
        guard.invoke(
            request=make_request(
                method=HttpMethod.GET,
                origin=None,
                credential_mode=HttpCredentialMode.ANONYMOUS,
                content_type=None,
                content_length=0,
                request_header_names=(),
                presented_csrf_proof=None,
                expected_csrf_proof=None,
            ),
            handler=lambda: "accepted",
        )
        == "accepted"
    )


def test_wildcard_and_credentialed_empty_origin_policy_are_impossible() -> None:
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: CanonicalOrigin("*"),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=frozenset({HttpMethod.GET}),
            allowed_content_types=frozenset({"*/*"}),
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=frozenset({HttpMethod.GET}),
            allowed_request_headers=frozenset({"*"}),
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=frozenset({HttpMethod.GET}),
            allow_credentials=True,
        ),
    )
    with pytest.raises(TypeError):
        HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=frozenset({HttpMethod.GET}),
            content_security_policy="script-src 'unsafe-inline'",  # type: ignore[call-arg]
        )


@pytest.mark.parametrize(
    ("request_metadata", "code"),
    (
        (
            make_request(presented_csrf_proof=None),
            HttpSecurityFailureCode.CSRF_DENIED,
        ),
        (
            make_request(expected_csrf_proof=None),
            HttpSecurityFailureCode.CSRF_DENIED,
        ),
        (
            make_request(presented_csrf_proof=OTHER_CSRF_PROOF),
            HttpSecurityFailureCode.CSRF_DENIED,
        ),
        (make_request(origin=None), HttpSecurityFailureCode.CSRF_DENIED),
        (
            make_request(origin=LOCAL_ORIGIN),
            HttpSecurityFailureCode.ORIGIN_DENIED,
        ),
    ),
)
def test_unsafe_cookie_requires_allowed_origin_and_matching_proofs(
    request_metadata: HttpRequestMetadata, code: HttpSecurityFailureCode
) -> None:
    calls = 0

    def handler() -> None:
        nonlocal calls
        calls += 1

    _assert_failure(
        code,
        lambda: HttpSecurityGuard(policy=make_policy()).invoke(
            request=request_metadata, handler=handler
        ),
    )
    assert calls == 0


@pytest.mark.parametrize(
    ("policy", "request_metadata", "code"),
    (
        (
            make_policy(allowed_methods=frozenset({HttpMethod.GET})),
            make_request(),
            HttpSecurityFailureCode.METHOD_DENIED,
        ),
        (
            make_policy(),
            make_request(content_type="text/plain"),
            HttpSecurityFailureCode.CONTENT_TYPE_DENIED,
        ),
        (
            make_policy(),
            make_request(request_header_names=("content-type", "x-extra")),
            HttpSecurityFailureCode.HEADER_DENIED,
        ),
        (
            make_policy(max_content_length=15),
            make_request(content_length=16),
            HttpSecurityFailureCode.CONTENT_LENGTH_DENIED,
        ),
    ),
)
def test_method_content_type_header_and_oversize_denials_precede_handler(
    policy: HttpSecurityPolicy,
    request_metadata: HttpRequestMetadata,
    code: HttpSecurityFailureCode,
) -> None:
    calls = 0

    def handler() -> None:
        nonlocal calls
        calls += 1

    _assert_failure(
        code,
        lambda: HttpSecurityGuard(policy=policy).invoke(
            request=request_metadata, handler=handler
        ),
    )
    assert calls == 0


def test_negative_or_boolean_content_length_fails_before_a_handler_exists() -> None:
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: make_request(content_length=-1),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: make_request(content_length=cast(int, True)),
    )


def test_handler_exception_is_sanitized_without_chaining() -> None:
    canary = "SYNTHETIC-PRIVATE-HANDLER-CANARY"
    calls = 0

    def handler() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError(f"{canary}:{CSRF_PROOF.reveal_for_comparison()}")

    failure = _assert_failure(
        HttpSecurityFailureCode.HANDLER_FAILED,
        lambda: HttpSecurityGuard(policy=make_policy()).invoke(
            request=make_request(), handler=handler
        ),
    )
    assert calls == 1
    diagnostics = f"{failure!s} {failure!r} {failure.args!r}"
    assert canary not in diagnostics
    assert CSRF_PROOF.reveal_for_comparison() not in diagnostics
    assert failure.__cause__ is None
    assert failure.__context__ is None


def test_response_headers_are_conservative_exact_and_deterministic() -> None:
    guard = HttpSecurityGuard(policy=make_policy())
    first = guard.response_headers(make_request())
    second = guard.response_headers(make_request())
    assert first == second
    headers = dict(first)
    assert headers["Content-Security-Policy"] == (
        "default-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    )
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Strict-Transport-Security"] == "max-age=31536000"
    assert headers["Access-Control-Allow-Origin"] == ADMIN_ORIGIN.reveal()
    assert headers["Access-Control-Allow-Credentials"] == "true"
    assert headers["Vary"] == "Origin"
    joined = " ".join(headers.values()).lower()
    assert "unsafe-inline" not in joined
    assert "unsafe-eval" not in joined
    assert "*" not in joined

    no_hsts = HttpSecurityGuard(
        policy=make_policy(hsts_max_age_seconds=None)
    ).response_headers(make_request())
    assert "Strict-Transport-Security" not in dict(no_hsts)


def test_problem_details_are_closed_fixed_and_redacted() -> None:
    expected_statuses = {
        HttpSecurityFailureCode.MALFORMED_INPUT: 400,
        HttpSecurityFailureCode.ORIGIN_DENIED: 403,
        HttpSecurityFailureCode.METHOD_DENIED: 405,
        HttpSecurityFailureCode.HEADER_DENIED: 400,
        HttpSecurityFailureCode.CONTENT_TYPE_DENIED: 415,
        HttpSecurityFailureCode.CONTENT_LENGTH_DENIED: 413,
        HttpSecurityFailureCode.CSRF_DENIED: 403,
        HttpSecurityFailureCode.HANDLER_FAILED: 500,
    }
    assert set(HttpSecurityFailureCode) == set(expected_statuses)
    assert {item.name for item in fields(ProblemDetails)} == {
        "type",
        "title",
        "status",
        "code",
        "correlation_id",
    }
    for code, status in expected_statuses.items():
        problem = ProblemDetails.from_failure(
            HttpSecurityFailure(code), correlation_id="correlation-0404"
        )
        assert problem.status == status
        assert problem.type.startswith("urn:raos:problem:http-security:")
        assert set(problem.as_dict()) == {
            "type",
            "title",
            "status",
            "code",
            "correlation_id",
        }
        assert "detail" not in problem.as_dict()
        assert "exception" not in problem.as_dict()
        assert "extensions" not in problem.as_dict()

    valid = ProblemDetails.from_failure(
        HttpSecurityFailure(HttpSecurityFailureCode.CSRF_DENIED),
        correlation_id="correlation-0404",
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: ProblemDetails(
            type=valid.type,
            title="attacker-controlled-title",
            status=valid.status,
            code=valid.code,
            correlation_id=valid.correlation_id,
        ),
    )
    with pytest.raises(FrozenInstanceError):
        valid.title = "changed"  # type: ignore[misc]


def test_csrf_proofs_are_canonical_redacted_immutable_and_not_picklable() -> None:
    raw = CSRF_PROOF.reveal_for_comparison()
    assert len(raw) == 43
    assert raw not in repr(CSRF_PROOF)
    assert raw not in str(CSRF_PROOF)
    with pytest.raises(TypeError):
        pickle.dumps(CSRF_PROOF)
    with pytest.raises(TypeError):
        cast(Any, CSRF_PROOF) == CSRF_PROOF
    with pytest.raises(AttributeError):
        CSRF_PROOF._value = "changed"
    for malformed in ("", raw + "=", raw[:-1], "+" + raw[1:], "/" + raw[1:]):

        def construct_csrf_proof(malformed: str = malformed) -> object:
            return CsrfProof(malformed)

        _assert_failure(
            HttpSecurityFailureCode.MALFORMED_INPUT,
            construct_csrf_proof,
        )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: CsrfProof.from_bytes(b"short"),
    )


def test_wrong_types_subclasses_duplicates_and_malformed_values_fail_closed() -> None:
    class StringSubclass(str):
        pass

    class TupleSubclass(tuple[str, ...]):
        pass

    class FrozenSetSubclass(frozenset[HttpMethod]):
        pass

    class OriginSubclass(CanonicalOrigin):  # type: ignore[misc]
        pass

    class PolicySubclass(HttpSecurityPolicy):  # type: ignore[misc]
        pass

    class FailureSubclass(HttpSecurityFailure):  # type: ignore[misc]
        pass

    class ProofSubclass(CsrfProof):  # type: ignore[misc]
        pass

    class ProblemDetailsSubclass(ProblemDetails):  # type: ignore[misc]
        pass

    origin_subclass = OriginSubclass("https://admin.example.invalid")
    bad_metadata: tuple[Callable[[], object], ...] = (
        lambda: make_request(method=cast(HttpMethod, "POST")),
        lambda: make_request(origin=origin_subclass),
        lambda: make_request(credential_mode=cast(HttpCredentialMode, "COOKIE")),
        lambda: make_request(content_type=cast(str, StringSubclass("text/plain"))),
        lambda: make_request(
            request_header_names=cast(tuple[str, ...], TupleSubclass(("content-type",)))
        ),
        lambda: make_request(request_header_names=("Content-Type",)),
        lambda: make_request(request_header_names=("content-type", "content-type")),
        lambda: make_request(
            correlation_id=cast(str, StringSubclass("correlation-0404"))
        ),
    )
    for operation in bad_metadata:
        _assert_failure(HttpSecurityFailureCode.MALFORMED_INPUT, operation)

    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=cast(int, True),
            allowed_methods=frozenset({HttpMethod.GET}),
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            hsts_max_age_seconds=cast(int, False),
            allowed_methods=frozenset({HttpMethod.GET}),
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=cast(
                frozenset[HttpMethod], FrozenSetSubclass({HttpMethod.GET})
            ),
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: HttpSecurityPolicy(
            max_content_length=0,
            allowed_methods=frozenset({HttpMethod.GET}),
            allowed_content_types=frozenset({"application/json", "Application/JSON"}),
        ),
    )
    subclassed_policy = PolicySubclass(
        max_content_length=0,
        allowed_methods=frozenset({HttpMethod.GET}),
    )
    with pytest.raises(TypeError):
        HttpSecurityGuard(policy=subclassed_policy)
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: ProblemDetails.from_failure(
            FailureSubclass(HttpSecurityFailureCode.CSRF_DENIED),
            correlation_id="correlation-0404",
        ),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: ProofSubclass.from_bytes(bytes(range(32))),
    )
    _assert_failure(
        HttpSecurityFailureCode.MALFORMED_INPUT,
        lambda: ProblemDetailsSubclass.from_failure(
            HttpSecurityFailure(HttpSecurityFailureCode.CSRF_DENIED),
            correlation_id="correlation-0404",
        ),
    )
