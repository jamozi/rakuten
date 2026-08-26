"""Recorded contract tests for the ST-0703 OpenAI Responses adapter."""

from __future__ import annotations

import ast
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import socket
from collections.abc import Callable
from typing import cast
from uuid import UUID

import pytest
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    UnprocessableEntityError,
)

from .support import REPOSITORY_ROOT
import raos.adapters.openai_responses as adapter_module
from raos.adapters.openai_responses import (
    OpenAIResponseRoute,
    OpenAIResponsesAdapter,
    ReasoningEffort,
)
from raos.adapters.recorded_ai import (
    InMemoryProviderExchangeRecorder,
    SyntheticRecordedCostCalculator,
)
from raos.domain.ai.provider import (
    ArtifactRef,
    calculate_synthetic_pricing_reference,
    IncompleteReason,
    MessageRole,
    ProviderIncomplete,
    PricingResult,
    ProviderRefusal,
    ProviderSuccess,
    ProviderUsage,
    RequestMetadata,
    Sha256Digest,
    StructuredInputMessage,
    StructuredOutputSchema,
    StructuredTaskRequest,
    SyntheticPricingQuote,
    synthetic_pricing_calculation_sha256,
)
from raos.ports.ai_provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderExchange,
    RecordedCostCalculator,
    StructuredModelProvider,
)


FIXTURE_ROOT = REPOSITORY_ROOT / "changes/st-0703/fixtures/recorded"
FIXTURE_NAMES = (
    "success-structured.json",
    "refusal-completed.json",
    "incomplete-max-output-tokens.json",
    "incomplete-content-filter.json",
    "error-rate-limit-429.json",
)
NOW = datetime(2026, 8, 6, 0, 0, 10, tzinfo=timezone.utc)


class _StatusError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__("SYNTHETIC_TEST_ONLY provider diagnostic")
        self.status_code = status_code


class _FakeResponses:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(copy.deepcopy(kwargs))
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return copy.deepcopy(self._outcome)


class _ConfiguredClient:
    def __init__(self, responses: _FakeResponses) -> None:
        self.responses = responses


class _FakeClient:
    def __init__(self, outcome: object) -> None:
        self.responses_resource = _FakeResponses(outcome)
        self.options: list[dict[str, object]] = []

    def with_options(
        self,
        *,
        max_retries: int,
        timeout: float,
    ) -> _ConfiguredClient:
        self.options.append({"max_retries": max_retries, "timeout": timeout})
        return _ConfiguredClient(self.responses_resource)


def _fixture(name: str) -> dict[str, object]:
    return cast(
        dict[str, object],
        json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8")),
    )


def _quote() -> SyntheticPricingQuote:
    return SyntheticPricingQuote(
        quote_id="st0703-synthetic-quote-v1",
        provider="openai",
        model_id="raos-synthetic-model-v1",
        native_currency="JPY",
        input_per_million=Decimal("81340"),
        cached_input_per_million=Decimal("486430"),
        output_per_million=Decimal("21700"),
        jpy_per_native_unit=Decimal("1"),
        observed_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 7, tzinfo=timezone.utc),
    )


def _route() -> OpenAIResponseRoute:
    return OpenAIResponseRoute(
        route_version="route.synthetic.recorded.v1",
        model_id="raos-synthetic-model-v1",
        reasoning_effort=ReasoningEffort.MEDIUM,
        timeout_seconds=12.5,
        pricing_quote=_quote(),
    )


def _request() -> StructuredTaskRequest:
    fixture = _fixture("success-structured.json")
    expected_request = cast(dict[str, object], fixture["expected_request"])
    text = cast(dict[str, object], expected_request["text"])
    output_format = cast(dict[str, object], text["format"])
    schema_document = cast(dict[str, object], output_format["schema"])
    schema_bytes = json.dumps(
        schema_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    input_bytes = b'{"synthetic":"SYNTHETIC_TEST_ONLY"}'
    return StructuredTaskRequest(
        task_code="AIT-004",
        model_route_version="route.synthetic.recorded.v1",
        prompt_version="PRM-004-v1",
        input_artifact=ArtifactRef(
            artifact_id=UUID("11111111-1111-4111-8111-111111111111"),
            sha256=Sha256Digest.of(input_bytes),
            uri="file://recorded/synthetic-input.json",
            content_type="application/json",
            byte_size=len(input_bytes),
        ),
        output_schema=StructuredOutputSchema(
            name=cast(str, output_format["name"]),
            uri="urn:raos:synthetic:st0703:output:v1",
            sha256=Sha256Digest.of(schema_bytes),
            document_bytes=schema_bytes,
        ),
        messages=(
            StructuredInputMessage(
                MessageRole.DEVELOPER,
                "SYNTHETIC_TEST_ONLY developer instruction.",
            ),
            StructuredInputMessage(
                MessageRole.USER,
                "SYNTHETIC_TEST_ONLY input record.",
            ),
        ),
        max_cost_jpy=100,
        max_output_tokens=128,
        metadata=RequestMetadata(
            correlation_id=UUID("22222222-2222-4222-8222-222222222222"),
            job_id=UUID("33333333-3333-4333-8333-333333333333"),
            environment="test",
        ),
    )


def _adapter(
    outcome: object,
) -> tuple[OpenAIResponsesAdapter, _FakeClient, InMemoryProviderExchangeRecorder]:
    client = _FakeClient(outcome)
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )
    assert isinstance(adapter, StructuredModelProvider)
    return adapter, client, recorder


