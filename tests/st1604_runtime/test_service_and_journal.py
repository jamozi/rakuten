"""Application and durable-journal tests for ST-1604 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import sqlite3
from uuid import UUID

import pytest

from raos.adapters.recorded_performance_load import (
    PerformanceLoadCommitFault,
    RecordedPerformanceLoadJournal,
    _CREATE_REPORT_NO_UPDATE,
)
from raos.application.ops.performance_load import PerformanceLoadEvaluationService
from raos.domain.ops.performance_load import (
    PerformanceLoadFailure,
    PerformanceLoadFailureCode,
    evaluate_performance_load,
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
