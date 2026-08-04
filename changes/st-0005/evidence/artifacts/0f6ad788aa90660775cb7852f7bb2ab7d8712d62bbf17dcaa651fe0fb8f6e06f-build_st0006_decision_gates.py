#!/usr/bin/env python3
"""Build and validate the ST-0006 open-decision blocker report."""

from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, Final

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode
from yaml.tokens import (
    AliasToken,
    AnchorToken,
    BlockEndToken,
    BlockMappingStartToken,
    BlockSequenceStartToken,
    FlowMappingEndToken,
    FlowMappingStartToken,
    FlowSequenceEndToken,
    FlowSequenceStartToken,
)

SCRIPT_REPO_ROOT = Path(__file__).resolve().parents[1]
if __package__:
    from scripts import import_raos_design
else:
    SCRIPT_MODULE_ROOT = Path(__file__).resolve().parent
    if str(SCRIPT_MODULE_ROOT) not in sys.path:
        sys.path.insert(0, str(SCRIPT_MODULE_ROOT))
    import import_raos_design  # type: ignore[no-redef]  # noqa: E402

REPO_ROOT: Final = SCRIPT_REPO_ROOT
DEFAULT_BUNDLE_ROOT: Final = REPO_ROOT / "changes" / "st-0006"
OPEN_DECISIONS_YAML: Final = (
    REPO_ROOT
    / "docs"
    / "canonical"
    / "01_integration"
    / "RAOS_07_open_decisions_v1.0.yaml"
)
OPEN_DECISIONS_CSV: Final = (
    REPO_ROOT / "docs" / "canonical" / "00_master" / "RAOS_open_decisions_v1.0.csv"
)
REPORT_NAME: Final = "gate-blocker-report.v1.yaml"
MANIFEST_NAME: Final = "manifest.yaml"
CONTRACTS_NAME: Final = "contracts"
SOURCE_SCHEMA_NAME: Final = "open-decision-source.schema.json"
REPORT_SCHEMA_NAME: Final = "gate-blocker-report.schema.json"
POLICY_NAME: Final = "decision-gate-policy.v1.yaml"
GENERATED_NAMES: Final = (CONTRACTS_NAME, REPORT_NAME, MANIFEST_NAME)

REVISION_ID: Final = "RAOS-OPEN-DECISION-GATE-001"
REVISION_VERSION: Final = "1.0.0"
GENERATOR_PATH: Final = "scripts/build_st0006_decision_gates.py"
SOURCE_DOCUMENT_ID: Final = "RAOS-OPEN-DECISIONS-001"
SOURCE_VERSION: Final = "1.0"
SOURCE_STATUS: Final = "ACTIVE"

PINNED_INPUT_HASHES: Final = {
    "docs/manifest.json": (
        "297301b55c70c529e01de2e52ff9a6a0add9c2a7ef4791a9813221316be7501e"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/00_master/RAOS_open_decisions_v1.0.csv": (
        "23a2d5afbdf83e4afeceaa2cbd784cd0e5da4c34fd2eb0ce4fc1dda5671f3276"
    ),
    "docs/canonical/01_integration/RAOS_07_status_taxonomy_v1.0.yaml": (
        "e3261a8a6102c1b93e6cc9006c52f01389ec31510e24ca37bc400437aebbf68b"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
}

EXPECTED_RULES: Final = (
    "未決事項をCodexが推測で確定しない",
    "default_behaviorは安全側へ倒す",
    "blocking=trueはProduction/Gate通過を禁止する",
)
ITEM_FIELDS: Final = (
    "id",
    "topic",
    "status",
    "required_by",
    "owner",
    "decision_needed",
    "default_behavior",
    "blocking",
)
CSV_FIELDS: Final = ITEM_FIELDS
CATALOG_SOURCE_FIELDS: Final = (
    "yaml_uri",
    "yaml_sha256",
    "csv_mirror_uri",
    "csv_mirror_sha256",
)
CURRENT_DECISION_IDS: Final = tuple(f"OD-{index:03d}" for index in range(1, 16))
CURRENT_DECISION_STATUSES: Final = (
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "EXTERNAL_EVIDENCE_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "EXTERNAL_EVIDENCE_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "HUMAN_DECISION_REQUIRED",
    "EXTERNAL_EVIDENCE_REQUIRED",
)
CURRENT_BLOCKER_IDS: Final = tuple(
    identifier for identifier in CURRENT_DECISION_IDS if identifier != "OD-004"
)
ALLOWED_STATUSES: Final = (
    "RESOLVED",
    "PROVISIONAL",
    "HUMAN_DECISION_REQUIRED",
    "EXTERNAL_EVIDENCE_REQUIRED",
)
UNRESOLVED_STATUSES: Final = tuple(
    status for status in ALLOWED_STATUSES if status != "RESOLVED"
)
RELEASE_TARGETS: Final = (
    "GATE-0",
    "GATE-1",
    "GATE-2",
    "GATE-3",
    "GATE-4",
    "PRODUCTION_RELEASE",
)

DECISION_ID_PATTERN: Final = re.compile(r"^OD-[0-9]{3}$")
MAX_YAML_BYTES: Final = 1024 * 1024
MAX_CSV_BYTES: Final = 1024 * 1024
MAX_ARTIFACT_BYTES: Final = 16 * 1024 * 1024
MAX_YAML_DEPTH: Final = 64
MAX_YAML_NODES: Final = 100_000
MAX_STRING_CHARS: Final = 4096


class NoAliasDumper(yaml.SafeDumper):
    """Emit deterministic YAML without anchors or aliases."""

    def ignore_aliases(self, data: object) -> bool:
        return True


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


class RollbackRecoveryRequired(RuntimeError):
    """Installation rollback was incomplete and recovery files were retained."""

    def __init__(self, recovery_path: Path) -> None:
        self.recovery_path = recovery_path
        super().__init__(
            f"generated bundle rollback incomplete; recovery retained at {recovery_path}"
        )


def construct_unique_mapping(
    loader: UniqueKeyLoader, node: MappingNode, deep: bool = False
) -> dict[Any, Any]:
    loader.flatten_mapping(node)
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
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    construct_unique_mapping,
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(
        _read_regular_bounded(path, maximum=MAX_ARTIFACT_BYTES, kind="hash input")
    )


def relative_repo_path(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def source_uri(path: Path) -> str:
    try:
        return f"repo://{relative_repo_path(path)}"
    except ValueError:
        return f"test://{path.name}"


def _has_symlink_component(path: Path) -> bool:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current /= component
        if current.is_symlink():
            return True
    return False


def _read_regular_bounded(path: Path, *, maximum: int, kind: str) -> bytes:
    error = f"required regular {kind} file is missing or unsafe: {path}"
    if _has_symlink_component(path):
        raise RuntimeError(error)
    try:
        before = path.lstat()
    except OSError as exc:
        raise RuntimeError(error) from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
        raise RuntimeError(error)
    if before.st_size > maximum:
        raise RuntimeError(f"{kind} file exceeds {maximum} bytes: {path}")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise RuntimeError(error) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink < 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise RuntimeError(f"{kind} file changed before descriptor open: {path}")
        chunks: list[bytes] = []
        consumed = 0
        while consumed <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - consumed))
            if not chunk:
                break
            chunks.append(chunk)
            consumed += len(chunk)
        if consumed > maximum:
            raise RuntimeError(f"{kind} file exceeds {maximum} bytes: {path}")
        after = os.fstat(descriptor)
        stable_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        )
        stable_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        if stable_before != stable_after or consumed != after.st_size:
            raise RuntimeError(f"{kind} file changed while reading: {path}")
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _parse_yaml_content(content: bytes, *, path: Path) -> dict[str, Any]:
    text = content.decode("utf-8-sig")
    nesting = 0
    tokens = 0
    starts = (
        BlockMappingStartToken,
        BlockSequenceStartToken,
        FlowMappingStartToken,
        FlowSequenceStartToken,
    )
    ends = (BlockEndToken, FlowMappingEndToken, FlowSequenceEndToken)
    for token in yaml.scan(text):
        tokens += 1
        if tokens > MAX_YAML_NODES * 8:
            raise RuntimeError(f"YAML token count exceeds complexity limits: {path}")
        if isinstance(token, (AliasToken, AnchorToken)):
            raise RuntimeError(f"YAML anchors and aliases are forbidden: {path}")
        if isinstance(token, starts):
            nesting += 1
            if nesting > MAX_YAML_DEPTH:
                raise RuntimeError(f"YAML nesting exceeds complexity limits: {path}")
        elif isinstance(token, ends):
            nesting = max(0, nesting - 1)
    loaded = yaml.load(text, Loader=UniqueKeyLoader)
    if not isinstance(loaded, dict):
        raise RuntimeError(f"expected YAML mapping: {path}")
    node_count = 0

    def visit(value: object, depth: int) -> None:
        nonlocal node_count
        node_count += 1
        if node_count > MAX_YAML_NODES or depth > MAX_YAML_DEPTH:
            raise RuntimeError(f"YAML structure exceeds complexity limits: {path}")
        if isinstance(value, dict):
            for key, item in value.items():
                visit(key, depth + 1)
                visit(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, depth + 1)

    visit(loaded, 0)
    return loaded


