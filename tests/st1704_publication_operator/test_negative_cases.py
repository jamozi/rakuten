"""Critical negative paths for exact publication and recovery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import tempfile

import pytest

import raos.adapters.self_hosted_wordpress_publication_operator_https_v2 as https
import scripts.st1704_wordpress_publication_operator_v2 as cli
from raos.adapters.self_hosted_wordpress_publication_operator_journal_v2 import (
    OwnerPrivatePublicationProposalJournalV2,
    PublicationIntentPhase,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PublicationApplyReceipt,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationOperatorOperation,
    PublicationProposal,
    PublicationProposalReceipt,
    PublicationProposalState,
    require_publish_article_id,
)


def _proposal() -> PublicationProposal:
    return PublicationProposal.bind(
        CommittedReviewDraftBinding(
            article_id="st1704-portable-power-station-guide",
            draft_post_id=28,
            packet_sha256="1" * 64,
            request_sha256="2" * 64,
            snapshot_payload_sha256="3" * 64,
            visible_content_sha256="4" * 64,
            public_slug="portable-power-station-guide",
        ),
        "5" * 64,
    )


def _time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_unknown_and_update_existing_articles_fail_before_any_network() -> None:
    for article_id in (
        "st1703-first-suitcase-comparison",
        "st1704-unknown-article",
        "",
    ):
        with pytest.raises(PublicationOperatorFailure) as failed:
            require_publish_article_id(article_id)
        assert (
            failed.value.code is PublicationOperatorFailureCode.ARTICLE_NOT_ALLOWLISTED
        )


def test_fresh_receipt_cannot_claim_recovery_or_terminal_state() -> None:
    candidate = _proposal()
    now = datetime.now(timezone.utc).replace(microsecond=0)
    with pytest.raises(PublicationOperatorFailure) as terminal:
        PublicationProposalReceipt(
            proposal_id=candidate.proposal_id,
            operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
            state=PublicationProposalState.APPROVED,
            created_at=_time(now),
            expires_at=_time(now + timedelta(seconds=900)),
            replayed=False,
        )
    assert terminal.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


def test_expired_exact_recovery_requires_new_proposal() -> None:
    candidate = _proposal()
    created = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
        state=PublicationProposalState.EXPIRED,
        created_at=_time(created),
        expires_at=_time(created + timedelta(seconds=900)),
        replayed=True,
    )
    assert receipt.is_expired()
    assert receipt.requires_new_proposal()


@pytest.mark.parametrize(
    "state",
    [PublicationProposalState.PROPOSED, PublicationProposalState.APPROVED],
)
def test_expired_nonterminal_recovery_clears_journal_and_requires_new_proposal(
    state: PublicationProposalState,
) -> None:
    candidate = _proposal()
    created = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
        state=state,
        created_at=_time(created),
        expires_at=_time(created + timedelta(seconds=900)),
        replayed=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-expired-recovery-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            assert cli._reconcile_receipt(journal, candidate, receipt) == 2
            assert journal.load() is None

    payload = cli._receipt_payload(receipt)
    assert payload["next_action"] == "NEW_PROPOSAL_REQUIRED"
    assert payload["approval_surface"] == "NOT_APPLICABLE"
    assert payload["human_approval_required"] is False


def test_verified_not_created_rejection_clears_create_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _proposal()

    class NotCreatedAdapter:
        def __init__(self, root: Path) -> None:
            assert root.is_absolute()

        def propose(self, observed: PublicationProposal) -> PublicationProposalReceipt:
            assert observed == candidate
            raise PublicationOperatorFailure(
                PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED
            )

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-not-created-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        monkeypatch.setattr(cli, "REPOSITORY_ROOT", root)
        monkeypatch.setattr(cli, "_request_token", lambda: candidate.request_token)
        monkeypatch.setattr(cli, "_proposal_from_intent", lambda *_args: candidate)
        monkeypatch.setattr(
            cli,
            "OfficialSelfHostedWordPressPublicationOperatorV2Adapter",
            NotCreatedAdapter,
        )
        with pytest.raises(PublicationOperatorFailure) as failed:
            cli._propose(candidate.binding.article_id)
        assert failed.value.code is PublicationOperatorFailureCode.PROPOSAL_NOT_CREATED
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            assert journal.load() is None


def test_exact_apply_intent_retry_reuses_only_the_bound_proposal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _proposal()
    calls: list[str] = []

    class ReplayingAdapter:
        def __init__(self, root: Path) -> None:
            assert root.is_absolute()

        def apply(self, observed_proposal_id: str) -> PublicationApplyReceipt:
            calls.append(observed_proposal_id)
            assert observed_proposal_id == candidate.proposal_id
            if len(calls) == 1:
                raise PublicationOperatorFailure(
                    PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
                )
            return PublicationApplyReceipt(
                proposal_id=candidate.proposal_id,
                operation=PublicationOperatorOperation.PUBLISH_ST1704_ARTICLE,
                result_code="ST1704_ARTICLE_PUBLISHED",
                replayed=True,
            )

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-apply-retry-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
        monkeypatch.setattr(cli, "REPOSITORY_ROOT", root)
        monkeypatch.setattr(cli, "_proposal_from_intent", lambda *_args: candidate)
        monkeypatch.setattr(
            cli,
            "OfficialSelfHostedWordPressPublicationOperatorV2Adapter",
            ReplayingAdapter,
        )

        with pytest.raises(PublicationOperatorFailure) as ambiguous:
            cli._apply(candidate.binding.article_id, candidate.proposal_id)
        assert ambiguous.value.code is PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
        with journal.exclusive():
            assert journal.load() is not None

        result = cli._apply(candidate.binding.article_id, candidate.proposal_id)

        assert result["replayed"] is True
        assert calls == [candidate.proposal_id, candidate.proposal_id]
        with journal.exclusive():
            assert journal.load() is None


def test_apply_intent_retry_with_a_different_proposal_id_fails_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = _proposal()

    class RejectNetworkAdapter:
        def __init__(self, root: Path) -> None:
            assert root.is_absolute()

        def apply(self, observed_proposal_id: str) -> PublicationApplyReceipt:
            del observed_proposal_id
            raise AssertionError("mismatched retry must not reach the network")

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-apply-mismatch-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.PROPOSED,
                target=PublicationIntentPhase.APPLY_INTENT,
            )
        monkeypatch.setattr(cli, "REPOSITORY_ROOT", root)
        monkeypatch.setattr(cli, "_proposal_from_intent", lambda *_args: candidate)
        monkeypatch.setattr(
            cli,
            "OfficialSelfHostedWordPressPublicationOperatorV2Adapter",
            RejectNetworkAdapter,
        )

        with pytest.raises(PublicationOperatorFailure) as failed:
            cli._apply(candidate.binding.article_id, "6" * 64)

        assert failed.value.code is PublicationOperatorFailureCode.JOURNAL_MISMATCH
        with journal.exclusive():
            assert journal.load() is not None


def test_exact_get_not_found_terminal_receipt_clears_create_intent() -> None:
    candidate = _proposal()
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=candidate.operation,
        state=PublicationProposalState.FAILED,
        created_at="1970-01-01T00:00:00Z",
        expires_at="1970-01-01T00:15:00Z",
        replayed=True,
    )
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-not-found-recovery-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            assert cli._reconcile_receipt(journal, candidate, receipt) == 2
            assert journal.load() is None


def test_needs_recovery_receipt_releases_apply_intent_without_success() -> None:
    candidate = _proposal()
    created = datetime.now(timezone.utc).replace(microsecond=0)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=candidate.operation,
        state=PublicationProposalState.NEEDS_RECOVERY,
        created_at=_time(created),
        expires_at=_time(created + timedelta(seconds=900)),
        replayed=True,
    )
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-needs-recovery-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.PROPOSED,
                target=PublicationIntentPhase.APPLY_INTENT,
            )
            assert cli._reconcile_receipt(journal, candidate, receipt) == 2
            assert journal.load() is None

    payload = cli._receipt_payload(receipt)
    assert payload["state"] == "NEEDS_RECOVERY"
    assert payload["next_action"] == "MANUAL_WORDPRESS_RECOVERY_REQUIRED"


def test_applying_receipt_directs_the_matching_apply_retry() -> None:
    candidate = _proposal()
    created = datetime.now(timezone.utc).replace(microsecond=0)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=candidate.operation,
        state=PublicationProposalState.APPLYING,
        created_at=_time(created),
        expires_at=_time(created + timedelta(seconds=900)),
        replayed=True,
    )

    payload = cli._receipt_payload(receipt)

    assert payload["state"] == "APPLYING"
    assert payload["next_action"] == "RUN_MATCHING_APPLY_COMMAND"


def test_expired_applying_receipt_preserves_exact_apply_retry() -> None:
    candidate = _proposal()
    created = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    receipt = PublicationProposalReceipt(
        proposal_id=candidate.proposal_id,
        operation=candidate.operation,
        state=PublicationProposalState.APPLYING,
        created_at=_time(created),
        expires_at=_time(created + timedelta(seconds=900)),
        replayed=True,
    )
    assert receipt.is_expired()
    assert not receipt.requires_new_proposal()

    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-expired-applying-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        private = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        private.mkdir(mode=0o700)
        journal = OwnerPrivatePublicationProposalJournalV2(root)
        with journal.exclusive():
            journal.record_create_intent(candidate)
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.CREATE_INTENT,
                target=PublicationIntentPhase.PROPOSED,
            )
            journal.advance(
                candidate,
                expected=PublicationIntentPhase.PROPOSED,
                target=PublicationIntentPhase.APPLY_INTENT,
            )
            assert cli._reconcile_receipt(journal, candidate, receipt) == 2
            preserved = journal.require_matching(candidate)
            assert preserved.phase is PublicationIntentPhase.APPLY_INTENT

    payload = cli._receipt_payload(receipt)
    assert payload["state"] == "APPLYING"
    assert payload["next_action"] == "RUN_MATCHING_APPLY_COMMAND"


def test_nonempty_tls_environment_is_rejected_without_proxy_false_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.setenv(name, "http://ignored.invalid")
    https.require_clean_publication_operator_environment()
    monkeypatch.setenv("SSLKEYLOGFILE", "/tmp/forbidden")
    with pytest.raises(PublicationOperatorFailure) as refused:
        https.require_clean_publication_operator_environment()
    assert refused.value.code is PublicationOperatorFailureCode.TRANSPORT_REFUSED


def test_journal_methods_require_exclusive_lock(tmp_path: Path) -> None:
    secrets = tmp_path / ".secrets"
    private = secrets / "wordpress-operator-local"
    secrets.mkdir(mode=0o700)
    private.mkdir(mode=0o700)
    journal = OwnerPrivatePublicationProposalJournalV2(tmp_path)
    with pytest.raises(PublicationOperatorFailure) as unlocked:
        journal.load()
    assert unlocked.value.code is PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS


def test_failure_repr_and_text_never_contain_payload_or_environment() -> None:
    secret = os.environ.get("RAOS_TEST_SECRET", "not-present")
    failure = PublicationOperatorFailure(
        PublicationOperatorFailureCode.OUTCOME_AMBIGUOUS
    )
    assert secret not in str(failure)
    assert secret not in repr(failure)
