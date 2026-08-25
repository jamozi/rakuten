"""Durability, recovery, path, schema, and tamper tests for ST-1602 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from threading import Barrier

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_slo_alert_runtime_v2 import (  # noqa: E402
    CommitFault,
    DisabledRecordedAlertNotificationAdapter,
    OwnerPrivateSqliteAlertJournal,
)
from raos.application.ops.slo_alert_runtime_v2 import (  # noqa: E402
    SloAlertRuntimeService,
)
from raos.domain.ops.slo_alert_runtime_v2 import (  # noqa: E402
    AlertConditionState,
    AlertObservation,
    AlertPersistCommand,
    AlertPersistReceipt,
    HoldVariant,
    SloAlertFailure,
    SloAlertFailureCode,
    alert_instance_key,
    compile_runtime_catalog,
    evaluate_alert,
    make_persist_command,
)
from raos.ports.slo_alert_runtime_v2 import (  # noqa: E402
    LocalNotificationOutcome,
)
from scripts import build_st1602_slo_alert_runtime as generator  # noqa: E402


def _owner_directory(tmp_path: Path) -> Path:
    owner = tmp_path / "owner-private"
    owner.mkdir(mode=0o700)
    owner.chmod(0o700)
    return owner


def _observation(
    *,
    condition: AlertConditionState = AlertConditionState.BREACH,
    observed: int = 10_000,
    evaluated: int = 10_010,
    started: int | None = 0,
) -> AlertObservation:
    return AlertObservation(
        alert_id="ALT-005",
        source="SYNTHETIC_RECORDED_FIXTURE_ONLY",
        observed_at_epoch_seconds=observed,
        evaluated_at_epoch_seconds=evaluated,
        fresh_until_epoch_seconds=20_000,
        sample_count=10,
        mature=True,
        condition_state=condition,
        hold_variant=HoldVariant.DEFAULT,
        condition_started_at_epoch_seconds=started,
        cycle_complete=False,
        observation_sha256="a" * 64,
    )


def _service(
    path: Path, *, fault: CommitFault = CommitFault.NONE
) -> tuple[
    SloAlertRuntimeService,
    OwnerPrivateSqliteAlertJournal,
    DisabledRecordedAlertNotificationAdapter,
]:
    journal = OwnerPrivateSqliteAlertJournal(database_path=path, commit_fault=fault)
    notification = DisabledRecordedAlertNotificationAdapter(capacity=20)
    service = SloAlertRuntimeService(
        catalog=compile_runtime_catalog(generator.runtime_catalog()),
        journal=journal,
        notification=notification,
    )
    return service, journal, notification


def test_owner_private_file_round_trip_idempotency_and_restart(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, notification = _service(path)

    first = service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )
    catalog = compile_runtime_catalog(generator.runtime_catalog())
    rule = catalog.alert("ALT-005")
    key = alert_instance_key("ALT-005", "database-primary")
    observation = _observation()
    replay_decision = evaluate_alert(rule, key, observation, None)
    replay_command = make_persist_command(
        rule=rule,
        instance_key=key,
        observation=observation,
        expected_version=0,
        decision=replay_decision,
    )
    replay_receipt = journal.commit(replay_command)

    assert first.receipt.replayed is False
    assert replay_receipt.replayed is True
    assert first.receipt.entry_sha256 == replay_receipt.entry_sha256
    assert (
        notification.record_local(notification.snapshot()[0])
        is LocalNotificationOutcome.REPLAYED_LOCAL_ONLY
    )
    assert journal.verify_integrity() == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    restarted, restarted_journal, _ = _service(path)
    latest = restarted_journal.load_latest("ALT-005:database-primary")
    assert latest is not None and latest.current_version == 1
    second = restarted.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=1,
        observation=_observation(
            condition=AlertConditionState.CLEAR,
            observed=10_100,
            evaluated=10_101,
            started=None,
        ),
    )
    assert second.receipt.current_version == 2
    assert restarted_journal.verify_integrity() == 2


def test_after_commit_ambiguity_is_recovered_exactly(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, _ = _service(path, fault=CommitFault.AFTER_COMMIT)

    result = service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )

    assert result.receipt.replayed is True
    assert journal.verify_integrity() == 1


def test_before_commit_ambiguity_has_no_row_and_cannot_be_forged(
    tmp_path: Path,
) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, _ = _service(path, fault=CommitFault.BEFORE_COMMIT)

    with pytest.raises(SloAlertFailure) as caught:
        service.evaluate_alert_step(
            instance_id="database-primary",
            expected_version=0,
            observation=_observation(),
        )
    assert caught.value.code is SloAlertFailureCode.RECOVERY_NOT_FOUND
    assert journal.verify_integrity() == 0


def test_sqlite_commit_error_after_commit_is_recovered_exactly(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, _ = _service(path, fault=CommitFault.SQLITE_ERROR_AFTER_COMMIT)

    result = service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )

    assert result.receipt.replayed is True
    assert journal.verify_integrity() == 1


def test_sqlite_commit_error_without_exact_row_is_commit_unknown(
    tmp_path: Path,
) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, _ = _service(path, fault=CommitFault.SQLITE_ERROR_BEFORE_COMMIT)

    with pytest.raises(SloAlertFailure) as caught:
        service.evaluate_alert_step(
            instance_id="database-primary",
            expected_version=0,
            observation=_observation(),
        )

    assert caught.value.code is SloAlertFailureCode.COMMIT_UNKNOWN
    assert journal.verify_integrity() == 0


def test_stale_expected_version_is_rejected_without_append(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, journal, _ = _service(path)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )

    with pytest.raises(SloAlertFailure) as caught:
        service.evaluate_alert_step(
            instance_id="database-primary",
            expected_version=0,
            observation=_observation(
                condition=AlertConditionState.CLEAR,
                observed=10_100,
                evaluated=10_101,
                started=None,
            ),
        )
    assert caught.value.code is SloAlertFailureCode.CONCURRENCY_CONFLICT
    assert journal.verify_integrity() == 1


def test_concurrent_compare_and_swap_allows_exactly_one_append(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    first_journal = OwnerPrivateSqliteAlertJournal(database_path=path)
    second_journal = OwnerPrivateSqliteAlertJournal(database_path=path)
    catalog = compile_runtime_catalog(generator.runtime_catalog())
    rule = catalog.alert("ALT-005")
    key = alert_instance_key("ALT-005", "database-primary")

    def command(observation: AlertObservation) -> AlertPersistCommand:
        decision = evaluate_alert(rule, key, observation, None)
        return make_persist_command(
            rule=rule,
            instance_key=key,
            observation=observation,
            expected_version=0,
            decision=decision,
        )

    commands = (
        command(_observation()),
        command(replace(_observation(), observation_sha256="b" * 64)),
    )
    barrier = Barrier(2)

    def commit(
        journal: OwnerPrivateSqliteAlertJournal,
        candidate: AlertPersistCommand,
    ) -> AlertPersistReceipt | SloAlertFailureCode:
        barrier.wait()
        try:
            return journal.commit(candidate)
        except SloAlertFailure as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(commit, first_journal, commands[0])
        second_future = executor.submit(commit, second_journal, commands[1])
        results = (
            first_future.result(),
            second_future.result(),
        )

    assert sum(type(result) is AlertPersistReceipt for result in results) == 1
    assert (
        sum(result is SloAlertFailureCode.CONCURRENCY_CONFLICT for result in results)
        == 1
    )
    assert first_journal.verify_integrity() == 1


def test_result_tamper_is_detected_on_restart(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    service, _, _ = _service(path)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA ignore_check_constraints = ON")
    connection.execute(
        "UPDATE alert_journal SET result_json = ? WHERE sequence = 1",
        (b"{}",),
    )
    connection.commit()
    connection.close()

    with pytest.raises(SloAlertFailure) as caught:
        OwnerPrivateSqliteAlertJournal(database_path=path)
    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED


def test_same_columns_weakened_constraint_schema_is_rejected(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    _service(path)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA writable_schema = ON")
    connection.execute(
        "UPDATE sqlite_master SET sql = replace(sql, "
        "'CHECK (current_version >= 1)', 'CHECK (current_version >= 0)') "
        "WHERE name = 'alert_instance'"
    )
    connection.commit()
    connection.close()

    with pytest.raises(SloAlertFailure) as caught:
        OwnerPrivateSqliteAlertJournal(database_path=path)
    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED


@pytest.mark.parametrize("partial", [False, True])
def test_preexisting_empty_or_partial_database_is_never_initialized(
    tmp_path: Path, *, partial: bool
) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    if partial:
        connection = sqlite3.connect(path)
        connection.execute("CREATE TABLE attacker_owned (value TEXT)")
        connection.commit()
        connection.close()
    else:
        path.touch(mode=0o600)
    path.chmod(0o600)

    with pytest.raises(SloAlertFailure) as caught:
        OwnerPrivateSqliteAlertJournal(database_path=path)

    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED
    if not partial:
        assert path.stat().st_size == 0


def test_live_file_identity_rejects_valid_snapshot_replacement(tmp_path: Path) -> None:
    owner = _owner_directory(tmp_path)
    path = owner / "alerts.sqlite3"
    service, journal, _ = _service(path)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )
    snapshot = owner / "valid-old.sqlite3"
    shutil.copyfile(path, snapshot)
    snapshot.chmod(0o600)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=1,
        observation=_observation(
            condition=AlertConditionState.CLEAR,
            observed=10_100,
            evaluated=10_101,
            started=None,
        ),
    )

    os.replace(snapshot, path)
    path.chmod(0o600)
    with pytest.raises(SloAlertFailure) as caught:
        journal.verify_integrity()
    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED


def test_live_monotonic_head_rejects_in_place_valid_rollback(tmp_path: Path) -> None:
    owner = _owner_directory(tmp_path)
    path = owner / "alerts.sqlite3"
    service, journal, _ = _service(path)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=0,
        observation=_observation(),
    )
    snapshot = owner / "valid-old.sqlite3"
    shutil.copyfile(path, snapshot)
    snapshot.chmod(0o600)
    service.evaluate_alert_step(
        instance_id="database-primary",
        expected_version=1,
        observation=_observation(
            condition=AlertConditionState.CLEAR,
            observed=10_100,
            evaluated=10_101,
            started=None,
        ),
    )
    identity = (path.stat().st_dev, path.stat().st_ino)

    shutil.copyfile(snapshot, path)
    path.chmod(0o600)
    assert (path.stat().st_dev, path.stat().st_ino) == identity
    with pytest.raises(SloAlertFailure) as caught:
        journal.verify_integrity()
    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED


def test_extra_trigger_is_rejected_as_owned_schema_drift(tmp_path: Path) -> None:
    path = _owner_directory(tmp_path) / "alerts.sqlite3"
    _service(path)
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TRIGGER forbidden_extra AFTER INSERT ON alert_journal BEGIN SELECT 1; END"
    )
    connection.commit()
    connection.close()

    with pytest.raises(SloAlertFailure) as caught:
        OwnerPrivateSqliteAlertJournal(database_path=path)
    assert caught.value.code is SloAlertFailureCode.JOURNAL_TAMPERED


def test_symlink_hardlink_and_weak_permissions_are_rejected(tmp_path: Path) -> None:
    owner = _owner_directory(tmp_path)
    outside = tmp_path / "outside.sqlite3"
    outside.write_bytes(b"")
    outside.chmod(0o600)
    symlink = owner / "symlink.sqlite3"
    symlink.symlink_to(outside)
    with pytest.raises(SloAlertFailure):
        OwnerPrivateSqliteAlertJournal(database_path=symlink)
    hardlink = owner / "hardlink.sqlite3"
    os.link(outside, hardlink)
    with pytest.raises(SloAlertFailure):
        OwnerPrivateSqliteAlertJournal(database_path=hardlink)
    weak = tmp_path / "weak"
    weak.mkdir(mode=0o755)
    weak.chmod(0o755)
    with pytest.raises(SloAlertFailure):
        OwnerPrivateSqliteAlertJournal(database_path=weak / "alerts.sqlite3")
