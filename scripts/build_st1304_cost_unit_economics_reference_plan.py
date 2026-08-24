#!/usr/bin/env python3
"""Build the non-executable ST-1304 cost/unit-economics reference plan."""

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
    "changes/st-1304/contracts/cost-unit-economics-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1304/generated/cost-unit-economics-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1304/manifest.yaml")
GENERATOR_PATH: Final = Path(
    "scripts/build_st1304_cost_unit_economics_reference_plan.py"
)
README_PATH: Final = Path("changes/st-1304/README.md")
TEST_PATHS: Final = (
    Path("tests/st1304/conftest.py"),
    Path("tests/st1304/test_contract.py"),
    Path("tests/st1304/test_generation.py"),
    Path("tests/st1304/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "00d791a17bea96a5dc4608876c37907effe53ebb3a8f7786ca7b98823faff5b9"
)
CONTRACT_SHA256: Final = (
    "80d775e8f38744e93ecf319756ee5c2d53cd91750e9061c8902d205ee5af0fdf"
)
CONTRACT_MODEL_SHA256: Final = (
    "9467589389da990744a92c7aece1a642a701cba58611ce97bf10e1f61fc534d8"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "/home/minami/.local/share/raos-toolchains/uv/0.12.1/uv run "
    "--frozen --offline --no-cache --no-sync --no-env-file python "
    "scripts/build_st1304_cost_unit_economics_reference_plan.py"
)

STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
OPEN_DECISIONS_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
)
REQUIREMENT_PATH: Final = Path(
    "docs/canonical/00_master/RAOS_master_traceability_v1.0.csv"
)
KPI_CATALOG_PATH: Final = Path(
    "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml"
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
ST0308_PLAN_PATH: Final = Path(
    "changes/st-0308/generated/persistence-boundary.reference-plan.v1.json"
)
JOB_CATALOG_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/catalogs/job-catalog.v0.4.yaml"
)
JOB_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/jobs/finance-calculate-unit-economics-v1.schema.json"
)
EVENT_SCHEMA_PATH: Final = Path(
    "contracts/raos-v0.4/contracts/schemas/events/jp-raos-finance-unit-economics-calculated-v1.schema.json"
)
ST0706_DOMAIN_PATH: Final = Path("python/raos/domain/ai/job_orchestration.py")
ST1205_PLAN_PATH: Final = Path(
    "changes/st-1205/generated/kpi-read-model-reference-plan.v1.json"
)
ST1303_PLAN_PATH: Final = Path(
    "changes/st-1303/generated/attribution-engine-reference-plan.v1.json"
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "dependencies",
    "source_pins",
    "canonical_constraints",
    "open_decision_boundary",
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
    "open_decision_boundary",
    "selection_boundary",
    "collections",
    "evaluation_boundary",
    "execution_boundary",
    "diagnostic_boundary",
    "verification_boundary",
)
COLLECTION_KEYS: Final = (
    "ai_job_observations",
    "external_cost_facts",
    "human_work_logs",
    "attribution_allocations",
    "kpi_inputs",
    "allocation_candidates",
    "cost_allocations",
    "unit_economics_snapshots",
    "read_model_rows",
    "emitted_events",
    "writes",
)
COUNT_KEYS: Final = (
    "ai_job_observation_count",
    "external_cost_fact_count",
    "human_work_log_count",
    "attribution_allocation_count",
    "kpi_input_count",
    "allocation_candidate_count",
    "cost_allocation_count",
    "unit_economics_snapshot_count",
    "read_model_row_count",
    "emitted_event_count",
    "write_count",
)
TOTAL_KEYS: Final = (
    "confirmed_commission_total_jpy",
    "external_cost_total_jpy",
    "human_cost_total_jpy",
    "allocated_cost_total_jpy",
    "contribution_profit_total_jpy",
    "eligible_click_count",
    "qualified_session_count",
    "confirmed_epc_jpy",
    "confirmed_rpm_jpy",
)
EVALUATION_KEYS: Final = (
    "dependency_readiness",
    "cost_fact_completeness",
    "labor_cost_known",
    "budget_selected",
    "currency_normalization",
    "allocation_rule_valid",
    "cost_totals_conserved",
    "attribution_basis_visible",
    "denominator_quality",
    "contribution_profit",
    "epc",
    "rpm",
    "correction",
    "supersession",
    "idempotency",
)
EXECUTION_STATUS_KEYS: Final = (
    "cost_intake",
    "pricing",
    "currency_conversion",
    "labor_rate_application",
    "allocation",
    "calculation",
    "sql",
    "database",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "event_emission",
    "audit",
    "outbox",
    "dashboard",
    "public_projection",
    "recommendation_input",
    "authorization",
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
    "cost_intake",
    "price",
    "convert_currency",
    "apply_labor_rate",
    "allocate",
    "calculate",
    "execute_sql",
    "database",
    "repository",
    "unit_of_work",
    "transaction",
    "fake_persistence",
    "queue",
    "job",
    "emit_event",
    "audit",
    "outbox",
    "dashboard",
    "public_projection",
    "recommendation_input",
    "authorize",
    "browser",
    "provider",
    "network",
    "write",
    "external",
)
RELEVANT_KPI_IDS: Final = (
    "KPI-001",
    "KPI-002",
    "KPI-003",
    "KPI-004",
    "KPI-022",
    "KPI-023",
    "KPI-025",
)
TABLE_NAMES: Final = (
    "finance.external_cost",
    "finance.human_work_log",
    "finance.allocation_rule",
    "finance.cost_allocation",
    "finance.unit_economics_snapshot",
)

