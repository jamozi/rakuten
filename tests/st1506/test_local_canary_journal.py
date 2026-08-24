"""Durability, recovery, concurrency, and tamper tests for ST-1506 V2."""

from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from raos.adapters.disabled_production_activation import DisabledProductionActivation
from raos.adapters.recorded_production_canary import (
    CommitFault,
    RecordedProductionCanaryJournal,
)
from raos.application.ops.production_canary import (
    LocalProductionCanaryRun,
    LocalProductionCanaryRunReceipt,
    LocalProductionCanaryService,
)
from raos.domain.ops.production_canary import (
    CanaryCommandKind,
    CanarySession,
    CanaryState,
    ProductionCanarySpec,
    advance_once,
    canonical_bytes,
    canonical_sha256,
)
from raos.ports.production_canary import (
    CanaryStepPersistCommand,
    ProductionCanaryJournalError,
    ProductionCanaryJournalFailureCode,
)
from raos.production_canary_runner import load_local_production_canary_spec


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_DATABASE_NAME = "st1506-local-production-canary.sqlite3"


@pytest.fixture
def spec() -> ProductionCanarySpec:
    return load_local_production_canary_spec(REPOSITORY_ROOT)


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "owner-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    return root


def _service(
    spec: ProductionCanarySpec,
    journal: RecordedProductionCanaryJournal,
) -> LocalProductionCanaryService:
    return LocalProductionCanaryService(
        spec=spec,
        activation=DisabledProductionActivation(),
        journal=journal,
    )


def _start(
    service: LocalProductionCanaryService,
    *,
    run: str,
    key: str,
) -> LocalProductionCanaryRunReceipt:
    return service.execute(
        LocalProductionCanaryRun(
            run_id=f"st1506-run-{run}",
            idempotency_key=f"st1506-key-{key}",
            command=CanaryCommandKind.START_CANARY_SIMULATION,
            observation=None,
        )
    )


def _command_from_latest(
    journal: RecordedProductionCanaryJournal, run_id: str
) -> CanaryStepPersistCommand:
    persisted = journal.load_latest(run_id)
    assert persisted is not None
    return CanaryStepPersistCommand(
        run_id=persisted.run_id,
        idempotency_key_sha256=persisted.idempotency_key_sha256,
        request_sha256=persisted.request_sha256,
        contract_sha256=persisted.contract_sha256,
        expected_version=persisted.expected_version,
        current_version=persisted.current_version,
        state=persisted.state,
        outcome=persisted.outcome,
        result_sha256=persisted.result_sha256,
        result_json=persisted.result_json,
    )


