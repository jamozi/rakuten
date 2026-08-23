"""Exact immutable JSON wrappers for OPS physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass

from raos.domain.shared.json_values import FrozenJsonObject


def _validate(value: object) -> None:
    if type(value) is not FrozenJsonObject:
        raise ValueError("INVALID_OPS_JSON_VALUE") from None


@dataclass(frozen=True, slots=True, repr=False)
class AuditEventRecordDetailsJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "AuditEventRecordDetailsJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class IdempotencyRecordResponseBodyJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "IdempotencyRecordResponseBodyJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JobAttemptMetricsJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "JobAttemptMetricsJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class JobPayloadJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "JobPayloadJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class ObjectArtifactMetadataJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "ObjectArtifactMetadataJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class OutboxEventRecordPayloadJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "OutboxEventRecordPayloadJson(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class RuntimeSettingVersionValueJson:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        _validate(self.value)

    def __repr__(self) -> str:
        return "RuntimeSettingVersionValueJson(<redacted>)"


__all__ = [
    "AuditEventRecordDetailsJson",
    "IdempotencyRecordResponseBodyJson",
    "JobAttemptMetricsJson",
    "JobPayloadJson",
    "ObjectArtifactMetadataJson",
    "OutboxEventRecordPayloadJson",
    "RuntimeSettingVersionValueJson",
]
