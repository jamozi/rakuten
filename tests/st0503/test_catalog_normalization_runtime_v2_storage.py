"""Durability, recovery, path, and tamper checks for ST-0503 V2."""

from __future__ import annotations

import hashlib
import json
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


_DATABASE_NAME = "st0503-catalog-normalization.sqlite3"


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


def test_independent_store_instances_preserve_atomic_cas_under_concurrency(
    tmp_path: Path,
) -> None:
    first_fixture = source_fixture_v2(tmp_path / "first", item_ordinals=(1,))
    second_fixture = source_fixture_v2(
        tmp_path / "second",
        item_ordinals=(2,),
        normalize_operation_index=1,
    )
    first_store = normalization_store_v2(tmp_path / "catalog")
    second_store = OwnerPrivateSqliteCatalogNormalizationStoreV2(
        environment=RuntimeEnvironment.CI,
        root=first_store.database_path.parent,
    )
    services = (
        normalization_service_v2(fixture=first_fixture, store=first_store),
        normalization_service_v2(fixture=second_fixture, store=second_store),
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
    assert first_store.current_version == second_store.current_version == 1


def test_payload_tamper_is_detected_before_repository_read(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    result = normalization_service_v2(fixture=fixture, store=store).normalize(
        fixture.command
    )
    connection = sqlite3.connect(store.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0503_V2"):
            connection.execute(
                "UPDATE st0503_candidates SET payload_bytes = ? WHERE candidate_id = ?",
                (b"{}", str(result.persisted.batch.candidates[0].candidate_id)),
            )
        connection.rollback()
        connection.execute("DROP TRIGGER st0503_candidates_no_update")
        connection.execute(
            "UPDATE st0503_candidates SET payload_bytes = ? WHERE candidate_id = ?",
            (b"{}", str(result.persisted.batch.candidates[0].candidate_id)),
        )
        connection.execute(
            "CREATE TRIGGER st0503_candidates_no_update "
            "BEFORE UPDATE ON st0503_candidates "
            "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ST0503_V2'); END"
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


def test_preexisting_empty_database_is_rejected_without_initialization_or_mutation(
    tmp_path: Path,
) -> None:
    private = tmp_path / "preexisting-empty"
    private.mkdir(mode=0o700)
    database = private / _DATABASE_NAME
    descriptor = os.open(
        database,
        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    os.close(descriptor)
    before = database.stat()

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=private,
        )

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY)
    after = database.stat()
    assert database.read_bytes() == b""
    assert (after.st_dev, after.st_ino, after.st_size) == (
        before.st_dev,
        before.st_ino,
        0,
    )


def test_preexisting_partial_and_foreign_databases_are_never_repaired(
    tmp_path: Path,
) -> None:
    for name, initialize in (
        ("partial", "CREATE TABLE st0503_state(state_id INTEGER)"),
        ("foreign", "CREATE TABLE unrelated(payload TEXT)"),
    ):
        private = tmp_path / name
        private.mkdir(mode=0o700)
        database = private / _DATABASE_NAME
        connection = sqlite3.connect(database)
        try:
            connection.execute(initialize)
            connection.commit()
        finally:
            connection.close()
        database.chmod(0o600)
        before = database.read_bytes()

        with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
            OwnerPrivateSqliteCatalogNormalizationStoreV2(
                environment=RuntimeEnvironment.CI,
                root=private,
            )

        _assert_code(caught, CatalogNormalizationRuntimeFailureCode.SCHEMA_INTEGRITY)
        assert database.read_bytes() == before


def test_preexisting_symlink_and_non_private_database_fail_closed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"not-a-database")
    target.chmod(0o600)
    symlink_root = tmp_path / "symlink-database"
    symlink_root.mkdir(mode=0o700)
    (symlink_root / _DATABASE_NAME).symlink_to(target)

    with pytest.raises(CatalogNormalizationRuntimeFailure) as symlink:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=symlink_root,
        )
    _assert_code(symlink, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)

    permission_root = tmp_path / "non-private-database"
    permission_root.mkdir(mode=0o700)
    database = permission_root / _DATABASE_NAME
    database.write_bytes(b"")
    database.chmod(0o640)
    with pytest.raises(CatalogNormalizationRuntimeFailure) as permission:
        OwnerPrivateSqliteCatalogNormalizationStoreV2(
            environment=RuntimeEnvironment.CI,
            root=permission_root,
        )
    _assert_code(permission, CatalogNormalizationRuntimeFailureCode.UNSAFE_PATH)


def test_live_store_rejects_valid_path_replacement_by_inode(tmp_path: Path) -> None:
    store = normalization_store_v2(tmp_path)
    database = store.database_path
    valid_bytes = database.read_bytes()
    original_identity = (database.stat().st_dev, database.stat().st_ino)
    parked = database.with_name("parked.sqlite3")
    os.replace(database, parked)
    descriptor = os.open(
        database,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    try:
        os.write(descriptor, valid_bytes)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    assert (database.stat().st_dev, database.stat().st_ino) != original_identity

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        _ = store.current_version

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED)


def test_live_store_rejects_same_inode_rollback_to_older_valid_snapshot(
    tmp_path: Path,
) -> None:
    fixture = source_fixture_v2(tmp_path / "source")
    store = normalization_store_v2(tmp_path / "catalog")
    database = store.database_path
    older_valid_snapshot = database.read_bytes()
    identity = (database.stat().st_dev, database.stat().st_ino)
    normalization_service_v2(fixture=fixture, store=store).normalize(fixture.command)
    assert store.current_version == 1

    descriptor = os.open(database, os.O_WRONLY | os.O_TRUNC | os.O_CLOEXEC)
    try:
        os.write(descriptor, older_valid_snapshot)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    assert (database.stat().st_dev, database.stat().st_ino) == identity

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        _ = store.current_version

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED)
    restarted_without_external_anchor = OwnerPrivateSqliteCatalogNormalizationStoreV2(
        environment=RuntimeEnvironment.CI,
        root=database.parent,
    )
    assert restarted_without_external_anchor.current_version == 0


