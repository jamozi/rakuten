#!/usr/bin/env python3
"""Generate and verify the closed ST-1203 Search Console fixture bundle."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import date, datetime
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tempfile
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1203/contracts/search-console-recorded-fixtures.v1.yaml"
)
FIXTURE_ROOT: Final = Path("changes/st-1203/fixtures/recorded")
MANIFEST_PATH: Final = Path("changes/st-1203/manifest.json")
GENERATOR_PATH: Final = Path("scripts/build_st1203_search_console_recorded_adapter.py")
MAX_CONTRACT_BYTES: Final = 256 * 1024
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 256 * 1024
FIXTURE_VERSION: Final = "1.0.0"
SYNTHETIC_MARKER: Final = "SYNTHETIC_TEST_ONLY"
SYNTHETIC_SITE_URL: Final = "sc-domain:example.invalid"
SYNTHETIC_PAGE_ORIGIN: Final = "https://example.invalid"
SYNTHETIC_QUERY_PATTERN: Final = re.compile(r"synthetic [a-z0-9]+(?:[ -][a-z0-9]+)*\Z")
PROVIDER_DATE_PATTERN: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
PROVIDER_COUNTRY_PATTERN: Final = re.compile(r"[a-z]{3}\Z")
ALLOWED_PROVIDER_DEVICES: Final = frozenset({"DESKTOP", "MOBILE", "TABLET"})
RECORDED_PROFILE_DIMENSIONS: Final = frozenset(
    {"date", "query", "page", "country", "device"}
)
MAX_SYNTHETIC_QUERY_LENGTH: Final = 80
EXPECTED_FIXTURE_NAMES: Final = (
    "baseline.json",
    "late-revised.json",
    "start-beyond-data.json",
)
REQUEST_KEYS: Final = frozenset(
    {
        "site_url",
        "start_date",
        "end_date",
        "dimensions",
        "search_type",
        "aggregation_type",
        "data_state",
        "row_limit",
        "start_row",
        "dimension_filter_groups",
    }
)
PROVIDER_RESPONSE_KEYS: Final = frozenset({"responseAggregationType", "rows"})
PROVIDER_ROW_KEYS: Final = frozenset(
    {"keys", "clicks", "impressions", "ctr", "position"}
)
ALLOWED_RESPONSE_AGGREGATIONS: Final = frozenset({"auto", "byPage", "byProperty"})
FORBIDDEN_DECODED_MARKERS: Final = (
    "authorization",
    "bearer ",
    "credential",
    "password",
    "private key",
    "private-key",
    "private_key",
    "client secret",
    "client-secret",
    "client_secret",
    "access token",
    "access-token",
    "access_token",
    "refresh token",
    "refresh-token",
    "refresh_token",
    "api key",
    "api-key",
    "api_key",
    "secret://",
    "set-cookie",
    "-----begin ",
    "ya29.",
    "aiza",
)
EXPECTED_PROVIDER_SEMANTICS: Final = {
    "outward_search_type_field": "type",
    "deprecated_field_forbidden": "searchType",
    "row_limit_maximum": 25000,
    "pagination_offset_field": "startRow",
    "response_key_order": "REQUESTED_DIMENSION_ORDER",
    "beyond_result_offset": "SUCCESS_WITH_ZERO_ROWS",
    "completeness": "TOP_ROWS_NOT_GUARANTEED_COMPLETE",
}
EXPECTED_STORY: Final[dict[str, object]] = {
    "objective": "GSC_FACTS_VERSIONED_IMPORT_RECORDED_SLICE",
    "dependencies": ["ST-0204", "ST-0305"],
    "requirement_ids": ["FR-013"],
    "test_suites": ["TST-030"],
    "open_decisions": [
        {
            "id": "OD-015",
            "status": "EXTERNAL_EVIDENCE_REQUIRED",
            "safe_default": "RECORDED_FIXTURE_ONLY",
        }
    ],
}
EXPECTED_GENERATION: Final[dict[str, object]] = {
    "fixture_root": "changes/st-1203/fixtures/recorded",
    "manifest_path": "changes/st-1203/manifest.json",
    "generated_by": "scripts/build_st1203_search_console_recorded_adapter.py",
    "generation_command": (
        "uv run --locked --no-sync --no-env-file python "
        "scripts/build_st1203_search_console_recorded_adapter.py"
    ),
    "check_command": (
        "uv run --locked --no-sync --no-env-file python "
        "scripts/build_st1203_search_console_recorded_adapter.py --check"
    ),
    "format": "STRICT_UTF8_LF_CANONICAL_JSON",
    "exact_fixture_files": [
        "baseline.json",
        "late-revised.json",
        "start-beyond-data.json",
    ],
}
EXPECTED_PROVENANCE: Final[dict[str, object]] = {
    "canonical_inputs": [
        {
            "uri": (
                "repo://docs/canonical/01_integration/"
                "RAOS_07_integration_design_v1.0.md"
            ),
            "sha256": (
                "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
            ),
        },
        {
            "uri": (
                "repo://docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
            ),
            "sha256": (
                "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
            ),
        },
        {
            "uri": (
                "repo://docs/canonical/03_analytics/"
                "RAOS_09_analytics_attribution_design_v1.0.md"
            ),
            "sha256": (
                "6f23dc1b68382f848ab41f4c7abc8f25e9cd5f4ba2732c30c53fdf5f0fe3a460"
            ),
        },
        {
            "uri": (
                "repo://docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"
            ),
            "sha256": (
                "b33049dc60814109b3a68c166c473f474789dd401a72116fe0a700aeeffb05fa"
            ),
        },
        {
            "uri": (
                "repo://docs/canonical/04_security/"
                "RAOS_10_security_control_catalog_v1.0.yaml"
            ),
            "sha256": (
                "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
            ),
        },
        {
            "uri": (
                "repo://docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
            ),
            "sha256": (
                "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
            ),
        },
        {
            "uri": ("repo://docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
            "sha256": (
                "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
            ),
        },
    ],
    "predecessors": [
        {
            "story_id": "ST-0204",
            "uri": "repo://changes/st-0204/manifest.yaml",
            "sha256": (
                "2c26f24dce1a1eda9a79bd0d339478b208dde77ecc76e9dfd71c918ad9fab3be"
            ),
        },
        {
            "story_id": "ST-0305",
            "uri": "repo://changes/st-0305/manifest.yaml",
            "sha256": (
                "af6034f99374b427aee444a6048531a174f0d78ae58974b2456c2be97f3d33b9"
            ),
        },
    ],
    "installed_contract_repository": {
        "uri": "repo://contracts/raos-v0.4/contract-repository.v0.4.json",
        "sha256": ("54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef"),
    },
    "contract_schemas": [
        {
            "role": "acquisition_request",
            "uri": (
                "repo://contracts/raos-v0.4/contracts/schemas/adapters/"
                "gsc-search-analytics-request.schema.json"
            ),
            "sha256": (
                "10dd3bfa4caa9be5cfe58f557db4647d4e178fa83e6d68bdded8e74d8443e89f"
            ),
        },
        {
            "role": "canonical_row",
            "uri": (
                "repo://contracts/raos-v0.4/contracts/schemas/adapters/"
                "gsc-search-analytics-row.schema.json"
            ),
            "sha256": (
                "827afbaa8ca50c631a00f893ee6932f5b2fc571d84e0566529b9e5958cc3b920"
            ),
        },
        {
            "role": "import_job",
            "uri": (
                "repo://contracts/raos-v0.4/contracts/schemas/jobs/"
                "analytics-import-search-console-v1.schema.json"
            ),
            "sha256": (
                "aa2c88caffeee692ee38d5ca6c8b7460f770ab3751abb0c35a9d197014d73f0c"
            ),
        },
        {
            "role": "import_completed_event",
            "uri": (
                "repo://contracts/raos-v0.4/contracts/schemas/events/"
                "jp-raos-analytics-import-completed-v1.schema.json"
            ),
            "sha256": (
                "50f6012ab7da5f2f04a0b4f9b3216f1ac9ea7a51b3c26f972ea24ecdcebea93d"
            ),
        },
        {
            "role": "daily_metrics_event",
            "uri": (
                "repo://contracts/raos-v0.4/contracts/schemas/events/"
                "jp-raos-analytics-daily-metrics-updated-v1.schema.json"
            ),
            "sha256": (
                "a8d28096dc570710ac02349569fea95ea82657b87a854d7799c1735c39ac1dd1"
            ),
        },
    ],
    "official_provider_reference": {
        "uri": "https://developers.google.com/webmaster-tools/v1/searchanalytics/query",
        "checked_on": "2026-08-06",
        "semantics": EXPECTED_PROVIDER_SEMANTICS,
    },
}


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that fails on duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            exists = key in result
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from exc
        if exists:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate key",
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


def _sorted_json(value: object, *, compact: bool) -> bytes:
    separators = (",", ":") if compact else None
    indent = None if compact else 2
    return (
        json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            indent=indent,
            separators=separators,
            sort_keys=True,
        )
        + ("" if compact else "\n")
    ).encode("utf-8")


def canonical_request_sha256(request: Mapping[str, object]) -> str:
    """Hash the exact normalized internal request without reordering arrays."""

    return _sha256(_sorted_json(dict(request), compact=True))


def _mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be a string-keyed mapping")
    return cast(dict[str, object], value)


def _sequence(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"{label} must be a list")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"{label} must be a non-empty string")
    return value


def _strict_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{label} must be an integer")
    return value


def _json_number(value: object, *, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RuntimeError(f"{label} must be a JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise RuntimeError(f"{label} must be finite")
    return value


def _normalized_relative(value: str, *, label: str) -> Path:
    if not value or "\\" in value:
        raise RuntimeError(f"{label} must be a normalized repository path")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or any(
        part in {"", ".", ".."} for part in candidate.parts
    ):
        raise RuntimeError(f"{label} must remain below the repository root")
    return Path(*candidate.parts)


def _require_directory(path: Path, *, label: str) -> None:
    try:
        metadata = path.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError(f"{label} is missing") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a real directory")


def _stat_signature(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _read_regular(
    root: Path,
    relative: Path,
    *,
    label: str,
    maximum_bytes: int,
) -> bytes:
    normalized = _normalized_relative(relative.as_posix(), label=f"{label} path")
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("repository root is missing") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("repository root must be a real directory")

    close_on_exec = os.O_CLOEXEC
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | close_on_exec
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | close_on_exec
    descriptors: list[int] = []
    primary_error: BaseException | None = None
    try:
        root_descriptor = os.open(root, directory_flags)
        descriptors.append(root_descriptor)
        opened_root = os.fstat(root_descriptor)
        if not stat.S_ISDIR(opened_root.st_mode):
            raise RuntimeError("repository root must open as a directory")
        if _stat_signature(opened_root) != _stat_signature(root_metadata):
            raise RuntimeError("repository root changed before it was opened")

        parent_descriptor = root_descriptor
        for part in normalized.parts[:-1]:
            try:
                directory_descriptor = os.open(
                    part,
                    directory_flags,
                    dir_fd=parent_descriptor,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"{label} ancestor could not be opened safely"
                ) from exc
            descriptors.append(directory_descriptor)
            directory_metadata = os.fstat(directory_descriptor)
            if not stat.S_ISDIR(directory_metadata.st_mode):
                raise RuntimeError(f"{label} ancestor must open as a directory")
            parent_descriptor = directory_descriptor

        try:
            descriptor = os.open(
                normalized.name,
                file_flags,
                dir_fd=parent_descriptor,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(f"{label} is missing") from exc
        except OSError as exc:
            raise RuntimeError(f"{label} could not be opened safely") from exc
        descriptors.append(descriptor)

        opened_before = os.fstat(descriptor)
        if not stat.S_ISREG(opened_before.st_mode):
            raise RuntimeError(f"{label} must open as a regular file")
        if opened_before.st_nlink != 1:
            raise RuntimeError(f"{label} must have one filesystem link")
        if opened_before.st_size > maximum_bytes:
            raise RuntimeError(f"{label} exceeds its size limit")

        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        opened_after = os.fstat(descriptor)
        if not stat.S_ISREG(opened_after.st_mode):
            raise RuntimeError(f"{label} must remain a regular file")
        if opened_after.st_nlink != 1:
            raise RuntimeError(f"{label} must have one filesystem link")
        if opened_after.st_size > maximum_bytes or len(content) > maximum_bytes:
            raise RuntimeError(f"{label} exceeds its size limit")
        if (
            _stat_signature(opened_before) != _stat_signature(opened_after)
            or len(content) != opened_after.st_size
        ):
            raise RuntimeError(f"{label} changed while it was read")
        return content
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        close_errors: list[OSError] = []
        for open_descriptor in reversed(descriptors):
            try:
                os.close(open_descriptor)
            except OSError as exc:
                close_errors.append(exc)
        if close_errors and primary_error is not None:
            try:
                primary_error.add_note("descriptor cleanup also failed")
            except BaseException:
                pass
        elif close_errors:
            raise close_errors[0]


def _load_yaml(content: bytes) -> dict[str, object]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("ST-1203 source contract must be UTF-8") from exc
    if "\r" in text or not text.endswith("\n"):
        raise RuntimeError("ST-1203 source contract must use LF and end with a newline")
    try:
        parsed = yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise RuntimeError("ST-1203 source contract is malformed") from exc
    return _mapping(parsed, label="ST-1203 source contract")


def _load_json(content: bytes, *, label: str) -> dict[str, object]:
    try:
        parsed = json.loads(
            content.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict JSON") from exc
    return _mapping(parsed, label=label)


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _repo_uri_path(uri: object, *, label: str) -> Path:
    text = _text(uri, label=label)
    prefix = "repo://"
    if not text.startswith(prefix):
        raise RuntimeError(f"{label} must be a repo URI")
    return _normalized_relative(text.removeprefix(prefix), label=label)


def _validate_exact_provenance(value: object) -> dict[str, object]:
    provenance = _mapping(value, label="provenance")
    if provenance != EXPECTED_PROVENANCE:
        raise RuntimeError("ST-1203 provenance inventory drifted")
    return provenance


def _validate_pinned_sources(
    root: Path, contract: Mapping[str, object]
) -> dict[Path, bytes]:
    provenance = _validate_exact_provenance(contract.get("provenance"))
    groups = (
        ("canonical_inputs", None),
        ("predecessors", "story_id"),
        ("contract_schemas", "role"),
    )
    seen: set[Path] = set()
    captured: dict[Path, bytes] = {}
    for group_name, required_extra in groups:
        for index, raw_entry in enumerate(
            _sequence(provenance.get(group_name), label=group_name)
        ):
            entry = _mapping(raw_entry, label=f"{group_name}[{index}]")
            required_keys = {"uri", "sha256"}
            if required_extra is not None:
                required_keys.add(required_extra)
            if set(entry) != required_keys:
                raise RuntimeError(f"{group_name}[{index}] has unexpected fields")
            relative = _repo_uri_path(entry.get("uri"), label=f"{group_name} URI")
            if relative in seen:
                raise RuntimeError("ST-1203 provenance paths must be unique")
            seen.add(relative)
            content = _read_regular(
                root,
                relative,
                label=f"pinned source {group_name}[{index}]",
                maximum_bytes=MAX_SOURCE_BYTES,
            )
            if _sha256(content) != _text(entry.get("sha256"), label="source sha256"):
                raise RuntimeError(f"pinned source hash drift in {group_name}")
            captured[relative] = content

    installed = _mapping(
        provenance.get("installed_contract_repository"),
        label="installed_contract_repository",
    )
    if set(installed) != {"uri", "sha256"}:
        raise RuntimeError("installed contract repository fields drifted")
    relative = _repo_uri_path(installed.get("uri"), label="contract repository URI")
    if relative in seen:
        raise RuntimeError("ST-1203 provenance paths must be unique")
    content = _read_regular(
        root,
        relative,
        label="installed contract repository",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    if _sha256(content) != _text(installed.get("sha256"), label="repository sha256"):
        raise RuntimeError("installed contract repository hash drift")
    captured[relative] = content
    return captured


def _validate_exact_contract(contract: Mapping[str, object]) -> None:
    expected_top_level = {
        "document",
        "story",
        "provenance",
        "generation",
        "request_hash",
        "recordings",
        "recorded_result_policy",
        "boundary",
    }
    if set(contract) != expected_top_level:
        raise RuntimeError("ST-1203 source contract top-level fields drifted")

    document = _mapping(contract.get("document"), label="document")
    if document != {
        "id": "RAOS-SEARCH-CONSOLE-RECORDED-FIXTURES-001",
        "version": "1.0.0",
        "story_id": "ST-1203",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    }:
        raise RuntimeError("ST-1203 document identity drifted")

    story = _mapping(contract.get("story"), label="story")
    if story != EXPECTED_STORY:
        raise RuntimeError("ST-1203 exact Story boundary drifted")

    generation = _mapping(contract.get("generation"), label="generation")
    if generation != EXPECTED_GENERATION:
        raise RuntimeError("ST-1203 exact generation contract drifted")

    request_hash = _mapping(contract.get("request_hash"), label="request_hash")
    if request_hash != {
        "algorithm": "SHA-256",
        "canonicalization": "UTF8_SORTED_KEYS_COMPACT_JSON",
        "scope": "EXACT_INTERNAL_ACQUISITION_REQUEST_DOCUMENT",
        "ordered_arrays": "PRESERVED",
        "omitted_defaults": "FORBIDDEN_IN_RECORDED_FIXTURES",
    }:
        raise RuntimeError("ST-1203 request-hash contract drifted")

    _validate_exact_provenance(contract.get("provenance"))

    policy = _mapping(
        contract.get("recorded_result_policy"), label="recorded_result_policy"
    )
    required_policy = {
        "synthetic_site_url": SYNTHETIC_SITE_URL,
        "synthetic_page_origin": SYNTHETIC_PAGE_ORIGIN,
        "synthetic_page_components": "NO_USERINFO_PORT_QUERY_OR_FRAGMENT",
        "synthetic_query_pattern": r"synthetic [a-z0-9]+(?:[ -][a-z0-9]+)*",
        "synthetic_query_max_length": MAX_SYNTHETIC_QUERY_LENGTH,
        "dimension_filter_groups": "REQUIRED_EMPTY",
        "dimensions": "EXACT_REQUEST_ORDER",
        "keys": "EXACT_PROVIDER_ORDER",
        "source_request_sha256": "REQUIRED_ON_EVERY_ROW",
        "top_rows_caveat": "REQUIRED_TRUE_ON_EVERY_ROW_AND_RESULT",
        "baseline_and_late_revised": "SEPARATELY_INSPECTABLE_NO_SUPERSESSION_CLAIM",
        "numeric_values": "PRESERVE_JSON_NUMBER_NO_CONVERSION_POLICY",
    }
    if policy != required_policy:
        raise RuntimeError("ST-1203 recorded-result policy drifted")

    boundary = _mapping(contract.get("boundary"), label="boundary")
    required_boundary = {
        "network": "FORBIDDEN",
        "credentials": "FORBIDDEN",
        "environment_credentials": "FORBIDDEN",
        "google_sdk": "FORBIDDEN",
        "live_api": "NOT_USED",
        "persistent_writes": "FORBIDDEN",
        "database_writes": "FORBIDDEN",
        "site_id_to_site_url_mapping": "NOT_DEFINED",
        "durable_supersession": "NOT_DEFINED",
        "dimension_key_sha256": "NOT_DEFINED",
        "date_derivation_for_date_less_requests": "NOT_DEFINED",
        "privacy_suppression_rules": "NOT_DEFINED",
        "numeric_conversion_policy": "NOT_DEFINED",
        "local_result": "IMPLEMENTATION_CANDIDATE_ONLY",
        "formal_tst_030": "NOT_EXECUTED",
        "production_readiness": "NOT_READY",
    }
    if boundary != required_boundary:
        raise RuntimeError("ST-1203 safe boundary drifted")


def _schema_by_role(
    contract: Mapping[str, object], role: str, captured: Mapping[Path, bytes]
) -> dict[str, object]:
    provenance = _mapping(contract.get("provenance"), label="provenance")
    matches = []
    for raw_entry in _sequence(
        provenance.get("contract_schemas"), label="contract_schemas"
    ):
        entry = _mapping(raw_entry, label="contract schema")
        if entry.get("role") == role:
            matches.append(entry)
    if len(matches) != 1:
        raise RuntimeError(f"contract schema role {role} must be unique")
    relative = _repo_uri_path(matches[0].get("uri"), label="contract schema URI")
    try:
        content = captured[relative]
    except KeyError as exc:
        raise RuntimeError(f"contract schema role {role} was not captured") from exc
    return _load_json(
        content,
        label=f"{role} schema",
    )


def _validate_schema_instance(
    schema: Mapping[str, object], instance: object, *, label: str
) -> None:
    try:
        Draft202012Validator.check_schema(dict(schema))
        validator = Draft202012Validator(dict(schema), format_checker=FormatChecker())
        validator.validate(instance)
    except (SchemaError, ValidationError) as exc:
        raise RuntimeError(f"{label} violates its installed contract schema") from exc


def _scan_recorded_material(value: object, *, label: str) -> None:
    pending = [value]
    visits = 0
    while pending:
        visits += 1
        if visits > 20_000:
            raise RuntimeError(f"{label} exceeds the fixture graph limit")
        item = pending.pop()
        if isinstance(item, dict):
            pending.extend(item.keys())
            pending.extend(item.values())
            continue
        if isinstance(item, list):
            pending.extend(item)
            continue
        if not isinstance(item, str):
            continue
        normalized = item.casefold()
        if any(marker in normalized for marker in FORBIDDEN_DECODED_MARKERS):
            raise RuntimeError(f"{label} contains credential-shaped material")
        split = urlsplit(item)
        if split.scheme in {"http", "https"} and (
            split.username is not None
            or split.password is not None
            or bool(split.query)
            or bool(split.fragment)
        ):
            raise RuntimeError(f"{label} contains a URL with sensitive components")


def _outbound_request(request: Mapping[str, object]) -> dict[str, object]:
    groups: list[object] = []
    for raw_group in cast(list[object], request["dimension_filter_groups"]):
        group = _mapping(raw_group, label="dimension filter group")
        filters = []
        for raw_filter in _sequence(group.get("filters"), label="filters"):
            item = _mapping(raw_filter, label="filter")
            filters.append(
                {
                    "dimension": item.get("dimension"),
                    "operator": item.get("operator"),
                    "expression": item.get("expression"),
                }
            )
        groups.append({"groupType": group.get("group_type"), "filters": filters})
    body = {
        "startDate": request["start_date"],
        "endDate": request["end_date"],
        "dimensions": deepcopy(request["dimensions"]),
        "type": request["search_type"],
        "aggregationType": request["aggregation_type"],
        "dataState": request["data_state"],
        "rowLimit": request["row_limit"],
        "startRow": request["start_row"],
        "dimensionFilterGroups": groups,
    }
    if "searchType" in body:
        raise RuntimeError("deprecated Search Analytics searchType is forbidden")
    return {"site_url": request["site_url"], "body": body}


def _validate_request(
    request: dict[str, object],
    *,
    expected_sha256: str,
    request_schema: Mapping[str, object],
) -> str:
    if set(request) != REQUEST_KEYS:
        raise RuntimeError("recorded request must contain the exact normalized fields")
    _validate_schema_instance(request_schema, request, label="recorded request")
    if request.get("site_url") != SYNTHETIC_SITE_URL:
        raise RuntimeError("recorded site_url must use the synthetic allowlist")
    if request.get("dimension_filter_groups") != []:
        raise RuntimeError(
            "recorded dimension filters are outside this synthetic slice"
        )
    try:
        start_date = date.fromisoformat(
            _text(request.get("start_date"), label="start_date")
        )
        end_date = date.fromisoformat(_text(request.get("end_date"), label="end_date"))
    except ValueError as exc:
        raise RuntimeError("recorded request dates must be ISO dates") from exc
    if end_date < start_date:
        raise RuntimeError("recorded request end_date cannot precede start_date")
    row_limit = _strict_integer(request.get("row_limit"), label="row_limit")
    start_row = _strict_integer(request.get("start_row"), label="start_row")
    if not 1 <= row_limit <= 25_000 or start_row < 0:
        raise RuntimeError("recorded request pagination is out of range")
    dimensions = _sequence(request.get("dimensions"), label="dimensions")
    if len(dimensions) != len(set(map(str, dimensions))):
        raise RuntimeError("recorded dimensions must be unique and ordered")
    if any(dimension not in RECORDED_PROFILE_DIMENSIONS for dimension in dimensions):
        raise RuntimeError(
            "recorded request dimension is unsupported by bounded recorded profile"
        )
    digest = canonical_request_sha256(request)
    if digest != expected_sha256:
        raise RuntimeError("recorded acquisition request hash drifted")
    return digest


def _validate_synthetic_dimension_key(
    dimension: object,
    key: object,
    *,
    request_start_date: date,
    request_end_date: date,
) -> None:
    if dimension == "date":
        if not isinstance(key, str) or PROVIDER_DATE_PATTERN.fullmatch(key) is None:
            raise RuntimeError("recorded date key must be an ISO date")
        try:
            provider_date = date.fromisoformat(key)
        except ValueError as exc:
            raise RuntimeError("recorded date key must be an ISO date") from exc
        if not request_start_date <= provider_date <= request_end_date:
            raise RuntimeError("recorded date key is outside the requested date range")
        return
    if dimension == "country":
        if not isinstance(key, str) or PROVIDER_COUNTRY_PATTERN.fullmatch(key) is None:
            raise RuntimeError(
                "recorded country key must be lowercase ISO-style alpha-3"
            )
        return
    if dimension == "device":
        if key not in ALLOWED_PROVIDER_DEVICES:
            raise RuntimeError("recorded device key must be DESKTOP, MOBILE, or TABLET")
        return
    if dimension == "query":
        if (
            not isinstance(key, str)
            or len(key) > MAX_SYNTHETIC_QUERY_LENGTH
            or SYNTHETIC_QUERY_PATTERN.fullmatch(key) is None
        ):
            raise RuntimeError("recorded query key violates the synthetic convention")
        return
    if dimension != "page":
        raise RuntimeError(
            "recorded provider dimension is unsupported by bounded recorded profile"
        )
    if not isinstance(key, str):
        raise RuntimeError("recorded page key must be a synthetic HTTPS URL")
    try:
        split = urlsplit(key)
        port = split.port
    except ValueError as exc:
        raise RuntimeError("recorded page key must be a synthetic HTTPS URL") from exc
    if (
        split.scheme != "https"
        or split.netloc != "example.invalid"
        or split.username is not None
        or split.password is not None
        or port is not None
        or not split.path.startswith("/")
        or bool(split.query)
        or bool(split.fragment)
        or not key.startswith(f"{SYNTHETIC_PAGE_ORIGIN}/")
    ):
        raise RuntimeError("recorded page key must use the synthetic HTTPS allowlist")


def _canonical_rows(
    *,
    recording: Mapping[str, object],
    request: Mapping[str, object],
    response: Mapping[str, object],
    request_sha256: str,
    row_schema: Mapping[str, object],
) -> list[dict[str, object]]:
    dimensions = list(_sequence(request.get("dimensions"), label="dimensions"))
    rows = _sequence(response.get("rows"), label="provider rows")
    row_limit = _strict_integer(request.get("row_limit"), label="row_limit")
    if len(rows) > row_limit:
        raise RuntimeError(
            "provider response row count exceeds the requested row_limit"
        )
    request_start_date = date.fromisoformat(
        _text(request.get("start_date"), label="start_date")
    )
    request_end_date = date.fromisoformat(
        _text(request.get("end_date"), label="end_date")
    )
    canonical: list[dict[str, object]] = []
    for index, raw_row in enumerate(rows):
        provider_row = _mapping(raw_row, label=f"provider row {index}")
        if set(provider_row) != PROVIDER_ROW_KEYS:
            raise RuntimeError("provider row contains unexpected fields")
        keys = _sequence(provider_row.get("keys"), label="provider row keys")
        if len(keys) != len(dimensions):
            raise RuntimeError(
                "provider row key order does not match requested dimensions"
            )
        if any(value is not None and not isinstance(value, str) for value in keys):
            raise RuntimeError("provider row keys must be strings or null")
        for dimension, key in zip(dimensions, keys, strict=True):
            _validate_synthetic_dimension_key(
                dimension,
                key,
                request_start_date=request_start_date,
                request_end_date=request_end_date,
            )
        clicks = _json_number(provider_row.get("clicks"), label="clicks")
        impressions = _json_number(provider_row.get("impressions"), label="impressions")
        ctr = _json_number(provider_row.get("ctr"), label="ctr")
        position = _json_number(provider_row.get("position"), label="position")
        row = {
            "site_id": _text(recording.get("site_id"), label="site_id"),
            "date_from": request["start_date"],
            "date_to": request["end_date"],
            "dimensions": deepcopy(dimensions),
            "keys": deepcopy(keys),
            "clicks": clicks,
            "impressions": impressions,
            "ctr": ctr,
            "position": position,
            "data_state": request["data_state"],
            "imported_at": _text(recording.get("recorded_at"), label="recorded_at"),
            "source_request_sha256": request_sha256,
            "is_top_rows_limited": True,
        }
        _validate_schema_instance(row_schema, row, label="recorded canonical row")
        canonical.append(row)
    return canonical


def _render_recording(
    recording: Mapping[str, object],
    *,
    request_schema: Mapping[str, object],
    row_schema: Mapping[str, object],
) -> tuple[str, bytes, dict[str, object]]:
    expected_fields = {
        "recording_id",
        "fixture_file",
        "synthetic_marker",
        "site_id",
        "recorded_at",
        "expected_source_request_sha256",
        "request",
        "provider_response",
    }
    if set(recording) != expected_fields:
        raise RuntimeError("recording contains unexpected fields")
    recording_id = _text(recording.get("recording_id"), label="recording_id")
    fixture_file = _text(recording.get("fixture_file"), label="fixture_file")
    normalized = _normalized_relative(fixture_file, label="fixture_file")
    if normalized.parent != Path(".") or normalized.suffix != ".json":
        raise RuntimeError("fixture_file must be one JSON basename")
    if recording.get("synthetic_marker") != SYNTHETIC_MARKER:
        raise RuntimeError("recording must retain the synthetic marker")
    try:
        UUID(_text(recording.get("site_id"), label="site_id"))
        recorded_at = datetime.fromisoformat(
            _text(recording.get("recorded_at"), label="recorded_at").replace(
                "Z", "+00:00"
            )
        )
    except ValueError as exc:
        raise RuntimeError("recording identity or timestamp is malformed") from exc
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise RuntimeError("recorded_at must be timezone-aware")

    request = deepcopy(_mapping(recording.get("request"), label="request"))
    expected_sha256 = _text(
        recording.get("expected_source_request_sha256"),
        label="expected_source_request_sha256",
    )
    request_sha256 = _validate_request(
        request,
        expected_sha256=expected_sha256,
        request_schema=request_schema,
    )
    response = deepcopy(
        _mapping(recording.get("provider_response"), label="provider_response")
    )
    if set(response) != PROVIDER_RESPONSE_KEYS:
        raise RuntimeError("provider response contains unexpected fields")
    if response.get("responseAggregationType") not in ALLOWED_RESPONSE_AGGREGATIONS:
        raise RuntimeError("provider response aggregation type is invalid")
    if (
        "page" in _sequence(request.get("dimensions"), label="dimensions")
        and response.get("responseAggregationType") != "byPage"
    ):
        raise RuntimeError(
            "the recorded page-dimensional response aggregation must be byPage"
        )
    canonical_rows = _canonical_rows(
        recording=recording,
        request=request,
        response=response,
        request_sha256=request_sha256,
        row_schema=row_schema,
    )
    fixture = {
        "fixture_version": FIXTURE_VERSION,
        "recording_id": recording_id,
        "synthetic_marker": SYNTHETIC_MARKER,
        "request": request,
        "source_request_sha256": request_sha256,
        "outbound_request": _outbound_request(request),
        "provider_response": response,
        "recorded_result": {
            "recorded_at": recording["recorded_at"],
            "pagination": {
                "row_limit": request["row_limit"],
                "start_row": request["start_row"],
                "returned_row_count": len(canonical_rows),
            },
            "top_rows_only": True,
            "rows_not_guaranteed_complete": True,
            "rows": canonical_rows,
        },
    }
    _scan_recorded_material(fixture, label=f"recording {recording_id}")
    content = _sorted_json(fixture, compact=False)
    if len(content) > MAX_GENERATED_BYTES:
        raise RuntimeError("generated fixture exceeds its size limit")
    inventory = {
        "path": fixture_file,
        "recording_id": recording_id,
        "bytes": len(content),
        "sha256": _sha256(content),
        "source_request_sha256": request_sha256,
        "row_limit": request["row_limit"],
        "start_row": request["start_row"],
        "returned_row_count": len(canonical_rows),
        "top_rows_only": True,
    }
    return fixture_file, content, inventory


def build_outputs(root: Path = REPOSITORY_ROOT) -> dict[Path, bytes]:
    contract_content = _read_regular(
        root,
        CONTRACT_PATH,
        label="ST-1203 source contract",
        maximum_bytes=MAX_CONTRACT_BYTES,
    )
    contract = _load_yaml(contract_content)
    _validate_exact_contract(contract)
    captured = _validate_pinned_sources(root, contract)
    request_schema = _schema_by_role(contract, "acquisition_request", captured)
    row_schema = _schema_by_role(contract, "canonical_row", captured)

    outputs: dict[Path, bytes] = {}
    inventories: list[dict[str, object]] = []
    recording_ids: set[str] = set()
    fixture_names: set[str] = set()
    for raw_recording in _sequence(contract.get("recordings"), label="recordings"):
        recording = _mapping(raw_recording, label="recording")
        fixture_name, content, inventory = _render_recording(
            recording,
            request_schema=request_schema,
            row_schema=row_schema,
        )
        recording_id = cast(str, inventory["recording_id"])
        if recording_id in recording_ids or fixture_name in fixture_names:
            raise RuntimeError("recording IDs and fixture files must be unique")
        recording_ids.add(recording_id)
        fixture_names.add(fixture_name)
        outputs[FIXTURE_ROOT / fixture_name] = content
        inventories.append(inventory)
    if tuple(sorted(fixture_names)) != EXPECTED_FIXTURE_NAMES:
        raise RuntimeError(
            "rendered fixture inventory does not match the closed contract"
        )
    by_id = {entry["recording_id"]: entry for entry in inventories}
    baseline = by_id.get("baseline")
    revised = by_id.get("late-revised")
    beyond = by_id.get("start-beyond-data")
    if baseline is None or revised is None or beyond is None:
        raise RuntimeError("the three required recording scenarios are missing")
    if baseline["source_request_sha256"] != revised["source_request_sha256"]:
        raise RuntimeError("baseline and late-revised must bind the same request hash")
    if beyond["returned_row_count"] != 0 or beyond["start_row"] != 25_000:
        raise RuntimeError(
            "the beyond-data scenario must return zero rows at offset 25000"
        )

    generator_content = _read_regular(
        root,
        GENERATOR_PATH,
        label="ST-1203 generator",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    generation = _mapping(contract.get("generation"), label="generation")
    manifest = {
        "document": {
            "id": "RAOS-SEARCH-CONSOLE-RECORDED-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1203",
        },
        "generation": {
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": _text(
                generation.get("generation_command"), label="generation command"
            ),
            "check_command": _text(
                generation.get("check_command"), label="check command"
            ),
        },
        "source_artifacts": [
            {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "bytes": len(contract_content),
                "sha256": _sha256(contract_content),
            },
            {
                "uri": f"repo://{GENERATOR_PATH.as_posix()}",
                "bytes": len(generator_content),
                "sha256": _sha256(generator_content),
            },
        ],
        "provenance": deepcopy(contract["provenance"]),
        "request_hash": deepcopy(contract["request_hash"]),
        "fixture_count": len(inventories),
        "fixtures": sorted(inventories, key=lambda item: cast(str, item["path"])),
        "boundary": deepcopy(contract["boundary"]),
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
    }
    outputs[MANIFEST_PATH] = _sorted_json(manifest, compact=False)
    return outputs


def _actual_fixture_names(root: Path, *, allow_missing_root: bool) -> set[str]:
    _require_directory(root, label="repository root")
    fixture_root = root
    for part in FIXTURE_ROOT.parts:
        fixture_root = fixture_root / part
        try:
            metadata = fixture_root.lstat()
        except FileNotFoundError:
            if allow_missing_root:
                return set()
            raise RuntimeError("fixture root is missing") from None
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise RuntimeError("fixture-root ancestors must be real directories")
    names: set[str] = set()
    with os.scandir(fixture_root) as entries:
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            if entry.is_symlink() or not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError("fixture root may contain only regular files")
            if metadata.st_nlink != 1:
                raise RuntimeError("fixture files must have one filesystem link")
            normalized = _normalized_relative(entry.name, label="fixture filename")
            if normalized.parent != Path(".") or normalized.suffix != ".json":
                raise RuntimeError("fixture root contains an invalid filename")
            names.add(entry.name)
    return names


def _ensure_output_parent(root: Path, relative_parent: Path) -> None:
    _require_directory(root, label="repository root")
    current = root
    for part in relative_parent.parts:
        current = current / part
        if current.exists():
            _require_directory(current, label="generated-output ancestor")
        else:
            current.mkdir(mode=0o755)


def _atomic_write(root: Path, relative: Path, content: bytes) -> None:
    _ensure_output_parent(root, relative.parent)
    destination = root / relative
    if destination.exists() or destination.is_symlink():
        metadata = destination.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError("generated output destination must be a regular file")
        if metadata.st_nlink != 1:
            raise RuntimeError("generated output destination must have one link")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{relative.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(
            destination.parent,
            os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
        )
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def generate(root: Path = REPOSITORY_ROOT) -> str:
    outputs = build_outputs(root)
    actual = _actual_fixture_names(root, allow_missing_root=True)
    extras = sorted(actual - set(EXPECTED_FIXTURE_NAMES))
    if extras:
        raise RuntimeError("fixture root contains files outside the closed inventory")
    for relative in sorted(outputs, key=lambda path: path.as_posix()):
        _atomic_write(root, relative, outputs[relative])
    return _sha256(outputs[MANIFEST_PATH])


def check(root: Path = REPOSITORY_ROOT) -> str:
    outputs = build_outputs(root)
    actual = _actual_fixture_names(root, allow_missing_root=False)
    if actual != set(EXPECTED_FIXTURE_NAMES):
        raise RuntimeError("fixture inventory has missing or extra files")
    for relative, expected in outputs.items():
        observed = _read_regular(
            root,
            relative,
            label=f"generated output {relative.as_posix()}",
            maximum_bytes=MAX_GENERATED_BYTES,
        )
        if observed != expected:
            raise RuntimeError(f"generated output drift: {relative.as_posix()}")
    return _sha256(outputs[MANIFEST_PATH])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify generated fixtures and manifest without writing",
    )
    arguments = parser.parse_args(argv)
    try:
        digest = check() if arguments.check else generate()
    except (OSError, RuntimeError) as exc:
        print(f"ST-1203 recorded fixture generation failed: {exc}", file=sys.stderr)
        return 1
    action = "verified" if arguments.check else "generated"
    print(f"ST-1203 recorded fixtures {action}; manifest sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
