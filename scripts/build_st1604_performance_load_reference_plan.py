#!/usr/bin/env python3
"""Build the non-executable ST-1604 performance/load reference plan."""

from __future__ import annotations

import argparse
import hashlib
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
    "changes/st-1604/contracts/performance-load-reference-plan.v1.yaml"
)
REFERENCE_PLAN_PATH: Final = Path(
    "changes/st-1604/generated/performance-load-reference-plan.v1.json"
)
MANIFEST_PATH: Final = Path("changes/st-1604/manifest.yaml")
GENERATOR_PATH: Final = Path("scripts/build_st1604_performance_load_reference_plan.py")
README_PATH: Final = Path("changes/st-1604/README.md")
TEST_PATHS: Final = (
    Path("tests/st1604/conftest.py"),
    Path("tests/st1604/test_contract.py"),
    Path("tests/st1604/test_generation.py"),
    Path("tests/st1604/test_negative_cases.py"),
)
SOURCE_PATHS: Final = (CONTRACT_PATH, README_PATH, GENERATOR_PATH, *TEST_PATHS)
GENERATED_PATHS: Final = (REFERENCE_PLAN_PATH, MANIFEST_PATH)
SOURCE_URI: Final = f"repo://{CONTRACT_PATH.as_posix()}"
GENERATOR_URI: Final = f"repo://{GENERATOR_PATH.as_posix()}"
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st1604_performance_load_reference_plan.py"
)
HELPER_PATH: Final = Path("scripts/build_st1505_staging_deployment.py")
HELPER_SHA256: Final = (
    "478c70fcdec48ceca5c9d072c84e4ad3dc55f63e8ccbee0f8e09d4d78eb6fdf5"
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024

INTEGRATION_PATH: Final = Path(
    "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
)
TEST_CATALOG_PATH: Final = Path(
    "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml"
)
SLO_PATH: Final = Path("docs/canonical/06_ops/RAOS_12_slo_catalog_v1.0.yaml")
STORY_PATH: Final = Path("docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml")
ST1505_CONTRACT_PATH: Final = Path(
    "changes/st-1505/contracts/staging-deployment.v1.yaml"
)
ST1505_PLAN_PATH: Final = Path(
    "infra/terraform/staging/staging-deployment.reference-plan.v1.json"
)
ST1505_MANIFEST_PATH: Final = Path("changes/st-1505/manifest.yaml")
ST1601_PATH: Final = Path("changes/st-1601/README.md")

EXPECTED_SOURCES: Final = (
    (
        "integration",
        INTEGRATION_PATH.as_posix(),
        "540d2775ab16fd3f456673bca25f00eb3f8d58c7bb4adb30f5625551b5529e7a",
    ),
    (
        "test_catalog",
        TEST_CATALOG_PATH.as_posix(),
        "7ccbb8449118e64275c8f44a876d1a49eebb8dde23847f81c76493d6cd8de98b",
    ),
    (
        "slo_catalog",
        SLO_PATH.as_posix(),
        "320a880073e3c9d87c361fa8620e1202898ffa719e2b8e94872d185415abcdf2",
    ),
    (
        "story",
        STORY_PATH.as_posix(),
        "4adcff3f293b82160a390e5d3e5102fd0bd0f46875d09677e0ba9b230eba680d",
    ),
)
EXPECTED_PREDECESSORS: Final = (
    (
        ST1505_CONTRACT_PATH,
        "be104a13490d4c39139047e101092e1b2f3541d45c9277e2d9937915a731e2f0",
    ),
    (
        ST1505_PLAN_PATH,
        "0c607b4c207068432477db1aa2a2e9598092964dbdce470d8b537c7022eaf105",
    ),
    (
        ST1505_MANIFEST_PATH,
        "0e970c5749a8bd94fcc8ae5e695d11a4b927028fcc168838618998ac48075aeb",
    ),
    (
        ST1601_PATH,
        "9eade86a2f3f7cae147d0ca26db1be0828be09250b068ac8f78832cf36ca65ef",
    ),
)

CONTRACT_KEYS: Final = (
    "document",
    "authority",
    "predecessors",
    "test_suite_rule",
    "target_surface_defaults",
    "slo_projection_rule",
    "measurement_requirements",
    "workload_defaults",
    "resource_and_cost_defaults",
    "report_defaults",
    "activation_defaults",
    "verification_defaults",
)
PLAN_KEYS: Final = (
    "document",
    "authority",
    "provenance",
    "predecessor_bindings",
    "test_suite",
    "target_surfaces",
    "slo_context",
    "workload_definition",
    "resource_and_cost_boundaries",
    "load_report",
    "activation",
    "verification_boundary",
)
SLO_FIELDS: Final = (
    "id",
    "name",
    "scope",
    "sli",
    "target",
    "window",
    "notes",
    "status",
    "implementation_status",
    "measurement_status",
)
SURFACES: Final = ("PUBLIC", "ADMIN", "API", "WORKER")
ACTION_COUNT_KEYS: Final = (
    "load",
    "browser",
    "network",
    "credential",
    "provider",
    "external",
    "staging",
    "release",
    "production",
)
ST1505_CONTRACT_ACTION_COUNT_KEYS: Final = base.STAGING_ACTION_COUNT_NAMES
ST1505_PLAN_ACTION_COUNT_KEYS: Final = tuple(sorted(base.STAGING_ACTION_COUNT_NAMES))
EXPECTED_ST1505_PROVIDER_NEUTRAL_ADMISSION: Final[dict[str, object]] = {
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


class PerformanceLoadReferenceError(RuntimeError):
    """Stable sanitized contract or generation failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise PerformanceLoadReferenceError(f"ST-1604 build failed: {code} field={field}")


def _mapping(value: object, field: str) -> Mapping[str, Any]:
    if type(value) is not dict:
        _fail("TYPE_MISMATCH", field)
    return value


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


def _load_json(root: Path, relative: Path, field: str) -> Mapping[str, Any]:
    base._repository_regular_file(root, relative, field)  # noqa: SLF001
    return _mapping(base.load_json(root / relative), field)


def _expected_source_rows() -> list[dict[str, str]]:
    return [
        {"role": role, "uri": f"repo://{path}", "sha256": digest}
        for role, path, digest in EXPECTED_SOURCES
    ]


def _expected_predecessors() -> list[dict[str, object]]:
    return [
        {
            "story_id": "ST-1505",
            "status": "PROVIDER_NEUTRAL_ADMISSION_DISABLED_INERT_ZERO_ACTION",
            "bindings": [
                {"uri": f"repo://{path.as_posix()}", "sha256": digest}
                for path, digest in EXPECTED_PREDECESSORS[:3]
            ],
            "provider_neutral_admission": EXPECTED_ST1505_PROVIDER_NEUTRAL_ADMISSION,
        },
        {
            "story_id": "ST-1601",
            "status": "INTERFACE_AVAILABLE_NOT_CONNECTED",
            "bindings": [
                {
                    "uri": f"repo://{ST1601_PATH.as_posix()}",
                    "sha256": EXPECTED_PREDECESSORS[3][1],
                }
            ],
        },
    ]


def _validate_hashes(root: Path) -> None:
    for _role, source_path, digest in EXPECTED_SOURCES:
        if _sha256(_read(root, Path(source_path), "authority.source")) != digest:
            _fail("SOURCE_HASH_DRIFT", "authority.source")
    for predecessor_path, digest in EXPECTED_PREDECESSORS:
        if _sha256(_read(root, predecessor_path, "predecessor.binding")) != digest:
            _fail("PREDECESSOR_HASH_DRIFT", "predecessor.binding")
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


EXPECTED_STORY: Final = {
    "id": "ST-1604",
    "epic_id": "EPIC-16",
    "title": "Performance/load test",
    "objective": "public/admin/API/worker capacity",
    "depends_on": ["ST-1505", "ST-1601"],
    "requirement_ids": [],
    "design_refs": [],
    "deliverables": ["load report", "budgets"],
    "acceptance_criteria": ["SLO target or documented capacity"],
    "test_suites": ["TST-027"],
    "priority": "P0",
    "mvp": True,
    "size": "M",
    "open_decisions": [],
    "one_pr_preferred": True,
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "verification_status": "NOT_EXECUTED",
}
EXPECTED_TEST_SUITE: Final = {
    "id": "TST-027",
    "name": "Performance and load",
    "layer": "performance",
    "purpose": "Public/Admin/API/workerのSLO capacity",
    "candidate_tools": ["k6相当", "browser RUM lab"],
    "release_blocking": True,
    "environments": ["staging"],
    "owner": "Engineering",
    "design_status": "APPROVED_FOR_IMPLEMENTATION",
    "implementation_status": "NOT_STARTED",
    "execution_status": "NOT_EXECUTED",
}


def _validate_authority_semantics(root: Path) -> None:
    stories = _load_yaml(root, STORY_PATH, "story")
    _exact(_find(stories.get("stories"), "ST-1604", "story"), EXPECTED_STORY, "story")
    suites = _load_yaml(root, TEST_CATALOG_PATH, "test_suite")
    _exact(
        _find(suites.get("suites"), "TST-027", "test_suite"),
        EXPECTED_TEST_SUITE,
        "test_suite",
    )


def _assert_unset_tree(value: object, field: str) -> None:
    if value is None:
        return
    if type(value) is list:
        if value:
            _fail("PREDECESSOR_SELECTION_SET", field)
        return
    if type(value) is dict:
        for key, nested in _mapping(value, field).items():
            _assert_unset_tree(nested, f"{field}.{key}")
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


def _validate_predecessor_semantics(root: Path) -> None:
    try:
        owner_contract = _load_yaml(
            root, ST1505_CONTRACT_PATH, "predecessor.st1505.contract"
        )
        base._validate_local_safety_invariants(owner_contract)  # noqa: SLF001
        owner_model = base.StagingDeploymentModel(contract=dict(owner_contract))
        owner_plan = base.render_reference_plan(owner_model)
        _runtime, runtime_specification = base.load_and_validate_runtime_contract(root)
        local_pipeline = base.render_local_pipeline(_runtime, runtime_specification)
        local_result = base.render_local_result(runtime_specification)
        owner_manifest = base.render_manifest(
            owner_model,
            owner_plan,
            local_pipeline,
            local_result,
            runtime_specification,
            root,
        )
    except base.StagingDeploymentContractError:
        raise PerformanceLoadReferenceError(
            "ST-1604 build failed: PREDECESSOR_OWNER_VALIDATION_FAILED "
            "field=predecessor.st1505"
        ) from None
    for relative, rendered in (
        (ST1505_PLAN_PATH, owner_plan),
        (ST1505_MANIFEST_PATH, owner_manifest),
    ):
        if _read(root, relative, "predecessor.owner_output") != rendered:
            _fail("PREDECESSOR_OWNER_OUTPUT_DRIFT", "predecessor.st1505")

    plan = _load_json(root, ST1505_PLAN_PATH, "predecessor.st1505.plan")
    document = _mapping(plan.get("document"), "predecessor.document")
    if (
        document.get("story_id") != "ST-1505"
        or document.get("artifact_kind")
        != (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
            "REFERENCE_PLAN"
        )
        or document.get("executable") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st1505.plan")
    activation = _mapping(plan.get("activation"), "predecessor.activation")
    if (
        activation.get("enabled") is not False
        or activation.get("status") != "DISABLED"
        or activation.get("runtime_status") != "NOT_EXECUTED"
        or activation.get("network_access") != "FORBIDDEN"
        or activation.get("credential_access") != "FORBIDDEN"
        or activation.get("live_provider_calls") != "FORBIDDEN"
        or activation.get("external_writes") != "FORBIDDEN"
        or activation.get("staging_action") != "FORBIDDEN"
        or activation.get("release_action") != "FORBIDDEN"
        or activation.get("production_action") != "FORBIDDEN"
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.activation")
    _assert_zero_counts(
        plan.get("action_counts"),
        ST1505_PLAN_ACTION_COUNT_KEYS,
        "predecessor.plan.action_counts",
    )
    _assert_unset_tree(plan.get("selected_bindings"), "predecessor.plan.bindings")
    admission = _mapping(
        plan.get("provider_neutral_staging_admission"),
        "predecessor.plan.provider_neutral_admission",
    )
    mapping_policy = _mapping(
        admission.get("mapping_policy"),
        "predecessor.plan.provider_neutral_admission.mapping_policy",
    )
    aws_boundary = _mapping(
        admission.get("aws_reference_boundary"),
        "predecessor.plan.provider_neutral_admission.aws_reference_boundary",
    )
    observed_admission = {
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
    _exact(
        observed_admission,
        EXPECTED_ST1505_PROVIDER_NEUTRAL_ADMISSION,
        "predecessor.plan.provider_neutral_admission",
    )
    reference = _mapping(
        plan.get("reference_architecture"), "predecessor.plan.reference_architecture"
    )
    if (
        reference.get("classification")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or reference.get("default") is not False
        or reference.get("implicit_fallback") is not False
        or reference.get("selected_binding") is not False
        or reference.get("eligibility_shortcut") is not False
        or reference.get("admission_requirement") is not False
        or reference.get("evidence_substitute") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.reference_architecture")

    manifest = _load_yaml(root, ST1505_MANIFEST_PATH, "predecessor.st1505.manifest")
    manifest_boundary = _mapping(manifest.get("boundary"), "predecessor.manifest")
    if (
        manifest_boundary.get("classification")
        != (
            "SOURCE_DERIVED_NON_EXECUTABLE_PROVIDER_NEUTRAL_STAGING_ADMISSION_"
            "REFERENCE_PLAN"
        )
        or manifest_boundary.get("activation") != "DISABLED"
        or manifest_boundary.get("provider_policy")
        != "STRICT_PROVIDER_NEUTRAL_STAGING_CAPABILITY_AND_DEPENDENCY_ADMISSION"
        or manifest_boundary.get("admission_status") != "NOT_EVALUATED"
        or manifest_boundary.get("eligible") is not False
        or manifest_boundary.get("selected_profile_id") is not None
        or manifest_boundary.get("selected_provider") is not None
        or manifest_boundary.get("default_profile_id") is not None
        or manifest_boundary.get("fallback_profile_id") is not None
        or manifest_boundary.get("configured_mapping_count") != 0
        or manifest_boundary.get("required_capability_count") != 13
        or manifest_boundary.get("aws_reference_only") is not True
        or manifest_boundary.get("aws_reference_role")
        != "CURRENT_CANONICAL_REFERENCE_ARCHITECTURE_ONLY"
        or manifest_boundary.get("canonical_story_deliverables")
        != ("CANONICAL_STORY_DELIVERABLES_PRESERVED_NOT_ERASED_REPLACED_OR_COMPLETED")
        or manifest_boundary.get("portable_implementation_paths")
        != "ADDITIONAL_PORTABLE_IMPLEMENTATION_PATHS"
        or manifest_boundary.get("aws_reference_selected_binding") is not False
    ):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.manifest")
    _assert_zero_counts(
        manifest_boundary.get("action_counts"),
        ST1505_CONTRACT_ACTION_COUNT_KEYS,
        "predecessor.manifest.action_counts",
    )

    telemetry_text = _read(root, ST1601_PATH, "predecessor.st1601").decode(
        "utf-8", errors="strict"
    )
    required = (
        "one inward sink port",
        "does not install or configure OpenTelemetry",
        "SLOs owned by ST-1602",
    )
    if any(fragment not in telemetry_text for fragment in required):
        _fail("PREDECESSOR_SEMANTIC_DRIFT", "predecessor.st1601")


def _project_slos(root: Path) -> list[dict[str, object]]:
    catalog = _load_yaml(root, SLO_PATH, "slo_catalog")
    if tuple(catalog) != ("document", "slos"):
        _fail("CATALOG_SCHEMA_DRIFT", "slo_catalog")
    _exact(
        catalog["document"],
        {
            "id": "RAOS-OPS-SLO-001",
            "version": "1.0",
            "note": "Targets are provisional until baseline/load/recovery measurements.",
        },
        "slo_catalog.document",
    )
    rows = _list(catalog["slos"], "slo_catalog.slos")
    if len(rows) != 14:
        _fail("CATALOG_COUNT_DRIFT", "slo_catalog.slos")
    projected: list[dict[str, object]] = []
    for index, raw in enumerate(rows, start=1):
        row = _mapping(raw, "slo_catalog.row")
        if tuple(row) != SLO_FIELDS or row.get("id") != f"SLO-{index:03d}":
            _fail("CATALOG_ROW_DRIFT", "slo_catalog.row")
        if (
            row.get("status") != "PROVISIONAL_TARGET"
            or row.get("implementation_status") != "NOT_STARTED"
            or row.get("measurement_status") != "NOT_EXECUTED"
            or type(row.get("target")) is not str
            or not row.get("target")
            or type(row.get("window")) is not str
            or not row.get("window")
        ):
            _fail("CATALOG_SEMANTIC_DRIFT", "slo_catalog.row")
        projected.append(dict(row))
    return projected


EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST1604-PERFORMANCE-LOAD-REFERENCE-PLAN-001",
    "version": "1.0.0",
    "story_id": "ST-1604",
    "classification": "SOURCE_DERIVED_NON_EXECUTABLE_PERFORMANCE_LOAD_REFERENCE_PLAN",
    "status": "LOCAL_IMPLEMENTATION_CANDIDATE",
    "executable": False,
    "interface_only": True,
    "decision": "NOT_READY",
    "story_acceptance": False,
    "production_eligible": False,
    "approval": None,
    "effective_canonical_status": "UNCHANGED",
}
EXPECTED_TEST_RULE: Final = {
    "suite_id": "TST-027",
    "selected_tool": None,
    "runner": None,
    "version": None,
    "executor": None,
    "selected_environment": None,
    "release_evidence_status": "NOT_EXECUTED",
    "release_evidence": None,
}
EXPECTED_SURFACE_DEFAULTS: Final = {
    "ordered_surfaces": list(SURFACES),
    "configuration_status": "NOT_CONFIGURED",
    "endpoint": None,
    "protocol": None,
    "authentication": None,
    "scenarios": [],
    "scenario_mix": [],
    "fixtures": [],
    "artifacts": [],
    "deployment": None,
}
EXPECTED_SLO_RULE: Final = {
    "exact_count": 14,
    "preserve_catalog_order": True,
    "selection_status": "NOT_DEFINED_IN_CANONICAL",
    "selected_slo_ids": [],
    "evaluations": [],
    "targets_met": [],
    "capacities": [],
}
EXPECTED_MEASUREMENTS: Final = {
    "dimensions": ["P95", "P99", "ERRORS", "QUEUE_AGE", "DB_CONNECTIONS", "COST"],
    "status": "REQUIRED_NOT_MEASURED",
    "values": [],
    "evidence": [],
}
EXPECTED_WORKLOAD: Final[dict[str, object]] = {
    "concurrency": None,
    "duration": None,
    "ramp": None,
    "arrival_rate": None,
    "request_count": None,
    "worker_job_count": None,
    "dataset": None,
    "random_seed": None,
    "headers": [],
    "payloads": [],
}
EXPECTED_RESOURCE_COST: Final[dict[str, object]] = {
    "cpu_cap": None,
    "memory_cap": None,
    "db_connection_cap": None,
    "queue_depth_cap": None,
    "cost_cap": None,
    "currency": None,
    "stop_conditions": [],
    "scale_caps": [],
    "unset_cap_interpretation": "EXECUTION_NOT_PERMITTED_NOT_ZERO",
    "execution_permitted": False,
}
EXPECTED_REPORT: Final[dict[str, object]] = {
    "status": "NOT_EXECUTED",
    "started_at": None,
    "finished_at": None,
    "summary": None,
    "results": [],
    "metrics": [],
    "errors": [],
    "artifacts": [],
    "capacity_claim": None,
    "slo_target_claim": None,
    "empty_interpretation": "NO_EVIDENCE_COLLECTED_NOT_ZERO_RESULTS",
}
EXPECTED_ACTIVATION: Final = {
    "enabled": False,
    "status": "DISABLED",
    "load_execution": "FORBIDDEN",
    "browser_execution": "FORBIDDEN",
    "network_access": "FORBIDDEN",
    "credential_access": "FORBIDDEN",
    "provider_access": "FORBIDDEN",
    "external_actions": "FORBIDDEN",
    "staging_action": "FORBIDDEN",
    "release_action": "FORBIDDEN",
    "production_action": "FORBIDDEN",
    "action_counts": {name: 0 for name in ACTION_COUNT_KEYS},
}
EXPECTED_VERIFICATION: Final = {
    "formal_tst_027": "NOT_EXECUTED",
    "actual_load": "NOT_EXECUTED",
    "browser_rum": "NOT_EXECUTED",
    "telemetry_backend": "NOT_EXECUTED",
    "staging": "NOT_EXECUTED",
    "release": "NOT_EXECUTED",
    "production": "NOT_EXECUTED",
    "decision": "NOT_READY",
    "approval": None,
    "story_acceptance": False,
    "production_eligible": False,
    "effective_canonical_status": "UNCHANGED",
}


def validate_contract(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> Mapping[str, Any]:
    if tuple(contract) != CONTRACT_KEYS:
        _fail("CONTRACT_SCHEMA_DRIFT", "contract")
    _exact(contract["document"], EXPECTED_DOCUMENT, "document")
    authority = _mapping(contract["authority"], "authority")
    if tuple(authority) != ("precedence", "sources"):
        _fail("CONTRACT_SCHEMA_DRIFT", "authority")
    _exact(
        authority["precedence"],
        "CANONICAL_INTEGRATION_THEN_STORY_THEN_TEST_AND_SLO_CATALOGS",
        "authority.precedence",
    )
    _exact(authority["sources"], _expected_source_rows(), "authority.sources")
    _exact(contract["predecessors"], _expected_predecessors(), "predecessors")
    _exact(contract["test_suite_rule"], EXPECTED_TEST_RULE, "test_suite_rule")
    _exact(
        contract["target_surface_defaults"],
        EXPECTED_SURFACE_DEFAULTS,
        "target_surface_defaults",
    )
    _exact(contract["slo_projection_rule"], EXPECTED_SLO_RULE, "slo_projection_rule")
    _exact(
        contract["measurement_requirements"],
        EXPECTED_MEASUREMENTS,
        "measurement_requirements",
    )
    _exact(contract["workload_defaults"], EXPECTED_WORKLOAD, "workload_defaults")
    _exact(
        contract["resource_and_cost_defaults"],
        EXPECTED_RESOURCE_COST,
        "resource_and_cost_defaults",
    )
    _exact(contract["report_defaults"], EXPECTED_REPORT, "report_defaults")
    _exact(contract["activation_defaults"], EXPECTED_ACTIVATION, "activation_defaults")
    _exact(
        contract["verification_defaults"],
        EXPECTED_VERIFICATION,
        "verification_defaults",
    )
    _validate_hashes(root)
    _validate_authority_semantics(root)
    _validate_predecessor_semantics(root)
    return contract


def load_contract(root: Path = REPO_ROOT) -> Mapping[str, Any]:
    return validate_contract(_load_yaml(root, CONTRACT_PATH, "contract"), root)


def reference_plan(
    contract: Mapping[str, Any], root: Path = REPO_ROOT
) -> dict[str, Any]:
    slos = _project_slos(root)
    surface_defaults = _mapping(
        contract["target_surface_defaults"], "target_surface_defaults"
    )
    target_surfaces = [
        {
            "surface": surface,
            "configuration_status": surface_defaults["configuration_status"],
            "endpoint": surface_defaults["endpoint"],
            "protocol": surface_defaults["protocol"],
            "authentication": surface_defaults["authentication"],
            "scenarios": surface_defaults["scenarios"],
            "scenario_mix": surface_defaults["scenario_mix"],
            "fixtures": surface_defaults["fixtures"],
            "artifacts": surface_defaults["artifacts"],
            "deployment": surface_defaults["deployment"],
        }
        for surface in SURFACES
    ]
    rule = _mapping(contract["slo_projection_rule"], "slo_projection_rule")
    test_rule = _mapping(contract["test_suite_rule"], "test_suite_rule")
    plan: dict[str, Any] = {
        "document": dict(_mapping(contract["document"], "document")),
        "authority": contract["authority"],
        "provenance": {
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
        },
        "predecessor_bindings": contract["predecessors"],
        "test_suite": {
            **EXPECTED_TEST_SUITE,
            "selected_tool": test_rule["selected_tool"],
            "runner": test_rule["runner"],
            "version": test_rule["version"],
            "executor": test_rule["executor"],
            "selected_environment": test_rule["selected_environment"],
            "release_evidence_status": test_rule["release_evidence_status"],
            "release_evidence": test_rule["release_evidence"],
        },
        "target_surfaces": target_surfaces,
        "slo_context": {
            "coverage": {"projected": 14, "canonical": 14},
            "slos": slos,
            "selection_status": rule["selection_status"],
            "selected_slo_ids": rule["selected_slo_ids"],
            "evaluations": rule["evaluations"],
            "targets_met": rule["targets_met"],
            "capacities": rule["capacities"],
            "measurement_requirements": contract["measurement_requirements"],
        },
        "workload_definition": contract["workload_defaults"],
        "resource_and_cost_boundaries": contract["resource_and_cost_defaults"],
        "load_report": contract["report_defaults"],
        "activation": contract["activation_defaults"],
        "verification_boundary": {
            "projection_coverage": "14/14 SLO",
            **dict(
                _mapping(contract["verification_defaults"], "verification_defaults")
            ),
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
            "id": "RAOS-ST1604-PERFORMANCE-LOAD-REFERENCE-MANIFEST-001",
            "version": "1.0.0",
            "story_id": "ST-1604",
            "source_contract": SOURCE_URI,
            "generated_by": GENERATOR_URI,
            "generation_command": GENERATION_COMMAND,
        },
        "provenance": {
            "contract_sha256": _sha256(_read(root, CONTRACT_PATH, "contract")),
            "authority_inputs": _expected_source_rows(),
            "predecessor_inputs": [
                {"uri": f"repo://{path.as_posix()}", "sha256": digest}
                for path, digest in EXPECTED_PREDECESSORS
            ],
            "implementation_helper": {
                "uri": f"repo://{HELPER_PATH.as_posix()}",
                "sha256": HELPER_SHA256,
            },
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
            "interface_only": True,
            "activation": "DISABLED",
            "execution_permitted": False,
            "selected_tool": None,
            "selected_environment": None,
            "selected_slo_ids": [],
            "formal_tst_027": "NOT_EXECUTED",
            "actual_load": "NOT_EXECUTED",
            "browser_rum": "NOT_EXECUTED",
            "telemetry_backend": "NOT_EXECUTED",
            "staging": "NOT_EXECUTED",
            "release": "NOT_EXECUTED",
            "production": "NOT_EXECUTED",
            "story_acceptance": False,
            "production_eligible": False,
            "effective_canonical_status": "UNCHANGED",
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
    except (PerformanceLoadReferenceError, base.StagingDeploymentContractError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        "ST-1604 performance/load reference plan checked"
        if args.check
        else "ST-1604 performance/load reference plan generated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
