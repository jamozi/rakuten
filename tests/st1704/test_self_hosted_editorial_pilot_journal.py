"""Digest journal and no-resend tests for the ST-1704 review boundary."""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
from collections.abc import Iterator
import os

import pytest

import raos.adapters.self_hosted_editorial_pilot_json as journal_module
from raos.adapters.self_hosted_editorial_pilot_json import (
    GENERATION_DIRECTORY,
    JOURNAL_DIRECTORY,
    OWNER_DIRECTORY,
    REQUEST_DIRECTORY,
    OwnerPrivateLiveReviewDraftJournal,
    OwnerPrivateReviewDraftGenerationLedger,
    OwnerPrivateReviewDraftJournal,
    RecordedWordPressReviewDraftAdapter,
    request_artifact_relative_path,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    EditorialPilotFailureCode,
    ReviewDraftDisposition,
    ReviewDraftReceipt,
    ReviewDraftRequest,
    bytes_sha256,
    canonical_json_bytes,
    canonical_sha256,
    fail_editorial_pilot,
)
from raos.ports.self_hosted_editorial_pilot import (
    ReviewDraftRevisionBinding,
    ReviewDraftRevisionDisposition,
    ReviewDraftRevisionObservation,
)
from .test_self_hosted_editorial_pilot import envelope, recorded_post, request


@pytest.fixture
def private_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-journal-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


def create_evidence(candidate: ReviewDraftRequest, *, valid: bool = True) -> bytes:
    post = recorded_post(candidate)
    if not valid:
        post["status"] = "publish"
    return envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_CREATE_REVIEW_DRAFT_V1",
        response=post,
        status=201,
    )


def recovery_evidence(candidate: ReviewDraftRequest, posts: list[object]) -> bytes:
    return envelope(
        candidate,
        schema="RAOS_RECORDED_WORDPRESS_RECOVER_REVIEW_DRAFT_V1",
        response=posts,
        status=200,
    )


def _live_journal_path(root: Path, candidate: ReviewDraftRequest) -> Path:
    return (
        root
        / ".secrets"
        / OWNER_DIRECTORY
        / JOURNAL_DIRECTORY
        / f"{candidate.article_id}.{candidate.packet_sha256}.live.v1.json"
    )


def _generation_ledger_path(root: Path, article_id: str) -> Path:
    return (
        root
        / ".secrets"
        / OWNER_DIRECTORY
        / GENERATION_DIRECTORY
        / f"{article_id}.generations.v1.json"
    )


def _revision(
    predecessor: ReviewDraftRequest,
    successor: ReviewDraftRequest,
    *,
    generation: int,
    draft_id: int = 1704,
) -> ReviewDraftRevisionBinding:
    return ReviewDraftRevisionBinding.bind(
        predecessor=predecessor,
        successor=successor,
        draft_id=draft_id,
        generation=generation,
    )


def _revision_observation(
    binding: ReviewDraftRevisionBinding,
    disposition: ReviewDraftRevisionDisposition,
    *,
    response_sha256: str = "e" * 64,
) -> ReviewDraftRevisionObservation:
    return ReviewDraftRevisionObservation(
        operation_sha256=binding.operation_sha256,
        response_sha256=response_sha256,
        draft_id=binding.draft_id,
        disposition=disposition,
    )


def _install_orphan_request_artifact(root: Path, candidate: ReviewDraftRequest) -> Path:
    directory = root / ".secrets" / OWNER_DIRECTORY / REQUEST_DIRECTORY
    directory.mkdir(parents=True, mode=0o700, exist_ok=True)
    (root / ".secrets").chmod(0o700)
    (root / ".secrets" / OWNER_DIRECTORY).chmod(0o700)
    directory.chmod(0o700)
    path = root / request_artifact_relative_path(candidate)
    payload = (
        canonical_json_bytes(
            journal_module._request_artifact_document(candidate)  # type: ignore[attr-defined]
        )
        + b"\n"
    )
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        assert os.write(descriptor, payload) == len(payload)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return path


