"""Human-bound Phase 3 publication package without publication authority.

The contract deliberately stops at a semantic seal.  It can represent the
result of a real human review, but it cannot create a WordPress request or move
content into a public state.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from html import escape as escape_html_attribute
from html.parser import HTMLParser
import re
from types import MappingProxyType
from typing import Final, Mapping, cast
import unicodedata

from raos.domain.decision_support_v2.models import (
    ClaimStatus,
    ClaimType,
    FreshnessState,
    RiskClass,
)
from raos.domain.decision_support_v2.publication import (
    ClaimEvidenceBinding,
    PublicationPackage,
    PublicationState,
    semantic_digest,
)

PHASE3_CONTRACT_SCHEMA: Final = "RAOS_V2_PHASE3_PUBLICATION_PACKAGE_V1"
PHASE3_CONTRACT_VERSION: Final = "1.0.0"
PHASE3_TARGET_ORIGIN: Final = "https://kurashinoshirube.com"
PHASE3_TARGET_ROUTE: Final = "/carry-on-suitcase-comparison/"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MACHINE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z", re.ASCII)
_POST_NAME = "carry-on-suitcase-comparison"
_WORDPRESS_EXPORT_SCHEMA = "RAOS_V2_WORDPRESS_EXPORT_BINDING_V2"
_WORDPRESS_EXPORT_VERSION = "2.0.0"
_PREACTION_SCHEMA = "RAOS_V2_PHASE3_PREACTION_BINDING_V1"
_PREACTION_VERSION = "1.0.0"
_PREACTION_PROVENANCE = "PUBLIC_READ_ONLY_CAPTURE_AND_OWNER_WORDPRESS_EXPORT"
_PLAIN_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);", re.I)
_FORBIDDEN_POST_TAG = re.compile(r"<\s*/?\s*(?:script|h1|html|head|img)\b", re.I)
_HREF = re.compile(r"""\bhref\s*=\s*["']([^"']+)["']""", re.I)
_CTA_STATE = re.compile(r"""\bdata-raos-v2-cta-state\s*=\s*["']([^"']+)["']""", re.I)
_PACKAGE_MARKER = 'data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"'
_DISCLOSURE_MARKER = 'class="raos-v2-decision-support__disclosure"'
_DISCLOSURE_LABEL = 'aria-label="広告表示"'
_STRUCTURED_DATA_SCHEMA = "RAOS_V2_PHASE3_STRUCTURED_DATA_EXPECTATION_V1"
_STRUCTURED_DATA_VERSION = "1.0.0"
_STRUCTURED_DATA_DERIVATION = "EXACT_WORDPRESS_FIELDS_V1"
_STRUCTURED_DATA_EMISSION_OWNER = "EXTERNAL_WORDPRESS_SEO_CONFIGURATION"
_STRUCTURED_DATA_EXTERNAL_STATUS = "UNVERIFIED_EXTERNAL"
_STRUCTURED_DATA_TYPES: Final = (
    "Article",
    "BreadcrumbList",
    "Organization",
    "WebSite",
)
_HTML_ENTITY = re.compile(r"&(?:#[0-9]+|#x[0-9a-f]+|[a-z][a-z0-9]+);", re.I)
_HTML_CLASS_LIST = re.compile(
    r"(?:raos-v2-[a-z0-9_-]+|is-blocked)" r"(?: (?:raos-v2-[a-z0-9_-]+|is-blocked))*\Z",
    re.ASCII,
)
_HTML_ID = re.compile(r"raos-v2-[a-z0-9-]+\Z", re.ASCII)
_HTML_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z", re.ASCII)
_HTML_INTERNAL_PATH = re.compile(
    r"/(?:[a-z0-9][a-z0-9-]*/)*\Z",
    re.ASCII,
)
_OFFICIAL_SOURCE_HREFS: Final = frozenset(
    {
        "https://store.ace.jp/shop/g/g06316-01/",
        "https://store.ace.jp/shop/g/g05721-04",
        "https://store.ace.jp/shop/g/g01471-02",
    }
)
_HTML_PRODUCT_ID = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)+\Z", re.ASCII)
_ALLOWED_HTML_ATTRIBUTES: Final[Mapping[str, frozenset[str]]] = MappingProxyType(
    {
        "a": frozenset({"href"}),
        "article": frozenset({"class", "data-raos-v2-evidence", "aria-labelledby"}),
        "aside": frozenset({"class", "aria-label"}),
        "button": frozenset({"type", "disabled", "aria-disabled"}),
        "caption": frozenset(),
        "dd": frozenset(),
        "div": frozenset(
            {
                "class",
                "data-raos-v2-package-marker",
                "data-raos-v2-article-id",
                "data-raos-v2-claim-state",
                "data-raos-v2-cta-state",
                "role",
                "aria-label",
                "tabindex",
            }
        ),
        "dl": frozenset({"class"}),
        "dt": frozenset(),
        "h2": frozenset({"id"}),
        "h3": frozenset({"id"}),
        "h4": frozenset(),
        "header": frozenset({"class"}),
        "li": frozenset(),
        "nav": frozenset({"class", "aria-label"}),
        "p": frozenset({"class", "data-raos-v2-evidence"}),
        "section": frozenset(
            {
                "class",
                "aria-labelledby",
                "data-raos-v2-product-id",
                "data-raos-v2-result-state",
            }
        ),
        "span": frozenset({"class"}),
        "strong": frozenset(),
        "table": frozenset(),
        "tbody": frozenset(),
        "td": frozenset(),
        "th": frozenset({"scope"}),
        "thead": frozenset(),
        "time": frozenset({"datetime"}),
        "tr": frozenset({"data-raos-v2-evidence"}),
        "ul": frozenset(),
    }
)


class Phase3PublicationState(StrEnum):
    """The only states available to the local Phase 3 package."""

    HUMAN_REVIEWED = "HUMAN_REVIEWED"
    PACKAGE_SEALED = "PACKAGE_SEALED"


class Phase3WordPressIntent(StrEnum):
    """The one local intent allowed for the preserved published route."""

    UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER = (
        "UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER"
    )


class Phase3PreActionStatus(StrEnum):
    """Whether current public state was verified before final human review."""

    HISTORICAL_BASELINE_ONLY = "HISTORICAL_BASELINE_ONLY"
    VERIFIED_PREACTION = "VERIFIED_PREACTION"


class Phase3WordPressExportRole(StrEnum):
    """Non-interchangeable roles for before/after WordPress exports."""

    PRE_WRITE_EXPORT = "PRE_WRITE_EXPORT"
    POST_ACTION_OWNER_EXPORT = "POST_ACTION_OWNER_EXPORT"


def _require_bool(value: object, field_name: str) -> None:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be boolean")


def _require_sha256(value: object, field_name: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")
    return value


def _require_nonblank(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"{field_name} must be a nonblank string")
    return value


def _has_forbidden_unicode(value: str, *, allow_layout: bool) -> bool:
    allowed_controls: set[str] = {"\t", "\n", "\r"} if allow_layout else set()
    return any(
        character not in allowed_controls
        and unicodedata.category(character) in {"Cc", "Cf", "Cs"}
        for character in value
    )


def _require_plain_text(
    value: object, field_name: str, *, allow_empty: bool = False
) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise ValueError(f"{field_name} must be plain text")
    if (
        any(character in value for character in "<>[]")
        or _PLAIN_ENTITY.search(value) is not None
        or _has_forbidden_unicode(value, allow_layout=False)
    ):
        raise ValueError(f"{field_name} contains forbidden markup or controls")
    return value


def _validate_phase3_html_attribute(tag: str, name: str, value: str | None) -> None:
    """Validate one decoded attribute from the closed Phase 3 projection."""

    if name == "disabled":
        if tag != "button" or value is not None:
            raise ValueError("post_content has an invalid boolean attribute")
        return
    if value is None or _has_forbidden_unicode(value, allow_layout=False):
        raise ValueError("post_content has an invalid attribute value")
    if name == "class":
        accepted = _HTML_CLASS_LIST.fullmatch(value) is not None
    elif name in {"id", "aria-labelledby"}:
        accepted = _HTML_ID.fullmatch(value) is not None
    elif name == "href":
        accepted = (
            _HTML_INTERNAL_PATH.fullmatch(value) is not None
            or value in _OFFICIAL_SOURCE_HREFS
        )
    elif name == "datetime":
        accepted = _HTML_DATE.fullmatch(value) is not None
    elif name == "data-raos-v2-package-marker":
        accepted = value == "RAOS_V2_A05_POST_CONTENT_V1"
    elif name == "data-raos-v2-article-id":
        accepted = value == "A05"
    elif name == "data-raos-v2-evidence":
        accepted = value in {"A_OFFICIAL_FACT", "D_EDITORIAL_JUDGEMENT"}
    elif name == "data-raos-v2-product-id":
        accepted = _HTML_PRODUCT_ID.fullmatch(value) is not None
    elif name == "data-raos-v2-claim-state":
        accepted = value == "UNKNOWN"
    elif name == "data-raos-v2-cta-state":
        accepted = value == "BLOCKED"
    elif name == "data-raos-v2-result-state":
        accepted = value == "UNKNOWN"
    elif name == "role":
        accepted = value in {"region", "status"}
    elif name == "tabindex":
        accepted = value == "0"
    elif name == "scope":
        accepted = value in {"col", "row"}
    elif name == "type":
        accepted = tag == "button" and value == "button"
    elif name == "aria-disabled":
        accepted = tag == "button" and value == "true"
    elif name == "aria-label":
        accepted = bool(value.strip()) and all(
            character not in value for character in "<>"
        )
    else:  # pragma: no cover - every allowed attribute is handled above
        accepted = False
    if not accepted:
        raise ValueError("post_content has a forbidden attribute value")


class _Phase3ProjectionHTMLParser(HTMLParser):
    """Fail-closed parser for the exact non-executable projection vocabulary."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._stack: list[str] = []
        self.top_level_count = 0
        self.root_marker_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        allowed = _ALLOWED_HTML_ATTRIBUTES.get(tag)
        if allowed is None:
            raise ValueError("post_content has a forbidden HTML element")
        names = [name for name, _value in attrs]
        if len(names) != len(set(names)) or not set(names).issubset(allowed):
            raise ValueError("post_content has duplicate or forbidden attributes")
        decoded = dict(attrs)
        for name, value in attrs:
            _validate_phase3_html_attribute(tag, name, value)
        canonical_start_tag = "<" + tag
        for name, value in attrs:
            canonical_start_tag += (
                f" {name}"
                if value is None
                else f' {name}="{escape_html_attribute(value, quote=True)}"'
            )
        canonical_start_tag += ">"
        if self.get_starttag_text() != canonical_start_tag:
            raise ValueError("post_content attributes must use canonical HTML syntax")
        if not self._stack:
            self.top_level_count += 1
            if (
                self.top_level_count != 1
                or tag != "div"
                or decoded.get("data-raos-v2-package-marker")
                != "RAOS_V2_A05_POST_CONTENT_V1"
            ):
                raise ValueError("post_content must have one marked root element")
        if decoded.get("data-raos-v2-package-marker") is not None:
            self.root_marker_count += 1
        self._stack.append(tag)

    def handle_endtag(self, tag: str) -> None:
        if not self._stack or self._stack[-1] != tag:
            raise ValueError("post_content HTML must be explicitly balanced")
        self._stack.pop()

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag, attrs
        raise ValueError("post_content does not allow self-closing elements")

    def handle_entityref(self, name: str) -> None:
        del name
        raise ValueError("post_content does not allow character references")

    def handle_charref(self, name: str) -> None:
        del name
        raise ValueError("post_content does not allow character references")

    def handle_comment(self, data: str) -> None:
        del data
        raise ValueError("post_content does not allow comments")

    def handle_decl(self, decl: str) -> None:
        del decl
        raise ValueError("post_content does not allow declarations")

    def handle_pi(self, data: str) -> None:
        del data
        raise ValueError("post_content does not allow processing instructions")

    def unknown_decl(self, data: str) -> None:
        del data
        raise ValueError("post_content does not allow unknown declarations")

    def assert_complete(self) -> None:
        if self._stack or self.top_level_count != 1 or self.root_marker_count != 1:
            raise ValueError("post_content must be one complete marked subtree")


