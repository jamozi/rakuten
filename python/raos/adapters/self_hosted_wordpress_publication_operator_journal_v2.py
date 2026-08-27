"""Crash-safe owner-private intent journal for publication operator v2."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Any, Final, NoReturn, SupportsIndex, cast, final

from raos.adapters import self_hosted_wordpress_operator_credentials as _v1_private
from raos.domain.operations.self_hosted_wordpress_operator import (
    WordPressOperatorFailure,
)
from raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2 import (
    DraftRevisionProposal,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationProposal,
    canonical_json_bytes,
    fail_publication_operator,
    require_publish_article_id,
    require_sha256,
)


PUBLICATION_INTENT_RELATIVE_DIRECTORY: Final = Path(
    ".secrets/wordpress-operator-local/publication-v2"
)
PUBLICATION_INTENT_FILE: Final = "publish-st1704-article.intent.v2.json"
PUBLICATION_INTENT_STAGING_FILE: Final = f".{PUBLICATION_INTENT_FILE}.pending"
PUBLICATION_INTENT_LOCK_FILE: Final = "publish-st1704-article.lock"
PUBLICATION_INTENT_SCHEMA: Final = "RAOS_ST1704_PUBLICATION_PROPOSAL_INTENT_V2"
MAX_PUBLICATION_INTENT_BYTES: Final = 4096
_ALLOWED_OPERATIONS: Final = frozenset(
    {"PUBLISH_ST1704_ARTICLE", "REVISE_ST1704_DRAFT"}
)

_DIRECTORY_NAME: Final = "publication-v2"
_LOCK_FLAGS: Final = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
_NEW_FILE_FLAGS: Final = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
)
_INTENT_KEYS: Final = frozenset(
    {
        "article_id",
        "canonical_request_sha256",
        "draft_post_id",
        "operation",
        "phase",
        "proposal_id",
        "request_token",
        "schema",
    }
)


class PublicationIntentPhase(StrEnum):
    CREATE_INTENT = "CREATE_INTENT"
    PROPOSED = "PROPOSED"
    APPLY_INTENT = "APPLY_INTENT"


_ALLOWED_TRANSITIONS: Final = frozenset(
    {
        (PublicationIntentPhase.CREATE_INTENT, PublicationIntentPhase.PROPOSED),
        (PublicationIntentPhase.PROPOSED, PublicationIntentPhase.APPLY_INTENT),
        (PublicationIntentPhase.APPLY_INTENT, PublicationIntentPhase.PROPOSED),
    }
)


def _fail(
    code: PublicationOperatorFailureCode = (
        PublicationOperatorFailureCode.JOURNAL_UNSAFE
    ),
) -> NoReturn:
    fail_publication_operator(code)


class _DuplicateKey(ValueError):
    pass


def _strict_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            raise _DuplicateKey
        result[key] = value
    return result


def _phase(value: object) -> PublicationIntentPhase:
    if type(value) is not str:
        _fail()
    try:
        return PublicationIntentPhase(value)
    except TypeError, ValueError:
        _fail()


def _post_id(value: object) -> int:
    if type(value) is not int or not 1 <= value <= (1 << 63) - 1:
        _fail()
    return value


def _proposal_identity(
    proposal: PublicationProposal | DraftRevisionProposal,
) -> tuple[str, int]:
    if isinstance(proposal, PublicationProposal):
        return proposal.binding.article_id, proposal.binding.draft_post_id
    if isinstance(proposal, DraftRevisionProposal):
        return proposal.binding.successor.article_id, proposal.binding.draft_id
    _fail()


@dataclass(frozen=True, slots=True, repr=False)
class PublicationProposalIntent:
    article_id: str
    draft_post_id: int
    proposal_id: str
    request_token: str
    canonical_request_sha256: str
    phase: PublicationIntentPhase
    operation: str = "PUBLISH_ST1704_ARTICLE"

    def __post_init__(self) -> None:
        require_publish_article_id(self.article_id)
        _post_id(self.draft_post_id)
        require_sha256(self.proposal_id)
        require_sha256(self.request_token)
        require_sha256(self.canonical_request_sha256)
        if (
            self.canonical_request_sha256 != self.proposal_id
            or type(self.phase) is not PublicationIntentPhase
            or self.operation not in _ALLOWED_OPERATIONS
        ):
            _fail(PublicationOperatorFailureCode.JOURNAL_MISMATCH)

    @classmethod
    def from_proposal(
        cls,
        proposal: PublicationProposal | DraftRevisionProposal,
        phase: PublicationIntentPhase,
    ) -> PublicationProposalIntent:
        if type(proposal) not in {PublicationProposal, DraftRevisionProposal}:
            _fail()
        article_id, draft_post_id = _proposal_identity(proposal)
        return cls(
            article_id=article_id,
            draft_post_id=draft_post_id,
            proposal_id=proposal.proposal_id,
            request_token=proposal.request_token,
            canonical_request_sha256=proposal.proposal_id,
            phase=phase,
            operation=proposal.operation.value,
        )

    def matches(
        self, proposal: PublicationProposal | DraftRevisionProposal
    ) -> bool:
        if type(proposal) not in {PublicationProposal, DraftRevisionProposal}:
            return False
        article_id, draft_post_id = _proposal_identity(proposal)
        return (
            self.article_id == article_id
            and self.draft_post_id == draft_post_id
            and self.proposal_id == proposal.proposal_id
            and self.request_token == proposal.request_token
            and self.canonical_request_sha256 == proposal.proposal_id
            and self.operation == proposal.operation.value
        )

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(
            {
                "article_id": self.article_id,
                "canonical_request_sha256": self.canonical_request_sha256,
                "draft_post_id": self.draft_post_id,
                "operation": self.operation,
                "phase": self.phase.value,
                "proposal_id": self.proposal_id,
                "request_token": self.request_token,
                "schema": PUBLICATION_INTENT_SCHEMA,
            }
        )

    def __str__(self) -> str:
        return "<redacted-publication-proposal-intent>"

    def __repr__(self) -> str:
        return "PublicationProposalIntent(<redacted>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("publication proposal intent serialization is disabled")


def _decode_intent(payload: bytes) -> PublicationProposalIntent:
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
        frozenset(mapping) != _INTENT_KEYS
        or mapping["schema"] != PUBLICATION_INTENT_SCHEMA
        or mapping["operation"] not in _ALLOWED_OPERATIONS
    ):
        _fail()
    try:
        return PublicationProposalIntent(
            article_id=require_publish_article_id(mapping["article_id"]),
            draft_post_id=_post_id(mapping["draft_post_id"]),
            proposal_id=require_sha256(mapping["proposal_id"]),
            request_token=require_sha256(mapping["request_token"]),
            canonical_request_sha256=require_sha256(
                mapping["canonical_request_sha256"]
            ),
            phase=_phase(mapping["phase"]),
            operation=mapping["operation"],
        )
    except PublicationOperatorFailure:
        _fail()


def _same_binding(
    left: PublicationProposalIntent, right: PublicationProposalIntent
) -> bool:
    return (
        left.article_id == right.article_id
        and left.draft_post_id == right.draft_post_id
        and left.proposal_id == right.proposal_id
        and left.request_token == right.request_token
        and left.canonical_request_sha256 == right.canonical_request_sha256
        and left.operation == right.operation
    )


@final
class OwnerPrivatePublicationProposalJournalV2:
    """One unresolved publication intent globally across all four articles."""

    __slots__ = ("_held", "_owner_uid", "repository_root")

    def __init__(self, repository_root: object) -> None:
        if not isinstance(repository_root, Path) or not repository_root.is_absolute():
            _fail()
        try:
            owner_uid = os.geteuid()
        except BaseException:
            _fail()
        if type(owner_uid) is not int or owner_uid < 0:
            _fail()
        self.repository_root = repository_root
        self._owner_uid = owner_uid
        self._held = False

    def __repr__(self) -> str:
        return "OwnerPrivatePublicationProposalJournalV2(<redacted>)"

    def _directory(self) -> int:
        try:
            parent = _v1_private._open_credential_directory(  # pyright: ignore[reportPrivateUsage]
                self.repository_root, self._owner_uid
            )
            try:
                try:
                    os.mkdir(_DIRECTORY_NAME, 0o700, dir_fd=parent)
                    os.fsync(parent)
                except FileExistsError:
                    pass
                return _v1_private._open_private_child(  # pyright: ignore[reportPrivateUsage]
                    parent, _DIRECTORY_NAME, self._owner_uid
                )
            finally:
                os.close(parent)
        except PublicationOperatorFailure:
            raise
        except WordPressOperatorFailure:
            _fail()
        except BaseException:
            _fail()

    @contextmanager
    def exclusive(self) -> Generator[None]:
        if self._held:
            _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        directory_fd = self._directory()
        descriptor = -1
        try:
            created = False
            try:
                descriptor = os.open(
                    PUBLICATION_INTENT_LOCK_FILE,
                    _LOCK_FLAGS | os.O_CREAT | os.O_EXCL,
                    0o600,
                    dir_fd=directory_fd,
                )
                created = True
            except FileExistsError:
                descriptor = os.open(
                    PUBLICATION_INTENT_LOCK_FILE,
                    _LOCK_FLAGS,
                    dir_fd=directory_fd,
                )
            if created:
                os.fchmod(descriptor, 0o600)
                os.fsync(descriptor)
                os.fsync(directory_fd)
            opened = os.fstat(descriptor)
            named = os.stat(
                PUBLICATION_INTENT_LOCK_FILE,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (
                not _v1_private._same_identity(opened, named)  # pyright: ignore[reportPrivateUsage]
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
                _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
            self._held = True
            yield
        except PublicationOperatorFailure:
            raise
        except WordPressOperatorFailure:
            _fail()
        except BaseException:
            _fail()
        finally:
            self._held = False
            if descriptor >= 0:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_UN)
                except OSError:
                    pass
                os.close(descriptor)
            os.close(directory_fd)

    def _require_lock(self) -> None:
        if not self._held:
            _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)

    def _metadata(self, directory_fd: int, name: str) -> os.stat_result | None:
        try:
            return _v1_private._named_metadata(  # pyright: ignore[reportPrivateUsage]
                directory_fd, name
            )
        except WordPressOperatorFailure:
            _fail()

    def _read(self, directory_fd: int, name: str) -> bytes | None:
        try:
            return _v1_private._read_bounded_private_file(  # pyright: ignore[reportPrivateUsage]
                directory_fd,
                name,
                maximum=MAX_PUBLICATION_INTENT_BYTES,
                owner_uid=self._owner_uid,
            )
        except WordPressOperatorFailure:
            _fail()

    def _recover_staging(self, directory_fd: int) -> None:
        final_metadata = self._metadata(directory_fd, PUBLICATION_INTENT_FILE)
        staging_metadata = self._metadata(directory_fd, PUBLICATION_INTENT_STAGING_FILE)
        if staging_metadata is None:
            return
        if (
            not stat.S_ISREG(staging_metadata.st_mode)
            or staging_metadata.st_uid != self._owner_uid
            or stat.S_IMODE(staging_metadata.st_mode) != 0o600
            or staging_metadata.st_nlink != 1
            or not 1 <= staging_metadata.st_size <= MAX_PUBLICATION_INTENT_BYTES
        ):
            _fail()
        staged_raw = self._read(directory_fd, PUBLICATION_INTENT_STAGING_FILE)
        if staged_raw is None:
            _fail()
        staged = _decode_intent(staged_raw)
        if final_metadata is not None:
            final_raw = self._read(directory_fd, PUBLICATION_INTENT_FILE)
            if final_raw is None:
                _fail()
            current = _decode_intent(final_raw)
            if staged == current:
                try:
                    os.unlink(PUBLICATION_INTENT_STAGING_FILE, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                    return
                except OSError:
                    _fail()
            if (
                not _same_binding(current, staged)
                or (current.phase, staged.phase) not in _ALLOWED_TRANSITIONS
            ):
                _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        try:
            os.replace(
                PUBLICATION_INTENT_STAGING_FILE,
                PUBLICATION_INTENT_FILE,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        except OSError:
            _fail()
        rebound = self._metadata(directory_fd, PUBLICATION_INTENT_FILE)
        if (
            rebound is None
            or rebound.st_uid != self._owner_uid
            or stat.S_IMODE(rebound.st_mode) != 0o600
            or rebound.st_nlink != 1
        ):
            _fail()

    def load(self) -> PublicationProposalIntent | None:
        self._require_lock()
        directory_fd = self._directory()
        try:
            self._recover_staging(directory_fd)
            raw = self._read(directory_fd, PUBLICATION_INTENT_FILE)
        finally:
            os.close(directory_fd)
        return None if raw is None else _decode_intent(raw)

    def _write_staging(self, intent: PublicationProposalIntent) -> None:
        self._require_lock()
        payload = intent.canonical_bytes()
        if not 1 <= len(payload) <= MAX_PUBLICATION_INTENT_BYTES:
            _fail()
        directory_fd = self._directory()
        descriptor = -1
        try:
            self._recover_staging(directory_fd)
            descriptor = os.open(
                PUBLICATION_INTENT_STAGING_FILE,
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
            named = os.stat(
                PUBLICATION_INTENT_STAGING_FILE,
                dir_fd=directory_fd,
                follow_symlinks=False,
            )
            if (
                not _v1_private._same_identity(opened, named)  # pyright: ignore[reportPrivateUsage]
                or not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != self._owner_uid
                or stat.S_IMODE(opened.st_mode) != 0o600
                or opened.st_nlink != 1
                or opened.st_size != len(payload)
            ):
                _fail()
            os.replace(
                PUBLICATION_INTENT_STAGING_FILE,
                PUBLICATION_INTENT_FILE,
                src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd,
            )
            os.fsync(directory_fd)
        except PublicationOperatorFailure:
            raise
        except WordPressOperatorFailure:
            _fail()
        except BaseException:
            _fail()
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            os.close(directory_fd)

    def record_create_intent(
        self, proposal: PublicationProposal | DraftRevisionProposal
    ) -> PublicationProposalIntent:
        self._require_lock()
        if self.load() is not None:
            _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        intent = PublicationProposalIntent.from_proposal(
            proposal, PublicationIntentPhase.CREATE_INTENT
        )
        self._write_staging(intent)
        observed = self.load()
        if observed != intent:
            _fail(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        return intent

    def require_matching(
        self, proposal: PublicationProposal | DraftRevisionProposal
    ) -> PublicationProposalIntent:
        self._require_lock()
        observed = self.load()
        if observed is None or not observed.matches(proposal):
            _fail(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        return observed

    def advance(
        self,
        proposal: PublicationProposal | DraftRevisionProposal,
        *,
        expected: PublicationIntentPhase,
        target: PublicationIntentPhase,
    ) -> PublicationProposalIntent:
        self._require_lock()
        observed = self.require_matching(proposal)
        if (
            observed.phase is not expected
            or (expected, target) not in _ALLOWED_TRANSITIONS
        ):
            _fail(PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS)
        advanced = PublicationProposalIntent.from_proposal(proposal, target)
        self._write_staging(advanced)
        rebound = self.load()
        if rebound != advanced:
            _fail(PublicationOperatorFailureCode.JOURNAL_MISMATCH)
        return advanced

    def clear_matching(
        self, proposal: PublicationProposal | DraftRevisionProposal
    ) -> None:
        self._require_lock()
        self.require_matching(proposal)
        directory_fd = self._directory()
        try:
            self._recover_staging(directory_fd)
            os.unlink(PUBLICATION_INTENT_FILE, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except PublicationOperatorFailure:
            raise
        except BaseException:
            _fail()
        finally:
            os.close(directory_fd)


__all__ = [
    "MAX_PUBLICATION_INTENT_BYTES",
    "OwnerPrivatePublicationProposalJournalV2",
    "PUBLICATION_INTENT_FILE",
    "PUBLICATION_INTENT_LOCK_FILE",
    "PUBLICATION_INTENT_RELATIVE_DIRECTORY",
    "PUBLICATION_INTENT_SCHEMA",
    "PublicationIntentPhase",
    "PublicationProposalIntent",
]
