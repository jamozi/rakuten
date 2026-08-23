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
        ("after-publication-namespace", 73),
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
    payload = {relative.as_posix(): content.hex() for relative, content in new.items()}
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
g.build_outputs = lambda _root: outputs
g._checkpoint = lambda name: os._exit(exit_code) if name == target else None
g.generate(root)
"""
    completed = subprocess.run(
        [
            os.fspath(Path(sys.executable)),
            "-c",
            child,
            os.fspath(tmp_path),
            __import__("json").dumps(payload, sort_keys=True),
            checkpoint,
            str(exit_code),
        ],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == exit_code
    monkeypatch.setattr(generator, "build_outputs", lambda _root: new)
    generator.generate(tmp_path)
    _assert_installed(tmp_path, new)


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
    with pytest.raises(OSError):
        generator.generate(tmp_path)
    assert (outside / "sentinel").read_bytes() == b"unchanged"
    assert (tmp_path / generator.STORY_ROOT / generator.JOURNAL_NAME).is_dir()


@pytest.mark.parametrize(
    "stale_name",
    [
        generator.STAGE_NAME,
        generator.JOURNAL_PREPARING_NAME,
        generator.JOURNAL_CLEANUP_NAME,
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
        state = generator._new_journal_state(
            previous_digest=previous_digest,
            next_digest=next_digest,
        )
        generator._create_journal_at(story_fd, state)
        generator._write_journal_phase_at(story_fd, state, phase)
        os.replace(
            generator.JOURNAL_NAME,
            generator.JOURNAL_CLEANUP_NAME,
            src_dir_fd=story_fd,
            dst_dir_fd=story_fd,
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

    with pytest.raises(RuntimeError, match="generated fixture integrity drifted"):
        generator.generate(tmp_path)
    assert (story / generator.JOURNAL_CLEANUP_NAME).is_dir()


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
    cleanup = story / generator.JOURNAL_CLEANUP_NAME
    cleanup.mkdir()
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
