#!/usr/bin/env python3
"""Compile the installed ST-0003 AI registries into one strict runtime JSON."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPO_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.shared.contract_repository import (  # noqa: E402
    ContractRepository,
    ContractRepositoryError,
    parse_strict_json,
)


CONTRACT_PATH: Final = Path(
    "changes/st-0701/contracts/ai-contract-registry-loader.v1.yaml"
)
OUTPUT_PATH: Final = Path("changes/st-0701/generated/ai-task-registry.v1.json")
MANIFEST_PATH: Final = Path("changes/st-0701/manifest.yaml")
CONTRACT_REPOSITORY_PATH: Final = Path("contracts/raos-v0.4")
CONTRACT_REPOSITORY_MANIFEST: Final = (
    CONTRACT_REPOSITORY_PATH / "contract-repository.v0.4.json"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "8898b6f49e692586598109a27c046ae6dff4423f59f81837af00f5c5ab8bb90a"
)
EXPECTED_REPOSITORY_MANIFEST_SHA256: Final = (
    "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef"
)
EXPECTED_ST0003_MANIFEST_SHA256: Final = (
    "142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482"
)
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python scripts/build_st0701_ai_registry.py"
)
PINNED_CANONICAL_INPUTS: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
}
STORY_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0701/README.md"),
    Path("docs/execplans/ST-0701.md"),
    Path("docs/worklogs/ST-0701.md"),
    Path("scripts/build_st0701_ai_registry.py"),
    Path("python/raos/adapters/__init__.py"),
    Path("python/raos/adapters/ai_contract_registry.py"),
    Path("python/raos/domain/ai/__init__.py"),
    Path("python/raos/domain/ai/contracts.py"),
    Path("python/raos/ports/__init__.py"),
    Path("python/raos/ports/task_registry.py"),
    Path("python/raos/shared/contract_repository.py"),
    Path("tests/st0701/conftest.py"),
    Path("tests/st0701/test_compiled_task_registry.py"),
    Path("tests/st0701/test_generation.py"),
    Path("tests/st0701/test_contract.py"),
    Path("tests/st0102/test_commands_and_docs.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path("Makefile"),
    Path("README.md"),
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
)
EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-AI-TASK-REGISTRY-001",
    "version": "1.0.0",
    "story_id": "ST-0701",
    "status": "IMPLEMENTATION_CANDIDATE",
}
EXPECTED_REGISTRY_DOCUMENT: Final = {
    "id": "RAOS-AI-001",
    "version": "0.1",
    "date": "2026-07-30",
    "status": "BASELINE_CANDIDATE",
}
EXPECTED_PROMPT_FRONTMATTER_KEYS: Final = {
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
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class RegistrySpec:
    kind: str
    path: str
    sha256: str
    byte_count: int
    entries_field: str
    key_field: str
    entry_count: int
    top_level_keys: frozenset[str]


REGISTRY_SPECS: Final = (
    RegistrySpec(
        "TASK",
        "contracts/ai/RAOS_05_ai_task_catalog_v0.1.yaml",
        "8b5a0d820f0a6180dd0bbbd050553114c22efe499a553d72bbdb24ffc8483c04",
        22884,
        "tasks",
        "task_code",
        12,
        frozenset({"document", "architecture_pattern", "global_invariants", "tasks"}),
    ),
    RegistrySpec(
        "PROMPT",
        "contracts/ai/RAOS_05_prompt_registry_v0.1.yaml",
        "745b0d6039a9f533dc92146bb3234f33e88518e184de88e67a59ca5b5c023d27",
        8714,
        "templates",
        "prompt_code",
        12,
        frozenset(
            {
                "document",
                "management_model",
                "compiler_contract",
                "templates",
                "review_rules",
            }
        ),
    ),
    RegistrySpec(
        "SCHEMA",
        "contracts/ai/RAOS_05_schema_registry_v0.1.yaml",
        "4a34d6d18192184333e374c8a44e849915b817f7a8019d9e6d0101077bdbe751",
        4108,
        "schemas",
        "schema_id",
        14,
        frozenset(
            {"document", "json_schema_dialect", "provider_compatibility", "schemas"}
        ),
    ),
    RegistrySpec(
        "ROUTE",
        "contracts/ai/RAOS_05_model_routing_catalog_v0.1.yaml",
        "dc76ed6d2586eec9bf18b8ac2e95eb76971179fe87fa1ee07b1ba8702f8faa96",
        7402,
        "routes",
        "route_code",
        7,
        frozenset(
            {
                "document",
                "selection_principle",
                "hard_eligibility_gates",
                "utility_after_hard_gates",
                "routing_invariants",
                "models",
                "routes",
                "prompt_cache_policy",
                "batch_policy",
            }
        ),
    ),
)


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader with duplicate-key rejection."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
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
                "found unhashable mapping key",
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
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


class NoAliasDumper(yaml.SafeDumper):
    """Keep the generated manifest explicit and diff-stable."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_sha256(value: object) -> str:
    try:
        content = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise RuntimeError("registry value is not canonical JSON") from exc
    return _sha256(content)


