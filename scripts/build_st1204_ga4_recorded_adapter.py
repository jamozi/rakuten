#!/usr/bin/env python3
"""Generate and verify the closed ST-1204 GA4 fixture bundle."""

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
import tempfile
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit
from uuid import UUID

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-1204/contracts/ga4-recorded-fixtures.v1.yaml")
FIXTURE_ROOT: Final = Path("changes/st-1204/fixtures/recorded")
MANIFEST_PATH: Final = Path("changes/st-1204/manifest.json")
GENERATOR_PATH: Final = Path("scripts/build_st1204_ga4_recorded_adapter.py")
MAX_CONTRACT_BYTES: Final = 256 * 1024
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 256 * 1024
FIXTURE_VERSION: Final = "1.0.0"
SYNTHETIC_MARKER: Final = "SYNTHETIC_TEST_ONLY"
SYNTHETIC_PROPERTY_ID: Final = "1000001204"
SYNTHETIC_PROPERTY_RESOURCE: Final = "properties/1000001204"
SYNTHETIC_SITE_ID: Final = "00000000-0000-4000-8000-000000001204"
SYNTHETIC_PAGE_PREFIX: Final = "/synthetic/"
RUN_REPORT_ENDPOINT: Final = (
    "https://analyticsdata.googleapis.com/v1beta/properties/1000001204:runReport"
)
REPORTING_IDENTITY_ENDPOINT: Final = (
    "https://analyticsadmin.googleapis.com/v1alpha/"
    "properties/1000001204/reportingIdentitySettings"
)
REPORTING_IDENTITY_RESOURCE: Final = "properties/1000001204/reportingIdentitySettings"
EXPECTED_FIXTURE_NAMES: Final = (
    "baseline.json",
    "late-revised.json",
    "provider-error-429.json",
)
REQUEST_KEYS: Final = frozenset(
    {
        "property_id",
        "date_ranges",
        "dimensions",
        "metrics",
        "dimension_filter",
        "metric_filter",
        "order_bys",
        "limit",
        "offset",
        "keep_empty_rows",
        "return_property_quota",
    }
)
EXPECTED_DIMENSIONS: Final = ("date", "pagePath", "deviceCategory")
EXPECTED_METRICS: Final = ("sessions", "screenPageViews", "engagedSessions")
EXPECTED_METRIC_TYPES: Final = (
    "TYPE_INTEGER",
    "TYPE_INTEGER",
    "TYPE_INTEGER",
)
ALLOWED_REPORTING_IDENTITIES: Final = frozenset({"BLENDED", "OBSERVED", "DEVICE_BASED"})
METRIC_VALUE_PATTERN: Final = re.compile(r"-?[0-9]+(?:\.[0-9]+)?\Z")
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


def canonical_json_sha256(value: Mapping[str, object]) -> str:
    """Hash an exact JSON object without reordering arrays."""

    return _sha256(_sorted_json(dict(value), compact=True))


def canonical_request_sha256(request: Mapping[str, object]) -> str:
    """Hash the exact normalized internal request without reordering arrays."""

    return canonical_json_sha256(request)


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
    if content.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError("ST-1204 source contract must not contain a BOM")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("ST-1204 source contract must be UTF-8") from exc
    if "\r" in text or not text.endswith("\n"):
        raise RuntimeError("ST-1204 source contract must use LF and end with a newline")
    try:
        tokens = tuple(yaml.scan(text))
        if any(isinstance(token, (AnchorToken, AliasToken)) for token in tokens):
            raise RuntimeError("ST-1204 source contract must not use YAML aliases")
        parsed = yaml.load(text, Loader=UniqueKeyLoader)
    except RuntimeError:
        raise
    except yaml.YAMLError as exc:
        raise RuntimeError("ST-1204 source contract is malformed") from exc
    result = _mapping(parsed, label="ST-1204 source contract")
    _validate_json_graph(result, label="ST-1204 source contract")
    return result


def _load_json(content: bytes, *, label: str) -> dict[str, object]:
    if content.startswith(b"\xef\xbb\xbf"):
        raise RuntimeError(f"{label} must not contain a BOM")
    try:
        text = content.decode("utf-8")
        if "\r" in text or not text.endswith("\n"):
            raise ValueError("JSON must use LF and end with a newline")
        parsed = json.loads(
            text,
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_json_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict JSON") from exc
    result = _mapping(parsed, label=label)
    _validate_json_graph(result, label=label)
    return result


def _reject_json_constant(value: str) -> NoReturn:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON member")
        result[key] = value
    return result


def _validate_json_graph(value: object, *, label: str) -> None:
    pending: list[tuple[object, int]] = [(value, 0)]
    visits = 0
    while pending:
        item, depth = pending.pop()
        visits += 1
        if visits > 20_000 or depth > 64:
            raise RuntimeError(f"{label} exceeds the document graph limit")
        if isinstance(item, dict):
            if not all(isinstance(key, str) for key in item):
                raise RuntimeError(f"{label} contains a non-string object key")
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, float) and not math.isfinite(item):
            raise RuntimeError(f"{label} contains a non-finite number")


