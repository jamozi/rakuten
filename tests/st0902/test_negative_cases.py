"""Hostile-input and fail-closed tests for the ST-0902 builder."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

import pytest
import yaml

from scripts import build_st0902_final_approval_reference_plan as generator
from scripts import build_st1505_staging_deployment as base


@pytest.mark.parametrize(
    ("section", "field", "value"),
    [
        ("document", "executable", True),
        ("document", "decision", "READY"),
        ("document", "readiness", "READY"),
        ("document", "story_acceptance", True),
        ("document", "approval_authority", True),
        ("document", "rejection_authority", True),
        ("document", "revocation_authority", True),
        ("document", "publication_permitted", True),
        ("document", "production_eligible", True),
        ("pro_assistance", "status", "CAPTURED"),
        ("pro_assistance", "authority", "UNAPPROVED_PROPOSAL"),
        ("pro_assistance", "proposal_captured", True),
        ("pro_assistance", "content_used", True),
        ("execution_defaults", "runtime_reader", "IMPLEMENTED"),
        ("execution_defaults", "network", "EXECUTED"),
        ("execution_defaults", "filesystem_runtime", "EXECUTED"),
        ("execution_defaults", "clock", "EXECUTED"),
        ("execution_defaults", "database", "EXECUTED"),
        ("execution_defaults", "api", "EXECUTED"),
        ("execution_defaults", "job", "EXECUTED"),
        ("execution_defaults", "event", "EXECUTED"),
        ("execution_defaults", "audit", "EXECUTED"),
        ("execution_defaults", "idempotency", "EXECUTED"),
        ("execution_defaults", "approval", "EXECUTED"),
        ("execution_defaults", "rejection", "EXECUTED"),
        ("execution_defaults", "revocation", "EXECUTED"),
        ("execution_defaults", "publication", "EXECUTED"),
        ("verification_defaults", "formal_tst_012", "PASS"),
        ("verification_defaults", "formal_tst_021", "PASS"),
        ("verification_defaults", "live", "PASS"),
        ("verification_defaults", "staging", "READY"),
        ("verification_defaults", "release", "READY"),
        ("verification_defaults", "production", "READY"),
    ],
)
def test_authority_execution_and_false_readiness_claims_are_rejected(
    section: str,
    field: str,
    value: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    contract[section][field] = value

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda value: value.pop("hard_gates"),
        lambda value: value.update({"unknown": None}),
        lambda value: value["authority"]["sources"].reverse(),
        lambda value: value["dependencies"].reverse(),
        lambda value: value["hard_gates"].reverse(),
        lambda value: value["hard_gates"][0].update({"unknown": None}),
        lambda value: value["record_defaults"]["rejection"].update(
            {"empty_records_interpretation": "ZERO_REJECTED"}
        ),
        lambda value: value["record_defaults"]["approval"].update(
            {"records": ["approval-1"]}
        ),
        lambda value: value["record_defaults"]["rejection"].update(
            {"records": ["rejection-1"]}
        ),
        lambda value: value["record_defaults"]["revocation"].update(
            {"records": ["revocation-1"]}
        ),
        lambda value: value["implementation_boundary"].update(
            {"runtime_modules": ["python/raos/application/final_approval.py"]}
        ),
    ],
)
def test_missing_unknown_reordered_record_and_boundary_drift_are_rejected(
    mutation: object,
) -> None:
    contract = deepcopy(generator.load_contract())
    mutation(contract)  # type: ignore[operator]

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.validate_contract(contract)


def test_bool_does_not_bypass_closed_string_or_list_types() -> None:
    contract = deepcopy(generator.load_contract())
    contract["record_defaults"]["approval"]["records"] = False

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.validate_contract(contract)


@pytest.mark.parametrize(
    "payload",
    [
        b"document: {}\ndocument: {}\n",
        b"document: &shared {}\nauthority: *shared\n",
        b"document: !!python/object/apply:os.system [id]\n",
        b"base: &base {enabled: false}\nmerged: {<<: *base}\n",
    ],
)
def test_yaml_duplicate_alias_tag_and_merge_are_rejected(
    isolated_repository: Path,
    payload: bytes,
) -> None:
    (isolated_repository / generator.CONTRACT_PATH).write_bytes(payload)

    with pytest.raises(
        (generator.FinalApprovalReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_oversized_contract_is_rejected(isolated_repository: Path) -> None:
    path = isolated_repository / generator.CONTRACT_PATH
    path.write_bytes(b"x" * (generator.MAX_SOURCE_BYTES + 1))

    with pytest.raises(
        (generator.FinalApprovalReferenceError, base.StagingDeploymentContractError)
    ):
        generator.load_contract(isolated_repository)


def test_symlink_contract_is_rejected(
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


def test_symlink_authority_ancestor_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    authority = isolated_repository / generator.STORY_PATH
    outside_directory = tmp_path / "outside-authority"
    authority.parent.rename(outside_directory)
    authority.parent.symlink_to(outside_directory, target_is_directory=True)

    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


def test_output_symlink_target_is_rejected(
    isolated_repository: Path,
    tmp_path: Path,
) -> None:
    target = isolated_repository / generator.REFERENCE_PLAN_PATH
    target.parent.mkdir(parents=True)
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    target.symlink_to(outside)

    with pytest.raises(base.StagingDeploymentContractError):
        generator.build(isolated_repository)
    assert outside.read_bytes() == b"outside"


def test_path_traversal_is_rejected(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "CONTRACT_PATH", Path("../outside.yaml"))

    with pytest.raises(base.StagingDeploymentContractError):
        generator.load_contract(isolated_repository)


@pytest.mark.parametrize(
    "relative",
    [
        generator.STORY_PATH,
        generator.MASTER_TRACE_PATH,
        generator.ROLE_MATRIX_PATH,
        generator.ADMIN_API_PATH,
        generator.APPROVAL_GRANTED_EVENT_PATH,
        Path("changes/st-0305/contracts/physical/publishing-guards.sql"),
        Path(
            "changes/st-0605/contracts/claim-evidence-coverage-reference-plan.v1.yaml"
        ),
        Path("python/raos/domain/publishing/review_decision_operations.py"),
        generator.HELPER_PATH,
    ],
)
def test_authority_dependency_or_helper_byte_drift_is_rejected(
    isolated_repository: Path,
    relative: Path,
) -> None:
    path = isolated_repository / relative
    path.write_bytes(path.read_bytes() + b"\ndrift\n")

    with pytest.raises(
        (generator.FinalApprovalReferenceError, base.StagingDeploymentContractError)
    ):
        generator.render_outputs(isolated_repository)


def _rebind_source(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: Path,
) -> None:
    digest = hashlib.sha256((isolated_repository / relative).read_bytes()).hexdigest()
    rebound = tuple(
        (role, path, digest if path == relative.as_posix() else expected)
        for role, path, expected in generator.EXPECTED_SOURCES
    )
    monkeypatch.setattr(generator, "EXPECTED_SOURCES", rebound)
    contract_path = isolated_repository / generator.CONTRACT_PATH
    contract = yaml.safe_load(contract_path.read_bytes())
    for source in contract["authority"]["sources"]:
        if source["uri"] == f"repo://{relative.as_posix()}":
            source["sha256"] = digest
    contract_path.write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def test_story_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.STORY_PATH
    catalog = yaml.safe_load(path.read_bytes())
    story = next(row for row in catalog["stories"] if row["id"] == "ST-0902")
    story["acceptance_criteria"] = ["self approval allowed"]
    path.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _rebind_source(isolated_repository, monkeypatch, generator.STORY_PATH)

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.render_outputs(isolated_repository)


def test_step_up_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.ROLE_MATRIX_PATH
    catalog = yaml.safe_load(path.read_bytes())
    permission = next(
        row for row in catalog["permissions"] if row["action"] == "final_approve"
    )
    permission["step_up_required"] = True
    path.write_text(
        yaml.safe_dump(catalog, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _rebind_source(isolated_repository, monkeypatch, generator.ROLE_MATRIX_PATH)

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.render_outputs(isolated_repository)


def test_api_decision_semantic_drift_is_rejected_even_when_hash_is_rebound(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.ADMIN_API_PATH
    api = yaml.safe_load(path.read_bytes())
    api["components"]["schemas"]["ApprovalRequest"]["properties"]["decision"][
        "enum"
    ] = ["APPROVED"]
    path.write_text(
        yaml.safe_dump(api, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    _rebind_source(isolated_repository, monkeypatch, generator.ADMIN_API_PATH)

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.render_outputs(isolated_repository)


def test_duplicate_event_json_key_is_rejected_after_hash_rebind(
    isolated_repository: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = isolated_repository / generator.APPROVAL_GRANTED_EVENT_PATH
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace('"$schema":', '"$schema": "duplicate",\n  "$schema":', 1),
        encoding="utf-8",
    )
    _rebind_source(
        isolated_repository,
        monkeypatch,
        generator.APPROVAL_GRANTED_EVENT_PATH,
    )

    with pytest.raises(generator.FinalApprovalReferenceError):
        generator.render_outputs(isolated_repository)


def test_hostile_value_is_rejected_without_echoing_it() -> None:
    canary = "secret-private-pro-run-canary"
    contract = deepcopy(generator.load_contract())
    contract["pro_assistance"]["status"] = canary

    with pytest.raises(generator.FinalApprovalReferenceError) as caught:
        generator.validate_contract(contract)
    assert canary not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("arguments", [["--checks"], ["--check=true"], ["build"]])
def test_cli_aliases_and_extra_commands_are_rejected(arguments: list[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        generator.parse_args(arguments)
    assert caught.value.code == 2
