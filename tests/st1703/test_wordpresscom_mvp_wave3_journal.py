"""Immutable journal and no-resend tests for ST-1703 WordPress.com Wave 3."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time

import pytest

import raos.adapters.wordpresscom_mvp_draft_journal as journal_module
from raos.adapters.wordpresscom_mvp_draft_journal import (
    EmptyWordPressComMvpDraftJournalView,
    ImmutableWordPressComMvpDraftJournal,
)
from raos.domain.editorial.wordpresscom_mvp_drafts import (
    MvpDraftOperationState,
    WordPressComMvpDraftFailure,
)


BINDING = "a" * 64
ROOT = Path(__file__).resolve().parents[2]


def _journal(tmp_path: Path) -> tuple[Path, ImmutableWordPressComMvpDraftJournal]:
    parent = tmp_path / "wordpresscom-review-draft"
    parent.mkdir(mode=0o700, parents=True)
    root = parent / "mvp-wave3-state"
    root.mkdir(mode=0o700)
    (root / "records").mkdir(mode=0o700)
    return root, ImmutableWordPressComMvpDraftJournal(root=root)


def test_intent_is_exclusive_fsynced_append_and_consumes_the_post_budget(
    tmp_path: Path,
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        intent = journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id="7",
        )
    record = root / "records/00000001.json"
    assert stat.S_IMODE(record.stat().st_mode) == 0o600
    assert stat.S_IMODE((root / ".mvp-wave3.lock").stat().st_mode) == 0o600
    assert intent.sequence == 1
    reloaded = ImmutableWordPressComMvpDraftJournal(root=root)
    with reloaded.locked():
        assert reloaded.entries() == (intent,)
        with pytest.raises(WordPressComMvpDraftFailure):
            reloaded.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="SECOND_POST_FORBIDDEN",
                object_id="7",
            )
    assert sorted(path.name for path in (root / "records").iterdir()) == [
        "00000001.json"
    ]


@pytest.mark.parametrize(
    "terminal",
    [
        MvpDraftOperationState.COMMITTED,
        MvpDraftOperationState.MUTATION_AMBIGUOUS,
        MvpDraftOperationState.RECONCILED_COMMITTED,
    ],
)
def test_intent_allows_only_one_approved_followup(
    tmp_path: Path, terminal: MvpDraftOperationState
) -> None:
    _, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id="7",
        )
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=terminal,
            reason_code=(
                "READBACK_UNCERTAIN"
                if terminal is MvpDraftOperationState.MUTATION_AMBIGUOUS
                else "EXACT_RECONCILIATION"
                if terminal is MvpDraftOperationState.RECONCILED_COMMITTED
                else "EXACT_READBACK"
            ),
            object_id="7",
        )
        entries = journal.entries()
    assert [entry.state for entry in entries] == [
        MvpDraftOperationState.INTENT,
        terminal,
    ]
    assert entries[1].previous_record_sha256 == entries[0].record_sha256


def test_ambiguous_allows_read_only_reconciliation_but_never_new_intent(
    tmp_path: Path,
) -> None:
    _, journal = _journal(tmp_path)
    with journal.locked():
        for state, reason in (
            (MvpDraftOperationState.INTENT, "POST_BUDGET_CONSUMED"),
            (MvpDraftOperationState.MUTATION_AMBIGUOUS, "READBACK_UNCERTAIN"),
            (MvpDraftOperationState.RECONCILED_COMMITTED, "EXACT_RECONCILIATION"),
        ):
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=state,
                reason_code=reason,
                object_id="7",
            )
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="FORBIDDEN",
                object_id="7",
            )


def test_fixed_order_requires_exact_terminal_predecessor(tmp_path: Path) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="page-about-create",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="POST_BUDGET_CONSUMED",
                object_id=None,
            )
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
        journal.append(
            operation_id="page-about-create",
            operation_binding_sha256="b" * 64,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="11",
        )
    assert len(list((root / "records").iterdir())) == 2


def test_corrupt_chain_sequence_binding_and_mode_fail_closed(tmp_path: Path) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
    record = root / "records/00000001.json"
    value = json.loads(record.read_text(encoding="ascii"))
    value["reason_code"] = "TAMPERED"
    record.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass


@pytest.mark.parametrize(
    ("reason", "object_id"),
    [("ARBITRARY_UPPERCASE", "7"), ("EXACT_DESIRED", "07"), ("EXACT_DESIRED", None)],
)
def test_append_rejects_invalid_reason_state_object_combinations_before_write(
    tmp_path: Path, reason: str, object_id: str | None
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.REUSED_EXACT,
                reason_code=reason,
                object_id=object_id,
            )
    assert list((root / "records").iterdir()) == []


def test_refusal_reason_is_pinned_to_article_or_page_operation(tmp_path: Path) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="page-about-create",
                operation_binding_sha256="b" * 64,
                state=MvpDraftOperationState.REFUSED_MISMATCH,
                reason_code="BASELINE_MISMATCH",
                object_id=None,
            )
    assert [path.name for path in (root / "records").iterdir()] == ["00000001.json"]


@pytest.mark.parametrize(
    ("field", "value"),
    [("reason_code", "ARBITRARY_UPPERCASE"), ("object_id", "07")],
)
def test_rehashed_corrupt_reason_or_object_id_is_still_rejected(
    tmp_path: Path, field: str, value: str
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
    record = root / "records/00000001.json"
    mapping = json.loads(record.read_text(encoding="ascii"))
    mapping[field] = value
    mapping["record_sha256"] = journal_module._record_hash(mapping)
    record.write_bytes(journal_module._canonical(mapping))
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass


def test_rehashed_article_record_with_page_refusal_reason_is_rejected(
    tmp_path: Path,
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id="7",
        )
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REFUSED_MISMATCH,
            reason_code="SECOND_BASELINE_MISMATCH",
            object_id=None,
        )
    record = root / "records/00000002.json"
    mapping = json.loads(record.read_text(encoding="ascii"))
    mapping["reason_code"] = "SECOND_SCAN_COLLISION"
    mapping["record_sha256"] = journal_module._record_hash(mapping)
    record.write_bytes(journal_module._canonical(mapping))
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass


def test_old_wave2_shape_is_unrepresentable_as_a_wave3_root(tmp_path: Path) -> None:
    wrong_parent = tmp_path / "wordpresscom-review-draft"
    wrong_parent.mkdir(mode=0o700)
    wrong_root = wrong_parent / "state"
    wrong_root.mkdir(mode=0o700)
    (wrong_root / "records").mkdir(mode=0o700)
    with pytest.raises(WordPressComMvpDraftFailure):
        ImmutableWordPressComMvpDraftJournal(root=wrong_root)


def test_symlink_record_and_unlocked_access_fail_closed(tmp_path: Path) -> None:
    root, journal = _journal(tmp_path)
    with pytest.raises(WordPressComMvpDraftFailure):
        journal.entries()
    target = tmp_path / "target"
    target.write_text("{}", encoding="ascii")
    (root / "records/00000001.json").symlink_to(target)
    with pytest.raises(WordPressComMvpDraftFailure):
        with journal.locked():
            pass


def test_empty_preview_view_never_mutates_or_allows_prepare() -> None:
    journal = EmptyWordPressComMvpDraftJournalView()
    assert journal.inspect() == ()
    with pytest.raises(WordPressComMvpDraftFailure):
        with journal.locked():
            pass
    with pytest.raises(WordPressComMvpDraftFailure):
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id="7",
        )


@pytest.mark.parametrize("failure_call", [1, 2])
def test_file_or_directory_fsync_failure_leaves_fail_closed_intent_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    root, journal = _journal(tmp_path)
    original = journal_module.os.fsync
    calls = 0

    def fail_selected(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("synthetic fsync failure")
        original(descriptor)

    monkeypatch.setattr(journal_module.os, "fsync", fail_selected)
    with journal.locked():
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="POST_BUDGET_CONSUMED",
                object_id="7",
            )
    assert (root / "records/00000001.json").exists()
    monkeypatch.setattr(journal_module.os, "fsync", original)
    reloaded = ImmutableWordPressComMvpDraftJournal(root=root)
    with reloaded.locked():
        assert reloaded.entries()[0].state is MvpDraftOperationState.INTENT
        with pytest.raises(WordPressComMvpDraftFailure):
            reloaded.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="SECOND_POST_FORBIDDEN",
                object_id="7",
            )


def test_partial_record_write_and_exclusive_collision_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, journal = _journal(tmp_path)
    original = journal_module.os.write
    calls = 0

    def partial_then_fail(descriptor: int, data: bytes) -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            return original(descriptor, data[:7])
        raise OSError("synthetic interrupted write")

    monkeypatch.setattr(journal_module.os, "write", partial_then_fail)
    with journal.locked():
        with pytest.raises(WordPressComMvpDraftFailure):
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="POST_BUDGET_CONSUMED",
                object_id="7",
            )
    monkeypatch.setattr(journal_module.os, "write", original)
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass

    collision_root, collision = _journal(tmp_path / "collision")
    record = collision_root / "records/00000001.json"
    original_open = journal_module._open_private

    def collide(path: Path, flags: int, mode: int = 0o600) -> int:
        if path == record and flags & os.O_EXCL:
            record.write_bytes(b"sentinel")
            record.chmod(0o600)
        return original_open(path, flags, mode)

    monkeypatch.setattr(journal_module, "_open_private", collide)
    with collision.locked():
        with pytest.raises(WordPressComMvpDraftFailure):
            collision.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="POST_BUDGET_CONSUMED",
                object_id="7",
            )
    assert record.read_bytes() == b"sentinel"


def test_record_mode_owner_and_symlink_ancestor_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
    record = root / "records/00000001.json"
    record.chmod(0o644)
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass
    record.chmod(0o600)
    real_euid = os.geteuid()
    monkeypatch.setattr(journal_module.os, "geteuid", lambda: real_euid + 1)
    with pytest.raises(WordPressComMvpDraftFailure):
        ImmutableWordPressComMvpDraftJournal(root=root)
    monkeypatch.setattr(journal_module.os, "geteuid", lambda: real_euid)

    real_parent = tmp_path / "real" / "wordpresscom-review-draft"
    real_parent.mkdir(parents=True, mode=0o700)
    real_root = real_parent / "mvp-wave3-state"
    real_root.mkdir(mode=0o700)
    (real_root / "records").mkdir(mode=0o700)
    alias_parent = tmp_path / "alias"
    alias_parent.symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(WordPressComMvpDraftFailure):
        ImmutableWordPressComMvpDraftJournal(
            root=alias_parent / "wordpresscom-review-draft/mvp-wave3-state"
        )


def test_missing_sequence_truncation_extra_name_and_maximum_records_fail_closed(
    tmp_path: Path,
) -> None:
    root, journal = _journal(tmp_path)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.REUSED_EXACT,
            reason_code="EXACT_DESIRED",
            object_id="7",
        )
    record = root / "records/00000001.json"
    original = record.read_bytes()
    record.write_bytes(original[:5])
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass
    record.write_bytes(original)
    extra = root / "records/unexpected"
    extra.write_bytes(b"")
    extra.chmod(0o600)
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass
    extra.unlink()
    record.rename(root / "records/00000002.json")
    with pytest.raises(WordPressComMvpDraftFailure):
        with ImmutableWordPressComMvpDraftJournal(root=root).locked():
            pass

    maximum_root, maximum = _journal(tmp_path / "maximum")
    for sequence in range(1, 130):
        path = maximum_root / f"records/{sequence:08d}.json"
        path.write_bytes(b"{}")
        path.chmod(0o600)
    with pytest.raises(WordPressComMvpDraftFailure):
        with maximum.locked():
            pass


def test_process_lock_serializes_concurrent_journal_users(tmp_path: Path) -> None:
    root, journal = _journal(tmp_path)
    marker = tmp_path / "child-acquired"
    code = """