def _repo_uri_path(uri: object, *, label: str) -> Path:
    text = _text(uri, label=label)
    prefix = "repo://"
    if not text.startswith(prefix):
        raise RuntimeError(f"{label} must be a repo URI")
    return _normalized_relative(text.removeprefix(prefix), label=label)


def _validate_pinned_sources(
    root: Path, contract: Mapping[str, object]
) -> dict[Path, bytes]:
    provenance = _mapping(contract.get("provenance"), label="provenance")
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
                raise RuntimeError("ST-1204 provenance paths must be unique")
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
        raise RuntimeError("ST-1204 provenance paths must be unique")
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
        "hashing",
        "request_policy",
        "recordings",
        "recorded_result_policy",
        "boundary",
    }
    if set(contract) != expected_top_level:
        raise RuntimeError("ST-1204 source contract top-level fields drifted")

    document = _mapping(contract.get("document"), label="document")
    if document != {
        "id": "RAOS-GA4-RECORDED-FIXTURES-001",
        "version": "1.0.0",
        "story_id": "ST-1204",
        "status": "LOCAL_SOURCE_CONTRACT_CANDIDATE",
    }:
        raise RuntimeError("ST-1204 document identity drifted")

    story = _mapping(contract.get("story"), label="story")
    if story != {
        "objective": "GA4_AGGREGATE_FACTS_VERSIONED_IMPORT_RECORDED_SLICE",
        "dependencies": ["ST-0204", "ST-0305"],
        "requirement_ids": ["FR-013"],
        "test_suites": ["TST-030"],
        "open_decisions": [
            {
                "id": "OD-012",
                "status": "HUMAN_DECISION_REQUIRED",
                "safe_default": "OPTIONAL_TRACKING_DISABLED",
            },
            {
                "id": "OD-015",
                "status": "EXTERNAL_EVIDENCE_REQUIRED",
                "safe_default": "RECORDED_FIXTURE_ONLY",
            },
        ],
    }:
        raise RuntimeError("ST-1204 Story boundary drifted")

    generation = _mapping(contract.get("generation"), label="generation")
    required_generation = {
        "source_contract": CONTRACT_PATH.as_posix(),
        "fixture_root": FIXTURE_ROOT.as_posix(),
        "manifest_path": MANIFEST_PATH.as_posix(),
        "generated_by": GENERATOR_PATH.as_posix(),
        "generation_command": (
            "uv run --locked --no-sync --no-env-file python "
            "scripts/build_st1204_ga4_recorded_adapter.py"
        ),
        "check_command": (
            "uv run --locked --no-sync --no-env-file python "
            "scripts/build_st1204_ga4_recorded_adapter.py --check"
        ),
        "format": "STRICT_UTF8_LF_CANONICAL_JSON",
        "exact_fixture_files": list(EXPECTED_FIXTURE_NAMES),
    }
    if generation != required_generation:
        raise RuntimeError("ST-1204 generation contract drifted")

    hashing = _mapping(contract.get("hashing"), label="hashing")
    if hashing != {
        "algorithm": "SHA-256",
        "canonicalization": "UTF8_SORTED_KEYS_COMPACT_JSON",
        "internal_request_scope": "EXACT_INTERNAL_RUN_REPORT_REQUEST_DOCUMENT",
        "wire_request_scope": "EXACT_RUN_REPORT_JSON_BODY",
        "response_scope": "EXACT_SANITIZED_PROVIDER_JSON_DOCUMENT",
        "ordered_arrays": "PRESERVED",
        "omitted_defaults": "FORBIDDEN_IN_RECORDED_FIXTURES",
    }:
        raise RuntimeError("ST-1204 hashing contract drifted")

    provenance = _mapping(contract.get("provenance"), label="provenance")
    if set(provenance) != {
        "canonical_inputs",
        "predecessors",
        "installed_contract_repository",
        "contract_schemas",
        "official_provider_references",
    }:
        raise RuntimeError("ST-1204 provenance fields drifted")
    provider = _mapping(
        provenance.get("official_provider_references"),
        label="official_provider_references",
    )
    if provider.get("retrieved_on") != "2026-08-06":
        raise RuntimeError("official GA4 review date drifted")
    sources = _sequence(provider.get("sources"), label="official sources")
    if [_mapping(item, label="official source").get("subject") for item in sources] != [
        "run_report_method",
        "run_report_response",
        "response_metadata",
        "property_quota",
        "row_wire_shape",
        "reporting_identity_method",
        "reporting_identity_resource",
        "error_responses",
        "quotas",
        "dimensions_and_metrics",
    ]:
        raise RuntimeError("official GA4 source inventory drifted")
    semantics = _mapping(provider.get("semantics"), label="provider semantics")
    if semantics != {
        "run_report_method": "POST",
        "run_report_endpoint": RUN_REPORT_ENDPOINT,
        "reporting_identity_method": "GET",
        "reporting_identity_endpoint": REPORTING_IDENTITY_ENDPOINT,
        "request_limit_wire_type": "INT64_STRING",
        "request_offset_wire_type": "INT64_STRING",
        "response_headers_and_values": "REQUEST_ORDERED",
        "response_row_count": "TOTAL_MATCHING_ROWS_INDEPENDENT_OF_PAGINATION",
        "metric_values": "PROVIDER_STRINGS",
        "reporting_identity_values": ["BLENDED", "OBSERVED", "DEVICE_BASED"],
        "quota_error_http_status": 429,
        "quota_error_canonical_status": "RESOURCE_EXHAUSTED",
    }:
        raise RuntimeError("official GA4 semantics drifted")

    request_policy = _mapping(contract.get("request_policy"), label="request_policy")
    if request_policy != {
        "synthetic_property_id": SYNTHETIC_PROPERTY_ID,
        "synthetic_property_resource": SYNTHETIC_PROPERTY_RESOURCE,
        "site_id": SYNTHETIC_SITE_ID,
        "exact_date_range_count": 1,
        "exact_dimensions": list(EXPECTED_DIMENSIONS),
        "exact_metrics": list(EXPECTED_METRICS),
        "dimension_filter": "REQUIRED_NULL",
        "metric_filter": "REQUIRED_NULL",
        "order_bys": "REQUIRED_EMPTY",
        "limit": 2,
        "offset": 0,
        "keep_empty_rows": False,
        "return_property_quota": True,
        "custom_fields": "FORBIDDEN",
        "comparisons": "FORBIDDEN",
        "cohorts": "FORBIDDEN",
        "metric_aggregations": "FORBIDDEN",
        "relative_dates": "FORBIDDEN",
    }:
        raise RuntimeError("ST-1204 request policy drifted")
    if UUID(SYNTHETIC_SITE_ID).version != 4:
        raise RuntimeError("synthetic site ID must remain a version-4 UUID")

    policy = _mapping(
        contract.get("recorded_result_policy"), label="recorded_result_policy"
    )
    required_policy = {
        "synthetic_property_only": True,
        "synthetic_page_path_prefix": SYNTHETIC_PAGE_PREFIX,
        "internal_request_hash": "REQUIRED",
        "wire_request_hash": "REQUIRED",
        "provider_response_hash": "REQUIRED",
        "reporting_identity_response_hash": "REQUIRED_FOR_SUCCESS",
        "dimension_headers": "EXACT_REQUEST_ORDER",
        "metric_headers": "EXACT_REQUEST_ORDER",
        "dimension_values": "EXACT_PROVIDER_ORDER",
        "metric_values": "PRESERVE_PROVIDER_STRINGS",
        "provider_row_count": "PRESERVE_WITHOUT_PAGINATION_REINTERPRETATION",
        "subject_to_thresholding": "PRESERVE_WITHOUT_REINTERPRETATION",
        "data_loss_from_other_row": "PRESERVE_WITHOUT_REINTERPRETATION",
        "sampling_metadata": "PRESERVE_WITHOUT_REINTERPRETATION",
        "timezone": "PRESERVE_WITHOUT_REINTERPRETATION",
        "currency": "PRESERVE_WITHOUT_REINTERPRETATION",
        "empty_reason": "PRESERVE_WITHOUT_REINTERPRETATION",
        "property_quota": "PRESERVE_WITHOUT_REINTERPRETATION",
        "reporting_identity": "PRESERVE_WITHOUT_REINTERPRETATION",
        "baseline_and_late_revised": "SEPARATELY_INSPECTABLE_NO_SUPERSESSION_CLAIM",
        "provider_error_429": "SANITIZED_NO_CANONICAL_ROWS",
    }
    if policy != required_policy:
        raise RuntimeError("ST-1204 recorded-result policy drifted")

    boundary = _mapping(contract.get("boundary"), label="boundary")
    required_boundary = {
        "network": "FORBIDDEN",
        "credentials": "FORBIDDEN",
        "environment_credentials": "FORBIDDEN",
        "google_sdk": "FORBIDDEN",
        "live_api": "NOT_USED",
        "public_collection": "FORBIDDEN",
        "job_dispatch": "FORBIDDEN",
        "event_publication": "FORBIDDEN",
        "database_writes": "FORBIDDEN",
        "persistent_writes": "FORBIDDEN",
        "site_id_to_property_id_mapping": "NOT_DEFINED",
        "admin_config_snapshot_persistence": "NOT_DEFINED",
        "retry_scheduling_policy": "NOT_DEFINED",
        "numeric_conversion_policy": "NOT_DEFINED",
        "dimension_schema_version": "NOT_DEFINED",
        "metric_date_and_grain_hash": "NOT_DEFINED",
        "durable_supersession": "NOT_DEFINED",
        "persistence_mapping": "NOT_DEFINED",
        "consent_and_privacy_configuration": "NOT_DEFINED",
        "local_result": "SOURCE_CONTRACT_CANDIDATE_ONLY",
        "formal_tst_030": "NOT_EXECUTED",
        "production_readiness": "NOT_READY",
    }
    if boundary != required_boundary:
        raise RuntimeError("ST-1204 safe boundary drifted")


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


