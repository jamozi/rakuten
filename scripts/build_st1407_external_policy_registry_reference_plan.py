#!/usr/bin/env python3
"""Build the inert, non-attesting ST-1407 external-policy reference plan."""

from __future__ import annotations

import argparse
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
    "changes/st-1407/contracts/external-policy-registry-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1407/generated/external-policy-registry-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1407/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1407_external_policy_registry_reference_plan.py"
)
README_PATH: Final = Path("changes/st-1407/README.md")
TEST_PATHS: Final = (
    Path("tests/st1407/conftest.py"),
    Path("tests/st1407/test_contract.py"),
    Path("tests/st1407/test_generation.py"),
    Path("tests/st1407/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st1407_external_policy_registry_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
MASTER_TRACE_PATH: Final = Path(
    "docs/canonical/00_master/RAOS_master_traceability_v1.0.csv"
)
ACCEPTANCE_TRACE_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_acceptance_traceability_v1.0.csv"
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
CONTRACT_REPOSITORY_PATH: Final = Path(
    "contracts/raos-v0.4/contract-repository.v0.4.json"
)
EXTERNAL_RULE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_external_rule_snapshot_v0.1.yaml"
)
OFFICIAL_REFERENCE_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_official_references_v0.1.yaml"
)
EDITORIAL_POLICY_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
ADMIN_API_PATH: Final = Path("contracts/raos-v0.4/contracts/openapi-admin.v0.4.yaml")
ASYNC_API_PATH: Final = Path("contracts/raos-v0.4/contracts/asyncapi.v0.4.yaml")
ALERT_CATALOG_PATH: Final = Path(
    "docs/canonical/06_ops/RAOS_12_alert_catalog_v1.0.yaml"
)
RUNBOOK_CATALOG_PATH: Final = Path(
    "docs/canonical/06_ops/RAOS_12_runbook_index_v1.0.yaml"
)
SECURITY_CONTROL_PATH: Final = Path(
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
        "open_decisions",
        OPEN_DECISIONS_PATH.as_posix(),
        "a51de01ab7665c37047371cad8c9308d3d1a9428dab485599a2ce3de3ddba07e",
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
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
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
        "contract_repository",
        CONTRACT_REPOSITORY_PATH.as_posix(),
        "54fc0cbb0c943f0b876881dbd2d55b49bb354f3cd8e533caef99dbbff4efaeef",
    ),
    (
        "external_rule_snapshot",
        EXTERNAL_RULE_PATH.as_posix(),
        "14a4131215f8c2f70a2f5b73aef0ccb1162f1a8ac6d410079c6a3b6b68955042",
    ),
    (
        "official_references",
        OFFICIAL_REFERENCE_PATH.as_posix(),
        "d7a3986affce9d2fc1110d6b3fffb196c668dae7db00288d466b9e62ba57e030",
    ),
    (
        "editorial_policy_catalog",
        EDITORIAL_POLICY_PATH.as_posix(),
        "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
    ),
    (
        "job_catalog",
        JOB_CATALOG_PATH.as_posix(),
        "70a9926f1ac64bd47ce084c28ebb08792d63b07feb5ced85e40377815ba3aeb1",
    ),
    (
        "admin_api",
        ADMIN_API_PATH.as_posix(),
        "6a22ee7a5f13ed89ac3bb6ceeffe49aad8b11e4f2a3a137c927542461c2ace70",
    ),
    (
        "asyncapi",
        ASYNC_API_PATH.as_posix(),
        "3373668d6028be7d90bb35c4ab893c4572201fd71c213d12a165ac1f190ee6dd",
    ),
    (
        "alert_catalog",
        ALERT_CATALOG_PATH.as_posix(),
        "f180e950f659d27e9270b6c1f9c1dcb6d0fa6194acdc1fdd7026ac7cea560be0",
    ),
    (
        "runbook_catalog",
        RUNBOOK_CATALOG_PATH.as_posix(),
        "2aed21892e78ead32fc647b928f50014971d280142d0f49f4e0d1e7d68897100",
    ),
    (
        "operations_design",
        "docs/canonical/06_ops/RAOS_12_operations_reliability_design_v1.0.md",
        "894a4520a54fe1a5391f5bdd7ebfd3fdacf745604d1245e20b139315eabad9c8",
    ),
    (
        "security_controls",
        SECURITY_CONTROL_PATH.as_posix(),
        "c4217f169d43352451ba728f674c72f6df2c0be6e90f36a183b510fa38e7adb8",
    ),
    (
        "threat_register",
        THREAT_REGISTER_PATH.as_posix(),
        "6a1208fe0013c7a8211089b7b839544ec603a943c50597228db612bf935826dd",
    ),
)

