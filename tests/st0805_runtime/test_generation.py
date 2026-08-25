from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path

import pytest

from scripts import build_st0805_policy_runtime as generator
from scripts import secure_generated_publication as secure_publication


def test_owner_generation_and_check_are_deterministic() -> None:
    generator.build(generator.REPO_ROOT)
    fixture = generator.REPO_ROOT / generator.FIXTURE_PATH
    manifest = generator.REPO_ROOT / generator.MANIFEST_PATH
    before = (fixture.read_bytes(), manifest.read_bytes())

    generator.build(generator.REPO_ROOT, check=True)
    generator.build(generator.REPO_ROOT)

    assert (fixture.read_bytes(), manifest.read_bytes()) == before


def test_check_path_never_calls_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(_artifacts: object) -> None:
        raise AssertionError("check attempted a write transaction")

    monkeypatch.setattr(generator, "_replace_generated", forbidden)
    fixture = generator.REPO_ROOT / generator.FIXTURE_PATH
    manifest = generator.REPO_ROOT / generator.MANIFEST_PATH
    before = (
        fixture.stat().st_mtime_ns,
        fixture.read_bytes(),
        manifest.stat().st_mtime_ns,
        manifest.read_bytes(),
    )
    generator.build(generator.REPO_ROOT, check=True)
    after = (
        fixture.stat().st_mtime_ns,
        fixture.read_bytes(),
        manifest.stat().st_mtime_ns,
        manifest.read_bytes(),
    )
    assert after == before


def test_symlink_hardlink_and_duplicate_destinations_are_rejected(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"old")
    hardlink = tmp_path / "hardlink"
    os.link(source, hardlink)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(source)

    with pytest.raises(generator.RuntimeGenerationError):
        generator._read_regular(source)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._read_regular(symlink)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((hardlink, b"new"),))
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((tmp_path / "same", b"a"),) * 2)
    assert source.read_bytes() == b"old"


def test_multioutput_success_preserves_foreign_files(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    foreign = tmp_path / "foreign"
    first.write_bytes(b"old-first")
    second.write_bytes(b"old-second")
    foreign.write_bytes(b"unrelated")

    generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"new-first"
    assert second.read_bytes() == b"new-second"
    assert foreign.read_bytes() == b"unrelated"


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

    monkeypatch.setattr(secure_publication, "_rename_exchange", fail_second)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"


def test_base_exception_rolls_back_then_propagates(
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

    monkeypatch.setattr(secure_publication, "_rename_exchange", interrupt_second)
    with pytest.raises(KeyboardInterrupt):
        generator._replace_generated(((first, b"new-first"), (second, b"new-second")))

    assert first.read_bytes() == b"old-first"
    assert second.read_bytes() == b"old-second"


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

    monkeypatch.setattr(secure_publication, "_rename_exchange", swap_then_exchange)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"
    assert parked.read_bytes() == b"original"


def test_post_exchange_foreign_target_and_backup_are_preserved(
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

    def exchange_then_swap(
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

    monkeypatch.setattr(secure_publication, "_rename_exchange", exchange_then_swap)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"
    assert moved_generated.read_bytes() == b"generated"
    recovery = [
        path for path in tmp_path.iterdir() if path.name.startswith(".target.st0805-")
    ]
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"original"


def test_missing_target_never_clobbers_raced_foreign_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"
    original_link = os.link
    injected = False

    def inject_then_link(
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

    monkeypatch.setattr(os, "link", inject_then_link)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert target.read_bytes() == b"foreign"


def test_parent_swap_preserves_foreign_replacement_tree(
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

    def swap_parent_then_commit(stage: secure_publication._StagedOutput) -> None:
        nonlocal swapped
        if not swapped:
            swapped = True
            owned.rename(parked)
            owned.mkdir()
            (owned / "target").write_bytes(b"foreign")
        original_commit(stage)

    monkeypatch.setattr(secure_publication, "_commit_stage", swap_parent_then_commit)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._replace_generated(((target, b"generated"),))

    assert (owned / "target").read_bytes() == b"foreign"
    assert (parked / "target").read_bytes() == b"original"


def test_source_identity_swap_during_read_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    replacement = tmp_path / "replacement"
    source.write_bytes(b"source")
    replacement.write_bytes(b"foreign")
    original_read = os.read
    swapped = False

    def swap_on_read(descriptor: int, size: int) -> bytes:
        nonlocal swapped
        chunk = original_read(descriptor, size)
        if not swapped:
            swapped = True
            replacement.replace(source)
        return chunk

    monkeypatch.setattr(os, "read", swap_on_read)
    with pytest.raises(generator.RuntimeGenerationError):
        generator._read_regular(source)
    assert source.read_bytes() == b"foreign"


@pytest.mark.parametrize(
    "mutation",
    (
        lambda value: value.replace(
            "schema_version: 2", "schema_version: 2\nschema_version: 2", 1
        ),
        lambda value: value.replace("schema_version: 2", "schema_version: &bad 2", 1),
        lambda value: value.replace("schema_version: 2", "schema_version: !!int 2", 1),
        lambda value: value.replace(
            "story_id: ST-0805", "story_id: ST-0805\nunknown: false", 1
        ),
        lambda value: value.replace(
            "policy_catalog_sha256: d68a584c",
            "policy_catalog_sha256: 068a584c",
            1,
        ),
    ),
)
def test_owner_contract_tamper_and_yaml_features_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: Callable[[str], str],
) -> None:
    contract = (generator.REPO_ROOT / generator.CONTRACT_PATH).read_text(
        encoding="utf-8"
    )
    target = tmp_path / generator.CONTRACT_PATH
    target.parent.mkdir(parents=True)
    target.write_text(mutation(contract), encoding="utf-8")
    monkeypatch.setattr(generator, "_require_hashes", lambda _root: None)
    with pytest.raises(generator.RuntimeGenerationError):
        generator.load_contract(tmp_path)


def test_generator_has_no_clobbering_replace_and_cli_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = Path(generator.__file__).read_text(encoding="utf-8")
    assert "os.replace" not in source
    assert "secure_generated_publication.publish_generated" in source
    called = False

    def forbidden(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(generator, "build", forbidden)
    assert generator.main(["--unknown"]) == 2
    assert not called
