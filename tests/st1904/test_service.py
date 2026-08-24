"""Deterministic behavior tests for the ST-1904 evaluator."""

from __future__ import annotations

import json

import pytest

from raos.adapters.recorded_multi_category import (
    CallerBytesRecordedMultiCategorySource,
)
from raos.application.catalog.multi_category import (
    MultiCategoryEvaluationService,
    evaluate_recorded_multi_category,
)
from raos.config.runtime import RuntimeEnvironment
from raos.domain.catalog.multi_category import (
    DEFAULT_MULTI_CATEGORY_SCOPE,
    IdentityDisposition,
    IdentityRuleState,
    MultiCategoryBoundaryStatus,
    MultiCategoryEvaluationCommand,
    MultiCategoryFailure,
    MultiCategoryFailureCode,
    MultiCategoryOutcome,
    MultiCategoryScope,
    RecordedMultiCategoryBundle,
    TemplateCandidateState,
    report_projection,
)
from tests.st1904.support import command, fixture_bytes, recorded_bundle


def test_default_is_disabled_and_closed_scope_has_no_live_member() -> None:
    assert DEFAULT_MULTI_CATEGORY_SCOPE is MultiCategoryScope.DISABLED
    assert {scope.value for scope in MultiCategoryScope} == {
        "DISABLED",
        "RECORDED_SYNTHETIC_CONTRACT_EVALUATION_ONLY",
    }


def test_recorded_fixture_is_deterministic_non_attesting_compatibility_only() -> None:
    bundle = recorded_bundle()
    first = evaluate_recorded_multi_category(bundle)
    second = evaluate_recorded_multi_category(bundle)
    assert first == second
    assert report_projection(first) == report_projection(second)
    assert first.outcome is (
        MultiCategoryOutcome.INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY
    )
    assert first.category_ids == (
        "synthetic_category_alpha",
        "synthetic_category_beta",
    )
    assert first.template_candidates == (
        ("synthetic_category_alpha", "TPL-AT-001"),
        ("synthetic_category_beta", "TPL-AT-003"),
    )
    assert first.human_review_category_count == 2
    assert first.freshness_safe_default_count == 2
    assert first.authority == "NONE"
    assert first.category_selection is (
        MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    )
    assert first.identity_rules is MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    assert first.freshness_sla is MultiCategoryBoundaryStatus.HUMAN_DECISION_REQUIRED
    assert first.category_activation is MultiCategoryBoundaryStatus.DISABLED
    assert first.template_activation is MultiCategoryBoundaryStatus.DISABLED
    assert first.release_decision is (
        MultiCategoryBoundaryStatus.RELEASE_DECISION_REQUIRED
    )
    assert first.canonical_status is MultiCategoryBoundaryStatus.DEFERRED_POST_MVP
    assert first.formal_tst_032 is MultiCategoryBoundaryStatus.NOT_EXECUTED
    assert (
        json.loads(json.dumps(report_projection(first)))["report_sha256"]
        == first.report_sha256
    )


def test_all_profiles_preserve_identity_freshness_and_inactive_templates() -> None:
    bundle = recorded_bundle()
    for category in bundle.categories:
        assert category.synthetic is True
        assert category.real_category_selected is False
        assert category.identity_rule_state is (
            IdentityRuleState.NOT_DEFINED_UNRESOLVED_OD_006
        )
        assert (
            category.identity_disposition is IdentityDisposition.HUMAN_REVIEW_REQUIRED
        )
        assert category.automatic_merge_enabled is False
        assert category.automatic_split_enabled is False
        assert category.category_override is None
        assert category.provider_override is None
        assert category.stale_never_fresh is True
        assert category.recommendation_auto_reorder == "FORBIDDEN"
        assert category.template_state is (
            TemplateCandidateState.SYNTHETIC_CANDIDATE_NOT_APPLIED
        )
        assert category.template_active is False
        assert category.human_review_required is True
    for flag in (
        bundle.runtime_enabled,
        bundle.persistence_enabled,
        bundle.provider_access_enabled,
        bundle.network_enabled,
        bundle.identity_decisions_applied,
        bundle.freshness_overrides_applied,
        bundle.templates_activated,
        bundle.editorial_mutation_enabled,
        bundle.recommendation_mutation_enabled,
        bundle.publication_authorized,
        bundle.release_authorized,
        bundle.production_authorized,
    ):
        assert flag is False


class _CountingSource:
    def __init__(self) -> None:
        self.calls = 0

    def read(
        self, command_value: MultiCategoryEvaluationCommand
    ) -> RecordedMultiCategoryBundle:
        del command_value
        self.calls += 1
        return recorded_bundle()


def test_disabled_scope_fails_before_port_call() -> None:
    source = _CountingSource()
    service = MultiCategoryEvaluationService(
        environment=RuntimeEnvironment.CI,
        source=source,
    )
    with pytest.raises(MultiCategoryFailure) as caught:
        service.evaluate(command(scope=MultiCategoryScope.DISABLED))
    assert caught.value.code is MultiCategoryFailureCode.FEATURE_DISABLED
    assert source.calls == 0


def test_service_accepts_only_local_environments_and_one_shot_source() -> None:
    source = CallerBytesRecordedMultiCategorySource(fixture_bytes())
    service = MultiCategoryEvaluationService(
        environment=RuntimeEnvironment.ENV_DEV,
        source=source,
    )
    assert service.evaluate(command()).outcome is (
        MultiCategoryOutcome.INTERFACE_COMPATIBLE_RECORDED_SYNTHETIC_ONLY
    )
    with pytest.raises(MultiCategoryFailure) as caught:
        service.evaluate(command())
    assert caught.value.code is MultiCategoryFailureCode.SOURCE_EXHAUSTED
    for environment in (
        RuntimeEnvironment.INTEGRATION,
        RuntimeEnvironment.STAGING,
        RuntimeEnvironment.RECOVERY,
        RuntimeEnvironment.PRODUCTION,
    ):
        with pytest.raises(MultiCategoryFailure):
            MultiCategoryEvaluationService(
                environment=environment,
                source=CallerBytesRecordedMultiCategorySource(fixture_bytes()),
            )


def test_category_and_release_approval_inputs_are_structurally_prohibited() -> None:
    baseline = command()
    with pytest.raises(MultiCategoryFailure) as category:
        type(baseline)(
            recording_id=baseline.recording_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            expected_binding_set_sha256=baseline.expected_binding_set_sha256,
            scope=baseline.scope,
            category_approval_sha256="a" * 64,
        )
    assert category.value.code is (
        MultiCategoryFailureCode.CATEGORY_APPROVAL_PROHIBITED
    )
    with pytest.raises(MultiCategoryFailure) as release:
        type(baseline)(
            recording_id=baseline.recording_id,
            source_sha256=baseline.source_sha256,
            source_bytes=baseline.source_bytes,
            expected_binding_set_sha256=baseline.expected_binding_set_sha256,
            scope=baseline.scope,
            release_decision_sha256="b" * 64,
        )
    assert release.value.code is MultiCategoryFailureCode.RELEASE_DECISION_PROHIBITED
