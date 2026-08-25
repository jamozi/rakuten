"""Read-only owner-private credentials for the WordPress operator bridge."""

from __future__ import annotations

import base64
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
import errno
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Any, Final, NoReturn, SupportsIndex, cast, final

from raos.domain.operations.self_hosted_wordpress_operator import (
    OperatorProposal,
    WORDPRESS_OPERATOR_CONTRACT_VERSION,
    WORDPRESS_OPERATOR_EXPECTED_ROLE,
    WORDPRESS_OPERATOR_ORIGIN,
    WordPressOperatorOperation,
    WordPressOperatorFailure,
    WordPressOperatorFailureCode,
    canonical_json_bytes,
    fail_wordpress_operator,
    require_sha256,
)


CREDENTIAL_RELATIVE_PATH: Final = Path(
    ".secrets/wordpress-operator-local/credentials.v1.json"
)
MAX_CREDENTIAL_BYTES: Final = 16 * 1024
PROPOSAL_INTENT_RELATIVE_DIRECTORY: Final = Path(
    ".secrets/wordpress-operator-local/proposal-intents"
)
MAX_PROPOSAL_INTENT_BYTES: Final = 1024

_DIRECTORY_COMPONENTS: Final = (".secrets", "wordpress-operator-local")
_CREDENTIAL_FILE: Final = "credentials.v1.json"
_PROPOSAL_INTENT_DIRECTORY: Final = "proposal-intents"
_PROPOSAL_INTENT_SCHEMA: Final = "RAOS_WORDPRESS_OPERATOR_PROPOSAL_INTENT_V1"
_PROPOSAL_INTENT_CANONICAL_PREFIX: Final = b'{"canonical_request_sha256":"'
_PROPOSAL_INTENT_FILES: Final = {
    WordPressOperatorOperation.APPLY_YOAST_PROFILE: "apply-yoast-profile.intent.v1.json",
    WordPressOperatorOperation.UPDATE_CHILD_THEME: "update-child-theme.intent.v1.json",
}
_PROPOSAL_INTENT_STAGING_FILES: Final = {
    operation: f".{name}.pending" for operation, name in _PROPOSAL_INTENT_FILES.items()
}
_PROPOSAL_LOCK_FILES: Final = {
    WordPressOperatorOperation.APPLY_YOAST_PROFILE: "apply-yoast-profile.lock",
    WordPressOperatorOperation.UPDATE_CHILD_THEME: "update-child-theme.lock",
}
_CREDENTIAL_KEYS: Final = frozenset(
    {
        "application_password",
        "expected_role",
        "schema_version",
        "site_origin",
        "username",
    }
)
_PROPOSAL_INTENT_KEYS: Final = frozenset(
    {
        "canonical_request_sha256",
        "operation",
        "proposal_id",
        "request_token",
        "schema",
    }
)
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
_FILE_FLAGS: Final = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_NEW_FILE_FLAGS: Final = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
)
_LOCK_FILE_FLAGS: Final = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK


def _fail(
    code: WordPressOperatorFailureCode = (
        WordPressOperatorFailureCode.CREDENTIAL_STORE_INVALID
    ),
) -> NoReturn:
    fail_wordpress_operator(code)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_mode == right.st_mode
        and left.st_uid == right.st_uid
    )


def _effective_owner_uid() -> int:
    value = os.geteuid()
    if type(value) is not int or value < 0:
        _fail()
    return value


def _open_absolute_directory(path: Path) -> int:
    if not path.is_absolute() or any(
        component in {"", ".", ".."} for component in path.parts[1:]
    ):
        _fail()
    try:
        current = os.open("/", _DIRECTORY_FLAGS)
    except OSError:
        _fail()
    try:
        for component in path.parts[1:]:
            following = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = following
        opened = os.fstat(current)
        named = os.stat(path, follow_symlinks=False)
        if not _same_identity(opened, named) or not stat.S_ISDIR(opened.st_mode):
            _fail()
        return current
    except WordPressOperatorFailure:
        os.close(current)
        raise
    except BaseException:
        os.close(current)
        _fail()


def _open_private_child(parent_fd: int, name: str, owner_uid: int) -> int:
    child = -1
    try:
        child = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
        opened = os.fstat(child)
        named = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except BaseException:
        if child >= 0:
            try:
                os.close(child)
            except OSError:
                pass
        _fail()
    if (
        not _same_identity(opened, named)
        or not stat.S_ISDIR(opened.st_mode)
        or opened.st_uid != owner_uid
        or stat.S_IMODE(opened.st_mode) != 0o700
        or opened.st_nlink < 2
    ):
        os.close(child)
        _fail()
    return child


