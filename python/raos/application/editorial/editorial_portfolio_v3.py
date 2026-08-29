"""Read-only runtime view of the generated Editorial V3 portfolio."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Final, Mapping, NoReturn, cast


PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v3/editorial-portfolio.v3.json"
)
ARTICLE_CODE_RE: Final = re.compile(r"a[0-9]{2}\Z")
PRODUCT_CODE_RE: Final = re.compile(r"p[0-9]{2}\Z")
MEASUREMENT_ID_RE: Final = re.compile(r"a[0-9]{2}-p[0-9]{2}-(?:card|final)\Z")


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
    rakuten_measurement_id: str
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
    articles: tuple[ArticleBindingV3, ...]
    products: tuple[ProductBindingV3, ...]

    @property
    def article_by_id(self) -> dict[str, ArticleBindingV3]:
        return {article.article_id: article for article in self.articles}

    @property
    def article_by_slug(self) -> dict[str, ArticleBindingV3]:
        return {article.production_slug: article for article in self.articles}

    @property
    def cta_by_measurement_id(self) -> dict[str, CtaBindingV3]:
        return {
            binding.rakuten_measurement_id: binding
            for article in self.articles
            for binding in article.cta_bindings
        }


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
    if (
        document.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V3"
        or document.get("version") != "3.0.0"
        or _mapping(document.get("predecessor")).get("historical_contract_preserved")
        is not True
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    policy = _mapping(document.get("rakuten_measurement_policy"))
    if (
        policy.get("format") != "{article_code}-{product_code}-{card|final}"
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

    articles: list[ArticleBindingV3] = []
    article_ids: set[str] = set()
    article_codes: set[str] = set()
    all_cta_ids: set[str] = set()
    all_measurement_ids: set[str] = set()
    for row in _rows(document.get("articles")):
        article_id = _text(row.get("article_id"))
        article_code = _text(row.get("article_code"))
        production_slug = _text(row.get("production_slug"))
        cluster_id = _text(row.get("cluster_id"))
        category_label = _text(row.get("category_label"))
        home_order = row.get("home_order")
        snapshot_id = _text(row.get("snapshot_id"))
        related = tuple(
            _text(item) for item in cast(list[object], row.get("related_article_ids"))
        )
        product_refs = tuple(
            _text(item) for item in cast(list[object], row.get("product_ids"))
        )
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
                rakuten_measurement_id=_text(
                    binding_value.get("rakuten_measurement_id")
                ),
                provider_profile_state=_text(
                    binding_value.get("provider_profile_state")
                ),
            )
            expected_measurement = (
                f"{binding.article_code}-{binding.product_code}-"
                f"{binding.placement_code}"
            )
            if (
                binding.article_id != article_id
                or binding.article_code != article_code
                or binding.product_id not in product_refs
                or binding.snapshot_id != snapshot_id
                or binding.placement not in {"product_card", "final_summary"}
                or binding.placement_code
                != {"product_card": "card", "final_summary": "final"}[binding.placement]
                or binding.rakuten_measurement_id != expected_measurement
                or MEASUREMENT_ID_RE.fullmatch(binding.rakuten_measurement_id) is None
                or binding.cta_id != f"cta-{expected_measurement}"
                or binding.offer_id
                != f"off-{binding.article_code}-{binding.product_code}"
                or binding.provider_profile_state != "UNVERIFIED_DISABLED"
                or binding.cta_id in all_cta_ids
                or binding.rakuten_measurement_id in all_measurement_ids
            ):
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            all_cta_ids.add(binding.cta_id)
            all_measurement_ids.add(binding.rakuten_measurement_id)
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
        or len(all_measurement_ids) != 74
        or any(
            not set(article.related_article_ids).issubset(article_ids)
            for article in articles
        )
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return EditorialPortfolioV3(
        version=_text(document.get("version")),
        target_origin=_text(document.get("target_origin")),
        articles=tuple(articles),
        products=tuple(products),
    )


__all__ = [
    "ArticleBindingV3",
    "CtaBindingV3",
    "EditorialPortfolioV3",
    "EditorialPortfolioV3Failure",
    "ProductBindingV3",
    "load_editorial_portfolio_v3",
]
