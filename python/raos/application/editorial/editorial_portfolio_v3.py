"""Read-only runtime view of the generated Editorial V3 portfolio."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
from pathlib import Path
import re
from typing import Final, Mapping, NoReturn, cast
from urllib.parse import urlsplit


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
LIFECYCLE_STATUS_ROUTE_ARTICLE_ID: Final = "solota-vs-rakua-mini-plus"
LIFECYCLE_STATUS_ROUTE_ARTICLE_CODE: Final = "a10"
INTENT_GROUP_CLUSTER: Final = {
    "carry-on-suitcase": "mobility",
    "countertop-dishwasher": "household",
    "portable-power": "preparedness",
    "robot-vacuum": "household",
}
CONTENT_ROLE_LABELS: Final = {
    "brand_family_comparison": "ブランド内比較",
    "category_guide": "選び方",
    "constraint_shortlist": "条件別比較",
    "feature_shortlist": "機能別比較",
    "head_to_head_comparison": "2製品比較",
    "head_to_head_with_reference": "2製品比較＋参考機種",
    "lifecycle_status_route": "型番・販売表示の確認案内",
    "model_family_comparison": "ブランド内比較",
}
ROLES_REQUIRING_BROADER_ARTICLE: Final = {
    "brand_family_comparison",
    "head_to_head_comparison",
    "head_to_head_with_reference",
    "lifecycle_status_route",
    "model_family_comparison",
}
ROLES_ALLOWING_BROADER_ARTICLE: Final = ROLES_REQUIRING_BROADER_ARTICLE | {
    "constraint_shortlist"
}
MARKET_UNIVERSE_METHODS: Final = {
    "BRAND_BOUND_CURRENT_MODELS",
    "CROSS_BRAND_CURRENT_CATEGORY",
    "CROSS_BRAND_CONSTRAINT_FILTER",
    "CROSS_BRAND_FEATURE_FILTER",
    "FIXED_HEAD_TO_HEAD_WITH_BROADER_ROUTE",
    "FIXED_MODEL_FAMILY",
}
MARKET_AXIS_STATES: Final = {
    "EVALUATED_NOT_DIFFERENTIATING",
    "OFFICIAL_EVIDENCE_USED",
    "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED",
}
PRODUCT_DUE_DILIGENCE_AXES: Final = {
    "safety",
    "warranty_and_support",
    "maintainability",
}
EXTERNAL_CANDIDATE_LIFECYCLE_STATES: Final = {
    "AVAILABLE",
    "PREORDER",
    "PRODUCTION_ENDED",
    "RESTOCK_NOTIFICATION_ONLY",
    "SOLD_OUT",
    "UNKNOWN",
}
EXTERNAL_CANDIDATE_EMBEDDED_LIFECYCLE_STATES: Final = {
    *EXTERNAL_CANDIDATE_LIFECYCLE_STATES,
    "NOT_PRESENT",
}
EXTERNAL_CANDIDATE_USE_ROLES: Final = {
    "BROADER_GUIDE_REFERENCE",
    "DIRECT_CATEGORY_PEER",
    "FEATURE_SCOPE_EDGE_CASE",
    "FIXED_FAMILY_ADJACENT",
    "LIFECYCLE_REFERENCE",
    "SCOPE_EDGE_CASE",
}


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


def _https_url(value: object) -> str:
    url = _text(value)
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return url


def _iso_date(value: object) -> str:
    raw = _text(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    if parsed.isoformat() != raw:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    return raw


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
    intent_group_id: str
    category_label: str
    content_role: str
    content_role_label: str
    primary_query_intent: str
    comparison_scope: str
    broader_article_id: str | None
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


def _validate_market_candidate_audit(
    value: object,
    *,
    article_by_id: Mapping[str, ArticleBindingV3],
    product_ids: set[str],
) -> None:
    document = _mapping(value)
    required_axes = (
        "use_case_fit",
        "safety",
        "dimensions",
        "performance",
        "warranty_and_support",
        "maintainability",
        "primary_source_confidence",
    )
    if (
        set(document)
        != {
            "schema",
            "version",
            "evaluated_at",
            "required_axes",
            "rules",
            "articles",
        }
        or document.get("schema") != "RAOS_EDITORIAL_MARKET_CANDIDATE_AUDIT_V1"
        or document.get("version") != "1.0.0"
        or _texts(document.get("required_axes")) != required_axes
        or _mapping(document.get("rules"))
        != {
            "decision_critical_unknown_allowed": False,
            "generic_unnamed_candidate_allowed": False,
            "hard_filters_required": True,
            "official_category_sources_required": True,
            "exact_model_variant_scope_required": True,
            "lifecycle_crosscheck_required": True,
            "reader_visible_lifecycle_precedence": True,
            "embedded_lifecycle_conflict_state": "CONFLICT",
            "external_disposition_states": ["EXCLUDED", "DEFERRED"],
            "portfolio_reference_disposition": "REFERENCE_ONLY",
            "portfolio_products_must_use_reference_bindings": True,
            "reader_visible_exclusions_required": True,
            "selected_candidate_only_audit_allowed": False,
            "selected_product_due_diligence_source": "RAOS_PRODUCT_SELECTION_AUDIT_V2",
            "article_guidance_never_establishes_product_axis_completion": True,
            "incomplete_selected_product_axes_block_publication": True,
            "price_weight": 0,
            "affiliate_reward_rate_weight": 0,
            "rakuten_availability_weight": 0,
        }
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    evaluated_at = _iso_date(document.get("evaluated_at"))
    audited_ids: set[str] = set()
    candidate_signatures: dict[str, tuple[object, ...]] = {}
    exclusion_headings: set[str] = set()
    for audit in _rows(document.get("articles")):
        if set(audit) != {
            "article_id",
            "content_role",
            "primary_query_intent",
            "comparison_scope",
            "broader_article_id",
            "candidate_universe_method",
            "hard_filters",
            "official_category_sources",
            "axis_assessments",
            "selected_product_ids",
            "considered_portfolio_candidates",
            "considered_external_candidates",
            "reader_visible_exclusions_heading",
            "reader_visible_required",
            "overlap_risk",
            "scope_separation",
        }:
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        article_id = _text(audit.get("article_id"))
        exclusion_heading = _text(audit.get("reader_visible_exclusions_heading"))
        article = article_by_id.get(article_id)
        selected = _texts(audit.get("selected_product_ids"))
        if (
            article is None
            or article_id in audited_ids
            or audit.get("content_role") != article.content_role
            or audit.get("primary_query_intent") != article.primary_query_intent
            or audit.get("comparison_scope") != article.comparison_scope
            or audit.get("broader_article_id") != article.broader_article_id
            or audit.get("candidate_universe_method") not in MARKET_UNIVERSE_METHODS
            or not 8 <= len(exclusion_heading) <= 60
            or exclusion_heading in exclusion_headings
            or audit.get("reader_visible_required") is not True
            or audit.get("overlap_risk") != "CONTROLLED_BY_EXPLICIT_SCOPE"
            or not _text(audit.get("scope_separation"))
            or selected != article.product_ids
            or len(selected) != len(set(selected))
            or not set(selected).issubset(product_ids)
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        exclusion_headings.add(exclusion_heading)
        seen_portfolio_candidates: set[str] = set()
        for candidate in _rows(audit.get("considered_portfolio_candidates")):
            if set(candidate) != {
                "product_id",
                "disposition",
                "route_article_id",
                "reason",
            }:
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            product_id = _text(candidate.get("product_id"))
            route_article_id = _text(candidate.get("route_article_id"))
            route_article = article_by_id.get(route_article_id)
            if (
                product_id in seen_portfolio_candidates
                or product_id in selected
                or product_id not in product_ids
                or candidate.get("disposition") != "REFERENCE_ONLY"
                or route_article_id == article_id
                or route_article is None
                or product_id not in route_article.product_ids
                or route_article.intent_group_id != article.intent_group_id
                or len(_text(candidate.get("reason"))) > 800
            ):
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            seen_portfolio_candidates.add(product_id)
        hard_filters = _texts(audit.get("hard_filters"))
        official_category_sources = (
            tuple(
                _https_url(reference)
                for reference in cast(
                    list[object], audit.get("official_category_sources")
                )
            )
            if type(audit.get("official_category_sources")) is list
            else ()
        )
        if (
            not hard_filters
            or len(hard_filters) != len(set(hard_filters))
            or any(len(value) > 300 for value in hard_filters)
            or not official_category_sources
            or len(official_category_sources) != len(set(official_category_sources))
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        assessments = _mapping(audit.get("axis_assessments"))
        if set(assessments) != set(required_axes):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        for axis in required_axes:
            assessment = _mapping(assessments.get(axis))
            state = _text(assessment.get("state"))
            is_due_diligence_recheck = (
                state == "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
            )
            expected_assessment_fields: set[str] = {
                "state",
                "rationale",
                "evidence_refs",
            }
            if is_due_diligence_recheck:
                expected_assessment_fields.add("recheck_by")
            if set(assessment) != expected_assessment_fields:
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            rationale = _text(assessment.get("rationale"))
            evidence_refs = (
                tuple(
                    _https_url(reference)
                    for reference in cast(list[object], assessment.get("evidence_refs"))
                )
                if type(assessment.get("evidence_refs")) is list
                else ()
            )
            recheck_by = (
                _iso_date(assessment.get("recheck_by"))
                if is_due_diligence_recheck
                else None
            )
            if (
                state not in MARKET_AXIS_STATES
                or (
                    axis
                    in {
                        "use_case_fit",
                        "dimensions",
                        "performance",
                        "primary_source_confidence",
                    }
                    and state != "OFFICIAL_EVIDENCE_USED"
                )
                or (
                    axis in PRODUCT_DUE_DILIGENCE_AXES
                    and (
                        not is_due_diligence_recheck
                        or recheck_by is None
                        or recheck_by <= evaluated_at
                        or "商品別" not in rationale
                        or "推奨根拠" not in rationale
                        or "公開" not in rationale
                    )
                )
                or (axis not in PRODUCT_DUE_DILIGENCE_AXES and is_due_diligence_recheck)
                or len(rationale) > 800
                or len(evidence_refs) != len(set(evidence_refs))
                or (state == "OFFICIAL_EVIDENCE_USED" and not evidence_refs)
                or (state != "OFFICIAL_EVIDENCE_USED" and evidence_refs)
                or "未確認" in rationale
                or "UNKNOWN" in rationale.upper()
                or "NOT_EVALUATED" in rationale.upper()
            ):
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        candidates = _rows(audit.get("considered_external_candidates"))
        if not candidates:
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        seen_candidates: set[str] = set()
        for candidate in candidates:
            if set(candidate) != {
                "candidate_id",
                "brand",
                "exact_model",
                "exact_variant_scope",
                "use_role",
                "disposition",
                "model_lifecycle",
                "variant_lifecycle",
                "reader_visible_lifecycle",
                "embedded_structured_lifecycle",
                "lifecycle_evidence_state",
                "effective_lifecycle",
                "decision_critical",
                "decision_critical_unknowns",
                "official_url",
                "evidence_refs",
                "exclusion_axis",
                "reason",
                "evaluated_at",
            }:
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            candidate_id = _text(candidate.get("candidate_id"))
            brand = _text(candidate.get("brand"))
            exact_model = _text(candidate.get("exact_model"))
            exact_variant_scope = _text(candidate.get("exact_variant_scope"))
            use_role = _text(candidate.get("use_role"))
            model_lifecycle = _text(candidate.get("model_lifecycle"))
            variant_lifecycle = _text(candidate.get("variant_lifecycle"))
            reader_visible_lifecycle = _text(candidate.get("reader_visible_lifecycle"))
            embedded_lifecycle = _text(candidate.get("embedded_structured_lifecycle"))
            lifecycle_evidence_state = _text(candidate.get("lifecycle_evidence_state"))
            effective_lifecycle = _text(candidate.get("effective_lifecycle"))
            disposition = _text(candidate.get("disposition"))
            decision_critical = candidate.get("decision_critical")
            decision_critical_unknowns = _texts(
                candidate.get("decision_critical_unknowns")
            )
            official_url = _https_url(candidate.get("official_url"))
            evidence_refs = (
                tuple(
                    _https_url(reference)
                    for reference in cast(list[object], candidate.get("evidence_refs"))
                )
                if type(candidate.get("evidence_refs")) is list
                else ()
            )
            exclusion_axis_value = candidate.get("exclusion_axis")
            exclusion_axis = (
                None if exclusion_axis_value is None else _text(exclusion_axis_value)
            )
            reason = _text(candidate.get("reason"))
            if (
                not candidate_id.startswith("EXT-")
                or re.fullmatch(r"EXT-[A-Z0-9]+(?:-[A-Z0-9]+)*", candidate_id, re.ASCII)
                is None
                or candidate_id in seen_candidates
                or candidate_id in product_ids
                or exact_model.casefold()
                in {"other", "unknown", "n/a", "その他", "候補", "現行モデル"}
                or exact_variant_scope.casefold()
                in {"other", "unknown", "n/a", "その他", "全モデル", "型番不明"}
                or use_role not in EXTERNAL_CANDIDATE_USE_ROLES
                or disposition not in {"EXCLUDED", "DEFERRED"}
                or model_lifecycle not in EXTERNAL_CANDIDATE_LIFECYCLE_STATES
                or variant_lifecycle not in EXTERNAL_CANDIDATE_LIFECYCLE_STATES
                or reader_visible_lifecycle not in EXTERNAL_CANDIDATE_LIFECYCLE_STATES
                or embedded_lifecycle
                not in EXTERNAL_CANDIDATE_EMBEDDED_LIFECYCLE_STATES
                or lifecycle_evidence_state
                not in {
                    "CONSISTENT",
                    "CONFLICT",
                    "READER_VISIBLE_ONLY",
                }
                or effective_lifecycle != reader_visible_lifecycle
                or (
                    embedded_lifecycle == "NOT_PRESENT"
                    and lifecycle_evidence_state != "READER_VISIBLE_ONLY"
                )
                or (
                    embedded_lifecycle != "NOT_PRESENT"
                    and embedded_lifecycle == reader_visible_lifecycle
                    and lifecycle_evidence_state != "CONSISTENT"
                )
                or (
                    embedded_lifecycle != "NOT_PRESENT"
                    and embedded_lifecycle != reader_visible_lifecycle
                    and lifecycle_evidence_state != "CONFLICT"
                )
                or type(decision_critical) is not bool
                or decision_critical_unknowns
                or (
                    decision_critical
                    and "UNKNOWN"
                    in {
                        model_lifecycle,
                        variant_lifecycle,
                        reader_visible_lifecycle,
                        effective_lifecycle,
                    }
                )
                or (
                    disposition == "DEFERRED"
                    and effective_lifecycle not in {"PREORDER", "UNKNOWN"}
                    and lifecycle_evidence_state != "CONFLICT"
                )
                or official_url not in evidence_refs
                or len(evidence_refs) != len(set(evidence_refs))
                or exclusion_axis
                not in {*required_axes, "comparison_scope", "lifecycle"}
                # Candidate observations can advance independently from the
                # audit baseline; they may never be backdated before it.
                or _iso_date(candidate.get("evaluated_at")) < evaluated_at
                or len(reason) > 1000
                or "公式情報で照合できない候補" in reason
                or reason == "候補に含めない"
            ):
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            signature = (
                brand,
                exact_model,
                exact_variant_scope,
                model_lifecycle,
                variant_lifecycle,
                reader_visible_lifecycle,
                embedded_lifecycle,
                lifecycle_evidence_state,
                effective_lifecycle,
                official_url,
            )
            previous = candidate_signatures.setdefault(candidate_id, signature)
            if previous != signature:
                _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
            seen_candidates.add(candidate_id)
        audited_ids.add(article_id)
    if audited_ids != set(article_by_id) or len(audited_ids) != 10:
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")


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
        or policy.get("client_measurement_default_enabled") is not False
        or policy.get("additional_tracking_default_enabled") is not False
    ):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    selection_policy = _mapping(document.get("selection_policy"))
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
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    if any(type(value) is not int or value != 0 for value in zero_weights.values()):
        _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
    completion_gate = _mapping(
        _mapping(document.get("evidence_policy")).get("completion_gate")
    )
    if set(completion_gate) != {
        "required_product_count",
        "required_product_card_count",
        "required_affiliate_cta_count",
        "required_product_state",
        "required_product_image_state",
        "maximum_neutral_product_images",
        "maximum_manufacturer_fallback_ctas",
    }:
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
        intent_group_id = _text(row.get("intent_group_id"))
        category_label = _text(row.get("category_label"))
        content_role = _text(row.get("content_role"))
        content_role_label = _text(row.get("content_role_label"))
        primary_query_intent = _text(row.get("primary_query_intent"))
        comparison_scope = _text(row.get("comparison_scope"))
        broader_value = row.get("broader_article_id")
        broader_article_id = None if broader_value is None else _text(broader_value)
        home_order = row.get("home_order")
        snapshot_id = _text(row.get("snapshot_id"))
        related = _texts(row.get("related_article_ids"))
        product_refs = _texts(row.get("product_ids"))
        if (
            article_id in article_ids
            or article_code in article_codes
            or ARTICLE_CODE_RE.fullmatch(article_code) is None
            or cluster_id not in {"mobility", "household", "preparedness"}
            or INTENT_GROUP_CLUSTER.get(intent_group_id) != cluster_id
            or re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", intent_group_id, re.ASCII)
            is None
            or CONTENT_ROLE_LABELS.get(content_role) != content_role_label
            or len(primary_query_intent) > 180
            or len(comparison_scope) > 120
            or (
                content_role in ROLES_REQUIRING_BROADER_ARTICLE
                and broader_article_id is None
            )
            or (
                broader_article_id is not None
                and content_role not in ROLES_ALLOWING_BROADER_ARTICLE
            )
            or type(home_order) is not int
            or home_order <= 0
            or not 1 <= len(related) <= 2
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
        lifecycle_identity = (
            article_id == LIFECYCLE_STATUS_ROUTE_ARTICLE_ID
            and article_code == LIFECYCLE_STATUS_ROUTE_ARTICLE_CODE
        )
        lifecycle_role = content_role == "lifecycle_status_route"
        zero_product_route = not product_refs
        zero_cta_route = not bindings
        if (
            lifecycle_identity != lifecycle_role
            or lifecycle_identity != zero_product_route
            or lifecycle_identity != zero_cta_route
        ):
            _fail("RAOS_EDITORIAL_V3_CONTRACT_INVALID")
        articles.append(
            ArticleBindingV3(
                article_id=article_id,
                article_code=article_code,
                production_slug=production_slug,
                cluster_id=cluster_id,
                intent_group_id=intent_group_id,
                category_label=category_label,
                content_role=content_role,
                content_role_label=content_role_label,
                primary_query_intent=primary_query_intent,
                comparison_scope=comparison_scope,
                broader_article_id=broader_article_id,
                home_order=home_order,
                snapshot_id=snapshot_id,
                related_article_ids=related,
                product_ids=product_refs,
                cta_bindings=tuple(bindings),
            )
        )
    article_by_id = {article.article_id: article for article in articles}
    _validate_market_candidate_audit(
        document.get("market_candidate_audit"),
        article_by_id=article_by_id,
        product_ids=product_ids,
    )
    intent_group_sizes = {
        intent_group_id: sum(
            article.intent_group_id == intent_group_id for article in articles
        )
        for intent_group_id in {article.intent_group_id for article in articles}
    }
    primary_query_intents_by_group = {
        intent_group_id: [
            article.primary_query_intent
            for article in articles
            if article.intent_group_id == intent_group_id
        ]
        for intent_group_id in intent_group_sizes
    }
    if (
        len(articles) != 10
        or len(products) != 33
        or {product_id for article in articles for product_id in article.product_ids}
        != product_ids
        or len(all_cta_ids) != 74
        or completion_gate
        != {
            "required_product_count": len(products),
            "required_product_card_count": sum(
                len(article.product_ids) for article in articles
            ),
            "required_affiliate_cta_count": len(all_cta_ids),
            "required_product_state": "verified",
            "required_product_image_state": "verified",
            "maximum_neutral_product_images": 0,
            "maximum_manufacturer_fallback_ctas": 0,
        }
        or set(intent_group_sizes) != set(INTENT_GROUP_CLUSTER)
        or referenced_provider_slot_ids
        != {
            provider_slots_by_key[(article.article_id, placement)].provider_slot_id
            for article in articles
            if article.product_ids
            for placement in ("product_card", "final_summary")
        }
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
        or any(
            len(values) != len(set(values))
            for values in primary_query_intents_by_group.values()
        )
        or any(
            article.broader_article_id is not None
            and (
                article.broader_article_id not in article_by_id
                or article.broader_article_id == article.article_id
                or article_by_id[article.broader_article_id].intent_group_id
                != article.intent_group_id
                or article_by_id[article.broader_article_id].content_role
                not in {"category_guide", "constraint_shortlist"}
                or article.broader_article_id not in article.related_article_ids
                or article.article_id
                not in article_by_id[article.broader_article_id].related_article_ids
            )
            for article in articles
        )
        or any(
            len(article.related_article_ids)
            != min(2, intent_group_sizes[article.intent_group_id] - 1)
            or any(
                article_by_id[target_id].intent_group_id != article.intent_group_id
                for target_id in article.related_article_ids
            )
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