def _open_credential_directory(repository_root: Path, owner_uid: int) -> int:
    current = _open_absolute_directory(repository_root)
    try:
        for component in _DIRECTORY_COMPONENTS:
            following = _open_private_child(current, component, owner_uid)
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _open_proposal_intent_directory(repository_root: Path, owner_uid: int) -> int:
    parent = _open_credential_directory(repository_root, owner_uid)
    try:
        try:
            os.mkdir(_PROPOSAL_INTENT_DIRECTORY, 0o700, dir_fd=parent)
            os.fsync(parent)
        except FileExistsError:
            pass
        child = _open_private_child(parent, _PROPOSAL_INTENT_DIRECTORY, owner_uid)
        return child
    except WordPressOperatorFailure:
        raise
    except BaseException:
        _fail()
    finally:
        os.close(parent)


def _read_bounded_credential(directory_fd: int, owner_uid: int) -> bytes:
    try:
        descriptor = os.open(_CREDENTIAL_FILE, _FILE_FLAGS, dir_fd=directory_fd)
    except OSError:
        _fail()
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != owner_uid
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != 1
            or not 1 <= before.st_size <= MAX_CREDENTIAL_BYTES
        ):
            _fail()
        chunks: list[bytes] = []
        remaining = MAX_CREDENTIAL_BYTES + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = os.stat(_CREDENTIAL_FILE, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(payload) != before.st_size
            or len(payload) > MAX_CREDENTIAL_BYTES
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail()
        return payload
    except WordPressOperatorFailure:
        raise
    except BaseException:
        _fail()
    finally:
        os.close(descriptor)


def _read_bounded_private_file(
    directory_fd: int,
    name: str,
    *,
    maximum: int,
    owner_uid: int,
    expected_link_count: int = 1,
    allow_empty: bool = False,
) -> bytes | None:
    descriptor = -1
    try:
        try:
            descriptor = os.open(name, _FILE_FLAGS, dir_fd=directory_fd)
        except OSError as error:
            if error.errno == errno.ENOENT:
                return None
            _fail()
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_uid != owner_uid
            or stat.S_IMODE(before.st_mode) != 0o600
            or before.st_nlink != expected_link_count
            or not (0 if allow_empty else 1) <= before.st_size <= maximum
        ):
            _fail()
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            len(payload) != before.st_size
            or len(payload) > maximum
            or not _same_identity(before, after)
            or not _same_identity(after, named)
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_ctime_ns != after.st_ctime_ns
        ):
            _fail()
        return payload
    except WordPressOperatorFailure:
        raise
    except BaseException:
        _fail()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _named_metadata(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as error:
        if error.errno == errno.ENOENT:
            return None
        _fail()


def _recover_proposal_intent_staging(
    directory_fd: int, operation: WordPressOperatorOperation, owner_uid: int
) -> None:
    final_name = _PROPOSAL_INTENT_FILES[operation]
    staging_name = _PROPOSAL_INTENT_STAGING_FILES[operation]
    final = _named_metadata(directory_fd, final_name)
    staging = _named_metadata(directory_fd, staging_name)
    if staging is None:
        return
    if (
        not stat.S_ISREG(staging.st_mode)
        or staging.st_uid != owner_uid
        or stat.S_IMODE(staging.st_mode) != 0o600
        or staging.st_size > MAX_PROPOSAL_INTENT_BYTES
    ):
        _fail()
    if final is None:
        if staging.st_nlink != 1:
            _fail()
        payload = _read_bounded_private_file(
            directory_fd,
            staging_name,
            maximum=MAX_PROPOSAL_INTENT_BYTES,
            owner_uid=owner_uid,
            allow_empty=True,
        )
        if payload is None:
            _fail()
        try:
            _decode_proposal_intent(payload, operation)
        except WordPressOperatorFailure:
            prefix_length = min(len(payload), len(_PROPOSAL_INTENT_CANONICAL_PREFIX))
            if payload[:prefix_length] != _PROPOSAL_INTENT_CANONICAL_PREFIX[
                :prefix_length
            ] or payload.endswith(b"}"):
                raise
            # No transport can start until record() returns.  A private, unlinked
            # canonical prefix that cannot yet decode is therefore only an
            # interrupted pre-publication write, never a published intent.
            rebound = _named_metadata(directory_fd, staging_name)
            if (
                rebound is None
                or not _same_identity(staging, rebound)
                or rebound.st_nlink != 1
            ):
                _fail()
            try:
                os.unlink(staging_name, dir_fd=directory_fd)
                os.fsync(directory_fd)
            except BaseException:
                _fail()
            if _named_metadata(directory_fd, staging_name) is not None:
                _fail()
            return
        try:
            os.link(
                staging_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
        except BaseException:
            _fail()
        final = _named_metadata(directory_fd, final_name)
        staging = _named_metadata(directory_fd, staging_name)
    elif staging.st_size < 1:
        _fail()
    if (
        final is None
        or staging is None
        or not _same_identity(final, staging)
        or final.st_nlink != 2
    ):
        _fail()
    payload = _read_bounded_private_file(
        directory_fd,
        staging_name,
        maximum=MAX_PROPOSAL_INTENT_BYTES,
        owner_uid=owner_uid,
        expected_link_count=2,
    )
    if payload is None:
        _fail()
    _decode_proposal_intent(payload, operation)
    try:
        os.unlink(staging_name, dir_fd=directory_fd)
        os.fsync(directory_fd)
    except BaseException:
        _fail()
    rebound = _named_metadata(directory_fd, final_name)
    if rebound is None or rebound.st_nlink != 1:
        _fail()


class _DuplicateKey(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _ascii_text(
    value: object,
    *,
    maximum: int,
    forbid_colon: bool,
    allow_spaces: bool,
) -> str:
    if (
        type(value) is not str
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or (forbid_colon and ":" in value)
        or any(
            ord(character) < (0x20 if allow_spaces else 0x21) or ord(character) > 0x7E
            for character in value
        )
    ):
        _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
    try:
        value.encode("ascii", errors="strict")
    except UnicodeError:
        _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
    return value


@dataclass(frozen=True, slots=True, repr=False)
class WordPressOperatorCredentialMetadata:
    site_origin: str
    username: str
    expected_role: str

    def __post_init__(self) -> None:
        if (
            self.site_origin != WORDPRESS_OPERATOR_ORIGIN
            or self.expected_role != WORDPRESS_OPERATOR_EXPECTED_ROLE
        ):
            _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
        _ascii_text(self.username, maximum=128, forbid_colon=True, allow_spaces=False)

    def __repr__(self) -> str:
        return "WordPressOperatorCredentialMetadata(<redacted>)"

    def __str__(self) -> str:
        return "<redacted-wordpress-operator-credential-metadata>"


@dataclass(frozen=True, slots=True, repr=False)
class WordPressOperatorCredentials:
    metadata: WordPressOperatorCredentialMetadata
    _application_password: str

    def __post_init__(self) -> None:
        if type(self.metadata) is not WordPressOperatorCredentialMetadata:
            _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
        _ascii_text(
            self._application_password,
            maximum=4096,
            forbid_colon=False,
            allow_spaces=True,
        )

    def __repr__(self) -> str:
        return "WordPressOperatorCredentials(<redacted>)"

    def __str__(self) -> str:
        return "<redacted-wordpress-operator-credentials>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("credential serialization is disabled")

    def authorization_header(self) -> str:
        raw = f"{self.metadata.username}:{self._application_password}".encode(
            "ascii", errors="strict"
        )
        return "Basic " + base64.b64encode(raw).decode("ascii")


def _decode_credentials(payload: bytes) -> WordPressOperatorCredentials:
    try:
        value = json.loads(
            payload.decode("utf-8", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail()
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[str, object], value)
    if (
        frozenset(mapping) != _CREDENTIAL_KEYS
        or type(mapping["schema_version"]) is not int
        or mapping["schema_version"] != WORDPRESS_OPERATOR_CONTRACT_VERSION
    ):
        _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
    site_origin = _ascii_text(
        mapping["site_origin"], maximum=128, forbid_colon=False, allow_spaces=False
    )
    expected_role = _ascii_text(
        mapping["expected_role"], maximum=128, forbid_colon=True, allow_spaces=False
    )
    if (
        site_origin != WORDPRESS_OPERATOR_ORIGIN
        or expected_role != WORDPRESS_OPERATOR_EXPECTED_ROLE
    ):
        _fail(WordPressOperatorFailureCode.CREDENTIAL_METADATA_INVALID)
    metadata = WordPressOperatorCredentialMetadata(
        site_origin=site_origin,
        username=_ascii_text(
            mapping["username"],
            maximum=128,
            forbid_colon=True,
            allow_spaces=False,
        ),
        expected_role=expected_role,
    )
    return WordPressOperatorCredentials(
        metadata=metadata,
        _application_password=_ascii_text(
            mapping["application_password"],
            maximum=4096,
            forbid_colon=False,
            allow_spaces=True,
        ),
    )


@dataclass(frozen=True, slots=True, repr=False)
class WordPressOperatorProposalIntent:
    operation: WordPressOperatorOperation
    proposal_id: str
    request_token: str
    canonical_request_sha256: str

    def __post_init__(self) -> None:
        if type(self.operation) is not WordPressOperatorOperation:
            _fail()
        require_sha256(self.proposal_id)
        require_sha256(self.request_token)
        require_sha256(self.canonical_request_sha256)
        if self.canonical_request_sha256 != self.proposal_id:
            _fail()

    def __repr__(self) -> str:
        return "WordPressOperatorProposalIntent(<redacted>)"

    def __str__(self) -> str:
        return "<redacted-wordpress-operator-proposal-intent>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("proposal intent serialization is disabled")

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "operation": self.operation.value,
                "proposal_id": self.proposal_id,
                "request_token": self.request_token,
                "canonical_request_sha256": self.canonical_request_sha256,
                "schema": _PROPOSAL_INTENT_SCHEMA,
            }
        )


def _decode_proposal_intent(
    payload: bytes, expected_operation: WordPressOperatorOperation
) -> WordPressOperatorProposalIntent:
    try:
        value = json.loads(
            payload.decode("ascii", errors="strict"),
            object_pairs_hook=_strict_pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except UnicodeError, ValueError, TypeError, RecursionError:
        _fail()
    if type(value) is not dict:
        _fail()
    mapping = cast(dict[str, object], value)
    if (
        frozenset(mapping) != _PROPOSAL_INTENT_KEYS
        or mapping["schema"] != _PROPOSAL_INTENT_SCHEMA
        or mapping["operation"] != expected_operation.value
    ):
        _fail()
    return WordPressOperatorProposalIntent(
        operation=expected_operation,
        proposal_id=require_sha256(mapping["proposal_id"]),
        request_token=require_sha256(mapping["request_token"]),
        canonical_request_sha256=require_sha256(mapping["canonical_request_sha256"]),
    )


@final
class OwnerPrivateWordPressOperatorProposalIntentJournal:
    """One unresolved, crash-persistent proposal intent per closed operation."""

    __slots__ = ("_held_operation", "_owner_uid", "repository_root")

    def __init__(self, repository_root: object) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            _fail()
        self.repository_root = repository_root
        self._owner_uid = _effective_owner_uid()
        self._held_operation: WordPressOperatorOperation | None = None

    def __repr__(self) -> str:
        return "OwnerPrivateWordPressOperatorProposalIntentJournal(<redacted>)"

    @contextmanager
    def exclusive(self, operation: WordPressOperatorOperation) -> Generator[None]:
        if (
            type(operation) is not WordPressOperatorOperation
            or self._held_operation is not None
        ):
            _fail()
        directory_fd = _open_proposal_intent_directory(
            self.repository_root, self._owner_uid
        )
        descriptor = -1
        name = _PROPOSAL_LOCK_FILES[operation]
        try:
            created = False
            try:
                descriptor = os.open(
                    name,
                    _LOCK_FILE_FLAGS | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                created = True
            except FileExistsError:
                descriptor = os.open(name, _LOCK_FILE_FLAGS, dir_fd=directory_fd)
            if created:
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
                os.fsync(directory_fd)
            opened = os.fstat(descriptor)
            named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not _same_identity(opened, named)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != self._owner_uid
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or opened.st_size != 0
            ):
                _fail()
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                _fail()
            self._held_operation = operation
            yield
        except WordPressOperatorFailure:
            raise
        except BaseException:
            _fail()
        finally:
            self._held_operation = None
            if descriptor >= 0:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(descriptor)
            os.close(directory_fd)

    def _require_lock(self, operation: WordPressOperatorOperation) -> None:
        if (
            type(operation) is not WordPressOperatorOperation
            or self._held_operation is not operation
        ):
            _fail()

    def load(
        self, operation: WordPressOperatorOperation
    ) -> WordPressOperatorProposalIntent | None:
        self._require_lock(operation)
        directory_fd = _open_proposal_intent_directory(
            self.repository_root, self._owner_uid
        )
        try:
            _recover_proposal_intent_staging(directory_fd, operation, self._owner_uid)
            payload = _read_bounded_private_file(
                directory_fd,
                _PROPOSAL_INTENT_FILES[operation],
                maximum=MAX_PROPOSAL_INTENT_BYTES,
                owner_uid=self._owner_uid,
            )
        finally:
            os.close(directory_fd)
        if payload is None:
            return None
        return _decode_proposal_intent(payload, operation)

    def record(self, proposal: OperatorProposal) -> WordPressOperatorProposalIntent:
        if type(proposal) is not OperatorProposal:
            _fail()
        self._require_lock(proposal.operation)
        intent = WordPressOperatorProposalIntent(
            operation=proposal.operation,
            proposal_id=proposal.proposal_id,
            request_token=proposal.request_token,
            canonical_request_sha256=proposal.proposal_id,
        )
        payload = intent.canonical_bytes()
        if not 1 <= len(payload) <= MAX_PROPOSAL_INTENT_BYTES:
            _fail()
        directory_fd = _open_proposal_intent_directory(
            self.repository_root, self._owner_uid
        )
        descriptor = -1
        final_name = _PROPOSAL_INTENT_FILES[proposal.operation]
        staging_name = _PROPOSAL_INTENT_STAGING_FILES[proposal.operation]
        try:
            _recover_proposal_intent_staging(
                directory_fd, proposal.operation, self._owner_uid
            )
            if _named_metadata(directory_fd, final_name) is not None:
                _fail()
            descriptor = os.open(
                staging_name,
                _NEW_FILE_FLAGS,
                0o600,
                dir_fd=directory_fd,
            )
            os.fchmod(descriptor, 0o600)
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    _fail()
                offset += written
            os.fsync(descriptor)
            opened = os.fstat(descriptor)
            named = os.stat(staging_name, dir_fd=directory_fd, follow_symlinks=False)
            if (
                not _same_identity(opened, named)
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != self._owner_uid
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or opened.st_size != len(payload)
            ):
                _fail()
            os.link(
                staging_name,
                final_name,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
                follow_symlinks=False,
            )
            linked = os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
            staged = os.stat(staging_name, dir_fd=directory_fd, follow_symlinks=False)
            if not _same_identity(linked, staged) or linked.st_nlink != 2:
                _fail()
            os.unlink(staging_name, dir_fd=directory_fd)
            os.fsync(directory_fd)
            rebound = os.stat(final_name, dir_fd=directory_fd, follow_symlinks=False)
            if rebound.st_nlink != 1:
                _fail()
            return intent
        except WordPressOperatorFailure:
            raise
        except BaseException:
            _fail()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(directory_fd)

    def clear(self, proposal: OperatorProposal) -> None:
        if type(proposal) is not OperatorProposal:
            _fail()
        self._require_lock(proposal.operation)
        observed = self.load(proposal.operation)
        if (
            observed is None
            or observed.proposal_id != proposal.proposal_id
            or observed.request_token != proposal.request_token
        ):
            _fail()
        self._unlink(proposal.operation)

    def clear_matching_proposal_id(
        self, operation: WordPressOperatorOperation, proposal_id: str
    ) -> bool:
        self._require_lock(operation)
        proposal_id = require_sha256(proposal_id)
        observed = self.load(operation)
        if observed is None or observed.proposal_id != proposal_id:
            return False
        self._unlink(operation)
        return True

    def _unlink(self, operation: WordPressOperatorOperation) -> None:
        self._require_lock(operation)
        directory_fd = _open_proposal_intent_directory(
            self.repository_root, self._owner_uid
        )
        try:
            os.unlink(_PROPOSAL_INTENT_FILES[operation], dir_fd=directory_fd)
            os.fsync(directory_fd)
        except WordPressOperatorFailure:
            raise
        except BaseException:
            _fail()
        finally:
            os.close(directory_fd)


@final
class OwnerPrivateWordPressOperatorCredentialStore:
    """Read the one fixed credential record; installation is intentionally absent."""

    __slots__ = ("_owner_uid", "repository_root")

    def __init__(self, repository_root: object) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            _fail()
        self.repository_root = repository_root
        self._owner_uid = _effective_owner_uid()

    def __repr__(self) -> str:
        return "OwnerPrivateWordPressOperatorCredentialStore(<redacted>)"

    def read(self) -> WordPressOperatorCredentials:
        directory_fd = _open_credential_directory(self.repository_root, self._owner_uid)
        try:
            payload = _read_bounded_credential(directory_fd, self._owner_uid)
        finally:
            os.close(directory_fd)
        return _decode_credentials(payload)

    def read_metadata(self) -> WordPressOperatorCredentialMetadata:
        return self.read().metadata


__all__ = [
    "CREDENTIAL_RELATIVE_PATH",
    "MAX_CREDENTIAL_BYTES",
    "MAX_PROPOSAL_INTENT_BYTES",
    "OwnerPrivateWordPressOperatorProposalIntentJournal",
    "OwnerPrivateWordPressOperatorCredentialStore",
    "PROPOSAL_INTENT_RELATIVE_DIRECTORY",
    "WordPressOperatorCredentialMetadata",
    "WordPressOperatorCredentials",
    "WordPressOperatorProposalIntent",
]
