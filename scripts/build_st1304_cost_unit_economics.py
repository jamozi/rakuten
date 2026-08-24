#!/usr/bin/env python3
"""Build the deterministic ST-1304 V2 recorded unit-economics projection."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Final, NoReturn, cast

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
GENERATOR_PATH: Final = Path("scripts/build_st1304_cost_unit_economics.py")
CONTRACT_PATH: Final = Path(
    "changes/st-1304/contracts/cost-unit-economics-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1304/fixtures/cost-unit-economics-recorded.synthetic.v2.json"
)
ATTRIBUTION_FIXTURE_PATH: Final = Path(
    "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1304/generated/cost-unit-economics-recorded.v2.json"
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1304/PREFLIGHT-v2.md"),
    Path("changes/st-1304/README-v2.md"),
    Path("python/raos/domain/finance/unit_economics.py"),
    Path("python/raos/ports/unit_economics.py"),
    Path("python/raos/application/finance/unit_economics.py"),
    Path("python/raos/adapters/recorded_unit_economics.py"),
    GENERATOR_PATH,
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
TOP_LEVEL_KEYS: Final = (
    "document",
    "source_bindings",
    "open_decision_boundary",
    "input_contract",
    "cost_contract",
    "reward_contract",
    "calculation_contract",
    "authority_boundary",
    "recorded_fixture",
    "verification_boundary",
)
SOURCE_BINDING_KEYS: Final = (
    "canonical_story",
    "integration_precedence",
    "open_decisions",
    "analytics_design",
    "kpi_catalog",
    "attribution_policy",
    "test_catalog",
    "security_design",
    "data_classification",
    "security_controls",
    "threat_register",
    "st0706_cost_boundary",
    "st1205_runtime",
    "st1205_projection",
    "st1303_runtime",
    "st1303_projection",
    "st1303_fixture",
    "five_slot_measurement",
)
SOURCE_BINDING_PATHS: Final = {
    "canonical_story": "docs/canonical/07_backlog/RAOS_13_story_backlog_v1.0.yaml",
    "integration_precedence": (
        "docs/canonical/01_integration/RAOS_07_integration_design_v1.0.md"
    ),
    "open_decisions": (
        "docs/canonical/01_integration/RAOS_07_open_decisions_v1.0.yaml"
    ),
    "analytics_design": (
        "docs/canonical/03_analytics/RAOS_09_analytics_attribution_design_v1.0.md"
    ),
    "kpi_catalog": "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml",
    "attribution_policy": (
        "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"
    ),
    "test_catalog": "docs/canonical/05_test/RAOS_11_test_suite_catalog_v1.0.yaml",
    "security_design": (
        "docs/canonical/04_security/RAOS_10_security_privacy_design_v1.0.md"
    ),
    "data_classification": (
        "docs/canonical/04_security/RAOS_10_data_classification_v1.0.yaml"
    ),
    "security_controls": (
        "docs/canonical/04_security/RAOS_10_security_control_catalog_v1.0.yaml"
    ),
    "threat_register": ("docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml"),
    "st0706_cost_boundary": "changes/st-0706/generated/durable-ai-job-queue.v2.json",
    "st1205_runtime": "changes/st-1205/contracts/kpi-read-model.v2.yaml",
    "st1205_projection": "changes/st-1205/generated/kpi-read-model.v2.json",
    "st1303_runtime": "changes/st-1303/contracts/attribution-engine-runtime.v2.yaml",
    "st1303_projection": (
        "changes/st-1303/generated/attribution-engine-recorded.v2.json"
    ),
    "st1303_fixture": (
        "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
    ),
    "five_slot_measurement": (
        "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
    ),
}


class UnitEconomicsBuildError(RuntimeError):
    """Sanitized owner-build failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise UnitEconomicsBuildError(
        f"ST-1304 build failed: {code} field={field}"
    ) from None


class UniqueSafeLoader(yaml.SafeLoader):
    pass


