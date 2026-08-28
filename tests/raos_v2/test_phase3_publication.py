from dataclasses import replace
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any, cast

import pytest
import yaml

from raos.adapters.decision_support_v2.errors import AdapterError, AdapterFailure
from raos.adapters.decision_support_v2.wordpress_phase3_disabled import (
    PHASE3_WORDPRESS_EXPORT_MAX_AGE,
    DisabledPhase3WordPressUpdate,
    wordpress_field_digest,
)
from raos.application.decision_support_v2.phase3_publication import (
    bind_human_review,
    bind_verified_preaction,
    build_phase3_review_candidate,
    derive_phase3_structured_data_expectation,
    seal_reviewed_package,
)
from raos.domain.decision_support_v2.models import (
    ClaimStatus,
    ClaimType,
    FreshnessState,
    RiskClass,
)
from raos.domain.decision_support_v2.phase3_publication import (
    PHASE3_TARGET_ROUTE,
    WORDPRESS_FIELD_NAMES,
    Phase3ClaimBinding,
    Phase3HumanReviewReceipt,
    Phase3PreActionBinding,
    Phase3PreActionStatus,
    Phase3PublicationPackage,
    Phase3PublicationState,
    Phase3ReviewCandidate,
    Phase3StructuredDataExpectation,
    Phase3WordPressExportBinding,
    Phase3WordPressExportRole,
    Phase3WordPressIntent,
    Phase3WordPressUpdateFields,
    Phase3WordPressUpdatePayload,
    phase3_claim_authority_digest,
)
from raos.domain.decision_support_v2.publication import (
    ClaimEvidenceBinding,
    PublicationPackage,
    semantic_digest,
)


ROOT = Path(__file__).resolve().parents[2]
PUBLIC_BODY_SHA256 = "e2cace30f5e14b3f2783b3ef10885f2b7b958ac8a3a4aee45447fd95e9e72121"
SAFE_POST_CONTENT = (
    '<div data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1">'
    '<aside class="raos-v2-decision-support__disclosure" aria-label="広告表示">'
    "広告表示</aside>"
    '<div data-raos-v2-cta-state="BLOCKED">確認待ち</div>'
    '<div data-raos-v2-cta-state="BLOCKED">確認待ち</div>'
    '<div data-raos-v2-cta-state="BLOCKED">確認待ち</div>'
    '<a href="/about-ad-policy/">広告方針</a>'
    "</div>"
)


