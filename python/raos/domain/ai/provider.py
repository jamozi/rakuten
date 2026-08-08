"""Immutable provider-neutral values for structured model execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import NoReturn, cast
from urllib.parse import urlsplit
from uuid import UUID


type JsonValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple["JsonValue", ...]
    | Mapping[str, "JsonValue"]
)

_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SCHEMA_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")
_MAX_JSON_VISITS = 100_000
_MAX_JSON_DEPTH = 100
_MAX_CANONICAL_JSON_BYTES = 4 * 1024 * 1024
_MAX_MESSAGE_CONTENT_BYTES = 1_000_000
_MAX_DECIMAL_SIGNIFICANT_DIGITS = 38
_MIN_DECIMAL_EXPONENT = -18
_MAX_DECIMAL_EXPONENT = 18
_MAX_SIGNED_BIGINT = (1 << 63) - 1
_MAX_STRUCTURED_MESSAGES = 128
_MAX_OUTPUT_TOKENS = 1_000_000


def _require_text(value: object, *, field_name: str, maximum: int = 256) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > maximum
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError(f"{field_name} must be bounded trimmed printable text")
    return value


def _require_identifier(value: object, *, field_name: str) -> str:
    text = _require_text(value, field_name=field_name)
    if _SAFE_IDENTIFIER.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be a safe identifier")
    return text


def _require_message_content(value: object) -> str:
    if type(value) is not str or not value:
        raise ValueError("content must be non-empty exact text")
    for character in value:
        code_point = ord(character)
        if (
            (code_point < 0x20 and code_point not in {0x09, 0x0A})
            or 0x7F <= code_point <= 0x9F
            or 0xD800 <= code_point <= 0xDFFF
        ):
            raise ValueError("content contains a forbidden control character")
    try:
        content_bytes = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ValueError("content must be valid UTF-8 text") from None
    if len(content_bytes) > _MAX_MESSAGE_CONTENT_BYTES:
        raise ValueError("content exceeds the UTF-8 byte limit")
    return value


def _require_exact_integer(
    value: object,
    *,
    field_name: str,
    minimum: int = 0,
    maximum: int = _MAX_SIGNED_BIGINT,
) -> int:
    if type(value) is not int or value < minimum or value > maximum:
        raise ValueError(
            f"{field_name} must be an exact integer from {minimum} to {maximum}"
        )
    return value


def _canonical_decimal_snapshot(value: object, *, field_name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value < 0:
        raise ValueError(f"{field_name} must be a finite nonnegative Decimal")
    components = value.as_tuple()
    exponent = cast(int, components.exponent)
    digits = components.digits
    if (
        len(digits) > _MAX_DECIMAL_SIGNIFICANT_DIGITS
        or exponent < _MIN_DECIMAL_EXPONENT
        or exponent > _MAX_DECIMAL_EXPONENT
    ):
        raise ValueError(f"{field_name} exceeds Decimal precision or exponent limits")
    if not any(digits):
        return Decimal(0)
    canonical_digits = list(digits)
    while canonical_digits[-1] == 0:
        canonical_digits.pop()
        exponent += 1
    if exponent > _MAX_DECIMAL_EXPONENT:
        raise ValueError(f"{field_name} exceeds Decimal precision or exponent limits")
    return Decimal((0, tuple(canonical_digits), exponent))


def _canonical_decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _require_utc(value: object, *, field_name: str) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError(f"{field_name} must be an aware UTC datetime")
    offset_lookup_failed = False
    offset = None
    try:
        offset = value.utcoffset()
    except Exception:
        offset_lookup_failed = True
    if offset_lookup_failed or offset != timezone.utc.utcoffset(None):
        raise ValueError(f"{field_name} must be an aware UTC datetime")
    return value.replace(tzinfo=timezone.utc)


def _require_uuid(value: object, *, field_name: str) -> UUID:
    if type(value) is not UUID:
        raise ValueError(f"{field_name} must be an exact UUID")
    return value


def _freeze_json(value: object, *, field_name: str) -> JsonValue:
    visits = 0
    active: set[int] = set()

    def freeze(item: object, depth: int) -> JsonValue:
        nonlocal visits
        visits += 1
        if visits > _MAX_JSON_VISITS or depth > _MAX_JSON_DEPTH:
            raise ValueError(f"{field_name} exceeds the JSON graph limit")
        if item is None or type(item) in {bool, int, str}:
            return cast(None | bool | int | str, item)
        if type(item) is float:
            number = item
            if not math.isfinite(number):
                raise ValueError(f"{field_name} cannot contain non-finite numbers")
            return number
        if not isinstance(item, (Mapping, list, tuple)):
            raise ValueError(f"{field_name} contains a non-JSON value")
        container = cast(
            Mapping[object, object] | list[object] | tuple[object, ...], item
        )
        identity = id(container)
        if identity in active:
            raise ValueError(f"{field_name} cannot contain a cycle")
        active.add(identity)
        try:
            if isinstance(container, Mapping):
                if not all(type(key) is str for key in container):
                    raise ValueError(f"{field_name} requires exact string keys")
                return MappingProxyType(
                    {
                        cast(str, key): freeze(child, depth + 1)
                        for key, child in container.items()
                    }
                )
            return tuple(freeze(child, depth + 1) for child in container)
        finally:
            active.remove(identity)

    return freeze(value, 0)


def _thaw_json(value: JsonValue) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(child) for child in value]
    return value


def _canonical_json_bytes(value: JsonValue) -> bytes:
    serialization_failed = False
    content = b""
    try:
        content = json.dumps(
            _thaw_json(value),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        serialization_failed = True
    if serialization_failed:
        raise ValueError("value must be canonical UTF-8 JSON") from None
    if len(content) > _MAX_CANONICAL_JSON_BYTES:
        content = b""
        raise ValueError("canonical JSON exceeds the 4 MiB byte limit")
    return content


def _reject_json_constant(value: str) -> NoReturn:
    del value
    raise ValueError("non-finite JSON number")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object member")
        result[key] = value
    return result


def _parse_json_object(content: bytes, *, field_name: str) -> Mapping[str, object]:
    if type(content) is not bytes:
        raise ValueError(f"{field_name} must be exact bytes")
    if not content or len(content) > _MAX_CANONICAL_JSON_BYTES:
        raise ValueError(f"{field_name} must be bounded non-empty JSON bytes")
    parse_failed = False
    value: object | None = None
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ):
        parse_failed = True
    if parse_failed:
        content = b""
        value = None
        raise ValueError("content must be strict JSON") from None
    if not isinstance(value, dict) or not all(type(key) is str for key in value):
        raise ValueError(f"{field_name} must be a JSON object")
    return cast(Mapping[str, object], value)


@dataclass(frozen=True, slots=True)
class Sha256Digest:
    """One exact lowercase SHA-256 digest."""

    value: str

    def __post_init__(self) -> None:
        if (
            type(self.value) is not str
            or len(self.value) != 64
            or any(character not in "0123456789abcdef" for character in self.value)
        ):
            raise ValueError("value must be a lowercase SHA-256 digest")

    @classmethod
    def of(cls, content: bytes) -> Sha256Digest:
        if type(content) is not bytes:
            raise ValueError("content must be exact bytes")
        return cls(hashlib.sha256(content).hexdigest())

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, repr=False)
class CanonicalJsonObject:
    """Deeply frozen JSON object with deterministic UTF-8 serialization."""

    value: Mapping[str, JsonValue] = field(repr=False)
    _canonical_bytes_snapshot: bytes = field(init=False, repr=False, compare=False)

    def __init__(self, value: Mapping[str, object]) -> None:
        frozen = _freeze_json(value, field_name="value")
        if not isinstance(frozen, Mapping):
            raise ValueError("value must be a JSON object")
        canonical_bytes = _canonical_json_bytes(cast(JsonValue, frozen))
        object.__setattr__(self, "value", frozen)
        object.__setattr__(self, "_canonical_bytes_snapshot", canonical_bytes)

    @classmethod
    def from_bytes(cls, content: bytes) -> CanonicalJsonObject:
        if type(content) is not bytes:
            raise ValueError("content must be exact bytes")
        return cls(_parse_json_object(content, field_name="content"))

    def canonical_bytes(self) -> bytes:
        return self._canonical_bytes_snapshot

    def __repr__(self) -> str:
        return "CanonicalJsonObject(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArtifactRef:
    """Provider-neutral reference to an immutable recorded artifact."""

    artifact_id: UUID
    sha256: Sha256Digest
    uri: str | None = None
    content_type: str | None = None
    byte_size: int | None = None

    def __post_init__(self) -> None:
        _require_uuid(self.artifact_id, field_name="artifact_id")
        if type(self.sha256) is not Sha256Digest:
            raise ValueError("sha256 must be an exact Sha256Digest")
        if self.uri is not None:
            uri = _require_text(self.uri, field_name="uri", maximum=2048)
            if not uri.startswith(("s3://", "file://")):
                raise ValueError("uri must use the s3 or file scheme")
            try:
                parsed_uri = urlsplit(uri)
            except ValueError:
                raise ValueError("uri must be a valid s3 or file URI") from None
            if (
                parsed_uri.username is not None
                or parsed_uri.password is not None
                or parsed_uri.query
                or parsed_uri.fragment
                or "?" in uri
                or "#" in uri
            ):
                raise ValueError(
                    "uri must not contain userinfo, a query, or a fragment"
                )
        if self.content_type is not None:
            _require_text(self.content_type, field_name="content_type", maximum=120)
        if self.byte_size is not None:
            _require_exact_integer(self.byte_size, field_name="byte_size")

    def __repr__(self) -> str:
        return (
            "ArtifactRef("
            f"artifact_id={self.artifact_id!r}, sha256={self.sha256!r}, "
            f"uri=<redacted>, content_type={self.content_type!r}, "
            f"byte_size={self.byte_size!r})"
        )


class MessageRole(str, Enum):
    DEVELOPER = "developer"
    USER = "user"


@dataclass(frozen=True, slots=True, repr=False)
class StructuredInputMessage:
    """One provider-neutral input message whose content is display-redacted."""

    role: MessageRole
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.role) is not MessageRole:
            raise ValueError("role must be an exact MessageRole")
        _require_message_content(self.content)

    def __repr__(self) -> str:
        return f"StructuredInputMessage(role={self.role!r}, content=<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class StructuredOutputSchema:
    """Exact JSON Schema bytes and their hash-bound parsed object."""

    name: str
    uri: str
    sha256: Sha256Digest
    document_bytes: bytes = field(repr=False)
    document: CanonicalJsonObject = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.name) is not str or _SCHEMA_NAME.fullmatch(self.name) is None:
            raise ValueError("name must be a bounded provider-safe schema name")
        _require_text(self.uri, field_name="uri", maximum=2048)
        if type(self.sha256) is not Sha256Digest:
            raise ValueError("sha256 must be an exact Sha256Digest")
        if type(self.document_bytes) is not bytes:
            raise ValueError("document_bytes must be exact bytes")
        snapshot = bytes(self.document_bytes)
        if Sha256Digest.of(snapshot) != self.sha256:
            raise ValueError("document_bytes do not match sha256")
        object.__setattr__(self, "document_bytes", snapshot)
        object.__setattr__(self, "document", CanonicalJsonObject.from_bytes(snapshot))

    def __repr__(self) -> str:
        return (
            "StructuredOutputSchema("
            f"name={self.name!r}, uri={self.uri!r}, sha256={self.sha256!r}, "
            "document_bytes=<redacted>, document=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class RequestMetadata:
    correlation_id: UUID
    job_id: UUID
    environment: str

    def __post_init__(self) -> None:
        _require_uuid(self.correlation_id, field_name="correlation_id")
        _require_uuid(self.job_id, field_name="job_id")
        _require_identifier(self.environment, field_name="environment")


@dataclass(frozen=True, slots=True, repr=False)
class StructuredTaskRequest:
    """Provider-neutral request whose digest covers its exact material."""

    task_code: str
    model_route_version: str
    prompt_version: str
    input_artifact: ArtifactRef
    output_schema: StructuredOutputSchema
    messages: tuple[StructuredInputMessage, ...] = field(repr=False)
    max_cost_jpy: int
    max_output_tokens: int
    metadata: RequestMetadata
    source_packet_version_id: UUID | None = None
    request_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.task_code, field_name="task_code")
        _require_identifier(self.model_route_version, field_name="model_route_version")
        _require_identifier(self.prompt_version, field_name="prompt_version")
        if type(self.input_artifact) is not ArtifactRef:
            raise ValueError("input_artifact must be an exact ArtifactRef")
        if type(self.output_schema) is not StructuredOutputSchema:
            raise ValueError("output_schema must be an exact StructuredOutputSchema")
        if type(self.messages) is not tuple or not self.messages:
            raise ValueError("messages must be a non-empty exact tuple")
        if len(self.messages) > _MAX_STRUCTURED_MESSAGES:
            raise ValueError("messages cannot exceed 128 items")
        if any(
            type(message) is not StructuredInputMessage for message in self.messages
        ):
            raise ValueError("messages require exact StructuredInputMessage values")
        if self.messages[0].role is not MessageRole.DEVELOPER:
            raise ValueError("the first message must be a developer message")
        if not any(message.role is MessageRole.USER for message in self.messages):
            raise ValueError("messages require at least one user message")
        _require_exact_integer(self.max_cost_jpy, field_name="max_cost_jpy", minimum=1)
        _require_exact_integer(
            self.max_output_tokens,
            field_name="max_output_tokens",
            minimum=1,
            maximum=_MAX_OUTPUT_TOKENS,
        )
        if type(self.metadata) is not RequestMetadata:
            raise ValueError("metadata must be exact RequestMetadata")
        if self.source_packet_version_id is not None:
            _require_uuid(
                self.source_packet_version_id, field_name="source_packet_version_id"
            )
        object.__setattr__(
            self, "request_sha256", Sha256Digest.of(self.canonical_bytes())
        )

    def canonical_bytes(self) -> bytes:
        document: dict[str, object] = {
            "task_code": self.task_code,
            "model_route_version": self.model_route_version,
            "prompt_version": self.prompt_version,
            "input_artifact": {
                "artifact_id": str(self.input_artifact.artifact_id),
                "sha256": self.input_artifact.sha256.value,
                "uri": self.input_artifact.uri,
                "content_type": self.input_artifact.content_type,
                "byte_size": self.input_artifact.byte_size,
            },
            "output_schema": {
                "name": self.output_schema.name,
                "uri": self.output_schema.uri,
                "sha256": self.output_schema.sha256.value,
            },
            "messages": [
                {"role": message.role.value, "content": message.content}
                for message in self.messages
            ],
            "max_cost_jpy": self.max_cost_jpy,
            "max_output_tokens": self.max_output_tokens,
            "metadata": {
                "correlation_id": str(self.metadata.correlation_id),
                "job_id": str(self.metadata.job_id),
                "environment": self.metadata.environment,
            },
            "source_packet_version_id": (
                str(self.source_packet_version_id)
                if self.source_packet_version_id is not None
                else None
            ),
        }
        return CanonicalJsonObject(document).canonical_bytes()

    def __repr__(self) -> str:
        return (
            "StructuredTaskRequest("
            f"task_code={self.task_code!r}, "
            f"model_route_version={self.model_route_version!r}, "
            f"prompt_version={self.prompt_version!r}, "
            f"request_sha256={self.request_sha256!r}, messages=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class ProviderUsage:
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int

    def __post_init__(self) -> None:
        _require_exact_integer(self.input_tokens, field_name="input_tokens")
        _require_exact_integer(self.output_tokens, field_name="output_tokens")
        _require_exact_integer(
            self.cached_input_tokens, field_name="cached_input_tokens"
        )
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached_input_tokens cannot exceed input_tokens")


@dataclass(frozen=True, slots=True)
class SyntheticPricingQuote:
    """Explicitly synthetic immutable quote for recorded fixture execution."""

    quote_id: str
    provider: str
    model_id: str
    native_currency: str
    input_per_million: Decimal
    cached_input_per_million: Decimal
    output_per_million: Decimal
    jpy_per_native_unit: Decimal
    observed_at: datetime
    quote_sha256: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        _require_identifier(self.quote_id, field_name="quote_id")
        _require_identifier(self.provider, field_name="provider")
        _require_identifier(self.model_id, field_name="model_id")
        if (
            type(self.native_currency) is not str
            or _CURRENCY.fullmatch(self.native_currency) is None
        ):
            raise ValueError("native_currency must be an ISO-style currency code")
        for field_name in (
            "input_per_million",
            "cached_input_per_million",
            "output_per_million",
            "jpy_per_native_unit",
        ):
            snapshot = _canonical_decimal_snapshot(
                getattr(self, field_name), field_name=field_name
            )
            object.__setattr__(self, field_name, snapshot)
        if self.jpy_per_native_unit <= 0:
            raise ValueError("jpy_per_native_unit must be positive")
        observed_at = _require_utc(self.observed_at, field_name="observed_at")
        object.__setattr__(self, "observed_at", observed_at)
        material = CanonicalJsonObject(
            {
                "kind": "SYNTHETIC_RECORDED_FIXTURE",
                "quote_id": self.quote_id,
                "provider": self.provider,
                "model_id": self.model_id,
                "native_currency": self.native_currency,
                "input_per_million": _canonical_decimal_text(self.input_per_million),
                "cached_input_per_million": _canonical_decimal_text(
                    self.cached_input_per_million
                ),
                "output_per_million": _canonical_decimal_text(self.output_per_million),
                "jpy_per_native_unit": _canonical_decimal_text(
                    self.jpy_per_native_unit
                ),
                "observed_at": self.observed_at.isoformat(),
            }
        ).canonical_bytes()
        object.__setattr__(self, "quote_sha256", Sha256Digest.of(material))


@dataclass(frozen=True, slots=True)
class PricingResult:
    estimated_cost_jpy: int
    provider_cost_native: Decimal
    native_currency: str
    quote_id: str
    quote_sha256: Sha256Digest

    def __post_init__(self) -> None:
        _require_exact_integer(self.estimated_cost_jpy, field_name="estimated_cost_jpy")
        provider_cost_native = _canonical_decimal_snapshot(
            self.provider_cost_native, field_name="provider_cost_native"
        )
        object.__setattr__(self, "provider_cost_native", provider_cost_native)
        if (
            type(self.native_currency) is not str
            or _CURRENCY.fullmatch(self.native_currency) is None
        ):
            raise ValueError("native_currency must be an ISO-style currency code")
        _require_identifier(self.quote_id, field_name="quote_id")
        if type(self.quote_sha256) is not Sha256Digest:
            raise ValueError("quote_sha256 must be an exact Sha256Digest")


@dataclass(frozen=True, slots=True)
class ResolvedProviderMetadata:
    provider: str
    requested_model_id: str
    resolved_model_id: str
    response_id: str
    provider_request_id: str | None
    response_status: str
    response_created_at: datetime
    received_at: datetime
    latency_ms: int

    def __post_init__(self) -> None:
        for field_name in (
            "provider",
            "requested_model_id",
            "resolved_model_id",
            "response_id",
            "response_status",
        ):
            _require_identifier(getattr(self, field_name), field_name=field_name)
        if self.provider_request_id is not None:
            _require_identifier(
                self.provider_request_id, field_name="provider_request_id"
            )
        response_created_at = _require_utc(
            self.response_created_at, field_name="response_created_at"
        )
        received_at = _require_utc(self.received_at, field_name="received_at")
        object.__setattr__(self, "response_created_at", response_created_at)
        object.__setattr__(self, "received_at", received_at)
        _require_exact_integer(self.latency_ms, field_name="latency_ms")


class IncompleteReason(str, Enum):
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    CONTENT_FILTER = "content_filter"


def _validate_recorded_result(
    *,
    metadata: ResolvedProviderMetadata,
    usage: ProviderUsage,
    pricing: PricingResult,
    request_sha256: Sha256Digest,
    response_sha256: Sha256Digest,
    raw_artifact: ArtifactRef,
) -> None:
    if type(metadata) is not ResolvedProviderMetadata:
        raise ValueError("metadata must be exact ResolvedProviderMetadata")
    if type(usage) is not ProviderUsage:
        raise ValueError("usage must be exact ProviderUsage")
    if type(pricing) is not PricingResult:
        raise ValueError("pricing must be exact PricingResult")
    if type(request_sha256) is not Sha256Digest:
        raise ValueError("request_sha256 must be exact Sha256Digest")
    if type(response_sha256) is not Sha256Digest:
        raise ValueError("response_sha256 must be exact Sha256Digest")
    if type(raw_artifact) is not ArtifactRef:
        raise ValueError("raw_artifact must be exact ArtifactRef")
    if raw_artifact.sha256 != response_sha256:
        raise ValueError("raw_artifact and response_sha256 must match")


@dataclass(frozen=True, slots=True, repr=False)
class ProviderSuccess:
    output: CanonicalJsonObject = field(repr=False)
    metadata: ResolvedProviderMetadata
    usage: ProviderUsage
    pricing: PricingResult
    request_sha256: Sha256Digest
    response_sha256: Sha256Digest
    raw_artifact: ArtifactRef

    def __post_init__(self) -> None:
        if type(self.output) is not CanonicalJsonObject:
            raise ValueError("output must be exact CanonicalJsonObject")
        _validate_recorded_result(
            metadata=self.metadata,
            usage=self.usage,
            pricing=self.pricing,
            request_sha256=self.request_sha256,
            response_sha256=self.response_sha256,
            raw_artifact=self.raw_artifact,
        )
        if self.metadata.response_status != "completed":
            raise ValueError("ProviderSuccess requires response_status completed")

    def __repr__(self) -> str:
        return (
            "ProviderSuccess(output=<redacted>, "
            f"metadata={self.metadata!r}, usage={self.usage!r}, "
            f"pricing={self.pricing!r}, request_sha256={self.request_sha256!r}, "
            f"response_sha256={self.response_sha256!r}, "
            f"raw_artifact={self.raw_artifact!r})"
        )


@dataclass(frozen=True, slots=True)
class ProviderRefusal:
    refusal_code: str
    metadata: ResolvedProviderMetadata
    usage: ProviderUsage
    pricing: PricingResult
    request_sha256: Sha256Digest
    response_sha256: Sha256Digest
    raw_artifact: ArtifactRef

    def __post_init__(self) -> None:
        if self.refusal_code != "AI-PRV-005":
            raise ValueError("refusal_code must be AI-PRV-005")
        _validate_recorded_result(
            metadata=self.metadata,
            usage=self.usage,
            pricing=self.pricing,
            request_sha256=self.request_sha256,
            response_sha256=self.response_sha256,
            raw_artifact=self.raw_artifact,
        )
        if self.metadata.response_status != "completed":
            raise ValueError("ProviderRefusal requires response_status completed")


@dataclass(frozen=True, slots=True)
class ProviderIncomplete:
    reason: IncompleteReason
    metadata: ResolvedProviderMetadata
    usage: ProviderUsage
    pricing: PricingResult
    request_sha256: Sha256Digest
    response_sha256: Sha256Digest
    raw_artifact: ArtifactRef

    def __post_init__(self) -> None:
        if type(self.reason) is not IncompleteReason:
            raise ValueError("reason must be exact IncompleteReason")
        _validate_recorded_result(
            metadata=self.metadata,
            usage=self.usage,
            pricing=self.pricing,
            request_sha256=self.request_sha256,
            response_sha256=self.response_sha256,
            raw_artifact=self.raw_artifact,
        )
        if self.metadata.response_status != "incomplete":
            raise ValueError("ProviderIncomplete requires response_status incomplete")


type ProviderResult = ProviderSuccess | ProviderRefusal | ProviderIncomplete


__all__ = [
    "ArtifactRef",
    "CanonicalJsonObject",
    "IncompleteReason",
    "JsonValue",
    "MessageRole",
    "PricingResult",
    "ProviderIncomplete",
    "ProviderRefusal",
    "ProviderResult",
    "ProviderSuccess",
    "ProviderUsage",
    "RequestMetadata",
    "ResolvedProviderMetadata",
    "Sha256Digest",
    "StructuredInputMessage",
    "StructuredOutputSchema",
    "StructuredTaskRequest",
    "SyntheticPricingQuote",
]