def load_yaml(path: Path) -> dict[str, Any]:
    content = _read_regular_bounded(path, maximum=MAX_YAML_BYTES, kind="YAML")
    return _parse_yaml_content(content, path=path)


def write_yaml(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            dict(document),
            Dumper=NoAliasDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            width=100,
        ),
        encoding="utf-8",
        newline="\n",
    )


def write_json(path: Path, document: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def require_mapping(value: object, *, source: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RuntimeError(f"expected string-keyed mapping: {source}")
    return value


def require_list(value: object, *, source: str) -> list[Any]:
    if not isinstance(value, list):
        raise RuntimeError(f"expected list: {source}")
    return value


def assert_exact_keys(
    value: Mapping[str, Any], *, required: set[str], source: str
) -> None:
    actual = set(value)
    if actual != required:
        raise RuntimeError(
            f"strict field violation in {source}: "
            f"missing={sorted(required - actual)}, unknown={sorted(actual - required)}"
        )


def require_string(value: object, *, source: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_STRING_CHARS
        or any(ord(character) < 32 for character in value)
    ):
        raise RuntimeError(f"expected bounded non-empty string: {source}")
    return value


def _validate_item(value: object, *, source: str) -> dict[str, Any]:
    item = require_mapping(value, source=source)
    assert_exact_keys(item, required=set(ITEM_FIELDS), source=source)
    normalized: dict[str, Any] = {
        field: require_string(item.get(field), source=f"{source}.{field}")
        for field in ITEM_FIELDS
        if field != "blocking"
    }
    identifier = normalized["id"]
    if not DECISION_ID_PATTERN.fullmatch(identifier):
        raise RuntimeError(f"invalid decision id in {source}: {identifier}")
    if normalized["status"] not in ALLOWED_STATUSES:
        raise RuntimeError(
            f"unknown decision status in {source}: {normalized['status']}"
        )
    blocking = item.get("blocking")
    if type(blocking) is not bool:
        raise RuntimeError(f"blocking must be a strict boolean: {source}")
    normalized["blocking"] = blocking
    return normalized


def _validate_inventory(
    items: Sequence[Mapping[str, Any]], *, require_current_inventory: bool
) -> None:
    identifiers = [item["id"] for item in items]
    if not identifiers:
        raise RuntimeError("open-decision inventory cannot be empty")
    if identifiers != sorted(identifiers):
        raise RuntimeError("open decisions must be sorted by id")
    if len(identifiers) != len(set(identifiers)):
        raise RuntimeError("duplicate open decision id")
    if require_current_inventory and tuple(identifiers) != CURRENT_DECISION_IDS:
        raise RuntimeError(
            "open-decision inventory drift: "
            f"expected={list(CURRENT_DECISION_IDS)}, actual={identifiers}"
        )


def _load_open_decision_yaml_snapshot(
    path: Path = OPEN_DECISIONS_YAML,
    *,
    require_pinned: bool = True,
    require_current_inventory: bool = True,
) -> tuple[dict[str, Any], str]:
    content = _read_regular_bounded(path, maximum=MAX_YAML_BYTES, kind="YAML")
    digest = sha256_bytes(content)
    if require_pinned:
        expected = PINNED_INPUT_HASHES[relative_repo_path(OPEN_DECISIONS_YAML)]
        if path != OPEN_DECISIONS_YAML or digest != expected:
            raise RuntimeError("canonical open-decision YAML hash drift")
    document = _parse_yaml_content(content, path=path)
    assert_exact_keys(
        document,
        required={"document", "rules", "items"},
        source="open-decision YAML",
    )
    metadata = require_mapping(document.get("document"), source="document")
    assert_exact_keys(
        metadata,
        required={"id", "version", "status"},
        source="document",
    )
    expected_metadata = {
        "id": SOURCE_DOCUMENT_ID,
        "version": SOURCE_VERSION,
        "status": SOURCE_STATUS,
    }
    if metadata != expected_metadata:
        raise RuntimeError(f"open-decision document identity drift: {metadata}")
    rules = require_list(document.get("rules"), source="rules")
    normalized_rules = [
        require_string(rule, source=f"rules[{index}]")
        for index, rule in enumerate(rules)
    ]
    if tuple(normalized_rules) != EXPECTED_RULES:
        raise RuntimeError("open-decision safety rules drift")
    raw_items = require_list(document.get("items"), source="items")
    items = [
        _validate_item(item, source=f"items[{index}]")
        for index, item in enumerate(raw_items)
    ]
    _validate_inventory(items, require_current_inventory=require_current_inventory)
    return (
        {
            "document": expected_metadata,
            "rules": normalized_rules,
            "items": items,
        },
        digest,
    )


def load_open_decision_yaml(
    path: Path = OPEN_DECISIONS_YAML,
    *,
    require_pinned: bool = True,
    require_current_inventory: bool = True,
) -> dict[str, Any]:
    document, _digest = _load_open_decision_yaml_snapshot(
        path,
        require_pinned=require_pinned,
        require_current_inventory=require_current_inventory,
    )
    return document


def _load_open_decision_csv_snapshot(
    path: Path = OPEN_DECISIONS_CSV,
    *,
    require_pinned: bool = True,
    require_current_inventory: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    content = _read_regular_bounded(path, maximum=MAX_CSV_BYTES, kind="CSV")
    digest = sha256_bytes(content)
    if require_pinned:
        expected = PINNED_INPUT_HASHES[relative_repo_path(OPEN_DECISIONS_CSV)]
        if path != OPEN_DECISIONS_CSV or digest != expected:
            raise RuntimeError("canonical open-decision CSV hash drift")
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
    if tuple(reader.fieldnames or ()) != CSV_FIELDS:
        raise RuntimeError(
            "open-decision CSV header drift: "
            f"expected={list(CSV_FIELDS)}, actual={reader.fieldnames}"
        )
    items: list[dict[str, Any]] = []
    for row_number, row in enumerate(reader, start=2):
        if None in row or any(value is None for value in row.values()):
            raise RuntimeError(f"malformed open-decision CSV row: {row_number}")
        blocking_text = row["blocking"]
        if blocking_text not in {"True", "False"}:
            raise RuntimeError(
                f"blocking must be True or False in CSV row {row_number}"
            )
        candidate: dict[str, Any] = dict(row)
        candidate["blocking"] = blocking_text == "True"
        items.append(_validate_item(candidate, source=f"CSV row {row_number}"))
    _validate_inventory(items, require_current_inventory=require_current_inventory)
    return items, digest


def load_open_decision_csv(
    path: Path = OPEN_DECISIONS_CSV,
    *,
    require_pinned: bool = True,
    require_current_inventory: bool = True,
) -> list[dict[str, Any]]:
    items, _digest = _load_open_decision_csv_snapshot(
        path,
        require_pinned=require_pinned,
        require_current_inventory=require_current_inventory,
    )
    return items


def assert_pinned_inputs() -> None:
    captured = io.StringIO()
    with contextlib.redirect_stdout(captured):
        import_raos_design.verify_import(REPO_ROOT / "docs")
    lines = captured.getvalue().splitlines()
    if len(lines) != 1:
        raise RuntimeError("complete import verification emitted an invalid result")
    try:
        import_result = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError("complete import verification emitted invalid JSON") from exc
    if not isinstance(import_result, dict) or (
        import_result.get("status"),
        import_result.get("story_id"),
    ) != ("PASS", "ST-0001"):
        raise RuntimeError("complete import verification did not pass")
    for logical, expected in PINNED_INPUT_HASHES.items():
        path = REPO_ROOT / PurePosixPath(logical)
        _read_regular_bounded(path, maximum=MAX_YAML_BYTES, kind="input")
        actual = sha256_file(path)
        if actual != expected:
            raise RuntimeError(
                f"immutable input hash mismatch: {logical}; "
                f"expected={expected}, actual={actual}"
            )


def load_decision_catalog(
    yaml_path: Path = OPEN_DECISIONS_YAML,
    csv_path: Path = OPEN_DECISIONS_CSV,
    *,
    require_pinned: bool = True,
    require_current_inventory: bool = True,
) -> dict[str, Any]:
    yaml_document, yaml_digest = _load_open_decision_yaml_snapshot(
        yaml_path,
        require_pinned=require_pinned,
        require_current_inventory=require_current_inventory,
    )
    csv_items, csv_digest = _load_open_decision_csv_snapshot(
        csv_path,
        require_pinned=require_pinned,
        require_current_inventory=require_current_inventory,
    )
    if yaml_document["items"] != csv_items:
        raise RuntimeError("canonical open-decision YAML/CSV parity mismatch")
    return {
        **yaml_document,
        "source": {
            "yaml_uri": source_uri(yaml_path),
            "yaml_sha256": yaml_digest,
            "csv_mirror_uri": source_uri(csv_path),
            "csv_mirror_sha256": csv_digest,
        },
    }


def is_resolved(status: str) -> bool:
    if status not in ALLOWED_STATUSES:
        raise RuntimeError(f"unknown decision status: {status}")
    return status == "RESOLVED"


def build_policy() -> dict[str, Any]:
    return {
        "document": {
            "id": "RAOS-DECISION-GATE-POLICY-001",
            "version": REVISION_VERSION,
            "story_id": "ST-0006",
            "generated_by": GENERATOR_PATH,
        },
        "source_contract": {
            "document_id": SOURCE_DOCUMENT_ID,
            "canonical_yaml": relative_repo_path(OPEN_DECISIONS_YAML),
            "parity_csv": relative_repo_path(OPEN_DECISIONS_CSV),
            "resolved_status": "RESOLVED",
            "unresolved_statuses": list(UNRESOLVED_STATUSES),
            "unknown_status": "REJECT",
        },
        "mapping": {
            "targets": list(RELEASE_TARGETS),
            "active_blocker": "blocking=true AND status!=RESOLVED",
            "target_policy": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
            "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
            "default_behavior_interpretation": "SAFE_FALLBACK_NOT_RESOLUTION",
            "clear_means_gate_pass": False,
        },
        "boundaries": {
            "decision_resolution_record": "NOT_DEFINED_BY_ST-0006",
            "full_gate_pack_story": "ST-1607",
            "live_status_apply": "NOT_ACTIVATED",
            "deployment": "NOT_ACTIVATED",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
        },
    }


def build_gate_report(catalog: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if catalog is None:
        catalog = load_decision_catalog()
    catalog_document = require_mapping(catalog, source="catalog")
    assert_exact_keys(
        catalog_document,
        required={"document", "rules", "items", "source"},
        source="catalog",
    )
    metadata = require_mapping(
        catalog_document.get("document"), source="catalog.document"
    )
    assert_exact_keys(
        metadata,
        required={"id", "version", "status"},
        source="catalog.document",
    )
    if metadata != {
        "id": SOURCE_DOCUMENT_ID,
        "version": SOURCE_VERSION,
        "status": SOURCE_STATUS,
    }:
        raise RuntimeError("catalog document identity drift")
    rules = require_list(catalog_document.get("rules"), source="catalog.rules")
    if tuple(rules) != EXPECTED_RULES:
        raise RuntimeError("catalog safety rules drift")
    source = require_mapping(catalog_document.get("source"), source="catalog.source")
    assert_exact_keys(
        source,
        required=set(CATALOG_SOURCE_FIELDS),
        source="catalog.source",
    )
    normalized_source = {
        field: require_string(source.get(field), source=f"catalog.source.{field}")
        for field in CATALOG_SOURCE_FIELDS
    }
    for field in ("yaml_sha256", "csv_mirror_sha256"):
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_source[field]):
            raise RuntimeError(f"invalid source SHA-256: catalog.source.{field}")

    raw_items = require_list(catalog_document.get("items"), source="catalog.items")
    items = [
        _validate_item(value, source=f"catalog.items[{index}]")
        for index, value in enumerate(raw_items)
    ]
    _validate_inventory(items, require_current_inventory=False)
    decisions: list[dict[str, Any]] = []
    active_blocker_ids: list[str] = []
    resolved_count = 0
    blocking_count = 0
    unresolved_nonblocking = 0
    for item in items:
        resolved = is_resolved(item["status"])
        active_blocker = item["blocking"] and not resolved
        if resolved:
            resolved_count += 1
        if item["blocking"]:
            blocking_count += 1
        if not resolved and not item["blocking"]:
            unresolved_nonblocking += 1
        blocked_targets = list(RELEASE_TARGETS) if active_blocker else []
        if active_blocker:
            active_blocker_ids.append(item["id"])
        decisions.append(
            {
                "id": item["id"],
                "topic": item["topic"],
                "source_status": item["status"],
                "resolution_state": "RESOLVED" if resolved else "UNRESOLVED",
                "blocking": item["blocking"],
                "active_blocker": active_blocker,
                "required_by": item["required_by"],
                "owner": item["owner"],
                "decision_needed": item["decision_needed"],
                "default_behavior": item["default_behavior"],
                "blocked_targets": blocked_targets,
            }
        )
    targets = [
        {
            "target_id": target,
            "open_decision_check": "BLOCKED" if active_blocker_ids else "CLEAR",
            "blocker_count": len(active_blocker_ids),
            "blocker_decision_ids": list(active_blocker_ids),
        }
        for target in RELEASE_TARGETS
    ]
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "schema_version": 1,
            "story_id": "ST-0006",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": GENERATOR_PATH,
            "generation_command": f"python3 {GENERATOR_PATH}",
        },
        "source": {
            "document_id": SOURCE_DOCUMENT_ID,
            "version": SOURCE_VERSION,
            "status": SOURCE_STATUS,
            **normalized_source,
            "yaml_csv_parity": "PASS",
        },
        "scope": {
            "kind": "OPEN_DECISION_BLOCKERS_ONLY",
            "full_gate_pack_story": "ST-1607",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
        },
        "policy": {
            "resolved_status": "RESOLVED",
            "unresolved_statuses": list(UNRESOLVED_STATUSES),
            "required_by_interpretation": "OPAQUE_CONTEXT_ONLY",
            "target_mapping": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS",
            "clear_does_not_imply_gate_pass": True,
        },
        "counts": {
            "decisions": len(decisions),
            "resolved": resolved_count,
            "unresolved": len(decisions) - resolved_count,
            "blocking": blocking_count,
            "unresolved_blocking": len(active_blocker_ids),
            "unresolved_nonblocking": unresolved_nonblocking,
            "blocked_targets": len(RELEASE_TARGETS) if active_blocker_ids else 0,
        },
        "overall_open_decision_check": ("BLOCKED" if active_blocker_ids else "CLEAR"),
        "decisions": decisions,
        "targets": targets,
        "boundary": {
            "gate_acceptance_decision": "NOT_MADE",
            "production_release_decision": "NOT_MADE",
            "live_status_apply": "NOT_ACTIVATED",
            "deployment": "NOT_ACTIVATED",
            "exceptions": [],
        },
    }


def open_decision_source_schema() -> dict[str, Any]:
    string = {"type": "string", "minLength": 1, "maxLength": MAX_STRING_CHARS}

    def item_schema(identifier: str, status: str) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": list(ITEM_FIELDS),
            "properties": {
                "id": {"const": identifier},
                "topic": string,
                "status": {"const": status},
                "required_by": string,
                "owner": string,
                "decision_needed": string,
                "default_behavior": string,
                "blocking": {"const": identifier in CURRENT_BLOCKER_IDS},
            },
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:raos:st-0006:open-decision-source:v1",
        "title": "RAOS canonical open-decision source",
        "type": "object",
        "additionalProperties": False,
        "required": ["document", "rules", "items"],
        "properties": {
            "document": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "version", "status"],
                "properties": {
                    "id": {"const": SOURCE_DOCUMENT_ID},
                    "version": {"const": SOURCE_VERSION},
                    "status": {"const": SOURCE_STATUS},
                },
            },
            "rules": {
                "type": "array",
                "prefixItems": [{"const": value} for value in EXPECTED_RULES],
                "items": False,
                "minItems": len(EXPECTED_RULES),
                "maxItems": len(EXPECTED_RULES),
            },
            "items": {
                "type": "array",
                "prefixItems": [
                    item_schema(identifier, status)
                    for identifier, status in zip(
                        CURRENT_DECISION_IDS, CURRENT_DECISION_STATUSES, strict=True
                    )
                ],
                "items": False,
                "minItems": len(CURRENT_DECISION_IDS),
                "maxItems": len(CURRENT_DECISION_IDS),
            },
        },
    }