def _validate_post_content(value: str) -> None:
    if _has_forbidden_unicode(value, allow_layout=True):
        raise ValueError("post_content contains forbidden controls")
    if "[" in value or "]" in value:
        raise ValueError("post_content does not allow shortcode delimiters")
    folded = value.casefold()
    if (
        _FORBIDDEN_POST_TAG.search(value) is not None
        or "hb.afl.rakuten.co.jp" in folded
        or "a.r10.to" in folded
        or "affiliate" in folded
        or "data-raos-v2-offer" in folded
    ):
        raise ValueError("post_content contains forbidden executable or affiliate HTML")
    if value.count(_PACKAGE_MARKER) != 1:
        raise ValueError("post_content must contain the exact package marker once")
    if value.count(_DISCLOSURE_MARKER) != 1 or value.count(_DISCLOSURE_LABEL) != 1:
        raise ValueError("post_content must contain the exact disclosure marker once")
    cta_states = _CTA_STATE.findall(value)
    if cta_states != ["BLOCKED", "BLOCKED", "BLOCKED"]:
        raise ValueError("post_content must contain exactly three BLOCKED CTAs")
    if any(
        (
            _HTML_INTERNAL_PATH.fullmatch(href) is None
            and href not in _OFFICIAL_SOURCE_HREFS
        )
        or href.startswith("//")
        for href in _HREF.findall(value)
    ):
        raise ValueError(
            "post_content links must remain internal or exact official sources"
        )
    if _HTML_ENTITY.search(value) is not None:
        raise ValueError("post_content contains forbidden character references")
    parser = _Phase3ProjectionHTMLParser()
    try:
        parser.feed(value)
        parser.close()
        parser.assert_complete()
    except (AssertionError, RecursionError) as error:
        raise ValueError("post_content is not valid closed projection HTML") from error


