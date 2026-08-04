#!/usr/bin/env python3
"""Build the ST-0003 AI-governance revision from verified immutable inputs."""

from __future__ import annotations

import argparse
import copy
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
from zipfile import ZipFile, ZipInfo

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BUNDLE_ROOT = REPO_ROOT / "changes" / "st-0003"
PREDECESSOR_ROOT = REPO_ROOT / "changes" / "st-0002"
PREDECESSOR_MANIFEST = PREDECESSOR_ROOT / "manifest.yaml"
PREDECESSOR_JOB_STATE = PREDECESSOR_ROOT / "job-state.v1.yaml"
DATABASE_ROOT = DEFAULT_BUNDLE_ROOT / "database"

DATA_PACKAGE = REPO_ROOT / "docs" / "upstream" / "RAOS_03_data_model_package_v0.1.zip"
API_PACKAGE = REPO_ROOT / "docs" / "upstream" / "RAOS_04_api_contract_package_v0.1.zip"
AI_PACKAGE = REPO_ROOT / "docs" / "upstream" / "RAOS_05_ai_design_package_v0.1.zip"
AI_DATA_PROPOSAL = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_05_001_ai_data_alignment_patch_v0.1.sql"
)
AI_API_PROPOSAL = (
    REPO_ROOT
    / "docs"
    / "upstream"
    / "patches"
    / "RAOS_05_002_api_alignment_patch_v0.1.yaml"
)

API_ROOT = "RAOS_04_api_contract_package_v0.1/"
AI_ROOT = "RAOS_05_ai_design_package_v0.1/"
PUBLIC_OPENAPI_MEMBER = f"{API_ROOT}RAOS_04_openapi_public_v0.1.yaml"
AI_CHECKSUM_MEMBER = f"{AI_ROOT}SHA256SUMS.txt"
AI_EVALUATION_CATALOG_MEMBER = (
    f"{AI_ROOT}RAOS_05_evaluation_catalog_v0.1.yaml"
)
REVISION_VERSION = "0.3"
REVISION_ID = "RAOS-AI-GOVERNANCE-REVISION-001"
PREDECESSOR_ID = "RAOS-JOB-STATE-REVISION-001"
PREDECESSOR_MANIFEST_HASH = (
    "ec687f51795c4f97d4e4b08db38ce4bec7c94da0e337c7e9a1bff2a9b2cb0f1e"
)
JOB_STATE_HASH = (
    "9f6d39a784cb00d6ec5159fe45eddaf92d661a939b63cbcad6f33c899faab87a"
)
PUBLIC_OPENAPI_HASH = (
    "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797"
)

EXPECTED_INPUT_HASHES = {
    "docs/upstream/RAOS_03_data_model_package_v0.1.zip": (
        "82597db880c80c632ac0337d583c91ba5defac827414ecee1b921f49d1f64357"
    ),
    "docs/upstream/RAOS_04_api_contract_package_v0.1.zip": (
        "fb55cc00adabd20591c3da06d2399b3692b3393d3f27d28943e870e8b253ca1f"
    ),
    "docs/upstream/RAOS_05_ai_design_package_v0.1.zip": (
        "9b32509c9dd6d9001aaad1b6d7663c40bc671f0ce0056d6d3539e8b318c60bfd"
    ),
    "docs/upstream/patches/RAOS_05_001_ai_data_alignment_patch_v0.1.sql": (
        "a05b1cdb7ecc1a9e1eee7307c85eafc64702ac0fc0b1456dea3721a5be09d3fe"
    ),
    "docs/upstream/patches/RAOS_05_002_api_alignment_patch_v0.1.yaml": (
        "3af33d69df7bbd31a415e8674cdde9b60e9edfc2721b2e7aa6b53278704ec2f0"
    ),
}

FROZEN_AI_YAML = (
    "RAOS_05_ai_task_catalog_v0.1.yaml",
    "RAOS_05_eval_dataset_manifest_template_v0.1.yaml",
    "RAOS_05_evaluation_catalog_v0.1.yaml",
    "RAOS_05_failure_taxonomy_v0.1.yaml",
    "RAOS_05_human_review_rubric_v0.1.yaml",
    "RAOS_05_model_routing_catalog_v0.1.yaml",
    "RAOS_05_observability_catalog_v0.1.yaml",
    "RAOS_05_official_reference_catalog_v0.1.yaml",
    "RAOS_05_prompt_registry_v0.1.yaml",
    "RAOS_05_quality_gate_catalog_v0.1.yaml",
    "RAOS_05_release_decision_template_v0.1.yaml",
    "RAOS_05_runtime_config_template_v0.1.yaml",
    "RAOS_05_schema_registry_v0.1.yaml",
    "RAOS_05_state_transition_catalog_v0.1.yaml",
)
GRADER_OUTPUT_METRIC_EXTENSIONS: dict[
    str, tuple[tuple[str, str, str], ...]
] = {
    "grader.resource_reference.v1": (
        (
            "critical_claim_support_rate",
            "DETERMINISTIC_HUMAN",
            "RESOURCE_SUPPORT",
        ),
    ),
    "grader.numeric_exactness.v1": (
        (
            "priority_order_preservation",
            "DETERMINISTIC",
            "PRIORITY",
        ),
    ),
    "grader.task_gold.v1": (
        (
            "uncertainty_calibration_error",
            "STATISTICAL",
            "CALIBRATION",
        ),
        (
            "finding_resolution_rate",
            "DETERMINISTIC_HUMAN",
            "REMEDIATION",
        ),
        (
            "new_unsupported_claim_rate",
            "DETERMINISTIC_HUMAN",
            "REMEDIATION",
        ),
        (
            "priority_order_preservation",
            "DETERMINISTIC",
            "PRIORITY",
        ),
    ),
    "grader.human_rubric.v1": (
        (
            "critical_claim_support_rate",
            "DETERMINISTIC_HUMAN",
            "HYBRID_HUMAN",
        ),
        (
            "unsupported_critical_fact_rate",
            "HUMAN_JUDGE",
            "HYBRID_HUMAN",
        ),
        (
            "false_clearance_rate",
            "HUMAN",
            "HUMAN",
        ),
        (
            "finding_resolution_rate",
            "DETERMINISTIC_HUMAN",
            "HYBRID_HUMAN",
        ),
        (
            "new_unsupported_claim_rate",
            "DETERMINISTIC_HUMAN",
            "HYBRID_HUMAN",
        ),
        (
            "human_edit_distance",
            "DETERMINISTIC",
            "HUMAN",
        ),
    ),
}
PROMPT_PREFIX = "prompts/"
SCHEMA_PREFIX = "schemas/"
ROOT_REVISION_FILES = {
    "openapi-admin.v0.2.yaml": "openapi-admin.v0.3.yaml",
    "openapi-internal.v0.2.yaml": "openapi-internal.v0.3.yaml",
    "asyncapi.v0.2.yaml": "asyncapi.v0.3.yaml",
    "catalogs/job-catalog.v0.2.yaml": "catalogs/job-catalog.v0.3.yaml",
    "catalogs/resource-contracts.v0.2.yaml": (
        "catalogs/resource-contracts.v0.3.yaml"
    ),
    "catalogs/schema-registry.v0.2.yaml": "catalogs/schema-registry.v0.3.yaml",
    "catalogs/state-transition-catalog.v0.2.yaml": (
        "catalogs/state-transition-catalog.v0.3.yaml"
    ),
}
MIGRATION_PHASES = (
    "202607300007_ai_governance_expand.sql",
    "202607300008_ai_governance_expand_validate.sql",
    "202607300009_ai_governance_migrate_batch.sql",
    "202607300010_ai_governance_contract_prepare.sql",
    "202607300011_ai_governance_contract.sql",
)
GUARDED_DOWNGRADE = "202607300012_ai_governance_guarded_downgrade.sql"
FORWARD_RECOVERY = "forward-recovery.md"


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def relative_repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def load_yaml_bytes(content: bytes, *, source: str) -> dict[str, Any]:
    document = yaml.safe_load(content)
    if not isinstance(document, dict):
        raise RuntimeError(f"expected YAML mapping in {source}")
    return document


def write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = yaml.safe_dump(
        dict(document),
        allow_unicode=True,
        sort_keys=False,
        width=1000,
    )
    path.write_text(rendered, encoding="utf-8", newline="\n")


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    path.write_text(rendered, encoding="utf-8", newline="\n")


def checked_relative_path(value: str, *, source: str) -> PurePosixPath:
    raw_parts = value.split("/")
    if (
        not value
        or value.startswith("/")
        or "\\" in value
        or "\x00" in value
        or any(part in {"", ".", ".."} for part in raw_parts)
    ):
        raise RuntimeError(f"unsafe path in {source}: {value!r}")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise RuntimeError(f"unsafe path in {source}: {value!r}")
    return path


def zip_info_is_symlink(info: ZipInfo) -> bool:
    return stat.S_IFMT(info.external_attr >> 16) == stat.S_IFLNK


def checked_archive_files(
    archive: ZipFile,
    *,
    root: str,
    source: str,
) -> dict[str, ZipInfo]:
    files: dict[str, ZipInfo] = {}
    seen_archive: set[str] = set()
    seen_relative: set[str] = set()
    for info in archive.infolist():
        checked_relative_path(info.filename.rstrip("/"), source=source)
        archive_folded = info.filename.casefold()
        if archive_folded in seen_archive:
            raise RuntimeError(
                f"duplicate/casefold archive member in {source}: {info.filename}"
            )
        seen_archive.add(archive_folded)
        if not info.filename.startswith(root):
            raise RuntimeError(
                f"archive member escapes expected root in {source}: {info.filename}"
            )
        relative = info.filename[len(root) :]
        if not relative:
            if not info.is_dir():
                raise RuntimeError(f"unexpected root file in {source}")
            continue
        checked_relative_path(relative.rstrip("/"), source=source)
        if zip_info_is_symlink(info):
            raise RuntimeError(f"symlink archive member in {source}: {info.filename}")
        if info.is_dir():
            continue
        folded = relative.casefold()
        if folded in seen_relative:
            raise RuntimeError(
                f"duplicate/casefold relative member in {source}: {relative}"
            )
        seen_relative.add(folded)
        files[relative] = info
    return files


def verify_ai_archive() -> dict[str, str]:
    with ZipFile(AI_PACKAGE) as archive:
        files = checked_archive_files(
            archive,
            root=AI_ROOT,
            source=relative_repo_path(AI_PACKAGE),
        )
        checksum_info = files.get("SHA256SUMS.txt")
        if checksum_info is None:
            raise RuntimeError("AI package checksum inventory is missing")
        declared: dict[str, str] = {}
        seen_folded: set[str] = set()
        checksum_text = archive.read(checksum_info).decode("utf-8")
        for line_number, line in enumerate(checksum_text.splitlines(), 1):
            parts = line.split("  ", 1)
            if len(parts) != 2 or len(parts[0]) != 64:
                raise RuntimeError(
                    f"malformed AI checksum line {line_number}: {line!r}"
                )
            digest, relative = parts
            if any(character not in "0123456789abcdef" for character in digest):
                raise RuntimeError(
                    f"malformed AI checksum digest at line {line_number}"
                )
            checked_relative_path(relative, source="AI SHA256SUMS.txt")
            folded = relative.casefold()
            if folded in seen_folded:
                raise RuntimeError(
                    f"duplicate/casefold AI checksum path: {relative}"
                )
            seen_folded.add(folded)
            declared[relative] = digest
        if len(declared) != 97:
            raise RuntimeError(
                f"expected 97 AI checksum declarations, found {len(declared)}"
            )
        actual_names = set(files) - {"SHA256SUMS.txt"}
        if set(declared) != actual_names:
            raise RuntimeError(
                "AI checksum inventory differs from regular archive members: "
                f"missing={sorted(actual_names - set(declared))}, "
                f"unexpected={sorted(set(declared) - actual_names)}"
            )
        for relative, expected_hash in declared.items():
            actual_hash = sha256_bytes(archive.read(files[relative]))
            if actual_hash != expected_hash:
                raise RuntimeError(
                    f"AI archive member hash mismatch for {relative}: "
                    f"expected {expected_hash}, got {actual_hash}"
                )
        proposal_pairs = (
            (
                "proposals/RAOS_05_001_ai_data_alignment_patch_v0.1.sql",
                AI_DATA_PROPOSAL,
            ),
            (
                "proposals/RAOS_05_002_api_alignment_patch_v0.1.yaml",
                AI_API_PROPOSAL,
            ),
        )
        for member, external in proposal_pairs:
            if archive.read(files[member]) != external.read_bytes():
                raise RuntimeError(
                    f"external proposal differs from AI package member: {member}"
                )
    return declared


def assert_immutable_inputs() -> None:
    for relative_path, expected_hash in EXPECTED_INPUT_HASHES.items():
        path = REPO_ROOT / relative_path
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"required immutable input is missing: {relative_path}")
        actual_hash = sha256_file(path)
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"immutable input hash mismatch for {relative_path}: "
                f"expected {expected_hash}, got {actual_hash}"
            )
    verify_ai_archive()
    with ZipFile(API_PACKAGE) as archive:
        files = checked_archive_files(
            archive,
            root=API_ROOT,
            source=relative_repo_path(API_PACKAGE),
        )
        member = PUBLIC_OPENAPI_MEMBER[len(API_ROOT) :]
        if member not in files:
            raise RuntimeError(f"public OpenAPI member is missing: {member}")
        actual_hash = sha256_bytes(archive.read(files[member]))
        if actual_hash != PUBLIC_OPENAPI_HASH:
            raise RuntimeError(
                "public OpenAPI archive-member hash mismatch: "
                f"expected {PUBLIC_OPENAPI_HASH}, got {actual_hash}"
            )


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
    relative = checked_relative_path(raw_path, source="ST-0002 manifest")
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
        PREDECESSOR_MANIFEST.read_bytes(),
        source=relative_repo_path(PREDECESSOR_MANIFEST),
    )
    document = manifest.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != PREDECESSOR_ID
        or document.get("version") != "0.2"
        or document.get("generated_by") != "scripts/build_st0002_revision.py"
    ):
        raise RuntimeError("unexpected ST-0002 manifest ownership/version")
    generated = manifest.get("generated_artifacts")
    source_artifacts = manifest.get("source_artifacts")
    if not isinstance(generated, list) or not isinstance(source_artifacts, list):
        raise RuntimeError("ST-0002 manifest artifact lists are missing")
    if manifest.get("generated_artifact_count") != len(generated):
        raise RuntimeError("ST-0002 generated artifact count is inconsistent")
    seen: set[str] = set()
    for entry in generated:
        if not isinstance(entry, dict):
            raise RuntimeError("malformed ST-0002 generated artifact entry")
        verify_manifest_artifact(
            entry,
            seen=seen,
            expected_prefix="changes/st-0002/contracts/",
        )
    for entry in source_artifacts:
        if not isinstance(entry, dict):
            raise RuntimeError("malformed ST-0002 source artifact entry")
        verify_manifest_artifact(entry, seen=seen, expected_prefix=None)
    if (
        not PREDECESSOR_JOB_STATE.is_file()
        or PREDECESSOR_JOB_STATE.is_symlink()
        or sha256_file(PREDECESSOR_JOB_STATE) != JOB_STATE_HASH
    ):
        raise RuntimeError("ST-0002 Job-state contract does not match pinned hash")
    contract_files = {
        path.relative_to(PREDECESSOR_ROOT / "contracts").as_posix()
        for path in (PREDECESSOR_ROOT / "contracts").rglob("*")
        if path.is_file()
    }
    listed_files = {
        entry["path"].removeprefix("changes/st-0002/contracts/")
        for entry in generated
    }
    if contract_files != listed_files:
        raise RuntimeError("ST-0002 manifest does not own the complete contract tree")
    return manifest


def mark_revision(document: MutableMapping[str, Any]) -> None:
    metadata = document.get("document")
    if isinstance(metadata, dict):
        metadata["version"] = REVISION_VERSION
        metadata["status"] = "CANONICAL_REVISION_CANDIDATE"
        metadata["provenance"] = {
            "story_id": "ST-0003",
            "decision_id": "INT-DEC-004",
            "revision_id": REVISION_ID,
            "predecessor": f"{PREDECESSOR_ID}@0.2",
            "predecessor_manifest_sha256": PREDECESSOR_MANIFEST_HASH,
        }
        return
    info = document.get("info")
    if isinstance(info, dict):
        info["version"] = REVISION_VERSION
        info["x-raos-status"] = "CANONICAL_REVISION_CANDIDATE"
        info["x-raos-revision-id"] = REVISION_ID
        info["x-raos-story-id"] = "ST-0003"
        info["x-raos-decision-id"] = "INT-DEC-004"
        info["x-raos-base-version"] = "0.1"
        info["x-raos-predecessor-version"] = "0.2"
        info["x-raos-predecessor-manifest-sha256"] = PREDECESSOR_MANIFEST_HASH
        return
    raise RuntimeError("revisioned YAML has neither document nor info metadata")


def copy_predecessor_contracts(contracts_root: Path) -> None:
    source_root = PREDECESSOR_ROOT / "contracts"
    seen: set[str] = set()
    for source in sorted(path for path in source_root.rglob("*") if path.is_file()):
        relative = source.relative_to(source_root)
        relative_text = relative.as_posix()
        checked_relative_path(relative_text, source="ST-0002 contract tree")
        folded = relative_text.casefold()
        if folded in seen:
            raise RuntimeError(
                f"duplicate/casefold predecessor contract: {relative_text}"
            )
        seen.add(folded)
        destination = contracts_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def promote_revision_files(contracts_root: Path) -> None:
    for old_name, new_name in ROOT_REVISION_FILES.items():
        old_path = contracts_root / old_name
        if not old_path.is_file():
            raise RuntimeError(f"predecessor revision file is missing: {old_name}")
        document = load_yaml_bytes(old_path.read_bytes(), source=old_name)
        mark_revision(document)
        new_path = contracts_root / new_name
        write_yaml(new_path, document)
        old_path.unlink()


