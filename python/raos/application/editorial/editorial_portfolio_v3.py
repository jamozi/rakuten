"""Read-only runtime view of the generated Editorial V3 portfolio."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Final, Mapping, NoReturn, cast


PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v3/editorial-portfolio.v3.json"
)
ARTICLE_CODE_RE: Final = re.compile(r"a[0-9]{2}\Z")
PRODUCT_CODE_RE: Final = re.compile(r"p[0-9]{2}\Z")
INTERNAL_CTA_ID_RE: Final = re.compile(
    r"icta_a[0-9]{2}_p[0-9]{2}_(?:card|final)\Z"
)
PROVIDER_SLOT_ID_RE: Final = re.compile(r"rps-a[0-9]{2}-(?:card|final)\Z")
INTERNAL_CTA_NAMESPACE: Final = "RAOS_INTERNAL_CTA_V1"
PROVIDER_SLOT_GRANULARITY: Final = "ARTICLE_PLACEMENT"
PROVIDER_SLOT_LIMIT: Final = 20


class EditorialPortfolioV3Failure(RuntimeError):
    """A stable, non-sensitive contract failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialPortfolioV3Failure(code) from None


def _mapping(value: object) -> Mapping[str, object]:
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return cast(Mapping[str, object], value)


def _rows(value: object) -> list[Mapping[str, object]]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return [_mapping(row) for row in cast(list[object], value)]


def _text(value: object) -> str:
    if type(value) is not str or value != value.strip() or not value:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return value


