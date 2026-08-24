"""Application and durable-journal tests for ST-1604 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
from typing import Any
from uuid import UUID

import pytest

from raos.adapters.recorded_performance_load import (
    PerformanceLoadCommitFault,
    RecordedPerformanceLoadJournal,
    _CREATE_REPORT_NO_UPDATE,
    _canonical_stored_uuid,
)
from raos.adapters import recorded_performance_load as recorded_adapter
from raos.application.ops.performance_load import PerformanceLoadEvaluationService
from raos.domain.ops.performance_load import (
    LoadEvidenceSource,
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    evaluate_performance_load,
    performance_load_record_sha256,
    performance_load_report_sha256,
)
from raos.ports.performance_load import (
    PerformanceLoadReceipt,
    PerformanceLoadWriteDisposition,
)

from conftest import make_request


_DATABASE_NAME = "st1604-local-performance-load.sqlite3"


def test_service_records_once_and_journal_replay_is_idempotent(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    service = PerformanceLoadEvaluationService(journal=journal)
    report = service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    replay = journal.append(report)
    assert replay.disposition is PerformanceLoadWriteDisposition.REPLAYED
    assert replay.sequence == 1
    assert service.action_count == journal.action_count == 0
    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        assert connection.execute(
            "SELECT count(*) FROM st1604_report_v2"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_same_run_id_with_changed_report_is_conflict(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    first = evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    journal.append(first)
    typed = perf_request  # type: ignore[assignment]
    changed = evaluate_performance_load(
        replace(
            typed,
            source_artifact_sha256="b" * 64,
        )
    )
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(changed)
    assert caught.value.code is PerformanceLoadFailureCode.RUN_ID_CONFLICT


def test_journal_rejects_direct_recorded_capture_report_without_artifact_binding(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    recorded = replace(
        evaluate_performance_load(perf_request),  # type: ignore[arg-type]
        evidence_source=LoadEvidenceSource.RECORDED_CAPTURE,
    )
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(recorded)
    assert caught.value.code is PerformanceLoadFailureCode.RECORDED_CAPTURE_DISABLED


def test_after_commit_ambiguity_recovers_exact_receipt(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(
        private_root=private_root,
        commit_fault_once=PerformanceLoadCommitFault.AFTER_COMMIT,
    )
    receipt = journal.append(
        evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    )
    assert receipt.sequence == 1
    assert receipt.disposition is PerformanceLoadWriteDisposition.APPENDED
    restarted = RecordedPerformanceLoadJournal(private_root=private_root)
    assert restarted.append(
        evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    ).disposition is (PerformanceLoadWriteDisposition.REPLAYED)


def test_before_commit_fault_writes_nothing(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(
        private_root=private_root,
        commit_fault_once=PerformanceLoadCommitFault.BEFORE_COMMIT,
    )
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(
            evaluate_performance_load(perf_request)  # type: ignore[arg-type]
        )
    assert caught.value.code is PerformanceLoadFailureCode.STORAGE_FAILED
    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        assert connection.execute(
            "SELECT count(*) FROM st1604_report_v2"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_concurrent_distinct_reports_form_one_exact_chain(private_root: Path) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    reports = [
        evaluate_performance_load(
            make_request(run_id=UUID(f"16040000-0000-4000-8000-{index:012d}"))
        )
        for index in range(1, 9)
    ]
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = tuple(pool.map(journal.append, reports))
    assert sorted(row.sequence for row in receipts) == list(range(1, 9))
    restarted = RecordedPerformanceLoadJournal(private_root=private_root)
    assert restarted.action_count == 0


def test_trigger_prevents_update_and_tamper_is_detected_after_hostile_rebuild(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    journal.append(
        evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    )
    database = private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE st1604_report_v2 SET observed_at='2026-01-01T00:00:00Z'"
            )
        connection.rollback()
        connection.execute("DROP TRIGGER st1604_report_no_update_v2")
        connection.execute(
            "UPDATE st1604_report_v2 SET observed_at='2026-01-01T00:00:00Z'"
        )
        connection.execute(_CREATE_REPORT_NO_UPDATE)
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PerformanceLoadFailure) as caught:
        RecordedPerformanceLoadJournal(private_root=private_root)
    assert caught.value.code is PerformanceLoadFailureCode.TAMPER_DETECTED


def test_private_root_and_database_require_owner_private_modes(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o755)
    with pytest.raises(PerformanceLoadFailure) as caught:
        RecordedPerformanceLoadJournal(private_root=root)
    assert caught.value.code is PerformanceLoadFailureCode.PRIVATE_PATH_INVALID
    root.chmod(0o700)
    journal = RecordedPerformanceLoadJournal(private_root=root)
    database = root / _DATABASE_NAME
    assert journal.action_count == 0
    assert database.stat().st_mode & 0o777 == 0o600
    os.link(database, tmp_path / "second-link.sqlite3")
    with pytest.raises(PerformanceLoadFailure) as linked:
        RecordedPerformanceLoadJournal(private_root=root)
    assert linked.value.code is PerformanceLoadFailureCode.PRIVATE_PATH_INVALID


def test_symlink_private_root_is_rejected(tmp_path: Path) -> None:
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    with pytest.raises(PerformanceLoadFailure) as caught:
        RecordedPerformanceLoadJournal(private_root=linked)
    assert caught.value.code is PerformanceLoadFailureCode.PRIVATE_PATH_INVALID


def test_database_symlink_and_extra_schema_are_rejected(
    tmp_path: Path, private_root: Path
) -> None:
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"outside")
    database = private_root / _DATABASE_NAME
    database.symlink_to(outside)
    with pytest.raises(PerformanceLoadFailure) as symlinked:
        RecordedPerformanceLoadJournal(private_root=private_root)
    assert symlinked.value.code is PerformanceLoadFailureCode.PRIVATE_PATH_INVALID
    assert outside.read_bytes() == b"outside"
    database.unlink()
    RecordedPerformanceLoadJournal(private_root=private_root)
    connection = sqlite3.connect(database)
    try:
        connection.execute("CREATE TABLE unexpected(value TEXT)")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PerformanceLoadFailure) as drifted:
        RecordedPerformanceLoadJournal(private_root=private_root)
    assert drifted.value.code is PerformanceLoadFailureCode.SCHEMA_DRIFT


@pytest.mark.parametrize("partial", [False, True])
def test_preexisting_empty_or_partial_private_database_is_never_initialized(
    private_root: Path, partial: bool
) -> None:
    database = private_root / _DATABASE_NAME
    if partial:
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE partial(value TEXT)")
            connection.commit()
        finally:
            connection.close()
    else:
        database.write_bytes(b"")
    database.chmod(0o600)
    before = database.read_bytes()
    with pytest.raises(PerformanceLoadFailure) as caught:
        RecordedPerformanceLoadJournal(private_root=private_root)
    assert caught.value.code is PerformanceLoadFailureCode.SCHEMA_DRIFT
    assert database.read_bytes() == before


def test_live_journal_rejects_database_inode_replacement(
    perf_request: object, private_root: Path, tmp_path: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    journal.append(evaluate_performance_load(perf_request))  # type: ignore[arg-type]
    database = private_root / _DATABASE_NAME
    original_identity = (database.stat().st_dev, database.stat().st_ino)
    replacement = tmp_path / "replacement.sqlite3"
    replacement.write_bytes(database.read_bytes())
    replacement.chmod(0o600)
    os.replace(replacement, database)
    assert (database.stat().st_dev, database.stat().st_ino) != original_identity
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(
            evaluate_performance_load(
                make_request(run_id=UUID("16040000-0000-4000-8000-000000000002"))
            )
        )
    assert caught.value.code is PerformanceLoadFailureCode.TAMPER_DETECTED


def test_live_journal_rejects_older_valid_same_inode_snapshot(
    perf_request: object, private_root: Path
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    journal.append(evaluate_performance_load(perf_request))  # type: ignore[arg-type]
    database = private_root / _DATABASE_NAME
    older_valid_snapshot = database.read_bytes()
    identity = (database.stat().st_dev, database.stat().st_ino)
    journal.append(
        evaluate_performance_load(
            make_request(run_id=UUID("16040000-0000-4000-8000-000000000002"))
        )
    )
    database.write_bytes(older_valid_snapshot)
    assert (database.stat().st_dev, database.stat().st_ino) == identity
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(
            evaluate_performance_load(
                make_request(run_id=UUID("16040000-0000-4000-8000-000000000003"))
            )
        )
    assert caught.value.code is PerformanceLoadFailureCode.TAMPER_DETECTED


def test_stored_uuid_parser_requires_exact_canonical_text() -> None:
    canonical = "16040000-0000-4000-8000-000000000001"
    assert str(_canonical_stored_uuid(canonical)) == canonical
    hostile = "NOT-A-SECRET-UUID-VALUE"
    with pytest.raises(PerformanceLoadFailure) as caught:
        _canonical_stored_uuid(hostile)
    assert caught.value.code is PerformanceLoadFailureCode.TAMPER_DETECTED
    assert str(caught.value) == "ST1604_TAMPER_DETECTED"
    assert hostile not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True


class _CommitErrorConnection:
    def __init__(
        self,
        connection: sqlite3.Connection,
        state: dict[str, object],
        *,
        after_commit: bool,
    ) -> None:
        self._connection = connection
        self._state = state
        self._after_commit = after_commit

    @property
    def row_factory(self) -> Any:
        return self._connection.row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        self._connection.row_factory = value

    @property
    def in_transaction(self) -> bool:
        return self._connection.in_transaction

    def execute(self, *args: object, **kwargs: object) -> sqlite3.Cursor:
        return self._connection.execute(*args, **kwargs)  # type: ignore[arg-type]

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()

    def commit(self) -> None:
        if self._state["remaining"] == 1:
            self._state["remaining"] = 0
            if self._after_commit:
                self._connection.commit()
            raise sqlite3.OperationalError("private commit detail")
        self._connection.commit()


def _install_commit_error(
    monkeypatch: pytest.MonkeyPatch, *, after_commit: bool
) -> None:
    real_connect = sqlite3.connect
    state: dict[str, object] = {"remaining": 1}

    def connect(*args: object, **kwargs: object) -> _CommitErrorConnection:
        return _CommitErrorConnection(
            real_connect(*args, **kwargs),  # type: ignore[arg-type]
            state,
            after_commit=after_commit,
        )

    monkeypatch.setattr(recorded_adapter.sqlite3, "connect", connect)


def test_sqlite_commit_exception_recovers_only_exact_committed_report(
    perf_request: object, private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    _install_commit_error(monkeypatch, after_commit=True)
    receipt = journal.append(
        evaluate_performance_load(perf_request)  # type: ignore[arg-type]
    )
    assert receipt.disposition is PerformanceLoadWriteDisposition.APPENDED
    assert receipt.sequence == 1


def test_sqlite_commit_exception_without_exact_report_is_commit_unknown(
    perf_request: object, private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = RecordedPerformanceLoadJournal(private_root=private_root)
    _install_commit_error(monkeypatch, after_commit=False)
    with pytest.raises(PerformanceLoadFailure) as caught:
        journal.append(
            evaluate_performance_load(perf_request)  # type: ignore[arg-type]
        )
    assert caught.value.code is PerformanceLoadFailureCode.COMMIT_UNKNOWN
    assert "private commit detail" not in str(caught.value)


class _HostileJournal:
    @property
    def action_count(self) -> int:
        return 0

    def append(self, report: object) -> PerformanceLoadReceipt:
        typed = report  # type: ignore[assignment]
        return PerformanceLoadReceipt(
            run_id=typed.run_id,
            report_sha256="0" * 64,
            sequence=1,
            previous_record_sha256="0" * 64,
            record_sha256="0" * 64,
            disposition=PerformanceLoadWriteDisposition.APPENDED,
        )


def test_service_rejects_hostile_receipt(perf_request: object) -> None:
    service = PerformanceLoadEvaluationService(journal=_HostileJournal())
    with pytest.raises(PerformanceLoadFailure) as caught:
        service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.JOURNAL_MISMATCH


class _SpoofedRecordDigestJournal:
    @property
    def action_count(self) -> int:
        return 0

    def append(self, report: object) -> PerformanceLoadReceipt:
        typed = report  # type: ignore[assignment]
        return PerformanceLoadReceipt(
            run_id=typed.run_id,
            report_sha256=performance_load_report_sha256(typed),
            sequence=1,
            previous_record_sha256="0" * 64,
            record_sha256="f" * 64,
            disposition=PerformanceLoadWriteDisposition.APPENDED,
        )


def test_service_recomputes_record_digest_instead_of_trusting_receipt(
    perf_request: object,
) -> None:
    service = PerformanceLoadEvaluationService(journal=_SpoofedRecordDigestJournal())
    with pytest.raises(PerformanceLoadFailure) as caught:
        service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.JOURNAL_MISMATCH


class _MutatingReportJournal(_SpoofedRecordDigestJournal):
    def append(self, report: object) -> PerformanceLoadReceipt:
        typed = report  # type: ignore[assignment]
        object.__setattr__(typed, "dataset_id", "MUTATED-BY-HOSTILE-JOURNAL")
        report_sha256 = performance_load_report_sha256(typed)
        previous = "0" * 64
        return PerformanceLoadReceipt(
            run_id=typed.run_id,
            report_sha256=report_sha256,
            sequence=1,
            previous_record_sha256=previous,
            record_sha256=performance_load_record_sha256(
                sequence=1,
                run_id=typed.run_id,
                report_sha256=report_sha256,
                request_sha256=typed.request_sha256,
                observed_at=typed.observed_at,
                report_status=typed.report_status,
                evidence_source=typed.evidence_source,
                previous_record_sha256=previous,
            ),
            disposition=PerformanceLoadWriteDisposition.APPENDED,
        )


def test_service_recomputes_report_hash_after_untrusted_append(
    perf_request: object,
) -> None:
    service = PerformanceLoadEvaluationService(journal=_MutatingReportJournal())
    with pytest.raises(PerformanceLoadFailure) as caught:
        service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.JOURNAL_MISMATCH


class _ActionCountJournal:
    def __init__(self, values: list[int]) -> None:
        self._values = values
        self.appended = False

    @property
    def action_count(self) -> int:
        return self._values.pop(0)

    def append(self, report: object) -> PerformanceLoadReceipt:
        self.appended = True
        typed = report  # type: ignore[assignment]
        previous = "0" * 64
        report_sha256 = performance_load_report_sha256(typed)
        return PerformanceLoadReceipt(
            run_id=typed.run_id,
            report_sha256=report_sha256,
            sequence=1,
            previous_record_sha256=previous,
            record_sha256=performance_load_record_sha256(
                sequence=1,
                run_id=typed.run_id,
                report_sha256=report_sha256,
                request_sha256=typed.request_sha256,
                observed_at=typed.observed_at,
                report_status=typed.report_status,
                evidence_source=typed.evidence_source,
                previous_record_sha256=previous,
            ),
            disposition=PerformanceLoadWriteDisposition.APPENDED,
        )


def test_service_rejects_nonzero_action_count_before_append(
    perf_request: object,
) -> None:
    journal = _ActionCountJournal([1])
    service = PerformanceLoadEvaluationService(journal=journal)
    with pytest.raises(PerformanceLoadFailure) as caught:
        service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.JOURNAL_MISMATCH
    assert journal.appended is False


def test_service_rejects_nonzero_action_count_after_append(
    perf_request: object,
) -> None:
    journal = _ActionCountJournal([0, 1])
    service = PerformanceLoadEvaluationService(journal=journal)
    with pytest.raises(PerformanceLoadFailure) as caught:
        service.evaluate_and_record(perf_request)  # type: ignore[arg-type]
    assert caught.value.code is PerformanceLoadFailureCode.JOURNAL_MISMATCH
    assert journal.appended is True
