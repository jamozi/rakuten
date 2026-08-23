"""Strict immutable JSON values for persistence and event boundaries."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import json
import math
from types import MappingProxyType
from typing import NoReturn, TypeAlias, cast, overload


JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | "FrozenJsonArray" | "FrozenJsonObject"
_MAX_DEPTH = 32
_MAX_ITEMS = 10_000
_MAX_TEXT = 1_048_576
_MAX_INTEGER = (1 << 63) - 1


def _invalid() -> NoReturn:
    raise ValueError("INVALID_JSON_VALUE") from None


def _key(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value) > 256
        or value != value.strip()
        or "\x00" in value
    ):
        _invalid()
    return value


def freeze_json(value: object, *, _depth: int = 0) -> JsonValue:
    if _depth > _MAX_DEPTH:
        _invalid()
    if value is None or type(value) in {bool, str}:
        if type(value) is str and (len(value) > _MAX_TEXT or "\x00" in value):
            _invalid()
        return cast(None | bool | str, value)
    if type(value) is int:
        if not -_MAX_INTEGER <= value <= _MAX_INTEGER:
            _invalid()
        return value
    if type(value) is float:
        if not math.isfinite(value):
            _invalid()
        return value
    if type(value) is FrozenJsonArray or type(value) is FrozenJsonObject:
        return value
    if isinstance(value, Mapping):
        if len(value) > _MAX_ITEMS:
            _invalid()
        pairs: list[tuple[str, JsonValue]] = []
        seen: set[str] = set()
        for raw_key, item in value.items():
            key = _key(raw_key)
            if key in seen:
                _invalid()
            seen.add(key)
            pairs.append((key, freeze_json(item, _depth=_depth + 1)))
        return FrozenJsonObject(tuple(sorted(pairs)))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > _MAX_ITEMS:
            _invalid()
        return FrozenJsonArray(
            tuple(freeze_json(item, _depth=_depth + 1) for item in value)
        )
    _invalid()


class FrozenJsonArray(Sequence[JsonValue]):
    __slots__ = ("_values",)

    def __init__(self, values: tuple[JsonValue, ...] = ()) -> None:
        if type(values) is not tuple or len(values) > _MAX_ITEMS:
            _invalid()
        self._values = tuple(freeze_json(value, _depth=1) for value in values)

    def __setattr__(self, name: str, value: object) -> None:
        try:
            object.__getattribute__(self, name)
        except AttributeError:
            object.__setattr__(self, name, value)
            return
        raise AttributeError("immutable JSON value") from None

    @overload
    def __getitem__(self, index: int) -> JsonValue: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[JsonValue, ...]: ...

    def __getitem__(self, index: int | slice) -> JsonValue | tuple[JsonValue, ...]:
        return self._values[index]

    def __len__(self) -> int:
        return len(self._values)

    def __repr__(self) -> str:
        return "FrozenJsonArray(<redacted>)"


class FrozenJsonObject(Mapping[str, JsonValue]):
    __slots__ = ("_pairs", "_values")

    def __init__(self, pairs: tuple[tuple[str, JsonValue], ...] = ()) -> None:
        if type(pairs) is not tuple or len(pairs) > _MAX_ITEMS:
            _invalid()
        normalized: list[tuple[str, JsonValue]] = []
        seen: set[str] = set()
        for pair in pairs:
            if type(pair) is not tuple or len(pair) != 2:
                _invalid()
            key, value = pair
            key = _key(key)
            if key in seen:
                _invalid()
            seen.add(key)
            normalized.append((key, freeze_json(value, _depth=1)))
        normalized.sort(key=lambda item: item[0])
        self._pairs = tuple(normalized)
        self._values = MappingProxyType(dict(normalized))

    def __setattr__(self, name: str, value: object) -> None:
        try:
            object.__getattribute__(self, name)
        except AttributeError:
            object.__setattr__(self, name, value)
            return
        raise AttributeError("immutable JSON value") from None

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> FrozenJsonObject:
        frozen = freeze_json(value)
        if type(frozen) is not cls:
            _invalid()
        return frozen

    def __getitem__(self, key: str) -> JsonValue:
        return self._values[key]

    def __iter__(self) -> Iterator[str]:
        return (key for key, _value in self._pairs)

    def __len__(self) -> int:
        return len(self._pairs)

    @property
    def pairs(self) -> tuple[tuple[str, JsonValue], ...]:
        return self._pairs

    def __repr__(self) -> str:
        return "FrozenJsonObject(<redacted>)"


def _plain(value: JsonValue) -> object:
    if type(value) is FrozenJsonObject:
        return {key: _plain(item) for key, item in value.pairs}
    if type(value) is FrozenJsonArray:
        return [_plain(item) for item in value]
    return value


def canonical_json_bytes(value: FrozenJsonObject) -> bytes:
    if type(value) is not FrozenJsonObject:
        _invalid()
    return (
        json.dumps(
            _plain(value),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )


__all__ = [
    "FrozenJsonArray",
    "FrozenJsonObject",
    "JsonScalar",
    "JsonValue",
    "canonical_json_bytes",
    "freeze_json",
]
