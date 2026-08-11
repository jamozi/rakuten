"""Recorded OpenAI Responses adapter with a provider-neutral inward boundary."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import json
import math
import re
from typing import Protocol, cast

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from jsonschema.exceptions import SchemaError  # type: ignore[import-untyped]
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

from raos.domain.ai.provider import (
    ArtifactRef,
    calculate_synthetic_pricing_reference,
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
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_MISSING_STATUS = object()
_PROVIDER_CLASS_CODES: tuple[tuple[type[BaseException], ProviderErrorCode], ...] = (
    (RateLimitError, ProviderErrorCode.RATE_LIMIT),
    (APITimeoutError, ProviderErrorCode.TIMEOUT),
    (TimeoutError, ProviderErrorCode.TIMEOUT),
    (AuthenticationError, ProviderErrorCode.AUTHENTICATION),
    (PermissionDeniedError, ProviderErrorCode.PERMISSION),
    (BadRequestError, ProviderErrorCode.INVALID_REQUEST),
    (ConflictError, ProviderErrorCode.INVALID_REQUEST),
    (NotFoundError, ProviderErrorCode.INVALID_REQUEST),
    (UnprocessableEntityError, ProviderErrorCode.INVALID_REQUEST),
    (APIConnectionError, ProviderErrorCode.UNAVAILABLE),
    (InternalServerError, ProviderErrorCode.SERVER_ERROR),
)


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


class _SchemaValidator(Protocol):
    def validate(self, instance: object) -> None: ...


@dataclass(frozen=True, slots=True)
class OpenAIResponseRoute:
    """One explicit recorded route; it does not perform model selection."""

    route_version: str
    model_id: str
    reasoning_effort: ReasoningEffort
    timeout_seconds: float
    pricing_quote: SyntheticPricingQuote | None

    def __post_init__(self) -> None:
        for field_name in ("route_version", "model_id"):
            value = getattr(self, field_name)
            if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be a bounded safe identifier")
        if type(self.reasoning_effort) is not ReasoningEffort:
            raise ValueError("reasoning_effort must be an exact ReasoningEffort")
        if (
            type(self.timeout_seconds) is not float
            or not math.isfinite(self.timeout_seconds)
            or not 0.1 <= self.timeout_seconds <= 600.0
        ):
            raise ValueError("timeout_seconds must be a float from 0.1 to 600")
        if (
            self.pricing_quote is not None
            and type(self.pricing_quote) is not SyntheticPricingQuote
        ):
            raise ValueError(
                "pricing_quote must be an exact SyntheticPricingQuote or None"
            )


class OpenAIResponsesAdapter:
    """Execute one strict Responses request with no retry, tool, or secret access."""

    def __init__(
        self,
        *,
        client: _OpenAIClient,
        route: OpenAIResponseRoute,
        recorder: ProviderExchangeRecorder,
        cost_calculator: RecordedCostCalculator,
        clock: Callable[[], datetime],
        monotonic_clock_ns: Callable[[], int],
    ) -> None:
        if type(route) is not OpenAIResponseRoute:
            raise TypeError("route must be an exact OpenAIResponseRoute")
        if not isinstance(cast(object, recorder), ProviderExchangeRecorder):
            raise TypeError("recorder must implement ProviderExchangeRecorder")
        if not isinstance(cast(object, cost_calculator), RecordedCostCalculator):
            raise TypeError("cost_calculator must implement RecordedCostCalculator")
        if not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(monotonic_clock_ns):
            raise TypeError("monotonic_clock_ns must be callable")
        self._client = client
        self._route = route
        self._recorder = recorder
        self._cost_calculator = cost_calculator
        self._clock = clock
        self._monotonic_ns = monotonic_clock_ns

    def execute(self, request: StructuredTaskRequest) -> ProviderResult:
        if type(request) is not StructuredTaskRequest:
            raise TypeError("request must be an exact StructuredTaskRequest")
        failure: ProviderErrorCode | None = None
        result: ProviderResult | None = None
        try:
            result = self._execute(request)
        except ProviderError as exc:
            if (
                type(exc) is ProviderError
                and type(exc.stable_code) is ProviderErrorCode
            ):
                failure = exc.stable_code
            else:
                failure = ProviderErrorCode.UNKNOWN
        except Exception:
            failure = ProviderErrorCode.UNKNOWN
        if failure is not None:
            raise ProviderError(failure) from None
        if result is None:
            raise ProviderError(ProviderErrorCode.UNKNOWN) from None
        return result

    def _execute(self, request: StructuredTaskRequest) -> ProviderResult:
        evaluated_at = self._safe_clock()
        if request.model_route_version != self._route.route_version:
            raise ProviderError(ProviderErrorCode.ROUTE_MISMATCH)
        payload = self._request_payload(request)
        started_ns = self._safe_monotonic_ns()
        response: object = None
        provider_failure: ProviderErrorCode | None = None
        try:
            configured_client = self._client.with_options(
                max_retries=0,
                timeout=self._route.timeout_seconds,
            )
            response = configured_client.responses.create(**payload)
        except Exception as exc:
            if type(exc) is ProviderError:
                provider_failure = exc.stable_code
            else:
                provider_failure = _classify_provider_error(exc)
        if provider_failure is not None:
            raise ProviderError(provider_failure)
        received_at = self._safe_clock()
        finished_ns = self._safe_monotonic_ns()
        response_document = _response_mapping(response)
        return self._classify_response(
            request=request,
            response=response_document,
            evaluated_at=evaluated_at,
            received_at=received_at,
            latency_ms=_latency_ms(started_ns, finished_ns),
            provider_request_id=_provider_request_id(response),
        )

    def _request_payload(self, request: StructuredTaskRequest) -> dict[str, object]:
        schema_document: object = None
        schema_invalid = False
        try:
            schema_document = json.loads(
                request.output_schema.document_bytes.decode("utf-8", errors="strict")
            )
            Draft202012Validator.check_schema(
                cast(bool | Mapping[str, object], schema_document)
            )
        except Exception:
            schema_invalid = True
        if schema_invalid:
            raise ProviderError(ProviderErrorCode.INVALID_SCHEMA)
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
        evaluated_at: datetime,
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
        metadata: ResolvedProviderMetadata | None = None
        try:
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
        except Exception:
            metadata = None
        if metadata is None:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        incomplete_reason: IncompleteReason | None = None
        output: CanonicalJsonObject | None = None
        outcome: dict[str, object]
        if status == "incomplete":
            incomplete_reason = _incomplete_reason(response.get("incomplete_details"))
            outcome = {"kind": "incomplete", "reason": incomplete_reason.value}
        else:
            content_kind, content = _completed_content(response.get("output"))
            if content_kind == "refusal":
                outcome = {"kind": "refusal", "refusal": True}
            else:
                output = _structured_output(content, request)
                outcome = {"kind": "success"}

        pricing = self._calculate_pricing(
            usage=usage,
            model_id=resolved_model,
            evaluated_at=evaluated_at,
        )
        exchange, response_digest = _recorded_exchange(
            request=request,
            metadata=metadata,
            usage=usage,
            outcome=outcome,
        )
        artifact = self._record(exchange)
        if incomplete_reason is not None:
            return ProviderIncomplete(
                reason=incomplete_reason,
                metadata=metadata,
                usage=usage,
                pricing=pricing,
                request_sha256=request.request_sha256,
                response_sha256=response_digest,
                raw_artifact=artifact,
            )
        if output is None:
            return ProviderRefusal(
                refusal_code="AI-PRV-005",
                metadata=metadata,
                usage=usage,
                pricing=pricing,
                request_sha256=request.request_sha256,
                response_sha256=response_digest,
                raw_artifact=artifact,
            )
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
        artifact: object = None
        recorder_failed = False
        try:
            artifact = self._recorder.record(exchange)
        except Exception:
            recorder_failed = True
        if recorder_failed or type(artifact) is not ArtifactRef:
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
        artifact_ref = artifact
        artifact_snapshot: ArtifactRef | None = None
        try:
            artifact_snapshot = ArtifactRef(
                artifact_id=artifact_ref.artifact_id,
                sha256=Sha256Digest(artifact_ref.sha256.value),
                uri=artifact_ref.uri,
                content_type=artifact_ref.content_type,
                byte_size=artifact_ref.byte_size,
            )
        except Exception:
            artifact_snapshot = None
        if artifact_snapshot is None or (
            artifact_snapshot.sha256.value != exchange.sha256.value
            or artifact_snapshot.byte_size != len(exchange.canonical_bytes)
            or artifact_snapshot.content_type != "application/json"
        ):
            raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
        return artifact_snapshot

    def _calculate_pricing(
        self,
        *,
        usage: ProviderUsage,
        model_id: str,
        evaluated_at: datetime,
    ) -> PricingResult:
        quote = self._route.pricing_quote
        if quote is None:
            raise ProviderError(ProviderErrorCode.PRICING_MISSING)
        if type(quote) is not SyntheticPricingQuote:
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        reference: PricingResult | None = None
        try:
            reference = calculate_synthetic_pricing_reference(
                usage=usage,
                provider="openai",
                model_id=model_id,
                quote=quote,
                evaluated_at=evaluated_at,
            )
        except Exception:
            reference = None
        if reference is None:
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        pricing: object = None
        calculator_failed = False
        try:
            pricing = self._cost_calculator.calculate(
                usage=usage,
                provider="openai",
                model_id=model_id,
                quote=quote,
                evaluated_at=evaluated_at,
            )
        except Exception:
            calculator_failed = True
        if calculator_failed:
            raise ProviderError(ProviderErrorCode.PRICING_MISSING)
        if type(pricing) is not PricingResult:
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        pricing_result = pricing
        pricing_snapshot: PricingResult | None = None
        pricing_matches = False
        try:
            if _pricing_results_match_exactly(pricing_result, reference):
                pricing_snapshot = PricingResult(
                    estimated_cost_jpy=pricing_result.estimated_cost_jpy,
                    provider_cost_native=pricing_result.provider_cost_native,
                    native_currency=pricing_result.native_currency,
                    quote_id=pricing_result.quote_id,
                    quote_sha256=Sha256Digest(pricing_result.quote_sha256.value),
                    provider=pricing_result.provider,
                    model_id=pricing_result.model_id,
                    usage_sha256=Sha256Digest(pricing_result.usage_sha256.value),
                    evaluated_at=pricing_result.evaluated_at,
                    calculation_sha256=Sha256Digest(
                        pricing_result.calculation_sha256.value
                    ),
                )
                pricing_matches = _pricing_results_match_exactly(
                    pricing_snapshot, reference
                )
        except Exception:
            pricing_snapshot = None
            pricing_matches = False
        if pricing_snapshot is None or not pricing_matches:
            raise ProviderError(ProviderErrorCode.PRICING_MISMATCH)
        return pricing_snapshot

    def _safe_clock(self) -> datetime:
        normalized: datetime | None = None
        try:
            value = self._clock()
            if (
                type(value) is datetime
                and value.tzinfo is not None
                and value.utcoffset() == timezone.utc.utcoffset(None)
            ):
                normalized = value.replace(tzinfo=timezone.utc)
        except Exception:
            normalized = None
        if normalized is None:
            raise ProviderError(ProviderErrorCode.UNKNOWN)
        return normalized

    def _safe_monotonic_ns(self) -> int:
        value: object = None
        clock_failed = False
        try:
            value = self._monotonic_ns()
        except Exception:
            clock_failed = True
        if clock_failed or type(value) is not int or value < 0:
            raise ProviderError(ProviderErrorCode.UNKNOWN)
        return value


def _response_mapping(response: object) -> Mapping[str, object]:
    value: object = None
    conversion_failed = False
    try:
        if isinstance(response, Mapping):
            value = cast(Mapping[object, object], response)
        else:
            model_dump = getattr(response, "model_dump", None)
            to_dict = getattr(response, "to_dict", None)
            if callable(model_dump):
                value = model_dump(mode="json")
            elif callable(to_dict):
                value = to_dict()
            else:
                conversion_failed = True
    except Exception:
        conversion_failed = True
    if conversion_failed:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)

    bounded: Mapping[str, object] | None = None
    try:
        bounded = _bounded_mapping(value)
    except Exception:
        bounded = None
    if bounded is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return bounded


def _bounded_mapping(value: object) -> Mapping[str, object]:
    visits = 0
    active: set[int] = set()

    def snapshot(item: object, depth: int) -> object:
        nonlocal visits
        visits += 1
        if visits > _MAX_RESPONSE_GRAPH_VISITS or depth > _MAX_RESPONSE_GRAPH_DEPTH:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        if item is None or type(item) in {bool, int, str}:
            return item
        if type(item) is float:
            if not math.isfinite(item):
                raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
            return item
        if not isinstance(item, (Mapping, list, tuple)):
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        container = cast(
            Mapping[object, object] | list[object] | tuple[object, ...], item
        )
        identity = id(container)
        if identity in active:
            raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
        active.add(identity)
        try:
            if isinstance(container, Mapping):
                result: dict[str, object] = {}
                for key, child in container.items():
                    if type(key) is not str:
                        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
                    result[key] = snapshot(child, depth + 1)
                return result
            return [snapshot(child, depth + 1) for child in container]
        finally:
            active.remove(identity)

    frozen = snapshot(value, 0)
    if type(frozen) is not dict:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(dict[str, object], frozen)


def _required_mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    mapping = cast(Mapping[object, object], value)
    if not all(type(key) is str for key in mapping):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(Mapping[str, object], mapping)


def _required_sequence(value: object) -> Sequence[object]:
    if not isinstance(value, (list, tuple)):
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return cast(Sequence[object], value)


def _required_identifier(value: object, *, field: str) -> str:
    del field
    if type(value) is not str or _SAFE_IDENTIFIER.fullmatch(value) is None:
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
    usage: ProviderUsage | None = None
    try:
        usage = ProviderUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_tokens,
        )
    except Exception:
        usage = None
    if usage is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return usage


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
    converted: datetime | None = None
    try:
        converted = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except Exception:
        converted = None
    if converted is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return converted


def _incomplete_reason(value: object) -> IncompleteReason:
    details = _required_mapping(value)
    reason = details.get("reason")
    parsed: IncompleteReason | None = None
    try:
        parsed = IncompleteReason(reason)
    except Exception:
        parsed = None
    if parsed is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)
    return parsed


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
    output: CanonicalJsonObject | None = None
    try:
        output = CanonicalJsonObject.from_bytes(
            content.encode("utf-8", errors="strict")
        )
    except Exception:
        output = None
    if output is None:
        raise ProviderError(ProviderErrorCode.MALFORMED_RESPONSE)

    validation_failure: ProviderErrorCode | None = None
    try:
        schema = cast(
            bool | Mapping[str, object],
            json.loads(request.output_schema.document_bytes),
        )
        validator = cast(_SchemaValidator, Draft202012Validator(schema))
        validator.validate(cast(object, json.loads(output.canonical_bytes())))
    except SchemaError:
        validation_failure = ProviderErrorCode.INVALID_SCHEMA
    except Exception:
        validation_failure = ProviderErrorCode.MALFORMED_RESPONSE
    if validation_failure is not None:
        raise ProviderError(validation_failure)
    return output


def _recorded_exchange(
    *,
    request: StructuredTaskRequest,
    metadata: ResolvedProviderMetadata,
    usage: ProviderUsage,
    outcome: Mapping[str, object],
) -> tuple[ProviderExchange, Sha256Digest]:
    exchange: ProviderExchange | None = None
    digest: Sha256Digest | None = None
    try:
        if (
            type(request) is not StructuredTaskRequest
            or type(metadata) is not ResolvedProviderMetadata
            or type(usage) is not ProviderUsage
            or type(outcome) is not dict
        ):
            raise ValueError("record inputs must be exact value objects")
        exact_outcome = dict(cast(Mapping[str, object], outcome))
        kind = exact_outcome.get("kind")
        valid_success = (
            set(exact_outcome) == {"kind"} and type(kind) is str and kind == "success"
        )
        refusal = exact_outcome.get("refusal")
        valid_refusal = (
            set(exact_outcome) == {"kind", "refusal"}
            and type(kind) is str
            and kind == "refusal"
            and type(refusal) is bool
            and refusal is True
        )
        reason = exact_outcome.get("reason")
        valid_incomplete = (
            set(exact_outcome) == {"kind", "reason"}
            and type(kind) is str
            and kind == "incomplete"
            and type(reason) is str
            and reason in {"max_output_tokens", "content_filter"}
        )
        if not (valid_success or valid_refusal or valid_incomplete):
            raise ValueError("record outcome is outside the closed schema")
        if (
            kind in {"success", "refusal"} and metadata.response_status != "completed"
        ) or (kind == "incomplete" and metadata.response_status != "incomplete"):
            raise ValueError("record outcome does not match response status")
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
                    "outcome": exact_outcome,
                },
            }
        )
        content = document.canonical_bytes()
        digest = Sha256Digest.of(content)
        exchange = ProviderExchange(canonical_bytes=content, sha256=digest)
    except Exception:
        exchange = None
        digest = None
    if exchange is None or digest is None:
        raise ProviderError(ProviderErrorCode.RECORDER_FAILURE)
    return exchange, digest


def _pricing_results_match_exactly(
    left: PricingResult,
    right: PricingResult,
) -> bool:
    """Compare validated result fields without Python's bool/int coercion."""

    return (
        type(left) is PricingResult
        and type(right) is PricingResult
        and type(left.estimated_cost_jpy) is int
        and type(right.estimated_cost_jpy) is int
        and left.estimated_cost_jpy == right.estimated_cost_jpy
        and type(left.provider_cost_native) is type(right.provider_cost_native)
        and left.provider_cost_native.as_tuple()
        == right.provider_cost_native.as_tuple()
        and type(left.native_currency) is str
        and type(right.native_currency) is str
        and left.native_currency == right.native_currency
        and type(left.quote_id) is str
        and type(right.quote_id) is str
        and left.quote_id == right.quote_id
        and type(left.quote_sha256) is Sha256Digest
        and type(right.quote_sha256) is Sha256Digest
        and left.quote_sha256.value == right.quote_sha256.value
        and type(left.provider) is str
        and type(right.provider) is str
        and left.provider == right.provider
        and type(left.model_id) is str
        and type(right.model_id) is str
        and left.model_id == right.model_id
        and type(left.usage_sha256) is Sha256Digest
        and type(right.usage_sha256) is Sha256Digest
        and left.usage_sha256.value == right.usage_sha256.value
        and type(left.evaluated_at) is datetime
        and type(right.evaluated_at) is datetime
        and left.evaluated_at.tzinfo is timezone.utc
        and right.evaluated_at.tzinfo is timezone.utc
        and left.evaluated_at == right.evaluated_at
        and type(left.calculation_sha256) is Sha256Digest
        and type(right.calculation_sha256) is Sha256Digest
        and left.calculation_sha256.value == right.calculation_sha256.value
    )


