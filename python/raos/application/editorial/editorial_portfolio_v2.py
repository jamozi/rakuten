"""Editorial V2 portfolio contracts and exact affiliate materialization.

The tracked portfolio contains identities and policy only. Provider responses,
affiliate destinations, image URLs, and image bytes remain owner-private and are
read only while a local preview or a production document is materialized.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Final, Literal, Mapping, NoReturn, cast
from urllib.parse import parse_qs, urlsplit

from raos.adapters.self_hosted_editorial_pilot_json import (
    read_rakuten_product_evidence,
)
from raos.application.editorial.editorial_portfolio_v3 import (
    EditorialPortfolioV3Failure,
    load_editorial_portfolio_v3,
)
from raos.domain.editorial.self_hosted_editorial_pilot import (
    EditorialPilotFailure,
    RakutenProductEvidence,
)


PORTFOLIO_RELATIVE_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
STATUS_RELATIVE_PATH: Final = Path(
    ".secrets/editorial-portfolio-v2/product-evidence-status.v2.json"
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
STATUS_SCHEMA: Final = "RAOS_EDITORIAL_PORTFOLIO_PRODUCT_EVIDENCE_STATUS_V2"
FIXTURE_SCHEMA: Final = "RAOS_WORDPRESS_LOCAL_PREVIEW_FIXTURE_V1"
MAX_TRACKED_BYTES: Final = 4 * 1024 * 1024
MAX_CONTENT_BYTES: Final = 1024 * 1024
MAX_STATUS_BYTES: Final = 1024 * 1024
FRESHNESS: Final = timedelta(hours=24)
REQUIRED_AD_DISCLOSURE: Final = (
    "広告を含みます。購入リンクから成果報酬を受け取る場合がありますが、"
    "選定・掲載順には使いません。"
)
SHA256_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
PRODUCT_ID_RE: Final = re.compile(r"PRD-[A-Z0-9]+(?:-[A-Z0-9]+)*\Z")
SLUG_RE: Final = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
ITEM_CODE_RE: Final = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}:[0-9]{5,20}\Z")
EvidenceState = Literal["verified", "not_found", "ambiguous", "expired"]


class EditorialPortfolioV2Failure(RuntimeError):
    """A stable, non-sensitive portfolio failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialPortfolioV2Failure(code) from None


def _read_json(path: Path, *, maximum: int, private: bool = False) -> object:
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
        return json.loads(raw.decode("utf-8", errors="strict"))
    except EditorialPortfolioV2Failure:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError, TypeError):
        _fail("RAOS_EDITORIAL_PORTFOLIO_FILE_INVALID")
    finally:
        if descriptor >= 0:
            os.close(descriptor)


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
class EditorialPortfolioV2:
    version: str
    target_origin: str
    theme_version: str
    articles: tuple[ArticleBindingV2, ...]
    products: tuple[ProductBindingV2, ...]
    freshness: timedelta = FRESHNESS

    @property
    def product_by_id(self) -> dict[str, ProductBindingV2]:
        return {product.product_id: product for product in self.products}

    @property
    def article_by_production_slug(self) -> dict[str, ArticleBindingV2]:
        return {article.production_slug: article for article in self.articles}


