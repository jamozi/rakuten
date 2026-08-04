"""Fail-closed Alembic runner for the ST-0301 migration framework."""

from __future__ import annotations

import io
import hashlib
import os
import re
import stat
import tempfile
import uuid
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Final

import psycopg
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy.engine import Connection, Engine, URL
from sqlalchemy.pool import NullPool

from .catalog import (
    ALEMBIC_RUNTIME_SPECS,
    ANCHOR_REVISION,
    HEAD_REVISION,
    REVISION_SPECS,
    CatalogVerification,
    verify_all_sources,
)


EXPECTED_SERVER_VERSION_NUM: Final = 180004
ADVISORY_LOCK_KEY: Final = -4304770990298879982
_ADVISORY_LOCK_UNSIGNED: Final = ADVISORY_LOCK_KEY % (1 << 64)
_ADVISORY_LOCK_CLASS_ID: Final = _ADVISORY_LOCK_UNSIGNED >> 32
_ADVISORY_LOCK_OBJECT_ID: Final = _ADVISORY_LOCK_UNSIGNED & 0xFFFFFFFF
DOMAIN_SCHEMAS: Final = (
    "ai",
    "analytics",
    "catalog",
    "editorial",
    "evidence",
    "finance",
    "freshness",
    "iam",
    "ops",
    "policy",
    "portfolio",
    "publishing",
    "readmodel",
)
_IDENTIFIER_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_AMBIENT_PG_PATTERN: Final = re.compile(r"^PG[A-Z0-9_]*$")


class MigrationEnvironment(StrEnum):
    """Environments allowed by the local/CI candidate runner."""

    DEV = "ENV-DEV"
    CI = "ENV-CI"
    INTEGRATION = "ENV-INTEGRATION"


class MigrationErrorCode(StrEnum):
    """Stable public error codes."""

    INVALID_TARGET = "MIG-RUN-001"
    AMBIENT_CONFIGURATION = "MIG-RUN-002"
    INVALID_PASSWORD_FILE = "MIG-RUN-003"
    CONNECTION_FAILED = "MIG-RUN-004"
    SERVER_VERSION_MISMATCH = "MIG-RUN-005"
    LOCK_BUSY = "MIG-RUN-006"
    GRAPH_MISMATCH = "MIG-RUN-007"
    UNMANAGED_DATABASE = "MIG-RUN-008"
    MIGRATION_FAILED = "MIG-RUN-009"
    HISTORY_INVALID = "MIG-RUN-010"
    SESSION_CLEANUP_FAILED = "MIG-RUN-011"
    DOWNGRADE_FORBIDDEN = "MIG-RUN-012"


_ERROR_MESSAGES: Final = {
    MigrationErrorCode.INVALID_TARGET: "database target is invalid",
    MigrationErrorCode.AMBIENT_CONFIGURATION: "ambient database configuration is forbidden",
    MigrationErrorCode.INVALID_PASSWORD_FILE: "password file is invalid",
    MigrationErrorCode.CONNECTION_FAILED: "database connection failed",
    MigrationErrorCode.SERVER_VERSION_MISMATCH: "database server version does not match",
    MigrationErrorCode.LOCK_BUSY: "migration lock is already held",
    MigrationErrorCode.GRAPH_MISMATCH: "migration graph or current revision is not recognized",
    MigrationErrorCode.UNMANAGED_DATABASE: "database is not an empty or managed RAOS database",
    MigrationErrorCode.MIGRATION_FAILED: "migration failed and requires forward recovery",
    MigrationErrorCode.HISTORY_INVALID: "migration version or history is invalid",
    MigrationErrorCode.SESSION_CLEANUP_FAILED: "migration session cleanup failed",
    MigrationErrorCode.DOWNGRADE_FORBIDDEN: "history anchor downgrade is forbidden",
}


class MigrationError(RuntimeError):
    """A sanitized operational failure."""

    __slots__ = ("code",)

    def __init__(self, code: MigrationErrorCode) -> None:
        self.code = code
        super().__init__(_ERROR_MESSAGES[code])


@dataclass(frozen=True, slots=True)
class DatabaseTarget:
    """Explicit local/CI database target without a DSN or secret value."""

    environment: MigrationEnvironment
    host: str
    port: int
    database: str
    user: str
    password_file: Path


@dataclass(frozen=True, slots=True)
class MigrationResult:
    """Allowlisted public result."""

    command: str
    environment: str | None
    changed: bool
    current_revision: str
    catalog_sha256: str
    revision_source_count: int
    checkpoint_source_count: int

    def public_dict(self) -> dict[str, object]:
        return {
            "catalog_sha256": self.catalog_sha256,
            "changed": self.changed,
            "checkpoint_source_count": self.checkpoint_source_count,
            "command": self.command,
            "current_revision": self.current_revision,
            "environment": self.environment,
            "revision_source_count": self.revision_source_count,
            "status": "PASS",
        }


EngineFactory = Callable[[DatabaseTarget], Engine]


