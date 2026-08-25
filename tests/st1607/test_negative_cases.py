from __future__ import annotations

import ast
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from scripts import build_st1505_staging_deployment as base
from scripts import build_st1607_gate_evidence_pack as builder


@pytest.mark.parametrize(
    ("section", "key", "invalid"),
    [
        ("document", "acceptance_criteria_satisfied", True),
        ("snapshot_boundary", "target_release_version", "release-v1"),
        ("snapshot_boundary", "snapshot_observed_at", "2026-08-16T00:00:00Z"),
        ("authority_boundary", "owner_gate_approval_authority", "GRANTED"),
        ("authority_boundary", "release_authority", "GRANTED"),
        ("authority_boundary", "production_authority", "GRANTED"),
        ("execution_boundary", "executable", True),
        ("execution_boundary", "input_size_limit_bytes", 16 * 1024 * 1024),
        ("execution_boundary", "external_action_count", 1),
        ("evidence_boundary", "formal_tst_032", "PASS"),
        ("evidence_boundary", "gate_pass_claim", True),
        ("evidence_boundary", "release_eligible", True),
        ("evidence_boundary", "production_ready", True),
    ],
)
def test_boundary_escalation_is_rejected(
    section: str,
    key: str,
    invalid: object,
    contract: dict[str, object],
) -> None:
    mapping = contract[section]
    assert isinstance(mapping, dict)
    mapping[key] = invalid
    with pytest.raises(builder.GateEvidencePackError):
        builder.validate_contract(contract)


def test_gate_pass_blocker_removal_and_mapping_inference_are_rejected(
    contract: dict[str, object],
) -> None:
    mutations = []

    passed = copy.deepcopy(contract)
    passed_report = passed["gate_report"]
    assert isinstance(passed_report, dict)
    passed_gates = passed_report["gates"]
    assert isinstance(passed_gates, list)
    passed_gates[0]["status"] = "PASS"
    mutations.append(passed)

    missing = copy.deepcopy(contract)
    blockers = missing["global_blockers"]
    assert isinstance(blockers, list)
    blockers.pop()
    mutations.append(missing)

    mapped = copy.deepcopy(contract)
    mapped_report = mapped["gate_report"]
    assert isinstance(mapped_report, dict)
    policy = mapped_report["mapping_policy"]
    assert isinstance(policy, dict)
    policy["suite_to_gate_mapping"] = {"TST-032": ["GATE-4"]}
    mutations.append(mapped)

    for mutation in mutations:
        with pytest.raises(builder.GateEvidencePackError):
            builder.validate_contract(mutation)


def test_qualifying_evidence_or_approval_injection_is_rejected(
    contract: dict[str, object],
) -> None:
    evidence = contract["required_evidence"]
    assert isinstance(evidence, list)
    evidence[0]["qualifying_evidence_references"] = ["repo://fabricated.json"]
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(contract)
    assert error.value.code == "SAFE_BOUNDARY_DRIFT"


def test_recorded_or_absent_identity_cannot_be_promoted(
    contract: dict[str, object],
) -> None:
    invalid_commit = copy.deepcopy(contract)
    snapshot = invalid_commit["snapshot_boundary"]
    assert isinstance(snapshot, dict)
    snapshot["local_base_commit"] = "A" * 40
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(invalid_commit)
    assert error.value.code == "INVALID_TYPED_IDENTITY"

    promoted_base = copy.deepcopy(contract)
    snapshot = promoted_base["snapshot_boundary"]
    assert isinstance(snapshot, dict)
    snapshot["local_base_commit_qualifying_evidence"] = True
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(promoted_base)
    assert error.value.code == "IDENTITY_PROMOTION_FORBIDDEN"

    fabricated_freeze = copy.deepcopy(contract)
    snapshot = fabricated_freeze["snapshot_boundary"]
    assert isinstance(snapshot, dict)
    snapshot["source_freeze_status"] = "RECORDED"
    snapshot["source_freeze_identifier"] = "0" * 64
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(fabricated_freeze)
    assert error.value.code == "IDENTITY_PROMOTION_FORBIDDEN"

    fabricated_reviewed_tree = copy.deepcopy(contract)
    snapshot = fabricated_reviewed_tree["snapshot_boundary"]
    assert isinstance(snapshot, dict)
    snapshot["reviewed_implementation_tree_commit_status"] = "RECORDED"
    snapshot["reviewed_implementation_tree_commit"] = "0" * 40
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(fabricated_reviewed_tree)
    assert error.value.code == "IDENTITY_PROMOTION_FORBIDDEN"