def _parse_timestamp(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            _text(value, label=label).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise RuntimeError(f"{label} must be an RFC 3339 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{label} must be timezone-aware")
    return parsed


def _validate_expected_hash(
    value: Mapping[str, object],
    expected: object,
    *,
    label: str,
) -> str:
    digest = canonical_json_sha256(value)
    if digest != _text(expected, label=f"{label} sha256"):
        raise RuntimeError(f"{label} hash drifted")
    return digest


def _outbound_request(request: Mapping[str, object]) -> dict[str, object]:
    date_ranges = []
    for raw_range in _sequence(request.get("date_ranges"), label="date_ranges"):
        date_range = _mapping(raw_range, label="date range")
        outbound_range = {
            "startDate": date_range["start_date"],
            "endDate": date_range["end_date"],
        }
        if date_range.get("name") is not None:
            outbound_range["name"] = date_range["name"]
        date_ranges.append(outbound_range)
    return {
        "dateRanges": date_ranges,
        "dimensions": [
            {"name": name}
            for name in _sequence(request.get("dimensions"), label="dimensions")
        ],
        "metrics": [
            {"name": name}
            for name in _sequence(request.get("metrics"), label="metrics")
        ],
        "limit": str(_strict_integer(request.get("limit"), label="limit")),
        "offset": str(_strict_integer(request.get("offset"), label="offset")),
        "keepEmptyRows": request["keep_empty_rows"],
        "returnPropertyQuota": request["return_property_quota"],
    }


def _validate_request(
    request: dict[str, object],
    *,
    expected_sha256: str,
    request_schema: Mapping[str, object],
) -> tuple[str, date, date]:
    if set(request) != REQUEST_KEYS:
        raise RuntimeError("recorded request must contain the exact normalized fields")
    _validate_schema_instance(request_schema, request, label="recorded request")
    if request.get("property_id") != SYNTHETIC_PROPERTY_ID:
        raise RuntimeError("recorded property_id must use the synthetic allowlist")
    ranges = _sequence(request.get("date_ranges"), label="date_ranges")
    if len(ranges) != 1:
        raise RuntimeError("recorded request must contain exactly one date range")
    date_range = _mapping(ranges[0], label="date range")
    if set(date_range) != {"start_date", "end_date", "name"}:
        raise RuntimeError("recorded date range fields drifted")
    if date_range.get("name") is not None:
        raise RuntimeError("recorded date range name must be explicit null")
    try:
        start_date = date.fromisoformat(
            _text(date_range.get("start_date"), label="start_date")
        )
        end_date = date.fromisoformat(
            _text(date_range.get("end_date"), label="end_date")
        )
    except ValueError as exc:
        raise RuntimeError("recorded request dates must be absolute ISO dates") from exc
    if (start_date.isoformat(), end_date.isoformat()) != (
        "2026-07-01",
        "2026-07-02",
    ):
        raise RuntimeError("recorded request date range drifted")
    if tuple(_sequence(request.get("dimensions"), label="dimensions")) != (
        EXPECTED_DIMENSIONS
    ):
        raise RuntimeError("recorded dimensions must retain their exact order")
    if tuple(_sequence(request.get("metrics"), label="metrics")) != EXPECTED_METRICS:
        raise RuntimeError("recorded metrics must retain their exact order")
    if (
        request.get("dimension_filter") is not None
        or request.get("metric_filter") is not None
        or request.get("order_bys") != []
    ):
        raise RuntimeError("filters and ordering are outside this recorded slice")
    if (
        _strict_integer(request.get("limit"), label="limit") != 2
        or _strict_integer(request.get("offset"), label="offset") != 0
        or request.get("keep_empty_rows") is not False
        or request.get("return_property_quota") is not True
    ):
        raise RuntimeError("recorded request defaults or pagination drifted")
    digest = canonical_request_sha256(request)
    if digest != expected_sha256:
        raise RuntimeError("recorded internal request hash drifted")
    return digest, start_date, end_date


def _validate_wire_request(
    request: Mapping[str, object],
    wire_request: dict[str, object],
    *,
    expected_sha256: str,
) -> str:
    if wire_request != _outbound_request(request):
        raise RuntimeError("recorded wire request does not match the internal request")
    if not isinstance(wire_request.get("limit"), str) or not isinstance(
        wire_request.get("offset"), str
    ):
        raise RuntimeError("GA4 wire limit and offset must remain int64 strings")
    return _validate_expected_hash(
        wire_request,
        expected_sha256,
        label="recorded wire request",
    )


def _validate_synthetic_page_path(value: object) -> str:
    path = _text(value, label="pagePath")
    if (
        not path.startswith(SYNTHETIC_PAGE_PREFIX)
        or "\\" in path
        or "?" in path
        or "#" in path
        or "\x00" in path
        or "//" in path
        or any(part in {"", ".", ".."} for part in path.removeprefix("/").split("/"))
        or re.fullmatch(r"/synthetic/[a-z0-9][a-z0-9/-]*", path) is None
    ):
        raise RuntimeError("recorded pagePath must use the synthetic allowlist")
    return path


def _validate_report_metadata(value: object) -> dict[str, object]:
    metadata = _mapping(value, label="runReport metadata")
    if set(metadata) != {
        "dataLossFromOtherRow",
        "samplingMetadatas",
        "schemaRestrictionResponse",
        "currencyCode",
        "timeZone",
        "emptyReason",
        "subjectToThresholding",
    }:
        raise RuntimeError("runReport metadata fields drifted")
    if not isinstance(metadata.get("dataLossFromOtherRow"), bool) or not isinstance(
        metadata.get("subjectToThresholding"), bool
    ):
        raise RuntimeError("runReport metadata flags must be booleans")
    sampling = _sequence(metadata.get("samplingMetadatas"), label="samplingMetadatas")
    if len(sampling) != 1:
        raise RuntimeError("sampling metadata must match the one requested date range")
    sample = _mapping(sampling[0], label="sampling metadata")
    if set(sample) != {"samplesReadCount", "samplingSpaceSize"} or any(
        not isinstance(sample.get(name), str)
        or re.fullmatch(r"[0-9]+", cast(str, sample.get(name))) is None
        for name in ("samplesReadCount", "samplingSpaceSize")
    ):
        raise RuntimeError("sampling metadata counts must remain int64 strings")
    restrictions = _mapping(
        metadata.get("schemaRestrictionResponse"),
        label="schemaRestrictionResponse",
    )
    if restrictions != {"activeMetricRestrictions": []}:
        raise RuntimeError("schema restrictions are outside this synthetic slice")
    currency = metadata.get("currencyCode")
    if not isinstance(currency, str) or re.fullmatch(r"[A-Z]{3}", currency) is None:
        raise RuntimeError("runReport currencyCode is invalid")
    if metadata.get("timeZone") != "Asia/Tokyo":
        raise RuntimeError("runReport synthetic timezone drifted")
    if not isinstance(metadata.get("emptyReason"), str):
        raise RuntimeError("runReport emptyReason must remain a string")
    return metadata


def _validate_property_quota(value: object) -> dict[str, object]:
    quota = _mapping(value, label="propertyQuota")
    if set(quota) != {
        "tokensPerDay",
        "tokensPerHour",
        "concurrentRequests",
        "serverErrorsPerProjectPerHour",
        "potentiallyThresholdedRequestsPerHour",
        "tokensPerProjectPerHour",
    }:
        raise RuntimeError("propertyQuota fields drifted")
    for name, raw_status in quota.items():
        status = _mapping(raw_status, label=f"quota {name}")
        if set(status) != {"consumed", "remaining"}:
            raise RuntimeError("quota status fields drifted")
        for field in ("consumed", "remaining"):
            if _strict_integer(status.get(field), label=f"quota {field}") < 0:
                raise RuntimeError("quota values cannot be negative")
    return quota


def _validate_reporting_identity_capture(
    value: object,
    *,
    recorded_at: datetime,
) -> tuple[dict[str, object], str, str]:
    capture = _mapping(value, label="reporting identity capture")
    if set(capture) != {
        "endpoint",
        "api_version",
        "retrieved_at",
        "response",
        "expected_response_sha256",
    }:
        raise RuntimeError("reporting identity capture fields drifted")
    if (
        capture.get("endpoint") != REPORTING_IDENTITY_ENDPOINT
        or capture.get("api_version") != "v1alpha"
    ):
        raise RuntimeError("reporting identity endpoint or API version drifted")
    if (
        _parse_timestamp(
            capture.get("retrieved_at"), label="reporting identity retrieved_at"
        )
        > recorded_at
    ):
        raise RuntimeError("reporting identity retrieval cannot follow recorded_at")
    response = deepcopy(
        _mapping(capture.get("response"), label="reporting identity response")
    )
    if set(response) != {"name", "reportingIdentity"}:
        raise RuntimeError("reporting identity response fields drifted")
    if response.get("name") != REPORTING_IDENTITY_RESOURCE:
        raise RuntimeError("reporting identity property resource drifted")
    identity = _text(
        response.get("reportingIdentity"), label="reporting identity value"
    )
    if identity not in ALLOWED_REPORTING_IDENTITIES:
        raise RuntimeError("reporting identity value is unsupported")
    digest = _validate_expected_hash(
        response,
        capture.get("expected_response_sha256"),
        label="reporting identity response",
    )
    return response, identity, digest


def _canonical_rows(
    *,
    request: Mapping[str, object],
    response: Mapping[str, object],
    request_sha256: str,
    reporting_identity: str,
    imported_at: str,
    row_schema: Mapping[str, object],
) -> list[dict[str, object]]:
    raw_dimension_headers = _sequence(
        response.get("dimensionHeaders"), label="dimensionHeaders"
    )
    dimension_headers = []
    for raw_header in raw_dimension_headers:
        header = _mapping(raw_header, label="dimension header")
        if set(header) != {"name"}:
            raise RuntimeError("dimension header fields drifted")
        dimension_headers.append(_text(header.get("name"), label="dimension name"))
    if tuple(dimension_headers) != EXPECTED_DIMENSIONS:
        raise RuntimeError("dimension headers must match request order")

    raw_metric_headers = _sequence(response.get("metricHeaders"), label="metricHeaders")
    metric_headers = []
    metric_types = []
    for raw_header in raw_metric_headers:
        header = _mapping(raw_header, label="metric header")
        if set(header) != {"name", "type"}:
            raise RuntimeError("metric header fields drifted")
        metric_headers.append(_text(header.get("name"), label="metric name"))
        metric_types.append(_text(header.get("type"), label="metric type"))
    if tuple(metric_headers) != EXPECTED_METRICS or tuple(metric_types) != (
        EXPECTED_METRIC_TYPES
    ):
        raise RuntimeError("metric headers must match request order and types")

    metadata = _validate_report_metadata(response.get("metadata"))
    quota = _validate_property_quota(response.get("propertyQuota"))
    rows = _sequence(response.get("rows"), label="runReport rows")
    provider_row_count = _strict_integer(
        response.get("rowCount"), label="provider rowCount"
    )
    if provider_row_count < len(rows):
        raise RuntimeError("provider rowCount cannot be below returned row count")

    date_range = _mapping(
        _sequence(request.get("date_ranges"), label="date_ranges")[0],
        label="date range",
    )
    canonical: list[dict[str, object]] = []
    for index, raw_row in enumerate(rows):
        provider_row = _mapping(raw_row, label=f"provider row {index}")
        if set(provider_row) != {"dimensionValues", "metricValues"}:
            raise RuntimeError("provider row fields drifted")
        raw_dimension_values = _sequence(
            provider_row.get("dimensionValues"), label="dimensionValues"
        )
        raw_metric_values = _sequence(
            provider_row.get("metricValues"), label="metricValues"
        )
        if len(raw_dimension_values) != len(dimension_headers) or len(
            raw_metric_values
        ) != len(metric_headers):
            raise RuntimeError("provider row values do not match header counts")
        dimension_values = []
        for raw_value in raw_dimension_values:
            entry = _mapping(raw_value, label="dimension value")
            if set(entry) != {"value"}:
                raise RuntimeError("dimension value fields drifted")
            dimension_values.append(_text(entry.get("value"), label="dimension value"))
        metric_values = []
        for raw_value in raw_metric_values:
            entry = _mapping(raw_value, label="metric value")
            if set(entry) != {"value"}:
                raise RuntimeError("metric value fields drifted")
            metric_value = _text(entry.get("value"), label="metric value")
            if METRIC_VALUE_PATTERN.fullmatch(metric_value) is None:
                raise RuntimeError("metric values must remain provider numeric strings")
            metric_values.append(metric_value)

        try:
            metric_date = datetime.strptime(dimension_values[0], "%Y%m%d").date()
        except ValueError as exc:
            raise RuntimeError("GA4 date dimension must use YYYYMMDD") from exc
        if not (
            date.fromisoformat(cast(str, date_range["start_date"]))
            <= metric_date
            <= date.fromisoformat(cast(str, date_range["end_date"]))
        ):
            raise RuntimeError("GA4 date dimension is outside the requested range")
        _validate_synthetic_page_path(dimension_values[1])
        if dimension_values[2] not in {"desktop", "mobile", "tablet"}:
            raise RuntimeError("deviceCategory is outside the synthetic allowlist")

        row = {
            "site_id": SYNTHETIC_SITE_ID,
            "property_id": SYNTHETIC_PROPERTY_ID,
            "date_from": date_range["start_date"],
            "date_to": date_range["end_date"],
            "dimension_values": dict(
                zip(dimension_headers, dimension_values, strict=True)
            ),
            "metric_values": dict(zip(metric_headers, metric_values, strict=True)),
            "reporting_identity": reporting_identity,
            "date_range_index": 0,
            "imported_at": imported_at,
            "source_request_sha256": request_sha256,
            "thresholding_applied": metadata["subjectToThresholding"],
            "quota_metadata": deepcopy(quota),
        }
        _validate_schema_instance(row_schema, row, label="recorded canonical row")
        canonical.append(row)
    return canonical


def _validate_success_semantics(
    recording_id: str,
    value: object,
) -> dict[str, object]:
    semantics = _mapping(value, label="expected success semantics")
    required = {
        "outcome": "SUCCESS",
        "returned_row_count": 2,
        "provider_row_count": 3,
        "row_count_independent_of_pagination": True,
        "canonical_row_count": 2,
        "configuration_snapshot": "IN_FIXTURE_ONLY",
        "supersession_claim": "NONE",
    }
    if recording_id == "late-revised":
        required["independently_inspectable_from_baseline"] = True
    if semantics != required:
        raise RuntimeError("success recording semantics drifted")
    return semantics


def _validate_error_semantics(value: object) -> dict[str, object]:
    semantics = _mapping(value, label="expected error semantics")
    if semantics != {
        "outcome": "PROVIDER_ERROR",
        "error_sanitized": True,
        "canonical_row_count": 0,
        "retry_scheduling_policy": "NOT_DEFINED",
        "configuration_snapshot": "NOT_CAPTURED_FOR_FAILED_REQUEST",
        "supersession_claim": "NONE",
    }:
        raise RuntimeError("provider-error semantics drifted")
    return semantics


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
        "recorded_at",
        "internal_request",
        "expected_internal_request_sha256",
        "wire_request",
        "expected_wire_request_sha256",
        "run_report_capture",
        "reporting_identity_capture",
        "expected_semantics",
    }
    if set(recording) != expected_fields:
        raise RuntimeError("recording contains unexpected fields")
    recording_id = _text(recording.get("recording_id"), label="recording_id")
    fixture_file = _text(recording.get("fixture_file"), label="fixture_file")
    expected_file_by_id = {
        "baseline": "baseline.json",
        "late-revised": "late-revised.json",
        "provider-error-429": "provider-error-429.json",
    }
    if expected_file_by_id.get(recording_id) != fixture_file:
        raise RuntimeError("recording ID and fixture file do not match")
    normalized = _normalized_relative(fixture_file, label="fixture_file")
    if normalized.parent != Path(".") or normalized.suffix != ".json":
        raise RuntimeError("fixture_file must be one JSON basename")
    if recording.get("synthetic_marker") != SYNTHETIC_MARKER:
        raise RuntimeError("recording must retain the synthetic marker")
    recorded_at_text = _text(recording.get("recorded_at"), label="recorded_at")
    recorded_at = _parse_timestamp(recorded_at_text, label="recorded_at")

    request = deepcopy(
        _mapping(recording.get("internal_request"), label="internal_request")
    )
    request_sha256, _start_date, _end_date = _validate_request(
        request,
        expected_sha256=_text(
            recording.get("expected_internal_request_sha256"),
            label="expected_internal_request_sha256",
        ),
        request_schema=request_schema,
    )
    wire_request = deepcopy(
        _mapping(recording.get("wire_request"), label="wire_request")
    )
    wire_request_sha256 = _validate_wire_request(
        request,
        wire_request,
        expected_sha256=_text(
            recording.get("expected_wire_request_sha256"),
            label="expected_wire_request_sha256",
        ),
    )

    run_capture = deepcopy(
        _mapping(recording.get("run_report_capture"), label="run_report_capture")
    )
    expected_run_fields = {
        "endpoint",
        "api_version",
        "retrieved_at",
        "response",
        "expected_response_sha256",
    }
    if recording_id == "provider-error-429":
        expected_run_fields.add("http_status")
    if set(run_capture) != expected_run_fields:
        raise RuntimeError("runReport capture fields drifted")
    if (
        run_capture.get("endpoint") != RUN_REPORT_ENDPOINT
        or run_capture.get("api_version") != "v1beta"
    ):
        raise RuntimeError("runReport endpoint or API version drifted")
    if (
        _parse_timestamp(
            run_capture.get("retrieved_at"), label="runReport retrieved_at"
        )
        > recorded_at
    ):
        raise RuntimeError("runReport retrieval cannot follow recorded_at")
    response = deepcopy(
        _mapping(run_capture.get("response"), label="runReport response")
    )
    response_sha256 = _validate_expected_hash(
        response,
        run_capture.get("expected_response_sha256"),
        label="runReport response",
    )

    reporting_identity_sha256: str | None
    if recording_id == "provider-error-429":
        if run_capture.get("http_status") != 429:
            raise RuntimeError("provider-error recording must retain HTTP 429")
        if recording.get("reporting_identity_capture") != (
            "NOT_ATTEMPTED_AFTER_PROVIDER_ERROR"
        ):
            raise RuntimeError("reporting identity must not follow provider error")
        error = _mapping(response.get("error"), label="provider error")
        if set(response) != {"error"} or error != {
            "code": 429,
            "message": "Synthetic quota limit reached.",
            "status": "RESOURCE_EXHAUSTED",
        }:
            raise RuntimeError("provider-error response is not the sanitized 429")
        semantics = _validate_error_semantics(recording.get("expected_semantics"))
        reporting_identity_sha256 = None
        canonical_rows: list[dict[str, object]] = []
        recorded_result = {
            "outcome": "PROVIDER_ERROR",
            "recorded_at": recorded_at_text,
            "request_hashes": {
                "internal_request_sha256": request_sha256,
                "wire_request_sha256": wire_request_sha256,
                "run_report_response_sha256": response_sha256,
                "reporting_identity_response_sha256": None,
            },
            "provider_error": deepcopy(response),
            "canonical_rows": canonical_rows,
            "retry_scheduling_policy": "NOT_DEFINED",
            "supersession_claim": "NONE",
            "contract_semantics": deepcopy(semantics),
        }
        provider_row_count: int | None = None
    else:
        if (
            set(response)
            != {
                "dimensionHeaders",
                "metricHeaders",
                "rows",
                "rowCount",
                "metadata",
                "propertyQuota",
                "kind",
            }
            or response.get("kind") != "analyticsData#runReport"
        ):
            raise RuntimeError("successful runReport response fields drifted")
        identity_response, reporting_identity, reporting_identity_sha256 = (
            _validate_reporting_identity_capture(
                recording.get("reporting_identity_capture"),
                recorded_at=recorded_at,
            )
        )
        canonical_rows = _canonical_rows(
            request=request,
            response=response,
            request_sha256=request_sha256,
            reporting_identity=reporting_identity,
            imported_at=recorded_at_text,
            row_schema=row_schema,
        )
        semantics = _validate_success_semantics(
            recording_id,
            recording.get("expected_semantics"),
        )
        if len(canonical_rows) != semantics["canonical_row_count"]:
            raise RuntimeError("canonical row count differs from contract semantics")
        provider_row_count = _strict_integer(
            response.get("rowCount"), label="provider rowCount"
        )
        if (
            provider_row_count != semantics["provider_row_count"]
            or len(_sequence(response.get("rows"), label="runReport rows"))
            != semantics["returned_row_count"]
        ):
            raise RuntimeError("runReport pagination semantics drifted")
        recorded_result = {
            "outcome": "SUCCESS",
            "recorded_at": recorded_at_text,
            "request_hashes": {
                "internal_request_sha256": request_sha256,
                "wire_request_sha256": wire_request_sha256,
                "run_report_response_sha256": response_sha256,
                "reporting_identity_response_sha256": reporting_identity_sha256,
            },
            "pagination": {
                "limit": request["limit"],
                "offset": request["offset"],
                "returned_row_count": len(canonical_rows),
                "provider_row_count": provider_row_count,
                "row_count_independent_of_pagination": True,
            },
            "raw_ordered_report": {
                "dimension_headers": deepcopy(response["dimensionHeaders"]),
                "metric_headers": deepcopy(response["metricHeaders"]),
                "rows": deepcopy(response["rows"]),
            },
            "report_metadata": deepcopy(response["metadata"]),
            "property_quota": deepcopy(response["propertyQuota"]),
            "reporting_identity_snapshot": identity_response,
            "canonical_rows": canonical_rows,
            "supersession_claim": "NONE",
            "contract_semantics": deepcopy(semantics),
        }

    fixture = {
        "fixture_version": FIXTURE_VERSION,
        "recording_id": recording_id,
        "synthetic_marker": SYNTHETIC_MARKER,
        "internal_request": request,
        "internal_request_sha256": request_sha256,
        "wire_request": wire_request,
        "wire_request_sha256": wire_request_sha256,
        "provider_capture": {
            "run_report": run_capture,
            "reporting_identity": deepcopy(recording["reporting_identity_capture"]),
        },
        "recorded_result": recorded_result,
    }
    _validate_json_graph(fixture, label=f"recording {recording_id}")
    _scan_recorded_material(fixture, label=f"recording {recording_id}")
    content = _sorted_json(fixture, compact=False)
    if len(content) > MAX_GENERATED_BYTES:
        raise RuntimeError("generated fixture exceeds its size limit")
    inventory = {
        "path": fixture_file,
        "recording_id": recording_id,
        "recorded_at": recorded_at_text,
        "outcome": recorded_result["outcome"],
        "bytes": len(content),
        "sha256": _sha256(content),
        "internal_request_sha256": request_sha256,
        "wire_request_sha256": wire_request_sha256,
        "run_report_response_sha256": response_sha256,
        "reporting_identity_response_sha256": reporting_identity_sha256,
        "limit": request["limit"],
        "offset": request["offset"],
        "returned_row_count": len(canonical_rows),
        "provider_row_count": provider_row_count,
        "canonical_row_count": len(canonical_rows),
        "supersession_claim": "NONE",
    }
    return fixture_file, content, inventory


