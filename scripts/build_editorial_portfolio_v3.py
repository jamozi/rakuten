#!/usr/bin/env python3
"""Build the additive Editorial V3 portfolio and navigation contracts."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Final, NoReturn, cast
from urllib.parse import urlsplit


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.raos_build_core import atomic_write, canonical_json_bytes  # noqa: E402


GENERATOR_PATH: Final = Path("scripts/build_editorial_portfolio_v3.py")
INPUT_PORTFOLIO_PATH: Final = Path(
    "changes/editorial-portfolio-v2/editorial-portfolio.v2.json"
)
INPUT_IDENTITIES_PATH: Final = Path(
    "changes/editorial-portfolio-v3/editorial-identities.v1.json"
)
MARKET_CANDIDATE_AUDIT_PATH: Final = Path(
    "changes/editorial-portfolio-v3/market-candidate-audit.v1.json"
)
PARSER_BOUNDARY_PATH: Final = Path(
    "changes/editorial-portfolio-v3/rakuten-parser-boundary.v1.json"
)
ARTICLE_CONTENT_PATHS: Final = (
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-comparison.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "portable-power-station-guide.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "anker-solix-c300-c800-c1000-differences.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "countertop-dishwasher-for-small-households.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "compact-robot-vacuum-shortlist.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "carry-on-suitcase-under-100-seats.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "lightweight-carry-on-suitcase-under-3kg.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "front-open-carry-on-suitcase-with-stopper.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "roomba-mini-vs-switchbot-k11-pro.html"
    ),
    Path(
        "changes/wordpress-local-preview-v1/fixtures/articles/"
        "solota-vs-rakua-mini-plus.html"
    ),
)
RUNTIME_PATHS: Final = (
    Path("python/raos/application/editorial/editorial_portfolio_v2.py"),
    Path("python/raos/application/editorial/editorial_portfolio_v3.py"),
    Path("python/raos/application/editorial/rakuten_measurement_activation_v3.py"),
    Path("python/raos/application/editorial/rakuten_standard_api_v1.py"),
    Path("python/raos/application/finance/editorial_economics_v3.py"),
    Path("scripts/raos_editorial_economics_v3.py"),
    Path("scripts/raos_rakuten_measurement_activation_v3.py"),
    Path("changes/editorial-portfolio-v3/README.md"),
)
OUTPUT_PATHS: Final = (
    Path("changes/editorial-portfolio-v3/editorial-portfolio.v3.json"),
    Path("changes/editorial-portfolio-v3/generated/navigation.v3.json"),
)
TEST_PATHS: Final = (
    Path("tests/editorial_portfolio_v2"),
    Path("tests/editorial_portfolio_v3"),
)

ARTICLE_CODE_PATTERN: Final = "a{position:02d}"
PRODUCT_CODE_PATTERN: Final = "p{position:02d}"
PLACEMENTS: Final = (
    ("product_card", "card"),
    ("final_summary", "final"),
)
INTERNAL_CTA_NAMESPACE: Final = "RAOS_INTERNAL_CTA_V1"
PROVIDER_SLOT_GRANULARITY: Final = "ARTICLE_PLACEMENT"
PROVIDER_SLOT_LIMIT: Final = 20
CURRENT_THEME_VERSION: Final = "1.5.0"
TARGET_ORIGIN: Final = "https://kurashinoshirube.com"
INTENT_GROUP_CLUSTER: Final = {
    "carry-on-suitcase": "mobility",
    "portable-power": "preparedness",
    "countertop-dishwasher": "household",
    "robot-vacuum": "household",
}
CONTENT_ROLE_LABELS: Final = {
    "brand_family_comparison": "ブランド内比較",
    "category_guide": "選び方",
    "constraint_shortlist": "条件別比較",
    "feature_shortlist": "機能別比較",
    "head_to_head_comparison": "2製品比較",
    "head_to_head_with_reference": "2製品比較＋参考機種",
    "lifecycle_status_route": "以前の比較対象の販売状態確認＋現行比較への案内",
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
RELATIONSHIP_CONTEXTS: Final = {
    "adjacent_condition": "近い条件を別の軸で比べる",
    "broader_guide": "候補を広げて選び直す",
    "lifecycle_reference": "以前の比較対象の販売状況を確認する",
    "narrower_comparison": "条件を絞った比較へ進む",
}


class EditorialV3BuildFailure(RuntimeError):
    """A stable, non-sensitive generator failure."""


def _fail(code: str) -> NoReturn:
    raise EditorialV3BuildFailure(code) from None


def _read_json(relative: Path) -> dict[str, object]:
    try:
        raw = (REPOSITORY_ROOT / relative).read_bytes()
        value = json.loads(raw.decode("utf-8", errors="strict"))
    except OSError, UnicodeError, json.JSONDecodeError:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return cast(dict[str, object], value)


def _mapping(value: object) -> dict[str, object]:
    if type(value) is not dict:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return cast(dict[str, object], value)


def _rows(value: object) -> list[dict[str, object]]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    result: list[dict[str, object]] = []
    for row in cast(list[object], value):
        result.append(_mapping(row))
    return result


def _values(value: object) -> list[object]:
    if type(value) is not list:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return cast(list[object], value)


def _text(value: object) -> str:
    if type(value) is not str or value != value.strip() or not value:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return value


def _positive_integer(value: object) -> int:
    if type(value) is not int or value <= 0:
        _fail("RAOS_EDITORIAL_V3_INPUT_INVALID")
    return value


def _content_sha256(reference: object) -> str:
    relative = Path(_text(reference))
    if (
        relative.is_absolute()
        or ".." in relative.parts
        or relative not in ARTICLE_CONTENT_PATHS
    ):
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    try:
        content = (REPOSITORY_ROOT / relative).read_bytes()
    except OSError:
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    if not content:
        _fail("RAOS_EDITORIAL_V3_CONTENT_REF_INVALID")
    return hashlib.sha256(content).hexdigest()


def _validate_parser_boundary() -> None:
    boundary = _read_json(PARSER_BOUNDARY_PATH)
    if boundary != {
        "schema": "RAOS_EDITORIAL_V3_RAKUTEN_PARSER_BOUNDARY_V1",
        "version": "1.0.0",
        "state": "DISABLED_UNTIL_VERIFIED_SAMPLE_PROFILE_BOUND",
        "authority": "OWNER_PRIVATE_SANITIZED_SAMPLE_REQUIRED",
        "tracked_live_column_names": [],
        "tracked_status_values": [],
        "rules": {
            "automatic_column_guessing": False,
            "automatic_status_guessing": False,
            "direct_requires_verified_measurement_column": True,
            "estimated_never_promoted_to_direct": True,
            "unmatched_measurement_id": "UNATTRIBUTED",
            "dry_run_source_hash_must_equal_commit_source_hash": True,
            "provider_totals_must_reconcile_before_commit": True,
            "raw_rows_remain_owner_private": True,
        },
    }:
        _fail("RAOS_EDITORIAL_V3_PARSER_BOUNDARY_INVALID")


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
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    return url


def _iso_date(value: object) -> str:
    raw = _text(value)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    if parsed.isoformat() != raw:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    return raw


def _validate_market_candidate_audit(
    *,
    v2_articles: list[dict[str, object]],
    identity_articles: list[dict[str, object]],
    v2_product_ids: set[str],
) -> dict[str, object]:
    document = _read_json(MARKET_CANDIDATE_AUDIT_PATH)
    if set(document) != {
        "schema",
        "version",
        "evaluated_at",
        "required_axes",
        "rules",
        "articles",
    }:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    if (
        document["schema"] != "RAOS_EDITORIAL_MARKET_CANDIDATE_AUDIT_V1"
        or document["version"] != "1.0.0"
    ):
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    evaluated_at = _iso_date(document["evaluated_at"])
    required_axes = [_text(value) for value in _values(document["required_axes"])]
    if required_axes != [
        "use_case_fit",
        "safety",
        "dimensions",
        "performance",
        "warranty_and_support",
        "maintainability",
        "primary_source_confidence",
    ]:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    if _mapping(document["rules"]) != {
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
    }:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")

    v2_by_id = {_text(row["article_id"]): row for row in v2_articles}
    identity_by_id = {_text(row["article_id"]): row for row in identity_articles}
    audit_by_id: dict[str, dict[str, object]] = {}
    candidate_signatures: dict[str, tuple[object, ...]] = {}
    exclusion_headings: set[str] = set()
    for audit in _rows(document["articles"]):
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
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        article_id = _text(audit["article_id"])
        exclusion_heading = _text(audit["reader_visible_exclusions_heading"])
        source_article = v2_by_id.get(article_id)
        identity = identity_by_id.get(article_id)
        if source_article is None or identity is None or article_id in audit_by_id:
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        if (
            audit["content_role"] != identity["content_role"]
            or audit["primary_query_intent"] != identity["primary_query_intent"]
            or audit["comparison_scope"] != identity["comparison_scope"]
            or audit["broader_article_id"] != identity["broader_article_id"]
            or audit["candidate_universe_method"] not in MARKET_UNIVERSE_METHODS
            or not 8 <= len(exclusion_heading) <= 60
            or exclusion_heading in exclusion_headings
            or audit["reader_visible_required"] is not True
            or audit["overlap_risk"] != "CONTROLLED_BY_EXPLICIT_SCOPE"
            or len(_text(audit["scope_separation"])) > 500
        ):
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        exclusion_headings.add(exclusion_heading)
        hard_filters = [_text(value) for value in _values(audit["hard_filters"])]
        official_category_sources = [
            _https_url(value) for value in _values(audit["official_category_sources"])
        ]
        if (
            not hard_filters
            or len(hard_filters) != len(set(hard_filters))
            or any(len(value) > 300 for value in hard_filters)
            or not official_category_sources
            or len(official_category_sources) != len(set(official_category_sources))
        ):
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        selected = [_text(value) for value in _values(audit["selected_product_ids"])]
        expected_selected = [
            _text(value) for value in _values(source_article["product_ids"])
        ]
        if (
            selected != expected_selected
            or len(selected) != len(set(selected))
            or not set(selected).issubset(v2_product_ids)
        ):
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        seen_portfolio_candidates: set[str] = set()
        for candidate in _rows(audit["considered_portfolio_candidates"]):
            if set(candidate) != {
                "product_id",
                "disposition",
                "route_article_id",
                "reason",
            }:
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
            product_id = _text(candidate["product_id"])
            route_article_id = _text(candidate["route_article_id"])
            route_article = v2_by_id.get(route_article_id)
            route_identity = identity_by_id.get(route_article_id)
            if (
                product_id in seen_portfolio_candidates
                or product_id in selected
                or product_id not in v2_product_ids
                or candidate["disposition"] != "REFERENCE_ONLY"
                or route_article_id == article_id
                or route_article is None
                or route_identity is None
                or product_id
                not in {_text(value) for value in _values(route_article["product_ids"])}
                or route_identity["intent_group_id"] != identity["intent_group_id"]
                or len(_text(candidate["reason"])) > 800
            ):
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
            seen_portfolio_candidates.add(product_id)

        axis_assessments = _mapping(audit["axis_assessments"])
        if set(axis_assessments) != set(required_axes):
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        for axis in required_axes:
            assessment = _mapping(axis_assessments[axis])
            state = _text(assessment.get("state"))
            is_due_diligence_recheck = (
                state == "SELECTED_PRODUCT_DUE_DILIGENCE_RECHECK_REQUIRED"
            )
            expected_assessment_fields = {
                "state",
                "rationale",
                "evidence_refs",
                *({"recheck_by"} if is_due_diligence_recheck else set()),
            }
            if set(assessment) != expected_assessment_fields:
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
            rationale = _text(assessment["rationale"])
            evidence_refs = [
                _https_url(value) for value in _values(assessment["evidence_refs"])
            ]
            recheck_by = (
                _iso_date(assessment["recheck_by"])
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
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")

        external_candidates = _rows(audit["considered_external_candidates"])
        if not external_candidates:
            _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
        seen_external: set[str] = set()
        for candidate in external_candidates:
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
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
            candidate_id = _text(candidate["candidate_id"])
            brand = _text(candidate["brand"])
            exact_model = _text(candidate["exact_model"])
            exact_variant_scope = _text(candidate["exact_variant_scope"])
            use_role = _text(candidate["use_role"])
            model_lifecycle = _text(candidate["model_lifecycle"])
            variant_lifecycle = _text(candidate["variant_lifecycle"])
            reader_visible_lifecycle = _text(candidate["reader_visible_lifecycle"])
            embedded_lifecycle = _text(candidate["embedded_structured_lifecycle"])
            lifecycle_evidence_state = _text(candidate["lifecycle_evidence_state"])
            effective_lifecycle = _text(candidate["effective_lifecycle"])
            disposition = _text(candidate["disposition"])
            decision_critical = candidate["decision_critical"]
            decision_critical_unknowns = [
                _text(value)
                for value in _values(candidate["decision_critical_unknowns"])
            ]
            official_url = _https_url(candidate["official_url"])
            evidence_refs = tuple(
                _https_url(value) for value in _values(candidate["evidence_refs"])
            )
            exclusion_axis_value = candidate["exclusion_axis"]
            exclusion_axis = (
                None if exclusion_axis_value is None else _text(exclusion_axis_value)
            )
            reason = _text(candidate["reason"])
            if (
                not candidate_id.startswith("EXT-")
                or re.fullmatch(r"EXT-[A-Z0-9]+(?:-[A-Z0-9]+)*", candidate_id, re.ASCII)
                is None
                or candidate_id in seen_external
                or candidate_id in v2_product_ids
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
                # The top-level date is the audit baseline. Individual current
                # candidates may be rechecked later without falsely backdating
                # every untouched candidate to the newest observation date.
                or _iso_date(candidate["evaluated_at"]) < evaluated_at
                or len(reason) > 1000
                or "公式情報で照合できない候補" in reason
                or "候補に含めない" == reason
            ):
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
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
            previous_signature = candidate_signatures.setdefault(
                candidate_id, signature
            )
            if previous_signature != signature:
                _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
            seen_external.add(candidate_id)
        audit_by_id[article_id] = audit
    if set(audit_by_id) != set(v2_by_id) or len(audit_by_id) != 10:
        _fail("RAOS_EDITORIAL_V3_MARKET_AUDIT_INVALID")
    return document


def build_documents() -> tuple[dict[str, object], dict[str, object]]:
    v2 = _read_json(INPUT_PORTFOLIO_PATH)
    identities = _read_json(INPUT_IDENTITIES_PATH)
    _validate_parser_boundary()
    if (
        v2.get("schema") != "RAOS_EDITORIAL_PORTFOLIO_V2"
        or v2.get("target_origin") != TARGET_ORIGIN
    ):
        _fail("RAOS_EDITORIAL_V3_PREDECESSOR_INVALID")
    if identities.get("schema") != "RAOS_EDITORIAL_V3_IDENTITIES_V1":
        _fail("RAOS_EDITORIAL_V3_IDENTITIES_INVALID")

    v2_articles = _rows(v2.get("articles"))
    v2_products = _rows(v2.get("products"))
    identity_articles = _rows(identities.get("articles"))
    identity_products = _rows(identities.get("products"))
    cluster_rows = _rows(identities.get("clusters"))
    evidence_policy = _mapping(v2.get("evidence_policy"))
    completion_gate = _mapping(evidence_policy.get("completion_gate"))
    required_product_count = completion_gate.get("required_product_count")
    if (
        len(v2_articles) != 10
        or type(required_product_count) is not int
        or required_product_count <= 0
        or len(v2_products) != required_product_count
    ):
        _fail("RAOS_EDITORIAL_V3_PREDECESSOR_CARDINALITY_INVALID")
    if (
        len(identity_articles) != 10
        or len(identity_products) != required_product_count
    ):
        _fail("RAOS_EDITORIAL_V3_IDENTITIES_CARDINALITY_INVALID")
    selection_policy = _mapping(v2.get("selection_policy"))
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
        _fail("RAOS_EDITORIAL_V3_SELECTION_POLICY_INVALID")
    if any(type(value) is not int or value != 0 for value in zero_weights.values()):
        _fail("RAOS_EDITORIAL_V3_SELECTION_POLICY_INVALID")

    v2_article_ids = [_text(row.get("article_id")) for row in v2_articles]
    v2_product_ids = [_text(row.get("product_id")) for row in v2_products]
    v2_article_by_id = {_text(row.get("article_id")): row for row in v2_articles}
    article_identity_by_id = {
        _text(row.get("article_id")): row for row in identity_articles
    }
    product_identity_by_id = {
        _text(row.get("product_id")): row for row in identity_products
    }
    if set(article_identity_by_id) != set(v2_article_ids):
        _fail("RAOS_EDITORIAL_V3_ARTICLE_IDENTITY_COVERAGE_INVALID")
    if set(product_identity_by_id) != set(v2_product_ids):
        _fail("RAOS_EDITORIAL_V3_PRODUCT_IDENTITY_COVERAGE_INVALID")

    cluster_by_id: dict[str, dict[str, object]] = {}
    for expected_order, cluster in enumerate(cluster_rows, start=1):
        if set(cluster) != {"cluster_id", "category_label", "home_order"}:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        cluster_id = _text(cluster["cluster_id"])
        if cluster_id in cluster_by_id:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        if _positive_integer(cluster["home_order"]) != expected_order:
            _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")
        _text(cluster["category_label"])
        cluster_by_id[cluster_id] = cluster
    if set(cluster_by_id) != {"mobility", "household", "preparedness"}:
        _fail("RAOS_EDITORIAL_V3_CLUSTER_INVALID")

    product_code_by_id: dict[str, str] = {}
    v3_products: list[dict[str, object]] = []
    for position, product in enumerate(v2_products, start=1):
        product_id = _text(product.get("product_id"))
        identity = product_identity_by_id[product_id]
        if set(identity) != {"product_id", "product_code"}:
            _fail("RAOS_EDITORIAL_V3_PRODUCT_IDENTITY_INVALID")
        product_code = _text(identity["product_code"])
        if product_code != PRODUCT_CODE_PATTERN.format(position=position):
            _fail("RAOS_EDITORIAL_V3_PRODUCT_CODE_INVALID")
        product_code_by_id[product_id] = product_code
        v3_products.append({**product, "product_code": product_code})
    if len(set(product_code_by_id.values())) != len(product_code_by_id):
        _fail("RAOS_EDITORIAL_V3_PRODUCT_CODE_INVALID")

    article_code_by_id: dict[str, str] = {}
    article_cluster_by_id: dict[str, str] = {}
    article_intent_group_by_id: dict[str, str] = {}
    article_primary_query_intent_by_id: dict[str, str] = {}
    article_content_role_by_id: dict[str, str] = {}
    article_broader_by_id: dict[str, str | None] = {}
    for position, article_id in enumerate(v2_article_ids, start=1):
        identity = article_identity_by_id[article_id]
        if set(identity) != {
            "article_id",
            "article_code",
            "cluster_id",
            "intent_group_id",
            "content_role",
            "content_role_label",
            "primary_query_intent",
            "comparison_scope",
            "broader_article_id",
            "home_order",
            "related_article_ids",
        }:
            _fail("RAOS_EDITORIAL_V3_ARTICLE_IDENTITY_INVALID")
        article_code = _text(identity["article_code"])
        if article_code != ARTICLE_CODE_PATTERN.format(position=position):
            _fail("RAOS_EDITORIAL_V3_ARTICLE_CODE_INVALID")
        cluster_id = _text(identity["cluster_id"])
        if cluster_id not in cluster_by_id:
            _fail("RAOS_EDITORIAL_V3_ARTICLE_CLUSTER_INVALID")
        if _text(v2_article_by_id[article_id]["category"]) != _text(
            cluster_by_id[cluster_id]["category_label"]
        ):
            _fail("RAOS_EDITORIAL_V3_ARTICLE_CLUSTER_INVALID")
        intent_group_id = _text(identity["intent_group_id"])
        if INTENT_GROUP_CLUSTER.get(intent_group_id) != cluster_id:
            _fail("RAOS_EDITORIAL_V3_ARTICLE_INTENT_GROUP_INVALID")
        content_role = _text(identity["content_role"])
        primary_query_intent = _text(identity["primary_query_intent"])
        if (
            CONTENT_ROLE_LABELS.get(content_role)
            != _text(identity["content_role_label"])
            or len(_text(identity["comparison_scope"])) > 120
            or len(primary_query_intent) > 180
        ):
            _fail("RAOS_EDITORIAL_V3_CONTENT_ROLE_INVALID")
        broader_value = identity["broader_article_id"]
        if broader_value is None:
            broader_article_id = None
        else:
            broader_article_id = _text(broader_value)
        if (
            content_role in ROLES_REQUIRING_BROADER_ARTICLE
            and broader_article_id is None
        ) or (
            broader_article_id is not None
            and content_role not in ROLES_ALLOWING_BROADER_ARTICLE
        ):
            _fail("RAOS_EDITORIAL_V3_CONTENT_ROLE_INVALID")
        article_code_by_id[article_id] = article_code
        article_cluster_by_id[article_id] = cluster_id
        article_intent_group_by_id[article_id] = intent_group_id
        article_primary_query_intent_by_id[article_id] = primary_query_intent
        article_content_role_by_id[article_id] = content_role
        article_broader_by_id[article_id] = broader_article_id
    if len(set(article_code_by_id.values())) != len(article_code_by_id):
        _fail("RAOS_EDITORIAL_V3_ARTICLE_CODE_INVALID")
    for intent_group_id in INTENT_GROUP_CLUSTER:
        query_intents = [
            article_primary_query_intent_by_id[article_id]
            for article_id, group_id in article_intent_group_by_id.items()
            if group_id == intent_group_id
        ]
        if len(query_intents) != len(set(query_intents)):
            _fail("RAOS_EDITORIAL_V3_PRIMARY_QUERY_INTENT_INVALID")

    intent_group_size = {
        intent_group_id: sum(
            1
            for value in article_intent_group_by_id.values()
            if value == intent_group_id
        )
        for intent_group_id in INTENT_GROUP_CLUSTER
    }
    if any(size < 2 for size in intent_group_size.values()):
        _fail("RAOS_EDITORIAL_V3_ARTICLE_INTENT_GROUP_INVALID")
    for article_id, broader_article_id in article_broader_by_id.items():
        if broader_article_id is None:
            continue
        broader_identity = article_identity_by_id.get(broader_article_id)
        if broader_identity is None:
            _fail("RAOS_EDITORIAL_V3_BROADER_ARTICLE_INVALID")
        narrow_related = {
            _text(value)
            for value in _values(
                article_identity_by_id[article_id]["related_article_ids"]
            )
        }
        broader_related = {
            _text(value) for value in _values(broader_identity["related_article_ids"])
        }
        if (
            broader_article_id == article_id
            or broader_article_id not in article_code_by_id
            or article_intent_group_by_id[broader_article_id]
            != article_intent_group_by_id[article_id]
            or article_content_role_by_id[broader_article_id]
            not in {"category_guide", "constraint_shortlist"}
            or broader_article_id not in narrow_related
            or article_id not in broader_related
        ):
            _fail("RAOS_EDITORIAL_V3_BROADER_ARTICLE_INVALID")
    market_candidate_audit = _validate_market_candidate_audit(
        v2_articles=v2_articles,
        identity_articles=identity_articles,
        v2_product_ids=set(v2_product_ids),
    )

    home_orders: dict[str, set[int]] = {key: set() for key in cluster_by_id}
    v3_articles: list[dict[str, object]] = []
    provider_slots: list[dict[str, object]] = []
    navigation_articles: list[dict[str, object]] = []
    for article in v2_articles:
        article_id = _text(article.get("article_id"))
        identity = article_identity_by_id[article_id]
        article_code = article_code_by_id[article_id]
        cluster_id = article_cluster_by_id[article_id]
        intent_group_id = article_intent_group_by_id[article_id]
        content_role = article_content_role_by_id[article_id]
        content_role_label = _text(identity["content_role_label"])
        primary_query_intent = article_primary_query_intent_by_id[article_id]
        comparison_scope = _text(identity["comparison_scope"])
        broader_article_id = article_broader_by_id[article_id]
        cluster = cluster_by_id[cluster_id]
        home_order = _positive_integer(identity["home_order"])
        if home_order in home_orders[cluster_id]:
            _fail("RAOS_EDITORIAL_V3_HOME_ORDER_INVALID")
        home_orders[cluster_id].add(home_order)
        related = [
            _text(value)
            for value in cast(list[object], identity["related_article_ids"])
        ]
        expected_related_count = min(2, intent_group_size[intent_group_id] - 1)
        if (
            len(related) != expected_related_count
            or len(related) != len(set(related))
            or article_id in related
            or not set(related).issubset(article_code_by_id)
            or any(
                article_intent_group_by_id[value] != intent_group_id
                for value in related
            )
        ):
            _fail("RAOS_EDITORIAL_V3_RELATED_ARTICLES_INVALID")
        product_ids = [
            _text(value) for value in cast(list[object], article["product_ids"])
        ]
        content_sha256 = _content_sha256(article.get("content_ref"))
        snapshot_id = f"snp-{article_code}-{content_sha256[:12]}"
        slot_by_placement: dict[str, str] = {}
        for placement, placement_code in PLACEMENTS:
            provider_slot_id = f"rps-{article_code}-{placement_code}"
            slot_by_placement[placement] = provider_slot_id
            provider_slots.append(
                {
                    "provider_slot_id": provider_slot_id,
                    "article_id": article_id,
                    "article_code": article_code,
                    "placement": placement,
                    "placement_code": placement_code,
                    "provider_profile_state": "UNVERIFIED_DISABLED",
                }
            )
        bindings: list[dict[str, object]] = []
        for product_id in product_ids:
            bound_product_code = product_code_by_id.get(product_id)
            if bound_product_code is None:
                _fail("RAOS_EDITORIAL_V3_PRODUCT_REFERENCE_INVALID")
            offer_id = f"off-{article_code}-{bound_product_code}"
            for placement, placement_code in PLACEMENTS:
                internal_cta_id = (
                    f"icta_{article_code}_{bound_product_code}_{placement_code}"
                )
                bindings.append(
                    {
                        "article_id": article_id,
                        "article_code": article_code,
                        "product_id": product_id,
                        "product_code": bound_product_code,
                        "snapshot_id": snapshot_id,
                        "offer_id": offer_id,
                        "cta_id": internal_cta_id,
                        "placement": placement,
                        "placement_code": placement_code,
                        "provider_slot_id": slot_by_placement[placement],
                        "provider_profile_state": "UNVERIFIED_DISABLED",
                    }
                )
        category_label = _text(cluster["category_label"])

        def related_record(related_id: str) -> dict[str, str]:
            if broader_article_id == related_id:
                relationship = "broader_guide"
            elif (
                article_broader_by_id[related_id] == article_id
                and article_content_role_by_id[related_id]
                == "lifecycle_status_route"
            ):
                relationship = "lifecycle_reference"
            elif article_broader_by_id[related_id] == article_id:
                relationship = "narrower_comparison"
            else:
                relationship = "adjacent_condition"
            return {
                "article_id": related_id,
                "relationship": relationship,
                "context": RELATIONSHIP_CONTEXTS[relationship],
            }

        related_records = [related_record(related_id) for related_id in related]
        relationship_priority = {
            "broader_guide": 0,
            "lifecycle_reference": 1,
            "narrower_comparison": 2,
            "adjacent_condition": 3,
        }
        observed_relationship_priority = [
            relationship_priority[row["relationship"]] for row in related_records
        ]
        if observed_relationship_priority != sorted(observed_relationship_priority):
            _fail("RAOS_EDITORIAL_V3_RELATED_ARTICLES_INVALID")
        v3_articles.append(
            {
                **article,
                "v2_category": article.get("category"),
                "article_code": article_code,
                "cluster_id": cluster_id,
                "intent_group_id": intent_group_id,
                "content_role": content_role,
                "content_role_label": content_role_label,
                "primary_query_intent": primary_query_intent,
                "comparison_scope": comparison_scope,
                "broader_article_id": broader_article_id,
                "category": cluster_id,
                "category_label": category_label,
                "home_order": home_order,
                "content_snapshot_sha256": content_sha256,
                "snapshot_id": snapshot_id,
                "related_article_ids": related,
                "related_articles": related_records,
                "cta_bindings": bindings,
            }
        )
        navigation_articles.append(
            {
                "article_id": article_id,
                "article_code": article_code,
                "production_slug": _text(article["production_slug"]),
                "title": _text(article["title"]),
                "cluster_id": cluster_id,
                "intent_group_id": intent_group_id,
                "content_role": content_role,
                "content_role_label": content_role_label,
                "primary_query_intent": primary_query_intent,
                "comparison_scope": comparison_scope,
                "broader_article_id": broader_article_id,
                "category_label": category_label,
                "home_order": home_order,
                "related_articles": [
                    {
                        "article_id": related_id,
                        "article_code": article_code_by_id[related_id],
                        "production_slug": _text(
                            next(
                                candidate["production_slug"]
                                for candidate in v2_articles
                                if candidate["article_id"] == related_id
                            )
                        ),
                        "relationship": related_record(related_id)["relationship"],
                        "context": related_record(related_id)["context"],
                    }
                    for related_id in related
                ],
            }
        )

    for cluster_id, orders in home_orders.items():
        count = sum(
            1 for value in article_cluster_by_id.values() if value == cluster_id
        )
        if orders != set(range(1, count + 1)):
            _fail("RAOS_EDITORIAL_V3_HOME_ORDER_INVALID")

    internal_cta_ids = [
        _text(binding["cta_id"])
        for article in v3_articles
        for binding in cast(list[dict[str, object]], article["cta_bindings"])
    ]
    provider_slot_ids = [_text(slot["provider_slot_id"]) for slot in provider_slots]
    provider_slot_keys = [
        (_text(slot["article_id"]), _text(slot["placement"])) for slot in provider_slots
    ]
    if len(internal_cta_ids) != 74 or len(set(internal_cta_ids)) != 74:
        _fail("RAOS_EDITORIAL_V3_CTA_ID_INVALID")
    if (
        len(provider_slot_ids) != PROVIDER_SLOT_LIMIT
        or len(set(provider_slot_ids)) != PROVIDER_SLOT_LIMIT
        or len(set(provider_slot_keys)) != PROVIDER_SLOT_LIMIT
    ):
        _fail("RAOS_EDITORIAL_V3_PROVIDER_SLOT_INVALID")

    clusters = [
        {
            **cluster,
            "article_ids": [
                _text(article["article_id"])
                for article in sorted(
                    (
                        row
                        for row in navigation_articles
                        if row["cluster_id"] == cluster["cluster_id"]
                    ),
                    key=lambda row: cast(int, row["home_order"]),
                )
            ],
        }
        for cluster in cluster_rows
    ]
    portfolio = {
        "schema": "RAOS_EDITORIAL_PORTFOLIO_V3",
        "version": "3.0.0",
        "predecessor": {
            "schema": "RAOS_EDITORIAL_PORTFOLIO_V2",
            "version": v2.get("version"),
            "historical_contract_preserved": True,
        },
        "target_origin": v2.get("target_origin"),
        "theme_version": CURRENT_THEME_VERSION,
        "evidence_policy": v2.get("evidence_policy"),
        "selection_policy": selection_policy,
        "content_contract": v2.get("content_contract"),
        "market_candidate_audit": market_candidate_audit,
        "strategy": {
            "article_count": 10,
            "cluster_count": 3,
            "new_content_gate": "NO_NEW_CONTENT_UNTIL_ACTUAL_DATA_GATE",
            "north_star": {
                "metric": "MONTHLY_CONFIRMED_CONTRIBUTION_PROFIT_JPY",
                "formula": (
                    "confirmed_reward_jpy - variable_external_cost_jpy - "
                    "editorial_minutes / 60 * approved_hourly_cost_jpy"
                ),
                "missing_value": "UNAVAILABLE",
                "unattributed_article_allocation": False,
            },
        },
        "rakuten_measurement_policy": {
            "internal_cta_id_format": (
                "icta_{article_code}_{product_code}_{card|final}"
            ),
            "placements": [placement for placement, _code in PLACEMENTS],
            "internal_cta_identity_count": len(internal_cta_ids),
            "internal_cta_namespace": INTERNAL_CTA_NAMESPACE,
            "provider_slot_format": "rps-{article_code}-{card|final}",
            "provider_slot_count": len(provider_slots),
            "provider_slot_limit": PROVIDER_SLOT_LIMIT,
            "provider_slot_granularity": PROVIDER_SLOT_GRANULARITY,
            "provider_measurement_id_storage": "OWNER_PRIVATE_ONLY",
            "provider_profile_state": "UNVERIFIED_DISABLED",
            "live_link_mutation_allowed": False,
            "client_measurement_default_enabled": False,
            "additional_tracking_default_enabled": False,
            "activation_gate": "VERIFIED_SAMPLE_PROFILE_AND_PROVIDER_CONSOLE_RECONCILIATION",
        },
        "rakuten_provider_slots": provider_slots,
        "clusters": clusters,
        "articles": v3_articles,
        "products": v3_products,
    }
    navigation = {
        "schema": "RAOS_EDITORIAL_NAVIGATION_V3",
        "version": "3.0.0",
        "target_origin": v2.get("target_origin"),
        "source_portfolio_schema": "RAOS_EDITORIAL_PORTFOLIO_V3",
        "clusters": clusters,
        "articles": sorted(
            navigation_articles,
            key=lambda row: (
                _positive_integer(
                    cluster_by_id[_text(row["cluster_id"])]["home_order"]
                ),
                _positive_integer(row["home_order"]),
            ),
        ),
    }
    return portfolio, navigation


def _check_or_write(path: Path, content: bytes, *, check: bool) -> None:
    absolute = REPOSITORY_ROOT / path
    if check:
        try:
            current = absolute.read_bytes()
        except OSError:
            _fail("RAOS_EDITORIAL_V3_OUTPUT_MISSING")
        if current != content:
            _fail("RAOS_EDITORIAL_V3_OUTPUT_DRIFT")
        return
    atomic_write(path, content)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args(argv)
    try:
        documents = build_documents()
        for path, document in zip(OUTPUT_PATHS, documents, strict=True):
            _check_or_write(path, canonical_json_bytes(document), check=arguments.check)
        print(
            "RAOS_EDITORIAL_V3_GENERATION "
            f"mode={'check' if arguments.check else 'write'} status=PASS"
        )
        return 0
    except EditorialV3BuildFailure as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
