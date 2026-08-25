"""Shared inward append-only audit capability."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import Protocol, runtime_checkable
from urllib.parse import urlsplit

from raos.domain.shared.identity import EntityId
from raos.domain.shared.json_values import FrozenJsonArray, FrozenJsonObject, JsonValue


_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,126}\Z", re.ASCII)
_SAFE_DETAIL_TEXT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,63}\Z", re.ASCII)
_SENSITIVE_KEY_MARKERS = (
    "accesskey",
    "accesstoken",
    "affiliateid",
    "apikey",
    "applicationid",
    "authorization",
    "clientid",
    "clientsecret",
    "cookie",
    "credential",
    "email",
    "ipaddress",
    "oauth",
    "password",
    "privatekey",
    "rawip",
    "refreshtoken",
    "session",
    "secret",
    "token",
    "useragent",
)
_HIGH_ENTROPY_TEXT = re.compile(
    r"(?:[A-Fa-f0-9]{24,}|[A-Za-z0-9_-]{24,}={0,2})\Z", re.ASCII
)
_AUDIT_DETAIL_KINDS = frozenset({"test", "transition"})
_AUDIT_DETAIL_KEYS = frozenset({"attempt", "automatic", "kind"})


def _sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _is_concrete_entity_id(value: object) -> bool:
    return isinstance(value, EntityId) and type(value) is not EntityId


def _sensitive_text(value: str) -> bool:
    if _SAFE_DETAIL_TEXT.fullmatch(value) is None or _HIGH_ENTROPY_TEXT.fullmatch(
        value
    ):
        return True
    lowered = value.casefold()
    if (
        lowered.startswith(("basic:", "bearer:", "basic/", "bearer/"))
        or "-----begin" in lowered
        or value.count(".") == 2
        and all(part for part in value.split("."))
    ):
        return True
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return True
    parsed = urlsplit(value)
    return bool(parsed.scheme or parsed.netloc or parsed.query or parsed.fragment)


def _contains_sensitive_material(value: JsonValue) -> bool:
    if type(value) is FrozenJsonObject:
        return any(
            _sensitive_key(key) or _contains_sensitive_material(item)
            for key, item in value.pairs
        )
    if type(value) is FrozenJsonArray:
        return any(_contains_sensitive_material(item) for item in value)
    if type(value) is str:
        return _sensitive_text(value)
    return False


def _closed_audit_metadata(value: FrozenJsonObject) -> bool:
    """Accept only typed, closed metadata; arbitrary text is never audit-safe."""

    if len(value) > len(_AUDIT_DETAIL_KEYS) or not set(value).issubset(
        _AUDIT_DETAIL_KEYS
    ):
        return False
    for key, item in value.pairs:
        if key == "kind":
            if type(item) is not str or item not in _AUDIT_DETAIL_KINDS:
                return False
        elif key == "attempt":
            if type(item) is not int or not 0 <= item <= 1000:
                return False
        elif key == "automatic":
            if type(item) is not bool:
                return False
        else:
            return False
    return True


@dataclass(frozen=True, slots=True, repr=False)
class SanitizedAuditDetails:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        if (
            type(self.value) is not FrozenJsonObject
            or not _closed_audit_metadata(self.value)
            or _contains_sensitive_material(self.value)
        ):
            raise ValueError("INVALID_SANITIZED_AUDIT_DETAILS") from None

    def __repr__(self) -> str:
        return "SanitizedAuditDetails(<redacted>)"


@dataclass(frozen=True, slots=True, repr=False)
class AuditIntent:
    action: str
    target_type: str
    target_id: EntityId | None
    outcome: str
    reason: str
    sanitized_details: SanitizedAuditDetails

    def __post_init__(self) -> None:
        if (
            type(self.action) is not str
            or _TOKEN.fullmatch(self.action) is None
            or type(self.target_type) is not str
            or _TOKEN.fullmatch(self.target_type) is None
            or (
                self.target_id is not None
                and (not _is_concrete_entity_id(self.target_id))
            )
            or self.outcome not in {"SUCCESS", "DENIED", "FAILED", "NOOP"}
            or type(self.reason) is not str
            or _TOKEN.fullmatch(self.reason) is None
            or type(self.sanitized_details) is not SanitizedAuditDetails
        ):
            raise ValueError("INVALID_AUDIT_INTENT") from None

    def __repr__(self) -> str:
        return "AuditIntent(<redacted>)"


@runtime_checkable
class AuditEventAppender(Protocol):
    def append_many(self, intents: tuple[AuditIntent, ...]) -> None: ...


__all__ = ["AuditEventAppender", "AuditIntent", "SanitizedAuditDetails"]