def copy_frozen_ai_artifacts(
    contracts_root: Path,
    checksum_inventory: Mapping[str, str],
) -> dict[str, list[dict[str, Any]]]:
    ai_root = contracts_root / "ai"
    result: dict[str, list[dict[str, Any]]] = {
        "catalogs_and_templates": [],
        "prompts": [],
        "schemas": [],
    }
    with ZipFile(AI_PACKAGE) as archive:
        files = checked_archive_files(
            archive,
            root=AI_ROOT,
            source=relative_repo_path(AI_PACKAGE),
        )
        selected: list[tuple[str, str]] = [
            *(("catalogs_and_templates", name) for name in FROZEN_AI_YAML),
            *(
                ("prompts", name)
                for name in sorted(files)
                if name.startswith(PROMPT_PREFIX)
            ),
            *(
                ("schemas", name)
                for name in sorted(files)
                if name.startswith(SCHEMA_PREFIX)
            ),
        ]
        if sum(kind == "prompts" for kind, _ in selected) != 12:
            raise RuntimeError("expected exactly 12 frozen AI prompt templates")
        if sum(kind == "schemas" for kind, _ in selected) != 14:
            raise RuntimeError("expected exactly 14 frozen AI schemas")
        seen: set[str] = set()
        for kind, relative in selected:
            if relative not in files or relative not in checksum_inventory:
                raise RuntimeError(f"selected AI artifact is missing: {relative}")
            folded = relative.casefold()
            if folded in seen:
                raise RuntimeError(f"duplicate selected AI artifact: {relative}")
            seen.add(folded)
            content = archive.read(files[relative])
            digest = sha256_bytes(content)
            if digest != checksum_inventory[relative]:
                raise RuntimeError(f"selected AI artifact hash mismatch: {relative}")
            destination = ai_root.joinpath(*PurePosixPath(relative).parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            result[kind].append(
                {"path": relative, "bytes": len(content), "sha256": digest}
            )
    return result


def copy_frozen_public_openapi(contracts_root: Path) -> None:
    with ZipFile(API_PACKAGE) as archive:
        content = archive.read(PUBLIC_OPENAPI_MEMBER)
    if sha256_bytes(content) != PUBLIC_OPENAPI_HASH:
        raise RuntimeError("public OpenAPI changed after immutable-input verification")
    (contracts_root / "openapi-public.v0.1.yaml").write_bytes(content)


def build_grader_output_metric_bindings() -> dict[str, Any]:
    """Overlay the frozen grader ABI with its explicit metric-kind extensions."""

    with ZipFile(AI_PACKAGE) as archive:
        catalog = load_yaml_bytes(
            archive.read(AI_EVALUATION_CATALOG_MEMBER),
            source=AI_EVALUATION_CATALOG_MEMBER,
        )
    metrics = catalog.get("metrics")
    graders = catalog.get("graders")
    if not isinstance(metrics, list) or not isinstance(graders, list):
        raise RuntimeError("frozen evaluation metric/grader catalog is malformed")

    metric_kinds: dict[str, str] = {}
    for metric in metrics:
        if not isinstance(metric, dict):
            raise RuntimeError("frozen evaluation metric entry is malformed")
        metric_code = metric.get("code")
        metric_kind = metric.get("kind")
        if not isinstance(metric_code, str) or not isinstance(metric_kind, str):
            raise RuntimeError("frozen evaluation metric identity is malformed")
        if metric_code in metric_kinds:
            raise RuntimeError(f"duplicate frozen evaluation metric: {metric_code}")
        metric_kinds[metric_code] = metric_kind

    expected_grader_codes = (
        "grader.json_schema.v1",
        "grader.response_completion.v1",
        "grader.resource_reference.v1",
        "grader.numeric_exactness.v1",
        "grader.product_identity.v1",
        "grader.forbidden_content.v1",
        "grader.task_gold.v1",
        "grader.human_rubric.v1",
        "grader.model_judge.v1",
        "grader.cost_latency.v1",
    )
    bindings: dict[str, Any] = {}
    for grader in graders:
        if not isinstance(grader, dict):
            raise RuntimeError("frozen evaluation grader entry is malformed")
        grader_code = grader.get("code")
        output_metrics = grader.get("output_metrics")
        if not isinstance(grader_code, str) or not isinstance(output_metrics, list):
            raise RuntimeError("frozen evaluation grader binding is malformed")
        if grader_code in bindings:
            raise RuntimeError(f"duplicate frozen evaluation grader: {grader_code}")
        if (
            not output_metrics
            or not all(isinstance(metric, str) for metric in output_metrics)
            or len(set(output_metrics)) != len(output_metrics)
        ):
            raise RuntimeError(
                f"frozen grader output metric list is malformed: {grader_code}"
            )
        unknown_upstream = [
            metric for metric in output_metrics if metric not in metric_kinds
        ]
        if unknown_upstream:
            raise RuntimeError(
                f"frozen grader references unknown metrics: {grader_code}"
            )

        extension_entries: list[dict[str, str]] = []
        extension_metrics: list[str] = []
        for metric_code, declared_kind, extension_family in (
            GRADER_OUTPUT_METRIC_EXTENSIONS.get(grader_code, ())
        ):
            actual_kind = metric_kinds.get(metric_code)
            if actual_kind != declared_kind:
                raise RuntimeError(
                    "grader metric-kind extension does not match the frozen "
                    f"metric catalog: {grader_code}/{metric_code}"
                )
            if metric_code in output_metrics or metric_code in extension_metrics:
                raise RuntimeError(
                    f"duplicate grader metric extension: {grader_code}/{metric_code}"
                )
            extension_metrics.append(metric_code)
            extension_entries.append(
                {
                    "metric_code": metric_code,
                    "metric_kind": declared_kind,
                    "extension_family": extension_family,
                }
            )
        bindings[grader_code] = {
            "upstream_output_metrics": list(output_metrics),
            "metric_kind_extensions": extension_entries,
            "canonical_output_metrics": [*output_metrics, *extension_metrics],
        }

    if tuple(bindings) != expected_grader_codes:
        raise RuntimeError("frozen evaluation grader set/order changed")
    unknown_extension_graders = set(GRADER_OUTPUT_METRIC_EXTENSIONS) - set(bindings)
    if unknown_extension_graders:
        raise RuntimeError("metric-kind extensions reference unknown graders")
    return {
        "source_catalog_ref": (
            "ai/RAOS_05_evaluation_catalog_v0.1.yaml#/graders"
        ),
        "metric_registry_ref": (
            "ai/RAOS_05_evaluation_catalog_v0.1.yaml#/metrics"
        ),
        "database_function": "ai.canonical_grader_output_metrics(text)",
        "ordering": "UPSTREAM_OUTPUT_METRICS_THEN_METRIC_KIND_EXTENSIONS",
        "bindings": bindings,
    }


def build_adoption_document(
    frozen: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    definitions = {
        "document": {
            "id": "RAOS-AI-CANONICAL-ADOPTION-001",
            "version": REVISION_VERSION,
            "story_id": "ST-0003",
            "decision_id": "INT-DEC-004",
            "status": "CANONICAL_REVISION_CANDIDATE",
        },
        "predecessor": {
            "id": PREDECESSOR_ID,
            "version": "0.2",
            "manifest_sha256": PREDECESSOR_MANIFEST_HASH,
            "job_state_sha256": JOB_STATE_HASH,
        },
        "source_package": {
            "path": relative_repo_path(AI_PACKAGE),
            "sha256": EXPECTED_INPUT_HASHES[relative_repo_path(AI_PACKAGE)],
            "sha256sums_declared_file_count": 97,
            "sha256sums_validation": "COMPLETE_PASS_REQUIRED_BEFORE_BUILD",
        },
        "frozen_artifacts": copy.deepcopy(dict(frozen)),
        "grader_output_metric_bindings": build_grader_output_metric_bindings(),
        "copy_policy": {
            "byte_identical": True,
            "package_relative_topology_preserved": True,
            "catalog_internal_version_rewritten": False,
        },
        "excluded_from_production_contract": [
            "eval_cases/bootstrap_cases_v0.1.jsonl",
            "fixtures/expected/**",
            "fixtures/source_packets/**",
        ],
        "proposal_policy": {
            "execution": "FORBIDDEN",
            "retention": "HASH_PINNED_PROVENANCE_ONLY",
            "data_proposal_sha256": EXPECTED_INPUT_HASHES[
                relative_repo_path(AI_DATA_PROPOSAL)
            ],
            "api_proposal_sha256": EXPECTED_INPUT_HASHES[
                relative_repo_path(AI_API_PROPOSAL)
            ],
        },
        "public_isolation": {
            "path": "../openapi-public.v0.1.yaml",
            "sha256": PUBLIC_OPENAPI_HASH,
            "ai_surface_allowed": False,
        },
    }
    return definitions


def generate_contracts(
    contracts_root: Path,
    *,
    checksum_inventory: Mapping[str, str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Generate the complete staged contract tree.

    The optional inventory is a stable test seam. Production builds always
    validate and pass the complete archive inventory before this function.
    """

    if checksum_inventory is None:
        checksum_inventory = verify_ai_archive()
    contracts_root.mkdir(parents=True, exist_ok=True)
    copy_predecessor_contracts(contracts_root)
    promote_revision_files(contracts_root)
    frozen = copy_frozen_ai_artifacts(contracts_root, checksum_inventory)
    copy_frozen_public_openapi(contracts_root)
    write_yaml(
        contracts_root / "ai" / "canonical-adoption.v0.3.yaml",
        build_adoption_document(frozen),
    )
    enrich_contracts(contracts_root)
    return frozen


SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"
AI_JOB_STATES = (
    "REQUESTED",
    "VALIDATING_INPUT",
    "QUEUED",
    "RUNNING",
    "VALIDATING_OUTPUT",
    "AWAITING_HUMAN",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "RETRY_SCHEDULED",
    "FAILED_TERMINAL",
    "QUARANTINED",
    "CANCELLED",
    "EXPIRED",
)
PROMPT_STATES = (
    "DRAFT",
    "IN_REVIEW",
    "EVALUATING",
    "CERTIFIED",
    "ACTIVE",
    "SUSPENDED",
    "RETIRED",
)
ROUTE_STATES = (
    "DRAFT",
    "EVALUATING",
    "CERTIFIED",
    "CANARY",
    "ACTIVE",
    "PAUSED",
    "ROLLED_BACK",
    "RETIRED",
)
DATASET_STATES = (
    "DRAFT",
    "CURATING",
    "LOCKED",
    "ACTIVE",
    "COMPROMISED",
    "RETIRED",
)
EVALUATION_RUN_STATES = (
    "PLANNED",
    "RUNNING",
    "GRADING",
    "HUMAN_REVIEW",
    "COMPLETED",
    "FAILED",
    "INVALIDATED",
)
REQUIRED_EVALUATION_SPLITS = (
    "DEV",
    "CALIBRATION",
    "HOLDOUT",
    "ADVERSARIAL",
    "REGRESSION",
)
ALL_BOUND_DATASET_EVALUATION_CASES_SCOPE = (
    "ALL_EVALUATION_CASES_IN_BOUND_DATASET"
)
EVALUATION_DISPOSITIONS = (
    "CALL_PROVIDER_AND_PASS",
    "CALL_PROVIDER_AND_FLAG",
    "BLOCK_BEFORE_PROVIDER",
    "EXPECTED_REFUSAL",
    "EXPECTED_TERMINAL_FAILURE",
)
ZERO_TOLERANCE_FAILURE_CODES = (
    "AI-FCT-001",
    "AI-FCT-004",
    "AI-POL-001",
    "AI-POL-002",
    "AI-FCT-003",
    "AI-POL-003",
    "AI-POL-005",
    "AI-POL-004",
)
ZERO_TOLERANCE_MAPPED_METRIC_CODES = (
    "unsupported_critical_fact_rate",
    "fabricated_experience_rate",
    "rakuten_review_body_leakage_rate",
    "affiliate_bias_violation_rate",
    "product_identity_accuracy",
    "prompt_injection_follow_rate",
)
ZERO_TOLERANCE_ARTIFACT_ONLY_CODES = ("AI-POL-005", "AI-POL-004")
RATIO_METRIC_CODES = (
    "schema_valid_rate",
    "complete_response_rate",
    "evidence_reference_precision",
    "critical_claim_support_rate",
    "unsupported_critical_fact_rate",
    "numeric_exactness",
    "product_identity_accuracy",
    "fabricated_experience_rate",
    "rakuten_review_body_leakage_rate",
    "affiliate_bias_violation_rate",
    "prompt_injection_follow_rate",
    "policy_blocker_recall",
    "false_clearance_rate",
    "critical_claim_recall",
    "claim_precision",
    "intent_accuracy",
    "cluster_purity",
    "editorial_business_separation",
    "finding_resolution_rate",
    "new_unsupported_claim_rate",
    "priority_order_preservation",
    "blocking_gap_recall",
    "affected_claim_recall",
    "human_acceptance_rate",
)
RELEASE_STATES = (
    "DRAFT",
    "READY_FOR_REVIEW",
    "APPROVED_CANARY",
    "APPROVED_ACTIVE",
    "REJECTED",
    "REVOKED",
)
SHA256_PATTERN = "^[0-9a-f]{64}$"
GIT_SHA_PATTERN = "^[0-9a-f]{40,64}$"


def uuid_schema(*, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": ["string", "null"] if nullable else "string",
        "format": "uuid",
    }


def timestamp_schema(*, nullable: bool = False) -> dict[str, Any]:
    return {
        "type": ["string", "null"] if nullable else "string",
        "format": "date-time",
    }


def text_schema(
    *,
    nullable: bool = False,
    min_length: int = 1,
    max_length: int = 500,
    pattern: str | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": ["string", "null"] if nullable else "string",
        "minLength": min_length,
        "maxLength": max_length,
    }
    if pattern is not None:
        schema["pattern"] = pattern
    return schema


def enum_schema(values: Iterable[str]) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def integer_schema(
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        schema["maximum"] = maximum
    return schema


def metadata_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "maxProperties": 100,
    }


def route_config_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "reasoning_effort": {
                "type": ["string", "null"],
                "enum": ["low", "medium", "high", None],
            },
            "temperature": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 2,
            },
            "max_output_tokens": integer_schema(minimum=1),
            "timeout_seconds": integer_schema(minimum=1, maximum=3600),
            "max_fallbacks": integer_schema(minimum=0, maximum=1),
            "fallback_on": {
                "type": "array",
                "items": enum_schema(
                    (
                        "PROVIDER_TRANSIENT",
                        "RATE_LIMIT",
                        "MODEL_UNAVAILABLE",
                        "SCHEMA_OUTPUT_AFTER_ONE_REPAIR",
                    )
                ),
                "uniqueItems": True,
                "maxItems": 4,
            },
            "never_fallback_on": {
                "type": "array",
                "items": enum_schema(
                    (
                        "ANY",
                        "POLICY",
                        "CONTRACT",
                        "INVALID_EVIDENCE",
                        "BUDGET",
                        "REFUSAL",
                        "CONTENT_FILTER",
                    )
                ),
                "uniqueItems": True,
                "maxItems": 7,
            },
            "minimum_eval_status": enum_schema(
                (
                    "CERTIFIED",
                    "CERTIFIED_CRITICAL",
                    "JUDGE_CALIBRATED",
                    "DISABLED",
                )
            ),
            "canary_max_percent": integer_schema(minimum=0, maximum=100),
            "batch_eligible": {"type": "boolean"},
            "prompt_cache_eligible": {"type": "boolean"},
            "enabled": {"type": "boolean"},
            "store": {"type": "boolean", "const": False},
            "strict_structured_output": {"type": "boolean"},
        },
        "required": [
            "reasoning_effort",
            "temperature",
            "max_fallbacks",
            "fallback_on",
            "never_fallback_on",
            "minimum_eval_status",
            "canary_max_percent",
            "batch_eligible",
            "prompt_cache_eligible",
            "enabled",
            "store",
            "strict_structured_output",
        ],
        "description": (
            "Canonical route configuration vocabulary copied from "
            "RAOS_05_model_routing_catalog_v0.1.yaml. The frozen field name is "
            "canary_max_percent; aliases are forbidden."
        ),
        "x-raos-canonical-source": (
            "ai/RAOS_05_model_routing_catalog_v0.1.yaml"
        ),
    }


def split_policy_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "dev_share": {"type": "number", "minimum": 0, "maximum": 1},
            "calibration_share": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "holdout_share": {"type": "number", "minimum": 0, "maximum": 1},
            "adversarial_share": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "regression_share": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "holdout_blinded": {"type": "boolean", "const": True},
            "labels_hidden_from_prompt_authors": {
                "type": "boolean",
                "const": True,
            },
        },
        "required": [
            "dev_share",
            "calibration_share",
            "holdout_share",
            "adversarial_share",
            "regression_share",
            "holdout_blinded",
            "labels_hidden_from_prompt_authors",
        ],
    }


def suite_config_schema() -> dict[str, Any]:
    """Build the exact 12-suite config union from the immutable AI catalog."""

    with ZipFile(AI_PACKAGE) as archive:
        catalog = load_yaml_bytes(
            archive.read(AI_EVALUATION_CATALOG_MEMBER),
            source=AI_EVALUATION_CATALOG_MEMBER,
        )
    suites = catalog.get("suites")
    if not isinstance(suites, list) or len(suites) != 12:
        raise RuntimeError("expected exactly 12 frozen evaluation suites")

    required_names = [
        "required_splits",
        "required_graders",
        "required_metrics",
        "minimum_human_reviews_per_case",
        "minimum_critical_human_reviews_per_case",
        "minimum_double_review_fraction",
        "adjudication_required_on_disagreement",
        "minimum_adjudicated_cases",
        "zero_tolerance_failures",
        "promotion_policy",
        "regression_margin",
    ]
    metric_value_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "operator": enum_schema((">=", ">", "<=", "<", "==", "!=")),
            "value": {"type": "number"},
        },
        "required": ["operator", "value"],
    }
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "required_splits": {
                "type": "array",
                "items": enum_schema(REQUIRED_EVALUATION_SPLITS),
                "minItems": 5,
                "maxItems": 5,
                "uniqueItems": True,
            },
            "required_graders": {
                "type": "array",
                "items": text_schema(max_length=200),
                "minItems": 6,
                "maxItems": 7,
                "uniqueItems": True,
            },
            "required_metrics": {
                "type": "object",
                "additionalProperties": copy.deepcopy(metric_value_schema),
                "minProperties": 1,
                "maxProperties": 100,
            },
            "minimum_human_reviews_per_case": {"type": "integer", "const": 1},
            "minimum_critical_human_reviews_per_case": {
                "type": "integer",
                "const": 2,
            },
            "minimum_double_review_fraction": {
                "type": "number",
                "const": 0.2,
            },
            "adjudication_required_on_disagreement": {
                "type": "boolean",
                "const": True,
            },
            "minimum_adjudicated_cases": {
                "type": "integer",
                "enum": [100, 150, 200],
            },
            "zero_tolerance_failures": {
                "type": "array",
                "items": text_schema(max_length=500),
                "minItems": 8,
                "maxItems": 8,
                "uniqueItems": True,
            },
            "promotion_policy": enum_schema(
                ("one_approver_plus_owner", "critical_two_person_approval")
            ),
            "regression_margin": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "absolute": {"type": "number", "const": 0.01},
                    "mean_score": {"type": "number", "const": 0.1},
                    "zero_tolerance": {"type": "number", "const": 0.0},
                },
                "required": ["absolute", "mean_score", "zero_tolerance"],
            },
        },
        "required": required_names,
        "description": (
            "Exact suite configuration union derived from all 12 frozen entries "
            "in RAOS_05_evaluation_catalog_v0.1.yaml. Unknown keys or values "
            "outside a frozen task variant are rejected."
        ),
        "x-raos-canonical-source": (
            "ai/RAOS_05_evaluation_catalog_v0.1.yaml#/suites"
        ),
        "x-raos-frozen-suite-config-variant-count": 12,
        "oneOf": [],
    }
    seen_configs: set[str] = set()
    for suite in suites:
        if not isinstance(suite, dict):
            raise RuntimeError("malformed frozen evaluation suite")
        suite_code = suite.get("suite_code")
        if not isinstance(suite_code, str):
            raise RuntimeError("frozen evaluation suite code is missing")
        config = {
            "required_splits": suite.get("required_splits"),
            "required_graders": suite.get("required_graders"),
            "required_metrics": suite.get("thresholds"),
            "minimum_human_reviews_per_case": 1,
            "minimum_critical_human_reviews_per_case": 2,
            "minimum_double_review_fraction": 0.2,
            "adjudication_required_on_disagreement": True,
            "minimum_adjudicated_cases": suite.get(
                "minimum_adjudicated_cases"
            ),
            "zero_tolerance_failures": suite.get("zero_tolerance_failures"),
            "promotion_policy": suite.get("promotion_policy"),
            "regression_margin": suite.get("regression_margin"),
        }
        fingerprint = json.dumps(config, ensure_ascii=False, sort_keys=True)
        if fingerprint in seen_configs:
            raise RuntimeError("duplicate frozen suite configuration variant")
        seen_configs.add(fingerprint)
        metrics = config["required_metrics"]
        if not isinstance(metrics, dict) or not metrics:
            raise RuntimeError(f"frozen suite metrics are missing: {suite_code}")
        metric_properties: dict[str, Any] = {}
        for metric_name, threshold in metrics.items():
            if not isinstance(metric_name, str) or not isinstance(threshold, dict):
                raise RuntimeError(f"malformed frozen suite metric: {suite_code}")
            metric_properties[metric_name] = {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "operator": {"const": threshold.get("operator")},
                    "value": {"const": threshold.get("value")},
                },
                "required": ["operator", "value"],
            }
        variant_properties = {
            name: {"const": copy.deepcopy(value)}
            for name, value in config.items()
            if name != "required_metrics"
        }
        variant_properties["required_metrics"] = {
            "type": "object",
            "additionalProperties": False,
            "properties": metric_properties,
            "required": list(metric_properties),
        }
        schema["oneOf"].append(
            {
                "title": suite_code,
                "properties": variant_properties,
                "required": required_names,
                "x-raos-suite-code": suite_code,
            }
        )
    return schema


def strict_schema(
    *,
    schema_id: str,
    title: str,
    properties: Mapping[str, Any],
    required: Iterable[str],
    description: str | None = None,
    classification: str = "INTERNAL",
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "$schema": SCHEMA_DIALECT,
        "$id": f"https://schemas.raos.local/ai-governance/{schema_id}/v1",
        "title": title,
        "type": "object",
        "additionalProperties": False,
        "properties": copy.deepcopy(dict(properties)),
        "required": list(required),
        "x-raos-classification": classification,
    }
    if description is not None:
        schema["description"] = description
    return schema


def rollback_strategy_conditions() -> list[dict[str, Any]]:
    """Require exactly one machine-readable rollback resolution."""

    return [
        {
            "if": {
                "properties": {
                    "rollback_strategy": {"const": "PREVIOUS_RELEASE"}
                },
                "required": ["rollback_strategy"],
            },
            "then": {
                "properties": {
                    "rollback_release_decision_id": uuid_schema(),
                    "rollback_runbook_artifact_id": {"type": "null"},
                    "rollback_runbook_sha256": {"type": "null"},
                },
                "required": [
                    "rollback_release_decision_id",
                    "rollback_runbook_artifact_id",
                    "rollback_runbook_sha256",
                ],
            },
        },
        {
            "if": {
                "properties": {
                    "rollback_strategy": {"const": "DISABLE_ROUTE"}
                },
                "required": ["rollback_strategy"],
            },
            "then": {
                "properties": {
                    "rollback_release_decision_id": {"type": "null"},
                    "rollback_runbook_artifact_id": uuid_schema(),
                    "rollback_runbook_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                },
                "required": [
                    "rollback_release_decision_id",
                    "rollback_runbook_artifact_id",
                    "rollback_runbook_sha256",
                ],
            },
        },
    ]


def nullable_artifact_hash_pair_condition(
    *,
    artifact_field: str,
    hash_field: str,
) -> dict[str, Any]:
    return {
        "oneOf": [
            {
                "properties": {
                    artifact_field: {"type": "null"},
                    hash_field: {"type": "null"},
                },
                "required": [artifact_field, hash_field],
            },
            {
                "properties": {
                    artifact_field: uuid_schema(),
                    hash_field: text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                },
                "required": [artifact_field, hash_field],
            },
        ]
    }


def current_champion_selection_invariants() -> dict[str, Any]:
    return {
        "task_scope": "SAME_TASK_DEFINITION",
        "release_status": "APPROVED_ACTIVE",
        "component_status_filter": "NONE",
        "selection": "LATEST_APPROVED_ACTIVE",
        "ordering": [
            {
                "field": "ACTIVE_RELEASE_APPROVAL.signed_at",
                "direction": "DESC",
            },
            {"field": "ReleaseDecisionV1.id", "direction": "DESC"},
        ],
    }


def previous_release_rollback_target_invariants() -> dict[str, Any]:
    protected_component_fields = [
        "task_definition_id",
        "prompt_version_id",
        "model_route_version_id",
        "output_schema_version_id",
        "resolved_model_id",
        "policy_bundle_version_id",
    ]
    return {
        "bound_resource": "ReleaseDecisionV1",
        "applies_when": {"rollback_strategy": "PREVIOUS_RELEASE"},
        "target_reference_field": "rollback_release_decision_id",
        "current_champion_selection": (
            current_champion_selection_invariants()
        ),
        "target_reference_exact_match": {
            "left": "rollback_release_decision_id",
            "operator": "==",
            "right": "CURRENT_CHAMPION.release_decision_id",
        },
        "target_release_requirements": {
            "same_task_definition": True,
            "status": "APPROVED_ACTIVE",
            "component_status_requirements": {
                field: "ACTIVE" for field in protected_component_fields
            },
        },
        "live_dependency_guard": {
            "dependent_statuses": [
                "READY_FOR_REVIEW",
                "APPROVED_CANARY",
                "APPROVED_ACTIVE",
            ],
            "target_release_revoke_forbidden": True,
            "protected_component_fields": protected_component_fields,
            "protected_component_active_exit_forbidden": True,
            "resolution_order": [
                "REVOKE_DEPENDENT_FIRST",
                "SELECT_DISABLE_ROUTE_WHILE_DEPENDENT_IS_DRAFT",
            ],
        },
    }


def judge_calibration_scope_invariants() -> dict[str, Any]:
    return {
        "applies_to_grader": "grader.model_judge.v1",
        "calibration_resource": "JudgeCalibrationV1",
        "required_calibration_status": "PASSED",
        "calibration_must_be_unexpired": True,
        "calibration_exact_bindings": [
            "evaluated_task_definition_id",
            "judge_route_version_id",
            "judge_prompt_version_id",
            "resolved_judge_model_id",
            "dataset_version_id",
            "rubric_artifact_id",
            "rubric_sha256",
            "grader_version",
        ],
        "evaluation_run_exact_matches": {
            "JudgeCalibrationV1.evaluated_task_definition_id": (
                "EvaluationSuiteV1.task_definition_id"
            ),
            "JudgeCalibrationV1.dataset_version_id": (
                "EvaluationRunV1.dataset_version_id"
            ),
        },
        "evaluation_metric_exact_matches": {
            "JudgeCalibrationV1.id": "EvaluationResult.judge_calibration_id",
            "JudgeCalibrationV1.judge_route_version_id": (
                "EvaluationResult.judge_route_version_id"
            ),
            "JudgeCalibrationV1.judge_prompt_version_id": (
                "EvaluationResult.judge_prompt_version_id"
            ),
            "JudgeCalibrationV1.rubric_artifact_id": (
                "EvaluationResult.judge_rubric_artifact_id"
            ),
            "JudgeCalibrationV1.resolved_judge_model_id": (
                "EvaluationResult.judge_resolved_model_id"
            ),
            "JudgeCalibrationV1.grader_version": (
                "EvaluationResult.judge_grader_version"
            ),
        },
        "dataset_scope": {
            "snapshot_match": "EXACT",
            "domain_category_coverage": (
                "SAME_DATASET_SNAPSHOT_INCLUDING_DOMAIN_AND_CATEGORY_SLICES"
            ),
        },
    }


def evaluation_evidence_uniqueness_invariants() -> dict[str, Any]:
    return {
        "evaluation_case_input_evidence": {
            "resource": "EvaluationCaseV1",
            "field": "input_artifact_id",
            "scope_fields": ["dataset_version_id"],
            "uniqueness": "UNIQUE_WITHIN_SCOPE",
            "null_policy": "NON_NULL",
        },
        "evaluation_case_result_evidence": {
            "resource": "EvaluationCaseResultV1",
            "scope": "ALL_EVALUATION_CASE_RESULTS",
            "independently_unique_when_non_null": [
                "ai_attempt_id",
                "output_artifact_id",
            ],
        },
        "prohibits": [
            "EVIDENCE_REUSE",
            "PADDED_MINIMUM_CASE_COUNTS",
        ],
    }


def evaluation_required_split_coverage_invariants() -> dict[str, Any]:
    return {
        "required_splits_source": "EvaluationSuiteV1.suite_config.required_splits",
        "required_splits": list(REQUIRED_EVALUATION_SPLITS),
        "bound_dataset": "EvaluationRunV1.dataset_version_id",
        "case_split_field": "EvaluationCaseV1.split",
        "minimum_case_count_per_required_split": 1,
        "enforced_at": [
            "DATASET_LOCK_OR_ACTIVATION",
            "EVALUATION_RUN_CREATION",
            "EVALUATION_RUN_COMPLETION",
        ],
        "missing_required_split_case": "BLOCKING",
    }


def zero_tolerance_evidence_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            code: {"type": "integer", "minimum": 0, "maximum": 50}
            for code in ZERO_TOLERANCE_FAILURE_CODES
        },
        "required": list(ZERO_TOLERANCE_FAILURE_CODES),
        "x-raos-property-sum-maximum": 50,
    }


def zero_tolerance_evidence_invariants() -> dict[str, Any]:
    return {
        "failure_codes": list(ZERO_TOLERANCE_FAILURE_CODES),
        "per_code_count": {"minimum": 0, "maximum": 50},
        "total_count_maximum": 50,
        "generated_failure_count": {
            "field": "zero_tolerance_failure_count",
            "expression": "SUM_ZERO_TOLERANCE_EVIDENCE_VALUES",
            "database_generated": True,
            "response_read_only": True,
            "writer_input": "FORBIDDEN",
        },
        "artifact_binding": {
            "artifact_field": "zero_tolerance_evidence_artifact_id",
            "sha256_field": "zero_tolerance_evidence_sha256",
            "artifact_must_be_immutable": True,
            "sha256_match": "EXACT",
        },
        "completion_binding": {
            "same_evaluation_run": True,
            "same_evaluation_case": True,
            "grader_code": "grader.forbidden_content.v1",
            "grader_result_artifact_field": "EvaluationResult.result_artifact_id",
            "must_equal": "zero_tolerance_evidence_artifact_id",
        },
        "mapped_metric_failure_equivalence": {
            "match": "FAILURE_AND_NON_FAILURE_MUST_AGREE",
            "evidence_count_failure": "GREATER_THAN_ZERO",
            "evidence_count_non_failure": "EQUALS_ZERO",
            "biconditional": True,
            "required_metric_codes": list(
                ZERO_TOLERANCE_MAPPED_METRIC_CODES
            ),
            "mappings": {
                "AI-FCT-001": {
                    "metric_code": "unsupported_critical_fact_rate",
                    "failure_when": "METRIC_VALUE_POSITIVE",
                },
                "AI-FCT-004": {
                    "metric_code": "fabricated_experience_rate",
                    "failure_when": "METRIC_VALUE_POSITIVE",
                },
                "AI-POL-001": {
                    "metric_code": "rakuten_review_body_leakage_rate",
                    "failure_when": "METRIC_VALUE_POSITIVE",
                },
                "AI-POL-002": {
                    "metric_code": "affiliate_bias_violation_rate",
                    "failure_when": "METRIC_VALUE_POSITIVE",
                },
                "AI-FCT-003": {
                    "metric_code": "product_identity_accuracy",
                    "failure_when": "METRIC_VALUE_BELOW_ONE",
                },
                "AI-POL-003": {
                    "metric_code": "prompt_injection_follow_rate",
                    "failure_when": "METRIC_VALUE_POSITIVE",
                },
            },
            "artifact_only_failure_codes": list(
                ZERO_TOLERANCE_ARTIFACT_ONLY_CODES
            ),
            "unmapped_failure_codes": list(
                ZERO_TOLERANCE_ARTIFACT_ONLY_CODES
            ),
            "artifact_only_semantics": {
                "metric_mapping": "FORBIDDEN",
                "evidence_source": "BOUND_IMMUTABLE_EVIDENCE_ARTIFACT_ONLY",
                "artifact_binding": "MUST_USE_EvaluationCaseResultV1_ARTIFACT_BINDING",
            },
        },
        "all_case_metric_completeness": {
            "case_scope": ALL_BOUND_DATASET_EVALUATION_CASES_SCOPE,
            "required_splits": list(REQUIRED_EVALUATION_SPLITS),
            "required_metric_codes": list(
                ZERO_TOLERANCE_MAPPED_METRIC_CODES
            ),
            "required_result_per_case_and_metric": "EXACTLY_ONE",
            "missing_metric": "RUN_COMPLETION_AND_RELEASE_BLOCKING",
        },
    }


def evaluation_baseline_invariants() -> dict[str, Any]:
    return {
        "field": "baseline_evaluation_run_id",
        "nullable": True,
        "create_request": "OPTIONAL",
        "read_detail_event": "PRESENT_NULLABLE",
        "immutability": "IMMUTABLE_AFTER_INSERT",
        "referenced_run": {
            "must_be_distinct_from_candidate": True,
            "required_status": "COMPLETED",
            "exact_match_fields": ["suite_id", "dataset_version_id"],
        },
        "release_binding": {
            "current_champion": current_champion_selection_invariants(),
            "when_current_champion_exists": {
                "required_non_null": True,
                "baseline_kind": (
                    "CURRENT_CHAMPION_COMPONENT_RERUN_ON_"
                    "CANDIDATE_SUITE_DATASET"
                ),
                "required_status": "COMPLETED",
                "must_be_distinct_from_candidate": True,
                "candidate_exact_match_fields": [
                    "suite_id",
                    "dataset_version_id",
                ],
                "current_champion_exact_component_bindings": [
                    "prompt_version_id",
                    "model_route_version_id",
                    "output_schema_version_id",
                    "resolved_model_id",
                    "policy_bundle_version_id",
                    "code_git_sha",
                ],
            },
            "when_no_current_champion_exists": {
                "condition": "NO_CURRENT_APPROVED_ACTIVE_CHAMPION",
                "must_be_null": True,
            },
        },
    }


def evaluation_result_ratio_metric_invariants() -> dict[str, Any]:
    return {
        "metric_unit_source": "ai.canonical_metric_unit(metric_code)",
        "ratio_metric_unit": "ratio",
        "ratio_metric_codes": list(RATIO_METRIC_CODES),
        "count_fields": [
            "proportion_numerator_count",
            "proportion_denominator_count",
        ],
        "ratio_rows": {
            "counts_required_non_null": True,
            "numerator": {"minimum": 0},
            "denominator": {"minimum": 1},
            "field_comparison": (
                "proportion_numerator_count <= proportion_denominator_count"
            ),
            "metric_value": {
                "database_derived": True,
                "response_read_only": True,
                "writer_input": "FORBIDDEN",
                "expression": (
                    "proportion_numerator_count::numeric / "
                    "proportion_denominator_count::numeric"
                ),
            },
        },
        "non_ratio_rows": {
            "proportion_numerator_count": "MUST_BE_NULL_OR_ABSENT",
            "proportion_denominator_count": "MUST_BE_NULL_OR_ABSENT",
        },
        "legacy_rows_without_evaluation_run_id": {
            "proportion_numerator_count": "MUST_BE_NULL",
            "proportion_denominator_count": "MUST_BE_NULL",
        },
        "aggregate_ratio": {
            "expression": "SUM_NUMERATOR_DIVIDED_BY_SUM_DENOMINATOR",
            "sql_semantics": (
                "sum(proportion_numerator_count)::numeric / "
                "sum(proportion_denominator_count)::numeric"
            ),
            "forbid_average_of_row_ratios": True,
        },
    }


def evaluation_blocking_aggregate_scope_invariants() -> dict[str, Any]:
    return {
        "required_splits": ["HOLDOUT", "ADVERSARIAL", "REGRESSION"],
        "blocking_scopes_per_split": {
            "overall": "REQUIRED",
            "category": {
                "source": "EvaluationCaseV1.category",
                "scope": "EACH_DISTINCT_CATEGORY_PRESENT_IN_SPLIT",
                "required": True,
            },
        },
        "missing_scope_result": "RUN_COMPLETION_AND_RELEASE_BLOCKING",
        "scope_local_aggregation": {
            "ratio_metrics": {
                "expression": "SUM_NUMERATOR_DIVIDED_BY_SUM_DENOMINATOR",
                "forbid_unweighted_average_of_case_ratios": True,
            },
            "p95_metrics": {
                "metric_codes": ["latency_p95_ms", "cost_jpy_p95"],
                "expression": "PERCENTILE_CONT_0_95_WITHIN_SCOPE",
                "forbid_reuse_of_global_p95": True,
            },
            "other_metrics": "AVERAGE_WITHIN_SCOPE",
        },
        "threshold_gate": {
            "applies_to_every_blocking_scope": True,
            "comparison": "DATABASE_EXACT_POINT_ESTIMATE",
        },
        "reporting_only_dimensions": [
            "article_type",
            "evidence_quality",
            "language_complexity",
            "route",
            "model",
            "tags",
            "other_non_category_slices",
        ],
        "reporting_only_dimensions_may_satisfy_blocking_scope": False,
    }


def cost_latency_reporting_completeness_invariants() -> dict[str, Any]:
    return {
        "required_grader": "grader.cost_latency.v1",
        "required_metric_codes": ["latency_p95_ms", "cost_jpy_p95"],
        "case_scope": ALL_BOUND_DATASET_EVALUATION_CASES_SCOPE,
        "required_splits": list(REQUIRED_EVALUATION_SPLITS),
        "required_result_per_case_and_metric": "EXACTLY_ONE",
        "missing_result": "RUN_COMPLETION_AND_REPORT_BLOCKING",
        "canonical_suite_threshold_semantics": {
            "current_frozen_canonical_suites": {
                "threshold_defined": False,
                "threshold_operator": "MUST_BE_NULL",
                "threshold_value": "MUST_BE_NULL",
                "passed": "MUST_BE_NULL",
                "purpose": "REPORT_COMPLETENESS_ONLY",
            },
            "when_present_in_required_metrics": {
                "threshold_defined": True,
                "required_non_null": [
                    "threshold_operator",
                    "threshold_value",
                    "passed",
                ],
                "exact_match_source": (
                    "EvaluationSuiteV1.suite_config.required_metrics"
                ),
                "blocking_threshold_gate": True,
            },
        },
        "passed_truth_table": {
            "current_frozen_canonical_report_only_p95": "MUST_BE_NULL",
            "required_p95": "MUST_BE_NON_NULL_DATABASE_EXACT",
            "legacy_or_non_report_only_metric": (
                "MUST_BE_NON_NULL_DATABASE_EXACT"
            ),
        },
        "aggregate_reporting": {
            "method": "PERCENTILE_CONT_0_95_WITHIN_EACH_REPORT_SCOPE",
            "current_frozen_canonical_suites_blocking_threshold": False,
            "when_present_in_required_metrics_blocking_threshold": True,
        },
    }


def release_canary_safety_invariants() -> dict[str, Any]:
    return {
        "critical_task_canary": {
            "risk_source": "AITaskDefinition.risk_level",
            "when_risk_level": "CRITICAL",
            "maximum_canary_percent": 1,
            "comparison": "LESS_THAN_OR_EQUAL",
        },
        "same_task_concurrent_canary": {
            "scope_field": "ReleaseDecisionV1.task_definition_id",
            "canary_status": "APPROVED_CANARY",
            "maximum_concurrent_decisions": 1,
            "second_canary": "REJECT",
            "serialization": "SAME_TASK_RELEASE_ADVISORY_LOCK",
        },
    }


def release_regression_invariants() -> dict[str, Any]:
    return {
        "candidate_baseline_field": "EvaluationRunV1.baseline_evaluation_run_id",
        "baseline_source": "PERSISTED_DATABASE_ROWS",
        "pairing": {
            "case_scope": "REGRESSION",
            "required_exact_bindings": [
                "evaluation_case_id",
                "metric_code",
                "grader_code",
                "threshold_operator",
                "threshold_value",
                "judge_calibration_id",
                "judge_route_version_id",
                "judge_prompt_version_id",
                "judge_rubric_artifact_id",
                "judge_resolved_model_id",
                "judge_grader_version",
            ],
            "missing_or_incomparable_pair": "RELEASE_BLOCKING",
        },
        "comparison_scopes": {
            "split": "REGRESSION",
            "overall": "REQUIRED",
            "category": {
                "source": "EvaluationCaseV1.category",
                "scope": "EACH_DISTINCT_CATEGORY_PRESENT_IN_REGRESSION",
                "required": True,
            },
            "scope_local_aggregation": (
                evaluation_blocking_aggregate_scope_invariants()[
                    "scope_local_aggregation"
                ]
            ),
            "missing_category_comparison": "RELEASE_BLOCKING",
        },
        "metric_semantics": {
            "unit_source": "ai.canonical_metric_unit(metric_code)",
            "direction_source": "ai.canonical_metric_direction(metric_code)",
            "margin_source": "ai.canonical_regression_margin(metric_code)",
            "ratio_aggregation": "SUM_NUMERATOR_DIVIDED_BY_SUM_DENOMINATOR",
            "higher_is_better": "candidate >= baseline - margin",
            "lower_is_better": "candidate <= baseline + margin",
            "unknown_unit_direction_or_margin": "RELEASE_BLOCKING",
        },
    }


def evaluation_statistics_artifact_invariants() -> dict[str, Any]:
    return {
        "applies_to": [
            "EvaluationRunV1.run_manifest_artifact_id",
            "EvaluationRunDetailV1.artifact_refs.report_artifact_id",
        ],
        "required_when": ["RUN_COMPLETED", "RELEASE_EVALUATION"],
        "blocking_aggregate_scopes": (
            evaluation_blocking_aggregate_scope_invariants()
        ),
        "cost_latency_reporting_completeness": (
            cost_latency_reporting_completeness_invariants()
        ),
        "ratio_metrics": {
            "required_fields": [
                "metric_code",
                "slice_key",
                "proportion_numerator_count",
                "proportion_denominator_count",
                "point_estimate",
                "one_sided_95_percent_wilson_lower_bound",
            ],
            "point_estimate": "SUM_NUMERATOR_DIVIDED_BY_SUM_DENOMINATOR",
            "uncertainty": {
                "method": "WILSON_SCORE",
                "sidedness": "ONE_SIDED_LOWER_BOUND",
                "confidence_level": 0.95,
            },
            "threshold_gate_value": "POINT_ESTIMATE",
            "wilson_bound_is_threshold_gate": False,
        },
        "pairwise_regression": {
            "required_fields": [
                "metric_code",
                "slice_key",
                "wins",
                "ties",
                "losses",
                "task_slice_win_rate",
                "two_sided_confidence_interval",
            ],
            "pairing_source": "release_regression_invariants.pairing",
            "confidence_interval": {
                "sidedness": "TWO_SIDED",
                "confidence_level": 0.95,
                "required_bounds": ["lower", "upper"],
            },
        },
        "reporting_only_dimensions": (
            evaluation_blocking_aggregate_scope_invariants()[
                "reporting_only_dimensions"
            ]
        ),
        "reporting_only_dimensions_are_release_gates": False,
    }


def evaluation_run_completion_evidence_invariants() -> dict[str, Any]:
    return {
        "required_split_coverage": (
            evaluation_required_split_coverage_invariants()
        ),
        "case_metric_completeness": {
            "case_scope": "ALL_CASES_IN_REQUIRED_SPLITS",
            "required_splits_source": "EvaluationSuiteV1.suite_config.required_splits",
            "required_metrics_source": "EvaluationSuiteV1.suite_config.required_metrics",
            "exact_match_fields": [
                "evaluation_run_id",
                "evaluation_case_id",
                "metric_code",
                "slice_key",
                "threshold_operator",
                "threshold_value",
            ],
        },
        "case_grader_completeness": {
            "case_scope": "ALL_CASES_IN_REQUIRED_SPLITS",
            "required_graders_source": "EvaluationSuiteV1.suite_config.required_graders",
            "grader_metric_binding_source": (
                "canonical-adoption.v0.3.yaml#/grader_output_metric_bindings"
            ),
        },
        "cost_latency_reporting_completeness": (
            cost_latency_reporting_completeness_invariants()
        ),
        "aggregate_threshold_promotion": {
            "required_splits": ["HOLDOUT", "ADVERSARIAL", "REGRESSION"],
            "required_metrics_source": "EvaluationSuiteV1.suite_config.required_metrics",
            "threshold_comparison": "DATABASE_EXACT",
            "blocking_scopes": (
                evaluation_blocking_aggregate_scope_invariants()
            ),
        },
        "metric_passed_truth": {
            "source_fields": [
                "metric_value",
                "threshold_operator",
                "threshold_value",
            ],
            "passed_field": "passed",
            "comparison": "DATABASE_EXACT",
        },
        "ratio_metric_truth": evaluation_result_ratio_metric_invariants(),
        "statistical_artifact_evidence": (
            evaluation_statistics_artifact_invariants()
        ),
        "zero_tolerance_evidence": zero_tolerance_evidence_invariants(),
        "execution_security": (
            evaluation_completion_execution_security_invariants()
        ),
    }


def evaluation_completion_execution_security_invariants() -> dict[str, Any]:
    return {
        "evaluation_run_trigger_guards": [
            {
                "function": "ai.guard_evaluation_run_mutation()",
                "trigger": "trg_ai_eval_run_mutation",
                "security_mode": "SECURITY_DEFINER",
                "fixed_search_path": ["pg_catalog", "ai", "pg_temp"],
            },
            {
                "function": "ai.guard_evaluation_run_start_integrity()",
                "trigger": "trg_ai_eval_run_start_integrity",
                "security_mode": "SECURITY_DEFINER",
                "fixed_search_path": ["pg_catalog", "ai", "policy", "pg_temp"],
            },
            {
                "function": "ai.guard_evaluation_run_completion_evidence()",
                "trigger": "trg_ai_eval_run_completion_evidence",
                "security_mode": "SECURITY_DEFINER",
                "fixed_search_path": ["pg_catalog", "ai", "pg_temp"],
                "invokes": "ai.assert_evaluation_run_evidence(uuid, boolean)",
            },
        ],
        "security_definer_owner": {
            "functions": [
                "ai.guard_evaluation_run_mutation()",
                "ai.guard_evaluation_run_start_integrity()",
                "ai.guard_evaluation_run_completion_evidence()",
            ],
            "must_match_relation_owner": "ai.evaluation_run",
            "live_verified_by": (
                "202607300010_ai_governance_contract_prepare.sql"
            ),
        },
        "worker_direct_execute": {
            "role": "raos_worker_rw",
            "policy": "REVOKED",
            "functions": [
                "ai.guard_evaluation_run_mutation()",
                "ai.guard_evaluation_run_start_integrity()",
                "ai.guard_evaluation_run_completion_evidence()",
                "ai.assert_evaluation_run_evidence(uuid, boolean)",
                "ai.artifact_matches_immutable_hash(uuid, text)",
            ],
            "allowed_path": "TRIGGER_OR_AUTHORIZED_WRAPPER_ONLY",
        },
        "public_execute": {
            "policy": "REVOKED",
            "functions": [
                "ai.guard_evaluation_run_mutation()",
                "ai.guard_evaluation_run_start_integrity()",
                "ai.guard_evaluation_run_completion_evidence()",
                "ai.assert_evaluation_run_evidence(uuid, boolean)",
                "ai.artifact_matches_immutable_hash(uuid, text)",
            ],
        },
    }


def evaluation_run_component_snapshot_freeze_invariants() -> dict[str, Any]:
    return {
        "bound_resource": "EvaluationRunV1",
        "freeze_trigger": {
            "status_leaves": "PLANNED",
            "semantic_event": "RUN_START",
        },
        "applies_in_statuses": [
            "RUNNING",
            "GRADING",
            "HUMAN_REVIEW",
            "COMPLETED",
            "FAILED",
            "INVALIDATED",
        ],
        "frozen_components": {
            "EvaluationSuiteV1.task_definition_id": "AITaskDefinition",
            "EvaluationRunV1.prompt_version_id": "PromptVersionV1",
            "EvaluationRunV1.model_route_version_id": "ModelRouteVersionV1",
            "EvaluationRunV1.output_schema_version_id": "OutputSchemaVersion",
            "EvaluationRunV1.resolved_model_id": "ModelDefinitionV1",
            "EvaluationRunV1.policy_bundle_version_id": "PolicyBundle",
        },
        "freeze_scope": [
            "BINDING_IDENTITY",
            "EVALUATED_COMPONENT_CONTENT_SNAPSHOT",
        ],
        "freeze_duration": "PERMANENT_AFTER_RUN_START",
        "component_content_mutation_after_freeze": "FORBIDDEN",
        "nested_graph_freeze": {
            "EvaluationRunV1.policy_bundle_version_id": (
                "POLICY_BUNDLE_RULE_MEMBERSHIP_AND_RULE_VERSION_CONTENT"
            ),
        },
        "semantic_substitution_after_freeze": "FORBIDDEN",
    }


def policy_rule_graph_invariants() -> dict[str, Any]:
    return {
        "rule_version": {
            "resource": "policy.rule_version",
            "draft_status": "DRAFT",
            "semantic_content_hash_and_approval_after_draft_exit": (
                "PERMANENTLY_IMMUTABLE"
            ),
            "lifecycle_transitions": {
                "DRAFT": ["ACTIVE", "REJECTED", "RETIRED"],
                "ACTIVE": ["RETIRED"],
                "REJECTED": [],
                "RETIRED": [],
            },
            "active_to_retired_forbidden_while_referenced_by_active_bundle": (
                True
            ),
        },
        "bundle_rule_membership": {
            "resource": "policy.bundle_rule",
            "mutation_policy": "APPEND_ONLY",
            "insert_allowed_when": {
                "PolicyBundle.status": "DRAFT",
                "policy.rule_version.status": "ACTIVE",
            },
            "update": "FORBIDDEN",
            "delete": "FORBIDDEN",
        },
        "active_bundle": {
            "resource": "PolicyBundle",
            "required_child_rule_status": "ACTIVE",
            "inactive_child_rule_allowed": False,
            "minimum_child_rule_count": 1,
            "draft_to_active_when_empty": "FORBIDDEN",
        },
        "evaluation_run_semantic_substitution_guard": {
            "freeze_trigger": "EvaluationRunV1.status_leaves_PLANNED",
            "run_binding": "EvaluationRunV1.policy_bundle_version_id",
            "frozen_child_graph": [
                "PolicyBundle",
                "policy.bundle_rule_membership",
                "policy.rule_version_identity_semantic_content_hash_and_approval",
            ],
            "semantic_substitution_after_run_start": "FORBIDDEN",
        },
        "concurrency_serialization": {
            "mechanism": "TRANSACTION_SCOPED_ADVISORY_LOCK",
            "lock_scope": "RULE",
            "competing_paths": [
                "RULE_VERSION_LIFECYCLE_TRANSITION",
                "BUNDLE_RULE_MEMBERSHIP_INSERT",
                "POLICY_BUNDLE_ACTIVATION",
            ],
            "serialization_required": True,
        },
    }


def resource_schema_definitions() -> dict[str, dict[str, Any]]:
    audit_fields = {
        "created_at": timestamp_schema(),
        "updated_at": timestamp_schema(),
        "lock_version": integer_schema(),
    }
    definitions: dict[str, dict[str, Any]] = {}
    definitions["ai-task-definition.v1.schema.json"] = strict_schema(
        schema_id="ai-task-definition",
        title="AI Task Definition",
        properties={
            "id": uuid_schema(),
            "task_code": text_schema(max_length=200),
            "name": text_schema(max_length=200),
            "description": text_schema(max_length=2000),
            "risk_level": enum_schema(("LOW", "MEDIUM", "HIGH", "CRITICAL")),
            "output_schema_code": text_schema(max_length=300),
            "default_max_tokens": integer_schema(minimum=1, maximum=1000000),
            "default_max_cost_jpy": integer_schema(),
            "human_review_required": {"type": "boolean"},
            "status": enum_schema(("ACTIVE", "PAUSED", "RETIRED")),
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "task_code",
            "name",
            "description",
            "risk_level",
            "output_schema_code",
            "default_max_tokens",
            "default_max_cost_jpy",
            "human_review_required",
            "status",
            "created_at",
        ),
    )
    definitions["ai-job.v1.schema.json"] = strict_schema(
        schema_id="ai-job",
        title="AI Job",
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "ops_job_id": uuid_schema(),
            "task_definition_id": uuid_schema(),
            "article_plan_id": uuid_schema(nullable=True),
            "article_version_id": uuid_schema(nullable=True),
            "source_packet_version_id": uuid_schema(),
            "prompt_version_id": uuid_schema(),
            "output_schema_version_id": uuid_schema(),
            "model_route_version_id": uuid_schema(),
            "policy_bundle_version_id": uuid_schema(nullable=True),
            "release_decision_id": uuid_schema(nullable=True),
            "status": enum_schema(AI_JOB_STATES),
            "request_config": metadata_schema(),
            "input_manifest_sha256": text_schema(
                nullable=True,
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "max_cost_jpy": integer_schema(),
            "budget_reserved_jpy": integer_schema(),
            "completed_at": timestamp_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "ops_job_id",
            "task_definition_id",
            "article_plan_id",
            "article_version_id",
            "source_packet_version_id",
            "prompt_version_id",
            "output_schema_version_id",
            "model_route_version_id",
            "policy_bundle_version_id",
            "release_decision_id",
            "status",
            "request_config",
            "input_manifest_sha256",
            "max_cost_jpy",
            "budget_reserved_jpy",
            "completed_at",
            *audit_fields,
        ),
    )
    definitions["prompt-version.v1.schema.json"] = strict_schema(
        schema_id="prompt-version",
        title="Prompt Version",
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "task_definition_id": uuid_schema(),
            "prompt_code": text_schema(max_length=200),
            "version_no": integer_schema(minimum=1),
            "locale": text_schema(
                min_length=2,
                max_length=16,
                pattern="^[a-z]{2,3}(-[A-Z]{2})?$",
            ),
            "git_path": text_schema(max_length=1000),
            "git_commit_sha": text_schema(
                min_length=40,
                max_length=64,
                pattern=GIT_SHA_PATTERN,
            ),
            "template_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "author_principal_id": uuid_schema(),
            "compiler_version": text_schema(nullable=True, max_length=100),
            "input_contract_sha256": text_schema(
                nullable=True,
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "policy_test_status": enum_schema(
                ("NOT_EXECUTED", "PASSED", "FAILED")
            ),
            "status": enum_schema(PROMPT_STATES),
            "effective_from": timestamp_schema(nullable=True),
            "effective_to": timestamp_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "task_definition_id",
            "prompt_code",
            "version_no",
            "locale",
            "git_path",
            "git_commit_sha",
            "template_sha256",
            "author_principal_id",
            "compiler_version",
            "input_contract_sha256",
            "policy_test_status",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            "approved_at",
            *audit_fields,
        ),
    )
    definitions["model-definition.v1.schema.json"] = strict_schema(
        schema_id="model-definition",
        title="Model Definition",
        properties={
            "id": uuid_schema(),
            "provider_code": text_schema(max_length=100),
            "provider_model_id": text_schema(max_length=200),
            "display_name": text_schema(max_length=200),
            "capabilities": {
                "type": "object",
                "additionalProperties": True,
            },
            "input_price_per_million": {
                "type": ["number", "null"],
                "minimum": 0,
            },
            "cached_input_price_per_million": {
                "type": ["number", "null"],
                "minimum": 0,
            },
            "output_price_per_million": {
                "type": ["number", "null"],
                "minimum": 0,
            },
            "pricing_currency": {
                "type": ["string", "null"],
                "pattern": "^[A-Z]{3}$",
            },
            "pricing_observed_at": timestamp_schema(nullable=True),
            "status": enum_schema(
                ("ACTIVE", "EVALUATION", "PAUSED", "RETIRED", "BLOCKED")
            ),
            "context_window_tokens": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "max_output_tokens": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "knowledge_cutoff": {
                "type": ["string", "null"],
                "format": "date",
            },
            "metadata_observed_at": timestamp_schema(nullable=True),
            "provider_metadata": metadata_schema(),
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "provider_code",
            "provider_model_id",
            "display_name",
            "capabilities",
            "input_price_per_million",
            "cached_input_price_per_million",
            "output_price_per_million",
            "pricing_currency",
            "pricing_observed_at",
            "status",
            "context_window_tokens",
            "max_output_tokens",
            "knowledge_cutoff",
            "metadata_observed_at",
            "provider_metadata",
            "created_at",
        ),
    )
    definitions["model-route-version.v1.schema.json"] = strict_schema(
        schema_id="model-route-version",
        title="Model Route Version",
        properties={
            "id": uuid_schema(),
            "route_code": text_schema(max_length=200),
            "version_no": integer_schema(minimum=1),
            "task_definition_id": uuid_schema(),
            "primary_model_id": uuid_schema(),
            "fallback_model_id": uuid_schema(nullable=True),
            "route_config": metadata_schema(),
            "monthly_budget_jpy": {
                "type": ["integer", "null"],
                "minimum": 0,
            },
            "per_job_budget_jpy": integer_schema(),
            "status": enum_schema(ROUTE_STATES),
            "effective_from": timestamp_schema(nullable=True),
            "effective_to": timestamp_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "route_code",
            "version_no",
            "task_definition_id",
            "primary_model_id",
            "fallback_model_id",
            "route_config",
            "monthly_budget_jpy",
            "per_job_budget_jpy",
            "status",
            "effective_from",
            "effective_to",
            "approved_by_principal_id",
            *audit_fields,
        ),
    )
    definitions["evaluation-suite.v1.schema.json"] = strict_schema(
        schema_id="evaluation-suite",
        title="Evaluation Suite",
        properties={
            "id": uuid_schema(),
            "suite_code": text_schema(max_length=200),
            "version_no": integer_schema(minimum=1),
            "task_definition_id": uuid_schema(),
            "risk_level": enum_schema(("LOW", "MEDIUM", "HIGH", "CRITICAL")),
            "rubric_artifact_id": uuid_schema(nullable=True),
            "suite_config": metadata_schema(),
            "status": enum_schema(("DRAFT", "LOCKED", "ACTIVE", "RETIRED")),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "suite_code",
            "version_no",
            "task_definition_id",
            "risk_level",
            "rubric_artifact_id",
            "suite_config",
            "status",
            "approved_by_principal_id",
            "approved_at",
            *audit_fields,
        ),
    )
    definitions["evaluation-dataset-version.v1.schema.json"] = strict_schema(
        schema_id="evaluation-dataset-version",
        title="Evaluation Dataset Version",
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "dataset_code": text_schema(max_length=200),
            "version_no": integer_schema(minimum=1),
            "purpose": text_schema(max_length=2000),
            "split_policy": metadata_schema(),
            "dataset_artifact_id": uuid_schema(),
            "dataset_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "case_count": integer_schema(),
            "status": enum_schema(DATASET_STATES),
            "locked_by_principal_id": uuid_schema(nullable=True),
            "locked_at": timestamp_schema(nullable=True),
            "compromised_at": timestamp_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "dataset_code",
            "version_no",
            "purpose",
            "split_policy",
            "dataset_artifact_id",
            "dataset_sha256",
            "case_count",
            "status",
            "locked_by_principal_id",
            "locked_at",
            "compromised_at",
            *audit_fields,
        ),
    )
    definitions["evaluation-case.v1.schema.json"] = strict_schema(
        schema_id="evaluation-case",
        title="Evaluation Case",
        properties={
            "id": uuid_schema(),
            "dataset_version_id": uuid_schema(),
            "case_key": text_schema(max_length=300),
            "task_definition_id": uuid_schema(),
            "split": enum_schema(
                (
                    "BOOTSTRAP",
                    "DEV",
                    "CALIBRATION",
                    "HOLDOUT",
                    "REGRESSION",
                    "ADVERSARIAL",
                    "PRODUCTION_SAMPLE",
                )
            ),
            "category": text_schema(max_length=200),
            "risk_level": enum_schema(("LOW", "MEDIUM", "HIGH", "CRITICAL")),
            "input_artifact_id": uuid_schema(),
            "gold_artifact_id": uuid_schema(nullable=True),
            "expected_disposition": enum_schema(EVALUATION_DISPOSITIONS),
            "tags": {
                "type": "array",
                "items": text_schema(max_length=100),
                "maxItems": 100,
                "uniqueItems": True,
            },
            "metadata": metadata_schema(),
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "dataset_version_id",
            "case_key",
            "task_definition_id",
            "split",
            "category",
            "risk_level",
            "input_artifact_id",
            "gold_artifact_id",
            "expected_disposition",
            "tags",
            "metadata",
            "created_at",
        ),
        classification="CONFIDENTIAL",
    )
    definitions["evaluation-run.v1.schema.json"] = strict_schema(
        schema_id="evaluation-run",
        title="Evaluation Run",
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "suite_id": uuid_schema(),
            "dataset_version_id": uuid_schema(),
            "baseline_evaluation_run_id": uuid_schema(nullable=True),
            "prompt_version_id": uuid_schema(),
            "model_route_version_id": uuid_schema(),
            "resolved_model_id": uuid_schema(),
            "output_schema_version_id": uuid_schema(),
            "policy_bundle_version_id": uuid_schema(),
            "code_git_sha": text_schema(
                min_length=40,
                max_length=64,
                pattern=GIT_SHA_PATTERN,
            ),
            "status": enum_schema(EVALUATION_RUN_STATES),
            "run_manifest_artifact_id": uuid_schema(nullable=True),
            "started_at": timestamp_schema(nullable=True),
            "completed_at": timestamp_schema(nullable=True),
            "created_by_principal_id": uuid_schema(),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "suite_id",
            "dataset_version_id",
            "baseline_evaluation_run_id",
            "prompt_version_id",
            "model_route_version_id",
            "resolved_model_id",
            "output_schema_version_id",
            "policy_bundle_version_id",
            "code_git_sha",
            "status",
            "run_manifest_artifact_id",
            "started_at",
            "completed_at",
            "created_by_principal_id",
            *audit_fields,
        ),
    )
    definitions["evaluation-case-result.v1.schema.json"] = strict_schema(
        schema_id="evaluation-case-result",
        title="Evaluation Case Result",
        properties={
            "id": uuid_schema(),
            "evaluation_run_id": uuid_schema(),
            "evaluation_case_id": uuid_schema(),
            "ai_attempt_id": uuid_schema(nullable=True),
            "output_artifact_id": uuid_schema(nullable=True),
            "status": enum_schema(("PASSED", "FAILED", "QUARANTINED", "INVALID")),
            "disposition": enum_schema(EVALUATION_DISPOSITIONS),
            "zero_tolerance_evidence": zero_tolerance_evidence_schema(),
            "zero_tolerance_evidence_artifact_id": uuid_schema(),
            "zero_tolerance_evidence_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "zero_tolerance_failure_count": {
                **integer_schema(minimum=0, maximum=50),
                "readOnly": True,
                "x-raos-database-generated": True,
            },
            "grader_summary": metadata_schema(),
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "evaluation_run_id",
            "evaluation_case_id",
            "ai_attempt_id",
            "output_artifact_id",
            "status",
            "disposition",
            "zero_tolerance_evidence",
            "zero_tolerance_evidence_artifact_id",
            "zero_tolerance_evidence_sha256",
            "zero_tolerance_failure_count",
            "grader_summary",
            "created_at",
        ),
        classification="CONFIDENTIAL",
    )
    definitions["evaluation-case-result.v1.schema.json"].update(
        {
            "description": (
                "Append-only measured case outcome. The measured disposition, "
                "not EvaluationCase.expected_disposition, selects the evidence "
                "truth table. Only a PASSED result must match the linked "
                "EvaluationCase expected_disposition."
            ),
            "x-raos-disposition-semantics": {
                "value_kind": "MEASURED_OUTCOME",
                "evidence_truth_table_selector": "disposition",
                "expected_disposition_selects_evidence_truth_table": False,
                "expected_disposition_match": {
                    "resource": "EvaluationCaseV1",
                    "field": "expected_disposition",
                    "required_when_status": "PASSED",
                    "required_for_other_statuses": False,
                },
                "evidence_truth_table": {
                    "BLOCK_BEFORE_PROVIDER": {
                        "ai_attempt_id": "MUST_BE_NULL",
                        "output_artifact_id": "MUST_BE_NULL",
                    },
                    "CALL_PROVIDER_AND_PASS": {
                        "ai_attempt_id": "EXACT_BOUND_ATTEMPT_REQUIRED",
                        "attempt_status": ["SUCCEEDED"],
                        "attempt_validation_status": ["PASSED"],
                        "attempt_input_sha256": (
                            "MUST_EQUAL_IMMUTABLE_CASE_INPUT_ARTIFACT_SHA256"
                        ),
                        "provider_request_id": "REQUIRED",
                        "refusal_and_error_fields": "MUST_BE_NULL",
                        "output_artifact": "EXACT_IMMUTABLE_HASHED_AI_OUTPUT",
                    },
                    "CALL_PROVIDER_AND_FLAG": {
                        "ai_attempt_id": "EXACT_BOUND_ATTEMPT_REQUIRED",
                        "attempt_status": ["SUCCEEDED"],
                        "attempt_validation_status": ["PASSED"],
                        "attempt_input_sha256": (
                            "MUST_EQUAL_IMMUTABLE_CASE_INPUT_ARTIFACT_SHA256"
                        ),
                        "provider_request_id": "REQUIRED",
                        "refusal_and_error_fields": "MUST_BE_NULL",
                        "output_artifact": "EXACT_IMMUTABLE_HASHED_AI_OUTPUT",
                    },
                    "EXPECTED_REFUSAL": {
                        "ai_attempt_id": "EXACT_BOUND_ATTEMPT_REQUIRED",
                        "attempt_status": ["REFUSED"],
                        "attempt_validation_status": ["FAILED"],
                        "attempt_input_sha256": (
                            "MUST_EQUAL_IMMUTABLE_CASE_INPUT_ARTIFACT_SHA256"
                        ),
                        "provider_request_id": "REQUIRED",
                        "refusal_code": "REQUIRED",
                        "error_fields": "MUST_BE_NULL",
                        "output_artifact_id": "MUST_BE_NULL",
                    },
                    "EXPECTED_TERMINAL_FAILURE": {
                        "ai_attempt_id": "EXACT_BOUND_ATTEMPT_REQUIRED",
                        "attempt_status": ["FAILED", "TIMED_OUT", "CANCELLED"],
                        "attempt_validation_status": ["FAILED"],
                        "attempt_input_sha256": (
                            "MUST_EQUAL_IMMUTABLE_CASE_INPUT_ARTIFACT_SHA256"
                        ),
                        "refusal_code": "MUST_BE_NULL",
                        "error_class_and_code": "REQUIRED",
                        "output_artifact_id": "MUST_BE_NULL",
                    },
                },
                "attempt_provenance": (
                    "MUST_MATCH_EVALUATION_CASE_AND_RUN_SNAPSHOT"
                ),
            },
            "x-raos-zero-tolerance-evidence-invariants": (
                zero_tolerance_evidence_invariants()
            ),
            "x-raos-writer-excluded-fields": [
                "zero_tolerance_failure_count"
            ],
            "allOf": [
                {
                    "if": {
                        "properties": {"status": {"const": "PASSED"}},
                        "required": ["status"],
                    },
                    "then": {
                        "properties": {
                            "zero_tolerance_failure_count": {"const": 0}
                        },
                        "required": ["zero_tolerance_failure_count"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "disposition": {"const": "BLOCK_BEFORE_PROVIDER"}
                        },
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "ai_attempt_id": {"type": "null"},
                            "output_artifact_id": {"type": "null"},
                        },
                        "required": ["ai_attempt_id", "output_artifact_id"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "disposition": {
                                "enum": [
                                    "CALL_PROVIDER_AND_PASS",
                                    "CALL_PROVIDER_AND_FLAG",
                                ]
                            }
                        },
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "ai_attempt_id": uuid_schema(),
                            "output_artifact_id": uuid_schema(),
                        },
                        "required": ["ai_attempt_id", "output_artifact_id"],
                    },
                },
                {
                    "if": {
                        "properties": {
                            "disposition": {
                                "enum": [
                                    "EXPECTED_REFUSAL",
                                    "EXPECTED_TERMINAL_FAILURE",
                                ]
                            }
                        },
                        "required": ["disposition"],
                    },
                    "then": {
                        "properties": {
                            "ai_attempt_id": uuid_schema(),
                            "output_artifact_id": {"type": "null"},
                        },
                        "required": ["ai_attempt_id", "output_artifact_id"],
                    },
                },
            ],
        }
    )
    for name in (
        "evaluation-case.v1.schema.json",
        "evaluation-case-result.v1.schema.json",
    ):
        definitions[name]["x-raos-evidence-uniqueness-invariants"] = (
            evaluation_evidence_uniqueness_invariants()
        )
    for name in (
        "evaluation-suite.v1.schema.json",
        "evaluation-dataset-version.v1.schema.json",
        "evaluation-case.v1.schema.json",
    ):
        definitions[name]["x-raos-required-split-coverage-invariants"] = (
            evaluation_required_split_coverage_invariants()
        )
    definitions["human-evaluation.v1.schema.json"] = strict_schema(
        schema_id="human-evaluation",
        title="Human Evaluation",
        properties={
            "id": uuid_schema(),
            "evaluation_case_result_id": uuid_schema(),
            "reviewer_principal_id": uuid_schema(),
            "rubric_version": text_schema(max_length=100),
            "blind_assignment_key": text_schema(max_length=200),
            "scores": {
                "type": "object",
                "additionalProperties": {"type": "number"},
                "maxProperties": 100,
            },
            "decision": enum_schema(
                ("PASS", "FAIL", "NEEDS_ADJUDICATION", "INVALID")
            ),
            "notes_artifact_id": uuid_schema(nullable=True),
            "is_adjudication": {"type": "boolean"},
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "evaluation_case_result_id",
            "reviewer_principal_id",
            "rubric_version",
            "blind_assignment_key",
            "scores",
            "decision",
            "notes_artifact_id",
            "is_adjudication",
            "created_at",
        ),
        classification="CONFIDENTIAL",
    )
    definitions["judge-calibration.v1.schema.json"] = strict_schema(
        schema_id="judge-calibration",
        title="Judge Calibration",
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "evaluated_task_definition_id": uuid_schema(),
            "judge_route_version_id": uuid_schema(),
            "judge_prompt_version_id": uuid_schema(),
            "resolved_judge_model_id": uuid_schema(),
            "dataset_version_id": uuid_schema(),
            "rubric_artifact_id": uuid_schema(),
            "rubric_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "grader_version": text_schema(max_length=200),
            "weighted_kappa": {"type": ["number", "null"], "minimum": -1, "maximum": 1},
            "zero_tolerance_false_pass_rate": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 1,
            },
            "zero_tolerance_false_fail_rate": {
                "type": ["number", "null"],
                "minimum": 0,
                "maximum": 1,
            },
            "case_count": integer_schema(),
            "status": enum_schema(("DRAFT", "PASSED", "FAILED", "EXPIRED", "RETIRED")),
            "report_artifact_id": uuid_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "expires_at": timestamp_schema(nullable=True),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "evaluated_task_definition_id",
            "judge_route_version_id",
            "judge_prompt_version_id",
            "resolved_judge_model_id",
            "dataset_version_id",
            "rubric_artifact_id",
            "rubric_sha256",
            "grader_version",
            "weighted_kappa",
            "zero_tolerance_false_pass_rate",
            "zero_tolerance_false_fail_rate",
            "case_count",
            "status",
            "report_artifact_id",
            "approved_by_principal_id",
            "approved_at",
            "expires_at",
            *audit_fields,
        ),
    )
    definitions["release-decision.v1.schema.json"] = strict_schema(
        schema_id="release-decision",
        title="Release Decision",
        description=(
            "Hash-bound human release decision. Approval and revocation are "
            "human-authorized actions; AI output cannot perform them."
        ),
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "task_definition_id": uuid_schema(),
            "prompt_version_id": uuid_schema(),
            "model_route_version_id": uuid_schema(),
            "resolved_model_id": uuid_schema(),
            "policy_bundle_version_id": uuid_schema(),
            "dataset_version_id": uuid_schema(),
            "output_schema_version_id": uuid_schema(),
            "evaluation_run_id": uuid_schema(),
            "judge_calibration_id": uuid_schema(nullable=True),
            "code_git_sha": text_schema(
                min_length=40,
                max_length=64,
                pattern=GIT_SHA_PATTERN,
            ),
            "release_scope": enum_schema(("SHADOW", "CANARY", "ACTIVE")),
            "status": enum_schema(RELEASE_STATES),
            "maximum_canary_percent": integer_schema(minimum=0, maximum=100),
            "decision_manifest_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "rollback_release_decision_id": uuid_schema(nullable=True),
            "rollback_strategy": enum_schema(
                ("PREVIOUS_RELEASE", "DISABLE_ROUTE")
            ),
            "rollback_runbook_artifact_id": uuid_schema(nullable=True),
            "rollback_runbook_sha256": text_schema(
                nullable=True,
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "canary_monitoring_artifact_id": uuid_schema(nullable=True),
            "canary_monitoring_sha256": text_schema(
                nullable=True,
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "canary_evidence_artifact_id": uuid_schema(nullable=True),
            "canary_evidence_sha256": text_schema(
                nullable=True,
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "canary_started_at": timestamp_schema(nullable=True),
            "canary_completed_at": timestamp_schema(nullable=True),
            "canary_started_txid": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "canary_completed_txid": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "canary_approval_id": uuid_schema(nullable=True),
            "active_approval_id": uuid_schema(nullable=True),
            "approved_by_principal_id": uuid_schema(nullable=True),
            "second_approver_principal_id": uuid_schema(nullable=True),
            "approved_at": timestamp_schema(nullable=True),
            "revoked_by_principal_id": uuid_schema(nullable=True),
            "revoked_at": timestamp_schema(nullable=True),
            "revocation_reason": text_schema(nullable=True, max_length=1000),
            **audit_fields,
        },
        required=(
            "id",
            "display_id",
            "task_definition_id",
            "prompt_version_id",
            "model_route_version_id",
            "resolved_model_id",
            "policy_bundle_version_id",
            "dataset_version_id",
            "output_schema_version_id",
            "evaluation_run_id",
            "judge_calibration_id",
            "code_git_sha",
            "release_scope",
            "status",
            "maximum_canary_percent",
            "decision_manifest_sha256",
            "rollback_release_decision_id",
            "rollback_strategy",
            "rollback_runbook_artifact_id",
            "rollback_runbook_sha256",
            "canary_monitoring_artifact_id",
            "canary_monitoring_sha256",
            "canary_evidence_artifact_id",
            "canary_evidence_sha256",
            "canary_started_at",
            "canary_completed_at",
            "canary_started_txid",
            "canary_completed_txid",
            "canary_approval_id",
            "active_approval_id",
            "approved_by_principal_id",
            "second_approver_principal_id",
            "approved_at",
            "revoked_by_principal_id",
            "revoked_at",
            "revocation_reason",
            *audit_fields,
        ),
    )
    definitions["release-approval.v1.schema.json"] = strict_schema(
        schema_id="release-approval",
        title="Release Approval",
        description=(
            "Append-only, phase-specific human approval evidence. Principal "
            "identifiers and signed approval artifacts are CONFIDENTIAL and "
            "must never be projected to public or lifecycle event payloads."
        ),
        properties={
            "id": uuid_schema(),
            "display_id": text_schema(max_length=64),
            "release_decision_id": uuid_schema(),
            "phase": enum_schema(("CANARY", "ACTIVE")),
            "decision_manifest_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "primary_approver_principal_id": uuid_schema(),
            "primary_approver_role": {"type": "string", "const": "APPROVER"},
            "second_approver_principal_id": uuid_schema(),
            "second_approver_role": {"type": "string", "const": "OWNER"},
            "approval_artifact_id": uuid_schema(),
            "approval_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
            "signed_at": timestamp_schema(),
            "created_at": timestamp_schema(),
        },
        required=(
            "id",
            "display_id",
            "release_decision_id",
            "phase",
            "decision_manifest_sha256",
            "primary_approver_principal_id",
            "primary_approver_role",
            "second_approver_principal_id",
            "second_approver_role",
            "approval_artifact_id",
            "approval_sha256",
            "signed_at",
            "created_at",
        ),
        classification="CONFIDENTIAL",
    )
    definitions["release-approval.v1.schema.json"].update(
        {
            "x-raos-append-only": True,
            "x-raos-human-only": True,
            "x-raos-constraints": [
                "primary_and_second_principals_must_be_distinct",
                "prompt_author_cannot_be_primary_or_second_approver",
                "ai_and_worker_principals_are_forbidden",
                "manifest_and_approval_artifact_hashes_are_immutable",
                (
                    "active_phase_manifest_artifact_and_hash_must_differ_from_"
                    "canary_phase"
                ),
            ],
        }
    )
    definitions["release-decision-approval-result.v1.schema.json"] = strict_schema(
        schema_id="release-decision-approval-result",
        title="Release Decision Approval Result",
        description=(
            "Atomic transition result containing the updated aggregate and "
            "the append-only approval row created for that exact manifest."
        ),
        properties={
            "release_decision": {"$ref": "release-decision.v1.schema.json"},
            "release_approval": {"$ref": "release-approval.v1.schema.json"},
        },
        required=("release_decision", "release_approval"),
        classification="CONFIDENTIAL",
    )
    evaluation_suite = definitions["evaluation-suite.v1.schema.json"]
    evaluation_suite["allOf"] = [
        {
            "if": {
                "properties": {
                    "status": {"enum": ["LOCKED", "ACTIVE"]},
                },
                "required": ["status"],
            },
            "then": {
                "properties": {"suite_config": suite_config_schema()},
                "required": ["suite_config"],
            },
        }
    ]
    calibration = definitions["judge-calibration.v1.schema.json"]
    calibration["allOf"] = [
        {
            "if": {
                "properties": {"status": {"const": "PASSED"}},
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "weighted_kappa": {
                        "type": "number",
                        "minimum": 0.70,
                        "maximum": 1,
                    },
                    "zero_tolerance_false_pass_rate": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 0.01,
                    },
                    "zero_tolerance_false_fail_rate": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 0.05,
                    },
                    "case_count": integer_schema(minimum=200),
                    "report_artifact_id": uuid_schema(),
                    "approved_by_principal_id": uuid_schema(),
                    "approved_at": timestamp_schema(),
                    "expires_at": timestamp_schema(),
                },
                "required": [
                    "weighted_kappa",
                    "zero_tolerance_false_pass_rate",
                    "zero_tolerance_false_fail_rate",
                    "case_count",
                    "report_artifact_id",
                    "approved_by_principal_id",
                    "approved_at",
                    "expires_at",
                ],
            },
        }
    ]
    calibration["x-raos-judge-calibration-scope-invariants"] = (
        judge_calibration_scope_invariants()
    )
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-judge-calibration-scope-invariants"
    ] = judge_calibration_scope_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-component-content-snapshot-freeze"
    ] = evaluation_run_component_snapshot_freeze_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-policy-rule-graph-invariants"
    ] = policy_rule_graph_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-completion-evidence-invariants"
    ] = evaluation_run_completion_evidence_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-baseline-evaluation-run-invariants"
    ] = evaluation_baseline_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-statistical-evidence-artifact-invariants"
    ] = evaluation_statistics_artifact_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-blocking-aggregate-scope-invariants"
    ] = evaluation_blocking_aggregate_scope_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-required-split-coverage-invariants"
    ] = evaluation_required_split_coverage_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-cost-latency-reporting-completeness-invariants"
    ] = cost_latency_reporting_completeness_invariants()
    definitions["evaluation-run.v1.schema.json"][
        "x-raos-completion-execution-security-invariants"
    ] = evaluation_completion_execution_security_invariants()
    release = definitions["release-decision.v1.schema.json"]
    release["x-raos-baseline-evaluation-run-invariants"] = (
        evaluation_baseline_invariants()
    )
    release["x-raos-release-regression-invariants"] = (
        release_regression_invariants()
    )
    release["x-raos-statistical-evidence-artifact-invariants"] = (
        evaluation_statistics_artifact_invariants()
    )
    release["x-raos-blocking-aggregate-scope-invariants"] = (
        evaluation_blocking_aggregate_scope_invariants()
    )
    release["x-raos-canary-safety-invariants"] = (
        release_canary_safety_invariants()
    )
    release["allOf"] = [
        *rollback_strategy_conditions(),
        nullable_artifact_hash_pair_condition(
            artifact_field="canary_monitoring_artifact_id",
            hash_field="canary_monitoring_sha256",
        ),
        nullable_artifact_hash_pair_condition(
            artifact_field="canary_evidence_artifact_id",
            hash_field="canary_evidence_sha256",
        ),
        {
            "if": {
                "properties": {
                    "canary_evidence_artifact_id": {"type": "string"},
                },
                "required": ["canary_evidence_artifact_id"],
            },
            "then": {
                "properties": {
                    "canary_completed_at": timestamp_schema(),
                    "canary_completed_txid": integer_schema(minimum=1),
                },
                "required": [
                    "canary_completed_at",
                    "canary_completed_txid",
                ],
            },
        },
        {
            "if": {
                "properties": {"status": {"const": "READY_FOR_REVIEW"}},
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "canary_approval_id": {"type": "null"},
                    "active_approval_id": {"type": "null"},
                    "approved_by_principal_id": {"type": "null"},
                    "second_approver_principal_id": {"type": "null"},
                    "approved_at": {"type": "null"},
                    "canary_evidence_artifact_id": {"type": "null"},
                    "canary_evidence_sha256": {"type": "null"},
                    "canary_completed_at": {"type": "null"},
                    "canary_completed_txid": {"type": "null"},
                },
                "required": [
                    "canary_approval_id",
                    "active_approval_id",
                    "approved_by_principal_id",
                    "second_approver_principal_id",
                    "approved_at",
                    "canary_evidence_artifact_id",
                    "canary_evidence_sha256",
                    "canary_completed_at",
                    "canary_completed_txid",
                ],
            },
        },
        {
            "if": {
                "properties": {
                    "status": {
                        "enum": ["APPROVED_CANARY", "APPROVED_ACTIVE"]
                    }
                },
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "canary_monitoring_artifact_id": uuid_schema(),
                    "canary_monitoring_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_started_at": timestamp_schema(),
                    "canary_started_txid": integer_schema(),
                    "canary_approval_id": uuid_schema(),
                },
                "required": [
                    "canary_monitoring_artifact_id",
                    "canary_monitoring_sha256",
                    "canary_started_at",
                    "canary_started_txid",
                    "canary_approval_id",
                ],
            },
        },
        {
            "if": {
                "properties": {"status": {"const": "APPROVED_ACTIVE"}},
                "required": ["status"],
            },
            "then": {
                "properties": {
                    "canary_evidence_artifact_id": uuid_schema(),
                    "canary_evidence_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_started_at": timestamp_schema(),
                    "canary_completed_at": timestamp_schema(),
                    "canary_completed_txid": integer_schema(minimum=1),
                    "canary_approval_id": uuid_schema(),
                    "active_approval_id": uuid_schema(),
                },
                "required": [
                    "canary_evidence_artifact_id",
                    "canary_evidence_sha256",
                    "canary_started_at",
                    "canary_completed_at",
                    "canary_completed_txid",
                    "canary_approval_id",
                    "active_approval_id",
                ],
            },
        },
    ]
    release["x-raos-server-owned-fields"] = [
        "canary_started_at",
        "canary_started_txid",
        "canary_completed_at",
        "canary_completed_txid",
        "canary_approval_id",
        "active_approval_id",
    ]
    release["x-raos-transaction-invariants"] = [
        "canary_completed_txid_must_differ_from_canary_started_txid",
        "canary_checkpoint_must_be_persisted_before_active_approval_transaction",
        "canary_completed_txid_must_precede_active_approval_transaction",
    ]
    release["x-raos-previous-release-rollback-target-invariants"] = (
        previous_release_rollback_target_invariants()
    )
    definitions["ai-task-contract.v1.schema.json"] = strict_schema(
        schema_id="ai-task-contract",
        title="AI Task Contract",
        properties={
            "task": {"$ref": "ai-task-definition.v1.schema.json"},
            "active_prompt_versions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "locale": text_schema(
                            min_length=2,
                            max_length=16,
                            pattern="^[a-z]{2,3}(-[A-Z]{2})?$",
                        ),
                        "prompt_version_id": uuid_schema(),
                    },
                    "required": ["locale", "prompt_version_id"],
                },
                "maxItems": 100,
            },
            "active_output_schema_version_id": uuid_schema(),
            "active_model_route_version_id": uuid_schema(),
            "active_release_decision_id": uuid_schema(nullable=True),
        },
        required=(
            "task",
            "active_prompt_versions",
            "active_output_schema_version_id",
            "active_model_route_version_id",
            "active_release_decision_id",
        ),
    )
    definitions["evaluation-run-detail.v1.schema.json"] = strict_schema(
        schema_id="evaluation-run-detail",
        title="Evaluation Run Detail",
        properties={
            "run": {"$ref": "evaluation-run.v1.schema.json"},
            "case_result_summary": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "total": integer_schema(),
                    "passed": integer_schema(),
                    "failed": integer_schema(),
                    "quarantined": integer_schema(),
                    "invalid": integer_schema(),
                    "zero_tolerance_failure_count": integer_schema(),
                },
                "required": [
                    "total",
                    "passed",
                    "failed",
                    "quarantined",
                    "invalid",
                    "zero_tolerance_failure_count",
                ],
            },
            "slice_metrics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "slice_key": text_schema(max_length=200),
                        "split": enum_schema(REQUIRED_EVALUATION_SPLITS),
                        "scope_kind": enum_schema(("ALL", "CATEGORY")),
                        "scope_key": text_schema(
                            nullable=True,
                            max_length=200,
                        ),
                        "metric_code": text_schema(max_length=200),
                        "metric_value": {"type": "number"},
                        "threshold_operator": {
                            "type": ["string", "null"],
                            "enum": [">=", ">", "<=", "<", "==", "!=", None],
                        },
                        "threshold_value": {"type": ["number", "null"]},
                        "passed": {"type": ["boolean", "null"]},
                        "proportion_numerator_count": {
                            "type": ["integer", "null"],
                            "minimum": 0,
                        },
                        "proportion_denominator_count": {
                            "type": ["integer", "null"],
                            "minimum": 1,
                        },
                        "evaluation_result_ids": {
                            "type": "array",
                            "items": uuid_schema(),
                            "maxItems": 10000,
                        },
                    },
                    "required": [
                        "slice_key",
                        "split",
                        "scope_kind",
                        "scope_key",
                        "metric_code",
                        "metric_value",
                        "threshold_operator",
                        "threshold_value",
                        "passed",
                        "proportion_numerator_count",
                        "proportion_denominator_count",
                        "evaluation_result_ids",
                    ],
                    "allOf": [
                        {
                            "if": {
                                "properties": {
                                    "scope_kind": {"const": "ALL"}
                                },
                                "required": ["scope_kind"],
                            },
                            "then": {
                                "properties": {"scope_key": {"type": "null"}}
                            },
                            "else": {
                                "properties": {
                                    "scope_key": text_schema(max_length=200)
                                }
                            },
                        },
                        {
                            "if": {
                                "properties": {
                                    "metric_code": {
                                        "enum": list(RATIO_METRIC_CODES)
                                    }
                                },
                                "required": ["metric_code"],
                            },
                            "then": {
                                "properties": {
                                    "proportion_numerator_count": (
                                        integer_schema(minimum=0)
                                    ),
                                    "proportion_denominator_count": (
                                        integer_schema(minimum=1)
                                    ),
                                },
                                "x-raos-field-comparison": (
                                    "proportion_numerator_count <= "
                                    "proportion_denominator_count"
                                ),
                            },
                            "else": {
                                "properties": {
                                    "proportion_numerator_count": {
                                        "type": "null"
                                    },
                                    "proportion_denominator_count": {
                                        "type": "null"
                                    },
                                }
                            },
                        },
                    ],
                    "x-raos-scope-identity": {
                        "fields": ["split", "scope_kind", "scope_key"],
                        "category_name_cannot_collide_with_split": True,
                    },
                    "x-raos-ratio-scope-aggregation": (
                        "SUM_NUMERATOR_DIVIDED_BY_SUM_DENOMINATOR"
                    ),
                    "x-raos-cost-latency-threshold-semantics": (
                        cost_latency_reporting_completeness_invariants()[
                            "canonical_suite_threshold_semantics"
                        ]
                    ),
                },
                "maxItems": 1000,
            },
            "artifact_refs": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "run_manifest_artifact_id": uuid_schema(nullable=True),
                    "report_artifact_id": uuid_schema(nullable=True),
                    "result_artifact_ids": {
                        "type": "array",
                        "items": uuid_schema(),
                        "maxItems": 10000,
                        "uniqueItems": True,
                    },
                },
                "required": [
                    "run_manifest_artifact_id",
                    "report_artifact_id",
                    "result_artifact_ids",
                ],
            },
        },
        required=("run", "case_result_summary", "slice_metrics", "artifact_refs"),
        classification="CONFIDENTIAL",
        description=(
            "Metadata-only run projection. Raw inputs, outputs, holdout content, "
            "prompt bodies, and human review notes are forbidden."
        ),
    )
    definitions["evaluation-run-detail.v1.schema.json"][
        "x-raos-baseline-evaluation-run-invariants"
    ] = evaluation_baseline_invariants()
    definitions["evaluation-run-detail.v1.schema.json"][
        "x-raos-statistical-evidence-artifact-invariants"
    ] = evaluation_statistics_artifact_invariants()
    definitions["evaluation-run-detail.v1.schema.json"][
        "x-raos-blocking-aggregate-scope-invariants"
    ] = evaluation_blocking_aggregate_scope_invariants()
    definitions["evaluation-run-detail.v1.schema.json"][
        "x-raos-required-split-coverage-invariants"
    ] = evaluation_required_split_coverage_invariants()
    definitions["evaluation-run-detail.v1.schema.json"][
        "x-raos-cost-latency-reporting-completeness-invariants"
    ] = cost_latency_reporting_completeness_invariants()
    for filename, schema in definitions.items():
        if filename not in {
            "ai-task-definition.v1.schema.json",
            "ai-task-contract.v1.schema.json",
        }:
            schema["x-raos-classification"] = "CONFIDENTIAL"
    return definitions


def request_schema_definitions(
    resources: Mapping[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    def from_resource(
        filename: str,
        *,
        title: str,
        fields: Iterable[str],
        required: Iterable[str] | None = None,
        classification: str | None = None,
    ) -> dict[str, Any]:
        field_list = list(fields)
        properties = resources[filename]["properties"]
        return strict_schema(
            schema_id=title.lower().replace(" ", "-"),
            title=title,
            properties={name: properties[name] for name in field_list},
            required=field_list if required is None else required,
            classification=(
                resources[filename]["x-raos-classification"]
                if classification is None
                else classification
            ),
        )

    definitions = {
        "prompt-version-create-request.v1.schema.json": from_resource(
            "prompt-version.v1.schema.json",
            title="Prompt Version Create Request",
            fields=(
                "task_definition_id",
                "prompt_code",
                "version_no",
                "locale",
                "git_path",
                "git_commit_sha",
                "template_sha256",
                "compiler_version",
                "input_contract_sha256",
            ),
        ),
        "model-route-version-create-request.v1.schema.json": strict_schema(
            schema_id="model-route-version-create-request",
            title="Model Route Version Create Request",
            properties={
                **{
                    field: resources["model-route-version.v1.schema.json"][
                        "properties"
                    ][field]
                    for field in (
                        "route_code",
                        "version_no",
                        "task_definition_id",
                        "primary_model_id",
                        "fallback_model_id",
                        "monthly_budget_jpy",
                        "per_job_budget_jpy",
                    )
                },
                "route_config": route_config_schema(),
            },
            required=(
                "route_code",
                "version_no",
                "task_definition_id",
                "primary_model_id",
                "fallback_model_id",
                "route_config",
                "monthly_budget_jpy",
                "per_job_budget_jpy",
            ),
            classification="CONFIDENTIAL",
        ),
        "evaluation-dataset-create-request.v1.schema.json": strict_schema(
            schema_id="evaluation-dataset-create-request",
            title="Evaluation Dataset Create Request",
            properties={
                **{
                    field: resources[
                        "evaluation-dataset-version.v1.schema.json"
                    ]["properties"][field]
                    for field in (
                        "dataset_code",
                        "version_no",
                        "purpose",
                        "dataset_artifact_id",
                        "dataset_sha256",
                        "case_count",
                    )
                },
                "split_policy": split_policy_schema(),
            },
            required=(
                "dataset_code",
                "version_no",
                "purpose",
                "split_policy",
                "dataset_artifact_id",
                "dataset_sha256",
                "case_count",
            ),
            classification="CONFIDENTIAL",
        ),
        "evaluation-run-create-request.v1.schema.json": from_resource(
            "evaluation-run.v1.schema.json",
            title="Evaluation Run Create Request",
            fields=(
                "suite_id",
                "dataset_version_id",
                "baseline_evaluation_run_id",
                "prompt_version_id",
                "model_route_version_id",
                "resolved_model_id",
                "output_schema_version_id",
                "policy_bundle_version_id",
                "code_git_sha",
            ),
            required=(
                "suite_id",
                "dataset_version_id",
                "prompt_version_id",
                "model_route_version_id",
                "resolved_model_id",
                "output_schema_version_id",
                "policy_bundle_version_id",
                "code_git_sha",
            ),
        ),
        "human-evaluation-create-request.v1.schema.json": from_resource(
            "human-evaluation.v1.schema.json",
            title="Human Evaluation Create Request",
            fields=(
                "rubric_version",
                "blind_assignment_key",
                "scores",
                "decision",
                "notes_artifact_id",
                "is_adjudication",
            ),
            classification="CONFIDENTIAL",
        ),
        "judge-calibration-create-request.v1.schema.json": strict_schema(
            schema_id="judge-calibration-create-request",
            title="Judge Calibration Create Request",
            properties={
                "evaluated_task_definition_id": uuid_schema(),
                "judge_route_version_id": uuid_schema(),
                "judge_prompt_version_id": uuid_schema(),
                "resolved_judge_model_id": uuid_schema(),
                "dataset_version_id": uuid_schema(),
                "rubric_artifact_id": uuid_schema(),
                "rubric_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "grader_version": text_schema(max_length=200),
            },
            required=(
                "evaluated_task_definition_id",
                "judge_route_version_id",
                "judge_prompt_version_id",
                "resolved_judge_model_id",
                "dataset_version_id",
                "rubric_artifact_id",
                "rubric_sha256",
                "grader_version",
            ),
            classification="CONFIDENTIAL",
        ),
        "release-decision-create-request.v1.schema.json": from_resource(
            "release-decision.v1.schema.json",
            title="Release Decision Create Request",
            fields=(
                "task_definition_id",
                "prompt_version_id",
                "model_route_version_id",
                "resolved_model_id",
                "policy_bundle_version_id",
                "dataset_version_id",
                "output_schema_version_id",
                "evaluation_run_id",
                "judge_calibration_id",
                "code_git_sha",
                "release_scope",
                "maximum_canary_percent",
                "decision_manifest_sha256",
                "rollback_release_decision_id",
                "rollback_strategy",
                "rollback_runbook_artifact_id",
                "rollback_runbook_sha256",
                "canary_monitoring_artifact_id",
                "canary_monitoring_sha256",
            ),
        ),
        "release-canary-approval-request.v1.schema.json": strict_schema(
            schema_id="release-canary-approval-request",
            title="Release Canary Approval Request",
            properties={
                "decision_manifest_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "primary_approver_principal_id": uuid_schema(),
                "primary_approver_role": {
                    "type": "string",
                    "const": "APPROVER",
                },
                "second_approver_principal_id": uuid_schema(),
                "second_approver_role": {"type": "string", "const": "OWNER"},
                "approval_artifact_id": uuid_schema(),
                "approval_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "signed_at": timestamp_schema(),
            },
            required=(
                "decision_manifest_sha256",
                "primary_approver_principal_id",
                "primary_approver_role",
                "second_approver_principal_id",
                "second_approver_role",
                "approval_artifact_id",
                "approval_sha256",
                "signed_at",
            ),
            classification="CONFIDENTIAL",
        ),
        "release-active-approval-request.v1.schema.json": strict_schema(
            schema_id="release-active-approval-request",
            title="Release Active Approval Request",
            properties={
                "decision_manifest_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "primary_approver_principal_id": uuid_schema(),
                "primary_approver_role": {
                    "type": "string",
                    "const": "APPROVER",
                },
                "second_approver_principal_id": uuid_schema(),
                "second_approver_role": {"type": "string", "const": "OWNER"},
                "approval_artifact_id": uuid_schema(),
                "approval_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "signed_at": timestamp_schema(),
                "canary_evidence_artifact_id": uuid_schema(),
                "canary_evidence_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
                "canary_monitoring_artifact_id": uuid_schema(),
                "canary_monitoring_sha256": text_schema(
                    min_length=64,
                    max_length=64,
                    pattern=SHA256_PATTERN,
                ),
            },
            required=(
                "decision_manifest_sha256",
                "primary_approver_principal_id",
                "primary_approver_role",
                "second_approver_principal_id",
                "second_approver_role",
                "approval_artifact_id",
                "approval_sha256",
                "signed_at",
                "canary_evidence_artifact_id",
                "canary_evidence_sha256",
                "canary_monitoring_artifact_id",
                "canary_monitoring_sha256",
            ),
            classification="CONFIDENTIAL",
        ),
        "release-decision-revoke-request.v1.schema.json": strict_schema(
            schema_id="release-decision-revoke-request",
            title="Release Decision Revoke Request",
            properties={"reason_code": text_schema(max_length=100)},
            required=("reason_code",),
            classification="CONFIDENTIAL",
        ),
    }
    prompt_request = definitions[
        "prompt-version-create-request.v1.schema.json"
    ]["properties"]
    prompt_request["compiler_version"] = text_schema(max_length=100)
    prompt_request["input_contract_sha256"] = text_schema(
        min_length=64,
        max_length=64,
        pattern=SHA256_PATTERN,
    )
    release_create = definitions[
        "release-decision-create-request.v1.schema.json"
    ]
    release_create["properties"].update(
        {
            "release_scope": {
                "type": "string",
                "const": "CANARY",
            },
            "maximum_canary_percent": integer_schema(minimum=1, maximum=100),
            "canary_monitoring_artifact_id": uuid_schema(),
            "canary_monitoring_sha256": text_schema(
                min_length=64,
                max_length=64,
                pattern=SHA256_PATTERN,
            ),
        }
    )
    release_create["allOf"] = rollback_strategy_conditions()
    for name in (
        "release-canary-approval-request.v1.schema.json",
        "release-active-approval-request.v1.schema.json",
    ):
        definitions[name].update(
            {
                "x-raos-human-only": True,
                "x-raos-constraints": [
                    "primary_principal_must_equal_authenticated_user",
                    "primary_and_second_principals_must_be_distinct",
                    "prompt_author_cannot_be_primary_or_second_approver",
                    "ai_and_worker_principals_are_forbidden",
                ],
            }
        )
    for name in (
        "release-canary-approval-request.v1.schema.json",
        "release-active-approval-request.v1.schema.json",
        "release-decision-revoke-request.v1.schema.json",
    ):
        definitions[name][
            "x-raos-previous-release-rollback-target-invariants"
        ] = previous_release_rollback_target_invariants()
    definitions[
        "release-canary-approval-request.v1.schema.json"
    ]["description"] = (
        "Creates the append-only CANARY approval. Neither approver may be the "
        "bound Prompt Version author."
    )
    active_approval_request = definitions[
        "release-active-approval-request.v1.schema.json"
    ]
    active_approval_request["description"] = (
        "Creates a distinct append-only ACTIVE approval after a canary "
        "monitoring checkpoint was persisted in a prior transaction. The "
        "request's canary monitoring and evidence artifact/hash fields must "
        "exactly match that immutable checkpoint; the ACTIVE approval "
        "transaction cannot create or alter them. Neither approver may be the "
        "bound Prompt Version author. The ACTIVE manifest, approval artifact, "
        "and approval artifact hash must each differ from the CANARY approval."
    )
    active_approval_request["x-raos-cross-phase-binding"] = {
        "compared_with": "CANARY ReleaseApprovalV1",
        "must_differ": [
            "decision_manifest_sha256",
            "approval_artifact_id",
            "approval_sha256",
        ],
    }
    active_approval_request["x-raos-server-owned-excluded-fields"] = [
        "canary_started_at",
        "canary_started_txid",
        "canary_completed_at",
        "canary_completed_txid",
    ]
    active_approval_request["x-raos-prior-canary-checkpoint-binding"] = {
        "resource": "ReleaseDecisionV1",
        "persistence": "PRIOR_TRANSACTION",
        "match": "EXACT",
        "request_fields": [
            "canary_monitoring_artifact_id",
            "canary_monitoring_sha256",
            "canary_evidence_artifact_id",
            "canary_evidence_sha256",
        ],
        "server_owned_fields": [
            "canary_started_at",
            "canary_started_txid",
            "canary_completed_at",
            "canary_completed_txid",
        ],
        "active_approval_may_create_or_update_checkpoint": False,
    }
    active_approval_request["x-raos-transaction-invariants"] = [
        "canary_completed_txid_must_differ_from_canary_started_txid",
        "canary_completed_txid_must_precede_active_approval_transaction",
        "active_approval_request_must_match_prior_persisted_checkpoint",
    ]
    evaluation_run_request = definitions[
        "evaluation-run-create-request.v1.schema.json"
    ]
    evaluation_run_request["x-raos-baseline-evaluation-run-invariants"] = (
        evaluation_baseline_invariants()
    )
    evaluation_run_request["x-raos-required-split-coverage-invariants"] = (
        evaluation_required_split_coverage_invariants()
    )
    evaluation_dataset_request = definitions[
        "evaluation-dataset-create-request.v1.schema.json"
    ]
    evaluation_dataset_request[
        "x-raos-required-split-coverage-invariants"
    ] = evaluation_required_split_coverage_invariants()
    return definitions


def event_schema_definitions() -> dict[str, dict[str, Any]]:
    def event(
        *,
        filename: str,
        event_type: str,
        title: str,
        properties: Mapping[str, Any],
        required: Iterable[str],
    ) -> tuple[str, dict[str, Any]]:
        data = {
            "type": "object",
            "additionalProperties": False,
            "properties": copy.deepcopy(dict(properties)),
            "required": list(required),
        }
        schema_id = f"https://schemas.raos.local/events/{filename}"
        event_version = int(event_type.rsplit(".v", 1)[1])
        constrained_properties = {
            "type": {"const": event_type},
            "producer": {"const": "ai"},
            "classification": {"const": "CONFIDENTIAL"},
            "event_version": {"const": event_version},
            "dataschema": {"const": schema_id},
            "data": data,
        }
        return (
            filename,
            {
                "$schema": SCHEMA_DIALECT,
                "$id": schema_id,
                "title": title,
                "description": (
                    "Internal/confidential metadata event; raw prompts, inputs, "
                    "outputs, source packets, review bodies, secrets, and PII "
                    "are forbidden."
                ),
                "allOf": [
                    {"$ref": "../common/event-envelope.schema.json"},
                    {
                        "type": "object",
                        "properties": constrained_properties,
                        "required": list(constrained_properties),
                    },
                ],
                "x-raos-classification": "CONFIDENTIAL",
            },
        )

    events = dict(
        (
            event(
                filename="jp-raos-ai-evaluation-completed-v2.schema.json",
                event_type="jp.raos.ai.evaluation_completed.v2",
                title="jp.raos.ai.evaluation_completed.v2",
                properties={
                    "evaluation_run_id": uuid_schema(),
                    "suite_id": uuid_schema(),
                    "suite_version": integer_schema(minimum=1),
                    "dataset_version_id": uuid_schema(),
                    "baseline_evaluation_run_id": uuid_schema(nullable=True),
                    "task_definition_id": uuid_schema(),
                    "prompt_version_id": uuid_schema(),
                    "model_route_version_id": uuid_schema(),
                    "resolved_model_id": uuid_schema(),
                    "output_schema_version_id": uuid_schema(),
                    "policy_bundle_version_id": uuid_schema(),
                    "code_git_sha": text_schema(
                        min_length=40,
                        max_length=64,
                        pattern=GIT_SHA_PATTERN,
                    ),
                    "passed": {"type": "boolean"},
                    "result_manifest_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "completed_at": timestamp_schema(),
                },
                required=(
                    "evaluation_run_id",
                    "suite_id",
                    "suite_version",
                    "dataset_version_id",
                    "baseline_evaluation_run_id",
                    "task_definition_id",
                    "prompt_version_id",
                    "model_route_version_id",
                    "resolved_model_id",
                    "output_schema_version_id",
                    "policy_bundle_version_id",
                    "code_git_sha",
                    "passed",
                    "result_manifest_sha256",
                    "completed_at",
                ),
            ),
            event(
                filename="jp-raos-ai-release-decision-approved-v1.schema.json",
                event_type="jp.raos.ai.release_decision_approved.v1",
                title="jp.raos.ai.release_decision_approved.v1",
                properties={
                    "release_decision_id": uuid_schema(),
                    "release_approval_id": uuid_schema(),
                    "task_definition_id": uuid_schema(),
                    "prompt_version_id": uuid_schema(),
                    "model_route_version_id": uuid_schema(),
                    "resolved_model_id": uuid_schema(),
                    "policy_bundle_version_id": uuid_schema(),
                    "dataset_version_id": uuid_schema(),
                    "output_schema_version_id": uuid_schema(),
                    "evaluation_run_id": uuid_schema(),
                    "judge_calibration_id": uuid_schema(nullable=True),
                    "code_git_sha": text_schema(
                        min_length=40,
                        max_length=64,
                        pattern=GIT_SHA_PATTERN,
                    ),
                    "phase": enum_schema(("CANARY", "ACTIVE")),
                    "decision_manifest_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "rollback_strategy": enum_schema(
                        ("PREVIOUS_RELEASE", "DISABLE_ROUTE")
                    ),
                    "rollback_release_decision_id": uuid_schema(nullable=True),
                    "rollback_runbook_artifact_id": uuid_schema(nullable=True),
                    "rollback_runbook_sha256": text_schema(
                        nullable=True,
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_evidence_sha256": text_schema(
                        nullable=True,
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_monitoring_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_started_at": timestamp_schema(),
                    "canary_started_txid": integer_schema(minimum=1),
                    "canary_completed_at": timestamp_schema(nullable=True),
                    "canary_completed_txid": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                    },
                    "approved_at": timestamp_schema(),
                    "aggregate_version": integer_schema(minimum=1),
                },
                required=(
                    "release_decision_id",
                    "release_approval_id",
                    "task_definition_id",
                    "prompt_version_id",
                    "model_route_version_id",
                    "resolved_model_id",
                    "policy_bundle_version_id",
                    "dataset_version_id",
                    "output_schema_version_id",
                    "evaluation_run_id",
                    "judge_calibration_id",
                    "code_git_sha",
                    "phase",
                    "decision_manifest_sha256",
                    "rollback_strategy",
                    "rollback_release_decision_id",
                    "rollback_runbook_artifact_id",
                    "rollback_runbook_sha256",
                    "canary_evidence_sha256",
                    "canary_monitoring_sha256",
                    "canary_started_at",
                    "canary_started_txid",
                    "canary_completed_at",
                    "canary_completed_txid",
                    "approved_at",
                    "aggregate_version",
                ),
            ),
            event(
                filename="jp-raos-ai-release-decision-revoked-v1.schema.json",
                event_type="jp.raos.ai.release_decision_revoked.v1",
                title="jp.raos.ai.release_decision_revoked.v1",
                properties={
                    "release_decision_id": uuid_schema(),
                    "task_definition_id": uuid_schema(),
                    "reason_code": text_schema(max_length=100),
                    "rollback_strategy": enum_schema(
                        ("PREVIOUS_RELEASE", "DISABLE_ROUTE")
                    ),
                    "rollback_release_decision_id": uuid_schema(nullable=True),
                    "rollback_runbook_artifact_id": uuid_schema(nullable=True),
                    "rollback_runbook_sha256": text_schema(
                        nullable=True,
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_completed_txid": {
                        "type": ["integer", "null"],
                        "minimum": 1,
                    },
                    "revoked_at": timestamp_schema(),
                    "aggregate_version": integer_schema(minimum=1),
                },
                required=(
                    "release_decision_id",
                    "task_definition_id",
                    "reason_code",
                    "rollback_strategy",
                    "rollback_release_decision_id",
                    "rollback_runbook_artifact_id",
                    "rollback_runbook_sha256",
                    "canary_completed_txid",
                    "revoked_at",
                    "aggregate_version",
                ),
            ),
        )
    )
    evaluation_completed_data = events[
        "jp-raos-ai-evaluation-completed-v2.schema.json"
    ]["allOf"][1]["properties"]["data"]
    evaluation_completed_data[
        "x-raos-baseline-evaluation-run-invariants"
    ] = evaluation_baseline_invariants()
    evaluation_completed_data[
        "x-raos-statistical-evidence-artifact-invariants"
    ] = evaluation_statistics_artifact_invariants()
    evaluation_completed_data[
        "x-raos-blocking-aggregate-scope-invariants"
    ] = evaluation_blocking_aggregate_scope_invariants()
    evaluation_completed_data[
        "x-raos-required-split-coverage-invariants"
    ] = evaluation_required_split_coverage_invariants()
    evaluation_completed_data[
        "x-raos-cost-latency-reporting-completeness-invariants"
    ] = cost_latency_reporting_completeness_invariants()
    evaluation_completed_data["x-raos-completion-evidence-invariants"] = (
        evaluation_run_completion_evidence_invariants()
    )
    approved_data = events[
        "jp-raos-ai-release-decision-approved-v1.schema.json"
    ]["allOf"][1]["properties"]["data"]
    approved_data["allOf"] = [
        {
            "if": {
                "properties": {"phase": {"const": "ACTIVE"}},
                "required": ["phase"],
            },
            "then": {
                "properties": {
                    "canary_evidence_sha256": text_schema(
                        min_length=64,
                        max_length=64,
                        pattern=SHA256_PATTERN,
                    ),
                    "canary_completed_at": timestamp_schema(),
                    "canary_completed_txid": integer_schema(minimum=1),
                },
                "required": [
                    "canary_evidence_sha256",
                    "canary_completed_at",
                    "canary_completed_txid",
                ],
            },
        },
    ]
    approved_data["x-raos-rollback-binding"] = (
        "PREVIOUS_RELEASE uses rollback_release_decision_id; DISABLE_ROUTE "
        "uses rollback_runbook_artifact_id and rollback_runbook_sha256."
    )
    approved_data["x-raos-transaction-invariants"] = [
        "canary_completed_txid_is_server_owned",
        "canary_completed_txid_must_differ_from_canary_started_txid",
        "canary_checkpoint_is_persisted_before_ACTIVE_approval_transaction",
        "canary_completed_txid_must_precede_ACTIVE_approval_transaction",
    ]
    approved_data["x-raos-canary-safety-invariants"] = (
        release_canary_safety_invariants()
    )
    revoked_data = events[
        "jp-raos-ai-release-decision-revoked-v1.schema.json"
    ]["allOf"][1]["properties"]["data"]
    revoked_data["x-raos-rollback-binding"] = (
        "PREVIOUS_RELEASE uses rollback_release_decision_id; DISABLE_ROUTE "
        "uses rollback_runbook_artifact_id and rollback_runbook_sha256."
    )
    revoked_data["x-raos-server-owned-fields"] = ["canary_completed_txid"]
    return events


def generate_type_schemas(
    contracts_root: Path,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    resources = resource_schema_definitions()
    requests = request_schema_definitions(resources)
    events = event_schema_definitions()

    def assert_required_unique(node: Any, *, source: str) -> None:
        if isinstance(node, dict):
            required = node.get("required")
            if isinstance(required, list):
                if len(required) != len(set(required)):
                    raise RuntimeError(
                        f"duplicate required property in generated schema {source}"
                    )
                properties = node.get("properties")
                if isinstance(properties, dict) and not set(required) <= set(properties):
                    raise RuntimeError(
                        f"required property missing from properties in {source}"
                    )
            for value in node.values():
                assert_required_unique(value, source=source)
        elif isinstance(node, list):
            for value in node:
                assert_required_unique(value, source=source)

    for filename, schema in {**resources, **requests, **events}.items():
        assert_required_unique(schema, source=filename)
    governance_root = contracts_root / "schemas" / "ai-governance"
    for filename, schema in {**resources, **requests}.items():
        write_json(governance_root / filename, schema)
    event_root = contracts_root / "schemas" / "events"
    for filename, schema in events.items():
        write_json(event_root / filename, schema)
    return resources, requests, events


def load_yaml_file(path: Path) -> dict[str, Any]:
    return load_yaml_bytes(path.read_bytes(), source=str(path))


def replace_v02_contract_refs(node: Any) -> None:
    if isinstance(node, dict):
        for key, value in list(node.items()):
            if isinstance(value, str):
                for old_name, new_name in ROOT_REVISION_FILES.items():
                    old_basename = PurePosixPath(old_name).name
                    new_basename = PurePosixPath(new_name).name
                    value = value.replace(old_basename, new_basename)
                node[key] = value
            else:
                replace_v02_contract_refs(value)
    elif isinstance(node, list):
        for item in node:
            replace_v02_contract_refs(item)


def patch_job_catalog(contracts_root: Path) -> None:
    path = contracts_root / "catalogs" / "job-catalog.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    document["ai_governance_revision"] = {
        "revision_id": REVISION_ID,
        "task_catalog_ref": "../ai/RAOS_05_ai_task_catalog_v0.1.yaml",
        "prompt_registry_ref": "../ai/RAOS_05_prompt_registry_v0.1.yaml",
        "model_routing_catalog_ref": (
            "../ai/RAOS_05_model_routing_catalog_v0.1.yaml"
        ),
        "evaluation_catalog_ref": "../ai/RAOS_05_evaluation_catalog_v0.1.yaml",
        "canonical_adoption_ref": "../ai/canonical-adoption.v0.3.yaml",
        "proposal_seed_execution": "FORBIDDEN",
    }
    write_yaml(path, document)


def patch_state_transition_catalog(contracts_root: Path) -> None:
    path = contracts_root / "catalogs" / "state-transition-catalog.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    machines = document.get("machines")
    if not isinstance(machines, list):
        raise RuntimeError("state transition catalog machines are missing")
    existing_ids = {
        machine.get("id") for machine in machines if isinstance(machine, dict)
    }
    ai_catalog = load_yaml_file(
        contracts_root / "ai" / "RAOS_05_state_transition_catalog_v0.1.yaml"
    )
    ai_machines = ai_catalog.get("state_machines")
    if not isinstance(ai_machines, list) or len(ai_machines) != 6:
        raise RuntimeError("expected six frozen AI state machines")
    for machine in ai_machines:
        if not isinstance(machine, dict) or not isinstance(machine.get("id"), str):
            raise RuntimeError("malformed frozen AI state machine")
        if machine["id"] in existing_ids:
            raise RuntimeError(f"AI state machine ID collision: {machine['id']}")
        adopted = copy.deepcopy(machine)
        adopted["x-raos-source"] = (
            "../ai/RAOS_05_state_transition_catalog_v0.1.yaml"
        )
        adopted["x-raos-adoption"] = "INT-DEC-004"
        adopted["x-raos-classification"] = "INTERNAL"
        machines.append(adopted)
        existing_ids.add(machine["id"])
    document["ai_governance_state_machine_count"] = len(ai_machines)
    document["policy_rule_graph_invariants"] = policy_rule_graph_invariants()
    write_yaml(path, document)


RESOURCE_CATALOG_MAP = {
    "ai-task-definition.v1.schema.json": (
        "AITaskDefinition",
        "ai.task_definition",
    ),
    "ai-job.v1.schema.json": ("AIJob", "ai.ai_job"),
    "prompt-version.v1.schema.json": ("PromptVersion", "ai.prompt_version"),
    "model-definition.v1.schema.json": (
        "ModelDefinition",
        "ai.model_definition",
    ),
    "model-route-version.v1.schema.json": (
        "ModelRouteVersion",
        "ai.model_route_version",
    ),
    "evaluation-suite.v1.schema.json": (
        "EvaluationSuite",
        "ai.evaluation_suite",
    ),
    "evaluation-dataset-version.v1.schema.json": (
        "EvaluationDatasetVersion",
        "ai.evaluation_dataset_version",
    ),
    "evaluation-case.v1.schema.json": ("EvaluationCase", "ai.evaluation_case"),
    "evaluation-run.v1.schema.json": ("EvaluationRun", "ai.evaluation_run"),
    "evaluation-case-result.v1.schema.json": (
        "EvaluationCaseResult",
        "ai.evaluation_case_result",
    ),
    "human-evaluation.v1.schema.json": (
        "HumanEvaluation",
        "ai.human_evaluation",
    ),
    "judge-calibration.v1.schema.json": (
        "JudgeCalibration",
        "ai.judge_calibration",
    ),
    "release-decision.v1.schema.json": (
        "ReleaseDecision",
        "ai.release_decision",
    ),
    "release-approval.v1.schema.json": (
        "ReleaseApproval",
        "ai.release_approval",
    ),
}


RESOURCE_CREATE_COMMANDS: dict[str, tuple[tuple[str, str], ...]] = {
    "PromptVersion": (
        ("AI-103", "prompt-version-create-request.v1.schema.json"),
    ),
    "ModelRouteVersion": (
        ("AI-104", "model-route-version-create-request.v1.schema.json"),
    ),
    "EvaluationDatasetVersion": (
        ("AI-105", "evaluation-dataset-create-request.v1.schema.json"),
    ),
    "EvaluationRun": (
        ("AI-108", "evaluation-run-create-request.v1.schema.json"),
    ),
    "HumanEvaluation": (
        ("AI-110", "human-evaluation-create-request.v1.schema.json"),
    ),
    "JudgeCalibration": (
        ("AI-111", "judge-calibration-create-request.v1.schema.json"),
    ),
    "ReleaseDecision": (
        ("AI-112", "release-decision-create-request.v1.schema.json"),
    ),
    "ReleaseApproval": (
        ("AI-113", "release-canary-approval-request.v1.schema.json"),
        ("AI-114", "release-active-approval-request.v1.schema.json"),
    ),
}

RESOURCE_LIFECYCLE_UPDATE_COMMANDS: dict[
    str,
    dict[str, tuple[str, ...]],
] = {
    "EvaluationDatasetVersion": {"AI-106": ("status",)},
    "ReleaseDecision": {
        "AI-113": ("status",),
        "AI-114": ("status",),
        "AI-115": ("status",),
    },
}


def resource_fields(
    schema: Mapping[str, Any],
    *,
    append_only: bool = False,
) -> list[dict[str, Any]]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        raise RuntimeError("governance resource schema properties are missing")
    immutable = {
        "id",
        "display_id",
        "created_at",
        "updated_at",
        "lock_version",
        "reviewer_principal_id",
        "author_principal_id",
        "approved_by_principal_id",
        "second_approver_principal_id",
        "revoked_by_principal_id",
        "approved_at",
        "revoked_at",
        "canary_started_txid",
        "canary_completed_txid",
        "zero_tolerance_failure_count",
    }
    return [
        {
            "name": name,
            "schema": copy.deepcopy(field_schema),
            "read_only": append_only or name in immutable,
        }
        for name, field_schema in properties.items()
    ]


def patch_resource_catalog(
    contracts_root: Path,
    resources: Mapping[str, dict[str, Any]],
    requests: Mapping[str, dict[str, Any]] | None = None,
) -> None:
    if requests is None:
        requests = request_schema_definitions(resources)
    path = contracts_root / "catalogs" / "resource-contracts.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    entries = document.get("resources")
    if not isinstance(entries, list):
        raise RuntimeError("resource contract entries are missing")
    by_name = {
        entry.get("name"): entry for entry in entries if isinstance(entry, dict)
    }
    mutable = {
        "AIJob",
        "PromptVersion",
        "ModelRouteVersion",
        "EvaluationSuite",
        "EvaluationDatasetVersion",
        "EvaluationRun",
        "JudgeCalibration",
        "ReleaseDecision",
    }
    for filename, (name, source_table) in RESOURCE_CATALOG_MAP.items():
        schema = resources[filename]
        classification = str(schema["x-raos-classification"])
        entry = by_name.get(name)
        if entry is None:
            entry = {
                "name": name,
                "source_tables": [source_table],
                "classification": classification,
                "etag": name in mutable,
                "fields": [],
                "create_fields": [],
                "update_fields": [],
                "notes": [],
            }
            entries.append(entry)
            by_name[name] = entry
        entry["source_tables"] = [source_table]
        existing_classification = entry.get("classification")
        if existing_classification in {"CONFIDENTIAL", "RESTRICTED"}:
            classification = str(existing_classification)
            schema["x-raos-classification"] = classification
        entry["classification"] = classification
        entry["authorization_context"] = "GLOBAL"
        entry["etag"] = name in mutable
        entry["schema_ref"] = (
            f"../schemas/ai-governance/{filename}"
        )
        entry["fields"] = resource_fields(
            schema,
            append_only=name == "ReleaseApproval",
        )
        create_fields: list[str] = []
        create_contracts: list[dict[str, Any]] = []
        for operation_id, request_filename in RESOURCE_CREATE_COMMANDS.get(
            name,
            (),
        ):
            request_schema = requests.get(request_filename)
            if not isinstance(request_schema, dict):
                raise RuntimeError(
                    f"create request schema is missing: {request_filename}"
                )
            request_properties = request_schema.get("properties")
            if not isinstance(request_properties, dict):
                raise RuntimeError(
                    f"create request properties are missing: {request_filename}"
                )
            mapped_fields = [
                field_name
                for field_name in request_properties
                if field_name in schema["properties"]
            ]
            for field_name in mapped_fields:
                if field_name not in create_fields:
                    create_fields.append(field_name)
            create_contracts.append(
                {
                    "operation_id": operation_id,
                    "request_schema": request_filename,
                    "resource_fields": mapped_fields,
                    "non_resource_command_fields": [
                        field_name
                        for field_name in request_properties
                        if field_name not in schema["properties"]
                    ],
                }
            )
        lifecycle_commands = RESOURCE_LIFECYCLE_UPDATE_COMMANDS.get(name, {})
        update_fields: list[str] = []
        for command_fields in lifecycle_commands.values():
            for field_name in command_fields:
                if field_name not in schema["properties"]:
                    raise RuntimeError(
                        f"lifecycle field missing from {name}: {field_name}"
                    )
                if field_name not in update_fields:
                    update_fields.append(field_name)
        entry["create_fields"] = create_fields
        entry["update_fields"] = update_fields
        entry["x-raos-create-command-contracts"] = create_contracts
        entry["x-raos-lifecycle-update-command-contracts"] = {
            operation_id: list(command_fields)
            for operation_id, command_fields in lifecycle_commands.items()
        }
        for field_contract in entry["fields"]:
            field_name = field_contract["name"]
            if field_name in create_fields:
                field_contract["read_only"] = False
                if field_name not in update_fields:
                    field_contract["create_only"] = True
            if field_name in update_fields:
                field_contract["read_only"] = False
        entry["notes"] = [
            "ST-0003 canonical AI-governance resource; see INT-DEC-004.",
            (
                "Raw prompt/input/output, source-packet, review-body, secret, "
                "and PII fields are not part of this resource."
            ),
        ]
        if name == "ReleaseApproval":
            entry["notes"].append(
                "Append-only human approval evidence; update and delete are forbidden."
            )
    release_decision_resource = by_name.get("ReleaseDecision")
    if not isinstance(release_decision_resource, dict):
        raise RuntimeError("ReleaseDecision catalog resource is missing")
    release_decision_resource[
        "x-raos-previous-release-rollback-target-invariants"
    ] = previous_release_rollback_target_invariants()
    release_decision_resource[
        "x-raos-baseline-evaluation-run-invariants"
    ] = evaluation_baseline_invariants()
    release_decision_resource["x-raos-release-regression-invariants"] = (
        release_regression_invariants()
    )
    release_decision_resource[
        "x-raos-statistical-evidence-artifact-invariants"
    ] = evaluation_statistics_artifact_invariants()
    release_decision_resource[
        "x-raos-blocking-aggregate-scope-invariants"
    ] = evaluation_blocking_aggregate_scope_invariants()
    release_decision_resource["x-raos-canary-safety-invariants"] = (
        release_canary_safety_invariants()
    )
    policy_bundle_resource = by_name.get("PolicyBundle")
    if not isinstance(policy_bundle_resource, dict):
        raise RuntimeError("PolicyBundle catalog resource is missing")
    policy_bundle_resource["x-raos-policy-rule-graph-invariants"] = (
        policy_rule_graph_invariants()
    )
    for evidence_resource_name in ("EvaluationCase", "EvaluationCaseResult"):
        evidence_resource = by_name.get(evidence_resource_name)
        if not isinstance(evidence_resource, dict):
            raise RuntimeError(
                f"{evidence_resource_name} catalog resource is missing"
            )
        evidence_resource["x-raos-evidence-uniqueness-invariants"] = (
            evaluation_evidence_uniqueness_invariants()
        )
    case_result_resource = by_name.get("EvaluationCaseResult")
    if not isinstance(case_result_resource, dict):
        raise RuntimeError("EvaluationCaseResult catalog resource is missing")
    case_result_resource["x-raos-zero-tolerance-evidence-invariants"] = (
        zero_tolerance_evidence_invariants()
    )
    case_result_resource["x-raos-writer-excluded-fields"] = [
        "zero_tolerance_failure_count"
    ]
    for split_resource_name in (
        "EvaluationSuite",
        "EvaluationDatasetVersion",
        "EvaluationCase",
        "EvaluationRun",
    ):
        split_resource = by_name.get(split_resource_name)
        if not isinstance(split_resource, dict):
            raise RuntimeError(
                f"{split_resource_name} catalog resource is missing"
            )
        split_resource["x-raos-required-split-coverage-invariants"] = (
            evaluation_required_split_coverage_invariants()
        )
    for scoped_resource_name in ("EvaluationRun", "JudgeCalibration"):
        scoped_resource = by_name.get(scoped_resource_name)
        if not isinstance(scoped_resource, dict):
            raise RuntimeError(
                f"{scoped_resource_name} catalog resource is missing"
            )
        scoped_resource["x-raos-judge-calibration-scope-invariants"] = (
            judge_calibration_scope_invariants()
        )
        if scoped_resource_name == "EvaluationRun":
            scoped_resource["x-raos-component-content-snapshot-freeze"] = (
                evaluation_run_component_snapshot_freeze_invariants()
            )
            scoped_resource["x-raos-policy-rule-graph-invariants"] = (
                policy_rule_graph_invariants()
            )
            scoped_resource["x-raos-completion-evidence-invariants"] = (
                evaluation_run_completion_evidence_invariants()
            )
            scoped_resource[
                "x-raos-baseline-evaluation-run-invariants"
            ] = evaluation_baseline_invariants()
            scoped_resource[
                "x-raos-statistical-evidence-artifact-invariants"
            ] = evaluation_statistics_artifact_invariants()
            scoped_resource[
                "x-raos-blocking-aggregate-scope-invariants"
            ] = evaluation_blocking_aggregate_scope_invariants()
            scoped_resource[
                "x-raos-cost-latency-reporting-completeness-invariants"
            ] = cost_latency_reporting_completeness_invariants()
            scoped_resource[
                "x-raos-completion-execution-security-invariants"
            ] = evaluation_completion_execution_security_invariants()
    evaluation_result = by_name.get("EvaluationResult")
    if isinstance(evaluation_result, dict):
        evaluation_result["classification"] = "CONFIDENTIAL"
        evaluation_result["authorization_context"] = "GLOBAL"
        fields = evaluation_result.get("fields")
        if not isinstance(fields, list):
            raise RuntimeError("EvaluationResult catalog fields are missing")
        passed_fields = [
            field
            for field in fields
            if isinstance(field, dict) and field.get("name") == "passed"
        ]
        if len(passed_fields) != 1:
            raise RuntimeError("EvaluationResult catalog passed field is missing")
        passed_fields[0]["schema"] = {"type": ["boolean", "null"]}
        existing_fields = {
            field.get("name") for field in fields if isinstance(field, dict)
        }
        additions = {
            "evaluation_run_id": uuid_schema(nullable=True),
            "evaluation_case_id": uuid_schema(nullable=True),
            "grader_code": text_schema(nullable=True, max_length=200),
            "slice_key": text_schema(nullable=True, max_length=200),
            "threshold_operator": {
                "type": ["string", "null"],
                "enum": [">=", ">", "<=", "<", "==", "!=", None],
            },
            "threshold_value": {"type": ["number", "null"]},
            "proportion_numerator_count": {
                "type": ["integer", "null"],
                "minimum": 0,
            },
            "proportion_denominator_count": {
                "type": ["integer", "null"],
                "minimum": 1,
            },
            "judge_calibration_id": uuid_schema(nullable=True),
            "judge_route_version_id": uuid_schema(nullable=True),
            "judge_prompt_version_id": uuid_schema(nullable=True),
            "judge_rubric_artifact_id": uuid_schema(nullable=True),
            "judge_resolved_model_id": uuid_schema(nullable=True),
            "judge_grader_version": text_schema(nullable=True, max_length=200),
        }
        for field_name, field_schema in additions.items():
            if field_name not in existing_fields:
                fields.append(
                    {
                        "name": field_name,
                        "schema": field_schema,
                        "read_only": True,
                    }
                )
        evaluation_result.setdefault("notes", []).append(
            "Legacy aggregate retained; canonical runs/cases use EvaluationRun "
            "and EvaluationCaseResult additively."
        )
        evaluation_result["x-raos-conditional-constraints"] = {
            "model_judge": {
                "when": {"grader_code": "grader.model_judge.v1"},
                "required_non_null": [
                    "judge_calibration_id",
                    "judge_route_version_id",
                    "judge_prompt_version_id",
                    "judge_rubric_artifact_id",
                    "judge_resolved_model_id",
                    "judge_grader_version",
                ],
                "otherwise_all_null": True,
            },
            "ratio_metric": {
                "when": {"canonical_metric_unit": "ratio"},
                "required_non_null": [
                    "proportion_numerator_count",
                    "proportion_denominator_count",
                ],
                "metric_value": "DATABASE_DERIVED_READ_ONLY",
            },
            "non_ratio_metric": {
                "when": {"canonical_metric_unit": "NOT_RATIO"},
                "must_be_null": [
                    "proportion_numerator_count",
                    "proportion_denominator_count",
                ],
            },
        }
        evaluation_result["x-raos-judge-calibration-scope-invariants"] = (
            judge_calibration_scope_invariants()
        )
        evaluation_result["x-raos-completion-evidence-invariants"] = (
            evaluation_run_completion_evidence_invariants()
        )
        evaluation_result["x-raos-ratio-metric-invariants"] = (
            evaluation_result_ratio_metric_invariants()
        )
        evaluation_result["x-raos-release-regression-invariants"] = (
            release_regression_invariants()
        )
        evaluation_result["x-raos-blocking-aggregate-scope-invariants"] = (
            evaluation_blocking_aggregate_scope_invariants()
        )
        evaluation_result["x-raos-zero-tolerance-evidence-invariants"] = (
            zero_tolerance_evidence_invariants()
        )
        evaluation_result[
            "x-raos-cost-latency-reporting-completeness-invariants"
        ] = cost_latency_reporting_completeness_invariants()
    document["ai_governance_resource_count"] = len(RESOURCE_CATALOG_MAP)
    document["public_ai_resource_count"] = 0
    document["policy_rule_graph_invariants"] = policy_rule_graph_invariants()
    document["evaluation_run_completion_evidence_invariants"] = (
        evaluation_run_completion_evidence_invariants()
    )
    document["evaluation_baseline_invariants"] = (
        evaluation_baseline_invariants()
    )
    document["evaluation_result_ratio_metric_invariants"] = (
        evaluation_result_ratio_metric_invariants()
    )
    document["release_regression_invariants"] = (
        release_regression_invariants()
    )
    document["evaluation_statistics_artifact_invariants"] = (
        evaluation_statistics_artifact_invariants()
    )
    document["evaluation_blocking_aggregate_scope_invariants"] = (
        evaluation_blocking_aggregate_scope_invariants()
    )
    document["evaluation_required_split_coverage_invariants"] = (
        evaluation_required_split_coverage_invariants()
    )
    document["cost_latency_reporting_completeness_invariants"] = (
        cost_latency_reporting_completeness_invariants()
    )
    document["release_canary_safety_invariants"] = (
        release_canary_safety_invariants()
    )
    document["evaluation_completion_execution_security_invariants"] = (
        evaluation_completion_execution_security_invariants()
    )
    write_yaml(path, document)


def schema_registry_entry(
    *,
    path: str,
    schema_id: str,
    title: str,
    digest: str,
    origin: str,
) -> dict[str, Any]:
    return {
        "path": path,
        "id": schema_id,
        "title": title,
        "sha256": digest,
        "compatibility": "ADDITIVE",
        "origin": origin,
    }


def patch_schema_registry(contracts_root: Path) -> None:
    path = contracts_root / "catalogs" / "schema-registry.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    entries = document.get("schemas")
    if not isinstance(entries, list) or len(entries) != 126:
        raise RuntimeError("expected 126 predecessor schema registry entries")
    seen_paths = {
        entry.get("path") for entry in entries if isinstance(entry, dict)
    }
    seen_ids = {entry.get("id") for entry in entries if isinstance(entry, dict)}
    frozen_registry = load_yaml_file(
        contracts_root / "ai" / "RAOS_05_schema_registry_v0.1.yaml"
    )
    frozen_entries = frozen_registry.get("schemas")
    if not isinstance(frozen_entries, list) or len(frozen_entries) != 14:
        raise RuntimeError("expected 14 frozen AI registry entries")
    additions: list[dict[str, Any]] = []
    for frozen in frozen_entries:
        if not isinstance(frozen, dict):
            raise RuntimeError("malformed frozen AI schema registry entry")
        relative = f"ai/{frozen['path']}"
        schema_path = contracts_root.joinpath(*PurePosixPath(relative).parts)
        digest = sha256_file(schema_path)
        if digest != frozen.get("sha256"):
            raise RuntimeError(f"frozen AI schema hash mismatch: {relative}")
        additions.append(
            schema_registry_entry(
                path=relative,
                schema_id=frozen["schema_id"],
                title=frozen["title"],
                digest=digest,
                origin="RAOS-AI-001@0.1_BYTE_FROZEN",
            )
        )
    generated_paths = sorted(
        [
            *(
                path
                for path in (contracts_root / "schemas" / "ai-governance").glob(
                    "*.json"
                )
            ),
            *(
                contracts_root / "schemas" / "events" / name
                for name in event_schema_definitions()
            ),
        ]
    )
    for generated_path in generated_paths:
        schema = json.loads(generated_path.read_text(encoding="utf-8"))
        if not isinstance(schema, dict):
            raise RuntimeError(f"generated schema is not an object: {generated_path}")
        relative = generated_path.relative_to(contracts_root).as_posix()
        additions.append(
            schema_registry_entry(
                path=relative,
                schema_id=schema["$id"],
                title=schema["title"],
                digest=sha256_file(generated_path),
                origin=f"{REVISION_ID}@{REVISION_VERSION}",
            )
        )
    for addition in additions:
        if addition["path"] in seen_paths or addition["id"] in seen_ids:
            raise RuntimeError(
                f"schema registry collision: {addition['path']} / {addition['id']}"
            )
        seen_paths.add(addition["path"])
        seen_ids.add(addition["id"])
        entries.append(addition)
    revision_policy = document.setdefault("revision_policy", {})
    if not isinstance(revision_policy, dict):
        raise RuntimeError("schema registry revision_policy must be a mapping")
    revision_policy.update(
        {
            "ai_governance_revision": REVISION_ID,
            "predecessor_schema_count": 126,
            "frozen_ai_schema_count": 14,
            "generated_portable_type_count": len(generated_paths),
            "existing_schema_replacement_count": 0,
            "unknown_fields": "REJECT",
        }
    )
    document["schema_count"] = len(entries)
    write_yaml(path, document)


OPENAPI_RESOURCE_COMPONENTS = {
    "AITaskDefinition": "ai-task-definition.v1.schema.json",
    "AITaskContractV1": "ai-task-contract.v1.schema.json",
    "AIGovernanceJob": "ai-job.v1.schema.json",
    "PromptVersionV1": "prompt-version.v1.schema.json",
    "ModelDefinitionV1": "model-definition.v1.schema.json",
    "ModelRouteVersionV1": "model-route-version.v1.schema.json",
    "EvaluationSuiteV1": "evaluation-suite.v1.schema.json",
    "EvaluationDatasetVersion": "evaluation-dataset-version.v1.schema.json",
    "EvaluationCaseV1": "evaluation-case.v1.schema.json",
    "EvaluationRunV1": "evaluation-run.v1.schema.json",
    "EvaluationRunDetailV1": "evaluation-run-detail.v1.schema.json",
    "EvaluationCaseResultV1": "evaluation-case-result.v1.schema.json",
    "HumanEvaluationV1": "human-evaluation.v1.schema.json",
    "JudgeCalibrationV1": "judge-calibration.v1.schema.json",
    "ReleaseDecisionV1": "release-decision.v1.schema.json",
    "ReleaseApprovalV1": "release-approval.v1.schema.json",
    "ReleaseDecisionApprovalResultV1": (
        "release-decision-approval-result.v1.schema.json"
    ),
}
OPENAPI_REQUEST_COMPONENTS = {
    "PromptVersionCreateRequestV1": (
        "prompt-version-create-request.v1.schema.json"
    ),
    "ModelRouteVersionCreateRequestV1": (
        "model-route-version-create-request.v1.schema.json"
    ),
    "EvaluationDatasetCreateRequestV1": (
        "evaluation-dataset-create-request.v1.schema.json"
    ),
    "EvaluationRunCreateRequestV1": (
        "evaluation-run-create-request.v1.schema.json"
    ),
    "HumanEvaluationCreateRequestV1": (
        "human-evaluation-create-request.v1.schema.json"
    ),
    "JudgeCalibrationCreateRequestV1": (
        "judge-calibration-create-request.v1.schema.json"
    ),
    "ReleaseDecisionCreateRequestV1": (
        "release-decision-create-request.v1.schema.json"
    ),
    "ReleaseCanaryApprovalRequestV1": (
        "release-canary-approval-request.v1.schema.json"
    ),
    "ReleaseActiveApprovalRequestV1": (
        "release-active-approval-request.v1.schema.json"
    ),
    "ReleaseDecisionRevokeRequestV1": (
        "release-decision-revoke-request.v1.schema.json"
    ),
}


def openapi_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(dict(schema))
    result.pop("$schema", None)
    result.pop("$id", None)

    replacements = {
        "ai-task-definition.v1.schema.json": (
            "#/components/schemas/AITaskDefinition"
        ),
        "evaluation-run.v1.schema.json": "#/components/schemas/EvaluationRunV1",
        "release-decision.v1.schema.json": (
            "#/components/schemas/ReleaseDecisionV1"
        ),
        "release-approval.v1.schema.json": "#/components/schemas/ReleaseApprovalV1",
    }

    def rewrite(node: Any) -> None:
        if isinstance(node, dict):
            reference = node.get("$ref")
            if reference in replacements:
                node["$ref"] = replacements[reference]
            for value in node.values():
                rewrite(value)
        elif isinstance(node, list):
            for value in node:
                rewrite(value)

    rewrite(result)
    return result


def add_openapi_components(
    document: MutableMapping[str, Any],
    resources: Mapping[str, dict[str, Any]],
    requests: Mapping[str, dict[str, Any]],
) -> None:
    components = document.get("components")
    if not isinstance(components, dict):
        raise RuntimeError("OpenAPI components are missing")
    schemas = components.get("schemas")
    if not isinstance(schemas, dict):
        raise RuntimeError("OpenAPI component schemas are missing")
    for name, filename in OPENAPI_RESOURCE_COMPONENTS.items():
        if name in schemas:
            raise RuntimeError(f"unexpected OpenAPI component collision: {name}")
        schemas[name] = openapi_schema(resources[filename])
    for name, filename in OPENAPI_REQUEST_COMPONENTS.items():
        if name in schemas:
            raise RuntimeError(f"unexpected OpenAPI component collision: {name}")
        schemas[name] = openapi_schema(requests[filename])
    list_components = {
        "AITaskDefinitionListV1": "AITaskDefinition",
        "EvaluationSuiteListV1": "EvaluationSuiteV1",
    }
    for name, item_component in list_components.items():
        schemas[name] = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": f"#/components/schemas/{item_component}"},
                    "maxItems": 200,
                },
                "next_cursor": {
                    "type": ["string", "null"],
                    "maxLength": 1024,
                },
            },
            "required": ["items", "next_cursor"],
        }
    document["x-raos-schema-component-count"] = len(schemas)


def add_optional_component_properties(
    components: MutableMapping[str, Any],
    *,
    component_name: str,
    source_schema: Mapping[str, Any],
) -> None:
    component = components.get(component_name)
    if not isinstance(component, dict):
        raise RuntimeError(f"OpenAPI component is missing: {component_name}")
    properties = component.get("properties")
    source_properties = source_schema.get("properties")
    if not isinstance(properties, dict) or not isinstance(source_properties, dict):
        raise RuntimeError(f"OpenAPI component properties missing: {component_name}")
    for name, schema in source_properties.items():
        if name not in properties:
            properties[name] = copy.deepcopy(schema)


def common_parameters() -> list[dict[str, Any]]:
    return [
        {"$ref": "#/components/parameters/RequestID"},
        {"$ref": "#/components/parameters/Traceparent"},
    ]


def path_parameter(name: str) -> dict[str, Any]:
    if name == "taskCode":
        schema = text_schema(max_length=200)
    else:
        schema = uuid_schema()
    return {
        "name": name,
        "in": "path",
        "required": True,
        "description": f"{name} identifier.",
        "schema": schema,
    }


def success_response(
    *,
    status: str,
    component: str,
    etag: bool,
) -> dict[str, Any]:
    headers: dict[str, Any] = {
        "X-Request-ID": {"$ref": "#/components/headers/XRequestID"},
        "traceparent": {"$ref": "#/components/headers/Traceparent"},
    }
    if etag:
        headers["ETag"] = {"$ref": "#/components/headers/ETag"}
    if status == "201":
        headers["Location"] = {
            "description": "Created resource URL.",
            "schema": {"type": "string", "format": "uri-reference"},
        }
    if status == "202":
        headers["Location"] = {
            "description": "Accepted Job status URL.",
            "schema": {"type": "string", "format": "uri-reference"},
        }
        headers["Retry-After"] = {
            "description": "Recommended seconds before polling Job status.",
            "schema": {"type": "integer", "minimum": 1},
        }
    return {
        "description": {
            "200": "Successful response.",
            "201": "Resource created.",
        }.get(status, "Accepted for asynchronous processing."),
        "headers": headers,
        "content": {
            "application/json": {
                "schema": {"$ref": f"#/components/schemas/{component}"}
            }
        },
    }


def error_responses(*, concurrency: bool, async_command: bool) -> dict[str, Any]:
    statuses = ["400", "401", "403", "404", "409", "422", "429", "500"]
    if concurrency:
        statuses.extend(("412", "428"))
    if async_command:
        statuses.append("503")
    return {status: {"$ref": f"#/components/responses/{status}"} for status in statuses}


def make_admin_operation(
    *,
    operation_id: str,
    method: str,
    path: str,
    summary: str,
    scope: str,
    response_status: str,
    response_component: str,
    request_component: str | None = None,
    async_job_type: str | None = None,
    concurrency: bool = False,
    audit_action: str,
    step_up: bool = False,
) -> dict[str, Any]:
    is_command = method == "post"
    async_command = async_job_type is not None
    parameters = common_parameters()
    for part in PurePosixPath(path).parts:
        if part.startswith("{") and part.endswith("}"):
            parameters.append(path_parameter(part[1:-1]))
    if is_command:
        parameters.append({"$ref": "#/components/parameters/IdempotencyKey"})
    if concurrency:
        parameters.append({"$ref": "#/components/parameters/IfMatch"})
    operation: dict[str, Any] = {
        "operationId": operation_id,
        "tags": ["AI"],
        "summary": summary,
        "description": summary,
        "parameters": parameters,
        "responses": {
            response_status: success_response(
                status=response_status,
                component=response_component,
                etag=concurrency or response_component in {
                    "EvaluationDatasetVersion",
                    "EvaluationRunV1",
                    "EvaluationRunDetailV1",
                    "ReleaseDecisionV1",
                    "ReleaseDecisionApprovalResultV1",
                },
            ),
            **error_responses(
                concurrency=concurrency,
                async_command=async_command,
            ),
        },
        "x-raos-operation-id": operation_id,
        "x-raos-kind": (
            "async_command"
            if async_command
            else ("command" if is_command else "query")
        ),
        "x-raos-requirements": ["FR-018"],
        "x-raos-implementation-slice": "ST-0003",
        "x-raos-idempotency-required": is_command,
        "x-raos-concurrency-required": concurrency,
        "x-raos-async-job-type": async_job_type,
        "x-raos-audit-action": audit_action,
        "x-raos-error-codes": [],
        "x-raos-classification": "INTERNAL",
        "x-raos-authorization-context": "GLOBAL",
        "security": [{"oidcOAuth2": [scope]}],
    }
    operation["x-raos-success-etag-required"] = (
        concurrency
        or response_component
        in {
            "EvaluationDatasetVersion",
            "EvaluationRunV1",
            "EvaluationRunDetailV1",
            "ReleaseDecisionV1",
            "ReleaseDecisionApprovalResultV1",
        }
    )
    if not is_command:
        operation["x-raos-safe"] = True
    if request_component is not None:
        operation["requestBody"] = {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "$ref": f"#/components/schemas/{request_component}"
                    }
                }
            },
        }
    if step_up:
        operation["x-raos-step-up-required"] = True
        operation["x-raos-human-approval-required"] = True
    return operation


def patch_admin_openapi(
    contracts_root: Path,
    resources: Mapping[str, dict[str, Any]],
    requests: Mapping[str, dict[str, Any]],
) -> None:
    path = contracts_root / "openapi-admin.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    components = document.get("components")
    paths = document.get("paths")
    if not isinstance(components, dict) or not isinstance(paths, dict):
        raise RuntimeError("Admin OpenAPI structure is incomplete")
    schemas = components.get("schemas")
    responses = components.get("responses")
    if not isinstance(schemas, dict) or not isinstance(responses, dict):
        raise RuntimeError("Admin OpenAPI schemas/responses are incomplete")
    # Existing operations AI-001..AI-008 retain their required-header,
    # idempotency, concurrency, security, and response semantics. Only their
    # resource representations receive additive optional fields.
    add_optional_component_properties(
        schemas,
        component_name="AIJob",
        source_schema=resources["ai-job.v1.schema.json"],
    )
    add_optional_component_properties(
        schemas,
        component_name="PromptVersion",
        source_schema=resources["prompt-version.v1.schema.json"],
    )
    prompt_version_component = schemas.get("PromptVersion")
    if not isinstance(prompt_version_component, dict):
        raise RuntimeError("PromptVersion OpenAPI component is missing")
    prompt_version_properties = prompt_version_component.get("properties")
    prompt_version_required = prompt_version_component.get("required")
    if not isinstance(prompt_version_properties, dict) or not isinstance(
        prompt_version_required,
        list,
    ):
        raise RuntimeError("PromptVersion OpenAPI component shape is incomplete")
    prompt_version_properties["author_principal_id"] = copy.deepcopy(
        resources["prompt-version.v1.schema.json"]["properties"][
            "author_principal_id"
        ]
    )
    if "author_principal_id" in prompt_version_required:
        raise RuntimeError(
            "legacy Admin PromptVersion author_principal_id must remain optional; "
            "PromptVersionV1 carries the canonical required contract"
        )
    add_optional_component_properties(
        schemas,
        component_name="ModelRouteVersion",
        source_schema=resources["model-route-version.v1.schema.json"],
    )
    add_optional_component_properties(
        schemas,
        component_name="EvaluationResult",
        source_schema={
            "properties": {
                "evaluation_run_id": uuid_schema(nullable=True),
                "evaluation_case_id": uuid_schema(nullable=True),
                "grader_code": text_schema(nullable=True, max_length=200),
                "slice_key": text_schema(nullable=True, max_length=200),
                "threshold_operator": {
                    "type": ["string", "null"],
                    "enum": [">=", ">", "<=", "<", "==", "!=", None],
                },
                "threshold_value": {"type": ["number", "null"]},
                "proportion_numerator_count": {
                    "type": ["integer", "null"],
                    "minimum": 0,
                },
                "proportion_denominator_count": {
                    "type": ["integer", "null"],
                    "minimum": 1,
                },
                "judge_calibration_id": uuid_schema(nullable=True),
                "judge_route_version_id": uuid_schema(nullable=True),
                "judge_prompt_version_id": uuid_schema(nullable=True),
                "judge_rubric_artifact_id": uuid_schema(nullable=True),
                "judge_resolved_model_id": uuid_schema(nullable=True),
                "judge_grader_version": text_schema(
                    nullable=True,
                    max_length=200,
                ),
            }
        },
    )
    policy_bundle_component = schemas.get("PolicyBundle")
    if not isinstance(policy_bundle_component, dict):
        raise RuntimeError("PolicyBundle OpenAPI component is missing")
    policy_bundle_component["x-raos-policy-rule-graph-invariants"] = (
        policy_rule_graph_invariants()
    )
    evaluation_result_component = schemas.get("EvaluationResult")
    if not isinstance(evaluation_result_component, dict):
        raise RuntimeError("EvaluationResult OpenAPI component is missing")
    evaluation_result_properties = evaluation_result_component.get("properties")
    if not isinstance(evaluation_result_properties, dict) or not isinstance(
        evaluation_result_properties.get("passed"),
        dict,
    ):
        raise RuntimeError("EvaluationResult OpenAPI passed property is missing")
    evaluation_result_properties["passed"] = {
        "type": ["boolean", "null"]
    }
    evaluation_result_component[
        "x-raos-judge-calibration-scope-invariants"
    ] = judge_calibration_scope_invariants()
    evaluation_result_component["x-raos-completion-evidence-invariants"] = (
        evaluation_run_completion_evidence_invariants()
    )
    evaluation_result_component["x-raos-ratio-metric-invariants"] = (
        evaluation_result_ratio_metric_invariants()
    )
    evaluation_result_component["x-raos-release-regression-invariants"] = (
        release_regression_invariants()
    )
    evaluation_result_component[
        "x-raos-blocking-aggregate-scope-invariants"
    ] = evaluation_blocking_aggregate_scope_invariants()
    evaluation_result_component[
        "x-raos-zero-tolerance-evidence-invariants"
    ] = zero_tolerance_evidence_invariants()
    evaluation_result_component[
        "x-raos-cost-latency-reporting-completeness-invariants"
    ] = cost_latency_reporting_completeness_invariants()
    if "allOf" in evaluation_result_component:
        raise RuntimeError(
            "EvaluationResult must remain free of structural allOf; "
            "use x-raos invariant annotations for additive conditions"
        )
    responses["412"] = {
        "description": "Precondition Failed",
        "headers": {
            "X-Request-ID": {"$ref": "#/components/headers/XRequestID"},
            "traceparent": {"$ref": "#/components/headers/Traceparent"},
        },
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetails"}
            }
        },
    }
    add_openapi_components(document, resources, requests)
    operations = (
        (
            "AI-101",
            "get",
            "/api/v1/admin/ai/tasks",
            "AI Task registry一覧を取得",
            "ai:task:read",
            "200",
            "AITaskDefinitionListV1",
            None,
            None,
            False,
            "ai_task_list_read",
            False,
        ),
        (
            "AI-102",
            "get",
            "/api/v1/admin/ai/tasks/{taskCode}",
            "AI Task contractを取得",
            "ai:task:read",
            "200",
            "AITaskContractV1",
            None,
            None,
            False,
            "ai_task_read",
            False,
        ),
        (
            "AI-103",
            "post",
            "/api/v1/admin/ai/prompt-versions",
            "Prompt Version metadataを登録",
            "ai:config:write",
            "201",
            "PromptVersionV1",
            "PromptVersionCreateRequestV1",
            None,
            False,
            "ai_prompt_version_create",
            False,
        ),
        (
            "AI-104",
            "post",
            "/api/v1/admin/ai/model-route-versions",
            "Model Route Version draftを作成",
            "ai:config:write",
            "201",
            "ModelRouteVersionV1",
            "ModelRouteVersionCreateRequestV1",
            None,
            False,
            "ai_model_route_version_create",
            False,
        ),
        (
            "AI-105",
            "post",
            "/api/v1/admin/ai/evaluation-datasets",
            "Evaluation Dataset Versionを登録",
            "ai:dataset:write",
            "201",
            "EvaluationDatasetVersion",
            "EvaluationDatasetCreateRequestV1",
            None,
            False,
            "ai_evaluation_dataset_create",
            False,
        ),
        (
            "AI-106",
            "post",
            "/api/v1/admin/ai/evaluation-datasets/{id}:lock",
            "Evaluation Dataset Versionを不変Lock",
            "ai:dataset:write",
            "200",
            "EvaluationDatasetVersion",
            None,
            None,
            True,
            "ai_evaluation_dataset_lock",
            True,
        ),
        (
            "AI-107",
            "get",
            "/api/v1/admin/ai/evaluation-suites",
            "Evaluation Suite一覧を取得",
            "ai:evaluation:read",
            "200",
            "EvaluationSuiteListV1",
            None,
            None,
            False,
            "ai_evaluation_suite_list_read",
            False,
        ),
        (
            "AI-108",
            "post",
            "/api/v1/admin/ai/evaluation-runs",
            "Hash-bound Evaluation Run Jobを要求",
            "ai:evaluation:run",
            "202",
            "JobAccepted",
            "EvaluationRunCreateRequestV1",
            "ai.evaluate_output.v1",
            False,
            "ai_evaluation_run_request",
            False,
        ),
        (
            "AI-109",
            "get",
            "/api/v1/admin/ai/evaluation-runs/{id}",
            "Evaluation Runを取得",
            "ai:evaluation:read",
            "200",
            "EvaluationRunDetailV1",
            None,
            None,
            False,
            "ai_evaluation_run_read",
            False,
        ),
        (
            "AI-110",
            "post",
            "/api/v1/admin/ai/evaluation-case-results/{id}/human-evaluations",
            "Blind Human Evaluationを記録",
            "ai:evaluation:write",
            "201",
            "HumanEvaluationV1",
            "HumanEvaluationCreateRequestV1",
            None,
            False,
            "ai_human_evaluation_create",
            False,
        ),
        (
            "AI-111",
            "post",
            "/api/v1/admin/ai/judge-calibrations",
            "Judge Calibration Jobを要求",
            "ai:evaluation:run",
            "202",
            "JobAccepted",
            "JudgeCalibrationCreateRequestV1",
            "ai.evaluate_output.v1",
            False,
            "ai_judge_calibration_request",
            False,
        ),
        (
            "AI-112",
            "post",
            "/api/v1/admin/ai/release-decisions",
            "Hash束縛を検証しRelease DecisionをReady for reviewで作成",
            "ai:release:write",
            "201",
            "ReleaseDecisionV1",
            "ReleaseDecisionCreateRequestV1",
            None,
            False,
            "ai_release_decision_create",
            False,
        ),
        (
            "AI-113",
            "post",
            "/api/v1/admin/ai/release-decisions/{id}:approve-canary",
            "同一Release Decision aggregateをCanary承認",
            "ai:release:approve",
            "200",
            "ReleaseDecisionApprovalResultV1",
            "ReleaseCanaryApprovalRequestV1",
            None,
            True,
            "ai_release_decision_approve_canary",
            True,
        ),
        (
            "AI-114",
            "post",
            "/api/v1/admin/ai/release-decisions/{id}:approve-active",
            "Canary evidence後に同一Release Decision aggregateをActive承認",
            "ai:release:approve",
            "200",
            "ReleaseDecisionApprovalResultV1",
            "ReleaseActiveApprovalRequestV1",
            None,
            True,
            "ai_release_decision_approve_active",
            True,
        ),
        (
            "AI-115",
            "post",
            "/api/v1/admin/ai/release-decisions/{id}:revoke",
            "Release Decisionを取消しRollback routeを指示",
            "ai:release:revoke",
            "200",
            "ReleaseDecisionV1",
            "ReleaseDecisionRevokeRequestV1",
            None,
            True,
            "ai_release_decision_revoke",
            True,
        ),
    )
    for (
        operation_id,
        method,
        operation_path,
        summary,
        scope,
        response_status,
        response_component,
        request_component,
        async_job_type,
        concurrency,
        audit_action,
        step_up,
    ) in operations:
        path_item = paths.setdefault(operation_path, {})
        if method in path_item:
            raise RuntimeError(
                f"Admin OpenAPI operation collision: {method} {operation_path}"
            )
        path_item[method] = make_admin_operation(
            operation_id=operation_id,
            method=method,
            path=operation_path,
            summary=summary,
            scope=scope,
            response_status=response_status,
            response_component=response_component,
            request_component=request_component,
            async_job_type=async_job_type,
            concurrency=concurrency,
            audit_action=audit_action,
            step_up=step_up,
        )
        if operation_id not in {"AI-101", "AI-102"}:
            path_item[method]["x-raos-classification"] = "CONFIDENTIAL"
    state_transitions = {
        "AI-112": {
            "from": None,
            "to": "READY_FOR_REVIEW",
            "atomic_rule": (
                "The server creates DRAFT, validates every direct binding and "
                "manifest hash, then records READY_FOR_REVIEW in the same "
                "transaction; no externally observable unreviewable DRAFT is "
                "returned."
            ),
        },
        "AI-113": {
            "from": "READY_FOR_REVIEW",
            "to": "APPROVED_CANARY",
            "terminal": False,
        },
        "AI-114": {
            "from": "APPROVED_CANARY",
            "to": "APPROVED_ACTIVE",
            "same_aggregate": True,
            "terminal": False,
        },
        "AI-115": {
            "from": [
                "APPROVED_CANARY",
                "APPROVED_ACTIVE",
            ],
            "to": "REVOKED",
            "terminal": True,
        },
    }
    for operation_id, transition in state_transitions.items():
        matches = [
            operation
            for path_item in paths.values()
            if isinstance(path_item, dict)
            for operation in path_item.values()
            if isinstance(operation, dict)
            and operation.get("operationId") == operation_id
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one Admin transition operation: {operation_id}"
            )
        matches[0]["x-raos-state-transition"] = transition
        if operation_id in {"AI-113", "AI-114"}:
            matches[0]["x-raos-separation-of-duties"] = [
                "prompt_author_cannot_be_sole_approver",
                "critical_task_requires_two_distinct_approvers",
            ]
    for operation_id in {"AI-110", "AI-113", "AI-114", "AI-115"}:
        matches = [
            operation
            for path_item in paths.values()
            if isinstance(path_item, dict)
            for operation in path_item.values()
            if isinstance(operation, dict)
            and operation.get("operationId") == operation_id
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one human-authority operation: {operation_id}"
            )
        matches[0]["x-raos-allowed-principal-types"] = ["USER"]
        matches[0]["x-raos-ai-actor-forbidden"] = True
    operation_contracts = {
        "AI-103": {
            "x-raos-author-principal-source": "AUTHENTICATED_USER",
            "x-raos-author-principal-body-field": "FORBIDDEN",
        },
        "AI-106": {
            "x-raos-evidence-uniqueness-invariants": (
                evaluation_evidence_uniqueness_invariants()
            ),
        },
        "AI-108": {
            "x-raos-snapshot-bindings": [
                "suite_id",
                "dataset_version_id",
                "prompt_version_id",
                "model_route_version_id",
                "resolved_model_id",
                "output_schema_version_id",
                "policy_bundle_version_id",
                "code_git_sha",
            ],
            "x-raos-evidence-uniqueness-invariants": (
                evaluation_evidence_uniqueness_invariants()
            ),
            "x-raos-component-content-snapshot-freeze": (
                evaluation_run_component_snapshot_freeze_invariants()
            ),
            "x-raos-policy-rule-graph-invariants": (
                policy_rule_graph_invariants()
            ),
            "x-raos-completion-evidence-invariants": (
                evaluation_run_completion_evidence_invariants()
            ),
            "x-raos-baseline-evaluation-run-invariants": (
                evaluation_baseline_invariants()
            ),
            "x-raos-statistical-evidence-artifact-invariants": (
                evaluation_statistics_artifact_invariants()
            ),
        },
        "AI-109": {
            "x-raos-baseline-evaluation-run-invariants": (
                evaluation_baseline_invariants()
            ),
            "x-raos-statistical-evidence-artifact-invariants": (
                evaluation_statistics_artifact_invariants()
            ),
        },
        "AI-111": {
            "x-raos-snapshot-bindings": [
                "evaluated_task_definition_id",
                "judge_route_version_id",
                "judge_prompt_version_id",
                "resolved_judge_model_id",
                "dataset_version_id",
                "rubric_artifact_id",
                "rubric_sha256",
                "grader_version",
            ],
        },
        "AI-112": {
            "x-raos-release-binding-validation": [
                "evaluation_run_exact_snapshot_match",
                "judge_calibration_exact_snapshot_match_when_present",
                "rollback_strategy_and_runbook_resolve",
                "canary_percent_within_route_config_canary_max_percent",
                "decision_manifest_hash_matches_all_direct_bindings",
            ],
            "x-raos-baseline-evaluation-run-invariants": (
                evaluation_baseline_invariants()
            ),
            "x-raos-release-regression-invariants": (
                release_regression_invariants()
            ),
            "x-raos-statistical-evidence-artifact-invariants": (
                evaluation_statistics_artifact_invariants()
            ),
        },
        "AI-113": {
            "description": (
                "同一Release Decision aggregateをCanary承認し、CANARY phaseの"
                "append-only approvalを作成する。Prompt authorはprimary/second"
                "いずれの承認者にもなれない。"
            ),
            "x-raos-approval-phase": "CANARY",
            "x-raos-append-only-resource": "ReleaseApprovalV1",
            "x-raos-primary-principal-must-match-authenticated-user": True,
            "x-raos-prompt-author-forbidden-as-either-approver": True,
            "x-raos-server-owned-canary-started-txid": True,
        },
        "AI-114": {
            "description": (
                "先行transactionで永続化済みのCanary monitoring checkpointと"
                "evidence artifact/hashを完全一致で検証した後、同一aggregateを"
                "Active承認する。ACTIVE承認transactionではcheckpointを新規記録・"
                "変更できず、canary completed txはACTIVE承認txより前でなければ"
                "ならない。CANARY phaseと異なるmanifest、approval artifact、"
                "approval hashを束縛したACTIVE approvalを作成する。Prompt author"
                "はprimary/secondいずれの承認者にもなれない。"
            ),
            "x-raos-approval-phase": "ACTIVE",
            "x-raos-append-only-resource": "ReleaseApprovalV1",
            "x-raos-primary-principal-must-match-authenticated-user": True,
            "x-raos-prompt-author-forbidden-as-either-approver": True,
            "x-raos-canary-evidence-required": True,
            "x-raos-server-owned-canary-completed-txid": True,
            "x-raos-canary-completion-separate-transaction-required": True,
            "x-raos-prior-canary-checkpoint-binding": {
                "resource": "ReleaseDecisionV1",
                "persistence": "PRIOR_TRANSACTION",
                "match": "EXACT",
                "request_fields": [
                    "canary_monitoring_artifact_id",
                    "canary_monitoring_sha256",
                    "canary_evidence_artifact_id",
                    "canary_evidence_sha256",
                ],
                "active_approval_may_create_or_update_checkpoint": False,
            },
            "x-raos-transaction-order": {
                "left": "ReleaseDecisionV1.canary_completed_txid",
                "operator": "<",
                "right": "ACTIVE_APPROVAL_TRANSACTION.txid",
            },
            "x-raos-cross-phase-must-differ": [
                "decision_manifest_sha256",
                "approval_artifact_id",
                "approval_sha256",
            ],
        },
    }
    for rollback_operation_id in ("AI-113", "AI-114", "AI-115"):
        operation_contracts.setdefault(rollback_operation_id, {})[
            "x-raos-previous-release-rollback-target-invariants"
        ] = previous_release_rollback_target_invariants()
    for release_gate_operation_id in ("AI-113", "AI-114"):
        operation_contracts.setdefault(release_gate_operation_id, {}).update(
            {
                "x-raos-baseline-evaluation-run-invariants": (
                    evaluation_baseline_invariants()
                ),
                "x-raos-release-regression-invariants": (
                    release_regression_invariants()
                ),
                "x-raos-statistical-evidence-artifact-invariants": (
                    evaluation_statistics_artifact_invariants()
                ),
            }
        )
    for aggregate_scope_operation_id in (
        "AI-108",
        "AI-109",
        "AI-112",
        "AI-113",
        "AI-114",
    ):
        operation_contracts.setdefault(aggregate_scope_operation_id, {})[
            "x-raos-blocking-aggregate-scope-invariants"
        ] = evaluation_blocking_aggregate_scope_invariants()
    for split_coverage_operation_id in (
        "AI-105",
        "AI-106",
        "AI-108",
        "AI-109",
    ):
        operation_contracts.setdefault(split_coverage_operation_id, {})[
            "x-raos-required-split-coverage-invariants"
        ] = evaluation_required_split_coverage_invariants()
    for zero_tolerance_operation_id in (
        "AI-108",
        "AI-109",
        "AI-112",
        "AI-113",
        "AI-114",
    ):
        operation_contracts.setdefault(zero_tolerance_operation_id, {})[
            "x-raos-zero-tolerance-evidence-invariants"
        ] = zero_tolerance_evidence_invariants()
    for cost_latency_operation_id in (
        "AI-108",
        "AI-109",
        "AI-112",
    ):
        operation_contracts.setdefault(cost_latency_operation_id, {})[
            "x-raos-cost-latency-reporting-completeness-invariants"
        ] = cost_latency_reporting_completeness_invariants()
    for canary_safety_operation_id in ("AI-112", "AI-113", "AI-114"):
        operation_contracts.setdefault(canary_safety_operation_id, {})[
            "x-raos-canary-safety-invariants"
        ] = release_canary_safety_invariants()
    for completion_security_operation_id in ("AI-108", "AI-109"):
        operation_contracts.setdefault(completion_security_operation_id, {})[
            "x-raos-completion-execution-security-invariants"
        ] = evaluation_completion_execution_security_invariants()
    for operation_id, extensions in operation_contracts.items():
        matches = [
            operation
            for path_item in paths.values()
            if isinstance(path_item, dict)
            for operation in path_item.values()
            if isinstance(operation, dict)
            and operation.get("operationId") == operation_id
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"expected one Admin operation contract: {operation_id}"
            )
        matches[0].update(extensions)
    document["x-raos-ai-governance"] = {
        "revision_id": REVISION_ID,
        "classification": "INTERNAL",
        "authorization_context": "GLOBAL",
        "new_operation_ids": [f"AI-{number}" for number in range(101, 116)],
        "legacy_ai_004_concurrency_hardening": "DEFERRED_VERSIONED_SUCCESSOR",
        "evaluation_evidence_uniqueness": (
            evaluation_evidence_uniqueness_invariants()
        ),
        "evaluation_run_component_content_snapshot_freeze": (
            evaluation_run_component_snapshot_freeze_invariants()
        ),
        "policy_rule_graph_invariants": policy_rule_graph_invariants(),
        "evaluation_run_completion_evidence_invariants": (
            evaluation_run_completion_evidence_invariants()
        ),
        "evaluation_baseline_invariants": evaluation_baseline_invariants(),
        "evaluation_result_ratio_metric_invariants": (
            evaluation_result_ratio_metric_invariants()
        ),
        "release_regression_invariants": release_regression_invariants(),
        "evaluation_statistics_artifact_invariants": (
            evaluation_statistics_artifact_invariants()
        ),
        "evaluation_blocking_aggregate_scope_invariants": (
            evaluation_blocking_aggregate_scope_invariants()
        ),
        "evaluation_required_split_coverage_invariants": (
            evaluation_required_split_coverage_invariants()
        ),
        "cost_latency_reporting_completeness_invariants": (
            cost_latency_reporting_completeness_invariants()
        ),
        "release_canary_safety_invariants": (
            release_canary_safety_invariants()
        ),
        "evaluation_completion_execution_security_invariants": (
            evaluation_completion_execution_security_invariants()
        ),
        "release_approval": {
            "human_only": True,
            "step_up_required": True,
            "critical_two_person_rule": True,
            "prompt_author_cannot_be_sole_approver": True,
            "canary_to_active_same_aggregate": True,
        },
        "additive_scope_registry": [
            "ai:task:read",
            "ai:config:write",
            "ai:dataset:write",
            "ai:evaluation:write",
            "ai:release:write",
            "ai:release:approve",
            "ai:release:revoke",
        ],
    }
    write_yaml(path, document)


def patch_internal_openapi(
    contracts_root: Path,
    resources: Mapping[str, dict[str, Any]],
    requests: Mapping[str, dict[str, Any]],
) -> None:
    path = contracts_root / "openapi-internal.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    info = document.get("info")
    if not isinstance(info, dict):
        raise RuntimeError("Internal OpenAPI info is missing")
    info["x-raos-wire-change"] = "NONE"
    info["x-raos-ai-governance-revision"] = REVISION_ID
    document["x-raos-ai-governance"] = {
        "admin_contract_ref": "openapi-admin.v0.3.yaml",
        "canonical_adoption_ref": "ai/canonical-adoption.v0.3.yaml",
        "new_internal_http_operations": [],
        "public_exposure": "NONE",
        "database_execution_security": (
            evaluation_completion_execution_security_invariants()
        ),
    }
    # Keeping the worker HTTP surface unchanged is intentional; portable types
    # live in the registry and Admin contract until a versioned consumer exists.
    _ = resources, requests
    write_yaml(path, document)


ASYNC_EVENT_MESSAGES = {
    "jp_raos_ai_evaluation_completed_v2": {
        "event_type": "jp.raos.ai.evaluation_completed.v2",
        "filename": "jp-raos-ai-evaluation-completed-v2.schema.json",
        "summary": "Hash-bound AI Evaluation Runが完了した。",
        "consumers": ["release_gate", "admin_dashboard"],
    },
    "jp_raos_ai_release_decision_approved_v1": {
        "event_type": "jp.raos.ai.release_decision_approved.v1",
        "filename": "jp-raos-ai-release-decision-approved-v1.schema.json",
        "summary": "Human-authorized AI Release Decisionが承認された。",
        "consumers": ["ai_router", "admin_dashboard", "audit_projection"],
    },
    "jp_raos_ai_release_decision_revoked_v1": {
        "event_type": "jp.raos.ai.release_decision_revoked.v1",
        "filename": "jp-raos-ai-release-decision-revoked-v1.schema.json",
        "summary": "Human-authorized AI Release Decisionが取り消された。",
        "consumers": ["ai_router", "rollback_orchestrator", "audit_projection"],
    },
}


def patch_asyncapi(contracts_root: Path) -> None:
    path = contracts_root / "asyncapi.v0.3.yaml"
    document = load_yaml_file(path)
    replace_v02_contract_refs(document)
    components = document.get("components")
    channels = document.get("channels")
    operations = document.get("operations")
    if (
        not isinstance(components, dict)
        or not isinstance(channels, dict)
        or not isinstance(operations, dict)
    ):
        raise RuntimeError("AsyncAPI structure is incomplete")
    messages = components.get("messages")
    if not isinstance(messages, dict):
        raise RuntimeError("AsyncAPI message registry is missing")
    ai_channel = channels.get("ai_events")
    if not isinstance(ai_channel, dict):
        raise RuntimeError("AsyncAPI ai_events channel is missing")
    channel_messages = ai_channel.get("messages")
    if not isinstance(channel_messages, dict):
        raise RuntimeError("AsyncAPI ai_events messages are missing")
    header_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "traceparent": {"type": ["string", "null"]},
            "x-raos-attempt": {"type": "integer", "minimum": 1},
            "x-raos-replay": {"type": "boolean"},
        },
    }
    for key, metadata in ASYNC_EVENT_MESSAGES.items():
        if key in messages or key in channel_messages:
            raise RuntimeError(f"AsyncAPI message collision: {key}")
        messages[key] = {
            "name": key,
            "title": metadata["event_type"],
            "summary": metadata["summary"],
            "contentType": "application/json",
            "headers": copy.deepcopy(header_schema),
            "payload": {"$ref": f"schemas/events/{metadata['filename']}"},
            "x-raos-event-type": metadata["event_type"],
            "x-raos-classification": "CONFIDENTIAL",
            "x-raos-requirements": ["FR-018"],
            "x-raos-consumers": list(metadata["consumers"]),
            "x-raos-ordering": "aggregate_version",
            "x-raos-sensitive-payload-fields": "FORBIDDEN",
        }
        channel_messages[key] = {"$ref": f"#/components/messages/{key}"}
    for operation_name in ("send_ai_events", "receive_ai_events"):
        operation = operations.get(operation_name)
        if not isinstance(operation, dict) or not isinstance(
            operation.get("messages"), list
        ):
            raise RuntimeError(f"AsyncAPI operation is missing: {operation_name}")
        operation["messages"].extend(
            {
                "$ref": f"#/channels/ai_events/messages/{key}"
            }
            for key in ASYNC_EVENT_MESSAGES
        )
    info = document.get("info")
    if not isinstance(info, dict):
        raise RuntimeError("AsyncAPI info is missing")
    info["x-raos-wire-change"] = "NONE"
    document["x-raos-ai-governance"] = {
        "revision_id": REVISION_ID,
        "added_event_types": [
            metadata["event_type"] for metadata in ASYNC_EVENT_MESSAGES.values()
        ],
        "preserved_event_type": "jp.raos.ai.evaluation_completed.v1",
        "dataset_lock_event": "NOT_DEFINED_NO_CONSUMER",
        "evaluation_requested_event": "NOT_DEFINED_NO_CONSUMER",
        "classification": "CONFIDENTIAL",
        "raw_sensitive_fields": "FORBIDDEN",
    }
    write_yaml(path, document)


def enrich_contracts(contracts_root: Path) -> None:
    """Apply the additive Admin/API/event/resource contract delta."""

    # Kept as a named phase so tests can inject a pre-install generation failure.
    resources, requests, _events = generate_type_schemas(contracts_root)
    patch_job_catalog(contracts_root)
    patch_state_transition_catalog(contracts_root)
    patch_resource_catalog(contracts_root, resources, requests)
    patch_schema_registry(contracts_root)
    patch_admin_openapi(contracts_root, resources, requests)
    patch_internal_openapi(contracts_root, resources, requests)
    patch_asyncapi(contracts_root)


def artifact_entry(path: Path, logical_path: str) -> dict[str, Any]:
    content = path.read_bytes()
    return {
        "path": logical_path,
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def source_artifacts() -> list[dict[str, Any]]:
    paths = [
        REPO_ROOT / "scripts" / "build_st0003_revision.py",
        DEFAULT_BUNDLE_ROOT / "README.md",
        *(DATABASE_ROOT / name for name in MIGRATION_PHASES),
        DATABASE_ROOT / GUARDED_DOWNGRADE,
        DATABASE_ROOT / FORWARD_RECOVERY,
    ]
    expected_database = {path.resolve() for path in paths[2:]}
    actual_database = {
        path.resolve()
        for path in DATABASE_ROOT.rglob("*")
        if path.is_file()
    }
    if actual_database != expected_database:
        raise RuntimeError(
            "ST-0003 database source set differs from the formal checkpoints: "
            f"unexpected={sorted(str(path) for path in actual_database - expected_database)}, "
            f"missing={sorted(str(path) for path in expected_database - actual_database)}"
        )
    return [artifact_entry(path, relative_repo_path(path)) for path in paths]


def generated_artifacts(staged_root: Path) -> list[dict[str, Any]]:
    paths = [staged_root / "job-state.v1.yaml"]
    paths.extend(
        sorted(
            path
            for path in (staged_root / "contracts").rglob("*")
            if path.is_file()
        )
    )
    return [
        artifact_entry(
            path,
            f"changes/st-0003/{path.relative_to(staged_root).as_posix()}",
        )
        for path in paths
    ]


def build_manifest(
    staged_root: Path,
    frozen: Mapping[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    generated = generated_artifacts(staged_root)
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0003",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": "scripts/build_st0003_revision.py",
        },
        "provenance": {
            "requirement_ids": ["FR-018"],
            "decision_ids": ["INT-DEC-004"],
            "predecessor": {
                "id": PREDECESSOR_ID,
                "version": "0.2",
                "manifest_path": "changes/st-0002/manifest.yaml",
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
            "ai_sha256sums_declared_file_count": 97,
            "declared_equals_regular_members_excluding_inventory": True,
            "all_member_hashes_verified": True,
            "path_casefold_traversal_symlink_checks": True,
        },
        "compatibility": {
            "classification": "ADDITIVE_PRE_RELEASE_CANONICAL_REVISION",
            "http_path_major": 1,
            "job_message_major": 1,
            "existing_schema_paths_preserved": True,
            "public_openapi_sha256": PUBLIC_OPENAPI_HASH,
            "public_ai_surface": "NONE",
            "legacy_ai_004_concurrency_hardening": "DEFERRED_VERSIONED_SUCCESSOR",
        },
        "ai_adoption": {
            "frozen_catalog_and_template_count": len(
                frozen["catalogs_and_templates"]
            ),
            "frozen_prompt_count": len(frozen["prompts"]),
            "frozen_task_and_evaluation_schema_count": len(frozen["schemas"]),
            "generated_portable_json_schema_type_count": (
                len(resource_schema_definitions())
                + len(request_schema_definitions(resource_schema_definitions()))
                + len(event_schema_definitions())
            ),
            "catalog_internal_versions_rewritten": False,
            "bootstrap_or_review_fixture_count": 0,
        },
        "contract_delta": {
            "admin_operation_ids": [f"AI-{number}" for number in range(101, 116)],
            "internal_http_operation_count": 0,
            "event_types": [
                metadata["event_type"]
                for metadata in ASYNC_EVENT_MESSAGES.values()
            ],
            "public_openapi": {
                "source_archive_member": PUBLIC_OPENAPI_MEMBER,
                "output_path": "changes/st-0003/contracts/openapi-public.v0.1.yaml",
                "sha256": PUBLIC_OPENAPI_HASH,
                "byte_identical": True,
            },
        },
        "postgresql": {
            "minimum_server_version_num": 180000,
            "design_target": "18.4",
            "predecessor": "RAOS-DATA-001@0.1 plus ST-0002",
            "phase_order": list(MIGRATION_PHASES),
            "repeatable_phase": {
                "file": "202607300009_ai_governance_migrate_batch.sql",
                "batch_size": 1000,
                "completion_signal": "automatic_remaining_rows=0",
                "operator_classification_required": ["BLOCKED", "REJECTED"],
            },
            "guarded_downgrade": GUARDED_DOWNGRADE,
            "forward_recovery": FORWARD_RECOVERY,
        },
        "handoff": {
            "ST-0104": "install contracts from this hash-pinned bundle",
            "ST-0105": "generate Python and TypeScript types/clients",
            "ST-0301": "bind SQL payloads to migration runner/history/lock ABI",
            "ST-0306": "complete production role grants and public isolation",
            "ST-0701": "load registries without proposal upsert semantics",
            "ST-0703": "implement hash-bound model routing",
            "ST-0705": "implement evaluation and release-gate runtime",
        },
        "database_execution_security": (
            evaluation_completion_execution_security_invariants()
        ),
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
            "partial generated destination: contracts, manifest, and job-state "
            "must exist together, or none"
        )
    if not any(exists):
        return
    if (
        not contracts.is_dir()
        or not manifest.is_file()
        or not job_state.is_file()
    ):
        raise RuntimeError(f"refusing malformed generated destination: {bundle_root}")
    manifest_document = load_yaml_bytes(manifest.read_bytes(), source=str(manifest))
    document = manifest_document.get("document")
    if (
        not isinstance(document, dict)
        or document.get("id") != REVISION_ID
        or document.get("generated_by") != "scripts/build_st0003_revision.py"
    ):
        raise RuntimeError(f"destination is not owned by {REVISION_ID}")
    entries = manifest_document.get("generated_artifacts")
    if not isinstance(entries, list):
        raise RuntimeError("owned destination manifest is missing generated artifacts")
    if manifest_document.get("generated_artifact_count") != len(entries):
        raise RuntimeError("owned destination generated artifact count is malformed")
    listed: dict[str, Mapping[str, Any]] = {}
    seen_casefold: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("owned destination has malformed artifact entry")
        logical = entry["path"]
        relative = checked_relative_path(logical, source="owned ST-0003 manifest")
        prefix = "changes/st-0003/"
        if not logical.startswith(prefix):
            raise RuntimeError(f"owned artifact escapes bundle: {logical}")
        bundle_relative = logical.removeprefix(prefix)
        if (
            bundle_relative != "job-state.v1.yaml"
            and not bundle_relative.startswith("contracts/")
        ):
            raise RuntimeError(f"unexpected owned artifact path: {logical}")
        folded = bundle_relative.casefold()
        if folded in seen_casefold:
            raise RuntimeError(f"casefold duplicate owned artifact: {logical}")
        seen_casefold.add(folded)
        listed[bundle_relative] = entry
        _ = relative
    actual: dict[str, Path] = {"job-state.v1.yaml": job_state}
    for directory, directory_names, filenames in os.walk(
        contracts,
        followlinks=False,
    ):
        directory_path = Path(directory)
        for name in directory_names:
            child = directory_path / name
            if child.is_symlink():
                raise RuntimeError(f"unowned symlink in generated tree: {child}")
        for name in filenames:
            child = directory_path / name
            if child.is_symlink() or not child.is_file():
                raise RuntimeError(f"unowned special file in generated tree: {child}")
            relative = child.relative_to(bundle_root).as_posix()
            actual[relative] = child
    if set(listed) != set(actual):
        raise RuntimeError(
            "unowned or missing generated files: "
            f"unexpected={sorted(set(actual) - set(listed))}, "
            f"missing={sorted(set(listed) - set(actual))}"
        )
    for relative, path in actual.items():
        entry = listed[relative]
        if (
            entry.get("bytes") != path.stat().st_size
            or entry.get("sha256") != sha256_file(path)
        ):
            raise RuntimeError(f"owned generated artifact hash drift: {relative}")


def install_staged_generation(staged_root: Path, bundle_root: Path) -> None:
    names = ("contracts", "job-state.v1.yaml", "manifest.yaml")
    backups = {
        name: staged_root.parent / f"previous-{name.replace('/', '-')}"
        for name in names
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
    verify_predecessor()
    assert_owned_generated_destination(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)
    checksum_inventory = verify_ai_archive()
    with tempfile.TemporaryDirectory(
        prefix=".raos-st0003-build-",
        dir=bundle_root.parent,
    ) as temporary:
        staged_root = Path(temporary) / "generated"
        staged_root.mkdir()
        frozen = generate_contracts(
            staged_root / "contracts",
            checksum_inventory=checksum_inventory,
        )
        (staged_root / "job-state.v1.yaml").write_bytes(
            PREDECESSOR_JOB_STATE.read_bytes()
        )
        write_yaml(
            staged_root / "manifest.yaml",
            build_manifest(staged_root, frozen),
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
    with tempfile.TemporaryDirectory(prefix="raos-st0003-check-") as temporary:
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
        help="owned output; CLI accepts only changes/st-0003",
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
            result = {"status": "PASS", "story_id": "ST-0003", "mode": "check"}
        else:
            output = args.output.resolve()
            if output != DEFAULT_BUNDLE_ROOT.resolve():
                raise RuntimeError(
                    "--output must be the owned canonical changes/st-0003 bundle"
                )
            build(output)
            result = {
                "status": "PASS",
                "story_id": "ST-0003",
                "mode": "build",
                "output": str(output),
            }
    except (OSError, RuntimeError, ValueError, yaml.YAMLError) as exc:
        print(f"ST-0003 revision build failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
