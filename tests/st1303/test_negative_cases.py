"""Hostile closed-boundary tests for the ST-1303 owner builder."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import (
    build_st1303_attribution_engine_reference_plan as generator,
)


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
        ("verification_boundary", "TST-007", "PASS"),
        ("verification_boundary", "TST-030", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "story_acceptance", True),
        ("verification_boundary", "live_evidence", True),
        ("verification_boundary", "decision", "READY"),
    ],
)
def test_false_execution_or_completion_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract[section][field] = value
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "field",
    [
        "method_version",
        "input_hash",
        "identity_mapping",
        "event_provider_link",
        "direct_provider_key",
        "session_pseudonym",
        "eligible_click_rule",
        "lookback_window",
        "time_bucket",
        "timezone",
        "article_active_window",
        "provider_timestamp_rule",
        "weight_rule",
        "confidence_rule",
        "confidence_scale_mapping",
        "conservation_basis",
        "conservation_tolerance",
        "rounding_policy",
        "remainder_policy",
        "tie_breaker",
        "correction_policy",
        "supersession_policy",
        "run_id",
        "run_timestamp",
        "source_watermarks",
        "job_type",
        "persistence_policy",
        "repository",
        "unit_of_work",
        "transaction",
        "approval_policy",
        "retention_policy",
    ],
)
def test_invented_method_identity_window_confidence_run_or_persistence_is_rejected(
    field: str,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["selection_boundary"][field] = "invented"
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("field", ["consent_eligibility", "event_eligibility"])
def test_unevaluated_eligibility_cannot_be_selected(field: str) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["selection_boundary"][field] = "ELIGIBLE"
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("collection", generator.COLLECTION_KEYS)
def test_event_fact_candidate_allocation_run_emit_or_write_is_rejected(
    collection: str,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["collections"][collection] = [{"invented": True}]
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("field", (*generator.COUNT_KEYS, *generator.TOTAL_KEYS))
@pytest.mark.parametrize("value", [0, 1, -1, 0.0, "0"])
def test_unknown_count_or_total_cannot_be_coerced_to_a_value(
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["collections"][field] = value
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("check", generator.EVALUATION_KEYS)
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "PASS"),
        ("evaluable", True),
        ("result", True),
        ("result", False),
    ],
)
def test_evaluation_cannot_become_executed_evaluable_or_vacuously_pass(
    check: str,
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["evaluation_boundary"][check][field] = value
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("boundary", generator.EXECUTION_STATUS_KEYS)
def test_runtime_boundary_cannot_become_executed(boundary: str) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["execution_boundary"][boundary] = "EXECUTED"
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_integer_zero_action_count_is_rejected(
    action: str,
    replacement: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("selection_boundary")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["selection_boundary"]["unknown"] = None


def _reverse_dependencies(value: dict[str, Any]) -> None:
    dependencies = value["dependencies"]
    value["dependencies"] = dict(reversed(tuple(dependencies.items())))


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
    with pytest.raises(generator.AttributionEngineReferenceError):
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
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(
        (
            generator.AttributionEngineReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (
            generator.AttributionEngineReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_or_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)
    contract.unlink()
    outside.replace(contract)
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize("relative", generator.GENERATED_PATHS)
def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
    relative: Path,
) -> None:
    target = isolated_repository / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / f"outside-{target.name}"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_output_symlink_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    generated = isolated_repository / generator.REFERENCE_PLAN_PATH.parent
    outside = tmp_path / "generated"
    outside.mkdir()
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.symlink_to(outside, target_is_directory=True)
    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert not tuple(outside.iterdir())


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


BOUND_INPUT_PATHS = tuple(
    path for path, _digest in generator._contract_artifacts(generator.load_contract())
)


@pytest.mark.parametrize("relative", BOUND_INPUT_PATHS)
def test_bound_input_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.AttributionEngineReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_does_not_echo_untrusted_contract_value(
    isolated_repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "DO_NOT_ECHO_ATTRIBUTION_IDENTITY_9b5de4"
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    contract["selection_boundary"]["identity_mapping"] = marker
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    assert generator.main_for_root(isolated_repository, []) == 1
    captured = capsys.readouterr()
    assert marker not in captured.out
    assert marker not in captured.err
