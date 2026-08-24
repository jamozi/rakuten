"""Application service for explicit one-step ST-1506 local simulations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from raos.domain.ops.production_canary import (
    CanaryCommandKind,
    CanarySession,
    CanaryState,
    EXTERNAL_ACTION_NAMES,
    ProductionCanaryError,
    ProductionCanarySpec,
    SyntheticObservation,
    advance_once,
    canonical_bytes,
    canonical_sha256,
)
from raos.ports.production_canary import (
    CanaryStepPersistCommand,
    CanaryStepPersistReceipt,
    PersistedCanaryStep,
    ProductionActivationCommand,
    ProductionActivationPort,
    ProductionActivationReceipt,
    ProductionCanaryJournalError,
    ProductionCanaryJournalFailureCode,
    ProductionCanaryJournalPort,
    copy_persisted_step,
    validate_persisted_spec_binding,
)


_RUN_ID = re.compile(r"^st1506-run-[a-z0-9][a-z0-9.-]{2,95}$")
_IDEMPOTENCY_KEY = re.compile(r"^st1506-key-[a-z0-9][a-z0-9.-]{2,95}$")


@dataclass(frozen=True, slots=True)
class LocalProductionCanaryRun:
    run_id: str
    idempotency_key: str
    command: CanaryCommandKind
    observation: SyntheticObservation | None

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or type(self.idempotency_key) is not str
            or _IDEMPOTENCY_KEY.fullmatch(self.idempotency_key) is None
            or type(self.command) is not CanaryCommandKind
            or (
                self.observation is not None
                and type(self.observation) is not SyntheticObservation
            )
        ):
            raise ProductionCanaryError("RUN_INPUT_INVALID", "run")


@dataclass(frozen=True, slots=True)
class LocalProductionCanaryRunReceipt:
    result_document: dict[str, object]
    persistence: CanaryStepPersistReceipt
    recovered_after_commit_ambiguity: bool

    def __post_init__(self) -> None:
        if (
            type(self.result_document) is not dict
            or type(self.persistence) is not CanaryStepPersistReceipt
            or type(self.recovered_after_commit_ambiguity) is not bool
        ):
            raise ProductionCanaryError("RUN_RECEIPT_INVALID", "receipt")


class LocalProductionCanaryService:
    """Coordinate pure evaluation, disabled activation, and local persistence."""

    __slots__ = ("_activation", "_journal", "_spec")

    def __init__(
        self,
        *,
        spec: ProductionCanarySpec,
        activation: ProductionActivationPort,
        journal: ProductionCanaryJournalPort,
    ) -> None:
        if type(spec) is not ProductionCanarySpec:
            raise ProductionCanaryError("SERVICE_INPUT_INVALID", "spec")
        self._spec = spec
        self._activation = activation
        self._journal = journal

    def execute(
        self, request: LocalProductionCanaryRun
    ) -> LocalProductionCanaryRunReceipt:
        if type(request) is not LocalProductionCanaryRun:
            raise ProductionCanaryError("RUN_INPUT_INVALID", "run")
        self._verify_activation_boundary()
        previous = self._load_latest_closed(request.run_id)
        if previous is None:
            session = CanarySession(
                run_id=request.run_id,
                version=0,
                state=CanaryState.CANARY_READY,
            )
        else:
            if previous.contract_sha256 != self._spec.semantic_sha256:
                raise ProductionCanaryJournalError(
                    ProductionCanaryJournalFailureCode.TAMPER_DETECTED
                )
            session = CanarySession(
                run_id=previous.run_id,
                version=previous.current_version,
                state=previous.state,
            )
        decision = advance_once(
            self._spec,
            session,
            command=request.command,
            observation=request.observation,
        )
        result_document = decision.to_document(self._spec)
        result_json = canonical_bytes(result_document)
        result_sha256 = result_document.get("result_sha256")
        if type(result_sha256) is not str:
            raise ProductionCanaryError("RESULT_INVALID", "result")
        idempotency_key_sha256 = hashlib.sha256(
            request.idempotency_key.encode("ascii")
        ).hexdigest()
        observation_sha256 = (
            None
            if request.observation is None
            else canonical_sha256(request.observation.to_payload())
        )
        request_sha256 = canonical_sha256(
            {
                "schema": "RAOS_LOCAL_PRODUCTION_CANARY_REQUEST_V2",
                "run_id": request.run_id,
                "idempotency_key_sha256": idempotency_key_sha256,
                "contract_sha256": self._spec.semantic_sha256,
                "expected_version": session.version,
                "state": session.state.value,
                "command": request.command.value,
                "observation_sha256": observation_sha256,
            }
        )
        command = CanaryStepPersistCommand(
            run_id=request.run_id,
            idempotency_key_sha256=idempotency_key_sha256,
            request_sha256=request_sha256,
            contract_sha256=self._spec.semantic_sha256,
            expected_version=session.version,
            current_version=decision.session.version,
            state=decision.session.state,
            outcome=decision.outcome,
            result_sha256=result_sha256,
            result_json=result_json,
        )
        recovered = False
        try:
            persistence = self._commit_closed(command)
        except ProductionCanaryJournalError as error:
            if error.code is not ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS:
                raise
            try:
                persistence = self._recover_closed(command)
            except ProductionCanaryJournalError as recovery_error:
                if (
                    recovery_error.code
                    is ProductionCanaryJournalFailureCode.RECOVERY_NOT_FOUND
                ):
                    raise ProductionCanaryJournalError(
                        ProductionCanaryJournalFailureCode.COMMIT_AMBIGUOUS
                    ) from None
                raise
            recovered = True
        self._validate_receipt(command, persistence)
        observed = self._load_latest_closed(request.run_id)
        if observed is None:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            )
        self._validate_persisted_command(command, observed)
        if (
            observed.sequence != persistence.sequence
            or observed.previous_entry_sha256 != persistence.previous_entry_sha256
            or observed.entry_sha256 != persistence.entry_sha256
        ):
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            )
        return LocalProductionCanaryRunReceipt(
            result_document=result_document,
            persistence=persistence,
            recovered_after_commit_ambiguity=recovered,
        )

    def _verify_activation_boundary(self) -> None:
        try:
            mode = self._activation.mode
            counts = self._activation.external_action_counts
        except Exception:
            raise ProductionCanaryError(
                "ACTIVATION_BOUNDARY_UNAVAILABLE", "activation"
            ) from None
        if type(mode) is not str or mode != "DISABLED_RECORDED_LOCAL_ONLY":
            raise ProductionCanaryError("ACTIVATION_BOUNDARY_INVALID", "activation")
        if type(counts) is not tuple:
            raise ProductionCanaryError("ACTIVATION_BOUNDARY_INVALID", "activation")
        try:
            copied_counts = tuple((name, count) for name, count in counts)
        except Exception:
            raise ProductionCanaryError(
                "ACTIVATION_BOUNDARY_INVALID", "activation"
            ) from None
        if any(
            type(name) is not str or type(count) is not int
            for name, count in copied_counts
        ) or copied_counts != tuple((name, 0) for name in EXTERNAL_ACTION_NAMES):
            raise ProductionCanaryError("ACTIVATION_BOUNDARY_INVALID", "activation")
        command = ProductionActivationCommand(
            contract_sha256=self._spec.semantic_sha256,
            request_activation=False,
            requested_action_count=0,
            request_public_write=False,
        )
        try:
            observed = self._activation.request(command)
        except Exception:
            raise ProductionCanaryError(
                "ACTIVATION_BOUNDARY_UNAVAILABLE", "activation"
            ) from None
        if type(observed) is not ProductionActivationReceipt:
            raise ProductionCanaryError("ACTIVATION_RECEIPT_INVALID", "activation")
        try:
            receipt = ProductionActivationReceipt(
                contract_sha256=observed.contract_sha256,
                status=observed.status,
                activation_allowed=observed.activation_allowed,
                public_write_allowed=observed.public_write_allowed,
                actions_executed=observed.actions_executed,
                reason_code=observed.reason_code,
            )
        except Exception:
            raise ProductionCanaryError(
                "ACTIVATION_RECEIPT_INVALID", "activation"
            ) from None
        if receipt.contract_sha256 != command.contract_sha256:
            raise ProductionCanaryError("ACTIVATION_RECEIPT_INVALID", "activation")

    def _load_latest_closed(self, run_id: str) -> PersistedCanaryStep | None:
        try:
            observed = self._journal.load_latest(run_id)
        except ProductionCanaryJournalError as error:
            if self._is_closed_journal_error(error):
                raise
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        except Exception:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        if observed is None:
            return None
        persisted = copy_persisted_step(observed)
        validate_persisted_spec_binding(persisted, self._spec)
        return persisted

    def _commit_closed(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt:
        try:
            observed = self._journal.commit(command)
        except ProductionCanaryJournalError as error:
            if self._is_closed_journal_error(error):
                raise
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        except Exception:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        return self._copy_receipt(observed)

    def _recover_closed(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt:
        try:
            observed = self._journal.recover_exact(command)
        except ProductionCanaryJournalError as error:
            if self._is_closed_journal_error(error):
                raise
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        except Exception:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.STORAGE_FAILURE
            ) from None
        return self._copy_receipt(observed)

    @staticmethod
    def _is_closed_journal_error(error: object) -> bool:
        if type(error) is not ProductionCanaryJournalError:
            return False
        try:
            return (
                type(error.code) is ProductionCanaryJournalFailureCode
                and type(error.args) is tuple
                and error.args == (error.code.value,)
            )
        except Exception:
            return False

    @staticmethod
    def _copy_receipt(observed: object) -> CanaryStepPersistReceipt:
        if type(observed) is not CanaryStepPersistReceipt:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            )
        try:
            return CanaryStepPersistReceipt(
                run_id=observed.run_id,
                current_version=observed.current_version,
                request_sha256=observed.request_sha256,
                result_sha256=observed.result_sha256,
                sequence=observed.sequence,
                previous_entry_sha256=observed.previous_entry_sha256,
                entry_sha256=observed.entry_sha256,
                replayed=observed.replayed,
            )
        except Exception:
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            ) from None

    @staticmethod
    def _validate_receipt(
        command: CanaryStepPersistCommand,
        receipt: CanaryStepPersistReceipt,
    ) -> None:
        if (
            receipt.run_id != command.run_id
            or receipt.current_version != command.current_version
            or receipt.request_sha256 != command.request_sha256
            or receipt.result_sha256 != command.result_sha256
        ):
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            )

    @staticmethod
    def _validate_persisted_command(
        command: CanaryStepPersistCommand,
        persisted: PersistedCanaryStep,
    ) -> None:
        if (
            persisted.run_id != command.run_id
            or persisted.idempotency_key_sha256 != command.idempotency_key_sha256
            or persisted.request_sha256 != command.request_sha256
            or persisted.contract_sha256 != command.contract_sha256
            or persisted.expected_version != command.expected_version
            or persisted.current_version != command.current_version
            or persisted.state is not command.state
            or persisted.outcome is not command.outcome
            or persisted.result_sha256 != command.result_sha256
            or persisted.result_json != command.result_json
        ):
            raise ProductionCanaryJournalError(
                ProductionCanaryJournalFailureCode.TAMPER_DETECTED
            )


__all__ = [
    "LocalProductionCanaryRun",
    "LocalProductionCanaryRunReceipt",
    "LocalProductionCanaryService",
]
