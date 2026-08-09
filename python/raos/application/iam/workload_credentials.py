"""Configuration-bound orchestration for material-free workload leases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from raos.config.runtime import RuntimeConfig, RuntimeEnvironment
from raos.domain.iam.workload_credentials import (
    CredentialAlias,
    CredentialFailure,
    CredentialFailureCode,
    CredentialLease,
    CredentialLeaseMetadata,
    CredentialLeaseState,
    CredentialRequest,
    CredentialRotationNotice,
    WorkloadBinding,
    WorkloadEnvironment,
    fail_credential,
)
from raos.ports.workload_credentials import (
    CredentialRotationHook,
    WorkloadCredentialPort,
)


_WORKLOAD_ENVIRONMENTS = {
    RuntimeEnvironment.ENV_DEV: WorkloadEnvironment.ENV_DEV,
    RuntimeEnvironment.CI: WorkloadEnvironment.CI,
    RuntimeEnvironment.INTEGRATION: WorkloadEnvironment.INTEGRATION,
    RuntimeEnvironment.STAGING: WorkloadEnvironment.STAGING,
    RuntimeEnvironment.RECOVERY: WorkloadEnvironment.RECOVERY,
    RuntimeEnvironment.PRODUCTION: WorkloadEnvironment.PRODUCTION,
}
_PASSTHROUGH_PORT_CODES = frozenset(
    {
        CredentialFailureCode.BACKEND_NOT_CONFIGURED,
        CredentialFailureCode.BACKEND_FAILURE,
        CredentialFailureCode.DEVELOPMENT_ONLY,
        CredentialFailureCode.LEASE_REUSED,
        CredentialFailureCode.PURPOSE_NOT_ALLOWED,
    }
)


def _require_now(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_credential(CredentialFailureCode.INVALID_REQUEST)
    return value


def _supports_port(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, WorkloadCredentialPort)
    except Exception:
        pass
    return supported


def _supports_hook(candidate: object) -> bool:
    supported = False
    try:
        supported = isinstance(candidate, CredentialRotationHook)
    except Exception:
        pass
    return supported


def _normalize_metadata(candidate: object) -> CredentialLeaseMetadata:
    normalized: CredentialLeaseMetadata | None = None
    if type(candidate) is CredentialLeaseMetadata:
        metadata = candidate
        try:
            normalized = CredentialLeaseMetadata(
                request=_normalize_request(metadata.request),
                lease_id=metadata.lease_id,
                issued_at=metadata.issued_at,
                not_before=metadata.not_before,
                expires_at=metadata.expires_at,
            )
        except Exception:
            pass
    if normalized is None:
        fail_credential(CredentialFailureCode.LEASE_MALFORMED)
    return normalized


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


def _extract_open_lease(
    candidate: object,
) -> tuple[CredentialLease, CredentialLeaseMetadata]:
    metadata: object = None
    state: object = None
    malformed = False
    lease: CredentialLease | None = None
    if type(candidate) is CredentialLease:
        lease = candidate
        try:
            state = lease.state
            metadata = lease.metadata
        except Exception:
            malformed = True
    else:
        malformed = True
    if malformed or lease is None:
        fail_credential(CredentialFailureCode.LEASE_MALFORMED)
    if state is not CredentialLeaseState.ACTIVE:
        fail_credential(CredentialFailureCode.LEASE_CLOSED)
    return lease, _normalize_metadata(metadata)


class WorkloadCredentialService:
    """Validate configuration, lease windows, replay, and rotation hooks."""

    __slots__ = (
        "_accepted_lease_ids",
        "_config",
        "_maximum_lease_lifetime",
        "_port",
        "_rotation_hooks",
        "_rotation_notice_ids",
    )

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        port: WorkloadCredentialPort,
        maximum_lease_lifetime: timedelta,
        rotation_hooks: tuple[CredentialRotationHook, ...],
    ) -> None:
        if type(config) is not RuntimeConfig:
            raise TypeError("config must be an exact RuntimeConfig")
        if not _supports_port(port):
            raise TypeError("port must implement WorkloadCredentialPort")
        if type(
            maximum_lease_lifetime
        ) is not timedelta or maximum_lease_lifetime <= timedelta(0):
            raise ValueError("maximum_lease_lifetime must be a positive timedelta")
        if type(rotation_hooks) is not tuple or any(
            not _supports_hook(hook) for hook in rotation_hooks
        ):
            raise TypeError("rotation_hooks must contain only rotation hooks")
        if len({id(hook) for hook in rotation_hooks}) != len(rotation_hooks):
            raise ValueError("rotation_hooks cannot contain duplicate objects")
        self._config = config
        self._port = port
        self._maximum_lease_lifetime = maximum_lease_lifetime
        self._rotation_hooks = rotation_hooks
        self._accepted_lease_ids: set[str] = set()
        self._rotation_notice_ids: set[tuple[str, str]] = set()

    def acquire(self, *, request: CredentialRequest, now: datetime) -> CredentialLease:
        """Acquire and validate exactly one fresh lease without resolving a Secret."""

        normalized_request = _normalize_request(request)
        observed_at = _require_now(now)
        self._validate_request(normalized_request)

        candidate: object = None
        port_failure: CredentialFailureCode | None = None
        try:
            candidate = self._port.acquire(
                request=normalized_request,
                now=observed_at,
            )
        except CredentialFailure as error:
            if (
                type(error) is CredentialFailure
                and type(error.code) is CredentialFailureCode
                and error.code in _PASSTHROUGH_PORT_CODES
            ):
                port_failure = error.code
            else:
                port_failure = CredentialFailureCode.BACKEND_FAILURE
        except Exception:
            port_failure = CredentialFailureCode.BACKEND_FAILURE
        if port_failure is not None:
            fail_credential(port_failure)

        lease, metadata = _extract_open_lease(candidate)
        self._validate_current_metadata(
            metadata=metadata,
            request=normalized_request,
            observed_at=observed_at,
        )
        if metadata.lease_id in self._accepted_lease_ids:
            fail_credential(CredentialFailureCode.LEASE_REUSED)
        self._accepted_lease_ids.add(metadata.lease_id)
        lease.close()
        return CredentialLease(metadata)

    def notify_rotation(
        self,
        *,
        previous: CredentialLeaseMetadata,
        replacement: CredentialLeaseMetadata,
    ) -> None:
        """Synchronously dispatch one newer non-overlapping metadata notice."""

        normalized_previous = _normalize_metadata(previous)
        normalized_replacement = _normalize_metadata(replacement)
        self._validate_rotation(
            previous=normalized_previous,
            replacement=normalized_replacement,
        )
        notice_id = (
            normalized_previous.lease_id,
            normalized_replacement.lease_id,
        )
        if notice_id in self._rotation_notice_ids:
            fail_credential(CredentialFailureCode.ROTATION_INVALID)
        self._rotation_notice_ids.add(notice_id)
        notice = CredentialRotationNotice(
            previous=normalized_previous,
            replacement=normalized_replacement,
        )

        hook_failed = False
        for hook in self._rotation_hooks:
            try:
                hook.notify(notice)
            except Exception:
                hook_failed = True
            if hook_failed:
                break
        if hook_failed:
            fail_credential(CredentialFailureCode.ROTATION_HOOK_FAILED)

    def _validate_request(self, request: CredentialRequest) -> None:
        config_invalid = False
        expected_environment: WorkloadEnvironment | None = None
        service_name: object = None
        alias_present = False
        try:
            runtime_environment = self._config.environment
            service_name = self._config.service_name
            if type(runtime_environment) is RuntimeEnvironment:
                expected_environment = _WORKLOAD_ENVIRONMENTS.get(runtime_environment)
            alias_present = request.alias.value in self._config.secret_references
        except Exception:
            config_invalid = True
        if (
            config_invalid
            or expected_environment is None
            or type(service_name) is not str
        ):
            fail_credential(CredentialFailureCode.CONFIGURATION_MISMATCH)
        if (
            request.binding.environment is not expected_environment
            or request.binding.service_name != service_name
        ):
            fail_credential(CredentialFailureCode.CONFIGURATION_MISMATCH)
        if not alias_present:
            fail_credential(CredentialFailureCode.UNKNOWN_ALIAS)

    def _validate_current_metadata(
        self,
        *,
        metadata: CredentialLeaseMetadata,
        request: CredentialRequest,
        observed_at: datetime,
    ) -> None:
        if metadata.request != request:
            fail_credential(CredentialFailureCode.LEASE_MALFORMED)
        self._validate_lifetime(metadata)
        if metadata.issued_at > observed_at or metadata.not_before > observed_at:
            fail_credential(CredentialFailureCode.LEASE_NOT_YET_VALID)
        if metadata.expires_at <= observed_at:
            fail_credential(CredentialFailureCode.LEASE_EXPIRED)

    def _validate_lifetime(self, metadata: CredentialLeaseMetadata) -> None:
        if metadata.expires_at - metadata.issued_at > self._maximum_lease_lifetime:
            fail_credential(CredentialFailureCode.LEASE_LIFETIME_EXCEEDED)

    def _validate_rotation(
        self,
        *,
        previous: CredentialLeaseMetadata,
        replacement: CredentialLeaseMetadata,
    ) -> None:
        self._validate_request(previous.request)
        self._validate_lifetime(previous)
        self._validate_lifetime(replacement)
        if (
            previous.request != replacement.request
            or previous.lease_id == replacement.lease_id
            or replacement.issued_at < previous.expires_at
            or replacement.not_before < previous.expires_at
            or replacement.expires_at <= previous.expires_at
        ):
            fail_credential(CredentialFailureCode.ROTATION_INVALID)


__all__ = ["WorkloadCredentialService"]