def _phase2_candidate() -> PublicationPackage:
    path = ROOT / "changes/raos-v2/phase-2/generated/publication-candidate.v2.json"
    return PublicationPackage.from_contract_record(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _claim_bindings(
    phase2: PublicationPackage,
) -> tuple[Phase3ClaimBinding, ...]:
    ledger_path = ROOT / "changes/raos-v2/phase-2/claims/claim-ledger.v2.yaml"
    ledger = yaml.safe_load(ledger_path.read_text(encoding="utf-8"))
    assert isinstance(ledger, dict)
    rows = ledger.get("claims")
    assert isinstance(rows, list)
    authority_by_id = {row["claim_id"]: row for row in rows if isinstance(row, dict)}
    bindings: list[Phase3ClaimBinding] = []
    for evidence in phase2.claim_evidence:
        authority = authority_by_id[evidence.claim_id]
        if evidence.claim_id.endswith("-USAGE-UNKNOWN"):
            claim_type = ClaimType.UNKNOWN
        elif "-CONDITIONAL-FIT" in evidence.claim_id or evidence.claim_id.endswith(
            "-LIGHTEST-IN-SCOPE"
        ):
            claim_type = ClaimType.D_EDITORIAL_JUDGEMENT
        else:
            claim_type = ClaimType.A_OFFICIAL_FACT
        bindings.append(
            Phase3ClaimBinding(
                claim_id=evidence.claim_id,
                claim_type=claim_type,
                risk_class=evidence.risk_class,
                freshness=evidence.freshness,
                authoritative_source_status=ClaimStatus(str(authority["status"])),
                checked_at=datetime.fromisoformat(str(authority["checked_at"])),
                next_review_at=datetime.fromisoformat(str(authority["next_review_at"])),
            )
        )
    return tuple(bindings)


def _bind_phase3_authority(
    phase2: PublicationPackage,
    bindings: tuple[Phase3ClaimBinding, ...],
) -> PublicationPackage:
    return replace(
        phase2,
        input_hashes={
            **phase2.input_hashes,
            "phase3_claim_authority": phase3_claim_authority_digest(bindings),
        },
    )


def _preaction_binding(
    *,
    body_sha256: str = PUBLIC_BODY_SHA256,
    captured_at: datetime | None = None,
) -> Phase3PreActionBinding:
    return Phase3PreActionBinding(
        captured_at=(
            captured_at or _phase2_candidate().created_at + timedelta(minutes=2)
        ),
        post_id=42,
        current_public_body_sha256=body_sha256,
        public_capture_sha256="a" * 64,
        wordpress_export_sha256="b" * 64,
        wordpress_export_bytes=4096,
    )


def _update_payload(*, verified: bool = True) -> Phase3WordPressUpdatePayload:
    historical = Phase3WordPressUpdatePayload(
        fields=Phase3WordPressUpdateFields(
            post_title="機内持ち込みスーツケース比較",
            post_content=SAFE_POST_CONTENT,
            post_excerpt="公式仕様と条件を分けて比較します。",
            meta_description="機内持ち込み条件を公式情報から確認する比較ガイドです。",
        ),
        expected_public_body_sha256=PUBLIC_BODY_SHA256,
    )
    if not verified:
        return historical
    return bind_verified_preaction(
        payload=historical,
        binding=_preaction_binding(),
    )


def _review_candidate(
    *,
    phase2: PublicationPackage | None = None,
    bindings: tuple[Phase3ClaimBinding, ...] | None = None,
    update_payload: Phase3WordPressUpdatePayload | None = None,
) -> Phase3ReviewCandidate:
    actual_phase2 = phase2 or _phase2_candidate()
    return build_phase3_review_candidate(
        phase2_candidate=actual_phase2,
        claim_bindings=bindings or _claim_bindings(actual_phase2),
        update_payload=update_payload or _update_payload(),
    )


def _receipt(candidate: Phase3ReviewCandidate) -> Phase3HumanReviewReceipt:
    return Phase3HumanReviewReceipt(
        reviewer_id="TEST-REAL-REVIEWER",
        reviewed_at=candidate.phase2_candidate.created_at + timedelta(minutes=5),
        review_version="P3-REVIEW-V1",
        correction_count=2,
        accepted=True,
        synthetic=False,
        candidate_digest=candidate.candidate_digest,
        payload_digest=candidate.payload_digest,
        target_route=PHASE3_TARGET_ROUTE,
    )


def _reviewed(
    candidate: Phase3ReviewCandidate | None = None,
) -> Phase3PublicationPackage:
    actual = candidate or _review_candidate()
    return bind_human_review(candidate=actual, receipt=_receipt(actual))


def _sealed(
    candidate: Phase3ReviewCandidate | None = None,
) -> Phase3PublicationPackage:
    return seal_reviewed_package(_reviewed(candidate))


def test_phase3_starts_from_exact_real_phase2_candidate_and_seals() -> None:
    candidate = _review_candidate()
    assert candidate.phase2_candidate.synthetic is False
    assert candidate.is_current()
    assert candidate.seal_blockers() == ()

    reviewed = _reviewed(candidate)
    assert reviewed.state is Phase3PublicationState.HUMAN_REVIEWED
    assert reviewed.package_digest is None

    sealed = reviewed.seal()
    assert sealed.state is Phase3PublicationState.PACKAGE_SEALED
    assert sealed.verify_seal()
    assert sealed.to_contract_record()["capabilities"] == {
        "network": False,
        "wordpress_write": False,
        "publish": False,
    }


def test_structured_data_expectation_is_closed_and_derived_from_wordpress_fields() -> (
    None
):
    payload = _update_payload()
    expected = derive_phase3_structured_data_expectation(fields=payload.fields)
    assert expected == payload.structured_data_expectation
    assert isinstance(expected, Phase3StructuredDataExpectation)
    record = expected.to_contract_record()
    canonical = "https://kurashinoshirube.com/carry-on-suitcase-comparison/"
    assert record["schema"] == "RAOS_V2_PHASE3_STRUCTURED_DATA_EXPECTATION_V1"
    assert record["derivation"] == "EXACT_WORDPRESS_FIELDS_V1"
    assert record["json_ld_script_count"] == 1
    assert record["json_ld_document_count"] == 1
    assert record["emission"] == {
        "owner": "EXTERNAL_WORDPRESS_SEO_CONFIGURATION",
        "local_json_ld_emission": False,
        "external_configuration_status": "UNVERIFIED_EXTERNAL",
    }
    assert record["json_ld_types"] == [
        "Article",
        "BreadcrumbList",
        "Organization",
        "WebSite",
    ]
    documents = record["documents"]
    assert isinstance(documents, list) and len(documents) == 1
    document = documents[0]
    assert isinstance(document, dict)
    assert document == {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "Article",
                "headline": payload.fields.post_title,
                "description": payload.fields.meta_description,
                "mainEntityOfPage": {"@id": canonical},
                "url": canonical,
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": payload.fields.post_title,
                        "item": canonical,
                    }
                ],
            },
            {
                "@type": "Organization",
                "url": "https://kurashinoshirube.com/",
            },
            {"@type": "WebSite", "url": "https://kurashinoshirube.com/"},
        ],
    }
    assert record["json_ld_sha256"] == semantic_digest({"documents": documents})
    assert payload.to_contract_record()["structured_data_expectation"] == record


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-article-property",
        "forbidden-product-node",
        "nested-review-type",
        "changed-description",
        "changed-canonical",
    ],
)
def test_any_json_ld_shape_or_field_mutation_changes_the_sealed_expectation(
    mutation: str,
) -> None:
    expectation = _update_payload().structured_data_expectation
    document = json.loads(
        json.dumps(expectation.json_ld_document(), ensure_ascii=False)
    )
    graph = document["@graph"]
    if mutation == "extra-article-property":
        graph[0]["author"] = {"name": "unreviewed"}
    elif mutation == "forbidden-product-node":
        graph.append({"@type": "Product", "name": "unreviewed"})
    elif mutation == "nested-review-type":
        graph[0]["review"] = {"@type": "Review", "name": "unreviewed"}
    elif mutation == "changed-description":
        graph[0]["description"] = "unreviewed"
    else:
        graph[1]["itemListElement"][-1]["item"] = "https://example.invalid/"
    assert semantic_digest({"documents": [document]}) != expectation.json_ld_sha256


