"""Owner-private archive, UoW, restart, and ambiguity checks for ST-0502 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
from threading import Barrier
from uuid import UUID

import pytest

from raos.adapters.recorded_rakuten_item_search_runtime_v2 import (
    RecordedRakutenItemSearchPageProviderV2,
)
from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
    SqliteCommitFaultV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    CommitRecoveryOutcomeV2,
    IngestionStepOutcomeV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchStepCommandV2,
    ItemSearchStepResultV2,
    ItemSearchWireRequestV2,
    ItemSearchPlanV2,
    ItemSearchProviderObservationV2,
    parse_item_search_page_v2,
    success_transition_v2,
)
from raos.application.catalog.rakuten_item_search_runtime_v2 import (
    RakutenItemSearchRuntimeServiceV2,
)

from runtime_v2_fixtures import (
    OBSERVED_AT_V2,
    SESSION_ID_V2,
    runtime_command_v2,
    runtime_exchange_v2,
    runtime_payload_v2,
    runtime_plan_v2,
    runtime_provider_v2,
    runtime_service_v2,
    runtime_store_v2,
    runtime_success_observation_v2,
)


def _completed_runtime(
    tmp_path: Path,
) -> tuple[
    ItemSearchPlanV2,
    ItemSearchWireRequestV2,
    ItemSearchProviderObservationV2,
    RecordedRakutenItemSearchPageProviderV2,
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
    RakutenItemSearchRuntimeServiceV2,
    ItemSearchStepCommandV2,
    ItemSearchStepResultV2,
]:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    provider = runtime_provider_v2(runtime_exchange_v2(request, observation))
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )
    result = service.step_once(command)
    return plan, request, observation, provider, store, service, command, result


def test_sqlite_blob_archive_round_trip_receipt_hash_version_and_permissions(
    tmp_path: Path,
) -> None:
    (
        _plan,
        _request,
        observation,
        _provider,
        store,
        _service,
        _command,
        result,
    ) = _completed_runtime(tmp_path)
    receipt = result.persisted.receipt
    assert receipt is not None and observation.raw_body is not None

    assert stat.S_IMODE((tmp_path / "private").stat().st_mode) == 0o700
    assert stat.S_IMODE(store.database_path.stat().st_mode) == 0o600
    assert store.database_path.stat().st_nlink == 1
    assert tuple(path.name for path in (tmp_path / "private").iterdir()) == (
        "st0502-item-search-archive.sqlite3",
    )
    assert receipt.artifact_sha256 == hashlib.sha256(observation.raw_body).hexdigest()
    assert receipt.byte_size == len(observation.raw_body)
    assert receipt.artifact_version == 1
    assert receipt.logical_key == (
        f"sha256/{receipt.artifact_sha256[:2]}/{receipt.artifact_sha256}"
    )
    assert store.read_raw(receipt) == observation.raw_body

    with sqlite3.connect(store.database_path) as connection:
        row = connection.execute(
            "SELECT typeof(body), length(body), sha256, logical_key, source FROM st0502_artifacts"
        ).fetchone()
    assert row == (
        "blob",
        len(observation.raw_body),
        receipt.artifact_sha256,
        receipt.logical_key,
        "RAKUTEN_ITEM_SEARCH_20260701",
    )


def test_restart_rehydrates_hash_bound_page_and_idempotency_journal(
    tmp_path: Path,
) -> None:
    (
        plan,
        request,
        observation,
        _provider,
        store,
        _service,
        command,
        result,
    ) = _completed_runtime(tmp_path)
    restarted_store = runtime_store_v2(tmp_path / "private")
    restarted_provider = runtime_provider_v2(runtime_exchange_v2(request, observation))
    restarted = runtime_service_v2(
        provider=restarted_provider,
        store=restarted_store,
    )

    replay = restarted.step_once(command)
    recovery = restarted.recover_commit(command)

    assert restarted_store.load_session(SESSION_ID_V2).plan == plan
    assert replay.persisted == result.persisted
    assert replay.page == result.page
    assert recovery.outcome is CommitRecoveryOutcomeV2.COMMITTED
    assert recovery.persisted == result.persisted
    assert restarted_provider.call_count == 0
    assert store.database_path == restarted_store.database_path


def test_content_addressed_body_is_deduplicated_across_session_receipts(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    second_at = OBSERVED_AT_V2 + timedelta(seconds=1)
    first_observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    assert first_observation.raw_body is not None
    second_observation = runtime_success_observation_v2(
        request,
        observed_at=second_at,
        raw=first_observation.raw_body,
    )
    provider = runtime_provider_v2(
        runtime_exchange_v2(request, first_observation, ordinal=1),
        runtime_exchange_v2(request, second_observation, ordinal=2),
    )
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    second_session = UUID("12345678-1234-4234-8234-123456789002")
    for session_id, observed_at in (
        (SESSION_ID_V2, OBSERVED_AT_V2),
        (second_session, second_at),
    ):
        service.create_session(
            session_id=session_id,
            plan=plan,
            created_at=OBSERVED_AT_V2,
        )
        service.step_once(
            ItemSearchStepCommandV2(
                operation_id=UUID(
                    "12345678-1234-4234-8234-123456789111"
                    if session_id == SESSION_ID_V2
                    else "12345678-1234-4234-8234-123456789112"
                ),
                session_id=session_id,
                expected_version=0,
                observed_at=observed_at,
            )
        )

    with sqlite3.connect(store.database_path) as connection:
        artifacts = connection.execute(
            "SELECT count(*), min(artifact_version), max(artifact_version) FROM st0502_artifacts"
        ).fetchone()
        receipts = connection.execute(
            "SELECT count(*), count(DISTINCT artifact_sha256) FROM st0502_receipts"
        ).fetchone()
    assert artifacts == (1, 1, 1)
    assert receipts == (2, 1)


@pytest.mark.parametrize(
    ("fault", "expected_outcome", "recovery"),
    (
        (
            SqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
            IngestionStepOutcomeV2.COMMIT_KNOWN_ROLLBACK,
            CommitRecoveryOutcomeV2.NOT_COMMITTED,
        ),
        (
            SqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            IngestionStepOutcomeV2.COMMIT_UNKNOWN,
            CommitRecoveryOutcomeV2.NOT_COMMITTED,
        ),
        (
            SqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,
            IngestionStepOutcomeV2.COMMIT_UNKNOWN,
            CommitRecoveryOutcomeV2.COMMITTED,
        ),
    ),
)
def test_commit_fault_recovery_distinguishes_known_and_ambiguous_results(
    tmp_path: Path,
    fault: SqliteCommitFaultV2,
    expected_outcome: IngestionStepOutcomeV2,
    recovery: CommitRecoveryOutcomeV2,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    provider = runtime_provider_v2(runtime_exchange_v2(request, observation))
    store = runtime_store_v2(
        tmp_path / "private",
        commit_faults=(SqliteCommitFaultV2.NONE, fault),
    )
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    command = runtime_command_v2(
        operation_index=0,
        expected_version=0,
        observed_at=OBSERVED_AT_V2,
    )

    result = service.step_once(command)
    restarted_store = runtime_store_v2(tmp_path / "private")
    restarted_provider = runtime_provider_v2(runtime_exchange_v2(request, observation))
    restarted = runtime_service_v2(
        provider=restarted_provider,
        store=restarted_store,
    )

    assert result.persisted.outcome is expected_outcome
    assert restarted.recover_commit(command).outcome is recovery
    expected_version = 1 if recovery is CommitRecoveryOutcomeV2.COMMITTED else 0
    assert restarted_store.load_session(SESSION_ID_V2).version == expected_version


def test_same_operation_with_different_payload_is_an_idempotency_conflict(
    tmp_path: Path,
) -> None:
    *_, service, command, _result = _completed_runtime(tmp_path)
    conflicting = ItemSearchStepCommandV2(
        operation_id=command.operation_id,
        session_id=command.session_id,
        expected_version=command.expected_version,
        observed_at=command.observed_at + timedelta(seconds=1),
    )

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        service.recover_commit(conflicting)
    assert captured.value.code is ItemSearchRuntimeFailureCode.IDEMPOTENCY_CONFLICT


def test_stale_session_compare_and_swap_is_rejected_without_second_archive(
    tmp_path: Path,
) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    provider = runtime_provider_v2(runtime_exchange_v2(request, observation))
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(provider=provider, store=store)
    service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    stale = store.load_session(SESSION_ID_V2)
    service.step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    page = service.step_once(
        runtime_command_v2(
            operation_index=1,
            expected_version=1,
            observed_at=OBSERVED_AT_V2 + timedelta(seconds=1),
        )
    )
    assert page.persisted.outcome is IngestionStepOutcomeV2.COMPLETED

    parsed = parse_item_search_page_v2(request=request, observation=observation)
    after, _outcome = success_transition_v2(
        session=stale,
        page=parsed,
        observed_at=OBSERVED_AT_V2,
    )
    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        store.commit_success(
            command=ItemSearchStepCommandV2(
                operation_id=UUID("12345678-1234-4234-8234-123456789199"),
                session_id=SESSION_ID_V2,
                expected_version=0,
                observed_at=OBSERVED_AT_V2,
            ),
            before=stale,
            after=after,
            request=request,
            observation=observation,
            page=parsed,
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.CONCURRENCY_CONFLICT


def test_concurrent_writers_commit_exactly_one_atomic_step(tmp_path: Path) -> None:
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    first_store = runtime_store_v2(tmp_path / "private")
    second_store = runtime_store_v2(tmp_path / "private")
    first_service = runtime_service_v2(
        provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
        store=first_store,
    )
    first_service.create_session(
        session_id=SESSION_ID_V2,
        plan=plan,
        created_at=OBSERVED_AT_V2,
    )
    before = first_store.load_session(SESSION_ID_V2)
    page = parse_item_search_page_v2(request=request, observation=observation)
    after, _outcome = success_transition_v2(
        session=before,
        page=page,
        observed_at=OBSERVED_AT_V2,
    )
    commands = (
        ItemSearchStepCommandV2(
            operation_id=UUID("12345678-1234-4234-8234-123456789201"),
            session_id=SESSION_ID_V2,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        ),
        ItemSearchStepCommandV2(
            operation_id=UUID("12345678-1234-4234-8234-123456789202"),
            session_id=SESSION_ID_V2,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        ),
    )
    barrier = Barrier(2)

    def commit(
        store: OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
        command: ItemSearchStepCommandV2,
    ) -> str:
        barrier.wait()
        try:
            store.commit_success(
                command=command,
                before=before,
                after=after,
                request=request,
                observation=observation,
                page=page,
            )
        except ItemSearchRuntimeFailure as error:
            return error.code.value
        return "COMMITTED"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(commit, (first_store, second_store), commands))

    assert sorted(outcomes) == ["COMMITTED", "CONCURRENCY_CONFLICT"]
    assert first_store.load_session(SESSION_ID_V2).version == 1
    with sqlite3.connect(first_store.database_path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM st0502_artifacts"
        ).fetchone() == (1,)
        assert connection.execute(
            "SELECT COUNT(*) FROM st0502_commands"
        ).fetchone() == (1,)


@pytest.mark.parametrize(
    "target",
    ("artifact", "artifact_sha", "session", "result"),
)
def test_tampering_is_detected_before_raw_state_or_result_is_returned(
    tmp_path: Path,
    target: str,
) -> None:
    *_, store, service, command, result = _completed_runtime(tmp_path)
    receipt = result.persisted.receipt
    assert receipt is not None
    statements = {
        "artifact": "UPDATE st0502_artifacts SET body = X'7B7D'",
        "artifact_sha": "UPDATE st0502_artifacts SET sha256 = '0000000000000000000000000000000000000000000000000000000000000000'",
        "session": "UPDATE st0502_sessions SET state_bytes = X'7B7D'",
        "result": "UPDATE st0502_commands SET result_bytes = X'7B7D'",
    }
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(statements[target])
        connection.commit()

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        if target in {"artifact", "artifact_sha"}:
            store.read_raw(receipt)
        elif target == "session":
            store.load_session(SESSION_ID_V2)
        else:
            service.recover_commit(command)
    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY


@pytest.mark.parametrize("drift", ("user_version", "extra_table"))
def test_schema_or_version_drift_is_rejected_on_the_next_store_operation(
    tmp_path: Path,
    drift: str,
) -> None:
    store = runtime_store_v2(tmp_path / "private")
    with sqlite3.connect(store.database_path) as connection:
        if drift == "user_version":
            connection.execute("PRAGMA user_version = 2")
        else:
            connection.execute("CREATE TABLE unexpected(value TEXT) STRICT")
        connection.commit()

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        store.load_session(SESSION_ID_V2)
    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY


def test_same_columns_with_weakened_check_constraint_is_schema_drift(
    tmp_path: Path,
) -> None:
    store = runtime_store_v2(tmp_path / "private")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DROP TABLE st0502_sessions")
        connection.execute(
            """CREATE TABLE st0502_sessions (
                session_id TEXT PRIMARY KEY,
                plan_fingerprint TEXT NOT NULL,
                state_bytes BLOB NOT NULL,
                state_sha256 TEXT NOT NULL,
                version INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            ) STRICT"""
        )
        connection.commit()

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        store.load_session(SESSION_ID_V2)
    assert captured.value.code is ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY


def test_traversal_symlink_hardlink_and_permissive_root_fail_closed(
    tmp_path: Path,
) -> None:
    traversal = tmp_path / "safe" / ".." / "escape"
    with pytest.raises(ItemSearchRuntimeFailure) as traversal_error:
        runtime_store_v2(traversal)
    assert traversal_error.value.code is ItemSearchRuntimeFailureCode.UNSAFE_PATH

    real_root = tmp_path / "real-root"
    real_root.mkdir(mode=0o700)
    symlink_root = tmp_path / "symlink-root"
    symlink_root.symlink_to(real_root, target_is_directory=True)
    with pytest.raises(ItemSearchRuntimeFailure) as symlink_error:
        runtime_store_v2(symlink_root)
    assert symlink_error.value.code is ItemSearchRuntimeFailureCode.UNSAFE_PATH

    permissive = tmp_path / "permissive"
    permissive.mkdir(mode=0o755)
    with pytest.raises(ItemSearchRuntimeFailure) as mode_error:
        runtime_store_v2(permissive)
    assert mode_error.value.code is ItemSearchRuntimeFailureCode.UNSAFE_PATH

    store = runtime_store_v2(tmp_path / "private")
    hardlink = tmp_path / "archive-hardlink.sqlite3"
    os.link(store.database_path, hardlink)
    with pytest.raises(ItemSearchRuntimeFailure) as hardlink_error:
        store.load_session(SESSION_ID_V2)
    assert hardlink_error.value.code is ItemSearchRuntimeFailureCode.UNSAFE_PATH


def test_database_symlink_is_rejected_before_sqlite_opens_it(tmp_path: Path) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    target = tmp_path / "target.sqlite3"
    target.touch(mode=0o600)
    (root / "st0502-item-search-archive.sqlite3").symlink_to(target)

    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2(
            environment=RuntimeEnvironment.CI,
            root=root,
        )
    assert captured.value.code is ItemSearchRuntimeFailureCode.UNSAFE_PATH
