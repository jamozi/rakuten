"""Fail-closed hostile cases for the ST-1505 local simulator."""

from __future__ import annotations

import copy
import json
import shutil
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from raos.adapters.disabled_deployment_identity import (
    DisabledDeploymentIdentityActivation,
)
from raos.application.ops.staging_admission import (
    LocalStagingAdmissionRun,
    LocalStagingAdmissionService,
)
from raos.domain.deployment_identity import DeploymentIdentityPolicyError
from raos.domain.ops.staging_admission import (
    LocalStagingAdmissionSpec,
    StagingAdmissionError,
    evaluate_local_admission,
)
from raos.ports.deployment_identity import (
    DeploymentIdentityActivationCommand,
    DeploymentIdentityActivationReceipt,
)
from raos.ports.staging_admission import (
    AdmissionPersistCommand,
    AdmissionPersistReceipt,
    StagingAdmissionJournalError,
    StagingAdmissionJournalFailureCode,
)
from raos.staging_admission_runner import (
    _CONTRACT_RELATIVE_PATH,
    _read_closed_yaml,
    _repository_path,
    load_local_staging_admission_spec,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


Mutation = Callable[[dict[str, Any]], None]


def _set_artifact_digest(document: dict[str, Any]) -> None:
    document["artifact"]["payload_sha256"] = "f" * 64


def _set_sbom_digest(document: dict[str, Any]) -> None:
    document["artifact"]["sbom"]["packages"][0]["artifact_sha256"] = "f" * 64


def _add_high_finding(document: dict[str, Any]) -> None:
    document["artifact"]["vulnerability_report"]["high_count"] = 1


def _set_external_builder(document: dict[str, Any]) -> None:
    document["artifact"]["provenance"]["builder_id"] = "https://example.com/build"


def _reorder_migration(document: dict[str, Any]) -> None:
    document["migration"]["steps"][0]["phase"] = "MIGRATE"


def _make_migration_destructive(document: dict[str, Any]) -> None:
    document["migration"]["steps"][0]["destructive"] = True


def _exceed_lock_budget(document: dict[str, Any]) -> None:
    document["migration"]["dry_run"]["observed_lock_milliseconds"] = 51


def _set_non_loopback_health(document: dict[str, Any]) -> None:
    document["health"]["surfaces"][0]["url"] = "http://192.0.2.1:38101/health/readiness"


def _set_generic_health_body(document: dict[str, Any]) -> None:
    document["health"]["surfaces"][0]["body"]["readiness"] = "PASS"


def _set_restore_digest(document: dict[str, Any]) -> None:
    document["rollback_restore"]["restored_integrity_sha256"] = "f" * 64


def _select_target(document: dict[str, Any]) -> None:
    document["execution_boundary"]["selected_target"] = "invented-staging"


def _add_external_action(document: dict[str, Any]) -> None:
    document["execution_boundary"]["action_counts"]["deploy"] = 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        (_set_artifact_digest, "ARTIFACT_DIGEST_MISMATCH"),
        (_set_sbom_digest, "SBOM_SUBJECT_DIGEST_MISMATCH"),
        (_add_high_finding, "NONZERO_EXTERNAL_ACTION"),
        (_set_external_builder, "RECORDED_BUILDER_ID_INVALID"),
        (_reorder_migration, "FIXED_VALUE_VIOLATION"),
        (_make_migration_destructive, "SAFE_BOUNDARY_VIOLATION"),
        (_exceed_lock_budget, "MIGRATION_LOCK_BUDGET_EXCEEDED"),
        (_set_non_loopback_health, "LOOPBACK_URL_REQUIRED"),
        (_set_generic_health_body, "FIXED_VALUE_VIOLATION"),
        (_set_restore_digest, "RESTORED_INTEGRITY_MISMATCH"),
        (_select_target, "SELECTION_MUST_REMAIN_UNSET"),
        (_add_external_action, "NONZERO_EXTERNAL_ACTION"),
    ],
)
def test_runtime_tamper_fails_closed(
    runtime_document: dict[str, Any], mutation: Mutation, expected_code: str
) -> None:
    document = copy.deepcopy(runtime_document)
    mutation(document)
    with pytest.raises(StagingAdmissionError) as captured:
        LocalStagingAdmissionSpec.from_document(document)
    assert captured.value.code == expected_code
    assert "invented-staging" not in str(captured.value)


