#!/usr/bin/env python3
"""Run the ST-0308 deterministic, read-only automated handoff preflight.

The command proves only byte-, shape-, and inventory-level facts.  It does not
interpret the proposed persistence design, reconcile canonical decisions, or
grant implementation authority.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
import tarfile
from typing import Any, Final, NamedTuple

import yaml
from yaml.constructor import ConstructorError
from yaml.events import AliasEvent, NodeEvent
from yaml.nodes import MappingNode
from yaml.tokens import AliasToken, AnchorToken, TagToken


SCRIPT_REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-0308/contracts/design-handoff-validation.v1.yaml"
)
# This digest is deliberately updated only after the declarative contract is
# final.  A changed contract is a trusted-environment error.
EXPECTED_CONTRACT_SHA256: Final = (
    "05d0e4a78f302e4286bf3d861d7e31625993ecbc7f718f5f9a4024586c06879c"
)

SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")
MAX_HARD_READ_BYTES: Final = 16 * 1024 * 1024
MAX_HANDOFF_BYTES: Final = 8 * 1024 * 1024
MODULES: Final = (
    "ops",
    "iam",
    "portfolio",
    "catalog",
    "evidence",
    "editorial",
    "ai",
    "policy",
)
DEFAULT_MANUAL_TOPICS: Final = (
    "aggregate_version_event_semantics",
    "domain_value_mapper_semantics",
    "exact_state_cas_predicate_semantics",
    "inward_uow_surface_semantics",
    "physical_inventory_and_lock_version_semantics",
    "shared_infrastructure_ownership",
    "idempotency_claim_completion_semantics",
    "d6_connection_and_identity_boundary_semantics",
)
DEFAULT_MANUAL_CHECKS: Final = (
    "finding_waiver_non_versioned_cas",
    "inward_uow_surfaces_all_modules_and_joined_forms",
    "shared_audit_outbox_idempotency_ownership",
    "idempotency_completion_cas_expressibility",
    "aggregate_version_source_or_event_exclusion",
    "exact_state_cas_predicates",
    "domain_value_mapper_targets",
    "connection_and_identity_boundary_semantics",
)
DIRECT_REFERENCE_PAIRS: Final = (
    ("path", "sha256"),
    ("source_path", "source_sha256"),
    ("file_path", "file_sha256"),
)
ARCHIVE_REFERENCE_KEYS: Final = frozenset(
    {"archive_path", "archive_sha256", "member_path", "member_sha256"}
)
DIRECT_REFERENCE_KEYS: Final = frozenset(
    key for pair in DIRECT_REFERENCE_PAIRS for key in pair
)


class CandidateFailure(Exception):
    """The proposed handoff is not a valid preflight candidate."""

    def __init__(self, code: str, **details: Any) -> None:
        super().__init__(code)
        self.code = code
        self.details = details


class TrustedFailure(Exception):
    """The validator cannot trust its repository or contract inputs."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UsageFailure(Exception):
    """The CLI invocation is invalid."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader with bounded composition and duplicate-key rejection."""

    def __init__(
        self,
        stream: object,
        *,
        depth_limit: int,
        node_limit: int,
        candidate: bool,
    ) -> None:
        super().__init__(stream)
        self._yaml_depth_limit = depth_limit
        self._yaml_node_limit = node_limit
        self._yaml_candidate = candidate
        self._yaml_depth = 0
        self._yaml_node_count = 0

    def _budget_failure(self, suffix: str) -> None:
        if self._yaml_candidate:
            raise CandidateFailure(suffix)
        raise TrustedFailure(f"trusted_{suffix}")

    def compose_node(self, parent: object, index: object) -> yaml.nodes.Node:
        event = self.peek_event()
        if isinstance(event, AliasEvent):
            self._budget_failure(
                "yaml_alias_or_anchor" if self._yaml_candidate else "yaml_alias"
            )
        if isinstance(event, NodeEvent) and (
            event.anchor is not None or event.tag is not None
        ):
            self._budget_failure(
                "yaml_alias_or_anchor" if self._yaml_candidate else "yaml_tag"
            )
        if self._yaml_node_count >= self._yaml_node_limit:
            self._budget_failure("yaml_node_limit")
        if self._yaml_depth > self._yaml_depth_limit:
            self._budget_failure("yaml_depth_limit")
        self._yaml_node_count += 1
        self._yaml_depth += 1
        try:
            return super().compose_node(parent, index)
        finally:
            self._yaml_depth -= 1


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
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
                "found duplicate mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _required_security_flags() -> tuple[int, int, int]:
    values: list[int] = []
    for name in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"):
        value = getattr(os, name, None)
        if type(value) is not int or value <= 0:
            raise TrustedFailure(f"missing_{name.lower()}")
        values.append(value)
    return values[0], values[1], values[2]


