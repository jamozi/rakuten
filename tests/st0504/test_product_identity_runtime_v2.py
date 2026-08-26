"""Domain, authorization, history and hostile-path checks for ST-0504 V2."""

from __future__ import annotations

from contextlib import contextmanager
import copy
from dataclasses import replace
from datetime import timedelta
import hashlib
from pathlib import Path
from typing import Generator, cast
from uuid import UUID

import pytest

from .runtime_v2_support import (
    DECISION_AT_V2,
    DECISION_OPERATION_IDS_V2,
    SITE_ID_V2,
    authorization_fixture_v2,
    persisted_catalog_v2,
    prepared_queue_v2,
    product_identity_store_v2,
    queue_command_v2,
    runtime_v2,
)
from raos.adapters.generated_st0403_authorization_registry import (
    CANONICAL_AUTHORIZATION_REGISTRY,
)
from raos.application.catalog.product_identity_runtime_v2 import (
    DurableProductIdentityRuntimeV2,
    ProductIdentityHumanDecisionRequestV2,
)
from raos.domain.catalog.product_identity_runtime_v2 import (
    PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2,
    PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2,
    PRODUCT_IDENTITY_OPEN_DECISION_V2,
    PRODUCT_IDENTITY_RUNTIME_VERSION_V2,
    PersistedProductIdentityDecisionV2,
    PersistedProductIdentityReviewQueueV2,
    PrepareProductIdentityReviewQueueCommandV2,
    ProductIdentityDecisionCommandV2,
    ProductIdentityDecisionCommitRecoveryV2,
    ProductIdentityDecisionTypeV2,
    ProductIdentityHumanDecisionV2,
    ProductIdentityOutboxEventV2,
    ProductIdentityQueueCommitRecoveryV2,
    ProductIdentityReadinessV2,
    ProductIdentityReplayStatusV2,
    ProductIdentityReviewStatusV2,
    ProductIdentityRuntimeFailureCodeV2,
    ProductIdentityRuntimeFailureV2,
    ProductIdentitySourceBindingV2,
    build_product_identity_review_queue_v2,
    fail_product_identity_runtime_v2,
    persisted_product_identity_decision_from_mapping_v2,
    persisted_product_identity_decision_mapping_v2,
    persisted_product_identity_review_queue_from_mapping_v2,
    persisted_product_identity_review_queue_mapping_v2,
)
from raos.domain.iam.authorization import (
    AuthorizationCommandResult,
    AuthorizationBindingStatus,
    OperationId,
)
from raos.domain.catalog.catalog_normalization_runtime_v2 import (
    PersistedCatalogNormalizationV2,
)
from raos.ports.product_identity_runtime_v2 import ProductIdentityUnitOfWorkStoreV2


def _request(
    *,
    queue: PersistedProductIdentityReviewQueueV2,
    authorization: object,
    operation_id: UUID,
    decision_type: ProductIdentityDecisionTypeV2,
    expected_version: int,
    supersedes: UUID | None,
    reason: str,
) -> ProductIdentityHumanDecisionRequestV2:
    from .runtime_v2_support import AuthorizationFixtureV2

    assert type(authorization) is AuthorizationFixtureV2
    return ProductIdentityHumanDecisionRequestV2(
        operation_id=operation_id,
        persisted_queue=queue,
        pair_id=queue.queue.pairs[0].pair_id,
        decision_type=decision_type,
        reason=reason,
        expected_history_version=expected_version,
        supersedes_decision_id=supersedes,
        decided_at=DECISION_AT_V2 + timedelta(seconds=expected_version),
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=DECISION_AT_V2,
    )


def _assert_failure(
    caught: pytest.ExceptionInfo[ProductIdentityRuntimeFailureV2],
    code: ProductIdentityRuntimeFailureCodeV2,
) -> None:
    assert caught.value.code is code
    assert str(caught.value) == code.value
    assert caught.value.args == (code.value,)
    assert "secret" not in repr(caught.value).lower()


