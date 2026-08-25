"""Exact SQLite schema, append-only guards, and tamper detection."""

from __future__ import annotations

from pathlib import Path
import sqlite3

import pytest

from raos.adapters.sqlite_artifact_registry_runtime_v2 import (
    RecordedSqliteArtifactRegistryFactoryV2,
)
from raos.application.ops.artifact_registry_runtime_v2 import (
    DurableArtifactRegistryServiceV2,
)
from raos.domain.ops.artifact_registry_runtime_v2 import (
    ARTIFACT_REGISTRY_SCHEMA_VERSION_V2,
    ArtifactRegistryCommitV2,
    ArtifactRegistryRuntimeFailureCodeV2,
    ArtifactRegistryRuntimeFailureV2,
)

from runtime_v2_fixtures import (
    BODY_ONE,
    private_root,
    receipt_for,
    request_for,
    service_for,
)


EXPECTED_TABLES = {
    "artifact_registry_metadata_v2",
    "artifact_object_v2",
    "artifact_operation_v2",
}
EXPECTED_TRIGGERS = {
    f"{table}_{operation}"
    for table in EXPECTED_TABLES
    for operation in ("no_update", "no_delete")
}


def _force_update(
    database: Path,
    *,
    table: str,
    statement: str,
    parameters: tuple[object, ...],
) -> None:
    connection = sqlite3.connect(database, isolation_level=None)
    try:
        trigger = f"{table}_no_update"
        row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
            (trigger,),
        ).fetchone()
        assert row is not None and type(row[0]) is str
        trigger_sql = row[0]
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(f"DROP TRIGGER {trigger}")
        connection.execute(statement, parameters)
        connection.execute(trigger_sql)
        connection.execute("COMMIT")
    finally:
        connection.close()


def _registered(
    tmp_path: Path,
) -> tuple[
    DurableArtifactRegistryServiceV2,
    RecordedSqliteArtifactRegistryFactoryV2,
    ArtifactRegistryCommitV2,
]:
    receipt = receipt_for()
    service, factory = service_for(private_root(tmp_path), (receipt, BODY_ONE))
    commit = service.register(request_for(receipt))
    return service, factory, commit


def test_schema_inventory_columns_uniqueness_and_foreign_key_are_exact(
    tmp_path: Path,
) -> None:
    _, factory, _ = _registered(tmp_path)
    connection = sqlite3.connect(factory.database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
            if not row[0].startswith("sqlite_")
        }
        triggers = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger'"
            )
        }
        assert tables == EXPECTED_TABLES
        assert triggers == EXPECTED_TRIGGERS
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            ).fetchall()
            == []
        )
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
            ).fetchall()
            == []
        )
        metadata = connection.execute(
            "SELECT singleton, schema_version, schema_sha256 FROM artifact_registry_metadata_v2"
        ).fetchall()
        assert len(metadata) == 1
        assert metadata[0][0:2] == (1, ARTIFACT_REGISTRY_SCHEMA_VERSION_V2)
        assert len(metadata[0][2]) == 64
        object_columns = [
            row[1]
            for row in connection.execute("PRAGMA table_info('artifact_object_v2')")
        ]
        assert object_columns == [
            "sequence",
            "artifact_id",
            "display_id",
            "source_receipt_id",
            "logical_key",
            "artifact_version",
            "candidate_json",
            "candidate_sha256",
            "content_sha256",
            "byte_size",
            "body",
            "ref_sha256",
            "previous_entry_sha256",
            "entry_sha256",
            "record_sha256",
        ]
        foreign_keys = connection.execute(
            "PRAGMA foreign_key_list('artifact_operation_v2')"
        ).fetchall()
        assert len(foreign_keys) == 1
        assert foreign_keys[0][2:8] == (
            "artifact_object_v2",
            "artifact_id",
            "artifact_id",
            "RESTRICT",
            "RESTRICT",
            "NONE",
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("table", "identity_column"),
    (
        ("artifact_registry_metadata_v2", "singleton"),
        ("artifact_object_v2", "sequence"),
        ("artifact_operation_v2", "operation_id"),
    ),
)
def test_direct_update_and_delete_are_blocked(
    tmp_path: Path, table: str, identity_column: str
) -> None:
    _, factory, _ = _registered(tmp_path)
    connection = sqlite3.connect(factory.database_path)
    try:
        with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0601_V2"):
            connection.execute(
                f"UPDATE {table} SET {identity_column} = {identity_column}"
            )
        with pytest.raises(sqlite3.IntegrityError, match="IMMUTABLE_ST0601_V2"):
            connection.execute(f"DELETE FROM {table}")
    finally:
        connection.close()


def test_body_tamper_is_detected_on_exact_readback(tmp_path: Path) -> None:
    service, factory, commit = _registered(tmp_path)
    _force_update(
        factory.database_path,
        table="artifact_object_v2",
        statement="UPDATE artifact_object_v2 SET body = ? WHERE sequence = 1",
        parameters=(b"tampered",),
    )

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        service.readback(commit.record.artifact_ref)

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED


def test_hash_chain_tamper_is_detected(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    _force_update(
        factory.database_path,
        table="artifact_object_v2",
        statement="UPDATE artifact_object_v2 SET entry_sha256 = ? WHERE sequence = 1",
        parameters=("0" * 64,),
    )

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open().verify_chain()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED


def test_operation_receipt_tamper_is_detected(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    _force_update(
        factory.database_path,
        table="artifact_operation_v2",
        statement=(
            "UPDATE artifact_operation_v2 SET receipt_sha256 = ? WHERE sequence = 1"
        ),
        parameters=("0" * 64,),
    )

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open().verify_chain()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.TAMPER_DETECTED


def test_extra_schema_object_fails_closed(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    connection = sqlite3.connect(factory.database_path)
    try:
        connection.execute("CREATE TABLE unexpected_table(value TEXT)")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT


def test_missing_trigger_fails_closed_without_automatic_repair(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    connection = sqlite3.connect(factory.database_path)
    try:
        connection.execute("DROP TRIGGER artifact_object_v2_no_update")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT
    connection = sqlite3.connect(factory.database_path)
    try:
        assert (
            connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'trigger' AND name = 'artifact_object_v2_no_update'"
            ).fetchone()
            is None
        )
    finally:
        connection.close()


def test_same_name_inert_trigger_is_schema_drift(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    connection = sqlite3.connect(factory.database_path)
    try:
        connection.execute("DROP TRIGGER artifact_object_v2_no_update")
        connection.execute(
            """CREATE TRIGGER artifact_object_v2_no_update
            BEFORE UPDATE ON artifact_object_v2 BEGIN SELECT 1; END"""
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT


def test_metadata_schema_hash_tamper_fails_closed(tmp_path: Path) -> None:
    _, factory, _ = _registered(tmp_path)
    _force_update(
        factory.database_path,
        table="artifact_registry_metadata_v2",
        statement="UPDATE artifact_registry_metadata_v2 SET schema_sha256 = ?",
        parameters=("0" * 64,),
    )

    with pytest.raises(ArtifactRegistryRuntimeFailureV2) as caught:
        factory.open()

    assert caught.value.code is ArtifactRegistryRuntimeFailureCodeV2.SCHEMA_DRIFT
