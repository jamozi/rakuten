"""Hostile closed-boundary tests for the ST-1305 owner builder."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1305_finance_reconciliation_reference_plan as generator


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "status", "READY"),
        ("document", "executable", True),
        ("document", "activation", True),
        ("document", "runtime_eligible", True),
        ("document", "authority", "GRANTED"),
        ("document", "decision", "READY"),
        ("document", "story_acceptance", True),
        ("document", "production_eligible", True),
        ("document", "approval", "approved"),
        ("authority", "changes_canonical_status", True),
        ("collections", "empty_means_zero", True),
        ("evaluation_boundary", "vacuous_pass_allowed", True),
        ("verification_boundary", "TST-030", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "story_acceptance", True),
        ("verification_boundary", "live_evidence", True),
        ("verification_boundary", "decision", "READY"),
    ],
)
def test_false_execution_or_completion_claim_is_rejected(
    section: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract[section][field] = value
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("report_sample", "report_sample", "invented"),
        ("report_sample", "column_mapping", "invented"),
        ("report_sample", "real_attribution_verified", True),
        ("labor", "hourly_cost_jpy", 0),
        ("labor", "labor_cost_state", "KNOWN"),
        ("labor", "unknown_labor_is_zero", True),
        ("budget", "monthly_caps", {"JPY": 1}),
        ("budget", "production_enabled", True),
        ("retention", "retention_period", "7 years"),
        ("retention", "automatic_deletion_enabled", True),
    ],
)
def test_inherited_open_decision_cannot_be_invented(
    section: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["inherited_open_decision_boundary"][section][field] = value
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "field",
    [key for key in generator.load_contract()["selection_boundary"] if key != "state"],
)
def test_unavailable_selection_cannot_be_invented(field: str) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["selection_boundary"][field] = "invented"
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("collection", generator.COLLECTION_KEYS)
def test_input_comparison_exception_report_or_write_is_rejected(
    collection: str,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["collections"][collection] = [{"invented": True}]
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("field", (*generator.COUNT_KEYS, *generator.TOTAL_KEYS))
@pytest.mark.parametrize("value", [0, 1, -1, 0.0, "0"])
def test_unknown_count_or_total_cannot_be_coerced_to_value(
    field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["collections"][field] = value
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("check", generator.EVALUATION_KEYS)
@pytest.mark.parametrize(
    ("field", "value"),
    [("status", "PASS"), ("evaluable", True), ("result", True), ("result", False)],
)
def test_evaluation_cannot_execute_or_vacuously_pass(
    check: str, field: str, value: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["evaluation_boundary"][check][field] = value
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("boundary", generator.EXECUTION_STATUS_KEYS)
def test_runtime_boundary_cannot_become_executed(boundary: str) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["execution_boundary"][boundary] = "EXECUTED"
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
def test_action_count_requires_exact_integer_zero(
    action: str, replacement: object
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("selection_boundary")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["selection_boundary"]["unknown"] = None


def _reverse_dependencies(value: dict[str, Any]) -> None:
    value["dependencies"] = {"unknown": None, **value["dependencies"]}


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_dependencies, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {schema_version: 1}\ndocument: {schema_version: 1}\n",
        b"document: &shared {schema_version: 1}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {executable: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path, payload: bytes
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(
        (
            generator.FinanceReconciliationReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(
        b"x" * (generator.MAX_SOURCE_BYTES + 1)
    )
    with pytest.raises(
        (
            generator.FinanceReconciliationReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
    isolated_repository: Path, tmp_path: Path
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize("relative", generator.GENERATED_PATHS)
def test_output_symlink_target_is_rejected(
    isolated_repository: Path, tmp_path: Path, relative: Path
) -> None:
    target = isolated_repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / f"outside-{target.name}"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_path_traversal_is_rejected(
    isolated_repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


BOUND_INPUT_PATHS = tuple(
    path for path, _digest in generator._contract_artifacts(generator.load_contract())
)


@pytest.mark.parametrize("relative", BOUND_INPUT_PATHS)
def test_bound_input_byte_drift_is_rejected(
    isolated_repository: Path, relative: Path
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.FinanceReconciliationReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_does_not_echo_untrusted_value(
    isolated_repository: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    marker = "DO_NOT_ECHO_FINANCE_VALUE_834cc2"
    path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(path.read_bytes())
    contract["selection_boundary"]["reconciliation_tolerance"] = marker
    path.write_text(yaml.safe_dump(contract, sort_keys=False), encoding="utf-8")
    assert generator.main_for_root(isolated_repository, []) == 1
    captured = capsys.readouterr()
    assert marker not in captured.out and marker not in captured.err