EXPECTED_STORY: Final = {
    "id": "ST-1304",
    "epic_id": "EPIC-13",
    "title": "Cost and unit economics",
    "objective": "AI/API/labor cost、EPC/RPM/profit",
    "depends_on": ["ST-0706", "ST-1205", "ST-1303"],
    "requirement_ids": ["FR-015"],
    "design_refs": [],
    "deliverables": ["cost allocation", "read models"],
    "acceptance_criteria": ["unknown labor not zero", "basis visible"],
    "test_suites": ["TST-030"],
    "priority": "P0",
    "mvp": True,
    "size": "L",
    "open_decisions": ["OD-005", "OD-009"],
    "one_pr_preferred": False,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_REQUIREMENT: Final = {
    "requirement_id": "FR-015",
    "requirement": "calculate_epc_rpm_cost_and_contribution_profit",
    "design_documents": "RAOS-ANALYTICS-001",
    "story_ids": "ST-0305;ST-1205;ST-1304",
    "test_suite_ids": "TST-008;TST-011;TST-030",
    "coverage_status": "DESIGNED_NOT_IMPLEMENTED",
}
EXPECTED_DECISIONS: Final = {
    "OD-005": {
        "topic": "human_reviewer_and_hourly_cost",
        "required_by": "GATE-1 and contribution profit",
        "owner": "Business Owner",
        "default_behavior": "公開不可、利益計算の人件費はUNKNOWN",
    },
    "OD-009": {
        "topic": "budget_and_acceptable_loss",
        "required_by": "Cloud/LLM release",
        "owner": "Business Owner",
        "default_behavior": "低い開発用上限、Production無効",
    },
}
EXPECTED_KPI_ROWS: Final = {
    "KPI-001": (
        "monthly_confirmed_commission_jpy",
        "sum(confirmed provider commission)",
    ),
    "KPI-002": (
        "monthly_confirmed_contribution_profit_jpy",
        "confirmed commission - variable external cost - editorial/update labor cost",
    ),
    "KPI-003": (
        "confirmed_epc_jpy",
        "confirmed attributed commission / eligible affiliate clicks",
    ),
    "KPI-004": (
        "confirmed_rpm_jpy",
        "confirmed attributed commission / qualified sessions * 1000",
    ),
    "KPI-022": (
        "article_update_cost_ratio",
        "article update cost / confirmed article commission",
    ),
    "KPI-023": (
        "content_payback_months",
        "initial content cost / trailing monthly confirmed contribution",
    ),
    "KPI-025": (
        "ai_cost_per_approved_article",
        "AI actual cost / approved article versions",
    ),
}


class CostUnitEconomicsReferenceError(RuntimeError):
    """Stable sanitized ST-1304 reference-plan failure."""


class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: object) -> bool:
        return True


def _fail(code: str, field: str) -> NoReturn:
    raise CostUnitEconomicsReferenceError(f"ST-1304 build failed: {code} field={field}")


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


