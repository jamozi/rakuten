"""Focused coverage for the additive fixed-ID Review Draft revision path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scripts.st1704_wordpress_publication_operator_v2 as cli

from raos.domain.editorial.self_hosted_editorial_pilot import (
    PILOT_AUTHOR_NAME,
    PILOT_ORIGIN,
    PublicationSnapshot,
    PublicationSnapshotPayload,
    ReviewDraftRequest,
    bytes_sha256,
)
from raos.domain.operations.self_hosted_wordpress_draft_revision_operator_v2 import (
    DRAFT_REVISION_RECOVERY_RESULT_CODE,
    DRAFT_REVISION_RESULT_CODE,
    DRAFT_REVISION_VERIFY_RESULT_CODE,
    DraftRevisionApplyReceipt,
    DraftRevisionOperatorStatus,
    DraftRevisionProposal,
    DraftRevisionRecoveryDisposition,
    DraftRevisionRecoveryReceipt,
    DraftRevisionVerifyReceipt,
)
from raos.domain.operations.self_hosted_wordpress_publication_operator_v2 import (
    PublicationOperatorFailure,
    PublicationOperatorFailureCode,
    PublicationOperatorOperation,
    PublicationProposalState,
)
from raos.ports.self_hosted_editorial_pilot import ReviewDraftRevisionBinding


ROOT = Path(__file__).resolve().parents[2]
CONTROLLER = (
    ROOT
    / "changes/st-1704/publication-operator-v2/wordpress-plugin/"
    "raos-bounded-operator/includes/st1704-publication-controller.v2.php"
)
BINDINGS = CONTROLLER.with_name("st1704-publication-bindings.v2.php")


def request(packet: str, content: str) -> ReviewDraftRequest:
    slug = "portable-power-station-guide"
    title = "停電対策用ポータブル電源の選び方"
    description = "容量・定格出力・持ち運びの条件を一次情報から整理します。"
    snapshot = PublicationSnapshot.bind(
        PublicationSnapshotPayload(
            article_id="st1704-portable-power-station-guide",
            packet_sha256=packet,
            slug=slug,
            title=title,
            seo_title="停電対策用ポータブル電源4モデル比較",
            description=description,
            canonical_url=f"{PILOT_ORIGIN}/{slug}/",
            og_title=title,
            og_description=description,
            published_at=None,
            modified_at=None,
            author_name=PILOT_AUTHOR_NAME,
            section="備え",
            visible_content_sha256=bytes_sha256(content.encode()),
        )
    )
    return ReviewDraftRequest.bind(
        article_id=snapshot.payload.article_id,
        packet_sha256=packet,
        title=title,
        public_slug=slug,
        excerpt=description,
        content=content,
        snapshot=snapshot,
    )


def revision_proposal() -> DraftRevisionProposal:
    binding = ReviewDraftRevisionBinding.bind(
        predecessor=request("1" * 64, "<p>旧世代の本文です。</p>"),
        successor=request("2" * 64, "<p>fresh evidence世代の本文です。</p>"),
        draft_id=28,
        generation=2,
    )
    return DraftRevisionProposal.bind(binding, "3" * 64)


def test_revision_proposal_binds_complete_successor_without_raw_body() -> None:
    proposal = revision_proposal()
    payload = proposal.payload()
    encoded = proposal.canonical_bytes()

    assert payload["operation"] == "REVISE_ST1704_DRAFT"
    assert payload["draft_post_id"] == 28
    assert payload["generation"] == 2
    assert payload["operation_sha256"] == proposal.binding.operation_sha256
    assert proposal.proposal_id == bytes_sha256(encoded)
    assert encoded.isascii()
    assert "fresh evidence世代" not in encoded.decode("ascii")
    assert set(payload["predecessor"]) == {
        "content_sha256",
        "packet_sha256",
        "payload_sha256",
        "request_sha256",
        "review_slug",
    }
    assert set(payload["successor"]) == {
        "content_base64",
        "content_sha256",
        "excerpt_base64",
        "packet_sha256",
        "payload_sha256",
        "request_sha256",
        "review_slug",
        "snapshot_base64",
        "title_base64",
    }
    assert json.loads(encoded) == payload


def test_completed_generation_reconstructs_exact_stale_publication_intent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate = revision_proposal()

    class CompletedGenerationLedger:
        def __init__(self, root: Path) -> None:
            assert root.is_absolute()

        def pending_binding(self, article_id: str) -> ReviewDraftRevisionBinding:
            del article_id
            raise AssertionError("completed generation has no pending binding")

        def revision_bindings(
            self, article_id: str
        ) -> tuple[ReviewDraftRevisionBinding, ...]:
            assert article_id == candidate.binding.successor.article_id
            return (candidate.binding,)

    monkeypatch.setattr(
        cli,
        "OwnerPrivateReviewDraftGenerationLedger",
        CompletedGenerationLedger,
    )
    resolved = cli._revision_proposal_from_intent(
        candidate.binding.successor.article_id,
        candidate.request_token,
        candidate.proposal_id,
    )
    assert resolved == candidate

    with pytest.raises(PublicationOperatorFailure) as mismatch:
        cli._revision_proposal_from_intent(
            candidate.binding.successor.article_id,
            candidate.request_token,
            "f" * 64,
        )
    assert mismatch.value.code is PublicationOperatorFailureCode.JOURNAL_MISMATCH


def test_php_review_request_hashes_use_utf8_canonical_json() -> None:
    php = CONTROLLER.read_text(encoding="utf-8")
    method_names = (
        ("normalize_revision_proposal_request", "fixed_articles"),
        ("capture_revision_state", "revision_before_state_matches"),
        ("revision_state_matches_successor", "register_admin_page"),
    )
    for current, following in method_names:
        start = php.index(f"function {current}")
        body = php[start : php.index(f"function {following}", start)]
        request_material = body[body.index("$request_material =") :]
        assert "$request_material = self::canonical_json(" in request_material
        assert "$request_material = self::canonical_ascii_json(" not in (
            request_material
        )
    assert "fresh evidence世代の本文です。" in (
        revision_proposal().binding.successor.content
    )


def test_revision_projection_preserves_legacy_publish_state_hash_semantics() -> None:
    php = CONTROLLER.read_text(encoding="utf-8")
    capture_start = php.index("function capture_post_storage")
    capture = php[capture_start : php.index("function capture_publication_state")]
    legacy_mutable = capture[
        capture.index("$mutable_columns = array(") : capture.index(
            "if ($revision_mutable_fields)"
        )
    ]
    for field in (
        "post_date",
        "post_date_gmt",
        "post_modified",
        "post_modified_gmt",
        "post_status",
        "post_name",
    ):
        assert f"'{field}'" in legacy_mutable
    for legacy_protected_field in ("post_content", "post_excerpt", "post_title"):
        assert f"'{legacy_protected_field}'" not in legacy_mutable
    assert "array('post_content', 'post_excerpt', 'post_title')" in capture

    publication_start = php.index("function capture_publication_state")
    publication = php[
        publication_start : php.index("function capture_operation_state")
    ]
    assert "$proposal['draft_post_id'],\n            $category\n        );" in publication
    revision_start = php.index("function capture_revision_state")
    revision = php[
        revision_start : php.index("function revision_before_state_matches")
    ]
    assert "$category,\n            $for_update,\n            true" in revision


def test_revision_receipts_and_separate_status_are_closed() -> None:
    proposal = revision_proposal()
    applied = DraftRevisionApplyReceipt(
        proposal_id=proposal.proposal_id,
        operation=PublicationOperatorOperation.REVISE_ST1704_DRAFT,
        result_code=DRAFT_REVISION_RESULT_CODE,
        replayed=False,
    )
    verified = DraftRevisionVerifyReceipt(
        proposal_id=proposal.proposal_id,
        operation=PublicationOperatorOperation.REVISE_ST1704_DRAFT,
        operation_sha256=proposal.binding.operation_sha256,
        draft_post_id=28,
        result_code=DRAFT_REVISION_VERIFY_RESULT_CODE,
    )
    status = DraftRevisionOperatorStatus(
        master_writes_enabled=True,
        publication_writes_enabled=True,
        writes_enabled=True,
    )
    assert applied.public_payload()["result_code"] == "ST1704_DRAFT_REVISED"
    assert verified.public_payload()["draft_post_id"] == 28
    assert status.public_payload()["supported_operations"] == [
        "REVISE_ST1704_DRAFT"
    ]


@pytest.mark.parametrize(
    ("proposal_state", "disposition"),
    [
        (
            PublicationProposalState.APPLIED,
            DraftRevisionRecoveryDisposition.SUCCESSOR,
        ),
        (
            PublicationProposalState.NEEDS_RECOVERY,
            DraftRevisionRecoveryDisposition.SUCCESSOR,
        ),
        *[
            (state, DraftRevisionRecoveryDisposition.PREDECESSOR)
            for state in (
                PublicationProposalState.PROPOSED,
                PublicationProposalState.APPROVED,
                PublicationProposalState.FAILED,
                PublicationProposalState.NEEDS_RECOVERY,
                PublicationProposalState.EXPIRED,
            )
        ],
    ],
)
def test_revision_recovery_receipt_accepts_only_observable_terminal_dispositions(
    proposal_state: PublicationProposalState,
    disposition: DraftRevisionRecoveryDisposition,
) -> None:
    candidate = revision_proposal()
    receipt = DraftRevisionRecoveryReceipt(
        proposal_id=candidate.proposal_id,
        operation=PublicationOperatorOperation.REVISE_ST1704_DRAFT,
        operation_sha256=candidate.binding.operation_sha256,
        draft_post_id=candidate.binding.draft_id,
        proposal_state=proposal_state,
        disposition=disposition,
    )

    assert receipt.public_payload() == {
        "disposition": disposition.value,
        "draft_post_id": candidate.binding.draft_id,
        "operation": "REVISE_ST1704_DRAFT",
        "operation_sha256": candidate.binding.operation_sha256,
        "proposal_id": candidate.proposal_id,
        "proposal_state": proposal_state.value,
        "result_code": DRAFT_REVISION_RECOVERY_RESULT_CODE,
    }


@pytest.mark.parametrize(
    ("proposal_state", "disposition"),
    [
        (state, disposition)
        for state in PublicationProposalState
        for disposition in DraftRevisionRecoveryDisposition
        if (state, disposition)
        not in {
            (
                PublicationProposalState.APPLIED,
                DraftRevisionRecoveryDisposition.SUCCESSOR,
            ),
            (
                PublicationProposalState.NEEDS_RECOVERY,
                DraftRevisionRecoveryDisposition.SUCCESSOR,
            ),
            *{
                (predecessor_state, DraftRevisionRecoveryDisposition.PREDECESSOR)
                for predecessor_state in (
                    PublicationProposalState.PROPOSED,
                    PublicationProposalState.APPROVED,
                    PublicationProposalState.FAILED,
                    PublicationProposalState.NEEDS_RECOVERY,
                    PublicationProposalState.EXPIRED,
                )
            },
        }
    ],
)
def test_revision_recovery_receipt_rejects_ambiguous_state_disposition_pairs(
    proposal_state: PublicationProposalState,
    disposition: DraftRevisionRecoveryDisposition,
) -> None:
    candidate = revision_proposal()
    with pytest.raises(PublicationOperatorFailure) as failure:
        DraftRevisionRecoveryReceipt(
            proposal_id=candidate.proposal_id,
            operation=PublicationOperatorOperation.REVISE_ST1704_DRAFT,
            operation_sha256=candidate.binding.operation_sha256,
            draft_post_id=candidate.binding.draft_id,
            proposal_state=proposal_state,
            disposition=disposition,
        )

    assert failure.value.code is PublicationOperatorFailureCode.RESPONSE_INVALID


def test_php_boundary_is_literal_id_draft_only_atomic_and_human_gated() -> None:
    php = CONTROLLER.read_text(encoding="utf-8")
    bindings = BINDINGS.read_text(encoding="utf-8")

    assert "const REVISION_OPERATION = 'REVISE_ST1704_DRAFT';" in php
    assert "const REVISION_RESULT_CODE = 'ST1704_DRAFT_REVISED';" in php
    assert "private function normalize_revision_proposal_request" in php
    assert "private function capture_revision_state" in php
    assert "private function revision_state_matches_successor" in php
    assert "private function execute_revision_apply_under_mutex" in php
    assert "private function apply_one_revision" in php
    assert "public function rest_verify_revision" in php
    assert "wp_check_password(" in php
    assert "proposer_user_id <> %d" in php
    assert "BINARY post_status = BINARY %s" in php
    assert "'draft'" in php
    assert "SET post_content = %s, post_excerpt = %s, post_title = %s" in php
    assert "SET meta_value = %s" in php
    assert "SET state = %s, result_code = %s, completed_at = %s" in php
    assert php.index("SET post_content = %s") < php.index(
        "SET state = %s, result_code = %s, completed_at = %s",
        php.index("private function apply_one_revision"),
    )
    assert '"st1704-portable-power-station-guide":28' in bindings
    assert '"st1704-anker-solix-c300-c800-c1000-differences":29' in bindings
    assert '"st1704-countertop-dishwasher-for-small-households":41' in bindings
    assert '"st1704-compact-robot-vacuum-shortlist":30' in bindings


def test_php_revision_recovery_route_classifies_only_exact_terminal_state() -> None:
    php = CONTROLLER.read_text(encoding="utf-8")
    start = php.index("public function rest_recover_revision_state")
    recovery = php[start : php.index("public function rest_apply", start)]

    assert "const REVISION_RECOVERY_RESULT_CODE" in php
    assert "'ST1704_DRAFT_REVISION_STATE_OBSERVED'" in php
    assert "'/proposals/(?P<proposal_id>[a-f0-9]{64})/revision-state'" in php
    assert "'callback' => array($this, 'rest_recover_revision_state')" in php
    assert "RAOS_ST1704_DRAFT_REVISION_RECOVERY_V2" in recovery
    assert "self::REVISION_RECOVERY_RESULT_CODE" in recovery
    assert "self::REVISION_OPERATION" in recovery
    assert "revision_state_matches_successor" in recovery
    assert "revision_before_state_matches" in recovery
    assert "approval_evidence_is_valid" in recovery
    for state in (
        "APPLIED",
        "PROPOSED",
        "APPROVED",
        "FAILED",
        "NEEDS_RECOVERY",
        "EXPIRED",
    ):
        assert f"'{state}'" in recovery
    assert "APPLYING remains recoverable only through the exact idempotent apply" in (
        recovery
    )
    assert "'SUCCESSOR'" in recovery
    assert "'PREDECESSOR'" in recovery


def test_publication_status_remains_byte_contract_compatible() -> None:
    php = CONTROLLER.read_text(encoding="utf-8")
    start = php.index("public function rest_status")
    end = php.index("public function rest_revision_status", start)
    status = php[start:end]
    assert "'operator_version' => self::VERSION" in status
    assert "'supported_operations' => array(self::OPERATION)" in status
    assert "REVISION_OPERATION" not in status
