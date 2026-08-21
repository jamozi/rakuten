"""Owner-private filesystem and fixed direct-HTTPS adapters for ST-0505."""

from __future__ import annotations

from dataclasses import dataclass
import ctypes
import errno
import hashlib
import http.client
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import ssl
import stat
from typing import Any, NoReturn, Protocol, cast, final, runtime_checkable
from urllib.parse import quote, urlencode

from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    LIVE_ITEM_SEARCH_ELEMENTS_V1,
    LiveItemSearchSortV1,
    RakutenItemSearchLiveRequestV1,
)
from raos.domain.catalog.rakuten_owner_local import (
    RAKUTEN_OWNER_LOCAL_HOST,
    RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES,
    RAKUTEN_OWNER_LOCAL_PORT,
    RAKUTEN_OWNER_LOCAL_PROFILE,
    RakutenOwnerLocalApi,
    RakutenOwnerLocalApiDefinition,
    RakutenOwnerLocalCredentials,
    RakutenOwnerLocalFailure,
    RakutenOwnerLocalFailureCode,
    RakutenOwnerLocalItemSearchRequest,
    RakutenOwnerLocalNormalizedRecord,
    RakutenOwnerLocalProductSearchRequest,
    RakutenOwnerLocalProductSort,
    RakutenOwnerLocalProviderResult,
    RakutenOwnerLocalRequest,
    RakutenOwnerLocalRequestDisposition,
    RakutenOwnerLocalResultEnvelope,
    api_definition,
    exact_response_selector,
    fail_owner_local,
    normalized_record,
)


CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
MAX_CREDENTIAL_BYTES = 16 * 1024
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESULT_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 50_000

_OWNER_DIRECTORY = (".secrets", "rakuten-owner-local")
_CREDENTIAL_FILE = "credentials.v1.json"
_RESULT_DIRECTORY = "results"
_CREDENTIAL_KEYS = frozenset(
    {
        "schema_version",
        "profile",
        "application_id",
        "access_key",
        "affiliate_id",
    }
)
_ITEM_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "keyword",
        "shop_code",
        "item_code",
        "genre_id",
        "hits",
        "page",
        "sort",
    }
)
_PRODUCT_REQUEST_KEYS = frozenset(
    {
        "schema_version",
        "keyword",
        "genre_id",
        "product_id",
        "product_code",
        "hits",
        "page",
        "sort",
    }
)
_SUMMARY_KEYS = frozenset({"count", "page", "first", "last", "hits", "pageCount"})
_PRODUCT_COLLECTION_ALIASES = frozenset({"items", "products"})
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_CONTENT_LENGTH = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_CHUNKED = re.compile(r"chunked\Z", re.ASCII | re.IGNORECASE)
_TLS_OVERRIDE_ENVIRONMENT = frozenset(
    {"SSL_CERT_DIR", "SSL_CERT_FILE", "SSLKEYLOGFILE"}
)
_PROXY_ENVIRONMENT = frozenset(
    {
        "ALL_PROXY",
        "HTTPS_PROXY",
        "HTTP_PROXY",
        "NO_PROXY",
        "all_proxy",
        "https_proxy",
        "http_proxy",
        "no_proxy",
    }
)
_RESULT_RECOVERY_BYTES = b"RAOS_ST0505_OWNER_LOCAL_RESULT_RECOVERY_REQUIRED_V1\n"
_CREDENTIAL_RECOVERY_FILE = ".credential-recovery-required"
_CREDENTIAL_RECOVERY_BYTES = (
    b"RAOS_ST0505_OWNER_LOCAL_CREDENTIAL_RECOVERY_REQUIRED_V1\n"
)
_RENAME_EXCHANGE = 2
_ACCESS_HEADER = "access" + "Key"
_ACCESS_RECORD_KEY = "access" + "_key"
_ACCEPT = "application/json"
_USER_AGENT = "RAOS-ST-0505-owner-local/1"


def _fail(
    code: RakutenOwnerLocalFailureCode,
    *,
    disposition: RakutenOwnerLocalRequestDisposition = (
        RakutenOwnerLocalRequestDisposition.NOT_SENT
    ),
    api: RakutenOwnerLocalApi | None = None,
    request_fingerprint: str | None = None,
    http_status: int | None = None,
    body_byte_count: int | None = None,
    response_sha256: str | None = None,
) -> NoReturn:
    fail_owner_local(
        code,
        disposition=disposition,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=http_status,
        body_byte_count=body_byte_count,
        response_sha256=response_sha256,
    )


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _open_absolute_directory(
    path: Path, *, failure: RakutenOwnerLocalFailureCode
) -> int:
    if not path.is_absolute() or any(
        component in {"", ".", ".."} for component in path.parts[1:]
    ):
        _fail(failure)
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        opened = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if not _same_identity(opened, named) or not stat.S_ISDIR(opened.st_mode):
            _fail(failure)
        return current
    except BaseException:
        os.close(current)
        raise


def _private_directory(
    parent_fd: int,
    name: str,
    *,
    create: bool,
    failure: RakutenOwnerLocalFailureCode,
) -> int:
    if not name or "/" in name or name in {".", ".."}:
        _fail(failure)
    if create:
        try:
            os.mkdir(name, mode=0o700, dir_fd=parent_fd)
            os.fsync(parent_fd)
        except FileExistsError:
            pass
    child = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    details = os.fstat(child)
    named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not _same_identity(details, named)
        or not stat.S_ISDIR(details.st_mode)
        or details.st_uid != os.getuid()
        or stat.S_IMODE(details.st_mode) != 0o700
        or details.st_nlink < 2
    ):
        os.close(child)
        _fail(failure)
    return child


def _open_owner_directory(repository_root: Path, *, create: bool) -> int:
    current = _open_absolute_directory(
        repository_root, failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID
    )
    try:
        for component in _OWNER_DIRECTORY:
            following = _private_directory(
                current,
                component,
                create=create,
                failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
            )
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _read_bounded_file(
    directory_fd: int,
    name: str,
    maximum: int,
    *,
    failure: RakutenOwnerLocalFailureCode,
) -> bytes:
    descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
        ):
            _fail(failure)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        os.lseek(descriptor, 0, os.SEEK_SET)
        verification_chunks: list[bytes] = []
        verification_remaining = maximum + 1
        while verification_remaining:
            chunk = os.read(descriptor, min(verification_remaining, 64 * 1024))
            if not chunk:
                break
            verification_chunks.append(chunk)
            verification_remaining -= len(chunk)
        verification = b"".join(verification_chunks)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(payload) > maximum
            or len(verification) > maximum
            or len(payload) != before.st_size
            or verification != payload
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            _fail(failure)
        return payload
    finally:
        os.close(descriptor)


