"""Crash, fault, confinement, and concurrency tests for ST-1204 publication."""

from __future__ import annotations

import hashlib
import json
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
    story_fd = generator._acquire_story_lock(root, exclusive=False, create=False)
    primary: BaseException | None = None
    try:
        generator._assert_no_pending_at(story_fd)
    except BaseException as exc:
        primary = exc
        raise
    finally:
        generator._release_story_lock(story_fd, primary)


def _write_bundle_directory(destination: Path, outputs: dict[Path, bytes]) -> None:
    destination.mkdir()
    for relative, content in outputs.items():
        below_bundle = relative.relative_to(generator.GENERATED_ROOT)
        target = destination / below_bundle
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)


def _terminal_cleanup_directory(story: Path) -> Path:
    candidates = [
        entry
        for entry in story.iterdir()
        if entry.name.startswith(generator.JOURNAL_CLEANUP_NAME)
    ]
    assert len(candidates) == 1
    return candidates[0]


def _replace_with_byte_identical_inode(
    source: Path, preserved: Path
) -> tuple[int, int]:
    content = source.read_bytes()
    source.rename(preserved)
    source.write_bytes(content)
    metadata = source.stat()
    return metadata.st_dev, metadata.st_ino


def _clone_journal_directory(source: Path, destination: Path) -> None:
    destination.mkdir()
    for entry in source.iterdir():
        assert entry.is_file()
        destination.joinpath(entry.name).write_bytes(entry.read_bytes())


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


def test_initial_journal_prepare_crash_preserves_unbound_nonempty_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("initial-journal-old")
    new = _outputs("initial-journal-new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint="after-journal-state-000-prepare",
        exit_code=72,
    )
    assert completed.returncode == 72
    story = tmp_path / generator.STORY_ROOT
    stage = story / generator.STAGE_NAME
    stage_identity = generator._stat_signature(stage.lstat())
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="no invocation ownership inventory",
    ):
        generator.generate(tmp_path)
    assert generator._stat_signature(stage.lstat()) == stage_identity
    for relative, content in old.items():
        assert (tmp_path / relative).read_bytes() == content


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
        "after-journal-cleanup-tombstone",
        "after-journal-cleanup-state-000-quarantine",
        "after-journal-cleanup-state-000-unlink",
        "after-journal-cleanup-root-quarantine",
    ],
)
def test_crashed_terminal_journal_cleanup_is_preserved_and_refused(
    checkpoint: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("terminal-crash-old")
    new = _outputs("terminal-crash-new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint=checkpoint,
        exit_code=96,
    )
    assert completed.returncode == 96, completed.stderr
    story = tmp_path / generator.STORY_ROOT
    cleanup_entries = [
        entry
        for entry in story.iterdir()
        if entry.name.startswith(generator.JOURNAL_CLEANUP_NAME)
        or entry.name.startswith(
            f"{generator.DELETE_TOMBSTONE_PREFIX}{generator.JOURNAL_CLEANUP_NAME}"
        )
    ]
    assert len(cleanup_entries) == 1
    cleanup_entry = cleanup_entries[0]
    before_identity = generator._stat_signature(cleanup_entry.lstat())
    before_names = sorted(path.name for path in cleanup_entry.iterdir())
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="no durable state identity inventory",
    ):
        generator.generate(tmp_path)
    assert generator._stat_signature(cleanup_entry.lstat()) == before_identity
    assert sorted(path.name for path in cleanup_entry.iterdir()) == before_names
    for relative, content in new.items():
        assert (tmp_path / relative).read_bytes() == content


def test_crash_after_terminal_journal_root_removal_needs_no_recovery_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("terminal-root-old")
    new = _outputs("terminal-root-new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint="after-journal-cleanup-root-rmdir",
        exit_code=97,
    )
    assert completed.returncode == 97, completed.stderr
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, new)


