"""Durable no-resend journal tests for the self-hosted draft path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raos.adapters.self_hosted_wordpress_journal import (
    DurableSelfHostedWordPressDraftAdapter,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDisposition,
    SelfHostedWordPressDraft,
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    fail_self_hosted_wordpress,
)


STATE_RELATIVE = Path(".secrets/wordpress-owner-local/state/draft-journal.v1.json")


def _candidate(
    *,
    operation: SelfHostedWordPressOperation = SelfHostedWordPressOperation.CREATE_DRAFT,
    draft_id: int | None = None,
    content: str = "<p>Bound content.</p>",
) -> SelfHostedWordPressDraft:
    return SelfHostedWordPressDraft.bind(
        operation=operation,
        title="Bound draft",
        content_html=content,
        existing_draft_id=draft_id,
    )


class CountingAttempt:
    def __init__(
        self,
        root: Path,
        *,
        failure: SelfHostedWordPressFailureCode | None = None,
        wrong_receipt: bool = False,
    ) -> None:
        self.root = root
        self.failure = failure
        self.wrong_receipt = wrong_receipt
        self.calls = 0
        self.saw_durable_intent = False

    def attempt(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt:
        self.calls += 1
        state = json.loads((self.root / STATE_RELATIVE).read_text(encoding="ascii"))
        self.saw_durable_intent = (
            state["pending"]["operation_sha256"] == candidate.operation_sha256
        )
        if self.failure is not None:
            fail_self_hosted_wordpress(self.failure)
        disposition = (
            SelfHostedWordPressDisposition.CREATED
            if candidate.operation is SelfHostedWordPressOperation.CREATE_DRAFT
            else SelfHostedWordPressDisposition.UPDATED
        )
        return SelfHostedWordPressDraftReceipt(
            draft_id=(candidate.existing_draft_id or 1703),
            operation=candidate.operation,
            disposition=disposition,
            status="draft",
            content_sha256=(
                "f" * 64 if self.wrong_receipt else candidate.content_sha256
            ),
            operation_sha256=candidate.operation_sha256,
            response_sha256="e" * 64,
        )


def test_intent_is_fsynced_before_attempt_and_commit_replays_without_attempt(
    tmp_path: Path,
) -> None:
    attempt = CountingAttempt(tmp_path)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )
    candidate = _candidate()

    first = durable.apply(candidate)
    replay = durable.apply(candidate)

    assert attempt.saw_durable_intent
    assert attempt.calls == 1
    assert first.disposition is SelfHostedWordPressDisposition.CREATED
    assert replay.disposition is SelfHostedWordPressDisposition.REPLAYED
    state = json.loads((tmp_path / STATE_RELATIVE).read_text(encoding="ascii"))
    assert state["pending"] is None
    assert state["committed"]["draft_id"] == 1703
    assert "content_html" not in state["committed"]
    assert "title" not in state["committed"]


def test_failed_attempt_leaves_pending_and_exact_repeat_never_resends(
    tmp_path: Path,
) -> None:
    attempt = CountingAttempt(
        tmp_path, failure=SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    )
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )
    candidate = _candidate()

    with pytest.raises(SelfHostedWordPressFailure) as first:
        durable.apply(candidate)
    assert first.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    with pytest.raises(SelfHostedWordPressFailure) as repeat:
        durable.apply(candidate)
    assert repeat.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert attempt.calls == 1


def test_receipt_mismatch_remains_ambiguous_and_is_not_committed(
    tmp_path: Path,
) -> None:
    attempt = CountingAttempt(tmp_path, wrong_receipt=True)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        durable.apply(_candidate())
    assert failure.value.code is SelfHostedWordPressFailureCode.OUTCOME_MISMATCH
    state = json.loads((tmp_path / STATE_RELATIVE).read_text(encoding="ascii"))
    assert state["pending"] is not None
    assert state["committed"] is None


def test_update_requires_exact_committed_positive_draft_id(tmp_path: Path) -> None:
    attempt = CountingAttempt(tmp_path)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )
    durable.apply(_candidate())

    update = _candidate(
        operation=SelfHostedWordPressOperation.UPDATE_DRAFT,
        draft_id=1703,
        content="<p>Reviewed correction.</p>",
    )
    updated = durable.apply(update)
    replay = durable.apply(update)
    assert updated.disposition is SelfHostedWordPressDisposition.UPDATED
    assert replay.disposition is SelfHostedWordPressDisposition.REPLAYED
    assert attempt.calls == 2

    with pytest.raises(SelfHostedWordPressFailure) as wrong_id:
        durable.apply(
            _candidate(
                operation=SelfHostedWordPressOperation.UPDATE_DRAFT,
                draft_id=1704,
                content="<p>Different target.</p>",
            )
        )
    assert wrong_id.value.code is SelfHostedWordPressFailureCode.JOURNAL_MISMATCH
    assert attempt.calls == 2


def test_update_without_create_and_second_create_are_refused_before_attempt(
    tmp_path: Path,
) -> None:
    attempt = CountingAttempt(tmp_path)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )
    with pytest.raises(SelfHostedWordPressFailure):
        durable.apply(
            _candidate(
                operation=SelfHostedWordPressOperation.UPDATE_DRAFT,
                draft_id=1703,
            )
        )
    assert attempt.calls == 0

    durable.apply(_candidate())
    with pytest.raises(SelfHostedWordPressFailure) as second:
        durable.apply(_candidate(content="<p>Changed create.</p>"))
    assert second.value.code is SelfHostedWordPressFailureCode.JOURNAL_MISMATCH
    assert attempt.calls == 1


def test_tampered_integrity_wrong_mode_and_symlinked_ancestor_fail_closed(
    tmp_path: Path,
) -> None:
    attempt = CountingAttempt(tmp_path)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=attempt
    )
    candidate = _candidate()
    durable.apply(candidate)
    state_path = tmp_path / STATE_RELATIVE
    state = json.loads(state_path.read_text(encoding="ascii"))
    state["integrity_sha256"] = "0" * 64
    state_path.write_text(json.dumps(state), encoding="ascii")
    state_path.chmod(0o600)
    with pytest.raises(SelfHostedWordPressFailure) as tampered:
        durable.apply(candidate)
    assert tampered.value.code is SelfHostedWordPressFailureCode.JOURNAL_INVALID
    assert attempt.calls == 1

    state_path.chmod(0o644)
    with pytest.raises(SelfHostedWordPressFailure):
        durable.apply(candidate)

    other = tmp_path / "other"
    other.mkdir()
    symlink_root = tmp_path / "symlink-root"
    symlink_root.mkdir()
    (symlink_root / ".secrets").symlink_to(other, target_is_directory=True)
    with pytest.raises(SelfHostedWordPressFailure):
        DurableSelfHostedWordPressDraftAdapter(
            repository_root=symlink_root,
            attempt_port=CountingAttempt(symlink_root),
        ).apply(candidate)


def test_journal_and_failure_representations_are_value_free(tmp_path: Path) -> None:
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path, attempt_port=CountingAttempt(tmp_path)
    )
    assert "Bound content" not in repr(durable)
    failure = SelfHostedWordPressFailure(
        SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    )
    assert str(failure) == "JOURNAL_AMBIGUOUS"
    assert "Bound content" not in repr(failure)