def _absolute_path(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _assert_no_symlink_ancestors(path: Path, *, final_may_be_file: bool) -> None:
    absolute = _absolute_path(path)
    if not absolute.is_absolute() or not absolute.parts:
        raise TrustedFailure("invalid_absolute_path")
    current = Path(absolute.anchor)
    for index, part in enumerate(absolute.parts[1:], start=1):
        current /= part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise TrustedFailure("missing_path_component") from exc
        is_final = index == len(absolute.parts) - 1
        if stat.S_ISLNK(metadata.st_mode):
            raise TrustedFailure("symlink_path_component")
        if not is_final or not final_may_be_file:
            if not stat.S_ISDIR(metadata.st_mode):
                raise TrustedFailure("non_directory_path_component")


def _read_limited(file_descriptor: int, limit: int) -> bytes:
    chunks: list[bytes] = []
    remaining = limit + 1
    while remaining:
        try:
            chunk = os.read(file_descriptor, min(1024 * 1024, remaining))
        except OSError as exc:
            raise TrustedFailure("file_read_failed") from exc
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _stable_file_metadata(
    directory_descriptor: int,
    leaf: str,
    file_descriptor: int,
    path_before: os.stat_result,
    metadata_before: os.stat_result,
) -> None:
    metadata_after = os.fstat(file_descriptor)
    try:
        path_after = os.stat(
            leaf,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
    except OSError as exc:
        raise TrustedFailure("file_disappeared") from exc
    stable_fields = (
        "st_dev",
        "st_ino",
        "st_mode",
        "st_size",
        "st_mtime_ns",
        "st_ctime_ns",
    )
    if not all(
        getattr(path_before, field)
        == getattr(metadata_before, field)
        == getattr(metadata_after, field)
        == getattr(path_after, field)
        for field in stable_fields
    ):
        raise TrustedFailure("file_changed_during_read")


def _secure_read_absolute(
    path: Path,
    *,
    limit: int,
    candidate_size_failure: bool = False,
) -> bytes:
    """Read a stable regular file with descriptor-relative no-follow opens."""

    if type(limit) is not int or limit <= 0 or limit > MAX_HARD_READ_BYTES:
        raise TrustedFailure("read_limit_invalid")
    directory_flag, nofollow_flag, nonblock_flag = _required_security_flags()
    absolute = _absolute_path(path)
    _assert_no_symlink_ancestors(absolute, final_may_be_file=True)
    parts = absolute.parts
    if len(parts) < 2:
        raise TrustedFailure("file_path_required")

    close_on_exec = getattr(os, "O_CLOEXEC", 0)
    directory_flags = os.O_RDONLY | directory_flag | nofollow_flag | close_on_exec
    descriptors: list[int] = []
    try:
        descriptor = os.open(absolute.anchor, directory_flags)
        descriptors.append(descriptor)
        for part in parts[1:-1]:
            descriptor = os.open(part, directory_flags, dir_fd=descriptor)
            descriptors.append(descriptor)

        leaf = parts[-1]
        try:
            path_before = os.stat(leaf, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise TrustedFailure("file_missing") from exc
        if not stat.S_ISREG(path_before.st_mode):
            raise TrustedFailure("file_not_regular")

        file_flags = os.O_RDONLY | nofollow_flag | nonblock_flag | close_on_exec
        try:
            file_descriptor = os.open(leaf, file_flags, dir_fd=descriptor)
        except OSError as exc:
            raise TrustedFailure("file_open_failed") from exc
        try:
            metadata_before = os.fstat(file_descriptor)
            if not stat.S_ISREG(metadata_before.st_mode):
                raise TrustedFailure("file_not_regular")
            content = _read_limited(file_descriptor, limit)
            _stable_file_metadata(
                descriptor,
                leaf,
                file_descriptor,
                path_before,
                metadata_before,
            )
            if len(content) > limit:
                if candidate_size_failure:
                    raise CandidateFailure(
                        "handoff_oversized",
                        candidate_sha256=_sha256_bytes(content),
                        candidate_bytes_read=len(content),
                        candidate_sha256_complete=False,
                    )
                raise TrustedFailure("file_oversized")
            return content
        finally:
            os.close(file_descriptor)
    except CandidateFailure:
        raise
    except TrustedFailure:
        raise
    except OSError as exc:
        raise TrustedFailure("secure_read_failed") from exc
    finally:
        for opened in reversed(descriptors):
            os.close(opened)


def _safe_repository_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CandidateFailure("unsafe_repository_reference")
    if "\\" in value or value.startswith("/") or value.endswith("/"):
        raise CandidateFailure("unsafe_repository_reference")
    raw_parts = value.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts):
        raise CandidateFailure("unsafe_repository_reference")
    if any(part.casefold() == ".secrets" for part in raw_parts):
        raise CandidateFailure("secrets_reference_forbidden")
    path = PurePosixPath(value)
    if path.is_absolute() or path.parts != tuple(raw_parts):
        raise CandidateFailure("unsafe_repository_reference")
    return value


def _trusted_repository_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise TrustedFailure("contract_path_invalid")
    if "\\" in value or value.startswith("/") or value.endswith("/"):
        raise TrustedFailure("contract_path_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TrustedFailure("contract_path_invalid")
    if any(part.casefold() == ".secrets" for part in parts):
        raise TrustedFailure("contract_secrets_path")
    return value


def _candidate_archive_member_name(value: object) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise CandidateFailure("archive_member_path_invalid")
    if "\\" in value or value.startswith("/"):
        raise CandidateFailure("archive_member_path_invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CandidateFailure("archive_member_path_invalid")
    if any(part.casefold() in {".secrets", ".git"} for part in parts):
        raise CandidateFailure("archive_member_secret_path")
    return value


def _trusted_archive_member_name(name: object) -> str:
    if not isinstance(name, str) or not name or "\x00" in name:
        raise TrustedFailure("bundle_member_path_invalid")
    if "\\" in name or name.startswith("/"):
        raise TrustedFailure("bundle_member_path_invalid")
    parts = name.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise TrustedFailure("bundle_member_path_invalid")
    if any(part.casefold() in {".secrets", ".git"} for part in parts):
        raise TrustedFailure("bundle_member_secrets_path")
    return name


def _read_repository_file(root: Path, relative: str, *, limit: int) -> bytes:
    safe = _trusted_repository_relative(relative)
    try:
        return _secure_read_absolute(root / Path(*safe.split("/")), limit=limit)
    except CandidateFailure as exc:
        raise TrustedFailure(exc.code) from exc


def _scan_yaml_safety(text: str, *, candidate: bool) -> None:
    try:
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                code = "yaml_alias_or_anchor" if candidate else "trusted_yaml_alias"
                raise (CandidateFailure if candidate else TrustedFailure)(code)
            if isinstance(token, TagToken):
                code = "yaml_tag_forbidden" if candidate else "trusted_yaml_tag"
                raise (CandidateFailure if candidate else TrustedFailure)(code)
    except CandidateFailure:
        raise
    except TrustedFailure:
        raise
    except Exception as exc:
        code = "yaml_scan_failed" if candidate else "trusted_yaml_scan_failed"
        raise (CandidateFailure if candidate else TrustedFailure)(code) from exc


def _check_yaml_complexity(value: object, *, depth_limit: int, node_limit: int) -> None:
    stack: list[tuple[object, int]] = [(value, 0)]
    count = 0
    while stack:
        current, depth = stack.pop()
        count += 1
        if count > node_limit:
            raise CandidateFailure("yaml_node_limit")
        if depth > depth_limit:
            raise CandidateFailure("yaml_depth_limit")
        if isinstance(current, Mapping):
            for key, item in current.items():
                if not isinstance(key, str):
                    raise CandidateFailure("yaml_mapping_key_not_string")
                stack.append((item, depth + 1))
                stack.append((key, depth + 1))
        elif isinstance(current, list):
            for item in reversed(current):
                stack.append((item, depth + 1))


def _load_yaml_mapping(
    content: bytes,
    *,
    candidate: bool,
    depth_limit: int,
    node_limit: int,
) -> dict[str, Any]:
    if b"\x00" in content:
        code = "yaml_nul_byte" if candidate else "trusted_yaml_nul_byte"
        raise (CandidateFailure if candidate else TrustedFailure)(code)
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        code = "yaml_non_utf8" if candidate else "trusted_yaml_non_utf8"
        raise (CandidateFailure if candidate else TrustedFailure)(code) from exc
    _scan_yaml_safety(text, candidate=candidate)
    if type(depth_limit) is not int or depth_limit <= 0:
        raise (CandidateFailure if candidate else TrustedFailure)(
            "yaml_depth_limit_invalid"
            if candidate
            else "trusted_yaml_depth_limit_invalid"
        )
    if type(node_limit) is not int or node_limit <= 0:
        raise (CandidateFailure if candidate else TrustedFailure)(
            "yaml_node_limit_invalid"
            if candidate
            else "trusted_yaml_node_limit_invalid"
        )
    loader = UniqueKeyLoader(
        text,
        depth_limit=depth_limit,
        node_limit=node_limit,
        candidate=candidate,
    )
    documents: list[object] = []
    try:
        while loader.check_data():
            if documents:
                code = (
                    "yaml_multiple_documents"
                    if candidate
                    else "trusted_yaml_multiple_documents"
                )
                raise (CandidateFailure if candidate else TrustedFailure)(code)
            documents.append(loader.get_data())
    except CandidateFailure:
        raise
    except TrustedFailure:
        raise
    except Exception as exc:
        code = "yaml_parse_failed" if candidate else "trusted_yaml_parse_failed"
        raise (CandidateFailure if candidate else TrustedFailure)(code) from exc
    finally:
        loader.dispose()
    if len(documents) != 1:
        code = (
            "yaml_multiple_documents"
            if candidate
            else "trusted_yaml_multiple_documents"
        )
        raise (CandidateFailure if candidate else TrustedFailure)(code)
    document = documents[0]
    if not isinstance(document, dict):
        code = "yaml_root_not_mapping" if candidate else "trusted_yaml_root_not_mapping"
        raise (CandidateFailure if candidate else TrustedFailure)(code)
    try:
        _check_yaml_complexity(
            document,
            depth_limit=depth_limit,
            node_limit=node_limit,
        )
    except CandidateFailure as exc:
        if candidate:
            raise
        raise TrustedFailure(f"trusted_{exc.code}") from exc
    return document


def _load_json_object(content: bytes, *, trusted_code: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustedFailure(trusted_code) from exc
    if not isinstance(value, dict):
        raise TrustedFailure(trusted_code)
    return value


def _mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateFailure(code)
    return value


def _trusted_mapping(value: object, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrustedFailure(code)
    return value


def _sequence(value: object, code: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise CandidateFailure(code)
    return value


def _trusted_sequence(value: object, code: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TrustedFailure(code)
    return value


def _string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CandidateFailure(code)
    return value


def _trusted_string(value: object, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TrustedFailure(code)
    return value


def _nonempty(value: object) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return bool(value)
    return value is not None


def _nonempty_string_list(value: object, code: str) -> list[str]:
    rows = _sequence(value, code)
    result: list[str] = []
    for item in rows:
        result.append(_string(item, code))
    if not result:
        raise CandidateFailure(code)
    return result


def _path_get(value: object, path: str) -> object:
    current = value
    for component in path.split("."):
        if not isinstance(current, Mapping) or component not in current:
            raise CandidateFailure("candidate_structure_invalid")
        current = current[component]
    return current


def _read_contract(root: Path) -> dict[str, Any]:
    content = _read_repository_file(
        root,
        CONTRACT_PATH.as_posix(),
        limit=MAX_HARD_READ_BYTES,
    )
    if _sha256_bytes(content) != EXPECTED_CONTRACT_SHA256:
        raise TrustedFailure("validator_contract_digest_mismatch")
    contract = _load_yaml_mapping(
        content,
        candidate=False,
        depth_limit=64,
        node_limit=100000,
    )
    document = _trusted_mapping(contract.get("document"), "validator_contract_document")
    if document.get("story_id") != "ST-0308":
        raise TrustedFailure("validator_contract_story_mismatch")
    if document.get("status") != "LOCAL_AUTOMATED_PREFLIGHT_ONLY":
        raise TrustedFailure("validator_contract_status_mismatch")
    if document.get("authority") != "NOT_IMPLEMENTATION_AUTHORITY":
        raise TrustedFailure("validator_contract_authority_mismatch")
    if document.get("semantic_authority") != "MANUAL_ONLY":
        raise TrustedFailure("validator_contract_semantic_authority_mismatch")

    limits = _trusted_mapping(contract.get("limits"), "contract_limits")
    for name in (
        "handoff_bytes",
        "repository_text_bytes",
        "sql_fragment_bytes",
        "archive_bytes",
        "yaml_depth",
        "yaml_nodes",
        "archive_member_bytes",
        "archive_uncompressed_regular_bytes",
    ):
        value = limits.get(name)
        if type(value) is not int or value <= 0:
            raise TrustedFailure("contract_limit_invalid")
        if name not in {"yaml_depth", "yaml_nodes"} and value > MAX_HARD_READ_BYTES:
            raise TrustedFailure("contract_limit_too_large")
    if limits["handoff_bytes"] > MAX_HANDOFF_BYTES:
        raise TrustedFailure("contract_handoff_limit_too_large")
    _validate_approval_boundary(contract)
    return contract


def _reference_rows(
    contract: Mapping[str, Any],
    *,
    include_trusted_v2_bundle_sources: bool,
) -> list[Mapping[str, Any]]:
    source = _trusted_mapping(contract.get("source_inputs"), "contract_source_inputs")
    rows = list(
        _trusted_sequence(
            source.get("required_repository_refs"),
            "contract_required_refs",
        )
    )
    if include_trusted_v2_bundle_sources:
        rows.extend(
            _trusted_sequence(
                source.get("trusted_v2_bundle_source_refs"),
                "contract_trusted_v2_bundle_refs",
            )
        )
    rows.extend(
        _trusted_sequence(
            source.get("required_st0304_physical_fragments"),
            "contract_physical_refs",
        )
    )
    result: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        mapping = _trusted_mapping(row, "contract_reference_row")
        path = _trusted_repository_relative(mapping.get("path"))
        digest = _trusted_string(mapping.get("sha256"), "contract_reference_hash")
        if not SHA256_PATTERN.fullmatch(digest):
            raise TrustedFailure("contract_reference_hash_invalid")
        if path in seen:
            raise TrustedFailure("contract_reference_duplicate")
        seen.add(path)
        result.append(mapping)
    return result


def _required_reference_rows(contract: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _reference_rows(contract, include_trusted_v2_bundle_sources=True)


def _candidate_required_reference_rows(
    contract: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    return _reference_rows(contract, include_trusted_v2_bundle_sources=False)


def _required_archive_member_rows(
    contract: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    source = _trusted_mapping(contract.get("source_inputs"), "contract_source_inputs")
    rows = _trusted_sequence(
        source.get("required_archive_members"),
        "contract_archive_member_requirements",
    )
    result: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in rows:
        row = _trusted_mapping(item, "contract_archive_member_row")
        archive_path = _trusted_repository_relative(row.get("archive_path"))
        archive_hash = _trusted_string(
            row.get("archive_sha256"),
            "contract_archive_hash_invalid",
        )
        member_path = _trusted_archive_member_name(row.get("member_path"))
        member_hash = _trusted_string(
            row.get("member_sha256"),
            "contract_member_hash_invalid",
        )
        if not SHA256_PATTERN.fullmatch(archive_hash) or not SHA256_PATTERN.fullmatch(
            member_hash
        ):
            raise TrustedFailure("contract_archive_member_hash_invalid")
        identity = (archive_path, member_path)
        if identity in seen:
            raise TrustedFailure("contract_archive_member_duplicate")
        seen.add(identity)
        result.append(row)
    if not result:
        raise TrustedFailure("contract_archive_member_requirements_empty")
    return result


def _required_hash_map(contract: Mapping[str, Any]) -> dict[str, str]:
    return {
        _trusted_repository_relative(row.get("path")): _trusted_string(
            row.get("sha256"),
            "contract_reference_hash",
        )
        for row in _required_reference_rows(contract)
    }


def _candidate_required_hash_map(contract: Mapping[str, Any]) -> dict[str, str]:
    return {
        _trusted_repository_relative(row.get("path")): _trusted_string(
            row.get("sha256"),
            "contract_reference_hash",
        )
        for row in _candidate_required_reference_rows(contract)
    }


def _trusted_v2_bundle_source_hash_map(
    contract: Mapping[str, Any],
) -> dict[str, str]:
    source = _trusted_mapping(contract.get("source_inputs"), "contract_source_inputs")
    if source.get("trusted_v2_bundle_source_reference_policy") != (
        "INTERNAL_BUNDLE_VALIDATION_ONLY_DIRECT_CANDIDATE_REFERENCE_FORBIDDEN"
    ):
        raise TrustedFailure("contract_trusted_v2_bundle_policy_invalid")
    rows = _trusted_sequence(
        source.get("trusted_v2_bundle_source_refs"),
        "contract_trusted_v2_bundle_refs",
    )
    return {
        _trusted_repository_relative(row.get("path")): _trusted_string(
            row.get("sha256"),
            "contract_reference_hash",
        )
        for item in rows
        for row in (_trusted_mapping(item, "contract_reference_row"),)
    }


def _sha_for_path(contract: Mapping[str, Any], path: str) -> str:
    try:
        return _required_hash_map(contract)[path]
    except KeyError as exc:
        raise TrustedFailure("contract_required_hash_missing") from exc


def _limit_for_path(contract: Mapping[str, Any], path: str) -> int:
    limits = _trusted_mapping(contract.get("limits"), "contract_limits")
    source = _trusted_mapping(contract.get("source_inputs"), "contract_source_inputs")
    fragments = {
        _trusted_repository_relative(row.get("path"))
        for row in _trusted_sequence(
            source.get("required_st0304_physical_fragments"),
            "contract_physical_refs",
        )
        for row in (_trusted_mapping(row, "contract_fragment_row"),)
    }
    bundle = _trusted_mapping(contract.get("v2_bundle"), "contract_v2_bundle")
    archive_path = _trusted_repository_relative(bundle.get("archive_path"))
    if path in fragments:
        return int(limits["sql_fragment_bytes"])
    if path == archive_path:
        return int(limits["archive_bytes"])
    return int(limits["repository_text_bytes"])


def _read_archive_member_limited(
    stream: Any,
    declared_size: int,
    *,
    limit: int,
) -> bytes:
    """Read one regular archive member without exceeding its independent cap."""

    if type(declared_size) is not int or declared_size < 0:
        raise TrustedFailure("bundle_member_size_invalid")
    if type(limit) is not int or limit <= 0 or limit > MAX_HARD_READ_BYTES:
        raise TrustedFailure("bundle_member_limit_invalid")
    if declared_size > limit:
        raise TrustedFailure("bundle_member_oversized")
    try:
        data = stream.read(limit + 1)
    except (OSError, ValueError, AttributeError) as exc:
        raise TrustedFailure("bundle_member_unreadable") from exc
    if not isinstance(data, bytes):
        raise TrustedFailure("bundle_member_unreadable")
    if len(data) > limit or len(data) != declared_size:
        raise TrustedFailure("bundle_member_read_limit")
    return data


def _advance_archive_regular_bytes(
    current: int,
    member_size: int,
    *,
    limit: int,
) -> int:
    """Apply the cumulative regular-file cap independently of member reads."""

    if type(current) is not int or current < 0:
        raise TrustedFailure("bundle_regular_bytes_state_invalid")
    if type(member_size) is not int or member_size < 0:
        raise TrustedFailure("bundle_member_size_invalid")
    if type(limit) is not int or limit <= 0 or limit > MAX_HARD_READ_BYTES:
        raise TrustedFailure("bundle_cumulative_limit_invalid")
    if current > limit or member_size > limit - current:
        raise TrustedFailure("bundle_uncompressed_regular_bytes_limit")
    return current + member_size


def _validate_archive_member_kind(member: tarfile.TarInfo) -> None:
    if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
        raise TrustedFailure("bundle_special_member")


def _validate_v2_bundle(
    contract: Mapping[str, Any],
    contents: Mapping[str, bytes],
) -> dict[str, Any]:
    bundle = _trusted_mapping(contract.get("v2_bundle"), "contract_v2_bundle")
    limits = _trusted_mapping(contract.get("limits"), "contract_limits")
    manifest_path = _trusted_repository_relative(bundle.get("manifest_path"))
    archive_path = _trusted_repository_relative(bundle.get("archive_path"))
    file_list_path = _trusted_repository_relative(bundle.get("file_list_path"))
    manifest = _load_yaml_mapping(
        contents[manifest_path],
        candidate=False,
        depth_limit=int(limits["yaml_depth"]),
        node_limit=int(limits["yaml_nodes"]),
    )
    document = _trusted_mapping(manifest.get("document"), "bundle_document")
    if document.get("story_id") != "ST-0308":
        raise TrustedFailure("bundle_story_mismatch")
    if document.get("authority") != "NOT_A_DESIGN_HANDOFF":
        raise TrustedFailure("bundle_authority_mismatch")

    source = _trusted_mapping(manifest.get("source"), "bundle_source")
    expected_source = {
        "correction_request": "changes/st-0308/PRO-CORRECTION-REQUEST-v2.md",
        "reconciliation": "changes/st-0308/CANONICAL-RECONCILIATION-v2.md",
        "file_list": file_list_path,
        "cumulative_contract_repository": "contracts/raos-v0.4/contract-repository.v0.4.json",
        "st0105_generated_ownership_manifest": "changes/st-0105/manifest.json",
        "canonical_read_order": "docs/canonical/00_master/RAOS_MASTER_README_v1.0.md",
        "canonical_open_decisions": "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
    }
    for field, expected_path in expected_source.items():
        item = _trusted_mapping(source.get(field), "bundle_source_field")
        if item.get("path") != expected_path:
            raise TrustedFailure("bundle_source_path_mismatch")
        digest = item.get("sha256")
        if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
            raise TrustedFailure("bundle_source_hash_invalid")
        if digest != _sha_for_path(contract, expected_path):
            raise TrustedFailure("bundle_source_hash_mismatch")

    approved = _trusted_mapping(
        source.get("approved_but_rejected_handoff"),
        "bundle_approved_input_metadata",
    )
    approved_member = _trusted_string(
        bundle.get("approved_input_member"),
        "contract_approved_member_invalid",
    )
    approved_hash = _trusted_string(
        bundle.get("approved_input_sha256"),
        "contract_approved_hash_invalid",
    )
    if not SHA256_PATTERN.fullmatch(approved_hash):
        raise TrustedFailure("contract_approved_hash_invalid")
    if approved.get("archive_path") != approved_member:
        raise TrustedFailure("bundle_approved_member_metadata_mismatch")
    if approved.get("sha256") != approved_hash:
        raise TrustedFailure("bundle_approved_hash_metadata_mismatch")
    owner_hash = approved.get("owner_approval_statement_sha256")
    if not isinstance(owner_hash, str) or not SHA256_PATTERN.fullmatch(owner_hash):
        raise TrustedFailure("bundle_owner_approval_hash_invalid")
    expected_source_path = _trusted_string(
        bundle.get("approved_input_source_path"),
        "contract_approved_source_path_invalid",
    )
    expected_owner_hash = _trusted_string(
        bundle.get("owner_approval_statement_sha256"),
        "contract_owner_approval_hash_invalid",
    )
    if not SHA256_PATTERN.fullmatch(expected_owner_hash):
        raise TrustedFailure("contract_owner_approval_hash_invalid")
    if approved.get("source_path") != expected_source_path:
        raise TrustedFailure("bundle_approved_source_path_mismatch")
    if owner_hash != expected_owner_hash:
        raise TrustedFailure("bundle_owner_approval_hash_mismatch")
    if approved.get("activation_result") != "MATERIAL_CONFLICT_REQUIRES_REAPPROVAL":
        raise TrustedFailure("bundle_activation_boundary_mismatch")
    required_members = _required_archive_member_rows(contract)
    for row in required_members:
        if (
            row.get("archive_path") != archive_path
            or row.get("archive_sha256") != _sha_for_path(contract, archive_path)
            or row.get("member_path") != approved_member
            or row.get("member_sha256") != approved_hash
        ):
            raise TrustedFailure("contract_approved_member_binding_mismatch")

    output = _trusted_mapping(manifest.get("output"), "bundle_output")
    if output.get("path") != archive_path:
        raise TrustedFailure("bundle_archive_path_mismatch")
    archive_digest = output.get("sha256")
    if archive_digest != _sha_for_path(contract, archive_path):
        raise TrustedFailure("bundle_archive_hash_mismatch")
    if output.get("bytes") != len(contents[archive_path]):
        raise TrustedFailure("bundle_archive_size_mismatch")
    if output.get("members") != bundle.get("expected_member_count"):
        raise TrustedFailure("bundle_member_count_metadata_mismatch")
    if output.get("regular_files") != bundle.get("expected_regular_file_count"):
        raise TrustedFailure("bundle_regular_count_metadata_mismatch")
    if output.get("directories") != bundle.get("expected_directory_count"):
        raise TrustedFailure("bundle_directory_count_metadata_mismatch")

    try:
        list_text = contents[file_list_path].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrustedFailure("bundle_file_list_non_utf8") from exc
    if "\x00" in list_text:
        raise TrustedFailure("bundle_file_list_nul_byte")
    listed = [line for line in list_text.splitlines() if line]
    if (
        len(listed) != int(bundle.get("expected_file_list_entries", -1))
        or len(listed) != 33
        or len(set(listed)) != len(listed)
    ):
        raise TrustedFailure("bundle_file_list_invalid")
    for name in listed:
        _trusted_archive_member_name(name)

    member_hashes: dict[str, str] = {}
    regular_member_bytes = 0
    try:
        member_limit = int(limits["archive_member_bytes"])
        regular_member_limit = int(limits["archive_uncompressed_regular_bytes"])
        expected_regular_count = int(bundle.get("expected_regular_file_count", -1))
        if regular_member_limit >= expected_regular_count * member_limit:
            raise TrustedFailure("bundle_cumulative_limit_not_below_member_aggregate")
        with tarfile.open(
            fileobj=io.BytesIO(contents[archive_path]),
            mode="r:gz",
        ) as archive:
            members = archive.getmembers()
            if len(members) != int(bundle.get("expected_member_count", -1)):
                raise TrustedFailure("bundle_member_count_mismatch")
            regular = sum(member.isfile() for member in members)
            directories = sum(member.isdir() for member in members)
            if regular != int(bundle.get("expected_regular_file_count", -1)):
                raise TrustedFailure("bundle_regular_file_count_mismatch")
            if directories != int(bundle.get("expected_directory_count", -1)):
                raise TrustedFailure("bundle_directory_count_mismatch")
            names: set[str] = set()
            for member in members:
                name = _trusted_archive_member_name(member.name)
                if name in names:
                    raise TrustedFailure("bundle_duplicate_member")
                names.add(name)
                _validate_archive_member_kind(member)
                if member.size > member_limit:
                    raise TrustedFailure("bundle_member_oversized")
                if member.isfile():
                    regular_member_bytes = _advance_archive_regular_bytes(
                        regular_member_bytes,
                        member.size,
                        limit=regular_member_limit,
                    )
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise TrustedFailure("bundle_member_unreadable")
                    data = _read_archive_member_limited(
                        extracted,
                        member.size,
                        limit=member_limit,
                    )
                    member_hashes[name] = _sha256_bytes(data)
            if not set(listed).issubset(names):
                raise TrustedFailure("bundle_file_list_member_missing")
    except TrustedFailure:
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise TrustedFailure("bundle_archive_invalid") from exc

    if approved_member not in member_hashes:
        raise TrustedFailure("bundle_approved_input_missing")
    if member_hashes[approved_member] != approved_hash:
        raise TrustedFailure("bundle_approved_input_hash_mismatch")
    return {
        "archive_path": archive_path,
        "archive_sha256": archive_digest,
        "approved_input_member": approved_member,
        "approved_input_sha256": approved_hash,
        "member_hashes": member_hashes,
        "regular_member_bytes": regular_member_bytes,
    }


def _validate_st0104_manifest(
    contract: Mapping[str, Any],
    contents: Mapping[str, bytes],
    root: Path,
) -> None:
    path = "contracts/raos-v0.4/contract-repository.v0.4.json"
    manifest = _load_json_object(
        contents[path],
        trusted_code="st0104_manifest_invalid_json",
    )
    document = _trusted_mapping(manifest.get("document"), "st0104_document_invalid")
    if document.get("story_id") != "ST-0104":
        raise TrustedFailure("st0104_story_mismatch")
    inventory = _trusted_mapping(manifest.get("inventory"), "st0104_inventory_invalid")
    if inventory.get("path_base") != "contracts/raos-v0.4":
        raise TrustedFailure("st0104_path_base_mismatch")
    if inventory.get("path_traversal_casefold_symlink_special_file_checks") is not True:
        raise TrustedFailure("st0104_safety_boundary_missing")
    resolution = _trusted_mapping(
        manifest.get("schema_resolution"),
        "st0104_schema_resolution_invalid",
    )
    aliases = _trusted_sequence(
        resolution.get("retrieval_uri_aliases"),
        "st0104_aliases_invalid",
    )
    if resolution.get("alias_count") != 6 or len(aliases) != 6:
        raise TrustedFailure("st0104_alias_count_mismatch")
    if resolution.get("network_retrieval") != "FORBIDDEN":
        raise TrustedFailure("st0104_network_boundary_mismatch")

    artifacts = _trusted_sequence(
        manifest.get("artifacts"),
        "st0104_artifacts_invalid",
    )
    if manifest.get("artifact_count") != 306 or len(artifacts) != 306:
        raise TrustedFailure("st0104_artifact_count_mismatch")
    seen: set[str] = set()
    for artifact in artifacts:
        row = _trusted_mapping(artifact, "st0104_artifact_row_invalid")
        artifact_path = _trusted_repository_relative(row.get("path"))
        if artifact_path in seen:
            raise TrustedFailure("st0104_duplicate_artifact")
        seen.add(artifact_path)
        digest = _trusted_string(row.get("sha256"), "st0104_artifact_hash_invalid")
        if not SHA256_PATTERN.fullmatch(digest):
            raise TrustedFailure("st0104_artifact_hash_invalid")
        byte_count = row.get("bytes")
        if type(byte_count) is not int or byte_count < 0:
            raise TrustedFailure("st0104_artifact_size_invalid")
        installed_path = f"contracts/raos-v0.4/{artifact_path}"
        artifact_content = _read_repository_file(
            root,
            installed_path,
            limit=int(
                _trusted_mapping(contract.get("limits"), "contract_limits")[
                    "repository_text_bytes"
                ]
            ),
        )
        if (
            len(artifact_content) != byte_count
            or _sha256_bytes(artifact_content) != digest
        ):
            raise TrustedFailure("st0104_artifact_hash_mismatch")


def _find_create_table_end(text: str, start: int) -> int:
    depth = 1
    state = "normal"
    index = start
    while index < len(text):
        char = text[index]
        if state == "single":
            if char == "\\":
                index += 2
                continue
            if char == "'":
                if index + 1 < len(text) and text[index + 1] == "'":
                    index += 2
                    continue
                state = "normal"
        elif state == "double":
            if char == '"':
                if index + 1 < len(text) and text[index + 1] == '"':
                    index += 2
                    continue
                state = "normal"
        else:
            if char == "'":
                state = "single"
            elif char == '"':
                state = "double"
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return index
        index += 1
    raise TrustedFailure("create_table_block_incomplete")


def _reconstruct_physical_inventory(
    contract: Mapping[str, Any],
    contents: Mapping[str, bytes],
) -> dict[str, Any]:
    physical = _trusted_mapping(
        contract.get("physical_reconstruction"),
        "contract_physical_reconstruction",
    )
    catalog_path = _trusted_repository_relative(physical.get("st0303_catalog_path"))
    st0303 = _load_json_object(
        contents[catalog_path],
        trusted_code="st0303_catalog_invalid_json",
    )
    tables = _trusted_sequence(st0303.get("tables"), "st0303_catalog_tables_invalid")
    if len(tables) != int(physical.get("st0303_table_count", -1)):
        raise TrustedFailure("st0303_table_count_mismatch")
    names: list[str] = []
    locks: set[str] = set()
    for item in tables:
        row = _trusted_mapping(item, "st0303_catalog_table_invalid")
        relation = _trusted_string(
            row.get("fully_qualified_name"),
            "st0303_relation_invalid",
        )
        if relation.count(".") != 1 or relation in names:
            raise TrustedFailure("st0303_relation_set_invalid")
        names.append(relation)
        columns = _trusted_sequence(row.get("columns"), "st0303_columns_invalid")
        column_names: set[str] = set()
        for column in columns:
            column_row = _trusted_mapping(column, "st0303_column_invalid")
            column_name = _trusted_string(
                column_row.get("name"),
                "st0303_column_name_invalid",
            )
            if column_name in column_names:
                raise TrustedFailure("st0303_duplicate_column")
            column_names.add(column_name)
            if column_name == "lock_version":
                locks.add(relation)

    source = _trusted_mapping(contract.get("source_inputs"), "contract_source_inputs")
    fragment_rows = _trusted_sequence(
        source.get("required_st0304_physical_fragments"),
        "contract_physical_refs",
    )
    if len(fragment_rows) != int(physical.get("st0304_fragment_count", -1)):
        raise TrustedFailure("st0304_fragment_count_mismatch")
    create_table_pattern = re.compile(
        r'CREATE TABLE "([^"]+)"\."([^"]+)" \(\n',
        re.MULTILINE,
    )
    st0304_count = 0
    for row in fragment_rows:
        fragment = _trusted_mapping(row, "contract_fragment_row")
        fragment_path = _trusted_repository_relative(fragment.get("path"))
        try:
            text = contents[fragment_path].decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrustedFailure("physical_fragment_non_utf8") from exc
        matches = list(create_table_pattern.finditer(text))
        for match in matches:
            end = _find_create_table_end(text, match.end())
            tail = text[end + 1 :].lstrip()
            if not tail.startswith(";"):
                raise TrustedFailure("create_table_block_terminator_invalid")
            schema, table = match.groups()
            relation = f"{schema}.{table}"
            if relation in names:
                raise TrustedFailure("physical_relation_duplicate")
            names.append(relation)
            st0304_count += 1
            body = text[match.end() : end]
            if re.search(r'^    "lock_version"\s+', body, re.MULTILINE):
                locks.add(relation)
    if st0304_count != int(physical.get("st0304_table_count", -1)):
        raise TrustedFailure("st0304_table_count_mismatch")
    if len(names) != int(physical.get("table_count", -1)):
        raise TrustedFailure("physical_table_count_mismatch")

    domain_catalog = _load_json_object(
        contents["changes/st-0304/generated/domain-catalog.v1.json"],
        trusted_code="st0304_catalog_invalid_json",
    )
    object_inventory = _trusted_mapping(
        domain_catalog.get("object_inventory"),
        "st0304_object_inventory_invalid",
    )
    objects = _trusted_sequence(
        object_inventory.get("objects"),
        "st0304_objects_invalid",
    )
    views = sorted(
        f"{row.get('schema')}.{row.get('name')}"
        for item in objects
        if isinstance(item, Mapping) and item.get("type") == "VIEW"
        for row in (item,)
    )
    if views != list(physical.get("view_relations", ())):
        raise TrustedFailure("physical_view_set_mismatch")
    normalized = (
        "ST0308_PHYSICAL_INVENTORY_V1\n"
        f"postgresql_server_version_num={physical.get('server_version_num')}\n"
        + "".join(f"TABLE\t{relation}\n" for relation in sorted(names))
        + "".join(f"VIEW\t{relation}\n" for relation in views)
    ).encode("utf-8")
    inventory_digest = _sha256_bytes(normalized)
    if inventory_digest != physical.get("normalized_inventory_sha256"):
        raise TrustedFailure("physical_inventory_digest_mismatch")
    expected_locks = sorted(
        str(item) for item in physical.get("lock_version_relations", ())
    )
    if len(expected_locks) != len(set(expected_locks)):
        raise TrustedFailure("contract_lock_version_set_duplicate")
    if sorted(locks) != expected_locks:
        raise TrustedFailure("physical_lock_version_set_mismatch")

    expected_state_rows = _trusted_sequence(
        physical.get("non_version_state_cas_required"),
        "contract_state_cas_set_invalid",
    )
    expected_state_relations = [
        _trusted_string(item, "contract_state_cas_relation_invalid")
        for item in expected_state_rows
    ]
    if any(relation.count(".") != 1 for relation in expected_state_relations):
        raise TrustedFailure("contract_state_cas_relation_invalid")
    if len(expected_state_relations) != len(set(expected_state_relations)):
        raise TrustedFailure("contract_state_cas_set_duplicate")
    state_relations = frozenset(expected_state_relations)
    physical_relations = frozenset(names)
    if not state_relations <= physical_relations:
        raise TrustedFailure("contract_state_cas_outside_physical_set")
    if state_relations & locks:
        raise TrustedFailure("contract_state_cas_overlaps_lock_version_set")
    return {
        "tables": len(names),
        "views": len(views),
        "inventory_sha256": inventory_digest,
        "relations": physical_relations,
        "view_relations": tuple(views),
        "lock_version_relations": frozenset(locks),
        "non_version_state_cas_required": state_relations,
    }


def _load_trusted_environment(
    root: Path,
    contract: Mapping[str, Any],
) -> tuple[dict[str, bytes], dict[str, Any], dict[str, Any]]:
    contents: dict[str, bytes] = {}
    for row in _required_reference_rows(contract):
        path = _trusted_repository_relative(row.get("path"))
        digest = _trusted_string(row.get("sha256"), "contract_reference_hash")
        content = _read_repository_file(
            root,
            path,
            limit=_limit_for_path(contract, path),
        )
        contents[path] = content
        if _sha256_bytes(content) != digest:
            raise TrustedFailure("pinned_repository_input_hash_mismatch")
    bundle = _validate_v2_bundle(contract, contents)
    _validate_st0104_manifest(contract, contents, root)
    physical = _reconstruct_physical_inventory(contract, contents)
    return contents, physical, bundle


def _walk_reference_records(
    value: object,
    location: str = "source_design_refs",
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    if isinstance(value, Mapping):
        keys = {key for key in value if isinstance(key, str)}
        archive_keys = keys & ARCHIVE_REFERENCE_KEYS
        direct_keys = keys & DIRECT_REFERENCE_KEYS
        if archive_keys:
            required = ARCHIVE_REFERENCE_KEYS
            if not required <= keys or direct_keys:
                raise CandidateFailure("archive_reference_ambiguous_or_unbound")
            records.append(
                {
                    "kind": "archive_member",
                    "archive_path": _safe_repository_relative(value["archive_path"]),
                    "archive_sha256": _candidate_hash(
                        value["archive_sha256"],
                        "archive_reference_hash_invalid",
                    ),
                    "member_path": _candidate_archive_member_name(value["member_path"]),
                    "member_sha256": _candidate_hash(
                        value["member_sha256"],
                        "archive_member_hash_invalid",
                    ),
                    "location": location,
                }
            )
        elif direct_keys:
            present = [
                (path_key, hash_key)
                for path_key, hash_key in DIRECT_REFERENCE_PAIRS
                if path_key in keys or hash_key in keys
            ]
            if len(present) != 1:
                raise CandidateFailure("source_reference_ambiguous")
            path_key, hash_key = present[0]
            if path_key not in keys or hash_key not in keys:
                raise CandidateFailure("source_reference_hash_missing")
            records.append(
                {
                    "kind": "repository",
                    "path": _safe_repository_relative(value[path_key]),
                    "sha256": _candidate_hash(
                        value[hash_key],
                        "source_reference_hash_invalid",
                    ),
                    "location": location,
                }
            )
        for key, item in value.items():
            if isinstance(key, str) and key not in (
                *ARCHIVE_REFERENCE_KEYS,
                *DIRECT_REFERENCE_KEYS,
            ):
                records.extend(_walk_reference_records(item, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            records.extend(_walk_reference_records(item, f"{location}[{index}]"))
    return records


def _candidate_hash(value: object, code: str) -> str:
    if not isinstance(value, str) or not SHA256_PATTERN.fullmatch(value):
        raise CandidateFailure(code)
    return value


def _check_source_design_refs(
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
    root: Path,
    bundle: Mapping[str, Any],
) -> None:
    source_refs = payload.get("source_design_refs")
    records = _walk_reference_records(source_refs)
    if not records:
        raise CandidateFailure("source_reference_set_empty")

    required = _candidate_required_hash_map(contract)
    trusted_v2_bundle_sources = _trusted_v2_bundle_source_hash_map(contract)
    observed_repository: set[tuple[str, str]] = set()
    observed_members: set[tuple[str, str, str, str]] = set()
    for record in records:
        if record["kind"] == "repository":
            identity = (record["path"], record["sha256"])
            if identity in observed_repository:
                raise CandidateFailure("source_reference_duplicate")
            observed_repository.add(identity)
            if record["path"] in trusted_v2_bundle_sources:
                raise CandidateFailure(
                    "trusted_bundle_source_direct_reference_forbidden"
                )
            try:
                content = _secure_read_absolute(
                    root / Path(*record["path"].split("/")),
                    limit=_limit_for_path(contract, record["path"]),
                )
            except TrustedFailure as exc:
                raise CandidateFailure("source_reference_untrusted_path") from exc
            if _sha256_bytes(content) != record["sha256"]:
                raise CandidateFailure("source_reference_hash_mismatch")
            expected_hash = required.get(record["path"])
            if expected_hash is not None and expected_hash != record["sha256"]:
                raise CandidateFailure("source_reference_not_pinned")
        else:
            identity = (
                record["archive_path"],
                record["archive_sha256"],
                record["member_path"],
                record["member_sha256"],
            )
            if identity in observed_members:
                raise CandidateFailure("archive_reference_duplicate")
            observed_members.add(identity)
            if (
                record["archive_path"] != bundle["archive_path"]
                or record["archive_sha256"] != bundle["archive_sha256"]
            ):
                raise CandidateFailure("archive_reference_not_pinned")
            member_hash = bundle["member_hashes"].get(record["member_path"])
            if member_hash is None:
                raise CandidateFailure("archive_member_missing_or_not_regular")
            if member_hash != record["member_sha256"]:
                raise CandidateFailure("archive_member_hash_mismatch")

    archive_source = (
        bundle["archive_path"],
        bundle["archive_sha256"],
    )
    for path, digest in required.items():
        direct_match = (path, digest) in observed_repository
        structured_archive_match = path == archive_source[0] and any(
            (record["archive_path"], record["archive_sha256"]) == archive_source
            for record in records
            if record["kind"] == "archive_member"
        )
        if not direct_match and not structured_archive_match:
            raise CandidateFailure("source_reference_minimum_missing")

    required_members = _required_archive_member_rows(contract)
    for row in required_members:
        expected = (
            _trusted_repository_relative(row.get("archive_path")),
            _trusted_string(row.get("archive_sha256"), "contract_archive_hash_invalid"),
            _trusted_archive_member_name(row.get("member_path")),
            _trusted_string(row.get("member_sha256"), "contract_member_hash_invalid"),
        )
        if expected not in observed_members:
            raise CandidateFailure("approved_archive_member_reference_missing")


def _candidate_payload(document: Mapping[str, Any]) -> Mapping[str, Any]:
    if set(document) != {"DESIGN_HANDOFF_V1"}:
        raise CandidateFailure("candidate_root_marker_invalid")
    payload = document.get("DESIGN_HANDOFF_V1")
    if not isinstance(payload, Mapping):
        raise CandidateFailure("candidate_payload_not_mapping")
    return payload


def _normalize_boundary_token(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


_BOUNDARY_FIELDS: Final = (
    "status",
    "implementation_authority",
    "owner_approval",
    "approved_by",
    "approved_at",
    "timestamp",
    "canonical_reconciliation",
)
_BOUNDARY_VALUE_CLASSES: Final = (
    "proposal",
    "pending",
    "blocked",
    "not_granted",
    "not_executed",
)

_BOUNDARY_PATTERN_IDS: Final = frozenset(
    {
        "direct_subject",
        "direct_predicate",
        "direct_status",
        "direct_timestamp",
        "is_subject",
        "is_predicate",
        "subject_status",
        "is_subject_status",
        "predicate_status",
        "is_predicate_status",
        "subject_by",
        "subject_at",
        "subject_timestamp",
        "predicate_by",
        "predicate_at",
        "predicate_timestamp",
        "subject_predicate",
        "subject_is_predicate",
        "is_subject_predicate",
        "predicate_subject",
        "predicate_is_subject",
        "is_predicate_subject",
        "is_subject_is_predicate",
        "is_subject_by",
        "is_subject_at",
        "is_subject_timestamp",
        "is_predicate_by",
        "is_predicate_at",
        "is_predicate_timestamp",
        "subject_predicate_status",
        "subject_is_predicate_status",
        "is_subject_predicate_status",
        "predicate_subject_status",
        "predicate_is_subject_status",
        "is_predicate_subject_status",
        "is_subject_is_predicate_status",
        "subject_predicate_by",
        "subject_predicate_at",
        "subject_predicate_timestamp",
        "subject_is_predicate_by",
        "subject_is_predicate_at",
        "subject_is_predicate_timestamp",
        "is_subject_predicate_by",
        "is_subject_predicate_at",
        "is_subject_predicate_timestamp",
        "predicate_subject_by",
        "predicate_subject_at",
        "predicate_subject_timestamp",
        "predicate_is_subject_by",
        "predicate_is_subject_at",
        "predicate_is_subject_timestamp",
        "is_predicate_subject_by",
        "is_predicate_subject_at",
        "is_predicate_subject_timestamp",
        "is_subject_is_predicate_by",
        "is_subject_is_predicate_at",
        "is_subject_is_predicate_timestamp",
    }
)
_BOUNDARY_GENERATED_ALIAS_HARD_CAP: Final = 8192
_BOUNDARY_TOKEN_PATTERN: Final = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
_BOUNDARY_DENIAL_PREDICATES: Final = frozenset(
    {"approved", "authorized", "authorised", "complete", "completed", "granted"}
)
_BOUNDARY_IS_PATTERNS: Final = frozenset(
    {
        "is_subject",
        "is_predicate",
        "subject_is_predicate",
        "is_subject_predicate",
        "predicate_is_subject",
        "is_predicate_subject",
        "is_subject_is_predicate",
    }
)
_BOUNDARY_REQUIRED_SUBJECT_TOKENS: Final = frozenset(
    {
        "authority",
        "approval",
        "implementation",
        "implementation_authority",
        "owner",
        "owner_approval",
        "canonical_reconciliation",
    }
)
_BOUNDARY_REQUIRED_PREDICATE_TOKENS: Final = frozenset(
    {
        "approval",
        "approved",
        "authorization",
        "authorized",
        "authorisation",
        "authorised",
        "completion",
        "complete",
        "completed",
        "grant",
        "granted",
    }
)


class BoundaryAliasRule(NamedTuple):
    """One normalized boundary key and its complete value policy."""

    field: str
    false_allowed: bool
    pattern_id: str

    @property
    def canonical_field(self) -> str:
        return self.field


class BoundaryRules(NamedTuple):
    """The finite, contract-compiled approval-boundary closure."""

    aliases: dict[str, BoundaryAliasRule]
    section_aliases: frozenset[str]
    value_aliases: dict[str, frozenset[str]]
    allowed_value_classes: dict[str, frozenset[str]]


def _contract_token_list(
    mapping: Mapping[str, Any],
    key: str,
    code: str = "contract_boundary_tokens_invalid",
) -> tuple[str, ...]:
    values = _trusted_sequence(mapping.get(key), code)
    if not values:
        raise TrustedFailure("contract_boundary_tokens_empty")
    result: list[str] = []
    for value in values:
        token = _trusted_string(value, code)
        if not _BOUNDARY_TOKEN_PATTERN.fullmatch(token):
            raise TrustedFailure("contract_boundary_token_invalid")
        if token in result:
            raise TrustedFailure("contract_boundary_token_duplicate")
        result.append(token)
    return tuple(result)


def _boundary_rule_field(
    token: str,
    subject_fields: Mapping[str, str],
    predicate_tokens: frozenset[str],
) -> str:
    if token in subject_fields:
        return subject_fields[token]
    if token in predicate_tokens:
        return "status"
    raise TrustedFailure("contract_boundary_subject_field_missing")


def _boundary_false_policy(pattern_id: str, predicate: str | None) -> bool:
    if pattern_id.endswith(("_status", "_by", "_at", "_timestamp")):
        return False
    if pattern_id == "is_predicate" and predicate == "status":
        return False
    if pattern_id in _BOUNDARY_IS_PATTERNS:
        return True
    if pattern_id in {
        "direct_predicate",
        "subject_predicate",
        "predicate_subject",
    }:
        return predicate in _BOUNDARY_DENIAL_PREDICATES
    return False


def _compile_boundary_aliases(
    contract: Mapping[str, Any],
) -> dict[str, BoundaryAliasRule]:
    """Compile the bounded declarative grammar into one alias-rule map."""

    candidate = _trusted_mapping(contract.get("candidate"), "contract_candidate")
    boundary = _trusted_mapping(
        candidate.get("approval_boundary"), "contract_approval_boundary"
    )
    fields = _trusted_sequence(
        boundary.get("canonical_fields"), "contract_boundary_canonical_fields"
    )
    canonical_fields = {
        _trusted_string(value, "contract_boundary_canonical_field_invalid")
        for value in fields
    }
    if canonical_fields != set(_BOUNDARY_FIELDS):
        raise TrustedFailure("contract_boundary_canonical_field_set_invalid")

    subject_fields_raw = _trusted_mapping(
        boundary.get("subject_field_bindings"),
        "contract_boundary_subject_field_bindings",
    )
    subject_fields: dict[str, str] = {}
    for key, value in subject_fields_raw.items():
        if not isinstance(key, str) or not _BOUNDARY_TOKEN_PATTERN.fullmatch(key):
            raise TrustedFailure("contract_boundary_token_invalid")
        field = _trusted_string(value, "contract_boundary_subject_field_invalid")
        if field not in canonical_fields:
            raise TrustedFailure("contract_boundary_subject_field_invalid")
        subject_fields[key] = field
    grammar = _trusted_mapping(
        boundary.get("finite_alias_grammar"),
        "contract_boundary_grammar_invalid",
    )
    raw_patterns = _trusted_sequence(
        grammar.get("patterns"), "contract_boundary_patterns_invalid"
    )
    patterns: list[str] = []
    for value in raw_patterns:
        pattern = _trusted_string(value, "contract_boundary_pattern_invalid")
        if pattern not in _BOUNDARY_PATTERN_IDS:
            raise TrustedFailure("contract_boundary_pattern_unknown")
        if pattern in patterns:
            raise TrustedFailure("contract_boundary_pattern_duplicate")
        patterns.append(pattern)
    if set(patterns) != set(_BOUNDARY_PATTERN_IDS):
        raise TrustedFailure("contract_boundary_pattern_set_invalid")

    subject_tokens = _contract_token_list(grammar, "subject_tokens")
    predicate_tokens = _contract_token_list(grammar, "predicate_tokens")
    status_tokens = _contract_token_list(grammar, "status_tokens")
    identity_suffix_tokens = _contract_token_list(grammar, "identity_suffix_tokens")
    time_suffix_tokens = _contract_token_list(grammar, "time_suffix_tokens")
    if not _BOUNDARY_REQUIRED_SUBJECT_TOKENS <= set(subject_tokens):
        raise TrustedFailure("contract_boundary_subject_token_set_invalid")
    if not _BOUNDARY_REQUIRED_PREDICATE_TOKENS <= set(predicate_tokens):
        raise TrustedFailure("contract_boundary_predicate_token_set_invalid")
    if set(status_tokens) != {"status"}:
        raise TrustedFailure("contract_boundary_status_token_set_invalid")
    if set(identity_suffix_tokens) != {"by"}:
        raise TrustedFailure("contract_boundary_identity_token_set_invalid")
    if set(time_suffix_tokens) != {"at", "timestamp"}:
        raise TrustedFailure("contract_boundary_time_token_set_invalid")
    if set(subject_fields) != set(subject_tokens):
        raise TrustedFailure("contract_boundary_subject_field_set_invalid")

    max_generated = grammar.get("max_generated_aliases")
    expected_generated = grammar.get("expected_generated_aliases")
    if (
        type(max_generated) is not int
        or max_generated <= 0
        or max_generated > _BOUNDARY_GENERATED_ALIAS_HARD_CAP
        or type(expected_generated) is not int
        or expected_generated <= 0
        or expected_generated > max_generated
    ):
        raise TrustedFailure("contract_boundary_generated_limit_invalid")

    aliases: dict[str, BoundaryAliasRule] = {}

    def add_alias(
        alias: str,
        field: str,
        false_allowed: bool,
        pattern_id: str,
    ) -> None:
        normalized = _normalize_boundary_token(alias)
        if not normalized:
            raise TrustedFailure("contract_boundary_alias_empty")
        if field not in canonical_fields:
            raise TrustedFailure("contract_boundary_alias_field_invalid")
        rule = BoundaryAliasRule(field, false_allowed, pattern_id)
        previous = aliases.get(normalized)
        if previous is not None:
            if previous.field != field:
                raise TrustedFailure("contract_boundary_alias_collision")
            if previous.false_allowed != false_allowed:
                raise TrustedFailure("contract_boundary_alias_false_policy_conflict")
            return
        aliases[normalized] = rule

    structural_subjects = tuple(subject_tokens)
    predicates = tuple(predicate_tokens)
    predicate_token_set = frozenset(predicate_tokens)
    compound_subjects = tuple(dict.fromkeys((*subject_tokens, *predicate_tokens)))
    non_predicate_subjects = tuple(
        subject for subject in structural_subjects if subject not in predicate_token_set
    )
    binary_shapes: dict[str, tuple[str, str, bool]] = {
        "subject_predicate": ("", "_", False),
        "subject_is_predicate": ("", "_is_", False),
        "is_subject_predicate": ("is_", "_", False),
        "predicate_subject": ("", "_", True),
        "predicate_is_subject": ("", "_is_", True),
        "is_predicate_subject": ("is_", "_", True),
        "is_subject_is_predicate": ("is_", "_is_", False),
    }
    subject_suffix_patterns = {
        "subject_status",
        "is_subject_status",
        "subject_by",
        "subject_at",
        "subject_timestamp",
        "is_subject_by",
        "is_subject_at",
        "is_subject_timestamp",
    }
    predicate_suffix_patterns = {
        "predicate_status",
        "is_predicate_status",
        "predicate_by",
        "predicate_at",
        "predicate_timestamp",
        "is_predicate_by",
        "is_predicate_at",
        "is_predicate_timestamp",
    }
    suffix_fields = {
        "by": "approved_by",
        "at": "approved_at",
        "timestamp": "timestamp",
    }

    def suffix_name(pattern_id: str) -> str:
        suffix = pattern_id.rsplit("_", 1)[-1]
        if suffix == "status":
            if status_tokens != ("status",):
                raise TrustedFailure("contract_boundary_status_token_set_invalid")
        elif suffix == identity_suffix_tokens[0]:
            pass
        elif suffix not in time_suffix_tokens:
            raise TrustedFailure("contract_boundary_suffix_token_missing")
        return suffix

    def field_for_suffix(subject_field: str, suffix: str) -> str:
        if suffix == "status":
            return subject_field
        try:
            return suffix_fields[suffix]
        except KeyError as exc:
            raise TrustedFailure("contract_boundary_suffix_field_missing") from exc

    def add_binary_pattern(pattern_id: str, suffix: str | None = None) -> None:
        prefix, infix, reversed_order = binary_shapes[pattern_id]
        alias_pattern_id = pattern_id if suffix is None else f"{pattern_id}_{suffix}"
        subjects = (
            non_predicate_subjects
            if pattern_id == "predicate_subject" and suffix is None
            else compound_subjects
        )
        for subject in subjects:
            for predicate in predicates:
                if reversed_order:
                    alias = f"{prefix}{predicate}{infix}{subject}"
                else:
                    alias = f"{prefix}{subject}{infix}{predicate}"
                if suffix is not None:
                    alias = f"{alias}_{suffix}"
                subject_field = _boundary_rule_field(
                    subject,
                    subject_fields,
                    predicate_token_set,
                )
                add_alias(
                    alias,
                    field_for_suffix(subject_field, suffix)
                    if suffix is not None
                    else subject_field,
                    _boundary_false_policy(alias_pattern_id, predicate),
                    alias_pattern_id,
                )

    for pattern_id in patterns:
        if pattern_id == "direct_subject":
            for subject in structural_subjects:
                add_alias(
                    subject,
                    _boundary_rule_field(subject, subject_fields, predicate_token_set),
                    False,
                    pattern_id,
                )
        elif pattern_id == "direct_predicate":
            for predicate in predicates:
                add_alias(
                    predicate,
                    "status",
                    _boundary_false_policy(pattern_id, predicate),
                    pattern_id,
                )
        elif pattern_id == "direct_status":
            for token in status_tokens:
                add_alias(token, "status", False, pattern_id)
        elif pattern_id == "direct_timestamp":
            add_alias(
                next(token for token in time_suffix_tokens if token == "timestamp"),
                "timestamp",
                False,
                pattern_id,
            )
        elif pattern_id == "is_subject":
            for subject in compound_subjects:
                add_alias(
                    f"is_{subject}",
                    _boundary_rule_field(subject, subject_fields, predicate_token_set),
                    _boundary_false_policy(pattern_id, None),
                    pattern_id,
                )
        elif pattern_id == "is_predicate":
            for predicate in (*predicates, *status_tokens):
                add_alias(
                    f"is_{predicate}",
                    "status",
                    _boundary_false_policy(pattern_id, predicate),
                    pattern_id,
                )
        elif pattern_id in subject_suffix_patterns:
            prefix = "is_" if pattern_id.startswith("is_subject_") else ""
            suffix = suffix_name(pattern_id)
            for subject in compound_subjects:
                subject_field = _boundary_rule_field(
                    subject,
                    subject_fields,
                    predicate_token_set,
                )
                add_alias(
                    f"{prefix}{subject}_{suffix}",
                    field_for_suffix(subject_field, suffix),
                    False,
                    pattern_id,
                )
        elif pattern_id in predicate_suffix_patterns:
            prefix = "is_" if pattern_id.startswith("is_predicate_") else ""
            suffix = suffix_name(pattern_id)
            for predicate in predicates:
                add_alias(
                    f"{prefix}{predicate}_{suffix}",
                    field_for_suffix("status", suffix),
                    False,
                    pattern_id,
                )
        elif pattern_id in binary_shapes:
            add_binary_pattern(pattern_id)
        elif any(
            pattern_id.endswith(f"_{suffix}")
            for suffix in ("status", "by", "at", "timestamp")
        ):
            suffix = suffix_name(pattern_id)
            base = pattern_id[: -(len(suffix) + 1)]
            if base not in binary_shapes:
                raise TrustedFailure("contract_boundary_pattern_shape_missing")
            add_binary_pattern(base, suffix)
        else:
            raise TrustedFailure("contract_boundary_pattern_shape_missing")

    explicit_aliases = _trusted_sequence(
        boundary.get("explicit_aliases"), "contract_boundary_explicit_aliases"
    )
    if not explicit_aliases:
        raise TrustedFailure("contract_boundary_explicit_aliases_empty")
    for raw_alias in explicit_aliases:
        row = _trusted_mapping(raw_alias, "contract_boundary_explicit_alias_invalid")
        if set(row) != {"alias", "field", "false_allowed"}:
            raise TrustedFailure("contract_boundary_explicit_alias_shape_invalid")
        alias = _trusted_string(row.get("alias"), "contract_boundary_alias_invalid")
        if not _BOUNDARY_TOKEN_PATTERN.fullmatch(alias):
            raise TrustedFailure("contract_boundary_token_invalid")
        field = _trusted_string(
            row.get("field"), "contract_boundary_alias_field_invalid"
        )
        false_allowed = row.get("false_allowed")
        if (
            field not in canonical_fields
            or type(false_allowed) is not bool
            or (false_allowed and field in {"approved_by", "approved_at", "timestamp"})
        ):
            raise TrustedFailure("contract_boundary_explicit_alias_semantics_invalid")
        add_alias(alias, field, false_allowed, "explicit_alias")

    generated_alias_count = sum(
        rule.pattern_id != "explicit_alias" for rule in aliases.values()
    )
    if generated_alias_count > max_generated:
        raise TrustedFailure("contract_boundary_generated_alias_overflow")
    if generated_alias_count != expected_generated:
        raise TrustedFailure("contract_boundary_generated_alias_count_mismatch")
    return aliases


def _approval_boundary_rules(
    contract: Mapping[str, Any],
) -> BoundaryRules:
    candidate = _trusted_mapping(contract.get("candidate"), "contract_candidate")
    boundary = _trusted_mapping(
        candidate.get("approval_boundary"),
        "contract_approval_boundary",
    )
    raw_sections = _trusted_sequence(
        boundary.get("boundary_section_aliases"),
        "contract_boundary_section_aliases",
    )
    section_aliases: set[str] = set()
    for value in raw_sections:
        section = _trusted_string(value, "contract_boundary_section_alias_invalid")
        if not _BOUNDARY_TOKEN_PATTERN.fullmatch(section):
            raise TrustedFailure("contract_boundary_section_alias_invalid")
        normalized = _normalize_boundary_token(section)
        if not normalized or normalized in section_aliases:
            raise TrustedFailure("contract_boundary_section_alias_collision")
        section_aliases.add(normalized)
    if not section_aliases:
        raise TrustedFailure("contract_boundary_section_aliases_empty")
    raw_values = _trusted_mapping(
        boundary.get("value_aliases"),
        "contract_boundary_value_aliases",
    )
    if set(raw_values) != set(_BOUNDARY_VALUE_CLASSES):
        raise TrustedFailure("contract_boundary_value_alias_set_invalid")
    value_aliases: dict[str, frozenset[str]] = {}
    value_alias_owners: dict[str, str] = {}
    for value_class in _BOUNDARY_VALUE_CLASSES:
        values = _trusted_sequence(
            raw_values.get(value_class),
            "contract_boundary_value_aliases_invalid",
        )
        normalized_values: set[str] = set()
        for value in values:
            normalized = _normalize_boundary_token(
                _trusted_string(value, "contract_boundary_value_alias_invalid")
            )
            if not normalized:
                raise TrustedFailure("contract_boundary_value_aliases_empty")
            previous_class = value_alias_owners.get(normalized)
            if previous_class is not None and previous_class != value_class:
                raise TrustedFailure("contract_boundary_value_alias_collision")
            value_alias_owners[normalized] = value_class
            normalized_values.add(normalized)
        if not normalized_values or "" in normalized_values:
            raise TrustedFailure("contract_boundary_value_aliases_empty")
        value_aliases[value_class] = frozenset(normalized_values)

    raw_allowed = _trusted_mapping(
        boundary.get("allowed_value_classes"),
        "contract_boundary_allowed_values",
    )
    if set(raw_allowed) != set(_BOUNDARY_FIELDS):
        raise TrustedFailure("contract_boundary_allowed_value_set_invalid")
    allowed: dict[str, set[str]] = {}
    for field in _BOUNDARY_FIELDS:
        values = _trusted_sequence(
            raw_allowed.get(field),
            "contract_boundary_allowed_values_invalid",
        )
        classes = {
            _trusted_string(value, "contract_boundary_value_class_invalid")
            for value in values
        }
        if not classes <= {*_BOUNDARY_VALUE_CLASSES, "null_value"}:
            raise TrustedFailure("contract_boundary_value_class_unknown")
        allowed[field] = classes
    return BoundaryRules(
        aliases=_compile_boundary_aliases(contract),
        section_aliases=frozenset(section_aliases),
        value_aliases=value_aliases,
        allowed_value_classes={
            field: frozenset(classes) for field, classes in allowed.items()
        },
    )


def _validate_approval_boundary(contract: Mapping[str, Any]) -> None:
    rules = _approval_boundary_rules(contract)
    if not rules.aliases or not rules.value_aliases or not rules.allowed_value_classes:
        raise TrustedFailure("contract_approval_boundary_empty")


def _boundary_value_allowed(
    rule: BoundaryAliasRule,
    value: object,
    rules: BoundaryRules,
) -> bool:
    if type(value) is bool:
        return value is False and rule.false_allowed
    if value is None:
        return "null_value" in rules.allowed_value_classes[rule.field]
    if not isinstance(value, str):
        return False
    normalized = _normalize_boundary_token(value)
    return any(
        value_class in rules.allowed_value_classes[rule.field] and normalized in aliases
        for value_class, aliases in rules.value_aliases.items()
    )


def _check_boundary_sections(
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    rules = _approval_boundary_rules(contract)
    boundary_roots: list[Mapping[str, Any]] = []
    seen_sections: set[str] = set()
    for key, item in payload.items():
        if not isinstance(key, str):
            continue
        normalized_key = _normalize_boundary_token(key)
        if normalized_key in rules.section_aliases:
            if normalized_key in seen_sections:
                raise CandidateFailure("optional_boundary_section_duplicate")
            seen_sections.add(normalized_key)
            if item is None:
                continue
            if not isinstance(item, Mapping):
                raise CandidateFailure("optional_boundary_section_invalid")
            boundary_roots.append(item)
            continue
        rule = rules.aliases.get(normalized_key)
        if rule is not None and not _boundary_value_allowed(rule, item, rules):
            raise CandidateFailure("boundary_claim_invalid")

    def visit_boundary(value: object) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    continue
                rule = rules.aliases.get(_normalize_boundary_token(key))
                if rule is not None:
                    if not _boundary_value_allowed(rule, item, rules):
                        raise CandidateFailure("boundary_claim_invalid")
                elif isinstance(item, (Mapping, list)):
                    visit_boundary(item)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, (Mapping, list)):
                    visit_boundary(item)

    for boundary_root in boundary_roots:
        visit_boundary(boundary_root)


def _check_candidate_shape(
    payload: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> None:
    candidate = _trusted_mapping(contract.get("candidate"), "contract_candidate")
    required = [
        str(item)
        for item in _trusted_sequence(
            candidate.get("mandatory_fields"),
            "contract_mandatory_fields",
        )
    ]
    nonempty = {
        str(item)
        for item in _trusted_sequence(
            candidate.get("mandatory_nonempty_fields"),
            "contract_nonempty_fields",
        )
    }
    if set(required) != {
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
        "open_decisions",
    }:
        raise TrustedFailure("contract_mandatory_field_set_invalid")
    for field in required:
        if field not in payload:
            raise CandidateFailure("candidate_mandatory_field_missing")
        if field in nonempty and not _nonempty(payload[field]):
            raise CandidateFailure("candidate_mandatory_field_empty")

    story = _mapping(payload.get("approved_story"), "approved_story_not_mapping")
    if story.get("id") != "ST-0308":
        raise CandidateFailure("approved_story_mismatch")
    dependencies = _nonempty_string_list(
        story.get("declared_dependencies"),
        "story_dependencies_invalid",
    )
    expected_dependencies = {"ST-0304", "ST-0105"}
    if set(dependencies) != expected_dependencies or len(dependencies) != 2:
        raise CandidateFailure("story_dependencies_mismatch")
    suites = _nonempty_string_list(
        story.get("required_suites"),
        "story_suites_invalid",
    )
    expected_suites = {"TST-005", "TST-008"}
    if set(suites) != expected_suites or len(suites) != 2:
        raise CandidateFailure("story_suites_mismatch")
    if payload.get("open_decisions") != []:
        raise CandidateFailure("open_decisions_not_empty")

    if not isinstance(payload.get("approved_scope"), Mapping):
        raise CandidateFailure("approved_scope_not_mapping")
    decision = _mapping(payload.get("decision"), "decision_not_mapping")
    if "connection_and_identity_boundary" not in decision or not _nonempty(
        decision["connection_and_identity_boundary"]
    ):
        raise CandidateFailure("d6_boundary_section_missing")
    _check_boundary_sections(payload, contract)


def _check_inventory_reconciliation(
    payload: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> None:
    decision = _mapping(payload.get("decision"), "decision_not_mapping")
    inventory = _mapping(
        decision.get("repository_inventory"),
        "repository_inventory_not_mapping",
    )
    included = _mapping(
        inventory.get("included_inventory"),
        "included_inventory_not_mapping",
    )
    schemas = _mapping(included.get("schemas"), "included_schema_map_invalid")
    expected_relations = set(physical["relations"])
    observed_relations: set[str] = set()
    for schema, table_values in schemas.items():
        if not isinstance(schema, str) or not schema:
            raise CandidateFailure("included_schema_name_invalid")
        for table in _sequence(table_values, "included_table_list_invalid"):
            table_name = _string(table, "included_table_name_invalid")
            if "." in table_name:
                raise CandidateFailure("included_table_name_not_unqualified")
            observed_relations.add(f"{schema}.{table_name}")
    if observed_relations != expected_relations:
        raise CandidateFailure("included_inventory_mismatch")

    views = _sequence(included.get("views"), "included_view_list_invalid")
    view_names = [_string(view, "included_view_name_invalid") for view in views]
    if set(view_names) != set(physical["view_relations"]) or len(view_names) != len(
        physical["view_relations"]
    ):
        raise CandidateFailure("included_view_inventory_mismatch")

    counts_by_schema = _mapping(
        included.get("counts_by_schema"),
        "included_counts_invalid",
    )
    expected_counts: dict[str, int] = {}
    for relation in expected_relations:
        schema, _table = relation.split(".", 1)
        expected_counts[schema] = expected_counts.get(schema, 0) + 1
    if set(counts_by_schema) != set(expected_counts) or any(
        counts_by_schema[schema] != count for schema, count in expected_counts.items()
    ):
        raise CandidateFailure("included_schema_counts_mismatch")

    scope = _mapping(payload.get("approved_scope"), "approved_scope_not_mapping")
    physical_cut = _mapping(scope.get("physical_cut"), "physical_cut_not_mapping")
    if (
        physical_cut.get("tables") != physical["tables"]
        or physical_cut.get("views") != physical["views"]
        or physical_cut.get("postgresql_server_version_num") != 180004
        or physical_cut.get("inventory_sha256") != physical["inventory_sha256"]
    ):
        raise CandidateFailure("approved_scope_physical_cut_mismatch")

    normalization = _mapping(
        inventory.get("inventory_normalization"),
        "inventory_normalization_not_mapping",
    )
    counts = _mapping(
        normalization.get("counts"),
        "inventory_normalization_counts_invalid",
    )
    if (
        counts.get("tables") != physical["tables"]
        or counts.get("views") != physical["views"]
        or normalization.get("sha256") != physical["inventory_sha256"]
    ):
        raise CandidateFailure("inventory_normalization_mismatch")


def _concurrency_models(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    decision = _mapping(payload.get("decision"), "decision_not_mapping")
    ports = _mapping(decision.get("port_contracts"), "port_contracts_not_mapping")
    return _mapping(
        ports.get("concurrency_models"),
        "concurrency_models_not_mapping",
    )


def _relation_list(value: object, code: str) -> list[str]:
    rows = _sequence(value, code)
    result = [_string(item, code) for item in rows]
    if len(result) != len(set(result)):
        raise CandidateFailure(code)
    return result


def _check_lock_version_reconciliation(
    payload: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> None:
    models = _concurrency_models(payload)
    lock_model = _mapping(
        models.get("LOCK_VERSION_CAS"),
        "lock_version_model_invalid",
    )
    candidate_lock = set(
        _relation_list(
            lock_model.get("relations"),
            "lock_version_list_invalid",
        )
    )
    if candidate_lock != set(physical["lock_version_relations"]):
        raise CandidateFailure("lock_version_cas_relation_set_mismatch")


def _check_state_cas_reconciliation(
    payload: Mapping[str, Any],
    physical: Mapping[str, Any],
) -> None:
    models = _concurrency_models(payload)
    state_model = _mapping(
        models.get("STATE_CAS_WITHOUT_LOCK_VERSION"),
        "state_cas_model_invalid",
    )
    state_relations = set(
        _relation_list(
            state_model.get("relations"),
            "state_cas_relation_list_invalid",
        )
    )
    if not state_relations <= set(physical["relations"]):
        raise CandidateFailure("state_cas_relation_outside_physical_set")
    if state_relations & set(physical["lock_version_relations"]):
        raise CandidateFailure("state_cas_overlaps_lock_version_set")
    expected_state_relations = set(physical["non_version_state_cas_required"])
    if state_relations != expected_state_relations:
        raise CandidateFailure("state_cas_relation_set_mismatch")


def _check_d6_boundary_presence(payload: Mapping[str, Any]) -> None:
    decision = _mapping(payload.get("decision"), "decision_not_mapping")
    if "connection_and_identity_boundary" not in decision:
        raise CandidateFailure("d6_boundary_section_missing")
    if not _nonempty(decision["connection_and_identity_boundary"]):
        raise CandidateFailure("d6_boundary_section_empty")


def _manual_topics(contract: Mapping[str, Any]) -> list[str]:
    checks = contract.get("automated_checks")
    if isinstance(checks, Mapping):
        topics = checks.get("manual_topics_even_after_pass")
        if isinstance(topics, list) and all(isinstance(item, str) for item in topics):
            return sorted(set(topics))
    return list(DEFAULT_MANUAL_TOPICS)


class CheckBook:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}
        self.errors: set[str] = set()

    def pass_check(self, name: str) -> None:
        self.values[name] = {"status": "PASS"}

    def fail_check(self, name: str, code: str) -> None:
        self.values[name] = {"status": "FAIL", "reason_codes": [code]}
        self.errors.add(code)

    def unavailable(self, name: str) -> None:
        self.values[name] = {
            "status": "UNAVAILABLE",
            "reason_codes": ["candidate_structure_unavailable"],
        }
        self.errors.add("candidate_structure_unavailable")

    def manual_required(self, name: str) -> None:
        self.values[name] = {
            "status": "MANUAL_REQUIRED",
            "reason_codes": ["semantic_review_not_automated"],
        }


def _seed_manual_checks(checks: CheckBook, contract: Mapping[str, Any]) -> None:
    automated = contract.get("automated_checks")
    names = DEFAULT_MANUAL_CHECKS
    if isinstance(automated, Mapping):
        configured = automated.get("manual_check_names")
        if isinstance(configured, list) and all(
            isinstance(item, str) for item in configured
        ):
            names = tuple(configured)
    for name in names:
        checks.manual_required(name)


def _run_candidate_check(
    checks: CheckBook,
    name: str,
    function: Any,
) -> None:
    try:
        function()
    except CandidateFailure as exc:
        checks.fail_check(name, exc.code)
    except (
        AttributeError,
        IndexError,
        KeyError,
        TypeError,
        ValueError,
    ):
        checks.fail_check(name, "candidate_structure_invalid")
    else:
        checks.pass_check(name)


def _report(
    *,
    status: str,
    candidate_sha256: str | None,
    expected_sha256: str | None,
    checks: CheckBook,
    manual_topics: Sequence[str],
    physical: Mapping[str, Any] | None = None,
    bundle: Mapping[str, Any] | None = None,
    trusted_errors: Sequence[str] = (),
    candidate_bytes_read: int | None = None,
    candidate_sha256_complete: bool | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "automated_pass_authorizes_implementation": False,
        "candidate_sha256": candidate_sha256,
        "checks": checks.values,
        "errors": sorted(set(checks.errors) | set(trusted_errors)),
        "exact_byte_owner_approval_required": True,
        "implementation_authority": "NOT_GRANTED",
        "manual_canonical_reconciliation_required": True,
        "manual_reconciliation_topics": sorted(set(manual_topics)),
        "semantic_validation": "MANUAL_REQUIRED",
        "status": status,
        "validation_status": status,
    }
    if expected_sha256 is not None:
        result["expected_sha256"] = expected_sha256
    if candidate_bytes_read is not None:
        result["candidate_bytes_read"] = candidate_bytes_read
    if candidate_sha256_complete is not None:
        result["candidate_sha256_complete"] = candidate_sha256_complete
    if physical is not None:
        result["derived_physical_inventory"] = {
            "tables": physical["tables"],
            "views": physical["views"],
            "inventory_sha256": physical["inventory_sha256"],
            "lock_version_relations": sorted(physical["lock_version_relations"]),
            "view_relations": list(physical["view_relations"]),
        }
    if bundle is not None:
        result["verified_v2_bundle"] = {
            "archive_path": bundle["archive_path"],
            "archive_sha256": bundle["archive_sha256"],
            "approved_input_member": bundle["approved_input_member"],
            "approved_input_sha256": bundle["approved_input_sha256"],
            "regular_member_count": len(bundle["member_hashes"]),
            "regular_member_uncompressed_bytes": bundle["regular_member_bytes"],
        }
    return result


def _emit(result: Mapping[str, Any]) -> None:
    sys.stdout.write(
        json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )


class _NonPrintingArgumentParser(argparse.ArgumentParser):
    """Convert argparse diagnostics into the validator's compact JSON error."""

    def error(self, message: str) -> None:
        del message
        raise UsageFailure("invalid_cli_arguments")

    def exit(self, status: int = 0, message: str | None = None) -> None:
        del status, message
        raise UsageFailure("invalid_cli_arguments")


def _parse_arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = _NonPrintingArgumentParser(
        add_help=False,
        allow_abbrev=False,
        exit_on_error=False,
    )
    parser.add_argument("--handoff")
    parser.add_argument("--expected-sha256")
    parser.add_argument("--repository-root")
    try:
        args = parser.parse_args(argv)
    except UsageFailure:
        raise
    except (argparse.ArgumentError, SystemExit) as exc:
        raise UsageFailure("invalid_cli_arguments") from exc
    if not isinstance(args.handoff, str) or not args.handoff:
        raise UsageFailure("handoff_argument_required")
    if not isinstance(args.expected_sha256, str) or not SHA256_PATTERN.fullmatch(
        args.expected_sha256
    ):
        raise UsageFailure("expected_sha256_must_be_lowercase_hex")
    return args


def _unavailable_candidate_checks(checks: CheckBook) -> None:
    for name in (
        "source_design_refs",
        "physical_inventory_reconciliation",
        "lock_version_cas_reconciliation",
        "state_cas_without_lock_version_reconciliation",
        "d6_boundary_presence",
    ):
        checks.unavailable(name)


def main(argv: Sequence[str] | None = None) -> int:
    expected_sha256: str | None = None
    try:
        args = _parse_arguments(argv)
        expected_sha256 = args.expected_sha256
    except UsageFailure as exc:
        checks = CheckBook()
        _seed_manual_checks(checks, {})
        checks.fail_check("cli_usage", exc.code)
        _emit(
            _report(
                status="ERROR",
                candidate_sha256=None,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=DEFAULT_MANUAL_TOPICS,
                trusted_errors=(exc.code,),
            )
        )
        return 2

    root = _absolute_path(
        Path(args.repository_root) if args.repository_root else SCRIPT_REPO_ROOT
    )
    checks = CheckBook()
    _seed_manual_checks(checks, {})
    candidate_sha256: str | None = None
    candidate_bytes_read: int | None = None
    candidate_sha256_complete: bool | None = None
    try:
        _assert_no_symlink_ancestors(root, final_may_be_file=False)
        root_metadata = root.lstat()
        if not stat.S_ISDIR(root_metadata.st_mode) or stat.S_ISLNK(
            root_metadata.st_mode
        ):
            raise TrustedFailure("repository_root_not_real_directory")
        contract = _read_contract(root)
        checks = CheckBook()
        _seed_manual_checks(checks, contract)
        contents, physical, bundle = _load_trusted_environment(root, contract)
        checks.pass_check("trusted_repository_inputs")
        checks.pass_check("v2_bundle_manifest_and_archive")
        checks.pass_check("cumulative_st0104_repository_manifest")
        checks.pass_check("physical_inventory_reconstruction")
    except TrustedFailure as exc:
        checks.fail_check("trusted_repository_inputs", exc.code)
        _emit(
            _report(
                status="ERROR",
                candidate_sha256=None,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=_manual_topics(locals().get("contract", {})),
                trusted_errors=(exc.code,),
            )
        )
        return 2

    limits = _trusted_mapping(contract.get("limits"), "contract_limits")
    try:
        handoff_content = _secure_read_absolute(
            Path(args.handoff),
            limit=int(limits["handoff_bytes"]),
            candidate_size_failure=True,
        )
        candidate_sha256 = _sha256_bytes(handoff_content)
        candidate_bytes_read = len(handoff_content)
        candidate_sha256_complete = True
    except CandidateFailure as exc:
        candidate_sha256 = exc.details.get("candidate_sha256")
        candidate_bytes_read = exc.details.get("candidate_bytes_read")
        candidate_sha256_complete = exc.details.get("candidate_sha256_complete")
        checks.fail_check("candidate_yaml_safety", exc.code)
        if candidate_sha256 is not None:
            checks.fail_check("expected_sha256_match", "candidate_sha256_incomplete")
        _unavailable_candidate_checks(checks)
        _emit(
            _report(
                status="FAIL",
                candidate_sha256=candidate_sha256,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=_manual_topics(contract),
                physical=physical,
                bundle=bundle,
                candidate_bytes_read=candidate_bytes_read,
                candidate_sha256_complete=candidate_sha256_complete,
            )
        )
        return 1
    except TrustedFailure as exc:
        checks.fail_check("candidate_input_path", exc.code)
        _emit(
            _report(
                status="ERROR",
                candidate_sha256=None,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=_manual_topics(contract),
                physical=physical,
                bundle=bundle,
                trusted_errors=(exc.code,),
            )
        )
        return 2

    if candidate_sha256 == expected_sha256:
        checks.pass_check("expected_sha256_match")
    else:
        checks.fail_check("expected_sha256_match", "candidate_sha256_mismatch")

    try:
        document = _load_yaml_mapping(
            handoff_content,
            candidate=True,
            depth_limit=int(limits["yaml_depth"]),
            node_limit=int(limits["yaml_nodes"]),
        )
    except CandidateFailure as exc:
        checks.fail_check("candidate_yaml_safety", exc.code)
        _unavailable_candidate_checks(checks)
        _emit(
            _report(
                status="FAIL",
                candidate_sha256=candidate_sha256,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=_manual_topics(contract),
                physical=physical,
                bundle=bundle,
                candidate_bytes_read=candidate_bytes_read,
                candidate_sha256_complete=candidate_sha256_complete,
            )
        )
        return 1
    checks.pass_check("candidate_yaml_safety")

    try:
        payload = _candidate_payload(document)
    except CandidateFailure as exc:
        checks.fail_check("candidate_shape_and_story", exc.code)
        _unavailable_candidate_checks(checks)
        _emit(
            _report(
                status="FAIL",
                candidate_sha256=candidate_sha256,
                expected_sha256=expected_sha256,
                checks=checks,
                manual_topics=_manual_topics(contract),
                physical=physical,
                bundle=bundle,
                candidate_bytes_read=candidate_bytes_read,
                candidate_sha256_complete=candidate_sha256_complete,
            )
        )
        return 1

    _run_candidate_check(
        checks,
        "candidate_shape_and_story",
        lambda: _check_candidate_shape(payload, contract),
    )
    _run_candidate_check(
        checks,
        "source_design_refs",
        lambda: _check_source_design_refs(payload, contract, root, bundle),
    )
    _run_candidate_check(
        checks,
        "physical_inventory_reconciliation",
        lambda: _check_inventory_reconciliation(payload, physical),
    )
    _run_candidate_check(
        checks,
        "lock_version_cas_reconciliation",
        lambda: _check_lock_version_reconciliation(payload, physical),
    )
    _run_candidate_check(
        checks,
        "state_cas_without_lock_version_reconciliation",
        lambda: _check_state_cas_reconciliation(payload, physical),
    )
    _run_candidate_check(
        checks,
        "d6_boundary_presence",
        lambda: _check_d6_boundary_presence(payload),
    )

    automated_names = (
        "candidate_yaml_safety",
        "candidate_shape_and_story",
        "expected_sha256_match",
        "source_design_refs",
        "v2_bundle_manifest_and_archive",
        "cumulative_st0104_repository_manifest",
        "physical_inventory_reconciliation",
        "lock_version_cas_reconciliation",
        "state_cas_without_lock_version_reconciliation",
        "d6_boundary_presence",
    )
    passed = all(
        checks.values.get(name, {}).get("status") == "PASS" for name in automated_names
    )
    status = "PASS_AUTOMATED_PREFLIGHT_ONLY" if passed else "FAIL"
    _emit(
        _report(
            status=status,
            candidate_sha256=candidate_sha256,
            expected_sha256=expected_sha256,
            checks=checks,
            manual_topics=_manual_topics(contract),
            physical=physical,
            bundle=bundle,
            candidate_bytes_read=candidate_bytes_read,
            candidate_sha256_complete=candidate_sha256_complete,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
