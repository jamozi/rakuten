"""Hostile collaborator and closed-failure tests for ST-1602 V2."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import traceback
from collections.abc import Callable
from typing import cast

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_slo_alert_runtime_v2 import (  # noqa: E402
    DisabledRecordedAlertNotificationAdapter,
)
from raos.application.ops.slo_alert_runtime_v2 import (  # noqa: E402
    SloAlertRuntimeService,
)
from raos.domain.ops.slo_alert_runtime_v2 import (  # noqa: E402
    AlertConditionState,
    AlertLifecycleState,
    AlertObservation,
    AlertPersistCommand,
    AlertPersistReceipt,
    AlertSnapshot,
    HoldVariant,
    RuntimeCatalog,
    SloAlertFailure,
    SloAlertFailureCode,
    compile_runtime_catalog,
)
from raos.ports.slo_alert_runtime_v2 import (  # noqa: E402
    AlertStateJournal,
    LocalAlertNotificationPort,
    LocalNotificationOutcome,
    LocalNotificationRecord,
    NotificationMode,
)
from scripts import build_st1602_slo_alert_runtime as generator  # noqa: E402


CANARY = "secret-canary-hostile-collaborator"


def _observation() -> AlertObservation:
    return AlertObservation(
        alert_id="ALT-001",
        source="SYNTHETIC_RECORDED_FIXTURE_ONLY",
        observed_at_epoch_seconds=100,
        evaluated_at_epoch_seconds=100,
        fresh_until_epoch_seconds=200,
        sample_count=1,
        mature=True,
        condition_state=AlertConditionState.BREACH,
        hold_variant=HoldVariant.DEFAULT,
        condition_started_at_epoch_seconds=100,
        cycle_complete=False,
        observation_sha256="a" * 64,
    )


class _HostileJournal:
    def __init__(self, method: str) -> None:
        self.method = method
        self.commit_calls = 0

    def load_latest(self, instance_key: str) -> AlertSnapshot | None:
        del instance_key
        if self.method == "load":
            raise RuntimeError(CANARY)
        return None

    def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        self.commit_calls += 1
        if self.method == "commit":
            raise RuntimeError(CANARY)
        if self.method == "forged_receipt":
            return AlertPersistReceipt(
                command.instance_key,
                command.current_version,
                "f" * 64,
                command.result_sha256,
                1,
                "0" * 64,
                "1" * 64,
                False,
            )
        raise SloAlertFailure(SloAlertFailureCode.COMMIT_AMBIGUOUS, "journal.commit")

    def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
        del command
        raise RuntimeError(CANARY)


class _HostileNotification:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior
        self.record_calls = 0

    @property
    def mode(self) -> NotificationMode:
        if self.behavior == "mode":
            raise RuntimeError(CANARY)
        return NotificationMode.LOCAL_LOG_ONLY_DISABLED

    @property
    def external_action_count(self) -> int:
        if self.behavior == "count":
            raise RuntimeError(CANARY)
        return 0

    def record_local(self, record: LocalNotificationRecord) -> object:
        del record
        self.record_calls += 1
        if self.behavior == "record":
            raise RuntimeError(CANARY)
        if self.behavior == "wrong_result":
            return CANARY
        return LocalNotificationOutcome.RECORDED_LOCAL_ONLY


def _catalog() -> RuntimeCatalog:
    return compile_runtime_catalog(generator.runtime_catalog())


def _assert_closed(
    operation: Callable[[], object], expected: SloAlertFailureCode
) -> None:
    try:
        operation()
    except SloAlertFailure as error:
        assert type(error) is SloAlertFailure
        assert error.code is expected
        rendered = "".join(traceback.format_exception(error))
        assert CANARY not in str(error)
        assert CANARY not in repr(error)
        assert CANARY not in rendered
    else:
        raise AssertionError("operation did not fail")


@pytest.mark.parametrize("method", ["load", "commit", "recover"])
def test_arbitrary_journal_exceptions_are_sanitized(method: str) -> None:
    journal = _HostileJournal(method)
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=journal,
        notification=DisabledRecordedAlertNotificationAdapter(capacity=2),
    )
    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=0,
            observation=_observation(),
        ),
        SloAlertFailureCode.JOURNAL_UNAVAILABLE,
    )
    if method == "load":
        assert journal.commit_calls == 0


@pytest.mark.parametrize("behavior", ["mode", "count"])
def test_notification_property_exceptions_block_before_journal_action(
    behavior: str,
) -> None:
    journal = _HostileJournal("commit")
    notification = _HostileNotification(behavior)
    _assert_closed(
        lambda: SloAlertRuntimeService(
            catalog=_catalog(),
            journal=journal,
            notification=cast(LocalAlertNotificationPort, notification),
        ),
        SloAlertFailureCode.NOTIFICATION_UNAVAILABLE,
    )
    assert journal.commit_calls == 0
    assert notification.record_calls == 0


def test_forged_exact_receipt_is_rejected_without_notification() -> None:
    journal = _HostileJournal("forged_receipt")
    notification = _HostileNotification("normal")
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=journal,
        notification=cast(LocalAlertNotificationPort, notification),
    )

    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=0,
            observation=_observation(),
        ),
        SloAlertFailureCode.JOURNAL_TAMPERED,
    )
    assert notification.record_calls == 0


def test_journal_cannot_mutate_command_hash_and_return_matching_receipt() -> None:
    class _MutatingJournal(_HostileJournal):
        def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            from raos.domain.ops.slo_alert_runtime_v2 import entry_sha256

            self.commit_calls += 1
            object.__setattr__(command, "request_sha256", "b" * 64)
            return AlertPersistReceipt(
                command.instance_key,
                command.current_version,
                command.request_sha256,
                command.result_sha256,
                1,
                "0" * 64,
                entry_sha256(
                    sequence=1,
                    previous_entry_sha256="0" * 64,
                    command=command,
                ),
                False,
            )

    journal = _MutatingJournal("normal")
    notification = _HostileNotification("normal")
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=journal,
        notification=cast(LocalAlertNotificationPort, notification),
    )

    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=0,
            observation=_observation(),
        ),
        SloAlertFailureCode.JOURNAL_TAMPERED,
    )
    assert journal.commit_calls == 1
    assert notification.record_calls == 0


def test_forged_exact_snapshot_route_binding_is_rejected_before_commit() -> None:
    rule = _catalog().alert("ALT-001")
    key = "ALT-001:public-route"
    forged = AlertSnapshot(
        key,
        "ALT-001",
        "f" * 64,
        1,
        AlertLifecycleState.FIRING,
        None,
        "1" * 64,
        1,
        "2" * 64,
    )

    class _ForgedSnapshotJournal(_HostileJournal):
        def load_latest(self, instance_key: str) -> AlertSnapshot | None:
            del instance_key
            return forged

    journal = _ForgedSnapshotJournal("commit")
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=journal,
        notification=DisabledRecordedAlertNotificationAdapter(capacity=2),
    )
    assert forged.rule_fingerprint != rule.dedup_fingerprint

    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=1,
            observation=_observation(),
        ),
        SloAlertFailureCode.JOURNAL_TAMPERED,
    )
    assert journal.commit_calls == 0


@pytest.mark.parametrize("behavior", ["record", "wrong_result"])
def test_notification_call_failure_is_closed_local_failure_not_delivery(
    behavior: str,
) -> None:
    # Use a minimal journal that returns a valid receipt constructed from the command.
    class _Journal:
        def load_latest(self, instance_key: str) -> AlertSnapshot | None:
            del instance_key
            return None

        def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            from raos.domain.ops.slo_alert_runtime_v2 import entry_sha256

            return AlertPersistReceipt(
                command.instance_key,
                1,
                command.request_sha256,
                command.result_sha256,
                1,
                "0" * 64,
                entry_sha256(
                    sequence=1,
                    previous_entry_sha256="0" * 64,
                    command=command,
                ),
                False,
            )

        def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            del command
            raise AssertionError("not expected")

    notification = _HostileNotification(behavior)
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=cast(AlertStateJournal, _Journal()),
        notification=cast(LocalAlertNotificationPort, notification),
    )
    result = service.evaluate_alert_step(
        instance_id="public-route",
        expected_version=0,
        observation=_observation(),
    )

    assert result.notification_outcome is LocalNotificationOutcome.LOCAL_LOG_FAILED
    assert result.notification_delivery_claim is False
    assert result.external_action_count == 0
    assert notification.external_action_count == 0


def test_notification_cannot_mutate_record_hash_or_action_count() -> None:
    class _Journal:
        def load_latest(self, instance_key: str) -> AlertSnapshot | None:
            del instance_key
            return None

        def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            from raos.domain.ops.slo_alert_runtime_v2 import entry_sha256

            return AlertPersistReceipt(
                command.instance_key,
                1,
                command.request_sha256,
                command.result_sha256,
                1,
                "0" * 64,
                entry_sha256(
                    sequence=1,
                    previous_entry_sha256="0" * 64,
                    command=command,
                ),
                False,
            )

        def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            del command
            raise AssertionError("not expected")

    class _MutatingNotification(_HostileNotification):
        def record_local(self, record: LocalNotificationRecord) -> object:
            self.record_calls += 1
            object.__setattr__(record, "result_sha256", "b" * 64)
            object.__setattr__(record, "external_action_count", 1)
            return LocalNotificationOutcome.RECORDED_LOCAL_ONLY

    notification = _MutatingNotification("normal")
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=cast(AlertStateJournal, _Journal()),
        notification=cast(LocalAlertNotificationPort, notification),
    )

    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=0,
            observation=_observation(),
        ),
        SloAlertFailureCode.NOTIFICATION_UNAVAILABLE,
    )
    assert notification.record_calls == 1


def test_notification_action_count_is_rechecked_after_local_record() -> None:
    class _Journal:
        def load_latest(self, instance_key: str) -> AlertSnapshot | None:
            del instance_key
            return None

        def commit(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            from raos.domain.ops.slo_alert_runtime_v2 import entry_sha256

            return AlertPersistReceipt(
                command.instance_key,
                1,
                command.request_sha256,
                command.result_sha256,
                1,
                "0" * 64,
                entry_sha256(
                    sequence=1,
                    previous_entry_sha256="0" * 64,
                    command=command,
                ),
                False,
            )

        def recover_exact(self, command: AlertPersistCommand) -> AlertPersistReceipt:
            del command
            raise AssertionError("not expected")

    class _DriftingNotification(_HostileNotification):
        def __init__(self) -> None:
            super().__init__("normal")
            self.count_reads = 0

        @property
        def external_action_count(self) -> int:
            self.count_reads += 1
            return 0 if self.count_reads <= 2 else 1

    notification = _DriftingNotification()
    service = SloAlertRuntimeService(
        catalog=_catalog(),
        journal=cast(AlertStateJournal, _Journal()),
        notification=cast(LocalAlertNotificationPort, notification),
    )

    _assert_closed(
        lambda: service.evaluate_alert_step(
            instance_id="public-route",
            expected_version=0,
            observation=_observation(),
        ),
        SloAlertFailureCode.NOTIFICATION_UNAVAILABLE,
    )
    assert notification.record_calls == 1
    assert notification.count_reads == 3


def test_untrusted_condition_or_provider_text_has_no_runtime_field_or_ranking_input() -> (
    None
):
    observation = _observation()
    assert CANARY not in repr(observation)
    assert not hasattr(observation, "condition_text")
    assert not hasattr(observation, "provider_text")
    assert not hasattr(observation, "profit")
    assert not hasattr(observation, "recommendation_rank")
    with pytest.raises(SloAlertFailure):
        replace(observation, observation_sha256=CANARY)
