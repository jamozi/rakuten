"""Hostile persistence, concurrency, restart, and ambiguity checks for ST-0603."""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from threading import Event, get_ident
from typing import Any, cast

import pytest

from raos.adapters.sqlite_fact_conflict_runtime_v2 import (
    FactConflictSqliteCommitFaultV2,
    OwnerPrivateSqliteFactConflictStoreV2,
)
from raos.application.evidence.fact_conflict_runtime_v2 import (
    DurableFactConflictDetectionServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.fact_conflict_runtime_v2 import (
    FactConflictDetectionResultV2,
    FactConflictFailureCodeV2,
    FactConflictFailureV2,
    FactConflictReplayStatusV2,
)
from tests.st0603.st0603_runtime_v2_fixtures import (
    conflict_store_v2,
    derive_persisted_fact_v2,
    exact_persisted_fact_v2,
)


def _code(call: object) -> FactConflictFailureCodeV2:
    assert callable(call)
    with pytest.raises(FactConflictFailureV2) as captured:
        call()
    return captured.value.code


@pytest.fixture()
def st0603_sqlite_root_v2() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(prefix="st0603-sqlite-", dir="/tmp") as raw:
        root = Path(raw)
        root.chmod(0o700)
        yield root


def _inputs(root: Path, *, label: str = "changed", delta: int = 1):
    first = exact_persisted_fact_v2(root / "upstream")
    second = derive_persisted_fact_v2(first, label=label, price_delta=delta)
    return first, second


def test_atomic_commit_replay_and_all_exact_readbacks(st0603_sqlite_root_v2) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    service = DurableFactConflictDetectionServiceV2(store)
    first = service.detect(inputs=inputs)
    replay = service.detect(inputs=inputs[::-1])
    assert first.replay_status is FactConflictReplayStatusV2.DIRECT_COMMIT
    assert replay.replay_status is FactConflictReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == first.persisted
    persisted = first.persisted
    assert store.verify_chain() == (persisted.chain_hash, 1)
    assert store.load_batch(persisted.batch.scan_id) == persisted.batch
    assert store.load_outbox(persisted.event.event_id) == persisted.event
    assert (
        tuple(
            store.load_conflict(item.conflict_id) for item in persisted.batch.conflicts
        )
        == persisted.batch.conflicts
    )
    assert tuple(store.load_queue(item.queue_id) for item in persisted.batch.queue) == (
        persisted.batch.queue
    )
    assert (
        first.external_action_count,
        first.provider_action_count,
        first.publication_action_count,
        first.ai_action_count,
    ) == (0, 0, 0, 0)


def test_restart_retains_exact_chain_without_cross_restart_rollback_claim(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    root = st0603_sqlite_root_v2 / "store"
    first_store = conflict_store_v2(root)
    persisted = (
        DurableFactConflictDetectionServiceV2(first_store)
        .detect(inputs=inputs)
        .persisted
    )
    restarted = conflict_store_v2(root)
    assert restarted.verify_chain() == (persisted.chain_hash, 1)
    assert restarted.recover_exact(persisted.command) == persisted


def test_zero_conflict_scan_and_later_conflict_append_atomically(
    st0603_sqlite_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_sqlite_root_v2 / "upstream")
    equal = derive_persisted_fact_v2(first, label="equal")
    changed = derive_persisted_fact_v2(first, label="changed-later", price_delta=1)
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    service = DurableFactConflictDetectionServiceV2(store)
    no_conflict = service.detect(inputs=(first, equal)).persisted
    conflict = service.detect(inputs=(first, changed)).persisted
    assert no_conflict.sequence == 1
    assert no_conflict.batch.conflicts == no_conflict.batch.queue == ()
    assert no_conflict.event.conflict_ids == no_conflict.event.queue_ids == ()
    assert conflict.sequence == 2 and len(conflict.batch.conflicts) == 1
    assert store.verify_chain() == (conflict.chain_hash, 2)


def test_repeated_fact_pair_in_expanded_scan_has_scan_bound_identity(
    st0603_sqlite_root_v2,
) -> None:
    first = exact_persisted_fact_v2(st0603_sqlite_root_v2 / "upstream")
    changed = derive_persisted_fact_v2(first, label="changed", price_delta=1)
    equal = derive_persisted_fact_v2(first, label="third-equal")
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    service = DurableFactConflictDetectionServiceV2(store)
    initial = service.detect(inputs=(first, changed)).persisted
    expanded = service.detect(inputs=(first, changed, equal)).persisted
    assert initial.sequence == 1 and expanded.sequence == 2
    assert len(initial.batch.conflicts) == 1
    assert len(expanded.batch.conflicts) == 2
    assert initial.batch.conflicts[0].conflict_id not in {
        item.conflict_id for item in expanded.batch.conflicts
    }
    assert all(
        item.scan_id == expanded.batch.scan_id for item in expanded.batch.conflicts
    )
    assert store.verify_chain() == (expanded.chain_hash, 2)


def test_unknown_after_commit_recovers_exact_durable_record(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(
        st0603_sqlite_root_v2 / "store",
        faults=(FactConflictSqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,),
    )
    result = DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    assert result.replay_status is FactConflictReplayStatusV2.RECOVERED_COMMIT
    assert store.recover_exact(result.persisted.command) == result.persisted
    assert store.verify_chain() == (result.persisted.chain_hash, 1)


@pytest.mark.parametrize(
    ("fault", "expected"),
    [
        (
            FactConflictSqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
            FactConflictFailureCodeV2.COMMIT_KNOWN_ROLLBACK,
        ),
        (
            FactConflictSqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            FactConflictFailureCodeV2.COMMIT_UNKNOWN,
        ),
    ],
)
def test_before_commit_faults_leave_no_durable_record(
    st0603_sqlite_root_v2,
    fault: FactConflictSqliteCommitFaultV2,
    expected: FactConflictFailureCodeV2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(
        st0603_sqlite_root_v2 / "store",
        faults=(fault,),
    )
    service = DurableFactConflictDetectionServiceV2(store)
    assert _code(lambda: service.detect(inputs=inputs)) is expected
    assert store.verify_chain()[1] == 0


def test_concurrent_calls_commit_once_and_replay_exactly(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    root = st0603_sqlite_root_v2 / "store"
    stores = tuple(conflict_store_v2(root) for _item in range(4))
    services = tuple(DurableFactConflictDetectionServiceV2(item) for item in stores)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = tuple(
            pool.map(lambda service: service.detect(inputs=inputs), services)
        )
    assert len({item.persisted.chain_hash for item in results}) == 1
    assert (
        sum(
            item.replay_status is FactConflictReplayStatusV2.DIRECT_COMMIT
            for item in results
        )
        == 1
    )
    assert all(store.verify_chain()[1] == 1 for store in stores)


def test_integrity_reads_share_one_snapshot_and_release_owned_transaction(
    st0603_sqlite_root_v2,
    monkeypatch,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    root = st0603_sqlite_root_v2 / "store"
    observed_transactions: list[bool] = []
    original = OwnerPrivateSqliteFactConflictStoreV2._verify_integrity

    def recording_verify_integrity(
        connection: sqlite3.Connection,
    ) -> tuple[str, int]:
        observed_transactions.append(connection.in_transaction)
        return original(connection)

    monkeypatch.setattr(
        OwnerPrivateSqliteFactConflictStoreV2,
        "_verify_integrity",
        staticmethod(recording_verify_integrity),
    )

    store = conflict_store_v2(root)
    assert observed_transactions == [True]
    observed_transactions.clear()
    store = conflict_store_v2(root)
    assert observed_transactions == [True]
    observed_transactions.clear()

    DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    store.verify_chain()
    assert observed_transactions
    assert all(observed_transactions)

    connection = store._connect(verify=False)  # noqa: SLF001
    try:
        store._verified_state(connection)  # noqa: SLF001
        assert not connection.in_transaction
    finally:
        store._close_safely(connection)  # noqa: SLF001


def test_constructor_snapshot_is_stable_during_concurrent_commit(
    st0603_sqlite_root_v2,
    monkeypatch,
) -> None:
    root = st0603_sqlite_root_v2 / "store"
    initial_store = conflict_store_v2(root)
    initial = DurableFactConflictDetectionServiceV2(initial_store).detect(
        inputs=_inputs(st0603_sqlite_root_v2 / "initial")
    )
    writer_store = conflict_store_v2(root)
    writer_service = DurableFactConflictDetectionServiceV2(writer_store)
    writer_inputs = _inputs(
        st0603_sqlite_root_v2 / "concurrent",
        label="concurrent",
        delta=2,
    )
    writer_start = Event()
    writer_at_commit = Event()
    writer_committed = Event()
    constructor_scan_seen = Event()
    commit_was_blocked: list[bool] = []
    constructor_thread = get_ident()
    original_connect = sqlite3.connect

    class CoordinatedConnection(sqlite3.Connection):
        def execute(
            self,
            sql: str,
            parameters: Any = (),
            /,
        ) -> sqlite3.Cursor:
            if get_ident() != constructor_thread and sql == "COMMIT":
                writer_at_commit.set()
                result = super().execute(sql, parameters)
                writer_committed.set()
                return result
            if (
                get_ident() == constructor_thread
                and sql == "SELECT * FROM st0603_scans ORDER BY sequence"
                and not constructor_scan_seen.is_set()
            ):
                constructor_scan_seen.set()
                writer_start.set()
                assert writer_at_commit.wait(timeout=2.0)
                commit_was_blocked.append(not writer_committed.wait(timeout=0.25))
            return super().execute(sql, parameters)

    def coordinated_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        kwargs["factory"] = CoordinatedConnection
        return cast(sqlite3.Connection, original_connect(*args, **kwargs))

    def append_while_constructing() -> FactConflictDetectionResultV2:
        assert writer_start.wait(timeout=2.0)
        return writer_service.detect(inputs=writer_inputs)

    monkeypatch.setattr(sqlite3, "connect", coordinated_connect)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(append_while_constructing)
        restarted = conflict_store_v2(root)
        appended = future.result(timeout=5.0)

    assert constructor_scan_seen.is_set()
    assert writer_at_commit.is_set()
    assert writer_committed.is_set()
    assert commit_was_blocked == [True]
    assert initial.persisted.sequence == 1
    assert appended.persisted.sequence == 2
    assert restarted.verify_chain() == (appended.persisted.chain_hash, 2)


def test_preexisting_empty_partial_and_wrong_mode_databases_fail_closed(
    st0603_sqlite_root_v2,
) -> None:
    for name, partial in (("empty", False), ("partial", True)):
        private = st0603_sqlite_root_v2 / name
        private.mkdir(mode=0o700)
        database = private / "st0603-fact-conflicts.sqlite3"
        if partial:
            connection = sqlite3.connect(database)
            connection.execute("CREATE TABLE foreign_table(value TEXT)")
            connection.close()
        else:
            database.touch(mode=0o600)
        database.chmod(0o600)
        assert (
            _code(
                lambda private=private: OwnerPrivateSqliteFactConflictStoreV2(
                    environment=RuntimeEnvironment.CI,
                    root=private,
                )
            )
            is FactConflictFailureCodeV2.SCHEMA_INTEGRITY
        )

    private = st0603_sqlite_root_v2 / "wrong-mode"
    private.mkdir(mode=0o700)
    database = private / "st0603-fact-conflicts.sqlite3"
    database.touch(mode=0o600)
    database.chmod(0o644)
    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.CI,
                root=private,
            )
        )
        is FactConflictFailureCodeV2.UNSAFE_PATH
    )


def test_preexisting_foreign_wal_database_is_rejected_without_mode_conversion(
    st0603_sqlite_root_v2,
) -> None:
    private = st0603_sqlite_root_v2 / "foreign-wal"
    private.mkdir(mode=0o700)
    database = private / "st0603-fact-conflicts.sqlite3"
    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
    connection.execute("CREATE TABLE foreign_table(value TEXT)")
    connection.commit()
    connection.close()
    database.chmod(0o600)

    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.CI,
                root=private,
            )
        )
        is FactConflictFailureCodeV2.STORE_UNAVAILABLE
    )
    connection = sqlite3.connect(database)
    assert connection.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    connection.close()