def test_generic_queue_is_all_pairs_human_review_and_exact_st0503_provenance(
    tmp_path: Path,
) -> None:
    source = persisted_catalog_v2(tmp_path, item_ordinals=(1, 2, 3))
    command = queue_command_v2(source)

    first = build_product_identity_review_queue_v2(command)
    second = build_product_identity_review_queue_v2(command)

    assert first == second
    assert len(first.pairs) == 3
    assert first.runtime_version == PRODUCT_IDENTITY_RUNTIME_VERSION_V2
    assert first.identity_status is ProductIdentityReviewStatusV2.HUMAN_REVIEW
    assert first.readiness is ProductIdentityReadinessV2.NOT_READY
    assert first.open_decision == PRODUCT_IDENTITY_OPEN_DECISION_V2
    assert first.automatic_merge_enabled is False
    assert first.automatic_split_enabled is False
    assert first.canonical_products == ()
    assert first.recommendation_inputs == ()
    assert first.forbidden_inputs == PRODUCT_IDENTITY_FORBIDDEN_INPUTS_V2
    assert first.external_actions == 0
    assert first.source.catalog_batch_id == source.batch.batch_id
    assert first.source.catalog_batch_sha256 == source.batch.sha256
    assert first.source.catalog_chain_hash == source.chain_hash
    assert (
        first.source.catalog_source_snapshot_id
        == source.batch.source_snapshot.snapshot_id
    )
    assert first.source.catalog_raw_sha256 == source.batch.source_snapshot.raw_sha256
    assert first.source.catalog_receipt_id == source.batch.source_snapshot.receipt_id
    assert tuple(pair.ordinal for pair in first.pairs) == (1, 2, 3)
    assert all(
        pair.identity_status is ProductIdentityReviewStatusV2.HUMAN_REVIEW
        and pair.readiness is ProductIdentityReadinessV2.NOT_READY
        and pair.rule_ids == ()
        and pair.thresholds == ()
        and pair.scores == ()
        and pair.recommendation_input is False
        for pair in first.pairs
    )


def test_review_queue_is_durable_restartable_and_idempotent(tmp_path: Path) -> None:
    source = persisted_catalog_v2(tmp_path / "source")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    store = product_identity_store_v2(tmp_path / "store")
    runtime = runtime_v2(authorization=authorization, store=store)

    direct = runtime.prepare_review_queue(command)
    replay = runtime.prepare_review_queue(command)

    assert direct.replay_status is ProductIdentityReplayStatusV2.DIRECT_COMMIT
    assert replay.replay_status is ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == direct.persisted
    assert runtime.external_action_count == 0
    restarted = product_identity_store_v2(tmp_path / "store")
    assert (
        restarted.load_review_queue(direct.persisted.queue.queue_id) == direct.persisted
    )
    assert restarted.current_history_version(direct.persisted.queue.queue_id) == 1
    assert (
        restarted.load_outbox(direct.persisted.event.event_id) == direct.persisted.event
    )


def test_merge_then_split_supersedes_without_mutating_history(tmp_path: Path) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(tmp_path)
    merge_request = _request(
        queue=queue,
        authorization=authorization,
        operation_id=DECISION_OPERATION_IDS_V2[0],
        decision_type=ProductIdentityDecisionTypeV2.MERGE,
        expected_version=1,
        supersedes=None,
        reason="Human compared the exact recorded source and chose merge.",
    )
    merged = runtime.record_human_decision(merge_request)
    first_mapping = persisted_product_identity_decision_mapping_v2(merged.persisted)

    second_authorization = authorization_fixture_v2(tmp_path / "auth-2", label="2")
    second_runtime = runtime_v2(authorization=second_authorization, store=store)
    split_request = _request(
        queue=queue,
        authorization=second_authorization,
        operation_id=DECISION_OPERATION_IDS_V2[1],
        decision_type=ProductIdentityDecisionTypeV2.SPLIT,
        expected_version=2,
        supersedes=merged.persisted.decision.decision_id,
        reason="A later human review found the recorded candidates must stay separate.",
    )
    split = second_runtime.record_human_decision(split_request)
    replay = second_runtime.record_human_decision(split_request)

    history = store.list_decisions(queue.queue.queue_id)
    assert tuple(item.history_version for item in history) == (2, 3)
    assert history[0] == merged.persisted
    assert persisted_product_identity_decision_mapping_v2(history[0]) == first_mapping
    assert history[0].decision.supersedes_decision_id is None
    assert history[1] == split.persisted
    assert history[1].decision.supersedes_decision_id == history[0].decision.decision_id
    assert history[0].decision.decision_type is ProductIdentityDecisionTypeV2.MERGE
    assert history[1].decision.decision_type is ProductIdentityDecisionTypeV2.SPLIT
    assert history[0].decision.grouping_applied is False
    assert history[1].decision.grouping_applied is False
    assert history[0].decision.canonical_product_id is None
    assert history[1].decision.canonical_product_id is None
    assert replay.replay_status is ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY
    assert store.current_history_version(queue.queue.queue_id) == 3
    restarted = product_identity_store_v2(tmp_path / "identity")
    assert restarted.list_decisions(queue.queue.queue_id) == history
    assert restarted.current_history_version(queue.queue.queue_id) == 3


