"""Owner-private SQLite, CAS, recovery, and tamper tests for ST-0604 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import os
from pathlib import Path
import shutil
import sqlite3
import stat

import pytest

from raos.adapters.sqlite_source_packet_lifecycle_runtime_v2 import (
    OwnerPrivateSqliteSourcePacketStoreV2,
    SourcePacketSqliteCommitFaultV2,
)
from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    SourcePacketCommandIdV2,
    SourcePacketFailureCodeV2,
    SourcePacketFailureV2,
)
from tests.st0604.runtime_v2_fixtures import (
    ARTICLE_PLAN_ID,
    EDITOR_FINGERPRINT,
    PACKET_ID,
    REVIEW_ASSIGNMENT_ID,
    SITE_ID,
    authorization_fixture_v2,
    source_content_v2,
    source_packet_runtime_v2,
    source_packet_store_v2,
)


def _failure(call: object) -> SourcePacketFailureCodeV2:
    assert callable(call)
    with pytest.raises(SourcePacketFailureV2) as caught:
        call()
    return caught.value.code


def _created_runtime(
    tmp_path: Path,
    *,
    faults: tuple[SourcePacketSqliteCommitFaultV2, ...] = (),
) -> tuple[object, object, OwnerPrivateSqliteSourcePacketStoreV2, object]:
    content = source_content_v2(tmp_path / "evidence")
    now = content.conflict_scan.committed_at + timedelta(minutes=1)
    authorization = authorization_fixture_v2(tmp_path / "authorization", now=now)
    store = source_packet_store_v2(tmp_path / "store", faults=faults)
    runtime = source_packet_runtime_v2(authorization=authorization, store=store)
    return runtime, authorization, store, content


def _create(runtime: object, authorization: object) -> object:
    return runtime.create_packet(
        command_id=SourcePacketCommandIdV2("RECORDED:ST0604:SQLITE:CREATE"),
        packet_id=PACKET_ID,
        site_id=SITE_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        creator_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=2),
    )


def test_database_is_created_only_and_owner_private_with_exact_schema(
    tmp_path: Path,
) -> None:
    _runtime, _authorization, store, _content = _created_runtime(tmp_path)
    assert stat.S_IMODE(store.database_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(store.database_path.parent.stat().st_mode) == 0o700
    connection = sqlite3.connect(store.database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger'"
            )
        }
    finally:
        connection.close()
    assert tables == {
        "source_packet_metadata",
        "source_packet_packet_registry",
        "source_packet_version_registry",
        "source_packet_command_journal",
        "source_packet_lifecycle_journal",
        "source_packet_review_journal",
        "source_packet_lock_journal",
        "source_packet_audit_journal",
    }
    assert len(triggers) == 2 * len(tables)
    assert all(name.endswith(("_no_update", "_no_delete")) for name in triggers)


def test_exact_command_replay_is_idempotent_and_changed_payload_conflicts(
    tmp_path: Path,
) -> None:
    runtime, authorization, store, _content = _created_runtime(tmp_path)
    first = _create(runtime, authorization)
    replay = _create(runtime, authorization)
    assert replay.state == first.state
    assert replay.chain_hash == first.chain_hash
    assert replay.sequence == first.sequence == 1
    assert len(store.audit_snapshot()) == 1
    assert (
        _failure(
            lambda: runtime.create_packet(
                command_id=SourcePacketCommandIdV2("RECORDED:ST0604:SQLITE:CREATE"),
                packet_id=PACKET_ID,
                site_id=SITE_ID,
                article_plan_id=ARTICLE_PLAN_ID,
                review_assignment_id=REVIEW_ASSIGNMENT_ID,
                creator_actor_fingerprint="a" * 64,
                occurred_at=authorization.now - timedelta(seconds=2),
            )
        )
        is SourcePacketFailureCodeV2.COMMAND_CONFLICT
    )


def test_after_commit_fault_recovers_exactly_without_reexecuting(
    tmp_path: Path,
) -> None:
    runtime, authorization, store, _content = _created_runtime(
        tmp_path,
        faults=(SourcePacketSqliteCommitFaultV2.AFTER_COMMIT,),
    )
    result = _create(runtime, authorization)
    assert result.state.aggregate_revision == 1
    assert len(store.audit_snapshot()) == 1
    assert store.load_state(PACKET_ID) == result.state


def test_before_commit_fault_remains_unknown_and_does_not_blind_retry(
    tmp_path: Path,
) -> None:
    runtime, authorization, store, _content = _created_runtime(
        tmp_path,
        faults=(SourcePacketSqliteCommitFaultV2.BEFORE_COMMIT,),
    )
    assert _failure(lambda: _create(runtime, authorization)) is (
        SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN
    )
    assert store.load_state(PACKET_ID) is None
    assert store.audit_snapshot() == ()


def test_two_writers_with_same_expected_revision_have_one_cas_winner(
    tmp_path: Path,
) -> None:
    runtime, authorization, store, content = _created_runtime(tmp_path)
    _create(runtime, authorization)
    runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:SQLITE:VERSION"),
        packet_id=PACKET_ID,
        expected_revision=1,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    peer = OwnerPrivateSqliteSourcePacketStoreV2(
        environment=store_environment(),
        root=store.database_path.parent,
    )
    peer_runtime = source_packet_runtime_v2(authorization=authorization, store=peer)

    def submit(candidate: tuple[object, str]) -> str:
        candidate_runtime, label = candidate
        try:
            candidate_runtime.submit_review(
                command_id=SourcePacketCommandIdV2(f"RECORDED:CAS:{label}"),
                packet_id=PACKET_ID,
                expected_revision=2,
                editor_actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now,
            )
        except SourcePacketFailureV2 as error:
            return error.code.value
        return "COMMITTED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = sorted(pool.map(submit, ((runtime, "A"), (peer_runtime, "B"))))
    assert outcomes == ["COMMITTED", SourcePacketFailureCodeV2.VERSION_CONFLICT.value]
    assert store.load_state(PACKET_ID).aggregate_revision == 3


def store_environment():
    from raos.config.runtime import RuntimeEnvironment

    return RuntimeEnvironment.CI


def test_append_only_trigger_blocks_update_and_delete(tmp_path: Path) -> None:
    runtime, authorization, store, _content = _created_runtime(tmp_path)
    _create(runtime, authorization)
    connection = sqlite3.connect(store.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE source_packet_audit_journal SET event_kind='FORGED' WHERE sequence=1"
            )
        connection.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "DELETE FROM source_packet_command_journal WHERE sequence=1"
            )
    finally:
        connection.close()


def test_missing_trigger_or_tampered_journal_fails_closed(tmp_path: Path) -> None:
    runtime, authorization, store, _content = _created_runtime(tmp_path)
    _create(runtime, authorization)
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute("DROP TRIGGER source_packet_audit_journal_no_update")
        connection.execute(
            "UPDATE source_packet_audit_journal SET actor_fingerprint=? WHERE sequence=1",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    assert _failure(store.audit_snapshot) is SourcePacketFailureCodeV2.TAMPER_DETECTED


def test_same_column_schema_with_weakened_constraints_fails_closed(
    tmp_path: Path,
) -> None:
    _runtime, _authorization, store, _content = _created_runtime(tmp_path)
    connection = sqlite3.connect(store.database_path)
    try:
        metadata = connection.execute(
            "SELECT singleton,schema_version,database_identity,schema_sha256 "
            "FROM source_packet_metadata"
        ).fetchone()
        assert metadata is not None
        connection.executescript(
            """
            DROP TRIGGER source_packet_metadata_no_update;
            DROP TRIGGER source_packet_metadata_no_delete;
            DROP TABLE source_packet_metadata;
            CREATE TABLE source_packet_metadata (
              singleton INTEGER PRIMARY KEY,
              schema_version TEXT NOT NULL,
              database_identity TEXT NOT NULL,
              schema_sha256 TEXT NOT NULL
            ) STRICT;
            CREATE TRIGGER source_packet_metadata_no_update
            BEFORE UPDATE ON source_packet_metadata
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER source_packet_metadata_no_delete
            BEFORE DELETE ON source_packet_metadata
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            """
        )
        connection.execute(
            "INSERT INTO source_packet_metadata VALUES (?,?,?,?)", metadata
        )
        connection.commit()
    finally:
        connection.close()
    assert _failure(store.audit_snapshot) is SourcePacketFailureCodeV2.TAMPER_DETECTED


def test_symlinked_ancestor_and_hardlinked_database_are_rejected(
    tmp_path: Path,
) -> None:
    real = tmp_path / "real"
    real.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(real, target_is_directory=True)
    assert (
        _failure(
            lambda: OwnerPrivateSqliteSourcePacketStoreV2(
                environment=store_environment(),
                root=linked / "private",
            )
        )
        is SourcePacketFailureCodeV2.STORAGE_FAILED
    )

    _runtime, _authorization, store, _content = _created_runtime(tmp_path / "safe")
    os.link(store.database_path, tmp_path / "database-hardlink")
    assert _failure(store.audit_snapshot) is SourcePacketFailureCodeV2.STORAGE_FAILED


def test_overdeep_noncanonical_journal_document_fails_closed(tmp_path: Path) -> None:
    _runtime, _authorization, store, _content = _created_runtime(tmp_path)
    overdeep = '{"x":' * 70 + "0" + "}" * 70
    connection = sqlite3.connect(store.database_path)
    try:
        connection.execute(
            "INSERT INTO source_packet_command_journal VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "RECORDED:HOSTILE:DEEP",
                1,
                "1" * 64,
                str(PACKET_ID),
                "CREATE_PACKET",
                overdeep,
                overdeep,
                "2" * 64,
                "0" * 64,
                "3" * 64,
                "2026-08-25T00:00:00.000000Z",
                "4" * 64,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    assert _failure(store.audit_snapshot) is SourcePacketFailureCodeV2.TAMPER_DETECTED


def test_process_local_prefix_anchor_detects_database_rollback(tmp_path: Path) -> None:
    runtime, authorization, store, content = _created_runtime(tmp_path)
    _create(runtime, authorization)
    snapshot = store.database_path.with_suffix(".snapshot")
    shutil.copy2(store.database_path, snapshot)
    runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:ROLLBACK:VERSION"),
        packet_id=PACKET_ID,
        expected_revision=1,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=authorization.now,
    )
    original_identity = store.database_path.stat().st_ino
    shutil.copyfile(snapshot, store.database_path)
    assert store.database_path.stat().st_ino == original_identity
    assert _failure(lambda: store.load_state(PACKET_ID)) is (
        SourcePacketFailureCodeV2.TAMPER_DETECTED
    )


def test_peer_prefix_becomes_process_local_rollback_floor(tmp_path: Path) -> None:
    runtime, authorization, writer, _content = _created_runtime(tmp_path)
    observer = OwnerPrivateSqliteSourcePacketStoreV2(
        environment=store_environment(),
        root=writer.database_path.parent,
    )
    snapshot = writer.database_path.with_suffix(".empty-snapshot")
    shutil.copy2(writer.database_path, snapshot)
    created = _create(runtime, authorization)
    assert observer.load_state(PACKET_ID) == created.state

    original_identity = writer.database_path.stat().st_ino
    shutil.copyfile(snapshot, writer.database_path)
    assert writer.database_path.stat().st_ino == original_identity
    assert _failure(lambda: observer.load_state(PACKET_ID)) is (
        SourcePacketFailureCodeV2.TAMPER_DETECTED
    )


def test_clean_reopen_revalidates_complete_chain_and_state(tmp_path: Path) -> None:
    runtime, authorization, store, content = _created_runtime(tmp_path)
    created = _create(runtime, authorization)
    versioned = runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:REOPEN:VERSION"),
        packet_id=PACKET_ID,
        expected_revision=1,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=authorization.now,
    )
    reopened = OwnerPrivateSqliteSourcePacketStoreV2(
        environment=store_environment(),
        root=store.database_path.parent,
    )
    assert created.sequence == 1
    assert reopened.load_state(PACKET_ID) == versioned.state
    assert len(reopened.audit_snapshot()) == 2


def test_store_rejects_hostile_mutation_of_nested_command_before_write(
    tmp_path: Path,
) -> None:
    runtime, authorization, store, _content = _created_runtime(tmp_path)
    result = _create(runtime, authorization)
    forged = replace(result.command, actor_fingerprint="f" * 64)
    object.__setattr__(forged, "packet_id", ARTICLE_PLAN_ID)
    assert _failure(lambda: store.execute(forged)) in {
        SourcePacketFailureCodeV2.COMMAND_CONFLICT,
        SourcePacketFailureCodeV2.STATE_CONFLICT,
        SourcePacketFailureCodeV2.TAMPER_DETECTED,
    }
