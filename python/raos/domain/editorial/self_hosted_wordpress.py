"""Closed self-hosted WordPress draft values for ST-1703.

These values can represent only one exact draft create or ID-bound draft
update at the owner-selected site.  They carry no publication, media, theme,
plugin, taxonomy, delete, scheduling, or generic HTTP authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import json
import re
from typing import NoReturn, SupportsIndex


SELF_HOSTED_WORDPRESS_ORIGIN = "https://kurashinoshirube.com"
SELF_HOSTED_WORDPRESS_STATUS = "draft"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z", re.ASCII)
_MAX_DRAFT_ID = (1 << 63) - 1
_MAX_TITLE_CHARS = 512
_MAX_SLUG_CHARS = 200
_MAX_CONTENT_BYTES = 1_000_000


class SelfHostedWordPressOperation(StrEnum):
    CREATE_DRAFT = "CREATE_DRAFT"
    UPDATE_DRAFT = "UPDATE_DRAFT"


class SelfHostedWordPressDisposition(StrEnum):
    CREATED = "CREATED"
    UPDATED = "UPDATED"
    REPLAYED = "REPLAYED"


class SelfHostedWordPressFailureCode(StrEnum):
    INVALID_ARGUMENT = "INVALID_ARGUMENT"
    CONTENT_PACKET_INVALID = "CONTENT_PACKET_INVALID"
    AFFILIATE_LINK_NOT_READY = "AFFILIATE_LINK_NOT_READY"
    THEME_ASSET_NOT_READY = "THEME_ASSET_NOT_READY"
    CREDENTIAL_METADATA_INVALID = "CREDENTIAL_METADATA_INVALID"
    CREDENTIAL_STORE_INVALID = "CREDENTIAL_STORE_INVALID"
    CREDENTIAL_INSTALL_REFUSED = "CREDENTIAL_INSTALL_REFUSED"
    REQUEST_INVALID = "REQUEST_INVALID"
    RESPONSE_INVALID = "RESPONSE_INVALID"
    TRANSPORT_REFUSED = "TRANSPORT_REFUSED"
    OUTCOME_AMBIGUOUS = "OUTCOME_AMBIGUOUS"
    JOURNAL_INVALID = "JOURNAL_INVALID"
    JOURNAL_AMBIGUOUS = "JOURNAL_AMBIGUOUS"
    JOURNAL_MISMATCH = "JOURNAL_MISMATCH"
    OUTCOME_MISMATCH = "OUTCOME_MISMATCH"
    OPERATION_NOT_ALLOWED = "OPERATION_NOT_ALLOWED"


class SelfHostedWordPressFailure(RuntimeError):
    """Sanitized closed failure that remains compatible with context managers."""

    __slots__ = ("_code",)

    def __init__(self, code: SelfHostedWordPressFailureCode) -> None:
        if type(code) is not SelfHostedWordPressFailureCode:
            raise TypeError("invalid self-hosted WordPress failure code")
        self._code = code
        super().__init__(code.value)

    @property
    def code(self) -> SelfHostedWordPressFailureCode:
        return self._code

    def __str__(self) -> str:
        return self.code.value

    def __repr__(self) -> str:
        return f"SelfHostedWordPressFailure(code={self.code.value})"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("self-hosted WordPress failure serialization is disabled")


def fail_self_hosted_wordpress(
    code: SelfHostedWordPressFailureCode = (
        SelfHostedWordPressFailureCode.INVALID_ARGUMENT
    ),
) -> NoReturn:
    raise SelfHostedWordPressFailure(code) from None


class _RedactedValue:
    __slots__ = ()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(<redacted-self-hosted-wordpress>)"

    def __str__(self) -> str:
        return "<redacted-self-hosted-wordpress>"

    def __reduce_ex__(self, protocol: SupportsIndex) -> NoReturn:
        del protocol
        raise TypeError("self-hosted WordPress value serialization is disabled")


def _canonical_json(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8", errors="strict")
    except TypeError, ValueError, UnicodeError:
        fail_self_hosted_wordpress()


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _require_sha256(value: object) -> str:
    if type(value) is not str or _SHA256.fullmatch(value) is None:
        fail_self_hosted_wordpress()
    return value


@dataclass(frozen=True, slots=True, repr=False)
class SelfHostedWordPressDraft(_RedactedValue):
    operation: SelfHostedWordPressOperation
    title: str
    slug: str
    content_html: str
    existing_draft_id: int | None
    content_sha256: str
    operation_sha256: str

    def __post_init__(self) -> None:
        if type(self.operation) is not SelfHostedWordPressOperation:
            fail_self_hosted_wordpress()
        if (
            type(self.title) is not str
            or not 1 <= len(self.title) <= _MAX_TITLE_CHARS
            or self.title != self.title.strip()
            or any(
                ord(character) < 32 or ord(character) == 127 for character in self.title
            )
            or type(self.content_html) is not str
            or not self.content_html.strip()
            or type(self.slug) is not str
            or not 1 <= len(self.slug) <= _MAX_SLUG_CHARS
            or _SLUG.fullmatch(self.slug) is None
        ):
            fail_self_hosted_wordpress()
        try:
            content_size = len(self.content_html.encode("utf-8", errors="strict"))
            self.title.encode("utf-8", errors="strict")
            self.slug.encode("ascii", errors="strict")
        except UnicodeError:
            fail_self_hosted_wordpress()
        if not 1 <= content_size <= _MAX_CONTENT_BYTES or any(
            ord(character) < 32 and character not in "\t\n\r"
            for character in self.content_html
        ):
            fail_self_hosted_wordpress()
        if self.operation is SelfHostedWordPressOperation.CREATE_DRAFT:
            valid_target = self.existing_draft_id is None
        else:
            valid_target = (
                type(self.existing_draft_id) is int
                and 1 <= self.existing_draft_id <= _MAX_DRAFT_ID
            )
        if not valid_target:
            fail_self_hosted_wordpress()
        _require_sha256(self.content_sha256)
        _require_sha256(self.operation_sha256)
        if (
            self.content_sha256 != self._expected_content_sha256()
            or self.operation_sha256 != self._expected_operation_sha256()
        ):
            fail_self_hosted_wordpress()

    @classmethod
    def bind(
        cls,
        *,
        operation: SelfHostedWordPressOperation,
        title: str,
        slug: str,
        content_html: str,
        existing_draft_id: int | None = None,
    ) -> SelfHostedWordPressDraft:
        content_sha256 = _digest(
            {
                "content_html": content_html,
                "origin": SELF_HOSTED_WORDPRESS_ORIGIN,
                "slug": slug,
                "status": SELF_HOSTED_WORDPRESS_STATUS,
                "title": title,
            }
        )
        operation_sha256 = _digest(
            {
                "content_sha256": content_sha256,
                "existing_draft_id": existing_draft_id,
                "operation": operation.value,
            }
        )
        return cls(
            operation=operation,
            title=title,
            slug=slug,
            content_html=content_html,
            existing_draft_id=existing_draft_id,
            content_sha256=content_sha256,
            operation_sha256=operation_sha256,
        )

    def _expected_content_sha256(self) -> str:
        return _digest(
            {
                "content_html": self.content_html,
                "origin": SELF_HOSTED_WORDPRESS_ORIGIN,
                "slug": self.slug,
                "status": SELF_HOSTED_WORDPRESS_STATUS,
                "title": self.title,
            }
        )

    def _expected_operation_sha256(self) -> str:
        return _digest(
            {
                "content_sha256": self.content_sha256,
                "existing_draft_id": self.existing_draft_id,
                "operation": self.operation.value,
            }
        )


@dataclass(frozen=True, slots=True, repr=False)
class SelfHostedWordPressDraftReceipt(_RedactedValue):
    draft_id: int
    operation: SelfHostedWordPressOperation
    disposition: SelfHostedWordPressDisposition
    status: str
    content_sha256: str
    operation_sha256: str
    response_sha256: str
    publication_authorized: bool = False
    production_eligible: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.draft_id) is not int
            or not 1 <= self.draft_id <= _MAX_DRAFT_ID
            or type(self.operation) is not SelfHostedWordPressOperation
            or type(self.disposition) is not SelfHostedWordPressDisposition
            or self.status != SELF_HOSTED_WORDPRESS_STATUS
            or self.publication_authorized is not False
            or self.production_eligible is not False
        ):
            fail_self_hosted_wordpress(SelfHostedWordPressFailureCode.OUTCOME_MISMATCH)
        for value in (
            self.content_sha256,
            self.operation_sha256,
            self.response_sha256,
        ):
            _require_sha256(value)


__all__ = [
    "SELF_HOSTED_WORDPRESS_ORIGIN",
    "SELF_HOSTED_WORDPRESS_STATUS",
    "SelfHostedWordPressDisposition",
    "SelfHostedWordPressDraft",
    "SelfHostedWordPressDraftReceipt",
    "SelfHostedWordPressFailure",
    "SelfHostedWordPressFailureCode",
    "SelfHostedWordPressOperation",
    "fail_self_hosted_wordpress",
]
