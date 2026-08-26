"""ST-1201 created-only SQLite, chain, and commit-recovery hardening."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import sqlite3
from typing import Any, Callable, Literal, cast
from uuid import UUID

import pytest

from .support import consent, envelope, validated_event
from raos.adapters.sqlite_event_collector_runtime_v2 import (
    EventStoreCommitFault,
    SqliteDurableRecordedEventStoreV2,
)
from raos.domain.analytics.event_collector import (
    EventDigest,
    RecordedStoreDisposition,
    ValidatedEvent,
)
from raos.domain.analytics.event_collector_runtime_v2 import (
    DurableEventReceiptV2,
    DurableEventStoreFailure,
    DurableEventStoreFailureCode,
)


_DATABASE_NAME = "st1201-recorded-event-store.sqlite3"


@pytest.fixture
def hardening_root(tmp_path: Path) -> Path:
    root = tmp_path / "st1201-hardening-private"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _database(root: Path) -> Path:
    return root / _DATABASE_NAME


def _event(number: int) -> ValidatedEvent:
    event_id = UUID(f"018f3e90-7b00-7000-8000-{number:012d}")
    return ValidatedEvent(
        envelope=replace(envelope(), event_id=event_id),
        consent=consent(),
    )


def _exchange(
    store: SqliteDurableRecordedEventStoreV2,
    event: ValidatedEvent,
) -> DurableEventReceiptV2:
    return store.exchange_durable(event, EventDigest.of(event))


def _file_evidence(path: Path) -> tuple[bytes, int, int, int, int, int]:
    metadata = path.stat(follow_symlinks=False)
    return (
        path.read_bytes(),
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_mtime_ns,
    )


@pytest.mark.parametrize(
    "kind,payload",
    [
        ("empty", b""),
        ("partial", b"SQLite format 3\x00partial"),
        ("foreign", None),
    ],
)
def test_preexisting_invalid_database_is_rejected_without_modification(
    hardening_root: Path,
    kind: str,
    payload: bytes | None,
) -> None:
    database = _database(hardening_root)
    if kind == "foreign":
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE foreign_owner(value TEXT) STRICT")
            connection.commit()
        finally:
            connection.close()
    else:
        assert payload is not None
        database.write_bytes(payload)
    os.chmod(database, 0o600)
    before = _file_evidence(database)

    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root)

    assert caught.value.code is DurableEventStoreFailureCode.SCHEMA_DRIFT
    assert _file_evidence(database) == before


def test_preexisting_non_private_database_mode_is_unchanged(
    hardening_root: Path,
) -> None:
    database = _database(hardening_root)
    database.write_bytes(b"not-owned-by-the-runtime")
    os.chmod(database, 0o640)
    before = _file_evidence(database)

    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root)

    assert caught.value.code is DurableEventStoreFailureCode.PRIVATE_PATH_INVALID
    assert _file_evidence(database) == before


def test_named_file_replacement_is_detected_by_live_store(
    hardening_root: Path,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    first = _event(120_101)
    _exchange(store, first)
    database = _database(hardening_root)
    moved = hardening_root / "moved.sqlite3"
    database.rename(moved)
    shutil.copyfile(moved, database)
    os.chmod(database, 0o600)

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(store, first)

    assert caught.value.code is DurableEventStoreFailureCode.PRIVATE_PATH_INVALID


def test_same_inode_older_valid_snapshot_is_detected_only_with_live_anchor(
    hardening_root: Path,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    first = _event(120_111)
    second = _event(120_112)
    _exchange(store, first)
    database = _database(hardening_root)
    old_valid_snapshot = database.read_bytes()
    inode = database.stat().st_ino
    _exchange(store, second)
    with database.open("r+b") as stream:
        stream.seek(0)
        stream.write(old_valid_snapshot)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    assert database.stat().st_ino == inode

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(store, first)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED

    # A new instance has no external anchor and therefore accepts this older,
    # internally valid snapshot. ST-1201 intentionally makes no stronger claim.
    restarted = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    assert _exchange(restarted, first).replayed is True


def test_same_count_alternate_valid_prefix_is_detected_by_live_store(
    tmp_path: Path,
) -> None:
    roots = tuple(tmp_path / name for name in ("left", "right"))
    for root in roots:
        root.mkdir(mode=0o700)
        os.chmod(root, 0o700)
    left = SqliteDurableRecordedEventStoreV2(private_root=roots[0])
    right = SqliteDurableRecordedEventStoreV2(private_root=roots[1])
    left_event = _event(120_121)
    right_event = _event(120_122)
    _exchange(left, left_event)
    _exchange(right, right_event)
    replacement = _database(roots[1]).read_bytes()
    left_database = _database(roots[0])
    inode = left_database.stat().st_ino
    with left_database.open("r+b") as stream:
        stream.write(replacement)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    assert left_database.stat().st_ino == inode

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(left, left_event)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED

    restarted = SqliteDurableRecordedEventStoreV2(private_root=roots[0])
    assert _exchange(restarted, right_event).replayed is True


def test_verified_peer_prefix_remains_pinned_after_commit_rollback(
    hardening_root: Path,
) -> None:
    anchored = SqliteDurableRecordedEventStoreV2(
        private_root=hardening_root,
        commit_fault_once=EventStoreCommitFault.BEFORE_COMMIT,
    )
    database = _database(hardening_root)
    empty_valid_snapshot = database.read_bytes()
    inode = database.stat().st_ino
    peer = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _exchange(peer, _event(120_131))

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(anchored, _event(120_132))
    assert caught.value.code is DurableEventStoreFailureCode.COMMIT_NOT_COMMITTED

    with database.open("r+b") as stream:
        stream.write(empty_valid_snapshot)
        stream.truncate()
        stream.flush()
        os.fsync(stream.fileno())
    assert database.stat().st_ino == inode

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(anchored, _event(120_132))
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED


def test_exact_schema_pragmas_guards_and_cas_are_enforced(
    hardening_root: Path,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    connection = store._connect()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    try:
        assert tuple(connection.execute("PRAGMA user_version").fetchone()) == (120102,)
        assert tuple(connection.execute("PRAGMA application_id").fetchone()) == (
            0x52414F53,
        )
        assert tuple(connection.execute("PRAGMA journal_mode").fetchone()) == (
            "delete",
        )
        assert tuple(connection.execute("PRAGMA foreign_keys").fetchone()) == (1,)
        assert tuple(connection.execute("PRAGMA trusted_schema").fetchone()) == (0,)
        assert tuple(connection.execute("PRAGMA temp_store").fetchone()) == (2,)
        assert tuple(connection.execute("PRAGMA synchronous").fetchone()) == (2,)
        assert tuple(connection.execute("PRAGMA secure_delete").fetchone()) == (1,)
        assert tuple(connection.execute("PRAGMA busy_timeout").fetchone()) == (10000,)
        objects = connection.execute(
            "SELECT type,name FROM sqlite_master ORDER BY type,name"
        ).fetchall()
        assert {tuple(row) for row in objects} == {
            ("table", "st1201_event_v2"),
            ("table", "st1201_metadata_v2"),
            ("index", "sqlite_autoindex_st1201_event_v2_1"),
            ("index", "sqlite_autoindex_st1201_event_v2_2"),
            ("trigger", "st1201_event_append_guard_v2"),
            ("trigger", "st1201_event_no_delete_v2"),
            ("trigger", "st1201_event_no_update_v2"),
            ("trigger", "st1201_metadata_guard_update_v2"),
            ("trigger", "st1201_metadata_no_delete_v2"),
            ("trigger", "st1201_metadata_no_insert_v2"),
        }
        assert tuple(
            (row[1], row[2], row[3], row[5], row[6])
            for row in connection.execute(
                "PRAGMA table_xinfo(st1201_metadata_v2)"
            ).fetchall()
        ) == (
            ("singleton", "INTEGER", 1, 1, 0),
            ("schema_version", "TEXT", 1, 0, 0),
            ("event_count", "INTEGER", 1, 0, 0),
            ("event_head_sha256", "TEXT", 1, 0, 0),
            ("record_sha256", "TEXT", 1, 0, 0),
        )
        assert tuple(
            (row[1], row[2], row[3], row[5], row[6])
            for row in connection.execute(
                "PRAGMA table_xinfo(st1201_event_v2)"
            ).fetchall()
        ) == (
            ("sequence", "INTEGER", 1, 1, 0),
            ("event_id", "TEXT", 1, 0, 0),
            ("payload_sha256", "TEXT", 1, 0, 0),
            ("command_sha256", "TEXT", 1, 0, 0),
            ("recovery_sha256", "TEXT", 1, 0, 0),
            ("site_id", "TEXT", 1, 0, 0),
            ("event_name", "TEXT", 1, 0, 0),
            ("source", "TEXT", 1, 0, 0),
            ("schema_version", "TEXT", 1, 0, 0),
            ("received_at", "TEXT", 1, 0, 0),
            ("canonical_event", "BLOB", 1, 0, 0),
            ("previous_record_sha256", "TEXT", 1, 0, 0),
            ("record_sha256", "TEXT", 1, 0, 0),
        )
        assert {
            row[1]: row[5]
            for row in connection.execute("PRAGMA table_list").fetchall()
            if row[1].startswith("st1201_")
        } == {"st1201_event_v2": 1, "st1201_metadata_v2": 1}
        assert (
            connection.execute("PRAGMA foreign_key_list(st1201_event_v2)").fetchall()
            == []
        )
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE st1201_metadata_v2 SET event_count = 2 WHERE singleton = 1"
            )
        connection.execute("ROLLBACK")
    finally:
        connection.close()

    event = validated_event()
    _exchange(store, event)
    connection = store._connect()  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
    try:
        connection.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM st1201_event_v2")
        connection.execute("ROLLBACK")
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE st1201_metadata_v2 SET event_count = event_count "
            "WHERE singleton = 1 AND event_count = 0"
        )
        assert cursor.rowcount == 0
        connection.execute("ROLLBACK")
    finally:
        connection.close()


def _noncanonical_spacing(payload: bytes) -> bytes:
    value = json.loads(payload)
    return json.dumps(value, sort_keys=True).encode("utf-8")


def _uppercase_uuid(payload: bytes) -> bytes:
    value = json.loads(payload)
    value["event_id"] = value["event_id"].upper()
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _offset_time(payload: bytes) -> bytes:
    value = json.loads(payload)
    value["received_at"] = value["received_at"].removesuffix("Z") + "+00:00"
    return json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


@pytest.mark.parametrize(
    "transform",
    [_noncanonical_spacing, _uppercase_uuid, _offset_time],
    ids=["json-spacing", "uppercase-uuid", "offset-time"],
)
def test_noncanonical_persisted_event_bytes_fail_closed(
    hardening_root: Path,
    transform: Callable[[bytes], bytes],
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _exchange(store, validated_event())
    database = _database(hardening_root)
    connection = sqlite3.connect(database)
    try:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'st1201_event_no_update_v2'"
        ).fetchone()
        payload = connection.execute(
            "SELECT canonical_event FROM st1201_event_v2"
        ).fetchone()
        assert trigger is not None and type(trigger[0]) is str
        assert payload is not None and type(payload[0]) is bytes
        connection.execute("DROP TRIGGER st1201_event_no_update_v2")
        connection.execute(
            "UPDATE st1201_event_v2 SET canonical_event = ?",
            (transform(payload[0]),),
        )
        connection.execute(trigger[0])
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED


def test_redundant_event_column_must_equal_canonical_payload(
    hardening_root: Path,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _exchange(store, validated_event())
    connection = sqlite3.connect(_database(hardening_root))
    try:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'st1201_event_no_update_v2'"
        ).fetchone()
        assert trigger is not None and type(trigger[0]) is str
        connection.execute("DROP TRIGGER st1201_event_no_update_v2")
        connection.execute(
            "UPDATE st1201_event_v2 SET site_id = ?",
            ("018f3e90-7b00-7000-8000-000000129999",),
        )
        connection.execute(trigger[0])
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED


@pytest.mark.parametrize(
    "trigger_name,statement",
    [
        (
            "st1201_event_no_update_v2",
            "UPDATE st1201_event_v2 SET command_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        ),
        (
            "st1201_event_no_update_v2",
            "UPDATE st1201_event_v2 SET recovery_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        ),
        (
            "st1201_event_no_update_v2",
            "UPDATE st1201_event_v2 SET previous_record_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        ),
        (
            "st1201_metadata_guard_update_v2",
            "UPDATE st1201_metadata_v2 SET record_sha256 = 'ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff'",
        ),
    ],
    ids=["command", "recovery", "chain", "metadata"],
)
def test_hash_bound_command_recovery_chain_and_metadata_fail_closed(
    hardening_root: Path,
    trigger_name: str,
    statement: str,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _exchange(store, validated_event())
    connection = sqlite3.connect(_database(hardening_root))
    try:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = ?",
            (trigger_name,),
        ).fetchone()
        assert trigger is not None and type(trigger[0]) is str
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.execute(statement)
        connection.execute(trigger[0])
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED


def test_injected_commit_outcomes_are_closed_and_idempotent(
    hardening_root: Path,
) -> None:
    event = validated_event()
    before = SqliteDurableRecordedEventStoreV2(
        private_root=hardening_root,
        commit_fault_once=EventStoreCommitFault.BEFORE_COMMIT,
    )
    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(before, event)
    assert caught.value.code is DurableEventStoreFailureCode.COMMIT_NOT_COMMITTED
    assert (
        _exchange(before, event).disposition
        is RecordedStoreDisposition.RECORDED_ACCEPTED
    )

    second_root = hardening_root.parent / "after-commit-private"
    second_root.mkdir(mode=0o700)
    os.chmod(second_root, 0o700)
    after = SqliteDurableRecordedEventStoreV2(
        private_root=second_root,
        commit_fault_once=EventStoreCommitFault.AFTER_COMMIT,
    )
    receipt = _exchange(after, event)
    assert receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert (
        _exchange(after, event).disposition
        is RecordedStoreDisposition.RECORDED_DUPLICATE
    )


def _install_real_commit_exception(
    monkeypatch: pytest.MonkeyPatch,
    *,
    after_commit: bool,
    recovery_available: bool,
) -> None:
    original_connect = sqlite3.connect
    state = {"fault_used": False}

    class FaultConnection(sqlite3.Connection):
        def execute(
            self,
            sql: str,
            parameters: object = (),
            /,
        ) -> sqlite3.Cursor:
            if sql == "COMMIT" and not state["fault_used"]:
                state["fault_used"] = True
                if after_commit:
                    super().execute(sql, cast(Any, parameters))
                raise sqlite3.OperationalError("simulated closed commit exception")
            return super().execute(sql, cast(Any, parameters))

    def connect(
        database: str,
        *,
        uri: bool,
        isolation_level: Literal["DEFERRED", "EXCLUSIVE", "IMMEDIATE"] | None,
        timeout: float,
        check_same_thread: bool,
    ) -> sqlite3.Connection:
        if state["fault_used"] and not recovery_available:
            raise sqlite3.OperationalError("simulated closed recovery outage")
        return original_connect(
            database,
            uri=uri,
            isolation_level=isolation_level,
            timeout=timeout,
            check_same_thread=check_same_thread,
            factory=FaultConnection,
        )

    monkeypatch.setattr(sqlite3, "connect", connect)


@pytest.mark.parametrize("after_commit", [False, True])
def test_real_commit_exception_is_classified_from_verified_recovery(
    hardening_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_commit: bool,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _install_real_commit_exception(
        monkeypatch,
        after_commit=after_commit,
        recovery_available=True,
    )

    if after_commit:
        receipt = _exchange(store, validated_event())
        assert receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    else:
        with pytest.raises(DurableEventStoreFailure) as caught:
            _exchange(store, validated_event())
        assert caught.value.code is DurableEventStoreFailureCode.COMMIT_NOT_COMMITTED


def test_real_commit_exception_is_ambiguous_when_recovery_cannot_verify(
    hardening_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SqliteDurableRecordedEventStoreV2(private_root=hardening_root)
    _install_real_commit_exception(
        monkeypatch,
        after_commit=True,
        recovery_available=False,
    )

    with pytest.raises(DurableEventStoreFailure) as caught:
        _exchange(store, validated_event())
    assert caught.value.code is DurableEventStoreFailureCode.COMMIT_AMBIGUOUS


def test_repeated_multi_store_concurrency_preserves_one_append_per_event(
    hardening_root: Path,
) -> None:
    stores = tuple(
        SqliteDurableRecordedEventStoreV2(private_root=hardening_root) for _ in range(8)
    )
    for offset in range(3):
        event = _event(120_200 + offset)

        def exchange_one(
            store: SqliteDurableRecordedEventStoreV2,
        ) -> DurableEventReceiptV2:
            return _exchange(store, event)

        with ThreadPoolExecutor(max_workers=len(stores)) as pool:
            receipts = tuple(pool.map(exchange_one, stores))
        dispositions = tuple(receipt.disposition for receipt in receipts)
        assert dispositions.count(RecordedStoreDisposition.RECORDED_ACCEPTED) == 1
        assert dispositions.count(RecordedStoreDisposition.RECORDED_DUPLICATE) == 7

    connection = sqlite3.connect(_database(hardening_root))
    try:
        assert connection.execute(
            "SELECT COUNT(*) FROM st1201_event_v2"
        ).fetchone() == (3,)
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        connection.close()