def test_recorded_create_commits_and_exact_replay_never_revalidates(
    private_root: Path,
) -> None:
    tmp_path = private_root
    candidate = request()
    adapter = RecordedWordPressReviewDraftAdapter()
    journal = OwnerPrivateReviewDraftJournal(tmp_path, adapter)
    evidence = create_evidence(candidate)

    first = journal.create(candidate, evidence)
    replay = journal.create(candidate, b"different bytes are ignored after commit")

    assert first.disposition is ReviewDraftDisposition.RECORDED_CREATED
    assert replay.disposition is ReviewDraftDisposition.LOCAL_REPLAY
    assert replay.draft_id == first.draft_id
    path = (
        tmp_path
        / ".secrets"
        / OWNER_DIRECTORY
        / JOURNAL_DIRECTORY
        / f"{candidate.article_id}.{candidate.packet_sha256}.v1.json"
    )
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["state"] == "COMMITTED"
    assert "content" not in document
    assert "title" not in document
    assert path.stat().st_mode & 0o777 == 0o600


def test_invalid_recorded_outcome_leaves_intent_and_recovery_is_exactly_once(
    private_root: Path,
) -> None:
    tmp_path = private_root
    candidate = request()
    journal = OwnerPrivateReviewDraftJournal(
        tmp_path, RecordedWordPressReviewDraftAdapter()
    )

    with pytest.raises(EditorialPilotFailure) as failed:
        journal.create(candidate, create_evidence(candidate, valid=False))
    assert failed.value.code is EditorialPilotFailureCode.RECORDED_RESPONSE_INVALID
    with pytest.raises(EditorialPilotFailure) as resend:
        journal.create(candidate, create_evidence(candidate))
    assert resend.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS

    receipt = journal.recover(
        candidate, recovery_evidence(candidate, [recorded_post(candidate)])
    )
    assert receipt.disposition is ReviewDraftDisposition.RECORDED_RECOVERED
    assert (
        journal.recover(candidate, b"ignored after committed recovery").disposition
        is ReviewDraftDisposition.LOCAL_REPLAY
    )


def test_zero_or_multiple_recovery_result_is_terminally_ambiguous(
    private_root: Path,
) -> None:
    tmp_path = private_root
    candidate = request()
    journal = OwnerPrivateReviewDraftJournal(
        tmp_path, RecordedWordPressReviewDraftAdapter()
    )
    with pytest.raises(EditorialPilotFailure):
        journal.create(candidate, create_evidence(candidate, valid=False))

    with pytest.raises(EditorialPilotFailure) as absent:
        journal.recover(candidate, recovery_evidence(candidate, []))
    assert absent.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    with pytest.raises(EditorialPilotFailure) as repeated:
        journal.recover(
            candidate,
            recovery_evidence(candidate, [recorded_post(candidate)]),
        )
    assert repeated.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS


