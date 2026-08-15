#!/usr/bin/env python3
"""Validate and render the closed ST-0703 recorded-fixture inventory."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
import tomllib
import unicodedata
from urllib.parse import urlsplit
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, NoReturn, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-0703/contracts/openai-responses-adapter.v1.yaml"
)
FIXTURE_ROOT: Final = Path("changes/st-0703/fixtures/recorded")
PYPROJECT_PATH: Final = Path("pyproject.toml")
UV_LOCK_PATH: Final = Path("uv.lock")
UV_CONFIG_PATH: Final = Path("uv.toml")
GENERATED_REGISTRY_PATH: Final = Path(
    "changes/st-0703/generated/recorded-fixture-registry.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0703/manifest.yaml")
V4_HANDOFF_PATH: Final = Path("changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v4.yaml")
V4_RECONCILIATION_PATH: Final = Path("changes/st-0703/CANONICAL-RECONCILIATION-v4.md")
V4_APPROVAL_PATH: Final = Path("changes/st-0703/DESIGN-HANDOFF-APPROVAL-v4.yaml")
V5_DECISION_REQUEST_PATH: Final = Path("changes/st-0703/DESIGN-DECISION-REQUEST-v5.md")
V5_HANDOFF_PATH: Final = Path("changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v5.yaml")
V5_RECONCILIATION_PATH: Final = Path("changes/st-0703/CANONICAL-RECONCILIATION-v5.md")
V5_APPROVAL_PATH: Final = Path("changes/st-0703/DESIGN-HANDOFF-APPROVAL-v5.yaml")
V4_HANDOFF_SHA256: Final = (
    "7d384015c2975d7a718ff348cb4d1538a354f095cc0d9a2b0c76dbca5f6e4898"
)
V4_RECONCILIATION_SHA256: Final = (
    "6c3285712156781c9a107dfb5417f87896246c75e3158fec485f1ea07be54887"
)
V4_APPROVAL_SHA256: Final = (
    "ed717125191c26dc609c61341320f020be7883add1f0967096b20d11e60eb202"
)
V5_DECISION_REQUEST_SHA256: Final = (
    "e2cec557d0c412effd5ae4a7fa7d1069ff46579caada980a9c8dd7479a6a51cd"
)
V5_HANDOFF_SHA256: Final = (
    "ac8afef5f18b4602c099d27ad7f86f3880acb28be5e57badc47d45b27c3abe97"
)
V5_RECONCILIATION_SHA256: Final = (
    "65021265c8c5bd40bd8949eb876542e53400333bb615794d67418975873d6ac3"
)
V5_APPROVAL_SHA256: Final = (
    "3f3183275ed819349c2528bfd555d195d48b221f759bea42e29f8e941b048fb3"
)
V5_APPROVED_DECISIONS: Final = (
    "ST0703-V3-D1",
    "ST0703-V3-D2",
    "ST0703-V3-D3",
    "ST0703-V3-D4",
    "ST0703-V5-D5-CORRECTION",
)
V5_INHERITED_DECISION_KEYS: Final = (
    "provider_boundary",
    "provider_error_mapping",
    "recorded_exchange",
    "synthetic_pricing",
    "provenance_regeneration",
)
EXPECTED_IMPLEMENTATION_AUTHORITY: Final[dict[str, object]] = {
    "handoff": f"repo://{V5_HANDOFF_PATH.as_posix()}",
    "approval": f"repo://{V5_APPROVAL_PATH.as_posix()}",
    "reconciliation": f"repo://{V5_RECONCILIATION_PATH.as_posix()}",
    "decision_source": f"repo://{V5_DECISION_REQUEST_PATH.as_posix()}",
    "prior_handoff": f"repo://{V4_HANDOFF_PATH.as_posix()}",
    "prior_approval": f"repo://{V4_APPROVAL_PATH.as_posix()}",
    "prior_reconciliation": f"repo://{V4_RECONCILIATION_PATH.as_posix()}",
    "semantic_delta_from_approved_v4": {
        "d1_through_d4": "NONE",
        "d5": "ST0703-V5-D5-CORRECTION",
    },
    "replaced_decision": "ST0703-V3-D5",
    "approved_decisions": list(V5_APPROVED_DECISIONS),
    "authority": "ST0703_RECORDED_SCOPE_ONLY",
    "open_decisions": [],
}
PREDECESSOR_MANIFEST_PROJECTION_SHA256: Final = {
    Path("changes/st-0204/manifest.yaml"): (
        "60173bf51df0e352bc2caf88d2ac5db57a89c7bd6b459c8267b0cac16f5ce5c6"
    ),
    Path("changes/st-0701/manifest.yaml"): (
        "a0d5aad3b2c95ba7a365d0fc0be5a7825834f7a9639260823e2729c27391ad0b"
    ),
    Path("changes/st-0801/manifest.yaml"): (
        "7704359cb758e3bf35bbe88e91e41c7f484e8133f1ab7d4a139b2bafde7b2540"
    ),
}
IMPLEMENTATION_SOURCE_PATHS: Final = (
    Path(".github/workflows/ci.yml"),
    Path("Makefile"),
    Path("README.md"),
    Path("changes/st-0204/manifest.yaml"),
    Path("changes/st-0701/manifest.yaml"),
    Path("changes/st-0801/manifest.yaml"),
    Path("changes/st-0703/CANONICAL-RECONCILIATION-v3.md"),
    V4_RECONCILIATION_PATH,
    V5_RECONCILIATION_PATH,
    Path("changes/st-0703/DESIGN-HANDOFF-APPROVAL-v3.yaml"),
    V4_APPROVAL_PATH,
    V5_APPROVAL_PATH,
    Path("changes/st-0703/DESIGN-DECISION-REQUEST-v3.md"),
    V5_DECISION_REQUEST_PATH,
    Path("changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v2.yaml"),
    Path("changes/st-0703/DESIGN_HANDOFF_V1_ST0703_v3.yaml"),
    V4_HANDOFF_PATH,
    V5_HANDOFF_PATH,
    Path("changes/st-0703/README.md"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/adapters/openai_responses.py"),
    Path("python/raos/adapters/recorded_ai.py"),
    Path("python/raos/domain/ai/provider.py"),
    Path("python/raos/ports/ai_provider.py"),
    Path("scripts/build_st0703_recorded_adapter.py"),
    Path("scripts/ci_job.sh"),
    Path("scripts/run_network_denied.sh"),
    Path("tests/st0102/test_toolchain_contract.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("tests/st0703/conftest.py"),
    Path("tests/st0703/test_adapter.py"),
    Path("tests/st0703/test_generation.py"),
    Path("tests/st0703/test_implementation_manifest.py"),
    Path("tests/st0703/test_recorded_support.py"),
)
EXPECTED_CONTRACT_SHA256: Final = (
    "2a8150e5b80b13d118a982e84a30692955e4e9b62272896cdfe2720d56ffa654"
)
EXPECTED_PYPROJECT_SHA256: Final = (
    "0c4e1f0ac9d9e4ed1f19bee3ec64c4860a2932257ed4e1ea6fdf13422c0718b6"
)
EXPECTED_UV_LOCK_SHA256: Final = (
    "90d79255a5bd0a6d0c918b8f496dec0a1bd11fb25316cdc5b1a9526c2eed3729"
)
EXPECTED_UV_CONFIG_SHA256: Final = (
    "02303c42f583b4a2106a7b9185bd0fad5264c4991e656ad58739558045f3ab37"
)
MAX_CONTRACT_BYTES: Final = 128 * 1024
MAX_FIXTURE_BYTES: Final = 64 * 1024
MAX_PYPROJECT_BYTES: Final = 64 * 1024
MAX_UV_LOCK_BYTES: Final = 256 * 1024
MAX_UV_CONFIG_BYTES: Final = 64 * 1024
MAX_PROVENANCE_SOURCE_BYTES: Final = 4 * 1024 * 1024
MAX_JSON_DEPTH: Final = 64
MAX_JSON_VISITS: Final = 20_000
EXPECTED_TOP_LEVEL_KEYS: Final = {
    "expected",
    "expected_request",
    "fixture_version",
    "pricing",
    "scenario",
    "synthetic",
    "transport",
}
EXPECTED_REQUEST: Final = {
    "input": [
        {
            "content": "SYNTHETIC_TEST_ONLY developer instruction.",
            "role": "developer",
        },
        {
            "content": "SYNTHETIC_TEST_ONLY input record.",
            "role": "user",
        },
    ],
    "max_output_tokens": 128,
    "model": "raos-synthetic-model-v1",
    "reasoning": {"effort": "medium"},
    "store": False,
    "text": {
        "format": {
            "name": "raos_synthetic_output_v1",
            "schema": {
                "$id": "urn:raos:synthetic:st0703:output:v1",
                "additionalProperties": False,
                "properties": {
                    "label": {"type": "string"},
                    "score": {"type": "integer"},
                },
                "required": ["label", "score"],
                "type": "object",
            },
            "strict": True,
            "type": "json_schema",
        }
    },
    "tools": [],
}
EXPECTED_RESULTS_BY_SCENARIO: Final[dict[str, dict[str, object]]] = {
    "structured_success": {
        "incomplete_reason": None,
        "kind": "ProviderSuccess",
        "output": {"label": "synthetic-pass", "score": 7},
        "provider_error_code": None,
        "recorder_calls": 1,
        "retryable": None,
        "usage": {
            "cached_input_tokens": 8,
            "input_tokens": 32,
            "output_tokens": 11,
        },
    },
    "completed_refusal": {
        "incomplete_reason": None,
        "kind": "ProviderRefusal",
        "output": None,
        "provider_error_code": None,
        "recorder_calls": 1,
        "refusal_code": "AI-PRV-005",
        "retryable": None,
        "usage": {
            "cached_input_tokens": 0,
            "input_tokens": 24,
            "output_tokens": 6,
        },
    },
    "incomplete_max_output_tokens": {
        "incomplete_reason": "max_output_tokens",
        "kind": "ProviderIncomplete",
        "output": None,
        "provider_error_code": None,
        "recorder_calls": 1,
        "retryable": None,
        "usage": {
            "cached_input_tokens": 10,
            "input_tokens": 40,
            "output_tokens": 128,
        },
    },
    "incomplete_content_filter": {
        "incomplete_reason": "content_filter",
        "kind": "ProviderIncomplete",
        "output": None,
        "provider_error_code": None,
        "recorder_calls": 1,
        "retryable": None,
        "usage": {
            "cached_input_tokens": 4,
            "input_tokens": 36,
            "output_tokens": 17,
        },
    },
    "rate_limit_429": {
        "incomplete_reason": None,
        "kind": "ProviderError",
        "output": None,
        "provider_error_code": "RATE_LIMIT",
        "recorder_calls": 0,
        "retryable": True,
        "usage": None,
    },
}
PRICING_KEYS: Final = frozenset({"expected_cost_jpy", "mode", "model_id", "quote_id"})
EXPECTED_PRICING_BY_SCENARIO: Final[dict[str, dict[str, object]]] = {
    "structured_success": {
        "expected_cost_jpy": 7,
        "mode": "SYNTHETIC_TEST_ONLY",
        "model_id": "raos-synthetic-model-v1",
        "quote_id": "st0703-synthetic-quote-v1",
    },
    "completed_refusal": {
        "expected_cost_jpy": 3,
        "mode": "SYNTHETIC_TEST_ONLY",
        "model_id": "raos-synthetic-model-v1",
        "quote_id": "st0703-synthetic-quote-v1",
    },
    "incomplete_max_output_tokens": {
        "expected_cost_jpy": 11,
        "mode": "SYNTHETIC_TEST_ONLY",
        "model_id": "raos-synthetic-model-v1",
        "quote_id": "st0703-synthetic-quote-v1",
    },
    "incomplete_content_filter": {
        "expected_cost_jpy": 5,
        "mode": "SYNTHETIC_TEST_ONLY",
        "model_id": "raos-synthetic-model-v1",
        "quote_id": "st0703-synthetic-quote-v1",
    },
    "rate_limit_429": {
        "expected_cost_jpy": None,
        "mode": "NOT_CALCULATED",
        "model_id": "raos-synthetic-model-v1",
        "quote_id": "st0703-synthetic-quote-v1",
    },
}
TRANSPORT_KEYS: Final = frozenset({"body", "kind", "status_code"})
RESPONSE_BODY_KEYS: Final = frozenset(
    {
        "background",
        "completed_at",
        "created_at",
        "error",
        "id",
        "incomplete_details",
        "instructions",
        "max_output_tokens",
        "metadata",
        "model",
        "object",
        "output",
        "parallel_tool_calls",
        "previous_response_id",
        "reasoning",
        "status",
        "store",
        "temperature",
        "text",
        "tool_choice",
        "tools",
        "top_p",
        "truncation",
        "usage",
    }
)
RESPONSE_USAGE_KEYS: Final = frozenset(
    {
        "input_tokens",
        "input_tokens_details",
        "output_tokens",
        "output_tokens_details",
        "total_tokens",
    }
)
MESSAGE_KEYS: Final = frozenset({"content", "id", "role", "status", "type"})
OUTPUT_TEXT_KEYS: Final = frozenset({"annotations", "logprobs", "text", "type"})
REFUSAL_KEYS: Final = frozenset({"refusal", "type"})
EXPECTED_RESPONSE_ROUTES: Final = {
    "structured_success": {
        "completed_at": 1785974401,
        "content_kind": "success",
        "created_at": 1785974400,
        "incomplete_reason": None,
        "message_id": "msg_synthetic_success_001",
        "message_status": "completed",
        "partial_text": None,
        "reasoning_tokens": 0,
        "response_id": "resp_synthetic_success_001",
        "status": "completed",
    },
    "completed_refusal": {
        "completed_at": 1785974402,
        "content_kind": "refusal",
        "created_at": 1785974401,
        "incomplete_reason": None,
        "message_id": "msg_synthetic_refusal_001",
        "message_status": "completed",
        "partial_text": None,
        "reasoning_tokens": 0,
        "response_id": "resp_synthetic_refusal_001",
        "status": "completed",
    },
    "incomplete_max_output_tokens": {
        "completed_at": None,
        "content_kind": "partial",
        "created_at": 1785974402,
        "incomplete_reason": "max_output_tokens",
        "message_id": "msg_synthetic_incomplete_max_001",
        "message_status": "incomplete",
        "partial_text": '{"label":',
        "reasoning_tokens": 12,
        "response_id": "resp_synthetic_incomplete_max_001",
        "status": "incomplete",
    },
    "incomplete_content_filter": {
        "completed_at": None,
        "content_kind": "partial",
        "created_at": 1785974403,
        "incomplete_reason": "content_filter",
        "message_id": "msg_synthetic_incomplete_filter_001",
        "message_status": "incomplete",
        "partial_text": '{"label":"synthetic',
        "reasoning_tokens": 0,
        "response_id": "resp_synthetic_incomplete_filter_001",
        "status": "incomplete",
    },
}
EXPECTED_RATE_LIMIT_ERROR: Final = {
    "code": "rate_limit_exceeded",
    "message": "SYNTHETIC_TEST_ONLY rate-limit diagnostic canary.",
    "param": None,
    "type": "rate_limit_error",
}
FORBIDDEN_FIXTURE_MARKERS: Final = (
    b"sk-",
    b"secret://",
    b"authorization",
    b"https://",
)
FORBIDDEN_DECODED_FIXTURE_MARKERS: Final = (
    "authorization",
    "credential",
    "header",
    "private key",
    "private-key",
    "private_key",
    "privatekey",
    "bearer",
    "api key",
    "api-key",
    "api_key",
    "apikey",
    "access token",
    "access-token",
    "access_token",
    "accesstoken",
    "client secret",
    "client-secret",
    "client_secret",
    "clientsecret",
    "password",
    "cookie",
    "set cookie",
    "set-cookie",
    "set_cookie",
    "secret://",
    "sk-",
)
URI_SCHEME_PATTERN: Final = re.compile(r"^[a-z][a-z0-9+.-]*:", re.ASCII)
OPENAI_REQUIREMENT_PATTERN: Final = re.compile(
    r"^openai(?=\s|[<>=!~;\[]|$)", re.IGNORECASE | re.ASCII
)
OPENAI_REQUIREMENT: Final = "openai==2.52.0"
OPENAI_VERSION: Final = "2.52.0"
OPENAI_PYPI_SOURCE: Final = {"registry": "https://pypi.org/simple"}
OPENAI_SDIST: Final = {
    "url": "https://files.pythonhosted.org/packages/bb/5a/"
    "c45fa035cd72c70ebe67c6e079e3adf871492382634f69e3dff62c43597d/"
    "openai-2.52.0.tar.gz",
    "hash": "sha256:7c736d592f81471ce1f734838390983c4d8c8aecff23dcd36e600a58e5032d9c",
    "size": 1098876,
    "upload-time": "2026-07-31T15:13:03.228Z",
}
OPENAI_WHEEL: Final = {
    "url": "https://files.pythonhosted.org/packages/a1/ac/"
    "ceb40c995df49533ad4dcff6c37f0d85cf14446a212363fc9d2f927e60b4/"
    "openai-2.52.0-py3-none-any.whl",
    "hash": "sha256:f97e231d9a8fa69ab55897df1080f02d99913fb0a30e3ee56ea16a1eb6c2d434",
    "size": 1659569,
    "upload-time": "2026-07-31T15:13:01.145Z",
}
EXPECTED_UV_CONFIGURATION: Final = {
    "required-version": "==0.12.1",
    "no-sources": True,
    "python-downloads": "manual",
    "python-preference": "only-managed",
    "prerelease": "disallow",
    "resolution": "highest",
    "exclude-newer": "2026-08-01T16:50:16Z",
    "index-strategy": "first-index",
    "keyring-provider": "disabled",
    "link-mode": "copy",
    "index": [
        {
            "name": "pypi",
            "url": "https://pypi.org/simple",
            "default": True,
        }
    ],
}


@dataclass(frozen=True, slots=True)
class FixtureSpec:
    path: str
    scenario: str
    contract_expected: str
    result_kind: str
    status_code: int
    byte_count: int
    sha256: str


FIXTURE_SPECS: Final = (
    FixtureSpec(
        path="error-rate-limit-429.json",
        scenario="rate_limit_429",
        contract_expected="ProviderError.RATE_LIMIT",
        result_kind="ProviderError",
        status_code=429,
        byte_count=1736,
        sha256="e0ce4372d287766cf4b5f3ec1f0afcaf17b49dc41939c379e64c4773dac2eb72",
    ),
    FixtureSpec(
        path="incomplete-content-filter.json",
        scenario="incomplete_content_filter",
        contract_expected="ProviderIncomplete.CONTENT_FILTER",
        result_kind="ProviderIncomplete",
        status_code=200,
        byte_count=3287,
        sha256="f894f71eb54e751a58b31bd61e18ac846841f58c59e901ae4d1f1c137d783e58",
    ),
    FixtureSpec(
        path="incomplete-max-output-tokens.json",
        scenario="incomplete_max_output_tokens",
        contract_expected="ProviderIncomplete.MAX_OUTPUT_TOKENS",
        result_kind="ProviderIncomplete",
        status_code=200,
        byte_count=3286,
        sha256="fe7bf867a169f05e615ef3c06146ea1a773999518c27ad58bb2ac1b3886be6d7",
    ),
    FixtureSpec(
        path="refusal-completed.json",
        scenario="completed_refusal",
        contract_expected="ProviderRefusal",
        result_kind="ProviderRefusal",
        status_code=200,
        byte_count=3189,
        sha256="f77119e429d422b4e85c50537df14136f5c92e89f30549b26f18051e9e60e350",
    ),
    FixtureSpec(
        path="success-structured.json",
        scenario="structured_success",
        contract_expected="ProviderSuccess",
        result_kind="ProviderSuccess",
        status_code=200,
        byte_count=3282,
        sha256="a6a7506c8201a979cdba2cf1e41c9c9d7288d801cf6f2f72aa5e6684e6da168c",
    ),
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
    result: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _normalized_relative(value: str, *, label: str) -> Path:
    if type(value) is not str or not value or "\\" in value:
        raise RuntimeError(f"{label} must be a normalized POSIX relative path")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise RuntimeError(f"{label} must be a normalized POSIX relative path")
    return Path(*pure.parts)


def _require_real_directory(path: Path, *, label: str) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a real directory")


def _require_real_ancestors(root: Path, relative_parent: Path, *, label: str) -> None:
    _require_real_directory(root, label="repository root")
    current = root
    for part in relative_parent.parts:
        current /= part
        _require_real_directory(current, label=f"{label} ancestor")


def _read_regular(
    root: Path,
    relative: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    relative = _normalized_relative(relative.as_posix(), label=label)
    _require_real_ancestors(root, relative.parent, label=label)
    path = root / relative
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    if before.st_nlink != 1:
        raise RuntimeError(f"{label} must have exactly one filesystem link")
    if before.st_size <= 0 or before.st_size > maximum_bytes:
        raise RuntimeError(f"{label} has an invalid byte size")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_dev != before.st_dev
            or opened.st_ino != before.st_ino
            or opened.st_size != before.st_size
            or opened.st_nlink != 1
        ):
            raise RuntimeError(f"{label} changed during validation")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, maximum_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum_bytes:
                raise RuntimeError(f"{label} exceeds its byte limit")
        content = b"".join(chunks)
        if len(content) != opened.st_size:
            raise RuntimeError(f"{label} changed during validation")
        return content
    finally:
        os.close(descriptor)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number {value!r}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object member {key!r}")
        result[key] = value
    return result


def _bounded_graph(value: object, *, label: str) -> None:
    visits = 0
    active: set[int] = set()

    def visit(item: object, depth: int) -> None:
        nonlocal visits
        visits += 1
        if visits > MAX_JSON_VISITS or depth > MAX_JSON_DEPTH:
            raise RuntimeError(f"{label} exceeds the JSON graph limit")
        if item is None or type(item) in {bool, int, str}:
            return
        if type(item) is float:
            if not math.isfinite(item):
                raise RuntimeError(f"{label} contains a non-finite number")
            return
        if not isinstance(item, (Mapping, list, tuple)):
            return
        identity = id(item)
        if identity in active:
            raise RuntimeError(f"{label} contains a graph cycle")
        active.add(identity)
        try:
            children = item.values() if isinstance(item, Mapping) else item
            for child in children:
                visit(child, depth + 1)
        finally:
            active.remove(identity)

    visit(value, 0)


def _strict_yaml(content: bytes, *, label: str) -> object:
    try:
        text = content.decode("utf-8", errors="strict")
        value = yaml.load(text, Loader=UniqueKeyLoader)
    except (UnicodeDecodeError, yaml.YAMLError, RecursionError) as exc:
        raise RuntimeError(f"{label} must be strict YAML") from exc
    _bounded_graph(value, label=label)
    return value


def _strict_toml(content: bytes, *, label: str) -> dict[str, object]:
    try:
        value = tomllib.loads(content.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError, RecursionError) as exc:
        raise RuntimeError(f"{label} must be strict TOML") from exc
    _bounded_graph(value, label=label)
    return _mapping(value, label=label)


def _strict_fixture_json(content: bytes, *, label: str) -> dict[str, object]:
    if content.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError(f"{label} must not contain a UTF-8 BOM")
    if b"\r" in content or not content.endswith(b"\n"):
        raise RuntimeError(f"{label} must use LF and end with one LF")
    try:
        value = json.loads(
            content.decode("utf-8", errors="strict"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise RuntimeError(f"{label} must be strict JSON") from exc
    if not isinstance(value, dict) or not all(type(key) is str for key in value):
        raise RuntimeError(f"{label} must contain one JSON object")
    _bounded_graph(value, label=label)
    return cast(dict[str, object], value)


def _normalized_fixture_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _validate_fixture_text(value: str, *, label: str) -> None:
    normalized = _normalized_fixture_text(value)
    if "http://" in normalized or "https://" in normalized:
        raise RuntimeError(f"{label} contains forbidden URI material")
    if any(marker in normalized for marker in FORBIDDEN_DECODED_FIXTURE_MARKERS):
        raise RuntimeError(f"{label} contains forbidden decoded material")

    candidate = normalized.strip()
    if not (
        URI_SCHEME_PATTERN.match(candidate) is not None or candidate.startswith("//")
    ):
        return
    try:
        parsed = urlsplit(candidate)
    except ValueError as exc:
        raise RuntimeError(f"{label} contains malformed URI material") from exc
    if parsed.scheme in {"http", "https"}:
        raise RuntimeError(f"{label} contains forbidden URI material")
    if parsed.username is not None or parsed.password is not None:
        raise RuntimeError(f"{label} contains forbidden URI material")
    if parsed.query or parsed.fragment or "?" in candidate or "#" in candidate:
        raise RuntimeError(f"{label} contains forbidden URI material")


def _validate_decoded_fixture_material(value: object, *, label: str) -> None:
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is str:
            _validate_fixture_text(item, label=label)
        elif isinstance(item, Mapping):
            for key, child in item.items():
                if type(key) is str:
                    _validate_fixture_text(key, label=label)
                pending.append(child)
        elif isinstance(item, (list, tuple)):
            pending.extend(item)


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(type(key) is str for key in value):
        raise RuntimeError(f"{label} must be an object")
    return cast(dict[str, object], value)


def _sequence(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be an array")
    return value


def _read_exact_authority_source(
    root: Path,
    relative: Path,
    expected_sha256: str,
    *,
    label: str,
) -> bytes:
    content = _read_regular(
        root,
        relative,
        label=label,
        maximum_bytes=MAX_PROVENANCE_SOURCE_BYTES,
    )
    if _sha256(content) != expected_sha256:
        raise RuntimeError(f"{label} hash drift")
    return content


def _read_authority_mapping(
    root: Path,
    relative: Path,
    expected_sha256: str,
    *,
    root_key: str,
    label: str,
) -> dict[str, object]:
    content = _read_exact_authority_source(
        root,
        relative,
        expected_sha256,
        label=label,
    )
    document = _mapping(_strict_yaml(content, label=label), label=label)
    if set(document) != {root_key}:
        raise RuntimeError(f"{label} root structure drift")
    return _mapping(document.get(root_key), label=f"{label} payload")


def _validate_v5_authority(root: Path, contract: dict[str, object]) -> None:
    authority = _mapping(
        contract.get("implementation_authority"),
        label="contract implementation authority",
    )
    if authority != EXPECTED_IMPLEMENTATION_AUTHORITY:
        raise RuntimeError("ST-0703 contract V5 implementation authority drift")

    provenance = _mapping(contract.get("provenance"), label="contract provenance")
    canonical_inputs = _sequence(
        provenance.get("canonical_inputs"),
        label="contract canonical_inputs",
    )
    observed_pins: dict[str, str] = {}
    for offset, raw_entry in enumerate(canonical_inputs):
        entry = _mapping(raw_entry, label=f"contract canonical_inputs[{offset}]")
        uri = entry.get("uri")
        digest = entry.get("sha256")
        if type(uri) is str and type(digest) is str:
            observed_pins[uri] = digest
    expected_pins = {
        f"repo://{V4_HANDOFF_PATH.as_posix()}": V4_HANDOFF_SHA256,
        f"repo://{V4_RECONCILIATION_PATH.as_posix()}": V4_RECONCILIATION_SHA256,
        f"repo://{V4_APPROVAL_PATH.as_posix()}": V4_APPROVAL_SHA256,
        f"repo://{V5_DECISION_REQUEST_PATH.as_posix()}": (V5_DECISION_REQUEST_SHA256),
        f"repo://{V5_HANDOFF_PATH.as_posix()}": V5_HANDOFF_SHA256,
        f"repo://{V5_RECONCILIATION_PATH.as_posix()}": V5_RECONCILIATION_SHA256,
        f"repo://{V5_APPROVAL_PATH.as_posix()}": V5_APPROVAL_SHA256,
    }
    if any(observed_pins.get(uri) != digest for uri, digest in expected_pins.items()):
        raise RuntimeError("ST-0703 contract V5 authority provenance drift")

    _read_exact_authority_source(
        root,
        V4_RECONCILIATION_PATH,
        V4_RECONCILIATION_SHA256,
        label="ST-0703 V4 reconciliation",
    )
    _read_exact_authority_source(
        root,
        V5_DECISION_REQUEST_PATH,
        V5_DECISION_REQUEST_SHA256,
        label="ST-0703 V5 decision request",
    )
    _read_exact_authority_source(
        root,
        V5_RECONCILIATION_PATH,
        V5_RECONCILIATION_SHA256,
        label="ST-0703 V5 reconciliation",
    )
    v4_handoff = _read_authority_mapping(
        root,
        V4_HANDOFF_PATH,
        V4_HANDOFF_SHA256,
        root_key="DESIGN_HANDOFF_V1",
        label="ST-0703 V4 handoff",
    )
    v4_approval = _read_authority_mapping(
        root,
        V4_APPROVAL_PATH,
        V4_APPROVAL_SHA256,
        root_key="DESIGN_HANDOFF_APPROVAL_V1",
        label="ST-0703 V4 approval",
    )
    v5_handoff = _read_authority_mapping(
        root,
        V5_HANDOFF_PATH,
        V5_HANDOFF_SHA256,
        root_key="DESIGN_HANDOFF_V1",
        label="ST-0703 V5 handoff",
    )
    v5_approval = _read_authority_mapping(
        root,
        V5_APPROVAL_PATH,
        V5_APPROVAL_SHA256,
        root_key="DESIGN_HANDOFF_APPROVAL_V1",
        label="ST-0703 V5 approval",
    )

    handoff_keys = {
        "document_version",
        "approved_story",
        "approved_scope",
        "source_design_refs",
        "decision",
        "rationale",
        "rejected_alternatives",
        "constraints",
        "security_and_approval_gates",
        "acceptance_criteria",
        "required_test_evidence",
        "deferred_external_decisions",
        "open_decisions",
        "approval",
    }
    if set(v4_handoff) != handoff_keys or set(v5_handoff) != handoff_keys:
        raise RuntimeError("ST-0703 V4/V5 handoff structure drift")
    if (
        v4_handoff.get("document_version") != 4
        or v5_handoff.get("document_version") != 5
        or v4_handoff.get("approved_story") != "ST-0703"
        or v5_handoff.get("approved_story") != "ST-0703"
        or v4_handoff.get("open_decisions") != []
        or v5_handoff.get("open_decisions") != []
    ):
        raise RuntimeError("ST-0703 V4/V5 handoff identity drift")

    v4_decision = _mapping(v4_handoff.get("decision"), label="V4 decision")
    v5_decision = _mapping(v5_handoff.get("decision"), label="V5 decision")
    for key in V5_INHERITED_DECISION_KEYS:
        if v5_decision.get(key) != v4_decision.get(key):
            raise RuntimeError(f"ST-0703 V5 inherited decision drift: {key}")

    expected_authority_revision: dict[str, object] = {
        "kind": "D5_CROSS_STORY_BOUNDARY_CORRECTION",
        "semantic_delta_from_approved_v4": {
            "d1_through_d4": "NONE",
            "d5": "REPLACED_BY_ST0703_V5_D5_CORRECTION",
        },
        "inherited_approved_decisions": list(V5_APPROVED_DECISIONS[:4]),
        "replaced_decision": "ST0703-V3-D5",
        "proposed_decision": "ST0703-V5-D5-CORRECTION",
        "correction_source": {
            "decision_request": {
                "uri": f"repo://{V5_DECISION_REQUEST_PATH.as_posix()}",
                "sha256": V5_DECISION_REQUEST_SHA256,
            }
        },
        "prior_approved_authority": {
            "handoff": {
                "uri": f"repo://{V4_HANDOFF_PATH.as_posix()}",
                "sha256": V4_HANDOFF_SHA256,
            },
            "reconciliation": {
                "uri": f"repo://{V4_RECONCILIATION_PATH.as_posix()}",
                "sha256": V4_RECONCILIATION_SHA256,
            },
            "approval": {
                "uri": f"repo://{V4_APPROVAL_PATH.as_posix()}",
                "sha256": V4_APPROVAL_SHA256,
            },
            "mutation": "forbidden",
        },
        "v5_approval_requirement": {
            "exact_handoff_sha256": "required",
            "exact_reconciliation_sha256": "required",
            "approval_artifact": f"repo://{V5_APPROVAL_PATH.as_posix()}",
            "implementation_authority_before_approval": "NONE",
        },
    }
    if v5_decision.get("authority_revision") != expected_authority_revision:
        raise RuntimeError("ST-0703 V5 authority revision drift")

    gate_wiring = _mapping(v5_decision.get("gate_wiring"), label="V5 gate wiring")
    expected_gate_keys = {
        "decision_id",
        "make_targets",
        "config_check_owner_target",
        "openai_recorded_gate",
        "ci_repository_policy_addition",
        "ci_unit_addition",
        "new_workflow_or_job",
        "workflow_secrets",
        "live_provider_or_network",
    }
    expected_config_check: dict[str, object] = {
        "exact_header": "config-check: | python-sync",
        "recipe": (
            "PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python "
            "scripts/build_st0204_config_loader.py --check"
        ),
        "final_delta_from_base": "NONE",
    }
    expected_openai_gate: dict[str, object] = {
        "prerequisites": [
            "ai-registry-check",
            "openai-recorded-check",
            "openai-recorded-static",
            "openai-recorded-test",
        ],
        "config_check_prerequisite": "forbidden",
        "direct_predecessor_command": (
            "PYTHONDONTWRITEBYTECODE=1 $(UV_READONLY_RUN) python "
            "scripts/build_st0204_config_loader.py --check"
        ),
        "direct_predecessor_command_count": 1,
        "hydration": "explicit and separate before the gate",
        "recursive_make": "forbidden",
        "python_sync_uv_run_sync_install_hydrate": "forbidden",
        "network_cache_sync_environment_credential_external_service": "forbidden",
    }
    if (
        set(gate_wiring) != expected_gate_keys
        or gate_wiring.get("decision_id") != "ST0703-V5-D5-CORRECTION"
        or gate_wiring.get("config_check_owner_target") != expected_config_check
        or gate_wiring.get("openai_recorded_gate") != expected_openai_gate
        or gate_wiring.get("ci_repository_policy_addition") != "openai-recorded-check"
        or gate_wiring.get("ci_unit_addition") != "isolated tests/st0703 process"
        or gate_wiring.get("new_workflow_or_job") is not False
        or gate_wiring.get("workflow_secrets") != "forbidden"
        or gate_wiring.get("live_provider_or_network") != "forbidden"
    ):
        raise RuntimeError("ST-0703 V5 gate wiring drift")

    if (
        v4_approval.get("status") != "APPROVED_FOR_IMPLEMENTATION"
        or v4_approval.get("implementation_authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or v4_approval.get("handoff_sha256") != V4_HANDOFF_SHA256
        or v4_approval.get("reconciliation_sha256") != V4_RECONCILIATION_SHA256
        or v4_approval.get("approved_decisions")
        != [*V5_APPROVED_DECISIONS[:4], "ST0703-V3-D5"]
        or v4_approval.get("open_decisions") != []
    ):
        raise RuntimeError("ST-0703 V4 approval structure drift")

    if (
        v5_approval.get("story_id") != "ST-0703"
        or v5_approval.get("handoff_uri") != f"repo://{V5_HANDOFF_PATH.as_posix()}"
        or v5_approval.get("handoff_sha256") != V5_HANDOFF_SHA256
        or v5_approval.get("reconciliation_uri")
        != f"repo://{V5_RECONCILIATION_PATH.as_posix()}"
        or v5_approval.get("reconciliation_sha256") != V5_RECONCILIATION_SHA256
        or v5_approval.get("decision_source_uri")
        != f"repo://{V5_DECISION_REQUEST_PATH.as_posix()}"
        or v5_approval.get("decision_source_sha256") != V5_DECISION_REQUEST_SHA256
        or v5_approval.get("prior_handoff_sha256") != V4_HANDOFF_SHA256
        or v5_approval.get("prior_reconciliation_sha256") != V4_RECONCILIATION_SHA256
        or v5_approval.get("prior_approval_sha256") != V4_APPROVAL_SHA256
        or v5_approval.get("semantic_delta_from_approved_v4")
        != {"d1_through_d4": "NONE", "d5": "ST0703-V5-D5-CORRECTION"}
        or v5_approval.get("replaced_decision") != "ST0703-V3-D5"
        or v5_approval.get("status") != "APPROVED_FOR_IMPLEMENTATION"
        or v5_approval.get("implementation_authority") != "ST0703_RECORDED_SCOPE_ONLY"
        or v5_approval.get("approved_decisions") != list(V5_APPROVED_DECISIONS)
        or v5_approval.get("open_decisions") != []
    ):
        raise RuntimeError("ST-0703 V5 approval structure drift")

    boundaries = _mapping(v5_approval.get("boundaries"), label="V5 boundaries")
    if (
        boundaries.get("semantic_story_changes") != ["ST-0703"]
        or boundaries.get("mechanical_owner_regeneration")
        != ["ST-0204 manifest", "ST-0701 manifest", "ST-0801 manifest"]
        or boundaries.get("config_check_owner_target") != "EXACT_BASE_SEMANTICS"
        or boundaries.get("st0204_semantic_change") != "NOT_AUTHORIZED"
        or boundaries.get("excluded_story_changes")
        != ["ST-0106", "ST-0107", "ST-0202", "ST-1203", "ST-1204"]
    ):
        raise RuntimeError("ST-0703 V5 approval boundary drift")


def _validate_predecessor_manifest_semantics(root: Path) -> dict[str, str]:
    """Verify that owner regeneration changed only source byte metadata."""

    observed: dict[str, str] = {}
    for (
        relative,
        expected_projection_sha256,
    ) in PREDECESSOR_MANIFEST_PROJECTION_SHA256.items():
        label = f"predecessor manifest {relative.as_posix()}"
        content = _read_regular(
            root,
            relative,
            label=label,
            maximum_bytes=MAX_PROVENANCE_SOURCE_BYTES,
        )
        document = _mapping(_strict_yaml(content, label=label), label=label)
        projection = copy.deepcopy(document)
        source_artifacts = _sequence(
            projection.get("source_artifacts"),
            label=f"{label} source_artifacts",
        )
        if not source_artifacts:
            raise RuntimeError(f"{label} source_artifacts must not be empty")

        seen_uris: set[str] = set()
        for offset, raw_artifact in enumerate(source_artifacts):
            artifact_label = f"{label} source_artifacts[{offset}]"
            artifact = _mapping(raw_artifact, label=artifact_label)
            if set(artifact) != {"uri", "bytes", "sha256"}:
                raise RuntimeError(f"{artifact_label} must contain exact keys")

            uri = artifact.get("uri")
            if type(uri) is not str or not uri.startswith("repo://"):
                raise RuntimeError(
                    f"{artifact_label} URI must be a normalized repository URI"
                )
            uri_text = uri
            uri_path = _normalized_relative(
                uri_text.removeprefix("repo://"),
                label=f"{artifact_label} URI",
            )
            if uri_text != f"repo://{uri_path.as_posix()}":
                raise RuntimeError(
                    f"{artifact_label} URI must be a normalized repository URI"
                )
            if uri_text in seen_uris:
                raise RuntimeError(f"{label} source artifact URI duplicated")

            byte_count = artifact.get("bytes")
            if type(byte_count) is not int or byte_count <= 0:
                raise RuntimeError(
                    f"{artifact_label} byte count must be a positive integer"
                )
            digest = artifact.get("sha256")
            if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise RuntimeError(f"{artifact_label} digest must be lowercase SHA-256")

            seen_uris.add(uri_text)
            artifact["bytes"] = 0
            artifact["sha256"] = "0" * 64

        try:
            canonical_projection = _canonical_json(projection).encode("utf-8")
        except (TypeError, ValueError, RecursionError) as exc:
            raise RuntimeError(f"{label} projection must be canonical JSON") from exc
        projection_sha256 = _sha256(canonical_projection)
        if projection_sha256 != expected_projection_sha256:
            raise RuntimeError(f"{label} semantic projection drift")
        observed[relative.as_posix()] = projection_sha256

    return observed


def _validate_contract_provenance(
    root: Path, document: dict[str, object]
) -> list[dict[str, str]]:
    provenance = _mapping(document.get("provenance"), label="contract provenance")
    expected_groups = {
        "canonical_inputs": {"sha256", "uri"},
        "predecessors": {"sha256", "story_id", "uri"},
        "provider_contracts": {"sha256", "uri"},
    }
    if set(provenance) != set(expected_groups):
        raise RuntimeError("ST-0703 contract provenance groups drift")

    records: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for group, expected_keys in expected_groups.items():
        entries = _sequence(provenance.get(group), label=f"contract {group}")
        if not entries:
            raise RuntimeError("ST-0703 contract provenance must not be empty")
        for offset, raw_entry in enumerate(entries):
            entry = _mapping(raw_entry, label=f"contract {group}[{offset}]")
            if set(entry) != expected_keys:
                raise RuntimeError("ST-0703 contract provenance entry drift")
            uri = entry.get("uri")
            expected_sha256 = entry.get("sha256")
            if (
                type(uri) is not str
                or not uri.startswith("repo://")
                or type(expected_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
            ):
                raise RuntimeError("ST-0703 contract provenance entry drift")
            relative = _normalized_relative(
                uri.removeprefix("repo://"),
                label="contract provenance path",
            )
            path_string = relative.as_posix()
            if path_string in seen_paths:
                raise RuntimeError("ST-0703 contract provenance path duplicated")
            if "story_id" in expected_keys:
                story_id = entry.get("story_id")
                if type(story_id) is not str or not story_id:
                    raise RuntimeError("ST-0703 contract provenance entry drift")
            content = _read_regular(
                root,
                relative,
                label="ST-0703 provenance source",
                maximum_bytes=MAX_PROVENANCE_SOURCE_BYTES,
            )
            if _sha256(content) != expected_sha256:
                raise RuntimeError("ST-0703 provenance source hash drift")
            records.append({"path": path_string, "sha256": expected_sha256})
            seen_paths.add(path_string)
    return records


def _contract_inventory(
    root: Path,
) -> tuple[
    dict[str, tuple[str, str]],
    dict[str, object],
    list[dict[str, str]],
]:
    content = _read_regular(
        root,
        CONTRACT_PATH,
        label="ST-0703 contract",
        maximum_bytes=MAX_CONTRACT_BYTES,
    )
    if _sha256(content) != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("ST-0703 contract hash drift")
    document = _mapping(
        _strict_yaml(content, label="ST-0703 contract"), label="contract"
    )
    provenance_records = _validate_contract_provenance(root, document)
    _validate_v5_authority(root, document)
    story = _mapping(document.get("story"), label="contract story")
    if story.get("open_decisions") != []:
        raise RuntimeError("ST-0703 contract must retain open_decisions: []")
    sdk = _mapping(document.get("official_sdk"), label="official_sdk")
    if sdk.get("exact_requirement") != OPENAI_REQUIREMENT:
        raise RuntimeError("ST-0703 SDK contract drift")

    fixture_inventory = _mapping(
        document.get("fixture_inventory"), label="fixture_inventory"
    )
    if fixture_inventory.get("root") != FIXTURE_ROOT.as_posix():
        raise RuntimeError("ST-0703 fixture root contract drift")
    if fixture_inventory.get("format") != "STRICT_UTF8_LF_JSON":
        raise RuntimeError("ST-0703 fixture format contract drift")
    entries = _sequence(fixture_inventory.get("files"), label="fixture files")
    inventory: dict[str, tuple[str, str]] = {}
    scenarios: set[str] = set()
    for offset, raw_entry in enumerate(entries):
        entry = _mapping(raw_entry, label=f"fixture files[{offset}]")
        if set(entry) != {"path", "scenario", "expected"}:
            raise RuntimeError("fixture contract entries require exact keys")
        path_value = entry.get("path")
        scenario = entry.get("scenario")
        expected = entry.get("expected")
        if not all(
            type(value) is str and value for value in (path_value, scenario, expected)
        ):
            raise RuntimeError("fixture contract entries require non-empty strings")
        path_string = cast(str, path_value)
        normalized = _normalized_relative(path_string, label="fixture contract path")
        if len(normalized.parts) != 1 or normalized.suffix != ".json":
            raise RuntimeError("fixture contract path must be one JSON basename")
        if path_string in inventory or cast(str, scenario) in scenarios:
            raise RuntimeError("fixture contract paths and scenarios must be unique")
        inventory[path_string] = (cast(str, scenario), cast(str, expected))
        scenarios.add(cast(str, scenario))
    return inventory, sdk, provenance_records


def _actual_fixture_names(root: Path) -> set[str]:
    _require_real_ancestors(root, FIXTURE_ROOT.parent, label="fixture root")
    fixture_root = root / FIXTURE_ROOT
    _require_real_directory(fixture_root, label="fixture root")
    names: set[str] = set()
    with os.scandir(fixture_root) as entries:
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError("fixture root may contain only regular files")
            if metadata.st_nlink != 1:
                raise RuntimeError("fixture files must have one filesystem link")
            normalized = _normalized_relative(entry.name, label="fixture filename")
            if len(normalized.parts) != 1 or normalized.suffix != ".json":
                raise RuntimeError("fixture root contains an invalid path")
            if entry.name in names:
                raise RuntimeError("fixture root contains a duplicate filename")
            names.add(entry.name)
    return names


def _load_pinned_toml(
    root: Path,
    relative: Path,
    *,
    expected_sha256: str,
    label: str,
    maximum_bytes: int,
) -> tuple[dict[str, object], str]:
    content = _read_regular(
        root,
        relative,
        label=label,
        maximum_bytes=maximum_bytes,
    )
    digest = _sha256(content)
    if digest != expected_sha256:
        raise RuntimeError(f"{label} hash drift")
    return _strict_toml(content, label=label), digest


def _validate_dependency_inputs(
    root: Path, sdk: dict[str, object]
) -> tuple[str, str, str]:
    pyproject, pyproject_sha256 = _load_pinned_toml(
        root,
        PYPROJECT_PATH,
        expected_sha256=EXPECTED_PYPROJECT_SHA256,
        label="ST-0703 pyproject",
        maximum_bytes=MAX_PYPROJECT_BYTES,
    )
    lock, lock_sha256 = _load_pinned_toml(
        root,
        UV_LOCK_PATH,
        expected_sha256=EXPECTED_UV_LOCK_SHA256,
        label="ST-0703 uv.lock",
        maximum_bytes=MAX_UV_LOCK_BYTES,
    )
    uv_configuration, uv_config_sha256 = _load_pinned_toml(
        root,
        UV_CONFIG_PATH,
        expected_sha256=EXPECTED_UV_CONFIG_SHA256,
        label="ST-0703 uv configuration",
        maximum_bytes=MAX_UV_CONFIG_BYTES,
    )
    if _canonical_json(uv_configuration) != _canonical_json(EXPECTED_UV_CONFIGURATION):
        raise RuntimeError("ST-0703 uv configuration drift")

    project = _mapping(pyproject.get("project"), label="pyproject project")
    dependencies = _sequence(
        project.get("dependencies"), label="pyproject dependencies"
    )
    if not all(type(item) is str for item in dependencies):
        raise RuntimeError("ST-0703 pyproject OpenAI dependency drift")
    direct_openai = [
        item
        for item in cast(list[str], dependencies)
        if OPENAI_REQUIREMENT_PATTERN.match(item) is not None
    ]
    if project.get("name") != "raos" or direct_openai != [OPENAI_REQUIREMENT]:
        raise RuntimeError("ST-0703 pyproject OpenAI dependency drift")

    lock_options = _mapping(lock.get("options"), label="uv.lock options")
    if (
        type(lock.get("version")) is not int
        or lock.get("version") != 1
        or type(lock.get("revision")) is not int
        or lock.get("revision") != 3
        or lock.get("requires-python") != project.get("requires-python")
        or _canonical_json(lock_options)
        != _canonical_json(
            {
                "prerelease-mode": "disallow",
                "exclude-newer": EXPECTED_UV_CONFIGURATION["exclude-newer"],
            }
        )
    ):
        raise RuntimeError("ST-0703 uv.lock root metadata drift")

    packages = [
        _mapping(item, label="uv.lock package")
        for item in _sequence(lock.get("package"), label="uv.lock packages")
    ]
    openai_packages = [item for item in packages if item.get("name") == "openai"]
    if len(openai_packages) != 1:
        raise RuntimeError("ST-0703 uv.lock OpenAI package drift")
    openai_package = openai_packages[0]
    wheels = [
        _mapping(item, label="uv.lock OpenAI wheel")
        for item in _sequence(
            openai_package.get("wheels"), label="uv.lock OpenAI wheels"
        )
    ]
    if (
        openai_package.get("version") != OPENAI_VERSION
        or _canonical_json(openai_package.get("source"))
        != _canonical_json(OPENAI_PYPI_SOURCE)
        or _canonical_json(openai_package.get("sdist")) != _canonical_json(OPENAI_SDIST)
        or len(wheels) != 1
        or _canonical_json(wheels[0]) != _canonical_json(OPENAI_WHEEL)
    ):
        raise RuntimeError("ST-0703 uv.lock OpenAI package drift")

    root_packages = [item for item in packages if item.get("name") == "raos"]
    if len(root_packages) != 1:
        raise RuntimeError("ST-0703 uv.lock root metadata drift")
    root_package = root_packages[0]
    root_dependencies = [
        _mapping(item, label="uv.lock root dependency")
        for item in _sequence(
            root_package.get("dependencies"), label="uv.lock root dependencies"
        )
    ]
    root_metadata = _mapping(
        root_package.get("metadata"), label="uv.lock root metadata"
    )
    requires_dist = [
        _mapping(item, label="uv.lock root requirement")
        for item in _sequence(
            root_metadata.get("requires-dist"), label="uv.lock root requires-dist"
        )
    ]
    locked_dependencies = [
        item for item in root_dependencies if item.get("name") == "openai"
    ]
    locked_requirements = [
        item for item in requires_dist if item.get("name") == "openai"
    ]
    if (
        _canonical_json(root_package.get("source")) != _canonical_json({"virtual": "."})
        or [_canonical_json(item) for item in locked_dependencies]
        != [_canonical_json({"name": "openai"})]
        or [_canonical_json(item) for item in locked_requirements]
        != [_canonical_json({"name": "openai", "specifier": f"=={OPENAI_VERSION}"})]
    ):
        raise RuntimeError("ST-0703 uv.lock root metadata drift")

    release_metadata = _mapping(
        sdk.get("release_metadata"), label="official_sdk release_metadata"
    )
    selection_note = _mapping(
        sdk.get("selection_note"), label="official_sdk selection_note"
    )
    wheel_hash = cast(str, OPENAI_WHEEL["hash"]).removeprefix("sha256:")
    sdist_hash = cast(str, OPENAI_SDIST["hash"]).removeprefix("sha256:")
    wheel_upload = cast(str, OPENAI_WHEEL["upload-time"])
    expected_contract_release = {
        "upload_time": wheel_upload.split(".", 1)[0] + "Z",
        "requires_python": ">=3.10",
        "wheel_sha256": wheel_hash,
        "sdist_sha256": sdist_hash,
    }
    if (
        sdk.get("distribution") != openai_package.get("name")
        or sdk.get("version") != openai_package.get("version")
        or sdk.get("exact_requirement") != direct_openai[0]
        or _canonical_json(release_metadata)
        != _canonical_json(expected_contract_release)
        or selection_note.get("authority")
        != "NON_AUTHORITATIVE_IMPLEMENTATION_PROVENANCE"
        or selection_note.get("repository_cutoff")
        != EXPECTED_UV_CONFIGURATION["exclude-newer"]
    ):
        raise RuntimeError("ST-0703 SDK dependency binding drift")
    return pyproject_sha256, lock_sha256, uv_config_sha256


def _validate_expected_request(
    document: dict[str, object], *, label: str
) -> dict[str, object]:
    request = _mapping(document.get("expected_request"), label=f"{label} request")
    if _canonical_json(request) != _canonical_json(EXPECTED_REQUEST):
        raise RuntimeError(f"{label} expected request drift")
    return request


def _strict_embedded_json_object(value: object, *, label: str) -> dict[str, object]:
    if type(value) is not str:
        raise RuntimeError(f"{label} must contain strict JSON object text")
    try:
        parsed = json.loads(
            value,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise RuntimeError(f"{label} must contain strict JSON object text") from exc
    if not isinstance(parsed, dict) or not all(type(key) is str for key in parsed):
        raise RuntimeError(f"{label} must contain strict JSON object text")
    _bounded_graph(parsed, label=label)
    return cast(dict[str, object], parsed)


def _usage_integer(value: object, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise RuntimeError(f"{label} response usage drift")
    return value


def _validate_response_usage(
    body: dict[str, object],
    expected: dict[str, object],
    route: dict[str, object],
    *,
    label: str,
) -> None:
    usage = _mapping(body.get("usage"), label=f"{label} response usage")
    if set(usage) != RESPONSE_USAGE_KEYS:
        raise RuntimeError(f"{label} response usage drift")
    input_details = _mapping(
        usage.get("input_tokens_details"), label=f"{label} input token details"
    )
    output_details = _mapping(
        usage.get("output_tokens_details"), label=f"{label} output token details"
    )
    if set(input_details) != {"cached_tokens", "cache_write_tokens"} or set(
        output_details
    ) != {"reasoning_tokens"}:
        raise RuntimeError(f"{label} response usage drift")

    input_tokens = _usage_integer(usage.get("input_tokens"), label=label)
    cached_tokens = _usage_integer(input_details.get("cached_tokens"), label=label)
    cache_write_tokens = _usage_integer(
        input_details.get("cache_write_tokens"), label=label
    )
    output_tokens = _usage_integer(usage.get("output_tokens"), label=label)
    reasoning_tokens = _usage_integer(
        output_details.get("reasoning_tokens"), label=label
    )
    total_tokens = _usage_integer(usage.get("total_tokens"), label=label)
    if (
        cache_write_tokens != 0
        or cached_tokens > input_tokens
        or total_tokens != input_tokens + output_tokens
        or reasoning_tokens != route.get("reasoning_tokens")
    ):
        raise RuntimeError(f"{label} response usage drift")

    expected_usage = _mapping(expected.get("usage"), label=f"{label} expected usage")
    bound_usage = {
        "cached_input_tokens": cached_tokens,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if _canonical_json(bound_usage) != _canonical_json(expected_usage):
        raise RuntimeError(f"{label} response usage drift")


def _validate_response_output(
    body: dict[str, object],
    expected: dict[str, object],
    route: dict[str, object],
    *,
    label: str,
) -> None:
    output = _sequence(body.get("output"), label=f"{label} response output")
    if len(output) != 1:
        raise RuntimeError(f"{label} response output drift")
    message = _mapping(output[0], label=f"{label} response message")
    if set(message) != MESSAGE_KEYS:
        raise RuntimeError(f"{label} response output drift")
    message_identity = {
        "id": message.get("id"),
        "role": message.get("role"),
        "status": message.get("status"),
        "type": message.get("type"),
    }
    expected_identity = {
        "id": route.get("message_id"),
        "role": "assistant",
        "status": route.get("message_status"),
        "type": "message",
    }
    if _canonical_json(message_identity) != _canonical_json(expected_identity):
        raise RuntimeError(f"{label} response output drift")

    content = _sequence(message.get("content"), label=f"{label} message content")
    if len(content) != 1:
        raise RuntimeError(f"{label} response output drift")
    block = _mapping(content[0], label=f"{label} response content block")
    content_kind = route.get("content_kind")
    if content_kind == "refusal":
        expected_block = {
            "refusal": "SYNTHETIC_TEST_ONLY refusal marker.",
            "type": "refusal",
        }
        if set(block) != REFUSAL_KEYS or _canonical_json(block) != _canonical_json(
            expected_block
        ):
            raise RuntimeError(f"{label} response output drift")
        if expected.get("output") is not None:
            raise RuntimeError(f"{label} response output drift")
        return

    if set(block) != OUTPUT_TEXT_KEYS:
        raise RuntimeError(f"{label} response output drift")
    block_envelope = {
        "annotations": block.get("annotations"),
        "logprobs": block.get("logprobs"),
        "type": block.get("type"),
    }
    if block_envelope != {"annotations": [], "logprobs": [], "type": "output_text"}:
        raise RuntimeError(f"{label} response output drift")
    if content_kind == "success":
        parsed_output = _strict_embedded_json_object(
            block.get("text"), label=f"{label} completed output"
        )
        expected_output = _mapping(
            expected.get("output"), label=f"{label} expected output"
        )
        if _canonical_json(parsed_output) != _canonical_json(expected_output):
            raise RuntimeError(f"{label} response output drift")
    elif content_kind == "partial":
        if block.get("text") != route.get("partial_text"):
            raise RuntimeError(f"{label} response output drift")
        if expected.get("output") is not None:
            raise RuntimeError(f"{label} response output drift")
    else:
        raise RuntimeError(f"{label} response output drift")


def _validate_response_transport(
    body: dict[str, object],
    expected: dict[str, object],
    request: dict[str, object],
    *,
    scenario: str,
    label: str,
) -> None:
    route_value = EXPECTED_RESPONSE_ROUTES.get(scenario)
    if route_value is None or set(body) != RESPONSE_BODY_KEYS:
        raise RuntimeError(f"{label} response transport drift")
    route = cast(dict[str, object], route_value)
    request_reasoning = _mapping(
        request.get("reasoning"), label=f"{label} request reasoning"
    )
    request_text = _mapping(request.get("text"), label=f"{label} request text")
    request_format = _mapping(
        request_text.get("format"), label=f"{label} request text format"
    )
    common_expected = {
        "background": False,
        "error": None,
        "instructions": None,
        "max_output_tokens": request.get("max_output_tokens"),
        "metadata": {"classification": "SYNTHETIC_TEST_ONLY"},
        "model": request.get("model"),
        "object": "response",
        "parallel_tool_calls": False,
        "previous_response_id": None,
        "reasoning": {
            "effort": request_reasoning.get("effort"),
            "summary": None,
        },
        "store": request.get("store"),
        "temperature": None,
        "text": {
            "format": {
                "name": request_format.get("name"),
                "strict": request_format.get("strict"),
                "type": request_format.get("type"),
            }
        },
        "tool_choice": "auto",
        "tools": request.get("tools"),
        "top_p": None,
        "truncation": "disabled",
    }
    common_actual = {key: body.get(key) for key in common_expected}
    if _canonical_json(common_actual) != _canonical_json(common_expected):
        raise RuntimeError(f"{label} response transport drift")

    incomplete_reason = route.get("incomplete_reason")
    route_expected = {
        "completed_at": route.get("completed_at"),
        "created_at": route.get("created_at"),
        "id": route.get("response_id"),
        "incomplete_details": (
            None if incomplete_reason is None else {"reason": incomplete_reason}
        ),
        "status": route.get("status"),
    }
    route_actual = {key: body.get(key) for key in route_expected}
    if (
        _canonical_json(route_actual) != _canonical_json(route_expected)
        or expected.get("incomplete_reason") != incomplete_reason
    ):
        raise RuntimeError(f"{label} response transport drift")
    _validate_response_usage(body, expected, route, label=label)
    _validate_response_output(body, expected, route, label=label)


def _validate_error_transport(
    body: dict[str, object], expected: dict[str, object], *, label: str
) -> None:
    if set(body) != {"error"}:
        raise RuntimeError(f"{label} error transport drift")
    error = _mapping(body.get("error"), label=f"{label} error body")
    if _canonical_json(error) != _canonical_json(EXPECTED_RATE_LIMIT_ERROR):
        raise RuntimeError(f"{label} error transport drift")
    expected_binding = {
        "incomplete_reason": expected.get("incomplete_reason"),
        "output": expected.get("output"),
        "provider_error_code": expected.get("provider_error_code"),
        "recorder_calls": expected.get("recorder_calls"),
        "retryable": expected.get("retryable"),
        "usage": expected.get("usage"),
    }
    if expected_binding != {
        "incomplete_reason": None,
        "output": None,
        "provider_error_code": "RATE_LIMIT",
        "recorder_calls": 0,
        "retryable": True,
        "usage": None,
    }:
        raise RuntimeError(f"{label} error transport drift")


def _validate_transport(
    document: dict[str, object],
    expected: dict[str, object],
    request: dict[str, object],
    *,
    spec: FixtureSpec,
    label: str,
) -> None:
    transport = _mapping(document.get("transport"), label=f"{label} transport")
    if (
        set(transport) != TRANSPORT_KEYS
        or transport.get("kind") != "http_response"
        or transport.get("status_code") != spec.status_code
    ):
        raise RuntimeError(f"{label} transport drift")
    body = _mapping(transport.get("body"), label=f"{label} transport body")
    if spec.status_code == 200:
        _validate_response_transport(
            body,
            expected,
            request,
            scenario=spec.scenario,
            label=label,
        )
    elif spec.status_code == 429 and spec.scenario == "rate_limit_429":
        _validate_error_transport(body, expected, label=label)
    else:
        raise RuntimeError(f"{label} transport drift")


def _validate_pricing(
    document: dict[str, object],
    expected: dict[str, object],
    request: dict[str, object],
    *,
    spec: FixtureSpec,
    label: str,
) -> None:
    pricing = _mapping(document.get("pricing"), label=f"{label} pricing")
    canonical_pricing = EXPECTED_PRICING_BY_SCENARIO.get(spec.scenario)
    canonical_result = EXPECTED_RESULTS_BY_SCENARIO.get(spec.scenario)
    if (
        canonical_pricing is None
        or canonical_result is None
        or set(pricing) != PRICING_KEYS
        or pricing.get("model_id") != request.get("model")
        or pricing.get("quote_id") != "st0703-synthetic-quote-v1"
        or expected.get("kind") != canonical_result.get("kind")
    ):
        raise RuntimeError(f"{label} synthetic pricing drift")

    cost = pricing.get("expected_cost_jpy")
    if spec.status_code == 200:
        if (
            pricing.get("mode") != "SYNTHETIC_TEST_ONLY"
            or type(cost) is not int
            or cost < 0
        ):
            raise RuntimeError(f"{label} synthetic pricing drift")
    elif spec.status_code == 429 and spec.scenario == "rate_limit_429":
        if pricing.get("mode") != "NOT_CALCULATED" or cost is not None:
            raise RuntimeError(f"{label} synthetic pricing drift")
    else:
        raise RuntimeError(f"{label} synthetic pricing drift")

    if _canonical_json(pricing) != _canonical_json(canonical_pricing):
        raise RuntimeError(f"{label} synthetic pricing drift")


def _validate_fixture_document(
    document: dict[str, object],
    *,
    spec: FixtureSpec,
) -> None:
    label = f"fixture {spec.path}"
    if set(document) != EXPECTED_TOP_LEVEL_KEYS:
        raise RuntimeError(f"{label} has an unexpected top-level shape")
    if document.get("fixture_version") != "1.0.0":
        raise RuntimeError(f"{label} has an unexpected version")
    if document.get("synthetic") != "SYNTHETIC_TEST_ONLY":
        raise RuntimeError(f"{label} lacks the synthetic-only marker")
    if document.get("scenario") != spec.scenario:
        raise RuntimeError(f"{label} scenario drift")

    expected = _mapping(document.get("expected"), label=f"{label} expected")
    canonical_expected = EXPECTED_RESULTS_BY_SCENARIO.get(spec.scenario)
    if (
        canonical_expected is None
        or canonical_expected.get("kind") != spec.result_kind
        or _canonical_json(expected) != _canonical_json(canonical_expected)
    ):
        raise RuntimeError(f"{label} expected result drift")
    request = _validate_expected_request(document, label=label)
    _validate_transport(document, expected, request, spec=spec, label=label)
    _validate_pricing(document, expected, request, spec=spec, label=label)


def render_fixture_registry(root: Path = REPOSITORY_ROOT) -> bytes:
    """Validate all inputs and render their deterministic in-memory registry."""

    _validate_predecessor_manifest_semantics(root)
    contract_inventory, sdk, provenance_records = _contract_inventory(root)
    pyproject_sha256, lock_sha256, uv_config_sha256 = _validate_dependency_inputs(
        root, sdk
    )
    pinned_inventory = {
        spec.path: (spec.scenario, spec.contract_expected) for spec in FIXTURE_SPECS
    }
    if contract_inventory != pinned_inventory:
        raise RuntimeError("contract and pinned fixture inventories differ")
    if set(EXPECTED_RESULTS_BY_SCENARIO) != {spec.scenario for spec in FIXTURE_SPECS}:
        raise RuntimeError("expected result scenario inventory differs")
    if set(EXPECTED_RESPONSE_ROUTES) != {
        spec.scenario for spec in FIXTURE_SPECS if spec.status_code == 200
    }:
        raise RuntimeError("response route scenario inventory differs")
    if set(EXPECTED_PRICING_BY_SCENARIO) != {spec.scenario for spec in FIXTURE_SPECS}:
        raise RuntimeError("synthetic pricing scenario inventory differs")
    actual_names = _actual_fixture_names(root)
    expected_names = set(pinned_inventory)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise RuntimeError(
            f"fixture inventory mismatch: missing={missing}, extra={extra}"
        )

    records: list[dict[str, object]] = []
    for spec in FIXTURE_SPECS:
        relative = FIXTURE_ROOT / spec.path
        content = _read_regular(
            root,
            relative,
            label=f"fixture {spec.path}",
            maximum_bytes=MAX_FIXTURE_BYTES,
        )
        if len(content) != spec.byte_count or _sha256(content) != spec.sha256:
            raise RuntimeError(f"fixture raw-byte drift: {spec.path}")
        lowered = content.lower()
        if any(marker in lowered for marker in FORBIDDEN_FIXTURE_MARKERS):
            raise RuntimeError(f"fixture contains forbidden material: {spec.path}")
        document = _strict_fixture_json(content, label=f"fixture {spec.path}")
        _validate_decoded_fixture_material(document, label=f"fixture {spec.path}")
        _validate_fixture_document(document, spec=spec)
        records.append(
            {
                "path": spec.path,
                "scenario": spec.scenario,
                "expected": spec.contract_expected,
                "bytes": len(content),
                "sha256": _sha256(content),
            }
        )

    registry = {
        "document": {
            "id": "RAOS-ST0703-RECORDED-FIXTURE-REGISTRY-001",
            "version": "1.0.0",
            "story_id": "ST-0703",
            "status": "IMPLEMENTATION_CANDIDATE",
        },
        "source_inputs": [
            {
                "path": CONTRACT_PATH.as_posix(),
                "sha256": EXPECTED_CONTRACT_SHA256,
            },
            {"path": PYPROJECT_PATH.as_posix(), "sha256": pyproject_sha256},
            {"path": UV_LOCK_PATH.as_posix(), "sha256": lock_sha256},
            {"path": UV_CONFIG_PATH.as_posix(), "sha256": uv_config_sha256},
            *provenance_records,
        ],
        "fixture_count": len(records),
        "fixtures": records,
    }
    return (
        json.dumps(
            registry,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _artifact_record(root: Path, relative: Path) -> dict[str, object]:
    content = _read_regular(
        root,
        relative,
        label=f"source artifact {relative.as_posix()}",
        maximum_bytes=MAX_PROVENANCE_SOURCE_BYTES,
    )
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def render_manifest(
    root: Path = REPOSITORY_ROOT,
    *,
    registry_content: bytes | None = None,
) -> bytes:
    """Render the implementation manifest from the verified source closure."""

    registry_bytes = (
        render_fixture_registry(root)
        if registry_content is None
        else bytes(registry_content)
    )
    registry = _strict_fixture_json(registry_bytes, label="generated fixture registry")
    contract_content = _read_regular(
        root,
        CONTRACT_PATH,
        label="ST-0703 contract",
        maximum_bytes=MAX_CONTRACT_BYTES,
    )
    contract = _mapping(
        _strict_yaml(contract_content, label="ST-0703 contract"),
        label="ST-0703 contract",
    )
    registry_sources = _sequence(
        registry.get("source_inputs"), label="registry source_inputs"
    )
    source_paths = {CONTRACT_PATH, PYPROJECT_PATH, UV_LOCK_PATH, UV_CONFIG_PATH}
    source_paths.update(IMPLEMENTATION_SOURCE_PATHS)
    source_paths.update(FIXTURE_ROOT / spec.path for spec in FIXTURE_SPECS)
    for raw_record in registry_sources:
        record = _mapping(raw_record, label="registry source input")
        path = record.get("path")
        if type(path) is not str:
            raise RuntimeError("registry source path must be text")
        source_paths.add(_normalized_relative(path, label="registry source path"))
    sources = [_artifact_record(root, relative) for relative in sorted(source_paths)]
    boundary = _mapping(contract.get("boundary"), label="contract boundary")
    manifest = {
        "document": {
            "id": "RAOS-OPENAI-RESPONSES-ADAPTER-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0703",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "generated_by": "repo://scripts/build_st0703_recorded_adapter.py",
            "generation_command": (
                "uv run --locked --no-sync --no-env-file python "
                "scripts/build_st0703_recorded_adapter.py"
            ),
        },
        "provenance": {
            "contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "contract_sha256": _sha256(contract_content),
            "handoff_uri": f"repo://{V5_HANDOFF_PATH.as_posix()}",
            "fixture_registry_uri": (f"repo://{GENERATED_REGISTRY_PATH.as_posix()}"),
            "fixture_registry_sha256": _sha256(registry_bytes),
            "predecessor_story_ids": ["ST-0204", "ST-0701"],
        },
        "evidence_chain": {"stories": ["ST-0204", "ST-0701", "ST-0703"]},
        "source_artifact_count": len(sources),
        "source_artifacts": sources,
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{GENERATED_REGISTRY_PATH.as_posix()}",
                "bytes": len(registry_bytes),
                "sha256": _sha256(registry_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check-installed",
        },
        "boundary": dict(boundary),
    }
    return yaml.safe_dump(
        manifest,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        metadata = destination.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("generated destination must be a regular file")
        if metadata.st_nlink != 1:
            raise RuntimeError("generated destination must have one link")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
        directory_descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def generate(root: Path = REPOSITORY_ROOT) -> str:
    """Generate the fixture registry and implementation manifest."""

    registry = render_fixture_registry(root)
    manifest = render_manifest(root, registry_content=registry)
    _atomic_write(root, GENERATED_REGISTRY_PATH, registry)
    _atomic_write(root, MANIFEST_PATH, manifest)
    return _sha256(registry)


def check(root: Path = REPOSITORY_ROOT) -> str:
    """Return the deterministic registry digest without writing any file."""

    return _sha256(render_fixture_registry(root))


def check_installed(root: Path = REPOSITORY_ROOT) -> str:
    """Verify committed generated artifacts without writing."""

    registry = render_fixture_registry(root)
    manifest = render_manifest(root, registry_content=registry)
    for relative, expected in (
        (GENERATED_REGISTRY_PATH, registry),
        (MANIFEST_PATH, manifest),
    ):
        actual = _read_regular(
            root,
            relative,
            label=f"generated artifact {relative.as_posix()}",
            maximum_bytes=MAX_PROVENANCE_SOURCE_BYTES,
        )
        if actual != expected:
            raise RuntimeError(f"generated artifact drift: {relative.as_posix()}")
    return _sha256(registry)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="validate the closed fixture inventory without writing",
    )
    mode.add_argument(
        "--check-installed",
        action="store_true",
        help="verify the committed registry and manifest without writing",
    )
    arguments = parser.parse_args(argv)
    try:
        if arguments.check_installed:
            registry_sha256 = check_installed()
            operation = "installed artifacts are current"
        elif arguments.check:
            registry_sha256 = check()
            operation = "recorded fixtures are current"
        else:
            registry_sha256 = generate()
            operation = "recorded artifacts generated"
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ST-0703 recorded fixture operation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"ST-0703 {operation} "
        f"(count={len(FIXTURE_SPECS)}, registry_sha256={registry_sha256})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
