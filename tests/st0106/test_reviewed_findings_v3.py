"""Exact additive-ledger checks for the PR #106 sanitized findings."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest

from scripts import build_st0106_reviewed_secret_findings_v3 as generator
from scripts.scan_secrets import parse_reviewed_findings, scan_bytes


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def require_reviewed_history_objects() -> None:
    source = json.loads((REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes())
    try:
        for entry in source["entries"]:
            generator._git_blob(
                REPOSITORY_ROOT,
                entry["exact_source_identifier"],
                entry["exact_source_bytes"],
            )
    except RuntimeError:
        pytest.skip("exact reviewed Git objects are unavailable in this checkout")


def run_trusted_git(
    root: Path, *arguments: str, input_bytes: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        generator._trusted_git_command(*arguments),
        cwd=root,
        env=generator.scanner_git_environment(),
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=generator.GIT_TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, result.stderr
    return result


def marker_helper(path: Path, marker: Path) -> None:
    path.write_text(
        f"#!/bin/sh\n/usr/bin/touch -- {shlex.quote(os.fspath(marker))}\nexit 1\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def test_generated_v3_ledger_preserves_parent_and_adds_three_history_bindings() -> None:
    parent_bytes = (REPOSITORY_ROOT / generator.PARENT_LEDGER_PATH).read_bytes()
    source_bytes = (REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes()
    output_bytes = (REPOSITORY_ROOT / generator.OUTPUT_PATH).read_bytes()
    parent = json.loads(parent_bytes)
    source = json.loads(source_bytes)
    output = json.loads(output_bytes)

    assert len(parent_bytes) == generator.EXPECTED_PARENT_BYTES
    assert hashlib.sha256(parent_bytes).hexdigest() == generator.EXPECTED_PARENT_SHA256
    assert source["document"] == generator.EXPECTED_DOCUMENT
    assert source["review"] == generator.EXPECTED_REVIEW
    assert len(source["entries"]) == generator.EXPECTED_NEW_ENTRIES
    assert output["entries"][: generator.EXPECTED_PARENT_ENTRIES] == parent["entries"]
    additions = output["entries"][generator.EXPECTED_PARENT_ENTRIES :]
    expected_additions = []
    for entry in source["entries"]:
        assert set(entry) == generator.ENTRY_KEYS
        assert entry["scope"] == "git_history"
        assert entry["path_hint"] == generator.CURRENT_OPERATOR_PATH.as_posix()
        assert entry["expected_ast"] == generator.EXPECTED_AST
        expected_additions.append(
            {
                "scope": entry["scope"],
                "exact_source_identifier": entry["exact_source_identifier"],
                "exact_line_number": entry["exact_line_number"],
                "exact_source_bytes": entry["exact_source_bytes"],
                "exact_source_sha256": entry["exact_source_sha256"],
                "exact_line_sha256": entry["exact_line_sha256"],
                "classification": generator.EXPECTED_REVIEW["classification"],
                "rationale": generator.EXPECTED_REVIEW["rationale"],
            }
        )
    assert additions == expected_additions
    assert sum(entry["scope"] == "worktree" for entry in output["entries"]) == 31
    assert sum(entry["scope"] == "git_history" for entry in output["entries"]) == 87
    assert len(parse_reviewed_findings(output_bytes)) == 118


def test_generator_reproduces_v3_when_exact_history_objects_are_available() -> None:
    require_reviewed_history_objects()
    output_bytes = (REPOSITORY_ROOT / generator.OUTPUT_PATH).read_bytes()
    assert generator.render(REPOSITORY_ROOT) == output_bytes


def test_v3_source_and_current_operator_have_no_sanitized_finding() -> None:
    for relative in (
        generator.SOURCE_PATH,
        generator.OUTPUT_PATH,
        generator.CURRENT_OPERATOR_PATH,
        Path("changes/st-0106/REVIEWED-SECRET-FINDINGS-ACTIVATION-v3.yaml"),
    ):
        content = (REPOSITORY_ROOT / relative).read_bytes()
        assert scan_bytes(content, relative.as_posix()) == set()


def test_generator_rejects_reviewed_blob_hash_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    require_reviewed_history_objects()
    original = generator._git_blob
    first_identifier = json.loads(
        (REPOSITORY_ROOT / generator.SOURCE_PATH).read_bytes()
    )["entries"][0]["exact_source_identifier"]

    def drifted_blob(root: Path, object_id: str, expected_size: int) -> bytes:
        content = original(root, object_id, expected_size)
        if object_id == first_identifier:
            return content + b"\n"
        return content

    monkeypatch.setattr(generator, "_git_blob", drifted_blob)
    with pytest.raises(RuntimeError, match="hash binding differs"):
        generator.render(REPOSITORY_ROOT)


def test_batch_blob_parser_rejects_truncated_and_trailing_responses() -> None:
    object_id = "1" * 40
    valid = f"{object_id} blob 3\n".encode() + b"abc\n"
    assert generator._parse_git_batch_blob(io.BytesIO(valid), object_id, 3) == b"abc"

    truncated = f"{object_id} blob 3\n".encode() + b"ab"
    with pytest.raises(RuntimeError, match="truncated"):
        generator._parse_git_batch_blob(io.BytesIO(truncated), object_id, 3)

    trailing = valid + b"unexpected"
    with pytest.raises(RuntimeError, match="trailing data"):
        generator._parse_git_batch_blob(io.BytesIO(trailing), object_id, 3)


def test_git_blob_rejects_oversized_object_before_content_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    run_trusted_git(repository, "init", "--quiet")
    oversized = b"x" * (generator.MAX_INPUT_BYTES + 1)
    object_id = (
        run_trusted_git(
            repository,
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=oversized,
        )
        .stdout.strip()
        .decode("ascii")
    )

    def forbidden_content_read(root: Path, identifier: str, size: int) -> bytes:
        raise AssertionError((root, identifier, size))

    monkeypatch.setattr(generator, "_read_git_blob", forbidden_content_read)
    with pytest.raises(RuntimeError, match="exceeds the bounded input size"):
        generator._git_blob(repository, object_id, len(oversized))


def test_missing_promisor_object_uses_sanitized_git_without_helpers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    run_trusted_git(repository, "init", "--quiet")

    hostile_bin = tmp_path / "hostile-bin"
    hostile_bin.mkdir()
    path_marker = tmp_path / "path-helper-called"
    remote_marker = tmp_path / "remote-helper-called"
    credential_marker = tmp_path / "credential-helper-called"
    marker_helper(hostile_bin / "git", path_marker)
    remote_helper = tmp_path / "remote-helper"
    credential_helper = tmp_path / "credential-helper"
    marker_helper(remote_helper, remote_marker)
    marker_helper(credential_helper, credential_marker)

    run_trusted_git(repository, "config", "core.repositoryformatversion", "1")
    run_trusted_git(repository, "config", "extensions.partialClone", "origin")
    run_trusted_git(repository, "config", "remote.origin.promisor", "true")
    run_trusted_git(
        repository, "config", "remote.origin.partialCloneFilter", "blob:none"
    )
    run_trusted_git(repository, "config", "protocol.ext.allow", "always")
    run_trusted_git(repository, "config", "remote.origin.url", f"ext::{remote_helper}")
    run_trusted_git(
        repository,
        "config",
        "credential.helper",
        f"!{credential_helper}",
    )

    hostile_global = tmp_path / "hostile-global.gitconfig"
    run_trusted_git(
        repository,
        "config",
        "--file",
        os.fspath(hostile_global),
        "credential.helper",
        f"!{credential_helper}",
    )
    monkeypatch.setenv("PATH", f"{hostile_bin}:/usr/bin:/bin")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.fspath(hostile_global))
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", f"!{credential_helper}")
    monkeypatch.setenv("GIT_NO_LAZY_FETCH", "0")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "1")

    observed: list[tuple[list[str], dict[str, object]]] = []
    actual_run = subprocess.run

    def audited_run(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[bytes]:
        observed.append((command, kwargs))
        return actual_run(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(generator.subprocess, "run", audited_run)
    with pytest.raises(RuntimeError, match="unavailable or not a blob"):
        generator._git_blob(repository, "f" * 40, 1)

    assert len(observed) == 1
    command, kwargs = observed[0]
    assert command[0] in {"/usr/bin/git", "/bin/git"}
    assert Path(command[0]).is_absolute()
    assert kwargs["env"] == generator.scanner_git_environment()
    assert kwargs["stderr"] is subprocess.DEVNULL
    assert kwargs["timeout"] == generator.GIT_TIMEOUT_SECONDS
    assert generator.scanner_git_environment()["GIT_NO_LAZY_FETCH"] == "1"
    assert generator.scanner_git_environment()["GIT_TERMINAL_PROMPT"] == "0"
    assert not path_marker.exists()
    assert not remote_marker.exists()
    assert not credential_marker.exists()


def test_git_blob_content_reader_uses_same_sanitized_absolute_git(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    run_trusted_git(repository, "init", "--quiet")
    content = b"ordinary source\n"
    object_id = (
        run_trusted_git(
            repository,
            "hash-object",
            "-w",
            "--stdin",
            input_bytes=content,
        )
        .stdout.strip()
        .decode("ascii")
    )
    observed: list[tuple[list[str], dict[str, object]]] = []
    actual_popen = subprocess.Popen

    def audited_popen(command: list[str], **kwargs: object) -> subprocess.Popen[bytes]:
        observed.append((command, kwargs))
        return actual_popen(command, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(generator.subprocess, "Popen", audited_popen)
    assert generator._git_blob(repository, object_id, len(content)) == content

    batch_calls = [item for item in observed if item[0][-2:] == ["cat-file", "--batch"]]
    assert len(batch_calls) == 1
    command, kwargs = batch_calls[0]
    assert command[0] in {"/usr/bin/git", "/bin/git"}
    assert Path(command[0]).is_absolute()
    assert kwargs["env"] == generator.scanner_git_environment()
    assert kwargs["stdin"] is subprocess.PIPE
    assert kwargs["stdout"] is subprocess.PIPE
    assert kwargs["stderr"] is subprocess.DEVNULL


def test_regular_file_rejects_preopen_leaf_swap_without_reading_symlink_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    relative = Path("changes/st-0106/contracts/source.json")
    target = repository / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"inside")
    held = target.with_name("held.json")
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    actual_stat = os.stat
    swapped = False

    def stat_with_leaf_swap(
        path: os.PathLike[str] | str | int,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> os.stat_result:
        nonlocal swapped
        if path == relative.name and dir_fd is not None and not swapped:
            target.rename(held)
            target.symlink_to(outside)
            swapped = True
        return actual_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(generator.os, "stat", stat_with_leaf_swap)
    with pytest.raises(RuntimeError, match="regular non-symlink"):
        generator._regular_file(repository, relative, "source")

    assert swapped is True
    assert held.read_bytes() == b"inside"
    assert outside.read_bytes() == b"outside"


def test_regular_file_rejects_postopen_leaf_swap_without_reading_symlink_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    relative = Path("changes/st-0106/contracts/source.json")
    target = repository / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"inside")
    held = target.with_name("held.json")
    outside = tmp_path / "outside.json"
    outside.write_bytes(b"outside")
    actual_open = os.open
    swapped = False

    def open_then_swap(
        path: os.PathLike[str] | str,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = actual_open(path, flags, mode, dir_fd=dir_fd)
        if path == relative.name and dir_fd is not None and not swapped:
            target.rename(held)
            target.symlink_to(outside)
            swapped = True
        return descriptor

    monkeypatch.setattr(generator.os, "open", open_then_swap)
    with pytest.raises(RuntimeError, match="changed while being read"):
        generator._regular_file(repository, relative, "source")

    assert swapped is True
    assert held.read_bytes() == b"inside"
    assert outside.read_bytes() == b"outside"


def test_install_rejects_parent_swap_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    parent = repository / generator.OUTPUT_PATH.parent
    parent.mkdir(parents=True)
    target = repository / generator.OUTPUT_PATH
    target.write_bytes(b"old")
    held_parent = tmp_path / "held-parent"
    outside = tmp_path / "outside"
    outside.mkdir()
    actual_assert = generator._assert_directory_identity
    swapped = False

    def assert_with_parent_swap(
        root_descriptor: int,
        relative: Path,
        expected: tuple[int, int],
        label: str,
    ) -> None:
        nonlocal swapped
        if not swapped:
            parent.rename(held_parent)
            parent.symlink_to(outside, target_is_directory=True)
            swapped = True
        actual_assert(root_descriptor, relative, expected, label)

    monkeypatch.setattr(
        generator, "_assert_directory_identity", assert_with_parent_swap
    )
    with pytest.raises(RuntimeError, match="parent"):
        generator._install(repository, b"new")

    assert swapped is True
    assert (held_parent / generator.OUTPUT_PATH.name).read_bytes() == b"old"
    assert list(outside.iterdir()) == []
    assert not any(
        path.name.startswith(".reviewed-secret-findings.v3.yaml")
        for path in held_parent.iterdir()
    )


def test_install_target_swap_replaces_link_without_writing_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    target = repository / generator.OUTPUT_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    actual_replace = os.replace
    swapped = False

    def replace_with_target_swap(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
    ) -> None:
        nonlocal swapped
        target.unlink()
        target.symlink_to(outside)
        swapped = True
        actual_replace(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )

    monkeypatch.setattr(generator.os, "replace", replace_with_target_swap)
    generator._install(repository, b"new")

    assert swapped is True
    assert target.is_file() and not target.is_symlink()
    assert target.read_bytes() == b"new"
    assert outside.read_bytes() == b"outside"


def test_install_rejects_existing_target_change_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    target = repository / generator.OUTPUT_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    actual_capture = generator._capture_target_state
    captures = 0

    def capture_with_target_change(
        parent_descriptor: int, name: str
    ) -> tuple[int, ...] | None:
        nonlocal captures
        captures += 1
        if captures == 2:
            target.write_bytes(b"competing owner")
        return actual_capture(parent_descriptor, name)

    monkeypatch.setattr(generator, "_capture_target_state", capture_with_target_change)
    with pytest.raises(RuntimeError, match="changed before publication"):
        generator._install(repository, b"new")

    assert captures == 2
    assert target.read_bytes() == b"competing owner"
    assert not any(
        path.name.startswith(".reviewed-secret-findings.v3.yaml")
        for path in target.parent.iterdir()
    )


def test_install_rejects_staging_name_swap_before_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    target = repository / generator.OUTPUT_PATH
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    actual_validate = generator._validate_staged_output
    validations = 0

    def validate_with_stage_swap(
        parent_descriptor: int,
        name: str,
        descriptor: int,
        expected_size: int,
    ) -> os.stat_result:
        nonlocal validations
        validations += 1
        if validations == 2:
            os.unlink(name, dir_fd=parent_descriptor)
            os.symlink(outside, name, dir_fd=parent_descriptor)
        return actual_validate(parent_descriptor, name, descriptor, expected_size)

    monkeypatch.setattr(generator, "_validate_staged_output", validate_with_stage_swap)
    with pytest.raises(RuntimeError, match="stage changed before publication"):
        generator._install(repository, b"new")

    assert validations == 2
    assert target.read_bytes() == b"old"
    assert outside.read_bytes() == b"outside"
    assert not any(
        path.name.startswith(".reviewed-secret-findings.v3.yaml")
        for path in target.parent.iterdir()
    )
