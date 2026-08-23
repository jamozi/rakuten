"""Crash, fault, confinement, and concurrency tests for ST-1204 publication."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading

import pytest

from scripts import build_st1204_ga4_recorded_adapter as generator


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _run_crashing_generate(
    root: Path,
    outputs: dict[Path, bytes],
    *,
    checkpoint: str,
    exit_code: int,
    legacy_manifest_sha256: str | None = None,
) -> subprocess.CompletedProcess[str]:
    payload = {
        relative.as_posix(): content.hex() for relative, content in outputs.items()
    }
    child = """
import json
import os
from pathlib import Path
import sys
from scripts import build_st1204_ga4_recorded_adapter as g
root = Path(sys.argv[1])
outputs = {Path(path): bytes.fromhex(value) for path, value in json.loads(sys.argv[2]).items()}
target = sys.argv[3]
exit_code = int(sys.argv[4])
if sys.argv[5]:
    g.LEGACY_MANIFEST_SHA256 = sys.argv[5]
g.build_outputs = lambda _root: outputs
g._checkpoint = lambda name: os._exit(exit_code) if name == target else None
g.generate(root)
"""
    return subprocess.run(
        [
            os.fspath(Path(sys.executable)),
            "-c",
            child,
            os.fspath(root),
            __import__("json").dumps(payload, sort_keys=True),
            checkpoint,
            str(exit_code),
            legacy_manifest_sha256 or "",
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def _outputs(tag: str) -> dict[Path, bytes]:
    fixtures = {
        name: generator._sorted_json({"name": name, "tag": tag}, compact=False)
        for name in generator.EXPECTED_FIXTURE_NAMES
    }
    manifest = generator._sorted_json(
        {
            "document": {
                "id": "RAOS-GA4-RECORDED-MANIFEST-001",
                "story_id": "ST-1204",
                "version": generator.MANIFEST_VERSION,
            },
            "fixture_count": len(fixtures),
            "fixtures": [
                {
                    "bytes": len(fixtures[name]),
                    "path": name,
                    "sha256": hashlib.sha256(fixtures[name]).hexdigest(),
                }
                for name in generator.EXPECTED_FIXTURE_NAMES
            ],
        },
        compact=False,
    )
    return {
        generator.MANIFEST_PATH: manifest,
        **{
            generator.FIXTURE_ROOT / name: content for name, content in fixtures.items()
        },
    }


def _install(
    root: Path,
    outputs: dict[Path, bytes],
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    return generator.generate(root)


def _assert_installed(root: Path, outputs: dict[Path, bytes]) -> None:
    for relative, content in outputs.items():
        assert (root / relative).read_bytes() == content
    story = root / generator.STORY_ROOT
    assert not any(
        (story / name).exists() or (story / name).is_symlink()
        for name in (
            generator.STAGE_NAME,
            generator.JOURNAL_PREPARING_NAME,
            generator.JOURNAL_NAME,
            generator.JOURNAL_CLEANUP_NAME,
        )
    )


def _write_bundle_directory(destination: Path, outputs: dict[Path, bytes]) -> None:
    destination.mkdir()
    for relative, content in outputs.items():
        below_bundle = relative.relative_to(generator.GENERATED_ROOT)
        target = destination / below_bundle
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def test_fresh_install_and_replacement_publish_one_exact_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _outputs("first")
    second = _outputs("second")
    assert (
        _install(tmp_path, first, monkeypatch)
        == hashlib.sha256(first[generator.MANIFEST_PATH]).hexdigest()
    )
    _assert_installed(tmp_path, first)

    assert (
        _install(tmp_path, second, monkeypatch)
        == hashlib.sha256(second[generator.MANIFEST_PATH]).hexdigest()
    )
    _assert_installed(tmp_path, second)
    assert (
        generator.check(tmp_path)
        == hashlib.sha256(second[generator.MANIFEST_PATH]).hexdigest()
    )


@pytest.mark.parametrize(
    ("checkpoint", "expected_generation"),
    [
        ("after-staged-baseline.json", "old"),
        ("before-publication", "old"),
        ("after-publication-namespace", "old"),
        ("after-publication-verify", "old"),
        ("after-committed-state", "new"),
        ("after-journal-cleanup-tombstone", "new"),
    ],
)
def test_fault_injection_restores_old_or_keeps_committed_new_tree(
    checkpoint: str,
    expected_generation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("old")
    new = _outputs("new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)

    def fail_at(name: str) -> None:
        if name == checkpoint:
            raise RuntimeError("synthetic publication fault")

    monkeypatch.setattr(generator, "_checkpoint", fail_at)
    with pytest.raises(RuntimeError, match="synthetic publication fault"):
        generator.generate(tmp_path)

    _assert_installed(tmp_path, old if expected_generation == "old" else new)


def test_exchange_unavailable_fails_before_changing_installed_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("old")
    new = _outputs("new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)

    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("renameat2 unavailable")

    monkeypatch.setattr(generator, "_rename_exchange_at", unavailable)
    with pytest.raises(RuntimeError, match="renameat2 unavailable"):
        generator.generate(tmp_path)
    _assert_installed(tmp_path, old)


def test_rollback_failure_retains_journal_then_next_generate_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("old")
    new = _outputs("new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    real_exchange = generator._rename_exchange_at
    exchange_calls = 0

    def fail_reverse(parent_fd: int, left: str, right: str) -> None:
        nonlocal exchange_calls
        exchange_calls += 1
        if exchange_calls == 2:
            raise RuntimeError("synthetic reverse exchange failure")
        real_exchange(parent_fd, left, right)

    def fail_after_exchange(name: str) -> None:
        if name == "after-publication-namespace":
            raise RuntimeError("primary synthetic publication failure")

    monkeypatch.setattr(generator, "_rename_exchange_at", fail_reverse)
    monkeypatch.setattr(generator, "_checkpoint", fail_after_exchange)
    with pytest.raises(
        RuntimeError, match="primary synthetic publication failure"
    ) as caught:
        generator.generate(tmp_path)
    assert any(
        "automatic publication recovery also failed" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    story = tmp_path / generator.STORY_ROOT
    assert (story / generator.JOURNAL_NAME).is_dir()
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.check(tmp_path)

    monkeypatch.setattr(generator, "_rename_exchange_at", real_exchange)
    monkeypatch.setattr(generator, "_checkpoint", lambda _name: None)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, new)


@pytest.mark.parametrize(
    ("checkpoint", "exit_code"),
    [
        ("after-journal-state-000-prepare", 72),
        ("after-publication-namespace", 73),
        ("after-journal-state-001-prepare", 75),
        ("after-committed-state", 74),
    ],
)
def test_real_process_crash_is_recovered_without_mixed_generation(
    checkpoint: str,
    exit_code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("old")
    new = _outputs("new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint=checkpoint,
        exit_code=exit_code,
    )
    assert completed.returncode == exit_code
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, new)


def test_interrupted_initial_journal_state_write_recovers_without_inference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("partial-journal")
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    real_write = os.write
    interrupted = False

    def short_then_fail(descriptor: int, content: bytes) -> int:
        nonlocal interrupted
        if not interrupted and b'"schema"' in content:
            interrupted = True
            real_write(descriptor, content[: max(1, len(content) // 2)])
            raise OSError("synthetic interrupted journal write")
        return real_write(descriptor, content)

    monkeypatch.setattr(os, "write", short_then_fail)
    with pytest.raises(OSError, match="interrupted journal write"):
        generator.generate(tmp_path)
    monkeypatch.setattr(os, "write", real_write)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, outputs)


@pytest.mark.parametrize(
    "checkpoint",
    [
        "after-bundle-cleanup-quarantine",
        "after-bundle-cleanup-deleting-state",
        "after-bundle-cleanup-baseline.json-quarantine",
        "after-bundle-cleanup-baseline.json-unlink",
        "after-bundle-cleanup-recorded-quarantine",
        "after-bundle-cleanup-recorded-rmdir",
        "after-bundle-cleanup-fixtures-quarantine",
        "after-bundle-cleanup-fixtures-rmdir",
        "after-bundle-cleanup-manifest-quarantine",
        "after-bundle-cleanup-manifest-unlink",
        "after-bundle-cleanup-root-quarantine",
        "after-bundle-cleanup-root-rmdir",
        "after-journal-cleanup-state-000-quarantine",
        "after-journal-cleanup-state-000-unlink",
        "after-journal-cleanup-root-quarantine",
        "after-journal-cleanup-root-rmdir",
    ],
)
def test_real_crash_during_destructive_bundle_cleanup_is_restartable(
    checkpoint: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("cleanup-old")
    new = _outputs("cleanup-new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint=checkpoint,
        exit_code=91,
    )
    assert completed.returncode == 91, completed.stderr
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, new)


@pytest.mark.parametrize(
    "checkpoint",
    [
        "after-legacy-manifest.json-quarantine",
        "after-legacy-fixtures-quarantine",
        "after-legacy-cleanup-deleting-state",
        "after-legacy-manifest-quarantine",
        "after-legacy-manifest-unlink",
        "after-legacy-fixture-baseline.json-quarantine",
        "after-legacy-fixture-baseline.json-unlink",
        "after-legacy-recorded-rmdir",
        "after-legacy-fixtures-root-rmdir",
    ],
)
def test_real_crash_during_legacy_quarantine_cleanup_is_restartable(
    checkpoint: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = _outputs("legacy")
    _install(tmp_path, outputs, monkeypatch)
    story = tmp_path / generator.STORY_ROOT
    legacy_manifest = b"synthetic exact legacy manifest\n"
    legacy_sha256 = hashlib.sha256(legacy_manifest).hexdigest()
    monkeypatch.setattr(generator, "LEGACY_MANIFEST_SHA256", legacy_sha256)
    (story / generator.LEGACY_MANIFEST_PATH.name).write_bytes(legacy_manifest)
    legacy_recorded = story / "fixtures/recorded"
    legacy_recorded.mkdir(parents=True)
    for fixture_name in generator.EXPECTED_FIXTURE_NAMES:
        legacy_recorded.joinpath(fixture_name).write_bytes(
            outputs[generator.FIXTURE_ROOT / fixture_name]
        )
    completed = _run_crashing_generate(
        tmp_path,
        outputs,
        checkpoint=checkpoint,
        exit_code=92,
        legacy_manifest_sha256=legacy_sha256,
    )
    assert completed.returncode == 92, completed.stderr
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, outputs)
    assert not (story / generator.LEGACY_MANIFEST_PATH.name).exists()
    assert not (story / "fixtures").exists()


def test_ancestor_swap_cannot_redirect_writes_from_captured_story_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    trusted = tmp_path / generator.STORY_ROOT
    trusted.mkdir(parents=True)
    replacement = tmp_path / "replacement-story"
    replacement.mkdir()
    (replacement / "sentinel").write_bytes(b"unchanged")
    captured = trusted.with_name("captured-st-1204")
    outputs = _outputs("captured")
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    real_open = os.open
    swapped = False

    def swapping_open(
        path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if not swapped and os.fsdecode(path) == "st-1204" and dir_fd is not None:
            trusted.rename(captured)
            replacement.rename(trusted)
            swapped = True
        return descriptor

    monkeypatch.setattr(os, "open", swapping_open)
    generator.generate(tmp_path)

    assert swapped is True
    assert (trusted / "sentinel").read_bytes() == b"unchanged"
    assert not (trusted / generator.GENERATED_ROOT.name).exists()
    for relative, content in outputs.items():
        below_story = relative.relative_to(generator.STORY_ROOT)
        assert (captured / below_story).read_bytes() == content


def test_same_byte_different_inode_installed_swap_is_restored_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("owned-old")
    new = _outputs("owned-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    generated = story / generator.GENERATED_ROOT.name
    displaced = story / "attacker-displaced-original"
    foreign_identity: tuple[int, int] | None = None

    def swap_after_revalidation(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-installed-revalidation" or foreign_identity is not None:
            return
        generated.rename(displaced)
        _write_bundle_directory(generated, old)
        metadata = generated.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_after_revalidation)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="exchanged previous ST-1204 bundle was not preserved",
    ):
        generator.generate(tmp_path)
    assert foreign_identity is not None
    assert (generated.stat().st_dev, generated.stat().st_ino) == foreign_identity
    assert displaced.is_dir()
    for relative, content in old.items():
        below_bundle = relative.relative_to(generator.GENERATED_ROOT)
        assert generated.joinpath(below_bundle).read_bytes() == content
    assert not (story / generator.JOURNAL_NAME).exists()


def test_same_uid_file_swap_after_quarantine_is_refused_without_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("file-old")
    new = _outputs("file-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-baseline.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_quarantined_file(name: str) -> None:
        nonlocal foreign_identity
        if name != "before-bundle-cleanup-baseline.json-unlink" or preserved.exists():
            return
        cleanup_root = next(story.glob(f"{generator.BUNDLE_CLEANUP_PREFIX}*"))
        tombstone = (
            cleanup_root
            / "fixtures/recorded"
            / generator._delete_tombstone_name("baseline.json")
        )
        tombstone.rename(preserved)
        tombstone.write_bytes(old[generator.FIXTURE_ROOT / "baseline.json"])
        metadata = tombstone.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_quarantined_file)
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    assert foreign_identity is not None
    cleanup_root = next(story.glob(f"{generator.BUNDLE_CLEANUP_PREFIX}*"))
    foreign = (
        cleanup_root
        / "fixtures/recorded"
        / generator._delete_tombstone_name("baseline.json")
    )
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert preserved.read_bytes() == old[generator.FIXTURE_ROOT / "baseline.json"]


def test_same_uid_old_stage_swap_before_quarantine_is_restored_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("stage-old")
    new = _outputs("stage-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-stage"
    foreign_identity: tuple[int, int] | None = None

    def swap_stage(name: str) -> None:
        nonlocal foreign_identity
        if name != "before-bundle-cleanup-quarantine" or preserved.exists():
            return
        stage = story / generator.STAGE_NAME
        stage.rename(preserved)
        _write_bundle_directory(stage, old)
        metadata = stage.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_stage)
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    stage = story / generator.STAGE_NAME
    assert foreign_identity is not None
    assert (stage.stat().st_dev, stage.stat().st_ino) == foreign_identity
    assert preserved.is_dir()
    assert not any(story.glob(f"{generator.BUNDLE_CLEANUP_PREFIX}*"))


def test_same_uid_directory_swap_after_quarantine_is_refused_without_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("directory-old")
    new = _outputs("directory-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-recorded"
    foreign_identity: tuple[int, int] | None = None

    def swap_quarantined_directory(name: str) -> None:
        nonlocal foreign_identity
        if name != "before-bundle-cleanup-recorded-rmdir" or preserved.exists():
            return
        cleanup_root = next(story.glob(f"{generator.BUNDLE_CLEANUP_PREFIX}*"))
        fixtures = cleanup_root / "fixtures"
        tombstone = fixtures / generator._delete_tombstone_name("recorded")
        tombstone.rename(preserved)
        tombstone.mkdir()
        metadata = tombstone.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_quarantined_directory)
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    assert foreign_identity is not None
    cleanup_root = next(story.glob(f"{generator.BUNDLE_CLEANUP_PREFIX}*"))
    foreign = cleanup_root / "fixtures" / generator._delete_tombstone_name("recorded")
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert preserved.is_dir()


def test_same_uid_legacy_manifest_swap_is_restored_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("legacy-swap")
    _install(tmp_path, outputs, monkeypatch)
    story = tmp_path / generator.STORY_ROOT
    legacy_manifest = b"synthetic owned legacy manifest\n"
    legacy_sha256 = hashlib.sha256(legacy_manifest).hexdigest()
    monkeypatch.setattr(generator, "LEGACY_MANIFEST_SHA256", legacy_sha256)
    manifest = story / generator.LEGACY_MANIFEST_PATH.name
    manifest.write_bytes(legacy_manifest)
    legacy_recorded = story / "fixtures/recorded"
    legacy_recorded.mkdir(parents=True)
    for fixture_name in generator.EXPECTED_FIXTURE_NAMES:
        legacy_recorded.joinpath(fixture_name).write_bytes(
            outputs[generator.FIXTURE_ROOT / fixture_name]
        )
    preserved = story / "preserved-owned-legacy-manifest"
    foreign_identity: tuple[int, int] | None = None

    def swap_manifest(name: str) -> None:
        nonlocal foreign_identity
        if name != "before-legacy-manifest.json-quarantine" or preserved.exists():
            return
        manifest.rename(preserved)
        manifest.write_bytes(legacy_manifest)
        metadata = manifest.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_manifest)
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    assert foreign_identity is not None
    assert (manifest.stat().st_dev, manifest.stat().st_ino) == foreign_identity
    assert preserved.read_bytes() == legacy_manifest
    assert not any(story.glob(f"{generator.LEGACY_CLEANUP_PREFIX}*.manifest"))


def test_final_entry_swap_replaces_symlink_not_external_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("fresh")
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"unchanged")

    def swap_final(name: str) -> None:
        if name == "before-publication":
            story = tmp_path / generator.STORY_ROOT
            (story / generator.GENERATED_ROOT.name).symlink_to(
                outside, target_is_directory=True
            )

    monkeypatch.setattr(generator, "_checkpoint", swap_final)
    with pytest.raises((OSError, RuntimeError)):
        generator.generate(tmp_path)
    assert (outside / "sentinel").read_bytes() == b"unchanged"
    assert (
        tmp_path / generator.STORY_ROOT / generator.GENERATED_ROOT.name
    ).is_symlink()


def test_late_fresh_destination_directory_is_preserved_by_noreplace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("fresh-collision")
    monkeypatch.setattr(generator, "build_outputs", lambda _root: outputs)
    collision_identity: tuple[int, int] | None = None

    def create_collision(name: str) -> None:
        nonlocal collision_identity
        if name != "before-publication" or collision_identity is not None:
            return
        collision = tmp_path / generator.GENERATED_ROOT
        collision.mkdir()
        metadata = collision.stat()
        collision_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", create_collision)
    with pytest.raises(RuntimeError, match="File exists"):
        generator.generate(tmp_path)
    collision = tmp_path / generator.GENERATED_ROOT
    assert collision_identity is not None
    assert (collision.stat().st_dev, collision.stat().st_ino) == collision_identity
    assert not any(collision.iterdir())


def test_exact_orphan_stage_is_not_owned_by_bytes_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed = _outputs("installed")
    orphan = _outputs("orphan")
    _install(tmp_path, installed, monkeypatch)
    story = tmp_path / generator.STORY_ROOT
    stage = story / generator.STAGE_NAME
    _write_bundle_directory(stage, orphan)
    stage_identity = stage.stat().st_dev, stage.stat().st_ino
    monkeypatch.setattr(generator, "build_outputs", lambda _root: orphan)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="no durable ownership record",
    ):
        generator.generate(tmp_path)
    assert (stage.stat().st_dev, stage.stat().st_ino) == stage_identity
    assert (story / generator.GENERATED_ROOT.name / "manifest.json").read_bytes() == (
        installed[generator.MANIFEST_PATH]
    )


def test_unbound_cleanup_quarantine_is_preserved_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("installed")
    _install(tmp_path, outputs, monkeypatch)
    story = tmp_path / generator.STORY_ROOT
    unbound = story / f"{generator.BUNDLE_CLEANUP_PREFIX}{'1' * 32}"
    unbound.mkdir()
    (unbound / "sentinel").write_bytes(b"preserve")
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="unbound ST-1204 cleanup entries",
    ):
        generator.generate(tmp_path)
    assert (unbound / "sentinel").read_bytes() == b"preserve"


def test_reappearance_before_cleanup_complete_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("reappear-old")
    new = _outputs("reappear-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    injected = False

    def reappear(name: str) -> None:
        nonlocal injected
        if name == "before-cleanup-complete-verification" and not injected:
            (story / generator.LEGACY_MANIFEST_PATH.name).write_bytes(b"foreign\n")
            injected = True

    monkeypatch.setattr(generator, "_checkpoint", reappear)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="cleanup inventory is not closed",
    ):
        generator.generate(tmp_path)
    assert (story / generator.LEGACY_MANIFEST_PATH.name).read_bytes() == b"foreign\n"
    assert (story / generator.JOURNAL_NAME).is_dir()


@pytest.mark.parametrize(
    "stale_name",
    [
        generator.STAGE_NAME,
        generator.JOURNAL_PREPARING_NAME,
    ],
)
def test_owned_stale_prepublication_and_cleanup_entries_recover(
    stale_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    story = tmp_path / generator.STORY_ROOT
    story.mkdir(parents=True)
    (story / stale_name).mkdir()
    outputs = _outputs("recovered")
    _install(tmp_path, outputs, monkeypatch)
    _assert_installed(tmp_path, outputs)


def _create_terminal_cleanup_tombstone(
    root: Path,
    *,
    phase: str,
    previous_digest: str | None,
    next_digest: str,
) -> None:
    story_fd = generator._acquire_story_lock(root, exclusive=True, create=False)
    primary: BaseException | None = None
    try:
        installed = generator._read_bundle_capture_at(
            story_fd, generator.GENERATED_ROOT.name, allow_missing=False
        )
        assert installed is not None
        installed_identity = installed[1]["."]
        state = generator._new_journal_state(
            mode="REPLACE" if previous_digest is not None else "FRESH",
            previous_digest=previous_digest,
            next_digest=next_digest,
            previous_identity=(
                installed_identity if previous_digest is not None else None
            ),
            next_identity=installed_identity,
            publication_phase=phase,
        )
        generator._create_journal_at(story_fd, state)
        state = generator._write_journal_update_at(
            story_fd, state, cleanup_phase="CLEANUP_COMPLETE"
        )
        journal_fd = generator._open_directory_at(
            story_fd, generator.JOURNAL_NAME, label="test journal"
        )
        try:
            journal_identity = generator._entry_identity(os.fstat(journal_fd))
        finally:
            os.close(journal_fd)
        transaction_id = state["transaction_id"]
        assert isinstance(transaction_id, str)
        cleanup_name = generator._journal_cleanup_entry_name(
            transaction_id, journal_identity
        )
        generator._rename_noreplace_at(
            story_fd,
            generator.JOURNAL_NAME,
            cleanup_name,
        )
        os.fsync(story_fd)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        generator._release_story_lock(story_fd, primary)


def test_committed_cleanup_tombstone_requires_exact_new_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("committed")
    _install(tmp_path, outputs, monkeypatch)
    next_digest = hashlib.sha256(outputs[generator.MANIFEST_PATH]).hexdigest()
    _create_terminal_cleanup_tombstone(
        tmp_path,
        phase="COMMITTED",
        previous_digest=None,
        next_digest=next_digest,
    )
    story = tmp_path / generator.STORY_ROOT
    fixture = story / generator.GENERATED_ROOT.name / "fixtures/recorded/baseline.json"
    fixture.write_bytes(b"tampered\n")

    with pytest.raises(
        RuntimeError,
        match="publication cleanup journal does not match terminal bundle",
    ):
        generator.generate(tmp_path)
    assert any(
        entry.name.startswith(generator.JOURNAL_CLEANUP_NAME)
        for entry in story.iterdir()
    )


def test_rolled_back_cleanup_tombstone_verifies_then_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = _outputs("previous")
    next_outputs = _outputs("next")
    _install(tmp_path, previous, monkeypatch)
    previous_digest = hashlib.sha256(previous[generator.MANIFEST_PATH]).hexdigest()
    next_digest = hashlib.sha256(next_outputs[generator.MANIFEST_PATH]).hexdigest()
    _create_terminal_cleanup_tombstone(
        tmp_path,
        phase="ROLLED_BACK",
        previous_digest=previous_digest,
        next_digest=next_digest,
    )

    monkeypatch.setattr(generator, "build_outputs", lambda _root: next_outputs)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, next_outputs)


def test_malformed_cleanup_tombstone_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("installed")
    _install(tmp_path, outputs, monkeypatch)
    story = tmp_path / generator.STORY_ROOT
    transaction_id = "0" * 31 + "1"
    preparing = story / f"{generator.JOURNAL_CLEANUP_NAME}preparing"
    preparing.mkdir()
    identity = preparing.stat()
    cleanup = story / generator._journal_cleanup_entry_name(
        transaction_id, (identity.st_dev, identity.st_ino)
    )
    preparing.rename(cleanup)
    (cleanup / generator.JOURNAL_STATE_NAME).write_bytes(b"{}\n")

    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="publication journal fields drifted",
    ):
        generator.generate(tmp_path)
    assert cleanup.is_dir()
    assert (cleanup / generator.JOURNAL_STATE_NAME).read_bytes() == b"{}\n"


def test_malformed_stale_journal_fails_closed_and_preserves_external_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    story = tmp_path / generator.STORY_ROOT
    story.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "sentinel").write_bytes(b"unchanged")
    (story / generator.JOURNAL_NAME).symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: _outputs("new"))
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    assert (outside / "sentinel").read_bytes() == b"unchanged"


def test_shared_and_exclusive_locks_fail_closed_on_contention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("locked")
    _install(tmp_path, outputs, monkeypatch)

    exclusive = generator._acquire_story_lock(tmp_path, exclusive=True, create=False)
    try:
        with pytest.raises(RuntimeError, match="another ST-1204"):
            generator.check(tmp_path)
    finally:
        generator._release_story_lock(exclusive, None)

    shared = generator._acquire_story_lock(tmp_path, exclusive=False, create=False)
    try:
        with pytest.raises(RuntimeError, match="another ST-1204"):
            generator.generate(tmp_path)
    finally:
        generator._release_story_lock(shared, None)


def test_check_cannot_accept_intermediate_namespace_during_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("old")
    new = _outputs("new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    exchanged = threading.Event()
    release = threading.Event()
    failures: list[BaseException] = []

    def pause_after_exchange(name: str) -> None:
        if name == "after-publication-namespace":
            exchanged.set()
            if not release.wait(timeout=10):
                raise RuntimeError("concurrency test timed out")

    def generate_in_thread() -> None:
        try:
            generator.generate(tmp_path)
        except BaseException as exc:
            failures.append(exc)

    monkeypatch.setattr(generator, "_checkpoint", pause_after_exchange)
    thread = threading.Thread(target=generate_in_thread)
    thread.start()
    assert exchanged.wait(timeout=10)
    try:
        with pytest.raises(RuntimeError, match="another ST-1204"):
            generator.check(tmp_path)
    finally:
        release.set()
        thread.join(timeout=10)
    assert not thread.is_alive()
    assert failures == []
    _assert_installed(tmp_path, new)


@pytest.mark.parametrize("entry_kind", ["hardlink", "fifo"])
def test_multiply_linked_and_special_fixture_entries_fail_closed(
    entry_kind: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outputs = _outputs("hostile")
    _install(tmp_path, outputs, monkeypatch)
    baseline = tmp_path / generator.FIXTURE_ROOT / "baseline.json"
    baseline.unlink()
    if entry_kind == "hardlink":
        outside = tmp_path / "outside.json"
        outside.write_bytes(b"outside")
        os.link(outside, baseline)
    else:
        os.mkfifo(baseline)
    with pytest.raises(RuntimeError, match="one-link regular file"):
        generator.check(tmp_path)
