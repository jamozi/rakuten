"""Owner-private SQLite journal and disabled local notification log for ST-1602."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
from enum import StrEnum
from pathlib import Path
from threading import RLock
from typing import Final, cast, final

from raos.domain.ops.slo_alert_runtime_v2 import (
    AlertDecision,
    AlertLifecycleState,
    AlertPersistCommand,
    AlertPersistReceipt,
    AlertSeverity,
    AlertSnapshot,
    AlertTransitionOutcome,
    DataBlockReason,
    PersistedAlertStep,
    SloAlertFailure,
    SloAlertFailureCode,
    ZERO_SHA256,
    entry_sha256,
    fail,
)
from raos.ports.slo_alert_runtime_v2 import (
    LocalNotificationOutcome,
    LocalNotificationRecord,
    NotificationMode,
)


_SCHEMA_VERSION: Final = 2
_APPLICATION_ID: Final = 1_602_002
_MAX_NOTIFICATION_RECORDS: Final = 10_000
_HEX_CHECK = (
    "length({column}) = 64 AND {column} = lower({column}) "
    "AND {column} NOT GLOB '*[^0-9a-f]*'"
)

_CREATE_METADATA_SQL: Final = f"""
CREATE TABLE alert_metadata (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  schema_version INTEGER NOT NULL CHECK (schema_version = {_SCHEMA_VERSION}),
  entry_count INTEGER NOT NULL CHECK (entry_count >= 0),
  tail_sha256 TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="tail_sha256")})
) STRICT
""".strip()

_CREATE_INSTANCE_SQL: Final = f"""
CREATE TABLE alert_instance (
  instance_key TEXT PRIMARY KEY CHECK (length(instance_key) BETWEEN 11 AND 104),
  alert_id TEXT NOT NULL CHECK (alert_id GLOB 'ALT-[0-9][0-9][0-9]'),
  rule_fingerprint TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="rule_fingerprint")}),
  current_version INTEGER NOT NULL CHECK (current_version >= 1),
  state TEXT NOT NULL CHECK (state IN ('PENDING','FIRING','RESOLVED')),
  pending_since_epoch_seconds INTEGER,
  result_sha256 TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="result_sha256")}),
  result_json BLOB NOT NULL CHECK (length(result_json) BETWEEN 2 AND 262144),
  latest_sequence INTEGER NOT NULL UNIQUE CHECK (latest_sequence >= 1),
  latest_entry_sha256 TEXT NOT NULL UNIQUE CHECK ({_HEX_CHECK.format(column="latest_entry_sha256")}),
  CHECK ((state = 'PENDING') = (pending_since_epoch_seconds IS NOT NULL)),
  CHECK (pending_since_epoch_seconds IS NULL OR pending_since_epoch_seconds >= 0),
  CHECK (substr(instance_key, 1, 7) = alert_id AND substr(instance_key, 8, 1) = ':')
) STRICT
""".strip()

_CREATE_JOURNAL_SQL: Final = f"""
CREATE TABLE alert_journal (
  sequence INTEGER PRIMARY KEY CHECK (sequence >= 1),
  previous_entry_sha256 TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="previous_entry_sha256")}),
  entry_sha256 TEXT NOT NULL UNIQUE CHECK ({_HEX_CHECK.format(column="entry_sha256")}),
  instance_key TEXT NOT NULL,
  alert_id TEXT NOT NULL CHECK (alert_id GLOB 'ALT-[0-9][0-9][0-9]'),
  rule_fingerprint TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="rule_fingerprint")}),
  idempotency_key_sha256 TEXT NOT NULL UNIQUE CHECK ({_HEX_CHECK.format(column="idempotency_key_sha256")}),
  request_sha256 TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="request_sha256")}),
  expected_version INTEGER NOT NULL CHECK (expected_version >= 0),
  current_version INTEGER NOT NULL CHECK (current_version = expected_version + 1),
  state TEXT NOT NULL CHECK (state IN ('PENDING','FIRING','RESOLVED')),
  outcome TEXT NOT NULL CHECK (outcome IN ('DATA_BLOCKED','PENDING','FIRING','RESOLVED','UNCHANGED')),
  reason TEXT NOT NULL CHECK (reason IN ('NONE','MISSING','INVALID','STALE','IMMATURE','ZERO_DENOMINATOR','SOURCE_MISMATCH')),
  pending_since_epoch_seconds INTEGER,
  result_sha256 TEXT NOT NULL CHECK ({_HEX_CHECK.format(column="result_sha256")}),
  result_json BLOB NOT NULL CHECK (length(result_json) BETWEEN 2 AND 262144),
  CHECK ((state = 'PENDING') = (pending_since_epoch_seconds IS NOT NULL)),
  CHECK ((outcome = 'DATA_BLOCKED') = (reason != 'NONE')),
  CHECK (pending_since_epoch_seconds IS NULL OR pending_since_epoch_seconds >= 0),
  CHECK (substr(instance_key, 1, 7) = alert_id AND substr(instance_key, 8, 1) = ':'),
  FOREIGN KEY (instance_key) REFERENCES alert_instance(instance_key)
    ON UPDATE NO ACTION ON DELETE NO ACTION
) STRICT
""".strip()

_EXPECTED_TABLE_SQL: Final = {
    "alert_instance": " ".join(_CREATE_INSTANCE_SQL.split()).lower(),
    "alert_journal": " ".join(_CREATE_JOURNAL_SQL.split()).lower(),
    "alert_metadata": " ".join(_CREATE_METADATA_SQL.split()).lower(),
}
_SELECT_JOURNAL: Final = (
    "SELECT sequence, previous_entry_sha256, entry_sha256, instance_key, "
    "alert_id, rule_fingerprint, idempotency_key_sha256, request_sha256, "
    "expected_version, current_version, state, outcome, reason, "
    "pending_since_epoch_seconds, result_sha256, result_json "
    "FROM alert_journal"
)


class CommitFault(StrEnum):
    NONE = "NONE"
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"
    SQLITE_ERROR_BEFORE_COMMIT = "SQLITE_ERROR_BEFORE_COMMIT"
    SQLITE_ERROR_AFTER_COMMIT = "SQLITE_ERROR_AFTER_COMMIT"


def _normalized_sql(value: object) -> str:
    if type(value) is not str:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
    return " ".join(value.split()).lower()


def _duplicates_rejected(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
        result[key] = value
    return result


def _decision_from_json(content: bytes) -> AlertDecision:
    if type(content) is not bytes or not content or len(content) > 262_144:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    try:
        parsed: object = json.loads(
            content.decode("utf-8", errors="strict"),
            object_pairs_hook=_duplicates_rejected,
            parse_constant=lambda _value: fail(
                SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result"
            ),
        )
    except SloAlertFailure:
        raise
    except UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    if type(parsed) is not dict:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    raw = cast(dict[str, object], parsed)
    if tuple(raw) != (
        "alert_id",
        "dedup_fingerprint",
        "external_action_count",
        "from_state",
        "instance_key",
        "notification_delivery_claim",
        "notification_mode",
        "outcome",
        "owner_id",
        "pending_since_epoch_seconds",
        "reason",
        "rule_fingerprint",
        "runbook_id",
        "severity",
        "state",
    ):
        # canonical JSON sorts keys, so the exact key order is itself bound.
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    try:
        decision = AlertDecision(
            instance_key=cast(str, raw["instance_key"]),
            alert_id=cast(str, raw["alert_id"]),
            severity=AlertSeverity(cast(str, raw["severity"])),
            owner_id=cast(str, raw["owner_id"]),
            runbook_id=cast(str, raw["runbook_id"]),
            rule_fingerprint=cast(str, raw["rule_fingerprint"]),
            dedup_fingerprint=cast(str, raw["dedup_fingerprint"]),
            from_state=AlertLifecycleState(cast(str, raw["from_state"])),
            state=AlertLifecycleState(cast(str, raw["state"])),
            outcome=AlertTransitionOutcome(cast(str, raw["outcome"])),
            reason=DataBlockReason(cast(str, raw["reason"])),
            pending_since_epoch_seconds=cast(
                int | None, raw["pending_since_epoch_seconds"]
            ),
            notification_mode=cast(str, raw["notification_mode"]),
            notification_delivery_claim=cast(bool, raw["notification_delivery_claim"]),
            external_action_count=cast(int, raw["external_action_count"]),
        )
    except KeyError, TypeError, ValueError, SloAlertFailure:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    from raos.domain.ops.slo_alert_runtime_v2 import canonical_bytes

    if canonical_bytes(decision.document()) != content:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    return decision


def _persisted_command(step: PersistedAlertStep) -> AlertPersistCommand:
    decision = _decision_from_json(step.result_json)
    if (
        decision.instance_key != step.instance_key
        or decision.alert_id != step.alert_id
        or decision.rule_fingerprint != step.rule_fingerprint
        or decision.state is not step.state
        or decision.outcome is not step.outcome
        or decision.reason is not step.reason
        or decision.pending_since_epoch_seconds != step.pending_since_epoch_seconds
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.result")
    return AlertPersistCommand(
        instance_key=step.instance_key,
        alert_id=step.alert_id,
        rule_fingerprint=step.rule_fingerprint,
        idempotency_key_sha256=step.idempotency_key_sha256,
        request_sha256=step.request_sha256,
        expected_version=step.expected_version,
        current_version=step.current_version,
        decision=decision,
        result_sha256=step.result_sha256,
        result_json=step.result_json,
    )


def _validate_command_binding(
    persisted: PersistedAlertStep, command: AlertPersistCommand
) -> None:
    if (
        type(persisted) is not PersistedAlertStep
        or type(command) is not AlertPersistCommand
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.binding")
    expected = (
        persisted.instance_key,
        persisted.alert_id,
        persisted.rule_fingerprint,
        persisted.idempotency_key_sha256,
        persisted.request_sha256,
        persisted.expected_version,
        persisted.current_version,
        persisted.state,
        persisted.outcome,
        persisted.reason,
        persisted.pending_since_epoch_seconds,
        persisted.result_sha256,
        persisted.result_json,
    )
    actual = (
        command.instance_key,
        command.alert_id,
        command.rule_fingerprint,
        command.idempotency_key_sha256,
        command.request_sha256,
        command.expected_version,
        command.current_version,
        command.decision.state,
        command.decision.outcome,
        command.decision.reason,
        command.decision.pending_since_epoch_seconds,
        command.result_sha256,
        command.result_json,
    )
    if expected != actual:
        fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.idempotency")


@final
class OwnerPrivateSqliteAlertJournal:
    """Exact-schema append-only alert journal with CAS and hash-chain checks."""

    __slots__ = (
        "_anchor_entry_count",
        "_anchor_tail_sha256",
        "_database_path",
        "_device",
        "_fault",
        "_fault_lock",
        "_fault_used",
        "_inode",
        "_state_lock",
    )

    def __init__(
        self,
        *,
        database_path: object,
        commit_fault: CommitFault = CommitFault.NONE,
    ) -> None:
        if not isinstance(database_path, Path) or type(commit_fault) is not CommitFault:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.path")
        if not database_path.is_absolute() or database_path.name in {"", ".", ".."}:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.path")
        self._database_path = database_path
        self._fault = commit_fault
        self._fault_lock = RLock()
        self._fault_used = False
        self._state_lock = RLock()
        created = self._prepare_file()
        metadata = self._verify_file()
        self._device = metadata.st_dev
        self._inode = metadata.st_ino
        connection = self._connect()
        try:
            if created:
                self._initialize_schema(connection)
            self._verify_schema(connection)
            self._anchor_entry_count, self._anchor_tail_sha256 = self._verified_head(
                connection
            )
        except SloAlertFailure:
            raise
        except sqlite3.Error:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.initialize")
        finally:
            connection.close()
        self._assert_live_file()

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _verify_parent(self) -> None:
        parent = self._database_path.parent
        try:
            metadata = parent.lstat()
            resolved = parent.resolve(strict=True)
        except OSError:
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.parent")
        if (
            resolved != parent
            or not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.getuid()
        ):
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.parent")

    def _prepare_file(self) -> bool:
        self._verify_parent()
        created = False
        try:
            self._database_path.lstat()
        except FileNotFoundError:
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            try:
                descriptor = os.open(self._database_path, flags, 0o600)
                os.close(descriptor)
                created = True
            except OSError:
                fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.file")
        except OSError:
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.file")
        self._verify_file()
        return created

    def _verify_file(self) -> os.stat_result:
        self._verify_parent()
        try:
            metadata = self._database_path.lstat()
        except OSError:
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.file")
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
        ):
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.file")
        return metadata

    def _assert_live_file(self) -> os.stat_result:
        metadata = self._verify_file()
        if (metadata.st_dev, metadata.st_ino) != (self._device, self._inode):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.identity")
        return metadata

    def _connect(self) -> sqlite3.Connection:
        self._assert_live_file()
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=0.0,
                isolation_level=None,
            )
            if connection.execute("PRAGMA trusted_schema = OFF").fetchone() is not None:
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.connection")
            if connection.execute("PRAGMA foreign_keys = ON").fetchone() is not None:
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.connection")
            connection.execute("PRAGMA busy_timeout = 0")
            # DELETE is the SQLite default and is persisted for this owner-private
            # database.  Querying it avoids taking a write lock while a competing
            # compare-and-swap transaction is active.
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()
            connection.execute("PRAGMA synchronous = FULL")
            if (
                journal_mode != ("delete",)
                or connection.execute("PRAGMA trusted_schema").fetchone() != (0,)
                or connection.execute("PRAGMA foreign_keys").fetchone() != (1,)
                or connection.execute("PRAGMA synchronous").fetchone() != (2,)
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.connection")
            self._assert_live_file()
            return connection
        except SloAlertFailure:
            if connection is not None:
                connection.close()
            raise
        except sqlite3.Error:
            if connection is not None:
                connection.close()
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.connect")

    @staticmethod
    def _initialize_schema(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(_CREATE_METADATA_SQL)
            connection.execute(_CREATE_INSTANCE_SQL)
            connection.execute(_CREATE_JOURNAL_SQL)
            connection.execute(f"PRAGMA application_id = {_APPLICATION_ID}")
            connection.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
            connection.execute(
                "INSERT INTO alert_metadata "
                "(singleton, schema_version, entry_count, tail_sha256) "
                "VALUES (1, ?, 0, ?)",
                (_SCHEMA_VERSION, ZERO_SHA256),
            )
            connection.commit()
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.schema")

    @staticmethod
    def _verify_schema(connection: sqlite3.Connection) -> None:
        try:
            if connection.execute("PRAGMA application_id").fetchone() != (
                _APPLICATION_ID,
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
            if connection.execute("PRAGMA user_version").fetchone() != (
                _SCHEMA_VERSION,
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
            rows = connection.execute(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"
            ).fetchall()
            if len(rows) != 3 or any(row[0] != "table" for row in rows):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
            observed = {cast(str, row[1]): _normalized_sql(row[2]) for row in rows}
            if observed != _EXPECTED_TABLE_SQL:
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
            expected_unique: dict[str, frozenset[tuple[str, ...]]] = {
                "alert_metadata": frozenset(),
                "alert_instance": frozenset(
                    {
                        ("instance_key",),
                        ("latest_sequence",),
                        ("latest_entry_sha256",),
                    }
                ),
                "alert_journal": frozenset(
                    {
                        ("entry_sha256",),
                        ("idempotency_key_sha256",),
                    }
                ),
            }
            for table, expected in expected_unique.items():
                indexes: set[tuple[str, ...]] = set()
                for index_row in connection.execute(
                    f"PRAGMA index_list('{table}')"  # noqa: S608 - closed name
                ).fetchall():
                    if index_row[2] != 1 or not cast(str, index_row[1]).startswith(
                        "sqlite_autoindex_"
                    ):
                        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
                    indexes.add(
                        tuple(
                            cast(str, value[2])
                            for value in connection.execute(
                                f"PRAGMA index_info('{cast(str, index_row[1])}')"
                            ).fetchall()
                        )
                    )
                if frozenset(indexes) != expected:
                    fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
            foreign_keys = connection.execute(
                "PRAGMA foreign_key_list('alert_journal')"
            ).fetchall()
            projected = tuple(
                (row[2], row[3], row[4], row[5], row[6]) for row in foreign_keys
            )
            if projected != (
                (
                    "alert_instance",
                    "instance_key",
                    "instance_key",
                    "NO ACTION",
                    "NO ACTION",
                ),
            ) or connection.execute("PRAGMA foreign_keys").fetchone() != (1,):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")
        except SloAlertFailure:
            raise
        except sqlite3.Error:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.schema")

    @classmethod
    def _verified_head(cls, connection: sqlite3.Connection) -> tuple[int, str]:
        entry_count = cls._verify_chain(connection)
        metadata = connection.execute(
            "SELECT entry_count, tail_sha256 FROM alert_metadata WHERE singleton = 1"
        ).fetchone()
        if (
            metadata is None
            or type(metadata[0]) is not int
            or metadata[0] != entry_count
            or type(metadata[1]) is not str
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.metadata")
        return entry_count, metadata[1]

    def _verify_live_anchor(self, connection: sqlite3.Connection) -> tuple[int, str]:
        self._assert_live_file()
        entry_count, tail_sha256 = self._verified_head(connection)
        if entry_count < self._anchor_entry_count:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.rollback")
        if self._anchor_entry_count:
            anchored = connection.execute(
                "SELECT entry_sha256 FROM alert_journal WHERE sequence = ?",
                (self._anchor_entry_count,),
            ).fetchone()
            if anchored != (self._anchor_tail_sha256,):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.rollback")
        elif self._anchor_tail_sha256 != ZERO_SHA256:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.rollback")
        if (
            entry_count == self._anchor_entry_count
            and tail_sha256 != self._anchor_tail_sha256
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.rollback")
        self._assert_live_file()
        self._anchor_entry_count = entry_count
        self._anchor_tail_sha256 = tail_sha256
        return entry_count, tail_sha256

    def _consume_fault(self, fault: CommitFault) -> bool:
        with self._fault_lock:
            if self._fault is not fault or self._fault_used:
                return False
            self._fault_used = True
            return True

    def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        with self._state_lock:
            return self._commit_locked(command)

    def _commit_locked(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        if type(command) is not AlertPersistCommand:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.command")
        if self._consume_fault(CommitFault.BEFORE_COMMIT):
            fail(SloAlertFailureCode.COMMIT_AMBIGUOUS, "journal.commit")
        connection = self._connect()
        connection_closed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._verify_schema(connection)
            self._verify_live_anchor(connection)
            replay = connection.execute(
                f"{_SELECT_JOURNAL} WHERE idempotency_key_sha256 = ?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if replay is not None:
                persisted = self._row_to_persisted(replay)
                _validate_command_binding(persisted, command)
                connection.rollback()
                return persisted.receipt(replayed=True)
            metadata = connection.execute(
                "SELECT schema_version, entry_count, tail_sha256 "
                "FROM alert_metadata WHERE singleton = 1"
            ).fetchone()
            if (
                metadata is None
                or metadata[0] != _SCHEMA_VERSION
                or type(metadata[1]) is not int
                or type(metadata[2]) is not str
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.metadata")
            sequence = metadata[1] + 1
            previous = metadata[2]
            current = connection.execute(
                "SELECT rule_fingerprint, current_version, state, "
                "pending_since_epoch_seconds FROM alert_instance "
                "WHERE instance_key = ?",
                (command.instance_key,),
            ).fetchone()
            if current is None:
                if (
                    command.expected_version != 0
                    or command.decision.from_state is not AlertLifecycleState.RESOLVED
                ):
                    fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.version")
            elif (
                current[0] != command.rule_fingerprint
                or current[1] != command.expected_version
                or current[2] != command.decision.from_state.value
                or current[3]
                != (
                    command.decision.pending_since_epoch_seconds
                    if command.decision.from_state is AlertLifecycleState.PENDING
                    and command.decision.state is AlertLifecycleState.PENDING
                    else current[3]
                )
            ):
                fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.version")
            entry = entry_sha256(
                sequence=sequence,
                previous_entry_sha256=previous,
                command=command,
            )
            values = (
                command.instance_key,
                command.alert_id,
                command.rule_fingerprint,
                command.current_version,
                command.decision.state.value,
                command.decision.pending_since_epoch_seconds,
                command.result_sha256,
                command.result_json,
                sequence,
                entry,
            )
            if current is None:
                connection.execute(
                    "INSERT INTO alert_instance "
                    "(instance_key, alert_id, rule_fingerprint, current_version, "
                    "state, pending_since_epoch_seconds, result_sha256, result_json, "
                    "latest_sequence, latest_entry_sha256) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )
            else:
                updated = connection.execute(
                    "UPDATE alert_instance SET current_version = ?, state = ?, "
                    "pending_since_epoch_seconds = ?, result_sha256 = ?, "
                    "result_json = ?, latest_sequence = ?, latest_entry_sha256 = ? "
                    "WHERE instance_key = ? AND current_version = ?",
                    (
                        command.current_version,
                        command.decision.state.value,
                        command.decision.pending_since_epoch_seconds,
                        command.result_sha256,
                        command.result_json,
                        sequence,
                        entry,
                        command.instance_key,
                        command.expected_version,
                    ),
                ).rowcount
                if updated != 1:
                    fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.version")
            connection.execute(
                "INSERT INTO alert_journal "
                "(sequence, previous_entry_sha256, entry_sha256, instance_key, "
                "alert_id, rule_fingerprint, idempotency_key_sha256, "
                "request_sha256, expected_version, current_version, state, outcome, "
                "reason, pending_since_epoch_seconds, result_sha256, result_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sequence,
                    previous,
                    entry,
                    command.instance_key,
                    command.alert_id,
                    command.rule_fingerprint,
                    command.idempotency_key_sha256,
                    command.request_sha256,
                    command.expected_version,
                    command.current_version,
                    command.decision.state.value,
                    command.decision.outcome.value,
                    command.decision.reason.value,
                    command.decision.pending_since_epoch_seconds,
                    command.result_sha256,
                    command.result_json,
                ),
            )
            updated = connection.execute(
                "UPDATE alert_metadata SET entry_count = ?, tail_sha256 = ? "
                "WHERE singleton = 1 AND entry_count = ? AND tail_sha256 = ?",
                (sequence, entry, sequence - 1, previous),
            ).rowcount
            if updated != 1:
                fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.metadata")
            try:
                if self._consume_fault(CommitFault.SQLITE_ERROR_BEFORE_COMMIT):
                    raise sqlite3.OperationalError("simulated commit failure")
                connection.commit()
                if self._consume_fault(CommitFault.SQLITE_ERROR_AFTER_COMMIT):
                    raise sqlite3.OperationalError("simulated commit failure")
            except sqlite3.Error:
                connection.close()
                connection_closed = True
                return self._recover_commit_error_locked(command)
            self._assert_live_file()
            connection.execute("BEGIN")
            self._verify_schema(connection)
            self._verify_live_anchor(connection)
            connection.rollback()
            receipt = AlertPersistReceipt(
                command.instance_key,
                command.current_version,
                command.request_sha256,
                command.result_sha256,
                sequence,
                previous,
                entry,
                False,
            )
            if self._consume_fault(CommitFault.AFTER_COMMIT):
                fail(SloAlertFailureCode.COMMIT_AMBIGUOUS, "journal.commit")
            return receipt
        except SloAlertFailure:
            if not connection_closed and connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.IntegrityError:
            if not connection_closed and connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.commit")
        except sqlite3.OperationalError:
            if not connection_closed and connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.commit")
        except sqlite3.Error:
            if not connection_closed and connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.commit")
        finally:
            if not connection_closed:
                connection.close()

    def _recover_commit_error_locked(
        self, command: AlertPersistCommand
    ) -> AlertPersistReceipt:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._verify_schema(connection)
            self._verify_live_anchor(connection)
            row = connection.execute(
                f"{_SELECT_JOURNAL} WHERE idempotency_key_sha256 = ?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if row is None:
                fail(SloAlertFailureCode.COMMIT_UNKNOWN, "journal.commit")
            persisted = self._row_to_persisted(row)
            _validate_command_binding(persisted, command)
            receipt = persisted.receipt(replayed=True)
            self._verify_live_anchor(connection)
            connection.rollback()
            return receipt
        except SloAlertFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.COMMIT_UNKNOWN, "journal.commit")
        finally:
            connection.close()

    def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        with self._state_lock:
            return self._recover_exact_locked(command)

    def _recover_exact_locked(
        self, command: AlertPersistCommand
    ) -> AlertPersistReceipt:
        if type(command) is not AlertPersistCommand:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.command")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._verify_schema(connection)
            self._verify_live_anchor(connection)
            row = connection.execute(
                f"{_SELECT_JOURNAL} WHERE idempotency_key_sha256 = ?",
                (command.idempotency_key_sha256,),
            ).fetchone()
            if row is None:
                fail(SloAlertFailureCode.RECOVERY_NOT_FOUND, "journal.recovery")
            persisted = self._row_to_persisted(row)
            _validate_command_binding(persisted, command)
            receipt = persisted.receipt(replayed=True)
            self._verify_live_anchor(connection)
            connection.rollback()
            return receipt
        except SloAlertFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.recovery")
        finally:
            connection.close()

    def load_latest(self, instance_key: str) -> AlertSnapshot | None:
        with self._state_lock:
            return self._load_latest_locked(instance_key)

    def _load_latest_locked(self, instance_key: str) -> AlertSnapshot | None:
        if type(instance_key) is not str or ":" not in instance_key:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "journal.instance")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            self._verify_schema(connection)
            self._verify_live_anchor(connection)
            row = connection.execute(
                f"{_SELECT_JOURNAL} WHERE instance_key = ? AND sequence = "
                "(SELECT latest_sequence FROM alert_instance WHERE instance_key = ?)",
                (instance_key, instance_key),
            ).fetchone()
            result = None if row is None else self._row_to_persisted(row).snapshot()
            self._verify_live_anchor(connection)
            connection.rollback()
            return result
        except SloAlertFailure:
            if connection.in_transaction:
                connection.rollback()
            raise
        except sqlite3.Error:
            if connection.in_transaction:
                connection.rollback()
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.load")
        finally:
            connection.close()

    def verify_integrity(self) -> int:
        with self._state_lock:
            connection = self._connect()
            try:
                connection.execute("BEGIN")
                self._verify_schema(connection)
                entry_count, _tail = self._verify_live_anchor(connection)
                connection.rollback()
                return entry_count
            except SloAlertFailure:
                if connection.in_transaction:
                    connection.rollback()
                raise
            except sqlite3.Error:
                if connection.in_transaction:
                    connection.rollback()
                fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.verify")
            finally:
                connection.close()

    @staticmethod
    def _row_to_persisted(row: tuple[object, ...]) -> PersistedAlertStep:
        if len(row) != 16:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.row")
        try:
            persisted = PersistedAlertStep(
                sequence=cast(int, row[0]),
                previous_entry_sha256=cast(str, row[1]),
                entry_sha256=cast(str, row[2]),
                instance_key=cast(str, row[3]),
                alert_id=cast(str, row[4]),
                rule_fingerprint=cast(str, row[5]),
                idempotency_key_sha256=cast(str, row[6]),
                request_sha256=cast(str, row[7]),
                expected_version=cast(int, row[8]),
                current_version=cast(int, row[9]),
                state=AlertLifecycleState(cast(str, row[10])),
                outcome=AlertTransitionOutcome(cast(str, row[11])),
                reason=DataBlockReason(cast(str, row[12])),
                pending_since_epoch_seconds=cast(int | None, row[13]),
                result_sha256=cast(str, row[14]),
                result_json=bytes(cast(bytes, row[15])),
            )
            _persisted_command(persisted)
            return persisted
        except SloAlertFailure:
            raise
        except TypeError, ValueError:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.row")

    @classmethod
    def _verify_chain(cls, connection: sqlite3.Connection) -> int:
        metadata = connection.execute(
            "SELECT schema_version, entry_count, tail_sha256 "
            "FROM alert_metadata WHERE singleton = 1"
        ).fetchone()
        if (
            metadata is None
            or metadata[0] != _SCHEMA_VERSION
            or type(metadata[1]) is not int
            or type(metadata[2]) is not str
        ):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.metadata")
        rows = connection.execute(f"{_SELECT_JOURNAL} ORDER BY sequence").fetchall()
        if len(rows) != metadata[1]:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.chain")
        previous = ZERO_SHA256
        latest: dict[str, PersistedAlertStep] = {}
        for expected_sequence, row in enumerate(rows, start=1):
            persisted = cls._row_to_persisted(row)
            command = _persisted_command(persisted)
            if (
                persisted.sequence != expected_sequence
                or persisted.previous_entry_sha256 != previous
                or persisted.entry_sha256
                != entry_sha256(
                    sequence=persisted.sequence,
                    previous_entry_sha256=persisted.previous_entry_sha256,
                    command=command,
                )
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.chain")
            prior = latest.get(persisted.instance_key)
            decision = command.decision
            if prior is None:
                if (
                    persisted.expected_version != 0
                    or decision.from_state is not AlertLifecycleState.RESOLVED
                ):
                    fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.chain")
            elif (
                persisted.expected_version != prior.current_version
                or persisted.rule_fingerprint != prior.rule_fingerprint
                or decision.from_state is not prior.state
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.chain")
            latest[persisted.instance_key] = persisted
            previous = persisted.entry_sha256
        if previous != metadata[2]:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.chain")
        current_rows = connection.execute(
            "SELECT instance_key, alert_id, rule_fingerprint, current_version, "
            "state, pending_since_epoch_seconds, result_sha256, result_json, "
            "latest_sequence, latest_entry_sha256 FROM alert_instance "
            "ORDER BY instance_key"
        ).fetchall()
        if len(current_rows) != len(latest):
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.current")
        for row in current_rows:
            current = latest.get(cast(str, row[0]))
            if current is None or (
                row[1] != current.alert_id
                or row[2] != current.rule_fingerprint
                or row[3] != current.current_version
                or row[4] != current.state.value
                or row[5] != current.pending_since_epoch_seconds
                or row[6] != current.result_sha256
                or bytes(cast(bytes, row[7])) != current.result_json
                or row[8] != current.sequence
                or row[9] != current.entry_sha256
            ):
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.current")
        return len(rows)


def _copy_notification_record(record: object) -> LocalNotificationRecord:
    if type(record) is not LocalNotificationRecord:
        fail(SloAlertFailureCode.INVALID_ARGUMENT, "notification.record")
    source = record
    try:
        return LocalNotificationRecord(
            notification_fingerprint=source.notification_fingerprint,
            dedup_fingerprint=source.dedup_fingerprint,
            instance_key=source.instance_key,
            alert_id=source.alert_id,
            severity=source.severity,
            owner_id=source.owner_id,
            runbook_id=source.runbook_id,
            state=source.state,
            outcome=source.outcome,
            result_sha256=source.result_sha256,
            external_action_count=source.external_action_count,
            delivery_claim=source.delivery_claim,
        )
    except SloAlertFailure:
        fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.record")


@final
class DisabledRecordedAlertNotificationAdapter:
    """Bounded local log; notification delivery is always disabled."""

    __slots__ = ("_capacity", "_lock", "_records")

    def __init__(self, *, capacity: int) -> None:
        if type(capacity) is not int or not 1 <= capacity <= _MAX_NOTIFICATION_RECORDS:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "notification.capacity")
        self._capacity = capacity
        self._lock = RLock()
        self._records: tuple[LocalNotificationRecord, ...] = ()

    @property
    def mode(self) -> NotificationMode:
        return NotificationMode.LOCAL_LOG_ONLY_DISABLED

    @property
    def external_action_count(self) -> int:
        return 0

    def record_local(self, record: LocalNotificationRecord) -> LocalNotificationOutcome:
        validated = _copy_notification_record(record)
        with self._lock:
            if any(
                existing.notification_fingerprint == validated.notification_fingerprint
                for existing in self._records
            ):
                return LocalNotificationOutcome.REPLAYED_LOCAL_ONLY
            if len(self._records) >= self._capacity:
                return LocalNotificationOutcome.LOCAL_LOG_FAILED
            self._records = (*self._records, validated)
            return LocalNotificationOutcome.RECORDED_LOCAL_ONLY

    def snapshot(self) -> tuple[LocalNotificationRecord, ...]:
        with self._lock:
            return tuple(_copy_notification_record(record) for record in self._records)


__all__ = [
    "CommitFault",
    "DisabledRecordedAlertNotificationAdapter",
    "OwnerPrivateSqliteAlertJournal",
]
