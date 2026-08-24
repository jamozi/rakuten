"""Provider-neutral identity values for the ST-0401 authentication boundary."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import re
from typing import NoReturn, Self, SupportsIndex, final
from urllib.parse import urlsplit


_BASE64URL_32 = re.compile(r"^[A-Za-z0-9_-]{43}$")
_PKCE_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_AUTHORIZATION_CODE = re.compile(r"^[A-Za-z0-9._~+/=-]{16,512}$")
_SUBJECT = re.compile(r"^[\x21-\x7e]{1,255}$")
_MAX_AUTHORIZATION_LIFETIME = timedelta(minutes=10)
_MAX_SESSION_LIFETIME = timedelta(hours=12)
_REDACTED = "<redacted-authentication-value>"


class AuthenticationFailureCode(str, Enum):
    """Stable, sanitized authentication failure classifications."""

    MALFORMED_INPUT = "MALFORMED_INPUT"
    ENTROPY_FAILURE = "ENTROPY_FAILURE"
    AUTHORIZATION_COLLISION = "AUTHORIZATION_COLLISION"
    AUTHORIZATION_UNKNOWN = "AUTHORIZATION_UNKNOWN"
    AUTHORIZATION_EXPIRED = "AUTHORIZATION_EXPIRED"
    AUTHORIZATION_REPLAY = "AUTHORIZATION_REPLAY"
    STATE_MISMATCH = "STATE_MISMATCH"
    NONCE_MISMATCH = "NONCE_MISMATCH"
    PKCE_UNSUPPORTED = "PKCE_UNSUPPORTED"
    PKCE_MISMATCH = "PKCE_MISMATCH"
    CODE_UNKNOWN = "CODE_UNKNOWN"
    CODE_EXPIRED = "CODE_EXPIRED"
    CODE_REPLAY = "CODE_REPLAY"
    SESSION_COLLISION = "SESSION_COLLISION"
    SESSION_UNKNOWN = "SESSION_UNKNOWN"
    SESSION_REVOKED = "SESSION_REVOKED"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    SESSION_CONFLICT = "SESSION_CONFLICT"
    DEVELOPMENT_ONLY = "DEVELOPMENT_ONLY"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    STORAGE_FAILURE = "STORAGE_FAILURE"
    STORAGE_COMMIT_UNKNOWN = "STORAGE_COMMIT_UNKNOWN"


@final
class AuthenticationFailure(RuntimeError):
    """Immutable typed failure that never retains rejected authentication data."""

    __slots__ = ("_code", "_sealed")
    _code: AuthenticationFailureCode
    _sealed: bool

    def __init__(self, code: AuthenticationFailureCode) -> None:
        if type(code) is not AuthenticationFailureCode:
            raise TypeError("code must be an exact AuthenticationFailureCode")
        super().__init__(code.value)
        object.__setattr__(self, "_code", code)
        object.__setattr__(self, "_sealed", True)

    @property
    def code(self) -> AuthenticationFailureCode:
        return self._code

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("AuthenticationFailure is immutable")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if getattr(self, "_sealed", False):
            raise AttributeError("AuthenticationFailure is immutable")
        super().__delattr__(name)

    def __repr__(self) -> str:
        return f"AuthenticationFailure(code={self.code!r})"


def _fail(code: AuthenticationFailureCode) -> NoReturn:
    raise AuthenticationFailure(code) from None


def require_utc(value: object) -> datetime:
    """Return one normalized aware UTC timestamp or fail without echoing input."""

    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timezone.utc.utcoffset(None)
    ):
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    return value.replace(tzinfo=timezone.utc)


def _encode_32_bytes(value: object) -> str:
    if type(value) is not bytes or len(value) != 32:
        _fail(AuthenticationFailureCode.ENTROPY_FAILURE)
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _require_base64url_32(value: object) -> str:
    if type(value) is not str or _BASE64URL_32.fullmatch(value) is None:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    decoded: bytes | None = None
    try:
        decoded = base64.urlsafe_b64decode(value + "=")
    except ValueError, UnicodeError:
        pass
    if decoded is None or len(decoded) != 32 or _encode_32_bytes(decoded) != value:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    return value


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({_REDACTED})"

    def __str__(self) -> str:
        return _REDACTED

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("authentication value serialization is not supported")


@dataclass(frozen=True, slots=True, repr=False)
class _Base64Url32(_RedactedValue):
    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_value", _require_base64url_32(self._value))

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        return cls(_encode_32_bytes(value))

    def reveal(self) -> str:
        """Expose the protocol value only at an explicit adapter boundary."""

        return self._value

    def fingerprint(self) -> str:
        return hashlib.sha256(self._value.encode("ascii")).hexdigest()


@final
class AuthorizationState(_Base64Url32):
    """A canonical 256-bit OAuth state value."""

    __slots__ = ()


@final
class OidcNonce(_Base64Url32):
    """A canonical 256-bit OpenID Connect nonce."""

    __slots__ = ()


@final
class PkceChallenge(_Base64Url32):
    """An exact SHA-256 PKCE challenge without base64 padding."""

    __slots__ = ()


@final
class SessionId(_Base64Url32):
    """An opaque 256-bit application session identifier."""

    __slots__ = ()


@dataclass(frozen=True, slots=True, repr=False)
class PkceVerifier(_RedactedValue):
    """An RFC 7636 verifier; only S256 derivation is exposed."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self._value) is not str
            or _PKCE_VERIFIER.fullmatch(self._value) is None
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        return cls(_encode_32_bytes(value))

    def reveal(self) -> str:
        return self._value

    def s256_challenge(self) -> PkceChallenge:
        digest = hashlib.sha256(self._value.encode("ascii")).digest()
        return PkceChallenge.from_bytes(digest)


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationCode(_RedactedValue):
    """A bounded opaque authorization code accepted at the provider port."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if (
            type(self._value) is not str
            or _AUTHORIZATION_CODE.fullmatch(self._value) is None
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)

    @classmethod
    def from_bytes(cls, value: bytes) -> Self:
        return cls(_encode_32_bytes(value))

    def reveal(self) -> str:
        return self._value

    def fingerprint(self) -> str:
        return hashlib.sha256(self._value.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True, repr=False)
class RedirectUri(_RedactedValue):
    """A fixed absolute callback URI with credentials and fragments forbidden."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        value = self._value
        valid = (
            type(value) is str and 1 <= len(value) <= 2048 and value == value.strip()
        )
        parsed = None
        if valid:
            try:
                parsed = urlsplit(value)
            except ValueError:
                pass
        if (
            parsed is None
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or any(
                ord(character) < 0x21 or ord(character) > 0x7E for character in value
            )
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if parsed.scheme != "https" and not (parsed.scheme == "http" and loopback):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)

    def reveal(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True, repr=False)