def _provider_request_id(response: object) -> str | None:
    try:
        value = getattr(response, "_request_id", None)
    except Exception:
        return None
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
    error_type = type(error)
    class_code = next(
        (
            code
            for exception_type, code in _PROVIDER_CLASS_CODES
            if issubclass(error_type, exception_type)
        ),
        None,
    )
    try:
        candidate_status = getattr(error, "status_code", _MISSING_STATUS)
    except Exception:
        return ProviderErrorCode.UNKNOWN
    if candidate_status is _MISSING_STATUS:
        return class_code or ProviderErrorCode.UNKNOWN
    if type(candidate_status) is not int:
        return ProviderErrorCode.UNKNOWN
    status_code = _classify_http_status(candidate_status)
    if status_code is None:
        return ProviderErrorCode.UNKNOWN
    if class_code is not None and class_code is not status_code:
        return ProviderErrorCode.UNKNOWN
    return status_code


def _classify_http_status(status: int) -> ProviderErrorCode | None:
    if status == 429:
        return ProviderErrorCode.RATE_LIMIT
    if status == 408:
        return ProviderErrorCode.TIMEOUT
    if status == 401:
        return ProviderErrorCode.AUTHENTICATION
    if status == 403:
        return ProviderErrorCode.PERMISSION
    if status in {400, 404, 409, 422}:
        return ProviderErrorCode.INVALID_REQUEST
    if status in {502, 503, 504}:
        return ProviderErrorCode.UNAVAILABLE
    if status >= 500:
        return ProviderErrorCode.SERVER_ERROR
    return None