class FakeOwnerLivePort:
    def __init__(self, root: Path, *, create_fails: bool = False) -> None:
        self.root = root
        self.create_fails = create_fails
        self.preflights: list[str] = []
        self.create_calls = 0
        self.recover_calls = 0

    def preflight(self, request: ReviewDraftRequest, command: str) -> None:
        assert request.article_id in {
            "st1703-first-suitcase-comparison",
            "st1704-portable-power-station-guide",
        }
        self.preflights.append(command)

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None:
        assert request.article_id in {
            "st1703-first-suitcase-comparison",
            "st1704-portable-power-station-guide",
        }
        assert command in {"create-review-draft", "recover-create-review-draft"}
        return 42 if request.article_id == "st1703-first-suitcase-comparison" else None

    def create(self, candidate: ReviewDraftRequest) -> ReviewDraftReceipt:
        self.create_calls += 1
        journal_path = (
            self.root
            / ".secrets"
            / OWNER_DIRECTORY
            / JOURNAL_DIRECTORY
            / f"{candidate.article_id}.{candidate.packet_sha256}.live.v1.json"
        )
        assert json.loads(journal_path.read_text(encoding="utf-8"))["state"] == "INTENT"
        artifact_path = self.root / request_artifact_relative_path(candidate)
        assert artifact_path.is_file()
        assert artifact_path.stat().st_mode & 0o777 == 0o600
        if self.create_fails:
            fail_editorial_pilot(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)
        return self._receipt(candidate, ReviewDraftDisposition.OWNER_LIVE_CREATED)

    def recover(self, candidate: ReviewDraftRequest) -> ReviewDraftReceipt:
        self.recover_calls += 1
        return self._receipt(candidate, ReviewDraftDisposition.OWNER_LIVE_RECOVERED)

    def verify_public(
        self, candidate: ReviewDraftRequest, expected_public_post_id: int
    ) -> object:
        del candidate, expected_public_post_id
        raise AssertionError("journal reached public verification")

    @staticmethod
    def _receipt(
        candidate: ReviewDraftRequest, disposition: ReviewDraftDisposition
    ) -> ReviewDraftReceipt:
        return ReviewDraftReceipt(
            article_id=candidate.article_id,
            packet_sha256=candidate.packet_sha256,
            request_sha256=candidate.request_sha256,
            response_sha256="d" * 64,
            draft_id=1704,
            disposition=disposition,
            target_public_post_id=(
                42
                if candidate.article_id == "st1703-first-suitcase-comparison"
                else None
            ),
            recorded_evidence_only=False,
            live_authority=True,
        )


def test_live_journal_writes_intent_before_attempt_and_never_resends(
    private_root: Path,
) -> None:
    tmp_path = private_root
    candidate = request()
    live = FakeOwnerLivePort(tmp_path)
    journal = OwnerPrivateLiveReviewDraftJournal(tmp_path, live)

    first = journal.create(candidate)
    replay = journal.create(candidate)

    assert first.disposition is ReviewDraftDisposition.OWNER_LIVE_CREATED
    assert replay.disposition is ReviewDraftDisposition.OWNER_LIVE_REPLAY
    assert live.create_calls == 1
    artifact_path = tmp_path / request_artifact_relative_path(candidate)
    journal_path = (
        tmp_path
        / ".secrets"
        / OWNER_DIRECTORY
        / JOURNAL_DIRECTORY
        / f"{candidate.article_id}.{candidate.packet_sha256}.live.v1.json"
    )
    artifact_raw = artifact_path.read_bytes()
    journal_document = json.loads(journal_path.read_text(encoding="utf-8"))
    assert journal_document["state"] == "COMMITTED"
    assert journal_document["request_artifact_name"] == artifact_path.name
    assert journal_document["request_artifact_sha256"] == bytes_sha256(artifact_raw)
    assert artifact_path.parent.name == REQUEST_DIRECTORY
    persisted, expected_public_post_id = journal.committed_request(candidate.article_id)
    assert persisted == candidate
    assert expected_public_post_id == first.draft_id


def test_live_ambiguous_create_can_only_reconcile_and_never_post_again(
    private_root: Path,
) -> None:
    tmp_path = private_root
    candidate = request()
    first_port = FakeOwnerLivePort(tmp_path, create_fails=True)
    first = OwnerPrivateLiveReviewDraftJournal(tmp_path, first_port)
    with pytest.raises(EditorialPilotFailure) as ambiguous:
        first.create(candidate)
    assert ambiguous.value.code is EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
    assert first.request_for_recovery(candidate.article_id) == candidate
    with pytest.raises(EditorialPilotFailure) as not_committed:
        first.committed_request(candidate.article_id)
    assert not_committed.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS

    recovery_port = FakeOwnerLivePort(tmp_path)
    recovery = OwnerPrivateLiveReviewDraftJournal(tmp_path, recovery_port)
    receipt = recovery.recover(candidate)
    assert receipt.disposition is ReviewDraftDisposition.OWNER_LIVE_RECOVERED
    assert first_port.create_calls == 1
    assert recovery_port.create_calls == 0
    assert recovery_port.recover_calls == 1
    assert recovery.committed_request(candidate.article_id) == (candidate, 1704)
    with pytest.raises(EditorialPilotFailure) as replay:
        recovery.recover(candidate)
    assert replay.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    assert recovery_port.recover_calls == 1