def gate_blocker_report_schema() -> dict[str, Any]:
    bounded_text = {
        "type": "string",
        "minLength": 1,
        "maxLength": MAX_STRING_CHARS,
    }
    all_targets = {
        "type": "array",
        "prefixItems": [{"const": target} for target in RELEASE_TARGETS],
        "items": False,
        "minItems": len(RELEASE_TARGETS),
        "maxItems": len(RELEASE_TARGETS),
    }
    no_targets = {"type": "array", "maxItems": 0}
    blocker_ids = {
        "type": "array",
        "prefixItems": [{"const": identifier} for identifier in CURRENT_BLOCKER_IDS],
        "items": False,
        "minItems": len(CURRENT_BLOCKER_IDS),
        "maxItems": len(CURRENT_BLOCKER_IDS),
    }

    def decision_schema(identifier: str, status: str) -> dict[str, Any]:
        blocking = identifier in CURRENT_BLOCKER_IDS
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "id",
                "topic",
                "source_status",
                "resolution_state",
                "blocking",
                "active_blocker",
                "required_by",
                "owner",
                "decision_needed",
                "default_behavior",
                "blocked_targets",
            ],
            "properties": {
                "id": {"const": identifier},
                "topic": bounded_text,
                "source_status": {"const": status},
                "resolution_state": {"const": "UNRESOLVED"},
                "blocking": {"const": blocking},
                "active_blocker": {"const": blocking},
                "required_by": bounded_text,
                "owner": bounded_text,
                "decision_needed": bounded_text,
                "default_behavior": bounded_text,
                "blocked_targets": all_targets if blocking else no_targets,
            },
        }

    def target_schema(target: str) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "target_id",
                "open_decision_check",
                "blocker_count",
                "blocker_decision_ids",
            ],
            "properties": {
                "target_id": {"const": target},
                "open_decision_check": {"const": "BLOCKED"},
                "blocker_count": {"const": len(CURRENT_BLOCKER_IDS)},
                "blocker_decision_ids": blocker_ids,
            },
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "urn:raos:st-0006:gate-blocker-report:v1",
        "title": "RAOS open-decision gate blocker report",
        "type": "object",
        "additionalProperties": False,
        "required": [
            "document",
            "source",
            "scope",
            "policy",
            "counts",
            "overall_open_decision_check",
            "decisions",
            "targets",
            "boundary",
        ],
        "properties": {
            "document": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "id",
                    "version",
                    "schema_version",
                    "story_id",
                    "status",
                    "generated_by",
                    "generation_command",
                ],
                "properties": {
                    "id": {"const": REVISION_ID},
                    "version": {"const": REVISION_VERSION},
                    "schema_version": {"const": 1},
                    "story_id": {"const": "ST-0006"},
                    "status": {"const": "IMPLEMENTATION_CANDIDATE"},
                    "generated_by": {"const": GENERATOR_PATH},
                    "generation_command": {"const": f"python3 {GENERATOR_PATH}"},
                },
            },
            "source": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "document_id",
                    "version",
                    "status",
                    "yaml_uri",
                    "yaml_sha256",
                    "csv_mirror_uri",
                    "csv_mirror_sha256",
                    "yaml_csv_parity",
                ],
                "properties": {
                    "document_id": {"const": SOURCE_DOCUMENT_ID},
                    "version": {"const": SOURCE_VERSION},
                    "status": {"const": SOURCE_STATUS},
                    "yaml_uri": {
                        "const": f"repo://{relative_repo_path(OPEN_DECISIONS_YAML)}"
                    },
                    "yaml_sha256": {
                        "const": PINNED_INPUT_HASHES[
                            relative_repo_path(OPEN_DECISIONS_YAML)
                        ]
                    },
                    "csv_mirror_uri": {
                        "const": f"repo://{relative_repo_path(OPEN_DECISIONS_CSV)}"
                    },
                    "csv_mirror_sha256": {
                        "const": PINNED_INPUT_HASHES[
                            relative_repo_path(OPEN_DECISIONS_CSV)
                        ]
                    },
                    "yaml_csv_parity": {"const": "PASS"},
                },
            },
            "scope": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kind",
                    "full_gate_pack_story",
                    "formal_tst_005",
                    "formal_tst_032",
                ],
                "properties": {
                    "kind": {"const": "OPEN_DECISION_BLOCKERS_ONLY"},
                    "full_gate_pack_story": {"const": "ST-1607"},
                    "formal_tst_005": {"const": "NOT_EXECUTED"},
                    "formal_tst_032": {"const": "NOT_EXECUTED"},
                },
            },
            "policy": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "resolved_status",
                    "unresolved_statuses",
                    "required_by_interpretation",
                    "target_mapping",
                    "clear_does_not_imply_gate_pass",
                ],
                "properties": {
                    "resolved_status": {"const": "RESOLVED"},
                    "unresolved_statuses": {
                        "type": "array",
                        "prefixItems": [
                            {"const": status} for status in UNRESOLVED_STATUSES
                        ],
                        "items": False,
                        "minItems": len(UNRESOLVED_STATUSES),
                        "maxItems": len(UNRESOLVED_STATUSES),
                    },
                    "required_by_interpretation": {"const": "OPAQUE_CONTEXT_ONLY"},
                    "target_mapping": {"const": "ALL_ACTIVE_BLOCKERS_TO_ALL_TARGETS"},
                    "clear_does_not_imply_gate_pass": {"const": True},
                },
            },
            "counts": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "decisions",
                    "resolved",
                    "unresolved",
                    "blocking",
                    "unresolved_blocking",
                    "unresolved_nonblocking",
                    "blocked_targets",
                ],
                "properties": {
                    "decisions": {"const": len(CURRENT_DECISION_IDS)},
                    "resolved": {"const": 0},
                    "unresolved": {"const": len(CURRENT_DECISION_IDS)},
                    "blocking": {"const": len(CURRENT_BLOCKER_IDS)},
                    "unresolved_blocking": {"const": len(CURRENT_BLOCKER_IDS)},
                    "unresolved_nonblocking": {
                        "const": len(CURRENT_DECISION_IDS) - len(CURRENT_BLOCKER_IDS)
                    },
                    "blocked_targets": {"const": len(RELEASE_TARGETS)},
                },
            },
            "overall_open_decision_check": {"const": "BLOCKED"},
            "decisions": {
                "type": "array",
                "prefixItems": [
                    decision_schema(identifier, status)
                    for identifier, status in zip(
                        CURRENT_DECISION_IDS, CURRENT_DECISION_STATUSES, strict=True
                    )
                ],
                "items": False,
                "minItems": len(CURRENT_DECISION_IDS),
                "maxItems": len(CURRENT_DECISION_IDS),
            },
            "targets": {
                "type": "array",
                "prefixItems": [target_schema(target) for target in RELEASE_TARGETS],
                "items": False,
                "minItems": len(RELEASE_TARGETS),
                "maxItems": len(RELEASE_TARGETS),
            },
            "boundary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "gate_acceptance_decision",
                    "production_release_decision",
                    "live_status_apply",
                    "deployment",
                    "exceptions",
                ],
                "properties": {
                    "gate_acceptance_decision": {"const": "NOT_MADE"},
                    "production_release_decision": {"const": "NOT_MADE"},
                    "live_status_apply": {"const": "NOT_ACTIVATED"},
                    "deployment": {"const": "NOT_ACTIVATED"},
                    "exceptions": {"type": "array", "maxItems": 0},
                },
            },
        },
    }