def test_review_and_package_seal_bind_structured_data_expectation_digest() -> None:
    sealed = _sealed()
    expectation_digest = (
        sealed.review_candidate.update_payload.structured_data_expectation_sha256
    )
    candidate_record = sealed.review_candidate.to_contract_record()
    package_record = sealed.to_contract_record()
    assert candidate_record["structured_data_expectation_sha256"] == (
        expectation_digest
    )
    assert package_record["structured_data_expectation_sha256"] == expectation_digest
    assert (
        sealed.review_receipt.payload_digest == sealed.review_candidate.payload_digest
    )

    object.__setattr__(
        sealed.review_candidate.update_payload.fields,
        "meta_description",
        "人間レビュー後の未承認変更",
    )
    assert not sealed.verify_seal()


def test_historical_or_missing_preaction_binding_blocks_seal() -> None:
    payload = _update_payload(verified=False)
    assert payload.preaction_status is Phase3PreActionStatus.HISTORICAL_BASELINE_ONLY
    assert payload.preaction_binding_digest is None
    candidate = _review_candidate(update_payload=payload)
    assert "PREACTION_BINDING_MISSING_OR_HISTORICAL_BASELINE_ONLY" in (
        candidate.seal_blockers()
    )
    with pytest.raises(ValueError, match="blocks Phase 3 seal"):
        _reviewed(candidate).seal()


def test_verified_preaction_rebind_is_reviewed_and_sealable() -> None:
    historical = _update_payload(verified=False)
    binding = _preaction_binding(body_sha256="c" * 64)
    rebound = bind_verified_preaction(payload=historical, binding=binding)
    assert rebound.expected_public_body_sha256 == "c" * 64
    assert rebound.preaction_status is Phase3PreActionStatus.VERIFIED_PREACTION
    assert rebound.preaction_binding_digest == binding.binding_digest
    candidate = _review_candidate(update_payload=rebound)
    sealed = _sealed(candidate)
    assert sealed.verify_seal()
    record = candidate.to_contract_record()
    assert record["preaction_status"] == "VERIFIED_PREACTION"
    assert record["preaction_binding_digest"] == binding.binding_digest


def test_preaction_capture_must_precede_the_bound_human_review() -> None:
    late = _preaction_binding(
        captured_at=_phase2_candidate().created_at + timedelta(minutes=6)
    )
    payload = bind_verified_preaction(
        payload=_update_payload(verified=False), binding=late
    )
    candidate = _review_candidate(update_payload=payload)
    with pytest.raises(ValueError, match="exact candidate"):
        candidate.bind_review(_receipt(candidate))


def test_generated_phase2_candidate_binds_exact_phase3_claim_authority() -> None:
    phase2 = _phase2_candidate()
    assert phase2.input_hashes["phase3_claim_authority"] == (
        phase3_claim_authority_digest(_claim_bindings(phase2))
    )


def test_phase3_rejects_synthetic_or_unreviewed_phase2_input() -> None:
    real = _phase2_candidate()
    with pytest.raises(ValueError, match="unsealed real"):
        _review_candidate(phase2=replace(real, synthetic=True))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"accepted": False}, "accepted non-synthetic"),
        ({"synthetic": True}, "accepted non-synthetic"),
        ({"correction_count": -1}, "non-negative"),
        ({"correction_count": True}, "non-negative"),
        ({"candidate_digest": "f" * 64}, "exact candidate"),
        ({"payload_digest": "f" * 64}, "exact candidate"),
    ],
)
def test_human_review_receipt_is_exact_and_non_synthetic(
    changes: dict[str, object], message: str
) -> None:
    candidate = _review_candidate()
    values = {
        "reviewer_id": "TEST-REAL-REVIEWER",
        "reviewed_at": candidate.phase2_candidate.created_at + timedelta(minutes=5),
        "review_version": "P3-REVIEW-V1",
        "correction_count": 0,
        "accepted": True,
        "synthetic": False,
        "candidate_digest": candidate.candidate_digest,
        "payload_digest": candidate.payload_digest,
        "target_route": PHASE3_TARGET_ROUTE,
    }
    receipt = None
    with pytest.raises(ValueError, match=message):
        receipt = Phase3HumanReviewReceipt(**(values | changes))  # type: ignore[arg-type]
        candidate.bind_review(receipt)
    assert receipt is None or isinstance(receipt, Phase3HumanReviewReceipt)


