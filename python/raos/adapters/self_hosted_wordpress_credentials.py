"""Owner-private JSON credential storage for self-hosted WordPress."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import errno
import json
import os
from pathlib import Path
import stat
from typing import Any, NoReturn, SupportsIndex, cast, final

from raos.domain.editorial.self_hosted_wordpress import (
    SELF_HOSTED_WORDPRESS_ORIGIN,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    fail_self_hosted_wordpress,
)


MAX_CREDENTIAL_BYTES = 16 * 1024
CREDENTIAL_RELATIVE_PATH = Path(".secrets/wordpress-owner-local/credentials.v1.json")

_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_DIRECTORY_COMPONENTS = (".secrets", "wordpress-owner-local")
_CREDENTIAL_FILE = "credentials.v1.json"
_STATE_DIRECTORY = "state"
_CREDENTIAL_KEYS = frozenset(
    {"schema_version", "site_origin", "username", "application_password"}
)


def _fail(code: SelfHostedWordPressFailureCode) -> NoReturn:
    fail_self_hosted_wordpress(code)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        component in {"", ".", ".."} for component in path.parts[1:]
    ):
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        opened = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if not _same_identity(opened, named) or not stat.S_ISDIR(opened.st_mode):
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        return current
    except BaseException:
        os.close(current)
        raise


def _private_directory(parent_fd: int, name: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    opened = os.fstat(child)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not _same_identity(opened, named)
        or not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != os.getuid()
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_nlink < 2
    ):
        os.close(child)
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    return child


def _open_owner_directory(repository_root: Path, *, create: bool) -> int:
    current = _open_absolute_directory(repository_root)
    try:
        for component in _DIRECTORY_COMPONENTS:
            following = _private_directory(current, component, create=create)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


class _DuplicateKey(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _read_bounded_private_file(directory_fd: int) -> bytes:
    descriptor = os.open(_CREDENTIAL_FILE, _FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_CREDENTIAL_BYTES
        ):
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        payload = os.read(descriptor, MAX_CREDENTIAL_BYTES + 1)
        if len(payload) != before.st_size or len(payload) > MAX_CREDENTIAL_BYTES:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        after = os.fstat(descriptor)
        named = os.stat(_CREDENTIAL_FILE, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not _same_identity(before, after)
            or not _same_identity(after, named)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        return payload
    finally:
        os.close(descriptor)


def _credential_text(
    value: object, *, maximum: int, allow_space: bool, forbid_colon: bool
) -> str:
    if (
        type(value) is not str
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or (forbid_colon and ":" in value)
        or any(
            ord(character) < (0x20 if allow_space else 0x21) or ord(character) > 0x7E
            for character in value
        )
    ):
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    try:
        value.encode("ascii", errors="strict")
    except UnicodeError:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class SelfHostedWordPressCredentials:
    username: str
    _application_password: str

    def __post_init__(self) -> None:
        _credential_text(
            self.username, maximum=128, allow_space=False, forbid_colon=True
        )
        _credential_text(
            self._application_password,
            maximum=4096,
            allow_space=True,
            forbid_colon=False,
        )

    def __repr__(self) -> str:
        return "SelfHostedWordPressCredentials(<redacted>)"

    def __str__(self) -> str:
        return "<redacted-self-hosted-wordpress-credentials>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("credential serialization is disabled")

    def authorization_header(self) -> str:
        raw = f"{self.username}:{self._application_password}".encode(
            "ascii", errors="strict"
        )
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def owner_private_store_payload(self) -> bytes:
        """Return only the fixed installer payload; callers must never log it."""

        try:
            value = (
                json.dumps(
                    {
                        "application_password": self._application_password,
                        "schema_version": 1,
                        "site_origin": SELF_HOSTED_WORDPRESS_ORIGIN,
                        "username": self.username,
                    },
                    ensure_ascii=True,
                    allow_nan=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("ascii")
                + b"\n"
            )
        except UnicodeError, ValueError, TypeError:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        if len(value) > MAX_CREDENTIAL_BYTES:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        return value


def _decode_credentials(raw: bytes) -> SelfHostedWordPressCredentials:
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    if type(value) is not dict:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    mapping = cast(dict[str, object], value)
    if (
        frozenset(mapping) != _CREDENTIAL_KEYS
        or type(mapping["schema_version"]) is not int
        or mapping["schema_version"] != 1
        or mapping["site_origin"] != SELF_HOSTED_WORDPRESS_ORIGIN
    ):
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    return SelfHostedWordPressCredentials(
        username=_credential_text(
            mapping["username"], maximum=128, allow_space=False, forbid_colon=True
        ),
        _application_password=_credential_text(
            mapping["application_password"],
            maximum=4096,
            allow_space=True,
            forbid_colon=False,
        ),
    )


def _credential_payload(credentials: SelfHostedWordPressCredentials) -> bytes:
    if type(credentials) is not SelfHostedWordPressCredentials:
        _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
    return credentials.owner_private_store_payload()


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "private write failed")
        offset += written


@final
class OwnerPrivateSelfHostedWordPressCredentialStore:
    """Metadata-only doctor, exact reader, and exclusive first install."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: object) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        self._repository_root = repository_root

    def metadata_status(self) -> str:
        """Inspect only directory/file metadata; never open credential bytes."""

        directory_fd = -1
        descriptor = -1
        try:
            try:
                directory_fd = _open_owner_directory(
                    self._repository_root, create=False
                )
            except FileNotFoundError:
                return "MISSING"
            names = set(os.listdir(directory_fd))
            if not names <= {_CREDENTIAL_FILE, _STATE_DIRECTORY}:
                _fail(SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID)
            if _CREDENTIAL_FILE not in names:
                return "MISSING"
            descriptor = os.open(_CREDENTIAL_FILE, _FILE_FLAGS, dir_fd=directory_fd)
            opened = os.fstat(descriptor)
            named = os.stat(
                _CREDENTIAL_FILE, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                not _same_identity(opened, named)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or not 1 <= opened.st_size <= MAX_CREDENTIAL_BYTES
            ):
                _fail(SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID)
            return "METADATA_READY"
        except SelfHostedWordPressFailure:
            raise
        except OSError, TypeError, ValueError:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_METADATA_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)

    def read(self) -> SelfHostedWordPressCredentials:
        directory_fd = -1
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=False)
            names = set(os.listdir(directory_fd))
            if _CREDENTIAL_FILE not in names or not names <= {
                _CREDENTIAL_FILE,
                _STATE_DIRECTORY,
            }:
                _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
            return _decode_credentials(_read_bounded_private_file(directory_fd))
        except SelfHostedWordPressFailure:
            raise
        except OSError, TypeError, ValueError:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)

    def install(self, credentials: SelfHostedWordPressCredentials) -> None:
        if type(credentials) is not SelfHostedWordPressCredentials:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        payload = _credential_payload(credentials)
        directory_fd = -1
        descriptor = -1
        temporary = ".credentials.v1.install"
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=True)
            if set(os.listdir(directory_fd)) - {_STATE_DIRECTORY}:
                _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=directory_fd,
            )
            _write_all(descriptor, payload)
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.getuid()
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or opened.st_size != len(payload)
            ):
                _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
            os.link(
                temporary,
                _CREDENTIAL_FILE,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            os.fsync(directory_fd)
            os.unlink(temporary, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except SelfHostedWordPressFailure:
            raise
        except FileExistsError, OSError, TypeError, ValueError:
            _fail(SelfHostedWordPressFailureCode.CREDENTIAL_INSTALL_REFUSED)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                try:
                    os.unlink(temporary, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except OSError:
                    pass
                os.close(directory_fd)


__all__ = [
    "CREDENTIAL_RELATIVE_PATH",
    "MAX_CREDENTIAL_BYTES",
    "OwnerPrivateSelfHostedWordPressCredentialStore",
    "SelfHostedWordPressCredentials",
]
