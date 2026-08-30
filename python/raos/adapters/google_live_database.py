"""Explicit owner-local PostgreSQL engine factory for Google analytics import."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import stat
from typing import Any, Final

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
        if (
            type(self.host) is not str
            or not self.host
            or type(self.port) is not int
            or not 1024 <= self.port <= 65535
            or type(self.database) is not str
            or _IDENTIFIER.fullmatch(self.database) is None
            or type(self.user) is not str
            or _IDENTIFIER.fullmatch(self.user) is None
            or not _is_runtime_path(self.password_file)
            or not self.password_file.is_absolute()
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        if self.host.startswith("/"):
            try:
                host = Path(self.host)
                metadata = host.lstat()
                if (
                    Path(os.path.abspath(host)) != host.resolve(strict=True)
                    or not stat.S_ISDIR(metadata.st_mode)
                    or stat.S_ISLNK(metadata.st_mode)
                ):
                    fail_google(
                        GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID
                    )
            except GoogleProviderFailure:
                raise
            except OSError:
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        elif self.host not in {"127.0.0.1", "::1"}:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


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
    if payload.endswith(b"\n"):
        payload = payload[:-1]
    if not payload or b"\x00" in payload or b"\r" in payload or b"\n" in payload:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    try:
        return payload.decode("utf-8", errors="strict")
    except UnicodeError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def create_local_google_analytics_engine(
    target: LocalGoogleAnalyticsDatabaseTarget,
) -> Engine:
    """Create a NullPool engine without accepting a DSN or ambient PG settings."""

    if type(target) is not LocalGoogleAnalyticsDatabaseTarget:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    _reject_ambient_postgres_configuration()

    def connect() -> Any:
        _reject_ambient_postgres_configuration()
        password = _read_owner_password(target.password_file)
        try:
            return psycopg.connect(
                host=target.host,
                port=target.port,
                dbname=target.database,
                user=target.user,
                password=password,
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

    return sa.create_engine(
        URL.create("postgresql+psycopg"),
        creator=connect,
        poolclass=NullPool,
        hide_parameters=True,
    )


__all__ = [
    "LocalGoogleAnalyticsDatabaseTarget",
    "create_local_google_analytics_engine",
]