def _validate_identifier(value: object) -> bool:
    return type(value) is str and _IDENTIFIER_PATTERN.fullmatch(value) is not None


def _is_path(value: object) -> bool:
    return isinstance(value, Path)


def _real_directory(path: Path) -> bool:
    if not path.is_absolute():
        return False
    try:
        lexical = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        metadata = path.lstat()
    except OSError:
        return False
    return (
        lexical == resolved
        and stat.S_ISDIR(metadata.st_mode)
        and not stat.S_ISLNK(metadata.st_mode)
    )


def _reject_ambient_postgres_configuration() -> None:
    if any(_AMBIENT_PG_PATTERN.fullmatch(key) for key in os.environ):
        raise MigrationError(MigrationErrorCode.AMBIENT_CONFIGURATION)


def _validate_target(target: DatabaseTarget) -> None:
    if type(target) is not DatabaseTarget:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.environment) is not MigrationEnvironment:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.host) is not str or not target.host:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if target.host.startswith("/"):
        if not _real_directory(Path(target.host)):
            raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    elif target.host not in {"127.0.0.1", "::1"}:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if type(target.port) is not int or not 1024 <= target.port <= 65535:
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if not _validate_identifier(target.database) or not _validate_identifier(
        target.user
    ):
        raise MigrationError(MigrationErrorCode.INVALID_TARGET)
    if not _is_path(target.password_file) or not target.password_file.is_absolute():
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    _reject_ambient_postgres_configuration()


def _read_password_file(path: Path) -> str:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    flags = os.O_RDONLY | os.O_CLOEXEC
    directory_flags = flags | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    open_failed = False
    try:
        current = os.open("/", directory_flags)
        descriptors.append(current)
        for component in path.parts[1:-1]:
            current = os.open(component, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(
            path.parts[-1],
            flags | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=current,
        )
        descriptors.append(descriptor)
    except MigrationError:
        raise
    except OSError:
        open_failed = True
        descriptor = -1
    if open_failed:
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    read_failed = False
    content = b""
    try:
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or not 1 <= metadata.st_size <= 1024
        ):
            raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
        content = os.read(descriptor, metadata.st_size + 1)
        if len(content) != metadata.st_size:
            raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    except MigrationError:
        raise
    except OSError:
        read_failed = True
    finally:
        for opened in reversed(descriptors):
            try:
                os.close(opened)
            except OSError:
                pass
    if read_failed:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    if content.endswith(b"\n"):
        content = content[:-1]
    if not content or b"\x00" in content or b"\r" in content or b"\n" in content:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    password: str | None
    try:
        password = content.decode("utf-8")
    except UnicodeDecodeError:
        password = None
    if password is None:
        raise MigrationError(MigrationErrorCode.INVALID_PASSWORD_FILE)
    return password


def _default_engine_factory(target: DatabaseTarget) -> Engine:
    def connect() -> Any:
        _reject_ambient_postgres_configuration()
        password = _read_password_file(target.password_file)
        return psycopg.connect(
            host=target.host,
            port=target.port,
            dbname=target.database,
            user=target.user,
            password=password,
            sslmode="disable",
            connect_timeout=5,
            application_name="raos-migration-st0301",
            options=(
                "-c lock_timeout=5000ms "
                "-c statement_timeout=300000ms "
                "-c idle_in_transaction_session_timeout=60000ms"
            ),
        )

    return sa.create_engine(
        URL.create("postgresql+psycopg"),
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
    )


def _alembic_config(repository_root: Path) -> Config:
    output = io.StringIO()
    configuration = Config(output_buffer=output, stdout=output)
    configuration.set_main_option(
        "script_location",
        str(repository_root / "migrations"),
    )
    return configuration


@contextmanager
def _verified_migration_root(
    verification: CatalogVerification,
) -> Generator[Path, None, None]:
    sources = (*verification.runtime_sources, *verification.revision_sources)
    expected_paths = tuple(
        item.relative_path
        for item in (
            *ALEMBIC_RUNTIME_SPECS,
            *REVISION_SPECS,
        )
    )
    if tuple(source.relative_path for source in sources) != expected_paths:
        raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
    with tempfile.TemporaryDirectory(prefix="raos-migration-snapshot-") as temporary:
        root = Path(temporary)
        try:
            for source in sources:
                content = source.content
                if (
                    content is None
                    or hashlib.sha256(content).hexdigest() != source.sha256
                    or source.relative_path.parts[0] != "migrations"
                ):
                    raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
                destination = root / source.relative_path
                destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                descriptor = os.open(
                    destination,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                    0o600,
                )
                try:
                    view = memoryview(content)
                    while view:
                        written = os.write(descriptor, view)
                        if written < 1:
                            raise OSError("snapshot write failed")
                        view = view[written:]
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        except MigrationError:
            raise
        except OSError:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH) from None
        yield root