class Issuer(_RedactedValue):
    """A strict HTTPS issuer identifier."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        value = self._value
        parsed = None
        if type(value) is str and 1 <= len(value) <= 2048 and value == value.strip():
            try:
                parsed = urlsplit(value)
            except ValueError:
                pass
        if (
            parsed is None
            or parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(
                ord(character) < 0x21 or ord(character) > 0x7E for character in value
            )
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)

    def reveal(self) -> str:
        return self._value


@dataclass(frozen=True, slots=True, repr=False)
class Subject(_RedactedValue):
    """A bounded, provider-issued subject identifier."""

    _value: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self._value) is not str or _SUBJECT.fullmatch(self._value) is None:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)

    def reveal(self) -> str:
        return self._value


class PkceMethod(str, Enum):
    """The only PKCE method accepted by ST-0401."""

    S256 = "S256"


@dataclass(frozen=True, slots=True, repr=False)
class PrincipalIdentity(_RedactedValue):
    """Sanitized identity claims allowed across the inward provider boundary."""

    issuer: Issuer
    subject: Subject
    display_name: str = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.issuer) is not Issuer or type(self.subject) is not Subject:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        if (
            type(self.display_name) is not str
            or not 1 <= len(self.display_name) <= 128
            or self.display_name != self.display_name.strip()
            or any(not character.isprintable() for character in self.display_name)
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationRequest(_RedactedValue):
    """Provider-neutral Authorization Code request state."""

    state: AuthorizationState
    nonce: OidcNonce
    pkce_challenge: PkceChallenge
    pkce_method: PkceMethod
    redirect_uri: RedirectUri
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.state) is not AuthorizationState
            or type(self.nonce) is not OidcNonce
            or type(self.pkce_challenge) is not PkceChallenge
            or type(self.pkce_method) is not PkceMethod
            or self.pkce_method is not PkceMethod.S256
            or type(self.redirect_uri) is not RedirectUri
        ):
            _fail(AuthenticationFailureCode.PKCE_UNSUPPORTED)
        created_at = require_utc(self.created_at)
        expires_at = require_utc(self.expires_at)
        if not created_at < expires_at <= created_at + _MAX_AUTHORIZATION_LIFETIME:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationCallback(_RedactedValue):
    """Strict callback values received after provider authorization."""

    state: AuthorizationState
    code: AuthorizationCode

    def __post_init__(self) -> None:
        if (
            type(self.state) is not AuthorizationState
            or type(self.code) is not AuthorizationCode
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)


@dataclass(frozen=True, slots=True, repr=False)
class AuthorizationTransaction(_RedactedValue):
    """Stored single-use correlation state; raw OAuth state is not retained."""

    state_fingerprint: str = field(repr=False)
    nonce: OidcNonce
    verifier: PkceVerifier
    redirect_uri: RedirectUri
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        if (
            type(self.state_fingerprint) is not str
            or len(self.state_fingerprint) != 64
            or any(
                character not in "0123456789abcdef"
                for character in self.state_fingerprint
            )
            or type(self.nonce) is not OidcNonce
            or type(self.verifier) is not PkceVerifier
            or type(self.redirect_uri) is not RedirectUri
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        created_at = require_utc(self.created_at)
        expires_at = require_utc(self.expires_at)
        consumed_at = (
            None if self.consumed_at is None else require_utc(self.consumed_at)
        )
        if not created_at < expires_at <= created_at + _MAX_AUTHORIZATION_LIFETIME:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        if consumed_at is not None and consumed_at < created_at:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "consumed_at", consumed_at)


@dataclass(frozen=True, slots=True, repr=False)
class Session(_RedactedValue):
    """Transport-neutral bounded application session state."""

    session_id: SessionId
    principal: PrincipalIdentity
    created_at: datetime
    last_seen_at: datetime
    idle_expires_at: datetime
    absolute_expires_at: datetime
    rotated_from: SessionId | None = field(default=None, repr=False)
    revoked_at: datetime | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            type(self.session_id) is not SessionId
            or type(self.principal) is not PrincipalIdentity
            or (
                self.rotated_from is not None
                and type(self.rotated_from) is not SessionId
            )
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        created_at = require_utc(self.created_at)
        last_seen_at = require_utc(self.last_seen_at)
        idle_expires_at = require_utc(self.idle_expires_at)
        absolute_expires_at = require_utc(self.absolute_expires_at)
        revoked_at = None if self.revoked_at is None else require_utc(self.revoked_at)
        if not (
            created_at
            <= last_seen_at
            < idle_expires_at
            <= absolute_expires_at
            <= created_at + _MAX_SESSION_LIFETIME
        ):
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        if revoked_at is not None and revoked_at < created_at:
            _fail(AuthenticationFailureCode.MALFORMED_INPUT)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "last_seen_at", last_seen_at)
        object.__setattr__(self, "idle_expires_at", idle_expires_at)
        object.__setattr__(self, "absolute_expires_at", absolute_expires_at)
        object.__setattr__(self, "revoked_at", revoked_at)

    def require_active(self, now: datetime) -> None:
        observed_at = require_utc(now)
        if self.revoked_at is not None:
            _fail(AuthenticationFailureCode.SESSION_REVOKED)
        if (
            observed_at >= self.idle_expires_at
            or observed_at >= self.absolute_expires_at
        ):
            _fail(AuthenticationFailureCode.SESSION_EXPIRED)


def snapshot_principal_identity(value: object) -> PrincipalIdentity:
    """Return an exact detached principal or reject collaborator mutation."""

    if type(value) is not PrincipalIdentity:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return PrincipalIdentity(
            issuer=Issuer(value.issuer.reveal()),
            subject=Subject(value.subject.reveal()),
            display_name=value.display_name,
        )
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


def snapshot_authorization_request(value: object) -> AuthorizationRequest:
    """Detach a request before it crosses a mutable collaborator boundary."""

    if type(value) is not AuthorizationRequest:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return AuthorizationRequest(
            state=AuthorizationState(value.state.reveal()),
            nonce=OidcNonce(value.nonce.reveal()),
            pkce_challenge=PkceChallenge(value.pkce_challenge.reveal()),
            pkce_method=value.pkce_method,
            redirect_uri=RedirectUri(value.redirect_uri.reveal()),
            created_at=value.created_at,
            expires_at=value.expires_at,
        )
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


def snapshot_authorization_callback(value: object) -> AuthorizationCallback:
    """Detach callback state and code from caller-owned object identity."""

    if type(value) is not AuthorizationCallback:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return AuthorizationCallback(
            state=AuthorizationState(value.state.reveal()),
            code=AuthorizationCode(value.code.reveal()),
        )
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


def snapshot_authorization_transaction(
    value: object,
) -> AuthorizationTransaction:
    """Detach one persisted authorization revision from collaborator state."""

    if type(value) is not AuthorizationTransaction:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return AuthorizationTransaction(
            state_fingerprint=value.state_fingerprint,
            nonce=OidcNonce(value.nonce.reveal()),
            verifier=PkceVerifier(value.verifier.reveal()),
            redirect_uri=RedirectUri(value.redirect_uri.reveal()),
            created_at=value.created_at,
            expires_at=value.expires_at,
            consumed_at=value.consumed_at,
        )
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


def snapshot_session_id(value: object) -> SessionId:
    """Detach an opaque identifier before handing it to a collaborator."""

    if type(value) is not SessionId:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return SessionId(value.reveal())
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


def snapshot_session(value: object) -> Session:
    """Return a deep, exact session value with no shared nested identity."""

    if type(value) is not Session:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)
    try:
        return Session(
            session_id=snapshot_session_id(value.session_id),
            principal=snapshot_principal_identity(value.principal),
            created_at=value.created_at,
            last_seen_at=value.last_seen_at,
            idle_expires_at=value.idle_expires_at,
            absolute_expires_at=value.absolute_expires_at,
            rotated_from=(
                None
                if value.rotated_from is None
                else snapshot_session_id(value.rotated_from)
            ),
            revoked_at=value.revoked_at,
        )
    except AuthenticationFailure:
        raise
    except Exception:
        _fail(AuthenticationFailureCode.MALFORMED_INPUT)


__all__ = [
    "AuthenticationFailure",
    "AuthenticationFailureCode",
    "AuthorizationCallback",
    "AuthorizationCode",
    "AuthorizationRequest",
    "AuthorizationState",
    "AuthorizationTransaction",
    "Issuer",
    "OidcNonce",
    "PkceChallenge",
    "PkceMethod",
    "PkceVerifier",
    "PrincipalIdentity",
    "RedirectUri",
    "Session",
    "SessionId",
    "Subject",
    "require_utc",
    "snapshot_authorization_callback",
    "snapshot_authorization_request",
    "snapshot_authorization_transaction",
    "snapshot_principal_identity",
    "snapshot_session",
    "snapshot_session_id",
]
