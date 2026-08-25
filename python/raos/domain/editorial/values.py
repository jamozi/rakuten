"""Exact immutable JSON wrappers for EDITORIAL physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


def _validate(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        raise ValueError("INVALID_EDITORIAL_JSON_VALUE") from None


@dataclass(frozen=True, slots=True, repr=False)
class ArticleBlockContentJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ArticleBlockContentJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticlePlanBriefJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ArticlePlanBriefJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTemplateVersionTemplateJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ArticleTemplateVersionTemplateJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ArticleTypeVersionContractJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ArticleTypeVersionContractJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class EditorialMethodologyVersionDefinitionJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "EditorialMethodologyVersionDefinitionJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class SeoMetadataVersionMetadataJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "SeoMetadataVersionMetadataJson(<redacted>)"


__all__ = [
    "ArticleBlockContentJson",
    "ArticlePlanBriefJson",
    "ArticleTemplateVersionTemplateJson",
    "ArticleTypeVersionContractJson",
    "EditorialMethodologyVersionDefinitionJson",
    "SeoMetadataVersionMetadataJson",
]