DEPENDENCY_INPUTS: Final = (
    (
        "ST-0405",
        "readme",
        "changes/st-0405/README.md",
        "8b046d65492947a458306c308f5515bb6496e0371bdc9695226d52328a04a657",
    ),
    (
        "ST-0405",
        "audit_port",
        "python/raos/ports/audit.py",
        "d358f8349ebeb70c3b8f046b82c109a80f162fe88432d1e0d4e11e4ff21592ec",
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
)

CONTRACT_KEYS: Final = (
    "document",
    "pro_assistance",
    "authority",
    "dependencies",
    "unresolved_gates",
    "projection_rules",
    "candidate_seam_defaults",
    "evaluation_defaults",
    "execution_defaults",
    "verification_defaults",
)
PLAN_KEYS: Final = (
    "document",
    "pro_assistance",
    "authority",
    "provenance",
    "dependencies",
    "unresolved_gates",
    "catalog_projection",
    "candidate_seams",
    "evaluation_boundary",
    "execution_boundary",
    "verification_boundary",
)
EXTERNAL_RULE_FIELDS: Final = (
    "id",
    "domain",
    "topic",
    "observed_rule",
    "url",
    "content_policy_ids",
)
OFFICIAL_REFERENCE_FIELDS: Final = (
    "id",
    "authority",
    "title",
    "url",
    "applied_to",
)
POLICY_FIELDS: Final = ("id", "severity", "stage", "code", "rule", "enforcement")
ALERT_FIELDS: Final = (
    "id",
    "severity",
    "name",
    "condition",
    "detection",
    "initial_action",
    "implementation_status",
    "test_status",
)
RUNBOOK_FIELDS: Final = (
    "id",
    "title",
    "severity",
    "minimum_steps",
    "document_status",
    "implementation_status",
    "drill_status",
)

EXTERNAL_RULE_IDS: Final = (
    "EXT-GOOGLE-001",
    "EXT-GOOGLE-002",
    "EXT-GOOGLE-003",
    "EXT-GOOGLE-004",
    "EXT-GOOGLE-005",
    "EXT-GOOGLE-006",
    "EXT-GOOGLE-007",
    "EXT-GOOGLE-008",
    "EXT-W3C-001",
    "EXT-RAKUTEN-001",
    "EXT-RAKUTEN-002",
    "EXT-RAKUTEN-003",
    "EXT-CAA-001",
)
EXPECTED_EXTERNAL_URLS: Final = {
    "EXT-GOOGLE-001": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
    "EXT-GOOGLE-002": "https://developers.google.com/search/docs/essentials/spam-policies",
    "EXT-GOOGLE-003": "https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links",
    "EXT-GOOGLE-004": "https://developers.google.com/search/docs/fundamentals/using-gen-ai-content",
    "EXT-GOOGLE-005": "https://developers.google.com/search/docs/fundamentals/ai-optimization-guide",
    "EXT-GOOGLE-006": "https://developers.google.com/search/docs/appearance/structured-data/product-snippet",
    "EXT-GOOGLE-007": "https://developers.google.com/search/updates#removing-faq-rich-result",
    "EXT-GOOGLE-008": "https://developers.google.com/search/docs/appearance/google-images",
    "EXT-W3C-001": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html",
    "EXT-RAKUTEN-001": "https://affiliate.rakuten.co.jp/guideline/rule/",
    "EXT-RAKUTEN-002": "https://affiliate.rakuten.co.jp/guideline/stealth_marketing_regulation/",
    "EXT-RAKUTEN-003": "https://webservice.rakuten.co.jp/guide/credit",
    "EXT-CAA-001": "https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing",
}
EXPECTED_EXTERNAL_POLICY_MAP: Final = {
    "EXT-GOOGLE-001": ("POL-CONT-019", "POL-CONT-020", "POL-CONT-021"),
    "EXT-GOOGLE-002": ("POL-CONT-020", "POL-CONT-030"),
    "EXT-GOOGLE-003": ("POL-CONT-010",),
    "EXT-GOOGLE-004": ("POL-CONT-001", "POL-CONT-002", "POL-CONT-020"),
    "EXT-GOOGLE-005": ("POL-CONT-020", "POL-CONT-030"),
    "EXT-GOOGLE-006": ("POL-CONT-027", "POL-CONT-029"),
    "EXT-GOOGLE-007": ("POL-CONT-028",),
    "EXT-GOOGLE-008": ("POL-CONT-032", "POL-CONT-033"),
    "EXT-W3C-001": ("POL-CONT-032",),
    "EXT-RAKUTEN-001": (
        "POL-CONT-004",
        "POL-CONT-007",
        "POL-CONT-011",
        "POL-CONT-013",
    ),
    "EXT-RAKUTEN-002": ("POL-CONT-008",),
    "EXT-RAKUTEN-003": ("POL-CONT-012",),
    "EXT-CAA-001": ("POL-CONT-008",),
}
OFFICIAL_REFERENCE_IDS: Final = (
    "REF-RAKUTEN-001",
    "REF-RAKUTEN-002",
    "REF-CAA-001",
    "REF-CAA-002",
    "REF-GOOGLE-001",
    "REF-GOOGLE-002",
    "REF-GOOGLE-003",
    "REF-GOOGLE-004",
    "REF-GOOGLE-005",
    "REF-GOOGLE-006",
    "REF-GOOGLE-007",
    "REF-W3C-001",
)
EXPECTED_OFFICIAL_URLS: Final = {
    "REF-RAKUTEN-001": "https://affiliate.rakuten.co.jp/guideline/rule/",
    "REF-RAKUTEN-002": "https://affiliate.rakuten.co.jp/guideline/stealth_marketing_regulation/",
    "REF-CAA-001": "https://www.caa.go.jp/policies/policy/representation/fair_labeling/stealth_marketing",
    "REF-CAA-002": "https://www.caa.go.jp/policies/policy/representation/fair_labeling/faq/stealth_marketing/",
    "REF-GOOGLE-001": "https://developers.google.com/search/docs/fundamentals/creating-helpful-content",
    "REF-GOOGLE-002": "https://developers.google.com/search/docs/essentials/spam-policies",
    "REF-GOOGLE-003": "https://developers.google.com/search/docs/specialty/ecommerce/write-high-quality-reviews",
    "REF-GOOGLE-004": "https://developers.google.com/search/docs/crawling-indexing/qualify-outbound-links",
    "REF-GOOGLE-005": "https://developers.google.com/search/docs/appearance/structured-data/article",
    "REF-GOOGLE-006": "https://developers.google.com/search/docs/appearance/structured-data/product",
    "REF-GOOGLE-007": "https://developers.google.com/search/updates",
    "REF-W3C-001": "https://www.w3.org/WAI/WCAG22/Understanding/non-text-content.html",
}


class ExternalPolicyReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise ExternalPolicyReferenceError(f"ST-1407 build failed: {code} field={field}")


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


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_dependency_rows() -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {"ST-0405": [], "ST-0805": []}
    for story_id, role, path, digest in DEPENDENCY_INPUTS:
        grouped[story_id].append(
            {"role": role, "uri": f"repo://{path}", "sha256": digest}
        )
    return [
        {
            "story_id": "ST-0405",
            "artifacts": grouped["ST-0405"],
            "implementation_scope": "PROCESS_LOCAL_RECORDED_AUDIT_SEAM",
            "connection_status": "NOT_EXECUTED",
            "use_status": "NOT_AUTHORIZED_FOR_ST1407_WRITES",
        },
        {
            "story_id": "ST-0805",
            "artifacts": grouped["ST-0805"],
            "implementation_scope": "PURE_LOCAL_EDITORIAL_POLICY_EVALUATOR",
            "connection_status": "NOT_EXECUTED",
            "bundle_identity_status": "NOT_AVAILABLE",
        },
    ]


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST1407-EXTERNAL-POLICY-REGISTRY-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-1407",
    "classification": "SOURCE_DERIVED_NON_ATTESTING_EXTERNAL_POLICY_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
}
EXPECTED_PRO_ASSISTANCE: Final = {
    "status": "PRO_UNAVAILABLE",
    "authority": "NONE",
    "proposal_captured": False,
    "content_used": False,
}
EXPECTED_UNRESOLVED_GATES: Final = [
    {
        "id": "OPEN-018",
        "topic": "primary_source_domain_allowlist",
        "status": "UNRESOLVED",
        "safe_default": "NO_AUTOMATED_SOURCE_ACQUISITION",
        "human_gated": True,
    },
    {
        "id": "OD-008",
        "topic": "legal_review_boundary",
        "status": "HUMAN_DECISION_REQUIRED",
        "safe_default": "BLOCK_PUBLICATION_NO_AI_LEGAL_SUBSTITUTION",
        "human_gated": True,
    },
    {
        "id": "OD-011",
        "topic": "notification_channels",
        "status": "HUMAN_DECISION_REQUIRED",
        "safe_default": "LOCAL_LOG_ONLY_PRODUCTION_DISABLED",
        "human_gated": True,
    },
]
EXPECTED_PROJECTION_RULES: Final = {
    "preserve_catalog_order": True,
    "exact_external_rule_count": 13,
    "exact_official_reference_count": 12,
    "exact_editorial_policy_count": 40,
    "project_external_rule_to_content_policy_ids": True,
    "infer_official_reference_links": False,
    "infer_source_snapshot_links": False,
    "infer_rule_version_links": False,
    "identify_external_snapshot_as_policy_bundle": False,
    "interpret_review_frequency_as_deadline": False,
    "initial_actions_are_inert_text": True,
    "runbook_steps_are_inert_text": True,
    "empty_arrays_mean_not_evaluated_or_not_executed": True,
}
EXPECTED_CANDIDATE_SEAMS: Final = {
    "source_snapshot": {
        "entity": "evidence.source_snapshot",
        "relation_to_external_policy": "UNSPECIFIED",
        "instances": [],
        "content_byte_artifacts": [],
    },
    "policy_bundle": {
        "entity": "policy.policy_bundle",
        "identity_relation": "DISTINCT_NOT_IDENTICAL",
        "bundle_links": [],
        "rule_version_links": [],
    },
    "publication_snapshot": {
        "entity": "publishing.publication_snapshot",
        "relation_status": "UNLINKED_CANDIDATE_SEAM",
        "version_links": [],
        "affected_articles": [],
    },
    "alert": {
        "entity": "ops.alert",
        "catalog_id": "ALT-019",
        "catalog_severity": "SEV4",
        "ops_severity_mapping": "NOT_DEFINED",
        "state": "NOT_EVALUATED",
        "records": [],
    },
    "audit": {
        "entity": "ops.audit_event",
        "action": "NOT_DEFINED",
        "state": "NOT_EVALUATED",
        "events": [],
    },
}
EXPECTED_EVALUATION: Final = {
    "snapshot_instances": [],
    "official_content_bytes": [],
    "change_diffs": [],
    "join_records": [],
    "version_links": [],
    "due_evaluations": [],
    "overdue": "NOT_EVALUATED",
    "impact_query": "NOT_EVALUATED",
    "affected_articles": [],
    "affected_articles_empty_interpretation": "QUERY_NOT_EXECUTED_NOT_ZERO_AFFECTED",
    "alert_records": [],
    "audit_events": [],
}
EXPECTED_EXECUTION: Final = {
    "runtime_reader": "NOT_IMPLEMENTED",
    "network": "NOT_EXECUTED",
    "filesystem_runtime": "NOT_EXECUTED",
    "database": "NOT_EXECUTED",
    "api": "NOT_EXECUTED",
    "job": "NOT_EXECUTED",
    "event": "NOT_EXECUTED",
    "provider": "NOT_EXECUTED",
    "clock": "NOT_EXECUTED",
    "alert": "NOT_EXECUTED",
    "audit": "NOT_EXECUTED",
    "activation": "NOT_EXECUTED",
    "hold": "NOT_EXECUTED",
    "kill": "NOT_EXECUTED",
    "re_review": "NOT_EXECUTED",
    "publication": "NOT_EXECUTED",
    "external_actions": [],
}
EXPECTED_VERIFICATION: Final = {
    "story_test_suites": ["TST-005", "TST-020"],
    "master_trace_test_suites": ["TST-005", "TST-019", "TST-020"],
    "acceptance_trace_test_suites": ["TST-008", "TST-020"],
    "traceability_status": "DIVERGENT_RECORDED_NOT_RESOLVED",
    "formal_tst_005": "NOT_EXECUTED",
    "formal_tst_019": "NOT_EXECUTED",
    "formal_tst_020": "NOT_EXECUTED",
    "live": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
}


