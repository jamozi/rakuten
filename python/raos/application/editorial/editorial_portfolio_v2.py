"""Editorial V2 portfolio contracts and exact affiliate materialization.

The tracked portfolio contains identities and policy only. Provider responses,
affiliate destinations, image URLs, and image bytes remain owner-private and are
read only while a local preview or a production document is materialized.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from html import escape
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, Literal, Mapping, NoReturn, cast
import unicodedata
from urllib.parse import parse_qs, urlsplit

from raos.adapters.self_hosted_editorial_pilot_json import (
    read_rakuten_product_evidence,
)
from raos.adapters import self_hosted_editorial_rakuten_capture as identity_capture
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    RakutenProductEvidence,
)


PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
MANUFACTURER_SALES_STATE_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/manufacturer-sales-state.v1.json"
)
STATUS_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-portfolio-v2/product-evidence-status.v2.json"
)
JAN_EVIDENCE_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-portfolio-v2/product-jan-evidence.v1.json"
)
JAN_EVIDENCE_SNAPSHOT_RELATIVE_ROOT: Final = Path(
    ".secrets/editorial-portfolio-v2/jan-evidence"
)
RAKUTEN_PRIVATE_RELATIVE_PATH: Final = Path(
    ".secrets/st1704-self-hosted-editorial-pilot/rakuten"
)
LOCAL_MEDIA_RELATIVE_PATH: Final = Path(
    ".secrets/wordpress-local-preview/product-media"
)
LOCAL_FIXTURE_RELATIVE_PATH: Final = Path(
    ".secrets/wordpress-local-preview/materialized-fixtures-v2"
)
PRODUCTION_FIXTURE_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-portfolio-v2/production-materialized-fixtures-v2"
)
SOURCE_FIXTURE_RELATIVE_PATH: Final = Path(
    "changes/wordpress-local-preview-v1/fixtures"
)

PORTFOLIO_SCHEMA: Final = "RAOS_EDITORIAL_PORTFOLIO_V2"
TARGET_ORIGIN: Final = "https://kurashinoshirube.com"
MANUFACTURER_SALES_STATE_SCHEMA: Final = "RAOS_MANUFACTURER_SALES_STATE_AUDIT_V1"
MANUFACTURER_SALES_STATE_SNAPSHOT_KIND: Final = (
    "STRUCTURED_OFFICIAL_SALES_STATE_SNAPSHOT_V1"
)
MANUFACTURER_SALES_STATE_HASH_FIELDS: Final = (
    "checked_at_utc",
    "product_id",
    "state",
    "availability_scope",
    "official_url",
    "status_evidence_urls",
    "locator",
    "basis",
    "variant_caveat",
    "alternative",
)
STATUS_SCHEMA: Final = "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2"
JAN_EVIDENCE_SCHEMA: Final = "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_JAN_EVIDENCE_V1"
FIXTURE_SCHEMA: Final = "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
MAX_TRACKED_BYTES: Final = 4 * 1024 * 1024
MAX_CONTENT_BYTES: Final = 1024 * 1024
MAX_STATUS_BYTES: Final = 1024 * 1024
MAX_IMAGE_BYTES: Final = 2_000_000
FRESHNESS: Final = timedelta(hours=24)
MANUFACTURER_SALES_STATE_FRESHNESS: Final = timedelta(hours=24)
MANUFACTURER_SALES_STATE_MAX_FUTURE_SKEW: Final = timedelta(minutes=5)
REQUIRED_AD_DISCLOSURE: Final = (
    "広告を含みます。購入リンクから成果報酬を受け取る場合がありますが、"
    "選定・掲載順には使いません。"
)
NONAFFILIATE_ARTICLE_ID: Final = "solota-vs-rakua-mini-plus"
REQUIRED_NONAFFILIATE_DISCLOSURE: Final = (
    "この記事には購入リンクがありません。以前の比較対象の販売状態を確認する案内記事のため、"
    "商品カードとアフィリエイトリンクは掲載していません。"
)
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
SLUG_RE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ITEM_CODE_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}:[0-9]{5,20}\Z")
EvidenceState = Literal["verified", "not_found", "ambiguous", "expired"]
ProductImageExtension = Literal["jpg", "png", "gif"]
ManufacturerSalesState = Literal["AVAILABLE", "OUT_OF_STOCK", "DISCONTINUED", "UNKNOWN"]
ManufacturerAvailabilityScope = Literal["MODEL", "VARIANT"]


class EditorialPortfolioV2Failure(RuntimeError):
    """A stable, non-sensitive portfolio failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialPortfolioV2Failure(code) from None


def _article_disclosure_is_exact(
    markup: str,
    *,
    article_id: str,
    product_ids: tuple[str, ...],
) -> bool:
    nonaffiliate_route = article_id == NONAFFILIATE_ARTICLE_ID
    if nonaffiliate_route != (not product_ids):
        return False
    affiliate_count = markup.count(REQUIRED_AD_DISCLOSURE)
    nonaffiliate_count = markup.count(REQUIRED_NONAFFILIATE_DISCLOSURE)
    if nonaffiliate_route:
        return affiliate_count == 0 and nonaffiliate_count == 1
    return affiliate_count == 1 and nonaffiliate_count == 0


def _read_bytes(path: Path, *, maximum: int, private: bool = False) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or not 1 <= before.st_size <= maximum
            or (private and before.st_uid != os.geteuid())
            or (private and stat.S_IMODE(before.st_mode) != 0o600)
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")
        raw = os.read(descriptor, before.st_size + 1)
        after = os.fstat(descriptor)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")
        return raw
    except EditorialPortfolioV2Failure:
        raise
    except OSError, ValueError, TypeError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _read_json(path: Path, *, maximum: int, private: bool = False) -> object:
    try:
        raw = _read_bytes(path, maximum=maximum, private=private)
        return json.loads(raw.decode("utf-8", errors="strict"))
    except EditorialPortfolioV2Failure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return cast(list[object], value)


