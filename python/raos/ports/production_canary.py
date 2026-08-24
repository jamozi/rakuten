"""Ports for the ST-1506 offline Production canary simulator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import NoReturn, Protocol, cast

from raos.domain.ops.production_canary import (
    APPROVAL_NAMES,
    APPROVAL_TYPES,
    CanaryCommandKind,
    CanaryOutcome,
    CanaryState,
    EXTERNAL_ACTION_NAMES,
    ProductionCanaryError,
    ProductionCanarySpec,
    REQUIRED_CAPABILITY_IDS,
    canonical_bytes,
    canonical_sha256,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^st1506-run-[a-z0-9][a-z0-9.-]{2,95}$")
_MAX_RESULT_BYTES = 131_072


class ProductionCanaryJournalFailureCode(StrEnum):
    INVALID_COMMAND = "INVALID_COMMAND"
    STORAGE_PATH_INVALID = "STORAGE_PATH_INVALID"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    COMMIT_AMBIGUOUS = "COMMIT_AMBIGUOUS"
    REPLAY_CONFLICT = "REPLAY_CONFLICT"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    CONCURRENCY_FAILURE = "CONCURRENCY_FAILURE"


class ProductionCanaryJournalError(RuntimeError):
    """Sanitized owner-private journal error."""

    __slots__ = ("code",)

    def __init__(self, code: ProductionCanaryJournalFailureCode) -> None:
        if type(code) is not ProductionCanaryJournalFailureCode:
            raise TypeError("INVALID_JOURNAL_FAILURE_CODE")
        self.code = code
        super().__init__(code.value)


def _journal_fail(code: ProductionCanaryJournalFailureCode) -> NoReturn:
    raise ProductionCanaryJournalError(code) from None


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


def _load_result(result_json: bytes) -> dict[str, object]:
    if (
        type(result_json) is not bytes
        or not result_json
        or len(result_json) > _MAX_RESULT_BYTES
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    try:
        loaded = cast(object, json.loads(result_json))
    except json.JSONDecodeError, UnicodeDecodeError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    if type(loaded) is not dict:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    raw = cast(dict[object, object], loaded)
    if any(type(key) is not str for key in raw):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    document = cast(dict[str, object], loaded)
    try:
        if canonical_bytes(document) != result_json:
            _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    except ProductionCanaryError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    return document


def _validate_result_document(
    document: dict[str, object],
    *,
    run_id: str,
    expected_version: int,
    current_version: int,
    contract_sha256: str,
    result_sha256: str,
) -> tuple[CanaryState, CanaryState, CanaryOutcome]:
    expected_keys = {
        "schema",
        "version",
        "run_id",
        "previous_version",
        "current_version",
        "from_state",
        "to_state",
        "command",
        "outcome",
        "observation_sha256",
        "block_reason",
        "contract_sha256",
        "staging_admission",
        "capability_boundary",
        "human_approvals",
        "approval_artifact_count",
        "activation",
        "kill_switch",
        "action_counts",
        "classification",
        "external_evidence",
        "result_sha256",
    }
    without_digest = dict(document)
    embedded_digest = without_digest.pop("result_sha256", None)
    try:
        observed_digest = canonical_sha256(without_digest)
    except ProductionCanaryError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    if (
        embedded_digest != result_sha256
        or observed_digest != result_sha256
        or document.get("schema") != "RAOS_LOCAL_PRODUCTION_CANARY_STEP_RESULT_V2"
        or document.get("version") != 2
        or document.get("run_id") != run_id
        or document.get("previous_version") != expected_version
        or document.get("current_version") != current_version
        or document.get("contract_sha256") != contract_sha256
        or set(document) != expected_keys
        or type(document.get("approval_artifact_count")) is not int
        or document.get("approval_artifact_count") != 0
        or document.get("classification")
        != "DETERMINISTIC_SYNTHETIC_LOCAL_ONLY_NOT_PRODUCTION_EVIDENCE"
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    try:
        from_state = CanaryState(cast(str, document.get("from_state")))
        state = CanaryState(cast(str, document.get("to_state")))
        command = CanaryCommandKind(cast(str, document.get("command")))
        outcome = CanaryOutcome(cast(str, document.get("outcome")))
    except TypeError, ValueError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    expected_relation = {
        CanaryOutcome.OBSERVE_REQUIRED: (
            CanaryState.CANARY_READY,
            CanaryState.OBSERVE,
        ),
        CanaryOutcome.DATA_BLOCKED: (CanaryState.OBSERVE, CanaryState.OBSERVE),
        CanaryOutcome.HUMAN_APPROVALS_REQUIRED: (
            CanaryState.OBSERVE,
            CanaryState.HOLD_FOR_HUMAN_APPROVAL,
        ),
        CanaryOutcome.ABORT_REQUIRED: (
            CanaryState.OBSERVE,
            CanaryState.ABORT_REQUIRED,
        ),
        CanaryOutcome.ROLLBACK_REQUIRED: (
            CanaryState.OBSERVE,
            CanaryState.ROLLBACK_REQUIRED,
        ),
    }
    if expected_relation[outcome] != (from_state, state):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    block_reason = document.get("block_reason")
    observation_sha256 = document.get("observation_sha256")
    allowed_block_reasons = {
        "MISSING_OBSERVATION",
        "FUTURE_OBSERVATION",
        "STALE_OBSERVATION",
        "CONTRACT_MISMATCH",
        "ARTIFACT_MISMATCH",
        "STAGING_RESULT_MISMATCH",
        "COHORT_MISMATCH",
        "IMMATURE_COHORT",
    }
    if (
        (outcome is CanaryOutcome.DATA_BLOCKED) != (type(block_reason) is str)
        or (type(block_reason) is str and block_reason not in allowed_block_reasons)
        or (
            outcome is CanaryOutcome.OBSERVE_REQUIRED
            and (command is not CanaryCommandKind.START_CANARY_SIMULATION)
        )
        or (
            outcome is not CanaryOutcome.OBSERVE_REQUIRED
            and command is not CanaryCommandKind.RECORD_SYNTHETIC_OBSERVATION
        )
        or (
            outcome is CanaryOutcome.OBSERVE_REQUIRED and observation_sha256 is not None
        )
        or (block_reason == "MISSING_OBSERVATION" and observation_sha256 is not None)
        or (
            outcome is not CanaryOutcome.OBSERVE_REQUIRED
            and block_reason != "MISSING_OBSERVATION"
            and not _is_sha256(observation_sha256)
        )
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    staging = document.get("staging_admission")
    if type(staging) is not dict:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    staging_values = cast(dict[object, object], staging)
    expected_staging_keys = {
        "contract_sha256",
        "contract_semantic_sha256",
        "manifest_sha256",
        "pipeline_sha256",
        "result_file_sha256",
        "result_sha256",
        "artifact_sha256",
        "sbom_sha256",
        "provenance_sha256",
    }
    if set(staging_values) != expected_staging_keys or any(
        not _is_sha256(value) for value in staging_values.values()
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    capability = document.get("capability_boundary")
    expected_capability = {
        "required_capability_ids": list(REQUIRED_CAPABILITY_IDS),
        "selected_mapping_count": 0,
        "selected_profile": None,
        "default_profile": None,
        "fallback_profile": None,
        "eligibility": "BLOCKED_NOT_CONFIGURED",
    }
    try:
        if canonical_bytes(capability) != canonical_bytes(expected_capability):
            _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    except ProductionCanaryError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    approvals = document.get("human_approvals")
    if type(approvals) is not dict:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    approval_values = cast(dict[object, object], approvals)
    expected_approvals: dict[str, object] = {
        name: {"artifact_type": artifact_type, "status": "ABSENT"}
        for name, artifact_type in zip(APPROVAL_NAMES, APPROVAL_TYPES, strict=True)
    }
    try:
        if canonical_bytes(approval_values) != canonical_bytes(expected_approvals):
            _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    except ProductionCanaryError:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    action_counts = document.get("action_counts")
    if type(action_counts) is not dict:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    counts = cast(dict[object, object], action_counts)
    if frozenset(counts) != frozenset(EXTERNAL_ACTION_NAMES) or any(
        type(value) is not int or value != 0 for value in counts.values()
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    activation = document.get("activation")
    kill_switch = document.get("kill_switch")
    external_evidence = document.get("external_evidence")
    expected_activation = {
        "enabled": False,
        "authority": "NONE",
        "public_write_authority": "NONE",
        "auto_advance": "FORBIDDEN",
    }
    expected_kill_switch = {
        "safeguard_enabled": True,
        "deactivation_allowed": False,
        "deactivation_authority": "NONE",
        "external_action_count": 0,
    }
    expected_evidence = {
        "formal_tst_009": "NOT_EXECUTED",
        "formal_tst_022": "NOT_EXECUTED",
        "formal_tst_032": "NOT_EXECUTED",
        "staging": "NOT_EXECUTED",
        "release": "NOT_EXECUTED",
        "production": "NOT_EXECUTED",
    }
    try:
        fixed_boundaries_valid = (
            canonical_bytes(activation) == canonical_bytes(expected_activation)
            and canonical_bytes(kill_switch) == canonical_bytes(expected_kill_switch)
            and canonical_bytes(external_evidence) == canonical_bytes(expected_evidence)
        )
    except ProductionCanaryError:
        fixed_boundaries_valid = False
    if not fixed_boundaries_valid:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    return from_state, state, outcome


@dataclass(frozen=True, slots=True)
class ProductionActivationCommand:
    contract_sha256: str
    request_activation: bool
    requested_action_count: int
    request_public_write: bool

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.contract_sha256)
            or type(self.request_activation) is not bool
            or self.request_activation
            or type(self.requested_action_count) is not int
            or self.requested_action_count != 0
            or type(self.request_public_write) is not bool
            or self.request_public_write
        ):
            raise ProductionCanaryError("ACTIVATION_COMMAND_INVALID", "activation")


@dataclass(frozen=True, slots=True)
class ProductionActivationReceipt:
    contract_sha256: str
    status: str
    activation_allowed: bool
    public_write_allowed: bool
    actions_executed: int
    reason_code: str

    def __post_init__(self) -> None:
        if (
            not _is_sha256(self.contract_sha256)
            or self.status != "DISABLED"
            or type(self.activation_allowed) is not bool
            or self.activation_allowed
            or type(self.public_write_allowed) is not bool
            or self.public_write_allowed
            or type(self.actions_executed) is not int
            or self.actions_executed != 0
            or self.reason_code != "LOCAL_PRODUCTION_ACTIVATION_DISABLED"
        ):
            raise ProductionCanaryError("ACTIVATION_RECEIPT_INVALID", "activation")


class ProductionActivationPort(Protocol):
    @property
    def mode(self) -> str: ...

    @property
    def external_action_counts(self) -> tuple[tuple[str, int], ...]: ...

    def request(
        self, command: ProductionActivationCommand
    ) -> ProductionActivationReceipt: ...


@dataclass(frozen=True, slots=True)
class CanaryStepPersistCommand:
    run_id: str
    idempotency_key_sha256: str
    request_sha256: str
    contract_sha256: str
    expected_version: int
    current_version: int
    state: CanaryState
    outcome: CanaryOutcome
    result_sha256: str
    result_json: bytes

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or not _is_sha256(self.idempotency_key_sha256)
            or not _is_sha256(self.request_sha256)
            or not _is_sha256(self.contract_sha256)
            or type(self.expected_version) is not int
            or self.expected_version < 0
            or type(self.current_version) is not int
            or self.current_version != self.expected_version + 1
            or type(self.state) is not CanaryState
            or type(self.outcome) is not CanaryOutcome
            or not _is_sha256(self.result_sha256)
        ):
            _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
        document = _load_result(self.result_json)
        _, observed_state, observed_outcome = _validate_result_document(
            document,
            run_id=self.run_id,
            expected_version=self.expected_version,
            current_version=self.current_version,
            contract_sha256=self.contract_sha256,
            result_sha256=self.result_sha256,
        )
        if observed_state is not self.state or observed_outcome is not self.outcome:
            _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)


@dataclass(frozen=True, slots=True)
class CanaryStepPersistReceipt:
    run_id: str
    current_version: int
    request_sha256: str
    result_sha256: str
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        if (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or type(self.current_version) is not int
            or self.current_version < 1
            or not _is_sha256(self.request_sha256)
            or not _is_sha256(self.result_sha256)
            or type(self.sequence) is not int
            or self.sequence < 1
            or not _is_sha256(self.previous_entry_sha256)
            or not _is_sha256(self.entry_sha256)
            or type(self.replayed) is not bool
        ):
            _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)


@dataclass(frozen=True, slots=True)
class PersistedCanaryStep:
    run_id: str
    idempotency_key_sha256: str
    request_sha256: str
    contract_sha256: str
    expected_version: int
    current_version: int
    state: CanaryState
    outcome: CanaryOutcome
    result_sha256: str
    result_json: bytes
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str

    def __post_init__(self) -> None:
        command = CanaryStepPersistCommand(
            run_id=self.run_id,
            idempotency_key_sha256=self.idempotency_key_sha256,
            request_sha256=self.request_sha256,
            contract_sha256=self.contract_sha256,
            expected_version=self.expected_version,
            current_version=self.current_version,
            state=self.state,
            outcome=self.outcome,
            result_sha256=self.result_sha256,
            result_json=self.result_json,
        )
        del command
        if (
            type(self.sequence) is not int
            or self.sequence < 1
            or not _is_sha256(self.previous_entry_sha256)
            or not _is_sha256(self.entry_sha256)
            or self.entry_sha256
            != canary_entry_sha256(
                run_id=self.run_id,
                idempotency_key_sha256=self.idempotency_key_sha256,
                request_sha256=self.request_sha256,
                contract_sha256=self.contract_sha256,
                expected_version=self.expected_version,
                current_version=self.current_version,
                state=self.state,
                outcome=self.outcome,
                result_sha256=self.result_sha256,
                sequence=self.sequence,
                previous_entry_sha256=self.previous_entry_sha256,
            )
        ):
            _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)

    def to_receipt(self, *, replayed: bool) -> CanaryStepPersistReceipt:
        return CanaryStepPersistReceipt(
            run_id=self.run_id,
            current_version=self.current_version,
            request_sha256=self.request_sha256,
            result_sha256=self.result_sha256,
            sequence=self.sequence,
            previous_entry_sha256=self.previous_entry_sha256,
            entry_sha256=self.entry_sha256,
            replayed=replayed,
        )


def copy_persisted_step(observed: object) -> PersistedCanaryStep:
    if type(observed) is not PersistedCanaryStep:
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
    value = observed
    try:
        return PersistedCanaryStep(
            run_id=value.run_id,
            idempotency_key_sha256=value.idempotency_key_sha256,
            request_sha256=value.request_sha256,
            contract_sha256=value.contract_sha256,
            expected_version=value.expected_version,
            current_version=value.current_version,
            state=value.state,
            outcome=value.outcome,
            result_sha256=value.result_sha256,
            result_json=value.result_json,
            sequence=value.sequence,
            previous_entry_sha256=value.previous_entry_sha256,
            entry_sha256=value.entry_sha256,
        )
    except Exception:
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)


def validate_persisted_binding(
    persisted: PersistedCanaryStep,
    command: CanaryStepPersistCommand,
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
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)


def validate_persisted_spec_binding(
    persisted: PersistedCanaryStep,
    spec: ProductionCanarySpec,
) -> None:
    """Bind a collaborator-returned persisted result to the exact loaded spec."""

    if (
        type(persisted) is not PersistedCanaryStep
        or type(spec) is not ProductionCanarySpec
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
    document = _load_result(persisted.result_json)
    expected_staging = {
        "contract_sha256": spec.staging_contract_sha256,
        "contract_semantic_sha256": spec.staging_contract_semantic_sha256,
        "manifest_sha256": spec.staging_manifest_sha256,
        "pipeline_sha256": spec.staging_pipeline_sha256,
        "result_file_sha256": spec.staging_result_file_sha256,
        "result_sha256": spec.staging_result_sha256,
        "artifact_sha256": spec.artifact_sha256,
        "sbom_sha256": spec.sbom_sha256,
        "provenance_sha256": spec.provenance_sha256,
    }
    try:
        staging_matches = canonical_bytes(
            document.get("staging_admission")
        ) == canonical_bytes(expected_staging)
        actions_match = canonical_bytes(
            document.get("action_counts")
        ) == canonical_bytes(dict(spec.action_counts))
    except ProductionCanaryError:
        staging_matches = False
        actions_match = False
    if (
        document.get("contract_sha256") != spec.semantic_sha256
        or not staging_matches
        or not actions_match
    ):
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)


def validated_persisted_transition(
    persisted: PersistedCanaryStep,
) -> tuple[CanaryState, CanaryState, CanaryOutcome]:
    """Revalidate and expose only the closed transition needed by the journal."""

    if type(persisted) is not PersistedCanaryStep:
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)
    document = _load_result(persisted.result_json)
    return _validate_result_document(
        document,
        run_id=persisted.run_id,
        expected_version=persisted.expected_version,
        current_version=persisted.current_version,
        contract_sha256=persisted.contract_sha256,
        result_sha256=persisted.result_sha256,
    )


def validated_command_transition(
    command: CanaryStepPersistCommand,
) -> tuple[CanaryState, CanaryState, CanaryOutcome]:
    """Revalidate a write command before any journal mutation."""

    if type(command) is not CanaryStepPersistCommand:
        _journal_fail(ProductionCanaryJournalFailureCode.INVALID_COMMAND)
    document = _load_result(command.result_json)
    return _validate_result_document(
        document,
        run_id=command.run_id,
        expected_version=command.expected_version,
        current_version=command.current_version,
        contract_sha256=command.contract_sha256,
        result_sha256=command.result_sha256,
    )


def canary_entry_sha256(
    *,
    run_id: str,
    idempotency_key_sha256: str,
    request_sha256: str,
    contract_sha256: str,
    expected_version: int,
    current_version: int,
    state: CanaryState,
    outcome: CanaryOutcome,
    result_sha256: str,
    sequence: int,
    previous_entry_sha256: str,
) -> str:
    """Content address one journal entry including its predecessor."""

    try:
        return canonical_sha256(
            {
                "schema": "RAOS_LOCAL_PRODUCTION_CANARY_JOURNAL_ENTRY_V2",
                "sequence": sequence,
                "previous_entry_sha256": previous_entry_sha256,
                "run_id": run_id,
                "idempotency_key_sha256": idempotency_key_sha256,
                "request_sha256": request_sha256,
                "contract_sha256": contract_sha256,
                "expected_version": expected_version,
                "current_version": current_version,
                "state": state.value,
                "outcome": outcome.value,
                "result_sha256": result_sha256,
            }
        )
    except AttributeError, ProductionCanaryError:
        _journal_fail(ProductionCanaryJournalFailureCode.TAMPER_DETECTED)


class ProductionCanaryJournalPort(Protocol):
    def commit(self, command: CanaryStepPersistCommand) -> CanaryStepPersistReceipt: ...

    def recover_exact(
        self, command: CanaryStepPersistCommand
    ) -> CanaryStepPersistReceipt: ...

    def load_latest(self, run_id: str) -> PersistedCanaryStep | None: ...

    def verify_integrity(self) -> int: ...


__all__ = [
    "CanaryStepPersistCommand",
    "CanaryStepPersistReceipt",
    "PersistedCanaryStep",
    "ProductionActivationCommand",
    "ProductionActivationPort",
    "ProductionActivationReceipt",
    "ProductionCanaryJournalError",
    "ProductionCanaryJournalFailureCode",
    "ProductionCanaryJournalPort",
    "canary_entry_sha256",
    "copy_persisted_step",
    "validate_persisted_spec_binding",
    "validated_command_transition",
    "validated_persisted_transition",
    "validate_persisted_binding",
]
