"""Provider-neutral, material-free workload credential contracts."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import re
from typing import NoReturn, SupportsIndex, final


_SERVICE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
_CREDENTIAL_ALIAS = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z")
_LEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
_REDACTED = "<redacted-workload-credential>"


class WorkloadEnvironment(str, Enum):
    """Closed environment taxonomy used without importing configuration code."""

    ENV_DEV = "ENV-DEV"
    CI = "ENV-CI"
    INTEGRATION = "ENV-INTEGRATION"
    STAGING = "ENV-STAGING"
    RECOVERY = "ENV-RECOVERY"
    PRODUCTION = "ENV-PRODUCTION"


class CredentialPurpose(str, Enum):
    """Closed machine-workload credential purposes."""

    PROVIDER_API = "PROVIDER_API"
    DATABASE_CONNECTION = "DATABASE_CONNECTION"
    CI_DEPLOYMENT = "CI_DEPLOYMENT"


class CredentialLeaseState(str, Enum):
    """The only states exposed by a material-free lease handle."""

    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class CredentialFailureCode(str, Enum):
    """Stable sanitized workload-credential failure classifications."""

    INVALID_REQUEST = "INVALID_REQUEST"
    CONFIGURATION_MISMATCH = "CONFIGURATION_MISMATCH"
    UNKNOWN_ALIAS = "UNKNOWN_ALIAS"
    PURPOSE_NOT_ALLOWED = "PURPOSE_NOT_ALLOWED"
    BACKEND_NOT_CONFIGURED = "BACKEND_NOT_CONFIGURED"
    BACKEND_FAILURE = "BACKEND_FAILURE"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    LEASE_MALFORMED = "LEASE_MALFORMED"
    LEASE_NOT_YET_VALID = "LEASE_NOT_YET_VALID"
    LEASE_EXPIRED = "LEASE_EXPIRED"
    LEASE_LIFETIME_EXCEEDED = "LEASE_LIFETIME_EXCEEDED"
    LEASE_CLOSED = "LEASE_CLOSED"
    LEASE_REUSED = "LEASE_REUSED"
    ROTATION_INVALID = "ROTATION_INVALID"
    ROTATION_HOOK_FAILED = "ROTATION_HOOK_FAILED"


@final
class CredentialFailure(RuntimeError):
    """Immutable failure retaining only one public stable code."""

    __slots__ = ("_code", "_sealed")
    _code: CredentialFailureCode
    _sealed: bool

    def __init__(self, code: CredentialFailureCode) -> None:
        if type(code) is not CredentialFailureCode:
            raise TypeError("code must be an exact CredentialFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> CredentialFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CredentialFailure is immutable")

    def __delattr__(self, name: str) -> None:
        del name
        raise AttributeError("CredentialFailure is immutable")

    def __repr__(self) -> str:
        return f"CredentialFailure(code={self.code!r})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("credential failure serialization is not supported")


def fail_credential(code: CredentialFailureCode) -> NoReturn:
    """Raise one sanitized failure without retaining rejected input."""

    raise CredentialFailure(code) from None


def require_credential_utc(value: object) -> datetime:
    """Accept only an exact datetime carrying the explicit UTC singleton."""

    if type(value) is not datetime or value.tzinfo is not UTC:
        fail_credential(CredentialFailureCode.LEASE_MALFORMED)
    return value


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("workload credential serialization is not supported")


@final
class CredentialAlias(_RedactedValue):
    """A bounded logical configuration alias, never a Secret reference value."""

    __slots__ = ("_value", "_sealed")
    _value: str
    _sealed: bool

    def __init__(self, value: str) -> None:
        if (
            type(value) is not str
            or len(value) > 64
            or _CREDENTIAL_ALIAS.fullmatch(value) is None
        ):
            fail_credential(CredentialFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "_value", value)
        object.__setattr__(self, "_sealed", True)

    @property
    def value(self) -> str:
        return self._value

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CredentialAlias is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CredentialAlias is immutable")

    def __eq__(self, other: object) -> bool:
        return type(other) is CredentialAlias and self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)


@final
class WorkloadBinding(_RedactedValue):
    """One exact service and environment workload binding."""

    __slots__ = ("_environment", "_sealed", "_service_name")
    _service_name: str
    _environment: WorkloadEnvironment
    _sealed: bool

    def __init__(self, *, service_name: str, environment: WorkloadEnvironment) -> None:
        if (
            type(service_name) is not str
            or len(service_name) > 63
            or _SERVICE_NAME.fullmatch(service_name) is None
            or type(environment) is not WorkloadEnvironment
        ):
            fail_credential(CredentialFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "_service_name", service_name)
        object.__setattr__(self, "_environment", environment)
        object.__setattr__(self, "_sealed", True)

    @property
    def service_name(self) -> str:
        return self._service_name

    @property
    def environment(self) -> WorkloadEnvironment:
        return self._environment

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("WorkloadBinding is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("WorkloadBinding is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is WorkloadBinding
            and self._service_name == other._service_name
            and self._environment is other._environment
        )

    def __hash__(self) -> int:
        return hash((self._service_name, self._environment))


@final
class CredentialRequest(_RedactedValue):
    """A material-free request bound to one workload, alias, and purpose."""

    __slots__ = ("_alias", "_binding", "_purpose", "_sealed")
    _binding: WorkloadBinding
    _purpose: CredentialPurpose
    _alias: CredentialAlias
    _sealed: bool

    def __init__(
        self,
        *,
        binding: WorkloadBinding,
        purpose: CredentialPurpose,
        alias: CredentialAlias,
    ) -> None:
        if (
            type(binding) is not WorkloadBinding
            or type(purpose) is not CredentialPurpose
            or type(alias) is not CredentialAlias
        ):
            fail_credential(CredentialFailureCode.INVALID_REQUEST)
        object.__setattr__(self, "_binding", binding)
        object.__setattr__(self, "_purpose", purpose)
        object.__setattr__(self, "_alias", alias)
        object.__setattr__(self, "_sealed", True)

    @property
    def binding(self) -> WorkloadBinding:
        return self._binding

    @property
    def purpose(self) -> CredentialPurpose:
        return self._purpose

    @property
    def alias(self) -> CredentialAlias:
        return self._alias

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CredentialRequest is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CredentialRequest is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is CredentialRequest
            and self._binding == other._binding
            and self._purpose is other._purpose
            and self._alias == other._alias
        )

    def __hash__(self) -> int:
        return hash((self._binding, self._purpose, self._alias))


@final
class CredentialLeaseMetadata(_RedactedValue):
    """Safe issuance metadata with an explicit UTC validity window."""

    __slots__ = (
        "_expires_at",
        "_issued_at",
        "_lease_id",
        "_not_before",
        "_request",
        "_sealed",
    )
    _request: CredentialRequest
    _lease_id: str
    _issued_at: datetime
    _not_before: datetime
    _expires_at: datetime
    _sealed: bool

    def __init__(
        self,
        *,
        request: CredentialRequest,
        lease_id: str,
        issued_at: datetime,
        not_before: datetime,
        expires_at: datetime,
    ) -> None:
        if (
            type(request) is not CredentialRequest
            or type(lease_id) is not str
            or _LEASE_ID.fullmatch(lease_id) is None
        ):
            fail_credential(CredentialFailureCode.LEASE_MALFORMED)
        normalized_issued_at = require_credential_utc(issued_at)
        normalized_not_before = require_credential_utc(not_before)
        normalized_expires_at = require_credential_utc(expires_at)
        if not normalized_issued_at <= normalized_not_before < normalized_expires_at:
            fail_credential(CredentialFailureCode.LEASE_MALFORMED)
        object.__setattr__(self, "_request", request)
        object.__setattr__(self, "_lease_id", lease_id)
        object.__setattr__(self, "_issued_at", normalized_issued_at)
        object.__setattr__(self, "_not_before", normalized_not_before)
        object.__setattr__(self, "_expires_at", normalized_expires_at)
        object.__setattr__(self, "_sealed", True)

    @property
    def request(self) -> CredentialRequest:
        return self._request

    @property
    def lease_id(self) -> str:
        return self._lease_id

    @property
    def issued_at(self) -> datetime:
        return self._issued_at

    @property
    def not_before(self) -> datetime:
        return self._not_before

    @property
    def expires_at(self) -> datetime:
        return self._expires_at

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CredentialLeaseMetadata is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CredentialLeaseMetadata is immutable")

    def __eq__(self, other: object) -> bool:
        return (
            type(other) is CredentialLeaseMetadata
            and self._request == other._request
            and self._lease_id == other._lease_id
            and self._issued_at == other._issued_at
            and self._not_before == other._not_before
            and self._expires_at == other._expires_at
        )

    def __hash__(self) -> int:
        return hash(
            (
                self._request,
                self._lease_id,
                self._issued_at,
                self._not_before,
                self._expires_at,
            )
        )


@final
class CredentialRotationNotice(_RedactedValue):
    """A metadata-only predecessor/replacement notification."""

    __slots__ = ("_previous", "_replacement", "_sealed")
    _previous: CredentialLeaseMetadata
    _replacement: CredentialLeaseMetadata
    _sealed: bool

    def __init__(
        self,
        *,
        previous: CredentialLeaseMetadata,
        replacement: CredentialLeaseMetadata,
    ) -> None:
        if (
            type(previous) is not CredentialLeaseMetadata
            or type(replacement) is not CredentialLeaseMetadata
        ):
            fail_credential(CredentialFailureCode.ROTATION_INVALID)
        object.__setattr__(self, "_previous", previous)
        object.__setattr__(self, "_replacement", replacement)
        object.__setattr__(self, "_sealed", True)

    @property
    def previous(self) -> CredentialLeaseMetadata:
        return self._previous

    @property
    def replacement(self) -> CredentialLeaseMetadata:
        return self._replacement

    def __setattr__(self, name: str, value: object) -> None:
        del name, value
        raise AttributeError("CredentialRotationNotice is immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CredentialRotationNotice is immutable")


@final
class CredentialLease(_RedactedValue):
    """Opaque material-free lease exposing only metadata and close state."""

    __slots__ = ("_metadata", "_state")
    _metadata: CredentialLeaseMetadata
    _state: CredentialLeaseState

    def __init__(self, metadata: CredentialLeaseMetadata) -> None:
        if type(metadata) is not CredentialLeaseMetadata:
            fail_credential(CredentialFailureCode.LEASE_MALFORMED)
        object.__setattr__(self, "_metadata", metadata)
        object.__setattr__(self, "_state", CredentialLeaseState.ACTIVE)

    @property
    def metadata(self) -> CredentialLeaseMetadata:
        return self._metadata

    @property
    def state(self) -> CredentialLeaseState:
        return self._state

    @property
    def closed(self) -> bool:
        return self._state is CredentialLeaseState.CLOSED

    def close(self) -> None:
        """Close the handle once; repeated close calls are intentionally harmless."""

        object.__setattr__(self, "_state", CredentialLeaseState.CLOSED)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("CredentialLease state is controlled by close()")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("CredentialLease is immutable")


__all__ = [
    "CredentialAlias",
    "CredentialFailure",
    "CredentialFailureCode",
    "CredentialLease",
    "CredentialLeaseMetadata",
    "CredentialLeaseState",
    "CredentialPurpose",
    "CredentialRequest",
    "CredentialRotationNotice",
    "WorkloadBinding",
    "WorkloadEnvironment",
    "fail_credential",
    "require_credential_utc",
]