def test_human_review_receipt_requires_aware_time_after_candidate() -> None:
    candidate = _review_candidate()
    receipt = _receipt(candidate)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(receipt, reviewed_at=receipt.reviewed_at.replace(tzinfo=None))
    with pytest.raises(ValueError, match="exact candidate"):
        candidate.bind_review(
            replace(
                receipt,
                reviewed_at=candidate.phase2_candidate.created_at
                - timedelta(seconds=1),
            )
        )


@pytest.mark.parametrize(
    ("freshness", "resolved", "expected"),
    [
        (FreshnessState.HARD_STALE, True, "OFFICIAL_FACT_NONFRESH"),
        (FreshnessState.UNKNOWN, True, "OFFICIAL_FACT_NONFRESH"),
        (FreshnessState.FRESH, False, "OFFICIAL_FACT_UNRESOLVED"),
    ],
)
def test_stale_or_unresolved_official_fact_blocks_seal(
    freshness: FreshnessState, resolved: bool, expected: str
) -> None:
    phase2 = _phase2_candidate()
    official_id = next(
        binding.claim_id
        for binding in _claim_bindings(phase2)
        if binding.claim_type is ClaimType.A_OFFICIAL_FACT
    )
    evidence = tuple(
        replace(item, freshness=freshness) if item.claim_id == official_id else item
        for item in phase2.claim_evidence
    )
    changed_phase2 = replace(phase2, claim_evidence=evidence)
    bindings = tuple(
        replace(
            item,
            freshness=freshness,
            authoritative_source_status=(
                ClaimStatus.VERIFIED if resolved else ClaimStatus.DRAFT
            ),
        )
        if item.claim_id == official_id
        else item
        for item in _claim_bindings(changed_phase2)
    )
    changed_phase2 = _bind_phase3_authority(changed_phase2, bindings)
    candidate = _review_candidate(phase2=changed_phase2, bindings=bindings)
    assert any(expected in blocker for blocker in candidate.seal_blockers())
    with pytest.raises(ValueError, match="claim evidence blocks"):
        _reviewed(candidate).seal()


@pytest.mark.parametrize(
    "authoritative_source_status",
    [ClaimStatus.DRAFT, ClaimStatus.VERIFIED, ClaimStatus.STALE],
)
def test_unknown_must_be_authoritatively_blocked_to_be_safely_disclosed(
    authoritative_source_status: ClaimStatus,
) -> None:
    phase2 = _phase2_candidate()
    bindings = _claim_bindings(phase2)
    unknown_id = next(
        binding.claim_id
        for binding in bindings
        if binding.claim_type is ClaimType.UNKNOWN
    )
    changed = tuple(
        replace(
            binding,
            authoritative_source_status=authoritative_source_status,
        )
        if binding.claim_id == unknown_id
        else binding
        for binding in bindings
    )
    phase2 = _bind_phase3_authority(phase2, changed)
    candidate = _review_candidate(phase2=phase2, bindings=changed)
    assert any(
        "UNKNOWN_NOT_SAFELY_DISCLOSED" in blocker
        for blocker in candidate.seal_blockers()
    )
    with pytest.raises(ValueError, match="claim evidence blocks"):
        _reviewed(candidate).seal()


@pytest.mark.parametrize(
    ("claim_type", "expected"),
    [
        (ClaimType.A_OFFICIAL_FACT, "OFFICIAL_FACT_AUTHORITY_EXPIRED"),
        (
            ClaimType.D_EDITORIAL_JUDGEMENT,
            "EDITORIAL_JUDGEMENT_AUTHORITY_EXPIRED",
        ),
        (ClaimType.UNKNOWN, "UNKNOWN_DISCLOSURE_AUTHORITY_EXPIRED"),
    ],
)
def test_claim_authority_deadline_is_exclusive_at_human_review(
    claim_type: ClaimType, expected: str
) -> None:
    phase2 = _phase2_candidate()
    bindings = _claim_bindings(phase2)
    target = next(item for item in bindings if item.claim_type is claim_type)
    deadline = phase2.created_at + timedelta(minutes=5)
    changed = tuple(
        replace(item, next_review_at=deadline)
        if item.claim_id == target.claim_id
        else item
        for item in bindings
    )
    phase2 = _bind_phase3_authority(phase2, changed)
    candidate = _review_candidate(phase2=phase2, bindings=changed)

    before_deadline = replace(
        _receipt(candidate), reviewed_at=deadline - timedelta(microseconds=1)
    )
    assert candidate.bind_review(before_deadline).seal().verify_seal()

    at_deadline = replace(_receipt(candidate), reviewed_at=deadline)
    reviewed = candidate.bind_review(at_deadline)
    assert any(
        expected in blocker for blocker in candidate.seal_blockers(reviewed_at=deadline)
    )
    with pytest.raises(ValueError, match="claim evidence blocks"):
        reviewed.seal()


