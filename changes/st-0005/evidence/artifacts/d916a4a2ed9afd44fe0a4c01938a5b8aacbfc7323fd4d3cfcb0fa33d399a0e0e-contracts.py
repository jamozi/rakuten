"""Immutable, provider-neutral AI catalog contracts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import cast


type ContractValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple["ContractValue", ...]
    | Mapping[str, "ContractValue"]
)


def _require_text(value: object, *, field_name: str) -> None:
    if (
        type(value) is not str
        or not value
        or value != value.strip()
        or any(not character.isprintable() for character in value)
    ):
        raise ValueError(
            f"{field_name} must be an exact non-empty trimmed printable string"
        )


def _require_sha256(value: object, *, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _deep_freeze(value: object, *, field_name: str) -> ContractValue:
    """Snapshot supported JSON values without retaining caller-owned containers."""

    visits = 0
    active: set[int] = set()

    def freeze(item: object, depth: int) -> ContractValue:
        nonlocal visits
        visits += 1
        if visits > 100_000 or depth > 100:
            raise ValueError(f"{field_name} exceeds the contract graph limit")
        if item is None or type(item) in {bool, int, str}:
            return cast(None | bool | int | str, item)
        if type(item) is float:
            number = item
            if not math.isfinite(number):
                raise ValueError(f"{field_name} cannot contain non-finite numbers")
            return number
        if not isinstance(item, (Mapping, list, tuple)):
            raise ValueError(f"{field_name} contains an unsupported value")
        container = cast(
            Mapping[object, object] | list[object] | tuple[object, ...], item
        )
        identity = id(container)
        if identity in active:
            raise ValueError(f"{field_name} cannot contain a cycle")
        active.add(identity)
        try:
            if isinstance(container, Mapping):
                raw_mapping = container
                if not all(type(key) is str for key in raw_mapping):
                    raise ValueError(f"{field_name} requires exact string keys")
                return MappingProxyType(
                    {
                        cast(str, key): freeze(child, depth + 1)
                        for key, child in raw_mapping.items()
                    }
                )
            raw_sequence = container
            return tuple(freeze(child, depth + 1) for child in raw_sequence)
        finally:
            active.remove(identity)

    return freeze(value, 0)


def _deep_freeze_mapping(
    value: Mapping[str, ContractValue], *, field_name: str
) -> Mapping[str, ContractValue]:
    frozen = _deep_freeze(value, field_name=field_name)
    if not isinstance(frozen, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return frozen


@dataclass(frozen=True, slots=True)
class PromptContract:
    """One exact prompt template and its frozen catalog metadata."""

    prompt_code: str
    version: int
    task_code: str
    status: str
    locale: str
    artifact_path: str
    sha256: str
    content: str = field(repr=False)
    metadata: Mapping[str, ContractValue] = field(repr=False)

    def __post_init__(self) -> None:
        for field_name in (
            "prompt_code",
            "task_code",
            "status",
            "locale",
            "artifact_path",
        ):
            _require_text(getattr(self, field_name), field_name=field_name)
        if type(self.version) is not int or self.version < 1:
            raise ValueError("version must be a positive exact integer")
        if type(self.content) is not str or not self.content:
            raise ValueError("content must be an exact non-empty string")
        _require_sha256(self.sha256, field_name="sha256")
        object.__setattr__(
            self,
            "metadata",
            _deep_freeze_mapping(self.metadata, field_name="metadata"),
        )


@dataclass(frozen=True, slots=True)
class OutputSchemaContract:
    """One exact task-output schema and its frozen registry metadata."""

    schema_id: str
    artifact_path: str
    sha256: str
    document: Mapping[str, ContractValue] = field(repr=False)
    metadata: Mapping[str, ContractValue] = field(repr=False)

    def __post_init__(self) -> None:
        _require_text(self.schema_id, field_name="schema_id")
        _require_text(self.artifact_path, field_name="artifact_path")
        _require_sha256(self.sha256, field_name="sha256")
        object.__setattr__(
            self,
            "document",
            _deep_freeze_mapping(self.document, field_name="document"),
        )
        object.__setattr__(
            self,
            "metadata",
            _deep_freeze_mapping(self.metadata, field_name="metadata"),
        )


@dataclass(frozen=True, slots=True)
class RouteContract:
    """Frozen candidate route metadata; this type does not activate a route."""

    route_code: str
    sha256: str
    metadata: Mapping[str, ContractValue] = field(repr=False)

    def __post_init__(self) -> None:
        _require_text(self.route_code, field_name="route_code")
        _require_sha256(self.sha256, field_name="sha256")
        object.__setattr__(
            self,
            "metadata",
            _deep_freeze_mapping(self.metadata, field_name="metadata"),
        )


@dataclass(frozen=True, slots=True)
class TaskContract:
    """Hash-bound Task/Prompt/Schema/Route projection for one catalog task."""

    task_code: str
    catalog_id: str
    lifecycle: str
    risk_level: str
    sha256: str
    binding_sha256: str
    prompt: PromptContract
    output_schema: OutputSchemaContract
    route: RouteContract
    metadata: Mapping[str, ContractValue] = field(repr=False)

    def __post_init__(self) -> None:
        for field_name in ("task_code", "catalog_id", "lifecycle", "risk_level"):
            _require_text(getattr(self, field_name), field_name=field_name)
        _require_sha256(self.sha256, field_name="sha256")
        _require_sha256(self.binding_sha256, field_name="binding_sha256")
        if type(self.prompt) is not PromptContract:
            raise ValueError("prompt must be an exact PromptContract")
        if type(self.output_schema) is not OutputSchemaContract:
            raise ValueError("output_schema must be an exact OutputSchemaContract")
        if type(self.route) is not RouteContract:
            raise ValueError("route must be an exact RouteContract")
        object.__setattr__(
            self,
            "metadata",
            _deep_freeze_mapping(self.metadata, field_name="metadata"),
        )
        if self.prompt.task_code != self.task_code:
            raise ValueError("prompt task_code does not match TaskContract")
        if self.route.route_code != self.metadata.get("route_code"):
            raise ValueError("route_code does not match TaskContract metadata")
