#!/usr/bin/env python3
"""Generate deterministic Python and TypeScript bindings for ST-0105."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import pydantic
import yaml

_IMPORT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_IMPORT_ROOT / "python"))

from raos.shared.contract_repository import ContractRepository  # noqa: E402


REPO_ROOT: Final = _IMPORT_ROOT
CONTRACT_ROOT: Final = REPO_ROOT / "contracts" / "raos-v0.4"
CONTRACT_MANIFEST: Final = CONTRACT_ROOT / "contract-repository.v0.4.json"
CONTRACT_MANIFEST_PATH: Final = "contracts/raos-v0.4/contract-repository.v0.4.json"
CONTRACT_MANIFEST_SHA256: Final = (
    "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef"
)

STORY_ID: Final = "ST-0105"
DOCUMENT_ID: Final = "RAOS-CONTRACT-CODEGEN-001"
DOCUMENT_VERSION: Final = "1.0"
GENERATOR_PATH: Final = "scripts/build_st0105_generated_contracts.py"
MANIFEST_PATH: Final = REPO_ROOT / "changes" / "st-0105" / "manifest.json"
PYTHON_OUTPUT_ROOT: Final = REPO_ROOT / "python" / "raos" / "generated"
TYPESCRIPT_OUTPUT_ROOT: Final = (
    REPO_ROOT / "packages" / "web-contracts" / "src" / "generated"
)

EXPECTED_ARTIFACT_COUNT: Final = 306
EXPECTED_SCHEMA_COUNT: Final = 224
EXPECTED_OPENAPI_COUNT: Final = 3
EXPECTED_OPERATION_COUNT: Final = 185
EXPECTED_ASYNCAPI_COUNT: Final = 1
EXPECTED_PYTHON_VERSION: Final = "3.14.6"
EXPECTED_NODE_VERSION: Final = "v24.18.1"
EXPECTED_DATAMODEL_CODEGEN_VERSION: Final = "0.71.0"
EXPECTED_PYDANTIC_VERSION: Final = "2.13.4"
EXPECTED_OPENAPI_TS_VERSION: Final = "0.99.0"
EXPECTED_TYPESCRIPT_VERSION: Final = "6.0.3"
MAX_INPUT_BYTES: Final = 16 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 8 * 1024 * 1024
MAX_OUTPUT_TOTAL_BYTES: Final = 64 * 1024 * 1024
MAX_TRANSACTION_STATE_BYTES: Final = 64 * 1024
RENAME_EXCHANGE: Final = 2
TRANSACTION_DIRECTORY_NAME: Final = ".install-transaction.v1"
TRANSACTION_PREPARING_NAME: Final = ".install-transaction.v1.preparing"
TRANSACTION_CLEANUP_NAME: Final = ".install-transaction.v1.cleanup"
TRANSACTION_STATE_NAME: Final = "state.json"
TRANSACTION_STATE_TEMPORARY_NAME: Final = ".state.json.next"
TRANSACTION_PREVIOUS_MANIFEST_NAME: Final = "previous-manifest.json"
TRANSACTION_NEXT_MANIFEST_NAME: Final = "next-manifest.json"
MANIFEST_TEMPORARY_NAME: Final = ".manifest.json.st0105-next"
TRANSACTION_SCHEMA: Final = "raos-st0105-install-transaction-v1"
TRANSACTION_STATES: Final = frozenset(
    {"STAGING", "PREPARED", "COMMITTED", "ROLLED_BACK"}
)

OPENAPI_INPUTS: Final = (
    ("public", "contracts/openapi-public.v0.1.yaml"),
    ("admin", "contracts/openapi-admin.v0.4.yaml"),
    ("internal", "contracts/openapi-internal.v0.4.yaml"),
)
ASYNCAPI_INPUT: Final = "contracts/asyncapi.v0.4.yaml"
HTTP_METHODS: Final = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _checked_relative_path(value: str, *, source: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"unsafe relative path in {source}: {value!r}")
    return path


def _read_regular(path: Path, *, maximum: int, kind: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect {kind}: {path}") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise RuntimeError(f"required regular non-symlink {kind}: {path}")
    if before.st_size > maximum:
        raise RuntimeError(f"{kind} exceeds {maximum} bytes: {path}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(f"cannot open {kind}: {path}") from exc
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise RuntimeError(f"{kind} exceeds {maximum} bytes: {path}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(after.st_mode) or (
        before.st_dev,
        before.st_ino,
        before.st_size,
    ) != (after.st_dev, after.st_ino, after.st_size):
        raise RuntimeError(f"{kind} changed while being read: {path}")
    return b"".join(chunks)


def _type_name(index: int, path: str) -> str:
    words = [part for part in re.split(r"[^A-Za-z0-9]+", path) if part]
    suffix = "".join(word[:1].upper() + word[1:] for word in words)
    name = f"Schema{index:03d}{suffix}"
    if not name.isidentifier():
        raise RuntimeError(f"generated unsafe type name for {path}: {name}")
    return name


def _mapping(value: object, *, source: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"expected string-keyed mapping in {source}")
    return value


def _list(value: object, *, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"expected list in {source}")
    return value


def _yaml_document(content: bytes, *, source: str) -> dict[str, Any]:
    try:
        value = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"cannot parse YAML {source}: {exc}") from exc
    return _mapping(value, source=source)


def _package_version(
    path: Path, *, expected_name: str, expected_version: str, kind: str
) -> str:
    try:
        value = json.loads(_read_regular(path, maximum=1024 * 1024, kind=kind))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot parse {kind}: {path}") from exc
    package = _mapping(value, source=path.as_posix())
    if (
        package.get("name") != expected_name
        or package.get("version") != expected_version
    ):
        raise RuntimeError(
            f"{kind} identity/version mismatch: expected "
            f"{expected_name}=={expected_version}"
        )
    return expected_version


def _verify_physical_regular_path(
    path: Path, *, label: str, executable: bool
) -> None:
    if not path.is_absolute() or path.anchor != os.sep:
        raise RuntimeError(f"{label} path must be an absolute physical path: {path}")
    components = path.parts[1:]
    if not components:
        raise RuntimeError(f"{label} path cannot name the filesystem root")
    descriptor = os.open(os.sep, _directory_open_flags())
    try:
        for component in components[:-1]:
            _checked_entry_name(component, source=f"{label} path")
            try:
                next_descriptor = os.open(
                    component, _directory_open_flags(), dir_fd=descriptor
                )
            except OSError as exc:
                raise RuntimeError(
                    f"{label} has an unsafe or missing physical directory ancestor: "
                    f"{path}"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
        name = _checked_entry_name(components[-1], source=f"{label} path")
        try:
            metadata = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(f"missing {label}: {path}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"{label} must be a regular non-symlink file: {path}")
        if executable and not metadata.st_mode & 0o111:
            raise RuntimeError(f"{label} must be executable: {path}")
    finally:
        os.close(descriptor)


def _verify_tools(
    datamodel_codegen: Path, node: Path, openapi_ts: Path
) -> dict[str, str]:
    expected_datamodel_codegen = REPO_ROOT / ".venv/bin/datamodel-codegen"
    expected_openapi_ts = (
        REPO_ROOT / "node_modules/@hey-api/openapi-ts/bin/run.js"
    )
    if datamodel_codegen != expected_datamodel_codegen:
        raise RuntimeError(
            "datamodel-codegen must use the repository environment: "
            f"{expected_datamodel_codegen}"
        )
    if openapi_ts != expected_openapi_ts:
        raise RuntimeError(
            "openapi-ts must use the repository node_modules tree: "
            f"{expected_openapi_ts}"
        )
    _verify_physical_regular_path(
        datamodel_codegen, label="datamodel-codegen", executable=True
    )
    _verify_physical_regular_path(node, label="Node", executable=True)
    _verify_physical_regular_path(
        openapi_ts, label="openapi-ts entrypoint", executable=False
    )

    python_version = ".".join(str(value) for value in sys.version_info[:3])
    if (
        sys.implementation.name != "cpython"
        or python_version != EXPECTED_PYTHON_VERSION
    ):
        raise RuntimeError(
            "required CPython "
            f"{EXPECTED_PYTHON_VERSION}; found "
            f"{sys.implementation.name} {python_version}"
        )

    datamodel_result = _run(
        [str(datamodel_codegen), "--version"],
        cwd=REPO_ROOT,
        home=REPO_ROOT,
        timeout=30,
    )
    if datamodel_result.strip() != (
        f"datamodel-codegen {EXPECTED_DATAMODEL_CODEGEN_VERSION}"
    ):
        raise RuntimeError(
            "required datamodel-code-generator version "
            f"=={EXPECTED_DATAMODEL_CODEGEN_VERSION}; found "
            f"{datamodel_result.strip()!r}"
        )
    node_result = _run(
        [str(node), "--version"], cwd=REPO_ROOT, home=REPO_ROOT, timeout=30
    )
    if node_result.strip() != EXPECTED_NODE_VERSION:
        raise RuntimeError(
            f"required Node {EXPECTED_NODE_VERSION}; found {node_result.strip()!r}"
        )
    if pydantic.__version__ != EXPECTED_PYDANTIC_VERSION:
        raise RuntimeError(
            f"required Pydantic {EXPECTED_PYDANTIC_VERSION}; "
            f"found {pydantic.__version__}"
        )
    openapi_version = _package_version(
        openapi_ts.parents[1] / "package.json",
        expected_name="@hey-api/openapi-ts",
        expected_version=EXPECTED_OPENAPI_TS_VERSION,
        kind="openapi-ts package manifest",
    )
    typescript_root = REPO_ROOT / "node_modules" / "typescript"
    typescript_version = _package_version(
        typescript_root / "package.json",
        expected_name="typescript",
        expected_version=EXPECTED_TYPESCRIPT_VERSION,
        kind="TypeScript package manifest",
    )
    typescript_entrypoint = typescript_root / "bin" / "tsc"
    _verify_physical_regular_path(
        typescript_entrypoint,
        label="pinned TypeScript compiler",
        executable=False,
    )
    return {
        "python": python_version,
        "pydantic": pydantic.__version__,
        "datamodel-code-generator": datamodel_result.strip().split()[-1],
        "node": node_result.strip().removeprefix("v"),
        "@hey-api/openapi-ts": openapi_version,
        "typescript": typescript_version,
    }


def _run(command: Sequence[str], *, cwd: Path, home: Path, timeout: int = 180) -> str:
    environment = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TZ": "UTC",
        "CI": "1",
        "NO_COLOR": "1",
        "FORCE_COLOR": "0",
        "COREPACK_ENABLE_NETWORK": "0",
        "COREPACK_ENABLE_PROJECT_SPEC": "0",
        "NEXT_TELEMETRY_DISABLED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    try:
        result = subprocess.run(
            list(command),
            cwd=cwd,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="strict",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"generator command failed to execute: {command[0]}"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            f"generator command failed ({result.returncode}): "
            f"{' '.join(command[:2])}\n{result.stdout}{result.stderr}"
        )
    return result.stdout


def _copy_verified_inputs(
    repository: ContractRepository, source_root: Path
) -> dict[str, bytes]:
    artifacts = repository.artifacts
    if len(artifacts) != EXPECTED_ARTIFACT_COUNT:
        raise RuntimeError("contract repository artifact count drifted")
    copied: dict[str, bytes] = {}
    for artifact in artifacts:
        relative = _checked_relative_path(artifact.path, source=CONTRACT_MANIFEST_PATH)
        content = repository.read_bytes(artifact.path)
        if len(content) > MAX_INPUT_BYTES:
            raise RuntimeError(
                f"contract artifact exceeds input limit: {artifact.path}"
            )
        if len(content) != artifact.byte_count or _sha256(content) != artifact.sha256:
            raise RuntimeError(
                f"contract artifact changed during codegen: {artifact.path}"
            )
        target = source_root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        copied[artifact.path] = content
    return copied


def _schema_bindings(
    repository: ContractRepository,
) -> tuple[list[dict[str, object]], dict[str, dict[str, str]]]:
    schema_artifacts = sorted(
        (
            artifact
            for artifact in repository.artifacts
            if artifact.path.endswith(".schema.json")
        ),
        key=lambda item: item.path,
    )
    if len(schema_artifacts) != EXPECTED_SCHEMA_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_SCHEMA_COUNT} standalone schemas; "
            f"found {len(schema_artifacts)}"
        )
    bindings: list[dict[str, object]] = []
    references: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for index, artifact in enumerate(schema_artifacts, 1):
        document = _mapping(repository.load_json(artifact.path), source=artifact.path)
        schema_id = document.get("$id")
        if not isinstance(schema_id, str) or not schema_id:
            raise RuntimeError(f"standalone schema lacks string $id: {artifact.path}")
        if schema_id in seen_ids:
            raise RuntimeError(f"duplicate standalone schema $id: {schema_id}")
        seen_ids.add(schema_id)
        name = _type_name(index, artifact.path)
        if name in seen_names:
            raise RuntimeError(f"generated type-name collision: {name}")
        seen_names.add(name)
        references[name] = {"$ref": artifact.path}
        bindings.append(
            {
                "path": artifact.path,
                "schema_id": schema_id,
                "bytes": artifact.byte_count,
                "sha256": artifact.sha256,
                "type_name": name,
            }
        )
    return bindings, references


def _render_intermediates(
    source_root: Path, references: Mapping[str, Mapping[str, str]]
) -> dict[str, bytes]:
    json_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "RaosGeneratedContractModels",
        "type": "object",
        "$defs": dict(references),
        "properties": {name: {"$ref": f"#/$defs/{name}"} for name in references},
        "additionalProperties": False,
    }
    openapi = {
        "openapi": "3.1.1",
        "info": {
            "title": "RAOS standalone contract schemas",
            "version": "0.4",
        },
        "paths": {},
        "components": {"schemas": dict(references)},
    }
    rendered = {
        "st0105-codegen-root.schema.json": _json_bytes(json_schema),
        "st0105-schema-models.openapi.json": _json_bytes(openapi),
    }
    for name, content in rendered.items():
        (source_root / name).write_bytes(content)
    return rendered


def _prepend_provenance(root: Path, suffix: str, prefix: str) -> None:
    header = (
        f"{prefix} RAOS source: {CONTRACT_MANIFEST_PATH} "
        f"sha256={CONTRACT_MANIFEST_SHA256}\n"
        f"{prefix} RAOS generation: {GENERATOR_PATH}\n"
    ).encode("utf-8")
    for path in sorted(root.rglob(f"*{suffix}")):
        content = _read_regular(path, maximum=MAX_OUTPUT_BYTES, kind="generated file")
        path.write_bytes(header + content)


def _generate_python(
    datamodel_codegen: Path,
    temporary_root: Path,
    source_root: Path,
    bindings: Sequence[Mapping[str, object]],
) -> Path:
    python_root = temporary_root / "python" / "raos" / "generated"
    models_root = python_root / "contracts"
    python_root.mkdir(parents=True)
    (python_root / "__init__.py").write_text(
        '"""Generated RAOS contract model boundary. Do not edit."""\n\n'
        "from . import contracts\n\n"
        '__all__ = ["contracts"]\n',
        encoding="utf-8",
    )
    _run(
        [
            str(datamodel_codegen),
            "--input",
            str(source_root / "st0105-codegen-root.schema.json"),
            "--input-file-type",
            "jsonschema",
            "--output",
            str(models_root),
            "--output-model-type",
            "pydantic_v2.BaseModel",
            "--target-python-version",
            "3.14",
            "--disable-timestamp",
            "--use-standard-collections",
            "--use-union-operator",
            "--use-annotated",
            "--field-constraints",
            "--allow-population-by-field-name",
            "--snake-case-field",
            "--formatters",
            "builtin",
            "--no-color",
        ],
        cwd=temporary_root,
        home=temporary_root,
    )
    (models_root / "py.typed").write_bytes(b"")
    (models_root / "schema-index.json").write_bytes(
        _json_bytes({"schema_count": len(bindings), "schemas": list(bindings)})
    )
    _prepend_provenance(python_root, ".py", "#")

    names = [str(binding["type_name"]) for binding in bindings]
    probe = (
        "import sys\n"
        f"sys.path.insert(0, {str((temporary_root / 'python'))!r})\n"
        "from raos.generated import contracts\n"
        f"expected = {names!r}\n"
        "missing = [name for name in expected if not hasattr(contracts, name)]\n"
        "assert not missing, missing\n"
        "assert len(expected) == 224\n"
    )
    _run(
        [sys.executable, "-c", probe],
        cwd=temporary_root,
        home=temporary_root,
    )
    return python_root


def _operation_inventory(
    copied: Mapping[str, bytes],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    surfaces: list[dict[str, object]] = []
    all_operations: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    for surface, source_path in OPENAPI_INPUTS:
        document = _yaml_document(copied[source_path], source=source_path)
        version = document.get("openapi")
        if version != "3.1.1":
            raise RuntimeError(
                f"unsupported OpenAPI version in {source_path}: {version}"
            )
        paths = _mapping(document.get("paths"), source=f"{source_path}:paths")
        surface_operations: list[dict[str, object]] = []
        for route in sorted(paths):
            item = _mapping(paths[route], source=f"{source_path}:{route}")
            for method in sorted(HTTP_METHODS & set(item)):
                operation = _mapping(
                    item[method], source=f"{source_path}:{method}:{route}"
                )
                operation_id = operation.get("operationId")
                if not isinstance(operation_id, str) or not operation_id:
                    raise RuntimeError(
                        f"HTTP operation lacks operationId: {source_path}:{method}:{route}"
                    )
                if operation_id in seen_ids:
                    raise RuntimeError(f"duplicate HTTP operationId: {operation_id}")
                seen_ids.add(operation_id)
                row = {
                    "operation_id": operation_id,
                    "method": method.upper(),
                    "path": route,
                    "surface": surface,
                }
                surface_operations.append(row)
                all_operations.append(row)
        artifact_sha = _sha256(copied[source_path])
        surfaces.append(
            {
                "surface": surface,
                "source_path": source_path,
                "source_sha256": artifact_sha,
                "operation_count": len(surface_operations),
                "operation_ids": [row["operation_id"] for row in surface_operations],
            }
        )
    if len(all_operations) != EXPECTED_OPERATION_COUNT:
        raise RuntimeError(
            f"expected {EXPECTED_OPERATION_COUNT} HTTP operations; "
            f"found {len(all_operations)}"
        )
    return surfaces, all_operations


def _asyncapi_registry(content: bytes) -> tuple[dict[str, object], bytes]:
    document = _yaml_document(content, source=ASYNCAPI_INPUT)
    if document.get("asyncapi") != "3.0.0":
        raise RuntimeError("unsupported AsyncAPI version")
    channels = _mapping(document.get("channels"), source="AsyncAPI channels")
    operations = _mapping(document.get("operations"), source="AsyncAPI operations")
    components = _mapping(document.get("components"), source="AsyncAPI components")
    messages = _mapping(components.get("messages"), source="AsyncAPI messages")

    channel_rows: list[dict[str, object]] = []
    for name in sorted(channels):
        channel = _mapping(channels[name], source=f"AsyncAPI channel {name}")
        channel_messages = _mapping(
            channel.get("messages"), source=f"AsyncAPI channel messages {name}"
        )
        channel_rows.append(
            {
                "name": name,
                "address": channel.get("address"),
                "message_refs": [
                    _mapping(channel_messages[key], source=f"{name}:{key}").get("$ref")
                    for key in sorted(channel_messages)
                ],
            }
        )
    operation_rows: list[dict[str, object]] = []
    for name in sorted(operations):
        operation = _mapping(operations[name], source=f"AsyncAPI operation {name}")
        message_refs = _list(
            operation.get("messages", []), source=f"AsyncAPI operation messages {name}"
        )
        operation_rows.append(
            {
                "name": name,
                "action": operation.get("action"),
                "channel_ref": _mapping(
                    operation.get("channel"),
                    source=f"AsyncAPI operation channel {name}",
                ).get("$ref"),
                "message_refs": [
                    _mapping(item, source=f"AsyncAPI operation message {name}").get(
                        "$ref"
                    )
                    for item in message_refs
                ],
            }
        )
    message_rows: list[dict[str, object]] = []
    for name in sorted(messages):
        message = _mapping(messages[name], source=f"AsyncAPI message {name}")
        payload = _mapping(
            message.get("payload"), source=f"AsyncAPI message payload {name}"
        )
        message_rows.append(
            {
                "name": name,
                "payload_ref": payload.get("$ref"),
            }
        )
    registry = {
        "source_path": ASYNCAPI_INPUT,
        "source_sha256": _sha256(content),
        "channel_count": len(channel_rows),
        "operation_count": len(operation_rows),
        "message_count": len(message_rows),
        "channels": channel_rows,
        "operations": operation_rows,
        "messages": message_rows,
    }
    serialized = json.dumps(registry, ensure_ascii=False, sort_keys=True, indent=2)
    typescript = (
        "// This file is generated by scripts/build_st0105_generated_contracts.py.\n"
        "export const asyncApiContract = " + serialized + " as const;\n"
    ).encode("utf-8")
    return registry, typescript


def _generate_typescript(
    node: Path,
    openapi_ts: Path,
    temporary_root: Path,
    source_root: Path,
    copied: Mapping[str, bytes],
) -> tuple[Path, list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    typescript_root = (
        temporary_root / "packages" / "web-contracts" / "src" / "generated"
    )
    typescript_root.mkdir(parents=True)
    surfaces, operations = _operation_inventory(copied)
    for surface, source_path in OPENAPI_INPUTS:
        _run(
            [
                str(node),
                str(openapi_ts),
                "--input",
                str(source_root / source_path),
                "--output",
                str(typescript_root / "clients" / surface),
                "--client",
                "@hey-api/client-fetch",
                "--no-log-file",
                "--silent",
            ],
            cwd=temporary_root,
            home=temporary_root,
        )
    _run(
        [
            str(node),
            str(openapi_ts),
            "--input",
            str(source_root / "st0105-schema-models.openapi.json"),
            "--output",
            str(typescript_root / "schema-models"),
            "--plugins",
            "@hey-api/typescript",
            "--no-log-file",
            "--silent",
        ],
        cwd=temporary_root,
        home=temporary_root,
    )
    asyncapi, asyncapi_typescript = _asyncapi_registry(copied[ASYNCAPI_INPUT])
    (typescript_root / "asyncapi.gen.ts").write_bytes(asyncapi_typescript)
    (typescript_root / "index.ts").write_text(
        "// Generated RAOS contract entrypoint. Do not edit.\n"
        "export * as schemas from './schema-models/index';\n"
        "export * as publicApi from './clients/public/index';\n"
        "export * as adminApi from './clients/admin/index';\n"
        "export * as internalApi from './clients/internal/index';\n"
        "export { asyncApiContract } from './asyncapi.gen';\n",
        encoding="utf-8",
    )
    _prepend_provenance(typescript_root, ".ts", "//")

    tsc = REPO_ROOT / "node_modules" / "typescript" / "bin" / "tsc"
    if not tsc.is_file() or tsc.is_symlink():
        raise RuntimeError("pinned TypeScript compiler is missing or unsafe")
    tsconfig = temporary_root / "tsconfig.codegen.json"
    tsconfig.write_bytes(
        _json_bytes(
            {
                "extends": (REPO_ROOT / "tsconfig.base.json").as_posix(),
                "compilerOptions": {
                    "exactOptionalPropertyTypes": False,
                    "types": [],
                },
                "include": [
                    (
                        typescript_root.relative_to(temporary_root).as_posix()
                        + "/**/*.ts"
                    )
                ],
                "exclude": [],
            }
        )
    )
    _run(
        [str(node), str(tsc), "--noEmit", "--project", str(tsconfig)],
        cwd=temporary_root,
        home=temporary_root,
    )
    return typescript_root, surfaces, operations, asyncapi


def _tree_files(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        raise RuntimeError(f"generated output root is missing or unsafe: {root}")
    result: dict[str, bytes] = {}
    folded: set[str] = set()
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        metadata = path.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError(f"symlink in generated output: {path}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            raise RuntimeError(f"special file in generated output: {path}")
        _checked_relative_path(relative, source=root.as_posix())
        casefolded = relative.casefold()
        if casefolded in folded:
            raise RuntimeError(f"case-fold collision in generated output: {relative}")
        folded.add(casefolded)
        content = _read_regular(path, maximum=MAX_OUTPUT_BYTES, kind="generated output")
        total += len(content)
        if total > MAX_OUTPUT_TOTAL_BYTES:
            raise RuntimeError("generated output aggregate size limit exceeded")
        result[relative] = content
    if not result:
        raise RuntimeError(f"generated output tree is empty: {root}")
    return result


def _manifest(
    python_files: Mapping[str, bytes],
    typescript_files: Mapping[str, bytes],
    bindings: Sequence[Mapping[str, object]],
    intermediates: Mapping[str, bytes],
    surfaces: Sequence[Mapping[str, object]],
    operations: Sequence[Mapping[str, object]],
    asyncapi: Mapping[str, object],
    tool_versions: Mapping[str, str],
) -> bytes:
    artifacts: list[dict[str, object]] = []
    for root, files in (
        ("python/raos/generated", python_files),
        ("packages/web-contracts/src/generated", typescript_files),
    ):
        for path, content in sorted(files.items()):
            artifacts.append(
                {
                    "path": f"{root}/{path}",
                    "bytes": len(content),
                    "sha256": _sha256(content),
                }
            )
    artifacts.sort(key=lambda item: str(item["path"]))
    document = {
        "document": {
            "id": DOCUMENT_ID,
            "version": DOCUMENT_VERSION,
            "story_id": STORY_ID,
            "status": "IMPLEMENTED_NOT_VALIDATED",
            "generated_by": GENERATOR_PATH,
        },
        "source": {
            "contract_repository_manifest": CONTRACT_MANIFEST_PATH,
            "contract_repository_manifest_sha256": CONTRACT_MANIFEST_SHA256,
            "artifact_count": EXPECTED_ARTIFACT_COUNT,
            "standalone_schema_count": len(bindings),
            "openapi_count": EXPECTED_OPENAPI_COUNT,
            "asyncapi_count": EXPECTED_ASYNCAPI_COUNT,
            "network_retrieval": "FORBIDDEN",
        },
        "tools": dict(tool_versions),
        "intermediates": [
            {
                "name": name,
                "bytes": len(content),
                "sha256": _sha256(content),
                "committed": False,
            }
            for name, content in sorted(intermediates.items())
        ],
        "schema_bindings": list(bindings),
        "http_clients": list(surfaces),
        "http_operations": list(operations),
        "asyncapi_registry": dict(asyncapi),
        "outputs": {
            "boundary": "EXACT",
            "roots": [
                "python/raos/generated",
                "packages/web-contracts/src/generated",
            ],
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
        },
    }
    return _json_bytes(document)


def _render(
    temporary_root: Path,
    datamodel_codegen: Path,
    node: Path,
    openapi_ts: Path,
    tool_versions: Mapping[str, str],
) -> tuple[Path, Path, bytes, dict[str, object]]:
    manifest_content = _read_regular(
        CONTRACT_MANIFEST,
        maximum=2 * 1024 * 1024,
        kind="contract repository manifest",
    )
    if _sha256(manifest_content) != CONTRACT_MANIFEST_SHA256:
        raise RuntimeError("contract repository manifest SHA-256 drifted")
    repository = ContractRepository(CONTRACT_ROOT)
    source_root = temporary_root / "source"
    source_root.mkdir()
    copied = _copy_verified_inputs(repository, source_root)
    bindings, references = _schema_bindings(repository)
    intermediates = _render_intermediates(source_root, references)
    python_root = _generate_python(
        datamodel_codegen, temporary_root, source_root, bindings
    )
    typescript_root, surfaces, operations, asyncapi = _generate_typescript(
        node, openapi_ts, temporary_root, source_root, copied
    )
    python_files = _tree_files(python_root)
    typescript_files = _tree_files(typescript_root)
    temporary_bytes = str(temporary_root).encode("utf-8")
    if any(
        temporary_bytes in content
        for content in (*python_files.values(), *typescript_files.values())
    ):
        raise RuntimeError("generated output leaked its temporary absolute path")
    manifest = _manifest(
        python_files,
        typescript_files,
        bindings,
        intermediates,
        surfaces,
        operations,
        asyncapi,
        tool_versions,
    )
    report = {
        "python_files": len(python_files),
        "typescript_files": len(typescript_files),
        "schemas": len(bindings),
        "http_operations": len(operations),
        "asyncapi_messages": asyncapi["message_count"],
    }
    return python_root, typescript_root, manifest, report


def _expected_manifest_artifacts(content: bytes) -> dict[str, tuple[int, str]]:
    try:
        document = _mapping(json.loads(content), source=MANIFEST_PATH.as_posix())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("cannot parse generated codegen manifest") from exc
    outputs = _mapping(document.get("outputs"), source="manifest outputs")
    entries = _list(outputs.get("artifacts"), source="manifest artifacts")
    result: dict[str, tuple[int, str]] = {}
    previous = ""
    for raw in entries:
        entry = _mapping(raw, source="manifest artifact")
        if set(entry) != {"path", "bytes", "sha256"}:
            raise RuntimeError("malformed generated manifest artifact")
        path = entry["path"]
        byte_count = entry["bytes"]
        digest = entry["sha256"]
        if (
            not isinstance(path, str)
            or type(byte_count) is not int
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise RuntimeError("invalid generated manifest artifact metadata")
        _checked_relative_path(path, source=MANIFEST_PATH.as_posix())
        if previous and path <= previous:
            raise RuntimeError("generated manifest artifacts are not path-sorted")
        previous = path
        result[path] = (byte_count, digest)
    if outputs.get("artifact_count") != len(result):
        raise RuntimeError("generated manifest artifact count mismatch")
    return result


class InstallRecoveryRequired(RuntimeError):
    """An interrupted installation must retain its journal for later recovery."""


def _checkpoint(_name: str) -> None:
    """Fault-injection seam used by subprocess crash-recovery tests."""


def _directory_open_flags() -> int:
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise RuntimeError("ST-0105 installation requires O_DIRECTORY and O_NOFOLLOW")
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _checked_entry_name(name: str, *, source: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise RuntimeError(f"unsafe directory entry name in {source}: {name!r}")
    return name


def _open_managed_directory(path: Path, *, create: bool) -> int:
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise RuntimeError(f"managed path escapes physical repository root: {path}") from exc
    try:
        root_metadata = REPO_ROOT.lstat()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect physical repository root: {REPO_ROOT}") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError(f"unsafe physical repository root: {REPO_ROOT}")
    try:
        descriptor = os.open(REPO_ROOT, _directory_open_flags())
    except OSError as exc:
        raise RuntimeError(f"cannot open physical repository root: {REPO_ROOT}") from exc
    try:
        for component in relative.parts:
            _checked_entry_name(component, source=path.as_posix())
            if create:
                try:
                    os.mkdir(component, 0o755, dir_fd=descriptor)
                    os.fsync(descriptor)
                except FileExistsError:
                    pass
            try:
                next_descriptor = os.open(
                    component, _directory_open_flags(), dir_fd=descriptor
                )
            except OSError as exc:
                raise RuntimeError(
                    f"unsafe or missing managed directory component: {path}"
                ) from exc
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


@contextmanager
def _open_install_layout(
    *, exclusive: bool, create: bool
) -> Iterator[dict[str, int]]:
    layout: dict[str, int] = {}
    try:
        layout["manifest"] = _open_managed_directory(
            MANIFEST_PATH.parent, create=create
        )
        lock_mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
        try:
            fcntl.flock(layout["manifest"], lock_mode | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            raise RuntimeError("another ST-0105 install/check operation is active") from exc
        layout["python"] = _open_managed_directory(
            PYTHON_OUTPUT_ROOT.parent, create=create
        )
        layout["typescript"] = _open_managed_directory(
            TYPESCRIPT_OUTPUT_ROOT.parent, create=create
        )
        yield layout
    finally:
        for descriptor in reversed(list(layout.values())):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _entry_mode_at(parent_fd: int, name: str) -> int | None:
    _checked_entry_name(name, source="managed directory")
    try:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False).st_mode
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"cannot inspect managed entry: {name}") from exc


def _open_directory_at(parent_fd: int, name: str) -> int:
    _checked_entry_name(name, source="managed directory")
    try:
        return os.open(name, _directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(f"required non-symlink directory is unavailable: {name}") from exc


def _read_regular_at(
    parent_fd: int, name: str, *, maximum: int, kind: str
) -> bytes:
    _checked_entry_name(name, source=kind)
    mode = _entry_mode_at(parent_fd, name)
    if mode is None or stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise RuntimeError(f"required regular non-symlink {kind}: {name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(f"cannot open {kind}: {name}") from exc
    try:
        before = os.fstat(descriptor)
        if before.st_size > maximum:
            raise RuntimeError(f"{kind} exceeds {maximum} bytes: {name}")
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > maximum:
                raise RuntimeError(f"{kind} exceeds {maximum} bytes: {name}")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if not stat.S_ISREG(after.st_mode) or (
        before.st_dev,
        before.st_ino,
        before.st_size,
    ) != (after.st_dev, after.st_ino, after.st_size):
        raise RuntimeError(f"{kind} changed while being read: {name}")
    return b"".join(chunks)


def _optional_regular_at(
    parent_fd: int, name: str, *, maximum: int, kind: str
) -> bytes | None:
    if _entry_mode_at(parent_fd, name) is None:
        return None
    return _read_regular_at(parent_fd, name, maximum=maximum, kind=kind)


def _write_all(descriptor: int, content: bytes, *, kind: str) -> None:
    offset = 0
    while offset < len(content):
        written = os.write(descriptor, content[offset:])
        if written <= 0:
            raise RuntimeError(f"short write while creating {kind}")
        offset += written


def _create_regular_at(parent_fd: int, name: str, content: bytes, *, kind: str) -> None:
    _checked_entry_name(name, source=kind)
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(f"cannot create {kind}: {name}") from exc
    try:
        _write_all(descriptor, content, kind=kind)
        os.fchmod(descriptor, 0o644)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.fsync(parent_fd)


def _unlink_regular_at(parent_fd: int, name: str, *, kind: str) -> None:
    mode = _entry_mode_at(parent_fd, name)
    if mode is None:
        return
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise RuntimeError(f"refusing to unlink unsafe {kind}: {name}")
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _atomic_write_at(
    parent_fd: int,
    name: str,
    content: bytes,
    *,
    temporary_name: str,
    kind: str,
    checkpoint: str | None = None,
) -> None:
    if _entry_mode_at(parent_fd, temporary_name) is not None:
        raise RuntimeError(f"stale temporary {kind} requires recovery")
    _create_regular_at(parent_fd, temporary_name, content, kind=f"temporary {kind}")
    replaced = False
    try:
        os.replace(
            temporary_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        replaced = True
        if checkpoint is not None:
            _checkpoint(checkpoint)
        os.fsync(parent_fd)
    finally:
        if not replaced and _entry_mode_at(parent_fd, temporary_name) is not None:
            _unlink_regular_at(
                parent_fd, temporary_name, kind=f"temporary {kind}"
            )


def _tree_files_from_fd(root_fd: int) -> dict[str, bytes]:
    result: dict[str, bytes] = {}
    folded: set[str] = set()
    total = 0

    def visit(directory_fd: int, prefix: PurePosixPath | None) -> None:
        nonlocal total
        try:
            entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
        except OSError as exc:
            raise RuntimeError("cannot enumerate generated output") from exc
        for entry in entries:
            metadata = entry.stat(follow_symlinks=False)
            relative = (
                PurePosixPath(entry.name)
                if prefix is None
                else prefix / entry.name
            )
            relative_text = relative.as_posix()
            _checked_relative_path(relative_text, source="generated output")
            if stat.S_ISLNK(metadata.st_mode):
                raise RuntimeError(f"symlink in generated output: {relative_text}")
            if stat.S_ISDIR(metadata.st_mode):
                child_fd = _open_directory_at(directory_fd, entry.name)
                try:
                    visit(child_fd, relative)
                finally:
                    os.close(child_fd)
                continue
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError(f"special file in generated output: {relative_text}")
            casefolded = relative_text.casefold()
            if casefolded in folded:
                raise RuntimeError(
                    f"case-fold collision in generated output: {relative_text}"
                )
            folded.add(casefolded)
            content = _read_regular_at(
                directory_fd,
                entry.name,
                maximum=MAX_OUTPUT_BYTES,
                kind="generated output",
            )
            total += len(content)
            if total > MAX_OUTPUT_TOTAL_BYTES:
                raise RuntimeError("generated output aggregate size limit exceeded")
            result[relative_text] = content

    visit(root_fd, None)
    if not result:
        raise RuntimeError("generated output tree is empty")
    return result


def _tree_files_at(parent_fd: int, name: str) -> dict[str, bytes]:
    root_fd = _open_directory_at(parent_fd, name)
    try:
        return _tree_files_from_fd(root_fd)
    finally:
        os.close(root_fd)


def _remove_directory_contents(
    directory_fd: int, *, checkpoint: str | None = None
) -> None:
    entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
    for entry in entries:
        metadata = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            child_fd = _open_directory_at(directory_fd, entry.name)
            try:
                _remove_directory_contents(child_fd, checkpoint=checkpoint)
            finally:
                os.close(child_fd)
            os.rmdir(entry.name, dir_fd=directory_fd)
        else:
            os.unlink(entry.name, dir_fd=directory_fd)
        if checkpoint is not None:
            _checkpoint(checkpoint)
    os.fsync(directory_fd)


def _remove_tree_at(
    parent_fd: int, name: str, *, checkpoint: str | None = None
) -> None:
    mode = _entry_mode_at(parent_fd, name)
    if mode is None:
        return
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        raise RuntimeError(f"refusing to remove unsafe managed tree: {name}")
    directory_fd = _open_directory_at(parent_fd, name)
    try:
        _remove_directory_contents(directory_fd, checkpoint=checkpoint)
    finally:
        os.close(directory_fd)
    os.rmdir(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _fsync_tree_directories(directory_fd: int) -> None:
    entries = sorted(os.scandir(directory_fd), key=lambda item: item.name)
    for entry in entries:
        metadata = entry.stat(follow_symlinks=False)
        if stat.S_ISDIR(metadata.st_mode) and not stat.S_ISLNK(metadata.st_mode):
            child_fd = _open_directory_at(directory_fd, entry.name)
            try:
                _fsync_tree_directories(child_fd)
            finally:
                os.close(child_fd)
    os.fsync(directory_fd)


def _write_tree_at(parent_fd: int, name: str, files: Mapping[str, bytes]) -> None:
    if not files:
        raise RuntimeError("refusing to stage an empty generated tree")
    if _entry_mode_at(parent_fd, name) is not None:
        raise RuntimeError(f"generated stage already exists: {name}")
    os.mkdir(name, 0o700, dir_fd=parent_fd)
    os.fsync(parent_fd)
    root_fd = _open_directory_at(parent_fd, name)
    try:
        for relative_text, content in sorted(files.items()):
            relative = _checked_relative_path(
                relative_text, source="rendered generated tree"
            )
            current_fd = os.dup(root_fd)
            try:
                for component in relative.parts[:-1]:
                    try:
                        os.mkdir(component, 0o755, dir_fd=current_fd)
                        os.fsync(current_fd)
                    except FileExistsError:
                        pass
                    next_fd = _open_directory_at(current_fd, component)
                    os.close(current_fd)
                    current_fd = next_fd
                _create_regular_at(
                    current_fd,
                    relative.parts[-1],
                    content,
                    kind="staged generated file",
                )
            finally:
                os.close(current_fd)
        _fsync_tree_directories(root_fd)
    finally:
        os.close(root_fd)
    os.fsync(parent_fd)


def _manifest_tree_inventory(
    content: bytes, prefix: str
) -> dict[str, tuple[int, str]]:
    expected = _expected_manifest_artifacts(content)
    marker = f"{prefix}/"
    result = {
        path.removeprefix(marker): metadata
        for path, metadata in expected.items()
        if path.startswith(marker)
    }
    if not result:
        raise RuntimeError(f"manifest has no artifacts for generated root: {prefix}")
    return result


def _tree_matches_inventory(
    files: Mapping[str, bytes], expected: Mapping[str, tuple[int, str]]
) -> bool:
    return set(files) == set(expected) and all(
        len(files[path]) == expected[path][0]
        and _sha256(files[path]) == expected[path][1]
        for path in files
    )


def _classify_tree_at(
    parent_fd: int,
    name: str,
    *,
    old: Mapping[str, tuple[int, str]] | None,
    new: Mapping[str, tuple[int, str]],
) -> str:
    mode = _entry_mode_at(parent_fd, name)
    if mode is None:
        return "missing"
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        return "unknown"
    try:
        files = _tree_files_at(parent_fd, name)
    except RuntimeError:
        return "unknown"
    matches_old = old is not None and _tree_matches_inventory(files, old)
    matches_new = _tree_matches_inventory(files, new)
    if matches_old and matches_new:
        return "both"
    if matches_old:
        return "old"
    if matches_new:
        return "new"
    return "unknown"


def _verify_installed_exact_locked(
    manifest_content: bytes, layout: Mapping[str, int]
) -> None:
    expected = _expected_manifest_artifacts(manifest_content)
    actual: dict[str, bytes] = {}
    for key, name, prefix in (
        ("python", PYTHON_OUTPUT_ROOT.name, "python/raos/generated"),
        (
            "typescript",
            TYPESCRIPT_OUTPUT_ROOT.name,
            "packages/web-contracts/src/generated",
        ),
    ):
        for path, content in _tree_files_at(layout[key], name).items():
            actual[f"{prefix}/{path}"] = content
    if set(actual) != set(expected):
        raise RuntimeError(
            "generated output inventory drift; "
            f"missing={sorted(set(expected) - set(actual))}, "
            f"extra={sorted(set(actual) - set(expected))}"
        )
    for path, content in actual.items():
        byte_count, digest = expected[path]
        if len(content) != byte_count or _sha256(content) != digest:
            raise RuntimeError(f"generated output hash drift: {path}")


def _verify_installed_exact(manifest_content: bytes) -> None:
    with _open_install_layout(exclusive=False, create=False) as layout:
        _assert_no_pending_transaction_locked(layout)
        _verify_installed_exact_locked(manifest_content, layout)


def _compare_locked(
    rendered_python: Path,
    rendered_typescript: Path,
    manifest: bytes,
    layout: Mapping[str, int],
) -> None:
    installed_manifest = _read_regular_at(
        layout["manifest"],
        MANIFEST_PATH.name,
        maximum=16 * 1024 * 1024,
        kind="ST-0105 codegen manifest",
    )
    if installed_manifest != manifest:
        raise RuntimeError("ST-0105 codegen manifest drifted")
    _verify_installed_exact_locked(installed_manifest, layout)
    if _tree_files_at(layout["python"], PYTHON_OUTPUT_ROOT.name) != _tree_files(
        rendered_python
    ):
        raise RuntimeError("generated Python tree drifted")
    if _tree_files_at(
        layout["typescript"], TYPESCRIPT_OUTPUT_ROOT.name
    ) != _tree_files(rendered_typescript):
        raise RuntimeError("generated TypeScript tree drifted")


def _compare(rendered_python: Path, rendered_typescript: Path, manifest: bytes) -> None:
    with _open_install_layout(exclusive=False, create=False) as layout:
        _assert_no_pending_transaction_locked(layout)
        _compare_locked(rendered_python, rendered_typescript, manifest, layout)


def _rename_exchange_at(parent_fd: int, left: str, right: str) -> None:
    _checked_entry_name(left, source="atomic exchange")
    _checked_entry_name(right, source="atomic exchange")
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except (AttributeError, OSError) as exc:
        raise RuntimeError("atomic directory exchange requires renameat2") from exc
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
        os.fsencode(left),
        parent_fd,
        os.fsencode(right),
        RENAME_EXCHANGE,
    )
    if result != 0:
        error = ctypes.get_errno()
        raise RuntimeError(
            f"atomic directory exchange failed: {os.strerror(error)} (errno={error})"
        )


def _transaction_id() -> str:
    return os.urandom(16).hex()


def _transaction_state_document(
    *,
    transaction_id: str,
    state: str,
    had_previous: bool,
    stages: Mapping[str, str],
    previous_manifest: bytes | None,
    next_manifest: bytes,
) -> dict[str, object]:
    return {
        "schema": TRANSACTION_SCHEMA,
        "transaction_id": transaction_id,
        "state": state,
        "had_previous": had_previous,
        "stages": dict(stages),
        "previous_manifest_sha256": (
            _sha256(previous_manifest) if previous_manifest is not None else None
        ),
        "next_manifest_sha256": _sha256(next_manifest),
    }


def _validate_transaction_state(value: object) -> dict[str, Any]:
    state = _mapping(value, source="ST-0105 transaction state")
    if set(state) != {
        "schema",
        "transaction_id",
        "state",
        "had_previous",
        "stages",
        "previous_manifest_sha256",
        "next_manifest_sha256",
    }:
        raise RuntimeError("malformed ST-0105 transaction state keys")
    transaction_id = state.get("transaction_id")
    if state.get("schema") != TRANSACTION_SCHEMA or not isinstance(
        transaction_id, str
    ) or not re.fullmatch(r"[0-9a-f]{32}", transaction_id):
        raise RuntimeError("malformed ST-0105 transaction identity")
    if state.get("state") not in TRANSACTION_STATES or type(
        state.get("had_previous")
    ) is not bool:
        raise RuntimeError("malformed ST-0105 transaction phase")
    stages = _mapping(state.get("stages"), source="ST-0105 transaction stages")
    expected_stages = {
        "python": f".{PYTHON_OUTPUT_ROOT.name}.st0105.{transaction_id}.python",
        "typescript": (
            f".{TYPESCRIPT_OUTPUT_ROOT.name}.st0105.{transaction_id}.typescript"
        ),
    }
    if stages != expected_stages:
        raise RuntimeError("malformed ST-0105 transaction stage names")
    previous_digest = state.get("previous_manifest_sha256")
    next_digest = state.get("next_manifest_sha256")
    if (
        previous_digest is not None
        and (
            not isinstance(previous_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", previous_digest)
        )
    ) or not isinstance(next_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", next_digest
    ):
        raise RuntimeError("malformed ST-0105 transaction manifest digests")
    if (previous_digest is not None) != state["had_previous"]:
        raise RuntimeError("ST-0105 transaction prior-state mismatch")
    return state


def _transaction_entry_names(had_previous: bool) -> set[str]:
    names = {TRANSACTION_STATE_NAME, TRANSACTION_NEXT_MANIFEST_NAME}
    if had_previous:
        names.add(TRANSACTION_PREVIOUS_MANIFEST_NAME)
    return names


def _create_transaction_locked(
    layout: Mapping[str, int], previous_manifest: bytes | None, next_manifest: bytes
) -> dict[str, Any]:
    manifest_fd = layout["manifest"]
    transaction_names = (
        TRANSACTION_DIRECTORY_NAME,
        TRANSACTION_PREPARING_NAME,
        TRANSACTION_CLEANUP_NAME,
    )
    if any(_entry_mode_at(manifest_fd, name) is not None for name in transaction_names):
        raise RuntimeError("pending ST-0105 transaction requires recovery")
    transaction_id = _transaction_id()
    stages = {
        "python": f".{PYTHON_OUTPUT_ROOT.name}.st0105.{transaction_id}.python",
        "typescript": (
            f".{TYPESCRIPT_OUTPUT_ROOT.name}.st0105.{transaction_id}.typescript"
        ),
    }
    state = _transaction_state_document(
        transaction_id=transaction_id,
        state="STAGING",
        had_previous=previous_manifest is not None,
        stages=stages,
        previous_manifest=previous_manifest,
        next_manifest=next_manifest,
    )
    os.mkdir(TRANSACTION_PREPARING_NAME, 0o700, dir_fd=manifest_fd)
    os.fsync(manifest_fd)
    preparing_fd = _open_directory_at(manifest_fd, TRANSACTION_PREPARING_NAME)
    try:
        _create_regular_at(
            preparing_fd,
            TRANSACTION_STATE_NAME,
            _json_bytes(state),
            kind="ST-0105 transaction state",
        )
        if previous_manifest is not None:
            _create_regular_at(
                preparing_fd,
                TRANSACTION_PREVIOUS_MANIFEST_NAME,
                previous_manifest,
                kind="ST-0105 previous manifest",
            )
        _create_regular_at(
            preparing_fd,
            TRANSACTION_NEXT_MANIFEST_NAME,
            next_manifest,
            kind="ST-0105 next manifest",
        )
        os.fsync(preparing_fd)
    finally:
        os.close(preparing_fd)
    os.replace(
        TRANSACTION_PREPARING_NAME,
        TRANSACTION_DIRECTORY_NAME,
        src_dir_fd=manifest_fd,
        dst_dir_fd=manifest_fd,
    )
    os.fsync(manifest_fd)
    _checkpoint("after-journal-publish")
    return _validate_transaction_state(state)


def _cleanup_transaction_state_temporary(journal_fd: int) -> None:
    mode = _entry_mode_at(journal_fd, TRANSACTION_STATE_TEMPORARY_NAME)
    if mode is None:
        return
    _unlink_regular_at(
        journal_fd,
        TRANSACTION_STATE_TEMPORARY_NAME,
        kind="transaction-state temporary",
    )


def _load_transaction_locked(
    layout: Mapping[str, int], *, cleanup_temporary: bool
) -> tuple[dict[str, Any], bytes | None, bytes]:
    journal_fd = _open_directory_at(
        layout["manifest"], TRANSACTION_DIRECTORY_NAME
    )
    try:
        if cleanup_temporary:
            _cleanup_transaction_state_temporary(journal_fd)
        state_content = _read_regular_at(
            journal_fd,
            TRANSACTION_STATE_NAME,
            maximum=MAX_TRANSACTION_STATE_BYTES,
            kind="ST-0105 transaction state",
        )
        try:
            state_value = json.loads(state_content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("cannot parse ST-0105 transaction state") from exc
        state = _validate_transaction_state(state_value)
        previous_manifest = (
            _read_regular_at(
                journal_fd,
                TRANSACTION_PREVIOUS_MANIFEST_NAME,
                maximum=16 * 1024 * 1024,
                kind="ST-0105 previous manifest",
            )
            if state["had_previous"]
            else None
        )
        next_manifest = _read_regular_at(
            journal_fd,
            TRANSACTION_NEXT_MANIFEST_NAME,
            maximum=16 * 1024 * 1024,
            kind="ST-0105 next manifest",
        )
        actual_names = {entry.name for entry in os.scandir(journal_fd)}
        if actual_names != _transaction_entry_names(state["had_previous"]):
            raise RuntimeError("unexpected file in ST-0105 transaction journal")
    finally:
        os.close(journal_fd)
    if (
        previous_manifest is not None
        and _sha256(previous_manifest) != state["previous_manifest_sha256"]
    ) or _sha256(next_manifest) != state["next_manifest_sha256"]:
        raise RuntimeError("ST-0105 transaction manifest digest mismatch")
    if previous_manifest is not None:
        _expected_manifest_artifacts(previous_manifest)
    _expected_manifest_artifacts(next_manifest)
    return state, previous_manifest, next_manifest


def _write_transaction_phase_locked(
    layout: Mapping[str, int], state: Mapping[str, Any], phase: str
) -> dict[str, Any]:
    if phase not in TRANSACTION_STATES:
        raise RuntimeError(f"invalid ST-0105 transaction phase: {phase}")
    updated = {**state, "state": phase}
    validated = _validate_transaction_state(updated)
    journal_fd = _open_directory_at(
        layout["manifest"], TRANSACTION_DIRECTORY_NAME
    )
    try:
        _atomic_write_at(
            journal_fd,
            TRANSACTION_STATE_NAME,
            _json_bytes(validated),
            temporary_name=TRANSACTION_STATE_TEMPORARY_NAME,
            kind="ST-0105 transaction state",
        )
    finally:
        os.close(journal_fd)
    return validated


def _validate_previous_state_locked(
    layout: Mapping[str, int], previous_manifest: bytes | None
) -> None:
    current_manifest = _optional_regular_at(
        layout["manifest"],
        MANIFEST_PATH.name,
        maximum=16 * 1024 * 1024,
        kind="ST-0105 manifest",
    )
    if previous_manifest is None:
        if current_manifest is not None or any(
            _entry_mode_at(layout[key], name) is not None
            for key, name in (
                ("python", PYTHON_OUTPUT_ROOT.name),
                ("typescript", TYPESCRIPT_OUTPUT_ROOT.name),
            )
        ):
            raise RuntimeError("fresh ST-0105 state was not restored")
        return
    if current_manifest != previous_manifest:
        raise RuntimeError("previous ST-0105 manifest was not restored")
    _verify_installed_exact_locked(previous_manifest, layout)


def _validate_next_state_locked(
    layout: Mapping[str, int], next_manifest: bytes
) -> None:
    current_manifest = _read_regular_at(
        layout["manifest"],
        MANIFEST_PATH.name,
        maximum=16 * 1024 * 1024,
        kind="ST-0105 manifest",
    )
    if current_manifest != next_manifest:
        raise RuntimeError("committed ST-0105 manifest does not match journal")
    _verify_installed_exact_locked(next_manifest, layout)


def _restore_tree_locked(
    *,
    parent_fd: int,
    destination: str,
    stage: str,
    old: Mapping[str, tuple[int, str]] | None,
    new: Mapping[str, tuple[int, str]],
    checkpoint: str,
) -> None:
    destination_state = _classify_tree_at(
        parent_fd, destination, old=old, new=new
    )
    stage_state = _classify_tree_at(parent_fd, stage, old=old, new=new)
    if old is not None:
        if destination_state in {"old", "both"}:
            os.fsync(parent_fd)
            return
        if destination_state == "new" and stage_state in {"old", "both"}:
            _rename_exchange_at(parent_fd, stage, destination)
            _checkpoint(checkpoint)
            os.fsync(parent_fd)
            return
        if destination_state == "missing" and stage_state in {"old", "both"}:
            os.replace(
                stage,
                destination,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            _checkpoint(checkpoint)
            os.fsync(parent_fd)
            return
    else:
        if destination_state == "missing":
            os.fsync(parent_fd)
            return
        if destination_state == "new" and stage_state == "missing":
            os.replace(
                destination,
                stage,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            _checkpoint(checkpoint)
            os.fsync(parent_fd)
            return
    raise RuntimeError(
        "cannot determine safe ST-0105 rollback direction: "
        f"destination={destination_state}, stage={stage_state}"
    )


def _restore_manifest_locked(
    layout: Mapping[str, int], previous_manifest: bytes | None, next_manifest: bytes
) -> None:
    manifest_fd = layout["manifest"]
    _unlink_regular_at(
        manifest_fd,
        MANIFEST_TEMPORARY_NAME,
        kind="manifest temporary",
    )
    current = _optional_regular_at(
        manifest_fd,
        MANIFEST_PATH.name,
        maximum=16 * 1024 * 1024,
        kind="ST-0105 manifest",
    )
    if previous_manifest is not None:
        if current == previous_manifest:
            os.fsync(manifest_fd)
            return
        if current != next_manifest:
            raise RuntimeError("refusing to overwrite unknown ST-0105 manifest")
        _atomic_write_at(
            manifest_fd,
            MANIFEST_PATH.name,
            previous_manifest,
            temporary_name=MANIFEST_TEMPORARY_NAME,
            kind="ST-0105 manifest",
            checkpoint="after-recovery-manifest-namespace",
        )
        return
    if current is None:
        os.fsync(manifest_fd)
        return
    if current != next_manifest:
        raise RuntimeError("refusing to unlink unknown ST-0105 manifest")
    _unlink_regular_at(manifest_fd, MANIFEST_PATH.name, kind="ST-0105 manifest")
    _checkpoint("after-recovery-manifest-namespace")


def _recover_prepared_locked(
    layout: Mapping[str, int],
    state: Mapping[str, Any],
    previous_manifest: bytes | None,
    next_manifest: bytes,
) -> dict[str, Any]:
    errors: list[str] = []
    previous_inventories = (
        {
            "python": _manifest_tree_inventory(
                previous_manifest, "python/raos/generated"
            ),
            "typescript": _manifest_tree_inventory(
                previous_manifest, "packages/web-contracts/src/generated"
            ),
        }
        if previous_manifest is not None
        else {"python": None, "typescript": None}
    )
    next_inventories = {
        "python": _manifest_tree_inventory(next_manifest, "python/raos/generated"),
        "typescript": _manifest_tree_inventory(
            next_manifest, "packages/web-contracts/src/generated"
        ),
    }
    for key, destination in (
        ("python", PYTHON_OUTPUT_ROOT.name),
        ("typescript", TYPESCRIPT_OUTPUT_ROOT.name),
    ):
        try:
            _restore_tree_locked(
                parent_fd=layout[key],
                destination=destination,
                stage=state["stages"][key],
                old=previous_inventories[key],
                new=next_inventories[key],
                checkpoint=f"after-recovery-{key}-namespace",
            )
        except BaseException as exc:
            errors.append(f"{key} tree: {exc}")
    try:
        _restore_manifest_locked(layout, previous_manifest, next_manifest)
    except BaseException as exc:
        errors.append(f"manifest: {exc}")
    try:
        _validate_previous_state_locked(layout, previous_manifest)
    except BaseException as exc:
        errors.append(f"restored-state verification: {exc}")
    if errors:
        raise InstallRecoveryRequired(
            "ST-0105 rollback requires another install invocation; "
            + "; ".join(errors)
        )
    rolled_back = _write_transaction_phase_locked(layout, state, "ROLLED_BACK")
    _checkpoint("after-rolled-back-state")
    return rolled_back


def _cleanup_terminal_transaction_locked(
    layout: Mapping[str, int],
    state: Mapping[str, Any],
    previous_manifest: bytes | None,
    next_manifest: bytes,
) -> None:
    if state["state"] == "COMMITTED":
        _validate_next_state_locked(layout, next_manifest)
    elif state["state"] == "ROLLED_BACK":
        _validate_previous_state_locked(layout, previous_manifest)
    else:
        raise RuntimeError("transaction cleanup requires a terminal phase")
    errors: list[str] = []
    for key in ("python", "typescript"):
        try:
            _remove_tree_at(layout[key], state["stages"][key])
            _checkpoint(f"after-{key}-stage-cleanup")
        except BaseException as exc:
            errors.append(f"{key} stage cleanup: {exc}")
    try:
        _unlink_regular_at(
            layout["manifest"],
            MANIFEST_TEMPORARY_NAME,
            kind="manifest temporary",
        )
    except BaseException as exc:
        errors.append(f"manifest temporary cleanup: {exc}")
    if errors:
        raise InstallRecoveryRequired(
            "terminal ST-0105 transaction cleanup is incomplete; "
            + "; ".join(errors)
        )
    os.replace(
        TRANSACTION_DIRECTORY_NAME,
        TRANSACTION_CLEANUP_NAME,
        src_dir_fd=layout["manifest"],
        dst_dir_fd=layout["manifest"],
    )
    _checkpoint("after-journal-tombstone-namespace")
    os.fsync(layout["manifest"])
    _remove_tree_at(
        layout["manifest"],
        TRANSACTION_CLEANUP_NAME,
        checkpoint="during-journal-tombstone-cleanup",
    )
    _checkpoint("after-journal-cleanup")


def _recover_pending_transaction_locked(layout: Mapping[str, int]) -> None:
    manifest_fd = layout["manifest"]
    preparing_mode = _entry_mode_at(manifest_fd, TRANSACTION_PREPARING_NAME)
    transaction_mode = _entry_mode_at(manifest_fd, TRANSACTION_DIRECTORY_NAME)
    cleanup_mode = _entry_mode_at(manifest_fd, TRANSACTION_CLEANUP_NAME)
    if cleanup_mode is not None:
        if preparing_mode is not None or transaction_mode is not None:
            raise InstallRecoveryRequired(
                "cleanup tombstone conflicts with another ST-0105 transaction"
            )
        _remove_tree_at(
            manifest_fd,
            TRANSACTION_CLEANUP_NAME,
            checkpoint="during-journal-tombstone-cleanup",
        )
        _checkpoint("after-cleanup-tombstone")
        preparing_mode = _entry_mode_at(manifest_fd, TRANSACTION_PREPARING_NAME)
        transaction_mode = _entry_mode_at(manifest_fd, TRANSACTION_DIRECTORY_NAME)
    if preparing_mode is not None:
        if transaction_mode is not None:
            raise InstallRecoveryRequired(
                "both preparing and published ST-0105 transactions exist"
            )
        _remove_tree_at(manifest_fd, TRANSACTION_PREPARING_NAME)
        _checkpoint("after-preparing-cleanup")
    if transaction_mode is None:
        _unlink_regular_at(
            manifest_fd,
            MANIFEST_TEMPORARY_NAME,
            kind="manifest temporary",
        )
        return
    if stat.S_ISLNK(transaction_mode) or not stat.S_ISDIR(transaction_mode):
        raise InstallRecoveryRequired("unsafe ST-0105 transaction journal")
    state, previous_manifest, next_manifest = _load_transaction_locked(
        layout, cleanup_temporary=True
    )
    if state["state"] == "STAGING":
        _validate_previous_state_locked(layout, previous_manifest)
        state = _write_transaction_phase_locked(layout, state, "ROLLED_BACK")
    elif state["state"] == "PREPARED":
        state = _recover_prepared_locked(
            layout, state, previous_manifest, next_manifest
        )
    _cleanup_terminal_transaction_locked(
        layout, state, previous_manifest, next_manifest
    )


def _assert_no_pending_transaction_locked(layout: Mapping[str, int]) -> None:
    pending = [
        name
        for name in (
            TRANSACTION_PREPARING_NAME,
            TRANSACTION_DIRECTORY_NAME,
            TRANSACTION_CLEANUP_NAME,
            MANIFEST_TEMPORARY_NAME,
        )
        if _entry_mode_at(layout["manifest"], name) is not None
    ]
    if pending:
        raise InstallRecoveryRequired(
            "read-only operation found pending ST-0105 recovery; "
            "run the mutating install command: "
            + ", ".join(pending)
        )


def _recover_pending_transaction() -> None:
    with _open_install_layout(exclusive=True, create=True) as layout:
        _recover_pending_transaction_locked(layout)
        _checkpoint("after-startup-recovery")


def _install(rendered_python: Path, rendered_typescript: Path, manifest: bytes) -> None:
    rendered_files = {
        "python": _tree_files(rendered_python),
        "typescript": _tree_files(rendered_typescript),
    }
    next_inventories = {
        "python": _manifest_tree_inventory(manifest, "python/raos/generated"),
        "typescript": _manifest_tree_inventory(
            manifest, "packages/web-contracts/src/generated"
        ),
    }
    if any(
        not _tree_matches_inventory(rendered_files[key], next_inventories[key])
        for key in ("python", "typescript")
    ):
        raise RuntimeError("rendered ST-0105 trees do not match the next manifest")

    with _open_install_layout(exclusive=True, create=True) as layout:
        _recover_pending_transaction_locked(layout)
        _checkpoint("after-startup-recovery")
        manifest_mode = _entry_mode_at(layout["manifest"], MANIFEST_PATH.name)
        output_modes = {
            "python": _entry_mode_at(layout["python"], PYTHON_OUTPUT_ROOT.name),
            "typescript": _entry_mode_at(
                layout["typescript"], TYPESCRIPT_OUTPUT_ROOT.name
            ),
        }
        if any(
            mode is not None and (stat.S_ISLNK(mode) or not stat.S_ISDIR(mode))
            for mode in output_modes.values()
        ) or (
            manifest_mode is not None
            and (stat.S_ISLNK(manifest_mode) or not stat.S_ISREG(manifest_mode))
        ):
            raise RuntimeError("unsafe existing ST-0105 installation")
        exists = {key: mode is not None for key, mode in output_modes.items()}
        manifest_exists = manifest_mode is not None
        if len(set((*exists.values(), manifest_exists))) != 1:
            raise RuntimeError("partial existing ST-0105 installation")
        previous_manifest = (
            _read_regular_at(
                layout["manifest"],
                MANIFEST_PATH.name,
                maximum=16 * 1024 * 1024,
                kind="existing ST-0105 manifest",
            )
            if manifest_exists
            else None
        )
        if previous_manifest is not None:
            _verify_installed_exact_locked(previous_manifest, layout)

        try:
            state = _create_transaction_locked(
                layout, previous_manifest, manifest
            )
            for key in ("python", "typescript"):
                _write_tree_at(
                    layout[key], state["stages"][key], rendered_files[key]
                )
                if _classify_tree_at(
                    layout[key],
                    state["stages"][key],
                    old=None,
                    new=next_inventories[key],
                ) != "new":
                    raise RuntimeError(f"staged {key} tree verification failed")
                _checkpoint(f"after-{key}-stage")
            state = _write_transaction_phase_locked(layout, state, "PREPARED")
            _checkpoint("after-prepared-state")

            for key, destination in (
                ("python", PYTHON_OUTPUT_ROOT.name),
                ("typescript", TYPESCRIPT_OUTPUT_ROOT.name),
            ):
                stage = state["stages"][key]
                if previous_manifest is not None:
                    _rename_exchange_at(layout[key], stage, destination)
                else:
                    os.replace(
                        stage,
                        destination,
                        src_dir_fd=layout[key],
                        dst_dir_fd=layout[key],
                    )
                _checkpoint(f"after-{key}-namespace")
                os.fsync(layout[key])

            _atomic_write_at(
                layout["manifest"],
                MANIFEST_PATH.name,
                manifest,
                temporary_name=MANIFEST_TEMPORARY_NAME,
                kind="ST-0105 manifest",
                checkpoint="after-manifest-namespace",
            )
            _validate_next_state_locked(layout, manifest)
            if _tree_files_at(
                layout["python"], PYTHON_OUTPUT_ROOT.name
            ) != rendered_files["python"] or _tree_files_at(
                layout["typescript"], TYPESCRIPT_OUTPUT_ROOT.name
            ) != rendered_files["typescript"]:
                raise RuntimeError("installed ST-0105 trees differ from rendered trees")
            state = _write_transaction_phase_locked(layout, state, "COMMITTED")
            _checkpoint("after-committed-state")
            _cleanup_terminal_transaction_locked(
                layout, state, previous_manifest, manifest
            )
        except BaseException as install_error:
            try:
                _recover_pending_transaction_locked(layout)
            except BaseException as recovery_error:
                raise InstallRecoveryRequired(
                    "ST-0105 install failed and durable recovery remains pending: "
                    f"{recovery_error}"
                ) from install_error
            raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verify-tools-only", action="store_true")
    parser.add_argument("--node", type=Path, required=True)
    parser.add_argument("--openapi-ts", type=Path, required=True)
    parser.add_argument("--datamodel-codegen", type=Path, required=True)
    arguments = parser.parse_args(argv)
    if arguments.check and arguments.verify_tools_only:
        parser.error("--check and --verify-tools-only are mutually exclusive")
    return arguments


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(argv)
    datamodel_codegen = arguments.datamodel_codegen
    node = arguments.node
    openapi_ts = arguments.openapi_ts
    try:
        if arguments.check or arguments.verify_tools_only:
            with _open_install_layout(exclusive=False, create=False) as layout:
                _assert_no_pending_transaction_locked(layout)
        else:
            _recover_pending_transaction()
        tool_versions = _verify_tools(datamodel_codegen, node, openapi_ts)
        if arguments.verify_tools_only:
            print(
                json.dumps(
                    {
                        "mode": "verify-tools",
                        "status": "PASS",
                        "story_id": STORY_ID,
                        "tools": tool_versions,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            return 0
        with tempfile.TemporaryDirectory(prefix="raos-st0105-codegen-") as temporary:
            temporary_root = Path(temporary)
            rendered_python, rendered_typescript, manifest, report = _render(
                temporary_root,
                datamodel_codegen,
                node,
                openapi_ts,
                tool_versions,
            )
            if arguments.check:
                _compare(rendered_python, rendered_typescript, manifest)
                mode = "check"
            else:
                _install(rendered_python, rendered_typescript, manifest)
                mode = "build"
        result = {
            "status": "PASS",
            "story_id": STORY_ID,
            "mode": mode,
            **report,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (OSError, RuntimeError, ValueError, TypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