def _verify_graph(repository_root: Path) -> None:
    try:
        script = ScriptDirectory.from_config(_alembic_config(repository_root))
        revisions = tuple(script.walk_revisions())
        heads = tuple(script.get_heads())
        bases = tuple(script.get_bases())
    except Exception:
        pass
    else:
        if (
            heads != (HEAD_REVISION,)
            or bases != (ANCHOR_REVISION,)
            or len(revisions) != len(REVISION_SPECS)
        ):
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        expected_by_revision = {item.revision: item for item in REVISION_SPECS}
        for observed in revisions:
            expected = expected_by_revision.get(observed.revision)
            branch_labels = set(observed.branch_labels or ())
            if (
                expected is None
                or observed.down_revision != expected.down_revision
                or observed.dependencies is not None
                or not branch_labels.issubset({"raos_framework"})
                or (
                    observed.revision == ANCHOR_REVISION
                    and branch_labels != {"raos_framework"}
                )
            ):
                raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        return
    raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)


def verify_repository(repository_root: Path) -> CatalogVerification:
    """Verify all source bytes and the exact Alembic graph offline."""

    verification = verify_all_sources(repository_root)
    graph_error: MigrationErrorCode | None = None
    try:
        with _verified_migration_root(verification) as snapshot_root:
            _verify_graph(snapshot_root)
    except MigrationError as error:
        graph_error = error.code
    except Exception:
        graph_error = MigrationErrorCode.GRAPH_MISMATCH
    if graph_error is not None:
        raise MigrationError(graph_error)
    return verification


def _current_heads(connection: Connection) -> tuple[str, ...]:
    context = MigrationContext.configure(
        connection,
        opts={
            "version_table": "raos_migration_version",
            "version_table_schema": "public",
        },
    )
    return tuple(context.get_current_heads())


def _assert_empty_database(connection: Connection) -> None:
    unmanaged = connection.execute(
        sa.text(
            """
            SELECT
                EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_namespace AS n
                    WHERE n.nspname NOT IN ('public', 'information_schema')
                      AND n.nspname NOT LIKE 'pg_%'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_class AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                    WHERE n.nspname = 'public'
                      AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_proc AS p
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_type AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.typnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_collation AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.collnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_conversion AS c
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = c.connamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_operator AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.oprnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opclass AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opcnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_opfamily AS o
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = o.opfnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_config AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.cfgnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_dict AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.dictnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_parser AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.prsnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_ts_template AS t
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = t.tmplnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_statistic_ext AS s
                    JOIN pg_catalog.pg_namespace AS n ON n.oid = s.stxnamespace
                    WHERE n.nspname = 'public'
                )
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_largeobject_metadata)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_server)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_foreign_data_wrapper)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_event_trigger)
                OR EXISTS (SELECT 1 FROM pg_catalog.pg_publication)
                OR EXISTS (
                    SELECT 1
                    FROM pg_catalog.pg_extension
                    WHERE extname <> 'plpgsql'
                )
            """
        )
    ).scalar_one()
    if unmanaged is not False:
        raise MigrationError(MigrationErrorCode.UNMANAGED_DATABASE)


@dataclass(frozen=True, slots=True)
class _OpenAttempt:
    attempt_id: str
    revision_index: int


@dataclass(frozen=True, slots=True)
class _LockedSession:
    """Opaque identity for the one PostgreSQL session holding the lock."""

    backend_pid: int
    driver_connection: Any = field(repr=False, compare=False)


