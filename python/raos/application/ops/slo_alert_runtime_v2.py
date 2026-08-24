"""One-step ST-1602 SLO and alert orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import final

from raos.domain.ops.slo_alert_runtime_v2 import (
    AlertDecision,
    AlertObservation,
    AlertPersistCommand,
    AlertPersistReceipt,
    AlertRule,
    AlertSnapshot,
    RuntimeCatalog,
    SloAlertFailure,
    SloAlertFailureCode,
    SloEvaluation,
    SloMetricWindow,
    alert_instance_key,
    canonical_sha256,
    evaluate_alert,
    evaluate_slo,
    fail,
    make_persist_command,
    validate_receipt,
)
from raos.ports.slo_alert_runtime_v2 import (
    AlertStateJournal,
    LocalAlertNotificationPort,
    LocalNotificationOutcome,
    LocalNotificationRecord,
    NotificationMode,
)


@dataclass(frozen=True, slots=True)
class AlertStepResult:
    decision: AlertDecision
    receipt: AlertPersistReceipt
    notification_outcome: LocalNotificationOutcome
    notification_delivery_claim: bool = False
    external_action_count: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.decision) is not AlertDecision
            or type(self.receipt) is not AlertPersistReceipt
            or type(self.notification_outcome) is not LocalNotificationOutcome
            or type(self.notification_delivery_claim) is not bool
            or self.notification_delivery_claim
            or type(self.external_action_count) is not int
            or self.external_action_count != 0
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.result")


def _snapshot(
    value: object, *, instance_key: str, rule: AlertRule
) -> AlertSnapshot | None:
    if value is None:
        return None
    if type(value) is not AlertSnapshot:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.snapshot")
    snapshot = value
    if (
        snapshot.instance_key != instance_key
        or snapshot.alert_id != rule.alert_id
        or snapshot.rule_fingerprint != rule.dedup_fingerprint
    ):
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.snapshot")
    return snapshot


def _command_binding(command: object) -> tuple[object, ...]:
    if type(command) is not AlertPersistCommand:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
    source = command
    try:
        validated = AlertPersistCommand(
            instance_key=source.instance_key,
            alert_id=source.alert_id,
            rule_fingerprint=source.rule_fingerprint,
            idempotency_key_sha256=source.idempotency_key_sha256,
            request_sha256=source.request_sha256,
            expected_version=source.expected_version,
            current_version=source.current_version,
            decision=source.decision,
            result_sha256=source.result_sha256,
            result_json=source.result_json,
        )
    except Exception:
        fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
    return (
        validated.instance_key,
        validated.alert_id,
        validated.rule_fingerprint,
        validated.idempotency_key_sha256,
        validated.request_sha256,
        validated.expected_version,
        validated.current_version,
        validated.result_sha256,
        validated.result_json,
    )


def _notification_binding(record: object) -> tuple[object, ...]:
    if type(record) is not LocalNotificationRecord:
        fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.record")
    source = record
    try:
        validated = LocalNotificationRecord(
            notification_fingerprint=source.notification_fingerprint,
            dedup_fingerprint=source.dedup_fingerprint,
            instance_key=source.instance_key,
            alert_id=source.alert_id,
            severity=source.severity,
            owner_id=source.owner_id,
            runbook_id=source.runbook_id,
            state=source.state,
            outcome=source.outcome,
            result_sha256=source.result_sha256,
            external_action_count=source.external_action_count,
            delivery_claim=source.delivery_claim,
        )
    except Exception:
        fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.record")
    return (
        validated.notification_fingerprint,
        validated.dedup_fingerprint,
        validated.instance_key,
        validated.alert_id,
        validated.severity,
        validated.owner_id,
        validated.runbook_id,
        validated.state,
        validated.outcome,
        validated.result_sha256,
        validated.external_action_count,
        validated.delivery_claim,
    )


@final
class SloAlertRuntimeService:
    """Evaluate exactly one caller-requested step with no autonomous loop."""

    __slots__ = ("_catalog", "_journal", "_notification")

    def __init__(
        self,
        *,
        catalog: RuntimeCatalog,
        journal: AlertStateJournal,
        notification: LocalAlertNotificationPort,
    ) -> None:
        if type(catalog) is not RuntimeCatalog:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "service.catalog")
        self._catalog = catalog
        self._journal = journal
        self._notification = notification
        self._validate_notification_boundary()

    @property
    def external_action_count(self) -> int:
        self._validate_notification_boundary()
        return 0

    def _validate_notification_boundary(self) -> None:
        try:
            mode = self._notification.mode
            count = self._notification.external_action_count
        except SloAlertFailure as error:
            if type(error) is SloAlertFailure:
                raise
            fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification")
        except Exception:
            fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification")
        if (
            type(mode) is not NotificationMode
            or mode is not NotificationMode.LOCAL_LOG_ONLY_DISABLED
        ):
            fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.mode")
        if type(count) is not int or count != 0:
            fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.actions")

    def evaluate_slo_window(self, window: SloMetricWindow) -> SloEvaluation:
        if type(window) is not SloMetricWindow:
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "slo.window")
        return evaluate_slo(self._catalog.slo(window.slo_id), window)

    def evaluate_alert_step(
        self,
        *,
        instance_id: str,
        expected_version: int,
        observation: AlertObservation,
    ) -> AlertStepResult:
        if (
            type(observation) is not AlertObservation
            or type(expected_version) is not int
            or expected_version < 0
        ):
            fail(SloAlertFailureCode.INVALID_ARGUMENT, "alert.request")
        rule = self._catalog.alert(observation.alert_id)
        instance_key = alert_instance_key(rule.alert_id, instance_id)
        self._validate_notification_boundary()
        try:
            raw_prior = self._journal.load_latest(instance_key)
        except SloAlertFailure as error:
            if type(error) is SloAlertFailure:
                raise
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.load")
        except Exception:
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.load")
        prior = _snapshot(raw_prior, instance_key=instance_key, rule=rule)
        observed_version = 0 if prior is None else prior.current_version
        if observed_version != expected_version:
            fail(SloAlertFailureCode.CONCURRENCY_CONFLICT, "journal.version")
        decision = evaluate_alert(rule, instance_key, observation, prior)
        command = make_persist_command(
            rule=rule,
            instance_key=instance_key,
            observation=observation,
            expected_version=expected_version,
            decision=decision,
        )
        command_binding = _command_binding(command)
        try:
            receipt = self._journal.commit(command)
        except SloAlertFailure as error:
            if _command_binding(command) != command_binding:
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
            if type(error) is not SloAlertFailure:
                fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.commit")
            if error.code is not SloAlertFailureCode.COMMIT_AMBIGUOUS:
                raise
            try:
                receipt = self._journal.recover_exact(command)
            except SloAlertFailure as recovery_error:
                if _command_binding(command) != command_binding:
                    fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
                if type(recovery_error) is SloAlertFailure:
                    raise
                fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.recover")
            except Exception:
                if _command_binding(command) != command_binding:
                    fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
                fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.recover")
        except Exception:
            if _command_binding(command) != command_binding:
                fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
            fail(SloAlertFailureCode.JOURNAL_UNAVAILABLE, "journal.commit")
        if _command_binding(command) != command_binding:
            fail(SloAlertFailureCode.JOURNAL_TAMPERED, "journal.command")
        validate_receipt(receipt, command)
        notification_record = LocalNotificationRecord(
            notification_fingerprint=canonical_sha256(
                {
                    "request_sha256": receipt.request_sha256,
                    "result_sha256": receipt.result_sha256,
                    "dedup_fingerprint": decision.dedup_fingerprint,
                    "state": decision.state.value,
                    "owner_id": decision.owner_id,
                    "runbook_id": decision.runbook_id,
                }
            ),
            dedup_fingerprint=decision.dedup_fingerprint,
            instance_key=decision.instance_key,
            alert_id=decision.alert_id,
            severity=decision.severity.value,
            owner_id=decision.owner_id,
            runbook_id=decision.runbook_id,
            state=decision.state,
            outcome=decision.outcome,
            result_sha256=receipt.result_sha256,
        )
        notification_binding = _notification_binding(notification_record)
        try:
            notification_outcome = self._notification.record_local(notification_record)
        except SloAlertFailure:
            notification_outcome = LocalNotificationOutcome.LOCAL_LOG_FAILED
        except Exception:
            notification_outcome = LocalNotificationOutcome.LOCAL_LOG_FAILED
        if type(notification_outcome) is not LocalNotificationOutcome:
            notification_outcome = LocalNotificationOutcome.LOCAL_LOG_FAILED
        if _notification_binding(notification_record) != notification_binding:
            fail(SloAlertFailureCode.NOTIFICATION_UNAVAILABLE, "notification.record")
        self._validate_notification_boundary()
        return AlertStepResult(
            decision=decision,
            receipt=receipt,
            notification_outcome=notification_outcome,
        )


__all__ = ["AlertStepResult", "SloAlertRuntimeService"]