from pathlib import Path
import sys
sys.path.insert(0, sys.argv[1])
from raos.adapters.wordpresscom_mvp_draft_journal import ImmutableWordPressComMvpDraftJournal
root = Path(sys.argv[2])
marker = Path(sys.argv[3])
with ImmutableWordPressComMvpDraftJournal(root=root).locked():
    marker.write_text('acquired', encoding='ascii')
"""
    with journal.locked():
        process = subprocess.Popen(
            [sys.executable, "-c", code, str(ROOT / "python"), str(root), str(marker)],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.15)
        assert process.poll() is None
        assert not marker.exists()
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0, (stdout, stderr)
    assert marker.read_text(encoding="ascii") == "acquired"


@pytest.mark.parametrize("failure_call", [1, 2])
def test_lock_acquisition_or_release_failure_is_always_sanitized(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_call: int,
) -> None:
    _, journal = _journal(tmp_path)
    original = journal_module.fcntl.flock
    calls = 0

    def fail_selected(descriptor: int, operation: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError("synthetic flock failure")
        original(descriptor, operation)

    monkeypatch.setattr(journal_module.fcntl, "flock", fail_selected)
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        with journal.locked():
            pass
    assert failure.value.code.value == "MVP_DRAFT_JOURNAL_IO_FAILURE"


def test_terminal_append_fsync_failure_cannot_create_a_second_post_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, journal = _journal(tmp_path)
    original = journal_module.os.fsync
    calls = 0

    def fail_terminal_file(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise OSError("synthetic terminal fsync failure")
        original(descriptor)

    monkeypatch.setattr(journal_module.os, "fsync", fail_terminal_file)
    with journal.locked():
        journal.append(
            operation_id="article-7-update",
            operation_binding_sha256=BINDING,
            state=MvpDraftOperationState.INTENT,
            reason_code="POST_BUDGET_CONSUMED",
            object_id="7",
        )
        with pytest.raises(WordPressComMvpDraftFailure) as failure:
            journal.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.COMMITTED,
                reason_code="EXACT_READBACK",
                object_id="7",
            )
    assert failure.value.code.value == "MVP_DRAFT_JOURNAL_IO_FAILURE"
    monkeypatch.setattr(journal_module.os, "fsync", original)
    reloaded = ImmutableWordPressComMvpDraftJournal(root=root)
    with reloaded.locked():
        states = [entry.state for entry in reloaded.entries()]
        assert states in [
            [MvpDraftOperationState.INTENT],
            [MvpDraftOperationState.INTENT, MvpDraftOperationState.COMMITTED],
        ]
        with pytest.raises(WordPressComMvpDraftFailure):
            reloaded.append(
                operation_id="article-7-update",
                operation_binding_sha256=BINDING,
                state=MvpDraftOperationState.INTENT,
                reason_code="POST_BUDGET_CONSUMED",
                object_id="7",
            )


def test_recursive_canonical_value_is_sanitized() -> None:
    recursive: dict[str, object] = {}
    recursive["self"] = recursive
    with pytest.raises(WordPressComMvpDraftFailure) as failure:
        journal_module._canonical(recursive)
    assert failure.value.code.value == "MVP_DRAFT_JOURNAL_INVALID"
