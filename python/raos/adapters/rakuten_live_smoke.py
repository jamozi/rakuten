"""Fixed credential, HTTPS, and report adapters for ST-0505."""

from __future__ import annotations

from dataclasses import dataclass
import errno
import hashlib
import http.client
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import ssl
import stat
from typing import Any, NoReturn, Protocol, cast, final, runtime_checkable
from urllib.parse import quote, urlencode

from raos.application.catalog.rakuten_live_smoke import MAX_RESPONSE_BYTES
from raos.domain.catalog.rakuten_item_search_live_request_v1 import (
    RakutenItemSearchLiveRequestV1,
)
from raos.domain.catalog.rakuten_live_smoke import (
    RAKUTEN_LIVE_SMOKE_ACCEPT,
    RAKUTEN_LIVE_SMOKE_ACCESS_HEADER,
    RAKUTEN_LIVE_SMOKE_HOST,
    RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS,
    RAKUTEN_LIVE_SMOKE_PATH,
    RAKUTEN_LIVE_SMOKE_USER_AGENT,
    RakutenLiveSmokeAuthClassification,
    RakutenLiveSmokeCredentials,
    RakutenLiveSmokeDiagnosticCode,
    RakutenLiveSmokeFailure,
    RakutenLiveSmokeHttpResponse,
    RakutenLiveSmokeReport,
    RakutenLiveSmokeRateClassification,
    RakutenLiveSmokeSchemaClassification,
    fail_rakuten_live_smoke,
    fixed_rakuten_live_smoke_policy,
)


CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 20
MAX_CREDENTIAL_BYTES = 16 * 1024
MAX_STAGING_BINDING_BYTES = 4 * 1024
_PORT = 443
_CREDENTIAL_DIRECTORY = (".secrets", "rakuten-live-smoke")
_CREDENTIAL_FILE = "credentials.v1.json"
_STAGING_BINDING_FILE = "staging-credential-binding.v1.json"
_REPORT_DIRECTORY = "reports"
_CREDENTIAL_KEYS = frozenset(
    {"schema_version", "application_id", "access_key", "affiliate_id"}
)
_STAGING_BINDING_KEYS = frozenset(
    {
        "schema_version",
        "environment",
        "credential_purpose",
        "credential_record_sha256",
    }
)
_STAGING_ENVIRONMENT = "staging"
_STAGING_CREDENTIAL_PURPOSE = "DEDICATED_TEST_CREDENTIAL_FOR_NON_FORMAL_DIAGNOSTIC"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
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
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_REPORT_RECOVERY_BYTES = b"RAOS_ST0505_REPORT_RECOVERY_REQUIRED_V1\n"


def _fail(code: RakutenLiveSmokeDiagnosticCode, *, request_count: int = 0) -> NoReturn:
    fail_rakuten_live_smoke(code, request_count=request_count)


