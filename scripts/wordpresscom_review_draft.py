#!/usr/bin/env python3
"""Operate the exact ST-1703 WordPress.com review-draft slice."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import termios
from typing import Any, Callable, Final, NoReturn


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT: Final = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.wordpresscom_oauth import (  # noqa: E402
    SystemWordPressComBrowserOpener,
    SystemWordPressComEntropySource,
    SystemWordPressComLoopbackListener,
    SystemWordPressComOAuthTokenTransport,
    WORDPRESSCOM_CLIENT_ID_ALIAS,
    WORDPRESSCOM_CLIENT_SECRET_ALIAS,
    WORDPRESSCOM_OAUTH_REDIRECT_URI,
    WORDPRESSCOM_OAUTH_SCOPE,
    WordPressComOAuthClientId,
    WordPressComOAuthClientSecret,
    WordPressComOAuthCallbackDiagnosticCode,
    WordPressComOAuthCallbackFailure,
    WordPressComOAuthSecretStore,
    WordPressComOAuthSetup,
    WordPressComOAuthTokenDiagnosticCode,
    WordPressComOAuthTokenFailure,
)
from raos.adapters.wordpresscom_review_draft_https import (  # noqa: E402
    OfficialWordPressComReviewDraftAdapter,
    SystemWordPressComHttpsConnectionFactory,
)
from raos.adapters.wordpresscom_mvp_draft_https import (  # noqa: E402
    OfficialWordPressComMvpDraftAdapter,
)
from raos.adapters.wordpresscom_mvp_draft_journal import (  # noqa: E402
    EmptyWordPressComMvpDraftJournalView,
    ImmutableWordPressComMvpDraftJournal,
)
from raos.application.editorial.wordpresscom_mvp_drafts import (  # noqa: E402
    build_bound_wordpresscom_mvp_content,
)
from raos.application.editorial.wordpresscom_mvp_preparation import (  # noqa: E402
    WordPressComMvpDraftPreparationService,
)
from raos.adapters.wordpresscom_review_draft_journal import (  # noqa: E402
    DurableWordPressComReviewDraftAdapter,
)
from raos.application.editorial.wordpresscom_review_draft import (  # noqa: E402
    build_bound_review_draft,
)
from raos.domain.editorial.wordpresscom_review_draft import (  # noqa: E402
    WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256,
    WORDPRESSCOM_REVIEW_DRAFT_TARGET,
    WordPressComReviewDraftFailure,
    WordPressComReviewDraftFailureCode,
    WordPressComReviewDraftReceipt,
    fail_wordpresscom_review_draft,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (  # noqa: E402
    MvpDraftContentBundle,
    MvpDraftPreview,
    WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256,
    WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256,
    WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256,
    WordPressComMvpDraftFailure,
    WordPressComMvpDraftFailureCode,
    fail_wordpresscom_mvp_draft,
)
from raos.ports.wordpresscom_mvp_draft_journal import (  # noqa: E402
    WordPressComMvpDraftJournalPort,
)


_EXPECTED_REPOSITORY_ROOT: Final = Path("/home/minami/rakuten")
_APPLICATION_REGISTRATION_URL: Final = "https://developer.wordpress.com/apps/new/"
_SECRET_PARENT: Final = Path(".secrets")
_SECRET_ROOT: Final = _SECRET_PARENT / "wordpresscom-review-draft"
_STATE_ROOT: Final = _SECRET_ROOT / "state"
_MVP_STATE_ROOT: Final = _SECRET_ROOT / "mvp-wave3-state"
_MVP_RECORDS_ROOT: Final = _MVP_STATE_ROOT / "records"
_BASE_HANDOFF_PATH: Final = Path(
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml"
)
_AMENDMENT_HANDOFF_PATH: Final = Path(
    "changes/st-1703/"
    "DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml"
)
_ACTIVATION_HANDOFF_PATH: Final = Path(
    "changes/st-1703/"
    "DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml"
)
_ARTICLE_PATH: Final = Path("changes/st-1703/first-article-review-draft.v1.md")
_SOURCE_PACKET_PATH: Final = Path(
    "changes/st-1703/source-packet-candidate.first-article.v1.yaml"
)
_FIXED_SOURCES: Final = (
    (_BASE_HANDOFF_PATH, 17_895, WORDPRESSCOM_REVIEW_DRAFT_BASE_HANDOFF_SHA256),
    (
        _AMENDMENT_HANDOFF_PATH,
        12_742,
        WORDPRESSCOM_REVIEW_DRAFT_AMENDMENT_HANDOFF_SHA256,
    ),
    (_ACTIVATION_HANDOFF_PATH, 12_678, WORDPRESSCOM_REVIEW_DRAFT_HANDOFF_SHA256),
    (_ARTICLE_PATH, 11_109, WORDPRESSCOM_REVIEW_DRAFT_ARTICLE_SHA256),
    (_SOURCE_PACKET_PATH, 8_116, WORDPRESSCOM_REVIEW_DRAFT_SOURCE_PACKET_SHA256),
)
_MVP_HANDOFF_PATH: Final = Path(
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3.yaml"
)
_MVP_APPROVAL_PATH: Final = Path(
    "changes/st-1703/"
    "DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3-v1.yaml"
)
_MVP_CONTENT_PACKET_PATH: Final = Path(
    "changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml"
)
_MVP_WAVE3A_HANDOFF_PATH: Final = Path(
    "changes/st-1703/"
    "DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3A_"
    "OPAQUE_DISCUSSION_EXTENSIONS.yaml"
)
_MVP_WAVE3A_APPROVAL_PATH: Final = Path(
    "changes/st-1703/"
    "DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3A-"
    "OPAQUE-DISCUSSION-EXTENSIONS-v1.yaml"
)
_MVP_WAVE3A_HANDOFF_SHA256: Final = (
    "1c0d50faedd3c76d18101afb1032d82da21a6daf0a01e9c687371d20519926aa"
)
_MVP_WAVE3A_APPROVAL_SHA256: Final = (
    "c1002959dda0de0ba0c0535697a814fa3221fcb05c7947f543452ef99232afb0"
)
_MVP_FIXED_SOURCES: Final = (
    *_FIXED_SOURCES,
    (_MVP_HANDOFF_PATH, 29_041, WORDPRESSCOM_MVP_WAVE3_HANDOFF_SHA256),
    (_MVP_APPROVAL_PATH, 1_991, WORDPRESSCOM_MVP_WAVE3_APPROVAL_SHA256),
    (
        _MVP_CONTENT_PACKET_PATH,
        12_670,
        WORDPRESSCOM_MVP_WAVE3_CONTENT_PACKET_SHA256,
    ),
    (_MVP_WAVE3A_HANDOFF_PATH, 12_741, _MVP_WAVE3A_HANDOFF_SHA256),
    (_MVP_WAVE3A_APPROVAL_PATH, 1_852, _MVP_WAVE3A_APPROVAL_SHA256),
)
_MVP_QUIESCENCE_PHRASE: Final = b"AFFIRM REMOTE WRITERS QUIESCED UNTIL FINAL READBACK"
_MVP_QUIESCENCE_PROMPT: Final = (
    "Type AFFIRM REMOTE WRITERS QUIESCED UNTIL FINAL READBACK: "
)
_MVP_APPROVED_BASE_COMMIT: Final = "acd79848a1b5bc33974bbcdbf5e2bd1d8e2ca60d"
_MVP_RUNTIME_MANIFEST_PATH: Final = Path(
    "changes/st-1703/wordpresscom-mvp-draft-preparation.wave3.runtime-manifest.v1.json"
)
_MVP_RUNTIME_PATHS: Final = (
    "Makefile",
    "changes/st-1703/DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3-v1.yaml",
    "changes/st-1703/DESIGN-HANDOFF-APPROVAL-WORDPRESSCOM-MVP-DRAFT-PREPARATION-WAVE-3A-OPAQUE-DISCUSSION-EXTENSIONS-v1.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3A_OPAQUE_DISCUSSION_EXTENSIONS.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2A_NUMERIC_PROXY_ACTIVATION.yaml",
    "changes/st-1703/DESIGN_HANDOFF_V1_WORDPRESSCOM_REVIEW_DRAFT_WAVE_2B_V1_1_ACTIVATION.yaml",
    "changes/st-1703/first-article-review-draft.v1.md",
    "changes/st-1703/source-packet-candidate.first-article.v1.yaml",
    "changes/st-1703/wordpresscom-mvp-draft-content.wave3.v1.yaml",
    "python/raos/adapters/wordpresscom_mvp_draft_https.py",
    "python/raos/adapters/wordpresscom_mvp_draft_journal.py",
    "python/raos/adapters/wordpresscom_oauth.py",
    "python/raos/adapters/wordpresscom_review_draft_https.py",
    "python/raos/adapters/wordpresscom_review_draft_journal.py",
    "python/raos/application/editorial/wordpresscom_mvp_affiliate.py",
    "python/raos/application/editorial/wordpresscom_mvp_drafts.py",
    "python/raos/application/editorial/wordpresscom_mvp_preparation.py",
    "python/raos/application/editorial/wordpresscom_review_draft.py",
    "python/raos/domain/editorial/wordpresscom_mvp_drafts.py",
    "python/raos/domain/editorial/wordpresscom_review_draft.py",
    "python/raos/ports/wordpresscom_mvp_draft_journal.py",
    "python/raos/ports/wordpresscom_mvp_drafts.py",
    "python/raos/ports/wordpresscom_review_draft_journal.py",
    "scripts/wordpresscom_review_draft.py",
    "scripts/wordpresscom_review_draft_python.sh",
)
_MVP_MANIFEST_MAX_BYTES: Final = 65_536
_MVP_RUNTIME_FILE_MAX_BYTES: Final = 2_000_000
_MVP_GIT: Final = Path("/usr/bin/git")
_MVP_EXPECTED_PYTHON_BASE: Final = Path(
    "/home/minami/.local/share/uv/python/cpython-3.14.6-linux-x86_64-gnu"
)
_MVP_EXPECTED_VENV: Final = _EXPECTED_REPOSITORY_ROOT / ".venv"
_MVP_EXPECTED_PYTHON: Final = _MVP_EXPECTED_PYTHON_BASE / "bin/python3.14"


def _fail(code: WordPressComReviewDraftFailureCode) -> NoReturn:
    fail_wordpresscom_review_draft(code)


def _mvp_fail(code: WordPressComMvpDraftFailureCode) -> NoReturn:
    fail_wordpresscom_mvp_draft(code)


def _mvp_manifest_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if type(key) is not str or key in result:
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        result[key] = value
    return result


def _physical_repository_root(value: object) -> Path:
    if not isinstance(value, Path):
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    try:
        root = Path(os.path.abspath(value))
        metadata = root.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    if (
        root != _EXPECTED_REPOSITORY_ROOT
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
    ):
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    return root


def _require_no_symlink_ancestors(path: Path) -> None:
    current = path
    while True:
        try:
            metadata = current.lstat()
        except OSError:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        if stat.S_ISLNK(metadata.st_mode):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        if current.parent == current:
            return
        current = current.parent


def _ensure_private_directory(path: Path, *, parent: Path) -> None:
    _require_no_symlink_ancestors(parent)
    try:
        parent_metadata = parent.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        not stat.S_ISDIR(parent_metadata.st_mode)
        or parent_metadata.st_uid != os.geteuid()
        or stat.S_IMODE(parent_metadata.st_mode) != 0o700
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    try:
        os.mkdir(path, mode=0o700)
        directory_descriptor = os.open(
            parent,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except FileExistsError:
        pass
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    _require_no_symlink_ancestors(path)
    try:
        metadata = path.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)


def _ensure_secret_roots(repository_root: Path, *, include_state: bool) -> None:
    secret_parent = repository_root / _SECRET_PARENT
    try:
        os.mkdir(secret_parent, mode=0o700)
    except FileExistsError:
        pass
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    _require_no_symlink_ancestors(secret_parent)
    try:
        metadata = secret_parent.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    secret_root = repository_root / _SECRET_ROOT
    _ensure_private_directory(secret_root, parent=secret_parent)
    if include_state:
        _ensure_private_directory(repository_root / _STATE_ROOT, parent=secret_root)


def _private_file_exists(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.geteuid()
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    return True


def _read_private_tty(prompt: str) -> bytes:
    if type(prompt) is not str or not prompt.isascii() or not prompt:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    descriptor: int | None = None
    original: list[Any] | None = None
    try:
        descriptor = os.open(
            "/dev/tty",
            os.O_RDWR | getattr(os, "O_NOCTTY", 0) | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if not stat.S_ISCHR(metadata.st_mode):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        original = termios.tcgetattr(descriptor)
        hidden = original.copy()
        hidden[3] &= ~(termios.ECHO | getattr(termios, "ECHONL", 0))
        termios.tcsetattr(descriptor, termios.TCSANOW, hidden)
        prompt_bytes = prompt.encode("ascii")
        prompt_offset = 0
        while prompt_offset < len(prompt_bytes):
            written = os.write(descriptor, prompt_bytes[prompt_offset:])
            if written <= 0:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
            prompt_offset += written
        value = bytearray()
        while True:
            chunk = os.read(descriptor, 1)
            if not chunk:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
            if chunk == b"\n":
                break
            if chunk == b"\r" or len(value) >= 4096:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
            value.extend(chunk)
        if not value:
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        return bytes(value)
    except WordPressComReviewDraftFailure:
        raise
    except BaseException:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    finally:
        if descriptor is not None:
            if original is not None:
                try:
                    termios.tcsetattr(descriptor, termios.TCSANOW, original)
                except BaseException:
                    pass
            try:
                os.write(descriptor, b"\n")
            except BaseException:
                pass
            try:
                os.close(descriptor)
            except BaseException:
                pass


def _write_private_credential(path: Path, value: bytes) -> None:
    descriptor: int | None = None
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.geteuid()
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
        data = value + b"\n"
        offset = 0
        while offset < len(data):
            written = os.write(descriptor, data[offset:])
            if written <= 0:
                _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
            offset += written
        os.fsync(descriptor)
    except WordPressComReviewDraftFailure:
        raise
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    try:
        parent_descriptor = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0),
        )
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)


def _initialize_client_credentials(
    repository_root: Path,
    *,
    reader: Callable[[str], bytes] | None = None,
) -> None:
    root = repository_root / _SECRET_ROOT
    client_id_path = root / WORDPRESSCOM_CLIENT_ID_ALIAS
    client_secret_path = root / WORDPRESSCOM_CLIENT_SECRET_ALIAS
    client_id_exists = _private_file_exists(client_id_path)
    client_secret_exists = _private_file_exists(client_secret_path)
    if client_id_exists and client_secret_exists:
        return
    if client_id_exists or client_secret_exists:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    effective_reader = _read_private_tty if reader is None else reader
    try:
        client_id = WordPressComOAuthClientId(
            effective_reader("WordPress.com Client ID: ")
        )
        client_secret = WordPressComOAuthClientSecret(
            effective_reader("WordPress.com Client Secret: ")
        )
    except WordPressComReviewDraftFailure:
        raise
    except BaseException:
        _fail(WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID)
    _write_private_credential(client_id_path, client_id._value)
    _write_private_credential(client_secret_path, client_secret._value)


def _read_fixed_source(
    repository_root: Path, relative: Path, expected_bytes: int, expected_sha256: str
) -> bytes:
    path = repository_root / relative
    try:
        metadata_before = path.lstat()
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    if (
        stat.S_ISLNK(metadata_before.st_mode)
        or not stat.S_ISREG(metadata_before.st_mode)
        or metadata_before.st_size != expected_bytes
    ):
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        metadata_open = os.fstat(descriptor)
        if not stat.S_ISREG(metadata_open.st_mode) or (
            metadata_open.st_dev,
            metadata_open.st_ino,
        ) != (metadata_before.st_dev, metadata_before.st_ino):
            _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(4096, expected_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > expected_bytes:
                _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
            chunks.append(chunk)
    except WordPressComReviewDraftFailure:
        raise
    except OSError:
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    value = b"".join(chunks)
    if (
        len(value) != expected_bytes
        or hashlib.sha256(value).hexdigest() != expected_sha256
    ):
        _fail(WordPressComReviewDraftFailureCode.SOURCE_BINDING_INVALID)
    return value


def _read_mvp_runtime_file(
    repository_root: Path, relative: Path, *, maximum_bytes: int
) -> bytes:
    if (
        not isinstance(relative, Path)
        or relative.is_absolute()
        or ".." in relative.parts
        or type(maximum_bytes) is not int
        or not 1 <= maximum_bytes <= _MVP_RUNTIME_FILE_MAX_BYTES
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    path = repository_root / relative
    try:
        _require_no_symlink_ancestors(path.parent)
        before = path.lstat()
        if (
            stat.S_ISLNK(before.st_mode)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.geteuid()
            or not 1 <= before.st_size <= maximum_bytes
        ):
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_uid != os.geteuid()
                or (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino)
            ):
                _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = os.read(descriptor, min(65_536, maximum_bytes + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > maximum_bytes:
                    _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
                chunks.append(chunk)
        finally:
            os.close(descriptor)
    except WordPressComMvpDraftFailure:
        raise
    except WordPressComReviewDraftFailure:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    except OSError:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    value = b"".join(chunks)
    if len(value) != before.st_size:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return value


def _mvp_git_result(
    repository_root: Path,
    arguments: tuple[str, ...],
    *,
    capture_stdout: bool,
    maximum_stdout: int = 4096,
) -> subprocess.CompletedProcess[bytes]:
    if (
        type(arguments) is not tuple
        or not arguments
        or any(type(value) is not str or not value for value in arguments)
        or type(maximum_stdout) is not int
        or not 0 <= maximum_stdout <= _MVP_RUNTIME_FILE_MAX_BYTES
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    try:
        metadata = _MVP_GIT.lstat()
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or not os.access(_MVP_GIT, os.X_OK)
        ):
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        result = subprocess.run(
            (
                str(_MVP_GIT),
                "--no-optional-locks",
                "--literal-pathspecs",
                "-c",
                "core.fsmonitor=false",
                *arguments,
            ),
            cwd=repository_root,
            env={
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            },
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
            check=False,
        )
    except WordPressComMvpDraftFailure:
        raise
    except BaseException:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if capture_stdout and len(result.stdout) > maximum_stdout:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return result


def _mvp_head_blob(
    repository_root: Path,
    *,
    commit: str,
    path: str,
    maximum_bytes: int,
) -> bytes:
    object_name = f"{commit}:{path}"
    size_result = _mvp_git_result(
        repository_root,
        ("cat-file", "-s", object_name),
        capture_stdout=True,
        maximum_stdout=80,
    )
    if size_result.returncode != 0:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    try:
        size_text = size_result.stdout.decode("ascii", errors="strict").strip()
        size = int(size_text)
    except UnicodeError, ValueError:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if (
        str(size) != size_text
        or not 1 <= size <= maximum_bytes
        or maximum_bytes > _MVP_RUNTIME_FILE_MAX_BYTES
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    blob = _mvp_git_result(
        repository_root,
        ("cat-file", "blob", object_name),
        capture_stdout=True,
        maximum_stdout=size,
    )
    if blob.returncode != 0 or len(blob.stdout) != size:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return blob.stdout


def _valid_mvp_python_runtime() -> bool:
    return (
        sys.version_info[:3] == (3, 14, 6)
        and sys.flags.isolated == 1
        and Path(sys.prefix) == _MVP_EXPECTED_VENV
        and Path(sys.base_prefix) == _MVP_EXPECTED_PYTHON_BASE
        and Path(sys.executable).resolve() == _MVP_EXPECTED_PYTHON
    )


def _verify_mvp_runtime_identity(repository_root: Path) -> None:
    """Bind one committed, clean runtime inventory before any live capability."""

    if (
        repository_root != _EXPECTED_REPOSITORY_ROOT
        or Path(__file__).resolve()
        != repository_root / "scripts/wordpresscom_review_draft.py"
        or not _valid_mvp_python_runtime()
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    raw = _read_mvp_runtime_file(
        repository_root,
        _MVP_RUNTIME_MANIFEST_PATH,
        maximum_bytes=_MVP_MANIFEST_MAX_BYTES,
    )
    try:
        parsed = json.loads(
            raw.decode("ascii", errors="strict"),
            object_pairs_hook=_mvp_manifest_pairs,
            parse_constant=lambda _value: _mvp_fail(
                WordPressComMvpDraftFailureCode.BINDING_INVALID
            ),
        )
    except WordPressComMvpDraftFailure:
        raise
    except UnicodeError, ValueError, RecursionError:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if type(parsed) is not dict:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    manifest = parsed
    if set(manifest) != {
        "approved_base_commit",
        "generated_by",
        "paths",
        "schema",
        "slice_id",
        "story_id",
    } or (
        manifest.get("schema") != "WORDPRESSCOM_MVP_DRAFT_RUNTIME_MANIFEST_V1"
        or manifest.get("generated_by")
        != "python3 scripts/build_wordpresscom_mvp_runtime_manifest.py"
        or manifest.get("story_id") != "ST-1703"
        or manifest.get("slice_id") != "WORDPRESSCOM_MVP_DRAFT_PREPARATION_WAVE_3"
        or manifest.get("approved_base_commit") != _MVP_APPROVED_BASE_COMMIT
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    values = manifest.get("paths")
    if type(values) is not list or len(values) != len(_MVP_RUNTIME_PATHS):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    observed_paths: list[str] = []
    runtime_contents: dict[str, bytes] = {}
    for value in values:
        if type(value) is not dict or set(value) != {"bytes", "path", "sha256"}:
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        path = value.get("path")
        expected_bytes = value.get("bytes")
        expected_sha256 = value.get("sha256")
        if (
            type(path) is not str
            or type(expected_bytes) is not int
            or not 1 <= expected_bytes <= _MVP_RUNTIME_FILE_MAX_BYTES
            or type(expected_sha256) is not str
            or len(expected_sha256) != 64
            or any(character not in "0123456789abcdef" for character in expected_sha256)
        ):
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        observed_paths.append(path)
        content = _read_mvp_runtime_file(
            repository_root,
            Path(path),
            maximum_bytes=_MVP_RUNTIME_FILE_MAX_BYTES,
        )
        if (
            len(content) != expected_bytes
            or hashlib.sha256(content).hexdigest() != expected_sha256
        ):
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
        runtime_contents[path] = content
    if tuple(observed_paths) != _MVP_RUNTIME_PATHS:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    top = _mvp_git_result(
        repository_root, ("rev-parse", "--show-toplevel"), capture_stdout=True
    )
    if top.returncode != 0:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    try:
        top_path = Path(top.stdout.decode("utf-8", errors="strict").strip())
    except UnicodeError:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if top_path != repository_root:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    head = _mvp_git_result(
        repository_root, ("rev-parse", "--verify", "HEAD"), capture_stdout=True
    )
    if head.returncode != 0:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    try:
        head_commit = head.stdout.decode("ascii", errors="strict").strip()
    except UnicodeError:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if len(head_commit) != 40 or any(
        character not in "0123456789abcdef" for character in head_commit
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if (
        _mvp_git_result(
            repository_root,
            (
                "merge-base",
                "--is-ancestor",
                _MVP_APPROVED_BASE_COMMIT,
                head_commit,
            ),
            capture_stdout=False,
        ).returncode
        != 0
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    if (
        _mvp_head_blob(
            repository_root,
            commit=head_commit,
            path=_MVP_RUNTIME_MANIFEST_PATH.as_posix(),
            maximum_bytes=_MVP_MANIFEST_MAX_BYTES,
        )
        != raw
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    for path in _MVP_RUNTIME_PATHS:
        if (
            _mvp_head_blob(
                repository_root,
                commit=head_commit,
                path=path,
                maximum_bytes=_MVP_RUNTIME_FILE_MAX_BYTES,
            )
            != runtime_contents[path]
        ):
            _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    tracked_paths = (_MVP_RUNTIME_MANIFEST_PATH.as_posix(), *_MVP_RUNTIME_PATHS)
    if (
        _mvp_git_result(
            repository_root,
            ("ls-files", "--error-unmatch", "--", *tracked_paths),
            capture_stdout=False,
        ).returncode
        != 0
        or _mvp_git_result(
            repository_root,
            (
                "diff",
                "--no-ext-diff",
                "--no-textconv",
                "--quiet",
                head_commit,
                "--",
                *tracked_paths,
            ),
            capture_stdout=False,
        ).returncode
        != 0
    ):
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)


def _build_mvp_bundle(repository_root: Path) -> MvpDraftContentBundle:
    """Verify every approved byte before any secret, journal, or network access."""

    try:
        source_values = {
            path: _read_fixed_source(repository_root, path, size, sha256)
            for path, size, sha256 in _MVP_FIXED_SOURCES
        }
        baseline = build_bound_review_draft(
            article_bytes=source_values[_ARTICLE_PATH],
            source_packet_bytes=source_values[_SOURCE_PACKET_PATH],
            base_handoff_bytes=source_values[_BASE_HANDOFF_PATH],
            amendment_handoff_bytes=source_values[_AMENDMENT_HANDOFF_PATH],
            activation_handoff_bytes=source_values[_ACTIVATION_HANDOFF_PATH],
        )
    except WordPressComReviewDraftFailure:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    return build_bound_wordpresscom_mvp_content(
        handoff_bytes=source_values[_MVP_HANDOFF_PATH],
        approval_bytes=source_values[_MVP_APPROVAL_PATH],
        content_packet_bytes=source_values[_MVP_CONTENT_PACKET_PATH],
        baseline_draft=baseline,
    )


def _affirm_mvp_remote_writer_quiescence(
    *, reader: Callable[[str], bytes] = _read_private_tty
) -> bool:
    """Require one exact, contemporaneous owner-operated TTY affirmation."""

    value = bytearray()
    try:
        observed = reader(_MVP_QUIESCENCE_PROMPT)
        if type(observed) is not bytes:
            return False
        value.extend(observed)
        return hmac.compare_digest(value, _MVP_QUIESCENCE_PHRASE)
    except BaseException:
        return False
    finally:
        for index in range(len(value)):
            value[index] = 0


def _ensure_mvp_journal_roots(repository_root: Path) -> Path:
    try:
        _ensure_secret_roots(repository_root, include_state=False)
    except WordPressComReviewDraftFailure:
        _mvp_fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    secret_root = repository_root / _SECRET_ROOT
    state_root = repository_root / _MVP_STATE_ROOT
    records_root = repository_root / _MVP_RECORDS_ROOT
    try:
        _ensure_private_directory(state_root, parent=secret_root)
        _ensure_private_directory(records_root, parent=state_root)
    except WordPressComReviewDraftFailure:
        _mvp_fail(WordPressComMvpDraftFailureCode.JOURNAL_INVALID)
    return state_root


def _mvp_preview_journal(
    repository_root: Path,
) -> WordPressComMvpDraftJournalPort:
    state_root = repository_root / _MVP_STATE_ROOT
    try:
        state_root.lstat()
    except FileNotFoundError:
        return EmptyWordPressComMvpDraftJournalView()
    except OSError:
        _mvp_fail(WordPressComMvpDraftFailureCode.JOURNAL_IO_FAILURE)
    return ImmutableWordPressComMvpDraftJournal(root=state_root)


def _mvp_preview_output(command: str, preview: object) -> dict[str, object]:
    if type(preview) is not MvpDraftPreview or command not in {
        "prepare-mvp-drafts",
        "preview-mvp",
    }:
        _mvp_fail(WordPressComMvpDraftFailureCode.BINDING_INVALID)
    preview.__post_init__()
    for operation in preview.operations:
        operation.__post_init__()
    return {
        "affiliate_slot_count": preview.affiliate_slot_count,
        "affiliate_state": preview.affiliate_state.value,
        "base_state": preview.base_state.value,
        "command": command,
        "manual_review_state": preview.manual_review_state.value,
        "operations": [
            {
                "operation": operation.operation_id,
                "reason_code": operation.reason_code.value,
                "state": operation.observation.value,
            }
            for operation in preview.operations
        ],
        "publication_authority": preview.publication_authority,
    }


def _run_prepare_mvp_drafts(
    repository_root: Path,
    *,
    affirmer: Callable[[], bool] = _affirm_mvp_remote_writer_quiescence,
) -> dict[str, object]:
    _verify_mvp_runtime_identity(repository_root)
    bundle = _build_mvp_bundle(repository_root)
    try:
        affirmed = affirmer()
    except BaseException:
        affirmed = False
    if affirmed is not True:
        _mvp_fail(WordPressComMvpDraftFailureCode.LIVE_MUTATION_NOT_AUTHORIZED)
    state_root = _ensure_mvp_journal_roots(repository_root)
    provider = OfficialWordPressComMvpDraftAdapter(
        token_reader=WordPressComOAuthSecretStore(repository_root=repository_root),
        connection_factory=SystemWordPressComHttpsConnectionFactory(),
    )
    preview = WordPressComMvpDraftPreparationService(
        bundle=bundle,
        provider=provider,
        journal=ImmutableWordPressComMvpDraftJournal(root=state_root),
    ).prepare()
    return _mvp_preview_output("prepare-mvp-drafts", preview)


def _run_preview_mvp(repository_root: Path) -> dict[str, object]:
    _verify_mvp_runtime_identity(repository_root)
    bundle = _build_mvp_bundle(repository_root)
    provider = OfficialWordPressComMvpDraftAdapter(
        token_reader=WordPressComOAuthSecretStore(repository_root=repository_root),
        connection_factory=SystemWordPressComHttpsConnectionFactory(),
    )
    preview = WordPressComMvpDraftPreparationService(
        bundle=bundle,
        provider=provider,
        journal=_mvp_preview_journal(repository_root),
    ).preview()
    return _mvp_preview_output("preview-mvp", preview)


def _run_oauth_setup(repository_root: Path) -> dict[str, object]:
    _ensure_secret_roots(repository_root, include_state=False)
    _initialize_client_credentials(repository_root)
    store = WordPressComOAuthSecretStore(repository_root=repository_root)
    receipt = WordPressComOAuthSetup(
        store=store,
        entropy=SystemWordPressComEntropySource(),
        opener=SystemWordPressComBrowserOpener(),
        listener=SystemWordPressComLoopbackListener(),
        transport=SystemWordPressComOAuthTokenTransport(),
    ).setup()
    return {
        "access_token_alias": receipt.access_token_alias,
        "access_token_stored": receipt.access_token_stored,
        "command": "oauth-setup",
        "publication_authorized": receipt.publication_authorized,
        "scope": receipt.scope,
        "target_origin": receipt.target_origin,
    }


def _run_create_review_draft(repository_root: Path) -> dict[str, object]:
    source_values = {
        path: _read_fixed_source(repository_root, path, size, sha256)
        for path, size, sha256 in _FIXED_SOURCES
    }
    _ensure_secret_roots(repository_root, include_state=False)
    store = WordPressComOAuthSecretStore(repository_root=repository_root)
    candidate = build_bound_review_draft(
        article_bytes=source_values[_ARTICLE_PATH],
        source_packet_bytes=source_values[_SOURCE_PACKET_PATH],
        base_handoff_bytes=source_values[_BASE_HANDOFF_PATH],
        amendment_handoff_bytes=source_values[_AMENDMENT_HANDOFF_PATH],
        activation_handoff_bytes=source_values[_ACTIVATION_HANDOFF_PATH],
    )
    creator = OfficialWordPressComReviewDraftAdapter(
        token_reader=store,
        connection_factory=SystemWordPressComHttpsConnectionFactory(),
    )
    _ensure_secret_roots(repository_root, include_state=True)
    receipt = DurableWordPressComReviewDraftAdapter(
        private_root=repository_root / _STATE_ROOT,
        creator=creator,
    ).create_review_draft(candidate)
    return _receipt_output(receipt)


def _receipt_output(receipt: WordPressComReviewDraftReceipt) -> dict[str, object]:
    if type(receipt) is not WordPressComReviewDraftReceipt:
        _fail(WordPressComReviewDraftFailureCode.RECEIPT_INVALID)
    return {
        "authority": receipt.authority,
        "command": "create-review-draft",
        "content_sha256": receipt.content_sha256,
        "disposition": receipt.disposition.value,
        "draft_id": receipt.draft_id,
        "network_status": receipt.network_status,
        "operation_binding_sha256": receipt.operation_binding_sha256,
        "production_eligible": receipt.production_eligible,
        "publication_authorized": receipt.publication_authorized,
        "response_body_sha256": receipt.response_body_sha256,
        "schema": receipt.schema,
        "status": receipt.status,
        "target_origin": receipt.target_origin,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wordpresscom-review-draft",
        allow_abbrev=False,
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("oauth-setup", allow_abbrev=False)
    subcommands.add_parser("create-review-draft", allow_abbrev=False)
    subcommands.add_parser("prepare-mvp-drafts", allow_abbrev=False)
    subcommands.add_parser("preview-mvp", allow_abbrev=False)
    return parser


def _failure_output(error: WordPressComReviewDraftFailure) -> dict[str, object]:
    output: dict[str, object] = {"ok": False, "reason_code": error.code.value}
    if (
        type(error) is WordPressComOAuthCallbackFailure
        and type(error.diagnostic_code) is WordPressComOAuthCallbackDiagnosticCode
    ):
        output["diagnostic_code"] = error.diagnostic_code.value
    elif (
        type(error) is WordPressComOAuthTokenFailure
        and type(error.diagnostic_code) is WordPressComOAuthTokenDiagnosticCode
    ):
        output["diagnostic_code"] = error.diagnostic_code.value
    if error.code is WordPressComReviewDraftFailureCode.OAUTH_SECRET_STORE_INVALID:
        output.update(
            {
                "manual_action": "REGISTER_APPLICATION_AND_CREATE_PRIVATE_CLIENT_FILES",
                "registration_url": _APPLICATION_REGISTRATION_URL,
                "redirect_uri": WORDPRESSCOM_OAUTH_REDIRECT_URI,
                "scope": WORDPRESSCOM_OAUTH_SCOPE,
                "target_origin": WORDPRESSCOM_REVIEW_DRAFT_TARGET,
            }
        )
    return output


def _mvp_failure_output(error: WordPressComMvpDraftFailure) -> dict[str, object]:
    return {"ok": False, "reason_code": error.code.value}


def main(
    argv: list[str] | None = None,
    *,
    repository_root: Path = REPOSITORY_ROOT,
    oauth_runner: Callable[[Path], dict[str, object]] = _run_oauth_setup,
    create_runner: Callable[[Path], dict[str, object]] = _run_create_review_draft,
    prepare_runner: Callable[[Path], dict[str, object]] = _run_prepare_mvp_drafts,
    preview_runner: Callable[[Path], dict[str, object]] = _run_preview_mvp,
) -> int:
    os.umask(0o077)
    try:
        root = _physical_repository_root(repository_root)
        arguments = _parser().parse_args(argv)
        runners = {
            "oauth-setup": oauth_runner,
            "create-review-draft": create_runner,
            "prepare-mvp-drafts": prepare_runner,
            "preview-mvp": preview_runner,
        }
        output = runners[arguments.command](root)
        rendered = {"ok": True, **output}
        print(
            json.dumps(
                rendered,
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except WordPressComReviewDraftFailure as error:
        print(
            json.dumps(
                _failure_output(error),
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2
    except WordPressComMvpDraftFailure as error:
        print(
            json.dumps(
                _mvp_failure_output(error),
                ensure_ascii=True,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
