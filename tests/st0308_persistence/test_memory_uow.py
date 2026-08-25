"""End-to-end transaction, CAS, idempotency, join, and event tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from raos.adapters.persistence.memory import WorkloadProfile
from raos.adapters.persistence.memory.identity import MemoryCommitMode
from raos.domain.iam.ids import PrincipalId
from raos.domain.ops.aggregates import RuntimeSettingVersion
from raos.domain.ops.enums import RuntimeSettingVersionStatus
from raos.domain.shared.idempotency import (
    ActorFingerprint,
    ClaimGranted,
    ClaimNotFound,
    IdempotencyClaim,
    IdempotencyIdentity,
    IdempotencyKey,
    IdempotencyOutcome,
    PayloadMismatch,
    ReplaySucceeded,
    RequestHash,
    RouteKey,
)
from raos.domain.shared.json_values import FrozenJsonArray, FrozenJsonObject
from raos.domain.shared.persistence import AwareUtcDateTime, PendingEventBuffer
from raos.ports.persistence.audit import SanitizedAuditDetails
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.st0308_persistence.support import (
    FIXED_TIME,
    make_audit,
    make_artifact,
    make_context,
    make_event,
    make_factory,
    make_runtime_setting,
    stable_uuid,
)


def _identity() -> IdempotencyIdentity:
    return IdempotencyIdentity(
        ActorFingerprint("a" * 64),
        RouteKey("POST:/ops/reference"),
        IdempotencyKey("fixture-key"),
    )


def _claim(
    *, digest: str = "b" * 64, expires_in: timedelta = timedelta(minutes=5)
) -> IdempotencyClaim:
    return IdempotencyClaim(
        _identity(),
        RequestHash(digest),
        FIXED_TIME + expires_in,
    )


def test_begin_is_inactive_and_identity_precedes_session_and_begin() -> None:
    factory, _store, pool = make_factory()
    outer = factory.begin(make_context())
    assert pool.trace == []
    with outer:
        assert pool.trace[:4] == [
            "connection.checkout",
            "identity.verify",
            "session.construct",
            "session.begin",
        ]
    assert "session.rollback" in pool.trace

    rejected, _store, rejected_pool = make_factory(dangerous=True)
    with pytest.raises(PersistenceError) as caught:
        with rejected.begin(make_context()):
            raise AssertionError("identity rejection must precede exposure")
    assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
    assert rejected_pool.trace == [
        "connection.checkout",
        "identity.verify",
        "connection.invalidate",
        "connection.close",
    ]


def test_atomic_business_audit_outbox_idempotency_and_pending_event_commit() -> None:
    factory, store, _pool = make_factory()
    artifact = make_artifact()
    setting = make_runtime_setting()
    event = make_event()
    buffer = PendingEventBuffer((event,))
    with factory.begin_idempotent(make_context()) as outer:
        outer.object_artifacts.add(artifact)
        assert outer.runtime_settings.append_version(setting, None).value == 1
        outer.audit.append_many((make_audit(),))
        decision = outer.idempotency.claim(_claim())
        assert isinstance(decision, ClaimGranted)
        outer.idempotency.complete_success(
            decision.handle,
            IdempotencyOutcome(
                201,
                response_body=FrozenJsonObject.from_mapping({"ok": True}),
            ),
        )
        outer._stage_pending_events(buffer)
        assert buffer.pending_events() == ()
        outer.commit()

    snapshot = store.snapshot()
    assert snapshot.revision == 1
    assert snapshot.object_artifacts == (artifact,)
    assert snapshot.runtime_settings == (setting,)
    assert len(snapshot.audit_events) == 1
    assert len(snapshot.outbox_events) == 1
    assert len(snapshot.idempotency_records) == 1
    assert buffer.pending_events() == ()


def test_known_rollback_restores_pending_events_and_exposes_no_partial_effects() -> (
    None
):
    factory, store, _pool = make_factory()
    event = make_event(suffix="rollback")
    buffer = PendingEventBuffer((event,))
    with factory.begin_idempotent(make_context(suffix="rollback")) as outer:
        outer.object_artifacts.add(make_artifact(suffix="002"))
        outer.audit.append_many((make_audit(),))
        outer.idempotency.claim(_claim())
        outer._stage_pending_events(buffer)
        assert buffer.pending_events() == ()
    snapshot = store.snapshot()
    assert snapshot.revision == 0
    assert snapshot.object_artifacts == ()
    assert snapshot.audit_events == ()
    assert snapshot.outbox_events == ()
    assert snapshot.idempotency_records == ()
    assert buffer.pending_events() == (event,)


def test_duplicate_stale_append_state_cas_and_optimistic_commit_conflict() -> None:
    factory, store, _pool = make_factory()
    artifact = make_artifact()
    draft = make_runtime_setting()
    with factory.begin(make_context()) as outer:
        outer.object_artifacts.add(artifact)
        outer.runtime_settings.append_version(draft, None)
        outer.commit()

    with factory.begin(make_context(suffix="negative")) as outer:
        with pytest.raises(PersistenceError) as duplicate:
            outer.object_artifacts.add(artifact)
        assert duplicate.value.code is PersistenceErrorCode.ALREADY_EXISTS
        version_two = make_runtime_setting(version_no=2)
        with pytest.raises(PersistenceError) as stale:
            outer.runtime_settings.append_version(version_two, 0)
        assert stale.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT

    actor = PrincipalId(stable_uuid("principal:actor"))
    active = RuntimeSettingVersion(
        replace(
            draft.state,
            status=RuntimeSettingVersionStatus.ACTIVE,
            approved_by_principal_id=actor,
            approval_reason="approved",
            effective_from=AwareUtcDateTime(FIXED_TIME),
        )
    )
    with factory.begin(make_context(suffix="activate")) as outer:
        assert (
            outer.runtime_settings.transition(
                draft.state.id,
                active,
                RuntimeSettingVersionStatus.DRAFT,
            )
            == active
        )
        outer.commit()
    with factory.begin(make_context(suffix="stale-state")) as outer:
        with pytest.raises(PersistenceError) as stale_state:
            outer.runtime_settings.transition(
                draft.state.id,
                active,
                RuntimeSettingVersionStatus.DRAFT,
            )
        assert stale_state.value.code is PersistenceErrorCode.STATE_CONFLICT

    first = factory.begin(make_context(suffix="first"))
    second = factory.begin(make_context(suffix="second"))
    first.__enter__()
    second.__enter__()
    try:
        first.object_artifacts.add(make_artifact(suffix="101"))
        second.object_artifacts.add(make_artifact(suffix="102"))
        first.commit()
        with pytest.raises(PersistenceError) as conflict:
            second.commit()
        assert conflict.value.code is PersistenceErrorCode.CONCURRENCY_CONFLICT
    finally:
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)
    assert {item.display_id for item in store.snapshot().object_artifacts} == {
        "ART-001",
        "ART-101",
    }


def test_join_reuses_exact_surfaces_and_cannot_own_transaction() -> None:
    factory, store, pool = make_factory()
    context = make_context(suffix="join")
    with factory.begin(context) as outer:
        join_capability = outer.join_token()
        joined_scope = factory.join(join_capability, context)
        with joined_scope as joined:
            assert joined.object_artifacts is outer.object_artifacts
            assert joined.runtime_settings is outer.runtime_settings
            assert joined.audit is outer.audit
            assert joined.outbox is outer.outbox
            assert not hasattr(joined, "commit")
            assert not hasattr(joined, "rollback")
            assert not hasattr(joined, "idempotency")
            joined.object_artifacts.add(make_artifact(suffix="201"))
            with pytest.raises(PersistenceError) as ownership:
                outer.commit()
            assert ownership.value.code is PersistenceErrorCode.TRANSACTION_OWNERSHIP
        outer.commit()
    assert len(store.snapshot().object_artifacts) == 1
    assert pool.trace.count("connection.checkout") == 1
    assert pool.trace.count("session.begin") == 1

    with pytest.raises(PersistenceError) as mismatch:
        factory.join(join_capability, make_context(suffix="other"))
    assert mismatch.value.code is PersistenceErrorCode.TRANSACTION_OWNERSHIP


def test_idempotency_replay_mismatch_lookup_expiry_and_foreign_handle() -> None:
    factory, store, _pool = make_factory()
    with factory.begin_idempotent(make_context()) as outer:
        granted = outer.idempotency.claim(_claim())
        assert isinstance(granted, ClaimGranted)
        outer.idempotency.complete_success(
            granted.handle,
            IdempotencyOutcome(200, FrozenJsonObject.from_mapping({"ok": True})),
        )
        outer.commit()

    with factory.begin_idempotent(make_context(suffix="replay")) as outer:
        assert isinstance(outer.idempotency.claim(_claim()), ReplaySucceeded)
        assert isinstance(
            outer.idempotency.lookup(_identity(), RequestHash("c" * 64)),
            PayloadMismatch,
        )
        with pytest.raises(PersistenceError) as foreign:
            outer.idempotency.complete_success(
                granted.handle,
                IdempotencyOutcome(200),
            )
        assert foreign.value.code is PersistenceErrorCode.LOST_IDEMPOTENCY_CLAIM

    expired_factory, _store, _pool = make_factory(
        store=store,
        now=FIXED_TIME + timedelta(minutes=5),
        id_prefix="expired",
    )
    old_record_id = store.snapshot().idempotency_records[0].id
    with expired_factory.begin_idempotent(make_context(suffix="expired")) as outer:
        assert isinstance(
            outer.idempotency.lookup(_identity(), RequestHash("b" * 64)),
            ClaimNotFound,
        )
        replacement = outer.idempotency.claim(
            _claim(digest="d" * 64, expires_in=timedelta(minutes=10))
        )
        assert isinstance(replacement, ClaimGranted)
        outer.commit()
    record = store.snapshot().idempotency_records[0]
    assert record.id == old_record_id
    assert record.request_hash.value == "d" * 64


def test_json_and_audit_boundaries_are_deeply_immutable_and_sensitive_safe() -> None:
    nested = FrozenJsonObject.from_mapping({"safe": [{"token": "redacted"}]})
    with pytest.raises(ValueError, match="INVALID_SANITIZED_AUDIT_DETAILS"):
        SanitizedAuditDetails(nested)
    value = FrozenJsonObject.from_mapping({"array": [1, 2]})
    with pytest.raises(AttributeError, match="immutable"):
        value._values = {}  # type: ignore[misc]
    array = FrozenJsonArray((1, 2))
    with pytest.raises(AttributeError, match="immutable"):
        array._values = ()  # type: ignore[misc]


@pytest.mark.parametrize(
    "payload",
    (
        {"api_key": "redacted"},
        {"nested": {"accessToken": "redacted"}},
        {"authorization_header": "redacted"},
        {"session_cookie": "redacted"},
        {"contact": "operator@example.test"},
        {"client": "192.0.2.10"},
        {"location": "https://user:pass@example.test/path"},
        {"opaque": "a" * 32},
        {"opaque": "header.payload.signature"},
    ),
)
def test_sanitized_audit_details_reject_nested_secrets_and_personal_data(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_SANITIZED_AUDIT_DETAILS"):
        SanitizedAuditDetails(FrozenJsonObject.from_mapping(payload))


def test_sanitized_audit_details_accepts_only_bounded_safe_metadata() -> None:
    details = SanitizedAuditDetails(
        FrozenJsonObject.from_mapping(
            {"kind": "transition", "attempt": 2, "automatic": False}
        )
    )
    assert tuple(details.value) == ("attempt", "automatic", "kind")


@pytest.mark.parametrize(
    "payload",
    (
        {"auth": "short-secret"},
        {"value": "abc123"},
        {"kind": "abc123"},
        {"kind": "transition", "attempt": True},
        {"kind": "transition", "attempt": 1001},
        {"kind": "transition", "automatic": 1},
    ),
)
def test_sanitized_audit_details_rejects_untyped_short_credentials(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="INVALID_SANITIZED_AUDIT_DETAILS"):
        SanitizedAuditDetails(FrozenJsonObject.from_mapping(payload))


def test_worker_composition_denies_idempotency_factory() -> None:
    factory, _store, _pool = make_factory(profile=WorkloadProfile.WORKER_COMMAND)
    with pytest.raises(PersistenceError) as denied:
        factory.begin_idempotent(make_context())
    assert denied.value.code is PersistenceErrorCode.IDENTITY_REJECTED


def test_unknown_commit_discards_uow_without_restoring_acknowledged_events() -> None:
    factory, store, pool = make_factory(commit_mode=MemoryCommitMode.UNKNOWN)
    event = make_event(suffix="unknown")
    buffer = PendingEventBuffer((event,))
    with factory.begin(make_context(suffix="unknown")) as outer:
        outer.object_artifacts.add(make_artifact(suffix="301"))
        outer._stage_pending_events(buffer)
        with pytest.raises(PersistenceError) as unknown:
            outer.commit()
        assert unknown.value.code is PersistenceErrorCode.UNKNOWN_COMMIT
    assert store.snapshot().revision == 0
    assert store.snapshot().object_artifacts == ()
    assert buffer.pending_events() == ()
    assert "session.commit" in pool.trace
    assert "session.rollback" not in pool.trace
