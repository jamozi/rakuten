from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from uuid import UUID

import pytest

import raos.domain.evidence.claim_evidence as claim_evidence_module
from raos.domain.evidence.claim_evidence import (
    CitationId,
    ClaimEvidenceSnapshot,
    ClaimEvidenceValueError,
    ConflictId,
    ConflictStatus,
    CoverageContractBinding,
    CoverageFindingCode,
    CoverageStatus,
    EvidenceConflict,
    EvidenceLink,
    EvidenceOrigin,
    EvidenceValidationAttestation,
    IdentityStatus,
    PolicyClaimType,
    PolicyLinkSupportType,
    PolicySourceTier,
    UnknownValueHandling,
    ValidationAttestationOrigin,
    complete_claim_set_sha256,
    evaluate_claim_evidence,
    meets_all_verifiable_threshold,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from raos.domain.evidence.ids import ClaimId, FactId
from raos.domain.shared.persistence import AwareUtcDateTime, Sha256Digest


def _reattest(value: ClaimEvidenceSnapshot) -> ClaimEvidenceSnapshot:
    unbound = replace(value, attestations=())
    attestations = []
    for kind, subject, input_sha in required_validation_attestation_inputs(unbound):
        owner, contract_version, contract_sha = validation_attestation_owner_binding(
            kind
        )
        decision = recorded_synthetic_attestation_decision_sha256(
            kind,
            subject,
            input_sha,
        )
        attestations.append(
            EvidenceValidationAttestation(
                kind=kind,
                owner_story_id=owner,
                contract_version=contract_version,
                contract_sha256=contract_sha,
                origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
                subject_sha256=subject,
                input_sha256=input_sha,
                decision_sha256=decision,
                validated_at=value.evaluated_at,
                valid=True,
            )
        )
    return replace(unbound, attestations=tuple(attestations))


def _single(value: ClaimEvidenceSnapshot) -> ClaimEvidenceSnapshot:
    claim = value.claims[0]
    fact = value.facts[0]
    claims = (claim,)
    article = replace(
        value.article,
        complete_claim_ids=(claim.claim_id,),
        complete_claim_set_sha256=complete_claim_set_sha256(claims),
    )
    return _reattest(
        replace(
            value,
            article=article,
            approved_packet=replace(value.approved_packet, fact_ids=(fact.fact_id,)),
            claims=claims,
            requirement_proofs=(value.requirement_proofs[0],),
            facts=(fact,),
            links=(value.links[0],),
            snapshots=(value.snapshots[0],),
            identities=(value.identities[0],),
            citations=(value.citations[0],),
        )
    )


def _claim_type(
    value: ClaimEvidenceSnapshot,
    claim_type: PolicyClaimType,
) -> ClaimEvidenceSnapshot:
    value = _single(value)
    claim = replace(value.claims[0], claim_type=claim_type)
    proof = value.requirement_proofs[0]
    source = value.sources[0]
    digest = Sha256Digest("d" * 64)
    if claim_type is PolicyClaimType.DERIVED_FACT:
        proof = replace(proof, derivation_formula_sha256=digest)
    elif claim_type is PolicyClaimType.COMPARATIVE:
        proof = replace(proof, comparison_population_sha256=digest)
    elif claim_type is PolicyClaimType.RECOMMENDATION:
        proof = replace(proof, recommendation_methodology_sha256=digest)
    elif claim_type is PolicyClaimType.EXPERIENCE:
        proof = replace(
            proof,
            experience_record_sha256=digest,
            experience_approved=True,
        )
        source = replace(
            source,
            tier=PolicySourceTier.TIER_D,
            origin=EvidenceOrigin.FIRST_HAND,
        )
    elif claim_type is PolicyClaimType.PRICE_AVAILABILITY:
        source = replace(
            source,
            tier=PolicySourceTier.TIER_B,
            origin=EvidenceOrigin.OFFER,
        )
    elif claim_type is PolicyClaimType.SUPERLATIVE:
        proof = replace(proof, comparison_population_sha256=digest)
    elif claim_type is PolicyClaimType.SAFETY_LEGAL_REGULATORY:
        proof = replace(proof, safety_compliance_review_sha256=digest)
    claims = (claim,)
    return replace(
        value,
        article=replace(
            value.article,
            complete_claim_set_sha256=complete_claim_set_sha256(claims),
        ),
        claims=claims,
        requirement_proofs=(proof,),
        sources=(source,),
    )


def test_recorded_fixture_passes_without_granting_publication(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    report = evaluate_claim_evidence(passing_snapshot)
    report.require_valid()
    assert report.status is CoverageStatus.PASS
    assert report.findings == ()
    assert report.major_coverage is not None
    assert (report.major_coverage.evidenced, report.major_coverage.total) == (1, 1)
    assert report.all_verifiable_coverage is not None
    assert (
        report.all_verifiable_coverage.evidenced,
        report.all_verifiable_coverage.total,
    ) == (2, 2)
    assert report.major_requirement_satisfied is True
    assert report.all_verifiable_requirement_satisfied is True
    assert report.publication_authorized is False
    assert report.production_eligible is False
    assert b'publication_authorized":false' in report.canonical_bytes()


@pytest.mark.parametrize(
    "claim_type",
    [
        PolicyClaimType.DIRECT_FACT,
        PolicyClaimType.DERIVED_FACT,
        PolicyClaimType.COMPARATIVE,
        PolicyClaimType.RECOMMENDATION,
        PolicyClaimType.EXPERIENCE,
        PolicyClaimType.PRICE_AVAILABILITY,
        PolicyClaimType.SUPERLATIVE,
        PolicyClaimType.SAFETY_LEGAL_REGULATORY,
    ],
)
def test_non_direct_types_require_owner_attestation_before_coverage_can_pass(
    passing_snapshot: ClaimEvidenceSnapshot,
    claim_type: PolicyClaimType,
) -> None:
    candidate = _claim_type(passing_snapshot, claim_type)
    if claim_type is not PolicyClaimType.DIRECT_FACT:
        unavailable = evaluate_claim_evidence(candidate)
        assert unavailable.status is CoverageStatus.UNEVALUABLE
        assert CoverageFindingCode.REQUIRED_ATTESTATION_MISSING in unavailable.findings
    report = evaluate_claim_evidence(_reattest(candidate))
    assert report.status is CoverageStatus.PASS
    assert report.findings == ()


def test_predictive_claim_is_default_blocked_despite_complete_evidence(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    report = evaluate_claim_evidence(
        _reattest(_claim_type(passing_snapshot, PolicyClaimType.PREDICTIVE))
    )
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.PREDICTIVE_CLAIM_DEFAULT_BLOCKED in report.findings
    assert report.major_requirement_satisfied is False


def test_zero_denominators_are_unevaluable_not_vacuously_passing(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    empty = replace(
        passing_snapshot,
        article=replace(
            passing_snapshot.article,
            complete_claim_ids=(),
            complete_claim_set_sha256=Sha256Digest("0" * 64),
        ),
        approved_packet=replace(passing_snapshot.approved_packet, fact_ids=()),
        claims=(),
        requirement_proofs=(),
        facts=(),
        links=(),
        sources=(),
        snapshots=(),
        identities=(),
        conflicts=(),
        citations=(),
    )
    report = evaluate_claim_evidence(empty)
    assert report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.ZERO_DENOMINATOR_UNEVALUABLE in report.findings
    assert report.major_coverage is None
    assert report.all_verifiable_coverage is None
    assert report.major_requirement_satisfied is None
    assert report.all_verifiable_requirement_satisfied is None


def test_threshold_uses_integer_cross_multiplication() -> None:
    assert meets_all_verifiable_threshold(evidenced=19, total=20) is True
    assert meets_all_verifiable_threshold(evidenced=18, total=19) is False
    assert meets_all_verifiable_threshold(evidenced=0, total=0) is False
    assert meets_all_verifiable_threshold(evidenced=True, total=1) is False


def test_exact_95_percent_non_major_gap_passes_without_becoming_100_percent(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    claims = []
    proofs = []
    facts = []
    identities = []
    links = []
    citations = []
    for index in range(20):
        claim_id = ClaimId(UUID(f"10000000-0000-4000-8000-{index + 1:012x}"))
        fact_id = FactId(UUID(f"20000000-0000-4000-8000-{index + 1:012x}"))
        claim = replace(
            value.claims[0],
            claim_id=claim_id,
            claim_text_sha256=Sha256Digest(f"{index + 1:064x}"),
            criticality=5 if index == 0 else 1,
            affects_purchase_decision=index == 0,
        )
        fact = replace(value.facts[0], fact_id=fact_id)
        claims.append(claim)
        proofs.append(replace(value.requirement_proofs[0], claim_id=claim_id))
        facts.append(fact)
        identities.append(replace(value.identities[0], fact_id=fact_id))
        if index < 19:
            links.append(replace(value.links[0], claim_id=claim_id, fact_id=fact_id))
            citations.append(
                replace(
                    value.citations[0],
                    citation_id=CitationId(
                        UUID(f"30000000-0000-4000-8000-{index + 1:012x}")
                    ),
                    claim_id=claim_id,
                    fact_id=fact_id,
                )
            )
    claim_tuple = tuple(claims)
    expanded = replace(
        value,
        article=replace(
            value.article,
            complete_claim_ids=tuple(item.claim_id for item in claim_tuple),
            complete_claim_set_sha256=complete_claim_set_sha256(claim_tuple),
        ),
        approved_packet=replace(
            value.approved_packet,
            fact_ids=tuple(item.fact_id for item in facts),
        ),
        claims=claim_tuple,
        requirement_proofs=tuple(proofs),
        facts=tuple(facts),
        links=tuple(links),
        identities=tuple(identities),
        citations=tuple(citations),
    )
    report = evaluate_claim_evidence(_reattest(expanded))
    assert report.status is CoverageStatus.PASS
    assert report.findings == ()
    assert report.major_coverage is not None
    assert (report.major_coverage.evidenced, report.major_coverage.total) == (1, 1)
    assert report.all_verifiable_coverage is not None
    assert (
        report.all_verifiable_coverage.evidenced,
        report.all_verifiable_coverage.total,
    ) == (19, 20)


def test_support_is_required_and_qualifies_alone_never_counts(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    link = replace(value.links[0], support_type=PolicyLinkSupportType.QUALIFIES)
    citation = replace(value.citations[0], support_type=PolicyLinkSupportType.QUALIFIES)
    report = evaluate_claim_evidence(
        replace(value, links=(link,), citations=(citation,))
    )
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.QUALIFIES_WITHOUT_SUPPORT in report.findings
    assert CoverageFindingCode.EVIDENCE_REQUIRED in report.findings
    assert CoverageFindingCode.MAJOR_COVERAGE_BELOW_100 in report.findings


def test_contradictory_link_blocks_even_with_support(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    contradiction = EvidenceLink(
        claim_id=value.claims[0].claim_id,
        fact_id=value.facts[0].fact_id,
        support_type=PolicyLinkSupportType.CONTRADICTS,
    )
    citation = replace(
        value.citations[0],
        citation_id=CitationId(UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")),
        support_type=PolicyLinkSupportType.CONTRADICTS,
    )
    report = evaluate_claim_evidence(
        replace(
            value,
            links=(*value.links, contradiction),
            citations=(*value.citations, citation),
        )
    )
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.CONTRADICTORY_EVIDENCE in report.findings


@pytest.mark.parametrize(
    ("identity", "finding"),
    [
        (IdentityStatus.UNRESOLVED, CoverageFindingCode.IDENTITY_UNRESOLVED),
        (IdentityStatus.CONFLICTING, CoverageFindingCode.IDENTITY_CONFLICT),
    ],
)
def test_identity_mismatch_fails_closed(
    passing_snapshot: ClaimEvidenceSnapshot,
    identity: IdentityStatus,
    finding: CoverageFindingCode,
) -> None:
    value = _single(passing_snapshot)
    report = evaluate_claim_evidence(
        _reattest(
            replace(
                value,
                identities=(replace(value.identities[0], status=identity),),
            )
        )
    )
    assert report.status is CoverageStatus.BLOCK
    assert finding in report.findings
    assert CoverageFindingCode.EVIDENCE_REQUIRED in report.findings


def test_stale_critical_evidence_blocks(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    stale = replace(
        value.snapshots[0],
        expires_at=AwareUtcDateTime(datetime(2026, 8, 24, tzinfo=timezone.utc)),
    )
    report = evaluate_claim_evidence(_reattest(replace(value, snapshots=(stale,))))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.STALE_EVIDENCE in report.findings


def test_open_source_conflict_blocks(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    conflict = EvidenceConflict(
        conflict_id=ConflictId(UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")),
        fact_ids=(value.facts[0].fact_id,),
        status=ConflictStatus.OPEN,
        resolution_decision_sha256=None,
        reviewer_identity_sha256=None,
        resolved_at=None,
    )
    report = evaluate_claim_evidence(_reattest(replace(value, conflicts=(conflict,))))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.UNRESOLVED_CONFLICT in report.findings


@pytest.mark.parametrize(
    ("origin", "tier", "finding"),
    [
        (
            EvidenceOrigin.AI_OUTPUT,
            PolicySourceTier.EXCLUDED,
            CoverageFindingCode.AI_OUTPUT_IS_NOT_EVIDENCE,
        ),
        (
            EvidenceOrigin.SEARCH_SNIPPET,
            PolicySourceTier.DISCOVERY,
            CoverageFindingCode.SEARCH_SNIPPET_IS_NOT_EVIDENCE,
        ),
        (
            EvidenceOrigin.RAKUTEN_REVIEW_BODY,
            PolicySourceTier.EXCLUDED,
            CoverageFindingCode.RAKUTEN_REVIEW_BODY_PROHIBITED,
        ),
        (
            EvidenceOrigin.COMPETITOR_CONTENT,
            PolicySourceTier.DISCOVERY,
            CoverageFindingCode.COMPETITOR_CONTENT_DISCOVERY_ONLY,
        ),
    ],
)
def test_prohibited_source_origins_never_count_as_evidence(
    passing_snapshot: ClaimEvidenceSnapshot,
    origin: EvidenceOrigin,
    tier: PolicySourceTier,
    finding: CoverageFindingCode,
) -> None:
    value = _single(passing_snapshot)
    source = replace(value.sources[0], origin=origin, tier=tier)
    report = evaluate_claim_evidence(_reattest(replace(value, sources=(source,))))
    assert report.status is CoverageStatus.BLOCK
    assert finding in report.findings


def test_claim_type_source_tier_mismatch_blocks(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    source = replace(
        value.sources[0],
        origin=EvidenceOrigin.INDEPENDENT,
        tier=PolicySourceTier.TIER_C,
    )
    report = evaluate_claim_evidence(_reattest(replace(value, sources=(source,))))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.SOURCE_TIER_MISMATCH in report.findings


def test_missing_citation_resolution_blocks(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    report = evaluate_claim_evidence(replace(value, citations=()))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.CITATION_SET_MISMATCH in report.findings
    assert CoverageFindingCode.CITATION_RESOLUTION_INVALID in report.findings


def test_out_of_packet_fact_blocks(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    report = evaluate_claim_evidence(
        _reattest(
            replace(
                value,
                approved_packet=replace(value.approved_packet, fact_ids=()),
            )
        )
    )
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.FACT_OUTSIDE_APPROVED_PACKET in report.findings
    assert CoverageFindingCode.PACKET_FACT_SET_MISMATCH in report.findings


def test_multiple_facts_may_share_one_complete_source_snapshot(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    shared_snapshot = passing_snapshot.snapshots[0]
    facts = (
        passing_snapshot.facts[0],
        replace(
            passing_snapshot.facts[1],
            source_snapshot_id=shared_snapshot.source_snapshot_id,
        ),
    )
    citations = (
        passing_snapshot.citations[0],
        replace(
            passing_snapshot.citations[1],
            source_id=shared_snapshot.source_id,
            source_snapshot_id=shared_snapshot.source_snapshot_id,
        ),
    )
    report = evaluate_claim_evidence(
        _reattest(
            replace(
                passing_snapshot,
                facts=facts,
                snapshots=(shared_snapshot,),
                citations=citations,
            )
        )
    )
    assert report.status is CoverageStatus.PASS


def test_temporal_formula_experience_population_and_imputation_rules(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    no_time = replace(
        value,
        requirement_proofs=(
            replace(value.requirement_proofs[0], temporal_scope_sha256=None),
        ),
    )
    assert (
        CoverageFindingCode.TEMPORAL_SCOPE_REQUIRED
        in evaluate_claim_evidence(no_time).findings
    )

    derived = _claim_type(passing_snapshot, PolicyClaimType.DERIVED_FACT)
    derived = replace(
        derived,
        requirement_proofs=(
            replace(derived.requirement_proofs[0], derivation_formula_sha256=None),
        ),
    )
    assert (
        CoverageFindingCode.DERIVED_FORMULA_REQUIRED
        in evaluate_claim_evidence(derived).findings
    )

    experience = _claim_type(passing_snapshot, PolicyClaimType.EXPERIENCE)
    experience = replace(
        experience,
        requirement_proofs=(
            replace(
                experience.requirement_proofs[0],
                experience_record_sha256=None,
                experience_approved=False,
            ),
        ),
    )
    experience_findings = evaluate_claim_evidence(experience).findings
    assert CoverageFindingCode.EXPERIENCE_RECORD_REQUIRED in experience_findings
    assert CoverageFindingCode.EXPERIENCE_APPROVAL_REQUIRED in experience_findings

    superlative = _claim_type(passing_snapshot, PolicyClaimType.SUPERLATIVE)
    superlative = replace(
        superlative,
        requirement_proofs=(
            replace(
                superlative.requirement_proofs[0],
                comparison_population_sha256=None,
            ),
        ),
    )
    assert CoverageFindingCode.COMPARISON_POPULATION_REQUIRED in (
        evaluate_claim_evidence(superlative).findings
    )

    imputed = replace(
        value,
        requirement_proofs=(
            replace(
                value.requirement_proofs[0],
                unknown_value_handling=UnknownValueHandling.IMPUTED,
            ),
        ),
    )
    assert CoverageFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN in (
        evaluate_claim_evidence(imputed).findings
    )


def test_binding_claim_set_duplicates_and_unknown_types_fail_closed(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    wrong_contract = replace(
        value,
        contract=replace(
            CoverageContractBinding.current(),
            policy_sha256=Sha256Digest("f" * 64),
        ),
    )
    assert evaluate_claim_evidence(wrong_contract).status is CoverageStatus.UNEVALUABLE

    wrong_hash = replace(
        value,
        article=replace(
            value.article,
            complete_claim_set_sha256=Sha256Digest("f" * 64),
        ),
    )
    assert CoverageFindingCode.CLAIM_SET_HASH_MISMATCH in (
        evaluate_claim_evidence(wrong_hash).findings
    )

    duplicate = replace(value, claims=(value.claims[0], value.claims[0]))
    duplicate_report = evaluate_claim_evidence(duplicate)
    assert duplicate_report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.DUPLICATE_CLAIM_ID in duplicate_report.findings

    mutated = replace(value.claims[0])
    object.__setattr__(mutated, "claim_type", "invented")
    unknown = replace(value, claims=(mutated,))
    assert (
        CoverageFindingCode.RECORD_TYPE_INVALID
        in evaluate_claim_evidence(unknown).findings
    )


def test_report_never_contains_raw_claim_or_source_text(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    canary = "raw-claim-source-canary"
    report = evaluate_claim_evidence(passing_snapshot)
    assert canary not in repr(report)
    assert canary.encode() not in report.canonical_bytes()
    assert "<redacted-st0605>" in repr(report)


def test_claim_subset_cannot_replace_the_attested_complete_inventory(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    claim = passing_snapshot.claims[0]
    fact = passing_snapshot.facts[0]
    claims = (claim,)
    subset = replace(
        passing_snapshot,
        article=replace(
            passing_snapshot.article,
            complete_claim_ids=(claim.claim_id,),
            complete_claim_set_sha256=complete_claim_set_sha256(claims),
        ),
        approved_packet=replace(
            passing_snapshot.approved_packet,
            fact_ids=(fact.fact_id,),
        ),
        claims=claims,
        requirement_proofs=(passing_snapshot.requirement_proofs[0],),
        facts=(fact,),
        links=(passing_snapshot.links[0],),
        snapshots=(passing_snapshot.snapshots[0],),
        identities=(passing_snapshot.identities[0],),
        citations=(passing_snapshot.citations[0],),
    )
    report = evaluate_claim_evidence(subset)
    assert report.status is CoverageStatus.UNEVALUABLE
    assert any(
        finding
        in {
            CoverageFindingCode.ATTESTATION_INVALID,
            CoverageFindingCode.ATTESTATION_SET_MISMATCH,
        }
        for finding in report.findings
    )


def test_article_rejects_a_different_self_declared_approved_packet(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    packet = replace(
        passing_snapshot.approved_packet,
        source_packet_version_id=type(
            passing_snapshot.approved_packet.source_packet_version_id
        )(UUID("40000000-0000-4000-8000-000000000001")),
        content_sha256=Sha256Digest("e" * 64),
    )
    report = evaluate_claim_evidence(replace(passing_snapshot, approved_packet=packet))
    assert report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.ARTICLE_PACKET_BINDING_MISMATCH in report.findings


def test_future_evidence_and_invalid_time_window_block(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    future = replace(
        value.snapshots[0],
        acquired_at=AwareUtcDateTime(datetime(2027, 1, 1, tzinfo=timezone.utc)),
        expires_at=AwareUtcDateTime(datetime(2026, 12, 1, tzinfo=timezone.utc)),
    )
    report = evaluate_claim_evidence(_reattest(replace(value, snapshots=(future,))))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.FUTURE_EVIDENCE in report.findings
    assert CoverageFindingCode.EVIDENCE_TIME_WINDOW_INVALID in report.findings


def test_future_packet_approval_cannot_pass(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    future_packet = replace(
        passing_snapshot.approved_packet,
        approved_at=AwareUtcDateTime(
            passing_snapshot.evaluated_at.value.replace(year=2030)
        ),
    )
    report = evaluate_claim_evidence(
        _reattest(replace(passing_snapshot, approved_packet=future_packet))
    )
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.FUTURE_EVIDENCE in report.findings


def test_resolved_conflict_without_review_evidence_cannot_pass_silently(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    value = _single(passing_snapshot)
    conflict = EvidenceConflict(
        conflict_id=ConflictId(UUID("50000000-0000-4000-8000-000000000001")),
        fact_ids=(value.facts[0].fact_id,),
        status=ConflictStatus.RESOLVED,
        resolution_decision_sha256=None,
        reviewer_identity_sha256=None,
        resolved_at=None,
    )
    report = evaluate_claim_evidence(_reattest(replace(value, conflicts=(conflict,))))
    assert report.status is CoverageStatus.BLOCK
    assert CoverageFindingCode.CONFLICT_RESOLUTION_EVIDENCE_REQUIRED in report.findings


def test_attestation_owner_version_hash_and_origin_are_closed(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    first = passing_snapshot.attestations[0]
    tampered = replace(first, owner_story_id="ST-9999")
    report = evaluate_claim_evidence(
        replace(
            passing_snapshot,
            attestations=(tampered, *passing_snapshot.attestations[1:]),
        )
    )
    assert report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.REQUIRED_ATTESTATION_MISSING in report.findings


def test_recorded_attestation_decision_digest_detects_corruption(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    first = passing_snapshot.attestations[0]
    corrupted = replace(first, decision_sha256=Sha256Digest("f" * 64))
    report = evaluate_claim_evidence(
        replace(
            passing_snapshot,
            attestations=(corrupted, *passing_snapshot.attestations[1:]),
        )
    )
    assert report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.REQUIRED_ATTESTATION_MISSING in report.findings


def test_semantically_empty_forged_pass_report_fails_validation(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    report = evaluate_claim_evidence(passing_snapshot)
    placeholder = replace(
        report,
        article_version_id=None,
        article_body_sha256=None,
        source_packet_version_id=None,
        source_packet_content_sha256=None,
        evaluated_at=None,
        evaluation_input_sha256=None,
        complete_claim_set_sha256=None,
        major_coverage=None,
        all_verifiable_coverage=None,
        major_requirement_satisfied=None,
        all_verifiable_requirement_satisfied=None,
        findings=(),
        status=CoverageStatus.PASS,
        report_sha256=Sha256Digest("0" * 64),
    )
    forged = replace(
        placeholder,
        report_sha256=Sha256Digest(
            hashlib.sha256(
                claim_evidence_module._report_bytes(  # noqa: SLF001
                    placeholder,
                    include_digest=False,
                )
            ).hexdigest()
        ),
    )
    with pytest.raises(ClaimEvidenceValueError):
        forged.require_valid()


def test_malformed_exact_snapshot_returns_sanitized_unevaluable(
    passing_snapshot: ClaimEvidenceSnapshot,
) -> None:
    malformed = replace(passing_snapshot)
    object.__setattr__(malformed, "article", object())
    report = evaluate_claim_evidence(malformed)
    assert report.status is CoverageStatus.UNEVALUABLE
    assert CoverageFindingCode.ARTICLE_BINDING_INVALID in report.findings
    assert CoverageFindingCode.ATTESTATION_INVALID in report.findings