def _construct_mapping(
    loader: UniqueSafeLoader, node: yaml.MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, yaml.MappingNode):
        _fail("YAML_SHAPE_INVALID", "contract")
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            _fail("YAML_DUPLICATE_KEY", "contract")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping
)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _sha256_text(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("ascii")


def _mapping(value: object, keys: tuple[str, ...], field: str) -> dict[str, object]:
    if type(value) is not dict or tuple(cast(dict[object, object], value)) != keys:
        _fail("CONTRACT_SHAPE_INVALID", field)
    document = cast(dict[str, object], value)
    if any(type(key) is not str for key in document):
        _fail("CONTRACT_SHAPE_INVALID", field)
    return document


def _regular_bytes(root: Path, relative: Path, field: str) -> bytes:
    if relative.is_absolute() or ".." in relative.parts:
        _fail("PATH_INVALID", field)
    current = root
    for part in relative.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            _fail("INPUT_UNAVAILABLE", field)
        if stat.S_ISLNK(metadata.st_mode):
            _fail("SYMLINK_REJECTED", field)
    try:
        metadata = current.stat()
        content = current.read_bytes()
    except OSError:
        _fail("INPUT_UNAVAILABLE", field)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or not content
        or len(content) != metadata.st_size
        or len(content) > MAX_SOURCE_BYTES
    ):
        _fail("INPUT_INVALID", field)
    return content


def load_contract(root: Path = REPO_ROOT) -> dict[str, object]:
    content = _regular_bytes(root, CONTRACT_PATH, "contract")
    try:
        value = yaml.load(content, Loader=UniqueSafeLoader)
    except UnitEconomicsBuildError:
        raise
    except Exception:
        _fail("YAML_INVALID", "contract")
    contract = _mapping(value, TOP_LEVEL_KEYS, "contract")
    validate_contract(contract)
    return contract


