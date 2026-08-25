"""Hostile collaborator and trust-boundary tests for ST-1506 V2."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
import yaml

from raos.adapters.disabled_production_activation import DisabledProductionActivation
from raos.adapters.recorded_production_canary import RecordedProductionCanaryJournal
from raos.application.ops.production_canary import (
    LocalProductionCanaryRun,
    LocalProductionCanaryService,
)
from raos.domain.ops.production_canary import (
    CanaryCommandKind,
    EXTERNAL_ACTION_NAMES,
    ProductionCanaryError,
    ProductionCanarySpec,
    canonical_bytes,
    canonical_sha256,
)
from raos.ports.production_canary import (
    CanaryStepPersistCommand,
    CanaryStepPersistReceipt,
    PersistedCanaryStep,
    ProductionActivationCommand,
    ProductionActivationReceipt,
    ProductionCanaryJournalError,
    ProductionCanaryJournalFailureCode,
    canary_entry_sha256,
)
from raos.production_canary_runner import (
    _read_closed_yaml,
    load_local_production_canary_spec,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = (
    REPOSITORY_ROOT
    / "changes/st-1506/contracts/local-production-canary-runtime.v2.yaml"
)
SECRET_CANARY = "HOSTILE_SECRET_CANARY_DO_NOT_DISCLOSE"


@pytest.fixture
def spec() -> ProductionCanarySpec:
    return load_local_production_canary_spec(REPOSITORY_ROOT)


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "owner-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def _request() -> LocalProductionCanaryRun:
    return LocalProductionCanaryRun(
        run_id="st1506-run-hostile-boundary",
        idempotency_key="st1506-key-hostile-boundary",
        command=CanaryCommandKind.START_CANARY_SIMULATION,
        observation=None,
    )


def _assert_sanitized(error: BaseException) -> None:
    assert SECRET_CANARY not in str(error)
    assert SECRET_CANARY not in repr(error)


class _HostileActivation:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.request_calls = 0

    @property
    def mode(self) -> str:
        if self.failure == "mode":
            raise RuntimeError(SECRET_CANARY)
        if self.failure == "mode-object":
            return cast(str, _ExplosiveValue())
        return "DISABLED_RECORDED_LOCAL_ONLY"

    @property
    def external_action_counts(self) -> tuple[tuple[str, int], ...]:
        if self.failure == "counts":
            raise RuntimeError(SECRET_CANARY)
        if self.failure == "nonzero":
            return tuple(
                (name, 1 if name == "deploy" else 0) for name in EXTERNAL_ACTION_NAMES
            )
        if self.failure == "count-object":
            return ((cast(str, _ExplosiveValue()), 0),)
        return tuple((name, 0) for name in EXTERNAL_ACTION_NAMES)

    def request(
        self, command: ProductionActivationCommand
    ) -> ProductionActivationReceipt:
        del command
        self.request_calls += 1
        if self.failure == "request":
            raise RuntimeError(SECRET_CANARY)
        if self.failure == "forged":
            receipt = object.__new__(ProductionActivationReceipt)
            object.__setattr__(receipt, "contract_sha256", "f" * 64)
            object.__setattr__(receipt, "status", "ENABLED")
            object.__setattr__(receipt, "activation_allowed", True)
            object.__setattr__(receipt, "public_write_allowed", True)
            object.__setattr__(receipt, "actions_executed", 1)
            object.__setattr__(receipt, "reason_code", SECRET_CANARY)
            return receipt
        return ProductionActivationReceipt(
            contract_sha256="f" * 64,
            status="DISABLED",
            activation_allowed=False,
            public_write_allowed=False,
            actions_executed=0,
            reason_code="LOCAL_PRODUCTION_ACTIVATION_DISABLED",
        )


class _ExplosiveValue:
    def __eq__(self, other: object) -> bool:
        del other
        raise RuntimeError(SECRET_CANARY)


def _forge_release_approval(document: dict[str, object]) -> None:
    approvals = cast(dict[str, object], document["human_approvals"])
    release = cast(dict[str, object], approvals["release_decision"])
    release["status"] = "APPROVED"


@pytest.mark.parametrize(
    ("failure", "expected_calls", "expected_code"),
    [
        ("mode", 0, "ACTIVATION_BOUNDARY_UNAVAILABLE"),
        ("mode-object", 0, "ACTIVATION_BOUNDARY_INVALID"),
        ("counts", 0, "ACTIVATION_BOUNDARY_UNAVAILABLE"),
        ("count-object", 0, "ACTIVATION_BOUNDARY_INVALID"),
        ("nonzero", 0, "ACTIVATION_BOUNDARY_INVALID"),
        ("request", 1, "ACTIVATION_BOUNDARY_UNAVAILABLE"),
        ("forged", 1, "ACTIVATION_RECEIPT_INVALID"),
        ("wrong-contract", 1, "ACTIVATION_RECEIPT_INVALID"),
    ],
)
def test_hostile_activation_is_sanitized_before_any_external_action(
    spec: ProductionCanarySpec,
    private_root: Path,
    failure: str,
    expected_calls: int,
    expected_code: str,
) -> None:
    activation = _HostileActivation(failure)
    service = LocalProductionCanaryService(
        spec=spec,
        activation=activation,
        journal=RecordedProductionCanaryJournal(private_root=private_root),
    )
    with pytest.raises(ProductionCanaryError) as captured:
        service.execute(_request())
    assert captured.value.code == expected_code
    assert activation.request_calls == expected_calls
    _assert_sanitized(captured.value)


class _HostileJournal:
    def __init__(
        self,
        delegate: RecordedProductionCanaryJournal,
        failure: str,
    ) -> None:
        self.delegate = delegate
        self.failure = failure

    def load_latest(self, run_id: str) -> PersistedCanaryStep | None:
        if self.failure == "load-exception":
            raise RuntimeError(SECRET_CANARY)
        observed = self.delegate.load_latest(run_id)
        if observed is not None and self.failure == "forged-load":
            forged = object.__new__(PersistedCanaryStep)
            for name in PersistedCanaryStep.__dataclass_fields__:
                object.__setattr__(forged, name, getattr(observed, name))
            object.__setattr__(
                forged, "result_json", b'{"tainted":"' + SECRET_CANARY.encode() + b'"}'
            )
            return forged
        if observed is not None and self.failure == "forged-valid-load":
            document = cast(dict[str, object], json.loads(observed.result_json))
            staging = cast(dict[str, object], document["staging_admission"])
            staging["artifact_sha256"] = "f" * 64
            without_digest = dict(document)
            without_digest.pop("result_sha256")
            result_sha256 = canonical_sha256(without_digest)
            document["result_sha256"] = result_sha256
            return PersistedCanaryStep(
                run_id=observed.run_id,
                idempotency_key_sha256=observed.idempotency_key_sha256,
                request_sha256=observed.request_sha256,
                contract_sha256=observed.contract_sha256,
                expected_version=observed.expected_version,
                current_version=observed.current_version,
                state=observed.state,
                outcome=observed.outcome,
                result_sha256=result_sha256,
                result_json=canonical_bytes(document),
                sequence=observed.sequence,
                previous_entry_sha256=observed.previous_entry_sha256,
                entry_sha256=canary_entry_sha256(
                    run_id=observed.run_id,
                    idempotency_key_sha256=observed.idempotency_key_sha256,
                    request_sha256=observed.request_sha256,
                    contract_sha256=observed.contract_sha256,
                    expected_version=observed.expected_version,
                    current_version=observed.current_version,
                    state=observed.state,
                    outcome=observed.outcome,
                    result_sha256=result_sha256,
                    sequence=observed.sequence,
                    previous_entry_sha256=observed.previous_entry_sha256,
                ),
            )
        return observed

    def commit(self, command: CanaryStepPersistCommand) -> CanaryStepPersistReceipt:
        if self.failure == "commit-exception":
            raise RuntimeError(SECRET_CANARY)
        if self.failure == "recover-exception":
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS
            )
        receipt = self.delegate.commit(command)
        if self.failure == "forged-receipt":
            forged = object.__new__(CanaryStepPersistReceipt)
            for name in CanaryStepPersistReceipt.__dataclass_fields__:
                object.__setattr__(forged, name, getattr(receipt, name))
            object.__setattr__(forged, "entry_sha256", "f" * 64)
            return forged
        return receipt

    def recover_exact(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt:
        if self.failure == "recover-exception":
            raise RuntimeError(SECRET_CANARY)
        return self.delegate.recover_exact(command)

    def verify_integrity(self) -> int:
        return self.delegate.verify_integrity()


@pytest.mark.parametrize(
    ("failure", "expected_code"),
    [
        ("load-exception", ProductionCanaryJournalFailureCode.STORAGE_FAILURE),
        ("commit-exception", ProductionCanaryJournalFailureCode.STORAGE_FAILURE),
        ("recover-exception", ProductionCanaryJournalFailureCode.STORAGE_FAILURE),
        ("forged-receipt", ProductionCanaryJournalFailureCode.TAMPER_DETECTED),
    ],
)
def test_hostile_journal_calls_and_receipts_are_sanitized(
    spec: ProductionCanarySpec,
    private_root: Path,
    failure: str,
    expected_code: ProductionCanaryJournalFailureCode,
) -> None:
    service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=_HostileJournal(
            RecordedProductionCanaryJournal(private_root=private_root), failure
        ),
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        service.execute(_request())
    assert captured.value.code is expected_code
    _assert_sanitized(captured.value)


def test_forged_exact_class_latest_result_is_rejected(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    delegate = RecordedProductionCanaryJournal(private_root=private_root)
    good_service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=delegate,
    )
    good_service.execute(_request())
    hostile_service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=_HostileJournal(delegate, "forged-load"),
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        hostile_service.execute(
            LocalProductionCanaryRun(
                run_id="st1506-run-hostile-boundary",
                idempotency_key="st1506-key-hostile-followup",
                command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
                observation=None,
            )
        )
    assert captured.value.code is ProductionCanaryJournalFailureCode.TAMPER_DETECTED
    _assert_sanitized(captured.value)


def test_forged_exact_class_with_valid_self_hash_but_wrong_spec_is_rejected(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    delegate = RecordedProductionCanaryJournal(private_root=private_root)
    good_service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=delegate,
    )
    good_service.execute(_request())
    hostile_service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=_HostileJournal(delegate, "forged-valid-load"),
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        hostile_service.execute(
            LocalProductionCanaryRun(
                run_id="st1506-run-hostile-boundary",
                idempotency_key="st1506-key-hostile-valid-followup",
                command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
                observation=None,
            )
        )
    assert captured.value.code is ProductionCanaryJournalFailureCode.TAMPER_DETECTED
    _assert_sanitized(captured.value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document.update({"unknown": SECRET_CANARY}),
        _forge_release_approval,
        lambda document: cast(dict[str, object], document["activation"]).update(
            {"enabled": 0}
        ),
        lambda document: cast(dict[str, object], document["external_evidence"]).update(
            {"production": "EXECUTED"}
        ),
        lambda document: document.update({"observation_sha256": "f" * 64}),
    ],
)
def test_persist_command_rejects_rehashed_result_boundary_forgery(
    spec: ProductionCanarySpec,
    private_root: Path,
    mutation: Callable[[dict[str, object]], None],
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    service = LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=journal,
    )
    service.execute(_request())
    persisted = journal.load_latest("st1506-run-hostile-boundary")
    assert persisted is not None
    document = cast(dict[str, object], json.loads(persisted.result_json))
    mutation(document)
    without_digest = dict(document)
    without_digest.pop("result_sha256")
    result_sha256 = canonical_sha256(without_digest)
    document["result_sha256"] = result_sha256
    with pytest.raises(ProductionCanaryJournalError) as captured:
        CanaryStepPersistCommand(
            run_id=persisted.run_id,
            idempotency_key_sha256=persisted.idempotency_key_sha256,
            request_sha256=persisted.request_sha256,
            contract_sha256=persisted.contract_sha256,
            expected_version=persisted.expected_version,
            current_version=persisted.current_version,
            state=persisted.state,
            outcome=persisted.outcome,
            result_sha256=result_sha256,
            result_json=canonical_bytes(document),
        )
    assert captured.value.code is ProductionCanaryJournalFailureCode.INVALID_COMMAND
    _assert_sanitized(captured.value)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda document: document["activation_boundary"].update(
            {"activation_enabled": True}
        ),
        lambda document: document["approval_boundary"]["release_decision"].update(
            {"status": "APPROVED"}
        ),
        lambda document: document["kill_switch_boundary"].update(
            {"deactivation_allowed": True}
        ),
        lambda document: document["execution_boundary"]["action_counts"].update(
            {"deploy": 1}
        ),
        lambda document: document["activation_boundary"].update(
            {"selected_region": "invented-region"}
        ),
        lambda document: document.update({"unknown": SECRET_CANARY}),
    ],
)
def test_any_contract_mutation_fails_the_closed_fingerprint(
    mutation: Callable[[dict[str, object]], None],
) -> None:
    source = yaml.safe_load(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert type(source) is dict
    document = copy.deepcopy(cast(dict[str, object], source))
    mutation(document)
    with pytest.raises(ProductionCanaryError) as captured:
        ProductionCanarySpec.from_document(document)
    assert captured.value.code == "CONTRACT_DEFINITION_DRIFT"
    _assert_sanitized(captured.value)


def test_duplicate_yaml_key_is_rejected_without_value_disclosure(
    tmp_path: Path,
) -> None:
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "document:\n  id: safe\n  id: " + SECRET_CANARY + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ProductionCanaryError) as captured:
        _read_closed_yaml(path)
    assert captured.value.code == "CONTRACT_PARSE_FAILED"
    _assert_sanitized(captured.value)


def test_story_sources_exclude_ranking_and_finance_influence() -> None:
    paths = [
        CONTRACT_PATH,
        REPOSITORY_ROOT / "python/raos/domain/ops/production_canary.py",
        REPOSITORY_ROOT / "python/raos/application/ops/production_canary.py",
    ]
    forbidden = ("affiliateRate", "EPC", "RPM", "commission_rate", "profit")
    text = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert all(token not in text for token in forbidden)
