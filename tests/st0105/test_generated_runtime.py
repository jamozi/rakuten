"""Runtime import and TypeScript compilation checks for ST-0105 outputs."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from pydantic import BaseModel

from .support import REPOSITORY_ROOT


def operation_export_name(operation_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", operation_id).lower()


def test_all_224_python_schema_bindings_import_and_build_json_schema(
    codegen_manifest: dict[str, Any],
) -> None:
    from raos.generated import contracts

    for row in codegen_manifest["schema_bindings"]:
        model = getattr(contracts, row["type_name"])
        assert issubclass(model, BaseModel)
        rendered = model.model_json_schema()
        assert isinstance(rendered, dict)
        assert rendered


def test_python_schema_index_matches_the_manifest(
    codegen_manifest: dict[str, Any],
) -> None:
    index = json.loads(
        (
            REPOSITORY_ROOT / "python/raos/generated/contracts/schema-index.json"
        ).read_text(encoding="utf-8")
    )
    assert index == {
        "schema_count": 224,
        "schemas": codegen_manifest["schema_bindings"],
    }


def test_every_generated_python_file_compiles_without_writing_bytecode() -> None:
    sources = sorted((REPOSITORY_ROOT / "python/raos/generated").rglob("*.py"))
    assert sources
    for path in sources:
        compile(path.read_bytes(), path.as_posix(), "exec", dont_inherit=True)


def test_schema_types_and_client_exports_cover_the_manifest_exactly(
    codegen_manifest: dict[str, Any],
) -> None:
    schema_types = (
        REPOSITORY_ROOT
        / "packages/web-contracts/src/generated/schema-models/types.gen.ts"
    ).read_text(encoding="utf-8")
    for row in codegen_manifest["schema_bindings"]:
        assert f"export type {row['type_name']}" in schema_types

    for client in codegen_manifest["http_clients"]:
        sdk = (
            REPOSITORY_ROOT
            / f"packages/web-contracts/src/generated/clients/{client['surface']}/sdk.gen.ts"
        ).read_text(encoding="utf-8")
        exports = set(re.findall(r"^export const ([A-Za-z0-9_]+) =", sdk, re.MULTILINE))
        assert exports == {
            operation_export_name(operation_id)
            for operation_id in client["operation_ids"]
        }


def test_typescript_package_exports_are_explicit_and_surfaces_remain_separate() -> None:
    package = json.loads(
        (REPOSITORY_ROOT / "packages/web-contracts/package.json").read_text(
            encoding="utf-8"
        )
    )
    assert package["exports"] == {
        ".": "./src/generated/index.ts",
        "./admin": "./src/generated/clients/admin/index.ts",
        "./asyncapi": "./src/generated/asyncapi.gen.ts",
        "./internal": "./src/generated/clients/internal/index.ts",
        "./public": "./src/generated/clients/public/index.ts",
        "./schemas": "./src/generated/schema-models/index.ts",
    }
    entrypoint = (
        REPOSITORY_ROOT / "packages/web-contracts/src/generated/index.ts"
    ).read_text(encoding="utf-8")
    assert "export * as publicApi" in entrypoint
    assert "export * as adminApi" in entrypoint
    assert "export * as internalApi" in entrypoint
    assert "export { asyncApiContract }" in entrypoint


def test_generated_typescript_compiles_with_the_pinned_strict_project(
    node_executable: Path,
) -> None:
    command = [
        str(node_executable),
        str(REPOSITORY_ROOT / "node_modules/typescript/bin/tsc"),
        "--noEmit",
        "--project",
        str(REPOSITORY_ROOT / "packages/web-contracts/tsconfig.json"),
    ]
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env={
            "PATH": os.defpath,
            "HOME": str(REPOSITORY_ROOT),
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        },
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def test_only_the_generator_compatibility_flag_relaxes_the_root_ts_contract() -> None:
    base = json.loads(
        (REPOSITORY_ROOT / "tsconfig.base.json").read_text(encoding="utf-8")
    )
    package = json.loads(
        (REPOSITORY_ROOT / "packages/web-contracts/tsconfig.json").read_text(
            encoding="utf-8"
        )
    )
    assert base["compilerOptions"]["strict"] is True
    assert base["compilerOptions"]["noUncheckedIndexedAccess"] is True
    assert base["compilerOptions"]["exactOptionalPropertyTypes"] is True
    assert package["extends"] == "../../tsconfig.base.json"
    assert package["compilerOptions"] == {
        "exactOptionalPropertyTypes": False,
        "types": [],
    }