def build_outputs(root: Path = REPOSITORY_ROOT) -> dict[Path, bytes]:
    contract_content = _read_regular(
        root,
        CONTRACT_PATH,
        label="ST-1204 source contract",
        maximum_bytes=MAX_CONTRACT_BYTES,
    )
    contract = _load_yaml(contract_content)
    _validate_exact_contract(contract)
    captured = _validate_pinned_sources(root, contract)
    request_schema = _schema_by_role(contract, "run_report_request", captured)
    row_schema = _schema_by_role(contract, "canonical_metric_row", captured)

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
    provider_error = by_id.get("provider-error-429")
    if baseline is None or revised is None or provider_error is None:
        raise RuntimeError("the three required recording scenarios are missing")
    if baseline["internal_request_sha256"] != revised["internal_request_sha256"]:
        raise RuntimeError("baseline and late-revised must bind the same request hash")
    if baseline["wire_request_sha256"] != revised["wire_request_sha256"]:
        raise RuntimeError("baseline and late-revised must bind the same wire hash")
    if baseline["run_report_response_sha256"] == revised["run_report_response_sha256"]:
        raise RuntimeError("late-revised must preserve a changed provider response")
    if _parse_timestamp(
        cast(str, revised["recorded_at"]), label="late-revised recorded_at"
    ) <= _parse_timestamp(
        cast(str, baseline["recorded_at"]), label="baseline recorded_at"
    ):
        raise RuntimeError("late-revised must be captured later than baseline")
    if baseline["outcome"] != "SUCCESS" or revised["outcome"] != "SUCCESS":
        raise RuntimeError("baseline and late-revised must be successful recordings")
    if provider_error["outcome"] != "PROVIDER_ERROR":
        raise RuntimeError("provider-error-429 must preserve a provider error")
    if (
        provider_error["returned_row_count"] != 0
        or provider_error["provider_row_count"] is not None
        or provider_error["canonical_row_count"] != 0
        or provider_error["reporting_identity_response_sha256"] is not None
    ):
        raise RuntimeError(
            "provider-error-429 must contain no rows or identity response"
        )

    generator_content = _read_regular(
        root,
        GENERATOR_PATH,
        label="ST-1204 generator",
        maximum_bytes=MAX_SOURCE_BYTES,
    )
    manifest = {
        "document": {
            "id": "RAOS-GA4-RECORDED-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1204",
        },
        "generation": {
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": contract["generation"]["generation_command"],
            "check_command": contract["generation"]["check_command"],
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
        "hashing": deepcopy(contract["hashing"]),
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
        print(f"ST-1204 recorded fixture generation failed: {exc}", file=os.sys.stderr)
        return 1
    action = "verified" if arguments.check else "generated"
    print(f"ST-1204 recorded fixtures {action}; manifest sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
