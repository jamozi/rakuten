#!/usr/bin/env python3
"""Build the deterministic additive ST-1105 V2 inventory and provenance manifest."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
CONTRACT_PATH: Final = Path(
    "changes/st-1105/contracts/admin-visual-accessibility-acceptance.v2.json"
)
BROWSER_CONTRACT_PATH: Final = Path(
    "changes/st-1105/contracts/admin-visual-browser-evidence.v2.json"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1105/fixtures/admin-visual-accessibility.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1105/generated/admin-visual-accessibility-recorded.v2.json"
)
GENERATED_TS_PATH: Final = Path(
    "packages/web-ui/src/admin-visual-accessibility-recorded.v2.ts"
)
MANIFEST_PATH: Final = Path("changes/st-1105/runtime-manifest.v2.json")
BASELINE_PATH: Final = Path("changes/st-1105/baselines/admin-visual.synthetic.v2.json")
EVIDENCE_PATH: Final = Path("changes/st-1105/evidence/local-browser-automated.v2.json")
SCREEN_CATALOG_PATH: Final = Path(
    "docs/canonical/02_ui/RAOS_08_screen_catalog_v1.0.yaml"
)
COMPONENT_CATALOG_PATH: Final = Path(
    "docs/canonical/02_ui/RAOS_08_component_catalog_v1.0.yaml"
)
WORKFLOW_CATALOG_PATH: Final = Path(
    "docs/canonical/02_ui/RAOS_08_workflow_catalog_v1.0.yaml"
)
CHECKLIST_PATH: Final = Path(
    "docs/canonical/02_ui/RAOS_08_accessibility_checklist_v1.0.csv"
)
SUITE_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
GENERATOR_PATH: Final = Path("scripts/build_st1105_admin_visual_accessibility.py")
MAX_INPUT_BYTES: Final = 8 * 1024 * 1024
SHA256_PATTERN: Final = "0123456789abcdef"

OWNED_SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    BROWSER_CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1105/EXECPLAN-20260824-v2.md"),
    Path("changes/st-1105/DEFERRED-VERIFICATION-v2.yaml"),
    Path("changes/st-1105/README.md"),
    Path("changes/st-1105/LOCAL-IMPLEMENTATION-COMPLETION-20260824-v2.yaml"),
    Path("docs/worklogs/ST-1105.md"),
    Path("packages/web-ui/src/admin-visual-accessibility-acceptance-v2.ts"),
    Path("packages/web-ui/src/index.ts"),
    GENERATOR_PATH,
    Path("scripts/check_st1105_admin_acceptance_browser.mjs"),
    Path("tests/st1105_v2/__init__.py"),
    Path("tests/st1105_v2/conftest.py"),
    Path("tests/st1105_v2/test_generation.py"),
    Path("tests/st1105_v2/test_negative.py"),
    Path("tests/st1105/admin-visual-accessibility-v2.test.ts"),
    Path("tests/st1105/admin-visual-accessibility-v2-negative.test.ts"),
)
LOCKED_TOOLCHAIN_PATHS: Final = (
    Path("pyproject.toml"),
    Path("uv.lock"),
    Path("package.json"),
    Path("package-lock.json"),
)


class BuildError(RuntimeError):
    """Sanitized ST-1105 owner-build failure."""


def fail(code: str, field: str) -> NoReturn:
    raise BuildError(f"ST-1105 build failed: {code} field={field}") from None


class UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        fail("YAML_SHAPE_INVALID", "mapping")
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            fail("YAML_DUPLICATE_KEY", "mapping")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in SHA256_PATTERN for character in value)
    )


def _safe_path(root: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        fail("PATH_INVALID", relative.as_posix())
    return root / relative


def read_regular(root: Path, relative: Path) -> bytes:
    path = _safe_path(root, relative)
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            fail("INPUT_UNAVAILABLE", relative.as_posix())
        if stat.S_ISLNK(metadata.st_mode):
            fail("SYMLINK_REJECTED", relative.as_posix())
    try:
        metadata = absolute.stat()
        content = absolute.read_bytes()
    except OSError:
        fail("INPUT_UNAVAILABLE", relative.as_posix())
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not content
        or len(content) != metadata.st_size
        or len(content) > MAX_INPUT_BYTES
    ):
        fail("INPUT_INVALID", relative.as_posix())
    return content


def _mapping(value: object, field: str) -> dict[str, object]:
    if type(value) is not dict or any(
        type(key) is not str for key in cast(dict[object, object], value)
    ):
        fail("SHAPE_INVALID", field)
    return cast(dict[str, object], value)


def _list(value: object, field: str) -> list[object]:
    if type(value) is not list:
        fail("SHAPE_INVALID", field)
    return cast(list[object], value)


def _string(value: object, field: str) -> str:
    if type(value) is not str or not value or value != value.strip():
        fail("VALUE_INVALID", field)
    return value


def _string_list(value: object, field: str) -> list[str]:
    items = _list(value, field)
    result = [_string(item, f"{field}[]") for item in items]
    if len(result) != len(set(result)):
        fail("DUPLICATE_VALUE", field)
    return result


def load_json(root: Path, relative: Path) -> dict[str, object]:
    content = read_regular(root, relative)

    def unique_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                fail("JSON_DUPLICATE_KEY", relative.as_posix())
            value[key] = item
        return value

    try:
        decoded = content.decode("utf-8")
        value = json.loads(
            decoded,
            object_pairs_hook=unique_pairs,
            parse_constant=lambda _value: fail(
                "JSON_NON_FINITE_NUMBER", relative.as_posix()
            ),
        )
    except BuildError:
        raise
    except UnicodeDecodeError, json.JSONDecodeError:
        fail("JSON_INVALID", relative.as_posix())
    return _mapping(value, relative.as_posix())


def load_yaml(root: Path, relative: Path) -> dict[str, object]:
    try:
        value = yaml.load(read_regular(root, relative), Loader=UniqueSafeLoader)
    except BuildError:
        raise
    except Exception:
        fail("YAML_INVALID", relative.as_posix())
    return _mapping(value, relative.as_posix())


def _validate_contract(
    root: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    contract = load_json(root, CONTRACT_PATH)
    browser = load_json(root, BROWSER_CONTRACT_PATH)
    fixture = load_json(root, FIXTURE_PATH)
    if (
        contract.get("schema_version") != 2
        or contract.get("story_id") != "ST-1105"
        or contract.get("local_status") != "LOCAL_IMPLEMENTATION_COMPLETE"
        or contract.get("canonical_status") != "UNCHANGED"
    ):
        fail("CONTRACT_VALUE_INVALID", "document")
    if (
        browser.get("schema_version") != 2
        or browser.get("story_id") != "ST-1105"
        or fixture.get("schema_version") != 2
        or fixture.get("story_id") != "ST-1105"
        or fixture.get("synthetic") is not True
    ):
        fail("CONTRACT_VALUE_INVALID", "supporting_document")
    bindings = _list(contract.get("source_bindings"), "source_bindings")
    seen_paths: set[str] = set()
    for index, value in enumerate(bindings):
        row = _mapping(value, f"source_bindings[{index}]")
        if tuple(row) != ("path", "sha256"):
            fail("CONTRACT_SHAPE_INVALID", f"source_bindings[{index}]")
        path = _string(row["path"], f"source_bindings[{index}].path")
        digest = row["sha256"]
        if path in seen_paths or not _is_sha256(digest):
            fail("CONTRACT_VALUE_INVALID", f"source_bindings[{index}]")
        seen_paths.add(path)
        protected = path.startswith(("docs/canonical/", "contracts/"))
        if protected and sha256(read_regular(root, Path(path))) != digest:
            fail("SOURCE_HASH_DRIFT", path)
    return contract, browser, fixture


def _catalog_by_id(
    root: Path, path: Path, collection_key: str
) -> dict[str, dict[str, object]]:
    document = load_yaml(root, path)
    rows = _list(document.get(collection_key), f"{path}.{collection_key}")
    result: dict[str, dict[str, object]] = {}
    for index, value in enumerate(rows):
        row = _mapping(value, f"{path}.{collection_key}[{index}]")
        identifier = _string(row.get("id"), f"{path}.{collection_key}[{index}].id")
        if identifier in result:
            fail("CATALOG_DUPLICATE_ID", identifier)
        result[identifier] = row
    return result


def _checklist(root: Path, contract: Mapping[str, object]) -> list[dict[str, object]]:
    content = read_regular(root, CHECKLIST_PATH).decode("utf-8-sig")
    try:
        reader = csv.DictReader(io.StringIO(content), strict=True)
        rows = list(reader)
    except csv.Error, UnicodeDecodeError:
        fail("CSV_INVALID", CHECKLIST_PATH.as_posix())
    expected_header = [
        "id",
        "requirement",
        "reference",
        "verification",
        "design_status",
        "implementation_status",
        "test_status",
    ]
    if reader.fieldnames != expected_header or len(rows) != 30:
        fail("CHECKLIST_SHAPE_INVALID", "checklist")
    boundary = _mapping(
        contract["local_acceptance_boundary"], "local_acceptance_boundary"
    )
    automated = set(
        _string_list(
            boundary["locally_automated_check_ids"], "locally_automated_check_ids"
        )
    )
    unavailable = set(
        _string_list(
            boundary["not_locally_automated_check_ids"],
            "not_locally_automated_check_ids",
        )
    )
    ids = [cast(str, row["id"]) for row in rows]
    if automated & unavailable or automated | unavailable != set(ids):
        fail("CHECKLIST_PARTITION_INVALID", "local_acceptance_boundary")
    return [
        {
            **row,
            "local_automation_capability": (
                "SYNTHETIC_PATTERN_AUTOMATED"
                if row["id"] in automated
                else "UNAVAILABLE"
            ),
            "formal_execution_status": "NOT_EXECUTED",
            "manual_execution_status": "NOT_EXECUTED",
        }
        for row in rows
    ]


def build_projection(root: Path = REPO_ROOT) -> dict[str, object]:
    contract, browser, fixture = _validate_contract(root)
    screens_catalog = _catalog_by_id(root, SCREEN_CATALOG_PATH, "screens")
    components_catalog = _catalog_by_id(root, COMPONENT_CATALOG_PATH, "components")
    workflows_catalog = _catalog_by_id(root, WORKFLOW_CATALOG_PATH, "workflows")
    suites_catalog = _catalog_by_id(root, SUITE_CATALOG_PATH, "suites")

    groups = _list(contract["screen_groups"], "screen_groups")
    screen_order: list[str] = []
    story_by_screen: dict[str, str] = {}
    group_screen_ids: dict[str, list[str]] = {}
    for index, value in enumerate(groups):
        group = _mapping(value, f"screen_groups[{index}]")
        if tuple(group) != ("story_id", "screen_ids"):
            fail("CONTRACT_SHAPE_INVALID", f"screen_groups[{index}]")
        story_id = _string(group["story_id"], f"screen_groups[{index}].story_id")
        screen_ids = _string_list(
            group["screen_ids"], f"screen_groups[{index}].screen_ids"
        )
        if story_id in group_screen_ids:
            fail("DUPLICATE_VALUE", "screen_groups.story_id")
        group_screen_ids[story_id] = screen_ids
        for screen_id in screen_ids:
            if screen_id in story_by_screen or screen_id not in screens_catalog:
                fail("SCREEN_SCOPE_INVALID", screen_id)
            story_by_screen[screen_id] = story_id
            screen_order.append(screen_id)
    if len(screen_order) != 44:
        fail("SCREEN_SCOPE_INVALID", "count")

    exposure = _mapping(contract["component_exposure"], "component_exposure")
    if set(exposure) != set(group_screen_ids):
        fail("COMPONENT_SCOPE_INVALID", "story_ids")
    per_screen_components: dict[str, list[str]] = {}
    story_components: dict[str, list[str]] = {}
    component_story_ids: dict[str, set[str]] = {}
    for story_id, value in exposure.items():
        row = _mapping(value, f"component_exposure.{story_id}")
        kind = _string(row.get("kind"), f"component_exposure.{story_id}.kind")
        source = _string(row.get("source"), f"component_exposure.{story_id}.source")
        if not source or kind not in {
            "NOT_EXPOSED_BY_DEPENDENCY",
            "DEPENDENCY_PER_SCREEN_CONTRACT",
            "DEPENDENCY_PER_SCREEN_PROJECTION",
            "DEPENDENCY_STORY_LEVEL_INVENTORY",
        }:
            fail("COMPONENT_SCOPE_INVALID", story_id)
        mappings = _mapping(
            row.get("per_screen"), f"component_exposure.{story_id}.per_screen"
        )
        if not set(mappings).issubset(group_screen_ids[story_id]):
            fail("COMPONENT_SCOPE_INVALID", story_id)
        for screen_id, ids_value in mappings.items():
            component_ids = _string_list(
                ids_value, f"component_exposure.{story_id}.per_screen.{screen_id}"
            )
            if any(
                component_id not in components_catalog for component_id in component_ids
            ):
                fail("COMPONENT_UNKNOWN", screen_id)
            per_screen_components[screen_id] = component_ids
            for component_id in component_ids:
                component_story_ids.setdefault(component_id, set()).add(story_id)
        component_ids = _string_list(
            row.get("story_component_ids"),
            f"component_exposure.{story_id}.story_component_ids",
        )
        if any(
            component_id not in components_catalog for component_id in component_ids
        ):
            fail("COMPONENT_UNKNOWN", story_id)
        story_components[story_id] = component_ids
        for component_id in component_ids:
            component_story_ids.setdefault(component_id, set()).add(story_id)

    workflow_mappings = _list(
        contract["critical_workflow_mappings"], "critical_workflow_mappings"
    )
    workflow_by_screen: dict[str, list[str]] = {
        screen_id: [] for screen_id in screen_order
    }
    workflows: list[dict[str, object]] = []
    expected_workflow_ids = [f"UI-WF-{index:03d}" for index in range(1, 11)]
    for index, value in enumerate(workflow_mappings):
        mapping = _mapping(value, f"critical_workflow_mappings[{index}]")
        workflow_id = _string(mapping.get("workflow_id"), f"workflow[{index}].id")
        screen_ids = _string_list(
            mapping.get("screen_ids"), f"workflow[{index}].screen_ids"
        )
        if workflow_id not in workflows_catalog or any(
            screen_id not in story_by_screen for screen_id in screen_ids
        ):
            fail("WORKFLOW_SCOPE_INVALID", workflow_id)
        mapping_basis = _string(
            mapping.get("mapping_basis"), f"workflow[{index}].basis"
        )
        catalog = workflows_catalog[workflow_id]
        workflows.append(
            {
                "workflow_id": workflow_id,
                "name": catalog["name"],
                "actors": catalog["actors"],
                "steps": catalog["steps"],
                "critical_guards": catalog["critical_guards"],
                "screen_ids": screen_ids,
                "mapping_basis": mapping_basis,
                "business_action_executed": False,
                "formal_execution_status": "NOT_EXECUTED",
            }
        )
        for screen_id in screen_ids:
            workflow_by_screen[screen_id].append(workflow_id)
    if [row["workflow_id"] for row in workflows] != expected_workflow_ids:
        fail("WORKFLOW_SCOPE_INVALID", "order")

    actual_renderer_ids = set(
        _string_list(
            _mapping(
                contract["local_acceptance_boundary"], "local_acceptance_boundary"
            )["actual_dependency_renderer_screen_ids"],
            "actual_dependency_renderer_screen_ids",
        )
    )
    screen_rows: list[dict[str, object]] = []
    for screen_id in screen_order:
        catalog = screens_catalog[screen_id]
        story_id = story_by_screen[screen_id]
        exposure_row = _mapping(exposure[story_id], f"component_exposure.{story_id}")
        screen_rows.append(
            {
                "screen_id": screen_id,
                "source_story_id": story_id,
                "name": catalog["name"],
                "catalog_route": catalog["route"],
                "area": catalog["area"],
                "roles": catalog["roles"],
                "purpose": catalog["purpose"],
                "mvp": catalog["mvp"],
                "critical_action": catalog["critical_action"],
                "api_dependencies": catalog["api_dependencies"],
                "catalog_design_status": catalog["design_status"],
                "catalog_implementation_status": catalog["implementation_status"],
                "catalog_runtime_verification": catalog["runtime_verification"],
                "component_exposure_kind": exposure_row["kind"],
                "component_ids": per_screen_components.get(screen_id, []),
                "story_component_ids": story_components[story_id],
                "workflow_ids": workflow_by_screen[screen_id],
                "local_browser_surface": (
                    "DEPENDENCY_RENDERER_AND_SYNTHETIC_FIXTURE"
                    if screen_id in actual_renderer_ids
                    else "SYNTHETIC_ACCEPTANCE_FIXTURE_ONLY"
                ),
                "catalog_route_registered": False,
                "authentication_established": False,
                "authorization_granted": False,
                "business_action_enabled": False,
            }
        )

    component_inventory = []
    for component_id in sorted(component_story_ids):
        catalog = components_catalog[component_id]
        component_inventory.append(
            {
                "component_id": component_id,
                "name": catalog["name"],
                "area": catalog["area"],
                "purpose": catalog["purpose"],
                "keyboard_required": catalog["keyboard_required"],
                "screen_reader_required": catalog["screen_reader_required"],
                "source_story_ids": sorted(component_story_ids[component_id]),
                "formal_runtime_verification": "NOT_EXECUTED",
            }
        )

    suites = []
    for suite_id in ("TST-023", "TST-024", "TST-025"):
        suite_row = suites_catalog.get(suite_id)
        if suite_row is None:
            fail("SUITE_UNKNOWN", suite_id)
        suites.append({**suite_row, "execution_status": "NOT_EXECUTED"})

    fixture_bytes = read_regular(root, FIXTURE_PATH)
    contract_bytes = read_regular(root, CONTRACT_PATH)
    browser_contract_bytes = read_regular(root, BROWSER_CONTRACT_PATH)
    result: dict[str, object] = {
        "schema_version": 2,
        "story_id": "ST-1105",
        "classification": contract["classification"],
        "local_status": contract["local_status"],
        "canonical_status": contract["canonical_status"],
        "source_mode": "RECORDED_SYNTHETIC_DEV_CI_ONLY",
        "screen_count": len(screen_rows),
        "screen_order": screen_order,
        "screens": screen_rows,
        "component_inventory": component_inventory,
        "component_count": len(component_inventory),
        "critical_workflows": workflows,
        "critical_workflow_count": len(workflows),
        "accessibility_checklist": _checklist(root, contract),
        "formal_suites": suites,
        "browser_contract": {
            "classification": browser["classification"],
            "baseline": _mapping(browser["visual_baseline"], "visual_baseline"),
            "evidence": _mapping(browser["evidence"], "evidence"),
            "zoom_proxy": _mapping(browser["zoom_proxy"], "zoom_proxy"),
        },
        "fixture": {
            "path": FIXTURE_PATH.as_posix(),
            "sha256": sha256(fixture_bytes),
            "bytes": len(fixture_bytes),
            "synthetic": True,
            "template": fixture["template"],
            "security": fixture["security"],
            "authority": fixture["authority"],
        },
        "formal_boundary": contract["formal_suite_boundary"],
        "security_controls": contract["security_controls"],
        "authority": contract["authority"],
        "provenance": {
            "integration": contract["integration_provenance"],
            "acceptance_contract_sha256": sha256(contract_bytes),
            "browser_contract_sha256": sha256(browser_contract_bytes),
            "fixture_sha256": sha256(fixture_bytes),
            "source_bindings": contract["source_bindings"],
        },
        "formal_acceptance_achieved": False,
        "production_eligible": False,
    }
    payload = json.dumps(
        result, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    result["payload_sha256"] = sha256(payload.encode("utf-8"))
    return result


def render_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_typescript(json_bytes: bytes) -> bytes:
    digest = sha256(json_bytes)
    text = json_bytes.decode("utf-8").removesuffix("\n")
    literal = (
        "'"
        + text.replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace("\r", "\\r")
        .replace("\n", "\\n")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
        + "'"
    )
    source = f"""// Generated by scripts/build_st1105_admin_visual_accessibility.py. Do not edit.
