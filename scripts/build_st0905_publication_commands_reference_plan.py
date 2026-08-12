#!/usr/bin/env python3
"""Build the strict non-executable ST-0905 publication-command/event reference plan."""

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
    "changes/st-0905/contracts/publication-commands-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0905/generated/publication-commands-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0905/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0905_publication_commands_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0905/README.md")
TEST_PATHS: Final = (
    Path("tests/st0905/conftest.py"),
    Path("tests/st0905/test_contract.py"),
    Path("tests/st0905/test_generation.py"),
    Path("tests/st0905/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0905_publication_commands_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
CONTRACT_SHA256: Final = (
    "5153ca3d18f9498f0be517ec375478824177129289d71a0c8e346cee419a699a"
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
CANONICAL_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
ROLE_MATRIX_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"
)
SECURITY_CONTROLS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
THREAT_REGISTER_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"
)
ADMIN_OPENAPI_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml"
)
STATE_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/state-transition-catalog.v0.4.yaml"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
PUBLISH_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/"
    "publishing-publish-snapshot-v1.schema.json"
)
UNPUBLISH_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/publishing-unpublish-v1.schema.json"
)
ROLLBACK_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/publishing-rollback-v1.schema.json"
)
PUBLISHED_EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-article-published-v1.schema.json"
)
UNPUBLISHED_EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-article-unpublished-v1.schema.json"
)
ROLLED_BACK_EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-article-rolled-back-v1.schema.json"
)