class _DuplicateKey(ValueError):
    pass


class _NonfiniteValue(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise _DuplicateKey
        value[key] = item
    return value


def _strict_json(raw: bytes, *, failure: RakutenOwnerLocalFailureCode) -> object:
    try:
        text = raw.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(_NonfiniteValue()),
        )
    except RakutenOwnerLocalFailure:
        raise
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail(failure)


def _valid_secret(value: object, *, maximum: int) -> bytes:
    if (
        type(value) is not str
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    try:
        return value.encode("ascii", errors="strict")
    except UnicodeError:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)


def _decode_credentials(raw: bytes) -> RakutenOwnerLocalCredentials:
    value = _strict_json(
        raw, failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID
    )
    if type(value) is not dict:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    mapping = cast(dict[str, object], value)
    if (
        frozenset(mapping) != _CREDENTIAL_KEYS
        or type(mapping["schema_version"]) is not int
        or mapping["schema_version"] != 1
        or type(mapping["profile"]) is not str
        or mapping["profile"] != RAKUTEN_OWNER_LOCAL_PROFILE
    ):
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    return RakutenOwnerLocalCredentials(
        profile=RAKUTEN_OWNER_LOCAL_PROFILE,
        _application_id=_valid_secret(mapping["application_id"], maximum=256),
        _access_key=_valid_secret(mapping["access_key"], maximum=4096),
        _affiliate_id=_valid_secret(mapping["affiliate_id"], maximum=256),
    )


