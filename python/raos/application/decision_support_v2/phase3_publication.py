"""Local Phase 3 use cases for human review binding and semantic sealing."""

from __future__ import annotations

from raos.domain.decision_support_v2.phase3_publication import (
    Phase3ClaimBinding,
    Phase3HumanReviewReceipt,
    Phase3PreActionBinding,
    Phase3PublicationPackage,
    Phase3ReviewCandidate,
    Phase3StructuredDataExpectation,
    Phase3WordPressUpdateFields,
    Phase3WordPressUpdatePayload,
)
from raos.domain.decision_support_v2.publication import PublicationPackage


def derive_phase3_structured_data_expectation(
    *, fields: Phase3WordPressUpdateFields
) -> Phase3StructuredDataExpectation:
    """Derive the closed JSON-LD expectation from reviewed WordPress fields."""

    return Phase3StructuredDataExpectation.from_wordpress_fields(fields)


def bind_verified_preaction(
    *,
    payload: Phase3WordPressUpdatePayload,
    binding: Phase3PreActionBinding,
) -> Phase3WordPressUpdatePayload:
    """Rebind a historical payload to verified current public state."""

    return payload.bind_verified_preaction(binding)


def build_phase3_review_candidate(
    *,
    phase2_candidate: PublicationPackage,
    claim_bindings: tuple[Phase3ClaimBinding, ...],
    update_payload: Phase3WordPressUpdatePayload,
) -> Phase3ReviewCandidate:
    """Bind the exact Phase 2 candidate and published-post update for review."""

    return Phase3ReviewCandidate.from_phase2(
        candidate=phase2_candidate,
        claim_bindings=claim_bindings,
        update_payload=update_payload,
    )


def bind_human_review(
    *,
    candidate: Phase3ReviewCandidate,
    receipt: Phase3HumanReviewReceipt,
) -> Phase3PublicationPackage:
    """Bind a non-synthetic human receipt without gaining write authority."""

    return candidate.bind_review(receipt)


def seal_reviewed_package(
    package: Phase3PublicationPackage,
) -> Phase3PublicationPackage:
    """Create a local semantic seal after all claim gates pass."""

    return package.seal()


__all__ = [
    "bind_human_review",
    "bind_verified_preaction",
    "build_phase3_review_candidate",
    "derive_phase3_structured_data_expectation",
    "seal_reviewed_package",
]
