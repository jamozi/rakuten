"""Metadata-only development and default-disabled credential adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import NoReturn, SupportsIndex, final

from raos.config.runtime import RuntimeEnvironment
from raos.domain.iam.workload_credentials import (
    CredentialAlias,
    CredentialFailureCode,
    CredentialLease,
    CredentialLeaseMetadata,
    CredentialPurpose,
    CredentialRequest,
    WorkloadBinding,
    WorkloadEnvironment,
    fail_credential,
)


def _require_development(environment: object) -> RuntimeEnvironment:
    if (
        type(environment) is not RuntimeEnvironment
        or environment is not RuntimeEnvironment.ENV_DEV
    ):
        fail_credential(CredentialFailureCode.DEVELOPMENT_ONLY)
    return environment


def _require_operation_time(now: object) -> datetime:
    if type(now) is not datetime or now.tzinfo is not UTC:
        fail_credential(CredentialFailureCode.INVALID_REQUEST)
    return now


def _normalize_request(candidate: object) -> CredentialRequest:
    normalized: CredentialRequest | None = None
    if type(candidate) is CredentialRequest:
        request = candidate
        try:
            normalized = CredentialRequest(
                binding=WorkloadBinding(
                    service_name=request.binding.service_name,
                    environment=request.binding.environment,
                ),
                purpose=request.purpose,
                alias=CredentialAlias(request.alias.value),
            )
        except Exception:
            pass
    if normalized is None:
        fail_credential(CredentialFailureCode.INVALID_REQUEST)
    return normalized


def _normalize_metadata(candidate: object) -> CredentialLeaseMetadata:
    normalized: CredentialLeaseMetadata | None = None
    if type(candidate) is CredentialLeaseMetadata:
        entry = candidate
        try:
            normalized = CredentialLeaseMetadata(
                request=_normalize_request(entry.request),
                lease_id=entry.lease_id,
                issued_at=entry.issued_at,
                not_before=entry.not_before,
                expires_at=entry.expires_at,
            )
        except Exception:
            pass
    if normalized is None:
        fail_credential(CredentialFailureCode.LEASE_MALFORMED)
    return normalized


@final
class DevelopmentScriptedWorkloadCredentialAdapter:
    """Consume deterministic ENV-DEV lease metadata without material or I/O."""

    __slots__ = ("_entries", "_environment", "_issued_indexes")

    def __init__(
        self,
        *,
        environment: RuntimeEnvironment,
        entries: tuple[CredentialLeaseMetadata, ...],
    ) -> None:
        self._environment = _require_development(environment)
        if type(entries) is not tuple:
            fail_credential(CredentialFailureCode.LEASE_MALFORMED)
        lease_ids: set[str] = set()
        normalized_entries: list[CredentialLeaseMetadata] = []
        for candidate in entries:
            entry = _normalize_metadata(candidate)
            if (
                entry.request.binding.environment is not WorkloadEnvironment.ENV_DEV
                or entry.request.purpose is CredentialPurpose.CI_DEPLOYMENT
                or entry.lease_id in lease_ids
            ):
                fail_credential(CredentialFailureCode.PURPOSE_NOT_ALLOWED)
            lease_ids.add(entry.lease_id)
            normalized_entries.append(entry)
        self._entries = tuple(normalized_entries)
        self._issued_indexes: set[int] = set()

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        """Issue one matching scripted metadata entry at most once."""

        self._guard()
        normalized_request = _normalize_request(request)
        _require_operation_time(now)
        if normalized_request.binding.environment is not WorkloadEnvironment.ENV_DEV:
            fail_credential(CredentialFailureCode.DEVELOPMENT_ONLY)
        if normalized_request.purpose is CredentialPurpose.CI_DEPLOYMENT:
            fail_credential(CredentialFailureCode.PURPOSE_NOT_ALLOWED)
        matching_consumed = False
        for index, entry in enumerate(self._entries):
            if entry.request == normalized_request:
                if index in self._issued_indexes:
                    matching_consumed = True
                    continue
                self._issued_indexes.add(index)
                return CredentialLease(entry)
        if matching_consumed:
            fail_credential(CredentialFailureCode.LEASE_REUSED)
        fail_credential(CredentialFailureCode.BACKEND_FAILURE)

    def _guard(self) -> None:
        _require_development(self._environment)

    def __repr__(self) -> str:
        return (
            "DevelopmentScriptedWorkloadCredentialAdapter("
            "environment='ENV-DEV', entries=<redacted>)"
        )

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("development credential adapter serialization is unsupported")


@final
class DisabledWorkloadCredentialAdapter:
    """Fail closed until an explicitly approved backend is configured."""

    __slots__ = ()

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        del request, now
        fail_credential(CredentialFailureCode.BACKEND_NOT_CONFIGURED)

    def __repr__(self) -> str:
        return "DisabledWorkloadCredentialAdapter(<backend-not-configured>)"


__all__ = [
    "DevelopmentScriptedWorkloadCredentialAdapter",
    "DisabledWorkloadCredentialAdapter",
]
