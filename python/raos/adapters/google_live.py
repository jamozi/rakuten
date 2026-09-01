"""Live, read-only Google provider adapters and owner-private composition inputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import date, datetime, timezone
import importlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time
from typing import Any, NoReturn, SupportsIndex, cast, final
from urllib.parse import quote, urlsplit
from uuid import UUID, uuid4

from raos.domain.analytics.google_live import (
    AnalyticsSiteBinding,
    GA4_EVENT_PARAMETER_NAMES,
    GA4_READONLY_SCOPE,
    GSC_READONLY_SCOPE,
    GSC_URL_INSPECTION_LANGUAGE_CODE,
    Ga4ImportBatch,
    Ga4LiveQuery,
    Ga4Observation,
    Ga4PropertyConfigSnapshot,
    GoogleProviderFailure,
    GoogleProviderFailureCode,
    SearchConsoleImportBatch,
    SearchConsoleLiveQuery,
    SearchConsoleObservation,
    SearchConsoleUrlInspectionBatch,
    SearchConsoleUrlInspectionObservation,
    SearchConsoleUrlInspectionQuery,
    canonical_json_bytes,
    fail_google,
    gsc_url_inspection_request_sha256,
    is_google_utc_timestamp,
    normalize_url_inspection_state,
    sha256_hex,
)
from raos.ports.google_live import (
    GoogleAuthorizedJsonTransport,
    GoogleImportClock,
    GoogleJsonResponse,
    GoogleRetrySleeper,
)


_GOOGLE_ORIGINS = frozenset(
    {
        "https://www.googleapis.com",
        "https://searchconsole.googleapis.com",
        "https://analyticsdata.googleapis.com",
        "https://analyticsadmin.googleapis.com",
    }
)
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_PAGES = 200
_RETRY_ATTEMPTS = 4
_MAX_OWNER_PRIVATE_FILE_BYTES = 1024 * 1024
_GSC_RESOURCE = "sc-domain:kurashinoshirube.com"
_SITE_ORIGIN = "https://kurashinoshirube.com"
_RECEIPT_SCHEMA = "RAOS_GOOGLE_OWNER_PRIVATE_BINDING_RECEIPT_V1"
_RECEIPT_COMPLETED_STATE = "OWNER_PRIVATE_BINDINGS_BOUND"
_RECEIPT_MATERIALIZING_STATE = "OWNER_PRIVATE_BINDINGS_MATERIALIZING"
_GSC_ADMIN_READBACK_SCHEMA = "RAOS_GSC_ADMIN_READBACK_V1"
_GA4_ADMIN_READBACK_SCHEMA = "RAOS_GA4_ADMIN_READBACK_V1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_PROJECT_ID = re.compile(r"[a-z][a-z0-9-]{4,28}[a-z0-9]\Z", re.ASCII)
_SERVICE_ACCOUNT_LOCAL_PART = re.compile(r"[a-z0-9][a-z0-9._+-]{0,126}\Z", re.ASCII)
_PROPERTY_RESOURCE = re.compile(r"properties/([1-9][0-9]{0,19})\Z", re.ASCII)
_PRIVATE_KEY_BEGIN = "-----BEGIN PRIVATE " + "KEY-----\n"
_PRIVATE_KEY_END = "-----END PRIVATE " + "KEY-----"
_RECEIPT_KEYS = frozenset(
    {
        "admin_readback_canonical_sha256s",
        "admin_readback_set_canonical_sha256",
        "authority",
        "binding_canonical_sha256s",
        "binding_set_canonical_sha256",
        "credential_readback_binding_canonical_sha256s",
        "credential_readback_binding_set_canonical_sha256",
        "schema",
        "site_id",
        "state",
        "verification",
        "version",
    }
)
_RECEIPT_VERIFICATION = {
    "credential_readback_cohash_created": True,
    "distinct_service_accounts": True,
    "exact_gsc_resource": True,
    "ga4_event_custom_dimensions_readback": True,
    "ga4_jpy_configuration_readback": True,
    "ga4_viewer_not_administrator_readback": True,
    "gsc_restricted_not_owner_readback": True,
    "numeric_ga4_property": True,
    "read_only_scopes": True,
    "readback_cryptographically_names_service_account": False,
    "same_gcp_project": True,
}
_RECEIPT_AUTHORITY = {
    "external_write": False,
    "measurement_gate_enabled": False,
    "provider_configuration_changed": False,
    "publication_authorized": False,
    "separate_admin_approval_asserted": False,
}
_GSC_READBACK_KEYS = frozenset(
    {
        "captured_at",
        "is_owner",
        "permission",
        "resource",
        "row_count",
        "schema",
        "service_account_readback",
    }
)
_GA4_READBACK_KEYS = frozenset(
    {
        "account_id",
        "captured_at",
        "currency_code",
        "custom_dimensions",
        "property_display_name",
        "property_id",
        "property_resource",
        "schema",
        "stream_origin",
        "viewer_is_administrator",
        "viewer_service_account_readback",
    }
)
_GA4_CUSTOM_DIMENSION_KEYS = frozenset(
    {
        "display_name",
        "event_scope_readback",
        "parameter_name",
        "row_count",
        "scope",
    }
)


def _is_runtime_instance(value: object, expected: type[object]) -> bool:
    """Retain fail-closed checks for values arriving from untyped composition."""

    return isinstance(value, expected)


@final
class SystemGoogleImportClock:
    __slots__ = ()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@final
class SystemGoogleRetrySleeper:
    __slots__ = ()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _directory_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
    )


def _valid_private_directory(metadata: os.stat_result) -> bool:
    return (
        stat.S_ISDIR(metadata.st_mode)
        and stat.S_IMODE(metadata.st_mode) == 0o700
        and metadata.st_uid == os.geteuid()
    )


@final
class _PinnedOwnerPrivateGoogleTree:
    """Pin root/google/provider directories and perform file I/O via openat."""

    __slots__ = ("_fds", "_identities", "_paths")

    _LOCATIONS = ("root", "google", "gsc", "ga4")
    _PARENTS = {"google": "root", "gsc": "google", "ga4": "google"}
    _NAMES = {"google": "google", "gsc": "gsc", "ga4": "ga4"}

    def __init__(self, owner_private_root: Path) -> None:
        if (
            not _is_runtime_instance(owner_private_root, Path)
            or not owner_private_root.is_absolute()
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self._fds: dict[str, int] = {}
        self._identities: dict[str, tuple[int, ...]] = {}
        self._paths = {
            "root": owner_private_root,
            "google": owner_private_root / "google",
            "gsc": owner_private_root / "google/gsc",
            "ga4": owner_private_root / "google/ga4",
        }
        try:
            self._open_root()
            for location in ("google", "gsc", "ga4"):
                self._open_child(location)
            self.verify()
        except GoogleProviderFailure:
            self.close()
            raise
        except OSError:
            self.close()
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    @staticmethod
    def _directory_flags() -> int:
        return (
            os.O_RDONLY
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
            | os.O_CLOEXEC
        )

    def _open_root(self) -> None:
        before = self._paths["root"].lstat()
        if not _valid_private_directory(before):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        descriptor = os.open(self._paths["root"], self._directory_flags())
        opened = os.fstat(descriptor)
        if not _valid_private_directory(opened) or _directory_identity(
            opened
        ) != _directory_identity(before):
            os.close(descriptor)
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self._fds["root"] = descriptor
        self._identities["root"] = _directory_identity(opened)

    def _open_child(self, location: str) -> None:
        parent = self._PARENTS[location]
        name = self._NAMES[location]
        before = os.stat(
            name,
            dir_fd=self._fds[parent],
            follow_symlinks=False,
        )
        if not _valid_private_directory(before):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        descriptor = os.open(
            name,
            self._directory_flags(),
            dir_fd=self._fds[parent],
        )
        opened = os.fstat(descriptor)
        if not _valid_private_directory(opened) or _directory_identity(
            opened
        ) != _directory_identity(before):
            os.close(descriptor)
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self._fds[location] = descriptor
        self._identities[location] = _directory_identity(opened)

    def verify(self) -> None:
        try:
            for location in self._LOCATIONS:
                descriptor_identity = _directory_identity(os.fstat(self._fds[location]))
                lexical_identity = _directory_identity(self._paths[location].lstat())
                if (
                    descriptor_identity != self._identities[location]
                    or lexical_identity != self._identities[location]
                ):
                    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            for location, parent in self._PARENTS.items():
                relative_identity = _directory_identity(
                    os.stat(
                        self._NAMES[location],
                        dir_fd=self._fds[parent],
                        follow_symlinks=False,
                    )
                )
                if relative_identity != self._identities[location]:
                    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        except GoogleProviderFailure:
            raise
        except OSError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    def directory_fd(self, location: str) -> int:
        if location not in self._LOCATIONS:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self.verify()
        return self._fds[location]

    def path(self, location: str, name: str) -> Path:
        if (
            location not in self._LOCATIONS
            or type(name) is not str
            or not name
            or name in {".", ".."}
            or "/" in name
            or "\x00" in name
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        return self._paths[location] / name

    def read_bytes(self, location: str, name: str, *, maximum: int) -> bytes:
        if not 1 <= maximum <= _MAX_OWNER_PRIVATE_FILE_BYTES:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        descriptor = -1
        try:
            directory_fd = self.directory_fd(location)
            before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(before.st_mode)
                or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_uid != os.geteuid()
                or before.st_nlink != 1
                or not 1 <= before.st_size <= maximum
            ):
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC,
                dir_fd=directory_fd,
            )
            opened = os.fstat(descriptor)
            if _file_identity(opened) != _file_identity(before):
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            chunks: list[bytes] = []
            remaining = opened.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            after_entry = os.stat(
                name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if _file_identity(after) != _file_identity(opened) or _file_identity(
                after_entry
            ) != _file_identity(opened):
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            self.verify()
            return raw
        except GoogleProviderFailure:
            raise
        except OSError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        finally:
            if descriptor >= 0:
                os.close(descriptor)

    def read_json(
        self, location: str, name: str, *, maximum: int
    ) -> tuple[dict[str, object], bytes]:
        return _decode_owner_private_json(
            self.read_bytes(location, name, maximum=maximum)
        )

    def entry_identity(self, location: str, name: str) -> tuple[int, ...] | None:
        self.path(location, name)
        directory_fd = self.directory_fd(location)
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            self.verify()
            return None
        except OSError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
            or metadata.st_uid != os.geteuid()
            or metadata.st_nlink != 1
            or not 1 <= metadata.st_size <= _MAX_OWNER_PRIVATE_FILE_BYTES
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self.verify()
        return _file_identity(metadata)

    def atomic_replace(
        self,
        location: str,
        name: str,
        content: bytes,
        *,
        expected: tuple[int, ...] | None,
    ) -> tuple[int, ...]:
        if (
            type(content) is not bytes
            or not 1 <= len(content) <= _MAX_OWNER_PRIVATE_FILE_BYTES
            or self.entry_identity(location, name) != expected
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        directory_fd = self.directory_fd(location)
        temporary_name = f".{name}.{uuid4().hex}.next"
        descriptor = -1
        temporary_exists = False
        try:
            descriptor = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | os.O_CLOEXEC,
                0o600,
                dir_fd=directory_fd,
            )
            temporary_exists = True
            os.fchmod(descriptor, 0o600)
            remaining = memoryview(content)
            while remaining:
                written = os.write(descriptor, remaining)
                if written <= 0:
                    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
                remaining = remaining[written:]
            os.fsync(descriptor)
            temporary_metadata = os.fstat(descriptor)
            temporary_entry = os.stat(
                temporary_name,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(temporary_metadata.st_mode)
                or stat.S_IMODE(temporary_metadata.st_mode) != 0o600
                or temporary_metadata.st_uid != os.geteuid()
                or temporary_metadata.st_nlink != 1
                or temporary_metadata.st_size != len(content)
                or _file_identity(temporary_entry) != _file_identity(temporary_metadata)
                or self.entry_identity(location, name) != expected
            ):
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            os.replace(
                temporary_name,
                name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            temporary_exists = False
            observed = self.entry_identity(location, name)
            opened_after_replace = _file_identity(os.fstat(descriptor))
            if observed is None or observed != opened_after_replace:
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
            os.fsync(directory_fd)
            self.verify()
            return observed
        except GoogleProviderFailure:
            raise
        except OSError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        finally:
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass
            if temporary_exists:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except OSError:
                    pass

    def close(self) -> None:
        for location in reversed(self._LOCATIONS):
            descriptor = self._fds.pop(location, -1)
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    def __enter__(self) -> _PinnedOwnerPrivateGoogleTree:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    document: dict[str, object] = {}
    for key, value in pairs:
        if key in document:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        document[key] = value
    return document


def _reject_nonfinite_json(_: str) -> None:
    fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _decode_owner_private_json(raw: bytes) -> tuple[dict[str, object], bytes]:
    try:
        value: object = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_nonfinite_json,
        )
    except GoogleProviderFailure:
        raise
    except UnicodeError, json.JSONDecodeError, RecursionError, ValueError:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    if type(value) is not dict:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    document = cast(dict[str, object], value)
    try:
        canonical = canonical_json_bytes(document)
    except GoogleProviderFailure:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return document, canonical


def _canonical_sha256(value: object) -> str:
    try:
        return sha256_hex(canonical_json_bytes(value))
    except GoogleProviderFailure:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _private_text(value: object, *, maximum: int) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return value


def _credential_identity(document: Mapping[str, object]) -> tuple[str, str]:
    project_id = _private_text(document.get("project_id"), maximum=30)
    client_email = _private_text(document.get("client_email"), maximum=254)
    private_key_value = document.get("private_key")
    if (
        document.get("type") != "service_account"
        or document.get("token_uri") != "https://oauth2.googleapis.com/token"
        or _PROJECT_ID.fullmatch(project_id) is None
        or type(private_key_value) is not str
        or not 1 <= len(private_key_value) <= 64 * 1024
        or not private_key_value.startswith(_PRIVATE_KEY_BEGIN)
        or not private_key_value.rstrip().endswith(_PRIVATE_KEY_END)
        or "\x00" in private_key_value
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    suffix = f"@{project_id}.iam.gserviceaccount.com"
    if not client_email.endswith(suffix):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    local_part = client_email.removesuffix(suffix)
    if _SERVICE_ACCOUNT_LOCAL_PART.fullmatch(local_part) is None:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return project_id, client_email


def _validate_gsc_readback(document: Mapping[str, object]) -> None:
    if (
        frozenset(document) != _GSC_READBACK_KEYS
        or document.get("schema") != _GSC_ADMIN_READBACK_SCHEMA
        or not is_google_utc_timestamp(document.get("captured_at"))
        or document.get("resource") != _GSC_RESOURCE
        or document.get("permission") != "RESTRICTED"
        or type(document.get("row_count")) is not int
        or document.get("row_count") != 1
        or document.get("service_account_readback") is not True
        or document.get("is_owner") is not False
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _validate_ga4_readback(document: Mapping[str, object], *, property_id: str) -> None:
    account_id = document.get("account_id")
    custom_dimensions = document.get("custom_dimensions")
    if (
        frozenset(document) != _GA4_READBACK_KEYS
        or document.get("schema") != _GA4_ADMIN_READBACK_SCHEMA
        or not is_google_utc_timestamp(document.get("captured_at"))
        or type(account_id) is not str
        or re.fullmatch(r"[1-9][0-9]{0,19}", account_id, re.ASCII) is None
        or document.get("property_id") != property_id
        or document.get("property_resource") != f"properties/{property_id}"
        or not _private_text(document.get("property_display_name"), maximum=100)
        or document.get("stream_origin") != _SITE_ORIGIN
        or document.get("currency_code") != "JPY"
        or document.get("viewer_service_account_readback") is not True
        or document.get("viewer_is_administrator") is not False
        or type(custom_dimensions) is not list
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    dimension_rows = cast(list[object], custom_dimensions)
    if len(dimension_rows) != len(GA4_EVENT_PARAMETER_NAMES):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    observed_parameters: list[str] = []
    for value in dimension_rows:
        if type(value) is not dict:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        row = cast(dict[str, object], value)
        parameter = row.get("parameter_name")
        if (
            frozenset(row) != _GA4_CUSTOM_DIMENSION_KEYS
            or type(parameter) is not str
            or row.get("display_name") != parameter
            or row.get("scope") != "EVENT"
            or type(row.get("row_count")) is not int
            or row.get("row_count") != 1
            or row.get("event_scope_readback") is not True
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        observed_parameters.append(parameter)
    if tuple(observed_parameters) != GA4_EVENT_PARAMETER_NAMES:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


def _exact_sha256_map(value: object) -> dict[str, str]:
    if type(value) is not dict:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    untyped_result = cast(dict[object, object], value)
    if frozenset(untyped_result) != frozenset({"GSC", "GA4"}):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    result = cast(dict[str, object], untyped_result)
    if any(
        type(item) is not str or _SHA256.fullmatch(item) is None
        for item in result.values()
    ):
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    return cast(dict[str, str], result)


_GOOGLE_AUTHORIZED_TRANSPORT_ISSUER = object()


@final
class _CredentialSnapshot:
    """Owner-private credential snapshot hidden from ordinary object walkers.

    The OS owner-private tree, provider IAM, and the RAOS process are the authority
    boundary.  This object limits accidental serialization and unsupported public
    access; it is not a sandbox against hostile code already executing inside the
    trusted Python process with access to module-private objects.
    """

    __canonical_json: bytes
    __canonical_sha256: str

    __slots__ = ("__canonical_json", "__canonical_sha256")

    def __init__(self, *, canonical_json: bytes, canonical_sha256: str) -> None:
        if (
            type(canonical_json) is not bytes
            or not canonical_json
            or type(canonical_sha256) is not str
            or _SHA256.fullmatch(canonical_sha256) is None
            or sha256_hex(canonical_json) != canonical_sha256
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        object.__setattr__(
            self,
            "_CredentialSnapshot__canonical_json",
            canonical_json,
        )
        object.__setattr__(
            self,
            "_CredentialSnapshot__canonical_sha256",
            canonical_sha256,
        )

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("credential snapshots are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("credential snapshots are immutable")

    def __repr__(self) -> str:
        return "_CredentialSnapshot(<redacted>)"

    def __reduce_ex__(self, _protocol: SupportsIndex, /) -> NoReturn:
        raise TypeError("credential snapshots are not serializable")

    def fingerprint(self) -> str:
        return self.__canonical_sha256

    def consume(self, *, issuer: object) -> dict[str, object]:
        if issuer is not _GOOGLE_AUTHORIZED_TRANSPORT_ISSUER:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        document, canonical = _decode_owner_private_json(self.__canonical_json)
        if (
            canonical != self.__canonical_json
            or sha256_hex(canonical) != self.__canonical_sha256
        ):
            fail_google(GoogleProviderFailureCode.CREDENTIAL_INVALID)
        return document


def _binding_canonical_document(
    binding: AnalyticsSiteBinding,
) -> dict[str, object]:
    return {
        "credential_file": "service-account.json",
        "provider": binding.provider,
        "resource": binding.resource,
        "schema_version": 1,
        "scopes": list(binding.scopes),
        "service_account_email_sha256": binding.service_account_email_sha256,
        "site_id": str(binding.site_id),
    }


def _binding_runtime_sha256(
    binding: AnalyticsSiteBinding,
    credential_snapshot: _CredentialSnapshot,
) -> str:
    return _canonical_sha256(
        {
            "binding": _binding_canonical_document(binding),
            "credential_path_sha256": sha256_hex(
                binding.credential_path.encode("utf-8")
            ),
            "credential_snapshot_canonical_sha256": (
                credential_snapshot.fingerprint()
            ),
        }
    )


_BINDING_GENERATION_SEAL_ISSUER = object()


@final
class _BindingGenerationSeal:
    """Binding-to-receipt consistency seal issued by the fixed loader.

    This detects stale or independently mutated runtime objects.  It is not a
    cryptographic authority boundary against hostile same-process introspection;
    authorization remains anchored in the private filesystem and provider IAM.
    """

    __binding_identity: int
    __binding_instance_nonce: object
    __binding_canonical_json: bytes
    __receipt_canonical_json: bytes
    __runtime_sha256: str
    __seal_sha256: str
    __state: str

    __slots__ = (
        "__binding_identity",
        "__binding_instance_nonce",
        "__binding_canonical_json",
        "__receipt_canonical_json",
        "__runtime_sha256",
        "__seal_sha256",
        "__state",
    )

    def __init__(
        self,
        *,
        issuer: object,
        binding: _GuardedAnalyticsSiteBinding,
        binding_instance_nonce: object,
        credential_snapshot: _CredentialSnapshot,
        binding_canonical_json: bytes,
        receipt_canonical_json: bytes,
        state: str,
    ) -> None:
        if (
            issuer is not _BINDING_GENERATION_SEAL_ISSUER
            or type(binding) is not _GuardedAnalyticsSiteBinding
            or type(binding_instance_nonce) is not object
            or type(credential_snapshot) is not _CredentialSnapshot
            or type(binding_canonical_json) is not bytes
            or not binding_canonical_json
            or type(receipt_canonical_json) is not bytes
            or not receipt_canonical_json
            or state != _RECEIPT_COMPLETED_STATE
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        binding_identity = id(binding)
        object.__setattr__(
            self,
            "_BindingGenerationSeal__binding_identity",
            binding_identity,
        )
        object.__setattr__(
            self,
            "_BindingGenerationSeal__binding_instance_nonce",
            binding_instance_nonce,
        )
        object.__setattr__(self, "_BindingGenerationSeal__state", state)
        object.__setattr__(
            self,
            "_BindingGenerationSeal__binding_canonical_json",
            binding_canonical_json,
        )
        object.__setattr__(
            self,
            "_BindingGenerationSeal__receipt_canonical_json",
            receipt_canonical_json,
        )
        runtime_sha256 = _binding_runtime_sha256(binding, credential_snapshot)
        object.__setattr__(
            self,
            "_BindingGenerationSeal__runtime_sha256",
            runtime_sha256,
        )
        object.__setattr__(
            self,
            "_BindingGenerationSeal__seal_sha256",
            self._seal_sha256(
                binding_identity=binding_identity,
                binding_instance_nonce=binding_instance_nonce,
                state=state,
                binding_canonical_json=binding_canonical_json,
                receipt_canonical_json=receipt_canonical_json,
                runtime_sha256=runtime_sha256,
            ),
        )
        self._validate(
            binding=binding,
            binding_instance_nonce=binding_instance_nonce,
            credential_snapshot=credential_snapshot,
        )

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("binding generation seals are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("binding generation seals are immutable")

    def __repr__(self) -> str:
        return "_BindingGenerationSeal(<redacted>)"

    def __reduce_ex__(self, _protocol: SupportsIndex, /) -> NoReturn:
        raise TypeError("binding generation seals are not serializable")

    @staticmethod
    def _seal_sha256(
        *,
        binding_identity: int,
        binding_instance_nonce: object,
        state: str,
        binding_canonical_json: bytes,
        receipt_canonical_json: bytes,
        runtime_sha256: str,
    ) -> str:
        return _canonical_sha256(
            {
                "binding_identity": binding_identity,
                "binding_instance_nonce_identity": id(binding_instance_nonce),
                "binding_canonical_sha256": sha256_hex(binding_canonical_json),
                "receipt_canonical_sha256": sha256_hex(receipt_canonical_json),
                "runtime_sha256": runtime_sha256,
                "state": state,
            }
        )

    def _validate(
        self,
        *,
        binding: _GuardedAnalyticsSiteBinding,
        binding_instance_nonce: object,
        credential_snapshot: _CredentialSnapshot,
    ) -> None:
        if (
            type(binding) is not _GuardedAnalyticsSiteBinding
            or id(binding) != self.__binding_identity
            or binding_instance_nonce is not self.__binding_instance_nonce
            or type(credential_snapshot) is not _CredentialSnapshot
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        binding_document, binding_canonical = _decode_owner_private_json(
            self.__binding_canonical_json
        )
        receipt, receipt_canonical = _decode_owner_private_json(
            self.__receipt_canonical_json
        )
        binding_sha256 = sha256_hex(binding_canonical)
        receipt_binding_hashes = _exact_sha256_map(
            receipt.get("binding_canonical_sha256s")
        )
        if (
            binding_canonical != self.__binding_canonical_json
            or binding_document != _binding_canonical_document(binding)
            or receipt_canonical != self.__receipt_canonical_json
            or frozenset(receipt) != _RECEIPT_KEYS
            or receipt.get("schema") != _RECEIPT_SCHEMA
            or type(receipt.get("version")) is not int
            or receipt.get("version") != 1
            or receipt.get("state") != self.__state
            or receipt.get("site_id") != str(binding.site_id)
            or receipt.get("verification") != _RECEIPT_VERIFICATION
            or receipt.get("authority") != _RECEIPT_AUTHORITY
            or receipt_binding_hashes.get(binding.provider) != binding_sha256
            or receipt.get("binding_set_canonical_sha256")
            != _canonical_sha256(receipt_binding_hashes)
            or _binding_runtime_sha256(binding, credential_snapshot)
            != self.__runtime_sha256
            or self._seal_sha256(
                binding_identity=self.__binding_identity,
                binding_instance_nonce=self.__binding_instance_nonce,
                state=self.__state,
                binding_canonical_json=self.__binding_canonical_json,
                receipt_canonical_json=self.__receipt_canonical_json,
                runtime_sha256=self.__runtime_sha256,
            )
            != self.__seal_sha256
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    def authorize(
        self,
        *,
        binding: _GuardedAnalyticsSiteBinding,
        binding_instance_nonce: object,
        credential_snapshot: _CredentialSnapshot,
    ) -> None:
        self._validate(
            binding=binding,
            binding_instance_nonce=binding_instance_nonce,
            credential_snapshot=credential_snapshot,
        )
        if self.__state != _RECEIPT_COMPLETED_STATE:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


@final
class _GuardedAnalyticsSiteBinding(AnalyticsSiteBinding):
    """Instance-bound binding that keeps capabilities out of dataclass walkers."""

    __credential_snapshot: _CredentialSnapshot
    __generation_seal: _BindingGenerationSeal
    __instance_nonce: object

    __slots__ = (
        "__credential_snapshot",
        "__generation_seal",
        "__instance_nonce",
    )

    def __init__(
        self,
        *,
        issuer: object,
        provider: str,
        site_id: UUID,
        resource: str,
        credential_path: str,
        service_account_email_sha256: str,
        scopes: tuple[str, ...],
        credential_snapshot: _CredentialSnapshot,
        binding_canonical_json: bytes,
        receipt_canonical_json: bytes,
        state: str,
    ) -> None:
        if (
            issuer is not _BINDING_GENERATION_SEAL_ISSUER
            or type(credential_snapshot) is not _CredentialSnapshot
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        AnalyticsSiteBinding.__init__(
            self,
            provider=provider,
            site_id=site_id,
            resource=resource,
            credential_path=credential_path,
            service_account_email_sha256=service_account_email_sha256,
            scopes=scopes,
        )
        instance_nonce = object()
        object.__setattr__(
            self,
            "_GuardedAnalyticsSiteBinding__credential_snapshot",
            credential_snapshot,
        )
        object.__setattr__(
            self,
            "_GuardedAnalyticsSiteBinding__instance_nonce",
            instance_nonce,
        )
        generation_seal = _BindingGenerationSeal(
            issuer=issuer,
            binding=self,
            binding_instance_nonce=instance_nonce,
            credential_snapshot=credential_snapshot,
            binding_canonical_json=binding_canonical_json,
            receipt_canonical_json=receipt_canonical_json,
            state=state,
        )
        object.__setattr__(
            self,
            "_GuardedAnalyticsSiteBinding__generation_seal",
            generation_seal,
        )

    def __setattr__(self, _name: str, _value: object) -> NoReturn:
        raise AttributeError("guarded analytics bindings are immutable")

    def __delattr__(self, _name: str) -> NoReturn:
        raise AttributeError("guarded analytics bindings are immutable")

    def __repr__(self) -> str:
        return "_GuardedAnalyticsSiteBinding(<redacted>)"

    def __reduce_ex__(self, _protocol: SupportsIndex, /) -> NoReturn:
        raise TypeError("guarded analytics bindings are not serializable")

    def authorize_transport(self, *, issuer: object) -> dict[str, object]:
        if issuer is not _GOOGLE_AUTHORIZED_TRANSPORT_ISSUER:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        self.__generation_seal.authorize(
            binding=self,
            binding_instance_nonce=self.__instance_nonce,
            credential_snapshot=self.__credential_snapshot,
        )
        return self.__credential_snapshot.consume(issuer=issuer)


def _guard_generation_binding(
    *,
    binding: AnalyticsSiteBinding,
    credential_snapshot: _CredentialSnapshot,
    binding_canonical_json: bytes,
    receipt_canonical_json: bytes,
    state: str,
) -> _GuardedAnalyticsSiteBinding:
    if state != _RECEIPT_COMPLETED_STATE:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
    try:
        return _GuardedAnalyticsSiteBinding(
            issuer=_BINDING_GENERATION_SEAL_ISSUER,
            provider=binding.provider,
            site_id=binding.site_id,
            resource=binding.resource,
            credential_path=binding.credential_path,
            service_account_email_sha256=binding.service_account_email_sha256,
            scopes=binding.scopes,
            credential_snapshot=credential_snapshot,
            binding_canonical_json=binding_canonical_json,
            receipt_canonical_json=receipt_canonical_json,
            state=state,
        )
    except GoogleProviderFailure:
        fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)


@final
class FixedOwnerPrivateAnalyticsSiteBindings:
    """Load two separate service-account bindings from a fixed 0700/0600 tree.

    Layout::

        <root>/google/gsc/{binding.v1.json,service-account.json}
        <root>/google/ga4/{binding.v1.json,service-account.json}
        <root>/google/{binding-receipt.v1.json}

    The completed receipt is the generation commit marker. Both bindings and
    both strict administrator readbacks must hash to that same generation.
    """

    __slots__ = ("_ga4", "_gsc")

    def __init__(self, owner_private_root: Path) -> None:
        self._load_generation(
            owner_private_root,
            expected_state=_RECEIPT_COMPLETED_STATE,
        )

    @classmethod
    def _for_generation_state(
        cls, owner_private_root: Path, *, expected_state: str
    ) -> FixedOwnerPrivateAnalyticsSiteBindings:
        if expected_state not in {
            _RECEIPT_COMPLETED_STATE,
            _RECEIPT_MATERIALIZING_STATE,
        }:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        instance = cls.__new__(cls)
        instance._load_generation(
            owner_private_root,
            expected_state=expected_state,
        )
        return instance

    def _load_generation(
        self, owner_private_root: Path, *, expected_state: str
    ) -> None:
        if expected_state not in {
            _RECEIPT_COMPLETED_STATE,
            _RECEIPT_MATERIALIZING_STATE,
        }:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        with _PinnedOwnerPrivateGoogleTree(owner_private_root) as tree:
            (
                gsc_binding,
                gsc_credential_snapshot,
                gsc_binding_canonical,
                gsc_project,
                gsc_email,
            ) = self._load_provider(
                tree=tree,
                provider="GSC",
                location="gsc",
                expected_scope=GSC_READONLY_SCOPE,
            )
            (
                ga4_binding,
                ga4_credential_snapshot,
                ga4_binding_canonical,
                ga4_project,
                ga4_email,
            ) = self._load_provider(
                tree=tree,
                provider="GA4",
                location="ga4",
                expected_scope=GA4_READONLY_SCOPE,
            )
            if (
                gsc_binding.site_id != ga4_binding.site_id
                or gsc_email == ga4_email
                or gsc_project != ga4_project
            ):
                fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

            gsc_readback, gsc_readback_canonical = tree.read_json(
                "gsc",
                "admin-readback.v1.json",
                maximum=_MAX_OWNER_PRIVATE_FILE_BYTES,
            )
            ga4_readback, ga4_readback_canonical = tree.read_json(
                "ga4",
                "admin-readback.v1.json",
                maximum=_MAX_OWNER_PRIVATE_FILE_BYTES,
            )
            _validate_gsc_readback(gsc_readback)
            _validate_ga4_readback(
                ga4_readback,
                property_id=ga4_binding.property_id,
            )
            receipt, receipt_canonical = tree.read_json(
                "google", "binding-receipt.v1.json", maximum=64 * 1024
            )
            self._validate_completion_receipt(
                receipt=receipt,
                expected_state=expected_state,
                site_id=gsc_binding.site_id,
                binding_hashes={
                    "GSC": sha256_hex(gsc_binding_canonical),
                    "GA4": sha256_hex(ga4_binding_canonical),
                },
                readback_hashes={
                    "GSC": sha256_hex(gsc_readback_canonical),
                    "GA4": sha256_hex(ga4_readback_canonical),
                },
                project_id=gsc_project,
                email_hashes={
                    "GSC": sha256_hex(gsc_email.encode("utf-8")),
                    "GA4": sha256_hex(ga4_email.encode("utf-8")),
                },
            )
            tree.verify()
            if expected_state == _RECEIPT_MATERIALIZING_STATE:
                self._gsc = gsc_binding
                self._ga4 = ga4_binding
                return
            self._gsc = _guard_generation_binding(
                binding=gsc_binding,
                credential_snapshot=gsc_credential_snapshot,
                binding_canonical_json=gsc_binding_canonical,
                receipt_canonical_json=receipt_canonical,
                state=expected_state,
            )
            self._ga4 = _guard_generation_binding(
                binding=ga4_binding,
                credential_snapshot=ga4_credential_snapshot,
                binding_canonical_json=ga4_binding_canonical,
                receipt_canonical_json=receipt_canonical,
                state=expected_state,
            )

    @staticmethod
    def _validate_completion_receipt(
        *,
        receipt: Mapping[str, object],
        expected_state: str,
        site_id: UUID,
        binding_hashes: Mapping[str, str],
        readback_hashes: Mapping[str, str],
        project_id: str,
        email_hashes: Mapping[str, str],
    ) -> None:
        if (
            frozenset(receipt) != _RECEIPT_KEYS
            or receipt.get("schema") != _RECEIPT_SCHEMA
            or type(receipt.get("version")) is not int
            or receipt.get("version") != 1
            or receipt.get("site_id") != str(site_id)
            or receipt.get("state") != expected_state
            or receipt.get("verification") != _RECEIPT_VERIFICATION
            or receipt.get("authority") != _RECEIPT_AUTHORITY
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        observed_binding_hashes = _exact_sha256_map(
            receipt.get("binding_canonical_sha256s")
        )
        observed_readback_hashes = _exact_sha256_map(
            receipt.get("admin_readback_canonical_sha256s")
        )
        observed_cohashes = _exact_sha256_map(
            receipt.get("credential_readback_binding_canonical_sha256s")
        )
        if (
            observed_binding_hashes != binding_hashes
            or receipt.get("binding_set_canonical_sha256")
            != _canonical_sha256(dict(binding_hashes))
            or observed_readback_hashes != readback_hashes
            or receipt.get("admin_readback_set_canonical_sha256")
            != _canonical_sha256(dict(readback_hashes))
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        project_sha256 = sha256_hex(project_id.encode("utf-8"))
        expected_cohashes = {
            provider: _canonical_sha256(
                {
                    "admin_readback_canonical_sha256": readback_hashes[provider],
                    "binding_canonical_sha256": binding_hashes[provider],
                    "gcp_project_id_sha256": project_sha256,
                    "service_account_email_sha256": email_hashes[provider],
                }
            )
            for provider in ("GSC", "GA4")
        }
        if observed_cohashes != expected_cohashes or receipt.get(
            "credential_readback_binding_set_canonical_sha256"
        ) != _canonical_sha256(expected_cohashes):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)

    @staticmethod
    def _load_provider(
        *,
        tree: _PinnedOwnerPrivateGoogleTree,
        provider: str,
        location: str,
        expected_scope: str,
    ) -> tuple[AnalyticsSiteBinding, _CredentialSnapshot, bytes, str, str]:
        credential_path = tree.path(location, "service-account.json")
        credential, credential_canonical = tree.read_json(
            location,
            "service-account.json",
            maximum=_MAX_OWNER_PRIVATE_FILE_BYTES,
        )
        project_id, client_email = _credential_identity(credential)
        document, canonical = tree.read_json(
            location, "binding.v1.json", maximum=16 * 1024
        )
        expected_keys = {
            "schema_version",
            "provider",
            "site_id",
            "resource",
            "credential_file",
            "service_account_email_sha256",
            "scopes",
        }
        scopes = document.get("scopes")
        resource = document.get("resource")
        email_sha256 = document.get("service_account_email_sha256")
        if (
            set(document) != expected_keys
            or type(document.get("schema_version")) is not int
            or document.get("schema_version") != 1
            or document.get("provider") != provider
            or document.get("credential_file") != "service-account.json"
            or type(resource) is not str
            or type(email_sha256) is not str
            or _SHA256.fullmatch(email_sha256) is None
            or email_sha256 != sha256_hex(client_email.encode("utf-8"))
            or type(scopes) is not list
            or scopes != [expected_scope]
            or (provider == "GSC" and resource != _GSC_RESOURCE)
            or (provider == "GA4" and _PROPERTY_RESOURCE.fullmatch(resource) is None)
        ):
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        try:
            site_id = UUID(cast(str, document.get("site_id")))
        except TypeError, ValueError, AttributeError:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        if site_id.int == 0:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        try:
            binding = AnalyticsSiteBinding(
                provider=provider,
                site_id=site_id,
                resource=resource,
                credential_path=str(credential_path),
                service_account_email_sha256=email_sha256,
                scopes=(expected_scope,),
            )
            credential_snapshot = _CredentialSnapshot(
                canonical_json=credential_canonical,
                canonical_sha256=sha256_hex(credential_canonical),
            )
        except GoogleProviderFailure:
            fail_google(GoogleProviderFailureCode.OWNER_PRIVATE_LAYOUT_INVALID)
        return binding, credential_snapshot, canonical, project_id, client_email

    def gsc(self) -> AnalyticsSiteBinding:
        return self._gsc

    def ga4(self) -> AnalyticsSiteBinding:
        return self._ga4


@final
class GoogleServiceAccountAuthorizedTransport:
    """Authorized HTTPS JSON transport backed by a completed private binding.

    Callers and module-private state execute inside the trusted RAOS process.  The
    service-account IAM grants and the mode-0700/0600 owner-private tree enforce
    the security boundary; the in-process guard enforces consistency and prevents
    accidental use of incomplete or ordinary binding values.
    """

    __slots__ = ("_credentials", "_lock", "_request_adapter", "_session", "_timeout")

    def __init__(
        self,
        *,
        binding: AnalyticsSiteBinding,
        timeout_seconds: float = 30.0,
    ) -> None:
        if (
            type(binding) is not _GuardedAnalyticsSiteBinding
            or type(timeout_seconds) is not float
            or not 1.0 <= timeout_seconds <= 120.0
        ):
            fail_google()
        guarded_binding = binding
        credential_info = guarded_binding.authorize_transport(
            issuer=_GOOGLE_AUTHORIZED_TRANSPORT_ISSUER,
        )
        try:
            service_account = importlib.import_module("google.oauth2.service_account")
            google_requests = importlib.import_module("google.auth.transport.requests")
            requests_module = importlib.import_module("requests")
            credentials = service_account.Credentials.from_service_account_info(
                credential_info,
                scopes=list(binding.scopes),
            )
            observed_email = cast(str, credentials.service_account_email)
            if (
                sha256_hex(observed_email.encode("utf-8"))
                != binding.service_account_email_sha256
            ):
                fail_google(GoogleProviderFailureCode.CREDENTIAL_INVALID)
            self._request_adapter = google_requests.Request()
            self._session = requests_module.Session()
            self._credentials = credentials
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.CREDENTIAL_INVALID)
        self._timeout = timeout_seconds
        self._lock = threading.RLock()

    def _access_token(self) -> str:
        try:
            with self._lock:
                if not bool(self._credentials.valid):
                    self._credentials.refresh(self._request_adapter)
                access_value = self._credentials.token
        except Exception:
            fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED, retryable=True)
        if type(access_value) is not str or not access_value:
            fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED)
        return access_value

    def request(
        self,
        *,
        method: str,
        url: str,
        body: Mapping[str, object] | None,
    ) -> GoogleJsonResponse:
        parsed = urlsplit(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if (
            method not in {"GET", "POST"}
            or origin not in _GOOGLE_ORIGINS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or (method == "GET" and body is not None)
            or (method == "POST" and type(body) is not dict)
        ):
            fail_google()
        json_body: dict[str, object] | None = (
            None if body is None else cast(dict[str, object], body).copy()
        )
        try:
            response: Any = self._session.request(
                method,
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {self._access_token()}",
                    "Content-Type": "application/json",
                    "User-Agent": "raos-google-live/1",
                },
                json=json_body,
                timeout=self._timeout,
                allow_redirects=False,
            )
            content = cast(bytes, response.content)
        except GoogleProviderFailure:
            raise
        except Exception:
            fail_google(GoogleProviderFailureCode.PROVIDER_UNAVAILABLE, retryable=True)
        if len(content) > _MAX_RESPONSE_BYTES:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        try:
            document: object = json.loads(content.decode("utf-8")) if content else {}
        except UnicodeDecodeError, json.JSONDecodeError:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        safe_headers = tuple(
            (name.lower(), cast(str, response.headers.get(name)))
            for name in ("Retry-After", "Content-Type")
            if response.headers.get(name) is not None
        )
        return GoogleJsonResponse(
            status=cast(int, response.status_code),
            headers=safe_headers,
            document=document,
        )


def _retry_delay(response: GoogleJsonResponse | None, attempt: int) -> float:
    if response is not None:
        for name, value in response.headers:
            if name == "retry-after":
                try:
                    return float(min(max(int(value), 0), 60))
                except ValueError:
                    break
    return float(2**attempt)


def _request_with_retry(
    *,
    transport: GoogleAuthorizedJsonTransport,
    sleeper: GoogleRetrySleeper,
    method: str,
    url: str,
    body: Mapping[str, object] | None,
) -> GoogleJsonResponse:
    last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
    for attempt in range(_RETRY_ATTEMPTS):
        response: GoogleJsonResponse | None = None
        try:
            response = transport.request(method=method, url=url, body=body)
        except GoogleProviderFailure as error:
            if not error.retryable:
                raise
            last_code = error.code
        except Exception:
            last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
        else:
            if 200 <= response.status < 300:
                return response
            if response.status == 401:
                fail_google(GoogleProviderFailureCode.AUTHENTICATION_FAILED)
            if response.status == 403:
                fail_google(GoogleProviderFailureCode.AUTHORIZATION_FAILED)
            if response.status == 404:
                fail_google(GoogleProviderFailureCode.RESOURCE_NOT_FOUND)
            if response.status == 429:
                last_code = GoogleProviderFailureCode.RATE_LIMITED
            elif 500 <= response.status <= 599:
                last_code = GoogleProviderFailureCode.PROVIDER_UNAVAILABLE
            else:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if attempt + 1 < _RETRY_ATTEMPTS:
            sleeper.sleep(_retry_delay(response, attempt))
    fail_google(last_code, retryable=True)


def _dict(value: object) -> dict[str, object]:
    if type(value) is not dict:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(dict[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(list[object], value)


def _number(value: object) -> float:
    if type(value) not in {int, float}:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    observed = float(cast(int | float, value))
    if not observed == observed or observed in {float("inf"), float("-inf")}:
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return observed


def _optional_utc_timestamp(value: object) -> str | None:
    if value is None:
        return None
    if not is_google_utc_timestamp(value):
        fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
    return cast(str, value)


@final
class LiveSearchConsoleProvider:
    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def query(self, query: SearchConsoleLiveQuery) -> SearchConsoleImportBatch:
        if type(query) is not SearchConsoleLiveQuery:
            fail_google()
        endpoint = (
            "https://www.googleapis.com/webmasters/v3/sites/"
            f"{quote(query.site_url, safe='')}/searchAnalytics/query"
        )
        rows: list[SearchConsoleObservation] = []
        request_hashes: list[str] = []
        seen_grains: set[str] = set()
        start_row = 0
        for _ in range(_MAX_PAGES):
            body: dict[str, object] = {
                "aggregationType": "auto",
                "dataState": "final",
                "dimensions": list(query.dimensions),
                "endDate": query.date_to.isoformat(),
                "rowLimit": query.row_limit,
                "startDate": query.date_from.isoformat(),
                "startRow": start_row,
                "type": "web",
            }
            page_hash = sha256_hex(
                canonical_json_bytes({"site_url": query.site_url, "body": body})
            )
            request_hashes.append(page_hash)
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            page_rows = _list(document.get("rows", []))
            for candidate in page_rows:
                item = _dict(candidate)
                keys = _list(item.get("keys"))
                if len(keys) != len(query.dimensions) or not all(
                    type(value) is str for value in keys
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                key_values = cast(list[str], keys)
                try:
                    metric_date = date.fromisoformat(key_values[0])
                except ValueError:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                clicks_value = item.get("clicks")
                impressions_value = item.get("impressions")
                if type(clicks_value) is not int or type(impressions_value) is not int:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                grain_hash = sha256_hex(
                    canonical_json_bytes(
                        {
                            "country": key_values[3].lower(),
                            "date": metric_date.isoformat(),
                            "device": key_values[4].upper(),
                            "page": key_values[2],
                            "query": key_values[1],
                        }
                    )
                )
                if grain_hash in seen_grains:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                seen_grains.add(grain_hash)
                rows.append(
                    SearchConsoleObservation(
                        metric_date=metric_date,
                        query_text=key_values[1],
                        page_url=key_values[2],
                        country_code=key_values[3].lower(),
                        device=key_values[4].upper(),
                        clicks=clicks_value,
                        impressions=impressions_value,
                        ctr=_number(item.get("ctr")),
                        average_position=_number(item.get("position")),
                        dimension_key_sha256=grain_hash,
                        source_request_sha256=page_hash,
                    )
                )
            if len(rows) > 2_000_000:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            if len(page_rows) < query.row_limit:
                break
            start_row += len(page_rows)
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        return SearchConsoleImportBatch(
            site_id=query.site_id,
            site_url=query.site_url,
            date_from=query.date_from,
            date_to=query.date_to,
            request_sha256=query.request_sha256,
            page_request_sha256s=tuple(request_hashes),
            rows=tuple(rows),
            retrieved_at=self._clock.now(),
            provider_row_count=len(rows),
        )


@final
class LiveSearchConsoleUrlInspectionProvider:
    """Inspect the closed URL set sequentially through the read-only GSC seam."""

    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def inspect(
        self, query: SearchConsoleUrlInspectionQuery
    ) -> SearchConsoleUrlInspectionBatch:
        if type(query) is not SearchConsoleUrlInspectionQuery:
            fail_google()
        endpoint = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
        results: list[SearchConsoleUrlInspectionObservation] = []
        for inspection_url in query.inspection_urls:
            body: dict[str, object] = {
                "inspectionUrl": inspection_url,
                "languageCode": GSC_URL_INSPECTION_LANGUAGE_CODE,
                "siteUrl": query.site_url,
            }
            request_sha256 = gsc_url_inspection_request_sha256(
                site_url=query.site_url,
                inspection_url=inspection_url,
            )
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            inspection_result = _dict(document.get("inspectionResult"))
            index_status = _dict(inspection_result.get("indexStatusResult"))
            verdict = index_status.get("verdict")
            indexing_state = index_status.get("indexingState")
            if type(verdict) is not str or type(indexing_state) is not str:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            last_crawl_at = _optional_utc_timestamp(index_status.get("lastCrawlTime"))
            normalized_response = {
                "indexingState": indexing_state,
                "lastCrawlTime": last_crawl_at,
                "verdict": verdict,
            }
            results.append(
                SearchConsoleUrlInspectionObservation(
                    inspected_url=inspection_url,
                    state=normalize_url_inspection_state(
                        verdict=verdict, indexing_state=indexing_state
                    ),
                    verdict=verdict,
                    indexing_state=indexing_state,
                    last_crawl_at=last_crawl_at,
                    source_request_sha256=request_sha256,
                    provider_response_sha256=sha256_hex(
                        canonical_json_bytes(normalized_response)
                    ),
                )
            )
        return SearchConsoleUrlInspectionBatch(
            site_id=query.site_id,
            site_url=query.site_url,
            request_sha256=query.request_sha256,
            results=tuple(results),
            retrieved_at=self._clock.now(),
        )


@final
class LiveGa4AdminProvider:
    __slots__ = ("_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if not _is_runtime_instance(
            transport, GoogleAuthorizedJsonTransport
        ) or not _is_runtime_instance(sleeper, GoogleRetrySleeper):
            fail_google()
        self._transport = transport
        self._sleeper = sleeper

    def get_property_configuration(
        self,
        *,
        property_id: str,
        retrieved_at: datetime,
    ) -> Ga4PropertyConfigSnapshot:
        resource = f"properties/{property_id}"
        property_response = _request_with_retry(
            transport=self._transport,
            sleeper=self._sleeper,
            method="GET",
            url=f"https://analyticsadmin.googleapis.com/v1alpha/{resource}",
            body=None,
        )
        identity_response = _request_with_retry(
            transport=self._transport,
            sleeper=self._sleeper,
            method="GET",
            url=(
                "https://analyticsadmin.googleapis.com/v1alpha/"
                f"{resource}/reportingIdentitySettings"
            ),
            body=None,
        )
        property_document = _dict(property_response.document)
        identity_document = _dict(identity_response.document)
        for name in ("name", "displayName", "timeZone", "currencyCode"):
            if type(property_document.get(name)) is not str:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if (
            property_document["name"] != resource
            or identity_document.get("name") != f"{resource}/reportingIdentitySettings"
            or type(identity_document.get("reportingIdentity")) is not str
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        custom_dimension_hashes: list[str] = []
        custom_dimension_scopes: dict[str, str] = {}
        page_token: str | None = None
        for _ in range(_MAX_PAGES):
            custom_dimensions_url = (
                "https://analyticsadmin.googleapis.com/v1alpha/"
                f"{resource}/customDimensions?pageSize=200"
            )
            if page_token is not None:
                custom_dimensions_url += f"&pageToken={quote(page_token, safe='')}"
            custom_dimensions_response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="GET",
                url=custom_dimensions_url,
                body=None,
            )
            custom_dimensions_document = _dict(custom_dimensions_response.document)
            custom_dimension_hashes.append(
                sha256_hex(canonical_json_bytes(custom_dimensions_document))
            )
            for raw_dimension in _list(
                custom_dimensions_document.get("customDimensions", [])
            ):
                dimension = _dict(raw_dimension)
                dimension_resource = dimension.get("name")
                parameter_name = dimension.get("parameterName")
                scope = dimension.get("scope")
                if (
                    type(dimension_resource) is not str
                    or not dimension_resource.startswith(
                        f"{resource}/customDimensions/"
                    )
                    or type(parameter_name) is not str
                    or not parameter_name
                    or type(scope) is not str
                    or parameter_name in custom_dimension_scopes
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                custom_dimension_scopes[parameter_name] = scope
            next_page_token = custom_dimensions_document.get("nextPageToken")
            if next_page_token is None:
                break
            if type(next_page_token) is not str or not next_page_token:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            page_token = next_page_token
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if any(
            custom_dimension_scopes.get(parameter_name) != "EVENT"
            for parameter_name in GA4_EVENT_PARAMETER_NAMES
        ):
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        property_hash = sha256_hex(canonical_json_bytes(property_document))
        identity_hash = sha256_hex(
            canonical_json_bytes(
                {
                    "custom_dimension_page_sha256s": custom_dimension_hashes,
                    "reporting_identity": identity_document,
                }
            )
        )
        snapshot_document = {
            "currency_code": property_document["currencyCode"],
            "display_name": property_document["displayName"],
            "property_resource": resource,
            "required_event_custom_dimensions": list(GA4_EVENT_PARAMETER_NAMES),
            "reporting_identity": identity_document["reportingIdentity"],
            "time_zone": property_document["timeZone"],
        }
        return Ga4PropertyConfigSnapshot(
            property_id=property_id,
            property_resource=resource,
            display_name=cast(str, property_document["displayName"]),
            time_zone=cast(str, property_document["timeZone"]),
            currency_code=cast(str, property_document["currencyCode"]),
            reporting_identity=cast(str, identity_document["reportingIdentity"]),
            retrieved_at=retrieved_at,
            property_response_sha256=property_hash,
            reporting_identity_response_sha256=identity_hash,
            snapshot_sha256=sha256_hex(canonical_json_bytes(snapshot_document)),
        )


@final
class LiveGa4DataProvider:
    __slots__ = ("_clock", "_sleeper", "_transport")

    def __init__(
        self,
        *,
        transport: GoogleAuthorizedJsonTransport,
        clock: GoogleImportClock,
        sleeper: GoogleRetrySleeper,
    ) -> None:
        if (
            not _is_runtime_instance(transport, GoogleAuthorizedJsonTransport)
            or not _is_runtime_instance(clock, GoogleImportClock)
            or not _is_runtime_instance(sleeper, GoogleRetrySleeper)
        ):
            fail_google()
        self._transport = transport
        self._clock = clock
        self._sleeper = sleeper

    def run_report(
        self,
        query: Ga4LiveQuery,
        *,
        configuration: Ga4PropertyConfigSnapshot,
    ) -> Ga4ImportBatch:
        if (
            type(query) is not Ga4LiveQuery
            or type(configuration) is not Ga4PropertyConfigSnapshot
            or configuration.property_id != query.property_id
        ):
            fail_google()
        endpoint = (
            "https://analyticsdata.googleapis.com/v1beta/"
            f"properties/{query.property_id}:runReport"
        )
        rows: list[Ga4Observation] = []
        request_hashes: list[str] = []
        seen_grains: set[str] = set()
        offset = 0
        expected_row_count: int | None = None
        thresholding = False
        data_loss = False
        for _ in range(_MAX_PAGES):
            body: dict[str, object] = {
                "dateRanges": [
                    {
                        "endDate": query.date_to.isoformat(),
                        "startDate": query.date_from.isoformat(),
                    }
                ],
                "dimensions": [{"name": item} for item in query.dimensions],
                "keepEmptyRows": False,
                "limit": str(query.page_limit),
                "metrics": [{"name": item} for item in query.metrics],
                "offset": str(offset),
                "returnPropertyQuota": True,
            }
            page_hash = sha256_hex(
                canonical_json_bytes(
                    {"property": f"properties/{query.property_id}", "body": body}
                )
            )
            request_hashes.append(page_hash)
            response = _request_with_retry(
                transport=self._transport,
                sleeper=self._sleeper,
                method="POST",
                url=endpoint,
                body=body,
            )
            document = _dict(response.document)
            dimension_headers = tuple(
                cast(str, _dict(item).get("name"))
                for item in _list(document.get("dimensionHeaders"))
            )
            metric_headers = tuple(
                cast(str, _dict(item).get("name"))
                for item in _list(document.get("metricHeaders"))
            )
            if dimension_headers != query.dimensions or metric_headers != query.metrics:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            declared_count = document.get("rowCount")
            if type(declared_count) is str and declared_count.isdigit():
                declared_count = int(declared_count)
            if type(declared_count) is not int or declared_count < 0:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            if expected_row_count is None:
                expected_row_count = declared_count
            elif expected_row_count != declared_count:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
            metadata = _dict(document.get("metadata", {}))
            thresholding = (
                thresholding or metadata.get("subjectToThresholding", False) is True
            )
            data_loss = data_loss or metadata.get("dataLossFromOtherRow", False) is True
            page_rows = _list(document.get("rows", []))
            for candidate in page_rows:
                item = _dict(candidate)
                dimension_values = tuple(
                    cast(str, _dict(value).get("value"))
                    for value in _list(item.get("dimensionValues"))
                )
                metric_values = tuple(
                    cast(str, _dict(value).get("value"))
                    for value in _list(item.get("metricValues"))
                )
                if (
                    len(dimension_values) != len(query.dimensions)
                    or len(metric_values) != len(query.metrics)
                    or not all(type(value) is str for value in dimension_values)
                    or not all(type(value) is str for value in metric_values)
                ):
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                try:
                    metric_date = datetime.strptime(
                        dimension_values[0], "%Y%m%d"
                    ).date()
                except ValueError:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                dimensions = tuple(zip(query.dimensions, dimension_values, strict=True))
                metrics = tuple(zip(query.metrics, metric_values, strict=True))
                grain_hash = sha256_hex(
                    canonical_json_bytes(
                        {
                            "date": metric_date.isoformat(),
                            "dimensions": dict(dimensions),
                        }
                    )
                )
                if grain_hash in seen_grains:
                    fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
                seen_grains.add(grain_hash)
                rows.append(
                    Ga4Observation(
                        metric_date=metric_date,
                        dimensions=dimensions,
                        metrics=metrics,
                        grain_key_sha256=grain_hash,
                        source_request_sha256=page_hash,
                        is_thresholded=thresholding,
                    )
                )
            offset += len(page_rows)
            if offset >= expected_row_count:
                break
            if not page_rows:
                fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        else:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if len(rows) != expected_row_count:
            fail_google(GoogleProviderFailureCode.PROVIDER_RESPONSE_INVALID)
        if thresholding:
            rows = [replace(row, is_thresholded=True) for row in rows]
        return Ga4ImportBatch(
            site_id=query.site_id,
            property_id=query.property_id,
            date_from=query.date_from,
            date_to=query.date_to,
            dimensions=query.dimensions,
            metrics=query.metrics,
            request_sha256=query.request_sha256,
            page_request_sha256s=tuple(request_hashes),
            rows=tuple(rows),
            configuration=configuration,
            retrieved_at=self._clock.now(),
            provider_row_count=len(rows),
            subject_to_thresholding=thresholding,
            data_loss_from_other_row=data_loss,
        )


__all__ = [
    "FixedOwnerPrivateAnalyticsSiteBindings",
    "GoogleServiceAccountAuthorizedTransport",
    "LiveGa4AdminProvider",
    "LiveGa4DataProvider",
    "LiveSearchConsoleProvider",
    "LiveSearchConsoleUrlInspectionProvider",
    "SystemGoogleImportClock",
    "SystemGoogleRetrySleeper",
]