def _text(value: object, *, maximum: int = 4096) -> str:
    if (
        type(value) is not str
        or not 1 <= len(value) <= maximum
        or value != value.strip()
        or "\x00" in value
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return value


def _text_tuple(value: object, *, maximum: int = 300) -> tuple[str, ...]:
    result = tuple(_text(item, maximum=maximum) for item in _list(value))
    if not result or len(result) != len(set(result)):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return result


def _https_url(value: object) -> str:
    url = _text(value, maximum=4096)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return url


@dataclass(frozen=True, slots=True)
class ProductBindingV2:
    product_id: str
    official_name: str
    official_models: tuple[str, ...]
    representative_model: str
    official_jan: str | None
    official_url: str
    rakuten_shop_code: str | None
    rakuten_item_code: str | None
    required_title_tokens: tuple[str, ...]
    product_kind_tokens: tuple[str, ...]
    forbidden_title_tokens: tuple[str, ...]

    @property
    def affiliate_ref(self) -> str:
        return f"AFF-{self.product_id.removeprefix('PRD-')}"

    @property
    def media_asset_ref(self) -> str:
        return f"MEDIA-{self.product_id.removeprefix('PRD-')}"


@dataclass(frozen=True, slots=True)
class ArticleBindingV2:
    article_id: str
    source_kind: str
    source_ref: str
    local_slug: str
    production_slug: str
    category: str
    title: str
    excerpt: str
    content_ref: str
    product_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExcludedAlternativeV2:
    scope: str
    reason: str


@dataclass(frozen=True, slots=True)
class ProductSelectionAuditV2:
    product_id: str
    article_ids: tuple[str, ...]
    evaluated_at: str
    axis_assessments: tuple[tuple[str, str], ...]
    inclusion_reason: str
    excluded_alternatives: tuple[ExcludedAlternativeV2, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ManufacturerVariantCaveatV1:
    code: str
    detail: str
    establishes_exact_rakuten_variant: Literal[False] = False


@dataclass(frozen=True, slots=True)
class ManufacturerSalesStateV1:
    checked_at_utc: str
    product_id: str
    state: ManufacturerSalesState
    official_url: str
    status_evidence_urls: tuple[str, ...]
    locator: str
    basis: str
    variant_caveat: ManufacturerVariantCaveatV1 | None
    structured_snapshot_sha256: str
    availability_scope: ManufacturerAvailabilityScope = "MODEL"
    recheck_required: Literal[True] = True

    @property
    def known_state(self) -> bool:
        return self.state != "UNKNOWN"

    @property
    def model_is_available(self) -> bool:
        return self.state == "AVAILABLE"

    @property
    def publication_gate(self) -> Literal["CONDITIONAL", "INELIGIBLE"]:
        return "CONDITIONAL" if self.model_is_available else "INELIGIBLE"

    @property
    def establishes_exact_rakuten_variant(self) -> Literal[False]:
        """Model-level manufacturer state is never exact Rakuten CTA proof."""

        return False


@dataclass(frozen=True, slots=True)
class ManufacturerSalesStateAuditV1:
    checked_at_utc: str
    document_sha256: str
    products: tuple[ManufacturerSalesStateV1, ...]
    availability_scope: Literal["MODEL", "MIXED"] = "MODEL"
    cta_requires_separate_exact_variant_evidence: Literal[True] = True

    @property
    def product_by_id(self) -> dict[str, ManufacturerSalesStateV1]:
        return {product.product_id: product for product in self.products}

    @property
    def known_product_count(self) -> int:
        return sum(product.known_state for product in self.products)

    @property
    def publication_eligible(self) -> bool:
        return bool(self.products) and all(
            product.model_is_available for product in self.products
        )


@dataclass(frozen=True, slots=True)
class EditorialPortfolioV2:
    version: str
    target_origin: str
    theme_version: str
    editorial_reviewed_on: str
    articles: tuple[ArticleBindingV2, ...]
    products: tuple[ProductBindingV2, ...]
    selection_audits: tuple[ProductSelectionAuditV2, ...] = ()
    manufacturer_sales_state_audit: ManufacturerSalesStateAuditV1 | None = None
    freshness: timedelta = FRESHNESS

    @property
    def product_by_id(self) -> dict[str, ProductBindingV2]:
        return {product.product_id: product for product in self.products}

    @property
    def article_by_production_slug(self) -> dict[str, ArticleBindingV2]:
        return {article.production_slug: article for article in self.articles}

    @property
    def manufacturer_sales_state_by_product_id(
        self,
    ) -> dict[str, ManufacturerSalesStateV1]:
        if self.manufacturer_sales_state_audit is None:
            return {}
        return self.manufacturer_sales_state_audit.product_by_id


@dataclass(frozen=True, slots=True)
class ProductEvidenceViewV2:
    product_id: str
    state: EvidenceState
    retrieved_at: str
    evidence: RakutenProductEvidence | None
    image_extension: ProductImageExtension | None = None
    jan_evidence_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ProductEvidenceReadinessV2:
    complete: bool
    product_count: int
    verified_product_count: int
    product_card_count: int
    verified_product_card_count: int
    affiliate_cta_count: int
    verified_affiliate_cta_count: int
    missing_registry_product_ids: tuple[str, ...]
    unverified_product_ids: tuple[str, ...]
    manufacturer_sales_state_contract_complete: bool
    manufacturer_sales_state_publication_eligible: bool
    manufacturer_sales_state_checked_at_utc: str | None
    manufacturer_sales_state_known_product_count: int
    manufacturer_sales_state_available_product_count: int
    manufacturer_sales_state_out_of_stock_product_count: int
    manufacturer_sales_state_unknown_product_ids: tuple[str, ...]
    manufacturer_sales_state_discontinued_product_ids: tuple[str, ...]
    manufacturer_sales_state_out_of_stock_product_ids: tuple[str, ...]
    manufacturer_sales_state_recheck_product_ids: tuple[str, ...]
    manufacturer_sales_state_ineligible_product_ids: tuple[str, ...]
    manufacturer_sales_state_scope: Literal["MODEL", "MIXED", "UNAVAILABLE"]
    manufacturer_state_establishes_exact_rakuten_variant: Literal[False]
    affiliate_variant_eligibility: Literal["SEPARATE_EXACT_VARIANT_EVIDENCE_REQUIRED"]


def _strict_contract_equal(value: object, expected: object) -> bool:
    """Compare JSON contract values without bool/int equality shortcuts."""

    if type(value) is not type(expected):
        return False
    if type(expected) is dict:
        actual_mapping = cast(dict[object, object], value)
        expected_mapping = cast(dict[object, object], expected)
        return set(actual_mapping) == set(expected_mapping) and all(
            _strict_contract_equal(actual_mapping[key], expected_mapping[key])
            for key in expected_mapping
        )
    if type(expected) is list:
        actual_list = cast(list[object], value)
        expected_list = cast(list[object], expected)
        return len(actual_list) == len(expected_list) and all(
            _strict_contract_equal(actual, wanted)
            for actual, wanted in zip(actual_list, expected_list, strict=True)
        )
    return value == expected


def _sales_state_timestamp(value: object) -> str:
    text = _text(value, maximum=20)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    if (
        parsed.tzinfo is None
        or parsed.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ") != text
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    return text


def _structured_sales_state_sha256(row: Mapping[str, object]) -> str:
    try:
        payload = {field: row[field] for field in MANUFACTURER_SALES_STATE_HASH_FIELDS}
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except KeyError, TypeError, UnicodeError, ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    return hashlib.sha256(encoded).hexdigest()


def _parse_manufacturer_sales_state_audit_v1(
    repository_root: Path,
    products: tuple[ProductBindingV2, ...],
) -> ManufacturerSalesStateAuditV1:
    raw = _read_bytes(
        repository_root / MANUFACTURER_SALES_STATE_RELATIVE_PATH,
        maximum=MAX_TRACKED_BYTES,
    )
    try:
        document = _mapping(json.loads(raw.decode("utf-8", errors="strict")))
    except EditorialPortfolioV2Failure:
        raise
    except UnicodeError, json.JSONDecodeError, ValueError, TypeError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    expected_root = {
        "schema",
        "checked_at_utc",
        "snapshot_kind",
        "hash_contract",
        "availability_scope_policy",
        "evidence_resolution_policy",
        "publication_policy",
        "products",
    }
    expected_hash_contract = {
        "algorithm": "SHA-256",
        "canonicalization": (
            "UTF-8 JSON with recursively sorted object keys, no insignificant "
            "whitespace, and unescaped Unicode"
        ),
        "fields": list(MANUFACTURER_SALES_STATE_HASH_FIELDS),
    }
    expected_scope_policy = {
        "MODEL": {
            "establishes_exact_rakuten_variant": False,
            "cta_requires_separate_exact_variant_evidence": True,
        },
        "VARIANT": {
            "establishes_exact_rakuten_variant": False,
            "cta_requires_separate_exact_variant_evidence": True,
        },
    }
    expected_evidence_resolution_policy = {
        "exact_variant_reader_visible_purchase_ui_required": True,
        "reader_visible_sold_out_discontinued_or_preorder_precedes_hidden_structured_availability": True,
        "structured_data_alone_cannot_establish_available": True,
        "conflict_resolution": "FAIL_CLOSED_TO_UNKNOWN_OR_OUT_OF_STOCK",
        "preorder_resolution": "FAIL_CLOSED_TO_UNKNOWN",
    }
    expected_publication_policy = {
        "AVAILABLE": {
            "state_gate": "CONDITIONAL",
            "known_state": True,
            "recheck_required": True,
        },
        "OUT_OF_STOCK": {
            "state_gate": "INELIGIBLE",
            "known_state": True,
            "recheck_required": True,
        },
        "UNKNOWN": {
            "state_gate": "INELIGIBLE",
            "known_state": False,
            "recheck_required": True,
        },
        "DISCONTINUED": {
            "state_gate": "INELIGIBLE",
            "known_state": True,
            "recheck_required": True,
        },
    }
    if (
        set(document) != expected_root
        or document.get("schema") != MANUFACTURER_SALES_STATE_SCHEMA
        or document.get("snapshot_kind") != MANUFACTURER_SALES_STATE_SNAPSHOT_KIND
        or not _strict_contract_equal(
            document.get("hash_contract"), expected_hash_contract
        )
        or not _strict_contract_equal(
            document.get("availability_scope_policy"), expected_scope_policy
        )
        or not _strict_contract_equal(
            document.get("evidence_resolution_policy"),
            expected_evidence_resolution_policy,
        )
        or not _strict_contract_equal(
            document.get("publication_policy"), expected_publication_policy
        )
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    checked_at_utc = _sales_state_timestamp(document["checked_at_utc"])
    bindings = {product.product_id: product for product in products}
    parsed_by_id: dict[str, ManufacturerSalesStateV1] = {}
    row_checked_at_values: list[str] = []
    expected_row_fields = set(MANUFACTURER_SALES_STATE_HASH_FIELDS) | {
        "snapshot_kind",
        "structured_snapshot_sha256",
    }
    for raw_row in _list(document["products"]):
        row = _mapping(raw_row)
        if set(row) != expected_row_fields:
            _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
        product_id = _text(row["product_id"], maximum=160)
        row_checked_at_utc = _sales_state_timestamp(row["checked_at_utc"])
        binding = bindings.get(product_id)
        raw_state = row["state"]
        official_url = _https_url(row["official_url"])
        status_evidence_urls = tuple(
            _https_url(value) for value in _list(row["status_evidence_urls"])
        )
        snapshot_sha256 = _text(row["structured_snapshot_sha256"], maximum=64)
        raw_availability_scope = row["availability_scope"]
        if (
            binding is None
            or product_id in parsed_by_id
            or type(raw_state) is not str
            or raw_state not in {"AVAILABLE", "OUT_OF_STOCK", "DISCONTINUED", "UNKNOWN"}
            or type(raw_availability_scope) is not str
            or raw_availability_scope not in {"MODEL", "VARIANT"}
            or official_url != binding.official_url
            or not status_evidence_urls
            or len(status_evidence_urls) != len(set(status_evidence_urls))
            or row["alternative"] is not None
            or row["snapshot_kind"] != MANUFACTURER_SALES_STATE_SNAPSHOT_KIND
            or type(row["snapshot_kind"]) is not str
            or SHA256_RE.fullmatch(snapshot_sha256) is None
            or not hmac.compare_digest(
                snapshot_sha256, _structured_sales_state_sha256(row)
            )
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
        row_checked_at_values.append(row_checked_at_utc)
        raw_caveat = row["variant_caveat"]
        caveat: ManufacturerVariantCaveatV1 | None = None
        if raw_caveat is not None:
            caveat_mapping = _mapping(raw_caveat)
            if (
                set(caveat_mapping)
                != {"code", "detail", "establishes_exact_rakuten_variant"}
                or caveat_mapping["establishes_exact_rakuten_variant"] is not False
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
            caveat = ManufacturerVariantCaveatV1(
                code=_text(caveat_mapping["code"], maximum=200),
                detail=_text(caveat_mapping["detail"], maximum=2000),
            )
        availability_scope: ManufacturerAvailabilityScope = (
            "MODEL" if raw_availability_scope == "MODEL" else "VARIANT"
        )
        parsed_by_id[product_id] = ManufacturerSalesStateV1(
            checked_at_utc=row_checked_at_utc,
            product_id=product_id,
            state=cast(ManufacturerSalesState, raw_state),
            official_url=official_url,
            status_evidence_urls=status_evidence_urls,
            locator=_text(row["locator"], maximum=4000),
            basis=_text(row["basis"], maximum=4000),
            variant_caveat=caveat,
            structured_snapshot_sha256=snapshot_sha256,
            availability_scope=availability_scope,
        )
    if (
        len(parsed_by_id) != len(products)
        or set(parsed_by_id) != set(bindings)
        or min(row_checked_at_values, default="") != checked_at_utc
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")
    return ManufacturerSalesStateAuditV1(
        checked_at_utc=checked_at_utc,
        document_sha256=hashlib.sha256(raw).hexdigest(),
        products=tuple(parsed_by_id[product.product_id] for product in products),
        availability_scope=(
            "MODEL"
            if all(row.availability_scope == "MODEL" for row in parsed_by_id.values())
            else "MIXED"
        ),
    )


def load_manufacturer_sales_state_audit_v1(
    repository_root: Path,
    *,
    products: tuple[ProductBindingV2, ...],
) -> ManufacturerSalesStateAuditV1:
    """Load and bind the tracked model-level manufacturer sales audit."""

    if not repository_root.is_absolute():
        _fail("RAOS_EDITORIAL_PORTFOLIO_ROOT_INVALID")
    try:
        return _parse_manufacturer_sales_state_audit_v1(repository_root, products)
    except EditorialPortfolioV2Failure as exc:
        if str(exc) == "RAOS_EDITORIAL_PORTFOLIO_ROOT_INVALID":
            raise
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INVALID")


def load_editorial_portfolio_v2(repository_root: Path) -> EditorialPortfolioV2:
    if not repository_root.is_absolute():
        _fail("RAOS_EDITORIAL_PORTFOLIO_ROOT_INVALID")
    document = _mapping(
        _read_json(
            repository_root / PORTFOLIO_RELATIVE_PATH,
            maximum=MAX_TRACKED_BYTES,
        )
    )
    expected_root = {
        "schema",
        "version",
        "target_origin",
        "editorial_reviewed_on",
        "theme_version",
        "evidence_policy",
        "selection_policy",
        "selection_audits",
        "content_contract",
        "common_forbidden_title_tokens",
        "articles",
        "products",
    }
    if set(document) != expected_root or document.get("schema") != PORTFOLIO_SCHEMA:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    policy = _mapping(document["evidence_policy"])
    completion_gate = _mapping(policy.get("completion_gate"))
    if (
        set(policy)
        != {
            "freshness_hours",
            "states",
            "verified_cta_placements",
            "affiliate_rel",
            "unverified_destination",
            "allow_search_result_destination",
            "allow_short_url_destination",
            "allow_variant_substitution",
            "identity_validation",
            "local_product_image_origin",
            "completion_gate",
        }
        or policy["freshness_hours"] != 24
        or policy["states"] != ["verified", "not_found", "ambiguous", "expired"]
        or policy["verified_cta_placements"] != ["product_card", "final_summary"]
        or policy["affiliate_rel"] != "sponsored nofollow"
        or policy["unverified_destination"] != "manufacturer_official"
        or policy["allow_search_result_destination"] is not False
        or policy["allow_short_url_destination"] is not False
        or policy["allow_variant_substitution"] is not False
        or policy["identity_validation"]
        != {
            "representative_model": "required_exact",
            "jan": "required_exact_when_official_jan_registered",
            "title_tokens": "required",
            "pc_mobile_item_code": "required_exact",
        }
        or policy["local_product_image_origin"] != "/raos-product-media/"
        or set(completion_gate)
        != {
            "required_product_count",
            "required_product_card_count",
            "required_affiliate_cta_count",
            "required_product_state",
            "required_product_image_state",
            "maximum_neutral_product_images",
            "maximum_manufacturer_fallback_ctas",
        }
        or completion_gate.get("required_product_state") != "verified"
        or completion_gate.get("required_product_image_state") != "verified"
        or completion_gate.get("maximum_neutral_product_images") != 0
        or completion_gate.get("maximum_manufacturer_fallback_ctas") != 0
        or any(
            type(completion_gate.get(field)) is not int
            for field in (
                "required_product_count",
                "required_product_card_count",
                "required_affiliate_cta_count",
                "maximum_neutral_product_images",
                "maximum_manufacturer_fallback_ctas",
            )
        )
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    selection_policy = _mapping(document["selection_policy"])
    zero_weights = _mapping(selection_policy.get("zero_weight_factors"))
    if selection_policy != {
        "ranking_factors": [
            "use_case_fit",
            "safety",
            "dimensions",
            "performance",
            "warranty_and_support",
            "maintainability",
            "primary_source_confidence",
        ],
        "zero_weight_factors": {
            "price": 0,
            "affiliate_reward_rate": 0,
            "rakuten_availability": 0,
        },
        "replacement_policy": (
            "one_for_one_with_recorded_inclusion_and_exclusion_reasons"
        ),
    }:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    if any(type(value) is not int or value != 0 for value in zero_weights.values()):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    common_forbidden = _text_tuple(document["common_forbidden_title_tokens"])
    content_contract = _mapping(document["content_contract"])
    if content_contract != {
        "body_format": "html_fragment",
        "required_editorial_root": "raos-editorial-v2",
        "required_ad_disclosure": REQUIRED_AD_DISCLOSURE,
        "required_nonaffiliate_disclosure": REQUIRED_NONAFFILIATE_DISCLOSURE,
        "nonaffiliate_article_ids": [NONAFFILIATE_ARTICLE_ID],
        "fixed_breaks_forbidden_in": ["h1", "h2", "th"],
        "article_metadata_fields": [
            "title",
            "excerpt",
            "content_ref",
        ],
        "primary_product_sources": "products[].official_url",
    }:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")

    fixtures = _mapping(
        _read_json(
            repository_root / SOURCE_FIXTURE_RELATIVE_PATH / "posts.json",
            maximum=MAX_TRACKED_BYTES,
        )
    )
    if fixtures.get("schema") != FIXTURE_SCHEMA:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    target_origin = _https_url(document["target_origin"])
    if target_origin != TARGET_ORIGIN:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    posts_by_slug: dict[str, Mapping[str, object]] = {}
    for raw_post in _list(fixtures.get("posts")):
        post = _mapping(raw_post)
        slug = post.get("slug")
        if type(slug) is not str or slug in posts_by_slug:
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        posts_by_slug[slug] = post

    products: list[ProductBindingV2] = []
    product_ids: set[str] = set()
    for raw_product in _list(document["products"]):
        product = _mapping(raw_product)
        allowed = {
            "product_id",
            "official_name",
            "official_models",
            "representative_model",
            "official_jan",
            "official_url",
            "rakuten_shop_code",
            "rakuten_item_code",
            "required_title_tokens",
            "product_kind_tokens",
            "additional_forbidden_title_tokens",
        }
        required = allowed - {"additional_forbidden_title_tokens", "official_jan"}
        if set(product) - allowed or not required.issubset(product):
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        product_id = _text(product["product_id"], maximum=160)
        models = _text_tuple(product["official_models"])
        representative = _text(product["representative_model"], maximum=300)
        official_jan = product.get("official_jan")
        shop = product["rakuten_shop_code"]
        item_code = product["rakuten_item_code"]
        if (
            PRODUCT_ID_RE.fullmatch(product_id) is None
            or product_id in product_ids
            or representative not in models
            or (
                official_jan is not None
                and (
                    type(official_jan) is not str
                    or re.fullmatch(r"[0-9]{8,14}", official_jan) is None
                )
            )
            or (shop is None) != (item_code is None)
            or (
                shop is not None
                and (
                    type(shop) is not str
                    or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", shop)
                    or type(item_code) is not str
                    or ITEM_CODE_RE.fullmatch(item_code) is None
                    or not item_code.startswith(f"{shop}:")
                )
            )
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        extra = product.get("additional_forbidden_title_tokens", [])
        extra_forbidden = _text_tuple(extra) if extra else ()
        forbidden = (*common_forbidden, *extra_forbidden)
        products.append(
            ProductBindingV2(
                product_id=product_id,
                official_name=_text(product["official_name"], maximum=500),
                official_models=models,
                representative_model=representative,
                official_jan=official_jan,
                official_url=_https_url(product["official_url"]),
                rakuten_shop_code=shop,
                rakuten_item_code=cast(str | None, item_code),
                required_title_tokens=_text_tuple(product["required_title_tokens"]),
                product_kind_tokens=_text_tuple(product["product_kind_tokens"]),
                forbidden_title_tokens=forbidden,
            )
        )
        product_ids.add(product_id)

    articles: list[ArticleBindingV2] = []
    article_ids: set[str] = set()
    local_slugs: set[str] = set()
    production_slugs: set[str] = set()
    occurrences = 0
    for raw_article in _list(document["articles"]):
        article = _mapping(raw_article)
        if set(article) != {
            "article_id",
            "source_kind",
            "source_ref",
            "local_slug",
            "production_slug",
            "category",
            "title",
            "excerpt",
            "content_ref",
            "product_ids",
        }:
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        article_id = _text(article["article_id"], maximum=160)
        source_kind = _text(article["source_kind"], maximum=40)
        source_ref = _text(article["source_ref"], maximum=300)
        local_slug = _text(article["local_slug"], maximum=200)
        production_slug = _text(article["production_slug"], maximum=200)
        title = _text(article["title"], maximum=500)
        excerpt = _text(article["excerpt"], maximum=4000)
        content_ref = _text(article["content_ref"], maximum=500)
        references = tuple(
            _text(item, maximum=160) for item in _list(article["product_ids"])
        )
        if len(references) != len(set(references)) or (
            not references and article_id != "solota-vs-rakua-mini-plus"
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        post_row = posts_by_slug.get(local_slug)
        expected_content_ref = (
            "changes/wordpress-local-preview-v1/fixtures/articles/"
            f"{production_slug}.html"
        )
        try:
            content_path = repository_root / content_ref
            metadata = content_path.lstat()
            content_payload = content_path.read_bytes()
            content = content_payload.decode("utf-8", errors="strict")
        except OSError, UnicodeError:
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        if (
            article_id in article_ids
            or local_slug in local_slugs
            or production_slug in production_slugs
            or source_kind not in {"st1704_renderer", "html_fixture"}
            or not local_slug.startswith("local-preview-")
            or production_slug != local_slug.removeprefix("local-preview-")
            or SLUG_RE.fullmatch(local_slug) is None
            or SLUG_RE.fullmatch(production_slug) is None
            or not set(references).issubset(product_ids)
            or (
                source_kind == "html_fixture"
                and source_ref != f"articles/{production_slug}.html"
            )
            or (source_kind == "st1704_renderer" and source_ref != article_id)
            or post_row is None
            or post_row.get("title") != title
            or post_row.get("excerpt") != excerpt
            or post_row.get("category") != article.get("category")
            or post_row.get("content_file") != f"articles/{production_slug}.html"
            or content_ref != expected_content_ref
            or content_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 1 <= len(content_payload) <= MAX_CONTENT_BYTES
            or content.count('class="raos-editorial-v2"') != 1
            or not _article_disclosure_is_exact(
                content,
                article_id=article_id,
                product_ids=references,
            )
            or re.search(
                r"<(?:h1|h2|th)\b[^>]*>(?:(?!</(?:h1|h2|th)>).)*<br\b",
                content,
                flags=re.IGNORECASE | re.DOTALL,
            )
            is not None
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
        articles.append(
            ArticleBindingV2(
                article_id=article_id,
                source_kind=source_kind,
                source_ref=source_ref,
                local_slug=local_slug,
                production_slug=production_slug,
                category=_text(article["category"], maximum=100),
                title=title,
                excerpt=excerpt,
                content_ref=content_ref,
                product_ids=references,
            )
        )
        article_ids.add(article_id)
        local_slugs.add(local_slug)
        production_slugs.add(production_slug)
        occurrences += len(references)

    if (
        len(articles) != 10
        or occurrences != 37
        or completion_gate["required_product_count"] != len(products)
        or completion_gate["required_product_card_count"] != occurrences
        or completion_gate["required_affiliate_cta_count"] != occurrences * 2
        or {product.product_id for product in products}
        != {product_id for article in articles for product_id in article.product_ids}
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_COUNT_INVALID")

    manufacturer_sales_state_audit = load_manufacturer_sales_state_audit_v1(
        repository_root,
        products=tuple(products),
    )

    audit_document = _mapping(document["selection_audits"])
    axis_order = (
        "use_case_fit",
        "safety",
        "dimensions",
        "performance",
        "warranty_and_support",
        "maintainability",
        "primary_source_confidence",
    )
    if (
        set(audit_document)
        != {"schema", "axis_order", "zero_weight_factors", "products"}
        or audit_document["schema"] != "RAOS_PRODUCT_SELECTION_AUDIT_V1"
        or tuple(
            _text(value, maximum=80) for value in _list(audit_document["axis_order"])
        )
        != axis_order
        or _mapping(audit_document["zero_weight_factors"])
        != {
            "price": 0,
            "affiliate_reward_rate": 0,
            "rakuten_availability": 0,
        }
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    allowed_assessments = {
        "use_case_fit": {"INCLUDED_FOR_DECLARED_USE_CASE"},
        "safety": {"SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"},
        "dimensions": {"OFFICIAL_SPEC_CONFIRMED"},
        "performance": {"OFFICIAL_SPEC_CONFIRMED"},
        "warranty_and_support": {"SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"},
        "maintainability": {"SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"},
        "primary_source_confidence": {"OFFICIAL_PRODUCT_PAGE_BOUND"},
    }
    product_by_id = {product.product_id: product for product in products}
    expected_articles_by_product = {
        product_id: tuple(
            article.article_id
            for article in articles
            if product_id in article.product_ids
        )
        for product_id in product_ids
    }
    selection_audits: list[ProductSelectionAuditV2] = []
    audited_product_ids: set[str] = set()
    for raw_audit in _list(audit_document["products"]):
        audit = _mapping(raw_audit)
        if set(audit) != {
            "product_id",
            "article_ids",
            "evaluated_at",
            "axis_assessments",
            "inclusion_reason",
            "excluded_alternatives",
            "evidence_refs",
        }:
            _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        product_id = _text(audit["product_id"], maximum=160)
        product_binding = product_by_id.get(product_id)
        article_refs = _text_tuple(audit["article_ids"], maximum=160)
        assessments = _mapping(audit["axis_assessments"])
        evidence_refs = tuple(
            _https_url(value) for value in _list(audit["evidence_refs"])
        )
        try:
            evaluated_at = date.fromisoformat(
                _text(audit["evaluated_at"], maximum=10)
            ).isoformat()
        except ValueError:
            _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        if (
            product_binding is None
            or product_id in audited_product_ids
            or article_refs != expected_articles_by_product[product_id]
            or set(assessments) != set(axis_order)
            or any(
                _text(assessments[axis], maximum=80) not in allowed_assessments[axis]
                for axis in axis_order
            )
            or not evidence_refs
            or evidence_refs[0] != product_binding.official_url
            or len(evidence_refs) != len(set(evidence_refs))
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        alternatives: list[ExcludedAlternativeV2] = []
        for raw_alternative in _list(audit["excluded_alternatives"]):
            alternative = _mapping(raw_alternative)
            if set(alternative) != {"scope", "reason"}:
                _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
            alternatives.append(
                ExcludedAlternativeV2(
                    scope=_text(alternative["scope"], maximum=1000),
                    reason=_text(alternative["reason"], maximum=1000),
                )
            )
        if not alternatives:
            _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
        selection_audits.append(
            ProductSelectionAuditV2(
                product_id=product_id,
                article_ids=article_refs,
                evaluated_at=evaluated_at,
                axis_assessments=tuple(
                    (axis, _text(assessments[axis], maximum=80)) for axis in axis_order
                ),
                inclusion_reason=_text(audit["inclusion_reason"], maximum=2000),
                excluded_alternatives=tuple(alternatives),
                evidence_refs=evidence_refs,
            )
        )
        audited_product_ids.add(product_id)
    if audited_product_ids != product_ids or len(selection_audits) != len(products):
        _fail("RAOS_EDITORIAL_PORTFOLIO_SELECTION_AUDIT_INVALID")
    representative_models = {
        product.product_id: product.representative_model for product in products
    }
    if (
        representative_models.get("PRD-IROBOT-ROOMBA-MINI-SLIM-F115060") != "F115060"
        or representative_models.get("PRD-THANKO-RAKUA-MINI-TK-MDW22W") != "TK-MDW22W"
        or representative_models.get("PRD-SIROCA-SS-M171") != "SS-M171"
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    editorial_reviewed_on = _text(
        document["editorial_reviewed_on"],
        maximum=10,
    )
    try:
        parsed_editorial_review = date.fromisoformat(editorial_reviewed_on)
    except ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    if parsed_editorial_review.isoformat() != editorial_reviewed_on:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    return EditorialPortfolioV2(
        version=_text(document["version"], maximum=30),
        target_origin=target_origin,
        theme_version=_text(document["theme_version"], maximum=30),
        editorial_reviewed_on=editorial_reviewed_on,
        articles=tuple(articles),
        products=tuple(products),
        selection_audits=tuple(selection_audits),
        manufacturer_sales_state_audit=manufacturer_sales_state_audit,
    )


def _parse_timestamp(value: object) -> datetime:
    text = _text(value, maximum=40)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    if parsed.tzinfo is None:
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    return parsed.astimezone(UTC)


_IDENTITY_TOKEN_SEPARATOR = re.compile(r"[\s+*・_.\-/＆&]+")
_IDENTITY_TOKEN_SEPARATOR_PATTERN: Final = r"[\s+*・_.\-/＆&]*"


def _title_has_token(title: str, token: str) -> bool:
    if type(title) is not str or type(token) is not str or not title or not token:
        return False
    normalized_title = unicodedata.normalize("NFKC", title).casefold()
    normalized_token = unicodedata.normalize("NFKC", token).casefold()
    components = tuple(
        component
        for component in _IDENTITY_TOKEN_SEPARATOR.split(normalized_token)
        if component
    )
    if not components:
        return False
    pattern = _IDENTITY_TOKEN_SEPARATOR_PATTERN.join(
        re.escape(component) for component in components
    )
    if re.fullmatch(r"[a-z0-9]", components[0][0], re.ASCII):
        pattern = r"(?<![a-z0-9])" + pattern
    if re.fullmatch(r"[a-z0-9]", components[-1][-1], re.ASCII):
        pattern += r"(?![a-z0-9])"
    return re.search(pattern, normalized_title) is not None


def _validate_rakuten_identity(
    binding: ProductBindingV2,
    evidence: RakutenProductEvidence,
    *,
    jan_evidence_sha256: str | None = None,
) -> None:
    title = evidence.item_name
    source = urlsplit(evidence.source_url)
    destination = urlsplit(evidence.destination_url)
    try:
        query = parse_qs(
            destination.query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=3,
        )
        pc = urlsplit(query["pc"][0])
        mobile = urlsplit(query["m"][0])
    except KeyError, IndexError, ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    pc_parts = pc.path.strip("/").split("/")
    mobile_parts = mobile.path.strip("/").split("/")
    item_code_parts = evidence.item_code.split(":", 1)
    if (
        evidence.product_id != binding.product_id
        or evidence.affiliate_ref != binding.affiliate_ref
        or evidence.media_asset_ref != binding.media_asset_ref
        or evidence.item_code != binding.rakuten_item_code
        or evidence.variant != binding.representative_model
        or not _title_has_token(title, binding.representative_model)
        or (
            evidence.jan is not None
            and re.fullmatch(r"[0-9]{8,14}", evidence.jan) is None
        )
        or (
            binding.official_jan is not None
            and (
                jan_evidence_sha256 is None
                or SHA256_RE.fullmatch(jan_evidence_sha256) is None
                or evidence.jan not in {None, binding.official_jan}
            )
        )
        or (binding.official_jan is None and jan_evidence_sha256 is not None)
        or not all(
            _title_has_token(title, token) for token in binding.required_title_tokens
        )
        or not any(
            _title_has_token(title, token) for token in binding.product_kind_tokens
        )
        or any(
            _title_has_token(title, token) for token in binding.forbidden_title_tokens
        )
        or destination.scheme != "https"
        or destination.netloc != "hb.afl.rakuten.co.jp"
        or set(query) != {"m", "pc", "rafcid"}
        or source.scheme != "https"
        or source.netloc != "item.rakuten.co.jp"
        or source.query
        or source.fragment
        or query["pc"][0] != evidence.source_url
        or pc.scheme != "https"
        or pc.netloc != "item.rakuten.co.jp"
        or pc.query
        or pc.fragment
        or len(pc_parts) != 2
        or mobile.scheme not in {"http", "https"}
        or mobile.netloc != "m.rakuten.co.jp"
        or mobile.query
        or mobile.fragment
        or len(mobile_parts) != 3
        or mobile_parts[1] != "i"
        or len(item_code_parts) != 2
        or pc_parts[0] != mobile_parts[0]
        or pc_parts[0] != item_code_parts[0]
        or mobile_parts[0] != item_code_parts[0]
        or mobile_parts[2] != item_code_parts[1]
        or evidence.item_code != f"{mobile_parts[0]}:{mobile_parts[2]}"
        or evidence.width != 128
        or evidence.height != 128
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")


def rakuten_identity_query_v1(binding: ProductBindingV2) -> str:
    """Widen only the search syntax; exact identity matching remains unchanged.

    Rakuten rejects one-byte search terms (for example the '2' in 'mini 2').
    Such terms are omitted from retrieval, not from product identity checks.
    """
    query = " ".join(
        part
        for part in binding.representative_model.split()
        if not (len(part) == 1 and part.isascii())
    )
    if not query:
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_QUERY_INVALID")
    return query


def discover_rakuten_identity_v1(
    binding: ProductBindingV2,
    raw: bytes,
) -> ProductBindingV2 | None:
    """Resolve only a complete, unique API search; never select by price/rank."""
    target = identity_capture.ProductCaptureTarget(
        product_id=binding.product_id,
        shop_code=binding.rakuten_shop_code or "unresolved",
        affiliate_ref=binding.affiliate_ref,
        media_asset_ref=binding.media_asset_ref,
        variants=(binding.representative_model,),
        required_title_tokens=binding.required_title_tokens,
        product_kind_tokens=binding.product_kind_tokens,
        forbidden_title_tokens=binding.forbidden_title_tokens,
        jan=None,
        fixed_item_code=None,
        fixed_destination_url=None,
    )
    rows = identity_capture.discovery_rows(raw)
    summary = json.loads(raw)
    if summary.get("count") != len(rows) or summary.get("page") != 1:
        return None  # An unexamined page can contain another matching listing.
    candidates = [
        row
        for row in rows
        if identity_capture.matches_product_identity(target, row)
        and (
            binding.rakuten_shop_code is None
            or row.get("shopCode") == binding.rakuten_shop_code
        )
        and not any(
            token in str(row.get("itemName", ""))
            for token in ("中古", "レンタル", "ジャンク", "訳あり", "再生品")
        )
    ]
    if len(candidates) != 1:
        return None
    row = candidates[0]
    code, shop = row.get("itemCode"), row.get("shopCode")
    if (
        type(code) is not str
        or ITEM_CODE_RE.fullmatch(code) is None
        or type(shop) is not str
        or code.split(":", 1)[0] != shop
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_INVALID")
    return replace(binding, rakuten_item_code=code, rakuten_shop_code=shop)


def resolve_rakuten_identity_v1(
    repository_root: Path,
    binding: ProductBindingV2,
    *,
    now: datetime | None = None,
) -> ProductBindingV2:
    """Replay private API identity evidence, separate from human attestation."""
    if binding.rakuten_item_code is not None:
        return binding
    root = repository_root / STATUS_RELATIVE_PATH.parent / "provider"
    receipt = _mapping(
        _read_json(
            root / f"{binding.product_id}.identity.v1.json",
            maximum=MAX_STATUS_BYTES,
            private=True,
        )
    )
    if set(receipt) != {
        "schema",
        "provenance",
        "owner_attested",
        "portfolio_sha256",
        "product_id",
        "query_model",
        "search_keyword",
        "retrieved_at",
        "response_sha256",
        "item_code",
        "shop_code",
    }:
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_INVALID")
    retrieved = _parse_timestamp(receipt.get("retrieved_at"))
    active_now = (now or datetime.now(UTC)).astimezone(UTC)
    raw = _read_bytes(
        root / f"{binding.product_id}.search-response.v2.json",
        maximum=MAX_STATUS_BYTES,
        private=True,
    )
    if (
        receipt.get("schema") != "RAOS_RAKUTEN_API_IDENTITY_V1"
        or receipt.get("provenance") != "API_VERIFIED"
        or receipt.get("owner_attested") is not False
        or receipt.get("portfolio_sha256") != portfolio_sha256(repository_root)
        or receipt.get("product_id") != binding.product_id
        or receipt.get("query_model") != binding.representative_model
        or receipt.get("search_keyword") != rakuten_identity_query_v1(binding)
        or receipt.get("response_sha256") != hashlib.sha256(raw).hexdigest()
        or active_now < retrieved
        or active_now - retrieved > FRESHNESS
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_INVALID")
    try:
        resolved = discover_rakuten_identity_v1(binding, raw)
    except identity_capture.RakutenProductCaptureFailure:
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_INVALID")
    if (
        resolved is None
        or receipt.get("item_code") != resolved.rakuten_item_code
        or receipt.get("shop_code") != resolved.rakuten_shop_code
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_DISCOVERY_INVALID")
    return resolved


def _load_status_receipt(repository_root: Path) -> Mapping[str, object] | None:
    path = repository_root / STATUS_RELATIVE_PATH
    if not path.exists() and not path.is_symlink():
        return None
    document = _mapping(_read_json(path, maximum=MAX_STATUS_BYTES, private=True))
    if set(document) != {"schema", "captured_at", "portfolio_sha256", "products"}:
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    return document


def product_jan_evidence_bindings_v1(
    repository_root: Path,
    *,
    portfolio: EditorialPortfolioV2,
    now: datetime | None = None,
) -> dict[str, str]:
    """Validate owner-private official JAN snapshots for API rows without JAN."""

    path = repository_root / JAN_EVIDENCE_RELATIVE_PATH
    if not path.exists() and not path.is_symlink():
        return {}
    document = _mapping(_read_json(path, maximum=MAX_STATUS_BYTES, private=True))
    if set(document) != {
        "schema",
        "verified_at",
        "portfolio_sha256",
        "owner_attested",
        "products",
    } or (
        document.get("schema") != JAN_EVIDENCE_SCHEMA
        or document.get("portfolio_sha256") != portfolio_sha256(repository_root)
        or document.get("owner_attested") is not True
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
    verified_at = _parse_timestamp(document.get("verified_at"))
    active_now = (now or datetime.now(UTC)).astimezone(UTC)
    if active_now < verified_at or active_now - verified_at > portfolio.freshness:
        _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_EXPIRED")
    expected = {
        product.product_id: product
        for product in portfolio.products
        if product.official_jan is not None
    }
    bindings: dict[str, str] = {}
    for raw in _list(document.get("products")):
        row = _mapping(raw)
        if set(row) != {
            "product_id",
            "representative_model",
            "official_jan",
            "official_url",
            "source_locator",
            "source_snapshot_file",
            "source_snapshot_sha256",
            "verified_at",
        }:
            _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
        product_id = _text(row.get("product_id"), maximum=160)
        binding = expected.get(product_id)
        row_verified_at = _parse_timestamp(row.get("verified_at"))
        snapshot_name = _text(row.get("source_snapshot_file"), maximum=200)
        snapshot_sha256 = _text(row.get("source_snapshot_sha256"), maximum=64)
        if (
            binding is None
            or product_id in bindings
            or row_verified_at != verified_at
            or row.get("representative_model") != binding.representative_model
            or row.get("official_jan") != binding.official_jan
            or row.get("official_url") != binding.official_url
            or snapshot_name != f"{product_id}.snapshot.txt"
            or SHA256_RE.fullmatch(snapshot_sha256) is None
            or snapshot_sha256 == "0" * 64
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
        snapshot = _read_bytes(
            repository_root / JAN_EVIDENCE_SNAPSHOT_RELATIVE_ROOT / snapshot_name,
            maximum=MAX_STATUS_BYTES,
            private=True,
        )
        if not hmac.compare_digest(
            hashlib.sha256(snapshot).hexdigest(), snapshot_sha256
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
        try:
            snapshot_text = unicodedata.normalize(
                "NFKC", snapshot.decode("utf-8", errors="strict")
            ).casefold()
        except UnicodeError:
            _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
        if (
            cast(str, binding.official_jan) not in snapshot_text
            or unicodedata.normalize("NFKC", binding.representative_model).casefold()
            not in snapshot_text
            or not _text(row.get("source_locator"), maximum=4000)
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INVALID")
        bindings[product_id] = hashlib.sha256(
            json.dumps(
                dict(row),
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    if set(bindings) != set(expected):
        _fail("RAOS_EDITORIAL_PORTFOLIO_JAN_EVIDENCE_INCOMPLETE")
    return bindings


def _verified_product_image_extension(
    repository_root: Path,
    *,
    product_id: str,
    expected_sha256: str,
) -> ProductImageExtension:
    """Bind the local filename extension to the captured bytes, not the URL."""

    raw = _read_bytes(
        repository_root / RAKUTEN_PRIVATE_RELATIVE_PATH / f"{product_id}.image",
        maximum=MAX_IMAGE_BYTES,
        private=True,
    )
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected_sha256):
        _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_INVALID")
    if raw.startswith(b"\xff\xd8"):
        return "jpg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_INVALID")


def product_evidence_views_v2(
    repository_root: Path,
    *,
    now: datetime | None = None,
    require_fresh_set: bool = False,
    require_verified_set: bool = False,
) -> dict[str, ProductEvidenceViewV2]:
    portfolio = load_editorial_portfolio_v2(repository_root)
    jan_evidence_bindings = product_jan_evidence_bindings_v1(
        repository_root,
        portfolio=portfolio,
        now=now,
    )
    active_now = (now or datetime.now(UTC)).astimezone(UTC)
    receipt = _load_status_receipt(repository_root)
    receipt_rows: dict[str, Mapping[str, object]] = {}
    receipt_captured_at: datetime | None = None
    if receipt is not None:
        if receipt.get("schema") != STATUS_SCHEMA or receipt.get(
            "portfolio_sha256"
        ) != portfolio_sha256(repository_root):
            if require_fresh_set or require_verified_set:
                _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
            receipt = None
        else:
            receipt_captured_at = _parse_timestamp(receipt["captured_at"])
            rows = _list(receipt["products"])
            for raw in rows:
                row = _mapping(raw)
                if set(row) != {
                    "product_id",
                    "state",
                    "retrieved_at",
                    "item_code",
                    "response_sha256",
                    "affiliate_response_sha256",
                    "image_sha256",
                }:
                    _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
                product_id = _text(row["product_id"], maximum=160)
                if product_id in receipt_rows:
                    _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
                receipt_rows[product_id] = row
    if (require_fresh_set or require_verified_set) and (
        receipt is None
        or receipt_captured_at is None
        or active_now - receipt_captured_at > portfolio.freshness
        or active_now < receipt_captured_at
        or set(receipt_rows) != {product.product_id for product in portfolio.products}
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_EXPIRED")

    views: dict[str, ProductEvidenceViewV2] = {}
    for binding in portfolio.products:
        status_row = receipt_rows.get(binding.product_id)
        if status_row is None:
            views[binding.product_id] = ProductEvidenceViewV2(
                binding.product_id, "expired", "1970-01-01T00:00:00Z", None
            )
            continue
        raw_state = status_row.get("state")
        if raw_state == "verified":
            stored_state: Literal["verified", "not_found", "ambiguous"] = "verified"
        elif raw_state == "not_found":
            stored_state = "not_found"
        elif raw_state == "ambiguous":
            stored_state = "ambiguous"
        else:
            _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
        retrieved = _parse_timestamp(status_row.get("retrieved_at"))
        state: EvidenceState = stored_state
        if active_now < retrieved or active_now - retrieved > portfolio.freshness:
            state = "expired"
        evidence: RakutenProductEvidence | None = None
        image_extension: ProductImageExtension | None = None
        jan_evidence_sha256 = jan_evidence_bindings.get(binding.product_id)
        if stored_state == "verified":
            binding = resolve_rakuten_identity_v1(
                repository_root, binding, now=active_now
            )
            verified_hashes = (
                status_row.get("response_sha256"),
                status_row.get("affiliate_response_sha256"),
                status_row.get("image_sha256"),
            )
            if (
                binding.rakuten_item_code is None
                or status_row.get("item_code") != binding.rakuten_item_code
                or any(
                    type(value) is not str or SHA256_RE.fullmatch(value) is None
                    for value in verified_hashes
                )
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
            if state == "verified":
                try:
                    evidence = read_rakuten_product_evidence(
                        repository_root, product_id=binding.product_id
                    )
                except EditorialPilotFailure:
                    _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
                _validate_rakuten_identity(
                    binding,
                    evidence,
                    jan_evidence_sha256=jan_evidence_sha256,
                )
                if (
                    _parse_timestamp(evidence.retrieved_at) != retrieved
                    or status_row.get("item_code") != evidence.item_code
                    or status_row.get("response_sha256") != evidence.response_sha256
                    or status_row.get("affiliate_response_sha256")
                    != evidence.affiliate_response_sha256
                    or status_row.get("image_sha256") != evidence.image_sha256
                ):
                    _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
                image_extension = _verified_product_image_extension(
                    repository_root,
                    product_id=binding.product_id,
                    expected_sha256=evidence.image_sha256,
                )
        else:
            if (
                status_row.get("item_code") is not None
                or status_row.get("affiliate_response_sha256") is not None
                or status_row.get("image_sha256") is not None
                or type(status_row.get("response_sha256")) is not str
                or SHA256_RE.fullmatch(cast(str, status_row["response_sha256"])) is None
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
        if (require_fresh_set or require_verified_set) and state == "expired":
            _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_EXPIRED")
        if require_verified_set and (state != "verified" or evidence is None):
            _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INCOMPLETE")
        views[binding.product_id] = ProductEvidenceViewV2(
            product_id=binding.product_id,
            state=state,
            retrieved_at=retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
            evidence=evidence,
            image_extension=image_extension,
            jan_evidence_sha256=jan_evidence_sha256,
        )
    return views


def product_evidence_readiness_v2(
    repository_root: Path,
    *,
    now: datetime | None = None,
) -> ProductEvidenceReadinessV2:
    """Return a URL-free completion summary safe for operator diagnostics."""

    portfolio = load_editorial_portfolio_v2(repository_root)
    views = product_evidence_views_v2(repository_root, now=now)
    verified = {
        product_id
        for product_id, view in views.items()
        if view.state == "verified" and view.evidence is not None
    }
    missing_registry = tuple(
        sorted(
            product.product_id
            for product in portfolio.products
            if product.rakuten_item_code is None and product.product_id not in verified
        )
    )
    unverified = tuple(
        sorted(
            product.product_id
            for product in portfolio.products
            if product.product_id not in verified
        )
    )
    card_count = sum(len(article.product_ids) for article in portfolio.articles)
    verified_cards = sum(
        1
        for article in portfolio.articles
        for product_id in article.product_ids
        if product_id in verified
    )
    required_ctas = card_count * 2
    sales_audit = portfolio.manufacturer_sales_state_audit
    sales_rows = sales_audit.products if sales_audit is not None else ()
    sales_available = {row.product_id for row in sales_rows if row.state == "AVAILABLE"}
    verified_ctas = (
        sum(
            1
            for article in portfolio.articles
            for product_id in article.product_ids
            if product_id in verified and product_id in sales_available
        )
        * 2
    )
    sales_out_of_stock = tuple(
        sorted(row.product_id for row in sales_rows if row.state == "OUT_OF_STOCK")
    )
    sales_unknown = tuple(
        sorted(row.product_id for row in sales_rows if row.state == "UNKNOWN")
    )
    sales_discontinued = tuple(
        sorted(row.product_id for row in sales_rows if row.state == "DISCONTINUED")
    )
    sales_recheck = tuple(
        sorted(row.product_id for row in sales_rows if row.recheck_required)
    )
    sales_ineligible = tuple(
        sorted(row.product_id for row in sales_rows if not row.model_is_available)
    )
    sales_contract_complete = (
        sales_audit is not None
        and len(sales_rows) == len(portfolio.products)
        and sales_audit.known_product_count == len(portfolio.products)
    )
    try:
        require_manufacturer_sales_state_for_products_v1(
            portfolio,
            tuple(product.product_id for product in portfolio.products),
            now=now,
        )
        sales_publication_eligible = sales_contract_complete
    except EditorialPortfolioV2Failure:
        sales_publication_eligible = False
    complete = (
        card_count == 37
        and required_ctas == 74
        and not missing_registry
        and not unverified
        and verified_cards == card_count
        and verified_ctas == required_ctas
        and sales_publication_eligible
    )
    return ProductEvidenceReadinessV2(
        complete=complete,
        product_count=len(portfolio.products),
        verified_product_count=len(verified),
        product_card_count=card_count,
        verified_product_card_count=verified_cards,
        affiliate_cta_count=required_ctas,
        verified_affiliate_cta_count=verified_ctas,
        missing_registry_product_ids=missing_registry,
        unverified_product_ids=unverified,
        manufacturer_sales_state_contract_complete=sales_contract_complete,
        manufacturer_sales_state_publication_eligible=sales_publication_eligible,
        manufacturer_sales_state_checked_at_utc=(
            sales_audit.checked_at_utc if sales_audit is not None else None
        ),
        manufacturer_sales_state_known_product_count=(
            sales_audit.known_product_count if sales_audit is not None else 0
        ),
        manufacturer_sales_state_available_product_count=len(sales_available),
        manufacturer_sales_state_out_of_stock_product_count=len(sales_out_of_stock),
        manufacturer_sales_state_unknown_product_ids=sales_unknown,
        manufacturer_sales_state_discontinued_product_ids=sales_discontinued,
        manufacturer_sales_state_out_of_stock_product_ids=sales_out_of_stock,
        manufacturer_sales_state_recheck_product_ids=sales_recheck,
        manufacturer_sales_state_ineligible_product_ids=sales_ineligible,
        manufacturer_sales_state_scope=(
            sales_audit.availability_scope if sales_audit is not None else "UNAVAILABLE"
        ),
        manufacturer_state_establishes_exact_rakuten_variant=False,
        affiliate_variant_eligibility=("SEPARATE_EXACT_VARIANT_EVIDENCE_REQUIRED"),
    )


def require_manufacturer_sales_state_for_products_v1(
    portfolio: EditorialPortfolioV2,
    product_ids: tuple[str, ...],
    *,
    now: datetime | None = None,
) -> ManufacturerSalesStateAuditV1:
    """Require a current, exact and AVAILABLE manufacturer state for selection."""

    audit = portfolio.manufacturer_sales_state_audit
    if audit is None:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_UNVERIFIED")
    active_now = now or datetime.now(UTC)
    if active_now.tzinfo is None:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_UNVERIFIED")
    active_now = active_now.astimezone(UTC)
    rows = audit.product_by_id
    selected = tuple(rows.get(product_id) for product_id in product_ids)
    if (
        not product_ids
        or len(product_ids) != len(set(product_ids))
        or any(row is None or not row.known_state for row in selected)
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_UNVERIFIED")
    try:
        checked_at_values = tuple(
            datetime.fromisoformat(
                row.checked_at_utc.replace("Z", "+00:00")
            ).astimezone(UTC)
            for row in selected
            if row is not None
        )
    except ValueError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_UNVERIFIED")
    if any(
        (age := active_now - checked_at) < -MANUFACTURER_SALES_STATE_MAX_FUTURE_SKEW
        or age > MANUFACTURER_SALES_STATE_FRESHNESS
        for checked_at in checked_at_values
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_STALE")
    if any(not row.model_is_available for row in selected if row is not None):
        _fail("RAOS_EDITORIAL_PORTFOLIO_MANUFACTURER_SALES_STATE_INELIGIBLE")
    return audit


def _anchor_attributes(tag: str) -> dict[str, str]:
    return {
        name.casefold(): value
        for name, _quote, value in re.findall(
            r"([:\w-]+)\s*=\s*([\"'])(.*?)\2", tag, flags=re.DOTALL
        )
    }


def _replace_product_anchors(
    markup: str,
    *,
    article: ArticleBindingV2,
    portfolio: EditorialPortfolioV2,
    evidence_views: Mapping[str, ProductEvidenceViewV2],
) -> str:
    bindings = portfolio.product_by_id
    counts: dict[tuple[str, str], int] = {}
    expected = {
        (product_id, placement)
        for product_id in article.product_ids
        for placement in ("product_card", "final_summary")
    }
    for tag in re.findall(r"<a\b[^>]*>", markup, flags=re.IGNORECASE | re.DOTALL):
        attributes = _anchor_attributes(tag)
        product_id = attributes.get("data-raos-product-id")
        placement = attributes.get("data-raos-placement")
        if (product_id is None) != (placement is None) or (
            product_id is not None and (product_id, placement) not in expected
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")

    def replace(match: re.Match[str]) -> str:
        opening = match.group(1)
        attributes = _anchor_attributes(opening)
        product_id = attributes.get("data-raos-product-id")
        placement = attributes.get("data-raos-placement")
        if product_id not in article.product_ids or placement not in {
            "product_card",
            "final_summary",
        }:
            return match.group(0)
        binding = bindings[product_id]
        view = evidence_views[product_id]
        sales_state = portfolio.manufacturer_sales_state_by_product_id.get(product_id)
        sales_state_allows_cta = (
            sales_state is not None and sales_state.state == "AVAILABLE"
        )
        counts[(product_id, placement)] = counts.get((product_id, placement), 0) + 1
        described = attributes.get("aria-describedby")
        described_attr = (
            f' aria-describedby="{escape(described, quote=True)}"' if described else ""
        )
        shared = (
            f' data-raos-article-id="{escape(article.article_id, quote=True)}"'
            f' data-raos-product-id="{escape(product_id, quote=True)}"'
            f' data-raos-placement="{placement}"'
            f"{described_attr}"
        )
        verified_label = (
            "楽天市場で型番・在庫・販売元を確認する"
            if placement == "product_card"
            else "楽天市場でこの候補の型番・在庫を確認する"
        )
        fallback_checks_sales_state = (
            placement == "final_summary" or not sales_state_allows_cta
        )
        fallback_label = (
            "メーカー公式で販売状況を確認する"
            if fallback_checks_sales_state
            else "メーカー公式で仕様と型番を確認する"
        )
        fallback_url = (
            sales_state.status_evidence_urls[0]
            if fallback_checks_sales_state and sales_state is not None
            else binding.official_url
        )
        if (
            sales_state_allows_cta
            and view.state == "verified"
            and view.evidence is not None
        ):
            return (
                '<a class="rakuten-cta raos-cta" href="'
                + escape(view.evidence.destination_url, quote=True)
                + '" rel="sponsored nofollow"'
                + shared
                + f'>{verified_label} <span aria-hidden="true">→</span></a>'
            )
        return (
            '<a class="official-product-link raos-cta" href="'
            + escape(fallback_url, quote=True)
            + '" rel="noopener noreferrer"'
            + shared
            + f'>{fallback_label} <span aria-hidden="true">→</span></a>'
        )

    result = re.sub(
        r"(<a\b(?=[^>]*\bdata-raos-product-id=[\"'][^\"']+[\"'])"
        r"(?=[^>]*\bdata-raos-placement=[\"'](?:product_card|final_summary)[\"'])"
        r"[^>]*>).*?</a>",
        replace,
        markup,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if counts != {key: 1 for key in expected}:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
    return result


_UNVERIFIED_PRODUCT_MEDIA_LABEL = "商品画像未確認・購入導線停止"


def _product_media_status(
    product_id: str, *, placement: Literal["product_card", "comparison_table"]
) -> str:
    compact = (
        " raos-product-image-status--compact" if placement == "comparison_table" else ""
    )
    element = "span" if placement == "comparison_table" else "p"
    return (
        f'<{element} class="raos-product-image-status{compact}" '
        f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
        f'data-raos-product-image-placement="{placement}" '
        'data-raos-product-image-state="unverified">'
        f"{_UNVERIFIED_PRODUCT_MEDIA_LABEL}</{element}>"
    )


def _verified_product_image(
    *,
    product_id: str,
    official_name: str,
    src: str,
    placement: Literal["product_card", "comparison_table"],
) -> str:
    if placement == "product_card":
        css_class = ""
        width = height = 128
        alt = f"{official_name}の商品画像（楽天市場の商品情報より）"
    else:
        css_class = ' class="raos-comparison__product-image"'
        width = height = 64
        alt = f"{official_name}の商品画像"
    return (
        f'<img{css_class} src="{escape(src, quote=True)}" '
        f'alt="{escape(alt, quote=True)}" width="{width}" height="{height}" '
        'loading="lazy" '
        f'data-raos-product-image-id="{escape(product_id, quote=True)}" '
        f'data-raos-product-image-placement="{placement}" '
        'data-raos-product-image-state="verified">'
    )


def _replace_product_images(
    markup: str,
    *,
    article: ArticleBindingV2,
    portfolio: EditorialPortfolioV2,
    evidence_views: Mapping[str, ProductEvidenceViewV2],
    mode: Literal["local", "production"],
) -> str:
    bindings = portfolio.product_by_id
    observed: set[str] = set()
    all_cards = tuple(
        re.finditer(
            r"<article\b(?=[^>]*\bdata-raos-product-id=[\"'][^\"']+[\"'])[^>]*>"
            r".*?</article>",
            markup,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    card_product_ids = tuple(
        _anchor_attributes(card.group(0).split(">", 1)[0] + ">").get(
            "data-raos-product-id", ""
        )
        for card in all_cards
    )
    if (
        len(all_cards) != len(article.product_ids)
        or len(card_product_ids) != len(set(card_product_ids))
        or set(card_product_ids) != set(article.product_ids)
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")

    for product_id in article.product_ids:
        binding = bindings[product_id]
        view = evidence_views[product_id]
        card_pattern = re.compile(
            r"(<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
            + re.escape(product_id)
            + r"[\"'])[^>]*>)(.*?)(</article>)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        if len(tuple(card_pattern.finditer(markup))) != 1:
            _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")

        def replace_card(match: re.Match[str]) -> str:
            body = match.group(2)
            media_divs = tuple(
                candidate
                for candidate in re.finditer(
                    r"<div\b[^>]*>.*?</div>",
                    body,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if "raos-product-card__media"
                in _anchor_attributes(candidate.group(0).split(">", 1)[0] + ">")
                .get("class", "")
                .split()
            )
            figures = tuple(
                candidate
                for candidate in re.finditer(
                    r"<figure\b[^>]*>.*?</figure>",
                    body,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                if "data-raos-product-image-id=" in candidate.group(0)
            )
            containers = (*media_divs, *figures)
            if len(containers) != 1:
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            container = containers[0]
            fragment = container.group(0)
            images = tuple(re.finditer(r"<img\b[^>]*>", fragment, flags=re.IGNORECASE))
            statuses = tuple(
                re.finditer(
                    r"<(?P<tag>p|span)\b"
                    r"(?=[^>]*\bdata-raos-product-image-id=[\"'][^\"']+[\"'])"
                    r"[^>]*>.*?</(?P=tag)>",
                    fragment,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            )
            candidates = (*images, *statuses)
            if (
                len(candidates) != 1
                or len(tuple(re.finditer(r"<img\b", body, flags=re.I))) != len(images)
                or len(
                    tuple(
                        re.finditer(
                            r"\bdata-raos-product-image-id\s*=",
                            body,
                            flags=re.IGNORECASE,
                        )
                    )
                )
                != 1
                or re.search(r"<source\b", body, flags=re.IGNORECASE) is not None
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            candidate = candidates[0].group(0)
            attributes = _anchor_attributes(candidate.split(">", 1)[0] + ">")
            if (
                attributes.get("data-raos-product-image-id") != product_id
                or attributes.get("data-raos-product-image-state")
                not in {"neutral", "unverified", "verified"}
                or attributes.get("data-raos-product-image-placement")
                not in {None, "product_card"}
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            if view.state == "verified" and view.evidence is not None:
                if view.image_extension is None:
                    _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_INVALID")
                image_src = (
                    f"/raos-product-media/{product_id}.{view.image_extension}"
                    if mode == "local"
                    else view.evidence.image_url
                )
                product_media = _verified_product_image(
                    product_id=product_id,
                    official_name=binding.official_name,
                    src=image_src,
                    placement="product_card",
                )
            else:
                product_media = _product_media_status(
                    product_id, placement="product_card"
                )
            media_container = (
                f'<div class="raos-product-card__media">{product_media}</div>'
            )
            observed.add(product_id)
            replaced_body = (
                body[: container.start()] + media_container + body[container.end() :]
            )
            return match.group(1) + replaced_body + match.group(3)

        markup, replacements = card_pattern.subn(replace_card, markup, count=1)
        if replacements != 1:
            _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
    expected = set(article.product_ids)
    if observed != expected:
        _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")

    comparison_pattern = re.compile(
        r"<img\b(?=[^>]*\bdata-raos-product-image-placement="
        r"[\"']comparison_table[\"'])[^>]*>"
        r"|<span\b(?=[^>]*\bdata-raos-product-image-placement="
        r"[\"']comparison_table[\"'])[^>]*>.*?</span>",
        flags=re.IGNORECASE | re.DOTALL,
    )
    comparison_counts = {product_id: 0 for product_id in article.product_ids}

    def replace_comparison_media(match: re.Match[str]) -> str:
        candidate = match.group(0)
        attributes = _anchor_attributes(candidate.split(">", 1)[0] + ">")
        product_id = attributes.get("data-raos-product-image-id", "")
        if product_id not in comparison_counts or attributes.get(
            "data-raos-product-image-state"
        ) not in {"unverified", "verified"}:
            _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
        comparison_counts[product_id] += 1
        view = evidence_views[product_id]
        if view.state == "verified" and view.evidence is not None:
            # The exact product image is rendered once in its product card.
            # Removing the blocked table marker avoids duplicate media nodes
            # being mistaken for additional independently verified products.
            return ""
        return _product_media_status(product_id, placement="comparison_table")

    markup = comparison_pattern.sub(replace_comparison_media, markup)
    expected_comparison_count = 2 if article.source_kind == "st1704_renderer" else 0
    comparison_images = tuple(
        re.finditer(
            r"<img\b(?=[^>]*\bclass=[\"'][^\"']*"
            r"\braos-comparison__product-image\b)[^>]*>",
            markup,
            flags=re.IGNORECASE,
        )
    )
    if (
        comparison_counts
        != {product_id: expected_comparison_count for product_id in article.product_ids}
        or comparison_images
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
    return markup


def _replace_product_cta_notes(
    markup: str,
    *,
    article: ArticleBindingV2,
    portfolio: EditorialPortfolioV2,
    evidence_views: Mapping[str, ProductEvidenceViewV2],
) -> str:
    bindings = portfolio.product_by_id
    for product_id in article.product_ids:
        binding = bindings[product_id]
        view = evidence_views[product_id]
        sales_state = portfolio.manufacturer_sales_state_by_product_id.get(product_id)
        sales_state_allows_cta = (
            sales_state is not None and sales_state.state == "AVAILABLE"
        )
        if (
            sales_state_allows_cta
            and view.state == "verified"
            and view.evidence is not None
        ):
            note = (
                f"楽天市場の商品ページで、{binding.official_name}"
                f"（代表型番：{binding.representative_model}）の型番、販売元、"
                "価格、在庫、商品画像を確認できます。"
            )
        elif sales_state is not None and sales_state.state == "OUT_OF_STOCK":
            note = (
                f"メーカー公式の販売ページで、{binding.official_name}"
                f"（代表型番：{binding.representative_model}）の販売状況を確認できます。"
                "メーカー公式通販で在庫切れのため、楽天購入リンクは掲載していません。"
                "仕様は上記の公式出典で確かめ、再入荷または後継機を確認してから"
                "再検討してください。"
            )
        elif sales_state is not None and sales_state.state == "UNKNOWN":
            note = (
                f"メーカー公式ページで、{binding.official_name}"
                f"（代表型番：{binding.representative_model}）の仕様を確認できます。"
                "現行販売を確認できていないため購入候補として勧めず、"
                "楽天購入リンクは掲載していません。仕様参考として、"
                "メーカー公式で販売状況を確認してください。"
            )
        else:
            note = (
                f"メーカー公式ページで、{binding.official_name}"
                f"（代表型番：{binding.representative_model}）の仕様を確認できます。"
                "一致する楽天商品を確認できなかったため、楽天購入リンクは掲載していません。"
            )
        card_pattern = re.compile(
            r"(<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
            + re.escape(product_id)
            + r"[\"'])[^>]*>)(.*?)(</article>)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        def replace_card(match: re.Match[str]) -> str:
            body, replacements = re.subn(
                r"(<(?P<tag>[a-z][a-z0-9]*)\b"
                r"(?=[^>]*\bclass=[\"'][^\"']*\bcta-note\b[^\"']*[\"'])"
                r"[^>]*>).*?(</(?P=tag)>)",
                lambda note_match: (
                    note_match.group(1) + escape(note) + note_match.group(3)
                ),
                match.group(2),
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if replacements != 1:
                _fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
            return match.group(1) + body + match.group(3)

        markup, replacements = card_pattern.subn(replace_card, markup, count=1)
        if replacements != 1:
            _fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
    return markup


def materialize_article_v2(
    markup: str,
    *,
    article: ArticleBindingV2,
    portfolio: EditorialPortfolioV2,
    evidence_views: Mapping[str, ProductEvidenceViewV2],
    mode: Literal["local", "production"],
) -> str:
    if (
        type(markup) is not str
        or not 1 <= len(markup.encode("utf-8")) <= MAX_CONTENT_BYTES
        or mode not in {"local", "production"}
        or markup.count('class="raos-editorial-v2"') != 1
        or re.search(
            r"<h([12])\b[^>]*>(?:(?!</h\1>).)*?<br\b",
            markup,
            flags=re.I | re.S,
        )
        or not _article_disclosure_is_exact(
            markup,
            article_id=article.article_id,
            product_ids=article.product_ids,
        )
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    if mode == "production" and article.product_ids:
        require_manufacturer_sales_state_for_products_v1(portfolio, article.product_ids)
        if any(
            evidence_views.get(product_id) is None
            or evidence_views[product_id].state != "verified"
            or evidence_views[product_id].evidence is None
            for product_id in article.product_ids
        ):
            _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INCOMPLETE")
    result = _replace_product_anchors(
        markup,
        article=article,
        portfolio=portfolio,
        evidence_views=evidence_views,
    )
    result = _replace_product_cta_notes(
        result,
        article=article,
        portfolio=portfolio,
        evidence_views=evidence_views,
    )
    result = _replace_product_images(
        result,
        article=article,
        portfolio=portfolio,
        evidence_views=evidence_views,
        mode=mode,
    )
    if mode == "local" and re.search(r"\bsrc=([\"'])https://", result, flags=re.I):
        _fail("RAOS_EDITORIAL_PORTFOLIO_LOCAL_EXTERNAL_IMAGE_INVALID")
    return result


def materialize_source_article_v2(
    repository_root: Path,
    article: ArticleBindingV2,
    *,
    evidence_views: Mapping[str, ProductEvidenceViewV2],
    mode: Literal["local", "production"],
) -> str:
    path = (
        repository_root
        / SOURCE_FIXTURE_RELATIVE_PATH
        / "articles"
        / (f"{article.production_slug}.html")
    )
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_UNAVAILABLE")
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size != len(raw)
        or not 1 <= len(raw) <= MAX_CONTENT_BYTES
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    try:
        markup = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
    return materialize_article_v2(
        markup,
        article=article,
        portfolio=load_editorial_portfolio_v2(repository_root),
        evidence_views=evidence_views,
        mode=mode,
    )


def portfolio_sha256(repository_root: Path) -> str:
    path = repository_root / PORTFOLIO_RELATIVE_PATH
    try:
        raw = path.read_bytes()
    except OSError:
        _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "ArticleBindingV2",
    "EditorialPortfolioV2",
    "EditorialPortfolioV2Failure",
    "LOCAL_FIXTURE_RELATIVE_PATH",
    "LOCAL_MEDIA_RELATIVE_PATH",
    "JAN_EVIDENCE_RELATIVE_PATH",
    "JAN_EVIDENCE_SNAPSHOT_RELATIVE_ROOT",
    "MANUFACTURER_SALES_STATE_FRESHNESS",
    "MANUFACTURER_SALES_STATE_RELATIVE_PATH",
    "ManufacturerSalesStateAuditV1",
    "ManufacturerSalesStateV1",
    "ManufacturerVariantCaveatV1",
    "PORTFOLIO_RELATIVE_PATH",
    "PRODUCTION_FIXTURE_RELATIVE_PATH",
    "ProductBindingV2",
    "ProductEvidenceReadinessV2",
    "ProductEvidenceViewV2",
    "STATUS_RELATIVE_PATH",
    "load_editorial_portfolio_v2",
    "load_manufacturer_sales_state_audit_v1",
    "materialize_article_v2",
    "materialize_source_article_v2",
    "portfolio_sha256",
    "product_evidence_readiness_v2",
    "product_evidence_views_v2",
    "product_jan_evidence_bindings_v1",
    "require_manufacturer_sales_state_for_products_v1",
]
