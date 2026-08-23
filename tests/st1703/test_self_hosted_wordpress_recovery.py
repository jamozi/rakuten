"""Fake-only one-use recovery tests for the self-hosted pending draft."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import threading

import pytest

import raos.adapters.self_hosted_wordpress_journal as journal_module
from raos.adapters.self_hosted_wordpress_journal import (
    DurableSelfHostedWordPressDraftAdapter,
    DurableSelfHostedWordPressDraftRecoveryAdapter,
)
from raos.domain.editorial.self_hosted_wordpress import (
    SelfHostedWordPressDisposition,
    SelfHostedWordPressDraft,
    SelfHostedWordPressDraftReceipt,
    SelfHostedWordPressFailure,
    SelfHostedWordPressFailureCode,
    SelfHostedWordPressOperation,
    SelfHostedWordPressRecoveryObservation,
    SelfHostedWordPressRecoveryObservationDisposition,
    fail_self_hosted_wordpress,
)


STATE_ROOT = Path(".secrets/wordpress-owner-local/state")
JOURNAL_PATH = STATE_ROOT / "draft-journal.v1.json"
RECOVERY_PATH = STATE_ROOT / "draft-recovery.v1.json"


def _candidate(
    content: str = "<p>Exact reviewed content.</p>",
) -> SelfHostedWordPressDraft:
    return SelfHostedWordPressDraft.bind(
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        title="Exact reviewed title",
        slug="exact-reviewed-title",
        content_html=content,
    )


def _receipt(
    candidate: SelfHostedWordPressDraft,
    *,
    draft_id: int = 1703,
) -> SelfHostedWordPressDraftReceipt:
    return SelfHostedWordPressDraftReceipt(
        draft_id=draft_id,
        operation=SelfHostedWordPressOperation.CREATE_DRAFT,
        disposition=SelfHostedWordPressDisposition.CREATED,
        status="draft",
        content_sha256=candidate.content_sha256,
        operation_sha256=candidate.operation_sha256,
        response_sha256="e" * 64,
    )


class Attempt:
    def __init__(
        self,
        *,
        failure: SelfHostedWordPressFailureCode | None = None,
        draft_id: int = 1703,
    ) -> None:
        self.failure = failure
        self.draft_id = draft_id
        self.calls = 0

    def attempt(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressDraftReceipt:
        self.calls += 1
        if self.failure is not None:
            fail_self_hosted_wordpress(self.failure)
        return _receipt(candidate, draft_id=self.draft_id)


class Probe:
    def __init__(
        self,
        disposition: SelfHostedWordPressRecoveryObservationDisposition,
        *,
        draft_id: int | None = None,
        failure: SelfHostedWordPressFailureCode | None = None,
        root: Path | None = None,
    ) -> None:
        self.disposition = disposition
        self.draft_id = draft_id
        self.failure = failure
        self.root = root
        self.calls = 0
        self.saw_intent = False

    def observe(
        self, candidate: SelfHostedWordPressDraft
    ) -> SelfHostedWordPressRecoveryObservation:
        self.calls += 1
        if self.root is not None:
            state = json.loads((self.root / RECOVERY_PATH).read_text(encoding="ascii"))
            self.saw_intent = state["state"] == "INTENT"
        if self.failure is not None:
            fail_self_hosted_wordpress(self.failure)
        return SelfHostedWordPressRecoveryObservation(
            disposition=self.disposition,
            draft_id=self.draft_id,
            status="draft" if self.draft_id is not None else None,
            content_sha256=candidate.content_sha256,
            operation_sha256=candidate.operation_sha256,
            query_sha256="a" * 64,
            response_sha256="b" * 64,
        )


def _pending(root: Path, candidate: SelfHostedWordPressDraft) -> Attempt:
    first = Attempt(failure=SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS)
    durable = DurableSelfHostedWordPressDraftAdapter(
        repository_root=root,
        attempt_port=first,
    )
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        durable.apply(candidate)
    assert failure.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    assert first.calls == 1
    return first


def test_exact_existing_draft_reconciles_pending_with_zero_post(tmp_path: Path) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    probe = Probe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_DRAFT,
        draft_id=91703,
        root=tmp_path,
    )
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )

    receipt = recovery.recover(candidate)

    assert probe.calls == 1
    assert probe.saw_intent
    assert post.calls == 0
    assert receipt.disposition is SelfHostedWordPressDisposition.RECONCILED
    assert receipt.draft_id == 91703
    journal = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
    assert journal["pending"] is None
    assert journal["committed"]["draft_id"] == 91703
    recovery_state = json.loads((tmp_path / RECOVERY_PATH).read_text(encoding="ascii"))
    assert recovery_state["state"] == "TERMINAL"
    assert recovery_state["outcome"] == "RECONCILED_EXISTING"
    assert recovery_state["write_response_sha256"] is None
    persisted = json.dumps(recovery_state, sort_keys=True)
    assert candidate.title not in persisted
    assert candidate.slug not in persisted
    assert candidate.content_html not in persisted


def test_exact_absence_permits_exactly_one_additional_post(tmp_path: Path) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    probe = Probe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE,
        root=tmp_path,
    )
    post = Attempt(draft_id=27103)
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )

    receipt = recovery.recover(candidate)

    assert probe.calls == 1
    assert post.calls == 1
    assert receipt.disposition is SelfHostedWordPressDisposition.CREATED
    state = json.loads((tmp_path / RECOVERY_PATH).read_text(encoding="ascii"))
    assert state["outcome"] == "CREATED_AFTER_EXACT_ABSENCE"
    assert state["write_response_sha256"] == "e" * 64

    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == post.calls == 1

    replay_attempt = Attempt()
    replay = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path,
        attempt_port=replay_attempt,
    ).apply(candidate)
    assert replay.disposition is SelfHostedWordPressDisposition.REPLAYED
    assert replay_attempt.calls == 0


def test_remote_mismatch_consumes_recovery_and_performs_zero_post(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    probe = Probe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE,
        failure=SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH,
    )
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )

    with pytest.raises(SelfHostedWordPressFailure) as first:
        recovery.recover(candidate)
    assert first.value.code is SelfHostedWordPressFailureCode.RECOVERY_REMOTE_MISMATCH
    assert probe.calls == 1
    assert post.calls == 0
    terminal = json.loads((tmp_path / RECOVERY_PATH).read_text(encoding="ascii"))
    assert terminal["outcome"] == "BLOCKED"
    assert terminal["reason_code"] == "RECOVERY_REMOTE_MISMATCH"

    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == 1
    assert post.calls == 0


def test_second_post_ambiguity_leaves_original_pending_and_blocks_third_attempt(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    original = _pending(tmp_path, candidate)
    probe = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    second = Attempt(failure=SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS)
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=second,
    )

    with pytest.raises(SelfHostedWordPressFailure) as ambiguous:
        recovery.recover(candidate)
    assert ambiguous.value.code is SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS
    journal = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
    assert journal["pending"]["operation_sha256"] == candidate.operation_sha256
    assert journal["committed"] is None

    with pytest.raises(SelfHostedWordPressFailure) as third:
        recovery.recover(candidate)
    assert third.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    assert original.calls == probe.calls == second.calls == 1


def test_missing_or_mismatched_pending_refuses_before_sidecar_probe_or_post(
    tmp_path: Path,
) -> None:
    candidate = _candidate()
    probe = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )
    with pytest.raises(SelfHostedWordPressFailure) as missing:
        recovery.recover(candidate)
    assert missing.value.code is SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE
    assert not (tmp_path / RECOVERY_PATH).exists()

    _pending(tmp_path, candidate)
    with pytest.raises(SelfHostedWordPressFailure) as mismatch:
        recovery.recover(_candidate("<p>Different content.</p>"))
    assert mismatch.value.code is SelfHostedWordPressFailureCode.RECOVERY_NOT_AVAILABLE
    assert not (tmp_path / RECOVERY_PATH).exists()
    assert probe.calls == post.calls == 0


@pytest.mark.parametrize("mutation", ["integrity", "mode", "hardlink", "symlink"])
def test_pending_journal_tamper_refuses_before_sidecar_probe_or_post(
    tmp_path: Path,
    mutation: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    path = tmp_path / JOURNAL_PATH
    if mutation == "integrity":
        journal = json.loads(path.read_text(encoding="ascii"))
        journal["integrity_sha256"] = "0" * 64
        path.write_text(
            json.dumps(journal, sort_keys=True, separators=(",", ":")) + "\n",
            encoding="ascii",
        )
        path.chmod(0o600)
    elif mutation == "mode":
        path.chmod(0o644)
    elif mutation == "hardlink":
        os.link(path, path.with_name("journal-hardlink"))
    else:
        payload = path.read_bytes()
        path.unlink()
        foreign = path.with_name("foreign-journal")
        foreign.write_bytes(payload)
        foreign.chmod(0o600)
        path.symlink_to(foreign)

    probe = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        recovery.recover(candidate)
    assert failure.value.code in {
        SelfHostedWordPressFailureCode.JOURNAL_INVALID,
        SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID,
    }
    assert probe.calls == post.calls == 0
    assert not (tmp_path / RECOVERY_PATH).exists()


@pytest.mark.parametrize("mutation", ["mode", "hardlink", "symlink"])
def test_recovery_sidecar_metadata_tamper_blocks_without_capability(
    tmp_path: Path,
    mutation: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    probe = Probe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE,
        failure=SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN,
    )
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=Attempt(),
    )
    with pytest.raises(SelfHostedWordPressFailure):
        recovery.recover(candidate)
    path = tmp_path / RECOVERY_PATH
    if mutation == "mode":
        path.chmod(0o644)
    elif mutation == "hardlink":
        os.link(path, path.with_name("recovery-hardlink"))
    else:
        path.unlink()
        foreign = path.with_name("foreign-recovery")
        foreign.write_text("{}", encoding="ascii")
        foreign.chmod(0o600)
        path.symlink_to(foreign)

    with pytest.raises(SelfHostedWordPressFailure) as failure:
        recovery.recover(candidate)
    assert failure.value.code is SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
    assert probe.calls == 1


def test_unexpected_probe_crash_consumes_and_blocks_reentry(tmp_path: Path) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)

    class CrashingProbe:
        def __init__(self) -> None:
            self.calls = 0

        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            assert observed is candidate
            self.calls += 1
            raise RuntimeError("synthetic crash")

    probe = CrashingProbe()
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )
    with pytest.raises(SelfHostedWordPressFailure) as crashed:
        recovery.recover(candidate)
    assert crashed.value.code is SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
    assert probe.calls == 1
    assert post.calls == 0
    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == 1
    assert post.calls == 0


def test_recovery_intent_file_and_directory_are_fsynced_before_probe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    events: list[str] = []
    real_fsync = journal_module.os.fsync

    def observed_fsync(descriptor: int) -> None:
        events.append("fsync")
        real_fsync(descriptor)

    class OrderedProbe(Probe):
        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            events.append("probe")
            return super().observe(observed)

    monkeypatch.setattr(journal_module.os, "fsync", observed_fsync)
    probe = OrderedProbe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_DRAFT,
        draft_id=1703,
    )
    DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=Attempt(),
    ).recover(candidate)

    probe_index = events.index("probe")
    assert probe_index >= 2
    assert events[:probe_index].count("fsync") >= 2


def test_recovery_sidecar_is_integrity_bound_and_redacted(tmp_path: Path) -> None:
    candidate = _candidate("<p>Never persist this exact content sentinel.</p>")
    journal_before = _pending(tmp_path, candidate)
    del journal_before
    probe = Probe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE,
        failure=SelfHostedWordPressFailureCode.RECOVERY_READ_UNCERTAIN,
    )
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=Attempt(),
    )
    with pytest.raises(SelfHostedWordPressFailure):
        recovery.recover(candidate)

    recovery_path = tmp_path / RECOVERY_PATH
    journal = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
    sidecar = json.loads(recovery_path.read_text(encoding="ascii"))
    assert sidecar["candidate"] == journal["pending"]
    assert sidecar["pending_journal_integrity_sha256"] == journal["integrity_sha256"]
    assert stat.S_IMODE(recovery_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(recovery_path.parent.stat().st_mode) == 0o700
    serialized = recovery_path.read_text(encoding="ascii")
    for forbidden in (
        candidate.title,
        candidate.slug,
        candidate.content_html,
        "https://kurashinoshirube.com",
        "Authorization",
        "Basic ",
        "application_password",
        str(tmp_path),
        "browser",
    ):
        assert forbidden not in serialized

    sidecar["integrity_sha256"] = "0" * 64
    recovery_path.write_text(
        json.dumps(sidecar, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="ascii",
    )
    recovery_path.chmod(0o600)
    with pytest.raises(SelfHostedWordPressFailure) as tampered:
        recovery.recover(candidate)
    assert tampered.value.code is SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
    assert probe.calls == 1


def test_stale_terminal_stage_blocks_before_probe_or_post(tmp_path: Path) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    stage = tmp_path / STATE_ROOT / ".draft-recovery.v1.terminal"
    stage.write_text("incomplete", encoding="ascii")
    stage.chmod(0o600)
    probe = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )
    with pytest.raises(SelfHostedWordPressFailure) as failure:
        recovery.recover(candidate)
    assert (
        failure.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == post.calls == 0
    assert post.calls == 0
    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == 0


def test_concurrent_recovery_has_one_probe_and_one_post(tmp_path: Path) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    entered = threading.Event()
    release = threading.Event()

    class BlockingProbe(Probe):
        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            entered.set()
            assert release.wait(timeout=5)
            return super().observe(observed)

    probe = BlockingProbe(
        SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE
    )
    post = Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )
    outcomes: list[object] = []

    def run() -> None:
        try:
            outcomes.append(recovery.recover(candidate))
        except SelfHostedWordPressFailure as error:
            outcomes.append(error.code)

    first = threading.Thread(target=run)
    second = threading.Thread(target=run)
    first.start()
    assert entered.wait(timeout=5)
    second.start()
    release.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert probe.calls == 1
    assert post.calls == 1
    assert len(outcomes) == 2
    assert (
        sum(type(value) is SelfHostedWordPressDraftReceipt for value in outcomes) == 1
    )
    assert SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED in outcomes
    assert stat.S_IMODE((tmp_path / RECOVERY_PATH).stat().st_mode) == 0o600