@dataclass(frozen=True, slots=True)
class Phase3ClaimBinding:
    """Canonical authority for one claim from the Phase 2 real candidate."""

    claim_id: str
    claim_type: ClaimType
    risk_class: RiskClass
    freshness: FreshnessState
    authoritative_source_status: ClaimStatus
    checked_at: datetime
    next_review_at: datetime

    def __post_init__(self) -> None:
        if (
            not self.claim_id.startswith("CLM-")
            or _MACHINE_ID.fullmatch(self.claim_id) is None
        ):
            raise ValueError("invalid Phase 3 claim ID")
        if type(self.claim_type) is not ClaimType:
            raise ValueError("invalid Phase 3 claim type")
        if type(self.risk_class) is not RiskClass:
            raise ValueError("invalid Phase 3 claim risk class")
        if type(self.freshness) is not FreshnessState:
            raise ValueError("invalid Phase 3 claim freshness")
        if type(self.authoritative_source_status) is not ClaimStatus:
            raise ValueError("invalid authoritative Phase 3 claim source status")
        if (
            self.checked_at.tzinfo is None
            or self.checked_at.utcoffset() is None
            or self.next_review_at.tzinfo is None
            or self.next_review_at.utcoffset() is None
        ):
            raise ValueError("Phase 3 claim authority times must be timezone-aware")
        if self.next_review_at <= self.checked_at:
            raise ValueError("Phase 3 claim next review must follow its check time")

    @property
    def resolved(self) -> bool:
        """Derive resolution exclusively from canonical type and source status."""

        return (
            self.claim_type is not ClaimType.UNKNOWN
            and self.authoritative_source_status is ClaimStatus.VERIFIED
        )

    @property
    def blocking(self) -> bool:
        """Derive blocking exclusively from canonical type and source status."""

        if self.claim_type is ClaimType.UNKNOWN:
            return self.authoritative_source_status is not ClaimStatus.BLOCKED
        return self.authoritative_source_status is not ClaimStatus.VERIFIED

    @property
    def intentionally_disclosed(self) -> bool:
        """Only an authoritative BLOCKED UNKNOWN is safe to disclose as unknown."""

        return (
            self.claim_type is ClaimType.UNKNOWN
            and self.authoritative_source_status is ClaimStatus.BLOCKED
        )

    def seal_blocker(self, *, reviewed_at: datetime) -> str | None:
        """Return a stable blocker code, or ``None`` when seal-safe."""

        if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
            raise ValueError("Phase 3 claim review time must be timezone-aware")
        prefix = f"{self.claim_id}:"
        if reviewed_at < self.checked_at:
            return prefix + "CLAIM_CHECKED_AFTER_REVIEW"
        if reviewed_at >= self.next_review_at:
            if self.claim_type is ClaimType.A_OFFICIAL_FACT:
                return prefix + "OFFICIAL_FACT_AUTHORITY_EXPIRED"
            if self.claim_type is ClaimType.D_EDITORIAL_JUDGEMENT:
                return prefix + "EDITORIAL_JUDGEMENT_AUTHORITY_EXPIRED"
            return prefix + "UNKNOWN_DISCLOSURE_AUTHORITY_EXPIRED"
        if self.claim_type is ClaimType.A_OFFICIAL_FACT:
            if not self.resolved:
                return prefix + "OFFICIAL_FACT_UNRESOLVED"
            if self.freshness not in {FreshnessState.FRESH, FreshnessState.DUE}:
                return prefix + "OFFICIAL_FACT_NONFRESH"
            if self.blocking:
                return prefix + "CLAIM_BLOCKING"
            return None
        if self.claim_type is ClaimType.D_EDITORIAL_JUDGEMENT:
            if not self.resolved:
                return prefix + "EDITORIAL_JUDGEMENT_UNRESOLVED"
            if self.freshness not in {FreshnessState.FRESH, FreshnessState.DUE}:
                return prefix + "EDITORIAL_JUDGEMENT_NONFRESH"
            if self.blocking:
                return prefix + "CLAIM_BLOCKING"
            return None
        if self.claim_type is ClaimType.UNKNOWN:
            if (
                self.resolved
                or self.blocking
                or not self.intentionally_disclosed
                or self.freshness
                not in {FreshnessState.UNKNOWN, FreshnessState.UNAVAILABLE}
            ):
                return prefix + "UNKNOWN_NOT_SAFELY_DISCLOSED"
            return None

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type.value,
            "risk_class": self.risk_class.value,
            "freshness": self.freshness.value,
            "authoritative_source_status": self.authoritative_source_status.value,
            "checked_at": self.checked_at.isoformat(),
            "next_review_at": self.next_review_at.isoformat(),
            "resolved": self.resolved,
            "blocking": self.blocking,
            "intentionally_disclosed": self.intentionally_disclosed,
        }

    def to_authority_record(self) -> Mapping[str, str]:
        """Return only fields controlled by the canonical claim authority."""

        return {
            "claim_id": self.claim_id,
            "claim_type": self.claim_type.value,
            "risk_class": self.risk_class.value,
            "freshness": self.freshness.value,
            "authoritative_source_status": self.authoritative_source_status.value,
            "checked_at": self.checked_at.isoformat(),
            "next_review_at": self.next_review_at.isoformat(),
        }


def phase3_claim_authority_payload(
    bindings: tuple[Phase3ClaimBinding, ...],
) -> Mapping[str, object]:
    """Build the closed canonical authority payload bound by Phase 2."""

    if not bindings or any(
        type(binding) is not Phase3ClaimBinding for binding in bindings
    ):
        raise ValueError("Phase 3 claim authority bindings must be nonempty")
    if len({binding.claim_id for binding in bindings}) != len(bindings):
        raise ValueError("Phase 3 claim authority IDs must be unique")
    return {
        "schema": "RAOS_V2_PHASE3_CLAIM_AUTHORITY_V1",
        "version": PHASE3_CONTRACT_VERSION,
        "claims": [
            dict(binding.to_authority_record())
            for binding in sorted(bindings, key=lambda item: item.claim_id)
        ],
    }


