"""Durable recorded-local ST-1201 V2 behavior and restart evidence."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
import os
from pathlib import Path
import sqlite3

import pytest

from .support import consent, envelope, http_policy, http_request, recorded_policy
from raos.adapters.sqlite_event_collector_runtime_v2 import (
    EventStoreCommitFault,
    SqliteDurableRecordedEventStoreV2,
)
from raos.application.analytics.event_collector_runtime_v2 import (
    DurableRecordedFirstPartyEventCollectorV2,
)
from raos.domain.analytics.event_collector import (
    ConsentState,
    EventCollectorFailure,
    EventCollectorFailureCode,
    EventParameter,
    RecordedStoreDisposition,
)
from raos.domain.analytics.event_collector_runtime_v2 import (
    DurableEventCollectionResultV2,
    DurableEventStoreFailure,
    DurableEventStoreFailureCode,
)


_DATABASE_NAME = "st1201-recorded-event-store.sqlite3"


@pytest.fixture
def private_root(tmp_path: Path) -> Path:
    root = tmp_path / "private-event-store"
    root.mkdir(mode=0o700)
    os.chmod(root, 0o700)
    return root


def _service(
    root: Path, *, fault: EventStoreCommitFault = EventStoreCommitFault.NONE
) -> DurableRecordedFirstPartyEventCollectorV2:
    return DurableRecordedFirstPartyEventCollectorV2(
        http_policy=http_policy(),
        collection_policy=recorded_policy(),
        store=SqliteDurableRecordedEventStoreV2(
            private_root=root,
            commit_fault_once=fault,
        ),
    )


def _collect(
    service: DurableRecordedFirstPartyEventCollectorV2,
) -> DurableEventCollectionResultV2:
    return service.collect(
        request=http_request(), envelope=envelope(), consent=consent()
    )


def test_first_commit_is_durable_but_tracking_and_measurement_stay_disabled(
    private_root: Path,
) -> None:
    service = _service(private_root)
    result = _collect(service)

    assert result.receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert result.receipt.replayed is False
    assert result.receipt.sequence == 1
    assert result.persistence == "DURABLE_RECORDED_LOCAL"
    assert result.tracking_activation.value == "DISABLED"
    assert result.measurement_observed is False
    assert result.decision.value == "NOT_READY"
    assert service.action_count == 0

    database = private_root / _DATABASE_NAME
    assert database.stat().st_mode & 0o777 == 0o600
    connection = sqlite3.connect(database)
    try:
        count = connection.execute("SELECT count(*) FROM st1201_event_v2").fetchone()
        payload = connection.execute(
            "SELECT canonical_event FROM st1201_event_v2"
        ).fetchone()
    finally:
        connection.close()
    assert count == (1,)
    assert payload == (envelope_event_bytes(),)


def envelope_event_bytes() -> bytes:
    from raos.domain.analytics.event_collector import ValidatedEvent

    return ValidatedEvent(envelope=envelope(), consent=consent()).canonical_bytes()


def test_restart_exact_replay_is_one_duplicate_without_second_row(
    private_root: Path,
) -> None:
    first = _collect(_service(private_root))
    second = _collect(_service(private_root))

    assert first.receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert second.receipt.disposition is RecordedStoreDisposition.RECORDED_DUPLICATE
    assert second.receipt.replayed is True
    assert second.receipt.sequence == first.receipt.sequence
    assert second.receipt.record_sha256 == first.receipt.record_sha256

    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        assert connection.execute(
            "SELECT count(*) FROM st1201_event_v2"
        ).fetchone() == (1,)
    finally:
        connection.close()


def test_same_event_id_with_changed_payload_is_conflict(private_root: Path) -> None:
    service = _service(private_root)
    _collect(service)
    changed = replace(
        envelope(),
        parameters=tuple(
            EventParameter(parameter.name, "article_bottom")
            if parameter.name == "placement"
            else parameter
            for parameter in envelope().parameters
        ),
    )
    with pytest.raises(EventCollectorFailure) as caught:
        service.collect(request=http_request(), envelope=changed, consent=consent())
    assert caught.value.code is EventCollectorFailureCode.EVENT_ID_CONFLICT


def test_after_commit_ambiguity_recovers_exact_accepted_receipt(
    private_root: Path,
) -> None:
    result = _collect(_service(private_root, fault=EventStoreCommitFault.AFTER_COMMIT))
    assert result.receipt.disposition is RecordedStoreDisposition.RECORDED_ACCEPTED
    assert result.receipt.replayed is False
    assert _collect(_service(private_root)).receipt.replayed is True


def test_before_commit_fault_rolls_back_and_safe_retry_accepts(
    private_root: Path,
) -> None:
    with pytest.raises(EventCollectorFailure) as caught:
        _collect(_service(private_root, fault=EventStoreCommitFault.BEFORE_COMMIT))
    assert caught.value.code is EventCollectorFailureCode.RECORDED_STORE_EXHAUSTED
    assert _collect(_service(private_root)).receipt.replayed is False


def test_concurrent_same_event_has_one_accept_and_only_duplicates(
    private_root: Path,
) -> None:
    service = _service(private_root)
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = tuple(pool.submit(_collect, service) for _ in range(16))
        results = tuple(future.result() for future in futures)
    dispositions = tuple(result.receipt.disposition for result in results)
    assert dispositions.count(RecordedStoreDisposition.RECORDED_ACCEPTED) == 1
    assert dispositions.count(RecordedStoreDisposition.RECORDED_DUPLICATE) == 15


def test_tamper_and_schema_drift_fail_closed_on_restart(private_root: Path) -> None:
    _collect(_service(private_root))
    database = private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        connection.execute("DROP TRIGGER st1201_event_no_update_v2")
        connection.execute(
            "UPDATE st1201_event_v2 SET payload_sha256=?",
            ("f" * 64,),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=private_root)
    assert caught.value.code in {
        DurableEventStoreFailureCode.SCHEMA_DRIFT,
        DurableEventStoreFailureCode.TAMPER_DETECTED,
    }


def test_row_hash_tamper_fails_closed_with_exact_schema(private_root: Path) -> None:
    _collect(_service(private_root))
    database = private_root / _DATABASE_NAME
    connection = sqlite3.connect(database)
    try:
        trigger = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name='st1201_event_no_update_v2'"
        ).fetchone()
        assert trigger is not None and type(trigger[0]) is str
        connection.execute("DROP TRIGGER st1201_event_no_update_v2")
        connection.execute(
            "UPDATE st1201_event_v2 SET canonical_event=?", (b"tampered",)
        )
        connection.execute(trigger[0])
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=private_root)
    assert caught.value.code is DurableEventStoreFailureCode.TAMPER_DETECTED


def test_extra_schema_object_fails_closed(private_root: Path) -> None:
    _collect(_service(private_root))
    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        connection.execute("CREATE TABLE attacker(value TEXT) STRICT")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=private_root)
    assert caught.value.code is DurableEventStoreFailureCode.SCHEMA_DRIFT


@pytest.mark.parametrize("mode", [0o755, 0o777])
def test_non_private_root_is_rejected(tmp_path: Path, mode: int) -> None:
    root = tmp_path / "not-private"
    root.mkdir(mode=mode)
    os.chmod(root, mode)
    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=root)
    assert caught.value.code is DurableEventStoreFailureCode.PRIVATE_PATH_INVALID


def test_symlink_and_hardlinked_database_are_rejected(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    os.chmod(target, 0o700)
    symlink = tmp_path / "link"
    symlink.symlink_to(target, target_is_directory=True)
    with pytest.raises(DurableEventStoreFailure):
        SqliteDurableRecordedEventStoreV2(private_root=symlink)

    _collect(_service(target))
    os.link(target / _DATABASE_NAME, tmp_path / "second-link.sqlite3")
    with pytest.raises(DurableEventStoreFailure) as caught:
        SqliteDurableRecordedEventStoreV2(private_root=target)
    assert caught.value.code is DurableEventStoreFailureCode.PRIVATE_PATH_INVALID


def test_exception_traceback_is_assignable_through_contextmanager() -> None:
    failure = EventCollectorFailure(EventCollectorFailureCode.MALFORMED_EVENT)
    failure.__traceback__ = None

    @contextmanager
    def reraising():
        try:
            yield
        except EventCollectorFailure:
            raise

    with pytest.raises(EventCollectorFailure):
        with reraising():
            raise failure


def test_denied_consent_writes_zero_event_rows(private_root: Path) -> None:
    service = _service(private_root)
    with pytest.raises(EventCollectorFailure) as caught:
        service.collect(
            request=http_request(),
            envelope=envelope(),
            consent=consent(state=ConsentState.DENIED),
        )
    assert caught.value.code is EventCollectorFailureCode.CONSENT_DENIED
    connection = sqlite3.connect(private_root / _DATABASE_NAME)
    try:
        assert connection.execute(
            "SELECT count(*) FROM st1201_event_v2"
        ).fetchone() == (0,)
    finally:
        connection.close()


def test_public_store_surface_has_no_read_export_or_lifecycle_methods() -> None:
    public = set(dir(SqliteDurableRecordedEventStoreV2))
    assert {
        "delete",
        "export",
        "get",
        "list",
        "purge",
        "query",
        "read",
        "restore",
        "retention",
    }.isdisjoint(public)