def _custom_adapter(
    outcome: object,
    *,
    route: OpenAIResponseRoute,
    cost_calculator: RecordedCostCalculator,
    clock: Callable[[], datetime] = lambda: NOW,
) -> tuple[OpenAIResponsesAdapter, _FakeClient, InMemoryProviderExchangeRecorder]:
    client = _FakeClient(outcome)
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=route,
        recorder=recorder,
        cost_calculator=cost_calculator,
        clock=clock,
        monotonic_clock_ns=lambda: next(ticks),
    )
    return adapter, client, recorder


_STATUS_ABSENT = object()


def _named_error(name: str, status: object = _STATUS_ABSENT) -> Exception:
    error_type = type(name, (RuntimeError,), {})
    error = error_type("SYNTHETIC_TEST_ONLY provider diagnostic")
    if status is not _STATUS_ABSENT:
        setattr(error, "status_code", status)
    return cast(Exception, error)


def _sdk_subclass_error(
    exception_type: type[Exception],
    status: object = _STATUS_ABSENT,
) -> Exception:
    synthetic_type = type("SyntheticSDKError", (exception_type,), {})
    try:
        error = cast(Exception, BaseException.__new__(synthetic_type))
        Exception.__init__(error, "SYNTHETIC_TEST_ONLY provider diagnostic")
    except TypeError:
        error = synthetic_type("SYNTHETIC_TEST_ONLY provider diagnostic")
    if status is not _STATUS_ABSENT:
        setattr(error, "status_code", status)
    return error


def _pricing_result_with(
    reference: PricingResult,
    **overrides: object,
) -> PricingResult:
    values: dict[str, object] = {
        "estimated_cost_jpy": reference.estimated_cost_jpy,
        "provider_cost_native": reference.provider_cost_native,
        "native_currency": reference.native_currency,
        "quote_id": reference.quote_id,
        "quote_sha256": reference.quote_sha256,
        "provider": reference.provider,
        "model_id": reference.model_id,
        "usage_sha256": reference.usage_sha256,
        "evaluated_at": reference.evaluated_at,
    }
    values.update(overrides)
    calculation_sha256 = synthetic_pricing_calculation_sha256(
        quote_sha256=cast(Sha256Digest, values["quote_sha256"]),
        usage_sha256=cast(Sha256Digest, values["usage_sha256"]),
        provider=cast(str, values["provider"]),
        model_id=cast(str, values["model_id"]),
        evaluated_at=cast(datetime, values["evaluated_at"]),
        provider_cost_native=cast(Decimal, values["provider_cost_native"]),
        native_currency=cast(str, values["native_currency"]),
        estimated_cost_jpy=cast(int, values["estimated_cost_jpy"]),
    )
    return PricingResult(
        estimated_cost_jpy=cast(int, values["estimated_cost_jpy"]),
        provider_cost_native=cast(Decimal, values["provider_cost_native"]),
        native_currency=cast(str, values["native_currency"]),
        quote_id=cast(str, values["quote_id"]),
        quote_sha256=cast(Sha256Digest, values["quote_sha256"]),
        provider=cast(str, values["provider"]),
        model_id=cast(str, values["model_id"]),
        usage_sha256=cast(Sha256Digest, values["usage_sha256"]),
        evaluated_at=cast(datetime, values["evaluated_at"]),
        calculation_sha256=calculation_sha256,
    )


class _FixedCalculator:
    def __init__(self, result: PricingResult) -> None:
        self._result = result
        self.calls: list[dict[str, object]] = []

    def calculate(
        self,
        *,
        usage: ProviderUsage,
        provider: str,
        model_id: str,
        quote: SyntheticPricingQuote,
        evaluated_at: datetime,
    ) -> PricingResult:
        self.calls.append(
            {
                "usage": usage,
                "provider": provider,
                "model_id": model_id,
                "quote": quote,
                "evaluated_at": evaluated_at,
            }
        )
        return self._result


class _TrackingCalculator:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._delegate = SyntheticRecordedCostCalculator()

    def calculate(
        self,
        *,
        usage: ProviderUsage,
        provider: str,
        model_id: str,
        quote: SyntheticPricingQuote,
        evaluated_at: datetime,
    ) -> PricingResult:
        self.calls.append(
            {
                "usage": usage,
                "provider": provider,
                "model_id": model_id,
                "quote": quote,
                "evaluated_at": evaluated_at,
            }
        )
        return self._delegate.calculate(
            usage=usage,
            provider=provider,
            model_id=model_id,
            quote=quote,
            evaluated_at=evaluated_at,
        )


