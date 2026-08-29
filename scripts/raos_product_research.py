#!/usr/bin/env python3
"""Local CLI for RAOS reliability-first product research V1."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
from typing import Literal, TypeVar, cast

from pydantic import ValidationError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
PYTHON_ROOT = REPOSITORY_ROOT / "python"
if str(PYTHON_ROOT) not in sys.path:
    sys.path.insert(0, str(PYTHON_ROOT))

from raos.adapters.recorded_recommendation import (  # noqa: E402
    load_recorded_recommendation_fixture,
)
from raos.adapters.reliability_product_research_v1 import (  # noqa: E402
    DisabledReviewThemeAdapterV1,
    DisabledSocialSignalAdapterV1,
    LiveProductSearchAdapterV1,
    LocalResearchArtifactStoreV1,
    OfficialPageCaptureAdapterV1,
    RecordedProductSearchAdapterV1,
    ResearchAdapterFailureV1,
    SystemBoundedHtmlTransportV1,
    SystemBoundedJsonTransportV1,
)
from raos.application.editorial.reliability_research_v1 import (  # noqa: E402
    DiscoveryServiceV1,
    build_review_packet,
    decide_review_packet,
    monitor_snapshot,
    resolve_identities,
    validate_sources,
)
from raos.domain.editorial.recommendation_v2 import (  # noqa: E402
    evaluate_recommendations_v2,
)
from raos.domain.reliability.contracts_v1 import (  # noqa: E402
    ArticleEvidenceSnapshotV1,
    ArtifactRefV1,
    CandidateDecisionV1,
    DiscoveryCheckpointV1,
    DiscoveryRunV1,
    EvidenceDimensionScoresV1,
    ProviderPageV1,
    ResearchPlanV1,
    ReviewDecisionActionV1,
    ReviewEvidenceStatusV1,
    ReviewObservationV1,
    ReviewPacketV1,
    ReviewThemeSetV1,
    SafetyObservationV1,
    SafetyStateV1,
    SourcePolicyV1,
    StrictContractV1,
    TrustedCandidateEvidenceV1,
    VerificationStateV1,
)
from raos.domain.reliability.selection_v1 import (  # noqa: E402
    calculate_review_aggregates,
    enhance_recommendation_v2,
)
from raos.ports.reliability.research_v1 import (  # noqa: E402
    ProductSearchPortV1,
)


SLICE_ROOT = REPOSITORY_ROOT / "changes/st-1704/reliability-product-selection-v1"
DEFAULT_PLAN = SLICE_ROOT / "generated/research-plan.v1.json"
DEFAULT_POLICY = SLICE_ROOT / "generated/source-policy.v1.json"
DEFAULT_PAGES = SLICE_ROOT / "generated/recorded-provider-pages.v1.json"
DEFAULT_DISCOVERY = SLICE_ROOT / "generated/discovery-run.v1.json"
DEFAULT_LEDGER = SLICE_ROOT / "generated/candidate-ledger.v1.json"
DEFAULT_REVIEW_PACKET = SLICE_ROOT / "generated/review-packet.v1.json"
DEFAULT_ARTICLE_PACKET = SLICE_ROOT / "generated/article-evidence-snapshot.v1.json"
DEFAULT_V2_FIXTURE = REPOSITORY_ROOT / (
    "changes/st-0804/generated/recommendation-pass.v2.json"
)
MAX_INPUT_BYTES = 16_777_216

TContract = TypeVar("TContract", bound=StrictContractV1)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read(path: Path) -> bytes:
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    try:
        metadata = path.lstat()
        if path.is_symlink() or not path.is_file() or metadata.st_size > MAX_INPUT_BYTES:
            raise ValueError("INPUT_FILE_UNSAFE")
        return path.read_bytes()
    except OSError:
        raise ValueError("INPUT_FILE_UNAVAILABLE") from None


def _load_model(path: Path, model_type: type[TContract]) -> TContract:
    return model_type.model_validate_json(_read(path))


def _load_wrapper(path: Path, key: str) -> list[object]:
    try:
        document = json.loads(_read(path))
    except Exception:
        raise ValueError("INPUT_JSON_INVALID") from None
    if type(document) is not dict or set(document) - {
        "schema_version",
        "article_id",
        key,
    }:
        raise ValueError("INPUT_JSON_SCHEMA_INVALID")
    value = document.get(key)
    if type(value) is not list:
        raise ValueError("INPUT_JSON_SCHEMA_INVALID")
    return cast(list[object], value)


def _model_from_object(value: object, model_type: type[TContract]) -> TContract:
    return model_type.model_validate_json(
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    )


def _store(arguments: argparse.Namespace) -> LocalResearchArtifactStoreV1:
    root = Path(cast(str, arguments.artifact_root))
    if not root.is_absolute():
        raise ValueError("ABSOLUTE_ARTIFACT_ROOT_REQUIRED")
    return LocalResearchArtifactStoreV1(root)


def _receipt(reference: ArtifactRefV1 | None, **extra: object) -> None:
    material = None if reference is None else reference.model_dump(mode="json")
    print(
        json.dumps(
            {"status": "PASS", "artifact": material, **extra},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _validate_plan(arguments: argparse.Namespace) -> None:
    plan = _load_model(Path(arguments.plan), ResearchPlanV1)
    _receipt(None, article_id=plan.article_id, profile_count=len(plan.profiles))


def _validate_sources(arguments: argparse.Namespace) -> None:
    policy = _load_model(Path(arguments.policy), SourcePolicyV1)
    validate_sources(policy, live=arguments.live, validated_at=_now())
    _receipt(None, source_count=len(policy.rules), live_ready=arguments.live)


def _recorded_pages(path: Path) -> tuple[ProviderPageV1, ...]:
    return tuple(
        _model_from_object(item, ProviderPageV1)
        for item in _load_wrapper(path, "pages")
    )


def _discover(arguments: argparse.Namespace) -> None:
    plan = _load_model(Path(arguments.plan), ResearchPlanV1)
    policy = _load_model(Path(arguments.policy), SourcePolicyV1)
    store = _store(arguments)
    mode = cast(Literal["RECORDED", "LIVE"], arguments.mode.upper())
    port: ProductSearchPortV1
    if mode == "RECORDED":
        port = RecordedProductSearchAdapterV1(
            _recorded_pages(Path(arguments.pages))
        )
    else:
        port = LiveProductSearchAdapterV1(
            repository_root=REPOSITORY_ROOT,
            policy=policy,
            transport=SystemBoundedJsonTransportV1(),
            clock=_now,
        )
    resume = (
        None
        if arguments.resume_checkpoint is None
        else _load_model(Path(arguments.resume_checkpoint), DiscoveryCheckpointV1)
    )
    checkpoint_refs: list[ArtifactRefV1] = []

    def checkpoint_sink(checkpoint: DiscoveryCheckpointV1) -> None:
        checkpoint_refs.append(store.put(checkpoint))

    run = DiscoveryServiceV1(port=port, clock=_now).discover(
        plan=plan,
        policy=policy,
        mode=mode,
        artifact_id=f"discovery-run:{mode.casefold()}:{int(_now().timestamp())}",
        resume=resume,
        checkpoint_sink=checkpoint_sink,
    )
    reference = store.put(run)
    _receipt(
        reference,
        offer_count=len(run.offers),
        mode=mode,
        checkpoint_count=len(checkpoint_refs),
    )


def _resolve_identities(arguments: argparse.Namespace) -> None:
    run = _load_model(Path(arguments.discovery), DiscoveryRunV1)
    decisions = resolve_identities(run, decided_at=_now())
    store = _store(arguments)
    references = tuple(store.put(item) for item in decisions)
    print(
        json.dumps(
            {
                "status": "PASS",
                "decision_count": len(decisions),
                "included_count": sum(
                    item.product_id is not None for item in decisions
                ),
                "artifacts": [item.model_dump(mode="json") for item in references],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _check_safety(arguments: argparse.Namespace) -> None:
    store = _store(arguments)
    checked_at = _now()
    if arguments.mode == "recorded":
        observation = SafetyObservationV1(
            artifact_id=f"safety:{arguments.product_id}:recorded",
            product_id=arguments.product_id,
            state=SafetyStateV1.NOT_CHECKED,
            source_refs=(),
            model_match_confirmed=False,
            checked_at=checked_at,
            expires_at=checked_at + timedelta(hours=24),
        )
    else:
        policy = _load_model(Path(arguments.policy), SourcePolicyV1)
        evidence = OfficialPageCaptureAdapterV1(
            policy=policy,
            transport=SystemBoundedHtmlTransportV1(),
            clock=_now,
        ).capture(
            source_id=arguments.source_id,
            exact_url=arguments.exact_url,
            artifact_id=f"official-page:{int(checked_at.timestamp())}",
        )
        evidence_ref = store.put(evidence)
        observation = SafetyObservationV1(
            artifact_id=f"safety:{arguments.product_id}:live",
            product_id=arguments.product_id,
            state=SafetyStateV1.POSSIBLE_MATCH,
            source_refs=(evidence_ref,),
            model_match_confirmed=False,
            checked_at=checked_at,
            expires_at=checked_at + timedelta(hours=24),
        )
    _receipt(store.put(observation), safety_state=observation.state.value)


def _candidate_ledger(path: Path) -> tuple[CandidateDecisionV1, ...]:
    return tuple(
        _model_from_object(item, CandidateDecisionV1)
        for item in _load_wrapper(path, "decisions")
    )


def _collect_reviews(arguments: argparse.Namespace) -> None:
    run = _load_model(Path(arguments.discovery), DiscoveryRunV1)
    decisions = _candidate_ledger(Path(arguments.candidate_ledger))
    product_by_offer = {
        source_offer: decision.product_id
        for decision in decisions
        if decision.product_id is not None
        for source_offer in decision.source_offer_keys
    }
    acquired_at = _now()
    observations: list[ReviewObservationV1] = []
    for offer in run.offers:
        product_id = product_by_offer.get(
            f"{offer.source_id}:{offer.provider_item_id}"
        )
        if (
            product_id is None
            or offer.review_average is None
            or offer.review_count is None
        ):
            continue
        observations.append(
            ReviewObservationV1(
                product_id=product_id,
                source_id=offer.source_id,
                rating_average=offer.review_average,
                rating_count=offer.review_count,
                identity_match_confirmed=True,
                anomaly_factor=Decimal("1"),
                verified_purchase=VerificationStateV1.UNAVAILABLE,
                acquired_at=offer.observed_at,
            )
        )
    result = calculate_review_aggregates(
        tuple(observations),
        artifact_id=f"review-aggregate:{int(acquired_at.timestamp())}",
        acquired_at=acquired_at,
    )
    _receipt(
        _store(arguments).put(result),
        product_count=len(result.signals),
        sufficient_count=sum(
            item.status is ReviewEvidenceStatusV1.SUFFICIENT
            for item in result.signals
        ),
        conflicting_count=sum(
            item.status is ReviewEvidenceStatusV1.CONFLICTING
            for item in result.signals
        ),
    )


def _derive_review_themes(arguments: argparse.Namespace) -> None:
    if arguments.input is None:
        DisabledReviewThemeAdapterV1().derive_themes(
            product_id=arguments.product_id
        )
        raise AssertionError("unreachable")
    themes = _load_model(Path(arguments.input), ReviewThemeSetV1)
    _receipt(
        _store(arguments).put(themes),
        eligible_for_article=themes.eligible_for_article,
    )


def _discover_social(arguments: argparse.Namespace) -> None:
    signal = DisabledSocialSignalAdapterV1(clock=_now).discover()
    _receipt(
        _store(arguments).put(signal),
        rank_adjustment=signal.direct_rank_adjustment,
    )


def _rank(arguments: argparse.Namespace) -> None:
    envelope = load_recorded_recommendation_fixture(
        _read(Path(arguments.v2_fixture))
    )
    report = evaluate_recommendations_v2(envelope)
    report.require_valid()
    evidence = tuple(
        TrustedCandidateEvidenceV1(
            product_id=str(candidate.product_id.value),
            review_signal=None,
            review_adjustment=Decimal("0"),
            review_status=ReviewEvidenceStatusV1.INSUFFICIENT,
            maximum_theme_severity=None,
            safety_state=SafetyStateV1.CLEAR,
            price_current=True,
            support_utility=Decimal("100"),
            evidence_dimensions=EvidenceDimensionScoresV1(
                identity=2,
                official_information=2,
                safety=2,
                independent_evidence=0,
                review_diversity=0,
                freshness_consistency=2,
                safety_required=True,
                unresolved_major_conflict=False,
                source_family_count=2,
            ),
        )
        for candidate in report.candidates
    )
    profile = cast(Literal["LIGHTWEIGHT", "CAPACITY", "ACCESS"], arguments.profile)
    result = enhance_recommendation_v2(
        report,
        evidence,
        artifact_id=f"trusted-recommendation:{profile.casefold()}",
        profile_id=profile,
        calculated_at=_now(),
    )
    _receipt(_store(arguments).put(result), ranking_order=result.ranking_order)


def _build_review_packet(arguments: argparse.Namespace) -> None:
    if arguments.input is not None:
        packet = _load_model(Path(arguments.input), ReviewPacketV1)
    else:
        snapshot = _load_model(Path(arguments.article_packet), ArticleEvidenceSnapshotV1)
        unknown_code_by_message = {
            "Live provider validation not executed": "LIVE_NOT_EXECUTED",
            "No approved review-body source pair": (
                "REVIEW_THEME_SOURCES_UNAVAILABLE"
            ),
            "Article-bound recommendation v2 envelope not generated": (
                "RECOMMENDATION_RESULT_MISSING"
            ),
        }
        unknown_codes = tuple(
            unknown_code_by_message.get(item, item) for item in snapshot.unknown_items
        )
        warning_codes = tuple(
            item
            for item in unknown_codes
            if item == "REVIEW_THEME_SOURCES_UNAVAILABLE"
        )
        blocker_codes = tuple(
            item for item in unknown_codes if item not in set(warning_codes)
        )
        packet = build_review_packet(
            artifact_id=f"review-packet:{int(_now().timestamp())}",
            input_refs=(*snapshot.evidence_refs, *snapshot.recommendation_refs),
            blocker_codes=blocker_codes,
            warning_codes=warning_codes,
            summary={
                "article_id": snapshot.article_id,
                "candidate_count": snapshot.candidate_count,
                "included_count": snapshot.included_count,
                "publication_authorized": False,
            },
            created_at=_now(),
        )
    _receipt(
        _store(arguments).put(packet),
        blocker_count=len(packet.blocker_codes),
        warning_count=len(packet.warning_codes),
    )


def _decide(arguments: argparse.Namespace) -> None:
    packet = _load_model(Path(arguments.packet), ReviewPacketV1)
    action = ReviewDecisionActionV1(arguments.action.upper())
    decision = decide_review_packet(
        packet,
        artifact_id=f"review-decision:{int(_now().timestamp())}",
        action=action,
        reviewer_ref=arguments.reviewer_ref,
        reason=arguments.reason,
        decided_at=_now(),
    )
    _receipt(_store(arguments).put(decision), action=decision.action.value)


def _build_article_packet(arguments: argparse.Namespace) -> None:
    snapshot = _load_model(Path(arguments.input), ArticleEvidenceSnapshotV1)
    _receipt(
        _store(arguments).put(snapshot),
        state=snapshot.state,
        publication_authorized=snapshot.publication_authorized,
    )


def _monitor(arguments: argparse.Namespace) -> None:
    previous = _load_model(Path(arguments.previous), ArticleEvidenceSnapshotV1)
    current = _load_model(Path(arguments.current), ArticleEvidenceSnapshotV1)
    diff = monitor_snapshot(
        previous,
        current,
        artifact_id=f"monitor-diff:{int(_now().timestamp())}",
        created_at=_now(),
    )
    _receipt(
        _store(arguments).put(diff),
        update_required=diff.update_required,
        required_regeneration_stages=diff.required_regeneration_stages,
    )


def _add_store(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifact-root", required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    validate_plan = commands.add_parser("validate-plan")
    validate_plan.add_argument("--plan", default=str(DEFAULT_PLAN))
    validate_plan.set_defaults(handler=_validate_plan)

    validate_policy = commands.add_parser("validate-sources")
    validate_policy.add_argument("--policy", default=str(DEFAULT_POLICY))
    validate_policy.add_argument("--live", action="store_true")
    validate_policy.set_defaults(handler=_validate_sources)

    discover = commands.add_parser("discover")
    discover.add_argument("--plan", default=str(DEFAULT_PLAN))
    discover.add_argument("--policy", default=str(DEFAULT_POLICY))
    discover.add_argument("--pages", default=str(DEFAULT_PAGES))
    discover.add_argument("--resume-checkpoint")
    discover.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    _add_store(discover)
    discover.set_defaults(handler=_discover)

    identities = commands.add_parser("resolve-identities")
    identities.add_argument("--discovery", default=str(DEFAULT_DISCOVERY))
    _add_store(identities)
    identities.set_defaults(handler=_resolve_identities)

    safety = commands.add_parser("check-safety")
    safety.add_argument("--mode", choices=("recorded", "live"), default="recorded")
    safety.add_argument("--policy", default=str(DEFAULT_POLICY))
    safety.add_argument("--source-id", default="NITE_SAFE_LITE")
    safety.add_argument(
        "--exact-url",
        default="https://www.nite.go.jp/jiko/jikojohou/safe-lite.html",
    )
    safety.add_argument("--product-id", required=True)
    _add_store(safety)
    safety.set_defaults(handler=_check_safety)

    reviews = commands.add_parser("collect-reviews")
    reviews.add_argument("--discovery", default=str(DEFAULT_DISCOVERY))
    reviews.add_argument("--candidate-ledger", default=str(DEFAULT_LEDGER))
    _add_store(reviews)
    reviews.set_defaults(handler=_collect_reviews)

    themes = commands.add_parser("derive-review-themes")
    themes.add_argument("--product-id", required=True)
    themes.add_argument("--input")
    _add_store(themes)
    themes.set_defaults(handler=_derive_review_themes)

    social = commands.add_parser("discover-social")
    _add_store(social)
    social.set_defaults(handler=_discover_social)

    rank = commands.add_parser("rank")
    rank.add_argument("--v2-fixture", default=str(DEFAULT_V2_FIXTURE))
    rank.add_argument(
        "--profile",
        choices=("LIGHTWEIGHT", "CAPACITY", "ACCESS"),
        default="LIGHTWEIGHT",
    )
    _add_store(rank)
    rank.set_defaults(handler=_rank)

    packet = commands.add_parser("build-review-packet")
    packet.add_argument("--input")
    packet.add_argument("--article-packet", default=str(DEFAULT_ARTICLE_PACKET))
    _add_store(packet)
    packet.set_defaults(handler=_build_review_packet)

    decide = commands.add_parser("decide")
    decide.add_argument("--packet", default=str(DEFAULT_REVIEW_PACKET))
    decide.add_argument("--action", choices=("approve", "reject"), required=True)
    decide.add_argument("--reviewer-ref", required=True)
    decide.add_argument("--reason", required=True)
    _add_store(decide)
    decide.set_defaults(handler=_decide)

    article = commands.add_parser("build-article-packet")
    article.add_argument("--input", default=str(DEFAULT_ARTICLE_PACKET))
    _add_store(article)
    article.set_defaults(handler=_build_article_packet)

    monitor = commands.add_parser("monitor")
    monitor.add_argument("--previous", required=True)
    monitor.add_argument("--current", required=True)
    _add_store(monitor)
    monitor.set_defaults(handler=_monitor)
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    try:
        handler = cast(object, arguments.handler)
        if not callable(handler):
            raise ValueError("COMMAND_HANDLER_UNAVAILABLE")
        handler(arguments)
        return 0
    except (ResearchAdapterFailureV1, ValidationError, ValueError, TypeError) as exc:
        code = exc.code if isinstance(exc, ResearchAdapterFailureV1) else type(exc).__name__
        print(f"RAOS_PRODUCT_RESEARCH_ERROR code={code}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