def test_nonfresh_editorial_judgement_blocks_seal() -> None:
    phase2 = _phase2_candidate()
    bindings = _claim_bindings(phase2)
    editorial_id = next(
        item.claim_id
        for item in bindings
        if item.claim_type is ClaimType.D_EDITORIAL_JUDGEMENT
    )
    evidence = tuple(
        replace(item, freshness=FreshnessState.HARD_STALE)
        if item.claim_id == editorial_id
        else item
        for item in phase2.claim_evidence
    )
    changed = tuple(
        replace(item, freshness=FreshnessState.HARD_STALE)
        if item.claim_id == editorial_id
        else item
        for item in bindings
    )
    phase2 = _bind_phase3_authority(replace(phase2, claim_evidence=evidence), changed)
    candidate = _review_candidate(phase2=phase2, bindings=changed)
    assert any(
        "EDITORIAL_JUDGEMENT_NONFRESH" in blocker
        for blocker in candidate.seal_blockers()
    )
    with pytest.raises(ValueError, match="claim evidence blocks"):
        _reviewed(candidate).seal()


def test_semantic_drift_invalidates_review_and_seal() -> None:
    sealed = _sealed()
    assert sealed.verify_seal()
    with pytest.raises(ValueError, match="seal is invalid"):
        replace(sealed, package_digest="f" * 64)
    with pytest.raises(ValueError, match="seal is invalid"):
        replace(
            sealed,
            review_receipt=replace(sealed.review_receipt, correction_count=3),
        )

    mutable_hashes = sealed.review_candidate.phase2_candidate.input_hashes
    assert isinstance(mutable_hashes, dict)
    mutable_hashes["article"] = "f" * 64
    assert not sealed.verify_seal()


def _before_hashes(payload: Phase3WordPressUpdatePayload) -> dict[str, str]:
    result = {field_name: "0" * 64 for field_name in WORDPRESS_FIELD_NAMES}
    result["post_title"] = wordpress_field_digest(
        "post_title", payload.fields.post_title
    )
    result["post_status"] = wordpress_field_digest("post_status", "publish")
    return result


def _export_binding(
    payload: Phase3WordPressUpdatePayload | None = None,
) -> Phase3WordPressExportBinding:
    actual = payload or _update_payload()
    return Phase3WordPressExportBinding(
        post_id=42,
        field_hashes=_before_hashes(actual),
        public_body_sha256=actual.expected_public_body_sha256,
        preaction_binding_sha256=(actual.preaction_binding_digest or "0" * 64),
        export_sha256="1" * 64,
        export_bytes=2048,
        restore_artifact_sha256="2" * 64,
        theme_artifact_sha256="3" * 64,
        seo_state_sha256="4" * 64,
        redirect_map_sha256="5" * 64,
        sitemap_state_sha256="6" * 64,
        captured_at=_phase2_candidate().created_at + timedelta(minutes=10),
    )


def _evaluated_at(export_binding: Phase3WordPressExportBinding) -> datetime:
    return export_binding.captured_at + timedelta(minutes=1)


def test_disabled_wordpress_dry_run_is_exact_hash_only_and_has_no_requests() -> None:
    sealed = _sealed()
    adapter = DisabledPhase3WordPressUpdate()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    preaction = sealed.review_candidate.update_payload.preaction_binding
    assert isinstance(preaction, Phase3PreActionBinding)
    receipt = adapter.dry_run(
        sealed,
        export_binding=export_binding,
        evaluated_at=_evaluated_at(export_binding),
    )
    assert adapter.mode == "DISABLED_DRY_RUN"
    assert adapter.request_count == 0
    assert adapter.external_action_count == 0
    assert receipt["request_count"] == 0
    assert receipt["external_action_count"] == 0
    assert receipt["external_status"] == "NOT_EXECUTED"
    assert receipt["intent"] == ("UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER")
    assert receipt["target"] == {
        "origin": "https://kurashinoshirube.com",
        "route": PHASE3_TARGET_ROUTE,
        "kind": "EXISTING_POST",
        "post_id": 42,
        "expected_match_count": 1,
    }
    assert receipt["export_binding_sha256"] == export_binding.binding_digest
    assert export_binding.to_contract_record()["export_role"] == "PRE_WRITE_EXPORT"
    assert receipt["preconditions"] == {
        "export_role": "PRE_WRITE_EXPORT",
        "expected_current_post_status": "publish",
        "before_post_status_sha256": wordpress_field_digest("post_status", "publish"),
        "expected_public_body_sha256": PUBLIC_BODY_SHA256,
        "observed_public_body_sha256": PUBLIC_BODY_SHA256,
        "export_captured_at": export_binding.captured_at.isoformat(),
        "human_reviewed_at": sealed.review_receipt.reviewed_at.isoformat(),
        "preaction_status": "VERIFIED_PREACTION",
        "preaction_binding_sha256": preaction.binding_digest,
        "observed_preaction_binding_sha256": (export_binding.preaction_binding_sha256),
        "preaction_captured_at": preaction.captured_at.isoformat(),
        "evaluated_at": _evaluated_at(export_binding).isoformat(),
        "max_export_age_seconds": 300,
        "satisfied": True,
    }
    assert receipt["postconditions"] == {
        "required_after_post_status": "publish",
        "after_post_status_sha256": wordpress_field_digest("post_status", "publish"),
        "satisfied": True,
    }
    field_diff = receipt["field_diff"]
    assert isinstance(field_diff, list)
    assert {item["field"] for item in field_diff} == set(WORDPRESS_FIELD_NAMES)
    title = next(item for item in field_diff if item["field"] == "post_title")
    assert title["changed"] is False
    assert all(
        set(item) == {"field", "before_sha256", "after_sha256", "changed"}
        for item in field_diff
    )
    serialized = json.dumps(receipt, ensure_ascii=False)
    assert "機内持ち込み" not in serialized
    assert "credential" not in serialized.casefold()
    assert "endpoint" not in serialized.casefold()
    assert not hasattr(adapter, "publish")
    assert not hasattr(adapter, "request")
    assert receipt == adapter.dry_run(
        sealed,
        export_binding=export_binding,
        evaluated_at=_evaluated_at(export_binding),
    )


