"""Reader-facing projections and eligibility rules; no network or publication.

These rules consume already validated evidence. A display decision is never a
substitute for the publication adapter's identity, freshness or approval checks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
import re
from typing import Literal, TypeGuard, cast
from urllib.parse import urlsplit


ArticleType = Literal["shortlist", "comparison", "model_difference", "status_check", "safety_rule"]
CtaType = Literal["learn", "verify", "offer"]
ARTICLE_TYPES = frozenset({"shortlist", "comparison", "model_difference", "status_check", "safety_rule"})
ROLE_TYPES: Mapping[str, ArticleType] = {
    "category_guide": "shortlist",
    "constraint_shortlist": "shortlist",
    "feature_shortlist": "shortlist",
    "brand_family_comparison": "model_difference",
    "model_family_comparison": "model_difference",
    "head_to_head_comparison": "comparison",
    "head_to_head_with_reference": "comparison",
    "lifecycle_status_route": "status_check",
}
COMPARISON_REQUIREMENTS = (
    "exact_model", "official_source", "body_dimensions", "door_or_installation_space",
    "water_supply_and_drainage", "capacity", "detergent", "maintenance",
    "cycle_time", "weight", "sales_state", "warranty", "generation_and_configuration",
)


def _is_mapping(value: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(value, Mapping)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_sequence(value: object) -> TypeGuard[Sequence[object]]:
    return isinstance(value, Sequence)


def _nonempty_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


@dataclass(frozen=True)
class CheckedFact:
    evidence_ref: str
    source_ref: str
    checked_at: str | None
    state: Literal["KNOWN", "UNKNOWN"]

    @property
    def usable(self) -> bool:
        try:
            if not isinstance(self.checked_at, str):
                return False
            date.fromisoformat(self.checked_at)
        except ValueError:
            return False
        evidence_ref = cast(object, self.evidence_ref)
        source_ref = cast(object, self.source_ref)
        return bool(isinstance(evidence_ref, str) and evidence_ref and isinstance(source_ref, str) and source_ref and self.state == "KNOWN")


def comparison_issues(products: Mapping[str, Mapping[str, CheckedFact]]) -> tuple[str, ...]:
    """Report missing evidence without manufacturing another comparison article."""
    issues: list[str] = []
    if len(products) != 2:
        issues.append("comparison.requires_two_exact_configurations")
    for product, facts in products.items():
        for field in COMPARISON_REQUIREMENTS:
            fact = facts.get(field)
            if fact is None or not fact.usable:
                issues.append(f"{product}.{field}")
    return tuple(issues)


@dataclass(frozen=True)
class CtaEvidence:
    """Capabilities projected from validated adapters, never from article copy."""

    existing_targets: frozenset[str] = frozenset()
    official_urls: frozenset[str] = frozenset()
    verified_offers: frozenset[tuple[str, str]] = frozenset()
    eligible_products: frozenset[str] = frozenset()


def cta_visible(
    kind: CtaType, url: str, product_ref: str | None, evidence: CtaEvidence,
    *, article_type: ArticleType,
) -> bool:
    if kind == "learn":
        return urlsplit(url).scheme in {'', 'https'} and not url.startswith('//') and url in evidence.existing_targets
    if kind == "verify":
        return url.startswith("https://") and url in evidence.official_urls
    return (
        kind == "offer"
        and url.startswith("https://")
        and article_type != "status_check"
        and product_ref is not None
        and product_ref in evidence.eligible_products
        and (product_ref, url) in evidence.verified_offers
    )


@dataclass(frozen=True)
class MediaAsset:
    asset_ref: str
    source: str
    usage_basis: str
    checked_at: str | None
    approval: Literal["approved", "pending", "rejected"]
    alt: str
    caption: str
    aspect_ratio: tuple[int, int]
    role: str
    asset_type: str = ""

    @property
    def displayable(self) -> bool:
        return _media_displayable({
            "asset_ref": self.asset_ref, "source": self.source,
            "usage_basis": self.usage_basis, "checked_at": self.checked_at,
            "approval": self.approval, "alt": self.alt, "caption": self.caption,
            "aspect_ratio": self.aspect_ratio, "role": self.role,
            "asset_type": self.asset_type,
        })


def _media_displayable(raw: Mapping[str, object]) -> bool:
    # Dataclass annotations do not validate callers or decoded JSON records.
    if raw["approval"] != "approved" or not all(
        _nonempty_text(raw[key]) for key in ("asset_ref", "source", "usage_basis", "alt", "caption", "role")
    ):
        return False
    if raw["asset_type"] not in {"photo", "svg", "html_diagram", "illustration"}:
        return False
    ratio = raw["aspect_ratio"]
    if not isinstance(ratio, (tuple, list)):
        return False
    ratio = cast(Sequence[object], ratio)
    if not all(type(value) is int and value > 0 for value in ratio):
        return False
    checked_at = raw["checked_at"]
    if len(ratio) != 2 or not isinstance(checked_at, str):
        return False
    try:
        date.fromisoformat(checked_at)
    except ValueError:
        return False
    return urlsplit(cast(str, raw["source"])).scheme in {"", "https"}


def approved_media_record(raw: Mapping[str, object]) -> bool:
    """Missing rights metadata omits the asset, including its visual frame."""
    if not all(key in raw for key in MediaAsset.__dataclass_fields__):
        return False
    try:
        return _media_displayable({key: raw[key] for key in MediaAsset.__dataclass_fields__})
    except (TypeError, ValueError):
        return False


def validate_experience(
    experience: Mapping[str, object], *, product_refs: frozenset[str],
    evidence_refs: frozenset[str], checked_fact_refs: frozenset[str] | None = None,
) -> tuple[str, ...]:
    """Validate the additive view model without making missing legacy data up."""
    issues: list[str] = []
    article_type = experience.get("article_type")
    if not isinstance(article_type, str) or article_type not in ARTICLE_TYPES:
        issues.append("article_type.invalid")
    status = experience.get("research_status")
    if _is_mapping(status):
        if status.get("ranking_uses_commission") is not False:
            issues.append("research_status.commission_ranking_forbidden")
        if not isinstance(status.get("real_world_tested"), bool):
            issues.append("research_status.real_world_tested_required")
    else:
        issues.append("research_status.required")
    def prose(value: object) -> list[str]:
        if isinstance(value, str):
            return [value]
        if _is_mapping(value):
            return [text for child in value.values() for text in prose(child)]
        if _is_list(value):
            return [text for child in value for text in prose(child)]
        return []

    if _is_mapping(status) and status.get("real_world_tested") is False:
        for text in prose(experience):
            for sentence in re.split(r"[。、！？\n]|(?<=です)が|(?<=でした)が|(?<=た)が|だが|ものの|けれど", text):
                if re.search(r"実際に使(?:って|った|いました)|使ってみ|使用したところ|実測した|試してみた|音が静か(?:です|でした)|使い心地[はが](?:良|快適)|よく落ちました|使いやすかった", sentence) and not re.search(r"未確認|未実施|いません|いない|していない|ではありません", sentence):
                    issues.append("research_status.unverified_experience_claim")
    summary = experience.get("decision_summary", {})
    if _is_mapping(summary):
        options = summary.get("options", [])
        if _is_sequence(options) and not isinstance(options, str):
            for option in options:
                if not _is_mapping(option):
                    issues.append("decision_summary.option_invalid")
                    continue
                if any(not _nonempty_text(option.get(key)) for key in ('reason', 'tradeoff')):
                    issues.append('decision_summary.option_incomplete')
                product = option.get("product_ref")
                if product is not None and (not isinstance(product, str) or product not in product_refs):
                    issues.append("decision_summary.unknown_product")
                if article_type == "status_check" and product is not None:
                    issues.append("status_check.recommendation_forbidden")
        else:
            issues.append("decision_summary.options_invalid")
    else:
        issues.append("decision_summary.invalid")
    for name, required in (
        ("decision_axes", ("label", "why_it_matters", "how_to_check")),
        ("unknowns", ("topic", "why_unknown", "how_to_verify", "decision_effect")),
        ("contextual_links", ("journey_stage", "question", "target_ref")),
    ):
        rows = experience.get(name, [])
        if not _is_list(rows) or any(not _is_mapping(row) or any(not _nonempty_text(row.get(key)) for key in required) for row in rows):
            issues.append(name + ".invalid")
        if name == "decision_axes" and _is_list(rows) and len(rows) > 5:
            issues.append("decision_axes.max_five")
    products = experience.get("products", [])
    if not _is_list(products):
        issues.append("products.invalid")
    else:
        seen: set[str] = set()
        for product in products:
            if not _is_mapping(product):
                issues.append("products.invalid")
                continue
            ref = product.get("product_ref")
            if not isinstance(ref, str) or ref not in product_refs or ref in seen:
                issues.append("products.unresolved_or_duplicate_reference")
            else:
                seen.add(ref)
            facts = product.get("evidence_facts", [])
            if not _is_list(facts) or any(not isinstance(ref, str) or ref not in evidence_refs for ref in facts):
                issues.append("products.evidence_must_reference_facts")
            elif checked_fact_refs is not None and any(ref not in checked_fact_refs for ref in facts):
                issues.append("products.official_checked_facts_required")
    if article_type == 'safety_rule':
        rule = experience.get('rule_status')
        if not _is_mapping(rule) or any(not _nonempty_text(rule.get(k)) for k in ('authority', 'final_decision_by', 'exceptions', 'scope_limit', 'evidence_ref')):
            issues.append('rule_status.required')
        elif rule['evidence_ref'] not in (checked_fact_refs if checked_fact_refs is not None else evidence_refs):
            issues.append('rule_status.official_checked_fact_required')
    if any(re.search(r"[0-9][0-9,]*\s*円", text) for text in prose(experience)):
        price = experience.get("price_snapshot")
        valid_price = False
        if _is_mapping(price) and isinstance(price.get("evidence_ref"), str) and price["evidence_ref"] in evidence_refs and isinstance(price.get("checked_at"), str):
            try:
                date.fromisoformat(cast(str, price["checked_at"]))
                valid_price = True
            except ValueError:
                pass
        if not valid_price:
            issues.append("price.checked_date_and_evidence_required")
    facts = experience.get("evidence", [])
    if not _is_list(facts) or any(not isinstance(ref, str) or ref not in evidence_refs for ref in facts):
        issues.append("evidence.unresolved_reference")
    return tuple(issues)
def reader_navigation(raw: object, articles: list[dict[str, object]]) -> dict[str, object]:
    """Validate taxonomy and derive hub memberships; counts remain runtime eligible counts."""
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError('READER_NAVIGATION_INVALID')
    navigation = cast(dict[str, object], raw)
    if not _is_list(navigation.get('groups')):
        raise ValueError('READER_NAVIGATION_INVALID')
    known = {str(a['article_id']): a for a in articles}
    groups = cast(list[object], navigation['groups'])
    validated_groups: list[dict[str, object]] = []
    categories: list[str] = []
    slugs: set[str] = set()
    for candidate in groups:
        if not isinstance(candidate, dict) or set(cast(dict[str, object], candidate)) != {'slug', 'label', 'description', 'kind', 'article_ids'}:
            raise ValueError('READER_GROUP_INVALID')
        group = cast(dict[str, object], candidate)
        if (group['kind'] not in {'category', 'purpose'}
            or not isinstance(group['slug'], str) or not re.fullmatch(r'[a-z]+(?:-[a-z]+)*', group['slug'])
            or group['slug'] in slugs or not _is_list(group['article_ids'])
            or not all(isinstance(x, str) and x in known for x in group['article_ids'])
            or len(set(group['article_ids'])) != len(group['article_ids'])
            or not all(_nonempty_text(group[k]) for k in ('label', 'description'))):
            raise ValueError('READER_GROUP_INVALID')
        slugs.add(group['slug'])
        validated_groups.append(group)
        if group['kind'] == 'category':
            categories.extend(cast(list[str], group['article_ids']))
    if sorted(categories) != sorted(known):
        raise ValueError('READER_PRIMARY_CATEGORY_MUST_BE_UNIQUE')
    core = [
        ('categories', '商品カテゴリから探す', '道具の種類から、暮らしに合う条件を確認します。', 'categories', list(known)),
        ('purposes', '悩み・目的から探す', '困っていることから、次に確認する条件を見つけます。', 'purposes', list(known)),
        ('guides', '選び方ガイド', '商品名を決める前に、測る・数える・確認する条件を整理します。', 'collection', [k for k,a in known.items() if a['content_role'] == 'category_guide']),
        ('comparisons', '比較・条件別の候補', '違いと妥協点を確認し、自分の条件に合う候補を絞ります。', 'collection', [k for k,a in known.items() if a['content_role'] != 'lifecycle_status_route']),
        ('updates', '最近更新したガイド', '内容を更新した順に、比較と購入前確認のガイドを案内します。', 'updates', list(known)),
    ]
    hubs: list[dict[str, object]] = [dict(slug=slug, label=label, description=description, kind=kind, article_ids=ids) for slug,label,description,kind,ids in core]
    if slugs.intersection(cast(str, h['slug']) for h in hubs):
        raise ValueError('READER_HUB_SLUG_COLLISION')
    hubs.extend(validated_groups)
    return {'hubs': hubs, 'primary_categories': {article: g['slug'] for g in validated_groups if g['kind'] == 'category' for article in cast(list[str], g['article_ids'])}}
