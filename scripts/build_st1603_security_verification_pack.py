#!/usr/bin/env python3
"""Build the non-attesting ST-1603 security verification reference pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1506_production_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-1603/contracts/security-verification-pack.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1603/generated/security-verification-pack.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1603/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1603_security_verification_pack.py")
README_PATH: Final = Path("changes/st-1603/README.md")
TEST_PATHS: Final = (
    Path("tests/st1603/conftest.py"),
    Path("tests/st1603/test_contract.py"),
    Path("tests/st1603/test_generation.py"),
    Path("tests/st1603/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st1603_security_verification_pack.py"
)

CONTROL_CATALOG_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
)
STAGING_PLAN_PATH: Final = Path(
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_bindings",
    "catalog_projection",
    "asvs_mapping",
    "verification_suites",
    "findings",
    "remediations",
    "exceptions",
    "evidence",
    "approvals",
    "decision",
    "execution_boundary",
    "evidence_boundary",
)
CONTROL_FIELDS: Final = (
    "id",
    "category",
    "title",
    "requirement",
    "verification",
    "priority",
    "gate",
    "design_status",
    "implementation_status",
    "verification_status",
)
EXPECTED_CATEGORY_COUNTS: Final = {
    "GOV": 8,
    "IAM": 12,
    "APP": 15,
    "DATA": 10,
    "INFRA": 10,
    "AI": 8,
    "SDLC": 12,
    "OPS": 8,
}
EXPECTED_PRIORITY_COUNTS: Final = {"P0": 32, "P1": 51}
EXPECTED_ASVS_MAPPING: Final[dict[str, object]] = {
    "status": "NOT_EXECUTED",
    "mappings": [],
    "invented_mappings": "FORBIDDEN",
}
EXPECTED_VERIFICATION_SUITES: Final[dict[str, object]] = {
    "required_suite_ids": ["TST-026", "TST-031"],
    "required_execution_status": "NOT_EXECUTED",
    "evidence_references": [],
}
EXPECTED_FINDINGS: Final[dict[str, object]] = {
    "collection_status": "NOT_EXECUTED",
    "open_critical": None,
    "open_high": None,
    "items": [],
    "empty_interpretation": "NO_RESULTS_COLLECTED_NOT_ZERO_FINDINGS",
}
EXPECTED_REMEDIATIONS: Final[dict[str, object]] = {
    "collection_status": "NOT_EXECUTED",
    "items": [],
    "empty_interpretation": "NO_REMEDIATIONS_COLLECTED_NOT_COMPLETE",
}
EXPECTED_EXCEPTIONS: Final[dict[str, object]] = {
    "collection_status": "NOT_EXECUTED",
    "items": [],
    "empty_interpretation": "NO_EXCEPTIONS_COLLECTED_NOT_APPROVED",
}
EXPECTED_EVIDENCE: Final[dict[str, object]] = {
    "collection_status": "NOT_EXECUTED",
    "control_evidence": [],
    "scan_results": [],
    "manual_results": [],
    "artifacts": [],
    "empty_interpretation": "NO_EVIDENCE_COLLECTED_NOT_PASS",
}
EXPECTED_STAGING_ACTION_COUNTS: Final[dict[str, int]] = {
    "alert": 0,
    "approve": 0,
    "browser": 0,
    "build": 0,
    "create": 0,
    "delete": 0,
    "deploy": 0,
    "migrate": 0,
    "migration_review": 0,
    "production": 0,
    "promote": 0,
    "release": 0,
    "restore": 0,
    "rollback": 0,
    "runtime": 0,
    "security": 0,
    "smoke": 0,
    "telemetry": 0,
    "transport_security": 0,
    "update": 0,
}
EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION: Final[dict[str, object]] = {
    "classification": (
        "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION"
    ),
    "admission_status": "NOT_EVALUATED",
    "eligible": False,
    "complete_mapping": False,
    "required_capability_count": 13,
    "configured_mapping_count": 0,
    "selected_provider_name": None,
    "selected_profile_id": None,
    "default_profile_id": None,
    "fallback_profile_id": None,
    "aws_reference_role": "OPTIONAL_HISTORICAL_REFERENCE_MAPPINGS_ONLY",
    "aws_reference_selected_binding": False,
}
EXPECTED_EXECUTION_BOUNDARY: Final[dict[str, object]] = {
    "executable": False,
    "interface_only": True,
    "activation": "DISABLED",
    "scanner_execution": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "subprocess_execution": "FORBIDDEN",
    "git_execution": "FORBIDDEN",
    "aws_access": "FORBIDDEN",
    "github_access": "FORBIDDEN",
    "environment_access": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "staging_action": "FORBIDDEN",
    "release_action": "FORBIDDEN",
    "production_action": "FORBIDDEN",
    "action_counts": {
        "scan": 0,
        "network": 0,
        "subprocess": 0,
        "git": 0,
        "aws": 0,
        "github": 0,
        "credential": 0,
        "staging": 0,
        "release": 0,
        "production": 0,
    },
}
EXPECTED_EVIDENCE_BOUNDARY: Final[dict[str, object]] = {
    "classification": (
        "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN"
    ),
    "projection_coverage": "83/83",
    "verified_controls": "0/83",
    "asvs_mapping": "NOT_EXECUTED",
    "formal_tst_026": "NOT_EXECUTED",
    "formal_tst_031": "NOT_EXECUTED",
    "scanner_results": "NOT_EXECUTED",
    "manual_results": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "st_1607_eligible": False,
    "release_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_SOURCE_HASHES: Final = {
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md": (
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
    ),
    "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml": (
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626"
    ),
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml": (
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    CONTROL_CATALOG_PATH.as_posix(): (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md": (
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md": (
        "4d4cffb36f790f15fb467713ee93f9f55e00ea2f3c2b74c19fe3436c56755234"
    ),
}
EXPECTED_PREDECESSOR_HASHES: Final = {
    "changes/st-0407/README.md": (
        "549d4b1e70fc9c3797ed8914721cdf837476b9d497b54ad3f1a3ec61e7f79232"
    ),
    "python/raos/domain/iam/workload_credentials.py": (
        "2419ac466d1b3e671d659c14a9d5c5ad4762a4b50d239d70fede092da886acd5"
    ),
    "python/raos/ports/workload_credentials.py": (
        "da5d8233d783b37ff6a550454037b97de4268f11d6707c5139b2d840ce519e88"
    ),
    "python/raos/application/iam/workload_credentials.py": (
        "8cd0ef7ff2c6210ec3f8116cb5a8bc55025bb1990e963d83a16f34a067d4d004"
    ),
    "python/raos/adapters/development_workload_credentials.py": (
        "42164321018c35f61d71c215d2a0c764d8e04c973dff56194db79e96926046e0"
    ),
    "changes/st-1505/contracts/staging-deployment.v1.yaml": (
        "c70deefd72bd84f4196bea7f078a70f511397f1d759846c200cfb9224468cc69"
    ),
    STAGING_PLAN_PATH.as_posix(): (
        "ba65ac0776c4dd811a2918843e8984945ab92e370892b164bb8099df67950cac"
    ),
    "changes/st-1505/manifest.yaml": (
        "a7e32e2fcc3962d7689a14a80a7838d15001fc57b71c45eeb986dfb3a30756a1"
    ),
}
EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES: Final = {
    "scripts/build_st1506_production_deployment.py": (
        "a57808e2c44feb51ebb4bcc1127c3aa0a64ef77d45d5c570207f66750b04d304"
    ),
}


class SecurityVerificationPackError(RuntimeError):
    """Sanitized ST-1603 generation failure."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"ST1603_ERROR code={code} field={field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise SecurityVerificationPackError(code, field) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail("INVALID_TYPE", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("INVALID_TYPE", field)
    return value


def _exact_mapping(
    value: object, expected: Mapping[str, object], field: str
) -> Mapping[str, Any]:
    observed = _mapping(value, field)
    if tuple(observed.keys()) != tuple(expected.keys()) or observed != expected:
        _fail("CONTRACT_SECTION_DRIFT", field)
    return observed


def _exact_zero(value: object, field: str) -> None:
    if type(value) is not int or value != 0:
        _fail("NONZERO_ACTION", field)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return physical.read_bytes()


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _uri_path(value: object, field: str) -> Path:
    if not isinstance(value, str) or not value.startswith("repo://"):
        _fail("INVALID_URI", field)
    relative = Path(value.removeprefix("repo://"))
    if relative.is_absolute() or ".." in relative.parts:
        _fail("INVALID_URI", field)
    return relative


def _verify_hashes(
    root: Path, rows: object, expected: Mapping[str, str], field: str
) -> None:
    records = _list(rows, field)
    if len(records) != len(expected):
        _fail("SOURCE_INVENTORY_DRIFT", field)
    observed: list[tuple[str, str]] = []
    for index, raw in enumerate(records):
        row = _mapping(raw, f"{field}[{index}]")
        if tuple(row.keys()) != ("uri", "sha256"):
            _fail("SOURCE_SCHEMA_DRIFT", f"{field}[{index}]")
        relative = _uri_path(row["uri"], f"{field}[{index}].uri")
        digest = row["sha256"]
        if not isinstance(digest, str):
            _fail("INVALID_TYPE", f"{field}[{index}].sha256")
        observed.append((relative.as_posix(), digest))
    if observed != list(expected.items()):
        _fail("SOURCE_INVENTORY_DRIFT", field)
    for expected_path, digest in expected.items():
        if _sha256_bytes(_read(root, Path(expected_path), f"{field}.input")) != digest:
            _fail("SOURCE_HASH_DRIFT", field)


def _validate_predecessors(contract: Mapping[str, Any], root: Path) -> None:
    predecessor = _mapping(contract["predecessor_bindings"], "predecessor_bindings")
    if tuple(predecessor.keys()) != ("workload_credential_seam", "staging_deployment"):
        _fail("PREDECESSOR_SCHEMA_DRIFT", "predecessor_bindings")

    workload = _exact_mapping(
        predecessor["workload_credential_seam"],
        {
            "story_id": "ST-0407",
            "readme_uri": "repo://changes/st-0407/README.md",
            "readme_sha256": EXPECTED_PREDECESSOR_HASHES["changes/st-0407/README.md"],
            "source_artifacts": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in list(EXPECTED_PREDECESSOR_HASHES.items())[1:5]
            ],
            "material_free": True,
            "failure_mode": "FAIL_CLOSED",
            "credential_material": "ABSENT",
            "provider_selection": None,
            "live_provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_031": "NOT_EXECUTED",
        },
        "workload",
    )
    staging = _exact_mapping(
        predecessor["staging_deployment"],
        {
            "story_id": "ST-1505",
            "contract_uri": (
                "repo://changes/st-1505/contracts/staging-deployment.v1.yaml"
            ),
            "contract_sha256": EXPECTED_PREDECESSOR_HASHES[
                "changes/st-1505/contracts/staging-deployment.v1.yaml"
            ],
            "reference_plan_uri": (
                "repo://infra/terraform/staging/"
                "staging-deployment.reference-plan.v1.json"
            ),
            "reference_plan_sha256": EXPECTED_PREDECESSOR_HASHES[
                STAGING_PLAN_PATH.as_posix()
            ],
            "manifest_uri": "repo://changes/st-1505/manifest.yaml",
            "manifest_sha256": EXPECTED_PREDECESSOR_HASHES[
                "changes/st-1505/manifest.yaml"
            ],
            "required_classification": (
                "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
                "REFERENCE_PLAN"
            ),
            "executable": False,
            "activation": "DISABLED",
            "credential_material": "ABSENT",
            "live_provider_calls": "FORBIDDEN",
            "external_writes": "FORBIDDEN",
            "action_counts": EXPECTED_STAGING_ACTION_COUNTS,
            "provider_neutral_admission": EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION,
        },
        "staging",
    )
    del workload
    for key, value in _mapping(
        staging["action_counts"], "staging.action_counts"
    ).items():
        _exact_zero(value, f"staging.action_counts.{key}")

    for relative, digest in EXPECTED_PREDECESSOR_HASHES.items():
        if _sha256_bytes(_read(root, Path(relative), "predecessor.input")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor_bindings")

    plan = _load_json(root, STAGING_PLAN_PATH, "staging.plan")
    document = _mapping(plan.get("document"), "staging.plan.document")
    if document.get("artifact_kind") != staging.get("required_classification"):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging.plan.classification")
    if document.get("executable") is not False:
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging.plan.executable")
    activation = _mapping(plan.get("activation"), "staging.plan.activation")
    if activation.get("enabled") is not False or activation.get("status") != "DISABLED":
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging.plan.activation")
    for key, value in _mapping(
        plan.get("action_counts"), "staging.plan.action_counts"
    ).items():
        _exact_zero(value, f"staging.plan.action_counts.{key}")
    _exact_mapping(
        plan.get("action_counts"),
        EXPECTED_STAGING_ACTION_COUNTS,
        "staging.plan.action_counts",
    )
    admission = _mapping(
        plan.get("provider_neutral_staging_admission"),
        "staging.plan.provider_neutral_admission",
    )
    mapping_policy = _mapping(
        admission.get("mapping_policy"),
        "staging.plan.provider_neutral_admission.mapping_policy",
    )
    aws_boundary = _mapping(
        admission.get("aws_reference_boundary"),
        "staging.plan.provider_neutral_admission.aws_reference_boundary",
    )
    observed_provider_neutral_admission = {
        "classification": admission.get("classification"),
        "admission_status": admission.get("admission_status"),
        "eligible": admission.get("eligible"),
        "complete_mapping": mapping_policy.get("complete_mapping"),
        "required_capability_count": mapping_policy.get("required_capability_count"),
        "configured_mapping_count": mapping_policy.get("configured_mapping_count"),
        "selected_provider_name": admission.get("selected_provider_name"),
        "selected_profile_id": admission.get("selected_profile_id"),
        "default_profile_id": admission.get("default_profile_id"),
        "fallback_profile_id": admission.get("fallback_profile_id"),
        "aws_reference_role": aws_boundary.get("role"),
        "aws_reference_selected_binding": aws_boundary.get("selected_binding"),
    }
    _exact_mapping(
        observed_provider_neutral_admission,
        EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION,
        "staging.plan.provider_neutral_admission",
    )
    for key, value in _mapping(
        plan.get("selected_bindings"), "staging.plan.selected"
    ).items():
        if value not in (None, []):
            _fail("PREDECESSOR_SEMANTIC_DRIFT", f"staging.plan.selected.{key}")


def _validate_implementation_dependencies(root: Path) -> None:
    for relative, digest in EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES.items():
        content = _read(root, Path(relative), "implementation_dependency.input")
        if _sha256_bytes(content) != digest:
            _fail("IMPLEMENTATION_DEPENDENCY_HASH_DRIFT", "implementation_dependency")


def _project_controls(root: Path) -> list[dict[str, object]]:
    catalog = _load_yaml(root, CONTROL_CATALOG_PATH, "catalog")
    document = _mapping(catalog.get("document"), "catalog.document")
    if document != {
        "id": "RAOS-SEC-CONTROLS-001",
        "version": "1.0",
        "baseline": "OWASP ASVS 5.0 Level 2 target plus RAOS-specific controls",
    }:
        _fail("CATALOG_IDENTITY_DRIFT", "catalog.document")
    raw_controls = _list(catalog.get("controls"), "catalog.controls")
    controls: list[dict[str, object]] = []
    for index, raw in enumerate(raw_controls):
        row = _mapping(raw, f"catalog.controls[{index}]")
        if tuple(row.keys()) != CONTROL_FIELDS:
            _fail("CONTROL_SCHEMA_DRIFT", f"catalog.controls[{index}]")
        controls.append({key: row[key] for key in CONTROL_FIELDS})
    if len(controls) != 83 or len({row["id"] for row in controls}) != 83:
        _fail("CONTROL_COUNT_DRIFT", "catalog.controls")
    if (
        dict(Counter(str(row["category"]) for row in controls))
        != EXPECTED_CATEGORY_COUNTS
    ):
        _fail("CATEGORY_COUNT_DRIFT", "catalog.controls")
    if (
        dict(Counter(str(row["priority"]) for row in controls))
        != EXPECTED_PRIORITY_COUNTS
    ):
        _fail("PRIORITY_COUNT_DRIFT", "catalog.controls")
    if len({str(row["verification"]) for row in controls}) != 75:
        _fail("VERIFICATION_STRING_DRIFT", "catalog.controls")
    for row in controls:
        if row["gate"] != "GATE-0":
            _fail("CONTROL_STATUS_DRIFT", "catalog.controls.gate")
        if row["design_status"] != "APPROVED_FOR_IMPLEMENTATION":
            _fail("CONTROL_STATUS_DRIFT", "catalog.controls.design_status")
        if row["implementation_status"] != "NOT_STARTED":
            _fail("CONTROL_STATUS_DRIFT", "catalog.controls.implementation_status")
        if row["verification_status"] != "NOT_EXECUTED":
            _fail("CONTROL_STATUS_DRIFT", "catalog.controls.verification_status")
    return controls


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    document = _mapping(contract["document"], "document")
    if document != {
        "id": "RAOS-SECURITY-VERIFICATION-PACK-001",
        "version": "1.0.0",
        "story_id": "ST-1603",
        "status": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
        "formal_verification": "NOT_EXECUTED",
    }:
        _fail("DOCUMENT_DRIFT", "document")
    _verify_hashes(root, contract["sources"], EXPECTED_SOURCE_HASHES, "sources")
    _validate_implementation_dependencies(root)
    _validate_predecessors(contract, root)

    projection = _mapping(contract["catalog_projection"], "catalog_projection")
    expected_projection = {
        "source_document_id": "RAOS-SEC-CONTROLS-001",
        "source_version": "1.0",
        "source_baseline": "OWASP ASVS 5.0 Level 2 target plus RAOS-specific controls",
        "projection_kind": "EXACT_ORDERED_SOURCE_FIELDS",
        "projected_fields": list(CONTROL_FIELDS),
        "expected_control_count": 83,
        "expected_unique_verification_string_count": 75,
        "category_counts": EXPECTED_CATEGORY_COUNTS,
        "priority_counts": EXPECTED_PRIORITY_COUNTS,
        "required_gate": "GATE-0",
        "required_design_status": "APPROVED_FOR_IMPLEMENTATION",
        "required_implementation_status": "NOT_STARTED",
        "required_verification_status": "NOT_EXECUTED",
        "projected_control_count": 83,
        "verified_control_count": 0,
        "interpretation": "INVENTORY_PROJECTION_ONLY_NOT_VERIFICATION",
    }
    if projection != expected_projection:
        _fail("PROJECTION_CONTRACT_DRIFT", "catalog_projection")
    _exact_mapping(contract["asvs_mapping"], EXPECTED_ASVS_MAPPING, "asvs_mapping")
    _exact_mapping(
        contract["verification_suites"],
        EXPECTED_VERIFICATION_SUITES,
        "verification_suites",
    )
    _exact_mapping(contract["findings"], EXPECTED_FINDINGS, "findings")
    _exact_mapping(contract["remediations"], EXPECTED_REMEDIATIONS, "remediations")
    _exact_mapping(contract["exceptions"], EXPECTED_EXCEPTIONS, "exceptions")
    _exact_mapping(contract["evidence"], EXPECTED_EVIDENCE, "evidence")
    if contract["approvals"] is not None or contract["decision"] != "NOT_READY":
        _fail("FALSE_APPROVAL", "decision")
    execution = _exact_mapping(
        contract["execution_boundary"],
        EXPECTED_EXECUTION_BOUNDARY,
        "execution_boundary",
    )
    for key, value in _mapping(
        execution["action_counts"], "execution.action_counts"
    ).items():
        _exact_zero(value, f"execution.action_counts.{key}")
    _exact_mapping(
        contract["evidence_boundary"],
        EXPECTED_EVIDENCE_BOUNDARY,
        "evidence_boundary",
    )
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], controls: list[dict[str, object]]
) -> dict[str, object]:
    projection = dict(_mapping(contract["catalog_projection"], "catalog_projection"))
    projection["controls"] = controls
    projection["projection_coverage"] = "83/83"
    projection["verification_coverage"] = "0/83"
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": GENERATOR_URI,
            "command": GENERATION_COMMAND,
            "source_contract": SOURCE_URI,
        },
        "story": {
            "id": "ST-1603",
            "scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "effective_canonical_status": "UNCHANGED",
        },
        "classification": "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN",
        "executable": False,
        "source_bindings": contract["sources"],
        "predecessor_bindings": contract["predecessor_bindings"],
        "catalog_projection": projection,
        "asvs_mapping": contract["asvs_mapping"],
        "verification_suites": contract["verification_suites"],
        "findings": contract["findings"],
        "remediations": contract["remediations"],
        "exceptions": contract["exceptions"],
        "evidence": contract["evidence"],
        "approvals": None,
        "decision": "NOT_READY",
        "execution_boundary": contract["execution_boundary"],
        "evidence_boundary": contract["evidence_boundary"],
        "prohibited_interpretations": [
            "CATALOG_PROJECTION_IS_NOT_VERIFICATION",
            "EMPTY_FINDINGS_IS_NOT_ZERO_FINDINGS",
            "LOCAL_TESTS_ARE_NOT_FORMAL_TST_026_OR_TST_031",
            "NO_ASVS_OR_THREAT_MAPPING_MAY_BE_INFERRED",
            "NO_APPROVAL_OR_RELEASE_ELIGIBILITY_MAY_BE_INFERRED",
        ],
    }


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def _artifact_row(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.input")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256_bytes(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "document": {
            "id": "RAOS-SECURITY-VERIFICATION-PACK-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1603",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256_bytes(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_SOURCE_HASHES.items()
            ],
            "predecessor_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_PREDECESSOR_HASHES.items()
            ],
            "implementation_inputs": [
                {"uri": f"repo://{path}", "sha256": digest}
                for path, digest in EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES.items()
            ],
        },
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact_row(root, path) for path in SOURCE_PATHS],
        "generated_artifact_count": 1,
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256_bytes(reference_bytes),
            }
        ],
        "manifest_self_integrity": {
            "included_in_generated_artifacts": False,
            "verification": "deterministic byte-for-byte regeneration via --check",
        },
        "boundary": {
            "classification": "SOURCE_DERIVED_NON_ATTESTING_SECURITY_VERIFICATION_REFERENCE_PLAN",
            "projected_controls": 83,
            "verified_controls": 0,
            "open_critical": None,
            "open_high": None,
            "decision": "NOT_READY",
            "st_1607_eligible": False,
            "release_eligible": False,
            "formal_tst_026": "NOT_EXECUTED",
            "formal_tst_031": "NOT_EXECUTED",
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    controls = _project_controls(root)
    reference_bytes = _json_bytes(reference_plan(contract, controls))
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
    except (
        SecurityVerificationPackError,
        base.ProductionDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1603 security verification reference pack checked"
        if args.check
        else "ST-1603 security verification reference pack generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
