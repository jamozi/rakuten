#!/usr/bin/env python3
"""Generate and verify the closed ST-1204 GA4 fixture bundle."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
from copy import deepcopy
import ctypes
from datetime import date, datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from jsonschema import Draft202012Validator, FormatChecker  # type: ignore[import-untyped]
from jsonschema.exceptions import (  # type: ignore[import-untyped]
    SchemaError,
    ValidationError,
)
import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
STORY_ROOT: Final = Path("changes/st-1204")
CONTRACT_PATH: Final = Path("changes/st-1204/contracts/ga4-recorded-fixtures.v1.yaml")
PUBLICATION_DESIGN_PATH: Final = Path(
    "changes/st-1204/DESIGN_HANDOFF_V1_ST1204_FIXTURE_v1.yaml"
)
GENERATED_ROOT: Final = STORY_ROOT / "generated"
FIXTURE_ROOT: Final = GENERATED_ROOT / "fixtures/recorded"
MANIFEST_PATH: Final = GENERATED_ROOT / "manifest.json"
LEGACY_FIXTURE_ROOT: Final = STORY_ROOT / "fixtures/recorded"
LEGACY_MANIFEST_PATH: Final = STORY_ROOT / "manifest.json"
GENERATOR_PATH: Final = Path("scripts/build_st1204_ga4_recorded_adapter.py")
MAX_CONTRACT_BYTES: Final = 256 * 1024
MAX_DESIGN_BYTES: Final = 256 * 1024
MAX_SOURCE_BYTES: Final = 16 * 1024 * 1024
MAX_GENERATED_BYTES: Final = 256 * 1024
FIXTURE_VERSION: Final = "1.0.0"
MANIFEST_VERSION: Final = "1.1.0"
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
RENAME_NOREPLACE: Final = 1
RENAME_EXCHANGE: Final = 2
STAGE_NAME: Final = ".generated.st1204.stage"
JOURNAL_PREPARING_NAME: Final = ".generated.st1204.transaction.preparing"
JOURNAL_NAME: Final = ".generated.st1204.transaction"
JOURNAL_CLEANUP_NAME: Final = ".generated.st1204.transaction.cleanup."
JOURNAL_STATE_NAME: Final = "state.000.json"
JOURNAL_STATE_PREFIX: Final = "state."
JOURNAL_STATE_PREPARING_SUFFIX: Final = ".preparing"
MAX_JOURNAL_STATES: Final = 32
JOURNAL_SCHEMA: Final = "ST1204_ATOMIC_PUBLICATION_V2"
JOURNAL_PHASES: Final = frozenset(
    {"PREPARED", "COMMITTED", "ROLLED_BACK", "DRIFT_REFUSAL"}
)
CLEANUP_PHASES: Final = frozenset(
    {
        "NONE",
        "BUNDLE_QUARANTINING",
        "BUNDLE_DELETING",
        "BUNDLE_REMOVED",
        "LEGACY_QUARANTINING",
        "LEGACY_DELETING",
        "CLEANUP_COMPLETE",
    }
)
BUNDLE_CLEANUP_PREFIX: Final = ".generated.st1204.bundle-cleanup."
LEGACY_CLEANUP_PREFIX: Final = ".generated.st1204.legacy-cleanup."
DELETE_TOMBSTONE_PREFIX: Final = ".st1204-delete."
LEGACY_MANIFEST_SHA256: Final = (
    "14596e1852b6d99c7359a2a5354f9ec03e9d189aaa6979335d8fe71b76490f91"
)
EXPECTED_BUNDLE_PATHS: Final = (
    "manifest.json",
    *(f"fixtures/recorded/{name}" for name in EXPECTED_FIXTURE_NAMES),
)
StatSignature = tuple[int, int, int, int, int, int, int]


class PublicationRecoveryRequired(RuntimeError):
    """A durable ST-1204 publication needs another owner invocation."""


class _InvocationIdentityDrift(PublicationRecoveryRequired):
    """An invocation-owned inode changed and must not be re-captured."""


class _ActiveJournalTrust:
    """Invocation-local identities that journal bytes cannot self-attest."""

    __slots__ = ("root_signature", "state_signatures")

    root_signature: StatSignature | None
    state_signatures: dict[str, StatSignature]

    def __init__(
        self,
        *,
        root_signature: StatSignature | None = None,
        state_signatures: Mapping[str, StatSignature] | None = None,
    ) -> None:
        self.root_signature = root_signature
        self.state_signatures = (
            {} if state_signatures is None else dict(state_signatures)
        )


class _ActiveStageTrust:
    """Invocation-local identities for a stage created by this process."""

    __slots__ = ("directory_identities", "file_signatures")

    def __init__(self) -> None:
        self.directory_identities: dict[str, tuple[int, int]] = {}
        self.file_signatures: dict[str, StatSignature] = {}


def _checkpoint(_name: str) -> None:
    """Fault-injection seam; production generation deliberately does nothing."""


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


def _stat_signature(metadata: os.stat_result) -> StatSignature:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _entry_identity(metadata: os.stat_result) -> tuple[int, int]:
    return metadata.st_dev, metadata.st_ino


def _identity_record(identity: tuple[int, int] | None) -> dict[str, int] | None:
    if identity is None:
        return None
    return {"dev": identity[0], "ino": identity[1]}


def _validated_identity(value: object, *, label: str) -> tuple[int, int] | None:
    if value is None:
        return None
    record = _mapping(value, label=label)
    if set(record) != {"dev", "ino"}:
        raise PublicationRecoveryRequired(f"{label} fields drifted")
    dev = record.get("dev")
    ino = record.get("ino")
    if type(dev) is not int or type(ino) is not int or dev < 0 or ino <= 0:
        raise PublicationRecoveryRequired(f"{label} is malformed")
    return dev, ino


def _identity_map_record(
    identities: Mapping[str, tuple[int, int]],
) -> dict[str, dict[str, int]]:
    return {
        name: cast(dict[str, int], _identity_record(identity))
        for name, identity in sorted(identities.items())
    }


def _validated_identity_map(
    value: object,
    *,
    label: str,
    expected_names: set[str],
) -> dict[str, tuple[int, int]]:
    record = _mapping(value, label=label)
    if set(record) != expected_names:
        raise PublicationRecoveryRequired(f"{label} inventory drifted")
    result: dict[str, tuple[int, int]] = {}
    for name, identity_record in record.items():
        identity = _validated_identity(identity_record, label=f"{label} {name}")
        if identity is None:
            raise PublicationRecoveryRequired(f"{label} {name} is missing")
        result[name] = identity
    return result


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
            expected = _text(entry.get("sha256"), label="source sha256")
            if group_name != "predecessors" and _sha256(content) != expected:
                raise RuntimeError(f"pinned source hash drift in {group_name}")
            captured[relative] = content

    publication_design = _mapping(
        provenance.get("publication_design"), label="publication_design"
    )
    if set(publication_design) != {"uri", "sha256"}:
        raise RuntimeError("publication design fields drifted")
    relative = _repo_uri_path(
        publication_design.get("uri"), label="publication design URI"
    )
    if relative != PUBLICATION_DESIGN_PATH or relative in seen:
        raise RuntimeError("ST-1204 publication design path drifted")
    content = _read_regular(
        root,
        relative,
        label="ST-1204 publication design",
        maximum_bytes=MAX_DESIGN_BYTES,
    )
    if _sha256(content) != _text(
        publication_design.get("sha256"), label="publication design sha256"
    ):
        raise RuntimeError("ST-1204 publication design hash drift")
    seen.add(relative)
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
        "version": "1.1.0",
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
        "publication_design": PUBLICATION_DESIGN_PATH.as_posix(),
        "authoritative_root": GENERATED_ROOT.as_posix(),
        "fixture_root": FIXTURE_ROOT.as_posix(),
        "manifest_path": MANIFEST_PATH.as_posix(),
        "legacy_fixture_root": LEGACY_FIXTURE_ROOT.as_posix(),
        "legacy_manifest_path": LEGACY_MANIFEST_PATH.as_posix(),
        "legacy_disposition": (
            "NON_AUTHORITATIVE_AFTER_COMMIT_THEN_DESCRIPTOR_RELATIVE_REMOVAL"
        ),
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
        "publication_design",
        "installed_contract_repository",
        "contract_schemas",
        "official_provider_references",
    }:
        raise RuntimeError("ST-1204 provenance fields drifted")
    provider = _mapping(
        provenance.get("official_provider_references"),
        label="official_provider_references",
    )
    if provider.get("retrieved_on") != "2026-08-25":
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
    recorded_result: dict[str, object]
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
    source_generation = _mapping(contract.get("generation"), label="generation")
    manifest = {
        "document": {
            "id": "RAOS-GA4-RECORDED-MANIFEST-001",
            "version": MANIFEST_VERSION,
            "story_id": "ST-1204",
        },
        "generation": {
            "source_contract": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": source_generation["generation_command"],
            "check_command": source_generation["check_command"],
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
            {
                "uri": f"repo://{PUBLICATION_DESIGN_PATH.as_posix()}",
                "bytes": len(captured[PUBLICATION_DESIGN_PATH]),
                "sha256": _sha256(captured[PUBLICATION_DESIGN_PATH]),
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


def _checked_entry_name(name: str, *, label: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise RuntimeError(f"unsafe {label} entry name")
    return name


def _directory_open_flags() -> int:
    if not os.O_DIRECTORY or not os.O_NOFOLLOW:
        raise RuntimeError("ST-1204 publication requires O_DIRECTORY and O_NOFOLLOW")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


def _open_story_directory(root: Path, *, create: bool) -> int:
    try:
        root_metadata = root.lstat()
    except OSError as exc:
        raise RuntimeError("physical repository root is unavailable") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("physical repository root must be a real directory")
    try:
        descriptor = os.open(root, _directory_open_flags())
    except OSError as exc:
        raise RuntimeError("physical repository root could not be opened") from exc
    try:
        opened_root = os.fstat(descriptor)
        if (opened_root.st_dev, opened_root.st_ino) != (
            root_metadata.st_dev,
            root_metadata.st_ino,
        ):
            raise RuntimeError("physical repository root identity changed")
        for component in STORY_ROOT.parts:
            _checked_entry_name(component, label="Story directory")
            if create:
                try:
                    os.mkdir(component, 0o755, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            try:
                child = os.open(
                    component,
                    _directory_open_flags(),
                    dir_fd=descriptor,
                )
            except OSError as exc:
                raise RuntimeError(
                    "ST-1204 Story directory is missing or unsafe"
                ) from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _acquire_story_lock(root: Path, *, exclusive: bool, create: bool) -> int:
    descriptor = _open_story_directory(root, create=create)
    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        fcntl.flock(descriptor, mode | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as exc:
        os.close(descriptor)
        raise RuntimeError(
            "another ST-1204 generate/check operation is active"
        ) from exc
    return descriptor


def _release_story_lock(descriptor: int, primary: BaseException | None) -> None:
    cleanup_error: OSError | None = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
    except OSError as exc:
        cleanup_error = exc
    try:
        os.close(descriptor)
    except OSError as exc:
        cleanup_error = cleanup_error or exc
    if cleanup_error is not None and primary is not None:
        primary.add_note("ST-1204 Story lock cleanup also failed")
    elif cleanup_error is not None:
        raise cleanup_error


def _entry_metadata_at(parent_fd: int, name: str) -> os.stat_result | None:
    _checked_entry_name(name, label="managed")
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"cannot inspect managed ST-1204 entry: {name}") from exc


def _open_directory_at(parent_fd: int, name: str, *, label: str) -> int:
    _checked_entry_name(name, label=label)
    try:
        descriptor = os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(f"{label} must be a non-symlink directory") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode):
        os.close(descriptor)
        raise RuntimeError(f"{label} must open as a directory")
    return descriptor


def _assert_directory_entry_identity_at(
    parent_fd: int, name: str, descriptor: int, *, label: str
) -> None:
    current = _entry_metadata_at(parent_fd, name)
    opened = os.fstat(descriptor)
    if (
        current is None
        or stat.S_ISLNK(current.st_mode)
        or not stat.S_ISDIR(current.st_mode)
        or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise PublicationRecoveryRequired(f"{label} identity changed")


def _assert_directory_signature_at(
    parent_fd: int,
    name: str,
    descriptor: int,
    *,
    expected_signature: StatSignature,
    label: str,
) -> None:
    current = _entry_metadata_at(parent_fd, name)
    opened_signature = _stat_signature(os.fstat(descriptor))
    if (
        current is None
        or _stat_signature(current) != expected_signature
        or opened_signature != expected_signature
    ):
        raise _InvocationIdentityDrift(f"{label} directory signature changed")


def _directory_names_at(descriptor: int, *, label: str) -> set[str]:
    try:
        with os.scandir(descriptor) as entries:
            return {entry.name for entry in entries}
    except OSError as exc:
        raise RuntimeError(f"cannot scan {label}") from exc


def _read_regular_stat_capture_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    maximum_bytes: int = MAX_GENERATED_BYTES,
) -> tuple[bytes, StatSignature]:
    metadata = _entry_metadata_at(parent_fd, name)
    if (
        metadata is None
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
    ):
        raise RuntimeError(f"{label} must be a one-link regular file")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise RuntimeError(f"{label} could not be opened safely") from exc
    primary: BaseException | None = None
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > maximum_bytes
            or _entry_identity(before) != _entry_identity(metadata)
        ):
            raise RuntimeError(f"{label} exceeds its safe file boundary")
        chunks: list[bytes] = []
        remaining = maximum_bytes + 1
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        content = b"".join(chunks)
        after = os.fstat(descriptor)
        if (
            after.st_nlink != 1
            or len(content) > maximum_bytes
            or len(content) != after.st_size
            or _stat_signature(before) != _stat_signature(after)
        ):
            raise RuntimeError(f"{label} changed while it was read")
        signature = _stat_signature(after)
        current = _entry_metadata_at(parent_fd, name)
        if current is None or _stat_signature(current) != signature:
            raise PublicationRecoveryRequired(f"{label} entry identity changed")
        return content, signature
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if primary is not None:
                primary.add_note(f"{label} descriptor cleanup also failed")
            else:
                raise exc


def _read_regular_capture_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    maximum_bytes: int = MAX_GENERATED_BYTES,
) -> tuple[bytes, tuple[int, int]]:
    content, signature = _read_regular_stat_capture_at(
        parent_fd,
        name,
        label=label,
        maximum_bytes=maximum_bytes,
    )
    return content, (signature[0], signature[1])


def _read_regular_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    maximum_bytes: int = MAX_GENERATED_BYTES,
) -> bytes:
    content, _identity = _read_regular_capture_at(
        parent_fd,
        name,
        label=label,
        maximum_bytes=maximum_bytes,
    )
    return content


def _create_regular_at(
    parent_fd: int,
    name: str,
    content: bytes,
    *,
    label: str,
) -> None:
    _checked_entry_name(name, label=label)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(f"cannot create {label}") from exc
    primary: BaseException | None = None
    try:
        offset = 0
        while offset < len(content):
            written = os.write(descriptor, content[offset:])
            if written <= 0:
                raise RuntimeError(f"short write while creating {label}")
            offset += written
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if primary is not None:
                primary.add_note(f"{label} descriptor cleanup also failed")
            else:
                raise exc


def _delete_tombstone_name(name: str) -> str:
    _checked_entry_name(name, label="cleanup tombstone source")
    tombstone = f"{DELETE_TOMBSTONE_PREFIX}{name}"
    _checked_entry_name(tombstone, label="cleanup tombstone")
    return tombstone


def _restore_mismatched_quarantine_at(
    parent_fd: int, source: str, quarantine: str, *, label: str
) -> NoReturn:
    if (
        _entry_metadata_at(parent_fd, source) is None
        and _entry_metadata_at(parent_fd, quarantine) is not None
    ):
        _rename_noreplace_at(parent_fd, quarantine, source)
        os.fsync(parent_fd)
    raise PublicationRecoveryRequired(f"{label} quarantine identity drifted")


def _unlink_regular_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    expected_content: bytes | None = None,
    expected_sha256: str | None = None,
    expected_identity: tuple[int, int] | None = None,
    expected_signature: StatSignature | None = None,
    checkpoint: str | None = None,
) -> None:
    tombstone = _delete_tombstone_name(name)
    source = _entry_metadata_at(parent_fd, name)
    quarantined = _entry_metadata_at(parent_fd, tombstone)
    if source is None and quarantined is None:
        return
    if source is not None and quarantined is not None:
        raise PublicationRecoveryRequired(f"conflicting {label} cleanup entries")
    captured_identity: tuple[int, int] | None = None
    captured_signature: StatSignature | None = None
    quarantine_signature: StatSignature | None = None
    observed_content: bytes
    if source is not None:
        observed_content, captured_signature = _read_regular_stat_capture_at(
            parent_fd,
            name,
            label=label,
        )
        captured_identity = (captured_signature[0], captured_signature[1])
        if expected_content is not None and observed_content != expected_content:
            raise PublicationRecoveryRequired(f"{label} bytes are unowned")
        if expected_sha256 is not None and _sha256(observed_content) != expected_sha256:
            raise PublicationRecoveryRequired(f"{label} digest is unowned")
        if expected_identity is not None and captured_identity != expected_identity:
            raise PublicationRecoveryRequired(f"{label} identity is unowned")
        if expected_signature is not None and captured_signature != expected_signature:
            raise PublicationRecoveryRequired(f"{label} signature is unowned")
        if checkpoint is not None:
            _checkpoint(f"before-{checkpoint}-quarantine")
        _rename_noreplace_at(parent_fd, name, tombstone)
        os.fsync(parent_fd)
        moved = _entry_metadata_at(parent_fd, tombstone)
        if (
            moved is None
            or _entry_identity(moved) != captured_identity
            or _stat_signature(moved)[:-1] != captured_signature[:-1]
            or _entry_metadata_at(parent_fd, name) is not None
        ):
            _restore_mismatched_quarantine_at(parent_fd, name, tombstone, label=label)
        quarantine_signature = _stat_signature(moved)
        if checkpoint is not None:
            _checkpoint(f"after-{checkpoint}-quarantine")
    else:
        observed_content, captured_signature = _read_regular_stat_capture_at(
            parent_fd,
            tombstone,
            label=f"quarantined {label}",
        )
        captured_identity = (captured_signature[0], captured_signature[1])
        if expected_content is not None and observed_content != expected_content:
            raise PublicationRecoveryRequired(f"quarantined {label} bytes are unowned")
        if expected_sha256 is not None and _sha256(observed_content) != expected_sha256:
            raise PublicationRecoveryRequired(f"quarantined {label} digest is unowned")
        if expected_identity is not None and captured_identity != expected_identity:
            raise PublicationRecoveryRequired(
                f"quarantined {label} identity is unowned"
            )
        if expected_signature is not None and captured_signature != expected_signature:
            raise PublicationRecoveryRequired(
                f"quarantined {label} signature is unowned"
            )
        quarantine_signature = captured_signature
    if checkpoint is not None:
        _checkpoint(f"before-{checkpoint}-unlink")
    confirmed_content, confirmed_signature = _read_regular_stat_capture_at(
        parent_fd,
        tombstone,
        label=f"quarantined {label}",
    )
    confirmed_identity = (confirmed_signature[0], confirmed_signature[1])
    if (
        confirmed_identity != captured_identity
        or confirmed_signature != quarantine_signature
        or confirmed_content != observed_content
        or (expected_content is not None and confirmed_content != expected_content)
        or (
            expected_sha256 is not None
            and _sha256(confirmed_content) != expected_sha256
        )
        or (expected_identity is not None and confirmed_identity != expected_identity)
    ):
        raise PublicationRecoveryRequired(
            f"quarantined {label} signature changed before unlink"
        )
    os.unlink(tombstone, dir_fd=parent_fd)
    os.fsync(parent_fd)
    if checkpoint is not None:
        _checkpoint(f"after-{checkpoint}-unlink")


def _rmdir_empty_at(
    parent_fd: int,
    name: str,
    *,
    label: str,
    expected_identity: tuple[int, int] | None = None,
    checkpoint: str | None = None,
) -> None:
    tombstone = _delete_tombstone_name(name)
    source = _entry_metadata_at(parent_fd, name)
    quarantined = _entry_metadata_at(parent_fd, tombstone)
    if source is None and quarantined is None:
        return
    if source is not None and quarantined is not None:
        raise PublicationRecoveryRequired(f"conflicting {label} directory cleanup")
    captured_identity: tuple[int, int]
    quarantine_signature: StatSignature
    if source is not None:
        descriptor = _open_directory_at(parent_fd, name, label=label)
        try:
            source_signature = _stat_signature(os.fstat(descriptor))
            captured_identity = (source_signature[0], source_signature[1])
            if expected_identity is not None and captured_identity != expected_identity:
                raise PublicationRecoveryRequired(f"{label} identity is unowned")
            if _directory_names_at(descriptor, label=label):
                raise PublicationRecoveryRequired(f"{label} is not empty")
            _assert_directory_entry_identity_at(
                parent_fd, name, descriptor, label=label
            )
            if checkpoint is not None:
                _checkpoint(f"before-{checkpoint}-quarantine")
            _rename_noreplace_at(parent_fd, name, tombstone)
            os.fsync(parent_fd)
            moved = _entry_metadata_at(parent_fd, tombstone)
            if (
                moved is None
                or _entry_identity(moved) != captured_identity
                or _stat_signature(moved)[:-1] != source_signature[:-1]
                or _entry_metadata_at(parent_fd, name) is not None
            ):
                _restore_mismatched_quarantine_at(
                    parent_fd,
                    name,
                    tombstone,
                    label=f"{label} directory",
                )
            quarantine_signature = _stat_signature(moved)
        finally:
            os.close(descriptor)
        if checkpoint is not None:
            _checkpoint(f"after-{checkpoint}-quarantine")
    else:
        descriptor = _open_directory_at(
            parent_fd, tombstone, label=f"quarantined {label}"
        )
        try:
            quarantine_signature = _stat_signature(os.fstat(descriptor))
            captured_identity = (
                quarantine_signature[0],
                quarantine_signature[1],
            )
            if expected_identity is not None and captured_identity != expected_identity:
                raise PublicationRecoveryRequired(
                    f"quarantined {label} identity is unowned"
                )
            if _directory_names_at(descriptor, label=f"quarantined {label}"):
                raise PublicationRecoveryRequired(f"quarantined {label} is not empty")
        finally:
            os.close(descriptor)
    if checkpoint is not None:
        _checkpoint(f"before-{checkpoint}-rmdir")
    descriptor = _open_directory_at(parent_fd, tombstone, label=f"quarantined {label}")
    try:
        if _directory_names_at(descriptor, label=f"quarantined {label}"):
            raise PublicationRecoveryRequired(f"quarantined {label} changed")
        _assert_directory_signature_at(
            parent_fd,
            tombstone,
            descriptor,
            expected_signature=quarantine_signature,
            label=f"quarantined {label}",
        )
        os.rmdir(tombstone, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(descriptor)
    if checkpoint is not None:
        _checkpoint(f"after-{checkpoint}-rmdir")


def _bundle_files(outputs: Mapping[Path, bytes]) -> dict[str, bytes]:
    expected_paths = {
        MANIFEST_PATH,
        *(FIXTURE_ROOT / name for name in EXPECTED_FIXTURE_NAMES),
    }
    if set(outputs) != expected_paths:
        raise RuntimeError("generated output paths drifted from the atomic bundle")
    result: dict[str, bytes] = {}
    for relative, content in outputs.items():
        try:
            bundled = relative.relative_to(GENERATED_ROOT).as_posix()
        except ValueError as exc:
            raise RuntimeError("generated output escapes the bundle root") from exc
        result[bundled] = content
    if tuple(sorted(result)) != tuple(sorted(EXPECTED_BUNDLE_PATHS)):
        raise RuntimeError("generated atomic bundle inventory drifted")
    _validate_bundle_files(result)
    return result


def _validate_bundle_files(files: Mapping[str, bytes]) -> str:
    if set(files) != set(EXPECTED_BUNDLE_PATHS):
        raise RuntimeError("ST-1204 generated tree inventory is not exact")
    manifest_content = files["manifest.json"]
    manifest = _load_json(manifest_content, label="ST-1204 generated manifest")
    document = _mapping(manifest.get("document"), label="generated manifest document")
    if (
        document.get("id") != "RAOS-GA4-RECORDED-MANIFEST-001"
        or document.get("story_id") != "ST-1204"
        or document.get("version") not in {"1.0.0", MANIFEST_VERSION}
        or manifest.get("fixture_count") != len(EXPECTED_FIXTURE_NAMES)
    ):
        raise RuntimeError("ST-1204 generated manifest identity drifted")
    fixtures = [
        _mapping(value, label="generated manifest fixture")
        for value in _sequence(manifest.get("fixtures"), label="manifest fixtures")
    ]
    if [value.get("path") for value in fixtures] != list(EXPECTED_FIXTURE_NAMES):
        raise RuntimeError("ST-1204 generated manifest fixture inventory drifted")
    for fixture in fixtures:
        name = _text(fixture.get("path"), label="manifest fixture path")
        content = files[f"fixtures/recorded/{name}"]
        if fixture.get("bytes") != len(content) or fixture.get("sha256") != _sha256(
            content
        ):
            raise RuntimeError("ST-1204 generated fixture integrity drifted")
    return _sha256(manifest_content)


def _read_bundle_capture_at(
    story_fd: int, name: str, *, allow_missing: bool
) -> tuple[dict[str, bytes], dict[str, tuple[int, int]]] | None:
    metadata = _entry_metadata_at(story_fd, name)
    if metadata is None:
        if allow_missing:
            return None
        raise RuntimeError("ST-1204 generated bundle is missing")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError("ST-1204 generated bundle must be a real directory")
    root_fd = _open_directory_at(story_fd, name, label="generated bundle")
    fixtures_fd: int | None = None
    recorded_fd: int | None = None
    try:
        if _directory_names_at(root_fd, label="generated bundle") != {
            "manifest.json",
            "fixtures",
        }:
            raise RuntimeError("ST-1204 generated bundle top-level inventory drifted")
        fixtures_fd = _open_directory_at(root_fd, "fixtures", label="fixture directory")
        if _directory_names_at(fixtures_fd, label="fixture directory") != {"recorded"}:
            raise RuntimeError("ST-1204 fixture directory inventory drifted")
        recorded_fd = _open_directory_at(
            fixtures_fd, "recorded", label="recorded fixture directory"
        )
        if _directory_names_at(recorded_fd, label="recorded fixture directory") != set(
            EXPECTED_FIXTURE_NAMES
        ):
            raise RuntimeError("ST-1204 recorded fixture inventory drifted")
        manifest_content, manifest_identity = _read_regular_capture_at(
            root_fd, "manifest.json", label="generated manifest"
        )
        files = {"manifest.json": manifest_content}
        identities = {
            ".": _entry_identity(os.fstat(root_fd)),
            "manifest.json": manifest_identity,
            "fixtures": _entry_identity(os.fstat(fixtures_fd)),
            "fixtures/recorded": _entry_identity(os.fstat(recorded_fd)),
        }
        for fixture_name in EXPECTED_FIXTURE_NAMES:
            content, identity = _read_regular_capture_at(
                recorded_fd,
                fixture_name,
                label=f"generated fixture {fixture_name}",
            )
            path = f"fixtures/recorded/{fixture_name}"
            files[path] = content
            identities[path] = identity
        _validate_bundle_files(files)
        _assert_directory_entry_identity_at(
            fixtures_fd,
            "recorded",
            recorded_fd,
            label="recorded fixture directory",
        )
        _assert_directory_entry_identity_at(
            root_fd, "fixtures", fixtures_fd, label="fixture directory"
        )
        _assert_directory_entry_identity_at(
            story_fd, name, root_fd, label="generated bundle"
        )
        return files, identities
    finally:
        for descriptor in (recorded_fd, fixtures_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)


def _read_bundle_at(
    story_fd: int, name: str, *, allow_missing: bool
) -> dict[str, bytes] | None:
    captured = _read_bundle_capture_at(story_fd, name, allow_missing=allow_missing)
    return None if captured is None else captured[0]


def _assert_stage_trust_at(
    story_fd: int,
    expected: Mapping[str, bytes],
    trust: _ActiveStageTrust,
    *,
    complete: bool,
) -> None:
    root_identity = trust.directory_identities.get(".")
    if root_identity is None:
        raise _InvocationIdentityDrift(
            "partial publication stage has no invocation ownership"
        )
    stage_fd = _open_directory_at(
        story_fd, STAGE_NAME, label="invocation-owned publication stage"
    )
    fixtures_fd: int | None = None
    recorded_fd: int | None = None
    try:
        if _entry_identity(os.fstat(stage_fd)) != root_identity:
            raise _InvocationIdentityDrift(
                "partial publication stage invocation identity drifted"
            )
        expected_root_names: set[str] = set()
        if "manifest.json" in trust.file_signatures:
            expected_root_names.add("manifest.json")
        if "fixtures" in trust.directory_identities:
            expected_root_names.add("fixtures")
        if (
            _directory_names_at(stage_fd, label="invocation-owned publication stage")
            != expected_root_names
        ):
            raise _InvocationIdentityDrift(
                "partial publication stage invocation inventory drifted"
            )
        manifest_signature = trust.file_signatures.get("manifest.json")
        if manifest_signature is not None:
            content, signature = _read_regular_stat_capture_at(
                stage_fd, "manifest.json", label="invocation-owned staged manifest"
            )
            if signature != manifest_signature or content != expected["manifest.json"]:
                raise _InvocationIdentityDrift(
                    "partial staged manifest invocation identity drifted"
                )
        fixtures_identity = trust.directory_identities.get("fixtures")
        if fixtures_identity is not None:
            fixtures_fd = _open_directory_at(
                stage_fd, "fixtures", label="invocation-owned staged fixtures"
            )
            if _entry_identity(os.fstat(fixtures_fd)) != fixtures_identity:
                raise _InvocationIdentityDrift(
                    "partial staged fixture directory invocation identity drifted"
                )
            expected_fixture_names = (
                {"recorded"}
                if "fixtures/recorded" in trust.directory_identities
                else set()
            )
            if (
                _directory_names_at(
                    fixtures_fd, label="invocation-owned staged fixtures"
                )
                != expected_fixture_names
            ):
                raise _InvocationIdentityDrift(
                    "partial staged fixture directory invocation inventory drifted"
                )
            recorded_identity = trust.directory_identities.get("fixtures/recorded")
            if recorded_identity is not None:
                recorded_fd = _open_directory_at(
                    fixtures_fd,
                    "recorded",
                    label="invocation-owned staged recorded fixtures",
                )
                if _entry_identity(os.fstat(recorded_fd)) != recorded_identity:
                    raise _InvocationIdentityDrift(
                        "partial recorded fixture directory invocation identity drifted"
                    )
                recorded_signatures = {
                    path.removeprefix("fixtures/recorded/"): signature
                    for path, signature in trust.file_signatures.items()
                    if path.startswith("fixtures/recorded/")
                }
                if _directory_names_at(
                    recorded_fd, label="invocation-owned staged recorded fixtures"
                ) != set(recorded_signatures):
                    raise _InvocationIdentityDrift(
                        "partial recorded fixture invocation inventory drifted"
                    )
                for fixture_name, expected_signature in recorded_signatures.items():
                    content, signature = _read_regular_stat_capture_at(
                        recorded_fd,
                        fixture_name,
                        label=f"invocation-owned staged fixture {fixture_name}",
                    )
                    if (
                        signature != expected_signature
                        or content != expected[f"fixtures/recorded/{fixture_name}"]
                    ):
                        raise _InvocationIdentityDrift(
                            "partial staged fixture invocation identity drifted"
                        )
                _assert_directory_entry_identity_at(
                    fixtures_fd,
                    "recorded",
                    recorded_fd,
                    label="invocation-owned staged recorded fixtures",
                )
            _assert_directory_entry_identity_at(
                stage_fd,
                "fixtures",
                fixtures_fd,
                label="invocation-owned staged fixtures",
            )
        _assert_directory_entry_identity_at(
            story_fd,
            STAGE_NAME,
            stage_fd,
            label="invocation-owned publication stage",
        )
        if complete and (
            set(trust.directory_identities) != {".", "fixtures", "fixtures/recorded"}
            or set(trust.file_signatures)
            != {
                "manifest.json",
                *(f"fixtures/recorded/{name}" for name in EXPECTED_FIXTURE_NAMES),
            }
        ):
            raise _InvocationIdentityDrift(
                "complete publication stage invocation inventory is incomplete"
            )
    finally:
        for descriptor in (recorded_fd, fixtures_fd, stage_fd):
            if descriptor is not None:
                os.close(descriptor)


def _create_stage_at(
    story_fd: int,
    files: Mapping[str, bytes],
    trust: _ActiveStageTrust,
) -> None:
    if _entry_metadata_at(story_fd, STAGE_NAME) is not None:
        raise PublicationRecoveryRequired("stale ST-1204 stage requires recovery")
    os.mkdir(STAGE_NAME, 0o700, dir_fd=story_fd)
    os.fsync(story_fd)
    stage_fd = _open_directory_at(story_fd, STAGE_NAME, label="publication stage")
    trust.directory_identities["."] = _entry_identity(os.fstat(stage_fd))
    _checkpoint("after-stage-directory")
    fixtures_fd: int | None = None
    recorded_fd: int | None = None
    try:
        os.mkdir("fixtures", 0o755, dir_fd=stage_fd)
        os.fsync(stage_fd)
        fixtures_fd = _open_directory_at(stage_fd, "fixtures", label="staged fixtures")
        trust.directory_identities["fixtures"] = _entry_identity(os.fstat(fixtures_fd))
        os.mkdir("recorded", 0o755, dir_fd=fixtures_fd)
        os.fsync(fixtures_fd)
        recorded_fd = _open_directory_at(
            fixtures_fd, "recorded", label="staged recorded fixtures"
        )
        trust.directory_identities["fixtures/recorded"] = _entry_identity(
            os.fstat(recorded_fd)
        )
        _create_regular_at(
            stage_fd,
            "manifest.json",
            files["manifest.json"],
            label="staged manifest",
        )
        _manifest_content, manifest_signature = _read_regular_stat_capture_at(
            stage_fd, "manifest.json", label="staged manifest"
        )
        trust.file_signatures["manifest.json"] = manifest_signature
        _checkpoint("after-staged-manifest")
        for fixture_name in EXPECTED_FIXTURE_NAMES:
            _create_regular_at(
                recorded_fd,
                fixture_name,
                files[f"fixtures/recorded/{fixture_name}"],
                label=f"staged fixture {fixture_name}",
            )
            _fixture_content, fixture_signature = _read_regular_stat_capture_at(
                recorded_fd,
                fixture_name,
                label=f"staged fixture {fixture_name}",
            )
            trust.file_signatures[f"fixtures/recorded/{fixture_name}"] = (
                fixture_signature
            )
            _checkpoint(f"after-staged-{fixture_name}")
        os.fsync(recorded_fd)
        os.fsync(fixtures_fd)
        os.fsync(stage_fd)
        _assert_directory_entry_identity_at(
            fixtures_fd,
            "recorded",
            recorded_fd,
            label="staged recorded fixtures",
        )
        _assert_directory_entry_identity_at(
            stage_fd, "fixtures", fixtures_fd, label="staged fixtures"
        )
        _assert_directory_entry_identity_at(
            story_fd, STAGE_NAME, stage_fd, label="publication stage"
        )
    finally:
        for descriptor in (recorded_fd, fixtures_fd, stage_fd):
            if descriptor is not None:
                os.close(descriptor)
    _checkpoint("after-stage-fsync")
    _assert_stage_trust_at(story_fd, files, trust, complete=True)
    observed = _read_bundle_at(story_fd, STAGE_NAME, allow_missing=False)
    if observed != files:
        raise RuntimeError("staged ST-1204 bundle failed exact verification")
    _assert_stage_trust_at(story_fd, files, trust, complete=True)
    _checkpoint("after-stage-verify")
    _assert_stage_trust_at(story_fd, files, trust, complete=True)


def _cleanup_entry_state(parent_fd: int, name: str) -> str:
    source = _entry_metadata_at(parent_fd, name)
    tombstone = _entry_metadata_at(parent_fd, _delete_tombstone_name(name))
    if source is not None and tombstone is not None:
        return "conflict"
    if source is not None:
        return "source"
    if tombstone is not None:
        return "quarantined"
    return "missing"


def _validate_monotonic_file_cleanup(parent_fd: int, names: Sequence[str]) -> None:
    states = [_cleanup_entry_state(parent_fd, name) for name in names]
    if "conflict" in states or states.count("quarantined") > 1:
        raise PublicationRecoveryRequired("bundle file cleanup state is ambiguous")
    seen_remaining = False
    for state in states:
        if state == "missing":
            if seen_remaining:
                raise PublicationRecoveryRequired(
                    "bundle file cleanup progress is not monotonic"
                )
        else:
            seen_remaining = True
    if "quarantined" in states:
        first_remaining = next(
            index for index, state in enumerate(states) if state != "missing"
        )
        if states[first_remaining] != "quarantined":
            raise PublicationRecoveryRequired(
                "bundle file quarantine is outside cleanup order"
            )


def _remove_owned_bundle_tree_at(
    story_fd: int,
    name: str,
    *,
    expected_sha256: Mapping[str, str],
    expected_identities: Mapping[str, tuple[int, int]],
    checkpoint_prefix: str,
) -> None:
    if set(expected_sha256) != set(EXPECTED_BUNDLE_PATHS) or set(
        expected_identities
    ) != {
        ".",
        "manifest.json",
        "fixtures",
        "fixtures/recorded",
        *EXPECTED_BUNDLE_PATHS[1:],
    }:
        raise PublicationRecoveryRequired("owned bundle cleanup record is incomplete")
    root_delete_name = _delete_tombstone_name(name)
    root_metadata = _entry_metadata_at(story_fd, name)
    root_delete_metadata = _entry_metadata_at(story_fd, root_delete_name)
    if root_metadata is None and root_delete_metadata is None:
        return
    if root_metadata is None:
        _rmdir_empty_at(
            story_fd,
            name,
            label="owned bundle cleanup root",
            expected_identity=expected_identities["."],
            checkpoint=f"{checkpoint_prefix}-root",
        )
        return
    if root_delete_metadata is not None:
        raise PublicationRecoveryRequired("owned bundle cleanup root conflicts")
    root_fd = _open_directory_at(story_fd, name, label="owned bundle cleanup root")
    fixtures_fd: int | None = None
    recorded_fd: int | None = None
    try:
        if _entry_identity(os.fstat(root_fd)) != expected_identities["."]:
            raise PublicationRecoveryRequired("owned bundle cleanup identity drifted")
        manifest_delete = _delete_tombstone_name("manifest.json")
        fixtures_delete = _delete_tombstone_name("fixtures")
        root_names = _directory_names_at(root_fd, label="owned bundle cleanup root")
        if not root_names <= {
            "manifest.json",
            manifest_delete,
            "fixtures",
            fixtures_delete,
        }:
            raise PublicationRecoveryRequired(
                "owned bundle cleanup has unknown entries"
            )
        manifest_state = _cleanup_entry_state(root_fd, "manifest.json")
        fixtures_state = _cleanup_entry_state(root_fd, "fixtures")
        if manifest_state == "conflict" or fixtures_state == "conflict":
            raise PublicationRecoveryRequired("owned bundle cleanup entries conflict")
        if manifest_state != "source" and fixtures_state != "missing":
            raise PublicationRecoveryRequired("owned bundle cleanup order drifted")
        if fixtures_state == "source":
            fixtures_fd = _open_directory_at(
                root_fd, "fixtures", label="owned bundle fixtures"
            )
            if (
                _entry_identity(os.fstat(fixtures_fd))
                != expected_identities["fixtures"]
            ):
                raise PublicationRecoveryRequired(
                    "owned bundle fixture directory identity drifted"
                )
            recorded_delete = _delete_tombstone_name("recorded")
            fixture_names = _directory_names_at(
                fixtures_fd, label="owned bundle fixtures"
            )
            if not fixture_names <= {"recorded", recorded_delete}:
                raise PublicationRecoveryRequired(
                    "owned bundle fixture cleanup has unknown entries"
                )
            recorded_state = _cleanup_entry_state(fixtures_fd, "recorded")
            if recorded_state == "conflict":
                raise PublicationRecoveryRequired(
                    "owned bundle recorded cleanup conflicts"
                )
            if recorded_state == "source":
                recorded_fd = _open_directory_at(
                    fixtures_fd,
                    "recorded",
                    label="owned bundle recorded fixtures",
                )
                if (
                    _entry_identity(os.fstat(recorded_fd))
                    != expected_identities["fixtures/recorded"]
                ):
                    raise PublicationRecoveryRequired(
                        "owned bundle recorded directory identity drifted"
                    )
                allowed_names = {
                    *EXPECTED_FIXTURE_NAMES,
                    *(
                        _delete_tombstone_name(fixture_name)
                        for fixture_name in EXPECTED_FIXTURE_NAMES
                    ),
                }
                names = _directory_names_at(
                    recorded_fd, label="owned bundle recorded fixtures"
                )
                if not names <= allowed_names:
                    raise PublicationRecoveryRequired(
                        "owned bundle recorded cleanup has unknown entries"
                    )
                _validate_monotonic_file_cleanup(recorded_fd, EXPECTED_FIXTURE_NAMES)
                for fixture_name in EXPECTED_FIXTURE_NAMES:
                    _unlink_regular_at(
                        recorded_fd,
                        fixture_name,
                        label=f"owned bundle fixture {fixture_name}",
                        expected_sha256=expected_sha256[
                            f"fixtures/recorded/{fixture_name}"
                        ],
                        expected_identity=expected_identities[
                            f"fixtures/recorded/{fixture_name}"
                        ],
                        checkpoint=f"{checkpoint_prefix}-{fixture_name}",
                    )
                recorded_identity = expected_identities["fixtures/recorded"]
                if _entry_identity(os.fstat(recorded_fd)) != recorded_identity:
                    raise PublicationRecoveryRequired(
                        "owned bundle recorded directory identity drifted"
                    )
                os.close(recorded_fd)
                recorded_fd = None
                _rmdir_empty_at(
                    fixtures_fd,
                    "recorded",
                    label="owned bundle recorded directory",
                    expected_identity=recorded_identity,
                    checkpoint=f"{checkpoint_prefix}-recorded",
                )
            elif recorded_state == "quarantined":
                _rmdir_empty_at(
                    fixtures_fd,
                    "recorded",
                    label="owned bundle recorded directory",
                    expected_identity=expected_identities["fixtures/recorded"],
                    checkpoint=f"{checkpoint_prefix}-recorded",
                )
            fixtures_identity = expected_identities["fixtures"]
            if _entry_identity(os.fstat(fixtures_fd)) != fixtures_identity:
                raise PublicationRecoveryRequired(
                    "owned bundle fixture directory identity drifted"
                )
            os.close(fixtures_fd)
            fixtures_fd = None
            _rmdir_empty_at(
                root_fd,
                "fixtures",
                label="owned bundle fixture directory",
                expected_identity=fixtures_identity,
                checkpoint=f"{checkpoint_prefix}-fixtures",
            )
        elif fixtures_state == "quarantined":
            _rmdir_empty_at(
                root_fd,
                "fixtures",
                label="owned bundle fixture directory",
                expected_identity=expected_identities["fixtures"],
                checkpoint=f"{checkpoint_prefix}-fixtures",
            )
        _unlink_regular_at(
            root_fd,
            "manifest.json",
            label="owned bundle manifest",
            expected_sha256=expected_sha256["manifest.json"],
            expected_identity=expected_identities["manifest.json"],
            checkpoint=f"{checkpoint_prefix}-manifest",
        )
        _assert_directory_entry_identity_at(
            story_fd, name, root_fd, label="owned bundle cleanup root"
        )
    finally:
        for descriptor in (recorded_fd, fixtures_fd, root_fd):
            if descriptor is not None:
                os.close(descriptor)
    _rmdir_empty_at(
        story_fd,
        name,
        label="owned bundle cleanup root",
        expected_identity=expected_identities["."],
        checkpoint=f"{checkpoint_prefix}-root",
    )


def _journal_bytes(state: Mapping[str, object]) -> bytes:
    return _sorted_json(dict(state), compact=False)


def _validated_sha256(value: object, *, label: str, optional: bool) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise PublicationRecoveryRequired(f"{label} is malformed")
    return value


def _validated_cleanup_record(
    value: object,
    *,
    label: str,
    transaction_id: str,
    kind: str,
) -> dict[str, object] | None:
    if value is None:
        return None
    record = _mapping(value, label=label)
    expected_fields = {
        "bundle": {
            "role",
            "source_name",
            "quarantine_name",
            "tree_identity",
            "file_sha256",
        },
        "legacy_manifest": {
            "source_name",
            "quarantine_name",
            "identity",
            "sha256",
        },
        "legacy_fixtures": {
            "source_name",
            "quarantine_name",
            "tree_identity",
            "file_sha256",
        },
    }[kind]
    if set(record) != expected_fields:
        raise PublicationRecoveryRequired(f"{label} fields drifted")
    identity_names: set[str] | None = None
    sha_names: set[str] | None = None
    if kind == "bundle":
        if record.get("role") not in {"PREVIOUS", "NEXT"}:
            raise PublicationRecoveryRequired(f"{label} role is malformed")
        if record.get("source_name") != STAGE_NAME:
            raise PublicationRecoveryRequired(f"{label} source is malformed")
        expected_name = f"{BUNDLE_CLEANUP_PREFIX}{transaction_id}"
        identity_names = {
            ".",
            "manifest.json",
            "fixtures",
            "fixtures/recorded",
            *EXPECTED_BUNDLE_PATHS[1:],
        }
        sha_names = set(EXPECTED_BUNDLE_PATHS)
    elif kind == "legacy_manifest":
        if record.get("source_name") != LEGACY_MANIFEST_PATH.name:
            raise PublicationRecoveryRequired(f"{label} source is malformed")
        expected_name = f"{LEGACY_CLEANUP_PREFIX}{transaction_id}.manifest"
        _validated_identity(record.get("identity"), label=f"{label} identity")
        _validated_sha256(record.get("sha256"), label=f"{label} sha256", optional=False)
    else:
        if record.get("source_name") != "fixtures":
            raise PublicationRecoveryRequired(f"{label} source is malformed")
        expected_name = f"{LEGACY_CLEANUP_PREFIX}{transaction_id}.fixtures"
        identity_names = {".", "recorded", *EXPECTED_FIXTURE_NAMES}
        sha_names = set(EXPECTED_FIXTURE_NAMES)
    if kind != "legacy_manifest":
        if identity_names is None or sha_names is None:
            raise PublicationRecoveryRequired(f"{label} cleanup kind is malformed")
        _validated_identity_map(
            record.get("tree_identity"),
            label=f"{label} tree identity",
            expected_names=identity_names,
        )
        file_sha256 = _mapping(record.get("file_sha256"), label=f"{label} file sha256")
        if set(file_sha256) != sha_names:
            raise PublicationRecoveryRequired(f"{label} file inventory drifted")
        for name, digest in file_sha256.items():
            _validated_sha256(
                digest, label=f"{label} file {name} sha256", optional=False
            )
    if record.get("quarantine_name") != expected_name:
        raise PublicationRecoveryRequired(f"{label} quarantine name is malformed")
    return record


def _validate_journal_state(value: object) -> dict[str, object]:
    state = _mapping(value, label="publication journal state")
    if set(state) != {
        "schema",
        "sequence",
        "previous_state_sha256",
        "transaction_id",
        "mode",
        "publication_phase",
        "cleanup_phase",
        "had_previous",
        "previous_manifest_sha256",
        "next_manifest_sha256",
        "previous_root_identity",
        "next_root_identity",
        "cleanup_bundle",
        "legacy_manifest",
        "legacy_fixtures",
    }:
        raise PublicationRecoveryRequired("publication journal fields drifted")
    sequence = state.get("sequence")
    previous_state_sha256 = _validated_sha256(
        state.get("previous_state_sha256"),
        label="previous journal state sha256",
        optional=True,
    )
    transaction_id = state.get("transaction_id")
    if (
        type(sequence) is not int
        or sequence < 0
        or sequence >= MAX_JOURNAL_STATES
        or (sequence == 0) != (previous_state_sha256 is None)
        or not isinstance(transaction_id, str)
        or not re.fullmatch(r"[0-9a-f]{32}", transaction_id)
        or UUID(hex=transaction_id).hex != transaction_id
    ):
        raise PublicationRecoveryRequired("publication journal sequence is malformed")
    previous = _validated_sha256(
        state.get("previous_manifest_sha256"),
        label="previous manifest sha256",
        optional=True,
    )
    next_digest = _validated_sha256(
        state.get("next_manifest_sha256"),
        label="next manifest sha256",
        optional=False,
    )
    previous_identity = _validated_identity(
        state.get("previous_root_identity"), label="previous root identity"
    )
    next_identity = _validated_identity(
        state.get("next_root_identity"), label="next root identity"
    )
    mode = state.get("mode")
    if (
        state.get("schema") != JOURNAL_SCHEMA
        or mode not in {"FRESH", "REPLACE", "NOOP_LEGACY"}
        or state.get("publication_phase") not in JOURNAL_PHASES
        or state.get("cleanup_phase") not in CLEANUP_PHASES
        or type(state.get("had_previous")) is not bool
        or (state.get("had_previous") is True) != (previous is not None)
        or next_identity is None
        or (mode == "FRESH" and (previous is not None or previous_identity is not None))
        or (mode in {"REPLACE", "NOOP_LEGACY"} and previous_identity is None)
        or (mode == "NOOP_LEGACY" and previous != next_digest)
    ):
        raise PublicationRecoveryRequired("publication journal state is malformed")
    bundle_record = _validated_cleanup_record(
        state.get("cleanup_bundle"),
        label="bundle cleanup",
        transaction_id=transaction_id,
        kind="bundle",
    )
    legacy_manifest_record = _validated_cleanup_record(
        state.get("legacy_manifest"),
        label="legacy manifest cleanup",
        transaction_id=transaction_id,
        kind="legacy_manifest",
    )
    legacy_fixtures_record = _validated_cleanup_record(
        state.get("legacy_fixtures"),
        label="legacy fixture cleanup",
        transaction_id=transaction_id,
        kind="legacy_fixtures",
    )
    publication_phase = state["publication_phase"]
    cleanup_phase = state["cleanup_phase"]
    if (
        (publication_phase == "PREPARED" and cleanup_phase != "NONE")
        or (publication_phase == "PREPARED" and bundle_record is not None)
        or (mode == "NOOP_LEGACY" and publication_phase != "COMMITTED")
        or (
            cleanup_phase
            in {"BUNDLE_QUARANTINING", "BUNDLE_DELETING", "BUNDLE_REMOVED"}
            and bundle_record is None
        )
        or (
            cleanup_phase in {"NONE", "BUNDLE_QUARANTINING", "BUNDLE_DELETING"}
            and (
                legacy_manifest_record is not None or legacy_fixtures_record is not None
            )
        )
        or (
            cleanup_phase in {"LEGACY_QUARANTINING", "LEGACY_DELETING"}
            and (
                publication_phase != "COMMITTED"
                or legacy_manifest_record is None
                or legacy_fixtures_record is None
            )
        )
    ):
        raise PublicationRecoveryRequired(
            "publication journal cleanup state is malformed"
        )
    return state


def _new_journal_state(
    *,
    mode: str,
    previous_digest: str | None,
    next_digest: str,
    previous_identity: tuple[int, int] | None,
    next_identity: tuple[int, int],
    publication_phase: str = "PREPARED",
) -> dict[str, object]:
    return _validate_journal_state(
        {
            "schema": JOURNAL_SCHEMA,
            "sequence": 0,
            "previous_state_sha256": None,
            "transaction_id": uuid4().hex,
            "mode": mode,
            "publication_phase": publication_phase,
            "cleanup_phase": "NONE",
            "had_previous": previous_digest is not None,
            "previous_manifest_sha256": previous_digest,
            "next_manifest_sha256": next_digest,
            "previous_root_identity": _identity_record(previous_identity),
            "next_root_identity": _identity_record(next_identity),
            "cleanup_bundle": None,
            "legacy_manifest": None,
            "legacy_fixtures": None,
        }
    )


def _journal_cleanup_entry_name(transaction_id: str, identity: tuple[int, int]) -> str:
    return f"{JOURNAL_CLEANUP_NAME}{transaction_id}.{identity[0]}.{identity[1]}"


def _parse_journal_cleanup_entry_name(name: str) -> tuple[str, str, tuple[int, int]]:
    logical_name = name
    if logical_name.startswith(DELETE_TOMBSTONE_PREFIX):
        logical_name = logical_name.removeprefix(DELETE_TOMBSTONE_PREFIX)
    match = re.fullmatch(
        rf"{re.escape(JOURNAL_CLEANUP_NAME)}([0-9a-f]{{32}})\.([0-9]+)\.([1-9][0-9]*)",
        logical_name,
    )
    if match is None:
        raise PublicationRecoveryRequired("publication cleanup name is malformed")
    transaction_id = match.group(1)
    if UUID(hex=transaction_id).hex != transaction_id:
        raise PublicationRecoveryRequired(
            "publication cleanup transaction is malformed"
        )
    return logical_name, transaction_id, (int(match.group(2)), int(match.group(3)))


def _remove_owned_journal_tree_at(
    story_fd: int,
    name: str,
    *,
    transaction_id: str,
    expected_identity: tuple[int, int],
    expected_state_signatures: Mapping[str, StatSignature],
) -> None:
    metadata = _entry_metadata_at(story_fd, name)
    root_tombstone = _entry_metadata_at(story_fd, _delete_tombstone_name(name))
    if metadata is None and root_tombstone is None:
        return
    if metadata is None:
        raise PublicationRecoveryRequired(
            "terminal publication cleanup has no durable state identity inventory"
        )
    if root_tombstone is not None:
        raise PublicationRecoveryRequired("publication cleanup journal conflicts")
    journal_fd = _open_directory_at(story_fd, name, label="publication cleanup journal")
    try:
        if _entry_identity(os.fstat(journal_fd)) != expected_identity:
            raise PublicationRecoveryRequired(
                "publication cleanup journal identity drifted"
            )
        current, contents, observed_signatures = _load_journal_from_fd(journal_fd)
        if (
            current["transaction_id"] != transaction_id
            or current["cleanup_phase"] != "CLEANUP_COMPLETE"
            or observed_signatures != dict(expected_state_signatures)
        ):
            raise PublicationRecoveryRequired(
                "publication cleanup journal state identity inventory drifted"
            )
        for sequence, content in enumerate(contents):
            logical_name = _journal_state_name(sequence)
            expected_signature = expected_state_signatures[logical_name]
            _unlink_regular_at(
                journal_fd,
                logical_name,
                label="publication cleanup journal state",
                expected_content=content,
                expected_identity=(expected_signature[0], expected_signature[1]),
                expected_signature=expected_signature,
                checkpoint=f"journal-cleanup-state-{sequence:03d}",
            )
        _assert_directory_entry_identity_at(
            story_fd, name, journal_fd, label="publication cleanup journal"
        )
    finally:
        os.close(journal_fd)
    _rmdir_empty_at(
        story_fd,
        name,
        label="publication cleanup journal",
        expected_identity=expected_identity,
        checkpoint="journal-cleanup-root",
    )


def _create_journal_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust | None = None,
) -> _ActiveJournalTrust:
    if trust is None:
        trust = _ActiveJournalTrust()
    elif trust.root_signature is not None or trust.state_signatures:
        raise _InvocationIdentityDrift(
            "new publication journal trust is already activated"
        )
    pending_names = {
        name
        for name in _directory_names_at(story_fd, label="ST-1204 Story directory")
        if name in {JOURNAL_PREPARING_NAME, JOURNAL_NAME}
        or name.startswith(JOURNAL_CLEANUP_NAME)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{JOURNAL_CLEANUP_NAME}")
    }
    if pending_names:
        raise PublicationRecoveryRequired("pending publication journal exists")
    os.mkdir(JOURNAL_PREPARING_NAME, 0o700, dir_fd=story_fd)
    os.fsync(story_fd)
    preparing_fd = _open_directory_at(
        story_fd, JOURNAL_PREPARING_NAME, label="preparing publication journal"
    )
    preparing_identity: tuple[int, int]
    initial_state_signature: StatSignature
    try:
        initial_state_signature, _preparing_root_signature = (
            _create_committed_journal_state_at(preparing_fd, state)
        )
        os.fsync(preparing_fd)
        _assert_directory_entry_identity_at(
            story_fd,
            JOURNAL_PREPARING_NAME,
            preparing_fd,
            label="preparing publication journal",
        )
        preparing_identity = _entry_identity(os.fstat(preparing_fd))
    finally:
        os.close(preparing_fd)
    _rename_noreplace_at(story_fd, JOURNAL_PREPARING_NAME, JOURNAL_NAME)
    os.fsync(story_fd)
    current = _entry_metadata_at(story_fd, JOURNAL_NAME)
    if current is None or _entry_identity(current) != preparing_identity:
        raise _InvocationIdentityDrift("published journal identity drifted")
    journal_fd = _open_directory_at(
        story_fd, JOURNAL_NAME, label="published publication journal"
    )
    try:
        loaded, _contents, observed_signatures = _load_journal_from_fd(journal_fd)
        if loaded != dict(state) or observed_signatures != {
            JOURNAL_STATE_NAME: initial_state_signature
        }:
            raise _InvocationIdentityDrift("published journal state identity drifted")
        root_signature = _stat_signature(os.fstat(journal_fd))
        _assert_directory_signature_at(
            story_fd,
            JOURNAL_NAME,
            journal_fd,
            expected_signature=root_signature,
            label="published publication journal",
        )
    finally:
        os.close(journal_fd)
    trust.root_signature = root_signature
    trust.state_signatures.update(observed_signatures)
    _checkpoint("after-journal-publish")
    _assert_active_journal_trust_at(story_fd, trust)
    return trust


def _journal_state_name(sequence: int) -> str:
    if sequence < 0 or sequence >= MAX_JOURNAL_STATES:
        raise PublicationRecoveryRequired("publication journal sequence is unsafe")
    return f"{JOURNAL_STATE_PREFIX}{sequence:03d}.json"


def _journal_state_preparing_name(sequence: int) -> str:
    return f"{_journal_state_name(sequence)}{JOURNAL_STATE_PREPARING_SUFFIX}"


def _create_committed_journal_state_at(
    journal_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust | None = None,
) -> tuple[StatSignature, StatSignature]:
    sequence = cast(int, state["sequence"])
    final_name = _journal_state_name(sequence)
    preparing_name = _journal_state_preparing_name(sequence)
    if (
        _entry_metadata_at(journal_fd, final_name) is not None
        or _entry_metadata_at(journal_fd, preparing_name) is not None
    ):
        raise PublicationRecoveryRequired("publication journal state already exists")
    _create_regular_at(
        journal_fd,
        preparing_name,
        _journal_bytes(state),
        label="preparing publication journal state",
    )
    expected_content = _journal_bytes(state)
    preparing_content, preparing_signature = _read_regular_stat_capture_at(
        journal_fd,
        preparing_name,
        label="preparing publication journal state",
        maximum_bytes=16 * 1024,
    )
    if preparing_content != expected_content:
        raise PublicationRecoveryRequired(
            "preparing publication journal state bytes drifted"
        )
    os.fsync(journal_fd)
    _checkpoint(f"after-journal-state-{sequence:03d}-prepare")
    preparing_current = _entry_metadata_at(journal_fd, preparing_name)
    if (
        preparing_current is None
        or _stat_signature(preparing_current) != preparing_signature
    ):
        raise _InvocationIdentityDrift(
            "preparing publication journal state identity drifted"
        )
    _rename_noreplace_at(journal_fd, preparing_name, final_name)
    os.fsync(journal_fd)
    final_content, final_signature = _read_regular_stat_capture_at(
        journal_fd,
        final_name,
        label="committed publication journal state",
        maximum_bytes=16 * 1024,
    )
    if final_content != expected_content or (
        final_signature[0],
        final_signature[1],
    ) != (preparing_signature[0], preparing_signature[1]):
        raise _InvocationIdentityDrift(
            "committed publication journal state identity drifted"
        )
    root_signature = _stat_signature(os.fstat(journal_fd))
    if trust is not None:
        trust.state_signatures[final_name] = final_signature
        trust.root_signature = root_signature
    _checkpoint(f"after-journal-state-{sequence:03d}-commit")
    return final_signature, root_signature


def _load_journal_from_fd(
    journal_fd: int, *, ignore_preparing: bool = False
) -> tuple[dict[str, object], list[bytes], dict[str, StatSignature]]:
    names = _directory_names_at(journal_fd, label="publication journal")
    if ignore_preparing:
        names = {
            name for name in names if not name.endswith(JOURNAL_STATE_PREPARING_SUFFIX)
        }
    parsed: list[tuple[int, str]] = []
    for name in names:
        match = re.fullmatch(r"state\.([0-9]{3})\.json", name)
        if match is None:
            raise PublicationRecoveryRequired("publication journal has unknown entries")
        parsed.append((int(match.group(1)), name))
    parsed.sort()
    if not parsed or [sequence for sequence, _name in parsed] != list(
        range(len(parsed))
    ):
        raise PublicationRecoveryRequired("publication journal sequence is incomplete")
    contents: list[bytes] = []
    states: list[dict[str, object]] = []
    signatures: dict[str, StatSignature] = {}
    for sequence, name in parsed:
        content, signature = _read_regular_stat_capture_at(
            journal_fd,
            name,
            label="publication journal state",
            maximum_bytes=16 * 1024,
        )
        state = _validate_journal_state(
            _load_json(content, label="publication journal state")
        )
        expected_previous = None if sequence == 0 else _sha256(contents[-1])
        if (
            state["sequence"] != sequence
            or state["previous_state_sha256"] != expected_previous
        ):
            raise PublicationRecoveryRequired("publication journal hash chain drifted")
        contents.append(content)
        states.append(state)
        signatures[name] = signature
    return states[-1], contents, signatures


def _capture_active_journal_trust_from_fd_at(
    story_fd: int,
    journal_fd: int,
    *,
    ignore_preparing: bool = False,
) -> tuple[dict[str, object], list[bytes], _ActiveJournalTrust]:
    current, contents, signatures = _load_journal_from_fd(
        journal_fd, ignore_preparing=ignore_preparing
    )
    root_signature = _stat_signature(os.fstat(journal_fd))
    _assert_directory_signature_at(
        story_fd,
        JOURNAL_NAME,
        journal_fd,
        expected_signature=root_signature,
        label="active publication journal",
    )
    return (
        current,
        contents,
        _ActiveJournalTrust(
            root_signature=root_signature,
            state_signatures=signatures,
        ),
    )


def _assert_active_journal_trust_from_fd_at(
    story_fd: int,
    journal_fd: int,
    trust: _ActiveJournalTrust,
    *,
    ignore_preparing: bool = False,
) -> tuple[dict[str, object], list[bytes], dict[str, StatSignature]]:
    if trust.root_signature is None:
        raise _InvocationIdentityDrift(
            "active publication journal has no invocation root signature"
        )
    _assert_directory_signature_at(
        story_fd,
        JOURNAL_NAME,
        journal_fd,
        expected_signature=trust.root_signature,
        label="active publication journal",
    )
    current, contents, signatures = _load_journal_from_fd(
        journal_fd, ignore_preparing=ignore_preparing
    )
    if signatures != trust.state_signatures:
        raise _InvocationIdentityDrift(
            "active publication journal state identity inventory drifted"
        )
    _assert_directory_signature_at(
        story_fd,
        JOURNAL_NAME,
        journal_fd,
        expected_signature=trust.root_signature,
        label="active publication journal",
    )
    return current, contents, signatures


def _assert_active_journal_trust_at(
    story_fd: int, trust: _ActiveJournalTrust
) -> tuple[dict[str, object], list[bytes], dict[str, StatSignature]]:
    journal_fd = _open_directory_at(
        story_fd, JOURNAL_NAME, label="active publication journal"
    )
    try:
        return _assert_active_journal_trust_from_fd_at(story_fd, journal_fd, trust)
    finally:
        os.close(journal_fd)


def _recover_preparing_journal_state_at(
    story_fd: int,
    journal_fd: int,
    trust: _ActiveJournalTrust,
) -> None:
    names = _directory_names_at(journal_fd, label="publication journal")
    preparing_names = sorted(
        name for name in names if name.endswith(JOURNAL_STATE_PREPARING_SUFFIX)
    )
    if not preparing_names:
        return
    if len(preparing_names) != 1:
        raise PublicationRecoveryRequired(
            "publication journal has conflicting preparing states"
        )
    preparing_name = preparing_names[0]
    match = re.fullmatch(r"state\.([0-9]{3})\.json\.preparing", preparing_name)
    if match is None:
        raise PublicationRecoveryRequired(
            "publication journal preparing state is malformed"
        )
    sequence = int(match.group(1))
    current, contents, _signatures = _assert_active_journal_trust_from_fd_at(
        story_fd, journal_fd, trust, ignore_preparing=True
    )
    if sequence != cast(int, current["sequence"]) + 1:
        raise PublicationRecoveryRequired(
            "publication journal preparing sequence drifted"
        )
    content, preparing_signature = _read_regular_stat_capture_at(
        journal_fd,
        preparing_name,
        label="preparing publication journal state",
        maximum_bytes=16 * 1024,
    )
    try:
        raw_candidate = _load_json(content, label="preparing publication journal state")
    except RuntimeError:
        _unlink_regular_at(
            journal_fd,
            preparing_name,
            label="partial preparing publication journal state",
            expected_content=content,
            expected_identity=(preparing_signature[0], preparing_signature[1]),
            expected_signature=preparing_signature,
        )
        os.fsync(journal_fd)
        trust.root_signature = _stat_signature(os.fstat(journal_fd))
        _assert_active_journal_trust_from_fd_at(story_fd, journal_fd, trust)
        return
    candidate = _validate_journal_state(raw_candidate)
    if candidate["sequence"] != sequence or candidate[
        "previous_state_sha256"
    ] != _sha256(contents[-1]):
        raise PublicationRecoveryRequired(
            "publication journal preparing state ownership drifted"
        )
    _rename_noreplace_at(
        journal_fd,
        preparing_name,
        _journal_state_name(sequence),
    )
    os.fsync(journal_fd)
    final_name = _journal_state_name(sequence)
    final_content, final_signature = _read_regular_stat_capture_at(
        journal_fd,
        final_name,
        label="recovered publication journal state",
        maximum_bytes=16 * 1024,
    )
    if final_content != content or (final_signature[0], final_signature[1]) != (
        preparing_signature[0],
        preparing_signature[1],
    ):
        raise _InvocationIdentityDrift(
            "recovered publication journal state identity drifted"
        )
    trust.state_signatures[final_name] = final_signature
    trust.root_signature = _stat_signature(os.fstat(journal_fd))
    _assert_active_journal_trust_from_fd_at(story_fd, journal_fd, trust)


def _load_journal_at(story_fd: int) -> dict[str, object]:
    journal_fd = _open_directory_at(story_fd, JOURNAL_NAME, label="publication journal")
    try:
        state, _contents, _signatures = _load_journal_from_fd(journal_fd)
        _assert_directory_entry_identity_at(
            story_fd, JOURNAL_NAME, journal_fd, label="publication journal"
        )
        return state
    finally:
        os.close(journal_fd)


def _write_journal_update_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
    **updates: object,
) -> dict[str, object]:
    sequence = cast(int, state["sequence"]) + 1
    updated = _validate_journal_state(
        {
            **state,
            **updates,
            "sequence": sequence,
            "previous_state_sha256": _sha256(_journal_bytes(state)),
        }
    )
    journal_fd = _open_directory_at(story_fd, JOURNAL_NAME, label="publication journal")
    try:
        current, _contents, _signatures = _assert_active_journal_trust_from_fd_at(
            story_fd, journal_fd, trust
        )
        if current != dict(state):
            raise PublicationRecoveryRequired(
                "publication journal update is based on stale state"
            )
        state_signature, root_signature = _create_committed_journal_state_at(
            journal_fd, updated, trust
        )
        trust.state_signatures[_journal_state_name(sequence)] = state_signature
        trust.root_signature = root_signature
        _assert_active_journal_trust_from_fd_at(story_fd, journal_fd, trust)
    finally:
        os.close(journal_fd)
    return updated


def _write_journal_phase_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
    phase: str,
) -> dict[str, object]:
    return _write_journal_update_at(story_fd, state, trust, publication_phase=phase)


def _renameat2_at(
    parent_fd: int,
    source: str,
    destination: str,
    *,
    flags: int,
    label: str,
) -> None:
    _checked_entry_name(source, label=label)
    _checked_entry_name(destination, label=label)
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise RuntimeError(f"{label} requires renameat2") from exc
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        parent_fd,
        os.fsencode(source),
        parent_fd,
        os.fsencode(destination),
        flags,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise RuntimeError(f"{label} failed: {os.strerror(error)} (errno={error})")


def _rename_exchange_at(parent_fd: int, left: str, right: str) -> None:
    _renameat2_at(
        parent_fd,
        left,
        right,
        flags=RENAME_EXCHANGE,
        label="atomic directory exchange",
    )


def _rename_noreplace_at(parent_fd: int, source: str, destination: str) -> None:
    _renameat2_at(
        parent_fd,
        source,
        destination,
        flags=RENAME_NOREPLACE,
        label="atomic no-replace rename",
    )


def _bundle_state_at(
    story_fd: int,
    name: str,
    *,
    previous_digest: str | None,
    next_digest: str,
    previous_identity: tuple[int, int] | None = None,
    next_identity: tuple[int, int] | None = None,
) -> str:
    try:
        captured = _read_bundle_capture_at(story_fd, name, allow_missing=True)
    except OSError:
        return "unknown"
    except RuntimeError:
        return "unknown"
    if captured is None:
        return "missing"
    files, identities = captured
    identity = identities["."]
    digest = _validate_bundle_files(files)
    if digest == next_digest and (next_identity is None or identity == next_identity):
        return "next"
    if (
        previous_digest is not None
        and digest == previous_digest
        and (previous_identity is None or identity == previous_identity)
    ):
        return "previous"
    return "unknown"


def _finish_terminal_journal_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
) -> None:
    if state["cleanup_phase"] != "CLEANUP_COMPLETE":
        raise PublicationRecoveryRequired("publication journal cleanup is incomplete")
    _assert_terminal_cleanup_inventory_at(story_fd, state)
    journal_fd = _open_directory_at(story_fd, JOURNAL_NAME, label="publication journal")
    try:
        current, _contents, state_signatures = _assert_active_journal_trust_from_fd_at(
            story_fd, journal_fd, trust
        )
        if current != dict(state):
            raise PublicationRecoveryRequired(
                "terminal publication journal state drifted"
            )
        identity = _entry_identity(os.fstat(journal_fd))
        _assert_directory_entry_identity_at(
            story_fd, JOURNAL_NAME, journal_fd, label="publication journal"
        )
    finally:
        os.close(journal_fd)
    transaction_id = cast(str, state["transaction_id"])
    cleanup_name = _journal_cleanup_entry_name(transaction_id, identity)
    if (
        _entry_metadata_at(story_fd, cleanup_name) is not None
        or _entry_metadata_at(story_fd, _delete_tombstone_name(cleanup_name))
        is not None
    ):
        raise PublicationRecoveryRequired(
            "publication cleanup journal destination already exists"
        )
    _rename_noreplace_at(story_fd, JOURNAL_NAME, cleanup_name)
    os.fsync(story_fd)
    moved = _entry_metadata_at(story_fd, cleanup_name)
    if (
        moved is None
        or _entry_identity(moved) != identity
        or _entry_metadata_at(story_fd, JOURNAL_NAME) is not None
    ):
        raise PublicationRecoveryRequired("publication cleanup journal move drifted")
    _checkpoint("after-journal-cleanup-tombstone")
    _remove_owned_journal_tree_at(
        story_fd,
        cleanup_name,
        transaction_id=transaction_id,
        expected_identity=identity,
        expected_state_signatures=state_signatures,
    )
    _checkpoint("after-journal-cleanup")


def _recover_journal_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
) -> None:
    previous_digest = cast(str | None, state["previous_manifest_sha256"])
    next_digest = cast(str, state["next_manifest_sha256"])
    previous_identity = _validated_identity(
        state["previous_root_identity"], label="previous root identity"
    )
    next_identity = _validated_identity(
        state["next_root_identity"], label="next root identity"
    )
    if next_identity is None:
        raise PublicationRecoveryRequired("next root identity is missing")
    phase = cast(str, state["publication_phase"])
    mode = cast(str, state["mode"])
    if phase == "PREPARED":
        destination = _bundle_state_at(
            story_fd,
            GENERATED_ROOT.name,
            previous_digest=previous_digest,
            next_digest=next_digest,
            previous_identity=previous_identity,
            next_identity=next_identity,
        )
        stage = _bundle_state_at(
            story_fd,
            STAGE_NAME,
            previous_digest=previous_digest,
            next_digest=next_digest,
            previous_identity=previous_identity,
            next_identity=next_identity,
        )
        terminal_phase = "ROLLED_BACK"
        if mode == "REPLACE" and destination == "previous" and stage == "next":
            pass
        elif (
            mode == "REPLACE"
            and destination == "next"
            and stage
            in {
                "previous",
                "unknown",
            }
        ):
            _rename_exchange_at(story_fd, STAGE_NAME, GENERATED_ROOT.name)
            os.fsync(story_fd)
            _checkpoint("after-recovery-reverse-exchange")
            restored_stage = _bundle_state_at(
                story_fd,
                STAGE_NAME,
                previous_digest=previous_digest,
                next_digest=next_digest,
                previous_identity=previous_identity,
                next_identity=next_identity,
            )
            restored_destination = _bundle_state_at(
                story_fd,
                GENERATED_ROOT.name,
                previous_digest=previous_digest,
                next_digest=next_digest,
                previous_identity=previous_identity,
                next_identity=next_identity,
            )
            if restored_stage != "next":
                raise PublicationRecoveryRequired(
                    "reversed ST-1204 stage identity drifted"
                )
            if stage == "previous" and restored_destination != "previous":
                raise PublicationRecoveryRequired(
                    "ST-1204 rollback verification failed"
                )
            if stage == "unknown":
                terminal_phase = "DRIFT_REFUSAL"
        elif mode == "REPLACE" and destination == "unknown" and stage == "next":
            terminal_phase = "DRIFT_REFUSAL"
        elif mode == "FRESH" and destination == "missing" and stage == "next":
            pass
        elif mode == "FRESH" and destination == "next" and stage == "missing":
            _rename_noreplace_at(story_fd, GENERATED_ROOT.name, STAGE_NAME)
            os.fsync(story_fd)
            _checkpoint("after-recovery-fresh-rename")
        elif mode == "FRESH" and destination == "unknown" and stage == "next":
            terminal_phase = "DRIFT_REFUSAL"
        else:
            raise PublicationRecoveryRequired(
                f"ambiguous PREPARED publication state: destination={destination}, stage={stage}"
            )
        state = _write_journal_phase_at(story_fd, state, trust, terminal_phase)
        phase = terminal_phase
        _checkpoint("after-rolled-back-state")
    if phase == "COMMITTED":
        expected_destination = "next"
    elif phase == "ROLLED_BACK":
        expected_destination = "previous" if mode == "REPLACE" else "missing"
    elif phase == "DRIFT_REFUSAL":
        expected_destination = "unknown"
    else:
        raise PublicationRecoveryRequired("unknown ST-1204 journal phase")
    destination = _bundle_state_at(
        story_fd,
        GENERATED_ROOT.name,
        previous_digest=previous_digest,
        next_digest=next_digest,
        previous_identity=previous_identity,
        next_identity=next_identity,
    )
    if phase != "DRIFT_REFUSAL" and destination != expected_destination:
        raise PublicationRecoveryRequired("terminal ST-1204 bundle is ambiguous")
    if phase == "DRIFT_REFUSAL" and destination == "next":
        raise PublicationRecoveryRequired("refused ST-1204 bundle became authoritative")
    state = _continue_terminal_cleanup_at(story_fd, state, trust)
    if state["cleanup_phase"] != "CLEANUP_COMPLETE":
        raise PublicationRecoveryRequired("terminal ST-1204 cleanup did not complete")
    _finish_terminal_journal_at(story_fd, state, trust)


def _recover_cleanup_tombstone_at(_story_fd: int, physical_name: str) -> None:
    cleanup_name, _transaction_id, _expected_identity = (
        _parse_journal_cleanup_entry_name(physical_name)
    )
    if physical_name not in {
        cleanup_name,
        _delete_tombstone_name(cleanup_name),
    }:
        raise PublicationRecoveryRequired("publication cleanup name is ambiguous")
    raise PublicationRecoveryRequired(
        "terminal publication cleanup has no durable state identity inventory"
    )


def _recover_pending_at(
    story_fd: int,
    expected_outputs: Mapping[Path, bytes] | None = None,
    stage_trust: _ActiveStageTrust | None = None,
    journal_trust: _ActiveJournalTrust | None = None,
) -> None:
    story_names = _directory_names_at(story_fd, label="ST-1204 Story directory")
    preparing = _entry_metadata_at(story_fd, JOURNAL_PREPARING_NAME)
    preparing_tombstone = _entry_metadata_at(
        story_fd, _delete_tombstone_name(JOURNAL_PREPARING_NAME)
    )
    journal = _entry_metadata_at(story_fd, JOURNAL_NAME)
    cleanup_names = sorted(
        name
        for name in story_names
        if name.startswith(JOURNAL_CLEANUP_NAME)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{JOURNAL_CLEANUP_NAME}")
    )
    gc_names = sorted(
        name
        for name in story_names
        if name.startswith(BUNDLE_CLEANUP_PREFIX)
        or name.startswith(LEGACY_CLEANUP_PREFIX)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{BUNDLE_CLEANUP_PREFIX}")
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{LEGACY_CLEANUP_PREFIX}")
    )
    if cleanup_names:
        if len(cleanup_names) != 1 or preparing is not None or journal is not None:
            raise PublicationRecoveryRequired("conflicting ST-1204 journal states")
        _recover_cleanup_tombstone_at(story_fd, cleanup_names[0])
        _checkpoint("after-stale-cleanup-tombstone")
        story_names = _directory_names_at(story_fd, label="ST-1204 Story directory")
    if preparing is not None:
        if journal is not None:
            raise PublicationRecoveryRequired("preparing and active journals conflict")
        preparing_fd = _open_directory_at(
            story_fd, JOURNAL_PREPARING_NAME, label="preparing publication journal"
        )
        try:
            identity = _entry_identity(os.fstat(preparing_fd))
            names = _directory_names_at(
                preparing_fd, label="preparing publication journal"
            )
            if names:
                if len(names) != 1:
                    raise PublicationRecoveryRequired(
                        "preparing publication journal is ambiguous"
                    )
                physical_name = next(iter(names))
                logical_name = physical_name.removeprefix(DELETE_TOMBSTONE_PREFIX)
                if logical_name not in {
                    JOURNAL_STATE_NAME,
                    _journal_state_preparing_name(0),
                }:
                    raise PublicationRecoveryRequired(
                        "preparing publication journal inventory drifted"
                    )
                content = _read_regular_at(
                    preparing_fd,
                    physical_name,
                    label="preparing publication journal state",
                    maximum_bytes=16 * 1024,
                )
                if logical_name == JOURNAL_STATE_NAME:
                    state = _validate_journal_state(
                        _load_json(content, label="preparing publication journal state")
                    )
                    if state["sequence"] != 0:
                        raise PublicationRecoveryRequired(
                            "preparing publication journal sequence drifted"
                        )
                _unlink_regular_at(
                    preparing_fd,
                    logical_name,
                    label="preparing publication journal state",
                    expected_content=content,
                )
        finally:
            os.close(preparing_fd)
        _rmdir_empty_at(
            story_fd,
            JOURNAL_PREPARING_NAME,
            label="preparing publication journal",
            expected_identity=identity,
        )
        _checkpoint("after-stale-preparing-cleanup")
        if expected_outputs is not None:
            _remove_partial_stage_at(
                story_fd, _bundle_files(expected_outputs), stage_trust
            )
    elif preparing_tombstone is not None:
        raise PublicationRecoveryRequired(
            "unbound preparing-journal tombstone requires manual recovery"
        )
    if journal is None:
        if gc_names:
            raise PublicationRecoveryRequired(
                "unbound ST-1204 cleanup entries require manual recovery"
            )
        stage_metadata = _entry_metadata_at(story_fd, STAGE_NAME)
        stage_tombstone = _entry_metadata_at(
            story_fd, _delete_tombstone_name(STAGE_NAME)
        )
        if stage_metadata is None and stage_tombstone is not None:
            raise PublicationRecoveryRequired(
                "unbound orphan stage tombstone requires manual recovery"
            )
        if stage_metadata is not None:
            stage_fd = _open_directory_at(
                story_fd, STAGE_NAME, label="orphan publication stage"
            )
            try:
                stage_identity = _entry_identity(os.fstat(stage_fd))
                empty = not _directory_names_at(
                    stage_fd, label="orphan publication stage"
                )
            finally:
                os.close(stage_fd)
            if empty:
                _rmdir_empty_at(
                    story_fd,
                    STAGE_NAME,
                    label="orphan publication stage",
                    expected_identity=stage_identity,
                )
            else:
                raise PublicationRecoveryRequired(
                    "nonempty orphan stage has no durable ownership record"
                )
        return
    if stat.S_ISLNK(journal.st_mode) or not stat.S_ISDIR(journal.st_mode):
        raise PublicationRecoveryRequired("active ST-1204 journal is unsafe")
    journal_fd = _open_directory_at(story_fd, JOURNAL_NAME, label="publication journal")
    try:
        if journal_trust is None:
            state, _contents, active_trust = _capture_active_journal_trust_from_fd_at(
                story_fd, journal_fd, ignore_preparing=True
            )
        else:
            active_trust = journal_trust
            state, _contents, _signatures = _assert_active_journal_trust_from_fd_at(
                story_fd, journal_fd, active_trust, ignore_preparing=True
            )
        _recover_preparing_journal_state_at(story_fd, journal_fd, active_trust)
        state, _contents, _signatures = _assert_active_journal_trust_from_fd_at(
            story_fd, journal_fd, active_trust
        )
    finally:
        os.close(journal_fd)
    _recover_journal_at(story_fd, state, active_trust)


def _assert_no_pending_at(story_fd: int) -> None:
    pending = sorted(
        name
        for name in _directory_names_at(story_fd, label="ST-1204 Story directory")
        if name in {STAGE_NAME, JOURNAL_PREPARING_NAME, JOURNAL_NAME}
        or name.startswith(JOURNAL_CLEANUP_NAME)
        or name.startswith(BUNDLE_CLEANUP_PREFIX)
        or name.startswith(LEGACY_CLEANUP_PREFIX)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{JOURNAL_CLEANUP_NAME}")
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{BUNDLE_CLEANUP_PREFIX}")
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{LEGACY_CLEANUP_PREFIX}")
        or name == _delete_tombstone_name(STAGE_NAME)
        or name == _delete_tombstone_name(JOURNAL_PREPARING_NAME)
    )
    if pending:
        raise PublicationRecoveryRequired(
            "read-only check found pending ST-1204 recovery: " + ", ".join(pending)
        )


def _record_identity_map(
    record: Mapping[str, object], *, label: str, expected_names: set[str]
) -> dict[str, tuple[int, int]]:
    return _validated_identity_map(
        record["tree_identity"], label=label, expected_names=expected_names
    )


def _record_sha256_map(
    record: Mapping[str, object], *, label: str, expected_names: set[str]
) -> dict[str, str]:
    value = _mapping(record["file_sha256"], label=label)
    if set(value) != expected_names:
        raise PublicationRecoveryRequired(f"{label} inventory drifted")
    return {
        name: cast(
            str,
            _validated_sha256(digest, label=f"{label} {name}", optional=False),
        )
        for name, digest in value.items()
    }


def _capture_legacy_fixtures_at(
    story_fd: int, name: str
) -> tuple[dict[str, bytes], dict[str, tuple[int, int]]]:
    fixtures_fd = _open_directory_at(story_fd, name, label="legacy fixtures")
    recorded_fd: int | None = None
    try:
        if _directory_names_at(fixtures_fd, label="legacy fixtures") != {"recorded"}:
            raise PublicationRecoveryRequired("legacy fixture root has unknown entries")
        recorded_fd = _open_directory_at(
            fixtures_fd, "recorded", label="legacy recorded fixtures"
        )
        if _directory_names_at(recorded_fd, label="legacy recorded fixtures") != set(
            EXPECTED_FIXTURE_NAMES
        ):
            raise PublicationRecoveryRequired(
                "legacy recorded fixture inventory drifted"
            )
        files: dict[str, bytes] = {}
        identities = {
            ".": _entry_identity(os.fstat(fixtures_fd)),
            "recorded": _entry_identity(os.fstat(recorded_fd)),
        }
        for fixture_name in EXPECTED_FIXTURE_NAMES:
            content, identity = _read_regular_capture_at(
                recorded_fd,
                fixture_name,
                label=f"legacy fixture {fixture_name}",
            )
            files[fixture_name] = content
            identities[fixture_name] = identity
        _assert_directory_entry_identity_at(
            fixtures_fd, "recorded", recorded_fd, label="legacy recorded fixtures"
        )
        _assert_directory_entry_identity_at(
            story_fd, name, fixtures_fd, label="legacy fixtures"
        )
        return files, identities
    finally:
        if recorded_fd is not None:
            os.close(recorded_fd)
        os.close(fixtures_fd)


def _remove_owned_legacy_fixtures_at(
    story_fd: int,
    name: str,
    *,
    expected_sha256: Mapping[str, str],
    expected_identities: Mapping[str, tuple[int, int]],
) -> None:
    root_metadata = _entry_metadata_at(story_fd, name)
    root_tombstone = _entry_metadata_at(story_fd, _delete_tombstone_name(name))
    if root_metadata is None and root_tombstone is None:
        return
    if root_metadata is None:
        _rmdir_empty_at(
            story_fd,
            name,
            label="legacy fixture cleanup root",
            expected_identity=expected_identities["."],
            checkpoint="legacy-fixtures-root",
        )
        return
    if root_tombstone is not None:
        raise PublicationRecoveryRequired("legacy fixture cleanup root conflicts")
    fixtures_fd = _open_directory_at(story_fd, name, label="legacy fixture cleanup")
    recorded_fd: int | None = None
    try:
        if _entry_identity(os.fstat(fixtures_fd)) != expected_identities["."]:
            raise PublicationRecoveryRequired("legacy fixture cleanup identity drifted")
        allowed_root = {"recorded", _delete_tombstone_name("recorded")}
        if (
            not _directory_names_at(fixtures_fd, label="legacy fixture cleanup")
            <= allowed_root
        ):
            raise PublicationRecoveryRequired(
                "legacy fixture cleanup has unknown entries"
            )
        recorded_state = _cleanup_entry_state(fixtures_fd, "recorded")
        if recorded_state == "conflict":
            raise PublicationRecoveryRequired("legacy recorded cleanup conflicts")
        if recorded_state == "source":
            recorded_fd = _open_directory_at(
                fixtures_fd, "recorded", label="legacy recorded cleanup"
            )
            if (
                _entry_identity(os.fstat(recorded_fd))
                != expected_identities["recorded"]
            ):
                raise PublicationRecoveryRequired(
                    "legacy recorded cleanup identity drifted"
                )
            allowed_files = {
                *EXPECTED_FIXTURE_NAMES,
                *(_delete_tombstone_name(item) for item in EXPECTED_FIXTURE_NAMES),
            }
            if (
                not _directory_names_at(recorded_fd, label="legacy recorded cleanup")
                <= allowed_files
            ):
                raise PublicationRecoveryRequired(
                    "legacy recorded cleanup has unknown entries"
                )
            _validate_monotonic_file_cleanup(recorded_fd, EXPECTED_FIXTURE_NAMES)
            for fixture_name in EXPECTED_FIXTURE_NAMES:
                _unlink_regular_at(
                    recorded_fd,
                    fixture_name,
                    label=f"legacy fixture {fixture_name}",
                    expected_sha256=expected_sha256[fixture_name],
                    expected_identity=expected_identities[fixture_name],
                    checkpoint=f"legacy-fixture-{fixture_name}",
                )
            os.close(recorded_fd)
            recorded_fd = None
            _rmdir_empty_at(
                fixtures_fd,
                "recorded",
                label="legacy recorded cleanup",
                expected_identity=expected_identities["recorded"],
                checkpoint="legacy-recorded",
            )
        elif recorded_state == "quarantined":
            _rmdir_empty_at(
                fixtures_fd,
                "recorded",
                label="legacy recorded cleanup",
                expected_identity=expected_identities["recorded"],
                checkpoint="legacy-recorded",
            )
        _assert_directory_entry_identity_at(
            story_fd, name, fixtures_fd, label="legacy fixture cleanup"
        )
    finally:
        if recorded_fd is not None:
            os.close(recorded_fd)
        os.close(fixtures_fd)
    _rmdir_empty_at(
        story_fd,
        name,
        label="legacy fixture cleanup root",
        expected_identity=expected_identities["."],
        checkpoint="legacy-fixtures-root",
    )


def _continue_bundle_cleanup_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
) -> dict[str, object]:
    phase = cast(str, state["publication_phase"])
    mode = cast(str, state["mode"])
    cleanup_phase = cast(str, state["cleanup_phase"])
    role: str | None = None
    if phase == "COMMITTED" and mode == "REPLACE":
        role = "PREVIOUS"
    elif phase in {"ROLLED_BACK", "DRIFT_REFUSAL"}:
        role = "NEXT"
    if role is None:
        return dict(state)
    if cleanup_phase == "NONE":
        captured = _read_bundle_capture_at(story_fd, STAGE_NAME, allow_missing=False)
        if captured is None:
            raise PublicationRecoveryRequired("owned cleanup stage is missing")
        files, identities = captured
        expected_digest = cast(
            str,
            state[
                "previous_manifest_sha256"
                if role == "PREVIOUS"
                else "next_manifest_sha256"
            ],
        )
        expected_root = _validated_identity(
            state[
                "previous_root_identity" if role == "PREVIOUS" else "next_root_identity"
            ],
            label="bundle cleanup root identity",
        )
        if (
            _validate_bundle_files(files) != expected_digest
            or identities["."] != expected_root
        ):
            raise PublicationRecoveryRequired("owned cleanup stage identity drifted")
        transaction_id = cast(str, state["transaction_id"])
        new_cleanup_record = {
            "role": role,
            "source_name": STAGE_NAME,
            "quarantine_name": f"{BUNDLE_CLEANUP_PREFIX}{transaction_id}",
            "tree_identity": _identity_map_record(identities),
            "file_sha256": {
                name: _sha256(value) for name, value in sorted(files.items())
            },
        }
        state = _write_journal_update_at(
            story_fd,
            state,
            trust,
            cleanup_phase="BUNDLE_QUARANTINING",
            cleanup_bundle=new_cleanup_record,
        )
        cleanup_phase = "BUNDLE_QUARANTINING"
        _checkpoint("after-bundle-cleanup-owned-state")
    cleanup_record = _mapping(state["cleanup_bundle"], label="bundle cleanup record")
    quarantine_name = cast(str, cleanup_record["quarantine_name"])
    identities = _record_identity_map(
        cleanup_record,
        label="bundle cleanup identities",
        expected_names={
            ".",
            "manifest.json",
            "fixtures",
            "fixtures/recorded",
            *EXPECTED_BUNDLE_PATHS[1:],
        },
    )
    hashes = _record_sha256_map(
        cleanup_record,
        label="bundle cleanup hashes",
        expected_names=set(EXPECTED_BUNDLE_PATHS),
    )
    if cleanup_phase == "BUNDLE_QUARANTINING":
        source = _entry_metadata_at(story_fd, STAGE_NAME)
        quarantined = _entry_metadata_at(story_fd, quarantine_name)
        if source is not None and quarantined is not None:
            raise PublicationRecoveryRequired("bundle cleanup quarantine conflicts")
        if source is not None:
            captured = _read_bundle_capture_at(
                story_fd, STAGE_NAME, allow_missing=False
            )
            if captured is None or captured[1] != identities:
                raise PublicationRecoveryRequired("bundle cleanup source drifted")
            _checkpoint("before-bundle-cleanup-quarantine")
            _rename_noreplace_at(story_fd, STAGE_NAME, quarantine_name)
            os.fsync(story_fd)
            _checkpoint("after-bundle-cleanup-quarantine")
        try:
            captured = _read_bundle_capture_at(
                story_fd, quarantine_name, allow_missing=False
            )
            quarantine_matches = (
                captured is not None
                and captured[1] == identities
                and {name: _sha256(value) for name, value in captured[0].items()}
                == hashes
            )
        except RuntimeError:
            quarantine_matches = False
        if not quarantine_matches:
            _restore_mismatched_quarantine_at(
                story_fd,
                STAGE_NAME,
                quarantine_name,
                label="bundle cleanup",
            )
        state = _write_journal_update_at(
            story_fd, state, trust, cleanup_phase="BUNDLE_DELETING"
        )
        cleanup_phase = "BUNDLE_DELETING"
        _checkpoint("after-bundle-cleanup-deleting-state")
    if cleanup_phase == "BUNDLE_DELETING":
        if _entry_metadata_at(story_fd, STAGE_NAME) is not None:
            raise PublicationRecoveryRequired("bundle cleanup source reappeared")
        _remove_owned_bundle_tree_at(
            story_fd,
            quarantine_name,
            expected_sha256=hashes,
            expected_identities=identities,
            checkpoint_prefix="bundle-cleanup",
        )
        state = _write_journal_update_at(
            story_fd, state, trust, cleanup_phase="BUNDLE_REMOVED"
        )
    return dict(state)


def _continue_legacy_cleanup_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
) -> dict[str, object]:
    cleanup_phase = cast(str, state["cleanup_phase"])
    if cleanup_phase == "CLEANUP_COMPLETE":
        return dict(state)
    if cleanup_phase in {"NONE", "BUNDLE_REMOVED"}:
        legacy_manifest = _entry_metadata_at(story_fd, LEGACY_MANIFEST_PATH.name)
        legacy_fixtures = _entry_metadata_at(story_fd, "fixtures")
        if legacy_manifest is None and legacy_fixtures is None:
            _assert_terminal_cleanup_inventory_at(story_fd, state)
            return _write_journal_update_at(
                story_fd, state, trust, cleanup_phase="CLEANUP_COMPLETE"
            )
        if legacy_manifest is None or legacy_fixtures is None:
            raise PublicationRecoveryRequired("legacy ST-1204 tree is incomplete")
        manifest_content, manifest_identity = _read_regular_capture_at(
            story_fd, LEGACY_MANIFEST_PATH.name, label="legacy ST-1204 manifest"
        )
        if _sha256(manifest_content) != LEGACY_MANIFEST_SHA256:
            raise PublicationRecoveryRequired("legacy ST-1204 manifest is unowned")
        legacy_files, legacy_identities = _capture_legacy_fixtures_at(
            story_fd, "fixtures"
        )
        generated = _read_bundle_at(story_fd, GENERATED_ROOT.name, allow_missing=False)
        if generated is None or any(
            legacy_files[name] != generated[f"fixtures/recorded/{name}"]
            for name in EXPECTED_FIXTURE_NAMES
        ):
            raise PublicationRecoveryRequired("legacy fixture bytes are unowned")
        transaction_id = cast(str, state["transaction_id"])
        new_manifest_record = {
            "source_name": LEGACY_MANIFEST_PATH.name,
            "quarantine_name": f"{LEGACY_CLEANUP_PREFIX}{transaction_id}.manifest",
            "identity": _identity_record(manifest_identity),
            "sha256": LEGACY_MANIFEST_SHA256,
        }
        new_fixtures_record = {
            "source_name": "fixtures",
            "quarantine_name": f"{LEGACY_CLEANUP_PREFIX}{transaction_id}.fixtures",
            "tree_identity": _identity_map_record(legacy_identities),
            "file_sha256": {
                name: _sha256(value) for name, value in sorted(legacy_files.items())
            },
        }
        state = _write_journal_update_at(
            story_fd,
            state,
            trust,
            cleanup_phase="LEGACY_QUARANTINING",
            legacy_manifest=new_manifest_record,
            legacy_fixtures=new_fixtures_record,
        )
        cleanup_phase = "LEGACY_QUARANTINING"
        _checkpoint("after-legacy-cleanup-owned-state")
    manifest_record = _mapping(
        state["legacy_manifest"], label="legacy manifest cleanup"
    )
    fixtures_record = _mapping(state["legacy_fixtures"], label="legacy fixture cleanup")
    manifest_quarantine = cast(str, manifest_record["quarantine_name"])
    fixtures_quarantine = cast(str, fixtures_record["quarantine_name"])
    recorded_manifest_identity = _validated_identity(
        manifest_record["identity"], label="legacy manifest identity"
    )
    if recorded_manifest_identity is None:
        raise PublicationRecoveryRequired("legacy manifest identity is missing")
    fixture_identities = _record_identity_map(
        fixtures_record,
        label="legacy fixture identities",
        expected_names={".", "recorded", *EXPECTED_FIXTURE_NAMES},
    )
    fixture_hashes = _record_sha256_map(
        fixtures_record,
        label="legacy fixture hashes",
        expected_names=set(EXPECTED_FIXTURE_NAMES),
    )
    if cleanup_phase == "LEGACY_QUARANTINING":
        for source_name, quarantine_name, expected_identity, is_directory in (
            (
                LEGACY_MANIFEST_PATH.name,
                manifest_quarantine,
                recorded_manifest_identity,
                False,
            ),
            ("fixtures", fixtures_quarantine, fixture_identities["."], True),
        ):
            source = _entry_metadata_at(story_fd, source_name)
            quarantined = _entry_metadata_at(story_fd, quarantine_name)
            if source is not None and quarantined is not None:
                raise PublicationRecoveryRequired("legacy cleanup quarantine conflicts")
            if source is not None:
                if is_directory:
                    source_files, source_identities = _capture_legacy_fixtures_at(
                        story_fd, source_name
                    )
                    if (
                        source_identities != fixture_identities
                        or {
                            name: _sha256(value) for name, value in source_files.items()
                        }
                        != fixture_hashes
                    ):
                        raise PublicationRecoveryRequired(
                            "legacy fixture source drifted"
                        )
                else:
                    source_content, source_identity = _read_regular_capture_at(
                        story_fd, source_name, label="legacy manifest source"
                    )
                    if (
                        source_identity != expected_identity
                        or _sha256(source_content) != LEGACY_MANIFEST_SHA256
                    ):
                        raise PublicationRecoveryRequired(
                            "legacy manifest source drifted"
                        )
                _checkpoint(f"before-legacy-{source_name}-quarantine")
                _rename_noreplace_at(story_fd, source_name, quarantine_name)
                os.fsync(story_fd)
                _checkpoint(f"after-legacy-{source_name}-quarantine")
            try:
                if is_directory:
                    captured_files, captured_identities = _capture_legacy_fixtures_at(
                        story_fd, quarantine_name
                    )
                    quarantine_matches = (
                        captured_identities == fixture_identities
                        and {
                            name: _sha256(value)
                            for name, value in captured_files.items()
                        }
                        == fixture_hashes
                    )
                else:
                    content, identity = _read_regular_capture_at(
                        story_fd, quarantine_name, label="legacy manifest quarantine"
                    )
                    quarantine_matches = (
                        identity == expected_identity
                        and _sha256(content) == LEGACY_MANIFEST_SHA256
                    )
            except RuntimeError:
                quarantine_matches = False
            if not quarantine_matches:
                _restore_mismatched_quarantine_at(
                    story_fd,
                    source_name,
                    quarantine_name,
                    label="legacy cleanup",
                )
        state = _write_journal_update_at(
            story_fd, state, trust, cleanup_phase="LEGACY_DELETING"
        )
        cleanup_phase = "LEGACY_DELETING"
        _checkpoint("after-legacy-cleanup-deleting-state")
    if cleanup_phase == "LEGACY_DELETING":
        _unlink_regular_at(
            story_fd,
            manifest_quarantine,
            label="legacy manifest quarantine",
            expected_sha256=LEGACY_MANIFEST_SHA256,
            expected_identity=recorded_manifest_identity,
            checkpoint="legacy-manifest",
        )
        _remove_owned_legacy_fixtures_at(
            story_fd,
            fixtures_quarantine,
            expected_sha256=fixture_hashes,
            expected_identities=fixture_identities,
        )
        _assert_terminal_cleanup_inventory_at(story_fd, state)
        state = _write_journal_update_at(
            story_fd, state, trust, cleanup_phase="CLEANUP_COMPLETE"
        )
    return dict(state)


def _assert_terminal_cleanup_inventory_at(
    story_fd: int,
    state: Mapping[str, object],
    *,
    allowed_journal_cleanup: str | None = None,
) -> None:
    _checkpoint("before-cleanup-complete-verification")
    story_names = _directory_names_at(story_fd, label="ST-1204 Story directory")
    forbidden = {
        STAGE_NAME,
        _delete_tombstone_name(STAGE_NAME),
        JOURNAL_PREPARING_NAME,
        _delete_tombstone_name(JOURNAL_PREPARING_NAME),
        LEGACY_MANIFEST_PATH.name,
        _delete_tombstone_name(LEGACY_MANIFEST_PATH.name),
        "fixtures",
        _delete_tombstone_name("fixtures"),
    }
    forbidden.update(
        name
        for name in story_names
        if name.startswith(BUNDLE_CLEANUP_PREFIX)
        or name.startswith(LEGACY_CLEANUP_PREFIX)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{BUNDLE_CLEANUP_PREFIX}")
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{LEGACY_CLEANUP_PREFIX}")
        or name.startswith(JOURNAL_CLEANUP_NAME)
        or name.startswith(f"{DELETE_TOMBSTONE_PREFIX}{JOURNAL_CLEANUP_NAME}")
    )
    if allowed_journal_cleanup is not None:
        forbidden.discard(allowed_journal_cleanup)
        forbidden.discard(_delete_tombstone_name(allowed_journal_cleanup))
    present = sorted(forbidden & story_names)
    if present:
        raise PublicationRecoveryRequired(
            "terminal ST-1204 cleanup inventory is not closed: " + ", ".join(present)
        )
    phase = cast(str, state["publication_phase"])
    if phase == "DRIFT_REFUSAL":
        return
    previous_identity = _validated_identity(
        state["previous_root_identity"], label="previous root identity"
    )
    next_identity = _validated_identity(
        state["next_root_identity"], label="next root identity"
    )
    destination = _bundle_state_at(
        story_fd,
        GENERATED_ROOT.name,
        previous_digest=cast(str | None, state["previous_manifest_sha256"]),
        next_digest=cast(str, state["next_manifest_sha256"]),
        previous_identity=previous_identity,
        next_identity=next_identity,
    )
    expected = (
        "next"
        if phase == "COMMITTED"
        else "previous"
        if state["mode"] == "REPLACE"
        else "missing"
    )
    if destination != expected:
        raise PublicationRecoveryRequired(
            "terminal ST-1204 authoritative bundle drifted during cleanup"
        )


def _continue_terminal_cleanup_at(
    story_fd: int,
    state: Mapping[str, object],
    trust: _ActiveJournalTrust,
) -> dict[str, object]:
    state = _continue_bundle_cleanup_at(story_fd, state, trust)
    if state["publication_phase"] == "COMMITTED":
        return _continue_legacy_cleanup_at(story_fd, state, trust)
    if state["cleanup_phase"] in {"NONE", "BUNDLE_REMOVED"}:
        _assert_terminal_cleanup_inventory_at(story_fd, state)
        return _write_journal_update_at(
            story_fd, state, trust, cleanup_phase="CLEANUP_COMPLETE"
        )
    return dict(state)


def _assert_legacy_absent_at(story_fd: int) -> None:
    if (
        _entry_metadata_at(story_fd, LEGACY_MANIFEST_PATH.name) is not None
        or _entry_metadata_at(story_fd, "fixtures") is not None
    ):
        raise RuntimeError("non-authoritative legacy ST-1204 outputs remain")


def _remove_partial_stage_at(
    story_fd: int,
    expected: Mapping[str, bytes],
    trust: _ActiveStageTrust | None = None,
) -> None:
    root_metadata = _entry_metadata_at(story_fd, STAGE_NAME)
    root_tombstone = _entry_metadata_at(story_fd, _delete_tombstone_name(STAGE_NAME))
    if root_metadata is None and root_tombstone is None:
        return
    if root_metadata is None:
        _rmdir_empty_at(story_fd, STAGE_NAME, label="partial publication stage")
        return
    if root_tombstone is not None:
        raise PublicationRecoveryRequired("partial publication stage conflicts")
    if trust is None:
        unbound_fd = _open_directory_at(
            story_fd, STAGE_NAME, label="unbound partial publication stage"
        )
        try:
            unbound_identity = _entry_identity(os.fstat(unbound_fd))
            if _directory_names_at(
                unbound_fd, label="unbound partial publication stage"
            ):
                raise PublicationRecoveryRequired(
                    "nonempty partial stage has no invocation ownership inventory"
                )
            _assert_directory_entry_identity_at(
                story_fd,
                STAGE_NAME,
                unbound_fd,
                label="unbound partial publication stage",
            )
        finally:
            os.close(unbound_fd)
        _rmdir_empty_at(
            story_fd,
            STAGE_NAME,
            label="empty partial publication stage",
            expected_identity=unbound_identity,
        )
        return
    _assert_stage_trust_at(story_fd, expected, trust, complete=False)
    stage_fd = _open_directory_at(
        story_fd, STAGE_NAME, label="partial publication stage"
    )
    fixtures_fd: int | None = None
    recorded_fd: int | None = None
    try:
        stage_identity = trust.directory_identities["."]
        if _entry_identity(os.fstat(stage_fd)) != stage_identity:
            raise PublicationRecoveryRequired(
                "partial publication stage invocation identity drifted"
            )
        stage_names = _directory_names_at(stage_fd, label="partial publication stage")
        if not stage_names <= {"manifest.json", "fixtures"}:
            raise PublicationRecoveryRequired("partial publication stage is unowned")
        if "fixtures" in stage_names:
            fixtures_fd = _open_directory_at(
                stage_fd, "fixtures", label="partial staged fixtures"
            )
            fixtures_identity = trust.directory_identities["fixtures"]
            if _entry_identity(os.fstat(fixtures_fd)) != fixtures_identity:
                raise PublicationRecoveryRequired(
                    "partial staged fixture directory invocation identity drifted"
                )
            fixture_names = _directory_names_at(
                fixtures_fd, label="partial staged fixtures"
            )
            if not fixture_names <= {"recorded"}:
                raise PublicationRecoveryRequired("partial staged fixtures are unowned")
            if "recorded" in fixture_names:
                recorded_fd = _open_directory_at(
                    fixtures_fd, "recorded", label="partial recorded fixtures"
                )
                recorded_identity = trust.directory_identities["fixtures/recorded"]
                if _entry_identity(os.fstat(recorded_fd)) != recorded_identity:
                    raise PublicationRecoveryRequired(
                        "partial recorded fixture directory invocation identity drifted"
                    )
                names = _directory_names_at(
                    recorded_fd, label="partial recorded fixtures"
                )
                expected_prefix = set(EXPECTED_FIXTURE_NAMES[: len(names)])
                if names != expected_prefix:
                    raise PublicationRecoveryRequired(
                        "partial recorded fixture progress is unowned"
                    )
                for fixture_name in EXPECTED_FIXTURE_NAMES:
                    if fixture_name not in names:
                        continue
                    content, signature = _read_regular_stat_capture_at(
                        recorded_fd,
                        fixture_name,
                        label=f"partial staged fixture {fixture_name}",
                    )
                    expected_signature = trust.file_signatures[
                        f"fixtures/recorded/{fixture_name}"
                    ]
                    if (
                        signature != expected_signature
                        or content != expected[f"fixtures/recorded/{fixture_name}"]
                    ):
                        raise PublicationRecoveryRequired(
                            "partial staged fixture invocation identity drifted"
                        )
                    _unlink_regular_at(
                        recorded_fd,
                        fixture_name,
                        label=f"partial staged fixture {fixture_name}",
                        expected_content=content,
                        expected_identity=(
                            expected_signature[0],
                            expected_signature[1],
                        ),
                        expected_signature=expected_signature,
                    )
                os.close(recorded_fd)
                recorded_fd = None
                _rmdir_empty_at(
                    fixtures_fd,
                    "recorded",
                    label="partial recorded fixtures",
                    expected_identity=recorded_identity,
                )
            os.close(fixtures_fd)
            fixtures_fd = None
            _rmdir_empty_at(
                stage_fd,
                "fixtures",
                label="partial staged fixtures",
                expected_identity=fixtures_identity,
            )
        if "manifest.json" in stage_names:
            content, signature = _read_regular_stat_capture_at(
                stage_fd, "manifest.json", label="partial staged manifest"
            )
            expected_signature = trust.file_signatures["manifest.json"]
            if signature != expected_signature or content != expected["manifest.json"]:
                raise PublicationRecoveryRequired(
                    "partial staged manifest invocation identity drifted"
                )
            _unlink_regular_at(
                stage_fd,
                "manifest.json",
                label="partial staged manifest",
                expected_content=content,
                expected_identity=(expected_signature[0], expected_signature[1]),
                expected_signature=expected_signature,
            )
        _assert_directory_entry_identity_at(
            story_fd, STAGE_NAME, stage_fd, label="partial publication stage"
        )
    finally:
        for descriptor in (recorded_fd, fixtures_fd, stage_fd):
            if descriptor is not None:
                os.close(descriptor)
    _rmdir_empty_at(
        story_fd,
        STAGE_NAME,
        label="partial publication stage",
        expected_identity=stage_identity,
    )


def _publish_outputs_at(story_fd: int, outputs: Mapping[Path, bytes]) -> str:
    expected = _bundle_files(outputs)
    next_digest = _validate_bundle_files(expected)
    installed_capture = _read_bundle_capture_at(
        story_fd, GENERATED_ROOT.name, allow_missing=True
    )
    installed = None if installed_capture is None else installed_capture[0]
    if installed == expected:
        if (
            _entry_metadata_at(story_fd, LEGACY_MANIFEST_PATH.name) is None
            and _entry_metadata_at(story_fd, "fixtures") is None
        ):
            return next_digest
        if installed_capture is None:
            raise PublicationRecoveryRequired("installed bundle capture disappeared")
        installed_identities = installed_capture[1]
        state = _new_journal_state(
            mode="NOOP_LEGACY",
            previous_digest=next_digest,
            next_digest=next_digest,
            previous_identity=installed_identities["."],
            next_identity=installed_identities["."],
            publication_phase="COMMITTED",
        )
        legacy_journal_trust = _ActiveJournalTrust()
        _create_journal_at(story_fd, state, legacy_journal_trust)
        _recover_journal_at(story_fd, state, legacy_journal_trust)
        return next_digest
    committed = False
    primary: BaseException | None = None
    stage_trust = _ActiveStageTrust()
    journal_trust: _ActiveJournalTrust | None = None
    try:
        previous_digest = (
            _validate_bundle_files(installed) if installed is not None else None
        )
        previous_identities = (
            installed_capture[1] if installed_capture is not None else None
        )
        _create_stage_at(story_fd, expected, stage_trust)
        staged_capture = _read_bundle_capture_at(
            story_fd, STAGE_NAME, allow_missing=False
        )
        if staged_capture is None:
            raise PublicationRecoveryRequired("publication stage disappeared")
        staged_files, staged_identities = staged_capture
        if staged_files != expected:
            raise PublicationRecoveryRequired("publication stage bytes drifted")
        state = _new_journal_state(
            mode="REPLACE" if installed is not None else "FRESH",
            previous_digest=previous_digest,
            next_digest=next_digest,
            previous_identity=(
                None if previous_identities is None else previous_identities["."]
            ),
            next_identity=staged_identities["."],
        )
        journal_trust = _ActiveJournalTrust()
        _create_journal_at(story_fd, state, journal_trust)
        _checkpoint("before-publication")
        current_stage = _read_bundle_capture_at(
            story_fd, STAGE_NAME, allow_missing=False
        )
        if current_stage != staged_capture:
            raise PublicationRecoveryRequired("publication stage identity drifted")
        if installed is None:
            _rename_noreplace_at(story_fd, STAGE_NAME, GENERATED_ROOT.name)
        else:
            current_installed = _read_bundle_capture_at(
                story_fd, GENERATED_ROOT.name, allow_missing=False
            )
            if current_installed != installed_capture:
                raise PublicationRecoveryRequired("installed bundle identity drifted")
            _checkpoint("after-installed-revalidation")
            _rename_exchange_at(story_fd, STAGE_NAME, GENERATED_ROOT.name)
        os.fsync(story_fd)
        _checkpoint("after-publication-namespace")
        published_capture = _read_bundle_capture_at(
            story_fd, GENERATED_ROOT.name, allow_missing=False
        )
        if published_capture != staged_capture:
            raise RuntimeError("published ST-1204 bundle failed exact verification")
        if installed is not None:
            preserved_capture = _read_bundle_capture_at(
                story_fd, STAGE_NAME, allow_missing=False
            )
            if preserved_capture != installed_capture:
                raise PublicationRecoveryRequired(
                    "exchanged previous ST-1204 bundle was not preserved"
                )
        _checkpoint("after-publication-verify")
        state = _write_journal_phase_at(story_fd, state, journal_trust, "COMMITTED")
        committed = True
        _checkpoint("after-committed-state")
        _recover_journal_at(story_fd, state, journal_trust)
        if (
            _read_bundle_at(story_fd, GENERATED_ROOT.name, allow_missing=False)
            != expected
        ):
            raise RuntimeError("committed ST-1204 bundle changed during cleanup")
        return next_digest
    except BaseException as exc:
        primary = exc
        if not isinstance(exc, _InvocationIdentityDrift):
            try:
                if _entry_metadata_at(story_fd, JOURNAL_NAME) is None:
                    _remove_partial_stage_at(story_fd, expected, stage_trust)
                _recover_pending_at(
                    story_fd,
                    outputs,
                    stage_trust,
                    journal_trust,
                )
            except BaseException as recovery_error:
                primary.add_note(
                    "ST-1204 automatic publication recovery also failed: "
                    f"{type(recovery_error).__name__}"
                )
        else:
            primary.add_note(
                "ST-1204 invocation identity drift was preserved without re-capture"
            )
        if committed:
            primary.add_note("the exact new ST-1204 bundle was durably committed")
        raise


def generate(root: Path = REPOSITORY_ROOT) -> str:
    story_fd = _acquire_story_lock(root, exclusive=True, create=True)
    primary: BaseException | None = None
    try:
        outputs = build_outputs(root)
        _recover_pending_at(story_fd, outputs)
        return _publish_outputs_at(story_fd, outputs)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _release_story_lock(story_fd, primary)


def check(root: Path = REPOSITORY_ROOT) -> str:
    story_fd = _acquire_story_lock(root, exclusive=False, create=False)
    primary: BaseException | None = None
    try:
        _assert_no_pending_at(story_fd)
        expected = _bundle_files(build_outputs(root))
        observed = _read_bundle_at(story_fd, GENERATED_ROOT.name, allow_missing=False)
        if observed != expected:
            raise RuntimeError("generated ST-1204 bundle drifted")
        _assert_legacy_absent_at(story_fd)
        return _validate_bundle_files(expected)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        _release_story_lock(story_fd, primary)


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
        print(f"ST-1204 recorded fixture generation failed: {exc}", file=sys.stderr)
        return 1
    action = "verified" if arguments.check else "generated"
    print(f"ST-1204 recorded fixtures {action}; manifest sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