@pytest.mark.parametrize(
    ("overrides", "expected_code"),
    [
        ({"identity_activation_status": "ENABLED"}, "IDENTITY_ACTIVATION_NOT_DISABLED"),
        (
            {"identity_activation_allowed": True},
            "IDENTITY_ACTIVATION_AUTHORITY_FORBIDDEN",
        ),
        (
            {"identity_credentials_issued": True},
            "IDENTITY_CREDENTIAL_ISSUANCE_FORBIDDEN",
        ),
        ({"identity_actions_executed": 1}, "IDENTITY_ACTION_FORBIDDEN"),
    ],
)
def test_identity_receipt_boundary_refuses_any_authority(
    runtime_spec: LocalStagingAdmissionSpec,
    overrides: dict[str, object],
    expected_code: str,
) -> None:
    arguments: dict[str, object] = {
        "identity_activation_status": "DISABLED",
        "identity_activation_allowed": False,
        "identity_credentials_issued": False,
        "identity_actions_executed": 0,
    }
    arguments.update(overrides)
    with pytest.raises(StagingAdmissionError) as captured:
        evaluate_local_admission(runtime_spec, **arguments)  # type: ignore[arg-type]
    assert captured.value.code == expected_code


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "ENABLED"},
        {"activation_allowed": True},
        {"credentials_issued": True},
        {"actions_executed": 1},
        {"reason_code": "ACTIVATED"},
    ],
)
def test_st1504_hardened_receipt_cannot_be_forged(overrides: dict[str, object]) -> None:
    arguments: dict[str, object] = {
        "policy_id": "st1504-policy-local-test",
        "fixture_id": "st1504-fixture-local-test",
        "status": "DISABLED",
        "activation_allowed": False,
        "credentials_issued": False,
        "actions_executed": 0,
        "reason_code": "LOCAL_ACTIVATION_DISABLED",
    }
    arguments.update(overrides)
    with pytest.raises(DeploymentIdentityPolicyError):
        DeploymentIdentityActivationReceipt(**arguments)  # type: ignore[arg-type]


class _MismatchedDisabledActivation:
    def activate(
        self, command: DeploymentIdentityActivationCommand
    ) -> DeploymentIdentityActivationReceipt:
        return DeploymentIdentityActivationReceipt(
            policy_id="st1504-policy-different-fixture",
            fixture_id=command.fixture_id,
            status="DISABLED",
            activation_allowed=False,
            credentials_issued=False,
            actions_executed=0,
            reason_code="LOCAL_ACTIVATION_DISABLED",
        )


class _UnusedJournal:
    def commit(self, _command: object) -> object:
        raise AssertionError("persistence must not be reached")

    def recover_exact(self, _command: object) -> object:
        raise AssertionError("recovery must not be reached")

    def verify_integrity(self) -> int:
        raise AssertionError("verification must not be reached")


def test_service_rejects_valid_but_mismatched_disabled_receipt(
    runtime_spec: LocalStagingAdmissionSpec,
) -> None:
    service = LocalStagingAdmissionService(
        spec=runtime_spec,
        activation=_MismatchedDisabledActivation(),
        journal=_UnusedJournal(),  # type: ignore[arg-type]
    )
    with pytest.raises(StagingAdmissionError) as captured:
        service.execute(
            LocalStagingAdmissionRun(
                run_id="st1505-run-mismatch-001",
                idempotency_key="st1505-key-mismatch-001",
            )
        )
    assert captured.value.code == "IDENTITY_RECEIPT_MISMATCH"


