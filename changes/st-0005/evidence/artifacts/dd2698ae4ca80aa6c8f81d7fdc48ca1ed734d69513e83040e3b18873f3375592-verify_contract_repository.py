#!/usr/bin/env python3
"""Verify the installed ST-0104 contract repository without network access."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import stat
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast
from urllib.parse import unquote_to_bytes, urljoin, urlsplit

import yaml
from jsonschema import Draft7Validator, Draft202012Validator, validators
from referencing import Registry, Resource


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "python"))

from raos.shared.contract_repository import (  # noqa: E402
    DEFAULT_CONTRACT_ROOT,
    ContractRepository,
    ContractRepositoryError,
    parse_strict_json,
)


EXPECTED_COUNTS = {"json": 244, "yaml": 47, "csv": 2, "markdown": 12}
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
VALIDATION_RESOURCE_ROOT = REPO_ROOT / "scripts" / "contract_validation_resources"
MAX_VALIDATION_RESOURCE_BYTES = 1024 * 1024
MAX_DOCUMENT_GRAPH_VISITS = 200_000
MAX_DOCUMENT_GRAPH_DEPTH = 128
OPENAPI_VALIDATION_RESOURCE = (
    "openapi-3.1-schema-2025-11-23.json",
    "1b8ccc6e34234b17536f2dd0eb3597142a32bd108438cd42471a5fca4c1a07ef",
    "https://spec.openapis.org/oas/3.1/schema/2025-11-23",
)
ASYNCAPI_VALIDATION_RESOURCE = (
    "asyncapi-3.0.0-schema.json",
    "d4571a420e6ffb7fcc7066c95a6db1202f299a3c51daa103d0706bf30f95e626",
    "http://asyncapi.com/definitions/3.0.0/asyncapi.json",
)
CONTENT_PATH_REFERENCE_DOCUMENTS = {
    "contracts/content/RAOS_06_content_contract_catalog_v0.1.yaml",
    "contracts/content/fixtures/invalid/expected_results.yaml",
}
LOCAL_REFERENCE_KEYS = {
    "x-raos-job-state-contract",
    "x-raos-state-contract",
    "schema_ref",
    "payload_schema",
    "source_catalog_ref",
    "metric_registry_ref",
    "task_catalog_ref",
    "prompt_registry_ref",
    "model_routing_catalog_ref",
    "evaluation_catalog_ref",
    "git_path",
    "admin_contract_ref",
    "canonical_adoption_ref",
    "output_schema",
    "request_schema",
    "schema_path",
    "state_machine_ref",
    "stored_ast_schema",
    "template",
    "prompt_template",
    "grader_metric_binding_source",
    "x-raos-canonical-source",
    "x-raos-source",
}


class VerificationError(RuntimeError):
    """A syntax, reference, identity, or registry check failed."""


class StrictSafeLoader(yaml.SafeLoader):
    """PyYAML safe loader which additionally rejects duplicate mapping keys."""

    def construct_mapping(
        self, node: yaml.nodes.MappingNode, deep: bool = False
    ) -> dict[object, object]:
        self.flatten_mapping(node)
        result: dict[object, object] = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                duplicate = key in result
            except TypeError as exc:
                raise VerificationError("unhashable YAML mapping key") from exc
            if duplicate:
                raise VerificationError(f"duplicate YAML mapping key: {key!r}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def _mapping(value: object, *, source: str) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise VerificationError(f"expected string-keyed mapping in {source}")
    return cast(Mapping[str, object], value)


def _list(value: object, *, source: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise VerificationError(f"expected list in {source}")
    return cast(Sequence[object], value)


def _string(value: object, *, source: str) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationError(f"expected non-empty string in {source}")
    return value


def _strict_yaml(content: bytes, *, source: str) -> object:
    try:
        text = content.decode("utf-8", errors="strict")
        documents = list(yaml.load_all(text, Loader=StrictSafeLoader))
    except (
        UnicodeDecodeError,
        yaml.YAMLError,
        VerificationError,
        RecursionError,
    ) as exc:
        raise VerificationError(f"invalid YAML in {source}: {exc}") from exc
    if len(documents) != 1 or documents[0] is None:
        raise VerificationError(
            f"expected exactly one non-empty YAML document in {source}"
        )
    document = cast(object, documents[0])
    for _ in _walk(document, source=source):
        pass
    return document


def _strict_csv(content: bytes, *, source: str) -> tuple[tuple[str, ...], ...]:
    try:
        text = content.decode("utf-8", errors="strict")
        rows = tuple(
            tuple(row) for row in csv.reader(io.StringIO(text, newline=""), strict=True)
        )
    except (UnicodeDecodeError, csv.Error) as exc:
        raise VerificationError(f"invalid CSV in {source}: {exc}") from exc
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise VerificationError(f"empty or non-rectangular CSV in {source}")
    return rows


def _verify_traceability_csv(
    rows: Sequence[Sequence[str]], repository: ContractRepository
) -> tuple[int, int]:
    path = "contracts/content/RAOS_06_traceability_matrix_v0.1.csv"
    expected_header = (
        "\ufeffrequirement_id",
        "design_id",
        "artifact",
        "enforcement",
        "test_area",
        "implementation_slice",
    )
    if not rows or tuple(rows[0]) != expected_header or len(rows) != 113:
        raise VerificationError("unexpected content traceability CSV contract")
    external_artifact = "RAOS_06_003_ai_alignment_patch_v0.1.yaml"
    expected_local_targets = {
        f"contracts/content/{filename}"
        for filename in (
            "RAOS_06_article_type_catalog_v0.1.yaml",
            "RAOS_06_claim_evidence_policy_v0.1.yaml",
            "RAOS_06_content_block_catalog_v0.1.yaml",
            "RAOS_06_editorial_policy_catalog_v0.1.yaml",
            "RAOS_06_freshness_update_policy_v0.1.yaml",
            "RAOS_06_internal_link_policy_v0.1.yaml",
            "RAOS_06_media_asset_policy_v0.1.yaml",
            "RAOS_06_quality_gate_catalog_v0.1.yaml",
            "RAOS_06_recommendation_methodology_v0.1.yaml",
            "RAOS_06_review_checklist_v0.1.yaml",
        )
    }
    local_count = 0
    external_count = 0
    local_targets: set[str] = set()
    for index, row in enumerate(rows[1:], start=2):
        if len(row) != len(expected_header) or not all(row):
            raise VerificationError(f"invalid traceability CSV row {index}")
        artifact = row[2]
        if artifact == external_artifact:
            external_count += 1
            continue
        target = _joined_path(path, artifact, contract_root_relative=False)
        repository.read_bytes(target)
        local_targets.add(target)
        local_count += 1
    if (
        local_count != 111
        or external_count != 1
        or local_targets != expected_local_targets
    ):
        raise VerificationError(
            "unexpected content traceability artifact coverage: "
            f"local={local_count}, external={external_count}, "
            f"targets={sorted(local_targets)}"
        )
    return local_count, external_count


def _read_pinned_validation_resource(filename: str, expected_sha256: str) -> bytes:
    path = VALIDATION_RESOURCE_ROOT / filename
    try:
        path_stat = path.lstat()
    except OSError as exc:
        raise VerificationError(
            f"cannot stat pinned validation resource {filename}: {exc}"
        ) from exc
    if stat.S_ISLNK(path_stat.st_mode) or not stat.S_ISREG(path_stat.st_mode):
        raise VerificationError(
            f"pinned validation resource is not a regular file: {filename}"
        )
    if path_stat.st_size > MAX_VALIDATION_RESOURCE_BYTES:
        raise VerificationError(f"pinned validation resource is too large: {filename}")
    no_follow = getattr(os, "O_NOFOLLOW", None)
    if no_follow is None:
        raise VerificationError("O_NOFOLLOW is required for validation resources")
    nonblocking = getattr(os, "O_NONBLOCK", None)
    if nonblocking is None:
        raise VerificationError("O_NONBLOCK is required for validation resources")
    flags = os.O_RDONLY | no_follow | nonblocking
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise VerificationError(
            f"cannot open pinned validation resource {filename}: {exc}"
        ) from exc
    body_error: BaseException | None = None
    try:
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or (path_stat.st_dev, path_stat.st_ino)
                != (before.st_dev, before.st_ino)
                or before.st_size > MAX_VALIDATION_RESOURCE_BYTES
            ):
                raise VerificationError(
                    f"unsafe pinned validation resource: {filename}"
                )
            chunks: list[bytes] = []
            size = 0
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_VALIDATION_RESOURCE_BYTES:
                    raise VerificationError(
                        f"pinned validation resource grew too large: {filename}"
                    )
                chunks.append(chunk)
            after = os.fstat(descriptor)
            if (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            ):
                raise VerificationError(
                    f"pinned validation resource changed during read: {filename}"
                )
        except OSError as exc:
            raise VerificationError(
                f"cannot read pinned validation resource {filename}: {exc}"
            ) from exc
    except BaseException as exc:
        body_error = exc
        raise
    finally:
        try:
            os.close(descriptor)
        except OSError as exc:
            if body_error is None:
                raise VerificationError(
                    f"cannot close pinned validation resource {filename}: {exc}"
                ) from exc
    content = b"".join(chunks)
    if len(content) != path_stat.st_size:
        raise VerificationError(f"short validation resource read: {filename}")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise VerificationError(f"validation resource hash mismatch: {filename}")
    return content


def _load_pinned_validation_schema(
    specification: tuple[str, str, str],
) -> tuple[Mapping[str, object], str]:
    filename, expected_sha256, expected_id = specification
    content = _read_pinned_validation_resource(filename, expected_sha256)
    schema = _mapping(parse_strict_json(content, source=filename), source=filename)
    if schema.get("$id") != expected_id:
        raise VerificationError(f"validation resource ID mismatch: {filename}")
    return schema, expected_id


def _first_validation_error(validator: object, document: object) -> object | None:
    try:
        errors = list(validator.iter_errors(document))  # type: ignore[attr-defined]
    except Exception as exc:
        raise VerificationError(
            f"specification validator failed closed: {exc}"
        ) from exc
    if not errors:
        return None
    return min(errors, key=lambda error: error.json_path)


def _verify_specification_syntax(
    documents: Mapping[str, object], openapi_paths: Sequence[str]
) -> None:
    openapi_schema, openapi_schema_id = _load_pinned_validation_schema(
        OPENAPI_VALIDATION_RESOURCE
    )
    asyncapi_schema, asyncapi_schema_id = _load_pinned_validation_schema(
        ASYNCAPI_VALIDATION_RESOURCE
    )
    try:
        Draft202012Validator.check_schema(openapi_schema)
        Draft7Validator.check_schema(asyncapi_schema)
        openapi_registry = Registry().with_resource(
            openapi_schema_id,
            Resource.from_contents(cast(dict[str, Any], openapi_schema)),
        )
        asyncapi_registry = Registry().with_resource(
            asyncapi_schema_id,
            Resource.from_contents(cast(dict[str, Any], asyncapi_schema)),
        )
        openapi_wrapper: dict[str, object] = {
            "$id": "urn:raos:st-0104:openapi-3.1-validation",
            "$schema": SCHEMA_DIALECT,
            "$ref": openapi_schema_id,
            "required": ["jsonSchemaDialect"],
            "properties": {"jsonSchemaDialect": {"const": SCHEMA_DIALECT}},
            "$defs": {
                "schema": {
                    "$dynamicAnchor": "meta",
                    "$ref": SCHEMA_DIALECT,
                }
            },
        }
        openapi_validator = Draft202012Validator(
            openapi_wrapper, registry=openapi_registry
        )
        asyncapi_validator = Draft7Validator(
            asyncapi_schema, registry=asyncapi_registry
        )
    except Exception as exc:
        raise VerificationError(f"invalid pinned specification schema: {exc}") from exc
    for path in openapi_paths:
        error = _first_validation_error(openapi_validator, documents[path])
        if error is not None:
            raise VerificationError(
                f"OpenAPI structure validation failed in {path} at "
                f"{error.json_path}: {error.message}"
            )
    asyncapi_path = "contracts/asyncapi.v0.4.yaml"
    error = _first_validation_error(asyncapi_validator, documents[asyncapi_path])
    if error is not None:
        raise VerificationError(
            f"AsyncAPI structure validation failed in {asyncapi_path} at "
            f"{error.json_path}: {error.message}"
        )


def _walk_paths(
    value: object, *, source: str
) -> Iterator[tuple[tuple[str, ...], str, object]]:
    """Walk with paths, without recursion, cycles, or alias amplification."""

    stack: list[tuple[str, object, int, tuple[str, ...]]] = [("visit", value, 0, ())]
    active_containers: set[int] = set()
    visits = 0
    while stack:
        action, payload, depth, path = stack.pop()
        if action == "leave":
            active_containers.remove(cast(int, payload))
            continue
        if action == "emit":
            key, child = cast(tuple[str, object], payload)
            yield path, key, child
            continue

        visits += 1
        if visits > MAX_DOCUMENT_GRAPH_VISITS:
            raise VerificationError(f"document graph visit limit exceeded in {source}")
        if depth > MAX_DOCUMENT_GRAPH_DEPTH:
            raise VerificationError(f"document graph depth limit exceeded in {source}")
        if not isinstance(payload, (dict, list)):
            continue

        container_id = id(payload)
        if container_id in active_containers:
            raise VerificationError(f"cyclic document graph in {source}")
        active_containers.add(container_id)
        stack.append(("leave", container_id, depth, path))
        if isinstance(payload, dict):
            for key, child in reversed(tuple(payload.items())):
                child_path = path + (str(key),)
                stack.append(("visit", child, depth + 1, child_path))
                if isinstance(key, str):
                    stack.append(("emit", (key, child), depth + 1, child_path))
        else:
            for index in range(len(payload) - 1, -1, -1):
                child = payload[index]
                stack.append(("visit", child, depth + 1, path + (str(index),)))


def _walk(value: object, *, source: str) -> Iterator[tuple[str, object]]:
    for _, key, child in _walk_paths(value, source=source):
        yield key, child


def _decode_fragment(value: str, *, source: str) -> str:
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise VerificationError(f"invalid percent escape in {source}: {value!r}")
    try:
        return unquote_to_bytes(value).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise VerificationError(f"invalid UTF-8 fragment in {source}") from exc


def _resolve_pointer(document: object, fragment: str, *, source: str) -> object:
    decoded = _decode_fragment(fragment, source=source)
    if decoded == "":
        return document
    if not decoded.startswith("/"):
        raise VerificationError(
            f"reference is not a JSON Pointer in {source}: #{fragment}"
        )
    current = document
    for raw_token in decoded[1:].split("/"):
        if re.search(r"~(?![01])", raw_token):
            raise VerificationError(f"invalid JSON Pointer escape in {source}")
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise VerificationError(
                    f"missing JSON Pointer key {token!r} in {source}"
                )
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise VerificationError(f"invalid JSON Pointer array index in {source}")
            index = int(token)
            if index >= len(current):
                raise VerificationError(
                    f"JSON Pointer array index out of range in {source}"
                )
            current = current[index]
        else:
            raise VerificationError(f"JSON Pointer traverses a scalar in {source}")
    return current


def _reference_location(
    current_path: str,
    reference: str,
    *,
    contract_root_relative: bool = False,
    base_directory: str | None = None,
) -> tuple[str, tuple[str, ...] | None]:
    """Return the physical document and decoded pointer tokens for a reference."""

    if reference.count("#") > 1:
        raise VerificationError(f"multiple fragments in {current_path}: {reference}")
    path_part, separator, fragment = reference.partition("#")
    if path_part:
        join_source = (
            f"{base_directory}/_reference_base"
            if base_directory is not None
            else current_path
        )
        target_path = _joined_path(
            join_source,
            path_part,
            contract_root_relative=contract_root_relative,
        )
    else:
        target_path = current_path
    if not separator:
        return target_path, None
    decoded = _decode_fragment(fragment, source=f"{current_path}: {reference}")
    if decoded == "":
        return target_path, ()
    if not decoded.startswith("/"):
        raise VerificationError(
            f"reference is not a JSON Pointer in {current_path}: {reference}"
        )
    tokens: list[str] = []
    for raw_token in decoded[1:].split("/"):
        if re.search(r"~(?![01])", raw_token):
            raise VerificationError(
                f"invalid JSON Pointer escape in {current_path}: {reference}"
            )
        tokens.append(raw_token.replace("~1", "/").replace("~0", "~"))
    return target_path, tuple(tokens)


def _joined_path(
    current_path: str, reference_path: str, *, contract_root_relative: bool
) -> str:
    if not reference_path or "\\" in reference_path or "\x00" in reference_path:
        raise VerificationError(f"unsafe empty/backslash reference in {current_path}")
    try:
        parsed = urlsplit(reference_path)
    except ValueError as exc:
        raise VerificationError(
            f"remote or malformed reference in {current_path}: {reference_path}"
        ) from exc
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise VerificationError(
            f"remote or malformed reference in {current_path}: {reference_path}"
        )
    if reference_path.startswith("/"):
        raise VerificationError(
            f"absolute reference in {current_path}: {reference_path}"
        )
    parts = (
        ["contracts"]
        if contract_root_relative
        else list(PurePosixPath(current_path).parent.parts)
    )
    for part in reference_path.split("/"):
        if part == "":
            raise VerificationError(
                f"non-normalized reference in {current_path}: {reference_path}"
            )
        if part == ".":
            continue
        if part == "..":
            if not parts:
                raise VerificationError(
                    f"reference escapes repository: {reference_path}"
                )
            parts.pop()
        else:
            parts.append(part)
    if not parts:
        raise VerificationError(
            f"reference resolves to repository root: {reference_path}"
        )
    return PurePosixPath(*parts).as_posix()


def _resolve_reference(
    documents: Mapping[str, object],
    repository: ContractRepository,
    current_path: str,
    reference: str,
    *,
    contract_root_relative: bool = False,
    base_directory: str | None = None,
    require_document_target: bool = False,
) -> object | None:
    if reference.count("#") > 1:
        raise VerificationError(f"multiple fragments in {current_path}: {reference}")
    path_part, separator, fragment = reference.partition("#")
    if path_part:
        join_source = (
            f"{base_directory}/_reference_base"
            if base_directory is not None
            else current_path
        )
        target_path = _joined_path(
            join_source, path_part, contract_root_relative=contract_root_relative
        )
    else:
        target_path = current_path
    repository.read_bytes(target_path)
    if require_document_target and target_path not in documents:
        raise VerificationError(f"reference target is not JSON/YAML: {target_path}")
    if separator:
        target = documents.get(target_path)
        if target is None:
            raise VerificationError(f"fragment target is not JSON/YAML: {target_path}")
        return _resolve_pointer(target, fragment, source=f"{current_path}: {reference}")
    return documents.get(target_path)


def _openapi_reference_role(path: tuple[str, ...]) -> str:
    """Classify every OpenAPI reference context in the frozen corpus."""

    location = path[:-1]
    if location[:2] == ("components", "schemas") or "schema" in location:
        return "schema"
    if (len(location) == 3 and location[:2] == ("components", "parameters")) or (
        len(location) >= 2 and location[-2] == "parameters"
    ):
        return "parameter"
    if (len(location) == 3 and location[:2] == ("components", "headers")) or (
        len(location) >= 2 and location[-2] == "headers"
    ):
        return "header"
    if (len(location) == 3 and location[:2] == ("components", "responses")) or (
        len(location) >= 2 and location[-2] == "responses"
    ):
        return "response"
    return "unknown"


def _resolve_local_object_chain(
    documents: Mapping[str, object],
    repository: ContractRepository,
    document_path: str,
    reference: str,
    *,
    namespace: tuple[str, ...],
    role: str,
    first_name: str | None = None,
) -> tuple[tuple[str, ...], Mapping[str, object]]:
    """Resolve one local Reference Object chain and reject category drift/cycles."""

    current_path = document_path
    current_reference = reference
    expected_name = first_name
    seen: set[tuple[str, tuple[str, ...]]] = set()
    while True:
        target_path, tokens = _reference_location(current_path, current_reference)
        if (
            target_path != document_path
            or tokens is None
            or len(tokens) != len(namespace) + 1
            or tokens[: len(namespace)] != namespace
            or (expected_name is not None and tokens[-1] != expected_name)
        ):
            raise VerificationError(
                f"{role} reference targets the wrong category in "
                f"{document_path}: {current_reference}"
            )
        identity = (target_path, tokens)
        if identity in seen:
            raise VerificationError(
                f"cyclic {role} Reference Object chain in {document_path}"
            )
        seen.add(identity)
        target = _resolve_reference(
            documents,
            repository,
            current_path,
            current_reference,
            require_document_target=True,
        )
        if not isinstance(target, dict):
            raise VerificationError(
                f"{role} reference target is not an object in "
                f"{document_path}: {current_reference}"
            )
        nested_reference = target.get("$ref")
        if nested_reference is None:
            return tokens, cast(Mapping[str, object], target)
        current_reference = _string(
            nested_reference, source=f"{document_path}.{role}.$ref"
        )
        current_path = target_path
        expected_name = None


def _verify_openapi_reference_semantics(
    documents: Mapping[str, object],
    repository: ContractRepository,
    openapi_paths: Sequence[str],
    schema_documents: Mapping[str, Mapping[str, object]],
) -> dict[str, int]:
    """Bind each OpenAPI `$ref` to the role required by its source location."""

    expected = {"schema": 492, "parameter": 486, "response": 1434, "header": 528}
    counts = {role: 0 for role in expected}
    object_namespaces = {
        "parameter": ("components", "parameters"),
        "response": ("components", "responses"),
        "header": ("components", "headers"),
    }
    for document_path in openapi_paths:
        document = documents[document_path]
        for path, key, raw_reference in _walk_paths(document, source=document_path):
            if key != "$ref":
                continue
            reference = _string(
                raw_reference, source=f"{document_path}:{'/'.join(path)}"
            )
            role = _openapi_reference_role(path)
            if role == "unknown":
                raise VerificationError(
                    "unclassified OpenAPI reference context in "
                    f"{document_path}: {'/'.join(path)}"
                )
            if role == "schema":
                target_path, tokens = _reference_location(document_path, reference)
                internal_component = (
                    target_path == document_path
                    and tokens is not None
                    and len(tokens) == 3
                    and tokens[:2] == ("components", "schemas")
                )
                external_schema = target_path in schema_documents and tokens is None
                if not internal_component and not external_schema:
                    raise VerificationError(
                        "OpenAPI schema reference targets the wrong category in "
                        f"{document_path}: {reference}"
                    )
                target = _resolve_reference(
                    documents,
                    repository,
                    document_path,
                    reference,
                    require_document_target=True,
                )
                if not isinstance(target, (dict, bool)):
                    raise VerificationError(
                        "OpenAPI schema reference target is not a schema in "
                        f"{document_path}: {reference}"
                    )
            else:
                _resolve_local_object_chain(
                    documents,
                    repository,
                    document_path,
                    reference,
                    namespace=object_namespaces[role],
                    role=f"OpenAPI {role}",
                )
            counts[role] += 1
    if counts != expected:
        raise VerificationError(f"unexpected OpenAPI reference roles: {counts}")
    return counts


def _asyncapi_reference_role(path: tuple[str, ...]) -> str:
    """Classify every AsyncAPI reference context in the frozen corpus."""

    if (
        len(path) == 4
        and path[0] == "operations"
        and path[2:]
        == (
            "channel",
            "$ref",
        )
    ):
        return "operation_channel"
    if (
        len(path) == 5
        and path[0] == "operations"
        and path[2] == "messages"
        and path[4] == "$ref"
    ):
        return "operation_message"
    if (
        len(path) == 5
        and path[0] == "channels"
        and path[2] == "messages"
        and path[4] == "$ref"
    ):
        return "channel_message"
    if (
        len(path) == 5
        and path[0] == "channels"
        and path[2] == "servers"
        and path[4] == "$ref"
    ):
        return "channel_server"
    if (
        len(path) == 5
        and path[:2] == ("components", "messages")
        and path[3:] == ("payload", "$ref")
    ):
        return "message_payload"
    return "unknown"


def _asyncapi_operation_channel_name(
    documents: Mapping[str, object],
    repository: ContractRepository,
    document_path: str,
    document: Mapping[str, object],
    operation_name: str,
) -> str:
    operations = _mapping(
        document.get("operations"), source=f"{document_path}.operations"
    )
    operation = _mapping(
        operations.get(operation_name),
        source=f"{document_path}.operations.{operation_name}",
    )
    channel = _mapping(
        operation.get("channel"),
        source=f"{document_path}.operations.{operation_name}.channel",
    )
    channel_reference = _string(
        channel.get("$ref"),
        source=f"{document_path}.operations.{operation_name}.channel.$ref",
    )
    tokens, _ = _resolve_local_object_chain(
        documents,
        repository,
        document_path,
        channel_reference,
        namespace=("channels",),
        role="AsyncAPI operation channel",
    )
    return tokens[-1]


def _resolve_asyncapi_channel_message(
    documents: Mapping[str, object],
    repository: ContractRepository,
    document_path: str,
    reference: str,
    *,
    channel_name: str,
) -> None:
    """Resolve an operation message through its declared channel message."""

    target_path, tokens = _reference_location(document_path, reference)
    namespace = ("channels", channel_name, "messages")
    if (
        target_path != document_path
        or tokens is None
        or len(tokens) != 4
        or tokens[:3] != namespace
    ):
        raise VerificationError(
            "AsyncAPI operation message targets a different channel or category "
            f"in {document_path}: {reference}"
        )
    target = _resolve_reference(
        documents,
        repository,
        document_path,
        reference,
        require_document_target=True,
    )
    if not isinstance(target, dict):
        raise VerificationError(
            f"AsyncAPI operation message target is not an object: {reference}"
        )
    component_reference = target.get("$ref")
    if component_reference is None:
        return
    _resolve_local_object_chain(
        documents,
        repository,
        document_path,
        _string(
            component_reference,
            source=f"{document_path}.channels.{channel_name}.messages.{tokens[-1]}.$ref",
        ),
        namespace=("components", "messages"),
        role="AsyncAPI channel message",
        first_name=tokens[-1],
    )


def _verify_asyncapi_reference_semantics(
    documents: Mapping[str, object],
    repository: ContractRepository,
    document_path: str,
    schema_documents: Mapping[str, Mapping[str, object]],
) -> dict[str, int]:
    """Bind each AsyncAPI `$ref` to its channel/message/server/schema role."""

    expected = {
        "operation_channel": 37,
        "operation_message": 249,
        "channel_message": 144,
        "channel_server": 22,
        "message_payload": 105,
    }
    counts = {role: 0 for role in expected}
    document = _mapping(documents[document_path], source=document_path)
    for path, key, raw_reference in _walk_paths(document, source=document_path):
        if key != "$ref":
            continue
        reference = _string(raw_reference, source=f"{document_path}:{'/'.join(path)}")
        role = _asyncapi_reference_role(path)
        if role == "unknown":
            raise VerificationError(
                "unclassified AsyncAPI reference context in "
                f"{document_path}: {'/'.join(path)}"
            )
        if role == "operation_channel":
            _resolve_local_object_chain(
                documents,
                repository,
                document_path,
                reference,
                namespace=("channels",),
                role="AsyncAPI operation channel",
            )
        elif role == "operation_message":
            channel_name = _asyncapi_operation_channel_name(
                documents, repository, document_path, document, path[1]
            )
            _resolve_asyncapi_channel_message(
                documents,
                repository,
                document_path,
                reference,
                channel_name=channel_name,
            )
        elif role == "channel_message":
            _resolve_local_object_chain(
                documents,
                repository,
                document_path,
                reference,
                namespace=("components", "messages"),
                role="AsyncAPI channel message",
                first_name=path[3],
            )
        elif role == "channel_server":
            _resolve_local_object_chain(
                documents,
                repository,
                document_path,
                reference,
                namespace=("servers",),
                role="AsyncAPI channel server",
            )
        else:
            target_path, tokens = _reference_location(document_path, reference)
            if target_path not in schema_documents or tokens is not None:
                raise VerificationError(
                    "AsyncAPI message payload reference targets the wrong category "
                    f"in {document_path}: {reference}"
                )
            target = _resolve_reference(
                documents,
                repository,
                document_path,
                reference,
                require_document_target=True,
            )
            if not isinstance(target, (dict, bool)):
                raise VerificationError(
                    "AsyncAPI message payload reference target is not a schema "
                    f"in {document_path}: {reference}"
                )
        counts[role] += 1
    if counts != expected:
        raise VerificationError(f"unexpected AsyncAPI reference roles: {counts}")
    return counts


def _verify_json_data_model(value: object, *, source: str) -> None:
    """Reject YAML-only values and non-string keys before schema validation."""

    stack: list[tuple[str, object, int]] = [("visit", value, 0)]
    active_containers: set[int] = set()
    visits = 0
    while stack:
        action, current, depth = stack.pop()
        if action == "leave":
            active_containers.remove(cast(int, current))
            continue
        visits += 1
        if visits > MAX_DOCUMENT_GRAPH_VISITS:
            raise VerificationError(f"JSON data-model visit limit exceeded in {source}")
        if depth > MAX_DOCUMENT_GRAPH_DEPTH:
            raise VerificationError(f"JSON data-model depth limit exceeded in {source}")
        if isinstance(current, dict):
            if not all(isinstance(key, str) for key in current):
                raise VerificationError(f"non-string JSON object key in {source}")
            container_id = id(current)
            if container_id in active_containers:
                raise VerificationError(f"cyclic JSON data model in {source}")
            active_containers.add(container_id)
            stack.append(("leave", container_id, depth))
            for child in reversed(tuple(current.values())):
                stack.append(("visit", child, depth + 1))
        elif isinstance(current, list):
            container_id = id(current)
            if container_id in active_containers:
                raise VerificationError(f"cyclic JSON data model in {source}")
            active_containers.add(container_id)
            stack.append(("leave", container_id, depth))
            for child in reversed(current):
                stack.append(("visit", child, depth + 1))
        elif current is None or isinstance(current, (str, bool, int)):
            continue
        elif isinstance(current, float) and math.isfinite(current):
            continue
        else:
            raise VerificationError(
                f"non-JSON value {type(current).__name__} in {source}"
            )


def _verify_embedded_public_resource_schemas(
    documents: Mapping[str, object], repository: ContractRepository
) -> tuple[int, int]:
    """Meta-validate and role-bind the seven embedded public resource schemas."""

    document_path = "contracts/catalogs/resource-contracts.v0.4.yaml"
    document = _mapping(documents[document_path], source=document_path)
    resources = _mapping(
        document.get("public_resources"),
        source=f"{document_path}.public_resources",
    )
    expected_names = {
        "AffiliateClickInput",
        "PublicArticleBlock",
        "PublicArticleDocument",
        "PublicOffer",
        "PublicProductCard",
        "PublicRoute",
        "RuntimeControl",
    }
    if set(resources) != expected_names:
        raise VerificationError("unexpected embedded public resource schemas")
    for name, schema in resources.items():
        if not isinstance(schema, (dict, bool)):
            raise VerificationError(f"embedded public resource is not a schema: {name}")
        _verify_json_data_model(schema, source=f"{document_path}.{name}")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise VerificationError(
                f"invalid embedded public resource schema {name}: {exc}"
            ) from exc

    reference_count = 0
    for path, key, raw_reference in _walk_paths(document, source=document_path):
        if key != "$ref" or path[:1] != ("public_resources",):
            continue
        reference = _string(raw_reference, source=f"{document_path}:{'/'.join(path)}")
        target_path, tokens = _reference_location(document_path, reference)
        if (
            target_path != document_path
            or tokens is None
            or len(tokens) != 2
            or tokens[0] != "public_resources"
            or tokens[1] not in expected_names
        ):
            raise VerificationError(
                "embedded public resource schema reference targets the wrong "
                f"category in {document_path}: {reference}"
            )
        target = _resolve_reference(
            documents,
            repository,
            document_path,
            reference,
            require_document_target=True,
        )
        if not isinstance(target, (dict, bool)):
            raise VerificationError(
                "embedded public resource reference target is not a schema in "
                f"{document_path}: {reference}"
            )
        reference_count += 1
    if reference_count != 3:
        raise VerificationError(
            f"unexpected embedded public resource schema refs: {reference_count}"
        )
    return len(resources), reference_count


def _verify_json_schema_references(
    schemas: Mapping[str, Mapping[str, object]],
    repository: ContractRepository,
) -> int:
    """Resolve Draft 2020-12 references by canonical base URI, offline only."""

    registry: Registry[Any] = Registry()
    resources: dict[str, Resource[Any]] = {}
    try:
        for path, schema in schemas.items():
            schema_id = _string(schema.get("$id"), source=f"{path}.$id")
            resource = Resource.from_contents(cast(dict[str, Any], schema))
            registry = registry.with_resource(schema_id, resource)
            resources[path] = resource
        for retrieval_uri in repository.schema_retrieval_aliases:
            target_path = repository.path_for_uri(retrieval_uri)
            resource = resources.get(target_path)
            if resource is None:
                raise VerificationError(
                    f"schema retrieval alias target is not a schema: {retrieval_uri}"
                )
            registry = registry.with_resource(retrieval_uri, resource)
    except VerificationError:
        raise
    except Exception as exc:
        raise VerificationError(
            f"cannot build offline JSON Schema registry: {exc}"
        ) from exc

    reference_count = 0
    used_aliases: set[str] = set()
    declared_aliases = set(repository.schema_retrieval_aliases)
    for path, schema in schemas.items():
        schema_id = _string(schema.get("$id"), source=f"{path}.$id")
        resolver = registry.resolver(base_uri=schema_id)
        for key, raw_reference in _walk(schema, source=path):
            if key != "$ref":
                continue
            reference = _string(raw_reference, source=f"{path}.$ref")
            try:
                resolved_uri = urljoin(schema_id, reference).partition("#")[0]
                if resolved_uri in declared_aliases:
                    used_aliases.add(resolved_uri)
                resolved = resolver.lookup(reference)
            except Exception as exc:
                raise VerificationError(
                    "JSON Schema URI reference does not resolve offline in "
                    f"{path}: {reference}"
                ) from exc
            if not isinstance(resolved.contents, (dict, bool)):
                raise VerificationError(
                    "JSON Schema URI reference target is not a schema in "
                    f"{path}: {reference}"
                )
            reference_count += 1
    if reference_count != 344:
        raise VerificationError(
            f"unexpected JSON Schema URI reference count: {reference_count}"
        )
    if used_aliases != declared_aliases:
        raise VerificationError(
            "schema retrieval URI aliases are missing or unused: "
            f"missing={sorted(declared_aliases - used_aliases)}, "
            f"unexpected={sorted(used_aliases - declared_aliases)}"
        )
    return reference_count


def _verify_registries(
    documents: Mapping[str, object], repository: ContractRepository
) -> int:
    specifications = (
        (
            "contracts/catalogs/schema-registry.v0.4.yaml",
            "contracts",
            "id",
            224,
        ),
        (
            "contracts/ai/RAOS_05_schema_registry_v0.1.yaml",
            "contracts/ai",
            "schema_id",
            14,
        ),
        (
            "contracts/content/RAOS_06_schema_registry_v0.1.yaml",
            "contracts/content",
            "schema_id",
            33,
        ),
    )
    total = 0
    root_ids: set[str] = set()
    for registry_path, base, id_key, expected_count in specifications:
        registry = _mapping(documents[registry_path], source=registry_path)
        entries = _list(registry.get("schemas"), source=f"{registry_path}.schemas")
        if len(entries) != expected_count:
            raise VerificationError(f"unexpected registry count in {registry_path}")
        seen_paths: set[str] = set()
        seen_ids: set[str] = set()
        for index, raw_entry in enumerate(entries):
            entry = _mapping(raw_entry, source=f"{registry_path}.schemas[{index}]")
            relative = _string(entry.get("path"), source=f"{registry_path}.path")
            schema_id = _string(entry.get(id_key), source=f"{registry_path}.{id_key}")
            digest = _string(entry.get("sha256"), source=f"{registry_path}.sha256")
            target_path = _joined_path(
                f"{base}/registry.yaml", relative, contract_root_relative=False
            )
            if target_path in seen_paths or schema_id in seen_ids:
                raise VerificationError(f"duplicate registry entry in {registry_path}")
            seen_paths.add(target_path)
            seen_ids.add(schema_id)
            content = repository.read_bytes(target_path)
            if hashlib.sha256(content).hexdigest() != digest:
                raise VerificationError(f"registry hash mismatch: {target_path}")
            schema = _mapping(documents[target_path], source=target_path)
            if schema.get("$id") != schema_id:
                raise VerificationError(f"registry ID mismatch: {target_path}")
            if repository.path_for_id(schema_id) != target_path:
                raise VerificationError(f"loader ID index mismatch: {schema_id}")
        if registry_path.endswith("catalogs/schema-registry.v0.4.yaml"):
            root_ids = seen_ids
        else:
            expected_prefix = f"{base}/schemas/"
            expected_paths = {
                artifact.path
                for artifact in repository.artifacts
                if artifact.path.startswith(expected_prefix)
                and artifact.path.endswith(".schema.json")
            }
            if seen_paths != expected_paths:
                raise VerificationError(
                    f"child schema registry does not exactly cover {expected_prefix}"
                )
        total += len(entries)
    if root_ids != set(repository.schema_ids):
        raise VerificationError(
            "root schema registry does not exactly cover schema IDs"
        )
    return total


def _expected_semantic_reference_locations() -> frozenset[tuple[str, tuple[str, ...]]]:
    """Return the frozen source locations of all 192 semantic path references."""

    locations: set[tuple[str, tuple[str, ...]]] = set()

    def add(document: str, *path: str) -> None:
        locations.add((document, path))

    ai_tasks = "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml"
    for index in range(12):
        add(ai_tasks, "tasks", str(index), "output_schema")
        add(ai_tasks, "tasks", str(index), "prompt_template")
        add(
            "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml",
            "templates",
            str(index),
            "git_path",
        )
    add(
        "contracts/ai/canonical-adoption.v0.3.yaml",
        "grader_output_metric_bindings",
        "source_catalog_ref",
    )
    add(
        "contracts/ai/canonical-adoption.v0.3.yaml",
        "grader_output_metric_bindings",
        "metric_registry_ref",
    )
    add("contracts/asyncapi.v0.4.yaml", "x-raos-job-state-contract")

    job_catalog = "contracts/catalogs/job-catalog.v0.4.yaml"
    add(job_catalog, "state_model", "state_machine_ref")
    for key in (
        "task_catalog_ref",
        "prompt_registry_ref",
        "model_routing_catalog_ref",
        "evaluation_catalog_ref",
        "canonical_adoption_ref",
    ):
        add(job_catalog, "ai_governance_revision", key)
    for index in range(39):
        add(job_catalog, "jobs", str(index), "payload_schema")

    resource_catalog = "contracts/catalogs/resource-contracts.v0.4.yaml"
    for index in (22, 23, 24, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65):
        add(resource_catalog, "resources", str(index), "schema_ref")
    for resource_index, command_index in (
        (23, 0),
        (24, 0),
        (58, 0),
        (60, 0),
        (62, 0),
        (63, 0),
        (64, 0),
        (65, 0),
        (65, 1),
    ):
        add(
            resource_catalog,
            "resources",
            str(resource_index),
            "x-raos-create-command-contracts",
            str(command_index),
            "request_schema",
        )
    add(
        resource_catalog,
        "resources",
        "50",
        "fields",
        "4",
        "schema",
        "x-raos-state-contract",
    )
    for resource_index in (25, 60):
        add(
            resource_catalog,
            "resources",
            str(resource_index),
            "x-raos-completion-evidence-invariants",
            "case_grader_completeness",
            "grader_metric_binding_source",
        )
    add(
        resource_catalog,
        "evaluation_run_completion_evidence_invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )

    transition_catalog = "contracts/catalogs/state-transition-catalog.v0.4.yaml"
    for index in range(10, 16):
        add(transition_catalog, "machines", str(index), "x-raos-source")
    article_catalog = "contracts/content/RAOS_06_article_type_catalog_v0.1.yaml"
    for index in range(5):
        add(article_catalog, "article_types", str(index), "template")
    block_catalog = "contracts/content/RAOS_06_content_block_catalog_v0.1.yaml"
    for index in range(24):
        add(block_catalog, "blocks", str(index), "schema_path")
    content_catalog = "contracts/content/RAOS_06_content_contract_catalog_v0.1.yaml"
    for index in range(14):
        add(content_catalog, "contracts", str(index), "path")
    add(
        "contracts/content/canonical-adoption.v0.4.yaml",
        "ast_boundary",
        "stored_ast_schema",
    )
    fixture_catalog = "contracts/content/fixtures/invalid/expected_results.yaml"
    for index in range(15):
        add(fixture_catalog, "fixtures", str(index), "path")

    openapi_admin = "contracts/openapi-admin.v0.4.yaml"
    for operation_path in (
        "/api/v1/admin/ops/jobs/{id}/retry",
        "/api/v1/admin/ops/jobs/{id}/cancel",
    ):
        add(openapi_admin, "paths", operation_path, "post", "x-raos-state-contract")
    add(
        openapi_admin,
        "paths",
        "/api/v1/admin/ai/evaluation-runs",
        "post",
        "x-raos-completion-evidence-invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )
    add(
        openapi_admin,
        "components",
        "schemas",
        "EvaluationResult",
        "x-raos-completion-evidence-invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )
    add(
        openapi_admin,
        "components",
        "schemas",
        "Job",
        "properties",
        "status",
        "x-raos-state-contract",
    )
    add(
        openapi_admin,
        "components",
        "schemas",
        "EvaluationSuiteV1",
        "allOf",
        "0",
        "then",
        "properties",
        "suite_config",
        "x-raos-canonical-source",
    )
    add(
        openapi_admin,
        "components",
        "schemas",
        "EvaluationRunV1",
        "x-raos-completion-evidence-invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )
    add(
        openapi_admin,
        "components",
        "schemas",
        "ModelRouteVersionCreateRequestV1",
        "properties",
        "route_config",
        "x-raos-canonical-source",
    )
    add(
        openapi_admin,
        "x-raos-ai-governance",
        "evaluation_run_completion_evidence_invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )

    openapi_internal = "contracts/openapi-internal.v0.4.yaml"
    add(openapi_internal, "info", "x-raos-job-state-contract")
    add(openapi_internal, "x-raos-ai-governance", "admin_contract_ref")
    add(openapi_internal, "x-raos-ai-governance", "canonical_adoption_ref")
    add(
        "contracts/schemas/ai-governance/evaluation-run.v1.schema.json",
        "x-raos-completion-evidence-invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )
    add(
        "contracts/schemas/ai-governance/evaluation-suite.v1.schema.json",
        "allOf",
        "0",
        "then",
        "properties",
        "suite_config",
        "x-raos-canonical-source",
    )
    add(
        "contracts/schemas/ai-governance/model-route-version-create-request.v1.schema.json",
        "properties",
        "route_config",
        "x-raos-canonical-source",
    )
    add(
        "contracts/schemas/events/jp-raos-ai-evaluation-completed-v2.schema.json",
        "allOf",
        "1",
        "properties",
        "data",
        "x-raos-completion-evidence-invariants",
        "case_grader_completeness",
        "grader_metric_binding_source",
    )
    if len(locations) != 192:
        raise AssertionError(f"invalid semantic reference inventory: {len(locations)}")
    return frozenset(locations)


def _verify_semantic_references(
    documents: Mapping[str, object],
    repository: ContractRepository,
    schema_documents: Mapping[str, Mapping[str, object]],
) -> tuple[int, int]:
    count = 0
    schema_target_count = 0
    schema_reference_keys = {
        "output_schema",
        "payload_schema",
        "request_schema",
        "schema_path",
        "schema_ref",
        "stored_ast_schema",
    }
    expected_locations = _expected_semantic_reference_locations()
    seen_locations: set[tuple[str, tuple[str, ...]]] = set()
    for current_path, document in documents.items():
        for path, key, raw_reference in _walk_paths(document, source=current_path):
            is_local_reference = (
                key in LOCAL_REFERENCE_KEYS
                or key.endswith("_catalog_ref")
                or key.endswith("_registry_ref")
                or (key == "path" and current_path in CONTENT_PATH_REFERENCE_DOCUMENTS)
            )
            location = (current_path, path)
            if location in expected_locations:
                if not is_local_reference or not isinstance(raw_reference, str):
                    raise VerificationError(
                        "semantic reference has the wrong type or key at "
                        f"{current_path}: {'/'.join(path)}"
                    )
                seen_locations.add(location)
            elif is_local_reference and isinstance(raw_reference, str):
                raise VerificationError(
                    "unclassified semantic reference context in "
                    f"{current_path}: {'/'.join(path)}"
                )
            else:
                continue
            if key == "state_machine_ref":
                path_part, separator, machine_id = raw_reference.partition("#")
                if not separator or not re.fullmatch(r"[A-Z][A-Z0-9-]*", machine_id):
                    raise VerificationError(
                        f"invalid state machine reference in {current_path}"
                    )
                target_path = _joined_path(
                    current_path, path_part, contract_root_relative=False
                )
                repository.read_bytes(target_path)
                target = _mapping(documents.get(target_path), source=target_path)
                machines = _list(
                    target.get("machines"), source=f"{target_path}.machines"
                )
                matches = [
                    machine
                    for machine in machines
                    if isinstance(machine, dict) and machine.get("id") == machine_id
                ]
                if len(matches) != 1:
                    raise VerificationError(
                        f"state machine ID is not unique: {raw_reference}"
                    )
                count += 1
                continue
            root_relative = (
                key == "payload_schema"
                or (
                    key in {"source_catalog_ref", "metric_registry_ref"}
                    and current_path.endswith("ai/canonical-adoption.v0.3.yaml")
                )
                or key == "stored_ast_schema"
                or key == "x-raos-canonical-source"
            )
            if key == "request_schema":
                base_directory = "contracts/schemas/ai-governance"
            elif key == "grader_metric_binding_source":
                base_directory = "contracts/ai"
            elif key == "path" and current_path in CONTENT_PATH_REFERENCE_DOCUMENTS:
                base_directory = "contracts/content"
            else:
                base_directory = None
            resolved_target = _resolve_reference(
                documents,
                repository,
                current_path,
                raw_reference,
                contract_root_relative=root_relative,
                base_directory=base_directory,
            )
            if key in schema_reference_keys:
                target_path, tokens = _reference_location(
                    current_path,
                    raw_reference,
                    contract_root_relative=root_relative,
                    base_directory=base_directory,
                )
                if (
                    target_path not in schema_documents
                    or tokens is not None
                    or not isinstance(resolved_target, (dict, bool))
                ):
                    raise VerificationError(
                        "semantic schema reference targets a non-schema in "
                        f"{current_path}: {raw_reference}"
                    )
                schema_target_count += 1
            count += 1
    if seen_locations != expected_locations:
        missing = sorted(expected_locations - seen_locations)
        unexpected = sorted(seen_locations - expected_locations)
        raise VerificationError(
            "semantic reference location inventory mismatch: "
            f"missing={missing}, unexpected={unexpected}"
        )
    if count != 192:
        raise VerificationError(f"unexpected semantic local reference count: {count}")
    if schema_target_count != 99:
        raise VerificationError(
            f"unexpected semantic schema reference count: {schema_target_count}"
        )
    return count, schema_target_count


def _verify_semantic_schema_ids(
    documents: Mapping[str, object], repository: ContractRepository
) -> int:
    count = 0
    resource_path = "contracts/catalogs/resource-contracts.v0.4.yaml"
    catalog = _mapping(documents[resource_path], source=resource_path)
    resources = _list(catalog.get("resources"), source=f"{resource_path}.resources")
    for index, raw_resource in enumerate(resources):
        resource = _mapping(raw_resource, source=f"{resource_path}.resources[{index}]")
        if "schema_id" not in resource:
            continue
        schema_id = _string(
            resource.get("schema_id"),
            source=f"{resource_path}.resources[{index}].schema_id",
        )
        repository.resolve_id(schema_id)
        count += 1
    if count != 11:
        raise VerificationError(f"unexpected resource schema ID count: {count}")

    dataschema_count = 0
    for current_path, document in documents.items():
        if not current_path.startswith("contracts/schemas/events/"):
            continue
        for key, raw_value in _walk(document, source=current_path):
            if key != "dataschema" or not isinstance(raw_value, dict):
                continue
            dataschema = _mapping(
                cast(object, raw_value), source=f"{current_path}.dataschema"
            )
            if "const" not in dataschema:
                continue
            schema_id = _string(
                dataschema.get("const"), source=f"{current_path}.dataschema.const"
            )
            if repository.path_for_id(schema_id) != current_path:
                raise VerificationError(
                    f"event dataschema ID does not bind its document: {current_path}"
                )
            dataschema_count += 1
    if dataschema_count != 3:
        raise VerificationError(
            f"unexpected event dataschema ID count: {dataschema_count}"
        )
    return count + dataschema_count


def _verify_hash_bound_references(
    documents: Mapping[str, object], repository: ContractRepository
) -> int:
    count = 0
    prompt_path = "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml"
    prompt_registry = _mapping(documents[prompt_path], source=prompt_path)
    templates = _list(
        prompt_registry.get("templates"), source=f"{prompt_path}.templates"
    )
    if len(templates) != 12:
        raise VerificationError("unexpected prompt registry template count")
    prompt_targets: set[str] = set()
    for index, raw_template in enumerate(templates):
        template = _mapping(raw_template, source=f"{prompt_path}.templates[{index}]")
        relative = _string(template.get("git_path"), source=f"{prompt_path}.git_path")
        digest = _string(template.get("sha256"), source=f"{prompt_path}.sha256")
        target = _joined_path(prompt_path, relative, contract_root_relative=False)
        content = repository.read_bytes(target)
        if hashlib.sha256(content).hexdigest() != digest:
            raise VerificationError(f"prompt registry hash mismatch: {target}")
        prompt_targets.add(target)
        count += 1
    expected_markdown = {
        artifact.path
        for artifact in repository.artifacts
        if artifact.path.startswith("contracts/ai/prompts/")
        and artifact.path.endswith(".md")
    }
    if prompt_targets != expected_markdown:
        raise VerificationError(
            "prompt registry does not exactly cover Markdown prompts"
        )

    task_catalog_path = "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml"
    task_catalog = _mapping(documents[task_catalog_path], source=task_catalog_path)
    tasks = _list(task_catalog.get("tasks"), source=f"{task_catalog_path}.tasks")
    if len(tasks) != 12:
        raise VerificationError("unexpected AI task catalog count")
    for index, raw_task in enumerate(tasks):
        task = _mapping(raw_task, source=f"{task_catalog_path}.tasks[{index}]")
        relative = _string(
            task.get("output_schema"), source=f"{task_catalog_path}.output_schema"
        )
        digest = _string(
            task.get("output_schema_sha256"),
            source=f"{task_catalog_path}.output_schema_sha256",
        )
        target = _joined_path(
            "contracts/ai/_reference_base",
            relative,
            contract_root_relative=False,
        )
        if hashlib.sha256(repository.read_bytes(target)).hexdigest() != digest:
            raise VerificationError(f"AI task output schema hash mismatch: {target}")
        count += 1

    adoption_path = "contracts/ai/canonical-adoption.v0.3.yaml"
    adoption = _mapping(documents[adoption_path], source=adoption_path)
    predecessor = _mapping(
        adoption.get("predecessor"), source=f"{adoption_path}.predecessor"
    )
    job_state_digest = _string(
        predecessor.get("job_state_sha256"),
        source=f"{adoption_path}.predecessor.job_state_sha256",
    )
    if (
        hashlib.sha256(repository.read_bytes("job-state.v1.yaml")).hexdigest()
        != job_state_digest
    ):
        raise VerificationError("AI predecessor job-state hash mismatch")
    count += 1
    frozen = _mapping(
        adoption.get("frozen_artifacts"), source=f"{adoption_path}.frozen_artifacts"
    )
    if set(frozen) != {"catalogs_and_templates", "prompts", "schemas"}:
        raise VerificationError("unexpected AI frozen artifact groups")
    frozen_count = 0
    for group, raw_entries in frozen.items():
        entries = _list(raw_entries, source=f"{adoption_path}.{group}")
        for index, raw_entry in enumerate(entries):
            entry = _mapping(raw_entry, source=f"{adoption_path}.{group}[{index}]")
            relative = _string(entry.get("path"), source=f"{adoption_path}.path")
            digest = _string(entry.get("sha256"), source=f"{adoption_path}.sha256")
            byte_count = entry.get("bytes")
            if not isinstance(byte_count, int) or isinstance(byte_count, bool):
                raise VerificationError(f"invalid frozen byte count: {relative}")
            target = _joined_path(adoption_path, relative, contract_root_relative=False)
            content = repository.read_bytes(target)
            if (
                len(content) != byte_count
                or hashlib.sha256(content).hexdigest() != digest
            ):
                raise VerificationError(f"AI frozen artifact mismatch: {target}")
            frozen_count += 1
            count += 1
    if frozen_count != 40:
        raise VerificationError(f"unexpected AI frozen artifact count: {frozen_count}")

    public_isolation = _mapping(
        adoption.get("public_isolation"), source=f"{adoption_path}.public_isolation"
    )
    public_relative = _string(
        public_isolation.get("path"), source=f"{adoption_path}.public_isolation.path"
    )
    public_digest = _string(
        public_isolation.get("sha256"),
        source=f"{adoption_path}.public_isolation.sha256",
    )
    public_target = _joined_path(
        adoption_path, public_relative, contract_root_relative=False
    )
    if (
        hashlib.sha256(repository.read_bytes(public_target)).hexdigest()
        != public_digest
    ):
        raise VerificationError("public isolation snapshot hash mismatch")
    return count + 1


def _verify_prompt_frontmatter(
    repository: ContractRepository,
    documents: Mapping[str, object],
    schema_documents: Mapping[str, Mapping[str, object]],
) -> int:
    expected_keys = {
        "prompt_code",
        "version",
        "task_code",
        "status",
        "locale",
        "route_code",
        "output_schema",
        "human_review_required",
        "tools_allowed",
        "network_access",
    }
    paths = sorted(
        artifact.path
        for artifact in repository.artifacts
        if artifact.path.startswith("contracts/ai/prompts/")
        and artifact.path.endswith(".md")
    )
    if len(paths) != 12:
        raise VerificationError("unexpected Markdown prompt count")
    for path in paths:
        text = repository.read_text(path)
        lines = text.splitlines()
        markers = [index for index, line in enumerate(lines) if line == "---"]
        if len(markers) != 2 or markers[0] != 0 or markers[1] <= 1:
            raise VerificationError(f"expected one YAML frontmatter block: {path}")
        frontmatter_text = "\n".join(lines[1 : markers[1]]) + "\n"
        frontmatter = _mapping(
            _strict_yaml(
                frontmatter_text.encode("utf-8"), source=f"{path}:frontmatter"
            ),
            source=f"{path}:frontmatter",
        )
        if set(frontmatter) != expected_keys:
            raise VerificationError(f"unexpected prompt frontmatter keys: {path}")
        if (
            not isinstance(frontmatter.get("version"), int)
            or isinstance(frontmatter.get("version"), bool)
            or frontmatter.get("version") != 1
            or frontmatter.get("status") not in {"CANDIDATE", "DISABLED"}
            or frontmatter.get("locale") != "ja-JP"
            or not isinstance(frontmatter.get("human_review_required"), bool)
            or frontmatter.get("tools_allowed") is not False
            or frontmatter.get("network_access") is not False
        ):
            raise VerificationError(f"unexpected prompt frontmatter contract: {path}")
        for required_string in ("prompt_code", "task_code", "route_code"):
            _string(
                frontmatter.get(required_string), source=f"{path}.{required_string}"
            )
        output_schema = _string(
            frontmatter.get("output_schema"), source=f"{path}.output_schema"
        )
        target_path, tokens = _reference_location(
            path,
            output_schema,
            base_directory="contracts/ai",
        )
        target = _resolve_reference(
            documents,
            repository,
            path,
            output_schema,
            base_directory="contracts/ai",
        )
        if (
            target_path not in schema_documents
            or tokens is not None
            or not isinstance(target, (dict, bool))
        ):
            raise VerificationError(
                f"prompt output_schema targets a non-schema in {path}: {output_schema}"
            )
        if not "\n".join(lines[markers[1] + 1 :]).strip():
            raise VerificationError(f"empty prompt body: {path}")
    return len(paths)


def verify(root: Path | str = DEFAULT_CONTRACT_ROOT) -> dict[str, int | str]:
    """Run TST-002-equivalent local verification and return PASS counts."""

    repository = ContractRepository(root)
    documents: dict[str, object] = {}
    csv_documents: dict[str, tuple[tuple[str, ...], ...]] = {}
    counts = {name: 0 for name in EXPECTED_COUNTS}
    for artifact in repository.artifacts:
        path = artifact.path
        if not path.startswith("contracts/"):
            continue
        if path.endswith(".json"):
            documents[path] = repository.load_json(path)
            counts["json"] += 1
        elif path.endswith(".yaml"):
            documents[path] = _strict_yaml(repository.read_bytes(path), source=path)
            counts["yaml"] += 1
        elif path.endswith(".csv"):
            csv_documents[path] = _strict_csv(repository.read_bytes(path), source=path)
            counts["csv"] += 1
        elif path.endswith(".md"):
            if not repository.read_text(path):
                raise VerificationError(f"empty Markdown artifact: {path}")
            counts["markdown"] += 1
        else:
            raise VerificationError(f"unsupported contract artifact extension: {path}")
    if counts != EXPECTED_COUNTS:
        raise VerificationError(f"contract syntax inventory mismatch: {counts}")
    documents["job-state.v1.yaml"] = _strict_yaml(
        repository.read_bytes("job-state.v1.yaml"), source="job-state.v1.yaml"
    )
    csv_rows_including_headers = sum(len(rows) for rows in csv_documents.values())
    csv_records = csv_rows_including_headers - len(csv_documents)
    if csv_rows_including_headers != 1128 or csv_records != 1126:
        raise VerificationError("unexpected CSV row inventory")
    traceability_local_refs, traceability_external_refs = _verify_traceability_csv(
        csv_documents["contracts/content/RAOS_06_traceability_matrix_v0.1.csv"],
        repository,
    )

    openapi_paths = sorted(
        path for path in documents if PurePosixPath(path).name.startswith("openapi-")
    )
    if openapi_paths != [
        "contracts/openapi-admin.v0.4.yaml",
        "contracts/openapi-internal.v0.4.yaml",
        "contracts/openapi-public.v0.1.yaml",
    ]:
        raise VerificationError("unexpected OpenAPI document inventory")
    openapi_identities = {
        "contracts/openapi-admin.v0.4.yaml": (
            "RAOS-OAS-ADMIN-001",
            "RAOS Admin API",
            "0.4",
        ),
        "contracts/openapi-internal.v0.4.yaml": (
            "RAOS-OAS-INTERNAL-001",
            "RAOS Internal API",
            "0.4",
        ),
        "contracts/openapi-public.v0.1.yaml": (
            "RAOS-OAS-PUBLIC-001",
            "RAOS Public API",
            "0.1",
        ),
    }
    for path in openapi_paths:
        document = _mapping(documents[path], source=path)
        if (
            document.get("openapi") != "3.1.1"
            or document.get("jsonSchemaDialect") != SCHEMA_DIALECT
        ):
            raise VerificationError(f"unexpected OpenAPI identity: {path}")
        info = _mapping(document.get("info"), source=f"{path}.info")
        expected_id, expected_title, expected_version = openapi_identities[path]
        if (
            info.get("x-raos-document-id") != expected_id
            or info.get("title") != expected_title
            or info.get("version") != expected_version
        ):
            raise VerificationError(f"unexpected OpenAPI info identity: {path}")
    asyncapi_path = "contracts/asyncapi.v0.4.yaml"
    asyncapi = _mapping(documents[asyncapi_path], source=asyncapi_path)
    if asyncapi.get("asyncapi") != "3.0.0":
        raise VerificationError("unexpected AsyncAPI identity")
    asyncapi_info = _mapping(asyncapi.get("info"), source=f"{asyncapi_path}.info")
    if (
        asyncapi_info.get("x-raos-document-id") != "RAOS-ASYNCAPI-001"
        or asyncapi_info.get("title") != "RAOS Event and Job Contracts"
        or asyncapi_info.get("version") != "0.4"
    ):
        raise VerificationError("unexpected AsyncAPI info identity")
    _verify_specification_syntax(documents, openapi_paths)

    schema_count = 0
    schema_documents: dict[str, Mapping[str, object]] = {}
    for path, document in documents.items():
        if (
            not path.endswith(".json")
            or not isinstance(document, dict)
            or "$schema" not in document
        ):
            continue
        schema = cast(dict[str, Any], document)
        if schema.get("$schema") != SCHEMA_DIALECT:
            raise VerificationError(f"unsupported JSON Schema dialect: {path}")
        validator_class = validators.validator_for(schema)
        if validator_class is not Draft202012Validator:
            raise VerificationError(f"unexpected JSON Schema validator: {path}")
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:
            raise VerificationError(
                f"invalid Draft 2020-12 schema {path}: {exc}"
            ) from exc
        schema_documents[path] = schema
        schema_count += 1
    if schema_count != 224:
        raise VerificationError(f"unexpected JSON Schema count: {schema_count}")

    openapi_reference_roles = _verify_openapi_reference_semantics(
        documents, repository, openapi_paths, schema_documents
    )
    asyncapi_reference_roles = _verify_asyncapi_reference_semantics(
        documents,
        repository,
        asyncapi_path,
        schema_documents,
    )
    embedded_schema_count, embedded_schema_reference_count = (
        _verify_embedded_public_resource_schemas(documents, repository)
    )

    reference_count = 0
    for current_path, document in documents.items():
        for key, raw_reference in _walk(document, source=current_path):
            if key != "$ref":
                continue
            reference = _string(raw_reference, source=f"{current_path}.$ref")
            _resolve_reference(
                documents,
                repository,
                current_path,
                reference,
                require_document_target=True,
            )
            reference_count += 1
    if reference_count != 3844:
        raise VerificationError(f"unexpected local $ref count: {reference_count}")
    json_schema_references = _verify_json_schema_references(
        schema_documents, repository
    )
    classified_reference_count = (
        sum(openapi_reference_roles.values())
        + sum(asyncapi_reference_roles.values())
        + json_schema_references
        + embedded_schema_reference_count
    )
    if classified_reference_count != reference_count:
        raise VerificationError(
            "role-classified reference coverage mismatch: "
            f"classified={classified_reference_count}, physical={reference_count}"
        )

    registry_entries = _verify_registries(documents, repository)
    semantic_references, semantic_schema_references = _verify_semantic_references(
        documents, repository, schema_documents
    )
    semantic_schema_ids = _verify_semantic_schema_ids(documents, repository)
    hash_bound_references = _verify_hash_bound_references(documents, repository)
    prompt_frontmatter_references = _verify_prompt_frontmatter(
        repository, documents, schema_documents
    )
    return {
        "status": "PASS",
        "artifacts": len(repository.artifacts),
        "json": counts["json"],
        "contract_yaml": counts["yaml"],
        "job_state_yaml": 1,
        "csv": counts["csv"],
        "csv_records": csv_records,
        "csv_header_rows": len(csv_documents),
        "csv_rows_including_headers": csv_rows_including_headers,
        "csv_local_refs": traceability_local_refs,
        "csv_external_provenance_refs": traceability_external_refs,
        "markdown": counts["markdown"],
        "openapi": len(openapi_paths),
        "asyncapi": 1,
        "openapi_schema_refs": openapi_reference_roles["schema"],
        "openapi_parameter_refs": openapi_reference_roles["parameter"],
        "openapi_response_refs": openapi_reference_roles["response"],
        "openapi_header_refs": openapi_reference_roles["header"],
        "asyncapi_operation_channel_refs": asyncapi_reference_roles[
            "operation_channel"
        ],
        "asyncapi_operation_message_refs": asyncapi_reference_roles[
            "operation_message"
        ],
        "asyncapi_channel_message_refs": asyncapi_reference_roles["channel_message"],
        "asyncapi_channel_server_refs": asyncapi_reference_roles["channel_server"],
        "asyncapi_message_payload_refs": asyncapi_reference_roles["message_payload"],
        "embedded_public_resource_schemas": embedded_schema_count,
        "embedded_public_resource_schema_refs": embedded_schema_reference_count,
        "json_schemas": schema_count,
        "schema_ids": len(repository.schema_ids),
        "json_schema_refs": json_schema_references,
        "schema_uri_aliases": len(repository.schema_retrieval_aliases),
        "local_refs": reference_count,
        "role_classified_local_refs": classified_reference_count,
        "registry_entries": registry_entries,
        "semantic_local_refs": semantic_references,
        "semantic_schema_path_refs": semantic_schema_references,
        "semantic_schema_id_refs": semantic_schema_ids,
        "hash_bound_refs": hash_bound_references,
        "declared_hash_bindings": registry_entries + hash_bound_references,
        "prompt_frontmatter_refs": prompt_frontmatter_references,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_CONTRACT_ROOT,
        help="installed contract repository root",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        report = verify(args.root)
    except (
        ContractRepositoryError,
        VerificationError,
        RecursionError,
        ValueError,
    ) as exc:
        print(
            json.dumps({"status": "FAIL", "error": str(exc)}, sort_keys=True),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