def test_disabled_wordpress_rejects_unsealed_candidate() -> None:
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            _reviewed(),
            export_binding=_export_binding(),
            evaluated_at=_phase2_candidate().created_at + timedelta(minutes=11),
        )
    assert error.value.code is AdapterFailure.DISABLED


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("target_route", "/wrong-route/"),
        ("expected_existing_post_count", 2),
        ("intent", "CREATE_NEW"),
        ("expected_current_post_status", "draft"),
        ("required_after_post_status", "draft"),
    ],
)
def test_disabled_wordpress_rejects_wrong_or_ambiguous_target(
    field: str, value: object
) -> None:
    sealed = _sealed()
    object.__setattr__(sealed.review_candidate.update_payload, field, value)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=_export_binding(),
            evaluated_at=_phase2_candidate().created_at + timedelta(minutes=11),
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", "WRONG"),
        ("version", "1.0.0"),
        ("target_route", "/wrong-route/"),
        ("target_kind", "NEW_POST"),
        ("exact_match_count", 2),
        ("post_id", 0),
        ("export_sha256", "not-a-hash"),
        ("export_bytes", 0),
        ("export_role", Phase3WordPressExportRole.POST_ACTION_OWNER_EXPORT),
    ],
)
def test_disabled_wordpress_rejects_mutated_export_binding(
    field: str, value: object
) -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    object.__setattr__(export_binding, field, value)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=_evaluated_at(export_binding),
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize("case", ["missing", "malformed", "draft-status"])
def test_disabled_wordpress_requires_exact_export_field_hashes(case: str) -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    hashes = dict(export_binding.field_hashes)
    if case == "missing":
        hashes.pop("post_excerpt")
    elif case == "malformed":
        hashes["post_excerpt"] = "not-a-hash"
    else:
        hashes["post_status"] = wordpress_field_digest("post_status", "draft")
    object.__setattr__(export_binding, "field_hashes", hashes)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=_evaluated_at(export_binding),
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


@pytest.mark.parametrize("case", ["public-body-drift", "pre-review-export"])
def test_disabled_wordpress_requires_fresh_exact_public_export(case: str) -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    if case == "public-body-drift":
        object.__setattr__(export_binding, "public_body_sha256", "f" * 64)
    else:
        object.__setattr__(
            export_binding,
            "captured_at",
            sealed.review_receipt.reviewed_at - timedelta(microseconds=1),
        )
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=_evaluated_at(export_binding),
        )
    assert error.value.code is AdapterFailure.STALE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", Phase3PreActionStatus.HISTORICAL_BASELINE_ONLY),
        ("provenance", "UNVERIFIED"),
        ("target_route", "/wrong-route/"),
        ("captured_at", datetime.fromisoformat("2026-08-28T00:00:00")),
        ("public_capture_sha256", "not-a-hash"),
        ("current_public_body_sha256", "f" * 64),
        ("wordpress_export_sha256", "e" * 64),
    ],
)
def test_disabled_wordpress_rejects_preaction_provenance_mutation(
    field: str, value: object
) -> None:
    sealed = _sealed()
    preaction = sealed.review_candidate.update_payload.preaction_binding
    assert isinstance(preaction, Phase3PreActionBinding)
    object.__setattr__(preaction, field, value)
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=_evaluated_at(export_binding),
        )
    assert error.value.code in {
        AdapterFailure.INVALID_RESPONSE,
        AdapterFailure.STALE,
    }


def test_fresh_export_must_bind_the_sealed_preaction_digest() -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    object.__setattr__(export_binding, "preaction_binding_sha256", "f" * 64)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=_evaluated_at(export_binding),
        )
    assert error.value.code is AdapterFailure.STALE


@pytest.mark.parametrize(
    ("offset", "accepted"),
    [
        (timedelta(microseconds=-1), True),
        (timedelta(0), False),
        (timedelta(microseconds=1), False),
    ],
)
def test_disabled_wordpress_rechecks_claim_deadline_at_cutover_export(
    offset: timedelta, accepted: bool
) -> None:
    sealed = _sealed()
    deadline = min(
        item.next_review_at for item in sealed.review_candidate.claim_bindings
    )
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    object.__setattr__(export_binding, "captured_at", deadline + offset)
    adapter = DisabledPhase3WordPressUpdate()
    if accepted:
        receipt = adapter.dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=deadline + offset,
        )
        preconditions = receipt["preconditions"]
        assert isinstance(preconditions, dict)
        assert preconditions["satisfied"] is True
        assert sealed.verify_seal(as_of=deadline + offset)
    else:
        with pytest.raises(AdapterError) as error:
            adapter.dry_run(
                sealed,
                export_binding=export_binding,
                evaluated_at=deadline + offset,
            )
        assert error.value.code is AdapterFailure.STALE
        assert not sealed.verify_seal(as_of=deadline + offset)


