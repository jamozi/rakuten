"""Hardened offline catalog verification tests."""

from __future__ import annotations

import errno
import hashlib
import os
import shutil
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from .support import REPOSITORY_ROOT
from raos.migrations import CatalogError, verify_all_sources
from raos.migrations import catalog
from raos.migrations import runner


def _copy_catalog_sources(target: Path) -> None:
    for item in (
        *catalog.ALEMBIC_RUNTIME_SPECS,
        *catalog.REVISION_SPECS,
        *catalog.CHECKPOINT_SPECS,
    ):
        destination = target / item.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPOSITORY_ROOT / item.relative_path, destination)


def test_live_catalog_verifies_every_source_and_is_deterministic() -> None:
    first = verify_all_sources(REPOSITORY_ROOT)
    second = verify_all_sources(REPOSITORY_ROOT)

    assert first == second
    assert len(first.runtime_sources) == 1
    assert len(first.revision_sources) == len(catalog.REVISION_SPECS) == 7
    assert len(first.checkpoint_sources) == 18
    assert len(first.catalog_sha256) == 64
    assert sum(item.size for item in first.checkpoint_sources) > 100_000
    assert first.runtime_sources[0].content is not None
    assert first.revision_sources[0].content is not None
    assert all(item.content is None for item in first.checkpoint_sources)


def test_executable_alembic_environment_drift_is_runtime_blocking(
    tmp_path: Path,
) -> None:
    _copy_catalog_sources(tmp_path)
    path = tmp_path / catalog.ALEMBIC_RUNTIME_SPECS[0].relative_path
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(CatalogError) as raised:
        verify_all_sources(tmp_path)
    assert raised.value.code is catalog.CatalogErrorCode.SOURCE_DIGEST_MISMATCH


def test_verified_execution_snapshot_is_immune_to_later_path_replacement(
    tmp_path: Path,
) -> None:
    _copy_catalog_sources(tmp_path)
    verification = verify_all_sources(tmp_path)
    relative = catalog.REVISION_SPECS[0].relative_path
    original = verification.revision_sources[0].content
    assert original is not None
    (tmp_path / relative).write_text(
        "raise RuntimeError('replaced')\n", encoding="utf-8"
    )

    with runner._verified_migration_root(verification) as snapshot_root:
        assert (snapshot_root / relative).read_bytes() == original
        assert b"replaced" not in (snapshot_root / relative).read_bytes()


def test_source_drift_fails_with_static_error(tmp_path: Path) -> None:
    _copy_catalog_sources(tmp_path)
    path = tmp_path / catalog.CHECKPOINT_SPECS[0].relative_path
    path.write_bytes(path.read_bytes() + b"\n")

    with pytest.raises(CatalogError) as raised:
        verify_all_sources(tmp_path)
    assert raised.value.code is catalog.CatalogErrorCode.SOURCE_DIGEST_MISMATCH
    assert str(raised.value) == "migration source digest does not match"
    assert str(path) not in str(raised.value)


def test_symlink_source_is_rejected_without_reading_target(tmp_path: Path) -> None:
    _copy_catalog_sources(tmp_path)
    relative = catalog.CHECKPOINT_SPECS[0].relative_path
    source = tmp_path / relative
    outside = tmp_path / "outside.sql"
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)

    with pytest.raises(CatalogError) as raised:
        verify_all_sources(tmp_path)
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_SOURCE


def test_symlink_ancestor_is_rejected(tmp_path: Path) -> None:
    _copy_catalog_sources(tmp_path)
    directory = tmp_path / "changes/st-0002/database"
    outside = tmp_path / "held-database"
    directory.rename(outside)
    directory.symlink_to(outside, target_is_directory=True)

    with pytest.raises(CatalogError) as raised:
        verify_all_sources(tmp_path)
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_SOURCE


def test_symlink_repository_root_is_rejected(tmp_path: Path) -> None:
    physical = tmp_path / "physical"
    physical.mkdir()
    linked = tmp_path / "linked"
    linked.symlink_to(physical, target_is_directory=True)

    with pytest.raises(CatalogError) as raised:
        verify_all_sources(linked)
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_ROOT


def test_regular_source_leaf_uses_required_nonblocking_nofollow_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sql"
    source.write_bytes(b"SELECT 1;\n")
    real_open = catalog.os.open
    calls: list[tuple[object, int, int | None]] = []

    def record_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        calls.append((path, flags, dir_fd))
        if dir_fd is None:
            return real_open(path, flags, mode)  # type: ignore[arg-type]
        return real_open(path, flags, mode, dir_fd=dir_fd)  # type: ignore[arg-type]

    monkeypatch.setattr(catalog.os, "open", record_open)

    assert catalog._read_regular_file(tmp_path, Path("source.sql"), 1024) == (
        b"SELECT 1;\n"
    )
    assert calls[-1][0] == "source.sql"
    assert calls[-1][1] & os.O_NOFOLLOW
    assert calls[-1][1] & os.O_NONBLOCK


@pytest.mark.parametrize("missing_flag", ("O_NOFOLLOW", "O_NONBLOCK"))
def test_missing_required_source_open_flag_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_flag: str,
) -> None:
    (tmp_path / "source.sql").write_bytes(b"SELECT 1;\n")
    monkeypatch.delattr(catalog.os, missing_flag)

    with pytest.raises(CatalogError) as raised:
        catalog._read_regular_file(tmp_path, Path("source.sql"), 1024)
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_SOURCE


