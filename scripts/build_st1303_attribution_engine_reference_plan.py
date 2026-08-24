#!/usr/bin/env python3
"""Build the non-executable ST-1303 attribution-engine reference plan."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
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
    "changes/st-1303/contracts/attribution-engine-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1303/generated/attribution-engine-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1303/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1303_attribution_engine_reference_plan.py"
)
README_PATH: Final = Path("changes/st-1303/README.md")
TEST_PATHS: Final = (
    Path("tests/st1303/conftest.py"),
    Path("tests/st1303/test_contract.py"),
    Path("tests/st1303/test_generation.py"),
    Path("tests/st1303/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
CONTRACT_SHA256: Final = (
    "f57848109939eb1a1df191b031ea12cb91bd3c029f97472af53dd923bfbc4488"
)
CONTRACT_MODEL_SHA256: Final = (
    "0c429d4afdc2e33e27e28398614893f2f701cfe477096071b71e22c107a56a66"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run "
    "--frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1303_attribution_engine_reference_plan.py"
)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
REQUIREMENT_PATH: Final = Path(
    "docs/canonical/00_master/RAOS_master_traceability_v1.0.csv"
)
ATTRIBUTION_POLICY_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"
)
EVENT_CATALOG_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_event_catalog_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
ST0305_CATALOG_PATH: Final = Path(
    "changes/st-0305/generated/publication-analytics-finance-catalog.v1.json"
)
ST0308_PLAN_PATH: Final = Path(
    "changes/st-0308/generated/persistence-boundary.reference-plan.v1.json"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
ST1202_SOURCE_PATH: Final = Path("packages/web-ui/src/public-event-instrumentation.ts")
ST1302_PLAN_PATH: Final = Path(
    "changes/st-1302/generated/provider-fact-commit-reference-plan.v1.json"
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "dependencies",
    "source_pins",
    "canonical_constraints",
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
    "dependency_bindings",
    "source_bindings",
    "canonical_constraints",
    "selection_boundary",
    "collections",
    "evaluation_boundary",
    "execution_boundary",
    "diagnostic_boundary",
    "verification_boundary",
)
COLLECTION_KEYS: Final = (
    "public_events",
    "provider_facts",
    "candidates",
    "allocations",
    "runs",
    "emitted_events",
    "writes",
)
COUNT_KEYS: Final = (
    "public_event_count",
    "provider_fact_count",
    "candidate_count",
    "allocation_count",
    "run_count",
    "emitted_event_count",
    "write_count",
)
TOTAL_KEYS: Final = (
    "provider_total_jpy",
    "direct_total_jpy",
    "estimated_total_jpy",
    "unattributed_total_jpy",
    "allocated_total_jpy",
    "difference_jpy",
)
EVALUATION_KEYS: Final = (
    "identity_linkage",
    "eligibility",
    "direct_attribution",
    "estimated_attribution",
    "unattributed_assignment",
    "method_version",
    "input_hash",
    "confidence",
    "totals_conserved",
    "correction",
    "supersession",
    "idempotency",
)
EXECUTION_STATUS_KEYS: Final = (
    "database",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "event_collector",
    "event_emission",
    "audit",
    "outbox",
    "browser",
    "provider",
    "network",
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
    "event_collector",
    "event_emission",
    "audit",
    "outbox",
    "browser",
    "provider",
    "network",
    "write",
    "create_fact",
    "create_candidate",
    "create_allocation",
    "create_run",
    "emit_event",
    "external",
)

EXPECTED_STORY: Final = {
    "id": "ST-1303",
    "epic_id": "EPIC-13",
    "title": "Attribution engine",
    "objective": "direct/estimated/unattributedを実装",
    "depends_on": ["ST-1202", "ST-1302"],
    "requirement_ids": ["FR-013"],
    "design_refs": [],
    "deliverables": ["method version", "run"],
    "acceptance_criteria": ["totals conserved", "confidence required"],
    "test_suites": ["TST-007", "TST-030"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": ["OD-003"],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_REQUIREMENT: Final = {
    "requirement_id": "FR-013",
    "requirement": "attribute_search_behavior_clicks_and_commission_to_articles",
    "design_documents": "RAOS-ANALYTICS-001",
    "story_ids": "ST-0305;ST-1201;ST-1202;ST-1203;ST-1204;ST-1205;ST-1303",
    "test_suite_ids": "TST-007;TST-008;TST-011;TST-012;TST-022;TST-030;TST-031",
    "coverage_status": "DESIGNED_NOT_IMPLEMENTED",
}
EXPECTED_POLICY_CLASSES: Final = [
    {
        "code": "PROVIDER_FACT",
        "definition": "楽天Reportに記録された発生・確定・取消事実",
        "confidence": 1.0,
    },
    {
        "code": "DIRECT",
        "definition": "Providerが提供する検証可能な識別子で記事/CTAへ直接接続",
        "confidence": "provider dependent",
    },
    {
        "code": "ESTIMATED",
        "definition": "許可された観測から統計的・規則的に配賦",
        "confidence": "0..1 and mandatory",
    },
    {
        "code": "UNATTRIBUTED",
        "definition": "合理的な配賦ができない",
        "confidence": 0.0,
    },
]
EXPECTED_POLICY_ESTIMATION: Final = {
    "status": "PROVISIONAL_PENDING_REAL_REPORT_SAMPLE",
    "eligible_inputs": [
        "confirmed provider fact",
        "eligible first-party affiliate clicks",
        "article snapshot active window",
        "provider timestamp if available",
    ],
    "forbidden_inputs": [
        "raw IP matching",
        "fingerprinting",
        "invented user identity",
        "commission rate as editorial signal",
    ],
    "method": "同一Site・Provider・時間Bucketでeligible click weightに比例配賦。必要情報がない場合はUNATTRIBUTED",
    "display_rule": "ESTIMATEDを常に明示しProvider/directと合算表示する場合も内訳を示す",
}
EXPECTED_TABLE_CONSTRAINTS: Final = [
    {
        "expression": "attribution_type IN ('DIRECT', 'ESTIMATED', 'UNATTRIBUTED')",
        "name": "ck_analytics_attribution_type",
    },
    {
        "expression": "allocation_ratio >= 0 AND allocation_ratio <= 1",
        "name": "ck_analytics_attribution_ratio",
    },
    {
        "expression": "confidence_score >= 0 AND confidence_score <= 100",
        "name": "ck_analytics_attribution_confidence",
    },
    {
        "expression": "status IN ('PROPOSED', 'APPROVED', 'REJECTED', 'SUPERSEDED')",
        "name": "ck_analytics_attribution_status",
    },
    {
        "expression": "jsonb_typeof(signals) = 'object'",
        "name": "ck_analytics_attribution_signals",
    },
    {
        "expression": "attribution_type = 'UNATTRIBUTED' OR article_id IS NOT NULL",
        "name": "ck_analytics_attribution_article",
    },
    {
        "expression": "(approved_by_principal_id IS NULL) = (approved_at IS NULL)",
        "name": "ck_analytics_attribution_approval",
    },
]


class AttributionEngineReferenceError(RuntimeError):
    """Stable sanitized ST-1303 reference-plan failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise AttributionEngineReferenceError(f"ST-1303 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        _fail("TYPE_MISMATCH", field)
    return cast(Mapping[str, Any], value)


def _list(value: object, field: str) -> list[Any]:
    if type(value) is not list:
        _fail("TYPE_MISMATCH", field)
    return value


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
    content = _read(root, relative, field)
    try:
        value = yaml.safe_load(content)
    except UnicodeDecodeError, yaml.YAMLError, RecursionError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


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


def _canonical_model_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError:
        _fail("MODEL_SERIALIZATION_FAILED", "contract")


def _clone(value: object) -> object:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False))
    except (
        TypeError,
        ValueError,
        UnicodeEncodeError,
        json.JSONDecodeError,
        RecursionError,
    ):
        _fail("MODEL_CLONE_FAILED", "contract")