def test_recovery_attempted_state_cannot_recover_again_or_verify(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = request()
    creator = OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root, create_fails=True)
    )
    with pytest.raises(EditorialPilotFailure):
        creator.create(candidate)
    recovery_port = FakeOwnerLivePort(private_root)

    def fail_recovery(request_value: ReviewDraftRequest) -> ReviewDraftReceipt:
        recovery_port.recover_calls += 1
        assert request_value == candidate
        fail_editorial_pilot(EditorialPilotFailureCode.OUTCOME_AMBIGUOUS)

    monkeypatch.setattr(recovery_port, "recover", fail_recovery)
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, recovery_port)
    persisted = journal.request_for_recovery(candidate.article_id)
    with pytest.raises(EditorialPilotFailure) as first:
        journal.recover(persisted)
    assert first.value.code is EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
    with pytest.raises(EditorialPilotFailure) as second:
        journal.request_for_recovery(candidate.article_id)
    assert second.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    with pytest.raises(EditorialPilotFailure) as verify:
        journal.committed_request(candidate.article_id)
    assert verify.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    with pytest.raises(EditorialPilotFailure) as direct_retry:
        journal.recover(candidate)
    assert direct_retry.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    assert recovery_port.recover_calls == 1


def test_remote_create_success_with_commit_failure_remains_recoverable(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = request()
    live = FakeOwnerLivePort(private_root)
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, live)
    original_write = journal_module._write_private_atomic  # type: ignore[attr-defined]
    calls = 0

    def fail_commit(path: Path, document: dict[str, object]) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            fail_editorial_pilot(EditorialPilotFailureCode.JOURNAL_UNSAFE)
        original_write(path, document)

    monkeypatch.setattr(journal_module, "_write_private_atomic", fail_commit)
    with pytest.raises(EditorialPilotFailure) as failed_commit:
        journal.create(candidate)
    assert failed_commit.value.code is EditorialPilotFailureCode.JOURNAL_UNSAFE
    assert live.create_calls == 1
    assert json.loads(_live_journal_path(private_root, candidate).read_text())[
        "state"
    ] == ("INTENT")
    assert (private_root / request_artifact_relative_path(candidate)).is_file()

    monkeypatch.setattr(journal_module, "_write_private_atomic", original_write)
    recovery_port = FakeOwnerLivePort(private_root)
    recovery = OwnerPrivateLiveReviewDraftJournal(private_root, recovery_port)
    persisted = recovery.request_for_recovery(candidate.article_id)
    receipt = recovery.recover(persisted)
    assert receipt.disposition is ReviewDraftDisposition.OWNER_LIVE_RECOVERED
    assert recovery_port.create_calls == 0
    assert recovery_port.recover_calls == 1
    assert recovery.committed_request(candidate.article_id) == (candidate, 1704)


def test_artifact_persistence_failure_happens_before_intent_and_remote_post(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = request()
    live = FakeOwnerLivePort(private_root)
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, live)

    def refuse_artifact(*_args: object, **_kwargs: object) -> bytes:
        fail_editorial_pilot(EditorialPilotFailureCode.JOURNAL_UNSAFE)

    monkeypatch.setattr(journal_module, "_write_private_immutable", refuse_artifact)
    with pytest.raises(EditorialPilotFailure) as failure:
        journal.create(candidate)
    assert failure.value.code is EditorialPilotFailureCode.JOURNAL_UNSAFE
    assert live.create_calls == 0
    assert not _live_journal_path(private_root, candidate).exists()


