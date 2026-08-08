"""Recorded OpenAI Responses adapter with a provider-neutral inward boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
from time import monotonic_ns
from typing import Protocol, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)

from raos.domain.ai.provider import (
    ArtifactRef,
    CanonicalJsonObject,
    IncompleteReason,
    PricingResult,
    ProviderIncomplete,
    ProviderRefusal,
    ProviderResult,
    ProviderSuccess,
    ProviderUsage,
    ResolvedProviderMetadata,
    Sha256Digest,
    StructuredTaskRequest,
    SyntheticPricingQuote,
)
from raos.ports.ai_provider import (
    ProviderError,
    ProviderErrorCode,
    ProviderExchange,
    ProviderExchangeRecorder,
    RecordedCostCalculator,
)


_MAX_RESPONSE_GRAPH_VISITS = 100_000
_MAX_RESPONSE_GRAPH_DEPTH = 100
_MAX_PROVIDER_IDENTIFIER = 256
_MAX_SIGNED_BIGINT = (1 << 63) - 1


class ReasoningEffort(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class _ResponsesResource(Protocol):
    def create(self, **kwargs: object) -> object: ...


class _ConfiguredClient(Protocol):
    @property
    def responses(self) -> _ResponsesResource: ...


class _OpenAIClient(Protocol):
    def with_options(
        self, *, max_retries: int, timeout: float
    ) -> _ConfiguredClient: ...


@dataclass(frozen=True, slots=True)
class OpenAIResponseRoute:
    """One explicit recorded route; it does not perform model selection."""

    route_version: str
    model_id: str
    reasoning_effort: ReasoningEffort
    timeout_seconds: float
    pricing_quote: SyntheticPricingQuote

    def __post_init__(self) -> None:
        for field_name in ("route_version", "model_id"):
            value = getattr(self, field_name)
            if (
                type(value) is not str
                or not value
                or value != value.strip()
                or len(value) > _MAX_PROVIDER_IDENTIFIER
                or any(not character.isprintable() for character in value)
            ):
                raise ValueError(f"{field_name} must be bounded printable text")
        if type(self.reasoning_effort) is not ReasoningEffort:
            raise ValueError("reasoning_effort must be an exact ReasoningEffort")
        if (
            type(self.timeout_seconds) is not float
            or not math.isfinite(self.timeout_seconds)
            or not 0.1 <= self.timeout_seconds <= 600.0
        ):
            raise ValueError("timeout_seconds must be a float from 0.1 to 600")
        if type(self.pricing_quote) is not SyntheticPricingQuote:
            raise ValueError("pricing_quote must be an exact SyntheticPricingQuote")
        if self.pricing_quote.provider != "openai":
            raise ValueError("pricing_quote provider must be openai")
        if self.pricing_quote.model_id != self.model_id:
            raise ValueError("pricing_quote model_id must match the route")


class OpenAIResponsesAdapter:
    """Execute one strict Responses request with no retry, tool, or secret access."""

    def __init__(
        self,
        *,
        client: _OpenAIClient,
        route: OpenAIResponseRoute,
        recorder: ProviderExchangeRecorder,
        cost_calculator: RecordedCostCalculator,
        clock: Callable[[], datetime] | None = None,
        monotonic_clock_ns: Callable[[], int] | None = None,
    ) -> None:
        if type(route) is not OpenAIResponseRoute:
            raise TypeError("route must be an exact OpenAIResponseRoute")
        if not isinstance(recorder, ProviderExchangeRecorder):
            raise TypeError("recorder must implement ProviderExchangeRecorder")
        if not isinstance(cost_calculator, RecordedCostCalculator):
            raise TypeError("cost_calculator must implement RecordedCostCalculator")
        self._client = client
        self._route = route
        self._recorder = recorder
        self._cost_calculator = cost_calculator
        self._clock = clock if clock is not None else _utc_now
        self._monotonic_ns = (
            monotonic_clock_ns if monotonic_clock_ns is not None else monotonic_ns
        )

    def execute(self, request: StructuredTaskRequest) -> ProviderResult:
        if type(request) is not StructuredTaskRequest:
            raise TypeError("request must be an exact StructuredTaskRequest")
        if request.model_route_version != self._route.route_version:
            raise ProviderError(ProviderErrorCode.ROUTE_MISMATCH)
        payload = self._request_payload(request)
        started_ns = self._safe_monotonic_ns()
        try:
            configured_client = self._client.with_options(
                max_retries=0,
                timeout=self._route.timeout_seconds,
            )
            response = configured_client.responses.create(**payload)
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError(_classify_provider_error(exc)) from None
        received_at = self._safe_clock()
        finished_ns = self._safe_monotonic_ns()
        response_document = _response_mapping(response)
        return self._classify_response(
            request=request,
            response=response_document,
            received_at=received_at,
            latency_ms=_latency_ms(started_ns, finished_ns),
            provider_request_id=_provider_request_id(response),
        )

    def _request_payload(self, request: StructuredTaskRequest) -> dict[str, object]:
        try:
            schema_document = json.loads(
                request.output_schema.document_bytes.decode("utf-8", errors="strict")
            )
            Draft202012Validator.check_schema(schema_document)
        except UnicodeDecodeError, json.JSONDecodeError, SchemaError, TypeError:
            raise ProviderError(ProviderErrorCode.INVALID_SCHEMA) from None
        return {
            "model": self._route.model_id,
            "input": [
                {"role": message.role.value, "content": message.content}
                for message in request.messages
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.output_schema.name,
                    "strict": True,
                    "schema": schema_document,
                }
            },
            "store": False,
            "tools": [],
            "max_output_tokens": request.max_output_tokens,
            "reasoning": {"effort": self._route.reasoning_effort.value},
        }

    def _classify_response(
        self,
        *,
        request: StructuredTaskRequest,
        response: Mapping[str, object],
        received_at: datetime,
        latency_ms: int,
        provider_request_id: str | None,
    ) -> ProviderResult:
        status = _required_identifier(response.get("status"), field="status")
        if status not in {"completed", "incomplete"}:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        response_id = _required_identifier(response.get("id"), field="id")
        resolved_model = _required_identifier(response.get("model"), field="model")
        if resolved_model != self._route.model_id:
            raise ProviderError(ProviderErrorCode.ROUTE_MISMATCH)
        created_at = _unix_timestamp(response.get("created_at"))
        usage = _usage(response.get("usage"))
        pricing = self._calculate_pricing(usage)
        metadata = ResolvedProviderMetadata(
            provider="openai",
            requested_model_id=self._route.model_id,
            resolved_model_id=resolved_model,
            response_id=response_id,
            provider_request_id=provider_request_id,
            response_status=status,
            response_created_at=created_at,
            received_at=received_at,
            latency_ms=latency_ms,
        )

        if status == "incomplete":
            reason = _incomplete_reason(response.get("incomplete_details"))
            exchange, response_digest = _recorded_exchange(
                request=request,
                metadata=metadata,
                usage=usage,
                outcome={"kind": "incomplete", "reason": reason.value},
            )
            artifact = self._record(exchange)
            return ProviderIncomplete(
                reason=reason,
                metadata=metadata,
                usage=usage,
                pricing=pricing,
                request_sha256=request.request_sha256,
                response_sha256=response_digest,
                raw_artifact=artifact,
            )

        content_kind, content = _completed_content(response.get("output"))
        if content_kind == "refusal":
            exchange, response_digest = _recorded_exchange(
                request=request,
                metadata=metadata,
                usage=usage,
                outcome={"kind": "refusal", "refusal": True},
            )
            artifact = self._record(exchange)
            return ProviderRefusal(
                refusal_code="AI-PRV-005",
                metadata=metadata,
                usage=usage,
                pricing=pricing,
                request_sha256=request.request_sha256,
                response_sha256=response_digest,
                raw_artifact=artifact,
            )

        output = _structured_output(content, request)
        exchange, response_digest = _recorded_exchange(
            request=request,
            metadata=metadata,
            usage=usage,
            outcome={
                "kind": "success",
                "output": json.loads(output.canonical_bytes()),
            },
        )
        artifact = self._record(exchange)
        return ProviderSuccess(
            output=output,
            metadata=metadata,
            usage=usage,
            pricing=pricing,
            request_sha256=request.request_sha256,
            response_sha256=response_digest,
            raw_artifact=artifact,
        )

    def _record(self, exchange: ProviderExchange) -> ArtifactRef:
        try:
            artifact = self._recorder.record(exchange)
        except Exception:
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE) from None
        if (
            artifact.sha256 != exchange.sha256
            or artifact.byte_size != len(exchange.canonical_bytes)
            or artifact.content_type != "application/json"
        ):
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
        return artifact

    def _calculate_pricing(self, usage: ProviderUsage) -> PricingResult:
        try:
            pricing = self._cost_calculator.calculate(
                usage,
                self._route.pricing_quote,
            )
        except Exception:
            raise ProviderError(ProviderErrorCode.PRICING_MISSING) from None
        if (
            pricing.quote_id != self._route.pricing_quote.quote_id
            or pricing.quote_sha256 != self._route.pricing_quote.quote_sha256
            or pricing.native_currency != self._route.pricing_quote.native_currency
        ):
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        return pricing

    def _safe_clock(self) -> datetime:
        try:
            value = self._clock()
            if type(value) is not datetime or value.tzinfo is None:
                raise ValueError
            if value.utcoffset() != timezone.utc.utcoffset(None):
                raise ValueError
            return value.replace(tzinfo=timezone.utc)
        except Exception:
            raise ProviderError(ProviderErrorCode.UNKNOWN) from None

    def _safe_monotonic_ns(self) -> int:
        try:
            value = self._monotonic_ns()
        except Exception:
            raise ProviderError(ProviderErrorCode.UNKNOWN) from None
        if type(value) is not int or value < 0:
            raise ProviderError(ProviderErrorCode.UNKNOWN)
        return value


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _response_mapping(response: object) -> Mapping[str, object]:
    value: object
    if isinstance(response, Mapping):
        value = response
    else:
        model_dump = getattr(response, "model_dump", None)
        to_dict = getattr(response, "to_dict", None)
        try:
            if callable(model_dump):
                value = model_dump(mode="json")
            elif callable(to_dict):
                value = to_dict()
            else:
                raise TypeError
        except Exception:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None
    return _bounded_mapping(value)


def _bounded_mapping(value: object) -> Mapping[str, object]:
    visits = 0
    active: set[int] = set()

    def validate(item: object, depth: int) -> None:
        nonlocal visits
        visits += 1
        if visits > _MAX_RESPONSE_GRAPH_VISITS or depth > _MAX_RESPONSE_GRAPH_DEPTH:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        if item is None or type(item) in {bool, int, str}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
            return
        if not isinstance(item, (Mapping, list, tuple)):
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        identity = id(item)
        if identity in active:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        active.add(identity)
        try:
            if isinstance(item, Mapping):
                if not all(type(key) is str for key in item):
                    raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
                for child in item.values():
                    validate(child, depth + 1)
            else:
                for child in item:
                    validate(child, depth + 1)
        finally:
            active.remove(identity)

    validate(value, 0)
    if not isinstance(value, Mapping):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(Mapping[str, object], value)


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(Mapping[str, object], value)


def _required_sequence(value: object) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(Sequence[object], value)


def _required_identifier(value: object, *, field: str) -> str:
    del field
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or len(value) > _MAX_PROVIDER_IDENTIFIER
        or any(not character.isprintable() for character in value)
    ):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return value


def _exact_nonnegative_integer(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_SIGNED_BIGINT:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return value


def _usage(value: object) -> ProviderUsage:
    document = _required_mapping(value)
    input_tokens = _exact_nonnegative_integer(document.get("input_tokens"))
    output_tokens = _exact_nonnegative_integer(document.get("output_tokens"))
    total_tokens = _exact_nonnegative_integer(document.get("total_tokens"))
    details = _required_mapping(document.get("input_tokens_details"))
    cached_tokens = _exact_nonnegative_integer(details.get("cached_tokens"))
    if total_tokens != input_tokens + output_tokens:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    try:
        return ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
        )
    except ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None


def _unix_timestamp(value: object) -> datetime:
    timestamp: int | float
    if type(value) is int:
        timestamp = value
    elif type(value) is float and math.isfinite(value):
        timestamp = value
    else:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    if not 0 <= timestamp <= _MAX_SIGNED_BIGINT:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    try:
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except OverflowError, OSError, ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None


def _incomplete_reason(value: object) -> IncompleteReason:
    details = _required_mapping(value)
    reason = details.get("reason")
    try:
        return IncompleteReason(reason)
    except TypeError, ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None


def _completed_content(value: object) -> tuple[str, str]:
    output = _required_sequence(value)
    message: Mapping[str, object] | None = None
    for item in output:
        candidate = _required_mapping(item)
        kind = candidate.get("type")
        if kind == "reasoning":
            continue
        if kind != "message" or message is not None:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        message = candidate
    if (
        message is None
        or message.get("role") != "assistant"
        or message.get("status") != "completed"
    ):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    content_items = _required_sequence(message.get("content"))
    if len(content_items) != 1:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    content = _required_mapping(content_items[0])
    kind = content.get("type")
    if kind == "refusal":
        refusal = content.get("refusal")
        if type(refusal) is not str or not refusal:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        return "refusal", ""
    if kind == "output_text":
        text = content.get("text")
        if type(text) is not str or not text:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        return "output_text", text
    raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)


def _structured_output(
    content: str,
    request: StructuredTaskRequest,
) -> CanonicalJsonObject:
    try:
        output = CanonicalJsonObject.from_bytes(
            content.encode("utf-8", errors="strict")
        )
    except UnicodeEncodeError, ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None
    try:
        schema = json.loads(request.output_schema.document_bytes)
        Draft202012Validator(schema).validate(json.loads(output.canonical_bytes()))
    except SchemaError:
        raise ProviderError(ProviderErrorCode.INVALID_SCHEMA) from None
    except ValidationError, json.JSONDecodeError, TypeError, ValueError:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE) from None
    return output


def _recorded_exchange(
    *,
    request: StructuredTaskRequest,
    metadata: ResolvedProviderMetadata,
    usage: ProviderUsage,
    outcome: Mapping[str, object],
) -> tuple[ProviderExchange, Sha256Digest]:
    document = CanonicalJsonObject(
        {
            "provider": "openai",
            "request": {
                "request_sha256": request.request_sha256.value,
                "task_code": request.task_code,
                "model_route_version": request.model_route_version,
                "prompt_version": request.prompt_version,
                "input_artifact_sha256": request.input_artifact.sha256.value,
                "output_schema_sha256": request.output_schema.sha256.value,
            },
            "response": {
                "response_id": metadata.response_id,
                "requested_model_id": metadata.requested_model_id,
                "resolved_model_id": metadata.resolved_model_id,
                "status": metadata.response_status,
                "created_at": metadata.response_created_at.isoformat(),
                "received_at": metadata.received_at.isoformat(),
                "latency_ms": metadata.latency_ms,
                "usage": {
                    "input_tokens": usage.input_tokens,
                    "cached_input_tokens": usage.cached_input_tokens,
                    "output_tokens": usage.output_tokens,
                },
                "outcome": dict(outcome),
            },
        }
    )
    content = document.canonical_bytes()
    digest = Sha256Digest.of(content)
    return ProviderExchange(canonical_bytes=content, sha256=digest), digest


def _provider_request_id(response: object) -> str | None:
    value = getattr(response, "_request_id", None)
    if value is None:
        return None
    try:
        return _required_identifier(value, field="provider_request_id")
    except ProviderError:
        return None


def _latency_ms(started_ns: int, finished_ns: int) -> int:
    if finished_ns < started_ns:
        raise ProviderError(ProviderErrorCode.UNKNOWN)
    value = (finished_ns - started_ns) // 1_000_000
    if value > _MAX_SIGNED_BIGINT:
        raise ProviderError(ProviderErrorCode.UNKNOWN)
    return value


def _classify_provider_error(error: Exception) -> ProviderErrorCode:
    name = type(error).__name__
    try:
        candidate_status = getattr(error, "status_code", None)
    except Exception:
        return ProviderErrorCode.UNKNOWN
    status: int | None
    if type(candidate_status) is int:
        status = candidate_status
    else:
        status = None
    if status == 429 or name == "RateLimitError":
        return ProviderErrorCode.RATE_LIMIT
    if status == 408 or name in {"APITimeoutError", "TimeoutError"}:
        return ProviderErrorCode.TIMEOUT
    if status == 401 or name == "AuthenticationError":
        return ProviderErrorCode.AUTHENTICATION
    if status == 403 or name == "PermissionDeniedError":
        return ProviderErrorCode.PERMISSION
    if status in {400, 404, 409, 422} or name in {
        "BadRequestError",
        "ConflictError",
        "NotFoundError",
        "UnprocessableEntityError",
    }:
        return ProviderErrorCode.INVALID_REQUEST
    if status in {502, 503, 504} or name == "APIConnectionError":
        return ProviderErrorCode.UNAVAILABLE
    if (status is not None and status >= 500) or name == "InternalServerError":
        return ProviderErrorCode.SERVER_ERROR
    return ProviderErrorCode.UNKNOWN


__all__ = [
    "OpenAIResponseRoute",
    "OpenAIResponsesAdapter",
    "ReasoningEffort",
]