def _contract_artifacts(contract: Mapping[str, Any]) -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    authority = _mapping(contract.get("authority"), "authority")
    for key in (
        "canonical_story",
        "integration_precedence",
        "requirement",
        "open_decision",
        "inherited_privacy_decision",
    ):
        row = _mapping(authority.get(key), f"authority.{key}")
        path = row.get("path")
        digest = row.get("sha256")
        if type(path) is not str or type(digest) is not str:
            _fail("ARTIFACT_BINDING_INVALID", f"authority.{key}")
        rows.append((Path(path), digest))
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    for name in ("st1202", "st1302"):
        dependency = _mapping(dependencies.get(name), f"dependencies.{name}")
        artifacts = _mapping(dependency.get("artifacts"), f"dependencies.{name}")
        for path, digest in artifacts.items():
            if type(digest) is not str:
                _fail("ARTIFACT_BINDING_INVALID", f"dependencies.{name}")
            rows.append((Path(path), digest))
    source_pins = _mapping(contract.get("source_pins"), "source_pins")
    for name, value in source_pins.items():
        row = _mapping(value, f"source_pins.{name}")
        path = row.get("path")
        digest = row.get("sha256")
        if type(path) is not str or type(digest) is not str:
            _fail("ARTIFACT_BINDING_INVALID", f"source_pins.{name}")
        rows.append((Path(path), digest))
    unique: dict[Path, str] = {}
    for path, digest in rows:
        previous = unique.setdefault(path, digest)
        if previous != digest:
            _fail("ARTIFACT_BINDING_CONFLICT", "input")
    return list(unique.items())