@pytest.mark.parametrize("fixture_name", FIXTURE_NAMES)
def test_recorded_fixture_contract(fixture_name: str) -> None:
    fixture = _fixture(fixture_name)
    transport = cast(dict[str, object], fixture["transport"])
    status_code = cast(int, transport["status_code"])
    if status_code == 200:
        outcome: object = transport["body"]
    else:
        outcome = _StatusError(status_code)
    adapter, client, recorder = _adapter(outcome)
    expected = cast(dict[str, object], fixture["expected"])

    if expected["kind"] == "ProviderError":
        with pytest.raises(ProviderError) as captured:
            adapter.execute(_request())
        error = captured.value
        assert error.stable_code.value == expected["provider_error_code"]
        assert error.retryable is expected["retryable"]
        assert error.__cause__ is None
    else:
        result = adapter.execute(_request())
        expected_usage = cast(dict[str, int], expected["usage"])
        assert result.usage.input_tokens == expected_usage["input_tokens"]
        assert result.usage.cached_input_tokens == expected_usage["cached_input_tokens"]
        assert result.usage.output_tokens == expected_usage["output_tokens"]
        expected_pricing = cast(dict[str, object], fixture["pricing"])
        assert (
            result.pricing.estimated_cost_jpy == expected_pricing["expected_cost_jpy"]
        )
        assert result.metadata.latency_ms == 12
        assert result.metadata.received_at == NOW
        if isinstance(result, ProviderSuccess):
            assert json.loads(result.output.canonical_bytes()) == expected["output"]
        elif isinstance(result, ProviderRefusal):
            assert result.refusal_code == expected["refusal_code"]
        else:
            assert isinstance(result, ProviderIncomplete)
            assert result.reason.value == expected["incomplete_reason"]
        recorded_bytes = recorder.read(result.raw_artifact)
        recorded = json.loads(recorded_bytes)
        assert recorded_bytes == json.dumps(
            recorded,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        assert 0 < len(recorded_bytes) <= 4 * 1024 * 1024
        assert set(recorded) == {"provider", "request", "response"}
        assert recorded["provider"] == "openai"
        assert set(recorded["request"]) == {
            "request_sha256",
            "task_code",
            "model_route_version",
            "prompt_version",
            "input_artifact_sha256",
            "output_schema_sha256",
        }
        assert set(recorded["response"]) == {
            "response_id",
            "requested_model_id",
            "resolved_model_id",
            "status",
            "created_at",
            "received_at",
            "latency_ms",
            "usage",
            "outcome",
        }
        assert set(recorded["response"]["usage"]) == {
            "input_tokens",
            "cached_input_tokens",
            "output_tokens",
        }
        assert recorded["request"]["request_sha256"] == _request().request_sha256.value
        assert "content" not in json.dumps(recorded["request"])
        assert "SYNTHETIC_TEST_ONLY refusal marker" not in json.dumps(recorded)
        assert "estimated_cost_jpy" not in json.dumps(recorded)
        assert "provider_request_id" not in json.dumps(recorded)
        assert result.response_sha256 == result.raw_artifact.sha256
        assert result.raw_artifact.byte_size == len(recorded_bytes)
        assert result.raw_artifact.content_type == "application/json"
        if isinstance(result, ProviderSuccess):
            assert recorded["response"]["outcome"] == {"kind": "success"}
            assert "synthetic-pass" not in json.dumps(recorded)
        elif isinstance(result, ProviderRefusal):
            assert recorded["response"]["outcome"] == {
                "kind": "refusal",
                "refusal": True,
            }
        else:
            assert isinstance(result, ProviderIncomplete)
            assert recorded["response"]["outcome"] == {
                "kind": "incomplete",
                "reason": result.reason.value,
            }

    assert client.options == [{"max_retries": 0, "timeout": 12.5}]
    assert client.responses_resource.calls == [fixture["expected_request"]]
    assert recorder.record_calls == expected["recorder_calls"]


def test_success_record_excludes_structured_output_content() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = '{"label":"SYNTHETIC_TEST_ONLY output content canary","score":7}'
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert b"output content canary" in result.output.canonical_bytes()
    recorded = recorder.read(result.raw_artifact)
    assert b"output content canary" not in recorded
    assert json.loads(recorded)["response"]["outcome"] == {"kind": "success"}


def test_recorded_exchange_excludes_all_unlisted_content_canaries() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = '{"label":"output-content-canary","score":7}'
    body.update(
        {
            "headers": {"x-canary": "header-canary"},
            "url": "https://url-canary.invalid",
            "credential": "credential-canary",
            "error": {"body": "error-body-canary"},
            "unlisted": "provider-field-canary",
        }
    )
    request = _request()
    request = StructuredTaskRequest(
        task_code=request.task_code,
        model_route_version=request.model_route_version,
        prompt_version=request.prompt_version,
        input_artifact=ArtifactRef(
            artifact_id=request.input_artifact.artifact_id,
            sha256=request.input_artifact.sha256,
            uri="file://source-material-canary/input.json",
            content_type=request.input_artifact.content_type,
            byte_size=request.input_artifact.byte_size,
        ),
        output_schema=request.output_schema,
        messages=(
            StructuredInputMessage(
                MessageRole.DEVELOPER,
                "developer-prompt-canary",
            ),
            StructuredInputMessage(MessageRole.USER, "user-source-canary"),
        ),
        max_cost_jpy=request.max_cost_jpy,
        max_output_tokens=request.max_output_tokens,
        metadata=request.metadata,
    )
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(request)
    recorded = recorder.read(result.raw_artifact)

    assert isinstance(result, ProviderSuccess)
    for canary in (
        b"output-content-canary",
        b"header-canary",
        b"url-canary",
        b"credential-canary",
        b"error-body-canary",
        b"provider-field-canary",
        b"source-material-canary",
        b"developer-prompt-canary",
        b"user-source-canary",
    ):
        assert canary not in recorded


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize(
    "relative_path",
    (
        Path("python/raos/domain/ai/provider.py"),
        Path("python/raos/ports/ai_provider.py"),
    ),
)
def test_inward_boundary_has_no_adapter_or_provider_sdk_dependency(
    relative_path: Path,
) -> None:
    imported = _imported_modules(REPOSITORY_ROOT / relative_path)

    assert not any(
        module == "openai"
        or module.startswith("openai.")
        or module == "raos.adapters"
        or module.startswith("raos.adapters.")
        for module in imported
    )


def test_adapter_has_no_environment_or_network_import_path() -> None:
    adapter_path = REPOSITORY_ROOT / "python/raos/adapters/openai_responses.py"
    imported = _imported_modules(adapter_path)
    forbidden_roots = {
        "boto3",
        "httpx",
        "os",
        "pathlib",
        "playwright",
        "psycopg",
        "redis",
        "requests",
        "socket",
        "sqlalchemy",
        "urllib",
    }

    assert forbidden_roots.isdisjoint(module.partition(".")[0] for module in imported)
    assert "openai" in imported

    tree = ast.parse(adapter_path.read_text(encoding="utf-8"))
    imported_openai_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "openai"
        for alias in node.names
    }
    assert imported_openai_names == {
        "APIConnectionError",
        "APITimeoutError",
        "AuthenticationError",
        "BadRequestError",
        "ConflictError",
        "InternalServerError",
        "NotFoundError",
        "PermissionDeniedError",
        "RateLimitError",
        "UnprocessableEntityError",
    }


