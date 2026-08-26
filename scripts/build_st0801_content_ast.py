#!/usr/bin/env python3
"""Validate ST-0801 inputs and build its deterministic evidence manifest."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

import yaml
from yaml.tokens import AliasToken, AnchorToken

try:
    from scripts import build_st0201_postgres_service as shared
except ModuleNotFoundError:  # Direct execution from the scripts directory.
    import build_st0201_postgres_service as shared  # type: ignore[no-redef]


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path("changes/st-0801/contracts/content-ast-loader.v1.yaml")
MANIFEST_PATH: Final = Path("changes/st-0801/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0801_content_ast.py")
CONTRACT_REPOSITORY_PATH: Final = Path(
    "contracts/raos-v0.4/contract-repository.v0.4.json"
)
ST0105_MANIFEST_PATH: Final = Path("changes/st-0105/manifest.json")
UV_CONFIGURATION_PATH: Final = Path("uv.toml")
CONTENT_ROOT: Final = Path("contracts/raos-v0.4/contracts/content")
SCHEMA_ROOT: Final = CONTENT_ROOT / "schemas"
VALID_FIXTURE_ROOT: Final = CONTENT_ROOT / "fixtures/valid"
INVALID_FIXTURE_ROOT: Final = CONTENT_ROOT / "fixtures/invalid"
SOURCE_CONTRACT_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync --no-env-file python scripts/build_st0801_content_ast.py"
)
EXPECTED_CONTRACT_SHA256: Final = (
    "9cdac8135b91ade54cb34d61b58bb98b9a758d0b9312cb171650b527e16a7159"
)
EXPECTED_TOOLCHAIN: Final = {
    "python": "3.14.6",
    "jsonschema": "4.26.0",
    "pydantic": "2.13.4",
    "pydantic_core": "2.46.4",
    "pyyaml": "6.0.3",
    "referencing": "0.37.0",
    "uv": "0.12.1",
}
RUNTIME_DISTRIBUTIONS: Final = {
    "jsonschema": "jsonschema",
    "pydantic": "pydantic",
    "pydantic_core": "pydantic-core",
    "pyyaml": "PyYAML",
    "referencing": "referencing",
}
MAX_SOURCE_ARTIFACT_BYTES: Final = 64 * 1024 * 1024

BLOCK_CODES: Final = (
    "lead",
    "decision_summary",
    "intended_reader",
    "methodology",
    "selection_criteria",
    "heading",
    "paragraph",
    "bullet_list",
    "numbered_list",
    "comparison_table",
    "product_card",
    "recommendation_group",
    "difference_matrix",
    "pros_cons",
    "tradeoff",
    "caution",
    "evidence_note",
    "source_summary",
    "faq",
    "media",
    "internal_links",
    "update_notice",
    "callout",
    "disclosure_slot",
)
ARTICLE_TYPE_CODES: Final = (
    "selection_guide",
    "use_case_recommendation",
    "product_comparison",
    "model_generation_capacity_difference",
    "condition_filtering",
)
SCHEMA_RELATIVE_PATHS: Final = tuple(
    Path(path)
    for path in (
        "blocks/bullet_list.schema.json",
        "blocks/callout.schema.json",
        "blocks/caution.schema.json",
        "blocks/comparison_table.schema.json",
        "blocks/decision_summary.schema.json",
        "blocks/difference_matrix.schema.json",
        "blocks/disclosure_slot.schema.json",
        "blocks/evidence_note.schema.json",
        "blocks/faq.schema.json",
        "blocks/heading.schema.json",
        "blocks/intended_reader.schema.json",
        "blocks/internal_links.schema.json",
        "blocks/lead.schema.json",
        "blocks/media.schema.json",
        "blocks/methodology.schema.json",
        "blocks/numbered_list.schema.json",
        "blocks/paragraph.schema.json",
        "blocks/product_card.schema.json",
        "blocks/pros_cons.schema.json",
        "blocks/recommendation_group.schema.json",
        "blocks/selection_criteria.schema.json",
        "blocks/source_summary.schema.json",
        "blocks/tradeoff.schema.json",
        "blocks/update_notice.schema.json",
        "claim.schema.json",
        "common/rich_text.schema.json",
        "content-ast.schema.json",
        "editorial-review-decision.schema.json",
        "media-asset.schema.json",
        "publication-content-manifest.schema.json",
        "recommendation-methodology.schema.json",
        "seo-metadata.schema.json",
        "structured-data-manifest.schema.json",
    )
)
VALID_FIXTURE_NAMES: Final = tuple(f"{code}.json" for code in ARTICLE_TYPE_CODES)
INVALID_FIXTURE_NAMES: Final = (
    "INV-001-raw-html.json",
    "INV-002-manual-affiliate-url.json",
    "INV-003-auto-publish.json",
    "INV-004-wrong-locale.json",
    "INV-005-unknown-block.json",
    "INV-006-faq-schema-enabled.json",
    "INV-007-disclosure-removable.json",
    "INV-008-comparison-hide-unknown.json",
    "INV-009-extra-finance-field.json",
    "INV-010-invalid-heading-level.json",
    "INV-101-disclosure-not-first.json",
    "INV-102-missing-source-summary.json",
    "INV-103-missing-methodology-block.json",
    "INV-104-duplicate-block-id.json",
    "INV-105-missing-required-article-block.json",
)
TEST_PATHS: Final = (
    Path("tests/st0801/conftest.py"),
    Path("tests/st0801/test_block_matrix.py"),
    Path("tests/st0801/test_contract_binding.py"),
    Path("tests/st0801/test_generation.py"),
    Path("tests/st0801/test_loader.py"),
    Path("tests/st0801/test_negative_cases.py"),
)
GENERATED_BINDING_PATHS: Final = (
    Path("python/raos/generated/contracts/__init__.py"),
    Path("python/raos/generated/contracts/content_ast.py"),
    Path("python/raos/generated/contracts/_internal.py"),
    Path("packages/web-contracts/src/generated/schema-models/index.ts"),
    Path("packages/web-contracts/src/generated/schema-models/types.gen.ts"),
)
BINDING_SUPPORT_PATHS: Final = (Path("packages/web-contracts/package.json"),)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    Path("changes/st-0801/README.md"),
    Path("docs/execplans/ST-0801.md"),
    Path("docs/worklogs/ST-0801.md"),
    GENERATOR_PATH,
    Path("scripts/build_st0201_postgres_service.py"),
    Path(".python-version"),
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("uv.toml"),
    Path("python/raos/__init__.py"),
    Path("python/raos/generated/__init__.py"),
    Path("python/raos/domain/editorial/__init__.py"),
    Path("python/raos/domain/editorial/content_ast.py"),
    Path("tests/conftest.py"),
    Path("tests/st0102/conftest.py"),
    *TEST_PATHS,
    Path("tests/st0102/test_toolchain_contract.py"),
    Path("tests/st0106/test_workflow_contract.py"),
    Path(".github/workflows/ci.yml"),
    Path("Makefile"),
    Path("README.md"),
    ST0105_MANIFEST_PATH,
    CONTRACT_REPOSITORY_PATH,
    CONTENT_ROOT / "RAOS_06_implementation_slices_v0.1.yaml",
    CONTENT_ROOT / "RAOS_06_content_block_catalog_v0.1.yaml",
    CONTENT_ROOT / "RAOS_06_article_type_catalog_v0.1.yaml",
    CONTENT_ROOT / "RAOS_06_schema_registry_v0.1.yaml",
    CONTENT_ROOT / "RAOS_06_content_test_matrix_v0.1.csv",
    INVALID_FIXTURE_ROOT / "expected_results.yaml",
    *(SCHEMA_ROOT / path for path in SCHEMA_RELATIVE_PATHS),
    *(VALID_FIXTURE_ROOT / name for name in VALID_FIXTURE_NAMES),
    *(INVALID_FIXTURE_ROOT / name for name in INVALID_FIXTURE_NAMES),
    *GENERATED_BINDING_PATHS,
    *BINDING_SUPPORT_PATHS,
)

EXPECTED_STORY: Final = {
    "id": "ST-0801",
    "epic_id": "EPIC-08",
    "title": "Content AST types and validator",
    "objective": "24 Blockを実装",
    "depends_on": ["ST-0004", "ST-0105"],
    "requirement_ids": ["FR-007", "FR-008"],
    "design_refs": [],
    "deliverables": ["types", "loader", "fixtures"],
    "acceptance_criteria": ["raw HTML/finance/review body rejected"],
    "test_suites": ["TST-020"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_TST020: Final = {
    "id": "TST-020",
    "name": "Content AST and policy",
    "layer": "content",
    "purpose": "5記事型、Block、Claim、Recommendation、Disclosure",
    "candidate_tools": ["pytest", "schema fixtures"],
    "release_blocking": True,
    "environments": ["CI"],
    "owner": "Engineering",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}
EXPECTED_SLICE: Final = {
    "id": "CONT-SLICE-002",
    "name": "Content AST domain types and loader",
    "objective": "Content AST v1をPython/PydanticとTypeScript型へ生成し、安全なLoaderを実装する",
    "depends_on": ["CONT-SLICE-001"],
    "deliverables": [
        "unknown field rejection",
        "schema version fail closed",
        "round-trip tests",
    ],
    "one_pr_preferred": True,
}


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"{label} must be a string-keyed mapping")
    return value


def _repo_path(uri: object) -> Path:
    if not isinstance(uri, str) or not uri.startswith("repo://"):
        raise RuntimeError("artifact URI must use repo://")
    relative = Path(uri.removeprefix("repo://"))
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe artifact URI: {uri}")
    return relative


def _read_repository_file(
    root: Path, relative: Path, label: str
) -> tuple[bytes, os.stat_result]:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe repository path for {label}: {relative}")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    descriptors: list[int] = []
    content: bytes | None = None
    final_metadata: os.stat_result | None = None
    failure: RuntimeError | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in relative.parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        file_descriptor = os.open(relative.name, file_flags, dir_fd=current)
        descriptors.append(file_descriptor)
        initial_metadata = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(initial_metadata.st_mode)
            or initial_metadata.st_size < 0
            or initial_metadata.st_size > MAX_SOURCE_ARTIFACT_BYTES
        ):
            raise RuntimeError(f"{label} must be a bounded regular file")
        remaining = initial_metadata.st_size
        chunks: list[bytes] = []
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise RuntimeError(f"{label} changed while being read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise RuntimeError(f"{label} changed while being read")
        final_metadata = os.fstat(file_descriptor)
        initial_identity = (
            initial_metadata.st_dev,
            initial_metadata.st_ino,
            initial_metadata.st_size,
            initial_metadata.st_mtime_ns,
            initial_metadata.st_ctime_ns,
        )
        final_identity = (
            final_metadata.st_dev,
            final_metadata.st_ino,
            final_metadata.st_size,
            final_metadata.st_mtime_ns,
            final_metadata.st_ctime_ns,
        )
        if (
            not stat.S_ISREG(final_metadata.st_mode)
            or initial_identity != final_identity
        ):
            raise RuntimeError(f"{label} changed while being read")
        content = b"".join(chunks)
    except RuntimeError as exc:
        failure = exc
    except OSError:
        failure = RuntimeError(f"{label} is unavailable")
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                if failure is None:
                    failure = RuntimeError(f"{label} could not be closed safely")
    if failure is not None:
        raise failure from None
    if content is None or final_metadata is None:
        raise RuntimeError(f"{label} is unavailable")
    return content, final_metadata


def _assert_digest(root: Path, relative: Path, expected: object, label: str) -> bytes:
    if (
        not isinstance(expected, str)
        or shared.SHA256_PATTERN.fullmatch(expected) is None
    ):
        raise RuntimeError(f"{label} has an invalid SHA-256")
    content, _ = _read_repository_file(root, relative, label)
    actual = shared.sha256_bytes(content)
    protected = relative.as_posix().startswith(("docs/canonical/", "contracts/"))
    if protected and actual != expected:
        raise RuntimeError(f"{label} digest drift: {relative}: {actual}")
    return content


def _load_json(content: bytes, label: str) -> Mapping[str, Any]:
    try:
        value = json.loads(content)
    except (UnicodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not valid JSON") from exc
    return _mapping(value, label)


def _load_yaml(content: bytes, label: str) -> Mapping[str, Any]:
    if len(content) > shared.MAX_YAML_BYTES:
        raise RuntimeError(f"{label} exceeds the YAML size limit")
    try:
        text = content.decode("utf-8")
        for token in yaml.scan(text):
            if isinstance(token, (AliasToken, AnchorToken)):
                raise RuntimeError(f"{label} contains a forbidden YAML alias or anchor")
        value = yaml.load(text, Loader=shared.UniqueKeyLoader)
    except UnicodeError as exc:
        raise RuntimeError(f"{label} is not UTF-8 YAML") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"{label} is not valid YAML") from exc
    return _mapping(value, label)


def _select_record(
    document: Mapping[str, Any], collection: str, record_id: str, label: str
) -> Mapping[str, Any]:
    records = document.get(collection)
    if not isinstance(records, list):
        raise RuntimeError(f"{label}.{collection} must be a list")
    matches = [
        item
        for item in records
        if isinstance(item, Mapping) and item.get("id") == record_id
    ]
    if len(matches) != 1:
        raise RuntimeError(f"{label} record {record_id} is missing or duplicated")
    return _mapping(matches[0], f"{label} record {record_id}")


def _inventory_identity(
    metadata: os.stat_result,
) -> tuple[int, int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _exact_file_inventory(root: Path, relative: Path) -> tuple[Path, ...]:
    if (
        relative.is_absolute()
        or not relative.parts
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise RuntimeError(f"unsafe inventory root: {relative}")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NONBLOCK | os.O_NOFOLLOW
    file_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    descriptors: list[int] = []
    tracked_entries: list[
        tuple[int, str, int, tuple[int, int, int, int, int, int]]
    ] = []
    result: list[Path] = []
    root_identity: tuple[int, int, int, int, int, int] | None = None
    root_descriptor: int | None = None
    failure: RuntimeError | None = None

    def open_child(
        parent_descriptor: int,
        name: str,
        display_path: Path,
        *,
        directory: bool,
    ) -> int:
        before = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode):
            raise RuntimeError(f"inventory contains a symlink: {display_path}")
        if directory and not stat.S_ISDIR(before.st_mode):
            raise RuntimeError(f"inventory directory changed: {display_path}")
        if not directory and not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"inventory contains a special file: {display_path}")
        descriptor = os.open(
            name,
            directory_flags if directory else file_flags,
            dir_fd=parent_descriptor,
        )
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
        if not expected_kind(opened.st_mode) or _inventory_identity(
            before
        ) != _inventory_identity(opened):
            raise RuntimeError(f"inventory entry changed: {display_path}")
        tracked_entries.append(
            (
                parent_descriptor,
                name,
                descriptor,
                _inventory_identity(opened),
            )
        )
        return descriptor

    def walk(directory_descriptor: int, local_root: Path) -> None:
        initial_directory = os.fstat(directory_descriptor)
        if not stat.S_ISDIR(initial_directory.st_mode):
            raise RuntimeError(f"inventory directory changed: {relative / local_root}")
        names_before = tuple(sorted(os.listdir(directory_descriptor)))
        for name in names_before:
            if name in {"", ".", ".."} or "/" in name:
                raise RuntimeError("inventory returned an unsafe entry name")
            local_path = local_root / name
            display_path = relative / local_path
            before = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
            if stat.S_ISLNK(before.st_mode):
                raise RuntimeError(f"inventory contains a symlink: {display_path}")
            if stat.S_ISDIR(before.st_mode):
                child_descriptor = open_child(
                    directory_descriptor,
                    name,
                    display_path,
                    directory=True,
                )
                walk(child_descriptor, local_path)
            elif stat.S_ISREG(before.st_mode):
                open_child(
                    directory_descriptor,
                    name,
                    display_path,
                    directory=False,
                )
                result.append(local_path)
            else:
                raise RuntimeError(f"inventory contains a special file: {display_path}")
        names_after = tuple(sorted(os.listdir(directory_descriptor)))
        final_directory = os.fstat(directory_descriptor)
        if names_after != names_before or _inventory_identity(
            final_directory
        ) != _inventory_identity(initial_directory):
            raise RuntimeError(f"inventory directory changed: {relative / local_root}")

    try:
        try:
            root_metadata = os.stat(root, follow_symlinks=False)
        except FileNotFoundError as exc:
            raise RuntimeError("inventory repository root is missing") from exc
        if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(
            root_metadata.st_mode
        ):
            raise RuntimeError("inventory repository root must be a real directory")
        root_identity = _inventory_identity(root_metadata)
        root_descriptor = os.open(root, directory_flags)
        descriptors.append(root_descriptor)
        if _inventory_identity(os.fstat(root_descriptor)) != root_identity:
            raise RuntimeError("inventory repository root changed")

        current_descriptor = root_descriptor
        traversed = Path()
        for part in relative.parts:
            traversed /= part
            current_descriptor = open_child(
                current_descriptor,
                part,
                traversed,
                directory=True,
            )
        walk(current_descriptor, Path())

        if root_identity != _inventory_identity(os.fstat(root_descriptor)):
            raise RuntimeError("inventory repository root changed")
        current_root_metadata = os.stat(root, follow_symlinks=False)
        if stat.S_ISLNK(current_root_metadata.st_mode) or root_identity != (
            _inventory_identity(current_root_metadata)
        ):
            raise RuntimeError("inventory repository root changed")
        for parent_descriptor, name, descriptor, identity in tracked_entries:
            opened_now = os.fstat(descriptor)
            named_now = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
            if identity != _inventory_identity(opened_now) or identity != (
                _inventory_identity(named_now)
            ):
                raise RuntimeError(f"inventory entry changed: {name}")
    except RuntimeError as exc:
        failure = exc
    except OSError:
        failure = RuntimeError(f"inventory is unavailable: {relative}")
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                if failure is None:
                    failure = RuntimeError(
                        "inventory descriptor could not be closed safely"
                    )
    if failure is not None:
        raise failure from None
    return tuple(sorted(result))


def _load_contract_only(root: Path = REPO_ROOT) -> dict[str, Any]:
    content = _assert_digest(
        root, CONTRACT_PATH, EXPECTED_CONTRACT_SHA256, "ST-0801 contract"
    )
    contract = _load_yaml(content, "ST-0801 contract")
    expected_keys = {
        "document",
        "story",
        "authority",
        "predecessors",
        "toolchain",
        "content_contracts",
        "content_ast",
        "schema_inventory",
        "fixture_inventory",
        "generated_bindings",
        "binding_support",
        "loader",
        "fixture_execution",
        "security",
        "verification",
        "boundary",
    }
    if set(contract) != expected_keys:
        raise RuntimeError("ST-0801 contract top-level keys differ")
    shared._require_exact(
        contract["document"],
        {
            "id": "RAOS-CONTENT-AST-LOADER-001",
            "version": "1.0.0",
            "story_id": "ST-0801",
            "implementation_slice": "CONT-SLICE-002",
            "status": "LOCAL_AND_CI_CANDIDATE",
            "formal_verification": "NOT_EXECUTED",
        },
        "ST-0801 contract.document",
    )
    story = _mapping(contract["story"], "ST-0801 contract.story")
    shared._require_exact(story["dependencies"], ["ST-0004", "ST-0105"], "dependencies")
    shared._require_exact(
        story["requirement_ids"], ["FR-007", "FR-008"], "requirements"
    )
    shared._require_exact(story["required_suite"], "TST-020", "required suite")
    shared._require_exact(story["open_decisions"], [], "open decisions")
    authority = _mapping(contract["authority"], "ST-0801 contract.authority")
    controls = _mapping(authority["security_controls"], "security controls")
    shared._require_exact(
        controls["applied_ids"], ["SEC-APP-001", "SEC-APP-004"], "security IDs"
    )
    schema_inventory = _mapping(contract["schema_inventory"], "schema inventory")
    shared._require_exact(schema_inventory["count"], 33, "schema count")
    fixtures = _mapping(contract["fixture_inventory"], "fixture inventory")
    shared._require_exact(fixtures["valid_count"], 5, "valid fixture count")
    shared._require_exact(fixtures["invalid_count"], 15, "invalid fixture count")
    shared._require_exact(
        contract["toolchain"], EXPECTED_TOOLCHAIN, "ST-0801 toolchain"
    )
    content = bytes(content)
    if not content.endswith(b"\n"):
        raise RuntimeError("ST-0801 contract must end with one newline")
    return dict(contract)


def assert_generation_toolchain(root: Path = REPO_ROOT) -> None:
    """Tool versions are verified once by setup/final, not per generator."""

    _ = root


def _validate_authority(contract: Mapping[str, Any], root: Path) -> None:
    authority = _mapping(contract["authority"], "authority")
    authority_content: dict[str, bytes] = {}
    for name, record_value in authority.items():
        record = _mapping(record_value, f"authority.{name}")
        authority_content[name] = _assert_digest(
            root,
            _repo_path(record["uri"]),
            record["sha256"],
            f"authority {name}",
        )

    backlog = _load_yaml(authority_content["story_backlog"], "canonical backlog")
    shared._require_exact(
        dict(_select_record(backlog, "stories", "ST-0801", "canonical backlog")),
        EXPECTED_STORY,
        "canonical ST-0801",
    )
    catalog = _load_yaml(authority_content["test_catalog"], "canonical test catalog")
    shared._require_exact(
        dict(_select_record(catalog, "suites", "TST-020", "canonical test catalog")),
        EXPECTED_TST020,
        "canonical TST-020",
    )
    security = _load_yaml(authority_content["security_controls"], "security catalog")
    for control_id in ("SEC-APP-001", "SEC-APP-004"):
        record = _select_record(security, "controls", control_id, "security catalog")
        if record.get("design_status") != "APPROVED_FOR_IMPLEMENTATION":
            raise RuntimeError(f"canonical {control_id} is not approved")
    open_decisions = _mapping(authority["open_decisions"], "open decisions")
    shared._require_exact(
        open_decisions["story_items"], [], "ST-0801 open-decision projection"
    )
    _load_yaml(authority_content["open_decisions"], "canonical open decisions")


def _validate_content_inputs(contract: Mapping[str, Any], root: Path) -> None:
    content_contracts = _mapping(contract["content_contracts"], "content contracts")
    contract_content: dict[str, bytes] = {}
    for name, record_value in content_contracts.items():
        record = _mapping(record_value, f"content contracts.{name}")
        contract_content[name] = _assert_digest(
            root,
            _repo_path(record["uri"]),
            record["sha256"],
            f"content contract {name}",
        )

    slices = _load_yaml(
        contract_content["implementation_slices"], "implementation slices"
    )
    shared._require_exact(
        dict(
            _select_record(slices, "slices", "CONT-SLICE-002", "implementation slices")
        ),
        EXPECTED_SLICE,
        "CONT-SLICE-002",
    )
    block_catalog = _load_yaml(contract_content["block_catalog"], "block catalog")
    blocks = block_catalog.get("blocks")
    if not isinstance(blocks, list):
        raise RuntimeError("block catalog blocks must be a list")
    shared._require_exact(
        [item.get("code") for item in blocks], list(BLOCK_CODES), "block codes"
    )
    article_catalog = _load_yaml(
        contract_content["article_type_catalog"], "article catalog"
    )
    article_types = article_catalog.get("article_types")
    if not isinstance(article_types, list):
        raise RuntimeError("article catalog article_types must be a list")
    shared._require_exact(
        [item.get("code") for item in article_types],
        list(ARTICLE_TYPE_CODES),
        "article type codes",
    )

    schema_inventory = _mapping(contract["schema_inventory"], "schema inventory")
    schema_artifacts = _mapping(schema_inventory["artifacts"], "schema artifacts")
    expected_schema_paths = tuple(SCHEMA_ROOT / path for path in SCHEMA_RELATIVE_PATHS)
    observed_schema_paths = tuple(_repo_path(uri) for uri in schema_artifacts)
    shared._require_exact(observed_schema_paths, expected_schema_paths, "schema paths")
    shared._require_exact(
        _exact_file_inventory(root, SCHEMA_ROOT),
        SCHEMA_RELATIVE_PATHS,
        "schema directory",
    )
    for uri, digest in schema_artifacts.items():
        schema_bytes = _assert_digest(root, _repo_path(uri), digest, "content schema")
        schema = _load_json(schema_bytes, f"schema {uri}")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise RuntimeError(f"schema draft differs: {uri}")

    registry = _load_yaml(contract_content["schema_registry"], "schema registry")
    registry_rows = registry.get("schemas")
    if not isinstance(registry_rows, list) or len(registry_rows) != 33:
        raise RuntimeError("schema registry must contain exactly 33 records")
    registry_projection = [
        (row.get("path"), row.get("sha256"))
        for row in registry_rows
        if isinstance(row, Mapping)
    ]
    shared._require_exact(
        registry_projection,
        [
            (
                f"schemas/{path.as_posix()}",
                schema_artifacts[f"repo://{(SCHEMA_ROOT / path).as_posix()}"],
            )
            for path in SCHEMA_RELATIVE_PATHS
        ],
        "schema registry projection",
    )

    fixtures = _mapping(contract["fixture_inventory"], "fixture inventory")
    valid = _mapping(fixtures["valid"], "valid fixtures")
    invalid = _mapping(fixtures["invalid"], "invalid fixtures")
    shared._require_exact(tuple(valid), ARTICLE_TYPE_CODES, "valid fixture keys")
    shared._require_exact(
        tuple(f"{name}.json" for name in invalid),
        INVALID_FIXTURE_NAMES,
        "invalid fixture keys",
    )
    shared._require_exact(
        _exact_file_inventory(root, VALID_FIXTURE_ROOT),
        tuple(sorted(Path(name) for name in VALID_FIXTURE_NAMES)),
        "valid fixture directory",
    )
    shared._require_exact(
        _exact_file_inventory(root, INVALID_FIXTURE_ROOT),
        tuple(Path(name) for name in (*INVALID_FIXTURE_NAMES, "expected_results.yaml")),
        "invalid fixture directory",
    )
    for record_value in valid.values():
        record = _mapping(record_value, "valid fixture")
        data = _load_json(
            _assert_digest(
                root, _repo_path(record["uri"]), record["sha256"], "valid fixture"
            ),
            "valid fixture",
        )
        if data.get("article_type") not in ARTICLE_TYPE_CODES:
            raise RuntimeError("valid fixture has an unknown article type")
    for record_value in invalid.values():
        record = _mapping(record_value, "invalid fixture")
        _assert_digest(
            root, _repo_path(record["uri"]), record["sha256"], "invalid fixture"
        )
    expected_results = _mapping(fixtures["expected_results"], "expected results")
    _assert_digest(
        root,
        _repo_path(expected_results["uri"]),
        expected_results["sha256"],
        "invalid fixture expected results",
    )


def _validate_predecessors_and_bindings(
    contract: Mapping[str, Any], root: Path
) -> None:
    predecessors = _mapping(contract["predecessors"], "predecessors")
    for name, record_value in predecessors.items():
        record = _mapping(record_value, f"predecessors.{name}")
        _assert_digest(
            root, _repo_path(record["uri"]), record["sha256"], f"predecessor {name}"
        )

    bindings = _mapping(contract["generated_bindings"], "generated bindings")
    binding_records: list[Mapping[str, Any]] = []
    for language_value in bindings.values():
        language = _mapping(language_value, "generated binding language")
        binding_records.extend(
            _mapping(item, "generated binding") for item in language.values()
        )
    shared._require_exact(
        tuple(_repo_path(record["uri"]) for record in binding_records),
        GENERATED_BINDING_PATHS,
        "generated binding paths",
    )
    for record in binding_records:
        _assert_digest(
            root, _repo_path(record["uri"]), record["sha256"], "generated binding"
        )
    support = _mapping(contract["binding_support"], "binding support")
    support_records = tuple(
        _mapping(item, "binding support artifact") for item in support.values()
    )
    shared._require_exact(
        tuple(_repo_path(record["uri"]) for record in support_records),
        BINDING_SUPPORT_PATHS,
        "binding support paths",
    )
    for record in support_records:
        _assert_digest(
            root, _repo_path(record["uri"]), record["sha256"], "binding support"
        )

    repository = _load_json(
        _assert_digest(
            root,
            CONTRACT_REPOSITORY_PATH,
            _mapping(predecessors["contract_repository"], "contract repository")[
                "sha256"
            ],
            "contract repository manifest",
        ),
        "contract repository manifest",
    )
    repository_artifacts = repository.get("artifacts")
    if not isinstance(repository_artifacts, list):
        raise RuntimeError("contract repository artifacts must be a list")
    repository_index = {
        item["path"]: item for item in repository_artifacts if isinstance(item, Mapping)
    }
    pinned_content_paths = (
        *(
            path.relative_to(Path("contracts/raos-v0.4"))
            for path in SOURCE_ARTIFACT_PATHS
            if path.is_relative_to(CONTENT_ROOT)
        ),
    )
    for path in pinned_content_paths:
        record = repository_index.get(path.as_posix())
        if record is None:
            raise RuntimeError(f"contract repository does not own {path}")
        content, _ = _read_repository_file(
            root,
            Path("contracts/raos-v0.4") / path,
            "installed contract artifact",
        )
        if record.get("bytes") != len(content) or record.get(
            "sha256"
        ) != shared.sha256_bytes(content):
            raise RuntimeError(f"contract repository record drift: {path}")

    generated_manifest = _load_json(
        _assert_digest(
            root,
            ST0105_MANIFEST_PATH,
            _mapping(predecessors["generated_bindings"], "generated predecessor")[
                "sha256"
            ],
            "ST-0105 manifest",
        ),
        "ST-0105 manifest",
    )
    source = _mapping(generated_manifest.get("source"), "ST-0105 source")
    shared._require_exact(
        source.get("contract_repository_manifest_sha256"),
        _mapping(predecessors["contract_repository"], "contract repository")["sha256"],
        "ST-0105 predecessor digest",
    )
    outputs = _mapping(generated_manifest.get("outputs"), "ST-0105 outputs")
    output_rows = outputs.get("artifacts")
    if not isinstance(output_rows, list):
        raise RuntimeError("ST-0105 output artifacts must be a list")
    shared._require_exact(outputs.get("artifact_count"), 354, "ST-0105 output count")
    shared._require_exact(outputs.get("boundary"), "EXACT", "ST-0105 output boundary")
    shared._require_exact(
        outputs.get("roots"),
        ["python/raos/generated", "packages/web-contracts/src/generated"],
        "ST-0105 output roots",
    )
    output_index: dict[str, Mapping[str, Any]] = {}
    for index, item_value in enumerate(output_rows):
        item = _mapping(item_value, f"ST-0105 output[{index}]")
        if set(item) != {"bytes", "path", "sha256"}:
            raise RuntimeError(f"ST-0105 output[{index}] keys differ")
        path_value = item["path"]
        if not isinstance(path_value, str):
            raise RuntimeError(f"ST-0105 output[{index}] path must be a string")
        path = _repo_path(f"repo://{path_value}")
        if path_value in output_index:
            raise RuntimeError(f"ST-0105 output path is duplicated: {path_value}")
        content = _assert_digest(root, path, item["sha256"], f"ST-0105 output[{index}]")
        if type(item["bytes"]) is not int or item["bytes"] != len(content):
            raise RuntimeError(f"ST-0105 output[{index}] byte count differs")
        output_index[path_value] = item
    if len(output_index) != 354:
        raise RuntimeError("ST-0105 output inventory must contain 354 unique paths")
    for record in binding_records:
        path = _repo_path(record["uri"])
        generated = output_index.get(path.as_posix())
        if generated is None or generated.get("sha256") != record["sha256"]:
            raise RuntimeError(f"ST-0105 output record drift: {path}")


def load_and_validate_contract(root: Path = REPO_ROOT) -> dict[str, Any]:
    contract = _load_contract_only(root)
    _validate_authority(contract, root)
    _validate_content_inputs(contract, root)
    _validate_predecessors_and_bindings(contract, root)
    if len(SOURCE_ARTIFACT_PATHS) != 94 or len(set(SOURCE_ARTIFACT_PATHS)) != 94:
        raise RuntimeError("ST-0801 source closure must contain 94 unique paths")
    return contract


def _artifact_record(root: Path, relative: Path) -> dict[str, Any]:
    content, _ = _read_repository_file(root, relative, "source artifact")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": shared.sha256_bytes(content),
    }


def render_manifest(root: Path = REPO_ROOT) -> bytes:
    assert_generation_toolchain(root)
    contract = load_and_validate_contract(root)
    artifacts = [_artifact_record(root, path) for path in SOURCE_ARTIFACT_PATHS]
    manifest = {
        "document": {
            "id": "RAOS-CONTENT-AST-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0801",
            "source_contract": SOURCE_CONTRACT_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "authority": contract["authority"],
            "predecessors": contract["predecessors"],
            "toolchain": contract["toolchain"],
            "content_contracts": contract["content_contracts"],
            "content_ast": contract["content_ast"],
            "schema_inventory": contract["schema_inventory"],
            "fixture_inventory": contract["fixture_inventory"],
            "generated_bindings": contract["generated_bindings"],
            "binding_support": contract["binding_support"],
            "predecessor_recursive_integrity": {
                "story_id": "ST-0105",
                "manifest_uri": f"repo://{ST0105_MANIFEST_PATH.as_posix()}",
                "declared_output_count": 354,
                "verification": "ALL_DECLARED_OUTPUT_BYTES_AND_SHA256_VERIFIED",
            },
        },
        "evidence_chain": {"stories": ["ST-0004", "ST-0104", "ST-0105", "ST-0801"]},
        "source_artifact_count": len(artifacts),
        "source_artifacts": artifacts,
        "generated_artifact_count": 0,
        "generated_artifacts": [],
        "manifest_self_integrity": {
            "included_in_source_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": contract["boundary"],
    }
    return yaml.dump(
        manifest,
        Dumper=shared.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
        width=1000,
    ).encode("utf-8")


def install_manifest(content: bytes, root: Path = REPO_ROOT) -> None:
    try:
        root_metadata = root.lstat()
    except FileNotFoundError as exc:
        raise RuntimeError("manifest root must exist") from exc
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        raise RuntimeError("manifest root must be a real directory")
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptors: list[int] = []
    temporary_name: str | None = None
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in MANIFEST_PATH.parent.parts:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        parent_descriptor = descriptors[-1]
        try:
            target_metadata = os.stat(
                MANIFEST_PATH.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            target_metadata = None
        if target_metadata is not None and not stat.S_ISREG(target_metadata.st_mode):
            raise RuntimeError("manifest target must be a regular non-symlink file")
        for suffix in range(100):
            candidate = f".{MANIFEST_PATH.name}.st0801-{os.getpid()}-{suffix}"
            try:
                output_descriptor = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise RuntimeError("cannot allocate a safe manifest staging file")
        try:
            view = memoryview(content)
            while view:
                written = os.write(output_descriptor, view)
                if written <= 0:
                    raise RuntimeError("short write while staging ST-0801 manifest")
                view = view[written:]
            os.fchmod(output_descriptor, 0o644)
            os.fsync(output_descriptor)
        finally:
            os.close(output_descriptor)
        os.replace(
            temporary_name,
            MANIFEST_PATH.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary_name = None
        os.fsync(parent_descriptor)
    finally:
        if descriptors and temporary_name is not None:
            try:
                os.unlink(temporary_name, dir_fd=descriptors[-1])
            except FileNotFoundError:
                pass
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def check_generated(root: Path = REPO_ROOT) -> None:
    expected = render_manifest(root)
    observed, metadata = _read_repository_file(root, MANIFEST_PATH, "ST-0801 manifest")
    if metadata.st_mode & 0o022:
        raise RuntimeError("ST-0801 manifest cannot be group/world writable")
    if observed != expected:
        raise RuntimeError("generated ST-0801 manifest drift")


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify without writing")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    try:
        if arguments.check:
            check_generated()
            mode = "check"
        else:
            install_manifest(render_manifest())
            mode = "install"
    except (OSError, RuntimeError, yaml.YAMLError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "generated_artifacts": 1,
                "mode": mode,
                "status": "PASS",
                "story_id": "ST-0801",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
