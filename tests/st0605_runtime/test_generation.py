from __future__ import annotations

from collections.abc import Callable
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any, cast

import pytest
import yaml

from raos.adapters.recorded_claim_evidence import (
    load_recorded_claim_evidence_fixture,
)
from raos.domain.evidence.claim_evidence import (
    CoverageStatus,
    ValidationAttestationKind,
    evaluate_claim_evidence,
    validation_attestation_owner_binding,
)
from scripts import build_st0605_claim_evidence_runtime as generator


ROOT = Path(__file__).resolve().parents[2]


def _contract_copy(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    root = tmp_path / "repository"
    for relative, _digest in (
        *generator.SOURCE_BINDINGS,
        *generator.IMPLEMENTATION_INPUT_BINDINGS,
        *generator.ATTESTATION_OWNER_INPUT_BINDINGS,
    ):
        source = ROOT / relative
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    contract_target = root / generator.CONTRACT_PATH
    contract_target.parent.mkdir(parents=True, exist_ok=True)
    loaded = yaml.safe_load((ROOT / generator.CONTRACT_PATH).read_bytes())
    assert isinstance(loaded, dict)
    contract = cast(dict[str, Any], copy.deepcopy(loaded))
    return root, contract


def _write_contract(root: Path, contract: dict[str, Any]) -> None:
    (root / generator.CONTRACT_PATH).write_text(
        yaml.safe_dump(contract, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


def _set_nested(
    contract: dict[str, Any],
    path: tuple[str, ...],
    value: object,
) -> None:
    current = contract
    for key in path[:-1]:
        nested = current[key]
        assert isinstance(nested, dict)
        current = cast(dict[str, Any], nested)
    current[path[-1]] = value


def test_owner_generator_check_is_current() -> None:
    generator.build(ROOT, check=True)


def test_generation_toolchain_is_exactly_locked() -> None:
    generator._validate_generation_toolchain()
    assert pytest.__version__ == generator.EXPECTED_PYTEST_VERSION


def test_generation_rejects_python_toolchain_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator, "EXPECTED_PYTHON_VERSION", (0, 0, 0))
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="GENERATION_PYTHON_TOOLCHAIN_DRIFT",
    ):
        generator._validate_generation_toolchain()


def test_generation_rejects_pyyaml_toolchain_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(generator.yaml, "__version__", "0.0.0")
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="GENERATION_PYYAML_TOOLCHAIN_DRIFT",
    ):
        generator._validate_generation_toolchain()


@pytest.mark.parametrize(
    ("distribution", "code"),
    [
        ("pydantic", "GENERATION_PYDANTIC_TOOLCHAIN_DRIFT"),
        ("pydantic-core", "GENERATION_PYDANTIC_CORE_TOOLCHAIN_DRIFT"),
        ("pytest", "GENERATION_PYTEST_TOOLCHAIN_DRIFT"),
    ],
)
def test_generation_rejects_imported_and_verification_dependency_drift(
    monkeypatch: pytest.MonkeyPatch,
    distribution: str,
    code: str,
) -> None:
    real_version = generator.distribution_version

    def drift_selected_distribution(name: str) -> str:
        if name == distribution:
            return "0.0.0"
        return real_version(name)

    monkeypatch.setattr(
        generator,
        "distribution_version",
        drift_selected_distribution,
    )
    with pytest.raises(generator.RuntimeGenerationError, match=code):
        generator._validate_generation_toolchain()


def test_generated_fixture_is_hash_bound_and_executable() -> None:
    payload = (ROOT / generator.FIXTURE_PATH).read_bytes()
    snapshot = load_recorded_claim_evidence_fixture(payload)
    report = evaluate_claim_evidence(snapshot)
    assert report.status is CoverageStatus.PASS
    assert report.findings == ()
    assert report.complete_claim_set_sha256 is not None
    decoded = json.loads(payload)
    assert decoded["article"]["complete_claim_set_sha256"] == (
        report.complete_claim_set_sha256.value
    )