def source_paths() -> list[Path]:
    fixed = [
        REPO_ROOT / GENERATOR_PATH,
        REPO_ROOT / "scripts" / "import_raos_design.py",
        DEFAULT_BUNDLE_ROOT / "README.md",
        REPO_ROOT / "docs" / "execplans" / "ST-0006.md",
        REPO_ROOT / "docs" / "worklogs" / "ST-0006.md",
    ]
    tests_root = REPO_ROOT / "tests" / "st0006"
    if _has_symlink_component(tests_root) or not tests_root.is_dir():
        raise RuntimeError("ST-0006 test source directory is missing")
    tests = sorted(
        path
        for path in tests_root.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix in {".py", ".yaml", ".json", ".csv"}
    )
    sources = fixed + tests
    for path in sources:
        _read_regular_bounded(path, maximum=MAX_YAML_BYTES, kind="source")
    return sources


def artifact_entry(path: Path, logical_path: str) -> dict[str, Any]:
    content = _read_regular_bounded(path, maximum=MAX_ARTIFACT_BYTES, kind="artifact")
    return {
        "path": logical_path,
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def pinned_input_entry(logical_path: str, expected_sha256: str) -> dict[str, Any]:
    path = REPO_ROOT / PurePosixPath(logical_path)
    entry = artifact_entry(path, logical_path)
    if entry["sha256"] != expected_sha256:
        raise RuntimeError(f"pinned input changed during generation: {logical_path}")
    return entry


def generated_artifacts(staged_root: Path) -> list[dict[str, Any]]:
    paths = [staged_root / REPORT_NAME]
    paths.extend(
        sorted(
            path for path in (staged_root / CONTRACTS_NAME).rglob("*") if path.is_file()
        )
    )
    return [
        artifact_entry(
            path,
            f"changes/st-0006/{path.relative_to(staged_root).as_posix()}",
        )
        for path in paths
    ]


def build_manifest(staged_root: Path, report: Mapping[str, Any]) -> dict[str, Any]:
    generated = generated_artifacts(staged_root)
    return {
        "document": {
            "id": REVISION_ID,
            "version": REVISION_VERSION,
            "story_id": "ST-0006",
            "status": "IMPLEMENTATION_CANDIDATE",
            "generated_by": GENERATOR_PATH,
        },
        "provenance": {
            "design_refs": [SOURCE_DOCUMENT_ID],
            "depends_on": ["ST-0005"],
            "pinned_inputs": [
                pinned_input_entry(path, expected)
                for path, expected in PINNED_INPUT_HASHES.items()
            ],
        },
        "status_boundary": {
            "overall_open_decision_check": report["overall_open_decision_check"],
            "active_blockers": report["counts"]["unresolved_blocking"],
            "blocked_targets": report["counts"]["blocked_targets"],
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_032": "NOT_EXECUTED",
            "gate_acceptance_decision": "NOT_MADE",
            "production_release_decision": "NOT_MADE",
            "live_status_apply": "NOT_ACTIVATED",
            "deployment": "NOT_ACTIVATED",
        },
        "manifest_self_integrity": {
            "path": "changes/st-0006/manifest.yaml",
            "included_in_generated_artifacts": False,
            "reason": "SELF_HASH_RECURSION_AVOIDED",
            "verification": "DETERMINISTIC_REGENERATION_BYTE_COMPARE",
        },
        "safety": {
            "strict_yaml_duplicate_alias_anchor_unknown_field": "REJECT",
            "yaml_csv_parity": "REQUIRED",
            "unknown_decision_status": "REJECT",
            "required_by_gate_inference": "FORBIDDEN",
            "unresolved_blocking_target_policy": "ALL_TARGETS",
            "clear_does_not_imply_gate_pass": True,
            "generated_install": "SIBLING_STAGING_WITH_ROLLBACK",
            "owned_tree_enforced": True,
        },
        "source_artifacts": [
            artifact_entry(path, relative_repo_path(path)) for path in source_paths()
        ],
        "generated_artifact_count": len(generated),
        "generated_artifacts": generated,
    }


def _directory_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect bundle root: {path}") from exc
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"bundle root is not a directory: {path}")
    return metadata.st_dev, metadata.st_ino


