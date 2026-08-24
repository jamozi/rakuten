"""Application service for explicit ST-1505 local admission runs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from raos.domain.ops.staging_admission import (
    LocalStagingAdmissionSpec,
    StagingAdmissionError,
    canonical_bytes,
    canonical_sha256,
    evaluate_local_admission,
)
from raos.ports.deployment_identity import (
    DeploymentIdentityActivationCommand,
    DeploymentIdentityActivationPort,
    DeploymentIdentityActivationReceipt,
)
from raos.ports.staging_admission import (
    AdmissionPersistCommand,
    AdmissionPersistReceipt,
    StagingAdmissionJournalError,
    StagingAdmissionJournalFailureCode,
    StagingAdmissionJournalPort,
)


_RUN_ID = re.compile(r"^st1505-run-[a-z0-9][a-z0-9.-]{2,95}$")
_IDEMPOTENCY_KEY = re.compile(r"^st1505-key-[a-z0-9][a-z0-9.-]{2,95}$")


@dataclass(frozen=True, slots=True)
class LocalStagingAdmissionRun:
    """Explicit local invocation with a non-secret replay key."""

    run_id: str
    idempotency_key: str

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or type(self.idempotency_key) is not str
            or _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key) is None
        ):
            raise StagingAdmissionError("RUN_INPUT_INVALID", "run")


@dataclass(frozen=True, slots=True)
class LocalStagingAdmissionRunReceipt:
    """Deterministic result plus its owner-private persistence receipt."""

    result_document: dict[str, object]
    persistence: AdmissionPersistReceipt
    recovered_after_commit_ambiguity: bool

    def __post_init__(self) -> None:
        if type(self.result_document) is not dict:
            raise StagingAdmissionError("RUN_RECEIPT_INVALID", "result")
        if type(self.persistence) is not AdmissionPersistReceipt:
            raise StagingAdmissionError("RUN_RECEIPT_INVALID", "persistence")
        if type(self.recovered_after_commit_ambiguity) is not bool:
            raise StagingAdmissionError("RUN_RECEIPT_INVALID", "recovered")


class LocalStagingAdmissionService:
    """Coordinate only disabled identity, pure evaluation, and local journaling."""

    __slots__ = ("_activation", "_journal", "_spec")

    def __init__(
        self,
        *,
        spec: LocalStagingAdmissionSpec,
        activation: DeploymentIdentityActivationPort,
        journal: StagingAdmissionJournalPort,
    ) -> None:
        if type(spec) is not LocalStagingAdmissionSpec:
            raise StagingAdmissionError("SERVICE_INPUT_INVALID", "spec")
        self._spec = spec
        self._activation = activation
        self._journal = journal

    def execute(
        self, request: LocalStagingAdmissionRun
    ) -> LocalStagingAdmissionRunReceipt:
        if type(request) is not LocalStagingAdmissionRun:
            raise StagingAdmissionError("RUN_INPUT_INVALID", "run")
        identity_command = DeploymentIdentityActivationCommand(
            policy_id=self._spec.identity_policy_id,
            fixture_id=self._spec.identity_fixture_id,
            evaluation_digest=self._spec.identity_evaluation_digest,
            enable_requested=False,
            requested_action_count=0,
            credential_material=None,
        )
        identity_receipt = self._activate_closed(identity_command)
        if (
            identity_receipt.policy_id != identity_command.policy_id
            or identity_receipt.fixture_id != identity_command.fixture_id
            or identity_receipt.reason_code != "LOCAL_ACTIVATION_DISABLED"
        ):
            raise StagingAdmissionError("IDENTITY_RECEIPT_MISMATCH", "identity")
        evaluation = evaluate_local_admission(
            self._spec,
            identity_activation_status=identity_receipt.status,
            identity_activation_allowed=identity_receipt.activation_allowed,
            identity_credentials_issued=identity_receipt.credentials_issued,
            identity_actions_executed=identity_receipt.actions_executed,
        )
        result_document = evaluation.to_document()
        result_json = canonical_bytes(result_document)
        idempotency_key_sha256 = hashlib.sha256(
            request.idempotency_key.encode("ascii")
        ).hexdigest()
        request_sha256 = canonical_sha256(
            {
                "schema": "RAOS_LOCAL_STAGING_ADMISSION_REQUEST_V2",
                "run_id": request.run_id,
                "idempotency_key_sha256": idempotency_key_sha256,
                "contract_sha256": self._spec.semantic_sha256,
                "pipeline_id": self._spec.pipeline_id,
            }
        )
        command = AdmissionPersistCommand(
            run_id=request.run_id,
            idempotency_key_sha256=idempotency_key_sha256,
            request_sha256=request_sha256,
            contract_sha256=self._spec.semantic_sha256,
            result_sha256=evaluation.result_sha256,
            result_json=result_json,
        )
        recovered = False
        try:
            persistence = self._commit_closed(command)
        except StagingAdmissionJournalError as error:
            if error.code is not StagingAdmissionJournalFailureCode.COMMIT_AMBIGUOUS:
                raise
            persistence = self._recover_closed(command)
            recovered = True
        self._validate_persistence(command, persistence)
        return LocalStagingAdmissionRunReceipt(
            result_document=result_document,
            persistence=persistence,
            recovered_after_commit_ambiguity=recovered,
        )

    def _activate_closed(
        self, command: DeploymentIdentityActivationCommand
    ) -> DeploymentIdentityActivationReceipt:
        try:
            observed = self._activation.activate(command)
        except Exception:
            raise StagingAdmissionError("IDENTITY_ACTIVATION_FAILED", "identity")
        if type(observed) is not DeploymentIdentityActivationReceipt:
            raise StagingAdmissionError("IDENTITY_RECEIPT_INVALID", "identity")
        try:
            closed_receipt = DeploymentIdentityActivationReceipt(
                policy_id=observed.policy_id,
                fixture_id=observed.fixture_id,
                status=observed.status,
                activation_allowed=observed.activation_allowed,
                credentials_issued=observed.credentials_issued,
                actions_executed=observed.actions_executed,
                reason_code=observed.reason_code,
            )
        except Exception:
            raise StagingAdmissionError(
                "IDENTITY_RECEIPT_INVALID", "identity"
            ) from None
        return closed_receipt

    def _commit_closed(
        self, command: AdmissionPersistCommand
    ) -> AdmissionPersistReceipt:
        observed: object | None = None
        closed_failure: StagingAdmissionJournalError | None = None
        unexpected_failure = False
        try:
            observed = self._journal.commit(command)
        except StagingAdmissionJournalError as error:
            if self._is_closed_journal_error(error):
                closed_failure = error
            else:
                unexpected_failure = True
        except Exception:
            unexpected_failure = True
        if unexpected_failure:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.STORAGE_FAILURE
            )
        if closed_failure is not None:
            raise closed_failure
        return self._copy_persistence_receipt(observed)

    def _recover_closed(
        self, command: AdmissionPersistCommand
    ) -> AdmissionPersistReceipt:
        observed: object | None = None
        closed_failure: StagingAdmissionJournalError | None = None
        unexpected_failure = False
        try:
            observed = self._journal.recover_exact(command)
        except StagingAdmissionJournalError as error:
            if self._is_closed_journal_error(error):
                closed_failure = error
            else:
                unexpected_failure = True
        except Exception:
            unexpected_failure = True
        if unexpected_failure:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.STORAGE_FAILURE
            )
        if closed_failure is not None:
            raise closed_failure
        return self._copy_persistence_receipt(observed)

    @staticmethod
    def _is_closed_journal_error(error: object) -> bool:
        if type(error) is not StagingAdmissionJournalError:
            return False
        try:
            code = error.code
            arguments = error.args
            return (
                type(code) is StagingAdmissionJournalFailureCode
                and type(arguments) is tuple
                and len(arguments) == 1
                and type(arguments[0]) is str
                and arguments[0] == code.value
            )
        except Exception:
            return False

    @staticmethod
    def _copy_persistence_receipt(observed: object) -> AdmissionPersistReceipt:
        if type(observed) is not AdmissionPersistReceipt:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.TAMPER_DETECTED
            )
        try:
            return AdmissionPersistReceipt(
                run_id=observed.run_id,
                idempotency_key_sha256=observed.idempotency_key_sha256,
                request_sha256=observed.request_sha256,
                result_sha256=observed.result_sha256,
                sequence=observed.sequence,
                previous_entry_sha256=observed.previous_entry_sha256,
                entry_sha256=observed.entry_sha256,
                replayed=observed.replayed,
            )
        except Exception:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.TAMPER_DETECTED
            ) from None

    @staticmethod
    def _validate_persistence(
        command: AdmissionPersistCommand, receipt: AdmissionPersistReceipt
    ) -> None:
        if type(receipt) is not AdmissionPersistReceipt or (
            receipt.run_id != command.run_id
            or receipt.idempotency_key_sha256 != command.idempotency_key_sha256
            or receipt.request_sha256 != command.request_sha256
            or receipt.result_sha256 != command.result_sha256
        ):
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.TAMPER_DETECTED
            )


__all__ = [
    "LocalStagingAdmissionRun",
    "LocalStagingAdmissionRunReceipt",
    "LocalStagingAdmissionService",
]