def phase3_claim_authority_digest(
    bindings: tuple[Phase3ClaimBinding, ...],
) -> str:
    """Digest claim classification, status and review times canonically."""

    return semantic_digest(phase3_claim_authority_payload(bindings))


@dataclass(frozen=True, slots=True)
class Phase3PreActionBinding:
    """Verified public capture and owner export observed before final review."""

    captured_at: datetime
    post_id: int
    current_public_body_sha256: str
    public_capture_sha256: str
    wordpress_export_sha256: str
    wordpress_export_bytes: int
    owner_evidence_sha256: str
    legacy_post_content_sha256: str
    schema: str = _PREACTION_SCHEMA
    version: str = _PREACTION_VERSION
    status: Phase3PreActionStatus = Phase3PreActionStatus.VERIFIED_PREACTION
    provenance: str = _PREACTION_PROVENANCE
    target_origin: str = PHASE3_TARGET_ORIGIN
    target_route: str = PHASE3_TARGET_ROUTE
    target_kind: str = "EXISTING_POST"
    exact_match_count: int = 1

    def __post_init__(self) -> None:
        if self.schema != _PREACTION_SCHEMA or self.version != _PREACTION_VERSION:
            raise ValueError("invalid Phase 3 preaction schema or version")
        if (
            type(self.status) is not Phase3PreActionStatus
            or self.status is not Phase3PreActionStatus.VERIFIED_PREACTION
            or self.provenance != _PREACTION_PROVENANCE
        ):
            raise ValueError("Phase 3 preaction provenance is not verified")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("Phase 3 preaction captured_at must be timezone-aware")
        if type(self.post_id) is not int or self.post_id < 1:
            raise ValueError("Phase 3 preaction post_id must be positive")
        if (
            type(self.wordpress_export_bytes) is not int
            or self.wordpress_export_bytes < 1
        ):
            raise ValueError("Phase 3 preaction export bytes must be positive")
        for field_name in (
            "current_public_body_sha256",
            "public_capture_sha256",
            "wordpress_export_sha256",
            "owner_evidence_sha256",
            "legacy_post_content_sha256",
        ):
            _require_sha256(getattr(self, field_name), field_name)
        if (
            self.target_origin != PHASE3_TARGET_ORIGIN
            or self.target_route != PHASE3_TARGET_ROUTE
            or self.target_kind != "EXISTING_POST"
            or type(self.exact_match_count) is not int
            or self.exact_match_count != 1
        ):
            raise ValueError("ambiguous or unexpected Phase 3 preaction target")

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "status": self.status.value,
            "provenance": self.provenance,
            "captured_at": self.captured_at.isoformat(),
            "target": {
                "origin": self.target_origin,
                "route": self.target_route,
                "kind": self.target_kind,
                "post_id": self.post_id,
                "exact_match_count": self.exact_match_count,
            },
            "current_public_body_sha256": self.current_public_body_sha256,
            "public_capture_sha256": self.public_capture_sha256,
            "wordpress_export_sha256": self.wordpress_export_sha256,
            "wordpress_export_bytes": self.wordpress_export_bytes,
            "owner_evidence_sha256": self.owner_evidence_sha256,
            "legacy_post_content_sha256": self.legacy_post_content_sha256,
        }

    @property
    def binding_digest(self) -> str:
        return semantic_digest(self.to_contract_record())

    def verify_integrity(self) -> bool:
        try:
            replace(self)
        except AttributeError, TypeError, ValueError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Phase3WordPressUpdateFields:
    """Closed WordPress fields whose exact values are reviewed and sealed."""

    post_title: str
    post_content: str
    post_excerpt: str
    meta_description: str
    post_name: str = _POST_NAME
    post_status: str = "publish"
    comment_status: str = "closed"
    ping_status: str = "closed"
    canonical_url: str = PHASE3_TARGET_ORIGIN + PHASE3_TARGET_ROUTE

    def __post_init__(self) -> None:
        _require_plain_text(self.post_title, "post_title")
        _require_nonblank(self.post_content, "post_content")
        _validate_post_content(self.post_content)
        _require_plain_text(self.post_excerpt, "post_excerpt", allow_empty=True)
        _require_plain_text(self.meta_description, "meta_description")
        if self.post_name != _POST_NAME:
            raise ValueError("post_name conflicts with the preserved Phase 3 route")
        if self.post_status != "publish":
            raise ValueError("Phase 3 WordPress update must preserve published status")
        if self.comment_status != "closed" or self.ping_status != "closed":
            raise ValueError("comments and pings must remain closed")
        if self.canonical_url != PHASE3_TARGET_ORIGIN + PHASE3_TARGET_ROUTE:
            raise ValueError("canonical URL conflicts with the preserved route")

    def to_contract_record(self) -> Mapping[str, str]:
        return {
            "canonical_url": self.canonical_url,
            "comment_status": self.comment_status,
            "meta_description": self.meta_description,
            "ping_status": self.ping_status,
            "post_content": self.post_content,
            "post_excerpt": self.post_excerpt,
            "post_name": self.post_name,
            "post_status": self.post_status,
            "post_title": self.post_title,
        }


WORDPRESS_FIELD_NAMES: Final = tuple(Phase3WordPressUpdateFields.__dataclass_fields__)


def wordpress_field_digest(field_name: str, value: object) -> str:
    """Hash a WordPress field name and value to prevent field substitution."""

    if field_name not in WORDPRESS_FIELD_NAMES or not isinstance(value, str):
        raise ValueError("invalid WordPress field digest input")
    return semantic_digest({"field": field_name, "value": value})