import {{ createJsonValue, type JsonObject }} from './serializable.ts';

export const ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_SHA256 =
  '{digest}' as const;

export const ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_JSON =
  {literal} as const;

export const ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2 = createJsonValue(
  JSON.parse(ST1105_ADMIN_VISUAL_ACCESSIBILITY_RECORDED_V2_JSON),
) as unknown as JsonObject;
"""
    return source.encode("utf-8")


def _integrity_artifact(root: Path, path: Path, role: str) -> dict[str, object]:
    content = read_regular(root, path)
    return {
        "uri": f"repo://{path.as_posix()}",
        "role": role,
        "bytes": len(content),
        "sha256": sha256(content),
    }


def _semantic_artifact(path: Path, role: str) -> dict[str, object]:
    return {
        "uri": f"repo://{path.as_posix()}",
        "role": role,
        "semantic_id": path.as_posix(),
        "version": "tracked",
    }


def render_manifest(root: Path, output_bytes: bytes, ts_bytes: bytes) -> bytes:
    contract = load_json(root, CONTRACT_PATH)
    bound_paths = [
        Path(_string(_mapping(value, "source_binding")["path"], "source_binding.path"))
        for value in _list(contract["source_bindings"], "source_bindings")
    ]
    artifacts = [
        *(
            _semantic_artifact(path, "TRACKED_OWNER_SOURCE")
            for path in OWNED_SOURCE_PATHS
        ),
        *(
            _integrity_artifact(root, path, "DEPENDENCY_LOCK")
            if path.name in {"uv.lock", "package-lock.json"}
            else _semantic_artifact(path, "TRACKED_DEPENDENCY_DESCRIPTOR")
            for path in LOCKED_TOOLCHAIN_PATHS
        ),
        *(
            _integrity_artifact(root, path, "IMMUTABLE_CANONICAL")
            if path.as_posix().startswith("docs/canonical/")
            else _semantic_artifact(path, "TRACKED_PREDECESSOR")
            for path in bound_paths
        ),
        {
            "uri": f"repo://{OUTPUT_PATH.as_posix()}",
            "role": "GENERATED_OWNER_OUTPUT",
            "bytes": len(output_bytes),
            "sha256": sha256(output_bytes),
        },
        {
            "uri": f"repo://{GENERATED_TS_PATH.as_posix()}",
            "role": "GENERATED_OWNER_OUTPUT",
            "bytes": len(ts_bytes),
            "sha256": sha256(ts_bytes),
        },
        _integrity_artifact(root, BASELINE_PATH, "RUNTIME_DATA_INTEGRITY"),
        _integrity_artifact(root, EVIDENCE_PATH, "RUNTIME_DATA_INTEGRITY"),
    ]
    manifest = {
        "schema_version": 2,
        "story_id": "ST-1105",
        "classification": "RAOS_SEMANTIC_BUILD_MANIFEST_V2",
        "generator_owner": "build_st1105_admin_visual_accessibility",
        "generator_version": 2,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE",
        "integration_provenance": contract["integration_provenance"],
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
        "generated_outputs": [OUTPUT_PATH.as_posix(), GENERATED_TS_PATH.as_posix()],
        "browser_outputs": [BASELINE_PATH.as_posix(), EVIDENCE_PATH.as_posix()],
        "formal_boundary": contract["formal_suite_boundary"],
        "authority": contract["authority"],
    }
    return render_json(manifest)


def _write_atomic(root: Path, relative: Path, content: bytes) -> None:
    path = _safe_path(root, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        fail("OUTPUT_SYMLINK_REJECTED", relative.as_posix())
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary_name, 0o644)
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _check_bytes(root: Path, relative: Path, expected: bytes) -> None:
    actual = read_regular(root, relative)
    if actual != expected:
        fail("GENERATED_DRIFT", relative.as_posix())


def build(
    root: Path = REPO_ROOT, *, check: bool = False, projection_only: bool = False
) -> None:
    projection_bytes = render_json(build_projection(root))
    typescript_bytes = render_typescript(projection_bytes)
    if check:
        _check_bytes(root, OUTPUT_PATH, projection_bytes)
        _check_bytes(root, GENERATED_TS_PATH, typescript_bytes)
    else:
        _write_atomic(root, OUTPUT_PATH, projection_bytes)
        _write_atomic(root, GENERATED_TS_PATH, typescript_bytes)
    if projection_only:
        return
    manifest_bytes = render_manifest(root, projection_bytes, typescript_bytes)
    if check:
        _check_bytes(root, MANIFEST_PATH, manifest_bytes)
    else:
        _write_atomic(root, MANIFEST_PATH, manifest_bytes)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--projection-only", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        build(check=arguments.check, projection_only=arguments.projection_only)
    except BuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(
        "ST-1105 owner outputs match"
        if arguments.check
        else "ST-1105 owner outputs generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
