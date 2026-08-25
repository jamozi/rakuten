"""Focused lifecycle, authorization, and evidence-boundary tests for ST-0604 V2."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path
from uuid import UUID

import pytest

from raos.adapters.sqlite_source_packet_lifecycle_runtime_v2 import (
    OwnerPrivateSqliteSourcePacketStoreV2,
)
from raos.application.evidence.source_packet_lifecycle_runtime_v2 import (
    DurableSourcePacketLifecycleServiceV2,
)
from raos.domain.evidence.source_packet_lifecycle_runtime_v2 import (
    ApprovedLockedGenerationInputV2,
    SourcePacketCommandIdV2,
    SourcePacketCommandKindV2,
    SourcePacketCommandV2,
    SourcePacketFailureCodeV2,
    SourcePacketFailureV2,
    SourcePacketReviewDecisionV2,
    SourcePacketStatusV2,
    apply_source_packet_command_v2,
    command_from_mapping_v2,
    command_mapping_v2,
    content_from_mapping_v2,
    content_mapping_v2,
    generation_input_from_mapping_v2,
    generation_input_mapping_v2,
    state_from_mapping_v2,
    state_mapping_v2,
)
from tests.st0604.runtime_v2_fixtures import (
    ARTICLE_PLAN_ID,
    EDITOR_FINGERPRINT,
    PACKET_ID,
    REVIEW_ASSIGNMENT_ID,
    SITE_ID,
    AuthorizationFixtureV2,
    authorization_fixture_v2,
    source_content_v2,
    source_packet_runtime_v2,
    source_packet_store_v2,
)


def _failure(call: object) -> SourcePacketFailureCodeV2:
    assert callable(call)
    with pytest.raises(SourcePacketFailureV2) as caught:
        call()
    assert caught.value.__cause__ is None
    return caught.value.code


def _setup(
    tmp_path: Path,
) -> tuple[
    DurableSourcePacketLifecycleServiceV2,
    AuthorizationFixtureV2,
    OwnerPrivateSqliteSourcePacketStoreV2,
]:
    content = source_content_v2(tmp_path / "evidence")
    now = content.conflict_scan.committed_at + timedelta(minutes=1)
    authorization = authorization_fixture_v2(tmp_path / "auth", now=now)
    store = source_packet_store_v2(tmp_path / "store")
    runtime = source_packet_runtime_v2(authorization=authorization, store=store)
    runtime.create_packet(
        command_id=SourcePacketCommandIdV2("RECORDED:ST0604:CREATE"),
        packet_id=PACKET_ID,
        site_id=SITE_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        creator_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=now - timedelta(seconds=3),
    )
    runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:ST0604:VERSION:1"),
        packet_id=PACKET_ID,
        expected_revision=1,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=now - timedelta(seconds=2),
    )
    return runtime, authorization, store


def _approve_and_lock(
    runtime: DurableSourcePacketLifecycleServiceV2,
    authorization: AuthorizationFixtureV2,
    *,
    prefix: str = "1",
    submit_revision: int = 2,
) -> None:
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2(f"RECORDED:ST0604:SUBMIT:{prefix}"),
        packet_id=PACKET_ID,
        expected_revision=submit_revision,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    runtime.record_review(
        command_id=SourcePacketCommandIdV2(f"RECORDED:ST0604:APPROVE:{prefix}"),
        packet_id=PACKET_ID,
        expected_revision=submit_revision + 1,
        decision=SourcePacketReviewDecisionV2.APPROVE,
        site_id=SITE_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=authorization.now,
    )
    runtime.lock_version(
        command_id=SourcePacketCommandIdV2(f"RECORDED:ST0604:LOCK:{prefix}"),
        packet_id=PACKET_ID,
        expected_revision=submit_revision + 2,
        actor_fingerprint=authorization.result.session_fingerprint,
        occurred_at=authorization.now + timedelta(seconds=1),
    )


def test_unapproved_building_and_in_review_versions_cannot_generate(
    tmp_path: Path,
) -> None:
    runtime, authorization, _store = _setup(tmp_path)
    assert (
        _failure(
            lambda: runtime.read_generation_input(
                command_id=SourcePacketCommandIdV2("RECORDED:READ:BUILDING"),
                packet_id=PACKET_ID,
                expected_revision=2,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now,
            )
        )
        is SourcePacketFailureCodeV2.NOT_GENERATION_READY
    )
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:SUBMIT:INREVIEW"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    assert (
        _failure(
            lambda: runtime.read_generation_input(
                command_id=SourcePacketCommandIdV2("RECORDED:READ:INREVIEW"),
                packet_id=PACKET_ID,
                expected_revision=3,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now,
            )
        )
        is SourcePacketFailureCodeV2.NOT_GENERATION_READY
    )


def test_approved_but_unlocked_version_cannot_generate(tmp_path: Path) -> None:
    runtime, authorization, _store = _setup(tmp_path)
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:SUBMIT:UNLOCKED"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    runtime.record_review(
        command_id=SourcePacketCommandIdV2("RECORDED:APPROVE:UNLOCKED"),
        packet_id=PACKET_ID,
        expected_revision=3,
        decision=SourcePacketReviewDecisionV2.APPROVE,
        site_id=SITE_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=authorization.now,
    )
    assert (
        _failure(
            lambda: runtime.read_generation_input(
                command_id=SourcePacketCommandIdV2("RECORDED:READ:UNLOCKED"),
                packet_id=PACKET_ID,
                expected_revision=4,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now + timedelta(seconds=1),
            )
        )
        is SourcePacketFailureCodeV2.NOT_GENERATION_READY
    )


def test_exact_approved_current_locked_version_yields_generation_input(
    tmp_path: Path,
) -> None:
    runtime, authorization, store = _setup(tmp_path)
    _approve_and_lock(runtime, authorization)
    result = runtime.read_generation_input(
        command_id=SourcePacketCommandIdV2("RECORDED:ST0604:GENERATION:1"),
        packet_id=PACKET_ID,
        expected_revision=5,
        actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now + timedelta(seconds=2),
    )
    value = result.generation_input
    assert type(value) is ApprovedLockedGenerationInputV2
    assert value.packet_id == PACKET_ID
    assert value.version_number == 1
    assert value.content.fact_count == len(value.content.fact_membership)
    assert value.content.conflict_scan.batch.conflicts == ()
    assert value.content.conflict_scan.batch.queue == ()
    assert value.fact_membership_sha256 == value.content.fact_membership_sha256
    assert value.conflict_scan_sha256 == value.content.conflict_scan_sha256
    assert result.state.aggregate_revision == 6
    assert len(store.audit_snapshot()) == 6
    assert runtime.external_action_count == runtime.provider_action_count == 0
    assert runtime.publication_action_count == runtime.ai_action_count == 0


def test_rejection_is_terminal_for_version_and_cannot_lock_or_generate(
    tmp_path: Path,
) -> None:
    runtime, authorization, _store = _setup(tmp_path)
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:SUBMIT:REJECT"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    rejected = runtime.record_review(
        command_id=SourcePacketCommandIdV2("RECORDED:REJECT"),
        packet_id=PACKET_ID,
        expected_revision=3,
        decision=SourcePacketReviewDecisionV2.REJECT,
        site_id=SITE_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=authorization.now,
    )
    assert rejected.state.packet_status is SourcePacketStatusV2.REJECTED
    assert (
        _failure(
            lambda: runtime.lock_version(
                command_id=SourcePacketCommandIdV2("RECORDED:LOCK:REJECTED"),
                packet_id=PACKET_ID,
                expected_revision=4,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now + timedelta(seconds=1),
            )
        )
        is SourcePacketFailureCodeV2.IMMUTABLE_VERSION
    )
    assert (
        _failure(
            lambda: runtime.read_generation_input(
                command_id=SourcePacketCommandIdV2("RECORDED:READ:REJECTED"),
                packet_id=PACKET_ID,
                expected_revision=4,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now + timedelta(seconds=2),
            )
        )
        is SourcePacketFailureCodeV2.NOT_GENERATION_READY
    )


def test_edit_after_lock_creates_new_version_and_supersedes_without_mutating_old(
    tmp_path: Path,
) -> None:
    runtime, authorization, store = _setup(tmp_path)
    _approve_and_lock(runtime, authorization)
    old = store.load_state(PACKET_ID).current_version
    assert old is not None and old.lock is not None and old.review is not None
    content = source_content_v2(tmp_path / "evidence-v2", label="second")
    edited = runtime.create_version(
        command_id=SourcePacketCommandIdV2("RECORDED:ST0604:VERSION:2"),
        packet_id=PACKET_ID,
        expected_revision=5,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        content=content,
        occurred_at=authorization.now + timedelta(seconds=2),
    )
    assert len(edited.state.versions) == 2
    assert edited.state.versions[0].status is SourcePacketStatusV2.SUPERSEDED
    assert edited.state.versions[0].content_sha256 == old.content_sha256
    assert edited.state.versions[0].review == old.review
    assert edited.state.versions[0].lock == old.lock
    assert edited.state.current_version.status is SourcePacketStatusV2.BUILDING
    assert (
        _failure(
            lambda: runtime.read_generation_input(
                command_id=SourcePacketCommandIdV2("RECORDED:READ:NONCURRENT"),
                packet_id=PACKET_ID,
                expected_revision=6,
                actor_fingerprint=EDITOR_FINGERPRINT,
                occurred_at=authorization.now + timedelta(seconds=3),
            )
        )
        is SourcePacketFailureCodeV2.NOT_GENERATION_READY
    )


def test_backdated_lifecycle_command_cannot_reorder_immutable_history(
    tmp_path: Path,
) -> None:
    runtime, authorization, store = _setup(tmp_path)
    _approve_and_lock(runtime, authorization)
    content = source_content_v2(tmp_path / "backdated", label="backdated")
    assert (
        _failure(
            lambda: runtime.create_version(
                command_id=SourcePacketCommandIdV2("RECORDED:BACKDATED:VERSION"),
                packet_id=PACKET_ID,
                expected_revision=5,
                editor_actor_fingerprint=EDITOR_FINGERPRINT,
                content=content,
                occurred_at=authorization.now,
            )
        )
        is SourcePacketFailureCodeV2.STATE_CONFLICT
    )
    state = store.load_state(PACKET_ID)
    assert state is not None and state.aggregate_revision == 5


def test_unresolved_conflict_packet_is_rejected_before_persistence(
    tmp_path: Path,
) -> None:
    assert (
        _failure(lambda: source_content_v2(tmp_path / "conflicted", conflicting=True))
        is SourcePacketFailureCodeV2.UNRESOLVED_CONFLICT
    )


def test_content_rejects_a_conflict_scan_for_different_fact_membership(
    tmp_path: Path,
) -> None:
    left = source_content_v2(tmp_path / "left", label="left")
    right = source_content_v2(tmp_path / "right", label="right")
    assert _failure(lambda: replace(left, conflict_scan=right.conflict_scan)) in {
        SourcePacketFailureCodeV2.DEPENDENCY_MISMATCH,
        SourcePacketFailureCodeV2.UNRESOLVED_CONFLICT,
    }


def test_closed_mappings_are_byte_deterministic_and_reject_unknown_fields(
    tmp_path: Path,
) -> None:
    content = source_content_v2(tmp_path / "mapping")
    copied = content_from_mapping_v2(content_mapping_v2(content))
    assert copied == content
    document = content_mapping_v2(content)
    assert _failure(lambda: content_from_mapping_v2({**document, "unknown": 1})) is (
        SourcePacketFailureCodeV2.TAMPER_DETECTED
    )
    now = content.conflict_scan.committed_at + timedelta(minutes=1)
    create = SourcePacketCommandV2(
        command_id=SourcePacketCommandIdV2("RECORDED:MAPPING"),
        kind=SourcePacketCommandKindV2.CREATE_PACKET,
        packet_id=PACKET_ID,
        expected_revision=0,
        occurred_at=now,
        actor_fingerprint=EDITOR_FINGERPRINT,
        site_id=SITE_ID,
        article_plan_id=ARTICLE_PLAN_ID,
        review_assignment_id=REVIEW_ASSIGNMENT_ID,
    )
    state, _ = apply_source_packet_command_v2(None, create)
    assert command_from_mapping_v2(command_mapping_v2(create)) == create
    assert state_from_mapping_v2(state_mapping_v2(state)) == state


def test_generation_input_mapping_binds_lock_and_approval(tmp_path: Path) -> None:
    runtime, authorization, _store = _setup(tmp_path)
    _approve_and_lock(runtime, authorization)
    value = runtime.read_generation_input(
        command_id=SourcePacketCommandIdV2("RECORDED:GEN:MAPPING"),
        packet_id=PACKET_ID,
        expected_revision=5,
        actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now + timedelta(seconds=2),
    ).generation_input
    assert value is not None
    document = generation_input_mapping_v2(value)
    assert generation_input_from_mapping_v2(document) == value
    assert (
        _failure(
            lambda: generation_input_from_mapping_v2(
                {**document, "lock_sha256": hashlib.sha256(b"forged").hexdigest()}
            )
        )
        is SourcePacketFailureCodeV2.TAMPER_DETECTED
    )


@pytest.mark.parametrize(
    "site_id,assignment_id,operation_id,action,state",
    (
        (
            UUID("74345678-1234-4234-8234-123456789099"),
            REVIEW_ASSIGNMENT_ID,
            "PUBADM-004",
            "review_article",
            "IN_PROGRESS",
        ),
        (
            SITE_ID,
            UUID("74345678-1234-4234-8234-123456789099"),
            "PUBADM-004",
            "review_article",
            "IN_PROGRESS",
        ),
        (SITE_ID, REVIEW_ASSIGNMENT_ID, "ED-011", "review_article", "IN_PROGRESS"),
        (
            SITE_ID,
            REVIEW_ASSIGNMENT_ID,
            "PUBADM-004",
            "edit_article_draft",
            "IN_PROGRESS",
        ),
        (SITE_ID, REVIEW_ASSIGNMENT_ID, "PUBADM-004", "review_article", "DRAFT"),
    ),
)
def test_wrong_recorded_authorization_binding_fails_closed(
    tmp_path: Path,
    site_id: UUID,
    assignment_id: UUID,
    operation_id: str,
    action: str,
    state: str,
) -> None:
    runtime, valid, _store = _setup(tmp_path)
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:SUBMIT:AUTH-NEG"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=valid.now - timedelta(seconds=1),
    )
    invalid = authorization_fixture_v2(
        tmp_path / "invalid-auth",
        site_id=site_id,
        review_assignment_id=assignment_id,
        operation_id=operation_id,
        action=action,
        state=state,
        label=f"NEG-{operation_id}-{action}-{state}",
        now=valid.now,
    )
    assert (
        _failure(
            lambda: runtime.record_review(
                command_id=SourcePacketCommandIdV2("RECORDED:REVIEW:AUTH-NEG"),
                packet_id=PACKET_ID,
                expected_revision=3,
                decision=SourcePacketReviewDecisionV2.APPROVE,
                site_id=SITE_ID,
                review_assignment_id=REVIEW_ASSIGNMENT_ID,
                session_id=invalid.session.session_id,
                authorization_command=invalid.command,
                authorization_result=invalid.result,
                authorization_checked_at=invalid.now,
            )
        )
        is SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED
    )


def test_forged_result_and_expired_reviewer_session_fail_closed(
    tmp_path: Path,
) -> None:
    runtime, authorization, store = _setup(tmp_path)
    runtime.submit_review(
        command_id=SourcePacketCommandIdV2("RECORDED:SUBMIT:AUTH-HOSTILE"),
        packet_id=PACKET_ID,
        expected_revision=2,
        editor_actor_fingerprint=EDITOR_FINGERPRINT,
        occurred_at=authorization.now - timedelta(seconds=1),
    )
    forged = replace(authorization.result)
    object.__setattr__(forged, "session_fingerprint", "f" * 64)
    assert (
        _failure(
            lambda: runtime.record_review(
                command_id=SourcePacketCommandIdV2("RECORDED:AUTH:FORGED-RESULT"),
                packet_id=PACKET_ID,
                expected_revision=3,
                decision=SourcePacketReviewDecisionV2.APPROVE,
                site_id=SITE_ID,
                review_assignment_id=REVIEW_ASSIGNMENT_ID,
                session_id=authorization.session.session_id,
                authorization_command=authorization.command,
                authorization_result=forged,
                authorization_checked_at=authorization.now,
            )
        )
        is SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED
    )
    assert (
        _failure(
            lambda: runtime.record_review(
                command_id=SourcePacketCommandIdV2("RECORDED:AUTH:EXPIRED"),
                packet_id=PACKET_ID,
                expected_revision=3,
                decision=SourcePacketReviewDecisionV2.APPROVE,
                site_id=SITE_ID,
                review_assignment_id=REVIEW_ASSIGNMENT_ID,
                session_id=authorization.session.session_id,
                authorization_command=authorization.command,
                authorization_result=authorization.result,
                authorization_checked_at=authorization.now + timedelta(hours=3),
            )
        )
        is SourcePacketFailureCodeV2.AUTHORIZATION_REQUIRED
    )
    state = store.load_state(PACKET_ID)
    assert state is not None and state.aggregate_revision == 3


def test_errors_and_representations_do_not_expose_source_or_secret_canaries(
    tmp_path: Path,
) -> None:
    content = source_content_v2(tmp_path / "redaction")
    assert "fact_batches" not in repr(content)
    assert "RECORDED" not in str(content)
    code = _failure(lambda: SourcePacketCommandIdV2("SECRET CANARY WITH SPACES"))
    assert code is SourcePacketFailureCodeV2.INVALID_ARGUMENT
    with pytest.raises(SourcePacketFailureV2) as caught:
        SourcePacketCommandIdV2("SECRET CANARY WITH SPACES")
    assert "SECRET" not in str(caught.value)
    assert "SECRET" not in repr(caught.value)