def validate_contract(contract: Mapping[str, object]) -> None:
    if type(contract) is not dict or tuple(contract) != TOP_LEVEL_KEYS:
        _fail("CONTRACT_SHAPE_INVALID", "contract")
    document = _mapping(
        contract["document"],
        (
            "schema_version",
            "story_id",
            "classification",
            "status",
            "executable_environments",
            "authority",
            "canonical_status",
            "formal_validation_claimed",
            "production_eligible",
        ),
        "document",
    )
    expected_document = {
        "schema_version": "2.0.0",
        "story_id": "ST-1304",
        "classification": "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_UNIT_ECONOMICS",
        "status": "LOCAL_CODE_COMPLETE",
        "executable_environments": ["ENV-DEV", "ENV-CI"],
        "authority": "RECORDED_SYNTHETIC_ONLY",
        "canonical_status": "UNCHANGED",
        "formal_validation_claimed": False,
        "production_eligible": False,
    }
    if document != expected_document:
        _fail("CONTRACT_VALUE_INVALID", "document")
    bindings = _mapping(
        contract["source_bindings"], SOURCE_BINDING_KEYS, "source_bindings"
    )
    for name, raw in bindings.items():
        row = _mapping(raw, ("path", "sha256"), f"source_bindings.{name}")
        if row["path"] != SOURCE_BINDING_PATHS[name] or not _sha256_text(row["sha256"]):
            _fail("CONTRACT_VALUE_INVALID", f"source_bindings.{name}")
    open_decisions = _mapping(
        contract["open_decision_boundary"],
        ("labor", "budget"),
        "open_decision_boundary",
    )
    labor_decision = _mapping(
        open_decisions["labor"],
        ("id", "status", "resolved", "safe_default", "fixture_rate_authority"),
        "open_decision_boundary.labor",
    )
    budget_decision = _mapping(
        open_decisions["budget"],
        ("id", "status", "resolved", "safe_default", "fixture_cost_authority"),
        "open_decision_boundary.budget",
    )
    if labor_decision != {
        "id": "OD-005",
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "safe_default": "UNKNOWN_NOT_ZERO",
        "fixture_rate_authority": "SYNTHETIC_TEST_DATA_ONLY",
    } or budget_decision != {
        "id": "OD-009",
        "status": "HUMAN_DECISION_REQUIRED",
        "resolved": False,
        "safe_default": "LOW_DEVELOPMENT_ONLY_PRODUCTION_DISABLED",
        "fixture_cost_authority": "SYNTHETIC_TEST_DATA_ONLY",
    }:
        _fail("CONTRACT_VALUE_INVALID", "open_decision_boundary")
    input_contract = _mapping(
        contract["input_contract"],
        (
            "profile",
            "method_version",
            "program",
            "period_duration_days",
            "article_slots",
            "exact_article_binding_required",
            "exact_attribution_result_recalculation_required",
            "same_program_required",
            "same_period_required",
            "verified_input_required",
            "mature_cohort_required",
            "work_minutes_match_measurement_required",
            "incremental_cost_match_measurement_required",
            "cost_component_conservation_required",
            "numeric_type",
            "float_allowed",
            "missing_as_zero",
            "unknown_labor_as_zero",
        ),
        "input_contract",
    )
    if input_contract != {
        "profile": "RAOS_ST1304_RECORDED_SYNTHETIC_V2",
        "method_version": "RAOS_ST1304_DIRECT_UNIT_ECONOMICS_V2",
        "program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE",
        "period_duration_days": 14,
        "article_slots": [1, 2, 3, 4, 5],
        "exact_article_binding_required": True,
        "exact_attribution_result_recalculation_required": True,
        "same_program_required": True,
        "same_period_required": True,
        "verified_input_required": True,
        "mature_cohort_required": True,
        "work_minutes_match_measurement_required": True,
        "incremental_cost_match_measurement_required": True,
        "cost_component_conservation_required": True,
        "numeric_type": "decimal.Decimal_and_integral_JPY",
        "float_allowed": False,
        "missing_as_zero": False,
        "unknown_labor_as_zero": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "input_contract")
    cost = _mapping(
        contract["cost_contract"],
        (
            "component_metrics",
            "provenance_metrics",
            "component_sum_equals_incremental_cost",
            "source_sha256_visible",
            "labor_rate_selected_by_runtime",
            "budget_selected_by_runtime",
        ),
        "cost_contract",
    )
    if cost != {
        "component_metrics": [
            "ai_actual_cost_jpy",
            "api_actual_cost_jpy",
            "hosting_actual_cost_jpy",
            "observability_actual_cost_jpy",
            "analytics_actual_cost_jpy",
            "content_tool_actual_cost_jpy",
            "other_actual_cost_jpy",
        ],
        "provenance_metrics": [
            "work_minutes",
            "incremental_cost_jpy",
            "qualified_sessions",
            "article_update_cost_jpy",
            "initial_content_cost_jpy",
            "approved_article_versions",
            "trailing_monthly_confirmed_contribution_jpy",
            "labor_hourly_cost_jpy",
        ],
        "component_sum_equals_incremental_cost": True,
        "source_sha256_visible": True,
        "labor_rate_selected_by_runtime": False,
        "budget_selected_by_runtime": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "cost_contract")
    reward = _mapping(
        contract["reward_contract"],
        (
            "provider_total_visible_separately",
            "article_economics_basis",
            "estimated_reward_in_article_metrics",
            "estimated_reward_visible_separately",
            "unattributed_reward_in_article_metrics",
            "unattributed_reward_visible_separately",
            "unattributed_allocation_to_articles",
            "exact_provider_total_conservation",
        ),
        "reward_contract",
    )
    if reward != {
        "provider_total_visible_separately": True,
        "article_economics_basis": "VERIFIED_DIRECT_ONLY",
        "estimated_reward_in_article_metrics": False,
        "estimated_reward_visible_separately": True,
        "unattributed_reward_in_article_metrics": False,
        "unattributed_reward_visible_separately": True,
        "unattributed_allocation_to_articles": False,
        "exact_provider_total_conservation": True,
    }:
        _fail("CONTRACT_VALUE_INVALID", "reward_contract")
    calculation = _mapping(
        contract["calculation_contract"],
        (
            "metrics",
            "decimal_precision",
            "rounding",
            "explicit_observed_zero_is_zero",
            "missing_unverified_zero_denominator_immature_mismatch",
            "unavailable_value",
            "learning_output",
        ),
        "calculation_contract",
    )
    expected_metrics = [
        {
            "id": "KPI-001",
            "name": "confirmed_provider_reward_jpy",
            "basis": "PROVIDER_FACT",
        },
        {
            "id": "SUPPLEMENTAL-DIRECT-REWARD",
            "name": "direct_confirmed_reward_jpy",
            "basis": "DIRECT",
        },
        {
            "id": "KPI-002-DIRECT-VIEW",
            "name": "direct_confirmed_contribution_profit_jpy",
            "basis": "DIRECT",
        },
        {"id": "KPI-003", "name": "confirmed_epc_jpy", "basis": "DIRECT"},
        {"id": "KPI-004", "name": "confirmed_rpm_jpy", "basis": "DIRECT"},
        {
            "id": "KPI-022",
            "name": "article_update_cost_ratio",
            "basis": "DIRECT",
        },
        {
            "id": "KPI-023",
            "name": "content_payback_months",
            "basis": "DIRECT",
        },
        {
            "id": "KPI-025",
            "name": "ai_cost_per_approved_article_jpy",
            "basis": "DIRECT",
        },
        {
            "id": "SUPPLEMENTAL-CONTENT-HOUR",
            "name": "confirmed_reward_per_content_hour_jpy",
            "basis": "DIRECT",
        },
    ]
    if calculation != {
        "metrics": expected_metrics,
        "decimal_precision": 50,
        "rounding": "ROUND_HALF_EVEN",
        "explicit_observed_zero_is_zero": True,
        "missing_unverified_zero_denominator_immature_mismatch": "UNAVAILABLE",
        "unavailable_value": None,
        "learning_output": "METRICS_ONLY_NO_MUTATION_OR_PROPOSAL",
    }:
        _fail("CONTRACT_VALUE_INVALID", "calculation_contract")
    authority = _mapping(
        contract["authority_boundary"],
        (
            "provider_call",
            "network",
            "persistence",
            "public_projection",
            "publication",
            "editorial_mutation",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
            "budget_selection",
            "labor_rate_selection",
            "staging",
            "release",
            "production",
            "recommendation_inputs_excluded",
        ),
        "authority_boundary",
    )
    if any(
        value is not False
        for key, value in authority.items()
        if key != "recommendation_inputs_excluded"
    ) or authority.get("recommendation_inputs_excluded") != [
        "AFFILIATE_COMMISSION_RATE",
        "CONFIRMED_REWARD",
        "UNATTRIBUTED_REWARD",
        "ESTIMATED_REWARD",
        "COMMISSION",
        "INCREMENTAL_COST",
        "LABOR_COST",
        "EPC",
        "RPM",
        "PROFIT",
    ]:
        _fail("CONTRACT_VALUE_INVALID", "authority_boundary")
    fixture = _mapping(
        contract["recorded_fixture"],
        (
            "path",
            "sha256",
            "synthetic",
            "attribution_input_sha256",
            "attribution_result_sha256",
            "unit_economics_input_sha256",
            "unit_economics_result_sha256",
            "provider_execution",
        ),
        "recorded_fixture",
    )
    if (
        fixture.get("path") != FIXTURE_PATH.as_posix()
        or fixture.get("synthetic") is not True
        or fixture.get("provider_execution") != "NOT_EXECUTED"
        or any(
            not _sha256_text(fixture[name])
            for name in (
                "sha256",
                "attribution_input_sha256",
                "attribution_result_sha256",
                "unit_economics_input_sha256",
                "unit_economics_result_sha256",
            )
        )
    ):
        _fail("CONTRACT_VALUE_INVALID", "recorded_fixture")
    verification = _mapping(
        contract["verification_boundary"],
        (
            "local_unit_property_adversarial",
            "dependency_regression",
            "owner_generator_check",
            "TST-030",
            "real_cost_and_labor_sources",
            "database",
            "live",
            "staging",
            "release",
            "production",
        ),
        "verification_boundary",
    )
    if verification != {
        "local_unit_property_adversarial": "CANDIDATE",
        "dependency_regression": "CANDIDATE",
        "owner_generator_check": "CANDIDATE",
        "TST-030": "NOT_EXECUTED",
        "real_cost_and_labor_sources": "NOT_EXECUTED",
        "database": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }:
        _fail("CONTRACT_VALUE_INVALID", "verification_boundary")