def test_runtime_manifest_binds_sources_fixture_and_closed_authority() -> None:
    manifest = yaml.safe_load((ROOT / generator.MANIFEST_PATH).read_bytes())
    assert manifest["source_artifact_count"] == len(generator.SOURCE_PATHS)
    assert manifest["source_artifacts"] == [
        {
            "uri": f"repo://{relative.as_posix()}",
            "bytes": (ROOT / relative).stat().st_size,
            "sha256": hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(),
        }
        for relative in generator.SOURCE_PATHS
    ]
    assert set(generator.DIRECT_EXECUTABLE_DEPENDENCY_PATHS).issubset(
        generator.SOURCE_PATHS
    )
    assert {relative for relative, _digest in generator.SOURCE_BINDINGS}.issubset(
        generator.SOURCE_PATHS
    )
    assert {
        relative for relative, _digest in generator.IMPLEMENTATION_INPUT_BINDINGS
    }.issubset(generator.SOURCE_PATHS)
    assert {
        relative for relative, _digest in generator.ATTESTATION_OWNER_INPUT_BINDINGS
    }.issubset(generator.SOURCE_PATHS)
    assert set(generator.RUNTIME_PACKAGE_BOUNDARY_PATHS).issubset(
        generator.SOURCE_PATHS
    )
    assert set(generator.LOCKED_TOOLCHAIN_PATHS).issubset(generator.SOURCE_PATHS)
    fixture = (ROOT / generator.FIXTURE_PATH).read_bytes()
    assert manifest["generated_artifacts"] == [
        {
            "uri": f"repo://{generator.FIXTURE_PATH.as_posix()}",
            "bytes": len(fixture),
            "sha256": hashlib.sha256(fixture).hexdigest(),
        }
    ]
    assert manifest["authority"] == {
        "publication_authorized": False,
        "production_eligible": False,
        "formal_test_status": "NOT_EXECUTED",
        "live": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }
    assert manifest["generation"] == {
        "owner": f"repo://{generator.GENERATOR_PATH.as_posix()}",
        "command": (".venv/bin/python scripts/build_st0605_claim_evidence_runtime.py"),
        "toolchain": {
            "lock": "repo://uv.lock",
            "project": "repo://pyproject.toml",
            "python_implementation": "CPython",
            "python_version": "3.14.6",
            "pyyaml_version": "6.0.3",
            "pydantic_version": "2.13.4",
            "pydantic_core_version": "2.46.4",
            "pytest_version": "9.1.1",
        },
    }


def test_contract_keeps_policy_persistence_and_ai_vocabularies_unmapped() -> None:
    contract = generator.load_contract(ROOT)
    boundary = contract["vocabulary_boundary"]
    assert boundary["inferred_persistence_mapping"] is False
    assert boundary["inferred_ai_mapping"] is False
    assert contract["precedence"]["predictive_default"] == "BLOCKED_IN_MVP"
    assert contract["thresholds"]["arithmetic"] == "INTEGER_CROSS_MULTIPLICATION"
    assert contract["thresholds"]["zero_denominator"] == "UNEVALUABLE"


@pytest.mark.parametrize(
    ("path", "value", "code"),
    [
        (
            ("runtime", "publication_authorized"),
            True,
            "CONTRACT_RUNTIME_INVALID",
        ),
        (
            ("runtime", "repository_write"),
            True,
            "CONTRACT_RUNTIME_INVALID",
        ),
        (
            ("runtime", "production_eligible"),
            True,
            "CONTRACT_RUNTIME_INVALID",
        ),
        (
            ("policy_binding", "policy_version"),
            "1.0.1",
            "CONTRACT_POLICY_BINDING_INVALID",
        ),
        (
            ("policy_binding", "policy_sha256"),
            "f" * 64,
            "CONTRACT_POLICY_BINDING_INVALID",
        ),
        (
            ("thresholds", "all_verifiable", "total_denominator"),
            100.0,
            "CONTRACT_THRESHOLDS_INVALID",
        ),
        (
            ("precedence", "predictive_default"),
            "ALLOWED",
            "CONTRACT_PRECEDENCE_INVALID",
        ),
        (
            ("execution_boundary", "network"),
            "ALLOWED",
            "CONTRACT_EXECUTION_BOUNDARY_INVALID",
        ),
        (
            ("execution_boundary", "pure_evaluator_authority"),
            "PUBLICATION",
            "CONTRACT_EXECUTION_BOUNDARY_INVALID",
        ),
        (
            ("execution_boundary", "trusted_snapshot_resolution"),
            "CALLER_SUPPLIED",
            "CONTRACT_EXECUTION_BOUNDARY_INVALID",
        ),
        (
            ("execution_boundary", "recorded_attestation_decision"),
            "AUTHENTICATION",
            "CONTRACT_EXECUTION_BOUNDARY_INVALID",
        ),
        (
            ("verification_boundary", "formal_validation"),
            "PASS",
            "CONTRACT_VERIFICATION_BOUNDARY_INVALID",
        ),
        (
            ("vocabulary_boundary", "inferred_persistence_mapping"),
            True,
            "CONTRACT_VOCABULARY_INVALID",
        ),
        (
            ("vocabulary_boundary", "inferred_ai_mapping"),
            True,
            "CONTRACT_VOCABULARY_INVALID",
        ),
    ],
)
def test_contract_nested_authority_and_status_drift_is_rejected(
    tmp_path: Path,
    path: tuple[str, ...],
    value: object,
    code: str,
) -> None:
    root, contract = _contract_copy(tmp_path)
    _set_nested(contract, path, value)
    _write_contract(root, contract)
    with pytest.raises(generator.RuntimeGenerationError, match=code):
        generator.load_contract(root)


