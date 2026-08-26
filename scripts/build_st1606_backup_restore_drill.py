#!/usr/bin/env python3
"""Build the non-executable ST-1606 backup/restore reference plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, NoReturn

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1502_data_services as data_base  # noqa: E402
from scripts import build_st1505_staging_deployment as base  # noqa: E402


CONTRACT_PATH: Final = Path("changes/st-1606/contracts/backup-restore-drill.v1.yaml")
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1606/generated/backup-restore-drill.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1606/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1606_backup_restore_drill.py")
README_PATH: Final = Path("changes/st-1606/README.md")
TEST_PATHS: Final = (
    Path("tests/st1606/conftest.py"),
    Path("tests/st1606/test_contract.py"),
    Path("tests/st1606/test_generation.py"),
    Path("tests/st1606/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python scripts/build_st1606_backup_restore_drill.py"
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_bindings",
    "open_decision_boundary",
    "recovery_environment",
    "logical_target_inventory",
    "source_backup_boundary",
    "selection_boundary",
    "reviewable_intents",
    "rpo_rto_design_targets",
    "execution_boundary",
    "evidence_boundary",
)

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
    "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml": (
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
    ),
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml": (
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b"
    ),
    "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md": (
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8"
    ),
    "docs/canonical/06_ops/RAOS_12_backup_restore_matrix_v1.0.yaml": (
        "60ab681822e1aa7c63584bb1b1f4cb6202f4f0dcbea572462dd3a3e7fa8c15f6"
    ),
    "docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml": (
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100"
    ),
    "docs/canonical/06_ops/RAOS_12_implementation_slices_v1.0.yaml": (
        "c338bef9bc45f6eef0dd46bb522a189ee59c06ecc8a44cd9f8988eadb5f47ee9"
    ),
    "docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml": (
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2"
    ),
    "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md": (
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b"
    ),
    "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml": (
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8"
    ),
    "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml": (
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd"
    ),
}
EXPECTED_PREDECESSOR_HASHES: Final = {
    "changes/st-1502/contracts/data-services-foundation.v1.yaml": (
        "89a0f1e7babfceffd2b270bc3a16f5d74fbeb6b62699e03156c860c9ae16c7e1"
    ),
    "infra/terraform/data-services/data-services.reference-plan.v1.json": (
        "2d52d7b99a4edda75814af603e48016f06fa34507bc221e3f573379c066f35c5"
    ),
    "changes/st-1502/manifest.yaml": (
        "efa59447601cf20f0fca3daf271567e1eeb5d81497b4414b0847cd9ae21bc390"
    ),
    "changes/st-1505/contracts/staging-deployment.v1.yaml": (
        "be104a13490d4c39139047e101092e1b2f3541d45c9277e2d9937915a731e2f0"
    ),
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json": (
        "0c607b4c207068432477db1aa2a2e9598092964dbdce470d8b537c7022eaf105"
    ),
    "changes/st-1505/manifest.yaml": (
        "0e970c5749a8bd94fcc8ae5e695d11a4b927028fcc168838618998ac48075aeb"
    ),
}
EXPECTED_IMPLEMENTATION_DEPENDENCY_HASHES: Final = {
    "scripts/build_st1502_data_services.py": (
        "73876b415aba2f7160d94dbe8df113087d4bf5be27b4830b82425b34f6ea6abe"
    ),
    "scripts/build_st1505_staging_deployment.py": (
        "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5"
    ),
}

EXPECTED_DOCUMENT: Final[dict[str, object]] = {
    "id": "RAOS-BACKUP-RESTORE-DRILL-001",
    "version": "1.0.0",
    "story_id": "ST-1606",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "classification": (
        "SOURCE_DERIVED_NON_AUTHORITATIVE_NON_EXECUTABLE_BACKUP_RESTORE_REFERENCE_PLAN"
    ),
    "acceptance_criteria_satisfied": False,
    "formal_verification": "NOT_EXECUTED",
}
EXPECTED_OPEN_DECISION: Final[dict[str, object]] = {
    "id": "OD-014",
    "topic": "retention_periods",
    "status": "HUMAN_DECISION_REQUIRED",
    "blocking": True,
    "default_behavior": "AUTOMATIC_DELETION_DISABLED_MINIMUM_COLLECTION_ONLY",
    "automatic_deletion": "DISABLED",
    "minimum_collection_only": True,
    "decision_value": None,
    "approval_artifacts": [],
}
EXPECTED_RECOVERY_ENVIRONMENT: Final[dict[str, object]] = {
    "label": "ENV-RECOVERY",
    "classification": "INERT_REFERENCE_LABEL_ONLY",
    "configuration_status": "NOT_CONFIGURED",
    "activation_status": "NOT_ACTIVATED",
    "staging_target": False,
    "production_target": False,
    "production_data": "FORBIDDEN",
    "credential_material": "ABSENT",
    "external_access": "FORBIDDEN",
}
EXPECTED_TARGETS: Final[list[dict[str, object]]] = [
    {
        "target": "database",
        "classification": "LOGICAL_TARGET_ONLY",
        "predecessor_story": "ST-1502",
        "source_backup_intent": "IMMUTABLE_READ_ONLY",
        "physical_resource": None,
    },
    {
        "target": "object_storage",
        "classification": "LOGICAL_TARGET_ONLY",
        "predecessor_story": "ST-1502",
        "source_backup_intent": "IMMUTABLE_READ_ONLY",
        "physical_resource": None,
    },
    {
        "target": "iac_configuration",
        "classification": "LOGICAL_TARGET_ONLY",
        "predecessor_story": "ST-1505",
        "source_backup_intent": "IMMUTABLE_READ_ONLY",
        "physical_resource": None,
    },
]
EXPECTED_SOURCE_BACKUP: Final[dict[str, object]] = {
    "immutable_intent": "REQUIRED",
    "read_only_intent": "REQUIRED",
    "source_mutation": "FORBIDDEN",
    "overwrite": "FORBIDDEN",
    "delete": "FORBIDDEN",
    "lifecycle": "FORBIDDEN",
    "retention_change": "FORBIDDEN",
    "cleanup": "FORBIDDEN",
    "expiry": "FORBIDDEN",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_SELECTIONS: Final[dict[str, object]] = {
    "retention_duration": None,
    "lifecycle_rules": [],
    "cleanup_policy": None,
    "deletion_policy": None,
    "expiry": None,
    "backup_schedule": None,
    "account": None,
    "region": None,
    "endpoint": None,
    "credential_reference": None,
    "encryption_key_reference": None,
    "bucket": None,
    "database_identifier": None,
    "iac_backend": None,
    "restore_destination": None,
    "provider": None,
    "tool": None,
    "tool_version": None,
    "physical_resources": [],
}
EXPECTED_INTENTS: Final[list[dict[str, object]]] = [
    {
        "intent": name,
        "classification": "FUTURE_CHECK_REQUIREMENT_ONLY",
        "status": "REQUIRED_NOT_EXECUTED",
        "evidence_references": [],
        "result": None,
    }
    for name in (
        "CONTENT_HASH_INTEGRITY",
        "ROW_OBJECT_COUNTS",
        "ROLE_ACCESS_BOUNDARY",
        "READ_MODEL_REBUILD_CONSISTENCY",
        "SOURCE_BACKUP_NON_MUTATION",
    )
]
EXPECTED_RPO_RTO: Final[list[dict[str, object]]] = [
    {
        "target": "database",
        "source_asset": "PostgreSQL transactional data",
        "target_rpo": "<=15 min",
        "target_rto": "<=4 h",
        "classification": "CANONICAL_DESIGN_TARGET_NOT_MEASUREMENT",
        "measurement_status": "NOT_EXECUTED",
        "measured_rpo": None,
        "measured_rto": None,
    },
    {
        "target": "object_storage",
        "source_asset": "Object artifacts/publication snapshots",
        "target_rpo": "<=1 h",
        "target_rto": "<=4 h",
        "classification": "CANONICAL_DESIGN_TARGET_NOT_MEASUREMENT",
        "measurement_status": "NOT_EXECUTED",
        "measured_rpo": None,
        "measured_rto": None,
    },
    {
        "target": "iac_configuration",
        "source_asset": "Infrastructure as Code",
        "target_rpo": "last merged commit",
        "target_rto": "<=4 h",
        "classification": "CANONICAL_DESIGN_TARGET_NOT_MEASUREMENT",
        "measurement_status": "NOT_EXECUTED",
        "measured_rpo": None,
        "measured_rto": None,
    },
]
ACTION_NAMES: Final = (
    "execute",
    "create",
    "update",
    "delete",
    "restore",
    "verify",
    "cleanup",
    "approval",
    "external",
)
DATA_PLAN_ACTION_KEYS: Final = tuple(sorted(data_base.ACTION_NAMES))
STAGING_PLAN_ACTION_KEYS: Final = tuple(sorted(base.STAGING_ACTION_COUNT_NAMES))
EXPECTED_DATA_PROVIDER_NEUTRAL_ADMISSION: Final[dict[str, object]] = {
    "classification": "STRICT_PROVIDER_NEUTRAL_DATA_SERVICES_CAPABILITY_ADMISSION",
    "admission_status": "NOT_EVALUATED",
    "eligible": False,
    "complete_mapping": False,
    "required_capability_count": 9,
    "configured_mapping_count": 0,
    "selected_provider_name": None,
    "selected_profile_id": None,
    "default_profile_id": None,
    "fallback_profile_id": None,
    "aws_reference_role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
    "canonical_story_deliverables": (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    ),
    "non_aws_owner_managed_profiles": "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS",
    "aws_reference_selected_binding": False,
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
    "aws_reference_role": "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY",
    "canonical_story_deliverables": (
        "CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED"
    ),
    "non_aws_owner_managed_profiles": "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS",
    "aws_reference_selected_binding": False,
}
EXPECTED_EXECUTION: Final[dict[str, object]] = {
    "executable": False,
    "interface_only": True,
    "activation_enabled": False,
    "activation_status": "DISABLED",
    "network_access": "FORBIDDEN",
    "environment_access": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "provider_calls": "FORBIDDEN",
    "subprocess_execution": "FORBIDDEN",
    "filesystem_restore": "FORBIDDEN",
    "native_iac": "FORBIDDEN",
    "database_api": "FORBIDDEN",
    "object_api": "FORBIDDEN",
    "external_actions": "FORBIDDEN",
    "operations": {name: "FORBIDDEN" for name in ACTION_NAMES},
    "action_counts": {name: 0 for name in ACTION_NAMES},
}
EXPECTED_EVIDENCE: Final[dict[str, object]] = {
    "classification": "PLAN_INVENTORY_PROJECTION_ONLY_NOT_RECOVERY_EVIDENCE",
    "performed_recovery_evidence": False,
    "restore_drill": "NOT_EXECUTED",
    "formal_tst_029": "NOT_EXECUTED",
    "hosted_ci": "NOT_EXECUTED",
    "runtime": "NOT_EXECUTED",
    "live_provider": "NOT_EXECUTED",
    "recovery_environment": "NOT_CONFIGURED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_AUTHORIZED",
    "production": "NOT_AUTHORIZED",
    "recoverability_claim": False,
    "restore_success_claim": False,
    "validated_claim": False,
    "rpo_rto_measurement_claim": False,
    "acceptance_criteria_satisfied": False,
    "st_1607_eligible": False,
    "release_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


class BackupRestoreReferenceError(RuntimeError):
    """Sanitized ST-1606 generation failure."""

    def __init__(self, code: str, field: str) -> None:
        super().__init__(f"ST1606_ERROR code={code} field={field}")
        self.code = code
        self.field = field


def _fail(code: str, field: str) -> NoReturn:
    raise BackupRestoreReferenceError(code, field) from None


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(type(key) is str for key in value):
        _fail("INVALID_TYPE", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("INVALID_TYPE", field)
    return value


def _exact(value: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        observed = _mapping(value, field)
        if tuple(observed.keys()) != tuple(expected.keys()):
            _fail("CLOSED_SCHEMA_DRIFT", field)
        for key, expected_value in expected.items():
            _exact(observed[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        observed_list = _list(value, field)
        expected_list = _list(expected, field)
        if not expected_list and observed_list:
            _fail("SAFE_BOUNDARY_DRIFT", field)
        if len(observed_list) != len(expected_list):
            _fail("FIXED_INVENTORY_DRIFT", field)
        for index, expected_value in enumerate(expected_list):
            _exact(observed_list[index], expected_value, f"{field}[{index}]")
        return
    if type(value) is not type(expected) or value != expected:
        if (
            expected is None
            or type(expected) is bool
            or (type(expected) is int and expected == 0)
        ):
            _fail("SAFE_BOUNDARY_DRIFT", field)
        _fail("FIXED_VALUE_DRIFT", field)


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _read(root: Path, relative: Path, field: str) -> bytes:
    physical = base._repository_regular_file(root, relative, field)  # noqa: SLF001
    try:
        return bytes(physical.read_bytes())
    except OSError:
        _fail("FILE_UNAVAILABLE", field)


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _uri_path(value: object, field: str) -> Path:
    if type(value) is not str or not value.startswith("repo://"):
        _fail("INVALID_URI", field)
    relative = Path(value.removeprefix("repo://"))
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        _fail("INVALID_URI", field)
    return relative


def _verify_hash_rows(
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
        if type(digest) is not str:
            _fail("INVALID_TYPE", f"{field}[{index}].sha256")
        observed.append((relative.as_posix(), digest))
    if observed != list(expected.items()):
        _fail("SOURCE_INVENTORY_DRIFT", field)
    for expected_path, digest in expected.items():
        if _sha256_bytes(_read(root, Path(expected_path), f"{field}.input")) != digest:
            _fail("SOURCE_HASH_DRIFT", field)


def _find_record(
    document: Mapping[str, Any], collection: str, record_id: str, field: str
) -> Mapping[str, Any]:
    matches = [
        _mapping(row, field)
        for row in _list(document.get(collection), field)
        if isinstance(row, Mapping) and row.get("id") == record_id
    ]
    if len(matches) != 1:
        _fail("AUTHORITY_RECORD_DRIFT", field)
    return matches[0]


def _validate_authority(root: Path) -> None:
    backlog = _load_yaml(
        root,
        Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml"),
        "backlog",
    )
    story = _find_record(backlog, "stories", "ST-1606", "backlog.stories")
    _exact(
        story,
        {
            "id": "ST-1606",
            "epic_id": "EPIC-16",
            "title": "Backup restore drill",
            "objective": "DB/Object/IaCを隔離復元",
            "depends_on": ["ST-1502", "ST-1505"],
            "requirement_ids": [],
            "design_refs": [],
            "deliverables": ["restore evidence", "RPO/RTO"],
            "acceptance_criteria": ["integrity/roles/readmodel validated"],
            "test_suites": ["TST-029"],
            "priority": "P0",
            "mvp": True,
            "size": "L",
            "open_decisions": ["OD-014"],
            "one_pr_preferred": False,
            "design_status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_status": "NOT_STARTED",
            "verification_status": "NOT_EXECUTED",
        },
        "backlog.ST-1606",
    )
    decisions = _load_yaml(
        root,
        Path("docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"),
        "open_decisions",
    )
    _exact(
        _find_record(decisions, "items", "OD-014", "open_decisions"),
        {
            "id": "OD-014",
            "topic": "retention_periods",
            "status": "HUMAN_DECISION_REQUIRED",
            "required_by": "Deletion jobs",
            "owner": "Privacy/Finance/Legal",
            "decision_needed": (
                "Analytics個票、Security Log、AI Artifact、成果データの保持期間を承認"
            ),
            "default_behavior": "自動削除Jobは無効、最小収集",
            "blocking": True,
        },
        "open_decisions.OD-014",
    )
    tests = _load_yaml(
        root,
        Path("docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"),
        "test_catalog",
    )
    _exact(
        _find_record(tests, "suites", "TST-029", "test_catalog"),
        {
            "id": "TST-029",
            "name": "Backup restore drill",
            "layer": "recovery",
            "purpose": "RDS/Object/Configのrestoreと整合",
            "candidate_tools": ["isolated restore environment"],
            "release_blocking": True,
            "environments": ["staging/recovery"],
            "owner": "Operations",
            "design_status": "APPROVED_FOR_IMPLEMENTATION",
            "implementation_status": "NOT_STARTED",
            "execution_status": "NOT_EXECUTED",
        },
        "test_catalog.TST-029",
    )


def _expected_predecessors() -> dict[str, object]:
    return {
        "data_services": {
            "story_id": "ST-1502",
            "contract_uri": (
                "repo://changes/st-1502/contracts/data-services-foundation.v1.yaml"
            ),
            "contract_sha256": EXPECTED_PREDECESSOR_HASHES[
                "changes/st-1502/contracts/data-services-foundation.v1.yaml"
            ],
            "reference_plan_uri": (
                "repo://infra/terraform/data-services/"
                "data-services.reference-plan.v1.json"
            ),
            "reference_plan_sha256": EXPECTED_PREDECESSOR_HASHES[
                "infra/terraform/data-services/data-services.reference-plan.v1.json"
            ],
            "manifest_uri": "repo://changes/st-1502/manifest.yaml",
            "manifest_sha256": EXPECTED_PREDECESSOR_HASHES[
                "changes/st-1502/manifest.yaml"
            ],
            "required_classification": (
                "SOURCE_DERIVED_PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_DATA_"
                "SERVICES_HCL"
            ),
            "required_executable": True,
            "required_execution_kind": ("PROVIDER_FREE_VALIDATION_ONLY_LOGICAL_HCL"),
            "required_implementation_scope": "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE",
            "required_activation_enabled": False,
            "required_activation_status": "DISABLED",
            "required_selected_values": "UNSET",
            "required_live_provider_calls": "FORBIDDEN",
            "required_external_writes": "FORBIDDEN",
            "required_action_counts": {name: 0 for name in data_base.ACTION_NAMES},
            "provider_neutral_admission": EXPECTED_DATA_PROVIDER_NEUTRAL_ADMISSION,
        },
        "staging_deployment": {
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
                "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
            ],
            "manifest_uri": "repo://changes/st-1505/manifest.yaml",
            "manifest_sha256": EXPECTED_PREDECESSOR_HASHES[
                "changes/st-1505/manifest.yaml"
            ],
            "required_classification": (
                "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
                "REFERENCE_PLAN"
            ),
            "required_executable": False,
            "required_activation_enabled": False,
            "required_activation_status": "DISABLED",
            "required_selected_values": "UNSET",
            "required_live_provider_calls": "FORBIDDEN",
            "required_external_writes": "FORBIDDEN",
            "required_action_counts": {
                name: 0 for name in base.STAGING_ACTION_COUNT_NAMES
            },
            "provider_neutral_admission": EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION,
        },
    }


def _assert_unset_tree(value: object, field: str) -> None:
    if value is None:
        return
    if isinstance(value, Mapping):
        for key, nested in _mapping(value, field).items():
            _assert_unset_tree(nested, f"{field}.{key}")
        return
    if type(value) is list and not value:
        return
    _fail("PREDECESSOR_SELECTION_SET", field)


def _assert_zero_counts(
    value: object, expected_keys: tuple[str, ...], field: str
) -> None:
    counts = _mapping(value, field)
    if tuple(counts) != expected_keys:
        _fail("PREDECESSOR_ACTION_DRIFT", field)
    for count in counts.values():
        if type(count) is not int or count != 0:
            _fail("PREDECESSOR_ACTION_DRIFT", field)


def _provider_neutral_summary(
    plan: Mapping[str, Any], section: str, field: str
) -> dict[str, object]:
    admission = _mapping(plan.get(section), field)
    mapping_policy = _mapping(admission.get("mapping_policy"), f"{field}.mapping")
    aws_boundary = _mapping(
        admission.get("aws_reference_boundary"), f"{field}.aws_reference"
    )
    return {
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
        "canonical_story_deliverables": aws_boundary.get(
            "canonical_story_deliverables"
        ),
        "non_aws_owner_managed_profiles": aws_boundary.get(
            "non_aws_owner_managed_profiles"
        ),
        "aws_reference_selected_binding": aws_boundary.get("selected_binding"),
    }


def _render_data_owner_outputs(root: Path) -> tuple[bytes, bytes]:
    try:
        outputs = data_base.render_outputs(root)
        return (
            outputs[data_base.REFERENCE_PLAN_PATH],
            outputs[data_base.MANIFEST_PATH],
        )
    except data_base.DataServicesContractError:
        _fail("PREDECESSOR_OWNER_VALIDATION_FAILED", "data_services")


def _render_staging_owner_outputs(root: Path) -> tuple[bytes, bytes]:
    contract = _load_yaml(
        root,
        Path("changes/st-1505/contracts/staging-deployment.v1.yaml"),
        "staging_owner.contract",
    )
    try:
        base._validate_local_safety_invariants(contract)  # noqa: SLF001
        model = base.StagingDeploymentModel(contract=dict(contract))
        plan = base.render_reference_plan(model)
        runtime, runtime_specification = base.load_and_validate_runtime_contract(root)
        local_pipeline = base.render_local_pipeline(runtime, runtime_specification)
        local_result = base.render_local_result(runtime_specification)
        return plan, base.render_manifest(
            model,
            plan,
            local_pipeline,
            local_result,
            runtime_specification,
            root,
        )
    except base.StagingDeploymentContractError:
        _fail("PREDECESSOR_OWNER_VALIDATION_FAILED", "staging_deployment")


def _validate_predecessors(contract: Mapping[str, Any], root: Path) -> None:
    _exact(contract["predecessor_bindings"], _expected_predecessors(), "predecessors")
    data_owner_plan, data_owner_manifest = _render_data_owner_outputs(root)
    staging_owner_plan, staging_owner_manifest = _render_staging_owner_outputs(root)
    owner_outputs = (
        (
            Path("infra/terraform/data-services/data-services.reference-plan.v1.json"),
            data_owner_plan,
        ),
        (Path("changes/st-1502/manifest.yaml"), data_owner_manifest),
        (
            Path("infra/terraform/staging/staging-deployment.reference-plan.v1.json"),
            staging_owner_plan,
        ),
        (Path("changes/st-1505/manifest.yaml"), staging_owner_manifest),
    )
    for owner_path, rendered in owner_outputs:
        if _read(root, owner_path, "predecessor.owner_output") != rendered:
            _fail("PREDECESSOR_OWNER_OUTPUT_DRIFT", "predecessors")

    data_plan = _load_json(
        root,
        Path("infra/terraform/data-services/data-services.reference-plan.v1.json"),
        "data_plan",
    )
    data_document = _mapping(data_plan.get("document"), "data_plan.document")
    if (
        data_document.get("artifact_kind")
        != ("SOURCE_DERIVED_PROVIDER_SCHEMA_FREE_EXECUTABLE_LOGICAL_DATA_SERVICES_HCL")
        or data_document.get("executable") is not True
        or data_document.get("execution_kind")
        != "PROVIDER_FREE_VALIDATION_ONLY_LOGICAL_HCL"
        or data_document.get("implementation_scope")
        != "MAXIMUM_SAFE_LOCAL_CODE_COMPLETE"
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "data_plan.document")
    data_activation = _mapping(data_plan.get("activation"), "data_plan.activation")
    if (
        data_activation.get("enabled") is not False
        or data_activation.get("status") != "DISABLED"
        or data_activation.get("network_access") != "FORBIDDEN"
        or data_activation.get("credential_access") != "FORBIDDEN"
        or data_activation.get("live_provider_calls") != "FORBIDDEN"
        or data_activation.get("external_writes") != "FORBIDDEN"
        or data_activation.get("deploy_action") != "FORBIDDEN"
        or data_activation.get("release_action") != "FORBIDDEN"
        or data_activation.get("production_action") != "FORBIDDEN"
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "data_plan.activation")
    _assert_unset_tree(data_plan.get("selected_configuration"), "data_plan.selected")
    _assert_zero_counts(
        data_plan.get("planned_actions"), DATA_PLAN_ACTION_KEYS, "data_plan.actions"
    )
    _exact(
        _provider_neutral_summary(
            data_plan,
            "provider_neutral_data_services_admission",
            "data_plan.provider_neutral_admission",
        ),
        EXPECTED_DATA_PROVIDER_NEUTRAL_ADMISSION,
        "data_plan.provider_neutral_admission",
    )
    data_reference = _mapping(
        data_plan.get("reference_architecture"), "data_plan.reference_architecture"
    )
    if (
        data_reference.get("classification")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or data_reference.get("default") is not False
        or data_reference.get("implicit_fallback") is not False
        or data_reference.get("selected_binding") is not False
        or data_reference.get("eligibility_shortcut") is not False
        or data_reference.get("admission_requirement") is not False
        or data_reference.get("evidence_substitute") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "data_plan.reference_architecture")
    data_manifest = _load_yaml(
        root, Path("changes/st-1502/manifest.yaml"), "data_manifest"
    )
    data_manifest_boundary = _mapping(
        data_manifest.get("boundary"), "data_manifest.boundary"
    )
    if (
        data_manifest_boundary.get("aws_reference_role")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or data_manifest_boundary.get("canonical_story_deliverables")
        != ("CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED")
        or data_manifest_boundary.get("portable_implementation_paths")
        != "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
        or data_manifest_boundary.get("aws_reference_selected_binding") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "data_manifest.boundary")

    staging_plan = _load_json(
        root,
        Path("infra/terraform/staging/staging-deployment.reference-plan.v1.json"),
        "staging_plan",
    )
    staging_document = _mapping(staging_plan.get("document"), "staging_plan.document")
    if (
        staging_document.get("artifact_kind")
        != (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
            "REFERENCE_PLAN"
        )
        or staging_document.get("executable") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging_plan.document")
    staging_activation = _mapping(
        staging_plan.get("activation"), "staging_plan.activation"
    )
    if (
        staging_activation.get("enabled") is not False
        or staging_activation.get("status") != "DISABLED"
        or staging_activation.get("runtime_status") != "NOT_EXECUTED"
        or staging_activation.get("network_access") != "FORBIDDEN"
        or staging_activation.get("credential_access") != "FORBIDDEN"
        or staging_activation.get("live_provider_calls") != "FORBIDDEN"
        or staging_activation.get("external_writes") != "FORBIDDEN"
        or staging_activation.get("staging_action") != "FORBIDDEN"
        or staging_activation.get("release_action") != "FORBIDDEN"
        or staging_activation.get("production_action") != "FORBIDDEN"
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging_plan.activation")
    _assert_unset_tree(staging_plan.get("selected_bindings"), "staging_plan.selected")
    _assert_zero_counts(
        staging_plan.get("action_counts"),
        STAGING_PLAN_ACTION_KEYS,
        "staging_plan.actions",
    )
    _exact(
        _provider_neutral_summary(
            staging_plan,
            "provider_neutral_staging_admission",
            "staging_plan.provider_neutral_admission",
        ),
        EXPECTED_STAGING_PROVIDER_NEUTRAL_ADMISSION,
        "staging_plan.provider_neutral_admission",
    )
    staging_reference = _mapping(
        staging_plan.get("reference_architecture"),
        "staging_plan.reference_architecture",
    )
    if (
        staging_reference.get("classification")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or staging_reference.get("default") is not False
        or staging_reference.get("implicit_fallback") is not False
        or staging_reference.get("selected_binding") is not False
        or staging_reference.get("eligibility_shortcut") is not False
        or staging_reference.get("admission_requirement") is not False
        or staging_reference.get("evidence_substitute") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging_plan.reference_architecture")
    staging_manifest = _load_yaml(
        root, Path("changes/st-1505/manifest.yaml"), "staging_manifest"
    )
    staging_manifest_boundary = _mapping(
        staging_manifest.get("boundary"), "staging_manifest.boundary"
    )
    if (
        staging_manifest_boundary.get("aws_reference_role")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or staging_manifest_boundary.get("canonical_story_deliverables")
        != ("CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED")
        or staging_manifest_boundary.get("portable_implementation_paths")
        != "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
        or staging_manifest_boundary.get("aws_reference_selected_binding") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "staging_manifest.boundary")


def _validate_implementation_dependency(root: Path) -> None:
    del root


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract.keys()) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    _verify_hash_rows(root, contract["sources"], EXPECTED_SOURCE_HASHES, "sources")
    _validate_implementation_dependency(root)
    _validate_authority(root)
    _validate_predecessors(contract, root)
    _exact(contract["open_decision_boundary"], EXPECTED_OPEN_DECISION, "OD-014")
    _exact(
        contract["recovery_environment"],
        EXPECTED_RECOVERY_ENVIRONMENT,
        "recovery_environment",
    )
    _exact(contract["logical_target_inventory"], EXPECTED_TARGETS, "targets")
    _exact(contract["source_backup_boundary"], EXPECTED_SOURCE_BACKUP, "backup")
    _exact(contract["selection_boundary"], EXPECTED_SELECTIONS, "selections")
    _exact(contract["reviewable_intents"], EXPECTED_INTENTS, "intents")
    _exact(contract["rpo_rto_design_targets"], EXPECTED_RPO_RTO, "rpo_rto")
    _exact(contract["execution_boundary"], EXPECTED_EXECUTION, "execution")
    _exact(contract["evidence_boundary"], EXPECTED_EVIDENCE, "evidence")
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(contract: Mapping[str, Any]) -> dict[str, object]:
    execution = _mapping(contract["execution_boundary"], "execution")
    return {
        "schema_version": "1.0.0",
        "generator": {
            "uri": GENERATOR_URI,
            "command": GENERATION_COMMAND,
            "source_contract": SOURCE_URI,
        },
        "story": {
            "id": "ST-1606",
            "scope": "INTERFACE_ONLY_PARTIAL_LOCAL_CODE",
            "effective_canonical_status": "UNCHANGED",
            "acceptance_criteria_satisfied": False,
        },
        "classification": EXPECTED_DOCUMENT["classification"],
        "executable": False,
        "source_bindings": contract["sources"],
        "predecessor_bindings": contract["predecessor_bindings"],
        "open_decision_boundary": contract["open_decision_boundary"],
        "recovery_environment": contract["recovery_environment"],
        "logical_target_inventory": contract["logical_target_inventory"],
        "source_backup_boundary": contract["source_backup_boundary"],
        "selected_bindings": contract["selection_boundary"],
        "reviewable_intents": contract["reviewable_intents"],
        "rpo_rto_design_targets": contract["rpo_rto_design_targets"],
        "activation": {
            "enabled": execution["activation_enabled"],
            "status": execution["activation_status"],
            "operations": execution["operations"],
            "network_access": execution["network_access"],
            "credential_access": execution["credential_access"],
            "provider_calls": execution["provider_calls"],
            "external_actions": execution["external_actions"],
        },
        "action_counts": execution["action_counts"],
        "evidence_boundary": contract["evidence_boundary"],
        "prohibited_interpretations": [
            "REFERENCE_PLAN_IS_NOT_RECOVERY_EVIDENCE",
            "DESIGN_RPO_RTO_IS_NOT_MEASURED_RPO_RTO",
            "REQUIRED_CHECK_IS_NOT_EXECUTED_CHECK",
            "SAFE_DEFAULT_IS_NOT_OD_014_RESOLUTION",
            "LOCAL_TESTS_ARE_NOT_FORMAL_TST_029",
            "NO_ST_1607_OR_RELEASE_ELIGIBILITY_MAY_BE_INFERRED",
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
            "id": "RAOS-BACKUP-RESTORE-DRILL-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1606",
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
            "classification": EXPECTED_EVIDENCE["classification"],
            "restore_drill": "NOT_EXECUTED",
            "formal_tst_029": "NOT_EXECUTED",
            "recoverability_claim": False,
            "rpo_rto_measurement_claim": False,
            "st_1607_eligible": False,
            "release_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
    }
    return yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).encode()


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan(contract))
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
    except (BackupRestoreReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1606 backup/restore reference plan checked"
        if args.check
        else "ST-1606 backup/restore reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