def _history_rows(connection: Connection) -> list[tuple[Any, ...]]:
    return [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT event_id, attempt_id::text, revision_id, story_id,
                       direction, status, source_sha256, runner_version,
                       server_version_num, error_code
                FROM public.raos_migration_history
                ORDER BY event_id
                """
            )
        ).all()
    ]


def _analyze_history(
    rows: list[tuple[Any, ...]],
    current_revision: str,
    *,
    allow_open: bool,
) -> _OpenAttempt | None:
    specs = tuple(REVISION_SPECS)
    by_revision = {item.revision: (index, item) for index, item in enumerate(specs)}
    completed_index = -1
    attempts: dict[str, int] = {}
    closed_attempts: set[str] = set()
    previous_event_id = 0
    for row in rows:
        if len(row) != 10:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        (
            event_id,
            attempt_id,
            revision_id,
            story_id,
            direction,
            status,
            source_sha256,
            runner_version,
            server_version_num,
            error_code,
        ) = row
        located = by_revision.get(revision_id)
        if (
            type(event_id) is not int
            or event_id <= previous_event_id
            or not isinstance(attempt_id, str)
            or located is None
        ):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        previous_event_id = event_id
        try:
            canonical_attempt_id = str(uuid.UUID(attempt_id))
        except ValueError, AttributeError:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID) from None
        index, spec = located
        if (
            canonical_attempt_id != attempt_id
            or story_id != spec.story_id
            or direction != "UPGRADE"
            or source_sha256 != spec.sha256
            or runner_version != spec.runner_version
            or server_version_num != spec.server_version_num
            or status not in {"STARTED", "SUCCEEDED", "FAILED"}
        ):
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        if status == "STARTED":
            if (
                index == 0
                or index != completed_index + 1
                or attempt_id in attempts
                or attempt_id in closed_attempts
                or error_code is not None
            ):
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            attempts[attempt_id] = index
            continue
        if index == 0:
            if (
                status != "SUCCEEDED"
                or completed_index != -1
                or attempts
                or attempt_id in closed_attempts
                or error_code is not None
            ):
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            completed_index = 0
            closed_attempts.add(attempt_id)
            continue
        if attempts.pop(attempt_id, None) != index or index != completed_index + 1:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
        closed_attempts.add(attempt_id)
        if status == "SUCCEEDED":
            if error_code is not None:
                raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
            completed_index = index
        elif error_code not in {"MIGRATION_FAILED", "INTERRUPTED_BEFORE_TERMINAL"}:
            raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    expected_current = (
        specs[completed_index].revision if completed_index >= 0 else "base"
    )
    if expected_current != current_revision or len(attempts) > 1:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    if not attempts:
        return None
    attempt_id, revision_index = next(iter(attempts.items()))
    if not allow_open:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    return _OpenAttempt(attempt_id=attempt_id, revision_index=revision_index)


def _append_attempt_event(
    connection: Connection,
    *,
    attempt_id: str,
    revision_index: int,
    status: str,
    error_code: str | None,
) -> None:
    spec = REVISION_SPECS[revision_index]
    connection.execute(
        sa.text(
            """
            INSERT INTO public.raos_migration_history (
                attempt_id, revision_id, story_id, direction, status,
                source_sha256, runner_version, server_version_num, error_code
            ) VALUES (
                CAST(:attempt_id AS uuid), :revision_id, :story_id, 'UPGRADE',
                :status, :source_sha256, :runner_version,
                :server_version_num, :error_code
            )
            """
        ),
        {
            "attempt_id": attempt_id,
            "revision_id": spec.revision,
            "story_id": spec.story_id,
            "status": status,
            "source_sha256": spec.sha256,
            "runner_version": spec.runner_version,
            "server_version_num": spec.server_version_num,
            "error_code": error_code,
        },
    )
    connection.commit()


def _validate_metadata_shape(connection: Connection) -> None:
    owner = connection.execute(sa.text("SELECT current_user")).scalar_one()
    relations = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, c.relkind, pg_get_userbyid(c.relowner)
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version',
                      'raos_migration_history',
                      'raos_migration_history_event_id_seq'
                  )
                ORDER BY c.relname
                """
            )
        ).all()
    ]
    if relations != [
        ("raos_migration_history", "r", owner),
        ("raos_migration_history_event_id_seq", "S", owner),
        ("raos_migration_version", "r", owner),
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    columns = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, a.attname,
                       pg_catalog.format_type(a.atttypid, a.atttypmod),
                       a.attnotnull, a.attidentity,
                       pg_catalog.pg_get_expr(d.adbin, d.adrelid)
                FROM pg_catalog.pg_attribute AS a
                JOIN pg_catalog.pg_class AS c ON c.oid = a.attrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                LEFT JOIN pg_catalog.pg_attrdef AS d
                  ON d.adrelid = a.attrelid AND d.adnum = a.attnum
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY c.relname, a.attnum
                """
            )
        ).all()
    ]
    expected_columns = [
        ("raos_migration_history", "event_id", "bigint", True, "a", None),
        ("raos_migration_history", "attempt_id", "uuid", True, "", None),
        (
            "raos_migration_history",
            "revision_id",
            "character varying(32)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "story_id",
            "character varying(16)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "direction",
            "character varying(9)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "status",
            "character varying(10)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "source_sha256",
            "character(64)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "runner_version",
            "character varying(32)",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "server_version_num",
            "integer",
            True,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "error_code",
            "character varying(64)",
            False,
            "",
            None,
        ),
        (
            "raos_migration_history",
            "occurred_at",
            "timestamp with time zone",
            True,
            "",
            "transaction_timestamp()",
        ),
        (
            "raos_migration_history",
            "transaction_id",
            "text",
            True,
            "",
            "(pg_current_xact_id())::text",
        ),
        (
            "raos_migration_version",
            "version_num",
            "character varying(32)",
            True,
            "",
            None,
        ),
    ]
    if columns != expected_columns:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    constraints = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, con.conname, con.contype, con.convalidated,
                       pg_catalog.pg_get_constraintdef(con.oid, true)
                FROM pg_catalog.pg_constraint AS con
                JOIN pg_catalog.pg_class AS c ON c.oid = con.conrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                ORDER BY c.relname, con.conname
                """
            )
        ).all()
    ]
    expected_constraints = [
        (
            "raos_migration_version",
            "raos_migration_version_pkc",
            "p",
            True,
            "PRIMARY KEY (version_num)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_revision",
            "c",
            True,
            "CHECK (revision_id::text ~ '^[0-9]{12}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_story",
            "c",
            True,
            "CHECK (story_id::text ~ '^ST-[0-9]{4}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_direction",
            "c",
            True,
            "CHECK (direction::text = ANY (ARRAY['UPGRADE'::character varying, "
            "'DOWNGRADE'::character varying]::text[]))",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_status",
            "c",
            True,
            "CHECK (status::text = ANY (ARRAY['STARTED'::character varying, "
            "'SUCCEEDED'::character varying, 'FAILED'::character varying]::text[]))",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_source_sha256",
            "c",
            True,
            "CHECK (source_sha256 ~ '^[0-9a-f]{64}$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_runner_version",
            "c",
            True,
            "CHECK (runner_version::text ~ '^[0-9]+[.][0-9]+[.][0-9]+$'::text)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_server_version",
            "c",
            True,
            "CHECK (server_version_num >= 100000 AND server_version_num <= 999999)",
        ),
        (
            "raos_migration_history",
            "ck_raos_migration_history_error_code",
            "c",
            True,
            "CHECK (status::text = 'FAILED'::text AND error_code IS NOT NULL "
            "OR status::text <> 'FAILED'::text AND error_code IS NULL)",
        ),
        (
            "raos_migration_history",
            "pk_raos_migration_history",
            "p",
            True,
            "PRIMARY KEY (event_id)",
        ),
        (
            "raos_migration_history",
            "uq_raos_migration_history_attempt_status",
            "u",
            True,
            "UNIQUE (attempt_id, status)",
        ),
    ]
    expected_constraints.extend(
        (
            relation,
            f"{relation}_{column}_not_null",
            "n",
            True,
            f"NOT NULL {column}",
        )
        for relation, column, _, not_null, _, _ in expected_columns
        if not_null
    )
    expected_constraints.sort()
    if constraints != expected_constraints:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    sequence_dependencies = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT sequence.relname, table_relation.relname,
                       column_attribute.attname, dependency.deptype
                FROM pg_catalog.pg_class AS sequence
                JOIN pg_catalog.pg_namespace AS sequence_namespace
                  ON sequence_namespace.oid = sequence.relnamespace
                JOIN pg_catalog.pg_depend AS dependency
                  ON dependency.classid = 'pg_class'::regclass
                 AND dependency.objid = sequence.oid
                JOIN pg_catalog.pg_class AS table_relation
                  ON table_relation.oid = dependency.refobjid
                JOIN pg_catalog.pg_attribute AS column_attribute
                  ON column_attribute.attrelid = table_relation.oid
                 AND column_attribute.attnum = dependency.refobjsubid
                WHERE sequence_namespace.nspname = 'public'
                  AND sequence.relname =
                      'raos_migration_history_event_id_seq'
                """
            )
        ).all()
    ]
    if sequence_dependencies != [
        (
            "raos_migration_history_event_id_seq",
            "raos_migration_history",
            "event_id",
            "i",
        )
    ]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)

    unexpected_acl_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM (
                SELECT x.grantee, c.relowner AS owner
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                CROSS JOIN LATERAL aclexplode(c.relacl) AS x
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version',
                      'raos_migration_history',
                      'raos_migration_history_event_id_seq'
                  )
                UNION ALL
                SELECT x.grantee, p.proowner AS owner
                FROM pg_catalog.pg_proc AS p
                JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                CROSS JOIN LATERAL aclexplode(p.proacl) AS x
                WHERE n.nspname = 'public'
                  AND p.proname =
                      'raos_reject_migration_history_mutation_st0301'
            ) AS privileges
            WHERE grantee <> owner
            """
        )
    ).scalar_one()
    acl_null_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_class AS c
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version',
                       'raos_migration_history',
                       'raos_migration_history_event_id_seq'
                   )
                   AND c.relacl IS NULL)
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_proc AS p
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'public'
                   AND p.proname =
                       'raos_reject_migration_history_mutation_st0301'
                   AND p.proacl IS NULL)
            """
        )
    ).scalar_one()
    trigger_functions = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, t.tgname, t.tgenabled, t.tgtype,
                       p.proname, l.lanname, p.prosecdef, p.provolatile,
                       p.proconfig,
                       trim(regexp_replace(p.prosrc, '\\s+', ' ', 'g'))
                FROM pg_catalog.pg_trigger AS t
                JOIN pg_catalog.pg_class AS c ON c.oid = t.tgrelid
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                JOIN pg_catalog.pg_proc AS p ON p.oid = t.tgfoid
                JOIN pg_catalog.pg_language AS l ON l.oid = p.prolang
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND NOT t.tgisinternal
                ORDER BY c.relname, t.tgname
                """
            )
        ).all()
    ]
    table_security = [
        tuple(row)
        for row in connection.execute(
            sa.text(
                """
                SELECT c.relname, c.relpersistence, c.relrowsecurity,
                       c.relforcerowsecurity, c.relreplident
                FROM pg_catalog.pg_class AS c
                JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                      'raos_migration_version', 'raos_migration_history'
                  )
                  AND c.relkind = 'r'
                ORDER BY c.relname
                """
            )
        ).all()
    ]
    unexpected_rewrite_or_policy_count = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT count(*)
                 FROM pg_catalog.pg_rewrite AS rewrite
                 JOIN pg_catalog.pg_class AS c ON c.oid = rewrite.ev_class
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version', 'raos_migration_history'
                   ))
                +
                (SELECT count(*)
                 FROM pg_catalog.pg_policy AS policy
                 JOIN pg_catalog.pg_class AS c ON c.oid = policy.polrelid
                 JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
                 WHERE n.nspname = 'public'
                   AND c.relname IN (
                       'raos_migration_version', 'raos_migration_history'
                   ))
                +
                (SELECT count(*) FROM pg_catalog.pg_event_trigger)
            """
        )
    ).scalar_one()
    if (
        unexpected_acl_count != 0
        or acl_null_count != 0
        or table_security
        != [
            ("raos_migration_history", "p", False, False, "d"),
            ("raos_migration_version", "p", False, False, "d"),
        ]
        or unexpected_rewrite_or_policy_count != 0
        or trigger_functions
        != [
            (
                "raos_migration_history",
                "trg_raos_migration_history_append_only",
                "O",
                58,
                "raos_reject_migration_history_mutation_st0301",
                "plpgsql",
                False,
                "v",
                ["search_path=pg_catalog"],
                (
                    "BEGIN RAISE EXCEPTION USING ERRCODE = '55000', "
                    "MESSAGE = 'RAOS migration history is append-only'; END;"
                ),
            )
        ]
    ):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


def _validate_installed_unchecked(
    connection: Connection,
    current_revision: str,
    *,
    allow_open: bool = False,
) -> _OpenAttempt | None:
    if _current_heads(connection) != (current_revision,):
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    version_rows = (
        connection.execute(
            sa.text(
                "SELECT version_num FROM public.raos_migration_version ORDER BY version_num"
            )
        )
        .scalars()
        .all()
    )
    if version_rows != [current_revision]:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    open_attempt = _analyze_history(
        _history_rows(connection), current_revision, allow_open=allow_open
    )
    _validate_metadata_shape(connection)
    domain_schema_count = connection.execute(
        sa.text(
            """
            SELECT count(*)
            FROM pg_catalog.pg_namespace
            WHERE nspname = ANY(CAST(:schemas AS text[]))
            """
        ),
        {"schemas": list(DOMAIN_SCHEMAS)},
    ).scalar_one()
    if current_revision == ANCHOR_REVISION and domain_schema_count != 0:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    return open_attempt


def _validate_installed(
    connection: Connection,
    current_revision: str,
    *,
    allow_open: bool = False,
) -> _OpenAttempt | None:
    validation_failed = False
    try:
        return _validate_installed_unchecked(
            connection, current_revision, allow_open=allow_open
        )
    except MigrationError:
        raise
    except Exception:
        if connection.in_transaction():
            connection.rollback()
        validation_failed = True
    if validation_failed:
        raise MigrationError(MigrationErrorCode.HISTORY_INVALID)
    raise MigrationError(MigrationErrorCode.HISTORY_INVALID)


class MigrationRunner:
    """Execute the reviewed linear migration graph on an explicit local target."""

    __slots__ = ("_engine_factory", "_repository_root", "_target")

    def __init__(
        self,
        repository_root: Path,
        target: DatabaseTarget,
        *,
        engine_factory: EngineFactory | None = None,
    ) -> None:
        self._repository_root = repository_root.absolute()
        self._target = target
        self._engine_factory = engine_factory or _default_engine_factory

    def _open_engine(self, verification: CatalogVerification) -> Engine:
        del verification
        _validate_target(self._target)
        engine_failed = False
        try:
            return self._engine_factory(self._target)
        except MigrationError:
            raise
        except Exception:
            engine_failed = True
        if engine_failed:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)

    @staticmethod
    def _prepare_and_lock(connection: Connection) -> _LockedSession:
        connection_failed = False
        try:
            if connection.dialect.name != "postgresql":
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            if connection.closed or connection.invalidated:
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            driver_connection = connection.connection.driver_connection
            if driver_connection is None:
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            version = connection.exec_driver_sql("SHOW server_version_num").scalar_one()
            if str(version) != str(EXPECTED_SERVER_VERSION_NUM):
                raise MigrationError(MigrationErrorCode.SERVER_VERSION_MISMATCH)
            connection.exec_driver_sql("SET lock_timeout = '5000ms'")
            connection.exec_driver_sql("SET statement_timeout = '300000ms'")
            connection.exec_driver_sql(
                "SET idle_in_transaction_session_timeout = '60000ms'"
            )
            acquired, backend_pid = connection.execute(
                sa.text("SELECT pg_try_advisory_lock(:key), pg_backend_pid()"),
                {"key": ADVISORY_LOCK_KEY},
            ).one()
            if (
                type(backend_pid) is not int
                or connection.closed
                or connection.invalidated
                or connection.connection.driver_connection is not driver_connection
            ):
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
            identity = _LockedSession(
                backend_pid=backend_pid,
                driver_connection=driver_connection,
            )
            connection.commit()
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection is not driver_connection
            ):
                raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        except MigrationError:
            if connection.in_transaction():
                connection.rollback()
            raise
        except Exception:
            if connection.in_transaction():
                connection.rollback()
            connection_failed = True
        else:
            if acquired is not True:
                raise MigrationError(MigrationErrorCode.LOCK_BUSY)
            return identity
        if connection_failed:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)

    @staticmethod
    def _assert_same_session(connection: Connection, identity: _LockedSession) -> None:
        session_failed = False
        try:
            if connection.closed or connection.invalidated:
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            if (
                connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            backend_pid, exact_lock_held = connection.execute(
                sa.text(
                    """
                    SELECT pg_backend_pid(),
                           (
                               SELECT count(*) = 1
                               FROM pg_catalog.pg_locks
                               WHERE locktype = 'advisory'
                                 AND pid = pg_backend_pid()
                                 AND classid::bigint = :class_id
                                 AND objid::bigint = :object_id
                                 AND objsubid = 1
                                 AND mode = 'ExclusiveLock'
                                 AND granted
                           )
                    """
                ),
                {
                    "class_id": _ADVISORY_LOCK_CLASS_ID,
                    "object_id": _ADVISORY_LOCK_OBJECT_ID,
                },
            ).one()
            if backend_pid != identity.backend_pid or exact_lock_held is not True:
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        except MigrationError:
            raise
        except Exception:
            if connection.in_transaction():
                try:
                    connection.rollback()
                except Exception:
                    pass
            session_failed = True
        if session_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)

    def _reconcile_interrupted_attempt(
        self,
        connection: Connection,
        current_revision: str,
        session_identity: _LockedSession,
    ) -> None:
        self._assert_same_session(connection, session_identity)
        open_attempt = _validate_installed(
            connection, current_revision, allow_open=True
        )
        if open_attempt is None:
            return
        self._assert_same_session(connection, session_identity)
        _append_attempt_event(
            connection,
            attempt_id=open_attempt.attempt_id,
            revision_index=open_attempt.revision_index,
            status="FAILED",
            error_code="INTERRUPTED_BEFORE_TERMINAL",
        )
        _validate_installed(connection, current_revision)

    @staticmethod
    def _unlock(connection: Connection, identity: _LockedSession) -> None:
        cleanup_failed = False
        try:
            if connection.in_transaction():
                connection.rollback()
            if (
                connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
            backend_pid, released = connection.execute(
                sa.text("SELECT pg_backend_pid(), pg_advisory_unlock(:key)"),
                {"key": ADVISORY_LOCK_KEY},
            ).one()
            connection.commit()
            if (
                backend_pid != identity.backend_pid
                or released is not True
                or connection.closed
                or connection.invalidated
                or connection.connection.driver_connection
                is not identity.driver_connection
            ):
                raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        except MigrationError:
            raise
        except Exception:
            if connection.in_transaction():
                connection.rollback()
            cleanup_failed = True
        if cleanup_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)

    def _result(
        self,
        command_name: str,
        changed: bool,
        current_revision: str,
        verification: CatalogVerification,
    ) -> MigrationResult:
        return MigrationResult(
            command=command_name,
            environment=self._target.environment.value,
            changed=changed,
            current_revision=current_revision,
            catalog_sha256=verification.catalog_sha256,
            revision_source_count=len(verification.revision_sources),
            checkpoint_source_count=len(verification.checkpoint_sources),
        )

    def _run_locked(
        self,
        engine: Engine,
        operation: Callable[[Connection, _LockedSession], MigrationResult],
    ) -> MigrationResult:
        """Run one operation and sanitize operation/cleanup failures separately."""

        result: MigrationResult | None = None
        error_code: MigrationErrorCode | None = None
        cleanup_failed = False
        try:
            try:
                with engine.connect() as connection:
                    identity: _LockedSession | None = None
                    try:
                        identity = self._prepare_and_lock(connection)
                        try:
                            result = operation(connection, identity)
                        except MigrationError as error:
                            error_code = error.code
                        except Exception:
                            error_code = MigrationErrorCode.CONNECTION_FAILED
                        try:
                            self._unlock(connection, identity)
                        except Exception:
                            cleanup_failed = True
                    except MigrationError as error:
                        if identity is None:
                            error_code = error.code
                    except Exception:
                        if identity is None:
                            error_code = MigrationErrorCode.CONNECTION_FAILED
            except MigrationError as error:
                if error_code is None:
                    error_code = error.code
            except Exception:
                if error_code is None:
                    error_code = MigrationErrorCode.CONNECTION_FAILED
        finally:
            try:
                engine.dispose()
            except Exception:
                pass
        if cleanup_failed:
            raise MigrationError(MigrationErrorCode.SESSION_CLEANUP_FAILED)
        if error_code is not None:
            raise MigrationError(error_code)
        if result is None:
            raise MigrationError(MigrationErrorCode.CONNECTION_FAILED)
        return result

    def _status_locked(
        self,
        connection: Connection,
        session_identity: _LockedSession,
        verification: CatalogVerification,
    ) -> MigrationResult:
        self._assert_same_session(connection, session_identity)
        heads = _current_heads(connection)
        if heads == ():
            _assert_empty_database(connection)
            current = "base"
        elif len(heads) == 1 and heads[0] in {item.revision for item in REVISION_SPECS}:
            current = heads[0]
            _validate_installed(connection, current)
        else:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        return self._result("status", False, current, verification)

    def status(self) -> MigrationResult:
        """Return managed base/head status under the migration lock."""

        verification = verify_repository(self._repository_root)
        engine = self._open_engine(verification)
        return self._run_locked(
            engine,
            lambda connection, identity: self._status_locked(
                connection, identity, verification
            ),
        )

    def _upgrade_locked(
        self,
        connection: Connection,
        session_identity: _LockedSession,
        verification: CatalogVerification,
    ) -> MigrationResult:
        self._assert_same_session(connection, session_identity)
        heads = _current_heads(connection)
        revision_ids = [item.revision for item in REVISION_SPECS]
        if heads == ():
            _assert_empty_database(connection)
            if connection.in_transaction():
                connection.commit()
            current_index = -1
        elif len(heads) == 1 and heads[0] in revision_ids:
            current_index = revision_ids.index(heads[0])
            self._reconcile_interrupted_attempt(connection, heads[0], session_identity)
        else:
            raise MigrationError(MigrationErrorCode.GRAPH_MISMATCH)
        if current_index == len(REVISION_SPECS) - 1:
            _validate_installed(connection, HEAD_REVISION)
            return self._result("upgrade", False, HEAD_REVISION, verification)
        with _verified_migration_root(verification) as snapshot_root:
            for revision_index in range(current_index + 1, len(REVISION_SPECS)):
                spec = REVISION_SPECS[revision_index]
                attempt_id = str(uuid.uuid4())
                if revision_index > 0:
                    self._assert_same_session(connection, session_identity)
                    _append_attempt_event(
                        connection,
                        attempt_id=attempt_id,
                        revision_index=revision_index,
                        status="STARTED",
                        error_code=None,
                    )
                configuration = _alembic_config(snapshot_root)
                configuration.attributes.update(
                    {
                        "attempt_id": attempt_id,
                        "connection": connection,
                        "revision_digests": {
                            item.revision: item.sha256 for item in REVISION_SPECS
                        },
                        "revision_stories": {
                            item.revision: item.story_id for item in REVISION_SPECS
                        },
                        "revision_runner_versions": {
                            item.revision: item.runner_version
                            for item in REVISION_SPECS
                        },
                        "revision_server_versions": {
                            item.revision: item.server_version_num
                            for item in REVISION_SPECS
                        },
                    }
                )
                migration_failed = False
                try:
                    self._assert_same_session(connection, session_identity)
                    command.upgrade(configuration, spec.revision)
                    self._assert_same_session(connection, session_identity)
                    if connection.in_transaction():
                        connection.commit()
                    self._assert_same_session(connection, session_identity)
                except Exception:
                    if connection.in_transaction():
                        connection.rollback()
                    if revision_index > 0:
                        try:
                            self._assert_same_session(connection, session_identity)
                            _append_attempt_event(
                                connection,
                                attempt_id=attempt_id,
                                revision_index=revision_index,
                                status="FAILED",
                                error_code="MIGRATION_FAILED",
                            )
                        except Exception:
                            if connection.in_transaction():
                                connection.rollback()
                    migration_failed = True
                if migration_failed:
                    raise MigrationError(MigrationErrorCode.MIGRATION_FAILED)
                _validate_installed(connection, spec.revision)
        return self._result("upgrade", True, HEAD_REVISION, verification)

    def upgrade(self) -> MigrationResult:
        """Upgrade an empty or managed database to the exact framework head."""

        verification = verify_repository(self._repository_root)
        engine = self._open_engine(verification)
        return self._run_locked(
            engine,
            lambda connection, identity: self._upgrade_locked(
                connection, identity, verification
            ),
        )

    def downgrade(self) -> None:
        """Refuse destruction of the retained history anchor."""

        raise MigrationError(MigrationErrorCode.DOWNGRADE_FORBIDDEN)


def verification_result(verification: CatalogVerification) -> MigrationResult:
    """Build the public result for an offline repository verification."""

    return MigrationResult(
        command="verify",
        environment=None,
        changed=False,
        current_revision=HEAD_REVISION,
        catalog_sha256=verification.catalog_sha256,
        revision_source_count=len(verification.revision_sources),
        checkpoint_source_count=len(verification.checkpoint_sources),
    )
