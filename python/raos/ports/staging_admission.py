"""Outbound persistence port for the ST-1505 local admission simulator."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, cast

from raos.domain.ops.staging_admission import (
    StagingAdmissionError,
    canonical_bytes,
    canonical_sha256,
)


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID = re.compile(r"^st1505-run-[a-z0-9][a-z0-9.-]{2,95}$")
_MAX_RESULT_BYTES = 131_072


class StagingAdmissionJournalFailureCode(StrEnum):
    """Closed storage failures that never include local path or database data."""

    INVALID_COMMAND = "INVALID_COMMAND"
    STORAGE_PATH_INVALID = "STORAGE_PATH_INVALID"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    COMMIT_AMBIGUOUS = "COMMIT_AMBIGUOUS"
    REPLAY_CONFLICT = "REPLAY_CONFLICT"
    RECOVERY_NOT_FOUND = "RECOVERY_NOT_FOUND"
    TAMPER_DETECTED = "TAMPER_DETECTED"
    CONCURRENCY_FAILURE = "CONCURRENCY_FAILURE"


class StagingAdmissionJournalError(RuntimeError):
    """Sanitized failure from the owner-private local journal."""

    __slots__ = ("code",)

    def __init__(self, code: StagingAdmissionJournalFailureCode) -> None:
        if type(code) is not StagingAdmissionJournalFailureCode:
            raise TypeError("INVALID_JOURNAL_FAILURE_CODE")
        self.code = code
        super().__init__(code.value)


def _is_sha256(value: object) -> bool:
    return type(value) is str and _SHA256.fullmatch(value) is not None


@dataclass(frozen=True, slots=True)
class AdmissionPersistCommand:
    """A canonical local result and only hashed replay material."""

    run_id: str
    idempotency_key_sha256: str
    request_sha256: str
    contract_sha256: str
    result_sha256: str
    result_json: bytes

    def __post_init__(self) -> None:
        invalid = (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or not _is_sha256(self.idempotency_key_sha256)
            or not _is_sha256(self.request_sha256)
            or not _is_sha256(self.contract_sha256)
            or not _is_sha256(self.result_sha256)
            or type(self.result_json) is not bytes
            or not self.result_json
            or len(self.result_json) > _MAX_RESULT_BYTES
        )
        if invalid:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            )
        try:
            loaded = cast(object, json.loads(self.result_json))
        except json.JSONDecodeError, UnicodeDecodeError:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            ) from None
        if type(loaded) is not dict:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            )
        raw_document = cast(dict[object, object], loaded)
        if any(type(key) is not str for key in raw_document):
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            )
        document = cast(dict[str, object], loaded)
        try:
            observed_canonical = canonical_bytes(document)
        except StagingAdmissionError:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            ) from None
        if observed_canonical != self.result_json:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            )
        document_without_digest = dict(document)
        embedded_digest = document_without_digest.pop("result_sha256", None)
        if (
            embedded_digest != self.result_sha256
            or canonical_sha256(document_without_digest) != self.result_sha256
            or document.get("contract_sha256") != self.contract_sha256
        ):
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.INVALID_COMMAND
            )


@dataclass(frozen=True, slots=True)
class AdmissionPersistReceipt:
    """Hash-only receipt for one committed or exactly recovered result."""

    run_id: str
    idempotency_key_sha256: str
    request_sha256: str
    result_sha256: str
    sequence: int
    previous_entry_sha256: str
    entry_sha256: str
    replayed: bool

    def __post_init__(self) -> None:
        invalid = (
            type(self.run_id) is not str
            or _RUN_ID.fullmatch(self.run_id) is None
            or not _is_sha256(self.idempotency_key_sha256)
            or not _is_sha256(self.request_sha256)
            or not _is_sha256(self.result_sha256)
            or type(self.sequence) is not int
            or self.sequence < 1
            or not _is_sha256(self.previous_entry_sha256)
            or not _is_sha256(self.entry_sha256)
            or type(self.replayed) is not bool
        )
        if invalid:
            raise StagingAdmissionJournalError(
                StagingAdmissionJournalFailureCode.STORAGE_FAILURE
            )


class StagingAdmissionJournalPort(Protocol):
    """Owner-private durable boundary; no provider or network operation exists."""

    def commit(self, command: AdmissionPersistCommand) -> AdmissionPersistReceipt: ...

    def recover_exact(
        self, command: AdmissionPersistCommand
    ) -> AdmissionPersistReceipt: ...

    def verify_integrity(self) -> int: ...


__all__ = [
    "AdmissionPersistCommand",
    "AdmissionPersistReceipt",
    "StagingAdmissionJournalError",
    "StagingAdmissionJournalFailureCode",
    "StagingAdmissionJournalPort",
]