_CANARY = "HOSTILE_COLLABORATOR_CANARY_ST1505"


class _RaisingActivation:
    def activate(self, _command: DeploymentIdentityActivationCommand) -> object:
        raise RuntimeError(_CANARY)


class _ExplosiveReceipt:
    @property
    def policy_id(self) -> object:
        raise RuntimeError(_CANARY)


class _WrongReceiptActivation:
    def activate(self, _command: DeploymentIdentityActivationCommand) -> object:
        return _ExplosiveReceipt()


class _ForgedReceiptActivation:
    def activate(
        self, _command: DeploymentIdentityActivationCommand
    ) -> DeploymentIdentityActivationReceipt:
        forged = object.__new__(DeploymentIdentityActivationReceipt)
        object.__setattr__(forged, "policy_id", _CANARY)
        return forged


class _HostileJournal:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.observed_action_counts: list[int] = []
        self.commit_calls = 0
        self.recover_calls = 0

    def commit(self, command: AdmissionPersistCommand) -> object:
        self.commit_calls += 1
        document = json.loads(command.result_json)
        self.observed_action_counts.append(sum(document["action_counts"].values()))
        if self.mode == "raise_commit":
            raise RuntimeError(_CANARY)
        if self.mode == "wrong_commit":
            return _ExplosiveReceipt()
        if self.mode == "forged_commit":
            forged = object.__new__(AdmissionPersistReceipt)
            object.__setattr__(forged, "run_id", _CANARY)
            return forged
        if self.mode == "poisoned_closed_error":
            error = StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.STORAGE_FAILURE
            )
            error.args = (_CANARY,)
            raise error
        if self.mode == "forged_closed_error":
            error = object.__new__(StagingAdmissionJournalError)
            RuntimeError.__init__(error, _CANARY)
            raise error
        if self.mode == "raise_recover":
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS
            )
        raise AssertionError(command.run_id)

    def recover_exact(self, _command: AdmissionPersistCommand) -> object:
        self.recover_calls += 1
        if self.mode == "raise_recover":
            raise RuntimeError(_CANARY)
        raise AssertionError(_CANARY)

    def verify_integrity(self) -> int:
        raise AssertionError(_CANARY)


@pytest.mark.parametrize(
    ("activation", "expected_code"),
    [
        (_RaisingActivation(), "IDENTITY_ACTIVATION_FAILED"),
        (_WrongReceiptActivation(), "IDENTITY_RECEIPT_INVALID"),
        (_ForgedReceiptActivation(), "IDENTITY_RECEIPT_INVALID"),
    ],
)
def test_hostile_activation_is_sanitized_before_persistence(
    runtime_spec: LocalStagingAdmissionSpec,
    activation: object,
    expected_code: str,
) -> None:
    service = LocalStagingAdmissionService(
        spec=runtime_spec,
        activation=activation,  # type: ignore[arg-type]
        journal=_UnusedJournal(),  # type: ignore[arg-type]
    )
    with pytest.raises(StagingAdmissionError) as captured:
        service.execute(
            LocalStagingAdmissionRun(
                run_id="st1505-run-hostile-activation",
                idempotency_key="st1505-key-hostile-activation",
            )
        )
    assert captured.value.code == expected_code
    assert _CANARY not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    "mode",
    [
        "raise_commit",
        "wrong_commit",
        "forged_commit",
        "poisoned_closed_error",
        "forged_closed_error",
        "raise_recover",
    ],
)
def test_hostile_journal_is_sanitized_and_never_retries_commit(
    runtime_spec: LocalStagingAdmissionSpec,
    mode: str,
) -> None:
    journal = _HostileJournal(mode)
    identifier = mode.replace("_", "-")
    service = LocalStagingAdmissionService(
        spec=runtime_spec,
        activation=DisabledDeploymentIdentityActivation(),
        journal=journal,  # type: ignore[arg-type]
    )
    with pytest.raises(StagingAdmissionJournalError) as captured:
        service.execute(
            LocalStagingAdmissionRun(
                run_id=f"st1505-run-hostile-{identifier}",
                idempotency_key=f"st1505-key-hostile-{identifier}",
            )
        )
    expected = (
        StagingAdmissionJournalFailureCode.TAMPER_DETECTED
        if mode in {"wrong_commit", "forged_commit"}
        else StagingAdmissionJournalFailureCode.STORAGE_FAILURE
    )
    assert captured.value.code is expected
    assert _CANARY not in str(captured.value)
    assert captured.value.__cause__ is None
    assert journal.observed_action_counts == [0]
    assert journal.commit_calls == 1
    assert journal.recover_calls == (1 if mode == "raise_recover" else 0)