def test_restart_does_not_infer_byte_identical_journal_state_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("restart-state-old")
    new = _outputs("restart-state-new")
    _install(tmp_path, old, monkeypatch)
    completed = _run_crashing_generate(
        tmp_path,
        new,
        checkpoint="after-journal-cleanup-tombstone",
        exit_code=98,
    )
    assert completed.returncode == 98, completed.stderr
    story = tmp_path / generator.STORY_ROOT
    cleanup = _terminal_cleanup_directory(story)
    state = cleanup / generator.JOURNAL_STATE_NAME
    preserved = story / "preserved-crashed-journal-state-000.json"
    foreign_identity = _replace_with_byte_identical_inode(state, preserved)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="no durable state identity inventory",
    ):
        generator.generate(tmp_path)
    assert (state.stat().st_dev, state.stat().st_ino) == foreign_identity
    assert state.read_bytes() == preserved.read_bytes()


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


def test_byte_identical_journal_state_swap_after_root_move_is_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("journal-state-old")
    new = _outputs("journal-state-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-journal-state-000.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_state(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-journal-cleanup-tombstone" or preserved.exists():
            return
        state = _terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME
        foreign_identity = _replace_with_byte_identical_inode(state, preserved)

    monkeypatch.setattr(generator, "_checkpoint", swap_state)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="state identity inventory drifted",
    ):
        generator.generate(tmp_path)
    foreign = _terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME
    assert foreign_identity is not None
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert preserved.read_bytes() == foreign.read_bytes()


def test_active_journal_state_signature_is_captured_before_commit_checkpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("active-state-old")
    new = _outputs("active-state-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-active-journal-state.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_final_committed_state(name: str) -> None:
        nonlocal foreign_identity
        if not name.startswith("after-journal-state-") or not name.endswith("-commit"):
            return
        journal = story / generator.JOURNAL_NAME
        if not journal.is_dir() or preserved.exists():
            return
        states = sorted(journal.glob("state.*.json"))
        latest = json.loads(states[-1].read_bytes())
        if latest["cleanup_phase"] != "CLEANUP_COMPLETE":
            return
        foreign_identity = _replace_with_byte_identical_inode(states[-1], preserved)

    monkeypatch.setattr(generator, "_checkpoint", swap_final_committed_state)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match=(
            "active publication journal (?:state identity inventory drifted|"
            "directory signature changed)"
        ),
    ):
        generator.generate(tmp_path)
    journal = story / generator.JOURNAL_NAME
    assert foreign_identity is not None
    foreign = sorted(journal.glob("state.*.json"))[-1]
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert foreign.read_bytes() == preserved.read_bytes()