def test_symlink_hardlink_and_inode_replacement_fail_closed(
    st0603_sqlite_root_v2,
) -> None:
    target = st0603_sqlite_root_v2 / "target"
    target.mkdir(mode=0o700)
    symlink = st0603_sqlite_root_v2 / "root-link"
    symlink.symlink_to(target, target_is_directory=True)
    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.CI,
                root=symlink,
            )
        )
        is FactConflictFailureCodeV2.UNSAFE_PATH
    )

    database_root = st0603_sqlite_root_v2 / "database-link-root"
    database_root.mkdir(mode=0o700)
    database_target = st0603_sqlite_root_v2 / "database-target"
    database_target.touch(mode=0o600)
    (database_root / "st0603-fact-conflicts.sqlite3").symlink_to(database_target)
    assert (
        _code(
            lambda: OwnerPrivateSqliteFactConflictStoreV2(
                environment=RuntimeEnvironment.CI,
                root=database_root,
            )
        )
        is FactConflictFailureCodeV2.UNSAFE_PATH
    )

    hard_store = conflict_store_v2(st0603_sqlite_root_v2 / "hard-store")
    os.link(hard_store.database_path, hard_store.database_path.with_suffix(".link"))
    assert _code(hard_store.verify_chain) is FactConflictFailureCodeV2.UNSAFE_PATH

    replace_store = conflict_store_v2(st0603_sqlite_root_v2 / "replace-store")
    replacement = replace_store.database_path.with_suffix(".replacement")
    shutil.copyfile(replace_store.database_path, replacement)
    replacement.chmod(0o600)
    os.replace(replacement, replace_store.database_path)
    assert _code(replace_store.verify_chain) is (
        FactConflictFailureCodeV2.TAMPER_DETECTED
    )


