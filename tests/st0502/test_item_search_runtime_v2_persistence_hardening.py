"""Hostile persistence checks for the mandatory ST-0502 SQLite hardening."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
import hashlib
import json
import os
from pathlib import Path
import sqlite3

import pytest

from raos.adapters.sqlite_rakuten_item_search_runtime_v2 import (
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
)
from raos.domain.catalog.rakuten_item_search_runtime_v2 import (
    ItemSearchIngestionSessionV2,
    ItemSearchRuntimeFailure,
    ItemSearchRuntimeFailureCode,
    ItemSearchStepCommandV2,
    ItemSearchStepResultV2,
    ItemSearchWireRequestV2,
    parse_item_search_page_v2,
    success_transition_v2,
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


_DATABASE_NAME = "st0502-item-search-archive.sqlite3"


def _assert_failure(
    action: Callable[[], object],
    expected: ItemSearchRuntimeFailureCode,
) -> None:
    with pytest.raises(ItemSearchRuntimeFailure) as captured:
        action()
    assert captured.value.code is expected


def _session_only_store(root: Path) -> OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2:
    store = runtime_store_v2(root)
    session = ItemSearchIngestionSessionV2.initial(
        session_id=SESSION_ID_V2,
        plan=runtime_plan_v2(),
        created_at=OBSERVED_AT_V2,
    )
    store.create_session(session)
    return store


@pytest.mark.parametrize("kind", ("empty", "partial", "foreign", "permissive"))
def test_only_exclusive_create_winner_may_initialize_database(
    tmp_path: Path,
    kind: str,
) -> None:
    root = tmp_path / kind
    root.mkdir(mode=0o700)
    database = root / _DATABASE_NAME
    if kind == "empty":
        database.touch(mode=0o600)
    elif kind == "partial":
        database.write_bytes(b"SQLite format 3\x00")
        database.chmod(0o600)
    else:
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE foreign_state(value TEXT)")
        database.chmod(0o644 if kind == "permissive" else 0o600)

    expected = (
        ItemSearchRuntimeFailureCode.UNSAFE_PATH
        if kind == "permissive"
        else ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY
    )
    _assert_failure(
        lambda: runtime_store_v2(root),
        expected,
    )


def _completed_store(
    tmp_path: Path,
) -> tuple[
    OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
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
    store = runtime_store_v2(tmp_path / "private")
    service = runtime_service_v2(
        provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
        store=store,
    )
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
    return store, command, result


def test_process_local_inode_replacement_and_same_inode_old_bytes_fail_closed(
    tmp_path: Path,
) -> None:
    store = _session_only_store(tmp_path / "same-inode")
    old_bytes = store.database_path.read_bytes()
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    service = runtime_service_v2(
        provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
        store=store,
    )
    service.step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    pinned_inode = store.database_path.stat().st_ino
    store.database_path.write_bytes(old_bytes)
    assert store.database_path.stat().st_ino == pinned_inode
    _assert_failure(
        lambda: store.load_session(SESSION_ID_V2),
        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY,
    )

    replacement_store = _session_only_store(tmp_path / "new-inode")
    replacement = replacement_store.database_path.with_suffix(".replacement")
    replacement.write_bytes(replacement_store.database_path.read_bytes())
    replacement.chmod(0o600)
    assert replacement.stat().st_ino != replacement_store.database_path.stat().st_ino
    os.replace(replacement, replacement_store.database_path)
    _assert_failure(
        lambda: replacement_store.load_session(SESSION_ID_V2),
        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY,
    )


def test_valid_old_snapshot_has_no_false_cross_restart_rollback_claim(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    store = _session_only_store(root)
    old_bytes = store.database_path.read_bytes()
    plan = runtime_plan_v2()
    request = ItemSearchWireRequestV2.from_plan(plan, page=1)
    observation = runtime_success_observation_v2(
        request,
        observed_at=OBSERVED_AT_V2,
        payload=runtime_payload_v2(page=1, page_count=1),
    )
    runtime_service_v2(
        provider=runtime_provider_v2(runtime_exchange_v2(request, observation)),
        store=store,
    ).step_once(
        runtime_command_v2(
            operation_index=0,
            expected_version=0,
            observed_at=OBSERVED_AT_V2,
        )
    )
    # No external anchor exists across restarts. A self-consistent old snapshot is
    # therefore accepted by a fresh process-equivalent store, as documented.
    store.database_path.write_bytes(old_bytes)
    restarted = runtime_store_v2(root)
    assert restarted.load_session(SESSION_ID_V2).version == 0


@pytest.mark.parametrize("mutation", ("json", "uuid", "time"))
def test_canonical_state_bytes_uuid_and_utc_are_required(
    tmp_path: Path,
    mutation: str,
) -> None:
    store = _session_only_store(tmp_path / mutation)
    with sqlite3.connect(store.database_path) as connection:
        payload = connection.execute(
            "SELECT state_bytes FROM st0502_sessions"
        ).fetchone()[0]
        data = json.loads(payload)
        if mutation == "json":
            tampered = json.dumps(data, ensure_ascii=False, sort_keys=False).encode()
        else:
            if mutation == "uuid":
                data["session_id"] = "ABCDEF78-1234-4234-8234-123456789001"
            else:
                data["created_at"] = data["created_at"].replace(
                    ".000000+00:00",
                    "Z",
                )
            tampered = json.dumps(
                data,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        connection.execute(
            "UPDATE st0502_sessions SET state_bytes = ?, state_sha256 = ?",
            (tampered, hashlib.sha256(tampered).hexdigest()),
        )
        connection.commit()
    _assert_failure(
        lambda: store.load_session(SESSION_ID_V2),
        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY,
    )


@pytest.mark.parametrize("target", ("journal_delete", "metadata_rebind"))
def test_false_recovery_is_rejected_after_trigger_bypass_and_restoration(
    tmp_path: Path,
    target: str,
) -> None:
    store, command, _result = _completed_store(tmp_path)
    with sqlite3.connect(store.database_path) as connection:
        if target == "journal_delete":
            trigger = "st0502_journal_no_delete"
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (trigger,),
            ).fetchone()[0]
            connection.execute(f"DROP TRIGGER {trigger}")
            connection.execute("DELETE FROM st0502_journal")
        else:
            trigger = "st0502_page_metadata_no_update"
            sql = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = ?",
                (trigger,),
            ).fetchone()[0]
            connection.execute(f"DROP TRIGGER {trigger}")
            payload = b'{"limit":100,"remaining":98,"reset_at":"2026-08-25T01:04:03.000000+00:00"}'
            connection.execute(
                "UPDATE st0502_page_metadata SET rate_remaining = 98, "
                "payload_bytes = ?, payload_sha256 = ?",
                (payload, hashlib.sha256(payload).hexdigest()),
            )
        connection.execute(sql)
        connection.commit()
    _assert_failure(
        lambda: store.recover_commit(command),
        ItemSearchRuntimeFailureCode.ARCHIVE_INTEGRITY,
    )


def test_repeated_concurrent_classification_is_deterministic(tmp_path: Path) -> None:
    def one_round(index: int) -> tuple[str, str]:
        root = tmp_path / f"round-{index}"
        plan = runtime_plan_v2()
        request = ItemSearchWireRequestV2.from_plan(plan, page=1)
        observation = runtime_success_observation_v2(
            request,
            observed_at=OBSERVED_AT_V2,
            payload=runtime_payload_v2(page=1, page_count=1),
        )
        first = runtime_store_v2(root)
        second = runtime_store_v2(root)
        session = ItemSearchIngestionSessionV2.initial(
            session_id=SESSION_ID_V2,
            plan=plan,
            created_at=OBSERVED_AT_V2,
        )
        first.create_session(session)
        before = first.load_session(SESSION_ID_V2)
        page = parse_item_search_page_v2(request=request, observation=observation)
        after, _ = success_transition_v2(
            session=before,
            page=page,
            observed_at=OBSERVED_AT_V2,
        )

        def commit(
            store: OwnerPrivateSqliteItemSearchUnitOfWorkStoreV2,
            operation_index: int,
        ) -> str:
            try:
                store.commit_success(
                    command=runtime_command_v2(
                        operation_index=operation_index,
                        expected_version=0,
                        observed_at=OBSERVED_AT_V2,
                    ),
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
            outcomes = tuple(executor.map(commit, (first, second), (0, 1)))
        ordered = sorted(outcomes)
        assert len(ordered) == 2
        return ordered[0], ordered[1]

    assert {one_round(index) for index in range(20)} == {
        ("COMMITTED", "CONCURRENCY_CONFLICT")
    }
