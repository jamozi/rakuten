"""Closed values for the self-hosted WordPress operator bridge.

The module deliberately models only the two allowlisted mutations required by
the ST-1506 operator slice.  It cannot represent posts, publication, media,
plugins, arbitrary options, arbitrary HTTP, or arbitrary WordPress REST paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import json
from pathlib import PurePosixPath
import re
from typing import Final, NoReturn, SupportsIndex


WORDPRESS_OPERATOR_ORIGIN: Final = "https://kurashinoshirube.com"
WORDPRESS_OPERATOR_NAMESPACE: Final = "/wp-json/raos-operator/v1"
WORDPRESS_OPERATOR_EXPECTED_ROLE: Final = "raos_operator_executor"
WORDPRESS_OPERATOR_CONTRACT_VERSION: Final = 1
WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS: Final = 900
WORDPRESS_OPERATOR_THEME_SLUG: Final = "kurashinoshirube-child"
WORDPRESS_OPERATOR_THEME_FROM_VERSION: Final = "1.1.1"
WORDPRESS_OPERATOR_YOAST_VERSION: Final = "28.3"
WORDPRESS_OPERATOR_PROFILE_VERSION: Final = 1
WORDPRESS_OPERATOR_SOCIAL_IMAGE_URI: Final = (
    "https://kurashinoshirube.com/wp-content/themes/kurashinoshirube-child/"
    "assets/images/home-hero.webp"
)
WORDPRESS_OPERATOR_YOAST_ARCHIVE_BYTES: Final = 5_151_735
WORDPRESS_OPERATOR_YOAST_ARCHIVE_SHA256: Final = (
    "381edc1603147bd76af81341f21c9155ff3e9f6ce29ed20886d889fb9d6744fb"
)
WORDPRESS_OPERATOR_YOAST_CHECKSUM_FILE_COUNT: Final = 1_952

MAX_THEME_PACKAGE_BYTES: Final = 16 * 1024 * 1024
MAX_THEME_FILE_BYTES: Final = 4 * 1024 * 1024
MAX_THEME_FILES: Final = 64

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,127}\Z", re.ASCII)
_SEMVER = re.compile(
    r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z",
    re.ASCII,
)
_THEME_PATH = re.compile(r"[A-Za-z0-9._/-]{1,240}\Z", re.ASCII)
_RFC3339 = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T"
    r"(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]Z\Z",
    re.ASCII,
)

_YOAST_CHECKSUM_FAIL_CODES: Final = frozenset(
    {
        "YOAST_CHECKSUM_MISMATCH",
        "YOAST_INSTALLATION_ABSENT",
        "YOAST_INSTALLATION_UNREADABLE",
    }
)
_YOAST_CHECKSUM_UNAVAILABLE_CODES: Final = frozenset(
    {
        "YOAST_CHECKSUM_BUSY",
        "YOAST_CHECKSUM_CACHE_INVALID",
        "YOAST_CHECKSUM_INTERNAL_INVALID",
        "YOAST_OFFICIAL_CHECKSUM_INVALID",
        "YOAST_OFFICIAL_CHECKSUM_UNAVAILABLE",
    }
)


class WordPressOperatorOperation(StrEnum):
    APPLY_YOAST_PROFILE = "APPLY_YOAST_PROFILE"
    UPDATE_CHILD_THEME = "UPDATE_CHILD_THEME"


class WordPressOperatorProposalState(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    APPLYING = "APPLYING"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    NEEDS_RECOVERY = "NEEDS_RECOVERY"
    EXPIRED = "EXPIRED"


class WordPressOperatorChecksumStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class WordPressOperatorYoastProfileCode(StrEnum):
    VERSION_ABSENT = "YOAST_VERSION_ABSENT"
    VERSION_MISMATCH = "YOAST_VERSION_MISMATCH"
    PROFILE_PREREQUISITE_FAILED = "YOAST_PROFILE_PREREQUISITE_FAILED"
    PROFILE_MATCH = "YOAST_PROFILE_MATCH"
    PROFILE_MISMATCH = "YOAST_PROFILE_MISMATCH"


class WordPressOperatorThemeStateCode(StrEnum):
    ABSENT = "THEME_ABSENT"
    TREE_UNREADABLE = "THEME_TREE_UNREADABLE"
    TREE_READABLE = "THEME_TREE_READABLE"


class WordPressOperatorFailureCode(StrEnum):
    INVALID_ARGUMENT = "WORDPRESS_OPERATOR_INVALID_ARGUMENT"
    CREDENTIAL_STORE_INVALID = "WORDPRESS_OPERATOR_CREDENTIAL_STORE_INVALID"
    CREDENTIAL_METADATA_INVALID = "WORDPRESS_OPERATOR_CREDENTIAL_METADATA_INVALID"
    THEME_PACKAGE_INVALID = "WORDPRESS_OPERATOR_THEME_PACKAGE_INVALID"
    THEME_VERSION_NOT_NEWER = "WORDPRESS_OPERATOR_THEME_VERSION_NOT_NEWER"
    REQUEST_INVALID = "WORDPRESS_OPERATOR_REQUEST_INVALID"
    RESPONSE_INVALID = "WORDPRESS_OPERATOR_RESPONSE_INVALID"
    TRANSPORT_REFUSED = "WORDPRESS_OPERATOR_TRANSPORT_REFUSED"
    OUTCOME_AMBIGUOUS = "WORDPRESS_OPERATOR_OUTCOME_AMBIGUOUS"
    OPERATION_NOT_ALLOWED = "WORDPRESS_OPERATOR_OPERATION_NOT_ALLOWED"
    HUMAN_APPROVAL_REQUIRED = "WORDPRESS_OPERATOR_HUMAN_APPROVAL_REQUIRED"
    INTERNAL_FAILURE = "WORDPRESS_OPERATOR_INTERNAL_FAILURE"


class WordPressOperatorFailure(RuntimeError):
    """Sanitized failure that never embeds provider or credential material."""

    __slots__ = ("_code",)

    def __init__(self, code: WordPressOperatorFailureCode) -> None:
        if type(code) is not WordPressOperatorFailureCode:
            raise TypeError("invalid WordPress operator failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> WordPressOperatorFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"WordPressOperatorFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress operator failure serialization is disabled")


def fail_wordpress_operator(
    code: WordPressOperatorFailureCode = WordPressOperatorFailureCode.INVALID_ARGUMENT,
) -> NoReturn:
    raise WordPressOperatorFailure(code) from None


def require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_wordpress_operator()
    return value


def _require_code(value: object) -> str:
    if type(value) is not str or _CODE.fullmatch(value) is None:
        fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return value


def _require_semver(value: object) -> str:
    if type(value) is not str or _SEMVER.fullmatch(value) is None:
        fail_wordpress_operator()
    return value


def _semver_parts(value: str) -> tuple[int, int, int]:
    _require_semver(value)
    major, minor, patch = value.split(".")
    return int(major), int(minor), int(patch)


def fixed_yoast_profile() -> dict[str, object]:
    return {
        "yoast_profile": {
            "plugin_slug": "wordpress-seo",
            "version": WORDPRESS_OPERATOR_YOAST_VERSION,
            "wpseo": {
                "enable_ai_generator": False,
                "enable_headless_rest_endpoints": False,
                "enable_index_now": False,
                "enable_schema": False,
                "enable_schema_aggregation_endpoint": False,
                "enable_xml_sitemap": True,
                "google_site_kit_feature_enabled": False,
                "googleverify": "",
                "semrush_integration_active": False,
                "tracking": False,
                "wincher_integration_active": False,
            },
            "wpseo_social": {
                "og_default_image": WORDPRESS_OPERATOR_SOCIAL_IMAGE_URI,
                "og_default_image_id": "",
                "opengraph": True,
                "twitter": True,
                "twitter_card_type": "summary_large_image",
            },
        }
    }


def _require_rfc3339(value: object) -> str:
    if type(value) is not str or _RFC3339.fullmatch(value) is None:
        fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
    return value


def canonical_json_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("ascii", errors="strict")
    except TypeError, ValueError, UnicodeError, RecursionError:
        fail_wordpress_operator()


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-wordpress-operator>)"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("WordPress operator value serialization is disabled")


@dataclass(frozen=True, slots=True, repr=False)
class ThemeFileManifestEntry(_RedactedValue):
    path: str
    size: int
    sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.path) is not str
            or _THEME_PATH.fullmatch(self.path) is None
            or "\\" in self.path
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        relative = PurePosixPath(self.path)
        if (
            relative.is_absolute()
            or not relative.parts
            or relative.as_posix() != self.path
            or any(part in {"", ".", ".."} for part in relative.parts)
            or type(self.size) is not int
            or not 1 <= self.size <= MAX_THEME_FILE_BYTES
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        try:
            self.path.encode("ascii", errors="strict")
        except UnicodeError:
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        require_sha256(self.sha256)

    def payload(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


@dataclass(frozen=True, slots=True, repr=False)
class ThemePackage(_RedactedValue):
    from_version: str
    to_version: str
    package_bytes: bytes
    package_sha256: str
    file_manifest: tuple[ThemeFileManifestEntry, ...]
    slug: str = WORDPRESS_OPERATOR_THEME_SLUG

    def __post_init__(self) -> None:
        if (
            self.slug != WORDPRESS_OPERATOR_THEME_SLUG
            or type(self.package_bytes) is not bytes
            or not 1 <= len(self.package_bytes) <= MAX_THEME_PACKAGE_BYTES
            or type(self.file_manifest) is not tuple
            or not 1 <= len(self.file_manifest) <= MAX_THEME_FILES
            or any(
                type(item) is not ThemeFileManifestEntry for item in self.file_manifest
            )
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        _require_semver(self.from_version)
        _require_semver(self.to_version)
        if _semver_parts(self.to_version) <= _semver_parts(self.from_version):
            fail_wordpress_operator(
                WordPressOperatorFailureCode.THEME_VERSION_NOT_NEWER
            )
        require_sha256(self.package_sha256)
        if hashlib.sha256(self.package_bytes).hexdigest() != self.package_sha256:
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        paths = tuple(item.path for item in self.file_manifest)
        folded_paths = tuple(path.casefold() for path in paths)
        if (
            paths != tuple(sorted(paths))
            or len(paths) != len(set(paths))
            or len(folded_paths) != len(set(folded_paths))
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)

    @classmethod
    def bind(
        cls,
        *,
        from_version: str,
        to_version: str,
        package_bytes: bytes,
        file_manifest: tuple[ThemeFileManifestEntry, ...],
    ) -> ThemePackage:
        if type(package_bytes) is not bytes:
            fail_wordpress_operator(WordPressOperatorFailureCode.THEME_PACKAGE_INVALID)
        return cls(
            from_version=from_version,
            to_version=to_version,
            package_bytes=package_bytes,
            package_sha256=hashlib.sha256(package_bytes).hexdigest(),
            file_manifest=file_manifest,
        )

    def proposal_payload(self) -> dict[str, object]:
        return {
            "file_manifest": [item.payload() for item in self.file_manifest],
            "from_version": self.from_version,
            "package_sha256": self.package_sha256,
            "package_size": len(self.package_bytes),
            "slug": self.slug,
            "to_version": self.to_version,
        }


@dataclass(frozen=True, slots=True, repr=False)
class OperatorProposal(_RedactedValue):
    operation: WordPressOperatorOperation
    theme: ThemePackage | None
    request_token: str
    proposal_id: str
    ttl_seconds: int = WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS

    def __post_init__(self) -> None:
        if (
            type(self.operation) is not WordPressOperatorOperation
            or type(self.ttl_seconds) is not int
            or self.ttl_seconds != WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS
        ):
            fail_wordpress_operator()
        if self.operation is WordPressOperatorOperation.APPLY_YOAST_PROFILE:
            valid_theme = self.theme is None
        else:
            valid_theme = type(self.theme) is ThemePackage
        if not valid_theme:
            fail_wordpress_operator()
        require_sha256(self.proposal_id)
        require_sha256(self.request_token)
        if self.proposal_id != hashlib.sha256(self.canonical_bytes()).hexdigest():
            fail_wordpress_operator()

    @classmethod
    def yoast(cls, request_token: str) -> OperatorProposal:
        request_token = require_sha256(request_token)
        profile = fixed_yoast_profile()
        payload = {
            "operator_contract_version": WORDPRESS_OPERATOR_CONTRACT_VERSION,
            "operation": WordPressOperatorOperation.APPLY_YOAST_PROFILE.value,
            "profile_version": WORDPRESS_OPERATOR_PROFILE_VERSION,
            "request_token": request_token,
            "site_origin": WORDPRESS_OPERATOR_ORIGIN,
            "ttl_seconds": WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS,
            **profile,
        }
        return cls(
            operation=WordPressOperatorOperation.APPLY_YOAST_PROFILE,
            theme=None,
            request_token=request_token,
            proposal_id=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    @classmethod
    def theme_update(cls, theme: ThemePackage, request_token: str) -> OperatorProposal:
        if type(theme) is not ThemePackage:
            fail_wordpress_operator()
        request_token = require_sha256(request_token)
        payload = {
            "operator_contract_version": WORDPRESS_OPERATOR_CONTRACT_VERSION,
            "operation": WordPressOperatorOperation.UPDATE_CHILD_THEME.value,
            "profile_version": WORDPRESS_OPERATOR_PROFILE_VERSION,
            "request_token": request_token,
            "site_origin": WORDPRESS_OPERATOR_ORIGIN,
            "theme": theme.proposal_payload(),
            "ttl_seconds": WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS,
        }
        return cls(
            operation=WordPressOperatorOperation.UPDATE_CHILD_THEME,
            theme=theme,
            request_token=request_token,
            proposal_id=hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
        )

    def payload(self) -> dict[str, object]:
        value: dict[str, object] = {
            "operator_contract_version": WORDPRESS_OPERATOR_CONTRACT_VERSION,
            "operation": self.operation.value,
            "profile_version": WORDPRESS_OPERATOR_PROFILE_VERSION,
            "request_token": self.request_token,
            "site_origin": WORDPRESS_OPERATOR_ORIGIN,
            "ttl_seconds": self.ttl_seconds,
        }
        if self.operation is WordPressOperatorOperation.APPLY_YOAST_PROFILE:
            value.update(fixed_yoast_profile())
        elif self.theme is not None:
            value["theme"] = self.theme.proposal_payload()
        return value

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.payload())


@dataclass(frozen=True, slots=True, repr=False)
class OperatorThemeStatus(_RedactedValue):
    installed_version: str | None
    active: bool
    state_code: WordPressOperatorThemeStateCode
    file_count: int
    tree_sha256: str | None
    slug: str = WORDPRESS_OPERATOR_THEME_SLUG

    def __post_init__(self) -> None:
        if (
            self.slug != WORDPRESS_OPERATOR_THEME_SLUG
            or type(self.active) is not bool
            or type(self.state_code) is not WordPressOperatorThemeStateCode
            or type(self.file_count) is not int
            or not 0 <= self.file_count <= MAX_THEME_FILES
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if self.installed_version is not None and (
            type(self.installed_version) is not str
            or _SEMVER.fullmatch(self.installed_version) is None
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if self.tree_sha256 is not None:
            try:
                require_sha256(self.tree_sha256)
            except WordPressOperatorFailure:
                fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if self.state_code is WordPressOperatorThemeStateCode.ABSENT:
            valid_state = (
                self.installed_version is None
                and self.tree_sha256 is None
                and self.file_count == 0
                and self.active is False
            )
        elif self.state_code is WordPressOperatorThemeStateCode.TREE_UNREADABLE:
            valid_state = self.tree_sha256 is None and self.file_count == 0
        else:
            valid_state = (
                self.installed_version is not None
                and self.tree_sha256 is not None
                and 1 <= self.file_count <= MAX_THEME_FILES
            )
        if not valid_state:
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "active": self.active,
            "file_count": self.file_count,
            "installed_version": self.installed_version,
            "slug": self.slug,
            "state_code": self.state_code.value,
            "tree_sha256": self.tree_sha256,
        }


@dataclass(frozen=True, slots=True, repr=False)
class OperatorStatus(_RedactedValue):
    writes_enabled: bool
    yoast_profile_code: WordPressOperatorYoastProfileCode
    theme: OperatorThemeStatus
    proposal_counts: tuple[tuple[WordPressOperatorProposalState, int], ...]
    operator_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if (
            type(self.writes_enabled) is not bool
            or type(self.yoast_profile_code) is not WordPressOperatorYoastProfileCode
            or type(self.theme) is not OperatorThemeStatus
            or self.operator_version != "1.0.0"
            or type(self.proposal_counts) is not tuple
            or len(self.proposal_counts) != len(WordPressOperatorProposalState)
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        expected = tuple(WordPressOperatorProposalState)
        if tuple(state for state, _count in self.proposal_counts) != expected:
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if any(
            type(count) is not int or not 0 <= count <= (1 << 63) - 1
            for _, count in self.proposal_counts
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "operator_version": self.operator_version,
            "proposal_counts": {
                state.value: count for state, count in self.proposal_counts
            },
            "supported_operations": [item.value for item in WordPressOperatorOperation],
            "theme": self.theme.public_payload(),
            "writes_enabled": self.writes_enabled,
            "yoast_profile_code": self.yoast_profile_code.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class YoastChecksumResult(_RedactedValue):
    status: WordPressOperatorChecksumStatus
    code: str
    checked_file_count: int
    mismatch_count: int

    def __post_init__(self) -> None:
        if (
            type(self.status) is not WordPressOperatorChecksumStatus
            or type(self.code) is not str
            or type(self.checked_file_count) is not int
            or type(self.mismatch_count) is not int
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        _require_code(self.code)
        exact_pass = (
            self.status is WordPressOperatorChecksumStatus.PASS
            and self.code == "YOAST_CHECKSUM_MATCH"
            and self.checked_file_count == WORDPRESS_OPERATOR_YOAST_CHECKSUM_FILE_COUNT
            and self.mismatch_count == 0
        )
        exact_fail = (
            self.status is WordPressOperatorChecksumStatus.FAIL
            and self.code in _YOAST_CHECKSUM_FAIL_CODES
            and self.checked_file_count == WORDPRESS_OPERATOR_YOAST_CHECKSUM_FILE_COUNT
            and 1 <= self.mismatch_count <= self.checked_file_count
        )
        exact_unavailable = (
            self.status is WordPressOperatorChecksumStatus.UNAVAILABLE
            and self.code in _YOAST_CHECKSUM_UNAVAILABLE_CODES
            and self.checked_file_count == 0
            and self.mismatch_count == 0
        )
        if not (exact_pass or exact_fail or exact_unavailable):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "checked_file_count": self.checked_file_count,
            "code": self.code,
            "expected_archive": {
                "byte_length": WORDPRESS_OPERATOR_YOAST_ARCHIVE_BYTES,
                "sha256": WORDPRESS_OPERATOR_YOAST_ARCHIVE_SHA256,
                "version": WORDPRESS_OPERATOR_YOAST_VERSION,
            },
            "mismatch_count": self.mismatch_count,
            "status": self.status.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ProposalReceipt(_RedactedValue):
    proposal_id: str
    operation: WordPressOperatorOperation
    state: WordPressOperatorProposalState
    created_at: str
    expires_at: str
    replayed: bool

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        if (
            type(self.operation) is not WordPressOperatorOperation
            or type(self.state) is not WordPressOperatorProposalState
            or type(self.replayed) is not bool
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        _require_rfc3339(self.created_at)
        _require_rfc3339(self.expires_at)
        try:
            created = datetime.fromisoformat(self.created_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        except ValueError:
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        if (
            expires - created
            != timedelta(seconds=WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS)
            or self.state
            not in {
                WordPressOperatorProposalState.PROPOSED,
                WordPressOperatorProposalState.APPROVED,
                WordPressOperatorProposalState.APPLYING,
            }
            or (
                not self.replayed
                and (
                    self.state is not WordPressOperatorProposalState.PROPOSED
                    or expires <= datetime.now(timezone.utc)
                )
            )
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)

    def is_expired(self, now: datetime | None = None) -> bool:
        if now is None:
            observed = datetime.now(timezone.utc)
        elif type(now) is not datetime or now.tzinfo is None:
            fail_wordpress_operator(WordPressOperatorFailureCode.INVALID_ARGUMENT)
        else:
            observed = now
        expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
        return expires <= observed

    def public_payload(self) -> dict[str, object]:
        return {
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "operation": self.operation.value,
            "proposal_id": self.proposal_id,
            "replayed": self.replayed,
            "state": self.state.value,
        }


@dataclass(frozen=True, slots=True, repr=False)
class ApplyReceipt(_RedactedValue):
    proposal_id: str
    operation: WordPressOperatorOperation
    result_code: str
    replayed: bool
    state: WordPressOperatorProposalState = WordPressOperatorProposalState.APPLIED

    def __post_init__(self) -> None:
        require_sha256(self.proposal_id)
        if (
            type(self.operation) is not WordPressOperatorOperation
            or self.state is not WordPressOperatorProposalState.APPLIED
            or type(self.replayed) is not bool
        ):
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)
        _require_code(self.result_code)
        expected_result_code = {
            WordPressOperatorOperation.APPLY_YOAST_PROFILE: "YOAST_PROFILE_APPLIED",
            WordPressOperatorOperation.UPDATE_CHILD_THEME: "THEME_UPDATE_APPLIED",
        }[self.operation]
        if self.result_code != expected_result_code:
            fail_wordpress_operator(WordPressOperatorFailureCode.RESPONSE_INVALID)

    def public_payload(self) -> dict[str, object]:
        return {
            "operation": self.operation.value,
            "proposal_id": self.proposal_id,
            "replayed": self.replayed,
            "result_code": self.result_code,
            "state": self.state.value,
        }


__all__ = [
    "ApplyReceipt",
    "MAX_THEME_FILE_BYTES",
    "MAX_THEME_FILES",
    "MAX_THEME_PACKAGE_BYTES",
    "OperatorProposal",
    "OperatorStatus",
    "OperatorThemeStatus",
    "ProposalReceipt",
    "ThemeFileManifestEntry",
    "ThemePackage",
    "WORDPRESS_OPERATOR_CONTRACT_VERSION",
    "WORDPRESS_OPERATOR_EXPECTED_ROLE",
    "WORDPRESS_OPERATOR_NAMESPACE",
    "WORDPRESS_OPERATOR_ORIGIN",
    "WORDPRESS_OPERATOR_PROPOSAL_TTL_SECONDS",
    "WORDPRESS_OPERATOR_PROFILE_VERSION",
    "WORDPRESS_OPERATOR_SOCIAL_IMAGE_URI",
    "WORDPRESS_OPERATOR_THEME_FROM_VERSION",
    "WORDPRESS_OPERATOR_THEME_SLUG",
    "WORDPRESS_OPERATOR_YOAST_ARCHIVE_BYTES",
    "WORDPRESS_OPERATOR_YOAST_ARCHIVE_SHA256",
    "WORDPRESS_OPERATOR_YOAST_CHECKSUM_FILE_COUNT",
    "WORDPRESS_OPERATOR_YOAST_VERSION",
    "WordPressOperatorChecksumStatus",
    "WordPressOperatorFailure",
    "WordPressOperatorFailureCode",
    "WordPressOperatorOperation",
    "WordPressOperatorProposalState",
    "WordPressOperatorThemeStateCode",
    "WordPressOperatorYoastProfileCode",
    "YoastChecksumResult",
    "canonical_json_bytes",
    "fail_wordpress_operator",
    "fixed_yoast_profile",
    "require_sha256",
]