def require_clean_rakuten_live_smoke_environment() -> None:
    """Reject trust, key-log, and proxy discovery overrides."""

    if any(
        name in os.environ for name in _TLS_OVERRIDE_ENVIRONMENT | _PROXY_ENVIRONMENT
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.TLS_ENVIRONMENT_INVALID)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        part in {"", ".", ".."} for part in path.parts[1:]
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    current = os.open("/", _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        opened = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if not _same_identity(opened, named):
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        return current
    except BaseException:
        os.close(current)
        raise


def _private_directory(parent_fd: int, name: str, *, create: bool = False) -> int:
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
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    return child


def _open_smoke_directory(repository_root: Path) -> int:
    current = _open_absolute_directory(repository_root)
    try:
        for component in _CREDENTIAL_DIRECTORY:
            following = _private_directory(current, component)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _read_bounded_file(directory_fd: int, name: str, maximum: int) -> bytes:
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
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        os.lseek(descriptor, 0, os.SEEK_SET)
        verification_chunks: list[bytes] = []
        verification_remaining = maximum + 1
        while verification_remaining:
            chunk = os.read(
                descriptor,
                min(verification_remaining, 64 * 1024),
            )
            if not chunk:
                break
            verification_chunks.append(chunk)
            verification_remaining -= len(chunk)
        verification = b"".join(verification_chunks)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(data) > maximum
            or len(verification) > maximum
            or len(data) != before.st_size
            or verification != data
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or after.st_size != before.st_size
            or after.st_mtime_ns != before.st_mtime_ns
            or after.st_ctime_ns != before.st_ctime_ns
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        return data
    finally:
        os.close(descriptor)


def _write_report_recovery_marker(directory_fd: int, run_id: str) -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            f"{run_id}.recovery-required",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        offset = 0
        while offset < len(_REPORT_RECOVERY_BYTES):
            written = os.write(descriptor, _REPORT_RECOVERY_BYTES[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "report recovery marker write failed")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.fsync(directory_fd)
    except OSError:
        pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _report_store_has_recovery(directory_fd: int) -> bool:
    return any(
        name.startswith(".preflight-") or name.endswith(".recovery-required")
        for name in os.listdir(directory_fd)
    )


def _fail_report_store(report: RakutenLiveSmokeReport) -> NoReturn:
    fail_rakuten_live_smoke(
        RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID,
        http_status=report.http_status,
        body_byte_count=report.body_byte_count,
        response_sha256=report.response_sha256,
        request_count=report.request_count,
        auth=report.auth_classification,
        schema=report.schema_classification,
        rate=report.rate_classification,
        affiliate_url_present=report.affiliate_url_present,
    )


def _credential_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        value[key] = item
    return value


def _decode_owner_private_json(raw: bytes) -> dict[str, object]:
    try:
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(
            decoded,
            object_pairs_hook=_credential_pairs,
            parse_constant=lambda ignored: _fail(
                RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID
            ),
        )
    except RakutenLiveSmokeFailure:
        raise
    except UnicodeError, ValueError, RecursionError, TypeError:
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    if type(value) is not dict:
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    return cast(dict[str, object], value)


def _staging_binding_digest(binding_raw: bytes) -> str:
    mapping = _decode_owner_private_json(binding_raw)
    digest = mapping.get("credential_record_sha256")
    if (
        frozenset(mapping) != _STAGING_BINDING_KEYS
        or type(mapping.get("schema_version")) is not int
        or mapping["schema_version"] != 1
        or mapping.get("environment") != _STAGING_ENVIRONMENT
        or mapping.get("credential_purpose") != _STAGING_CREDENTIAL_PURPOSE
        or type(digest) is not str
        or _SHA256.fullmatch(digest) is None
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    return digest


def _valid_secret(value: object, *, maximum: int) -> bytes:
    if (
        type(value) is not str
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value)
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
    try:
        return value.encode("ascii", errors="strict")
    except UnicodeError:
        _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)


@final
class OwnerPrivateRakutenLiveSmokeCredentialReader:
    """Descriptor-bound reader for the one fixed 0600 JSON record."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def read(self) -> RakutenLiveSmokeCredentials:
        try:
            directory_fd = _open_smoke_directory(self._repository_root)
        except RakutenLiveSmokeFailure:
            raise
        except RakutenLiveSmokeFailure, OSError, ValueError, TypeError:
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        try:
            binding_raw = _read_bounded_file(
                directory_fd,
                _STAGING_BINDING_FILE,
                MAX_STAGING_BINDING_BYTES,
            )
            binding_digest = _staging_binding_digest(binding_raw)
            raw = _read_bounded_file(
                directory_fd, _CREDENTIAL_FILE, MAX_CREDENTIAL_BYTES
            )
        except RakutenLiveSmokeFailure:
            raise
        except OSError, UnicodeError, ValueError, TypeError:
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        finally:
            os.close(directory_fd)
        if binding_digest != hashlib.sha256(raw).hexdigest():
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        mapping = _decode_owner_private_json(raw)
        if frozenset(mapping) != _CREDENTIAL_KEYS:
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        if type(mapping["schema_version"]) is not int or mapping["schema_version"] != 1:
            _fail(RakutenLiveSmokeDiagnosticCode.CREDENTIAL_STORE_INVALID)
        return RakutenLiveSmokeCredentials(
            _application_id=_valid_secret(mapping["application_id"], maximum=256),
            _access_key=_valid_secret(mapping["access_key"], maximum=4096),
            _affiliate_id=_valid_secret(mapping["affiliate_id"], maximum=256),
        )


@runtime_checkable
class RakutenLiveSmokeHttpsResponse(Protocol):
    status: int

    def getheader(self, name: str, default: str | None = None) -> str | None: ...

    def read(self, amount: int | None = None) -> bytes: ...


@runtime_checkable
class RakutenLiveSmokeHttpsConnection(Protocol):
    def connect(self) -> None: ...

    def set_read_timeout(self, seconds: int) -> None: ...

    def request(self, method: str, path: str, headers: dict[str, str]) -> None: ...

    def getresponse(self) -> RakutenLiveSmokeHttpsResponse: ...

    def close(self) -> None: ...


@runtime_checkable
class RakutenLiveSmokeHttpsConnectionFactory(Protocol):
    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenLiveSmokeHttpsConnection: ...


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
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
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
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    return address


def _validated_resolved_address(row: object) -> _ResolvedAddress:
    if type(row) is not tuple:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    values = cast(tuple[object, ...], row)
    if len(values) != 5:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
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
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    family = int(family_value)
    socket_type = int(socket_type_value)
    protocol = int(protocol_value)
    socket_address = cast(tuple[object, ...], address_value)
    if (
        family not in {socket.AF_INET, socket.AF_INET6}
        or socket_type != socket.SOCK_STREAM
        or protocol != socket.IPPROTO_TCP
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    if family == socket.AF_INET:
        if (
            len(socket_address) != 2
            or type(socket_address[1]) is not int
            or socket_address[1] != _PORT
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    elif (
        len(socket_address) != 4
        or type(socket_address[1]) is not int
        or socket_address[1] != _PORT
        or type(socket_address[2]) is not int
        or socket_address[2] != 0
        or type(socket_address[3]) is not int
        or socket_address[3] != 0
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    address = _public_ip(socket_address[0], family=family)
    canonical_socket_address: tuple[str, int] | tuple[str, int, int, int]
    if family == socket.AF_INET:
        canonical_socket_address = (str(address), _PORT)
    else:
        canonical_socket_address = (str(address), _PORT, 0, 0)
    return _ResolvedAddress(
        family=family,
        socket_type=socket_type,
        protocol=protocol,
        socket_address=canonical_socket_address,
        ip=address,
    )


def _resolve_public_rakuten_addresses(
    host: str, port: int
) -> tuple[_ResolvedAddress, ...]:
    if host != RAKUTEN_LIVE_SMOKE_HOST or port != _PORT:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
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
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    if type(rows) is not list or not rows:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    return tuple(_validated_resolved_address(row) for row in rows)


def _require_exact_peer(candidate: _ResolvedAddress, peer: object) -> None:
    if type(peer) is not tuple:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    peer_tuple = cast(tuple[object, ...], peer)
    if len(peer_tuple) not in {2, 4}:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    if (
        type(peer_tuple[1]) is not int
        or peer_tuple[1] != _PORT
        or (candidate.family == socket.AF_INET and len(peer_tuple) != 2)
        or (candidate.family == socket.AF_INET6 and len(peer_tuple) != 4)
        or (
            len(peer_tuple) == 4
            and (
                type(peer_tuple[2]) is not int
                or type(peer_tuple[3]) is not int
                or peer_tuple[3] != 0
            )
        )
    ):
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)
    if _public_ip(peer_tuple[0], family=candidate.family) != candidate.ip:
        _fail(RakutenLiveSmokeDiagnosticCode.DNS_FAILED)


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
            or address != (RAKUTEN_LIVE_SMOKE_HOST, _PORT)
            or timeout != CONNECT_TIMEOUT_SECONDS
            or source_address is not None
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED)
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
        self,
        connection: http.client.HTTPSConnection,
        candidate: _ResolvedAddress,
    ) -> None:
        self._connection = connection
        self._candidate = candidate

    def connect(self) -> None:
        if getattr(self._connection, "_tunnel_host", None) is not None:
            _fail(RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED)
        try:
            self._connection.connect()
            if self._connection.sock is None:
                _fail(RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED)
            _require_exact_peer(self._candidate, self._connection.sock.getpeername())
        except BaseException:
            self._connection.close()
            raise

    def set_read_timeout(self, seconds: int) -> None:
        if self._connection.sock is None:
            _fail(RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED)
        self._connection.sock.settimeout(seconds)

    def request(self, method: str, path: str, headers: dict[str, str]) -> None:
        self._connection.request(method, path, body=None, headers=headers)

    def getresponse(self) -> RakutenLiveSmokeHttpsResponse:
        return cast(RakutenLiveSmokeHttpsResponse, self._connection.getresponse())

    def close(self) -> None:
        self._connection.close()


@final
class SystemRakutenLiveSmokeHttpsConnectionFactory:
    __slots__ = ()

    def open(
        self,
        *,
        host: str,
        port: int,
        connect_timeout_seconds: int,
        tls_context: ssl.SSLContext,
    ) -> RakutenLiveSmokeHttpsConnection:
        if (
            host != RAKUTEN_LIVE_SMOKE_HOST
            or port != _PORT
            or connect_timeout_seconds != CONNECT_TIMEOUT_SECONDS
            or type(tls_context) is not ssl.SSLContext
            or tls_context.verify_mode != ssl.CERT_REQUIRED
            or not tls_context.check_hostname
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.TLS_CONTEXT_INVALID)
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


def _read_bounded_response(
    response: RakutenLiveSmokeHttpsResponse, *, http_status: int
) -> bytes:
    content_length_value = response.getheader("Content-Length")
    transfer_encoding = response.getheader("Transfer-Encoding")
    if transfer_encoding is not None:
        if (
            type(transfer_encoding) is not str
            or _CHUNKED.fullmatch(transfer_encoding) is None
            or content_length_value is not None
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS, request_count=1)
        expected_length: int | None = None
    elif content_length_value is None:
        expected_length = None
    else:
        if (
            type(content_length_value) is not str
            or _CONTENT_LENGTH.fullmatch(content_length_value) is None
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS, request_count=1)
        try:
            expected_length = int(content_length_value, 10)
        except ValueError:
            _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS, request_count=1)
    chunks: list[bytes] = []
    remaining = MAX_RESPONSE_BYTES + 1
    while remaining:
        chunk = response.read(min(remaining, 64 * 1024))
        if type(chunk) is not bytes:
            _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS, request_count=1)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    body = b"".join(chunks)
    if len(body) > MAX_RESPONSE_BYTES:
        auth = RakutenLiveSmokeAuthClassification.NOT_OBSERVED
        schema = RakutenLiveSmokeSchemaClassification.NOT_OBSERVED
        rate = RakutenLiveSmokeRateClassification.NOT_OBSERVED
        if http_status == 200:
            auth = RakutenLiveSmokeAuthClassification.ACCEPTED
            schema = RakutenLiveSmokeSchemaClassification.INVALID
            rate = RakutenLiveSmokeRateClassification.SINGLE_REQUEST_NOT_THROTTLED
        elif http_status in {401, 403}:
            auth = RakutenLiveSmokeAuthClassification.REJECTED
        elif http_status == 429:
            rate = RakutenLiveSmokeRateClassification.THROTTLED
        fail_rakuten_live_smoke(
            RakutenLiveSmokeDiagnosticCode.RESPONSE_OVERSIZED,
            http_status=http_status,
            body_byte_count=len(body),
            request_count=1,
            auth=auth,
            schema=schema,
            rate=rate,
        )
    if expected_length is not None and len(body) != expected_length:
        _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS, request_count=1)
    return body


@dataclass(slots=True)
class DirectRakutenLiveSmokeTransport:
    """Use one direct stdlib TLS connection and never retry or redirect."""

    connection_factory: RakutenLiveSmokeHttpsConnectionFactory
    _attempted: bool = False

    def execute(
        self,
        policy: RakutenItemSearchLiveRequestV1,
        credentials: RakutenLiveSmokeCredentials,
    ) -> RakutenLiveSmokeHttpResponse:
        if self._attempted:
            _fail(
                RakutenLiveSmokeDiagnosticCode.REQUEST_ALREADY_ATTEMPTED,
                request_count=1,
            )
        self._attempted = True
        expected = fixed_rakuten_live_smoke_policy()
        if (
            type(policy) is not RakutenItemSearchLiveRequestV1
            or policy.canonical_json != expected.canonical_json
            or type(credentials) is not RakutenLiveSmokeCredentials
            or policy.retry_limit != 0
            or policy.pagination_followup_limit != 0
        ):
            _fail(RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS)
        require_clean_rakuten_live_smoke_environment()
        try:
            context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        except OSError, ssl.SSLError, ValueError:
            _fail(RakutenLiveSmokeDiagnosticCode.TLS_CONTEXT_INVALID)
        query = urlencode(
            (
                ("applicationId", credentials.application_id_query_value()),
                ("affiliateId", credentials.affiliate_id_query_value()),
                ("keyword", "収納"),
                ("hits", "1"),
                ("page", "1"),
                ("format", "json"),
                ("formatVersion", "2"),
                ("sort", "standard"),
                ("elements", ",".join(RAKUTEN_LIVE_SMOKE_MINIMAL_ELEMENTS)),
            ),
            doseq=False,
            safe=",",
            quote_via=quote,
        )
        target = f"{RAKUTEN_LIVE_SMOKE_PATH}?{query}"
        headers = {
            "Accept": RAKUTEN_LIVE_SMOKE_ACCEPT,
            "User-Agent": RAKUTEN_LIVE_SMOKE_USER_AGENT,
        }
        headers[RAKUTEN_LIVE_SMOKE_ACCESS_HEADER] = (
            credentials.access_key_header_value()
        )
        connection: RakutenLiveSmokeHttpsConnection | None = None
        request_started = False
        try:
            connection = self.connection_factory.open(
                host=RAKUTEN_LIVE_SMOKE_HOST,
                port=_PORT,
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
                    RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS,
                    request_count=1,
                )
            body = _read_bounded_response(response, http_status=response.status)
            content_type = response.getheader("Content-Type")
            return RakutenLiveSmokeHttpResponse(
                status=response.status,
                content_type=content_type,
                body=body,
            )
        except RakutenLiveSmokeFailure:
            raise
        except socket.gaierror:
            code = RakutenLiveSmokeDiagnosticCode.DNS_FAILED
        except ssl.SSLError:
            code = RakutenLiveSmokeDiagnosticCode.TLS_FAILED
        except TimeoutError, socket.timeout:
            code = RakutenLiveSmokeDiagnosticCode.TIMEOUT
        except http.client.HTTPException, OSError:
            code = (
                RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS
                if request_started
                else RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED
            )
        except BaseException:
            code = (
                RakutenLiveSmokeDiagnosticCode.REQUEST_AMBIGUOUS
                if request_started
                else RakutenLiveSmokeDiagnosticCode.CONNECTION_FAILED
            )
        finally:
            if connection is not None:
                try:
                    connection.close()
                except BaseException:
                    pass
        _fail(code, request_count=int(request_started))


@final
class OwnerPrivateRakutenLiveSmokeReportWriter:
    """Publish one mode-0600 sanitized report without replacement."""

    __slots__ = ("_repository_root",)

    def __init__(self, repository_root: Path) -> None:
        self._repository_root = repository_root

    def doctor_ready(self) -> None:
        """Check report metadata read-only; do not publish or create an inode."""

        smoke_fd = -1
        report_fd = -1
        try:
            smoke_fd = _open_smoke_directory(self._repository_root)
            if not getattr(os, "O_TMPFILE", 0):
                raise OSError(errno.ENOTSUP, "anonymous report inode unavailable")
            try:
                report_fd = _private_directory(smoke_fd, _REPORT_DIRECTORY)
            except FileNotFoundError:
                # The private parent is sufficient for the live preflight to create it.
                pass
            else:
                if _report_store_has_recovery(report_fd):
                    raise OSError(errno.EIO, "report preflight recovery required")
        except BaseException:
            _fail(RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID)
        finally:
            if report_fd >= 0:
                os.close(report_fd)
            if smoke_fd >= 0:
                os.close(smoke_fd)

    def preflight(self) -> None:
        """Prove anonymous private publication support before the provider GET."""

        smoke_fd = -1
        report_fd = -1
        descriptor = -1
        target = ""
        linked = False
        try:
            smoke_fd = _open_smoke_directory(self._repository_root)
            report_fd = _private_directory(smoke_fd, _REPORT_DIRECTORY, create=True)
            if _report_store_has_recovery(report_fd):
                raise OSError(errno.EIO, "report preflight recovery required")
            anonymous_flag = getattr(os, "O_TMPFILE", 0)
            if not anonymous_flag:
                raise OSError(errno.ENOTSUP, "anonymous report inode unavailable")
            descriptor = os.open(
                ".",
                os.O_WRONLY | anonymous_flag | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=report_fd,
            )
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            details = os.fstat(descriptor)
            if (
                not stat.S_ISREG(details.st_mode)
                or details.st_uid != os.getuid()
                or stat.S_IMODE(details.st_mode) != 0o600
                or details.st_nlink != 0
                or details.st_size != 0
            ):
                raise OSError(errno.EIO, "private report preflight failed")
            target = f".preflight-{os.getpid()}-{os.urandom(16).hex()}"
            os.link(
                f"/proc/self/fd/{descriptor}",
                target,
                dst_dir_fd=report_fd,
                follow_symlinks=True,
            )
            linked = True
            named = os.stat(target, dir_fd=report_fd, follow_symlinks=False)
            current = os.fstat(descriptor)
            if (
                not stat.S_ISREG(named.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or named.st_uid != os.getuid()
                or stat.S_IMODE(named.st_mode) != 0o600
                or named.st_nlink != 1
                or named.st_size != 0
                or (named.st_dev, named.st_ino) != (current.st_dev, current.st_ino)
                or current.st_nlink != 1
            ):
                raise OSError(errno.EIO, "private report preflight publication failed")
            os.fsync(report_fd)
            os.unlink(target, dir_fd=report_fd)
            linked = False
            os.fsync(report_fd)
            if os.fstat(descriptor).st_nlink != 0:
                raise OSError(errno.EIO, "private report preflight rollback failed")
        except BaseException:
            if linked and report_fd >= 0 and target:
                try:
                    os.unlink(target, dir_fd=report_fd)
                    os.fsync(report_fd)
                except OSError:
                    pass
            _fail(RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if report_fd >= 0:
                os.close(report_fd)
            if smoke_fd >= 0:
                os.close(smoke_fd)

    def write(self, report: RakutenLiveSmokeReport) -> None:
        if type(report) is not RakutenLiveSmokeReport:
            _fail(RakutenLiveSmokeDiagnosticCode.REPORT_STORE_INVALID)
        try:
            smoke_fd = _open_smoke_directory(self._repository_root)
        except BaseException:
            _fail_report_store(report)
        report_fd = -1
        target = f"{report.run_id}.json"
        descriptor = -1
        linked = False
        try:
            report_fd = _private_directory(smoke_fd, _REPORT_DIRECTORY, create=True)
            if _report_store_has_recovery(report_fd):
                _fail_report_store(report)
            anonymous_flag = getattr(os, "O_TMPFILE", 0)
            if not anonymous_flag:
                raise OSError(errno.ENOTSUP, "anonymous report inode unavailable")
            descriptor = os.open(
                ".",
                os.O_WRONLY | anonymous_flag | os.O_CLOEXEC | os.O_NOFOLLOW,
                0o600,
                dir_fd=report_fd,
            )
            payload = report.json_bytes
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError(errno.EIO, "private report write failed")
                offset += written
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
                raise OSError(errno.EIO, "private report validation failed")
            os.link(
                f"/proc/self/fd/{descriptor}",
                target,
                dst_dir_fd=report_fd,
                follow_symlinks=True,
            )
            linked = True
            named = os.stat(target, dir_fd=report_fd, follow_symlinks=False)
            current = os.fstat(descriptor)
            if (
                not stat.S_ISREG(named.st_mode)
                or not stat.S_ISREG(current.st_mode)
                or named.st_uid != os.getuid()
                or stat.S_IMODE(named.st_mode) != 0o600
                or named.st_nlink != 1
                or named.st_size != len(payload)
                or (named.st_dev, named.st_ino) != (current.st_dev, current.st_ino)
                or current.st_nlink != 1
            ):
                raise OSError(errno.EIO, "private report publication failed")
            os.fsync(report_fd)
        except OSError, RakutenLiveSmokeFailure, TypeError, ValueError:
            if linked and report_fd >= 0:
                try:
                    os.unlink(target, dir_fd=report_fd)
                    os.fsync(report_fd)
                    linked = False
                except OSError:
                    _write_report_recovery_marker(report_fd, report.run_id)
            _fail_report_store(report)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if report_fd >= 0:
                os.close(report_fd)
            os.close(smoke_fd)


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "DirectRakutenLiveSmokeTransport",
    "MAX_CREDENTIAL_BYTES",
    "OwnerPrivateRakutenLiveSmokeCredentialReader",
    "OwnerPrivateRakutenLiveSmokeReportWriter",
    "READ_TIMEOUT_SECONDS",
    "RakutenLiveSmokeHttpsConnection",
    "RakutenLiveSmokeHttpsConnectionFactory",
    "RakutenLiveSmokeHttpsResponse",
    "SystemRakutenLiveSmokeHttpsConnectionFactory",
    "require_clean_rakuten_live_smoke_environment",
]