def _normalize_json(value: object, *, source: str) -> object:
    visits = 0
    active: set[int] = set()

    def normalize(item: object, depth: int) -> object:
        nonlocal visits
        visits += 1
        if visits > 100_000 or depth > 100:
            raise RuntimeError(f"{source} exceeds the JSON graph limit")
        if item is None or type(item) in {bool, int, str}:
            return item
        if type(item) is float:
            if not math.isfinite(cast(float, item)):
                raise RuntimeError(f"{source} contains a non-finite number")
            return item
        if not isinstance(item, (dict, list)):
            raise RuntimeError(f"{source} contains a non-JSON value")
        identity = id(item)
        if identity in active:
            raise RuntimeError(f"{source} contains a cycle")
        active.add(identity)
        try:
            if isinstance(item, dict):
                if not all(type(key) is str for key in item):
                    raise RuntimeError(f"{source} contains a non-string key")
                return {
                    cast(str, key): normalize(child, depth + 1)
                    for key, child in item.items()
                }
            return [normalize(child, depth + 1) for child in item]
        finally:
            active.remove(identity)

    return normalize(value, 0)


def _strict_yaml(content: bytes, *, source: str) -> object:
    try:
        text = content.decode("utf-8", errors="strict")
        loaded = yaml.load(text, Loader=UniqueKeyLoader)
    except RuntimeError:
        raise
    except (UnicodeDecodeError, yaml.YAMLError, RecursionError) as exc:
        raise RuntimeError(f"{source} is not strict YAML") from exc
    return _normalize_json(loaded, source=source)


def _mapping(value: object, *, source: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(type(key) is str for key in value):
        raise RuntimeError(f"{source} must be a string-keyed object")
    return cast(dict[str, object], value)


def _sequence(value: object, *, source: str) -> list[object]:
    if not isinstance(value, list):
        raise RuntimeError(f"{source} must be an array")
    return cast(list[object], value)


def _string(value: object, *, source: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise RuntimeError(f"{source} must be a non-empty trimmed string")
    return value


def _integer(value: object, *, source: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RuntimeError(f"{source} must be an integer")
    return value


def _read_regular(root: Path, relative: Path, *, label: str) -> bytes:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe {label} path")
    normalized_root = Path(os.path.abspath(root))
    target = normalized_root / relative
    try:
        if normalized_root.resolve(strict=True) != normalized_root:
            raise RuntimeError("repository root contains a symlink")
        if target.resolve(strict=True) != target:
            raise RuntimeError(f"{label} path contains a symlink")
        before = target.lstat()
    except OSError as exc:
        raise RuntimeError(f"required {label} is missing") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    if before.st_size > MAX_SOURCE_BYTES:
        raise RuntimeError(f"{label} exceeds the size limit")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(target, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
            opened.st_dev,
            opened.st_ino,
        ):
            raise RuntimeError(f"{label} changed before read")
        chunks: list[bytes] = []
        consumed = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, MAX_SOURCE_BYTES + 1 - consumed))
            if not chunk:
                break
            chunks.append(chunk)
            consumed += len(chunk)
            if consumed > MAX_SOURCE_BYTES:
                raise RuntimeError(f"{label} exceeds the size limit")
        after = os.fstat(descriptor)
        if (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ) or consumed != after.st_size:
            raise RuntimeError(f"{label} changed during read")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _checked_ai_path(value: object, *, source: str) -> str:
    raw = _string(value, source=source)
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or "\\" in raw
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != raw
        or "://" in raw
    ):
        raise RuntimeError(f"unsafe AI artifact path in {source}")
    return f"contracts/ai/{raw}"


