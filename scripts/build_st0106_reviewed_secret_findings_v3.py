#!/usr/bin/env python3
"""Build the additive, exact-reviewed ST-0106 V3 findings ledger."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import selectors
import stat
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if os.fspath(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, os.fspath(REPOSITORY_ROOT))

from scripts.scan_secrets import (  # noqa: E402
    Finding,
    GIT_TIMEOUT_SECONDS,
    RULE_GENERIC_CREDENTIAL,
    _git_environment as scanner_git_environment,
    _git_executable as scanner_git_executable,
    parse_reviewed_findings,
    scan_bytes,
)


SOURCE_PATH: Final = Path(
    "changes/st-0106/contracts/reviewed-secret-findings.v3-additions.json"
)
PARENT_LEDGER_PATH: Final = Path(
    "changes/st-0106/contracts/reviewed-secret-findings.v2.yaml"
)
OUTPUT_PATH: Final = Path("changes/st-0106/contracts/reviewed-secret-findings.v3.yaml")
CURRENT_OPERATOR_PATH: Final = Path("scripts/github_ruleset_operator.py")
GENERATION_COMMAND: Final = (
    "uv run --locked --no-sync python "
    "scripts/build_st0106_reviewed_secret_findings_v3.py"
)
EXPECTED_PARENT_BYTES: Final = 59_769
EXPECTED_PARENT_SHA256: Final = (
    "667fee6720dad2e25e71220b2ec2fc8918a845ee30309c581f687ca87f51ca1b"
)
EXPECTED_PARENT_ENTRIES: Final = 115
EXPECTED_NEW_ENTRIES: Final = 3
MAX_INPUT_BYTES: Final = 2 * 1024 * 1024
READ_CHUNK_BYTES: Final = 64 * 1024
MAX_GIT_HEADER_BYTES: Final = 256
TEMPORARY_ATTEMPTS: Final = 32
PROCESS_REAP_TIMEOUT_SECONDS: Final = 5.0
NONBLOCKING_READ_RETRY_ERRORS: Final = (BlockingIOError, InterruptedError)
GIT_READER_ERRORS: Final = (OSError, RuntimeError, ValueError)
PIPE_CLOSE_ERRORS: Final = (OSError, ValueError)
OBJECT_ID: Final = re.compile(r"^[0-9a-f]{40}$")
SHA256: Final = re.compile(r"^[0-9a-f]{64}$")
EXPECTED_DOCUMENT: Final = {
    "id": "RAOS-ST0106-REVIEWED-SECRET-FINDINGS-V3-ADDITIONS",
    "version": "1.0.0",
    "story_id": "ST-0106",
    "status": "LOCAL_EXACT_REVIEW_CANDIDATE",
    "parent_ledger": {
        "uri": "repo://changes/st-0106/contracts/reviewed-secret-findings.v2.yaml",
        "bytes": EXPECTED_PARENT_BYTES,
        "sha256": EXPECTED_PARENT_SHA256,
        "entry_count": EXPECTED_PARENT_ENTRIES,
    },
}
EXPECTED_REVIEW: Final = {
    "rule_id": RULE_GENERIC_CREDENTIAL,
    "classification": "REVIEWED_FALSE_POSITIVE",
    "rationale": "Sanitized source location reviewed; no live credential is present.",
    "method": "HASH_BOUND_PYTHON_AST_ASSIGNMENT_CALL_WITHOUT_STRING_LITERALS",
    "matched_values_extracted": False,
    "matched_values_printed": False,
    "matched_values_persisted": False,
    "specific_rule_suppression": "FORBIDDEN",
}
ENTRY_KEYS: Final = {
    "scope",
    "exact_source_identifier",
    "exact_line_number",
    "exact_source_bytes",
    "exact_source_sha256",
    "exact_line_sha256",
    "path_hint",
    "expected_ast",
}
EXPECTED_AST: Final = {
    "node": "Assign",
    "target": "token",
    "call": "read_token_from_environment",
    "string_literal_count": 0,
}


class DuplicateKeyError(ValueError):
    """A strict JSON object repeated a key."""


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError(key)
        result[key] = value
    return result


def _directory_flags() -> int:
    if not getattr(os, "O_DIRECTORY", 0) or not getattr(os, "O_NOFOLLOW", 0):
        raise RuntimeError("descriptor-bound filesystem support is unavailable")
    return os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | os.O_DIRECTORY | os.O_NOFOLLOW


def _open_root_descriptor(root: Path) -> int:
    try:
        before = os.stat(root, follow_symlinks=False)
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
            raise RuntimeError("repository root must be a non-symlink directory")
        descriptor = os.open(os.fspath(root), _directory_flags())
    except OSError as exc:
        raise RuntimeError("repository root must be a non-symlink directory") from exc
    after = os.fstat(descriptor)
    if not stat.S_ISDIR(after.st_mode) or (before.st_dev, before.st_ino) != (
        after.st_dev,
        after.st_ino,
    ):
        os.close(descriptor)
        raise RuntimeError("repository root must be a non-symlink directory")
    return descriptor


def _open_directory_descriptor(root_descriptor: int, relative: Path, label: str) -> int:
    current = os.dup(root_descriptor)
    try:
        for component in relative.parts:
            if component in {"", ".", ".."}:
                raise RuntimeError(f"unsafe {label} parent")
            try:
                before = os.stat(component, dir_fd=current, follow_symlinks=False)
                if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
                    raise RuntimeError(
                        f"{label} parent must contain only non-symlink directories"
                    )
                following = os.open(component, _directory_flags(), dir_fd=current)
            except OSError as exc:
                raise RuntimeError(
                    f"{label} parent must contain only non-symlink directories"
                ) from exc
            after = os.fstat(following)
            if not stat.S_ISDIR(after.st_mode) or (before.st_dev, before.st_ino) != (
                after.st_dev,
                after.st_ino,
            ):
                os.close(following)
                raise RuntimeError(f"{label} parent changed during traversal")
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


def _descriptor_identity(descriptor: int) -> tuple[int, int]:
    metadata = os.fstat(descriptor)
    return metadata.st_dev, metadata.st_ino


def _stable_file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _assert_root_identity(root: Path, expected: tuple[int, int]) -> None:
    try:
        metadata = os.stat(root, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError("repository root changed during operation") from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or (metadata.st_dev, metadata.st_ino) != expected
    ):
        raise RuntimeError("repository root changed during operation")


def _assert_directory_identity(
    root_descriptor: int,
    relative: Path,
    expected: tuple[int, int],
    label: str,
) -> None:
    current = _open_directory_descriptor(root_descriptor, relative, label)
    try:
        if _descriptor_identity(current) != expected:
            raise RuntimeError(f"{label} parent changed during operation")
    finally:
        os.close(current)


def _read_exact_descriptor(descriptor: int, size: int, label: str) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = os.read(descriptor, min(READ_CHUNK_BYTES, remaining))
        if not chunk:
            raise RuntimeError(f"{label} was truncated while being read")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _regular_file(root: Path, relative: Path, label: str) -> bytes:
    if relative.is_absolute() or any(
        part in {"", ".", ".."} for part in relative.parts
    ):
        raise RuntimeError(f"unsafe {label} path")
    root_descriptor = _open_root_descriptor(root)
    parent_descriptor = -1
    descriptor = -1
    try:
        root_identity = _descriptor_identity(root_descriptor)
        parent_descriptor = _open_directory_descriptor(
            root_descriptor, relative.parent, label
        )
        parent_identity = _descriptor_identity(parent_descriptor)
        try:
            path_before = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
            if stat.S_ISLNK(path_before.st_mode) or not stat.S_ISREG(
                path_before.st_mode
            ):
                raise RuntimeError(f"{label} must be a regular non-symlink file")
            descriptor = os.open(
                relative.name,
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NONBLOCK", 0)
                | os.O_NOFOLLOW,
                dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise RuntimeError(f"{label} must be a regular non-symlink file") from exc
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or _stable_file_identity(path_before) != _stable_file_identity(before)
            or before.st_size < 1
            or before.st_size > MAX_INPUT_BYTES
        ):
            raise RuntimeError(f"{label} size or type is invalid")
        content = _read_exact_descriptor(descriptor, before.st_size, label)
        if os.read(descriptor, 1):
            raise RuntimeError(f"{label} grew while being read")
        after = os.fstat(descriptor)
        if _stable_file_identity(before) != _stable_file_identity(after):
            raise RuntimeError(f"{label} changed while being read")
        try:
            named = os.stat(
                relative.name,
                dir_fd=parent_descriptor,
                follow_symlinks=False,
            )
        except OSError as exc:
            raise RuntimeError(f"{label} changed while being read") from exc
        if not stat.S_ISREG(named.st_mode) or _stable_file_identity(
            named
        ) != _stable_file_identity(after):
            raise RuntimeError(f"{label} changed while being read")
        _assert_directory_identity(
            root_descriptor, relative.parent, parent_identity, label
        )
        _assert_root_identity(root, root_identity)
        return content
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        os.close(root_descriptor)


def _strict_json(data: bytes, label: str) -> dict[str, Any]:
    try:
        parsed = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (DuplicateKeyError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"{label} is not strict UTF-8 JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError(f"{label} must be an object")
    return parsed


def _physical_line(data: bytes, line_number: int) -> bytes:
    lines = data.split(b"\n")
    if line_number < 1 or line_number > len(lines):
        raise RuntimeError("reviewed line is outside its source")
    selected = lines[line_number - 1]
    if line_number < len(lines):
        selected += b"\n"
    return selected


def _trusted_git_command(*arguments: str) -> list[str]:
    executable = scanner_git_executable()
    if executable is None:
        raise RuntimeError("trusted Git executable is unavailable")
    return [executable, "-c", "core.quotePath=true", *arguments]


def _git_blob_metadata(root: Path, object_id: str) -> int:
    try:
        result = subprocess.run(
            _trusted_git_command(
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
            ),
            cwd=root,
            env=scanner_git_environment(),
            input=object_id.encode("ascii") + b"\n",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("reviewed Git object metadata check failed") from exc
    fields = result.stdout.strip().split(b" ")
    if (
        result.returncode != 0
        or len(fields) != 3
        or fields[0] != object_id.encode("ascii")
        or fields[1] != b"blob"
    ):
        raise RuntimeError("reviewed Git object is unavailable or not a blob")
    try:
        size = int(fields[2])
    except ValueError as exc:
        raise RuntimeError("reviewed Git object metadata is invalid") from exc
    if size < 1 or size > MAX_INPUT_BYTES:
        raise RuntimeError("reviewed Git blob exceeds the bounded input size")
    return size


def _parse_git_batch_blob(response: bytes, object_id: str, expected_size: int) -> bytes:
    expected_header = f"{object_id} blob {expected_size}\n".encode("ascii")
    if len(expected_header) > MAX_GIT_HEADER_BYTES:
        raise RuntimeError("reviewed Git blob response header is oversized")
    if len(response) < len(expected_header):
        if expected_header.startswith(response):
            raise RuntimeError("reviewed Git blob response is truncated")
        raise RuntimeError("reviewed Git blob response header differs")
    if response[: len(expected_header)] != expected_header:
        raise RuntimeError("reviewed Git blob response header differs")
    payload = response[len(expected_header) :]
    if len(payload) < expected_size:
        raise RuntimeError("reviewed Git blob response is truncated")
    content = payload[:expected_size]
    suffix = payload[expected_size:]
    if not suffix or suffix[:1] != b"\n":
        raise RuntimeError("reviewed Git blob response delimiter differs")
    if len(suffix) != 1:
        raise RuntimeError("reviewed Git blob response has trailing data")
    return content


def _remaining_git_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise RuntimeError("reviewed Git blob reader timed out")
    return remaining


def _read_git_response(stream: Any, maximum_size: int, deadline: float) -> bytes:
    descriptor = stream.fileno()
    os.set_blocking(descriptor, False)
    response = bytearray()
    selector = selectors.DefaultSelector()
    try:
        selector.register(descriptor, selectors.EVENT_READ)
        while True:
            events = selector.select(_remaining_git_time(deadline))
            if not events:
                _remaining_git_time(deadline)
                continue
            try:
                chunk = os.read(
                    descriptor,
                    min(READ_CHUNK_BYTES, maximum_size + 1 - len(response)),
                )
            except NONBLOCKING_READ_RETRY_ERRORS:
                continue
            if not chunk:
                return bytes(response)
            response.extend(chunk)
            if len(response) > maximum_size:
                raise RuntimeError("reviewed Git blob response has trailing data")
    finally:
        selector.close()


def _kill_and_reap_git_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is None:
        try:
            process.kill()
        except OSError as exc:
            if process.poll() is None:
                raise RuntimeError(
                    "reviewed Git blob reader could not be killed"
                ) from exc
    try:
        process.wait(timeout=PROCESS_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("reviewed Git blob reader could not be reaped") from exc


def _close_process_pipes(*streams: Any | None) -> None:
    for stream in streams:
        if stream is None:
            continue
        try:
            stream.close()
        except PIPE_CLOSE_ERRORS:
            pass


def _read_git_blob(root: Path, object_id: str, expected_size: int) -> bytes:
    if expected_size < 1 or expected_size > MAX_INPUT_BYTES:
        raise RuntimeError("reviewed Git blob declared size is invalid")
    try:
        process = subprocess.Popen(
            _trusted_git_command("cat-file", "--batch"),
            cwd=root,
            env=scanner_git_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        raise RuntimeError("reviewed Git blob reader failed to start") from exc
    deadline = time.monotonic() + GIT_TIMEOUT_SECONDS
    try:
        if process.stdin is None or process.stdout is None:
            raise RuntimeError("reviewed Git blob reader pipes are unavailable")
        process.stdin.write(object_id.encode("ascii") + b"\n")
        process.stdin.close()
        expected_header = f"{object_id} blob {expected_size}\n".encode("ascii")
        response = _read_git_response(
            process.stdout,
            len(expected_header) + expected_size + 1,
            deadline,
        )
        content = _parse_git_batch_blob(response, object_id, expected_size)
        try:
            return_code = process.wait(timeout=_remaining_git_time(deadline))
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("reviewed Git blob reader timed out") from exc
        if return_code != 0:
            raise RuntimeError("reviewed Git blob reader failed")
        return content
    except GIT_READER_ERRORS:
        _kill_and_reap_git_process(process)
        raise
    finally:
        _close_process_pipes(process.stdin, process.stdout)


def _git_blob(root: Path, object_id: str, expected_size: int) -> bytes:
    actual_size = _git_blob_metadata(root, object_id)
    if actual_size != expected_size:
        raise RuntimeError("reviewed Git blob declared size differs")
    return _read_git_blob(root, object_id, actual_size)


def _validate_python_shape(data: bytes, line_number: int) -> None:
    try:
        tree = ast.parse(data.decode("utf-8"), filename="<reviewed-git-blob>")
    except (SyntaxError, UnicodeDecodeError) as exc:
        raise RuntimeError("reviewed Git blob is not valid UTF-8 Python") from exc
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign) and node.lineno == line_number
    ]
    if len(candidates) != 1:
        raise RuntimeError("reviewed line does not select one assignment")
    node = candidates[0]
    if (
        len(node.targets) != 1
        or not isinstance(node.targets[0], ast.Name)
        or node.targets[0].id != EXPECTED_AST["target"]
        or not isinstance(node.value, ast.Call)
        or not isinstance(node.value.func, ast.Name)
        or node.value.func.id != EXPECTED_AST["call"]
        or node.value.args
        or node.value.keywords
    ):
        raise RuntimeError("reviewed assignment shape differs")
    string_literals = sum(
        isinstance(child, ast.Constant) and isinstance(child.value, (str, bytes))
        for child in ast.walk(node)
    )
    if string_literals != EXPECTED_AST["string_literal_count"]:
        raise RuntimeError("reviewed assignment contains string literal material")


def _ledger_entry(raw: object, root: Path, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict) or set(raw) != ENTRY_KEYS:
        raise RuntimeError(f"reviewed addition {index} schema differs")
    if raw["scope"] != "git_history":
        raise RuntimeError(f"reviewed addition {index} scope differs")
    object_id = raw["exact_source_identifier"]
    line_number = raw["exact_line_number"]
    source_bytes = raw["exact_source_bytes"]
    source_sha256 = raw["exact_source_sha256"]
    line_sha256 = raw["exact_line_sha256"]
    if (
        not isinstance(object_id, str)
        or OBJECT_ID.fullmatch(object_id) is None
        or type(line_number) is not int
        or line_number < 1
        or type(source_bytes) is not int
        or source_bytes < 1
        or not isinstance(source_sha256, str)
        or SHA256.fullmatch(source_sha256) is None
        or not isinstance(line_sha256, str)
        or SHA256.fullmatch(line_sha256) is None
        or raw["path_hint"] != CURRENT_OPERATOR_PATH.as_posix()
        or raw["expected_ast"] != EXPECTED_AST
    ):
        raise RuntimeError(f"reviewed addition {index} binding differs")

    blob = _git_blob(root, object_id, source_bytes)
    line = _physical_line(blob, line_number)
    if (
        len(blob) != source_bytes
        or hashlib.sha256(blob).hexdigest() != source_sha256
        or hashlib.sha256(line).hexdigest() != line_sha256
    ):
        raise RuntimeError(f"reviewed addition {index} hash binding differs")
    expected_finding = Finding(object_id, line_number, RULE_GENERIC_CREDENTIAL)
    line_findings = {
        finding
        for finding in scan_bytes(blob, object_id)
        if finding.line == line_number
    }
    if line_findings != {expected_finding}:
        raise RuntimeError(f"reviewed addition {index} scanner finding differs")
    _validate_python_shape(blob, line_number)
    return {
        "scope": "git_history",
        "exact_source_identifier": object_id,
        "exact_line_number": line_number,
        "exact_source_bytes": source_bytes,
        "exact_source_sha256": source_sha256,
        "exact_line_sha256": line_sha256,
        "classification": EXPECTED_REVIEW["classification"],
        "rationale": EXPECTED_REVIEW["rationale"],
    }


def render(root: Path = REPOSITORY_ROOT) -> bytes:
    parent_bytes = _regular_file(root, PARENT_LEDGER_PATH, "parent ledger")
    if (
        len(parent_bytes) != EXPECTED_PARENT_BYTES
        or hashlib.sha256(parent_bytes).hexdigest() != EXPECTED_PARENT_SHA256
    ):
        raise RuntimeError("parent ledger binding differs")
    parent = _strict_json(parent_bytes, "parent ledger")
    if len(parse_reviewed_findings(parent_bytes)) != EXPECTED_PARENT_ENTRIES:
        raise RuntimeError("parent ledger entry count differs")

    source = _strict_json(
        _regular_file(root, SOURCE_PATH, "additions source"), "additions source"
    )
    if set(source) != {"document", "review", "entries"}:
        raise RuntimeError("additions source top-level schema differs")
    if source["document"] != EXPECTED_DOCUMENT or source["review"] != EXPECTED_REVIEW:
        raise RuntimeError("additions source policy binding differs")
    raw_entries = source["entries"]
    if not isinstance(raw_entries, list) or len(raw_entries) != EXPECTED_NEW_ENTRIES:
        raise RuntimeError("additions source entry inventory differs")
    additions = [
        _ledger_entry(raw, root, index)
        for index, raw in enumerate(raw_entries, start=1)
    ]
    keys = {
        (entry["scope"], entry["exact_source_identifier"], entry["exact_line_number"])
        for entry in [*parent["entries"], *additions]
    }
    if len(keys) != EXPECTED_PARENT_ENTRIES + EXPECTED_NEW_ENTRIES:
        raise RuntimeError("generated ledger contains duplicate bindings")

    current_operator = _regular_file(root, CURRENT_OPERATOR_PATH, "current operator")
    if scan_bytes(current_operator, CURRENT_OPERATOR_PATH.as_posix()):
        raise RuntimeError("current operator still contains a sanitized finding")

    generated = dict(parent)
    generated["entries"] = [*parent["entries"], *additions]
    content = (json.dumps(generated, indent=2, ensure_ascii=True) + "\n").encode()
    if len(parse_reviewed_findings(content)) != len(generated["entries"]):
        raise RuntimeError("generated ledger does not validate exactly")
    return content


def _capture_target_state(parent_descriptor: int, name: str) -> tuple[int, ...] | None:
    try:
        metadata = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(metadata.st_mode):
        raise RuntimeError("generated ledger target is unsafe")
    return _stable_file_identity(metadata)


def _validate_staged_output(
    parent_descriptor: int,
    name: str,
    descriptor: int,
    expected_size: int,
) -> os.stat_result:
    staged = os.fstat(descriptor)
    named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
    if (
        not stat.S_ISREG(staged.st_mode)
        or staged.st_nlink != 1
        or staged.st_size != expected_size
        or stat.S_IMODE(staged.st_mode) != 0o644
        or _stable_file_identity(staged) != _stable_file_identity(named)
        or named.st_nlink != 1
    ):
        raise RuntimeError("generated ledger stage changed before publication")
    return staged


def _publication_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_size,
        metadata.st_nlink,
    )


def _install(root: Path, content: bytes) -> None:
    if not content or len(content) > MAX_INPUT_BYTES:
        raise RuntimeError("generated ledger content size is invalid")
    root_descriptor = _open_root_descriptor(root)
    parent_descriptor = -1
    output_descriptor = -1
    temporary_name: str | None = None
    published = False
    try:
        root_identity = _descriptor_identity(root_descriptor)
        parent_descriptor = _open_directory_descriptor(
            root_descriptor, OUTPUT_PATH.parent, "generated ledger"
        )
        parent_identity = _descriptor_identity(parent_descriptor)
        target_state = _capture_target_state(parent_descriptor, OUTPUT_PATH.name)

        for _attempt in range(TEMPORARY_ATTEMPTS):
            candidate = (
                f".{OUTPUT_PATH.name}.st0106-{os.getpid()}-{os.urandom(8).hex()}"
            )
            try:
                output_descriptor = os.open(
                    candidate,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_CLOEXEC", 0)
                    | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent_descriptor,
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise RuntimeError("cannot allocate a safe generated ledger stage")

        view = memoryview(content)
        while view:
            written = os.write(output_descriptor, view)
            if written <= 0:
                raise RuntimeError("short write while staging generated ledger")
            view = view[written:]
        os.fchmod(output_descriptor, 0o644)
        os.fsync(output_descriptor)
        staged = _validate_staged_output(
            parent_descriptor,
            temporary_name,
            output_descriptor,
            len(content),
        )

        _assert_directory_identity(
            root_descriptor,
            OUTPUT_PATH.parent,
            parent_identity,
            "generated ledger",
        )
        _assert_root_identity(root, root_identity)
        if _capture_target_state(parent_descriptor, OUTPUT_PATH.name) != target_state:
            raise RuntimeError("generated ledger target changed before publication")
        rechecked_stage = _validate_staged_output(
            parent_descriptor,
            temporary_name,
            output_descriptor,
            len(content),
        )
        if _stable_file_identity(rechecked_stage) != _stable_file_identity(staged):
            raise RuntimeError("generated ledger stage changed before publication")
        os.replace(
            temporary_name,
            OUTPUT_PATH.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        published = True
        temporary_name = None
        current = os.stat(
            OUTPUT_PATH.name,
            dir_fd=parent_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(current.st_mode) or _publication_identity(
            current
        ) != _publication_identity(staged):
            raise RuntimeError("generated ledger target changed during publication")
        os.fsync(parent_descriptor)
        _assert_directory_identity(
            root_descriptor,
            OUTPUT_PATH.parent,
            parent_identity,
            "generated ledger",
        )
        _assert_root_identity(root, root_identity)
    finally:
        if output_descriptor >= 0:
            os.close(output_descriptor)
        if temporary_name is not None and parent_descriptor >= 0 and not published:
            try:
                os.unlink(temporary_name, dir_fd=parent_descriptor)
            except FileNotFoundError:
                pass
        if parent_descriptor >= 0:
            os.close(parent_descriptor)
        os.close(root_descriptor)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        content = render()
        if arguments.check:
            if (
                _regular_file(REPOSITORY_ROOT, OUTPUT_PATH, "generated ledger")
                != content
            ):
                raise RuntimeError("generated V3 ledger drift")
            mode = "check"
        else:
            _install(REPOSITORY_ROOT, content)
            mode = "install"
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "entry_count": EXPECTED_PARENT_ENTRIES + EXPECTED_NEW_ENTRIES,
                "mode": mode,
                "specific_rule_suppression": "FORBIDDEN",
                "status": "PASS",
                "story_id": "ST-0106",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