def test_contract_vocabulary_and_ordered_source_inventory_are_exact(
    tmp_path: Path,
) -> None:
    mutations: tuple[tuple[str, Callable[[dict[str, Any]], None]], ...] = (
        (
            "CONTRACT_VOCABULARY_INVALID",
            lambda contract: contract["vocabulary_boundary"][
                "policy_claim_types"
            ].reverse(),
        ),
        (
            "SOURCE_BINDING_INVALID",
            lambda contract: contract["source_bindings"].reverse(),
        ),
    )
    for index, (code, mutate) in enumerate(mutations):
        case_root, contract = _contract_copy(tmp_path / str(index))
        mutate(contract)
        _write_contract(case_root, contract)
        with pytest.raises(generator.RuntimeGenerationError, match=code):
            generator.load_contract(case_root)


def test_policy_source_hash_and_identity_are_cross_bound(tmp_path: Path) -> None:
    root, contract = _contract_copy(tmp_path)
    _write_contract(root, contract)
    policy_path = root / generator.SOURCE_BINDINGS[0][0]
    policy_path.write_bytes(policy_path.read_bytes() + b"\n")
    with pytest.raises(generator.RuntimeGenerationError, match="SOURCE_HASH_DRIFT"):
        generator.load_contract(root)


def test_policy_binding_and_source_inventory_cannot_be_rebased_together(
    tmp_path: Path,
) -> None:
    root, contract = _contract_copy(tmp_path)
    wrong_digest = "f" * 64
    contract["policy_binding"]["policy_sha256"] = wrong_digest
    contract["source_bindings"][0]["sha256"] = wrong_digest
    _write_contract(root, contract)
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="CONTRACT_POLICY_BINDING_INVALID",
    ):
        generator.load_contract(root)


def test_canonical_implementation_input_hash_drift_is_rejected(
    tmp_path: Path,
) -> None:
    root, contract = _contract_copy(tmp_path)
    _write_contract(root, contract)
    source_path = root / generator.IMPLEMENTATION_INPUT_BINDINGS[0][0]
    source_path.write_bytes(source_path.read_bytes() + b"\n")
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="IMPLEMENTATION_INPUT_HASH_DRIFT",
    ):
        generator.load_contract(root)


def test_attestation_owner_mapping_and_source_hash_are_cross_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, contract = _contract_copy(tmp_path)
    _write_contract(root, contract)
    assert generator.load_contract(root)["story_id"] == "ST-0605"
    real_binding = validation_attestation_owner_binding

    def wrong_owner_binding(kind: Any) -> Any:
        owner, version, digest = real_binding(kind)
        if kind is generator.ATTESTATION_OWNER_BINDINGS[0][0]:
            owner = "ST-UNKNOWN"
        return owner, version, digest

    monkeypatch.setattr(
        generator,
        "validation_attestation_owner_binding",
        wrong_owner_binding,
    )
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="ATTESTATION_OWNER_BINDING_INVALID",
    ):
        generator.load_contract(root)


def test_packet_approval_receipt_binds_current_st0604_runtime_semantics() -> None:
    owner, version, digest = validation_attestation_owner_binding(
        ValidationAttestationKind.PACKET_APPROVAL_MEMBERSHIP
    )
    assert (owner, version, digest.value) == (
        "ST-0604",
        generator.ST0604_CURRENT_CONTRACT_VERSION,
        generator.ST0604_CURRENT_CONTRACT_SHA256,
    )
    assert generator.ST0604_CURRENT_CONTRACT_PATH == Path(
        "changes/st-0604/contracts/source-packet-lifecycle-runtime.v2.json"
    )
    generator._validate_st0604_runtime_semantics(ROOT)


def test_packet_approval_runtime_semantic_drift_is_rejected(tmp_path: Path) -> None:
    root, _contract = _contract_copy(tmp_path)
    source_path = root / generator.ST0604_CURRENT_CONTRACT_PATH
    document = json.loads(source_path.read_bytes())
    document["generation_gate"]["required_lock"] = False
    source_path.write_text(
        json.dumps(document, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="ST0604_RUNTIME_SEMANTIC_DRIFT",
    ):
        generator._validate_st0604_runtime_semantics(root)


def test_attestation_owner_source_hash_drift_is_rejected(tmp_path: Path) -> None:
    root, contract = _contract_copy(tmp_path)
    _write_contract(root, contract)
    source_path = root / generator.ATTESTATION_OWNER_INPUT_BINDINGS[0][0]
    source_path.write_bytes(source_path.read_bytes() + b"\n")
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="ATTESTATION_OWNER_SOURCE_HASH_DRIFT",
    ):
        generator.load_contract(root)