def _validate_source_hashes(root: Path) -> None:
    for _role, path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for _story_id, _role, path, digest in DEPENDENCY_INPUTS:
        if _sha256(_read(root, Path(path), "dependency.source")) != digest:
            _fail("DEPENDENCY_HASH_DRIFT", "dependency.source")
    if _sha256(_read(root, HELPER_PATH, "implementation.helper")) != HELPER_SHA256:
        _fail("IMPLEMENTATION_HELPER_DRIFT", "implementation.helper")


def _find(items: object, identity: str, field: str) -> Mapping[str, Any]:
    matches = [
        _mapping(item, field)
        for item in _list(items, field)
        if type(item) is dict and item.get("id") == identity
    ]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _csv_row(root: Path, path: Path, requirement: str, field: str) -> dict[str, str]:
    try:
        text = _read(root, path, field).decode("utf-8-sig", errors="strict")
        rows = [row for row in csv.DictReader(io.StringIO(text)) if row]
    except UnicodeError, csv.Error:
        _fail("CSV_INVALID", field)
    matches = [row for row in rows if row.get("requirement_id") == requirement]
    if len(matches) != 1:
        _fail("CANONICAL_RECORD_MISSING", field)
    return matches[0]


def _require_fragments(
    root: Path, path: Path, fragments: tuple[str, ...], field: str
) -> None:
    try:
        text = _read(root, path, field).decode("utf-8", errors="strict")
    except UnicodeError:
        _fail("UTF8_INVALID", field)
    if any(fragment not in text for fragment in fragments):
        _fail("CANONICAL_SEMANTIC_DRIFT", field)


