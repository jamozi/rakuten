"""Durability, recovery, concurrency, and path-security checks for ST-0602 V2."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import os
import shutil
import sqlite3
from threading import Barrier

import pytest

from raos.adapters.sqlite_fact_extraction_runtime_v2 import (
    FactExtractionSqliteCommitFaultV2,
    OwnerPrivateSqliteFactExtractionStoreV2,
)
from raos.application.evidence.fact_extraction_runtime_v2 import (
    DurableFactExtractionServiceV2,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.evidence.fact_extraction_runtime_v2 import (
    FactExtractionCommandV2,
    FactExtractionFailureCodeV2,
    FactExtractionFailureV2,
    FactExtractionReplayStatusV2,
)
from tests.st0602.runtime_v2_fixtures import (
    exact_dependencies_v2,
    fact_store_v2,
)


def _extract(dependencies, store):
    return DurableFactExtractionServiceV2(store).extract(
        artifact=dependencies.artifact,
        normalization=dependencies.normalization,
    )


def test_restart_retains_exact_append_only_result(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    first = _extract(dependencies, store)
    restarted = OwnerPrivateSqliteFactExtractionStoreV2(
        environment=RuntimeEnvironment.CI,
        root=store.database_path.parent,
    )
    replay = _extract(dependencies, restarted)
    assert replay.replay_status is FactExtractionReplayStatusV2.IDEMPOTENT_REPLAY
    assert replay.persisted == first.persisted
    assert restarted.verify_chain() == (first.persisted.chain_hash, 1)


def test_commit_after_ambiguity_recovers_exactly(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(
        tmp_path,
        faults=(FactExtractionSqliteCommitFaultV2.UNKNOWN_AFTER_COMMIT,),
    )
    result = _extract(dependencies, store)
    assert result.replay_status is FactExtractionReplayStatusV2.RECOVERED_COMMIT
    assert store.verify_chain() == (result.persisted.chain_hash, 1)


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        (
            FactExtractionSqliteCommitFaultV2.KNOWN_BEFORE_COMMIT,
            FactExtractionFailureCodeV2.COMMIT_KNOWN_ROLLBACK,
        ),
        (
            FactExtractionSqliteCommitFaultV2.UNKNOWN_BEFORE_COMMIT,
            FactExtractionFailureCodeV2.COMMIT_UNKNOWN,
        ),
    ],
)
def test_before_commit_faults_leave_no_record(tmp_path, fault, code) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path, faults=(fault,))
    with pytest.raises(FactExtractionFailureV2) as captured:
        _extract(dependencies, store)
    assert captured.value.code is code
    assert store.verify_chain() == ("0" * 64, 0)


def test_idempotency_payload_conflict_fails_closed(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    result = _extract(dependencies, store)
    changed_binding = replace(
        result.persisted.command.source_binding,
        catalog_batch_sha256="f" * 64,
    )
    conflicting = FactExtractionCommandV2.issue(changed_binding)
    assert conflicting.idempotency_key == result.persisted.command.idempotency_key
    assert conflicting.payload_sha256 != result.persisted.command.payload_sha256
    with pytest.raises(FactExtractionFailureV2) as captured:
        store.lookup(conflicting)
    assert captured.value.code is FactExtractionFailureCodeV2.IDEMPOTENCY_CONFLICT


def test_concurrent_calls_never_duplicate_and_eventually_replay(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    barrier = Barrier(8)

    def run() -> object:
        barrier.wait()
        try:
            return _extract(dependencies, store)
        except FactExtractionFailureV2 as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = tuple(pool.map(lambda _index: run(), range(8)))
    successes = [
        item for item in outcomes if not isinstance(item, FactExtractionFailureCodeV2)
    ]
    failures = [
        item for item in outcomes if isinstance(item, FactExtractionFailureCodeV2)
    ]
    assert successes
    assert all(
        item is FactExtractionFailureCodeV2.CONCURRENCY_CONFLICT for item in failures
    )
    assert store.verify_chain()[1] == 1
    assert (
        _extract(dependencies, store).replay_status
        is FactExtractionReplayStatusV2.IDEMPOTENT_REPLAY
    )


def test_schema_and_payload_tamper_are_detected(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    _extract(dependencies, store)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("DROP TRIGGER st0602_batches_no_update")
        connection.execute(
            "UPDATE st0602_batches SET batch_bytes = zeroblob(length(batch_bytes))"
        )
    with pytest.raises(FactExtractionFailureV2) as captured:
        store.verify_chain()
    assert captured.value.code in {
        FactExtractionFailureCodeV2.SCHEMA_INTEGRITY,
        FactExtractionFailureCodeV2.TAMPER_DETECTED,
    }


def test_immutable_records_reject_update_and_delete(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    _extract(dependencies, store)
    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM st0602_outbox")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE st0602_facts SET ordinal = ordinal + 1")


def test_preexisting_empty_or_partial_database_is_never_initialized(tmp_path) -> None:
    for name, partial in (("empty", False), ("partial", True)):
        root = tmp_path / name
        root.mkdir(mode=0o700)
        database = root / "st0602-fact-extraction.sqlite3"
        database.touch(mode=0o600)
        if partial:
            with sqlite3.connect(database) as connection:
                connection.execute("CREATE TABLE attacker_material(value TEXT)")
        database.chmod(0o600)
        with pytest.raises(FactExtractionFailureV2) as captured:
            OwnerPrivateSqliteFactExtractionStoreV2(
                environment=RuntimeEnvironment.CI,
                root=root,
            )
        assert captured.value.code is FactExtractionFailureCodeV2.SCHEMA_INTEGRITY


def test_inode_replacement_and_hardlink_are_detected(tmp_path) -> None:
    store = fact_store_v2(tmp_path)
    database = store.database_path
    backup = database.with_suffix(".replacement")
    shutil.copyfile(database, backup)
    backup.chmod(0o600)
    os.replace(backup, database)
    with pytest.raises(FactExtractionFailureV2) as captured:
        store.verify_chain()
    assert captured.value.code is FactExtractionFailureCodeV2.TAMPER_DETECTED

    second_root = tmp_path / "hardlink-case"
    second = fact_store_v2(second_root)
    link = second.database_path.with_suffix(".linked")
    os.link(second.database_path, link)
    with pytest.raises(FactExtractionFailureV2) as hardlink_failure:
        second.verify_chain()
    assert hardlink_failure.value.code is FactExtractionFailureCodeV2.UNSAFE_PATH


def test_process_lifetime_chain_ancestry_rejects_longer_rewrite(tmp_path) -> None:
    pinned_dependencies = exact_dependencies_v2(
        tmp_path / "pinned-source",
        item_name="Pinned source",
    )
    pinned_store = fact_store_v2(tmp_path / "pinned-store")
    _extract(pinned_dependencies, pinned_store)

    replacement_store = fact_store_v2(tmp_path / "replacement-store")
    _extract(
        exact_dependencies_v2(
            tmp_path / "replacement-source-1",
            item_name="Replacement one",
        ),
        replacement_store,
    )
    _extract(
        exact_dependencies_v2(
            tmp_path / "replacement-source-2",
            item_name="Replacement two",
        ),
        replacement_store,
    )
    assert replacement_store.verify_chain()[1] == 2

    replacement_bytes = replacement_store.database_path.read_bytes()
    with pinned_store.database_path.open("r+b") as destination:
        destination.seek(0)
        destination.write(replacement_bytes)
        destination.truncate()
        destination.flush()
        os.fsync(destination.fileno())
    with pytest.raises(FactExtractionFailureV2) as captured:
        pinned_store.verify_chain()
    assert captured.value.code is FactExtractionFailureCodeV2.TAMPER_DETECTED


def test_symlinked_root_is_rejected(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(target, target_is_directory=True)
    with pytest.raises(FactExtractionFailureV2) as captured:
        OwnerPrivateSqliteFactExtractionStoreV2(
            environment=RuntimeEnvironment.CI,
            root=linked,
        )
    assert captured.value.code is FactExtractionFailureCodeV2.UNSAFE_PATH


def test_database_never_contains_provider_text_or_raw_urls(tmp_path) -> None:
    dependencies = exact_dependencies_v2(tmp_path)
    store = fact_store_v2(tmp_path)
    _extract(dependencies, store)
    material = store.database_path.read_bytes()
    assert b"https://" not in material
    assert b"affiliate.example" not in material
    assert b"Unicode" not in material
    assert b"Synthetic shop" not in material
