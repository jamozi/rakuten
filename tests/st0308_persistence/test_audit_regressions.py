"""Focused regressions for the independent ST-0308 security/runtime audit."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import timedelta
import json
from types import MappingProxyType
from typing import cast

import pytest

from raos.adapters.persistence.memory import (
    MemoryConnectionPool,
    MemoryEffectiveRoleVerifier,
    MemoryPersistenceStore,
    VerifiedDatabaseIdentity,
    WorkloadProfile,
)
from raos.adapters.persistence.memory.identity import (
    EffectiveRoleVerifier,
    MemoryCommitMode,
    MemoryConnection,
)
from raos.adapters.persistence.memory.shared import MemoryIdempotencyRepository
from raos.adapters.persistence.memory.unit_of_work import (
    MemoryJoinedOpsUnitOfWork,
    MemoryOpsUnitOfWork,
)
from raos.adapters.persistence.sqlalchemy.mappers import ops as mappers
from raos.domain.ops.aggregates import OutboxEventRecord
from raos.domain.ops.events import (
    EVENT_RUNTIME_BINDINGS_BY_CLASS,
    EVENT_RUNTIME_BINDINGS_BY_TYPE,
    OpsJobRequested,
)
from raos.domain.ops.values import OutboxEventRecordPayloadJson
from raos.domain.shared.events import DomainEvent, EVENT_BY_TYPE
from raos.domain.shared.identity import Actor, ActorType
from raos.domain.shared.idempotency import (
    ClaimGranted,
    ClaimInProgress,
    IdempotencyOutcome,
    PayloadMismatch,
)
from raos.domain.shared.json_values import FrozenJsonObject
from raos.domain.shared.persistence import Sha256Digest
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from raos.ports.persistence.outbox import ValidatedOutboxEvent
from scripts import build_st0308_persistence as generator
from tests.st0308_persistence.support import (
    make_artifact,
    make_context,
    make_event,
    make_factory,
    stable_uuid,
)
from tests.st0308_persistence.test_memory_uow import _claim


class _NullProofVerifier:
    def verify(
        self,
        connection: MemoryConnection,
        expected_profile: WorkloadProfile,
    ) -> VerifiedDatabaseIdentity:
        del connection, expected_profile
        return cast(VerifiedDatabaseIdentity, None)


class _ForeignConnectionProofVerifier:
    def __init__(self, foreign_pool: MemoryConnectionPool) -> None:
        self._foreign_pool = foreign_pool

    def verify(
        self,
        connection: MemoryConnection,
        expected_profile: WorkloadProfile,
    ) -> VerifiedDatabaseIdentity:
        del connection
        return MemoryEffectiveRoleVerifier().verify(
            self._foreign_pool.checkout(), expected_profile
        )


def test_identity_requires_exact_bound_positive_proof_and_exact_group_set() -> None:
    for verifier in (
        cast(EffectiveRoleVerifier, _NullProofVerifier()),
        cast(
            EffectiveRoleVerifier,
            _ForeignConnectionProofVerifier(make_factory()[2]),
        ),
    ):
        factory, _store, pool = make_factory(verifier=verifier)
        with pytest.raises(PersistenceError) as caught:
            factory.begin(make_context()).__enter__()
        assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
        assert "session.construct" not in pool.trace
        assert pool.trace[-2:] == ["connection.invalidate", "connection.close"]

    extra_group, _store, pool = make_factory(
        groups=frozenset({"raos_api_rw", "unregistered_group"})
    )
    with pytest.raises(PersistenceError) as caught:
        extra_group.begin(make_context()).__enter__()
    assert caught.value.code is PersistenceErrorCode.IDENTITY_REJECTED
    assert "session.construct" not in pool.trace


def test_event_registry_uses_exact_class_identity_and_validates_payload_values() -> (
    None
):
    assert isinstance(EVENT_BY_TYPE, MappingProxyType)
    assert isinstance(EVENT_RUNTIME_BINDINGS_BY_CLASS, MappingProxyType)
    assert isinstance(EVENT_RUNTIME_BINDINGS_BY_TYPE, MappingProxyType)
    binding = EVENT_RUNTIME_BINDINGS_BY_CLASS[OpsJobRequested]
    assert EVENT_RUNTIME_BINDINGS_BY_TYPE[binding.descriptor.event_type] is binding
    assert binding.event_class is OpsJobRequested
    assert binding.descriptor is EVENT_BY_TYPE[OpsJobRequested.DESCRIPTOR_TYPE]
    assert binding.payload_schema_sha256 == binding.descriptor.schema_sha256
    with pytest.raises(TypeError):
        EVENT_BY_TYPE["spoofed"] = EVENT_BY_TYPE[OpsJobRequested.DESCRIPTOR_TYPE]  # type: ignore[index]
    with pytest.raises(TypeError):
        EVENT_RUNTIME_BINDINGS_BY_CLASS[DomainEvent] = binding  # type: ignore[index]
    with pytest.raises(TypeError):
        EVENT_RUNTIME_BINDINGS_BY_TYPE["spoofed"] = binding  # type: ignore[index]

    forged_type = type(
        "OpsJobRequested",
        (DomainEvent,),
        {
            "__module__": "raos.domain.ops.events",
            "__qualname__": "OpsJobRequested",
            "DESCRIPTOR_TYPE": OpsJobRequested.DESCRIPTOR_TYPE,
        },
    )
    genuine = make_event(suffix="exact-class")
    with pytest.raises(ValueError, match="INVALID_DOMAIN_EVENT"):
        forged_type(
            event_id=genuine.event_id,
            aggregate_id=genuine.aggregate_id,
            aggregate_version=genuine.aggregate_version,
            occurred_at=genuine.occurred_at,
            causation_id=genuine.causation_id,
            data=genuine.data,
        )

    invalid_payloads = (
        {},
        {
            "available_at": genuine.data["available_at"],
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
        },
        {
            "available_at": genuine.data["available_at"],
            "extra": "not-schema-owned",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": genuine.data["available_at"],
            "job_id": True,
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": genuine.data["available_at"],
            "job_id": genuine.data["job_id"],
            "job_type": 1,
            "queue": "local",
        },
        {
            "available_at": genuine.data["available_at"],
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": False,
        },
        {
            "available_at": genuine.occurred_at.replace(tzinfo=None).isoformat(),
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "not-a-date-time",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "20260824T030000+00:00",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "2026-W35-1T03:00:00+00:00",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "2026-08-24T03:00:00+00:00:01",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "2026-08-24T03:00:60Z",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "2026-01-01T12:34:60+09:00",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": "2016-12-31T23:59:60Z",
            "job_id": genuine.data["job_id"],
            "job_type": "TEST",
            "queue": "local",
        },
        {
            "available_at": genuine.data["available_at"],
            "job_id": str(stable_uuid("job:other")),
            "job_type": "TEST",
            "queue": "local",
        },
    )
    for payload in invalid_payloads:
        with pytest.raises(ValueError, match="INVALID_DOMAIN_EVENT"):
            replace(genuine, data=FrozenJsonObject.from_mapping(payload))


def _map_outbox_payload(
    row: mappers.OutboxEventScalars,
    payload: OutboxEventRecordPayloadJson,
) -> OutboxEventRecord:
    return mappers.map_ops_outbox_event_from_row(
        id=row[0],
        event_type=row[1],
        event_version=row[2],
        producer=row[3],
        aggregate_type=row[4],
        aggregate_id=row[5],
        aggregate_version=row[6],
        correlation_id=row[7],
        causation_id=row[8],
        actor_type=row[9],
        actor_id=row[10],
        payload=payload,
        payload_schema_hash=row[12],
        status=row[13],
        available_at=row[14],
        published_at=row[15],
        publish_attempts=row[16],
        last_error=row[17],
        created_at=row[18],
    )


def _stored_outbox_row(*, suffix: str) -> mappers.OutboxEventScalars:
    factory, store, _pool = make_factory(id_prefix=suffix)
    with factory.begin(make_context(suffix=suffix)) as outer:
        outer.outbox.append_many((ValidatedOutboxEvent(make_event()),))
        outer.commit()
    return mappers.map_ops_outbox_event_to_row(store.snapshot().outbox_events[0])


@pytest.mark.parametrize(
    "available_at",
    (
        "2026-08-24T03:00:00Z",
        "2026-08-24t12:34:56.123456+09:30",
        "2026-08-24T03:00:59Z",
        "2026-01-01T12:34:59+09:00",
    ),
)
def test_rfc3339_payload_roundtrips_without_normalization(available_at: str) -> None:
    genuine = make_event()
    raw_payload = dict(genuine.data.items())
    raw_payload["available_at"] = available_at
    domain_event = replace(
        genuine,
        data=FrozenJsonObject.from_mapping(raw_payload),
    )
    assert domain_event.data["available_at"] == available_at

    row = _stored_outbox_row(suffix=f"valid-rfc3339-{available_at}")
    payload = OutboxEventRecordPayloadJson(FrozenJsonObject.from_mapping(raw_payload))
    restored = _map_outbox_payload(row, payload)
    assert restored.payload.value["available_at"] == available_at
    assert mappers.map_ops_outbox_event_to_row(restored)[11] == payload


def test_stored_outbox_payload_requires_exact_validator_and_roundtrips() -> None:
    row = _stored_outbox_row(suffix="stored-payload")

    restored = _map_outbox_payload(row, row[11])
    assert mappers.map_ops_outbox_event_to_row(restored) == row

    valid = dict(row[11].value.items())
    invalid_payloads = (
        {},
        {key: value for key, value in valid.items() if key != "queue"},
        {**valid, "extra": "not-schema-owned"},
        {**valid, "job_type": 1},
        {**valid, "queue": False},
        {**valid, "available_at": "2026-08-24T03:00:00"},
        {**valid, "available_at": "20260824T030000+00:00"},
        {**valid, "available_at": "2026-W35-1T03:00:00+00:00"},
        {**valid, "available_at": "2026-08-24T03:00:00+00:00:01"},
        {**valid, "available_at": "2026-08-24T03:00:60Z"},
        {**valid, "available_at": "2026-01-01T12:34:60+09:00"},
        {**valid, "available_at": "2016-12-31T23:59:60Z"},
        {**valid, "job_id": str(stable_uuid("stored:other-job"))},
    )
    for raw_payload in invalid_payloads:
        payload = OutboxEventRecordPayloadJson(
            FrozenJsonObject.from_mapping(raw_payload)
        )
        with pytest.raises(PersistenceError) as caught:
            _map_outbox_payload(row, payload)
        assert caught.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert str(caught.value) == "STORAGE_CORRUPTION"
        assert caught.value.__cause__ is None


_MISSING_EVENT_VALIDATOR_TYPES = tuple(
    event_type
    for event_type in EVENT_BY_TYPE
    if event_type != OpsJobRequested.DESCRIPTOR_TYPE
)


@pytest.mark.parametrize(
    "event_type",
    _MISSING_EVENT_VALIDATOR_TYPES,
    ids=_MISSING_EVENT_VALIDATOR_TYPES,
)
def test_every_unimplemented_event_descriptor_rejects_missing_validator(
    event_type: str,
) -> None:
    assert len(_MISSING_EVENT_VALIDATOR_TYPES) == 17
    row = _stored_outbox_row(suffix=f"missing-validator-{event_type}")
    unimplemented = EVENT_BY_TYPE[event_type]
    with pytest.raises(PersistenceError) as missing_validator:
        mappers.map_ops_outbox_event_from_row(
            id=row[0],
            event_type=unimplemented.event_type,
            event_version=unimplemented.event_version,
            producer=unimplemented.producer,
            aggregate_type=unimplemented.aggregate_type,
            aggregate_id=row[5],
            aggregate_version=row[6],
            correlation_id=row[7],
            causation_id=row[8],
            actor_type=row[9],
            actor_id=row[10],
            payload=row[11],
            payload_schema_hash=Sha256Digest(unimplemented.schema_sha256),
            status=row[13],
            available_at=row[14],
            published_at=row[15],
            publish_attempts=row[16],
            last_error=row[17],
            created_at=row[18],
        )
    assert missing_validator.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
    assert str(missing_validator.value) == "STORAGE_CORRUPTION"
    assert missing_validator.value.__cause__ is None


def test_failed_enter_unwinds_duplicate_transaction_registration() -> None:
    duplicate_id = stable_uuid("duplicate-transaction")
    factory, store, pool = make_factory(id_factory=lambda: duplicate_id)
    first = factory.begin(make_context(suffix="first-duplicate"))
    second = factory.begin(make_context(suffix="second-duplicate"))
    first.__enter__()
    try:
        with pytest.raises(PersistenceError) as caught:
            second.__enter__()
        assert caught.value.code is PersistenceErrorCode.TRANSACTION_OWNERSHIP
        assert second._connection is None
        assert second._session is None
        assert second._transaction is None
        assert second._entered is False
        assert pool.trace[-4:] == [
            "session.rollback",
            "session.close",
            "connection.invalidate",
            "connection.close",
        ]
        first.commit()
    finally:
        first.__exit__(None, None, None)
    assert store.snapshot().revision == 1


def test_joined_scope_retains_no_outer_or_forbidden_capability() -> None:
    factory, _store, _pool = make_factory()
    context = make_context(suffix="narrow-join")
    with factory.begin(context) as outer:
        joined_scope = factory.join(outer.join_token(), context)
        assert type(joined_scope) is MemoryJoinedOpsUnitOfWork
        assert "_outer" not in MemoryJoinedOpsUnitOfWork.__slots__
        assert "_transaction" not in MemoryJoinedOpsUnitOfWork.__slots__
        for name in ("commit", "rollback", "idempotency", "join_token", "outer"):
            assert not hasattr(joined_scope, name)
        for slot in MemoryJoinedOpsUnitOfWork.__slots__:
            value = getattr(joined_scope, slot)
            assert type(value) is not MemoryOpsUnitOfWork
            assert type(value) is not MemoryIdempotencyRepository
        transaction_scope = joined_scope._transaction_scope
        for name in ("commit", "rollback", "idempotency", "join_token", "outer"):
            assert not hasattr(transaction_scope, name)
        with joined_scope as joined:
            joined.object_artifacts.add(make_artifact(suffix="401"))
        outer.commit()


def test_join_requires_exact_active_outer_context_before_any_exposure() -> None:
    factory, store, _pool = make_factory()
    context = make_context(suffix="join-context")
    with factory.begin(context) as outer:
        join_capability = outer.join_token()
        transaction = outer._transaction
        assert transaction is not None
        mismatches = (
            replace(context, command_id=stable_uuid("join:other-command")),
            replace(context, correlation_id=stable_uuid("join:other-correlation")),
            replace(context, causation_id=None),
            replace(
                context,
                actor=Actor(ActorType.SERVICE, stable_uuid("join:other-actor")),
            ),
            replace(context, source="tests.st0308.other"),
            replace(context, occurred_at=context.occurred_at + timedelta(seconds=1)),
        )
        for mismatched_context in mismatches:
            before = store.snapshot()
            with pytest.raises(PersistenceError) as caught:
                factory.join(join_capability, mismatched_context)
            assert caught.value.code is PersistenceErrorCode.TRANSACTION_OWNERSHIP
            assert caught.value.__cause__ is None
            assert transaction.joined_count == 0
            assert store.snapshot() == before
            assert transaction.state.object_artifacts == {}
            assert transaction.state.audit_events == []
            assert transaction.state.outbox_events == []

        same_context_scope = factory.join(join_capability, context)
        assert transaction.joined_count == 0
        with same_context_scope as joined:
            assert transaction.joined_count == 1
            assert joined.context is context
            assert joined.object_artifacts is outer.object_artifacts
        assert transaction.joined_count == 0
        outer.rollback()
    assert store.snapshot().revision == 0


def test_claim_reservation_exposes_loser_decision_before_commit_and_releases() -> None:
    factory, store, _pool = make_factory(id_prefix="concurrent-claim")
    first = factory.begin_idempotent(make_context(suffix="claim-owner"))
    second = factory.begin_idempotent(make_context(suffix="claim-loser"))
    first.__enter__()
    second.__enter__()
    try:
        assert isinstance(first.idempotency.claim(_claim()), ClaimGranted)
        assert isinstance(second.idempotency.claim(_claim()), ClaimInProgress)
        assert isinstance(
            second.idempotency.claim(_claim(digest="c" * 64)), PayloadMismatch
        )
        assert store.snapshot().idempotency_records == ()
        first.rollback()
        assert isinstance(second.idempotency.claim(_claim()), ClaimGranted)
        second.commit()
    finally:
        first.__exit__(None, None, None)
        second.__exit__(None, None, None)
    assert len(store.snapshot().idempotency_records) == 1


def test_outbox_metadata_terminal_shape_and_artifact_fk_fail_closed() -> None:
    factory, store, _pool = make_factory(id_prefix="invariant")
    with factory.begin(make_context(suffix="outbox-metadata")) as outer:
        outer.outbox.append_many((ValidatedOutboxEvent(make_event()),))
        outer.commit()
    outbox = store.snapshot().outbox_events[0]
    with pytest.raises(ValueError, match="INVALID_OPS_PERSISTENCE_VALUE"):
        replace(outbox, producer="unknown")
    row = mappers.map_ops_outbox_event_to_row(outbox)
    with pytest.raises(PersistenceError) as corrupt:
        mappers.map_ops_outbox_event_from_row(
            id=row[0],
            event_type="jp.raos.unknown.v1",
            event_version=row[2],
            producer=row[3],
            aggregate_type=row[4],
            aggregate_id=row[5],
            aggregate_version=row[6],
            correlation_id=row[7],
            causation_id=row[8],
            actor_type=row[9],
            actor_id=row[10],
            payload=row[11],
            payload_schema_hash=row[12],
            status=row[13],
            available_at=row[14],
            published_at=row[15],
            publish_attempts=row[16],
            last_error=row[17],
            created_at=row[18],
        )
    assert corrupt.value.code is PersistenceErrorCode.STORAGE_CORRUPTION

    terminal = store.snapshot().idempotency_records
    assert terminal == ()
    factory, _store, _pool = make_factory(id_prefix="terminal-invariant")
    with factory.begin_idempotent(make_context(suffix="terminal-invariant")) as outer:
        granted = outer.idempotency.claim(_claim())
        assert isinstance(granted, ClaimGranted)
        in_progress = next(
            iter(outer._transaction.state.idempotency_records.values())  # type: ignore[union-attr]
        )
        with pytest.raises(ValueError, match="INVALID_OPS_PERSISTENCE_VALUE"):
            replace(
                in_progress,
                response_status=200,
                response_body=FrozenJsonObject.from_mapping({"invalid": True}),
            )
        with pytest.raises(PersistenceError) as missing_artifact:
            outer.idempotency.complete_success(
                granted.handle,
                IdempotencyOutcome(
                    200,
                    response_artifact_id=make_artifact(suffix="402").id,
                ),
            )
        assert missing_artifact.value.code is PersistenceErrorCode.INTEGRITY_CONFLICT


def test_commit_clone_fault_is_precommit_and_unknown_commit_invalidates() -> None:
    def broken_clone(_state: object) -> object:
        raise RuntimeError("untrusted clone detail")

    store = MemoryPersistenceStore(
        state_cloner=cast(object, broken_clone)  # type: ignore[arg-type]
    )
    factory, _store, pool = make_factory(store=store)
    with factory.begin(make_context(suffix="clone-fault")) as outer:
        outer.object_artifacts.add(make_artifact(suffix="403"))
        with pytest.raises(PersistenceError) as caught:
            outer.commit()
        assert caught.value.code is PersistenceErrorCode.STORAGE_CORRUPTION
        assert str(caught.value) == "STORAGE_CORRUPTION"
    assert "session.commit" not in pool.trace
    assert "session.rollback" in pool.trace
    assert store.snapshot().revision == 0

    unknown_factory, unknown_store, unknown_pool = make_factory(
        commit_mode=MemoryCommitMode.UNKNOWN
    )
    unknown = unknown_factory.begin(make_context(suffix="unknown-invalidated"))
    unknown.__enter__()
    unknown.object_artifacts.add(make_artifact(suffix="404"))
    with pytest.raises(PersistenceError) as caught:
        unknown.commit()
    assert caught.value.code is PersistenceErrorCode.UNKNOWN_COMMIT
    assert unknown_store.snapshot().revision == 0
    assert unknown_pool.trace[-3:] == [
        "connection.invalidate",
        "session.close",
        "connection.close",
    ]
    assert "session.rollback" not in unknown_pool.trace
    with pytest.raises(PersistenceError) as closed:
        unknown.commit()
    assert closed.value.code is PersistenceErrorCode.TRANSACTION_CLOSED
    unknown.__exit__(None, None, None)
    assert "session.rollback" not in unknown_pool.trace


def test_generator_rejects_product_boundary_drift() -> None:
    runtime = copy.deepcopy(
        generator.load_yaml(generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH)
    )
    generator._validate_product_contract(runtime)

    mutations = (
        lambda candidate: candidate["boundary"].__setitem__("production", "ALLOWED"),
        lambda candidate: candidate["runtime_decisions"].__setitem__(
            "cross_module_write", "ALLOWED"
        ),
        lambda candidate: candidate["execution_control"].__setitem__(
            "caller_generic_callback", "ALLOWED"
        ),
        lambda candidate: candidate["identity_runtime"].__setitem__(
            "query_owner", "ST0306_MIGRATION"
        ),
        lambda candidate: candidate["document"].__setitem__(
            "formal_tst_005", "VALIDATED"
        ),
    )
    for mutate in mutations:
        candidate_runtime = copy.deepcopy(runtime)
        mutate(candidate_runtime)
        with pytest.raises(generator.PersistenceBuildError):
            generator._validate_product_contract(candidate_runtime)

    metadata = json.loads(
        (
            generator.REPO_ROOT
            / "changes/st-0308/generated/persistence-runtime.ops-reference.v1.json"
        ).read_bytes()
    )
    assert generator.RUNTIME_CONTRACT_PATH.as_posix() in metadata["source_sha256"]
    assert metadata["runtime_artifacts_implemented"]["scope"] == (
        "FULL_LOCAL_PERSISTENCE_CATALOG_WITH_OPS_REFERENCE_SQL"
    )
    assert (
        metadata["runtime_artifacts_implemented"]["owner_generated_table_metadata"]
        == 103
    )
    assert (
        metadata["runtime_artifacts_implemented"][
            "owner_generated_read_only_view_metadata"
        ]
        == 1
    )
    assert "runtime_table_mappers" not in metadata["physical_parity"]
    assert metadata["contract_inventory_verified"]["runtime_mapper_coverage"] == (
        "FULL_EXACT_PHYSICAL_CHECK_GUARDS"
    )


def test_generator_rejects_unbound_product_inventory_drift() -> None:
    runtime = copy.deepcopy(
        generator.load_yaml(generator.REPO_ROOT / generator.RUNTIME_CONTRACT_PATH)
    )
    generator._validate_product_contract(runtime)

    mutations = (
        lambda candidate: candidate.__setitem__("publication_authority", "GRANTED"),
        lambda candidate: candidate["sources"][0].__setitem__(
            "production_authority", "GRANTED"
        ),
        lambda candidate: candidate["sources"].pop(),
        lambda candidate: candidate["sources"].append(
            copy.deepcopy(candidate["sources"][0])
        ),
        lambda candidate: candidate["sources"][0].__setitem__(
            "path", candidate["sources"][1]["path"]
        ),
        lambda candidate: candidate["sources"].reverse(),
        lambda candidate: candidate["sources"][-1].pop("authority"),
        lambda candidate: candidate["sources"][-1].__setitem__(
            "authority", "PRODUCTION"
        ),
        lambda candidate: candidate["physical_fragments"].pop(),
        lambda candidate: candidate["physical_fragments"][0].__setitem__(
            "authority", "PRODUCTION"
        ),
        lambda candidate: candidate["executable_matrices"]["identity"].__setitem__(
            "path",
            candidate["executable_matrices"]["concurrency"]["path"],
        ),
        lambda candidate: candidate["executable_matrices"]["identity"].__setitem__(
            "authority", "PRODUCTION"
        ),
        lambda candidate: candidate["representative_slices"][
            "ops_reference"
        ].__setitem__("authority", "PRODUCTION"),
        lambda candidate: candidate["inventory"].__setitem__("tables", 104),
        lambda candidate: candidate["inventory"].__setitem__("tables", True),
        lambda candidate: candidate["inventory"].__setitem__(
            "contract_bidirectional_table_mapper_rows", True
        ),
        lambda candidate: candidate["inventory"].__setitem__(
            "repository_relation_ownership", 104
        ),
        lambda candidate: candidate["two_way_gates"].pop(),
    )
    for mutate in mutations:
        candidate_runtime = copy.deepcopy(runtime)
        mutate(candidate_runtime)
        with pytest.raises(generator.PersistenceBuildError):
            generator._validate_product_contract(candidate_runtime)

    metadata = json.loads(
        (
            generator.REPO_ROOT
            / "changes/st-0308/generated/persistence-runtime.ops-reference.v1.json"
        ).read_bytes()
    )
    assert set(metadata["matrix_sha256"]) == set(generator.MATRIX_KEYS)
    assert set(generator.EXPECTED_RUNTIME_SOURCE_PATHS) <= set(
        metadata["source_sha256"]
    )
    inventory = metadata["contract_inventory_verified"]
    assert inventory["repository_owned_relation_count"] == 103
    assert len(inventory["repository_owned_relation_identities"]) == 103
    assert inventory["repository_excluded_relation_count"] == 1
    assert inventory["repository_excluded_relation_identities"] == ["ops.inbox_receipt"]
    assert inventory["total_relation_contract_identities"] == 104
    assert "repository_relation_ownership" not in inventory
    parity = metadata["physical_parity"]
    assert parity["physical_view_identities_matched_to_relation_contracts"] == 1
    assert parity["physical_view_column_type_nullability_parity"] == (
        "POSTGRESQL_RUNTIME_NOT_EXECUTED"
    )
    assert "physical_views_matched_to_relation_contracts" not in parity
    runtime_artifacts = metadata["runtime_artifacts_implemented"]
    assert "explicit_mappers" not in runtime_artifacts
    assert "event_runtime" not in runtime_artifacts
    assert "PRESENT_OUTSIDE_OWNER_OUTPUTS" not in json.dumps(metadata)