@pytest.mark.serial
@pytest.mark.parametrize("node_kind", ("fifo", "socket", "directory"))
def test_special_source_leaf_fails_closed_without_blocking(
    tmp_path: Path,
    node_kind: str,
) -> None:
    source = tmp_path / "source.sql"
    listener: socket.socket | None = None
    if node_kind == "fifo":
        os.mkfifo(source)
    elif node_kind == "socket":
        try:
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        except PermissionError as exc:
            if (
                exc.errno == errno.EPERM
                and os.environ.get("RAOS_NETWORK_DENIED") == "1"
            ):
                pytest.skip(
                    "outer denied-network seccomp blocks AF_UNIX socket setup; "
                    "ordinary hosts retain socket-leaf rejection coverage"
                )
            raise
        listener.bind(os.fspath(source))
    else:
        source.mkdir()
    script = """
import sys
from pathlib import Path
from raos.migrations import catalog

path = Path(sys.argv[1])
try:
    catalog._read_regular_file(path.parent, Path(path.name), 1024)
except catalog.CatalogError as error:
    print(error.code)
else:
    raise SystemExit(1)
"""
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.fspath(REPOSITORY_ROOT / "python")
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-c", script, os.fspath(source)],
            cwd=REPOSITORY_ROOT,
            env=environment,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=2.0,
            check=False,
        )
    finally:
        if listener is not None:
            listener.close()
    assert completed.returncode == 0
    assert completed.stdout.strip() == catalog.CatalogErrorCode.INVALID_SOURCE
    assert completed.stderr == ""


@pytest.mark.parametrize("content", (b"\xff", b"SELECT 1;\x00"))
def test_invalid_text_is_rejected_even_with_matching_digest(
    tmp_path: Path,
    content: bytes,
) -> None:
    path = tmp_path / "source.sql"
    path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()

    with pytest.raises(CatalogError) as raised:
        catalog._verify_source(tmp_path, Path("source.sql"), digest, 1024)
    assert raised.value.code is catalog.CatalogErrorCode.SOURCE_TEXT_INVALID


def test_oversized_source_is_rejected_before_hashing(tmp_path: Path) -> None:
    path = tmp_path / "source.sql"
    path.write_bytes(b"x" * 9)

    with pytest.raises(CatalogError) as raised:
        catalog._verify_source(tmp_path, Path("source.sql"), "0" * 64, 8)
    assert raised.value.code is catalog.CatalogErrorCode.SOURCE_TOO_LARGE


def test_catalog_rejects_duplicate_or_reordered_checkpoint_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    duplicate = replace(
        catalog.CHECKPOINT_SPECS[1],
        revision=catalog.CHECKPOINT_SPECS[0].revision,
    )
    mutated = (catalog.CHECKPOINT_SPECS[0], duplicate, *catalog.CHECKPOINT_SPECS[2:])
    monkeypatch.setattr(catalog, "CHECKPOINT_SPECS", mutated)

    with pytest.raises(CatalogError) as raised:
        catalog.validate_catalog()
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_CATALOG


def test_catalog_rejects_path_escape(monkeypatch: pytest.MonkeyPatch) -> None:
    escaped = replace(
        catalog.CHECKPOINT_SPECS[0],
        relative_path=Path("../outside.sql"),
    )
    monkeypatch.setattr(
        catalog,
        "CHECKPOINT_SPECS",
        (escaped, *catalog.CHECKPOINT_SPECS[1:]),
    )

    with pytest.raises(CatalogError) as raised:
        catalog.validate_catalog()
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_CATALOG


def test_catalog_rejects_unpinned_revision_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = replace(catalog.REVISION_SPECS[0], sha256="TO_BE_PINNED")
    monkeypatch.setattr(catalog, "REVISION_SPECS", (marker,))

    with pytest.raises(CatalogError) as raised:
        catalog.validate_catalog()
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_CATALOG


def test_catalog_accepts_only_a_linear_extensible_revision_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    successor = catalog.RevisionSpec(
        revision="202608030007",
        down_revision=catalog.HEAD_REVISION,
        story_id="ST-0308",
        relative_path=Path("migrations/versions/202608030007_future.py"),
        sha256="1" * 64,
        runner_version="1.6.0",
        server_version_num=180004,
    )
    monkeypatch.setattr(catalog, "REVISION_SPECS", (*catalog.REVISION_SPECS, successor))
    monkeypatch.setattr(catalog, "HEAD_REVISION", successor.revision)
    catalog.validate_catalog()

    monkeypatch.setattr(
        catalog,
        "REVISION_SPECS",
        (*catalog.REVISION_SPECS[:-1], replace(successor, down_revision=None)),
    )
    with pytest.raises(CatalogError) as raised:
        catalog.validate_catalog()
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_CATALOG


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("runner_version", "latest"),
        ("server_version_num", True),
        ("server_version_num", 99999),
        ("server_version_num", 1000000),
    ),
)
def test_catalog_rejects_invalid_revision_runtime_metadata(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
) -> None:
    mutated = replace(catalog.REVISION_SPECS[0], **{field: value})
    monkeypatch.setattr(catalog, "REVISION_SPECS", (mutated,))

    with pytest.raises(CatalogError) as raised:
        catalog.validate_catalog()
    assert raised.value.code is catalog.CatalogErrorCode.INVALID_CATALOG


def test_revision_runtime_metadata_is_bound_into_catalog_digest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline = catalog._catalog_digest()
    mutated = replace(catalog.REVISION_SPECS[0], runner_version="1.0.1")
    monkeypatch.setattr(catalog, "REVISION_SPECS", (mutated,))

    assert catalog._catalog_digest() != baseline