def _unique_index(
    entries: object, *, key_field: str, source: str, expected_count: int
) -> dict[str, dict[str, object]]:
    raw_entries = _sequence(entries, source=source)
    if len(raw_entries) != expected_count:
        raise RuntimeError(f"{source} entry count mismatch")
    index: dict[str, dict[str, object]] = {}
    folded: set[str] = set()
    for offset, raw_entry in enumerate(raw_entries):
        entry = _mapping(raw_entry, source=f"{source}[{offset}]")
        key = _string(entry.get(key_field), source=f"{source}[{offset}].{key_field}")
        if key in index or key.casefold() in folded:
            raise RuntimeError(f"duplicate or conflicting {key_field}: {key}")
        index[key] = entry
        folded.add(key.casefold())
    return index


def _load_registries(
    repository: ContractRepository,
) -> dict[str, dict[str, object]]:
    artifact_index = {artifact.path: artifact for artifact in repository.artifacts}
    result: dict[str, dict[str, object]] = {}
    for spec in REGISTRY_SPECS:
        artifact = artifact_index.get(spec.path)
        if (
            artifact is None
            or artifact.byte_count != spec.byte_count
            or artifact.sha256 != spec.sha256
        ):
            raise RuntimeError(f"{spec.kind} registry manifest binding mismatch")
        content = repository.read_bytes(spec.path)
        if len(content) != spec.byte_count or _sha256(content) != spec.sha256:
            raise RuntimeError(f"{spec.kind} registry hash mismatch")
        document = _mapping(_strict_yaml(content, source=spec.path), source=spec.path)
        if set(document) != set(spec.top_level_keys):
            raise RuntimeError(f"{spec.kind} registry top-level shape mismatch")
        if document.get("document") != EXPECTED_REGISTRY_DOCUMENT:
            raise RuntimeError(f"{spec.kind} registry document mismatch")
        _unique_index(
            document.get(spec.entries_field),
            key_field=spec.key_field,
            source=f"{spec.kind} registry entries",
            expected_count=spec.entry_count,
        )
        result[spec.kind] = document
    return result


def _verified_resource(
    repository: ContractRepository,
    artifact_index: Mapping[str, object],
    path: str,
    expected_sha256: object,
    *,
    label: str,
) -> bytes:
    digest = _string(expected_sha256, source=f"{label}.sha256")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise RuntimeError(f"invalid {label} SHA-256")
    artifact = artifact_index.get(path)
    if artifact is None or getattr(artifact, "sha256", None) != digest:
        raise RuntimeError(f"{label} repository-manifest hash mismatch")
    content = repository.read_bytes(path)
    if _sha256(content) != digest or len(content) != getattr(
        artifact, "byte_count", -1
    ):
        raise RuntimeError(f"{label} artifact hash mismatch")
    return content