def _assert_directory_identity(path: Path, expected: tuple[int, int]) -> None:
    if _directory_identity(path) != expected:
        raise RuntimeError(f"bundle root changed during generation: {path}")


def _directory_open_flags() -> int:
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise RuntimeError("owned generation requires O_DIRECTORY and O_NOFOLLOW")
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _open_pinned_directory(path: Path, expected: tuple[int, int] | None = None) -> int:
    try:
        descriptor = os.open(path, _directory_open_flags())
    except OSError as exc:
        raise RuntimeError(f"cannot open pinned directory: {path}") from exc
    metadata = os.fstat(descriptor)
    identity = (metadata.st_dev, metadata.st_ino)
    if not stat.S_ISDIR(metadata.st_mode) or (
        expected is not None and identity != expected
    ):
        os.close(descriptor)
        raise RuntimeError(f"directory identity changed before install: {path}")
    return descriptor


def _read_regular_at(
    directory_descriptor: int, name: str, *, maximum: int, kind: str
) -> bytes:
    try:
        before = os.stat(name, dir_fd=directory_descriptor, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(
            f"cannot inspect descriptor-relative {kind}: {name}"
        ) from exc
    if not stat.S_ISREG(before.st_mode) or before.st_nlink < 1:
        raise RuntimeError(f"descriptor-relative {kind} is not regular: {name}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NONBLOCK", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(name, flags, dir_fd=directory_descriptor)
    except OSError as exc:
        raise RuntimeError(f"cannot open descriptor-relative {kind}: {name}") from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink < 1
            or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
        ):
            raise RuntimeError(f"descriptor-relative {kind} changed: {name}")
        if opened.st_size > maximum:
            raise RuntimeError(f"descriptor-relative {kind} is oversized: {name}")
        chunks: list[bytes] = []
        consumed = 0
        while consumed <= maximum:
            chunk = os.read(descriptor, min(64 * 1024, maximum + 1 - consumed))
            if not chunk:
                break
            chunks.append(chunk)
            consumed += len(chunk)
        after = os.fstat(descriptor)
        if (
            consumed > maximum
            or consumed != after.st_size
            or (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        ):
            raise RuntimeError(
                f"descriptor-relative {kind} changed while reading: {name}"
            )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _generated_file_map_at(root_descriptor: int) -> dict[str, bytes]:
    allowed_top = {"README.md", CONTRACTS_NAME, MANIFEST_NAME, REPORT_NAME}
    try:
        top_names = set(os.listdir(root_descriptor))
    except OSError as exc:
        raise RuntimeError("cannot enumerate pinned generated bundle") from exc
    if top_names - allowed_top:
        raise RuntimeError("unexpected entry in pinned generated bundle")
    contracts_descriptor = os.open(
        CONTRACTS_NAME,
        _directory_open_flags(),
        dir_fd=root_descriptor,
    )
    try:
        expected_contract_names = {
            SOURCE_SCHEMA_NAME,
            REPORT_SCHEMA_NAME,
            POLICY_NAME,
        }
        if set(os.listdir(contracts_descriptor)) != expected_contract_names:
            raise RuntimeError("pinned generated contract inventory is not exact")
        result = {
            MANIFEST_NAME: _read_regular_at(
                root_descriptor,
                MANIFEST_NAME,
                maximum=MAX_ARTIFACT_BYTES,
                kind="generated manifest",
            ),
            REPORT_NAME: _read_regular_at(
                root_descriptor,
                REPORT_NAME,
                maximum=MAX_ARTIFACT_BYTES,
                kind="generated report",
            ),
        }
        for name in sorted(expected_contract_names):
            result[f"{CONTRACTS_NAME}/{name}"] = _read_regular_at(
                contracts_descriptor,
                name,
                maximum=MAX_ARTIFACT_BYTES,
                kind="generated contract",
            )
        return result
    finally:
        os.close(contracts_descriptor)


def assert_owned_generated_destination(bundle_root: Path) -> tuple[int, int]:
    if _has_symlink_component(bundle_root) or (
        bundle_root.exists() and not bundle_root.is_dir()
    ):
        raise RuntimeError(f"refusing unsafe bundle root: {bundle_root}")
    root_identity = _directory_identity(bundle_root)
    allowed_top_level = {"README.md", *GENERATED_NAMES}
    try:
        top_entries = list(os.scandir(bundle_root))
    except OSError as exc:
        raise RuntimeError(f"cannot enumerate bundle root: {bundle_root}") from exc
    for entry in top_entries:
        child = Path(entry.path)
        if entry.name not in allowed_top_level:
            raise RuntimeError(f"unowned top-level bundle entry: {child}")
        if entry.name == "README.md" and (
            entry.is_symlink() or not entry.is_file(follow_symlinks=False)
        ):
            raise RuntimeError(f"unsafe Story README entry: {child}")
    contracts = bundle_root / CONTRACTS_NAME
    report = bundle_root / REPORT_NAME
    manifest = bundle_root / MANIFEST_NAME
    if contracts.is_symlink() or report.is_symlink() or manifest.is_symlink():
        raise RuntimeError(f"refusing symlinked generated destination: {bundle_root}")
    exists = (contracts.exists(), report.exists(), manifest.exists())
    if any(exists) and not all(exists):
        raise RuntimeError("partial generated destination")
    if not any(exists):
        _assert_directory_identity(bundle_root, root_identity)
        return root_identity
    if not contracts.is_dir() or not report.is_file() or not manifest.is_file():
        raise RuntimeError("malformed generated destination")
    manifest_document = load_yaml(manifest)
    identity = manifest_document.get("document")
    if (
        not isinstance(identity, dict)
        or identity.get("id") != REVISION_ID
        or identity.get("generated_by") != GENERATOR_PATH
    ):
        raise RuntimeError(f"destination is not owned by {REVISION_ID}")
    entries = manifest_document.get("generated_artifacts")
    if not isinstance(entries, list) or manifest_document.get(
        "generated_artifact_count"
    ) != len(entries):
        raise RuntimeError("owned destination manifest inventory is malformed")
    prefix = "changes/st-0006/"
    listed: dict[str, Mapping[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("malformed owned artifact entry")
        logical = entry["path"]
        if not logical.startswith(prefix):
            raise RuntimeError(f"owned artifact escapes bundle: {logical}")
        relative = logical.removeprefix(prefix)
        if relative != REPORT_NAME and not relative.startswith(f"{CONTRACTS_NAME}/"):
            raise RuntimeError(f"unexpected owned artifact path: {logical}")
        if relative.casefold() in {path.casefold() for path in listed}:
            raise RuntimeError(f"casefold duplicate owned artifact: {logical}")
        listed[relative] = entry
    expected_owned = {
        REPORT_NAME,
        f"{CONTRACTS_NAME}/{SOURCE_SCHEMA_NAME}",
        f"{CONTRACTS_NAME}/{REPORT_SCHEMA_NAME}",
        f"{CONTRACTS_NAME}/{POLICY_NAME}",
    }
    if set(listed) != expected_owned:
        raise RuntimeError(
            "owned manifest cannot expand the generated allowlist: "
            f"unexpected={sorted(set(listed) - expected_owned)}, "
            f"missing={sorted(expected_owned - set(listed))}"
        )
    actual: dict[str, Path] = {REPORT_NAME: report}
    try:
        contract_entries = list(os.scandir(contracts))
    except OSError as exc:
        raise RuntimeError(
            f"cannot enumerate generated contracts: {contracts}"
        ) from exc
    for entry in contract_entries:
        child = Path(entry.path)
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            raise RuntimeError(
                f"unowned directory or special file in generated tree: {child}"
            )
        actual[child.relative_to(bundle_root).as_posix()] = child
    if set(listed) != set(actual):
        raise RuntimeError(
            "unowned or missing generated files: "
            f"unexpected={sorted(set(actual) - set(listed))}, "
            f"missing={sorted(set(listed) - set(actual))}"
        )
    for relative, path in actual.items():
        entry = listed[relative]
        if entry.get("bytes") != path.stat().st_size or entry.get(
            "sha256"
        ) != sha256_file(path):
            raise RuntimeError(f"owned generated artifact hash drift: {relative}")
    _assert_directory_identity(bundle_root, root_identity)
    return root_identity


def install_staged_generation(
    staged_root: Path,
    bundle_root: Path,
    *,
    expected_bundle_identity: tuple[int, int],
    expected_staged_identity: tuple[int, int],
    expected_backup_identity: tuple[int, int],
    expected_files: Mapping[str, bytes],
    previous_files: Mapping[str, bytes] | None,
) -> None:
    backups = {name: f"previous-{name.replace('/', '-')}" for name in GENERATED_NAMES}
    moved_old: list[str] = []
    installed_new: list[str] = []
    bundle_descriptor = _open_pinned_directory(bundle_root, expected_bundle_identity)
    try:
        staged_descriptor = _open_pinned_directory(
            staged_root, expected_staged_identity
        )
    except BaseException:
        os.close(bundle_descriptor)
        raise
    try:
        backup_descriptor = _open_pinned_directory(
            staged_root.parent, expected_backup_identity
        )
    except BaseException:
        os.close(staged_descriptor)
        os.close(bundle_descriptor)
        raise
    try:
        _assert_directory_identity(bundle_root, expected_bundle_identity)
        _assert_directory_identity(staged_root, expected_staged_identity)
        _assert_directory_identity(staged_root.parent, expected_backup_identity)
        if _generated_file_map_at(staged_descriptor) != expected_files:
            raise RuntimeError("staged generated files changed before install")
        try:
            os.stat(
                MANIFEST_NAME,
                dir_fd=bundle_descriptor,
                follow_symlinks=False,
            )
            had_previous = True
        except FileNotFoundError:
            had_previous = False
        if had_previous != (previous_files is not None):
            raise RuntimeError("generated destination changed before backup")
        if had_previous:
            for name in GENERATED_NAMES:
                os.replace(
                    name,
                    backups[name],
                    src_dir_fd=bundle_descriptor,
                    dst_dir_fd=backup_descriptor,
                )
                moved_old.append(name)
        for name in GENERATED_NAMES:
            os.replace(
                name,
                name,
                src_dir_fd=staged_descriptor,
                dst_dir_fd=bundle_descriptor,
            )
            installed_new.append(name)
        _assert_directory_identity(bundle_root, expected_bundle_identity)
        if _generated_file_map_at(bundle_descriptor) != expected_files:
            raise RuntimeError("installed generated files differ from staged build")
    except BaseException as install_error:
        rollback_errors: list[BaseException] = []
        for name in reversed(installed_new):
            try:
                os.replace(
                    name,
                    name,
                    src_dir_fd=bundle_descriptor,
                    dst_dir_fd=staged_descriptor,
                )
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        for name in reversed(moved_old):
            try:
                os.replace(
                    backups[name],
                    name,
                    src_dir_fd=backup_descriptor,
                    dst_dir_fd=bundle_descriptor,
                )
            except BaseException as rollback_error:
                rollback_errors.append(rollback_error)
        try:
            rollback_bundle = os.fstat(bundle_descriptor)
            if (rollback_bundle.st_dev, rollback_bundle.st_ino) != (
                expected_bundle_identity
            ):
                raise RuntimeError("pinned bundle descriptor identity changed")
            if previous_files is None:
                restored = True
                for name in GENERATED_NAMES:
                    try:
                        os.stat(
                            name,
                            dir_fd=bundle_descriptor,
                            follow_symlinks=False,
                        )
                    except FileNotFoundError:
                        continue
                    restored = False
                    break
            else:
                restored = _generated_file_map_at(bundle_descriptor) == previous_files
        except BaseException as rollback_error:
            rollback_errors.append(rollback_error)
            restored = False
        if not restored:
            recovery_error = RollbackRecoveryRequired(staged_root.parent)
            if rollback_errors:
                raise recovery_error from rollback_errors[0]
            raise recovery_error from install_error
        raise install_error
    finally:
        os.close(backup_descriptor)
        os.close(staged_descriptor)
        os.close(bundle_descriptor)


def build(bundle_root: Path = DEFAULT_BUNDLE_ROOT) -> dict[str, Any]:
    assert_pinned_inputs()
    bundle_root.mkdir(parents=True, exist_ok=True)
    bundle_identity = assert_owned_generated_destination(bundle_root)
    previous_files = (
        generated_file_map(bundle_root)
        if (bundle_root / MANIFEST_NAME).exists()
        else None
    )
    catalog = load_decision_catalog()
    report = build_gate_report(catalog)
    temporary_root = Path(
        tempfile.mkdtemp(prefix=".raos-st0006-build-", dir=bundle_root.parent)
    )
    backup_identity = _directory_identity(temporary_root)
    retain_recovery = False
    try:
        staged_root = temporary_root / "generated"
        staged_root.mkdir()
        staged_identity = _directory_identity(staged_root)
        write_json(
            staged_root / CONTRACTS_NAME / SOURCE_SCHEMA_NAME,
            open_decision_source_schema(),
        )
        write_json(
            staged_root / CONTRACTS_NAME / REPORT_SCHEMA_NAME,
            gate_blocker_report_schema(),
        )
        write_yaml(staged_root / CONTRACTS_NAME / POLICY_NAME, build_policy())
        write_yaml(staged_root / REPORT_NAME, report)
        write_yaml(staged_root / MANIFEST_NAME, build_manifest(staged_root, report))
        expected_files = generated_file_map(staged_root)
        install_staged_generation(
            staged_root,
            bundle_root,
            expected_bundle_identity=bundle_identity,
            expected_staged_identity=staged_identity,
            expected_backup_identity=backup_identity,
            expected_files=expected_files,
            previous_files=previous_files,
        )
    except RollbackRecoveryRequired:
        retain_recovery = True
        raise
    finally:
        if not retain_recovery:
            _assert_directory_identity(temporary_root, backup_identity)
            shutil.rmtree(temporary_root)
    return report


def generated_file_map(bundle_root: Path) -> dict[str, bytes]:
    allowed_top = {"README.md", CONTRACTS_NAME, MANIFEST_NAME, REPORT_NAME}
    try:
        top_entries = list(os.scandir(bundle_root))
    except OSError as exc:
        raise RuntimeError(f"cannot enumerate generated bundle: {bundle_root}") from exc
    if {entry.name for entry in top_entries} - allowed_top:
        raise RuntimeError(f"unexpected entry in generated bundle: {bundle_root}")
    contracts = bundle_root / CONTRACTS_NAME
    expected_contract_names = {
        SOURCE_SCHEMA_NAME,
        REPORT_SCHEMA_NAME,
        POLICY_NAME,
    }
    try:
        contract_entries = list(os.scandir(contracts))
    except OSError as exc:
        raise RuntimeError(
            f"cannot enumerate generated contracts: {contracts}"
        ) from exc
    if {entry.name for entry in contract_entries} != expected_contract_names or any(
        entry.is_symlink() or not entry.is_file(follow_symlinks=False)
        for entry in contract_entries
    ):
        raise RuntimeError(f"generated contract inventory is not exact: {contracts}")
    paths = [
        bundle_root / MANIFEST_NAME,
        bundle_root / REPORT_NAME,
        *[contracts / name for name in sorted(expected_contract_names)],
    ]
    return {
        path.relative_to(bundle_root).as_posix(): _read_regular_bounded(
            path, maximum=MAX_ARTIFACT_BYTES, kind="generated artifact"
        )
        for path in paths
    }


def check_generated() -> dict[str, Any]:
    assert_owned_generated_destination(DEFAULT_BUNDLE_ROOT)
    with tempfile.TemporaryDirectory(prefix="raos-st0006-check-") as temporary:
        candidate = Path(temporary) / "bundle"
        candidate_report = build(candidate)
        expected = generated_file_map(candidate)
        actual = generated_file_map(DEFAULT_BUNDLE_ROOT)
    if expected == actual:
        return candidate_report
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


def report_evaluation(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "decisions": report["counts"]["decisions"],
        "unresolved_blocking": report["counts"]["unresolved_blocking"],
        "blocked_targets": report["counts"]["blocked_targets"],
        "open_decision_check": report["overall_open_decision_check"],
        "release_authorized": False,
    }


def validate_decisions() -> dict[str, Any]:
    assert_pinned_inputs()
    return report_evaluation(build_gate_report(load_decision_catalog()))


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help="fail if committed generated files differ from a clean build",
    )
    modes.add_argument(
        "--validate-decisions",
        action="store_true",
        help="validate pinned decision inputs and print blocker counts without writing",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_BUNDLE_ROOT)
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] = ()) -> int:
    args = parse_args(argv)
    try:
        if args.output.resolve() != DEFAULT_BUNDLE_ROOT.resolve():
            raise RuntimeError("custom output is forbidden for the ST-0006 CLI")
        if args.check:
            report = check_generated()
            result: dict[str, Any] = {
                "mode": "check",
                **report_evaluation(report),
            }
        elif args.validate_decisions:
            result = {"mode": "validate-decisions", **validate_decisions()}
        else:
            report = build()
            result = {
                "mode": "build",
                "output": str(DEFAULT_BUNDLE_ROOT),
                **report_evaluation(report),
            }
        print(
            json.dumps(
                {
                    "status": "EVALUATED",
                    "command_status": "PASS",
                    "story_id": "ST-0006",
                    **result,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, RuntimeError, UnicodeError, csv.Error, yaml.YAMLError) as exc:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "command_status": "FAIL",
                    "story_id": "ST-0006",
                    "error": str(exc),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
