"""Explicit owner-local PostgreSQL engine factory for Google analytics import."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from collections.abc import Callable
from typing import Any, Final, NoReturn, SupportsIndex, final

import psycopg
import sqlalchemy as sa
from sqlalchemy.engine import Engine, URL
from sqlalchemy.pool import NullPool

from raos.domain.analytics.google_live import (
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    fail_google,
)


_IDENTIFIER: Final = re.compile(r"[a-z_][a-z0-9_]{0,62}\Z", re.ASCII)
_AMBIENT_PG: Final = re.compile(r"PG[A-Z0-9_]*\Z", re.ASCII)


def _layout_failure() -> NoReturn:
    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _validate_endpoint(*, host: object, port: object, database: object, user: object) -> None:
    if (
        type(host) is not str
        or not host
        or type(port) is not int
        or not 1024 <= port <= 65535
        or type(database) is not str
        or _IDENTIFIER.fullmatch(database) is None
        or type(user) is not str
        or _IDENTIFIER.fullmatch(user) is None
    ):
        _layout_failure()
    if host.startswith("/"):
        try:
            host_path = Path(host)
            metadata = host_path.lstat()
            if (
                Path(os.path.abspath(host_path)) != host_path.resolve(strict=True)
                or not stat.S_ISDIR(metadata.st_mode)
                or stat.S_ISLNK(metadata.st_mode)
            ):
                _layout_failure()
        except GoogleProviderFailure:
            raise
        except OSError:
            _layout_failure()
    elif host not in {"127.0.0.1", "::1"}:
        _layout_failure()


def _is_runtime_path(value: object) -> bool:
    """Keep the local credential boundary defensive for untyped callers."""

    return isinstance(value, Path)


@dataclass(frozen=True, slots=True, repr=False)
class LocalGoogleAnalyticsDatabaseTarget:
    host: str
    port: int
    database: str
    user: str
    password_file: Path

    def __post_init__(self) -> None:
        _validate_endpoint(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
        )
        if (
            not _is_runtime_path(self.password_file)
            or not self.password_file.is_absolute()
        ):
            _layout_failure()


def _password_text(payload: object) -> str:
    if type(payload) is not bytes or not 1 <= len(payload) <= 1024:
        _layout_failure()
    content = payload
    if content.endswith(b"\n"):
        content = content[:-1]
    if not content or b"\x00" in content or b"\r" in content or b"\n" in content:
        _layout_failure()
    try:
        return content.decode("utf-8", errors="strict")
    except UnicodeError:
        _layout_failure()


@final
class OwnerPrivateDatabaseCredentialSnapshot:
    """Immutable credential value already read through an owner-private boundary."""

    __value: str
    __slots__ = ("__value",)

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or not value
            or "\x00" in value
            or "\r" in value
            or "\n" in value
        ):
            _layout_failure()
        try:
            encoded_size = len(value.encode("utf-8"))
        except UnicodeError:
            _layout_failure()
        if encoded_size > 1024:
            _layout_failure()
        object.__setattr__(self, "_OwnerPrivateDatabaseCredentialSnapshot__value", value)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("owner-private credential snapshots are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("owner-private credential snapshots are immutable")

    def __repr__(self) -> str:
        return "OwnerPrivateDatabaseCredentialSnapshot(<redacted>)"

    def connect_local_database(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
    ) -> Any:
        """Use the snapshot as a local connection capability without exposing it."""

        _validate_endpoint(host=host, port=port, database=database, user=user)
        _reject_ambient_postgres_configuration()
        return _connect_postgres(
            host=host,
            port=port,
            database=database,
            user=user,
            db_value=self.__value,
        )

    def __reduce_ex__(self, _protocol: SupportsIndex, /) -> NoReturn:
        """Credential snapshots must not cross a serialization boundary."""

        raise TypeError("owner-private credential snapshots are not serializable")


def seal_owner_private_database_credential(
    payload: bytes,
) -> OwnerPrivateDatabaseCredentialSnapshot:
    """Seal one already-validated owner-private file snapshot for live use."""

    return OwnerPrivateDatabaseCredentialSnapshot(_password_text(payload))


@final
class SealedLocalGoogleAnalyticsDatabaseTarget:
    host: str
    port: int
    database: str
    user: str
    credential: OwnerPrivateDatabaseCredentialSnapshot
    __slots__ = ("host", "port", "database", "user", "credential")

    def __init__(
        self,
        *,
        host: str,
        port: int,
        database: str,
        user: str,
        credential: OwnerPrivateDatabaseCredentialSnapshot,
    ) -> None:
        _validate_endpoint(
            host=host,
            port=port,
            database=database,
            user=user,
        )
        if type(credential) is not OwnerPrivateDatabaseCredentialSnapshot:
            _layout_failure()
        object.__setattr__(self, "host", host)
        object.__setattr__(self, "port", port)
        object.__setattr__(self, "database", database)
        object.__setattr__(self, "user", user)
        object.__setattr__(self, "credential", credential)

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("sealed database targets are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("sealed database targets are immutable")

    def __repr__(self) -> str:
        return "SealedLocalGoogleAnalyticsDatabaseTarget(<redacted>)"

    def __reduce_ex__(self, _protocol: SupportsIndex, /) -> NoReturn:
        raise TypeError("sealed database targets are not serializable")

    def connect_local_database(self) -> Any:
        """Open one bounded local connection without revealing the snapshot."""

        return self.credential.connect_local_database(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
        )


def _reject_ambient_postgres_configuration() -> None:
    if any(_AMBIENT_PG.fullmatch(name) for name in os.environ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _read_owner_password(path: Path) -> str:
    try:
        lexical = Path(os.path.abspath(path))
        resolved = path.resolve(strict=True)
        parent = path.parent.lstat()
        metadata = path.lstat()
    except OSError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    if (
        lexical != resolved
        or path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or metadata.st_nlink != 1
        or not 1 <= metadata.st_size <= 1024
        or not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != os.geteuid()
        or stat.S_IMODE(parent.st_mode) != 0o700
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        payload = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
    except OSError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if (
        len(payload) != before.st_size
        or (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns)
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return _password_text(payload)


def _connect_postgres(
    *,
    host: str,
    port: int,
    database: str,
    user: str,
    db_value: str,
) -> Any:
    try:
        return psycopg.connect(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=db_value,
            sslmode="disable",
            connect_timeout=5,
            application_name="raos-google-live-import",
            options=(
                "-c lock_timeout=5000ms "
                "-c statement_timeout=300000ms "
                "-c idle_in_transaction_session_timeout=60000ms "
                "-c timezone=UTC "
                "-c search_path=pg_catalog"
            ),
        )
    except GoogleProviderFailure:
        raise
    except Exception:
        fail_google(GoogleProviderFailureCode.PERSISTENCE_FAILED)


def _create_engine(*, connector: Callable[[], Any]) -> Engine:
    def connect() -> Any:
        _reject_ambient_postgres_configuration()
        return connector()

    return sa.create_engine(
        URL.create("postgresql+psycopg"),
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
    )


def create_local_google_analytics_engine(
    target: LocalGoogleAnalyticsDatabaseTarget,
) -> Engine:
    """Compatibility factory; live refreshes must use the sealed factory below."""

    if type(target) is not LocalGoogleAnalyticsDatabaseTarget:
        _layout_failure()
    _reject_ambient_postgres_configuration()

    def connect_compatibility_target() -> Any:
        db_value = _read_owner_password(target.password_file)
        return _connect_postgres(
            host=target.host,
            port=target.port,
            database=target.database,
            user=target.user,
            db_value=db_value,
        )

    return _create_engine(connector=connect_compatibility_target)


def create_sealed_local_google_analytics_engine(
    target: SealedLocalGoogleAnalyticsDatabaseTarget,
) -> Engine:
    """Create a live engine that never reopens an owner-private credential path."""

    if type(target) is not SealedLocalGoogleAnalyticsDatabaseTarget:
        _layout_failure()
    _reject_ambient_postgres_configuration()
    return _create_engine(connector=target.connect_local_database)


__all__ = [
    "LocalGoogleAnalyticsDatabaseTarget",
    "OwnerPrivateDatabaseCredentialSnapshot",
    "SealedLocalGoogleAnalyticsDatabaseTarget",
    "create_local_google_analytics_engine",
    "create_sealed_local_google_analytics_engine",
    "seal_owner_private_database_credential",
]
