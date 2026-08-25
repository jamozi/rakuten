from __future__ import annotations

from dataclasses import replace
import json
from uuid import UUID

import pytest

from raos.adapters.recorded_recommendation import (
    ProhibitedRecommendationInputError,
    RecordedRecommendationAdapter,
    RecordedRecommendationError,
    load_recorded_recommendation_fixture,
)
from raos.application.editorial.recommendation import (
    EvaluateRecommendationService,
    RecordRecommendationService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.recommendation_v2 import (
    RecommendationEvaluationStatus,
    evaluate_recommendations_v2,
)
from raos.domain.shared.persistence import Sha256Digest


def _adapter(fixture_bytes: bytes) -> RecordedRecommendationAdapter:
    return RecordedRecommendationAdapter(
        environment=RuntimeEnvironment.CI,
        capacity=4,
        snapshot_bytes=(fixture_bytes,),
    )


def _payload(material: object) -> bytes:
    return (
        json.dumps(
            material,
            ensure_ascii=True,
            allow_nan=False,
            indent=2,
            separators=(",", ": "),
        )
        + "\n"
    ).encode("ascii")


def test_local_services_evaluate_and_record_idempotently(fixture_bytes: bytes) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_recommendation_fixture(fixture_bytes)
    article_version_id = envelope.context.article_version_id
    evaluator = EvaluateRecommendationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    recorder = RecordRecommendationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )

    report = evaluator.evaluate(article_version_id)
    assert report.status is RecommendationEvaluationStatus.LOCAL_CALCULATED
    first = recorder.record(article_version_id, report)
    second = recorder.record(article_version_id, report)
    assert first == second
    assert first.sequence == 1
    assert first.report_sha256 == report.report_sha256
    assert not first.publication_authorized
    assert not first.ranking_authorized
    assert adapter.receipts() == (first,)


def test_services_reject_nonlocal_environments(fixture_bytes: bytes) -> None:
    with pytest.raises(RecordedRecommendationError):
        RecordedRecommendationAdapter(
            environment=RuntimeEnvironment.PRODUCTION,
            capacity=1,
            snapshot_bytes=(fixture_bytes,),
        )
    adapter = _adapter(fixture_bytes)
    with pytest.raises(ValueError, match="INVALID_RECOMMENDATION_SERVICE"):
        EvaluateRecommendationService(
            environment=RuntimeEnvironment.STAGING,
            reader=adapter,
        )


def test_missing_article_version_returns_explicit_unavailable(
    fixture_bytes: bytes,
) -> None:
    adapter = _adapter(fixture_bytes)
    service = EvaluateRecommendationService(
        environment=RuntimeEnvironment.ENV_DEV,
        reader=adapter,
    )
    report = service.evaluate(
        ArticleVersionId(UUID("ffffffff-ffff-4fff-8fff-ffffffffffff"))
    )
    assert report.status is RecommendationEvaluationStatus.UNEVALUABLE
    assert report.candidates == ()
    assert report.ranking_order == ()


def test_record_service_reresolves_and_rejects_forged_report(
    fixture_bytes: bytes,
) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_recommendation_fixture(fixture_bytes)
    report = evaluate_recommendations_v2(envelope)
    forged = replace(report, report_sha256=Sha256Digest("f" * 64))
    service = RecordRecommendationService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    with pytest.raises(Exception):
        service.record(envelope.context.article_version_id, forged)
    assert adapter.receipts() == ()


@pytest.mark.parametrize(
    "alias",
    (
        "affiliateRewardRate",
        "ＡＦＦＩＬＩＡＴＥ＿ＲＡＴＥ",
        "Aff1l1ate-R3ward",
        "confirmedCommission",
        "利益率",
        "ＥＰＣ",
        "rPm",
    ),
)
def test_nested_alias_keys_and_values_are_rejected_before_shape_resolution(
    fixture_bytes: bytes,
    alias: str,
) -> None:
    material = json.loads(fixture_bytes)
    material["comparison_report"]["nested_unknown"] = [
        {alias: "SAFE"},
        {"safe": alias},
    ]
    with pytest.raises(
        ProhibitedRecommendationInputError,
        match="PROHIBITED_RECOMMENDATION_INPUT",
    ):
        load_recorded_recommendation_fixture(_payload(material))


@pytest.mark.parametrize(
    "mutator",
    (
        lambda material: material["declared_hashes"].__setitem__(
            "recommendation_input_sha256", "f" * 64
        ),
        lambda material: material["comparison_record_receipt"].__setitem__(
            "report_sha256", "f" * 64
        ),
        lambda material: material["comparison_report"].__setitem__(
            "report_sha256", "f" * 64
        ),
        lambda material: material["dimensions"][0].__setitem__("weight", "1E+999999"),
        lambda material: material["assessments"][0].__setitem__(
            "normalized_score", True
        ),
    ),
)
def test_hash_decimal_and_type_tampering_fails_closed(
    fixture_bytes: bytes,
    mutator: object,
) -> None:
    material = json.loads(fixture_bytes)
    mutator(material)  # type: ignore[operator]
    with pytest.raises(RecordedRecommendationError):
        load_recorded_recommendation_fixture(_payload(material))


def test_duplicate_keys_float_depth_and_oversized_strings_fail_closed(
    fixture_bytes: bytes,
) -> None:
    duplicate = fixture_bytes.replace(
        b'"schema_version": 2,',
        b'"schema_version": 2,\n  "schema_version": 2,',
        1,
    )
    with pytest.raises(RecordedRecommendationError):
        load_recorded_recommendation_fixture(duplicate)

    material = json.loads(fixture_bytes)
    material["comparison_report"]["unexpected_float"] = 1.5
    with pytest.raises(RecordedRecommendationError):
        load_recorded_recommendation_fixture(_payload(material))

    material = json.loads(fixture_bytes)
    nested: object = "SAFE"
    for _ in range(34):
        nested = [nested]
    material["comparison_report"]["unexpected_depth"] = nested
    with pytest.raises(RecordedRecommendationError):
        load_recorded_recommendation_fixture(_payload(material))

    material = json.loads(fixture_bytes)
    material["comparison_report"]["unexpected_string"] = "A" * 4_097
    with pytest.raises(RecordedRecommendationError):
        load_recorded_recommendation_fixture(_payload(material))


def test_adapter_rechecks_payload_anchor_and_has_no_mutation_surface(
    fixture_bytes: bytes,
) -> None:
    adapter = _adapter(fixture_bytes)
    envelope = load_recorded_recommendation_fixture(fixture_bytes)
    adapter._snapshot_bytes = (fixture_bytes + b" ",)  # noqa: SLF001
    with pytest.raises(RecordedRecommendationError):
        adapter.get_snapshot(envelope.context.article_version_id)
    public = {name for name in dir(adapter) if not name.startswith("_")}
    assert public == {"append_report", "environment", "get_snapshot", "receipts"}
    assert "<redacted" in repr(adapter)
    with pytest.raises(TypeError, match="serialization"):
        adapter.__reduce_ex__(4)
