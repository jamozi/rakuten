"""Hostile closed-boundary assertions for the ST-0705 owner builder."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from scripts import build_st0705_ai_output_validation_reference_plan as generator
from scripts import build_st1505_staging_deployment as base


EXPECTED_ERRORS = (
    generator.AiOutputValidationReferenceError,
    base.StagingDeploymentContractError,
)


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "decision", "READY"),
        ("document", "story_acceptance", True),
        ("evaluation_boundary", "candidate_validation", "PASS"),
        ("evaluation_boundary", "content_validation", "PASS"),
        ("evaluation_boundary", "schema_only_acceptance_forbidden", False),
        ("evaluation_boundary", "event_emission", True),
        ("validation_state", "context", {"prompt": "invented"}),
        ("validation_state", "facts", [{"id": "invented"}]),
        ("validation_state", "findings", [{"id": "invented"}]),
        ("execution_state", "provider", "EXECUTED"),
        ("acceptance_boundary", "formal_tst_019", "PASS"),
        ("acceptance_boundary", "formal_tst_020", "PASS"),
    ],
)
def test_forbidden_evaluation_content_or_execution_is_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value
    with pytest.raises(generator.AiOutputValidationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize("replacement", [False, True, 0.0, "0"])
def test_bool_float_and_string_do_not_bypass_exact_integer_zero(
    replacement: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract["execution_state"]["action_counts"]["validation"] = replacement
    with pytest.raises(generator.AiOutputValidationReferenceError):
        generator.validate_contract(contract)


def _remove_top(value: dict[str, Any]) -> None:
    value.pop("acceptance_boundary")


def _add_top(value: dict[str, Any]) -> None:
    value["unknown"] = None


def _add_nested(value: dict[str, Any]) -> None:
    value["evaluation_boundary"]["unknown"] = None


def _reverse_prohibited(value: dict[str, Any]) -> None:
    value["prohibited_inferences"].reverse()


@pytest.mark.parametrize(
    "mutation", [_remove_top, _add_top, _add_nested, _reverse_prohibited]
)
def test_missing_unknown_and_reordered_contract_data_are_rejected(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]
    with pytest.raises(generator.AiOutputValidationReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"schema_version: 1\nschema_version: 1\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_duplicate_alias_tag_and_merge_yaml_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)
    with pytest.raises(EXPECTED_ERRORS):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(
        b"x" * (generator.MAX_SOURCE_BYTES + 1)
    )
    with pytest.raises(EXPECTED_ERRORS):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [*generator.AUTHORITY_PATHS, *generator.PREDECESSOR_PATHS],
)
def test_authority_or_predecessor_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")
    with pytest.raises(generator.AiOutputValidationReferenceError):
        generator.render_outputs(isolated_repository)


def test_predecessor_semantic_tamper_is_rejected_after_hash_rebind(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.ST0703_PLAN_PATH
    document = yaml.safe_load(path.read_bytes())
    document["recorded_exchange_contract"]["canonical_json"]["allow_nan"] = True
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    generator.rebind_predecessor_hash_for_test(
        root=isolated_repository,
        relative=generator.ST0703_PLAN_PATH,
        digest=digest,
        monkeypatch=monkeypatch,
    )
    with pytest.raises(generator.AiOutputValidationReferenceError):
        generator.render_outputs(isolated_repository)


def test_rebound_st0702_context_contract_still_rejects_unsafe_semantics(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.ST0702_PATHS[1]
    document = yaml.safe_load(path.read_bytes())
    document["packing_rules"]["available"][
        "silent_required_fact_truncation_forbidden"
    ] = False
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    generator.rebind_predecessor_hash_for_test(
        root=isolated_repository,
        relative=generator.ST0702_PATHS[1],
        digest=digest,
        monkeypatch=monkeypatch,
    )
    with pytest.raises(
        generator.AiOutputValidationReferenceError, match="ST0702_SEMANTIC_DRIFT"
    ):
        generator.render_outputs(isolated_repository)


def test_contract_and_output_symlinks_are_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    contract = isolated_repository / generator.CONTRACT_PATH
    outside_contract = tmp_path / "outside.yaml"
    outside_contract.write_bytes(contract.read_bytes())
    contract.unlink()
    contract.symlink_to(outside_contract)
    with pytest.raises(EXPECTED_ERRORS):
        generator.load_contract(isolated_repository)

    shutil_target = isolated_repository / generator.REFERENCE_PLAN_PATH
    shutil_target.parent.mkdir(parents=True, exist_ok=True)
    outside_output = tmp_path / "outside.json"
    outside_output.write_bytes(b"outside")
    shutil_target.symlink_to(outside_output)
    with pytest.raises(EXPECTED_ERRORS):
        generator.build(isolated_repository)
    assert outside_output.read_bytes() == b"outside"


def test_symlink_ancestor_and_path_traversal_are_rejected(
    isolated_repository: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changes = isolated_repository / "changes"
    moved = tmp_path / "changes"
    changes.rename(moved)
    changes.symlink_to(moved, target_is_directory=True)
    with pytest.raises(EXPECTED_ERRORS):
        generator.load_contract(isolated_repository)

    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))
    with pytest.raises(EXPECTED_ERRORS):
        generator.load_contract(isolated_repository)


def test_failure_is_stable_sanitized_and_does_not_echo_rejected_value() -> None:
    canary = "secret-canary-model-provider-identity"
    contract = deepcopy(generator.load_contract())
    contract["prohibited_inferences"][0] = canary
    with pytest.raises(generator.AiOutputValidationReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
