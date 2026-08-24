from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from uuid import UUID

import pytest

from raos.domain.editorial.comparison_validation_v2 import (
    CandidateUniverse,
    CandidateUniverseId,
    ComparisonAxisDataType,
    ComparisonCellStatus,
    ComparisonFindingCode,
    ComparisonRuntimeValueError,
    ComparisonSnapshotV2,
    ComparisonValidationEnvelopeV2,
    ComparisonValidationStatus,
    TypedComparisonValue,
    article_binding_sha256,
    axis_catalog_sha256,
    candidate_universe_sha256,
    canonical_decimal,
    comparison_input_sha256,
    fact_set_sha256,
    temporal_scope_sha256,
    validate_comparison_v2,
)
from raos.domain.evidence.claim_evidence import (
    ClaimEvidenceSnapshot,
    CoverageStatus,
    EvidenceValidationAttestation,
    IdentityStatus,
    ValidationAttestationKind,
    ValidationAttestationOrigin,
    evaluate_claim_evidence,
    recorded_synthetic_attestation_decision_sha256,
    required_validation_attestation_inputs,
    validation_attestation_owner_binding,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.domain.shared.persistence import AwareUtcDateTime


def _rehash_comparison(comparison: ComparisonSnapshotV2) -> ComparisonSnapshotV2:
    candidate = comparison.candidate_universe
    candidate = replace(
        candidate,
        candidate_universe_sha256=candidate_universe_sha256(candidate),
    )
    catalog = comparison.axis_catalog
    catalog = replace(catalog, axis_catalog_sha256=axis_catalog_sha256(catalog))
    rebound = replace(
        comparison,
        candidate_universe=candidate,
        axis_catalog=catalog,
        fact_set_sha256=fact_set_sha256(comparison.facts),
        temporal_scope_sha256=temporal_scope_sha256(
            evaluated_at=comparison.evaluated_at,
            facts=comparison.facts,
        ),
        evaluation_input_sha256=Sha256Digest("0" * 64),
    )
    return replace(rebound, evaluation_input_sha256=comparison_input_sha256(rebound))


def _receipts_without_comparison(
    claim_snapshot: ClaimEvidenceSnapshot,
) -> tuple[EvidenceValidationAttestation, ...]:
    bare = replace(claim_snapshot, attestations=())
    receipts: list[EvidenceValidationAttestation] = []
    for kind, subject, input_digest in required_validation_attestation_inputs(bare):
        if kind is ValidationAttestationKind.COMPARISON:
            continue
        owner, version, contract_sha256 = validation_attestation_owner_binding(kind)
        receipts.append(
            EvidenceValidationAttestation(
                kind=kind,
                owner_story_id=owner,
                contract_version=version,
                contract_sha256=contract_sha256,
                origin=ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY,
                subject_sha256=subject,
                input_sha256=input_digest,
                decision_sha256=recorded_synthetic_attestation_decision_sha256(
                    kind,
                    subject,
                    input_digest,
                ),
                validated_at=claim_snapshot.evaluated_at,
                valid=True,
            )
        )
    return tuple(receipts)


def test_pass_binds_every_input_and_emits_exact_comparison_receipt(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    report = validate_comparison_v2(envelope)
    report.require_valid()
    comparison = envelope.comparison

    assert report.status is ComparisonValidationStatus.LOCAL_VALIDATED
    assert report.findings == ()
    assert report.article_id == comparison.article.article_id
    assert report.article_version_id == comparison.article.article_version_id
    assert report.article_version_no == comparison.article.article_version_no
    assert report.article_body_sha256 == comparison.article.article_body_sha256
    assert report.article_binding_sha256 == comparison.article.binding_sha256
    assert (
        report.source_packet_version_id == comparison.article.source_packet_version_id
    )
    assert (
        report.source_packet_content_sha256
        == comparison.article.source_packet_content_sha256
    )
    assert (
        report.complete_claim_set_sha256 == comparison.article.complete_claim_set_sha256
    )
    assert (
        report.candidate_universe_sha256
        == comparison.candidate_universe.candidate_universe_sha256
    )
    assert report.axis_catalog_sha256 == comparison.axis_catalog.axis_catalog_sha256
    assert report.fact_set_sha256 == comparison.fact_set_sha256
    assert report.temporal_scope_sha256 == comparison.temporal_scope_sha256
    assert report.evaluation_input_sha256 == comparison.evaluation_input_sha256
    assert report.evaluated_at == comparison.evaluated_at
    assert len(report.comparison_attestations) == 1
    receipt = report.comparison_attestations[0]
    assert receipt.kind is ValidationAttestationKind.COMPARISON
    assert receipt.owner_story_id == "ST-0803"
    assert receipt.origin is ValidationAttestationOrigin.RECORDED_SYNTHETIC_ONLY
    assert receipt.valid is True
    assert not report.publication_authorized
    assert not report.recommendation_authorized
    assert not report.ranking_authorized
    assert not report.production_eligible


def test_emitted_receipt_closes_st0605_without_mutating_input(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    before = envelope.claim_evidence.attestations
    report = validate_comparison_v2(envelope)
    rebound = replace(
        envelope.claim_evidence,
        attestations=(*before, *report.comparison_attestations),
    )

    assert envelope.claim_evidence.attestations == before
    coverage = evaluate_claim_evidence(rebound)
    assert coverage.status is CoverageStatus.PASS
    assert coverage.findings == ()


def test_declared_hash_drift_is_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    cases = (
        (
            replace(
                envelope.comparison,
                fact_set_sha256=Sha256Digest("f" * 64),
            ),
            ComparisonFindingCode.FACT_SET_HASH_MISMATCH,
        ),
        (
            replace(
                envelope.comparison,
                temporal_scope_sha256=Sha256Digest("f" * 64),
            ),
            ComparisonFindingCode.TEMPORAL_SCOPE_HASH_MISMATCH,
        ),
        (
            replace(
                envelope.comparison,
                evaluation_input_sha256=Sha256Digest("f" * 64),
            ),
            ComparisonFindingCode.EVALUATION_INPUT_HASH_MISMATCH,
        ),
    )
    for corrupt, finding in cases:
        report = validate_comparison_v2(replace(envelope, comparison=corrupt))
        assert report.status is ComparisonValidationStatus.UNEVALUABLE
        assert finding in report.findings
        assert report.comparison_attestations == ()


def test_candidate_and_axis_hash_drift_are_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    candidate = replace(
        envelope.comparison.candidate_universe,
        candidate_universe_sha256=Sha256Digest("e" * 64),
    )
    candidate_report = validate_comparison_v2(
        replace(
            envelope,
            comparison=replace(envelope.comparison, candidate_universe=candidate),
        )
    )
    catalog = replace(
        envelope.comparison.axis_catalog,
        axis_catalog_sha256=Sha256Digest("d" * 64),
    )
    catalog_report = validate_comparison_v2(
        replace(envelope, comparison=replace(envelope.comparison, axis_catalog=catalog))
    )

    assert candidate_report.status is ComparisonValidationStatus.UNEVALUABLE
    assert (
        ComparisonFindingCode.CANDIDATE_UNIVERSE_HASH_MISMATCH
        in candidate_report.findings
    )
    assert catalog_report.status is ComparisonValidationStatus.UNEVALUABLE
    assert ComparisonFindingCode.AXIS_CATALOG_HASH_MISMATCH in catalog_report.findings


def test_exact_article_body_packet_and_claim_set_drift_are_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    changed_articles = (
        replace(
            envelope.comparison.article,
            article_body_sha256=Sha256Digest("a" * 64),
        ),
        replace(
            envelope.comparison.article,
            source_packet_content_sha256=Sha256Digest("a" * 64),
        ),
        replace(
            envelope.comparison.article,
            complete_claim_set_sha256=Sha256Digest("a" * 64),
        ),
    )
    for changed in changed_articles:
        changed = replace(changed, binding_sha256=article_binding_sha256(changed))
        comparison = _rehash_comparison(replace(envelope.comparison, article=changed))
        report = validate_comparison_v2(replace(envelope, comparison=comparison))
        assert report.status is ComparisonValidationStatus.UNEVALUABLE
        assert ComparisonFindingCode.ARTICLE_BINDING_INVALID in report.findings


def test_candidate_population_semantic_mismatch_blocks(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    universe = replace(
        envelope.comparison.candidate_universe,
        version_no=envelope.comparison.candidate_universe.version_no + 1,
    )
    comparison = _rehash_comparison(
        replace(envelope.comparison, candidate_universe=universe)
    )
    report = validate_comparison_v2(replace(envelope, comparison=comparison))

    assert report.status is ComparisonValidationStatus.BLOCK
    assert ComparisonFindingCode.CLAIM_POPULATION_MISMATCH in report.findings


def test_temporal_scope_semantic_mismatch_blocks(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    evaluated_at = AwareUtcDateTime(datetime(2026, 8, 25, tzinfo=timezone.utc))
    comparison = _rehash_comparison(
        replace(envelope.comparison, evaluated_at=evaluated_at)
    )
    claim_snapshot = replace(
        envelope.claim_evidence,
        evaluated_at=evaluated_at,
        attestations=(),
    )
    claim_snapshot = replace(
        claim_snapshot,
        attestations=_receipts_without_comparison(claim_snapshot),
    )
    report = validate_comparison_v2(
        replace(
            envelope,
            comparison=comparison,
            claim_evidence=claim_snapshot,
        )
    )

    assert report.status is ComparisonValidationStatus.BLOCK
    assert ComparisonFindingCode.CLAIM_TEMPORAL_SCOPE_MISMATCH in report.findings


def test_trusted_variant_mismatch_blocks(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    facts = (
        replace(
            envelope.comparison.facts[0],
            variant_identity_sha256=Sha256Digest("9" * 64),
        ),
        envelope.comparison.facts[1],
    )
    comparison = _rehash_comparison(replace(envelope.comparison, facts=facts))
    report = validate_comparison_v2(replace(envelope, comparison=comparison))

    assert report.status is ComparisonValidationStatus.BLOCK
    assert ComparisonFindingCode.VARIANT_MISMATCH in report.findings
    assert report.comparison_attestations == ()


@pytest.mark.parametrize(
    "alias",
    [
        "COMMISSION_RATE",
        "AFF1L1ATE_RATE",
        "SP0NS0R_BENEFIT",
        "EPC",
        "REVENUE",
        "CONTRIBUTION_PROFIT",
    ],
)
def test_finance_and_affiliate_axis_aliases_block(
    envelope: ComparisonValidationEnvelopeV2,
    alias: str,
) -> None:
    axis = replace(envelope.comparison.axis_catalog.axes[0], axis_code=alias)
    catalog = replace(envelope.comparison.axis_catalog, axes=(axis,))
    comparison = _rehash_comparison(replace(envelope.comparison, axis_catalog=catalog))
    report = validate_comparison_v2(replace(envelope, comparison=comparison))

    assert report.status is ComparisonValidationStatus.BLOCK
    assert ComparisonFindingCode.PROHIBITED_AXIS in report.findings


@pytest.mark.parametrize(
    ("status", "finding"),
    [
        (
            ComparisonCellStatus.UNKNOWN,
            ComparisonFindingCode.UNKNOWN_VALUE_IMPUTATION_FORBIDDEN,
        ),
        (ComparisonCellStatus.MISSING, ComparisonFindingCode.REQUIRED_VALUE_MISSING),
        (ComparisonCellStatus.CONFLICT, ComparisonFindingCode.CONFLICTING_VALUE),
        (ComparisonCellStatus.UNSUPPORTED, ComparisonFindingCode.UNSUPPORTED_VALUE),
    ],
)
def test_explicit_nonvalid_states_never_pass(
    envelope: ComparisonValidationEnvelopeV2,
    status: ComparisonCellStatus,
    finding: ComparisonFindingCode,
) -> None:
    cell = replace(envelope.comparison.cells[0], status=status)
    comparison = _rehash_comparison(
        replace(
            envelope.comparison,
            cells=(cell, envelope.comparison.cells[1]),
        )
    )
    report = validate_comparison_v2(replace(envelope, comparison=comparison))

    assert report.status is not ComparisonValidationStatus.LOCAL_VALIDATED
    assert finding in report.findings
    assert report.comparison_attestations == ()


def test_missing_exact_st0504_receipt_is_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    receipts = tuple(
        item
        for item in envelope.claim_evidence.attestations
        if item.kind is not ValidationAttestationKind.IDENTITY_DECISION
    )
    claim_snapshot = replace(envelope.claim_evidence, attestations=receipts)
    report = validate_comparison_v2(replace(envelope, claim_evidence=claim_snapshot))

    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert ComparisonFindingCode.IDENTITY_RECEIPT_MISSING in report.findings


def test_oversized_nested_contract_string_is_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    receipt = replace(
        envelope.claim_evidence.attestations[0],
        owner_story_id="X" * 161,
    )
    claim_snapshot = replace(
        envelope.claim_evidence,
        attestations=(receipt, *envelope.claim_evidence.attestations[1:]),
    )
    report = validate_comparison_v2(replace(envelope, claim_evidence=claim_snapshot))

    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert ComparisonFindingCode.ST0605_INPUT_INVALID in report.findings


def test_preexisting_comparison_receipt_is_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    emitted = validate_comparison_v2(envelope).comparison_attestations
    claim_snapshot = replace(
        envelope.claim_evidence,
        attestations=(*envelope.claim_evidence.attestations, *emitted),
    )
    report = validate_comparison_v2(replace(envelope, claim_evidence=claim_snapshot))

    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert ComparisonFindingCode.PREEXISTING_COMPARISON_RECEIPT in report.findings


def test_trusted_identity_mismatch_blocks(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    identities = (
        replace(
            envelope.claim_evidence.identities[0],
            status=IdentityStatus.CONFLICTING,
        ),
        envelope.claim_evidence.identities[1],
    )
    changed = replace(envelope.claim_evidence, identities=identities, attestations=())
    changed = replace(changed, attestations=_receipts_without_comparison(changed))
    report = validate_comparison_v2(replace(envelope, claim_evidence=changed))

    assert report.status is ComparisonValidationStatus.BLOCK
    assert ComparisonFindingCode.ST0605_SEMANTIC_BLOCK in report.findings


def test_structural_collection_overflow_is_unevaluable(
    envelope: ComparisonValidationEnvelopeV2,
) -> None:
    products = envelope.comparison.candidate_universe.products * 11
    universe = replace(envelope.comparison.candidate_universe, products=products)
    report = validate_comparison_v2(
        replace(
            envelope,
            comparison=replace(envelope.comparison, candidate_universe=universe),
        )
    )

    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert ComparisonFindingCode.COLLECTION_BOUND_INVALID in report.findings


def test_wrong_root_type_is_redacted_unevaluable() -> None:
    report = validate_comparison_v2({"untrusted": "must-not-echo"})

    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert report.findings == (ComparisonFindingCode.INPUT_TYPE_INVALID,)
    assert b"must-not-echo" not in report.canonical_bytes()


def test_incomplete_exact_runtime_objects_fail_closed_without_exception() -> None:
    unsafe_envelope = object.__new__(ComparisonValidationEnvelopeV2)
    report = validate_comparison_v2(unsafe_envelope)
    assert report.status is ComparisonValidationStatus.UNEVALUABLE
    assert report.findings == (ComparisonFindingCode.INPUT_TYPE_INVALID,)


def test_decimal_canonicalization_is_context_independent_and_bounded() -> None:
    with localcontext() as context:
        context.prec = 2
        assert canonical_decimal(Decimal("12345678901234567890.1234567890")) == (
            "12345678901234567890.123456789"
        )
    assert canonical_decimal(Decimal("-0.0000000001")) == "-0.0000000001"
    assert canonical_decimal(Decimal("-0")) == "0"
    with pytest.raises(ComparisonRuntimeValueError):
        canonical_decimal(Decimal("123456789012345678901"))
    with pytest.raises(ComparisonRuntimeValueError):
        canonical_decimal(Decimal("1E+999999999"))
    with pytest.raises(ComparisonRuntimeValueError):
        canonical_decimal(Decimal("1E-999999999"))
    with pytest.raises(ComparisonRuntimeValueError):
        TypedComparisonValue(
            data_type=ComparisonAxisDataType.DECIMAL,
            decimal_value=Decimal("NaN"),
        )


def test_identifier_repr_and_serialization_are_redacted() -> None:
    value = CandidateUniverse(
        universe_id=CandidateUniverseId(UUID("20202020-2020-4020-8020-202020202020")),
        version_no=1,
        products=(),
        candidate_universe_sha256=Sha256Digest("1" * 64),
    )
    assert "20202020" not in repr(value)
    with pytest.raises(TypeError):
        value.__reduce_ex__(4)