def test_adapter_has_no_ambient_clock_path() -> None:
    source = (REPOSITORY_ROOT / "python/raos/adapters/openai_responses.py").read_text(
        encoding="utf-8"
    )

    assert "datetime.now(" not in source
    assert "from time import" not in source


def test_recorded_execution_has_no_network_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    adapter, _, _ = _adapter(transport["body"])

    assert isinstance(adapter.execute(_request()), ProviderSuccess)


@pytest.mark.parametrize(
    ("error", "expected"),
    (
        (_StatusError(401), ProviderErrorCode.AUTHENTICATION),
        (_StatusError(403), ProviderErrorCode.PERMISSION),
        (_StatusError(400), ProviderErrorCode.INVALID_REQUEST),
        (_StatusError(500), ProviderErrorCode.SERVER_ERROR),
        (_StatusError(503), ProviderErrorCode.UNAVAILABLE),
        (TimeoutError("SYNTHETIC_TEST_ONLY"), ProviderErrorCode.TIMEOUT),
        (RuntimeError("SYNTHETIC_TEST_ONLY"), ProviderErrorCode.UNKNOWN),
    ),
)
def test_provider_errors_are_sanitized(
    error: Exception, expected: ProviderErrorCode
) -> None:
    adapter, _, recorder = _adapter(error)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is expected
    assert "SYNTHETIC_TEST_ONLY" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert recorder.record_calls == 0


def test_route_mismatch_fails_before_provider_call() -> None:
    body = cast(dict[str, object], _fixture("success-structured.json")["transport"])[
        "body"
    ]
    adapter, client, recorder = _adapter(body)
    request = _request()
    request = StructuredTaskRequest(
        task_code=request.task_code,
        model_route_version="route.other.v1",
        prompt_version=request.prompt_version,
        input_artifact=request.input_artifact,
        output_schema=request.output_schema,
        messages=request.messages,
        max_cost_jpy=request.max_cost_jpy,
        max_output_tokens=request.max_output_tokens,
        metadata=request.metadata,
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(request)

    assert captured.value.stable_code is ProviderErrorCode.ROUTE_MISMATCH
    assert client.options == []
    assert client.responses_resource.calls == []
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("route_version", "route with spaces"),
        ("model_id", "model with spaces"),
        ("model_id", "../unsafe"),
        ("route_version", ""),
    ),
)
def test_route_rejects_unsafe_identifiers_before_adapter_construction(
    field_name: str,
    value: str,
) -> None:
    values: dict[str, object] = {
        "route_version": "route.synthetic.recorded.v1",
        "model_id": "raos-synthetic-model-v1",
        "reasoning_effort": ReasoningEffort.MEDIUM,
        "timeout_seconds": 12.5,
        "pricing_quote": _quote(),
    }
    values[field_name] = value

    with pytest.raises(ValueError, match="safe identifier"):
        OpenAIResponseRoute(**values)  # type: ignore[arg-type]


def test_adapter_requires_both_injected_clocks() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = InMemoryProviderExchangeRecorder()
    calculator = SyntheticRecordedCostCalculator()

    with pytest.raises(TypeError):
        OpenAIResponsesAdapter(  # type: ignore[call-arg]
            client=client,
            route=_route(),
            recorder=recorder,
            cost_calculator=calculator,
        )


def test_evaluated_at_is_the_entry_clock_value() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    evaluated_at = NOW - timedelta(seconds=5)
    received_at = NOW
    times = iter((evaluated_at, received_at))
    calculator = _TrackingCalculator()
    adapter, _, _ = _custom_adapter(
        transport["body"],
        route=_route(),
        cost_calculator=calculator,
        clock=lambda: next(times),
    )

    result = adapter.execute(_request())

    assert result.pricing.evaluated_at == evaluated_at
    assert result.metadata.received_at == received_at
    assert calculator.calls == [
        {
            "usage": result.usage,
            "provider": "openai",
            "model_id": "raos-synthetic-model-v1",
            "quote": _route().pricing_quote,
            "evaluated_at": evaluated_at,
        }
    ]


@pytest.mark.parametrize(
    "mutation",
    (
        lambda body: body.update(status="queued"),
        lambda body: body.update(model="other-model"),
        lambda body: cast(dict[str, object], body["usage"]).update(total_tokens=99),
        lambda body: cast(
            dict[str, object],
            cast(dict[str, object], body["usage"])["input_tokens_details"],
        ).update(cached_tokens=999),
        lambda body: body.update(output=[]),
        lambda body: cast(list[object], body["output"]).append(
            copy.deepcopy(cast(list[object], body["output"])[0])
        ),
    ),
)
def test_malformed_response_fails_closed(
    mutation: Callable[[dict[str, object]], object],
) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    mutation(body)
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code in {
        ProviderErrorCode.MALFORMED_RESPONSE,
        ProviderErrorCode.ROUTE_MISMATCH,
    }
    assert recorder.record_calls == 0