def _credential_payload(credentials: RakutenOwnerLocalCredentials) -> bytes:
    if type(credentials) is not RakutenOwnerLocalCredentials:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    payload = {
        "schema_version": 1,
        "profile": RAKUTEN_OWNER_LOCAL_PROFILE,
        "application_id": credentials.application_id_query_value(),
        _ACCESS_RECORD_KEY: credentials.access_key_header_value(),
        "affiliate_id": credentials.affiliate_id_query_value(),
    }
    try:
        encoded = (
            json.dumps(
                payload,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
            + b"\n"
        )
    except UnicodeError, ValueError, TypeError:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    if len(encoded) > MAX_CREDENTIAL_BYTES:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
    return encoded


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if written <= 0:
            raise OSError(errno.EIO, "private write failed")
        offset += written


def _open_anonymous_private_file(directory_fd: int, payload: bytes) -> int:
    anonymous_flag = getattr(os, "O_TMPFILE", 0)
    if not anonymous_flag:
        raise OSError(errno.ENOTSUP, "anonymous inode unavailable")
    descriptor = os.open(
        ".",
        os.O_WRONLY | anonymous_flag | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        _write_all(descriptor, payload)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        details = os.fstat(descriptor)
        if (
            not stat.S_ISREG(details.st_mode)
            or details.st_uid != os.getuid()
            or stat.S_IMODE(details.st_mode) != 0o600
            or details.st_nlink != 0
            or details.st_size != len(payload)
        ):
            raise OSError(errno.EIO, "anonymous inode validation failed")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _validate_published_file(
    directory_fd: int, name: str, descriptor: int, expected_size: int
) -> None:
    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    current = os.fstat(descriptor)
    if (
        not stat.S_ISREG(named.st_mode)
        or not stat.S_ISREG(current.st_mode)
        or named.st_uid != os.getuid()
        or stat.S_IMODE(named.st_mode) != 0o600
        or named.st_nlink != 1
        or named.st_size != expected_size
        or not _same_identity(named, current)
        or current.st_nlink != 1
    ):
        raise OSError(errno.EIO, "private publication validation failed")


def _rename_exchange(directory_fd: int, left: str, right: str) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as error:
        raise OSError(errno.ENOSYS, "renameat2 unavailable") from error
    renameat2.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    renameat2.restype = ctypes.c_int
    result = renameat2(
        directory_fd,
        os.fsencode(left),
        directory_fd,
        os.fsencode(right),
        _RENAME_EXCHANGE,
    )
    if result != 0:
        value = ctypes.get_errno()
        raise OSError(value, os.strerror(value))


def _credential_store_has_recovery(directory_fd: int) -> bool:
    return any(
        name == _CREDENTIAL_RECOVERY_FILE or name.startswith(".rotate-")
        for name in os.listdir(directory_fd)
    )


def _validate_owner_inventory(directory_fd: int) -> None:
    names = set(os.listdir(directory_fd))
    if _CREDENTIAL_FILE not in names or not names <= {
        _CREDENTIAL_FILE,
        _RESULT_DIRECTORY,
    }:
        _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)


def _write_credential_recovery_marker(directory_fd: int) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            _CREDENTIAL_RECOVERY_FILE,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, _CREDENTIAL_RECOVERY_BYTES)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@final
class OwnerPrivateRakutenOwnerLocalCredentialReader:
    """Read the exact fixed owner-local record through stable descriptors."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def read(self) -> RakutenOwnerLocalCredentials:
        directory_fd = -1
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=False)
            if _credential_store_has_recovery(directory_fd):
                _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
            _validate_owner_inventory(directory_fd)
            raw = _read_bounded_file(
                directory_fd,
                _CREDENTIAL_FILE,
                MAX_CREDENTIAL_BYTES,
                failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
            )
            return _decode_credentials(raw)
        except RakutenOwnerLocalFailure:
            raise
        except OSError, UnicodeError, ValueError, TypeError:
            _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)


@final
class OwnerPrivateRakutenOwnerLocalCredentialStore:
    """Setup once or atomically exchange a validated private credential record."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def setup_ready(self) -> None:
        """Validate setup metadata without creating directories or reading values."""

        root_fd = -1
        secrets_fd = -1
        owner_fd = -1
        try:
            root_fd = _open_absolute_directory(
                self._repository_root,
                failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
            )
            try:
                secrets_fd = _private_directory(
                    root_fd,
                    _OWNER_DIRECTORY[0],
                    create=False,
                    failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                )
            except FileNotFoundError:
                return
            try:
                owner_fd = _private_directory(
                    secrets_fd,
                    _OWNER_DIRECTORY[1],
                    create=False,
                    failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                )
            except FileNotFoundError:
                return
            if os.listdir(owner_fd):
                _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        except RakutenOwnerLocalFailure:
            raise
        except OSError, TypeError, ValueError:
            _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if owner_fd >= 0:
                os.close(owner_fd)
            if secrets_fd >= 0:
                os.close(secrets_fd)
            if root_fd >= 0:
                os.close(root_fd)

    def rotate_ready(self) -> None:
        """Validate existing record metadata without reading credential bytes."""

        directory_fd = -1
        descriptor = -1
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=False)
            if _credential_store_has_recovery(directory_fd):
                _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
            _validate_owner_inventory(directory_fd)
            descriptor = os.open(_CREDENTIAL_FILE, _FILE_FLAGS, dir_fd=directory_fd)
            details = os.fstat(descriptor)
            named = os.stat(
                _CREDENTIAL_FILE, dir_fd=directory_fd, follow_symlinks=False
            )
            if (
                not _same_identity(details, named)
                or not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 1
                or not 1 <= details.st_size <= MAX_CREDENTIAL_BYTES
            ):
                _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        except RakutenOwnerLocalFailure:
            raise
        except OSError, TypeError, ValueError:
            _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)

    def setup(self, credentials: RakutenOwnerLocalCredentials) -> None:
        self.setup_ready()
        payload = _credential_payload(credentials)
        directory_fd = -1
        descriptor = -1
        linked = False
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=True)
            descriptor = _open_anonymous_private_file(directory_fd, payload)
            os.link(
                f"/proc/self/fd/{descriptor}",
                _CREDENTIAL_FILE,
                dst_dir_fd=directory_fd,
                follow_symlinks=True,
            )
            linked = True
            _validate_published_file(
                directory_fd, _CREDENTIAL_FILE, descriptor, len(payload)
            )
            os.fsync(directory_fd)
            _decode_credentials(
                _read_bounded_file(
                    directory_fd,
                    _CREDENTIAL_FILE,
                    MAX_CREDENTIAL_BYTES,
                    failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                )
            )
        except RakutenOwnerLocalFailure:
            if linked and directory_fd >= 0:
                try:
                    os.unlink(_CREDENTIAL_FILE, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except OSError:
                    _write_credential_recovery_marker(directory_fd)
            raise
        except BaseException:
            if linked and directory_fd >= 0:
                try:
                    os.unlink(_CREDENTIAL_FILE, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except OSError:
                    _write_credential_recovery_marker(directory_fd)
            _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)

    def rotate(self, credentials: RakutenOwnerLocalCredentials) -> None:
        self.rotate_ready()
        payload = _credential_payload(credentials)
        directory_fd = -1
        descriptor = -1
        stage_name = f".rotate-{os.getpid()}-{os.urandom(16).hex()}"
        staged = False
        exchanged = False
        publication_needs_recovery = False
        try:
            directory_fd = _open_owner_directory(self._repository_root, create=False)
            _decode_credentials(
                _read_bounded_file(
                    directory_fd,
                    _CREDENTIAL_FILE,
                    MAX_CREDENTIAL_BYTES,
                    failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                )
            )
            descriptor = _open_anonymous_private_file(directory_fd, payload)
            os.link(
                f"/proc/self/fd/{descriptor}",
                stage_name,
                dst_dir_fd=directory_fd,
                follow_symlinks=True,
            )
            staged = True
            _validate_published_file(directory_fd, stage_name, descriptor, len(payload))
            os.fsync(directory_fd)
            _rename_exchange(directory_fd, stage_name, _CREDENTIAL_FILE)
            exchanged = True
            publication_needs_recovery = True
            _validate_published_file(
                directory_fd, _CREDENTIAL_FILE, descriptor, len(payload)
            )
            _decode_credentials(
                _read_bounded_file(
                    directory_fd,
                    _CREDENTIAL_FILE,
                    MAX_CREDENTIAL_BYTES,
                    failure=RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID,
                )
            )
            os.fsync(directory_fd)
            os.unlink(stage_name, dir_fd=directory_fd)
            staged = False
            exchanged = False
            os.fsync(directory_fd)
            publication_needs_recovery = False
        except BaseException:
            if exchanged and directory_fd >= 0:
                try:
                    _rename_exchange(directory_fd, stage_name, _CREDENTIAL_FILE)
                    exchanged = False
                    os.fsync(directory_fd)
                    publication_needs_recovery = False
                except OSError:
                    _write_credential_recovery_marker(directory_fd)
            if staged and directory_fd >= 0 and not exchanged:
                try:
                    os.unlink(stage_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except OSError:
                    _write_credential_recovery_marker(directory_fd)
            if exchanged and directory_fd >= 0:
                _write_credential_recovery_marker(directory_fd)
            if publication_needs_recovery and directory_fd >= 0:
                _write_credential_recovery_marker(directory_fd)
            _fail(RakutenOwnerLocalFailureCode.CREDENTIAL_STORE_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if directory_fd >= 0:
                os.close(directory_fd)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
    return value


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
    return value


def _decode_item_request(mapping: dict[str, object]) -> RakutenOwnerLocalRequest:
    if frozenset(mapping) != _ITEM_REQUEST_KEYS:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
    try:
        sort = LiveItemSearchSortV1(mapping["sort"])
        policy = RakutenItemSearchLiveRequestV1(
            api_version="2026-07-01",
            format_version=2,
            keyword=_optional_text(mapping["keyword"]),
            shop_code=_optional_text(mapping["shop_code"]),
            item_code=_optional_text(mapping["item_code"]),
            genre_id=_optional_int(mapping["genre_id"]),
            hits=cast(int, mapping["hits"]),
            page=cast(int, mapping["page"]),
            sort=sort,
            elements=LIVE_ITEM_SEARCH_ELEMENTS_V1,
            min_price_jpy=None,
            max_price_jpy=None,
            or_flag=False,
            availability=True,
            postage_included_only=False,
            has_review_only=False,
            appoint_delivery_date_only=False,
            attribute_flag=False,
            genre_information_flag=False,
        )
        return RakutenOwnerLocalItemSearchRequest(policy=policy)
    except RakutenOwnerLocalFailure:
        raise
    except BaseException:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)


def _decode_product_request(mapping: dict[str, object]) -> RakutenOwnerLocalRequest:
    if frozenset(mapping) != _PRODUCT_REQUEST_KEYS:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
    try:
        sort_value = mapping["sort"]
        if type(sort_value) is not str:
            _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
        return RakutenOwnerLocalProductSearchRequest(
            keyword=_optional_text(mapping["keyword"]),
            genre_id=_optional_int(mapping["genre_id"]),
            product_id=_optional_text(mapping["product_id"]),
            product_code=_optional_text(mapping["product_code"]),
            hits=cast(int, mapping["hits"]),
            page=cast(int, mapping["page"]),
            sort=RakutenOwnerLocalProductSort(sort_value),
        )
    except RakutenOwnerLocalFailure:
        raise
    except BaseException:
        _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)


@final
class OwnerPrivateRakutenOwnerLocalRequestReader:
    """Read one absolute owner-only JSON request without following symlinks."""

    __slots__ = ()

    def read(self, path: Path, api: RakutenOwnerLocalApi) -> RakutenOwnerLocalRequest:
        if not path.is_absolute() or type(api) is not RakutenOwnerLocalApi:
            _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
        directory_fd = -1
        try:
            directory_fd = _open_absolute_directory(
                path.parent, failure=RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID
            )
            raw = _read_bounded_file(
                directory_fd,
                path.name,
                MAX_REQUEST_BYTES,
                failure=RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID,
            )
            value = _strict_json(
                raw, failure=RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID
            )
            if type(value) is not dict:
                _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
            mapping = cast(dict[str, object], value)
            if (
                type(mapping.get("schema_version")) is not int
                or mapping["schema_version"] != 1
            ):
                _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
            if api is RakutenOwnerLocalApi.ITEM_SEARCH:
                return _decode_item_request(mapping)
            if api is RakutenOwnerLocalApi.PRODUCT_SEARCH:
                return _decode_product_request(mapping)
            _fail(RakutenOwnerLocalFailureCode.API_NOT_ALLOWED)
        except RakutenOwnerLocalFailure:
            raise
        except OSError, UnicodeError, ValueError, TypeError:
            _fail(RakutenOwnerLocalFailureCode.REQUEST_FILE_INVALID)
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)