def _validate_bindings(root: Path, bindings: Mapping[str, object]) -> None:
    for name in SOURCE_BINDING_KEYS:
        row = cast(dict[str, str], bindings[name])
        content = _regular_bytes(root, Path(row["path"]), name)
        if _sha256(content) != row["sha256"]:
            _fail("INPUT_HASH_DRIFT", name)


def _source_artifacts(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in SOURCE_PATHS:
        content = _regular_bytes(root, path, path.name)
        rows.append(
            {
                "bytes": len(content),
                "sha256": _sha256(content),
                "uri": f"repo://{path.as_posix()}",
            }
        )
    return rows


def render_output(root: Path = REPO_ROOT) -> bytes:
    contract = load_contract(root)
    _validate_bindings(root, cast(Mapping[str, object], contract["source_bindings"]))

    from raos.adapters.recorded_unit_economics import (
        RecordedUnitEconomicsAdapter,
        load_recorded_unit_economics_fixture,
    )
    from raos.application.finance.unit_economics import UnitEconomicsService
    from raos.config.runtime import RuntimeEnvironment
    from scripts import build_st1303_attribution_engine as st1303

    measurement_contract = st1303.load_contract(root)[1]
    scenario = load_recorded_unit_economics_fixture(
        (root / FIXTURE_PATH).resolve(),
        attribution_fixture_path=(root / ATTRIBUTION_FIXTURE_PATH).resolve(),
        contract=measurement_contract,
    )
    adapter = RecordedUnitEconomicsAdapter()
    result = UnitEconomicsService(
        environment=RuntimeEnvironment.CI, runner=adapter
    ).execute(scenario.request)
    fixture_binding = cast(dict[str, object], contract["recorded_fixture"])
    if (
        scenario.fixture_sha256.value != fixture_binding["sha256"]
        or scenario.request.attribution_request.input_sha256.value
        != fixture_binding["attribution_input_sha256"]
        or scenario.request.attribution_result.result_sha256.value
        != fixture_binding["attribution_result_sha256"]
        or scenario.request.input_sha256.value
        != fixture_binding["unit_economics_input_sha256"]
        or result.result_sha256.value != fixture_binding["unit_economics_result_sha256"]
    ):
        _fail("RECORDED_FIXTURE_BINDING_DRIFT", "recorded_fixture")
    projection = {
        "completion_boundary": {
            "canonical_status_changed": False,
            "formal_or_live_evidence_claimed": False,
            "local_code_complete": True,
            "local_integration_complete": False,
        },
        "document": dict(cast(dict[str, object], contract["document"])),
        "measurement_boundary": {
            "article_slots": [
                {
                    "article_id": item.article_id,
                    "packet_sha256": item.packet_sha256.value,
                    "slot": item.slot,
                }
                for item in measurement_contract.articles
            ],
            "contract_sha256": measurement_contract.sha256.value,
            "period": scenario.request.attribution_request.period.payload(),
            "program": scenario.request.attribution_request.program,
        },
        "open_decision_boundary": contract["open_decision_boundary"],
        "provenance": {
            "attribution_fixture_sha256": scenario.attribution_fixture_sha256.value,
            "fixture_sha256": scenario.fixture_sha256.value,
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": (
                ".venv/bin/python scripts/build_st1304_cost_unit_economics.py"
            ),
            "source_artifacts": _source_artifacts(root),
            "source_bindings": contract["source_bindings"],
        },
        "recorded_result": result.payload(),
        "verification_boundary": contract["verification_boundary"],
    }
    return _json_bytes(projection)


