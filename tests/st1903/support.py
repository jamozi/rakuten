from __future__ import annotations

from collections.abc import Callable
import json

from raos.domain.publishing.partial_auto_publication import (
    LowRiskChangeClass,
    PartialAutoPublicationCandidate,
    PartialAutoPublicationCommand,
    PartialAutoPublicationScope,
    canonical_json_bytes,
    sha256_bytes,
)


def command_for(
    payload: bytes,
    *,
    scope: PartialAutoPublicationScope = (
        PartialAutoPublicationScope.RECORDED_SYNTHETIC_ELIGIBILITY_EVALUATION_ONLY
    ),
) -> PartialAutoPublicationCommand:
    return PartialAutoPublicationCommand(
        recording_id="st1903_recorded_evaluation_v1",
        source_sha256=sha256_bytes(payload),
        source_bytes=len(payload),
        scope=scope,
    )


def mutate_fixture(
    payload: bytes,
    operation: Callable[[dict[str, object]], None],
    *,
    rebind_candidate: bool = False,
) -> bytes:
    parsed = json.loads(payload)
    assert type(parsed) is dict
    operation(parsed)
    if rebind_candidate:
        candidate = parsed["candidate"]
        assert type(candidate) is dict
        material = dict(candidate)
        material.pop("candidate_sha256", None)
        candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(material))
    return canonical_json_bytes(parsed) + b"\n"


def candidate_with(**overrides: object) -> PartialAutoPublicationCandidate:
    material: dict[str, object] = {
        "affiliate_destination_change": False,
        "article_id": "AT-1903-SYNTHETIC-001",
        "candidate_id": "st1903-synthetic-suppression-001",
        "change_class": LowRiskChangeClass.STALE_VALUE_SUPPRESSION_ONLY.value,
        "change_count": 1,
        "claim_change": False,
        "content_addition": False,
        "finance_input_present": False,
        "high_risk": False,
        "personal_data_present": False,
        "price_or_stock_assertion_added": False,
        "product_identity_change": False,
        "public_write_requested": False,
        "raw_html_present": False,
        "recommendation_order_change": False,
        "risk_ambiguous": False,
        "synthetic": True,
    }
    material.update(overrides)
    change_count = material["change_count"]
    if type(change_count) is not int:
        raise AssertionError("test change_count must be an integer")
    return PartialAutoPublicationCandidate(
        candidate_id=str(material["candidate_id"]),
        article_id=str(material["article_id"]),
        candidate_sha256=sha256_bytes(canonical_json_bytes(material)),
        change_class=LowRiskChangeClass(str(material["change_class"])),
        change_count=change_count,
        synthetic=material["synthetic"] is True,
        risk_ambiguous=material["risk_ambiguous"] is True,
        high_risk=material["high_risk"] is True,
        content_addition=material["content_addition"] is True,
        claim_change=material["claim_change"] is True,
        recommendation_order_change=(material["recommendation_order_change"] is True),
        product_identity_change=material["product_identity_change"] is True,
        affiliate_destination_change=(material["affiliate_destination_change"] is True),
        raw_html_present=material["raw_html_present"] is True,
        price_or_stock_assertion_added=(
            material["price_or_stock_assertion_added"] is True
        ),
        personal_data_present=material["personal_data_present"] is True,
        finance_input_present=material["finance_input_present"] is True,
        public_write_requested=material["public_write_requested"] is True,
    )
