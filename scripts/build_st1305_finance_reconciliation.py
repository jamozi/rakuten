#!/usr/bin/env python3
"""Build the deterministic ST-1305 V2 recorded reconciliation projection."""

from __future__ import annotations

import argparse
from collections.abc import Mapping, Sequence
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from typing import Any, Final, NoReturn, cast
from uuid import UUID

import yaml


REPO_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.raos_build_core import input_hash_required  # noqa: E402

GENERATOR_PATH: Final = Path("scripts/build_st1305_finance_reconciliation.py")
CONTRACT_PATH: Final = Path(
    "changes/st-1305/contracts/finance-reconciliation-runtime.v2.yaml"
)
FIXTURE_PATH: Final = Path(
    "changes/st-1305/fixtures/finance-reconciliation-recorded.synthetic.v2.json"
)
UNIT_ECONOMICS_FIXTURE_PATH: Final = Path(
    "changes/st-1304/fixtures/cost-unit-economics-recorded.synthetic.v2.json"
)
ATTRIBUTION_FIXTURE_PATH: Final = Path(
    "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
)
OUTPUT_PATH: Final = Path(
    "changes/st-1305/generated/finance-reconciliation-recorded.v2.json"
)
SOURCE_PATHS: Final = (
    CONTRACT_PATH,
    FIXTURE_PATH,
    Path("changes/st-1305/PREFLIGHT-v2.md"),
    Path("changes/st-1305/README-v2.md"),
    Path("python/raos/domain/finance/reconciliation.py"),
    Path("python/raos/ports/finance_reconciliation.py"),
    Path("python/raos/application/finance/reconciliation.py"),
    Path("python/raos/adapters/recorded_finance_reconciliation.py"),
    GENERATOR_PATH,
)
MAX_SOURCE_BYTES: Final = 4 * 1024 * 1024
TOP_LEVEL_KEYS: Final = (
    "document",
    "source_bindings",
    "open_decision_boundary",
    "report_contract",
    "metric_contract",
    "learning_contract",
    "authority_boundary",
    "recorded_fixture",
    "verification_boundary",
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
    "attribution_policy": (
        "docs/canonical/03_analytics/RAOS_09_attribution_policy_v1.0.yaml"
    ),
    "kpi_catalog": "docs/canonical/03_analytics/RAOS_09_kpi_catalog_v1.0.yaml",
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
    "threat_register": "docs/canonical/04_security/RAOS_10_threat_register_v1.0.yaml",
    "st1303_runtime": "changes/st-1303/contracts/attribution-engine-runtime.v2.yaml",
    "st1303_projection": (
        "changes/st-1303/generated/attribution-engine-recorded.v2.json"
    ),
    "st1303_fixture": (
        "changes/st-1303/fixtures/attribution-engine-recorded.synthetic.v2.json"
    ),
    "st1304_runtime": ("changes/st-1304/contracts/cost-unit-economics-runtime.v2.yaml"),
    "st1304_projection": (
        "changes/st-1304/generated/cost-unit-economics-recorded.v2.json"
    ),
    "st1304_fixture": (
        "changes/st-1304/fixtures/cost-unit-economics-recorded.synthetic.v2.json"
    ),
    "five_slot_measurement": (
        "changes/st-1704/affiliate-learning-v2/measurement-contract.v2.json"
    ),
}
SOURCE_BINDING_KEYS: Final = tuple(SOURCE_BINDING_PATHS)


class FinanceReconciliationBuildError(RuntimeError):
    """Sanitized owner-build failure."""