def _prompt_frontmatter(content: bytes, *, source: str) -> dict[str, object]:
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{source} is not UTF-8") from exc
    if not text.startswith("---\n"):
        raise RuntimeError(f"{source} has no prompt frontmatter")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise RuntimeError(f"{source} has unterminated prompt frontmatter")
    frontmatter = _mapping(
        _strict_yaml(text[4:closing].encode("utf-8"), source=f"{source} frontmatter"),
        source=f"{source} frontmatter",
    )
    if set(frontmatter) != EXPECTED_PROMPT_FRONTMATTER_KEYS:
        raise RuntimeError(f"{source} frontmatter shape mismatch")
    return frontmatter


def _artifact_record(root: Path, relative: Path, *, label: str) -> dict[str, object]:
    content = _read_regular(root, relative, label=label)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _compiler_input_records(
    repository: ContractRepository,
) -> list[dict[str, object]]:
    registries = _load_registries(repository)
    paths = {spec.path for spec in REGISTRY_SPECS}
    prompt_entries = _sequence(
        registries["PROMPT"]["templates"], source="prompt registry templates"
    )
    schema_entries = _sequence(
        registries["SCHEMA"]["schemas"], source="schema registry schemas"
    )
    for offset, raw_prompt in enumerate(prompt_entries):
        prompt = _mapping(raw_prompt, source=f"prompt registry templates[{offset}]")
        paths.add(
            _checked_ai_path(
                prompt.get("git_path"), source=f"prompt template[{offset}].git_path"
            )
        )
    for offset, raw_schema in enumerate(schema_entries):
        schema = _mapping(raw_schema, source=f"schema registry schemas[{offset}]")
        paths.add(
            _checked_ai_path(
                schema.get("path"), source=f"schema registry[{offset}].path"
            )
        )
    artifact_index = {artifact.path: artifact for artifact in repository.artifacts}
    records: list[dict[str, object]] = []
    for path in sorted(paths):
        artifact = artifact_index.get(path)
        if artifact is None:
            raise RuntimeError(f"compiler input is not repository-owned: {path}")
        repository.read_bytes(path)
        records.append(
            {
                "uri": f"repo://{CONTRACT_REPOSITORY_PATH.as_posix()}/{path}",
                "repository_path": path,
                "bytes": artifact.byte_count,
                "sha256": artifact.sha256,
            }
        )
    if len(records) != 30:
        raise RuntimeError("unexpected ST-0701 compiler input count")
    return records


