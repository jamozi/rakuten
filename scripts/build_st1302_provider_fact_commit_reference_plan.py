#!/usr/bin/env python3
"""Build the non-executable ST-1302 provider-fact commit reference plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import stat
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
    "changes/st-1302/contracts/provider-fact-commit-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1302/generated/provider-fact-commit-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1302/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1302_provider_fact_commit_reference_plan.py"
)
README_PATH: Final = Path("changes/st-1302/README.md")
TEST_PATHS: Final = (
    Path("tests/st1302/conftest.py"),
    Path("tests/st1302/test_contract.py"),
    Path("tests/st1302/test_generation.py"),
    Path("tests/st1302/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "9e8a89c0faac140af6a0bdee7eceb68a90ccd885f3d9ea318372187560528aff"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1302_provider_fact_commit_reference_plan.py"
)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
STORY_SHA256: Final = "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d"
INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
INTEGRATION_SHA256: Final = (
    "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a"
)
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
OPEN_DECISIONS_SHA256: Final = (
    "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e"
)

PREDECESSOR_COMMIT: Final = "20d1a2649f5b4635d49b970e76d17bd3ef93a1dc"
PREDECESSOR_ARTIFACTS: Final = (
    (
        Path("changes/st-1301/README.md"),
        "49ec7923d508c31ab5e29c1a53d59258e3c832859df142407beac72de284b7e0",
    ),
    (
        Path("python/raos/domain/finance/revenue_import.py"),
        "9698846ff18dfa7fb81b338f126fe70e28f96151ed8283eac8cb5da7132265eb",
    ),
    (
        Path("python/raos/ports/revenue_import.py"),
        "d3c2adb05f3db3810a2d7bc7462dcb87b62fd45e308777d6575824733c940e48",
    ),
    (
        Path("python/raos/application/finance/revenue_import.py"),
        "4ad42b6f47668c3e9a602efdd24e12ed41ccfa926f1ca4f30d27cc241e750421",
    ),
    (
        Path("python/raos/adapters/recorded_revenue_import.py"),
        "9d5f2c0d9ee0f8a27d6468613d2d0487b24e2996cc1c5396b5343306da852889",
    ),
    (
        Path("tests/st1301/conftest.py"),
        "0171298b72be27418efc7d0eac35551d12934b80bd82a3bf73f554c7040d4244",
    ),
    (
        Path("tests/st1301/test_contract.py"),
        "e496aa856a7bfaedb589ec62c7196ecb8d1595dcc992a525453c14bf718fb902",
    ),
    (
        Path("tests/st1301/test_revenue_import.py"),
        "99b29264593f6fc92fea19540a6028830df854e3719542c3345b0455ab78133c",
    ),
    (
        Path("tests/st1301/test_negative_cases.py"),
        "a0fac1fea74bee63640d4d702223c1bd9f3933887f7ee887c3ef7cae7da51b07",
    ),
)

ST0308_CONTRACT_PATH: Final = Path(
    "changes/st-0308/contracts/persistence-boundary-reference.v1.yaml"
)
ST0308_PLAN_PATH: Final = Path(
    "changes/st-0308/generated/persistence-boundary.reference-plan.v1.json"
)
ST0308_MANIFEST_PATH: Final = Path("changes/st-0308/manifest.yaml")
ST0305_CONTRACT_PATH: Final = Path(
    "changes/st-0305/contracts/publication-analytics-finance.v1.yaml"
)
ST0305_CATALOG_PATH: Final = Path(
    "changes/st-0305/generated/publication-analytics-finance-catalog.v1.json"
)
CANONICAL_ROW_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/imports/revenue-canonical-row.schema.json"
)
COMMIT_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/finance-commit-revenue-import-v1.schema.json"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
STATE_TRANSITION_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/state-transition-catalog.v0.4.yaml"
)
ADMIN_OPENAPI_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml"
)
RBAC_MATRIX_PATH: Final = Path(
    "docs/canonical/04_security/RAOS_10_role_permission_matrix_v1.0.yaml"
)

AUTHORITY_ARTIFACTS: Final = (
    (STORY_PATH, STORY_SHA256),
    (INTEGRATION_PATH, INTEGRATION_SHA256),
    (OPEN_DECISIONS_PATH, OPEN_DECISIONS_SHA256),
)
REFERENCE_INPUT_ARTIFACTS: Final = (
    (
        ST0308_CONTRACT_PATH,
        "93d7a84ccd7c9f195119eca63762239c5ec903aae1f7bb4d7d81b73bbf838035",
    ),
    (
        ST0308_PLAN_PATH,
        "e5caada483b12b6f7c9ea2fe0bd86c493b47b24a6d9bb5a11293eed8597f13b6",
    ),
    (
        ST0308_MANIFEST_PATH,
        "8c05065f29a2901f71fd59970e97cb0d69151a0c987b7ac4b42369f25faabad2",
    ),
    (
        ST0305_CONTRACT_PATH,
        "2947fe100633a2611b9287c6530856b9679365bb10d4af4728a5148ed970377f",
    ),
    (
        ST0305_CATALOG_PATH,
        "0757434a72b22ae54dadd13edbd3d7995eaf0776a18ba69be5064f2db8e75e61",
    ),
    (
        CANONICAL_ROW_SCHEMA_PATH,
        "02bc3d854a7420a74a8b302342a9ad0e23cfe4529565716a185c333b43ebbff8",
    ),
    (
        COMMIT_JOB_SCHEMA_PATH,
        "9e0b860aacd151888e67e76a64ad94e8c3dd33072de42f570b8b233e1a9dce0d",
    ),
    (
        JOB_CATALOG_PATH,
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        STATE_TRANSITION_PATH,
        "203eb10d9b6fc6ba4fb0e9f0491f713c313a6a5627dcaf60b7ce53665ecec8a5",
    ),
    (
        ADMIN_OPENAPI_PATH,
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
    ),
    (
        RBAC_MATRIX_PATH,
        "dfd67960ca8a004bbe6f3249ca9fa64ab1b24e94a57a2e88fc282267adc8b984",
    ),
)
REQUIRED_INPUT_ARTIFACTS: Final = (
    *AUTHORITY_ARTIFACTS,
    *PREDECESSOR_ARTIFACTS,
    *REFERENCE_INPUT_ARTIFACTS,
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessor",
    "source_pins",
    "vocabularies",
    "namespace_separation",
    "unresolved_inconsistency",
    "selection_boundary",
    "collections",
    "evaluation_boundary",
    "execution_boundary",
    "diagnostic_boundary",
    "verification_boundary",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_binding",
    "source_bindings",
    "vocabularies",
    "namespace_separation",
    "unresolved_inconsistency",
    "selection_boundary",
    "collections",
    "evaluation_boundary",
    "execution_boundary",
    "diagnostic_boundary",
    "verification_boundary",
)
EVALUATION_KEYS: Final = (
    "same_hash",
    "idempotency",
    "reconciliation",
    "authorization",
    "step_up",
    "audit_atomicity",
)
EXECUTION_STATUS_KEYS: Final = (
    "database",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "audit",
    "outbox",
    "provider",
    "network",
    "file_intake",
    "runtime",
    "live",
    "staging",
    "release",
    "production",
)
ACTION_COUNT_KEYS: Final = (
    "database",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "audit",
    "outbox",
    "provider",
    "network",
    "file_intake",
    "write",
    "create_fact",
    "emit_event",
    "external",
)

EXPECTED_STORY: Final = {
    "id": "ST-1302",
    "epic_id": "EPIC-13",
    "title": "Provider fact commit",
    "objective": "dry runと同一Hashを冪等取込",
    "depends_on": ["ST-1301"],
    "requirement_ids": ["FR-014"],
    "design_refs": [],
    "deliverables": ["commit command", "facts"],
    "acceptance_criteria": ["generated/confirmed/cancelled separate"],
    "test_suites": ["TST-008", "TST-030"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": [],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_DOCUMENT: Final = {
    "schema_version": "1.0.0",
    "story_id": "ST-1302",
    "classification": "SOURCE_DERIVED_NONEXECUTABLE_PROVIDER_FACT_COMMIT_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "activation": False,
    "runtime_eligible": False,
    "authority": "NOT_GRANTED",
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "canonical_status": "UNCHANGED",
}
EXPECTED_CONTRACT_AUTHORITY: Final = {
    "canonical_story": {
        "path": STORY_PATH.as_posix(),
        "sha256": STORY_SHA256,
        "story_id": "ST-1302",
    },
    "integration_precedence": {
        "path": INTEGRATION_PATH.as_posix(),
        "sha256": INTEGRATION_SHA256,
    },
    "open_decisions": {
        "path": OPEN_DECISIONS_PATH.as_posix(),
        "sha256": OPEN_DECISIONS_SHA256,
        "required_id": "OD-003",
        "required_status": "EXTERNAL_EVIDENCE_REQUIRED",
        "blocking": True,
    },
    "authority_kind": "SOURCE_DERIVED_REFERENCE_ONLY",
    "changes_canonical_status": False,
}
EXPECTED_AUTHORITY: Final = {
    "canonical_story": EXPECTED_STORY,
    "integration_precedence": EXPECTED_CONTRACT_AUTHORITY["integration_precedence"],
    "open_decisions": EXPECTED_CONTRACT_AUTHORITY["open_decisions"],
    "authority_kind": "SOURCE_DERIVED_REFERENCE_ONLY",
    "changes_canonical_status": False,
}
EXPECTED_PREDECESSOR_SEMANTICS: Final = {
    "classification": "MAXIMUM_SAFE_LOCAL_SYNTHETIC_NON_PERSISTENT_REVENUE_DRY_RUN_REFERENCE_SEAM",
    "profile": "RAOS_ST1301_SYNTHETIC_V1",
    "execution": "SYNTHETIC_FIXTURE_ONLY",
    "mapping": "UNVERIFIED",
    "decision": "NOT_READY",
    "provider_total_jpy": None,
    "reconciliation": "NOT_EXECUTED",
    "persistence": "NOT_EXECUTED",
    "facts": "NOT_CREATED",
    "commit_capability": "ABSENT",
}


def _artifact_rows(artifacts: Sequence[tuple[Path, str]]) -> dict[str, str]:
    return {path.as_posix(): digest for path, digest in artifacts}


def _artifact_uri_rows(artifacts: Sequence[tuple[Path, str]]) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest}
        for path, digest in artifacts
    ]


EXPECTED_PREDECESSOR: Final = {
    "story_id": "ST-1301",
    "feature_commit": PREDECESSOR_COMMIT,
    "binding": "EXACT_CURRENT_COMMITTED_BYTES",
    "artifacts": _artifact_rows(PREDECESSOR_ARTIFACTS),
    "required_semantics": EXPECTED_PREDECESSOR_SEMANTICS,
}
EXPECTED_SOURCE_PINS: Final = {
    "st0308_persistence_plan": {
        "path": ST0308_CONTRACT_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[0][1],
    },
    "st0308_reference_plan": {
        "path": ST0308_PLAN_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[1][1],
    },
    "st0308_manifest": {
        "path": ST0308_MANIFEST_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[2][1],
    },
    "st0305_contract": {
        "path": ST0305_CONTRACT_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[3][1],
    },
    "st0305_catalog": {
        "path": ST0305_CATALOG_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[4][1],
    },
    "canonical_row_schema": {
        "path": CANONICAL_ROW_SCHEMA_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[5][1],
    },
    "commit_job_schema": {
        "path": COMMIT_JOB_SCHEMA_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[6][1],
    },
    "job_catalog": {
        "path": JOB_CATALOG_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[7][1],
    },
    "state_transition_catalog": {
        "path": STATE_TRANSITION_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[8][1],
    },
    "admin_openapi": {
        "path": ADMIN_OPENAPI_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[9][1],
    },
    "rbac_matrix": {
        "path": RBAC_MATRIX_PATH.as_posix(),
        "sha256": REFERENCE_INPUT_ARTIFACTS[10][1],
    },
}
EXPECTED_VOCABULARIES: Final = {
    "mapping_defined": False,
    "canonical_row_event": ["GENERATED", "CONFIRMED", "CANCELLED", "ADJUSTED"],
    "commission_status": ["GENERATED", "CONFIRMED", "CANCELLED", "ADJUSTED", "UNKNOWN"],
    "commission_event": [
        "GENERATED",
        "CONFIRMED",
        "CANCELLED",
        "AMOUNT_CHANGED",
        "CORRECTED",
    ],
}
EXPECTED_NAMESPACE_SEPARATION: Final = {
    "equivalence_inferred": False,
    "api_operation": "FIN-006",
    "oauth_scope": "finance:revenue:confirm",
    "audit_action": "revenue_import_confirm",
    "rbac_action": "commit_revenue_import",
    "mapping": [],
}
EXPECTED_UNRESOLVED_INCONSISTENCY: Final = {
    "status": "UNRESOLVED",
    "job_catalog_idempotency_basis": [
        "revenue_import_id",
        "source_sha256",
        "preview_hash",
    ],
    "commit_job_payload_fields": [
        "revenue_import_id",
        "expected_source_sha256",
        "expected_accepted_count",
        "expected_commission_amount_jpy",
    ],
    "admin_confirm_request_fields": [
        "expected_source_sha256",
        "expected_accepted_count",
        "expected_commission_amount_jpy",
    ],
    "missing_field": "preview_hash",
    "selected_preview_hash": None,
    "replacement_algorithm": None,
    "resolved": False,
}
EXPECTED_SELECTION_BOUNDARY: Final = {
    "data_class": "RESTRICTED",
    "source_sha256": None,
    "preview_hash": None,
    "provider_identity": None,
    "provider_event_identity": None,
    "currency_literal": "JPY",
    "fx_policy": None,
    "conversion_policy": None,
    "business_policy": None,
    "cost_policy": None,
    "retention_policy": None,
    "period": None,
    "committed_at": None,
    "actor": None,
    "authorization": None,
    "step_up": None,
    "reconciliation_result": None,
    "commit_result": None,
    "approval": None,
}
EXPECTED_COLLECTIONS: Final[dict[str, object]] = {
    "canonical_rows": [],
    "provider_facts": [],
    "commission_events": [],
    "emitted_events": [],
    "writes": [],
    "canonical_row_count": None,
    "provider_fact_count": None,
    "commission_event_count": None,
    "emitted_event_count": None,
    "write_count": None,
    "amount_total_jpy": None,
    "empty_means_zero": False,
}
EXPECTED_EVALUATION_BOUNDARY: Final = {
    **{key: {"evaluable": False, "result": None} for key in EVALUATION_KEYS},
    "vacuous_pass_allowed": False,
}
EXPECTED_ACTION_COUNTS: Final = {key: 0 for key in ACTION_COUNT_KEYS}
EXPECTED_EXECUTION_BOUNDARY: Final = {
    **{key: "NOT_EXECUTED" for key in EXECUTION_STATUS_KEYS},
    "action_counts": EXPECTED_ACTION_COUNTS,
    "external_actions": [],
}
EXPECTED_DIAGNOSTIC_BOUNDARY: Final = {
    "raw_row_allowed": False,
    "provider_id_allowed": False,
    "note_allowed": False,
    "error_allowed": False,
    "fixture_body_allowed": False,
    "dynamic_values": [],
}
EXPECTED_VERIFICATION_BOUNDARY: Final = {
    "TST-008": "NOT_EXECUTED",
    "TST-030": "NOT_EXECUTED",
    "formal_validation": "NOT_EXECUTED",
    "story_acceptance": False,
    "decision": "NOT_READY",
}


class ProviderFactCommitReferenceError(RuntimeError):
    """Stable sanitized reference-plan failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise ProviderFactCommitReferenceError(
        f"ST-1302 build failed: {code} field={field}"
    )


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
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
    _read(root, relative, field)
    return _mapping(base.load_yaml(root / relative), field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    content = _read(root, relative, field)
    try:
        value = json.loads(content)
    except UnicodeDecodeError, json.JSONDecodeError, RecursionError:
        _fail("JSON_INVALID", field)
    return _mapping(value, field)


def _find_record(items: object, key: str, value: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get(key) == value
    ]
    if len(matches) != 1:
        _fail("RECORD_MISSING_OR_DUPLICATE", field)
    return matches[0]


def _verify_hashes(root: Path) -> None:
    for relative, expected in REQUIRED_INPUT_ARTIFACTS:
        if _sha256(_read(root, relative, "input")) != expected:
            _fail("INPUT_HASH_DRIFT", "input")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_HASH_DRIFT", "helper")


def _validate_story_and_decision(root: Path) -> None:
    story_source = _load_yaml(root, STORY_PATH, "story")
    story = _find_record(story_source.get("stories"), "id", "ST-1302", "story")
    _exact(story, EXPECTED_STORY, "story")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")
    decision = _find_record(decisions.get("items"), "id", "OD-003", "open_decisions")
    _exact(decision.get("status"), "EXTERNAL_EVIDENCE_REQUIRED", "open_decisions")
    _exact(decision.get("blocking"), True, "open_decisions")


def _validate_predecessor_semantics(root: Path) -> None:
    domain = _read(
        root, Path("python/raos/domain/finance/revenue_import.py"), "predecessor"
    ).decode("utf-8", errors="strict")
    readme = _read(root, Path("changes/st-1301/README.md"), "predecessor").decode(
        "utf-8", errors="strict"
    )
    for fragment in (
        'RAOS_ST1301_SYNTHETIC_V1 = "RAOS_ST1301_SYNTHETIC_V1"',
        'SYNTHETIC_FIXTURE_ONLY = "SYNTHETIC_FIXTURE_ONLY"',
        'UNVERIFIED = "UNVERIFIED"',
        'NOT_CREATED = "NOT_CREATED"',
        'NOT_READY = "NOT_READY"',
        "self.provider_total_jpy is not None",
        "self.persistence is not RevenueExecutionStatus.NOT_EXECUTED",
    ):
        if fragment not in domain:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")
    for fragment in (
        "fully synthetic CSV",
        "deliberately not a Rakuten report format",
        "`NOT_READY`",
    ):
        if fragment not in readme:
            _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor")


def _validate_reference_semantics(root: Path) -> None:
    persistence = _load_json(root, ST0308_PLAN_PATH, "st0308")
    document = _mapping(persistence.get("document"), "st0308.document")
    activation = _mapping(persistence.get("activation"), "st0308.activation")
    if (
        document.get("executable") is not False
        or activation.get("enabled") is not False
        or activation.get("runtime_eligible") is not False
        or activation.get("authority") != "NOT_GRANTED"
    ):
        _fail("PERSISTENCE_BOUNDARY_DRIFT", "st0308")

    row_schema = _load_json(root, CANONICAL_ROW_SCHEMA_PATH, "row_schema")
    properties = _mapping(row_schema.get("properties"), "row_schema.properties")
    event_type = _mapping(properties.get("event_type"), "row_schema.event_type")
    _exact(
        event_type.get("enum"),
        EXPECTED_VOCABULARIES["canonical_row_event"],
        "row_schema",
    )

    job_schema = _load_json(root, COMMIT_JOB_SCHEMA_PATH, "commit_job")
    all_of = _list(job_schema.get("allOf"), "commit_job.allOf")
    payload = _mapping(
        _mapping(_mapping(all_of[1], "commit_job").get("properties"), "commit_job").get(
            "payload"
        ),
        "commit_job.payload",
    )
    payload_fields = _mapping(payload.get("properties"), "commit_job.fields")
    _exact(
        list(payload_fields),
        EXPECTED_UNRESOLVED_INCONSISTENCY["commit_job_payload_fields"],
        "commit_job.fields",
    )
    if "preview_hash" in payload_fields:
        _fail("PREVIEW_HASH_INCONSISTENCY_CLOSED", "commit_job")

    catalog = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")
    job = _find_record(
        catalog.get("jobs"),
        "job_type",
        "finance.commit_revenue_import.v1",
        "job_catalog",
    )
    _exact(
        job.get("idempotency_basis"),
        EXPECTED_UNRESOLVED_INCONSISTENCY["job_catalog_idempotency_basis"],
        "job_catalog",
    )

    openapi_text = _read(root, ADMIN_OPENAPI_PATH, "openapi").decode(
        "utf-8", errors="strict"
    )
    for fragment in (
        "operationId: FIN-006",
        "finance:revenue:confirm",
        "x-raos-audit-action: revenue_import_confirm",
        "expected_source_sha256:",
        "expected_accepted_count:",
        "expected_commission_amount_jpy:",
    ):
        if fragment not in openapi_text:
            _fail("OPENAPI_SEMANTIC_DRIFT", "openapi")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    expected_sections = (
        ("document", EXPECTED_DOCUMENT),
        ("authority", EXPECTED_CONTRACT_AUTHORITY),
        ("predecessor", EXPECTED_PREDECESSOR),
        ("source_pins", EXPECTED_SOURCE_PINS),
        ("vocabularies", EXPECTED_VOCABULARIES),
        ("namespace_separation", EXPECTED_NAMESPACE_SEPARATION),
        ("unresolved_inconsistency", EXPECTED_UNRESOLVED_INCONSISTENCY),
        ("selection_boundary", EXPECTED_SELECTION_BOUNDARY),
        ("collections", EXPECTED_COLLECTIONS),
        ("evaluation_boundary", EXPECTED_EVALUATION_BOUNDARY),
        ("execution_boundary", EXPECTED_EXECUTION_BOUNDARY),
        ("diagnostic_boundary", EXPECTED_DIAGNOSTIC_BOUNDARY),
        ("verification_boundary", EXPECTED_VERIFICATION_BOUNDARY),
    )
    for key, expected in expected_sections:
        _exact(contract.get(key), expected, key)
    _verify_hashes(root)
    _validate_story_and_decision(root)
    _validate_predecessor_semantics(root)
    _validate_reference_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    return validate_contract(contract, root)


def reference_plan(contract: Mapping[str, Any]) -> dict[str, object]:
    validated = validate_contract(contract)
    source_bindings = [
        {"name": name, "uri": f"repo://{value['path']}", "sha256": value["sha256"]}
        for name, value in _mapping(validated["source_pins"], "source_pins").items()
    ]
    plan: dict[str, object] = {
        "document": EXPECTED_DOCUMENT,
        "authority": EXPECTED_AUTHORITY,
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_binding": EXPECTED_PREDECESSOR,
        "source_bindings": source_bindings,
        "vocabularies": EXPECTED_VOCABULARIES,
        "namespace_separation": EXPECTED_NAMESPACE_SEPARATION,
        "unresolved_inconsistency": EXPECTED_UNRESOLVED_INCONSISTENCY,
        "selection_boundary": EXPECTED_SELECTION_BOUNDARY,
        "collections": EXPECTED_COLLECTIONS,
        "evaluation_boundary": EXPECTED_EVALUATION_BOUNDARY,
        "execution_boundary": EXPECTED_EXECUTION_BOUNDARY,
        "diagnostic_boundary": EXPECTED_DIAGNOSTIC_BOUNDARY,
        "verification_boundary": EXPECTED_VERIFICATION_BOUNDARY,
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def _json_bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail("JSON_SERIALIZATION_FAILED", "output")


def _artifact(root: Path, relative: Path) -> dict[str, object]:
    content = _read(root, relative, "manifest.source")
    return {
        "uri": f"repo://{relative.as_posix()}",
        "bytes": len(content),
        "sha256": _sha256(content),
    }


def _manifest_bytes(root: Path, reference_bytes: bytes) -> bytes:
    manifest = {
        "schema_version": "1.0.0",
        "story_id": "ST-1302",
        "classification": EXPECTED_DOCUMENT["classification"],
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "source_contract": SOURCE_URI,
        "source_artifact_count": len(SOURCE_PATHS),
        "source_artifacts": [_artifact(root, path) for path in SOURCE_PATHS],
        "generated_artifacts": [
            {
                "uri": f"repo://{REFERENCE_PLAN_PATH.as_posix()}",
                "bytes": len(reference_bytes),
                "sha256": _sha256(reference_bytes),
            }
        ],
        "provenance": {
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
            "predecessor_commit": PREDECESSOR_COMMIT,
            "predecessor_inputs": _artifact_uri_rows(PREDECESSOR_ARTIFACTS),
            "reference_inputs": _artifact_uri_rows(REFERENCE_INPUT_ARTIFACTS),
            "authority_inputs": _artifact_uri_rows(AUTHORITY_ARTIFACTS),
        },
        "boundary": {
            "canonical_row_count": None,
            "provider_fact_count": None,
            "commission_event_count": None,
            "emitted_event_count": None,
            "write_count": None,
            "amount_total_jpy": None,
            "source_sha256": None,
            "preview_hash": None,
            "commit_result": None,
            "action_counts": EXPECTED_ACTION_COUNTS,
        },
    }
    return yaml.dump(
        manifest, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True
    ).encode("utf-8")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan_for_root(contract, root))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, reference_bytes),
    }


