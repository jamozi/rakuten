"""Durability, recovery, concurrency, tamper and path checks for ST-0504 V2."""

from __future__ import annotations

from pathlib import Path
import os
import sqlite3
from threading import Barrier, Thread
from uuid import UUID

import pytest

from runtime_v2_support import (
    DECISION_AT_V2,
    DECISION_OPERATION_IDS_V2,
    authorization_fixture_v2,
    persisted_catalog_v2,
    prepared_queue_v2,
    product_identity_store_v2,
    queue_command_v2,
    runtime_v2,
)
from raos.adapters.sqlite_product_identity_runtime_v2 import (
    OwnerPrivateSqliteProductIdentityStoreV2,
    ProductIdentitySqliteCommitFaultV2,
)
from raos.application.catalog.product_identity_runtime_v2 import (
    ProductIdentityHumanDecisionRequestV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.product_identity_runtime_v2 import (
    ProductIdentityDecisionTypeV2,
    ProductIdentityReplayStatusV2,
    ProductIdentityRuntimeFailureCodeV2,
    ProductIdentityRuntimeFailureV2,
)


def _assert_code(
    caught: pytest.ExceptionInfo[ProductIdentityRuntimeFailureV2],
    code: ProductIdentityRuntimeFailureCodeV2,
) -> None:
    assert caught.value.code is code
    assert caught.value.args == (code.value,)


def _request(
    *,
    queue: object,
    authorization: object,
    operation_id: UUID,
    reason: str,
) -> ProductIdentityHumanDecisionRequestV2:
    from runtime_v2_support import AuthorizationFixtureV2
    from raos.domain.catalog.product_identity_runtime_v2 import (
        PersistedProductIdentityReviewQueueV2,
    )

    assert type(queue) is PersistedProductIdentityReviewQueueV2
    assert type(authorization) is AuthorizationFixtureV2
    return ProductIdentityHumanDecisionRequestV2(
        operation_id=operation_id,
        persisted_queue=queue,
        pair_id=queue.queue.pairs[0].pair_id,
        decision_type=ProductIdentityDecisionTypeV2.MERGE,
        reason=reason,
        expected_history_version=1,
        supersedes_decision_id=None,
        decided_at=DECISION_AT_V2,
        session_id=authorization.session.session_id,
        authorization_command=authorization.command,
        authorization_result=authorization.result,
        authorization_checked_at=DECISION_AT_V2,
    )


def test_queue_unknown_after_commit_recovers_exactly(tmp_path: Path) -> None:
    source = persisted_catalog_v2(tmp_path / "catalog")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    store = product_identity_store_v2(
        tmp_path / "store",
        faults=(ProductIdentitySqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,),
    )
    runtime = runtime_v2(authorization=authorization, store=store)

    result = runtime.prepare_review_queue(command)

    assert result.replay_status is ProductIdentityReplayStatusV2.RECOVERED_COMMIT
    assert store.load_review_queue(result.persisted.queue.queue_id) == result.persisted


@pytest.mark.parametrize(
    ("fault", "code"),
    (
        (
            ProductIdentitySqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
            ProductIdentityRuntimeFailureCodeV2.COMMIT_KNOWN_ROLLBACK,
        ),
        (
            ProductIdentitySqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            ProductIdentityRuntimeFailureCodeV2.COMMIT_UNKNOWN,
        ),
    ),
)
def test_queue_precommit_fault_is_not_fabricated_as_success(
    tmp_path: Path,
    fault: ProductIdentitySqliteCommitFaultV2,
    code: ProductIdentityRuntimeFailureCodeV2,
) -> None:
    source = persisted_catalog_v2(tmp_path / "catalog")
    command = queue_command_v2(source)
    authorization = authorization_fixture_v2(tmp_path / "auth")
    store = product_identity_store_v2(tmp_path / "store", faults=(fault,))
    runtime = runtime_v2(authorization=authorization, store=store)

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        runtime.prepare_review_queue(command)
    _assert_code(caught, code)
    assert store.lookup_review_queue(command) is None


def test_decision_unknown_after_commit_recovers_without_duplicate(
    tmp_path: Path,
) -> None:
    runtime, store, authorization, queue = prepared_queue_v2(
        tmp_path,
        faults=(
            ProductIdentitySqliteCommitFaultV2.NONE,
            ProductIdentitySqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,
        ),
    )
    request = _request(
        queue=queue,
        authorization=authorization,
        operation_id=DECISION_OPERATION_IDS_V2[0],
        reason="Human decision with ambiguous commit recovery.",
    )

    recovered = runtime.record_human_decision(request)
    replay = runtime.record_human_decision(request)

    assert recovered.replay_status is ProductIdentityReplayStatusV2.RECOVERED_COMMIT
    assert replay.replay_status is ProductIdentityReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == recovered.persisted
    assert store.list_decisions(queue.queue.queue_id) == (recovered.persisted,)


def test_concurrent_same_version_allows_one_append_only_winner(tmp_path: Path) -> None:
    _runtime, store, _authorization, queue = prepared_queue_v2(tmp_path / "base")
    authorization_a = authorization_fixture_v2(tmp_path / "auth-a", label="A")
    authorization_b = authorization_fixture_v2(tmp_path / "auth-b", label="B")
    runtime_a = runtime_v2(authorization=authorization_a, store=store)
    runtime_b = runtime_v2(authorization=authorization_b, store=store)
    request_a = _request(
        queue=queue,
        authorization=authorization_a,
        operation_id=DECISION_OPERATION_IDS_V2[0],
        reason="Concurrent human decision A.",
    )
    request_b = _request(
        queue=queue,
        authorization=authorization_b,
        operation_id=DECISION_OPERATION_IDS_V2[1],
        reason="Concurrent human decision B.",
    )
    barrier = Barrier(3)
    outcomes: list[str] = []

    def run(runtime: object, request: ProductIdentityHumanDecisionRequestV2) -> None:
        from raos.application.catalog.product_identity_runtime_v2 import (
            DurableProductIdentityRuntimeV2,
        )

        assert type(runtime) is DurableProductIdentityRuntimeV2
        barrier.wait()
        try:
            runtime.record_human_decision(request)
            outcomes.append("COMMITTED")
        except ProductIdentityRuntimeFailureV2 as error:
            outcomes.append(error.code.value)

    first = Thread(target=run, args=(runtime_a, request_a))
    second = Thread(target=run, args=(runtime_b, request_b))
    first.start()
    second.start()
    barrier.wait()
    first.join()
    second.join()

    assert outcomes.count("COMMITTED") == 1
    assert len(outcomes) == 2
    assert (
        outcomes.count(ProductIdentityRuntimeFailureCodeV2.CONCURRENCY_CONFLICT.value)
        == 1
    )
    history = store.list_decisions(queue.queue.queue_id)
    assert len(history) == 1
    assert history[0].history_version == 2


def test_payload_tamper_is_detected_on_next_open(tmp_path: Path) -> None:
    _runtime, store, _authorization, queue = prepared_queue_v2(tmp_path)
    connection = sqlite3.connect(store.database_path)
    connection.execute(
        "UPDATE st0504_pairs SET payload_bytes = ? WHERE pair_id = ?",
        (b"{}", str(queue.queue.pairs[0].pair_id)),
    )
    connection.commit()
    connection.close()

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        store.load_review_queue(queue.queue.queue_id)
    _assert_code(caught, ProductIdentityRuntimeFailureCodeV2.TAMPER_DETECTED)


def test_schema_drift_is_rejected(tmp_path: Path) -> None:
    _runtime, store, _authorization, _queue = prepared_queue_v2(tmp_path)
    connection = sqlite3.connect(store.database_path)
    connection.execute("CREATE TABLE injected_schema (value TEXT) STRICT")
    connection.commit()
    connection.close()

    with pytest.raises(ProductIdentityRuntimeFailureV2) as caught:
        OwnerPrivateSqliteProductIdentityStoreV2(
            environment=RuntimeEnvironment.CI,
            root=store.database_path.parent,
        )
    _assert_code(caught, ProductIdentityRuntimeFailureCodeV2.SCHEMA_INTEGRITY)


def test_path_symlink_hardlink_and_permissions_fail_closed(tmp_path: Path) -> None:
    relative = Path("relative-st0504-private")
    with pytest.raises(ProductIdentityRuntimeFailureV2) as relative_caught:
        OwnerPrivateSqliteProductIdentityStoreV2(
            environment=RuntimeEnvironment.CI,
            root=relative,
        )
    _assert_code(relative_caught, ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    symlink = tmp_path / "symlink"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(ProductIdentityRuntimeFailureV2) as symlink_caught:
        OwnerPrivateSqliteProductIdentityStoreV2(
            environment=RuntimeEnvironment.CI,
            root=symlink,
        )
    _assert_code(symlink_caught, ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH)

    store = OwnerPrivateSqliteProductIdentityStoreV2(
        environment=RuntimeEnvironment.CI,
        root=target,
    )
    hardlink = tmp_path / "database-hardlink"
    os.link(store.database_path, hardlink)
    with pytest.raises(ProductIdentityRuntimeFailureV2) as hardlink_caught:
        store.current_history_version(UUID("92345678-1234-4234-8234-123456789001"))
    _assert_code(hardlink_caught, ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH)
    hardlink.unlink()

    store.database_path.chmod(0o640)
    with pytest.raises(ProductIdentityRuntimeFailureV2) as mode_caught:
        store.current_history_version(UUID("92345678-1234-4234-8234-123456789001"))
    _assert_code(mode_caught, ProductIdentityRuntimeFailureCodeV2.UNSAFE_PATH)


def test_database_and_directory_are_owner_private(tmp_path: Path) -> None:
    root = tmp_path / "private"
    store = OwnerPrivateSqliteProductIdentityStoreV2(
        environment=RuntimeEnvironment.CI,
        root=root,
    )
    assert root.stat().st_mode & 0o777 == 0o700
    assert store.database_path.stat().st_mode & 0o777 == 0o600
    assert store.database_path.stat().st_nlink == 1
    assert store.external_action_count == 0