def compile_registry(repository: ContractRepository) -> dict[str, object]:
    """Compile and reconcile every pinned Task/Prompt/Schema/Route binding."""

    registries = _load_registries(repository)
    artifacts = {artifact.path: artifact for artifact in repository.artifacts}

    task_document = registries["TASK"]
    prompt_document = registries["PROMPT"]
    schema_document = registries["SCHEMA"]
    route_document = registries["ROUTE"]

    tasks = _unique_index(
        task_document["tasks"],
        key_field="task_code",
        source="task registry tasks",
        expected_count=12,
    )
    _unique_index(
        task_document["tasks"],
        key_field="id",
        source="task registry catalog IDs",
        expected_count=12,
    )
    prompts = _unique_index(
        prompt_document["templates"],
        key_field="prompt_code",
        source="prompt registry templates",
        expected_count=12,
    )
    prompts_by_task = _unique_index(
        prompt_document["templates"],
        key_field="task_code",
        source="prompt registry task bindings",
        expected_count=12,
    )
    schemas_by_id = _unique_index(
        schema_document["schemas"],
        key_field="schema_id",
        source="schema registry schemas",
        expected_count=14,
    )
    schemas_by_path = _unique_index(
        schema_document["schemas"],
        key_field="path",
        source="schema registry paths",
        expected_count=14,
    )
    routes = _unique_index(
        route_document["routes"],
        key_field="route_code",
        source="route registry routes",
        expected_count=7,
    )
    models = _unique_index(
        route_document["models"],
        key_field="model_key",
        source="route registry models",
        expected_count=3,
    )

    for route_code, route in routes.items():
        for field_name in ("primary_model_key", "fallback_model_key"):
            model_key = route.get(field_name)
            if model_key is not None and model_key not in models:
                raise RuntimeError(
                    f"route {route_code} has unknown {field_name}: {model_key!r}"
                )

    prompt_resources: dict[str, tuple[str, str, dict[str, object]]] = {}
    for prompt_code, prompt in prompts.items():
        repository_path = _checked_ai_path(
            prompt.get("git_path"), source=f"prompt {prompt_code}.git_path"
        )
        content = _verified_resource(
            repository,
            artifacts,
            repository_path,
            prompt.get("sha256"),
            label=f"prompt {prompt_code}",
        )
        frontmatter = _prompt_frontmatter(content, source=repository_path)
        for field_name in ("prompt_code", "version", "task_code", "status"):
            if frontmatter.get(field_name) != prompt.get(field_name):
                raise RuntimeError(
                    f"prompt {prompt_code} frontmatter {field_name} conflict"
                )
        prompt_resources[prompt_code] = (
            repository_path,
            _sha256(content),
            frontmatter,
        )

    schema_resources: dict[str, tuple[str, str, dict[str, object]]] = {}
    for schema_id, schema in schemas_by_id.items():
        repository_path = _checked_ai_path(
            schema.get("path"), source=f"schema {schema_id}.path"
        )
        content = _verified_resource(
            repository,
            artifacts,
            repository_path,
            schema.get("sha256"),
            label=f"schema {schema_id}",
        )
        raw_schema = parse_strict_json(content, source=repository_path)
        normalized_schema = _mapping(
            _normalize_json(raw_schema, source=repository_path), source=repository_path
        )
        if normalized_schema.get("$id") != schema_id:
            raise RuntimeError(f"schema ID conflict: {schema_id}")
        schema_resources[schema_id] = (
            repository_path,
            _sha256(content),
            normalized_schema,
        )

    if set(prompts_by_task) != set(tasks):
        raise RuntimeError("Task and Prompt task-code inventories differ")

    compiled_entries: list[dict[str, object]] = []
    used_prompt_codes: set[str] = set()
    used_schema_paths: set[str] = set()
    for task_code in sorted(tasks):
        task = tasks[task_code]
        prompt_code = _string(
            task.get("prompt_code"), source=f"task {task_code}.prompt_code"
        )
        prompt = prompts.get(prompt_code)
        if prompt is None or prompt.get("task_code") != task_code:
            raise RuntimeError(f"task {task_code} has a broken Prompt reference")
        used_prompt_codes.add(prompt_code)
        prompt_path, prompt_sha256, frontmatter = prompt_resources[prompt_code]
        task_prompt_path = _checked_ai_path(
            task.get("prompt_template"), source=f"task {task_code}.prompt_template"
        )
        if task_prompt_path != prompt_path:
            raise RuntimeError(f"task {task_code} Prompt path conflict")

        schema_relative_path = _string(
            task.get("output_schema"), source=f"task {task_code}.output_schema"
        )
        schema = schemas_by_path.get(schema_relative_path)
        if schema is None:
            raise RuntimeError(f"task {task_code} has a broken Schema reference")
        schema_id = _string(
            schema.get("schema_id"), source=f"task {task_code} schema_id"
        )
        schema_path, schema_sha256, _schema_bytes = schema_resources[schema_id]
        used_schema_paths.add(schema_relative_path)
        if task.get("output_schema_sha256") != schema_sha256:
            raise RuntimeError(f"task {task_code} Schema hash conflict")

        route_code = _string(
            task.get("route_code"), source=f"task {task_code}.route_code"
        )
        route = routes.get(route_code)
        if route is None:
            raise RuntimeError(f"task {task_code} has a broken Route reference")

        expected_frontmatter = {
            "prompt_code": prompt_code,
            "version": prompt.get("version"),
            "task_code": task_code,
            "status": prompt.get("status"),
            "route_code": route_code,
            "output_schema": schema_relative_path,
            "human_review_required": task.get("human_review_required"),
            "tools_allowed": task.get("tools_allowed"),
            "network_access": task.get("network_access"),
        }
        for field_name, expected in expected_frontmatter.items():
            if frontmatter.get(field_name) != expected:
                raise RuntimeError(
                    f"task {task_code} Prompt frontmatter {field_name} conflict"
                )

        prompt_metadata = dict(prompt)
        prompt_metadata["frontmatter"] = dict(frontmatter)
        unsigned_entry: dict[str, object] = {
            "task": dict(task),
            "task_sha256": _canonical_sha256(task),
            "prompt": {
                "prompt_code": prompt_code,
                "version": _integer(
                    prompt.get("version"), source=f"prompt {prompt_code}.version"
                ),
                "task_code": task_code,
                "status": _string(
                    prompt.get("status"), source=f"prompt {prompt_code}.status"
                ),
                "locale": _string(
                    frontmatter.get("locale"),
                    source=f"prompt {prompt_code}.locale",
                ),
                "artifact_path": prompt_path,
                "sha256": prompt_sha256,
                "metadata": prompt_metadata,
            },
            "output_schema": {
                "schema_id": schema_id,
                "artifact_path": schema_path,
                "sha256": schema_sha256,
                "metadata": dict(schema),
            },
            "route": {
                "route_code": route_code,
                "sha256": _canonical_sha256(route),
                "metadata": dict(route),
            },
        }
        compiled_entries.append(
            {**unsigned_entry, "binding_sha256": _canonical_sha256(unsigned_entry)}
        )

    if used_prompt_codes != set(prompts):
        raise RuntimeError("Prompt registry contains an unbound template")
    task_output_paths = {
        _string(schema.get("path"), source="task-output schema path")
        for schema in schemas_by_id.values()
        if schema.get("kind") == "task_output"
    }
    if used_schema_paths != task_output_paths:
        raise RuntimeError("Task-output Schema registry closure mismatch")

    return {
        "document": dict(EXPECTED_DOCUMENT),
        "task_count": len(compiled_entries),
        "tasks": compiled_entries,
    }


