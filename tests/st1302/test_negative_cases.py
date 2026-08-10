"""Hostile closed-boundary tests for the ST-1302 owner builder."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, cast

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import (
    build_st1302_provider_fact_commit_reference_plan as generator,
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
        ("vocabularies", "mapping_defined", True),
        ("namespace_separation", "equivalence_inferred", True),
        ("unresolved_inconsistency", "resolved", True),
        ("collections", "canonical_row_count", 0),
        ("collections", "provider_fact_count", 0),
        ("collections", "commission_event_count", 0),
        ("collections", "emitted_event_count", 0),
        ("collections", "write_count", 0),
        ("collections", "amount_total_jpy", 0),
        ("collections", "empty_means_zero", True),
        ("evaluation_boundary", "vacuous_pass_allowed", True),
        ("verification_boundary", "TST-008", "PASS"),
        ("verification_boundary", "TST-030", "PASS"),
        ("verification_boundary", "formal_validation", "PASS"),
        ("verification_boundary", "story_acceptance", True),
        ("verification_boundary", "decision", "READY"),
    ],
)
def test_false_execution_mapping_or_completion_claim_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    contract[section][field] = value
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("selection_boundary", "source_sha256", "a" * 64),
        ("selection_boundary", "preview_hash", "b" * 64),
        ("selection_boundary", "provider_identity", "provider"),
        ("selection_boundary", "period", "2026-08"),
        ("selection_boundary", "fx_policy", "invented"),
        ("selection_boundary", "cost_policy", "invented"),
        ("selection_boundary", "retention_policy", "invented"),
        ("selection_boundary", "commit_result", "COMMITTED"),
        ("collections", "canonical_rows", [{}]),
        ("collections", "provider_facts", [{}]),
        ("collections", "commission_events", [{}]),
        ("collections", "emitted_events", [{}]),
        ("collections", "writes", [{}]),
        ("diagnostic_boundary", "provider_id_allowed", True),
        ("diagnostic_boundary", "dynamic_values", ["provider"]),
    ],
)
def test_invented_selection_fact_policy_write_or_diagnostic_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("check", generator.EVALUATION_KEYS)
@pytest.mark.parametrize(
    ("field", "value"),
    [("evaluable", True), ("result", True), ("result", False)],
)
def test_evaluation_cannot_become_evaluable_or_vacuously_pass(
    check: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["evaluation_boundary"][check][field] = value
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [1, False, True, 0.0, "0"])
@pytest.mark.parametrize("action", generator.ACTION_COUNT_KEYS)
def test_non_exact_integer_zero_action_count_is_rejected(
    action: str,
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_boundary"]["action_counts"][action] = replacement
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("selection_boundary")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["selection_boundary"]["unknown"] = None


def _reverse_predecessor_files(value: dict[str, Any]) -> None:
    value["predecessor"]["artifacts"] = dict(
        reversed(tuple(value["predecessor"]["artifacts"].items()))
    )


def _reverse_actions(value: dict[str, Any]) -> None:
    counts = value["execution_boundary"]["action_counts"]
    value["execution_boundary"]["action_counts"] = dict(reversed(tuple(counts.items())))


@pytest.mark.parametrize(
    "mutation",
    [_remove_top, _add_top, _add_nested, _reverse_predecessor_files, _reverse_actions],
)
def test_missing_unknown_and_reordered_keys_are_rejected(
    mutation: Callable[[dict[str, Any]], None],
) -> None:
    contract = cast(dict[str, Any], deepcopy(generator.load_contract()))
    mutation(contract)
    with pytest.raises(generator.ProviderFactCommitReferenceError):
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
            generator.ProviderFactCommitReferenceError,
            base.StagingDeploymentContractError,
        )
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))
    with pytest.raises(
        (
            generator.ProviderFactCommitReferenceError,
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


@pytest.mark.parametrize(
    "relative",
    [path for path, _digest in generator.REQUIRED_INPUT_ARTIFACTS],
)
def test_bound_input_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.render_outputs(isolated_repository)


def _rebind_digest(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    collection_name: str,
    relative: Path,
    digest: str,
) -> None:
    collection = getattr(generator, collection_name)
    rebound = tuple(
        (candidate, digest if candidate == relative else expected)
        for candidate, expected in collection
    )
    monkeypatch.setattr(generator, collection_name, rebound)
    monkeypatch.setattr(
        generator,
        "REQUIRED_INPUT_ARTIFACTS",
        (
            *generator.AUTHORITY_ARTIFACTS,
            *generator.PREDECESSOR_ARTIFACTS,
            *generator.REFERENCE_INPUT_ARTIFACTS,
        ),
    )
    contract = yaml.safe_load(
        (isolated_repository / generator.CONTRACT_PATH).read_bytes()
    )
    if collection_name == "PREDECESSOR_ARTIFACTS":
        contract["predecessor"]["artifacts"][relative.as_posix()] = digest
    elif collection_name == "REFERENCE_INPUT_ARTIFACTS":
        pin_name = next(
            name
            for name, value in contract["source_pins"].items()
            if value["path"] == relative.as_posix()
        )
        contract["source_pins"][pin_name]["sha256"] = digest
    else:
        authority_name = next(
            name
            for name, value in contract["authority"].items()
            if type(value) is dict and value.get("path") == relative.as_posix()
        )
        contract["authority"][authority_name]["sha256"] = digest
    (isolated_repository / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )


def test_predecessor_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = Path("python/raos/domain/finance/revenue_import.py")
    path = isolated_repository / relative
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            'UNVERIFIED = "UNVERIFIED"',
            'VERIFIED = "VERIFIED"',
            1,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_digest(
        isolated_repository,
        monkeypatch,
        collection_name="PREDECESSOR_ARTIFACTS",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.render_outputs(isolated_repository)


def test_canonical_story_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.STORY_PATH
    path = isolated_repository / relative
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "- id: ST-1302\n  epic_id: EPIC-13",
            "- id: ST-1302\n  epic_id: EPIC-CHANGED",
            1,
        ),
        encoding="utf-8",
    )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_digest(
        isolated_repository,
        monkeypatch,
        collection_name="AUTHORITY_ARTIFACTS",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.render_outputs(isolated_repository)


def test_reference_semantic_drift_fails_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = generator.COMMIT_JOB_SCHEMA_PATH
    path = isolated_repository / relative
    schema = json.loads(path.read_bytes())
    schema["allOf"][1]["properties"]["payload"]["properties"]["preview_hash"] = {
        "type": "string"
    }
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _rebind_digest(
        isolated_repository,
        monkeypatch,
        collection_name="REFERENCE_INPUT_ARTIFACTS",
        relative=relative,
        digest=digest,
    )
    with pytest.raises(generator.ProviderFactCommitReferenceError):
        generator.render_outputs(isolated_repository)


def test_failure_does_not_echo_untrusted_contract_value(
    isolated_repository: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    marker = "DO_NOT_ECHO_PROVIDER_IDENTIFIER_9b5de4"
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    contract["selection_boundary"]["provider_identity"] = marker
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False), encoding="utf-8"
    )
    assert generator.main_for_root(isolated_repository, []) == 1
    captured = capsys.readouterr()
    assert marker not in captured.out
    assert marker not in captured.err