@dataclass(frozen=True, slots=True)
class Phase3StructuredDataExpectation:
    """Exact JSON-LD graph derived only from the reviewed WordPress fields."""

    headline: str
    description: str
    canonical_url: str
    target_origin: str = PHASE3_TARGET_ORIGIN
    schema: str = _STRUCTURED_DATA_SCHEMA
    version: str = _STRUCTURED_DATA_VERSION
    derivation: str = _STRUCTURED_DATA_DERIVATION
    json_ld_script_count: int = 1
    json_ld_document_count: int = 1
    emission_owner: str = _STRUCTURED_DATA_EMISSION_OWNER
    external_configuration_status: str = _STRUCTURED_DATA_EXTERNAL_STATUS
    local_json_ld_emission: bool = False

    def __post_init__(self) -> None:
        _require_plain_text(self.headline, "structured_data.headline")
        _require_plain_text(self.description, "structured_data.description")
        if (
            self.schema != _STRUCTURED_DATA_SCHEMA
            or self.version != _STRUCTURED_DATA_VERSION
            or self.derivation != _STRUCTURED_DATA_DERIVATION
            or type(self.json_ld_script_count) is not int
            or self.json_ld_script_count != 1
            or type(self.json_ld_document_count) is not int
            or self.json_ld_document_count != 1
            or self.emission_owner != _STRUCTURED_DATA_EMISSION_OWNER
            or self.external_configuration_status != _STRUCTURED_DATA_EXTERNAL_STATUS
            or type(self.local_json_ld_emission) is not bool
            or self.local_json_ld_emission
        ):
            raise ValueError("invalid Phase 3 structured-data contract")
        if (
            self.target_origin != PHASE3_TARGET_ORIGIN
            or self.canonical_url != PHASE3_TARGET_ORIGIN + PHASE3_TARGET_ROUTE
        ):
            raise ValueError("structured data conflicts with the preserved route")

    @classmethod
    def from_wordpress_fields(
        cls, fields: Phase3WordPressUpdateFields
    ) -> Phase3StructuredDataExpectation:
        """Create the only supported graph without accepting an untyped mapping."""

        if type(fields) is not Phase3WordPressUpdateFields:
            raise ValueError("structured data requires exact WordPress update fields")
        return cls(
            headline=fields.post_title,
            description=fields.meta_description,
            canonical_url=fields.canonical_url,
        )

    def json_ld_document(self) -> Mapping[str, object]:
        """Return a fresh closed graph; no caller-owned mapping is retained."""

        canonical = self.canonical_url
        origin = self.target_origin + "/"
        return {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "Article",
                    "headline": self.headline,
                    "description": self.description,
                    "mainEntityOfPage": {"@id": canonical},
                    "url": canonical,
                },
                {
                    "@type": "BreadcrumbList",
                    "itemListElement": [
                        {
                            "@type": "ListItem",
                            "position": 1,
                            "name": self.headline,
                            "item": canonical,
                        }
                    ],
                },
                {"@type": "Organization", "url": origin},
                {"@type": "WebSite", "url": origin},
            ],
        }

    def semantic_payload(self) -> Mapping[str, object]:
        """Match the public capture's canonical ``documents`` digest envelope."""

        return {"documents": [dict(self.json_ld_document())]}

    @property
    def json_ld_sha256(self) -> str:
        return semantic_digest(self.semantic_payload())

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "derivation": self.derivation,
            "json_ld_script_count": self.json_ld_script_count,
            "json_ld_document_count": self.json_ld_document_count,
            "json_ld_types": list(_STRUCTURED_DATA_TYPES),
            "emission": {
                "owner": self.emission_owner,
                "local_json_ld_emission": self.local_json_ld_emission,
                "external_configuration_status": (self.external_configuration_status),
            },
            "documents": [dict(self.json_ld_document())],
            "json_ld_sha256": self.json_ld_sha256,
        }

    def verify_integrity(self) -> bool:
        try:
            replace(self)
        except AttributeError, TypeError, ValueError:
            return False
        return self.json_ld_sha256 == semantic_digest(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class Phase3WordPressUpdatePayload:
    """Exact local-only update for one existing published post at cutover."""

    fields: Phase3WordPressUpdateFields
    expected_public_body_sha256: str
    intent: Phase3WordPressIntent = (
        Phase3WordPressIntent.UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER
    )
    target_origin: str = PHASE3_TARGET_ORIGIN
    target_route: str = PHASE3_TARGET_ROUTE
    target_kind: str = "EXISTING_POST"
    expected_existing_post_count: int = 1
    expected_current_post_status: str = "publish"
    required_after_post_status: str = "publish"
    preaction_binding: Phase3PreActionBinding | None = None

    def __post_init__(self) -> None:
        if type(self.fields) is not Phase3WordPressUpdateFields:
            raise ValueError("invalid WordPress update fields")
        Phase3StructuredDataExpectation.from_wordpress_fields(self.fields)
        _require_sha256(self.expected_public_body_sha256, "expected_public_body_sha256")
        if (
            type(self.intent) is not Phase3WordPressIntent
            or self.intent
            is not Phase3WordPressIntent.UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER
        ):
            raise ValueError("ambiguous or forbidden WordPress intent")
        if (
            self.target_origin != PHASE3_TARGET_ORIGIN
            or self.target_route != PHASE3_TARGET_ROUTE
            or self.target_kind != "EXISTING_POST"
            or type(self.expected_existing_post_count) is not int
            or self.expected_existing_post_count != 1
        ):
            raise ValueError("ambiguous or unexpected WordPress target")
        if (
            self.expected_current_post_status != "publish"
            or self.required_after_post_status != "publish"
            or self.fields.post_status != "publish"
        ):
            raise ValueError("Phase 3 cutover must preserve publish status")
        if self.preaction_binding is not None:
            binding = self.preaction_binding
            if (
                type(binding) is not Phase3PreActionBinding
                or not binding.verify_integrity()
                or binding.target_origin != self.target_origin
                or binding.target_route != self.target_route
                or binding.target_kind != self.target_kind
                or binding.exact_match_count != self.expected_existing_post_count
                or binding.current_public_body_sha256
                != self.expected_public_body_sha256
            ):
                raise ValueError("invalid verified Phase 3 preaction binding")

    @property
    def preaction_status(self) -> Phase3PreActionStatus:
        if self.preaction_binding is None:
            return Phase3PreActionStatus.HISTORICAL_BASELINE_ONLY
        return self.preaction_binding.status

    @property
    def preaction_binding_digest(self) -> str | None:
        if self.preaction_binding is None:
            return None
        return self.preaction_binding.binding_digest

    @property
    def structured_data_expectation(self) -> Phase3StructuredDataExpectation:
        """Derive rather than accept the sealed JSON-LD expectation."""

        return Phase3StructuredDataExpectation.from_wordpress_fields(self.fields)

    @property
    def structured_data_expectation_sha256(self) -> str:
        return self.structured_data_expectation.json_ld_sha256

    def bind_verified_preaction(
        self, binding: Phase3PreActionBinding
    ) -> Phase3WordPressUpdatePayload:
        """Return a new payload bound to the freshly observed public body."""

        if (
            type(binding) is not Phase3PreActionBinding
            or not binding.verify_integrity()
        ):
            raise ValueError("invalid verified Phase 3 preaction binding")
        return replace(
            self,
            expected_public_body_sha256=binding.current_public_body_sha256,
            preaction_binding=binding,
        )

    def preaction_seal_blocker(self) -> str | None:
        binding = self.preaction_binding
        if binding is None:
            return "PREACTION_BINDING_MISSING_OR_HISTORICAL_BASELINE_ONLY"
        if (
            not binding.verify_integrity()
            or self.preaction_status is not Phase3PreActionStatus.VERIFIED_PREACTION
            or self.preaction_binding_digest != binding.binding_digest
            or self.expected_public_body_sha256 != binding.current_public_body_sha256
        ):
            return "PREACTION_BINDING_INVALID"
        return None

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": "RAOS_V2_PHASE3_WORDPRESS_UPDATE_PAYLOAD_V1",
            "version": PHASE3_CONTRACT_VERSION,
            "intent": self.intent.value,
            "target": {
                "origin": self.target_origin,
                "route": self.target_route,
                "kind": self.target_kind,
                "expected_match_count": self.expected_existing_post_count,
                "expected_public_body_sha256": self.expected_public_body_sha256,
            },
            "preconditions": {
                "expected_current_post_status": self.expected_current_post_status,
            },
            "postconditions": {
                "required_after_post_status": self.required_after_post_status,
            },
            "structured_data_expectation": dict(
                self.structured_data_expectation.to_contract_record()
            ),
            "preaction": {
                "status": self.preaction_status.value,
                "binding_digest": self.preaction_binding_digest,
                "binding": (
                    None
                    if self.preaction_binding is None
                    else dict(self.preaction_binding.to_contract_record())
                ),
            },
            "fields": dict(self.fields.to_contract_record()),
        }

    @property
    def payload_digest(self) -> str:
        return semantic_digest(self.to_contract_record())


