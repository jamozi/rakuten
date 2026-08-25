from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import build_st0803_comparison_validation_runtime as generator
from scripts import secure_generated_publication as secure_publication


def test_owner_generation_and_check_are_deterministic() -> None:
    generator.build(generator.REPO_ROOT)
    fixture_before = (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes()
    manifest_before = (generator.REPO_ROOT / generator.MANIFEST_PATH).read_bytes()

    generator.build(generator.REPO_ROOT, check=True)
    generator.build(generator.REPO_ROOT)

    assert (generator.REPO_ROOT / generator.FIXTURE_PATH).read_bytes() == fixture_before
    assert (
        generator.REPO_ROOT / generator.MANIFEST_PATH
    ).read_bytes() == manifest_before


def test_check_path_never_calls_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_artifacts: object) -> None:
        raise AssertionError("check attempted a write transaction")

    monkeypatch.setattr(generator, "_replace_generated", forbidden)
    generator.build(generator.REPO_ROOT, check=True)


def test_destination_symlink_and_hardlink_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"old")
    hardlink = tmp_path / "hardlink"
    os.link(source, hardlink)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(source)

    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((hardlink, b"new"),))
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((symlink, b"new"),))
    assert source.read_bytes() == b"old"


def test_source_hardlink_and_duplicate_destinations_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"source")
    hardlink = tmp_path / "hardlink"
    os.link(source, hardlink)

    with pytest.raises(generator.RuntimeGenerationError):
        generator._read_regular(source)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((tmp_path / "same", b"a"),) * 2)


def test_multioutput_failure_rolls_back_exact_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    original_exchange = secure_publication._rename_exchange
    calls = 0

    def fail_second(parent_descriptor: int, source: str, destination: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic")
        original_exchange(parent_descriptor, source, destination)

    monkeypatch.setattr(
        secure_publication,
        "_rename_exchange",
        fail_second,
    )
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["first", "second"]


def test_async_interruption_rolls_back_then_propagates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    original_exchange = secure_publication._rename_exchange
    calls = 0

    def interrupt_second(parent_descriptor: int, source: str, destination: str) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original_exchange(parent_descriptor, source, destination)

    monkeypatch.setattr(
        secure_publication,
        "_rename_exchange",
        interrupt_second,
    )
    with pytest.raises(KeyboardInterrupt):
        generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["first", "second"]


def test_exchange_restores_foreign_target_swapped_at_syscall_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    parked = tmp_path / "parked-original"
    foreign = tmp_path / "foreign"
    target.write_bytes(b"original")
    foreign.write_bytes(b"foreign")
    original_exchange = secure_publication._rename_exchange
    swapped = False

    def swap_then_exchange(
        parent_descriptor: int, source: str, destination: str
    ) -> None:
        nonlocal swapped
        if not swapped and destination == target.name:
            swapped = True
            os.rename(
                target.name,
                parked.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.rename(
                foreign.name,
                target.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
        original_exchange(parent_descriptor, source, destination)

    monkeypatch.setattr(
        secure_publication,
        "_rename_exchange",
        swap_then_exchange,
    )
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"
    assert parked.read_bytes() == b"original"
    assert sorted(path.name for path in tmp_path.iterdir()) == [
        "parked-original",
        "target",
    ]


def test_post_exchange_foreign_target_stays_in_place_and_backup_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    moved_generated = tmp_path / "moved-generated"
    foreign = tmp_path / "foreign"
    target.write_bytes(b"original")
    foreign.write_bytes(b"foreign")
    original_exchange = secure_publication._rename_exchange
    swapped = False

    def exchange_then_swap_target(
        parent_descriptor: int, source: str, destination: str
    ) -> None:
        nonlocal swapped
        original_exchange(parent_descriptor, source, destination)
        if not swapped and destination == target.name:
            swapped = True
            os.rename(
                target.name,
                moved_generated.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )
            os.rename(
                foreign.name,
                target.name,
                src_dir_fd=parent_descriptor,
                dst_dir_fd=parent_descriptor,
            )

    monkeypatch.setattr(
        secure_publication,
        "_rename_exchange",
        exchange_then_swap_target,
    )
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"
    assert moved_generated.read_bytes() == b"generated"
    recovery = [
        path for path in tmp_path.iterdir() if path.name.startswith(".target.st0803-")
    ]
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"original"


def test_missing_target_install_never_clobbers_raced_foreign_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    original_link = os.link
    injected = False

    def inject_foreign_then_link(
        source: str,
        destination: str,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        if not injected:
            injected = True
            descriptor = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=dst_dir_fd,
            )
            try:
                os.write(descriptor, b"foreign")
            finally:
                os.close(descriptor)
        original_link(
            source,
            destination,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    monkeypatch.setattr(os, "link", inject_foreign_then_link)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["target"]


def test_parent_directory_swap_preserves_foreign_replacement_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned = tmp_path / "owned"
    parked = tmp_path / "parked-owned"
    owned.mkdir()
    target = owned / "target"
    target.write_bytes(b"original")
    original_commit = secure_publication._commit_stage
    swapped = False

    def swap_parent_then_commit(
        stage: secure_publication._StagedOutput,
    ) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            owned.rename(parked)
            owned.mkdir()
            (owned / "target").write_bytes(b"foreign")
        original_commit(stage)

    monkeypatch.setattr(
        secure_publication,
        "_commit_stage",
        swap_parent_then_commit,
    )
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert (owned / "target").read_bytes() == b"foreign"
    assert (parked / "target").read_bytes() == b"original"


def test_generator_does_not_use_clobbering_replace() -> None:
    source = Path(generator.__file__).read_text(encoding="utf-8")
    assert "os.replace" not in source


def test_unknown_cli_argument_is_rejected_without_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(generator, "build", forbidden)
    assert generator.main(["--unknown"]) == 2
    assert not called
