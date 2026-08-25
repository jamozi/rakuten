"""Exact immutable JSON wrappers for EVIDENCE physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


def _validate(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        raise ValueError("INVALID_EVIDENCE_JSON_VALUE") from None


@dataclass(frozen=True, slots=True, repr=False)
class FactLocatorJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "FactLocatorJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FactValueJsonJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "FactValueJsonJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FirstHandExperienceRecordEnvironmentJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "FirstHandExperienceRecordEnvironmentJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class FirstHandExperienceRecordProductVariantIdentityJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "FirstHandExperienceRecordProductVariantIdentityJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SourceMetadataJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "SourceMetadataJson(<redacted>)"


__all__ = [
    "FactLocatorJson",
    "FactValueJsonJson",
    "FirstHandExperienceRecordEnvironmentJson",
    "FirstHandExperienceRecordProductVariantIdentityJson",
    "SourceMetadataJson",
]