@dataclass(frozen=True, slots=True)
class Phase3WordPressExportBinding:
    """Sanitized proof binding the exact existing published WordPress post."""

    captured_at: datetime
    post_id: int
    field_hashes: Mapping[str, str]
    public_body_sha256: str
    preaction_binding_sha256: str
    export_sha256: str
    export_bytes: int
    restore_artifact_sha256: str
    theme_artifact_sha256: str
    seo_state_sha256: str
    redirect_map_sha256: str
    sitemap_state_sha256: str
    schema: str = _WORDPRESS_EXPORT_SCHEMA
    version: str = _WORDPRESS_EXPORT_VERSION
    target_origin: str = PHASE3_TARGET_ORIGIN
    target_route: str = PHASE3_TARGET_ROUTE
    target_kind: str = "EXISTING_POST"
    exact_match_count: int = 1
    raw_export_location: str = "OWNER_STORAGE_ONLY_NOT_GIT"
    status: str = "VERIFIED_HUMAN_EXPORT"
    export_role: Phase3WordPressExportRole = Phase3WordPressExportRole.PRE_WRITE_EXPORT

    def __post_init__(self) -> None:
        if (
            self.schema != _WORDPRESS_EXPORT_SCHEMA
            or self.version != _WORDPRESS_EXPORT_VERSION
        ):
            raise ValueError("invalid WordPress export binding schema or version")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("WordPress export captured_at must be timezone-aware")
        if type(self.post_id) is not int or self.post_id < 1:
            raise ValueError("WordPress export post_id must be a positive integer")
        if type(self.export_bytes) is not int or self.export_bytes < 1:
            raise ValueError("WordPress export bytes must be a positive integer")
        if (
            self.target_origin != PHASE3_TARGET_ORIGIN
            or self.target_route != PHASE3_TARGET_ROUTE
            or self.target_kind != "EXISTING_POST"
            or type(self.exact_match_count) is not int
            or self.exact_match_count != 1
        ):
            raise ValueError("ambiguous or unexpected WordPress export target")
        if (
            self.raw_export_location != "OWNER_STORAGE_ONLY_NOT_GIT"
            or self.status != "VERIFIED_HUMAN_EXPORT"
            or type(self.export_role) is not Phase3WordPressExportRole
        ):
            raise ValueError("WordPress export is not a verified owner-held export")
        digest_fields = (
            "export_sha256",
            "preaction_binding_sha256",
            "public_body_sha256",
            "restore_artifact_sha256",
            "theme_artifact_sha256",
            "seo_state_sha256",
            "redirect_map_sha256",
            "sitemap_state_sha256",
        )
        for field_name in digest_fields:
            _require_sha256(getattr(self, field_name), field_name)
        raw_field_hashes = cast(Mapping[object, object], self.field_hashes)
        normalized_field_hashes: dict[str, str] = {}
        for name, value in raw_field_hashes.items():
            if (
                not isinstance(name, str)
                or not isinstance(value, str)
                or _SHA256.fullmatch(value) is None
            ):
                raise ValueError(
                    "WordPress export field hashes are incomplete or invalid"
                )
            normalized_field_hashes[name] = value
        if set(normalized_field_hashes) != set(WORDPRESS_FIELD_NAMES):
            raise ValueError("WordPress export field hashes are incomplete or invalid")
        if normalized_field_hashes["post_status"] != wordpress_field_digest(
            "post_status", "publish"
        ):
            raise ValueError("WordPress export current post status must be publish")
        object.__setattr__(
            self, "field_hashes", MappingProxyType(normalized_field_hashes)
        )

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": self.schema,
            "version": self.version,
            "target": {
                "origin": self.target_origin,
                "route": self.target_route,
                "kind": self.target_kind,
                "post_id": self.post_id,
                "exact_match_count": self.exact_match_count,
            },
            "captured_at": self.captured_at.isoformat(),
            "field_hashes": dict(sorted(self.field_hashes.items())),
            "public_body_sha256": self.public_body_sha256,
            "preaction_binding_sha256": self.preaction_binding_sha256,
            "export_sha256": self.export_sha256,
            "export_bytes": self.export_bytes,
            "restore_artifact_sha256": self.restore_artifact_sha256,
            "theme_artifact_sha256": self.theme_artifact_sha256,
            "seo_state_sha256": self.seo_state_sha256,
            "redirect_map_sha256": self.redirect_map_sha256,
            "sitemap_state_sha256": self.sitemap_state_sha256,
            "raw_export_location": self.raw_export_location,
            "status": self.status,
            "export_role": self.export_role.value,
        }

    @property
    def binding_digest(self) -> str:
        return semantic_digest(self.to_contract_record())

    def verify_integrity(self) -> bool:
        """Re-run the closed constructor after any possible object/map mutation."""

        try:
            replace(self)
        except AttributeError, TypeError, ValueError:
            return False
        return True