@pytest.mark.parametrize("mutation", ["content", "mode", "missing"])
def test_committed_request_rejects_tampered_or_unsafe_artifact(
    private_root: Path, mutation: str
) -> None:
    candidate = request()
    journal = OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    )
    journal.create(candidate)
    artifact_path = private_root / request_artifact_relative_path(candidate)
    if mutation == "content":
        document = json.loads(artifact_path.read_text(encoding="utf-8"))
        document["request"]["content"] += "<p>tampered</p>"
        material = {
            key: value for key, value in document.items() if key != "integrity_sha256"
        }
        document["integrity_sha256"] = canonical_sha256(material)
        artifact_path.write_bytes(canonical_json_bytes(document) + b"\n")
        artifact_path.chmod(0o600)
    elif mutation == "mode":
        artifact_path.chmod(0o644)
    elif mutation == "missing":
        artifact_path.rename(artifact_path.with_suffix(".held"))
    else:
        raise AssertionError("unknown mutation")
    with pytest.raises(EditorialPilotFailure) as failure:
        journal.committed_request(candidate.article_id)
    assert failure.value.code in {
        EditorialPilotFailureCode.JOURNAL_AMBIGUOUS,
        EditorialPilotFailureCode.JOURNAL_MISMATCH,
        EditorialPilotFailureCode.JOURNAL_UNSAFE,
    }