def test_authorization_is_recovered_and_bound_to_actor_site_resource_and_action(
    tmp_path: Path,
) -> None:
    runtime, _store, authorization, queue = prepared_queue_v2(tmp_path)
    result = runtime.record_human_decision(
        _request(
            queue=queue,
            authorization=authorization,
            operation_id=DECISION_OPERATION_IDS_V2[0],
            decision_type=ProductIdentityDecisionTypeV2.MERGE,
            expected_version=1,
            supersedes=None,
            reason="Recorded human comparison with exact authorization binding.",
        )
    )
    proof = result.persisted.decision.authorization
    assert proof.operation_id == "CAT-006"
    assert proof.action == PRODUCT_IDENTITY_AUTHORIZATION_ACTION_V2
    assert proof.site_id == queue.queue.site_id
    assert proof.resource_kind == "PRODUCT"
    assert proof.resource_state is None
    assert proof.step_up_receipt_fingerprint is None
    assert proof.actor_fingerprint == authorization.result.session_fingerprint
    assert proof.authorization_audit_digest == authorization.result.audit.digest
    assert result.persisted.decision.actor_fingerprint == proof.actor_fingerprint


@pytest.mark.parametrize(
    ("site_id", "action", "operation_id"),
    (
        (
            UUID("82345678-1234-4234-8234-123456789001"),
            "manage_product_identity",
            "CAT-006",
        ),
        (SITE_ID_V2, "edit_article_draft", "CAT-006"),
        (SITE_ID_V2, "manage_product_identity", "CAT-008"),
    ),
)
def test_wrong_authorization_binding_fails_before_identity_store_write(
    tmp_path: Path,
    site_id: UUID,
    action: str,
    operation_id: str,
) -> None:
    _runtime, store, _authorization, queue = prepared_queue_v2(tmp_path / "base")
    wrong = authorization_fixture_v2(
        tmp_path / "wrong",
        site_id=site_id,
        action=action,
        operation_id=operation_id,
    )
    runtime = runtime_v2(authorization=wrong, store=store)
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.record_human_decision(
            _request(
                queue=queue,
                authorization=wrong,
                operation_id=DECISION_OPERATION_IDS_V2[0],
                decision_type=ProductIdentityDecisionTypeV2.MERGE,
                expected_version=1,
                supersedes=None,
                reason="secret rejected authorization canary",
            )
        )
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
    assert store.list_decisions(queue.queue.queue_id) == ()


def test_current_canonical_cat006_binding_remains_blocked_by_open_mapping() -> None:
    resolution = CANONICAL_AUTHORIZATION_REGISTRY.resolve(OperationId("CAT-006"))
    assert resolution.status is AuthorizationBindingStatus.BLOCKED
    assert resolution.binding is None
    assert resolution.required_evidence