@dataclass(frozen=True, slots=True)
class Phase3HumanReviewReceipt:
    """Content-free owner assertion bound to a payload, not authenticated approval."""

    reviewer_id: str
    reviewed_at: datetime
    review_version: str
    correction_count: int
    accepted: bool
    synthetic: bool
    candidate_digest: str
    payload_digest: str
    target_route: str
    assertion_status: str = "UNAUTHENTICATED_OWNER_ASSERTION"
    acceptance_authority: bool = False

    def __post_init__(self) -> None:
        if self.reviewer_id != "OWNER_ASSERTION_LOCAL":
            raise ValueError(
                "reviewer ID must be the fixed non-personal assertion class"
            )
        if self.review_version != "P3-OWNER-ASSERTION-V1":
            raise ValueError(
                "review version must be the fixed owner assertion contract"
            )
        if self.reviewed_at.tzinfo is None or self.reviewed_at.utcoffset() is None:
            raise ValueError("reviewed_at must be timezone-aware")
        if type(self.correction_count) is not int or self.correction_count < 0:
            raise ValueError("correction_count must be a non-negative integer")
        _require_bool(self.accepted, "accepted")
        _require_bool(self.synthetic, "synthetic")
        if not self.accepted or self.synthetic:
            raise ValueError("Phase 3 seal needs an accepted non-synthetic review")
        _require_sha256(self.candidate_digest, "candidate_digest")
        _require_sha256(self.payload_digest, "payload_digest")
        if self.target_route != PHASE3_TARGET_ROUTE:
            raise ValueError("review receipt route conflicts with Phase 3 target")
        if self.assertion_status != "UNAUTHENTICATED_OWNER_ASSERTION":
            raise ValueError(
                "review receipt assertion status must remain unauthenticated"
            )
        _require_bool(self.acceptance_authority, "acceptance_authority")
        if self.acceptance_authority:
            raise ValueError("unsigned owner assertion has no acceptance authority")

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": "RAOS_V2_PHASE3_HUMAN_REVIEW_RECEIPT_V1",
            "version": PHASE3_CONTRACT_VERSION,
            "reviewer_id": self.reviewer_id,
            "reviewed_at": self.reviewed_at.isoformat(),
            "review_version": self.review_version,
            "correction_count": self.correction_count,
            "accepted": self.accepted,
            "synthetic": self.synthetic,
            "candidate_digest": self.candidate_digest,
            "payload_digest": self.payload_digest,
            "target_route": self.target_route,
            "assertion_status": self.assertion_status,
            "acceptance_authority": self.acceptance_authority,
        }


@dataclass(frozen=True, slots=True)
class Phase3ReviewCandidate:
    """Exact bridge from the generated Phase 2 real-content candidate."""

    phase2_candidate: PublicationPackage
    claim_bindings: tuple[Phase3ClaimBinding, ...]
    update_payload: Phase3WordPressUpdatePayload
    candidate_digest: str
    payload_digest: str

    def __post_init__(self) -> None:
        if type(self.phase2_candidate) is not PublicationPackage:
            raise ValueError("Phase 3 must start from a Phase 2 publication candidate")
        candidate = self.phase2_candidate
        if (
            candidate.synthetic
            or candidate.state is not PublicationState.EVIDENCE_COMPLETE
            or candidate.review_binding is not None
            or candidate.package_digest is not None
        ):
            raise ValueError("Phase 3 needs an unsealed real Phase 2 candidate")
        if (
            candidate.target_origin != PHASE3_TARGET_ORIGIN
            or candidate.target_route != PHASE3_TARGET_ROUTE
        ):
            raise ValueError("Phase 2 candidate route is not the Phase 3 target")
        if type(self.update_payload) is not Phase3WordPressUpdatePayload:
            raise ValueError("invalid Phase 3 WordPress payload")
        if self.update_payload.target_route != candidate.target_route:
            raise ValueError("candidate and WordPress payload routes differ")
        _require_sha256(self.candidate_digest, "candidate_digest")
        _require_sha256(self.payload_digest, "payload_digest")
        if self.candidate_digest != semantic_digest(candidate.to_contract_record()):
            raise ValueError("Phase 2 candidate digest is invalid")
        if self.payload_digest != self.update_payload.payload_digest:
            raise ValueError("WordPress payload digest is invalid")
        if not self.claim_bindings or any(
            type(binding) is not Phase3ClaimBinding for binding in self.claim_bindings
        ):
            raise ValueError("Phase 3 claim bindings must be nonempty")
        bound_by_id = {binding.claim_id: binding for binding in self.claim_bindings}
        phase2_by_id = {
            binding.claim_id: binding for binding in candidate.claim_evidence
        }
        if (
            len(bound_by_id) != len(self.claim_bindings)
            or set(bound_by_id) != set(phase2_by_id)
            or any(
                binding.freshness is not phase2_by_id[claim_id].freshness
                or binding.risk_class is not phase2_by_id[claim_id].risk_class
                for claim_id, binding in bound_by_id.items()
            )
        ):
            raise ValueError("Phase 3 claim bindings do not close Phase 2 evidence")
        expected_authority_digest = candidate.input_hashes.get("phase3_claim_authority")
        if (
            expected_authority_digest is None
            or expected_authority_digest
            != phase3_claim_authority_digest(self.claim_bindings)
        ):
            raise ValueError(
                "Phase 3 claim authority does not match the Phase 2 binding"
            )

    @classmethod
    def from_phase2(
        cls,
        *,
        candidate: PublicationPackage,
        claim_bindings: tuple[Phase3ClaimBinding, ...],
        update_payload: Phase3WordPressUpdatePayload,
    ) -> Phase3ReviewCandidate:
        return cls(
            phase2_candidate=candidate,
            claim_bindings=claim_bindings,
            update_payload=update_payload,
            candidate_digest=semantic_digest(candidate.to_contract_record()),
            payload_digest=update_payload.payload_digest,
        )

    def is_current(self) -> bool:
        return (
            self.candidate_digest
            == semantic_digest(self.phase2_candidate.to_contract_record())
            and self.payload_digest == self.update_payload.payload_digest
            and self.phase2_candidate.input_hashes.get("phase3_claim_authority")
            == phase3_claim_authority_digest(self.claim_bindings)
            and self._claim_authority_is_current()
        )

    def _claim_authority_is_current(self) -> bool:
        """Recheck IDs, risk and freshness against Phase 2 evidence."""

        evidence: tuple[ClaimEvidenceBinding, ...] = (
            self.phase2_candidate.claim_evidence
        )
        by_id = {item.claim_id: item for item in evidence}
        if (
            len(by_id) != len(evidence)
            or len({item.claim_id for item in self.claim_bindings})
            != len(self.claim_bindings)
            or set(by_id) != {item.claim_id for item in self.claim_bindings}
        ):
            return False
        return all(
            item.freshness is by_id[item.claim_id].freshness
            and item.risk_class is by_id[item.claim_id].risk_class
            for item in self.claim_bindings
        )

    def seal_blockers(self, *, reviewed_at: datetime | None = None) -> tuple[str, ...]:
        effective_review_time = reviewed_at or self.phase2_candidate.created_at
        claim_blockers = tuple(
            blocker
            for binding in sorted(self.claim_bindings, key=lambda item: item.claim_id)
            if (blocker := binding.seal_blocker(reviewed_at=effective_review_time))
            is not None
        )
        preaction_blocker = self.update_payload.preaction_seal_blocker()
        if preaction_blocker is None:
            return claim_blockers
        return (preaction_blocker, *claim_blockers)

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            "schema": "RAOS_V2_PHASE3_REVIEW_CANDIDATE_V1",
            "version": PHASE3_CONTRACT_VERSION,
            "phase2_candidate": dict(self.phase2_candidate.to_contract_record()),
            "candidate_digest": self.candidate_digest,
            "claim_bindings": [
                dict(binding.to_contract_record())
                for binding in sorted(
                    self.claim_bindings, key=lambda item: item.claim_id
                )
            ],
            "update_payload": dict(self.update_payload.to_contract_record()),
            "preaction_status": self.update_payload.preaction_status.value,
            "preaction_binding_digest": (self.update_payload.preaction_binding_digest),
            "structured_data_expectation_sha256": (
                self.update_payload.structured_data_expectation_sha256
            ),
            "payload_digest": self.payload_digest,
        }

    def bind_review(
        self, receipt: Phase3HumanReviewReceipt
    ) -> Phase3PublicationPackage:
        return Phase3PublicationPackage.bind(self, receipt)


