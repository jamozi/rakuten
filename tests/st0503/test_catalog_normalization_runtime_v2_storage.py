"""Durability, recovery, path, and tamper checks for ST-0503 V2."""

from __future__ import annotations

import os
from pathlib import Path
import sqlite3
from threading import Barrier, Lock, Thread

import pytest

from raos.adapters.sqlite_catalog_normalization_runtime_v2 import (
    CatalogNormalizationSqliteCommitFaultV2,
    OwnerPrivateSqliteCatalogNormalizationStoreV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    CatalogCommitRecoveryOutcomeV2,
    CatalogNormalizationRuntimeFailure,
    CatalogNormalizationRuntimeFailureCode,
    CatalogReplayStatusV2,
)

from runtime_v2_fixtures import (
    normalization_service_v2,
    normalization_store_v2,
    source_fixture_v2,
)


def _assert_code(
    caught: pytest.ExceptionInfo[CatalogNormalizationRuntimeFailure],
    code: CatalogNormalizationRuntimeFailureCode,
) -> None:
    assert caught.value.code is code
    assert caught.value.args == (code.value,)


def test_owner_private_modes_restart_hash_chain_and_recovery(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    result = normalization_service_v2(fixture=fixture, store=store).normalize(
        fixture.command
    )

    assert (store.database_path.parent.stat().st_mode & 0o777) == 0o700
    assert (store.database_path.stat().st_mode & 0o777) == 0o600
    assert result.persisted.previous_chain_hash == "0" * 64
    assert result.persisted.chain_hash != result.persisted.previous_chain_hash

    restarted = OwnerPrivateSqliteCatalogNormalizationStoreV2(
        environment=RuntimeEnvironment.CI,
        root=store.database_path.parent,
    )
    assert restarted.current_version == 1
    assert restarted.lookup(fixture.command) == result.persisted
    recovery = restarted.recover_commit(fixture.command)
    assert recovery.outcome is CatalogCommitRecoveryOutcomeV2.COMMITTED
    assert recovery.persisted == result.persisted


def test_unknown_after_commit_is_recovered_without_duplicate_write(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(
        tmp_path,
        faults=(CatalogNormalizationSqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,),
    )
    service = normalization_service_v2(fixture=fixture, store=store)

    result = service.normalize(fixture.command)
    replay = service.normalize(fixture.command)

    assert result.replay_status is CatalogReplayStatusV2.RECOVERED_COMMIT
    assert replay.replay_status is CatalogReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == result.persisted
    assert store.current_version == 1


@pytest.mark.parametrize(
    ("fault", "expected_code"),
    (
        (
            CatalogNormalizationSqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
            CatalogNormalizationRuntimeFailureCode.COMMIT_KNOWN_ROLLBACK,
        ),
        (
            CatalogNormalizationSqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            CatalogNormalizationRuntimeFailureCode.COMMIT_UNKNOWN,
        ),
    ),
)
def test_precommit_faults_leave_no_partial_batch(
    tmp_path: Path,
    fault: CatalogNormalizationSqliteCommitFaultV2,
    expected_code: CatalogNormalizationRuntimeFailureCode,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path, faults=(fault,))
    service = normalization_service_v2(fixture=fixture, store=store)

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        service.normalize(fixture.command)

    _assert_code(caught, expected_code)
    assert store.current_version == 0
    recovery = store.recover_commit(fixture.command)
    assert recovery.outcome is CatalogCommitRecoveryOutcomeV2.NOT_COMMITTED
    assert recovery.persisted is None


def test_stale_catalog_cas_is_rejected_before_any_partial_write(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    service = normalization_service_v2(fixture=fixture, store=store)
    service.normalize(fixture.command)
    second_fixture = source_fixture_v2(
        tmp_path / "second-source",
        item_ordinals=(3,),
        normalize_operation_index=1,
        expected_catalog_version=0,
    )
    second_service = normalization_service_v2(
        fixture=second_fixture,
        store=store,
    )

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        second_service.normalize(second_fixture.command)

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT)
    assert store.current_version == 1
    assert store.recover_commit(second_fixture.command).outcome is (
        CatalogCommitRecoveryOutcomeV2.NOT_COMMITTED
    )


def test_concurrent_expected_version_zero_commits_have_one_atomic_winner(
    tmp_path: Path,
) -> None:
    first_fixture = source_fixture_v2(tmp_path / "first", item_ordinals=(1,))
    second_fixture = source_fixture_v2(
        tmp_path / "second",
        item_ordinals=(2,),
        normalize_operation_index=1,
    )
    store = normalization_store_v2(tmp_path / "catalog")
    services = (
        normalization_service_v2(fixture=first_fixture, store=store),
        normalization_service_v2(fixture=second_fixture, store=store),
    )
    commands = (first_fixture.command, second_fixture.command)
    barrier = Barrier(2)
    lock = Lock()
    outcomes: list[tuple[str, object]] = []

    def invoke(index: int) -> None:
        barrier.wait()
        try:
            value: object = services[index].normalize(commands[index])
            kind = "committed"
        except CatalogNormalizationRuntimeFailure as error:
            value = error.code
            kind = "failed"
        with lock:
            outcomes.append((kind, value))

    threads = (Thread(target=invoke, args=(0,)), Thread(target=invoke, args=(1,)))
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert [kind for kind, _value in outcomes].count("committed") == 1
    assert [kind for kind, _value in outcomes].count("failed") == 1
    failure = next(value for kind, value in outcomes if kind == "failed")
    assert failure is CatalogNormalizationRuntimeFailureCode.CONCURRENCY_CONFLICT
    assert store.current_version == 1


def test_payload_tamper_is_detected_before_repository_read(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    result = normalization_service_v2(fixture=fixture, store=store).normalize(
        fixture.command
    )
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "UPDATE st0503_candidates SET payload_bytes = ? WHERE candidate_id = ?",
            (b"{}", str(result.persisted.batch.candidates[0].candidate_id)),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        store.load_batch(result.persisted.batch.batch_id)

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED)


def test_schema_drift_is_rejected_on_restart(tmp_path: Path) -> None:
    store = normalization_store_v2(tmp_path)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute("PRAGMA user_version = 9")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=store.database_path.parent,
        )

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY)


def test_relative_symlink_hardlink_and_permission_drift_paths_fail_closed(
    tmp_path: Path,
) -> None:
    with pytest.raises(CatalogNormalizationRuntimeFailure) as relative:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=Path("relative-private"),
        )
    _assert_code(relative, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)

    private = tmp_path / "actual-private"
    private.mkdir(mode=0o700)
    alias = tmp_path / "alias-private"
    alias.symlink_to(private, target_is_directory=True)
    with pytest.raises(CatalogNormalizationRuntimeFailure) as symlink:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=alias,
        )
    _assert_code(symlink, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)

    store = normalization_store_v2(tmp_path / "hardlink")
    os.link(store.database_path, store.database_path.parent / "duplicate.sqlite3")
    with pytest.raises(CatalogNormalizationRuntimeFailure) as hardlink:
        _ = store.current_version
    _assert_code(hardlink, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)

    permission_store = normalization_store_v2(tmp_path / "permissions")
    permission_store.database_path.chmod(0o640)
    with pytest.raises(CatalogNormalizationRuntimeFailure) as permissions:
        _ = permission_store.current_version
    _assert_code(permissions, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)
