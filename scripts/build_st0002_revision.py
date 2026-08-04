#!/usr/bin/env python3
"""Build the ST-0002 canonical Job-state revision from immutable packages."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = REPO_ROOT / "changes" / "st-0002"
STATE_SOURCE = DEFAULT_BUNDLE_ROOT / "job-state.v1.yaml"
DATABASE_ROOT = DEFAULT_BUNDLE_ROOT / "database"
API_PACKAGE = REPO_ROOT / "docs" / "upstream" / "RAOS_04_api_contract_package_v0.1.zip"
DATA_PACKAGE = REPO_ROOT / "docs" / "upstream" / "RAOS_03_data_model_package_v0.1.zip"
PROPOSAL_PATCH = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_04_001_contract_alignment_patch_v0.1.sql"
)
API_ROOT = "RAOS_04_api_contract_package_v0.1/"
REVISION_VERSION = "0.2"
REVISION_ID = "RAOS-JOB-STATE-REVISION-001"
EXPECTED_INPUT_HASHES = {
    "docs/upstream/RAOS_03_data_model_package_v0.1.zip": (
        "82597db880c80c632ac0337d583c91ba5defac827414ecee1b921f49d1f64357"
    ),
    "docs/upstream/RAOS_04_api_contract_package_v0.1.zip": (
        "fb55cc00adabd20591c3da06d2399b3692b3393d3f27d28943e870e8b253ca1f"
    ),
    "docs/upstream/patches/RAOS_04_001_contract_alignment_patch_v0.1.sql": (
        "53372f0bf34169988e842bed7d51b29c9688107459e412c3ecae1a357cdeff72"
    ),
}
MIGRATION_FILES = (
    "202607300001_job_state_expand.sql",
    "202607300002_job_state_expand_validate.sql",
    "202607300003_job_state_migrate_batch.sql",
    "202607300004_job_state_contract_prepare.sql",
    "202607300005_job_state_contract.sql",
    "202607300006_job_state_guarded_downgrade.sql",
    "forward-recovery.md",
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative_repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def assert_immutable_inputs() -> None:
    for relative_path, expected_hash in EXPECTED_INPUT_HASHES.items():
        path = REPO_ROOT / relative_path
        if not path.is_file():
            raise RuntimeError(f"required immutable input is missing: {relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"immutable input hash mismatch for {relative_path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )


def load_yaml_bytes(content: bytes, *, source: str) -> dict[str, Any]:
    document = yaml.safe_load(content)
    if not isinstance(document, dict):
        raise RuntimeError(f"expected YAML mapping in {source}")
    return document


def load_state_source() -> dict[str, Any]:
    return load_yaml_bytes(
        STATE_SOURCE.read_bytes(), source=relative_repo_path(STATE_SOURCE)
    )


def read_api_yaml(archive: ZipFile, filename: str) -> dict[str, Any]:
    member = f"{API_ROOT}{filename}"
    try:
        content = archive.read(member)
    except KeyError as exc:
        raise RuntimeError(f"API package member is missing: {member}") from exc
    return load_yaml_bytes(content, source=member)


def write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        dict(document),
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(rendered, encoding="utf-8", newline="\n")


def mark_document_revision(document: MutableMapping[str, Any]) -> None:
    document["version"] = REVISION_VERSION
    document["status"] = "CANONICAL_REVISION_CANDIDATE"
    document["provenance"] = {
        "story_id": "ST-0002",
        "decision_id": "INT-DEC-003",
        "revision_id": REVISION_ID,
        "base_version": "0.1",
    }


def mark_openapi_revision(document: MutableMapping[str, Any]) -> None:
    info = document.get("info")
    if not isinstance(info, dict):
        raise RuntimeError("OpenAPI info object is missing")
    info["version"] = REVISION_VERSION
    info["x-raos-status"] = "CANONICAL_REVISION_CANDIDATE"
    info["x-raos-revision-id"] = REVISION_ID
    info["x-raos-story-id"] = "ST-0002"
    info["x-raos-decision-id"] = "INT-DEC-003"
    info["x-raos-base-version"] = "0.1"


def nullable_datetime(description: str) -> dict[str, Any]:
    return {
        "anyOf": [
            {
                "type": "string",
                "format": "date-time",
                "description": description,
            },
            {"type": "null"},
        ],
        "readOnly": True,
    }


def patch_admin_openapi(document: dict[str, Any], states: list[str]) -> None:
    mark_openapi_revision(document)
    try:
        job_schema = document["components"]["schemas"]["Job"]
        job_properties = job_schema["properties"]
    except KeyError as exc:
        raise RuntimeError("Admin OpenAPI Job schema is missing") from exc
    if not isinstance(job_properties, dict):
        raise RuntimeError("Admin OpenAPI Job properties must be a mapping")

    status_schema = job_properties.get("status")
    if not isinstance(status_schema, dict):
        raise RuntimeError("Admin OpenAPI Job.status is missing")
    status_schema["enum"] = list(states)
    status_schema["x-raos-state-contract"] = "../job-state.v1.yaml"
    job_properties["job_version"] = {
        "type": "integer",
        "minimum": 1,
        "description": "Job message/payload contract version; distinct from lock_version.",
        "readOnly": True,
    }
    job_properties["deadline_at"] = nullable_datetime(
        "Deadline after which an eligible active Job may expire."
    )
    job_properties["cancel_requested_at"] = nullable_datetime(
        "Timestamp of a cooperative cancellation request."
    )

    try:
        list_operation = document["paths"]["/api/v1/admin/ops/jobs"]["get"]
    except KeyError as exc:
        raise RuntimeError("Admin OpenAPI OPS-001 operation is missing") from exc
    status_parameters = [
        parameter
        for parameter in list_operation.get("parameters", [])
        if isinstance(parameter, dict) and parameter.get("name") == "status"
    ]
    if len(status_parameters) != 1:
        raise RuntimeError(
            "Admin OpenAPI OPS-001 must have exactly one status parameter"
        )
    status_parameters[0]["schema"]["enum"] = list(states)
    status_parameters[0]["description"] = "Canonical Job state."

    command_paths = (
        ("/api/v1/admin/ops/jobs/{id}/retry", "202"),
        ("/api/v1/admin/ops/jobs/{id}/cancel", "200"),
    )
    for path, success_status in command_paths:
        operation = document["paths"][path]["post"]
        success_response = operation["responses"][success_status]
        success_headers = success_response.setdefault("headers", {})
        success_headers["ETag"] = {"$ref": "#/components/headers/ETag"}
        operation["x-raos-state-contract"] = "../job-state.v1.yaml"
        operation["x-raos-state-conflict-status"] = 409
        operation["x-raos-success-etag-required"] = True


def patch_internal_openapi(document: dict[str, Any]) -> None:
    mark_openapi_revision(document)
    document["info"]["x-raos-wire-change"] = "NONE"
    document["info"]["x-raos-job-state-contract"] = "../job-state.v1.yaml"


def patch_asyncapi(document: dict[str, Any]) -> None:
    info = document.get("info")
    if not isinstance(info, dict):
        raise RuntimeError("AsyncAPI info object is missing")
    info["version"] = REVISION_VERSION
    info["x-raos-status"] = "CANONICAL_REVISION_CANDIDATE"
    info["x-raos-revision-id"] = REVISION_ID
    info["x-raos-story-id"] = "ST-0002"
    info["x-raos-decision-id"] = "INT-DEC-003"
    info["x-raos-base-version"] = "0.1"
    info["x-raos-wire-change"] = "NONE"
    document["x-raos-job-state-contract"] = "../job-state.v1.yaml"


def patch_job_catalog(
    document: dict[str, Any],
    state_source: dict[str, Any],
) -> None:
    mark_document_revision(document["document"])
    model = state_source["state_model"]
    document["canonical_states"] = list(model["states"])
    document["state_model"] = {
        "initial_state": model["initial"],
        "completed_at_required": list(model["completed_at_required"]),
        "absorbing": list(model["absorbing"]),
        "deadline_index_states": list(model["deadline_index_states"]),
        "cancellable": list(model["cancellable"]),
        "state_machine_ref": "state-transition-catalog.v0.2.yaml#SM-JOB",
        "migration_revision": "ST-0002",
    }


def patch_state_catalog(
    document: dict[str, Any],
    state_source: dict[str, Any],
) -> None:
    mark_document_revision(document["document"])
    machines = document.get("machines")
    if not isinstance(machines, list):
        raise RuntimeError("state transition catalog machines are missing")
    matches = [machine for machine in machines if machine.get("id") == "SM-JOB"]
    if len(matches) != 1:
        raise RuntimeError("state transition catalog must contain exactly one SM-JOB")
    machine = matches[0]
    model = state_source["state_model"]
    machine["initial"] = model["initial"]
    machine["states"] = list(model["states"])
    machine["transitions"] = [
        [transition["from"], transition["to"], transition["reason"]]
        for transition in state_source["transitions"]
    ]
    machine["guards"] = [
        guard["rule"] for guard in state_source.get("global_guards", [])
    ]
    machine["x-raos-completed-at-required"] = list(model["completed_at_required"])
    machine["x-raos-absorbing-states"] = list(model["absorbing"])
    machine["x-raos-deadline-index-states"] = list(model["deadline_index_states"])
    machine["x-raos-cancellable-states"] = list(model["cancellable"])
    machine["x-raos-legacy-mapping"] = dict(state_source["legacy_mapping"])
    machine["x-raos-transition-guards"] = [
        {
            "from": transition["from"],
            "to": transition["to"],
            "guards": list(transition.get("guards", [])),
        }
        for transition in state_source["transitions"]
        if transition.get("guards")
    ]


def job_resource(document: dict[str, Any]) -> dict[str, Any]:
    resources = document.get("resources")
    if not isinstance(resources, list):
        raise RuntimeError("resource contract resources are missing")
    matches = [resource for resource in resources if resource.get("name") == "Job"]
    if len(matches) != 1:
        raise RuntimeError("resource contracts must contain exactly one Job")
    return matches[0]


def normalize_resource_contract_refs(document: dict[str, Any]) -> None:
    """Repair the three v0.1 catalog pointers to their actual local definitions."""

    replacements = {
        "#/components/schemas/PublicOffer": "#/public_resources/PublicOffer",
        "#/components/schemas/PublicProductCard": (
            "#/public_resources/PublicProductCard"
        ),
        "#/components/schemas/PublicArticleBlock": (
            "#/public_resources/PublicArticleBlock"
        ),
    }
    counts = dict.fromkeys(replacements, 0)

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if reference in replacements:
                node["$ref"] = replacements[reference]
                counts[reference] += 1
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)

    visit(document)
    unexpected_counts = {
        reference: count for reference, count in counts.items() if count != 1
    }
    if unexpected_counts:
        raise RuntimeError(
            "expected exactly one occurrence of each v0.1 resource-contract "
            f"pointer defect, got {unexpected_counts}"
        )


def patch_resource_contracts(document: dict[str, Any], states: list[str]) -> None:
    mark_document_revision(document["document"])
    normalize_resource_contract_refs(document)
    resource = job_resource(document)
    fields = resource.get("fields")
    if not isinstance(fields, list):
        raise RuntimeError("Job resource fields are missing")
    status_fields = [field for field in fields if field.get("name") == "status"]
    if len(status_fields) != 1:
        raise RuntimeError("Job resource must contain exactly one status field")
    status_fields[0]["schema"]["enum"] = list(states)
    status_fields[0]["schema"]["x-raos-state-contract"] = "../../job-state.v1.yaml"

    existing_names = {field.get("name") for field in fields}
    additions = [
        {
            "name": "job_version",
            "schema": {
                "type": "integer",
                "minimum": 1,
                "description": (
                    "Job message/payload contract version; distinct from lock_version."
                ),
            },
            "read_only": True,
        },
        {
            "name": "deadline_at",
            "schema": nullable_datetime(
                "Deadline after which an eligible active Job may expire."
            ),
            "read_only": True,
        },
        {
            "name": "cancel_requested_at",
            "schema": nullable_datetime(
                "Timestamp of a cooperative cancellation request."
            ),
            "read_only": True,
        },
    ]
    for addition in additions:
        if addition["name"] in existing_names:
            raise RuntimeError(f"unexpected existing Job field: {addition['name']}")
        fields.append(addition)
    resource.setdefault("notes", []).append(
        "ST-0002 canonical Job-state revision; see INT-DEC-003."
    )


def patch_schema_registry(document: dict[str, Any]) -> None:
    mark_document_revision(document["document"])
    document["revision_policy"] = {
        "job_message_wire_change": "NONE",
        "job_message_version": 1,
        "common_schema_frozen": True,
        "revision_id": REVISION_ID,
    }


def checked_schema_members(archive: ZipFile) -> list[str]:
    prefix = f"{API_ROOT}schemas/"
    members: list[str] = []
    seen_casefold: set[str] = set()
    for info in archive.infolist():
        if not info.filename.startswith(prefix) or info.is_dir():
            continue
        relative_name = info.filename[len(API_ROOT) :]
        relative_path = PurePosixPath(relative_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError(f"unsafe schema member: {info.filename}")
        folded = relative_name.casefold()
        if folded in seen_casefold:
            raise RuntimeError(
                f"case-insensitive duplicate schema member: {relative_name}"
            )
        seen_casefold.add(folded)
        members.append(info.filename)
    if len(members) != 126:
        raise RuntimeError(f"expected 126 API schemas, found {len(members)}")
    return sorted(members)


def copy_and_verify_schemas(
    archive: ZipFile,
    contracts_root: Path,
    schema_registry: dict[str, Any],
) -> None:
    registry_entries = schema_registry.get("schemas")
    if not isinstance(registry_entries, list):
        raise RuntimeError("schema registry entries are missing")
    expected_hashes = {
        entry["path"]: entry["sha256"]
        for entry in registry_entries
        if isinstance(entry, dict) and "path" in entry and "sha256" in entry
    }
    if len(expected_hashes) != 126:
        raise RuntimeError(
            f"expected 126 registry hashes, found {len(expected_hashes)}"
        )

    copied_paths: set[str] = set()
    for member in checked_schema_members(archive):
        relative_name = member[len(API_ROOT) :]
        content = archive.read(member)
        expected_hash = expected_hashes.get(relative_name)
        if expected_hash is None:
            raise RuntimeError(f"schema is not registered: {relative_name}")
        actual_hash = sha256_bytes(content)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"schema hash mismatch for {relative_name}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
        destination = contracts_root / relative_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        copied_paths.add(relative_name)

    missing = set(expected_hashes) - copied_paths
    if missing:
        raise RuntimeError(
            f"registered schemas are missing from package: {sorted(missing)}"
        )


def generate_contracts(contracts_root: Path, state_source: dict[str, Any]) -> None:
    contracts_root.mkdir(parents=True, exist_ok=True)
    states = list(state_source["state_model"]["states"])
    with ZipFile(API_PACKAGE) as archive:
        admin = read_api_yaml(archive, "RAOS_04_openapi_admin_v0.1.yaml")
        internal = read_api_yaml(archive, "RAOS_04_openapi_internal_v0.1.yaml")
        asyncapi = read_api_yaml(archive, "RAOS_04_asyncapi_v0.1.yaml")
        job_catalog = read_api_yaml(archive, "RAOS_04_job_catalog_v0.1.yaml")
        state_catalog = read_api_yaml(
            archive, "RAOS_04_state_transition_catalog_v0.1.yaml"
        )
        resources = read_api_yaml(archive, "RAOS_04_resource_contracts_v0.1.yaml")
        schema_registry = read_api_yaml(archive, "RAOS_04_schema_registry_v0.1.yaml")

        patch_admin_openapi(admin, states)
        patch_internal_openapi(internal)
        patch_asyncapi(asyncapi)
        patch_job_catalog(job_catalog, state_source)
        patch_state_catalog(state_catalog, state_source)
        patch_resource_contracts(resources, states)
        patch_schema_registry(schema_registry)

        write_yaml(contracts_root / "openapi-admin.v0.2.yaml", admin)
        write_yaml(contracts_root / "openapi-internal.v0.2.yaml", internal)
        write_yaml(contracts_root / "asyncapi.v0.2.yaml", asyncapi)
        write_yaml(contracts_root / "catalogs" / "job-catalog.v0.2.yaml", job_catalog)
        write_yaml(
            contracts_root / "catalogs" / "state-transition-catalog.v0.2.yaml",
            state_catalog,
        )
        write_yaml(
            contracts_root / "catalogs" / "resource-contracts.v0.2.yaml",
            resources,
        )
        write_yaml(
            contracts_root / "catalogs" / "schema-registry.v0.2.yaml",
            schema_registry,
        )
        copy_and_verify_schemas(archive, contracts_root, schema_registry)


def artifact_entry(path: Path, logical_path: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": logical_path,
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def contract_artifacts(contracts_root: Path) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for path in sorted(item for item in contracts_root.rglob("*") if item.is_file()):
        relative = path.relative_to(contracts_root).as_posix()
        artifacts.append(artifact_entry(path, f"changes/st-0002/contracts/{relative}"))
    return artifacts


def source_artifacts() -> list[dict[str, Any]]:
    paths = [
        REPO_ROOT / "scripts" / "build_st0002_revision.py",
        DEFAULT_BUNDLE_ROOT / "README.md",
        STATE_SOURCE,
        *(DATABASE_ROOT / name for name in MIGRATION_FILES),
    ]
    return [artifact_entry(path, relative_repo_path(path)) for path in paths]


def build_manifest(contracts_root: Path) -> dict[str, Any]:
    generated = contract_artifacts(contracts_root)
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0002",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": "scripts/build_st0002_revision.py",
        },
        "provenance": {
            "requirement_ids": ["FR-020"],
            "decision_ids": ["INT-DEC-003"],
            "base_contracts": ["RAOS-DATA-001@0.1", "RAOS-API-001@0.1"],
            "proposal_execution": "NOT_EXECUTABLE_AS_IS",
            "proposal_retained": True,
        },
        "inputs": [
            {"path": path, "sha256": digest}
            for path, digest in EXPECTED_INPUT_HASHES.items()
        ],
        "compatibility": {
            "classification": "PRE_RELEASE_CANONICAL_DEFECT_CORRECTION",
            "http_path_major": 1,
            "job_message_major": 1,
            "job_message_wire_change": "NONE",
            "published_consumer_cutover": "NOT_APPLICABLE_BASELINE_CANDIDATE",
        },
        "postgresql": {
            "minimum_server_version_num": 180000,
            "design_target": "18.4",
            "predecessor": "RAOS-DATA-001@0.1 ops.job",
            "phase_order": [
                "202607300001_job_state_expand.sql",
                "202607300002_job_state_expand_validate.sql",
                "202607300003_job_state_migrate_batch.sql",
                "202607300004_job_state_contract_prepare.sql",
                "202607300005_job_state_contract.sql",
            ],
            "repeatable_phase": {
                "file": "202607300003_job_state_migrate_batch.sql",
                "batch_size": 1000,
                "completion_signal": "remaining_rows=0",
                "checkpoint_required": True,
            },
            "guarded_downgrade": "202607300006_job_state_guarded_downgrade.sql",
            "forward_recovery": "forward-recovery.md",
        },
        "handoff": {
            "ST-0104": "install contracts and loader from this hash-pinned bundle",
            "ST-0301": "bind SQL payloads to migration runner/history/lock ABI",
            "ST-0303": "install canonical ops.job in IAM/OPS schema wave",
            "ST-1404": "implement transition, lease, retry, and DLQ runtime",
        },
        "source_artifacts": source_artifacts(),
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
    }


def assert_owned_generated_destination(bundle_root: Path) -> None:
    if bundle_root.is_symlink() or (bundle_root.exists() and not bundle_root.is_dir()):
        raise RuntimeError(f"refusing unsafe bundle root: {bundle_root}")

    contracts_root = bundle_root / "contracts"
    manifest_path = bundle_root / "manifest.yaml"
    if contracts_root.is_symlink() or manifest_path.is_symlink():
        raise RuntimeError(f"refusing symlinked generated destination: {bundle_root}")

    contracts_exist = contracts_root.exists()
    manifest_exists = manifest_path.exists()
    if contracts_exist != manifest_exists:
        raise RuntimeError(
            "generated destination must contain both contracts and manifest, or neither"
        )
    if not contracts_exist:
        return
    if not contracts_root.is_dir() or not manifest_path.is_file():
        raise RuntimeError(f"refusing malformed generated destination: {bundle_root}")

    manifest = load_yaml_bytes(manifest_path.read_bytes(), source=str(manifest_path))
    document = manifest.get("document")
    if not isinstance(document, dict) or document.get("id") != REVISION_ID:
        raise RuntimeError(
            f"refusing to replace a destination not owned by {REVISION_ID}"
        )
    if document.get("generated_by") != "scripts/build_st0002_revision.py":
        raise RuntimeError("generated destination has an unexpected ownership marker")


def install_staged_generation(staged_root: Path, bundle_root: Path) -> None:
    target_contracts = bundle_root / "contracts"
    target_manifest = bundle_root / "manifest.yaml"
    staged_contracts = staged_root / "contracts"
    staged_manifest = staged_root / "manifest.yaml"
    backup_contracts = staged_root.parent / "previous-contracts"
    backup_manifest = staged_root.parent / "previous-manifest.yaml"

    had_previous = target_contracts.exists()
    previous_contracts_moved = False
    previous_manifest_moved = False
    new_contracts_installed = False
    new_manifest_installed = False
    try:
        if had_previous:
            os.replace(target_contracts, backup_contracts)
            previous_contracts_moved = True
            os.replace(target_manifest, backup_manifest)
            previous_manifest_moved = True
        os.replace(staged_contracts, target_contracts)
        new_contracts_installed = True
        os.replace(staged_manifest, target_manifest)
        new_manifest_installed = True
    except OSError:
        if new_manifest_installed and target_manifest.is_file():
            target_manifest.unlink()
        if new_contracts_installed and target_contracts.is_dir():
            shutil.rmtree(target_contracts)
        if previous_manifest_moved:
            os.replace(backup_manifest, target_manifest)
        if previous_contracts_moved:
            os.replace(backup_contracts, target_contracts)
        raise


def build(bundle_root: Path) -> None:
    """Render completely in staging, then replace only an owned generated tree."""

    assert_immutable_inputs()
    state_source = load_state_source()
    assert_owned_generated_destination(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".raos-st0002-build-", dir=bundle_root.parent
    ) as temporary:
        staged_root = Path(temporary) / "generated"
        staged_root.mkdir()
        staged_contracts = staged_root / "contracts"
        generate_contracts(staged_contracts, state_source)
        write_yaml(
            staged_root / "manifest.yaml",
            build_manifest(staged_contracts),
        )
        install_staged_generation(staged_root, bundle_root)


def generated_file_map(bundle_root: Path) -> dict[str, bytes]:
    paths = [bundle_root / "manifest.yaml"]
    contracts_root = bundle_root / "contracts"
    if contracts_root.is_dir():
        paths.extend(
            sorted(item for item in contracts_root.rglob("*") if item.is_file())
        )
    return {
        path.relative_to(bundle_root).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


def check_generated() -> None:
    with tempfile.TemporaryDirectory(prefix="raos-st0002-check-") as temporary:
        candidate_root = Path(temporary)
        build(candidate_root)
        expected = generated_file_map(candidate_root)
        actual = generated_file_map(DEFAULT_BUNDLE_ROOT)
    if expected == actual:
        return
    missing = sorted(set(expected) - set(actual))
    unexpected = sorted(set(actual) - set(expected))
    changed = sorted(
        path for path in set(expected) & set(actual) if expected[path] != actual[path]
    )
    raise RuntimeError(
        json.dumps(
            {
                "status": "DRIFT",
                "missing": missing,
                "unexpected": unexpected,
                "changed": changed,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_BUNDLE_ROOT,
        help=(
            "owned bundle root; only the canonical changes/st-0002 destination "
            "is accepted by the CLI"
        ),
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild in a temporary directory and fail on generated drift",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = ()) -> int:
    args = parse_args(argv)
    try:
        if args.check:
            if args.output.resolve() != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError("--check does not accept a custom --output")
            check_generated()
            result = {"status": "PASS", "story_id": "ST-0002", "mode": "check"}
        else:
            output = args.output.resolve()
            if output != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError(
                    "--output must be the owned canonical changes/st-0002 bundle"
                )
            build(output)
            result = {
                "status": "PASS",
                "story_id": "ST-0002",
                "mode": "build",
                "output": str(output),
            }
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ST-0002 revision build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
