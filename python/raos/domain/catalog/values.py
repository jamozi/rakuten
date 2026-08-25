"""Exact immutable JSON wrappers for CATALOG physical jsonb columns."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

from raos.domain.shared.json_values import (
    FrozenJsonArray,
    FrozenJsonObject,
    JsonValue,
)


_SENSITIVE_CONFIG_KEY_MARKERS = (
    "accesskey",
    "accesstoken",
    "affiliateid",
    "apikey",
    "appid",
    "applicationid",
    "authorization",
    "clientsecret",
    "cookie",
    "credential",
    "oauth",
    "password",
    "privatekey",
    "refreshtoken",
    "secret",
    "session",
    "token",
)
_HIGH_ENTROPY_CONFIG_TEXT = re.compile(
    r"(?:[A-Fa-f0-9]{32,}|[A-Za-z0-9_-]{32,}={0,2})\Z", re.ASCII
)
_PROVIDER_CONFIG_KEYS = frozenset(
    {"field_mapping", "live_enabled", "page_size", "timeout_seconds"}
)
_PROVIDER_FIELD_MAPPING = FrozenJsonObject.from_mapping({"title": "itemName"})


def _sensitive_config_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", key.casefold())
    return any(marker in normalized for marker in _SENSITIVE_CONFIG_KEY_MARKERS)


def _sensitive_config_text(value: str) -> bool:
    lowered = value.casefold()
    if (
        len(value) > 512
        or _HIGH_ENTROPY_CONFIG_TEXT.fullmatch(value)
        or lowered.startswith(("basic ", "bearer "))
        or "-----begin" in lowered
    ):
        return True
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        return True
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        return True
    return any(_sensitive_config_key(key) for key, _item in parse_qsl(parsed.query))


def _contains_provider_secret(value: JsonValue) -> bool:
    if type(value) is FrozenJsonObject:
        return any(
            _sensitive_config_key(key) or _contains_provider_secret(item)
            for key, item in value.pairs
        )
    if type(value) is FrozenJsonArray:
        return any(_contains_provider_secret(item) for item in value)
    return type(value) is str and _sensitive_config_text(value)


def _is_closed_provider_config(value: FrozenJsonObject) -> bool:
    """Accept only the versioned, non-secret operational configuration surface.

    The physical contract permits a JSON object but explicitly excludes provider
    credentials.  An arbitrary JSON/string escape hatch cannot prove that
    exclusion, even with a denylist, so the local runtime accepts only fields with
    closed value domains.  Future provider mappings require an explicit contract
    version rather than silently widening this persistence boundary.
    """

    if not set(value).issubset(_PROVIDER_CONFIG_KEYS):
        return False
    for key, item in value.pairs:
        if key == "timeout_seconds":
            if type(item) is not int or not 1 <= item <= 600:
                return False
        elif key == "page_size":
            if type(item) is not int or not 1 <= item <= 100:
                return False
        elif key == "field_mapping":
            if type(item) is not FrozenJsonObject or item.pairs not in {
                (),
                _PROVIDER_FIELD_MAPPING.pairs,
            }:
                return False
        elif key == "live_enabled":
            if type(item) is not bool or item:
                return False
        else:  # pragma: no cover - protected by the closed key set above.
            return False
    return True


@dataclass(frozen=True, slots=True, repr=False)
class _ObjectJsonValue:
    value: FrozenJsonObject

    def __post_init__(self) -> None:
        if type(self.value) is not FrozenJsonObject:
            raise ValueError("INVALID_CATALOG_JSON_VALUE") from None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted>)"


class CanonicalProductIdentityAttributesJson(_ObjectJsonValue):
    __slots__ = ()


class GroupingDecisionReasonsJson(_ObjectJsonValue):
    __slots__ = ()


class IngestionRequestRateLimitObservationJson(_ObjectJsonValue):
    __slots__ = ()


class IngestionRequestRequestParametersJson(_ObjectJsonValue):
    __slots__ = ()


class ProductCandidateImageSetJson(_ObjectJsonValue):
    __slots__ = ()


class ProviderEndpointNonSecretConfigJson(_ObjectJsonValue):
    __slots__ = ()

    def __post_init__(self) -> None:
        super().__post_init__()
        if not _is_closed_provider_config(self.value) or _contains_provider_secret(
            self.value
        ):
            raise ValueError("INVALID_PROVIDER_NON_SECRET_CONFIG") from None


__all__ = [
    "CanonicalProductIdentityAttributesJson",
    "GroupingDecisionReasonsJson",
    "IngestionRequestRateLimitObservationJson",
    "IngestionRequestRequestParametersJson",
    "ProductCandidateImageSetJson",
    "ProviderEndpointNonSecretConfigJson",
]
