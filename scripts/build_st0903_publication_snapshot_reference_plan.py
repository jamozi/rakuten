#!/usr/bin/env python3
"""Build the strict non-executable ST-0903 publication-snapshot reference plan."""

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
    "changes/st-0903/contracts/publication-snapshot-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0903/generated/publication-snapshot-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0903/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st0903_publication_snapshot_reference_plan.py"
)
README_PATH: Final = Path("changes/st-0903/README.md")
TEST_PATHS: Final = (
    Path("tests/st0903/conftest.py"),
    Path("tests/st0903/test_contract.py"),
    Path("tests/st0903/test_generation.py"),
    Path("tests/st0903/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0903_publication_snapshot_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
CONTRACT_SHA256: Final = (
    "00d031f8ed8d2ab4597ef0de6e88ecbefaf1321f4829937d53ba9d682731d827"
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
CONTENT_MANIFEST_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/schemas/"
    "publication-content-manifest.schema.json"
)
SNAPSHOT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/common/publication-snapshot.schema.json"
)
ARTIFACT_REF_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/common/artifact-ref.schema.json"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/"
    "publishing-build-snapshot-v1.schema.json"
)
EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/"
    "jp-raos-publishing-snapshot-built-v1.schema.json"
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
        "content_manifest_schema",
        CONTENT_MANIFEST_SCHEMA_PATH.as_posix(),
        "97b31e1e8b1288bdb25ec5d1df3c29f101912ca4b5b0c953ae07da809369c881",
    ),
    (
        "publication_snapshot_schema",
        SNAPSHOT_SCHEMA_PATH.as_posix(),
        "2b1aa3d1035cd997d3262786fdfd80aa5c25df62e2c758ac481179c5d6803c38",
    ),
    (
        "artifact_ref_schema",
        ARTIFACT_REF_SCHEMA_PATH.as_posix(),
        "9d47faf85d4986e6340a0d71dbf5e340b3475270c20a7d03056cd51d679ef930",
    ),
    (
        "job_catalog",
        JOB_CATALOG_PATH.as_posix(),
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        "build_snapshot_job_schema",
        JOB_SCHEMA_PATH.as_posix(),
        "e2b8680b25276a3b23002a567d65f333d7df4d13fdecb8d4e2b2f1d8919bbacd",
    ),
    (
        "snapshot_built_event_schema",
        EVENT_SCHEMA_PATH.as_posix(),
        "6651393069ae07c1b45a9b6e2cece31157f7a821a53f68c88538fb8a4726727f",
    ),
    (
        "public_openapi",
        "contracts/raos-v0.4/contracts/openapi-public.v0.1.yaml",
        "8122958e80e04096ba3b254b4a8d843138bb757c8fc4e71bd8406914dba80797",
    ),
)

DEPENDENCY_INPUTS: Final = (
    (
        "ST-0902",
        "changes/st-0902/contracts/final-approval-reference-plan.v1.yaml",
        "6f449d9a1bdc58baada052dbc89e71aa42d6a133ecc8ba3d64d57cc6f536c08f",
    ),
    (
        "ST-0807",
        "changes/st-0807/README.md",
        "333f953e4f15b05c5b70705259643b3531e0259faa26c7612e278962130917a5",
    ),
    (
        "ST-0808",
        "changes/st-0808/README.md",
        "385f7f849bd4b16296ec47c512bf109b58f49861b0533df47a1825e65475651b",
    ),
    (
        "ST-0202",
        "changes/st-0202/contracts/local-object-storage.v1.yaml",
        "76bb9581ec8b78be57ca325040f996369a2a132aa48462da860a8385f1291b15",
    ),
    (
        "ST-0305",
        "changes/st-0305/README.md",
        "b45c333996c723ab1978c8b474420de86c563277a3c4a0d2e2a7d76cdbaed4bb",
    ),
    (
        "ST-0306",
        "changes/st-0306/contracts/database-roles-grants.v1.yaml",
        "20b5c37d6979b67f4b4a5b014f7b18a9f729c889b47ca6cc6916f58b2ef08fc5",
    ),
    (
        "ST-0307",
        "changes/st-0307/contracts/migration-upgrade-fixtures.v1.yaml",
        "4139aca30bcb7376f806e2debc40bacb1fcdc59c934a419e7ea97859b7247ec4",
    ),
    (
        "ST-0601",
        "changes/st-0601/README.md",
        "93759bfea0e51fbbd6b5fe8858fa27f3ed6e5677b0bde3f5a198997ada003766",
    ),
)