@pytest.mark.parametrize(
    ("case", "accepted"),
    [
        ("exact-max-age", True),
        ("stale-by-one-microsecond", False),
        ("future-export", False),
        ("backdated-evaluation", False),
    ],
)
def test_disabled_wordpress_export_age_and_time_order_are_fail_closed(
    case: str, accepted: bool
) -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    if case == "exact-max-age":
        evaluated_at = export_binding.captured_at + PHASE3_WORDPRESS_EXPORT_MAX_AGE
    elif case == "stale-by-one-microsecond":
        evaluated_at = (
            export_binding.captured_at
            + PHASE3_WORDPRESS_EXPORT_MAX_AGE
            + timedelta(microseconds=1)
        )
    elif case == "future-export":
        evaluated_at = export_binding.captured_at - timedelta(microseconds=1)
    else:
        evaluated_at = sealed.review_receipt.reviewed_at - timedelta(microseconds=1)

    adapter = DisabledPhase3WordPressUpdate()
    if accepted:
        receipt = adapter.dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=evaluated_at,
        )
        preconditions = receipt["preconditions"]
        assert isinstance(preconditions, dict)
        assert preconditions["evaluated_at"] == evaluated_at.isoformat()
        assert preconditions["max_export_age_seconds"] == 300
    else:
        with pytest.raises(AdapterError) as error:
            adapter.dry_run(
                sealed,
                export_binding=export_binding,
                evaluated_at=evaluated_at,
            )
        expected = (
            AdapterFailure.STALE
            if case == "stale-by-one-microsecond"
            else AdapterFailure.INVALID_RESPONSE
        )
        assert error.value.code is expected


def test_disabled_wordpress_idempotency_binds_evaluation_time() -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    first = DisabledPhase3WordPressUpdate().dry_run(
        sealed,
        export_binding=export_binding,
        evaluated_at=export_binding.captured_at,
    )
    second = DisabledPhase3WordPressUpdate().dry_run(
        sealed,
        export_binding=export_binding,
        evaluated_at=export_binding.captured_at + timedelta(microseconds=1),
    )
    assert first["idempotency_key"] != second["idempotency_key"]


def test_disabled_wordpress_requires_aware_evaluation_time() -> None:
    sealed = _sealed()
    export_binding = _export_binding(sealed.review_candidate.update_payload)
    with pytest.raises(AdapterError) as error:
        DisabledPhase3WordPressUpdate().dry_run(
            sealed,
            export_binding=export_binding,
            evaluated_at=export_binding.captured_at.replace(tzinfo=None),
        )
    assert error.value.code is AdapterFailure.INVALID_RESPONSE


def test_phase3_machine_has_no_publish_or_live_state() -> None:
    assert set(Phase3PublicationState) == {
        Phase3PublicationState.HUMAN_REVIEWED,
        Phase3PublicationState.PACKAGE_SEALED,
    }
    assert "PUBLISHED" not in Phase3PublicationState.__members__
    assert not hasattr(Phase3PublicationPackage, "publish")


def test_phase3_claim_disposition_is_derived_from_type_and_source_status() -> None:
    evidence: ClaimEvidenceBinding = _phase2_candidate().claim_evidence[0]
    binding = Phase3ClaimBinding(
        claim_id=evidence.claim_id,
        claim_type=ClaimType.A_OFFICIAL_FACT,
        risk_class=evidence.risk_class,
        freshness=evidence.freshness,
        authoritative_source_status=ClaimStatus.VERIFIED,
        checked_at=datetime.fromisoformat("2026-08-26T13:54:33+09:00"),
        next_review_at=datetime.fromisoformat("2026-11-24T13:54:33+09:00"),
    )
    assert binding.resolved is True
    assert binding.blocking is False
    assert binding.intentionally_disclosed is False
    assert "resolved" not in Phase3ClaimBinding.__dataclass_fields__
    assert "blocking" not in Phase3ClaimBinding.__dataclass_fields__
    assert "intentionally_disclosed" not in Phase3ClaimBinding.__dataclass_fields__


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("claim_type", ClaimType.D_EDITORIAL_JUDGEMENT),
        ("risk_class", RiskClass.LOW),
        ("freshness", FreshnessState.DUE),
        ("authoritative_source_status", ClaimStatus.DRAFT),
        ("checked_at", datetime.fromisoformat("2026-08-26T13:54:34+09:00")),
        ("next_review_at", datetime.fromisoformat("2026-11-24T13:54:34+09:00")),
    ],
)
def test_phase3_rejects_claim_authority_mutation(field: str, value: object) -> None:
    phase2 = _phase2_candidate()
    bindings = _claim_bindings(phase2)
    official_id = next(
        item.claim_id
        for item in bindings
        if item.claim_type is ClaimType.A_OFFICIAL_FACT
        and item.risk_class is not RiskClass.LOW
        and item.freshness is FreshnessState.FRESH
    )
    changed = tuple(
        replace(item, **cast(Any, {field: value}))
        if item.claim_id == official_id
        else item
        for item in bindings
    )
    with pytest.raises(ValueError, match="Phase 3 claim"):
        _review_candidate(phase2=phase2, bindings=changed)