@pytest.mark.parametrize(
    "yaml_text",
    [
        "document:\n  id: first\n  id: second\n",
        "value: &shared unsafe\ncopy: *shared\n",
        "value: !!python/object:builtins.str {}\n",
    ],
)
def test_closed_yaml_rejects_duplicate_alias_anchor_and_explicit_tag(
    tmp_path: Path, yaml_text: str
) -> None:
    path = tmp_path / "hostile.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    with pytest.raises(StagingAdmissionError):
        _read_closed_yaml(path)


def test_repository_binding_rejects_escape_and_symlink(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_text("marker", encoding="utf-8")
    (root / "linked").symlink_to(outside)
    for uri in ("repo://../outside", "repo://linked"):
        with pytest.raises(StagingAdmissionError):
            _repository_path(root, uri)


def test_runner_rejects_symlinked_repository_ancestor(tmp_path: Path) -> None:
    physical_parent = tmp_path / "physical-parent"
    physical_parent.mkdir()
    repository = physical_parent / "repository"
    repository.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(physical_parent, target_is_directory=True)
    with pytest.raises(StagingAdmissionError) as captured:
        load_local_staging_admission_spec(linked_parent / "repository")
    assert captured.value.code == "REPOSITORY_ROOT_INVALID"


def test_runner_rejects_symlinked_fixed_contract(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    contract = root / _CONTRACT_RELATIVE_PATH
    contract.parent.mkdir(parents=True)
    outside = tmp_path / "outside-contract.yaml"
    outside.write_bytes((REPOSITORY_ROOT / _CONTRACT_RELATIVE_PATH).read_bytes())
    contract.symlink_to(outside)
    with pytest.raises(StagingAdmissionError) as captured:
        load_local_staging_admission_spec(root)
    assert captured.value.code == "REPOSITORY_PATH_INVALID"


def test_runner_rejects_tampered_frozen_st1504_manifest(
    tmp_path: Path, runtime_document: dict[str, Any]
) -> None:
    root = tmp_path / "repository"
    contract_target = root / (
        "changes/st-1505/contracts/local-staging-admission-runtime.v2.yaml"
    )
    contract_target.parent.mkdir(parents=True)
    shutil.copy2(
        REPOSITORY_ROOT
        / "changes/st-1505/contracts/local-staging-admission-runtime.v2.yaml",
        contract_target,
    )
    bindings = list(runtime_document["predecessor_bindings"].values())
    identity = runtime_document["identity_boundary"]
    uris = [
        *(
            row[field]
            for row in bindings
            for field in ("contract_uri", "reference_plan_uri")
        ),
        identity["source_manifest_uri"],
        identity["source_activation_port_uri"],
        identity["evaluation_fixture_uri"],
    ]
    for uri in uris:
        relative = PurePosixPath(uri.removeprefix("repo://"))
        target = root.joinpath(*relative.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPOSITORY_ROOT.joinpath(*relative.parts), target)
    manifest = root / "changes/st-1504/manifest.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    assert load_local_staging_admission_spec(root).fixture_id == (
        "st1505-fixture-local-admission-v2"
    )
