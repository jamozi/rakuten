"""Immutable generated-fixture adapter for the ST-1702 DEV/CI boundary."""

from __future__ import annotations

import hashlib
import json
from typing import Any, NoReturn, cast, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.category_fixtures import (
    CategoryFixtureFailure,
    CategoryFixtureFailureCode,
    CategoryFixtureLoadRequest,
    CategoryFixtureLoadResult,
    build_category_fixture_bundle,
    category_fixture_sha256,
    fail_category_fixture,
)
from raos.adapters.recorded_category_fixture_v2 import (
    ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON,
    ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256,
)


_MAX_FIXTURE_BYTES = 256 * 1024
_MAX_JSON_DEPTH = 24
_MAX_JSON_NODES = 10_000
def _invalid() -> NoReturn:
    fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_INVALID)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _invalid()
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    del value
    _invalid()


def _bounded_tree(value: object) -> None:
    pending: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while pending:
        current, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            _invalid()
        if current is None or type(current) in {str, bool, int}:
            continue
        if type(current) is list:
            pending.extend((item, depth + 1) for item in cast(list[object], current))
            continue
        if type(current) is dict:
            pending.extend(
                (item, depth + 1)
                for item in cast(dict[object, object], current).values()
            )
            continue
        _invalid()


def _fixture_material() -> tuple[bytes, dict[str, Any]]:
    if type(ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON) is not str:
        _invalid()
    try:
        payload = ST1702_RECORDED_CATEGORY_FIXTURE_V2_JSON.encode(
            "utf-8", errors="strict"
        )
    except UnicodeError:
        _invalid()
    if not 2 <= len(payload) <= _MAX_FIXTURE_BYTES:
        _invalid()
    expected_sha = category_fixture_sha256(ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256)
    if hashlib.sha256(payload).hexdigest() != expected_sha:
        fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH)
    try:
        parsed: object = json.loads(
            payload,
            object_pairs_hook=_pairs,
            parse_constant=_constant,
        )
    except CategoryFixtureFailure:
        raise
    except UnicodeError, json.JSONDecodeError, RecursionError, ValueError, TypeError:
        _invalid()
    _bounded_tree(parsed)
    if type(parsed) is not dict:
        _invalid()
    return payload, cast(dict[str, Any], parsed)


@final
class RecordedCategoryFixtureAdapter:
    """Parse the generated fixture from immutable module bytes on each call."""

    __slots__ = ("_environment", "_fixture_id", "_source_sha256")

    def __init__(self, *, environment: RuntimeEnvironment) -> None:
        if type(environment) is not RuntimeEnvironment or environment not in {
            RuntimeEnvironment.ENV_DEV,
            RuntimeEnvironment.CI,
        }:
            fail_category_fixture()
        _payload, parsed = _fixture_material()
        source_sha = category_fixture_sha256(ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256)
        bundle = build_category_fixture_bundle(
            parsed,
            source_fixture_sha256=source_sha,
        )
        self._environment = environment
        self._fixture_id = bundle.fixture_id
        self._source_sha256 = source_sha

    def load(self, request: CategoryFixtureLoadRequest) -> CategoryFixtureLoadResult:
        if type(request) is not CategoryFixtureLoadRequest:
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH)
        try:
            request.__post_init__()
        except Exception:
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH)
        if (
            request.fixture_id != self._fixture_id
            or request.expected_source_fixture_sha256 != self._source_sha256
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH)
        payload, parsed = _fixture_material()
        current_sha256 = category_fixture_sha256(
            ST1702_RECORDED_CATEGORY_FIXTURE_V2_SHA256
        )
        if (
            current_sha256 != self._source_sha256
            or hashlib.sha256(payload).hexdigest() != self._source_sha256
        ):
            fail_category_fixture(CategoryFixtureFailureCode.FIXTURE_HASH_MISMATCH)
        bundle = build_category_fixture_bundle(
            parsed,
            source_fixture_sha256=self._source_sha256,
        )
        return CategoryFixtureLoadResult(
            request_fingerprint=request.fingerprint,
            bundle=bundle,
            source_mode="RECORDED_SYNTHETIC_DEV_CI_ONLY",
            persistence="NOT_EXECUTED",
            external_actions="NOT_EXECUTED",
        )


__all__ = ["RecordedCategoryFixtureAdapter"]
