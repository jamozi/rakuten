"""Fake-only one-use recovery tests for the self-hosted pending draft."""

from __future__ import annotations

from collections.abc import Callable
import hashlib
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
RECOVERY_GUARD_PATH = STATE_ROOT / "draft-recovery.v1.guard"


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )


def _empty_journal_bytes() -> bytes:
    payload = {
        "committed": None,
        "pending": None,
        "schema": "SELF_HOSTED_WORDPRESS_DRAFT_JOURNAL_V1",
        "site_origin": "https://kurashinoshirube.com",
    }
    return _canonical_json(
        {
            **payload,
            "integrity_sha256": hashlib.sha256(_canonical_json(payload)).hexdigest(),
        }
    )


def _fork_and_wait(action: Callable[[], None]) -> None:
    child = os.fork()
    if child == 0:
        try:
            action()
        except BaseException:
            os._exit(1)
        os._exit(0)
    waited, wait_status = os.waitpid(child, 0)
    assert waited == child
    assert os.waitstatus_to_exitcode(wait_status) == 0


def _atomic_replace(path: Path, payload: bytes) -> None:
    replacement = path.with_name(f".hostile-{path.name}-replacement")
    descriptor = os.open(
        replacement,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        assert os.write(descriptor, payload) == len(payload)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(replacement, path)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _unlink_and_fsync(path: Path) -> None:
    path.unlink()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


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
    assert journal["schema"] == "SELF_HOSTED_WORDPRESS_DRAFT_JOURNAL_V1"
    assert journal["pending"]["operation_sha256"] == candidate.operation_sha256
    assert journal["committed"] is None
    assert (tmp_path / RECOVERY_GUARD_PATH).is_file()

    with pytest.raises(SelfHostedWordPressFailure) as third:
        recovery.recover(candidate)
    assert third.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    assert original.calls == probe.calls == second.calls == 1

    ordinary_post = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as ordinary:
        DurableSelfHostedWordPressDraftAdapter(
            repository_root=tmp_path,
            attempt_port=ordinary_post,
        ).apply(candidate)
    assert ordinary.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert ordinary_post.calls == 0


@pytest.mark.parametrize("replacement_kind", ["valid-different", "byte-identical"])
@pytest.mark.parametrize("network_window", ["get", "post"])
def test_child_atomic_journal_replace_during_network_is_not_overwritten(
    tmp_path: Path,
    replacement_kind: str,
    network_window: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    replacement = _empty_journal_bytes()

    def replace_journal() -> None:
        path = tmp_path / JOURNAL_PATH
        _fork_and_wait(
            lambda: _atomic_replace(
                path,
                replacement
                if replacement_kind == "valid-different"
                else path.read_bytes(),
            )
        )

    class ReplacingProbe(Probe):
        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            replace_journal()
            return super().observe(observed)

    class ReplacingAttempt(Attempt):
        def attempt(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressDraftReceipt:
            replace_journal()
            return super().attempt(observed)

    probe_type = ReplacingProbe if network_window == "get" else Probe
    probe = probe_type(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post = ReplacingAttempt() if network_window == "post" else Attempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )

    with pytest.raises(SelfHostedWordPressFailure) as drift:
        recovery.recover(candidate)
    assert drift.value.code is SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
    assert probe.calls == 1
    assert post.calls == (1 if network_window == "post" else 0)
    if replacement_kind == "valid-different":
        assert (tmp_path / JOURNAL_PATH).read_bytes() == replacement
    else:
        replaced = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
        assert replaced["pending"]["operation_sha256"] == candidate.operation_sha256
        assert replaced["committed"] is None
    assert (tmp_path / RECOVERY_GUARD_PATH).is_file()

    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == 1
    assert post.calls == (1 if network_window == "post" else 0)

    ordinary_post = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as ordinary:
        DurableSelfHostedWordPressDraftAdapter(
            repository_root=tmp_path,
            attempt_port=ordinary_post,
        ).apply(candidate)
    assert ordinary.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert ordinary_post.calls == 0
    if replacement_kind == "valid-different":
        assert (tmp_path / JOURNAL_PATH).read_bytes() == replacement


@pytest.mark.parametrize(
    "mutation", ["unlink", "replace", "unlink-and-journal-replace"]
)
def test_child_sidecar_mutation_during_ambiguous_post_cannot_enable_third_attempt(
    tmp_path: Path,
    mutation: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)
    probe = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)

    class UnlinkingAmbiguousAttempt(Attempt):
        def attempt(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressDraftReceipt:
            assert observed is candidate
            self.calls += 1
            sidecar = tmp_path / RECOVERY_PATH
            if mutation == "unlink":
                _fork_and_wait(lambda: _unlink_and_fsync(sidecar))
            elif mutation == "replace":
                _fork_and_wait(lambda: _atomic_replace(sidecar, sidecar.read_bytes()))
            else:

                def replace_both() -> None:
                    _unlink_and_fsync(sidecar)
                    _atomic_replace(tmp_path / JOURNAL_PATH, _empty_journal_bytes())

                _fork_and_wait(replace_both)
            fail_self_hosted_wordpress(SelfHostedWordPressFailureCode.OUTCOME_AMBIGUOUS)

    post = UnlinkingAmbiguousAttempt()
    recovery = DurableSelfHostedWordPressDraftRecoveryAdapter(
        repository_root=tmp_path,
        probe_port=probe,
        attempt_port=post,
    )

    with pytest.raises(SelfHostedWordPressFailure) as drift:
        recovery.recover(candidate)
    assert drift.value.code is SelfHostedWordPressFailureCode.RECOVERY_STATE_INVALID
    assert probe.calls == 1
    assert post.calls == 1
    assert (tmp_path / RECOVERY_PATH).exists() is (mutation == "replace")
    assert (tmp_path / RECOVERY_GUARD_PATH).is_file()
    journal = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
    if mutation == "unlink-and-journal-replace":
        assert journal["pending"] is None
    else:
        assert journal["pending"]["operation_sha256"] == candidate.operation_sha256
    assert journal["committed"] is None

    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        recovery.recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe.calls == post.calls == 1

    ordinary_post = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as ordinary:
        DurableSelfHostedWordPressDraftAdapter(
            repository_root=tmp_path,
            attempt_port=ordinary_post,
        ).apply(candidate)
    assert ordinary.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert ordinary_post.calls == 0


@pytest.mark.parametrize("network_window", ["get", "post"])
def test_process_exit_during_network_keeps_recovery_permanently_consumed(
    tmp_path: Path,
    network_window: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)

    class ExitingProbe:
        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            assert observed is candidate
            os._exit(23)

    class ExitingAttempt:
        def attempt(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressDraftReceipt:
            assert observed is candidate
            os._exit(24)

    child = os.fork()
    if child == 0:
        probe: object = (
            ExitingProbe()
            if network_window == "get"
            else Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
        )
        post: object = ExitingAttempt() if network_window == "post" else Attempt()
        DurableSelfHostedWordPressDraftRecoveryAdapter(
            repository_root=tmp_path,
            probe_port=probe,
            attempt_port=post,
        ).recover(candidate)
        os._exit(1)
    waited, wait_status = os.waitpid(child, 0)
    assert waited == child
    assert os.waitstatus_to_exitcode(wait_status) == (
        23 if network_window == "get" else 24
    )

    assert (tmp_path / RECOVERY_GUARD_PATH).is_file()
    pending = json.loads((tmp_path / JOURNAL_PATH).read_text(encoding="ascii"))
    assert pending["pending"]["operation_sha256"] == candidate.operation_sha256
    assert pending["committed"] is None
    intent = json.loads((tmp_path / RECOVERY_PATH).read_text(encoding="ascii"))
    assert intent["state"] == "INTENT"

    probe_after = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post_after = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        DurableSelfHostedWordPressDraftRecoveryAdapter(
            repository_root=tmp_path,
            probe_port=probe_after,
            attempt_port=post_after,
        ).recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe_after.calls == post_after.calls == 0

    ordinary_post = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as ordinary:
        DurableSelfHostedWordPressDraftAdapter(
            repository_root=tmp_path,
            attempt_port=ordinary_post,
        ).apply(candidate)
    assert ordinary.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    assert ordinary_post.calls == 0


@pytest.mark.parametrize("terminal_target", ["journal", "sidecar"])
def test_process_exit_during_held_terminal_write_keeps_recovery_consumed(
    tmp_path: Path,
    terminal_target: str,
) -> None:
    candidate = _candidate()
    _pending(tmp_path, candidate)

    class ArmingProbe(Probe):
        def observe(
            self, observed: SelfHostedWordPressDraft
        ) -> SelfHostedWordPressRecoveryObservation:
            result = super().observe(observed)
            original_write_all = journal_module._write_all
            write_calls = 0

            def exit_during_write(descriptor: int, payload: bytes) -> None:
                nonlocal write_calls
                write_calls += 1
                target_call = 1 if terminal_target == "journal" else 2
                if write_calls == target_call:
                    assert os.write(descriptor, payload[:1]) == 1
                    os._exit(25 if terminal_target == "journal" else 26)
                original_write_all(descriptor, payload)

            journal_module._write_all = exit_during_write
            return result

    child = os.fork()
    if child == 0:
        DurableSelfHostedWordPressDraftRecoveryAdapter(
            repository_root=tmp_path,
            probe_port=ArmingProbe(
                SelfHostedWordPressRecoveryObservationDisposition.EXACT_DRAFT,
                draft_id=91703,
            ),
            attempt_port=Attempt(),
        ).recover(candidate)
        os._exit(1)
    waited, wait_status = os.waitpid(child, 0)
    assert waited == child
    assert os.waitstatus_to_exitcode(wait_status) == (
        25 if terminal_target == "journal" else 26
    )
    assert (tmp_path / RECOVERY_GUARD_PATH).is_file()

    probe_after = Probe(SelfHostedWordPressRecoveryObservationDisposition.EXACT_ABSENCE)
    post_after = Attempt()
    with pytest.raises(SelfHostedWordPressFailure) as repeated:
        DurableSelfHostedWordPressDraftRecoveryAdapter(
            repository_root=tmp_path,
            probe_port=probe_after,
            attempt_port=post_after,
        ).recover(candidate)
    assert (
        repeated.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
    assert probe_after.calls == post_after.calls == 0

    ordinary_post = Attempt()
    ordinary = DurableSelfHostedWordPressDraftAdapter(
        repository_root=tmp_path,
        attempt_port=ordinary_post,
    )
    if terminal_target == "journal":
        with pytest.raises(SelfHostedWordPressFailure) as blocked:
            ordinary.apply(candidate)
        assert blocked.value.code is SelfHostedWordPressFailureCode.JOURNAL_AMBIGUOUS
    else:
        replay = ordinary.apply(candidate)
        assert replay.disposition is SelfHostedWordPressDisposition.REPLAYED
    assert ordinary_post.calls == 0


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
    assert (
        failure.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
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
    guard_path = tmp_path / RECOVERY_GUARD_PATH
    guard = json.loads(guard_path.read_text(encoding="ascii"))
    assert sidecar["candidate"] == journal["pending"] == guard["candidate"]
    assert (
        sidecar["pending_journal_integrity_sha256"]
        == guard["pending_journal_integrity_sha256"]
        == journal["integrity_sha256"]
    )
    assert stat.S_IMODE(recovery_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(guard_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(recovery_path.parent.stat().st_mode) == 0o700
    serialized = "".join(
        path.read_text(encoding="ascii") for path in (recovery_path, guard_path)
    )
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
    assert (
        tampered.value.code is SelfHostedWordPressFailureCode.RECOVERY_ALREADY_CONSUMED
    )
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