def test_wordpress_update_contract_can_only_preserve_published_status() -> None:
    payload = _update_payload()
    assert payload.fields.post_status == "publish"
    assert payload.expected_current_post_status == "publish"
    assert payload.required_after_post_status == "publish"
    assert payload.intent is (
        Phase3WordPressIntent.UPDATE_EXISTING_PUBLISHED_POST_AT_APPROVED_CUTOVER
    )
    with pytest.raises(ValueError, match="preserve published"):
        replace(payload.fields, post_status="draft")
    with pytest.raises(ValueError, match="preserve publish"):
        replace(payload, expected_current_post_status="draft")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("post_title", "<b>比較</b>"),
        ("post_title", "[gallery]"),
        ("post_excerpt", "比較&#91;改変&#93;"),
        ("meta_description", "比較&colon;改変"),
        ("meta_description", "比較\u202e改変"),
        ("post_excerpt", "比較\x00改変"),
    ],
)
def test_wordpress_plain_fields_reject_markup_shortcode_entities_and_controls(
    field: str, value: str
) -> None:
    fields = _update_payload().fields
    with pytest.raises(ValueError, match="forbidden|plain text"):
        replace(fields, **cast(Any, {field: value}))


@pytest.mark.parametrize(
    "post_content",
    [
        SAFE_POST_CONTENT + "<script>alert(1)</script>",
        SAFE_POST_CONTENT + "<h1>duplicate</h1>",
        SAFE_POST_CONTENT + "<html></html>",
        SAFE_POST_CONTENT + "<head></head>",
        SAFE_POST_CONTENT + '<img src="x">',
        SAFE_POST_CONTENT.replace(
            'href="/about-ad-policy/"',
            'href="https://hb.afl.rakuten.co.jp/example"',
        ),
        SAFE_POST_CONTENT.replace(
            'data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"', ""
        ),
        SAFE_POST_CONTENT
        + '<span data-raos-v2-package-marker="RAOS_V2_A05_POST_CONTENT_V1"></span>',
        SAFE_POST_CONTENT.replace(
            'data-raos-v2-cta-state="BLOCKED"',
            'data-raos-v2-cta-state="PASS"',
            1,
        ),
        SAFE_POST_CONTENT.replace('class="raos-v2-decision-support__disclosure"', ""),
        SAFE_POST_CONTENT + "\u202e",
    ],
)
def test_wordpress_post_content_requires_exact_safe_package_contract(
    post_content: str,
) -> None:
    with pytest.raises(ValueError, match="post_content"):
        replace(_update_payload().fields, post_content=post_content)


@pytest.mark.parametrize(
    "injection",
    [
        '<svg onload="alert(1)"></svg>',
        '<iframe src="https://example.invalid/"></iframe>',
        '<style>@import "https://example.invalid/x.css";</style>',
        '<form action="https://example.invalid/"><button>送信</button></form>',
        '<object data="https://example.invalid/"></object>',
        '<embed src="https://example.invalid/">',
        "<a href=javascript:alert(1)>危険</a>",
        '<a href="JaVaScRiPt:alert(1)">危険</a>',
        '<a href="jav&#x61;script:alert(1)">危険</a>',
        "<a href=/about-ad-policy/>非canonical属性</a>",
        "<a href='/about-ad-policy/'>非canonical引用符</a>",
        '<A HREF="/about-ad-policy/">非canonical大小文字</A>',
        '<a href="/about-ad-policy/" onclick="alert(1)">危険</a>',
        '<p style="background:url(https://example.invalid/)">危険</p>',
        '<DIV ONLOAD="alert(1)">危険</DIV>',
        '[gallery ids="1"]',
        "[evil]危険[/evil]",
        "[embed]https://example.invalid/[/embed]",
    ],
)
def test_wordpress_post_content_strict_allowlist_rejects_html_bypass_variants(
    injection: str,
) -> None:
    attacked = SAFE_POST_CONTENT.replace("</div>", injection + "</div>", 1)
    with pytest.raises(ValueError, match="post_content"):
        replace(_update_payload().fields, post_content=attacked)


def test_generated_wordpress_fields_pass_domain_boundary() -> None:
    path = ROOT / "changes/raos-v2/phase-3/generated/wordpress-update-candidate.v1.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    fields = document["fields"]
    assert isinstance(fields, dict)
    validated = Phase3WordPressUpdateFields(**fields)
    assert validated.post_content.count('data-raos-v2-cta-state="BLOCKED"') == 3
    expectation = Phase3StructuredDataExpectation.from_wordpress_fields(validated)
    assert expectation.verify_integrity()
