from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts import build_st0803_comparison_validation_runtime as generator


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
    original_replace = os.replace
    calls = 0

    def fail_second(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("synthetic")
        original_replace(source, destination)

    monkeypatch.setattr(
        "scripts.build_st0803_comparison_validation_runtime.os.replace",
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
    original_replace = os.replace
    calls = 0

    def interrupt_second(
        source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        original_replace(source, destination)

    monkeypatch.setattr(
        "scripts.build_st0803_comparison_validation_runtime.os.replace",
        interrupt_second,
    )
    with pytest.raises(KeyboardInterrupt):
        generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["first", "second"]


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