EXPECTED_DEPENDENCY_AUTHORITY: Final = {
    "ST-0902": "NONEXECUTABLE_REFERENCE_PLAN_INSUFFICIENT_FOR_APPROVAL",
    "ST-0807": "CALLER_RESOLVED_NONAUTHORITATIVE_RENDERER_INPUTS",
    "ST-0808": "ADMIN_ONLY_REFERENCE_NO_PUBLIC_RENDERER_INPUT",
    "ST-0202": "LOCAL_RAW_BUCKET_CONTRACT_ONLY",
    "ST-0305": "DATABASE_SCHEMA_CANDIDATE_ONLY",
    "ST-0306": "PUBLIC_READMODEL_ROLE_CANDIDATE_ONLY",
    "ST-0307": "SYNTHETIC_FIXTURE_ONLY",
    "ST-0601": "NONATTESTING_REFERENCE_PLAN_NO_ARTIFACT_REGISTRY",
}
EXPECTED_HARD_GATE_ROWS: Final = (
    (
        "ST0903-GATE-001",
        "authoritative_non_revoked_final_approval",
        "ABSENT",
        "NO_BUILD",
        None,
    ),
    (
        "ST0903-GATE-002",
        "complete_authoritative_input_aggregate",
        "NOT_DEFINED",
        "NO_BUILD",
        None,
    ),
    (
        "ST0903-GATE-003",
        "manifest_snapshot_database_precedence_and_reconciliation",
        "UNRESOLVED",
        "KEEP_SURFACES_DISTINCT_NO_BUILD",
        None,
    ),
    (
        "ST0903-GATE-004",
        "canonical_bytes_hash_self_exclusion_unicode_number_null_and_order",
        "NOT_DEFINED",
        "NO_CANONICAL_OR_SNAPSHOT_DIGEST",
        None,
    ),
    (
        "ST0903-GATE-005",
        "id_display_version_time_generation_and_replay",
        "NOT_DEFINED",
        "NO_IDENTIFIERS_OR_TIMESTAMPS",
        None,
    ),
    (
        "ST0903-GATE-006",
        "approval_revocation_and_effectiveness_at_build_time",
        "NOT_DEFINED",
        "NO_BUILD",
        None,
    ),
    (
        "ST0903-GATE-007",
        "media_seo_disclosure_methodology_product_and_safe_offer_binding",
        "NOT_AUTHORITATIVE",
        "NO_ELIGIBILITY_OR_BINDING",
        None,
    ),
    (
        "ST0903-GATE-008",
        "artifact_object_database_job_event_audit_idempotency_uow_outbox_and_crash_recovery",
        "NOT_IMPLEMENTED",
        "NO_SIDE_EFFECT",
        None,
    ),
    (
        "ST0903-GATE-009",
        "confidential_snapshot_public_allowlist_and_redaction",
        "NOT_DEFINED",
        "NO_PUBLIC_PROJECTION",
        None,
    ),
    (
        "ST0903-GATE-010",
        "executable_pure_or_runtime_builder_authority",
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


class PublicationSnapshotReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


_HELPER_MODULE: ModuleType | None = None


def _fail(code: str, field: str) -> NoReturn:
    raise PublicationSnapshotReferenceError(
        f"ST-0903 build failed: {code} field={field}"
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
    except PublicationSnapshotReferenceError:
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
    except PublicationSnapshotReferenceError:
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
    except PublicationSnapshotReferenceError:
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


def _validate_semantics(root: Path, projection: Mapping[str, Any]) -> None:
    story = _find(
        _load_yaml(root, STORY_PATH, "story")["stories"], "id", "ST-0903", "story"
    )
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
        _exact(
            story[key],
            _mapping(projection["story"], "projection.story")[key],
            f"story.{key}",
        )

    requirement = _find(
        _load_yaml(root, REQUIREMENTS_PATH, "requirements")["functional_requirements"],
        "id",
        "FR-010",
        "requirements",
    )
    _exact(requirement, projection["requirement"], "requirement.FR-010")

    master = _csv_row(root, MASTER_TRACE_PATH, "FR-010", "master_trace")
    acceptance = _csv_row(root, ACCEPTANCE_TRACE_PATH, "FR-010", "acceptance_trace")
    traces = _mapping(projection["trace_variants"], "projection.traces")
    _exact(
        master["story_ids"].split(";"),
        traces["master_story_ids"],
        "trace.master.stories",
    )
    _exact(
        master["test_suite_ids"].split(";"),
        traces["master_test_suites"],
        "trace.master.tests",
    )
    try:
        acceptance_tests = ast.literal_eval(acceptance["test_suites"])
    except SyntaxError, ValueError:
        _fail("SOURCE_SEMANTIC_DRIFT", "trace.acceptance.tests")
    _exact(acceptance_tests, traces["acceptance_test_suites"], "trace.acceptance.tests")

    suite_catalog = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    for suite_id in ("TST-014", "TST-021"):
        suite = _find(suite_catalog["suites"], "id", suite_id, f"test.{suite_id}")
        _exact(suite["execution_status"], "NOT_EXECUTED", f"test.{suite_id}.execution")

    content_schema = _load_json(root, CONTENT_MANIFEST_SCHEMA_PATH, "content_manifest")
    content_projection = _mapping(
        projection["publication_content_manifest_schema"], "projection.content_manifest"
    )
    _exact(
        content_schema["required"],
        content_projection["required"],
        "content_manifest.required",
    )
    _exact(content_schema["additionalProperties"], False, "content_manifest.additional")
    _exact(
        _mapping(content_schema["properties"], "content_manifest.properties")[
            "content_schema_version"
        ],
        {"const": "1.0.0"},
        "content_manifest.content_schema_version",
    )

    snapshot_schema = _load_json(root, SNAPSHOT_SCHEMA_PATH, "snapshot_schema")
    snapshot_projection = _mapping(
        projection["publication_snapshot_schema"], "projection.snapshot_schema"
    )
    _exact(
        snapshot_schema["required"],
        snapshot_projection["required"],
        "snapshot.required",
    )
    _exact(snapshot_schema["additionalProperties"], False, "snapshot.additional")
    snapshot_properties = _mapping(snapshot_schema["properties"], "snapshot.properties")
    _exact(
        _mapping(snapshot_properties["seo_metadata"], "snapshot.seo")[
            "additionalProperties"
        ],
        True,
        "snapshot.seo.additional",
    )

    artifact_schema = _load_json(root, ARTIFACT_REF_SCHEMA_PATH, "artifact_ref")
    artifact_projection = _mapping(
        projection["artifact_reference_schema"], "projection.artifact_ref"
    )
    _exact(
        artifact_schema["required"],
        artifact_projection["required"],
        "artifact_ref.required",
    )

    job = _find(
        _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")["jobs"],
        "job_type",
        "publishing.build_snapshot.v1",
        "job_catalog",
    )
    job_projection = _mapping(
        projection["build_snapshot_job_catalog"], "projection.job"
    )
    for key in (
        "job_type",
        "version",
        "queue",
        "producer",
        "consumer",
        "payload_schema",
        "idempotency_basis",
        "lock_scope",
        "max_attempts",
        "timeout_seconds",
        "retry_classes",
        "non_retry_classes",
        "emits",
    ):
        _exact(job[key], job_projection[key], f"job.{key}")

    job_schema = _load_json(root, JOB_SCHEMA_PATH, "job_schema")
    job_all_of = _list(job_schema["allOf"], "job_schema.allOf")
    job_envelope = _mapping(job_all_of[1], "job_schema.envelope")
    job_properties = _mapping(job_envelope["properties"], "job_schema.properties")
    payload = _mapping(job_properties["payload"], "job_schema.payload")
    payload_projection = _mapping(
        projection["build_snapshot_job_schema"], "projection.job_schema"
    )
    _exact(
        payload["required"],
        payload_projection["payload_required"],
        "job_schema.required",
    )
    _exact(
        list(_mapping(payload["properties"], "job_schema.payload.properties")),
        payload_projection["payload_properties"],
        "job_schema.properties",
    )

    event_schema = _load_json(root, EVENT_SCHEMA_PATH, "event_schema")
    event_all_of = _list(event_schema["allOf"], "event_schema.allOf")
    event_properties = _mapping(
        _mapping(event_all_of[1], "event_schema.envelope")["properties"],
        "event_schema.properties",
    )
    data = _mapping(event_properties["data"], "event_schema.data")
    event_projection = _mapping(
        projection["snapshot_built_event_schema"], "projection.event"
    )
    _exact(data["required"], event_projection["required"], "event.required")
    _exact(data["additionalProperties"], False, "event.additional")

    controls = _load_yaml(root, SECURITY_CONTROLS_PATH, "security_controls")["controls"]
    for control_id in ("SEC-DATA-004", "SEC-DATA-006"):
        control = _find(controls, "id", control_id, f"control.{control_id}")
        _exact(
            control["verification_status"],
            "NOT_EXECUTED",
            f"control.{control_id}.verification",
        )
    threats = _load_yaml(root, THREAT_REGISTER_PATH, "threat_register")["threats"]
    for threat_id in ("THR-018", "THR-019"):
        threat = _find(threats, "id", threat_id, f"threat.{threat_id}")
        _exact(
            threat["verification_status"],
            "NOT_EXECUTED",
            f"threat.{threat_id}.verification",
        )

    fragments = {
        "system_architecture": (
            "承認済みのArticle VersionからPublication Snapshotを生成",
            "公開サイトは公開Projectionのみを読み",
            "at-least-once",
        ),
        "data_model": (
            "### `publishing.publication_snapshot`",
            "**Write pattern:** `APPEND_ONLY`",
            "**Classification:** `CONFIDENTIAL`",
            "uq_publishing_snapshot_hash",
            "### `ops.object_artifact`",
        ),
        "content_design": ("Candidate Universe", "safe offer", "Publication Snapshot"),
        "api_event_job_design": ("publishing.build_snapshot.v1", "snapshot_built"),
    }
    source_map = {role: Path(path) for role, path, _digest in EXPECTED_SOURCES}
    for role, required in fragments.items():
        text = _text(root, source_map[role], f"source.{role}")
        if any(fragment not in text for fragment in required):
            _fail("SOURCE_SEMANTIC_DRIFT", f"source.{role}")

    dependency_fragments = {
        "ST-0902": ("SOURCE_DERIVED_NONEXECUTABLE", "publication_permitted: false"),
        "ST-0807": (
            "PURE_DETERMINISTIC_LOCAL_SEO_RENDERER",
            "CALLER_SUPPLIED_UNAPPROVED",
        ),
        "ST-0808": ("ADMIN_ONLY_REFERENCE", "never yields a URL"),
        "ST-0601": ("SOURCE_BOUND_RECORDED_NON_ATTESTING", "NOT_EXECUTED"),
    }
    dependency_map = {
        story_id: Path(path) for story_id, path, _digest in DEPENDENCY_INPUTS
    }
    for story_id, required in dependency_fragments.items():
        text = _text(root, dependency_map[story_id], f"dependency.{story_id}")
        if any(fragment not in text for fragment in required):
            _fail("DEPENDENCY_SEMANTIC_DRIFT", f"dependency.{story_id}")

    storage = _load_yaml(root, dependency_map["ST-0202"], "dependency.ST-0202")
    bucket = _mapping(
        _mapping(storage["runtime"], "storage.runtime")["bucket"], "storage.bucket"
    )
    storage_projection = _mapping(
        projection["local_storage_boundary"], "projection.storage"
    )
    _exact(bucket["name"], storage_projection["bucket_name"], "storage.bucket.name")
    _exact(
        bucket["retention_period"],
        storage_projection["retention_period"],
        "storage.retention",
    )

    roles = _load_yaml(root, dependency_map["ST-0306"], "dependency.ST-0306")
    public_boundary = _mapping(roles["public_boundary"], "roles.public_boundary")
    public_projection = _mapping(projection["public_isolation"], "projection.public")
    _exact(
        public_boundary["schema_usage"],
        public_projection["public_role_schema_usage"],
        "public.schema",
    )
    _exact(
        public_boundary["table_privileges"],
        public_projection["public_role_table_privileges"],
        "public.privileges",
    )


def _validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    document = _mapping(contract["document"], "document")
    expected_document = {
        "id": "RAOS-ST0903-PUBLICATION-SNAPSHOT-REFERENCE-PLAN-001",
        "version": "1.0.0",
        "story_id": "ST-0903",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLICATION_SNAPSHOT_REFERENCE_PLAN",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "interface_only": True,
        "decision": "NOT_READY",
        "readiness": "NOT_READY",
        "story_acceptance": False,
        "snapshot_builder_authorized": False,
        "runtime_builder_authorized": False,
        "approval_authority": False,
        "publication_permitted": False,
        "production_eligible": False,
    }
    _exact(document, expected_document, "document")
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
    projection = _mapping(contract["contract_projection_defaults"], "projection")
    _validate_semantics(root, projection)

    records = _mapping(contract["record_defaults"], "record_defaults")
    _exact(
        tuple(records),
        (
            "manifests",
            "snapshots",
            "hashes",
            "version_links",
            "artifacts",
            "jobs",
            "events",
            "audits",
            "approvals",
            "publications",
        ),
        "record_defaults.keys",
    )
    for name, value in records.items():
        record = _mapping(value, f"record_defaults.{name}")
        _exact(record["status"], "NOT_EVALUATED", f"record_defaults.{name}.status")
        _exact(record["records"], [], f"record_defaults.{name}.records")
    _exact(
        _mapping(records["snapshots"], "record_defaults.snapshots")[
            "empty_records_interpretation"
        ],
        "NO_BUILD_OR_EVIDENCE_NOT_ZERO_VALID_SNAPSHOTS",
        "record_defaults.snapshots.interpretation",
    )
    execution = _mapping(contract["execution_defaults"], "execution_defaults")
    _exact(execution["runtime_reader"], "NOT_IMPLEMENTED", "execution.runtime_reader")
    _exact(
        execution["pure_snapshot_builder"], "NOT_IMPLEMENTED", "execution.pure_builder"
    )
    _exact(
        execution["runtime_snapshot_builder"],
        "NOT_IMPLEMENTED",
        "execution.runtime_builder",
    )
    _exact(execution["external_actions"], [], "execution.external_actions")
    for key, value in execution.items():
        if key not in {
            "runtime_reader",
            "pure_snapshot_builder",
            "runtime_snapshot_builder",
            "external_actions",
        }:
            _exact(value, "NOT_EXECUTED", f"execution.{key}")
    verification = _mapping(contract["verification_defaults"], "verification_defaults")
    _exact(verification["story_acceptance"], False, "verification.story_acceptance")
    _exact(verification["readiness"], "NOT_READY", "verification.readiness")
    _exact(verification["production_eligible"], False, "verification.production")
    for key, value in verification.items():
        if key not in {"story_acceptance", "readiness", "production_eligible"}:
            _exact(value, "NOT_EXECUTED", f"verification.{key}")
    boundary = _mapping(contract["implementation_boundary"], "implementation_boundary")
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
        _exact(boundary[key], [], f"implementation_boundary.{key}")
    _exact(
        boundary["executable_builder_requires"],
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
        "implementation_boundary.executable",
    )
    _exact(
        boundary["runtime_builder_requires"],
        "OWNER_APPROVED_DESIGN_HANDOFF_V1",
        "implementation_boundary.runtime",
    )
    return contract


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    try:
        return _validate_contract(contract, root)
    except PublicationSnapshotReferenceError:
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
            "id": "RAOS-ST0903-PUBLICATION-SNAPSHOT-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-0903",
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
            "classification": "SOURCE_DERIVED_NONEXECUTABLE_PUBLICATION_SNAPSHOT_REFERENCE_PLAN",
            "executable": False,
            "runtime_reader": "NOT_IMPLEMENTED",
            "pure_snapshot_builder": "NOT_IMPLEMENTED",
            "runtime_snapshot_builder": "NOT_IMPLEMENTED",
            "records": "NOT_EVALUATED",
            "empty_snapshots": "NO_BUILD_OR_EVIDENCE_NOT_ZERO_VALID_SNAPSHOTS",
            "formal_tst_014": "NOT_EXECUTED",
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
    except PublicationSnapshotReferenceError:
        raise
    except RuntimeError:
        _fail("OUTPUT_PATH_REJECTED", "output")


def _output_file(root: Path, relative: Path) -> Path:
    try:
        return cast(Path, _helper()._output_file(root, relative))
    except PublicationSnapshotReferenceError:
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
    except PublicationSnapshotReferenceError:
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
    except PublicationSnapshotReferenceError:
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
    except PublicationSnapshotReferenceError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-0903 publication-snapshot reference plan checked"
        if args.check
        else "ST-0903 publication-snapshot reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