def test_append_only_triggers_and_rehashed_payload_tamper_are_detected(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    result = DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    connection = sqlite3.connect(store.database_path)
    with pytest.raises(sqlite3.DatabaseError):
        connection.execute("DELETE FROM st0603_review_queue")
    with pytest.raises(sqlite3.DatabaseError):
        connection.execute(
            "UPDATE st0603_conflicts SET payload_sha256 = ?",
            ("f" * 64,),
        )
    connection.execute("DROP TRIGGER st0603_conflicts_no_update")
    tampered = b"{}"
    connection.execute(
        "UPDATE st0603_conflicts SET payload_bytes = ?, payload_sha256 = ?",
        (tampered, hashlib.sha256(tampered).hexdigest()),
    )
    connection.execute(
        "CREATE TRIGGER st0603_conflicts_no_update BEFORE UPDATE ON st0603_conflicts BEGIN SELECT RAISE(ABORT, 'append_only'); END"
    )
    connection.commit()
    connection.close()
    assert _code(store.verify_chain) is FactConflictFailureCodeV2.TAMPER_DETECTED
    assert result.persisted.batch.conflicts


def test_process_local_count_and_prefix_monotonicity_rejects_rollback(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    snapshot = store.database_path.with_suffix(".empty-snapshot")
    shutil.copyfile(store.database_path, snapshot)
    snapshot.chmod(0o600)
    DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs)
    identity_before = store.database_path.stat()
    shutil.copyfile(snapshot, store.database_path)
    identity_after = store.database_path.stat()
    assert (identity_before.st_dev, identity_before.st_ino) == (
        identity_after.st_dev,
        identity_after.st_ino,
    )
    assert _code(store.verify_chain) is FactConflictFailureCodeV2.TAMPER_DETECTED


def test_idempotency_payload_mutation_is_never_accepted(
    st0603_sqlite_root_v2,
) -> None:
    inputs = _inputs(st0603_sqlite_root_v2)
    store = conflict_store_v2(st0603_sqlite_root_v2 / "store")
    persisted = (
        DurableFactConflictDetectionServiceV2(store).detect(inputs=inputs).persisted
    )
    object.__setattr__(persisted.command, "payload_sha256", "b" * 64)
    assert _code(lambda: store.lookup(persisted.command)) is (
        FactConflictFailureCodeV2.IDEMPOTENCY_CONFLICT
    )