def _validate_output_target(root: Path) -> Path:
    target = root / OUTPUT_PATH
    current = root
    for part in OUTPUT_PATH.parent.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            _fail("OUTPUT_PARENT_UNAVAILABLE", "output")
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            _fail("OUTPUT_PARENT_INVALID", "output")
    try:
        metadata = os.lstat(target)
    except FileNotFoundError:
        return target
    except OSError:
        _fail("OUTPUT_UNAVAILABLE", "output")
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _fail("OUTPUT_INVALID", "output")
    return target


def _atomic_write(root: Path, content: bytes) -> None:
    target = _validate_output_target(root)
    descriptor = -1
    stage_name = ""
    try:
        descriptor, stage_name = tempfile.mkstemp(
            prefix=f".{target.name}.", suffix=".stage", dir=target.parent
        )
        os.fchmod(descriptor, 0o644)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = -1
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(stage_name, target)
        stage_name = ""
        os.chmod(target, 0o644, follow_symlinks=False)
        parent_fd = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        if descriptor >= 0:
            os.close(descriptor)
        if stage_name:
            try:
                os.unlink(stage_name)
            except OSError:
                pass
        _fail("ATOMIC_WRITE_FAILED", "output")


def build(root: Path = REPO_ROOT, *, check: bool = False) -> None:
    expected = render_output(root)
    target = _validate_output_target(root)
    if check:
        try:
            actual = target.read_bytes()
            mode = stat.S_IMODE(target.stat().st_mode)
        except OSError:
            _fail("OUTPUT_UNAVAILABLE", "output")
        if actual != expected or mode != 0o644:
            _fail("OUTPUT_DRIFT", "output")
        return
    _atomic_write(root, expected)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("--check", action="store_true")
    return parser.parse_args(list(argv))


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        build(check=bool(arguments.check))
    except UnitEconomicsBuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    action = "checked" if arguments.check else "generated"
    print(f"ST-1304 unit-economics projection {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
