from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts import build_st1606_backup_restore_drill as builder
from scripts import build_st1505_staging_deployment as base


@pytest.mark.parametrize("field", tuple(builder.EXPECTED_SELECTIONS))
def test_any_selected_binding_fails_closed(
    field: str, contract: dict[str, object]
) -> None:
    selections = contract["selection_boundary"]
    assert isinstance(selections, dict)
    selections[field] = (
        ["selected"] if isinstance(selections[field], list) else "selected"
    )
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.validate_contract(contract)
    assert error.value.code == "SAFE_BOUNDARY_DRIFT"
    assert "selected" not in str(error.value)


@pytest.mark.parametrize("action", builder.ACTION_NAMES)
@pytest.mark.parametrize("invalid", [True, 1, 0.0, "0"])
def test_non_exact_zero_action_fails_closed(
    action: str, invalid: object, contract: dict[str, object]
) -> None:
    execution = contract["execution_boundary"]
    assert isinstance(execution, dict)
    counts = execution["action_counts"]
    assert isinstance(counts, dict)
    counts[action] = invalid
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.validate_contract(contract)
    assert error.value.code == "SAFE_BOUNDARY_DRIFT"


@pytest.mark.parametrize(
    ("section", "key", "invalid"),
    [
        ("document", "acceptance_criteria_satisfied", True),
        ("open_decision_boundary", "decision_value", "chosen"),
        ("open_decision_boundary", "automatic_deletion", "ENABLED"),
        ("recovery_environment", "activation_status", "ACTIVE"),
        ("recovery_environment", "production_data", "ALLOWED"),
        ("source_backup_boundary", "delete", "ALLOWED"),
        ("source_backup_boundary", "retention_change", "ALLOWED"),
        ("evidence_boundary", "restore_drill", "PASS"),
        ("evidence_boundary", "recoverability_claim", True),
        ("evidence_boundary", "st_1607_eligible", True),
        ("evidence_boundary", "release_eligible", True),
    ],
)
def test_boundary_escalation_is_rejected(
    section: str, key: str, invalid: object, contract: dict[str, object]
) -> None:
    mapping = contract[section]
    assert isinstance(mapping, dict)
    mapping[key] = invalid
    with pytest.raises(builder.BackupRestoreReferenceError):
        builder.validate_contract(contract)


def test_unknown_or_missing_contract_key_is_rejected(
    contract: dict[str, object],
) -> None:
    unknown = copy.deepcopy(contract)
    unknown["unknown"] = None
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.validate_contract(unknown)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"
    missing = copy.deepcopy(contract)
    del missing["reviewable_intents"]
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.validate_contract(missing)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"


def test_duplicate_yaml_key_and_alias_are_rejected(repository_copy: Path) -> None:
    contract_path = repository_copy / builder.CONTRACT_PATH
    original = contract_path.read_text()
    contract_path.write_text(original + "document: {}\n")
    with pytest.raises(base.StagingDeploymentContractError):
        builder.load_contract(repository_copy)
    contract_path.write_text("a: &x {}\nb: *x\n")
    with pytest.raises(base.StagingDeploymentContractError):
        builder.load_contract(repository_copy)


def test_semantically_tampered_predecessor_is_rejected_after_digest_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path("infra/terraform/staging/staging-deployment.reference-plan.v1.json")
    path = repository_copy / relative
    plan = json.loads(path.read_text())
    plan["activation"]["enabled"] = True
    path.write_text(json.dumps(plan, indent=2) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    predecessor_hashes = dict(builder.EXPECTED_PREDECESSOR_HASHES)
    predecessor_hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_PREDECESSOR_HASHES", predecessor_hashes)
    raw = base.load_yaml(repository_copy / builder.CONTRACT_PATH)
    assert isinstance(raw, dict)
    raw["predecessor_bindings"]["staging_deployment"]["reference_plan_sha256"] = digest
    with pytest.raises(builder.BackupRestoreReferenceError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "PREDECESSOR_SEMANTIC_DRIFT"


def test_builder_has_no_external_or_restore_execution_surface() -> None:
    source = (builder.REPO_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    forbidden_imports = {
        "boto3",
        "botocore",
        "requests",
        "httpx",
        "socket",
        "subprocess",
        "sqlalchemy",
        "psycopg",
        "terraform",
    }
    observed: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            observed.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            observed.add(node.module.split(".")[0])
    assert observed.isdisjoint(forbidden_imports)
    for token in (
        "os.environ",
        "getenv(",
        "Popen(",
        "subprocess.run",
        "requests.",
        "boto3.",
        "restore_database",
        "delete_backup",
    ):
        assert token not in source


def test_cli_accepts_only_build_or_check() -> None:
    assert builder.parse_args([]).check is False
    assert builder.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit) as error:
        builder.parse_args(["--apply"])
    assert error.value.code == 2
