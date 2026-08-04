"""Manifest, source-binding, and generated-inventory checks for ST-0105."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from conftest import REPOSITORY_ROOT
from raos.shared.contract_repository import ContractRepository


SOURCE_MANIFEST = "contracts/raos-v0.4/contract-repository.v0.4.json"
SOURCE_SHA256 = "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef"
OUTPUT_ROOTS = (
    "python/raos/generated",
    "packages/web-contracts/src/generated",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_manifest_is_canonical_and_preserves_the_status_boundary(
    codegen_manifest: dict[str, Any],
) -> None:
    manifest_path = REPOSITORY_ROOT / "changes/st-0105/manifest.json"
    assert (
        manifest_path.read_bytes()
        == (
            json.dumps(codegen_manifest, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n"
        ).encode()
    )
    assert codegen_manifest["document"] == {
        "generated_by": "scripts/build_st0105_generated_contracts.py",
        "id": "RAOS-CONTRACT-CODEGEN-001",
        "status": "IMPLEMENTED_NOT_VALIDATED",
        "story_id": "ST-0105",
        "version": "1.0",
    }
    assert codegen_manifest["source"] == {
        "artifact_count": 306,
        "asyncapi_count": 1,
        "contract_repository_manifest": SOURCE_MANIFEST,
        "contract_repository_manifest_sha256": SOURCE_SHA256,
        "network_retrieval": "FORBIDDEN",
        "openapi_count": 3,
        "standalone_schema_count": 224,
    }
    assert codegen_manifest["tools"] == {
        "@hey-api/openapi-ts": "0.99.0",
        "datamodel-code-generator": "0.71.0",
        "node": "24.18.1",
        "pydantic": "2.13.4",
        "python": "3.14.6",
        "typescript": "6.0.3",
    }


def test_every_schema_binding_matches_the_verified_repository(
    codegen_manifest: dict[str, Any],
    contract_repository: ContractRepository,
) -> None:
    assert len(contract_repository.artifacts) == 306
    artifacts = {artifact.path: artifact for artifact in contract_repository.artifacts}
    bindings = codegen_manifest["schema_bindings"]
    assert len(bindings) == 224
    assert [row["path"] for row in bindings] == sorted(row["path"] for row in bindings)
    assert len({row["schema_id"] for row in bindings}) == 224
    assert len({row["type_name"] for row in bindings}) == 224
    for index, row in enumerate(bindings, 1):
        assert set(row) == {"bytes", "path", "schema_id", "sha256", "type_name"}
        assert row["path"].endswith(".schema.json")
        artifact = artifacts[row["path"]]
        assert row["bytes"] == artifact.byte_count
        assert row["sha256"] == artifact.sha256
        assert row["type_name"].startswith(f"Schema{index:03d}")
        assert re.fullmatch(r"Schema\d{3}[A-Za-z0-9]+", row["type_name"])


def test_http_clients_are_complete_unique_and_surface_separated(
    codegen_manifest: dict[str, Any],
) -> None:
    clients = codegen_manifest["http_clients"]
    assert [(row["surface"], row["operation_count"]) for row in clients] == [
        ("public", 6),
        ("admin", 171),
        ("internal", 8),
    ]
    operations = codegen_manifest["http_operations"]
    assert len(operations) == 185
    assert len({row["operation_id"] for row in operations}) == 185
    for client in clients:
        selected = [row for row in operations if row["surface"] == client["surface"]]
        assert len(selected) == client["operation_count"]
        assert [row["operation_id"] for row in selected] == client["operation_ids"]
    for operation in operations:
        assert set(operation) == {"method", "operation_id", "path", "surface"}
        assert operation["method"] in {
            "GET",
            "PUT",
            "POST",
            "DELETE",
            "OPTIONS",
            "HEAD",
            "PATCH",
            "TRACE",
        }
        assert operation["path"].startswith("/")


def test_asyncapi_registry_is_complete_and_source_bound(
    codegen_manifest: dict[str, Any],
) -> None:
    registry = codegen_manifest["asyncapi_registry"]
    assert registry["source_path"] == "contracts/asyncapi.v0.4.yaml"
    assert re.fullmatch(r"[0-9a-f]{64}", registry["source_sha256"])
    assert registry["channel_count"] == len(registry["channels"]) == 22
    assert registry["operation_count"] == len(registry["operations"]) == 37
    assert registry["message_count"] == len(registry["messages"]) == 105
    assert len({row["name"] for row in registry["channels"]}) == 22
    assert len({row["name"] for row in registry["operations"]}) == 37
    assert len({row["name"] for row in registry["messages"]}) == 105


def test_generated_output_inventory_is_exact_hash_bound_and_safe(
    codegen_manifest: dict[str, Any],
) -> None:
    outputs = codegen_manifest["outputs"]
    assert outputs["boundary"] == "EXACT"
    assert outputs["roots"] == list(OUTPUT_ROOTS)
    artifacts = outputs["artifacts"]
    assert outputs["artifact_count"] == len(artifacts) == 354
    assert [row["path"] for row in artifacts] == sorted(
        row["path"] for row in artifacts
    )

    actual: dict[str, Path] = {}
    for root in OUTPUT_ROOTS:
        root_path = REPOSITORY_ROOT / root
        assert root_path.is_dir() and not root_path.is_symlink()
        for path in root_path.rglob("*"):
            assert not path.is_symlink(), path
            if path.is_file():
                actual[path.relative_to(REPOSITORY_ROOT).as_posix()] = path
    assert set(actual) == {row["path"] for row in artifacts}
    for row in artifacts:
        path = actual[row["path"]]
        assert path.stat().st_size == row["bytes"]
        assert sha256(path) == row["sha256"]


def test_intermediates_are_hash_bound_but_not_committed(
    codegen_manifest: dict[str, Any],
) -> None:
    intermediates = codegen_manifest["intermediates"]
    assert [row["name"] for row in intermediates] == [
        "st0105-codegen-root.schema.json",
        "st0105-schema-models.openapi.json",
    ]
    assert all(row["committed"] is False for row in intermediates)
    assert all(row["bytes"] > 0 for row in intermediates)
    assert all(re.fullmatch(r"[0-9a-f]{64}", row["sha256"]) for row in intermediates)
    for row in intermediates:
        assert not (REPOSITORY_ROOT / row["name"]).exists()


def test_every_source_file_has_stable_relative_provenance() -> None:
    expected = (
        f"RAOS source: {SOURCE_MANIFEST} sha256={SOURCE_SHA256}\n"
        "{comment} RAOS generation: scripts/build_st0105_generated_contracts.py\n"
    )
    generated = [
        *(REPOSITORY_ROOT / OUTPUT_ROOTS[0]).rglob("*.py"),
        *(REPOSITORY_ROOT / OUTPUT_ROOTS[1]).rglob("*.ts"),
    ]
    assert generated
    for path in generated:
        comment = "#" if path.suffix == ".py" else "//"
        content = path.read_text(encoding="utf-8")
        header = f"{comment} " + expected.format(comment=comment)
        assert content.startswith(header), path
        assert "raos-st0105-codegen-" not in content
        assert str(REPOSITORY_ROOT) not in content