def _verify_hashes(contract: Mapping[str, Any], root: Path) -> None:
    for relative, expected in _contract_artifacts(contract):
        if _sha256(_read(root, relative, "input")) != expected:
            _fail("INPUT_HASH_DRIFT", "input")
    if _sha256(_read(root, HELPER_PATH, "helper")) != HELPER_SHA256:
        _fail("HELPER_HASH_DRIFT", "helper")


def _validate_story_requirement_and_decisions(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    story = _find_record(stories.get("stories"), "id", "ST-1303", "story")
    if story != EXPECTED_STORY or tuple(story) != tuple(EXPECTED_STORY):
        _fail("STORY_SEMANTIC_DRIFT", "story")

    content = _read(root, REQUIREMENT_PATH, "requirement").decode(
        "utf-8-sig", errors="strict"
    )
    records = list(csv.DictReader(io.StringIO(content)))
    matches = [record for record in records if record.get("requirement_id") == "FR-013"]
    if matches != [EXPECTED_REQUIREMENT]:
        _fail("REQUIREMENT_SEMANTIC_DRIFT", "requirement")

    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")
    od003 = _find_record(decisions.get("items"), "id", "OD-003", "open_decisions")
    od012 = _find_record(decisions.get("items"), "id", "OD-012", "open_decisions")
    if (
        od003.get("status") != "EXTERNAL_EVIDENCE_REQUIRED"
        or od003.get("blocking") is not True
    ):
        _fail("OPEN_DECISION_DRIFT", "OD-003")
    if (
        od012.get("status") != "HUMAN_DECISION_REQUIRED"
        or od012.get("blocking") is not True
        or od012.get("default_behavior")
        != "非必須Trackingを無効化しFirst-party最小Eventのみ"
    ):
        _fail("OPEN_DECISION_DRIFT", "OD-012")


def _validate_dependency_semantics(root: Path) -> None:
    st1202 = _read(root, ST1202_SOURCE_PATH, "st1202").decode("utf-8", errors="strict")
    for fragment in (
        "UNREGISTERED_DISABLED_HEADLESS_ST1202_PUBLIC_EVENT_INSTRUMENTATION_REQUIREMENTS_CANDIDATE",
        "'EVT-001'",
        "'EVT-002'",
        "'EVT-003'",
        "'EVT-004'",
        "'EVT-006'",
        "'EVT-012'",
        "instrumentationImplemented: false",
        "emissionEnabled: false",
        "sessionPseudonym: null",
        "events: []",
        "actions: []",
        "effects: []",
    ):
        if fragment not in st1202:
            _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1202")

    st1302 = _load_json(root, ST1302_PLAN_PATH, "st1302")
    document = _mapping(st1302.get("document"), "st1302.document")
    predecessor = _mapping(st1302.get("predecessor_binding"), "st1302.predecessor")
    required = _mapping(predecessor.get("required_semantics"), "st1302.required")
    collections = _mapping(st1302.get("collections"), "st1302.collections")
    execution = _mapping(st1302.get("execution_boundary"), "st1302.execution")
    if (
        document.get("classification")
        != "SOURCE_DERIVED_NONEXECUTABLE_PROVIDER_FACT_COMMIT_REFERENCE_PLAN"
        or document.get("executable") is not False
        or document.get("authority") != "NOT_GRANTED"
        or document.get("decision") != "NOT_READY"
        or required.get("mapping") != "UNVERIFIED"
        or required.get("facts") != "NOT_CREATED"
        or required.get("commit_capability") != "ABSENT"
        or collections.get("provider_facts") != []
        or collections.get("provider_fact_count") is not None
        or collections.get("amount_total_jpy") is not None
        or execution.get("database") != "NOT_EXECUTED"
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1302")


def _walk_mappings(value: object) -> list[Mapping[str, Any]]:
    found: list[Mapping[str, Any]] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            row = cast(dict[str, Any], current)
            found.append(row)
            stack.extend(row.values())
        elif type(current) is list:
            stack.extend(current)
    return found


def _validate_canonical_semantics(root: Path) -> None:
    policy = _load_yaml(root, ATTRIBUTION_POLICY_PATH, "policy")
    if policy.get("classes") != EXPECTED_POLICY_CLASSES:
        _fail("POLICY_CLASS_DRIFT", "policy")
    if policy.get("mvp_estimation") != EXPECTED_POLICY_ESTIMATION:
        _fail("POLICY_ESTIMATION_DRIFT", "policy")
    principles = _list(policy.get("principles"), "policy.principles")
    for required in (
        "Provider Factは変更しない",
        "推定値はProvider事実と別Table/Badge",
        "帰属不能を失敗とせずUNATTRIBUTEDで保持",
        "Method versionとInput hashを保存",
        "Revenue totalを帰属処理で増減させない",
    ):
        if required not in principles:
            _fail("POLICY_PRINCIPLE_DRIFT", "policy")

    event_catalog = _load_yaml(root, EVENT_CATALOG_PATH, "event_catalog")
    event = _find_record(event_catalog.get("events"), "id", "EVT-018", "event")
    expected_event = {
        "id": "EVT-018",
        "event_name": "attribution_run_completed",
        "source": "worker",
        "purpose": "帰属計算完了",
        "ga4_mapping": None,
        "mvp": True,
        "parameters": [
            "run_id",
            "method_version",
            "direct_count",
            "estimated_count",
            "unattributed_count",
        ],
        "prohibited_parameters": [
            "email",
            "phone",
            "raw_ip",
            "full_user_agent",
            "raw_search_query",
            "article_body",
            "source_packet_text",
            "affiliate_url_query_secret",
        ],
        "implementation_status": "NOT_STARTED",
        "runtime_verification": "NOT_EXECUTED",
    }
    if event != expected_event or tuple(event) != tuple(expected_event):
        _fail("EVENT_SEMANTIC_DRIFT", "EVT-018")

    test_catalog = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    for suite_id, purpose in (
        ("TST-007", "冪等性、状態遷移、金額、正規化の不変条件"),
        ("TST-030", "Event/GA4/GSC/Revenue/Attribution/KPIの再現"),
    ):
        suite = _find_record(test_catalog.get("suites"), "id", suite_id, "suite")
        if (
            suite.get("purpose") != purpose
            or suite.get("release_blocking") is not True
            or suite.get("implementation_status") != "NOT_STARTED"
            or suite.get("execution_status") != "NOT_EXECUTED"
        ):
            _fail("TEST_SUITE_DRIFT", suite_id)

    catalog = _load_json(root, ST0305_CATALOG_PATH, "st0305")
    tables = [
        row
        for row in _walk_mappings(catalog)
        if row.get("fully_qualified_name") == "analytics.attribution_estimate"
    ]
    if len(tables) != 1:
        _fail("ATTRIBUTION_TABLE_MISSING_OR_DUPLICATE", "st0305")
    table = tables[0]
    if (
        table.get("classification") != "RESTRICTED"
        or table.get("retention_class") != "FINANCE_7Y_PROVISIONAL"
        or table.get("check_constraints") != EXPECTED_TABLE_CONSTRAINTS
    ):
        _fail("ATTRIBUTION_TABLE_DRIFT", "st0305")

    persistence = _load_json(root, ST0308_PLAN_PATH, "st0308")
    persistence_document = _mapping(persistence.get("document"), "st0308.document")
    activation = _mapping(persistence.get("activation"), "st0308.activation")
    if (
        persistence_document.get("executable") is not False
        or activation.get("enabled") is not False
        or activation.get("runtime_eligible") is not False
        or activation.get("authority") != "NOT_GRANTED"
    ):
        _fail("PERSISTENCE_BOUNDARY_DRIFT", "st0308")

    jobs = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")
    for job in _list(jobs.get("jobs"), "job_catalog.jobs"):
        job_type = _mapping(job, "job_catalog.job").get("job_type")
        if type(job_type) is str and "attribution" in job_type.lower():
            _fail("ATTRIBUTION_JOB_UNEXPECTED", "job_catalog")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    if tuple(dependencies) != ("st1202", "st1302"):
        _fail("CONTRACT_SCHEMA_DRIFT", "dependencies")
    execution = _mapping(contract.get("execution_boundary"), "execution_boundary")
    action_counts = _mapping(execution.get("action_counts"), "action_counts")
    if tuple(action_counts) != ACTION_COUNT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "action_counts")
    if _sha256(_canonical_model_bytes(contract)) != CONTRACT_MODEL_SHA256:
        _fail("CONTRACT_MODEL_DRIFT", "contract")
    _verify_hashes(contract, root)
    _validate_story_requirement_and_decisions(root)
    _validate_dependency_semantics(root)
    _validate_canonical_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    content = _read(root, CONTRACT_PATH, "contract")
    if _sha256(content) != CONTRACT_SHA256:
        _fail("CONTRACT_BYTES_DRIFT", "contract")
    contract = _load_yaml(root, CONTRACT_PATH, "contract")
    return validate_contract(contract, root)


def _source_bindings(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    source_pins = _mapping(contract.get("source_pins"), "source_pins")
    bindings: list[dict[str, str]] = []
    for name, value in source_pins.items():
        row = _mapping(value, f"source_pins.{name}")
        bindings.append(
            {
                "name": name,
                "uri": f"repo://{row['path']}",
                "sha256": cast(str, row["sha256"]),
            }
        )
    return bindings


def reference_plan_for_root(
    contract: Mapping[str, Any], root: Path
) -> dict[str, object]:
    validated = validate_contract(contract, root)
    plan: dict[str, object] = {
        "document": _clone(validated["document"]),
        "authority": _clone(validated["authority"]),
        "provenance": {
            "source_contract": SOURCE_URI,
            "source_contract_sha256": CONTRACT_SHA256,
            "source_contract_model_sha256": CONTRACT_MODEL_SHA256,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "dependency_bindings": _clone(validated["dependencies"]),
        "source_bindings": _source_bindings(validated),
        "canonical_constraints": _clone(validated["canonical_constraints"]),
        "selection_boundary": _clone(validated["selection_boundary"]),
        "collections": _clone(validated["collections"]),
        "evaluation_boundary": _clone(validated["evaluation_boundary"]),
        "execution_boundary": _clone(validated["execution_boundary"]),
        "diagnostic_boundary": _clone(validated["diagnostic_boundary"]),
        "verification_boundary": _clone(validated["verification_boundary"]),
    }
    if tuple(plan) != PLAN_KEYS:
        _fail("PLAN_SCHEMA_DRIFT", "plan")
    return plan


def reference_plan(contract: Mapping[str, Any]) -> dict[str, object]:
    return reference_plan_for_root(contract, REPO_ROOT)


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


def _artifact_uri_rows(rows: Sequence[tuple[Path, str]]) -> list[dict[str, str]]:
    return [
        {"uri": f"repo://{path.as_posix()}", "sha256": digest} for path, digest in rows
    ]


def _manifest_bytes(
    root: Path, contract: Mapping[str, Any], reference_bytes: bytes
) -> bytes:
    dependencies = _mapping(contract["dependencies"], "dependencies")
    manifest = {
        "schema_version": "1.0.0",
        "story_id": "ST-1303",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_ATTRIBUTION_ENGINE_REFERENCE_PLAN",
        "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
        "executable": False,
        "authority": "NOT_GRANTED",
        "decision": "NOT_READY",
        "story_acceptance": False,
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
            "dependency_provenance": {
                name: {
                    "feature_commit": _mapping(value, f"dependencies.{name}")[
                        "feature_commit"
                    ],
                    "artifact_binding_commit": _mapping(value, f"dependencies.{name}")[
                        "artifact_binding_commit"
                    ],
                    "binding": _mapping(value, f"dependencies.{name}")["binding"],
                }
                for name, value in dependencies.items()
            },
            "bound_inputs": _artifact_uri_rows(_contract_artifacts(contract)),
        },
        "boundary": {
            **{
                key: None
                for key in (
                    *COUNT_KEYS,
                    *TOTAL_KEYS,
                    "method_version",
                    "input_hash",
                    "direct_provider_key",
                    "time_bucket",
                    "confidence_rule",
                    "conservation_basis",
                    "rounding_policy",
                    "correction_policy",
                    "run_id",
                    "persistence_policy",
                )
            },
            "empty_means_zero": False,
            "vacuous_pass_allowed": False,
            "action_counts": _clone(
                _mapping(contract["execution_boundary"], "execution")["action_counts"]
            ),
        },
        "verification": _clone(contract["verification_boundary"]),
    }
    try:
        return yaml.dump(
            manifest,
            Dumper=NoAliasDumper,
            sort_keys=False,
            allow_unicode=True,
        ).encode("utf-8")
    except TypeError, ValueError, UnicodeEncodeError, RecursionError, yaml.YAMLError:
        _fail("MANIFEST_SERIALIZATION_FAILED", "manifest")


def render_outputs(root: Path = REPO_ROOT) -> dict[Path, bytes]:
    contract = load_contract(root)
    reference_bytes = _json_bytes(reference_plan_for_root(contract, root))
    return {
        REFERENCE_PLAN_PATH: reference_bytes,
        MANIFEST_PATH: _manifest_bytes(root, contract, reference_bytes),
    }


def check_outputs(root: Path, expected: Mapping[Path, bytes]) -> None:
    if set(expected) != set(GENERATED_PATHS):
        _fail("GENERATED_INVENTORY_DRIFT", "output")
    for relative in GENERATED_PATHS:
        path = base._output_file(root, relative)  # noqa: SLF001
        try:
            actual = path.read_bytes()
            mode = stat.S_IMODE(path.stat().st_mode)
        except OSError:
            _fail("GENERATED_OUTPUT_UNAVAILABLE", "output")
        if actual != expected[relative]:
            _fail("GENERATED_OUTPUT_DRIFT", "output")
        if mode != 0o644:
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
        AttributionEngineReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1303 attribution-engine reference plan checked"
        if args.check
        else "ST-1303 attribution-engine reference plan generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