def require_clean_rakuten_owner_local_environment() -> None:
    """Reject ambient proxy discovery and TLS trust/key-log overrides."""

    if any(
        name in os.environ for name in _TLS_OVERRIDE_ENVIRONMENT | _PROXY_ENVIRONMENT
    ):
        _fail(RakutenOwnerLocalFailureCode.TLS_ENVIRONMENT_INVALID)


@runtime_checkable
class RakutenOwnerLocalHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class RakutenOwnerLocalHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(self, method: str, path: str, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> RakutenOwnerLocalHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class RakutenOwnerLocalHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenOwnerLocalHttpsConnection: ...


@dataclass(frozen=True, slots=True)
class _ResolvedAddress:
    family: int
    socket_type: int
    protocol: int
    socket_address: tuple[str, int] | tuple[str, int, int, int]
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address


def _public_ip(
    value: object, *, family: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    if (
        (family == socket.AF_INET and type(address) is not ipaddress.IPv4Address)
        or (family == socket.AF_INET6 and type(address) is not ipaddress.IPv6Address)
        or not address.is_global
        or address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or getattr(address, "is_site_local", False)
        or (
            type(address) is ipaddress.IPv6Address
            and (address.ipv4_mapped is not None or address.scope_id is not None)
        )
    ):
        _fail(RakutenOwnerLocalFailureCode.DNS_ADDRESS_REJECTED)
    return address


def _validated_resolved_address(row: object) -> _ResolvedAddress:
    if type(row) is not tuple:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    values = cast(tuple[object, ...], row)
    if len(values) != 5:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    family_value, socket_type_value, protocol_value, canonical_name, address_value = (
        values
    )
    if (
        not isinstance(family_value, int)
        or type(family_value) is bool
        or not isinstance(socket_type_value, int)
        or type(socket_type_value) is bool
        or not isinstance(protocol_value, int)
        or type(protocol_value) is bool
        or type(canonical_name) is not str
        or type(address_value) is not tuple
    ):
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    family = int(family_value)
    socket_type = int(socket_type_value)
    protocol = int(protocol_value)
    socket_address = cast(tuple[object, ...], address_value)
    if (
        family not in {socket.AF_INET, socket.AF_INET6}
        or socket_type != socket.SOCK_STREAM
        or protocol != socket.IPPROTO_TCP
    ):
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    if family == socket.AF_INET:
        if (
            len(socket_address) != 2
            or type(socket_address[1]) is not int
            or socket_address[1] != RAKUTEN_OWNER_LOCAL_PORT
        ):
            _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    elif (
        len(socket_address) != 4
        or type(socket_address[1]) is not int
        or socket_address[1] != RAKUTEN_OWNER_LOCAL_PORT
        or type(socket_address[2]) is not int
        or socket_address[2] != 0
        or type(socket_address[3]) is not int
        or socket_address[3] != 0
    ):
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    address = _public_ip(socket_address[0], family=family)
    canonical: tuple[str, int] | tuple[str, int, int, int]
    if family == socket.AF_INET:
        canonical = (str(address), RAKUTEN_OWNER_LOCAL_PORT)
    else:
        canonical = (str(address), RAKUTEN_OWNER_LOCAL_PORT, 0, 0)
    return _ResolvedAddress(
        family=family,
        socket_type=socket_type,
        protocol=protocol,
        socket_address=canonical,
        ip=address,
    )


def _resolve_public_rakuten_addresses(
    host: str, port: int
) -> tuple[_ResolvedAddress, ...]:
    if host != RAKUTEN_OWNER_LOCAL_HOST or port != RAKUTEN_OWNER_LOCAL_PORT:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    try:
        rows = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
            flags=0,
        )
    except OSError, UnicodeError, ValueError, TypeError:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    if type(rows) is not list or not rows:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    # Materialize all rows before selecting the first. One unsafe row vetoes all.
    return tuple(_validated_resolved_address(row) for row in rows)


def _require_exact_peer(candidate: _ResolvedAddress, peer: object) -> None:
    if type(peer) is not tuple:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    values = cast(tuple[object, ...], peer)
    if len(values) not in {2, 4}:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    if (
        type(values[1]) is not int
        or values[1] != RAKUTEN_OWNER_LOCAL_PORT
        or (candidate.family == socket.AF_INET and len(values) != 2)
        or (candidate.family == socket.AF_INET6 and len(values) != 4)
        or (
            len(values) == 4
            and (
                type(values[2]) is not int
                or type(values[3]) is not int
                or values[3] != 0
            )
        )
    ):
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)
    if _public_ip(values[0], family=candidate.family) != candidate.ip:
        _fail(RakutenOwnerLocalFailureCode.DNS_FAILED)