def test_inactive_session_recovery_stops_before_decision_write(tmp_path: Path) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(tmp_path)
    request = _request(
        queue=queue,
        authorization=authorization,
        operation_id=DECISION_OPERATION_IDS_V2[0],
        decision_type=ProductIdentityDecisionTypeV2.MERGE,
        expected_version=1,
        supersedes=None,
        reason="This decision must not survive an expired active session check.",
    )
    expired = replace(
        request,
        authorization_checked_at=DECISION_AT_V2 + timedelta(hours=3),
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.record_human_decision(expired)
    _assert_failure(
        caught,
        ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_NOT_DURABLE,
    )
    assert store.list_decisions(queue.queue.queue_id) == ()


def test_stale_cas_and_wrong_supersedes_are_rejected(tmp_path: Path) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(tmp_path)
    first = runtime.record_human_decision(
        _request(
            queue=queue,
            authorization=authorization,
            operation_id=DECISION_OPERATION_IDS_V2[0],
            decision_type=ProductIdentityDecisionTypeV2.MERGE,
            expected_version=1,
            supersedes=None,
            reason="First recorded human decision.",
        )
    )
    second_authorization = authorization_fixture_v2(tmp_path / "auth-2", label="2")
    second_runtime = runtime_v2(authorization=second_authorization, store=store)
    stale = _request(
        queue=queue,
        authorization=second_authorization,
        operation_id=DECISION_OPERATION_IDS_V2[1],
        decision_type=ProductIdentityDecisionTypeV2.SPLIT,
        expected_version=1,
        supersedes=None,
        reason="Stale decision must be rejected.",
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        second_runtime.record_human_decision(stale)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT)

    wrong_head = _request(
        queue=queue,
        authorization=second_authorization,
        operation_id=DECISION_OPERATION_IDS_V2[2],
        decision_type=ProductIdentityDecisionTypeV2.SPLIT,
        expected_version=2,
        supersedes=UUID("82345678-1234-4234-8234-123456789099"),
        reason="Wrong supersession head must be rejected.",
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as wrong_caught:
        second_runtime.record_human_decision(wrong_head)
    _assert_failure(wrong_caught, ProductIdentityRuntimeFailureCodeV2.STATE_CONFLICT)
    assert store.list_decisions(queue.queue.queue_id) == (first.persisted,)


def test_conflicting_decision_idempotency_key_is_rejected(tmp_path: Path) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(tmp_path)
    operation_id = DECISION_OPERATION_IDS_V2[0]
    runtime.record_human_decision(
        _request(
            queue=queue,
            authorization=authorization,
            operation_id=operation_id,
            decision_type=ProductIdentityDecisionTypeV2.MERGE,
            expected_version=1,
            supersedes=None,
            reason="Original human decision for this operation key.",
        )
    )
    conflict = _request(
        queue=queue,
        authorization=authorization,
        operation_id=operation_id,
        decision_type=ProductIdentityDecisionTypeV2.SPLIT,
        expected_version=1,
        supersedes=None,
        reason="Conflicting human decision for the same operation key.",
    )

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.record_human_decision(conflict)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.IDEMPOTENCY_CONFLICT)
    assert len(store.list_decisions(queue.queue.queue_id)) == 1


def test_mapping_round_trips_are_exact_and_unknown_fields_fail(tmp_path: Path) -> None:
    runtime, _store, authorization, queue = prepared_queue_v2(tmp_path)
    queue_mapping = persisted_product_identity_review_queue_mapping_v2(queue)
    assert (
        persisted_product_identity_review_queue_from_mapping_v2(queue_mapping) == queue
    )
    decision = runtime.record_human_decision(
        _request(
            queue=queue,
            authorization=authorization,
            operation_id=DECISION_OPERATION_IDS_V2[0],
            decision_type=ProductIdentityDecisionTypeV2.MERGE,
            expected_version=1,
            supersedes=None,
            reason="Mapping round trip human reason.",
        )
    ).persisted
    mapping = persisted_product_identity_decision_mapping_v2(decision)
    assert persisted_product_identity_decision_from_mapping_v2(mapping) == decision
    mapping["ranking_score"] = 99
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        persisted_product_identity_decision_from_mapping_v2(mapping)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED)


def test_mapping_rejects_noncanonical_uuid_and_rfc3339_text(tmp_path: Path) -> None:
    _runtime, _store, _authorization, queue = prepared_queue_v2(tmp_path)
    mapping = persisted_product_identity_review_queue_mapping_v2(queue)

    noncanonical_uuid = copy.deepcopy(mapping)
    noncanonical_uuid["operation_id"] = "{" + str(queue.operation_id) + "}"
    with pytest.raises(ProductIdentityRuntimeFailureV2) as uuid_caught:
        persisted_product_identity_review_queue_from_mapping_v2(noncanonical_uuid)
    _assert_failure(
        uuid_caught,
        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
    )

    noncanonical_time = copy.deepcopy(mapping)
    noncanonical_time["committed_at"] = queue.committed_at.isoformat(
        timespec="microseconds"
    ).replace("+00:00", "Z")
    with pytest.raises(ProductIdentityRuntimeFailureV2) as time_caught:
        persisted_product_identity_review_queue_from_mapping_v2(noncanonical_time)
    _assert_failure(
        time_caught,
        ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
    )


