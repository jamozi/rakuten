#!/usr/bin/env python3
"""Build the strict non-executable ST-0902 final-approval reference plan."""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import io
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0902/contracts/final-approval-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0902/generated/final-approval-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0902/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st0902_final_approval_reference_plan.py")
README_PATH: Final = Path("changes/st-0902/README.md")
TEST_PATHS: Final = (
    Path("tests/st0902/conftest.py"),
    Path("tests/st0902/test_contract.py"),
    Path("tests/st0902/test_generation.py"),
    Path("tests/st0902/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0902_final_approval_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9afb71a8715ea76a65e4a681a3d41940e38d5d3dc4a0b838f7bd7eea6180065b"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
MASTER_TRACE_PATH: Final = Path(
    "docs/canonical/00_master/RAOS_master_traceability_v1.0.csv"
)
ACCEPTANCE_TRACE_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_acceptance_traceability_v1.0.csv"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
ROLE_MATRIX_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"
)
CANONICAL_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
SECURITY_DESIGN_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"
)
SECURITY_CONTROLS_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
ARCHITECTURE_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md"
)
DATA_MODEL_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md"
)
API_DESIGN_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_04_api_event_job_contract_design_v0.1.md"
)
CONTENT_DESIGN_PATH: Final = Path(
    "docs/upstream/key_documents/RAOS_06_content_editorial_evidence_design_v0.1.md"
)
ADMIN_API_PATH: Final = Path("contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml")
APPROVAL_GRANTED_EVENT_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-approval-granted-v1.schema.json"
)
APPROVAL_REVOKED_EVENT_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-approval-revoked-v1.schema.json"
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
        "role_matrix",
        ROLE_MATRIX_PATH.as_posix(),
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
    (
        "security_design",
        SECURITY_DESIGN_PATH.as_posix(),
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    (
        "security_controls",
        SECURITY_CONTROLS_PATH.as_posix(),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "system_architecture",
        ARCHITECTURE_PATH.as_posix(),
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3",
    ),
    (
        "data_model",
        DATA_MODEL_PATH.as_posix(),
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    ),
    (
        "api_event_job_design",
        API_DESIGN_PATH.as_posix(),
        "1fe1e73db3c732379f3f83268141d2d1af72e921c0ed60e4d2fc40caf1973fcf",
    ),
    (
        "content_design",
        CONTENT_DESIGN_PATH.as_posix(),
        "a40b9859122b330f9db7246f58e7e45f8024f64fde8b07a41ab234ed11cae682",
    ),
    (
        "admin_openapi",
        ADMIN_API_PATH.as_posix(),
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
    ),
    (
        "approval_granted_event_schema",
        APPROVAL_GRANTED_EVENT_PATH.as_posix(),
        "ef597efed4ffe2d50440bec59dea9d1fa08ae0fa2f76ad20d3ce30e227b8e097",
    ),
    (
        "approval_revoked_event_schema",
        APPROVAL_REVOKED_EVENT_PATH.as_posix(),
        "3ea30eefd85cdf9f48fa84a4caf3b26956d1943c621a2035cf4584477680f1c1",
    ),
)

