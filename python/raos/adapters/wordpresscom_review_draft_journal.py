"""Owner-private durable create-or-replay journal for one WordPress.com draft."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
from typing import Any, Generator, NoReturn, cast, final

from raos.domain.editorial.wordpresscom_review_draft import (
    ReviewDraftDisposition,
    WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
    WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
    WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
    WordPressComReviewDraft,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    WordPressComReviewDraftReceipt,
    fail_wordpresscom_review_draft,
    require_exact_wordpresscom_review_draft,
)
from raos.ports.wordpresscom_review_draft_journal import (
    WordPressComReviewDraftAttemptPort,
)


_STATE_SCHEMA = "WORDPRESSCOM_REVIEW_DRAFT_STATE_V1"
_STATE_FILE = "review-draft-state.v1.json"
_LOCK_FILE = ".review-draft-state.v1.lock"
_INTENT_KEYS = {
    "content_sha256",
    "operation_binding_sha256",
    "schema",
    "state",
    "target_origin",
}
_COMMITTED_KEYS = _INTENT_KEYS | {
    "exact_status_on_success",
    "positive_draft_id_on_success",
    "response_body_sha256_on_success",
}


def _fail(code: WordPressComReviewDraftFailureCode) -> NoReturn:
    fail_wordpresscom_review_draft(code)


def _canonical_json(value: dict[str, object]) -> bytes:
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("ascii")
    except TypeError, ValueError, UnicodeError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    del value
    _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)


def _check_directory(path: Path, *, exact_mode: int) -> None:
    try:
        metadata = path.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != exact_mode
    ):
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)


def _check_no_symlink_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
        if stat.S_ISLNK(metadata.st_mode):
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
        if current.parent == current:
            break
        current = current.parent


def _open_private_file(path: Path, flags: int, mode: int = 0o600) -> int:
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags | nofollow, mode)
        metadata = os.fstat(descriptor)
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        os.close(descriptor)
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
    return descriptor


@contextmanager
def _locked(root: Path) -> Generator[None]:
    descriptor = _open_private_file(root / _LOCK_FILE, os.O_RDWR | os.O_CREAT)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    except WordPressComReviewDraftFailure:
        raise
    except BaseException:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _read_state(path: Path) -> dict[str, object] | None:
    try:
        path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    descriptor = _open_private_file(path, os.O_RDONLY)
    try:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 4096)
            if not chunk:
                break
            total += len(chunk)
            if total > 4096:
                _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
            chunks.append(chunk)
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    try:
        value = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeError, ValueError, RecursionError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
    if (
        type(value) is not dict
        or _canonical_json(cast(dict[str, object], value)) != raw
    ):
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
    return cast(dict[str, object], value)


def _write_state(root: Path, value: dict[str, object], *, replace: bool) -> None:
    state_path = root / _STATE_FILE
    data = _canonical_json(value)
    temporary = root / ".review-draft-state.v1.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = _open_private_file(temporary, flags)
    try:
        written = 0
        while written < len(data):
            count = os.write(descriptor, data[written:])
            if count <= 0:
                _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
            written += count
        os.fsync(descriptor)
    except WordPressComReviewDraftFailure:
        raise
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)
    finally:
        os.close(descriptor)
    try:
        if not replace and state_path.exists():
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
        os.replace(temporary, state_path)
        directory_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except WordPressComReviewDraftFailure:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_IO_FAILURE)


def _intent(candidate: WordPressComReviewDraft) -> dict[str, object]:
    return {
        "content_sha256": candidate.content_sha256,
        "operation_binding_sha256": candidate.operation_binding_sha256,
        "schema": _STATE_SCHEMA,
        "state": "INTENT",
        "target_origin": candidate.target_origin,
    }


def _require_binding(
    state: dict[str, object], candidate: WordPressComReviewDraft
) -> None:
    if (
        state.get("schema") != _STATE_SCHEMA
        or state.get("target_origin") != candidate.target_origin
        or state.get("operation_binding_sha256") != candidate.operation_binding_sha256
        or state.get("content_sha256") != candidate.content_sha256
    ):
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_MISMATCH)


def _receipt_from_state(
    state: dict[str, object], candidate: WordPressComReviewDraft
) -> WordPressComReviewDraftReceipt:
    if set(state) != _COMMITTED_KEYS or state.get("state") != "COMMITTED":
        _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
    _require_binding(state, candidate)
    return WordPressComReviewDraftReceipt(
        schema=WORDPRESSCOM_REVIEW_DRAFT_RECEIPT_SCHEMA,
        authority=WORDPRESSCOM_REVIEW_DRAFT_AUTHORITY,
        network_status=WORDPRESSCOM_REVIEW_DRAFT_NETWORK_STATUS,
        target_origin=candidate.target_origin,
        draft_id=cast(int, state["positive_draft_id_on_success"]),
        status=cast(str, state["exact_status_on_success"]),
        operation_binding_sha256=candidate.operation_binding_sha256,
        content_sha256=candidate.content_sha256,
        response_body_sha256=cast(str, state["response_body_sha256_on_success"]),
        disposition=ReviewDraftDisposition.COMMITTED_REPLAY,
        publication_authorized=False,
        production_eligible=False,
    )


@final
class DurableWordPressComReviewDraftAdapter:
    """Call the creator at most once after durable intent, then replay locally."""

    __slots__ = ("_creator", "_root")

    def __init__(self, *, private_root: object, creator: object) -> None:
        if not isinstance(private_root, Path) or not isinstance(
            creator, WordPressComReviewDraftAttemptPort
        ):
            _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
        root = Path(os.path.abspath(private_root))
        _check_no_symlink_ancestors(root)
        _check_directory(root, exact_mode=0o700)
        self._root = root
        self._creator = creator

    def __repr__(self) -> str:
        return "DurableWordPressComReviewDraftAdapter(<redacted-review-draft>)"

    def create_review_draft(
        self, candidate: WordPressComReviewDraft
    ) -> WordPressComReviewDraftReceipt:
        require_exact_wordpresscom_review_draft(candidate)
        _check_no_symlink_ancestors(self._root)
        _check_directory(self._root, exact_mode=0o700)
        with _locked(self._root):
            state = _read_state(self._root / _STATE_FILE)
            if state is not None:
                state_name = state.get("state")
                if state_name == "COMMITTED":
                    return _receipt_from_state(state, candidate)
                if set(state) != _INTENT_KEYS:
                    _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)
                _require_binding(state, candidate)
                if state_name == "INTENT":
                    _fail(WordPressComReviewDraftFailureCode.JOURNAL_AMBIGUOUS)
                _fail(WordPressComReviewDraftFailureCode.JOURNAL_INVALID)

            try:
                self._creator.require_create_capability(candidate)
            except WordPressComReviewDraftFailure:
                raise
            except BaseException:
                _fail(WordPressComReviewDraftFailureCode.HTTPS_SETUP_INVALID)
            _write_state(self._root, _intent(candidate), replace=False)
            try:
                receipt = self._creator.attempt_create_review_draft(candidate)
            except BaseException:
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            try:
                if type(receipt) is not WordPressComReviewDraftReceipt:
                    _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
                receipt.__post_init__()
            except BaseException:
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            if (
                receipt.target_origin != candidate.target_origin
                or receipt.operation_binding_sha256
                != candidate.operation_binding_sha256
                or receipt.content_sha256 != candidate.content_sha256
                or receipt.disposition is not ReviewDraftDisposition.CREATED
            ):
                _fail(WordPressComReviewDraftFailureCode.CREATE_AMBIGUOUS)
            committed = {
                **_intent(candidate),
                "exact_status_on_success": receipt.status,
                "positive_draft_id_on_success": receipt.draft_id,
                "response_body_sha256_on_success": receipt.response_body_sha256,
                "state": "COMMITTED",
            }
            _write_state(self._root, committed, replace=True)
            return receipt


__all__ = ["DurableWordPressComReviewDraftAdapter"]