def test_arbitrary_authorization_audit_digest_is_recomputed_and_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(tmp_path)
    forged_audit = replace(authorization.result.audit, digest="f" * 64)
    forged_result = replace(authorization.result, audit=forged_audit)
    assert type(forged_result) is AuthorizationCommandResult
    request = replace(
        _request(
            queue=queue,
            authorization=authorization,
            operation_id=DECISION_OPERATION_IDS_V2[0],
            decision_type=ProductIdentityDecisionTypeV2.MERGE,
            expected_version=1,
            supersedes=None,
            reason="Forged audit digest must not authorize a decision.",
        ),
        authorization_result=forged_result,
    )

    def recover_forged(_self: object, **_kwargs: object) -> AuthorizationCommandResult:
        return forged_result

    monkeypatch.setattr(
        type(authorization.service),
        "recover_admin",
        recover_forged,
    )

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.record_human_decision(request)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.AUTHORIZATION_MISMATCH)
    assert store.list_decisions(queue.queue.queue_id) == ()


def test_forged_exact_st0503_source_is_sanitized() -> None:
    forged = object.__new__(PersistedCatalogNormalizationV2)
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        ProductIdentitySourceBindingV2.from_persisted(forged)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY)


class _ForgedStore:
    @property
    def action_count(self) -> int:
        return 0

    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        del command
        return object.__new__(PersistedProductIdentityReviewQueueV2)

    def commit_review_queue(
        self, **kwargs: object
    ) -> PersistedProductIdentityReviewQueueV2:
        del kwargs
        return object.__new__(PersistedProductIdentityReviewQueueV2)

    def recover_review_queue_commit(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> ProductIdentityQueueCommitRecoveryV2:
        del command
        return object.__new__(ProductIdentityQueueCommitRecoveryV2)

    def lookup_decision(
        self, command: ProductIdentityDecisionCommandV2
    ) -> PersistedProductIdentityDecisionV2 | None:
        del command
        return object.__new__(PersistedProductIdentityDecisionV2)

    def commit_decision(self, **kwargs: object) -> PersistedProductIdentityDecisionV2:
        del kwargs
        return object.__new__(PersistedProductIdentityDecisionV2)

    def recover_decision_commit(
        self, command: ProductIdentityDecisionCommandV2
    ) -> ProductIdentityDecisionCommitRecoveryV2:
        del command
        return object.__new__(ProductIdentityDecisionCommitRecoveryV2)

    def load_review_queue(
        self, queue_id: object
    ) -> PersistedProductIdentityReviewQueueV2:
        del queue_id
        return object.__new__(PersistedProductIdentityReviewQueueV2)

    def list_decisions(
        self, queue_id: object
    ) -> tuple[PersistedProductIdentityDecisionV2, ...]:
        del queue_id
        return ()

    def load_outbox(self, event_id: object) -> ProductIdentityOutboxEventV2:
        del event_id
        return object.__new__(ProductIdentityOutboxEventV2)


class _ExplodingStore(_ForgedStore):
    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        del command
        raise RuntimeError("secret collaborator canary") from None


class _ForgedRecoveryStore(_ForgedStore):
    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        del command
        return None

    def commit_review_queue(
        self, **kwargs: object
    ) -> PersistedProductIdentityReviewQueueV2:
        del kwargs
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN
        )

    def recover_review_queue_commit(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> ProductIdentityQueueCommitRecoveryV2:
        del command
        return object.__new__(ProductIdentityQueueCommitRecoveryV2)


class _MutatingStore(_ForgedStore):
    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        object.__setattr__(command, "payload_fingerprint", "0" * 64)
        return None


class _ActionCountMutationStore(_ForgedStore):
    def __init__(self) -> None:
        self.count = 0

    @property
    def action_count(self) -> int:
        return self.count

    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        del command
        self.count = 1
        return None


class _ActionCountInputMutationStore(_ForgedStore):
    def __init__(self, command: PrepareProductIdentityReviewQueueCommandV2) -> None:
        self.command = command
        self.action_count_reads = 0
        self.lookup_calls = 0

    @property
    def action_count(self) -> int:
        self.action_count_reads += 1
        if self.action_count_reads == 2:
            object.__setattr__(self.command, "payload_fingerprint", "0" * 64)
        return 0

    def lookup_review_queue(
        self, command: PrepareProductIdentityReviewQueueCommandV2
    ) -> PersistedProductIdentityReviewQueueV2 | None:
        del command
        self.lookup_calls += 1
        return None


@pytest.mark.parametrize(
    ("store", "code"),
    (
        (
            cast(ProductIdentityUnitOfWorkStoreV2, _ForgedStore()),
            ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED,
        ),
        (
            cast(ProductIdentityUnitOfWorkStoreV2, _ExplodingStore()),
            ProductIdentityRuntimeFailureCodeV2.STORE_UNAVAILABLE,
        ),
        (
            cast(ProductIdentityUnitOfWorkStoreV2, _ForgedRecoveryStore()),
            ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN,
        ),
    ),
)
def test_forged_and_exploding_collaborators_are_sanitized(
    tmp_path: Path,
    store: ProductIdentityUnitOfWorkStoreV2,
    code: ProductIdentityRuntimeFailureCodeV2,
) -> None:
    source = persisted_catalog_v2(tmp_path / "source")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    runtime = DurableProductIdentityRuntimeV2(
        authorization_service=authorization.service,
        store=store,
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.prepare_review_queue(command)
    _assert_failure(caught, code)


@pytest.mark.parametrize(
    "store",
    (
        cast(ProductIdentityUnitOfWorkStoreV2, _MutatingStore()),
        cast(ProductIdentityUnitOfWorkStoreV2, _ActionCountMutationStore()),
    ),
)
def test_collaborator_input_mutation_and_action_spoof_fail_closed(
    tmp_path: Path,
    store: ProductIdentityUnitOfWorkStoreV2,
) -> None:
    source = persisted_catalog_v2(tmp_path / "source")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    runtime = DurableProductIdentityRuntimeV2(
        authorization_service=authorization.service,
        store=store,
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.prepare_review_queue(command)
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED)


def test_action_count_input_mutation_is_rejected_before_store_call(
    tmp_path: Path,
) -> None:
    source = persisted_catalog_v2(tmp_path / "source")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    store = _ActionCountInputMutationStore(command)
    runtime = DurableProductIdentityRuntimeV2(
        authorization_service=authorization.service,
        store=cast(ProductIdentityUnitOfWorkStoreV2, store),
    )

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.prepare_review_queue(command)

    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED)
    assert store.lookup_calls == 0


def test_closed_exception_supports_traceback_and_context_manager_unwinding() -> None:
    @contextmanager
    def boundary() -> Generator[None, None, None]:
        yield

    failure = ProductIdentityRuntimeFailureV2(
        ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY
    )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        with boundary():
            raise failure
    assert caught.value is failure
    assert caught.value.__traceback__ is not None
    caught.value.__traceback__ = caught.value.__traceback__
    _assert_failure(caught, ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY)
    with pytest.raises(TypeError):
        ProductIdentityRuntimeFailureV2(
            cast(ProductIdentityRuntimeFailureCodeV2, "secret")
        )
    with pytest.raises(ProductIdentityRuntimeFailureV2) as fresh:
        fail_product_identity_runtime_v2(
            ProductIdentityRuntimeFailureCodeV2.SOURCE_INTEGRITY
        )
    assert fresh.value.__context__ is None


def test_finance_reward_review_and_ranking_inputs_are_absent_from_surface() -> None:
    joined = "\n".join(
        (
            PersistedProductIdentityReviewQueueV2.__doc__ or "",
            ProductIdentityHumanDecisionV2.__doc__ or "",
            " ".join(ProductIdentityHumanDecisionV2.__dataclass_fields__),
            " ".join(ProductIdentityHumanDecisionRequestV2.__dataclass_fields__),
        )
    ).lower()
    for forbidden in (
        "affiliate_rate",
        "commission",
        "epc",
        "profit",
        "ranking_score",
        "review_body",
        "reward",
        "rpm",
    ):
        assert forbidden not in joined
    assert hashlib.sha256(joined.encode()).hexdigest()
