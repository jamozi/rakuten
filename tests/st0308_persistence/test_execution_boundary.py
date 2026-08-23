"""Factory-private cancellation/deadline lifecycle regressions."""

from __future__ import annotations

import inspect

import pytest

from raos.adapters.persistence.memory.execution import (
    _ExecutionBudget,
    _ExecutionPoint,
    _ExecutionStateFactory,
)
from raos.adapters.persistence.memory.unit_of_work import MemoryOpsUnitOfWorkFactory
from raos.ports.persistence.context import PersistenceContext
from raos.ports.persistence.errors import PersistenceError, PersistenceErrorCode
from tests.st0308_persistence.support import make_artifact, make_context, make_factory


def test_public_context_and_factory_methods_have_no_execution_control_input() -> None:
    assert tuple(PersistenceContext.__dataclass_fields__) == (
        "command_id",
        "correlation_id",
        "causation_id",
        "actor",
        "source",
        "occurred_at",
    )
    assert tuple(inspect.signature(MemoryOpsUnitOfWorkFactory.begin).parameters) == (
        "self",
        "context",
    )
    assert tuple(inspect.signature(MemoryOpsUnitOfWorkFactory.join).parameters) == (
        "self",
        "join_capability",
        "context",
    )
    assert tuple(
        inspect.signature(MemoryOpsUnitOfWorkFactory.begin_idempotent).parameters
    ) == ("self", "context")


def test_cancel_before_checkout_and_deadline_fail_without_exposure() -> None:
    cancelled_factory, _store, cancelled_pool = make_factory()
    cancelled = cancelled_factory.begin(make_context(suffix="cancel-pre-checkout"))
    cancelled._execution_state._cancel()
    with pytest.raises(PersistenceError) as caught:
        cancelled.__enter__()
    assert caught.value.code is PersistenceErrorCode.CANCELLED
    assert cancelled_pool.trace == []

    deadline_factory, _store, deadline_pool = make_factory()
    deadline_factory._execution_state_factory = _ExecutionStateFactory(
        _ExecutionBudget(timeout_ns=0)
    )
    with pytest.raises(PersistenceError) as expired:
        deadline_factory.begin(make_context(suffix="deadline")).__enter__()
    assert expired.value.code is PersistenceErrorCode.DEADLINE_EXCEEDED
    assert deadline_pool.trace == []


def test_cancelled_active_outer_rolls_back_and_join_reuses_exact_state() -> None:
    factory, store, _pool = make_factory()
    context = make_context(suffix="cancel-active")
    outer = factory.begin(context)
    outer.__enter__()
    try:
        join_capability = outer.join_token()
        joined_scope = factory.join(join_capability, context)
        with joined_scope as joined:
            assert (
                joined.object_artifacts._transaction.execution_state
                is outer._execution_state
            )
        outer._execution_state._cancel()
        with pytest.raises(PersistenceError) as operation:
            outer.object_artifacts.add(make_artifact(suffix="999"))
        assert operation.value.code is PersistenceErrorCode.CANCELLED
        with pytest.raises(PersistenceError) as commit:
            outer.commit()
        assert commit.value.code is PersistenceErrorCode.CANCELLED
    finally:
        outer.__exit__(None, None, None)
    assert store.snapshot().revision == 0
    assert store.snapshot().object_artifacts == ()


def test_success_observes_every_required_lifecycle_boundary() -> None:
    factory, _store, _pool = make_factory()
    outer = factory.begin(make_context(suffix="lifecycle"))
    with outer:
        outer.object_artifacts.get(make_artifact().id)
        outer.flush()
        outer.commit()
    assert outer._execution_state._observations() == (
        _ExecutionPoint.PRE_CHECKOUT,
        _ExecutionPoint.POST_CHECKOUT,
        _ExecutionPoint.POST_IDENTITY,
        _ExecutionPoint.PRE_SESSION_BEGIN,
        _ExecutionPoint.PRE_EXPOSURE,
        _ExecutionPoint.PRE_REPOSITORY_QUERY_OR_DML,
        _ExecutionPoint.PRE_FLUSH,
        _ExecutionPoint.PRE_COMMIT,
        _ExecutionPoint.POST_KNOWN_DRIVER_RETURN,
    )