def test_unknown_missing_duplicate_and_aliased_contract_shape_is_rejected(
    contract: dict[str, object], repository_copy: Path
) -> None:
    unknown = copy.deepcopy(contract)
    unknown["unknown"] = None
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(unknown)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    missing = copy.deepcopy(contract)
    del missing["global_blockers"]
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(missing)
    assert error.value.code == "CONTRACT_SCHEMA_DRIFT"

    contract_path = repository_copy / builder.CONTRACT_PATH
    original = contract_path.read_text()
    contract_path.write_text(original + "document: {}\n")
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.load_contract(repository_copy)
    assert error.value.code == "YAML_INVALID"
    contract_path.write_text("a: &x {}\nb: *x\n")
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.load_contract(repository_copy)
    assert error.value.code == "YAML_ALIAS_FORBIDDEN"


def test_semantically_tampered_dependency_is_rejected_after_digest_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path(
        "changes/st-1605/generated/"
        "failure-injection-drill.local-synthetic-evidence.v1.json"
    )
    path = repository_copy / relative
    report = json.loads(path.read_text())
    report["evidence_boundary"]["st_1607_eligible"] = True
    path.write_text(json.dumps(report, indent=2) + "\n")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    dependency_hashes = dict(builder.EXPECTED_DEPENDENCY_HASHES)
    dependency_hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_DEPENDENCY_HASHES", dependency_hashes)
    raw = base.load_yaml(repository_copy / builder.CONTRACT_PATH)
    assert isinstance(raw, dict)
    raw["dependency_bindings"]["st_1605"]["artifacts"][1]["sha256"] = digest
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "DEPENDENCY_SEMANTIC_DRIFT"


def test_semantically_tampered_decision_report_is_rejected_after_digest_rebind(
    repository_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    relative = Path("changes/st-0006/gate-blocker-report.v1.yaml")
    path = repository_copy / relative
    report = base.load_yaml(path)
    assert isinstance(report, dict)
    report["decisions"][0]["blocked_targets"] = ["GATE-0"]
    path.write_text(yaml.safe_dump(report, sort_keys=False, allow_unicode=True))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    decision_hashes = dict(builder.EXPECTED_DECISION_GATE_HASHES)
    decision_hashes[relative.as_posix()] = digest
    monkeypatch.setattr(builder, "EXPECTED_DECISION_GATE_HASHES", decision_hashes)
    raw = base.load_yaml(repository_copy / builder.CONTRACT_PATH)
    assert isinstance(raw, dict)
    raw["decision_gate_binding"]["artifacts"][1]["sha256"] = digest
    with pytest.raises(builder.GateEvidencePackError) as error:
        builder.validate_contract(raw, repository_copy)
    assert error.value.code == "DECISION_REPORT_DRIFT"


def test_builder_has_no_external_execution_surface() -> None:
    source = (builder.REPO_ROOT / builder.GENERATOR_PATH).read_text()
    tree = ast.parse(source)
    forbidden_imports = {
        "boto3",
        "botocore",
        "requests",
        "httpx",
        "importlib",
        "socket",
        "subprocess",
        "scripts",
        "sqlalchemy",
        "psycopg",
        "terraform",
    }
    observed: set[str] = set()
    repository_helper_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            observed.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            observed.add(node.module.split(".")[0])
            if node.module == "scripts":
                repository_helper_imports.update(alias.name for alias in node.names)
    assert observed.isdisjoint(forbidden_imports)
    for token in (
        "os.environ",
        "getenv(",
        "Popen(",
        "subprocess.run",
        "requests.",
        "boto3.",
        "release_create",
        "status_apply(",
        "deploy_staging",
    ):
        assert token not in source
    assert "build_st1505_staging_deployment" not in repository_helper_imports
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"compile", "eval", "exec", "__import__"}
        for node in ast.walk(tree)
    )


def test_cli_accepts_only_build_or_check() -> None:
    assert builder.parse_args([]).check is False
    assert builder.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit) as error:
        builder.parse_args(["--apply"])
    assert error.value.code == 2


@pytest.mark.parametrize(
    "python_flags",
    ((), ("-I",), ("-B",)),
)
def test_cli_requires_isolated_no_bytecode_mode(
    python_flags: tuple[str, ...],
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            *python_flags,
            str(builder.REPO_ROOT / builder.GENERATOR_PATH),
            "--check",
        ],
        cwd=builder.REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    expected = (
        "NO_BYTECODE_MODE_REQUIRED"
        if python_flags == ("-I",)
        else "ISOLATED_MODE_REQUIRED"
    )
    assert expected in result.stderr
    assert result.stdout == ""
