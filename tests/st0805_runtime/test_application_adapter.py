from __future__ import annotations

import json
from uuid import UUID

import pytest

from raos.adapters.recorded_policy_engine import (
    ProhibitedPolicyInputError,
    RecordedPolicyAdapter,
    RecordedPolicyError,
    load_recorded_policy_fixture,
)
from raos.application.editorial.policy_engine import (
    EvaluatePolicyService,
    RecordPolicyReportService,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.editorial.ids import ArticleVersionId
from raos.domain.editorial.policy_engine_v2 import (
    PolicyEvaluationStatusV2,
    evaluate_editorial_policy_v2,
    unavailable_policy_report,
)


def test_strict_fixture_round_trip(fixture_bytes: bytes) -> None:
    envelope = load_recorded_policy_fixture(fixture_bytes)
    report = evaluate_editorial_policy_v2(envelope)
    report.require_valid()
    assert report.status is PolicyEvaluationStatusV2.LOCAL_EVALUATED


def test_duplicate_and_unknown_members_are_rejected(fixture_bytes: bytes) -> None:
    duplicate = fixture_bytes.replace(
        b'"schema_version": 2,',
        b'"schema_version": 2, "schema_version": 2,',
        1,
    )
    with pytest.raises(RecordedPolicyError):
        load_recorded_policy_fixture(duplicate)

    payload = json.loads(fixture_bytes)
    payload["unexpected"] = False
    with pytest.raises(RecordedPolicyError):
        load_recorded_policy_fixture(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "alias",
    (
        "affiliateRate",
        "FinancialBenefit",
        "Ｃｏｍｍｉｓｓｉｏｎ",
        "R3V3NUE",
        "EＰC",
        "rpm",
        "成果報酬",
        "料率",
        "報酬",
        "収益",
        "利益",
    ),
)
def test_deep_unicode_case_and_leet_finance_alias_keys_are_rejected(
    fixture_bytes: bytes,
    alias: str,
) -> None:
    payload = json.loads(fixture_bytes)
    payload["policy_seed"]["policy_results"][0][alias] = {"nested": [1]}
    encoded = json.dumps(payload, ensure_ascii=False).encode()
    with pytest.raises(ProhibitedPolicyInputError):
        load_recorded_policy_fixture(encoded)


def test_schema_owned_affiliate_disclosure_flag_remains_valid(
    fixture_bytes: bytes,
) -> None:
    payload = json.loads(fixture_bytes)
    assert (
        payload["draft"]["content_ast"]["publication_flags"]["affiliate_content"]
        is True
    )
    load_recorded_policy_fixture(fixture_bytes)


def test_fixture_size_and_scalar_shapes_are_bounded(fixture_bytes: bytes) -> None:
    with pytest.raises(RecordedPolicyError):
        load_recorded_policy_fixture(b"{" + b" " * (8 * 1024 * 1024))
    payload = json.loads(fixture_bytes)
    payload["policy_seed"]["waiver_policy_ids"] = ["POL-CONT-019"] * 41
    with pytest.raises(RecordedPolicyError):
        load_recorded_policy_fixture(json.dumps(payload).encode())


def test_adapter_and_services_re_resolve_and_record_process_local_metadata(
    fixture_bytes: bytes,
) -> None:
    envelope = load_recorded_policy_fixture(fixture_bytes)
    article_version_id = ArticleVersionId(envelope.draft.snapshot.version_id)
    adapter = RecordedPolicyAdapter(
        environment=RuntimeEnvironment.CI,
        fixtures=(fixture_bytes,),
        capacity=2,
    )
    evaluator = EvaluatePolicyService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    recorder = RecordPolicyReportService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
        appender=adapter,
    )
    report = evaluator.evaluate(article_version_id)
    first = recorder.record(article_version_id, report)
    second = recorder.record(article_version_id, report)

    assert first == second
    assert first.sequence == 1
    assert first.report_sha256 == report.report_sha256
    assert first.approval_authorized is False
    assert first.apply_authorized is False
    assert first.publication_authorized is False
    assert first.ranking_override_authorized is False
    assert adapter.receipts() == (first,)


def test_record_service_refuses_non_derived_report(fixture_bytes: bytes) -> None:
    envelope = load_recorded_policy_fixture(fixture_bytes)
    article_version_id = ArticleVersionId(envelope.draft.snapshot.version_id)
    adapter = RecordedPolicyAdapter(
        environment=RuntimeEnvironment.ENV_DEV,
        fixtures=(fixture_bytes,),
    )
    recorder = RecordPolicyReportService(
        environment=RuntimeEnvironment.ENV_DEV,
        reader=adapter,
        appender=adapter,
    )
    with pytest.raises(ValueError, match="POLICY_EVALUATION_RECORD_MISMATCH"):
        recorder.record(article_version_id, unavailable_policy_report())


def test_nonlocal_environment_is_rejected(fixture_bytes: bytes) -> None:
    with pytest.raises(RecordedPolicyError):
        RecordedPolicyAdapter(
            environment=RuntimeEnvironment.PRODUCTION,
            fixtures=(fixture_bytes,),
        )
    envelope = load_recorded_policy_fixture(fixture_bytes)
    adapter = RecordedPolicyAdapter(
        environment=RuntimeEnvironment.CI,
        fixtures=(fixture_bytes,),
    )
    with pytest.raises(ValueError, match="INVALID_POLICY_EVALUATION_SERVICE"):
        EvaluatePolicyService(
            environment=RuntimeEnvironment.PRODUCTION,
            reader=adapter,
        )
    assert envelope.draft.snapshot.state.value == "DRAFT"


def test_unknown_article_version_returns_authority_free_unevaluable(
    fixture_bytes: bytes,
) -> None:
    adapter = RecordedPolicyAdapter(
        environment=RuntimeEnvironment.CI,
        fixtures=(fixture_bytes,),
    )
    service = EvaluatePolicyService(
        environment=RuntimeEnvironment.CI,
        reader=adapter,
    )
    missing = ArticleVersionId(UUID("018f3e90-7b00-7000-8000-000000000899"))
    report = service.evaluate(missing)
    assert report.status is PolicyEvaluationStatusV2.UNEVALUABLE
    assert report.publication_authorized is False
