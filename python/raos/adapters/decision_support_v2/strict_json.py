"""Strict JSON decoding shared by recorded-only adapters."""

from __future__ import annotations

import json
from typing import Any, NoReturn

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure


class _DuplicateKey(ValueError):
    pass


class _NonFiniteNumber(ValueError):
    pass


def _reject_nonfinite(value: str) -> NoReturn:
    raise _NonFiniteNumber(value)


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def loads_strict_json(raw: str) -> Any:
    """Decode standards-compliant JSON and reject duplicate keys at every level."""

    try:
        return json.loads(
            raw,
            object_pairs_hook=_object_without_duplicates,
            parse_constant=_reject_nonfinite,
        )
    except (json.JSONDecodeError, _DuplicateKey, _NonFiniteNumber) as exc:
        raise AdapterError(AdapterFailure.INVALID_RESPONSE) from exc


__all__ = ["loads_strict_json"]
