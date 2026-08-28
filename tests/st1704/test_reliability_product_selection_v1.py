"""Behavior tests for the reliability-first product selection V1 slice."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import os
from pathlib import Path
import subprocess
from uuid import UUID

import pytest

from raos.adapters.recorded_recommendation import (
    load_recorded_recommendation_fixture,
)
from raos.adapters.reliability_product_research_v1 import (
    DisabledReviewThemeAdapterV1,
    DisabledSocialSignalAdapterV1,
    LiveProductSearchAdapterV1,
    LocalResearchArtifactStoreV1,
    OfficialPageCaptureAdapterV1,
    RAKUTEN_SOURCE_ID,
    RecordedProductSearchAdapterV1,
    ResearchAdapterFailureV1,
    YAHOO_SOURCE_ID,
    parse_rakuten_page_v1,
    parse_yahoo_page_v1,
)
from raos.application.editorial.reliability_research_v1 import (
    DiscoveryServiceV1,
    PersistReviewObservationsServiceV1,
    ReviewObservationPersistenceBindingV1,
    build_article_snapshot,
    build_review_packet,
    decide_review_packet,
    monitor_snapshot,
    resolve_identities,
    validate_sources,
)
from raos.domain.catalog.aggregates import ReviewAggregateObservation
from raos.domain.catalog.ids import OfferId
from raos.domain.evidence.ids import SourceSnapshotId
from raos.domain.editorial.recommendation_v2 import evaluate_recommendations_v2
from raos.domain.reliability.contracts_v1 import (
    AcquisitionMethodV1,
    ArtifactRefV1,
    CandidateDecisionCodeV1,
    ConfidenceGradeV1,
    DiscoveryCheckpointV1,
    DiscoveryRunV1,
    EvidenceDimensionScoresV1,
    FitCandidateV1,
    OfferPriceV1,
    ProviderPageV1,
    RecommendationStatusV1,
    ResearchPlanV1,
    ReviewDecisionActionV1,
    ReviewEvidenceStatusV1,
    ReviewObservationV1,
    ReviewThemeSetV1,
    ReviewThemeV1,
    SafetyStateV1,
    SourceDecisionV1,
    SourcePolicyV1,
    ThemeSeverityV1,
    TrustedCandidateEvidenceV1,
    VerificationStateV1,
    artifact_ref,
)
from raos.domain.reliability.selection_v1 import (
    PROFILES,
    add_calendar_months,
    calculate_fit_scores,
    calculate_review_aggregates,
    enhance_recommendation_v2,
)
from raos.domain.shared.persistence import AggregateVersion


ROOT = Path(__file__).resolve().parents[2]
SLICE = ROOT / "changes/st-1704/reliability-product-selection-v1"
NOW = datetime(2026, 8, 27, 0, 0, tzinfo=timezone.utc)
PRODUCT_1 = "11111111-1111-4111-8111-111111111111"
PRODUCT_2 = "22222222-2222-4222-8222-222222222222"
PRODUCT_3 = "33333333-3333-4333-8333-333333333333"


def _load_policy() -> SourcePolicyV1:
    return SourcePolicyV1.model_validate_json(
        (SLICE / "generated/source-policy.v1.json").read_bytes()
    )


def _load_plan() -> ResearchPlanV1:
    return ResearchPlanV1.model_validate_json(
        (SLICE / "generated/research-plan.v1.json").read_bytes()
    )


def _offer(
    product_id: str,
    *,
    source: str = RAKUTEN_SOURCE_ID,
    price: int = 30_000,
    observed_at: datetime = NOW,
) -> FitCandidateV1:
    suffix = product_id[0]
    return FitCandidateV1(
        product_id=product_id,
        height_cm=Decimal("55"),
        width_cm=Decimal("35"),
        depth_cm=Decimal("25"),
        body_weight_kg=Decimal(f"3.{suffix}"),
        base_capacity_l=Decimal(f"3{suffix}"),
        access_utility=Decimal("50"),
        support_utility=Decimal("100"),
        offers=(
            OfferPriceV1(
                source_id=source,
                displayed_price_jpy=price,
                observed_at=observed_at,
                is_new=True,
                is_domestic_regular=True,
            ),
        ),
    )


def _review(
    product_id: str,
    source: str,
    rating: str,
    count: int,
    *,
    acquired_at: datetime = NOW,
    verified: VerificationStateV1 = VerificationStateV1.UNAVAILABLE,
) -> ReviewObservationV1:
    return ReviewObservationV1(
        product_id=product_id,
        source_id=source,
        rating_average=Decimal(rating),
        rating_count=count,
        identity_match_confirmed=True,
        anomaly_factor=Decimal("1"),
        verified_purchase=verified,
        acquired_at=acquired_at,
    )


def test_generated_package_is_deterministic_and_unpublished() -> None:
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/build_st1704_reliability_product_selection_v1.py",
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    assert result.returncode == 0, result.stderr
    snapshot = json.loads(
        (SLICE / "generated/article-evidence-snapshot.v1.json").read_text()
    )
    assert snapshot["article_id"] == "raos-reliability-suitcase-pilot-001"
    assert snapshot["state"] == "UNPUBLISHED_REVIEW_PACKET"
    assert snapshot["publication_authorized"] is False
    assert snapshot["route_created"] is False
    assert snapshot["wordpress_written"] is False
    packet = json.loads((SLICE / "generated/review-packet.v1.json").read_text())
    assert packet["blocker_codes"] == [
        "LIVE_NOT_EXECUTED",
        "RECOMMENDATION_RESULT_MISSING",
    ]
    assert packet["warning_codes"] == ["REVIEW_THEME_SOURCES_UNAVAILABLE"]
    assert "LIVE_NOT_EXECUTED" in packet["override_forbidden_codes"]


def test_plan_has_fixed_queries_limit_and_profile_weights() -> None:
    plan = _load_plan()
    assert plan.provider_offer_limit == 3000
    assert plan.queries == (
        "機内持ち込み スーツケース",
        "機内持ち込み キャリーケース",
    )
    assert plan.profiles == PROFILES
    assert all(profile.price_weight == 25 for profile in plan.profiles)


def test_policy_blocks_live_before_credential_or_port_access() -> None:
    policy = _load_policy()
    with pytest.raises(ValueError, match="SOURCE_TERMS_RECORD_REQUIRED"):
        validate_sources(policy, live=True)


def test_live_source_terms_attestation_expires_after_ninety_days() -> None:
    policy = _load_policy()
    checked_rules = tuple(
        rule.model_copy(
            update={"terms_checked_by": "policy:owner", "terms_checked_at": NOW}
        )
        if rule.source_id in {RAKUTEN_SOURCE_ID, YAHOO_SOURCE_ID}
        else rule
        for rule in policy.rules
    )
    checked_policy = policy.model_copy(update={"rules": checked_rules})
    validate_sources(checked_policy, live=True, validated_at=NOW + timedelta(days=90))
    with pytest.raises(ValueError, match="SOURCE_TERMS_RECORD_EXPIRED"):
        validate_sources(
            checked_policy,
            live=True,
            validated_at=NOW + timedelta(days=90, seconds=1),
        )


def test_live_adapter_rejects_expired_terms_before_credential_read(
    tmp_path: Path,
) -> None:
    policy = _load_policy()
    checked_rules = tuple(
        rule.model_copy(
            update={"terms_checked_by": "policy:owner", "terms_checked_at": NOW}
        )
        if rule.source_id == RAKUTEN_SOURCE_ID
        else rule
        for rule in policy.rules
    )

    class Transport:
        called = False

        def get(self, *, host: str, path: str, headers: object) -> bytes:
            del host, path, headers
            self.called = True
            return b"{}"

    transport = Transport()
    adapter = LiveProductSearchAdapterV1(
        repository_root=tmp_path,
        policy=policy.model_copy(update={"rules": checked_rules}),
        transport=transport,
        clock=lambda: NOW + timedelta(days=91),
    )
    with pytest.raises(ResearchAdapterFailureV1) as failure:
        adapter.fetch_page(
            source_id=RAKUTEN_SOURCE_ID,
            query_index=0,
            query="機内持ち込み スーツケース",
            page=1,
        )
    assert failure.value.code == "TERMS_RECORD_EXPIRED"
    assert transport.called is False


def test_unknown_source_rule_is_disabled_and_has_no_credential() -> None:
    policy = _load_policy()
    for source in ("REVIEW_BODY_FUTURE", "SOCIAL_FUTURE"):
        rule = policy.rule_for(source)
        assert rule.decision is SourceDecisionV1.UNKNOWN
        assert rule.acquisition_method is AcquisitionMethodV1.DISABLED
        assert rule.credential_ref is None


def test_review_and_social_body_inputs_have_no_storage_surface() -> None:
    with pytest.raises(ResearchAdapterFailureV1) as failure:
        DisabledReviewThemeAdapterV1().derive_themes(product_id=PRODUCT_1)
    assert failure.value.code == "POLICY_BLOCKED"
    social = DisabledSocialSignalAdapterV1(clock=lambda: NOW).discover()
    assert social.enabled is False
    assert social.direct_rank_adjustment == 0


def test_exact_official_url_is_rejected_before_transport() -> None:
    class Transport:
        called = False

        def get(self, *, host: str, path: str, headers: object) -> bytes:
            del host, path, headers
            self.called = True
            return b"<html></html>"

    transport = Transport()
    adapter = OfficialPageCaptureAdapterV1(
        policy=_load_policy(), transport=transport, clock=lambda: NOW
    )
    with pytest.raises(ResearchAdapterFailureV1):
        adapter.capture(
            source_id="NITE_SAFE_LITE",
            exact_url="https://www.nite.go.jp/not-allowlisted",
            artifact_id="official:test",
        )
    assert transport.called is False


def test_rakuten_parser_drops_affiliate_points_and_query_material() -> None:
    payload = json.dumps(
        {
            "pageCount": 1,
            "Items": [
                {
                    "itemCode": "shop:item",
                    "itemName": "ACE 06316",
                    "itemUrl": "https://item.rakuten.co.jp/shop/item?secret=x",
                    "itemPrice": 31900,
                    "reviewAverage": 4.5,
                    "reviewCount": 30,
                    "jan": "4549531590011",
                    "shopName": "ACE",
                    "affiliateRate": 99,
                    "pointRate": 20,
                }
            ],
        }
    ).encode()
    page = parse_rakuten_page_v1(
        payload,
        query_index=0,
        query="機内持ち込み スーツケース",
        page=1,
        observed_at=NOW,
    )
    offer = page.offers[0]
    assert offer.item_url == "https://item.rakuten.co.jp/shop/item"
    assert "affiliate" not in offer.model_dump_json().casefold()
    assert "point" not in offer.model_dump_json().casefold()


def test_yahoo_parser_keeps_only_product_review_aggregate() -> None:
    payload = json.dumps(
        {
            "totalResultsAvailable": 1,
            "firstResultsPosition": 1,
            "totalResultsReturned": 1,
            "hits": [
                {
                    "code": "ace-06316",
                    "name": "ACE 06316",
                    "url": "https://store.shopping.yahoo.co.jp/ace/06316?x=1",
                    "price": 32000,
                    "janCode": "4549531590011",
                    "brand": {"name": "ACE"},
                    "review": {"rate": 4.4, "count": 40},
                    "seller": {"review": {"rate": 1, "count": 99999}},
                    "affiliateRate": 100,
                }
            ],
        }
    ).encode()
    page = parse_yahoo_page_v1(
        payload,
        query_index=0,
        query="機内持ち込み スーツケース",
        page=1,
        observed_at=NOW,
    )
    offer = page.offers[0]
    assert offer.review_average == Decimal("4.4")
    assert offer.review_count == 40
    assert "seller" not in offer.model_dump_json()
    assert "affiliate" not in offer.model_dump_json().casefold()


def test_discovery_retries_transient_page_failure() -> None:
    source_pages = json.loads(
        (SLICE / "generated/recorded-provider-pages.v1.json").read_text()
    )["pages"]
    pages = tuple(
        ProviderPageV1.model_validate_json(json.dumps(item))
        for item in source_pages
    )
    delegate = RecordedProductSearchAdapterV1(pages)

    class Flaky:
        attempts = 0

        def fetch_page(
            self, *, source_id: str, query_index: int, query: str, page: int
        ) -> ProviderPageV1:
            self.attempts += 1
            if self.attempts == 1:
                raise RuntimeError("transient")
            return delegate.fetch_page(
                source_id=source_id,
                query_index=query_index,
                query=query,
                page=page,
            )

    flaky = Flaky()
    run = DiscoveryServiceV1(port=flaky, clock=lambda: NOW).discover(
        plan=_load_plan(),
        policy=_load_policy(),
        mode="RECORDED",
        artifact_id="discovery:test-retry",
    )
    assert flaky.attempts == 5
    assert len(run.receipts) == 4


def test_discovery_resumes_from_hash_bound_checkpoint() -> None:
    source_pages = json.loads(
        (SLICE / "generated/recorded-provider-pages.v1.json").read_text()
    )["pages"]
    pages = tuple(
        ProviderPageV1.model_validate_json(json.dumps(item))
        for item in source_pages
    )
    checkpoints: list[DiscoveryCheckpointV1] = []
    complete = DiscoveryServiceV1(
        port=RecordedProductSearchAdapterV1(pages), clock=lambda: NOW
    ).discover(
        plan=_load_plan(),
        policy=_load_policy(),
        mode="RECORDED",
        artifact_id="discovery:checkpoint-source",
        checkpoint_sink=checkpoints.append,
    )
    resumed = DiscoveryServiceV1(
        port=RecordedProductSearchAdapterV1(pages), clock=lambda: NOW
    ).discover(
        plan=_load_plan(),
        policy=_load_policy(),
        mode="RECORDED",
        artifact_id="discovery:checkpoint-resumed",
        resume=checkpoints[0],
    )
    assert resumed.offers == complete.offers
    assert resumed.receipts == complete.receipts
    assert resumed.source_stop_reasons == complete.source_stop_reasons


def test_identity_resolution_prefers_jan_and_retains_exclusion_reason() -> None:
    run = DiscoveryRunV1.model_validate_json(
        (SLICE / "generated/discovery-run.v1.json").read_bytes()
    )
    decisions = resolve_identities(run, decided_at=NOW)
    included = tuple(item for item in decisions if item.product_id is not None)
    assert len(included) == 3
    assert all(item.canonical_product_key.startswith("JAN:") for item in included)
    excluded = tuple(item for item in decisions if item.product_id is None)
    assert excluded[0].decision is CandidateDecisionCodeV1.ACCESSORY


def test_mpn_identity_requires_generation_and_two_independent_sources() -> None:
    run = DiscoveryRunV1.model_validate_json(
        (SLICE / "generated/discovery-run.v1.json").read_bytes()
    )
    first = run.offers[0].model_copy(
        update={
            "jan_gtin": None,
            "brand": "Example",
            "manufacturer_part_number": "MPN-1",
            "variant_label": "GEN-2-35L",
        }
    )
    single = run.model_copy(update={"offers": (first,)})
    assert (
        resolve_identities(single, decided_at=NOW)[0].decision
        is CandidateDecisionCodeV1.IDENTITY_UNRESOLVED
    )
    second = first.model_copy(
        update={
            "source_id": YAHOO_SOURCE_ID,
            "provider_item_id": "independent-item",
        }
    )
    corroborated = run.model_copy(update={"offers": (first, second)})
    unresolved = resolve_identities(corroborated, decided_at=NOW)[0]
    assert unresolved.decision is CandidateDecisionCodeV1.IDENTITY_UNRESOLVED
    official_reference = ArtifactRefV1(
        artifact_type="OfficialPageEvidenceV1",
        artifact_id="official-page:identity-test",
        content_sha256="0" * 64,
        byte_size=2,
    )
    confirmed = resolve_identities(
        corroborated,
        decided_at=NOW,
        official_mpn_evidence={
            unresolved.canonical_product_key: official_reference
        },
    )[0]
    assert (
        confirmed.decision
        is CandidateDecisionCodeV1.INCLUDED
    )
    assert confirmed.identity_evidence_refs == (official_reference,)


def test_fit_score_uses_fresh_median_and_three_profiles() -> None:
    first = _offer(PRODUCT_1, price=30_000)
    first = first.model_copy(
        update={
            "offers": (
                first.offers[0],
                first.offers[0].model_copy(update={"displayed_price_jpy": 32_000}),
                first.offers[0].model_copy(update={"displayed_price_jpy": 1}),
            )
        }
    )
    scores = calculate_fit_scores(
        (first, _offer(PRODUCT_2, price=50_000), _offer(PRODUCT_3, price=80_000)),
        now=NOW,
    )
    selected = next(
        item
        for item in scores
        if item.product_id == PRODUCT_1 and item.profile_id == "LIGHTWEIGHT"
    )
    assert selected.median_price_jpy == Decimal("30000")
    assert selected.price_current is True
    assert {item.profile_id for item in scores} == {
        "LIGHTWEIGHT",
        "CAPACITY",
        "ACCESS",
    }


def test_stale_price_is_unknown_and_cannot_be_current() -> None:
    candidate = _offer(
        PRODUCT_1,
        observed_at=NOW - timedelta(hours=24, seconds=1),
    )
    score = calculate_fit_scores((candidate,), now=NOW)[0]
    assert score.price_current is False
    assert "PRICE_MISSING_OR_STALE" in score.reason_codes
    assert score.evidence_coverage == Decimal("0.7500")


def test_carry_on_dimensions_are_hard_gate() -> None:
    candidate = _offer(PRODUCT_1).model_copy(update={"height_cm": Decimal("56")})
    scores = calculate_fit_scores((candidate,), now=NOW)
    assert all(item.fit_score is None for item in scores)
    assert all("HARD_CONSTRAINT_FAILED" in item.reason_codes for item in scores)


def test_two_review_sites_receive_equal_weight_and_verified_is_not_inferred() -> None:
    observations = (
        _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "4.8", 500),
        _review(PRODUCT_1, YAHOO_SOURCE_ID, "4.6", 40),
        _review(PRODUCT_2, RAKUTEN_SOURCE_ID, "3.5", 50),
        _review(PRODUCT_2, YAHOO_SOURCE_ID, "3.7", 50),
    )
    result = calculate_review_aggregates(
        observations, artifact_id="review:test", acquired_at=NOW
    )
    first = next(item for item in result.signals if item.product_id == PRODUCT_1)
    assert first.status is ReviewEvidenceStatusV1.SUFFICIENT
    assert {item.final_weight for item in first.contributions} == {Decimal("0.5000")}
    assert all(
        item.verified_purchase is VerificationStateV1.UNAVAILABLE
        for item in first.contributions
    )


def test_three_review_sites_are_capped_at_forty_percent() -> None:
    observations = (
        _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "4.8", 10_000),
        _review(PRODUCT_1, YAHOO_SOURCE_ID, "4.6", 40),
        _review(PRODUCT_1, "THIRD_SOURCE", "4.4", 40),
        _review(PRODUCT_2, RAKUTEN_SOURCE_ID, "3.5", 50),
        _review(PRODUCT_2, YAHOO_SOURCE_ID, "3.7", 50),
        _review(PRODUCT_2, "THIRD_SOURCE", "3.8", 50),
    )
    result = calculate_review_aggregates(
        observations, artifact_id="review:test-three", acquired_at=NOW
    )
    first = next(item for item in result.signals if item.product_id == PRODUCT_1)
    assert max(item.final_weight for item in first.contributions) <= Decimal("0.4000")
    assert sum(item.final_weight for item in first.contributions) == Decimal("1.0000")


def test_review_minimum_and_staleness_are_fail_closed() -> None:
    observations = (
        _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "4.8", 14),
        _review(PRODUCT_1, YAHOO_SOURCE_ID, "4.6", 15),
        _review(
            PRODUCT_2,
            RAKUTEN_SOURCE_ID,
            "4.8",
            500,
            acquired_at=NOW - timedelta(days=31),
        ),
        _review(PRODUCT_2, YAHOO_SOURCE_ID, "4.6", 500),
    )
    result = calculate_review_aggregates(
        observations, artifact_id="review:test-low", acquired_at=NOW
    )
    assert all(
        item.status is ReviewEvidenceStatusV1.INSUFFICIENT
        and item.review_adjustment == 0
        for item in result.signals
    )


def test_review_adjustment_respects_positive_and_negative_caps() -> None:
    observations = (
        _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "5", 500),
        _review(PRODUCT_1, YAHOO_SOURCE_ID, "5", 500),
        _review(PRODUCT_2, RAKUTEN_SOURCE_ID, "1", 500),
        _review(PRODUCT_2, YAHOO_SOURCE_ID, "1", 500),
    )
    result = calculate_review_aggregates(
        observations, artifact_id="review:test-caps", acquired_at=NOW
    )
    adjustments = {item.product_id: item.review_adjustment for item in result.signals}
    assert adjustments[PRODUCT_1] == Decimal("5.0000")
    assert adjustments[PRODUCT_2] == Decimal("-8.0000")


def test_cross_site_review_conflict_neutralizes_adjustment() -> None:
    observations = (
        _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "5", 100),
        _review(PRODUCT_1, YAHOO_SOURCE_ID, "1", 100),
        _review(PRODUCT_2, RAKUTEN_SOURCE_ID, "1", 100),
        _review(PRODUCT_2, YAHOO_SOURCE_ID, "5", 100),
    )
    result = calculate_review_aggregates(
        observations, artifact_id="review:conflict", acquired_at=NOW
    )
    assert all(
        item.status is ReviewEvidenceStatusV1.CONFLICTING
        and item.review_adjustment == 0
        and item.structural_anomaly_detected is True
        and item.maximum_percentile_spread == Decimal("100.0000")
        for item in result.signals
    )


def test_review_retention_uses_thirteen_calendar_months() -> None:
    acquired = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert add_calendar_months(acquired, 13) == datetime(
        2027, 2, 28, tzinfo=timezone.utc
    )


def test_review_aggregate_appends_through_existing_offer_repository() -> None:
    aggregate = calculate_review_aggregates(
        (
            _review(PRODUCT_1, RAKUTEN_SOURCE_ID, "4.8", 50),
            _review(PRODUCT_1, YAHOO_SOURCE_ID, "4.6", 50),
        ),
        artifact_id="review:persistence-test",
        acquired_at=NOW,
    )

    class Offers:
        def __init__(self) -> None:
            self.appended: list[ReviewAggregateObservation] = []

        def get(self, offer_id: object) -> None:
            del offer_id
            return None

        def add(self, offer: object) -> AggregateVersion:
            del offer
            return AggregateVersion(1)

        def save(self, offer: object, expected_version: object) -> AggregateVersion:
            del offer, expected_version
            return AggregateVersion(1)

        def append_observations(
            self,
            offer_id: OfferId,
            batch: tuple[object, ...],
            expected_version: AggregateVersion,
        ) -> AggregateVersion:
            del offer_id
            assert expected_version == AggregateVersion(1)
            self.appended.extend(
                item for item in batch if isinstance(item, ReviewAggregateObservation)
            )
            return AggregateVersion(2)

        def get_current_projection(self, offer_id: object) -> None:
            del offer_id
            return None

    repository = Offers()
    bindings = tuple(
        ReviewObservationPersistenceBindingV1(
            product_id=item.product_id,
            source_id=item.source_id,
            offer_id=OfferId(
                UUID(
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
                    if item.source_id == RAKUTEN_SOURCE_ID
                    else "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
                )
            ),
            source_snapshot_id=SourceSnapshotId(
                UUID(
                    "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
                    if item.source_id == RAKUTEN_SOURCE_ID
                    else "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
                )
            ),
            expected_offer_version=AggregateVersion(1),
        )
        for item in aggregate.observations
    )
    versions = PersistReviewObservationsServiceV1(repository).persist(
        aggregate,
        bindings=bindings,
        ingested_at=NOW,
    )
    assert versions == (AggregateVersion(2), AggregateVersion(2))
    assert len(repository.appended) == 2
    assert all(
        type(item) is ReviewAggregateObservation for item in repository.appended
    )


def test_review_theme_requires_two_domains_five_observations_and_human_review() -> None:
    base = dict(
        artifact_id="review-theme:test",
        product_id=PRODUCT_1,
        raw_body_persisted=False,
        quotations_persisted=False,
        derived_at=NOW,
        expires_at=add_calendar_months(NOW, 13),
    )
    with pytest.raises(ValueError):
        ReviewThemeSetV1(
            **base,
            themes=(
                ReviewThemeV1(
                    theme_code="WHEEL_FAILURE",
                    severity=ThemeSeverityV1.HIGH,
                    matching_observation_count=5,
                    source_domains=("one.example",),
                    identity_match_confirmed=True,
                    human_validated=True,
                ),
            ),
            eligible_for_article=True,
        )
    valid = ReviewThemeSetV1(
        **base,
        themes=(
            ReviewThemeV1(
                theme_code="WHEEL_FAILURE",
                severity=ThemeSeverityV1.HIGH,
                matching_observation_count=5,
                source_domains=("one.example", "two.example"),
                identity_match_confirmed=True,
                human_validated=True,
            ),
        ),
        eligible_for_article=True,
    )
    assert valid.raw_body_persisted is False
    assert valid.eligible_for_article is True


def _trusted_evidence(
    product_id: str,
    *,
    safety: SafetyStateV1 = SafetyStateV1.CLEAR,
    price_current: bool = True,
    confidence: int = 2,
    review_status: ReviewEvidenceStatusV1 = ReviewEvidenceStatusV1.SUFFICIENT,
    official_information: int = 2,
    support_utility: Decimal = Decimal("100"),
) -> TrustedCandidateEvidenceV1:
    return TrustedCandidateEvidenceV1(
        product_id=product_id,
        review_signal=Decimal("75"),
        review_adjustment=Decimal("2.5"),
        review_status=review_status,
        maximum_theme_severity=None,
        safety_state=safety,
        price_current=price_current,
        support_utility=support_utility,
        evidence_dimensions=EvidenceDimensionScoresV1(
            identity=confidence,
            official_information=official_information,
            safety=2,
            independent_evidence=2,
            review_diversity=2,
            freshness_consistency=2,
            safety_required=True,
            unresolved_major_conflict=False,
            source_family_count=3,
        ),
    )


def test_v3_binds_exact_v2_base_score_and_excludes_active_recall() -> None:
    envelope = load_recorded_recommendation_fixture(
        (ROOT / "changes/st-0804/generated/recommendation-pass.v2.json").read_bytes()
    )
    report = evaluate_recommendations_v2(envelope)
    product_ids = tuple(str(item.product_id.value) for item in report.candidates)
    result = enhance_recommendation_v2(
        report,
        (
            _trusted_evidence(product_ids[0], price_current=False),
            _trusted_evidence(
                product_ids[1], safety=SafetyStateV1.ACTIVE_RECALL
            ),
        ),
        artifact_id="recommendation-v3:test",
        profile_id="LIGHTWEIGHT",
        calculated_at=NOW,
    )
    first = next(item for item in result.candidates if item.product_id == product_ids[0])
    recalled = next(item for item in result.candidates if item.product_id == product_ids[1])
    assert first.fit_score == report.candidates[0].base_score
    assert first.recommendation_status is RecommendationStatusV1.CONDITIONAL
    assert recalled.recommendation_status is RecommendationStatusV1.EXCLUDED
    assert recalled.internal_rank_score is None
    assert product_ids[1] not in result.ranking_order
    assert result.v2_report_sha256 == report.report_sha256.value


def test_low_identity_confidence_caps_grade_at_d() -> None:
    envelope = load_recorded_recommendation_fixture(
        (ROOT / "changes/st-0804/generated/recommendation-pass.v2.json").read_bytes()
    )
    report = evaluate_recommendations_v2(envelope)
    ids = tuple(str(item.product_id.value) for item in report.candidates)
    result = enhance_recommendation_v2(
        report,
        tuple(_trusted_evidence(item, confidence=1) for item in ids),
        artifact_id="recommendation-v3:low-confidence",
        profile_id="CAPACITY",
        calculated_at=NOW,
    )
    assert all(item.confidence_grade is ConfidenceGradeV1.D for item in result.candidates)
    assert all(
        item.recommendation_status is RecommendationStatusV1.INSUFFICIENT_EVIDENCE
        for item in result.candidates
    )


def test_only_complete_a_or_b_evidence_is_recommended() -> None:
    envelope = load_recorded_recommendation_fixture(
        (ROOT / "changes/st-0804/generated/recommendation-pass.v2.json").read_bytes()
    )
    report = evaluate_recommendations_v2(envelope)
    ids = tuple(str(item.product_id.value) for item in report.candidates)
    trusted = enhance_recommendation_v2(
        report,
        tuple(_trusted_evidence(item) for item in ids),
        artifact_id="recommendation-v3:complete",
        profile_id="LIGHTWEIGHT",
        calculated_at=NOW,
    )
    assert all(
        item.confidence_grade in {ConfidenceGradeV1.A, ConfidenceGradeV1.B}
        and item.recommendation_status is RecommendationStatusV1.RECOMMENDED
        for item in trusted.candidates
    )
    conditional = enhance_recommendation_v2(
        report,
        (
            _trusted_evidence(
                ids[0], review_status=ReviewEvidenceStatusV1.INSUFFICIENT
            ),
            _trusted_evidence(ids[1], official_information=1),
        ),
        artifact_id="recommendation-v3:conditional",
        profile_id="LIGHTWEIGHT",
        calculated_at=NOW,
    )
    assert all(
        item.recommendation_status is RecommendationStatusV1.CONDITIONAL
        for item in conditional.candidates
    )


def test_conflicting_review_signal_is_watch_even_with_high_confidence() -> None:
    envelope = load_recorded_recommendation_fixture(
        (ROOT / "changes/st-0804/generated/recommendation-pass.v2.json").read_bytes()
    )
    report = evaluate_recommendations_v2(envelope)
    ids = tuple(str(item.product_id.value) for item in report.candidates)
    result = enhance_recommendation_v2(
        report,
        tuple(
            _trusted_evidence(
                item, review_status=ReviewEvidenceStatusV1.CONFLICTING
            )
            for item in ids
        ),
        artifact_id="recommendation-v3:review-conflict",
        profile_id="ACCESS",
        calculated_at=NOW,
    )
    assert all(
        item.recommendation_status is RecommendationStatusV1.WATCH
        and "REVIEW_SIGNAL_CONFLICTING" in item.reason_codes
        for item in result.candidates
    )


def test_review_packet_cannot_approve_non_overridable_blocker() -> None:
    plan = _load_plan()
    packet = build_review_packet(
        artifact_id="review-packet:test",
        input_refs=(artifact_ref(plan),),
        blocker_codes=("ACTIVE_RECALL",),
        summary={"candidate_count": 1},
        created_at=NOW,
    )
    with pytest.raises(ValueError, match="NON_OVERRIDABLE_BLOCKER_PRESENT"):
        decide_review_packet(
            packet,
            artifact_id="review-decision:test",
            action=ReviewDecisionActionV1.APPROVE,
            reviewer_ref="editor:test",
            reason="cannot override",
            decided_at=NOW,
        )


def test_review_theme_source_absence_is_warning_not_blocker() -> None:
    plan = _load_plan()
    packet = build_review_packet(
        artifact_id="review-packet:theme-warning",
        input_refs=(artifact_ref(plan),),
        blocker_codes=(),
        warning_codes=("REVIEW_THEME_SOURCES_UNAVAILABLE",),
        summary={"candidate_count": 1},
        created_at=NOW,
    )
    assert packet.blocker_codes == ()
    assert packet.warning_codes == ("REVIEW_THEME_SOURCES_UNAVAILABLE",)
    decision = decide_review_packet(
        packet,
        artifact_id="review-decision:theme-warning",
        action=ReviewDecisionActionV1.APPROVE,
        reviewer_ref="editor:test",
        reason="themes omitted and disclosed",
        decided_at=NOW,
    )
    assert decision.publication_authorized is False


def test_article_snapshot_and_monitor_never_authorize_publication() -> None:
    plan = _load_plan()
    first = build_article_snapshot(
        artifact_id="article:test-one",
        evidence_refs=(artifact_ref(plan),),
        recommendation_refs=(),
        candidate_count=1,
        included_count=1,
        price_as_of=NOW,
        unknown_items=(),
        created_at=NOW,
    )
    second = first.model_copy(
        update={"artifact_id": "article:test-two", "unknown_items": ("PRICE_STALE",)}
    )
    diff = monitor_snapshot(
        first,
        second,
        artifact_id="monitor:test",
        created_at=NOW,
    )
    assert first.publication_authorized is False
    assert first.wordpress_written is False
    assert diff.update_required is True
    assert diff.required_regeneration_stages == ("ARTICLE_PACKET",)
    assert diff.automatic_publication_action_count == 0
    changed_plan = plan.model_copy(update={"artifact_id": "research-plan:changed"})
    evidence_changed = second.model_copy(
        update={
            "artifact_id": "article:test-three",
            "evidence_refs": (artifact_ref(changed_plan),),
        }
    )
    evidence_diff = monitor_snapshot(
        second,
        evidence_changed,
        artifact_id="monitor:evidence-change",
        created_at=NOW,
    )
    assert evidence_diff.required_regeneration_stages == (
        "RECOMMENDATION_V2",
        "TRUSTED_RECOMMENDATION_V3",
        "ARTICLE_PACKET",
    )


def test_local_artifact_store_is_private_idempotent_and_tamper_evident(
    tmp_path: Path,
) -> None:
    store = LocalResearchArtifactStoreV1(tmp_path / "artifacts")
    plan = _load_plan()
    reference = store.put(plan)
    assert store.put(plan) == reference
    assert json.loads(store.get(reference))["article_id"] == plan.article_id
    files = tuple((tmp_path / "artifacts").glob("*.json"))
    assert len(files) == 1
    assert files[0].stat().st_mode & 0o777 == 0o600
    files[0].write_bytes(b"{}\n")
    with pytest.raises(ResearchAdapterFailureV1):
        store.get(reference)


def test_cli_validates_plan_and_runs_recorded_discovery(tmp_path: Path) -> None:
    validate = subprocess.run(
        [str(ROOT / ".venv/bin/python"), "scripts/raos_product_research.py", "validate-plan"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    assert validate.returncode == 0, validate.stderr
    discovery = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/raos_product_research.py",
            "discover",
            "--mode",
            "recorded",
            "--artifact-root",
            str(tmp_path / "artifacts"),
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    assert discovery.returncode == 0, discovery.stderr
    receipt = json.loads(discovery.stdout)
    assert receipt["mode"] == "RECORDED"
    assert receipt["offer_count"] == 7


def test_cli_live_validation_fails_closed_without_terms_record() -> None:
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "scripts/raos_product_research.py",
            "validate-sources",
            "--live",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": "python"},
    )
    assert result.returncode == 2
    assert "SOURCE_TERMS_RECORD_REQUIRED" not in result.stderr
    assert "ValueError" in result.stderr
