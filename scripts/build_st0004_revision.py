#!/usr/bin/env python3
"""Build the ST-0004 content-contract revision from verified immutable inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterable, Mapping, MutableMapping
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import BadZipFile, ZipFile, ZipInfo

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = REPO_ROOT / "changes" / "st-0004"
PREDECESSOR_ROOT = REPO_ROOT / "changes" / "st-0003"
PREDECESSOR_MANIFEST = PREDECESSOR_ROOT / "manifest.yaml"
PREDECESSOR_JOB_STATE = PREDECESSOR_ROOT / "job-state.v1.yaml"
DATABASE_ROOT = DEFAULT_BUNDLE_ROOT / "database"

CONTENT_PACKAGE = (
    REPO_ROOT / "docs" / "upstream" / "RAOS_06_content_design_package_v0.1.zip"
)
CONTENT_DATA_PROPOSAL = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_06_001_data_alignment_patch_v0.1.sql"
)
CONTENT_API_PROPOSAL = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_06_002_api_alignment_patch_v0.1.yaml"
)
CONTENT_AI_PROPOSAL = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_06_003_ai_alignment_patch_v0.1.yaml"
)

CONTENT_ROOT = "raos_content_v0_1/"
CONTENT_CHECKSUM_MEMBER = f"{CONTENT_ROOT}RAOS_06_SHA256SUMS_v0.1.txt"
REVISION_VERSION = "0.4"
REVISION_ID = "RAOS-CONTENT-REVISION-001"
PREDECESSOR_ID = "RAOS-AI-GOVERNANCE-REVISION-001"
PREDECESSOR_MANIFEST_HASH = (
    "142d27a392ab5ecd2362327d231c9f8ea2a8d716e3f6fcd7bb15440697a50482"
)
JOB_STATE_HASH = (
    "9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a"
)
PUBLIC_OPENAPI_HASH = (
    "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797"
)

EXPECTED_INPUT_HASHES = {
    "docs/upstream/RAOS_06_content_design_package_v0.1.zip": (
        "4cc7e0802b2dfd7d01762aa73190caa746b6f2490c2411804c564f7ce02803ec"
    ),
    "docs/upstream/patches/RAOS_06_001_data_alignment_patch_v0.1.sql": (
        "69ac7925c206862bea5244d6831a65eaa0b3b5bc6cf9defde8a3e6a3a654ed3e"
    ),
    "docs/upstream/patches/RAOS_06_002_api_alignment_patch_v0.1.yaml": (
        "4390ea3a638eb70217ea023dbe0d76d3167a436d0fd1cfc9ea40ba2659bfa573"
    ),
    "docs/upstream/patches/RAOS_06_003_ai_alignment_patch_v0.1.yaml": (
        "89fe29c6182dc38b40d96379a65715fada43b74e93b5715eb3320b6a50285c1e"
    ),
}

ROOT_REVISION_FILES = {
    "openapi-admin.v0.3.yaml": "openapi-admin.v0.4.yaml",
    "openapi-internal.v0.3.yaml": "openapi-internal.v0.4.yaml",
    "asyncapi.v0.3.yaml": "asyncapi.v0.4.yaml",
    "catalogs/job-catalog.v0.3.yaml": "catalogs/job-catalog.v0.4.yaml",
    "catalogs/resource-contracts.v0.3.yaml": (
        "catalogs/resource-contracts.v0.4.yaml"
    ),
    "catalogs/schema-registry.v0.3.yaml": "catalogs/schema-registry.v0.4.yaml",
    "catalogs/state-transition-catalog.v0.3.yaml": (
        "catalogs/state-transition-catalog.v0.4.yaml"
    ),
}

MIGRATION_PHASES = (
    "202607300013_content_expand.sql",
    "202607300014_content_expand_validate.sql",
    "202607300015_content_migrate_batch.sql",
    "202607300016_content_contract_prepare.sql",
    "202607300017_content_contract.sql",
)
GUARDED_DOWNGRADE = "202607300018_content_guarded_downgrade.sql"
FORWARD_RECOVERY = "forward-recovery.md"

FROZEN_TOP_LEVEL_CONTRACTS = {
    "RAOS_06_article_type_catalog_v0.1.yaml",
    "RAOS_06_claim_evidence_policy_v0.1.yaml",
    "RAOS_06_content_block_catalog_v0.1.yaml",
    "RAOS_06_content_contract_catalog_v0.1.yaml",
    "RAOS_06_content_test_matrix_v0.1.csv",
    "RAOS_06_editorial_policy_catalog_v0.1.yaml",
    "RAOS_06_external_rule_snapshot_v0.1.yaml",
    "RAOS_06_freshness_update_policy_v0.1.yaml",
    "RAOS_06_implementation_slices_v0.1.yaml",
    "RAOS_06_internal_link_policy_v0.1.yaml",
    "RAOS_06_media_asset_policy_v0.1.yaml",
    "RAOS_06_official_references_v0.1.yaml",
    "RAOS_06_quality_gate_catalog_v0.1.yaml",
    "RAOS_06_recommendation_methodology_v0.1.yaml",
    "RAOS_06_review_checklist_v0.1.yaml",
    "RAOS_06_schema_registry_v0.1.yaml",
    "RAOS_06_seo_metadata_structured_data_policy_v0.1.yaml",
    "RAOS_06_traceability_matrix_v0.1.csv",
}

CONTENT_API_OPERATIONS = (
    "ED-016",
    "ED-017",
    "ED-018",
    "ED-019",
    "ED-020",
    "ED-021",
    "ED-022",
    "ED-023",
    "ED-024",
    "ED-025",
    "ED-026",
    "ED-027",
    "ED-028",
    "ED-029",
    "ED-030",
    "INT-005",
    "INT-006",
    "INT-007",
    "INT-008",
)
CONTENT_ADMIN_OAUTH_SCOPES = (
    "content:config:read",
    "content:config:write",
    "content:article:read",
    "content:article:write",
    "content:review:approve",
    "media:read",
    "media:write",
    "evidence:experience:read",
    "evidence:experience:write",
)


class NoAliasDumper(yaml.SafeDumper):
    """Emit deterministic YAML without anchors shared through Python objects."""

    def ignore_aliases(self, data: object) -> bool:
        return True


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative_repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def load_yaml_bytes(content: bytes, *, source: str) -> dict[str, Any]:
    loaded = yaml.safe_load(content)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"expected YAML mapping in {source}")
    return loaded


def write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.dump(
        dict(document),
        Dumper=NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=100,
    )
    path.write_text(rendered, encoding="utf-8", newline="\n")


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def checked_relative_path(value: str, *, source: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise RuntimeError(f"unsafe relative path in {source}: {value!r}")
    return path


def zip_info_is_symlink(info: ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def checked_archive_files(archive: ZipFile) -> dict[str, ZipInfo]:
    regular: dict[str, ZipInfo] = {}
    seen_casefold: set[str] = set()
    for info in archive.infolist():
        if info.is_dir():
            continue
        if zip_info_is_symlink(info):
            raise RuntimeError(f"content archive contains a symlink: {info.filename}")
        if not info.filename.startswith(CONTENT_ROOT):
            raise RuntimeError(f"content archive member escapes root: {info.filename}")
        relative = info.filename.removeprefix(CONTENT_ROOT)
        checked_relative_path(relative, source=relative_repo_path(CONTENT_PACKAGE))
        folded = relative.casefold()
        if folded in seen_casefold:
            raise RuntimeError(f"duplicate/casefold content member: {relative}")
        seen_casefold.add(folded)
        regular[relative] = info
    if len(regular) != 111:
        raise RuntimeError(
            f"unexpected RAOS-06 regular-member count: expected 111, got {len(regular)}"
        )
    return regular


def parse_checksum_inventory(content: bytes) -> dict[str, str]:
    result: dict[str, str] = {}
    seen_casefold: set[str] = set()
    for line_number, raw_line in enumerate(content.decode("utf-8").splitlines(), 1):
        parts = raw_line.split("  ", 1)
        if len(parts) != 2 or len(parts[0]) != 64:
            raise RuntimeError(f"malformed RAOS-06 checksum line {line_number}")
        digest, raw_path = parts
        int(digest, 16)
        path = checked_relative_path(raw_path, source=CONTENT_CHECKSUM_MEMBER)
        logical = path.as_posix()
        folded = logical.casefold()
        if folded in seen_casefold:
            raise RuntimeError(f"duplicate/casefold RAOS-06 checksum path: {logical}")
        seen_casefold.add(folded)
        result[logical] = digest
    if len(result) != 110:
        raise RuntimeError(
            f"unexpected RAOS-06 checksum count: expected 110, got {len(result)}"
        )
    return result


def verify_content_archive() -> dict[str, bytes]:
    with ZipFile(CONTENT_PACKAGE) as archive:
        files = checked_archive_files(archive)
        checksum_relative = CONTENT_CHECKSUM_MEMBER.removeprefix(CONTENT_ROOT)
        if checksum_relative not in files:
            raise RuntimeError("RAOS-06 checksum inventory is missing")
        declared = parse_checksum_inventory(archive.read(files[checksum_relative]))
        expected = set(files) - {checksum_relative}
        if set(declared) != expected:
            raise RuntimeError(
                "RAOS-06 checksum inventory differs from regular members: "
                f"missing={sorted(expected - set(declared))}, "
                f"unexpected={sorted(set(declared) - expected)}"
            )
        payloads: dict[str, bytes] = {}
        for relative, info in files.items():
            payload = archive.read(info)
            payloads[relative] = payload
            if relative == checksum_relative:
                continue
            if sha256_bytes(payload) != declared[relative]:
                raise RuntimeError(f"RAOS-06 member hash mismatch: {relative}")

    proposal_pairs = {
        "RAOS_06_001_data_alignment_patch_v0.1.sql": CONTENT_DATA_PROPOSAL,
        "RAOS_06_002_api_alignment_patch_v0.1.yaml": CONTENT_API_PROPOSAL,
        "RAOS_06_003_ai_alignment_patch_v0.1.yaml": CONTENT_AI_PROPOSAL,
    }
    for name, external in proposal_pairs.items():
        expected = external.read_bytes()
        if payloads[name] != expected or payloads[f"proposals/{name}"] != expected:
            raise RuntimeError(f"standalone/archive proposal byte mismatch: {name}")
    return payloads


def assert_immutable_inputs() -> None:
    for relative, expected in EXPECTED_INPUT_HASHES.items():
        path = REPO_ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required immutable input is missing: {relative}")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"immutable input hash mismatch for {relative}: expected {expected}, got {actual}"
            )
    verify_content_archive()


def path_has_symlink(root: Path, relative: PurePosixPath) -> bool:
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def verify_manifest_artifact(
    entry: Mapping[str, Any],
    *,
    seen: set[str],
    expected_prefix: str | None,
) -> Path:
    raw_path = entry.get("path")
    expected_hash = entry.get("sha256")
    expected_bytes = entry.get("bytes")
    if (
        not isinstance(raw_path, str)
        or not isinstance(expected_hash, str)
        or not isinstance(expected_bytes, int)
    ):
        raise RuntimeError(f"malformed predecessor artifact entry: {entry!r}")
    relative = checked_relative_path(raw_path, source="ST-0003 manifest")
    if expected_prefix is not None and not raw_path.startswith(expected_prefix):
        raise RuntimeError(f"unexpected predecessor artifact path: {raw_path}")
    folded = raw_path.casefold()
    if folded in seen:
        raise RuntimeError(f"duplicate/casefold predecessor artifact: {raw_path}")
    seen.add(folded)
    path = REPO_ROOT.joinpath(*relative.parts)
    if (
        not path.is_file()
        or path_has_symlink(REPO_ROOT, relative)
        or path.stat().st_size != expected_bytes
        or sha256_file(path) != expected_hash
    ):
        raise RuntimeError(f"predecessor artifact integrity failure: {raw_path}")
    return path


def verify_predecessor() -> dict[str, Any]:
    if (
        not PREDECESSOR_MANIFEST.is_file()
        or PREDECESSOR_MANIFEST.is_symlink()
        or sha256_file(PREDECESSOR_MANIFEST) != PREDECESSOR_MANIFEST_HASH
    ):
        raise RuntimeError(
            "predecessor manifest is missing or has hash drift from the pinned value"
        )
    manifest = load_yaml_bytes(
        PREDECESSOR_MANIFEST.read_bytes(), source=relative_repo_path(PREDECESSOR_MANIFEST)
    )
    document = manifest.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != PREDECESSOR_ID
        or document.get("version") != "0.3"
        or document.get("generated_by") != "scripts/build_st0003_revision.py"
    ):
        raise RuntimeError("unexpected ST-0003 manifest ownership/version")
    generated = manifest.get("generated_artifacts")
    sources = manifest.get("source_artifacts")
    inputs = manifest.get("inputs")
    if (
        not isinstance(generated, list)
        or not isinstance(sources, list)
        or not isinstance(inputs, list)
    ):
        raise RuntimeError("ST-0003 manifest artifact lists are missing")
    if manifest.get("generated_artifact_count") != len(generated):
        raise RuntimeError("ST-0003 generated artifact count is inconsistent")
    seen: set[str] = set()
    if len(inputs) != 5:
        raise RuntimeError("unexpected ST-0003 immutable-input count")
    for entry in inputs:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("path"), str)
            or not isinstance(entry.get("sha256"), str)
        ):
            raise RuntimeError("malformed ST-0003 immutable-input entry")
        raw_path = entry["path"]
        relative = checked_relative_path(raw_path, source="ST-0003 manifest inputs")
        folded = raw_path.casefold()
        if folded in seen:
            raise RuntimeError(f"duplicate/casefold predecessor input: {raw_path}")
        seen.add(folded)
        path = REPO_ROOT.joinpath(*relative.parts)
        if (
            not path.is_file()
            or path_has_symlink(REPO_ROOT, relative)
            or sha256_file(path) != entry["sha256"]
        ):
            raise RuntimeError(f"predecessor immutable-input integrity failure: {raw_path}")
    for entry in generated:
        if not isinstance(entry, dict):
            raise RuntimeError("malformed ST-0003 generated artifact entry")
        verify_manifest_artifact(
            entry,
            seen=seen,
            expected_prefix="changes/st-0003/",
        )
    for entry in sources:
        if not isinstance(entry, dict):
            raise RuntimeError("malformed ST-0003 source artifact entry")
        verify_manifest_artifact(entry, seen=seen, expected_prefix=None)
    if (
        not PREDECESSOR_JOB_STATE.is_file()
        or PREDECESSOR_JOB_STATE.is_symlink()
        or sha256_file(PREDECESSOR_JOB_STATE) != JOB_STATE_HASH
    ):
        raise RuntimeError("ST-0003 Job-state contract does not match pinned hash")
    contract_files = {
        path.relative_to(PREDECESSOR_ROOT).as_posix()
        for path in (PREDECESSOR_ROOT / "contracts").rglob("*")
        if path.is_file()
    }
    listed_contract_files = {
        entry["path"].removeprefix("changes/st-0003/")
        for entry in generated
        if isinstance(entry, dict)
        and isinstance(entry.get("path"), str)
        and entry["path"].startswith("changes/st-0003/contracts/")
    }
    if contract_files != listed_contract_files:
        raise RuntimeError("ST-0003 manifest does not own the complete contract tree")
    public_path = PREDECESSOR_ROOT / "contracts" / "openapi-public.v0.1.yaml"
    if sha256_file(public_path) != PUBLIC_OPENAPI_HASH:
        raise RuntimeError("ST-0003 public OpenAPI drifted from its pinned immutable hash")
    return manifest


def replace_revision_refs(value: Any) -> Any:
    if isinstance(value, str):
        result = value
        for previous, successor in ROOT_REVISION_FILES.items():
            result = result.replace(Path(previous).name, Path(successor).name)
        return result
    if isinstance(value, list):
        return [replace_revision_refs(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_revision_refs(item) for key, item in value.items()}
    return value


def revision_provenance() -> dict[str, Any]:
    return {
        "story_id": "ST-0004",
        "decision_id": "INT-DEC-005",
        "supporting_decision_ids": ["INT-DEC-006"],
        "revision_id": REVISION_ID,
        "predecessor": f"{PREDECESSOR_ID}@0.3",
        "predecessor_manifest_sha256": PREDECESSOR_MANIFEST_HASH,
    }


def copy_predecessor_contracts(contracts_root: Path) -> None:
    source_root = PREDECESSOR_ROOT / "contracts"
    contracts_root.mkdir(parents=True)
    seen: set[str] = set()
    copied = 0
    for directory, directory_names, filenames in os.walk(source_root, followlinks=False):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                raise RuntimeError(f"symlinked predecessor contract directory: {child}")
        for name in sorted(filenames):
            source = directory_path / name
            if source.is_symlink() or not source.is_file():
                raise RuntimeError(f"unsafe predecessor contract file: {source}")
            relative = source.relative_to(source_root)
            checked_relative_path(relative.as_posix(), source="ST-0003 contract tree")
            folded = relative.as_posix().casefold()
            if folded in seen:
                raise RuntimeError(f"casefold predecessor contract collision: {relative}")
            seen.add(folded)
            destination = contracts_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(source.read_bytes())
            copied += 1
    expected = sum(1 for path in source_root.rglob("*") if path.is_file())
    if copied != expected:
        raise RuntimeError(
            f"predecessor contract copy count mismatch: expected {expected}, got {copied}"
        )


def promote_predecessor_contracts(contracts_root: Path) -> None:
    copy_predecessor_contracts(contracts_root)
    for previous, successor in ROOT_REVISION_FILES.items():
        source = contracts_root / previous
        destination = contracts_root / successor
        if not source.is_file() or destination.exists():
            raise RuntimeError(f"cannot promote predecessor root contract: {previous}")
        document = replace_revision_refs(
            load_yaml_bytes(source.read_bytes(), source=previous)
        )
        if "openapi" in document or "asyncapi" in document:
            info = document.get("info")
            if not isinstance(info, dict):
                raise RuntimeError(f"missing info mapping in {previous}")
            info["version"] = REVISION_VERSION
            document["x-raos-content-revision"] = {
                "story_id": "ST-0004",
                "decision_id": "INT-DEC-005",
                "supporting_decision_ids": ["INT-DEC-006"],
                "revision_id": REVISION_ID,
                "predecessor_manifest_sha256": PREDECESSOR_MANIFEST_HASH,
                "proposal_execution": "FORBIDDEN",
            }
        else:
            metadata = document.get("document")
            if not isinstance(metadata, dict):
                raise RuntimeError(f"missing document metadata in {previous}")
            metadata["version"] = REVISION_VERSION
            metadata["status"] = "CANONICAL_REVISION_CANDIDATE"
            metadata["provenance"] = revision_provenance()
        write_yaml(destination, document)
        source.unlink()


def frozen_content_member(relative: str) -> bool:
    return (
        relative in FROZEN_TOP_LEVEL_CONTRACTS
        or relative.startswith("schemas/")
        or relative.startswith("templates/")
        or relative.startswith("fixtures/")
    )


def install_frozen_content(
    contracts_root: Path, payloads: Mapping[str, bytes]
) -> list[dict[str, Any]]:
    frozen: list[dict[str, Any]] = []
    for relative in sorted(payloads):
        if not frozen_content_member(relative):
            continue
        destination = contracts_root / "content" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payloads[relative])
        frozen.append(
            {
                "archive_member": f"{CONTENT_ROOT}{relative}",
                "output_path": f"content/{relative}",
                "bytes": len(payloads[relative]),
                "sha256": sha256_bytes(payloads[relative]),
                "byte_identical": True,
            }
        )
    return frozen


def uuid_schema(*, nullable: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "format": "uuid"}
    if nullable:
        schema["type"] = ["string", "null"]
    return schema


def timestamp_schema(*, nullable: bool = False) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "format": "date-time"}
    if nullable:
        schema["type"] = ["string", "null"]
    return schema


def sha256_schema() -> dict[str, Any]:
    return {"type": "string", "pattern": "^[0-9a-f]{64}$"}


def semantic_version_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "pattern": r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$",
        "maxLength": 64,
    }


def strict_schema(
    slug: str,
    title: str,
    properties: Mapping[str, Any],
    required: Iterable[str],
    *,
    description: str,
    invariants: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://schemas.raos.local/content-revision/{slug}.v1.schema.json",
        "title": title,
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "properties": dict(properties),
        "required": list(required),
    }
    if invariants:
        document["x-raos-invariants"] = dict(invariants)
    return document


def content_resource_schemas() -> dict[str, dict[str, Any]]:
    status_version = {
        "type": "string",
        "enum": ["DRAFT", "ACTIVE", "DEPRECATED", "RETIRED"],
    }
    opaque_object = {"type": "object", "additionalProperties": True}
    text = {"type": "string", "minLength": 1, "maxLength": 255}
    nonempty_text = {"type": "string", "minLength": 1, "maxLength": 4000}
    schemas: dict[str, dict[str, Any]] = {}

    schemas["ContentSchemaVersionV1"] = strict_schema(
        "content-schema-version",
        "Content Schema Version",
        {
            "id": uuid_schema(),
            "schema_code": text,
            "semantic_version": semantic_version_schema(),
            "artifact_id": uuid_schema(),
            "schema_sha256": sha256_schema(),
            "status": status_version,
            "effective_from": timestamp_schema(),
            "effective_to": timestamp_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "schema_code",
            "semantic_version",
            "artifact_id",
            "schema_sha256",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Hash-bound, append-only Content AST schema version.",
        invariants={
            "active_requires_human_approval": True,
            "single_active_per_schema_code": True,
            "non_active_preserves_approval_history": True,
        },
    )
    schemas["ArticleTypeVersionV1"] = strict_schema(
        "article-type-version",
        "Article Type Version",
        {
            "id": uuid_schema(),
            "article_type_code": text,
            "semantic_version": semantic_version_schema(),
            "contract": opaque_object,
            "contract_sha256": sha256_schema(),
            "status": status_version,
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "article_type_code",
            "semantic_version",
            "contract",
            "contract_sha256",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Versioned article-type contract; active versions are human approved.",
        invariants={"single_active_per_article_type_code": True, "append_only": True},
    )
    schemas["ArticleTemplateVersionV1"] = strict_schema(
        "article-template-version",
        "Article Template Version",
        {
            "id": uuid_schema(),
            "article_type_version_id": uuid_schema(),
            "semantic_version": semantic_version_schema(),
            "template": opaque_object,
            "template_sha256": sha256_schema(),
            "status": status_version,
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "article_type_version_id",
            "semantic_version",
            "template",
            "template_sha256",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Hash-bound template version for exactly one article-type version.",
        invariants={"single_active_per_article_type_version": True, "append_only": True},
    )
    schemas["EditorialMethodologyVersionV1"] = strict_schema(
        "editorial-methodology-version",
        "Editorial Methodology Version",
        {
            "id": uuid_schema(),
            "methodology_code": text,
            "semantic_version": semantic_version_schema(),
            "article_type_version_id": uuid_schema(),
            "definition": opaque_object,
            "definition_sha256": sha256_schema(),
            "excludes_finance_inputs": {"const": True},
            "status": status_version,
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "methodology_code",
            "semantic_version",
            "article_type_version_id",
            "definition",
            "definition_sha256",
            "excludes_finance_inputs",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Recommendation methodology bound to an article-type version.",
        invariants={
            "finance_inputs_forbidden": True,
            "single_active_per_methodology_and_article_type": True,
            "append_only": True,
        },
    )
    schemas["ArticleMethodologyBindingV1"] = strict_schema(
        "article-methodology-binding",
        "Article Methodology Binding",
        {
            "article_version_id": uuid_schema(),
            "methodology_version_id": uuid_schema(),
            "candidate_universe_artifact_id": uuid_schema(),
            "candidate_universe_sha256": sha256_schema(),
            "bound_at": timestamp_schema(),
            "bound_by_principal_id": uuid_schema(),
        },
        (
            "article_version_id",
            "methodology_version_id",
            "candidate_universe_artifact_id",
            "candidate_universe_sha256",
            "bound_at",
            "bound_by_principal_id",
        ),
        description="Immutable methodology and candidate-universe binding.",
        invariants={"article_type_must_match": True, "append_only": True},
    )
    schemas["SeoMetadataVersionV1"] = strict_schema(
        "seo-metadata-version",
        "SEO Metadata Version",
        {
            "id": uuid_schema(),
            "article_version_id": uuid_schema(),
            "semantic_version": semantic_version_schema(),
            "metadata": opaque_object,
            "metadata_sha256": sha256_schema(),
            "status": {
                "type": "string",
                "enum": ["DRAFT", "VALIDATED", "APPROVED", "REJECTED"],
            },
            "validated_at": timestamp_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "article_version_id",
            "semantic_version",
            "metadata",
            "metadata_sha256",
            "status",
            "validated_at",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Append-only SEO metadata version; renderer owns JSON-LD output.",
        invariants={"approved_requires_human_approval": True, "append_only": True},
    )
    schemas["StructuredDataManifestV1"] = strict_schema(
        "structured-data-manifest-resource",
        "Structured Data Manifest Resource",
        {
            "id": uuid_schema(),
            "article_version_id": uuid_schema(),
            "seo_metadata_version_id": uuid_schema(),
            "generator_version": text,
            "visible_content_sha256": sha256_schema(),
            "jsonld_artifact_id": uuid_schema(),
            "jsonld_sha256": sha256_schema(),
            "enabled_types": {
                "type": "array",
                "items": text,
                "uniqueItems": True,
            },
            "disabled_types": {
                "type": "array",
                "items": text,
                "uniqueItems": True,
            },
            "validation_status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "validated_at": timestamp_schema(),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "article_version_id",
            "seo_metadata_version_id",
            "generator_version",
            "visible_content_sha256",
            "jsonld_artifact_id",
            "jsonld_sha256",
            "enabled_types",
            "disabled_types",
            "validation_status",
            "validated_at",
            "created_at",
        ),
        description="Deterministic JSON-LD render/validation manifest.",
        invariants={
            "seo_and_article_binding_must_match": True,
            "enabled_disabled_disjoint": True,
            "faq_page_disabled": True,
        },
    )
    schemas["MediaAssetV1"] = strict_schema(
        "media-asset-resource",
        "Media Asset Resource",
        {
            "id": uuid_schema(),
            "display_id": text,
            "asset_class": text,
            "source_id": uuid_schema(),
            "raw_artifact_id": uuid_schema(),
            "asset_sha256": sha256_schema(),
            "license_status": text,
            "modification_policy": text,
            "alt_text": {"type": "string", "maxLength": 2000},
            "decorative": {"type": "boolean"},
            "long_description_artifact_id": uuid_schema(nullable=True),
            "width": {"type": "integer", "minimum": 1},
            "height": {"type": "integer", "minimum": 1},
            "captured_or_observed_at": timestamp_schema(),
            "status": {
                "type": "string",
                "enum": ["DRAFT", "APPROVED", "BLOCKED", "RETIRED"],
            },
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "display_id",
            "asset_class",
            "source_id",
            "raw_artifact_id",
            "asset_sha256",
            "license_status",
            "modification_policy",
            "alt_text",
            "decorative",
            "long_description_artifact_id",
            "width",
            "height",
            "captured_or_observed_at",
            "status",
            "approved_by_principal_id",
            "approved_at",
            "created_at",
        ),
        description="Source- and artifact-bound media asset.",
        invariants={
            "source_and_raw_artifact_required": True,
            "non_decorative_alt_text_required": True,
            "approved_requires_human_approval": True,
        },
    )
    schemas["FirstHandExperienceRecordV1"] = strict_schema(
        "first-hand-experience-record",
        "First-Hand Experience Record",
        {
            "id": uuid_schema(),
            "display_id": text,
            "product_id": uuid_schema(),
            "product_variant_identity": opaque_object,
            "tester_principal_id": uuid_schema(),
            "procedure_version": text,
            "started_at": timestamp_schema(),
            "ended_at": timestamp_schema(),
            "environment": opaque_object,
            "limitations": nonempty_text,
            "review_status": {
                "type": "string",
                "enum": ["DRAFT", "REVIEWED", "APPROVED", "REJECTED"],
            },
            "reviewed_by_principal_id": uuid_schema(nullable=True),
            "reviewed_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "id",
            "display_id",
            "product_id",
            "product_variant_identity",
            "tester_principal_id",
            "procedure_version",
            "started_at",
            "ended_at",
            "environment",
            "limitations",
            "review_status",
            "reviewed_by_principal_id",
            "reviewed_at",
            "created_at",
        ),
        description="Human-authored, evidence-backed first-hand experience record.",
        invariants={
            "ai_authorship_forbidden": True,
            "approved_requires_distinct_human_reviewer": True,
        },
    )
    schemas["FirstHandExperienceAssetV1"] = strict_schema(
        "first-hand-experience-asset",
        "First-Hand Experience Asset",
        {
            "experience_record_id": uuid_schema(),
            "artifact_id": uuid_schema(),
            "role": {
                "type": "string",
                "enum": ["PHOTO", "VIDEO", "MEASUREMENT", "LOG", "PROCEDURE", "OTHER"],
            },
            "artifact_sha256": sha256_schema(),
            "created_at": timestamp_schema(),
        },
        (
            "experience_record_id",
            "artifact_id",
            "role",
            "artifact_sha256",
            "created_at",
        ),
        description="Immutable artifact evidence attached to an experience record.",
    )
    schemas["ArticleDisclosureContextV1"] = strict_schema(
        "article-disclosure-context",
        "Article Disclosure Context",
        {
            "article_version_id": uuid_schema(),
            "affiliate_relationship": {"type": "boolean"},
            "material_benefit_relationship": {"type": "boolean"},
            "benefit_types": {"type": "array", "items": text, "uniqueItems": True},
            "disclosure_policy_version": semantic_version_schema(),
            "additional_disclosure_text": {
                "type": ["string", "null"],
                "maxLength": 4000,
            },
            "reviewed_by_principal_id": uuid_schema(nullable=True),
            "reviewed_at": timestamp_schema(nullable=True),
            "created_at": timestamp_schema(),
        },
        (
            "article_version_id",
            "affiliate_relationship",
            "material_benefit_relationship",
            "benefit_types",
            "disclosure_policy_version",
            "additional_disclosure_text",
            "reviewed_by_principal_id",
            "reviewed_at",
            "created_at",
        ),
        description="Renderer-owned, policy-versioned disclosure inputs.",
        invariants={"ai_override_forbidden": True, "renderer_owned": True},
    )

    schemas["ContentValidationRequestV1"] = strict_schema(
        "content-validation-request",
        "Content Validation Request",
        {
            "content_schema_version_id": uuid_schema(),
            "content_schema_sha256": sha256_schema(),
            "article_type_version_id": uuid_schema(),
            "article_template_version_id": uuid_schema(),
            "content_ast": {
                "$ref": "../../content/schemas/content-ast.schema.json"
            },
        },
        (
            "content_schema_version_id",
            "content_schema_sha256",
            "article_type_version_id",
            "article_template_version_id",
            "content_ast",
        ),
        description="Hash-bound AST validation command input.",
        invariants={"unknown_schema_fails_closed": True, "stored_ast_only": True},
    )
    schemas["ContentValidationResultV1"] = strict_schema(
        "content-validation-result",
        "Content Validation Result",
        {
            "valid": {"type": "boolean"},
            "content_schema_version_id": uuid_schema(),
            "content_schema_sha256": sha256_schema(),
            "finding_codes": {
                "type": "array",
                "items": {"type": "string", "minLength": 1, "maxLength": 128},
                "uniqueItems": True,
            },
        },
        ("valid", "content_schema_version_id", "content_schema_sha256", "finding_codes"),
        description="Deterministic schema and policy validation result.",
    )
    schemas["SeoMetadataUpdateRequestV1"] = strict_schema(
        "seo-metadata-update-request",
        "SEO Metadata Successor Request",
        {
            "semantic_version": semantic_version_schema(),
            "metadata": {
                "$ref": "../../content/schemas/seo-metadata.schema.json"
            },
            "metadata_sha256": sha256_schema(),
        },
        ("semantic_version", "metadata", "metadata_sha256"),
        description="Create a successor SEO metadata version; never mutate approved bytes.",
        invariants={"creates_successor_version": True},
    )
    schemas["MediaAssetCreateRequestV1"] = strict_schema(
        "media-asset-create-request",
        "Media Asset Create Request",
        {
            key: value
            for key, value in schemas["MediaAssetV1"]["properties"].items()
            if key
            not in {
                "id",
                "display_id",
                "status",
                "approved_by_principal_id",
                "approved_at",
                "created_at",
            }
        },
        (
            "asset_class",
            "source_id",
            "raw_artifact_id",
            "asset_sha256",
            "license_status",
            "modification_policy",
            "alt_text",
            "decorative",
            "long_description_artifact_id",
            "width",
            "height",
            "captured_or_observed_at",
        ),
        description="Register a source-bound media artifact.",
    )
    schemas["MediaAssetUpdateRequestV1"] = strict_schema(
        "media-asset-update-request",
        "Media Asset Update Request",
        {
            "alt_text": {"type": "string", "maxLength": 2000},
            "decorative": {"type": "boolean"},
            "long_description_artifact_id": uuid_schema(nullable=True),
            "status": {
                "type": "string",
                "enum": ["DRAFT", "APPROVED", "BLOCKED", "RETIRED"],
            },
        },
        (),
        description="Concurrency-guarded metadata/status transition; asset bytes are immutable.",
        invariants={"asset_identity_and_hash_immutable": True},
    )
    schemas["FirstHandExperienceCreateRequestV1"] = strict_schema(
        "first-hand-experience-create-request",
        "First-Hand Experience Create Request",
        {
            key: value
            for key, value in schemas["FirstHandExperienceRecordV1"]["properties"].items()
            if key
            not in {
                "id",
                "display_id",
                "tester_principal_id",
                "review_status",
                "reviewed_by_principal_id",
                "reviewed_at",
                "created_at",
            }
        },
        (
            "product_id",
            "product_variant_identity",
            "procedure_version",
            "started_at",
            "ended_at",
            "environment",
            "limitations",
        ),
        description="Authenticated human tester is server-derived, never body supplied.",
        invariants={"tester_principal_source": "AUTHENTICATED_HUMAN"},
    )
    schemas["ContentReviewRequestV1"] = strict_schema(
        "content-review-request",
        "Content Review Decision Request",
        {
            "decision": {"type": "string", "enum": ["APPROVE", "REJECT"]},
            "reason": nonempty_text,
            "checklist_version": semantic_version_schema(),
            "checklist_sha256": sha256_schema(),
            "review_artifact_id": uuid_schema(),
            "review_artifact_sha256": sha256_schema(),
        },
        (
            "decision",
            "reason",
            "checklist_version",
            "checklist_sha256",
            "review_artifact_id",
            "review_artifact_sha256",
        ),
        description="Human-only, step-up authenticated final content review decision.",
        invariants={
            "human_only": True,
            "ai_and_service_principals_forbidden": True,
            "author_final_approver_separation": True,
        },
    )
    schemas["MethodologyValidationRequestV1"] = strict_schema(
        "methodology-validation-request",
        "Methodology Validation Request",
        {"definition_sha256": sha256_schema()},
        ("definition_sha256",),
        description="Validate the stored methodology artifact without changing it.",
    )
    schemas["StructuredDataCommandRequestV1"] = strict_schema(
        "structured-data-command-request",
        "Structured Data Command Request",
        {
            "seo_metadata_version_id": uuid_schema(),
            "visible_content_sha256": sha256_schema(),
            "generator_version": semantic_version_schema(),
        },
        ("seo_metadata_version_id", "visible_content_sha256", "generator_version"),
        description="Renderer-owned deterministic structured-data command.",
        invariants={"ai_json_ld_forbidden": True},
    )
    schemas["PublicationManifestCreateRequestV1"] = strict_schema(
        "publication-manifest-create-request",
        "Publication Content Manifest Create Request",
        {
            "article_version_id": uuid_schema(),
            "content_schema_version_id": uuid_schema(),
            "article_type_version_id": uuid_schema(),
            "article_template_version_id": uuid_schema(),
            "methodology_version_id": uuid_schema(),
            "policy_bundle_version_id": uuid_schema(),
            "seo_metadata_version_id": uuid_schema(),
            "structured_data_manifest_id": uuid_schema(),
            "review_decision_id": uuid_schema(),
            "renderer_version": semantic_version_schema(),
        },
        (
            "article_version_id",
            "content_schema_version_id",
            "article_type_version_id",
            "article_template_version_id",
            "methodology_version_id",
            "policy_bundle_version_id",
            "seo_metadata_version_id",
            "structured_data_manifest_id",
            "review_decision_id",
            "renderer_version",
        ),
        description="Hash resolution is server-owned; finance, secrets and raw evidence are forbidden.",
        invariants={
            "human_approval_required": True,
            "blocking_findings_must_be_zero": True,
            "finance_secret_internal_uri_forbidden": True,
        },
    )
    return schemas


def generate_type_schemas(contracts_root: Path) -> dict[str, dict[str, Any]]:
    schemas = content_resource_schemas()
    output = contracts_root / "schemas" / "content-revision"
    for component, schema in schemas.items():
        slug = schema["$id"].rsplit("/", 1)[-1]
        write_json(output / slug, schema)
    return schemas


def load_frozen_yaml(contracts_root: Path, name: str) -> dict[str, Any]:
    path = contracts_root / "content" / name
    return load_yaml_bytes(path.read_bytes(), source=path.as_posix())


def build_content_adoption(contracts_root: Path) -> dict[str, Any]:
    catalog = load_frozen_yaml(contracts_root, "RAOS_06_content_contract_catalog_v0.1.yaml")
    article_types = load_frozen_yaml(contracts_root, "RAOS_06_article_type_catalog_v0.1.yaml")
    blocks = load_frozen_yaml(contracts_root, "RAOS_06_content_block_catalog_v0.1.yaml")
    registry = load_frozen_yaml(contracts_root, "RAOS_06_schema_registry_v0.1.yaml")
    expected = load_frozen_yaml(
        contracts_root, "fixtures/invalid/expected_results.yaml"
    )
    valid_names = sorted(
        path.name
        for path in (contracts_root / "content" / "fixtures" / "valid").glob("*.json")
    )
    invalid_names = sorted(
        item["path"] for item in expected.get("fixtures", []) if isinstance(item, dict)
    )
    return {
        "document": {
            "id": "RAOS-CONTENT-CANONICAL-ADOPTION-001",
            "version": REVISION_VERSION,
            "status": "CANONICAL_REVISION_CANDIDATE",
            "provenance": revision_provenance(),
        },
        "adopted_package": {
            "id": catalog.get("package_id"),
            "version": catalog.get("package_version"),
            "archive_path": relative_repo_path(CONTENT_PACKAGE),
            "archive_sha256": EXPECTED_INPUT_HASHES[
                "docs/upstream/RAOS_06_content_design_package_v0.1.zip"
            ],
            "proposal_execution": "FORBIDDEN",
        },
        "inventory": {
            "article_type_count": len(article_types.get("article_types", [])),
            "block_type_count": len(blocks.get("blocks", [])),
            "schema_count": len(registry.get("schemas", [])),
            "valid_fixture_count": len(valid_names),
            "invalid_fixture_count": len(invalid_names),
            "valid_fixtures": valid_names,
            "invalid_fixtures": invalid_names,
        },
        "canonical_field_names": {
            "content_schema_version": "content_schema_version_id",
            "article_type_version": "article_type_version_id",
            "article_template_version": "article_template_version_id",
            "methodology_version": "methodology_version_id",
            "editorial_policy_bundle": "policy_bundle_version_id",
            "renderer_owned_fields": "renderer_owned_field_set",
        },
        "ast_boundary": {
            "stored_ast_schema": "content/schemas/content-ast.schema.json",
            "stored_ast_requires_disclosure_slot_first": True,
            "disclosure_slot_is_renderer_owned_placeholder": True,
            "renderer_owned_payload_mutation_by_ai": "FORBIDDEN",
            "raw_html": "FORBIDDEN",
            "manual_affiliate_url": "FORBIDDEN",
            "finance_fields": "FORBIDDEN",
            "review_body": "FORBIDDEN",
            "unknown_schema_or_hash": "FAIL_CLOSED",
        },
        "publication_authority": {
            "content_repository": "CANONICAL",
            "cms": "PUBLICATION_ADAPTER_ONLY",
            "auto_publish": "FORBIDDEN",
            "human_final_approval_required": True,
            "blocking_finding_count_required": 0,
            "quality_score_minimum": 85,
            "all_axis_floors_required": True,
        },
        "compatibility": {
            "classification": "ADDITIVE_PRE_RELEASE_CANONICAL_REVISION",
            "json_schema_dialect": "2020-12",
            "openapi_version": "3.1.1",
            "existing_operations_removed_or_semantically_changed": False,
            "new_required_fields_on_existing_schemas": False,
            "public_evidence_or_finance_exposure": False,
            "content_event_delta": "NONE",
        },
    }


def build_ai_alignment(payloads: Mapping[str, bytes]) -> dict[str, Any]:
    proposal = load_yaml_bytes(
        payloads["RAOS_06_003_ai_alignment_patch_v0.1.yaml"],
        source="RAOS_06_003_ai_alignment_patch_v0.1.yaml",
    )
    affected: list[dict[str, Any]] = []
    for raw in proposal.get("affected_tasks", []):
        if not isinstance(raw, dict):
            raise RuntimeError("malformed content AI affected-task entry")
        item = dict(raw)
        item["successor_contract_version"] = REVISION_VERSION
        item["input_binding"] = "HASH_BOUND_VERSION_OR_MANIFEST"
        item["existing_prompt_hash_preserved"] = True
        affected.append(item)
    return {
        "document": {
            "id": "RAOS-CONTENT-AI-ALIGNMENT-001",
            "version": REVISION_VERSION,
            "status": "CANONICAL_REVISION_CANDIDATE",
            "provenance": revision_provenance(),
        },
        "proposal": {
            "id": proposal.get("document", {}).get("id"),
            "path": relative_repo_path(CONTENT_AI_PROPOSAL),
            "sha256": EXPECTED_INPUT_HASHES[
                "docs/upstream/patches/RAOS_06_003_ai_alignment_patch_v0.1.yaml"
            ],
            "execution": "FORBIDDEN",
        },
        "affected_tasks": affected,
        "global_prompt_constraints": proposal.get("global_prompt_additions", []),
        "evaluation_dimensions": proposal.get("evaluation_additions", []),
        "authority": {
            "ai_approval": "FORBIDDEN",
            "ai_publication": "FORBIDDEN",
            "policy_assistant": "FINDING_CANDIDATE_ONLY",
            "renderer_owned_fields": "FORBIDDEN_OUTPUT",
            "finance_recommendation_input": "FORBIDDEN",
        },
        "canonical_input_names": {
            "content_ast_schema_version": "content_schema_version_id",
            "article_type_version": "article_type_version_id",
            "article_template_version": "article_template_version_id",
            "methodology_version": "methodology_version_id",
            "editorial_policy_bundle": "policy_bundle_version_id",
            "immutable_renderer_owned_fields": "renderer_owned_field_set",
        },
        "frozen_raos_05_artifacts_modified": False,
    }


def patch_schema_registry(contracts_root: Path) -> None:
    path = contracts_root / "catalogs" / "schema-registry.v0.4.yaml"
    document = load_yaml_bytes(path.read_bytes(), source=path.as_posix())
    entries = document.get("schemas")
    if not isinstance(entries, list):
        raise RuntimeError("schema registry entries are missing")
    by_path: dict[str, dict[str, Any]] = {}
    ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("malformed predecessor schema registry entry")
        by_path[entry["path"]] = entry
        schema_id = entry.get("id")
        if isinstance(schema_id, str):
            ids.add(schema_id)
    roots = (
        contracts_root / "content" / "schemas",
        contracts_root / "schemas" / "content-revision",
    )
    for root in roots:
        for schema_path in sorted(root.rglob("*.json")):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema_id = schema.get("$id")
            if not isinstance(schema_id, str) or not schema_id:
                raise RuntimeError(f"content schema has no $id: {schema_path}")
            logical = schema_path.relative_to(contracts_root).as_posix()
            if logical in by_path or schema_id in ids:
                raise RuntimeError(f"duplicate schema path or $id in content revision: {logical}")
            entry = {
                "path": logical,
                "id": schema_id,
                "title": schema.get("title", schema_path.stem),
                "sha256": sha256_file(schema_path),
                "compatibility": "NEW",
                "provenance": "RAOS-CONTENT-001"
                if logical.startswith("content/")
                else REVISION_ID,
            }
            entries.append(entry)
            by_path[logical] = entry
            ids.add(schema_id)
    entries.sort(key=lambda item: item["path"])
    document["schema_count"] = len(entries)
    document["content_schema_count"] = sum(
        1
        for entry in entries
        if entry["path"].startswith("content/schemas/")
        or entry["path"].startswith("schemas/content-revision/")
    )
    document["content_revision_policy"] = {
        "unknown_schema_or_hash": "FAIL_CLOSED",
        "frozen_raos_06_schema_bytes_modified": False,
        "new_required_fields_on_predecessor_schemas": False,
    }
    write_yaml(path, document)


def resource_catalog_entry(
    name: str,
    source_tables: list[str],
    schema: Mapping[str, Any],
    *,
    create_fields: list[str] | None = None,
    update_fields: list[str] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    readonly = {
        "id",
        "display_id",
        "created_at",
        "approved_by_principal_id",
        "approved_at",
        "reviewed_by_principal_id",
        "reviewed_at",
        "validated_at",
    }
    return {
        "name": name,
        "source_tables": source_tables,
        "classification": "CONFIDENTIAL",
        "etag": bool(update_fields),
        "fields": [
            {
                "name": field,
                "schema": definition,
                "read_only": field in readonly,
            }
            for field, definition in schema.get("properties", {}).items()
        ],
        "create_fields": create_fields or [],
        "update_fields": update_fields or [],
        "notes": notes or [],
        "schema_id": schema.get("$id"),
        "revision": REVISION_ID,
    }


def patch_resource_catalog(
    contracts_root: Path, schemas: Mapping[str, Mapping[str, Any]]
) -> None:
    path = contracts_root / "catalogs" / "resource-contracts.v0.4.yaml"
    document = load_yaml_bytes(path.read_bytes(), source=path.as_posix())
    resources = document.get("resources")
    if not isinstance(resources, list):
        raise RuntimeError("resource catalog resources are missing")
    existing = {entry.get("name") for entry in resources if isinstance(entry, dict)}
    definitions = (
        ("ContentSchemaVersion", ["editorial.content_schema_version"], "ContentSchemaVersionV1"),
        ("ArticleTypeVersion", ["editorial.article_type_version"], "ArticleTypeVersionV1"),
        ("ArticleTemplateVersion", ["editorial.article_template_version"], "ArticleTemplateVersionV1"),
        ("EditorialMethodologyVersion", ["editorial.editorial_methodology_version"], "EditorialMethodologyVersionV1"),
        ("ArticleMethodologyBinding", ["editorial.article_methodology_binding"], "ArticleMethodologyBindingV1"),
        ("SeoMetadataVersion", ["editorial.seo_metadata_version"], "SeoMetadataVersionV1"),
        ("StructuredDataManifest", ["editorial.structured_data_manifest"], "StructuredDataManifestV1"),
        ("MediaAsset", ["editorial.media_asset"], "MediaAssetV1"),
        ("FirstHandExperienceRecord", ["evidence.first_hand_experience_record"], "FirstHandExperienceRecordV1"),
        ("FirstHandExperienceAsset", ["evidence.first_hand_experience_asset"], "FirstHandExperienceAssetV1"),
        ("ArticleDisclosureContext", ["editorial.article_disclosure_context"], "ArticleDisclosureContextV1"),
    )
    for name, tables, component in definitions:
        if name in existing:
            raise RuntimeError(f"content resource collides with predecessor resource: {name}")
        create_fields: list[str] = []
        update_fields: list[str] = []
        if name == "MediaAsset":
            create_fields = list(schemas["MediaAssetCreateRequestV1"]["properties"])
            update_fields = list(schemas["MediaAssetUpdateRequestV1"]["properties"])
        resources.append(
            resource_catalog_entry(
                name,
                tables,
                schemas[component],
                create_fields=create_fields,
                update_fields=update_fields,
                notes=["Version/approval transitions are server-owned and audited."],
            )
        )
    document["content_resource_count"] = len(definitions)
    document["content_cross_layer_bindings"] = {
        "article_version": [
            "content_schema_version_id",
            "article_type_version_id",
            "article_template_version_id",
            "seo_metadata_version_id",
        ],
        "methodology": "methodology_version_id plus candidate_universe artifact/hash",
        "publication_manifest": "existing publication snapshot plus RAOS-06 manifest schema",
        "review_decision": "existing review/audit authority plus RAOS-06 decision schema",
    }
    document["content_security"] = {
        "public_surface": "NONE",
        "ai_approval_or_publication": "FORBIDDEN",
        "human_final_approval_required": True,
        "cms_role": "PUBLICATION_ADAPTER_ONLY",
    }
    write_yaml(path, document)


def list_schema(component: str) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "items": {
                "type": "array",
                "items": {"$ref": f"#/components/schemas/{component}"},
            },
            "next_cursor": {"type": ["string", "null"]},
        },
        "required": ["items", "next_cursor"],
    }


def path_parameter(name: str) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string", "minLength": 1, "maxLength": 255}
    if name.endswith("id") or name == "id":
        schema = uuid_schema()
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": f"Stable {name} identifier.",
        "schema": schema,
    }


def success_response(
    component: str,
    *,
    status: str,
    description: str,
    etag: bool = False,
    location: bool = False,
) -> dict[str, Any]:
    headers: dict[str, Any] = {
        "X-Request-ID": {"$ref": "#/components/headers/XRequestID"},
        "traceparent": {"$ref": "#/components/headers/Traceparent"},
    }
    if etag:
        headers["ETag"] = {
            "description": "Strong ETag for optimistic concurrency.",
            "schema": {"type": "string"},
        }
    if location:
        headers["Location"] = {
            "description": "Created resource URL.",
            "schema": {"type": "string", "format": "uri-reference"},
        }
    return {
        "description": description,
        "headers": headers,
        "content": {
            "application/json": {"schema": {"$ref": f"#/components/schemas/{component}"}}
        },
    }


def operation(
    operation_id: str,
    *,
    tag: str,
    summary: str,
    response_component: str,
    response_status: str = "200",
    path_parameters: Iterable[str] = (),
    request_component: str | None = None,
    idempotency: bool = False,
    concurrency: bool = False,
    internal: bool = False,
    scope: str = "content:read",
    audit_action: str | None = None,
    human_only: bool = False,
) -> dict[str, Any]:
    parameters: list[dict[str, Any]] = [
        {"$ref": "#/components/parameters/RequestID"},
        {"$ref": "#/components/parameters/Traceparent"},
    ]
    parameters.extend(path_parameter(name) for name in path_parameters)
    if idempotency:
        parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
    if concurrency:
        parameters.append({"$ref": "#/components/parameters/IfMatch"})
    responses: dict[str, Any] = {
        response_status: success_response(
            response_component,
            status=response_status,
            description="Content contract operation succeeded.",
            etag=concurrency or response_status == "200",
            location=response_status == "201",
        )
    }
    for code in ("400", "401", "403", "404", "409", "412", "422", "429", "500"):
        if code == "412" and not concurrency:
            continue
        responses[code] = {"$ref": f"#/components/responses/{code}"}
    result: dict[str, Any] = {
        "operationId": operation_id,
        "tags": [tag],
        "summary": summary,
        "description": summary,
        "parameters": parameters,
        "responses": responses,
        "x-raos-operation-id": operation_id,
        "x-raos-kind": "command" if request_component else "query",
        "x-raos-requirements": ["FR-007", "FR-010"],
        "x-raos-implementation-slice": "ST-0004",
        "x-raos-idempotency-required": idempotency,
        "x-raos-concurrency-required": concurrency,
        "x-raos-audit-action": audit_action,
        "x-raos-error-codes": [],
        "x-raos-classification": "CONFIDENTIAL",
        "x-raos-authorization-context": "SERVICE" if internal else "CONTENT",
        "security": [{"serviceBearer": []}] if internal else [{"oidcOAuth2": [scope]}],
        "x-raos-success-etag-required": concurrency,
    }
    if request_component:
        result["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {"$ref": f"#/components/schemas/{request_component}"}
                }
            },
        }
    if human_only:
        result.update(
            {
                "x-raos-human-approval-required": True,
                "x-raos-step-up-authentication-required": True,
                "x-raos-ai-principal-forbidden": True,
                "x-raos-service-principal-forbidden": True,
                "x-raos-author-final-approver-separation": True,
            }
        )
    return result


def add_openapi_components(
    document: MutableMapping[str, Any], schemas: Mapping[str, Mapping[str, Any]]
) -> None:
    components = document.get("components")
    if not isinstance(components, dict):
        raise RuntimeError("OpenAPI components mapping is missing")
    component_schemas = components.get("schemas")
    if not isinstance(component_schemas, dict):
        raise RuntimeError("OpenAPI component schemas are missing")
    for name, schema in schemas.items():
        if name in component_schemas:
            raise RuntimeError(f"OpenAPI component collision: {name}")
        slug = str(schema["$id"]).rsplit("/", 1)[-1]
        component_schemas[name] = {
            "$ref": f"./schemas/content-revision/{slug}"
        }
    frozen = {
        "ContentAstV1": "content-ast.schema.json",
        "RecommendationMethodologyContractV1": "recommendation-methodology.schema.json",
        "SeoMetadataContractV1": "seo-metadata.schema.json",
        "StructuredDataManifestContractV1": "structured-data-manifest.schema.json",
        "EditorialReviewDecisionV1": "editorial-review-decision.schema.json",
        "PublicationContentManifestV1": "publication-content-manifest.schema.json",
    }
    for name, relative in frozen.items():
        if name in component_schemas:
            raise RuntimeError(f"OpenAPI frozen component collision: {name}")
        component_schemas[name] = {"$ref": f"./content/schemas/{relative}"}
    for resource in (
        "ContentSchemaVersionV1",
        "ArticleTypeVersionV1",
        "ArticleTemplateVersionV1",
        "EditorialMethodologyVersionV1",
    ):
        component_schemas[resource.removesuffix("V1") + "ListV1"] = list_schema(resource)
    document["x-raos-schema-component-count"] = len(component_schemas)


def add_paths(document: MutableMapping[str, Any], additions: Mapping[str, Any]) -> None:
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("OpenAPI paths mapping is missing")
    collisions = sorted(set(paths) & set(additions))
    if collisions:
        raise RuntimeError(f"content OpenAPI paths collide with predecessor: {collisions}")
    paths.update(additions)


def patch_admin_openapi(
    contracts_root: Path, schemas: Mapping[str, Mapping[str, Any]]
) -> None:
    path = contracts_root / "openapi-admin.v0.4.yaml"
    document = load_yaml_bytes(path.read_bytes(), source=path.as_posix())
    add_openapi_components(document, schemas)
    try:
        declared_scopes = document["components"]["securitySchemes"]["oidcOAuth2"][
            "flows"
        ]["authorizationCode"]["scopes"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Admin OAuth2 authorization-code scope map is missing") from exc
    if not isinstance(declared_scopes, dict):
        raise RuntimeError("Admin OAuth2 authorization-code scopes must be a mapping")
    for scope in CONTENT_ADMIN_OAUTH_SCOPES:
        existing = declared_scopes.get(scope)
        if existing is not None and existing != scope:
            raise RuntimeError(f"Admin OAuth2 scope declaration drift: {scope}")
        declared_scopes[scope] = scope
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise RuntimeError("Admin OpenAPI paths mapping is missing")
    for inherited_path in (
        "/api/v1/admin/ai/evaluation-datasets/{id}:lock",
        "/api/v1/admin/ai/release-decisions/{id}:approve-canary",
        "/api/v1/admin/ai/release-decisions/{id}:approve-active",
        "/api/v1/admin/ai/release-decisions/{id}:revoke",
    ):
        path_item = paths.get(inherited_path)
        if not isinstance(path_item, dict):
            raise RuntimeError(f"inherited Admin path is missing: {inherited_path}")
        if "parameters" in path_item:
            raise RuntimeError(f"inherited Admin path parameter repair collided: {inherited_path}")
        path_item["parameters"] = [path_parameter("id")]
    tags = document.get("tags")
    if not isinstance(tags, list):
        raise RuntimeError("Admin OpenAPI tags are missing")
    for name, description in (
        ("Content", "Versioned content contracts and review authority."),
        ("Media", "Source- and license-bound media assets."),
        ("Evidence", "Human-authored first-hand experience evidence."),
    ):
        if not any(isinstance(item, dict) and item.get("name") == name for item in tags):
            tags.append({"name": name, "description": description})
    additions = {
        "/api/v1/admin/content/article-types": {
            "get": operation(
                "ED-016",
                tag="Content",
                summary="Article Typeのactive/version一覧を取得",
                response_component="ArticleTypeVersionListV1",
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/article-types/{code}/versions": {
            "get": operation(
                "ED-017",
                tag="Content",
                summary="Article Type codeのversion履歴を取得",
                response_component="ArticleTypeVersionListV1",
                path_parameters=("code",),
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/schemas": {
            "get": operation(
                "ED-018",
                tag="Content",
                summary="Content Schema version一覧を取得",
                response_component="ContentSchemaVersionListV1",
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/templates": {
            "get": operation(
                "ED-019",
                tag="Content",
                summary="Article Template version一覧を取得",
                response_component="ArticleTemplateVersionListV1",
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/templates/{id}": {
            "get": operation(
                "ED-020",
                tag="Content",
                summary="Article Template versionを取得",
                response_component="ArticleTemplateVersionV1",
                path_parameters=("id",),
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/methodologies": {
            "get": operation(
                "ED-021",
                tag="Content",
                summary="Editorial Methodology version一覧を取得",
                response_component="EditorialMethodologyVersionListV1",
                scope="content:config:read",
            )
        },
        "/api/v1/admin/content/methodologies/{id}:validate": {
            "post": operation(
                "ED-022",
                tag="Content",
                summary="Editorial Methodology artifactを検証",
                response_component="ContentValidationResultV1",
                path_parameters=("id",),
                request_component="MethodologyValidationRequestV1",
                idempotency=True,
                scope="content:config:write",
                audit_action="content_methodology_validate",
            )
        },
        "/api/v1/admin/articles/{article_id}/versions/{version_id}/seo": {
            "get": operation(
                "ED-023",
                tag="Content",
                summary="Article VersionのSEO metadata versionを取得",
                response_component="SeoMetadataVersionV1",
                path_parameters=("article_id", "version_id"),
                scope="content:article:read",
            ),
            "put": operation(
                "ED-024",
                tag="Content",
                summary="SEO metadata successor versionを作成",
                response_component="SeoMetadataVersionV1",
                path_parameters=("article_id", "version_id"),
                request_component="SeoMetadataUpdateRequestV1",
                idempotency=True,
                concurrency=True,
                scope="content:article:write",
                audit_action="content_seo_successor_create",
            ),
        },
        "/api/v1/admin/media-assets": {
            "post": operation(
                "ED-025",
                tag="Media",
                summary="Media Assetを登録",
                response_component="MediaAssetV1",
                response_status="201",
                request_component="MediaAssetCreateRequestV1",
                idempotency=True,
                scope="media:write",
                audit_action="media_asset_create",
            )
        },
        "/api/v1/admin/media-assets/{id}": {
            "get": operation(
                "ED-026",
                tag="Media",
                summary="Media Assetを取得",
                response_component="MediaAssetV1",
                path_parameters=("id",),
                scope="media:read",
            ),
            "patch": operation(
                "ED-027",
                tag="Media",
                summary="Media Asset metadata/statusを更新",
                response_component="MediaAssetV1",
                path_parameters=("id",),
                request_component="MediaAssetUpdateRequestV1",
                idempotency=True,
                concurrency=True,
                scope="media:write",
                audit_action="media_asset_update",
                human_only=True,
            ),
        },
        "/api/v1/admin/evidence/experience-records": {
            "post": operation(
                "ED-028",
                tag="Evidence",
                summary="First-Hand Experience Recordを登録",
                response_component="FirstHandExperienceRecordV1",
                response_status="201",
                request_component="FirstHandExperienceCreateRequestV1",
                idempotency=True,
                scope="evidence:experience:write",
                audit_action="experience_record_create",
                human_only=True,
            )
        },
        "/api/v1/admin/evidence/experience-records/{id}": {
            "get": operation(
                "ED-029",
                tag="Evidence",
                summary="First-Hand Experience Recordを取得",
                response_component="FirstHandExperienceRecordV1",
                path_parameters=("id",),
                scope="evidence:experience:read",
            )
        },
        "/api/v1/admin/articles/{version_id}/content-review": {
            "post": operation(
                "ED-030",
                tag="Content",
                summary="人間のContent Review Decisionを記録",
                response_component="EditorialReviewDecisionV1",
                response_status="201",
                path_parameters=("version_id",),
                request_component="ContentReviewRequestV1",
                idempotency=True,
                scope="content:review:approve",
                audit_action="content_review_decision_record",
                human_only=True,
            )
        },
    }
    add_paths(document, additions)
    used_oauth_scopes: set[str] = set()
    for path_item in document["paths"].values():
        if not isinstance(path_item, dict):
            continue
        for candidate_operation in path_item.values():
            if not isinstance(candidate_operation, dict):
                continue
            for requirement in candidate_operation.get("security", []):
                if isinstance(requirement, dict):
                    scopes = requirement.get("oidcOAuth2", [])
                    if isinstance(scopes, list):
                        used_oauth_scopes.update(
                            scope for scope in scopes if isinstance(scope, str)
                        )
    for scope in sorted(used_oauth_scopes):
        existing = declared_scopes.get(scope)
        if existing is not None and existing != scope:
            raise RuntimeError(f"Admin OAuth2 scope declaration drift: {scope}")
        declared_scopes[scope] = scope
    document["x-raos-content-revision"].update(
        {
            "admin_operation_ids": list(CONTENT_API_OPERATIONS[:15]),
            "public_surface": "NONE",
            "human_only_operation_ids": ["ED-027", "ED-028", "ED-030"],
        }
    )
    write_yaml(path, document)


def patch_internal_openapi(
    contracts_root: Path, schemas: Mapping[str, Mapping[str, Any]]
) -> None:
    path = contracts_root / "openapi-internal.v0.4.yaml"
    document = load_yaml_bytes(path.read_bytes(), source=path.as_posix())
    add_openapi_components(document, schemas)
    tags = document.get("tags")
    if isinstance(tags, list) and not any(
        isinstance(item, dict) and item.get("name") == "Content" for item in tags
    ):
        tags.append({"name": "Content", "description": "Internal deterministic content commands."})
    additions = {
        "/api/v1/internal/content/validate": {
            "post": operation(
                "INT-005",
                tag="Content",
                summary="Content ASTとArticle Type/Template policyを検証",
                response_component="ContentValidationResultV1",
                request_component="ContentValidationRequestV1",
                idempotency=True,
                internal=True,
                audit_action="content_ast_validate",
            )
        },
        "/api/v1/internal/articles/{version_id}/structured-data/render": {
            "post": operation(
                "INT-006",
                tag="Content",
                summary="Structured Dataを決定的にrender",
                response_component="StructuredDataManifestV1",
                path_parameters=("version_id",),
                request_component="StructuredDataCommandRequestV1",
                idempotency=True,
                internal=True,
                audit_action="structured_data_render",
            )
        },
        "/api/v1/internal/articles/{version_id}/structured-data/validate": {
            "post": operation(
                "INT-007",
                tag="Content",
                summary="Structured Data Manifestを検証",
                response_component="ContentValidationResultV1",
                path_parameters=("version_id",),
                request_component="StructuredDataCommandRequestV1",
                idempotency=True,
                internal=True,
                audit_action="structured_data_validate",
            )
        },
        "/api/v1/internal/articles/{version_id}/publication-content-manifest": {
            "post": operation(
                "INT-008",
                tag="Content",
                summary="Publication Content Manifest candidateを生成",
                response_component="PublicationContentManifestV1",
                response_status="201",
                path_parameters=("version_id",),
                request_component="PublicationManifestCreateRequestV1",
                idempotency=True,
                internal=True,
                audit_action="publication_content_manifest_create",
            )
        },
    }
    add_paths(document, additions)
    document["x-raos-content-revision"].update(
        {
            "internal_operation_ids": list(CONTENT_API_OPERATIONS[15:]),
            "commands_are_candidates_only": True,
            "publication_authority": "NONE",
        }
    )
    write_yaml(path, document)


def patch_non_http_contracts(contracts_root: Path) -> None:
    async_path = contracts_root / "asyncapi.v0.4.yaml"
    async_document = load_yaml_bytes(async_path.read_bytes(), source=async_path.as_posix())
    async_document["x-raos-content-revision"].update(
        {
            "event_delta": "NONE",
            "existing_channels_operations_messages_preserved": True,
            "invented_content_events": False,
        }
    )
    write_yaml(async_path, async_document)

    job_path = contracts_root / "catalogs" / "job-catalog.v0.4.yaml"
    job_document = load_yaml_bytes(job_path.read_bytes(), source=job_path.as_posix())
    job_document["content_revision"] = {
        "job_delta": "NONE",
        "commands": [
            "ValidateContentAst",
            "ValidateArticleTemplate",
            "EvaluateClaimEvidenceCoverage",
            "CalculateEditorialSuitability",
            "RenderDisclosure",
            "RenderStructuredData",
            "EvaluateFreshnessDegradation",
            "ValidateMediaAsset",
            "GenerateInternalLinkCandidates",
            "CreateContentLifecycleCandidate",
        ],
        "runtime_job_mapping": "DEFERRED_TO_IMPLEMENTATION_STORIES",
    }
    write_yaml(job_path, job_document)

    state_path = contracts_root / "catalogs" / "state-transition-catalog.v0.4.yaml"
    state_document = load_yaml_bytes(state_path.read_bytes(), source=state_path.as_posix())
    state_document["content_revision"] = {
        "state_machine_delta": "NONE",
        "version_resource_mutation": "APPEND_ONLY_SUCCESSOR",
        "human_approval_authority": True,
        "ai_approval_or_publication": "FORBIDDEN",
    }
    write_yaml(state_path, state_document)


def enrich_contracts(
    contracts_root: Path, payloads: Mapping[str, bytes]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    frozen = install_frozen_content(contracts_root, payloads)
    write_yaml(
        contracts_root / "content" / "canonical-adoption.v0.4.yaml",
        build_content_adoption(contracts_root),
    )
    write_yaml(
        contracts_root / "content" / "ai-content-alignment.v0.4.yaml",
        build_ai_alignment(payloads),
    )
    schemas = generate_type_schemas(contracts_root)
    patch_resource_catalog(contracts_root, schemas)
    patch_schema_registry(contracts_root)
    patch_admin_openapi(contracts_root, schemas)
    patch_internal_openapi(contracts_root, schemas)
    patch_non_http_contracts(contracts_root)
    return schemas, frozen


def artifact_entry(path: Path, logical_path: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {"path": logical_path, "bytes": len(content), "sha256": sha256_bytes(content)}


def source_artifacts() -> list[dict[str, Any]]:
    paths = [
        REPO_ROOT / "scripts" / "build_st0004_revision.py",
        DEFAULT_BUNDLE_ROOT / "README.md",
        *(DATABASE_ROOT / name for name in MIGRATION_PHASES),
        DATABASE_ROOT / GUARDED_DOWNGRADE,
        DATABASE_ROOT / FORWARD_RECOVERY,
    ]
    for path in paths:
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required ST-0004 source artifact is missing: {path}")
    expected_database = {path.resolve() for path in paths[2:]}
    actual_database = {
        path.resolve() for path in DATABASE_ROOT.rglob("*") if path.is_file()
    }
    if expected_database != actual_database:
        raise RuntimeError(
            "ST-0004 database source set differs from formal checkpoints: "
            f"unexpected={sorted(str(path) for path in actual_database - expected_database)}, "
            f"missing={sorted(str(path) for path in expected_database - actual_database)}"
        )
    return [artifact_entry(path, relative_repo_path(path)) for path in paths]


def generated_artifacts(staged_root: Path) -> list[dict[str, Any]]:
    paths = [staged_root / "job-state.v1.yaml"]
    paths.extend(
        sorted(path for path in (staged_root / "contracts").rglob("*") if path.is_file())
    )
    return [
        artifact_entry(
            path,
            f"changes/st-0004/{path.relative_to(staged_root).as_posix()}",
        )
        for path in paths
    ]


def event_surface_hash(path: Path) -> str:
    document = load_yaml_bytes(path.read_bytes(), source=path.as_posix())
    surface = {
        "channels": document.get("channels"),
        "operations": document.get("operations"),
        "messages": document.get("components", {}).get("messages"),
    }
    return sha256_bytes(
        json.dumps(surface, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )


def assert_async_surface_preserved(staged_root: Path) -> str:
    predecessor_async = PREDECESSOR_ROOT / "contracts" / "asyncapi.v0.3.yaml"
    successor_async = staged_root / "contracts" / "asyncapi.v0.4.yaml"
    predecessor_hash = event_surface_hash(predecessor_async)
    successor_hash = event_surface_hash(successor_async)
    if predecessor_hash != successor_hash:
        raise RuntimeError("ST-0004 must not change the AsyncAPI event surface")
    predecessor_events = PREDECESSOR_ROOT / "contracts" / "schemas" / "events"
    successor_events = staged_root / "contracts" / "schemas" / "events"
    predecessor_files = {
        path.relative_to(predecessor_events).as_posix(): path.read_bytes()
        for path in predecessor_events.rglob("*")
        if path.is_file()
    }
    successor_files = {
        path.relative_to(successor_events).as_posix(): path.read_bytes()
        for path in successor_events.rglob("*")
        if path.is_file()
    }
    if predecessor_files != successor_files:
        raise RuntimeError("ST-0004 must preserve every predecessor event schema byte")
    return predecessor_hash


def build_manifest(
    staged_root: Path,
    schemas: Mapping[str, Mapping[str, Any]],
    frozen: list[dict[str, Any]],
    predecessor_manifest: Mapping[str, Any],
    preserved_event_surface_hash: str,
) -> dict[str, Any]:
    generated = generated_artifacts(staged_root)
    content_root = staged_root / "contracts" / "content"
    valid_count = len(list((content_root / "fixtures" / "valid").glob("*.json")))
    invalid_count = len(list((content_root / "fixtures" / "invalid").glob("INV-*.json")))
    database_execution_security = predecessor_manifest.get(
        "database_execution_security"
    )
    if not isinstance(database_execution_security, dict):
        raise RuntimeError("ST-0003 database execution-security metadata is missing")
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0004",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": "scripts/build_st0004_revision.py",
        },
        "provenance": {
            "requirement_ids": ["FR-007", "FR-010"],
            "decision_ids": ["INT-DEC-005"],
            "supporting_decision_ids": ["INT-DEC-006"],
            "predecessor": {
                "id": PREDECESSOR_ID,
                "version": "0.3",
                "manifest_path": "changes/st-0003/manifest.yaml",
                "manifest_sha256": PREDECESSOR_MANIFEST_HASH,
                "job_state_sha256": JOB_STATE_HASH,
                "complete_artifact_verification": True,
            },
            "proposal_execution": "FORBIDDEN",
            "proposal_retained": True,
        },
        "inputs": [
            {"path": path, "sha256": digest}
            for path, digest in EXPECTED_INPUT_HASHES.items()
        ],
        "archive_validation": {
            "regular_member_count": 111,
            "declared_checksum_count": 110,
            "declared_equals_regular_members_excluding_inventory": True,
            "all_member_hashes_verified": True,
            "standalone_proposals_equal_both_archive_copies": True,
            "path_casefold_traversal_symlink_checks": True,
        },
        "compatibility": {
            "classification": "ADDITIVE_PRE_RELEASE_CANONICAL_REVISION",
            "http_path_major": 1,
            "job_message_major": 1,
            "existing_schema_paths_preserved": True,
            "existing_operations_removed_or_semantically_changed": False,
            "public_openapi_sha256": PUBLIC_OPENAPI_HASH,
            "public_openapi_byte_identical": True,
            "public_content_evidence_finance_surface": "NONE",
            "async_event_delta": "NONE",
            "async_event_surface_sha256": preserved_event_surface_hash,
            "async_event_surface_hash_preserved": True,
            "ai_execution_security_metadata_preserved": True,
        },
        "content_adoption": {
            "frozen_artifact_count": len(frozen),
            "frozen_artifacts": frozen,
            "article_type_count": 5,
            "block_type_count": 24,
            "frozen_schema_count": 33,
            "generated_resource_and_request_schema_count": len(schemas),
            "valid_fixture_count": valid_count,
            "invalid_fixture_count": invalid_count,
            "template_count": 5,
            "stored_ast_disclosure_slot_first": True,
            "cms_authority": "PUBLICATION_ADAPTER_ONLY",
            "auto_publish": "FORBIDDEN",
        },
        "contract_delta": {
            "admin_operation_ids": list(CONTENT_API_OPERATIONS[:15]),
            "internal_operation_ids": list(CONTENT_API_OPERATIONS[15:]),
            "operation_count": len(CONTENT_API_OPERATIONS),
            "api_resource_count": 10,
            "database_table_count": 11,
            "article_version_binding_count": 4,
            "command_count": 10,
            "affected_ai_task_count": 8,
            "event_types_added": [],
        },
        "postgresql": {
            "minimum_server_version_num": 180000,
            "design_target": "18.4",
            "predecessor": "RAOS-DATA-001@0.1 plus ST-0002 plus ST-0003",
            "phase_order": list(MIGRATION_PHASES),
            "repeatable_phase": {
                "file": "202607300015_content_migrate_batch.sql",
                "completion_signal": "automatic_remaining_rows=0",
            },
            "guarded_downgrade": GUARDED_DOWNGRADE,
            "forward_recovery": FORWARD_RECOVERY,
        },
        "handoff": {
            "ST-0104": "install contracts from this hash-pinned bundle",
            "ST-0105": "generate Python and TypeScript types/clients",
            "ST-0301": "bind SQL checkpoints to migration runner/history/lock ABI",
            "ST-0306": "complete production role grants and public isolation",
            "ST-0705": "consume content AI alignment in output validators",
            "ST-0801": "implement runtime AST/policy validator using frozen fixtures",
            "ST-0903": "implement CMS adapter with explicit human publish approval",
        },
        "database_execution_security": database_execution_security,
        "source_artifacts": source_artifacts(),
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
    }


def assert_owned_generated_destination(bundle_root: Path) -> None:
    if bundle_root.is_symlink() or (bundle_root.exists() and not bundle_root.is_dir()):
        raise RuntimeError(f"refusing unsafe bundle root: {bundle_root}")
    contracts = bundle_root / "contracts"
    manifest = bundle_root / "manifest.yaml"
    job_state = bundle_root / "job-state.v1.yaml"
    if contracts.is_symlink() or manifest.is_symlink() or job_state.is_symlink():
        raise RuntimeError(f"refusing symlinked generated destination: {bundle_root}")
    exists = (contracts.exists(), manifest.exists(), job_state.exists())
    if any(exists) and not all(exists):
        raise RuntimeError(
            "partial generated destination: contracts, manifest, and job-state must exist together"
        )
    if not any(exists):
        return
    if not contracts.is_dir() or not manifest.is_file() or not job_state.is_file():
        raise RuntimeError(f"refusing malformed generated destination: {bundle_root}")
    manifest_document = load_yaml_bytes(manifest.read_bytes(), source=manifest.as_posix())
    document = manifest_document.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != REVISION_ID
        or document.get("generated_by") != "scripts/build_st0004_revision.py"
    ):
        raise RuntimeError(f"destination is not owned by {REVISION_ID}")
    entries = manifest_document.get("generated_artifacts")
    if not isinstance(entries, list) or manifest_document.get("generated_artifact_count") != len(entries):
        raise RuntimeError("owned destination manifest artifact inventory is malformed")
    listed: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("owned destination has malformed artifact entry")
        logical = entry["path"]
        prefix = "changes/st-0004/"
        if not logical.startswith(prefix):
            raise RuntimeError(f"owned artifact escapes bundle: {logical}")
        relative = logical.removeprefix(prefix)
        if relative != "job-state.v1.yaml" and not relative.startswith("contracts/"):
            raise RuntimeError(f"unexpected owned artifact path: {logical}")
        if relative.casefold() in {item.casefold() for item in listed}:
            raise RuntimeError(f"casefold duplicate owned artifact: {logical}")
        listed[relative] = entry
    actual: dict[str, Path] = {"job-state.v1.yaml": job_state}
    for directory, directory_names, filenames in os.walk(contracts, followlinks=False):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                raise RuntimeError(f"unowned symlink in generated tree: {child}")
        for name in filenames:
            child = directory_path / name
            if child.is_symlink() or not child.is_file():
                raise RuntimeError(f"unowned special file in generated tree: {child}")
            actual[child.relative_to(bundle_root).as_posix()] = child
    if set(listed) != set(actual):
        raise RuntimeError(
            "unowned or missing generated files: "
            f"unexpected={sorted(set(actual) - set(listed))}, "
            f"missing={sorted(set(listed) - set(actual))}"
        )
    for relative, path in actual.items():
        entry = listed[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get("sha256") != sha256_file(path):
            raise RuntimeError(f"owned generated artifact hash drift: {relative}")


def install_staged_generation(staged_root: Path, bundle_root: Path) -> None:
    names = ("contracts", "job-state.v1.yaml", "manifest.yaml")
    backups = {
        name: staged_root.parent / f"previous-{name.replace('/', '-')}" for name in names
    }
    moved_old: list[str] = []
    installed_new: list[str] = []
    had_previous = (bundle_root / "manifest.yaml").exists()
    try:
        if had_previous:
            for name in names:
                os.replace(bundle_root / name, backups[name])
                moved_old.append(name)
        for name in names:
            os.replace(staged_root / name, bundle_root / name)
            installed_new.append(name)
    except OSError:
        for name in reversed(installed_new):
            target = bundle_root / name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        for name in reversed(moved_old):
            os.replace(backups[name], bundle_root / name)
        raise


def build(bundle_root: Path) -> None:
    """Render completely in sibling staging, then atomically replace ownership."""

    assert_immutable_inputs()
    predecessor_manifest = verify_predecessor()
    assert_owned_generated_destination(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    payloads = verify_content_archive()
    with tempfile.TemporaryDirectory(
        prefix=".raos-st0004-build-", dir=bundle_root.parent
    ) as temporary:
        staged_root = Path(temporary) / "generated"
        staged_root.mkdir()
        contracts_root = staged_root / "contracts"
        promote_predecessor_contracts(contracts_root)
        schemas, frozen = enrich_contracts(contracts_root, payloads)
        preserved_event_surface_hash = assert_async_surface_preserved(staged_root)
        (staged_root / "job-state.v1.yaml").write_bytes(
            PREDECESSOR_JOB_STATE.read_bytes()
        )
        write_yaml(
            staged_root / "manifest.yaml",
            build_manifest(
                staged_root,
                schemas,
                frozen,
                predecessor_manifest,
                preserved_event_surface_hash,
            ),
        )
        install_staged_generation(staged_root, bundle_root)


def generated_file_map(bundle_root: Path) -> dict[str, bytes]:
    paths = [bundle_root / "manifest.yaml", bundle_root / "job-state.v1.yaml"]
    contracts = bundle_root / "contracts"
    if contracts.is_dir():
        paths.extend(sorted(path for path in contracts.rglob("*") if path.is_file()))
    return {
        path.relative_to(bundle_root).as_posix(): path.read_bytes()
        for path in paths
        if path.is_file()
    }


def check_generated() -> None:
    assert_owned_generated_destination(DEFAULT_BUNDLE_ROOT)
    with tempfile.TemporaryDirectory(prefix="raos-st0004-check-") as temporary:
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
        help="owned output; CLI accepts only changes/st-0004",
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
            result = {"status": "PASS", "story_id": "ST-0004", "mode": "check"}
        else:
            output = args.output.resolve()
            if output != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError(
                    "--output must be the owned canonical changes/st-0004 bundle"
                )
            build(output)
            result = {
                "status": "PASS",
                "story_id": "ST-0004",
                "mode": "build",
                "output": str(output),
            }
    except (
        BadZipFile,
        OSError,
        RuntimeError,
        UnicodeError,
        ValueError,
        yaml.YAMLError,
    ) as exc:
        print(
            json.dumps(
                {"status": "ERROR", "story_id": "ST-0004", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