def _contract_artifacts(contract: Mapping[str, Any]) -> list[tuple[Path, str]]:
    rows: list[tuple[Path, str]] = []
    authority = _mapping(contract.get("authority"), "authority")
    for key in (
        "canonical_story",
        "integration_precedence",
        "requirement",
        "open_decisions",
    ):
        row = _mapping(authority.get(key), f"authority.{key}")
        path, digest = row.get("path"), row.get("sha256")
        if type(path) is not str or type(digest) is not str:
            _fail("ARTIFACT_BINDING_INVALID", f"authority.{key}")
        rows.append((Path(path), digest))
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    for name in ("st0706", "st1205", "st1303"):
        dependency = _mapping(dependencies.get(name), f"dependencies.{name}")
        artifacts = _mapping(dependency.get("artifacts"), f"dependencies.{name}")
        for path, digest in artifacts.items():
            if type(digest) is not str:
                _fail("ARTIFACT_BINDING_INVALID", f"dependencies.{name}")
            rows.append((Path(path), digest))
    source_pins = _mapping(contract.get("source_pins"), "source_pins")
    for name, value in source_pins.items():
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


def _validate_story_requirement_and_decisions(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    story = _find_record(stories.get("stories"), "id", "ST-1304", "story")
    if story != EXPECTED_STORY or tuple(story) != tuple(EXPECTED_STORY):
        _fail("STORY_SEMANTIC_DRIFT", "story")
    content = _read(root, REQUIREMENT_PATH, "requirement").decode(
        "utf-8-sig", errors="strict"
    )
    matches = [
        row
        for row in csv.DictReader(io.StringIO(content))
        if row.get("requirement_id") == "FR-015"
    ]
    if matches != [EXPECTED_REQUIREMENT]:
        _fail("REQUIREMENT_SEMANTIC_DRIFT", "requirement")
    decisions = _load_yaml(root, OPEN_DECISIONS_PATH, "open_decisions")
    for decision_id, expected in EXPECTED_DECISIONS.items():
        row = _find_record(decisions.get("items"), "id", decision_id, decision_id)
        if (
            row.get("status") != "HUMAN_DECISION_REQUIRED"
            or row.get("blocking") is not True
            or any(row.get(key) != value for key, value in expected.items())
        ):
            _fail("OPEN_DECISION_DRIFT", decision_id)


def _validate_dependency_semantics(root: Path) -> None:
    st0706 = _read(root, ST0706_DOMAIN_PATH, "st0706").decode("utf-8", errors="strict")
    for fragment in (
        "actual_cost_jpy: int | None",
        "input_tokens: int | None",
        "total_tokens: int | None",
    ):
        if fragment not in st0706:
            _fail("DEPENDENCY_SEMANTIC_DRIFT", "st0706")
    st1205 = _load_json(root, ST1205_PLAN_PATH, "st1205")
    st1205_document = _mapping(st1205.get("document"), "st1205.document")
    projection = _mapping(st1205.get("catalog_projection"), "st1205.projection")
    calculation = _mapping(st1205.get("calculation_boundary"), "st1205.calculation")
    if (
        st1205_document.get("executable") is not False
        or st1205_document.get("decision") != "NOT_READY"
        or projection.get("definition_count") != 30
        or projection.get("calculation_count") != 0
        or projection.get("verified_count") != 0
        or calculation.get("inputs") != []
        or calculation.get("read_model_rows") != []
        or calculation.get("results") != []
        or calculation.get("evidence") != []
        or calculation.get("empty_means_zero") is not False
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1205")
    st1303 = _load_json(root, ST1303_PLAN_PATH, "st1303")
    st1303_document = _mapping(st1303.get("document"), "st1303.document")
    collections = _mapping(st1303.get("collections"), "st1303.collections")
    if (
        st1303_document.get("executable") is not False
        or st1303_document.get("authority") != "NOT_GRANTED"
        or st1303_document.get("decision") != "NOT_READY"
        or any(
            collections.get(key) != []
            for key in ("public_events", "provider_facts", "allocations", "runs")
        )
        or collections.get("provider_total_jpy") is not None
        or collections.get("allocated_total_jpy") is not None
        or collections.get("empty_means_zero") is not False
    ):
        _fail("DEPENDENCY_SEMANTIC_DRIFT", "st1303")


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


def _relevant_kpi_definitions(root: Path) -> list[Mapping[str, Any]]:
    catalog = _load_yaml(root, KPI_CATALOG_PATH, "kpi_catalog")
    rows = []
    for kpi_id in RELEVANT_KPI_IDS:
        row = _find_record(catalog.get("kpis"), "id", kpi_id, kpi_id)
        name, formula = EXPECTED_KPI_ROWS[kpi_id]
        if (
            row.get("name") != name
            or row.get("formula") != formula
            or row.get("design_status") != "APPROVED_FOR_IMPLEMENTATION"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("runtime_verification") != "NOT_EXECUTED"
        ):
            _fail("KPI_SEMANTIC_DRIFT", kpi_id)
        rows.append(row)
    return rows


def _validate_canonical_semantics(root: Path) -> None:
    _relevant_kpi_definitions(root)
    slices = _load_yaml(root, SLICES_PATH, "slices")
    row = _find_record(slices.get("slices"), "id", "AN-SLICE-008", "slice")
    if row != {
        "id": "AN-SLICE-008",
        "name": "Cost allocation and unit economics",
        "depends_on": ["AN-SLICE-007"],
        "deliverables": ["AI/API/labor cost", "EPC/RPM/profit"],
        "implementation_status": "NOT_STARTED",
        "runtime_verification": "NOT_EXECUTED",
    }:
        _fail("SLICE_SEMANTIC_DRIFT", "AN-SLICE-008")
    tests = _load_yaml(root, TEST_CATALOG_PATH, "test_catalog")
    suite = _find_record(tests.get("suites"), "id", "TST-030", "TST-030")
    if (
        suite.get("purpose") != "Event/GA4/GSC/Revenue/Attribution/KPIの再現"
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
    if tuple(name for name in TABLE_NAMES if name in tables) != TABLE_NAMES:
        _fail("FINANCE_TABLE_DRIFT", "st0305")
    for expected in TABLE_NAMES:
        row = tables[expected]
        if row.get("classification") != "RESTRICTED":
            _fail("FINANCE_TABLE_DRIFT", expected)
    snapshot_checks = _list(
        tables["finance.unit_economics_snapshot"].get("check_constraints"),
        "snapshot.checks",
    )
    if not any(
        type(item) is dict
        and item.get("expression")
        == "contribution_profit_jpy = confirmed_commission_jpy - external_cost_jpy - human_cost_jpy"
        for item in snapshot_checks
    ):
        _fail("FINANCE_TABLE_DRIFT", "snapshot.formula")
    persistence = _load_json(root, ST0308_PLAN_PATH, "st0308")
    activation = _mapping(persistence.get("activation"), "st0308.activation")
    if (
        _mapping(persistence.get("document"), "st0308.document").get("executable")
        is not False
        or activation.get("enabled") is not False
        or activation.get("runtime_eligible") is not False
        or activation.get("authority") != "NOT_GRANTED"
    ):
        _fail("PERSISTENCE_BOUNDARY_DRIFT", "st0308")
    jobs = _load_yaml(root, JOB_CATALOG_PATH, "job_catalog")
    job = _find_record(
        jobs.get("jobs"), "job_type", "finance.calculate_unit_economics.v1", "job"
    )
    if (
        job.get("queue") != "analytics"
        or job.get("implementation_slice") != "SLICE-021"
        or job.get("enabled") is not True
        or job.get("emits") != ["jp.raos.finance.unit_economics_calculated.v1"]
    ):
        _fail("JOB_SEMANTIC_DRIFT", "job")
    job_schema = _load_json(root, JOB_SCHEMA_PATH, "job_schema")
    if job_schema.get("title") != "finance.calculate_unit_economics.v1":
        _fail("JOB_SCHEMA_DRIFT", "job_schema")
    event_schema = _load_json(root, EVENT_SCHEMA_PATH, "event_schema")
    if event_schema.get("title") != "jp.raos.finance.unit_economics_calculated.v1":
        _fail("EVENT_SCHEMA_DRIFT", "event_schema")


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    dependencies = _mapping(contract.get("dependencies"), "dependencies")
    if tuple(dependencies) != ("st0706", "st1205", "st1303"):
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
    _validate_story_requirement_and_decisions(root)
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
    constraints = cast(dict[str, object], _clone(validated["canonical_constraints"]))
    constraints["relevant_kpi_definitions"] = _clone(_relevant_kpi_definitions(root))
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
        "canonical_constraints": constraints,
        "open_decision_boundary": _clone(validated["open_decision_boundary"]),
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
        "story_id": "ST-1304",
        "classification": "SOURCE_DERIVED_NONEXECUTABLE_COST_UNIT_ECONOMICS_REFERENCE_PLAN",
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
            **{key: None for key in (*COUNT_KEYS, *TOTAL_KEYS)},
            "hourly_cost_jpy": None,
            "allocation_rule": None,
            "calculation_version": None,
            "period_month": None,
            "source_watermarks": None,
            "rounding_policy": None,
            "persistence_policy": None,
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
        CostUnitEconomicsReferenceError,
        base.StagingDeploymentContractError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1304 cost/unit-economics reference plan checked"
        if args.check
        else "ST-1304 cost/unit-economics reference plan generated"
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return main_for_root(REPO_ROOT, argv)


if __name__ == "__main__":
    raise SystemExit(main())
