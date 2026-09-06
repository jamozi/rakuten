"""Read-only product review applicability from tracked portfolio metadata.

This adapter requires reviews; it does not perform them, verify official sources,
check runtime freshness, or confer publication authority. No current tracked kind
proves a product-specific exemption: in particular, generic suitcase tokens do
not prove the absence of batteries or smart features. Uncertainty stays REQUIRED,
never NOT_APPLICABLE. Adding an exemption needs a separate, grounded policy change.

Call classify_product_audit_scope for every preparation/replay and bind its
to_document() into the reviewed inputs. An in-memory result can require_current()
before reuse. Source fingerprints bind the exact V2 source and V3 projection
bytes, including new/unknown metadata; they are not claim/source freshness checks.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Literal, NoReturn, cast


SCHEMA = "RAOS_READER_RELEASE_APPLICABILITY_V1"
SOURCE_PATH = Path("changes/editorial-portfolio-v2/editorial-portfolio.v2.json")
PROJECTION_PATH = Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json")
MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_ROWS = 512
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}\Z", re.ASCII)
CATEGORY_CODES = {"移動": "mobility", "備え": "preparedness", "家事": "household"}
KIND_RULES = (
    ("suitcase", "mobility", frozenset({"スーツケース", "キャリーケース"})),
    (
        "portable_power_station",
        "preparedness",
        frozenset({"ポータブル電源", "Portable Power Station"}),
    ),
    ("dishwasher", "household", frozenset({"食器洗い乾燥機", "食洗機"})),
    (
        "robot_vacuum",
        "household",
        frozenset(
            {"ロボット掃除機", "Robot Vacuum", "Roomba", "掃除機&床拭きロボット"}
        ),
    ),
)
KNOWN_PRODUCT_FIELDS = frozenset(
    {
        "product_id",
        "official_name",
        "official_models",
        "representative_model",
        "official_url",
        "product_kind_tokens",
        "required_title_tokens",
        "rakuten_item_code",
        "rakuten_shop_code",
        "official_jan",
        "additional_forbidden_title_tokens",
    }
)
BASIS_FIELDS = (
    "product_id",
    "product_kind_tokens",
    "official_name",
    "official_models",
    "representative_model",
    "official_url",
)


class ReaderReleaseApplicabilityFailure(ValueError):
    """A stable failure with no source values, URLs, or filesystem paths."""


def _fail(code: str) -> NoReturn:
    raise ReaderReleaseApplicabilityFailure(
        f"RAOS_READER_APPLICABILITY_{code}"
    ) from None


@dataclass(frozen=True)
class ProductAuditRequirementV1:
    basis_status: Literal["TRACKED_KIND", "UNKNOWN"]
    rationale: str

    def to_document(self) -> dict[str, object]:
        return {
            "state": "REQUIRED",
            "basis_status": self.basis_status,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class ProductAuditApplicabilityV1:
    product_id: str
    product_kind: str
    product_kind_tokens: tuple[str, ...]
    official_name: str
    official_models: tuple[str, ...]
    representative_model: str
    official_url: str
    article_categories: tuple[tuple[str, str], ...]
    source_references: tuple[str, ...]
    unrecognized_metadata_fields: tuple[str, ...]
    smart_device: ProductAuditRequirementV1
    disposal: ProductAuditRequirementV1

    def to_document(self) -> dict[str, object]:
        return {
            "product_id": self.product_id,
            "product_kind": self.product_kind,
            "basis": {
                "product_kind_tokens": list(self.product_kind_tokens),
                "official_name": self.official_name,
                "official_models": list(self.official_models),
                "representative_model": self.representative_model,
                "official_url": self.official_url,
                "official_reference_status": "TRACKED_REFERENCE_ONLY",
                "article_categories": dict(self.article_categories),
                "source_references": list(self.source_references),
                "unrecognized_metadata_fields": list(self.unrecognized_metadata_fields),
            },
            "smart_device": self.smart_device.to_document(),
            "disposal": self.disposal.to_document(),
        }


@dataclass(frozen=True)
class ReaderReleaseApplicabilityV1:
    retained_product_ids: tuple[str, ...]
    products: tuple[ProductAuditApplicabilityV1, ...]
    source_fingerprints: tuple[tuple[str, str], ...]

    @property
    def smart_device_product_ids(self) -> tuple[str, ...]:
        # Every decision this policy can establish is REQUIRED, including UNKNOWN.
        return tuple(product.product_id for product in self.products)

    @property
    def disposal_product_ids(self) -> tuple[str, ...]:
        return tuple(product.product_id for product in self.products)

    @property
    def source_fingerprint(self) -> str:
        raw = json.dumps(
            {"schema": SCHEMA, "sources": dict(self.source_fingerprints)},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def to_document(self) -> dict[str, object]:
        return {
            "schema": SCHEMA,
            "purpose": "REQUIRE_REVIEWS_ONLY",
            "audit_completion": "NOT_EVALUATED",
            "publication_authority": False,
            "retained_product_ids": list(self.retained_product_ids),
            "smart_device_product_ids": list(self.smart_device_product_ids),
            "disposal_product_ids": list(self.disposal_product_ids),
            "source_fingerprint": self.source_fingerprint,
            "source_fingerprints": dict(self.source_fingerprints),
            "products": [product.to_document() for product in self.products],
        }

    def require_current(self, root: Path) -> None:
        """Reject stale sources or an altered decision before reusing this record."""
        if self != classify_product_audit_scope(root, self.retained_product_ids):
            _fail("SOURCE_CHANGED")


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("SOURCE_INVALID")
    return cast(dict[str, object], value)


def _text(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > 4096:
        _fail("SOURCE_INVALID")
    return value


def _strings(value: object) -> tuple[str, ...]:
    if type(value) is not list or len(value) > MAX_ROWS:
        _fail("SOURCE_INVALID")
    values = tuple(_text(item) for item in cast(list[object], value))
    if len(set(values)) != len(values):
        _fail("SOURCE_INVALID")
    return tuple(sorted(values))


def _ids(value: object, *, caller: bool = False) -> tuple[str, ...]:
    code = "PRODUCT_IDS_INVALID" if caller else "SOURCE_INVALID"
    if type(value) is not (tuple if caller else list):
        _fail(code)
    values = cast(tuple[object, ...] | list[object], value)
    if len(values) > MAX_ROWS or any(
        type(item) is not str or ID_RE.fullmatch(item) is None for item in values
    ):
        _fail(code)
    result = cast(tuple[str, ...], tuple(values))
    if len(set(result)) != len(result):
        _fail(code)
    return tuple(sorted(result))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            _fail("SOURCE_INVALID")
        result[key] = value
    return result


def _invalid_constant(_value: str) -> NoReturn:
    _fail("SOURCE_INVALID")


def _read_source(
    root: Path, relative: Path, schema: str
) -> tuple[dict[str, object], str]:
    try:
        base = root.resolve(strict=True)
        path = base
        for part in relative.parts:
            path = path / part
            if path.is_symlink():
                _fail("SOURCE_INVALID")
        if not path.is_file() or not path.resolve(strict=True).is_relative_to(base):
            _fail("SOURCE_INVALID")
        with path.open("rb") as source:
            raw = source.read(MAX_SOURCE_BYTES + 1)
        if len(raw) > MAX_SOURCE_BYTES:
            _fail("SOURCE_INVALID")
        document = _mapping(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_invalid_constant,
            )
        )
    except OSError, UnicodeError, ValueError, RecursionError:
        _fail("SOURCE_INVALID")
    if document.get("schema") != schema:
        _fail("SOURCE_INVALID")
    return document, hashlib.sha256(raw).hexdigest()


def _index(value: object, key: str) -> dict[str, tuple[int, dict[str, object]]]:
    if type(value) is not list or len(value) > MAX_ROWS:
        _fail("SOURCE_INVALID")
    result: dict[str, tuple[int, dict[str, object]]] = {}
    for position, row in enumerate(cast(list[object], value)):
        record = _mapping(row)
        identifier = _text(record.get(key))
        if ID_RE.fullmatch(identifier) is None or identifier in result:
            _fail("SOURCE_INVALID")
        result[identifier] = position, record
    return result


def _article_basis(
    source: dict[str, object], projection: dict[str, object], retained: tuple[str, ...]
) -> dict[str, tuple[tuple[tuple[str, str], ...], tuple[str, ...]]]:
    before = _index(source.get("articles"), "article_id")
    after = _index(projection.get("articles"), "article_id")
    if before.keys() != after.keys():
        _fail("ARTICLE_MAPPING_MISMATCH")
    categories: dict[str, list[tuple[str, str]]] = {product: [] for product in retained}
    references: dict[str, list[str]] = {product: [] for product in retained}
    selected = set(retained)
    for article_id in sorted(before):
        source_index, source_row = before[article_id]
        projected_index, projected_row = after[article_id]
        source_ids = _ids(source_row.get("product_ids"))
        projected_ids = _ids(projected_row.get("product_ids"))
        included = selected.intersection((*source_ids, *projected_ids))
        if not included:
            continue
        category = _text(projected_row.get("category"))
        original_category = _text(source_row.get("category"))
        if (
            source_ids != projected_ids
            or projected_row.get("v2_category") != original_category
            or (
                original_category in CATEGORY_CODES
                and CATEGORY_CODES[original_category] != category
            )
        ):
            _fail("ARTICLE_MAPPING_MISMATCH")
        for product_id in included:
            categories[product_id].append((article_id, category))
            for path, index, fields in (
                (SOURCE_PATH, source_index, ("article_id", "product_ids", "category")),
                (
                    PROJECTION_PATH,
                    projected_index,
                    ("article_id", "product_ids", "category", "v2_category"),
                ),
            ):
                references[product_id].extend(
                    f"{path.as_posix()}#/articles/{index}/{field}" for field in fields
                )
    if any(not rows for rows in categories.values()):
        _fail("PRODUCT_UNBOUND")
    return {
        product: (tuple(categories[product]), tuple(sorted(references[product])))
        for product in retained
    }


def _requirements(
    kind: str, unknown_fields: tuple[str, ...]
) -> tuple[ProductAuditRequirementV1, ProductAuditRequirementV1]:
    if unknown_fields:
        rationale = (
            "Unrecognized product metadata needs review; no unrecognized field "
            "can establish non-applicability."
        )
    elif kind == "unknown":
        rationale = (
            "Product kind or article category is missing, unrecognized, or "
            "conflicting. Both audit concerns remain unknown and require review."
        )
    elif kind == "suitcase":
        rationale = (
            "Tracked suitcase kind and mobility category do not establish the "
            "absence of batteries, powered accessories, or smart features. "
            "No product-specific non-applicability basis is tracked."
        )
    else:
        return (
            ProductAuditRequirementV1(
                "UNKNOWN",
                "Tracked electrical product requires app/cloud/security/EOL review; "
                "connectivity and service dependencies have not been established.",
            ),
            ProductAuditRequirementV1(
                "TRACKED_KIND",
                f"Tracked {kind} kind requires electrical/battery disposal, recycling "
                "and transport review. Applicable guidance has not been audited.",
            ),
        )
    required = ProductAuditRequirementV1("UNKNOWN", rationale)
    return required, required


def classify_product_audit_scope(
    root: Path, retained_product_ids: tuple[str, ...]
) -> ReaderReleaseApplicabilityV1:
    """Classify exactly the selected products, failing closed on invalid mappings.

    Unknown IDs fail; new or incomplete kinds remain REQUIRED with an unknown
    rationale. There is no metadata flag or external map that can waive reviews.
    Only the two bounded, tracked JSON sources are read. Nothing is written.
    """
    retained = _ids(retained_product_ids, caller=True)
    if not retained:
        return ReaderReleaseApplicabilityV1((), (), ())
    source, source_hash = _read_source(root, SOURCE_PATH, "RAOS_EDITORIAL_PORTFOLIO_V2")
    projection, projection_hash = _read_source(
        root, PROJECTION_PATH, "RAOS_EDITORIAL_PORTFOLIO_V3"
    )
    before = _index(source.get("products"), "product_id")
    after = _index(projection.get("products"), "product_id")
    for product_id in retained:
        if product_id not in before and product_id not in after:
            _fail("UNKNOWN_PRODUCT")
        if product_id not in before or product_id not in after:
            _fail("PRODUCT_MAPPING_MISMATCH")
        if before[product_id][1] != {
            key: value
            for key, value in after[product_id][1].items()
            if key != "product_code"
        }:
            _fail("PRODUCT_MAPPING_MISMATCH")
    articles = _article_basis(source, projection, retained)
    products: list[ProductAuditApplicabilityV1] = []
    for product_id in retained:
        source_index, row = before[product_id]
        projected_index, _projected_row = after[product_id]
        tokens = _strings(row.get("product_kind_tokens", []))
        article_categories, article_refs = articles[product_id]
        kind = next(
            (
                name
                for name, category, known_tokens in KIND_RULES
                if tokens
                and set(tokens) <= known_tokens
                and {value for _, value in article_categories} == {category}
            ),
            "unknown",
        )
        unknown_fields = tuple(sorted(set(row) - KNOWN_PRODUCT_FIELDS))
        smart, disposal = _requirements(kind, unknown_fields)
        references = tuple(
            sorted(
                (
                    *article_refs,
                    *(
                        f"{path.as_posix()}#/products/{index}/{field}"
                        for path, index in (
                            (SOURCE_PATH, source_index),
                            (PROJECTION_PATH, projected_index),
                        )
                        for field in BASIS_FIELDS
                        if field in row
                    ),
                )
            )
        )
        products.append(
            ProductAuditApplicabilityV1(
                product_id=product_id,
                product_kind=kind,
                product_kind_tokens=tokens,
                official_name=_text(row.get("official_name")),
                official_models=_strings(row.get("official_models")),
                representative_model=_text(row.get("representative_model")),
                official_url=_text(row.get("official_url")),
                article_categories=article_categories,
                source_references=references,
                unrecognized_metadata_fields=unknown_fields,
                smart_device=smart,
                disposal=disposal,
            )
        )
    return ReaderReleaseApplicabilityV1(
        retained,
        tuple(products),
        (
            (SOURCE_PATH.as_posix(), source_hash),
            (PROJECTION_PATH.as_posix(), projection_hash),
        ),
    )