def test_schema_validity_is_not_equated_with_output_validity() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = '{"label":"synthetic-pass","score":"not-an-integer"}'
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert recorder.record_calls == 0


def test_refusal_is_classified_without_parsing_refusal_text_as_json() -> None:
    transport = cast(dict[str, object], _fixture("refusal-completed.json")["transport"])
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["refusal"] = "{not-json and deliberately untrusted}"
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderRefusal)
    assert recorder.record_calls == 1


def test_incomplete_is_classified_without_parsing_partial_output() -> None:
    transport = cast(
        dict[str, object],
        _fixture("incomplete-max-output-tokens.json")["transport"],
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = "not-json"
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderIncomplete)
    assert result.reason is IncompleteReason.MAX_OUTPUT_TOKENS
    assert recorder.record_calls == 1


def test_adapter_does_not_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("environment access is forbidden")

    monkeypatch.setattr(os, "getenv", forbidden)
    monkeypatch.setattr(os.environ, "get", forbidden)
    adapter, _, recorder = _adapter(transport["body"])

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert recorder.record_calls == 1


def test_recorder_contract_failure_is_sanitized() -> None:
    class BrokenRecorder:
        def record(self, exchange: ProviderExchange) -> ArtifactRef:
            del exchange
            raise RuntimeError("SYNTHETIC_TEST_ONLY raw recorder diagnostic")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=BrokenRecorder(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert "SYNTHETIC_TEST_ONLY" not in str(captured.value)


def test_sdk_float_created_at_is_accepted() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    created_at = cast(int, body["created_at"])
    body["created_at"] = float(created_at)
    adapter, _, _ = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert result.metadata.response_created_at == datetime.fromtimestamp(
        float(created_at), tz=timezone.utc
    )


def test_reasoning_items_are_ignored_without_recording_summary() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    output = cast(list[object], body["output"])
    output.insert(
        0,
        {
            "id": "rs_synthetic_reasoning_001",
            "type": "reasoning",
            "summary": [
                {
                    "type": "summary_text",
                    "text": "SYNTHETIC_TEST_ONLY reasoning summary canary",
                }
            ],
        },
    )
    adapter, _, recorder = _adapter(body)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    recorded = recorder.read(result.raw_artifact)
    assert b"reasoning summary canary" not in recorded


def test_non_assistant_completed_message_fails_closed() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    message["role"] = "user"
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert recorder.record_calls == 0


def test_status_code_accessor_failure_is_sanitized() -> None:
    class ExplosiveStatusError(RuntimeError):
        @property
        def status_code(self) -> int:
            raise RuntimeError("SYNTHETIC_TEST_ONLY status getter diagnostic")

    adapter, _, recorder = _adapter(ExplosiveStatusError("synthetic"))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.UNKNOWN
    assert "SYNTHETIC_TEST_ONLY" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert recorder.record_calls == 0


def test_http_408_is_classified_as_timeout() -> None:
    adapter, _, recorder = _adapter(_StatusError(408))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.TIMEOUT
    assert captured.value.retryable is True
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    "error",
    (
        _StatusError(429),
        TimeoutError("SYNTHETIC_TEST_ONLY timeout diagnostic"),
        RuntimeError("SYNTHETIC_TEST_ONLY unknown diagnostic"),
    ),
)
def test_provider_errors_do_not_retain_exception_context(error: Exception) -> None:
    adapter, _, recorder = _adapter(error)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_malformed_output_does_not_retain_parser_context() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    message = cast(dict[str, object], cast(list[object], body["output"])[0])
    content = cast(dict[str, object], cast(list[object], message["content"])[0])
    content["text"] = "{not-json"
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_invalid_schema_does_not_retain_validator_context() -> None:
    request = _request()
    schema_bytes = b'{"type":7}'
    invalid_request = StructuredTaskRequest(
        task_code=request.task_code,
        model_route_version=request.model_route_version,
        prompt_version=request.prompt_version,
        input_artifact=request.input_artifact,
        output_schema=StructuredOutputSchema(
            name="invalid_schema_for_context_test",
            uri="urn:raos:synthetic:invalid-schema-context:v1",
            sha256=Sha256Digest.of(schema_bytes),
            document_bytes=schema_bytes,
        ),
        messages=request.messages,
        max_cost_jpy=request.max_cost_jpy,
        max_output_tokens=request.max_output_tokens,
        metadata=request.metadata,
    )
    adapter, client, recorder = _adapter(
        cast(dict[str, object], _fixture("success-structured.json")["transport"])[
            "body"
        ]
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(invalid_request)

    assert captured.value.stable_code is ProviderErrorCode.INVALID_SCHEMA
    assert captured.value.__context__ is None
    assert client.responses_resource.calls == []
    assert recorder.record_calls == 0


def test_recorder_failure_does_not_retain_exception_context() -> None:
    class BrokenRecorder:
        def record(self, exchange: ProviderExchange) -> ArtifactRef:
            del exchange
            raise RuntimeError("SYNTHETIC_TEST_ONLY raw recorder context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=BrokenRecorder(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__context__ is None


def test_pricing_failure_does_not_retain_exception_context() -> None:
    class BrokenCalculator:
        def calculate(
            self,
            *,
            usage: ProviderUsage,
            provider: str,
            model_id: str,
            quote: SyntheticPricingQuote,
            evaluated_at: datetime,
        ) -> PricingResult:
            del usage, provider, model_id, quote, evaluated_at
            raise RuntimeError("SYNTHETIC_TEST_ONLY raw pricing context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=BrokenCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISSING
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_invalid_recorder_result_fails_closed() -> None:
    class InvalidRecorder:
        def record(self, exchange: ProviderExchange) -> ArtifactRef:
            del exchange
            return cast(ArtifactRef, object())

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=InvalidRecorder(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__context__ is None


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("sha256", Sha256Digest("0" * 64)),
        ("byte_size", True),
        ("content_type", "text/plain"),
    ),
)
def test_forged_exact_artifact_ref_fails_closed(
    field_name: str,
    value: object,
) -> None:
    class ForgingRecorder:
        def __init__(self) -> None:
            self.calls = 0

        def record(self, exchange: ProviderExchange) -> ArtifactRef:
            self.calls += 1
            reference = ArtifactRef(
                artifact_id=UUID("44444444-4444-4444-8444-444444444444"),
                sha256=exchange.sha256,
                uri=f"file://recorded/{exchange.sha256.value}.json",
                content_type="application/json",
                byte_size=len(exchange.canonical_bytes),
            )
            object.__setattr__(reference, field_name, value)
            return reference

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = ForgingRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.calls == 1


@pytest.mark.parametrize(
    "outcome",
    (
        {"kind": "success", "unexpected": 1},
        {"kind": "refusal", "refusal": 1},
        {"kind": "incomplete", "reason": True},
        {"kind": True},
    ),
)
def test_recorded_exchange_rejects_schema_extension_and_wrong_value_types(
    outcome: dict[str, object],
) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    adapter, _, _ = _adapter(transport["body"])
    result = adapter.execute(_request())

    with pytest.raises(ProviderError) as captured:
        adapter_module._recorded_exchange(
            request=_request(),
            metadata=result.metadata,
            usage=result.usage,
            outcome=outcome,
        )

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE


@pytest.mark.parametrize("failure_kind", ("construction", "size"))
def test_canonical_record_failure_calls_no_recorder(
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    class BrokenCanonicalJsonObject:
        def __init__(self, value: object) -> None:
            del value
            if failure_kind == "construction":
                raise ValueError("SYNTHETIC_TEST_ONLY canonical diagnostic")

        def canonical_bytes(self) -> bytes:
            return b'{"value":"' + b"x" * (4 * 1024 * 1024) + b'"}'

    transport = cast(dict[str, object], _fixture("refusal-completed.json")["transport"])
    adapter, _, recorder = _adapter(transport["body"])
    monkeypatch.setattr(
        adapter_module,
        "CanonicalJsonObject",
        BrokenCanonicalJsonObject,
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RECORDER_FAILURE
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_invalid_pricing_result_fails_closed() -> None:
    class InvalidCalculator:
        def calculate(
            self,
            *,
            usage: ProviderUsage,
            provider: str,
            model_id: str,
            quote: SyntheticPricingQuote,
            evaluated_at: datetime,
        ) -> PricingResult:
            del usage, provider, model_id, quote, evaluated_at
            return cast(PricingResult, object())

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    client = _FakeClient(transport["body"])
    recorder = InMemoryProviderExchangeRecorder()
    ticks = iter((1_000_000_000, 1_012_000_000))
    adapter = OpenAIResponsesAdapter(
        client=client,
        route=_route(),
        recorder=recorder,
        cost_calculator=InvalidCalculator(),
        clock=lambda: NOW,
        monotonic_clock_ns=lambda: next(ticks),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


@pytest.mark.parametrize("failure_kind", ("provider", "malformed_output"))
def test_pricing_is_not_called_before_provider_outcome_validation(
    failure_kind: str,
) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    outcome: object
    if failure_kind == "provider":
        outcome = _StatusError(429)
    else:
        body = copy.deepcopy(cast(dict[str, object], transport["body"]))
        message = cast(dict[str, object], cast(list[object], body["output"])[0])
        content = cast(dict[str, object], cast(list[object], message["content"])[0])
        content["text"] = "{malformed"
        outcome = body
    calculator = _TrackingCalculator()
    adapter, _, recorder = _custom_adapter(
        outcome,
        route=_route(),
        cost_calculator=calculator,
    )

    with pytest.raises(ProviderError):
        adapter.execute(_request())

    assert calculator.calls == []
    assert recorder.record_calls == 0


def test_missing_quote_fails_before_calculator_and_recorder() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    calculator = _TrackingCalculator()
    adapter, _, recorder = _custom_adapter(
        transport["body"],
        route=replace(_route(), pricing_quote=None),
        cost_calculator=calculator,
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISSING
    assert calculator.calls == []
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    ("observed_at", "expires_at", "expected_success"),
    (
        (NOW, NOW + timedelta(seconds=1), True),
        (NOW - timedelta(days=1), NOW + timedelta(microseconds=1), True),
        (NOW + timedelta(microseconds=1), NOW + timedelta(days=1), False),
        (NOW - timedelta(days=1), NOW, False),
    ),
)
def test_quote_validity_interval_boundaries(
    observed_at: datetime,
    expires_at: datetime,
    expected_success: bool,
) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    quote = replace(
        _quote(),
        observed_at=observed_at,
        expires_at=expires_at,
    )
    calculator = _TrackingCalculator()
    adapter, _, recorder = _custom_adapter(
        transport["body"],
        route=replace(_route(), pricing_quote=quote),
        cost_calculator=calculator,
    )

    if expected_success:
        assert isinstance(adapter.execute(_request()), ProviderSuccess)
        assert len(calculator.calls) == 1
        assert recorder.record_calls == 1
    else:
        with pytest.raises(ProviderError) as captured:
            adapter.execute(_request())
        assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
        assert calculator.calls == []
        assert recorder.record_calls == 0


def test_tampered_quote_hash_fails_before_calculator_and_recorder() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    quote = _quote()
    object.__setattr__(quote, "input_per_million", Decimal("1"))
    calculator = _TrackingCalculator()
    adapter, _, recorder = _custom_adapter(
        transport["body"],
        route=replace(_route(), pricing_quote=quote),
        cost_calculator=calculator,
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
    assert calculator.calls == []
    assert recorder.record_calls == 0


def test_quote_model_mismatch_fails_before_calculator_and_recorder() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    quote = replace(_quote(), model_id="raos-other-model")
    calculator = _TrackingCalculator()
    adapter, _, recorder = _custom_adapter(
        transport["body"],
        route=replace(_route(), pricing_quote=quote),
        cost_calculator=calculator,
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
    assert calculator.calls == []
    assert recorder.record_calls == 0


def test_every_pricing_result_binding_is_compared_to_reference() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    usage = ProviderUsage(
        input_tokens=32,
        output_tokens=11,
        cached_input_tokens=8,
    )
    reference = calculate_synthetic_pricing_reference(
        usage=usage,
        provider="openai",
        model_id="raos-synthetic-model-v1",
        quote=_quote(),
        evaluated_at=NOW,
    )
    mismatches = (
        _pricing_result_with(reference, estimated_cost_jpy=0),
        _pricing_result_with(reference, provider_cost_native=Decimal("0")),
        _pricing_result_with(reference, native_currency="USD"),
        _pricing_result_with(reference, quote_id="different-quote"),
        _pricing_result_with(reference, quote_sha256=Sha256Digest("0" * 64)),
        _pricing_result_with(reference, model_id="raos-other-model"),
        _pricing_result_with(reference, usage_sha256=Sha256Digest("1" * 64)),
        _pricing_result_with(
            reference,
            evaluated_at=NOW + timedelta(microseconds=1),
        ),
    )

    for mismatch in mismatches:
        adapter, _, recorder = _custom_adapter(
            transport["body"],
            route=_route(),
            cost_calculator=_FixedCalculator(mismatch),
        )
        with pytest.raises(ProviderError) as captured:
            adapter.execute(_request())
        assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
        assert recorder.record_calls == 0


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("estimated_cost_jpy", True),
        ("provider", "other-provider"),
        ("calculation_sha256", Sha256Digest("0" * 64)),
    ),
)
def test_forged_exact_pricing_result_fails_closed(
    field_name: str,
    value: object,
) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    reference = calculate_synthetic_pricing_reference(
        usage=ProviderUsage(32, 11, 8),
        provider="openai",
        model_id="raos-synthetic-model-v1",
        quote=_quote(),
        evaluated_at=NOW,
    )
    object.__setattr__(reference, field_name, value)
    adapter, _, recorder = _custom_adapter(
        transport["body"],
        route=_route(),
        cost_calculator=_FixedCalculator(reference),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.PRICING_MISMATCH
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_response_conversion_accessor_failure_is_sanitized() -> None:
    class ExplosiveResponse:
        def __deepcopy__(self, memo: dict[int, object]) -> ExplosiveResponse:
            del memo
            return self

        @property
        def model_dump(self) -> object:
            raise RuntimeError("SYNTHETIC_TEST_ONLY response accessor context")

    adapter, _, recorder = _adapter(ExplosiveResponse())

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_request_id_accessor_failure_is_ignored() -> None:
    class SDKResponse:
        def __init__(self, body: dict[str, object]) -> None:
            self._body = body

        def __deepcopy__(self, memo: dict[int, object]) -> SDKResponse:
            del memo
            return self

        def model_dump(self, *, mode: str) -> dict[str, object]:
            assert mode == "json"
            return copy.deepcopy(self._body)

        @property
        def _request_id(self) -> str:
            raise RuntimeError("SYNTHETIC_TEST_ONLY request-id accessor context")

    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    response = SDKResponse(copy.deepcopy(cast(dict[str, object], transport["body"])))
    adapter, _, recorder = _adapter(response)

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert result.metadata.provider_request_id is None
    assert recorder.record_calls == 1


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    (
        (429, ProviderErrorCode.RATE_LIMIT, True),
        (408, ProviderErrorCode.TIMEOUT, True),
        (401, ProviderErrorCode.AUTHENTICATION, False),
        (403, ProviderErrorCode.PERMISSION, False),
        (400, ProviderErrorCode.INVALID_REQUEST, False),
        (404, ProviderErrorCode.INVALID_REQUEST, False),
        (409, ProviderErrorCode.INVALID_REQUEST, False),
        (422, ProviderErrorCode.INVALID_REQUEST, False),
        (502, ProviderErrorCode.UNAVAILABLE, True),
        (503, ProviderErrorCode.UNAVAILABLE, True),
        (504, ProviderErrorCode.UNAVAILABLE, True),
        (500, ProviderErrorCode.SERVER_ERROR, True),
        (599, ProviderErrorCode.SERVER_ERROR, True),
        (200, ProviderErrorCode.UNKNOWN, False),
        (418, ProviderErrorCode.UNKNOWN, False),
    ),
)
def test_closed_http_status_matrix(
    status: int,
    code: ProviderErrorCode,
    retryable: bool,
) -> None:
    adapter, _, recorder = _adapter(_StatusError(status))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is code
    assert captured.value.retryable is retryable
    assert captured.value.args == ()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    ("exception_type", "code", "retryable"),
    (
        (RateLimitError, ProviderErrorCode.RATE_LIMIT, True),
        (APITimeoutError, ProviderErrorCode.TIMEOUT, True),
        (TimeoutError, ProviderErrorCode.TIMEOUT, True),
        (AuthenticationError, ProviderErrorCode.AUTHENTICATION, False),
        (PermissionDeniedError, ProviderErrorCode.PERMISSION, False),
        (BadRequestError, ProviderErrorCode.INVALID_REQUEST, False),
        (ConflictError, ProviderErrorCode.INVALID_REQUEST, False),
        (NotFoundError, ProviderErrorCode.INVALID_REQUEST, False),
        (UnprocessableEntityError, ProviderErrorCode.INVALID_REQUEST, False),
        (APIConnectionError, ProviderErrorCode.UNAVAILABLE, True),
        (InternalServerError, ProviderErrorCode.SERVER_ERROR, True),
        (RuntimeError, ProviderErrorCode.UNKNOWN, False),
    ),
)
def test_closed_exception_class_matrix_without_status(
    exception_type: type[Exception],
    code: ProviderErrorCode,
    retryable: bool,
) -> None:
    adapter, _, recorder = _adapter(_sdk_subclass_error(exception_type))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is code
    assert captured.value.retryable is retryable
    assert captured.value.args == ()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


@pytest.mark.parametrize("status", (True, None, "429", 429.0))
def test_malformed_status_overrides_recognized_class_to_unknown(
    status: object,
) -> None:
    adapter, _, recorder = _adapter(_sdk_subclass_error(RateLimitError, status))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.UNKNOWN
    assert captured.value.retryable is False
    assert captured.value.args == ()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    ("exception_type", "status", "expected"),
    (
        (RateLimitError, 401, ProviderErrorCode.UNKNOWN),
        (RateLimitError, 429, ProviderErrorCode.RATE_LIMIT),
        (RuntimeError, 429, ProviderErrorCode.RATE_LIMIT),
        (RateLimitError, 418, ProviderErrorCode.UNKNOWN),
        (InternalServerError, 503, ProviderErrorCode.UNKNOWN),
    ),
)
def test_class_status_conflict_rule(
    exception_type: type[Exception],
    status: int,
    expected: ProviderErrorCode,
) -> None:
    adapter, _, _ = _adapter(_sdk_subclass_error(exception_type, status))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is expected


def test_recognized_class_with_hostile_status_getter_is_unknown() -> None:
    def status_getter(self: object) -> int:
        del self
        raise RuntimeError("SYNTHETIC_TEST_ONLY hostile status")

    error_type = type(
        "SyntheticHostileRateLimitError",
        (RateLimitError,),
        {"status_code": property(status_getter)},
    )
    error = cast(Exception, BaseException.__new__(error_type))
    Exception.__init__(error, "SYNTHETIC_TEST_ONLY provider diagnostic")
    adapter, _, _ = _adapter(error)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.UNKNOWN
    assert captured.value.retryable is False
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_provider_exception_subclass_name_is_not_trusted() -> None:
    adapter, _, _ = _adapter(_named_error("RateLimitError"))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.UNKNOWN
    assert captured.value.retryable is False


def test_actual_provider_exception_subclass_is_classified() -> None:
    adapter, _, _ = _adapter(_sdk_subclass_error(RateLimitError))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.RATE_LIMIT
    assert captured.value.retryable is True


def test_provider_neutral_client_error_is_reconstructed_and_sanitized() -> None:
    original = ProviderError(ProviderErrorCode.RATE_LIMIT)
    adapter, _, recorder = _adapter(original)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value is not original
    assert captured.value.stable_code is ProviderErrorCode.RATE_LIMIT
    assert captured.value.retryable is True
    assert captured.value.args == ()
    assert str(captured.value) == ""
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_malformed_provider_neutral_client_error_becomes_unknown() -> None:
    malformed = ProviderError(ProviderErrorCode.RATE_LIMIT)
    object.__setattr__(malformed, "_stable_code", "RATE_LIMIT")
    adapter, _, _ = _adapter(malformed)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.UNKNOWN
    assert captured.value.retryable is False
    assert captured.value.args == ()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None


def test_malformed_response_identifier_is_sanitized() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    body["id"] = "resp synthetic spaces"
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert captured.value.args == ()
    assert captured.value.__cause__ is None
    assert captured.value.__context__ is None
    assert recorder.record_calls == 0


def test_received_at_before_provider_created_at_is_malformed() -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    times = iter(
        (
            NOW,
            datetime(2026, 8, 5, 23, 59, 59, tzinfo=timezone.utc),
        )
    )
    adapter, client, recorder = _custom_adapter(
        transport["body"],
        route=_route(),
        cost_calculator=SyntheticRecordedCostCalculator(),
        clock=lambda: next(times),
    )

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.stable_code is ProviderErrorCode.MALFORMED_RESPONSE
    assert len(client.responses_resource.calls) == 1
    assert recorder.record_calls == 0