def test_committed_request_rejects_multiple_journals_but_ignores_orphan_artifact(
    private_root: Path,
) -> None:
    candidate = request()
    live = FakeOwnerLivePort(private_root)
    journal = OwnerPrivateLiveReviewDraftJournal(private_root, live)
    journal.create(candidate)
    other = request(packet_sha256="b" * 64)
    _install_orphan_request_artifact(private_root, other)

    assert journal.committed_request(candidate.article_id) == (candidate, 1704)
    with pytest.raises(EditorialPilotFailure) as stale_create:
        journal.create(other)
    assert stale_create.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    assert live.create_calls == 1

    original_journal = _live_journal_path(private_root, candidate)
    duplicate_journal = original_journal.with_name(
        f"{candidate.article_id}.{'c' * 64}.live.v1.json"
    )
    payload = original_journal.read_bytes()
    descriptor = os.open(
        duplicate_journal,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        assert os.write(descriptor, payload) == len(payload)
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    with pytest.raises(EditorialPilotFailure) as multiple:
        journal.committed_request(candidate.article_id)
    assert multiple.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS


def test_generation_ledger_bootstraps_legacy_and_atomically_activates_successor(
    private_root: Path,
) -> None:
    predecessor = request()
    successor = request(
        packet_sha256="b" * 64,
        content='<p class="ks-lead">新しい一次情報で条件を再確認します。</p>',
    )
    live_journal = OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    )
    live_journal.create(predecessor)
    old_journal_path = _live_journal_path(private_root, predecessor)
    old_artifact_path = private_root / request_artifact_relative_path(predecessor)
    old_journal_raw = old_journal_path.read_bytes()
    old_artifact_raw = old_artifact_path.read_bytes()
    ledger = OwnerPrivateReviewDraftGenerationLedger(private_root)
    binding = _revision(predecessor, successor, generation=2)

    assert ledger.active_request(predecessor.article_id) == (
        predecessor,
        1704,
        1,
    )
    assert ledger.revision_preparation_context(predecessor.article_id) == (
        predecessor,
        1704,
        2,
    )
    assert ledger.propose(binding) == binding
    assert ledger.propose(binding) == binding
    with pytest.raises(EditorialPilotFailure) as pending_preparation:
        ledger.revision_preparation_context(predecessor.article_id)
    assert pending_preparation.value.code is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    assert ledger.pending_binding(predecessor.article_id) == binding
    assert ledger.revision_binding(
        predecessor.article_id, binding.operation_sha256
    ) == binding
    assert ledger.active_request(predecessor.article_id) == (
        predecessor,
        1704,
        1,
    )
    assert live_journal.committed_request(predecessor.article_id) == (
        predecessor,
        1704,
    )
    assert old_journal_path.read_bytes() == old_journal_raw
    assert old_artifact_path.read_bytes() == old_artifact_raw
    assert (private_root / request_artifact_relative_path(successor)).is_file()
    assert len(
        list(
            (
                private_root / ".secrets" / OWNER_DIRECTORY / REQUEST_DIRECTORY
            ).glob(f"{predecessor.article_id}.*.request.v1.json")
        )
    ) == 2

    ledger.mark_attempted(binding)
    applied = _revision_observation(
        binding, ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED
    )
    assert ledger.commit(binding, applied) == (successor, 1704, 2)
    assert ledger.commit(binding, applied) == (successor, 1704, 2)
    # A process may die after the generation ledger commits but before the
    # publication intent is cleared. The exact completed binding remains
    # reconstructable and an apply replay must not overwrite its audit result.
    assert ledger.revision_bindings(predecessor.article_id) == (binding,)
    assert ledger.mark_attempted(binding) == binding
    assert ledger.recover(
        binding,
        _revision_observation(
            binding,
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
            response_sha256="f" * 64,
        ),
    ) == (successor, 1704, 2)
    assert ledger.active_request(predecessor.article_id) == (successor, 1704, 2)
    assert live_journal.committed_request(predecessor.article_id) == (
        successor,
        1704,
    )
    assert ledger.revision_binding(predecessor.article_id) == binding
    verified = _revision_observation(
        binding,
        ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
        response_sha256="f" * 64,
    )
    assert ledger.verify(binding, verified) == (successor, 1704, 2)
    assert old_journal_path.read_bytes() == old_journal_raw
    assert old_artifact_path.read_bytes() == old_artifact_raw
    generation_path = _generation_ledger_path(private_root, predecessor.article_id)
    assert generation_path.stat().st_mode & 0o777 == 0o600
    document = json.loads(generation_path.read_text(encoding="utf-8"))
    assert document["active_generation"] == 2
    assert document["pending"] is None
    assert [entry["generation"] for entry in document["generations"]] == [1, 2]
    assert document["generations"][1]["operation_sha256"] == (
        binding.operation_sha256
    )
    assert document["generations"][1]["outcome"] == (
        ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED.value
    )
    assert document["generations"][1]["response_sha256"] == (
        applied.response_sha256
    )