DEPENDENCY_INPUTS: Final = (
    (
        "ST-0305",
        "publishing_guard",
        "changes/st-0305/contracts/physical/publishing-guards.sql",
        "d3ecd89ac35c386333ac2bf75907259aa28fc8718f65e8c303499193d57fe82e",
    ),
    (
        "ST-0402",
        "readme",
        "changes/st-0402/README.md",
        "6a3d5b2a1836d683b2dc96ecb73e4a02943a9a6fd8068496e6d550492514534b",
    ),
    (
        "ST-0403",
        "readme",
        "changes/st-0403/README.md",
        "e7c0e10e44abf6f5db2fbbd94c6a14ecbc9d6bc0ff77fcb312d652204165b6e9",
    ),
    (
        "ST-0405",
        "readme",
        "changes/st-0405/README.md",
        "8b046d65492947a458306c308f5515bb6496e0371bdc9695226d52328a04a657",
    ),
    (
        "ST-0605",
        "readme",
        "changes/st-0605/README.md",
        "f5a59ab0542a95987720c5d9ec43ef4355d92cea2b7bafcf8851e510fb98cf4b",
    ),
    (
        "ST-0605",
        "contract",
        "changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml",
        "3e9de9f652b6b6ef4b90614877ba25ad16285b6750966013a4c02dd7277771e6",
    ),
    (
        "ST-0805",
        "readme",
        "changes/st-0805/README.md",
        "914739de388086da1f83dc25691a89d877eba303ad51e0ab4068ac7105ddec13",
    ),
    (
        "ST-0805",
        "policy_engine",
        "python/raos/domain/editorial/policy_engine.py",
        "d858a9b010253cf411083bd5eb9da995ff3f9a172c7626ca9e499a6256559e51",
    ),
    (
        "ST-0901",
        "pr1_readme",
        "changes/st-0901/README.md",
        "e444a0dea6585ba88ac8705150caa633f095618daa0f2a8dd5fdf035121ec2b0",
    ),
    (
        "ST-0901",
        "pr3_readme",
        "changes/st-0901/README_PR3.md",
        "8b76eab672fb2941288cca91e57551ee1e3407776862166f7344dcd2048c1a5c",
    ),
    (
        "ST-0901",
        "review_workflow",
        "python/raos/domain/publishing/review_workflow.py",
        "f7c84e1911d4570a4dc3492c395255da3fcef5eee5ec7b891058caf596e1efb5",
    ),
    (
        "ST-0901",
        "review_decision_operations",
        "python/raos/domain/publishing/review_decision_operations.py",
        "f267f2af141d1269bceb175095dc4a397cafb78a120516bb3fb82a8c0706bc71",
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

EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0902-FINAL-APPROVAL-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-0902",
    "classification": "SOURCE_DERIVED_NONEXECUTABLE_FINAL_APPROVAL_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "readiness": "NOT_READY",
    "story_acceptance": False,
    "approval_authority": False,
    "rejection_authority": False,
    "revocation_authority": False,
    "publication_permitted": False,
    "production_eligible": False,
}
EXPECTED_PRO_ASSISTANCE: Final = {
    "status": "PRO_UNAVAILABLE",
    "authority": "NONE",
    "proposal_captured": False,
    "content_used": False,
}

_DEPENDENCY_METADATA: Final = {
    "ST-0305": (
        "FINAL_APPROVAL_DATABASE_GUARD_FRAGMENT",
        "NOT_EXECUTED",
        "INSUFFICIENT_FOR_ST0902",
    ),
    "ST-0402": (
        "PROVIDER_NEUTRAL_LOCAL_STEP_UP_SEAM",
        "NOT_EXECUTED",
        "ABSENT",
    ),
    "ST-0403": (
        "TEST_ONLY_DENY_DEFAULT_AUTHORIZATION_SEAM",
        "NOT_EXECUTED",
        "ABSENT",
    ),
    "ST-0405": (
        "PROCESS_LOCAL_RECORDED_AUDIT_SEAM",
        "NOT_EXECUTED",
        "ABSENT",
    ),
    "ST-0605": (
        "NONEXECUTABLE_CLAIM_EVIDENCE_REFERENCE_PLAN",
        "NOT_EXECUTED",
        "ABSENT",
    ),
    "ST-0805": (
        "PURE_LOCAL_EDITORIAL_POLICY_EVALUATOR",
        "NOT_EXECUTED",
        "ABSENT",
    ),
    "ST-0901": (
        "PURE_AND_RECORDED_LOCAL_NEGATIVE_REVIEW_DECISIONS",
        "NOT_EXECUTED",
        "ABSENT",
    ),
}

EXPECTED_HARD_GATES: Final = [
    {
        "id": "ST0902-GATE-001",
        "topic": "identity_and_active_human_mapping",
        "status": "UNRESOLVED",
        "safe_default": "NO_ACTOR_OR_AUTHORITY",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-002",
        "topic": "final_approve_role_and_resource_scope",
        "status": "UNRESOLVED",
        "safe_default": "DENY",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-003",
        "topic": "mfa_claim_mapping",
        "status": "UNRESOLVED",
        "safe_default": "DENY",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-004",
        "topic": "step_up_conflict_and_freshness",
        "status": "CONFLICTING_SOURCES",
        "safe_default": "DENY",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-005",
        "topic": "separation_of_duties_self_comparator_and_solo_exception",
        "status": "UNRESOLVED",
        "safe_default": "DENY_WITH_NO_SOLO_EXCEPTION",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-006",
        "topic": "effective_st0901_review_decision",
        "status": "NOT_DEFINED",
        "safe_default": "NO_EFFECTIVE_DECISION",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-007",
        "topic": "checklist_and_preapproval_gate_hash_manifest",
        "status": "NOT_DEFINED",
        "safe_default": "NO_GATE_MANIFEST",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-008",
        "topic": "finding_and_waiver_truth",
        "status": "UNRESOLVED",
        "safe_default": "NO_CLEARANCE_OR_ZERO_FINDING_CLAIM",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-009",
        "topic": "quality_source_policy_evidence_and_freshness",
        "status": "NOT_AUTHORITATIVE",
        "safe_default": "NO_EVIDENCE_ELIGIBILITY",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-010",
        "topic": "idempotency_audit_unit_of_work_transaction_and_outbox",
        "status": "NOT_IMPLEMENTED",
        "safe_default": "NO_COMMAND_OR_SIDE_EFFECT",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
    {
        "id": "ST0902-GATE-011",
        "topic": "approval_revocation_supersession_effectiveness_and_publication",
        "status": "NOT_DEFINED",
        "safe_default": "NO_APPROVAL_REJECTION_REVOCATION_OR_PUBLICATION_EFFECT",
        "resolution_required": "OWNER_APPROVED_DESIGN_HANDOFF_V1",
    },
]

EXPECTED_RECORD_DEFAULTS: Final = {
    "approval": {
        "command_status": "NOT_EXECUTED",
        "evaluation_status": "NOT_EVALUATED",
        "authority": "ABSENT",
        "commands": [],
        "requests": [],
        "results": [],
        "records": [],
    },
    "rejection": {
        "command_status": "NOT_EXECUTED",
        "evaluation_status": "NOT_EVALUATED",
        "authority": "ABSENT",
        "requests": [],
        "results": [],
        "records": [],
        "empty_records_interpretation": "NO_COMMAND_OR_EVIDENCE_NOT_ZERO_REJECTED",
    },
    "revocation": {
        "command_status": "NOT_EXECUTED",
        "evaluation_status": "NOT_EVALUATED",
        "authority": "ABSENT",
        "requests": [],
        "results": [],
        "records": [],
    },
    "events": {
        "execution_status": "NOT_EXECUTED",
        "approval_granted": [],
        "approval_revoked": [],
    },
    "audits": {"execution_status": "NOT_EXECUTED", "records": []},
    "idempotency": {"execution_status": "NOT_EXECUTED", "entries": []},
}
EXPECTED_EXECUTION_DEFAULTS: Final = {
    "runtime_reader": "NOT_IMPLEMENTED",
    "network": "NOT_EXECUTED",
    "filesystem_runtime": "NOT_EXECUTED",
    "clock": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "api": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "audit": "NOT_EXECUTED",
    "idempotency": "NOT_EXECUTED",
    "approval": "NOT_EXECUTED",
    "rejection": "NOT_EXECUTED",
    "revocation": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "external_actions": [],
}
EXPECTED_VERIFICATION_DEFAULTS: Final = {
    "local_reference_checks": "NOT_EXECUTED",
    "formal_tst_011": "NOT_EXECUTED",
    "formal_tst_012": "NOT_EXECUTED",
    "formal_tst_020": "NOT_EXECUTED",
    "formal_tst_021": "NOT_EXECUTED",
    "formal_tst_022": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "story_acceptance": False,
    "readiness": "NOT_READY",
    "production_eligible": False,
}
EXPECTED_IMPLEMENTATION_BOUNDARY: Final = {
    "new_files": [
        CONTRACT_PATH.as_posix(),
        GENERATOR_PATH.as_posix(),
        REFERENCE_PLAN_PATH.as_posix(),
        MANIFEST_PATH.as_posix(),
        README_PATH.as_posix(),
        *(path.as_posix() for path in TEST_PATHS),
    ],
    "existing_files_modified": False,
    "runtime_modules": [],
    "positive_executable_slice_requires": ("SEPARATE_OWNER_APPROVED_DESIGN_HANDOFF_V1"),
    "negative_executable_slice_requires": ("SEPARATE_OWNER_APPROVED_DESIGN_HANDOFF_V1"),
}


class FinalApprovalReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise FinalApprovalReferenceError(f"ST-0902 build failed: {code} field={field}")


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


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        content = physical.read_bytes()
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


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


def _require_fragments(
    root: Path, relative: Path, fragments: tuple[str, ...], field: str
) -> None:
    content = _text(root, relative, field)
    if any(fragment not in content for fragment in fragments):
        _fail("SOURCE_SEMANTIC_DRIFT", field)


def _find(rows: object, identifier: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(row, field)
        for row in _list(rows, field)
        if _mapping(row, field).get("id") == identifier
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
    if len(matches) != 1 or any(
        key is None or value is None for key, value in matches[0].items()
    ):
        _fail("SOURCE_ID_DRIFT", field)
    return matches[0]


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_dependency_rows() -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {
        story_id: [] for story_id in _DEPENDENCY_METADATA
    }
    for story_id, role, path, digest in DEPENDENCY_INPUTS:
        grouped[story_id].append(
            {"role": role, "uri": f"repo://{path}", "sha256": digest}
        )
    rows: list[dict[str, object]] = []
    for story_id, (scope, connection, authority) in _DEPENDENCY_METADATA.items():
        row: dict[str, object] = {
            "story_id": story_id,
            "implementation_scope": scope,
            "artifacts": grouped[story_id],
            "connection_status": connection,
        }
        if story_id == "ST-0901":
            row["effective_decision_status"] = "NOT_DEFINED"
        row["authority_status"] = authority
        rows.append(row)
    return rows


def _validate_source_hashes(root: Path) -> None:
    for role, path, expected in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(path), f"source.{role}")) != expected:
            _fail("SOURCE_HASH_MISMATCH", f"source.{role}")
    for story_id, role, path, expected in DEPENDENCY_INPUTS:
        if (
            _sha256(_read(root, Path(path), f"dependency.{story_id}.{role}"))
            != expected
        ):
            _fail("DEPENDENCY_HASH_MISMATCH", f"dependency.{story_id}.{role}")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_HASH_MISMATCH", "helper")


EXPECTED_STORY: Final = {
    "id": "ST-0902",
    "epic_id": "EPIC-09",
    "title": "Final approval",
    "objective": "全Gate/hashを束ねる承認",
    "depends_on": ["ST-0901", "ST-0605", "ST-0805"],
    "requirement_ids": ["FR-009"],
    "design_refs": [],
    "deliverables": ["approval command"],
    "acceptance_criteria": ["self approval separation", "blocking finding rejects"],
    "test_suites": ["TST-012", "TST-021"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}


def _project_story(root: Path) -> dict[str, object]:
    catalog = _load_yaml(root, STORY_PATH, "story")
    story = _find(catalog.get("stories"), "ST-0902", "story")
    _exact(story, EXPECTED_STORY, "story")
    return {
        key: story[key]
        for key in (
            "id",
            "objective",
            "depends_on",
            "requirement_ids",
            "deliverables",
            "acceptance_criteria",
            "design_status",
            "implementation_status",
            "verification_status",
        )
    }


def _project_traces(root: Path) -> dict[str, object]:
    master = _csv_row(root, MASTER_TRACE_PATH, "FR-009", "master_trace")
    acceptance = _csv_row(root, ACCEPTANCE_TRACE_PATH, "FR-009", "acceptance_trace")
    if (
        master.get("requirement") != "require_human_approval_by_default"
        or master.get("story_ids") != "ST-0901;ST-0902"
        or master.get("test_suite_ids") != "TST-011;TST-012;TST-020;TST-021"
        or master.get("coverage_status") != "DESIGNED_NOT_IMPLEMENTED"
    ):
        _fail("TRACE_DRIFT", "master_trace")
    try:
        acceptance_tests = ast.literal_eval(acceptance.get("test_suites", ""))
    except SyntaxError, ValueError:
        _fail("TRACE_DRIFT", "acceptance_trace")
    if (
        acceptance.get("requirement") != "require_human_approval_by_default"
        or acceptance_tests != ["TST-012", "TST-021", "TST-022"]
        or acceptance.get("implementation_status") != "NOT_STARTED"
        or acceptance.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TRACE_DRIFT", "acceptance_trace")
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    for suite_id in ("TST-011", "TST-012", "TST-020", "TST-021", "TST-022"):
        suite = _find(suites.get("suites"), suite_id, "test_catalog")
        if (
            suite.get("release_blocking") is not True
            or suite.get("implementation_status") != "NOT_STARTED"
            or suite.get("execution_status") != "NOT_EXECUTED"
        ):
            _fail("TEST_CATALOG_DRIFT", "test_catalog")
    return {
        "story_test_suites": ["TST-012", "TST-021"],
        "master_fr009_test_suites": ["TST-011", "TST-012", "TST-020", "TST-021"],
        "acceptance_fr009_test_suites": ["TST-012", "TST-021", "TST-022"],
        "traceability_status": "DIVERGENT_RECORDED_NOT_RESOLVED",
    }


def _operation_projection(
    api: Mapping[str, Any], path: str, operation_id: str, scope: str, audit: str
) -> dict[str, object]:
    paths = _mapping(api.get("paths"), "admin_api.paths")
    operation = _mapping(
        _mapping(paths.get(path), "admin_api.path").get("post"), "admin_api.operation"
    )
    request = _mapping(operation.get("requestBody"), "admin_api.request")
    content = _mapping(request.get("content"), "admin_api.request")
    request_schema = _mapping(
        _mapping(content.get("application/json"), "admin_api.request").get("schema"),
        "admin_api.request",
    ).get("$ref")
    responses = _mapping(operation.get("responses"), "admin_api.responses")
    response = _mapping(responses.get("201"), "admin_api.response")
    response_content = _mapping(response.get("content"), "admin_api.response")
    response_schema = _mapping(
        _mapping(response_content.get("application/json"), "admin_api.response").get(
            "schema"
        ),
        "admin_api.response",
    ).get("$ref")
    security = _list(operation.get("security"), "admin_api.security")
    scopes = _list(
        _mapping(security[0], "admin_api.security").get("oidcOAuth2"),
        "admin_api.security",
    )
    expected_request = (
        "#/components/schemas/ApprovalRequest"
        if operation_id == "PUBADM-005"
        else "#/components/schemas/RevokeApprovalRequest"
    )
    if (
        operation.get("operationId") != operation_id
        or operation.get("x-raos-operation-id") != operation_id
        or operation.get("x-raos-kind") != "command"
        or operation.get("x-raos-requirements") != ["FR-009", "FR-020"]
        or operation.get("x-raos-implementation-slice") != "SLICE-014"
        or operation.get("x-raos-idempotency-required") is not True
        or operation.get("x-raos-concurrency-required") is not False
        or operation.get("x-raos-async-job-type") is not None
        or operation.get("x-raos-audit-action") != audit
        or scopes != [scope]
        or request_schema != expected_request
        or response_schema != "#/components/schemas/Approval"
    ):
        _fail("API_OPERATION_DRIFT", operation_id)
    return {
        "method": "POST",
        "path": path,
        "operation_id": operation_id,
        "kind": "command",
        "authentication": "admin",
        "scopes": [scope],
        "request_schema": expected_request.rsplit("/", 1)[-1],
        "response_schema": "Approval",
        "success": 201,
        "idempotency_required": True,
        "concurrency_required": False,
        "async_job_type": None,
        "audit_action": audit,
        "requirements": ["FR-009", "FR-020"],
        "implementation_slice": "SLICE-014",
    }


def _project_api(
    root: Path,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    api = _load_yaml(root, ADMIN_API_PATH, "admin_api")
    pubadm_005 = _operation_projection(
        api,
        "/api/v1/admin/approvals",
        "PUBADM-005",
        "publishing:approval:decide",
        "approval_record",
    )
    pubadm_006 = _operation_projection(
        api,
        "/api/v1/admin/approvals/{id}/revoke",
        "PUBADM-006",
        "publishing:approval:revoke",
        "approval_revoke",
    )
    schemas = _mapping(
        _mapping(api.get("components"), "admin_api.components").get("schemas"),
        "admin_api.schemas",
    )
    request = _mapping(schemas.get("ApprovalRequest"), "approval_request")
    revoke = _mapping(schemas.get("RevokeApprovalRequest"), "revoke_request")
    response = _mapping(schemas.get("Approval"), "approval_response")
    request_properties = _mapping(request.get("properties"), "approval_request")
    revoke_properties = _mapping(revoke.get("properties"), "revoke_request")
    response_properties = _mapping(response.get("properties"), "approval_response")
    approval_type = _mapping(request_properties.get("approval_type"), "approval_type")
    decision = _mapping(request_properties.get("decision"), "decision")
    reason = _mapping(request_properties.get("decision_reason"), "decision_reason")
    valid_until = _mapping(request_properties.get("valid_until"), "valid_until")
    revoke_reason = _mapping(revoke_properties.get("reason"), "revoke_reason")
    api_projection: dict[str, object] = {
        "request": {
            "additional_properties": request.get("additionalProperties"),
            "property_names": list(request_properties),
            "required": request.get("required"),
            "approval_types": approval_type.get("enum"),
            "decisions": decision.get("enum"),
            "decision_reason_min_length": reason.get("minLength"),
            "decision_reason_max_length": reason.get("maxLength"),
            "valid_until_nullable": valid_until.get("type") == ["string", "null"],
        },
        "revoke_request": {
            "additional_properties": revoke.get("additionalProperties"),
            "property_names": list(revoke_properties),
            "required": revoke.get("required"),
            "reason_min_length": revoke_reason.get("minLength"),
            "reason_max_length": revoke_reason.get("maxLength"),
        },
        "response": {
            "additional_properties": response.get("additionalProperties"),
            "required": response.get("required"),
            "approved_by_principal_id_exposed": (
                "approved_by_principal_id" in response_properties
            ),
            "revoked_by_principal_id_exposed": (
                "revoked_by_principal_id" in response_properties
            ),
        },
    }
    return pubadm_005, pubadm_006, api_projection


def _project_database(root: Path) -> dict[str, object]:
    constraints = [
        "approval_type IN ('EDITORIAL', 'FACT', 'COMPLIANCE', 'FINAL')",
        "decision IN ('APPROVED', 'REJECTED', 'REVOKED')",
        "valid_until IS NULL OR valid_until > approved_at",
        "(revoked_at IS NULL) = (revoked_by_principal_id IS NULL)",
        "decision <> 'REVOKED' OR (supersedes_approval_id IS NOT NULL AND revoked_at IS NOT NULL AND revoked_by_principal_id IS NOT NULL)",
    ]
    _require_fragments(
        root,
        DATA_MODEL_PATH,
        (
            "### `publishing.approval`",
            "- **Write pattern:** `LIFECYCLE`",
            "- **Classification:** `RESTRICTED`",
            *(f"`{constraint}`" for constraint in constraints),
            "Final APPROVED decision is made by an active USER principal.",
            "Critical zero-tolerance RuleはDB/Serviceで申請不可にする。",
            "status IN ('OPEN', 'FIXED', 'WAIVED', 'FALSE_POSITIVE', 'ACCEPTED_RISK')",
        ),
        "data_model",
    )
    guard_path = Path("changes/st-0305/contracts/physical/publishing-guards.sql")
    _require_fragments(
        root,
        guard_path,
        (
            "IF NEW.approval_type <> 'FINAL' OR NEW.decision <> 'APPROVED' THEN",
            "RETURN NEW;",
            "principal.principal_type = 'USER'",
            "principal.status = 'ACTIVE'",
            "quality_run.status = 'PASSED'",
            "quality_run.blocking_finding_count = 0",
            "source_packet_version.status = 'APPROVED'",
            "quality_score.passed IS TRUE",
            "finding.is_blocking IS TRUE",
            "finding.status = 'OPEN'",
        ),
        "st0305_guard",
    )
    return {
        "write_pattern": "LIFECYCLE",
        "classification": "RESTRICTED",
        "approval_types": ["EDITORIAL", "FACT", "COMPLIANCE", "FINAL"],
        "decisions": ["APPROVED", "REJECTED", "REVOKED"],
        "constraints": constraints,
        "final_approved_guard": {
            "applies_to": "FINAL_APPROVED_ONLY",
            "other_decision_outcome": "RETURN_NEW",
            "requires_active_user": True,
            "requires_passed_quality_run": True,
            "requires_zero_cached_blocking_findings": True,
            "requires_approved_source_packet": True,
            "requires_passed_quality_score": True,
            "blocking_query_status": "OPEN_ONLY",
            "role_scope_mfa_step_up_sod_self_check": False,
            "effective_review_check": False,
            "full_gate_hash_manifest_check": False,
            "authoritative_claim_coverage_check": False,
            "waiver_truth_check": False,
        },
    }


def _event_projection(
    root: Path,
    path: Path,
    event_type: str,
    expected_properties: list[str],
    expected_required: list[str],
) -> dict[str, object]:
    schema = _load_json(root, path, event_type)
    all_of = _list(schema.get("allOf"), event_type)
    if len(all_of) != 2:
        _fail("EVENT_SCHEMA_DRIFT", event_type)
    overlay = _mapping(all_of[1], event_type)
    properties = _mapping(overlay.get("properties"), event_type)
    type_schema = _mapping(properties.get("type"), event_type)
    producer_schema = _mapping(properties.get("producer"), event_type)
    data = _mapping(properties.get("data"), event_type)
    data_properties = _mapping(data.get("properties"), event_type)
    if (
        type_schema.get("const") != event_type
        or producer_schema.get("const") != "publishing"
        or data.get("additionalProperties") is not False
        or list(data_properties) != expected_properties
        or data.get("required") != expected_required
    ):
        _fail("EVENT_SCHEMA_DRIFT", event_type)
    return {
        "event_type": event_type,
        "producer": "publishing",
        "property_names": expected_properties,
        "required": expected_required,
    }


def _project_events(root: Path) -> dict[str, object]:
    granted = _event_projection(
        root,
        APPROVAL_GRANTED_EVENT_PATH,
        "jp.raos.publishing.approval_granted.v1",
        [
            "approval_id",
            "article_version_id",
            "approval_type",
            "quality_check_run_id",
            "policy_bundle_id",
            "valid_until",
        ],
        [
            "approval_id",
            "article_version_id",
            "approval_type",
            "quality_check_run_id",
            "policy_bundle_id",
        ],
    )
    revoked = _event_projection(
        root,
        APPROVAL_REVOKED_EVENT_PATH,
        "jp.raos.publishing.approval_revoked.v1",
        ["approval_id", "article_version_id", "revoked_at", "reason"],
        ["approval_id", "article_version_id", "revoked_at", "reason"],
    )
    return {
        "granted": granted,
        "revoked": revoked,
        "rejected_event_contract": "ABSENT",
        "actor_and_gate_hash_binding": "ABSENT",
    }


def _project_security(root: Path) -> dict[str, object]:
    catalog = _load_yaml(root, ROLE_MATRIX_PATH, "role_matrix")
    permission = [
        _mapping(row, "role_matrix.permission")
        for row in _list(catalog.get("permissions"), "role_matrix.permissions")
        if _mapping(row, "role_matrix.permission").get("action") == "final_approve"
    ]
    if len(permission) != 1:
        _fail("ROLE_MATRIX_DRIFT", "final_approve")
    row = permission[0]
    expected = {
        "action": "final_approve",
        "data_class": "CONFIDENTIAL",
        "allowed_roles": ["MANAGING_EDITOR"],
        "mfa_required": True,
        "step_up_required": False,
        "separation_of_duties": True,
        "implementation_status": "NOT_STARTED",
        "runtime_verification": "NOT_EXECUTED",
    }
    _exact(row, expected, "final_approve")
    _require_fragments(
        root,
        SECURITY_DESIGN_PATH,
        (
            "Final Approval、Publish、Rollback、Kill Switch解除、Revenue CommitはStep-up対象。",
            "EditorとFinal Approverの分離を標準とし、例外は理由と上位承認を監査する。",
            "OIDC Providerは未決であり、Production認証は`NOT_CONFIGURED`である。",
        ),
        "security_design",
    )
    _require_fragments(
        root,
        API_DESIGN_PATH,
        (
            "Final Approval等はMFA claimとStep-up freshnessを要求する。",
            "API-OPEN-001 | Production OIDC providerとMFA/step-up claim名。",
        ),
        "api_design",
    )
    return {
        "final_approve_role": {
            key: row[key]
            for key in (
                "allowed_roles",
                "mfa_required",
                "step_up_required",
                "separation_of_duties",
                "implementation_status",
                "runtime_verification",
            )
        },
        "security_and_api_require_step_up": True,
        "step_up_contract_status": "CONFLICTING_SOURCES",
    }


def _validate_context_semantics(root: Path) -> None:
    _require_fragments(
        root,
        CANONICAL_DECISIONS_PATH,
        (
            "- id: INT-DEC-009",
            "auto-publishはMVPで無効",
            "- id: INT-DEC-013",
            "最終承認の権限を持たない",
        ),
        "canonical_decisions",
    )
    _require_fragments(
        root,
        OPEN_DECISIONS_PATH,
        (
            "id: OD-005",
            "公開不可、利益計算の人件費はUNKNOWN",
            "id: OD-010",
            "Local fake authはdevelopmentのみ。外部公開不可",
        ),
        "open_decisions",
    )
    _require_fragments(
        root,
        ARCHITECTURE_PATH,
        (
            "Blocking Findingを解消しない限りApprove不可",
            "Approval時にArticle Version、Source Packet、Policy Bundle、Quality ResultをFreeze",
            "ApprovalはActor、時刻、Role、理由、MFA状態を記録",
            "1名運用時の兼務は許すが、Role切替と明示操作を残す。",
        ),
        "system_architecture",
    )
    _require_fragments(
        root,
        CONTENT_DESIGN_PATH,
        (
            "AND every axis >= floor",
            "AND zero-tolerance blockers = 0",
            "AND unresolved blocking findings = 0",
            "AND human approval exists",
            "QG-CONT-011 | publication_snapshot",
            "QG-CONT-012 | post_publication",
            "AuthorとFinal Approverを別Actorにする。",
            "同一自然人がRoleを兼務できる。",
            "Approval時に再認証",
        ),
        "content_design",
    )
    _require_fragments(
        root,
        SECURITY_CONTROLS_PATH,
        (
            "title: OIDC only admin",
            "title: MFA mandatory",
            "title: Step-up critical actions",
            "title: Least privilege",
            "title: Server authorization",
        ),
        "security_controls",
    )
    dependency_fragments = {
        "changes/st-0402/README.md": (
            "provider-neutral MFA step-up seam",
            "critical-action mapping",
        ),
        "changes/st-0403/README.md": (
            "TEST_ONLY:*",
            "action-to-OAuth-scope-to-operation/resource/state map",
        ),
        "changes/st-0405/README.md": (
            "process-local only",
            "It does **not** make a",
            "business mutation and audit event atomic.",
        ),
        "changes/st-0605/README.md": (
            "SOURCE_DERIVED_NONEXECUTABLE_CLAIM_EVIDENCE_COVERAGE_REFERENCE_PLAN",
            "Coverage is unevaluable",
        ),
        "changes/st-0805/README.md": (
            "PURE_DETERMINISTIC_LOCAL_EDITORIAL_POLICY_EVALUATOR",
            "publication_authorized=false",
        ),
        "changes/st-0901/README.md": (
            "APPROVE_GATE_UNRESOLVED",
            "contains no positive approval",
        ),
        "changes/st-0901/README_PR3.md": (
            "no latest/effective/tail",
            "Final approval, approval separation",
        ),
        "python/raos/domain/publishing/review_workflow.py": (
            "APPROVE_GATE_UNRESOLVED",
            "Validate structure only; never append, approve, authorize, or mutate.",
        ),
        "python/raos/domain/publishing/review_decision_operations.py": (
            "it has no effective state",
            "no tail, latest, or effective semantics",
        ),
    }
    for path, fragments in dependency_fragments.items():
        _require_fragments(root, Path(path), fragments, f"dependency.{path}")


def _contract_projection(root: Path) -> dict[str, object]:
    pubadm_005, pubadm_006, approval_api = _project_api(root)
    return {
        "story": _project_story(root),
        "trace_variants": _project_traces(root),
        "pubadm_005": pubadm_005,
        "pubadm_006": pubadm_006,
        "approval_api": approval_api,
        "approval_database": _project_database(root),
        "approval_events": _project_events(root),
        "security_projection": _project_security(root),
    }


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _exact(contract["pro_assistance"], EXPECTED_PRO_ASSISTANCE, "pro_assistance")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_INSTALLED_CONTRACTS",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["dependencies"], _expected_dependency_rows(), "dependencies")
    _exact(contract["hard_gates"], EXPECTED_HARD_GATES, "hard_gates")
    _exact(contract["record_defaults"], EXPECTED_RECORD_DEFAULTS, "record_defaults")
    _exact(
        contract["execution_defaults"],
        EXPECTED_EXECUTION_DEFAULTS,
        "execution_defaults",
    )
    _exact(
        contract["verification_defaults"],
        EXPECTED_VERIFICATION_DEFAULTS,
        "verification_defaults",
    )
    _exact(
        contract["implementation_boundary"],
        EXPECTED_IMPLEMENTATION_BOUNDARY,
        "implementation_boundary",
    )
    _validate_source_hashes(root)
    _validate_context_semantics(root)
    _exact(
        contract["contract_projection_defaults"],
        _contract_projection(root),
        "contract_projection_defaults",
    )
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
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
        },
        "dependencies": contract["dependencies"],
        "hard_gates": contract["hard_gates"],
        "contract_projection": contract["contract_projection_defaults"],
        "record_boundary": contract["record_defaults"],
        "execution_boundary": {
            **dict(_mapping(contract["execution_defaults"], "execution")),
            "action_counts": {
                "command": 0,
                "request": 0,
                "result": 0,
                "approval_record": 0,
                "rejection_record": None,
                "revocation_record": 0,
                "event": 0,
                "audit": 0,
                "idempotency_entry": 0,
                "publication": 0,
            },
            "rejection_count_interpretation": ("NOT_EVALUATED_NO_COMMAND_OR_EVIDENCE"),
        },
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
            "id": "RAOS-ST0902-FINAL-APPROVAL-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0902",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "dependency_inputs": [
                {
                    "story_id": story_id,
                    "role": role,
                    "uri": f"repo://{path}",
                    "sha256": digest,
                }
                for story_id, role, path, digest in DEPENDENCY_INPUTS
            ],
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "pro_assistance": "PRO_UNAVAILABLE_NONE_NO_PROPOSAL_NO_CONTENT",
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "boundary": {
            "classification": EXPECTED_DOCUMENT["classification"],
            "executable": False,
            "runtime_reader": "NOT_IMPLEMENTED",
            "approval_authority": False,
            "rejection_authority": False,
            "revocation_authority": False,
            "approval_commands": "NOT_EXECUTED",
            "rejection_commands": "NOT_EXECUTED",
            "revocation_commands": "NOT_EXECUTED",
            "records": "NOT_EVALUATED",
            "empty_rejection_records": "NO_COMMAND_OR_EVIDENCE_NOT_ZERO_REJECTED",
            "events": "NOT_EXECUTED",
            "audits": "NOT_EXECUTED",
            "idempotency": "NOT_EXECUTED",
            "formal_tst_011": "NOT_EXECUTED",
            "formal_tst_012": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "formal_tst_021": "NOT_EXECUTED",
            "formal_tst_022": "NOT_EXECUTED",
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


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative, content in outputs.items():
        base._atomic_write(root, relative, content)  # noqa: SLF001


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
    except (FinalApprovalReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0902 final-approval reference plan checked"
        if args.check
        else "ST-0902 final-approval reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