def test_exact_replay_is_idempotent_at_journal_boundary(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    first = _start(_service(spec, journal), run="idempotent", key="idempotent")
    command = _command_from_latest(journal, "st1506-run-idempotent")
    replay = journal.commit(command)
    assert replay.replayed is True
    assert replay.sequence == first.persistence.sequence == 1
    assert replay.entry_sha256 == first.persistence.entry_sha256
    assert journal.verify_integrity() == 1


def test_restart_loads_exact_content_addressed_state(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    first_journal = RecordedProductionCanaryJournal(private_root=private_root)
    first = _start(_service(spec, first_journal), run="restart", key="restart")
    restarted = RecordedProductionCanaryJournal(private_root=private_root)
    persisted = restarted.load_latest("st1506-run-restart")
    assert persisted is not None
    assert persisted.result_sha256 == first.persistence.result_sha256
    assert persisted.entry_sha256 == first.persistence.entry_sha256
    assert restarted.verify_integrity() == 1


def test_after_commit_ambiguity_recovers_exactly_once(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(
        private_root=private_root,
        commit_fault_once=CommitFault.AFTER_COMMIT,
    )
    receipt = _start(_service(spec, journal), run="after-commit", key="after-commit")
    assert receipt.recovered_after_commit_ambiguity is True
    assert receipt.persistence.replayed is True
    assert journal.verify_integrity() == 1


def test_before_commit_ambiguity_remains_unknown_and_does_not_retry(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(
        private_root=private_root,
        commit_fault_once=CommitFault.BEFORE_COMMIT,
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        _start(_service(spec, journal), run="before-commit", key="before-commit")
    assert captured.value.code is ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS
    assert journal.verify_integrity() == 0


def test_direct_first_write_cannot_skip_the_canary_ready_state(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    decision = advance_once(
        spec,
        CanarySession(
            run_id="st1506-run-invalid-first-state",
            version=0,
            state=CanaryState.OBSERVE,
        ),
        command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
        observation=None,
    )
    document = decision.to_document(spec)
    result_sha256 = document["result_sha256"]
    assert type(result_sha256) is str
    command = CanaryStepPersistCommand(
        run_id=decision.session.run_id,
        idempotency_key_sha256="1" * 64,
        request_sha256="2" * 64,
        contract_sha256=spec.semantic_sha256,
        expected_version=0,
        current_version=1,
        state=decision.session.state,
        outcome=decision.outcome,
        result_sha256=result_sha256,
        result_json=canonical_bytes(document),
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        journal.commit(command)
    assert captured.value.code is ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE
    assert journal.verify_integrity() == 0


def test_direct_write_cannot_change_contract_mid_run(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    _start(_service(spec, journal), run="contract-drift", key="contract-drift-start")
    decision = advance_once(
        spec,
        CanarySession(
            run_id="st1506-run-contract-drift",
            version=1,
            state=CanaryState.OBSERVE,
        ),
        command=CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION,
        observation=None,
    )
    document = decision.to_document(spec)
    document["contract_sha256"] = "f" * 64
    without_digest = dict(document)
    without_digest.pop("result_sha256")
    result_sha256 = canonical_sha256(without_digest)
    document["result_sha256"] = result_sha256
    command = CanaryStepPersistCommand(
        run_id=decision.session.run_id,
        idempotency_key_sha256="3" * 64,
        request_sha256="4" * 64,
        contract_sha256="f" * 64,
        expected_version=1,
        current_version=2,
        state=decision.session.state,
        outcome=decision.outcome,
        result_sha256=result_sha256,
        result_json=canonical_bytes(document),
    )
    with pytest.raises(ProductionCanaryJournalError) as captured:
        journal.commit(command)
    assert captured.value.code is ProductionCanaryJournalFailureCode.CONCURRENCY_FAILURE
    assert journal.verify_integrity() == 1


@pytest.mark.parametrize(
    "tamper_sql",
    [
        "UPDATE canary_metadata SET tail_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        "UPDATE canary_run SET result_json = x'7b7d'",
        "UPDATE canary_journal SET request_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        "UPDATE canary_journal SET previous_entry_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
    ],
)
def test_hash_chain_and_cas_tamper_are_detected(
    spec: ProductionCanarySpec, private_root: Path, tamper_sql: str
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    _start(_service(spec, journal), run="tamper", key="tamper")
    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        connection.execute(tamper_sql)
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ProductionCanaryJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is ProductionCanaryJournalFailureCode.TAMPER_DETECTED


def test_same_column_weakened_schema_is_rejected(
    private_root: Path,
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    database = journal.database_path
    connection = sqlite3.connect(database)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.executescript(
            """
            DROP TABLE canary_journal;
            DROP TABLE canary_run;
            CREATE TABLE canary_run (
              run_id TEXT PRIMARY KEY NOT NULL,
              contract_sha256 TEXT NOT NULL,
              current_version INTEGER NOT NULL,
              state TEXT NOT NULL,
              outcome TEXT NOT NULL,
              result_sha256 TEXT NOT NULL,
              result_json BLOB NOT NULL,
              latest_sequence INTEGER NOT NULL UNIQUE,
              latest_entry_sha256 TEXT NOT NULL UNIQUE
            ) STRICT;
            CREATE TABLE canary_journal (
              sequence INTEGER PRIMARY KEY,
              previous_entry_sha256 TEXT NOT NULL,
              entry_sha256 TEXT NOT NULL UNIQUE,
              run_id TEXT NOT NULL,
              idempotency_key_sha256 TEXT NOT NULL UNIQUE,
              request_sha256 TEXT NOT NULL,
              contract_sha256 TEXT NOT NULL,
              expected_version INTEGER NOT NULL,
              current_version INTEGER NOT NULL,
              state TEXT NOT NULL,
              outcome TEXT NOT NULL,
              result_sha256 TEXT NOT NULL,
              result_json BLOB NOT NULL,
              UNIQUE (run_id, current_version),
              FOREIGN KEY (run_id) REFERENCES canary_run(run_id)
            ) STRICT;
            """
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ProductionCanaryJournalError) as captured:
        RecordedProductionCanaryJournal(private_root=private_root)
    assert captured.value.code is ProductionCanaryJournalFailureCode.TAMPER_DETECTED


@pytest.mark.parametrize("unsafe_kind", ["mode", "symlink", "hardlink"])
def test_owner_private_file_safety_is_enforced(
    tmp_path: Path, unsafe_kind: str
) -> None:
    root = tmp_path / "owner-private"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    if unsafe_kind == "mode":
        root.chmod(0o755)
    elif unsafe_kind == "symlink":
        target = tmp_path / "real-private"
        target.mkdir(mode=0o700)
        target.chmod(0o700)
        root.rmdir()
        root.symlink_to(target, target_is_directory=True)
    else:
        journal = RecordedProductionCanaryJournal(private_root=root)
        os.link(journal.database_path, tmp_path / "journal-hardlink")
    with pytest.raises(ProductionCanaryJournalError) as captured:
        RecordedProductionCanaryJournal(private_root=root)
    assert (
        captured.value.code is ProductionCanaryJournalFailureCode.STORAGE_PATH_INVALID
    )


def test_concurrent_first_writers_do_not_both_commit(
    spec: ProductionCanarySpec, private_root: Path
) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)

    def invoke(index: int) -> str:
        try:
            _start(
                _service(spec, journal),
                run="concurrent",
                key=f"concurrent-{index}",
            )
            return "PASS"
        except ProductionCanaryJournalError as error:
            return error.code.value

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(invoke, (1, 2)))
    assert outcomes.count("PASS") == 1
    assert set(outcomes) <= {
        "PASS",
        "CONCURRENCY_FAILURE",
    }
    assert journal.verify_integrity() == 1


def test_extra_trigger_or_index_is_rejected(private_root: Path) -> None:
    journal = RecordedProductionCanaryJournal(private_root=private_root)
    connection = sqlite3.connect(journal.database_path)
    try:
        connection.execute(
            "CREATE TRIGGER hostile_trigger AFTER INSERT ON canary_run BEGIN SELECT 1; END"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(ProductionCanaryJournalError) as captured:
        journal.verify_integrity()
    assert captured.value.code is ProductionCanaryJournalFailureCode.TAMPER_DETECTED