def test_generation_recovery_keeps_predecessor_active_and_retains_failed_audit(
    private_root: Path,
) -> None:
    predecessor = request()
    OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    ).create(predecessor)
    ledger = OwnerPrivateReviewDraftGenerationLedger(private_root)
    rejected_successor = request(
        packet_sha256="b" * 64,
        content='<p class="ks-lead">確認対象を更新します。</p>',
    )
    rejected = _revision(predecessor, rejected_successor, generation=2)
    ledger.propose(rejected)
    recovered_predecessor = _revision_observation(
        rejected,
        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR,
    )

    assert ledger.recover(rejected, recovered_predecessor) == (
        predecessor,
        1704,
        1,
    )
    assert ledger.revision_bindings(predecessor.article_id) == (rejected,)
    assert ledger.revision_preparation_context(predecessor.article_id) == (
        predecessor,
        1704,
        3,
    )
    assert ledger.recover(rejected, recovered_predecessor) == (
        predecessor,
        1704,
        1,
    )
    with pytest.raises(EditorialPilotFailure) as no_active_revision:
        ledger.revision_binding(predecessor.article_id)
    assert (
        no_active_revision.value.code
        is EditorialPilotFailureCode.JOURNAL_AMBIGUOUS
    )

    applied_successor = request(
        packet_sha256="c" * 64,
        content='<p class="ks-lead">再取得した一次情報で条件を確定します。</p>',
    )
    applied = _revision(predecessor, applied_successor, generation=3)
    ledger.propose(applied)
    # A newer offline generation may be staged after the remote outcome was
    # finalized but before its separate publication intent was cleared. The
    # exact older predecessor recovery remains replayable without touching it.
    assert ledger.recover(rejected, recovered_predecessor) == (
        predecessor,
        1704,
        1,
    )
    assert ledger.pending_binding(predecessor.article_id) == applied
    ledger.mark_attempted(applied)
    recovered_applied = _revision_observation(
        applied,
        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
        response_sha256="f" * 64,
    )
    assert ledger.recover(applied, recovered_applied) == (
        applied_successor,
        1704,
        3,
    )
    document = json.loads(
        _generation_ledger_path(private_root, predecessor.article_id).read_text(
            encoding="utf-8"
        )
    )
    assert document["active_generation"] == 3
    assert len(document["generations"]) == 3
    assert document["generations"][1]["outcome"] == (
        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_PREDECESSOR.value
    )
    assert document["generations"][2]["predecessor_generation"] == 1
    assert document["generations"][2]["outcome"] == (
        ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED.value
    )
    assert len(
        list(
            (
                private_root / ".secrets" / OWNER_DIRECTORY / REQUEST_DIRECTORY
            ).glob(f"{predecessor.article_id}.*.request.v1.json")
        )
    ) == 3


def test_completed_success_replay_survives_a_newer_pending_generation(
    private_root: Path,
) -> None:
    predecessor = request()
    OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    ).create(predecessor)
    ledger = OwnerPrivateReviewDraftGenerationLedger(private_root)
    successor = request(
        packet_sha256="b" * 64,
        content='<p class="ks-lead">第二世代を確定します。</p>',
    )
    completed = _revision(predecessor, successor, generation=2)
    ledger.propose(completed)
    ledger.mark_attempted(completed)
    original = _revision_observation(
        completed,
        ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED,
    )
    ledger.commit(completed, original)

    later_request = request(
        packet_sha256="c" * 64,
        content='<p class="ks-lead">第三世代をオフラインで準備します。</p>',
    )
    later = _revision(successor, later_request, generation=3)
    ledger.propose(later)

    assert ledger.mark_attempted(completed) == completed
    assert ledger.recover(
        completed,
        _revision_observation(
            completed,
            ReviewDraftRevisionDisposition.OWNER_LIVE_RECOVERED_APPLIED,
            response_sha256="f" * 64,
        ),
    ) == (successor, 1704, 2)
    assert ledger.revision_binding(
        predecessor.article_id, completed.operation_sha256
    ) == completed
    assert ledger.verify(
        completed,
        _revision_observation(
            completed,
            ReviewDraftRevisionDisposition.OWNER_LIVE_VERIFIED,
            response_sha256="e" * 64,
        ),
    ) == (successor, 1704, 2)
    assert ledger.pending_binding(predecessor.article_id) == later
    document = json.loads(
        _generation_ledger_path(private_root, predecessor.article_id).read_text(
            encoding="utf-8"
        )
    )
    assert document["active_generation"] == 2
    assert document["pending"]["successor_generation"] == 3
    assert document["generations"][1]["outcome"] == original.disposition.value
    assert document["generations"][1]["response_sha256"] == (
        original.response_sha256
    )


