"""Owner-private SQLite quarantine and deterministic recorded ST-0406 adapters."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tarfile
from threading import Lock, RLock
from typing import Mapping, NoReturn, cast, final
from uuid import UUID
import zipfile

from raos.config.runtime import RuntimeEnvironment
from raos.domain.ops.object_intake import (
    DuplicateStatus,
    IntakeDescriptor,
    IntakePrivacyClass,
    ObjectIntakeKind,
    Sha256Digest,
)
from raos.domain.ops.object_intake_runtime_v2 import (
    ContentInspectionSummaryV2,
    DurableIntakeDescriptorV2,
    DurableIntakeState,
    DurableQuarantineReceiptV2,
    IntakeCommandId,
    IntakeFormat,
    IntakeRuntimePolicyV2,
    MalwareScanReceiptV2,
    ObjectIntakeRuntimeFailure,
    ObjectIntakeRuntimeFailureCode,
    PrivacyClassificationReceiptV2,
    RecordedMalwareVerdict,
    RecordedPrivacyVerdict,
    RecoveredIntakeOutcomeV2,
    RejectedQuarantineReceiptV2,
    fail_intake_runtime,
)


_DATABASE_NAME = "secure-object-intake-runtime-v2.sqlite3"
_APPLICATION_ID = 1_380_400_602
_SCHEMA_VERSION = 2
_GENESIS = "0" * 64
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_DOCUMENT_BYTES = 65_536
_MAX_SCRIPT_ROWS = 10_000
_ALLOWED_ENVIRONMENTS = {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
_EVENT_KINDS = frozenset({"OPEN", "APPEND", "SEAL", "ACCEPT", "REJECT"})
_FINAL_STATES = frozenset(
    {DurableIntakeState.CLEAN_QUARANTINED.value, DurableIntakeState.REJECTED.value}
)


_SCHEMA_TABLE_NAMES = frozenset(
    {
        "st0406_runtime_metadata",
        "st0406_quarantine",
        "st0406_quarantine_event",
        "st0406_intake_command",
        "st0406_intake_audit",
        "st0406_duplicate_index",
        "st0406_intake_result",
    }
)
_SCHEMA_INDEX_TABLES: Mapping[str, str] = {
    "st0406_event_command_version": "st0406_quarantine_event",
    "st0406_command_command_version": "st0406_intake_command",
    "st0406_audit_command_sequence": "st0406_intake_audit",
}
_SCHEMA_IMPLICIT_INDEX_TABLES: Mapping[str, str] = {
    "sqlite_autoindex_st0406_duplicate_index_1": "st0406_duplicate_index",
    "sqlite_autoindex_st0406_duplicate_index_2": "st0406_duplicate_index",
    "sqlite_autoindex_st0406_duplicate_index_3": "st0406_duplicate_index",
    "sqlite_autoindex_st0406_intake_audit_1": "st0406_intake_audit",
    "sqlite_autoindex_st0406_intake_audit_2": "st0406_intake_audit",
    "sqlite_autoindex_st0406_intake_command_1": "st0406_intake_command",
    "sqlite_autoindex_st0406_intake_command_2": "st0406_intake_command",
    "sqlite_autoindex_st0406_intake_result_1": "st0406_intake_result",
    "sqlite_autoindex_st0406_quarantine_1": "st0406_quarantine",
    "sqlite_autoindex_st0406_quarantine_2": "st0406_quarantine",
    "sqlite_autoindex_st0406_quarantine_3": "st0406_quarantine",
    "sqlite_autoindex_st0406_quarantine_event_1": "st0406_quarantine_event",
}
_SCHEMA_TRIGGER_TABLES: Mapping[str, str] = {
    "st0406_metadata_no_delete": "st0406_runtime_metadata",
    "st0406_metadata_guard_update": "st0406_runtime_metadata",
    "st0406_quarantine_no_delete": "st0406_quarantine",
    "st0406_event_no_update": "st0406_quarantine_event",
    "st0406_event_no_delete": "st0406_quarantine_event",
    "st0406_command_no_update": "st0406_intake_command",
    "st0406_command_no_delete": "st0406_intake_command",
    "st0406_audit_no_update": "st0406_intake_audit",
    "st0406_audit_no_delete": "st0406_intake_audit",
    "st0406_duplicate_no_update": "st0406_duplicate_index",
    "st0406_duplicate_no_delete": "st0406_duplicate_index",
    "st0406_result_no_update": "st0406_intake_result",
    "st0406_result_no_delete": "st0406_intake_result",
}

_SCHEMA_OBJECTS: Mapping[str, str] = {
    "st0406_runtime_metadata": """
        CREATE TABLE st0406_runtime_metadata(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1),
          schema_version INTEGER NOT NULL CHECK(schema_version=2),
          schema_binding TEXT NOT NULL CHECK(length(schema_binding)=64 AND schema_binding NOT GLOB '*[^0-9a-f]*'),
          event_count INTEGER NOT NULL CHECK(event_count>=0),
          event_head TEXT NOT NULL CHECK(length(event_head)=64 AND event_head NOT GLOB '*[^0-9a-f]*'),
          command_count INTEGER NOT NULL CHECK(command_count>=0),
          command_head TEXT NOT NULL CHECK(length(command_head)=64 AND command_head NOT GLOB '*[^0-9a-f]*'),
          audit_count INTEGER NOT NULL CHECK(audit_count>=0),
          audit_head TEXT NOT NULL CHECK(length(audit_head)=64 AND audit_head NOT GLOB '*[^0-9a-f]*'),
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_quarantine": """
        CREATE TABLE st0406_quarantine(
          command_id TEXT PRIMARY KEY CHECK(length(command_id) BETWEEN 1 AND 128),
          request_digest TEXT NOT NULL CHECK(length(request_digest)=64 AND request_digest NOT GLOB '*[^0-9a-f]*'),
          descriptor_digest TEXT NOT NULL CHECK(length(descriptor_digest)=64 AND descriptor_digest NOT GLOB '*[^0-9a-f]*'),
          authorization_digest TEXT NOT NULL CHECK(length(authorization_digest)=64 AND authorization_digest NOT GLOB '*[^0-9a-f]*'),
          intake_id TEXT NOT NULL UNIQUE,
          quarantine_id TEXT NOT NULL UNIQUE,
          site_id TEXT NOT NULL,
          authorization_resource_id TEXT NOT NULL,
          kind TEXT NOT NULL,
          leaf_name TEXT NOT NULL,
          media_type TEXT NOT NULL,
          declared_size INTEGER NOT NULL CHECK(declared_size>0),
          declared_sha256 TEXT NOT NULL CHECK(length(declared_sha256)=64 AND declared_sha256 NOT GLOB '*[^0-9a-f]*'),
          privacy_class TEXT NOT NULL CHECK(privacy_class IN ('SYNTHETIC','APPROVED_ANONYMIZED')),
          state TEXT NOT NULL CHECK(state IN ('OPEN','SEALED','CLEAN_QUARANTINED','REJECTED')),
          version INTEGER NOT NULL CHECK(version>0),
          received_bytes INTEGER NOT NULL CHECK(received_bytes>=0),
          chunk_count INTEGER NOT NULL CHECK(chunk_count>=0),
          content BLOB NOT NULL,
          sealed_sha256 TEXT CHECK(sealed_sha256 IS NULL OR (length(sealed_sha256)=64 AND sealed_sha256 NOT GLOB '*[^0-9a-f]*')),
          failure_code TEXT,
          result_document TEXT,
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_quarantine_event": """
        CREATE TABLE st0406_quarantine_event(
          sequence INTEGER PRIMARY KEY,
          command_id TEXT NOT NULL REFERENCES st0406_quarantine(command_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
          version INTEGER NOT NULL CHECK(version>0),
          event_kind TEXT NOT NULL CHECK(event_kind IN ('OPEN','APPEND','SEAL','ACCEPT','REJECT')),
          event_document TEXT NOT NULL,
          previous_digest TEXT NOT NULL CHECK(length(previous_digest)=64 AND previous_digest NOT GLOB '*[^0-9a-f]*'),
          digest TEXT NOT NULL UNIQUE CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'),
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_intake_command": """
        CREATE TABLE st0406_intake_command(
          sequence INTEGER PRIMARY KEY CHECK(sequence>0),
          lifecycle_sequence INTEGER NOT NULL UNIQUE REFERENCES st0406_quarantine_event(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT,
          command_id TEXT NOT NULL REFERENCES st0406_quarantine(command_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
          version INTEGER NOT NULL CHECK(version>0),
          operation TEXT NOT NULL CHECK(operation IN ('OPEN','APPEND','SEAL','ACCEPT','REJECT')),
          intent_document TEXT NOT NULL,
          result_document TEXT NOT NULL,
          previous_digest TEXT NOT NULL CHECK(length(previous_digest)=64 AND previous_digest NOT GLOB '*[^0-9a-f]*'),
          digest TEXT NOT NULL UNIQUE CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'),
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_intake_audit": """
        CREATE TABLE st0406_intake_audit(
          sequence INTEGER PRIMARY KEY CHECK(sequence>0),
          command_sequence INTEGER NOT NULL UNIQUE REFERENCES st0406_intake_command(sequence) ON UPDATE RESTRICT ON DELETE RESTRICT,
          command_id TEXT NOT NULL REFERENCES st0406_quarantine(command_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
          action TEXT NOT NULL,
          outcome TEXT NOT NULL CHECK(outcome='RECORDED'),
          binding_digest TEXT NOT NULL CHECK(length(binding_digest)=64 AND binding_digest NOT GLOB '*[^0-9a-f]*'),
          previous_digest TEXT NOT NULL CHECK(length(previous_digest)=64 AND previous_digest NOT GLOB '*[^0-9a-f]*'),
          digest TEXT NOT NULL UNIQUE CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'),
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_duplicate_index": """
        CREATE TABLE st0406_duplicate_index(
          sha256 TEXT PRIMARY KEY,
          intake_id TEXT NOT NULL UNIQUE,
          command_id TEXT NOT NULL UNIQUE REFERENCES st0406_quarantine(command_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_intake_result": """
        CREATE TABLE st0406_intake_result(
          command_id TEXT PRIMARY KEY REFERENCES st0406_quarantine(command_id) ON UPDATE RESTRICT ON DELETE RESTRICT,
          request_digest TEXT NOT NULL CHECK(length(request_digest)=64 AND request_digest NOT GLOB '*[^0-9a-f]*'),
          descriptor_digest TEXT NOT NULL CHECK(length(descriptor_digest)=64 AND descriptor_digest NOT GLOB '*[^0-9a-f]*'),
          authorization_digest TEXT NOT NULL CHECK(length(authorization_digest)=64 AND authorization_digest NOT GLOB '*[^0-9a-f]*'),
          outcome TEXT NOT NULL CHECK(outcome IN ('CLEAN_QUARANTINED','REJECTED')),
          document TEXT NOT NULL,
          digest TEXT NOT NULL CHECK(length(digest)=64 AND digest NOT GLOB '*[^0-9a-f]*'),
          record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64 AND record_sha256 NOT GLOB '*[^0-9a-f]*')
        ) STRICT
    """,
    "st0406_event_command_version": """
        CREATE UNIQUE INDEX st0406_event_command_version
        ON st0406_quarantine_event(command_id,version)
    """,
    "st0406_command_command_version": """
        CREATE UNIQUE INDEX st0406_command_command_version
        ON st0406_intake_command(command_id,version)
    """,
    "st0406_audit_command_sequence": """
        CREATE UNIQUE INDEX st0406_audit_command_sequence
        ON st0406_intake_audit(command_id,command_sequence)
    """,
    "st0406_metadata_no_delete": """
        CREATE TRIGGER st0406_metadata_no_delete
        BEFORE DELETE ON st0406_runtime_metadata
        BEGIN SELECT RAISE(ABORT,'ST0406_METADATA_REQUIRED'); END
    """,
    "st0406_metadata_guard_update": """
        CREATE TRIGGER st0406_metadata_guard_update
        BEFORE UPDATE ON st0406_runtime_metadata
        WHEN NEW.singleton!=OLD.singleton
          OR NEW.schema_version!=OLD.schema_version
          OR NEW.schema_binding!=OLD.schema_binding
          OR NEW.event_count!=OLD.event_count+1
          OR NEW.command_count!=OLD.command_count+1
          OR NEW.audit_count!=OLD.audit_count+1
          OR NEW.event_head=OLD.event_head
          OR NEW.command_head=OLD.command_head
          OR NEW.audit_head=OLD.audit_head
          OR NEW.record_sha256=OLD.record_sha256
        BEGIN SELECT RAISE(ABORT,'ST0406_METADATA_TRANSITION_INVALID'); END
    """,
    "st0406_quarantine_no_delete": """
        CREATE TRIGGER st0406_quarantine_no_delete
        BEFORE DELETE ON st0406_quarantine
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_event_no_update": """
        CREATE TRIGGER st0406_event_no_update
        BEFORE UPDATE ON st0406_quarantine_event
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_event_no_delete": """
        CREATE TRIGGER st0406_event_no_delete
        BEFORE DELETE ON st0406_quarantine_event
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_command_no_update": """
        CREATE TRIGGER st0406_command_no_update
        BEFORE UPDATE ON st0406_intake_command
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_command_no_delete": """
        CREATE TRIGGER st0406_command_no_delete
        BEFORE DELETE ON st0406_intake_command
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_audit_no_update": """
        CREATE TRIGGER st0406_audit_no_update
        BEFORE UPDATE ON st0406_intake_audit
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_audit_no_delete": """
        CREATE TRIGGER st0406_audit_no_delete
        BEFORE DELETE ON st0406_intake_audit
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_duplicate_no_update": """
        CREATE TRIGGER st0406_duplicate_no_update
        BEFORE UPDATE ON st0406_duplicate_index
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_duplicate_no_delete": """
        CREATE TRIGGER st0406_duplicate_no_delete
        BEFORE DELETE ON st0406_duplicate_index
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_result_no_update": """
        CREATE TRIGGER st0406_result_no_update
        BEFORE UPDATE ON st0406_intake_result
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
    "st0406_result_no_delete": """
        CREATE TRIGGER st0406_result_no_delete
        BEFORE DELETE ON st0406_intake_result
        BEGIN SELECT RAISE(ABORT,'ST0406_APPEND_ONLY'); END
    """,
}

_SCHEMA_BINDING = hashlib.sha256(
    json.dumps(
        dict(sorted(_SCHEMA_OBJECTS.items())),
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
).hexdigest()
_SCHEMA_INITIALIZATION_LOCK = Lock()


@dataclass(frozen=True, slots=True)
class _IntegrityState:
    count: int
    event_head: str
    command_head: str
    audit_head: str


@dataclass(slots=True)
class _ProcessAnchor:
    database_identity: tuple[int, int]
    root_identity: tuple[int, int]
    state: _IntegrityState
    lock: RLock


@dataclass(frozen=True, slots=True)
class _LifecycleRecord:
    sequence: int
    version: int
    kind: str
    document: dict[str, object]
    digest: str


_PROCESS_REGISTRY_LOCK = RLock()
_PROCESS_ANCHORS: dict[str, _ProcessAnchor] = {}


def _fail(code: ObjectIntakeRuntimeFailureCode) -> NoReturn:
    fail_intake_runtime(code)


def _recorded_environment(value: object) -> RuntimeEnvironment:
    if type(value) is not RuntimeEnvironment or value not in _ALLOWED_ENVIRONMENTS:
        _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
    return value


def _sha(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _text(value: object, *, maximum: int = 256) -> str:
    if type(value) is not str or not value or len(value) > maximum:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _integer(value: object, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum or value > (1 << 63) - 1:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return value


def _json_bytes(value: object) -> bytes:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
    except TypeError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if len(encoded) > _MAX_DOCUMENT_BYTES:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return encoded


def _digest_document(value: object) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _row_digest(values: tuple[object, ...]) -> str:
    return _digest_document({"schema": "ST0406_ROW_V2", "values": values})


def _document(value: object) -> dict[str, object]:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > _MAX_DOCUMENT_BYTES
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        parsed: object = json.loads(value)
    except json.JSONDecodeError, UnicodeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if type(parsed) is not dict:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    raw = cast(dict[object, object], parsed)
    if any(type(key) is not str for key in raw):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    document = {cast(str, key): item for key, item in raw.items()}
    if _json_bytes(document).decode("ascii") != value:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return document


def _exact_mapping(value: object, keys: frozenset[str]) -> dict[str, object]:
    if type(value) is not dict:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    raw = cast(dict[object, object], value)
    if (
        any(type(key) is not str for key in raw)
        or frozenset(cast(str, key) for key in raw) != keys
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return {cast(str, key): item for key, item in raw.items()}


def _sql_normalized(value: str) -> str:
    return (
        " ".join(value.split()).replace(" ,", ",").replace("( ", "(").replace(" )", ")")
    )


def _schema_is_exact(connection: sqlite3.Connection) -> bool:
    rows = connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_schema "
        "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%' "
        "AND sql IS NOT NULL ORDER BY type,name"
    ).fetchall()
    observed = {
        str(name): (str(kind), str(table), _sql_normalized(str(sql)))
        for kind, name, table, sql in rows
    }
    expected: dict[str, tuple[str, str, str]] = {}
    for name in _SCHEMA_TABLE_NAMES:
        expected[name] = ("table", name, _sql_normalized(_SCHEMA_OBJECTS[name]))
    for name, table in _SCHEMA_INDEX_TABLES.items():
        expected[name] = ("index", table, _sql_normalized(_SCHEMA_OBJECTS[name]))
    for name, table in _SCHEMA_TRIGGER_TABLES.items():
        expected[name] = ("trigger", table, _sql_normalized(_SCHEMA_OBJECTS[name]))
    version = connection.execute("PRAGMA user_version").fetchone()
    application = connection.execute("PRAGMA application_id").fetchone()
    strict_rows = connection.execute(
        "SELECT name,strict FROM pragma_table_list "
        "WHERE schema='main' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    implicit_indexes = connection.execute(
        "SELECT name,tbl_name FROM sqlite_schema "
        "WHERE type='index' AND sql IS NULL ORDER BY name"
    ).fetchall()
    return (
        observed == expected
        and version is not None
        and tuple(version) == (_SCHEMA_VERSION,)
        and application is not None
        and tuple(application) == (_APPLICATION_ID,)
        and tuple((str(name), strict) for name, strict in strict_rows)
        == tuple((name, 1) for name in sorted(_SCHEMA_TABLE_NAMES))
        and tuple((str(name), str(table)) for name, table in implicit_indexes)
        == tuple(sorted(_SCHEMA_IMPLICIT_INDEX_TABLES.items()))
        and tuple(connection.execute("PRAGMA foreign_keys").fetchone()) == (1,)
        and tuple(connection.execute("PRAGMA trusted_schema").fetchone()) == (0,)
        and tuple(connection.execute("PRAGMA journal_mode").fetchone()) == ("delete",)
        and tuple(connection.execute("PRAGMA synchronous").fetchone()) == (2,)
        and tuple(connection.execute("PRAGMA secure_delete").fetchone()) == (1,)
    )


def _metadata_values(
    *,
    event_count: int,
    event_head: str,
    command_count: int,
    command_head: str,
    audit_count: int,
    audit_head: str,
) -> tuple[object, ...]:
    return (
        1,
        _SCHEMA_VERSION,
        _SCHEMA_BINDING,
        event_count,
        event_head,
        command_count,
        command_head,
        audit_count,
        audit_head,
    )


def _event_digest(
    *,
    sequence: int,
    command_id: str,
    version: int,
    event_kind: str,
    event_document: str,
    previous_digest: str,
) -> str:
    return _digest_document(
        {
            "schema": "ST0406_EVENT_V2",
            "sequence": sequence,
            "command_id": command_id,
            "version": version,
            "event_kind": event_kind,
            "event_document_sha256": hashlib.sha256(
                event_document.encode("ascii")
            ).hexdigest(),
            "previous_digest": previous_digest,
        }
    )


def _command_result_document(event_digest: str) -> str:
    return _json_bytes(
        {
            "schema": "ST0406_COMMAND_RESULT_V2",
            "lifecycle_digest": event_digest,
        }
    ).decode("ascii")


def _command_digest(
    *,
    sequence: int,
    lifecycle_sequence: int,
    command_id: str,
    version: int,
    operation: str,
    intent_document: str,
    result_document: str,
    previous_digest: str,
) -> str:
    return _digest_document(
        {
            "schema": "ST0406_COMMAND_V2",
            "sequence": sequence,
            "lifecycle_sequence": lifecycle_sequence,
            "command_id": command_id,
            "version": version,
            "operation": operation,
            "intent_sha256": hashlib.sha256(
                intent_document.encode("ascii")
            ).hexdigest(),
            "result_sha256": hashlib.sha256(
                result_document.encode("ascii")
            ).hexdigest(),
            "previous_digest": previous_digest,
        }
    )


def _audit_digest(
    *,
    sequence: int,
    command_sequence: int,
    command_id: str,
    action: str,
    outcome: str,
    binding_digest: str,
    previous_digest: str,
) -> str:
    return _digest_document(
        {
            "schema": "ST0406_AUDIT_V2",
            "sequence": sequence,
            "command_sequence": command_sequence,
            "command_id": command_id,
            "action": action,
            "outcome": outcome,
            "binding_digest": binding_digest,
            "previous_digest": previous_digest,
        }
    )


def _quarantine_id(command_id: IntakeCommandId) -> UUID:
    raw = bytearray(hashlib.sha256(command_id.value.encode("ascii")).digest()[:16])
    raw[6] = (raw[6] & 0x0F) | 0x40
    raw[8] = (raw[8] & 0x3F) | 0x80
    value = UUID(bytes=bytes(raw))
    if value.int == 0:
        _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
    return value


def _descriptor_document(descriptor: DurableIntakeDescriptorV2) -> dict[str, object]:
    base = descriptor.descriptor
    return {
        "intake_id": str(base.intake_id),
        "site_id": str(base.site_id),
        "authorization_resource_id": str(descriptor.authorization_resource_id),
        "kind": base.kind.value,
        "leaf_name": base.leaf_name.value,
        "media_type": base.media_type.value,
        "declared_size": base.declared_size,
        "declared_sha256": base.declared_sha256.value,
        "privacy_class": base.privacy_class.value,
    }


def _inspection_document(value: ContentInspectionSummaryV2) -> dict[str, object]:
    return {
        "format": value.format.value,
        "archive_entry_count": value.archive_entry_count,
        "archive_uncompressed_bytes": value.archive_uncompressed_bytes,
        "csv_row_count": value.csv_row_count,
        "csv_column_count": value.csv_column_count,
        "csv_max_cell_bytes": value.csv_max_cell_bytes,
        "formula_prefix_safe": value.formula_prefix_safe,
    }


def _inspection_from_document(value: object) -> ContentInspectionSummaryV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "format",
                "archive_entry_count",
                "archive_uncompressed_bytes",
                "csv_row_count",
                "csv_column_count",
                "csv_max_cell_bytes",
                "formula_prefix_safe",
            }
        ),
    )
    try:
        format_value = IntakeFormat(_text(row["format"], maximum=16))
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    formula = row["formula_prefix_safe"]
    if type(formula) is not bool:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return ContentInspectionSummaryV2(
        format=format_value,
        archive_entry_count=_integer(row["archive_entry_count"]),
        archive_uncompressed_bytes=_integer(row["archive_uncompressed_bytes"]),
        csv_row_count=_integer(row["csv_row_count"]),
        csv_column_count=_integer(row["csv_column_count"]),
        csv_max_cell_bytes=_integer(row["csv_max_cell_bytes"]),
        formula_prefix_safe=formula,
    )


def _privacy_document(value: PrivacyClassificationReceiptV2) -> dict[str, object]:
    return {
        "verdict": value.verdict.value,
        "classified_as": None
        if value.classified_as is None
        else value.classified_as.value,
        "classifier_revision": value.classifier_revision,
    }


def _privacy_from_document(value: object) -> PrivacyClassificationReceiptV2:
    row = _exact_mapping(
        value, frozenset({"verdict", "classified_as", "classifier_revision"})
    )
    try:
        verdict = RecordedPrivacyVerdict(_text(row["verdict"], maximum=16))
        raw_class = row["classified_as"]
        classified = (
            None
            if raw_class is None
            else IntakePrivacyClass(_text(raw_class, maximum=32))
        )
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return PrivacyClassificationReceiptV2(
        verdict=verdict,
        classified_as=classified,
        classifier_revision=_text(row["classifier_revision"]),
    )


def _malware_document(value: MalwareScanReceiptV2) -> dict[str, object]:
    return {"verdict": value.verdict.value, "engine_revision": value.engine_revision}


def _malware_from_document(value: object) -> MalwareScanReceiptV2:
    row = _exact_mapping(value, frozenset({"verdict", "engine_revision"}))
    try:
        verdict = RecordedMalwareVerdict(_text(row["verdict"], maximum=16))
    except ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return MalwareScanReceiptV2(
        verdict=verdict, engine_revision=_text(row["engine_revision"])
    )


def _accepted_document(receipt: DurableQuarantineReceiptV2) -> dict[str, object]:
    return {
        "schema": "ST0406_ACCEPTED_RECEIPT_V2",
        "command_id": receipt.command_id.value,
        "intake_id": str(receipt.intake_id),
        "quarantine_id": str(receipt.quarantine_id),
        "site_id": str(receipt.site_id),
        "authorization_resource_id": str(receipt.authorization_resource_id),
        "kind": receipt.kind.value,
        "state": receipt.state.value,
        "version": receipt.version,
        "received_bytes": receipt.received_bytes,
        "chunk_count": receipt.chunk_count,
        "sha256": receipt.sha256.value,
        "duplicate_status": receipt.duplicate_status.value,
        "duplicate_of_intake_id": (
            None
            if receipt.duplicate_of_intake_id is None
            else str(receipt.duplicate_of_intake_id)
        ),
        "inspection": _inspection_document(receipt.inspection),
        "privacy": _privacy_document(receipt.privacy),
        "malware": _malware_document(receipt.malware),
        "journal_head_sha256": receipt.journal_head_sha256,
    }


def _accepted_from_document(value: object) -> DurableQuarantineReceiptV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "schema",
                "command_id",
                "intake_id",
                "quarantine_id",
                "site_id",
                "authorization_resource_id",
                "kind",
                "state",
                "version",
                "received_bytes",
                "chunk_count",
                "sha256",
                "duplicate_status",
                "duplicate_of_intake_id",
                "inspection",
                "privacy",
                "malware",
                "journal_head_sha256",
            }
        ),
    )
    if row["schema"] != "ST0406_ACCEPTED_RECEIPT_V2":
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        intake_id = UUID(_text(row["intake_id"], maximum=36))
        quarantine_id = UUID(_text(row["quarantine_id"], maximum=36))
        site_id = UUID(_text(row["site_id"], maximum=36))
        authorization_resource_id = UUID(
            _text(row["authorization_resource_id"], maximum=36)
        )
        kind = ObjectIntakeKind(_text(row["kind"], maximum=32))
        state = DurableIntakeState(_text(row["state"], maximum=32))
        duplicate_status = DuplicateStatus(_text(row["duplicate_status"], maximum=32))
        raw_duplicate = row["duplicate_of_intake_id"]
        duplicate_id = (
            None if raw_duplicate is None else UUID(_text(raw_duplicate, maximum=36))
        )
    except ValueError, AttributeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return DurableQuarantineReceiptV2(
        command_id=IntakeCommandId(_text(row["command_id"])),
        intake_id=intake_id,
        quarantine_id=quarantine_id,
        site_id=site_id,
        authorization_resource_id=authorization_resource_id,
        kind=kind,
        state=state,
        version=_integer(row["version"], minimum=1),
        received_bytes=_integer(row["received_bytes"], minimum=1),
        chunk_count=_integer(row["chunk_count"], minimum=1),
        sha256=Sha256Digest(_sha(row["sha256"])),
        duplicate_status=duplicate_status,
        duplicate_of_intake_id=duplicate_id,
        inspection=_inspection_from_document(row["inspection"]),
        privacy=_privacy_from_document(row["privacy"]),
        malware=_malware_from_document(row["malware"]),
        journal_head_sha256=_sha(row["journal_head_sha256"]),
    )


def _rejected_document(receipt: RejectedQuarantineReceiptV2) -> dict[str, object]:
    return {
        "schema": "ST0406_REJECTED_RECEIPT_V2",
        "command_id": receipt.command_id.value,
        "intake_id": str(receipt.intake_id),
        "quarantine_id": str(receipt.quarantine_id),
        "state": receipt.state.value,
        "version": receipt.version,
        "failure_code": receipt.failure_code.value,
        "journal_head_sha256": receipt.journal_head_sha256,
    }


def _rejected_from_document(value: object) -> RejectedQuarantineReceiptV2:
    row = _exact_mapping(
        value,
        frozenset(
            {
                "schema",
                "command_id",
                "intake_id",
                "quarantine_id",
                "state",
                "version",
                "failure_code",
                "journal_head_sha256",
            }
        ),
    )
    if row["schema"] != "ST0406_REJECTED_RECEIPT_V2":
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    try:
        return RejectedQuarantineReceiptV2(
            command_id=IntakeCommandId(_text(row["command_id"])),
            intake_id=UUID(_text(row["intake_id"], maximum=36)),
            quarantine_id=UUID(_text(row["quarantine_id"], maximum=36)),
            state=DurableIntakeState(_text(row["state"], maximum=32)),
            version=_integer(row["version"], minimum=1),
            failure_code=ObjectIntakeRuntimeFailureCode(
                _text(row["failure_code"], maximum=32)
            ),
            journal_head_sha256=_sha(row["journal_head_sha256"]),
        )
    except ValueError, AttributeError:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)


def _outcome_from_result_row(row: tuple[object, ...]) -> RecoveredIntakeOutcomeV2:
    if len(row) != 8:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    values = row[:-1]
    if _sha(row[-1]) != _row_digest(values):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    (
        command_id,
        request_digest,
        descriptor_digest,
        authorization_digest,
        outcome,
        document,
        result_digest,
    ) = values
    raw_document = _text(document, maximum=_MAX_DOCUMENT_BYTES)
    if _sha(result_digest) != hashlib.sha256(raw_document.encode("ascii")).hexdigest():
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    parsed = _document(raw_document)
    accepted: DurableQuarantineReceiptV2 | None = None
    rejected: RejectedQuarantineReceiptV2 | None = None
    if outcome == DurableIntakeState.CLEAN_QUARANTINED.value:
        accepted = _accepted_from_document(parsed)
    elif outcome == DurableIntakeState.REJECTED.value:
        rejected = _rejected_from_document(parsed)
    else:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if (accepted is not None and accepted.command_id.value != command_id) or (
        rejected is not None and rejected.command_id.value != command_id
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return RecoveredIntakeOutcomeV2(
        request_digest=_sha(request_digest),
        descriptor_digest=_sha(descriptor_digest),
        authorization_digest=_sha(authorization_digest),
        accepted=accepted,
        rejected=rejected,
    )


def _quarantine_values(row: sqlite3.Row) -> tuple[object, ...]:
    content = row["content"]
    if type(content) is not bytes:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    return (
        row["command_id"],
        row["request_digest"],
        row["descriptor_digest"],
        row["authorization_digest"],
        row["intake_id"],
        row["quarantine_id"],
        row["site_id"],
        row["authorization_resource_id"],
        row["kind"],
        row["leaf_name"],
        row["media_type"],
        row["declared_size"],
        row["declared_sha256"],
        row["privacy_class"],
        row["state"],
        row["version"],
        row["received_bytes"],
        row["chunk_count"],
        hashlib.sha256(content).hexdigest(),
        row["sealed_sha256"],
        row["failure_code"],
        row["result_document"],
    )


def _validate_lifecycle_semantics(
    *,
    command_id: str,
    projection: sqlite3.Row,
    records: tuple[_LifecycleRecord, ...],
    result: RecoveredIntakeOutcomeV2 | None,
    allow_in_progress: bool,
) -> None:
    if not records or records[0].kind != "OPEN":
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    content = projection["content"]
    if type(content) is not bytes:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    received = 0
    chunk_count = 0
    sealed = False
    final_kind: str | None = None
    for record in records:
        if record.kind == "OPEN":
            document = _exact_mapping(
                record.document,
                frozenset({"schema", "descriptor_digest", "authorization_digest"}),
            )
            if (
                record.version != 1
                or document["schema"] != "ST0406_OPEN_V2"
                or _sha(document["descriptor_digest"])
                != projection["descriptor_digest"]
                or _sha(document["authorization_digest"])
                != projection["authorization_digest"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            continue
        if final_kind is not None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        if record.kind == "APPEND":
            document = _exact_mapping(
                record.document,
                frozenset({"schema", "chunk_bytes", "chunk_sha256", "received_bytes"}),
            )
            chunk_bytes = _integer(document["chunk_bytes"], minimum=1)
            next_received = received + chunk_bytes
            if (
                sealed
                or document["schema"] != "ST0406_APPEND_V2"
                or next_received > len(content)
                or _sha(document["chunk_sha256"])
                != hashlib.sha256(content[received:next_received]).hexdigest()
                or _integer(document["received_bytes"], minimum=1) != next_received
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            received = next_received
            chunk_count += 1
            continue
        if record.kind == "SEAL":
            document = _exact_mapping(
                record.document,
                frozenset({"schema", "received_bytes", "chunk_count", "sha256"}),
            )
            if (
                sealed
                or document["schema"] != "ST0406_SEAL_V2"
                or _integer(document["received_bytes"], minimum=1) != received
                or _integer(document["chunk_count"], minimum=1) != chunk_count
                or _sha(document["sha256"]) != hashlib.sha256(content).hexdigest()
                or received != len(content)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            sealed = True
            continue
        if record.kind == "ACCEPT":
            document = _exact_mapping(
                record.document,
                frozenset(
                    {
                        "schema",
                        "inspection_sha256",
                        "privacy_sha256",
                        "malware_sha256",
                        "duplicate_status",
                    }
                ),
            )
            accepted = None if result is None else result.accepted
            if (
                not sealed
                or accepted is None
                or document["schema"] != "ST0406_ACCEPT_V2"
                or _sha(document["inspection_sha256"])
                != _digest_document(_inspection_document(accepted.inspection))
                or _sha(document["privacy_sha256"])
                != _digest_document(_privacy_document(accepted.privacy))
                or _sha(document["malware_sha256"])
                != _digest_document(_malware_document(accepted.malware))
                or _text(document["duplicate_status"], maximum=32)
                != accepted.duplicate_status.value
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            final_kind = "ACCEPT"
            continue
        if record.kind == "REJECT":
            document = _exact_mapping(
                record.document,
                frozenset({"schema", "failure_code", "received_bytes"}),
            )
            rejected = None if result is None else result.rejected
            if (
                rejected is None
                or document["schema"] != "ST0406_REJECT_V2"
                or _text(document["failure_code"], maximum=32)
                != rejected.failure_code.value
                or _integer(document["received_bytes"]) != received
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            final_kind = "REJECT"
            continue
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if (
        received != projection["received_bytes"]
        or chunk_count != projection["chunk_count"]
        or records[-1].version != projection["version"]
    ):
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    state = DurableIntakeState(_text(projection["state"], maximum=32))
    if state is DurableIntakeState.CLEAN_QUARANTINED:
        if final_kind != "ACCEPT" or result is None or result.accepted is None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    elif state is DurableIntakeState.REJECTED:
        if final_kind != "REJECT" or result is None or result.rejected is None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    elif not allow_in_progress or final_kind is not None:
        _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
    if result is not None:
        receipt = result.accepted or result.rejected
        if (
            receipt is None
            or receipt.command_id.value != command_id
            or receipt.journal_head_sha256 != records[-1].digest
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)


@final
class RecordedMalwareScannerV2:
    """Digest-scripted scanner; it cannot contact or execute a scanner engine."""

    def __init__(
        self, scripts: tuple[tuple[Sha256Digest, MalwareScanReceiptV2], ...]
    ) -> None:
        if (
            type(scripts) is not tuple
            or not scripts
            or len(scripts) > _MAX_SCRIPT_ROWS
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not MalwareScanReceiptV2
                for row in scripts
            )
            or len({row[0] for row in scripts}) != len(scripts)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._scripts = scripts

    @property
    def action_count(self) -> int:
        return 0

    def scan(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> MalwareScanReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED)
        for expected, receipt in self._scripts:
            if expected == sha256:
                return receipt
        _fail(ObjectIntakeRuntimeFailureCode.MALWARE_REJECTED)


@final
class DisabledMalwareScannerV2:
    @property
    def action_count(self) -> int:
        return 0

    def scan(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> MalwareScanReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.MALWARE_DISABLED)
        return MalwareScanReceiptV2(
            verdict=RecordedMalwareVerdict.UNAVAILABLE,
            engine_revision="DISABLED",
        )


@final
class RecordedPrivacyClassifierV2:
    def __init__(
        self,
        scripts: tuple[tuple[Sha256Digest, PrivacyClassificationReceiptV2], ...],
    ) -> None:
        if (
            type(scripts) is not tuple
            or not scripts
            or len(scripts) > _MAX_SCRIPT_ROWS
            or any(
                type(row) is not tuple
                or len(row) != 2
                or type(row[0]) is not Sha256Digest
                or type(row[1]) is not PrivacyClassificationReceiptV2
                for row in scripts
            )
            or len({row[0] for row in scripts}) != len(scripts)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._scripts = scripts

    @property
    def action_count(self) -> int:
        return 0

    def classify(
        self, *, descriptor: IntakeDescriptor, sha256: Sha256Digest
    ) -> PrivacyClassificationReceiptV2:
        if type(descriptor) is not IntakeDescriptor or type(sha256) is not Sha256Digest:
            _fail(ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED)
        for expected, receipt in self._scripts:
            if expected == sha256:
                return receipt
        _fail(ObjectIntakeRuntimeFailureCode.PRIVACY_REJECTED)


def _safe_archive_name(name: str) -> bool:
    if not name or "\x00" in name or "\\" in name or name.startswith(("/", "~")):
        return False
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return False
    return not (len(path.parts[0]) >= 2 and path.parts[0][1] == ":")


def _nested_archive(name: str, prefix: bytes) -> bool:
    lowered = name.lower()
    suffixes = (".zip", ".tar", ".tgz", ".tar.gz", ".gz")
    return (
        lowered.endswith(suffixes)
        or prefix.startswith((b"PK\x03\x04", b"PK\x05\x06", b"\x1f\x8b"))
        or (len(prefix) >= 265 and prefix[257:262] == b"ustar")
    )


def _csv_summary(
    content: bytes, policy: IntakeRuntimePolicyV2
) -> ContentInspectionSummaryV2:
    if content.startswith(b"\xef\xbb\xbf") or b"\x00" in content:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    try:
        text = content.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if any(ord(character) < 32 and character not in "\r\n\t" for character in text):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    try:
        rows = list(csv.reader(io.StringIO(text, newline=""), strict=True))
    except csv.Error:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if not rows or len(rows) > policy.max_csv_rows:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    width = len(rows[0])
    if (
        width == 0
        or width > policy.max_csv_columns
        or any(len(row) != width for row in rows)
    ):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if (
        any(not header or header != header.strip() for header in rows[0])
        or len(set(rows[0])) != width
    ):
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    maximum = 0
    for row in rows:
        for cell in row:
            cell_bytes = len(cell.encode("utf-8"))
            maximum = max(maximum, cell_bytes)
            if cell_bytes > policy.max_csv_cell_bytes:
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            stripped = cell.lstrip(" \t\r\n")
            if stripped.startswith(("=", "+", "-", "@")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.CSV,
        archive_entry_count=0,
        archive_uncompressed_bytes=0,
        csv_row_count=len(rows),
        csv_column_count=width,
        csv_max_cell_bytes=maximum,
        formula_prefix_safe=True,
    )


def _zip_summary(
    content: bytes, policy: IntakeRuntimePolicyV2
) -> ContentInspectionSummaryV2:
    names: set[str] = set()
    total = 0
    count = 0
    try:
        with zipfile.ZipFile(io.BytesIO(content), mode="r") as archive:
            for entry in archive.infolist():
                count += 1
                if count > policy.max_archive_entries or not _safe_archive_name(
                    entry.filename
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.filename in names or entry.flag_bits & 0x1:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                names.add(entry.filename)
                mode = (entry.external_attr >> 16) & 0xFFFF
                file_type = stat.S_IFMT(mode)
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                total += entry.file_size
                if (
                    total > policy.max_archive_uncompressed_bytes
                    or entry.file_size
                    > max(entry.compress_size, 1) * policy.max_archive_ratio
                    or total > len(content) * policy.max_archive_ratio
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.is_dir():
                    continue
                with archive.open(entry, mode="r") as stream:
                    data = stream.read(policy.max_archive_uncompressed_bytes + 1)
                if (
                    len(data) != entry.file_size
                    or len(data) > policy.max_archive_uncompressed_bytes
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if _nested_archive(entry.filename, data[:512]):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    except ObjectIntakeRuntimeFailure:
        raise
    except OSError, RuntimeError, ValueError, zipfile.BadZipFile, NotImplementedError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if count == 0:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.ZIP,
        archive_entry_count=count,
        archive_uncompressed_bytes=total,
        csv_row_count=0,
        csv_column_count=0,
        csv_max_cell_bytes=0,
        formula_prefix_safe=True,
    )


def _tar_summary(
    content: bytes, policy: IntakeRuntimePolicyV2, *, compressed: bool
) -> ContentInspectionSummaryV2:
    names: set[str] = set()
    total = 0
    count = 0
    try:
        if compressed:
            with gzip.GzipFile(fileobj=io.BytesIO(content), mode="rb") as probe:
                uncompressed_probe = probe.read(
                    policy.max_archive_uncompressed_bytes + 1
                )
            if len(uncompressed_probe) > policy.max_archive_uncompressed_bytes:
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:*") as archive:
            for entry in archive:
                count += 1
                if count > policy.max_archive_entries or not _safe_archive_name(
                    entry.name
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.name in names or entry.issym() or entry.islnk():
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                names.add(entry.name)
                if not (entry.isfile() or entry.isdir()):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                total += entry.size
                if (
                    total > policy.max_archive_uncompressed_bytes
                    or total > len(content) * policy.max_archive_ratio
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if entry.isdir():
                    continue
                stream = archive.extractfile(entry)
                if stream is None:
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                with stream:
                    data = stream.read(policy.max_archive_uncompressed_bytes + 1)
                if (
                    len(data) != entry.size
                    or len(data) > policy.max_archive_uncompressed_bytes
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
                if _nested_archive(entry.name, data[:512]):
                    _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    except ObjectIntakeRuntimeFailure:
        raise
    except gzip.BadGzipFile, OSError, EOFError, tarfile.TarError, ValueError:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    if count == 0:
        _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
    return ContentInspectionSummaryV2(
        format=IntakeFormat.TAR_GZIP if compressed else IntakeFormat.TAR,
        archive_entry_count=count,
        archive_uncompressed_bytes=total,
        csv_row_count=0,
        csv_column_count=0,
        csv_max_cell_bytes=0,
        formula_prefix_safe=True,
    )


@final
class DeterministicContentInspectorV2:
    """Closed local parser; archives are read from memory and never extracted."""

    @property
    def action_count(self) -> int:
        return 0

    def inspect(
        self,
        *,
        descriptor: IntakeDescriptor,
        content: bytes,
        policy: IntakeRuntimePolicyV2,
    ) -> ContentInspectionSummaryV2:
        if (
            type(descriptor) is not IntakeDescriptor
            or type(content) is not bytes
            or not content
            or type(policy) is not IntakeRuntimePolicyV2
            or len(content) != descriptor.declared_size
            or len(content) > policy.max_object_bytes
            or descriptor.media_type.value not in policy.allowed_media_types
        ):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        name = descriptor.leaf_name.value.lower()
        media = descriptor.media_type.value
        if name.endswith(".csv") and media == "text/csv":
            if content.startswith((b"PK", b"\x1f\x8b", b"%PDF")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _csv_summary(content, policy)
        if name.endswith(".zip") and media == "application/zip":
            if not content.startswith((b"PK\x03\x04", b"PK\x05\x06")):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _zip_summary(content, policy)
        if name.endswith(".tar") and media == "application/x-tar":
            if len(content) < 265 or content[257:262] != b"ustar":
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _tar_summary(content, policy, compressed=False)
        if name.endswith((".tar.gz", ".tgz")) and media == "application/gzip":
            if not content.startswith(b"\x1f\x8b"):
                _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
            return _tar_summary(content, policy, compressed=True)
        binary: tuple[str, str, bytes, IntakeFormat] | None = None
        if name.endswith(".png"):
            binary = (".png", "image/png", b"\x89PNG\r\n\x1a\n", IntakeFormat.PNG)
        elif name.endswith((".jpg", ".jpeg")):
            binary = (".jpg", "image/jpeg", b"\xff\xd8\xff", IntakeFormat.JPEG)
        elif name.endswith(".webp"):
            if (
                media == "image/webp"
                and content.startswith(b"RIFF")
                and content[8:12] == b"WEBP"
            ):
                return ContentInspectionSummaryV2(
                    format=IntakeFormat.WEBP,
                    archive_entry_count=0,
                    archive_uncompressed_bytes=0,
                    csv_row_count=0,
                    csv_column_count=0,
                    csv_max_cell_bytes=0,
                    formula_prefix_safe=True,
                )
        elif name.endswith(".pdf"):
            binary = (".pdf", "application/pdf", b"%PDF-", IntakeFormat.PDF)
        if binary is None or media != binary[1] or not content.startswith(binary[2]):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        return ContentInspectionSummaryV2(
            format=binary[3],
            archive_entry_count=0,
            archive_uncompressed_bytes=0,
            csv_row_count=0,
            csv_column_count=0,
            csv_max_cell_bytes=0,
            formula_prefix_safe=True,
        )


class _InjectedCommitFault(RuntimeError):
    pass


class RecordedIntakeCommitFault(str):
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


@final
class RecordedSqliteObjectIntakeRepositoryV2:
    """Recorded-only durable quarantine with no byte read/export lifecycle API."""

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        private_root: Path,
        fault_once_at: str | None = None,
    ) -> None:
        self._environment = _recorded_environment(environment)
        if fault_once_at not in {
            None,
            RecordedIntakeCommitFault.BEFORE_COMMIT,
            RecordedIntakeCommitFault.AFTER_COMMIT,
        }:
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        self._private_root, self._root_identity = self._prepare_private_root(
            private_root
        )
        self._database_path = self._private_root / _DATABASE_NAME
        self._database_identity: tuple[int, int] = (-1, -1)
        self._fault_once_at = fault_once_at
        self._fault_lock = Lock()
        self._state_lock = RLock()
        self._process_anchor: _ProcessAnchor | None = None
        with _SCHEMA_INITIALIZATION_LOCK:
            created, identity = self._open_database_file(allow_create=True)
            self._database_identity = identity
            connection = self._connect(allow_empty=created)
            try:
                if created:
                    self._initialize_new(connection)
                state = self._validate_all(connection, allow_in_progress=False)
                self._bind_process_anchor(connection, state=state)
            finally:
                self._close_safely(connection)

    @property
    def action_count(self) -> int:
        return 0

    @staticmethod
    def _prepare_private_root(value: object) -> tuple[Path, tuple[int, int]]:
        if not isinstance(value, Path) or not value.is_absolute():
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        root = Path(os.path.abspath(value))
        if not root.exists():
            parent = root.parent
            if not parent.exists():
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            RecordedSqliteObjectIntakeRepositoryV2._validate_ancestor_chain(parent)
            try:
                os.mkdir(root, 0o700)
            except OSError:
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        RecordedSqliteObjectIntakeRepositoryV2._validate_ancestor_chain(root)
        metadata = os.lstat(root)
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        return root, (metadata.st_dev, metadata.st_ino)

    @staticmethod
    def _validate_ancestor_chain(path: Path) -> None:
        current_fd = os.open(
            "/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
        )
        descriptors = [current_fd]
        try:
            for component in path.parts[1:]:
                named = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
                if stat.S_ISLNK(named.st_mode) or not stat.S_ISDIR(named.st_mode):
                    _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
                child = os.open(
                    component,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    dir_fd=current_fd,
                )
                opened = os.fstat(child)
                if (
                    opened.st_dev != named.st_dev
                    or opened.st_ino != named.st_ino
                    or opened.st_mode != named.st_mode
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
                descriptors.append(child)
                current_fd = child
        except ObjectIntakeRuntimeFailure:
            raise
        except OSError:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            for descriptor in reversed(descriptors):
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def _open_database_file(
        self, *, allow_create: bool, allow_empty: bool = False
    ) -> tuple[bool, tuple[int, int]]:
        root_fd = -1
        descriptor = -1
        created = False
        try:
            root_fd = os.open(
                self._private_root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
            )
            root_metadata = os.fstat(root_fd)
            if (
                (root_metadata.st_dev, root_metadata.st_ino) != self._root_identity
                or root_metadata.st_uid != os.geteuid()
                or stat.S_IMODE(root_metadata.st_mode) != 0o700
            ):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
            if allow_create:
                try:
                    descriptor = os.open(
                        _DATABASE_NAME,
                        flags | os.O_CREAT | os.O_EXCL,
                        0o600,
                        dir_fd=root_fd,
                    )
                    created = True
                    os.fsync(descriptor)
                    os.fsync(root_fd)
                except FileExistsError:
                    descriptor = os.open(_DATABASE_NAME, flags, dir_fd=root_fd)
            else:
                descriptor = os.open(
                    _DATABASE_NAME,
                    flags,
                    dir_fd=root_fd,
                )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or stat.S_IMODE(metadata.st_mode) != 0o600
                or metadata.st_nlink != 1
                or (not created and not allow_empty and metadata.st_size == 0)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            return created, (metadata.st_dev, metadata.st_ino)
        except ObjectIntakeRuntimeFailure:
            raise
        except OSError:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_fd >= 0:
                os.close(root_fd)

    def _validate_database_identity(self) -> None:
        try:
            root = self._private_root.lstat()
            database = self._database_path.lstat()
        except OSError:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        if (
            (root.st_dev, root.st_ino) != self._root_identity
            or stat.S_ISLNK(root.st_mode)
            or not stat.S_ISDIR(root.st_mode)
            or root.st_uid != os.geteuid()
            or stat.S_IMODE(root.st_mode) != 0o700
            or (database.st_dev, database.st_ino) != self._database_identity
            or stat.S_ISLNK(database.st_mode)
            or not stat.S_ISREG(database.st_mode)
            or database.st_uid != os.geteuid()
            or database.st_nlink != 1
            or stat.S_IMODE(database.st_mode) != 0o600
        ):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def _connect(self, *, allow_empty: bool = False) -> sqlite3.Connection:
        _created, identity = self._open_database_file(
            allow_create=False, allow_empty=allow_empty
        )
        if identity != self._database_identity:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=10.0,
                isolation_level=None,
                check_same_thread=False,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA busy_timeout=10000")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            if tuple(connection.execute("PRAGMA journal_mode=DELETE").fetchone()) != (
                "delete",
            ):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            self._validate_database_identity()
            return connection
        except ObjectIntakeRuntimeFailure:
            if connection is not None:
                self._close_safely(connection)
            raise
        except sqlite3.Error, OSError:
            if connection is not None:
                self._close_safely(connection)
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def _initialize_new(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            if tuple(
                connection.execute("SELECT COUNT(*) FROM sqlite_schema").fetchone()
            ) != (0,):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            connection.execute(f"PRAGMA application_id={_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version={_SCHEMA_VERSION}")
            for name in _SCHEMA_TABLE_NAMES:
                connection.execute(_SCHEMA_OBJECTS[name])
            for name in _SCHEMA_INDEX_TABLES:
                connection.execute(_SCHEMA_OBJECTS[name])
            values = _metadata_values(
                event_count=0,
                event_head=_GENESIS,
                command_count=0,
                command_head=_GENESIS,
                audit_count=0,
                audit_head=_GENESIS,
            )
            connection.execute(
                "INSERT INTO st0406_runtime_metadata VALUES (?,?,?,?,?,?,?,?,?,?)",
                (*values, _row_digest(values)),
            )
            for name in _SCHEMA_TRIGGER_TABLES:
                connection.execute(_SCHEMA_OBJECTS[name])
            if not _schema_is_exact(connection):
                _fail(ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT)
            connection.commit()
            self._validate_database_identity()
        except ObjectIntakeRuntimeFailure:
            connection.rollback()
            raise
        except sqlite3.Error:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def _validate_all(
        self, connection: sqlite3.Connection, *, allow_in_progress: bool
    ) -> _IntegrityState:
        self._validate_database_identity()
        if not _schema_is_exact(connection):
            _fail(ObjectIntakeRuntimeFailureCode.SCHEMA_DRIFT)
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or tuple(integrity) != ("ok",):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        metadata = connection.execute(
            "SELECT singleton,schema_version,schema_binding,event_count,event_head,"
            "command_count,command_head,audit_count,audit_head,record_sha256 "
            "FROM st0406_runtime_metadata"
        ).fetchall()
        if len(metadata) != 1:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        meta = tuple(metadata[0])
        if (
            len(meta) != 10
            or meta[0] != 1
            or meta[1] != _SCHEMA_VERSION
            or meta[2] != _SCHEMA_BINDING
            or _integer(meta[3]) < 0
            or _sha(meta[4]) != meta[4]
            or _integer(meta[5]) < 0
            or _sha(meta[6]) != meta[6]
            or _integer(meta[7]) < 0
            or _sha(meta[8]) != meta[8]
            or not meta[3] == meta[5] == meta[7]
            or _sha(meta[9]) != _row_digest(meta[:-1])
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        event_count = cast(int, meta[3])
        event_head = cast(str, meta[4])
        command_head = cast(str, meta[6])
        audit_head = cast(str, meta[8])

        quarantine_rows = connection.execute(
            "SELECT * FROM st0406_quarantine ORDER BY command_id"
        ).fetchall()
        quarantine: dict[str, sqlite3.Row] = {}
        for row in quarantine_rows:
            values = _quarantine_values(row)
            if _sha(row["record_sha256"]) != _row_digest(values):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            command = _text(row["command_id"])
            try:
                UUID(_text(row["intake_id"], maximum=36))
                UUID(_text(row["quarantine_id"], maximum=36))
                UUID(_text(row["site_id"], maximum=36))
                UUID(_text(row["authorization_resource_id"], maximum=36))
                ObjectIntakeKind(_text(row["kind"], maximum=32))
                IntakePrivacyClass(_text(row["privacy_class"], maximum=32))
                state = DurableIntakeState(_text(row["state"], maximum=32))
            except ValueError, AttributeError:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            version = _integer(row["version"], minimum=1)
            received = _integer(row["received_bytes"])
            chunks = _integer(row["chunk_count"])
            declared = _integer(row["declared_size"], minimum=1)
            content = row["content"]
            _text(row["leaf_name"], maximum=128)
            _text(row["media_type"], maximum=127)
            if (
                _sha(row["request_digest"]) != row["request_digest"]
                or _sha(row["descriptor_digest"]) != row["descriptor_digest"]
                or _sha(row["authorization_digest"]) != row["authorization_digest"]
                or _sha(row["declared_sha256"]) != row["declared_sha256"]
                or type(content) is not bytes
                or len(content) != received
                or received > declared
                or (received == 0) != (chunks == 0)
                or (not allow_in_progress and state.value not in _FINAL_STATES)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state in {
                DurableIntakeState.SEALED,
                DurableIntakeState.CLEAN_QUARANTINED,
            } and (
                received != declared
                or _sha(row["sealed_sha256"]) != hashlib.sha256(content).hexdigest()
                or row["sealed_sha256"] != row["declared_sha256"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state is DurableIntakeState.CLEAN_QUARANTINED and (
                row["failure_code"] is not None or row["result_document"] is None
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            if state is DurableIntakeState.REJECTED and (
                row["failure_code"] is None or row["result_document"] is None
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            quarantine[command] = row

        previous = _GENESIS
        last_version: dict[str, int] = {}
        final_head: dict[str, str] = {}
        first_kind: set[str] = set()
        lifecycle_by_command: dict[str, list[_LifecycleRecord]] = {}
        lifecycle_by_sequence: dict[int, tuple[str, int, str, str, str]] = {}
        event_rows = connection.execute(
            "SELECT sequence,command_id,version,event_kind,event_document,"
            "previous_digest,digest,record_sha256 "
            "FROM st0406_quarantine_event ORDER BY sequence"
        ).fetchall()
        if len(event_rows) != event_count:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for expected_sequence, raw in enumerate(event_rows, start=1):
            row = tuple(raw)
            values = row[:-1]
            if row[0] != expected_sequence or _sha(row[-1]) != _row_digest(values):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            command = _text(row[1])
            version = _integer(row[2], minimum=1)
            kind = _text(row[3], maximum=16)
            event_document = _text(row[4], maximum=_MAX_DOCUMENT_BYTES)
            prior = _sha(row[5])
            digest = _sha(row[6])
            if (
                command not in quarantine
                or kind not in _EVENT_KINDS
                or prior != previous
                or digest
                != _event_digest(
                    sequence=expected_sequence,
                    command_id=command,
                    version=version,
                    event_kind=kind,
                    event_document=event_document,
                    previous_digest=prior,
                )
                or version != last_version.get(command, 0) + 1
                or (command not in first_kind and kind != "OPEN")
                or (command in first_kind and kind == "OPEN")
                or version > quarantine[command]["version"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            document = _document(event_document)
            first_kind.add(command)
            last_version[command] = version
            final_head[command] = digest
            lifecycle_by_command.setdefault(command, []).append(
                _LifecycleRecord(
                    sequence=expected_sequence,
                    version=version,
                    kind=kind,
                    document=document,
                    digest=digest,
                )
            )
            lifecycle_by_sequence[expected_sequence] = (
                command,
                version,
                kind,
                event_document,
                digest,
            )
            previous = digest
        if previous != event_head or event_count != len(event_rows):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for command, row in quarantine.items():
            if last_version.get(command) != row["version"]:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        previous_command = _GENESIS
        command_rows = connection.execute(
            "SELECT sequence,lifecycle_sequence,command_id,version,operation,"
            "intent_document,result_document,previous_digest,digest,record_sha256 "
            "FROM st0406_intake_command ORDER BY sequence"
        ).fetchall()
        if len(command_rows) != event_count:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        command_by_sequence: dict[int, tuple[str, str, str]] = {}
        for expected_sequence, raw in enumerate(command_rows, start=1):
            row = tuple(raw)
            values = row[:-1]
            lifecycle = lifecycle_by_sequence.get(expected_sequence)
            intent_document = _text(row[5], maximum=_MAX_DOCUMENT_BYTES)
            result_document = _text(row[6], maximum=_MAX_DOCUMENT_BYTES)
            prior = _sha(row[7])
            digest = _sha(row[8])
            if (
                row[0] != expected_sequence
                or row[1] != expected_sequence
                or lifecycle is None
                or row[2] != lifecycle[0]
                or row[3] != lifecycle[1]
                or row[4] != lifecycle[2]
                or intent_document != lifecycle[3]
                or result_document != _command_result_document(lifecycle[4])
                or _document(intent_document)
                != lifecycle_by_command[cast(str, row[2])][
                    cast(int, row[3]) - 1
                ].document
                or _document(result_document)
                != {
                    "schema": "ST0406_COMMAND_RESULT_V2",
                    "lifecycle_digest": lifecycle[4],
                }
                or prior != previous_command
                or digest
                != _command_digest(
                    sequence=expected_sequence,
                    lifecycle_sequence=expected_sequence,
                    command_id=_text(row[2]),
                    version=_integer(row[3], minimum=1),
                    operation=_text(row[4], maximum=16),
                    intent_document=intent_document,
                    result_document=result_document,
                    previous_digest=prior,
                )
                or _sha(row[9]) != _row_digest(values)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            command_by_sequence[expected_sequence] = (
                _text(row[2]),
                _text(row[4], maximum=16),
                digest,
            )
            previous_command = digest
        if previous_command != command_head:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        previous_audit = _GENESIS
        audit_rows = connection.execute(
            "SELECT sequence,command_sequence,command_id,action,outcome,"
            "binding_digest,previous_digest,digest,record_sha256 "
            "FROM st0406_intake_audit ORDER BY sequence"
        ).fetchall()
        if len(audit_rows) != event_count:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for expected_sequence, raw in enumerate(audit_rows, start=1):
            row = tuple(raw)
            values = row[:-1]
            command_record = command_by_sequence.get(expected_sequence)
            action = _text(row[3], maximum=32)
            audit_outcome = _text(row[4], maximum=16)
            binding = _sha(row[5])
            prior = _sha(row[6])
            digest = _sha(row[7])
            if (
                row[0] != expected_sequence
                or row[1] != expected_sequence
                or command_record is None
                or row[2] != command_record[0]
                or action != f"INTAKE_{command_record[1]}"
                or audit_outcome != "RECORDED"
                or binding != command_record[2]
                or prior != previous_audit
                or digest
                != _audit_digest(
                    sequence=expected_sequence,
                    command_sequence=expected_sequence,
                    command_id=_text(row[2]),
                    action=action,
                    outcome=audit_outcome,
                    binding_digest=binding,
                    previous_digest=prior,
                )
                or _sha(row[8]) != _row_digest(values)
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            previous_audit = digest
        if previous_audit != audit_head:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        result_rows = connection.execute(
            "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
            "outcome,document,digest,record_sha256 FROM st0406_intake_result "
            "ORDER BY command_id"
        ).fetchall()
        results: dict[str, RecoveredIntakeOutcomeV2] = {}
        for raw in result_rows:
            outcome = _outcome_from_result_row(tuple(raw))
            command = _text(raw["command_id"])
            if command not in quarantine or command in results:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            projection = quarantine[command]
            if (
                projection["request_digest"] != outcome.request_digest
                or projection["descriptor_digest"] != outcome.descriptor_digest
                or projection["authorization_digest"] != outcome.authorization_digest
                or projection["result_document"] != raw["document"]
                or projection["state"] != raw["outcome"]
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            receipt = outcome.accepted or outcome.rejected
            if receipt is None or receipt.journal_head_sha256 != final_head.get(
                command
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            results[command] = outcome
        if not allow_in_progress and set(results) != set(quarantine):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

        duplicate_rows = connection.execute(
            "SELECT sha256,intake_id,command_id,record_sha256 "
            "FROM st0406_duplicate_index ORDER BY sha256"
        ).fetchall()
        for raw in duplicate_rows:
            values = tuple(raw)[:-1]
            sha256, intake_id, command_id = values
            if (
                _sha(raw[-1]) != _row_digest(values)
                or _sha(sha256) != sha256
                or _text(command_id) not in results
                or results[_text(command_id)].accepted is None
                or quarantine[_text(command_id)]["intake_id"] != intake_id
                or quarantine[_text(command_id)]["sealed_sha256"] != sha256
            ):
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        for command, projection in quarantine.items():
            _validate_lifecycle_semantics(
                command_id=command,
                projection=projection,
                records=tuple(lifecycle_by_command.get(command, ())),
                result=results.get(command),
                allow_in_progress=allow_in_progress,
            )
        return _IntegrityState(
            count=event_count,
            event_head=event_head,
            command_head=command_head,
            audit_head=audit_head,
        )

    def _bind_process_anchor(
        self, connection: sqlite3.Connection, *, state: _IntegrityState
    ) -> None:
        key = str(self._database_path)
        with _PROCESS_REGISTRY_LOCK:
            anchor = _PROCESS_ANCHORS.get(key)
            if anchor is None:
                anchor = _ProcessAnchor(
                    database_identity=self._database_identity,
                    root_identity=self._root_identity,
                    state=state,
                    lock=RLock(),
                )
                _PROCESS_ANCHORS[key] = anchor
            elif (
                anchor.database_identity != self._database_identity
                or anchor.root_identity != self._root_identity
            ):
                _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
            self._process_anchor = anchor
        with anchor.lock:
            self._require_process_monotonic(connection, state=state)
            if state.count > anchor.state.count:
                anchor.state = state

    def _require_process_monotonic(
        self, connection: sqlite3.Connection, *, state: _IntegrityState
    ) -> None:
        anchor = self._process_anchor
        if anchor is None:
            return
        if (
            anchor.database_identity != self._database_identity
            or anchor.root_identity != self._root_identity
            or state.count < anchor.state.count
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        if anchor.state.count == 0:
            observed = _IntegrityState(
                count=0,
                event_head=_GENESIS,
                command_head=_GENESIS,
                audit_head=_GENESIS,
            )
        else:
            sequence = anchor.state.count
            event = connection.execute(
                "SELECT digest FROM st0406_quarantine_event WHERE sequence=?",
                (sequence,),
            ).fetchone()
            command = connection.execute(
                "SELECT digest FROM st0406_intake_command WHERE sequence=?",
                (sequence,),
            ).fetchone()
            audit = connection.execute(
                "SELECT digest FROM st0406_intake_audit WHERE sequence=?",
                (sequence,),
            ).fetchone()
            if event is None or command is None or audit is None:
                _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
            observed = _IntegrityState(
                count=sequence,
                event_head=_sha(event[0]),
                command_head=_sha(command[0]),
                audit_head=_sha(audit[0]),
            )
        if observed != anchor.state or (
            state.count == anchor.state.count and state != anchor.state
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)

    def _pin_process_state(self, *, state: _IntegrityState) -> None:
        anchor = self._process_anchor
        if anchor is None or state.count < anchor.state.count:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        if state.count == anchor.state.count and state != anchor.state:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        anchor.state = state

    def _acquire_state(self) -> _ProcessAnchor:
        self._state_lock.acquire()
        anchor = self._process_anchor
        if anchor is None:
            self._state_lock.release()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        anchor.lock.acquire()
        return anchor

    def _release_state(self, anchor: _ProcessAnchor) -> None:
        anchor.lock.release()
        self._state_lock.release()

    @staticmethod
    def _close_safely(connection: sqlite3.Connection) -> None:
        try:
            connection.close()
        except sqlite3.Error:
            pass

    def _append_event(
        self,
        connection: sqlite3.Connection,
        *,
        command_id: str,
        version: int,
        event_kind: str,
        event: dict[str, object],
    ) -> str:
        meta = connection.execute(
            "SELECT singleton,schema_version,schema_binding,event_count,event_head,"
            "command_count,command_head,audit_count,audit_head,record_sha256 "
            "FROM st0406_runtime_metadata WHERE singleton=1"
        ).fetchone()
        if meta is None:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        values = tuple(meta)
        if _sha(values[-1]) != _row_digest(values[:-1]):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        sequence = _integer(values[3]) + 1
        if sequence != _integer(values[5]) + 1 or sequence != _integer(values[7]) + 1:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        previous = _sha(values[4])
        previous_command = _sha(values[6])
        previous_audit = _sha(values[8])
        document = _json_bytes(event).decode("ascii")
        digest = _event_digest(
            sequence=sequence,
            command_id=command_id,
            version=version,
            event_kind=event_kind,
            event_document=document,
            previous_digest=previous,
        )
        event_values = (
            sequence,
            command_id,
            version,
            event_kind,
            document,
            previous,
            digest,
        )
        connection.execute(
            "INSERT INTO st0406_quarantine_event VALUES (?,?,?,?,?,?,?,?)",
            (*event_values, _row_digest(event_values)),
        )
        command_result = _command_result_document(digest)
        command_digest = _command_digest(
            sequence=sequence,
            lifecycle_sequence=sequence,
            command_id=command_id,
            version=version,
            operation=event_kind,
            intent_document=document,
            result_document=command_result,
            previous_digest=previous_command,
        )
        command_values = (
            sequence,
            sequence,
            command_id,
            version,
            event_kind,
            document,
            command_result,
            previous_command,
            command_digest,
        )
        connection.execute(
            "INSERT INTO st0406_intake_command VALUES (?,?,?,?,?,?,?,?,?,?)",
            (*command_values, _row_digest(command_values)),
        )
        audit_action = f"INTAKE_{event_kind}"
        audit_digest = _audit_digest(
            sequence=sequence,
            command_sequence=sequence,
            command_id=command_id,
            action=audit_action,
            outcome="RECORDED",
            binding_digest=command_digest,
            previous_digest=previous_audit,
        )
        audit_values = (
            sequence,
            sequence,
            command_id,
            audit_action,
            "RECORDED",
            command_digest,
            previous_audit,
            audit_digest,
        )
        connection.execute(
            "INSERT INTO st0406_intake_audit VALUES (?,?,?,?,?,?,?,?,?)",
            (*audit_values, _row_digest(audit_values)),
        )
        metadata_values = _metadata_values(
            event_count=sequence,
            event_head=digest,
            command_count=sequence,
            command_head=command_digest,
            audit_count=sequence,
            audit_head=audit_digest,
        )
        cursor = connection.execute(
            "UPDATE st0406_runtime_metadata SET event_count=?,event_head=?,"
            "command_count=?,command_head=?,audit_count=?,audit_head=?,record_sha256=? "
            "WHERE singleton=1 AND event_count=? AND event_head=? "
            "AND command_count=? AND command_head=? AND audit_count=? AND audit_head=? "
            "AND record_sha256=?",
            (
                sequence,
                digest,
                sequence,
                command_digest,
                sequence,
                audit_digest,
                _row_digest(metadata_values),
                values[3],
                previous,
                values[5],
                previous_command,
                values[7],
                previous_audit,
                values[-1],
            ),
        )
        if cursor.rowcount != 1:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        return digest

    def _begin(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        descriptor_digest: str,
        authorization_digest: str,
        descriptor: DurableIntakeDescriptorV2,
    ) -> RecordedObjectIntakeUnitOfWorkV2:
        if (
            type(command_id) is not IntakeCommandId
            or type(descriptor) is not DurableIntakeDescriptorV2
        ):
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        for digest in (request_digest, descriptor_digest, authorization_digest):
            if type(digest) is not str or _SHA256.fullmatch(digest) is None:
                _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        if _digest_document(_descriptor_document(descriptor)) != descriptor_digest:
            _fail(ObjectIntakeRuntimeFailureCode.INVALID_ARGUMENT)
        base = descriptor.descriptor
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN IMMEDIATE")
            state = self._validate_all(connection, allow_in_progress=False)
            self._require_process_monotonic(connection, state=state)
            self._pin_process_state(state=state)
            existing = connection.execute(
                "SELECT request_digest,descriptor_digest,authorization_digest "
                "FROM st0406_quarantine WHERE command_id=?",
                (command_id.value,),
            ).fetchone()
            if existing is not None:
                if tuple(existing) != (
                    request_digest,
                    descriptor_digest,
                    authorization_digest,
                ):
                    _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
                outcome_row = connection.execute(
                    "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
                    "outcome,document,digest,record_sha256 FROM st0406_intake_result "
                    "WHERE command_id=?",
                    (command_id.value,),
                ).fetchone()
                if outcome_row is None:
                    _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
                return RecordedObjectIntakeUnitOfWorkV2(
                    repository=self,
                    connection=connection,
                    command_id=command_id,
                    existing=_outcome_from_result_row(tuple(outcome_row)),
                    anchor=anchor,
                )
            collision = connection.execute(
                "SELECT command_id FROM st0406_quarantine WHERE intake_id=?",
                (str(base.intake_id),),
            ).fetchone()
            if collision is not None:
                _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
            quarantine_id = _quarantine_id(command_id)
            base_values = (
                command_id.value,
                request_digest,
                descriptor_digest,
                authorization_digest,
                str(base.intake_id),
                str(quarantine_id),
                str(base.site_id),
                str(descriptor.authorization_resource_id),
                base.kind.value,
                base.leaf_name.value,
                base.media_type.value,
                base.declared_size,
                base.declared_sha256.value,
                base.privacy_class.value,
                DurableIntakeState.OPEN.value,
                1,
                0,
                0,
                b"",
                None,
                None,
                None,
            )
            digest_values = (
                *base_values[:18],
                hashlib.sha256(b"").hexdigest(),
                *base_values[19:],
            )
            connection.execute(
                "INSERT INTO st0406_quarantine VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*base_values, _row_digest(digest_values)),
            )
            self._append_event(
                connection,
                command_id=command_id.value,
                version=1,
                event_kind="OPEN",
                event={
                    "schema": "ST0406_OPEN_V2",
                    "descriptor_digest": descriptor_digest,
                    "authorization_digest": authorization_digest,
                },
            )
            return RecordedObjectIntakeUnitOfWorkV2(
                repository=self,
                connection=connection,
                command_id=command_id,
                existing=None,
                anchor=anchor,
            )
        except ObjectIntakeRuntimeFailure:
            if connection is not None:
                connection.rollback()
                self._close_safely(connection)
            self._release_state(anchor)
            raise
        except sqlite3.Error:
            if connection is not None:
                connection.rollback()
                self._close_safely(connection)
            self._release_state(anchor)
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            if connection is not None:
                connection.rollback()
                self._close_safely(connection)
            self._release_state(anchor)
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)

    def begin(
        self,
        *,
        command_id: IntakeCommandId,
        request_digest: str,
        descriptor_digest: str,
        authorization_digest: str,
        descriptor: DurableIntakeDescriptorV2,
    ) -> RecordedObjectIntakeUnitOfWorkV2:
        return self._begin(
            command_id=command_id,
            request_digest=request_digest,
            descriptor_digest=descriptor_digest,
            authorization_digest=authorization_digest,
            descriptor=descriptor,
        )

    def recover(
        self, *, command_id: IntakeCommandId, request_digest: str
    ) -> RecoveredIntakeOutcomeV2:
        if (
            type(command_id) is not IntakeCommandId
            or type(request_digest) is not str
            or _SHA256.fullmatch(request_digest) is None
        ):
            _fail(ObjectIntakeRuntimeFailureCode.RECOVERY_NOT_FOUND)
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN")
            state = self._validate_all(connection, allow_in_progress=False)
            self._require_process_monotonic(connection, state=state)
            self._pin_process_state(state=state)
            row = connection.execute(
                "SELECT command_id,request_digest,descriptor_digest,authorization_digest,"
                "outcome,document,digest,record_sha256 FROM st0406_intake_result "
                "WHERE command_id=?",
                (command_id.value,),
            ).fetchone()
            if row is None:
                _fail(ObjectIntakeRuntimeFailureCode.RECOVERY_NOT_FOUND)
            outcome = _outcome_from_result_row(tuple(row))
            if outcome.request_digest != request_digest:
                _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)
            connection.rollback()
            return outcome
        except ObjectIntakeRuntimeFailure:
            if connection is not None:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection is not None:
                connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        except Exception:
            if connection is not None:
                connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            if connection is not None:
                self._close_safely(connection)
            self._release_state(anchor)

    def verify_integrity(self) -> None:
        anchor = self._acquire_state()
        connection: sqlite3.Connection | None = None
        try:
            connection = self._connect()
            connection.execute("BEGIN")
            state = self._validate_all(connection, allow_in_progress=False)
            self._require_process_monotonic(connection, state=state)
            self._pin_process_state(state=state)
            connection.rollback()
        except ObjectIntakeRuntimeFailure:
            if connection is not None:
                connection.rollback()
            raise
        except Exception:
            if connection is not None:
                connection.rollback()
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        finally:
            if connection is not None:
                self._close_safely(connection)
            self._release_state(anchor)

    def _inject_fault(self, point: str) -> None:
        with self._fault_lock:
            if self._fault_once_at == point:
                self._fault_once_at = None
                raise _InjectedCommitFault("ST0406_RECORDED_COMMIT_FAULT")


@final
class RecordedObjectIntakeUnitOfWorkV2:
    def __init__(
        self,
        *,
        repository: RecordedSqliteObjectIntakeRepositoryV2,
        connection: sqlite3.Connection,
        command_id: IntakeCommandId,
        existing: RecoveredIntakeOutcomeV2 | None,
        anchor: _ProcessAnchor,
    ) -> None:
        self._repository = repository
        self._connection = connection
        self._command_id = command_id
        self._existing = existing
        self._anchor = anchor
        self._closed = False
        self._finalized = existing is not None

    def _require_open(self) -> sqlite3.Connection:
        if self._closed:
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        return self._connection

    def existing(self) -> RecoveredIntakeOutcomeV2 | None:
        self._require_open()
        return self._existing

    def _projection(self) -> sqlite3.Row:
        row = (
            self._require_open()
            .execute(
                "SELECT * FROM st0406_quarantine WHERE command_id=?",
                (self._command_id.value,),
            )
            .fetchone()
        )
        if row is None or _sha(row["record_sha256"]) != _row_digest(
            _quarantine_values(row)
        ):
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        return cast(sqlite3.Row, row)

    def _update_projection(
        self,
        row: sqlite3.Row,
        *,
        expected_version: int,
        state: DurableIntakeState,
        received_bytes: int,
        chunk_count: int,
        content: bytes,
        sealed_sha256: str | None,
        failure_code: str | None,
        result_document: str | None,
    ) -> int:
        if type(expected_version) is not int or expected_version != row["version"]:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        next_version = expected_version + 1
        base = (
            row["command_id"],
            row["request_digest"],
            row["descriptor_digest"],
            row["authorization_digest"],
            row["intake_id"],
            row["quarantine_id"],
            row["site_id"],
            row["authorization_resource_id"],
            row["kind"],
            row["leaf_name"],
            row["media_type"],
            row["declared_size"],
            row["declared_sha256"],
            row["privacy_class"],
            state.value,
            next_version,
            received_bytes,
            chunk_count,
            hashlib.sha256(content).hexdigest(),
            sealed_sha256,
            failure_code,
            result_document,
        )
        cursor = self._require_open().execute(
            "UPDATE st0406_quarantine SET state=?,version=?,received_bytes=?,"
            "chunk_count=?,content=?,sealed_sha256=?,failure_code=?,result_document=?,"
            "record_sha256=? WHERE command_id=? AND version=? AND record_sha256=?",
            (
                state.value,
                next_version,
                received_bytes,
                chunk_count,
                content,
                sealed_sha256,
                failure_code,
                result_document,
                _row_digest(base),
                self._command_id.value,
                expected_version,
                row["record_sha256"],
            ),
        )
        if cursor.rowcount != 1:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        return next_version

    def append(self, *, expected_version: int, chunk: bytes) -> int:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.OPEN.value
            or type(chunk) is not bytes
            or not chunk
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        content = row["content"]
        if type(content) is not bytes:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        combined = content + chunk
        if len(combined) > row["declared_size"]:
            _fail(ObjectIntakeRuntimeFailureCode.STREAM_LIMIT_EXCEEDED)
        next_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.OPEN,
            received_bytes=len(combined),
            chunk_count=row["chunk_count"] + 1,
            content=combined,
            sealed_sha256=None,
            failure_code=None,
            result_document=None,
        )
        self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="APPEND",
            event={
                "schema": "ST0406_APPEND_V2",
                "chunk_bytes": len(chunk),
                "chunk_sha256": hashlib.sha256(chunk).hexdigest(),
                "received_bytes": len(combined),
            },
        )
        return next_version

    def seal(
        self,
        *,
        expected_version: int,
        sha256: Sha256Digest,
        received_bytes: int,
        chunk_count: int,
    ) -> int:
        row = self._projection()
        content = row["content"]
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.OPEN.value
            or type(sha256) is not Sha256Digest
            or type(content) is not bytes
            or type(received_bytes) is not int
            or type(chunk_count) is not int
            or received_bytes != len(content)
            or received_bytes != row["received_bytes"]
            or received_bytes != row["declared_size"]
            or chunk_count != row["chunk_count"]
            or sha256.value != row["declared_sha256"]
            or sha256.value != hashlib.sha256(content).hexdigest()
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONTENT_MISMATCH)
        next_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.SEALED,
            received_bytes=received_bytes,
            chunk_count=chunk_count,
            content=content,
            sealed_sha256=sha256.value,
            failure_code=None,
            result_document=None,
        )
        self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="SEAL",
            event={
                "schema": "ST0406_SEAL_V2",
                "received_bytes": received_bytes,
                "chunk_count": chunk_count,
                "sha256": sha256.value,
            },
        )
        return next_version

    def reject(
        self,
        *,
        expected_version: int,
        failure_code: ObjectIntakeRuntimeFailureCode,
    ) -> RejectedQuarantineReceiptV2:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or type(failure_code) is not ObjectIntakeRuntimeFailureCode
        ):
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        content = row["content"]
        if type(content) is not bytes:
            _fail(ObjectIntakeRuntimeFailureCode.TAMPER_DETECTED)
        next_version = expected_version + 1
        head = self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="REJECT",
            event={
                "schema": "ST0406_REJECT_V2",
                "failure_code": failure_code.value,
                "received_bytes": row["received_bytes"],
            },
        )
        receipt = RejectedQuarantineReceiptV2(
            command_id=self._command_id,
            intake_id=UUID(row["intake_id"]),
            quarantine_id=UUID(row["quarantine_id"]),
            state=DurableIntakeState.REJECTED,
            version=next_version,
            failure_code=failure_code,
            journal_head_sha256=head,
        )
        document = _json_bytes(_rejected_document(receipt)).decode("ascii")
        observed_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.REJECTED,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            content=content,
            sealed_sha256=row["sealed_sha256"],
            failure_code=failure_code.value,
            result_document=document,
        )
        if observed_version != next_version:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        self._insert_result(
            row=row, outcome=DurableIntakeState.REJECTED, document=document
        )
        self._finalized = True
        return receipt

    def accept(
        self,
        *,
        expected_version: int,
        inspection: ContentInspectionSummaryV2,
        privacy: PrivacyClassificationReceiptV2,
        malware: MalwareScanReceiptV2,
    ) -> DurableQuarantineReceiptV2:
        row = self._projection()
        if (
            self._existing is not None
            or self._finalized
            or row["state"] != DurableIntakeState.SEALED.value
            or type(inspection) is not ContentInspectionSummaryV2
            or type(privacy) is not PrivacyClassificationReceiptV2
            or privacy.verdict is not RecordedPrivacyVerdict.MATCH
            or privacy.classified_as is None
            or privacy.classified_as.value != row["privacy_class"]
            or type(malware) is not MalwareScanReceiptV2
            or malware.verdict is not RecordedMalwareVerdict.CLEAN
        ):
            _fail(ObjectIntakeRuntimeFailureCode.FORMAT_REJECTED)
        duplicate = self._connection.execute(
            "SELECT intake_id FROM st0406_duplicate_index WHERE sha256=?",
            (row["sealed_sha256"],),
        ).fetchone()
        duplicate_status = (
            DuplicateStatus.NEW
            if duplicate is None
            else DuplicateStatus.EXACT_DUPLICATE
        )
        duplicate_id = None if duplicate is None else UUID(duplicate[0])
        next_version = expected_version + 1
        head = self._repository._append_event(  # pyright: ignore[reportPrivateUsage]
            self._connection,
            command_id=self._command_id.value,
            version=next_version,
            event_kind="ACCEPT",
            event={
                "schema": "ST0406_ACCEPT_V2",
                "inspection_sha256": _digest_document(_inspection_document(inspection)),
                "privacy_sha256": _digest_document(_privacy_document(privacy)),
                "malware_sha256": _digest_document(_malware_document(malware)),
                "duplicate_status": duplicate_status.value,
            },
        )
        receipt = DurableQuarantineReceiptV2(
            command_id=self._command_id,
            intake_id=UUID(row["intake_id"]),
            quarantine_id=UUID(row["quarantine_id"]),
            site_id=UUID(row["site_id"]),
            authorization_resource_id=UUID(row["authorization_resource_id"]),
            kind=ObjectIntakeKind(row["kind"]),
            state=DurableIntakeState.CLEAN_QUARANTINED,
            version=next_version,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            sha256=Sha256Digest(row["sealed_sha256"]),
            duplicate_status=duplicate_status,
            duplicate_of_intake_id=duplicate_id,
            inspection=inspection,
            privacy=privacy,
            malware=malware,
            journal_head_sha256=head,
        )
        document = _json_bytes(_accepted_document(receipt)).decode("ascii")
        observed_version = self._update_projection(
            row,
            expected_version=expected_version,
            state=DurableIntakeState.CLEAN_QUARANTINED,
            received_bytes=row["received_bytes"],
            chunk_count=row["chunk_count"],
            content=row["content"],
            sealed_sha256=row["sealed_sha256"],
            failure_code=None,
            result_document=document,
        )
        if observed_version != next_version:
            _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        if duplicate is None:
            values = (row["sealed_sha256"], row["intake_id"], self._command_id.value)
            try:
                self._connection.execute(
                    "INSERT INTO st0406_duplicate_index VALUES (?,?,?,?)",
                    (*values, _row_digest(values)),
                )
            except sqlite3.IntegrityError:
                _fail(ObjectIntakeRuntimeFailureCode.CONCURRENT_MODIFICATION)
        self._insert_result(
            row=row,
            outcome=DurableIntakeState.CLEAN_QUARANTINED,
            document=document,
        )
        self._finalized = True
        return receipt

    def _insert_result(
        self, *, row: sqlite3.Row, outcome: DurableIntakeState, document: str
    ) -> None:
        values = (
            self._command_id.value,
            row["request_digest"],
            row["descriptor_digest"],
            row["authorization_digest"],
            outcome.value,
            document,
            hashlib.sha256(document.encode("ascii")).hexdigest(),
        )
        try:
            self._connection.execute(
                "INSERT INTO st0406_intake_result VALUES (?,?,?,?,?,?,?,?)",
                (*values, _row_digest(values)),
            )
        except sqlite3.IntegrityError:
            _fail(ObjectIntakeRuntimeFailureCode.IDEMPOTENCY_CONFLICT)

    def commit(self) -> None:
        if self._closed or (self._existing is None and not self._finalized):
            _fail(ObjectIntakeRuntimeFailureCode.STORAGE_FAILED)
        committed = False
        commit_started = False
        pending_state = self._anchor.state
        try:
            pending_state = self._repository._validate_all(  # pyright: ignore[reportPrivateUsage]
                self._connection, allow_in_progress=False
            )
            self._repository._require_process_monotonic(  # pyright: ignore[reportPrivateUsage]
                self._connection, state=pending_state
            )
            self._repository._inject_fault(  # pyright: ignore[reportPrivateUsage]
                RecordedIntakeCommitFault.BEFORE_COMMIT
            )
            commit_started = True
            self._connection.commit()
            committed = True
            self._repository._validate_database_identity()  # pyright: ignore[reportPrivateUsage]
            self._repository._pin_process_state(  # pyright: ignore[reportPrivateUsage]
                state=pending_state
            )
            self._repository._inject_fault(  # pyright: ignore[reportPrivateUsage]
                RecordedIntakeCommitFault.AFTER_COMMIT
            )
        except _InjectedCommitFault:
            if not committed:
                self._connection.rollback()
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if committed
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        except ObjectIntakeRuntimeFailure:
            if not committed:
                self._connection.rollback()
            raise
        except sqlite3.Error:
            if not committed:
                try:
                    self._connection.rollback()
                except sqlite3.Error:
                    pass
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        except Exception:
            if not committed:
                self._connection.rollback()
            _fail(
                ObjectIntakeRuntimeFailureCode.STORAGE_COMMIT_UNKNOWN
                if commit_started
                else ObjectIntakeRuntimeFailureCode.STORAGE_FAILED
            )
        finally:
            self._closed = True
            self._repository._close_safely(  # pyright: ignore[reportPrivateUsage]
                self._connection
            )
            self._repository._release_state(  # pyright: ignore[reportPrivateUsage]
                self._anchor
            )

    def rollback(self) -> None:
        if self._closed:
            return
        try:
            self._connection.rollback()
        except sqlite3.Error:
            pass
        finally:
            self._closed = True
            self._repository._close_safely(  # pyright: ignore[reportPrivateUsage]
                self._connection
            )
            self._repository._release_state(  # pyright: ignore[reportPrivateUsage]
                self._anchor
            )


__all__ = [
    "DeterministicContentInspectorV2",
    "DisabledMalwareScannerV2",
    "RecordedIntakeCommitFault",
    "RecordedMalwareScannerV2",
    "RecordedObjectIntakeUnitOfWorkV2",
    "RecordedPrivacyClassifierV2",
    "RecordedSqliteObjectIntakeRepositoryV2",
]