def test_multi_artifact_replace_rolls_back_first_on_second_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "fixture.json"
    manifest = tmp_path / "manifest.yaml"
    fixture.write_bytes(b"old-fixture")
    manifest.write_bytes(b"old-manifest")
    fixture.chmod(0o600)
    manifest.chmod(0o640)
    real_replace = os.replace
    call_count = 0

    def fail_second_replace(source: Any, destination: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("synthetic second replace failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_second_replace)
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="GENERATION_TRANSACTION_FAILED",
    ):
        generator._replace_generated(
            (
                (fixture, b"new-fixture"),
                (manifest, b"new-manifest"),
            )
        )
    assert call_count == 4
    assert fixture.read_bytes() == b"old-fixture"
    assert manifest.read_bytes() == b"old-manifest"
    assert stat.S_IMODE(fixture.stat().st_mode) == 0o600
    assert stat.S_IMODE(manifest.stat().st_mode) == 0o640
    assert {path.name for path in tmp_path.iterdir()} == {
        "fixture.json",
        "manifest.yaml",
    }


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit])
def test_multi_artifact_replace_rolls_back_on_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_type: type[BaseException],
) -> None:
    fixture = tmp_path / "fixture.json"
    manifest = tmp_path / "manifest.yaml"
    fixture.write_bytes(b"old-fixture")
    manifest.write_bytes(b"old-manifest")
    real_replace = os.replace
    call_count = 0

    def interrupt_second_replace(source: Any, destination: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise failure_type("synthetic asynchronous interruption")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupt_second_replace)
    with pytest.raises(failure_type):
        generator._replace_generated(
            (
                (fixture, b"new-fixture"),
                (manifest, b"new-manifest"),
            )
        )
    assert call_count == 4
    assert fixture.read_bytes() == b"old-fixture"
    assert manifest.read_bytes() == b"old-manifest"
    assert {path.name for path in tmp_path.iterdir()} == {
        "fixture.json",
        "manifest.yaml",
    }


def test_stage_payload_cleans_temporary_file_on_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupt_fsync(_descriptor: int) -> None:
        raise KeyboardInterrupt("synthetic stage interruption")

    monkeypatch.setattr(os, "fsync", interrupt_fsync)
    with pytest.raises(KeyboardInterrupt):
        generator._stage_payload(
            tmp_path / "fixture.json",
            b"new-fixture",
            mode=0o600,
        )
    assert tuple(tmp_path.iterdir()) == ()


def test_rollback_failure_is_closed_for_base_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "fixture.json"
    manifest = tmp_path / "manifest.yaml"
    fixture.write_bytes(b"old-fixture")
    manifest.write_bytes(b"old-manifest")
    real_replace = os.replace
    call_count = 0

    def interrupt_then_fail_rollback(source: Any, destination: Any) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise KeyboardInterrupt("synthetic second replace interruption")
        if call_count == 3:
            raise OSError("synthetic rollback failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", interrupt_then_fail_rollback)
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="GENERATION_ROLLBACK_FAILED",
    ):
        generator._replace_generated(
            (
                (fixture, b"new-fixture"),
                (manifest, b"new-manifest"),
            )
        )


def test_post_commit_cleanup_retries_base_exception_without_partial_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "fixture.json"
    manifest = tmp_path / "manifest.yaml"
    fixture.write_bytes(b"old-fixture")
    manifest.write_bytes(b"old-manifest")
    real_unlink = Path.unlink
    call_count = 0

    def interrupt_first_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise KeyboardInterrupt("synthetic post-commit cleanup interruption")
        real_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", interrupt_first_cleanup)
    generator._replace_generated(
        (
            (fixture, b"new-fixture"),
            (manifest, b"new-manifest"),
        )
    )

    assert fixture.read_bytes() == b"new-fixture"
    assert manifest.read_bytes() == b"new-manifest"
    assert call_count >= 5
    assert {path.name for path in tmp_path.iterdir()} == {
        "fixture.json",
        "manifest.yaml",
    }


def test_persistent_post_commit_cleanup_failure_is_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = tmp_path / "fixture.json"
    manifest = tmp_path / "manifest.yaml"
    fixture.write_bytes(b"old-fixture")
    manifest.write_bytes(b"old-manifest")

    def fail_cleanup(_path: Path, *, missing_ok: bool = False) -> None:
        del missing_ok
        raise OSError("synthetic persistent post-commit cleanup failure")

    monkeypatch.setattr(Path, "unlink", fail_cleanup)
    with pytest.raises(
        generator.RuntimeGenerationError,
        match="GENERATION_POST_COMMIT_CLEANUP_FAILED",
    ):
        generator._replace_generated(
            (
                (fixture, b"new-fixture"),
                (manifest, b"new-manifest"),
            )
        )

    assert fixture.read_bytes() == b"new-fixture"
    assert manifest.read_bytes() == b"new-manifest"