def test_generation_ledger_cas_rejects_competing_binding_and_draft_id_drift(
    private_root: Path,
) -> None:
    predecessor = request()
    OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    ).create(predecessor)
    ledger = OwnerPrivateReviewDraftGenerationLedger(private_root)
    successor = request(
        packet_sha256="b" * 64,
        content='<p class="ks-lead">新しい証拠へ更新します。</p>',
    )
    binding = _revision(predecessor, successor, generation=2)
    with pytest.raises(EditorialPilotFailure) as wrong_draft:
        ledger.propose(
            _revision(predecessor, successor, generation=2, draft_id=1705)
        )
    assert wrong_draft.value.code is EditorialPilotFailureCode.JOURNAL_MISMATCH
    ledger.propose(binding)
    competing = _revision(
        predecessor,
        request(
            packet_sha256="c" * 64,
            content='<p class="ks-lead">競合する別の更新です。</p>',
        ),
        generation=2,
    )
    with pytest.raises(EditorialPilotFailure) as competing_failure:
        ledger.propose(competing)
    assert competing_failure.value.code is EditorialPilotFailureCode.JOURNAL_MISMATCH

    assert ledger.mark_attempted(binding) == binding
    assert ledger.mark_attempted(binding) == binding
    wrong_observation = ReviewDraftRevisionObservation(
        operation_sha256="0" * 64,
        response_sha256="e" * 64,
        draft_id=binding.draft_id,
        disposition=ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED,
    )
    with pytest.raises(EditorialPilotFailure) as wrong_outcome:
        ledger.commit(binding, wrong_observation)
    assert wrong_outcome.value.code is EditorialPilotFailureCode.OUTCOME_AMBIGUOUS
    assert ledger.pending_binding(predecessor.article_id) == binding

    ledger.commit(
        binding,
        _revision_observation(
            binding, ReviewDraftRevisionDisposition.OWNER_LIVE_APPLIED
        ),
    )
    generation_path = _generation_ledger_path(private_root, predecessor.article_id)
    document = json.loads(generation_path.read_text(encoding="utf-8"))
    document["draft_id"] = 1705
    material = {
        key: value for key, value in document.items() if key != "integrity_sha256"
    }
    document["integrity_sha256"] = canonical_sha256(material)
    generation_path.write_bytes(canonical_json_bytes(document) + b"\n")
    generation_path.chmod(0o600)
    with pytest.raises(EditorialPilotFailure) as drift:
        ledger.active_request(predecessor.article_id)
    assert drift.value.code is EditorialPilotFailureCode.JOURNAL_MISMATCH


def test_generation_ledger_rejects_more_than_thirty_two_generations(
    private_root: Path,
) -> None:
    predecessor = request()
    OwnerPrivateLiveReviewDraftJournal(
        private_root, FakeOwnerLivePort(private_root)
    ).create(predecessor)
    ledger = OwnerPrivateReviewDraftGenerationLedger(private_root)
    successor = request(
        packet_sha256="b" * 64,
        content='<p class="ks-lead">上限検証用の更新です。</p>',
    )
    binding = _revision(predecessor, successor, generation=2)
    ledger.propose(binding)
    generation_path = _generation_ledger_path(private_root, predecessor.article_id)
    document = json.loads(generation_path.read_text(encoding="utf-8"))
    document["generations"] = document["generations"] * 17
    material = {
        key: value for key, value in document.items() if key != "integrity_sha256"
    }
    document["integrity_sha256"] = canonical_sha256(material)
    generation_path.write_bytes(canonical_json_bytes(document) + b"\n")
    generation_path.chmod(0o600)

    with pytest.raises(EditorialPilotFailure) as oversized:
        ledger.active_request(predecessor.article_id)
    assert oversized.value.code is EditorialPilotFailureCode.JOURNAL_MISMATCH


def test_symlinked_owner_layout_fails_closed(private_root: Path) -> None:
    tmp_path = private_root
    (tmp_path / ".secrets").symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    with pytest.raises(EditorialPilotFailure) as failure:
        OwnerPrivateReviewDraftJournal(
            tmp_path, RecordedWordPressReviewDraftAdapter()
        ).create(request(), create_evidence(request()))
    assert failure.value.code is EditorialPilotFailureCode.JOURNAL_UNSAFE