@dataclass(frozen=True, slots=True)
class ProductEvidenceViewV2:
    product_id: str
    state: EvidenceState
    retrieved_at: str
    evidence: RakutenProductEvidence | None


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
        "theme_version",
        "evidence_policy",
        "content_contract",
        "common_forbidden_title_tokens",
        "articles",
        "products",
    }
    if set(document) != expected_root or document.get("schema") != PORTFOLIO_SCHEMA:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    policy = _mapping(document["evidence_policy"])
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
            "jan": "match_when_provider_value_is_available",
            "title_tokens": "required",
            "pc_mobile_item_code": "required_exact",
        }
        or policy["local_product_image_origin"] != "/raos-product-media/"
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    common_forbidden = _text_tuple(document["common_forbidden_title_tokens"])
    content_contract = _mapping(document["content_contract"])
    if content_contract != {
        "body_format": "html_fragment",
        "required_editorial_root": "raos-editorial-v2",
        "required_ad_disclosure": REQUIRED_AD_DISCLOSURE,
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
    try:
        successor = load_editorial_portfolio_v3(repository_root)
    except EditorialPortfolioV3Failure:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    if successor.target_origin != target_origin:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")
    successor_articles = successor.article_by_id
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

    if product_ids != {product.product_id for product in successor.products}:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CONTRACT_INVALID")

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
        references = _text_tuple(article["product_ids"], maximum=160)
        post_row = posts_by_slug.get(local_slug)
        successor_article = successor_articles.get(article_id)
        expected_content_ref = (
            "changes/wordpress-local-preview-v1/fixtures/articles/"
            f"{production_slug}.html"
        )
        try:
            content_path = repository_root / content_ref
            metadata = content_path.lstat()
            content_payload = content_path.read_bytes()
            content = content_payload.decode("utf-8", errors="strict")
        except (OSError, UnicodeError):
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
            or (source_kind == "html_fixture" and source_ref != f"articles/{production_slug}.html")
            or (source_kind == "st1704_renderer" and source_ref != article_id)
            or successor_article is None
            or successor_article.production_slug != production_slug
            or successor_article.product_ids != references
            or post_row is None
            or post_row.get("title") != title
            or post_row.get("excerpt") != excerpt
            or post_row.get("category") != successor_article.category_label
            or post_row.get("content_file") != f"articles/{production_slug}.html"
            or content_ref != expected_content_ref
            or content_path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 1 <= len(content_payload) <= MAX_CONTENT_BYTES
            or content.count('class="raos-editorial-v2"') != 1
            or content.count(REQUIRED_AD_DISCLOSURE) != 1
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
        or len(products) != 32
        or occurrences != 37
        or article_ids != set(successor_articles)
        or {product.product_id for product in products}
        != {product_id for article in articles for product_id in article.product_ids}
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_COUNT_INVALID")
    representative_models = {
        product.product_id: product.representative_model for product in products
    }
    if (
        representative_models.get("PRD-IROBOT-ROOMBA-MINI-SLIM-F115060")
        != "F115060"
        or representative_models.get("PRD-THANKO-RAKUA-MINI-PLUS-TK-MDW22B")
        != "TK-MDW22B"
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_REPRESENTATIVE_INVALID")
    return EditorialPortfolioV2(
        version=_text(document["version"], maximum=30),
        target_origin=target_origin,
        theme_version=_text(document["theme_version"], maximum=30),
        articles=tuple(articles),
        products=tuple(products),
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


def _title_has_token(title: str, token: str) -> bool:
    def normalized(value: str) -> str:
        return re.sub(r"[\s+*・_.\-/＆&]", "", value).casefold()

    return normalized(token) in normalized(title)


def _validate_rakuten_identity(
    binding: ProductBindingV2, evidence: RakutenProductEvidence
) -> None:
    title = evidence.item_name
    destination = urlsplit(evidence.destination_url)
    query = parse_qs(destination.query, keep_blank_values=True, strict_parsing=True)
    try:
        pc = urlsplit(query["pc"][0])
        mobile = urlsplit(query["m"][0])
    except (KeyError, IndexError, ValueError):
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    pc_parts = pc.path.strip("/").split("/")
    mobile_parts = mobile.path.strip("/").split("/")
    if (
        evidence.product_id != binding.product_id
        or evidence.affiliate_ref != binding.affiliate_ref
        or evidence.media_asset_ref != binding.media_asset_ref
        or evidence.item_code != binding.rakuten_item_code
        or evidence.variant != binding.representative_model
        or (
            evidence.jan is not None
            and re.fullmatch(r"[0-9]{8,14}", evidence.jan) is None
        )
        or (
            binding.official_jan is not None
            and evidence.jan is not None
            and evidence.jan != binding.official_jan
        )
        or not all(_title_has_token(title, token) for token in binding.required_title_tokens)
        or not any(_title_has_token(title, token) for token in binding.product_kind_tokens)
        or any(_title_has_token(title, token) for token in binding.forbidden_title_tokens)
        or destination.scheme != "https"
        or destination.netloc != "hb.afl.rakuten.co.jp"
        or set(query) != {"m", "pc", "rafcid"}
        or pc.scheme != "https"
        or pc.netloc != "item.rakuten.co.jp"
        or len(pc_parts) != 2
        or mobile.scheme not in {"http", "https"}
        or mobile.netloc != "m.rakuten.co.jp"
        or len(mobile_parts) != 3
        or mobile_parts[1] != "i"
        or pc_parts[0] != mobile_parts[0]
        or evidence.item_code != f"{mobile_parts[0]}:{mobile_parts[2]}"
        or evidence.width != 128
        or evidence.height != 128
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")


def _load_status_receipt(repository_root: Path) -> Mapping[str, object] | None:
    path = repository_root / STATUS_RELATIVE_PATH
    if not path.exists() and not path.is_symlink():
        return None
    document = _mapping(_read_json(path, maximum=MAX_STATUS_BYTES, private=True))
    if set(document) != {"schema", "captured_at", "portfolio_sha256", "products"}:
        _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
    return document


def product_evidence_views_v2(
    repository_root: Path,
    *,
    now: datetime | None = None,
    require_fresh_set: bool = False,
) -> dict[str, ProductEvidenceViewV2]:
    portfolio = load_editorial_portfolio_v2(repository_root)
    active_now = (now or datetime.now(UTC)).astimezone(UTC)
    receipt = _load_status_receipt(repository_root)
    receipt_rows: dict[str, Mapping[str, object]] = {}
    receipt_captured_at: datetime | None = None
    if receipt is not None:
        if (
            receipt.get("schema") != STATUS_SCHEMA
            or receipt.get("portfolio_sha256") != portfolio_sha256(repository_root)
        ):
            if require_fresh_set:
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
    if require_fresh_set and (
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
        if stored_state == "verified":
            verified_hashes = (
                status_row.get("response_sha256"),
                status_row.get("affiliate_response_sha256"),
                status_row.get("image_sha256"),
            )
            if (
                binding.rakuten_item_code is None
                or status_row.get("item_code") != binding.rakuten_item_code
                or any(
                    type(value) is not str
                    or SHA256_RE.fullmatch(value) is None
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
                _validate_rakuten_identity(binding, evidence)
                if (
                    _parse_timestamp(evidence.retrieved_at) != retrieved
                    or status_row.get("item_code") != evidence.item_code
                    or status_row.get("response_sha256") != evidence.response_sha256
                    or status_row.get("affiliate_response_sha256")
                    != evidence.affiliate_response_sha256
                    or status_row.get("image_sha256") != evidence.image_sha256
                ):
                    _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
        else:
            if (
                status_row.get("item_code") is not None
                or status_row.get("affiliate_response_sha256") is not None
                or status_row.get("image_sha256") is not None
                or type(status_row.get("response_sha256")) is not str
                or SHA256_RE.fullmatch(cast(str, status_row["response_sha256"]))
                is None
            ):
                _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_INVALID")
        if require_fresh_set and state == "expired":
            _fail("RAOS_EDITORIAL_PORTFOLIO_EVIDENCE_EXPIRED")
        views[binding.product_id] = ProductEvidenceViewV2(
            product_id=binding.product_id,
            state=state,
            retrieved_at=retrieved.strftime("%Y-%m-%dT%H:%M:%SZ"),
            evidence=evidence,
        )
    return views


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
        if view.state == "verified" and view.evidence is not None:
            return (
                '<a class="rakuten-cta raos-cta" href="'
                + escape(view.evidence.destination_url, quote=True)
                + '" rel="sponsored nofollow"'
                + shared
                + '>楽天市場で現在の価格・在庫を見る <span aria-hidden="true">→</span></a>'
            )
        return (
            '<a class="official-product-link raos-cta" href="'
            + escape(binding.official_url, quote=True)
            + '" rel="noopener noreferrer"'
            + shared
            + '>メーカー公式で仕様を確認する <span aria-hidden="true">→</span></a>'
        )

    result = re.sub(
        r"(<a\b(?=[^>]*\bdata-raos-product-id=[\"'][^\"']+[\"'])"
        r"(?=[^>]*\bdata-raos-placement=[\"'](?:product_card|final_summary)[\"'])"
        r"[^>]*>).*?</a>",
        replace,
        markup,
        flags=re.IGNORECASE | re.DOTALL,
    )
    expected = {
        (product_id, placement)
        for product_id in article.product_ids
        for placement in ("product_card", "final_summary")
    }
    if counts != {key: 1 for key in expected}:
        _fail("RAOS_EDITORIAL_PORTFOLIO_CTA_STRUCTURE_INVALID")
    return result


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

    for product_id in article.product_ids:
        binding = bindings[product_id]
        view = evidence_views[product_id]
        card_pattern = re.compile(
            r"(<article\b(?=[^>]*\bdata-raos-product-id=[\"']"
            + re.escape(product_id)
            + r"[\"'])[^>]*>)(.*?)(</article>)",
            flags=re.IGNORECASE | re.DOTALL,
        )

        def replace_card(match: re.Match[str]) -> str:
            body = match.group(2)
            image_match = re.search(r"<img\b[^>]*>", body, flags=re.IGNORECASE)
            if image_match is None:
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            image_tag = image_match.group(0)
            source_attributes = _anchor_attributes(image_tag)
            if view.state == "verified" and view.evidence is not None:
                image_src = (
                    f"/raos-product-media/{product_id}.image"
                    if mode == "local"
                    else view.evidence.image_url
                )
                image_alt = (
                    f"{binding.official_name}の商品画像（楽天市場の商品情報より）"
                )
                image_state = "verified"
            else:
                image_src = source_attributes.get("src", "")
                if (
                    not image_src.startswith(
                        "/wp-content/themes/kurashinoshirube-child/assets/images/"
                    )
                    or ".." in image_src
                    or urlsplit(image_src).scheme
                ):
                    _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
                image_alt = (
                    f"{binding.official_name}を比較検討するための中立イメージ。"
                    "商品写真ではありません"
                )
                image_state = "neutral"
            image_tag = re.sub(
                r"\bsrc\s*=\s*([\"']).*?\1",
                f'src="{escape(image_src, quote=True)}"',
                image_tag,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            image_tag = re.sub(
                r"\balt\s*=\s*([\"']).*?\1",
                'alt="' + escape(image_alt, quote=True) + '"',
                image_tag,
                count=1,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if not re.search(r"\balt\s*=", image_tag, flags=re.IGNORECASE):
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            if "data-raos-product-image-id=" not in image_tag:
                image_tag = image_tag[:-1] + (
                    f' data-raos-product-image-id="{escape(product_id, quote=True)}">'
                )
            if "data-raos-product-image-state=" in image_tag:
                image_tag = re.sub(
                    r"\bdata-raos-product-image-state\s*=\s*([\"']).*?\1",
                    f'data-raos-product-image-state="{image_state}"',
                    image_tag,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            else:
                image_tag = image_tag[:-1] + (
                    f' data-raos-product-image-state="{image_state}">'
                )
            if view.state == "verified":
                if re.search(r"\bwidth\s*=", image_tag, flags=re.IGNORECASE):
                    image_tag = re.sub(
                        r"\bwidth\s*=\s*([\"']).*?\1",
                        'width="128"',
                        image_tag,
                        count=1,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                else:
                    image_tag = image_tag[:-1] + ' width="128">'
                if re.search(r"\bheight\s*=", image_tag, flags=re.IGNORECASE):
                    image_tag = re.sub(
                        r"\bheight\s*=\s*([\"']).*?\1",
                        'height="128"',
                        image_tag,
                        count=1,
                        flags=re.IGNORECASE | re.DOTALL,
                    )
                else:
                    image_tag = image_tag[:-1] + ' height="128">'
            observed.add(product_id)
            replaced_body = body[: image_match.start()] + image_tag + body[image_match.end() :]
            captions = re.findall(
                r"<figcaption\b[^>]*>.*?</figcaption>",
                replaced_body,
                flags=re.IGNORECASE | re.DOTALL,
            )
            if len(captions) > 1:
                _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
            if captions:
                caption = (
                    f"{binding.official_name}の商品画像（楽天市場の商品情報より）"
                    if view.state == "verified"
                    else "比較検討用の中立イメージ（商品写真ではありません）"
                )
                replaced_body = re.sub(
                    r"(<figcaption\b[^>]*>).*?(</figcaption>)",
                    lambda caption_match: (
                        caption_match.group(1)
                        + escape(caption)
                        + caption_match.group(2)
                    ),
                    replaced_body,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
            return match.group(1) + replaced_body + match.group(3)

        markup, replacements = card_pattern.subn(replace_card, markup, count=1)
        if replacements != 1:
            _fail("RAOS_EDITORIAL_PORTFOLIO_IMAGE_STRUCTURE_INVALID")
    expected = set(article.product_ids)
    if observed != expected:
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
        if view.state == "verified" and view.evidence is not None:
            note = (
                f"楽天市場の商品ページで、{binding.official_name}"
                f"（代表型番：{binding.representative_model}）の型番、販売元、"
                "価格、在庫、商品画像を確認できます。"
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
        or markup.count(REQUIRED_AD_DISCLOSURE) != 1
    ):
        _fail("RAOS_EDITORIAL_PORTFOLIO_ARTICLE_INVALID")
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
    path = repository_root / SOURCE_FIXTURE_RELATIVE_PATH / "articles" / (
        f"{article.production_slug}.html"
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
    "PORTFOLIO_RELATIVE_PATH",
    "PRODUCTION_FIXTURE_RELATIVE_PATH",
    "ProductBindingV2",
    "ProductEvidenceViewV2",
    "STATUS_RELATIVE_PATH",
    "load_editorial_portfolio_v2",
    "materialize_article_v2",
    "materialize_source_article_v2",
    "portfolio_sha256",
    "product_evidence_views_v2",
]