def _fail(code: str, field: str) -> NoReturn:
    raise FinanceReconciliationBuildError(
        f"ST-1305 build failed: {code} field={field}"
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
    try:
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
    except Exception:
        _fail("JSON_SERIALIZATION_FAILED", "output")


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
    except FinanceReconciliationBuildError:
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
    if document != {
        "schema_version": "2.0.0",
        "story_id": "ST-1305",
        "classification": (
            "MAXIMUM_SAFE_LOCAL_RECORDED_SYNTHETIC_FINANCE_RECONCILIATION"
        ),
        "status": "LOCAL_CODE_COMPLETE",
        "executable_environments": ["ENV-DEV", "ENV-CI"],
        "authority": "RECORDED_SYNTHETIC_ONLY",
        "canonical_status": "UNCHANGED",
        "formal_validation_claimed": False,
        "production_eligible": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "document")
    bindings = _mapping(
        contract["source_bindings"], SOURCE_BINDING_KEYS, "source_bindings"
    )
    for name, raw in bindings.items():
        row = _mapping(raw, ("path", "sha256"), f"source_bindings.{name}")
        if row["path"] != SOURCE_BINDING_PATHS[name] or not _sha256_text(row["sha256"]):
            _fail("CONTRACT_VALUE_INVALID", f"source_bindings.{name}")
    decisions = _mapping(
        contract["open_decision_boundary"],
        ("report_sample", "labor", "budget", "retention"),
        "open_decision_boundary",
    )
    expected_decisions = {
        "report_sample": {
            "id": "OD-003",
            "status": "EXTERNAL_EVIDENCE_REQUIRED",
            "resolved": False,
            "safe_default": "SYNTHETIC_FIXTURE_ONLY_REAL_REPORT_UNVERIFIED",
        },
        "labor": {
            "id": "OD-005",
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "safe_default": "UNKNOWN_NOT_ZERO",
        },
        "budget": {
            "id": "OD-009",
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "safe_default": "LOW_DEVELOPMENT_ONLY_PRODUCTION_DISABLED",
        },
        "retention": {
            "id": "OD-014",
            "status": "HUMAN_DECISION_REQUIRED",
            "resolved": False,
            "safe_default": "AUTOMATIC_DELETION_DISABLED",
        },
    }
    for name, expected in expected_decisions.items():
        if (
            _mapping(decisions[name], tuple(expected), f"open_decision_boundary.{name}")
            != expected
        ):
            _fail("CONTRACT_VALUE_INVALID", "open_decision_boundary")
    report = _mapping(
        contract["report_contract"],
        (
            "profile",
            "method_version",
            "program",
            "period_duration_days",
            "article_slots",
            "exact_dependency_recalculation_required",
            "same_program_required",
            "same_period_required",
            "verified_input_required",
            "mature_cohort_required",
            "arbitrary_total_allocation",
            "missing_as_zero",
            "synthetic_provider_report_claimed",
            "canonical_dimensions",
            "unavailable_without_real_report",
            "batch_totals_required",
            "typed_exceptions_required",
            "raw_provider_rows_in_report",
        ),
        "report_contract",
    )
    if report != {
        "profile": "RAOS_ST1305_RECORDED_SYNTHETIC_V2",
        "method_version": "RAOS_ST1305_FINANCE_RECONCILIATION_V2",
        "program": "WORDPRESS_BLOG_RAKUTEN_AFFILIATE",
        "period_duration_days": 14,
        "article_slots": [1, 2, 3, 4, 5],
        "exact_dependency_recalculation_required": True,
        "same_program_required": True,
        "same_period_required": True,
        "verified_input_required": True,
        "mature_cohort_required": True,
        "arbitrary_total_allocation": False,
        "missing_as_zero": False,
        "synthetic_provider_report_claimed": False,
        "canonical_dimensions": [
            "file_hash_uniqueness",
            "row_count",
            "generated_confirmed_cancelled_amount_totals",
            "currency",
            "period",
            "duplicate_provider_row",
            "dry_run_to_commit_hash_equality",
        ],
        "unavailable_without_real_report": [
            "file_hash_uniqueness",
            "row_count",
            "generated_confirmed_cancelled_amount_totals",
            "dry_run_to_commit_hash_equality",
        ],
        "batch_totals_required": True,
        "typed_exceptions_required": True,
        "raw_provider_rows_in_report": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "report_contract")
    metric = _mapping(
        contract["metric_contract"],
        (
            "metrics",
            "source",
            "same_program_period_verified_mature_only",
            "explicit_observed_zero_is_zero",
            "missing_unverified_zero_denominator_immature_mismatch",
            "unavailable_value",
            "provider_direct_estimated_unattributed_separate",
            "unattributed_reward_article_allocation",
        ),
        "metric_contract",
    )
    if metric != {
        "metrics": [
            "search_ctr",
            "affiliate_click_rate",
            "confirmed_reward_per_click_jpy",
            "confirmation_rate",
            "confirmed_reward_per_content_hour_jpy",
        ],
        "source": "EXACT_ST1303_RECALCULATION",
        "same_program_period_verified_mature_only": True,
        "explicit_observed_zero_is_zero": True,
        "missing_unverified_zero_denominator_immature_mismatch": "UNAVAILABLE",
        "unavailable_value": None,
        "provider_direct_estimated_unattributed_separate": True,
        "unattributed_reward_article_allocation": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "metric_contract")
    learning = _mapping(
        contract["learning_contract"],
        (
            "output_kind",
            "allowed_signals",
            "excluded_finance_signals",
            "rules",
            "rule_order_then_slot_order",
            "reward_or_profit_priority",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
        ),
        "learning_contract",
    )
    if learning != {
        "output_kind": "REVIEW_CANDIDATES_ONLY",
        "allowed_signals": [
            "search_impressions",
            "search_clicks",
            "article_views",
            "affiliate_clicks",
            "broken_links",
            "intent_classification",
        ],
        "excluded_finance_signals": [
            "pending_outcomes",
            "confirmed_outcomes",
            "rejected_outcomes",
            "direct_confirmed_reward_jpy",
            "unattributed_confirmed_reward_jpy",
            "affiliate_commission_rate",
            "incremental_cost_jpy",
            "work_minutes",
            "epc",
            "rpm",
            "profit",
        ],
        "rules": [
            "BROKEN_LINK_REPAIR_REVIEW",
            "SEARCH_INTENT_ALIGNMENT_REVIEW",
            "PURCHASE_DECISION_BRIDGE_REVIEW",
        ],
        "rule_order_then_slot_order": True,
        "reward_or_profit_priority": False,
        "article_html_mutation": False,
        "cta_mutation": False,
        "product_selection_mutation": False,
        "recommendation_order_mutation": False,
        "publication_snapshot_mutation": False,
    }:
        _fail("CONTRACT_VALUE_INVALID", "learning_contract")
    authority = _mapping(
        contract["authority_boundary"],
        (
            "provider_call",
            "network",
            "credential_access",
            "persistence",
            "database",
            "public_projection",
            "publication",
            "editorial_mutation",
            "article_html_mutation",
            "cta_mutation",
            "product_selection_mutation",
            "recommendation_order_mutation",
            "publication_snapshot_mutation",
            "approval",
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
    ) or authority["recommendation_inputs_excluded"] != [
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
            "unit_economics_fixture_sha256",
            "unit_economics_input_sha256",
            "unit_economics_result_sha256",
            "reconciliation_input_sha256",
            "reconciliation_result_sha256",
            "provider_execution",
        ),
        "recorded_fixture",
    )
    if (
        fixture["path"] != FIXTURE_PATH.as_posix()
        or fixture["synthetic"] is not True
        or fixture["provider_execution"] != "NOT_EXECUTED"
        or any(
            not _sha256_text(fixture[name])
            for name in (
                "sha256",
                "unit_economics_fixture_sha256",
                "unit_economics_input_sha256",
                "unit_economics_result_sha256",
                "reconciliation_input_sha256",
                "reconciliation_result_sha256",
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
            "real_provider_report",
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
        "real_provider_report": "NOT_EXECUTED",
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
        if (
            input_hash_required(row["path"])
            or name.startswith(("st1303_", "st1304_"))
            or name == "five_slot_measurement"
        ) and _sha256(_regular_bytes(root, Path(row["path"]), name)) != row["sha256"]:
            _fail("INPUT_HASH_DRIFT", name)


def refresh_upstream_bindings(root: Path = REPO_ROOT) -> None:
    """Rebind the unchanged, hash-verified synthetic report to current inputs."""
    from raos.adapters import recorded_finance_reconciliation as recorded
    from raos.adapters.recorded_unit_economics import (
        load_recorded_unit_economics_fixture,
    )
    from raos.domain.finance.reconciliation import (
        FinanceReconciliationRunRequest,
        build_finance_reconciliation,
    )
    from raos.domain.finance.unit_economics import build_unit_economics
    from scripts import build_st1303_attribution_engine as st1303

    contract = cast(dict[str, Any], copy.deepcopy(load_contract(root)))
    previous = _regular_bytes(root, FIXTURE_PATH, "fixture")
    binding = contract["recorded_fixture"]
    if _sha256(previous) != binding["sha256"]:
        _fail("SYNTHETIC_REBIND_INPUT_INVALID", "fixture")
    try:
        fixture = dict(
            recorded._mapping(
                recorded._unique_json(previous),
                (
                    "schema_version",
                    "profile",
                    "scenario_id",
                    "synthetic",
                    "unit_economics_fixture_sha256",
                    "expected_unit_economics_input_sha256",
                    "expected_unit_economics_result_sha256",
                    "request",
                    "expected_input_sha256",
                    "expected_result_sha256",
                ),
            )
        )
        if (
            fixture["schema_version"] != "2.0.0"
            or fixture["profile"] != recorded.PROFILE
            or fixture["synthetic"] is not True
            or fixture["expected_input_sha256"]
            != binding["reconciliation_input_sha256"]
            or fixture["expected_result_sha256"]
            != binding["reconciliation_result_sha256"]
            or fixture["unit_economics_fixture_sha256"]
            != binding["unit_economics_fixture_sha256"]
            or fixture["expected_unit_economics_input_sha256"]
            != binding["unit_economics_input_sha256"]
            or fixture["expected_unit_economics_result_sha256"]
            != binding["unit_economics_result_sha256"]
        ):
            _fail("SYNTHETIC_REBIND_INPUT_INVALID", "fixture")
        measurement = st1303.load_contract(root)[1]
        prior = json.loads(_regular_bytes(root, OUTPUT_PATH, "previous_projection"))
        identity = ("slot", "article_id", "slug", "intent_classification")
        if [
            tuple(row[key] for key in identity)
            for row in prior["measurement_boundary"]["article_slots"]
        ] != [
            tuple(getattr(article, key) for key in identity)
            for article in measurement.articles
        ]:
            _fail("UPSTREAM_ARTICLE_IDENTITY_DRIFT", "fixture")
        unit = load_recorded_unit_economics_fixture(
            (root / UNIT_ECONOMICS_FIXTURE_PATH).resolve(),
            attribution_fixture_path=(root / ATTRIBUTION_FIXTURE_PATH).resolve(),
            contract=measurement,
        )
        unit_result = build_unit_economics(unit.request)
        source = recorded._mapping(fixture["request"], ("run_id", "requested_at"))
        request = FinanceReconciliationRunRequest(
            run_id=UUID(recorded._string(source["run_id"], maximum=36)),
            requested_at=recorded._timestamp(source["requested_at"]),
            unit_economics_request=unit.request,
            unit_economics_result=unit_result,
        )
        result = build_finance_reconciliation(request)
        fixture.update(
            unit_economics_fixture_sha256=unit.fixture_sha256.value,
            expected_unit_economics_input_sha256=unit.request.input_sha256.value,
            expected_unit_economics_result_sha256=unit_result.result_sha256.value,
            expected_input_sha256=request.input_sha256.value,
            expected_result_sha256=result.result_sha256.value,
        )
        payload = (
            previous
            if fixture == recorded._unique_json(previous)
            else (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode()
        )
        binding.update(
            sha256=_sha256(payload),
            unit_economics_fixture_sha256=unit.fixture_sha256.value,
            unit_economics_input_sha256=unit.request.input_sha256.value,
            unit_economics_result_sha256=unit_result.result_sha256.value,
            reconciliation_input_sha256=request.input_sha256.value,
            reconciliation_result_sha256=result.result_sha256.value,
        )
        for name, row in contract["source_bindings"].items():
            if (
                name.startswith(("st1303_", "st1304_"))
                or name == "five_slot_measurement"
            ):
                row["sha256"] = _sha256(_regular_bytes(root, Path(row["path"]), name))
        validate_contract(contract)
        _validate_bindings(root, contract["source_bindings"])
    except FinanceReconciliationBuildError:
        raise
    except Exception:
        _fail("SYNTHETIC_REBIND_INPUT_INVALID", "fixture")
    replacements = {FIXTURE_PATH: payload}
    if contract != load_contract(root):
        replacements[CONTRACT_PATH] = yaml.safe_dump(
            contract, allow_unicode=True, sort_keys=False
        ).encode()
    originals = {
        path: _regular_bytes(root, path, "binding_input") for path in replacements
    }
    written: list[Path] = []
    try:
        for path, value in replacements.items():
            if value != originals[path]:
                _atomic_write(root, value, relative=path)
                written.append(path)
    except FinanceReconciliationBuildError:
        for path in reversed(written):
            _atomic_write(root, originals[path], relative=path)
        raise


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

    from raos.adapters.recorded_finance_reconciliation import (
        RecordedFinanceReconciliationAdapter,
        load_recorded_finance_reconciliation_fixture,
    )
    from raos.application.finance.reconciliation import (
        FinanceReconciliationService,
    )
    from raos.config.runtime import RuntimeEnvironment
    from scripts import build_st1303_attribution_engine as st1303

    measurement_contract = st1303.load_contract(root)[1]
    scenario = load_recorded_finance_reconciliation_fixture(
        (root / FIXTURE_PATH).resolve(),
        unit_economics_fixture_path=(root / UNIT_ECONOMICS_FIXTURE_PATH).resolve(),
        attribution_fixture_path=(root / ATTRIBUTION_FIXTURE_PATH).resolve(),
        contract=measurement_contract,
    )
    adapter = RecordedFinanceReconciliationAdapter()
    result = FinanceReconciliationService(
        environment=RuntimeEnvironment.CI, runner=adapter
    ).execute(scenario.request)
    fixture_binding = cast(dict[str, object], contract["recorded_fixture"])
    if (
        scenario.fixture_sha256.value != fixture_binding["sha256"]
        or scenario.unit_economics_fixture_sha256.value
        != fixture_binding["unit_economics_fixture_sha256"]
        or scenario.request.unit_economics_request.input_sha256.value
        != fixture_binding["unit_economics_input_sha256"]
        or scenario.request.unit_economics_result.result_sha256.value
        != fixture_binding["unit_economics_result_sha256"]
        or scenario.request.input_sha256.value
        != fixture_binding["reconciliation_input_sha256"]
        or result.result_sha256.value != fixture_binding["reconciliation_result_sha256"]
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
                    "intent_classification": item.intent_classification,
                    "packet_sha256": item.packet_sha256.value,
                    "slot": item.slot,
                    "slug": item.slug,
                }
                for item in measurement_contract.articles
            ],
            "contract_sha256": measurement_contract.sha256.value,
            "period": scenario.request.unit_economics_request.attribution_request.period.payload(),
            "program": scenario.request.unit_economics_request.attribution_request.program,
        },
        "open_decision_boundary": contract["open_decision_boundary"],
        "provenance": {
            "fixture_sha256": scenario.fixture_sha256.value,
            "generated_by": f"repo://{GENERATOR_PATH.as_posix()}",
            "generation_command": (
                ".venv/bin/python scripts/build_st1305_finance_reconciliation.py"
            ),
            "source_artifacts": _source_artifacts(root),
            "source_bindings": contract["source_bindings"],
            "unit_economics_fixture_sha256": (
                scenario.unit_economics_fixture_sha256.value
            ),
        },
        "recorded_report": result.payload(),
        "verification_boundary": contract["verification_boundary"],
    }
    return _json_bytes(projection)


def _validate_output_target(root: Path, relative: Path = OUTPUT_PATH) -> Path:
    if relative not in (OUTPUT_PATH, CONTRACT_PATH, FIXTURE_PATH):
        _fail("OUTPUT_INVALID", "output")
    target = root / relative
    current = root
    for part in relative.parent.parts:
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


def _atomic_write(root: Path, content: bytes, *, relative: Path = OUTPUT_PATH) -> None:
    target = _validate_output_target(root, relative)
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
    if not check:
        refresh_upstream_bindings(root)
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
    except FinanceReconciliationBuildError as error:
        print(str(error), file=sys.stderr)
        return 1
    action = "checked" if arguments.check else "generated"
    print(f"ST-1305 finance reconciliation projection {action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
