"""Deterministic TOCTOU regressions for the ST-0101 workspace writer."""

from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
from typing import Any

import pytest

from scripts import bootstrap_workspace as workspace


REPO_ROOT = Path(__file__).resolve().parents[2]


def copy_bootstrap_seed(destination: Path) -> None:
    """Copy the code-owned seed allowlist, never paths from untrusted JSON."""

    destination.mkdir()
    for relative_text in workspace.EXPECTED_REQUIRED_FILES:
        relative = Path(relative_text)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_ROOT / relative, target)


def tree_snapshot(root: Path) -> dict[str, tuple[str, bytes | str]]:
    result: dict[str, tuple[str, bytes | str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            result[relative] = ("symlink", os.readlink(path))
        elif path.is_file():
            result[relative] = ("file", path.read_bytes())
        elif path.is_dir():
            result[relative] = ("directory", "")
    return result


def test_leaf_symlink_swap_writes_only_to_pinned_fd_and_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A post-preflight leaf swap must never redirect a marker outside root."""

    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    outside_marker = outside / workspace.MARKER_FILE
    outside_marker.write_text("# Human-owned outside marker\n", encoding="utf-8")
    outside_before = tree_snapshot(outside)

    original_atomic_write = getattr(workspace, "_atomic_write_at", None)
    assert callable(original_atomic_write), (
        "the workspace writer must expose the fd-relative _atomic_write_at primitive"
    )
    logical_leaf = root / "apps/api"
    pinned_leaf = root / "apps/api-pinned-by-race"
    injected = False

    def swap_leaf_then_write(
        directory_fd: int,
        filename: str,
        payload: bytes,
    ) -> Any:
        nonlocal injected
        if not injected:
            assert logical_leaf.is_dir() and not logical_leaf.is_symlink()
            logical_leaf.rename(pinned_leaf)
            logical_leaf.symlink_to(outside, target_is_directory=True)
            injected = True
        return original_atomic_write(directory_fd, filename, payload)

    monkeypatch.setattr(workspace, "_atomic_write_at", swap_leaf_then_write)

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert failure["story_id"] == "ST-0101"
    assert isinstance(failure["error"], str) and failure["error"]

    # The attacker-controlled logical path remains a symlink, so PASS would
    # be invalid even though the verified directory descriptor stayed pinned.
    assert logical_leaf.is_symlink()
    assert logical_leaf.resolve(strict=True) == outside.resolve(strict=True)

    # The fd-relative write may safely land in the renamed, already-open leaf.
    # It must never follow the replacement symlink into the outside directory.
    pinned_marker = pinned_leaf / workspace.MARKER_FILE
    assert pinned_marker.is_file() and not pinned_marker.is_symlink()
    config = json.loads((root / workspace.CONFIG_NAME).read_text(encoding="utf-8"))
    assert pinned_marker.read_bytes() == workspace.marker_bytes(
        config["directories"][0]
    )
    assert tree_snapshot(outside) == outside_before


def test_missing_parent_symlink_swap_cannot_redirect_mkdir_or_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A symlink inserted after ENOENT must be rejected by the descriptor walk."""

    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "sentinel.txt"
    sentinel.write_text("unchanged\n", encoding="utf-8")
    outside_before = tree_snapshot(outside)

    original_mkdir = workspace.os.mkdir
    injected = False

    def swap_missing_parent(
        path: str | bytes,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> None:
        nonlocal injected
        if not injected and path == "apps" and dir_fd is not None:
            workspace.os.symlink(
                outside,
                path,
                target_is_directory=True,
                dir_fd=dir_fd,
            )
            injected = True
            raise FileExistsError(errno.EEXIST, "injected symlink race", path)
        original_mkdir(path, mode=mode, dir_fd=dir_fd)

    monkeypatch.setattr(workspace.os, "mkdir", swap_missing_parent)

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "symlink component" in failure["error"]
    assert (root / "apps").is_symlink()
    assert tree_snapshot(outside) == outside_before
    assert not (outside / workspace.MARKER_FILE).exists()


def test_oversized_sparse_config_is_rejected_before_any_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    config = root / workspace.CONFIG_NAME
    with config.open("r+b") as handle:
        handle.truncate(workspace.MAX_CONFIG_BYTES + 1)

    original_read = workspace.os.read
    bytes_read = 0

    def counted_read(descriptor: int, length: int) -> bytes:
        nonlocal bytes_read
        result = original_read(descriptor, length)
        bytes_read += len(result)
        return result

    monkeypatch.setattr(workspace.os, "read", counted_read)
    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "exceeds 262144 bytes" in failure["error"]
    assert bytes_read == 0
    assert not (root / "apps").exists()


def test_config_symlink_swap_between_lstat_and_open_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    config = root / workspace.CONFIG_NAME
    pinned_config = root / f"{workspace.CONFIG_NAME}.pinned"
    outside = tmp_path / "outside-config.json"
    outside.write_text('{"human_owned": true}\n', encoding="utf-8")
    outside_before = outside.read_bytes()

    original_open = workspace.os.open
    injected = False

    def swap_config_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal injected
        if not injected and path == workspace.CONFIG_NAME and dir_fd is not None:
            config.rename(pinned_config)
            config.symlink_to(outside)
            injected = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(workspace.os, "open", swap_config_then_open)
    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "symlink" in failure["error"]
    assert outside.read_bytes() == outside_before
    assert pinned_config.is_file()
    assert not (root / "apps").exists()


def test_existing_leaf_replacement_after_preflight_fails_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A different ordinary directory cannot inherit preflight trust."""

    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    logical_leaf = root / "apps/api"
    logical_leaf.mkdir(parents=True)
    preflight_leaf = root / "apps/api-preflight"

    original_open_directory = workspace._open_directory_fd
    target = workspace.PurePosixPath("apps/api")
    target_open_count = 0

    def replace_before_write_open(
        root_fd: int,
        relative: workspace.PurePosixPath,
        *,
        create: bool,
        require_final_creation: bool = False,
        source: str = "managed directory",
    ) -> int:
        nonlocal target_open_count
        if relative == target:
            target_open_count += 1
            if target_open_count == 2:
                logical_leaf.rename(preflight_leaf)
                logical_leaf.mkdir()
        return original_open_directory(
            root_fd,
            relative,
            create=create,
            require_final_creation=require_final_creation,
            source=source,
        )

    monkeypatch.setattr(
        workspace,
        "_open_directory_fd",
        replace_before_write_open,
    )

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert target_open_count == 2
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "changed after preflight: apps/api" in failure["error"]
    assert not (logical_leaf / workspace.MARKER_FILE).exists()
    assert not (preflight_leaf / workspace.MARKER_FILE).exists()


def test_marker_payload_is_complete_before_anonymous_inode_is_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """No discoverable temporary pathname may exist during marker writes."""

    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    first_leaf = root / "apps/api"
    original_write_all = workspace._write_all
    inspected = False

    def inspect_anonymous_inode(descriptor: int, payload: bytes) -> None:
        nonlocal inspected
        if not inspected:
            inspected = True
            assert first_leaf.is_dir()
            assert os.fstat(descriptor).st_nlink == 0
            assert workspace.MARKER_FILE not in os.listdir(first_leaf)
            assert not any(
                name.startswith(f".{workspace.MARKER_FILE}.")
                for name in os.listdir(first_leaf)
            )
        original_write_all(descriptor, payload)

    monkeypatch.setattr(workspace, "_write_all", inspect_anonymous_inode)

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert inspected
    assert exit_code == 0
    assert captured.err == ""
    result = json.loads(captured.out)
    assert result["status"] == "PASS"
    assert len(result["changed"]) == len(workspace.EXPECTED_DIRECTORY_PATHS)


def test_destination_appearing_at_publish_boundary_is_not_clobbered(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A raced-in human marker wins create-if-absent publication."""

    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    human_payload = b"# Human-owned marker created during bootstrap\n"
    original_link = workspace.os.link
    injected = False

    def insert_destination_then_link(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        assert dst_dir_fd is not None
        if not injected and destination == workspace.MARKER_FILE:
            raced_fd = os.open(
                workspace.MARKER_FILE,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            try:
                os.write(raced_fd, human_payload)
            finally:
                os.close(raced_fd)
            injected = True
        original_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(workspace.os, "link", insert_destination_then_link)

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "appeared during bootstrap" in failure["error"]
    assert (root / "apps/api" / workspace.MARKER_FILE).read_bytes() == human_payload
    assert not any(
        path.name.startswith(f".{workspace.MARKER_FILE}.")
        for path in (root / "apps/api").iterdir()
    )


def test_regular_file_swap_between_lstat_and_open_fails_inode_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    marker = leaf / workspace.MARKER_FILE
    marker.write_bytes(b"original\n")
    pinned = leaf / "README.preflight"
    directory_fd = os.open(leaf, workspace._directory_flags())
    original_open = workspace.os.open
    injected = False

    def replace_regular_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal injected
        if not injected and path == workspace.MARKER_FILE and dir_fd == directory_fd:
            marker.rename(pinned)
            marker.write_bytes(b"replacement\n")
            injected = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(workspace.os, "open", replace_regular_then_open)
    try:
        with pytest.raises(workspace.WorkspaceError, match="changed during validation"):
            workspace._open_regular_at(
                directory_fd,
                workspace.MARKER_FILE,
                source="race marker",
            )
    finally:
        os.close(directory_fd)

    assert injected
    assert pinned.read_bytes() == b"original\n"
    assert marker.read_bytes() == b"replacement\n"


def test_fifo_swap_between_lstat_and_open_is_nonblocking_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    leaf = tmp_path / "leaf"
    leaf.mkdir()
    marker = leaf / workspace.MARKER_FILE
    marker.write_bytes(b"original\n")
    pinned = leaf / "README.preflight"
    directory_fd = os.open(leaf, workspace._directory_flags())
    original_open = workspace.os.open
    injected = False

    def replace_with_fifo_then_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal injected
        if not injected and path == workspace.MARKER_FILE and dir_fd == directory_fd:
            assert flags & os.O_NONBLOCK
            marker.rename(pinned)
            os.mkfifo(marker)
            injected = True
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(workspace.os, "open", replace_with_fifo_then_open)
    try:
        with pytest.raises(workspace.WorkspaceError, match="changed during validation"):
            workspace._open_regular_at(
                directory_fd,
                workspace.MARKER_FILE,
                source="race marker",
            )
    finally:
        os.close(directory_fd)

    assert injected
    assert pinned.read_bytes() == b"original\n"
    assert stat.S_ISFIFO(marker.stat().st_mode)


def test_missing_leaf_appearing_after_preflight_is_not_adopted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    logical_leaf = root / "apps/api"
    original_open_directory = workspace._open_directory_fd
    target = workspace.PurePosixPath("apps/api")
    injected = False

    def insert_leaf_before_materialization(
        root_fd: int,
        relative: workspace.PurePosixPath,
        *,
        create: bool,
        require_final_creation: bool = False,
        source: str = "managed directory",
    ) -> int:
        nonlocal injected
        if not injected and relative == target and create and require_final_creation:
            logical_leaf.mkdir(parents=True)
            injected = True
        return original_open_directory(
            root_fd,
            relative,
            create=create,
            require_final_creation=require_final_creation,
            source=source,
        )

    monkeypatch.setattr(
        workspace,
        "_open_directory_fd",
        insert_leaf_before_materialization,
    )

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "appeared after preflight: apps/api" in failure["error"]
    assert not (logical_leaf / workspace.MARKER_FILE).exists()


def test_persistent_hard_link_on_managed_marker_is_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    assert workspace.main(["--root", str(root)]) == 0
    capsys.readouterr()

    marker = root / "apps/api" / workspace.MARKER_FILE
    outside_alias = tmp_path / "outside-marker-alias"
    os.link(marker, outside_alias)

    exit_code = workspace.main(["--root", str(root), "--check"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "must have exactly one hard link" in failure["error"]
    assert outside_alias.read_bytes() == marker.read_bytes()


def test_hard_link_added_at_publish_boundary_prevents_pass_and_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    outside_alias = tmp_path / "outside-marker-alias"
    original_link = workspace.os.link
    injected = False

    def publish_then_add_alias(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        original_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )
        if not injected and destination == workspace.MARKER_FILE:
            assert dst_dir_fd is not None
            original_link(
                destination,
                outside_alias,
                src_dir_fd=dst_dir_fd,
                follow_symlinks=False,
            )
            injected = True

    monkeypatch.setattr(workspace.os, "link", publish_then_add_alias)

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert injected
    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "changed during publication" in failure["error"]

    retry_code = workspace.main(["--root", str(root), "--check"])
    retry = capsys.readouterr()
    assert retry_code == 1
    assert retry.out == ""
    retry_failure = json.loads(retry.err)
    assert "must have exactly one hard link" in retry_failure["error"]


def test_check_mode_does_not_require_otmpfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    assert workspace.main(["--root", str(root)]) == 0
    capsys.readouterr()

    monkeypatch.delattr(workspace.os, "O_TMPFILE")
    exit_code = workspace.main(["--root", str(root), "--check"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    assert json.loads(captured.out)["status"] == "PASS"


def test_write_mode_fails_closed_without_otmpfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    monkeypatch.delattr(workspace.os, "O_TMPFILE")

    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "requires anonymous O_TMPFILE support" in failure["error"]
    assert not (root / "apps/api" / workspace.MARKER_FILE).exists()


def test_write_mode_fails_closed_when_filesystem_rejects_otmpfile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)
    original_open = workspace.os.open

    def reject_anonymous_inode(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if flags & os.O_TMPFILE == os.O_TMPFILE:
            raise OSError(errno.EOPNOTSUPP, "injected O_TMPFILE rejection")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(workspace.os, "open", reject_anonymous_inode)
    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "requires anonymous O_TMPFILE support" in failure["error"]
    assert not (root / "apps/api" / workspace.MARKER_FILE).exists()


def test_write_mode_fails_closed_when_procfs_publish_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repository"
    copy_bootstrap_seed(root)

    def reject_procfs_publish(*args: Any, **kwargs: Any) -> None:
        raise OSError(errno.ENOENT, "injected procfs rejection")

    monkeypatch.setattr(workspace.os, "link", reject_procfs_publish)
    exit_code = workspace.main(["--root", str(root)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    failure = json.loads(captured.err)
    assert failure["status"] == "FAIL"
    assert "Linux procfs link support is required" in failure["error"]
    assert not (root / "apps/api" / workspace.MARKER_FILE).exists()


def test_private_fd_window_restores_dumpability() -> None:
    before = workspace._prctl(workspace.PR_GET_DUMPABLE)
    assert before in {0, 1}

    with workspace._private_fd_window():
        assert workspace._prctl(workspace.PR_GET_DUMPABLE) == 0

    assert workspace._prctl(workspace.PR_GET_DUMPABLE) == before


def test_private_fd_window_blocks_parent_proc_fd_hardlink(tmp_path: Path) -> None:
    child_directory = tmp_path / "child-directory"
    child_directory.mkdir()
    outside_directory = tmp_path / "outside-directory"
    outside_directory.mkdir()
    outside_alias = outside_directory / "outside-alias"
    child_code = """
import os
import sys
from scripts import bootstrap_workspace as workspace

directory_fd = os.open(sys.argv[1], workspace._directory_flags())
try:
    with workspace._private_fd_window():
        descriptor = os.open(
            ".",
            os.O_WRONLY | os.O_TMPFILE | os.O_CLOEXEC,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            print(f"{os.getpid()} {descriptor}", flush=True)
            if sys.stdin.readline() != "continue\\n":
                raise RuntimeError("parent handshake failed")
            os.write(descriptor, b"complete before publish\\n")
            os.fsync(descriptor)
            os.link(
                f"/proc/self/fd/{descriptor}",
                "published",
                dst_dir_fd=directory_fd,
                follow_symlinks=True,
            )
        finally:
            os.close(descriptor)
finally:
    os.close(directory_fd)
print("SELF_PUBLISH_PASS", flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", child_code, str(child_directory)],
        cwd=REPO_ROOT,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert process.stdin is not None
    assert process.stdout is not None
    header = process.stdout.readline().strip()
    process_id, descriptor = (int(value) for value in header.split())
    outside_fd = os.open(outside_directory, workspace._directory_flags())

    blocked_error: OSError | None = None
    try:
        os.link(
            f"/proc/{process_id}/fd/{descriptor}",
            outside_alias.name,
            dst_dir_fd=outside_fd,
            follow_symlinks=True,
        )
    except OSError as exc:
        blocked_error = exc
    finally:
        os.close(outside_fd)
        process.stdin.write("continue\n")
        process.stdin.flush()

    remaining_stdout, stderr = process.communicate(timeout=10)
    assert process.returncode == 0, stderr
    assert blocked_error is not None
    assert blocked_error.errno in {errno.EACCES, errno.EPERM}
    assert not outside_alias.exists()
    assert remaining_stdout.strip() == "SELF_PUBLISH_PASS"
    assert (child_directory / "published").read_bytes() == (
        b"complete before publish\n"
    )