def _texts(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return tuple(_text(item) for item in cast(list[object], value))


def _reject_tracked_provider_measurement_id(value: object) -> None:
    if type(value) is list:
        for item in cast(list[object], value):
            _reject_tracked_provider_measurement_id(item)
        return
    if type(value) is dict:
        mapping = cast(Mapping[object, object], value)
        if {"provider_measurement_id", "rakuten_measurement_id"}.intersection(mapping):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        for item in mapping.values():
            _reject_tracked_provider_measurement_id(item)


@dataclass(frozen=True, slots=True)
class CtaBindingV3:
    article_id: str
    article_code: str
    product_id: str
    product_code: str
    snapshot_id: str
    offer_id: str
    cta_id: str
    placement: str
    placement_code: str
    provider_slot_id: str
    provider_profile_state: str


@dataclass(frozen=True, slots=True)
class ProviderSlotV3:
    """Tracked logical provider capacity without an actual provider ID."""

    provider_slot_id: str
    article_id: str
    article_code: str
    placement: str
    placement_code: str
    provider_profile_state: str


@dataclass(frozen=True, slots=True)
class ArticleBindingV3:
    article_id: str
    article_code: str
    production_slug: str
    cluster_id: str
    category_label: str
    home_order: int
    snapshot_id: str
    related_article_ids: tuple[str, ...]
    product_ids: tuple[str, ...]
    cta_bindings: tuple[CtaBindingV3, ...]


@dataclass(frozen=True, slots=True)
class ProductBindingV3:
    product_id: str
    product_code: str


@dataclass(frozen=True, slots=True)
class EditorialPortfolioV3:
    version: str
    target_origin: str
    source_sha256: str
    articles: tuple[ArticleBindingV3, ...]
    products: tuple[ProductBindingV3, ...]
    provider_slots: tuple[ProviderSlotV3, ...]

    @property
    def article_by_id(self) -> dict[str, ArticleBindingV3]:
        return {article.article_id: article for article in self.articles}

    @property
    def article_by_slug(self) -> dict[str, ArticleBindingV3]:
        return {article.production_slug: article for article in self.articles}

    @property
    def cta_by_candidate_id(self) -> dict[str, CtaBindingV3]:
        """Return explicitly namespaced internal CTA identities."""

        return {
            binding.cta_id: binding
            for article in self.articles
            for binding in article.cta_bindings
        }

    @property
    def provider_slot_by_id(self) -> dict[str, ProviderSlotV3]:
        return {slot.provider_slot_id: slot for slot in self.provider_slots}

    @property
    def provider_slot_by_key(self) -> dict[tuple[str, str], ProviderSlotV3]:
        return {(slot.article_id, slot.placement): slot for slot in self.provider_slots}


def load_editorial_portfolio_v3(repository_root: Path) -> EditorialPortfolioV3:
    if not repository_root.is_absolute():
        _fail("RAOS_EDITORIAL_V3_ROOT_INVALID")
    try:
        raw = (repository_root / PORTFOLIO_RELATIVE_PATH).read_bytes()
        document = _mapping(json.loads(raw.decode("utf-8", errors="strict")))
    except EditorialPortfolioV3Failure:
        raise
    except OSError, UnicodeError, json.JSONDecodeError:
        _fail("RAOS_EDITORIAL_V3_FILE_INVALID")
    _reject_tracked_provider_measurement_id(document)
    if (
        document.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V3"
        or document.get("version") != "3.0.0"
        or _mapping(document.get("predecessor")).get("historical_contract_preserved")
        is not True
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    policy = _mapping(document.get("rakuten_measurement_policy"))
    if (
        policy.get("internal_cta_id_format")
        != "icta_{article_code}_{product_code}_{card|final}"
        or policy.get("internal_cta_identity_count") != 74
        or policy.get("internal_cta_namespace") != INTERNAL_CTA_NAMESPACE
        or policy.get("provider_slot_format") != "rps-{article_code}-{card|final}"
        or policy.get("provider_slot_count") != PROVIDER_SLOT_LIMIT
        or policy.get("provider_slot_limit") != PROVIDER_SLOT_LIMIT
        or policy.get("provider_slot_granularity") != PROVIDER_SLOT_GRANULARITY
        or policy.get("provider_measurement_id_storage") != "OWNER_PRIVATE_ONLY"
        or policy.get("provider_profile_state") != "UNVERIFIED_DISABLED"
        or policy.get("live_link_mutation_allowed") is not False
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")

    products: list[ProductBindingV3] = []
    product_ids: set[str] = set()
    product_codes: set[str] = set()
    for row in _rows(document.get("products")):
        product_id = _text(row.get("product_id"))
        product_code = _text(row.get("product_code"))
        if (
            product_id in product_ids
            or product_code in product_codes
            or PRODUCT_CODE_RE.fullmatch(product_code) is None
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        product_ids.add(product_id)
        product_codes.add(product_code)
        products.append(ProductBindingV3(product_id, product_code))

    provider_slots: list[ProviderSlotV3] = []
    provider_slots_by_id: dict[str, ProviderSlotV3] = {}
    provider_slots_by_key: dict[tuple[str, str], ProviderSlotV3] = {}
    expected_slot_fields = {
        "provider_slot_id",
        "article_id",
        "article_code",
        "placement",
        "placement_code",
        "provider_profile_state",
    }
    for row in _rows(document.get("rakuten_provider_slots")):
        if set(row) != expected_slot_fields:
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        slot = ProviderSlotV3(
            provider_slot_id=_text(row.get("provider_slot_id")),
            article_id=_text(row.get("article_id")),
            article_code=_text(row.get("article_code")),
            placement=_text(row.get("placement")),
            placement_code=_text(row.get("placement_code")),
            provider_profile_state=_text(row.get("provider_profile_state")),
        )
        expected_placement_code = {
            "product_card": "card",
            "final_summary": "final",
        }.get(slot.placement)
        slot_key = (slot.article_id, slot.placement)
        if (
            expected_placement_code is None
            or slot.placement_code != expected_placement_code
            or slot.provider_slot_id != f"rps-{slot.article_code}-{slot.placement_code}"
            or PROVIDER_SLOT_ID_RE.fullmatch(slot.provider_slot_id) is None
            or ARTICLE_CODE_RE.fullmatch(slot.article_code) is None
            or slot.provider_profile_state != "UNVERIFIED_DISABLED"
            or slot.provider_slot_id in provider_slots_by_id
            or slot_key in provider_slots_by_key
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        provider_slots.append(slot)
        provider_slots_by_id[slot.provider_slot_id] = slot
        provider_slots_by_key[slot_key] = slot
    if len(provider_slots) != PROVIDER_SLOT_LIMIT:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")

    articles: list[ArticleBindingV3] = []
    article_ids: set[str] = set()
    article_codes: set[str] = set()
    all_cta_ids: set[str] = set()
    referenced_provider_slot_ids: set[str] = set()
    for row in _rows(document.get("articles")):
        article_id = _text(row.get("article_id"))
        article_code = _text(row.get("article_code"))
        production_slug = _text(row.get("production_slug"))
        cluster_id = _text(row.get("cluster_id"))
        category_label = _text(row.get("category_label"))
        home_order = row.get("home_order")
        snapshot_id = _text(row.get("snapshot_id"))
        related = _texts(row.get("related_article_ids"))
        product_refs = _texts(row.get("product_ids"))
        if (
            article_id in article_ids
            or article_code in article_codes
            or ARTICLE_CODE_RE.fullmatch(article_code) is None
            or cluster_id not in {"mobility", "household", "preparedness"}
            or type(home_order) is not int
            or home_order <= 0
            or len(related) < 2
            or len(related) != len(set(related))
            or not set(product_refs).issubset(product_ids)
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        article_ids.add(article_id)
        article_codes.add(article_code)
        bindings: list[CtaBindingV3] = []
        for binding_value in _rows(row.get("cta_bindings")):
            binding = CtaBindingV3(
                article_id=_text(binding_value.get("article_id")),
                article_code=_text(binding_value.get("article_code")),
                product_id=_text(binding_value.get("product_id")),
                product_code=_text(binding_value.get("product_code")),
                snapshot_id=_text(binding_value.get("snapshot_id")),
                offer_id=_text(binding_value.get("offer_id")),
                cta_id=_text(binding_value.get("cta_id")),
                placement=_text(binding_value.get("placement")),
                placement_code=_text(binding_value.get("placement_code")),
                provider_slot_id=_text(binding_value.get("provider_slot_id")),
                provider_profile_state=_text(
                    binding_value.get("provider_profile_state")
                ),
            )
            expected_cta_id = (
                f"icta_{binding.article_code}_{binding.product_code}_"
                f"{binding.placement_code}"
            )
            provider_slot = provider_slots_by_id.get(binding.provider_slot_id)
            if (
                binding.article_id != article_id
                or binding.article_code != article_code
                or binding.product_id not in product_refs
                or binding.snapshot_id != snapshot_id
                or binding.placement not in {"product_card", "final_summary"}
                or binding.placement_code
                != {"product_card": "card", "final_summary": "final"}[binding.placement]
                or binding.cta_id != expected_cta_id
                or INTERNAL_CTA_ID_RE.fullmatch(binding.cta_id) is None
                or binding.offer_id
                != f"off-{binding.article_code}-{binding.product_code}"
                or provider_slot is None
                or provider_slot.article_id != article_id
                or provider_slot.article_code != article_code
                or provider_slot.placement != binding.placement
                or provider_slot.placement_code != binding.placement_code
                or binding.provider_profile_state != "UNVERIFIED_DISABLED"
                or binding.cta_id in all_cta_ids
            ):
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            all_cta_ids.add(binding.cta_id)
            referenced_provider_slot_ids.add(binding.provider_slot_id)
            bindings.append(binding)
        if len(bindings) != len(product_refs) * 2:
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        articles.append(
            ArticleBindingV3(
                article_id=article_id,
                article_code=article_code,
                production_slug=production_slug,
                cluster_id=cluster_id,
                category_label=category_label,
                home_order=home_order,
                snapshot_id=snapshot_id,
                related_article_ids=related,
                product_ids=product_refs,
                cta_bindings=tuple(bindings),
            )
        )
    if (
        len(articles) != 10
        or len(products) != 32
        or len(all_cta_ids) != 74
        or referenced_provider_slot_ids != set(provider_slots_by_id)
        or set(provider_slots_by_key)
        != {
            (article.article_id, placement)
            for article in articles
            for placement in ("product_card", "final_summary")
        }
        or any(
            not set(article.related_article_ids).issubset(article_ids)
            for article in articles
        )
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return EditorialPortfolioV3(
        version=_text(document.get("version")),
        target_origin=_text(document.get("target_origin")),
        source_sha256=hashlib.sha256(raw).hexdigest(),
        articles=tuple(articles),
        products=tuple(products),
        provider_slots=tuple(provider_slots),
    )


__all__ = [
    "ArticleBindingV3",
    "CtaBindingV3",
    "EditorialPortfolioV3",
    "EditorialPortfolioV3Failure",
    "ProductBindingV3",
    "ProviderSlotV3",
    "load_editorial_portfolio_v3",
]
