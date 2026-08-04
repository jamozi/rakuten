"""Provider-neutral runtime configuration without implicit I/O.

The mapping loader accepts only the fixed ``RAOS_`` namespace.  Reading the
process environment is a separate, explicit operation; this module never reads
files, contacts a provider, or snapshots environment state at import time.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable, Mapping
from enum import Enum
from types import MappingProxyType
from typing import Annotated, Literal, NoReturn, Self, SupportsIndex, cast, final
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    GetCoreSchemaHandler,
    GetJsonSchemaHandler,
    Field,
    StringConstraints,
    ValidationError,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.config import ExtraValues
from pydantic_core import core_schema
from pydantic.json_schema import JsonSchemaValue


_ENVIRONMENT_KEY = "RAOS_ENVIRONMENT"
_SERVICE_NAME_KEY = "RAOS_SERVICE_NAME"
_LOG_LEVEL_KEY = "RAOS_LOG_LEVEL"
_SECRET_REFERENCES_KEY = "RAOS_SECRET_REFERENCES"
_ALLOWED_ENVIRONMENT_KEYS = frozenset(
    {
        _ENVIRONMENT_KEY,
        _SERVICE_NAME_KEY,
        _LOG_LEVEL_KEY,
        _SECRET_REFERENCES_KEY,
    }
)
_MODEL_FIELDS = frozenset(
    {
        "schema_version",
        "environment",
        "service_name",
        "log_level",
        "secret_references",
    }
)

_MAX_SOURCE_ENTRIES = 4_096
_MAX_SECRET_REFERENCES = 64
_MAX_SECRET_REFERENCES_JSON_BYTES = 16_384
_MAX_MODEL_JSON_BYTES = 32_768
_MAX_SECRET_REFERENCE_CHARS = 512
_MAX_REQUIRED_SECRET_ALIASES = 64

_SERVICE_NAME_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_SECRET_ALIAS_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_SECRET_TARGET_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*\Z")
_SERVICE_NAME_PYDANTIC_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_SECRET_REFERENCE_PYDANTIC_PATTERN = (
    r"^secret://[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:/[.]*[A-Za-z0-9_-][A-Za-z0-9._-]*)*$"
)
_SERVICE_NAME_SCHEMA_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$(?![\s\S])"
_SECRET_ALIAS_SCHEMA_PATTERN = r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$(?![\s\S])"
_SECRET_REFERENCE_SCHEMA_PATTERN = (
    r"^secret://[A-Za-z0-9][A-Za-z0-9._-]*"
    r"(?:/[.]*[A-Za-z0-9_-][A-Za-z0-9._-]*)*$(?![\s\S])"
)
_REDACTED_SECRET_REFERENCE = "<redacted-secret-reference>"
_INVALID_MODEL_FIELD = "__invalid_configuration__"
_INVALID_SECRET_ALIAS = "__invalid_secret_alias__"

DiagnosticValue = int | str | list[str]
ServiceName = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=63,
        pattern=_SERVICE_NAME_PYDANTIC_PATTERN,
    ),
]
SecretAlias = Annotated[
    str,
    StringConstraints(
        strict=True,
        min_length=1,
        max_length=64,
    ),
]


class RuntimeEnvironment(str, Enum):
    """The exact runtime environments recognized by RAOS configuration."""

    ENV_DEV = "ENV-DEV"
    CI = "ENV-CI"
    INTEGRATION = "ENV-INTEGRATION"
    STAGING = "ENV-STAGING"
    RECOVERY = "ENV-RECOVERY"
    PRODUCTION = "ENV-PRODUCTION"


class LogLevel(str, Enum):
    """Supported Python-compatible service log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class _ConfigurationReason(Enum):
    INVALID_SOURCE = (
        "INVALID_CONFIGURATION_SOURCE",
        "configuration source is invalid",
    )
    UNKNOWN_KEY = (
        "UNKNOWN_RAOS_CONFIGURATION_KEY",
        "configuration contains an unsupported RAOS key",
    )
    MISSING_REQUIRED = (
        "MISSING_REQUIRED_CONFIGURATION",
        "required configuration is missing",
    )
    INVALID_VALUE = (
        "INVALID_CONFIGURATION_VALUE",
        "configuration value is invalid",
    )
    INVALID_SECRET_REFERENCES = (
        "INVALID_SECRET_REFERENCES",
        "secret references are invalid",
    )
    INVALID_REQUIRED_SECRET_ALIASES = (
        "INVALID_REQUIRED_SECRET_ALIASES",
        "required secret aliases are invalid",
    )
    MISSING_REQUIRED_SECRET_REFERENCE = (
        "MISSING_REQUIRED_SECRET_REFERENCE",
        "a required secret reference is missing",
    )

    @property
    def code(self) -> str:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class ConfigurationError(ValueError):
    """A sanitized runtime-configuration boundary failure."""

    __slots__ = ("code", "message")

    def __init__(self, reason: _ConfigurationReason) -> None:
        self.code = reason.code
        self.message = reason.message
        super().__init__(f"{self.code}: {self.message}")

    def __repr__(self) -> str:
        return f"ConfigurationError(code={self.code!r}, message={self.message!r})"