def test_active_journal_swap_and_commit_checkpoint_failure_never_recaptures_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("active-state-fault-old")
    new = _outputs("active-state-fault-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-active-journal-state-with-fault.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_state_then_fail(name: str) -> None:
        nonlocal foreign_identity
        if not name.startswith("after-journal-state-") or not name.endswith("-commit"):
            return
        journal = story / generator.JOURNAL_NAME
        if not journal.is_dir() or preserved.exists():
            return
        states = sorted(journal.glob("state.*.json"))
        latest = json.loads(states[-1].read_bytes())
        if latest["cleanup_phase"] != "CLEANUP_COMPLETE":
            return
        foreign_identity = _replace_with_byte_identical_inode(states[-1], preserved)
        raise RuntimeError("synthetic checkpoint failure after journal replacement")

    monkeypatch.setattr(generator, "_checkpoint", swap_state_then_fail)
    with pytest.raises(
        RuntimeError,
        match="synthetic checkpoint failure after journal replacement",
    ) as caught:
        generator.generate(tmp_path)
    assert any(
        "automatic publication recovery also failed" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    journal = story / generator.JOURNAL_NAME
    assert foreign_identity is not None
    foreign = sorted(journal.glob("state.*.json"))[-1]
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert foreign.read_bytes() == preserved.read_bytes()


def test_new_active_journal_root_swap_and_publish_checkpoint_failure_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("active-root-publish-fault-old")
    new = _outputs("active-root-publish-fault-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-new-active-journal-root"
    foreign_identity: tuple[int, int] | None = None

    def swap_root_then_fail(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-journal-publish" or preserved.exists():
            return
        journal = story / generator.JOURNAL_NAME
        journal.rename(preserved)
        _clone_journal_directory(preserved, journal)
        metadata = journal.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino
        raise RuntimeError(
            "synthetic checkpoint failure after journal root replacement"
        )

    monkeypatch.setattr(generator, "_checkpoint", swap_root_then_fail)
    with pytest.raises(
        RuntimeError,
        match="synthetic checkpoint failure after journal root replacement",
    ) as caught:
        generator.generate(tmp_path)
    assert any(
        "automatic publication recovery also failed" in note
        for note in getattr(caught.value, "__notes__", ())
    )
    journal = story / generator.JOURNAL_NAME
    assert foreign_identity is not None
    assert (journal.stat().st_dev, journal.stat().st_ino) == foreign_identity
    assert preserved.is_dir()
    assert sorted(item.read_bytes() for item in journal.iterdir()) == sorted(
        item.read_bytes() for item in preserved.iterdir()
    )
    for relative, content in old.items():
        assert (tmp_path / relative).read_bytes() == content


def test_whole_active_journal_root_clone_swap_is_preserved_before_terminal_move(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("active-root-old")
    new = _outputs("active-root-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-active-journal-root"
    foreign_identity: tuple[int, int] | None = None

    def swap_terminal_root(name: str) -> None:
        nonlocal foreign_identity
        if name != "before-cleanup-complete-verification" or preserved.exists():
            return
        journal = story / generator.JOURNAL_NAME
        if not journal.is_dir():
            return
        states = sorted(journal.glob("state.*.json"))
        if not states:
            return
        latest = json.loads(states[-1].read_bytes())
        if latest["cleanup_phase"] != "CLEANUP_COMPLETE":
            return
        journal.rename(preserved)
        _clone_journal_directory(preserved, journal)
        metadata = journal.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_terminal_root)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="active publication journal directory signature changed",
    ):
        generator.generate(tmp_path)
    journal = story / generator.JOURNAL_NAME
    assert foreign_identity is not None
    assert (journal.stat().st_dev, journal.stat().st_ino) == foreign_identity
    assert preserved.is_dir()
    assert sorted(item.read_bytes() for item in journal.iterdir()) == sorted(
        item.read_bytes() for item in preserved.iterdir()
    )


@pytest.mark.parametrize("mutation", ["mode", "mtime"])
def test_journal_state_full_signature_drift_after_root_move_is_not_deleted(
    mutation: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs(f"journal-signature-{mutation}-old")
    new = _outputs(f"journal-signature-{mutation}-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    state_identity: tuple[int, int] | None = None
    state_content: bytes | None = None

    def mutate_signature(name: str) -> None:
        nonlocal state_content, state_identity
        if name != "after-journal-cleanup-tombstone" or state_identity is not None:
            return
        state = _terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME
        state_content = state.read_bytes()
        if mutation == "mode":
            state.chmod(0o600)
        else:
            metadata = state.stat()
            os.utime(
                state,
                ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
            )
        metadata = state.stat()
        state_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", mutate_signature)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="state identity inventory drifted",
    ):
        generator.generate(tmp_path)
    state = _terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME
    assert state_identity is not None
    assert state_content is not None
    assert (state.stat().st_dev, state.stat().st_ino) == state_identity
    assert state.read_bytes() == state_content


def test_journal_state_signature_drift_immediately_before_unlink_is_not_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("journal-pre-unlink-signature-old")
    new = _outputs("journal-pre-unlink-signature-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    mutated: Path | None = None
    mutated_identity: tuple[int, int] | None = None
    mutated_content: bytes | None = None

    def mutate_signature(name: str) -> None:
        nonlocal mutated, mutated_content, mutated_identity
        if name != "before-journal-cleanup-state-000-unlink" or mutated is not None:
            return
        cleanup = _terminal_cleanup_directory(story)
        mutated = cleanup / generator._delete_tombstone_name(
            generator.JOURNAL_STATE_NAME
        )
        mutated_content = mutated.read_bytes()
        mutated.chmod(0o600)
        metadata = mutated.stat()
        mutated_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", mutate_signature)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="signature",
    ):
        generator.generate(tmp_path)
    assert mutated is not None
    assert mutated.exists()
    assert mutated_identity is not None
    assert mutated_content is not None
    assert (mutated.stat().st_dev, mutated.stat().st_ino) == mutated_identity
    assert mutated.read_bytes() == mutated_content


def test_journal_state_signature_drift_immediately_before_quarantine_is_not_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("journal-pre-quarantine-signature-old")
    new = _outputs("journal-pre-quarantine-signature-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    mutated: Path | None = None
    mutated_identity: tuple[int, int] | None = None

    def mutate_signature(name: str) -> None:
        nonlocal mutated, mutated_identity
        if name != "before-journal-cleanup-state-000-quarantine" or mutated is not None:
            return
        mutated = _terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME
        mutated.chmod(0o600)
        metadata = mutated.stat()
        mutated_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", mutate_signature)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="quarantine identity drifted",
    ):
        generator.generate(tmp_path)
    assert mutated is not None
    assert mutated.exists()
    assert mutated_identity is not None
    assert (mutated.stat().st_dev, mutated.stat().st_ino) == mutated_identity


def test_journal_root_signature_drift_immediately_before_rmdir_is_not_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("journal-root-pre-rmdir-signature-old")
    new = _outputs("journal-root-pre-rmdir-signature-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    mutated: Path | None = None
    mutated_identity: tuple[int, int] | None = None

    def mutate_signature(name: str) -> None:
        nonlocal mutated, mutated_identity
        if name != "before-journal-cleanup-root-rmdir" or mutated is not None:
            return
        mutated = next(
            entry
            for entry in story.iterdir()
            if entry.name.startswith(
                f"{generator.DELETE_TOMBSTONE_PREFIX}{generator.JOURNAL_CLEANUP_NAME}"
            )
        )
        mutated.chmod(0o755)
        metadata = mutated.stat()
        mutated_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", mutate_signature)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="directory signature changed",
    ):
        generator.generate(tmp_path)
    assert mutated is not None
    assert mutated.is_dir()
    assert mutated_identity is not None
    assert (mutated.stat().st_dev, mutated.stat().st_ino) == mutated_identity


def test_journal_root_signature_drift_before_quarantine_is_not_deleted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old = _outputs("journal-root-pre-quarantine-signature-old")
    new = _outputs("journal-root-pre-quarantine-signature-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    mutated: Path | None = None
    mutated_identity: tuple[int, int] | None = None

    def mutate_signature(name: str) -> None:
        nonlocal mutated, mutated_identity
        if name != "before-journal-cleanup-root-quarantine" or mutated is not None:
            return
        mutated = _terminal_cleanup_directory(story)
        mutated.chmod(0o755)
        metadata = mutated.stat()
        mutated_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", mutate_signature)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="quarantine identity drifted",
    ):
        generator.generate(tmp_path)
    assert mutated is not None
    assert mutated.is_dir()
    assert mutated_identity is not None
    assert (mutated.stat().st_dev, mutated.stat().st_ino) == mutated_identity


def test_terminal_journal_preparing_reappearance_refuses_before_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("journal-temp-old")
    new = _outputs("journal-temp-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    injected: Path | None = None

    def add_preparing_state(name: str) -> None:
        nonlocal injected
        if name != "after-journal-cleanup-tombstone" or injected is not None:
            return
        cleanup = _terminal_cleanup_directory(story)
        source = cleanup / generator.JOURNAL_STATE_NAME
        injected = cleanup / f"{generator.JOURNAL_STATE_NAME}.preparing"
        injected.write_bytes(source.read_bytes())

    monkeypatch.setattr(generator, "_checkpoint", add_preparing_state)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="publication journal has unknown entries",
    ):
        generator.generate(tmp_path)
    assert injected is not None
    assert injected.is_file()
    assert (_terminal_cleanup_directory(story) / generator.JOURNAL_STATE_NAME).is_file()


def test_byte_identical_journal_tombstone_swap_is_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("journal-quarantine-old")
    new = _outputs("journal-quarantine-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-journal-tombstone-000.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_tombstone(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-journal-cleanup-state-000-quarantine" or preserved.exists():
            return
        tombstone = _terminal_cleanup_directory(
            story
        ) / generator._delete_tombstone_name(generator.JOURNAL_STATE_NAME)
        foreign_identity = _replace_with_byte_identical_inode(tombstone, preserved)

    monkeypatch.setattr(generator, "_checkpoint", swap_tombstone)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="changed before unlink",
    ):
        generator.generate(tmp_path)
    foreign = _terminal_cleanup_directory(story) / generator._delete_tombstone_name(
        generator.JOURNAL_STATE_NAME
    )
    assert foreign_identity is not None
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert preserved.read_bytes() == foreign.read_bytes()


def test_byte_identical_last_journal_state_swap_after_prefix_cleanup_is_not_deleted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("journal-last-old")
    new = _outputs("journal-last-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-owned-journal-last.json"
    last_name: str | None = None
    foreign_identity: tuple[int, int] | None = None

    def swap_last_state(name: str) -> None:
        nonlocal foreign_identity, last_name
        if name not in {
            "after-journal-cleanup-tombstone",
            "after-journal-cleanup-state-000-unlink",
        }:
            return
        cleanup = _terminal_cleanup_directory(story)
        if name == "after-journal-cleanup-tombstone":
            last_name = sorted(
                entry.name
                for entry in cleanup.iterdir()
                if entry.name.startswith(generator.JOURNAL_STATE_PREFIX)
                and entry.name.endswith(".json")
            )[-1]
            assert last_name != generator.JOURNAL_STATE_NAME
        elif name == "after-journal-cleanup-state-000-unlink":
            assert last_name is not None
            foreign_identity = _replace_with_byte_identical_inode(
                cleanup / last_name,
                preserved,
            )

    monkeypatch.setattr(generator, "_checkpoint", swap_last_state)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="identity is unowned",
    ):
        generator.generate(tmp_path)
    assert last_name is not None
    foreign = _terminal_cleanup_directory(story) / last_name
    assert foreign_identity is not None
    assert (foreign.stat().st_dev, foreign.stat().st_ino) == foreign_identity
    assert preserved.read_bytes() == foreign.read_bytes()


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


def test_detected_partial_stage_root_replacement_is_preserved_not_reowned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("partial-root-old")
    new = _outputs("partial-root-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-invocation-stage-root"
    foreign_identity: tuple[int, int] | None = None

    def swap_stage_root(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-stage-directory" or preserved.exists():
            return
        stage = story / generator.STAGE_NAME
        stage.rename(preserved)
        stage.mkdir()
        metadata = stage.stat()
        foreign_identity = metadata.st_dev, metadata.st_ino

    monkeypatch.setattr(generator, "_checkpoint", swap_stage_root)
    with pytest.raises(generator.PublicationRecoveryRequired):
        generator.generate(tmp_path)
    stage = story / generator.STAGE_NAME
    assert foreign_identity is not None
    assert (stage.stat().st_dev, stage.stat().st_ino) == foreign_identity
    assert preserved.is_dir()
    for relative, content in old.items():
        assert (tmp_path / relative).read_bytes() == content


def test_byte_identical_partial_stage_file_replacement_is_preserved_not_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = _outputs("partial-file-old")
    new = _outputs("partial-file-new")
    _install(tmp_path, old, monkeypatch)
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    story = tmp_path / generator.STORY_ROOT
    preserved = story / "preserved-invocation-stage-manifest.json"
    foreign_identity: tuple[int, int] | None = None

    def swap_staged_manifest(name: str) -> None:
        nonlocal foreign_identity
        if name != "after-staged-manifest" or preserved.exists():
            return
        manifest = story / generator.STAGE_NAME / "manifest.json"
        foreign_identity = _replace_with_byte_identical_inode(manifest, preserved)

    monkeypatch.setattr(generator, "_checkpoint", swap_staged_manifest)
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="partial staged manifest invocation identity drifted",
    ):
        generator.generate(tmp_path)
    manifest = story / generator.STAGE_NAME / "manifest.json"
    assert foreign_identity is not None
    assert (manifest.stat().st_dev, manifest.stat().st_ino) == foreign_identity
    assert manifest.read_bytes() == preserved.read_bytes()
    for relative, content in old.items():
        assert (tmp_path / relative).read_bytes() == content


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
        trust = generator._create_journal_at(story_fd, state)
        state = generator._write_journal_update_at(
            story_fd, state, trust, cleanup_phase="CLEANUP_COMPLETE"
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


def test_committed_cleanup_tombstone_without_identity_inventory_is_preserved(
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
        generator.PublicationRecoveryRequired,
        match="no durable state identity inventory",
    ):
        generator.generate(tmp_path)
    assert any(
        entry.name.startswith(generator.JOURNAL_CLEANUP_NAME)
        for entry in story.iterdir()
    )


def test_rolled_back_cleanup_tombstone_without_identity_inventory_is_preserved(
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
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="no durable state identity inventory",
    ):
        generator.generate(tmp_path)
    story = tmp_path / generator.STORY_ROOT
    assert any(
        entry.name.startswith(generator.JOURNAL_CLEANUP_NAME)
        for entry in story.iterdir()
    )


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
        match="no durable state identity inventory",
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


def test_bundle_acceptance_revalidates_fixtures_name_against_open_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("nested-fixtures")
    _install(tmp_path, outputs, monkeypatch)
    fixtures = tmp_path / generator.GENERATED_ROOT / "fixtures"
    preserved = tmp_path / generator.STORY_ROOT / "preserved-bundle-fixtures"
    foreign_identity: tuple[int, int] | None = None
    real_read = generator._read_regular_capture_at

    def swap_fixtures_on_manifest_read(
        parent_fd: int,
        name: str,
        *,
        label: str,
        maximum_bytes: int = generator.MAX_GENERATED_BYTES,
    ) -> tuple[bytes, tuple[int, int]]:
        nonlocal foreign_identity
        result = real_read(
            parent_fd,
            name,
            label=label,
            maximum_bytes=maximum_bytes,
        )
        if label == "generated manifest" and foreign_identity is None:
            fixtures.rename(preserved)
            recorded = fixtures / "recorded"
            recorded.mkdir(parents=True)
            for fixture_name in generator.EXPECTED_FIXTURE_NAMES:
                recorded.joinpath(fixture_name).write_bytes(
                    preserved.joinpath("recorded", fixture_name).read_bytes()
                )
            metadata = fixtures.stat()
            foreign_identity = metadata.st_dev, metadata.st_ino
        return result

    monkeypatch.setattr(
        generator, "_read_regular_capture_at", swap_fixtures_on_manifest_read
    )
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="fixture directory identity changed",
    ):
        generator.check(tmp_path)
    assert foreign_identity is not None
    assert (fixtures.stat().st_dev, fixtures.stat().st_ino) == foreign_identity
    assert preserved.is_dir()


def test_bundle_acceptance_revalidates_recorded_name_against_open_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outputs = _outputs("nested-recorded")
    _install(tmp_path, outputs, monkeypatch)
    recorded = tmp_path / generator.FIXTURE_ROOT
    preserved = tmp_path / generator.STORY_ROOT / "preserved-bundle-recorded"
    foreign_identity: tuple[int, int] | None = None
    real_read = generator._read_regular_capture_at

    def swap_recorded_on_manifest_read(
        parent_fd: int,
        name: str,
        *,
        label: str,
        maximum_bytes: int = generator.MAX_GENERATED_BYTES,
    ) -> tuple[bytes, tuple[int, int]]:
        nonlocal foreign_identity
        result = real_read(
            parent_fd,
            name,
            label=label,
            maximum_bytes=maximum_bytes,
        )
        if label == "generated manifest" and foreign_identity is None:
            recorded.rename(preserved)
            recorded.mkdir()
            for fixture_name in generator.EXPECTED_FIXTURE_NAMES:
                recorded.joinpath(fixture_name).write_bytes(
                    preserved.joinpath(fixture_name).read_bytes()
                )
            metadata = recorded.stat()
            foreign_identity = metadata.st_dev, metadata.st_ino
        return result

    monkeypatch.setattr(
        generator, "_read_regular_capture_at", swap_recorded_on_manifest_read
    )
    with pytest.raises(
        generator.PublicationRecoveryRequired,
        match="recorded fixture directory identity changed",
    ):
        generator.check(tmp_path)
    assert foreign_identity is not None
    assert (recorded.stat().st_dev, recorded.stat().st_ino) == foreign_identity
    assert preserved.is_dir()


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