def render_registry(root: Path = REPO_ROOT) -> bytes:
    """Render deterministic JSON only after every pinned input verifies."""

    if sys.version_info[:3] != (3, 14, 6) or yaml.__version__ != "6.0.3":
        raise RuntimeError("ST-0701 generation requires Python 3.14.6 and PyYAML 6.0.3")
    contract_content = _read_regular(root, CONTRACT_PATH, label="ST-0701 contract")
    if _sha256(contract_content) != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("ST-0701 source contract hash drift")
    contract = _mapping(
        _strict_yaml(contract_content, source=CONTRACT_PATH.as_posix()),
        source=CONTRACT_PATH.as_posix(),
    )
    projection = _mapping(
        contract.get("compiled_projection"), source="compiled_projection"
    )
    if projection.get("document") != EXPECTED_DOCUMENT:
        raise RuntimeError("ST-0701 compiled document contract drift")
    manifest_content = _read_regular(
        root, CONTRACT_REPOSITORY_MANIFEST, label="contract repository manifest"
    )
    if _sha256(manifest_content) != EXPECTED_REPOSITORY_MANIFEST_SHA256:
        raise RuntimeError("contract repository manifest hash drift")
    repository = ContractRepository(root / CONTRACT_REPOSITORY_PATH)
    document = compile_registry(repository)
    return (
        json.dumps(
            document,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def render_manifest(registry_content: bytes, root: Path = REPO_ROOT) -> bytes:
    """Render the Story manifest from the exact current source inventory."""

    contract_content = _read_regular(root, CONTRACT_PATH, label="ST-0701 contract")
    if _sha256(contract_content) != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("ST-0701 source contract hash drift")
    contract = _mapping(
        _strict_yaml(contract_content, source=CONTRACT_PATH.as_posix()),
        source=CONTRACT_PATH.as_posix(),
    )
    canonical_records: list[dict[str, object]] = []
    for path_string, expected_digest in PINNED_CANONICAL_INPUTS.items():
        record = _artifact_record(
            root, Path(path_string), label=f"canonical input {path_string}"
        )
        if record["sha256"] != expected_digest:
            raise RuntimeError(f"canonical input hash drift: {path_string}")
        canonical_records.append(record)

    st0003_record = _artifact_record(
        root, Path("changes/st-0003/manifest.yaml"), label="ST-0003 manifest"
    )
    if st0003_record["sha256"] != EXPECTED_ST0003_MANIFEST_SHA256:
        raise RuntimeError("ST-0003 predecessor manifest hash drift")
    repository_manifest_record = _artifact_record(
        root,
        CONTRACT_REPOSITORY_MANIFEST,
        label="ST-0104 contract repository manifest",
    )
    if repository_manifest_record["sha256"] != EXPECTED_REPOSITORY_MANIFEST_SHA256:
        raise RuntimeError("ST-0104 repository manifest hash drift")

    repository = ContractRepository(root / CONTRACT_REPOSITORY_PATH)
    compiler_inputs = _compiler_input_records(repository)
    story_sources = [
        _artifact_record(root, path, label=f"ST-0701 source {path.as_posix()}")
        for path in STORY_SOURCE_PATHS
    ]
    if len(STORY_SOURCE_PATHS) != len(set(STORY_SOURCE_PATHS)):
        raise RuntimeError("duplicate ST-0701 source path")

    compiled = _mapping(
        parse_strict_json(registry_content, source=OUTPUT_PATH.as_posix()),
        source=OUTPUT_PATH.as_posix(),
    )
    tasks = _sequence(compiled.get("tasks"), source="compiled tasks")
    task_codes: list[str] = []
    route_codes: set[str] = set()
    schema_ids: set[str] = set()
    for offset, raw_entry in enumerate(tasks):
        entry = _mapping(raw_entry, source=f"compiled tasks[{offset}]")
        task = _mapping(entry.get("task"), source=f"compiled tasks[{offset}].task")
        route = _mapping(entry.get("route"), source=f"compiled tasks[{offset}].route")
        schema = _mapping(
            entry.get("output_schema"),
            source=f"compiled tasks[{offset}].output_schema",
        )
        task_codes.append(
            _string(task.get("task_code"), source=f"compiled tasks[{offset}].task_code")
        )
        route_codes.add(
            _string(
                route.get("route_code"), source=f"compiled tasks[{offset}].route_code"
            )
        )
        schema_ids.add(
            _string(
                schema.get("schema_id"), source=f"compiled tasks[{offset}].schema_id"
            )
        )
    if task_codes != sorted(task_codes) or len(task_codes) != 12:
        raise RuntimeError("compiled task closure is not exact")

    registries = _load_registries(repository)
    all_route_codes = set(
        _unique_index(
            registries["ROUTE"]["routes"],
            key_field="route_code",
            source="route registry routes",
            expected_count=7,
        )
    )
    all_schema_ids = set(
        _unique_index(
            registries["SCHEMA"]["schemas"],
            key_field="schema_id",
            source="schema registry schemas",
            expected_count=14,
        )
    )
    generated_record = {
        "uri": f"repo://{OUTPUT_PATH.as_posix()}",
        "bytes": len(registry_content),
        "sha256": _sha256(registry_content),
    }
    manifest: dict[str, object] = {
        "document": {
            "id": "RAOS-AI-CONTRACT-REGISTRY-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0701",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": "scripts/build_st0701_ai_registry.py",
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "source_contract": {
                "uri": f"repo://{CONTRACT_PATH.as_posix()}",
                "sha256": EXPECTED_CONTRACT_SHA256,
            },
            "predecessors": [
                {
                    "story_id": "ST-0003",
                    **st0003_record,
                },
                {
                    "story_id": "ST-0104",
                    **repository_manifest_record,
                },
            ],
            "canonical_inputs": canonical_records,
            "compiler_inputs": compiler_inputs,
        },
        "source_artifact_count": len(story_sources),
        "source_artifacts": story_sources,
        "generated_artifact_count": 1,
        "generated_artifacts": [generated_record],
        "closure": {
            "registry_count": 4,
            "registry_entry_counts": {
                "tasks": 12,
                "prompts": 12,
                "schemas": 14,
                "routes": 7,
                "models": 3,
            },
            "compiler_input_count": len(compiler_inputs),
            "compiled_task_count": len(task_codes),
            "compiled_task_codes": task_codes,
            "bound_prompt_count": 12,
            "bound_task_output_schema_count": len(schema_ids),
            "bound_route_count": len(route_codes),
            "unbound_schema_ids": sorted(all_schema_ids - schema_ids),
            "unbound_route_codes": sorted(all_route_codes - route_codes),
            "cross_reference_verification": "COMPLETE_FAIL_CLOSED",
        },
        "integrity": {
            "source_repository_full_integrity": "VERIFIED",
            "compiled_registry_sha256": generated_record["sha256"],
            "strict_json_duplicate_keys": "REJECT",
            "unknown_task_or_hash_mismatch": "FAIL_CLOSED",
            "network_retrieval": "FORBIDDEN",
            "manifest_self_hash": "EXCLUDED_TO_AVOID_RECURSION",
            "manifest_verification": "DETERMINISTIC_BYTE_REGENERATION_VIA_CHECK",
        },
        "boundary": dict(_mapping(contract.get("boundary"), source="ST-0701 boundary")),
    }
    return yaml.dump(
        manifest,
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    registry_content = render_registry(root)
    return {
        OUTPUT_PATH: registry_content,
        MANIFEST_PATH: render_manifest(registry_content, root),
    }


def _install(relative: Path, content: bytes, root: Path = REPO_ROOT) -> None:
    if relative not in {OUTPUT_PATH, MANIFEST_PATH}:
        raise RuntimeError("unowned ST-0701 generated path")
    target = root / relative
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    parent_stat = parent.lstat()
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise RuntimeError("generated output parent must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    parent_descriptor = os.open(parent, directory_flags)
    temporary_name: str | None = None
    descriptor: int | None = None
    try:
        try:
            existing = os.stat(
                target.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise RuntimeError("generated output target must be a regular file")
        for suffix in range(100):
            candidate = f".{target.name}.st0701-{os.getpid()}-{suffix}"
            try:
                descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        if descriptor is None or temporary_name is None:
            raise RuntimeError("cannot allocate ST-0701 staging file")
        view = memoryview(content)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RuntimeError("short ST-0701 generated write")
            view = view[written:]
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.replace(
            temporary_name,
            target.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        os.close(parent_descriptor)


def _check_outputs(expected_outputs: Mapping[Path, bytes], root: Path) -> None:
    for relative, expected in expected_outputs.items():
        actual = _read_regular(
            root, relative, label=f"generated ST-0701 artifact {relative}"
        )
        if actual != expected:
            raise RuntimeError(f"generated ST-0701 artifact is out of date: {relative}")


def generate(*, check: bool, root: Path = REPO_ROOT) -> None:
    expected_outputs = render_outputs(root)
    if check:
        _check_outputs(expected_outputs, root)
        return
    for relative, content in expected_outputs.items():
        _install(relative, content, root)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    arguments = parser.parse_args(argv)
    try:
        generate(check=arguments.check)
    except (ContractRepositoryError, OSError, RuntimeError) as exc:
        print(f"ST-0701 registry generation failed: {exc}", file=sys.stderr)
        return 1
    print(
        "ST-0701 AI task registry is current"
        if arguments.check
        else "generated ST-0701 AI task registry"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