def _validate_installed_contract_inventory(root: Path) -> None:
    try:
        repository = json.loads(
            _read(root, CONTRACT_REPOSITORY_PATH, "contract_repository").decode(
                "utf-8", errors="strict"
            )
        )
    except UnicodeError, json.JSONDecodeError:
        _fail("JSON_INVALID", "contract_repository")
    document = _mapping(repository, "contract_repository")
    artifacts = _list(document.get("artifacts"), "contract_repository.artifacts")
    expected = {
        "contracts/content/RAOS_06_external_rule_snapshot_v0.1.yaml": (
            4677,
            "14a4131215f8c2f70a2f5b73aef0ccb1162f1a8ac6d410079c6a3b6b68955042",
        ),
        "contracts/content/RAOS_06_official_references_v0.1.yaml": (
            3960,
            "d7a3986affce9d2fc1110d6b3fffb196c668dae7db00288d466b9e62ba57e030",
        ),
        "contracts/content/RAOS_06_editorial_policy_catalog_v0.1.yaml": (
            8571,
            "d68a584c9ef23de379fdad3f28a087b55e604d33d8d88756e32aeab04ef3220a",
        ),
    }
    found: dict[str, tuple[object, object]] = {}
    for raw in artifacts:
        row = _mapping(raw, "contract_repository.artifact")
        path = row.get("path")
        if type(path) is str and path in expected:
            if path in found:
                _fail("CANONICAL_RECORD_DUPLICATE", "contract_repository.artifact")
            found[path] = (row.get("bytes"), row.get("sha256"))
    if found != expected:
        _fail("INSTALLED_CONTRACT_INVENTORY_DRIFT", "contract_repository")


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    story = _find(stories.get("stories"), "ST-1407", "story")
    if (
        story.get("depends_on") != ["ST-0405", "ST-0805"]
        or story.get("requirement_ids") != ["FR-017"]
        or story.get("design_refs") != []
        or story.get("deliverables") != ["policy snapshot", "impact query"]
        or story.get("acceptance_criteria") != ["overdue alert", "version links"]
        or story.get("test_suites") != ["TST-005", "TST-020"]
        or story.get("open_decisions") != []
        or story.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
        or story.get("implementation_status") != "NOT_STARTED"
        or story.get("verification_status") != "NOT_EXECUTED"
    ):
        _fail("CANONICAL_STORY_DRIFT", "story")

    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")
    for decision_id, expected_default in (
        ("OD-008", "法的判断をAI/開発者が代替せず公開をブロック"),
        ("OD-011", "Local logのみ。Production不可"),
    ):
        decision = _find(decisions.get("items"), decision_id, "open_decision")
        if (
            decision.get("status") != "HUMAN_DECISION_REQUIRED"
            or decision.get("default_behavior") != expected_default
            or decision.get("blocking") is not True
        ):
            _fail("OPEN_DECISION_DRIFT", "open_decision")

    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    for suite_id in ("TST-005", "TST-019", "TST-020"):
        suite = _find(suites.get("suites"), suite_id, "test_catalog")
        if (
            suite.get("implementation_status") != "NOT_STARTED"
            or suite.get("execution_status") != "NOT_EXECUTED"
            or suite.get("release_blocking") is not True
        ):
            _fail("TEST_SUITE_DRIFT", "test_catalog")

    master = _csv_row(root, MASTER_TRACE_PATH, "FR-017", "master_traceability")
    if (
        master.get("requirement") != "link_policy_versions_to_affected_articles"
        or master.get("story_ids") != "ST-0805;ST-1407"
        or master.get("test_suite_ids") != "TST-005;TST-019;TST-020"
        or master.get("coverage_status") != "DESIGNED_NOT_IMPLEMENTED"
    ):
        _fail("TRACEABILITY_DRIFT", "master_traceability")
    acceptance = _csv_row(
        root, ACCEPTANCE_TRACE_PATH, "FR-017", "acceptance_traceability"
    )
    if (
        acceptance.get("requirement") != "link_policy_versions_to_affected_articles"
        or acceptance.get("test_suites") != "['TST-008', 'TST-020']"
        or acceptance.get("implementation_status") != "NOT_STARTED"
        or acceptance.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TRACEABILITY_DRIFT", "acceptance_traceability")

    _require_fragments(
        root,
        ARCHITECTURE_PATH,
        (
            "Affected Content Query",
            "| FR-017 | Quality & Policy | Policy Bundle、Affected Article Query |",
            "| OPEN-018 | 一次情報Allowlist | Source取込前 | Acquisition policy |",
        ),
        "system_architecture",
    )
    _require_fragments(
        root,
        DATA_MODEL_PATH,
        (
            "### `evidence.source_snapshot`",
            "### `policy.policy_bundle`",
            "### `policy.rule_version`",
            "### `policy.bundle_rule`",
            "### `policy.finding`",
            "### `publishing.publication_snapshot`",
            "| `policy_bundle_id` | `uuid` | NO",
            "### `ops.alert`",
            "### `ops.audit_event`",
        ),
        "data_model",
    )
    _require_fragments(
        root,
        API_DESIGN_PATH,
        ("source_snapshot_capture_request", "policy_bundle_activate"),
        "api_event_job_design",
    )
    _require_fragments(
        root,
        JOB_CATALOG_PATH,
        (
            "evidence.capture_source_snapshot.v1",
            "quality.recheck_policy_bundle.v1",
            "freshness.assess_change_impact.v1",
        ),
        "job_catalog",
    )
    _require_fragments(
        root,
        ADMIN_API_PATH,
        (
            "x-raos-audit-action: source_snapshot_capture_request",
            "x-raos-audit-action: policy_bundle_create",
            "x-raos-audit-action: policy_bundle_activate",
            "operationId: OPS-014",
        ),
        "admin_api",
    )
    _require_fragments(
        root,
        ASYNC_API_PATH,
        (
            "jp_raos_evidence_source_snapshot_captured_v1",
            "jp_raos_policy_policy_bundle_activated_v1",
            "jp_raos_freshness_impact_detected_v1",
        ),
        "asyncapi",
    )
    controls = _load_yaml(root, SECURITY_CONTROL_PATH, "security_controls")
    for control_id in ("SEC-GOV-004", "SEC-DATA-004", "SEC-DATA-005", "SEC-AI-001"):
        control = _find(controls.get("controls"), control_id, "security_control")
        if (
            control.get("implementation_status") != "NOT_STARTED"
            or control.get("verification_status") != "NOT_EXECUTED"
        ):
            _fail("SECURITY_CONTROL_DRIFT", "security_control")
    threats = _load_yaml(root, THREAT_REGISTER_PATH, "threat_register")
    threat = _find(threats.get("threats"), "THR-027", "threat_register")
    if (
        threat.get("controls")
        != "contract monitor、official source review、kill switch"
        or threat.get("implementation_status") != "NOT_STARTED"
        or threat.get("verification_status") != "NOT_EXECUTED"
    ):
        _fail("THREAT_REGISTER_DRIFT", "threat_register")
    _require_fragments(
        root,
        Path("changes/st-0405/README.md"),
        ("This slice is process-local only.", "durable writer, durable query"),
        "dependency.st0405",
    )
    _require_fragments(
        root,
        Path("changes/st-0805/README.md"),
        (
            "PURE_DETERMINISTIC_LOCAL_EDITORIAL_POLICY_EVALUATOR",
            "evaluation performs no file, environment, clock, network, database",
        ),
        "dependency.st0805",
    )
    _validate_installed_contract_inventory(root)


def _project_external_rules(root: Path) -> dict[str, object]:
    catalog = _load_yaml(root, EXTERNAL_RULE_PATH, "external_rules")
    if tuple(catalog) != ("document", "observed_at", "review_policy", "rules"):
        _fail("CATALOG_SCHEMA_DRIFT", "external_rules")
    document = _mapping(catalog["document"], "external_rules.document")
    if (
        document.get("id") != "RAOS-CONTENT-EXTERNAL-001"
        or document.get("version") != "0.1"
        or document.get("status") != "APPROVED_FOR_IMPLEMENTATION_CONTRACT"
        or catalog.get("observed_at") != "2026-07-30"
        or catalog.get("review_policy")
        != {
            "frequency": "monthly and event-driven",
            "authoritative_sources_only": True,
            "change_action": "create policy diff, affected publication set, risk classification, approval and re-evaluation",
        }
    ):
        _fail("CATALOG_DOCUMENT_DRIFT", "external_rules")
    rows = _list(catalog["rules"], "external_rules.rules")
    if len(rows) != 13:
        _fail("CATALOG_COUNT_DRIFT", "external_rules")
    projected: list[dict[str, object]] = []
    for expected_id, raw in zip(EXTERNAL_RULE_IDS, rows, strict=True):
        row = _mapping(raw, "external_rules.rule")
        if tuple(row) != EXTERNAL_RULE_FIELDS or row.get("id") != expected_id:
            _fail("CATALOG_ROW_DRIFT", "external_rules")
        if (
            row.get("url") != EXPECTED_EXTERNAL_URLS[expected_id]
            or tuple(_list(row.get("content_policy_ids"), "external_rules.mapping"))
            != EXPECTED_EXTERNAL_POLICY_MAP[expected_id]
            or any(
                type(row.get(name)) is not str or not row.get(name)
                for name in ("domain", "topic", "observed_rule")
            )
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", "external_rules")
        projected.append(dict(row))
    return {
        "document": dict(document),
        "observed_at": catalog["observed_at"],
        "review_policy": catalog["review_policy"],
        "rules": projected,
        "coverage": {"projected": 13, "canonical": 13},
        "official_content_bytes": [],
        "snapshot_instances": [],
    }


def _project_official_references(root: Path) -> dict[str, object]:
    catalog = _load_yaml(root, OFFICIAL_REFERENCE_PATH, "official_references")
    if tuple(catalog) != ("document", "sources", "revalidation_triggers"):
        _fail("CATALOG_SCHEMA_DRIFT", "official_references")
    document = _mapping(catalog["document"], "official_references.document")
    if (
        document.get("id") != "RAOS-CONTENT-REF-001"
        or document.get("version") != "0.1"
        or document.get("verified_on") != "2026-07-30"
        or document.get("status") != "CURRENT_SNAPSHOT_REVALIDATE_BEFORE_PRODUCTION"
    ):
        _fail("CATALOG_DOCUMENT_DRIFT", "official_references")
    rows = _list(catalog["sources"], "official_references.sources")
    if len(rows) != 12:
        _fail("CATALOG_COUNT_DRIFT", "official_references")
    projected: list[dict[str, object]] = []
    for expected_id, raw in zip(OFFICIAL_REFERENCE_IDS, rows, strict=True):
        row = _mapping(raw, "official_references.source")
        if tuple(row) != OFFICIAL_REFERENCE_FIELDS or row.get("id") != expected_id:
            _fail("CATALOG_ROW_DRIFT", "official_references")
        applied_to = _list(row.get("applied_to"), "official_references.applied_to")
        if (
            row.get("url") != EXPECTED_OFFICIAL_URLS[expected_id]
            or any(
                type(row.get(name)) is not str or not row.get(name)
                for name in ("authority", "title")
            )
            or not applied_to
            or any(type(value) is not str or not value for value in applied_to)
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", "official_references")
        projected.append(dict(row))
    triggers = _list(catalog["revalidation_triggers"], "revalidation_triggers")
    if len(triggers) != 5 or any(
        type(value) is not str or not value for value in triggers
    ):
        _fail("CATALOG_SEMANTIC_DRIFT", "revalidation_triggers")
    return {
        "document": dict(document),
        "sources": projected,
        "revalidation_triggers": list(triggers),
        "coverage": {"projected": 12, "canonical": 12},
        "inferred_external_rule_links": [],
    }


def _project_policy_reference(root: Path) -> dict[str, object]:
    catalog = _load_yaml(root, EDITORIAL_POLICY_PATH, "editorial_policies")
    expected_keys = (
        "document",
        "policy_bundle_code",
        "effective_date",
        "precedence",
        "policies",
        "waiver_policy",
    )
    if tuple(catalog) != expected_keys:
        _fail("CATALOG_SCHEMA_DRIFT", "editorial_policies")
    document = _mapping(catalog["document"], "editorial_policies.document")
    if (
        document.get("id") != "RAOS-CONTENT-POLICY-001"
        or document.get("version") != "0.1"
        or document.get("status") != "APPROVED_FOR_IMPLEMENTATION_CONTRACT"
        or catalog.get("policy_bundle_code") != "content-editorial-policy.jp.v1"
        or catalog.get("effective_date") != "2026-07-30"
        or catalog.get("waiver_policy")
        != {
            "blocker_waiver_allowed": False,
            "major_waiver_allowed": True,
            "required": [
                "specific_policy_id",
                "scope",
                "reason",
                "evidence",
                "expiry_at",
                "compliance_approver",
                "audit_event",
            ],
            "maximum_default_duration_days": 30,
        }
    ):
        _fail("CATALOG_DOCUMENT_DRIFT", "editorial_policies")
    rows = _list(catalog["policies"], "editorial_policies.policies")
    expected_ids = tuple(f"POL-CONT-{index:03d}" for index in range(1, 41))
    policy_ids: list[str] = []
    for expected_id, raw in zip(expected_ids, rows, strict=True):
        row = _mapping(raw, "editorial_policies.policy")
        if tuple(row) != POLICY_FIELDS or row.get("id") != expected_id:
            _fail("CATALOG_ROW_DRIFT", "editorial_policies")
        policy_ids.append(expected_id)
    referenced_ids = {
        policy_id
        for policy_ids_for_rule in EXPECTED_EXTERNAL_POLICY_MAP.values()
        for policy_id in policy_ids_for_rule
    }
    if not referenced_ids.issubset(set(policy_ids)):
        _fail("EXTERNAL_POLICY_MAPPING_UNRESOLVED", "editorial_policies")
    return {
        "document": dict(document),
        "catalog_bundle_code": catalog["policy_bundle_code"],
        "catalog_policy_ids": policy_ids,
        "coverage": {"projected_ids": 40, "canonical": 40},
        "mapping_validation": "EXACT_REFERENCED_POLICY_IDS_EXIST",
        "runtime_policy_bundle_id": None,
        "rule_version_links": [],
    }


def _project_alert_and_runbook(
    root: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    alerts = _load_yaml(root, ALERT_CATALOG_PATH, "alerts")
    alert = _find(alerts.get("alerts"), "ALT-019", "alerts")
    expected_alert = {
        "id": "ALT-019",
        "severity": "SEV4",
        "name": "Policy/reference due",
        "condition": "external rules snapshot review overdue",
        "detection": "weekly",
        "initial_action": "assign reviewer",
        "implementation_status": "NOT_STARTED",
        "test_status": "NOT_EXECUTED",
    }
    if tuple(alert) != ALERT_FIELDS or not _same_exact(alert, expected_alert):
        _fail("CATALOG_ROW_DRIFT", "alerts")
    runbooks = _load_yaml(root, RUNBOOK_CATALOG_PATH, "runbooks")
    runbook = _find(runbooks.get("runbooks"), "RB-018", "runbooks")
    expected_runbook = {
        "id": "RB-018",
        "title": "External policy change",
        "severity": "varies",
        "minimum_steps": [
            "capture official change",
            "impact query",
            "kill/hold affected flow",
            "approve patch",
        ],
        "document_status": "DESIGNED_INDEX_ONLY",
        "implementation_status": "NOT_STARTED",
        "drill_status": "NOT_EXECUTED",
    }
    if tuple(runbook) != RUNBOOK_FIELDS or not _same_exact(runbook, expected_runbook):
        _fail("CATALOG_ROW_DRIFT", "runbooks")
    return dict(alert), dict(runbook)


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
    _exact(contract["unresolved_gates"], EXPECTED_UNRESOLVED_GATES, "unresolved_gates")
    _exact(contract["projection_rules"], EXPECTED_PROJECTION_RULES, "projection_rules")
    _exact(
        contract["candidate_seam_defaults"],
        EXPECTED_CANDIDATE_SEAMS,
        "candidate_seams",
    )
    _exact(contract["evaluation_defaults"], EXPECTED_EVALUATION, "evaluation")
    _exact(contract["execution_defaults"], EXPECTED_EXECUTION, "execution")
    _exact(contract["verification_defaults"], EXPECTED_VERIFICATION, "verification")
    _validate_source_hashes(root)
    _validate_authority_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    external_rules = _project_external_rules(root)
    official_references = _project_official_references(root)
    policy_reference = _project_policy_reference(root)
    alert, runbook = _project_alert_and_runbook(root)
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
        "unresolved_gates": contract["unresolved_gates"],
        "catalog_projection": {
            "external_rule_snapshot": external_rules,
            "official_reference_snapshot": official_references,
            "editorial_policy_reference": policy_reference,
            "alert_reference": {
                **alert,
                "authority": "INERT_CATALOG_TEXT_ONLY",
                "ops_severity_mapping": "NOT_DEFINED",
                "state": "NOT_EVALUATED",
                "records": [],
            },
            "runbook_reference": {
                **runbook,
                "authority": "INERT_CATALOG_TEXT_ONLY",
                "execution": "NOT_EXECUTED",
            },
        },
        "candidate_seams": contract["candidate_seam_defaults"],
        "evaluation_boundary": contract["evaluation_defaults"],
        "execution_boundary": {
            **dict(_mapping(contract["execution_defaults"], "execution")),
            "action_counts": {
                "fetch": 0,
                "read_runtime": 0,
                "create": 0,
                "update": 0,
                "delete": 0,
                "publish": 0,
                "notify": 0,
                "activate": 0,
                "hold": 0,
                "kill": 0,
            },
        },
        "verification_boundary": {
            **dict(_mapping(contract["verification_defaults"], "verification")),
            "approval": None,
            "decision": "NOT_READY",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
        },
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
            "id": "RAOS-ST1407-EXTERNAL-POLICY-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1407",
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
            "pro_assistance": "PRO_UNAVAILABLE_NO_CONTENT_USED",
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
            "snapshot_instances": "NOT_EVALUATED",
            "content_bytes": "NOT_EVALUATED",
            "version_links": "NOT_EVALUATED",
            "due": "NOT_EVALUATED",
            "overdue": "NOT_EVALUATED",
            "impact_query": "NOT_EVALUATED",
            "affected_articles": "QUERY_NOT_EXECUTED_NOT_ZERO_AFFECTED",
            "alerts": "NOT_EVALUATED",
            "audit": "NOT_EVALUATED",
            "formal_tst_005": "NOT_EXECUTED",
            "formal_tst_019": "NOT_EXECUTED",
            "formal_tst_020": "NOT_EXECUTED",
            "live": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
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
    except (ExternalPolicyReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1407 external-policy reference plan checked"
        if args.check
        else "ST-1407 external-policy reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