def _raise_configuration_error(reason: _ConfigurationReason) -> NoReturn:
    raise ConfigurationError(reason) from None


@final
class SecretReference:
    """An opaque logical reference whose displays and serialization are redacted."""

    __slots__ = ("__logical_reference",)
    __logical_reference: str

    def __init__(self, logical_reference: str) -> None:
        if not _is_valid_secret_reference(logical_reference):
            raise ValueError("invalid secret reference")
        object.__setattr__(
            self, "_SecretReference__logical_reference", logical_reference
        )

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("SecretReference subclassing is not supported") from None

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("SecretReference is immutable")

    def __repr__(self) -> str:
        return f"SecretReference({_REDACTED_SECRET_REFERENCE!r})"

    def __str__(self) -> str:
        return _REDACTED_SECRET_REFERENCE

    def __eq__(self, other: object) -> bool:
        if type(other) is not SecretReference:
            return NotImplemented
        return self.__logical_reference == other.__logical_reference

    def __hash__(self) -> int:
        return hash(self.__logical_reference)

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        """Forbid generic serialization that could expose the reference."""

        del protocol
        raise TypeError("SecretReference serialization is not supported") from None

    @staticmethod
    def _require_pydantic_string(value: object) -> str:
        if type(value) is not str:
            raise ValueError("invalid secret reference")
        return value

    @classmethod
    def _from_pydantic_string(cls, value: str) -> Self:
        return cls(value)

    @staticmethod
    def _serialize_for_pydantic(value: SecretReference) -> str:
        del value
        return _REDACTED_SECRET_REFERENCE

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: object,
        handler: GetCoreSchemaHandler,
    ) -> core_schema.CoreSchema:
        del source_type, handler
        from_string = core_schema.no_info_after_validator_function(
            cls._from_pydantic_string,
            core_schema.no_info_before_validator_function(
                cls._require_pydantic_string,
                core_schema.str_schema(
                    strict=True,
                    min_length=10,
                    max_length=512,
                    pattern=_SECRET_REFERENCE_PYDANTIC_PATTERN,
                ),
            ),
        )
        return core_schema.json_or_python_schema(
            json_schema=from_string,
            python_schema=core_schema.union_schema(
                [core_schema.is_instance_schema(cls), from_string],
                mode="left_to_right",
            ),
            serialization=core_schema.plain_serializer_function_ser_schema(
                cls._serialize_for_pydantic,
                info_arg=False,
                return_schema=core_schema.str_schema(),
                when_used="always",
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        schema: core_schema.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            {
                "format": "secret-reference",
                "pattern": _SECRET_REFERENCE_SCHEMA_PATTERN,
                "writeOnly": True,
            }
        )
        return json_schema


def _sanitize_model_secret_references(
    value: object,
    *,
    json_mode: bool = False,
) -> dict[str, object]:
    """Return a bounded reference mapping safe for structured errors.

    Valid logical identifiers become opaque ``SecretReference`` instances;
    rejected aliases and values are replaced by fixed sentinels.  No exception
    from a caller-controlled mapping is allowed to retain the original input in
    a Pydantic ``ValidationError``.
    """

    if not isinstance(value, Mapping):
        return {_INVALID_SECRET_ALIAS: None}
    untrusted = cast(Mapping[object, object], value)
    copied: dict[str, object] = {}
    try:
        for index, key in enumerate(untrusted, start=1):
            if (
                index > _MAX_SECRET_REFERENCES
                or type(key) is not str
                or not _is_valid_secret_alias(key)
                or key in copied
            ):
                return {_INVALID_SECRET_ALIAS: None}
            raw_reference = untrusted[key]
            if type(raw_reference) is SecretReference:
                copied[key] = raw_reference
            elif type(raw_reference) is str and _is_valid_secret_reference(
                raw_reference
            ):
                copied[key] = (
                    raw_reference if json_mode else SecretReference(raw_reference)
                )
            else:
                copied[key] = None
    except Exception:
        return {_INVALID_SECRET_ALIAS: None}
    return copied


def _safe_secret_aliases(value: object) -> list[str]:
    """Return only bounded, validated aliases from potentially bypassed state."""

    if not isinstance(value, Mapping):
        return []
    untrusted = cast(Mapping[object, object], value)
    aliases: list[str] = []
    try:
        for index, alias in enumerate(untrusted, start=1):
            if (
                index > _MAX_SECRET_REFERENCES
                or type(alias) is not str
                or not _is_valid_secret_alias(alias)
                or alias in aliases
            ):
                return []
            aliases.append(alias)
    except Exception:
        return []
    return sorted(aliases)


def _untrusted_runtime_value(value: object) -> object:
    """Erase static field types when guarding deliberate BaseModel bypasses."""

    return value


@final
class RuntimeConfig(BaseModel):
    """Validated immutable service configuration with opaque secret references."""

    model_config = ConfigDict(
        strict=True,
        frozen=True,
        extra="forbid",
        hide_input_in_errors=True,
        revalidate_instances="always",
    )

    schema_version: Literal[1]
    environment: RuntimeEnvironment
    service_name: ServiceName
    log_level: LogLevel = LogLevel.INFO
    secret_references: Annotated[
        Mapping[SecretAlias, SecretReference],
        Field(max_length=_MAX_SECRET_REFERENCES),
    ]

    def __init_subclass__(cls, **kwargs: object) -> None:
        del cls, kwargs
        raise TypeError("RuntimeConfig subclassing is not supported") from None

    def __repr__(self) -> str:
        return "RuntimeConfig(<redacted>)"

    def __str__(self) -> str:
        return "RuntimeConfig(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        """Forbid generic serialization of a runtime configuration object."""

        del protocol
        raise TypeError("RuntimeConfig serialization is not supported") from None

    def model_copy(
        self,
        *,
        update: Mapping[str, object] | None = None,
        deep: bool = False,
    ) -> Self:
        """Copy the frozen model without Pydantic's unvalidated update path."""

        if not update:
            return super().model_copy(deep=deep)
        raise TypeError("RuntimeConfig updates are not supported") from None

    @classmethod
    def model_validate(
        cls,
        obj: object,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        from_attributes: bool | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Validate Python input without caller-controlled policy weakening."""

        if cls is not RuntimeConfig:
            raise TypeError("RuntimeConfig subclass validation is not supported")
        if strict is False or extra not in {None, "forbid"} or from_attributes is True:
            raise TypeError(
                "RuntimeConfig validation policy cannot be weakened"
            ) from None
        if type(obj) is RuntimeConfig:
            existing = obj
            obj = {
                "schema_version": _untrusted_runtime_value(existing.schema_version),
                "environment": _untrusted_runtime_value(existing.environment),
                "service_name": _untrusted_runtime_value(existing.service_name),
                "log_level": _untrusted_runtime_value(existing.log_level),
                "secret_references": _untrusted_runtime_value(
                    existing.secret_references
                ),
            }
        return super().model_validate(
            obj,
            strict=True,
            extra="forbid",
            from_attributes=False,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Validate JSON input with strict and extra-forbid policy fixed."""

        if cls is not RuntimeConfig:
            raise TypeError("RuntimeConfig subclass validation is not supported")
        if strict is False or extra not in {None, "forbid"}:
            raise TypeError(
                "RuntimeConfig validation policy cannot be weakened"
            ) from None
        if type(json_data) not in {str, bytes, bytearray}:
            _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
        stable_json_data: str | bytes
        if type(json_data) is bytearray:
            if len(json_data) > _MAX_MODEL_JSON_BYTES:
                _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
            stable_json_data = bytes(json_data)
        elif type(json_data) is bytes:
            stable_json_data = json_data
        else:
            stable_json_data = cast(str, json_data)
        input_length: int | None = None
        try:
            input_length = (
                len(stable_json_data.encode("utf-8"))
                if type(stable_json_data) is str
                else len(stable_json_data)
            )
        except UnicodeEncodeError:
            pass
        if input_length is None or input_length > _MAX_MODEL_JSON_BYTES:
            _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
        json_prescan_failed = False
        try:
            json.loads(
                stable_json_data,
                object_pairs_hook=_unique_bounded_object,
                parse_constant=_reject_json_constant,
            )
        except (
            json.JSONDecodeError,
            TypeError,
            UnicodeError,
            ValueError,
            RecursionError,
        ):
            json_prescan_failed = True
        if json_prescan_failed:
            _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
        validated: Self | None = None
        try:
            validated = super().model_validate_json(
                stable_json_data,
                strict=True,
                extra="forbid",
                context=context,
                by_alias=by_alias,
                by_name=by_name,
            )
        except ValidationError:
            pass
        if validated is None:
            _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
        return validated

    @classmethod
    def model_validate_strings(
        cls,
        obj: object,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: object | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> NoReturn:
        """Reject Pydantic's intentionally coercive string-validation mode."""

        del obj, strict, extra, context, by_alias, by_name
        raise TypeError("RuntimeConfig string coercion is not supported") from None

    @classmethod
    def model_construct(
        cls,
        _fields_set: set[str] | None = None,
        **values: object,
    ) -> NoReturn:
        """Reject Pydantic's intentionally unvalidated construction mode."""

        del _fields_set, values
        raise TypeError(
            "RuntimeConfig unvalidated construction is not supported"
        ) from None

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        schema: core_schema.CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        raw_properties: object = json_schema.get("properties")
        if isinstance(raw_properties, dict):
            properties = cast(dict[str, object], raw_properties)
            raw_service_name = properties.get("service_name")
            if isinstance(raw_service_name, dict):
                service_name = cast(dict[str, object], raw_service_name)
                service_name["pattern"] = _SERVICE_NAME_SCHEMA_PATTERN
            raw_secret_references = properties.get("secret_references")
            if isinstance(raw_secret_references, dict):
                secret_references = cast(dict[str, object], raw_secret_references)
                raw_property_names = secret_references.get("propertyNames")
                if isinstance(raw_property_names, dict):
                    property_names = cast(dict[str, object], raw_property_names)
                    property_names["pattern"] = _SECRET_ALIAS_SCHEMA_PATTERN
        return json_schema

    @model_validator(mode="before")
    @classmethod
    def _sanitize_model_input(
        cls,
        value: object,
        info: ValidationInfo,
    ) -> object:
        """Copy untrusted input while removing values from validation errors.

        ``hide_input_in_errors`` protects the textual rendering of a Pydantic
        error, but its structured ``errors()`` and ``json()`` surfaces retain
        rejected inputs.  This validator therefore replaces every rejected
        value before field validation and converts valid logical references to
        opaque objects.  It never raises while the original mapping is still
        attached to the validation context.
        """

        if not isinstance(value, Mapping):
            return {_INVALID_MODEL_FIELD: None}
        untrusted = cast(Mapping[object, object], value)
        copied: dict[str, object] = {}
        try:
            for index, key in enumerate(untrusted, start=1):
                if (
                    index > len(_MODEL_FIELDS)
                    or type(key) is not str
                    or key not in _MODEL_FIELDS
                    or key in copied
                ):
                    return {_INVALID_MODEL_FIELD: None}
                raw_value = untrusted[key]
                if key == "schema_version":
                    copied[key] = (
                        raw_value if type(raw_value) is int and raw_value == 1 else None
                    )
                elif key == "environment":
                    copied[key] = (
                        raw_value
                        if isinstance(raw_value, RuntimeEnvironment)
                        or (info.mode == "json" and type(raw_value) is str)
                        else None
                    )
                elif key == "service_name":
                    copied[key] = (
                        raw_value if _is_valid_service_name(raw_value) else None
                    )
                elif key == "log_level":
                    copied[key] = (
                        raw_value
                        if isinstance(raw_value, LogLevel)
                        or (info.mode == "json" and type(raw_value) is str)
                        else None
                    )
                else:
                    copied[key] = _sanitize_model_secret_references(
                        raw_value,
                        json_mode=info.mode == "json",
                    )
        except Exception:
            return {_INVALID_MODEL_FIELD: None}
        return copied

    @field_validator("schema_version", mode="before")
    @classmethod
    def _validate_schema_version(cls, value: object) -> int:
        if type(value) is not int or value != 1:
            raise ValueError("schema version is invalid")
        return value

    @field_validator("environment", mode="before")
    @classmethod
    def _validate_environment_type(cls, value: object, info: ValidationInfo) -> object:
        if info.mode == "python" and not isinstance(value, RuntimeEnvironment):
            raise ValueError("environment type is invalid")
        return value

    @field_validator("service_name", mode="before")
    @classmethod
    def _validate_service_name(cls, value: object) -> object:
        if not _is_valid_service_name(value):
            raise ValueError("service name is invalid")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def _validate_log_level_type(cls, value: object, info: ValidationInfo) -> object:
        if info.mode == "python" and not isinstance(value, LogLevel):
            raise ValueError("log level type is invalid")
        return value

    @field_validator("secret_references", mode="before")
    @classmethod
    def _validate_secret_aliases_before_values(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            raise ValueError("secret references must be a mapping")
        untrusted = cast(Mapping[object, object], value)
        copied: dict[str, object] = {}
        failed = False
        try:
            for index, key in enumerate(untrusted, start=1):
                if (
                    index > _MAX_SECRET_REFERENCES
                    or type(key) is not str
                    or not _is_valid_secret_alias(key)
                    or key in copied
                ):
                    failed = True
                    break
                copied[key] = untrusted[key]
        except Exception:
            failed = True
        if failed:
            raise ValueError("secret reference alias is invalid")
        return copied

    @field_validator("secret_references")
    @classmethod
    def _freeze_secret_references(
        cls, value: Mapping[str, SecretReference]
    ) -> Mapping[str, SecretReference]:
        return MappingProxyType(dict(value))

    @field_serializer("secret_references")
    def _serialize_secret_references(self, value: object) -> dict[str, str]:
        del self
        return {
            alias: _REDACTED_SECRET_REFERENCE for alias in _safe_secret_aliases(value)
        }

    @field_serializer("schema_version")
    def _serialize_schema_version(self, value: object) -> int:
        del self
        return 1 if type(value) is int and value == 1 else 0

    @field_serializer("environment")
    def _serialize_environment(self, value: object) -> str:
        del self
        return (
            value.value
            if isinstance(value, RuntimeEnvironment)
            else "<invalid-environment>"
        )

    @field_serializer("service_name")
    def _serialize_service_name(self, value: object) -> str:
        del self
        return (
            cast(str, value)
            if _is_valid_service_name(value)
            else "<invalid-service-name>"
        )

    @field_serializer("log_level")
    def _serialize_log_level(self, value: object) -> str:
        del self
        return value.value if isinstance(value, LogLevel) else "<invalid-log-level>"

    def redacted_diagnostics(self) -> dict[str, DiagnosticValue]:
        """Return the exact JSON-safe diagnostic allowlist without references."""

        raw_schema_version = _untrusted_runtime_value(self.schema_version)
        raw_environment = _untrusted_runtime_value(self.environment)
        raw_service_name = _untrusted_runtime_value(self.service_name)
        raw_log_level = _untrusted_runtime_value(self.log_level)
        raw_secret_references = _untrusted_runtime_value(self.secret_references)
        aliases = _safe_secret_aliases(raw_secret_references)
        environment = (
            raw_environment.value
            if isinstance(raw_environment, RuntimeEnvironment)
            else "<invalid-environment>"
        )
        service_name = (
            cast(str, raw_service_name)
            if _is_valid_service_name(raw_service_name)
            else "<invalid-service-name>"
        )
        log_level = (
            raw_log_level.value
            if isinstance(raw_log_level, LogLevel)
            else "<invalid-log-level>"
        )
        return {
            "schema_version": (
                raw_schema_version
                if type(raw_schema_version) is int and raw_schema_version == 1
                else 0
            ),
            "environment": environment,
            "service_name": service_name,
            "log_level": log_level,
            "secret_aliases": aliases,
            "secret_reference_count": len(aliases),
        }


class _JsonObjectError(ValueError):
    """Internal sentinel for sanitized JSON object failures."""


def redacted_diagnostics(config: object) -> dict[str, DiagnosticValue]:
    """Return the public diagnostic allowlist for one runtime configuration."""

    if not isinstance(config, RuntimeConfig):
        raise TypeError("config must be a RuntimeConfig")
    return config.redacted_diagnostics()


def _contains_control(value: str) -> bool:
    return any(
        ord(character) < 0x20 or 0x7F <= ord(character) <= 0x9F for character in value
    )


def _is_valid_service_name(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 63
        and not _contains_control(value)
        and _SERVICE_NAME_PATTERN.fullmatch(value) is not None
    )


def _is_valid_secret_alias(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 64
        and not _contains_control(value)
        and _SECRET_ALIAS_PATTERN.fullmatch(value) is not None
    )


def _is_valid_secret_reference(value: object) -> bool:
    if (
        type(value) is not str
        or not 10 <= len(value) <= _MAX_SECRET_REFERENCE_CHARS
        or _contains_control(value)
        or any(ord(character) > 0x7E for character in value)
        or not value.startswith("secret://")
    ):
        return False
    target = value.removeprefix("secret://")
    if _SECRET_TARGET_PATTERN.fullmatch(target) is None:
        return False
    parsed = urlsplit(value)
    if (
        parsed.scheme != "secret"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    if "//" in target:
        return False
    segments = target.split("/")
    return all(segment and set(segment) != {"."} for segment in segments)


def _validate_required_secret_aliases(
    aliases: Iterable[str],
) -> frozenset[str]:
    if isinstance(aliases, (str, bytes)):
        _raise_configuration_error(_ConfigurationReason.INVALID_REQUIRED_SECRET_ALIASES)
    collected: list[str] = []
    failed = False
    try:
        for alias in aliases:
            if len(collected) >= _MAX_REQUIRED_SECRET_ALIASES:
                failed = True
                break
            if not _is_valid_secret_alias(alias) or alias in collected:
                failed = True
                break
            collected.append(alias)
    except Exception:
        failed = True
    if failed:
        _raise_configuration_error(_ConfigurationReason.INVALID_REQUIRED_SECRET_ALIASES)
    return frozenset(collected)


def _select_raos_values(source: Mapping[str, object]) -> dict[str, object]:
    untrusted = cast(Mapping[object, object], source)
    selected: dict[str, object] = {}
    failed = False
    unknown = False
    try:
        for index, key in enumerate(untrusted, start=1):
            if index > _MAX_SOURCE_ENTRIES or type(key) is not str:
                failed = True
                break
            if _contains_control(key):
                failed = True
                break
            if key.casefold().startswith("raos_"):
                if key not in _ALLOWED_ENVIRONMENT_KEYS or key in selected:
                    unknown = True
                    break
                selected[key] = untrusted[key]
    except Exception:
        failed = True
    if failed:
        _raise_configuration_error(_ConfigurationReason.INVALID_SOURCE)
    if unknown:
        _raise_configuration_error(_ConfigurationReason.UNKNOWN_KEY)
    return selected


def _require_text(value: object, *, maximum_length: int) -> str | None:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum_length
        or _contains_control(value)
    ):
        return None
    return value


def _reject_json_constant(value: str) -> object:
    del value
    raise _JsonObjectError


def _unique_bounded_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    if len(pairs) > _MAX_SECRET_REFERENCES:
        raise _JsonObjectError
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _JsonObjectError
        result[key] = value
    return result


def _is_flat_json_object_source(value: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for character in value:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
            if depth > 1:
                return False
        elif character == "}":
            depth -= 1
            if depth < 0:
                return False
        elif character in "[]":
            return False
    return depth == 0 and not in_string and not escaped


def _parse_secret_references(value: object) -> dict[str, SecretReference]:
    text = _require_text(
        value,
        maximum_length=_MAX_SECRET_REFERENCES_JSON_BYTES,
    )
    encoded: bytes | None = None
    if text is not None:
        try:
            encoded = text.encode("utf-8")
        except UnicodeEncodeError:
            pass
    if (
        text is None
        or encoded is None
        or len(encoded) > _MAX_SECRET_REFERENCES_JSON_BYTES
        or not _is_flat_json_object_source(text)
    ):
        _raise_configuration_error(_ConfigurationReason.INVALID_SECRET_REFERENCES)

    parsed: object | None = None
    failed = False
    try:
        parsed = json.loads(
            text,
            object_pairs_hook=_unique_bounded_object,
            parse_constant=_reject_json_constant,
        )
    except json.JSONDecodeError, TypeError, ValueError, RecursionError:
        failed = True
    if failed or not isinstance(parsed, dict):
        _raise_configuration_error(_ConfigurationReason.INVALID_SECRET_REFERENCES)

    untrusted = cast(dict[object, object], parsed)
    references: dict[str, SecretReference] = {}
    for alias, logical_reference in untrusted.items():
        if (
            type(alias) is not str
            or not _is_valid_secret_alias(alias)
            or type(logical_reference) is not str
        ):
            _raise_configuration_error(_ConfigurationReason.INVALID_SECRET_REFERENCES)
        try:
            reference = SecretReference(logical_reference)
        except ValueError:
            reference = None
        if reference is None:
            _raise_configuration_error(_ConfigurationReason.INVALID_SECRET_REFERENCES)
        references[alias] = reference
    return references


def load_runtime_config(
    source: Mapping[str, object],
    *,
    required_secret_aliases: Iterable[str] = (),
) -> RuntimeConfig:
    """Load one explicit mapping without file, network, or provider access."""

    required_aliases = _validate_required_secret_aliases(required_secret_aliases)
    selected = _select_raos_values(source)
    if _ENVIRONMENT_KEY not in selected or _SERVICE_NAME_KEY not in selected:
        _raise_configuration_error(_ConfigurationReason.MISSING_REQUIRED)

    environment_text = _require_text(selected[_ENVIRONMENT_KEY], maximum_length=32)
    service_name = _require_text(selected[_SERVICE_NAME_KEY], maximum_length=63)
    log_level = _require_text(selected.get(_LOG_LEVEL_KEY, "INFO"), maximum_length=16)
    if environment_text is None or service_name is None or log_level is None:
        _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
    if not _is_valid_service_name(service_name):
        _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)

    validated_log_level: LogLevel | None = None
    try:
        validated_log_level = LogLevel(log_level)
    except ValueError:
        pass
    if validated_log_level is None:
        _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)

    environment: RuntimeEnvironment | None = None
    try:
        environment = RuntimeEnvironment(environment_text)
    except ValueError:
        pass
    if environment is None:
        _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)

    secret_references = _parse_secret_references(
        selected.get(_SECRET_REFERENCES_KEY, "{}")
    )
    if not required_aliases.issubset(secret_references):
        _raise_configuration_error(
            _ConfigurationReason.MISSING_REQUIRED_SECRET_REFERENCE
        )

    config: RuntimeConfig | None = None
    try:
        config = RuntimeConfig(
            schema_version=1,
            environment=environment,
            service_name=service_name,
            log_level=validated_log_level,
            secret_references=secret_references,
        )
    except ValidationError, TypeError, ValueError:
        pass
    if config is None:
        _raise_configuration_error(_ConfigurationReason.INVALID_VALUE)
    return config


def load_runtime_config_from_environment(
    *,
    required_secret_aliases: Iterable[str] = (),
    environ: Mapping[str, object] | None = None,
) -> RuntimeConfig:
    """Explicitly read the process environment, or a supplied environment view."""

    source: Mapping[str, object] = os.environ if environ is None else environ
    return load_runtime_config(
        source,
        required_secret_aliases=required_secret_aliases,
    )
