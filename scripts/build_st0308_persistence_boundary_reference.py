#!/usr/bin/env python3
"""Build the non-executable ST-0308 persistence-boundary reference artifacts."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import stat
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Final, NoReturn


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if __package__ in {None, ""} and str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import build_st1506_production_deployment as secure_io  # noqa: E402


CONTRACT_PATH: Final = Path(
    "changes/st-0308/contracts/persistence-boundary-reference.v1.yaml"
)
REFERENCE_DOCUMENT_PATH: Final = Path(
    "changes/st-0308/PERSISTENCE-BOUNDARY-REFERENCE.md"
)
EXECPLAN_PATH: Final = Path("docs/execplans/ST-0308.md")
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-0308/generated/persistence-boundary.reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-0308/manifest.yaml")
OWNER_OUTPUT_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)

GENERATOR_PATH: Final = Path("scripts/build_st0308_persistence_boundary_reference.py")
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file "
    "python scripts/build_st0308_persistence_boundary_reference.py"
)
SOURCE_ARTIFACT_PATHS: Final = (
    CONTRACT_PATH,
    REFERENCE_DOCUMENT_PATH,
    EXECPLAN_PATH,
    GENERATOR_PATH,
    Path("tests/st0308_reference/conftest.py"),
    Path("tests/st0308_reference/test_contract.py"),
    Path("tests/st0308_reference/test_generation.py"),
    Path("tests/st0308_reference/test_negative_cases.py"),
)

SECURE_HELPER_ROW: Final = (
    "scripts/build_st1506_production_deployment.py",
    42566,
    "ef2c4c887886444041609fc88b6fdef928190e56c4f7882b1f76e3a127ce863f",
)

SOURCE_ROWS: Final = (
    (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md",
        7943,
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_canonical_decisions_v1.0.yaml",
        3955,
        "6330a7e8690edeb30de47ac15a1294e42534bf5d9ef617064ef7c0e0f71c7626",
    ),
    (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml",
        4956,
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md",
        7929,
        "6424dd403cf94b6cd4591792868dfe6435d680ab5b08eefa2fb24a229b4ab01b",
    ),
    (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml",
        24993,
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_acceptance_design_v1.0.md",
        6609,
        "28d60d379c28b72ab0e700f0be1b40fc06b8e4bda531eef1749ce1e4f9ce93ac",
    ),
    (
        "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
        11395,
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
        71458,
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
    (
        "docs/execplans/RAOS-IMPLEMENTATION-FIRST.md",
        10741,
        "9996eb1ff99d84cd1f666663011e53de37ab5c99234707698cad9be04d972d8b",
    ),
    (
        "docs/upstream/key_documents/RAOS_02_system_architecture_v0.1.md",
        150878,
        "00da457014aaf6dd1b726c1a9972a4b371720cb8604d517bccc180ba7a9a93f3",
    ),
    (
        "docs/upstream/key_documents/RAOS_03_data_model_database_design_v0.1.md",
        448029,
        "dce0b457ddacef791b1e134fb5988dee6a4c1f51fa905a3bc7e7d33fb3a0269c",
    ),
    (
        "changes/st-0308/DESIGN-DECISION-REQUEST.md",
        12490,
        "f3d8ec753ce8f60c830d4cf434820ba6b56fc3355e153c2c9421302e691c962b",
    ),
    (
        "changes/st-0308/CANONICAL-RECONCILIATION-v3.md",
        11113,
        "91748530eafc018823b5a6a74cc2ca052569cb3c46f6e90dd1224d720d3fdc08",
    ),
    (
        "changes/st-0308/IMPLEMENTATION-READINESS-v3.md",
        11305,
        "29e90628cc8ed4259b54486ab12abddb606ae414e3a2391c5055dbbf521577f7",
    ),
    (
        "changes/st-0308/contracts/design-handoff-validation.v1.yaml",
        18293,
        "05d0e4a78f302e4286bf3d861d7e31625993ecbc7f718f5f9a4024586c06879c",
    ),
    (
        "scripts/validate_st0308_design_handoff.py",
        104128,
        "e90cf0c39b8b965a521d11403c13e929d381c58ce077050bc36744efcc662dcc",
    ),
)

ST0304_ROWS: Final = (
    (
        "changes/st-0304/contracts/domain-schema.v1.yaml",
        11378,
        "8030f28f59124686c2fb975b507f66e70640b529ff5769666f88202628e19122",
    ),
    (
        "changes/st-0304/contracts/physical/01-domain-physical.sql",
        67717,
        "b2f937ae00d526a886e5e875e095e247702f4bd7831a3164e2eda93423d7fdb8",
    ),
    (
        "changes/st-0304/contracts/physical/02-domain-physical.sql",
        63003,
        "b685751e4e2743ea6c7202e8ce726486ac152e46987bb832e6777e61b987aafc",
    ),
    (
        "changes/st-0304/contracts/physical/03-domain-physical.sql",
        72315,
        "f95ad5a2fd349177b01f97237d0d9a3fb598b2781828e9531a04c3c42b811b45",
    ),
    (
        "changes/st-0304/contracts/physical/04-domain-physical.sql",
        72392,
        "4a3c029980e8c27957fac2291e7b0a8efb81eaf1faa74dee4e757b0836e7ba30",
    ),
    (
        "changes/st-0304/contracts/physical/05-domain-physical.sql",
        72390,
        "c78e946f9be015d461350f347f125a2cf8f01b267647a8685158af207cefc0ec",
    ),
    (
        "changes/st-0304/contracts/physical/06-domain-physical.sql",
        72312,
        "cc520254390d68fdc68d54c01ed6b95e031ea422814e5be924849ec61636904d",
    ),
    (
        "changes/st-0304/contracts/physical/07-domain-physical.sql",
        72283,
        "739cc2ecae7e49702da5e36be6e37eaebaa7a535be4a623c79dee86926212870",
    ),
    (
        "changes/st-0304/contracts/physical/08-domain-physical.sql",
        72327,
        "eafb7b89c6fa08bd74a8c13d89aa19aea3a946e739720a8cff9e6faa3ca2bfc4",
    ),
    (
        "changes/st-0304/contracts/physical/09-domain-physical.sql",
        72161,
        "6cebf09249f027662557038f8367bdc586030197911046be242543cd43502ae5",
    ),
    (
        "changes/st-0304/contracts/physical/10-domain-physical.sql",
        72195,
        "3d806436b7ed91f25e0396e15b914dda7258b743589ec4dc6c3f4272c9fcb38d",
    ),
    (
        "changes/st-0304/contracts/physical/11-domain-physical.sql",
        7630,
        "947e480157a52b0d926461a4d40a7409e92e6e50482c216d394953a462d8cd09",
    ),
    (
        "changes/st-0304/generated/domain-catalog.v1.json",
        967320,
        "41d0c9c4ba94aaf65587687a31bbab1caa05a8fed1d323d99991363013258208",
    ),
    (
        "changes/st-0304/generated/domain-validation.v1.sql",
        18856,
        "7e1ce307a5751fc5d95e4c06652f0e6fb41b8bdc29c583ea9cd0a3d83d1fa3a5",
    ),
    (
        "changes/st-0304/manifest.yaml",
        11667,
        "d09aed90f37c7238f2a3dab4675e6e3b06f108b6c40d4468979541d70577ee51",
    ),
    (
        "migrations/versions/202608030004_domain_schemas.py",
        106632,
        "632fc5146a57e2c7768745e3ed665aba0f91f229afc174c17fca8e9e2d88c407",
    ),
    (
        "scripts/build_st0304_domain_schemas.py",
        79921,
        "17fa798043481c2174abc4b697708f89891dc30079592392390db2002a331f6c",
    ),
    (
        "tests/st0304/conftest.py",
        776,
        "59c99e4d9ee73110414684404ead48a0ebfe7a358eade9677ad23b9f0b3b65a3",
    ),
    (
        "tests/st0304/test_contract.py",
        7609,
        "19785320e51da45e83a4107c3fbe61eebf035bfb4af030e788a913c666169e36",
    ),
    (
        "tests/st0304/test_generation.py",
        20567,
        "c10576b24da67e1cb8e30ea3a29cde20a17e6f7c488cbd75db314cb9cb325980",
    ),
    (
        "tests/st0304/test_postgresql.py",
        32924,
        "7e55e939432e78d13d55f60559fd6a8c0ed71405bf6bd3907b7af5632710d7ac",
    ),
)

ST0105_ROWS: Final = (
    (
        "contracts/raos-v0.4/contract-repository.v0.4.json",
        65443,
        "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef",
    ),
    (
        "changes/st-0105/manifest.json",
        250888,
        "7f1ead0b00d7264f40b29c79a06f35cdad06610231a5c7f7a3e5e1d18054ceb7",
    ),
    (
        "changes/st-0105/README.md",
        4081,
        "15adf4e461592453f78a363ccba411c861f476aeaf58444039c6eaff12ade8de",
    ),
    (
        "scripts/build_st0105_generated_contracts.py",
        80107,
        "b91848efa9a35fa703e3cad08f04336c14c05a0a3fd182e7c97e75a554e372a4",
    ),
    (
        "scripts/codegen_toolchain.sh",
        4633,
        "35bbe2059363745b373546627cf68282233cfe50dbde5cecefdcf360ddd140c0",
    ),
    (
        "tests/st0105/conftest.py",
        2579,
        "4b0fe8dc6d88e787a37f5844d49f2e0e66ccc3d11f355f683b509a17f337ed1d",
    ),
    (
        "tests/st0105/test_codegen_cli.py",
        6948,
        "cb2a77ffb08c6ab24e570327614d99672370ca691a6c551baeef696ccbf86403",
    ),
    (
        "tests/st0105/test_commands_and_docs.py",
        6265,
        "dba5e94ad4a3e25198679e53eaffd27cfb46a4cbd2829348b8d4be644e40332c",
    ),
    (
        "tests/st0105/test_determinism_and_safety.py",
        28072,
        "00d10142e631e222c01c3d0f6667d07a4c010e067bdd36e71196515b819c25cf",
    ),
    (
        "tests/st0105/test_generated_runtime.py",
        4808,
        "766de70bda43fd5afe8bd8e8ec656289e7d79c5ba19ca3c3a09d1990642a33c2",
    ),
    (
        "tests/st0105/test_manifest_contract.py",
        7170,
        "491b9cbd2a9435c0ee442482514c4eaf4b1d4305c5e6d834abe4a7009fc4348b",
    ),
)

TOP_LEVEL_KEYS: Final = (
    "document",
    "sources",
    "predecessor_bindings",
    "scope",
    "local_design_gaps",
    "selected_design",
    "implementation_inventory",
    "safe_defaults",
    "activation",
    "action_boundary",
    "evidence_boundary",
    "downstream_boundary",
)
REFERENCE_PLAN_KEYS: Final = (
    "document",
    "source_bindings",
    "predecessor_bindings",
    "scope",
    "local_design_gap_registry",
    "selected_design",
    "implementation_inventory",
    "safe_defaults",
    "activation",
    "action_boundary",
    "evidence_boundary",
    "downstream_boundary",
    "prohibited_interpretations",
)
PROHIBITED_INTERPRETATIONS: Final = (
    "LOCAL_DESIGN_GAPS_ARE_NOT_CANONICAL_OPEN_DECISIONS",
    "NULL_SELECTIONS_DO_NOT_RESOLVE_D1_THROUGH_D6",
    "REFERENCE_PLAN_IS_NOT_A_DESIGN_HANDOFF_OR_IMPLEMENTATION_AUTHORITY",
    "PREDECESSOR_HASH_BINDING_DOES_NOT_SELECT_PERSISTENCE_DESIGN",
    "ZERO_RUNTIME_ARTIFACTS_DO_NOT_SATISFY_ST0308_DELIVERABLES",
    "LOCAL_CHECKS_ARE_NOT_FORMAL_TST005_OR_TST008",
    "NO_REPOSITORY_UOW_FAKE_MIGRATION_ROLE_GRANT_OR_DATABASE_BEHAVIOR_MAY_BE_INFERRED",
)
ST0105_TOP_LEVEL_KEYS: Final = (
    "asyncapi_registry",
    "document",
    "http_clients",
    "http_operations",
    "intermediates",
    "outputs",
    "schema_bindings",
    "source",
    "tools",
)
ST0105_OUTPUT_ROOTS: Final = (
    "python/raos/generated",
    "packages/web-contracts/src/generated",
)

EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0308-PERSISTENCE-BOUNDARY-REFERENCE-001",
    "version": "1.0.0",
    "story": "ST-0308",
    "status": "MAXIMUM_SAFE_REFERENCE_ONLY_LOCAL_SLICE",
    "classification": (
        "SOURCE_BOUND_NON_AUTHORITATIVE_NON_EXECUTABLE_"
        "PERSISTENCE_BOUNDARY_REFERENCE_PLAN"
    ),
    "authority": "NON_AUTHORITATIVE",
    "executable": False,
    "implementation_dependencies": [
        {
            "uri": f"repo://{SECURE_HELPER_ROW[0]}",
            "bytes": SECURE_HELPER_ROW[1],
            "sha256": SECURE_HELPER_ROW[2],
            "use": "DESCRIPTOR_SAFE_YAML_PATH_AND_ATOMIC_OUTPUT_ONLY",
        }
    ],
}
EXPECTED_SCOPE: Final = {
    "story_id": "ST-0308",
    "title": "Persistence ports and repositories",
    "dependencies": ["ST-0304", "ST-0105"],
    "deliverables": ["repositories", "transaction boundary"],
    "acceptance_criteria": ["cross-module write rules"],
    "required_suites": ["TST-005", "TST-008"],
    "open_decisions": [],
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_LOCAL_GAPS: Final = {
    "count": 6,
    "selected_count": 0,
    "unresolved_count": 6,
    "canonical_open_decision_count": 0,
    "canonical_open_decisions": [],
    "gaps": [
        {
            "id": f"ST0308-D{index}",
            "source_kind": "LOCAL_NONCANONICAL_DESIGN_GAP",
            "resolution_state": "UNRESOLVED",
            "selected_value": None,
            "resolution_payload": None,
            "runtime_implementation": "BLOCKED",
        }
        for index in range(1, 7)
    ],
}
EXPECTED_SELECTED_DESIGN: Final = {
    "repository_and_aggregate_inventory": None,
    "inward_port_contracts": None,
    "sqlalchemy_and_domain_mapping": None,
    "unit_of_work_and_session_lifecycle": None,
    "cross_module_writes_outbox_audit_and_idempotency": None,
    "connection_factory_and_workload_identity": None,
    "approved_handoff_uri": None,
    "approved_handoff_sha256": None,
    "conflict_free_canonical_reconciliation": None,
    "repository_owner_approval": None,
}
INVENTORY_NAMES: Final = (
    "repository_ports",
    "repository_signatures",
    "repository_adapters",
    "unit_of_work_ports",
    "unit_of_work_implementations",
    "fake_repositories",
    "domain_models",
    "persistence_mappers",
    "runtime_factories",
    "migrations",
    "schema_changes",
    "role_changes",
    "grant_changes",
    "database_behaviors",
    "executable_artifacts",
)
EXPECTED_IMPLEMENTATION_INVENTORY: Final = {name: 0 for name in INVENTORY_NAMES}
EXPECTED_SAFE_DEFAULTS: Final = {
    "design_selections": "FORBIDDEN",
    "unresolved_defaults_are_resolution": False,
    "source_bindings_are_authority": False,
    "repository_uow_fake_and_database_code": "FORBIDDEN",
    "production": "DISABLED",
}
EXPECTED_ACTIVATION: Final = {
    "enabled": False,
    "status": "BLOCKED_PENDING_APPROVED_DESIGN_HANDOFF",
    "authority": "NOT_GRANTED",
    "approved_handoff_uri": None,
    "approved_handoff_sha256": None,
    "conflict_free_canonical_reconciliation": None,
    "repository_owner_approval": None,
    "runtime_eligible": False,
}
ACTION_NAMES: Final = (
    "repository_runtime",
    "unit_of_work_runtime",
    "fake_runtime",
    "database_connection",
    "database_read",
    "database_write",
    "transaction",
    "migration",
    "schema_change",
    "role_change",
    "grant_change",
    "external",
    "staging",
    "release",
    "production",
)
EXPECTED_ACTION_BOUNDARY: Final = {
    "counts": {name: 0 for name in ACTION_NAMES},
    "database_access": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "subprocess_execution": "FORBIDDEN",
    "external_actions": "FORBIDDEN",
    "staging_actions": "FORBIDDEN",
    "release_actions": "FORBIDDEN",
    "production_actions": "FORBIDDEN",
}
EXPECTED_EVIDENCE_BOUNDARY: Final = {
    "formal_tst_005": "NOT_EXECUTED",
    "formal_tst_008": "NOT_EXECUTED",
    "postgresql_runtime": "NOT_EXECUTED",
    "security_verification": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "human_approval": "NOT_OBTAINED",
    "canonical_reconciliation": "NOT_OBTAINED",
    "effective_canonical_status": "UNCHANGED",
    "acceptance_criteria_satisfied": False,
    "local_evidence": "REFERENCE_CHECKS_ONLY",
}
EXPECTED_DOWNSTREAM_BOUNDARY: Final = {
    "st0308_runtime_readiness": False,
    "st0308_acceptance_readiness": False,
    "dependent_story_readiness": False,
    "staging_readiness": False,
    "release_readiness": False,
    "production_readiness": False,
}
EXPECTED_ST0105_FACTS: Final = {
    "top_level_keys": list(ST0105_TOP_LEVEL_KEYS),
    "source_artifacts": 306,
    "schema_bindings": 224,
    "openapi_documents": 3,
    "asyncapi_documents": 1,
    "clients": 3,
    "http_operations": 185,
    "asyncapi_channels": 22,
    "asyncapi_operations": 37,
    "asyncapi_messages": 105,
    "outputs": 354,
    "output_roots": list(ST0105_OUTPUT_ROOTS),
    "current_tree_all_outputs_present": True,
    "current_tree_all_output_hashes_match": True,
    "predecessor_owner_check_claimed": False,
}

MAX_BOUND_FILE_BYTES: Final = 2 * 1024 * 1024
SHA256_PATTERN: Final = re.compile(r"^[0-9a-f]{64}$")


class PersistenceReferenceError(RuntimeError):
    """A fixed-code validation failure with no rejected input value."""

    def __init__(self, code: str, field: str) -> None:
        self.code = code
        self.field = field
        super().__init__(f"{code} field={field}")


@dataclass(frozen=True, slots=True)
class PersistenceReferenceModel:
    """A fully validated, closed ST-0308 reference contract."""

    contract: Mapping[str, Any]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fail(code: str, field: str) -> NoReturn:
    raise PersistenceReferenceError(code, field)


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(
        type(key) is str for key in value.keys()
    ):
        _fail("TYPE_MISMATCH", field)
    return value


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


def _strict_match(actual: object, expected: object, field: str) -> None:
    if isinstance(expected, Mapping):
        actual_mapping = _mapping(actual, field)
        expected_mapping = _mapping(expected, field)
        if tuple(actual_mapping) != tuple(expected_mapping):
            _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", field)
        for key, expected_value in expected_mapping.items():
            _strict_match(actual_mapping[key], expected_value, f"{field}.{key}")
        return
    if type(expected) is list:
        actual_list = _list(actual, field)
        expected_list = _list(expected, field)
        if len(actual_list) != len(expected_list):
            _fail("FIXED_VALUE_VIOLATION", field)
        for index, expected_value in enumerate(expected_list):
            _strict_match(actual_list[index], expected_value, f"{field}.item")
        return
    if expected is None:
        if actual is not None:
            _fail("SELECTION_MUST_REMAIN_NULL", field)
        return
    if type(actual) is not type(expected):
        _fail("TYPE_MISMATCH", field)
    if actual != expected:
        if type(expected) is bool or (type(expected) is int and expected == 0):
            _fail("SAFE_BOUNDARY_VIOLATION", field)
        _fail("FIXED_VALUE_VIOLATION", field)


def _safe_repository_file(root: Path, relative: Path, field: str) -> Path:
    try:
        return secure_io._repository_regular_file(root, relative, field)
    except secure_io.ProductionDeploymentContractError:
        _fail("BOUND_FILE_UNAVAILABLE", field)


def _read_bound_file(root: Path, relative: Path, field: str) -> bytes:
    path = _safe_repository_file(root, relative, field)
    try:
        content = path.read_bytes()
    except OSError:
        _fail("BOUND_FILE_UNAVAILABLE", field)
    if len(content) > MAX_BOUND_FILE_BYTES:
        _fail("BOUND_FILE_SIZE_LIMIT", field)
    return content


def _repo_uri_path(value: object, field: str) -> Path:
    try:
        return secure_io._repo_relative_uri(value)
    except secure_io.ProductionDeploymentContractError:
        _fail("REPOSITORY_URI_INVALID", field)


def _validate_bound_rows(
    raw_rows: object,
    expected_rows: Sequence[tuple[str, int, str]],
    root: Path,
    field: str,
) -> None:
    rows = _list(raw_rows, field)
    if len(rows) != len(expected_rows):
        _fail("BOUND_ROW_INVENTORY_DRIFT", field)
    for raw_row, (expected_path, expected_bytes, expected_sha256) in zip(
        rows, expected_rows, strict=True
    ):
        row = _mapping(raw_row, f"{field}.item")
        if tuple(row) != ("uri", "bytes", "sha256"):
            _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", f"{field}.item")
        relative = _repo_uri_path(row["uri"], f"{field}.item.uri")
        _strict_match(relative.as_posix(), expected_path, f"{field}.item.uri")
        _strict_match(row["bytes"], expected_bytes, f"{field}.item.bytes")
        _strict_match(row["sha256"], expected_sha256, f"{field}.item.sha256")
        content = _read_bound_file(root, relative, f"{field}.bound_file")
        if len(content) != expected_bytes:
            _fail("BOUND_FILE_BYTES_MISMATCH", f"{field}.bound_file")
        if sha256_bytes(content) != expected_sha256:
            _fail("BOUND_FILE_DIGEST_MISMATCH", f"{field}.bound_file")


def _load_contract(root: Path) -> Mapping[str, Any]:
    contract_path = _safe_repository_file(root, CONTRACT_PATH, "contract")
    try:
        return _mapping(secure_io.load_yaml(contract_path), "contract")
    except secure_io.ProductionDeploymentContractError:
        _fail("CONTRACT_YAML_INVALID", "contract")


def _load_st0105_manifest(root: Path) -> Mapping[str, Any]:
    manifest_path = _safe_repository_file(
        root, Path("changes/st-0105/manifest.json"), "st0105_manifest"
    )
    try:
        return _mapping(secure_io.load_json(manifest_path), "st0105_manifest")
    except secure_io.ProductionDeploymentContractError:
        _fail("ST0105_MANIFEST_INVALID", "st0105_manifest")


def _validate_st0105_projection(raw_facts: object, root: Path) -> None:
    _strict_match(raw_facts, EXPECTED_ST0105_FACTS, "st0105.manifest_facts")
    manifest = _load_st0105_manifest(root)
    if tuple(manifest) != ST0105_TOP_LEVEL_KEYS:
        _fail("ST0105_TOP_LEVEL_KEYS_DRIFT", "st0105_manifest")

    source = _mapping(manifest.get("source"), "st0105_manifest.source")
    registry = _mapping(
        manifest.get("asyncapi_registry"), "st0105_manifest.asyncapi_registry"
    )
    outputs = _mapping(manifest.get("outputs"), "st0105_manifest.outputs")
    observed = {
        "source_artifacts": source.get("artifact_count"),
        "schema_bindings": len(
            _list(manifest.get("schema_bindings"), "st0105_manifest.schema_bindings")
        ),
        "openapi_documents": source.get("openapi_count"),
        "asyncapi_documents": source.get("asyncapi_count"),
        "clients": len(
            _list(manifest.get("http_clients"), "st0105_manifest.http_clients")
        ),
        "http_operations": len(
            _list(
                manifest.get("http_operations"),
                "st0105_manifest.http_operations",
            )
        ),
        "asyncapi_channels": registry.get("channel_count"),
        "asyncapi_operations": registry.get("operation_count"),
        "asyncapi_messages": registry.get("message_count"),
        "outputs": outputs.get("artifact_count"),
    }
    for name, expected in EXPECTED_ST0105_FACTS.items():
        if name in observed:
            _strict_match(observed[name], expected, f"st0105_manifest.facts.{name}")

    _strict_match(
        len(_list(registry.get("channels"), "st0105_manifest.channels")),
        22,
        "st0105_manifest.channels",
    )
    _strict_match(
        len(_list(registry.get("operations"), "st0105_manifest.operations")),
        37,
        "st0105_manifest.operations",
    )
    _strict_match(
        len(_list(registry.get("messages"), "st0105_manifest.messages")),
        105,
        "st0105_manifest.messages",
    )
    roots = _list(outputs.get("roots"), "st0105_manifest.outputs.roots")
    _strict_match(roots, list(ST0105_OUTPUT_ROOTS), "st0105_manifest.outputs.roots")

    artifacts = _list(outputs.get("artifacts"), "st0105_manifest.outputs.artifacts")
    _strict_match(len(artifacts), 354, "st0105_manifest.outputs.artifact_count")
    seen: set[str] = set()
    for raw_artifact in artifacts:
        artifact = _mapping(raw_artifact, "st0105_manifest.outputs.artifact")
        if tuple(artifact) != ("bytes", "path", "sha256"):
            _fail(
                "ORDERED_CLOSED_SCHEMA_VIOLATION",
                "st0105_manifest.outputs.artifact",
            )
        expected_bytes = artifact["bytes"]
        relative_text = artifact["path"]
        expected_sha256 = artifact["sha256"]
        if type(expected_bytes) is not int or expected_bytes < 0:
            _fail("TYPE_MISMATCH", "st0105_manifest.outputs.artifact.bytes")
        if type(relative_text) is not str or "\\" in relative_text:
            _fail("REPOSITORY_URI_INVALID", "st0105_manifest.outputs.artifact.path")
        pure = PurePosixPath(relative_text)
        if (
            pure.is_absolute()
            or not pure.parts
            or any(part in {"", ".", ".."} for part in pure.parts)
        ):
            _fail("REPOSITORY_URI_INVALID", "st0105_manifest.outputs.artifact.path")
        if relative_text in seen:
            _fail("ST0105_OUTPUT_DUPLICATE", "st0105_manifest.outputs.artifact")
        seen.add(relative_text)
        if not any(
            relative_text == output_root or relative_text.startswith(f"{output_root}/")
            for output_root in ST0105_OUTPUT_ROOTS
        ):
            _fail("ST0105_OUTPUT_ROOT_ESCAPE", "st0105_manifest.outputs.artifact")
        if (
            type(expected_sha256) is not str
            or SHA256_PATTERN.fullmatch(expected_sha256) is None
        ):
            _fail("DIGEST_INVALID", "st0105_manifest.outputs.artifact.sha256")
        content = _read_bound_file(
            root,
            Path(*pure.parts),
            "st0105_manifest.outputs.artifact.file",
        )
        _strict_match(
            len(content), expected_bytes, "st0105_manifest.outputs.artifact.bytes"
        )
        _strict_match(
            sha256_bytes(content),
            expected_sha256,
            "st0105_manifest.outputs.artifact.sha256",
        )


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> PersistenceReferenceModel:
    try:
        physical_root = secure_io._real_repository_root(root)
    except secure_io.ProductionDeploymentContractError:
        _fail("UNSAFE_REPOSITORY_ROOT", "repository")
    if tuple(contract) != TOP_LEVEL_KEYS:
        _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", "contract")

    _strict_match(contract["document"], EXPECTED_DOCUMENT, "document")
    helper_content = _read_bound_file(
        physical_root, Path(SECURE_HELPER_ROW[0]), "implementation_dependencies"
    )
    _strict_match(
        len(helper_content), SECURE_HELPER_ROW[1], "implementation_dependencies.bytes"
    )
    _strict_match(
        sha256_bytes(helper_content),
        SECURE_HELPER_ROW[2],
        "implementation_dependencies.sha256",
    )

    _validate_bound_rows(contract["sources"], SOURCE_ROWS, physical_root, "sources")

    predecessors = _mapping(contract["predecessor_bindings"], "predecessors")
    if tuple(predecessors) != ("ST-0304", "ST-0105"):
        _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", "predecessors")
    st0304 = _mapping(predecessors["ST-0304"], "predecessors.ST-0304")
    if tuple(st0304) != ("classification", "semantic_projection", "rows"):
        _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", "predecessors.ST-0304")
    _strict_match(
        st0304["classification"], "OPAQUE_CONTEXT_ONLY", "predecessors.ST-0304"
    )
    _strict_match(st0304["semantic_projection"], "FORBIDDEN", "predecessors.ST-0304")
    _validate_bound_rows(
        st0304["rows"], ST0304_ROWS, physical_root, "predecessors.ST-0304.rows"
    )

    st0105 = _mapping(predecessors["ST-0105"], "predecessors.ST-0105")
    if tuple(st0105) != (
        "classification",
        "semantic_projection",
        "rows",
        "manifest_facts",
    ):
        _fail("ORDERED_CLOSED_SCHEMA_VIOLATION", "predecessors.ST-0105")
    _strict_match(
        st0105["classification"],
        "API_BINDINGS_ONLY_NOT_PERSISTENCE_DESIGN",
        "predecessors.ST-0105",
    )
    _strict_match(
        st0105["semantic_projection"],
        "MANIFEST_FACTS_ONLY",
        "predecessors.ST-0105",
    )
    _validate_bound_rows(
        st0105["rows"], ST0105_ROWS, physical_root, "predecessors.ST-0105.rows"
    )
    _validate_st0105_projection(st0105["manifest_facts"], physical_root)

    _strict_match(contract["scope"], EXPECTED_SCOPE, "scope")
    _strict_match(
        contract["local_design_gaps"], EXPECTED_LOCAL_GAPS, "local_design_gaps"
    )
    _strict_match(
        contract["selected_design"], EXPECTED_SELECTED_DESIGN, "selected_design"
    )
    _strict_match(
        contract["implementation_inventory"],
        EXPECTED_IMPLEMENTATION_INVENTORY,
        "implementation_inventory",
    )
    _strict_match(contract["safe_defaults"], EXPECTED_SAFE_DEFAULTS, "safe_defaults")
    _strict_match(contract["activation"], EXPECTED_ACTIVATION, "activation")
    _strict_match(
        contract["action_boundary"], EXPECTED_ACTION_BOUNDARY, "action_boundary"
    )
    _strict_match(
        contract["evidence_boundary"],
        EXPECTED_EVIDENCE_BOUNDARY,
        "evidence_boundary",
    )
    _strict_match(
        contract["downstream_boundary"],
        EXPECTED_DOWNSTREAM_BOUNDARY,
        "downstream_boundary",
    )
    return PersistenceReferenceModel(contract=contract)


def load_and_validate_contract(root: Path = REPO_ROOT) -> PersistenceReferenceModel:
    return validate_contract(_load_contract(root), root)


def reference_plan_document(
    model: PersistenceReferenceModel,
) -> dict[str, object]:
    contract = model.contract
    document: dict[str, object] = {
        "document": copy.deepcopy(contract["document"]),
        "source_bindings": copy.deepcopy(contract["sources"]),
        "predecessor_bindings": copy.deepcopy(contract["predecessor_bindings"]),
        "scope": copy.deepcopy(contract["scope"]),
        "local_design_gap_registry": copy.deepcopy(contract["local_design_gaps"]),
        "selected_design": copy.deepcopy(contract["selected_design"]),
        "implementation_inventory": copy.deepcopy(contract["implementation_inventory"]),
        "safe_defaults": copy.deepcopy(contract["safe_defaults"]),
        "activation": copy.deepcopy(contract["activation"]),
        "action_boundary": copy.deepcopy(contract["action_boundary"]),
        "evidence_boundary": copy.deepcopy(contract["evidence_boundary"]),
        "downstream_boundary": copy.deepcopy(contract["downstream_boundary"]),
        "prohibited_interpretations": list(PROHIBITED_INTERPRETATIONS),
    }
    if tuple(document) != REFERENCE_PLAN_KEYS:
        _fail("REFERENCE_PLAN_SCHEMA_DRIFT", "reference_plan")
    return document


def render_reference_plan(model: PersistenceReferenceModel) -> bytes:
    return (
        json.dumps(
            reference_plan_document(model),
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _artifact_row(root: Path, relative: Path, field: str) -> dict[str, object]:
    content = _read_bound_file(root, relative, field)
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": sha256_bytes(content),
    }


def render_manifest(reference_plan: bytes, root: Path = REPO_ROOT) -> bytes:
    source_rows = [
        _artifact_row(root, relative, "manifest.source_artifact")
        for relative in SOURCE_ARTIFACT_PATHS
    ]
    generated_rows = [
        {
            "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
            "bytes": len(reference_plan),
            "sha256": sha256_bytes(reference_plan),
        }
    ]
    document = {
        "document": {
            "id": "RAOS-ST0308-ARTIFACT-MANIFEST-001",
            "version": "1.0.0",
            "story": "ST-0308",
            "source_contract_uri": f"repo://{CONTRACT_PATH.as_posix()}",
            "generated_by": GENERATOR_PATH.as_posix(),
            "generation_command": GENERATION_COMMAND,
            "source_artifact_count": 8,
            "generated_artifact_count": 1,
            "manifest_self_excluded": True,
        },
        "source_artifacts": source_rows,
        "generated_artifacts": generated_rows,
        "boundary": {
            "classification": (
                "SOURCE_BOUND_NON_AUTHORITATIVE_NON_EXECUTABLE_"
                "PERSISTENCE_BOUNDARY_REFERENCE_PLAN"
            ),
            "implementation_authority": "NOT_GRANTED",
            "runtime_eligible": False,
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_008": "NOT_EXECUTED",
        },
    }
    rendered: str = secure_io.yaml.dump(  # type: ignore[attr-defined]
        document,
        Dumper=secure_io.NoAliasDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return rendered.encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    model = load_and_validate_contract(root)
    reference_plan = render_reference_plan(model)
    return {
        REFERENCE_PLAN_PATH: reference_plan,
        MANIFEST_PATH: render_manifest(reference_plan, root),
    }


def _owner_output(root: Path, relative: Path) -> Path:
    try:
        path = secure_io._output_file(root, relative)
    except secure_io.ProductionDeploymentContractError:
        _fail("OWNER_OUTPUT_UNSAFE", "output")
    try:
        metadata = path.lstat()
    except OSError:
        _fail("OWNER_OUTPUT_UNAVAILABLE", "output")
    if stat.S_IMODE(metadata.st_mode) != 0o644:
        _fail("OWNER_OUTPUT_MODE_INVALID", "output")
    return path


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if tuple(expected) != OWNER_OUTPUT_PATHS:
        _fail("OWNER_OUTPUT_INVENTORY_DRIFT", "output")
    for relative in OWNER_OUTPUT_PATHS:
        path = _owner_output(root, relative)
        try:
            actual = path.read_bytes()
        except OSError:
            _fail("OWNER_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("OWNER_OUTPUT_DRIFT", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    outputs = render_outputs(root)
    if check:
        check_outputs(root, outputs)
        return
    for relative in OWNER_OUTPUT_PATHS:
        try:
            secure_io._atomic_write(root, relative, outputs[relative])
        except secure_io.ProductionDeploymentContractError:
            _fail("OWNER_OUTPUT_WRITE_FAILED", "output")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the ST-0308 persistence-boundary reference artifacts.",
        allow_abbrev=False,
        add_help=False,
    )
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments not in ([], ["--check"]):
        parser.error("unsupported argument")
    return argparse.Namespace(check=arguments == ["--check"])


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(REPO_ROOT, check=bool(args.check))
    except PersistenceReferenceError as exc:
        print(f"ERROR code={exc.code} field={exc.field}", file=sys.stderr)
        return 1
    except Exception:
        print("ERROR code=UNEXPECTED_FAILURE field=builder", file=sys.stderr)
        return 1
    if args.check:
        print("ST-0308 persistence-boundary reference check passed")
    else:
        print("ST-0308 persistence-boundary reference artifacts generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
