"""Committed Review Draft provenance binding tests."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
import tempfile

import pytest

from raos.adapters.self_hosted_editorial_pilot_json import (
    OwnerPrivateLiveReviewDraftJournal,
    request_artifact_relative_path,
)
from raos.adapters.self_hosted_wordpress_publication_operator_json_v2 import (
    OwnerPrivateCommittedReviewDraftBindingAdapter,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    PublicVerification,
    ReviewDraftDisposition,
    ReviewDraftReceipt,
    ReviewDraftRequest,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
)
from test_domain import review_request


@pytest.fixture
def private_root() -> Iterator[Path]:
    with tempfile.TemporaryDirectory(
        prefix="raos-st1704-publication-binding-", dir="/var/tmp"
    ) as directory:
        yield Path(directory)


class _LiveDraftPort:
    def preflight(self, request: ReviewDraftRequest, command: str) -> None:
        assert request.article_id == "st1704-portable-power-station-guide"
        assert command == "create-review-draft"

    def resolve_public_target(
        self, request: ReviewDraftRequest, command: str
    ) -> int | None:
        self.preflight(request, command)
        return None

    def create(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        return ReviewDraftReceipt(
            article_id=request.article_id,
            packet_sha256=request.packet_sha256,
            request_sha256=request.request_sha256,
            response_sha256="a" * 64,
            draft_id=28,
            disposition=ReviewDraftDisposition.OWNER_LIVE_CREATED,
            target_public_post_id=None,
            recorded_evidence_only=False,
            live_authority=True,
        )

    def recover(self, request: ReviewDraftRequest) -> ReviewDraftReceipt:
        del request
        raise AssertionError("unexpected recovery")

    def verify_public(
        self, request: ReviewDraftRequest, expected_public_post_id: int
    ) -> PublicVerification:
        del request, expected_public_post_id
        raise AssertionError("unexpected public verification")


def _commit(root: Path) -> ReviewDraftRequest:
    request = review_request()
    receipt = OwnerPrivateLiveReviewDraftJournal(root, _LiveDraftPort()).create(request)
    assert receipt.draft_id == 28
    return request


def test_binding_comes_only_from_exact_committed_request_and_preserved_post_id(
    private_root: Path,
) -> None:
    request = _commit(private_root)

    binding = OwnerPrivateCommittedReviewDraftBindingAdapter(private_root).load(
        request.article_id
    )

    assert binding.article_id == request.article_id
    assert binding.draft_post_id == 28
    assert binding.packet_sha256 == request.packet_sha256
    assert binding.request_sha256 == request.request_sha256
    assert binding.snapshot_payload_sha256 == request.snapshot.payload_sha256
    assert binding.visible_content_sha256 == (
        request.snapshot.payload.visible_content_sha256
    )
    assert binding.public_slug == request.public_slug


def test_missing_or_tampered_committed_artifact_fails_closed(
    private_root: Path,
) -> None:
    adapter = OwnerPrivateCommittedReviewDraftBindingAdapter(private_root)
    with pytest.raises(PublicationOperatorFailure) as missing:
        adapter.load("st1704-portable-power-station-guide")
    assert missing.value.code in {
        PublicationOperatorFailureCode.JOURNAL_AMBIGUOUS,
        PublicationOperatorFailureCode.JOURNAL_UNSAFE,
    }

    request = _commit(private_root)
    artifact = private_root / request_artifact_relative_path(request)
    artifact.write_bytes(b"{}\n")
    artifact.chmod(0o600)
    with pytest.raises(PublicationOperatorFailure) as tampered:
        adapter.load(request.article_id)
    assert tampered.value.code in {
        PublicationOperatorFailureCode.JOURNAL_MISMATCH,
        PublicationOperatorFailureCode.JOURNAL_UNSAFE,
        PublicationOperatorFailureCode.REVIEW_BINDING_INVALID,
    }


def test_at003_is_rejected_before_any_review_journal_lookup(
    private_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("v2 attempted an AT-003 journal read")

    monkeypatch.setattr(
        OwnerPrivateLiveReviewDraftJournal,
        "committed_request",
        forbidden,
    )
    with pytest.raises(PublicationOperatorFailure) as refused:
        OwnerPrivateCommittedReviewDraftBindingAdapter(private_root).load(
            "st1703-first-suitcase-comparison"
        )
    assert refused.value.code is PublicationOperatorFailureCode.ARTICLE_NOT_ALLOWLISTED
