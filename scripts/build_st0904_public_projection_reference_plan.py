#!/usr/bin/env python3
"""Build the strict non-executable ST-0904 public-projection reference plan."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import importlib
import io
import json
import os
import stat
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


CONTRACT_PATH: Final = Path(
    "changes/st-0904/contracts/public-projection-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0904/generated/public-projection-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0904/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0904_public_projection_reference_plan.py")
README_PATH: Final = Path("changes/st-0904/README.md")
TEST_PATHS: Final = (
    Path("tests/st0904/conftest.py"),
    Path("tests/st0904/test_contract.py"),
    Path("tests/st0904/test_generation.py"),
    Path("tests/st0904/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0904_public_projection_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
CONTRACT_SHA256: Final = (
    "900a5f8d838bf592a815cd136648b43c22546ecf3eb35e7c05bb76cc564e3e7d"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
REQUIREMENTS_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_01_requirements_catalog_v0.1.yaml"
)
MASTER_TRACE_PATH: Final = Path(
    "docs/canonical/00_master/RAOS_master_traceability_v1.0.csv"
)
ACCEPTANCE_TRACE_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_acceptance_traceability_v1.0.csv"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
SNAPSHOT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/common/publication-snapshot.schema.json"
)
DATA_CATALOG_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_catalog_v0.1.yaml"
)
PUBLIC_OPENAPI_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml"
)
INTERNAL_OPENAPI_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/openapi-internal.v0.4.yaml"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
REBUILD_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/"
    "publishing-rebuild-public-projection-v1.schema.json"
)
PUBLISH_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/"
    "publishing-publish-snapshot-v1.schema.json"
)
OPS_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/ops-rebuild-readmodel-v1.schema.json"
)
PROJECTION_EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-public-projection-rebuilt-v1.schema.json"
)
SECURITY_CONTROLS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
THREAT_REGISTER_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"
)

EXPECTED_SOURCES: Final = (
    (
        "integration",
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "canonical_decisions",
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "open_decisions",
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "requirements",
        REQUIREMENTS_PATH.as_posix(),
        "bd4398da2aa73008b7332d2403e7a2e290b7bf1dd77df7bd7e7fd44bb3620827",
    ),
    (
        "master_traceability",
        MASTER_TRACE_PATH.as_posix(),
        "7e9b9bf17582eae90a827fede5d5bab511a0411a50fbfe071fad73e0d11ccbf4",
    ),
    (
        "acceptance_traceability",
        ACCEPTANCE_TRACE_PATH.as_posix(),
        "253293a34e91b81d88dee103da8ee77ed5ff604689c3eb434f0c0ae231d50341",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH.as_posix(),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "system_architecture",
        "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md",
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3",
    ),
    (
        "data_model",
        "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md",
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    ),
    (
        "data_catalog",
        DATA_CATALOG_PATH.as_posix(),
        "187bd1c24ce2a3229d22cfea8f300db840046b5c147d3018a4096625c415933d",
    ),
    (
        "api_event_job_design",
        "docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md",
        "1fe1e73db3c732379f3f83268141d2d1af72e921c0ed60e4d2fc40caf1973fcf",
    ),
    (
        "content_design",
        "docs/upstream/key_documents/RAOS_06_content_editorial_evidence_design_v0.1.md",
        "a40b9859122b330f9db7246f58e7e45f8024f64fde8b07a41ab234ed11cae682",
    ),
    (
        "security_design",
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    (
        "security_controls",
        SECURITY_CONTROLS_PATH.as_posix(),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "role_matrix",
        "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml",
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
    (
        "threat_register",
        THREAT_REGISTER_PATH.as_posix(),
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    ),
    (
        "publication_snapshot_schema",
        SNAPSHOT_SCHEMA_PATH.as_posix(),
        "2b1aa3d1035cd997d3262786fdfd80aa5c25df62e2c758ac481179c5d6803c38",
    ),
    (
        "job_catalog",
        JOB_CATALOG_PATH.as_posix(),
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        "rebuild_public_projection_job_schema",
        REBUILD_JOB_SCHEMA_PATH.as_posix(),
        "a03cadf868e424fc471536b478189e152b28671167c5dde1871d925cceda5a03",
    ),
    (
        "publish_snapshot_job_schema",
        PUBLISH_JOB_SCHEMA_PATH.as_posix(),
        "81f885e435bcaf4af75ab3149a2007668b7585155cfbe730242e78efefc5a6e7",
    ),
    (
        "ops_rebuild_readmodel_job_schema",
        OPS_JOB_SCHEMA_PATH.as_posix(),
        "b59e06560a629f69db4b9f1498c31f2fe8b7dd53768a6f7f3d33ff8353000ae7",
    ),
    (
        "public_projection_rebuilt_event_schema",
        PROJECTION_EVENT_SCHEMA_PATH.as_posix(),
        "b204281bd26c57542219067a6ebd10aeeb68c1ba2dd6925cc6467ac3c420e3f8",
    ),
    (
        "public_openapi",
        PUBLIC_OPENAPI_PATH.as_posix(),
        "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797",
    ),
    (
        "internal_openapi",
        INTERNAL_OPENAPI_PATH.as_posix(),
        "616ea270aec830a987679853869c0d22e1114a95bcf0279d6e635a5f359a6f21",
    ),
)

DEPENDENCY_INPUTS: Final = (
    (
        "ST-0903",
        "changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml",
        "6e9a1fc7f00517f89b0e0c3ff7816595e0455ba73d73d11c613d623312a49fca",
    ),
    (
        "ST-0306",
        "changes/st-0306/contracts/database-roles-grants.v1.yaml",
        "0fa422a6fa8f82e9cf5f1d25f134444211a44ea58e3d62480dee245cadfc2d2a",
    ),
)

EXPECTED_DEPENDENCY_AUTHORITY: Final = {
    "ST-0903": "NONEXECUTABLE_REFERENCE_PLAN_NO_PROJECTABLE_SNAPSHOT",
    "ST-0306": "PUBLIC_READMODEL_ROLE_CANDIDATE_ONLY",
}
EXPECTED_HARD_GATE_ROWS: Final = (
    (
        "ST0904-GATE-001",
        "authoritative_projectable_publication_snapshot",
        "ABSENT",
        "NO_PROJECTION",
        None,
    ),
    (
        "ST0904-GATE-002",
        "exact_confidential_snapshot_to_public_allowlist_and_redaction",
        "NOT_DEFINED",
        "NO_PUBLIC_ROW",
        None,
    ),
    (
        "ST0904-GATE-003",
        "snapshot_database_openapi_readmodel_mapping",
        "UNRESOLVED",
        "KEEP_SURFACES_DISTINCT_NO_PROJECTION",
        None,
    ),
    (
        "ST0904-GATE-004",
        "publish_rebuild_and_ops_job_ownership",
        "UNRESOLVED",
        "NO_JOB_OR_LIFECYCLE_ACTION",
        None,
    ),
    (
        "ST0904-GATE-005",
        "current_snapshot_publication_route_and_scope",
        "NOT_DEFINED",
        "NO_CURRENT_SELECTION_OR_ROUTE",
        None,
    ),
    (
        "ST0904-GATE-006",
        "projection_generation_atomicity_ordering_concurrency_and_deletion",
        "NOT_DEFINED",
        "NO_PROJECTION",
        None,
    ),
    (
        "ST0904-GATE-007",
        "idempotency_inbox_uow_outbox_event_audit_and_crash_recovery",
        "NOT_IMPLEMENTED",
        "NO_SIDE_EFFECT",
        None,
    ),
    (
        "ST0904-GATE-008",
        "safe_offer_freshness_media_seo_disclosure_and_kill_switch_binding",
        "NOT_AUTHORITATIVE",
        "NO_ELIGIBILITY_OR_BINDING",
        None,
    ),
    (
        "ST0904-GATE-009",
        "public_role_isolation_and_runtime_proof",
        "NOT_EXECUTED",
        "NO_PUBLIC_RUNTIME",
        None,
    ),
    (
        "ST0904-GATE-010",
        "executable_pure_or_runtime_projector_authority",
        "ABSENT",
        "REFERENCE_PLAN_ONLY",
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "pro_assistance",
    "authority",
    "dependencies",
    "hard_gates",
    "contract_projection_defaults",
    "record_defaults",
    "execution_defaults",
    "verification_defaults",
    "implementation_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "pro_assistance",
    "authority",
    "provenance",
    "dependencies",
    "hard_gates",
    "contract_projection",
    "record_boundary",
    "execution_boundary",
    "verification_boundary",
    "implementation_boundary",
)


class PublicProjectionReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


_HELPER_MODULE: ModuleType | None = None


def _fail(code: str, field: str) -> NoReturn:
    raise PublicProjectionReferenceError(
        f"ST-0904 build failed: {code} field={field}"
    ) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _same_exact(left: object, right: object) -> bool:
    if type(left) is not type(right):
        return False
    if type(right) is dict:
        left_map = cast(dict[str, object], left)
        right_map = cast(dict[str, object], right)
        return tuple(left_map) == tuple(right_map) and all(
            _same_exact(left_map[key], right_map[key]) for key in right_map
        )
    if type(right) is list:
        left_list = cast(list[object], left)
        right_list = cast(list[object], right)
        return len(left_list) == len(right_list) and all(
            _same_exact(a, b) for a, b in zip(left_list, right_list, strict=True)
        )
    return left == right


def _exact(value: object, expected: object, field: str) -> None:
    if not _same_exact(value, expected):
        _fail("VALUE_MISMATCH", field)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _helper() -> ModuleType:
    """Verify the pinned helper bytes before its first import or execution."""

    global _HELPER_MODULE
    if _HELPER_MODULE is not None:
        return _HELPER_MODULE
    current = REPO_ROOT
    try:
        for part in HELPER_PATH.parts[:-1]:
            current /= part
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                _fail("HELPER_PATH_UNSAFE", "helper")
        target = current / HELPER_PATH.name
        metadata = target.lstat()
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            _fail("HELPER_PATH_UNSAFE", "helper")
        content = target.read_bytes()
    except PublicProjectionReferenceError:
        raise
    except OSError:
        _fail("HELPER_UNAVAILABLE", "helper")
    if len(content) > MAX_SOURCE_BYTES:
        _fail("HELPER_SIZE_LIMIT", "helper")
    if _sha256(content) != HELPER_SHA256:
        _fail("HELPER_HASH_MISMATCH", "helper")
    try:
        module = importlib.import_module("scripts.build_st1505_staging_deployment")
    except Exception:
        _fail("HELPER_IMPORT_FAILED", "helper")
    _HELPER_MODULE = module
    return module


def _expected_dependencies() -> list[dict[str, object]]:
    return [
        {
            "story_id": story_id,
            "artifact": f"repo://{path}",
            "sha256": digest,
            "connection_status": "NOT_EXECUTED",
            "authority_status": EXPECTED_DEPENDENCY_AUTHORITY[story_id],
        }
        for story_id, path, digest in DEPENDENCY_INPUTS
    ]


def _expected_hard_gates() -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    for gate_id, topic, status, safe_default, resolution in EXPECTED_HARD_GATE_ROWS:
        gate: dict[str, object] = {
            "id": gate_id,
            "topic": topic,
            "status": status,
            "safe_default": safe_default,
        }
        if resolution is not None:
            gate["resolution_required"] = resolution
        gates.append(gate)
    return gates


def _read(root: Path, relative: Path, field: str) -> bytes:
    try:
        physical = cast(Path, _helper()._repository_regular_file(root, relative, field))
    except PublicProjectionReferenceError:
        raise
    except RuntimeError:
        _fail("REPOSITORY_PATH_REJECTED", field)
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    _read(root, relative, field)
    try:
        value = _helper().load_yaml(root / relative)
    except PublicProjectionReferenceError:
        raise
    except RuntimeError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


def _json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("JSON_DUPLICATE_KEY", "json")
        result[key] = value
    return result


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)
    try:
        value = json.loads(content.decode("utf-8"), object_pairs_hook=_json_object)
    except UnicodeDecodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", field)
    return _mapping(value, field)


def _text(root: Path, relative: Path, field: str) -> str:
    try:
        return _read(root, relative, field).decode("utf-8-sig")
    except UnicodeDecodeError:
        _fail("UTF8_INVALID", field)


def _find(rows: object, key: str, identifier: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(row, field)
        for row in _list(rows, field)
        if _mapping(row, field).get(key) == identifier
    ]
    if len(matches) != 1:
        _fail("SOURCE_ID_DRIFT", field)
    return matches[0]


def _csv_row(root: Path, relative: Path, identifier: str, field: str) -> dict[str, str]:
    reader = csv.DictReader(io.StringIO(_text(root, relative, field)))
    if reader.fieldnames is None or len(reader.fieldnames) != len(
        set(reader.fieldnames)
    ):
        _fail("CSV_HEADER_INVALID", field)
    matches = [dict(row) for row in reader if row.get("requirement_id") == identifier]
    if len(matches) != 1 or any(value is None for value in matches[0].values()):
        _fail("SOURCE_ID_DRIFT", field)
    return matches[0]


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _validate_hashes(root: Path) -> None:
    if _sha256(_read(root, CONTRACT_PATH, "contract")) != CONTRACT_SHA256:
        _fail("CONTRACT_HASH_MISMATCH", "contract")
    for role, path, expected in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(path), f"source.{role}")) != expected:
            _fail("SOURCE_HASH_MISMATCH", f"source.{role}")
    for story_id, path, expected in DEPENDENCY_INPUTS:
        if _sha256(_read(root, Path(path), f"dependency.{story_id}")) != expected:
            _fail("DEPENDENCY_HASH_MISMATCH", f"dependency.{story_id}")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_HASH_MISMATCH", "helper")


def _validate_st0904_semantics(root: Path, projection: Mapping[str, Any]) -> None:
    story = _find(
        _load_yaml(root, STORY_PATH, "story")["stories"], "id", "ST-0904", "story"
    )
    projected_story = _mapping(projection["story"], "projection.story")
    for key in (
        "id",
        "objective",
        "depends_on",
        "requirement_ids",
        "deliverables",
        "acceptance_criteria",
        "test_suites",
        "open_decisions",
        "design_status",
        "implementation_status",
        "verification_status",
    ):
        _exact(story[key], projected_story[key], f"story.{key}")

    requirement = _find(
        _load_yaml(root, REQUIREMENTS_PATH, "requirements")["functional_requirements"],
        "id",
        "FR-010",
        "requirements",
    )
    _exact(requirement, projection["requirement"], "requirement.FR-010")
    traces = _mapping(projection["trace_variants"], "projection.traces")
    master = _csv_row(root, MASTER_TRACE_PATH, "FR-010", "master_trace")
    acceptance = _csv_row(root, ACCEPTANCE_TRACE_PATH, "FR-010", "acceptance_trace")
    _exact(master["story_ids"].split(";"), traces["master_story_ids"], "trace.stories")
    _exact(
        master["test_suite_ids"].split(";"),
        traces["master_test_suites"],
        "trace.tests",
    )
    try:
        acceptance_tests = ast.literal_eval(acceptance["test_suites"])
    except SyntaxError, ValueError:
        _fail("SOURCE_SEMANTIC_DRIFT", "trace.acceptance.tests")
    _exact(acceptance_tests, traces["acceptance_test_suites"], "trace.acceptance")
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")["suites"]
    for suite_id in ("TST-011", "TST-021"):
        suite = _find(suites, "id", suite_id, f"test.{suite_id}")
        _exact(suite["execution_status"], "NOT_EXECUTED", f"test.{suite_id}")

    snapshot = _load_json(root, SNAPSHOT_SCHEMA_PATH, "snapshot_schema")
    snapshot_projection = _mapping(
        projection["publication_snapshot_schema"], "projection.snapshot"
    )
    _exact(snapshot["title"], snapshot_projection["title"], "snapshot.title")
    _exact(snapshot["required"], snapshot_projection["required"], "snapshot.required")
    _exact(snapshot["additionalProperties"], False, "snapshot.additional")

    catalog = _load_yaml(root, DATA_CATALOG_PATH, "data_catalog")
    readmodel = _find(catalog["schemas"], "id", "readmodel", "data.readmodel")
    tables = _list(readmodel["tables"], "data.tables")
    selected = [
        f"readmodel.{_mapping(row, 'data.table')['name']}"
        for row in tables
        if _mapping(row, "data.table").get("implementation_slice") == "SLICE-016"
    ]
    public_readmodel = _mapping(projection["public_readmodel"], "projection.readmodel")
    _exact(selected, public_readmodel["tables"], "readmodel.tables")
    runtime = _find(tables, "name", "runtime_control", "data.runtime_control")
    _exact(runtime["implementation_slice"], "SLICE-022", "runtime_control.slice")
    _exact(public_readmodel["runtime_control_in_scope"], False, "runtime_control.scope")

    block_table = _find(tables, "name", "public_article_block", "data.block")
    block_checks = block_table["check_constraints"]
    _exact(
        _find(
            block_checks,
            "name",
            "ck_readmodel_public_block_heading",
            "data.block.heading",
        )["expression"],
        "heading_level IS NULL OR heading_level BETWEEN 2 AND 6",
        "data.block.heading",
    )
    card_table = _find(tables, "name", "public_product_card", "data.card")
    _exact(
        _find(card_table["columns"], "name", "badges", "data.card.badges")["type"],
        "jsonb",
        "data.card.badges.type",
    )
    _exact(
        _find(
            card_table["check_constraints"],
            "name",
            "ck_readmodel_public_card_badges",
            "data.card.badges.check",
        )["expression"],
        "jsonb_typeof(badges) = 'object'",
        "data.card.badges.check",
    )
    offer_table = _find(tables, "name", "public_offer", "data.offer")
    _exact(
        _find(
            offer_table["columns"],
            "name",
            "destination_host",
            "data.offer.destination_host",
        )["nullable"],
        True,
        "data.offer.destination_host.nullable",
    )
    _exact(
        _find(
            offer_table["check_constraints"],
            "name",
            "ck_readmodel_public_offer_generation",
            "data.offer.generation",
        )["expression"],
        "projection_generation > 0",
        "data.offer.generation",
    )

    public_openapi = _load_yaml(root, PUBLIC_OPENAPI_PATH, "public_openapi")
    schemas = _mapping(
        _mapping(public_openapi["components"], "public_openapi.components")["schemas"],
        "public_openapi.schemas",
    )
    block_schema = _mapping(schemas["PublicArticleBlock"], "public_openapi.block")
    block_properties = _mapping(
        block_schema["properties"], "public_openapi.block.props"
    )
    heading = _mapping(block_properties["heading_level"], "public_openapi.heading")
    _exact((heading["minimum"], heading["maximum"]), (2, 4), "public_openapi.heading")
    card_schema = _mapping(schemas["PublicProductCard"], "public_openapi.card")
    card_properties = _mapping(card_schema["properties"], "public_openapi.card.props")
    _exact(
        _mapping(card_properties["badges"], "public_openapi.badges")["type"],
        "array",
        "public_openapi.badges.type",
    )
    offer_schema = _mapping(schemas["PublicOffer"], "public_openapi.offer")
    offer_properties = _mapping(
        offer_schema["properties"], "public_openapi.offer.props"
    )
    _exact(
        _mapping(offer_properties["destination_host"], "public_openapi.destination")[
            "type"
        ],
        "string",
        "public_openapi.destination.type",
    )
    if "destination_host" not in _list(
        offer_schema["required"], "public_openapi.offer.required"
    ):
        _fail("SOURCE_SEMANTIC_DRIFT", "public_openapi.destination.required")
    article_schema = _mapping(
        schemas["PublicArticleDocument"], "public_openapi.article"
    )
    article_properties = _mapping(
        article_schema["properties"], "public_openapi.article.props"
    )
    _exact(
        _mapping(
            article_properties["projection_generation"],
            "public_openapi.projection_generation",
        )["minimum"],
        0,
        "public_openapi.projection_generation.minimum",
    )

    dependencies = {story_id: Path(path) for story_id, path, _ in DEPENDENCY_INPUTS}
    predecessor = _load_yaml(root, dependencies["ST-0903"], "dependency.ST-0903")
    predecessor_document = _mapping(predecessor["document"], "dependency.ST-0903")
    _exact(predecessor_document["executable"], False, "dependency.ST-0903.executable")
    _exact(
        predecessor_document["snapshot_builder_authorized"],
        False,
        "dependency.ST-0903.builder",
    )
    roles = _load_yaml(root, dependencies["ST-0306"], "dependency.ST-0306")
    public_boundary = _mapping(roles["public_boundary"], "roles.public_boundary")
    role_projection = _mapping(projection["role_boundary"], "projection.roles")
    _exact(
        public_boundary["schema_usage"],
        role_projection["public_role_schema_usage"],
        "roles.schema_usage",
    )
    _exact(
        public_boundary["table_privileges"],
        role_projection["public_role_table_privileges"],
        "roles.table_privileges",
    )

    jobs = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")["jobs"]
    job_projection = _mapping(projection["job_surfaces"], "projection.jobs")
    for field, job_type in (
        ("publish_snapshot", "publishing.publish_snapshot.v1"),
        ("rebuild_public_projection", "publishing.rebuild_public_projection.v1"),
        ("ops_rebuild_readmodel", "ops.rebuild_readmodel.v1"),
    ):
        job = _find(jobs, "job_type", job_type, f"job.{field}")
        expected = _mapping(job_projection[field], f"projection.job.{field}")
        _exact(job["job_type"], expected["job_type"], f"job.{field}.type")
        _exact(
            job["implementation_slice"],
            expected["implementation_slice"],
            f"job.{field}.slice",
        )
    rebuild = _find(
        jobs,
        "job_type",
        "publishing.rebuild_public_projection.v1",
        "job.rebuild",
    )
    rebuild_projection = _mapping(
        job_projection["rebuild_public_projection"], "projection.job.rebuild"
    )
    _exact(
        rebuild["idempotency_basis"],
        rebuild_projection["idempotency_basis"],
        "job.rebuild.idempotency",
    )
    rebuild_schema = _load_json(root, REBUILD_JOB_SCHEMA_PATH, "job_schema")
    payload = _mapping(
        _mapping(
            _mapping(_list(rebuild_schema["allOf"], "job.allOf")[1], "job.body")[
                "properties"
            ],
            "job.properties",
        )["payload"],
        "job.payload",
    )
    _exact(payload["required"], rebuild_projection["payload_required"], "job.required")
    _exact(
        list(_mapping(payload["properties"], "job.payload.properties")),
        rebuild_projection["payload_required"] + rebuild_projection["payload_optional"],
        "job.payload.properties",
    )
    _exact(rebuild_projection["reconciled"], False, "job.reconciled")

    event = _load_json(root, PROJECTION_EVENT_SCHEMA_PATH, "event_schema")
    event_data = _mapping(
        _mapping(
            _mapping(_list(event["allOf"], "event.allOf")[1], "event.body")[
                "properties"
            ],
            "event.properties",
        )["data"],
        "event.data",
    )
    event_projection = _mapping(projection["event_surface"], "projection.event")
    _exact(event_data["required"], event_projection["required"], "event.required")
    _exact(event_projection["snapshot_identity_present"], False, "event.snapshot")

    conflicts = _mapping(projection["surface_conflicts"], "projection.conflicts")
    _exact(
        conflicts,
        {
            "heading_level": {
                "database": "2..6",
                "public_openapi": "2..4",
                "reconciled": False,
            },
            "badges_shape": {
                "database": "object",
                "public_openapi": "array",
                "reconciled": False,
            },
            "destination_host": {
                "database": "nullable",
                "public_openapi": "required_string",
                "reconciled": False,
            },
            "projection_generation": {
                "database": "greater_than_0",
                "public_openapi": "minimum_0",
                "reconciled": False,
            },
            "rebuild_idempotency": {
                "catalog": "snapshot_generation",
                "payload": "expected_snapshot_hash",
                "reconciled": False,
            },
        },
        "projection.conflicts",
    )

    source_map = {role: Path(path) for role, path, _ in EXPECTED_SOURCES}
    fragments = {
        "integration": ("Public Read Model", "Publication Snapshot"),
        "data_model": ("readmodel.public_article", "readmodel.runtime_control"),
        "public_openapi": (
            "heading_level",
            "destination_host",
            "projection_generation",
        ),
    }
    for role, required in fragments.items():
        text = _text(root, source_map[role], f"source.{role}")
        if any(fragment not in text for fragment in required):
            _fail("SOURCE_SEMANTIC_DRIFT", f"source.{role}")


def _validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(
        contract["document"],
        {
            "id": "RAOS-ST0904-PUBLIC-PROJECTION-REFERENCE-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-0904",
            "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLIC_PROJECTION_REFERENCE_PLAN",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "readiness": "NOT_READY",
            "story_acceptance": False,
            "projector_authorized": False,
            "runtime_projector_authorized": False,
            "approval_authority": False,
            "publication_permitted": False,
            "production_eligible": False,
        },
        "document",
    )
    _exact(
        contract["pro_assistance"],
        {
            "status": "PRO_UNAVAILABLE",
            "authority": "NONE",
            "proposal_captured": False,
            "content_used": False,
        },
        "pro_assistance",
    )
    authority = _mapping(contract["authority"], "authority")
    _exact(tuple(authority), ("precedence", "sources"), "authority.keys")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_INSTALLED_CONTRACTS",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["dependencies"], _expected_dependencies(), "dependencies")
    _exact(contract["hard_gates"], _expected_hard_gates(), "hard_gates")
    _validate_hashes(root)
    _validate_st0904_semantics(
        root, _mapping(contract["contract_projection_defaults"], "projection")
    )
    records = _mapping(contract["record_defaults"], "records")
    _exact(
        tuple(records),
        ("projections", "public_rows", "jobs", "events", "audits", "publications"),
        "records.keys",
    )
    for name, value in records.items():
        record = _mapping(value, f"records.{name}")
        _exact(record["status"], "NOT_EVALUATED", f"records.{name}.status")
        _exact(record["records"], [], f"records.{name}.records")
    _exact(
        _mapping(records["projections"], "records.projections")[
            "empty_records_interpretation"
        ],
        "NO_PROJECTION_OR_EVIDENCE_NOT_ZERO_VALID_PROJECTIONS",
        "records.projections.interpretation",
    )
    execution = _mapping(contract["execution_defaults"], "execution")
    for key in ("runtime_reader", "pure_projector", "runtime_projector"):
        _exact(execution[key], "NOT_IMPLEMENTED", f"execution.{key}")
    _exact(execution["external_actions"], [], "execution.external_actions")
    for key, value in execution.items():
        if key not in {
            "runtime_reader",
            "pure_projector",
            "runtime_projector",
            "external_actions",
        }:
            _exact(value, "NOT_EXECUTED", f"execution.{key}")
    verification = _mapping(contract["verification_defaults"], "verification")
    _exact(verification["story_acceptance"], False, "verification.acceptance")
    _exact(verification["readiness"], "NOT_READY", "verification.readiness")
    _exact(verification["production_eligible"], False, "verification.production")
    for key, value in verification.items():
        if key not in {"story_acceptance", "readiness", "production_eligible"}:
            _exact(value, "NOT_EXECUTED", f"verification.{key}")
    boundary = _mapping(contract["implementation_boundary"], "boundary")
    for key in (
        "runtime_modules",
        "domain_modules",
        "application_modules",
        "ports",
        "adapters",
        "database_changes",
        "storage_changes",
        "api_changes",
        "job_changes",
        "event_changes",
        "status_changes",
        "generated_binding_changes",
    ):
        _exact(boundary[key], [], f"boundary.{key}")
    _exact(
        boundary["executable_projector_requires"],
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
        "boundary.executable",
    )
    _exact(
        boundary["runtime_projector_requires"],
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
        "boundary.runtime",
    )
    return contract


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    try:
        return _validate_contract(contract, root)
    except PublicProjectionReferenceError:
        raise
    except AttributeError, IndexError, KeyError, TypeError:
        _fail("SOURCE_SHAPE_INVALID", "contract")


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "document": contract["document"],
        "pro_assistance": contract["pro_assistance"],
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "source_contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "digest_classification": "LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT",
        },
        "dependencies": contract["dependencies"],
        "hard_gates": contract["hard_gates"],
        "contract_projection": contract["contract_projection_defaults"],
        "record_boundary": contract["record_defaults"],
        "execution_boundary": contract["execution_defaults"],
        "verification_boundary": {
            **dict(_mapping(contract["verification_defaults"], "verification")),
            "effective_canonical_status": "UNCHANGED",
        },
        "implementation_boundary": contract["implementation_boundary"],
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-ST0904-PUBLIC-PROJECTION-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0904",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "dependency_inputs": [
                {"story_id": story_id, "uri": f"repo://{path}", "sha256": digest}
                for story_id, path, digest in DEPENDENCY_INPUTS
            ],
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "pro_assistance": "PRO_UNAVAILABLE_NONE_NO_PROPOSAL_NO_CONTENT",
            "digest_classification": "LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT",
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
                "digest_classification": "LOCAL_GENERATION_INTEGRITY_ONLY_NONCANONICAL_NONAUDIT",
            }
        ],
        "boundary": {
            "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLIC_PROJECTION_REFERENCE_PLAN",
            "executable": False,
            "runtime_reader": "NOT_IMPLEMENTED",
            "pure_projector": "NOT_IMPLEMENTED",
            "runtime_projector": "NOT_IMPLEMENTED",
            "records": "NOT_EVALUATED",
            "empty_projections": "NO_PROJECTION_OR_EVIDENCE_NOT_ZERO_VALID_PROJECTIONS",
            "formal_tst_011": "NOT_EXECUTED",
            "formal_tst_021": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "readiness": "NOT_READY",
            "production_eligible": False,
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract, root))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def _safe_output_parent(root: Path, relative: Path, *, create: bool) -> Path:
    try:
        return cast(Path, _helper()._safe_output_parent(root, relative, create=create))
    except PublicProjectionReferenceError:
        raise
    except RuntimeError:
        _fail("OUTPUT_PATH_REJECTED", "output")


def _output_file(root: Path, relative: Path) -> Path:
    try:
        return cast(Path, _helper()._output_file(root, relative))
    except PublicProjectionReferenceError:
        raise
    except RuntimeError:
        _fail("OUTPUT_PATH_REJECTED", "output")


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = _output_file(root, relative)
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


@dataclass
class _StagedOutput:
    relative: Path
    parent: Path
    target: Path
    original: bytes | None
    staged: Path | None


def _stage_bytes(parent: Path, name: str, content: bytes) -> Path:
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(temporary_name)
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return temporary
    except OSError:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def _replace(source: Path, target: Path) -> None:
    os.replace(source, target)


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _snapshot_and_stage(
    root: Path, outputs: Mapping[Path, bytes]
) -> list[_StagedOutput]:
    staged: list[_StagedOutput] = []
    try:
        for relative in GENERATED_PATHS:
            parent = _safe_output_parent(root, relative, create=True)
            target = parent / relative.name
            try:
                metadata = target.lstat()
            except FileNotFoundError:
                original = None
            except OSError:
                raise
            else:
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    _fail("OUTPUT_PATH_REJECTED", "output")
                original = target.read_bytes()
            temporary = _stage_bytes(parent, relative.name, outputs[relative])
            staged.append(_StagedOutput(relative, parent, target, original, temporary))
        return staged
    except PublicProjectionReferenceError:
        for item in staged:
            if item.staged is not None:
                item.staged.unlink(missing_ok=True)
        raise
    except OSError:
        for item in staged:
            if item.staged is not None:
                try:
                    item.staged.unlink(missing_ok=True)
                except OSError:
                    pass
        _fail("OUTPUT_STAGE_FAILED", "output")


def _restore_outputs(staged: Sequence[_StagedOutput]) -> bool:
    rollback_failed = False
    for item in staged:
        try:
            if item.original is None:
                try:
                    metadata = item.target.lstat()
                except FileNotFoundError:
                    continue
                if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                    rollback_failed = True
                    continue
                item.target.unlink()
            else:
                restore = _stage_bytes(item.parent, item.target.name, item.original)
                try:
                    _replace(restore, item.target)
                finally:
                    restore.unlink(missing_ok=True)
            _fsync_directory(item.parent)
        except OSError:
            rollback_failed = True
    return not rollback_failed


def _atomic_write_set(root: Path, outputs: Mapping[Path, bytes]) -> None:
    if tuple(outputs) != GENERATED_PATHS:
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    staged = _snapshot_and_stage(root, outputs)
    try:
        for item in staged:
            if item.staged is None:
                _fail("OUTPUT_STAGE_MISSING", "output")
            _replace(item.staged, item.target)
            item.staged = None
            _fsync_directory(item.parent)
    except PublicProjectionReferenceError:
        if not _restore_outputs(staged):
            _fail("OUTPUT_TRANSACTION_ROLLBACK_FAILED", "output")
        raise
    except OSError:
        if not _restore_outputs(staged):
            _fail("OUTPUT_TRANSACTION_ROLLBACK_FAILED", "output")
        _fail("OUTPUT_TRANSACTION_FAILED", "output")
    finally:
        for item in staged:
            if item.staged is not None:
                try:
                    item.staged.unlink(missing_ok=True)
                except OSError:
                    pass


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    _atomic_write_set(root, outputs)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        raise SystemExit(2)
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(arguments)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(check=args.check)
    except PublicProjectionReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0904 public-projection reference plan checked"
        if args.check
        else "ST-0904 public-projection reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
