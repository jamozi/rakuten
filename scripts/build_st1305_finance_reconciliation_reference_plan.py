#!/usr/bin/env python3
"""Build the non-executable ST-1305 finance reconciliation reference plan."""

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
    "changes/st-1305/contracts/finance-reconciliation-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1305/generated/finance-reconciliation-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1305/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1305_finance_reconciliation_reference_plan.py"
)
README_PATH: Final = Path("changes/st-1305/README.md")
TEST_PATHS: Final = (
    Path("tests/st1305/conftest.py"),
    Path("tests/st1305/test_contract.py"),
    Path("tests/st1305/test_generation.py"),
    Path("tests/st1305/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "ed557f514da1bcf05a2946cc776cb944062be0c920c7b5b8a851d42f19adc5d5"
)
CONTRACT_SHA256: Final = (
    "e17ed196436835871137f9f61c4c4be71d90e872fdac6abc1baa2eac41883fd3"
)
CONTRACT_MODEL_SHA256: Final = (
    "bbabc371691f335ca2bff570f9b8dbcae93b0f4bea204b2375bfae4fe1e51326"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run "
    "--frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1305_finance_reconciliation_reference_plan.py"
)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
ATTRIBUTION_POLICY_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"
)
SLICES_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_implementation_slices_v1.0.yaml"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
ST0305_CATALOG_PATH: Final = Path(
    "changes/st-0305/generated/publication-analytics-finance-catalog.v1.json"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
REVENUE_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/finance-commit-revenue-import-v1.schema.json"
)
UNIT_ECONOMICS_JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/finance-calculate-unit-economics-v1.schema.json"
)
ST1304_PLAN_PATH: Final = Path(
    "changes/st-1304/generated/cost-unit-economics-reference-plan.v1.json"
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "dependencies",
    "source_pins",
    "canonical_constraints",
    "inherited_open_decision_boundary",
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
    "inherited_open_decision_boundary",
    "selection_boundary",
    "collections",
    "evaluation_boundary",
    "execution_boundary",
    "diagnostic_boundary",
    "verification_boundary",
)
COLLECTION_KEYS: Final = (
    "provider_reports",
    "source_files",
    "revenue_import_batches",
    "canonical_rows",
    "provider_facts",
    "attribution_allocations",
    "external_cost_facts",
    "human_work_logs",
    "cost_allocations",
    "unit_economics_snapshots",
    "reconciliation_candidates",
    "total_comparisons",
    "exceptions",
    "reports",
    "evidence_artifacts",
    "approvals",
    "audit_records",
    "jobs",
    "emitted_events",
    "writes",
)
COUNT_KEYS: Final = (
    "provider_report_count",
    "source_file_count",
    "revenue_import_batch_count",
    "canonical_row_count",
    "provider_fact_count",
    "attribution_allocation_count",
    "external_cost_fact_count",
    "human_work_log_count",
    "cost_allocation_count",
    "unit_economics_snapshot_count",
    "reconciliation_candidate_count",
    "total_comparison_count",
    "exception_count",
    "report_count",
    "evidence_artifact_count",
    "approval_count",
    "audit_record_count",
    "job_count",
    "emitted_event_count",
    "write_count",
)
TOTAL_KEYS: Final = (
    "provider_generated_total_jpy",
    "provider_confirmed_total_jpy",
    "provider_cancelled_total_jpy",
    "canonical_generated_total_jpy",
    "canonical_confirmed_total_jpy",
    "canonical_cancelled_total_jpy",
    "attribution_allocated_total_jpy",
    "attribution_unattributed_total_jpy",
    "external_cost_total_jpy",
    "human_cost_total_jpy",
    "allocated_cost_total_jpy",
    "contribution_profit_total_jpy",
)
EVALUATION_KEYS: Final = (
    "dependency_readiness",
    "source_integrity",
    "file_hash_uniqueness",
    "row_count",
    "status_amount_totals",
    "currency",
    "period",
    "duplicate_provider_row",
    "dry_run_to_commit_hash_equality",
    "provider_to_canonical_total",
    "attribution_conservation",
    "cost_allocation_completeness",
    "denominator_quality",
    "exception_completeness",
    "approval",
    "audit",
    "evidence",
    "idempotency",
    "retention",
)
EXECUTION_STATUS_KEYS: Final = (
    "provider_report_intake",
    "csv_intake",
    "file_scan",
    "parsing",
    "schema_mapping",
    "dry_run",
    "canonical_commit",
    "reconciliation",
    "attribution",
    "cost_allocation",
    "unit_economics_calculation",
    "exception_workflow",
    "report_generation",
    "evidence_creation",
    "approval",
    "authorization",
    "step_up",
    "audit",
    "retention",
    "sql",
    "database",
    "migration",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "event_emission",
    "outbox",
    "api",
    "ui",
    "public_projection",
    "recommendation_input",
    "browser",
    "provider",
    "network",
    "runtime",
    "live",
    "ci",
    "staging",
    "release",
    "production",
)
ACTION_COUNT_KEYS: Final = (
    "provider_report_intake",
    "csv_intake",
    "file_scan",
    "parse",
    "map_schema",
    "dry_run",
    "commit",
    "reconcile",
    "attribute",
    "allocate_cost",
    "calculate_unit_economics",
    "handle_exception",
    "generate_report",
    "create_evidence",
    "approve",
    "authorize",
    "step_up",
    "audit",
    "enforce_retention",
    "execute_sql",
    "database",
    "migrate",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "emit_event",
    "outbox",
    "api",
    "ui",
    "public_projection",
    "recommendation_input",
    "browser",
    "provider",
    "network",
    "write",
    "external",
)
TABLE_NAMES: Final = (
    "finance.revenue_import",
    "finance.commission_event",
    "finance.cost_allocation",
    "finance.unit_economics_snapshot",
)
EXPECTED_RECONCILIATION_DIMENSIONS: Final = (
    "file_hash_uniqueness",
    "row_count",
    "generated_confirmed_cancelled_amount_totals",
    "currency",
    "period",
    "duplicate_provider_row",
    "dry_run_to_commit_hash_equality",
)
EXPECTED_POLICY_ROWS: Final = (
    "file hash uniqueness",
    "row count",
    "generated/confirmed/cancelled amount totals",
    "currency",
    "period",
    "duplicate provider row",
    "dry run to commit hash equality",
)
EXPECTED_STORY: Final = {
    "id": "ST-1305",
    "epic_id": "EPIC-13",
    "title": "Finance reconciliation report",
    "objective": "Provider/Canonical/Attribution/Costを照合",
    "depends_on": ["ST-1304"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["report/evidence"],
    "acceptance_criteria": ["batch totals and exceptions"],
    "test_suites": ["TST-030"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_DECISIONS: Final = {
    "OD-003": (
        "EXTERNAL_EVIDENCE_REQUIRED",
        "Synthetic fixtureのみ。実成果帰属を未検証表示",
    ),
    "OD-005": ("HUMAN_DECISION_REQUIRED", "公開不可、利益計算の人件費はUNKNOWN"),
    "OD-009": ("HUMAN_DECISION_REQUIRED", "低い開発用上限、Production無効"),
    "OD-014": ("HUMAN_DECISION_REQUIRED", "自動削除Jobは無効、最小収集"),
}


class FinanceReconciliationReferenceError(RuntimeError):
    """Stable sanitized ST-1305 reference-plan failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise FinanceReconciliationReferenceError(
        f"ST-1305 build failed: {code} field={field}"
    )


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
        content = cast(bytes, physical.read_bytes())
    except OSError:
        _fail("FILE_UNAVAILABLE", field)
    if len(content) > MAX_SOURCE_BYTES:
        _fail("FILE_SIZE_LIMIT", field)
    return content


def _load_yaml(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    try:
        value = yaml.safe_load(_read(root, relative, field))
    except UnicodeDecodeError, yaml.YAMLError, RecursionError:
        _fail("YAML_INVALID", field)
    return _mapping(value, field)


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    try:
        value = json.loads(_read(root, relative, field))
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
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
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


def _contract_artifacts(contract: Mapping[str, Any]) -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    authority = _mapping(contract.get("authority"), "authority")
    for key in ("canonical_story", "integration_precedence", "open_decisions"):
        row = _mapping(authority.get(key), f"authority.{key}")
        path, digest = row.get("path"), row.get("sha256")
        if type(path) is not str or type(digest) is not str:
            _fail("ARTIFACT_BINDING_INVALID", f"authority.{key}")
        rows.append((Path(path), digest))
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    dependency = _mapping(dependencies.get("st1304"), "dependencies.st1304")
    for path, digest in _mapping(
        dependency.get("artifacts"), "dependencies.st1304.artifacts"
    ).items():
        if type(digest) is not str:
            _fail("ARTIFACT_BINDING_INVALID", "dependencies.st1304")
        rows.append((Path(path), digest))
    for name, value in _mapping(contract.get("source_pins"), "source_pins").items():
        row = _mapping(value, f"source_pins.{name}")
        path, digest = row.get("path"), row.get("sha256")
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


def _validate_story_and_decisions(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    story = _find_record(stories.get("stories"), "id", "ST-1305", "story")
    if story != EXPECTED_STORY or tuple(story) != tuple(EXPECTED_STORY):
        _fail("STORY_SEMANTIC_DRIFT", "story")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")
    for decision_id, (status, default) in EXPECTED_DECISIONS.items():
        row = _find_record(decisions.get("items"), "id", decision_id, decision_id)
        if (
            row.get("status") != status
            or row.get("default_behavior") != default
            or row.get("blocking") is not True
        ):
            _fail("OPEN_DECISION_DRIFT", decision_id)


def _validate_dependency_semantics(root: Path) -> None:
    plan = _load_json(root, ST1304_PLAN_PATH, "st1304")
    document = _mapping(plan.get("document"), "st1304.document")
    collections = _mapping(plan.get("collections"), "st1304.collections")
    execution = _mapping(plan.get("execution_boundary"), "st1304.execution")
    if (
        document.get("classification")
        != "SOURCE_DERIVED_NONEXECUTABLE_COST_UNIT_ECONOMICS_REFERENCE_PLAN"
        or document.get("executable") is not False
        or document.get("authority") != "NOT_GRANTED"
        or document.get("decision") != "NOT_READY"
        or any(
            collections.get(key) != []
            for key in (
                "external_cost_facts",
                "human_work_logs",
                "attribution_allocations",
                "cost_allocations",
                "unit_economics_snapshots",
                "read_model_rows",
                "emitted_events",
                "writes",
            )
        )
        or any(
            collections.get(key) is not None
            for key in (
                "confirmed_commission_total_jpy",
                "external_cost_total_jpy",
                "human_cost_total_jpy",
                "contribution_profit_total_jpy",
            )
        )
        or collections.get("empty_means_zero") is not False
        or execution.get("sql") != "NOT_EXECUTED"
        or execution.get("database") != "NOT_EXECUTED"
        or execution.get("runtime") != "NOT_EXECUTED"
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1304")


def _validate_canonical_semantics(root: Path) -> None:
    policy = _load_yaml(root, ATTRIBUTION_POLICY_PATH, "attribution_policy")
    if (
        tuple(_list(policy.get("reconciliation"), "reconciliation"))
        != EXPECTED_POLICY_ROWS
    ):
        _fail("RECONCILIATION_VOCABULARY_DRIFT", "attribution_policy")
    slices = _load_yaml(root, SLICES_PATH, "slices")
    row = _find_record(slices.get("slices"), "id", "AN-SLICE-010", "slice")
    if (
        row.get("name") != "Analytics privacy and validation"
        or row.get("deliverables")
        != ["PII scan", "consent test", "provider reconciliation", "late arrival"]
        or row.get("implementation_status") != "NOT_STARTED"
        or row.get("runtime_verification") != "NOT_EXECUTED"
    ):
        _fail("SLICE_SEMANTIC_DRIFT", "AN-SLICE-010")
    tests = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    suite = _find_record(tests.get("suites"), "id", "TST-030", "TST-030")
    if (
        suite.get("name") != "Analytics reconciliation"
        or suite.get("purpose") != "Event/GA4/GSC/Revenue/Attribution/KPIの再現"
        or suite.get("candidate_tools") != ["fixtures", "SQL assertions"]
        or suite.get("release_blocking") is not True
        or suite.get("environments") != ["CI", "staging"]
        or suite.get("implementation_status") != "NOT_STARTED"
        or suite.get("execution_status") != "NOT_EXECUTED"
    ):
        _fail("TEST_SUITE_DRIFT", "TST-030")
    catalog = _load_json(root, ST0305_CATALOG_PATH, "st0305")
    tables = {
        cast(str, item.get("fully_qualified_name")): item
        for item in _walk_mappings(catalog)
        if item.get("fully_qualified_name") in TABLE_NAMES
    }
    expected_patterns = {
        "finance.revenue_import": "MUTABLE",
        "finance.commission_event": "APPEND_ONLY",
        "finance.cost_allocation": "APPEND_ONLY",
        "finance.unit_economics_snapshot": "LIFECYCLE",
    }
    if tuple(name for name in TABLE_NAMES if name in tables) != TABLE_NAMES:
        _fail("FINANCE_TABLE_DRIFT", "st0305")
    for name, pattern in expected_patterns.items():
        if (
            tables[name].get("classification") != "RESTRICTED"
            or tables[name].get("write_pattern") != pattern
        ):
            _fail("FINANCE_TABLE_DRIFT", name)
    jobs = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")
    for job_type, schema_path in (
        ("finance.commit_revenue_import.v1", REVENUE_JOB_SCHEMA_PATH),
        ("finance.calculate_unit_economics.v1", UNIT_ECONOMICS_JOB_SCHEMA_PATH),
    ):
        job = _find_record(jobs.get("jobs"), "job_type", job_type, job_type)
        if job.get("queue") != "analytics" or job.get("enabled") is not True:
            _fail("JOB_SEMANTIC_DRIFT", job_type)
        if _load_json(root, schema_path, job_type).get("title") != job_type:
            _fail("JOB_SCHEMA_DRIFT", job_type)


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    if tuple(dependencies) != ("st1304",):
        _fail("CONTRACT_SCHEMA_DRIFT", "dependencies")
    collections = _mapping(contract.get("collections"), "collections")
    if tuple(collections) != (
        *COLLECTION_KEYS,
        *COUNT_KEYS,
        *TOTAL_KEYS,
        "empty_means_zero",
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "collections")
    evaluations = _mapping(contract.get("evaluation_boundary"), "evaluation_boundary")
    if tuple(evaluations) != (*EVALUATION_KEYS, "vacuous_pass_allowed"):
        _fail("CONTRACT_SCHEMA_DRIFT", "evaluation_boundary")
    execution = _mapping(contract.get("execution_boundary"), "execution_boundary")
    if tuple(execution) != (
        *EXECUTION_STATUS_KEYS,
        "action_counts",
        "external_actions",
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "execution_boundary")
    if (
        tuple(_mapping(execution.get("action_counts"), "action_counts"))
        != ACTION_COUNT_KEYS
    ):
        _fail("CONTRACT_SCHEMA_DRIFT", "action_counts")
    if _sha256(_canonical_model_bytes(contract)) != CONTRACT_MODEL_SHA256:
        _fail("CONTRACT_MODEL_DRIFT", "contract")
    _verify_hashes(contract, root)
    _validate_story_and_decisions(root)
    _validate_dependency_semantics(root)
    _validate_canonical_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    content = _read(root, CONTRACT_PATH, "contract")
    if _sha256(content) != CONTRACT_SHA256:
        _fail("CONTRACT_BYTES_DRIFT", "contract")
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def _source_bindings(contract: Mapping[str, Any]) -> list[dict[str, str]]:
    bindings = []
    for name, value in _mapping(contract.get("source_pins"), "source_pins").items():
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
        "inherited_open_decision_boundary": _clone(
            validated["inherited_open_decision_boundary"]
        ),
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
    dependency = _mapping(
        _mapping(contract["dependencies"], "dependencies")["st1304"], "st1304"
    )
    manifest = {
        "schema_version": "1.0.0",
        "story_id": "ST-1305",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_FINANCE_RECONCILIATION_REFERENCE_PLAN",
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
                "st1304": {
                    "feature_commit": dependency["feature_commit"],
                    "artifact_binding_commit": dependency["artifact_binding_commit"],
                    "binding": dependency["binding"],
                }
            },
            "bound_inputs": _artifact_uri_rows(_contract_artifacts(contract)),
        },
        "boundary": {
            **{key: None for key in (*COUNT_KEYS, *TOTAL_KEYS)},
            "provider_report_schema": None,
            "revenue_import_batch_identity": None,
            "reconciliation_tolerance": None,
            "rounding_policy": None,
            "exception_schema": None,
            "approval_policy": None,
            "audit_policy": None,
            "evidence_format": None,
            "retention_policy": None,
            "labor_cost_state": "UNKNOWN",
            "unknown_labor_is_zero": False,
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
            manifest, Dumper=NoAliasDumper, sort_keys=False, allow_unicode=True
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
        FinanceReconciliationReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1305 finance reconciliation reference plan checked"
        if args.check
        else "ST-1305 finance reconciliation reference plan generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
