from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone, tzinfo
import hashlib
from pathlib import Path
from typing import cast

import pytest

from raos.adapters.recorded_ai_output_validation import (
    RecordedAiOutputValidationCaseReader,
    RecordedAiOutputValidationError,
    TrustedTaskValidationProfiles,
    load_recorded_ai_output_validation_fixture,
    load_trusted_ai_output_validation_profiles,
)
from raos.application.ai.output_validation import EvaluateAiOutputService
from raos.config.runtime import RuntimeEnvironment
from raos.domain.ai.output_validation import (
    AiOutputValidationError,
    AiOutputValidationInput,
    FailureDisposition,
    LocalValidationStatus,
    SemanticReceiptKind,
    TRUSTED_PROFILE_REGISTRY_SHA256,
    TRUSTED_PROFILE_SHA256_BY_TASK,
    evaluate_ai_output,
    failure_disposition,
)
from scripts import build_st0705_ai_output_validation_runtime as generator


ROOT = Path(__file__).resolve().parents[2]


def test_owner_generator_is_reproducible_and_all_profiles_are_exact(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> None:
    generator.build(check=True)
    profiles = trusted_profiles.values()
    assert tuple(item.task_id for item in profiles) == tuple(
        f"AIT-{number:03d}" for number in range(1, 13)
    )
    assert {item.task_id: item.profile_sha256 for item in profiles} == dict(
        TRUSTED_PROFILE_SHA256_BY_TASK
    )
    assert (
        TRUSTED_PROFILE_REGISTRY_SHA256.value
        == generator.trust_anchors(generator.load_contract())["profile_registry_sha256"]
    )
    for profile in profiles:
        schema = ROOT / profile.output_schema_path
        assert schema.is_file()
        assert (
            hashlib.sha256(schema.read_bytes()).hexdigest()
            == profile.output_schema_sha256.value
        )
        checks = set(profile.required_runtime_checks) | set(
            profile.prompt_required_runtime_checks
        )
        assert {item.check_name for item in profile.runtime_check_bindings} == checks
        assert profile.max_output_bytes == 4 * 1024 * 1024


def test_all_profiles_bind_the_repaired_st0702_context_contract(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> None:
    expected = hashlib.sha256((ROOT / generator.CONTEXT_CONTRACT_PATH).read_bytes()).hexdigest()
    for profile in trusted_profiles.values():
        context_receipts = profile.required_semantic_receipts[:2]
        assert tuple(item.receipt_kind for item in context_receipts) == (
            SemanticReceiptKind.CONTEXT_MANIFEST_BINDING,
            SemanticReceiptKind.INPUT_TAINT_SCAN,
        )
        assert all(item.owner_story_id == "ST-0702" for item in context_receipts)
        assert all(
            item.owner_contract_sha256.value == expected for item in context_receipts
        )


def test_profile_capability_gaps_versions_and_disabled_lifecycle_are_explicit(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> None:
    ait004 = trusted_profiles.get("AIT-004")
    ait005 = trusted_profiles.get("AIT-005")
    ait009 = trusted_profiles.get("AIT-009")
    ait011 = trusted_profiles.get("AIT-011")
    ait012 = trusted_profiles.get("AIT-012")
    assert ait004 is not None
    assert ait005 is not None
    assert ait009 is not None
    assert ait011 is not None
    assert ait012 is not None
    assert [item.pointer for item in ait004.schema_version_locators] == [
        "/schema_version",
        "/article/schema_version",
    ]
    assert ait005.semantic_capability_limitations == (
        "ALIGNMENT_SUBJECT_REFS_EVIDENCE_REQUIREMENTS_TEMPORAL_SCOPE_ABSENT_FROM_SCHEMA",
    )
    assert ait009.schema_version_locators == ()
    assert ait009.semantic_capability_limitations == (
        "ALIGNMENT_PRIMARY_DECISION_INTENT_CLUSTER_MERGE_REFS_ABSENT_FROM_SCHEMA",
    )
    assert ait011.lifecycle == "GATE_1_PROPOSED_DISABLED"
    assert ait012.lifecycle == "GATE_2_PROPOSED_DISABLED"
    assert any(
        item.receipt_kind is SemanticReceiptKind.REFRESH_DIFF_BINDING
        for item in ait012.required_semantic_receipts
    )


def test_registry_is_content_addressed_and_runtime_lookup_is_immutable() -> None:
    payload = (ROOT / generator.PROFILE_REGISTRY_PATH).read_bytes()
    with pytest.raises(RecordedAiOutputValidationError):
        load_trusted_ai_output_validation_profiles(payload + b" ")
    profiles = load_trusted_ai_output_validation_profiles(payload)
    with pytest.raises(TypeError):
        cast(dict[str, object], TRUSTED_PROFILE_SHA256_BY_TASK)["AIT-001"] = (
            TRUSTED_PROFILE_SHA256_BY_TASK["AIT-002"]
        )
    with pytest.raises(RecordedAiOutputValidationError):
        TrustedTaskValidationProfiles(
            profiles={item.task_id: item for item in profiles.values()},
            trust_anchor=object(),
        )


def test_pass_report_is_deterministic_redacted_and_has_no_authority(
    passing_input: AiOutputValidationInput,
) -> None:
    first = evaluate_ai_output(passing_input)
    second = evaluate_ai_output(passing_input)
    assert first == second
    assert first.status is LocalValidationStatus.LOCAL_VALIDATED
    assert failure_disposition(first) is FailureDisposition.NO_FAILURE
    assert first.output_sha256 != first.provider_exchange_sha256
    assert first.raw_output_sha256 == first.output_sha256
    assert passing_input.envelope.output_bytes not in first.canonical_bytes()
    assert first.authority == "NONE"
    assert first.publication_authorized is False
    assert first.provider_authorized is False
    assert first.persistence_authorized is False
    assert first.production_eligible is False


def test_application_is_local_read_only_and_fail_closed(
    passing_input: AiOutputValidationInput,
) -> None:
    reader = RecordedAiOutputValidationCaseReader(
        environment=RuntimeEnvironment.CI,
        cases=(("pass", passing_input),),
    )
    service = EvaluateAiOutputService(environment=RuntimeEnvironment.CI, reader=reader)
    assert (
        service.evaluate(case_id="pass", evaluated_at=passing_input.evaluated_at).status
        is LocalValidationStatus.LOCAL_VALIDATED
    )
    missing = service.evaluate(
        case_id="missing", evaluated_at=passing_input.evaluated_at
    )
    assert missing.status is LocalValidationStatus.UNEVALUABLE
    with pytest.raises(ValueError):
        EvaluateAiOutputService(
            environment=RuntimeEnvironment.PRODUCTION, reader=reader
        )


class _ChangingTimezone(tzinfo):
    def __init__(self) -> None:
        self.calls = 0

    def utcoffset(self, value: datetime | None) -> timedelta:
        del value
        self.calls += 1
        return timedelta(0) if self.calls == 1 else timedelta(hours=9)

    def dst(self, value: datetime | None) -> timedelta:
        del value
        return timedelta(0)

    def tzname(self, value: datetime | None) -> str:
        del value
        return "changing"


@pytest.mark.parametrize(
    "invalid_time",
    [
        datetime(2026, 8, 24, 0, 0),
        datetime(2026, 8, 24, 0, 0, tzinfo=timezone(timedelta(hours=9))),
    ],
)
def test_application_rejects_noncanonical_time_before_reader_call(
    passing_input: AiOutputValidationInput, invalid_time: datetime
) -> None:
    reader = RecordedAiOutputValidationCaseReader(
        environment=RuntimeEnvironment.CI,
        cases=(("pass", passing_input),),
    )
    service = EvaluateAiOutputService(environment=RuntimeEnvironment.CI, reader=reader)
    with pytest.raises(ValueError, match="INVALID_AI_OUTPUT_VALIDATION_REQUEST"):
        service.evaluate(case_id="pass", evaluated_at=invalid_time)


def test_application_snapshots_mutating_utc_timezone_before_collaboration(
    passing_input: AiOutputValidationInput,
) -> None:
    reader = RecordedAiOutputValidationCaseReader(
        environment=RuntimeEnvironment.CI,
        cases=(("pass", passing_input),),
    )
    service = EvaluateAiOutputService(environment=RuntimeEnvironment.CI, reader=reader)
    changing = _ChangingTimezone()
    supplied = datetime(2026, 8, 24, 0, 0, tzinfo=changing)
    report = service.evaluate(case_id="pass", evaluated_at=supplied)
    assert report.status is LocalValidationStatus.LOCAL_VALIDATED
    assert report.evaluated_at.tzinfo is timezone.utc
    assert changing.calls == 1


def test_recorded_reader_bounds_cases_ids_and_detects_post_init_mutation(
    passing_input: AiOutputValidationInput,
) -> None:
    with pytest.raises(RecordedAiOutputValidationError):
        RecordedAiOutputValidationCaseReader(
            environment=RuntimeEnvironment.CI,
            cases=tuple((f"case-{number}", passing_input) for number in range(129)),
        )
    with pytest.raises(RecordedAiOutputValidationError):
        RecordedAiOutputValidationCaseReader(
            environment=RuntimeEnvironment.CI,
            cases=(("x" * 121, passing_input),),
        )
    copied = replace(passing_input)
    reader = RecordedAiOutputValidationCaseReader(
        environment=RuntimeEnvironment.CI,
        cases=(("copy", copied),),
    )
    object.__setattr__(
        copied,
        "evaluated_at",
        copied.evaluated_at + timedelta(seconds=1),
    )
    assert reader.get_case("copy") is None


def test_fixture_loader_caps_schema_bytes(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> None:
    with pytest.raises(RecordedAiOutputValidationError):
        load_recorded_ai_output_validation_fixture(
            fixture_bytes=(ROOT / generator.PASS_FIXTURE_PATH).read_bytes(),
            profiles=trusted_profiles,
            schema_bytes=b"{" + b" " * (4 * 1024 * 1024),
        )


def test_profile_collections_and_strings_are_bounded(
    trusted_profiles: TrustedTaskValidationProfiles,
) -> None:
    profile = trusted_profiles.get("AIT-001")
    assert profile is not None
    with pytest.raises(AiOutputValidationError):
        replace(
            profile,
            allowed_input_fields=tuple(f"field-{number}" for number in range(257)),
        )
    with pytest.raises(AiOutputValidationError):
        replace(profile, semantic_capability_limitations=("x" * 4097,))
