"""Recorded contract tests for the ST-0703 OpenAI Responses adapter."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from decimal import Decimal
import json
from typing import cast
from uuid import UUID

import pytest

from conftest import REPOSITORY_ROOT
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
    IncompleteReason,
    MessageRole,
    ProviderIncomplete,
    ProviderRefusal,
    ProviderSuccess,
    RequestMetadata,
    Sha256Digest,
    StructuredInputMessage,
    StructuredOutputSchema,
    StructuredTaskRequest,
    SyntheticPricingQuote,
)
from raos.ports.ai_provider import (
    ProviderError,
    ProviderErrorCode,
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


class _TransportError(RuntimeError):
    def __init__(self, name: str, status_code: int | None = None) -> None:
        super().__init__("SYNTHETIC_TEST_ONLY provider diagnostic")
        self.status_code = status_code
        self._name = name

    @property
    def __class__(self):  # type: ignore[override]
        return type(self._name, (RuntimeError,), {})


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
        assert error.code.value == expected["provider_error_code"]
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
        recorded = json.loads(recorder.read(result.raw_artifact))
        assert recorded["request"]["request_sha256"] == _request().request_sha256.value
        assert "content" not in json.dumps(recorded["request"])
        assert "SYNTHETIC_TEST_ONLY refusal marker" not in json.dumps(recorded)

    assert client.options == [{"max_retries": 0, "timeout": 12.5}]
    assert client.responses_resource.calls == [fixture["expected_request"]]
    assert recorder.record_calls == expected["recorder_calls"]


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

    assert captured.value.code is expected
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

    assert captured.value.code is ProviderErrorCode.ROUTE_MISMATCH
    assert client.options == []
    assert client.responses_resource.calls == []
    assert recorder.record_calls == 0


@pytest.mark.parametrize(
    "mutation",
    (
        lambda body: body.update(status="queued"),
        lambda body: body.update(model="other-model"),
        lambda body: cast(dict[str, object], body["usage"]).update(total_tokens=99),
        lambda body: cast(dict[str, object], body["usage"])[
            "input_tokens_details"
        ].update(cached_tokens=999),
        lambda body: body.update(output=[]),
        lambda body: cast(list[object], body["output"]).append(
            copy.deepcopy(cast(list[object], body["output"])[0])
        ),
    ),
)
def test_malformed_response_fails_closed(mutation) -> None:
    transport = cast(
        dict[str, object], _fixture("success-structured.json")["transport"]
    )
    body = copy.deepcopy(cast(dict[str, object], transport["body"]))
    mutation(body)
    adapter, _, recorder = _adapter(body)

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code in {
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

    assert captured.value.code is ProviderErrorCode.MALFORMED_RESPONSE
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
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-read")
    adapter, _, recorder = _adapter(transport["body"])

    result = adapter.execute(_request())

    assert isinstance(result, ProviderSuccess)
    assert "must-not-be-read" not in recorder.read(result.raw_artifact).decode("utf-8")


def test_recorder_contract_failure_is_sanitized() -> None:
    class BrokenRecorder:
        def record(self, exchange):
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

    assert captured.value.code is ProviderErrorCode.RECORDER_FAILURE
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

    assert captured.value.code is ProviderErrorCode.MALFORMED_RESPONSE
    assert recorder.record_calls == 0


def test_status_code_accessor_failure_is_sanitized() -> None:
    class ExplosiveStatusError(RuntimeError):
        @property
        def status_code(self) -> int:
            raise RuntimeError("SYNTHETIC_TEST_ONLY status getter diagnostic")

    adapter, _, recorder = _adapter(ExplosiveStatusError("synthetic"))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.UNKNOWN
    assert "SYNTHETIC_TEST_ONLY" not in str(captured.value)
    assert captured.value.__cause__ is None
    assert recorder.record_calls == 0


def test_http_408_is_classified_as_timeout() -> None:
    adapter, _, recorder = _adapter(_StatusError(408))

    with pytest.raises(ProviderError) as captured:
        adapter.execute(_request())

    assert captured.value.code is ProviderErrorCode.TIMEOUT
    assert captured.value.retryable is True
    assert recorder.record_calls == 0
