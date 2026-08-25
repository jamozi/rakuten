from __future__ import annotations

# pyright: reportPrivateUsage=false

from copy import deepcopy
from dataclasses import replace
import json
from typing import cast

import pytest

from raos.adapters.recorded_public_projection_v2 import RecordedPublicProjectionStep
from raos.domain.publishing.public_projection_v2 import (
    LOCAL_DISCLOSURE_TEXT,
    PUBLIC_ARTICLE_FIELDS,
    PUBLIC_BLOCK_FIELDS,
    PUBLIC_PROJECTION_FIELDS,
    PUBLIC_ROUTE_FIELDS,
    ROW_COUNT_FIELDS,
    ProjectionCompatibility,
    PublicProjectionFailure,
    PublicProjectionFailureCode,
    PublicProjectionRequestV2,
    build_public_projection_v2,
)
from raos.domain.shared.persistence import Sha256Digest
from raos.domain.publishing import public_projection_v2 as domain


def test_projection_is_deterministic_and_exactly_source_bound(
    step: RecordedPublicProjectionStep,
) -> None:
    rebuilt = build_public_projection_v2(request=step.request, source=step.source)
    assert rebuilt.canonical_bytes() == step.result.canonical_bytes()
    assert rebuilt.projection_bytes == step.result.projection_bytes
    assert rebuilt.snapshot_sha256 == step.source.snapshot_result.snapshot_sha256
    assert rebuilt.compatibility is (
        ProjectionCompatibility.COMMON_PUBLIC_SUBSET_LEGACY_RECONCILIATION_REQUIRED
    )


def test_projection_uses_closed_public_api_shapes(
    step: RecordedPublicProjectionStep,
) -> None:
    projection = step.result.projection()
    article = cast(dict[str, object], projection["article"])
    route = cast(dict[str, object], projection["route"])
    row_counts = cast(dict[str, object], projection["row_counts"])
    assert frozenset(projection) == frozenset(PUBLIC_PROJECTION_FIELDS)
    assert frozenset(article) == frozenset(PUBLIC_ARTICLE_FIELDS)
    assert frozenset(route) == frozenset(PUBLIC_ROUTE_FIELDS)
    assert frozenset(row_counts) == frozenset(ROW_COUNT_FIELDS)
    assert article["canonical_path"] == "/synthetic-recorded-policy-seo/"
    assert article["disclosure_text"] == LOCAL_DISCLOSURE_TEXT
    assert article["freshness_status"] == "UNKNOWN"
    assert article["structured_data"] == {}
    assert article["product_cards"] == []
    assert route == {
        "path": article["canonical_path"],
        "route_type": "ARTICLE",
        "article_id": article["article_id"],
        "redirect_path": None,
        "http_status": 200,
        "is_indexable": False,
        "projection_generation": 1,
    }
    assert projection["row_counts"] == {
        "public_article": 1,
        "public_article_block": 9,
        "public_offer": 0,
        "public_product_card": 0,
        "public_route": 1,
    }
    blocks = cast(list[dict[str, object]], article["blocks"])
    for index, block in enumerate(blocks):
        assert frozenset(block) == frozenset(PUBLIC_BLOCK_FIELDS)
        assert block["block_key"] == f"block-{index + 1:03d}"
        assert block["position"] == index
        assert block["heading_level"] is None
        assert block["heading_text"] is None
        assert block["rendered_html"] is None
        payload = cast(dict[str, object], block["render_payload"])
        assert frozenset(payload) == frozenset(("source_type", "text"))


def test_projection_redacts_internal_evidence_and_finance_fields(
    step: RecordedPublicProjectionStep,
) -> None:
    serialized = json.dumps(step.result.projection(), ensure_ascii=False).casefold()
    for token in (
        "approval_ids",
        "article_version_id",
        "claim_ids",
        "commission",
        "epc",
        "evidence",
        "finance",
        "input_hashes",
        "methodology_ref",
        "policy_bundle_version",
        "profit",
        "quality_result_id",
        "recommendation_ref",
        "revenue",
        "rpm",
        "safe_offer_projection_version",
        "source_packet_version_ref",
    ):
        assert token not in serialized


def test_projection_result_carries_no_side_effect_authority(
    step: RecordedPublicProjectionStep,
) -> None:
    result = step.result
    assert result.persisted is False
    assert result.event_emitted is False
    assert result.route_activated is False
    assert result.public_read_served is False
    assert result.public_projection_authorized is False
    assert result.publication_authorized is False
    assert result.release_authorized is False
    assert result.production_authorized is False
    assert set(json.loads(result.canonical_bytes())["external_gates"].values()) == {
        "NOT_EXECUTED"
    }


def test_source_binding_hash_mismatch_fails_closed(
    step: RecordedPublicProjectionStep,
) -> None:
    conflicting = PublicProjectionRequestV2(
        expected_source_binding_sha256=Sha256Digest("0" * 64),
        idempotency_key="st0904-v2-conflicting-projection",
    )
    with pytest.raises(PublicProjectionFailure) as captured:
        build_public_projection_v2(request=conflicting, source=step.source)
    assert captured.value.code is (
        PublicProjectionFailureCode.SNAPSHOT_BINDING_MISMATCH
    )


def test_projection_generation_cannot_be_promoted(
    step: RecordedPublicProjectionStep,
) -> None:
    with pytest.raises(PublicProjectionFailure) as captured:
        replace(step.request, projection_generation=2)
    assert captured.value.code is PublicProjectionFailureCode.INVALID_ARGUMENT


def test_arbitrary_types_fail_closed(step: RecordedPublicProjectionStep) -> None:
    with pytest.raises(PublicProjectionFailure) as captured:
        build_public_projection_v2(request=step.request, source=object())  # type: ignore[arg-type]
    assert captured.value.code is PublicProjectionFailureCode.INVALID_ARGUMENT


def test_unknown_content_ast_field_fails_closed(
    step: RecordedPublicProjectionStep,
) -> None:
    snapshot = step.source.snapshot_result.snapshot()
    ast = cast(dict[str, object], deepcopy(snapshot["renderable_content"]))
    ast["unexpected_internal_field"] = "must-not-project"
    with pytest.raises(PublicProjectionFailure) as captured:
        domain._validate_current_content_ast(ast)
    assert captured.value.code is PublicProjectionFailureCode.SNAPSHOT_INVALID
