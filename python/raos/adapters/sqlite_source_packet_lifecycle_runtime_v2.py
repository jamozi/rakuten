"""Owner-private, created-only SQLite journal for ST-0604 V2."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
from typing import cast, final
from uuid import UUID

from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    SOURCE_PACKET_GENESIS_SHA256_V2,
    SOURCE_PACKET_SCHEMA_VERSION_V2,
    SourcePacketCommandIdV2,
    SourcePacketCommandKindV2,
    SourcePacketCommandResultV2,
    SourcePacketCommandV2,
    SourcePacketFailureCodeV2,
    SourcePacketFailureV2,
    SourcePacketReplayStatusV2,
    SourcePacketStateV2,
    apply_source_packet_command_v2,
    canonical_json_bytes_v2,
    canonical_sha256_v2,
    command_from_mapping_v2,
    command_mapping_v2,
    fail_source_packet_v2,
    generation_input_mapping_v2,
    result_from_mapping_v2,
    result_mapping_v2,
    source_packet_chain_hash_v2,
    utc_text_v2,
)


_DATABASE_NAME = "source-packet-runtime-v2.sqlite3"
_USER_VERSION = 60402
_MAX_JSON_BYTES = 8 * 1024 * 1024
_MAX_JSON_DEPTH = 64
_MAX_JSON_NODES = 100_000
_ALLOWED_ENVIRONMENTS = {RuntimeEnvironment.ENV_DEV, RuntimeEnvironment.CI}
_TABLES = frozenset(
    {
        "source_packet_metadata",
        "source_packet_packet_registry",
        "source_packet_version_registry",
        "source_packet_command_journal",
        "source_packet_lifecycle_journal",
        "source_packet_review_journal",
        "source_packet_lock_journal",
        "source_packet_audit_journal",
    }
)
_EXPECTED_COLUMNS = {
    "source_packet_metadata": (
        "singleton",
        "schema_version",
        "database_identity",
        "schema_sha256",
    ),
    "source_packet_packet_registry": (
        "packet_id",
        "site_id",
        "article_plan_id",
        "review_assignment_id",
        "creator_actor_fingerprint",
        "created_at",
        "record_sha256",
    ),
    "source_packet_version_registry": (
        "packet_id",
        "version_number",
        "version_id",
        "content_sha256",
        "content_document",
        "editor_actor_fingerprint",
        "created_at",
        "record_sha256",
    ),
    "source_packet_command_journal": (
        "command_id",
        "sequence",
        "request_sha256",
        "packet_id",
        "command_kind",
        "command_document",
        "result_document",
        "state_sha256",
        "previous_chain_hash",
        "chain_hash",
        "committed_at",
        "record_sha256",
    ),
    "source_packet_lifecycle_journal": (
        "command_sequence",
        "packet_id",
        "version_number",
        "event_kind",
        "from_status",
        "to_status",
        "occurred_at",
        "record_sha256",
    ),
    "source_packet_review_journal": (
        "command_sequence",
        "packet_id",
        "version_id",
        "version_number",
        "decision",
        "content_sha256",
        "fact_membership_sha256",
        "conflict_scan_sha256",
        "authorization_sha256",
        "binding_sha256",
        "reviewed_at",
        "record_sha256",
    ),
    "source_packet_lock_journal": (
        "command_sequence",
        "packet_id",
        "version_id",
        "version_number",
        "content_sha256",
        "approval_binding_sha256",
        "lock_sha256",
        "locked_at",
        "record_sha256",
    ),
    "source_packet_audit_journal": (
        "sequence",
        "command_id_fingerprint",
        "request_sha256",
        "packet_id",
        "event_kind",
        "actor_fingerprint",
        "state_sha256",
        "previous_chain_hash",
        "chain_hash",
        "occurred_at",
        "record_sha256",
    ),
}

_SCHEMA_SQL = """
CREATE TABLE source_packet_metadata (
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  schema_version TEXT NOT NULL,
  database_identity TEXT NOT NULL CHECK(length(database_identity)=64),
  schema_sha256 TEXT NOT NULL CHECK(length(schema_sha256)=64)
) STRICT;
CREATE TABLE source_packet_packet_registry (
  packet_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  article_plan_id TEXT NOT NULL,
  review_assignment_id TEXT NOT NULL,
  creator_actor_fingerprint TEXT NOT NULL CHECK(length(creator_actor_fingerprint)=64),
  created_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
CREATE TABLE source_packet_version_registry (
  packet_id TEXT NOT NULL REFERENCES source_packet_packet_registry(packet_id),
  version_number INTEGER NOT NULL CHECK(version_number BETWEEN 1 AND 64),
  version_id TEXT NOT NULL UNIQUE,
  content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
  content_document TEXT NOT NULL,
  editor_actor_fingerprint TEXT NOT NULL CHECK(length(editor_actor_fingerprint)=64),
  created_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64),
  PRIMARY KEY(packet_id, version_number)
) STRICT;
CREATE TABLE source_packet_command_journal (
  command_id TEXT PRIMARY KEY,
  sequence INTEGER NOT NULL UNIQUE CHECK(sequence > 0),
  request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
  packet_id TEXT NOT NULL,
  command_kind TEXT NOT NULL,
  command_document TEXT NOT NULL,
  result_document TEXT NOT NULL,
  state_sha256 TEXT NOT NULL CHECK(length(state_sha256)=64),
  previous_chain_hash TEXT NOT NULL CHECK(length(previous_chain_hash)=64),
  chain_hash TEXT NOT NULL CHECK(length(chain_hash)=64),
  committed_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
CREATE TABLE source_packet_lifecycle_journal (
  command_sequence INTEGER PRIMARY KEY REFERENCES source_packet_command_journal(sequence),
  packet_id TEXT NOT NULL,
  version_number INTEGER,
  event_kind TEXT NOT NULL,
  from_status TEXT,
  to_status TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
CREATE TABLE source_packet_review_journal (
  command_sequence INTEGER PRIMARY KEY REFERENCES source_packet_command_journal(sequence),
  packet_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  decision TEXT NOT NULL,
  content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
  fact_membership_sha256 TEXT NOT NULL CHECK(length(fact_membership_sha256)=64),
  conflict_scan_sha256 TEXT NOT NULL CHECK(length(conflict_scan_sha256)=64),
  authorization_sha256 TEXT NOT NULL CHECK(length(authorization_sha256)=64),
  binding_sha256 TEXT NOT NULL CHECK(length(binding_sha256)=64),
  reviewed_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
CREATE TABLE source_packet_lock_journal (
  command_sequence INTEGER PRIMARY KEY REFERENCES source_packet_command_journal(sequence),
  packet_id TEXT NOT NULL,
  version_id TEXT NOT NULL,
  version_number INTEGER NOT NULL,
  content_sha256 TEXT NOT NULL CHECK(length(content_sha256)=64),
  approval_binding_sha256 TEXT NOT NULL CHECK(length(approval_binding_sha256)=64),
  lock_sha256 TEXT NOT NULL CHECK(length(lock_sha256)=64),
  locked_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
CREATE TABLE source_packet_audit_journal (
  sequence INTEGER PRIMARY KEY REFERENCES source_packet_command_journal(sequence),
  command_id_fingerprint TEXT NOT NULL CHECK(length(command_id_fingerprint)=64),
  request_sha256 TEXT NOT NULL CHECK(length(request_sha256)=64),
  packet_id TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  actor_fingerprint TEXT NOT NULL CHECK(length(actor_fingerprint)=64),
  state_sha256 TEXT NOT NULL CHECK(length(state_sha256)=64),
  previous_chain_hash TEXT NOT NULL CHECK(length(previous_chain_hash)=64),
  chain_hash TEXT NOT NULL CHECK(length(chain_hash)=64),
  occurred_at TEXT NOT NULL,
  record_sha256 TEXT NOT NULL CHECK(length(record_sha256)=64)
) STRICT;
"""


class SourcePacketSqliteCommitFaultV2(str, Enum):
    BEFORE_COMMIT = "BEFORE_COMMIT"
    AFTER_COMMIT = "AFTER_COMMIT"


def _schema_sha256() -> str:
    material = _SCHEMA_SQL + "".join(
        _immutable_trigger(table) for table in sorted(_TABLES)
    )
    return hashlib.sha256(f"{_USER_VERSION}\n{material}".encode("utf-8")).hexdigest()


def _canonical_text(value: object) -> str:
    return canonical_json_bytes_v2(value).decode("ascii")


def _reject_json_constant(_value: str) -> None:
    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)


def _validate_json_tree(value: object) -> None:
    stack: list[tuple[object, int]] = [(value, 1)]
    count = 0
    while stack:
        current, depth = stack.pop()
        count += 1
        if depth > _MAX_JSON_DEPTH or count > _MAX_JSON_NODES:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if type(current) is dict:
            stack.extend(
                (item, depth + 1) for item in cast(dict[str, object], current).values()
            )
        elif type(current) is list:
            stack.extend((item, depth + 1) for item in cast(list[object], current))
        elif current is not None and type(current) not in {str, int, bool}:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)


def _decode(text: object) -> dict[str, object]:
    if type(text) is not str or len(text.encode("utf-8")) > _MAX_JSON_BYTES:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, value in items:
            if key in output:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            output[key] = value
        return output

    try:
        loaded: object = json.loads(
            text,
            object_pairs_hook=pairs,
            parse_constant=_reject_json_constant,
        )
    except SourcePacketFailureV2:
        raise
    except Exception:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    _validate_json_tree(loaded)
    if type(loaded) is not dict:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    value = cast(dict[str, object], loaded)
    if _canonical_text(value) != text:
        fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
    return value


def _record_sha(value: object) -> str:
    return canonical_sha256_v2(value)


def _immutable_trigger(table: str) -> str:
    return f"""
CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""


def _schema_inventory(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple(row)
        for row in connection.execute(
            "SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
        ).fetchall()
    )


def _expected_schema_inventory() -> tuple[tuple[object, ...], ...]:
    connection = sqlite3.connect(":memory:", isolation_level=None)
    try:
        connection.executescript(_SCHEMA_SQL)
        for table in sorted(_TABLES):
            connection.executescript(_immutable_trigger(table))
        return _schema_inventory(connection)
    finally:
        connection.close()


_EXPECTED_SCHEMA_INVENTORY = _expected_schema_inventory()


def _validate_root_path(root: object) -> Path:
    if (
        type(root) is not type(Path())
        or not root.is_absolute()
        or ".." in root.parts
        or Path(os.path.abspath(root)) != root
    ):
        fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
    current = Path(root.anchor)
    for component in root.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            continue
        except OSError:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        if stat.S_ISLNK(metadata.st_mode):
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
    return root


def _safe_close(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        connection.close()
    except Exception:
        pass


@final
class OwnerPrivateSqliteSourcePacketStoreV2:
    """Append-only local journal with exact CAS and in-process prefix anchor.

    The prefix anchor detects rollback/replacement while this object remains
    alive. Across process restarts there is no external monotonic anchor, so a
    privileged rollback of both database and filesystem metadata cannot be
    distinguished. That limitation is intentionally documented rather than
    represented as Production integrity.
    """

    __slots__ = (
        "_database_identity",
        "_database_path",
        "_file_identity",
        "_faults",
        "_prefix_chain_hash",
        "_prefix_sequence",
        "_root",
    )

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        root: object,
        commit_faults: tuple[SourcePacketSqliteCommitFaultV2, ...] = (),
    ) -> None:
        if (
            type(environment) is not RuntimeEnvironment
            or environment not in _ALLOWED_ENVIRONMENTS
            or not isinstance(root, Path)
            or type(commit_faults) is not tuple
            or any(
                type(item) is not SourcePacketSqliteCommitFaultV2
                for item in commit_faults
            )
        ):
            fail_source_packet_v2()
        self._root = _validate_root_path(root)
        self._faults = list(commit_faults)
        self._prepare_root()
        self._database_path = self._root / _DATABASE_NAME
        created = self._create_only_if_absent()
        self._file_identity: tuple[int, int] | None = self._assert_owner_private_file()
        if created:
            self._initialize()
        connection = self._connect()
        try:
            self._validate_all(connection)
            identity = connection.execute(
                "SELECT database_identity FROM source_packet_metadata WHERE singleton=1"
            ).fetchone()
            if identity is None or type(identity[0]) is not str:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            self._database_identity = identity[0]
            last = connection.execute(
                "SELECT sequence,chain_hash FROM source_packet_command_journal ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            self._prefix_sequence = 0 if last is None else cast(int, last[0])
            self._prefix_chain_hash = (
                SOURCE_PACKET_GENESIS_SHA256_V2 if last is None else cast(str, last[1])
            )
        finally:
            _safe_close(connection)

    @property
    def action_count(self) -> int:
        return 0

    @property
    def database_path(self) -> Path:
        return self._database_path

    def _prepare_root(self) -> None:
        try:
            self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
            _validate_root_path(self._root)
            metadata = self._root.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        except OSError:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)

    def _create_only_if_absent(self) -> bool:
        root_descriptor = -1
        descriptor = -1
        try:
            nofollow = getattr(os, "O_NOFOLLOW", 0)
            root_descriptor = os.open(
                self._root,
                os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | nofollow,
            )
            try:
                descriptor = os.open(
                    _DATABASE_NAME,
                    os.O_CREAT | os.O_EXCL | os.O_RDWR | os.O_CLOEXEC | nofollow,
                    0o600,
                    dir_fd=root_descriptor,
                )
            except FileExistsError:
                return False
            opened = os.fstat(descriptor)
            named = os.stat(
                _DATABASE_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            os.fsync(root_descriptor)
        except SourcePacketFailureV2:
            raise
        except OSError:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if root_descriptor >= 0:
                os.close(root_descriptor)
        return True

    def _assert_owner_private_file(self) -> tuple[int, int]:
        try:
            info = self._database_path.lstat()
        except OSError:
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_nlink != 1
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        identity = (info.st_dev, info.st_ino)
        pinned = getattr(self, "_file_identity", None)
        if pinned is not None and identity != pinned:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        return identity

    def _connect(self) -> sqlite3.Connection:
        self._assert_owner_private_file()
        try:
            connection = sqlite3.connect(
                self._database_path,
                timeout=0,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA recursive_triggers=ON")
            connection.execute("PRAGMA busy_timeout=0")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA secure_delete=ON")
            connection.execute("PRAGMA temp_store=MEMORY")
            mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
            self._assert_owner_private_file()
        except sqlite3.Error:
            _safe_close(locals().get("connection"))
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        if mode is None or str(mode[0]).lower() != "delete":
            _safe_close(connection)
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        identity = os.urandom(32).hex()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.executescript(_SCHEMA_SQL)
            for table in sorted(_TABLES):
                connection.executescript(_immutable_trigger(table))
            connection.execute(f"PRAGMA user_version={_USER_VERSION}")
            connection.execute(
                "INSERT INTO source_packet_metadata VALUES (1,?,?,?)",
                (SOURCE_PACKET_SCHEMA_VERSION_V2, identity, _schema_sha256()),
            )
            connection.commit()
        except sqlite3.Error:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        finally:
            _safe_close(connection)

    def _assert_prefix(self, connection: sqlite3.Connection) -> None:
        row = connection.execute(
            "SELECT database_identity FROM source_packet_metadata WHERE singleton=1"
        ).fetchone()
        if row is None or row[0] != self._database_identity:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        if self._prefix_sequence > 0:
            anchor = connection.execute(
                "SELECT chain_hash FROM source_packet_command_journal WHERE sequence=?",
                (self._prefix_sequence,),
            ).fetchone()
            if anchor is None or anchor[0] != self._prefix_chain_hash:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        latest = connection.execute(
            "SELECT sequence,chain_hash FROM source_packet_command_journal "
            "ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        next_sequence = 0 if latest is None else latest[0]
        next_chain_hash = (
            SOURCE_PACKET_GENESIS_SHA256_V2 if latest is None else latest[1]
        )
        if (
            type(next_sequence) is not int
            or type(next_chain_hash) is not str
            or next_sequence < self._prefix_sequence
            or (
                next_sequence == self._prefix_sequence
                and next_chain_hash != self._prefix_chain_hash
            )
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        # Every completely verified prefix observed by this process becomes a
        # new rollback floor, including prefixes written by a peer store.
        self._prefix_sequence = next_sequence
        self._prefix_chain_hash = next_chain_hash

    @staticmethod
    def _journal_status(
        previous: SourcePacketStateV2 | None,
        current: SourcePacketStateV2,
    ) -> tuple[int | None, str | None, str]:
        prior_version = None if previous is None else previous.current_version
        next_version = current.current_version
        return (
            None if next_version is None else next_version.version_number,
            None if prior_version is None else prior_version.status.value,
            current.packet_status.value,
        )

    @staticmethod
    def _packet_record(state: SourcePacketStateV2) -> dict[str, object]:
        return {
            "article_plan_id": str(state.article_plan_id),
            "created_at": utc_text_v2(state.created_at),
            "creator_actor_fingerprint": state.creator_actor_fingerprint,
            "packet_id": str(state.packet_id),
            "review_assignment_id": str(state.review_assignment_id),
            "site_id": str(state.site_id),
        }

    @staticmethod
    def _version_record(state: SourcePacketStateV2) -> dict[str, object]:
        version = state.current_version
        if version is None:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        return {
            "content_document": _canonical_text(version.content.canonical_material),
            "content_sha256": version.content_sha256,
            "created_at": utc_text_v2(version.created_at),
            "editor_actor_fingerprint": version.editor_actor_fingerprint,
            "packet_id": str(state.packet_id),
            "version_id": str(version.version_id),
            "version_number": version.version_number,
        }

    @staticmethod
    def _lifecycle_record(
        *,
        sequence: int,
        command: SourcePacketCommandV2,
        previous: SourcePacketStateV2 | None,
        state: SourcePacketStateV2,
    ) -> dict[str, object]:
        version_number, prior, current = (
            OwnerPrivateSqliteSourcePacketStoreV2._journal_status(previous, state)
        )
        return {
            "command_sequence": sequence,
            "event_kind": command.kind.value,
            "from_status": prior,
            "occurred_at": utc_text_v2(command.occurred_at),
            "packet_id": str(command.packet_id),
            "to_status": current,
            "version_number": version_number,
        }

    def _load_state_unchecked(
        self, connection: sqlite3.Connection, packet_id: UUID
    ) -> SourcePacketStateV2 | None:
        row = connection.execute(
            "SELECT result_document FROM source_packet_command_journal WHERE packet_id=? ORDER BY sequence DESC LIMIT 1",
            (str(packet_id),),
        ).fetchone()
        if row is None:
            return None
        return result_from_mapping_v2(_decode(row[0])).state

    def _load_command_unchecked(
        self,
        connection: sqlite3.Connection,
        command_id: SourcePacketCommandIdV2,
    ) -> tuple[str, SourcePacketCommandResultV2] | None:
        row = connection.execute(
            "SELECT request_sha256,result_document FROM source_packet_command_journal WHERE command_id=?",
            (command_id.value,),
        ).fetchone()
        if row is None:
            return None
        return cast(str, row[0]), result_from_mapping_v2(_decode(row[1]))

    def execute(self, command: SourcePacketCommandV2) -> SourcePacketCommandResultV2:
        if type(command) is not SourcePacketCommandV2:
            fail_source_packet_v2()
        # Canonical copy prevents hostile mutation of nested frozen values.
        command = command_from_mapping_v2(command_mapping_v2(command))
        connection = self._connect()
        committed = False
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._validate_all(connection)
            self._assert_prefix(connection)
            existing = self._load_command_unchecked(connection, command.command_id)
            if existing is not None:
                if existing[0] != command.request_sha256:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.COMMAND_CONFLICT)
                connection.rollback()
                return replace(
                    existing[1], replay_status=SourcePacketReplayStatusV2.REPLAYED
                )
            previous = self._load_state_unchecked(connection, command.packet_id)
            state, generation = apply_source_packet_command_v2(previous, command)
            last = connection.execute(
                "SELECT sequence,chain_hash FROM source_packet_command_journal ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = 1 if last is None else cast(int, last[0]) + 1
            previous_chain = (
                SOURCE_PACKET_GENESIS_SHA256_V2 if last is None else cast(str, last[1])
            )
            generation_sha = (
                None
                if generation is None
                else canonical_sha256_v2(generation_input_mapping_v2(generation))
            )
            chain = source_packet_chain_hash_v2(
                previous_chain_hash=previous_chain,
                sequence=sequence,
                command_sha256=command.request_sha256,
                state_sha256=state.state_sha256,
                generation_input_sha256=generation_sha,
                committed_at=command.occurred_at,
            )
            result = SourcePacketCommandResultV2(
                command=command,
                state=state,
                generation_input=generation,
                sequence=sequence,
                previous_chain_hash=previous_chain,
                chain_hash=chain,
                committed_at=command.occurred_at,
                replay_status=SourcePacketReplayStatusV2.COMMITTED,
            )
            if command.kind is SourcePacketCommandKindV2.CREATE_PACKET:
                packet = self._packet_record(state)
                connection.execute(
                    "INSERT INTO source_packet_packet_registry VALUES (?,?,?,?,?,?,?)",
                    (
                        packet["packet_id"],
                        packet["site_id"],
                        packet["article_plan_id"],
                        packet["review_assignment_id"],
                        packet["creator_actor_fingerprint"],
                        packet["created_at"],
                        _record_sha(packet),
                    ),
                )
            if command.kind is SourcePacketCommandKindV2.CREATE_VERSION:
                version = self._version_record(state)
                connection.execute(
                    "INSERT INTO source_packet_version_registry VALUES (?,?,?,?,?,?,?,?)",
                    (
                        version["packet_id"],
                        version["version_number"],
                        version["version_id"],
                        version["content_sha256"],
                        version["content_document"],
                        version["editor_actor_fingerprint"],
                        version["created_at"],
                        _record_sha(version),
                    ),
                )
            command_document = _canonical_text(command_mapping_v2(command))
            result_document = _canonical_text(result_mapping_v2(result))
            command_record = {
                "chain_hash": chain,
                "command_document": command_document,
                "command_id": command.command_id.value,
                "command_kind": command.kind.value,
                "committed_at": utc_text_v2(command.occurred_at),
                "packet_id": str(command.packet_id),
                "previous_chain_hash": previous_chain,
                "request_sha256": command.request_sha256,
                "result_document": result_document,
                "sequence": sequence,
                "state_sha256": state.state_sha256,
            }
            connection.execute(
                "INSERT INTO source_packet_command_journal VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    command_record["command_id"],
                    command_record["sequence"],
                    command_record["request_sha256"],
                    command_record["packet_id"],
                    command_record["command_kind"],
                    command_record["command_document"],
                    command_record["result_document"],
                    command_record["state_sha256"],
                    command_record["previous_chain_hash"],
                    command_record["chain_hash"],
                    command_record["committed_at"],
                    _record_sha(command_record),
                ),
            )
            lifecycle = self._lifecycle_record(
                sequence=sequence, command=command, previous=previous, state=state
            )
            connection.execute(
                "INSERT INTO source_packet_lifecycle_journal VALUES (?,?,?,?,?,?,?,?)",
                (
                    lifecycle["command_sequence"],
                    lifecycle["packet_id"],
                    lifecycle["version_number"],
                    lifecycle["event_kind"],
                    lifecycle["from_status"],
                    lifecycle["to_status"],
                    lifecycle["occurred_at"],
                    _record_sha(lifecycle),
                ),
            )
            if command.kind is SourcePacketCommandKindV2.RECORD_REVIEW:
                current = state.current_version
                if current is None or current.review is None:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
                review = current.review
                row = {
                    "authorization_sha256": review.authorization.sha256,
                    "binding_sha256": review.binding_sha256,
                    "command_sequence": sequence,
                    "conflict_scan_sha256": review.conflict_scan_sha256,
                    "content_sha256": review.content_sha256,
                    "decision": review.decision.value,
                    "fact_membership_sha256": review.fact_membership_sha256,
                    "packet_id": str(review.packet_id),
                    "reviewed_at": utc_text_v2(review.reviewed_at),
                    "version_id": str(review.version_id),
                    "version_number": review.version_number,
                }
                # SQL column order is explicit and differs from canonical key order.
                connection.execute(
                    "INSERT INTO source_packet_review_journal VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        sequence,
                        str(review.packet_id),
                        str(review.version_id),
                        review.version_number,
                        review.decision.value,
                        review.content_sha256,
                        review.fact_membership_sha256,
                        review.conflict_scan_sha256,
                        review.authorization.sha256,
                        review.binding_sha256,
                        utc_text_v2(review.reviewed_at),
                        _record_sha(row),
                    ),
                )
            if command.kind is SourcePacketCommandKindV2.LOCK_VERSION:
                current = state.current_version
                if current is None or current.lock is None:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
                lock = current.lock
                row = {
                    "approval_binding_sha256": lock.approval_binding_sha256,
                    "command_sequence": sequence,
                    "content_sha256": lock.content_sha256,
                    "lock_sha256": lock.lock_sha256,
                    "locked_at": utc_text_v2(lock.locked_at),
                    "packet_id": str(lock.packet_id),
                    "version_id": str(lock.version_id),
                    "version_number": lock.version_number,
                }
                connection.execute(
                    "INSERT INTO source_packet_lock_journal VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        sequence,
                        str(lock.packet_id),
                        str(lock.version_id),
                        lock.version_number,
                        lock.content_sha256,
                        lock.approval_binding_sha256,
                        lock.lock_sha256,
                        utc_text_v2(lock.locked_at),
                        _record_sha(row),
                    ),
                )
            audit = {
                "actor_fingerprint": command.actor_fingerprint,
                "chain_hash": chain,
                "command_id_fingerprint": hashlib.sha256(
                    command.command_id.value.encode("ascii")
                ).hexdigest(),
                "event_kind": command.kind.value,
                "occurred_at": utc_text_v2(command.occurred_at),
                "packet_id": str(command.packet_id),
                "previous_chain_hash": previous_chain,
                "request_sha256": command.request_sha256,
                "sequence": sequence,
                "state_sha256": state.state_sha256,
            }
            connection.execute(
                "INSERT INTO source_packet_audit_journal VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sequence,
                    audit["command_id_fingerprint"],
                    command.request_sha256,
                    str(command.packet_id),
                    command.kind.value,
                    command.actor_fingerprint,
                    state.state_sha256,
                    previous_chain,
                    chain,
                    utc_text_v2(command.occurred_at),
                    _record_sha(audit),
                ),
            )
            fault = self._faults.pop(0) if self._faults else None
            if fault is SourcePacketSqliteCommitFaultV2.BEFORE_COMMIT:
                connection.rollback()
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            try:
                connection.commit()
            except sqlite3.Error:
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            committed = True
            self._prefix_sequence = sequence
            self._prefix_chain_hash = chain
            if fault is SourcePacketSqliteCommitFaultV2.AFTER_COMMIT:
                fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_COMMIT_UNKNOWN)
            return result
        except SourcePacketFailureV2:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            raise
        except sqlite3.IntegrityError:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        except sqlite3.OperationalError as error:
            if not committed:
                try:
                    connection.rollback()
                except sqlite3.Error:
                    pass
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                fail_source_packet_v2(SourcePacketFailureCodeV2.VERSION_CONFLICT)
            fail_source_packet_v2(SourcePacketFailureCodeV2.STORAGE_FAILED)
        finally:
            _safe_close(connection)

    def recover(
        self,
        *,
        command_id: SourcePacketCommandIdV2,
        request_sha256: str,
    ) -> SourcePacketCommandResultV2:
        if (
            type(command_id) is not SourcePacketCommandIdV2
            or type(request_sha256) is not str
        ):
            fail_source_packet_v2()
        connection = self._connect()
        try:
            self._validate_all(connection)
            self._assert_prefix(connection)
            existing = self._load_command_unchecked(connection, command_id)
            if existing is None:
                fail_source_packet_v2(SourcePacketFailureCodeV2.COMMAND_UNKNOWN)
            if existing[0] != request_sha256:
                fail_source_packet_v2(SourcePacketFailureCodeV2.COMMAND_CONFLICT)
            return replace(
                existing[1], replay_status=SourcePacketReplayStatusV2.REPLAYED
            )
        finally:
            _safe_close(connection)

    def load_state(self, packet_id: UUID) -> SourcePacketStateV2 | None:
        if type(packet_id) is not UUID or packet_id.int == 0:
            fail_source_packet_v2()
        connection = self._connect()
        try:
            self._validate_all(connection)
            self._assert_prefix(connection)
            return self._load_state_unchecked(connection, packet_id)
        finally:
            _safe_close(connection)

    def audit_snapshot(self) -> tuple[dict[str, object], ...]:
        connection = self._connect()
        try:
            self._validate_all(connection)
            self._assert_prefix(connection)
            rows = connection.execute(
                "SELECT sequence,command_id_fingerprint,request_sha256,packet_id,event_kind,actor_fingerprint,state_sha256,previous_chain_hash,chain_hash,occurred_at FROM source_packet_audit_journal ORDER BY sequence"
            ).fetchall()
            return tuple(
                {
                    "actor_fingerprint": row[5],
                    "chain_hash": row[8],
                    "command_id_fingerprint": row[1],
                    "event_kind": row[4],
                    "occurred_at": row[9],
                    "packet_id": row[3],
                    "previous_chain_hash": row[7],
                    "request_sha256": row[2],
                    "sequence": row[0],
                    "state_sha256": row[6],
                }
                for row in rows
            )
        finally:
            _safe_close(connection)

    def _validate_all(self, connection: sqlite3.Connection) -> None:
        try:
            pragma = {
                "busy_timeout": connection.execute("PRAGMA busy_timeout").fetchone(),
                "foreign_keys": connection.execute("PRAGMA foreign_keys").fetchone(),
                "journal_mode": connection.execute("PRAGMA journal_mode").fetchone(),
                "trusted_schema": connection.execute(
                    "PRAGMA trusted_schema"
                ).fetchone(),
                "recursive_triggers": connection.execute(
                    "PRAGMA recursive_triggers"
                ).fetchone(),
                "synchronous": connection.execute("PRAGMA synchronous").fetchone(),
                "secure_delete": connection.execute("PRAGMA secure_delete").fetchone(),
                "temp_store": connection.execute("PRAGMA temp_store").fetchone(),
                "user_version": connection.execute("PRAGMA user_version").fetchone(),
            }
            if (
                pragma["busy_timeout"] != (0,)
                or pragma["foreign_keys"] != (1,)
                or pragma["journal_mode"] != ("delete",)
                or pragma["trusted_schema"] != (0,)
                or pragma["recursive_triggers"] != (1,)
                or pragma["synchronous"] != (2,)
                or pragma["secure_delete"] != (1,)
                or pragma["temp_store"] != (2,)
                or pragma["user_version"] != (_USER_VERSION,)
                or _schema_inventory(connection) != _EXPECTED_SCHEMA_INVENTORY
                or connection.execute("PRAGMA foreign_key_check").fetchall()
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            tables = frozenset(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )
            if tables != _TABLES:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            for table, columns in _EXPECTED_COLUMNS.items():
                observed = tuple(
                    row[1] for row in connection.execute(f"PRAGMA table_info({table})")
                )
                if observed != columns:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            triggers = frozenset(
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger'"
                )
            )
            expected_triggers = frozenset(
                f"{table}_{suffix}"
                for table in _TABLES
                for suffix in ("no_update", "no_delete")
            )
            if triggers != expected_triggers:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            metadata = connection.execute(
                "SELECT schema_version,database_identity,schema_sha256 FROM source_packet_metadata ORDER BY singleton"
            ).fetchall()
            if (
                len(metadata) != 1
                or metadata[0][0] != SOURCE_PACKET_SCHEMA_VERSION_V2
                or type(metadata[0][1]) is not str
                or len(metadata[0][1]) != 64
                or any(
                    character not in "0123456789abcdef" for character in metadata[0][1]
                )
                or metadata[0][2] != _schema_sha256()
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            self._validate_command_chain(connection)
            self._validate_registries(connection)
            self._validate_auxiliary_journals(connection)
        except sqlite3.Error:
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    def _validate_command_chain(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            "SELECT command_id,sequence,request_sha256,packet_id,command_kind,command_document,result_document,state_sha256,previous_chain_hash,chain_hash,committed_at,record_sha256 FROM source_packet_command_journal ORDER BY sequence"
        ).fetchall()
        states: dict[UUID, SourcePacketStateV2] = {}
        previous_chain = SOURCE_PACKET_GENESIS_SHA256_V2
        for expected_sequence, row in enumerate(rows, start=1):
            if row[1] != expected_sequence or row[8] != previous_chain:
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            command = command_from_mapping_v2(_decode(row[5]))
            result = result_from_mapping_v2(_decode(row[6]))
            prior = states.get(command.packet_id)
            expected_state, expected_generation = apply_source_packet_command_v2(
                prior, command
            )
            record = {
                "chain_hash": row[9],
                "command_document": row[5],
                "command_id": row[0],
                "command_kind": row[4],
                "committed_at": row[10],
                "packet_id": row[3],
                "previous_chain_hash": row[8],
                "request_sha256": row[2],
                "result_document": row[6],
                "sequence": row[1],
                "state_sha256": row[7],
            }
            if (
                row[0] != command.command_id.value
                or row[2] != command.request_sha256
                or row[3] != str(command.packet_id)
                or row[4] != command.kind.value
                or row[7] != expected_state.state_sha256
                or row[10] != utc_text_v2(command.occurred_at)
                or row[11] != _record_sha(record)
                or result.command != command
                or result.state != expected_state
                or result.generation_input != expected_generation
                or result.sequence != expected_sequence
                or result.previous_chain_hash != previous_chain
                or result.chain_hash != row[9]
                or result.replay_status is not SourcePacketReplayStatusV2.COMMITTED
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            states[command.packet_id] = expected_state
            previous_chain = row[9]
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM source_packet_audit_journal"
        ).fetchone()
        lifecycle_count = connection.execute(
            "SELECT COUNT(*) FROM source_packet_lifecycle_journal"
        ).fetchone()
        if audit_count != (len(rows),) or lifecycle_count != (len(rows),):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    def _validate_registries(self, connection: sqlite3.Connection) -> None:
        command_rows = connection.execute(
            "SELECT sequence,result_document FROM source_packet_command_journal ORDER BY sequence"
        ).fetchall()
        expected_packets: dict[str, dict[str, object]] = {}
        expected_versions: dict[tuple[str, int], dict[str, object]] = {}
        expected_reviews = 0
        expected_locks = 0
        for _, document in command_rows:
            result = result_from_mapping_v2(_decode(document))
            command = result.command
            if command.kind is SourcePacketCommandKindV2.CREATE_PACKET:
                expected_packets[str(result.state.packet_id)] = self._packet_record(
                    result.state
                )
            elif command.kind is SourcePacketCommandKindV2.CREATE_VERSION:
                record = self._version_record(result.state)
                expected_versions[
                    (str(result.state.packet_id), cast(int, record["version_number"]))
                ] = record
            elif command.kind is SourcePacketCommandKindV2.RECORD_REVIEW:
                expected_reviews += 1
            elif command.kind is SourcePacketCommandKindV2.LOCK_VERSION:
                expected_locks += 1
        packet_rows = connection.execute(
            "SELECT packet_id,site_id,article_plan_id,review_assignment_id,creator_actor_fingerprint,created_at,record_sha256 FROM source_packet_packet_registry ORDER BY packet_id"
        ).fetchall()
        if len(packet_rows) != len(expected_packets):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        for row in packet_rows:
            packet_record = expected_packets.get(row[0])
            packet_expected = (
                None
                if packet_record is None
                else (
                    packet_record["packet_id"],
                    packet_record["site_id"],
                    packet_record["article_plan_id"],
                    packet_record["review_assignment_id"],
                    packet_record["creator_actor_fingerprint"],
                    packet_record["created_at"],
                )
            )
            if (
                packet_record is None
                or packet_expected != row[:-1]
                or row[-1] != _record_sha(packet_record)
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        version_rows = connection.execute(
            "SELECT packet_id,version_number,version_id,content_sha256,content_document,editor_actor_fingerprint,created_at,record_sha256 FROM source_packet_version_registry ORDER BY packet_id,version_number"
        ).fetchall()
        if len(version_rows) != len(expected_versions):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
        for row in version_rows:
            version_record = expected_versions.get((row[0], row[1]))
            version_expected = (
                None
                if version_record is None
                else (
                    version_record["packet_id"],
                    version_record["version_number"],
                    version_record["version_id"],
                    version_record["content_sha256"],
                    version_record["content_document"],
                    version_record["editor_actor_fingerprint"],
                    version_record["created_at"],
                )
            )
            if (
                version_record is None
                or version_expected != row[:-1]
                or row[-1] != _record_sha(version_record)
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            _decode(row[4])
        review_count = connection.execute(
            "SELECT COUNT(*) FROM source_packet_review_journal"
        ).fetchone()
        lock_count = connection.execute(
            "SELECT COUNT(*) FROM source_packet_lock_journal"
        ).fetchone()
        if review_count != (expected_reviews,) or lock_count != (expected_locks,):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)

    def _validate_auxiliary_journals(self, connection: sqlite3.Connection) -> None:
        commands = connection.execute(
            "SELECT sequence,result_document FROM source_packet_command_journal ORDER BY sequence"
        ).fetchall()
        lifecycle_rows = {
            row[0]: row
            for row in connection.execute(
                "SELECT command_sequence,packet_id,version_number,event_kind,from_status,to_status,occurred_at,record_sha256 FROM source_packet_lifecycle_journal"
            )
        }
        audit_rows = {
            row[0]: row
            for row in connection.execute(
                "SELECT sequence,command_id_fingerprint,request_sha256,packet_id,event_kind,actor_fingerprint,state_sha256,previous_chain_hash,chain_hash,occurred_at,record_sha256 FROM source_packet_audit_journal"
            )
        }
        review_rows = {
            row[0]: row
            for row in connection.execute(
                "SELECT command_sequence,packet_id,version_id,version_number,decision,content_sha256,fact_membership_sha256,conflict_scan_sha256,authorization_sha256,binding_sha256,reviewed_at,record_sha256 FROM source_packet_review_journal"
            )
        }
        lock_rows = {
            row[0]: row
            for row in connection.execute(
                "SELECT command_sequence,packet_id,version_id,version_number,content_sha256,approval_binding_sha256,lock_sha256,locked_at,record_sha256 FROM source_packet_lock_journal"
            )
        }
        prior_by_packet: dict[UUID, SourcePacketStateV2] = {}
        expected_review_sequences: set[int] = set()
        expected_lock_sequences: set[int] = set()
        for sequence, document in commands:
            result = result_from_mapping_v2(_decode(document))
            command = result.command
            prior = prior_by_packet.get(command.packet_id)
            lifecycle = self._lifecycle_record(
                sequence=sequence,
                command=command,
                previous=prior,
                state=result.state,
            )
            lifecycle_row = lifecycle_rows.get(sequence)
            expected_lifecycle = (
                sequence,
                str(command.packet_id),
                lifecycle["version_number"],
                command.kind.value,
                lifecycle["from_status"],
                lifecycle["to_status"],
                utc_text_v2(command.occurred_at),
                _record_sha(lifecycle),
            )
            audit = {
                "actor_fingerprint": command.actor_fingerprint,
                "chain_hash": result.chain_hash,
                "command_id_fingerprint": hashlib.sha256(
                    command.command_id.value.encode("ascii")
                ).hexdigest(),
                "event_kind": command.kind.value,
                "occurred_at": utc_text_v2(command.occurred_at),
                "packet_id": str(command.packet_id),
                "previous_chain_hash": result.previous_chain_hash,
                "request_sha256": command.request_sha256,
                "sequence": sequence,
                "state_sha256": result.state.state_sha256,
            }
            expected_audit = (
                sequence,
                audit["command_id_fingerprint"],
                command.request_sha256,
                str(command.packet_id),
                command.kind.value,
                command.actor_fingerprint,
                result.state.state_sha256,
                result.previous_chain_hash,
                result.chain_hash,
                utc_text_v2(command.occurred_at),
                _record_sha(audit),
            )
            if (
                lifecycle_row != expected_lifecycle
                or audit_rows.get(sequence) != expected_audit
            ):
                fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            current = result.state.current_version
            if command.kind is SourcePacketCommandKindV2.RECORD_REVIEW:
                expected_review_sequences.add(sequence)
                if current is None or current.review is None:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
                review = current.review
                material = {
                    "authorization_sha256": review.authorization.sha256,
                    "binding_sha256": review.binding_sha256,
                    "command_sequence": sequence,
                    "conflict_scan_sha256": review.conflict_scan_sha256,
                    "content_sha256": review.content_sha256,
                    "decision": review.decision.value,
                    "fact_membership_sha256": review.fact_membership_sha256,
                    "packet_id": str(review.packet_id),
                    "reviewed_at": utc_text_v2(review.reviewed_at),
                    "version_id": str(review.version_id),
                    "version_number": review.version_number,
                }
                expected_review = (
                    sequence,
                    str(review.packet_id),
                    str(review.version_id),
                    review.version_number,
                    review.decision.value,
                    review.content_sha256,
                    review.fact_membership_sha256,
                    review.conflict_scan_sha256,
                    review.authorization.sha256,
                    review.binding_sha256,
                    utc_text_v2(review.reviewed_at),
                    _record_sha(material),
                )
                if review_rows.get(sequence) != expected_review:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            if command.kind is SourcePacketCommandKindV2.LOCK_VERSION:
                expected_lock_sequences.add(sequence)
                if current is None or current.lock is None:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
                lock = current.lock
                material = {
                    "approval_binding_sha256": lock.approval_binding_sha256,
                    "command_sequence": sequence,
                    "content_sha256": lock.content_sha256,
                    "lock_sha256": lock.lock_sha256,
                    "locked_at": utc_text_v2(lock.locked_at),
                    "packet_id": str(lock.packet_id),
                    "version_id": str(lock.version_id),
                    "version_number": lock.version_number,
                }
                expected_lock = (
                    sequence,
                    str(lock.packet_id),
                    str(lock.version_id),
                    lock.version_number,
                    lock.content_sha256,
                    lock.approval_binding_sha256,
                    lock.lock_sha256,
                    utc_text_v2(lock.locked_at),
                    _record_sha(material),
                )
                if lock_rows.get(sequence) != expected_lock:
                    fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)
            prior_by_packet[command.packet_id] = result.state
        if (
            set(review_rows) != expected_review_sequences
            or set(lock_rows) != expected_lock_sequences
        ):
            fail_source_packet_v2(SourcePacketFailureCodeV2.TAMPER_DETECTED)


__all__ = [
    "OwnerPrivateSqliteSourcePacketStoreV2",
    "SourcePacketSqliteCommitFaultV2",
]
