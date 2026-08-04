#!/usr/bin/env python3
"""Deterministically scan maintained files and fetched Git blobs for secrets.

The command deliberately has no allowlist: a maintained input that cannot be
read and inspected safely is an operational failure.  Findings contain only a
rule identifier and source location; matched bytes are never rendered.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import unicodedata
import zipfile


REPOSITORY_ROOT = Path(__file__).resolve(strict=True).parents[1]

READ_CHUNK_BYTES = 1024 * 1024
MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 4096
MAX_ARCHIVE_DEPTH = 4
MAX_COMPRESSION_RATIO = 200
COMPRESSION_RATIO_MINIMUM_BYTES = 1024 * 1024
GIT_TIMEOUT_SECONDS = 60

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_OPERATIONAL_ERROR = 2

RULE_AWS_ACCESS_KEY = "AWS_ACCESS_KEY_ID"
RULE_GITHUB_TOKEN = "GITHUB_TOKEN"
RULE_OPENAI_API_KEY = "OPENAI_API_KEY"
RULE_PRIVATE_KEY = "PRIVATE_KEY"
RULE_GENERIC_CREDENTIAL = "GENERIC_CREDENTIAL"

SPECIFIC_RULES = (
    (
        RULE_AWS_ACCESS_KEY,
        re.compile(rb"(?<![A-Z0-9])(?:AKIA|ASIA)[A-Z0-9]{16}(?![A-Z0-9])"),
    ),
    (
        RULE_GITHUB_TOKEN,
        re.compile(
            rb"(?<![A-Za-z0-9_])(?:gh[pousr]_[A-Za-z0-9]{36,255}"
            rb"|github_pat_[A-Za-z0-9_]{20,255})(?![A-Za-z0-9_])"
        ),
    ),
    (
        RULE_OPENAI_API_KEY,
        re.compile(
            rb"(?<![A-Za-z0-9_-])sk-(?:proj-|svcacct-)?"
            rb"[A-Za-z0-9_-]{20,255}(?![A-Za-z0-9_-])"
        ),
    ),
    (
        RULE_PRIVATE_KEY,
        re.compile(
            rb"-----BEGIN (?:RSA |DSA |EC |OPENSSH |ENCRYPTED )?"
            rb"PRIVATE KEY-----"
        ),
    ),
)

GENERIC_ASSIGNMENT = re.compile(
    rb"(?ix)"
    rb"(?<![A-Za-z0-9_])['\"]?"
    rb"(?:api[_-]?key|access[_-]?(?:key|token)|auth[_-]?token|"
    rb"client[_-]?secret|password|passwd|pwd|secret|token)"
    rb"['\"]?[ \t]*(?::|=)[ \t]*"
    rb"(?:"
    rb"\"(?P<double>[^\"\r\n]{8,512})\"|"
    rb"'(?P<single>[^'\r\n]{8,512})'|"
    rb"(?P<bare>[^\s,;#{}\[\]]{8,512})"
    rb")"
)

GENERIC_PLACEHOLDER = re.compile(
    rb"(?:"
    rb"change[-_]?me|changeme|do[-_]?not[-_]?read|dummy|example|fake|"
    rb"fixture|forbidden|masked|not[-_]?a[-_]?(?:real[-_]?)?secret|"
    rb"placeholder|redacted|replace[-_]?me|sample|test[-_]?token|"
    rb"your[-_]?(?:key|password|secret|token)"
    rb")"
    rb"(?:[-_.](?:"
    rb"access|api|auth|client|credential|credentials|deployment|dev|"
    rb"development|env|environment|example|fixture|for|here|in|key|"
    rb"local|only|password|placeholder|production|pwd|required|sample|"
    rb"secret|staging|test|tests|token|use|value"
    rb"))*"
)

SAFE_BARE_SOURCE_EXPRESSIONS = frozenset(
    {
        b'content.decode("utf-8")',
        b"_read_password_file(target.password_file)",
    }
)

EXCLUDED_DIRECTORY_NAMES = frozenset(
    {
        ".cache",
        ".git",
        ".idea",
        ".mypy_cache",
        ".next",
        ".node-offline-check",
        ".npm-cache",
        ".nox",
        ".pytest_cache",
        ".ruff_cache",
        ".secrets",
        ".tox",
        ".venv",
        ".venv-offline-check",
        ".vscode",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "htmlcov",
        "node_modules",
        "venv",
    }
)

EXCLUDED_FILE_NAMES = frozenset(
    {
        ".coverage",
        ".DS_Store",
        "Thumbs.db",
        "coverage.xml",
        "settings.local.json",
    }
)

ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
ZIP_SUFFIXES = (".zip", ".jar", ".whl", ".docx", ".xlsx", ".pptx")
HEX_OBJECT_ID = re.compile(rb"[0-9a-f]{40}(?:[0-9a-f]{24})?")
ARCHIVE_READ_ERRORS = (
    EOFError,
    NotImplementedError,
    OSError,
    RuntimeError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
)
GIT_EXECUTION_ERRORS = (OSError, subprocess.TimeoutExpired)


@dataclass(frozen=True, order=True)
class Finding:
    """A sanitized secret finding."""

    source: str
    line: int
    rule_id: str


@dataclass
class ArchiveBudget:
    """Expansion limits shared by one outer archive and all nested archives."""

    members: int = 0
    expanded_bytes: int = 0


class ScanError(RuntimeError):
    """An unsafe or unreadable input, represented without attacker data."""

    def __init__(self, code: str, source: str) -> None:
        super().__init__(code)
        self.code = code
        self.source = source


def _line_number(data: bytes, offset: int) -> int:
    return data.count(b"\n", 0, offset) + 1


def _overlaps(span: tuple[int, int], other: tuple[int, int]) -> bool:
    return span[0] < other[1] and other[0] < span[1]


def _generic_value(
    match: re.Match[bytes],
) -> tuple[str, bytes, tuple[int, int]]:
    for group in ("double", "single", "bare"):
        value = match.group(group)
        if value is not None:
            return group, value, match.span(group)
    raise AssertionError("generic credential expression has no value")


def _looks_like_real_generic_credential(value: bytes, *, kind: str) -> bool:
    candidate = value.strip()
    if len(candidate) < 12:
        return False
    if kind == "bare" and candidate in SAFE_BARE_SOURCE_EXPRESSIONS:
        return False
    lowered = candidate.lower()
    if GENERIC_PLACEHOLDER.fullmatch(lowered) is not None:
        return False
    if lowered in {b"none", b"null", b"undefined", b"required"}:
        return False
    if lowered.startswith((b"$", b"%", b"<", b"{{", b"http://", b"https://")):
        return False
    if any(
        marker in lowered
        for marker in (
            b"getenv(",
            b"match.group(",
            b"os.environ",
            b"process.env",
            b".removeprefix(",
            b".replace(",
            b"secret_name",
            b"secretref",
        )
    ):
        return False
    return len(set(candidate)) >= 6


def scan_bytes(data: bytes, source: str) -> set[Finding]:
    """Return sanitized findings from one non-archive byte sequence."""

    findings: set[Finding] = set()
    specific_spans: list[tuple[int, int]] = []
    for rule_id, pattern in SPECIFIC_RULES:
        for match in pattern.finditer(data):
            specific_spans.append(match.span())
            findings.add(
                Finding(
                    source=source,
                    line=_line_number(data, match.start()),
                    rule_id=rule_id,
                )
            )

    for match in GENERIC_ASSIGNMENT.finditer(data):
        value_kind, value, value_span = _generic_value(match)
        if any(_overlaps(value_span, span) for span in specific_spans):
            continue
        if not _looks_like_real_generic_credential(value, kind=value_kind):
            continue
        findings.add(
            Finding(
                source=source,
                line=_line_number(data, match.start()),
                rule_id=RULE_GENERIC_CREDENTIAL,
            )
        )
    return findings


def _archive_candidate(data: bytes, path_hint: str) -> bool:
    return data.startswith(ZIP_SIGNATURES) or path_hint.casefold().endswith(
        ZIP_SUFFIXES
    )


def _validated_archive_member(
    info: zipfile.ZipInfo,
    source: str,
) -> PurePosixPath | None:
    original = info.orig_filename
    if "\x00" in original or "\\" in original:
        raise ScanError("unsafe-archive-member", source)
    raw_parts = original.split("/")
    if any(part in {"", ".", ".."} for part in raw_parts[:-1]):
        raise ScanError("unsafe-archive-member", source)

    member = PurePosixPath(original)
    if member.is_absolute() or ".." in member.parts:
        raise ScanError("unsafe-archive-member", source)
    if member.parts and member.parts[0].endswith(":"):
        raise ScanError("unsafe-archive-member", source)
    if not member.parts:
        raise ScanError("unsafe-archive-member", source)

    if info.flag_bits & (0x1 | 0x40):
        raise ScanError("encrypted-archive-member", source)

    if info.create_system == 3:
        file_type = stat.S_IFMT(info.external_attr >> 16)
        allowed_type = stat.S_IFDIR if info.is_dir() else stat.S_IFREG
        if file_type not in {0, allowed_type}:
            raise ScanError("unsafe-archive-member-type", source)

    if info.is_dir():
        return None
    if original.endswith("/"):
        raise ScanError("unsafe-archive-member", source)
    return member


def _read_archive_member(
    archive: zipfile.ZipFile,
    info: zipfile.ZipInfo,
    source: str,
) -> bytes:
    chunks: list[bytes] = []
    size = 0
    try:
        with archive.open(info, "r") as stream:
            while chunk := stream.read(READ_CHUNK_BYTES):
                size += len(chunk)
                if size > info.file_size or size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ScanError("archive-member-expanded-too-large", source)
                chunks.append(chunk)
    except ScanError:
        raise
    except ARCHIVE_READ_ERRORS:
        raise ScanError("unreadable-archive-member", source) from None
    if size != info.file_size:
        raise ScanError("archive-member-size-mismatch", source)
    return b"".join(chunks)


def scan_archive(
    data: bytes,
    source: str,
    *,
    depth: int,
    budget: ArchiveBudget,
) -> set[Finding]:
    """Scan a ZIP and nested ZIPs while enforcing one shared expansion budget."""

    if depth > MAX_ARCHIVE_DEPTH:
        raise ScanError("archive-nesting-too-deep", source)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except ARCHIVE_READ_ERRORS:
        raise ScanError("invalid-archive", source) from None

    findings: set[Finding] = set()
    seen_paths: set[str] = set()
    normalized_paths: set[str] = set()
    try:
        with archive:
            validated: list[tuple[PurePosixPath, zipfile.ZipInfo]] = []
            for info in archive.infolist():
                member = _validated_archive_member(info, source)
                if member is None:
                    continue
                member_name = member.as_posix()
                normalized = unicodedata.normalize("NFC", member_name).casefold()
                if member_name in seen_paths or normalized in normalized_paths:
                    raise ScanError("duplicate-archive-member", source)
                seen_paths.add(member_name)
                normalized_paths.add(normalized)

                budget.members += 1
                budget.expanded_bytes += info.file_size
                if budget.members > MAX_ARCHIVE_MEMBERS:
                    raise ScanError("archive-member-limit", source)
                if info.file_size > MAX_ARCHIVE_MEMBER_BYTES:
                    raise ScanError("archive-member-too-large", source)
                if budget.expanded_bytes > MAX_ARCHIVE_EXPANDED_BYTES:
                    raise ScanError("archive-expansion-limit", source)
                if (
                    info.file_size >= COMPRESSION_RATIO_MINIMUM_BYTES
                    and info.file_size / max(info.compress_size, 1)
                    > MAX_COMPRESSION_RATIO
                ):
                    raise ScanError("archive-compression-ratio", source)
                validated.append((member, info))

            for member, info in sorted(
                validated,
                key=lambda item: item[0].as_posix().encode("utf-8", "surrogatepass"),
            ):
                member_source = f"{source}!{member.as_posix()}"
                member_data = _read_archive_member(archive, info, member_source)
                if _archive_candidate(member_data, member.as_posix()):
                    if depth >= MAX_ARCHIVE_DEPTH:
                        raise ScanError("archive-nesting-too-deep", member_source)
                    findings.update(
                        scan_archive(
                            member_data,
                            member_source,
                            depth=depth + 1,
                            budget=budget,
                        )
                    )
                else:
                    findings.update(scan_bytes(member_data, member_source))
    except ScanError:
        raise
    except ARCHIVE_READ_ERRORS:
        raise ScanError("invalid-archive", source) from None
    return findings


def scan_payload(data: bytes, source: str, path_hint: str) -> set[Finding]:
    if _archive_candidate(data, path_hint):
        return scan_archive(data, source, depth=1, budget=ArchiveBudget())
    return scan_bytes(data, source)


def _directory_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_open_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _validated_relative_parts(relative: str, source: str) -> tuple[str, ...]:
    if not relative or relative.startswith("/") or "\x00" in relative:
        raise ScanError("unsafe-worktree-path", source)
    parts = tuple(relative.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise ScanError("unsafe-worktree-path", source)
    return parts


def read_maintained_file(root: Path, relative: str) -> bytes:
    """Read a regular file descriptor-relatively without following symlinks."""

    source = relative
    parts = _validated_relative_parts(relative, source)
    descriptors: list[int] = []
    try:
        root_fd = os.open(os.fspath(root), _directory_open_flags())
        descriptors.append(root_fd)
        parent_fd = root_fd
        for part in parts[:-1]:
            next_fd = os.open(part, _directory_open_flags(), dir_fd=parent_fd)
            descriptors.append(next_fd)
            parent_fd = next_fd
        file_fd = os.open(parts[-1], _file_open_flags(), dir_fd=parent_fd)
        descriptors.append(file_fd)
        before = os.fstat(file_fd)
        if not stat.S_ISREG(before.st_mode):
            raise ScanError("unsafe-worktree-file-type", source)
        if before.st_size < 0 or before.st_size > MAX_INPUT_BYTES:
            raise ScanError("worktree-file-too-large", source)

        chunks: list[bytes] = []
        size = 0
        while chunk := os.read(file_fd, READ_CHUNK_BYTES):
            size += len(chunk)
            if size > MAX_INPUT_BYTES:
                raise ScanError("worktree-file-too-large", source)
            chunks.append(chunk)
        after = os.fstat(file_fd)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        )
        if identity_before != identity_after or size != before.st_size:
            raise ScanError("worktree-file-changed", source)
        return b"".join(chunks)
    except ScanError:
        raise
    except OSError:
        raise ScanError("unreadable-worktree-input", source) from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _is_fallback_excluded(parts: tuple[str, ...], is_directory: bool) -> bool:
    name = parts[-1]
    if is_directory:
        if name in EXCLUDED_DIRECTORY_NAMES:
            return True
        if name.startswith(".node-offline-check."):
            return True
        return False

    if name in EXCLUDED_FILE_NAMES:
        return True
    if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
        return True
    if name.endswith((".log", ".pyc", ".swp", ".tmp", "~")):
        return True
    return parts == (".claude", "settings.local.json")


def _walk_fallback_directory(
    directory_fd: int,
    parts: tuple[str, ...],
    files: list[str],
) -> None:
    try:
        with os.scandir(directory_fd) as iterator:
            entries = sorted(iterator, key=lambda entry: os.fsencode(entry.name))
    except OSError:
        source = "/".join(parts) or "."
        raise ScanError("unreadable-worktree-directory", source) from None

    for entry in entries:
        child_parts = (*parts, entry.name)
        try:
            metadata = entry.stat(follow_symlinks=False)
        except OSError:
            raise ScanError(
                "unreadable-worktree-input", "/".join(child_parts)
            ) from None
        mode = metadata.st_mode
        is_directory = stat.S_ISDIR(mode)
        if _is_fallback_excluded(child_parts, is_directory):
            continue
        if stat.S_ISLNK(mode):
            raise ScanError("unsafe-worktree-symlink", "/".join(child_parts))
        if is_directory:
            try:
                child_fd = os.open(
                    entry.name,
                    _directory_open_flags(),
                    dir_fd=directory_fd,
                )
            except OSError:
                raise ScanError(
                    "unreadable-worktree-directory", "/".join(child_parts)
                ) from None
            try:
                _walk_fallback_directory(child_fd, child_parts, files)
            finally:
                os.close(child_fd)
        elif stat.S_ISREG(mode):
            files.append("/".join(child_parts))
        else:
            raise ScanError("unsafe-worktree-file-type", "/".join(child_parts))


def fallback_worktree_files(root: Path) -> list[str]:
    descriptors: list[int] = []
    try:
        root_fd = os.open(os.fspath(root), _directory_open_flags())
        descriptors.append(root_fd)
        root_stat = os.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ScanError("invalid-repository-root", ".")
        files: list[str] = []
        _walk_fallback_directory(root_fd, (), files)
        return sorted(set(files), key=os.fsencode)
    except ScanError:
        raise
    except OSError:
        raise ScanError("invalid-repository-root", ".") from None
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _git_executable() -> str | None:
    for candidate in ("/usr/bin/git", "/bin/git"):
        try:
            metadata = os.stat(candidate, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISREG(metadata.st_mode) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _git_environment() -> dict[str, str]:
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": "/usr/bin:/bin",
    }


def _run_git(
    root: Path,
    arguments: list[str],
    *,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    executable = _git_executable()
    if executable is None:
        raise ScanError("git-unavailable", ".")
    try:
        return subprocess.run(
            [executable, "-c", "core.quotePath=true", *arguments],
            cwd=root,
            env=_git_environment(),
            input=input_bytes,
            stdin=subprocess.DEVNULL if input_bytes is None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except GIT_EXECUTION_ERRORS:
        raise ScanError("git-command-failed", ".") from None


def _empty_git_marker(root: Path) -> bool:
    marker = root / ".git"
    try:
        metadata = marker.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        return False
    if not stat.S_ISDIR(metadata.st_mode):
        return False
    try:
        return next(marker.iterdir(), None) is None
    except OSError:
        return False


def git_repository_available(root: Path) -> bool:
    executable = _git_executable()
    if executable is None:
        if _empty_git_marker(root):
            return False
        raise ScanError("git-unavailable", ".")
    marker = root / ".git"
    try:
        marker_metadata = marker.lstat()
    except FileNotFoundError:
        marker_metadata = None
    except OSError:
        raise ScanError("unsafe-git-metadata", ".") from None
    if marker_metadata is not None and not stat.S_ISDIR(marker_metadata.st_mode):
        raise ScanError("unsafe-git-metadata", ".")
    result = _run_git(root, ["rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        if _empty_git_marker(root):
            return False
        raise ScanError("invalid-git-repository", ".")
    try:
        reported = Path(os.fsdecode(result.stdout.strip()))
        if not reported.is_absolute() or not os.path.samefile(root, reported):
            raise ScanError("git-root-mismatch", ".")
    except OSError:
        raise ScanError("git-root-mismatch", ".") from None
    return True


def git_worktree_files(root: Path) -> list[str]:
    result = _run_git(
        root,
        ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"],
    )
    if result.returncode != 0 or not result.stdout.endswith(b"\x00") and result.stdout:
        raise ScanError("git-worktree-enumeration-failed", ".")
    paths: set[str] = set()
    for raw_path in result.stdout.split(b"\x00"):
        if not raw_path:
            continue
        if raw_path.startswith(b"/") or b"\x00" in raw_path:
            raise ScanError("unsafe-git-path", ".")
        raw_parts = raw_path.split(b"/")
        if any(part in {b"", b".", b".."} for part in raw_parts):
            raise ScanError("unsafe-git-path", ".")
        relative = os.fsdecode(raw_path)
        _validated_relative_parts(relative, relative)
        paths.add(relative)
    return sorted(paths, key=os.fsencode)


def worktree_files(root: Path) -> list[str]:
    if git_repository_available(root):
        return git_worktree_files(root)
    return fallback_worktree_files(root)


def scan_worktree(root: Path) -> set[Finding]:
    findings: set[Finding] = set()
    for relative in worktree_files(root):
        data = read_maintained_file(root, relative)
        findings.update(scan_payload(data, relative, relative))
    return findings


def _require_complete_git_repository(root: Path) -> None:
    if not git_repository_available(root):
        raise ScanError("git-history-requires-repository", ".")
    shallow = _run_git(root, ["rev-parse", "--is-shallow-repository"])
    if shallow.returncode != 0 or shallow.stdout.strip() not in {b"true", b"false"}:
        raise ScanError("git-shallow-check-failed", ".")
    if shallow.stdout.strip() != b"false":
        raise ScanError("shallow-git-history", ".")


def git_blob_inventory(root: Path) -> list[tuple[bytes, int]]:
    """Enumerate every blob physically available from the local object database."""

    result = _run_git(
        root,
        [
            "cat-file",
            "--batch-all-objects",
            "--unordered",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ],
    )
    if result.returncode != 0:
        raise ScanError("git-object-enumeration-failed", ".")

    blobs: dict[bytes, int] = {}
    for line in result.stdout.splitlines():
        fields = line.split(b" ")
        if len(fields) != 3 or HEX_OBJECT_ID.fullmatch(fields[0]) is None:
            raise ScanError("invalid-git-object-metadata", ".")
        object_id, object_type, raw_size = fields
        try:
            object_size = int(raw_size)
        except ValueError:
            raise ScanError("invalid-git-object-metadata", ".") from None
        if object_size < 0:
            raise ScanError("invalid-git-object-metadata", ".")
        if object_type != b"blob":
            continue
        if object_size > MAX_INPUT_BYTES:
            raise ScanError(
                "git-blob-too-large", f"git-blob:{object_id.decode('ascii')}"
            )
        previous = blobs.setdefault(object_id, object_size)
        if previous != object_size:
            raise ScanError("invalid-git-object-metadata", ".")
    return sorted(blobs.items())


def _read_exact(stream: object, size: int, source: str) -> bytes:
    reader = getattr(stream, "read")
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = reader(min(remaining, READ_CHUNK_BYTES))
        if not chunk:
            raise ScanError("truncated-git-object", source)
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def scan_git_history(root: Path) -> set[Finding]:
    _require_complete_git_repository(root)
    inventory = git_blob_inventory(root)
    if not inventory:
        return set()

    executable = _git_executable()
    if executable is None:
        raise ScanError("git-unavailable", ".")
    try:
        process = subprocess.Popen(
            [executable, "cat-file", "--batch"],
            cwd=root,
            env=_git_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise ScanError("git-object-reader-failed", ".") from None

    findings: set[Finding] = set()
    try:
        if process.stdin is None or process.stdout is None:
            raise ScanError("git-object-reader-failed", ".")
        for object_id, expected_size in inventory:
            source = f"git-blob:{object_id.decode('ascii')}"
            try:
                process.stdin.write(object_id + b"\n")
                process.stdin.flush()
                header = process.stdout.readline()
            except OSError:
                raise ScanError("git-object-reader-failed", source) from None
            fields = header.rstrip(b"\n").split(b" ")
            if len(fields) != 3 or fields[0] != object_id or fields[1] != b"blob":
                raise ScanError("invalid-git-object-response", source)
            try:
                actual_size = int(fields[2])
            except ValueError:
                raise ScanError("invalid-git-object-response", source) from None
            if actual_size != expected_size:
                raise ScanError("invalid-git-object-response", source)
            data = _read_exact(process.stdout, actual_size, source)
            if process.stdout.read(1) != b"\n":
                raise ScanError("invalid-git-object-response", source)
            findings.update(scan_payload(data, source, source))

        process.stdin.close()
        try:
            return_code = process.wait(timeout=GIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise ScanError("git-object-reader-timeout", ".") from None
        if return_code != 0:
            raise ScanError("git-object-reader-failed", ".")
    except ScanError:
        process.kill()
        process.wait()
        raise
    finally:
        if process.stdin is not None and not process.stdin.closed:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()
    return findings


def _render_source(source: str) -> str:
    return json.dumps(source, ensure_ascii=True)


def emit_findings(findings: set[Finding]) -> None:
    for finding in sorted(findings):
        print(
            f"FINDING rule={finding.rule_id} "
            f"source={_render_source(finding.source)} line={finding.line}"
        )


def emit_error(error: ScanError) -> None:
    print(
        f"ERROR code={error.code} source={_render_source(error.source)}",
        file=sys.stderr,
    )


def parse_arguments(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan maintained worktree files and fetched Git history."
    )
    parser.add_argument(
        "--worktree",
        action="store_true",
        help="scan tracked and nonignored untracked maintained files",
    )
    parser.add_argument(
        "--git-history",
        action="store_true",
        help="scan every blob in a complete, non-shallow local Git object database",
    )
    arguments = parser.parse_args(argv)
    if not arguments.worktree and not arguments.git_history:
        parser.error("at least one of --worktree or --git-history is required")
    return arguments


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    findings: set[Finding] = set()
    try:
        if arguments.worktree:
            findings.update(scan_worktree(REPOSITORY_ROOT))
        if arguments.git_history:
            findings.update(scan_git_history(REPOSITORY_ROOT))
    except ScanError as error:
        emit_error(error)
        return EXIT_OPERATIONAL_ERROR
    except Exception:
        emit_error(ScanError("internal-scanner-error", "."))
        return EXIT_OPERATIONAL_ERROR

    emit_findings(findings)
    return EXIT_FINDINGS if findings else EXIT_CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