@dataclass(frozen=True, slots=True)
class Phase3PublicationPackage:
    """A reviewed or sealed package; neither state carries write authority."""

    review_candidate: Phase3ReviewCandidate
    review_receipt: Phase3HumanReviewReceipt
    state: Phase3PublicationState
    package_digest: str | None = None

    def __post_init__(self) -> None:
        if type(self.review_candidate) is not Phase3ReviewCandidate:
            raise ValueError("invalid Phase 3 review candidate")
        if type(self.review_receipt) is not Phase3HumanReviewReceipt:
            raise ValueError("invalid Phase 3 human review receipt")
        if type(self.state) is not Phase3PublicationState:
            raise ValueError("invalid Phase 3 package state")
        candidate = self.review_candidate
        receipt = self.review_receipt
        preaction = candidate.update_payload.preaction_binding
        if not candidate.is_current():
            raise ValueError("review candidate has semantic drift")
        if (
            receipt.candidate_digest != candidate.candidate_digest
            or receipt.payload_digest != candidate.payload_digest
            or receipt.target_route != candidate.phase2_candidate.target_route
            or receipt.reviewed_at < candidate.phase2_candidate.created_at
            or (preaction is not None and receipt.reviewed_at < preaction.captured_at)
        ):
            raise ValueError("human review receipt does not bind the exact candidate")
        if self.state is Phase3PublicationState.HUMAN_REVIEWED:
            if self.package_digest is not None:
                raise ValueError("only a sealed Phase 3 package has a digest")
        elif self.state is Phase3PublicationState.PACKAGE_SEALED:
            _require_sha256(self.package_digest, "package_digest")
            if self.package_digest != semantic_digest(self.semantic_payload()):
                raise ValueError("Phase 3 package seal is invalid")

    @classmethod
    def bind(
        cls,
        candidate: Phase3ReviewCandidate,
        receipt: Phase3HumanReviewReceipt,
    ) -> Phase3PublicationPackage:
        return cls(
            review_candidate=candidate,
            review_receipt=receipt,
            state=Phase3PublicationState.HUMAN_REVIEWED,
        )

    @property
    def target_origin(self) -> str:
        return self.review_candidate.phase2_candidate.target_origin

    @property
    def target_route(self) -> str:
        return self.review_candidate.phase2_candidate.target_route

    def semantic_payload(self) -> Mapping[str, object]:
        return {
            "schema": PHASE3_CONTRACT_SCHEMA,
            "version": PHASE3_CONTRACT_VERSION,
            "state": self.state.value,
            "review_candidate": dict(self.review_candidate.to_contract_record()),
            "human_review_receipt": dict(self.review_receipt.to_contract_record()),
            "simulation_only": True,
            "approval_acceptance_authority": False,
            "structured_data_expectation_sha256": (
                self.review_candidate.update_payload.structured_data_expectation_sha256
            ),
            "capabilities": {
                "network": False,
                "wordpress_write": False,
                "publish": False,
            },
        }

    def to_contract_record(self) -> Mapping[str, object]:
        return {
            **self.semantic_payload(),
            "package_digest": self.package_digest,
        }

    def seal(self) -> Phase3PublicationPackage:
        if self.state is not Phase3PublicationState.HUMAN_REVIEWED:
            raise ValueError("only a human-reviewed package can be sealed")
        if not self.review_candidate.is_current():
            raise ValueError("semantic drift invalidates human review")
        blockers = self.review_candidate.seal_blockers(
            reviewed_at=self.review_receipt.reviewed_at
        )
        if blockers:
            raise ValueError(
                "claim evidence blocks Phase 3 seal: " + ",".join(blockers)
            )
        payload = dict(self.semantic_payload())
        payload["state"] = Phase3PublicationState.PACKAGE_SEALED.value
        return replace(
            self,
            state=Phase3PublicationState.PACKAGE_SEALED,
            package_digest=semantic_digest(payload),
        )

    def verify_seal(self, *, as_of: datetime | None = None) -> bool:
        effective_time = as_of or self.review_receipt.reviewed_at
        if effective_time.tzinfo is None or effective_time.utcoffset() is None:
            raise ValueError("Phase 3 seal verification time must be timezone-aware")
        return (
            self.state is Phase3PublicationState.PACKAGE_SEALED
            and self.review_candidate.is_current()
            and effective_time >= self.review_receipt.reviewed_at
            and not self.review_candidate.seal_blockers(reviewed_at=effective_time)
            and self.package_digest is not None
            and self.package_digest == semantic_digest(self.semantic_payload())
        )


__all__ = [
    "PHASE3_CONTRACT_SCHEMA",
    "PHASE3_CONTRACT_VERSION",
    "PHASE3_TARGET_ORIGIN",
    "PHASE3_TARGET_ROUTE",
    "WORDPRESS_FIELD_NAMES",
    "Phase3ClaimBinding",
    "Phase3HumanReviewReceipt",
    "Phase3PreActionBinding",
    "Phase3PreActionStatus",
    "Phase3PublicationPackage",
    "Phase3PublicationState",
    "Phase3ReviewCandidate",
    "Phase3StructuredDataExpectation",
    "Phase3WordPressExportBinding",
    "Phase3WordPressExportRole",
    "Phase3WordPressIntent",
    "Phase3WordPressUpdateFields",
    "Phase3WordPressUpdatePayload",
    "phase3_claim_authority_digest",
    "phase3_claim_authority_payload",
    "wordpress_field_digest",
]
