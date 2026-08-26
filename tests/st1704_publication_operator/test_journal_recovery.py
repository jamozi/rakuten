"""Owner-private v2 intent journal and crash-recovery tests."""

from __future__ import annotations

from collections.abc import Iterator
import os
from pathlib import Path
import tempfile

import pytest

from raos.adapters.self_hosted_wordpress_publication_operator_journal_v2 import (
    OwnerPrivatePublicationProposalJournalV2,
    PUBLICATION_INTENT_FILE,
    PUBLICATION_INTENT_RELATIVE_DIRECTORY,
    PUBLICATION_INTENT_STAGING_FILE,
    PublicationIntentPhase,
    PublicationProposalIntent,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    CommittedReviewDraftBinding,
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationProposal,
)


@pytest.fixture
def private_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-publication-journal-", dir="/var/tmp"
    ) as directory:
        root = Path(directory)
        secrets = root / ".secrets"
        operator = secrets / "wordpress-operator-local"
        secrets.mkdir(mode=0o700)
        operator.mkdir(mode=0o700)
        yield root


def proposal(token: str = "5" * 64) -> PublicationProposal:
    binding = CommittedReviewDraftBinding(
        article_id="st1704-portable-power-station-guide",
        draft_post_id=28,
        packet_sha256="1" * 64,
        request_sha256="2" * 64,
        snapshot_payload_sha256="3" * 64,
        visible_content_sha256="4" * 64,
        public_slug="portable-power-station-guide",
    )
    return PublicationProposal.bind(binding, token)


def _intent_path(root: Path) -> Path:
    return root / PUBLICATION_INTENT_RELATIVE_DIRECTORY / PUBLICATION_INTENT_FILE


def test_one_global_intent_advances_durably_and_clears_only_exact_match(
    private_root: Path,
) -> None:
    candidate = proposal()
    journal = OwnerPrivatePublicationProposalJournalV2(private_root)
    with journal.exclusive():
        created = journal.record_create_intent(candidate)
        assert created.phase is PublicationIntentPhase.CREATE_INTENT
        proposed = journal.advance(
            candidate,
            expected=PublicationIntentPhase.CREATE_INTENT,
            target=PublicationIntentPhase.PROPOSED,
        )
        assert proposed.phase is PublicationIntentPhase.PROPOSED
        applying = journal.advance(
            candidate,
            expected=PublicationIntentPhase.PROPOSED,
            target=PublicationIntentPhase.APPLY_INTENT,
        )
        assert applying.phase is PublicationIntentPhase.APPLY_INTENT
        with pytest.raises(PublicationOperatorFailure) as different:
            journal.require_matching(proposal("6" * 64))
        assert different.value.code is PublicationOperatorFailureCode.JOURNAL_MISMATCH
        assert journal.load() == applying
        journal.clear_matching(candidate)
        assert journal.load() is None

    path = _intent_path(private_root)
    assert not path.exists()
    assert path.parent.stat().st_mode & 0o777 == 0o700


def test_crash_staging_is_promoted_only_for_exact_next_phase(
    private_root: Path,
) -> None:
    candidate = proposal()
    journal = OwnerPrivatePublicationProposalJournalV2(private_root)
    with journal.exclusive():
        journal.record_create_intent(candidate)
    directory = private_root / PUBLICATION_INTENT_RELATIVE_DIRECTORY
    staged = PublicationProposalIntent.from_proposal(
        candidate, PublicationIntentPhase.PROPOSED
    )
    staging = directory / PUBLICATION_INTENT_STAGING_FILE
    staging.write_bytes(staged.canonical_bytes())
    staging.chmod(0o600)

    rebound = OwnerPrivatePublicationProposalJournalV2(private_root)
    with rebound.exclusive():
        assert rebound.load() == staged
    assert not staging.exists()
    assert _intent_path(private_root).stat().st_mode & 0o777 == 0o600


def test_corruption_symlink_hardlink_and_second_intent_fail_closed(
    private_root: Path,
) -> None:
    candidate = proposal()
    journal = OwnerPrivatePublicationProposalJournalV2(private_root)
    with journal.exclusive():
        journal.record_create_intent(candidate)
        with pytest.raises(PublicationOperatorFailure) as second:
            journal.record_create_intent(proposal("6" * 64))
        assert second.value.code is PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS

    path = _intent_path(private_root)
    sibling = path.with_name("unexpected-hardlink")
    os.link(path, sibling)
    locked = OwnerPrivatePublicationProposalJournalV2(private_root)
    with locked.exclusive():
        with pytest.raises(PublicationOperatorFailure):
            locked.load()


def test_effective_uid_is_used_even_if_real_uid_differs(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(os, "getuid", lambda: os.geteuid() + 1)
    journal = OwnerPrivatePublicationProposalJournalV2(private_root)
    with journal.exclusive():
        journal.record_create_intent(proposal())
        assert journal.load() is not None
