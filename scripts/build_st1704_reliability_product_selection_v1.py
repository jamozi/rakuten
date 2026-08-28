#!/usr/bin/env python3
"""Generate the ST-1704 reliability-first product selection V1 package."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Final


REPOSITORY_ROOT: Final = Path(__file__).resolve().parents[1]
PYTHON_ROOT_TEXT: Final = f"{REPOSITORY_ROOT}/python"
if PYTHON_ROOT_TEXT not in sys.path:
    sys.path.insert(0, PYTHON_ROOT_TEXT)

from raos.adapters.reliability_product_research_v1 import (  # noqa: E402
    RAKUTEN_SOURCE_ID,
    YAHOO_SOURCE_ID,
    RecordedProductSearchAdapterV1,
)
from raos.application.editorial.reliability_research_v1 import (  # noqa: E402
    DiscoveryServiceV1,
    build_article_snapshot,
    build_review_packet,
    resolve_identities,
)
from raos.domain.reliability.contracts_v1 import (  # noqa: E402
    AcquisitionMethodV1,
    ArticleEvidenceSnapshotV1,
    CandidateDecisionV1,
    DiscoveryCheckpointV1,
    DiscoveryOfferV1,
    DiscoveryRunV1,
    EvidenceDimensionScoresV1,
    FitCandidateV1,
    FitScoreV1,
    MonitorDiffV1,
    MonitoringPolicyV1,
    OfferPriceV1,
    ProductReviewSignalV1,
    ProviderPageV1,
    ResearchPlanV1,
    ReviewAggregateSetV1,
    ReviewDecisionV1,
    ReviewObservationV1,
    ReviewPacketV1,
    ReviewThemeSetV1,
    SafetyObservationV1,
    SocialSignalSetV1,
    SourceDecisionV1,
    SourcePolicyV1,
    SourceRuleV1,
    StrictContractV1,
    TrustedRecommendationResultV1,
    VerificationStateV1,
    artifact_ref,
    canonical_json_bytes,
)
from raos.domain.reliability.selection_v1 import (  # noqa: E402
    PROFILES,
    calculate_fit_scores,
    calculate_review_aggregates,
)


SCHEMA_CATALOG_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/contracts/schema-catalog.v1.json"
)
RESEARCH_PLAN_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/research-plan.v1.json"
)
SOURCE_POLICY_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/source-policy.v1.json"
)
RECORDED_PAGES_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/recorded-provider-pages.v1.json"
)
DISCOVERY_RUN_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/discovery-run.v1.json"
)
CANDIDATE_LEDGER_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/candidate-ledger.v1.json"
)
FIT_SCORES_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/fit-scores.v1.json"
)
REVIEW_AGGREGATES_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/review-aggregates.v1.json"
)
ARTICLE_SNAPSHOT_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/article-evidence-snapshot.v1.json"
)
REVIEW_PACKET_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/review-packet.v1.json"
)
MONITORING_POLICY_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/generated/monitoring-policy.v1.json"
)
RUNTIME_MANIFEST_PATH: Final = Path(
    "changes/st-1704/reliability-product-selection-v1/runtime-manifest.v1.json"
)
OUTPUT_PATHS: Final = (
    SCHEMA_CATALOG_PATH,
    RESEARCH_PLAN_PATH,
    SOURCE_POLICY_PATH,
    RECORDED_PAGES_PATH,
    DISCOVERY_RUN_PATH,
    CANDIDATE_LEDGER_PATH,
    FIT_SCORES_PATH,
    REVIEW_AGGREGATES_PATH,
    ARTICLE_SNAPSHOT_PATH,
    REVIEW_PACKET_PATH,
    MONITORING_POLICY_PATH,
    RUNTIME_MANIFEST_PATH,
)
SOURCE_PATHS: Final = (
    Path("python/raos/domain/reliability/contracts_v1.py"),
    Path("python/raos/domain/reliability/selection_v1.py"),
    Path("python/raos/application/editorial/reliability_research_v1.py"),
    Path("python/raos/ports/reliability/research_v1.py"),
    Path("python/raos/adapters/reliability_product_research_v1.py"),
    Path("scripts/raos_product_research.py"),
)
FIXED_NOW: Final = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("utf-8")


def _artifact_bytes(value: StrictContractV1) -> bytes:
    return canonical_json_bytes(value) + b"\n"


def _source_policy() -> SourcePolicyV1:
    return SourcePolicyV1(
        artifact_id="source-policy:trust-selection-v1",
        rules=(
            SourceRuleV1(
                source_id=RAKUTEN_SOURCE_ID,
                decision=SourceDecisionV1.ALLOW_AGGREGATE_ONLY,
                acquisition_method=AcquisitionMethodV1.JSON_API,
                allowed_hosts=("openapi.rakuten.co.jp",),
                allowed_path_prefixes=(
                    "/ichibams/api/IchibaItem/Search/20260701",
                ),
                allowed_exact_urls=(),
                allowed_fields=(
                    "itemCode",
                    "itemName",
                    "itemUrl",
                    "itemPrice",
                    "reviewAverage",
                    "reviewCount",
                    "shopCode",
                    "shopName",
                    "jan",
                ),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=True,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=(
                    ".secrets/rakuten-owner-local/credentials.v1.json"
                ),
                minimum_request_interval_ms=1100,
                freshness_hours=24,
                retention_months=13,
            ),
            SourceRuleV1(
                source_id=YAHOO_SOURCE_ID,
                decision=SourceDecisionV1.ALLOW_AGGREGATE_ONLY,
                acquisition_method=AcquisitionMethodV1.JSON_API,
                allowed_hosts=("shopping.yahooapis.jp",),
                allowed_path_prefixes=("/ShoppingWebService/V3/itemSearch",),
                allowed_exact_urls=(),
                allowed_fields=(
                    "code",
                    "name",
                    "url",
                    "price",
                    "janCode",
                    "brand.name",
                    "review.rate",
                    "review.count",
                ),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=True,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=(
                    ".secrets/yahoo-shopping-owner-local/credentials.v1.json"
                ),
                minimum_request_interval_ms=1100,
                freshness_hours=24,
                retention_months=13,
            ),
            SourceRuleV1(
                source_id="ACE_OFFICIAL",
                decision=SourceDecisionV1.ALLOW_STRUCTURED_FIELDS,
                acquisition_method=AcquisitionMethodV1.EXACT_URL_HTML,
                allowed_hosts=("store.ace.jp",),
                allowed_path_prefixes=("/shop/g/",),
                allowed_exact_urls=(
                    "https://store.ace.jp/shop/g/g06316-01/",
                    "https://store.ace.jp/shop/g/g05721-04",
                    "https://store.ace.jp/shop/g/g01471-02",
                ),
                allowed_fields=(
                    "model",
                    "dimensions",
                    "capacity",
                    "weight",
                    "access",
                    "support",
                    "warranty",
                ),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=True,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=None,
                minimum_request_interval_ms=1100,
                freshness_hours=2160,
                retention_months=120,
            ),
            SourceRuleV1(
                source_id="NITE_SAFE_LITE",
                decision=SourceDecisionV1.ALLOW_STRUCTURED_FIELDS,
                acquisition_method=AcquisitionMethodV1.EXACT_URL_HTML,
                allowed_hosts=("www.nite.go.jp",),
                allowed_path_prefixes=("/jiko/jikojohou/safe-lite",),
                allowed_exact_urls=(
                    "https://www.nite.go.jp/jiko/jikojohou/safe-lite.html",
                ),
                allowed_fields=("recall_status", "model", "announcement_date"),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=True,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=None,
                minimum_request_interval_ms=1100,
                freshness_hours=24,
                retention_months=120,
            ),
            SourceRuleV1(
                source_id="REVIEW_BODY_FUTURE",
                decision=SourceDecisionV1.UNKNOWN,
                acquisition_method=AcquisitionMethodV1.DISABLED,
                allowed_hosts=(),
                allowed_path_prefixes=(),
                allowed_exact_urls=(),
                allowed_fields=(),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=False,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=None,
                minimum_request_interval_ms=0,
                freshness_hours=720,
                retention_months=13,
            ),
            SourceRuleV1(
                source_id="SOCIAL_FUTURE",
                decision=SourceDecisionV1.UNKNOWN,
                acquisition_method=AcquisitionMethodV1.DISABLED,
                allowed_hosts=(),
                allowed_path_prefixes=(),
                allowed_exact_urls=(),
                allowed_fields=(),
                raw_body_storage_allowed=False,
                quotation_storage_allowed=False,
                derived_storage_allowed=False,
                terms_checked_by=None,
                terms_checked_at=None,
                credential_ref=None,
                minimum_request_interval_ms=0,
                freshness_hours=720,
                retention_months=13,
            ),
        ),
        created_at=FIXED_NOW,
    )


def _offer(
    *,
    source: str,
    item_id: str,
    title: str,
    jan: str | None,
    brand: str | None,
    model: str | None,
    price: int,
    rating: str,
    count: int,
) -> DiscoveryOfferV1:
    host = "item.rakuten.co.jp" if source == RAKUTEN_SOURCE_ID else "store.shopping.yahoo.co.jp"
    return DiscoveryOfferV1(
        source_id=source,
        provider_item_id=item_id,
        item_url=f"https://{host}/fixture/{item_id.replace(':', '-')}",
        title=title,
        jan_gtin=jan,
        brand=brand,
        manufacturer_part_number=model,
        variant_label=model,
        displayed_price_jpy=price,
        review_average=Decimal(rating),
        review_count=count,
        observed_at=FIXED_NOW,
    )


def _page(
    *, source: str, query_index: int, offers: tuple[DiscoveryOfferV1, ...]
) -> ProviderPageV1:
    query = ("機内持ち込み スーツケース", "機内持ち込み キャリーケース")[
        query_index
    ]
    material = f"{source}:{query_index}:1:{query}".encode("utf-8")
    response = _json_bytes([item.model_dump(mode="json") for item in offers])
    return ProviderPageV1(
        source_id=source,
        query_index=query_index,
        page=1,
        offers=offers,
        request_fingerprint=hashlib.sha256(material).hexdigest(),
        response_sha256=hashlib.sha256(response).hexdigest(),
        is_last_page=True,
    )


def _pages() -> tuple[ProviderPageV1, ...]:
    cresta_r = _offer(
        source=RAKUTEN_SOURCE_ID,
        item_id="ace:06316",
        title="ACE クレスタ 06316 機内持ち込み スーツケース 34L",
        jan="4549531590011",
        brand="ACE",
        model="06316",
        price=31_900,
        rating="4.50",
        count=120,
    )
    difference_r = _offer(
        source=RAKUTEN_SOURCE_ID,
        item_id="ace:05721",
        title="ace.TOKYO ディフェレンス 05721 32L",
        jan="4549531580029",
        brand="ACE",
        model="05721",
        price=39_600,
        rating="4.35",
        count=72,
    )
    maxpass_r = _offer(
        source=RAKUTEN_SOURCE_ID,
        item_id="ace:01471",
        title="PROTECA マックスパス4 01471 40L",
        jan="4549531570037",
        brand="PROTECA",
        model="01471",
        price=79_200,
        rating="4.70",
        count=55,
    )
    accessory = _offer(
        source=RAKUTEN_SOURCE_ID,
        item_id="parts:cover01",
        title="スーツケース 保護カバー 機内持ち込み用",
        jan=None,
        brand=None,
        model=None,
        price=1_980,
        rating="4.20",
        count=200,
    )
    cresta_y = _offer(
        source=YAHOO_SOURCE_ID,
        item_id="ace-06316",
        title="ACE クレスタ 06316 機内持ち込み 34L",
        jan="4549531590011",
        brand="ACE",
        model="06316",
        price=32_450,
        rating="4.42",
        count=88,
    )
    difference_y = _offer(
        source=YAHOO_SOURCE_ID,
        item_id="ace-05721",
        title="ace.TOKYO ディフェレンス 05721 32L",
        jan="4549531580029",
        brand="ACE",
        model="05721",
        price=40_100,
        rating="4.30",
        count=42,
    )
    maxpass_y = _offer(
        source=YAHOO_SOURCE_ID,
        item_id="ace-01471",
        title="PROTECA マックスパス4 01471 40L",
        jan="4549531570037",
        brand="PROTECA",
        model="01471",
        price=78_900,
        rating="4.61",
        count=31,
    )
    return (
        _page(source=RAKUTEN_SOURCE_ID, query_index=0, offers=(cresta_r, maxpass_r)),
        _page(source=RAKUTEN_SOURCE_ID, query_index=1, offers=(difference_r, accessory)),
        _page(source=YAHOO_SOURCE_ID, query_index=0, offers=(cresta_y, maxpass_y)),
        _page(source=YAHOO_SOURCE_ID, query_index=1, offers=(difference_y,)),
    )


def _clock() -> datetime:
    return FIXED_NOW


def _build_models() -> tuple[
    ResearchPlanV1,
    SourcePolicyV1,
    MonitoringPolicyV1,
    tuple[ProviderPageV1, ...],
    DiscoveryRunV1,
    tuple[CandidateDecisionV1, ...],
    tuple[FitScoreV1, ...],
    ReviewAggregateSetV1,
    ArticleEvidenceSnapshotV1,
    ReviewPacketV1,
]:
    plan = ResearchPlanV1(
        artifact_id="research-plan:suitcase-v1",
        profiles=PROFILES,
        created_at=FIXED_NOW,
    )
    policy = _source_policy()
    monitoring = MonitoringPolicyV1(artifact_id="monitoring-policy:pilot-v1")
    pages = _pages()
    run = DiscoveryServiceV1(
        port=RecordedProductSearchAdapterV1(pages), clock=_clock
    ).discover(
        plan=plan,
        policy=policy,
        mode="RECORDED",
        artifact_id="discovery-run:recorded-v1",
    )
    decisions = resolve_identities(run, decided_at=FIXED_NOW)
    included = {
        item.canonical_product_key: item.product_id
        for item in decisions
        if item.product_id is not None
    }
    specifications = {
        "JAN:4549531590011": ("55", "35", "25", "3.2", "34", "50", "100"),
        "JAN:4549531580029": ("55", "36", "24", "3.5", "32", "100", "100"),
        "JAN:4549531570037": ("50", "40", "25", "3.6", "40", "100", "100"),
    }
    fit_candidates: list[FitCandidateV1] = []
    review_observations: list[ReviewObservationV1] = []
    for key, product_id in sorted(included.items()):
        assert product_id is not None
        related = tuple(
            offer
            for offer in run.offers
            if offer.jan_gtin == key.removeprefix("JAN:")
        )
        height, width, depth, weight, capacity, access, support = specifications[key]
        fit_candidates.append(
            FitCandidateV1(
                product_id=product_id,
                height_cm=Decimal(height),
                width_cm=Decimal(width),
                depth_cm=Decimal(depth),
                body_weight_kg=Decimal(weight),
                base_capacity_l=Decimal(capacity),
                access_utility=Decimal(access),
                support_utility=Decimal(support),
                offers=tuple(
                    OfferPriceV1(
                        source_id=offer.source_id,
                        displayed_price_jpy=offer.displayed_price_jpy or 1,
                        observed_at=offer.observed_at,
                        is_new=True,
                        is_domestic_regular=True,
                    )
                    for offer in related
                ),
            )
        )
        review_observations.extend(
            ReviewObservationV1(
                product_id=product_id,
                source_id=offer.source_id,
                rating_average=offer.review_average or Decimal("0"),
                rating_count=offer.review_count or 0,
                identity_match_confirmed=True,
                anomaly_factor=Decimal("1"),
                verified_purchase=VerificationStateV1.UNAVAILABLE,
                acquired_at=offer.observed_at,
            )
            for offer in related
        )
    fit_scores = calculate_fit_scores(tuple(fit_candidates), now=FIXED_NOW)
    reviews = calculate_review_aggregates(
        tuple(review_observations),
        artifact_id="review-aggregate:recorded-v1",
        acquired_at=FIXED_NOW,
    )
    evidence_refs = (
        artifact_ref(plan),
        artifact_ref(policy),
        artifact_ref(monitoring),
        artifact_ref(run),
        *(artifact_ref(item) for item in decisions),
        artifact_ref(reviews),
    )
    article = build_article_snapshot(
        artifact_id="article-evidence:pilot-v1",
        evidence_refs=evidence_refs,
        recommendation_refs=(),
        candidate_count=len(decisions),
        included_count=len(included),
        price_as_of=FIXED_NOW,
        unknown_items=(
            "Live provider validation not executed",
            "No approved review-body source pair",
            "Article-bound recommendation v2 envelope not generated",
        ),
        created_at=FIXED_NOW,
    )
    packet = build_review_packet(
        artifact_id="review-packet:pilot-v1",
        input_refs=(*evidence_refs, artifact_ref(article)),
        blocker_codes=(
            "LIVE_NOT_EXECUTED",
            "RECOMMENDATION_RESULT_MISSING",
        ),
        warning_codes=("REVIEW_THEME_SOURCES_UNAVAILABLE",),
        summary={
            "article_id": plan.article_id,
            "candidate_count": len(decisions),
            "included_count": len(included),
            "publication_authorized": False,
        },
        created_at=FIXED_NOW,
    )
    return (
        plan,
        policy,
        monitoring,
        pages,
        run,
        decisions,
        fit_scores,
        reviews,
        article,
        packet,
    )


def _schemas() -> bytes:
    model_types = (
        ResearchPlanV1,
        SourcePolicyV1,
        DiscoveryRunV1,
        DiscoveryCheckpointV1,
        CandidateDecisionV1,
        SafetyObservationV1,
        ReviewAggregateSetV1,
        ReviewThemeSetV1,
        SocialSignalSetV1,
        TrustedRecommendationResultV1,
        ArticleEvidenceSnapshotV1,
        ReviewPacketV1,
        ReviewDecisionV1,
        ProviderPageV1,
        FitScoreV1,
        ProductReviewSignalV1,
        EvidenceDimensionScoresV1,
        MonitorDiffV1,
        MonitoringPolicyV1,
    )
    return _json_bytes(
        {
            "schema_version": 1,
            "profile": "TRUST_SELECTION_STRICT_ARTIFACT_SCHEMAS_V1",
            "schemas": {
                model_type.__name__: model_type.model_json_schema()
                for model_type in model_types
            },
        }
    )


def _expected() -> tuple[tuple[Path, bytes], ...]:
    (
        plan,
        policy,
        monitoring,
        pages,
        run,
        decisions,
        fit_scores,
        reviews,
        article,
        packet,
    ) = _build_models()
    artifacts: list[tuple[Path, bytes]] = [
        (SCHEMA_CATALOG_PATH, _schemas()),
        (RESEARCH_PLAN_PATH, _artifact_bytes(plan)),
        (SOURCE_POLICY_PATH, _artifact_bytes(policy)),
        (
            RECORDED_PAGES_PATH,
            _json_bytes(
                {
                    "schema_version": 1,
                    "pages": [item.model_dump(mode="json") for item in pages],
                }
            ),
        ),
        (DISCOVERY_RUN_PATH, _artifact_bytes(run)),
        (
            CANDIDATE_LEDGER_PATH,
            _json_bytes(
                {
                    "schema_version": 1,
                    "article_id": plan.article_id,
                    "decisions": [
                        item.model_dump(mode="json") for item in decisions
                    ],
                }
            ),
        ),
        (
            FIT_SCORES_PATH,
            _json_bytes(
                {
                    "schema_version": 1,
                    "article_id": plan.article_id,
                    "scores": [item.model_dump(mode="json") for item in fit_scores],
                }
            ),
        ),
        (REVIEW_AGGREGATES_PATH, _artifact_bytes(reviews)),
        (ARTICLE_SNAPSHOT_PATH, _artifact_bytes(article)),
        (REVIEW_PACKET_PATH, _artifact_bytes(packet)),
        (
            MONITORING_POLICY_PATH,
            _artifact_bytes(monitoring),
        ),
    ]
    manifest = {
        "schema_version": 1,
        "story_id": "ST-1704",
        "slice_id": "RELIABILITY_PRODUCT_SELECTION_V1",
        "article_id": plan.article_id,
        "local_status": "LOCAL_IMPLEMENTATION_COMPLETE_RECORDED_FIXTURES",
        "owner_generator": (
            "repo://scripts/build_st1704_reliability_product_selection_v1.py"
        ),
        "source_artifacts": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len((REPOSITORY_ROOT / path).read_bytes()),
                "sha256": hashlib.sha256(
                    (REPOSITORY_ROOT / path).read_bytes()
                ).hexdigest(),
            }
            for path in SOURCE_PATHS
        ],
        "generated_artifacts": [
            {
                "uri": f"repo://{path.as_posix()}",
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
            for path, payload in artifacts
        ],
        "authority": {
            "live_validation": "NOT_EXECUTED",
            "publication_authorized": False,
            "activation_authorized": False,
            "wordpress_write_count": 0,
        },
    }
    artifacts.append((RUNTIME_MANIFEST_PATH, _json_bytes(manifest)))
    return tuple(artifacts)


def _write(relative: Path, payload: bytes) -> None:
    target = REPOSITORY_ROOT / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, target)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def build(*, check: bool) -> None:
    for relative, expected in _expected():
        target = REPOSITORY_ROOT / relative
        if check:
            if not target.is_file() or target.read_bytes() != expected:
                raise SystemExit(f"RELIABILITY_GENERATOR_DRIFT {relative}")
        else:
            _write(relative, expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    build(check=arguments.check)
    print(
        "RAOS_RELIABILITY_PRODUCT_SELECTION_V1 "
        f"mode={'CHECK' if arguments.check else 'GENERATE'} status=PASS"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