def test_schema_is_strict_foreign_key_bound_and_append_only(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    normalization_service_v2(fixture=fixture, store=store).normalize(fixture.command)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        assert connection.execute("PRAGMA user_version").fetchone() == (2,)
        strict = {
            row[1]: row[5]
            for row in connection.execute("PRAGMA table_list").fetchall()
            if str(row[1]).startswith("st0503_")
        }
        assert strict and set(strict.values()) == {1}
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        assert len(triggers) == 16
        assert {
            "st0503_state_no_insert",
            "st0503_state_no_delete",
            "st0503_journal_no_update",
            "st0503_journal_no_delete",
        }.issubset(triggers)
        assert (
            len(
                connection.execute("PRAGMA foreign_key_list(st0503_batches)").fetchall()
            )
            == 1
        )
        assert (
            len(
                connection.execute(
                    "PRAGMA foreign_key_list(st0503_observations)"
                ).fetchall()
            )
            == 3
        )

        for table in (
            "st0503_snapshots",
            "st0503_batches",
            "st0503_candidates",
            "st0503_offers",
            "st0503_observations",
            "st0503_outbox",
            "st0503_journal",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0503_V2"):
                connection.execute(f"DELETE FROM {table}")
            connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0503_V2"):
            connection.execute("DELETE FROM st0503_state")
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0503_V2"):
            connection.execute(
                "INSERT INTO st0503_state VALUES (2, ?, 0, ?)",
                ("0" * 64, "0" * 64),
            )
        connection.rollback()
    finally:
        connection.close()


def test_noncanonical_json_with_recomputed_digest_is_rejected(tmp_path: Path) -> None:
    fixture = source_fixture_v2(tmp_path)
    store = normalization_store_v2(tmp_path)
    normalization_service_v2(fixture=fixture, store=store).normalize(fixture.command)
    connection = sqlite3.connect(store.database_path)
    try:
        row = connection.execute(
            "SELECT operation_id, result_bytes FROM st0503_journal"
        ).fetchone()
        assert row is not None
        noncanonical = json.dumps(
            json.loads(row[1]),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=False,
            indent=2,
        ).encode("utf-8")
        connection.execute("DROP TRIGGER st0503_journal_no_update")
        connection.execute(
            "UPDATE st0503_journal SET result_bytes=?, result_sha256=? WHERE operation_id=?",
            (noncanonical, hashlib.sha256(noncanonical).hexdigest(), row[0]),
        )
        connection.execute(
            "CREATE TRIGGER st0503_journal_no_update "
            "BEFORE UPDATE ON st0503_journal "
            "BEGIN SELECT RAISE(ABORT, 'IMMUTABLE_ST0503_V2'); END"
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(CatalogNormalizationRuntimeFailure) as caught:
        store.lookup(fixture.command)

    _assert_code(caught, CatalogNormalizationRuntimeFailureCode.TAMPER_DETECTED)


def test_duplicate_source_and_conflicting_operation_are_rejected(
    tmp_path: Path,
) -> None:
    first = source_fixture_v2(tmp_path / "first")
    store = normalization_store_v2(tmp_path / "catalog")
    normalization_service_v2(fixture=first, store=store).normalize(first.command)

    conflicting_operation = source_fixture_v2(
        tmp_path / "conflicting-operation",
        item_ordinals=(3,),
        normalize_operation_index=0,
        expected_catalog_version=1,
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as operation:
        normalization_service_v2(
            fixture=conflicting_operation,
            store=store,
        ).normalize(conflicting_operation.command)
    _assert_code(operation, CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT)

    duplicate_source = source_fixture_v2(
        tmp_path / "duplicate-source",
        normalize_operation_index=1,
        expected_catalog_version=1,
    )
    with pytest.raises(CatalogNormalizationRuntimeFailure) as source:
        normalization_service_v2(
            fixture=duplicate_source,
            store=store,
        ).normalize(duplicate_source.command)
    _assert_code(source, CatalogNormalizationRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
    assert store.current_version == 1


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
