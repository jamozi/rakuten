"""Application services for the reliability-first research workflow V1."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import re
from typing import Final, Literal
from uuid import NAMESPACE_URL, uuid5

from raos.domain.catalog.aggregates import ReviewAggregateObservation
from raos.domain.catalog.ids import (
    OfferId,
    ReviewAggregateObservationId,
)
from raos.domain.evidence.ids import SourceSnapshotId
from raos.domain.reliability.contracts_v1 import (
    AcquisitionMethodV1,
    ArticleEvidenceSnapshotV1,
    ArtifactRefV1,
    CandidateDecisionCodeV1,
    CandidateDecisionV1,
    DiscoveryCheckpointV1,
    DiscoveryOfferV1,
    DiscoveryPageReceiptV1,
    DiscoveryRunV1,
    IdentityConfidenceV1,
    MonitorDiffV1,
    ResearchPlanV1,
    ReviewDecisionActionV1,
    ReviewDecisionV1,
    ReviewAggregateSetV1,
    ReviewPacketV1,
    SourceDecisionV1,
    SourcePolicyV1,
    artifact_ref,
)
from raos.domain.shared.persistence import (
    AggregateVersion,
    AwareUtcDateTime,
    PersistedVersion,
)
from raos.ports.reliability.research_v1 import ProductSearchPortV1
from raos.ports.catalog.repositories import OfferRepository


INITIAL_PRODUCT_SOURCES: Final = ("RAKUTEN_ICHIBA", "YAHOO_SHOPPING")
_ACCESSORY_TOKENS: Final = (
    "カバー",
    "ベルト",
    "交換用",
    "キャスターのみ",
    "ネームタグ",
    "収納袋",
    "保護ケース",
)
_BUNDLE_TOKENS: Final = ("セット販売", "2個セット", "福袋")
_USED_TOKENS: Final = ("中古", "展示品", "used")
_PARALLEL_TOKENS: Final = ("並行輸入", "海外仕様")
_IDENTIFIER_TOKEN = re.compile(r"[A-Za-z]{1,12}[-_ ]?[A-Za-z0-9]{2,24}")


def _utc(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("AWARE_UTC_REQUIRED")
    return value.astimezone(timezone.utc)


def validate_sources(
    policy: SourcePolicyV1,
    *,
    source_ids: tuple[str, ...] = INITIAL_PRODUCT_SOURCES,
    live: bool,
    validated_at: datetime | None = None,
) -> None:
    """Fail closed before any source port or credential access."""

    for source_id in source_ids:
        rule = policy.rule_for(source_id)
        if (
            rule.decision is not SourceDecisionV1.ALLOW_AGGREGATE_ONLY
            or rule.acquisition_method is not AcquisitionMethodV1.JSON_API
        ):
            raise ValueError("SOURCE_POLICY_BLOCKED")
        if live and (rule.terms_checked_by is None or rule.terms_checked_at is None):
            raise ValueError("SOURCE_TERMS_RECORD_REQUIRED")
        if live:
            current = _utc(validated_at or datetime.now(timezone.utc))
            assert rule.terms_checked_at is not None
            age = current - _utc(rule.terms_checked_at)
            if age < timedelta(0) or age > timedelta(
                days=policy.terms_attestation_days
            ):
                raise ValueError("SOURCE_TERMS_RECORD_EXPIRED")
        if live and rule.credential_ref is None:
            raise ValueError("SOURCE_CREDENTIAL_REF_REQUIRED")


@dataclass(frozen=True, slots=True)
class ReviewObservationPersistenceBindingV1:
    product_id: str
    source_id: str
    offer_id: OfferId
    source_snapshot_id: SourceSnapshotId
    expected_offer_version: AggregateVersion

    def __post_init__(self) -> None:
        if (
            not self.product_id
            or not self.source_id
            or type(self.offer_id) is not OfferId
            or type(self.source_snapshot_id) is not SourceSnapshotId
            or type(self.expected_offer_version) is not AggregateVersion
        ):
            raise ValueError("INVALID_REVIEW_PERSISTENCE_BINDING")


class PersistReviewObservationsServiceV1:
    """Append normalized provider aggregates through the existing Offer port."""

    __slots__ = ("_offers",)

    def __init__(self, offers: object) -> None:
        if not isinstance(offers, OfferRepository):
            raise TypeError("INVALID_OFFER_REPOSITORY")
        self._offers = offers

    def persist(
        self,
        aggregate: ReviewAggregateSetV1,
        *,
        bindings: tuple[ReviewObservationPersistenceBindingV1, ...],
        ingested_at: datetime,
    ) -> tuple[PersistedVersion, ...]:
        mapping = {(item.product_id, item.source_id): item for item in bindings}
        if len(mapping) != len(bindings) or set(mapping) != {
            (item.product_id, item.source_id) for item in aggregate.observations
        }:
            raise ValueError("REVIEW_PERSISTENCE_BINDING_MISMATCH")
        timestamp = AwareUtcDateTime(_utc(ingested_at))
        results: list[PersistedVersion] = []
        for observation in aggregate.observations:
            binding = mapping[(observation.product_id, observation.source_id)]
            identifier = ReviewAggregateObservationId(
                uuid5(
                    NAMESPACE_URL,
                    "raos:review-observation:"
                    f"{binding.offer_id.value}:{observation.source_id}:"
                    f"{observation.acquired_at.isoformat()}",
                )
            )
            persisted = ReviewAggregateObservation(
                id=identifier,
                offer_id=binding.offer_id,
                review_count=observation.rating_count,
                review_average=observation.rating_average,
                observed_at=AwareUtcDateTime(_utc(observation.acquired_at)),
                ingested_at=timestamp,
                source_snapshot_id=binding.source_snapshot_id,
                created_at=timestamp,
            )
            results.append(
                self._offers.append_observations(
                    binding.offer_id,
                    (persisted,),
                    binding.expected_offer_version,
                )
            )
        return tuple(results)


class DiscoveryServiceV1:
    """Round-robin provider/query discovery with deterministic bounded stops."""

    __slots__ = ("_clock", "_port")

    def __init__(
        self,
        *,
        port: object,
        clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(port, ProductSearchPortV1) or not callable(clock):
            raise TypeError("INVALID_DISCOVERY_SERVICE")
        self._port = port
        self._clock = clock

    def discover(
        self,
        *,
        plan: ResearchPlanV1,
        policy: SourcePolicyV1,
        mode: Literal["RECORDED", "LIVE"],
        artifact_id: str,
        resume: DiscoveryCheckpointV1 | None = None,
        checkpoint_sink: Callable[[DiscoveryCheckpointV1], None] | None = None,
    ) -> DiscoveryRunV1:
        if mode not in {"RECORDED", "LIVE"}:
            raise ValueError("INVALID_DISCOVERY_MODE")
        validate_sources(
            policy,
            live=mode == "LIVE",
            validated_at=self._clock(),
        )
        expected_pages = {
            (source_id, query_index): 1
            for source_id in INITIAL_PRODUCT_SOURCES
            for query_index, _query in enumerate(plan.queries)
        }
        if checkpoint_sink is not None and not callable(checkpoint_sink):
            raise TypeError("INVALID_CHECKPOINT_SINK")
        if resume is None:
            started_at = _utc(self._clock())
            pages = dict(expected_pages)
            ended: set[tuple[str, int]] = set()
            unique: dict[str, dict[str, DiscoveryOfferV1]] = {
                source_id: {} for source_id in INITIAL_PRODUCT_SOURCES
            }
            receipts: list[DiscoveryPageReceiptV1] = []
            stop_reasons: dict[
                str, Literal["END_OF_RESULTS", "OFFER_LIMIT"]
            ] = {}
        else:
            if resume.mode != mode or resume.queries != plan.queries:
                raise ValueError("DISCOVERY_CHECKPOINT_BINDING_MISMATCH")
            expected_keys = {
                f"{source_id}|{query_index}" for source_id, query_index in expected_pages
            }
            if set(resume.next_pages) != expected_keys:
                raise ValueError("DISCOVERY_CHECKPOINT_BINDING_MISMATCH")
            pages = {
                (source_id, query_index): resume.next_pages[
                    f"{source_id}|{query_index}"
                ]
                for source_id, query_index in expected_pages
            }
            ended = set()
            for raw_key in resume.ended_searches:
                try:
                    source_id, query_text = raw_key.split("|", 1)
                    parsed_key = (source_id, int(query_text))
                except Exception:
                    raise ValueError("DISCOVERY_CHECKPOINT_BINDING_MISMATCH") from None
                if parsed_key not in expected_pages:
                    raise ValueError("DISCOVERY_CHECKPOINT_BINDING_MISMATCH")
                ended.add(parsed_key)
            unique = {source_id: {} for source_id in INITIAL_PRODUCT_SOURCES}
            for offer in resume.offers:
                if offer.source_id not in unique:
                    raise ValueError("DISCOVERY_CHECKPOINT_BINDING_MISMATCH")
                unique[offer.source_id][offer.provider_item_id] = offer
            receipts = list(resume.receipts)
            stop_reasons = dict(resume.source_stop_reasons)
            started_at = _utc(resume.started_at)
        checkpoint_sequence = 0

        def emit_checkpoint() -> None:
            nonlocal checkpoint_sequence
            if checkpoint_sink is None:
                return
            checkpoint_sequence += 1
            checkpoint_sink(
                DiscoveryCheckpointV1(
                    artifact_id=(
                        f"{artifact_id}:checkpoint-{checkpoint_sequence:06d}"
                    ),
                    mode=mode,
                    queries=plan.queries,
                    receipts=tuple(receipts),
                    offers=tuple(
                        unique[source_id][item_id]
                        for source_id in INITIAL_PRODUCT_SOURCES
                        for item_id in sorted(unique[source_id])
                    ),
                    next_pages={
                        f"{source_id}|{query_index}": next_page
                        for (source_id, query_index), next_page in pages.items()
                    },
                    ended_searches=tuple(
                        f"{source_id}|{query_index}"
                        for source_id, query_index in sorted(ended)
                    ),
                    source_stop_reasons=stop_reasons,
                    started_at=started_at,
                    updated_at=_utc(self._clock()),
                )
            )
        while len(ended) < len(pages):
            progressed = False
            for source_id in INITIAL_PRODUCT_SOURCES:
                if source_id in stop_reasons:
                    continue
                for query_index, query in enumerate(plan.queries):
                    key = (source_id, query_index)
                    if key in ended:
                        continue
                    if len(unique[source_id]) >= plan.provider_offer_limit:
                        stop_reasons[source_id] = "OFFER_LIMIT"
                        ended.update(
                            item for item in pages if item[0] == source_id
                        )
                        emit_checkpoint()
                        break
                    page_number = pages[key]
                    page = None
                    for attempt in range(3):
                        try:
                            page = self._port.fetch_page(
                                source_id=source_id,
                                query_index=query_index,
                                query=query,
                                page=page_number,
                            )
                            break
                        except Exception:
                            if attempt == 2:
                                raise ValueError("PROVIDER_PAGE_RETRY_EXHAUSTED") from None
                    assert page is not None
                    if (
                        page.source_id != source_id
                        or page.query_index != query_index
                        or page.page != page_number
                    ):
                        raise ValueError("PROVIDER_PAGE_BINDING_MISMATCH")
                    receipts.append(
                        DiscoveryPageReceiptV1(
                            source_id=source_id,
                            query_index=query_index,
                            page=page_number,
                            request_fingerprint=page.request_fingerprint,
                            response_sha256=page.response_sha256,
                            hit_count=len(page.offers),
                        )
                    )
                    for offer in page.offers:
                        unique[source_id].setdefault(offer.provider_item_id, offer)
                        if len(unique[source_id]) >= plan.provider_offer_limit:
                            break
                    pages[key] += 1
                    progressed = True
                    if page.is_last_page:
                        ended.add(key)
                    if len(unique[source_id]) >= plan.provider_offer_limit:
                        stop_reasons[source_id] = "OFFER_LIMIT"
                        ended.update(
                            item for item in pages if item[0] == source_id
                        )
                        emit_checkpoint()
                        break
                    emit_checkpoint()
                if (
                    source_id not in stop_reasons
                    and all(
                        (source_id, query_index) in ended
                        for query_index in range(len(plan.queries))
                    )
                ):
                    stop_reasons[source_id] = "END_OF_RESULTS"
                    emit_checkpoint()
            if not progressed and len(ended) < len(pages):
                raise ValueError("DISCOVERY_DID_NOT_PROGRESS")
        offers = tuple(
            unique[source_id][item_id]
            for source_id in INITIAL_PRODUCT_SOURCES
            for item_id in sorted(unique[source_id])
        )
        return DiscoveryRunV1(
            artifact_id=artifact_id,
            mode=mode,
            queries=plan.queries,
            receipts=tuple(receipts),
            offers=offers,
            source_stop_reasons=stop_reasons,
            unique_offer_count_by_source={
                source_id: len(items) for source_id, items in unique.items()
            },
            started_at=started_at,
            completed_at=_utc(self._clock()),
        )


def _first_reason(title: str) -> CandidateDecisionCodeV1 | None:
    normalized = title.casefold()
    for tokens, code in (
        (_USED_TOKENS, CandidateDecisionCodeV1.USED),
        (_PARALLEL_TOKENS, CandidateDecisionCodeV1.PARALLEL_IMPORT),
        (_ACCESSORY_TOKENS, CandidateDecisionCodeV1.ACCESSORY),
        (_BUNDLE_TOKENS, CandidateDecisionCodeV1.BUNDLE),
    ):
        if any(token.casefold() in normalized for token in tokens):
            return code
    return None


def _identity_key(offer: DiscoveryOfferV1) -> tuple[str, IdentityConfidenceV1]:
    if offer.jan_gtin is not None:
        return f"JAN:{offer.jan_gtin}", IdentityConfidenceV1.CONFIRMED
    if offer.brand and offer.manufacturer_part_number and offer.variant_label:
        return (
            "MPN:"
            f"{offer.brand.casefold()}:"
            f"{offer.manufacturer_part_number.casefold()}:"
            f"{offer.variant_label.casefold()}",
            IdentityConfidenceV1.CONFIRMED,
        )
    inferred = _IDENTIFIER_TOKEN.search(offer.title)
    if offer.brand and inferred is not None:
        return (
            f"INFERRED:{offer.brand.casefold()}:{inferred.group(0).casefold()}",
            IdentityConfidenceV1.PARTIAL,
        )
    return (
        "UNRESOLVED:"
        + hashlib.sha256(offer.title.encode("utf-8")).hexdigest()[:24],
        IdentityConfidenceV1.UNRESOLVED,
    )


def resolve_identities(
    run: DiscoveryRunV1,
    *,
    decided_at: datetime,
    official_mpn_evidence: Mapping[str, ArtifactRefV1] | None = None,
) -> tuple[CandidateDecisionV1, ...]:
    """Build an auditable, fail-closed identity ledger without merging variants."""

    official_by_key = dict(official_mpn_evidence or {})
    if any(
        not key.startswith("MPN:")
        or reference.artifact_type != "OfficialPageEvidenceV1"
        for key, reference in official_by_key.items()
    ):
        raise ValueError("INVALID_OFFICIAL_MPN_EVIDENCE")

    grouped: dict[str, list[DiscoveryOfferV1]] = defaultdict(list)
    confidence_by_key: dict[str, IdentityConfidenceV1] = {}
    exclusion_by_key: dict[str, CandidateDecisionCodeV1] = {}
    for offer in run.offers:
        key, confidence = _identity_key(offer)
        grouped[key].append(offer)
        confidence_by_key[key] = confidence
        exclusion = _first_reason(offer.title)
        if exclusion is not None:
            exclusion_by_key[key] = exclusion
    decisions: list[CandidateDecisionV1] = []
    for key in sorted(grouped):
        offers = grouped[key]
        confidence = confidence_by_key[key]
        if key.startswith("MPN:") and (
            len({item.source_id for item in offers}) < 2
            or key not in official_by_key
        ):
            confidence = IdentityConfidenceV1.PARTIAL
        variants = {
            item.variant_label for item in offers if item.variant_label is not None
        }
        decision = CandidateDecisionCodeV1.INCLUDED
        reasons: list[CandidateDecisionCodeV1] = []
        if key in exclusion_by_key:
            decision = exclusion_by_key[key]
            reasons.append(decision)
        elif confidence is not IdentityConfidenceV1.CONFIRMED:
            decision = CandidateDecisionCodeV1.IDENTITY_UNRESOLVED
            reasons.append(decision)
        elif len(variants) > 1:
            decision = CandidateDecisionCodeV1.VARIANT_AMBIGUOUS
            reasons.append(decision)
        else:
            reasons.append(CandidateDecisionCodeV1.INCLUDED)
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        product_uuid = None
        if decision is CandidateDecisionCodeV1.INCLUDED:
            product_uuid = str(uuid5(NAMESPACE_URL, f"raos:{key}"))
        decisions.append(
            CandidateDecisionV1(
                artifact_id=f"candidate:{digest[:24]}",
                product_id=product_uuid,
                canonical_product_key=key,
                source_offer_keys=tuple(
                    sorted(
                        f"{item.source_id}:{item.provider_item_id}" for item in offers
                    )
                ),
                identity_evidence_refs=(
                    (official_by_key[key],) if key in official_by_key else ()
                ),
                identity_confidence=confidence,
                decision=decision,
                variant_key=next(iter(variants)) if len(variants) == 1 else None,
                reason_codes=tuple(reasons),
                decided_at=_utc(decided_at),
            )
        )
    return tuple(decisions)


def build_review_packet(
    *,
    artifact_id: str,
    input_refs: tuple[ArtifactRefV1, ...],
    blocker_codes: Iterable[str],
    warning_codes: Iterable[str] = (),
    summary: dict[str, int | str | bool],
    created_at: datetime,
) -> ReviewPacketV1:
    blockers = tuple(sorted(set(blocker_codes)))
    warnings = tuple(sorted(set(warning_codes)))
    if set(blockers) & set(warnings):
        raise ValueError("REVIEW_PACKET_CODE_CLASSIFICATION_CONFLICT")
    forbidden = tuple(
        code
        for code in (
            "ACTIVE_RECALL",
            "HARD_CONSTRAINT_FAILED",
            "IDENTITY_UNRESOLVED",
            "LIVE_NOT_EXECUTED",
            "PRICE_MISSING_OR_STALE",
            "RECOMMENDATION_RESULT_MISSING",
            "SOURCE_POLICY_BLOCKED",
        )
        if code in blockers
    )
    return ReviewPacketV1(
        artifact_id=artifact_id,
        input_refs=input_refs,
        blocker_codes=blockers,
        warning_codes=warnings,
        override_forbidden_codes=forbidden,
        summary=summary,
        created_at=_utc(created_at),
    )


def decide_review_packet(
    packet: ReviewPacketV1,
    *,
    artifact_id: str,
    action: ReviewDecisionActionV1,
    reviewer_ref: str,
    reason: str,
    decided_at: datetime,
) -> ReviewDecisionV1:
    if action is ReviewDecisionActionV1.APPROVE and packet.override_forbidden_codes:
        raise ValueError("NON_OVERRIDABLE_BLOCKER_PRESENT")
    return ReviewDecisionV1(
        artifact_id=artifact_id,
        packet_ref=artifact_ref(packet),
        action=action,
        reviewer_ref=reviewer_ref,
        reason=reason,
        decided_at=_utc(decided_at),
    )


def build_article_snapshot(
    *,
    artifact_id: str,
    evidence_refs: tuple[ArtifactRefV1, ...],
    recommendation_refs: tuple[ArtifactRefV1, ...],
    candidate_count: int,
    included_count: int,
    price_as_of: datetime | None,
    unknown_items: tuple[str, ...],
    created_at: datetime,
) -> ArticleEvidenceSnapshotV1:
    if not 0 <= included_count <= candidate_count:
        raise ValueError("INVALID_ARTICLE_CANDIDATE_COUNTS")
    return ArticleEvidenceSnapshotV1(
        artifact_id=artifact_id,
        evidence_refs=evidence_refs,
        recommendation_refs=recommendation_refs,
        candidate_count=candidate_count,
        included_count=included_count,
        excluded_count=candidate_count - included_count,
        price_as_of=None if price_as_of is None else _utc(price_as_of),
        unknown_items=unknown_items,
        created_at=_utc(created_at),
    )


def monitor_snapshot(
    previous: ArticleEvidenceSnapshotV1,
    current: ArticleEvidenceSnapshotV1,
    *,
    artifact_id: str,
    created_at: datetime,
) -> MonitorDiffV1:
    previous_ref = artifact_ref(previous)
    current_ref = artifact_ref(current)
    previous_types = {
        (item.artifact_type, item.content_sha256) for item in previous.evidence_refs
    }
    previous_recommendations = {
        (item.artifact_type, item.content_sha256)
        for item in previous.recommendation_refs
    }
    current_types = {
        (item.artifact_type, item.content_sha256) for item in current.evidence_refs
    }
    current_recommendations = {
        (item.artifact_type, item.content_sha256)
        for item in current.recommendation_refs
    }
    changed_evidence = previous_types.symmetric_difference(current_types)
    changed_recommendations = previous_recommendations.symmetric_difference(
        current_recommendations
    )
    changed = tuple(
        sorted(
            {item[0] for item in (*changed_evidence, *changed_recommendations)}
        )
    )
    snapshot_changed = previous_ref.content_sha256 != current_ref.content_sha256
    regeneration_stages: tuple[
        Literal["RECOMMENDATION_V2", "TRUSTED_RECOMMENDATION_V3", "ARTICLE_PACKET"],
        ...,
    ]
    if changed_evidence:
        regeneration_stages = (
            "RECOMMENDATION_V2",
            "TRUSTED_RECOMMENDATION_V3",
            "ARTICLE_PACKET",
        )
    elif changed_recommendations:
        changed_recommendation_types = {item[0] for item in changed_recommendations}
        regeneration_stages = (
            ("TRUSTED_RECOMMENDATION_V3", "ARTICLE_PACKET")
            if "RecommendationReportV2" in changed_recommendation_types
            else ("ARTICLE_PACKET",)
        )
    elif snapshot_changed:
        regeneration_stages = ("ARTICLE_PACKET",)
    else:
        regeneration_stages = ()
    return MonitorDiffV1(
        artifact_id=artifact_id,
        previous_snapshot_sha256=previous_ref.content_sha256,
        current_snapshot_sha256=current_ref.content_sha256,
        changed_artifact_types=changed,
        update_required=snapshot_changed,
        required_regeneration_stages=regeneration_stages,
        created_at=_utc(created_at),
    )


__all__ = [
    "DiscoveryServiceV1",
    "INITIAL_PRODUCT_SOURCES",
    "PersistReviewObservationsServiceV1",
    "ReviewObservationPersistenceBindingV1",
    "build_article_snapshot",
    "build_review_packet",
    "decide_review_packet",
    "monitor_snapshot",
    "resolve_identities",
    "validate_sources",
]