@dataclass(slots=True)
class _PinnedSocketConnector:
    candidate: _ResolvedAddress
    _attempted: bool = False

    def __call__(
        self,
        address: tuple[str, int],
        timeout: object,
        source_address: tuple[str, int] | None,
    ) -> socket.socket:
        if (
            self._attempted
            or address != (RAKUTEN_OWNER_LOCAL_HOST, RAKUTEN_OWNER_LOCAL_PORT)
            or timeout != CONNECT_TIMEOUT_SECONDS
            or source_address is not None
        ):
            _fail(RakutenOwnerLocalFailureCode.CONNECTION_FAILED)
        self._attempted = True
        connection = socket.socket(
            self.candidate.family,
            self.candidate.socket_type,
            self.candidate.protocol,
        )
        try:
            connection.settimeout(CONNECT_TIMEOUT_SECONDS)
            connection.connect(self.candidate.socket_address)
            _require_exact_peer(self.candidate, connection.getpeername())
            return connection
        except BaseException:
            connection.close()
            raise


@final
class _SystemHttpsConnection:
    __slots__ = ("_candidate", "_connection")

    def __init__(
        self, connection: http.client.HTTPSConnection, candidate: _ResolvedAddress
    ) -> None:
        self._connection = connection
        self._candidate = candidate

    def connect(self) -> None:
        if getattr(self._connection, "_tunnel_host", None) is not None:
            _fail(RakutenOwnerLocalFailureCode.CONNECTION_FAILED)
        try:
            self._connection.connect()
            if self._connection.sock is None:
                _fail(RakutenOwnerLocalFailureCode.CONNECTION_FAILED)
            _require_exact_peer(self._candidate, self._connection.sock.getpeername())
        except BaseException:
            self._connection.close()
            raise

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None or seconds != READ_TIMEOUT_SECONDS:
            _fail(RakutenOwnerLocalFailureCode.CONNECTION_FAILED)
        self._connection.sock.settimeout(seconds)

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self._connection.request(method, path, body=None, headers=headers)

    def getresponse(self) -> RakutenOwnerLocalHttpsResponse:
        return cast(RakutenOwnerLocalHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemRakutenOwnerLocalHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenOwnerLocalHttpsConnection:
        if (
            host != RAKUTEN_OWNER_LOCAL_HOST
            or port != RAKUTEN_OWNER_LOCAL_PORT
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(RakutenOwnerLocalFailureCode.TLS_CONTEXT_INVALID)
        candidates = _resolve_public_rakuten_addresses(host, port)
        candidate = candidates[0]
        connection = http.client.HTTPSConnection(
            host=host,
            port=port,
            timeout=connect_timeout_seconds,
            context=tls_context,
        )
        setattr(connection, "_create_connection", _PinnedSocketConnector(candidate))
        return _SystemHttpsConnection(connection, candidate)


def _read_bounded_response(response: RakutenOwnerLocalHttpsResponse) -> bytes:
    content_length_value = response.getheader("Content-Length")
    transfer_encoding = response.getheader("Transfer-Encoding")
    if transfer_encoding is not None:
        if (
            type(transfer_encoding) is not str
            or _CHUNKED.fullmatch(transfer_encoding) is None
            or content_length_value is not None
        ):
            _fail(
                RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
            )
        expected_length: int | None = None
    elif content_length_value is None:
        expected_length = None
    else:
        if (
            type(content_length_value) is not str
            or _CONTENT_LENGTH.fullmatch(content_length_value) is None
        ):
            _fail(
                RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
            )
        try:
            expected_length = int(content_length_value, 10)
        except ValueError:
            _fail(
                RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
            )
        if expected_length > RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES:
            _fail(
                RakutenOwnerLocalFailureCode.RESPONSE_OVERSIZED,
                disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
            )
    chunks: list[bytes] = []
    remaining = RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES + 1
    while remaining:
        chunk = response.read(min(remaining, 64 * 1024))
        if type(chunk) is not bytes:
            _fail(
                RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
            )
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > RAKUTEN_OWNER_LOCAL_MAX_RESPONSE_BYTES:
        _fail(
            RakutenOwnerLocalFailureCode.RESPONSE_OVERSIZED,
            disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
        )
    if expected_length is not None and len(body) != expected_length:
        _fail(
            RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
            disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
        )
    return body


def _response_failure(
    code: RakutenOwnerLocalFailureCode,
    *,
    api: RakutenOwnerLocalApi,
    request_fingerprint: str,
    status: int,
    body: bytes,
) -> NoReturn:
    _fail(
        code,
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=status,
        body_byte_count=len(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
    )


def _valid_json_content_type(value: object) -> bool:
    if type(value) is not str or value != value.strip():
        return False
    parts = value.split(";")
    if not parts or parts[0].strip().lower() != "application/json":
        return False
    parameters: dict[str, str] = {}
    for part in parts[1:]:
        name, separator, parameter = part.partition("=")
        name = name.strip().lower()
        parameter = parameter.strip().lower()
        if not separator or not name or name in parameters:
            return False
        parameters[name] = parameter
    return not parameters or parameters == {"charset": "utf-8"}


def _json_response_failure(
    code: RakutenOwnerLocalFailureCode,
    *,
    api: RakutenOwnerLocalApi,
    request_fingerprint: str,
    body: bytes,
) -> NoReturn:
    _fail(
        code,
        disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
        api=api,
        request_fingerprint=request_fingerprint,
        http_status=200,
        body_byte_count=len(body),
        response_sha256=hashlib.sha256(body).hexdigest(),
    )


def _parse_response_json(
    body: bytes, *, api: RakutenOwnerLocalApi, request_fingerprint: str
) -> object:
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeError:
        _json_response_failure(
            RakutenOwnerLocalFailureCode.RESPONSE_ENCODING_INVALID,
            api=api,
            request_fingerprint=request_fingerprint,
            body=body,
        )
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda ignored: (_ for _ in ()).throw(_NonfiniteValue()),
        )
    except _DuplicateKey:
        _json_response_failure(
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_DUPLICATE_KEY,
            api=api,
            request_fingerprint=request_fingerprint,
            body=body,
        )
    except _NonfiniteValue:
        _json_response_failure(
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_NONFINITE,
            api=api,
            request_fingerprint=request_fingerprint,
            body=body,
        )
    except json.JSONDecodeError, RecursionError, ValueError, TypeError:
        _json_response_failure(
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_INVALID,
            api=api,
            request_fingerprint=request_fingerprint,
            body=body,
        )
    stack: list[tuple[object, int]] = [(value, 1)]
    nodes = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES or depth > MAX_JSON_DEPTH:
            _json_response_failure(
                RakutenOwnerLocalFailureCode.RESPONSE_JSON_TREE_INVALID,
                api=api,
                request_fingerprint=request_fingerprint,
                body=body,
            )
        if current is None or type(current) in {bool, int, str}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _json_response_failure(
                    RakutenOwnerLocalFailureCode.RESPONSE_JSON_NONFINITE,
                    api=api,
                    request_fingerprint=request_fingerprint,
                    body=body,
                )
            continue
        if type(current) is list:
            stack.extend((member, depth + 1) for member in cast(list[object], current))
            continue
        if type(current) is dict:
            mapping = cast(dict[object, object], current)
            if any(type(key) is not str for key in mapping):
                _json_response_failure(
                    RakutenOwnerLocalFailureCode.RESPONSE_JSON_TREE_INVALID,
                    api=api,
                    request_fingerprint=request_fingerprint,
                    body=body,
                )
            stack.extend((member, depth + 1) for member in mapping.values())
            continue
        _json_response_failure(
            RakutenOwnerLocalFailureCode.RESPONSE_JSON_TREE_INVALID,
            api=api,
            request_fingerprint=request_fingerprint,
            body=body,
        )
    return value


def _request_hits(request: RakutenOwnerLocalRequest) -> int:
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        return request.policy.hits
    if type(request) is RakutenOwnerLocalProductSearchRequest:
        return request.hits
    _fail(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)


def _collection(
    api: RakutenOwnerLocalApi, root: dict[str, object]
) -> tuple[str, list[object]]:
    if api is RakutenOwnerLocalApi.ITEM_SEARCH:
        collection_key = "items"
        if frozenset(root) != _SUMMARY_KEYS | {collection_key}:
            _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
    else:
        aliases = frozenset(root) & _PRODUCT_COLLECTION_ALIASES
        if len(aliases) != 1 or frozenset(root) != _SUMMARY_KEYS | aliases:
            _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
        collection_key = next(iter(aliases))
    value = root[collection_key]
    if type(value) is not list:
        _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
    return collection_key, cast(list[object], value)


def _unwrap_record(api: RakutenOwnerLocalApi, value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
    del api
    return cast(dict[str, object], value)


def _validate_exact_selector(
    request: RakutenOwnerLocalRequest,
    record: dict[str, object],
) -> None:
    selector = exact_response_selector(request)
    if selector is None:
        return
    field, requested_value = selector
    returned_value = record.get(field)
    if type(returned_value) is not str or not returned_value:
        _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
    if returned_value != requested_value:
        _fail(RakutenOwnerLocalFailureCode.RESULT_MISMATCH)


def _parse_provider_success(
    definition: RakutenOwnerLocalApiDefinition,
    request: RakutenOwnerLocalRequest,
    body: bytes,
) -> RakutenOwnerLocalProviderResult:
    api = definition.api
    fingerprint = request.fingerprint
    try:
        value = _parse_response_json(body, api=api, request_fingerprint=fingerprint)
        if type(value) is not dict:
            _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
        root = cast(dict[str, object], value)
        _collection_name, values = _collection(api, root)
        for name in _SUMMARY_KEYS:
            if type(root[name]) is not int:
                _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
        count = cast(int, root["count"])
        page = cast(int, root["page"])
        first = cast(int, root["first"])
        last = cast(int, root["last"])
        hits = cast(int, root["hits"])
        page_count = cast(int, root["pageCount"])
        if (
            count < 0
            or page != 1
            or first < 0
            or last < 0
            or hits != _request_hits(request)
            or not 0 <= page_count <= 100
            or len(values) > hits
        ):
            _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
        record_count = len(values)
        if (
            count < record_count
            or (count == 0) != (record_count == 0)
            or (page_count == 0) != (record_count == 0)
            or first != (1 if record_count else 0)
            or last != record_count
        ):
            _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
        definition_record_fields = frozenset(definition.elements) - _SUMMARY_KEYS
        normalized_fields = frozenset(definition.normalized_record_fields)
        mandatory = {
            RakutenOwnerLocalApi.ITEM_SEARCH: frozenset(
                {"affiliateUrl", "itemCode", "itemName", "itemPrice", "itemUrl"}
            ),
            RakutenOwnerLocalApi.PRODUCT_SEARCH: frozenset(
                {"affiliateUrl", "productCode", "productId", "productUrlPC"}
            ),
        }[api]
        records: list[RakutenOwnerLocalNormalizedRecord] = []
        for member in values:
            raw_record = _unwrap_record(api, member)
            names = frozenset(raw_record)
            if (
                not names <= definition_record_fields
                or not mandatory <= names
                or not names.isdisjoint(
                    {"reviewAverage", "reviewCount", "affiliateRate"}
                )
            ):
                _fail(RakutenOwnerLocalFailureCode.RESPONSE_SCHEMA_DRIFT)
            _validate_exact_selector(request, raw_record)
            projected = {
                name: item
                for name, item in raw_record.items()
                if name in normalized_fields
            }
            records.append(normalized_record(api, projected))
        return RakutenOwnerLocalProviderResult(
            api=api,
            request_fingerprint=fingerprint,
            http_status=200,
            body_byte_count=len(body),
            response_sha256=hashlib.sha256(body).hexdigest(),
            count=count,
            page=page,
            first=first,
            last=last,
            hits=hits,
            page_count=page_count,
            records=tuple(records),
        )
    except RakutenOwnerLocalFailure as failure:
        if failure.api is not None:
            raise
        _fail(
            failure.code,
            disposition=RakutenOwnerLocalRequestDisposition.RESPONSE_RECEIVED,
            api=api,
            request_fingerprint=fingerprint,
            http_status=200,
            body_byte_count=len(body),
            response_sha256=hashlib.sha256(body).hexdigest(),
        )


def _query_parameters(
    request: RakutenOwnerLocalRequest, credentials: RakutenOwnerLocalCredentials
) -> tuple[tuple[str, str], ...]:
    common: list[tuple[str, str]] = [
        ("applicationId", credentials.application_id_query_value()),
        ("affiliateId", credentials.affiliate_id_query_value()),
    ]
    if type(request) is RakutenOwnerLocalItemSearchRequest:
        policy = request.policy
        item_selectors = (
            ("keyword", policy.keyword),
            ("shopCode", policy.shop_code),
            ("itemCode", policy.item_code),
            ("genreId", policy.genre_id),
        )
        common.extend(
            (name, str(value)) for name, value in item_selectors if value is not None
        )
        common.extend(
            (
                ("hits", str(policy.hits)),
                ("page", "1"),
                ("format", "json"),
                ("formatVersion", "2"),
                ("sort", policy.sort.value),
                ("availability", "1"),
                (
                    "elements",
                    ",".join(element.value for element in policy.elements),
                ),
            )
        )
        return tuple(common)
    if type(request) is RakutenOwnerLocalProductSearchRequest:
        product_selectors = (
            ("keyword", request.keyword),
            ("genreId", request.genre_id),
            ("productId", request.product_id),
            ("productCode", request.product_code),
        )
        common.extend(
            (name, str(value)) for name, value in product_selectors if value is not None
        )
        common.extend(
            (
                ("hits", str(request.hits)),
                ("page", "1"),
                ("format", "json"),
                ("formatVersion", "2"),
                ("sort", request.sort.value),
                (
                    "elements",
                    ",".join(api_definition(request.api).elements),
                ),
            )
        )
        return tuple(common)
    _fail(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)


_HTTP_FAILURES = {
    400: RakutenOwnerLocalFailureCode.HTTP_400,
    401: RakutenOwnerLocalFailureCode.HTTP_401,
    403: RakutenOwnerLocalFailureCode.HTTP_403,
    404: RakutenOwnerLocalFailureCode.HTTP_404,
    429: RakutenOwnerLocalFailureCode.HTTP_429,
    500: RakutenOwnerLocalFailureCode.HTTP_500,
    503: RakutenOwnerLocalFailureCode.HTTP_503,
}


@dataclass(slots=True)
class DirectRakutenOwnerLocalTransport:
    """Issue one direct fixed-origin GET; retry, redirect, and fallback do not exist."""

    connection_factory: RakutenOwnerLocalHttpsConnectionFactory
    _attempted: bool = False

    def execute(
        self,
        definition: RakutenOwnerLocalApiDefinition,
        request: RakutenOwnerLocalRequest,
        credentials: RakutenOwnerLocalCredentials,
    ) -> RakutenOwnerLocalProviderResult:
        if self._attempted:
            _fail(RakutenOwnerLocalFailureCode.REQUEST_ALREADY_ATTEMPTED)
        self._attempted = True
        if (
            type(definition) is not RakutenOwnerLocalApiDefinition
            or type(request)
            not in {
                RakutenOwnerLocalItemSearchRequest,
                RakutenOwnerLocalProductSearchRequest,
            }
            or type(credentials) is not RakutenOwnerLocalCredentials
            or request.api is not definition.api
            or definition != api_definition(request.api)
        ):
            _fail(RakutenOwnerLocalFailureCode.INVALID_ARGUMENT)
        require_clean_rakuten_owner_local_environment()
        try:
            context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except OSError, ssl.SSLError, ValueError:
            _fail(RakutenOwnerLocalFailureCode.TLS_CONTEXT_INVALID)
        query = urlencode(
            _query_parameters(request, credentials),
            doseq=False,
            safe=",",
            quote_via=quote,
        )
        target = f"{definition.path}?{query}"
        headers = {
            "Accept": _ACCEPT,
            "Host": RAKUTEN_OWNER_LOCAL_HOST,
            "User-Agent": _USER_AGENT,
            _ACCESS_HEADER: credentials.access_key_header_value(),
        }
        connection: RakutenOwnerLocalHttpsConnection | None = None
        request_started = False
        try:
            connection = self.connection_factory.open(
                host=RAKUTEN_OWNER_LOCAL_HOST,
                port=RAKUTEN_OWNER_LOCAL_PORT,
                connect_timeout_seconds=CONNECT_TIMEOUT_SECONDS,
                tls_context=context,
            )
            connection.connect()
            connection.set_read_timeout(READ_TIMEOUT_SECONDS)
            request_started = True
            connection.request("GET", target, headers)
            response = connection.getresponse()
            if type(response.status) is not int or not 100 <= response.status <= 599:
                _fail(
                    RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS,
                    disposition=RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS,
                )
            body = _read_bounded_response(response)
            status = response.status
            if status != 200:
                code = _HTTP_FAILURES.get(status)
                if 300 <= status <= 399:
                    code = RakutenOwnerLocalFailureCode.HTTP_REDIRECT_REJECTED
                if code is None:
                    code = RakutenOwnerLocalFailureCode.HTTP_STATUS_UNEXPECTED
                _response_failure(
                    code,
                    api=definition.api,
                    request_fingerprint=request.fingerprint,
                    status=status,
                    body=body,
                )
            if not _valid_json_content_type(response.getheader("Content-Type")):
                _response_failure(
                    RakutenOwnerLocalFailureCode.RESPONSE_CONTENT_TYPE_INVALID,
                    api=definition.api,
                    request_fingerprint=request.fingerprint,
                    status=status,
                    body=body,
                )
            return _parse_provider_success(definition, request, body)
        except RakutenOwnerLocalFailure as failure:
            if (
                failure.disposition
                is RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
                and failure.api is None
            ):
                _fail(
                    failure.code,
                    disposition=failure.disposition,
                    api=definition.api,
                    request_fingerprint=request.fingerprint,
                )
            raise
        except BaseException as error:
            if request_started:
                code = RakutenOwnerLocalFailureCode.REQUEST_AMBIGUOUS
                disposition = RakutenOwnerLocalRequestDisposition.OUTCOME_AMBIGUOUS
            elif isinstance(error, (ssl.SSLError, ssl.CertificateError)):
                code = RakutenOwnerLocalFailureCode.TLS_FAILED
                disposition = RakutenOwnerLocalRequestDisposition.NOT_SENT
            elif isinstance(error, (TimeoutError, socket.timeout)):
                code = RakutenOwnerLocalFailureCode.TIMEOUT
                disposition = RakutenOwnerLocalRequestDisposition.NOT_SENT
            elif isinstance(error, socket.gaierror):
                code = RakutenOwnerLocalFailureCode.DNS_FAILED
                disposition = RakutenOwnerLocalRequestDisposition.NOT_SENT
            else:
                code = RakutenOwnerLocalFailureCode.CONNECTION_FAILED
                disposition = RakutenOwnerLocalRequestDisposition.NOT_SENT
            _fail(
                code,
                disposition=disposition,
                api=definition.api,
                request_fingerprint=request.fingerprint,
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass


def _result_store_has_recovery(directory_fd: int) -> bool:
    return any(
        name.startswith(".preflight-") or name.endswith(".recovery-required")
        for name in os.listdir(directory_fd)
    )


def _write_result_recovery_marker(directory_fd: int, run_id: str) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            f"{run_id}.recovery-required",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        _write_all(descriptor, _RESULT_RECOVERY_BYTES)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _fail_result_store(envelope: RakutenOwnerLocalResultEnvelope) -> NoReturn:
    if type(envelope) is not RakutenOwnerLocalResultEnvelope:
        _fail(RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID)
    result = envelope.provider_result
    failure = envelope.failure
    _fail(
        RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
        disposition=envelope.disposition,
        api=envelope.api,
        request_fingerprint=envelope.request_fingerprint,
        http_status=(
            result.http_status
            if result is not None
            else failure.http_status
            if failure is not None
            else None
        ),
        body_byte_count=(
            result.body_byte_count
            if result is not None
            else failure.body_byte_count
            if failure is not None
            else None
        ),
        response_sha256=(
            result.response_sha256
            if result is not None
            else failure.response_sha256
            if failure is not None
            else None
        ),
    )


def _result_payload(envelope: RakutenOwnerLocalResultEnvelope) -> bytes:
    if type(envelope) is not RakutenOwnerLocalResultEnvelope:
        _fail(RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID)
    try:
        payload = (
            json.dumps(
                envelope.as_result_object(),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )
    except RakutenOwnerLocalFailure:
        raise
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail_result_store(envelope)
    if not 1 <= len(payload) <= MAX_RESULT_BYTES:
        _fail_result_store(envelope)
    return payload


@final
class OwnerPrivateRakutenOwnerLocalResultWriter:
    """Atomically publish one sanitized mode-0600 result without replacement."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def doctor_ready(self) -> None:
        """Check result-store metadata without creating or publishing an inode."""

        owner_fd = -1
        result_fd = -1
        try:
            owner_fd = _open_owner_directory(self._repository_root, create=False)
            if not getattr(os, "O_TMPFILE", 0):
                raise OSError(errno.ENOTSUP, "anonymous result inode unavailable")
            try:
                result_fd = _private_directory(
                    owner_fd,
                    _RESULT_DIRECTORY,
                    create=False,
                    failure=RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
                )
            except FileNotFoundError:
                return
            if _result_store_has_recovery(result_fd):
                raise OSError(errno.EIO, "result recovery required")
        except BaseException:
            _fail(RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID)
        finally:
            if result_fd >= 0:
                os.close(result_fd)
            if owner_fd >= 0:
                os.close(owner_fd)

    def preflight(self) -> None:
        """Prove anonymous no-replace publication and rollback before a GET."""

        owner_fd = -1
        result_fd = -1
        descriptor = -1
        target = ""
        linked = False
        try:
            owner_fd = _open_owner_directory(self._repository_root, create=False)
            result_fd = _private_directory(
                owner_fd,
                _RESULT_DIRECTORY,
                create=True,
                failure=RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
            )
            if _result_store_has_recovery(result_fd):
                raise OSError(errno.EIO, "result recovery required")
            descriptor = _open_anonymous_private_file(result_fd, b"")
            target = f".preflight-{os.getpid()}-{os.urandom(16).hex()}"
            os.link(
                f"/proc/self/fd/{descriptor}",
                target,
                dst_dir_fd=result_fd,
                follow_symlinks=True,
            )
            linked = True
            _validate_published_file(result_fd, target, descriptor, 0)
            os.fsync(result_fd)
            os.unlink(target, dir_fd=result_fd)
            linked = False
            os.fsync(result_fd)
            if os.fstat(descriptor).st_nlink != 0:
                raise OSError(errno.EIO, "result preflight rollback failed")
        except BaseException:
            if linked and result_fd >= 0 and target:
                try:
                    os.unlink(target, dir_fd=result_fd)
                    os.fsync(result_fd)
                except OSError:
                    pass
            _fail(RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if result_fd >= 0:
                os.close(result_fd)
            if owner_fd >= 0:
                os.close(owner_fd)

    def write(self, envelope: RakutenOwnerLocalResultEnvelope) -> None:
        payload = _result_payload(envelope)
        owner_fd = -1
        result_fd = -1
        descriptor = -1
        target = f"{envelope.run_id}.json"
        linked = False
        try:
            owner_fd = _open_owner_directory(self._repository_root, create=False)
            result_fd = _private_directory(
                owner_fd,
                _RESULT_DIRECTORY,
                create=True,
                failure=RakutenOwnerLocalFailureCode.RESULT_STORE_INVALID,
            )
            if _result_store_has_recovery(result_fd):
                _fail_result_store(envelope)
            descriptor = _open_anonymous_private_file(result_fd, payload)
            os.link(
                f"/proc/self/fd/{descriptor}",
                target,
                dst_dir_fd=result_fd,
                follow_symlinks=True,
            )
            linked = True
            _validate_published_file(result_fd, target, descriptor, len(payload))
            os.fsync(result_fd)
        except RakutenOwnerLocalFailure:
            if linked and result_fd >= 0:
                try:
                    os.unlink(target, dir_fd=result_fd)
                    os.fsync(result_fd)
                    linked = False
                except OSError:
                    _write_result_recovery_marker(result_fd, envelope.run_id)
            _fail_result_store(envelope)
        except BaseException:
            if linked and result_fd >= 0:
                try:
                    os.unlink(target, dir_fd=result_fd)
                    os.fsync(result_fd)
                    linked = False
                except OSError:
                    _write_result_recovery_marker(result_fd, envelope.run_id)
            _fail_result_store(envelope)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if result_fd >= 0:
                os.close(result_fd)
            if owner_fd >= 0:
                os.close(owner_fd)


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "DirectRakutenOwnerLocalTransport",
    "MAX_CREDENTIAL_BYTES",
    "MAX_REQUEST_BYTES",
    "MAX_RESULT_BYTES",
    "OwnerPrivateRakutenOwnerLocalCredentialReader",
    "OwnerPrivateRakutenOwnerLocalCredentialStore",
    "OwnerPrivateRakutenOwnerLocalRequestReader",
    "OwnerPrivateRakutenOwnerLocalResultWriter",
    "READ_TIMEOUT_SECONDS",
    "RakutenOwnerLocalHttpsConnection",
    "RakutenOwnerLocalHttpsConnectionFactory",
    "RakutenOwnerLocalHttpsResponse",
    "SystemRakutenOwnerLocalHttpsConnectionFactory",
    "require_clean_rakuten_owner_local_environment",
]