def reference_plan_for_root(
    contract: Mapping[str, Any], root: Path
) -> dict[str, object]:
    validate_contract(contract, root)
    source_bindings = [
        {"name": name, "uri": f"repo://{value['path']}", "sha256": value["sha256"]}
        for name, value in _mapping(contract["source_pins"], "source_pins").items()
    ]
    return {
        "document": EXPECTED_DOCUMENT,
        "authority": EXPECTED_AUTHORITY,
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_binding": EXPECTED_PREDECESSOR,
        "source_bindings": source_bindings,
        "vocabularies": EXPECTED_VOCABULARIES,
        "namespace_separation": EXPECTED_NAMESPACE_SEPARATION,
        "unresolved_inconsistency": EXPECTED_UNRESOLVED_INCONSISTENCY,
        "selection_boundary": EXPECTED_SELECTION_BOUNDARY,
        "collections": EXPECTED_COLLECTIONS,
        "evaluation_boundary": EXPECTED_EVALUATION_BOUNDARY,
        "execution_boundary": EXPECTED_EXECUTION_BOUNDARY,
        "diagnostic_boundary": EXPECTED_DIAGNOSTIC_BOUNDARY,
        "verification_boundary": EXPECTED_VERIFICATION_BOUNDARY,
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
        if stat.S_IMODE(path.stat().st_mode) != 0o644:
            _fail("GENERATED_OUTPUT_MODE_DRIFT", "output")


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


def main_for_root(root: Path, argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        build(root, check=args.check)
    except (
        ProviderFactCommitReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1302 provider-fact reference plan checked"
        if args.check
        else "ST-1302 provider-fact reference plan generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
