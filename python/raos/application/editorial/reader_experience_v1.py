"""Reader-facing projections and eligibility rules; no network or publication.

These rules consume already validated evidence. A display decision is never a
substitute for the publication adapter's identity, freshness or approval checks.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal
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


@dataclass(frozen=True)
class CheckedFact:
    evidence_ref: str
    source_ref: str
    checked_at: str | None
    state: Literal["KNOWN", "UNKNOWN"]

    @property
    def usable(self) -> bool:
        try:
            if self.checked_at is None:
                return False
            date.fromisoformat(self.checked_at)
        except ValueError:
            return False
        return bool(self.evidence_ref and self.source_ref and self.state == "KNOWN")


def comparison_issues(products: Mapping[str, Mapping[str, CheckedFact]]) -> tuple[str, ...]:
    """Report missing evidence without manufacturing another comparison article."""
    issues = []
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
        return url in evidence.existing_targets
    if kind == "verify":
        return url.startswith("https://") and url in evidence.official_urls
    return (
        kind == "offer"
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

    @property
    def displayable(self) -> bool:
        if self.approval != "approved" or not all(
            (self.asset_ref, self.source, self.usage_basis, self.alt, self.caption, self.role)
        ):
            return False
        if not all(type(value) is int and value > 0 for value in self.aspect_ratio):
            return False
        if len(self.aspect_ratio) != 2 or not self.checked_at:
            return False
        try:
            date.fromisoformat(self.checked_at)
        except ValueError:
            return False
        return urlsplit(self.source).scheme in {"", "https"}


def validate_experience(
    experience: Mapping[str, object], *, product_refs: frozenset[str],
    evidence_refs: frozenset[str],
) -> tuple[str, ...]:
    """Validate the additive view model without making missing legacy data up."""
    issues: list[str] = []
    article_type = experience.get("article_type")
    if article_type not in ARTICLE_TYPES:
        issues.append("article_type.invalid")
    status = experience.get("research_status")
    if isinstance(status, Mapping):
        if status.get("ranking_uses_commission") is not False:
            issues.append("research_status.commission_ranking_forbidden")
        if not isinstance(status.get("real_world_tested"), bool):
            issues.append("research_status.real_world_tested_required")
    else:
        issues.append("research_status.required")
    summary = experience.get("decision_summary", {})
    if isinstance(summary, Mapping):
        options = summary.get("options", [])
        if isinstance(options, Sequence) and not isinstance(options, str):
            for option in options:
                if not isinstance(option, Mapping):
                    issues.append("decision_summary.option_invalid")
                    continue
                product = option.get("product_ref")
                if product is not None and product not in product_refs:
                    issues.append("decision_summary.unknown_product")
                if article_type == "status_check" and product is not None:
                    issues.append("status_check.recommendation_forbidden")
    facts = experience.get("evidence", [])
    if not isinstance(facts, list) or any(ref not in evidence_refs for ref in facts):
        issues.append("evidence.unresolved_reference")
    return tuple(issues)