EXPECTED_SOURCES: Final = (
    (
        "integration",
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "canonical_decisions",
        CANONICAL_DECISIONS_PATH.as_posix(),
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "open_decisions",
        OPEN_DECISIONS_PATH.as_posix(),
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
        "api_event_job_design",
        "docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md",
        "1fe1e73db3c732379f3f83268141d2d1af72e921c0ed60e4d2fc40caf1973fcf",
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
        ROLE_MATRIX_PATH.as_posix(),
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
    (
        "threat_register",
        THREAT_REGISTER_PATH.as_posix(),
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    ),
    (
        "admin_openapi",
        ADMIN_OPENAPI_PATH.as_posix(),
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
    ),
    (
        "state_transition_catalog",
        STATE_CATALOG_PATH.as_posix(),
        "203eb10d9b6fc6ba4fb0e9f0491f713c313a6a5627dcaf60b7ce53665ecec8a5",
    ),
    (
        "job_catalog",
        JOB_CATALOG_PATH.as_posix(),
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        "publish_job_schema",
        PUBLISH_JOB_SCHEMA_PATH.as_posix(),
        "81f885e435bcaf4af75ab3149a2007668b7585155cfbe730242e78efefc5a6e7",
    ),
    (
        "unpublish_job_schema",
        UNPUBLISH_JOB_SCHEMA_PATH.as_posix(),
        "037516debc7d44f860de113f68973c85141ded552d9b45de88fdc6a6ac84a862",
    ),
    (
        "rollback_job_schema",
        ROLLBACK_JOB_SCHEMA_PATH.as_posix(),
        "8dd422009feea40da8821e57403ac493dd86f24ccf333beb29b637b60d7276d9",
    ),
    (
        "published_event_schema",
        PUBLISHED_EVENT_SCHEMA_PATH.as_posix(),
        "70fbe58d58399d44bd386ed39673682f7fa3eb3acfdbc8c5e2f46fcf7be12f19",
    ),
    (
        "unpublished_event_schema",
        UNPUBLISHED_EVENT_SCHEMA_PATH.as_posix(),
        "91fc5b6322bd98301440b493c639955541aba9a45b24420888ca855e90eac9b6",
    ),
    (
        "rolled_back_event_schema",
        ROLLED_BACK_EVENT_SCHEMA_PATH.as_posix(),
        "a405b5826a80f2e95029d7a5b824caf9e5795e8050edfc97e2e76906742cf660",
    ),
)

DEPENDENCY_INPUTS: Final = (
    (
        "ST-0903",
        "changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml",
        "cf6f9a55f769a2861cda655cdc7e963d6048a7ff721ded55a40aaa0978702692",
    ),
    (
        "ST-0904",
        "changes/st-0904/contracts/public-projection-reference-plan.v1.yaml",
        "a61b1d16c35c45b2c12b886222fc79dc36d46ca496223303c81b9f796f7ea672",
    ),
    (
        "ST-0402",
        "changes/st-0402/README.md",
        "6a3d5b2a1836d683b2dc96ecb73e4a02943a9a6fd8068496e6d550492514534b",
    ),
)

EXPECTED_DEPENDENCY_AUTHORITY: Final = {
    "ST-0903": "NONEXECUTABLE_REFERENCE_PLAN_NO_AUTHORITATIVE_SNAPSHOT",
    "ST-0904": "NONEXECUTABLE_REFERENCE_PLAN_NO_PROJECTOR_OR_PUBLIC_ROW",
    "ST-0402": "DEVELOPMENT_SYNTHETIC_STEP_UP_ONLY_NO_PUBLIC_AUTHORITY",
}
EXPECTED_HARD_GATE_ROWS: Final = (
    (
        "ST0905-GATE-001",
        "authoritative_effective_non_revoked_publication_snapshot",
        "ABSENT",
        "NO_COMMAND",
        None,
    ),
    (
        "ST0905-GATE-002",
        "executable_public_projector_current_row_and_route",
        "ABSENT",
        "NO_PUBLICATION",
        None,
    ),
    (
        "ST0905-GATE-003",
        "production_identity_mfa_step_up_and_action_mapping",
        "NOT_IMPLEMENTED",
        "DENY_COMMAND",
        None,
    ),
    (
        "ST0905-GATE-004",
        "unpublish_role_mfa_step_up_and_separation_of_duties",
        "NOT_DEFINED",
        "DENY_UNPUBLISH",
        None,
    ),
    (
        "ST0905-GATE-005",
        "http_request_job_payload_and_idempotency_mapping",
        "UNRESOLVED",
        "KEEP_SURFACES_DISTINCT_NO_COMMAND",
        None,
    ),
    (
        "ST0905-GATE-006",
        "same_key_cross_key_job_outbox_and_event_deduplication",
        "NOT_DEFINED",
        "NO_JOB_OR_EVENT",
        None,
    ),
    (
        "ST0905-GATE-007",
        "etag_current_snapshot_route_lock_and_state_resolution",
        "NOT_DEFINED",
        "NO_DATABASE_MUTATION",
        None,
    ),
    (
        "ST0905-GATE-008",
        "idempotency_job_audit_outbox_event_publication_atomicity_and_crash_recovery",
        "NOT_IMPLEMENTED",
        "NO_SIDE_EFFECT",
        None,
    ),
    (
        "ST0905-GATE-009",
        "publication_kill_switch_runtime_and_fail_closed_guard",
        "NOT_IMPLEMENTED",
        "NO_PUBLISH_OR_ROLLBACK",
        None,
    ),
    (
        "ST0905-GATE-010",
        "approval_rights_policy_legal_freshness_and_rollback_target_eligibility",
        "NOT_AUTHORITATIVE",
        "NO_PUBLICATION_OR_ROLLBACK",
        None,
    ),
    (
        "ST0905-GATE-011",
        "scheduled_publish_and_scheduler_authority_with_auto_publish_disabled",
        "PROHIBITED_FOR_MVP",
        "NO_SCHEDULED_PUBLISH",
        None,
    ),
    (
        "ST0905-GATE-012",
        "executable_command_job_event_and_publication_authority",
        "ABSENT",
        "REFERENCE_PLAN_ONLY",
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    ),
)

EXPECTED_CONFLICT_ROWS: Final = (
    {
        "id": "ST0905-CONFLICT-001",
        "topic": "publish_candidate_identity",
        "api_surface": "path:{id}+body:publication_candidate_id",
        "job_surface": "publication_candidate_id",
        "status": "UNRESOLVED",
        "safe_default": "NO_COMMAND",
    },
    {
        "id": "ST0905-CONFLICT-002",
        "topic": "publish_route_idempotency",
        "api_surface": "route_absent",
        "job_surface": "idempotency_basis:route+payload:route_absent",
        "status": "UNRESOLVED",
        "safe_default": "NO_JOB",
    },
    {
        "id": "ST0905-CONFLICT-003",
        "topic": "scheduled_publish_authority",
        "api_surface": "scheduled_for_optional",
        "job_surface": "scheduler_producer",
        "status": "CONFLICTS_WITH_AUTO_PUBLISH_DISABLED",
        "safe_default": "NO_SCHEDULED_PUBLISH",
    },
    {
        "id": "ST0905-CONFLICT-004",
        "topic": "rollback_from_snapshot_resolution",
        "api_surface": "from_snapshot_id_absent",
        "job_surface": "from_snapshot_id_required",
        "status": "UNRESOLVED",
        "safe_default": "NO_ROLLBACK",
    },
    {
        "id": "ST0905-CONFLICT-005",
        "topic": "unpublish_current_snapshot_and_reason_class",
        "api_surface": "reason_only+current_snapshot_absent",
        "job_surface": "idempotency_basis:current_snapshot_id+reason_class",
        "status": "UNRESOLVED",
        "safe_default": "NO_UNPUBLISH",
    },
    {
        "id": "ST0905-CONFLICT-006",
        "topic": "unpublish_authorization",
        "api_surface": "scope:publishing:unpublish",
        "job_surface": "role_matrix_action_absent",
        "status": "SECURITY_DECISION_REQUIRED",
        "safe_default": "DENY_UNPUBLISH",
    },
    {
        "id": "ST0905-CONFLICT-007",
        "topic": "logical_exactly_once_boundary",
        "api_surface": "same_key_replay_only",
        "job_surface": "cross_key_job_outbox_event_deduplication_not_defined",
        "status": "UNRESOLVED",
        "safe_default": "NO_SIDE_EFFECT",
    },
    {
        "id": "ST0905-CONFLICT-008",
        "topic": "atomic_publication_unit_of_work",
        "api_surface": "async_202_job_acceptance",
        "job_surface": "publication_readmodel_job_audit_outbox_event_atomicity_not_implemented",
        "status": "NOT_IMPLEMENTED",
        "safe_default": "NO_SIDE_EFFECT",
    },
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


class PublicationCommandsReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


_HELPER_MODULE: ModuleType | None = None


def _fail(code: str, field: str) -> NoReturn:
    raise PublicationCommandsReferenceError(
        f"ST-0905 build failed: {code} field={field}"
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
    except PublicationCommandsReferenceError:
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
    except PublicationCommandsReferenceError:
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
    except PublicationCommandsReferenceError:
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


def _schema_body(schema: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    all_of = _list(schema["allOf"], field)
    return _mapping(all_of[1], field)


def _payload_schema(schema: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    body = _schema_body(schema, field)
    properties = _mapping(body["properties"], field)
    return _mapping(properties["payload"], field)


def _event_data_schema(schema: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    body = _schema_body(schema, field)
    properties = _mapping(body["properties"], field)
    return _mapping(properties["data"], field)


def _validate_st0905_semantics(root: Path, projection: Mapping[str, Any]) -> None:
    story = _find(
        _load_yaml(root, STORY_PATH, "story")["stories"], "id", "ST-0905", "story"
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
    _exact(
        projected_story["test_suites"],
        traces["story_test_suites"],
        "trace.story.tests",
    )
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
    _exact(
        traces["traceability_status"],
        "DIVERGENT_RECORDED_NOT_RESOLVED",
        "trace.status",
    )
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")["suites"]
    for suite_id in ("TST-012", "TST-013", "TST-021"):
        suite = _find(suites, "id", suite_id, f"test.{suite_id}")
        _exact(suite["execution_status"], "NOT_EXECUTED", f"test.{suite_id}")

    dependencies = {story_id: Path(path) for story_id, path, _ in DEPENDENCY_INPUTS}
    snapshot_plan = _load_yaml(root, dependencies["ST-0903"], "dependency.ST-0903")
    snapshot_document = _mapping(
        snapshot_plan["document"], "dependency.ST-0903.document"
    )
    _exact(snapshot_document["executable"], False, "dependency.ST-0903.executable")
    _exact(
        snapshot_document["snapshot_builder_authorized"],
        False,
        "dependency.ST-0903.builder",
    )
    projection_plan = _load_yaml(root, dependencies["ST-0904"], "dependency.ST-0904")
    projection_document = _mapping(
        projection_plan["document"], "dependency.ST-0904.document"
    )
    _exact(projection_document["executable"], False, "dependency.ST-0904.executable")
    _exact(
        projection_document["projector_authorized"],
        False,
        "dependency.ST-0904.projector",
    )
    step_up = _text(root, dependencies["ST-0402"], "dependency.ST-0402")
    for fragment in (
        "exact-`ENV-DEV` deterministic source",
        "synthetic already-verified grants",
        "does not implement an MFA challenge",
        "public/live activation",
    ):
        if fragment not in step_up:
            _fail("SOURCE_SEMANTIC_DRIFT", "dependency.ST-0402")

    openapi = _load_yaml(root, ADMIN_OPENAPI_PATH, "admin_openapi")
    paths = _mapping(openapi["paths"], "admin_openapi.paths")
    components = _mapping(openapi["components"], "admin_openapi.components")
    schemas = _mapping(components["schemas"], "admin_openapi.schemas")
    command_projection = _mapping(projection["command_surfaces"], "projection.commands")
    for name in ("publish", "rollback", "unpublish"):
        expected = _mapping(command_projection[name], f"projection.command.{name}")
        path = expected["path"]
        operation = _mapping(
            _mapping(paths[path], f"openapi.path.{name}")["post"],
            f"openapi.operation.{name}",
        )
        _exact(expected["method"], "POST", f"command.{name}.method")
        for source_key, expected_key in (
            ("operationId", "operation_id"),
            ("x-raos-kind", "kind"),
            ("x-raos-implementation-slice", "implementation_slice"),
            ("x-raos-idempotency-required", "idempotency_required"),
            ("x-raos-concurrency-required", "concurrency_required"),
            ("x-raos-async-job-type", "async_job_type"),
            ("x-raos-audit-action", "audit_action"),
            ("x-raos-requirements", "requirements"),
        ):
            _exact(
                operation[source_key],
                expected[expected_key],
                f"command.{name}.{expected_key}",
            )
        parameter_refs = [
            str(_mapping(row, f"command.{name}.parameter")["$ref"]).rsplit("/", 1)[-1]
            for row in _list(operation["parameters"], f"command.{name}.parameters")
            if "$ref" in _mapping(row, f"command.{name}.parameter")
        ]
        _exact(
            parameter_refs,
            expected["parameter_refs"],
            f"command.{name}.parameter_refs",
        )
        request_body = _mapping(
            operation["requestBody"], f"command.{name}.request_body"
        )
        request_content = _mapping(
            request_body["content"], f"command.{name}.request_content"
        )
        request_media = _mapping(
            request_content["application/json"], f"command.{name}.request_media"
        )
        request_ref = str(
            _mapping(request_media["schema"], f"command.{name}.request_ref")["$ref"]
        )
        _exact(
            request_ref.rsplit("/", 1)[-1],
            expected["request_schema"],
            f"command.{name}.request_schema",
        )
        request_schema = _mapping(
            schemas[expected["request_schema"]], f"command.{name}.schema"
        )
        required = _list(request_schema["required"], f"command.{name}.required")
        properties = _mapping(
            request_schema["properties"], f"command.{name}.properties"
        )
        _exact(required, expected["request_required"], f"command.{name}.required")
        _exact(
            [key for key in properties if key not in required],
            expected["request_optional"],
            f"command.{name}.optional",
        )
        security = _mapping(
            _list(operation["security"], f"command.{name}.security")[0],
            f"command.{name}.security",
        )
        _exact(
            _list(security["oidcOAuth2"], f"command.{name}.scopes"),
            [expected["scope"]],
            f"command.{name}.scope",
        )
        responses = _mapping(operation["responses"], f"command.{name}.responses")
        response = _mapping(
            responses[str(expected["response_status"])], f"command.{name}.response"
        )
        response_content = _mapping(
            response["content"], f"command.{name}.response_content"
        )
        response_media = _mapping(
            response_content["application/json"], f"command.{name}.response_media"
        )
        response_ref = str(
            _mapping(response_media["schema"], f"command.{name}.response_ref")["$ref"]
        )
        _exact(
            response_ref.rsplit("/", 1)[-1],
            expected["response_schema"],
            f"command.{name}.response_schema",
        )
        _exact(expected["command_status"], "NOT_IMPLEMENTED", f"command.{name}.status")

    jobs = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")["jobs"]
    job_projection = _mapping(projection["job_surfaces"], "projection.jobs")
    job_schemas = {
        "publish": PUBLISH_JOB_SCHEMA_PATH,
        "unpublish": UNPUBLISH_JOB_SCHEMA_PATH,
        "rollback": ROLLBACK_JOB_SCHEMA_PATH,
    }
    for name in ("publish", "unpublish", "rollback"):
        expected = _mapping(job_projection[name], f"projection.job.{name}")
        job = _find(jobs, "job_type", str(expected["job_type"]), f"job.{name}")
        for source_key, expected_key in (
            ("job_type", "job_type"),
            ("queue", "queue"),
            ("producer", "producers"),
            ("consumer", "consumer"),
            ("idempotency_basis", "idempotency_basis"),
            ("lock_scope", "lock_scope"),
            ("emits", "emits"),
            ("enabled", "enabled_in_catalog"),
        ):
            _exact(
                job[source_key], expected[expected_key], f"job.{name}.{expected_key}"
            )
        schema = _load_json(root, job_schemas[name], f"job_schema.{name}")
        payload = _payload_schema(schema, f"job_schema.{name}")
        required = _list(payload["required"], f"job_schema.{name}.required")
        properties = _mapping(payload["properties"], f"job_schema.{name}.properties")
        _exact(required, expected["payload_required"], f"job.{name}.required")
        _exact(
            [key for key in properties if key not in required],
            expected["payload_optional"],
            f"job.{name}.optional",
        )
        _exact(
            expected["execution_status"],
            "NOT_IMPLEMENTED",
            f"job.{name}.execution",
        )

    event_projection = _mapping(projection["event_surfaces"], "projection.events")
    event_schemas = {
        "published": PUBLISHED_EVENT_SCHEMA_PATH,
        "unpublished": UNPUBLISHED_EVENT_SCHEMA_PATH,
        "rolled_back": ROLLED_BACK_EVENT_SCHEMA_PATH,
    }
    for name in ("published", "unpublished", "rolled_back"):
        expected = _mapping(event_projection[name], f"projection.event.{name}")
        schema = _load_json(root, event_schemas[name], f"event_schema.{name}")
        body = _schema_body(schema, f"event_schema.{name}")
        properties = _mapping(body["properties"], f"event_schema.{name}.properties")
        _exact(schema["title"], expected["event_type"], f"event.{name}.title")
        _exact(
            _mapping(properties["type"], f"event.{name}.type")["const"],
            expected["event_type"],
            f"event.{name}.type",
        )
        _exact(
            _mapping(properties["producer"], f"event.{name}.producer")["const"],
            expected["producer"],
            f"event.{name}.producer",
        )
        data = _event_data_schema(schema, f"event_schema.{name}")
        _exact(data["required"], expected["required"], f"event.{name}.required")
        _exact(
            expected["emission_status"],
            "NOT_IMPLEMENTED",
            f"event.{name}.status",
        )
        _exact(
            expected["envelope_allocation"],
            "NOT_DEFINED",
            f"event.{name}.envelope",
        )

    state_projection = _mapping(projection["state_surface"], "projection.state")
    machines = _load_yaml(root, STATE_CATALOG_PATH, "state_catalog")["machines"]
    machine = _find(machines, "id", "SM-PUBLICATION", "state.publication")
    for key in ("id", "aggregate", "initial", "states", "guards"):
        _exact(machine[key], state_projection[key], f"state.{key}")
    transitions = [
        {
            "from": _list(row, "state.transition")[0],
            "to": _list(row, "state.transition")[1],
            "reason": _list(row, "state.transition")[2],
        }
        for row in _list(machine["transitions"], "state.transitions")
    ]
    _exact(transitions, state_projection["transitions"], "state.transitions")
    _exact(state_projection["runtime_status"], "NOT_IMPLEMENTED", "state.runtime")

    security = _mapping(projection["security_boundary"], "projection.security")
    permissions = _load_yaml(root, ROLE_MATRIX_PATH, "role_matrix")["permissions"]
    for name in ("publish", "rollback"):
        expected = _mapping(security[name], f"security.{name}")
        permission = _find(permissions, "action", name, f"role.{name}")
        _exact(expected["role_matrix_action_present"], True, f"role.{name}.present")
        for key in (
            "allowed_roles",
            "mfa_required",
            "step_up_required",
            "separation_of_duties",
            "runtime_verification",
        ):
            _exact(permission[key], expected[key], f"role.{name}.{key}")
    unpublish_matches = [
        row
        for row in _list(permissions, "role.permissions")
        if _mapping(row, "role.permission").get("action") == "unpublish"
    ]
    _exact(len(unpublish_matches), 0, "role.unpublish.absent")
    unpublish_security = _mapping(security["unpublish"], "security.unpublish")
    _exact(unpublish_security["role_matrix_action_present"], False, "role.unpublish")
    _exact(unpublish_security["allowed_roles"], [], "role.unpublish.roles")
    _exact(unpublish_security["safe_default"], "DENY_UNPUBLISH", "role.unpublish.safe")

    controls = _load_yaml(root, SECURITY_CONTROLS_PATH, "security_controls")["controls"]
    for control_id in _list(security["controls"], "security.controls"):
        control = _find(controls, "id", str(control_id), f"control.{control_id}")
        _exact(
            control["verification_status"],
            "NOT_EXECUTED",
            f"control.{control_id}.verification",
        )
    threats = _load_yaml(root, THREAT_REGISTER_PATH, "threat_register")["threats"]
    for threat_id in _list(security["threats"], "security.threats"):
        threat = _find(threats, "id", str(threat_id), f"threat.{threat_id}")
        _exact(
            threat["verification_status"],
            "NOT_EXECUTED",
            f"threat.{threat_id}.verification",
        )
    decisions = _load_yaml(root, CANONICAL_DECISIONS_PATH, "canonical_decisions")[
        "decisions"
    ]
    auto_publish = _find(decisions, "id", "INT-DEC-009", "decision.INT-DEC-009")
    _exact(
        auto_publish["implementation_effect"], "auto-publishはMVPで無効", "auto_publish"
    )
    codex_authority = _find(decisions, "id", "INT-DEC-013", "decision.INT-DEC-013")
    if "公開" not in str(codex_authority["decision"]):
        _fail("SOURCE_SEMANTIC_DRIFT", "decision.INT-DEC-013")
    _exact(security["auto_publish_mvp_enabled"], False, "security.auto_publish")
    _exact(security["publication_authority"], False, "security.authority")
    _exact(
        security["external_publication_permitted"],
        False,
        "security.external_publication",
    )
    open_items = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")["items"]
    for decision_id in ("OD-002", "OD-005", "OD-007", "OD-008", "OD-010"):
        decision = _find(open_items, "id", decision_id, f"open_decision.{decision_id}")
        _exact(decision["blocking"], True, f"open_decision.{decision_id}.blocking")

    _exact(
        projection["surface_conflicts"],
        list(EXPECTED_CONFLICT_ROWS),
        "projection.conflicts",
    )

    source_map = {role: Path(path) for role, path, _ in EXPECTED_SOURCES}
    fragments = {
        "integration": ("Public Read Model", "Human Approval", "Publication Snapshot"),
        "data_model": (
            "publishing.publication",
            "publishing.publication_event",
            "publishing.rollback_record",
        ),
        "api_event_job_design": (
            "PUBADM-009",
            "PUBADM-012",
            "PUBADM-013",
            "publishing.publish_snapshot.v1",
            "jp.raos.publishing.article_published.v1",
        ),
    }
    for role, required_fragments in fragments.items():
        text = _text(root, source_map[role], f"source.{role}")
        if any(fragment not in text for fragment in required_fragments):
            _fail("SOURCE_SEMANTIC_DRIFT", f"source.{role}")


def _validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(
        contract["document"],
        {
            "id": "RAOS-ST0905-PUBLICATION-COMMANDS-REFERENCE-PLAN-001",
            "version": "1.0.0",
            "story_id": "ST-0905",
            "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLICATION_COMMAND_EVENT_REFERENCE_PLAN",
            "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
            "executable": False,
            "interface_only": True,
            "decision": "NOT_READY",
            "readiness": "NOT_READY",
            "story_acceptance": False,
            "command_handlers_authorized": False,
            "job_producers_authorized": False,
            "event_emission_authorized": False,
            "audit_mutation_authorized": False,
            "database_mutation_authorized": False,
            "external_actions_authorized": False,
            "approval_authority": False,
            "publication_authority": False,
            "publication_permitted": False,
            "production_eligible": False,
        },
        "document",
    )
    _exact(
        contract["pro_assistance"],
        {"pro_required_for_reference_slice": False},
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
    _validate_st0905_semantics(
        root, _mapping(contract["contract_projection_defaults"], "projection")
    )

    records = _mapping(contract["record_defaults"], "records")
    _exact(
        tuple(records),
        (
            "commands",
            "jobs",
            "events",
            "audits",
            "database_mutations",
            "external_actions",
            "publications",
            "rollbacks",
        ),
        "records.keys",
    )
    for name, value in records.items():
        record = _mapping(value, f"records.{name}")
        _exact(record["status"], "NOT_EVALUATED", f"records.{name}.status")
        _exact(record["records"], [], f"records.{name}.records")
    _exact(
        _mapping(records["commands"], "records.commands")[
            "empty_records_interpretation"
        ],
        "NO_COMMAND_OR_EVIDENCE_NOT_ZERO_VALID_COMMANDS",
        "records.commands.interpretation",
    )

    execution = _mapping(contract["execution_defaults"], "execution")
    not_implemented = {
        "command_handlers",
        "job_producers",
        "job_consumers",
        "event_emitters",
        "audit_writer",
        "database_unit_of_work",
        "external_cms_adapter",
    }
    for key, value in execution.items():
        if key in not_implemented:
            _exact(value, "NOT_IMPLEMENTED", f"execution.{key}")
        elif key == "external_side_effects":
            _exact(value, [], "execution.external_side_effects")
        else:
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
        "existing_file_changes",
        "runtime_modules",
        "domain_modules",
        "application_modules",
        "ports",
        "adapters",
        "database_changes",
        "migration_changes",
        "api_changes",
        "job_changes",
        "event_changes",
        "canonical_changes",
        "status_changes",
        "generated_binding_changes",
    ):
        _exact(boundary[key], [], f"boundary.{key}")
    _exact(
        boundary["allowed_outputs"],
        [
            "reference_contract",
            "deterministic_reference_projection",
            "source_manifest",
            "documentation",
            "isolated_tests",
        ],
        "boundary.allowed_outputs",
    )
    _exact(
        boundary["executable_work_requires"],
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
        "boundary.executable",
    )
    return contract


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    try:
        return _validate_contract(contract, root)
    except PublicationCommandsReferenceError:
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
            "id": "RAOS-ST0905-PUBLICATION-COMMANDS-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0905",
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
            "pro_assistance": "NOT_REQUIRED_FOR_REFERENCE_SLICE_NO_RUN_NO_DIAGNOSTIC",
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
            "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLICATION_COMMAND_EVENT_REFERENCE_PLAN",
            "executable": False,
            "command_handlers": "NOT_IMPLEMENTED",
            "job_producers": "NOT_IMPLEMENTED",
            "job_consumers": "NOT_IMPLEMENTED",
            "event_emitters": "NOT_IMPLEMENTED",
            "audit_writer": "NOT_IMPLEMENTED",
            "database_unit_of_work": "NOT_IMPLEMENTED",
            "external_cms_adapter": "NOT_IMPLEMENTED",
            "records": "NOT_EVALUATED",
            "empty_commands": "NO_COMMAND_OR_EVIDENCE_NOT_ZERO_VALID_COMMANDS",
            "formal_tst_012": "NOT_EXECUTED",
            "formal_tst_013": "NOT_EXECUTED",
            "formal_tst_021": "NOT_EXECUTED",
            "runtime": "NOT_EXECUTED",
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
    except PublicationCommandsReferenceError:
        raise
    except RuntimeError:
        _fail("OUTPUT_PATH_REJECTED", "output")


def _output_file(root: Path, relative: Path) -> Path:
    try:
        return cast(Path, _helper()._output_file(root, relative))
    except PublicationCommandsReferenceError:
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
    except PublicationCommandsReferenceError:
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
    except PublicationCommandsReferenceError:
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
    except PublicationCommandsReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0905 publication-commands reference plan checked"
        if args.check
        else "ST-0905 publication-commands reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
